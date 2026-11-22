# Khung tích lũy, khung trượt và loại trừ hàng theo phương ngữ

Giả sử một cửa hàng ghi nhận doanh số theo từng giao dịch. Báo cáo không chỉ cần doanh số **của từng giao dịch**, mà còn cần **doanh số cộng dồn đến giao dịch hiện tại**, **trung bình ba giao dịch gần nhất**, hoặc **tổng doanh số trước giao dịch này, không tính chính nó**. Khi có nhiều giao dịch cùng ngày, yêu cầu có thể là **cộng cả nhóm cùng ngày** thay vì chỉ cộng một số hàng vật lý.

Các phép tính ấy được thực hiện bằng **hàm cửa sổ** (*window functions*) và đặc biệt là **khung cửa sổ** (*window frame*). Trong một phân vùng đã được sắp thứ tự, khung quyết định **những hàng nào đóng góp vào phép tính tại mỗi hàng hiện tại**.

Bài học **Database SQL → Hàm cửa sổ** tập trung vào:

- **Khung tích lũy** (*running/cumulative frame*): từ đầu phân vùng tới vị trí hiện tại.
- **Khung trượt** (*moving/sliding frame*): vài hàng, vài nhóm giá trị bằng nhau hoặc một khoảng giá trị quanh hàng hiện tại.
- **Đơn vị khung `ROWS`, `RANGE`, `GROUPS`**: khác nhau ở cách xác định “trước”, “sau” và “hiện tại”.
- **Loại trừ hàng trong khung** với `EXCLUDE CURRENT ROW`, `EXCLUDE GROUP`, `EXCLUDE TIES` và `EXCLUDE NO OTHERS`.
- **Khác biệt giữa các hệ quản trị SQL**: không phải SQL dialect nào cũng có `GROUPS`, `EXCLUDE` hoặc khoảng `RANGE` giống PostgreSQL.

Ví dụ chính dùng **PostgreSQL**, với các kết quả được tính từ một bảng mẫu cố định. Những ví dụ ở các dialect khác được đánh dấu riêng, không trộn cú pháp không tương thích vào cùng một script.

## 1. Khung cửa sổ nằm ở đâu trong OVER?

Cú pháp điển hình:

~~~sql
SUM(amount) OVER (
    PARTITION BY store_id
    ORDER BY sale_day, sale_id
    ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
)
~~~

Đọc theo bốn phần:

1. `SUM(amount)` là phép tính cần thực hiện.
2. `PARTITION BY store_id` chia dữ liệu thành **các phân vùng**; ở đây mỗi cửa hàng được tính riêng.
3. `ORDER BY sale_day, sale_id` xác định **thứ tự logic trong từng phân vùng**. Hai giao dịch cùng ngày được phân định bằng `sale_id`.
4. `ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW` xác định **khung của từng hàng**: tất cả hàng từ đầu phân vùng đến và bao gồm hàng hiện tại.

Khái niệm cần phân biệt:

| Thành phần | Câu hỏi mà nó trả lời |
| --- | --- |
| `PARTITION BY` | Hàng hiện tại thuộc **nhóm cửa hàng nào**? |
| `ORDER BY` bên trong `OVER` | Trong nhóm ấy, **hàng nào đứng trước hàng nào**? |
| `ROWS` / `RANGE` / `GROUPS` | **Khung quanh hàng hiện tại được tính theo đơn vị nào**? |
| `BETWEEN ... AND ...` | **Khung bắt đầu và kết thúc ở đâu**? |
| `EXCLUDE ...` | Từ khung đã chọn, **bỏ hàng nào ra khỏi phép tính**? |
| `ORDER BY` cuối truy vấn | **Các hàng kết quả được hiển thị theo thứ tự nào**? |

**Hàm cửa sổ không gộp nhiều giao dịch thành một dòng** như `GROUP BY` thông thường. Mỗi giao dịch vẫn là một hàng đầu ra; hàm cửa sổ tính thêm một giá trị phụ thuộc các hàng xung quanh nó.

### 1.1. Minh họa khung di chuyển

Với doanh số một cửa hàng được sắp thứ tự:

~~~text
Giao dich:           A      B      C      D      E
So tien:            10     20     30     40     50

Hang hien tai = C

Khung tich luy:    [10     20     30]    40     50  => SUM = 60
Khung 2 hang truoc:[10     20     30]    40     50  => SUM = 60
Khung 1 truoc/1 sau:
                     10    [20     30     40]    50  => SUM = 90
~~~

Tại hàng D, khung tích lũy trở thành `10+20+30+40 = 100`, còn khung “2 hàng trước và hiện tại” trượt thành `20+30+40 = 90`. Sự khác nhau là **điểm đầu của khung có cố định ở đầu phân vùng hay di chuyển theo hàng hiện tại**.

## 2. Chuẩn bị dữ liệu mẫu có ngày trùng nhau

Để thấy rõ sự khác biệt giữa `ROWS`, `RANGE` và `GROUPS`, bảng phải có **nhiều giao dịch cùng ngày** và **khoảng trống ngày**.

Trong database **PostgreSQL thực hành riêng**, chạy đoạn khởi tạo này **một lần**, khi chưa có bảng `lab_wf242_sales`:

~~~sql
CREATE TABLE lab_wf242_sales (
    sale_id INTEGER PRIMARY KEY,
    store_id VARCHAR(10) NOT NULL,
    sale_day DATE NOT NULL,
    amount NUMERIC(12, 2) NOT NULL CHECK (amount >= 0)
);

INSERT INTO lab_wf242_sales (sale_id, store_id, sale_day, amount)
VALUES
    (101, 'A', DATE '2026-03-01', 10.00),
    (102, 'A', DATE '2026-03-02', 20.00),
    (103, 'A', DATE '2026-03-02', 30.00),
    (104, 'A', DATE '2026-03-04', 40.00),
    (105, 'A', DATE '2026-03-05', 50.00),
    (106, 'A', DATE '2026-03-08', 60.00),
    (201, 'B', DATE '2026-03-01',  5.00),
    (202, 'B', DATE '2026-03-03', 15.00),
    (203, 'B', DATE '2026-03-03', 25.00),
    (204, 'B', DATE '2026-03-07', 35.00);
~~~

Xem các hàng theo **cửa hàng, ngày và ID**:

~~~sql
SELECT sale_id, store_id, sale_day, amount
FROM lab_wf242_sales
ORDER BY store_id, sale_day, sale_id;
~~~

| sale_id | store_id | sale_day | amount |
| ---: | --- | --- | ---: |
| 101 | A | 2026-03-01 | 10.00 |
| 102 | A | 2026-03-02 | 20.00 |
| 103 | A | 2026-03-02 | 30.00 |
| 104 | A | 2026-03-04 | 40.00 |
| 105 | A | 2026-03-05 | 50.00 |
| 106 | A | 2026-03-08 | 60.00 |
| 201 | B | 2026-03-01 | 5.00 |
| 202 | B | 2026-03-03 | 15.00 |
| 203 | B | 2026-03-03 | 25.00 |
| 204 | B | 2026-03-07 | 35.00 |

Tổng doanh số cửa hàng A là **210.00**, cửa hàng B là **80.00**. Ngày **02/03** có hai giao dịch của A; ngày **03/03** có hai giao dịch của B. Cửa hàng A **không có giao dịch ngày 03/03, 06/03 và 07/03**.

Việc giữ các ngày trống là có chủ đích: một khung “ba hàng gần nhất” **không giống** một khung “ba ngày gần nhất”.

## 3. Khung tích lũy bằng ROWS

Yêu cầu: “Tại mỗi giao dịch, tính tổng doanh số **đến giao dịch đó**, riêng cho từng cửa hàng”.

