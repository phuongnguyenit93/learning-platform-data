# GROUPING để phân biệt NULL dữ liệu với NULL của tổng phụ

Khi tổng hợp dữ liệu bằng `GROUP BY`, các giá trị `NULL` trong cột nhóm thường biểu thị **thông tin chưa xác định** ở dữ liệu gốc. Nhưng khi sử dụng `ROLLUP`, `CUBE` hoặc `GROUPING SETS` để tạo các mức tổng hợp, SQL còn có thể hiển thị `NULL` tại vị trí của **chiều phân nhóm đã được gộp bỏ**.

Hai loại `NULL` có hình thức giống nhau nhưng ý nghĩa hoàn toàn khác nhau:

- **`NULL` của dữ liệu gốc:** một hàng bán hàng thật sự chưa có khu vực hoặc chưa xác định kênh bán.
- **`NULL` của hàng tổng phụ/tổng cộng:** DBMS chủ động bỏ chiều phân nhóm đó để tính tổng trên nhiều giá trị.

Nếu chỉ dùng `IS NULL` hoặc `COALESCE` để xác định hàng tổng, báo cáo có thể **gắn nhãn sai, cộng trùng hoặc lọc nhầm dữ liệu**. Hàm **`GROUPING(expression)`** ra đời để giải quyết chính xác vấn đề này.

Bài học giải thích cách `GROUPING` hoạt động với `ROLLUP`, `CUBE` và `GROUPING SETS`; cách đọc các cờ `0`/`1` và mã bitmask nhiều chiều; cách gắn nhãn, lọc và sắp xếp kết quả; cũng như các khác biệt theo phương ngữ SQL. Các ví dụ chính sử dụng **PostgreSQL** để có cú pháp và kết quả nhất quán.

## 1. Vì sao có nhiều loại NULL trong kết quả tổng hợp?

Trước tiên, xét việc nhóm bình thường:

```sql
SELECT region, SUM(amount) AS revenue
FROM sales
GROUP BY region;
```

Nếu một số dòng có `region IS NULL`, SQL đặt chúng vào **một nhóm khu vực chưa biết**, rồi tính tổng cho nhóm đó. Trong trường hợp này, `NULL` ở cột `region` biểu diễn giá trị phân nhóm xuất phát từ dữ liệu.

Nhưng khi muốn báo cáo vừa có **doanh thu từng khu vực** vừa có **tổng doanh thu tất cả khu vực**, ta có thể viết:

```sql
SELECT region, SUM(amount) AS revenue
FROM sales
GROUP BY ROLLUP (region);
```

Kết quả có thể chứa hai hàng với `region = NULL`:

1. Tổng doanh thu **của các dòng không có khu vực**.
2. Tổng doanh thu **của tất cả khu vực**, tức hàng tổng cộng.

Cả hai đều xuất hiện dưới dạng `NULL` ở cột `region`, nhưng chắc chắn không phải cùng một nhóm.

### 1.1. Nhìn vào bảng kết quả là chưa đủ

Giả sử dữ liệu có:

| region | amount |
| --- | ---: |
| Bắc | 100 |
| Bắc | 50 |
| Nam | 80 |
| `NULL` | 20 |

Truy vấn `ROLLUP(region)` có thể tạo:

| region | revenue | Ý nghĩa thực sự |
| --- | ---: | --- |
| Bắc | 150 | Doanh thu khu vực Bắc |
| Nam | 80 | Doanh thu khu vực Nam |
| `NULL` | 20 | Doanh thu của các dòng **không có khu vực** |
| `NULL` | 250 | **Tổng doanh thu** |

Nếu sử dụng `WHERE region IS NULL` trên một kết quả đã tổng hợp, hoặc gắn nhãn mọi `NULL` là `'TỔNG CỘNG'`, người đọc sẽ không thể phân biệt hàng doanh thu **20** với hàng doanh thu **250**.

**Giải pháp:** thêm cột `GROUPING(region)` để biết `region` có bị **bỏ ra khỏi tập cột phân nhóm** tại hàng kết quả đó hay không.

## 2. GROUPING trả về gì?

Về mặt khái niệm, `GROUPING(column_or_expression)` trả:

| Kết quả | Ý nghĩa |
| ---: | --- |
| `0` | Biểu thức **có mặt** trong tập cột dùng để nhóm cho hàng kết quả này. Giá trị hiển thị vẫn có thể là `NULL` thật từ dữ liệu. |
| `1` | Biểu thức **không có mặt** trong tập cột dùng để nhóm cho hàng kết quả này; nó đã được gộp bỏ để tạo tổng phụ/tổng cộng. `NULL` ở vị trí ấy là dấu hiệu tổng hợp. |

Điều quan trọng nhất:

> **`GROUPING(column) = 1` không có nghĩa “cột chứa NULL”. Nó có nghĩa “cột đã được gộp bỏ ở mức tổng hợp này”.**

Ngược lại, `GROUPING(column) = 0` không bảo đảm giá trị cột khác `NULL`. Nó chỉ xác nhận cột vẫn là một chiều nhóm của hàng hiện tại.

### 2.1. Một ví dụ ngắn

```sql
-- PostgreSQL, SQL Server, Oracle và các DBMS hỗ trợ GROUPING/ROLLUP.
SELECT
    region,
    SUM(amount) AS revenue,
    GROUPING(region) AS g_region
FROM sales
GROUP BY ROLLUP (region)
ORDER BY GROUPING(region), region;
```

Trong ví dụ nhỏ ở mục 1:

| region | revenue | g_region |
| --- | ---: | ---: |
| Bắc | 150 | 0 |
| Nam | 80 | 0 |
| `NULL` | 20 | 0 |
| `NULL` | 250 | 1 |

Hai hàng cuối giống nhau về `region` nhưng khác `g_region`:

- `(NULL, 20, 0)` là nhóm dữ liệu thực sự thiếu khu vực.
- `(NULL, 250, 1)` là tổng cộng, vì cột khu vực đã bị gộp bỏ.

Ở các DBMS khác nhau, vị trí sắp xếp của `NULL` có thể khác nhau; bảng trên chỉ trình bày nội dung. Nếu cần thứ tự ổn định, phải chủ động sắp xếp theo cờ nhóm và các khóa cần thiết.

## 3. Tạo dữ liệu mẫu có NULL thật

Dùng một bảng bán hàng gồm hai chiều phân tích:

- `region`: khu vực bán hàng.
- `channel`: kênh bán hàng.

Cả hai đều **được phép `NULL`** vì dữ liệu có thể đến từ nhiều nguồn và chưa được phân loại đầy đủ.

Ví dụ PostgreSQL:

```sql
CREATE TABLE sales_demo (
    sale_id INTEGER PRIMARY KEY,
    region VARCHAR(30),
    channel VARCHAR(30),
    amount NUMERIC(12, 2) NOT NULL
);

INSERT INTO sales_demo (sale_id, region, channel, amount)
VALUES
    (1, 'Bắc', 'Online', 100),
    (2, 'Bắc', NULL,       40),
    (3, 'Bắc', 'Store',    60),
    (4, 'Nam', 'Online',   80),
    (5, 'Nam', NULL,      20),
    (6, NULL,  'Online',   30),
    (7, NULL,  NULL,       10);
```

Dữ liệu gốc:

| sale_id | region | channel | amount |
| ---: | --- | --- | ---: |
| 1 | Bắc | Online | 100 |
| 2 | Bắc | `NULL` | 40 |
| 3 | Bắc | Store | 60 |
| 4 | Nam | Online | 80 |
| 5 | Nam | `NULL` | 20 |
| 6 | `NULL` | Online | 30 |
| 7 | `NULL` | `NULL` | 10 |

Các tổng có thể tính bằng tay:

- Khu vực **Bắc**: `100 + 40 + 60 = 200`.
- Khu vực **Nam**: `80 + 20 = 100`.
- Nhóm **chưa xác định khu vực**: `30 + 10 = 40`.
- **Tổng toàn bộ dữ liệu**: `200 + 100 + 40 = 340`.

Chỉ tính theo kênh:

- **Online**: `100 + 80 + 30 = 210`.
- **Store**: `60`.
- **Kênh chưa xác định**: `40 + 20 + 10 = 70`.

Bảng này cố ý có cả `region IS NULL` lẫn `channel IS NULL` để thể hiện mọi tình huống dễ nhầm với hàng tổng.

## 4. GROUP BY thông thường: NULL chỉ là giá trị của nhóm

Trước khi dùng `ROLLUP`, chạy truy vấn hai chiều:

```sql
SELECT
    region,
    channel,
    SUM(amount) AS revenue
FROM sales_demo
GROUP BY region, channel
ORDER BY region NULLS LAST, channel NULLS LAST;
```

