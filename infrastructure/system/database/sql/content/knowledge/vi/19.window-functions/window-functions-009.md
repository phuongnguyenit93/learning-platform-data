# Biên cửa sổ, khung mặc định và ảnh hưởng của hàng đồng hạng

Khi học hàm cửa sổ (*window functions*) trong SQL, nhiều người đã quen với `OVER (PARTITION BY ... ORDER BY ...)` nhưng lại bỏ qua một thành phần quyết định kết quả: **khung cửa sổ** (*window frame*). Chỉ cần bảng có **hai hàng cùng giá trị sắp xếp**, một phép `SUM` tích lũy có thể nhảy ngay từ 100 lên 220 trên **cả hai hàng đồng ngày**, thay vì tăng lần lượt 150 rồi 220 như người viết mong đợi.

Một bẫy khác xuất hiện với `LAST_VALUE`. Tên hàm khiến ta nghĩ nó luôn trả “giá trị ở hàng cuối của cả nhóm”, nhưng với khung mặc định có `ORDER BY`, nó thường trả giá trị ở **hàng cuối của khung hiện tại** — không phải hàng cuối của toàn bộ phân hoạch.

Bài học thuộc **Database SQL → Hàm cửa sổ → Biên cửa sổ, khung mặc định và ảnh hưởng của hàng đồng hạng**. Chúng ta sẽ phân biệt:

- **Phân hoạch** (*partition*): nhóm hàng mà hàm cửa sổ làm việc.
- **Thứ tự cửa sổ** (*window ordering*): thứ tự logic của các hàng trong phân hoạch.
- **Khung cửa sổ** (*frame*): tập con của phân hoạch mà một số hàm sử dụng khi tính cho từng hàng.
- **Hàng đồng hạng** (*peer rows*): các hàng có cùng giá trị của mọi biểu thức `ORDER BY` trong định nghĩa cửa sổ.
- **Biên khung** (*frame bounds*): điểm bắt đầu và điểm kết thúc như `UNBOUNDED PRECEDING`, `CURRENT ROW` và `1 FOLLOWING`.

Các truy vấn thực hành chủ yếu sử dụng **PostgreSQL**. Các quy tắc cụ thể về mặc định, tùy chọn khung và hỗ trợ cú pháp cần được kiểm tra khi chuyển sang DBMS khác.

## 1. Ba cấp độ cần phân biệt: partition, ordering và frame

Cấu trúc đầy đủ có thể có dạng:

```sql
window_function(...) OVER (
    PARTITION BY partition_expression
    ORDER BY sort_expression
    ROWS BETWEEN frame_start AND frame_end
)
```

Ba phần trong `OVER` có nhiệm vụ khác nhau:

| Thành phần | Trả lời câu hỏi | Ví dụ |
| --- | --- | --- |
| `PARTITION BY region` | Những hàng nào thuộc cùng nhóm tính toán? | Mỗi khu vực được tính riêng |
| `ORDER BY sold_on` | Các hàng trong nhóm được sắp xếp logic thế nào? | Theo ngày bán |
| `ROWS BETWEEN ... AND ...` | Với hàng hiện tại, những hàng nào nằm trong khung tính? | Từ đầu nhóm tới hàng hiện tại |

Ví dụ:

```sql
SUM(amount) OVER (
    PARTITION BY region
    ORDER BY sold_on, sale_id
    ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
)
```

có ý nghĩa: với mỗi hàng bán, lấy tất cả hàng **cùng khu vực**, sắp xếp theo ngày rồi theo mã giao dịch để không còn hòa, cộng tiền từ **đầu khu vực đến đúng hàng này**.

Nhưng nếu bỏ phần `ROWS BETWEEN ...`, PostgreSQL dùng **khung mặc định**, và điều đó có thể tạo kết quả khác khi có hàng cùng `sold_on`.

### Hình dung ba lớp

```text
Toàn bộ bảng
  ├── partition North
  │     ├── 2026-03-01: sale 1
  │     ├── 2026-03-02: sale 2, sale 3  ← cùng ngày, là peers
  │     ├── 2026-03-04: sale 4
  │     └── 2026-03-05: sale 5, sale 6  ← cùng ngày, là peers
  └── partition South
        ├── 2026-03-01: sale 7, sale 8
        ├── 2026-03-03: sale 9
        └── 2026-03-06: sale 10

Ở sale 2, khung có thể là:
  ROWS từ đầu đến hàng thứ 2:          sale 1, sale 2
  RANGE mặc định theo sold_on:          sale 1, sale 2, sale 3
  GROUPS gồm nhóm ngày hiện tại:        sale 2, sale 3
```

Điểm mấu chốt: **khung là tập con phụ thuộc hàng đang được tính**, không phải lúc nào cũng trùng toàn bộ phân hoạch.

## 2. Dữ liệu thực hành: giao dịch trùng ngày và giá trị NULL

Mở một phiên **PostgreSQL thực hành** rồi tạo bảng tạm sau:

```sql
CREATE TEMP TABLE window_frames_lab (
    sale_id INTEGER PRIMARY KEY,
    region  TEXT NOT NULL,
    sold_on DATE NOT NULL,
    amount  NUMERIC(10, 2)
);

INSERT INTO window_frames_lab (sale_id, region, sold_on, amount)
VALUES
    (1,  'North', DATE '2026-03-01', 100.00),
    (2,  'North', DATE '2026-03-02',  50.00),
    (3,  'North', DATE '2026-03-02',  70.00),
    (4,  'North', DATE '2026-03-04',   NULL),
    (5,  'North', DATE '2026-03-05',  20.00),
    (6,  'North', DATE '2026-03-05',   0.00),
    (7,  'South', DATE '2026-03-01',  40.00),
    (8,  'South', DATE '2026-03-01',  60.00),
    (9,  'South', DATE '2026-03-03',  90.00),
    (10, 'South', DATE '2026-03-06',   NULL);

SELECT sale_id, region, sold_on, amount
FROM window_frames_lab
ORDER BY region, sold_on, sale_id;
```

Đây là **bảng tạm**, tồn tại trong phiên kết nối. Nếu đã tạo cùng tên, hãy dùng phiên mới hoặc đổi tên trước khi chạy lại.

Các nhóm dữ liệu:

| Khu vực | Ngày | Giao dịch | Số tiền |
| --- | --- | --- | --- |
| North | 2026-03-01 | 1 | 100 |
| North | 2026-03-02 | 2, 3 | 50, 70 |
| North | 2026-03-04 | 4 | `NULL` |
| North | 2026-03-05 | 5, 6 | 20, 0 |
| South | 2026-03-01 | 7, 8 | 40, 60 |
| South | 2026-03-03 | 9 | 90 |
| South | 2026-03-06 | 10 | `NULL` |

Tổng tiền đã biết của North là **240**, của South là **190**. Giá trị `NULL` nghĩa là số tiền chưa được xác định, không phải số 0; còn giao dịch 6 có số tiền **0 thật**.

Các ngày trùng nhau được đưa vào có chủ đích để minh họa **hàng đồng hạng**.

## 3. Hàng đồng hạng (peers) được xác định thế nào?

Hai hàng là **peers** nếu chúng có cùng giá trị theo **toàn bộ danh sách biểu thức `ORDER BY` của cửa sổ**.

Ví dụ:

```sql
OVER (
    PARTITION BY region
    ORDER BY sold_on
)
```

Trong North:

- Sale 2 và sale 3 là peers, vì cùng `sold_on = 2026-03-02`.
- Sale 5 và sale 6 là peers, vì cùng `sold_on = 2026-03-05`.
- Sale 1 và sale 4 không đồng hạng với hàng nào khác trong North.

Trong South, sale 7 và sale 8 là peers.

### Peer phụ thuộc đủ các khóa sắp xếp

Nếu thêm khóa thứ hai:

```sql
OVER (
    PARTITION BY region
    ORDER BY sold_on, sale_id
)
```

thì sale 2 và sale 3 **không còn là peers**, do `sale_id` khác nhau. Mỗi giao dịch trong bảng mẫu có khóa chính riêng, nên không còn hai hàng hòa khi xét cặp `(sold_on, sale_id)`.

Điều này vừa làm thứ tự xác định hơn, vừa **thay đổi nhóm peers** — vì thế cũng có thể thay đổi khung `RANGE`/`GROUPS` và các hàm như `RANK`.

### Peer không đồng nghĩa trùng toàn bộ hàng

Sale 2 và sale 3 khác `sale_id` và `amount`, nhưng vẫn là peers khi cửa sổ chỉ `ORDER BY sold_on`. Những cột không xuất hiện trong `ORDER BY` của cửa sổ **không tham gia xác định peer**.

Cũng đừng nhầm hàng đồng hạng với các hàng cùng `region`. `PARTITION BY region` xác định phạm vi lớn hơn; trong mỗi phân hoạch có thể có **nhiều nhóm đồng hạng**.

## 4. Khung mặc định của PostgreSQL: có ORDER BY và không ORDER BY

Đây là quy tắc quan trọng nhất của bài.

### 4.1. Có ORDER BY nhưng không viết frame

Trong PostgreSQL, với một hàm cửa sổ sử dụng khung, nếu có `ORDER BY` và không chỉ rõ khung, mặc định về ý nghĩa là:

```sql
RANGE BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
```

Khung bắt đầu ở **đầu phân hoạch**, kết thúc tại **hàng đồng hạng cuối cùng của hàng hiện tại** theo `ORDER BY`.

Từ khóa `CURRENT ROW` trong chế độ `RANGE` **không đơn giản chỉ là hàng vật lý hiện tại**. Nó bao gồm nhóm peers tại biên.

Ví dụ:

```sql
SUM(amount) OVER (
    PARTITION BY region
    ORDER BY sold_on
)
```

tương đương về khung với:

```sql
SUM(amount) OVER (
    PARTITION BY region
    ORDER BY sold_on
    RANGE BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
)
```

Khi chạy ở sale 2 (ngày 02-03), khung chứa **cả sale 2 và sale 3** cùng ngày, dù sale 3 có thể đứng sau sale 2 trong thứ tự hiển thị.

### 4.2. Không có ORDER BY trong OVER

