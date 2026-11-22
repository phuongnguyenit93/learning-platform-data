# Tính tỷ lệ, trung bình có trọng số và chia cho không trong PostgreSQL

Trong báo cáo kinh doanh, dữ liệu thường không dừng ở việc đếm số hàng hay tính tổng. Chúng ta cần biết **tỷ lệ chuyển đổi**, **tỷ lệ đơn giao thành công**, **giá bán trung bình trên mỗi sản phẩm**, **hiệu quả quảng cáo**, hoặc **tỷ trọng doanh thu của một nhóm**. Những chỉ số này đều liên quan tới phép chia, nhưng chỉ cần chọn sai mẫu số, để phép chia số nguyên làm mất phần thập phân, hoặc lấy trung bình đơn giản của các tỷ lệ có quy mô khác nhau, kết quả có thể sai dù câu SQL chạy thành công.

PostgreSQL cung cấp các công cụ cần thiết để tính đúng những chỉ số này: kiểu `numeric`, phép ép kiểu `::numeric`, các hàm tổng hợp `SUM()`, `COUNT()`, `AVG()`, mệnh đề `FILTER`, phép `NULLIF()` để xử lý mẫu số bằng 0, `CASE` để thể hiện quy tắc nghiệp vụ, `COALESCE()` khi cần giá trị thay thế, cùng khả năng tổng hợp và tính phần trăm theo nhóm.

Bài học thuộc chương **Tổng hợp dữ liệu** của PostgreSQL. Mục tiêu là không chỉ viết SQL tránh lỗi, mà còn **xác định được phép tính đúng về mặt toán học và ý nghĩa dữ liệu**.

## 1. Phân biệt tỷ lệ, trung bình và trung bình có trọng số

Ba phép tính thường bị nhầm lẫn:

- **Tỷ lệ**: số lượng một nhóm so với tập làm mẫu số, ví dụ 20 đăng ký trên 100 lượt truy cập.
- **Trung bình cộng**: tổng giá trị chia số quan sát hợp lệ, ví dụ trung bình giá niêm yết của ba mặt hàng.
- **Trung bình có trọng số**: mỗi giá trị có tầm quan trọng hoặc số lượng đại diện khác nhau, ví dụ giá bình quân trên mỗi đơn vị đã bán.

### 1.1. Tỷ lệ

Với tử số \(a\) và mẫu số \(b\):

\[
r = \frac{a}{b}, \qquad b \ne 0
\]

Ví dụ 20 đăng ký từ 100 lượt truy cập:

\[
r = \frac{20}{100}=0{,}2=20\%
\]

Ở đây cần biết **tử số có thuộc cùng tập quan sát với mẫu số không**. Nếu 20 đăng ký thuộc tuần này nhưng 100 lượt truy cập thuộc tuần trước, SQL vẫn tính ra 20%, nhưng chỉ số không có ý nghĩa như mong muốn.

### 1.2. Trung bình cộng

Với ba mức giá 100.000, 160.000 và 50.000:

\[
\bar{x}=\frac{100000+160000+50000}{3}
\approx 103333{,}33
\]

Phép tính này giả định **mỗi mức giá có trọng số bằng nhau**, bất kể bán được bao nhiêu hàng.

### 1.3. Trung bình có trọng số

Giả sử bán:

| Đơn giá | Số lượng |
|---:|---:|
| 100.000 | 2 |
| 160.000 | 1 |
| 50.000 | 7 |

Giá bình quân **trên mỗi đơn vị đã bán** là:

\[
\bar{x}_w=\frac{\sum_i w_i x_i}{\sum_i w_i}
=\frac{2\times100000+1\times160000+7\times50000}{2+1+7}
=71000
\]

Kết quả 71.000 khác trung bình cộng 103.333,33 vì có đến 7 trong 10 đơn vị được bán với giá 50.000.

**Lựa chọn cách trung bình phụ thuộc câu hỏi nghiệp vụ.** Nếu muốn “giá trung bình của ba mặt hàng trong danh mục”, trung bình cộng có thể phù hợp. Nếu muốn “giá thu được bình quân trên một sản phẩm đã bán”, trọng số phải là số lượng đã bán.

## 2. Lỗi phép chia số nguyên trong PostgreSQL

Đây là lỗi SQL rất dễ bỏ qua:

~~~sql
SELECT
    1 / 2 AS integer_division,
    1::numeric / 2 AS numeric_division,
    1.0 / 2 AS decimal_division;
~~~

Về ý nghĩa:

| Biểu thức | Kết quả |
|---|---:|
| `1 / 2` | `0` |
| `1::numeric / 2` | `0.5` |
| `1.0 / 2` | `0.5` |

Khi cả hai toán hạng là kiểu số nguyên, phép chia số nguyên trong PostgreSQL **bỏ phần thập phân**. Với phép chia âm, phần lẻ bị cắt về phía 0 theo ngữ nghĩa chia nguyên.

### 2.1. Vì sao COUNT và SUM dễ dẫn tới lỗi này?

`COUNT(*)` trả `bigint`. `SUM(integer)` cũng thường trả `bigint`. Vì thế:

~~~sql
SELECT
    COUNT(*) FILTER (WHERE status = 'success')
    / COUNT(*) AS success_rate
FROM some_events;
~~~

nếu bảng `some_events` tồn tại, biểu thức đang chia hai số nguyên; tỷ lệ dưới 100% có thể bị cắt thành 0.

Cách đúng:

~~~sql
SELECT
    COUNT(*) FILTER (WHERE status = 'success')::numeric
    / NULLIF(COUNT(*), 0) AS success_rate
FROM some_events;
~~~

Dùng `::numeric` ở **tử số trước phép chia**, không phải chỉ ép kiểu kết quả sau khi phép chia nguyên đã xảy ra.

### 2.2. CAST sau phép chia là quá muộn

Sai về mục tiêu giữ phần thập phân:

~~~sql
SELECT (1 / 2)::numeric AS wrong_rate;
~~~

Kết quả vẫn là 0, vì phép chia nguyên đã diễn ra trước.

Đúng:

~~~sql
SELECT
    1::numeric / 2 AS correct_rate,
    CAST(1 AS numeric) / 2 AS also_correct;
~~~

Có thể dùng một hằng số thập phân:

~~~sql
SELECT 100.0 * 1 / 2 AS percentage;
~~~

Trong PostgreSQL, `100.0` là literal kiểu số có phần thập phân, giúp phép tính theo ngữ nghĩa `numeric` thay vì chia nguyên thuần túy.

### 2.3. Phần trăm là tỷ lệ nhân 100

Nếu tỷ lệ là 0.125:

~~~sql
SELECT
    25::numeric / 200 AS ratio,
    100.0 * 25 / 200 AS percentage;
~~~

Kết quả là tỷ lệ `0.125` và phần trăm `12.5`.

**Không vừa nhân 100 ở SQL vừa nhân 100 lần nữa ở giao diện.** Cần thống nhất hợp đồng API đang trả `ratio = 0.125` hay `percentage = 12.5`.

## 3. Chia cho không: quy tắc toán học và hành vi SQL

Tỷ lệ \(a/b\) không được xác định khi \(b=0\). PostgreSQL không tự chọn một giá trị “hợp lý về nghiệp vụ” cho trường hợp đó.

~~~sql
-- Ví dụ cố ý gây lỗi; không cần chạy trong quy trình lab:
-- SELECT 10 / 0;
~~~

PostgreSQL sẽ báo lỗi **division by zero**, thường với SQLSTATE `22012`.

### 3.1. Phân biệt ba tình huống

| Tử số | Mẫu số | Ý nghĩa |
|---:|---:|---|
| 0 | 10 | Tỷ lệ bằng 0 |
| 5 | 10 | Tỷ lệ bằng 0,5 |
| 0 | 0 | Tỷ lệ không xác định |
| 5 | 0 | Tỷ lệ không xác định |

**Không thể mặc định 0/0 = 0.** Chẳng hạn chiến dịch không có lượt truy cập và không có đăng ký: tỷ lệ chuyển đổi chưa có mẫu để tính, khác với chiến dịch có 100 lượt truy cập nhưng không có đăng ký (0%).

### 3.2. NULL không phải số 0

Trong SQL, `NULL` thường biểu thị giá trị không có hoặc chưa biết. Nếu mẫu số là NULL, phép chia cũng trả NULL:

~~~sql
SELECT
    5::numeric / NULL::numeric AS unknown_rate;
~~~

Điều này khác trường hợp mẫu số thật sự bằng 0, nhưng `NULLIF</BT> có thể chuyển mẫu số 0 thành NULL để tránh phép chia không hợp lệ.

## 4. NULLIF: cách viết an toàn cho mẫu số

Cú pháp:

~~~sql
NULLIF(expression_1, expression_2)
~~~

`NULLIF(a,b)` trả `NULL` nếu hai biểu thức bằng nhau; nếu không, trả giá trị của biểu thức đầu.

Ví dụ:

~~~sql
SELECT
    NULLIF(10, 0) AS ten,
    NULLIF(0, 0) AS null_instead_of_zero;
~~~

Kết quả: giá trị đầu là 10, giá trị sau là NULL.

### 4.1. Mẫu an toàn thông dụng

~~~sql
SELECT
    25::numeric / NULLIF(150, 0) AS rate;
~~~

Khi mẫu số bằng 0, mẫu số trở thành NULL và toàn bộ phép chia trả NULL thay vì gây lỗi.

Công thức SQL tổng quát:

~~~sql
numerator::numeric / NULLIF(denominator, 0)
~~~

Hoặc biểu thị phần trăm:

~~~sql
100.0 * numerator / NULLIF(denominator, 0)
~~~

Các tên `numerator</BT> và `denominator</BT> ở hai mẫu là **placeholder khái niệm**; chỉ chạy nếu bảng/truy vấn thực có cột tương ứng.

### 4.2. NULLIF không tự làm tỷ lệ thành 0

~~~sql
SELECT
    0::numeric / NULLIF(0, 0) AS undefined_rate;
~~~

Kết quả là NULL. Đây thường là lựa chọn tốt khi báo cáo cần phân biệt **không có dữ liệu để tính** với **tỷ lệ bằng 0**.

### 4.3. NULLIF chỉ bảo vệ mẫu số tương ứng

Nếu một phép tính có nhiều bước chia, cần xem từng mẫu số. Ví dụ:

~~~sql
SELECT
    (10::numeric / NULLIF(0, 0))
    / NULLIF(2, 0) AS result;
~~~

Kết quả là NULL vì mẫu số đầu bằng 0.

`NULLIF</BT> không tự ngăn lỗi tràn số trong phép nhân ở tử số hoặc lỗi ép kiểu ở những biểu thức khác. Cần đặt đúng kiểu dữ liệu trước khi tính toán.

## 5. CASE: khi mẫu số 0 cần quyết định nghiệp vụ

Dùng `CASE` khi muốn quy tắc rõ:

~~~sql
SELECT
    CASE
        WHEN 0 = 0 THEN NULL
        ELSE 5::numeric / 0
    END AS rate;
~~~

Trong thực hành, nên dùng biểu thức không tạo phép chia hằng số cho 0:

~~~sql
WITH metric AS (
    SELECT 5::numeric AS numerator, 0::numeric AS denominator
)
SELECT
    CASE
        WHEN denominator = 0 THEN NULL
        ELSE numerator / NULLIF(denominator, 0)
    END AS rate
FROM metric;
~~~