Kết quả gồm bảy nhóm:

| region | channel | revenue |
| --- | --- | ---: |
| Bắc | Online | 100 |
| Bắc | Store | 60 |
| Bắc | `NULL` | 40 |
| Nam | Online | 80 |
| Nam | `NULL` | 20 |
| `NULL` | Online | 30 |
| `NULL` | `NULL` | 10 |

Trong `GROUP BY` thông thường, các hàng có cùng tổ hợp khóa nhóm được gom với nhau. Những giá trị `NULL` của cột nhóm được xét cùng một nhóm theo quy tắc phân nhóm của SQL, dù phép `NULL = NULL` trong điều kiện so sánh bình thường trả `UNKNOWN`.

Nhìn vào hàng cuối:

```text
region  = NULL
channel = NULL
revenue = 10
```

Đây **không** phải tổng cộng. Nó là doanh thu của dòng `sale_id = 7`, nơi cả khu vực và kênh đều chưa biết.

Nếu gọi hàm `GROUPING` trong một ngữ cảnh phân nhóm mà cả hai chiều đều luôn được giữ lại, các cờ tương ứng đều là `0`. `GROUPING` không phải một biến thể của `IS NULL`.

## 5. ROLLUP: tạo tổng phụ theo hệ phân cấp

`ROLLUP` tạo thêm những mức tổng hợp bằng cách lần lượt **bỏ các chiều từ phải sang trái** trong danh sách phân nhóm.

Ví dụ:

```sql
GROUP BY ROLLUP (region, channel)
```

tạo các tập cột nhóm:

| Mức | Tập cột nhóm | Ý nghĩa |
| --- | --- | --- |
| Chi tiết | `(region, channel)` | Doanh thu cho từng tổ hợp khu vực/kênh. |
| Tổng phụ theo khu vực | `(region)` | Doanh thu mọi kênh trong từng khu vực. |
| Tổng cộng | `()` | Doanh thu tất cả khu vực, tất cả kênh. |

Với hai chiều, `ROLLUP(region, channel)` tạo **ba mức**, không phải bốn mức. Nó không tự tạo hàng tổng riêng cho từng kênh trên toàn khu vực; muốn mức đó, dùng `CUBE` hoặc `GROUPING SETS`.

### 5.1. Truy vấn ROLLUP với các cờ GROUPING

```sql
SELECT
    region,
    channel,
    SUM(amount) AS revenue,
    GROUPING(region) AS g_region,
    GROUPING(channel) AS g_channel
FROM sales_demo
GROUP BY ROLLUP (region, channel)
ORDER BY
    GROUPING(region),
    region NULLS LAST,
    GROUPING(channel),
    channel NULLS LAST;
```

Kết quả được trình bày theo từng khu vực:

| region | channel | revenue | g_region | g_channel |
| --- | --- | ---: | ---: | ---: |
| Bắc | Online | 100 | 0 | 0 |
| Bắc | Store | 60 | 0 | 0 |
| Bắc | `NULL` | 40 | 0 | 0 |
| Bắc | `NULL` | 200 | 0 | 1 |
| Nam | Online | 80 | 0 | 0 |
| Nam | `NULL` | 20 | 0 | 0 |
| Nam | `NULL` | 100 | 0 | 1 |
| `NULL` | Online | 30 | 0 | 0 |
| `NULL` | `NULL` | 10 | 0 | 0 |
| `NULL` | `NULL` | 40 | 0 | 1 |
| `NULL` | `NULL` | 340 | 1 | 1 |

Kết quả có **11 hàng**:

- **7 hàng chi tiết** từ `(region, channel)`.
- **3 hàng tổng phụ khu vực** từ `(region)`: Bắc, Nam và khu vực thật sự chưa xác định.
- **1 hàng tổng cộng** từ `()`.

### 5.2. Phân tích bốn hàng có cả region và channel là NULL

Trong bảng trên xuất hiện **ba hàng** đều hiển thị:

```text
region  = NULL
channel = NULL
```

Nhưng doanh thu và cờ khác nhau:

| revenue | g_region | g_channel | Ý nghĩa |
| ---: | ---: | ---: | --- |
| 10 | 0 | 0 | **Hàng chi tiết:** khu vực và kênh đều thiếu trong dữ liệu thật. |
| 40 | 0 | 1 | **Tổng phụ khu vực chưa xác định:** gộp tất cả kênh của các dòng `region IS NULL`. |
| 340 | 1 | 1 | **Tổng cộng toàn bảng:** cả hai chiều đều bị gộp bỏ. |

Ở kết quả `ROLLUP` này thực tế có **ba** hàng mà cả hai cột đều là `NULL`; hàng `(NULL, Online, 30)` không thuộc trường hợp cả hai cột `NULL`. Những cờ trong ba hàng giống hình thức ấy giúp xác định chính xác ý nghĩa của chúng.

> Khi nhìn kết quả `ROLLUP`, hãy đọc **giá trị nhóm cùng với cờ `GROUPING`**, không chỉ nhìn chuỗi hiển thị của `region` hoặc `channel`.

### 5.3. Cách hiểu cờ của từng mức

| g_region | g_channel | Mức trong `ROLLUP(region, channel)` |
| ---: | ---: | --- |
| 0 | 0 | Chi tiết theo khu vực và kênh; `NULL` nếu có là từ nhóm dữ liệu gốc. |
| 0 | 1 | Tổng phụ theo khu vực; kênh đã bị gộp bỏ. |
| 1 | 1 | Tổng cộng; cả khu vực và kênh đã bị gộp bỏ. |

Tổ hợp `(1, 0)` **không được tạo bởi thứ tự `ROLLUP(region, channel)`**. Nó sẽ xuất hiện khi dùng `CUBE(region, channel)` hoặc tạo grouping set chỉ gồm `(channel)`.

## 6. Gắn nhãn đúng: GROUPING trước, IS NULL sau

Một yêu cầu thực tế là đổi những ô `NULL` trong báo cáo thành tên dễ hiểu:

- Tổng các khu vực → `TẤT CẢ KHU VỰC`.
- Khu vực thiếu trong dữ liệu → `CHƯA XÁC ĐỊNH KHU VỰC`.
- Tổng các kênh → `TẤT CẢ KÊNH`.
- Kênh thiếu trong dữ liệu → `CHƯA XÁC ĐỊNH KÊNH`.

**Không nên chỉ dùng `COALESCE(region, 'TẤT CẢ KHU VỰC')`**, vì nó sẽ đổi cả `NULL` thật của dữ liệu thành nhãn tổng cộng.

### 6.1. Cách làm đúng với CASE

```sql
SELECT
    CASE
        WHEN GROUPING(region) = 1 THEN 'TẤT CẢ KHU VỰC'
        WHEN region IS NULL THEN 'CHƯA XÁC ĐỊNH KHU VỰC'
        ELSE region
    END AS region_label,
    CASE
        WHEN GROUPING(channel) = 1 THEN 'TẤT CẢ KÊNH'
        WHEN channel IS NULL THEN 'CHƯA XÁC ĐỊNH KÊNH'
        ELSE channel
    END AS channel_label,
    SUM(amount) AS revenue,
    GROUPING(region) AS g_region,
    GROUPING(channel) AS g_channel
FROM sales_demo
GROUP BY ROLLUP (region, channel)
ORDER BY
    GROUPING(region),
    region NULLS LAST,
    GROUPING(channel),
    channel NULLS LAST;
```

Ví dụ một số hàng quan trọng:

| region_label | channel_label | revenue | g_region | g_channel |
| --- | --- | ---: | ---: | ---: |
| Bắc | CHƯA XÁC ĐỊNH KÊNH | 40 | 0 | 0 |
| Bắc | TẤT CẢ KÊNH | 200 | 0 | 1 |
| CHƯA XÁC ĐỊNH KHU VỰC | CHƯA XÁC ĐỊNH KÊNH | 10 | 0 | 0 |
| CHƯA XÁC ĐỊNH KHU VỰC | TẤT CẢ KÊNH | 40 | 0 | 1 |
| TẤT CẢ KHU VỰC | TẤT CẢ KÊNH | 340 | 1 | 1 |

**Thứ tự kiểm tra rất quan trọng:** xét `GROUPING(...) = 1` trước để nhận biết tổng phụ/tổng cộng, sau đó mới xét `IS NULL` để đặt nhãn cho dữ liệu thiếu.

### 6.2. Vì sao COALESCE đơn thuần gây lỗi?

Truy vấn sau **không đủ thông tin**:

```sql
SELECT
    COALESCE(region, 'TẤT CẢ KHU VỰC') AS region_label,
    SUM(amount) AS revenue
FROM sales_demo
GROUP BY ROLLUP (region);
```