Khi không có `ORDER BY`, các hàng trong một phân hoạch cùng thuộc **một nhóm peers**. Khung mặc định vì vậy bao phủ **toàn bộ phân hoạch**.

```sql
SELECT
    sale_id,
    region,
    amount,
    SUM(amount) OVER (
        PARTITION BY region
    ) AS region_total
FROM window_frames_lab
ORDER BY region, sold_on, sale_id;
```

Mọi hàng North đều có `region_total = 240`; mọi hàng South có `region_total = 190`.

Nếu bỏ cả `PARTITION BY` và `ORDER BY`:

```sql
SUM(amount) OVER ()
```

thì toàn bộ tập kết quả đi vào **một phân hoạch**, và tổng của bảng mẫu là **430** cho mỗi hàng.

### 4.3. ORDER BY bên ngoài không thay đổi frame

So sánh:

```sql
SELECT sale_id,
       SUM(amount) OVER (
           PARTITION BY region
           ORDER BY sold_on
       ) AS running_total
FROM window_frames_lab
ORDER BY sale_id DESC;
```

`ORDER BY sale_id DESC` ở cuối câu chỉ thay đổi **thứ tự trình bày các hàng kết quả**. Nó không biến thứ tự khung thành giảm dần theo `sale_id`. Muốn đổi logic tính cửa sổ phải sửa `ORDER BY` **bên trong `OVER`**.

## 5. Minh họa bẫy tổng tích lũy nhảy bậc khi trùng ngày

Chạy:

```sql
SELECT
    sale_id,
    region,
    sold_on,
    amount,
    SUM(amount) OVER (
        PARTITION BY region
        ORDER BY sold_on
    ) AS sum_default
FROM window_frames_lab
ORDER BY region, sold_on, sale_id;
```

Kết quả của bảng mẫu:

| `sale_id` | `region` | `sold_on` | `amount` | `sum_default` |
| ---: | --- | --- | ---: | ---: |
| 1 | North | 03-01 | 100 | 100 |
| 2 | North | 03-02 | 50 | 220 |
| 3 | North | 03-02 | 70 | 220 |
| 4 | North | 03-04 | `NULL` | 220 |
| 5 | North | 03-05 | 20 | 240 |
| 6 | North | 03-05 | 0 | 240 |
| 7 | South | 03-01 | 40 | 100 |
| 8 | South | 03-01 | 60 | 100 |
| 9 | South | 03-03 | 90 | 190 |
| 10 | South | 03-06 | `NULL` | 190 |

Ngày hiển thị rút gọn là tháng-ngày của năm 2026.

### Vì sao sale 2 đã có tổng 220?

North đến ngày 03-02 có:

```text
03-01: sale 1 = 100
03-02: sale 2 =  50
       sale 3 =  70
-------------------
Tổng tới hết nhóm ngày 03-02 = 220
```

Với `RANGE ... CURRENT ROW`, khung của sale 2 và sale 3 đều kết thúc tại **cuối nhóm ngày 03-02**. Vì vậy cả hai cùng nhận 220.

Tương tự, South có hai giao dịch ngày 03-01: `40 + 60 = 100`, nên **cả sale 7 và sale 8** đã có tổng 100.

Đây không phải DBMS đếm trùng; đó là **ngữ nghĩa của khung theo nhóm peers**.

### Lý do sale 4 không làm thay đổi tổng

Sale 4 có `amount = NULL`. `SUM` bỏ qua các giá trị `NULL`, nên tổng North vẫn là 220. Nó vẫn là một **hàng trong khung**, nhưng không cộng một số tiền mới.

Nếu dùng `COUNT(*)`, sale 4 vẫn được đếm. Nếu dùng `COUNT(amount)`, sale 4 không đóng góp vào số lượng giá trị đã biết.

## 6. Muốn cộng tích lũy từng hàng: dùng ROWS và khóa phá hòa

Khi mục tiêu là tổng tăng sau **từng giao dịch riêng biệt**, hãy chọn thứ tự xác định bằng khóa phụ và ghi rõ `ROWS`:

```sql
SELECT
    sale_id,
    region,
    sold_on,
    amount,
    SUM(amount) OVER (
        PARTITION BY region
        ORDER BY sold_on, sale_id
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS sum_by_row
FROM window_frames_lab
ORDER BY region, sold_on, sale_id;
```

Kết quả:

| `sale_id` | `region` | `amount` | `sum_by_row` |
| ---: | --- | ---: | ---: |
| 1 | North | 100 | 100 |
| 2 | North | 50 | 150 |
| 3 | North | 70 | 220 |
| 4 | North | `NULL` | 220 |
| 5 | North | 20 | 240 |
| 6 | North | 0 | 240 |
| 7 | South | 40 | 40 |
| 8 | South | 60 | 100 |
| 9 | South | 90 | 190 |
| 10 | South | `NULL` | 190 |

Khung `ROWS` đếm **vị trí hàng** theo thứ tự cửa sổ, không tự mở rộng để bao gồm tất cả peers ở cùng mốc sắp xếp.

### Nếu chỉ ROWS nhưng vẫn ORDER BY sold_on thì sao?

Ví dụ:

```sql
SUM(amount) OVER (
    PARTITION BY region
    ORDER BY sold_on
    ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
)
```

Khung sẽ dừng ở một hàng cụ thể trong thứ tự xử lý. Nhưng sale 2 và sale 3 có cùng `sold_on` nên **thứ tự giữa chúng không được bảo đảm**. Tùy kế hoạch, có thể tính 50 trước 70 hoặc ngược lại, khiến hai tổng trung gian khác nhau.

Vì vậy, nếu cần kết quả lũy kế ổn định **theo từng giao dịch**, hãy thêm khóa phá hòa như `sale_id` vào `ORDER BY` **bên trong cửa sổ**, không chỉ ở `ORDER BY` cuối truy vấn.

### So sánh hai kết quả trong cùng câu SQL

```sql
SELECT
    sale_id,
    region,
    sold_on,
    amount,
    SUM(amount) OVER (
        PARTITION BY region
        ORDER BY sold_on
    ) AS sum_by_day_group,
    SUM(amount) OVER (
        PARTITION BY region
        ORDER BY sold_on, sale_id
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS sum_by_transaction
FROM window_frames_lab
ORDER BY region, sold_on, sale_id;
```

Với sale 2, `sum_by_day_group = 220` còn `sum_by_transaction = 150`. Hai biểu thức trả lời **hai câu hỏi khác nhau**:

- Tổng đến **hết ngày** của giao dịch.
- Tổng đến **chính giao dịch đó** trong một thứ tự xác định.

## 7. Cú pháp và ý nghĩa của các biên khung

Một khai báo đầy đủ có dạng:

```sql
ROWS | RANGE | GROUPS
BETWEEN frame_start AND frame_end
```

Trong đó các mốc phổ biến gồm:

| Biên | Ý nghĩa trực giác |
| --- | --- |
| `UNBOUNDED PRECEDING` | Từ đầu phân hoạch |
| `n PRECEDING` | Lùi lại n hàng, n nhóm peers hoặc một khoảng giá trị, tùy chế độ |
| `CURRENT ROW` | Mốc của hàng hiện tại; có thể bao gồm cả nhóm peers |
| `n FOLLOWING` | Tiến tới n hàng, n nhóm peers hoặc một khoảng giá trị |
| `UNBOUNDED FOLLOWING` | Đến cuối phân hoạch |

Các dạng thường gặp:

```sql
-- Tích lũy từ đầu phân hoạch đến hiện tại
ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW

-- Hàng trước + hàng hiện tại + hàng sau
ROWS BETWEEN 1 PRECEDING AND 1 FOLLOWING

-- Toàn bộ phân hoạch, có ORDER BY để dùng với LAST_VALUE
ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING

-- Từ hàng hiện tại đến cuối phân hoạch
ROWS BETWEEN CURRENT ROW AND UNBOUNDED FOLLOWING

-- Hai nhóm peers liền trước cùng nhóm peers hiện tại
GROUPS BETWEEN 2 PRECEDING AND CURRENT ROW
```

Cách rút gọn:

```sql
ROWS UNBOUNDED PRECEDING
```

thường tương đương với:

```sql
ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
```

Trong PostgreSQL, biên đầu và biên cuối phải tạo khung hợp lệ về thứ tự. Không thể tùy ý viết `UNBOUNDED FOLLOWING` làm biên đầu hoặc `UNBOUNDED PRECEDING` làm biên cuối. Các giới hạn chính xác còn phụ thuộc loại khung và cách khai báo offset.

### UNBOUNDED không có nghĩa toàn bộ bảng

`UNBOUNDED PRECEDING` và `UNBOUNDED FOLLOWING` giới hạn theo **phân hoạch hiện tại**, không vượt qua `PARTITION BY region` để lấy hàng khu vực khác.

Ví dụ toàn bộ khung trong North vẫn chỉ xét 6 hàng North, không bao gồm 4 hàng South.

## 8. Ba kiểu khung: ROWS, RANGE và GROUPS

Ba kiểu frame khác nhau ở cách hiểu **đơn vị** khi xét biên:

| Loại | Đơn vị di chuyển biên | Vai trò của peers |
| --- | --- | --- |
| **`ROWS`** | Vị trí hàng riêng lẻ | `CURRENT ROW` là đúng hàng hiện tại; nếu thứ tự còn hòa, chọn hàng trước/sau không ổn định |
| **`RANGE`** | Giá trị của biểu thức `ORDER BY` hoặc phạm vi peers | `CURRENT ROW` kéo đến đầu/cuối **nhóm peers** theo biên khung; offset đo theo khoảng giá trị |
| **`GROUPS`** | Số nhóm peers theo thứ tự | `1 PRECEDING` là **nhóm đồng hạng trước**, không phải một hàng trước |

Một ví dụ trên North:

```text
Nhóm ngày G1: 03-01 = [sale 1]
Nhóm ngày G2: 03-02 = [sale 2, sale 3]
Nhóm ngày G3: 03-04 = [sale 4]
Nhóm ngày G4: 03-05 = [sale 5, sale 6]

Ở sale 3:
  ROWS 1 PRECEDING .. CURRENT ROW: sale 2, sale 3
  GROUPS 1 PRECEDING .. CURRENT ROW: G1 + G2
  RANGE 2 ngày PRECEDING .. CURRENT ROW: ngày 03-01 và 03-02
```