Lưu ý PostgreSQL có thể đánh giá một số **biểu thức hằng** ở giai đoạn lập kế hoạch, nên đừng dựa vào `CASE WHEN FALSE THEN 1/0 ...` như cách bảo đảm không lỗi trong mọi hoàn cảnh. `NULLIF</BT> là mẫu rõ và gọn hơn cho phép chia.

### 5.1. Ba chính sách khi không có mẫu số

| Chính sách | Kết quả khi mẫu số 0 | Khi nào cân nhắc |
|---|---|---|
| Trả NULL | “Không tính được / chưa đủ dữ liệu” | Tỷ lệ chuyển đổi, hiệu suất mẫu rỗng |
| Trả 0 | Hiển thị 0 theo hợp đồng riêng | Một số dashboard đã quy ước rõ |
| Không trả hàng | Loại nhóm khỏi báo cáo | Báo cáo chỉ liệt kê nhóm có hoạt động |

Không có một chính sách đúng cho mọi KPI. **Phải xác định ý nghĩa trước khi dùng COALESCE.**

### 5.2. Trả trạng thái cùng với tỷ lệ

Thay vì chỉ trả một con số, có thể cung cấp:

~~~sql
WITH metric AS (
    SELECT 0::numeric AS successes, 0::numeric AS attempts
)
SELECT
    CASE
        WHEN attempts = 0 THEN 'NO_SAMPLE'
        ELSE 'COMPUTED'
    END AS rate_status,
    successes / NULLIF(attempts, 0) AS rate
FROM metric;
~~~

Khi không có lượt thử, `rate_status = 'NO_SAMPLE'` và `rate = NULL`. Client có thể hiển thị “Chưa đủ dữ liệu” thay vì “0%”.

## 6. COALESCE: hữu ích nhưng dễ che mất dữ liệu thiếu

`COALESCE(a,b)` trả biểu thức đầu tiên không NULL.

~~~sql
SELECT
    COALESCE(NULL::numeric, 0) AS replaced_null;
~~~

Một cách viết thường thấy:

~~~sql
COALESCE(numerator::numeric / NULLIF(denominator, 0), 0)
~~~

Nó biến mọi kết quả NULL thành 0, bao gồm trường hợp mẫu số 0 và trường hợp dữ liệu bị thiếu ở tử số.

### 6.1. Khi nào 0 có ý nghĩa?

Ví dụ dashboard liệt kê số đơn mỗi ngày: không có bản ghi giao dịch trong một ngày đã đối soát đầy đủ có thể được hiển thị là **0 đơn**. Khi đó `COALESCE(COUNT...)</BT> thường không cần nếu COUNT trả 0, còn `COALESCE(SUM(...),0)` có thể hợp lý.

Nhưng với tỷ lệ chuyển đổi ngày không có lượt truy cập, **0%** có thể khiến người xem hiểu nhầm “có lượt truy cập nhưng không ai đăng ký”.

### 6.2. Cách tốt: giữ một cột có ý nghĩa NULL

~~~sql
SELECT
    numerator::numeric / NULLIF(denominator, 0)
        AS rate_or_null,
    COALESCE(
        numerator::numeric / NULLIF(denominator, 0),
        0::numeric
    ) AS display_zero_if_undefined
FROM metrics;
~~~

Đây là ví dụ cấu trúc, cần bảng `metrics</BT> nếu chạy nguyên văn. Khi triển khai thật, chỉ nên dùng cách trả 0 nếu hợp đồng báo cáo chấp nhận.

## 7. Aggregate và NULL trong PostgreSQL

Trước khi tính tỷ lệ tổng hợp, cần hiểu `COUNT</BT>, `SUM</BT> và `AVG</BT> xử lý NULL ra sao.

### 7.1. COUNT(*) khác COUNT(column)

~~~sql
SELECT
    COUNT(*) AS total_rows,
    COUNT(value) AS nonnull_values
FROM (
    VALUES (1), (NULL), (3)
) AS t(value);
~~~

Kết quả:

| total_rows | nonnull_values |
|---:|---:|
| 3 | 2 |

`COUNT(*)` đếm mọi hàng. `COUNT(column)` chỉ đếm những hàng mà biểu thức không NULL.

### 7.2. AVG bỏ qua NULL

~~~sql
SELECT AVG(value) AS avg_nonnull
FROM (
    VALUES (10::numeric), (NULL::numeric), (20::numeric)
) AS t(value);
~~~

Kết quả là 15, không phải 10. Mẫu số của `AVG(value)` là **số giá trị không NULL**.

### 7.3. SUM trên tập rỗng trả NULL

~~~sql
SELECT
    COUNT(*) AS rows_count,
    SUM(x) AS sum_value,
    AVG(x) AS avg_value
FROM (
    SELECT 1::numeric AS x
    WHERE FALSE
) AS t;
~~~

Kết quả gồm một hàng:

| rows_count | sum_value | avg_value |
|---:|---|---|
| 0 | NULL | NULL |

Khác biệt này quan trọng khi bảng tổng hợp chưa có dữ liệu: `COUNT(*)` trả 0 còn `SUM</BT>/`AVG</BT> thường trả NULL nếu không có đầu vào hợp lệ.

### 7.4. SUM của toàn NULL cũng NULL

~~~sql
SELECT
    COUNT(*) AS total_rows,
    COUNT(x) AS known_values,
    SUM(x) AS sum_value
FROM (VALUES (NULL::numeric), (NULL::numeric)) AS t(x);
~~~

Có hai hàng nhưng không có số nào để cộng, nên `SUM(x)</BT> là NULL. Không nên coi đây là tổng thật sự bằng 0 trừ khi nghiệp vụ quy định rõ.

## 8. Lab: dữ liệu chiến dịch để tính tỷ lệ

Từ đây, ta dùng một bộ dữ liệu nhỏ, có chủ đích tạo cả nhóm **mẫu số dương**, **mẫu số bằng 0** và **nhóm không có hàng dữ liệu**.

Chạy các lệnh trong **database PostgreSQL thử nghiệm** có quyền tạo schema. Không chạy trên production. Nếu schema `ratio_lab` đã tồn tại, dùng database hoặc tên schema khác; không xóa dữ liệu thật chỉ để làm lại ví dụ.

### 8.1. Tạo schema và danh sách chiến dịch

~~~sql
CREATE SCHEMA ratio_lab;

CREATE TABLE ratio_lab.campaigns (
    campaign_id INTEGER PRIMARY KEY,
    campaign_name TEXT NOT NULL UNIQUE
);

INSERT INTO ratio_lab.campaigns (campaign_id, campaign_name)
VALUES
    (1, 'Alpha'),
    (2, 'Beta'),
    (3, 'Gamma'),
    (4, 'Delta');
~~~

### 8.2. Tạo bảng số liệu theo ngày

~~~sql
CREATE TABLE ratio_lab.campaign_daily (
    campaign_id INTEGER NOT NULL
        REFERENCES ratio_lab.campaigns(campaign_id),
    metric_day DATE NOT NULL,
    visitors INTEGER NOT NULL CHECK (visitors >= 0),
    signups INTEGER NOT NULL CHECK (signups >= 0),
    revenue NUMERIC(14, 2) NOT NULL CHECK (revenue >= 0),
    spend NUMERIC(14, 2) NOT NULL CHECK (spend >= 0),

    CONSTRAINT pk_campaign_daily
        PRIMARY KEY (campaign_id, metric_day),

    CONSTRAINT chk_signups_within_visitors
        CHECK (signups <= visitors)
);
~~~

Mỗi hàng có ý nghĩa **một chiến dịch, một ngày**. `signups <= visitors` chỉ hợp lý khi signups và visitors đã được đo theo **cùng định nghĩa lượt/người**. Trong sản phẩm thật, có thể có nhiều signup trên cùng một người hoặc visitor không được định danh; phải xác nhận định nghĩa trước khi đặt constraint.

### 8.3. Thêm dữ liệu có chủ đích

~~~sql
INSERT INTO ratio_lab.campaign_daily (
    campaign_id,
    metric_day,
    visitors,
    signups,
    revenue,
    spend
)
VALUES
    (1, DATE '2026-11-10', 100, 20, 1200000.00, 400000.00),
    (1, DATE '2026-11-11',  50,  5,  300000.00, 200000.00),
    (2, DATE '2026-11-10',   0,  0,       0.00,      0.00),
    (2, DATE '2026-11-11',  20,  4,  160000.00,  80000.00),
    (3, DATE '2026-11-10',   0,  0,       0.00,      0.00);
~~~

Tình huống:

| Campaign | Ngày | Visitors | Signups | Revenue | Spend |
|---|---|---:|---:|---:|---:|
| Alpha | 10/11 | 100 | 20 | 1.200.000 | 400.000 |
| Alpha | 11/11 | 50 | 5 | 300.000 | 200.000 |
| Beta | 10/11 | 0 | 0 | 0 | 0 |
| Beta | 11/11 | 20 | 4 | 160.000 | 80.000 |
| Gamma | 10/11 | 0 | 0 | 0 | 0 |
| Delta | Không có hàng | — | — | — | — |

Dữ liệu này cho phép phân biệt:

- Alpha: tổng 25 đăng ký trên 150 lượt truy cập.
- Beta: một ngày không có lượt truy cập, một ngày có 4/20.
- Gamma: có bản ghi ngày nhưng mẫu số là 0.
- Delta: có chiến dịch trong danh mục nhưng **chưa có bản ghi số liệu ngày**.

## 9. Tính tỷ lệ từng ngày bằng NULLIF

~~~sql
SELECT
    campaign_id,
    metric_day,
    visitors,
    signups,
    ROUND(
        100.0 * signups / NULLIF(visitors, 0),
        2
    ) AS signup_rate_pct
FROM ratio_lab.campaign_daily
ORDER BY campaign_id, metric_day;
~~~

Dự kiến:

| Campaign ID | Ngày | Visitors | Signups | signup_rate_pct |
|---:|---|---:|---:|---:|
| 1 | 10/11 | 100 | 20 | 20.00 |
| 1 | 11/11 | 50 | 5 | 10.00 |
| 2 | 10/11 | 0 | 0 | NULL |
| 2 | 11/11 | 20 | 4 | 20.00 |
| 3 | 10/11 | 0 | 0 | NULL |

Chỉ số trả NULL cho ngày không có visitor; nó không gây phép chia cho 0.

### 9.1. Vì sao chưa tính trung bình ngày để ra tỷ lệ cả chiến dịch?

Ngày 10/11 của Alpha có 100 visitors, còn ngày 11/11 có 50 visitors. Nếu lấy trung bình 20% và 10%, ta được 15%. Nhưng xét cả hai ngày, Alpha có **25 đăng ký / 150 visitors ≈ 16,67%**.

Sự khác nhau xuất phát từ **mẫu số mỗi ngày không bằng nhau**.

### 9.2. Một ngày không có visitors không đồng nghĩa có tỷ lệ 0

Beta ngày 10/11: `0/0` là tỷ lệ không xác định. Nếu trước khi tổng hợp thay NULL bằng 0 rồi `AVG</BT> trên hai ngày, ta sẽ tính ra sai 10% thay vì tỷ lệ 20% trên tập thực có visitors.

## 10. Tổng hợp đúng tỷ lệ theo chiến dịch

Công thức đúng cho tỷ lệ chuyển đổi của toàn bộ tập quan sát:

\[
\text{Conversion rate} =
\frac{\sum \text{signups}}{\sum \text{visitors}}
\]

Trong PostgreSQL:

~~~sql
SELECT
    campaign_id,
    SUM(visitors) AS total_visitors,
    SUM(signups) AS total_signups,
    ROUND(
        100.0 * SUM(signups)
        / NULLIF(SUM(visitors), 0),
        2
    ) AS signup_rate_pct
FROM ratio_lab.campaign_daily
GROUP BY campaign_id
ORDER BY campaign_id;
~~~

Kết quả dự kiến:

| campaign_id | total_visitors | total_signups | signup_rate_pct |
|---:|---:|---:|---:|
| 1 | 150 | 25 | 16.67 |
| 2 | 20 | 4 | 20.00 |
| 3 | 0 | 0 | NULL |

Delta chưa xuất hiện vì nó không có bản ghi trong `campaign_daily`. Ta sẽ xử lý tình huống này bằng `LEFT JOIN` ở phần sau.

### 10.1. Đừng dùng AVG của các tỷ lệ ngày khi muốn tỷ lệ toàn kỳ

Một câu tính trung bình đơn giản:

~~~sql
SELECT
    campaign_id,
    ROUND(
        AVG(
            100.0 * signups / NULLIF(visitors, 0)
        ),
        2
    ) AS average_daily_rate_pct
FROM ratio_lab.campaign_daily
GROUP BY campaign_id
ORDER BY campaign_id;
~~~

Cho Alpha kết quả **15.00**, còn tỷ lệ cả kỳ là **16.67**.

Không phải câu trên luôn “sai”: nó trả **trung bình cộng của tỷ lệ theo những ngày đủ mẫu số**, đúng nếu câu hỏi thực là “ngày điển hình có tỷ lệ bao nhiêu, mỗi ngày có trọng số như nhau?”. Nhưng nó **không phải** tỷ lệ trên tổng lượt truy cập.

### 10.2. Công thức tổng hợp hai nhóm

Nếu nhóm A có 10/100, nhóm B có 5/50:

\[
\frac{10+5}{100+50}=\frac{15}{150}=10\%
\]

Nếu nhóm A có 20/100, nhóm B có 5/50:

\[
\frac{20+5}{100+50}=\frac{25}{150}\approx16{,}67\%
\]

Đó là lý do khi thiết kế dashboard tổng hợp nhiều kỳ, cần lưu hoặc truyền **tử số và mẫu số**, không chỉ lưu tỷ lệ đã làm tròn.

## 11. Mối liên hệ giữa tỷ lệ toàn kỳ và trung bình có trọng số

Giả sử mỗi ngày \(i\) có:

\[
r_i = \frac{a_i}{b_i}
\]

Khi \(b_i > 0\), tỷ lệ tổng thể là:

\[
R=\frac{\sum_i a_i}{\sum_i b_i}
=\frac{\sum_i b_i r_i}{\sum_i b_i}
\]

Nghĩa là **tỷ lệ trên tổng** chính là **trung bình có trọng số của các tỷ lệ con**, với **trọng số bằng mẫu số tương ứng**, nếu các nhóm hợp lệ và quy tắc dữ liệu nhất quán.

Với Alpha:

| Ngày | Tỷ lệ | Trọng số visitors |
|---|---:|---:|
| 10/11 | 20% | 100 |
| 11/11 | 10% | 50 |

\[
R = \frac{100\times20\%+50\times10\%}{100+50}
=\frac{25}{150}\approx16{,}67\%
\]

### 11.1. Viết theo tỷ lệ con để minh họa

~~~sql
SELECT
    campaign_id,
    ROUND(
        100.0 *
        SUM(
            visitors * (signups::numeric / NULLIF(visitors, 0))
        )
        / NULLIF(SUM(visitors), 0),
        2
    ) AS weighted_rate_pct
FROM ratio_lab.campaign_daily
GROUP BY campaign_id
ORDER BY campaign_id;
~~~

Câu trên có thể cho kết quả phù hợp với tỷ lệ trên tổng đối với dữ liệu lab. Tuy nhiên, **không nên chọn cách dài và dễ gặp NULL này để tính KPI thật** nếu đã có tổng tử số và tổng mẫu số.

Cách đơn giản, dễ kiểm chứng hơn:

~~~sql
SUM(signups)::numeric / NULLIF(SUM(visitors), 0)
~~~

### 11.2. Vì sao phép tính phức tạp có thể gây lệch khi dữ liệu thiếu?

Nếu một ngày có `visitors=0` và một số đo khác không tuân thủ tính cùng tập, biểu thức `visitors * (signups / NULLIF(visitors,0))` trả NULL cho ngày đó. `SUM</BT> bỏ qua NULL, trong khi cách tính tổng có thể cộng những hàng khác vào tử/mẫu.

Do vậy, trước khi chuyển từ “tỷ lệ của tổng” sang “trung bình có trọng số”, cần đảm bảo mỗi tỷ lệ con có ý nghĩa, các mẫu số hợp lệ và tập quan sát trùng nhau.

## 12. Định nghĩa đúng tử số và mẫu số

Trước khi viết SQL, hãy xác định **đơn vị đo** và **phạm vi**.

Ví dụ:

| KPI | Tử số | Mẫu số |
|---|---|---|
| Tỷ lệ đăng ký | Số người/lượt đăng ký hợp lệ | Số người/lượt truy cập đủ điều kiện |
| Tỷ lệ đơn giao thành công | Số đơn đã giao | Số đơn đã được giao cho vận chuyển hoặc tập đơn theo định nghĩa |
| Tỷ lệ lỗi API | Số request lỗi theo định nghĩa | Tổng request được xử lý |
| Tỷ lệ click | Số click hợp lệ | Số impression hợp lệ |
| Tỷ trọng doanh thu nhóm | Doanh thu nhóm | Tổng doanh thu toàn tập |
| ROAS | Doanh thu quy thuộc quảng cáo | Chi phí quảng cáo |
| Giá bán bình quân theo lượng | Tổng doanh thu các dòng bán | Tổng đơn vị bán |

### 12.1. Không trộn “người” và “sự kiện”

Giả sử một người truy cập trang 5 lần và đăng ký một lần:

- Event-level conversion: 1 đăng ký / 5 visits = 20%.
- User-level conversion: 1 người đăng ký / 1 unique visitor = 100%.

Cả hai có thể hợp lệ nhưng **đo hai khái niệm khác nhau**. Nếu báo cáo nói “tỷ lệ người dùng đăng ký”, mẫu số thường phải là số người dùng duy nhất trong tập phù hợp, không phải số page views.

### 12.2. Tử số phải là tập con phù hợp của mẫu số

Với một tỷ lệ xác suất/chuyển đổi 0–100%, cần kiểm tra điều kiện:

\[
0 \le a \le b
\]

Nếu tử số lớn hơn mẫu số, đó có thể là lỗi dữ liệu, hoặc là dấu hiệu bạn đang đo hai đơn vị khác nhau. Không tự dùng `LEAST(ratio,1)` để ép tỷ lệ xuống 100% trước khi hiểu nguyên nhân.

### 12.3. Không phải mọi ratio đều bị giới hạn 100%

ROAS có thể là 2.5 nghĩa là doanh thu gấp 2,5 lần chi phí. Tỷ số đơn vị bán trên khách cũng có thể lớn hơn 1. Chỉ những KPI được định nghĩa là tỷ lệ của một **tập con so với tập toàn phần** mới nên mặc định giới hạn 0–1.

## 13. Trung bình có trọng số: công thức tổng quát

Với giá trị \(x_i\) và trọng số \(w_i\):

\[
\bar{x}_w=\frac{\sum_i x_i w_i}{\sum_i w_i}
\]

Điều kiện thông thường để có trung bình có ý nghĩa:

- Mỗi trọng số phản ánh cùng một đại lượng như số lượng, thời gian hoặc mức độ đóng góp.
- Trọng số được định nghĩa nhất quán.
- Với trọng số thông thường, `w_i \ge 0`.
- Tổng trọng số **lớn hơn 0**.
- Các hàng thiếu giá trị/trọng số được xử lý nhất quán ở cả tử số và mẫu số.

SQL mẫu:

~~~sql
SELECT
    SUM(value * weight)
    / NULLIF(SUM(weight), 0) AS weighted_average
FROM measurements;
~~~

Đây là ví dụ cấu trúc; cần bảng hoặc CTE `measurements` có hai cột nếu chạy nguyên văn.

### 13.1. Tại sao không dùng AVG(value * weight)?

`AVG(value * weight)` chia tổng tích cho **số hàng hợp lệ**, không chia tổng trọng số. Ví dụ trọng số lần lượt 2, 1, 7 thì số hàng là 3 nhưng tổng trọng số là 10. Hai phép tính khác nhau.

### 13.2. Tại sao không dùng AVG(value) khi các trọng số khác nhau?

`AVG(value)` mặc định mỗi hàng có cùng trọng số. Nếu một hàng đại diện cho 10.000 lượt truy cập còn hàng khác đại diện cho 5 lượt, cách tính bình quân đơn giản rất dễ cho kết quả không phản ánh tập dữ liệu tổng.

## 14. Lab: giá bán bình quân theo số lượng

Tạo bảng dòng hàng đã bán:

~~~sql
CREATE TABLE ratio_lab.sales_lines (
    sale_line_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    category TEXT NOT NULL,
    product_id INTEGER NOT NULL,
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    unit_price NUMERIC(12, 2) NOT NULL
        CHECK (unit_price >= 0),
    sold_at TIMESTAMPTZ NOT NULL
);

INSERT INTO ratio_lab.sales_lines (
    category, product_id, quantity, unit_price, sold_at
)
VALUES
    ('Book', 101, 2, 100000.00, TIMESTAMPTZ '2026-11-10 09:00:00+07'),
    ('Book', 102, 1, 160000.00, TIMESTAMPTZ '2026-11-10 10:00:00+07'),
    ('Book', 103, 7,  50000.00, TIMESTAMPTZ '2026-11-11 14:00:00+07'),
    ('Toy',  201, 4,  25000.00, TIMESTAMPTZ '2026-11-11 15:00:00+07');
~~~

### 14.1. Trung bình đơn giá mỗi dòng hàng

~~~sql
SELECT
    category,
    ROUND(AVG(unit_price), 2) AS simple_avg_price
FROM ratio_lab.sales_lines
GROUP BY category
ORDER BY category;
~~~

Đối với Book: `(100000+160000+50000)/3 = 103333.33`.

Đây là bình quân **mỗi dòng**, không phải bình quân mỗi đơn vị đã bán.

### 14.2. Trung bình có trọng số quantity

~~~sql
SELECT
    category,
    SUM(quantity) AS total_units,
    SUM(quantity * unit_price) AS total_revenue,
    ROUND(
        SUM(quantity * unit_price)
        / NULLIF(SUM(quantity), 0),
        2
    ) AS weighted_avg_unit_price
FROM ratio_lab.sales_lines
GROUP BY category
ORDER BY category;
~~~

Kết quả dự kiến:

| category | total_units | total_revenue | weighted_avg_unit_price |
|---|---:|---:|---:|
| Book | 10 | 710.000 | 71.000.00 |
| Toy | 4 | 100.000 | 25.000.00 |

Phép tính cho Book:

~~~text
2 × 100.000 = 200.000
1 × 160.000 = 160.000
7 ×  50.000 = 350.000

Tổng doanh thu = 710.000
Tổng lượng bán = 10
Giá bình quân theo lượng = 71.000
~~~

### 14.3. Vì sao quantity * unit_price có kiểu đủ chính xác?

Trong lab, `unit_price` là `numeric(12,2)`, nên phép nhân với số lượng có ngữ nghĩa số thập phân chính xác của `numeric` thay vì số thực dấu phẩy động.

Nếu hai toán hạng đều là integer và có thể rất lớn, phép nhân có thể **tràn kiểu trước khi tổng hợp**. Khi cần, hãy ép kiểu trước phép nhân:

~~~sql
SELECT
    SUM(quantity::numeric * unit_price) AS precise_amount
FROM ratio_lab.sales_lines;
~~~

Trong bài lab đơn giá đã là numeric, nhưng mẫu ép kiểu là thói quen hữu ích khi dữ liệu đo bằng integer lớn.

### 14.4. Giá bình quân không thay thế tổng doanh thu

`weighted_avg_unit_price</BT> là chỉ số mô tả. Nó không nên được làm tròn rồi nhân lại để hạch toán từng đơn hoặc đối soát tiền nếu hệ thống đang có giá và số lượng gốc chính xác.

## 15. Khi trọng số bằng 0

Nếu tất cả trọng số đều bằng 0, mẫu số của trung bình có trọng số là 0. Ví dụ:

~~~sql
WITH measurements(value, weight) AS (
    VALUES
        (10::numeric, 0::numeric),
        (20::numeric, 0::numeric)
)
SELECT
    SUM(value * weight) AS weighted_sum,
    SUM(weight) AS total_weight,
    SUM(value * weight)
        / NULLIF(SUM(weight), 0) AS weighted_avg
FROM measurements;
~~~

Kết quả:

| weighted_sum | total_weight | weighted_avg |
|---:|---:|---|
| 0 | 0 | NULL |

**Không có trọng lượng quan sát để định nghĩa trung bình.** Giá trị trung bình không phải tự động bằng 0.

### 15.1. Một vài trọng số 0 vẫn có thể hợp lệ

~~~sql
WITH measurements(value, weight) AS (
    VALUES
        (10::numeric, 2::numeric),
        (99::numeric, 0::numeric),
        (20::numeric, 3::numeric)
)
SELECT
    SUM(value * weight)
    / NULLIF(SUM(weight), 0) AS weighted_avg
FROM measurements;
~~~

Tử số `10×2 + 99×0 + 20×3 = 80`, mẫu số `2+0+3=5`, kết quả `16`. Hàng trọng số 0 không ảnh hưởng kết quả.

### 15.2. Trọng số âm cần được quyết định rõ

Trong nhiều bài toán trung bình có trọng số, trọng số phải không âm. Nếu cho trọng số âm mà tổng trọng số gần 0, kết quả có thể rất lớn hoặc nằm ngoài khoảng nhỏ nhất–lớn nhất của giá trị.

Với dữ liệu bán hàng, trả hàng hoặc hoàn tiền có thể được biểu diễn bằng quantity âm ở một số thiết kế, nhưng khi đó phép tính `SUM(quantity * price)/SUM(quantity)` có semantics **net sales** chứ không đơn thuần là giá trung bình của các đơn vị bán ra.