Nó đặt cùng nhãn cho:

- Nhóm khu vực không được khai báo, doanh thu `40`.
- Tổng tất cả khu vực, doanh thu `340`.

Nếu đem kết quả này làm biểu đồ, người đọc có thể thấy hai hàng cùng nhãn mà không hiểu nguyên nhân hoặc hệ thống có thể gộp sai hai hàng.

**Nguyên tắc:** `COALESCE` có ích để thay giá trị `NULL` theo ý nghĩa đã biết; nó **không biết vì sao `NULL` xuất hiện**. Hàm `GROUPING` mới cung cấp thông tin đó khi dùng các mức tổng hợp.

## 7. GROUPING nhiều tham số và bitmask

Trên PostgreSQL, `GROUPING` có thể nhận **nhiều biểu thức**:

```sql
GROUPING(region, channel)
```

Kết quả là một **số nguyên bitmask**. Mỗi biểu thức có một bit:

- Bit `0` nếu biểu thức còn trong grouping set của hàng hiện tại.
- Bit `1` nếu biểu thức đã bị gộp bỏ.

Đối số **bên phải nhất** ứng với bit thấp nhất (trọng số `1`), đối số bên trái có trọng số cao hơn.

Với hai biểu thức:

```text
GROUPING(region, channel)
            |       |
            |       +-- bit thấp nhất: 1 nếu channel bị bỏ
            +---------- bit tiếp theo: 2 nếu region bị bỏ
```

Vì vậy:

| GROUPING(region) | GROUPING(channel) | GROUPING(region, channel) | Mức |
| ---: | ---: | ---: | --- |
| 0 | 0 | 0 | Chi tiết `(region, channel)` |
| 0 | 1 | 1 | Tổng phụ khu vực `(region)` |
| 1 | 0 | 2 | Tổng phụ kênh `(channel)` |
| 1 | 1 | 3 | Tổng cộng `()` |

Trong `ROLLUP(region, channel)` chỉ có mã **0**, **1** và **3**; mã **2** sẽ xuất hiện với `CUBE` hoặc `GROUPING SETS` có tập nhóm theo kênh.

### 7.1. Truy vấn cùng lúc cờ riêng và mã nhóm

```sql
SELECT
    region,
    channel,
    SUM(amount) AS revenue,
    GROUPING(region) AS g_region,
    GROUPING(channel) AS g_channel,
    GROUPING(region, channel) AS grouping_mask
FROM sales_demo
GROUP BY ROLLUP (region, channel)
ORDER BY
    GROUPING(region),
    region NULLS LAST,
    GROUPING(channel),
    channel NULLS LAST;
```

Một số hàng tiêu biểu:

| region | channel | revenue | g_region | g_channel | grouping_mask |
| --- | --- | ---: | ---: | ---: | ---: |
| Bắc | Online | 100 | 0 | 0 | 0 |
| Bắc | `NULL` | 40 | 0 | 0 | 0 |
| Bắc | `NULL` | 200 | 0 | 1 | 1 |
| `NULL` | `NULL` | 10 | 0 | 0 | 0 |
| `NULL` | `NULL` | 40 | 0 | 1 | 1 |
| `NULL` | `NULL` | 340 | 1 | 1 | 3 |

Mã `0` **không nói rằng tất cả giá trị đều khác `NULL`**. Nó chỉ nói mọi chiều phân tích còn trong grouping set. Hàng `(NULL, NULL, 10)` vẫn có mã `0`.

### 7.2. Ba chiều thì sao?

Nếu có ba chiều:

```sql
GROUPING(region, channel, product_type)
```

thì các trọng số bit là:

| Đối số | Trọng số nếu bị gộp bỏ |
| --- | ---: |
| `region` | 4 |
| `channel` | 2 |
| `product_type` | 1 |

Ví dụ:

- Mã `0`: giữ cả ba chiều.
- Mã `1`: chỉ bỏ `product_type`.
- Mã `3`: bỏ `channel` và `product_type`.
- Mã `7`: bỏ cả ba chiều.

Cần chú ý **thứ tự đối số**: `GROUPING(channel, region)` sẽ dùng trọng số ngược với `GROUPING(region, channel)`.

### 7.3. GROUPING và GROUPING_ID

SQL Server và Oracle có hàm **`GROUPING_ID(...)`** chuyên trả mã mức nhóm theo biểu thức được chỉ định. PostgreSQL dùng **`GROUPING(expr1, expr2, ...)`** để lấy bitmask nhiều chiều.

Không nên sao chép nguyên:

```sql
GROUPING_ID(region, channel)
```

sang PostgreSQL và mặc định hệ quản trị có hàm đó. Trên PostgreSQL, biểu thức tương ứng là:

```sql
GROUPING(region, channel)
```

Phương ngữ và hỗ trợ nhiều đối số cần được kiểm tra theo DBMS mục tiêu.

## 8. CUBE: xuất hiện đầy đủ bốn loại hàng với hai chiều

`ROLLUP` tạo tổng theo hệ phân cấp. `CUBE` tạo mọi tổ hợp chọn/bỏ các chiều phân nhóm.

Với:

```sql
GROUP BY CUBE (region, channel)
```

các grouping set là:

| Tập nhóm | Giải thích | GROUPING(region, channel) |
| --- | --- | ---: |
| `(region, channel)` | Chi tiết hai chiều | 0 |
| `(region)` | Tổng phụ theo khu vực | 1 |
| `(channel)` | Tổng phụ theo kênh | 2 |
| `()` | Tổng cộng | 3 |

### 8.1. Ví dụ CUBE với cờ GROUPING

```sql
SELECT
    region,
    channel,
    SUM(amount) AS revenue,
    GROUPING(region) AS g_region,
    GROUPING(channel) AS g_channel,
    GROUPING(region, channel) AS grouping_mask
FROM sales_demo
GROUP BY CUBE (region, channel)
ORDER BY
    GROUPING(region),
    GROUPING(channel),
    region NULLS LAST,
    channel NULLS LAST;
```

Với dữ liệu mẫu, `CUBE` tạo:

- **7 hàng chi tiết** `(region, channel)`.
- **3 hàng tổng phụ theo khu vực** `(region)`.
- **3 hàng tổng phụ theo kênh** `(channel)`.
- **1 hàng tổng cộng** `()`.

Tổng cộng **14 hàng**. Đây là các hàng kết quả ở những mức khác nhau, **không phải 14 bản ghi mới** được thêm vào `sales_demo`.

### 8.2. Các hàng có hai cột NULL trong CUBE

Điều đáng chú ý nhất là `CUBE` tạo ra **bốn hàng** mà cả hai cột `region` và `channel` đều hiển thị `NULL`:

| region | channel | revenue | g_region | g_channel | grouping_mask | Ý nghĩa |
| --- | --- | ---: | ---: | ---: | ---: | --- |
| `NULL` | `NULL` | 10 | 0 | 0 | 0 | Chi tiết: cả hai chiều thiếu trong dữ liệu gốc |
| `NULL` | `NULL` | 40 | 0 | 1 | 1 | Tổng phụ của **nhóm khu vực chưa biết** |
| `NULL` | `NULL` | 70 | 1 | 0 | 2 | Tổng phụ của **nhóm kênh chưa biết** |
| `NULL` | `NULL` | 340 | 1 | 1 | 3 | Tổng cộng tất cả khu vực và kênh |

Bảng này là minh họa rõ nhất về sự khác biệt giữa:

- **`NULL` là giá trị nhóm thực sự từ dữ liệu**.
- **`NULL` là chỗ trống do chiều phân tích đã bị gộp bỏ để tổng hợp**.

Chỉ nhìn hai cột `region` và `channel` không thể biết hàng nào thuộc mức nào. Bộ cờ `GROUPING` hoặc bitmask `GROUPING(region, channel)` giải quyết được sự mơ hồ này.

### 8.3. Một hàng tổng phụ kênh có region NULL nhưng channel có giá trị

Ví dụ `CUBE` tạo:

```text
region  = NULL
channel = Online
revenue = 210
g_region = 1
g_channel = 0
grouping_mask = 2
```

Nó có nghĩa **doanh thu Online trên tất cả khu vực**:

```text
100 (Bắc)
+ 80 (Nam)
+ 30 (khu vực chưa biết)
= 210
```

Đây không phải “doanh thu Online chỉ ở những dòng `region IS NULL`”, vì tổng của nhóm đó là **30** và `g_region = 0`.

## 9. GROUPING SETS: chọn chính xác các mức cần hiển thị

Nếu chỉ cần một số mức tổng, ta có thể dùng `GROUPING SETS` thay vì toàn bộ `CUBE`.