Ở sale 4 (ngày 03-04), sự khác biệt rõ hơn:

```text
  ROWS 1 PRECEDING .. CURRENT ROW: sale 3, sale 4
  GROUPS 1 PRECEDING .. CURRENT ROW: G2 + G3
  RANGE 2 ngày PRECEDING .. CURRENT ROW: các ngày 03-02 đến 03-04
```

Hai kiểu sau có thể cho cùng giá trị **trong bộ dữ liệu cụ thể này**, nhưng ngữ nghĩa vẫn khác: `GROUPS` đếm nhóm ngày có mặt, `RANGE` đo độ dài ngày thực trên trục thời gian.

## 9. ROWS: khung trượt theo số hàng

Ví dụ cộng số tiền của **hàng trước và hàng hiện tại** trong mỗi khu vực:

```sql
SELECT
    sale_id,
    region,
    sold_on,
    amount,
    SUM(amount) OVER (
        PARTITION BY region
        ORDER BY sold_on, sale_id
        ROWS BETWEEN 1 PRECEDING AND CURRENT ROW
    ) AS previous_and_current
FROM window_frames_lab
ORDER BY region, sold_on, sale_id;
```

Với North:

| sale_id | amount | Khung gồm | previous_and_current |
| ---: | ---: | --- | ---: |
| 1 | 100 | 1 | 100 |
| 2 | 50 | 1, 2 | 150 |
| 3 | 70 | 2, 3 | 120 |
| 4 | `NULL` | 3, 4 | 70 |
| 5 | 20 | 4, 5 | 20 |
| 6 | 0 | 5, 6 | 20 |

Với sale 4, khung có sale 3 = 70 và sale 4 = `NULL`; `SUM` bỏ qua `NULL` nên trả 70.

### ROWS BETWEEN 1 PRECEDING AND 1 FOLLOWING

```sql
SELECT sale_id, amount,
       SUM(amount) OVER (
           PARTITION BY region
           ORDER BY sold_on, sale_id
           ROWS BETWEEN 1 PRECEDING AND 1 FOLLOWING
       ) AS three_row_sum
FROM window_frames_lab
WHERE region = 'North'
ORDER BY sold_on, sale_id;
```

Với sale 3, khung gồm sale 2 (50), sale 3 (70) và sale 4 (`NULL`), nên tổng là **120**. Với sale 1 ở đầu phân hoạch, không có hàng phía trước; khung thực tế chỉ gồm sale 1 và sale 2, tổng **150**.

**Biên vượt ra ngoài phân hoạch** được giới hạn tại đầu hoặc cuối phân hoạch; `ROWS` không tạo ra hàng giả có giá trị 0 để bù vị trí không tồn tại.

## 10. RANGE: khung theo khoảng giá trị ORDER BY

`RANGE` không nhất thiết đếm số hàng. Với một biểu thức thứ tự thuộc kiểu thời gian, offset có thể diễn đạt khoảng thời gian.

Ví dụ tổng tiền trong phạm vi **hai ngày trở lại tính cả ngày hiện tại**:

```sql
SELECT
    sale_id,
    region,
    sold_on,
    amount,
    SUM(amount) OVER (
        PARTITION BY region
        ORDER BY sold_on::TIMESTAMP
        RANGE BETWEEN INTERVAL '2 days' PRECEDING
                  AND CURRENT ROW
    ) AS sum_last_two_days_back
FROM window_frames_lab
ORDER BY region, sold_on, sale_id;
```

Trong PostgreSQL, chúng ta ép `sold_on` từ `DATE` sang `TIMESTAMP` để dùng offset `INTERVAL '2 days'` một cách tường minh.

Khung ở ngày `d` gồm các hàng có thời điểm sắp xếp thuộc **`[d - 2 ngày, d]`**, kể cả toàn bộ peers cùng ngày.

Ví dụ North:

| Ngày | Những ngày có dữ liệu trong khung | Tổng |
| --- | --- | ---: |
| 03-01 | 03-01 | 100 |
| 03-02 | 03-01, 03-02 | 220 |
| 03-04 | 03-02, 03-04 | 120 |
| 03-05 | 03-04, 03-05 | 20 |

North không có bản ghi ngày 03-03, nhưng `RANGE` vẫn xét mốc ngày **thực**, không dịch về “hai nhóm ngày gần nhất”.

### RANGE offset khác ROWS offset

Với dữ liệu có ngày trùng:

- `ROWS BETWEEN 2 PRECEDING AND CURRENT ROW` lấy tối đa **ba hàng**.
- `RANGE BETWEEN INTERVAL '2 days' PRECEDING AND CURRENT ROW` lấy **bao nhiêu hàng cũng được** miễn thời điểm nằm trong phạm vi hai ngày và cùng phân hoạch.

Nếu một ngày có 1000 giao dịch, một khung `RANGE` bao gồm ngày đó có thể chứa cả 1000 giao dịch, không phải chỉ một hoặc hai hàng.

### Giới hạn của RANGE có offset

Trong PostgreSQL, khi `RANGE` có offset `n PRECEDING` hoặc `n FOLLOWING`, `ORDER BY` của cửa sổ cần một biểu thức thích hợp để xác định khoảng giá trị. Kiểu offset phải tương thích với kiểu biểu thức thứ tự: số với số, khoảng thời gian thích hợp với ngày/giờ.

Ví dụ với số:

```sql
WITH measurements(measure_id, score) AS (
    VALUES
        (1, 10::NUMERIC),
        (2, 12::NUMERIC),
        (3, 12::NUMERIC),
        (4, 20::NUMERIC)
)
SELECT measure_id,
       score,
       COUNT(*) OVER (
           ORDER BY score
           RANGE BETWEEN 2 PRECEDING AND CURRENT ROW
       ) AS nearby_score_count
FROM measurements
ORDER BY score, measure_id;
```

Kết quả theo bốn hàng là **1, 3, 3, 1**:

- Ở điểm 10 chỉ có một hàng điểm 10.
- Ở điểm 12, khung [10,12] gồm một hàng 10 và hai hàng 12.
- Ở điểm 20, khung [18,20] chỉ có hàng 20.

Đừng chuyển câu này thành `ROWS BETWEEN 2 PRECEDING ...` rồi kỳ vọng giống nhau: đó là hai đơn vị đo khác nhau.

## 11. GROUPS: khung trượt theo nhóm đồng hạng

`GROUPS` đếm các **nhóm peers liên tiếp** trong thứ tự cửa sổ. Khi `ORDER BY sold_on`, mỗi ngày có dữ liệu tạo một nhóm peers trong từng khu vực.

```sql
SELECT
    sale_id,
    region,
    sold_on,
    amount,
    SUM(amount) OVER (
        PARTITION BY region
        ORDER BY sold_on
        GROUPS BETWEEN 1 PRECEDING AND CURRENT ROW
    ) AS previous_day_group_and_current
FROM window_frames_lab
ORDER BY region, sold_on, sale_id;
```

Với North:

| Ngày | Nhóm peers có trong khung | Tổng |
| --- | --- | ---: |
| 03-01 | G1 (03-01) | 100 |
| 03-02 | G1 + G2 | 220 |
| 03-04 | G2 + G3 | 120 |
| 03-05 | G3 + G4 | 20 |

Hai hàng cùng ngày nhận cùng kết quả.

### GROUPS không phải “một ngày trước”

Từ 03-02 tới 03-04 có khoảng trống ngày 03-03:

- `GROUPS 1 PRECEDING` tại 03-04 lấy nhóm có dữ liệu ở 03-02.
- Nếu bạn muốn đúng **24 giờ trước đó**, phải dùng `RANGE` theo thời gian tương ứng, không phải `GROUPS`.

### Có nhiều biểu thức ORDER BY

`GROUPS` dùng nhóm peers theo **toàn bộ** `ORDER BY`. Nếu viết `ORDER BY sold_on, sale_id` trên bảng mẫu, mỗi `sale_id` là duy nhất, các nhóm peers trở thành **nhóm một hàng**. Khi đó `GROUPS 1 PRECEDING` có thể trông tương tự `ROWS 1 PRECEDING` trên dữ liệu này, nhưng vẫn là hai kiểu khung với đơn vị định nghĩa khác nhau.

## 12. CURRENT ROW không mang một nghĩa duy nhất

Xét khung:

```sql
BETWEEN CURRENT ROW AND CURRENT ROW
```

Ý nghĩa thay đổi theo kiểu khung:

| Cách viết | Các hàng nằm trong khung |
| --- | --- |
| `ROWS BETWEEN CURRENT ROW AND CURRENT ROW` | Chỉ **hàng vật lý hiện tại** |
| `RANGE BETWEEN CURRENT ROW AND CURRENT ROW` | Toàn bộ **nhóm peers của hàng hiện tại** |
| `GROUPS BETWEEN CURRENT ROW AND CURRENT ROW` | Toàn bộ **nhóm peers của hàng hiện tại** |

Ví dụ:

```sql
SELECT
    sale_id, region, sold_on, amount,
    COUNT(*) OVER (
        PARTITION BY region
        ORDER BY sold_on
        ROWS BETWEEN CURRENT ROW AND CURRENT ROW
    ) AS one_row,
    COUNT(*) OVER (
        PARTITION BY region
        ORDER BY sold_on
        RANGE BETWEEN CURRENT ROW AND CURRENT ROW
    ) AS peer_row_count
FROM window_frames_lab
ORDER BY region, sold_on, sale_id;
```

Ở sale 2 và sale 3:

- `one_row = 1`.
- `peer_row_count = 2`.

Ở sale 1:

- `one_row = 1`.
- `peer_row_count = 1`.

Đây là minh họa ngắn gọn nhất cho việc **khung `RANGE` có thể mở rộng theo peers dù ghi `CURRENT ROW`**.

## 13. FIRST_VALUE, LAST_VALUE và bẫy khung mặc định

Các hàm `FIRST_VALUE`, `LAST_VALUE` và `NTH_VALUE` đặc biệt nhạy với biên khung.

### LAST_VALUE: “cuối khung”, không tự động là “cuối phân hoạch”