**Đừng xóa dấu âm hoặc dùng ABS(weight) trước khi xác định quy tắc nghiệp vụ.**

## 16. NULL ở giá trị và trọng số: bẫy mẫu số không tương thích

Một lỗi tinh vi: tử số và mẫu số tổng hợp **khác tập hàng** do NULL.

~~~sql
WITH measurements(value, weight) AS (
    VALUES
        (10::numeric, 2::numeric),
        (20::numeric, NULL::numeric),
        (NULL::numeric, 5::numeric)
)
SELECT
    SUM(value * weight) AS weighted_sum,
    SUM(weight) AS total_weight,
    SUM(value * weight)
        / NULLIF(SUM(weight), 0) AS naive_weighted_avg
FROM measurements;
~~~

Tử số:

- Hàng `(10,2)` đóng góp 20.
- Hàng `(20,NULL)` tạo tích NULL, bị SUM bỏ qua.
- Hàng `(NULL,5)` tạo tích NULL, bị SUM bỏ qua.

Mẫu số `SUM(weight)` lại cộng cả trọng số 5 của hàng thiếu value, cho tổng 7. Kết quả “20/7” **không phải** trung bình của các cặp quan sát đầy đủ.

### 16.1. Lọc cùng tập cặp hợp lệ

~~~sql
WITH measurements(value, weight) AS (
    VALUES
        (10::numeric, 2::numeric),
        (20::numeric, NULL::numeric),
        (NULL::numeric, 5::numeric)
)
SELECT
    SUM(value * weight)
        / NULLIF(SUM(weight), 0) AS weighted_avg
FROM measurements
WHERE value IS NOT NULL
  AND weight IS NOT NULL
  AND weight > 0;
~~~

Chỉ hàng `(10,2)` được dùng, nên trung bình là 10.

### 16.2. Dùng FILTER khi cần nhiều chỉ số cùng lúc

~~~sql
WITH measurements(value, weight) AS (
    VALUES
        (10::numeric, 2::numeric),
        (20::numeric, NULL::numeric),
        (NULL::numeric, 5::numeric)
)
SELECT
    COUNT(*) AS all_rows,
    COUNT(*) FILTER (
        WHERE value IS NOT NULL
          AND weight IS NOT NULL
          AND weight > 0
    ) AS valid_pairs,
    SUM(value * weight) FILTER (
        WHERE value IS NOT NULL
          AND weight IS NOT NULL
          AND weight > 0
    )
    /
    NULLIF(
        SUM(weight) FILTER (
            WHERE value IS NOT NULL
              AND weight IS NOT NULL
              AND weight > 0
        ),
        0
    ) AS weighted_avg
FROM measurements;
~~~

Trong báo cáo lớn, có thể đặt tập cặp hợp lệ trong CTE để tránh lặp lại điều kiện và giúp tên ý nghĩa hơn.

### 16.3. Đừng tự coi NULL là 0 trong mọi bài toán

`COALESCE(value,0)` nghĩa là biến “không biết giá trị” thành “giá trị bằng 0”. Điều đó có thể sai về phân tích số liệu.

Với dữ liệu thực, cần phân loại nguồn NULL:

- Không áp dụng cho hàng này.
- Chưa có số đo.
- Mất dữ liệu khi nhập.
- Cố ý không thu thập.
- Giá trị thật sự bằng 0 nhưng được ghi NULL.

Chỉ sau khi thống nhất ý nghĩa mới quyết định lọc, tính 0 hoặc trả kết quả thiếu.

## 17. FILTER: tính nhiều tỷ lệ có điều kiện trong một lần GROUP BY

PostgreSQL hỗ trợ cú pháp:

~~~sql
aggregate(expression) FILTER (WHERE condition)
~~~

Nó cho phép **mỗi aggregate có tập hàng riêng** trong cùng truy vấn.

Ví dụ từ dữ liệu chiến dịch:

~~~sql
SELECT
    campaign_id,
    SUM(visitors) AS total_visitors,
    SUM(signups) AS total_signups,
    SUM(visitors) FILTER (
        WHERE metric_day = DATE '2026-11-10'
    ) AS visitors_on_day_10,
    SUM(visitors) FILTER (
        WHERE metric_day = DATE '2026-11-11'
    ) AS visitors_on_day_11
FROM ratio_lab.campaign_daily
GROUP BY campaign_id
ORDER BY campaign_id;
~~~

Với chiến dịch không có hàng thỏa FILTER ở một ngày, `SUM(...)</BT> của tập lọc rỗng trả NULL, không tự trả 0.

### 17.1. COUNT(*) FILTER cho tỷ lệ theo trạng thái

~~~sql
WITH events(event_id, outcome) AS (
    VALUES
        (1, 'success'),
        (2, 'failure'),
        (3, 'success'),
        (4, 'success')
)
SELECT
    COUNT(*) AS total_events,
    COUNT(*) FILTER (
        WHERE outcome = 'success'
    ) AS success_events,
    ROUND(
        100.0 * COUNT(*) FILTER (
            WHERE outcome = 'success'
        ) / NULLIF(COUNT(*), 0),
        2
    ) AS success_rate_pct
FROM events;
~~~

Kết quả 3/4 = 75%.

### 17.2. FILTER khác WHERE toàn truy vấn

Nếu đặt:

~~~sql
WHERE outcome = 'success'
~~~

thì `COUNT(*)</BT> chỉ đếm success, không còn đếm tất cả events. Khi cần cả tổng và số success trong một câu, `FILTER` biểu đạt tử và mẫu riêng rõ hơn.

### 17.3. Dấu ngoặc quan trọng

Nên viết đủ:

~~~sql
100.0 *
COUNT(*) FILTER (WHERE outcome = 'success')
/
NULLIF(COUNT(*), 0)
~~~

Đặt trong `ROUND(...,2)` khi dùng kiểu numeric. Không bỏ các dấu ngoặc tạo hàm hoặc ghép FILTER nhầm vào toàn biểu thức.

## 18. CASE và FILTER: hai cách tổng hợp có điều kiện

Một công thức tương đương trong nhiều trường hợp:

~~~sql
COUNT(*) FILTER (WHERE outcome = 'success')
~~~

và:

~~~sql
SUM(CASE WHEN outcome = 'success' THEN 1 ELSE 0 END)
~~~

Nhưng cần hiểu khác biệt về tập rỗng:

- `COUNT(*) FILTER</BT> trả 0 khi không có hàng được đếm.
- `SUM(CASE ... END)</BT> trả NULL nếu **không có hàng đầu vào** cho aggregate.
- `SUM(CASE WHEN ... THEN 1 END)</BT> có thể NULL khi tất cả hàng không khớp vì ELSE mặc định NULL.

### 18.1. Ví dụ

~~~sql
WITH events(outcome) AS (
    VALUES ('failure'), ('failure')
)
SELECT
    COUNT(*) FILTER (
        WHERE outcome = 'success'
    ) AS success_count,
    SUM(
        CASE
            WHEN outcome = 'success' THEN 1
            ELSE 0
        END
    ) AS success_sum
FROM events;
~~~

Cả hai là 0 vì có hai hàng đầu vào và CASE có `ELSE 0`.

### 18.2. Chọn cách nào?

- `FILTER` rõ khi cần nhiều chỉ số tổng hợp có điều kiện.
- `CASE` hữu ích khi logic chọn giá trị phức tạp hoặc cần phân loại.
- Cả hai phải dùng **đúng đơn vị và cùng tập quan sát**.

## 19. LEFT JOIN và nhóm không có dữ liệu

Bảng `ratio_lab.campaigns` có bốn chiến dịch nhưng bảng `campaign_daily` chỉ có dữ liệu cho ba chiến dịch. Muốn hiển thị đủ danh mục, dùng `LEFT JOIN`:

~~~sql
SELECT
    c.campaign_id,
    c.campaign_name,
    COUNT(d.campaign_id) AS days_with_data,
    SUM(d.visitors) AS total_visitors,
    SUM(d.signups) AS total_signups,
    ROUND(
        100.0 * SUM(d.signups)
        / NULLIF(SUM(d.visitors), 0),
        2
    ) AS signup_rate_pct
FROM ratio_lab.campaigns AS c
LEFT JOIN ratio_lab.campaign_daily AS d
    ON d.campaign_id = c.campaign_id
GROUP BY c.campaign_id, c.campaign_name
ORDER BY c.campaign_id;
~~~

Kết quả dự kiến:

| Campaign | days_with_data | Visitors | Signups | Rate |
|---|---:|---:|---:|---:|
| Alpha | 2 | 150 | 25 | 16.67 |
| Beta | 2 | 20 | 4 | 20.00 |
| Gamma | 1 | 0 | 0 | NULL |
| Delta | 0 | NULL | NULL | NULL |

### 19.1. Gamma và Delta khác nhau

- **Gamma:** có số liệu ghi nhận, nhưng visitors=0; tỷ lệ là 0/0 và không xác định.
- **Delta:** không có hàng số liệu ngày; không biết liệu chưa chạy, ETL chưa tới hay chưa được ghi nhận.

Nếu dùng:

~~~sql
COALESCE(SUM(d.visitors), 0)
~~~

Gamma và Delta đều có thể hiển thị visitors 0. Để không mất thông tin, nên giữ thêm `days_with_data` hoặc một cột tình trạng dữ liệu.

### 19.2. COUNT(*) trên LEFT JOIN có bẫy

~~~sql
COUNT(*)
~~~

đếm một hàng kết quả LEFT JOIN ngay cả khi không có hàng thực phía phải. Đối với Delta, `COUNT(*)` có thể là 1.

Muốn đếm bản ghi số liệu thực, dùng cột bắt buộc không NULL ở phía phải:

~~~sql
COUNT(d.campaign_id)
~~~

### 19.3. Không đặt điều kiện phía phải vào WHERE một cách bất cẩn

~~~sql
SELECT c.campaign_name, d.metric_day
FROM ratio_lab.campaigns AS c
LEFT JOIN ratio_lab.campaign_daily AS d
    ON d.campaign_id = c.campaign_id
WHERE d.metric_day >= DATE '2026-11-10';
~~~

Điều kiện `WHERE</BT> loại những hàng không khớp có `d.metric_day IS NULL`, làm biến mất Delta.

Nếu cần giữ mọi chiến dịch trong khoảng thời gian, có thể đặt điều kiện ngày ở `ON`:

~~~sql
SELECT c.campaign_name, d.metric_day
FROM ratio_lab.campaigns AS c
LEFT JOIN ratio_lab.campaign_daily AS d
    ON d.campaign_id = c.campaign_id
   AND d.metric_day >= DATE '2026-11-10';
~~~

Với outer join, điều kiện ở `ON` và `WHERE` không phải luôn hoán đổi được.

## 20. Kết quả “0%”, “NULL” và “không có hàng” không giống nhau

Ba trường hợp này cần hiển thị khác nếu dashboard muốn người dùng ra quyết định đúng:

~~~text
100 attempts, 0 successes -> 0% thực sự
0 attempts, 0 successes   -> NULL / N/A
Không có bản ghi attempts -> NULL / NO_DATA
~~~

Có thể làm rõ bằng SQL:

~~~sql
SELECT
    c.campaign_name,
    COUNT(d.campaign_id) AS row_count,
    SUM(d.visitors) AS visitors,
    SUM(d.signups) AS signups,
    CASE
        WHEN COUNT(d.campaign_id) = 0 THEN 'NO_DATA'
        WHEN SUM(d.visitors) = 0 THEN 'NO_SAMPLE'
        ELSE 'COMPUTED'
    END AS rate_status,
    ROUND(
        100.0 * SUM(d.signups)
        / NULLIF(SUM(d.visitors), 0),
        2
    ) AS signup_rate_pct
FROM ratio_lab.campaigns AS c
LEFT JOIN ratio_lab.campaign_daily AS d
    ON d.campaign_id = c.campaign_id
GROUP BY c.campaign_id, c.campaign_name
ORDER BY c.campaign_id;
~~~

Đối với lab, trạng thái:

- Alpha, Beta: `COMPUTED`.
- Gamma: `NO_SAMPLE`.
- Delta: `NO_DATA`.

Khi ứng dụng cần JSON API, đây thường là thiết kế rõ hơn việc cố gắng biểu thị tất cả bằng một giá trị số.

## 21. ROAS và ROI: cùng phép chia nhưng khác ý nghĩa

Trong marketing:

\[
ROAS = \frac{\text{Revenue attributed to ads}}{\text{Ad spend}}
\]