~~~sql
SELECT
    store_id,
    sale_id,
    sale_day,
    amount,
    SUM(amount) OVER (
        PARTITION BY store_id
        ORDER BY sale_day, sale_id
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS running_total
FROM lab_wf242_sales
ORDER BY store_id, sale_day, sale_id;
~~~

Kết quả:

| store_id | sale_id | amount | running_total |
| --- | ---: | ---: | ---: |
| A | 101 | 10.00 | 10.00 |
| A | 102 | 20.00 | 30.00 |
| A | 103 | 30.00 | 60.00 |
| A | 104 | 40.00 | 100.00 |
| A | 105 | 50.00 | 150.00 |
| A | 106 | 60.00 | 210.00 |
| B | 201 | 5.00 | 5.00 |
| B | 202 | 15.00 | 20.00 |
| B | 203 | 25.00 | 45.00 |
| B | 204 | 35.00 | 80.00 |

`UNBOUNDED PRECEDING` nghĩa là **đầu phân vùng**, không phải “một số lượng hàng rất lớn”. `CURRENT ROW` trong khung `ROWS` nghĩa là **chính hàng hiện tại** sau khi sắp xếp.

Khi chuyển từ A sang B, tổng bắt đầu lại từ **5.00** vì có `PARTITION BY store_id`. Nếu bỏ `PARTITION BY`, phép cộng dồn diễn ra trên một phân vùng chung của tất cả cửa hàng, không còn đúng bài toán tính riêng từng cửa hàng.

### 3.1. Cú pháp rút gọn

Trong PostgreSQL, hai cách viết sau tương đương:

~~~sql
ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW

ROWS UNBOUNDED PRECEDING
~~~

Ví dụ:

~~~sql
SELECT
    sale_id,
    SUM(amount) OVER (
        PARTITION BY store_id
        ORDER BY sale_day, sale_id
        ROWS UNBOUNDED PRECEDING
    ) AS running_total
FROM lab_wf242_sales
ORDER BY store_id, sale_day, sale_id;
~~~

Viết đầy đủ `BETWEEN ... AND ...` thường rõ hơn cho người mới học vì thể hiện cả hai đầu khung.

### 3.2. Vì sao phải có sale_id trong ORDER BY của ROWS?

Cửa hàng A có hai giao dịch **cùng ngày 02/03** với số tiền 20 và 30. Nếu chỉ viết:

~~~sql
ORDER BY sale_day
ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
~~~

SQL chưa quy định **giao dịch 102 hay 103 đứng trước** trong cùng ngày. Kết quả cộng dồn của mỗi giao dịch có thể phụ thuộc thứ tự xử lý các hàng bằng nhau trong `ORDER BY`.

Viết `ORDER BY sale_day, sale_id` xác định rõ giao dịch 102 trước 103. Khi dùng `ROWS`, **khóa thứ tự nên đủ để phân định các hàng** nếu cần kết quả tái lập được trên cùng một snapshot dữ liệu.

Lưu ý: `ORDER BY` cuối `SELECT` chỉ sắp xếp các hàng được hiển thị; nó **không sửa được** việc khung `ROWS` đã tính theo một thứ tự nội bộ chưa xác định.

## 4. Mặc định của OVER có ORDER BY: bẫy RANGE và nhóm đồng hạng

Một người viết truy vấn rất ngắn:

~~~sql
SUM(amount) OVER (
    PARTITION BY store_id
    ORDER BY sale_day
)
~~~

Họ có thể kỳ vọng đây là cộng dồn **từng giao dịch**. Nhưng trong PostgreSQL, khi có `ORDER BY` mà **không khai báo frame**, mặc định tương ứng với:

~~~sql
RANGE BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
~~~

Với `RANGE`, `CURRENT ROW` ở vị trí kết thúc tính **cả những hàng đồng hạng theo `ORDER BY`** (*peers*), không chỉ một hàng vật lý.

### 4.1. So sánh mặc định RANGE với ROWS tường minh

~~~sql
SELECT
    store_id,
    sale_id,
    sale_day,
    amount,
    SUM(amount) OVER (
        PARTITION BY store_id
        ORDER BY sale_day
    ) AS default_range_total,
    SUM(amount) OVER (
        PARTITION BY store_id
        ORDER BY sale_day, sale_id
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS explicit_rows_total
FROM lab_wf242_sales
ORDER BY store_id, sale_day, sale_id;
~~~

| store_id | sale_id | sale_day | default_range_total | explicit_rows_total |
| --- | ---: | --- | ---: | ---: |
| A | 101 | 2026-03-01 | 10.00 | 10.00 |
| A | 102 | 2026-03-02 | 60.00 | 30.00 |
| A | 103 | 2026-03-02 | 60.00 | 60.00 |
| A | 104 | 2026-03-04 | 100.00 | 100.00 |
| A | 105 | 2026-03-05 | 150.00 | 150.00 |
| A | 106 | 2026-03-08 | 210.00 | 210.00 |
| B | 201 | 2026-03-01 | 5.00 | 5.00 |
| B | 202 | 2026-03-03 | 45.00 | 20.00 |
| B | 203 | 2026-03-03 | 45.00 | 45.00 |
| B | 204 | 2026-03-07 | 80.00 | 80.00 |

Ở A, hai giao dịch ngày 02/03 là **peers** vì cả hai có cùng `sale_day` khi `ORDER BY` chỉ chứa ngày. Do đó, ngay tại giao dịch 102, khung `RANGE` đã chứa **10 + 20 + 30 = 60**; giao dịch 103 cũng nhận 60.

Trong khung `ROWS` có thêm khóa `sale_id`, giao dịch 102 chỉ cộng **10 + 20 = 30**, còn giao dịch 103 cộng **10 + 20 + 30 = 60**.

**Không có một câu trả lời “luôn đúng” giữa hai cách.** Nếu báo cáo cần tổng **đến cuối ngày**, cùng một ngày nhận cùng tổng có thể chính xác. Nếu muốn tổng **sau mỗi giao dịch cụ thể**, dùng `ROWS` với thứ tự phân định rõ.

### 4.2. Peers là gì?

Trong một partition, **peers** là các hàng **bằng nhau theo tất cả biểu thức trong `ORDER BY` của cửa sổ**:

- `ORDER BY sale_day`: hai giao dịch cùng ngày là peers.
- `ORDER BY sale_day, sale_id`: vì `sale_id` duy nhất trong bảng mẫu, không còn hai giao dịch khác nhau là peers.
- Không có `ORDER BY` trong cửa sổ: về ngữ nghĩa nhóm peer, **mọi hàng trong partition** là peers.

Thêm cột phá hòa vào `ORDER BY` giúp xác định thứ tự từng giao dịch, nhưng cũng **thay đổi cách xác định nhóm peer** cho `RANGE`, `GROUPS` và `EXCLUDE TIES/GROUP`. Hãy chọn bộ cột `ORDER BY` theo đúng nghĩa nghiệp vụ, không thêm cột chỉ vì muốn kết quả “có vẻ ổn định”.

### 4.3. Không có ORDER BY trong OVER

Nếu viết:

~~~sql
SELECT
    sale_id,
    store_id,
    amount,
    SUM(amount) OVER (PARTITION BY store_id) AS store_total
FROM lab_wf242_sales
ORDER BY store_id, sale_id;
~~~

thì mọi giao dịch của A nhận **210.00**, mọi giao dịch của B nhận **80.00**. Khi cửa sổ không có `ORDER BY` và không khai báo frame khác, khung mặc định bao trùm **toàn bộ partition**.

Do vậy ba phép tính sau khác nhau:

1. `SUM(amount) OVER (PARTITION BY store_id)`: tổng **cả cửa hàng** trên mỗi hàng.
2. `SUM(amount) OVER (PARTITION BY store_id ORDER BY sale_day)`: cộng dồn **đến nhóm ngày hiện tại**, bao gồm peers.
3. `SUM(amount) OVER (PARTITION BY store_id ORDER BY sale_day, sale_id ROWS UNBOUNDED PRECEDING)`: cộng dồn **đến giao dịch hiện tại** theo thứ tự xác định.

## 5. ROWS: khung trượt theo số hàng

`ROWS` đo khoảng cách bằng **số hàng theo thứ tự của cửa sổ**, không phải số ngày hay số đơn vị giá trị.

### 5.1. Tổng ba giao dịch gần nhất

~~~sql
SELECT
    store_id,
    sale_id,
    sale_day,
    amount,
    SUM(amount) OVER (
        PARTITION BY store_id
        ORDER BY sale_day, sale_id
        ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
    ) AS last_3_sales_total,
    COUNT(*) OVER (
        PARTITION BY store_id
        ORDER BY sale_day, sale_id
        ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
    ) AS rows_in_frame
FROM lab_wf242_sales
ORDER BY store_id, sale_day, sale_id;
~~~

Kết quả:

| store_id | sale_id | amount | last_3_sales_total | rows_in_frame |
| --- | ---: | ---: | ---: | ---: |
| A | 101 | 10.00 | 10.00 | 1 |
| A | 102 | 20.00 | 30.00 | 2 |
| A | 103 | 30.00 | 60.00 | 3 |
| A | 104 | 40.00 | 90.00 | 3 |
| A | 105 | 50.00 | 120.00 | 3 |
| A | 106 | 60.00 | 150.00 | 3 |
| B | 201 | 5.00 | 5.00 | 1 |
| B | 202 | 15.00 | 20.00 | 2 |
| B | 203 | 25.00 | 45.00 | 3 |
| B | 204 | 35.00 | 75.00 | 3 |

Giải thích trường hợp A, giao dịch 104:

~~~text
101: 10
102: 20  <-- 2 PRECEDING
103: 30  <-- 1 PRECEDING
104: 40  <-- CURRENT ROW
105: 50
106: 60

Khung tai 104 = {102, 103, 104}
Tong = 20 + 30 + 40 = 90
~~~

Với giao dịch 101, **không có hai hàng trước**, nên khung chỉ chứa giao dịch 101. SQL không tự thêm hàng số tiền 0 để làm đủ ba hàng. Khi cần trung bình, `AVG(amount)` chia cho số giá trị số tiền **khác `NULL` thực sự có trong khung**, không chia mặc định cho 3.

### 5.2. Trung bình trượt

~~~sql
SELECT
    store_id,
    sale_id,
    amount,
    ROUND(
        AVG(amount) OVER (
            PARTITION BY store_id
            ORDER BY sale_day, sale_id
            ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
        ),
        2
    ) AS avg_last_3_sales
FROM lab_wf242_sales
ORDER BY store_id, sale_day, sale_id;
~~~

Với A, các giá trị lần lượt là **10.00, 15.00, 20.00, 30.00, 40.00, 50.00**:

- Giao dịch đầu: trung bình của 10 = 10.
- Giao dịch thứ hai: (10+20)/2 = 15.
- Giao dịch thứ tư: (20+30+40)/3 = 30.
- Giao dịch thứ sáu: (40+50+60)/3 = 50.

Nếu nghiệp vụ yêu cầu **chỉ hiển thị trung bình khi có đủ ba giao dịch**, hãy tách việc kiểm tra số hàng khỏi phép tính:

~~~sql
WITH moving_values AS (
    SELECT
        store_id,
        sale_id,
        sale_day,
        AVG(amount) OVER (
            PARTITION BY store_id
            ORDER BY sale_day, sale_id
            ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
        ) AS moving_avg,
        COUNT(*) OVER (
            PARTITION BY store_id
            ORDER BY sale_day, sale_id
            ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
        ) AS frame_count
    FROM lab_wf242_sales
)
SELECT
    store_id,
    sale_id,
    CASE
        WHEN frame_count = 3 THEN ROUND(moving_avg, 2)
        ELSE NULL
    END AS avg_only_full_frame
FROM moving_values
ORDER BY store_id, sale_id;
~~~

Hai giao dịch đầu mỗi cửa hàng nhận `NULL` vì **khung chưa đủ ba hàng**. Đây là **quy tắc báo cáo do chúng ta chọn**, không phải hành vi mặc định của `AVG`.

### 5.3. Khung đối xứng: một hàng trước và một hàng sau

~~~sql
SELECT
    store_id,
    sale_id,
    amount,
    SUM(amount) OVER (
        PARTITION BY store_id
        ORDER BY sale_day, sale_id
        ROWS BETWEEN 1 PRECEDING AND 1 FOLLOWING
    ) AS centered_3_rows_sum
FROM lab_wf242_sales
ORDER BY store_id, sale_day, sale_id;
~~~

Với A, kết quả theo ID 101–106 là **30, 60, 90, 120, 150, 110**. Giao dịch 103 nhận 20+30+40=90. Giao dịch 106 chỉ có hàng trước và chính nó, nên nhận 50+60=110.

Đây là khung **nhìn cả về phía sau và phía trước**. Trong báo cáo dữ liệu lịch sử hoàn chỉnh nó có thể hữu ích, nhưng trong hệ thống thời gian thực, “hàng tiếp theo” có thể **chưa xuất hiện**. Đừng gọi kết quả là “trung bình đến hiện tại” khi công thức còn sử dụng dữ liệu tương lai.

## 6. RANGE: khung trượt theo khoảng giá trị

`RANGE` khác `ROWS` ở chỗ nó xét **khoảng giá trị của biểu thức sắp xếp**, không đếm vị trí hàng. Với cột ngày/giờ, có thể dùng khoảng thời gian nếu SQL dialect hỗ trợ.

Trong PostgreSQL, một ví dụ là:

~~~sql
RANGE BETWEEN INTERVAL '2 days' PRECEDING AND CURRENT ROW
~~~

Với `ORDER BY sale_day` tăng dần, khung tại ngày D bao gồm giao dịch có ngày trong khoảng **D trừ 2 ngày** đến **D**, kể cả hai đầu mút. Tất cả giao dịch cùng ngày được xét cùng nhau.

### 6.1. Tổng doanh số trong cửa sổ ba ngày lịch

~~~sql
SELECT
    store_id,
    sale_id,
    sale_day,
    amount,
    SUM(amount) OVER (
        PARTITION BY store_id
        ORDER BY sale_day
        RANGE BETWEEN INTERVAL '2 days' PRECEDING AND CURRENT ROW
    ) AS last_3_calendar_days_total
FROM lab_wf242_sales
ORDER BY store_id, sale_day, sale_id;
~~~

Kết quả:

| store_id | sale_id | sale_day | last_3_calendar_days_total |
| --- | ---: | --- | ---: |
| A | 101 | 2026-03-01 | 10.00 |
| A | 102 | 2026-03-02 | 60.00 |
| A | 103 | 2026-03-02 | 60.00 |
| A | 104 | 2026-03-04 | 90.00 |
| A | 105 | 2026-03-05 | 90.00 |
| A | 106 | 2026-03-08 | 60.00 |
| B | 201 | 2026-03-01 | 5.00 |
| B | 202 | 2026-03-03 | 45.00 |
| B | 203 | 2026-03-03 | 45.00 |
| B | 204 | 2026-03-07 | 35.00 |

Điểm khác biệt quan trọng:

- Tại A ngày **04/03**, khoảng ba ngày lịch gồm **02/03, 03/03, 04/03**: tổng 20+30+40 = **90**.
- Tại A ngày **05/03**, khoảng gồm **03/03, 04/03, 05/03**: tổng 40+50 = **90**, dù chỉ có **hai giao dịch** vì ngày 03/03 không có giao dịch.
- Tại A ngày **08/03**, khoảng gồm **06/03, 07/03, 08/03**: chỉ có giao dịch 106 nên tổng là **60**.
- Tại B ngày **03/03**, khoảng bao gồm ngày 01/03 và 03/03 nên 5+15+25 = **45**.

So với `ROWS BETWEEN 2 PRECEDING AND CURRENT ROW`, giao dịch 106 của A có tổng **150** theo ba hàng gần nhất nhưng chỉ **60** theo ba ngày lịch. Hai con số đều đúng **theo định nghĩa khung khác nhau**.

### 6.2. Giới hạn của RANGE offset

Trong PostgreSQL, khi dùng một khoảng `PRECEDING`/`FOLLOWING` **có độ dài cụ thể** trong `RANGE`:

- Cửa sổ phải có **đúng một biểu thức `ORDER BY`** để xác định khoảng theo giá trị của biểu thức đó.
- Kiểu của offset phải phù hợp với kiểu sắp xếp: ví dụ `INTERVAL` cho ngày/giờ, số cho cột số học khi được hỗ trợ.
- Với các giá trị **bằng nhau theo `ORDER BY`**, các hàng đồng hạng được xử lý theo khung giá trị, không dựa vào ID.
- Nếu `ORDER BY` dùng `DESC`, ý nghĩa `PRECEDING`/`FOLLOWING` là theo **chiều thứ tự đã khai báo**, không được mặc định hiểu giống “ngày trước” trong thứ tự thời gian tăng dần.

Ví dụ sai khi giữ offset theo ngày nhưng thêm khóa ID:

~~~sql
-- PostgreSQL khong chap nhan RANGE offset voi hai khoa ORDER BY.
SELECT
    SUM(amount) OVER (
        PARTITION BY store_id
        ORDER BY sale_day, sale_id
        RANGE BETWEEN INTERVAL '2 days' PRECEDING AND CURRENT ROW
    )
FROM lab_wf242_sales;
~~~

Nếu cần **cửa sổ theo khoảng ngày**, chỉ dùng `ORDER BY sale_day` trong cửa sổ `RANGE`. Có thể đặt `sale_id` ở **ORDER BY cuối truy vấn** chỉ để hiển thị các giao dịch cùng ngày theo thứ tự rõ ràng; điều đó không đổi tập ngày của khung.

## 7. GROUPS: khung trượt theo các nhóm peer

`GROUPS` coi các hàng có cùng giá trị `ORDER BY` là **một nhóm đồng hạng** (*peer group*). Offset `1 PRECEDING` nghĩa là **nhóm peer trước**, bất kể nhóm đó chứa một hay nhiều hàng.

Với cửa hàng A và `ORDER BY sale_day`, các nhóm là:

~~~text
Nhom 1: 01/03 -> [101: 10]
Nhom 2: 02/03 -> [102: 20, 103: 30]
Nhom 3: 04/03 -> [104: 40]
Nhom 4: 05/03 -> [105: 50]
Nhom 5: 08/03 -> [106: 60]
~~~

Khung:

~~~sql
GROUPS BETWEEN 1 PRECEDING AND CURRENT ROW
~~~

bao gồm **nhóm ngày hiện tại** và **một nhóm ngày có giao dịch liền trước**, không nhất thiết là ngày hôm trước theo lịch.

~~~sql
SELECT
    store_id,
    sale_id,
    sale_day,
    amount,
    SUM(amount) OVER (
        PARTITION BY store_id
        ORDER BY sale_day
        GROUPS BETWEEN 1 PRECEDING AND CURRENT ROW
    ) AS current_and_previous_date_group
FROM lab_wf242_sales
ORDER BY store_id, sale_day, sale_id;
~~~

Kết quả:

| store_id | sale_id | sale_day | current_and_previous_date_group |
| --- | ---: | --- | ---: |
| A | 101 | 2026-03-01 | 10.00 |
| A | 102 | 2026-03-02 | 60.00 |
| A | 103 | 2026-03-02 | 60.00 |
| A | 104 | 2026-03-04 | 90.00 |
| A | 105 | 2026-03-05 | 90.00 |
| A | 106 | 2026-03-08 | 110.00 |
| B | 201 | 2026-03-01 | 5.00 |
| B | 202 | 2026-03-03 | 45.00 |
| B | 203 | 2026-03-03 | 45.00 |
| B | 204 | 2026-03-07 | 75.00 |

Ví dụ tại A ngày **08/03**: nhóm trước là **05/03**, nên kết quả 50+60 = **110**. Khác với `RANGE INTERVAL '2 days' PRECEDING`, vốn chỉ lấy giao dịch ngày 08/03 và trả **60** vì ngày 05/03 cách ba ngày.

Tại A ngày **04/03**, nhóm trước là **02/03** với **hai giao dịch**, nên kết quả **20+30+40 = 90**. Offset `1 PRECEDING` theo `GROUPS` không có nghĩa chỉ lấy một hàng.

### 7.1. So sánh ba loại frame trên cùng dữ liệu

| Đơn vị | Ví dụ | “2 PRECEDING” được hiểu là gì? |
| --- | --- | --- |
| `ROWS` | `ROWS BETWEEN 2 PRECEDING AND CURRENT ROW` | **Hai hàng** ngay trước trong thứ tự cửa sổ |
| `RANGE` | `RANGE BETWEEN INTERVAL '2 days' PRECEDING AND CURRENT ROW` | Các hàng có giá trị ngày trong **khoảng hai ngày** trước ngày hiện tại |
| `GROUPS` | `GROUPS BETWEEN 2 PRECEDING AND CURRENT ROW` | **Hai nhóm peer** có giá trị sắp xếp trước nhóm hiện tại |

`GROUPS` đòi hỏi một thứ tự để hình thành các nhóm peer theo cửa sổ. Với dữ liệu doanh số có nhiều giao dịch cùng ngày, `ORDER BY sale_day` tạo nhóm theo ngày. Nếu thêm `sale_id` duy nhất vào cửa sổ, mỗi hàng thành một nhóm peer riêng và khung `GROUPS` có thể giống một khung `ROWS` cùng offset trên dữ liệu đó.

## 8. Giới hạn và ý nghĩa các đầu khung

Khung có thể được khai báo bằng những biên thường gặp:

| Từ khóa/biên | Ý nghĩa |
| --- | --- |
| `UNBOUNDED PRECEDING` | Đầu phân vùng |
| `n PRECEDING` | n hàng trước (`ROWS`), n nhóm trước (`GROUPS`) hoặc n đơn vị giá trị trước (`RANGE`) |
| `CURRENT ROW` | Hàng hiện tại (`ROWS`) hoặc nhóm peers hiện tại (`RANGE`/`GROUPS`) |
| `n FOLLOWING` | n hàng/nhóm/đơn vị giá trị phía sau theo kiểu khung |
| `UNBOUNDED FOLLOWING` | Cuối phân vùng |

Ví dụ:

~~~sql
ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
ROWS BETWEEN 1 PRECEDING AND 1 FOLLOWING
ROWS BETWEEN CURRENT ROW AND UNBOUNDED FOLLOWING
ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING
~~~

Các biên phải được khai báo theo **thứ tự hợp lệ**. Không thể dùng một biên kết thúc nằm “trước” biên bắt đầu trong trật tự khung, hoặc đặt `UNBOUNDED FOLLOWING` làm biên bắt đầu. Độ dài offset phải hợp lệ theo SQL dialect và kiểu khung.

### 8.1. Tính tổng phần còn lại của phân vùng

~~~sql
SELECT
    store_id,
    sale_id,
    amount,
    SUM(amount) OVER (
        PARTITION BY store_id
        ORDER BY sale_day, sale_id
        ROWS BETWEEN CURRENT ROW AND UNBOUNDED FOLLOWING
    ) AS remaining_including_current
FROM lab_wf242_sales
ORDER BY store_id, sale_day, sale_id;
~~~

Với A, `remaining_including_current` lần lượt là **210, 200, 180, 150, 110, 60**. Tại giao dịch 103, khung gồm 103–106 nên tổng là 30+40+50+60 = **180**.

Tên “còn lại” ở đây là **còn lại trong phân vùng theo thứ tự đã định nghĩa**. Nó không đồng nghĩa “doanh thu chưa thu tiền” hoặc “dự báo doanh thu tương lai”; đó là những khái niệm nghiệp vụ khác.

## 9. EXCLUDE: loại trừ hàng ngay trong khung cửa sổ

Đôi khi ta muốn giữ nguyên khung đã xác định, nhưng **không tính một số hàng** khi áp dụng hàm tổng hợp. PostgreSQL hỗ trợ mệnh đề:

~~~sql
EXCLUDE NO OTHERS
EXCLUDE CURRENT ROW
EXCLUDE GROUP
EXCLUDE TIES
~~~

Nó xuất hiện **sau phần biên khung**:

~~~sql
SUM(amount) OVER (
    PARTITION BY store_id
    ORDER BY sale_day
    GROUPS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    EXCLUDE GROUP
)
~~~

| Lựa chọn | Những hàng bị bỏ khỏi khung đã chọn |
| --- | --- |
| `EXCLUDE NO OTHERS` | **Không bỏ hàng nào**; đây là hành vi mặc định |
| `EXCLUDE CURRENT ROW` | Bỏ **hàng hiện tại**, nhưng các peers khác có thể vẫn được tính |
| `EXCLUDE GROUP` | Bỏ **toàn bộ peer group của hàng hiện tại**, gồm cả chính nó |
| `EXCLUDE TIES` | Bỏ **những peers khác**, nhưng **giữ hàng hiện tại** nếu nó thuộc khung |

**EXCLUDE không xóa hàng khỏi kết quả `SELECT`, cũng không thay thế `WHERE`.** Nó chỉ điều chỉnh **những hàng nằm trong frame khi một hàm cửa sổ cụ thể được tính**.

### 9.1. Một ví dụ phân biệt cả bốn lựa chọn

Chỉ xét cửa hàng A. Dùng `ORDER BY sale_day` để hai giao dịch ngày 02/03 là peers. Khung được chọn là **từ đầu phân vùng đến hết nhóm ngày hiện tại**:

~~~sql
SELECT
    sale_id,
    sale_day,
    amount,
    SUM(amount) OVER (
        ORDER BY sale_day
        GROUPS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
        EXCLUDE NO OTHERS
    ) AS no_others,
    SUM(amount) OVER (
        ORDER BY sale_day
        GROUPS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
        EXCLUDE CURRENT ROW
    ) AS without_current_row,
    SUM(amount) OVER (
        ORDER BY sale_day
        GROUPS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
        EXCLUDE GROUP
    ) AS without_current_group,
    SUM(amount) OVER (
        ORDER BY sale_day
        GROUPS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
        EXCLUDE TIES
    ) AS without_other_ties
FROM lab_wf242_sales
WHERE store_id = 'A'
ORDER BY sale_day, sale_id;
~~~

Kết quả:

| sale_id | amount | no_others | without_current_row | without_current_group | without_other_ties |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 101 | 10.00 | 10.00 | `NULL` | `NULL` | 10.00 |
| 102 | 20.00 | 60.00 | 40.00 | 10.00 | 30.00 |
| 103 | 30.00 | 60.00 | 30.00 | 10.00 | 40.00 |
| 104 | 40.00 | 100.00 | 60.00 | 60.00 | 100.00 |
| 105 | 50.00 | 150.00 | 100.00 | 100.00 | 150.00 |
| 106 | 60.00 | 210.00 | 150.00 | 150.00 | 210.00 |

Giải thích hai giao dịch ngày 02/03:

~~~text
Khung chua loai tru cho ca 102 va 103:
    {101:10, 102:20, 103:30}
    SUM = 60

Tai giao dich 102:
    NO OTHERS    = 10 + 20 + 30 = 60
    CURRENT ROW  = 10 + 30      = 40  (bo 102)
    GROUP        = 10           = 10  (bo ca 102 va 103)
    TIES         = 10 + 20      = 30  (giu 102, bo peer 103)

Tai giao dich 103:
    NO OTHERS    = 10 + 20 + 30 = 60
    CURRENT ROW  = 10 + 20      = 30  (bo 103)
    GROUP        = 10           = 10  (bo ca 102 va 103)
    TIES         = 10 + 30      = 40  (giu 103, bo peer 102)
~~~

Đây là ví dụ quan trọng nhất để phân biệt `EXCLUDE CURRENT ROW`, `EXCLUDE GROUP` và `EXCLUDE TIES`: chúng **không tương đương** nếu có nhiều hàng cùng giá trị `ORDER BY`.

### 9.2. Vì sao hàng đầu có kết quả NULL khi bị loại trừ?

Ở giao dịch 101, khung ban đầu chỉ chứa **chính giao dịch 101**. Nếu dùng `EXCLUDE CURRENT ROW` hoặc `EXCLUDE GROUP`, **khung trở thành rỗng**.

Trong PostgreSQL:

- `SUM(amount)` của một frame rỗng trả về **`NULL`**.
- `AVG(amount)` của một frame rỗng trả về **`NULL`**.
- `COUNT(*)` của một frame rỗng trả về **0**.

Không nên coi `SUM = NULL` là số 0 thực tế nếu chưa quy định rõ cách xử lý trường hợp không có dữ liệu nào trong khung.

### 9.3. Tại sao EXCLUDE GROUP không giống WHERE sale_day < current_day?

Nếu mục tiêu là **doanh số ở những ngày có giao dịch trước ngày hiện tại**, `EXCLUDE GROUP` trên khung tích lũy theo nhóm có thể biểu diễn đúng ý định: bỏ **tất cả giao dịch cùng ngày** với giao dịch hiện tại.

Nhưng `WHERE sale_day < ...` không thể chỉ thêm trực tiếp ở cấp truy vấn ngoài để cho kết quả riêng cho mỗi hàng mà vẫn giữ nguyên tất cả các hàng kết quả. Muốn thay `EXCLUDE GROUP` bằng một truy vấn tương quan hoặc tổng hợp trước theo ngày, phải viết rõ liên hệ giữa ngày của hàng hiện tại và dữ liệu được xét, như phần thay thế theo phương ngữ.

## 10. EXCLUDE CURRENT ROW và cách viết thay thế bằng ROWS

Một nhu cầu hay gặp là **tổng của tất cả giao dịch trước đó, không tính giao dịch hiện tại**. Nếu thứ tự được xác định duy nhất theo `sale_day, sale_id`, có hai cách:

~~~sql
SELECT
    store_id,
    sale_id,
    amount,
    SUM(amount) OVER (
        PARTITION BY store_id
        ORDER BY sale_day, sale_id
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
        EXCLUDE CURRENT ROW
    ) AS previous_total_exclude,
    SUM(amount) OVER (
        PARTITION BY store_id
        ORDER BY sale_day, sale_id
        ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING
    ) AS previous_total_bound
FROM lab_wf242_sales
ORDER BY store_id, sale_day, sale_id;
~~~

Hai cột cùng kết quả trên bảng mẫu:

| store_id | sale_id | previous_total_exclude | previous_total_bound |
| --- | ---: | ---: | ---: |
| A | 101 | `NULL` | `NULL` |
| A | 102 | 10.00 | 10.00 |
| A | 103 | 30.00 | 30.00 |
| A | 104 | 60.00 | 60.00 |
| A | 105 | 100.00 | 100.00 |
| A | 106 | 150.00 | 150.00 |
| B | 201 | `NULL` | `NULL` |
| B | 202 | 5.00 | 5.00 |
| B | 203 | 20.00 | 20.00 |
| B | 204 | 45.00 | 45.00 |

`ROWS ... 1 PRECEDING` là một **cách thay thế có tính di động cao hơn** nếu hệ quản trị hỗ trợ `ROWS` nhưng không hỗ trợ `EXCLUDE`.

Tuy nhiên, hai cách **không đồng nghĩa trong mọi dạng frame**. Ví dụ `EXCLUDE GROUP` phải loại tất cả peers, chứ không chỉ bỏ một hàng hiện tại. Tương tự, `EXCLUDE TIES` phải bỏ các peers **khác** nhưng giữ hàng hiện tại; không thể thay máy móc bằng việc đổi biên thành `1 PRECEDING`.

## 11. Khi không có EXCLUDE: các cách biểu diễn thay thế

Một số SQL dialect hỗ trợ `ROWS`/`RANGE` nhưng **không hỗ trợ `EXCLUDE`**. Có thể diễn đạt lại một số yêu cầu bằng biên khung, truy vấn con tương quan hoặc tổng hợp trung gian. Cần kiểm tra tương đương **theo nghiệp vụ**, đặc biệt với `NULL` và các ngày trùng.

### 11.1. Tổng các giao dịch trước hiện tại, không dùng EXCLUDE

Cách đơn giản nhất dùng `ROWS` và biên kết thúc ở một hàng trước:

~~~sql
SELECT
    store_id,
    sale_id,
    SUM(amount) OVER (
        PARTITION BY store_id
        ORDER BY sale_day, sale_id
        ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING
    ) AS previous_total
FROM lab_wf242_sales
ORDER BY store_id, sale_day, sale_id;
~~~

Khung rỗng của giao dịch đầu vẫn cho `SUM = NULL`, tương ứng với ý nghĩa “chưa có giao dịch nào trước đó”.

### 11.2. Tổng của những ngày trước, bỏ tất cả peers cùng ngày

Một cách tương đối phổ biến giữa các hệ quản trị là **truy vấn con tương quan**:

~~~sql
SELECT
    s.store_id,
    s.sale_id,
    s.sale_day,
    s.amount,
    (
        SELECT SUM(p.amount)
        FROM lab_wf242_sales AS p
        WHERE p.store_id = s.store_id
          AND p.sale_day < s.sale_day
    ) AS total_before_today
FROM lab_wf242_sales AS s
ORDER BY s.store_id, s.sale_day, s.sale_id;
~~~

Ví dụ tại A ngày 02/03, cả giao dịch 102 và 103 có `total_before_today = 10`. Tại ngày 04/03, kết quả là **60** (10+20+30). Không có giao dịch nào trước ngày 01/03 nên giá trị giao dịch 101 là `NULL`.

Truy vấn này gần ý nghĩa với `GROUPS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW EXCLUDE GROUP` khi `ORDER BY` chỉ theo ngày và số tiền không `NULL`, nhưng nó không sử dụng cú pháp `EXCLUDE`. Điểm đánh đổi là một correlated subquery có thể tốn chi phí trên dữ liệu lớn; bộ tối ưu có thể xử lý khác nhau giữa các hệ.

### 11.3. Tổng theo nhóm ngày rồi cộng dồn ở cấp ngày

Nếu báo cáo **theo ngày**, thay vì từng giao dịch, có thể nhóm trước:

~~~sql
WITH daily AS (
    SELECT store_id, sale_day, SUM(amount) AS daily_total
    FROM lab_wf242_sales
    GROUP BY store_id, sale_day
)
SELECT
    store_id,
    sale_day,
    daily_total,
    SUM(daily_total) OVER (
        PARTITION BY store_id
        ORDER BY sale_day
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS cumulative_daily_total
FROM daily
ORDER BY store_id, sale_day;
~~~

Ở A, ngày 02/03 có `daily_total = 50` và `cumulative_daily_total = 60`. Khác với bảng giao dịch, truy vấn trả **một dòng cho mỗi cặp (cửa hàng, ngày)**. Đây là cách thích hợp nếu đơn vị báo cáo thật sự là **ngày**; đừng dùng nó khi vẫn cần một dòng cho từng giao dịch mà chưa có bước ghép kết quả ngày trở lại các giao dịch.

### 11.4. Đừng trừ amount khỏi tổng rồi coi luôn là EXCLUDE

Với `amount NOT NULL` và phép `SUM` cộng dồn, có thể có ý tưởng:

~~~sql
SUM(amount) OVER (...) - amount
~~~

Giá trị số học của cách trừ ấy có thể bằng tổng trước hàng hiện tại, nhưng **không phải phép thay thế hoàn toàn tương đương** về ngữ nghĩa SQL:

- Với hàng đầu tiên, phép trừ cho **0**, trong khi `SUM` trên khung rỗng trả **NULL**.
- Nếu `amount` có thể `NULL`, phép trừ có thể tạo `NULL` ngay cả khi tổng các hàng trước đã biết.
- Với `EXCLUDE GROUP` hoặc `EXCLUDE TIES`, phải tính đến **cả peer group**, không chỉ giá trị của hàng hiện tại.
- Với các hàm khác như `AVG`, không thể sửa bằng trừ một giá trị rồi giữ nguyên mẫu số.

Khi cần bảo toàn quy tắc khung rỗng, peers và giá trị thiếu, nên dùng biên `ROWS`, tổng hợp theo ngày, hoặc biểu thức tương quan được xác định rõ.

## 12. FIRST_VALUE, LAST_VALUE và mặc định khung

Không phải chỉ `SUM` hoặc `AVG` mới chịu ảnh hưởng của frame. Các hàm như `FIRST_VALUE`, `LAST_VALUE` và `NTH_VALUE` cũng đọc giá trị trong **khung hiện tại**.

### 12.1. LAST_VALUE không tự có nghĩa “hàng cuối phân vùng”

~~~sql
SELECT
    store_id,
    sale_id,
    amount,
    LAST_VALUE(amount) OVER (
        PARTITION BY store_id
        ORDER BY sale_day, sale_id
    ) AS last_in_default_frame,
    LAST_VALUE(amount) OVER (
        PARTITION BY store_id
        ORDER BY sale_day, sale_id
        ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING
    ) AS last_in_partition
FROM lab_wf242_sales
ORDER BY store_id, sale_day, sale_id;
~~~

Vì `ORDER BY sale_day, sale_id` xác định thứ tự riêng cho từng giao dịch, khung mặc định kết thúc ở **hàng hiện tại**. Do đó `last_in_default_frame` của A tại giao dịch 102 là **20.00**, không phải doanh số giao dịch cuối cùng của A.

Ngược lại, khung `ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING` bao trùm **toàn phân vùng**, nên `last_in_partition` của mọi giao dịch A là **60.00**, của mọi giao dịch B là **35.00**.

Điều này rất quan trọng khi viết báo cáo “giá trị đầu kỳ/cuối kỳ”. `LAST_VALUE` lấy **hàng cuối khung**, không tự tìm “giá trị cuối của cả nhóm” nếu khung chưa bao trùm toàn bộ nhóm.

### 12.2. Hàm xếp hạng và LAG/LEAD không hoạt động như SUM theo frame

Trong PostgreSQL, `ROW_NUMBER`, `RANK`, `DENSE_RANK` cũng như `LAG`/`LEAD` được định nghĩa theo **phân vùng và thứ tự cửa sổ**; chúng **không dùng frame giống `SUM`/`AVG` hoặc `LAST_VALUE`**. Đừng thêm `ROWS BETWEEN ...` rồi kỳ vọng `LAG` chỉ được nhìn hai hàng của frame, hoặc `ROW_NUMBER` sẽ bắt đầu lại mỗi khi frame trượt.

Nếu muốn lấy số tiền giao dịch trước, có thể dùng:

~~~sql
SELECT
    store_id,
    sale_id,
    amount,
    LAG(amount) OVER (
        PARTITION BY store_id
        ORDER BY sale_day, sale_id
    ) AS previous_amount
FROM lab_wf242_sales
ORDER BY store_id, sale_day, sale_id;
~~~

Đó là phép tham chiếu một hàng trước trong thứ tự của partition, **khác** bài toán tổng nhiều hàng trong một frame.

## 13. Phạm vi xử lý: WHERE, GROUP BY, HAVING và ORDER BY

Một phép `OVER` được đánh giá trên **những hàng đã đi qua các giai đoạn lọc/nhóm tương ứng** của cấp truy vấn. Điều này tạo ra những điểm dễ nhầm.

### 13.1. WHERE lọc hàng trước khi tính window ở cùng cấp

~~~sql
SELECT
    sale_id,
    sale_day,
    amount,
    SUM(amount) OVER (
        ORDER BY sale_day, sale_id
        ROWS UNBOUNDED PRECEDING
    ) AS running_total
FROM lab_wf242_sales
WHERE store_id = 'A'
  AND sale_day >= DATE '2026-03-04'
ORDER BY sale_day, sale_id;
~~~

Truy vấn chỉ giữ ba giao dịch **104, 105, 106** trước khi tính window. Tổng cộng dồn vì vậy lần lượt là **40, 90, 150**, không phải 100, 150, 210 như khi tính trên **toàn bộ lịch sử** của A.

Nếu yêu cầu là “tính tổng cộng dồn từ đầu lịch sử, **sau đó chỉ hiển thị từ ngày 04/03**”, dùng truy vấn con/CTE để tách hai cấp:

~~~sql
WITH running AS (
    SELECT
        store_id, sale_id, sale_day, amount,
        SUM(amount) OVER (
            PARTITION BY store_id
            ORDER BY sale_day, sale_id
            ROWS UNBOUNDED PRECEDING
        ) AS running_total
    FROM lab_wf242_sales
)
SELECT sale_id, sale_day, amount, running_total
FROM running
WHERE store_id = 'A'
  AND sale_day >= DATE '2026-03-04'
ORDER BY sale_day, sale_id;
~~~

Lúc này kết quả các giao dịch **104, 105, 106** có tổng **100, 150, 210**. Cùng một điều kiện ngày nhưng đặt ở **hai cấp truy vấn khác nhau** làm phạm vi cộng dồn thay đổi.

### 13.2. Không dùng window function trực tiếp trong WHERE cùng cấp

Ví dụ sau **không hợp lệ** trong PostgreSQL:

~~~sql
-- SAI: window function khong thuoc giai doan WHERE cung cap.
SELECT sale_id, amount
FROM lab_wf242_sales
WHERE SUM(amount) OVER (
    PARTITION BY store_id
    ORDER BY sale_day, sale_id
    ROWS UNBOUNDED PRECEDING
) >= 100;
~~~

Muốn lọc theo giá trị cửa sổ, tính nó trong CTE/truy vấn con rồi `WHERE` ở cấp ngoài:

~~~sql
WITH running AS (
    SELECT
        store_id, sale_id, sale_day, amount,
        SUM(amount) OVER (
            PARTITION BY store_id
            ORDER BY sale_day, sale_id
            ROWS UNBOUNDED PRECEDING
        ) AS running_total
    FROM lab_wf242_sales
)
SELECT store_id, sale_id, running_total
FROM running
WHERE running_total >= 100
ORDER BY store_id, sale_day, sale_id;
~~~

Kết quả là giao dịch **104, 105, 106** của A, với các tổng **100, 150, 210**. B chưa đạt 100 trên dữ liệu mẫu.

### 13.3. ORDER BY trong OVER khác ORDER BY cuối truy vấn

~~~sql
SELECT
    sale_id,
    sale_day,
    amount,
    SUM(amount) OVER (
        PARTITION BY store_id
        ORDER BY sale_day, sale_id
        ROWS UNBOUNDED PRECEDING
    ) AS running_total
FROM lab_wf242_sales
ORDER BY amount DESC, sale_id DESC;
~~~

Kết quả được **hiển thị theo số tiền giảm dần**, nhưng `running_total` vẫn được tính theo **ngày rồi ID tăng dần trong từng cửa hàng**. Hai mệnh đề sắp xếp phục vụ **hai nhiệm vụ khác nhau**.

## 14. Đặt tên window khi có nhiều phép tính chung phạm vi

Khi cần cùng lúc cộng dồn, tổng trượt và trung bình trượt, truy vấn có thể lặp nhiều lần `PARTITION BY` và `ORDER BY`. PostgreSQL hỗ trợ mệnh đề `WINDOW` để đặt tên các cấu hình:

~~~sql
SELECT
    store_id,
    sale_id,
    sale_day,
    amount,
    SUM(amount) OVER w_running AS running_total,
    SUM(amount) OVER w_recent AS last_3_total,
    ROUND(AVG(amount) OVER w_recent, 2) AS last_3_average
FROM lab_wf242_sales
WINDOW
    w_running AS (
        PARTITION BY store_id
        ORDER BY sale_day, sale_id
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ),
    w_recent AS (
        PARTITION BY store_id
        ORDER BY sale_day, sale_id
        ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
    )
ORDER BY store_id, sale_day, sale_id;
~~~

Ví dụ tại giao dịch A–104, ba giá trị là:

- `running_total = 100.00`.
- `last_3_total = 90.00`.
- `last_3_average = 30.00`.

Mệnh đề `WINDOW` không tạo bảng lưu trữ mới. Nó giúp đặt tên cửa sổ để tái sử dụng trong cùng câu `SELECT`. Quy tắc kế thừa/ghi đè các thành phần của cửa sổ có chi tiết theo hệ quản trị, nên với bài này dùng **hai cấu hình tường minh** thay vì cố mở rộng một window đã có frame.

## 15. NULL, frame rỗng và giá trị không có giao dịch

Bảng `lab_wf242_sales` cố ý có `amount NOT NULL`, giúp quan sát logic khung mà không lẫn dữ liệu thiếu. Với bảng thực tế có giá trị `NULL`, cần phân biệt **ba khái niệm**:

1. **Khung chứa hàng**: xác định bởi `ROWS`, `RANGE` hoặc `GROUPS` và có thể bị chỉnh bởi `EXCLUDE`.
2. **Khung chứa bao nhiêu giá trị `amount` không NULL**: có thể ít hơn số hàng.
3. **Ngày không có giao dịch**: không có hàng nào để tạo ra một kết quả cửa sổ, trừ khi ta **tạo trước một trục ngày lịch**.

Ví dụ độc lập có thể chạy trên PostgreSQL:

~~~sql
WITH sample(seq, amount) AS (
    VALUES
        (1, 10::numeric),
        (2, NULL::numeric),
        (3, 30::numeric)
)
SELECT
    seq,
    amount,
    COUNT(*) OVER (
        ORDER BY seq ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
    ) AS row_count,
    COUNT(amount) OVER (
        ORDER BY seq ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
    ) AS known_amount_count,
    SUM(amount) OVER (
        ORDER BY seq ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
    ) AS amount_sum,
    AVG(amount) OVER (
        ORDER BY seq ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
    ) AS amount_avg
FROM sample
ORDER BY seq;
~~~

| seq | amount | row_count | known_amount_count | amount_sum | amount_avg |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | 10 | 1 | 1 | 10 | 10 |
| 2 | `NULL` | 2 | 1 | 10 | 10 |
| 3 | 30 | 3 | 2 | 40 | 20 |

`COUNT(*)` đếm **hàng trong frame**, trong khi `COUNT(amount)` chỉ đếm những hàng có số tiền khác `NULL`. `SUM` và `AVG` bỏ qua những giá trị số tiền `NULL`. Khi tất cả số tiền trong frame đều `NULL` hoặc frame rỗng, `SUM`/`AVG` trả `NULL`; `COUNT(*)` của frame rỗng trả 0.

### 15.1. “Không có giao dịch hôm qua” khác “doanh số hôm qua bằng 0”

Nếu dùng `ROWS BETWEEN 2 PRECEDING AND CURRENT ROW` trên bảng giao dịch, SQL chỉ đếm **các hàng thực có**. Nếu cần **trung bình trượt theo ngày lịch** gồm cả ngày có doanh số 0, cần tạo danh sách ngày, nối hoặc tổng hợp doanh số mỗi ngày, rồi áp dụng frame trên **mỗi ngày một hàng**.

Ví dụ PostgreSQL minh họa cho **cửa hàng A** trong khoảng 01/03–08/03:

~~~sql
WITH calendar AS (
    SELECT d::date AS day_value
    FROM generate_series(
        DATE '2026-03-01',
        DATE '2026-03-08',
        INTERVAL '1 day'
    ) AS g(d)
),
daily AS (
    SELECT sale_day, SUM(amount) AS daily_amount
    FROM lab_wf242_sales
    WHERE store_id = 'A'
    GROUP BY sale_day
),
calendar_daily AS (
    SELECT
        c.day_value,
        COALESCE(d.daily_amount, 0) AS daily_amount
    FROM calendar AS c
    LEFT JOIN daily AS d
        ON d.sale_day = c.day_value
)
SELECT
    day_value,
    daily_amount,
    SUM(daily_amount) OVER (
        ORDER BY day_value
        ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
    ) AS last_3_calendar_days
FROM calendar_daily
ORDER BY day_value;
~~~

Ngày 03/03, 06/03 và 07/03 được tạo từ lịch, có doanh số 0 theo **quy ước cho ngày không có giao dịch**. Trên tập lịch mỗi ngày đúng một hàng, `ROWS 2 PRECEDING` bây giờ tương ứng với **ba ngày liên tiếp**. Đây là cách hữu ích khi cần hiện cả ngày trống trên biểu đồ, nhưng chỉ nên coi ngày không có giao dịch là 0 khi nghiệp vụ và quy trình nhập liệu bảo đảm điều đó.

`generate_series` là hàm tiện ích của PostgreSQL; các hệ quản trị khác cần bảng ngày hoặc cách tạo dãy ngày phù hợp.

## 16. Khác biệt theo SQL dialect

Cú pháp khung cửa sổ không đồng nhất giữa các hệ quản trị. Một đoạn SQL dùng `EXCLUDE TIES` ở PostgreSQL không được mặc định là chạy được trên MySQL hoặc SQL Server.

| Hệ quản trị / phiên bản | `ROWS` | `RANGE` | `GROUPS` | `EXCLUDE` | Ghi chú thực hành |
| --- | --- | --- | --- | --- | --- |
| **PostgreSQL 11+** | Có | Có, hỗ trợ các offset phù hợp với kiểu `ORDER BY` | Có | Có các lựa chọn `NO OTHERS`, `CURRENT ROW`, `GROUP`, `TIES` | Ví dụ `INTERVAL '2 days'` với ngày/giờ và `IS DISTINCT FROM` là cú pháp PostgreSQL |
| **SQLite 3.28.0+** | Có | Có | Có | Có | Các biểu thức ngày/giờ, kiểu dữ liệu và offset `RANGE` cần điều chỉnh theo mô hình giá trị của SQLite |
| **MySQL 8.0** | Có | Có với các giới hạn của dialect | Không có cú pháp `GROUPS` | Không hỗ trợ `EXCLUDE` như PostgreSQL | Dùng `ROWS`, `RANGE` hoặc truy vấn/tổng hợp phụ để thay thế |
| **SQL Server (T-SQL)** | Có | Có nhưng các biên `RANGE` được hỗ trợ hạn chế hơn, không dùng tùy ý `n PRECEDING` như PostgreSQL | Không hỗ trợ `GROUPS` theo cú pháp PostgreSQL | Không hỗ trợ `EXCLUDE` theo cú pháp PostgreSQL | Thường dùng `ROWS`, CTE hoặc truy vấn tương quan khi cần khung theo thời gian |
| **Oracle Database** | Có | Có | Các phiên bản hiện đại có hỗ trợ khung nhóm; kiểm tra phiên bản cụ thể | Cú pháp/khả năng loại trừ phụ thuộc phiên bản; không suy luận từ PostgreSQL | Oracle có cú pháp analytic nâng cao nhưng khác chi tiết hỗ trợ từng bản |

**Ghi chú phiên bản:** bảng trên mô tả các khả năng phổ biến của họ hệ quản trị và các mốc phiên bản nêu rõ, không thay thế tài liệu của **đúng phiên bản máy chủ đang chạy**. Khi port một báo cáo, kiểm tra cả cú pháp và **ngữ nghĩa peer, NULL, offset, mặc định frame**, không chỉ xem truy vấn có chạy thành công hay không.

### 16.1. PostgreSQL: hỗ trợ nhiều đơn vị và EXCLUDE

Ví dụ PostgreSQL đầy đủ:

~~~sql
SELECT
    sale_id,
    SUM(amount) OVER (
        PARTITION BY store_id
        ORDER BY sale_day
        GROUPS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
        EXCLUDE GROUP
    ) AS total_of_prior_date_groups
FROM lab_wf242_sales
ORDER BY store_id, sale_day, sale_id;
~~~

Ở cửa hàng A ngày 02/03, kết quả cho hai giao dịch 102 và 103 đều là **10.00**. Đây không phải “tổng trước một hàng”, mà là **tổng trước nhóm ngày hiện tại**.

### 16.2. MySQL: dùng ROWS cho khung theo số hàng

Ví dụ dạng có thể áp dụng trong MySQL 8.0 khi bảng nguồn và cột tương ứng tồn tại:

~~~sql
SELECT
    store_id,
    sale_id,
    amount,
    SUM(amount) OVER (
        PARTITION BY store_id
        ORDER BY sale_day, sale_id
        ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
    ) AS last_3_total
FROM lab_wf242_sales
ORDER BY store_id, sale_day, sale_id;
~~~

Đối với phép tính theo nhóm ngày hoặc loại trừ peers trong MySQL, không thể chỉ thay chữ `GROUPS` bằng `ROWS`: phải xem lại dữ liệu và tính toán tương ứng, ví dụ tổng hợp theo ngày trước hoặc dùng truy vấn tương quan.

### 16.3. SQL Server: ROWS phổ biến hơn RANGE có offset

Mẫu T-SQL có thể viết:

~~~sql
-- Vi du T-SQL, gia dinh co dbo.sales voi cac cot tuong ung.
SELECT
    store_id,
    sale_id,
    amount,
    SUM(amount) OVER (
        PARTITION BY store_id
        ORDER BY sale_day, sale_id
        ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
    ) AS last_3_total
FROM dbo.sales
ORDER BY store_id, sale_day, sale_id;
~~~

Tuy nhiên, không thể giả định rằng:

~~~sql
-- Khong chuyen nguyen xi tu PostgreSQL sang T-SQL:
RANGE BETWEEN INTERVAL '2 days' PRECEDING AND CURRENT ROW
~~~

là cú pháp hợp lệ trên SQL Server. Với yêu cầu khoảng ngày, có thể tính theo điều kiện ngày trong truy vấn tương quan hoặc dùng bảng ngày và khung `ROWS` trên dữ liệu **đã được quy về một hàng cho mỗi ngày**.

### 16.4. SQLite: GROUPS và EXCLUDE có ở các bản phù hợp

SQLite mới hỗ trợ `GROUPS` và các dạng `EXCLUDE` trong window frame, nhưng không cung cấp tất cả cú pháp kiểu dữ liệu của PostgreSQL. Ví dụ mệnh đề:

~~~sql
GROUPS BETWEEN 1 PRECEDING AND CURRENT ROW
EXCLUDE TIES
~~~

có thể dùng trong cửa sổ phù hợp của SQLite phiên bản hỗ trợ. Ngược lại, offset thời gian `INTERVAL '2 days'` không phải cú pháp có thể mang nguyên sang SQLite; cần hiểu cách lưu ngày (văn bản ISO-8601, số Julian, Unix timestamp...) trước khi xác định khoảng `RANGE`.

### 16.5. Cách chọn phương án dễ chuyển hệ

| Nhu cầu | Phương án khi ưu tiên khả năng chuyển hệ |
| --- | --- |
| Cộng dồn mỗi giao dịch | `ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW` với thứ tự có khóa phân định |
| Tổng ba giao dịch gần nhất | `ROWS BETWEEN 2 PRECEDING AND CURRENT ROW` |
| Tổng trước giao dịch hiện tại | `ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING` |
| Tổng theo ba ngày lịch | Điều kiện ngày trong correlated subquery; hoặc tạo tập ngày một hàng/ngày rồi dùng `ROWS` |
| Tổng theo nhóm các giá trị bằng nhau | Tổng hợp một hàng cho mỗi nhóm, rồi tính khung trên bảng nhóm |
| Bỏ toàn bộ ngày hiện tại | Correlated subquery với điều kiện `other.sale_day < current.sale_day` hoặc phép tổng hợp theo ngày |
| Bỏ peers nhưng giữ hàng hiện tại | Đòi hỏi mô tả rõ peer group và phép tính; dùng `EXCLUDE TIES` nếu có, nếu không xây phương án tương đương phù hợp với từng hàm |

## 17. Hiệu năng và sự ổn định của kết quả

Hàm cửa sổ thường cần xử lý hàng theo `PARTITION BY` và `ORDER BY`. Khi có nhiều khung trong một truy vấn, máy chủ có thể phải thực hiện thêm các thao tác sắp xếp, quản lý trạng thái hoặc bộ đệm.

### 17.1. Chỉ mục và thứ tự

Với các truy vấn trên bảng mẫu, một chỉ mục có thể phù hợp trong một số tải thực tế là:

~~~sql
-- DDL minh hoa: khong bat buoc cho bai thuc hanh.
CREATE INDEX lab_wf242_store_day_id_idx
ON lab_wf242_sales (store_id, sale_day, sale_id);
~~~

Chỉ mục theo **cửa hàng → ngày → ID** có thể giúp một số truy vấn lọc và sắp xếp theo những cột đó. Nhưng điều này **không bảo đảm** PostgreSQL sẽ bỏ qua mọi bước sắp xếp hoặc dùng chỉ mục trong tất cả câu có window: kế hoạch còn tùy số hàng, thống kê, chi phí đọc và các biểu thức cụ thể.

Trên bảng chỉ mười hàng, một quét tuần tự kèm sắp xếp nhỏ thường hoàn toàn hợp lý. Không nên tạo nhiều chỉ mục chỉ để làm nhanh bài thực hành.

### 17.2. Quan sát kế hoạch bằng EXPLAIN

~~~sql
EXPLAIN
SELECT
    sale_id,
    SUM(amount) OVER (
        PARTITION BY store_id
        ORDER BY sale_day, sale_id
        ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
    ) AS last_3_total
FROM lab_wf242_sales;
~~~

`EXPLAIN` của PostgreSQL có thể thể hiện bước `WindowAgg` và cách sắp xếp/truy cập dữ liệu. Nó dùng để hiểu **kế hoạch dự kiến**; kết quả thực tế khác nhau giữa tập thử nhỏ và bảng sản xuất.

### 17.3. Tránh cộng dồn sai do fan-out JOIN

Nếu trước khi tính cửa sổ bạn nối mỗi giao dịch với nhiều hàng chi tiết, một giao dịch có thể bị **nhân thành nhiều hàng**. Khi đó `ROWS 2 PRECEDING` đếm **các hàng sau JOIN**, không còn đếm ba giao dịch thực.

Trước khi dùng window frame, cần xác định **độ hạt** (*grain*) của dữ liệu đầu vào: một hàng là một giao dịch, một dòng sản phẩm hay một ngày? Nếu cần cộng dồn theo giao dịch, có thể phải tổng hợp bảng chi tiết về **một hàng cho mỗi `sale_id`** trước khi áp dụng cửa sổ.

### 17.4. OFFSET, bản ghi mới và thứ tự xác định

Các báo cáo có phân trang và sắp theo `sale_day, sale_id` có thứ tự xác định trên **một trạng thái dữ liệu cố định**. Tuy nhiên, nếu phát sinh giao dịch mới chèn vào giữa các trang, vị trí các hàng có thể đổi. Cùng một truy vấn có thể tính lại frame khác nếu dữ liệu thay đổi.

Với báo cáo kỳ đã khóa sổ, có thể phù hợp hơn khi dùng snapshot ổn định; với dữ liệu thời gian thực, cần chấp nhận cập nhật hoặc thiết kế cách truy xuất nhất quán phù hợp.

## 18. Những lỗi thường gặp

| Cách viết hoặc cách hiểu | Vấn đề | Cách sửa |
| --- | --- | --- |
| `SUM(amount) OVER (ORDER BY sale_day)` và kỳ vọng cộng từng giao dịch | Khung mặc định `RANGE` bao gồm tất cả peers cùng ngày | Nếu cần từng giao dịch: `ROWS UNBOUNDED PRECEDING` với `ORDER BY sale_day, sale_id` |
| `ROWS BETWEEN 2 PRECEDING AND CURRENT ROW` để tính “ba ngày lịch” | Hai ngày trống hoặc nhiều giao dịch cùng ngày làm khác số ngày | Dùng `RANGE INTERVAL` khi dialect hỗ trợ hoặc tạo trục ngày |
| `ORDER BY depth` / `ORDER BY sale_day` mà bỏ khóa phá hòa cho `ROWS` | Các hàng bằng khóa không có thứ tự nội bộ xác định | Thêm khóa định danh ổn định khi muốn đếm theo hàng |
| `ORDER BY sale_day, sale_id` trong `RANGE INTERVAL '2 days'` PostgreSQL | `RANGE` với offset cần một khóa `ORDER BY` | Chỉ `ORDER BY sale_day` trong cửa sổ giá trị thời gian |
| `GROUPS 1 PRECEDING` được hiểu là một hàng trước | Một peer group có thể gồm nhiều hàng | Phân biệt số nhóm với số hàng |
| `EXCLUDE CURRENT ROW` được hiểu là bỏ cả giao dịch cùng ngày | Chỉ bỏ chính hàng hiện tại | Dùng `EXCLUDE GROUP` để bỏ cả peer group |
| `EXCLUDE TIES` được hiểu là bỏ cả chính hàng hiện tại | TIES giữ chính hàng hiện tại, bỏ những peers khác | Dùng `EXCLUDE GROUP` nếu muốn bỏ cả nhóm |
| `SUM` của frame rỗng được cho bằng 0 | `SUM` trả `NULL` khi không có giá trị để cộng | Giữ `NULL` hoặc `COALESCE` theo nghiệp vụ |
| `COUNT(*)` và `COUNT(amount)` luôn bằng nhau | Hàng có `amount IS NULL` vẫn được `COUNT(*)` đếm | Chọn hàm đếm phù hợp |
| Thêm `WHERE sale_day >= ...` rồi mong running total vẫn tính từ đầu lịch sử | `WHERE` lọc đầu vào trước khi window cùng cấp chạy | Tính window trong CTE, rồi lọc ngày ở truy vấn ngoài |
| Dùng window function trực tiếp trong `WHERE` cùng cấp | Không hợp lệ trong PostgreSQL | Tính trong CTE/subquery rồi lọc ngoài |
| `LAST_VALUE(amount)` được cho là giá trị cuối phân vùng | Default frame có thể kết thúc ở hàng hoặc peer hiện tại | Khai báo khung đến `UNBOUNDED FOLLOWING` |
| Mang `EXCLUDE` PostgreSQL sang MySQL/SQL Server | Cú pháp không được hỗ trợ tương tự | Dùng biên `ROWS` hoặc thay bằng truy vấn tương đương |
| Dùng một hàm băm hoặc trừ số tiền để mô phỏng mọi loại `EXCLUDE` | Không xử lý đúng peers, frame rỗng, NULL hoặc AVG | Thiết kế thay thế theo đúng phép tính và định nghĩa khung |
| Đặt `ORDER BY` ở cuối và tưởng nó xác định khung | `ORDER BY` cuối chỉ sắp hiển thị; thứ tự frame nằm trong `OVER` | Viết rõ cả hai nếu cần |

## 19. Bài tập thực hành có đáp án

Các bài dùng dữ liệu `lab_wf242_sales` ở mục 2, trừ nơi ghi rõ là ví dụ độc lập. Hãy dự đoán **khung chứa những hàng nào** trước khi tính số tiền; làm như vậy sẽ ít nhầm lẫn hơn việc chỉ nhớ công thức.

### Bài 1 — Cộng dồn theo từng giao dịch

**Yêu cầu:** viết query trả `store_id`, `sale_id`, `amount` và `running_total` theo từng cửa hàng; các giao dịch cùng ngày phải theo ID tăng.

**Đáp án:**

~~~sql
SELECT
    store_id,
    sale_id,
    amount,
    SUM(amount) OVER (
        PARTITION BY store_id
        ORDER BY sale_day, sale_id
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS running_total
FROM lab_wf242_sales
ORDER BY store_id, sale_day, sale_id;
~~~

Với A, các tổng lần lượt **10, 30, 60, 100, 150, 210**. Với B: **5, 20, 45, 80**.

### Bài 2 — Tổng của ba giao dịch gần nhất

**Yêu cầu:** tìm tổng ba giao dịch tính cả hiện tại, không phụ thuộc khoảng cách ngày.

**Đáp án:**

~~~sql
SELECT
    store_id,
    sale_id,
    SUM(amount) OVER (
        PARTITION BY store_id
        ORDER BY sale_day, sale_id
        ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
    ) AS last_3_total
FROM lab_wf242_sales
ORDER BY store_id, sale_day, sale_id;
~~~

Tại A–106, kết quả **150** vì ba giao dịch cuối là 104, 105, 106 có tiền 40+50+60. Đây không phải tổng ba ngày lịch cuối.

### Bài 3 — Mặc định RANGE khi trùng ngày

**Câu hỏi:** hai biểu thức sau có luôn cùng kết quả tại giao dịch A–102 không?

~~~sql
SUM(amount) OVER (
    PARTITION BY store_id ORDER BY sale_day
)

SUM(amount) OVER (
    PARTITION BY store_id ORDER BY sale_day, sale_id
    ROWS UNBOUNDED PRECEDING
)
~~~

**Đáp án:** **không**. Biểu thức đầu dùng khung `RANGE` mặc định, bao cả giao dịch 102 và 103 cùng ngày, nên cho **60** ở 102. Biểu thức `ROWS` có ID phân định cho **30** tại 102. Cả hai cho 60 tại 103.

### Bài 4 — Khung đối xứng

**Yêu cầu:** tại A–104 (40), tính tổng của một hàng trước, hiện tại và một hàng sau.

**Đáp án:**

~~~sql
SELECT
    sale_id,
    SUM(amount) OVER (
        PARTITION BY store_id
        ORDER BY sale_day, sale_id
        ROWS BETWEEN 1 PRECEDING AND 1 FOLLOWING
    ) AS centered_sum
FROM lab_wf242_sales
ORDER BY store_id, sale_day, sale_id;
~~~

Tại 104, khung là các giao dịch **103 (30), 104 (40), 105 (50)**, tổng **120**.

### Bài 5 — Ba ngày lịch khác ba giao dịch

**Yêu cầu:** tại giao dịch A–106 ngày 08/03, so sánh hai frame:

~~~sql
ROWS BETWEEN 2 PRECEDING AND CURRENT ROW

RANGE BETWEEN INTERVAL '2 days' PRECEDING AND CURRENT ROW
~~~

**Đáp án:** `ROWS` theo `ORDER BY sale_day, sale_id` cho **150** (40+50+60). `RANGE` theo `ORDER BY sale_day` cho **60**, vì khoảng 06–08/03 chỉ có giao dịch 106. Đây là hai định nghĩa báo cáo khác nhau.

### Bài 6 — GROUPS với ngày có nhiều giao dịch

**Yêu cầu:** dùng `GROUPS BETWEEN 1 PRECEDING AND CURRENT ROW` theo ngày. Kết quả của A–104 và A–106 là bao nhiêu?

**Đáp án:**

~~~sql
SELECT
    sale_id,
    SUM(amount) OVER (
        PARTITION BY store_id
        ORDER BY sale_day
        GROUPS BETWEEN 1 PRECEDING AND CURRENT ROW
    ) AS sum_two_date_groups
FROM lab_wf242_sales
ORDER BY store_id, sale_day, sale_id;
~~~

A–104 nhận **90** vì nhóm 02/03 (20+30) và nhóm 04/03 (40). A–106 nhận **110** vì hai nhóm 05/03 (50) và 08/03 (60).

### Bài 7 — Bốn lựa chọn EXCLUDE

**Yêu cầu:** với A–102, khung `GROUPS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW` theo `ORDER BY sale_day` có tổng 60. Hãy cho kết quả nếu lần lượt dùng `EXCLUDE NO OTHERS`, `CURRENT ROW`, `GROUP`, `TIES`.

**Đáp án:**

| Lựa chọn | Kết quả | Giải thích |
| --- | ---: | --- |
| NO OTHERS | 60 | Cộng 101, 102, 103 |
| CURRENT ROW | 40 | Bỏ 102, còn 101 + 103 |
| GROUP | 10 | Bỏ 102 và 103 vì cùng ngày |
| TIES | 30 | Giữ 102, bỏ peer 103; còn 101 + 102 |

Điểm mấu chốt: **CURRENT ROW và GROUP khác nhau khi có peers; TIES giữ chính hàng hiện tại**.

### Bài 8 — Tổng trước giao dịch, không dùng EXCLUDE

**Yêu cầu:** hệ quản trị không hỗ trợ `EXCLUDE`; cần tổng trước giao dịch hiện tại theo thứ tự ngày/ID.

**Đáp án:**

~~~sql
SELECT
    store_id,
    sale_id,
    SUM(amount) OVER (
        PARTITION BY store_id
        ORDER BY sale_day, sale_id
        ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING
    ) AS previous_total
FROM lab_wf242_sales
ORDER BY store_id, sale_day, sale_id;
~~~

Tại A–101 không có hàng trước nên `previous_total IS NULL`; tại A–104 kết quả **60**.

### Bài 9 — Tổng trước ngày hiện tại, bỏ cả nhóm cùng ngày

**Yêu cầu:** tại mỗi giao dịch, chỉ cộng giao dịch của **những ngày trước**, không tính các giao dịch khác cùng ngày. Viết cách không dùng `EXCLUDE`.

**Đáp án:**

~~~sql
SELECT
    s.store_id,
    s.sale_id,
    s.sale_day,
    (
        SELECT SUM(p.amount)
        FROM lab_wf242_sales AS p
        WHERE p.store_id = s.store_id
          AND p.sale_day < s.sale_day
    ) AS previous_days_total
FROM lab_wf242_sales AS s
ORDER BY s.store_id, s.sale_day, s.sale_id;
~~~

Hai giao dịch A–102 và A–103 đều nhận **10**, vì chỉ có 10 của ngày 01/03 đứng trước. A–104 nhận **60**.

### Bài 10 — Lọc theo tổng cửa sổ

**Yêu cầu:** tìm các giao dịch có tổng cộng dồn của cửa hàng đạt **100 trở lên**. Vì sao không dùng window function trực tiếp trong `WHERE` cùng cấp?

**Đáp án:**

~~~sql
WITH running AS (
    SELECT
        store_id, sale_id, sale_day,
        SUM(amount) OVER (
            PARTITION BY store_id
            ORDER BY sale_day, sale_id
            ROWS UNBOUNDED PRECEDING
        ) AS running_total
    FROM lab_wf242_sales
)
SELECT store_id, sale_id, running_total
FROM running
WHERE running_total >= 100
ORDER BY store_id, sale_day, sale_id;
~~~

Kết quả chỉ có A–104, A–105, A–106 với tổng **100, 150, 210**. Tính window trong CTE rồi lọc kết quả ở truy vấn ngoài; `WHERE` của cùng cấp truy vấn được đánh giá trước window.

### Bài 11 — LAST_VALUE cuối partition

**Yêu cầu:** với mỗi giao dịch, hiển thị `amount` của **giao dịch cuối cùng** theo `sale_day, sale_id` trong cùng cửa hàng.

**Đáp án:**

~~~sql
SELECT
    store_id,
    sale_id,
    LAST_VALUE(amount) OVER (
        PARTITION BY store_id
        ORDER BY sale_day, sale_id
        ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING
    ) AS last_amount
FROM lab_wf242_sales
ORDER BY store_id, sale_day, sale_id;
~~~

Các giao dịch của A cùng nhận **60**, B cùng nhận **35**. Thiếu `UNBOUNDED FOLLOWING` có thể làm `LAST_VALUE` chỉ lấy hàng cuối **của frame mặc định**.

### Bài 12 — Chọn đúng đơn vị frame

**Yêu cầu:** ghép yêu cầu nghiệp vụ với lựa chọn khung:

1. Ba **giao dịch** gần nhất.
2. Ba **ngày lịch** gần nhất, tính từ ngày hiện tại.
3. Hai **ngày có giao dịch** gần nhất, mỗi ngày có thể chứa nhiều giao dịch.
4. Tổng từ đầu tới trước **nhóm giao dịch cùng ngày** hiện tại.

**Đáp án tham khảo (PostgreSQL):**

| Yêu cầu | Khung / cách diễn đạt |
| --- | --- |
| 1 | `ROWS BETWEEN 2 PRECEDING AND CURRENT ROW` với thứ tự giao dịch xác định |
| 2 | `RANGE BETWEEN INTERVAL '2 days' PRECEDING AND CURRENT ROW`, `ORDER BY sale_day` |
| 3 | `GROUPS BETWEEN 1 PRECEDING AND CURRENT ROW`, `ORDER BY sale_day` |
| 4 | `GROUPS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW EXCLUDE GROUP`, `ORDER BY sale_day` |

Với yêu cầu 2, nếu muốn cả **ngày không có giao dịch** cũng xuất hiện thành hàng trên báo cáo, cần thêm trục ngày lịch; `RANGE` trên giao dịch đơn thuần không tự tạo hàng cho ngày trống.

## 20. Ghi nhớ

| Mục tiêu | Mẫu PostgreSQL | Điều cần chú ý |
| --- | --- | --- |
| Tổng cộng dồn từng giao dịch | `ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW` | Dùng thứ tự có khóa phân định |
| Tổng vài giao dịch gần nhất | `ROWS BETWEEN n PRECEDING AND CURRENT ROW` | Đếm hàng, không đếm ngày |
| Tổng theo khoảng ngày | `RANGE BETWEEN INTERVAL 'n days' PRECEDING AND CURRENT ROW` | Cần `ORDER BY` ngày phù hợp, chỉ một biểu thức khi có offset |
| Tổng theo vài nhóm đồng hạng | `GROUPS BETWEEN n PRECEDING AND CURRENT ROW` | Nhóm peers được xác định bởi `ORDER BY` |
| Cộng dồn mặc định có `ORDER BY` | `RANGE UNBOUNDED PRECEDING` tới nhóm peer hiện tại | Các hàng trùng khóa thứ tự có thể cùng tổng |
| Bỏ chính hàng hiện tại | `EXCLUDE CURRENT ROW` | Không tự bỏ peers khác |
| Bỏ cả nhóm peers hiện tại | `EXCLUDE GROUP` | Bỏ cả chính hàng hiện tại |
| Bỏ peers khác nhưng giữ hiện tại | `EXCLUDE TIES` | Khác `EXCLUDE GROUP` |
| Không loại trừ gì | `EXCLUDE NO OTHERS` | Là mặc định |
| Tổng trước hàng hiện tại, không có EXCLUDE | `ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING` | Frame đầu phân vùng có thể rỗng, `SUM` trả `NULL` |
| Lấy giá trị cuối cả phân vùng | `ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING` với `LAST_VALUE` | Không dựa vào frame mặc định |
| Lọc theo kết quả window | CTE/truy vấn con rồi `WHERE` bên ngoài | `WHERE` cùng cấp không nhận window function |

Trước khi viết hàm cửa sổ, hãy tự hỏi **“Đơn vị của chữ ‘trước’ là hàng, khoảng giá trị hay nhóm đồng hạng?”**. Sau đó xác định **cửa sổ chia theo gì**, **thứ tự có đủ rõ không**, **frame bắt đầu/kết thúc ở đâu** và **có loại trừ hàng nào không**. Tách bạch những quyết định ấy sẽ giúp bạn tính đúng tổng tích lũy và trung bình trượt, xử lý được nhiều giao dịch cùng ngày, và chuyển đổi báo cáo giữa các SQL dialect mà không vô tình đổi ngữ nghĩa.