Ví dụ:

```sql
SELECT
    sale_id, region, sold_on,
    LAST_VALUE(sale_id) OVER (
        PARTITION BY region
        ORDER BY sold_on, sale_id
    ) AS last_id_default
FROM window_frames_lab
ORDER BY region, sold_on, sale_id;
```

Trong ví dụ, `ORDER BY sold_on, sale_id` xác định một thứ tự duy nhất. Khung mặc định kết thúc ở hàng hiện tại vì không còn peers khác hàng. Do vậy `last_id_default` lần lượt bằng **chính `sale_id` của mỗi hàng**.

Nếu mong muốn “ID của hàng cuối cùng trong cả khu vực”, phải mở rộng khung tới cuối phân hoạch:

```sql
SELECT
    sale_id, region, sold_on,
    LAST_VALUE(sale_id) OVER (
        PARTITION BY region
        ORDER BY sold_on, sale_id
        ROWS BETWEEN UNBOUNDED PRECEDING
                 AND UNBOUNDED FOLLOWING
    ) AS final_id_in_region
FROM window_frames_lab
ORDER BY region, sold_on, sale_id;
```

Kết quả:

- Mọi hàng North có `final_id_in_region = 6`.
- Mọi hàng South có `final_id_in_region = 10`.

**Khóa phá hòa `sale_id` rất quan trọng.** Nếu chỉ `ORDER BY sold_on`, hai giao dịch cùng ngày cuối có thể hòa, và giá trị cuối được lấy từ peer nào có thể không ổn định.

### Vì sao không dùng LAST_VALUE(amount) cho ví dụ đơn giản?

Hàng cuối South có `amount = NULL`. Nếu hỏi “giá trị của hàng cuối” thì kết quả đúng theo dữ liệu là **`NULL`**, không phải 90. PostgreSQL `LAST_VALUE` không tự bỏ qua `NULL` để tìm số tiền đã biết cuối cùng. Muốn tìm “giá trị không NULL mới nhất” cần biểu thức/truy vấn theo quy tắc nghiệp vụ, không chỉ đổi frame.

### FIRST_VALUE cũng có frame

`FIRST_VALUE` trả giá trị ở hàng **đầu tiên của khung**. Với khung mặc định bắt đầu ở `UNBOUNDED PRECEDING` và thứ tự đầy đủ, nó thường chính là hàng đầu phân hoạch.

```sql
SELECT sale_id, region,
       FIRST_VALUE(sale_id) OVER (
           PARTITION BY region
           ORDER BY sold_on, sale_id
       ) AS first_id_in_default_frame
FROM window_frames_lab
ORDER BY region, sold_on, sale_id;
```

Mọi hàng North trả 1, mọi hàng South trả 7.

Nhưng nếu khung bắt đầu bằng `CURRENT ROW`:

```sql
FIRST_VALUE(sale_id) OVER (
    PARTITION BY region
    ORDER BY sold_on, sale_id
    ROWS BETWEEN CURRENT ROW AND UNBOUNDED FOLLOWING
)
```

thì hàng đầu của khung là chính hàng hiện tại, nên `FIRST_VALUE` trả `sale_id` của hàng đó. Tên hàm không có nghĩa nó bỏ qua định nghĩa frame.

### NTH_VALUE: chưa có đủ hàng trong khung sẽ trả NULL

`NTH_VALUE(expression, n)` trả giá trị của hàng thứ `n` trong **khung hiện tại** khi đếm từ đầu, với `n` bắt đầu từ 1 trong PostgreSQL.

```sql
SELECT
    sale_id, region,
    NTH_VALUE(sale_id, 2) OVER (
        PARTITION BY region
        ORDER BY sold_on, sale_id
    ) AS second_id_default,
    NTH_VALUE(sale_id, 2) OVER (
        PARTITION BY region
        ORDER BY sold_on, sale_id
        ROWS BETWEEN UNBOUNDED PRECEDING
                 AND UNBOUNDED FOLLOWING
    ) AS second_id_full_partition
FROM window_frames_lab
ORDER BY region, sold_on, sale_id;
```

Ở hàng đầu North, khung mặc định mới có một hàng nên `second_id_default = NULL`; từ hàng thứ hai trở đi nó là 2. Trong cột full-partition, mọi hàng North đều trả 2, mọi hàng South trả 8.

**Bài học:** một giá trị `NULL` từ `NTH_VALUE` có thể do **khung chưa chứa vị trí thứ n**, không nhất thiết do dữ liệu nguồn tại vị trí đó là `NULL`.

## 14. Những hàm nào phụ thuộc khung, những hàm nào chủ yếu phụ thuộc phân hoạch và thứ tự?

Không phải mọi hàm có `OVER` đều dùng frame theo cách giống `SUM` hoặc `LAST_VALUE`.

| Nhóm hàm | Quan hệ với frame trong PostgreSQL | Lưu ý |
| --- | --- | --- |
| `SUM`, `AVG`, `COUNT`, `MIN`, `MAX` khi dùng `OVER` | Tính trên **khung hiện tại** | Frame quyết định tập giá trị được tổng hợp |
| `FIRST_VALUE`, `LAST_VALUE`, `NTH_VALUE` | Nhạy với **biên khung** | Mặc định có thể gây bất ngờ |
| `ROW_NUMBER` | Đánh số hàng theo thứ tự cửa sổ | Không bị giới hạn bởi frame; nếu peers chưa được phá hòa, thứ tự giữa họ không ổn định |
| `RANK`, `DENSE_RANK` | Xếp hạng theo peer groups | Không thay đổi kết quả chỉ vì đổi khung từ ROWS sang RANGE |
| `PERCENT_RANK`, `CUME_DIST` | Dựa vào thứ hạng/kích thước peers và phân hoạch | Peers ảnh hưởng trực tiếp, nhưng không theo kiểu tổng trên frame |
| `LAG`, `LEAD` | Lấy giá trị ở vị trí trước/sau trong phân hoạch theo thứ tự | Không bị chặn bởi frame tính tổng |
| `NTILE` | Chia phân hoạch thành các nhóm theo thứ tự | Không phải phép tổng hợp trên frame |

Ví dụ:

```sql
SELECT
    sale_id,
    region,
    sold_on,
    ROW_NUMBER() OVER (
        PARTITION BY region
        ORDER BY sold_on, sale_id
    ) AS row_no,
    RANK() OVER (
        PARTITION BY region
        ORDER BY sold_on
    ) AS rank_by_day,
    DENSE_RANK() OVER (
        PARTITION BY region
        ORDER BY sold_on
    ) AS dense_rank_by_day
FROM window_frames_lab
ORDER BY region, sold_on, sale_id;
```

Trong North:

| sale_id | sold_on | row_no | rank_by_day | dense_rank_by_day |
| ---: | --- | ---: | ---: | ---: |
| 1 | 03-01 | 1 | 1 | 1 |
| 2 | 03-02 | 2 | 2 | 2 |
| 3 | 03-02 | 3 | 2 | 2 |
| 4 | 03-04 | 4 | 4 | 3 |
| 5 | 03-05 | 5 | 5 | 4 |
| 6 | 03-05 | 6 | 5 | 4 |

`RANK` chừa khoảng sau nhóm peers; `DENSE_RANK` không chừa khoảng. Chúng liên quan tới peers theo `ORDER BY` nhưng không có cùng ý nghĩa với việc `SUM` “nhảy bậc” do khung `RANGE`.

### LAG có thể nhìn ra ngoài frame rất hẹp

```sql
SELECT sale_id, region, amount,
       LAG(amount) OVER (
           PARTITION BY region
           ORDER BY sold_on, sale_id
           ROWS BETWEEN CURRENT ROW AND CURRENT ROW
       ) AS previous_amount
FROM window_frames_lab
ORDER BY region, sold_on, sale_id;
```

Dù `ROWS BETWEEN CURRENT ROW AND CURRENT ROW` chỉ có hàng hiện tại trong frame, `LAG` vẫn tham chiếu **hàng trước đó trong phân hoạch** theo thứ tự; frame không giới hạn phép lấy này ở PostgreSQL.

Đây là lý do phải biết **hàm cụ thể có sử dụng frame hay không**, thay vì áp một mô hình duy nhất cho mọi window function.

## 15. COUNT và NULL trong khung cửa sổ

Một khung có thể chứa hàng nhưng không có số tiền nào khác `NULL`:

```sql
SELECT
    sale_id,
    region,
    amount,
    COUNT(*) OVER (
        PARTITION BY region
        ORDER BY sold_on, sale_id
        ROWS BETWEEN CURRENT ROW AND CURRENT ROW
    ) AS frame_rows,
    COUNT(amount) OVER (
        PARTITION BY region
        ORDER BY sold_on, sale_id
        ROWS BETWEEN CURRENT ROW AND CURRENT ROW
    ) AS known_amounts,
    SUM(amount) OVER (
        PARTITION BY region
        ORDER BY sold_on, sale_id
        ROWS BETWEEN CURRENT ROW AND CURRENT ROW
    ) AS frame_amount
FROM window_frames_lab
ORDER BY region, sold_on, sale_id;
```

Với sale 4 (North) và sale 10 (South), mỗi khung chỉ gồm một hàng có `amount = NULL`:

- `frame_rows = 1`.
- `known_amounts = 0`.
- `frame_amount = NULL`.

Với sale 6, `amount = 0` là giá trị đã biết:

- `frame_rows = 1`.
- `known_amounts = 1`.
- `frame_amount = 0`.

Đừng thay `NULL` bằng 0 chỉ để làm mọi dòng có số hiển thị. Việc thiếu dữ liệu và giá trị số 0 là hai trạng thái khác nhau.

### Khung rỗng

Một khung hoàn toàn rỗng có thể tạo:

- `COUNT(*) = 0`.
- `COUNT(amount) = 0`.
- `SUM(amount) = NULL`.
- `AVG(amount) = NULL`.

Ví dụ sử dụng **nhóm peers ngay trước**, không bao gồm nhóm hiện tại:

```sql
SELECT sale_id, region, sold_on,
       COUNT(*) OVER (
           PARTITION BY region
           ORDER BY sold_on
           GROUPS BETWEEN 1 PRECEDING AND 1 PRECEDING
       ) AS previous_group_rows,
       SUM(amount) OVER (
           PARTITION BY region
           ORDER BY sold_on
           GROUPS BETWEEN 1 PRECEDING AND 1 PRECEDING
       ) AS previous_group_amount
FROM window_frames_lab
ORDER BY region, sold_on, sale_id;
```

Ở **nhóm ngày đầu tiên** của mỗi khu vực, không có nhóm peers trước, nên `previous_group_rows = 0` và `previous_group_amount = NULL`.

`NULL` của `SUM` trong trường hợp này đến từ **khung rỗng**, không phải một giao dịch nguồn có `amount = NULL`.

## 16. EXCLUDE: loại hàng hiện tại hoặc peers khỏi khung

PostgreSQL hỗ trợ tùy chọn `EXCLUDE` trong định nghĩa frame, cho phép loại một số hàng sau khi xác định phạm vi ban đầu.

Các lựa chọn thường gặp:

| Tùy chọn | Tác động |
| --- | --- |
| `EXCLUDE NO OTHERS` | Không loại hàng nào; hành vi mặc định |
| `EXCLUDE CURRENT ROW` | Loại chính hàng hiện tại, **giữ peers khác** nếu nằm trong khung |
| `EXCLUDE GROUP` | Loại cả **nhóm peers** của hàng hiện tại, kể cả chính nó |
| `EXCLUDE TIES` | Loại **các peers khác**, nhưng **giữ hàng hiện tại** |

Dùng `RANGE` để tạo khung tích lũy theo ngày, rồi quan sát số hàng:

```sql
SELECT
    sale_id, region, sold_on,
    COUNT(*) OVER (
        PARTITION BY region
        ORDER BY sold_on
        RANGE BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS normal_count,
    COUNT(*) OVER (
        PARTITION BY region
        ORDER BY sold_on
        RANGE BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
        EXCLUDE CURRENT ROW
    ) AS except_current,
    COUNT(*) OVER (
        PARTITION BY region
        ORDER BY sold_on
        RANGE BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
        EXCLUDE GROUP
    ) AS except_peer_group,
    COUNT(*) OVER (
        PARTITION BY region
        ORDER BY sold_on
        RANGE BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
        EXCLUDE TIES
    ) AS except_other_peers
FROM window_frames_lab
ORDER BY region, sold_on, sale_id;
```

Với **sale 2 và sale 3** (North, ngày 03-02), khung bình thường gồm `1,2,3`:

| Khung | Số hàng |
| --- | ---: |
| Không `EXCLUDE` | 3 |
| `EXCLUDE CURRENT ROW` | 2 |
| `EXCLUDE GROUP` | 1 |
| `EXCLUDE TIES` | 2 |

Giải thích:

- Loại *current row*: còn sale 1 và peer kia.
- Loại *group*: chỉ còn sale 1.
- Loại *ties*: giữ sale 1 và chính sale đang tính, loại peer kia.

Đối với sale 1 (không có peer khác), `EXCLUDE CURRENT ROW` và `EXCLUDE GROUP` làm khung rỗng; còn `EXCLUDE TIES` vẫn giữ sale 1.

### Khi nào EXCLUDE hữu ích?

- So sánh một giao dịch với **các giao dịch trước ngày hiện tại**, không lấy ngày hiện tại: dùng cơ chế loại nhóm peers hoặc khung kết thúc tại nhóm trước.
- So sánh một giao dịch với **các giao dịch khác cùng nhóm**, không tính chính nó.
- Tính tổng hoặc trung bình tham chiếu không bao gồm một số đối tượng đang được đánh giá.

Tuy nhiên, không nên dùng `EXCLUDE` mà chưa mô tả được rõ **hàng nào bị loại** và **có giữ các peers khác hay không**. Với dữ liệu có ngày đồng hạng, các lựa chọn cho kết quả khác nhau đáng kể.

## 17. Đổi hướng ORDER BY sẽ thay đổi nghĩa PRECEDING/FOLLOWING

`PRECEDING` và `FOLLOWING` dựa trên **thứ tự của cửa sổ**, không phải luôn là thời gian sớm hơn hoặc muộn hơn.

Ví dụ:

```sql
SELECT sale_id, region, sold_on,
       SUM(amount) OVER (
           PARTITION BY region
           ORDER BY sold_on DESC, sale_id DESC
           ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
       ) AS reverse_running_total
FROM window_frames_lab
ORDER BY region, sold_on DESC, sale_id DESC;
```

Với North, trình tự là sale 6, 5, 4, 3, 2, 1. Tổng tích lũy theo thứ tự **giảm dần** sẽ cộng từ giao dịch muộn nhất tới giao dịch sớm hơn:

```text
sale 6 (0)       → 0
sale 5 (20)      → 20
sale 4 (NULL)    → 20
sale 3 (70)      → 90
sale 2 (50)      → 140
sale 1 (100)     → 240
```

`UNBOUNDED PRECEDING` ở đây là **đầu của thứ tự giảm dần**, tức các hàng có ngày mới nhất. Không nên hiểu nó là “tất cả ngày trong quá khứ” một cách tuyệt đối.

Tương tự, `RANGE ... PRECEDING` với `ORDER BY ... DESC` phải được hiểu theo quy tắc hướng sắp xếp và kiểu offset của DBMS.

## 18. PARTITION BY và GROUP BY không thay thế nhau

`GROUP BY` biến nhiều hàng thành các hàng tổng hợp theo nhóm. Hàm cửa sổ thường **giữ lại từng hàng** và bổ sung giá trị tính trên phân hoạch/khung.

So sánh:

```sql
-- Mỗi khu vực một hàng
SELECT region, SUM(amount) AS total_amount
FROM window_frames_lab
GROUP BY region
ORDER BY region;
```

Kết quả có **2 hàng**: North = 240 và South = 190.

```sql
-- Vẫn là 10 hàng bán, mỗi hàng kèm tổng của khu vực
SELECT sale_id, region, amount,
       SUM(amount) OVER (PARTITION BY region) AS region_total
FROM window_frames_lab
ORDER BY region, sold_on, sale_id;
```

Kết quả có **10 hàng**. Mọi hàng North mang `region_total = 240`, South mang `190`.

Một khác biệt bổ sung: nếu câu SQL có `GROUP BY`, các hàm cửa sổ ở `SELECT` được đánh giá trên **các hàng đã qua bước tổng hợp** của cấp truy vấn tương ứng. Không thể tùy tiện dùng cột chi tiết không thuộc `GROUP BY` trong biểu thức window sau khi đã gom nhóm. Khi cần tính cửa sổ trên số liệu tổng hợp theo ngày, hãy tạo CTE tổng hợp trước rồi áp dụng window ở cấp ngoài.

## 19. Tính tích lũy trên ngày đã tổng hợp: một phương án rõ ràng cho nghiệp vụ

Nếu báo cáo yêu cầu **một hàng mỗi ngày** và tổng tiền lũy kế theo ngày, cách dễ hiểu là tính tổng ngày trước, sau đó chạy cửa sổ trên dữ liệu ngày:

```sql
WITH daily_sales AS (
    SELECT
        region,
        sold_on,
        SUM(amount) AS daily_amount
    FROM window_frames_lab
    GROUP BY region, sold_on
)
SELECT
    region,
    sold_on,
    daily_amount,
    SUM(daily_amount) OVER (
        PARTITION BY region
        ORDER BY sold_on
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS running_daily_amount
FROM daily_sales
ORDER BY region, sold_on;
```

Với North:

| Ngày | daily_amount | running_daily_amount |
| --- | ---: | ---: |
| 03-01 | 100 | 100 |
| 03-02 | 120 | 220 |
| 03-04 | `NULL` | 220 |
| 03-05 | 20 | 240 |

Ngày 03-04 có giao dịch nhưng `amount` toàn `NULL`, nên `daily_amount` là `NULL`. Tổng lũy kế `SUM` bỏ qua giá trị đó; nếu cần kiểm soát độ đầy đủ của số liệu, nên kèm thêm `COUNT(*)` và `COUNT(amount)` trong CTE ngày.

Ở cấp `daily_sales`, cặp `(region,sold_on)` là duy nhất, nên dùng `ROWS` với `ORDER BY sold_on` cho tổng ngày tích lũy là có thứ tự xác định. Đây là một lựa chọn thiết kế khác với việc trả **một hàng cho mỗi giao dịch** nhưng dùng khung `RANGE` theo nhóm peers.

## 20. Một khung đầy đủ để tính chỉ tiêu của cả phân hoạch

Khi cần `FIRST_VALUE`, `LAST_VALUE` hoặc `NTH_VALUE` trên **toàn bộ phân hoạch**, có thể khai báo rõ:

```sql
ROWS BETWEEN UNBOUNDED PRECEDING
         AND UNBOUNDED FOLLOWING
```

Ví dụ:

```sql
SELECT
    sale_id,
    region,
    FIRST_VALUE(sale_id) OVER (
        PARTITION BY region
        ORDER BY sold_on, sale_id
        ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING
    ) AS first_sale_id,
    LAST_VALUE(sale_id) OVER (
        PARTITION BY region
        ORDER BY sold_on, sale_id
        ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING
    ) AS last_sale_id,
    SUM(amount) OVER (
        PARTITION BY region
        ORDER BY sold_on, sale_id
        ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING
    ) AS region_total
FROM window_frames_lab
ORDER BY region, sold_on, sale_id;
```

Kết quả:

- North: `first_sale_id = 1`, `last_sale_id = 6`, `region_total = 240`.
- South: `first_sale_id = 7`, `last_sale_id = 10`, `region_total = 190`.

Đối với `SUM(amount)` toàn phân hoạch, thường có thể viết đơn giản hơn:

```sql
SUM(amount) OVER (PARTITION BY region)
```

vì không cần thứ tự để tính tổng. Nhưng `LAST_VALUE` cần một **thứ tự có nghĩa** để định nghĩa “cuối cùng”, nên không nên bỏ `ORDER BY` ở hàm này.

### Nếu muốn tổng của các hàng còn lại phía sau