Ví dụ:

```sql
SELECT
    region,
    channel,
    SUM(amount) AS revenue,
    GROUPING(region) AS g_region,
    GROUPING(channel) AS g_channel
FROM sales_demo
GROUP BY GROUPING SETS (
    (region, channel),
    (region),
    ()
);
```

Ba tập nhóm này tạo cùng **các mức** với:

```sql
GROUP BY ROLLUP (region, channel)
```

Còn nếu muốn:

- Chi tiết theo khu vực và kênh.
- Tổng theo kênh trên toàn khu vực.
- Tổng cộng.

Có thể viết:

```sql
SELECT
    region,
    channel,
    SUM(amount) AS revenue,
    GROUPING(region, channel) AS grouping_mask
FROM sales_demo
GROUP BY GROUPING SETS (
    (region, channel),
    (channel),
    ()
)
ORDER BY
    GROUPING(region, channel),
    region NULLS LAST,
    channel NULLS LAST;
```

Truy vấn này có các mã **0**, **2**, **3** nhưng không có mã **1** do không tạo tổng phụ riêng theo khu vực.

### 9.1. Không phải GROUPING SETS chỉ dùng để thay ROLLUP

`GROUPING SETS` thích hợp khi báo cáo cần **một tập các mức cụ thể**, chẳng hạn:

```sql
GROUP BY GROUPING SETS (
    (region, channel),
    (region),
    (channel),
    ()
)
```

Tổ hợp này tương đương các mức của `CUBE(region, channel)` trong ví dụ hai chiều. Nhưng với nhiều chiều, `GROUPING SETS` cho phép chỉ chọn những mức thực sự cần, tránh tạo quá nhiều tập nhóm.

### 9.2. Có thể chọn một mức duy nhất

Ví dụ chỉ cần tổng doanh thu theo kênh:

```sql
SELECT
    channel,
    SUM(amount) AS revenue
FROM sales_demo
GROUP BY channel;
```

Không cần dùng `GROUPING SETS` hoặc `GROUPING` nếu không có các mức tổng khác nhau và không cần phân biệt `NULL` tổng phụ. Chọn công cụ đơn giản nhất đáp ứng đúng bài toán.

## 10. Lọc hàng tổng phụ bằng HAVING và GROUPING

Một nhu cầu phổ biến là truy vấn tất cả mức tổng, sau đó chỉ giữ một loại hàng.

Điểm quan trọng về thứ tự xử lý logic SQL:

- `WHERE` lọc **các dòng dữ liệu nguồn** trước tổng hợp.
- `GROUP BY`/`ROLLUP`/`CUBE` tạo các nhóm và mức tổng.
- `HAVING` lọc **các nhóm/kết quả tổng hợp**.
- `ORDER BY` của truy vấn cuối cùng quy định thứ tự trả về.

Vì `GROUPING(...)` mô tả **mức nhóm**, ta thường dùng trong `SELECT` và `HAVING`, hoặc lọc các cờ đã tính bằng một truy vấn ngoài.

### 10.1. Chỉ lấy hàng chi tiết

```sql
SELECT
    region,
    channel,
    SUM(amount) AS revenue
FROM sales_demo
GROUP BY ROLLUP (region, channel)
HAVING GROUPING(region) = 0
   AND GROUPING(channel) = 0
ORDER BY region NULLS LAST, channel NULLS LAST;
```

Kết quả là **7 hàng chi tiết**. Các hàng có `region IS NULL` hoặc `channel IS NULL` thật vẫn được giữ lại, vì cờ `GROUPING` của chúng là `0`.

### 10.2. Chỉ lấy tổng phụ theo khu vực, không lấy tổng cộng

```sql
SELECT
    region,
    SUM(amount) AS revenue,
    GROUPING(region) AS g_region,
    GROUPING(channel) AS g_channel
FROM sales_demo
GROUP BY ROLLUP (region, channel)
HAVING GROUPING(region) = 0
   AND GROUPING(channel) = 1
ORDER BY region NULLS LAST;
```

Kết quả:

| region | revenue | g_region | g_channel |
| --- | ---: | ---: | ---: |
| Bắc | 200 | 0 | 1 |
| Nam | 100 | 0 | 1 |
| `NULL` | 40 | 0 | 1 |

Hàng `(NULL, 40, 0, 1)` là **tổng phụ của nhóm khu vực chưa biết**, không phải tổng cộng tất cả khu vực.

### 10.3. Chỉ lấy tổng cộng

```sql
SELECT
    SUM(amount) AS revenue,
    GROUPING(region, channel) AS grouping_mask
FROM sales_demo
GROUP BY ROLLUP (region, channel)
HAVING GROUPING(region) = 1
   AND GROUPING(channel) = 1;
```

Kết quả:

| revenue | grouping_mask |
| ---: | ---: |
| 340 | 3 |

Với bài toán chỉ cần tổng doanh thu, cách ngắn gọn hơn là:

```sql
SELECT SUM(amount) AS revenue
FROM sales_demo;
```

Nhưng khi đang xây báo cáo đa mức, `GROUPING` giúp tách đúng hàng tổng cộng trong cùng một phép tổng hợp.

### 10.4. Chỉ lấy các hàng có channel NULL thật

Khác hoàn toàn với việc lấy tổng phụ:

```sql
SELECT
    region,
    channel,
    SUM(amount) AS revenue
FROM sales_demo
GROUP BY ROLLUP (region, channel)
HAVING GROUPING(region) = 0
   AND GROUPING(channel) = 0
   AND channel IS NULL
ORDER BY region NULLS LAST;
```

Kết quả:

| region | channel | revenue |
| --- | --- | ---: |
| Bắc | `NULL` | 40 |
| Nam | `NULL` | 20 |
| `NULL` | `NULL` | 10 |

Hai điều kiện `GROUPING(...)=0` giữ **mức chi tiết**, còn `channel IS NULL` chọn giá trị kênh thiếu thực sự.

Chỉ viết:

```sql
HAVING channel IS NULL
```

sẽ còn nhận cả những hàng tổng phụ mà `channel` đã bị gộp bỏ, vì chúng cũng hiển thị `NULL`.

### 10.5. Lọc ngoài CTE bằng các cờ đã tính

Đôi khi dễ đọc hơn nếu tính cờ một lần:

```sql
WITH grouped_sales AS (
    SELECT
        region,
        channel,
        SUM(amount) AS revenue,
        GROUPING(region) AS g_region,
        GROUPING(channel) AS g_channel
    FROM sales_demo
    GROUP BY ROLLUP (region, channel)
)
SELECT
    region,
    revenue
FROM grouped_sales
WHERE g_region = 0
  AND g_channel = 1
ORDER BY region NULLS LAST;
```

Ở đây `WHERE` của **truy vấn ngoài** lọc những hàng tổng hợp đã được tạo trong CTE. Nó khác `WHERE` trực tiếp đặt trên `sales_demo` trước `GROUP BY`.

## 11. Vì sao WHERE column IS NULL có thể làm sai tổng?

Xét truy vấn:

```sql
SELECT
    region,
    channel,
    SUM(amount) AS revenue,
    GROUPING(channel) AS g_channel
FROM sales_demo
WHERE channel IS NULL
GROUP BY ROLLUP (region, channel);
```

`WHERE channel IS NULL` xảy ra trước tổng hợp, nên chỉ giữ **ba dòng dữ liệu gốc** có kênh thiếu:

| sale_id | region | channel | amount |
| ---: | --- | --- | ---: |
| 2 | Bắc | `NULL` | 40 |
| 5 | Nam | `NULL` | 20 |
| 7 | `NULL` | `NULL` | 10 |

Vì vậy **tổng cộng của truy vấn này chỉ là 70**, không phải tổng 340 của bảng gốc.

Đây không phải “chọn những hàng tổng phụ có kênh NULL”; đây là **lọc dữ liệu nguồn trước khi tạo tổng**.

Nếu muốn tổng phụ theo khu vực từ **mọi kênh**, phải dùng:

```sql
HAVING GROUPING(channel) = 1
   AND GROUPING(region) = 0
```

hoặc lọc các cờ sau khi chạy `ROLLUP` trong CTE.

### 11.1. Ba câu hỏi tương ứng ba truy vấn khác nhau

| Muốn biết | Phương án |
| --- | --- |
| Doanh thu của các bản ghi **không khai báo kênh** | `WHERE channel IS NULL` trước tổng hợp hoặc lọc hàng chi tiết có `GROUPING(channel)=0 AND channel IS NULL` |
| Doanh thu **mọi kênh theo từng khu vực** | `ROLLUP(region,channel)` rồi chọn `GROUPING(region)=0 AND GROUPING(channel)=1` |
| **Tổng doanh thu mọi khu vực, mọi kênh** | Chọn hàng có `GROUPING(region)=1 AND GROUPING(channel)=1` hoặc `SUM(amount)` toàn bảng |