ROAS là một **hệ số**, không nhất thiết là một phần trăm và có thể lớn hơn 1.

Một chỉ số khác:

\[
ROI = \frac{\text{Return}-\text{Investment}}{\text{Investment}}
\]

Trong thực tế, “return” và “investment” của ROI có thể cần thêm chi phí hàng hóa, vận hành và nhiều thành phần khác. Vì thế đừng nhầm một ví dụ số học với công thức kế toán chuẩn cho mọi doanh nghiệp.

### 21.1. Tính ROAS từ dữ liệu lab

~~~sql
SELECT
    campaign_id,
    SUM(revenue) AS total_revenue,
    SUM(spend) AS total_spend,
    ROUND(
        SUM(revenue) / NULLIF(SUM(spend), 0),
        3
    ) AS roas
FROM ratio_lab.campaign_daily
GROUP BY campaign_id
ORDER BY campaign_id;
~~~

Dự kiến:

| campaign_id | total_revenue | total_spend | roas |
|---:|---:|---:|---:|
| 1 | 1.500.000 | 600.000 | 2.500 |
| 2 | 160.000 | 80.000 | 2.000 |
| 3 | 0 | 0 | NULL |

Gamma có chi phí 0 nên ROAS không xác định theo phép chia này, dù doanh thu cũng bằng 0. Không tự diễn giải 0/0 thành ROAS bằng 0.

### 21.2. Tính “net return ratio” minh họa

~~~sql
SELECT
    campaign_id,
    ROUND(
        (SUM(revenue) - SUM(spend))
        / NULLIF(SUM(spend), 0),
        3
    ) AS illustrative_net_return_ratio
FROM ratio_lab.campaign_daily
GROUP BY campaign_id
ORDER BY campaign_id;
~~~

Đây chỉ là chỉ số minh họa `(revenue - ad_spend)/ad_spend`, **không phải ROI kế toán đầy đủ** nếu còn giá vốn, thuế, phí và chi phí khác.

### 21.3. Không lấy AVG(ROAS ngày) để ra ROAS kỳ

ROAS của ngày đầu Alpha là 1.200.000 / 400.000 = 3.0; ngày sau là 300.000 / 200.000 = 1.5.

Trung bình hai ngày là 2.25, trong khi ROAS toàn kỳ là:

\[
\frac{1500000}{600000}=2{,}5
\]

Cần tổng doanh thu và tổng chi phí đúng kỳ, không trung bình hệ số mà bỏ qua trọng số chi tiêu.

## 22. Tỷ trọng của từng nhóm trong tổng số

Một câu hỏi khác: “Chiến dịch nào đóng góp bao nhiêu phần trăm tổng doanh thu?”

\[
\text{Share}_i=\frac{\text{Revenue}_i}{\sum_j \text{Revenue}_j}
\]

Ta có thể dùng window function:

~~~sql
WITH revenue_by_campaign AS (
    SELECT
        c.campaign_id,
        c.campaign_name,
        COALESCE(SUM(d.revenue), 0::numeric) AS revenue
    FROM ratio_lab.campaigns AS c
    LEFT JOIN ratio_lab.campaign_daily AS d
        ON d.campaign_id = c.campaign_id
    GROUP BY c.campaign_id, c.campaign_name
)
SELECT
    campaign_name,
    revenue,
    ROUND(
        100.0 * revenue
        / NULLIF(SUM(revenue) OVER (), 0),
        2
    ) AS revenue_share_pct
FROM revenue_by_campaign
ORDER BY campaign_id;
~~~

Trong lab, tổng doanh thu là 1.660.000; Alpha chiếm khoảng **90,36%**, Beta **9,64%**, Gamma và Delta **0%**.

### 22.1. Vì sao tính SUM toàn kỳ sau GROUP BY?

CTE tạo **một hàng trên mỗi campaign**. Window `SUM(revenue) OVER ()` cộng những tổng cấp chiến dịch để có mẫu số chung. Không cần self JOIN tất cả nhóm với nhau.

### 22.2. Nếu tổng doanh thu bằng 0

Khi mọi campaign có revenue 0, `NULLIF(SUM(revenue) OVER (),0)` trả NULL, nên tỷ trọng là NULL. Không có tổng doanh thu dương để định nghĩa tỷ phần.

### 22.3. Tỷ trọng khác tốc độ tăng trưởng

Một nhóm có doanh thu 100 và toàn tập 1.000 thì tỷ trọng là 10%. Nếu doanh thu tháng trước là 80 thì tăng trưởng là `(100-80)/80 = 25%`. Hai chỉ số có **mẫu số khác nhau**.

## 23. Tỷ lệ tăng trưởng và mẫu số kỳ trước bằng 0

Tốc độ tăng trưởng thường được định nghĩa:

\[
g=\frac{current-previous}{previous}
\]

Ví dụ:

~~~sql
WITH periods(previous_value, current_value) AS (
    VALUES
        (80::numeric, 100::numeric),
        (0::numeric, 100::numeric),
        (0::numeric, 0::numeric)
)
SELECT
    previous_value,
    current_value,
    ROUND(
        100.0 * (current_value - previous_value)
        / NULLIF(previous_value, 0),
        2
    ) AS growth_pct
FROM periods;
~~~

Kết quả:

| previous | current | growth_pct |
|---:|---:|---:|
| 80 | 100 | 25.00 |
| 0 | 100 | NULL |
| 0 | 0 | NULL |

Không thể diễn đạt một mức tăng từ 0 lên 100 bằng tỷ lệ phần trăm thông thường với mẫu số 0. Một số báo cáo có thể ghi “New”, “From zero” hoặc chỉ số tuyệt đối thay vì phần trăm.

### 23.1. Tăng trưởng âm hợp lệ

Nếu kỳ trước là 100, kỳ này là 80:

~~~sql
SELECT
    100.0 * (80::numeric - 100)
    / NULLIF(100, 0) AS growth_pct;
~~~

Kết quả **-20%**. Giá trị âm không phải lỗi chia, mà có thể phản ánh sự suy giảm thật.

### 23.2. Previous âm cần định nghĩa riêng

Trong kế toán, một chỉ tiêu có thể âm vì lỗ hoặc điều chỉnh. Công thức growth thông thường khi mẫu số âm có thể tạo cách diễn giải không mong muốn. Đừng máy móc áp dụng công thức tăng trưởng mà không xác định semantics cho các giá trị âm và trường hợp đổi dấu.

## 24. Trung bình có trọng số từ nhiều mức tổng hợp

Một lỗi BI phổ biến: có báo cáo ngày với `avg_unit_price` và `units_sold`, rồi muốn gộp cả tháng.

Nếu chỉ có:

~~~text
Day 1: 10 units, avg_price 100
Day 2: 90 units, avg_price  50
~~~

Trung bình cộng của hai giá bình quân ngày là 75, nhưng bình quân cả kỳ là:

\[
\frac{10\times100+90\times50}{10+90}=55
\]

### 24.1. Cần giữ tử số và trọng số khi lưu bảng aggregate

Thay vì chỉ lưu:

~~~text
day, avg_unit_price
~~~

hãy lưu:

~~~text
day, sales_amount, units_sold
~~~

Sau đó tính:

~~~sql
SELECT
    SUM(sales_amount) / NULLIF(SUM(units_sold), 0)
        AS overall_avg_unit_price
FROM daily_product_stats;
~~~

Đây là ví dụ cấu trúc, cần bảng `daily_product_stats` nếu chạy nguyên văn.

### 24.2. Khi nào AVG của các AVG vẫn đúng?

Nếu mọi nhóm có cùng **số lượng quan sát hợp lệ** hoặc cùng trọng số theo đúng định nghĩa, trung bình cộng của các average nhóm có thể bằng overall average. Nhưng không nên mặc định điều kiện đó luôn xảy ra.

### 24.3. Không làm tròn các avg trung gian trước khi gộp

Nếu lưu giá bình quân ngày làm tròn 2 chữ số rồi nhân lại với số lượng, có thể xuất hiện sai số tích lũy. Tốt hơn là lưu tổng giá trị và tổng trọng số chính xác rồi **làm tròn ở bước trình bày cuối**.

## 25. JOIN fanout: tổng hợp có thể sai trước cả phép chia

Giả sử bảng orders có một hàng cho mỗi đơn, bảng order_items có nhiều hàng cho mỗi đơn.

~~~text
orders
  order_id=1, shipping_fee=20

order_items
  (order=1, product=A)
  (order=1, product=B)
  (order=1, product=C)
~~~

Nếu JOIN rồi `SUM(o.shipping_fee)`, phí vận chuyển 20 có thể bị cộng **ba lần** vì order bị lặp theo ba item.

### 25.1. Ví dụ cấu trúc dễ sai

~~~sql
SELECT
    SUM(o.shipping_fee) AS wrong_shipping_sum
FROM orders AS o
JOIN order_items AS i
    ON i.order_id = o.order_id;
~~~