```sql
SELECT sale_id, region, amount,
       SUM(amount) OVER (
           PARTITION BY region
           ORDER BY sold_on, sale_id
           ROWS BETWEEN CURRENT ROW AND UNBOUNDED FOLLOWING
       ) AS remaining_total
FROM window_frames_lab
ORDER BY region, sold_on, sale_id;
```

Với North:

| sale_id | remaining_total |
| ---: | ---: |
| 1 | 240 |
| 2 | 140 |
| 3 | 90 |
| 4 | 20 |
| 5 | 20 |
| 6 | 0 |

Ở sale 4, tổng từ sale 4 đến 6 là `NULL + 20 + 0 = 20` theo quy tắc `SUM` bỏ qua `NULL`. Nếu khung chỉ có các số tiền `NULL`, `SUM` sẽ trả `NULL`, không phải 0.

## 21. WINDOW: đặt tên cho cấu hình cửa sổ

Khi nhiều biểu thức dùng cùng `PARTITION BY`, `ORDER BY` và frame, PostgreSQL hỗ trợ mệnh đề `WINDOW` để đặt tên cấu hình:

```sql
SELECT
    sale_id,
    region,
    sold_on,
    amount,
    SUM(amount) OVER w AS running_sum,
    COUNT(*) OVER w AS running_rows,
    COUNT(amount) OVER w AS running_known_amounts
FROM window_frames_lab
WINDOW w AS (
    PARTITION BY region
    ORDER BY sold_on, sale_id
    ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
)
ORDER BY region, sold_on, sale_id;
```

Cả ba hàm dùng cùng khung `w`:

- `SUM(amount)` cộng tiền đã biết.
- `COUNT(*)` đếm mọi giao dịch trong khung.
- `COUNT(amount)` chỉ đếm các giao dịch có số tiền khác `NULL`.

Việc đặt tên cửa sổ giúp tránh việc cùng một báo cáo vô tình dùng các frame khác nhau chỉ do sao chép thiếu một dòng `ROWS BETWEEN ...`.

### Hai cửa sổ cho hai mục tiêu

```sql
SELECT
    sale_id,
    region,
    sold_on,
    SUM(amount) OVER w_running AS running_total,
    SUM(amount) OVER w_full AS full_region_total
FROM window_frames_lab
WINDOW
    w_running AS (
        PARTITION BY region
        ORDER BY sold_on, sale_id
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ),
    w_full AS (
        PARTITION BY region
        ORDER BY sold_on, sale_id
        ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING
    )
ORDER BY region, sold_on, sale_id;
```

Hai tên cửa sổ mô tả rõ **tổng tích lũy** và **tổng cả khu vực**. Không nên đặt cả hai là `w` chỉ vì chúng cùng `PARTITION BY`.

## 22. Lọc theo kết quả cửa sổ cần đúng cấp truy vấn

Trong PostgreSQL, không thể dùng trực tiếp hàm cửa sổ ở `WHERE` cùng cấp như cách dùng một điều kiện thông thường:

```sql
-- Ví dụ lỗi trong PostgreSQL:
SELECT sale_id,
       ROW_NUMBER() OVER (
           PARTITION BY region ORDER BY sold_on, sale_id
       ) AS row_no
FROM window_frames_lab
WHERE ROW_NUMBER() OVER (
    PARTITION BY region ORDER BY sold_on, sale_id
) <= 2;
```

Hãy tính hàm cửa sổ trong CTE rồi lọc ở truy vấn ngoài:

```sql
WITH ranked_sales AS (
    SELECT sale_id, region, sold_on, amount,
           ROW_NUMBER() OVER (
               PARTITION BY region
               ORDER BY sold_on, sale_id
           ) AS row_no
    FROM window_frames_lab
)
SELECT sale_id, region, sold_on, amount, row_no
FROM ranked_sales
WHERE row_no <= 2
ORDER BY region, row_no;
```

Điều này cũng áp dụng khi cần lọc theo một `SUM` cửa sổ hoặc theo chênh lệch giữa tổng tích lũy và tổng cả phân hoạch.

Quan trọng: nếu lọc các hàng **trước khi** chạy window, dữ liệu còn lại trong mỗi phân hoạch sẽ thay đổi và có thể làm khung, peers và kết quả tính khác đi. Lọc **sau khi** window trong CTE cấp ngoài giữ được ngữ nghĩa “tính trên tập nguồn ban đầu rồi mới chọn hàng”.

## 23. NULL và kiểu dữ liệu trong ORDER BY của cửa sổ

Trong bảng thực hành, `sold_on` có `NOT NULL` để peer groups dễ quan sát. Nhưng trong dữ liệu thực tế, biểu thức thứ tự có thể chứa `NULL`, chuỗi hoặc nhiều giá trị trùng.

### NULL trong khóa sắp xếp

PostgreSQL cho phép định nghĩa vị trí `NULL`:

```sql
ORDER BY some_date ASC NULLS LAST
```

hoặc:

```sql
ORDER BY some_date DESC NULLS FIRST
```

Trong PostgreSQL, với `ASC` mặc định các `NULL` thường nằm cuối; với `DESC` mặc định thường nằm đầu, nếu không ghi rõ vị trí. Các hàng có khóa thứ tự `NULL` có thể là peers nếu các khóa khác của `ORDER BY` cũng bằng nhau theo quy tắc sắp xếp.

Nếu nghiệp vụ không muốn đưa các ngày thiếu vào tổng tích lũy theo ngày, cần **định nghĩa chính sách riêng**: lọc, đặt nhóm “chưa xác định ngày”, hoặc xử lý bằng một biểu thức sắp xếp có chủ đích. Không nên mặc định thứ tự `NULL` của mọi DBMS đều giống PostgreSQL.

### Chuỗi và collation

Nếu `ORDER BY` là chuỗi, quy tắc đối chiếu (*collation*) có thể ảnh hưởng thứ tự và việc xác định các giá trị sắp xếp đồng hạng. Đối với báo cáo cần kết quả ổn định, nên hiểu collation đang sử dụng và bổ sung khóa phá hòa phù hợp khi cần.

### Cột có giá trị bằng nhau không có thứ tự nội bộ được bảo đảm

Nếu `ORDER BY sold_on` mà hai hàng cùng ngày, SQL không bảo đảm sale 2 trước sale 3. Dù `ORDER BY region,sold_on,sale_id` ở cuối truy vấn làm bảng hiển thị theo ID, nó **không tự quyết định lại thứ tự nội bộ của hàm cửa sổ**.

Đây là nguyên nhân dễ khiến một truy vấn `ROWS` có kết quả lũy kế khác nhau giữa môi trường hoặc sau khi index/kế hoạch thay đổi.

## 24. Hiệu năng của window frame và các lựa chọn thiết kế

Hàm cửa sổ có thể cần sắp xếp các hàng theo `PARTITION BY` và `ORDER BY`. Một số khung còn phải giữ trạng thái tính toán hoặc truy cập nhiều hàng quanh hàng hiện tại.

Các yếu tố cần quan tâm:

- Kích thước phân hoạch: một khu vực có hàng triệu giao dịch sẽ khác một khu vực có 10 hàng.
- Số lượng peer rows: nếu một ngày có rất nhiều giao dịch, `RANGE` mặc định có thể xử lý khung lớn.
- Frame kết thúc ở `UNBOUNDED FOLLOWING`: có thể yêu cầu biết các hàng phía sau.
- `ROWS` với khung trượt khác với `RANGE` theo khoảng thời gian hoặc `GROUPS` theo nhóm peers.
- Nhiều biểu thức window với thứ tự khác nhau có thể làm tăng công việc sắp xếp.
- Các biểu thức `ORDER BY`, cột lọc và chỉ mục có thể ảnh hưởng kế hoạch, nhưng không có một index chung tối ưu mọi truy vấn.

Trong PostgreSQL, có thể bắt đầu bằng:

```sql
EXPLAIN
SELECT
    sale_id,
    SUM(amount) OVER (
        PARTITION BY region
        ORDER BY sold_on, sale_id
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS running_total
FROM window_frames_lab;
```

`EXPLAIN` hiển thị kế hoạch dự kiến. Với dữ liệu tạm nhỏ, việc quét tuần tự và sắp xếp có thể hoàn toàn hợp lý. `EXPLAIN ANALYZE` thực thi câu lệnh để lấy thống kê thực tế, chỉ dùng khi an toàn và cần thiết trong môi trường phù hợp.

**Đừng đổi `RANGE` thành `ROWS` chỉ vì dự đoán nó nhanh hơn.** Hai khung có thể khác ngữ nghĩa nếu có peers. Hãy chọn đúng kết quả trước rồi mới đo và tối ưu.

## 25. Những điểm khác nhau giữa các hệ quản trị SQL

Khái niệm window function phổ biến, nhưng **không phải mọi DBMS hỗ trợ cùng loại frame, cùng mặc định hoặc cùng cách xử lý peers**.

| Chủ đề | PostgreSQL | Lưu ý khi chuyển hệ |
| --- | --- | --- |
| `PARTITION BY`, `ORDER BY` trong `OVER` | Có | Rộng rãi trong các DBMS hiện đại |
| Khung `ROWS` | Có | Cú pháp và phạm vi dùng với từng hàm có thể khác |
| Khung `RANGE` | Có, gồm một số kiểu offset giá trị/thời gian | SQL Server có những hạn chế đáng kể với `RANGE`; nhiều hệ không hỗ trợ đầy đủ offset như PostgreSQL |
| Khung `GROUPS` | Có ở PostgreSQL hiện đại | Không phải DBMS nào cũng hỗ trợ |
| `EXCLUDE CURRENT ROW/GROUP/TIES` | Có | Mức hỗ trợ khác nhau, không nên mặc định có ở mọi DBMS |
| Khung mặc định có `ORDER BY` | Phổ biến là `RANGE UNBOUNDED PRECEDING ... CURRENT ROW` | Cần kiểm tra quy định theo **loại hàm và DBMS** |
| `LAST_VALUE` | Phụ thuộc frame, thường cần ghi toàn phân hoạch | Lỗi tư duy “luôn là hàng cuối partition” có thể xuất hiện trên nhiều hệ |
| `NULLS FIRST/LAST` | Có cú pháp rõ ràng | Mặc định sắp xếp `NULL` khác nhau tùy DBMS |
| Mệnh đề `WINDOW` đặt tên cửa sổ | Có | Mức hỗ trợ và cách kế thừa cấu hình khác giữa hệ |
| `QUALIFY` để lọc window | Không phải cú pháp PostgreSQL phổ thông | Một số DBMS hỗ trợ; PostgreSQL có thể dùng CTE/subquery ngoài |