Nếu báo cáo có ba chỉ số này, chúng phải được đặt **tên khác nhau**. Chỉ cùng hiển thị `NULL` ở một cột không đủ để kết luận chúng cùng ý nghĩa.

## 12. COUNT(*), COUNT(column) và NULL trong hàng tổng

`GROUPING` giải quyết việc nhận diện **mức tổng hợp**; nó không thay đổi quy tắc tính của các hàm tổng hợp.

Với bảng mẫu, xét:

```sql
SELECT
    region,
    channel,
    COUNT(*) AS source_rows,
    COUNT(channel) AS non_null_channel_rows,
    SUM(amount) AS revenue,
    GROUPING(region) AS g_region,
    GROUPING(channel) AS g_channel
FROM sales_demo
GROUP BY ROLLUP (region, channel)
ORDER BY
    GROUPING(region),
    region NULLS LAST,
    GROUPING(channel),
    channel NULLS LAST;
```

Các hàng đáng chú ý:

| Mức/nhóm | source_rows | non_null_channel_rows | revenue |
| --- | ---: | ---: | ---: |
| Chi tiết Bắc / Online | 1 | 1 | 100 |
| Chi tiết Bắc / kênh `NULL` thật | 1 | 0 | 40 |
| Tổng phụ Bắc / mọi kênh | 3 | 2 | 200 |
| Tổng phụ Nam / mọi kênh | 2 | 1 | 100 |
| Tổng phụ khu vực `NULL` thật / mọi kênh | 2 | 1 | 40 |
| Tổng cộng | 7 | 4 | 340 |

**Vì sao tổng phụ Bắc có `COUNT(channel)=2` mà `COUNT(*)=3`?** Vì có ba dòng bán hàng trong khu vực Bắc, nhưng một dòng có `channel IS NULL` nên `COUNT(channel)` bỏ qua dòng đó.

Không nên nhìn ô `channel = NULL` của hàng tổng phụ rồi kết luận `COUNT(channel)` phải bằng 0. `channel` ở đầu ra bị gộp bỏ; hàm `COUNT(channel)` vẫn tính theo các giá trị `channel` ở **những dòng nguồn của nhóm**, rồi loại các giá trị nguồn `NULL`.

### 12.1. COUNT(DISTINCT ...) cũng không thay GROUPING

`COUNT(DISTINCT channel)` đếm các giá trị kênh khác nhau và thường bỏ `NULL`. Nó không cho biết ô `channel` trong hàng hiện tại là `NULL` thật hay chỗ trống tổng phụ.

Ví dụ tổng phụ khu vực Bắc có hai kênh được xác định là Online và Store, nên `COUNT(DISTINCT channel) = 2`. Nhưng cờ `GROUPING(channel)=1` vẫn cần thiết để nhận diện hàng tổng phụ.

### 12.2. SUM trên tập rỗng và NULL của phép tổng

`SUM(amount)` có thể trả `NULL` trong một số trường hợp, chẳng hạn một nhóm không có giá trị không `NULL` phù hợp; `COUNT(*)` lại có thể trả 0. Đây là **`NULL` của giá trị tổng hợp**, khác với `NULL` ở cột chiều do `ROLLUP` tạo ra.

Trong dữ liệu mẫu, `amount` là `NOT NULL` và luôn có dòng nên các tổng đã trình bày đều là số. Trong hệ thống thực, cần phân biệt:

- `NULL` trong **cột nhóm**.
- `NULL` trong **kết quả hàm `SUM`**.
- `1` từ **`GROUPING`** khi một chiều bị gộp bỏ.

Ba ý nghĩa này không thể thay thế cho nhau.

## 13. Dùng mã mức nhóm để xây báo cáo có nhãn rõ ràng

Khi nhiều nhóm có thể mang `NULL` thật, cách thực tế là giữ cả:

- Giá trị chiều gốc.
- Các cờ `GROUPING` hoặc mã nhóm.
- Nhãn hiển thị.
- Số liệu tổng hợp.

Ví dụ:

```sql
WITH report_rows AS (
    SELECT
        region,
        channel,
        SUM(amount) AS revenue,
        GROUPING(region) AS g_region,
        GROUPING(channel) AS g_channel,
        GROUPING(region, channel) AS grouping_mask
    FROM sales_demo
    GROUP BY ROLLUP (region, channel)
)
SELECT
    CASE
        WHEN g_region = 1 THEN 'TẤT CẢ KHU VỰC'
        WHEN region IS NULL THEN 'CHƯA XÁC ĐỊNH KHU VỰC'
        ELSE region
    END AS region_label,
    CASE
        WHEN g_channel = 1 THEN 'TẤT CẢ KÊNH'
        WHEN channel IS NULL THEN 'CHƯA XÁC ĐỊNH KÊNH'
        ELSE channel
    END AS channel_label,
    CASE grouping_mask
        WHEN 0 THEN 'CHI_TIET'
        WHEN 1 THEN 'TONG_THEO_KHU_VUC'
        WHEN 3 THEN 'TONG_CONG'
        ELSE 'MUC_KHAC'
    END AS row_type,
    revenue,
    grouping_mask
FROM report_rows
ORDER BY
    g_region,
    region NULLS LAST,
    g_channel,
    channel NULLS LAST;
```

Kết quả có các thuộc tính hữu ích:

- `row_type = 'CHI_TIET'`: hàng chi tiết, kể cả khi có `NULL` thật.
- `row_type = 'TONG_THEO_KHU_VUC'`: tổng phụ theo khu vực.
- `row_type = 'TONG_CONG'`: tổng toàn bảng.
- `grouping_mask`: mã máy có thể dùng để lọc, định dạng hoặc kiểm tra.
- `region_label` và `channel_label`: chuỗi có ý nghĩa với người đọc.

Giữ `grouping_mask` hoặc các cờ trong dữ liệu trả về giúp frontend **không phải suy đoán loại hàng từ nhãn văn bản**. Đây là cách thiết kế đặc biệt hữu ích khi xuất Excel, JSON hoặc dữ liệu cho biểu đồ.

### 13.1. Đừng dùng mỗi nhãn làm khóa định danh

Nếu dữ liệu gốc thực sự có một khu vực tên `'TẤT CẢ KHU VỰC'`, tên nhãn có thể trùng với chuỗi do báo cáo tạo ra. Kể cả khi điều đó hiếm xảy ra, ứng dụng nên dùng **mức nhóm + giá trị gốc** để định danh hàng, không chỉ dùng chuỗi hiển thị.

Tương tự, hai khu vực có thể có tên hiển thị giống nhau nhưng mang ID khác nhau. Khi có thể, hãy nhóm theo khóa định danh ổn định và dùng tên để hiển thị.

## 14. Chọn mức nhóm bằng GROUPING cho biểu đồ và KPI

Giả sử muốn đưa kết quả `ROLLUP` vào hai thành phần giao diện:

1. Bảng chi tiết theo khu vực/kênh.
2. Ba thẻ tổng doanh thu theo khu vực.

Không nên đưa **tất cả 11 hàng** vào cùng một biểu đồ phân bổ doanh thu rồi cộng các giá trị trong biểu đồ: hàng tổng phụ và tổng cộng đã chứa dữ liệu của các hàng chi tiết, nên doanh thu sẽ bị **cộng trùng**.

### 14.1. Lấy riêng dữ liệu chi tiết

```sql
SELECT
    region,
    channel,
    SUM(amount) AS revenue
FROM sales_demo
GROUP BY ROLLUP (region, channel)
HAVING GROUPING(region, channel) = 0
ORDER BY region NULLS LAST, channel NULLS LAST;
```

Các hàng này phân chia doanh thu gốc thành bảy nhóm không trùng theo bộ chiều `(region, channel)`. Tổng doanh thu của chúng là **340**.

### 14.2. Lấy riêng dữ liệu tổng phụ theo khu vực

```sql
SELECT
    region,
    SUM(amount) AS revenue
FROM sales_demo
GROUP BY ROLLUP (region, channel)
HAVING GROUPING(region, channel) = 1
ORDER BY region NULLS LAST;
```

Các tổng phụ: Bắc `200`, Nam `100`, khu vực thiếu `40`. Tổng của ba mức **cùng cấp** này cũng là **340**.

### 14.3. Lấy riêng KPI tổng cộng

```sql
SELECT SUM(amount) AS revenue
FROM sales_demo;
-- 340
```