Kết quả của một phép tổng hợp không được đảm bảo đúng chỉ vì có `SUM</BT>.

### 25.2. Giải pháp: tổng hợp đúng mức độ chi tiết

Có thể tổng hợp order items ở cấp order trước rồi JOIN:

~~~sql
WITH item_totals AS (
    SELECT
        order_id,
        SUM(quantity * unit_price) AS item_amount
    FROM order_items
    GROUP BY order_id
)
SELECT
    SUM(o.shipping_fee) AS total_shipping,
    SUM(i.item_amount) AS total_items
FROM orders AS o
JOIN item_totals AS i
    ON i.order_id = o.order_id;
~~~

Đây là mẫu tổng hợp ở **granularity order** rồi mới ghép. Cần chú ý loại JOIN: INNER JOIN sẽ bỏ các orders không có item; nếu cần giữ toàn bộ order, dùng LEFT JOIN và quy tắc NULL thích hợp.

### 25.3. Một tỷ lệ có thể sai dù cả tử và mẫu đều bị nhân

Đôi khi nhân đều cả tử và mẫu tạo ra một tỷ lệ tình cờ giống ban đầu, khiến test đơn giản không phát hiện lỗi. Nhưng khi các order có số item khác nhau, mức nhân **không đồng đều**, nên tỷ lệ hoặc trung bình có trọng số cũng bị lệch.

Cần xác định:

- Một hàng sau JOIN là đơn, dòng hàng, khách hay sự kiện?
- Mỗi giá trị đo có bị lặp không?
- Trọng số phải tính ở cấp nào?
- Đang muốn average theo người, theo đơn hay theo item?

## 26. COUNT DISTINCT: tỷ lệ trên tập thực thể duy nhất

Nếu bảng event có nhiều sự kiện của cùng một user, có thể cần đếm user duy nhất.

~~~sql
WITH visits(user_id, did_signup) AS (
    VALUES
        (101, FALSE),
        (101, TRUE),
        (102, FALSE),
        (103, TRUE),
        (103, TRUE)
)
SELECT
    COUNT(DISTINCT user_id) AS distinct_users,
    COUNT(DISTINCT user_id) FILTER (
        WHERE did_signup
    ) AS distinct_signed_up_users,
    ROUND(
        100.0 * COUNT(DISTINCT user_id) FILTER (
            WHERE did_signup
        )
        / NULLIF(COUNT(DISTINCT user_id), 0),
        2
    ) AS user_conversion_pct
FROM visits;
~~~

Có 3 người duy nhất (101, 102, 103), trong đó 2 người từng có event signup TRUE. Tỷ lệ user-level là **66,67%**.

### 26.1. Nếu COUNT(*) thay COUNT DISTINCT?

Có 5 event và 3 event có `did_signup=TRUE`, tạo tỷ lệ event-level 60%. Đó là đơn vị đo khác.

### 26.2. Khi nào DISTINCT không đủ?

- Một user có thể có nhiều định danh thiết bị.
- Có event bot hoặc traffic không hợp lệ.
- Tử số và mẫu số thuộc các kỳ quan sát khác nhau.
- Identity mapping bị thiếu hoặc đổi theo thời gian.

Đây là vấn đề mô hình dữ liệu và sản phẩm, không thể giải quyết chỉ bằng thêm từ khóa DISTINCT.

## 27. FILTER và điều kiện kỳ đo phải cùng nhau

Một KPI có thể dùng tử số từ tập đã lọc nhưng mẫu số từ toàn bảng, vô tình thay đổi ý nghĩa.

Ví dụ muốn tỷ lệ signup **trong tháng 11**:

~~~sql
SELECT
    ROUND(
        100.0 * SUM(signups) FILTER (
            WHERE metric_day >= DATE '2026-11-01'
              AND metric_day < DATE '2026-12-01'
        )
        /
        NULLIF(
            SUM(visitors) FILTER (
                WHERE metric_day >= DATE '2026-11-01'
                  AND metric_day < DATE '2026-12-01'
            ),
            0
        ),
        2
    ) AS november_signup_rate_pct
FROM ratio_lab.campaign_daily;
~~~

Với chỉ một kỳ mục tiêu, cách đơn giản và dễ đọc hơn thường là lọc cùng kỳ trong `WHERE` rồi tính tổng:

~~~sql
SELECT
    ROUND(
        100.0 * SUM(signups)
        / NULLIF(SUM(visitors), 0),
        2
    ) AS november_signup_rate_pct
FROM ratio_lab.campaign_daily
WHERE metric_day >= DATE '2026-11-01'
  AND metric_day < DATE '2026-12-01';
~~~

### 27.1. Khi nào FILTER hợp lý hơn WHERE?

Nếu cùng một hàng báo cáo cần các chỉ số cho **nhiều kỳ hoặc nhiều điều kiện khác nhau**, FILTER giúp tính nhiều tổng trong một lượt GROUP BY. Nếu cả tử và mẫu dùng cùng tập, WHERE thường gọn hơn.

### 27.2. Date và timestamptz phải theo timezone nghiệp vụ

Với bảng sự kiện lưu `occurred_at TIMESTAMPTZ`, lọc theo “ngày 14/11 tại Việt Nam” cần hai mốc biên địa phương chuyển sang instant:

~~~sql
WHERE occurred_at >= (
    TIMESTAMP '2026-11-14 00:00'
    AT TIME ZONE 'Asia/Ho_Chi_Minh'
)
AND occurred_at < (
    TIMESTAMP '2026-11-15 00:00'
    AT TIME ZONE 'Asia/Ho_Chi_Minh'
)
~~~

Nếu tính tử số theo ngày Việt Nam nhưng mẫu số theo ngày UTC, tỷ lệ có thể lệch. Cùng một KPI phải dùng **cùng quy ước cửa sổ thời gian**.

## 28. Tính tỷ lệ của tổng bằng window functions

Window functions giúp tính tỷ trọng mà không làm mất từng hàng kết quả.

### 28.1. Tỷ trọng doanh thu từng dòng trong category

~~~sql
SELECT
    sale_line_id,
    category,
    quantity * unit_price AS line_revenue,
    ROUND(
        100.0 * quantity * unit_price
        / NULLIF(
            SUM(quantity * unit_price) OVER (
                PARTITION BY category
            ),
            0
        ),
        2
    ) AS category_revenue_share_pct
FROM ratio_lab.sales_lines
ORDER BY category, sale_line_id;
~~~

Mỗi dòng có phần trăm doanh thu so với **tổng doanh thu của category đó**.

### 28.2. Phân biệt OVER() và OVER(PARTITION BY ...)

- `OVER ()` tính trên toàn tập kết quả của bước window tương ứng.
- `OVER (PARTITION BY category)` tính trong từng category.

Chọn sai partition có thể khiến phần trăm dùng tổng toàn bộ thay vì tổng của nhóm.

### 28.3. Tránh tính lặp trên hàng đã nhân do JOIN

Window function chạy trên tập hàng của truy vấn tại giai đoạn phù hợp. Nếu FROM/JOIN đã nhân dòng hàng, mẫu số window có thể cũng bị nhân. Cần sửa granularity ở đầu vào, không dùng window để che fanout.

## 29. ROUND: làm tròn ở đâu?

PostgreSQL hỗ trợ:

~~~sql
SELECT ROUND(16.666666::numeric, 2) AS rounded_percentage;
~~~

Kết quả là `16.67`.

### 29.1. ROUND cuối cùng khác ROUND từng phần rồi cộng

Ví dụ hai tỷ lệ chưa làm tròn là 33,333...% và 66,666...%. Nếu làm tròn từng phần, tổng có thể thành 99,99% hoặc 100,01% với nhiều nhóm do sai số làm tròn.

Về số học, không nên cộng lại các tỷ lệ đã làm tròn để tính KPI tổng. Hãy lưu **tổng tử/mẫu** hoặc giá trị numeric gốc rồi làm tròn khi hiển thị.

### 29.2. Hàm ROUND có các overload theo kiểu

~~~sql
SELECT ROUND(1.2345::numeric, 2);
~~~

Hợp lệ với `numeric` và tham số số chữ số.

Với `double precision`, dạng `ROUND(double precision, integer)` không được hỗ trợ giống dạng numeric; nếu cần làm tròn tới hai chữ số, ép thành numeric khi phù hợp:

~~~sql
SELECT ROUND(1.2345::double precision::numeric, 2);
~~~

Chú ý ép số thực xấp xỉ sang numeric không thể khôi phục mọi độ chính xác đã mất trước đó.

### 29.3. Làm tròn khác trình bày dấu %

Khi SQL trả `16.67` ở cột `signup_rate_pct`, giao diện có thể hiển thị `16.67%`. Không nên dùng `TO_CHAR</BT> rồi gắn dấu % ở mọi tầng nếu API cần giữ kiểu số để sắp xếp hoặc tính toán.

## 30. NUMERIC và DOUBLE PRECISION

PostgreSQL có hai nhóm kiểu số thường gặp trong phân tích:

- `NUMERIC` cho tính toán thập phân có độ chính xác phù hợp tài chính/đơn vị đếm và khi yêu cầu kiểm soát làm tròn.
- `REAL`/`DOUBLE PRECISION` cho số thực dấu phẩy động xấp xỉ, có thể nhanh và phù hợp những phép đo khoa học/thống kê.

### 30.1. Với tiền, ưu tiên NUMERIC khi cần số thập phân chính xác

~~~sql
SELECT
    0.1::numeric + 0.2::numeric AS decimal_sum;
~~~

`numeric` thường phù hợp tiền vì tránh nhiều sai số biểu diễn nhị phân đặc trưng của floating point.

### 30.2. Với đo lường lớn, double precision có trade-off

Nếu giá trị nguồn là `double precision`, SUM và phép nhân cũng có thể mang sai số xấp xỉ. Điều này không có nghĩa dữ liệu sai, nhưng báo cáo cần biết độ chính xác kỳ vọng.

### 30.3. Ép kiểu trước phép nhân tránh overflow số nguyên

Nếu quantity và price đều là integer lớn:

~~~sql
SELECT
    2000000000::numeric * 2000000000::numeric
    AS product_without_integer_overflow;
~~~

Nếu trước đó phép nhân đã tràn khi thực hiện bằng integer, cast kết quả sau phép nhân là quá muộn. Cần tính với kiểu đủ rộng **ngay tại toán hạng**.

### 30.4. AVG và SUM có kiểu kết quả khác nhau tùy input

Trong PostgreSQL, `AVG(integer)` có thể trả `numeric`; `SUM(integer)` thường trả `bigint`. Đừng suy luận `SUM(integer)/COUNT(*)` tự có phần thập phân chỉ vì `AVG(integer)` trả numeric.

Dùng trực tiếp:

~~~sql
SELECT AVG(quantity) FROM ratio_lab.sales_lines;
~~~

hoặc cast rõ nếu tự thực hiện phép chia:

~~~sql
SELECT
    SUM(quantity)::numeric / NULLIF(COUNT(*), 0)
FROM ratio_lab.sales_lines;
~~~

## 31. Quy tắc khi có giá trị âm

Một tỷ lệ như `revenue/spend` thường mong muốn spend không âm. Nếu spend âm do bút toán hoàn/điều chỉnh, ROAS tổng có thể mang nghĩa khác.

Một trung bình có trọng số với trọng số âm cũng không còn tính chất nằm giữa min và max.

### 31.1. Chọn phạm vi dữ liệu trước khi tính

Nếu chỉ xét giao dịch bán, tách những dòng return/refund theo quy tắc nghiệp vụ hoặc thiết kế fact table lưu riêng loại giao dịch.

### 31.2. Không tự dùng ABS hoặc GREATEST

~~~sql
-- Không mặc định dùng cách này để "sửa" KPI:
-- SUM(ABS(weight) * value) / SUM(ABS(weight))
-- GREATEST(spend, 1)
~~~

Các thao tác trên **thay đổi định nghĩa chỉ số**, không chỉ ngăn lỗi kỹ thuật. Đặc biệt, `GREATEST(denominator,1)` làm những nhóm có 0 attempts trở thành có 1 attempt giả, khiến KPI sai một cách khó phát hiện.

## 32. Đánh giá chất lượng dữ liệu trước khi tổng hợp

Một tỷ lệ có thể âm, lớn hơn 100%, NULL hoặc có mẫu số 0. Trước khi sửa công thức, nên tạo báo cáo kiểm kê.

### 32.1. Kiểm tra dữ liệu chiến dịch

~~~sql
SELECT
    campaign_id,
    metric_day,
    visitors,
    signups
FROM ratio_lab.campaign_daily
WHERE visitors < 0
   OR signups < 0
   OR signups > visitors
   OR visitors IS NULL
   OR signups IS NULL;
~~~

Trong lab với constraints phù hợp, query này dự kiến không trả hàng. Nhưng dữ liệu thật có thể có nguồn nhiều loại metrics hoặc bảng staging chưa có constraints.

### 32.2. Đếm các nhóm mẫu số 0

~~~sql
SELECT
    campaign_id,
    COUNT(*) AS days_total,
    COUNT(*) FILTER (
        WHERE visitors = 0
    ) AS days_with_zero_visitors,
    COUNT(*) FILTER (
        WHERE visitors > 0
    ) AS days_with_positive_visitors
FROM ratio_lab.campaign_daily
GROUP BY campaign_id
ORDER BY campaign_id;
~~~

Biết số ngày không có mẫu giúp người phân tích hiểu độ tin cậy và phạm vi của tỷ lệ.

### 32.3. Báo cáo mức độ bao phủ

Nếu một KPI của 30 ngày chỉ có 4 ngày số liệu, tỷ lệ tính trên 4 ngày có thể đúng về mặt SQL nhưng không đại diện toàn tháng. Cần biết:

- Số ngày có dữ liệu.
- Số ngày được kỳ vọng.
- Mức độ trễ ETL.
- Có sự kiện chưa nhập hay chưa xử lý không.
- Denominator thuộc toàn bộ dân số hay chỉ những hàng quan sát được.