Một số nhận định riêng:

- **PostgreSQL:** hỗ trợ `ROWS`, `RANGE`, `GROUPS` và các tùy chọn `EXCLUDE`. Với `ORDER BY` và không có frame tường minh, những peers ở biên hiện tại được đưa vào khung mặc định.
- **SQL Server:** hỗ trợ cửa sổ với `ROWS` và `RANGE`, nhưng không thể suy rằng mọi offset `RANGE n PRECEDING` hoặc `GROUPS` như PostgreSQL đều chạy được. `LAST_VALUE` vẫn là điểm cần xem xét khung.
- **MySQL 8+:** hỗ trợ window functions và một số khai báo frame, nhưng các hạn chế cụ thể với loại frame, offset và hàm khác PostgreSQL. Cần kiểm tra phiên bản đang vận hành.
- **SQLite hiện đại:** hỗ trợ các dạng frame `ROWS`, `RANGE`, `GROUPS` và `EXCLUDE` theo tài liệu phiên bản tương ứng; kiểu dữ liệu và biểu thức thứ tự có khác biệt so với PostgreSQL.
- **Oracle Database:** có các cơ chế window frame/analytic functions phong phú, nhưng cách viết và giới hạn với nhiều khóa thứ tự, khung thời gian hoặc giá trị cụ thể cần kiểm tra theo phiên bản.

**Quy tắc di chuyển an toàn:** viết rõ loại frame và biên khi báo cáo phụ thuộc vào chúng, rồi kiểm tra câu lệnh trên DBMS đích thay vì chỉ dựa trên một tên hàm giống nhau.

## 26. Các lỗi thường gặp

| Triệu chứng | Nguyên nhân khả dĩ | Hướng xử lý |
| --- | --- | --- |
| Tổng tích lũy tăng cùng một lần cho hai giao dịch cùng ngày | `RANGE` mặc định bao gồm toàn bộ peers | Nếu muốn theo từng giao dịch, dùng `ROWS` và khóa phá hòa; nếu muốn tổng tới hết ngày, giữ `RANGE` |
| `LAST_VALUE` trả ngay `sale_id` hiện tại | Khung mặc định kết thúc tại current row/peer cuối | Dùng khung đến `UNBOUNDED FOLLOWING` và thứ tự rõ |
| `FIRST_VALUE` thay đổi khi dùng frame bắt đầu CURRENT ROW | Hàm lấy đầu **khung**, không nhất thiết đầu phân hoạch | Chọn biên phù hợp với mục tiêu |
| `NTH_VALUE` trả `NULL` ở các hàng đầu | Khung chưa có đủ n hàng | Mở rộng frame hoặc xác nhận mục tiêu là “thứ n đã quan sát” |
| ROWS 1 PRECEDING cho kết quả không ổn định ở hai hàng cùng ngày | `ORDER BY` không xác định thứ tự giữa peers | Thêm cột khóa duy nhất vào `ORDER BY` của cửa sổ |
| `RANGE INTERVAL` không hoạt động trên ORDER BY nhiều cột | Hạn chế cú pháp offset RANGE và kiểu dữ liệu | Dùng một khóa thời gian thích hợp; kiểm tra DBMS |
| GROUPS 1 PRECEDING lấy ngày cách nhiều ngày | Đếm **nhóm peers có dữ liệu**, không đếm ngày lịch | Dùng `RANGE` theo thời gian nếu cần |
| `CURRENT ROW` trong RANGE trả nhiều hàng | Nó mở rộng theo nhóm peers | Dùng `ROWS` nếu cần đúng một hàng |
| Dùng khung mặc định mà tưởng có tổng toàn phân hoạch | Có `ORDER BY` làm khung dừng tại current peer | Bỏ `ORDER BY` khi không cần hoặc ghi frame toàn phân hoạch |
| `COUNT(*)` và `SUM(amount)` khác nhau ở hàng NULL | COUNT đếm hàng; SUM bỏ giá trị NULL | Giữ thêm `COUNT(amount)` nếu cần biết độ đầy đủ |
| EXCLUDE TIES không giống EXCLUDE GROUP | TIES giữ hàng hiện tại; GROUP loại cả nó | Chọn theo yêu cầu so sánh |
| Thêm `sale_id` vào `ORDER BY` làm thay đổi `RANK` | Peer groups bị phá hòa | Tách cửa sổ xếp hạng theo ngày và cửa sổ lũy kế theo giao dịch |
| `ORDER BY` cuối truy vấn không sửa thứ tự ROWS | Thứ tự hiển thị khác thứ tự cửa sổ | Đặt khóa phá hòa trong `OVER` |
| Tổng trên giao dịch bị tính trùng khi nối bảng khác | JOIN một-nhiều làm tăng số hàng trước window | Kiểm tra cardinality và mức dữ liệu trước khi tính |
| SQL có frame chạy trên PostgreSQL nhưng không chạy trên SQL Server | Mức hỗ trợ RANGE/GROUPS/EXCLUDE khác nhau | Chọn cú pháp được DBMS đích hỗ trợ |
| Không lọc được bằng window trong WHERE cùng cấp | Window không được dùng trực tiếp trong WHERE PostgreSQL | Tính window trong CTE/subquery, lọc ở cấp ngoài |

## 27. Bài tập thực hành

Các bài sau dùng bảng tạm `window_frames_lab` của mục 2. Hãy **dự đoán khung chứa những hàng nào** trước khi dự đoán kết quả hàm. Khi cần thứ tự từng hàng, dùng `ORDER BY sold_on, sale_id`.

### Bài 1. Tổng toàn phân hoạch

Viết câu truy vấn trả `sale_id`, `region`, `amount` và `region_total` bằng `SUM(amount) OVER (PARTITION BY region)`. Dự đoán tổng của North và South.

### Bài 2. Khung mặc định và peers

Chạy:

```sql
SELECT sale_id, region, sold_on,
       SUM(amount) OVER (
           PARTITION BY region ORDER BY sold_on
       ) AS total_default
FROM window_frames_lab
ORDER BY region, sold_on, sale_id;
```

Vì sao sale 2 và sale 3 đều có tổng 220? Sale 7 và sale 8 có tổng bao nhiêu?

### Bài 3. Tổng tích lũy từng giao dịch

Dùng `ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW` với `ORDER BY sold_on, sale_id`. Tính tổng tới sale 2, sale 3 và sale 5 của North.

### Bài 4. Biên CURRENT ROW

Dùng `COUNT(*)` để so sánh:

- `ROWS BETWEEN CURRENT ROW AND CURRENT ROW`.
- `RANGE BETWEEN CURRENT ROW AND CURRENT ROW`.

Tại sale 2, hai biểu thức trả kết quả gì? Vì sao?

### Bài 5. Khung hai hàng

Tính `SUM(amount)` với `ROWS BETWEEN 1 PRECEDING AND CURRENT ROW`. Tại sale 3, 4, 5 và 6 của North, kết quả lần lượt là gì?

### Bài 6. Khung theo khoảng hai ngày

Dùng:

```sql
ORDER BY sold_on::TIMESTAMP
RANGE BETWEEN INTERVAL '2 days' PRECEDING AND CURRENT ROW
```

Tại ngày 03-04 của North, những ngày nào được tính? Vì sao ngày 03-01 không nằm trong khung?

### Bài 7. GROUPS so với RANGE

Viết `GROUPS BETWEEN 1 PRECEDING AND CURRENT ROW` theo `sold_on`. Tại 03-04 và 03-05 của North, nhóm peers nào nằm trong khung? Kết quả `SUM(amount)` bằng bao nhiêu?

### Bài 8. LAST_VALUE

Viết hai biểu thức `LAST_VALUE(sale_id)` cùng thứ tự `sold_on, sale_id`:

1. Không ghi frame.
2. Ghi `ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING`.

Tại sale 2, hai kết quả khác nhau ra sao? Tại mọi hàng South, biểu thức thứ hai trả giá trị gì?

### Bài 9. NTH_VALUE

Tìm `sale_id` thứ hai trong mỗi khu vực bằng `NTH_VALUE(sale_id,2)`:

1. Với khung mặc định.
2. Với khung toàn phân hoạch.

Vì sao hàng đầu của mỗi khu vực trả `NULL` trong trường hợp thứ nhất?

### Bài 10. RANK và hàng đồng hạng

Tính `ROW_NUMBER` theo `sold_on, sale_id`; `RANK` và `DENSE_RANK` theo `sold_on`. Dự đoán ba giá trị ở sale 3 và sale 4 của North.

### Bài 11. EXCLUDE

Với khung `RANGE UNBOUNDED PRECEDING ... CURRENT ROW` và `COUNT(*)`, dự đoán ở sale 2:

- Không loại hàng nào.
- `EXCLUDE CURRENT ROW`.
- `EXCLUDE GROUP`.
- `EXCLUDE TIES`.

Giải thích điều khác nhau giữa `GROUP` và `TIES`.

### Bài 12. Khung rỗng và NULL

Dùng `GROUPS BETWEEN 1 PRECEDING AND 1 PRECEDING`. Ở ngày đầu tiên của North, `COUNT(*)` và `SUM(amount)` trả gì?

### Bài 13. Báo cáo một hàng mỗi ngày

Tạo CTE `daily_sales` để gom `SUM(amount)` theo `region,sold_on`. Sau đó tính tổng ngày tích lũy bằng `ROWS`. Với North, số tiền ngày 03-02 và tổng đến ngày đó bằng bao nhiêu?

### Bài 14. Cửa sổ và lọc

Lấy **hai giao dịch sớm nhất của mỗi khu vực** theo `sold_on,sale_id`. Dùng `ROW_NUMBER` trong CTE và lọc `row_no <= 2` ở truy vấn ngoài. Vì sao không đưa trực tiếp `ROW_NUMBER()` vào `WHERE` cùng cấp của PostgreSQL?