Hoặc nếu lấy từ kết quả `ROLLUP`, lọc `GROUPING(region, channel)=3`. Cách này phù hợp khi một truy vấn đa mức được dùng chung cho nhiều thành phần.

**Lưu ý báo cáo:** tổng của **tất cả các hàng từ ROLLUP** không phải doanh thu gốc. Với hai chiều trong ví dụ, mỗi dòng bán hàng đóng góp vào hàng chi tiết, hàng tổng phụ khu vực và hàng tổng cộng, nên tổng của tất cả giá trị `revenue` trong 11 hàng là **1.020** (`340 × 3`). Đó là đặc tính của báo cáo đa mức, không phải dữ liệu nguồn bị nhân ba.

## 15. Thứ tự các chiều trong ROLLUP quyết định mức tổng phụ

So sánh:

```sql
GROUP BY ROLLUP (region, channel)
```

với:

```sql
GROUP BY ROLLUP (channel, region)
```

Truy vấn thứ nhất tạo:

```text
(region, channel)  → chi tiết
(region)           → tổng theo khu vực
()                 → tổng cộng
```

Truy vấn thứ hai tạo:

```text
(channel, region)  → chi tiết
(channel)          → tổng theo kênh
()                 → tổng cộng
```

Ví dụ:

```sql
SELECT
    region,
    channel,
    SUM(amount) AS revenue,
    GROUPING(region) AS g_region,
    GROUPING(channel) AS g_channel
FROM sales_demo
GROUP BY ROLLUP (channel, region)
ORDER BY
    GROUPING(channel),
    channel NULLS LAST,
    GROUPING(region),
    region NULLS LAST;
```

Ở mức tổng phụ theo kênh:

| region | channel | revenue | g_region | g_channel |
| --- | --- | ---: | ---: | ---: |
| `NULL` | Online | 210 | 1 | 0 |
| `NULL` | Store | 60 | 1 | 0 |
| `NULL` | `NULL` | 70 | 1 | 0 |

Hàng `(NULL, NULL, 70)` là **tổng phụ của kênh chưa biết trên mọi khu vực**, khác với hàng `(NULL, NULL, 40)` của `ROLLUP(region, channel)`, vốn là **tổng phụ khu vực chưa biết trên mọi kênh**.

`GROUPING` luôn cho biết **chiều nào đang bị gộp bỏ** theo hàng kết quả, bất kể thứ tự các chiều của `ROLLUP`.

## 16. GROUPING với biểu thức, không chỉ tên cột

Đôi khi ta nhóm theo **một biểu thức**, chẳng hạn năm của ngày đặt hàng:

```sql
-- PostgreSQL, nếu có bảng orders với cột order_date:
SELECT
    EXTRACT(YEAR FROM order_date) AS order_year,
    SUM(amount) AS revenue,
    GROUPING(EXTRACT(YEAR FROM order_date)) AS g_year
FROM orders
GROUP BY ROLLUP (EXTRACT(YEAR FROM order_date));
```

Trong PostgreSQL, đối số của `GROUPING` phải **tương ứng với biểu thức dùng để phân nhóm**. Nếu nhóm theo `EXTRACT(YEAR FROM order_date)`, không được tự ý thay đối số bằng cột `order_date` rồi kỳ vọng có cùng ý nghĩa.

Trong nhiều tình huống, để tránh viết lặp biểu thức và dễ kiểm soát metadata, có thể tạo biểu thức phân nhóm trong CTE:

```sql
WITH normalized_orders AS (
    SELECT
        EXTRACT(YEAR FROM order_date) AS order_year,
        amount
    FROM orders
)
SELECT
    order_year,
    SUM(amount) AS revenue,
    GROUPING(order_year) AS g_year
FROM normalized_orders
GROUP BY ROLLUP (order_year);
```

Đây là truy vấn minh họa khi bảng `orders` có các cột `order_date` và `amount` phù hợp; nó **không yêu cầu** bảng mẫu `sales_demo` phải chứa những cột này.

### 16.1. Vì sao GROUPING(year) không phải IS NULL?

Nếu `order_date IS NULL`, biểu thức `EXTRACT(YEAR FROM order_date)` có thể thành `NULL` trong dữ liệu gốc. Khi tạo tổng cộng, chiều `order_year` lại bị gộp bỏ. Kết quả vẫn cần `GROUPING(order_year)` để phân biệt:

- Năm chưa biết trong dữ liệu (`g_year = 0`).
- Tổng tất cả năm (`g_year = 1`).

Cơ chế giống hệt ví dụ khu vực/kênh: một chiều nhóm có thể là **biểu thức tính toán** chứ không nhất thiết là cột thô.

## 17. Trường hợp dữ liệu rỗng và các hàm tổng

Với một tập dữ liệu nguồn không có hàng, các mức nhóm chi tiết và mức nhóm rỗng `()` có hành vi riêng theo ngữ nghĩa SQL:

- Nhóm theo một giá trị thực thường không tạo nhóm nếu không có hàng nguồn.
- Mức **tổng cộng không có chiều nhóm** có thể vẫn tạo một hàng tổng hợp toàn bộ đầu vào.
- Trong hàng tổng này, `COUNT(*)` là `0`; `SUM(amount)` thường trả `NULL` vì không có giá trị nào để cộng.

Có thể minh họa trên PostgreSQL:

```sql
SELECT
    COUNT(*) AS source_rows,
    SUM(amount) AS revenue,
    GROUPING(region) AS g_region
FROM sales_demo
WHERE 1 = 0
GROUP BY ROLLUP (region);
```

Mức tổng cộng `()` được biểu diễn bằng `g_region = 1` ngay cả khi không có dữ liệu. Điều đó cho thấy `GROUPING` phản ánh **mức nhóm được chọn**, không phản ánh có bao nhiêu hàng nguồn và cũng không phản ánh giá trị của `SUM`.

Khi hiển thị KPI “doanh thu bằng 0”, cần quyết định việc dùng `COALESCE(SUM(amount), 0)` có đúng nghiệp vụ không. Một tổng `NULL` do không có hàng có thể được trình bày thành 0 cho báo cáo, nhưng đó là **quy tắc hiển thị/số học**, không làm thay đổi ý nghĩa cờ `GROUPING`.

## 18. Khác biệt giữa các hệ quản trị SQL

Không phải DBMS nào cũng hỗ trợ cùng cú pháp `ROLLUP`, `CUBE`, `GROUPING SETS` và `GROUPING`.

| DBMS | Khả năng liên quan | Ghi chú |
| --- | --- | --- |
| **PostgreSQL** | `ROLLUP`, `CUBE`, `GROUPING SETS`, `GROUPING(...)` nhiều đối số | Ví dụ chính của bài; `GROUPING(...)` trả bitmask. |
| **SQL Server** | `ROLLUP`, `CUBE`, `GROUPING SETS`, `GROUPING(expr)`, `GROUPING_ID(...)` | `GROUPING_ID` dùng để nhận mã mức nhóm nhiều chiều. |
| **Oracle Database** | `ROLLUP`, `CUBE`, `GROUPING SETS`, `GROUPING(expr)`, `GROUPING_ID(...)` | Có các khả năng tổng hợp đa mức và những quy tắc riêng về cú pháp/kiểu. |
| **MySQL 8.x** | `WITH ROLLUP` và `GROUPING(...)` ở phiên bản hỗ trợ | Cú pháp `WITH ROLLUP` là dạng phổ biến; không nên giả định mọi tính năng `CUBE`/`GROUPING SETS` giống PostgreSQL. |
| **SQLite** | Không có `ROLLUP`/`CUBE`/`GROUPING` dựng sẵn trong SQL lõi | Có thể mô phỏng các mức bằng `UNION ALL` và cờ tự tạo. |

Khi chuyển SQL giữa các hệ, phải kiểm tra **cả tính năng và phiên bản**. Một cái tên giống nhau không bảo đảm mọi dạng biểu thức hoặc cú pháp sắp xếp đều tương đương.

### 18.1. PostgreSQL

```sql
SELECT
    region,
    channel,
    SUM(amount) AS revenue,
    GROUPING(region, channel) AS grouping_mask
FROM sales_demo
GROUP BY ROLLUP (region, channel);
```

PostgreSQL hỗ trợ cả cú pháp tổng hợp đa mức và nhiều đối số trong `GROUPING`. Các cờ có thể dùng trong `SELECT`/`HAVING`/`ORDER BY` phù hợp với ngữ cảnh nhóm.

### 18.2. SQL Server

Ví dụ T-SQL:

```sql
SELECT
    region,
    channel,
    SUM(amount) AS revenue,
    GROUPING(region) AS g_region,
    GROUPING(channel) AS g_channel,
    GROUPING_ID(region, channel) AS grouping_mask
FROM dbo.sales_demo
GROUP BY ROLLUP (region, channel);
```