Đây là một phần của **chất lượng số liệu**, không thể giải quyết chỉ bằng `NULLIF</BT>.

## 33. HAVING: lọc nhóm sau khi tổng hợp

Có lúc báo cáo chỉ muốn các nhóm có mẫu số dương.

~~~sql
SELECT
    campaign_id,
    SUM(visitors) AS total_visitors,
    ROUND(
        100.0 * SUM(signups)
        / NULLIF(SUM(visitors), 0),
        2
    ) AS signup_rate_pct
FROM ratio_lab.campaign_daily
GROUP BY campaign_id
HAVING SUM(visitors) > 0
ORDER BY campaign_id;
~~~

Gamma bị loại vì tổng visitors bằng 0.

### 33.1. HAVING khác WHERE

- `WHERE</BT> lọc **hàng nguồn** trước khi nhóm.
- `HAVING</BT> lọc **nhóm kết quả** sau khi aggregate.

Không dùng:

~~~sql
WHERE SUM(visitors) > 0
~~~

vì aggregate không được sử dụng như điều kiện WHERE trực tiếp cùng cấp truy vấn.

### 33.2. Có nên loại nhóm không mẫu?

Phụ thuộc báo cáo:

- Bảng “top campaigns có traffic” có thể loại nhóm 0.
- Dashboard giám sát cần thấy nhóm 0 để phát hiện chiến dịch chưa chạy.
- Data quality report nên giữ nhóm 0 và nêu trạng thái.

Đừng đặt HAVING chỉ vì muốn tránh chia 0 rồi vô tình che mất nhóm quan trọng.

## 34. GROUP BY nhiều chiều và tổng cấp cao

Khi có campaign, ngày, kênh, vùng địa lý, cần xác định nhóm trước khi tính ratio.

Ví dụ dữ liệu lab có campaign và ngày:

~~~sql
SELECT
    metric_day,
    SUM(visitors) AS total_visitors,
    SUM(signups) AS total_signups,
    ROUND(
        100.0 * SUM(signups)
        / NULLIF(SUM(visitors), 0),
        2
    ) AS signup_rate_pct
FROM ratio_lab.campaign_daily
GROUP BY metric_day
ORDER BY metric_day;
~~~

Một tỷ lệ theo ngày trên tất cả campaigns phải dùng **tổng signups của ngày / tổng visitors của ngày**, không AVG tỷ lệ từng chiến dịch trừ khi mỗi chiến dịch là một quan sát có trọng số bằng nhau theo mục tiêu riêng.

### 34.1. Gộp ngày lên tháng

~~~sql
SELECT
    date_trunc('month', metric_day::timestamp)::date
        AS metric_month,
    SUM(visitors) AS visitors,
    SUM(signups) AS signups,
    ROUND(
        100.0 * SUM(signups)
        / NULLIF(SUM(visitors), 0),
        2
    ) AS signup_rate_pct
FROM ratio_lab.campaign_daily
GROUP BY 1
ORDER BY 1;
~~~

Mẫu số của tháng là tổng visitors thuộc đúng kỳ và tập đang xét.

### 34.2. GROUPING SETS/ROLLUP

PostgreSQL hỗ trợ `ROLLUP</BT> hoặc `GROUPING SETS</BT> để tính nhiều cấp nhóm.

~~~sql
SELECT
    campaign_id,
    metric_day,
    SUM(visitors) AS visitors,
    SUM(signups) AS signups,
    ROUND(
        100.0 * SUM(signups)
        / NULLIF(SUM(visitors), 0),
        2
    ) AS signup_rate_pct
FROM ratio_lab.campaign_daily
GROUP BY ROLLUP (campaign_id, metric_day)
ORDER BY campaign_id NULLS LAST, metric_day NULLS LAST;
~~~

Các hàng subtotal/grand total cần được phân biệt bằng `GROUPING()</BT> khi cột nhóm cũng có thể NULL trong dữ liệu. Quan trọng: **mỗi cấp ROLLUP phải tính lại ratio từ SUM tử và SUM mẫu**, không lấy AVG các ratio đã làm tròn ở cấp dưới.

## 35. Performance: giảm khối lượng trước khi chia

Với PostgreSQL, phép chia không phải lúc nào cũng là phần đắt nhất. Trong nhiều báo cáo lớn, chi phí nằm ở:

- Quét tập dữ liệu lớn.
- JOIN làm nhân số hàng.
- GROUP BY trên nhiều khóa.
- Sort hoặc hash aggregate lớn.
- Các biểu thức ép kiểu và hàm phức tạp được tính trên nhiều hàng.
- Dữ liệu chuyển ra ứng dụng.

### 35.1. Lọc thời gian trước khi tổng hợp

~~~sql
SELECT
    campaign_id,
    SUM(signups)::numeric
        / NULLIF(SUM(visitors), 0) AS signup_rate
FROM ratio_lab.campaign_daily
WHERE metric_day >= DATE '2026-11-01'
  AND metric_day < DATE '2026-12-01'
GROUP BY campaign_id;
~~~

Nếu báo cáo thường lọc theo ngày và nhóm theo campaign, index có thể được cân nhắc:

~~~sql
CREATE INDEX idx_campaign_daily_day_campaign
ON ratio_lab.campaign_daily (metric_day, campaign_id);
~~~

Nhưng bảng lab nhỏ nên PostgreSQL có thể vẫn chọn sequential scan. Không tạo index chỉ vì cột nằm trong GROUP BY; phải xem workload, chọn lọc, write overhead và query plan.

### 35.2. Dùng EXPLAIN

~~~sql
EXPLAIN
SELECT
    campaign_id,
    SUM(signups)::numeric
        / NULLIF(SUM(visitors), 0) AS signup_rate
FROM ratio_lab.campaign_daily
GROUP BY campaign_id;
~~~

`EXPLAIN` cho kế hoạch dự kiến. Khi có dữ liệu kiểm thử an toàn:

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT
    campaign_id,
    SUM(signups)::numeric
        / NULLIF(SUM(visitors), 0) AS signup_rate
FROM ratio_lab.campaign_daily
GROUP BY campaign_id;
~~~

`EXPLAIN ANALYZE` **thực sự chạy SELECT** để đo hàng và thời gian. Với DML nó cũng thực thi thay đổi dữ liệu trừ khi được rollback phù hợp.

### 35.3. Partial aggregate và materialized views

Nếu cần cùng một chỉ số theo ngày/tháng cho hàng tỷ sự kiện, có thể cân nhắc lưu **tổng tử số và tổng mẫu số** vào bảng aggregate hoặc materialized view, rồi tính ratio khi đọc.

Không nên chỉ lưu ratio đã làm tròn vì khó gộp các kỳ chính xác.

Ví dụ cấu trúc summary:

~~~sql
CREATE TABLE ratio_lab.campaign_month_summary (
    campaign_id INTEGER NOT NULL,
    metric_month DATE NOT NULL,
    total_visitors BIGINT NOT NULL CHECK (total_visitors >= 0),
    total_signups BIGINT NOT NULL CHECK (total_signups >= 0),
    PRIMARY KEY (campaign_id, metric_month),
    CHECK (total_signups <= total_visitors)
);
~~~

Tầng ETL phải đảm bảo các tổng được cập nhật đúng, không cộng lặp khi retry, và đồng bộ với dữ liệu nguồn. Bản thân việc có bảng summary không bảo đảm số liệu đúng.

## 36. Tích hợp ứng dụng Java: xử lý tỷ lệ NULL

Khi SQL trả `NULL` cho tỷ lệ không xác định, ứng dụng không nên âm thầm biến NULL thành 0 chỉ vì trường nhận `double` nguyên thủy không hỗ trợ null.

Với PostgreSQL/JDBC:

~~~java
import java.math.BigDecimal;
import java.sql.ResultSet;

BigDecimal rate = rs.getBigDecimal("signup_rate_pct");

if (rate == null) {
    // Hiển thị "Chưa đủ dữ liệu" theo hợp đồng API.
} else {
    // Định dạng phần trăm theo locale của người dùng.
}
~~~

Biến `rs` giả định là ResultSet đã được điều hướng tới hàng phù hợp.

### 36.1. Kiểu JSON trong API

Một cách trả rõ:

~~~json
{
  "campaign": "Gamma",
  "totalVisitors": 0,
  "totalSignups": 0,
  "signupRatePct": null,
  "rateStatus": "NO_SAMPLE"
}
~~~

Đây là ví dụ JSON literal, không phải PostgreSQL SQL. Tầng API có thể phân biệt giá trị 0 thật với chưa có mẫu.

### 36.2. BigDecimal và tỷ lệ tiền

Nếu Java cần tính lại giá bình quân, dùng `BigDecimal` với quy tắc scale/rounding được xác định. Với báo cáo tài chính, đừng dùng phép nhân double rồi hy vọng mọi chữ số thập phân đều chính xác.

### 36.3. Không tính một KPI hai lần theo hai công thức khác nhau

Nếu PostgreSQL đã trả `signup_rate_pct=16.67`, frontend không nên tự lấy `25/150` rồi làm tròn theo quy tắc khác trong cùng một vị trí báo cáo mà không thống nhất. Có thể chọn trả **raw numerator/denominator** và để một layer tính, hoặc trả ratio đã được định nghĩa rõ.

## 37. Kiểm thử kết quả và các trường hợp biên

Một công thức tỷ lệ/trung bình có trọng số nên có các test ít nhất cho:

1. Tử số bằng 0, mẫu số dương.
2. Tử số và mẫu số đều 0.
3. Không có hàng đầu vào.
4. Tử số dương và mẫu số 0 nếu dữ liệu cho phép.
5. Một số hàng mẫu số 0 nhưng tổng mẫu số dương.
6. Hai nhóm có kích thước rất chênh lệch.
7. Trọng số bằng 0.
8. Trọng số NULL.
9. Giá trị x NULL nhưng trọng số dương.
10. Trọng số âm nếu mô hình cho phép.
11. Hai nguồn JOIN làm nhân số hàng.
12. Ngày báo cáo khác timezone của session.
13. Số tiền/numerator rất lớn.
14. Làm tròn ở cuối vs làm tròn từng nhóm.
15. Các nhóm dimension không có dữ liệu thực.

### 37.1. Test số học nhỏ

~~~sql
WITH example(numerator, denominator) AS (
    VALUES
        (0::numeric, 10::numeric),
        (5::numeric, 10::numeric),
        (0::numeric, 0::numeric),
        (5::numeric, 0::numeric)
)
SELECT
    numerator,
    denominator,
    numerator / NULLIF(denominator, 0) AS ratio
FROM example;
~~~

Kết quả: 0, 0.5, NULL, NULL.

### 37.2. Kiểm tra weighted average bằng kết quả đã biết

~~~sql
WITH prices(price, quantity) AS (
    VALUES
        (100000::numeric, 2::numeric),
        (160000::numeric, 1::numeric),
        (50000::numeric, 7::numeric)
)
SELECT
    SUM(price * quantity)
    / NULLIF(SUM(quantity), 0) AS weighted_avg_price
FROM prices;
~~~

Kết quả dự kiến: **71000**.

### 37.3. Kiểm tra tỷ lệ trên tổng

~~~sql
WITH days(visitors, signups) AS (
    VALUES
        (100::numeric, 20::numeric),
        (50::numeric, 5::numeric)
)
SELECT
    ROUND(
        100.0 * SUM(signups)
        / NULLIF(SUM(visitors), 0),
        2
    ) AS total_rate_pct,
    ROUND(
        AVG(
            100.0 * signups / NULLIF(visitors, 0)
        ),
        2
    ) AS avg_daily_rate_pct
FROM days;
~~~

Kết quả dự kiến: **16.67** và **15.00**. Test này minh họa trực tiếp vì sao không thể thay tỷ lệ trên tổng bằng AVG tỷ lệ con.

## 38. Những sai lầm thường gặp

### 38.1. Chia hai số nguyên rồi mới CAST

Sai:

~~~sql
(1 / 2)::numeric
~~~

Đúng:

~~~sql
1::numeric / 2
~~~

### 38.2. Không xử lý mẫu số bằng 0

Sai:

~~~sql
SUM(signups)::numeric / SUM(visitors)
~~~

Khi tổng visitors bằng 0, PostgreSQL có thể báo lỗi.

Đúng:

~~~sql
SUM(signups)::numeric / NULLIF(SUM(visitors), 0)
~~~

### 38.3. Biến mọi NULL thành 0

`COALESCE(ratio,0)` có thể xóa sự khác biệt giữa **0% thật** và **chưa đủ mẫu**.

### 38.4. Dùng AVG của tỷ lệ ngày cho tỷ lệ tháng

Sai nếu muốn tỷ lệ trên toàn kỳ với số visitors mỗi ngày khác nhau. Dùng tổng tử/tổng mẫu.

### 38.5. Dùng AVG(unit_price) cho giá bình quân từng đơn vị bán

Nếu quantity mỗi dòng khác nhau, phải dùng trọng số quantity.

### 38.6. Dùng AVG(value * weight)

AVG chia số hàng hợp lệ, không chia tổng weight; đây không phải weighted average.

### 38.7. Tử và mẫu dùng tập hàng khác nhau do NULL

`SUM(value*weight)</BT> có thể bỏ hàng thiếu value, còn `SUM(weight)</BT> vẫn cộng weight của hàng đó. Phải nhất quán cặp quan sát.

### 38.8. Dùng COUNT(*) sau LEFT JOIN để đếm hàng phải

LEFT JOIN không khớp vẫn có một hàng kết quả, vì thế `COUNT(*)` không phải số hàng thực phía phải. Dùng `COUNT(right_table.nonnull_key)`.

### 38.9. Đặt WHERE lên cột của bên phải sau LEFT JOIN

Có thể loại những nhóm thiếu dữ liệu mà ban đầu muốn giữ.

### 38.10. Trộn số người và số event

Chỉ số vẫn ra một con số nhưng có thể không cùng định nghĩa.

### 38.11. Làm tròn từng rate trước khi gộp

Làm tròn không thay thế việc tổng hợp tử/mẫu chính xác.

### 38.12. Không bảo vệ phép nhân khỏi overflow

Cast kết quả sau khi số nguyên đã tràn là quá muộn. Đổi kiểu của toán hạng.

### 38.13. Dùng GREATEST(denominator,1) để tránh 0

Cách này âm thầm thay đổi mẫu số thật và có thể làm KPI sai.