## 28. Gợi ý lời giải

### Bài 1

```sql
SELECT sale_id, region, amount,
       SUM(amount) OVER (
           PARTITION BY region
       ) AS region_total
FROM window_frames_lab
ORDER BY region, sold_on, sale_id;
```

North = **240**, South = **190**. Không có `ORDER BY` trong cửa sổ nên tổng áp dụng cho toàn phân hoạch.

### Bài 2

Sale 2 và 3 là peers khi `ORDER BY sold_on`, cùng nằm trong khung mặc định từ đầu khu vực tới **cuối nhóm ngày 03-02**. Tổng North tới ngày đó là `100+50+70=220`. Sale 7 và 8 của South đều trả **100**.

### Bài 3

```sql
SELECT sale_id, region, amount,
       SUM(amount) OVER (
           PARTITION BY region
           ORDER BY sold_on, sale_id
           ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
       ) AS running_amount
FROM window_frames_lab
ORDER BY region, sold_on, sale_id;
```

North: sale 2 = **150**, sale 3 = **220**, sale 5 = **240**.

### Bài 4

```sql
SELECT sale_id,
       COUNT(*) OVER (
           PARTITION BY region ORDER BY sold_on
           ROWS BETWEEN CURRENT ROW AND CURRENT ROW
       ) AS rows_current,
       COUNT(*) OVER (
           PARTITION BY region ORDER BY sold_on
           RANGE BETWEEN CURRENT ROW AND CURRENT ROW
       ) AS range_current
FROM window_frames_lab
ORDER BY region, sold_on, sale_id;
```

Ở sale 2: `rows_current = 1`, `range_current = 2` vì sale 2 và 3 cùng nhóm peers theo ngày.

### Bài 5

```sql
SELECT sale_id, region, amount,
       SUM(amount) OVER (
           PARTITION BY region
           ORDER BY sold_on, sale_id
           ROWS BETWEEN 1 PRECEDING AND CURRENT ROW
       ) AS two_row_sum
FROM window_frames_lab
ORDER BY region, sold_on, sale_id;
```

North: sale 3 = **120**, sale 4 = **70**, sale 5 = **20**, sale 6 = **20**.

### Bài 6

```sql
SELECT sale_id, region, sold_on,
       SUM(amount) OVER (
           PARTITION BY region
           ORDER BY sold_on::TIMESTAMP
           RANGE BETWEEN INTERVAL '2 days' PRECEDING AND CURRENT ROW
       ) AS amount_in_range
FROM window_frames_lab
ORDER BY region, sold_on, sale_id;
```

Ở 03-04, khung là **[03-02,03-04]**: có hai giao dịch ngày 03-02 và một giao dịch `NULL` ngày 03-04; tổng là **120**. Ngày 03-01 nằm trước mốc hai ngày nên bị loại.

### Bài 7

```sql
SELECT sale_id, region, sold_on,
       SUM(amount) OVER (
           PARTITION BY region
           ORDER BY sold_on
           GROUPS BETWEEN 1 PRECEDING AND CURRENT ROW
       ) AS sum_two_peer_groups
FROM window_frames_lab
ORDER BY region, sold_on, sale_id;
```

Tại 03-04, khung gồm nhóm 03-02 và 03-04, tổng **120**. Tại 03-05, khung gồm nhóm 03-04 và 03-05, tổng **20**.

### Bài 8

```sql
SELECT sale_id, region,
       LAST_VALUE(sale_id) OVER (
           PARTITION BY region
           ORDER BY sold_on, sale_id
       ) AS last_default,
       LAST_VALUE(sale_id) OVER (
           PARTITION BY region
           ORDER BY sold_on, sale_id
           ROWS BETWEEN UNBOUNDED PRECEDING
                    AND UNBOUNDED FOLLOWING
       ) AS last_full
FROM window_frames_lab
ORDER BY region, sold_on, sale_id;
```

Sale 2 trả `last_default = 2` và `last_full = 6`. Mọi hàng South có `last_full = 10`.

### Bài 9

```sql
SELECT sale_id, region,
       NTH_VALUE(sale_id, 2) OVER (
           PARTITION BY region
           ORDER BY sold_on, sale_id
       ) AS second_default,
       NTH_VALUE(sale_id, 2) OVER (
           PARTITION BY region
           ORDER BY sold_on, sale_id
           ROWS BETWEEN UNBOUNDED PRECEDING
                    AND UNBOUNDED FOLLOWING
       ) AS second_full
FROM window_frames_lab
ORDER BY region, sold_on, sale_id;
```

Ở hàng đầu mỗi phân hoạch, khung mặc định chỉ có một hàng nên chưa có vị trí thứ hai; `second_default = NULL`. Cột `second_full` luôn bằng **2** cho North và **8** cho South.

### Bài 10

```sql
SELECT sale_id, region, sold_on,
       ROW_NUMBER() OVER (
           PARTITION BY region ORDER BY sold_on, sale_id
       ) AS row_no,
       RANK() OVER (
           PARTITION BY region ORDER BY sold_on
       ) AS rank_no,
       DENSE_RANK() OVER (
           PARTITION BY region ORDER BY sold_on
       ) AS dense_rank_no
FROM window_frames_lab
ORDER BY region, sold_on, sale_id;
```

Sale 3: `row_no = 3`, `rank_no = 2`, `dense_rank_no = 2`. Sale 4: `row_no = 4`, `rank_no = 4`, `dense_rank_no = 3`.

### Bài 11

Ở sale 2, khung ban đầu gồm sale 1, 2, 3:

- Bình thường: **3**.
- `EXCLUDE CURRENT ROW`: **2**.
- `EXCLUDE GROUP`: **1**.
- `EXCLUDE TIES`: **2**.

`GROUP` loại cả sale 2 lẫn sale 3; `TIES` chỉ loại peer còn lại, vẫn giữ sale 2.

### Bài 12

```sql
SELECT sale_id, region, sold_on,
       COUNT(*) OVER (
           PARTITION BY region
           ORDER BY sold_on
           GROUPS BETWEEN 1 PRECEDING AND 1 PRECEDING
       ) AS rows_previous_group,
       SUM(amount) OVER (
           PARTITION BY region
           ORDER BY sold_on
           GROUPS BETWEEN 1 PRECEDING AND 1 PRECEDING
       ) AS amount_previous_group
FROM window_frames_lab
ORDER BY region, sold_on, sale_id;
```

Tại nhóm ngày đầu North, không có nhóm trước đó: `rows_previous_group = 0`, `amount_previous_group = NULL`.

### Bài 13

```sql
WITH daily_sales AS (
    SELECT region,
           sold_on,
           SUM(amount) AS daily_amount
    FROM window_frames_lab
    GROUP BY region, sold_on
)
SELECT region, sold_on, daily_amount,
       SUM(daily_amount) OVER (
           PARTITION BY region
           ORDER BY sold_on
           ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
       ) AS running_daily_amount
FROM daily_sales
ORDER BY region, sold_on;
```

Ngày 03-02 của North có `daily_amount = 120`, tổng từ đầu tới hết ngày là **220**.

### Bài 14

```sql
WITH ranked_sales AS (
    SELECT sale_id, region, sold_on, amount,
           ROW_NUMBER() OVER (
               PARTITION BY region
               ORDER BY sold_on, sale_id
           ) AS row_no
    FROM window_frames_lab
)
SELECT sale_id, region, sold_on, amount
FROM ranked_sales
WHERE row_no <= 2
ORDER BY region, row_no;
```

Kết quả gồm sale **1, 2** của North và sale **7, 8** của South. PostgreSQL không cho dùng hàm cửa sổ trực tiếp trong `WHERE` cùng cấp; cần tính ở cấp trong rồi lọc ở cấp ngoài.

## 29. Tổng kết: chọn khung từ câu hỏi nghiệp vụ

Khi viết một window function, đừng chỉ hỏi “dùng hàm nào?”. Hãy xác định thêm:

1. **Phân hoạch theo gì?** Ví dụ mỗi khu vực, khách hàng, tài khoản hoặc danh mục.
2. **Thứ tự nào có ý nghĩa?** Ngày, thời điểm, số thứ tự giao dịch hay tổng điểm?
3. **Có hàng đồng hạng không?** Cùng ngày, cùng điểm, cùng mức giá là những trường hợp thường gặp.
4. **Mong muốn tính đến từng hàng hay hết cả nhóm đồng hạng?** Chọn `ROWS` hay `RANGE/GROUPS` theo đó.
5. **Offset đo bằng gì?** Số hàng, nhóm peers hay khoảng giá trị/thời gian.
6. **Hàm được chọn có phụ thuộc frame không?** `SUM`, `LAST_VALUE` và `NTH_VALUE` khác `LAG` và `RANK`.
7. **Muốn lấy cuối toàn phân hoạch hay cuối khung hiện tại?** Với `LAST_VALUE` phải chỉ rõ nếu cần `UNBOUNDED FOLLOWING`.
8. **Cần kết quả ổn định giữa các lần chạy không?** Với khung `ROWS` và hàm theo vị trí, thêm khóa phá hòa vào `ORDER BY` của cửa sổ.
9. **Có giá trị `NULL` hoặc khung rỗng không?** `COUNT(*)`, `COUNT(column)`, `SUM` có hành vi khác nhau.
10. **Hệ quản trị đích hỗ trợ frame nào?** Không giả định mọi cú pháp `RANGE`, `GROUPS` hay `EXCLUDE` đều di chuyển được.

**Quy tắc cần nhớ nhất:** trong PostgreSQL, có `ORDER BY` mà không ghi frame thì khung mặc định của các hàm sử dụng frame thường đi **từ đầu phân hoạch đến hết nhóm peers của hàng hiện tại**. Vì vậy tổng tích lũy có thể “nhảy” qua các hàng cùng ngày, còn `LAST_VALUE` có thể trả giá trị ở **cuối khung** thay vì cuối cả phân hoạch. Viết rõ `ROWS`, `RANGE` hoặc `GROUPS` cùng các biên phù hợp sẽ biến hành vi đó thành một quyết định có chủ đích, dễ giải thích và đáng tin cậy.