`GROUPING_ID(region, channel)` trả mã mức nhóm tương ứng với các cờ `GROUPING`. Chú ý `dbo.sales_demo` chỉ là cách gọi bảng trong một schema SQL Server; bảng mẫu ở mục 3 được viết theo PostgreSQL nên không cần giả định nó đã tồn tại trên SQL Server.

### 18.3. MySQL

Trong MySQL 8.x có hỗ trợ `GROUPING` tương ứng, cú pháp tổng phụ quen thuộc là:

```sql
SELECT
    region,
    channel,
    SUM(amount) AS revenue,
    GROUPING(region) AS g_region,
    GROUPING(channel) AS g_channel
FROM sales_demo
GROUP BY region, channel WITH ROLLUP;
```

Khả năng `GROUPING` và các giới hạn đối số phụ thuộc phiên bản MySQL. Một số phiên bản MySQL cũ hỗ trợ `WITH ROLLUP` nhưng không cung cấp cách dùng `GROUPING` như MySQL hiện đại; khi ấy phân biệt `NULL` gốc với `NULL` tổng phụ khó hơn nếu chỉ dựa trên truy vấn này.

Không dùng `region IS NULL` để nhận diện hàng tổng trong MySQL nếu dữ liệu có thể chứa `NULL` thật: **bẫy ngữ nghĩa vẫn như nhau**.

### 18.4. Oracle Database

Oracle hỗ trợ `GROUPING_ID`:

```sql
SELECT
    region,
    channel,
    SUM(amount) AS revenue,
    GROUPING(region) AS g_region,
    GROUPING(channel) AS g_channel,
    GROUPING_ID(region, channel) AS grouping_mask
FROM sales_demo
GROUP BY ROLLUP (region, channel);
```

Có thể dùng cờ để đổi nhãn hoặc tách các mức báo cáo. Cần lưu ý quy tắc kiểu chuỗi, cách trình bày `NULL` và cú pháp DBMS khi chuyển ví dụ từ PostgreSQL sang Oracle.

### 18.5. SQLite: mô phỏng bằng UNION ALL

SQLite không hỗ trợ trực tiếp `GROUPING` và `ROLLUP` trong SQL lõi. Nếu cần một báo cáo tương đương `ROLLUP(region, channel)`, ta có thể **tạo từng mức riêng** rồi gộp bằng `UNION ALL`.

```sql
-- SQLite: giả định sales_demo đã được tạo với dữ liệu tương tự.
SELECT region, channel, SUM(amount) AS revenue,
       0 AS g_region, 0 AS g_channel
FROM sales_demo
GROUP BY region, channel

UNION ALL

SELECT region, NULL AS channel, SUM(amount) AS revenue,
       0 AS g_region, 1 AS g_channel
FROM sales_demo
GROUP BY region

UNION ALL

SELECT NULL AS region, NULL AS channel, SUM(amount) AS revenue,
       1 AS g_region, 1 AS g_channel
FROM sales_demo;
```

Các cờ `0`/`1` trong truy vấn này được **tự gán theo mức nhóm**, không phải trả về từ hàm `GROUPING`.

**Vì sao dùng `UNION ALL` thay cho `UNION`?** Vì một số hàng ở các mức khác nhau có thể giống nhau về giá trị hiển thị. `UNION` có chức năng loại bản ghi trùng và có thể làm mất các hàng nếu người viết không mang đủ cờ/mức nhóm; `UNION ALL` phản ánh trực tiếp việc nối các tập nhóm và giữ mọi hàng mong muốn.

Đây là phương án mô phỏng cho hệ không hỗ trợ tính năng tổng hợp đa mức, không nhất thiết tối ưu giống một phép `ROLLUP` dựng sẵn.

## 19. Chi phí và thiết kế báo cáo đa mức

`ROLLUP`, `CUBE` và `GROUPING SETS` rất tiện khi muốn tạo nhiều mức tổng từ cùng một nguồn. Tuy nhiên, cần cân nhắc số chiều.

Với `n` chiều:

- `ROLLUP(a, b, c, ...)` tạo một chuỗi **n + 1 grouping set** theo tiền tố, trong trường hợp liệt kê đơn giản.
- `CUBE` trên `n` chiều tạo **2^n grouping set**.
- `GROUPING SETS` cho phép liệt kê thủ công những mức cần thiết.

Ví dụ `CUBE` trên 2 chiều có 4 grouping set, trên 5 chiều có 32 grouping set. Số **hàng kết quả** có thể còn lớn hơn nhiều vì mỗi grouping set tạo nhiều nhóm tùy giá trị thực tế.

### 19.1. Hạn chế tạo quá nhiều mức không dùng

Nếu dashboard chỉ cần:

- Doanh thu theo khu vực/kênh.
- Tổng theo khu vực.
- Tổng cộng.

thì `ROLLUP(region, channel)` là lựa chọn tự nhiên. Không nhất thiết dùng `CUBE` để tạo thêm tổng kênh nếu chúng không xuất hiện ở màn hình.

Nếu cần một số tập mức không theo thứ tự phân cấp, `GROUPING SETS` giúp chỉ định chính xác.

### 19.2. Đừng cộng các hàng thuộc mức khác nhau

Với dữ liệu mẫu, tổng doanh thu gốc là `340`. Nhưng nếu cộng tất cả 11 giá trị `revenue` từ `ROLLUP(region, channel)`, ta được `1.020` vì mỗi dòng nguồn được tính vào ba mức báo cáo.

Để hiển thị đúng tổng:

- Chọn **hàng tổng cộng duy nhất**.
- Hoặc cộng các hàng ở **một mức nhóm duy nhất** tạo thành phân hoạch không chồng lặp, ví dụ các hàng chi tiết.
- Không cộng bừa chi tiết + tổng phụ + tổng cộng.

Các cờ `GROUPING` rất hữu ích để phòng lỗi cộng trùng này trong code báo cáo.

### 19.3. Chỉ mục và kế hoạch thực thi

Hiệu năng còn phụ thuộc dữ liệu, chỉ mục, bộ tối ưu và mức tổng cần tạo. Một câu `ROLLUP` có thể tiện hơn nhiều truy vấn riêng, nhưng không có bảo đảm phổ quát rằng nó luôn nhanh hơn mọi phương án khác.

Ưu tiên xây đúng tập mức và ngữ nghĩa `NULL` trước, sau đó mới quan sát kế hoạch thực thi (`EXPLAIN` trên PostgreSQL hoặc công cụ tương ứng) với dữ liệu thực tế.

## 20. Những lỗi dễ mắc

| Lỗi | Vì sao sai | Cách sửa |
| --- | --- | --- |
| Xem mọi `NULL` trong `ROLLUP` là tổng cộng | `NULL` có thể đến từ bản ghi gốc | Dùng `GROUPING(column)` |
| Dùng `COALESCE(region, 'TOTAL')` để gắn nhãn | Gộp nhãn khu vực thiếu với tổng tất cả khu vực | `CASE WHEN GROUPING(region)=1 ... WHEN region IS NULL ...` |
| Cho rằng `GROUPING(column)=0` nghĩa là không có `NULL` | `0` chỉ cho biết chiều vẫn được phân nhóm | Kiểm tra `column IS NULL` riêng nếu cần |
| Dùng `WHERE channel IS NULL` để chọn hàng tổng phụ | `WHERE` lọc dữ liệu nguồn trước khi tạo tổng | Dùng `HAVING GROUPING(channel)=1` hoặc lọc CTE |
| Dùng `HAVING channel IS NULL` mà không kiểm tra cờ | Có thể lấy cả chi tiết `NULL` thật và tổng phụ | Kết hợp `GROUPING(channel)` |
| Nhầm `ROLLUP(region, channel)` có tổng theo kênh | `ROLLUP` theo tiền tố nên chỉ tạo tổng theo khu vực | Dùng `CUBE`, đảo thứ tự `ROLLUP` hoặc `GROUPING SETS` |
| Tính mã bitmask nhưng không quan tâm thứ tự đối số | Trọng số bit thay đổi khi đổi thứ tự | Ghi rõ quy ước `GROUPING(region,channel)` |
| Cộng tất cả hàng của `ROLLUP` | Mỗi dòng nguồn bị tính ở nhiều mức | Chọn một mức báo cáo bằng cờ nhóm |
| Cho rằng `COUNT(channel)=COUNT(*)` ở hàng tổng phụ | `COUNT(channel)` bỏ qua `NULL` của dữ liệu nguồn | Chọn hàm đếm đúng yêu cầu |
| Sao chép `GROUPING_ID` từ SQL Server sang PostgreSQL | Tên hàm không giống nhau | PostgreSQL dùng `GROUPING(...)` nhiều đối số |
| Không dùng `ORDER BY` ở kết quả cuối | Thứ tự các mức không được đảm bảo | Sắp theo cờ nhóm và khóa chiều |
| Nhầm `NULL` của `SUM` với `NULL` của chiều nhóm | Chúng có nguyên nhân và ý nghĩa khác nhau | Đọc kiểu biểu thức và cờ nhóm riêng |