### 38.14. Dùng ABS(weight) để loại dấu âm

Có thể thay đổi ngữ nghĩa dòng trả hàng/điều chỉnh. Cần nghiệp vụ quyết định.

### 38.15. Dùng DISTINCT để chữa JOIN fanout

Distinct không khôi phục quan hệ giữa orders và order_items, và có thể bỏ các giá trị hợp lệ trùng nhau.

### 38.16. Coi ROAS là tỷ lệ chuyển đổi 0–100%

ROAS là hệ số doanh thu/chi phí, có thể lớn hơn 1. Tỷ lệ đăng ký thuộc tập con/trọn tập có định nghĩa khác.

### 38.17. Tính ratio giữa hai khoảng thời gian khác nhau

Cửa sổ thời gian không đồng nhất khiến KPI sai dù SQL không lỗi.

### 38.18. Cho rằng NULL và không có hàng là một

Một nhóm có hàng và mẫu số 0 khác nhóm không có bất kỳ bản ghi nguồn nào.

### 38.19. Cho rằng tất cả tỷ lệ đều phải có 2 số sau dấu phẩy

Precision hiển thị phụ thuộc nghiệp vụ. Tỷ lệ có mẫu rất nhỏ có thể cần cảnh báo độ tin cậy, không chỉ thêm chữ số thập phân.

### 38.20. Có chỉ số đúng toán nhưng sai câu hỏi

Trung bình ngày 15% và tỷ lệ cả kỳ 16,67% đều tính được; chỉ một trong hai trả lời đúng câu hỏi “bao nhiêu phần trăm visitors của toàn kỳ đăng ký?”.

## 39. Bài tập thực hành

### Bài 1 — Phép chia số nguyên

Dự đoán kết quả:

~~~sql
SELECT 3 / 4, 3::numeric / 4;
~~~

**Gợi ý:** 0 và 0.75.

### Bài 2 — Chia cho 0

Viết biểu thức cho 5/0 trả NULL thay vì lỗi.

**Đáp án:**

~~~sql
SELECT 5::numeric / NULLIF(0, 0);
~~~

### Bài 3 — Phân biệt 0 và không xác định

Vì sao 0/100 = 0% còn 0/0 không nên mặc định 0%?

**Gợi ý:** Trường hợp đầu có 100 cơ hội quan sát nhưng không thành công; trường hợp sau không có mẫu để tính.

### Bài 4 — Tỷ lệ chuyển đổi theo ngày

Dùng `ratio_lab.campaign_daily` tính phần trăm signup mỗi ngày, trả NULL nếu visitors=0.

~~~sql
SELECT
    campaign_id,
    metric_day,
    ROUND(
        100.0 * signups / NULLIF(visitors,0),
        2
    ) AS signup_rate_pct
FROM ratio_lab.campaign_daily;
~~~

### Bài 5 — Tỷ lệ cả chiến dịch

Alpha có 20/100 và 5/50. Tính tỷ lệ cả kỳ.

**Gợi ý:** `(20+5)/(100+50) = 16.67%` sau làm tròn.

### Bài 6 — AVG của tỷ lệ

Tại sao AVG(20%,10%)=15% khác tỷ lệ cả kỳ của Alpha?

**Gợi ý:** Hai ngày có visitors 100 và 50, không có trọng số bằng nhau.

### Bài 7 — Weighted average đơn giá

Book bán 2 sản phẩm giá 100.000, 1 sản phẩm giá 160.000 và 7 sản phẩm giá 50.000. Giá bình quân trên một đơn vị?

**Gợi ý:** 71.000.

### Bài 8 — Công thức sai

Vì sao `AVG(quantity*unit_price)` không tính được giá bán bình quân có trọng số quantity?

**Gợi ý:** AVG chia cho số dòng, không phải tổng quantity.

### Bài 9 — Trọng số 0

Hai quan sát có trọng số đều 0. Weighted average trả gì?

**Gợi ý:** NULL / không xác định theo công thức chuẩn.

### Bài 10 — Thiếu cặp value-weight

Giá trị thứ ba NULL nhưng weight=5. Có nên cộng weight=5 vào mẫu khi tử số bỏ giá trị đó?

**Gợi ý:** Không nếu muốn weighted average từ các cặp quan sát đầy đủ.

### Bài 11 — COUNT FILTER

Tạo tỷ lệ event có `outcome='success'` bằng `COUNT(*) FILTER</BT> và mẫu số COUNT(*).

**Gợi ý:** Ép kiểu numeric ở tử và bảo vệ mẫu số bằng NULLIF.

### Bài 12 — LEFT JOIN

Campaign Delta không có dòng daily. Vì sao `COUNT(*)` sau LEFT JOIN có thể bằng 1?

**Gợi ý:** Có một hàng kết quả giữ campaign trái, dù cột bên phải NULL.

### Bài 13 — Gamma khác Delta

Gamma có visitors=0 ở một ngày; Delta không có hàng daily nào. Cần thêm cột gì để phân biệt?

**Gợi ý:** `COUNT(d.campaign_id)` và trạng thái dữ liệu.

### Bài 14 — ROAS

Alpha có revenue=1.500.000 và spend=600.000. ROAS cả kỳ?

**Đáp án:** 2.5.

### Bài 15 — Trung bình ROAS ngày

Alpha có ROAS 3.0 và 1.5 theo hai ngày. Vì sao AVG=2.25 khác ROAS cả kỳ=2.5?

**Gợi ý:** Hai ngày có spend 400.000 và 200.000; trọng số spend khác nhau.

### Bài 16 — Tỷ trọng doanh thu

Alpha doanh thu 1.500.000, Beta 160.000. Alpha chiếm bao nhiêu % tổng hai chiến dịch?

**Gợi ý:** Khoảng 90.36%.

### Bài 17 — Tăng trưởng từ 0

Kỳ trước revenue=0, kỳ này=100. Có nên trả growth=100% không?

**Gợi ý:** Công thức phần trăm thông thường không xác định do mẫu số 0; có thể trả NULL hoặc nhãn mới.

### Bài 18 — JOIN nhân hàng

Một order có 3 order_items và shipping_fee=20. Sau INNER JOIN, SUM(shipping_fee) có thể thành bao nhiêu?

**Gợi ý:** 60, nếu phí của order bị nhân qua 3 item.

### Bài 19 — User-level conversion

Có 5 visit events từ 3 user duy nhất; 2 user có signup. Tỷ lệ user-level?

**Gợi ý:** 2/3 ≈ 66.67%; không dùng số event ở mẫu.

### Bài 20 — GROUP BY tháng

Viết query tính tỷ lệ theo tháng từ campaign_daily, không AVG tỷ lệ theo ngày.

**Gợi ý:** GROUP BY tháng và `SUM(signups)::numeric / NULLIF(SUM(visitors),0)`.

### Bài 21 — HAVING

Chỉ trả campaign có tổng visitors > 0.

**Gợi ý:** `HAVING SUM(visitors) > 0`.

### Bài 22 — ROUND đúng thời điểm

Vì sao nên làm tròn phần trăm sau khi tính SUM tử và SUM mẫu?

**Gợi ý:** Tránh sai số làm tròn ở nhiều nhóm trung gian.

### Bài 23 — Double precision

Vì sao với doanh thu/chi phí thập phân, NUMERIC có thể phù hợp hơn DOUBLE PRECISION?

**Gợi ý:** NUMERIC hỗ trợ tính toán thập phân chính xác; double dùng số thực nhị phân xấp xỉ.

### Bài 24 — Mẫu số giả

Vì sao thay `NULLIF(spend,0)` bằng `GREATEST(spend,1)` có thể làm ROAS sai?

**Gợi ý:** Nó thay dữ liệu mẫu số thực bằng 1 khi spend=0.

### Bài 25 — API hiển thị tỷ lệ

Nếu PostgreSQL trả `signup_rate_pct=NULL`, JSON và UI nên truyền tải gì?

**Gợi ý:** Có thể trả null cùng rateStatus=NO_SAMPLE và hiển thị “Chưa đủ dữ liệu”, không tự đổi thành 0%.

## 40. Bảng tra nhanh

| Nhu cầu | Công thức PostgreSQL |
|---|---|
| Tỷ lệ thập phân | `numerator::numeric / NULLIF(denominator,0)` |
| Tỷ lệ phần trăm | `100.0 * numerator / NULLIF(denominator,0)` |
| Tỷ lệ từ các tổng | `SUM(numerator)::numeric / NULLIF(SUM(denominator),0)` |
| Tỷ lệ % làm tròn 2 số | `ROUND(100.0 * SUM(num)/NULLIF(SUM(den),0),2)` |
| Trung bình cộng | `AVG(value)` |
| Trung bình có trọng số | `SUM(value*weight)/NULLIF(SUM(weight),0)` |
| Giá bình quân mỗi đơn vị | `SUM(quantity*unit_price)/NULLIF(SUM(quantity),0)` |
| Tỷ lệ success trong event | `COUNT(*) FILTER (WHERE success)::numeric / NULLIF(COUNT(*),0)` |
| Đếm hàng không NULL của cột | `COUNT(column)` |
| Đếm mọi hàng | `COUNT(*)` |
| Tỷ trọng trên toàn tập | `value / NULLIF(SUM(value) OVER (),0)` |
| Tỷ trọng trong phân nhóm | `value / NULLIF(SUM(value) OVER (PARTITION BY group_key),0)` |
| ROAS | `SUM(revenue)/NULLIF(SUM(spend),0)` |
| Tốc độ tăng trưởng | `(current-previous)/NULLIF(previous,0)` |
| Phân biệt nhóm có dữ liệu | `COUNT(right_table.nonnull_key)` |
| Nhóm có mẫu số dương | `HAVING SUM(denominator)>0` |
| Làm tròn numeric | `ROUND(expression::numeric,2)` |
| NULL khi mẫu bằng 0 | `NULLIF(denominator,0)` |
| Hiển thị 0 thay NULL khi hợp đồng cho phép | `COALESCE(expression,0)` |
| Kiểm tra kết quả nhóm | `GROUP BY`, `HAVING` |
| Nhiều tổng có điều kiện | `aggregate(...) FILTER (WHERE ...)` |
| Xem kế hoạch | `EXPLAIN` |
| Đo query có thực thi | `EXPLAIN (ANALYZE, BUFFERS)` |

---

## Kết luận

Khi tính **tỷ lệ**, **trung bình có trọng số** và xử lý **chia cho không** trong PostgreSQL, vấn đề đầu tiên không phải cú pháp mà là **ý nghĩa của tử số, mẫu số và đơn vị quan sát**. Một phép chia có thể chạy bình thường nhưng trả chỉ số sai nếu hai tập không cùng phạm vi, nếu JOIN làm nhân hàng hoặc nếu dùng trung bình các tỷ lệ con thay cho tỷ lệ trên tổng.

Ba mẫu SQL quan trọng cần nhớ là:

~~~sql
-- 1. Tỷ lệ trên tổng; giữ phần thập phân và tránh chia 0.
SUM(numerator)::numeric / NULLIF(SUM(denominator), 0)

-- 2. Trung bình có trọng số; các cặp value-weight phải cùng tập hợp.
SUM(value * weight) / NULLIF(SUM(weight), 0)

-- 3. Phần trăm được làm tròn khi hiển thị.
ROUND(
    100.0 * SUM(numerator) / NULLIF(SUM(denominator), 0),
    2
)
~~~

Đây là **mẫu biểu thức khái niệm**; thay `numerator`, `denominator`, `value` và `weight` bằng cột/biểu thức thực tế.

Hãy để `NULLIF` bảo vệ mẫu số 0, chỉ dùng `COALESCE</BT> khi số 0 thực sự có ý nghĩa, ép kiểu trước phép chia hoặc phép nhân có nguy cơ mất chính xác, và làm tròn sau khi đã tổng hợp. Khi lưu số liệu theo ngày/nhóm, nên giữ **tổng tử và tổng mẫu** để có thể gộp kỳ đúng, thay vì chỉ giữ tỷ lệ đã làm tròn.

Quan trọng nhất, một chỉ số đáng tin cậy phải đúng cả về **toán học, kiểu dữ liệu, thời gian, granularity, tình trạng dữ liệu thiếu và quy tắc nghiệp vụ**. PostgreSQL cung cấp đủ công cụ để biểu đạt các phép tính đó rõ ràng; trách nhiệm của người viết SQL là chọn đúng ý nghĩa trước khi chọn công thức.