## 21. Bài tập thực hành và lời giải

Sử dụng bảng `sales_demo` được tạo ở mục 3. Các bài từ 1 đến 9 minh họa cú pháp PostgreSQL.

### Bài 1. Tìm hàng chi tiết mà cả hai chiều đều NULL thật

**Yêu cầu:** Trên kết quả `ROLLUP(region, channel)`, chỉ lấy hàng mà `region` và `channel` đều `NULL` từ dữ liệu gốc.

```sql
SELECT
    region,
    channel,
    SUM(amount) AS revenue
FROM sales_demo
GROUP BY ROLLUP (region, channel)
HAVING GROUPING(region, channel) = 0
   AND region IS NULL
   AND channel IS NULL;
```

**Đáp án:** một hàng có `revenue = 10`. Cờ `GROUPING(...)=0` chứng minh cả hai chiều vẫn là chiều nhóm.

### Bài 2. Vì sao có hai hàng Bắc / NULL?

Xét `ROLLUP(region, channel)`:

| region | channel | revenue |
| --- | --- | ---: |
| Bắc | `NULL` | 40 |
| Bắc | `NULL` | 200 |

**Câu hỏi:** Hàng nào là tổng phụ?

**Đáp án:** hàng doanh thu `200` có `GROUPING(channel)=1`, vì nó gộp các kênh Online, Store và kênh chưa xác định. Hàng doanh thu `40` có `GROUPING(channel)=0` và là nhóm dữ liệu kênh `NULL` thật.

### Bài 3. Đọc bitmask

Với `GROUPING(region, channel)`, hãy giải thích các mã `0`, `1`, `2`, `3`.

**Đáp án:**

- `0`: chi tiết theo cả hai chiều.
- `1`: tổng phụ khu vực (bỏ kênh).
- `2`: tổng phụ kênh (bỏ khu vực).
- `3`: tổng cộng toàn bộ.

`ROLLUP(region, channel)` không tự tạo mã `2`; `CUBE` tạo đủ bốn mã.

### Bài 4. Tìm đúng ba tổng phụ theo khu vực

```sql
SELECT region, SUM(amount) AS revenue
FROM sales_demo
GROUP BY ROLLUP (region, channel)
HAVING GROUPING(region) = 0
   AND GROUPING(channel) = 1
ORDER BY region NULLS LAST;
```

**Đáp án:** Bắc `200`, Nam `100`, khu vực `NULL` thật `40`.

### Bài 5. Lấy tổng cộng 340 từ ROLLUP

```sql
SELECT SUM(amount) AS revenue
FROM sales_demo
GROUP BY ROLLUP (region, channel)
HAVING GROUPING(region, channel) = 3;
```

**Đáp án:** một hàng, `revenue = 340`.

### Bài 6. Lấy tổng phụ của kênh chưa xác định trong CUBE

**Yêu cầu:** Chọn doanh thu của các bản ghi có `channel IS NULL` trên **tất cả khu vực** từ `CUBE(region, channel)`.

```sql
SELECT
    region,
    channel,
    SUM(amount) AS revenue,
    GROUPING(region, channel) AS grouping_mask
FROM sales_demo
GROUP BY CUBE (region, channel)
HAVING GROUPING(region) = 1
   AND GROUPING(channel) = 0
   AND channel IS NULL;
```

**Đáp án:** `region = NULL` (do đã gộp khu vực), `channel = NULL` (kênh chưa biết thật), `revenue = 70`, mã nhóm `2`.

Nếu thay `GROUPING(channel)=0` bằng `1`, ta sẽ chọn **tổng cộng toàn bảng** chứ không phải nhóm kênh thiếu.

### Bài 7. Phân biệt bốn hàng NULL/NULL của CUBE

**Yêu cầu:** Điền tên mức cho bốn hàng:

| revenue | grouping_mask | Mức cần nhận diện |
| ---: | ---: | --- |
| 10 | 0 | ? |
| 40 | 1 | ? |
| 70 | 2 | ? |
| 340 | 3 | ? |

**Đáp án:**

- `10`: chi tiết cả khu vực và kênh đều không xác định.
- `40`: tổng phụ khu vực không xác định, mọi kênh.
- `70`: tổng phụ kênh không xác định, mọi khu vực.
- `340`: tổng cộng mọi khu vực, mọi kênh.

### Bài 8. Gắn nhãn bằng CASE

**Yêu cầu:** Khi cột `region` là `NULL`, gắn:

- `TẤT CẢ KHU VỰC` nếu là tổng cộng.
- `CHƯA XÁC ĐỊNH` nếu là dữ liệu thật.

```sql
SELECT
    CASE
        WHEN GROUPING(region) = 1 THEN 'TẤT CẢ KHU VỰC'
        WHEN region IS NULL THEN 'CHƯA XÁC ĐỊNH'
        ELSE region
    END AS region_label,
    SUM(amount) AS revenue,
    GROUPING(region) AS g_region
FROM sales_demo
GROUP BY ROLLUP (region)
ORDER BY GROUPING(region), region NULLS LAST;
```

**Đáp án:** nhãn `CHƯA XÁC ĐỊNH` đi cùng tổng `40`; nhãn `TẤT CẢ KHU VỰC` đi cùng tổng `340`.

### Bài 9. Đếm số dòng nguồn của hàng tổng phụ Bắc

```sql
SELECT
    region,
    COUNT(*) AS row_count,
    COUNT(channel) AS known_channel_count
FROM sales_demo
GROUP BY ROLLUP (region, channel)
HAVING GROUPING(region) = 0
   AND GROUPING(channel) = 1
   AND region = 'Bắc';
```

**Đáp án:** `row_count = 3` nhưng `known_channel_count = 2`, vì một dòng Bắc có `channel IS NULL`.

### Bài 10. Nếu DBMS không có GROUPING thì sao?

**Yêu cầu:** Giải thích cách mô phỏng mức `ROLLUP(region, channel)` trên SQLite.

**Gợi ý đáp án:** Dùng ba truy vấn:

1. `GROUP BY region, channel` với cờ `(0,0)`.
2. `GROUP BY region` với cờ `(0,1)`.
3. Tổng không `GROUP BY` với cờ `(1,1)`.

Nối bằng `UNION ALL`, giữ cờ ngay trong kết quả. Đừng nhìn `IS NULL` để đoán mức tổng.

## 22. Ghi nhớ để không nhầm NULL dữ liệu và NULL của tổng phụ

Khi viết báo cáo đa mức, hãy trả lời lần lượt:

1. **Giá trị `NULL` này có thể đã có ở dữ liệu gốc không?** Nếu cột nhóm cho phép `NULL`, câu trả lời có thể là có.
2. **Hàng này thuộc tập cột nhóm nào?** `GROUPING(column)=0` nghĩa là chiều còn tham gia phân nhóm; `1` nghĩa là chiều đã bị gộp bỏ.
3. **Cần xem chi tiết, tổng phụ hay tổng cộng?** Dùng cờ `GROUPING` hoặc mã nhiều chiều để lọc chính xác.
4. **Có cần nhãn hiển thị không?** Dùng `CASE` kiểm tra `GROUPING` trước, sau đó mới kiểm tra `IS NULL` của giá trị thật.
5. **Số liệu có bị cộng trùng vì trộn các mức tổng không?** Không cộng tất cả hàng từ `ROLLUP`/`CUBE` để lấy tổng toàn bảng.
6. **Đang chạy phương ngữ nào?** PostgreSQL có `GROUPING(...)` nhiều đối số; SQL Server và Oracle có `GROUPING_ID`; MySQL thường dùng `WITH ROLLUP`; SQLite cần mô phỏng nếu không có hàm.

**Nguyên tắc cốt lõi:** `GROUPING(column)` **không kiểm tra một giá trị có phải `NULL` hay không**. Nó kiểm tra liệu chiều phân nhóm đã được **gộp bỏ ở mức tổng hợp hiện tại**. Nhờ phân biệt rõ `GROUPING(column)=0` và `GROUPING(column)=1`, bạn có thể xây báo cáo tổng hợp đúng, đọc chính xác các hàng có `NULL` và tránh gắn nhầm dữ liệu thiếu thành tổng phụ hay tổng cộng.
