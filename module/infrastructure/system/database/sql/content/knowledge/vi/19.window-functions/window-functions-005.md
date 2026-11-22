# LAG và LEAD để so sánh các hàng trong SQL

Giả sử có bảng doanh thu theo ngày và cần trả lời: **“Doanh thu cửa hàng hôm nay tăng hay giảm so với lần ghi nhận trước?”**, **“Sự kiện nào xảy ra ngay sau sự kiện hiện tại?”**, hoặc **“Trạng thái đơn hàng đã chuyển từ gì sang gì?”**. Một phép `SELECT` thông thường chỉ làm việc với giá trị của từng hàng đang được chọn; phép `GROUP BY` gom nhiều hàng thành một nhóm và thường làm mất chi tiết từng hàng. Trong khi đó, các **hàm cửa sổ** (*window functions*) có thể đọc giá trị của **các hàng liên quan** mà vẫn giữ mỗi hàng nguồn trong kết quả.

Hai hàm rất quan trọng là:

- **`LAG`**: lấy giá trị từ một hàng **đứng trước** hàng hiện tại trong thứ tự được định nghĩa.
- **`LEAD`**: lấy giá trị từ một hàng **đứng sau** hàng hiện tại trong cùng thứ tự.

Ví dụ:

~~~sql
SELECT
    cua_hang_id,
    ngay,
    doanh_thu,
    LAG(doanh_thu) OVER (
        PARTITION BY cua_hang_id
        ORDER BY ngay
    ) AS doanh_thu_lan_truoc,
    LEAD(doanh_thu) OVER (
        PARTITION BY cua_hang_id
        ORDER BY ngay
    ) AS doanh_thu_lan_sau
FROM doanh_thu_ngay_win
ORDER BY cua_hang_id, ngay;
~~~

Ở đây, `PARTITION BY cua_hang_id` chia các hàng theo từng cửa hàng, còn `ORDER BY ngay` xác định quan hệ **trước/sau** bên trong mỗi cửa hàng. Bài này sẽ giải thích cặn kẽ cú pháp, phép tính chênh lệch, xử lý `NULL`, khoảng trống thời gian, sắp xếp đồng hạng, sự kiện đổi trạng thái và những lỗi cần tránh khi kết hợp hàm cửa sổ với `WHERE`, CTE, `JOIN` và `GROUP BY`.

Các ví dụ thực hành dùng **PostgreSQL**. `LAG` và `LEAD` cũng được hỗ trợ trong nhiều phiên bản MySQL, SQL Server và Oracle Database, nhưng có những khác biệt về xử lý `NULL`, cú pháp và kiểu dữ liệu.

## 1. Từ “hàng hiện tại” đến “hàng trước” và “hàng sau”

Giả sử một cửa hàng có ba bản ghi đã được sắp theo ngày:

| Ngày | Doanh thu | LAG(doanh_thu) | LEAD(doanh_thu) |
| --- | ---: | ---: | ---: |
| 01/10 | 100.000 | `NULL` | 130.000 |
| 02/10 | 130.000 | 100.000 | 90.000 |
| 04/10 | 90.000 | 130.000 | `NULL` |

Ở ngày 02/10:

- `LAG` nhìn **lùi một hàng**, trả doanh thu của ngày 01/10.
- `LEAD` nhìn **tiến một hàng**, trả doanh thu của ngày 04/10.

Điểm dễ nhầm: **ngày 04/10 đứng ngay sau ngày 02/10 trong tập hàng đã sắp xếp**, dù giữa hai ngày còn **ngày 03/10 không có bản ghi**. Vì vậy “hàng trước” **không tự động có nghĩa “ngày hôm qua”**. Nếu bài toán thực sự cần so sánh đúng các ngày liên tiếp, phải kiểm tra chênh lệch ngày hoặc bổ sung lịch.

Một cách nhìn:

~~~mermaid
flowchart LR
    A["01/10\n100.000"] -->|"LEAD từ 01/10\nLAG từ 02/10"| B["02/10\n130.000"]
    B -->|"LEAD từ 02/10\nLAG từ 04/10"| C["04/10\n90.000"]
~~~

**`LAG` và `LEAD` không tự tìm hàng theo giá trị bằng nhau hay theo thời gian gần nhất.** Chúng dựa vào **thứ tự hàng trong một cửa sổ** do người viết câu SQL định nghĩa.

## 2. Bộ dữ liệu thực hành PostgreSQL

Ta tạo một bảng doanh thu đã tổng hợp theo cửa hàng và ngày. Các bảng `TEMP` dưới đây chỉ tồn tại trong **phiên kết nối PostgreSQL hiện tại**; mở phiên khác cần chạy lại phần tạo bảng.

~~~sql
CREATE TEMP TABLE doanh_thu_ngay_win (
    cua_hang_id INTEGER NOT NULL,
    ngay DATE NOT NULL,
    doanh_thu NUMERIC(14, 2) CHECK (doanh_thu >= 0),
    so_don INTEGER CHECK (so_don >= 0),
    PRIMARY KEY (cua_hang_id, ngay)
);

INSERT INTO doanh_thu_ngay_win
    (cua_hang_id, ngay, doanh_thu, so_don)
VALUES
    (10, DATE '2026-10-01', 1000000, 10),
    (10, DATE '2026-10-02', 1300000, 12),
    (10, DATE '2026-10-04',  900000,  9),
    (10, DATE '2026-10-05',    NULL, NULL),
    (10, DATE '2026-10-06',       0,  0),
    (10, DATE '2026-10-07',  800000,  8),
    (20, DATE '2026-10-01',  500000,  5),
    (20, DATE '2026-10-03',  550000,  6),
    (20, DATE '2026-10-04',  550000,  6),
    (20, DATE '2026-10-06',  100000,  2),
    (20, DATE '2026-10-07',  900000,  9);
~~~

Bảng có **11 hàng**: sáu bản ghi của cửa hàng `10`, năm bản ghi của cửa hàng `20`. Khóa chính `(cua_hang_id, ngay)` bảo đảm tối đa **một hàng cho mỗi cửa hàng trong một ngày**.

### 2.1. Các tình huống được cố ý đưa vào

| Trường hợp | Dữ liệu | Điều cần hiểu |
| --- | --- | --- |
| Cửa hàng có nhiều ngày | Cửa hàng 10 và 20 | Cần `PARTITION BY` để không so sánh chéo cửa hàng |
| Ngày bị thiếu bản ghi | Cửa hàng 10 thiếu ngày 03/10 | `LAG` ngày 04/10 lấy ngày 02/10, không phải 03/10 |
| Doanh thu chưa biết | Cửa hàng 10 ngày 05/10 có `doanh_thu = NULL` | Hàng tồn tại nhưng giá trị không có |
| Doanh thu thực bằng 0 | Cửa hàng 10 ngày 06/10 có doanh thu `0` | `0` khác `NULL`; ảnh hưởng mẫu số tăng trưởng |
| Hai ngày doanh thu bằng nhau | Cửa hàng 20 ngày 03/10 và 04/10 đều 550.000 | Chênh lệch bằng 0, không phải tăng hay giảm |
| Ngày đầu/ngày cuối mỗi nhóm | Ngày đầu và cuối từng cửa hàng | Không có hàng trước/sau nên trả `NULL` hoặc giá trị mặc định |

Mô hình này là **ảnh chụp doanh thu theo ngày**. Nó không giả định doanh thu `NULL` có nghĩa 0, cũng không tự tạo các ngày không có hàng.

### 2.2. Xem bảng với thứ tự rõ ràng

~~~sql
SELECT
    cua_hang_id,
    ngay,
    doanh_thu,
    so_don
FROM doanh_thu_ngay_win
ORDER BY cua_hang_id, ngay;
~~~

Trong SQL, nếu không có `ORDER BY` ở truy vấn cuối, **thứ tự trình bày không được bảo đảm**, dù bảng có khóa chính hoặc được chèn theo thứ tự ngày. Điều này đặc biệt quan trọng khi học các hàm lấy hàng lân cận.

## 3. Cú pháp LAG và LEAD

Trong PostgreSQL, dạng cơ bản:

~~~sql
LAG(bieu_thuc [, do_lech [, gia_tri_mac_dinh]])
    OVER (
        [PARTITION BY cot_chia_nhom]
        ORDER BY cot_xac_dinh_thu_tu
    )

LEAD(bieu_thuc [, do_lech [, gia_tri_mac_dinh]])
    OVER (
        [PARTITION BY cot_chia_nhom]
        ORDER BY cot_xac_dinh_thu_tu
    )
~~~

Các dấu `[...]` trong mẫu trên chỉ **thành phần tùy chọn**, không phải ký tự cần gõ nguyên văn vào câu SQL.

| Thành phần | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| `bieu_thuc` | Giá trị cần lấy từ hàng khác | `doanh_thu`, `trang_thai`, `ngay` |
| `do_lech` | Số vị trí hàng cần lùi/tiến; mặc định `1` | `LAG(doanh_thu, 2)` |
| `gia_tri_mac_dinh` | Giá trị thay khi **hàng ở vị trí đó không tồn tại**; mặc định `NULL` | `LAG(doanh_thu, 1, 0)` |
| `OVER` | Khai báo ngữ cảnh cửa sổ cho hàm | `OVER (PARTITION BY ... ORDER BY ...)` |
| `PARTITION BY` | Chia dữ liệu thành những nhóm độc lập | `PARTITION BY cua_hang_id` |
| `ORDER BY` trong `OVER` | Xác định hàng nào đứng trước/sau | `ORDER BY ngay` |

### 3.1. LAG và LEAD mặc định lệch một hàng

~~~sql
SELECT
    cua_hang_id,
    ngay,
    doanh_thu,
    LAG(doanh_thu) OVER (
        PARTITION BY cua_hang_id
        ORDER BY ngay
    ) AS doanh_thu_truoc,
    LEAD(doanh_thu) OVER (
        PARTITION BY cua_hang_id
        ORDER BY ngay
    ) AS doanh_thu_sau
FROM doanh_thu_ngay_win
ORDER BY cua_hang_id, ngay;
~~~

Đối với cửa hàng `10`, kết quả phần quan trọng là:

| ngày | doanh_thu | doanh_thu_truoc | doanh_thu_sau |
| --- | ---: | ---: | ---: |
| 01/10 | 1.000.000 | `NULL` | 1.300.000 |
| 02/10 | 1.300.000 | 1.000.000 | 900.000 |
| 04/10 | 900.000 | 1.300.000 | `NULL` |
| 05/10 | `NULL` | 900.000 | 0 |
| 06/10 | 0 | `NULL` | 800.000 |
| 07/10 | 800.000 | 0 | `NULL` |

Ở ngày 04/10, `LEAD(doanh_thu)` là `NULL` **không phải vì không có hàng tiếp theo**: hàng ngày 05/10 **có tồn tại** nhưng `doanh_thu` của nó là `NULL`. Đây là phân biệt rất quan trọng khi bàn đến giá trị mặc định.

### 3.2. LAG không làm giảm số dòng

Với `GROUP BY cua_hang_id`, dữ liệu có thể từ 11 dòng thành hai dòng tổng hợp. Ngược lại, việc thêm `LAG`/`LEAD` vào `SELECT` **không tự gom hay loại hàng**. Nếu không có phép lọc khác, truy vấn trên vẫn trả **11 dòng**, mỗi bản ghi ngày vẫn giữ nguyên.

Đặc tính **giữ mức chi tiết hàng** khiến hàm cửa sổ phù hợp với biểu đồ chuỗi thời gian, nhật ký sự kiện, báo cáo chênh lệch và phân tích thay đổi.

## 4. PARTITION BY: không so sánh nhầm giữa các nhóm

Ví dụ viết thiếu nhóm:

~~~sql
SELECT
    cua_hang_id,
    ngay,
    doanh_thu,
    LAG(doanh_thu) OVER (
        ORDER BY cua_hang_id, ngay
    ) AS doanh_thu_truoc
FROM doanh_thu_ngay_win
ORDER BY cua_hang_id, ngay;
~~~

Hàm trên xem **toàn bộ 11 dòng là một chuỗi duy nhất**. Khi chuyển từ dòng cuối cửa hàng `10` (07/10, 800.000) sang dòng đầu cửa hàng `20` (01/10, 500.000), `LAG` của cửa hàng 20 sẽ nhận **800.000 của cửa hàng 10**. Kết quả có số nhưng **không đúng đối tượng so sánh**.

Đúng hơn:

~~~sql
LAG(doanh_thu) OVER (
    PARTITION BY cua_hang_id
    ORDER BY ngay
)
~~~

`PARTITION BY` tạo **một chuỗi thời gian độc lập cho mỗi cửa hàng**:

~~~text
Cửa hàng 10: 01/10 -> 02/10 -> 04/10 -> 05/10 -> 06/10 -> 07/10
Cửa hàng 20: 01/10 -> 03/10 -> 04/10 -> 06/10 -> 07/10
             ^ LAG đầu nhóm trả NULL, không lấy cuối nhóm trước
~~~

### 4.1. Có thể chia theo nhiều cột

Nếu dữ liệu ở mức **cửa hàng + sản phẩm + ngày** và mục tiêu là so sánh doanh số cùng sản phẩm qua các ngày:

~~~sql
LAG(so_luong_ban) OVER (
    PARTITION BY cua_hang_id, ma_san_pham
    ORDER BY ngay
)
~~~

Lúc này mỗi tổ hợp `(cua_hang_id, ma_san_pham)` là một partition. Nếu bỏ `ma_san_pham`, kết quả có thể lấy giá trị của **sản phẩm khác**; nếu bỏ `cua_hang_id`, kết quả có thể lấy giá trị của **cửa hàng khác**.

**Hãy chọn `PARTITION BY` theo đối tượng cần so sánh**, không đơn thuần theo những cột sẵn có trong bảng.

### 4.2. Nếu không có PARTITION BY thì sao?

Không có `PARTITION BY` là hoàn toàn hợp lệ **khi muốn so sánh trên toàn bộ tập hàng**. Ví dụ bảng tỷ giá hoặc chỉ số thị trường có một chuỗi thời gian chung không cần chia nhóm. Sai sót chỉ xuất hiện khi dữ liệu có nhiều chuỗi độc lập nhưng người viết vô tình trộn chúng.

## 5. ORDER BY: “trước” và “sau” phụ thuộc thứ tự nào?

`LAG`/`LEAD` không có khái niệm “trước” tuyệt đối. Chúng chỉ biết **thứ tự được khai báo trong `OVER`**.

### 5.1. Tăng dần và giảm dần cho ý nghĩa khác nhau

~~~sql
SELECT
    cua_hang_id,
    ngay,
    doanh_thu,
    LAG(doanh_thu) OVER (
        PARTITION BY cua_hang_id
        ORDER BY ngay ASC
    ) AS doanh_thu_ngay_som_hon,
    LAG(doanh_thu) OVER (
        PARTITION BY cua_hang_id
        ORDER BY ngay DESC
    ) AS doanh_thu_ngay_muon_hon
FROM doanh_thu_ngay_win
WHERE cua_hang_id = 20
ORDER BY ngay;
~~~

`ORDER BY ngay ASC` đặt ngày cũ trước ngày mới; `LAG` của 04/10 lấy ngày **03/10**. Với `ORDER BY ngay DESC`, thứ tự đi ngược thời gian; `LAG` của 04/10 lấy ngày **06/10**. Do đó **“LAG” không mặc định có nghĩa “ngày trước đó trong lịch”** nếu người viết dùng thứ tự giảm dần.

### 5.2. ORDER BY trong OVER khác ORDER BY ngoài cùng

~~~sql
SELECT
    ngay,
    doanh_thu,
    LAG(doanh_thu) OVER (
        PARTITION BY cua_hang_id
        ORDER BY ngay ASC
    ) AS doanh_thu_truoc
FROM doanh_thu_ngay_win
WHERE cua_hang_id = 10
ORDER BY ngay DESC;
~~~

`LAG` vẫn tính theo **ngày tăng dần** trong `OVER`, dù kết quả cuối **hiển thị theo ngày giảm dần**. Hai `ORDER BY` có trách nhiệm khác nhau:

- **Bên trong `OVER`**: định nghĩa hàng lân cận cho hàm cửa sổ.
- **Ngoài cùng**: quyết định thứ tự hiển thị của tập kết quả.

Một câu SQL chỉ có `ORDER BY` bên ngoài **không bù được** việc thiếu thứ tự đúng trong `OVER`.

### 5.3. Khi các hàng có cùng khóa sắp xếp

Nếu hai sự kiện của một đơn có cùng `thoi_diem`, biểu thức:

~~~sql
LAG(trang_thai) OVER (
    PARTITION BY don_hang_id
    ORDER BY thoi_diem
)
~~~

**không đủ xác định một thứ tự duy nhất** giữa hai hàng đồng thời điểm. DBMS có thể chọn một thứ tự giữa các hàng đồng hạng, nên kết quả “trạng thái trước” không ổn định theo yêu cầu nghiệp vụ.

Thường nên thêm một khóa phân xử (*tie-breaker*) có ý nghĩa:

~~~sql
LAG(trang_thai) OVER (
    PARTITION BY don_hang_id
    ORDER BY thoi_diem, id
)
~~~

Nếu ID chỉ là số sinh ra không phản ánh thứ tự nghiệp vụ, nên dùng **số thứ tự sự kiện** hoặc một cột thời gian/sequence đáng tin cậy khác. Thêm `id` giúp thứ tự kỹ thuật ổn định, nhưng không tự bảo đảm đúng thứ tự thực tế khi dữ liệu nguồn ghi sự kiện không theo ID.

## 6. Độ lệch OFFSET: nhìn lùi hoặc tiến nhiều hàng

Đối số thứ hai là **số lượng hàng cần nhảy**. Nếu bỏ qua, độ lệch mặc định là `1`:

~~~sql
SELECT
    cua_hang_id,
    ngay,
    doanh_thu,
    LAG(doanh_thu, 1) OVER (
        PARTITION BY cua_hang_id
        ORDER BY ngay
    ) AS lan_truoc,
    LAG(doanh_thu, 2) OVER (
        PARTITION BY cua_hang_id
        ORDER BY ngay
    ) AS hai_hang_truoc,
    LEAD(doanh_thu, 2) OVER (
        PARTITION BY cua_hang_id
        ORDER BY ngay
    ) AS hai_hang_sau
FROM doanh_thu_ngay_win
ORDER BY cua_hang_id, ngay;
~~~

Với cửa hàng `10` ngày 04/10:

- `LAG(doanh_thu, 1)` trả **1.300.000** (ngày 02/10).
- `LAG(doanh_thu, 2)` trả **1.000.000** (ngày 01/10).
- `LEAD(doanh_thu, 2)` trả **0** (ngày 06/10); hàng 05/10 ở giữa vẫn được đếm là một bước, dù doanh thu `NULL`.

Nếu không đủ số hàng để nhảy, kết quả mặc định là `NULL`. Ví dụ, cửa hàng 10 ngày 02/10 chỉ có một hàng trước, nên `LAG(doanh_thu, 2)` trả `NULL`.

### 6.1. Độ lệch hai hàng không phải luôn hai ngày

Vì cửa hàng 10 thiếu ngày 03/10, `LAG(..., 2)` của ngày 04/10 lấy ngày 01/10: **cách ba ngày theo lịch**, không phải “hai ngày trước”.

Điều này cũng đúng với dữ liệu giao dịch: `LAG(..., 5)` nghĩa là **giao dịch đứng trước năm vị trí trong thứ tự**, không phải cách năm phút, năm giờ hay năm ngày.

### 6.2. Độ lệch 0 và độ lệch không phù hợp

Trong PostgreSQL, dùng `LAG(bieu_thuc, 0)` sẽ tham chiếu **hàng hiện tại**, nên thường không cần thiết nếu mục tiêu chỉ đọc giá trị đang có. Với việc so sánh hàng trước/sau, nên dùng **độ lệch nguyên không âm rõ ràng**, thường là 1 hoặc 2.

Không nên dựa vào độ lệch âm để đảo hướng giữa `LAG` và `LEAD`: mức hỗ trợ và các giới hạn của đối số này có thể khác theo DBMS. Khi cần đi tới hàng sau, dùng `LEAD` giúp người đọc hiểu rõ ý định.

## 7. Giá trị mặc định: không có hàng khác với hàng có NULL

Đối số thứ ba của `LAG`/`LEAD` thường tạo **giá trị mặc định khi hàng ở vị trí lùi/tiến không tồn tại**:

~~~sql
SELECT
    cua_hang_id,
    ngay,
    doanh_thu,
    LAG(doanh_thu, 1, -1) OVER (
        PARTITION BY cua_hang_id
        ORDER BY ngay
    ) AS truoc_hoac_am_mot
FROM doanh_thu_ngay_win
WHERE cua_hang_id = 10
ORDER BY ngay;
~~~

Với cửa hàng 10:

| Ngày | Giá trị từ LAG(doanh_thu, 1, -1) | Lý do |
| --- | ---: | --- |
| 01/10 | `-1` | Không có **hàng trước** trong partition |
| 02/10 | 1.000.000 | Hàng trước có doanh thu 1.000.000 |
| 04/10 | 1.300.000 | Hàng trước là 02/10 |
| 05/10 | 900.000 | Hàng trước là 04/10 |
| 06/10 | `NULL` | Hàng trước **có tồn tại** (05/10) nhưng `doanh_thu IS NULL` |
| 07/10 | 0 | Hàng trước tồn tại và doanh thu bằng 0 |

**Điểm cốt lõi:** `default` của `LAG`/`LEAD` không có nghĩa “thay mọi giá trị `NULL` từ hàng trước”. Nó chỉ được dùng khi **không có hàng ở vị trí được yêu cầu**.

Đối số mặc định cần có kiểu phù hợp với biểu thức được lấy. Với giá trị tiền `NUMERIC`, các hằng số `0`, `-1` hoặc `NULL::numeric` có thể được dùng theo quy tắc ép kiểu của DBMS.

### 7.1. Không đặt 0 làm mặc định nếu dễ gây nhầm

~~~sql
LAG(doanh_thu, 1, 0) OVER (...)
~~~

giúp hàng đầu tiên có giá trị “trước đó” bằng 0, nhưng **0 là một doanh thu thực có thể xảy ra**. Khi hiển thị báo cáo hoặc tính phần trăm thay đổi, gộp “không có ngày trước” với “ngày trước có doanh thu 0” có thể tạo diễn giải sai.

Nếu cần phân biệt, có thể lấy thêm **khóa của hàng trước**:

~~~sql
SELECT
    cua_hang_id,
    ngay,
    doanh_thu,
    LAG(ngay) OVER (
        PARTITION BY cua_hang_id
        ORDER BY ngay
    ) AS ngay_truoc,
    LAG(doanh_thu) OVER (
        PARTITION BY cua_hang_id
        ORDER BY ngay
    ) AS doanh_thu_truoc
FROM doanh_thu_ngay_win
ORDER BY cua_hang_id, ngay;
~~~

Nếu `ngay_truoc IS NULL` trong bảng mẫu (nơi `ngay NOT NULL`), thật sự không có hàng trước. Nếu `ngay_truoc` có giá trị nhưng `doanh_thu_truoc IS NULL`, hàng trước có tồn tại và dữ liệu doanh thu đang thiếu.

## 8. Tính chênh lệch giữa các hàng với LAG

Một ứng dụng phổ biến là so sánh **doanh thu hiện tại** với **doanh thu lần ghi nhận trước của cùng cửa hàng**.

~~~sql
WITH co_doanh_thu_truoc AS (
    SELECT
        cua_hang_id,
        ngay,
        doanh_thu,
        LAG(ngay) OVER (
            PARTITION BY cua_hang_id
            ORDER BY ngay
        ) AS ngay_truoc,
        LAG(doanh_thu) OVER (
            PARTITION BY cua_hang_id
            ORDER BY ngay
        ) AS doanh_thu_truoc
    FROM doanh_thu_ngay_win
)
SELECT
    cua_hang_id,
    ngay,
    doanh_thu,
    ngay_truoc,
    doanh_thu_truoc,
    doanh_thu - doanh_thu_truoc AS chenh_lech
FROM co_doanh_thu_truoc
ORDER BY cua_hang_id, ngay;
~~~

Theo dữ liệu:

- Cửa hàng 10, ngày 02/10: `1.300.000 - 1.000.000 = +300.000`.
- Cửa hàng 10, ngày 04/10: `900.000 - 1.300.000 = -400.000`.
- Cửa hàng 10, ngày 06/10: `0 - NULL = NULL`; không thể kết luận giảm 900.000 vì **ngày trước hiện có là 05/10 với doanh thu chưa biết**.
- Cửa hàng 10, ngày 07/10: `800.000 - 0 = +800.000`.
- Cửa hàng 20, ngày 04/10: `550.000 - 550.000 = 0` (không đổi).

Mỗi hàng được giữ nguyên trong kết quả; cột `chenh_lech` chỉ là **giá trị tính thêm**.

### 8.1. Phân loại tăng, giảm, không đổi và thiếu dữ liệu

~~~sql
WITH co_lan_truoc AS (
    SELECT
        cua_hang_id,
        ngay,
        doanh_thu,
        LAG(ngay) OVER (
            PARTITION BY cua_hang_id
            ORDER BY ngay
        ) AS ngay_truoc,
        LAG(doanh_thu) OVER (
            PARTITION BY cua_hang_id
            ORDER BY ngay
        ) AS doanh_thu_truoc
    FROM doanh_thu_ngay_win
)
SELECT
    cua_hang_id,
    ngay,
    doanh_thu,
    doanh_thu_truoc,
    CASE
        WHEN ngay_truoc IS NULL THEN 'LAN_GHI_NHAN_DAU'
        WHEN doanh_thu IS NULL OR doanh_thu_truoc IS NULL
            THEN 'THIEU_DU_LIEU'
        WHEN doanh_thu > doanh_thu_truoc THEN 'TANG'
        WHEN doanh_thu < doanh_thu_truoc THEN 'GIAM'
        ELSE 'KHONG_DOI'
    END AS xu_huong
FROM co_lan_truoc
ORDER BY cua_hang_id, ngay;
~~~

Khi không có hàng trước, báo `LAN_GHI_NHAN_DAU`. Khi hàng trước tồn tại nhưng dữ liệu thiếu, báo `THIEU_DU_LIEU`. Hai trường hợp được giữ riêng thay vì cùng trở thành 0 hoặc một nhãn “không đổi”.

### 8.2. Vì sao cần CTE để đặt tên LAG?

CTE `co_lan_truoc` tạo các cột `ngay_truoc` và `doanh_thu_truoc` **một lần ở mức câu SQL**, giúp biểu thức `CASE` và phép trừ bên ngoài dễ đọc. CTE này không nhất thiết được materialize vật lý; bộ tối ưu hóa PostgreSQL có thể biến đổi kế hoạch nhưng phải giữ nguyên ý nghĩa.

## 9. Tính phần trăm tăng trưởng và tránh chia cho 0

Tỷ lệ thay đổi so với lần ghi nhận trước thường được tính:

\[
\text{Tăng trưởng (\%)} =
\frac{\text{giá trị hiện tại} - \text{giá trị trước}}{\text{giá trị trước}}
\times 100
\]

Ví dụ doanh thu tăng từ 1.000.000 lên 1.300.000:

\[
\frac{1\,300\,000 - 1\,000\,000}{1\,000\,000}\times100 = 30\%
\]

Trong SQL, **mẫu số có thể bằng 0 hoặc `NULL`**. Dùng `NULLIF` để tránh chia cho 0:

~~~sql
WITH co_lan_truoc AS (
    SELECT
        cua_hang_id,
        ngay,
        doanh_thu,
        LAG(doanh_thu) OVER (
            PARTITION BY cua_hang_id
            ORDER BY ngay
        ) AS doanh_thu_truoc
    FROM doanh_thu_ngay_win
)
SELECT
    cua_hang_id,
    ngay,
    doanh_thu,
    doanh_thu_truoc,
    doanh_thu - doanh_thu_truoc AS chenh_lech,
    ROUND(
        (doanh_thu - doanh_thu_truoc) * 100.0
        / NULLIF(doanh_thu_truoc, 0),
        2
    ) AS ty_le_thay_doi_pct
FROM co_lan_truoc
ORDER BY cua_hang_id, ngay;
~~~

Một số giá trị:

| Cửa hàng | Ngày | Doanh thu trước | Doanh thu hiện tại | Chênh lệch | Tỷ lệ |
| ---: | --- | ---: | ---: | ---: | ---: |
| 10 | 02/10 | 1.000.000 | 1.300.000 | +300.000 | +30,00% |
| 10 | 04/10 | 1.300.000 | 900.000 | -400.000 | khoảng -30,77% |
| 10 | 06/10 | `NULL` | 0 | `NULL` | `NULL` |
| 10 | 07/10 | 0 | 800.000 | +800.000 | `NULL` |
| 20 | 03/10 | 500.000 | 550.000 | +50.000 | +10,00% |
| 20 | 04/10 | 550.000 | 550.000 | 0 | 0,00% |
| 20 | 06/10 | 550.000 | 100.000 | -450.000 | khoảng -81,82% |
| 20 | 07/10 | 100.000 | 900.000 | +800.000 | +800,00% |

Khi doanh thu trước là `0`, **tỷ lệ phần trăm theo công thức trên không xác định**; `NULLIF(doanh_thu_truoc, 0)` biến mẫu số 0 thành `NULL`, khiến kết quả là `NULL` thay vì lỗi.

Nếu ứng dụng muốn hiển thị `'N/A'` cho tỷ lệ không xác định, nên tạo **nhãn hiển thị riêng**, không ép một tỷ lệ không xác định thành `0%` hay `100%` nếu không có quy tắc nghiệp vụ rõ.

### 9.1. Kiểu số và chia nguyên

Ở ví dụ, `doanh_thu` là `NUMERIC` và `100.0` là hằng có phần thập phân nên kết quả phù hợp để làm tròn. Với các cột `INTEGER` ở DBMS khác, phép chia giữa hai số nguyên có thể **bỏ phần thập phân**. Khi tính tỷ lệ, chuyển kiểu tường minh sang `DECIMAL`/`NUMERIC` hoặc dùng hằng số có kiểu phù hợp theo DBMS.

### 9.2. Tăng trưởng giữa hai lần ghi nhận không nhất thiết là tăng trưởng từng ngày

Ở cửa hàng 10, ngày 04/10 được so với ngày 02/10 vì không có bản ghi 03/10. Do đó tỷ lệ `-30,77%` là thay đổi **giữa hai lần ghi nhận liên tiếp**, không tự động là **thay đổi một ngày**. Nếu báo cáo gọi đây là “daily growth”, cần xử lý ngày thiếu trước.

## 10. LAG theo thứ tự hàng khác so sánh ngày liền kề

Để biết ngày trước thực sự **cách mấy ngày**, dùng `LAG(ngay)`:

~~~sql
WITH chuoi AS (
    SELECT
        cua_hang_id,
        ngay,
        doanh_thu,
        LAG(ngay) OVER (
            PARTITION BY cua_hang_id
            ORDER BY ngay
        ) AS ngay_truoc,
        LAG(doanh_thu) OVER (
            PARTITION BY cua_hang_id
            ORDER BY ngay
        ) AS doanh_thu_truoc
    FROM doanh_thu_ngay_win
)
SELECT
    cua_hang_id,
    ngay,
    ngay_truoc,
    ngay - ngay_truoc AS so_ngay_cach,
    CASE
        WHEN ngay_truoc IS NULL THEN 'LAN_DAU'
        WHEN ngay - ngay_truoc = 1 THEN 'NGAY_LIEN_TRUOC'
        ELSE 'CO_KHOANG_TRONG'
    END AS loai_khoang
FROM chuoi
ORDER BY cua_hang_id, ngay;
~~~

Trong PostgreSQL, phép `DATE - DATE` trả số **ngày nguyên** giữa hai giá trị ngày. Theo dữ liệu mẫu:

- Cửa hàng 10, **04/10** có `ngay_truoc = 02/10`, chênh **2 ngày**.
- Cửa hàng 20, **03/10** có `ngay_truoc = 01/10`, chênh **2 ngày**.
- Cửa hàng 20, **06/10** có `ngay_truoc = 04/10`, chênh **2 ngày**.

Nếu nghiệp vụ chỉ muốn so sánh với **ngày hôm trước**, có thể giới hạn phép tính:

~~~sql
WITH chuoi AS (
    SELECT
        cua_hang_id,
        ngay,
        doanh_thu,
        LAG(ngay) OVER (
            PARTITION BY cua_hang_id
            ORDER BY ngay
        ) AS ngay_truoc,
        LAG(doanh_thu) OVER (
            PARTITION BY cua_hang_id
            ORDER BY ngay
        ) AS doanh_thu_truoc
    FROM doanh_thu_ngay_win
)
SELECT
    cua_hang_id,
    ngay,
    CASE
        WHEN ngay_truoc = ngay - 1
            THEN doanh_thu - doanh_thu_truoc
        ELSE NULL
    END AS chenh_lech_so_voi_hom_qua
FROM chuoi
ORDER BY cua_hang_id, ngay;
~~~

Ngày 04/10 của cửa hàng 10 có kết quả `NULL` ở cột này, vì bản ghi liền trước của nó là 02/10, **không phải hôm qua**. Câu SQL không bịa ra doanh thu ngày 03/10.

### 10.1. Bổ sung lịch ngày khi cần

Nếu biểu đồ cần hiển thị **mọi ngày từ 01/10 đến 07/10**, PostgreSQL có thể sinh dãy ngày bằng `generate_series` rồi `LEFT JOIN` dữ liệu thật:

~~~sql
WITH lich AS (
    SELECT
        generate_series(
            TIMESTAMP '2026-10-01 00:00:00',
            TIMESTAMP '2026-10-07 00:00:00',
            INTERVAL '1 day'
        )::date AS ngay
),
chuoi_du_ngay AS (
    SELECT
        l.ngay,
        d.ngay IS NULL AS thieu_ban_ghi,
        d.doanh_thu
    FROM lich AS l
    LEFT JOIN doanh_thu_ngay_win AS d
        ON d.cua_hang_id = 10
       AND d.ngay = l.ngay
)
SELECT
    ngay,
    thieu_ban_ghi,
    doanh_thu,
    LAG(doanh_thu) OVER (ORDER BY ngay) AS doanh_thu_hom_truoc
FROM chuoi_du_ngay
ORDER BY ngay;
~~~

Với cửa hàng 10:

- **03/10** được sinh từ lịch, có `thieu_ban_ghi = TRUE` và doanh thu `NULL`.
- **05/10** đã có bản ghi thật, nên `thieu_ban_ghi = FALSE`, nhưng doanh thu vẫn là `NULL`.
- **06/10** đã có bản ghi và doanh thu **bằng 0**.

Đây là ba trạng thái dữ liệu **khác nhau**. Nếu dùng `COALESCE(doanh_thu, 0)` ngay trong CTE, cả ngày thiếu bản ghi và ngày có doanh thu chưa biết đều biến thành 0, có thể làm sai báo cáo. Chỉ điền 0 khi nghiệp vụ **bảo đảm** thiếu bản ghi nghĩa là không có giao dịch hoặc không phát sinh doanh thu.

Với nhiều cửa hàng, có thể tạo lưới **cửa hàng × ngày** từ danh sách cửa hàng và lịch, rồi `LEFT JOIN` doanh thu; cần cân nhắc số dòng nếu số cửa hàng và khoảng thời gian rất lớn.

## 11. LEAD: nhìn trước để đo khoảng cách đến sự kiện tiếp theo

`LEAD` rất hữu ích khi dữ liệu có **mốc bắt đầu** và cần biết **mốc tiếp theo**:

~~~sql
SELECT
    cua_hang_id,
    ngay AS ngay_hien_tai,
    LEAD(ngay) OVER (
        PARTITION BY cua_hang_id
        ORDER BY ngay
    ) AS ngay_tiep_theo,
    LEAD(ngay) OVER (
        PARTITION BY cua_hang_id
        ORDER BY ngay
    ) - ngay AS so_ngay_den_lan_tiep
FROM doanh_thu_ngay_win
ORDER BY cua_hang_id, ngay;
~~~

Cửa hàng 10:

| Ngày hiện tại | Ngày tiếp theo | Số ngày đến lần tiếp |
| --- | --- | ---: |
| 01/10 | 02/10 | 1 |
| 02/10 | 04/10 | 2 |
| 04/10 | 05/10 | 1 |
| 05/10 | 06/10 | 1 |
| 06/10 | 07/10 | 1 |
| 07/10 | `NULL` | `NULL` |

Ví dụ ứng dụng khác: bảng giá có các mốc `ngay_hieu_luc`. Nếu dữ liệu mô tả **mỗi mốc bắt đầu một giai đoạn hiệu lực cho đến trước mốc kế tiếp**, `LEAD(ngay_hieu_luc)` có thể tính **ngày kết thúc loại trừ** của khoảng hiện hành:

~~~sql
-- Mẫu ý tưởng cho bảng bang_gia_lich_su giả định:
SELECT
    ma_san_pham,
    ngay_hieu_luc AS tu_ngay,
    LEAD(ngay_hieu_luc) OVER (
        PARTITION BY ma_san_pham
        ORDER BY ngay_hieu_luc, id
    ) AS den_truoc_ngay
FROM bang_gia_lich_su;
~~~

Truy vấn này là **mẫu thiết kế**, cần có bảng `bang_gia_lich_su` chứa các cột tương ứng mới chạy được. Giá trị `den_truoc_ngay IS NULL` ở bản ghi cuối có thể được hiểu là “chưa có mốc tiếp theo”; chính sách kết thúc hiệu lực thực tế phải do nghiệp vụ xác định.

### 11.1. LAG và LEAD không phải hàm tìm min/max

`LEAD(ngay)` lấy **ngày ở hàng ngay sau** trong thứ tự, không tự chọn ngày có khoảng cách thời gian nhỏ nhất nếu thứ tự được khai báo khác thời gian. `LAG(doanh_thu)` lấy **giá trị của hàng trước**, không phải **giá trị doanh thu nhỏ hơn gần nhất**. Nếu muốn giá trị cực trị theo nhóm, thường dùng `MIN`, `MAX`, `FIRST_VALUE` hoặc một truy vấn tìm kiếm theo điều kiện cụ thể.

## 12. LAG và LEAD với trạng thái thay đổi theo sự kiện

Một ứng dụng quan trọng là **lịch sử trạng thái đơn hàng**. Để theo dõi chuyển trạng thái, ta cần thứ tự sự kiện và ID sự kiện để xử lý trường hợp hai sự kiện có cùng timestamp.

~~~sql
CREATE TEMP TABLE su_kien_don_win (
    id INTEGER PRIMARY KEY,
    don_hang_id INTEGER NOT NULL,
    thoi_diem TIMESTAMPTZ NOT NULL,
    trang_thai TEXT NOT NULL
);

INSERT INTO su_kien_don_win
    (id, don_hang_id, thoi_diem, trang_thai)
VALUES
    (1, 101, '2026-10-01 08:00:00+07', 'MOI'),
    (2, 101, '2026-10-01 09:00:00+07', 'XAC_NHAN'),
    (3, 101, '2026-10-01 09:00:00+07', 'DANG_GIAO'),
    (4, 101, '2026-10-02 17:00:00+07', 'HOAN_TAT'),
    (5, 102, '2026-10-03 10:00:00+07', 'MOI'),
    (6, 102, '2026-10-03 11:00:00+07', 'HUY');
~~~

Có sáu sự kiện, chia thành hai chuỗi theo `don_hang_id`. Trong dữ liệu thực hành, khi thời điểm bằng nhau, ta **quy ước ID sự kiện tăng dần phản ánh thứ tự**. Hệ thống thật cần xác nhận điều này hoặc lưu một cột `thu_tu_su_kien` riêng.

### 12.1. Tìm trạng thái ngay trước và ngay sau

~~~sql
SELECT
    don_hang_id,
    id AS su_kien_id,
    thoi_diem,
    trang_thai,
    LAG(trang_thai) OVER (
        PARTITION BY don_hang_id
        ORDER BY thoi_diem, id
    ) AS trang_thai_truoc,
    LEAD(trang_thai) OVER (
        PARTITION BY don_hang_id
        ORDER BY thoi_diem, id
    ) AS trang_thai_sau
FROM su_kien_don_win
ORDER BY don_hang_id, thoi_diem, id;
~~~

Kết quả chính:

| Đơn | Sự kiện | Trạng thái hiện tại | Trước | Sau |
| ---: | ---: | --- | --- | --- |
| 101 | 1 | MOI | `NULL` | XAC_NHAN |
| 101 | 2 | XAC_NHAN | MOI | DANG_GIAO |
| 101 | 3 | DANG_GIAO | XAC_NHAN | HOAN_TAT |
| 101 | 4 | HOAN_TAT | DANG_GIAO | `NULL` |
| 102 | 5 | MOI | `NULL` | HUY |
| 102 | 6 | HUY | MOI | `NULL` |

Không có trạng thái trước cho sự kiện đầu của mỗi đơn, và không có trạng thái sau cho sự kiện cuối của mỗi đơn.

### 12.2. Chỉ lấy các lần chuyển trạng thái thật sự

Nếu bảng lịch sử có thể ghi nhiều sự kiện liên tiếp với **cùng trạng thái**, cần xác định sự kiện nào tạo ra chuyển trạng thái:

~~~sql
WITH co_trang_thai_truoc AS (
    SELECT
        id,
        don_hang_id,
        thoi_diem,
        trang_thai,
        LAG(id) OVER (
            PARTITION BY don_hang_id
            ORDER BY thoi_diem, id
        ) AS su_kien_truoc_id,
        LAG(trang_thai) OVER (
            PARTITION BY don_hang_id
            ORDER BY thoi_diem, id
        ) AS trang_thai_truoc
    FROM su_kien_don_win
)
SELECT
    don_hang_id,
    id AS su_kien_id,
    trang_thai_truoc,
    trang_thai AS trang_thai_moi
FROM co_trang_thai_truoc
WHERE su_kien_truoc_id IS NOT NULL
  AND trang_thai IS DISTINCT FROM trang_thai_truoc
ORDER BY don_hang_id, su_kien_id;
~~~

Trong PostgreSQL, `IS DISTINCT FROM` là phép so sánh **null-safe**: nó xác định hai giá trị có khác nhau hay không, kể cả khi có `NULL`. Bộ dữ liệu mẫu khai báo `trang_thai NOT NULL`, nhưng mẫu này còn dễ mở rộng cho nguồn dữ liệu nullable.

Kết quả có **4 lần chuyển**: đơn 101 có ba lần (`MOI → XAC_NHAN → DANG_GIAO → HOAN_TAT`), đơn 102 có một lần (`MOI → HUY`). Các sự kiện mở đầu không được tính là “chuyển từ một trạng thái trước” vì chưa có hàng trước.

### 12.3. Nhóm những đoạn trạng thái liên tiếp

Với dữ liệu có thể chứa nhiều lần ghi trạng thái giống nhau, ta có thể đánh dấu **đầu một đoạn trạng thái mới**, rồi cộng dồn các dấu:

~~~sql
WITH su_kien_co_truoc AS (
    SELECT
        *,
        LAG(trang_thai) OVER (
            PARTITION BY don_hang_id
            ORDER BY thoi_diem, id
        ) AS trang_thai_truoc
    FROM su_kien_don_win
),
co_dau_doan AS (
    SELECT
        *,
        CASE
            WHEN trang_thai IS DISTINCT FROM trang_thai_truoc
                THEN 1 ELSE 0
        END AS bat_dau_doan_moi
    FROM su_kien_co_truoc
)
SELECT
    don_hang_id,
    id,
    trang_thai,
    SUM(bat_dau_doan_moi) OVER (
        PARTITION BY don_hang_id
        ORDER BY thoi_diem, id
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS so_doan
FROM co_dau_doan
ORDER BY don_hang_id, thoi_diem, id;
~~~

Ở đây, `LAG` xác định **sự thay đổi giữa các hàng**, còn `SUM(... OVER)` tạo **mã đoạn tăng dần**. CTE trung gian cần thiết vì không thể tùy tiện lồng trực tiếp một hàm cửa sổ bên trong biểu thức của hàm cửa sổ khác cùng cấp.

Đây là một biến thể của bài toán **gaps and islands** trong phân tích chuỗi sự kiện.

## 13. LAG với dữ liệu thiếu: RESPECT NULLS và IGNORE NULLS

Theo hành vi PostgreSQL, `LAG`/`LEAD` **tôn trọng vị trí các hàng chứa `NULL`**. Chúng không tự nhảy qua hàng có giá trị trống:

~~~sql
SELECT
    ngay,
    doanh_thu,
    LAG(doanh_thu) OVER (ORDER BY ngay) AS doanh_thu_truoc
FROM doanh_thu_ngay_win
WHERE cua_hang_id = 10
ORDER BY ngay;
~~~

Ngày 06/10 trả `doanh_thu_truoc = NULL` do giá trị của **ngày 05/10** là `NULL`, dù ngày 04/10 có doanh thu 900.000.

### 13.1. “Giá trị ở hàng trước” và “giá trị khác NULL gần nhất” là hai bài toán khác

Nếu nghiệp vụ cần **doanh thu khác `NULL` gần nhất trước ngày hiện tại**, không thể dùng `LAG(doanh_thu)` thông thường trong PostgreSQL rồi mặc định nó bỏ qua hàng trống. Một cách diễn đạt bằng truy vấn con tương quan:

~~~sql
SELECT
    d.cua_hang_id,
    d.ngay,
    d.doanh_thu,
    (
        SELECT d2.doanh_thu
        FROM doanh_thu_ngay_win AS d2
        WHERE d2.cua_hang_id = d.cua_hang_id
          AND d2.ngay < d.ngay
          AND d2.doanh_thu IS NOT NULL
        ORDER BY d2.ngay DESC
        LIMIT 1
    ) AS doanh_thu_co_gia_tri_gan_nhat
FROM doanh_thu_ngay_win AS d
WHERE d.cua_hang_id = 10
ORDER BY d.ngay;
~~~

Với cửa hàng 10:

- Ngày **06/10** lấy **900.000** từ ngày 04/10, bỏ qua bản ghi 05/10 có doanh thu `NULL`.
- Ngày **07/10** lấy **0** từ ngày 06/10, vì `0` là giá trị **khác `NULL`**, dù không phải doanh thu dương.

Đây là **giá trị không NULL gần nhất trước ngày hiện tại**, khác với **giá trị của hàng ở vị trí ngay trước**. Nếu dùng cách này trên bảng lớn, cần cân nhắc chỉ mục theo `(cua_hang_id, ngay)` và kế hoạch thực thi. Trong bảng mẫu, khóa chính đã tạo chỉ mục tương ứng.

### 13.2. Hỗ trợ IGNORE NULLS khác nhau theo DBMS

- **PostgreSQL:** không cung cấp cú pháp `IGNORE NULLS` cho `LAG`/`LEAD`; hành vi tương ứng là **RESPECT NULLS**.
- **Oracle Database:** hỗ trợ các lựa chọn `IGNORE NULLS`/`RESPECT NULLS` cho `LAG`/`LEAD` trong các phiên bản thích hợp.
- **SQL Server 2022 trở lên:** có hỗ trợ `IGNORE NULLS`/`RESPECT NULLS` cho `LAG`/`LEAD`; cần lưu ý phiên bản và các bản cập nhật vì từng có sửa lỗi liên quan.
- **MySQL 8.0:** hỗ trợ `LAG`/`LEAD`, nhưng không nên giả định `IGNORE NULLS` được triển khai như ở Oracle/SQL Server.

Vì vậy, **không chép nguyên một câu SQL có `IGNORE NULLS` từ DBMS này sang DBMS khác**. Khi cần bỏ qua các giá trị `NULL`, nên xác định yêu cầu trước rồi chọn cú pháp/phương án tương thích.

### 13.3. Không mặc định chuyển NULL thành 0

`COALESCE(doanh_thu, 0)` là một quy tắc **điền dữ liệu** có thể hợp lý ở một số báo cáo, nhưng cũng có thể biến “chưa tổng hợp xong doanh thu” thành “doanh thu bằng 0”. Nếu cần so sánh dựa trên dữ liệu đã được xác nhận, hãy lọc hoặc đánh dấu trạng thái dữ liệu thay vì lấp `NULL` tùy tiện.

## 14. Hàm cửa sổ được tính ở giai đoạn nào của truy vấn?

Trong PostgreSQL, hàm cửa sổ như `LAG`/`LEAD` được dùng chủ yếu ở **danh sách `SELECT`** và **`ORDER BY`** của cấp truy vấn đó. Không viết trực tiếp chúng vào `WHERE` hoặc `HAVING` cùng cấp:

~~~sql
-- Cách viết không hợp lệ trong PostgreSQL:
-- SELECT *
-- FROM doanh_thu_ngay_win
-- WHERE doanh_thu > LAG(doanh_thu) OVER (
--     PARTITION BY cua_hang_id ORDER BY ngay
-- );
~~~

Muốn **lọc các hàng có doanh thu tăng so với lần trước**, hãy tính `LAG` trong CTE hoặc bảng dẫn xuất trước, sau đó lọc ở truy vấn ngoài:

~~~sql
WITH so_sanh AS (
    SELECT
        cua_hang_id,
        ngay,
        doanh_thu,
        LAG(doanh_thu) OVER (
            PARTITION BY cua_hang_id
            ORDER BY ngay
        ) AS doanh_thu_truoc
    FROM doanh_thu_ngay_win
)
SELECT
    cua_hang_id,
    ngay,
    doanh_thu,
    doanh_thu_truoc
FROM so_sanh
WHERE doanh_thu > doanh_thu_truoc
ORDER BY cua_hang_id, ngay;
~~~

Trong dữ liệu mẫu, các hàng tăng là:

| Cửa hàng | Ngày | Lý do |
| ---: | --- | --- |
| 10 | 02/10 | 1.300.000 lớn hơn 1.000.000 |
| 10 | 07/10 | 800.000 lớn hơn 0 |
| 20 | 03/10 | 550.000 lớn hơn 500.000 |
| 20 | 07/10 | 900.000 lớn hơn 100.000 |

Kết quả có **4 dòng**. Những hàng có một trong hai giá trị `NULL` không đáp ứng phép so sánh `>`.

### 14.1. Lọc trước LAG và lọc sau LAG không tương đương

Yêu cầu: chỉ **hiển thị các ngày từ 04/10 trở đi**, nhưng doanh thu trước vẫn phải được tính từ **toàn bộ lịch sử đã ghi nhận**.

Sai về ý định:

~~~sql
SELECT
    cua_hang_id,
    ngay,
    doanh_thu,
    LAG(doanh_thu) OVER (
        PARTITION BY cua_hang_id ORDER BY ngay
    ) AS doanh_thu_truoc
FROM doanh_thu_ngay_win
WHERE cua_hang_id = 10
  AND ngay >= DATE '2026-10-04'
ORDER BY ngay;
~~~

`WHERE` loại ngày 01/10 và 02/10 **trước khi hàm cửa sổ được tính**, nên ngày 04/10 trở thành **hàng đầu partition sau lọc**, có `LAG = NULL`. Nhưng doanh thu ghi nhận trước đó thực sự là **1.300.000 ngày 02/10**.

Đúng cho yêu cầu “tính trên lịch sử đầy đủ, chỉ lọc kết quả hiển thị”:

~~~sql
WITH lich_su AS (
    SELECT
        cua_hang_id,
        ngay,
        doanh_thu,
        LAG(doanh_thu) OVER (
            PARTITION BY cua_hang_id ORDER BY ngay
        ) AS doanh_thu_truoc
    FROM doanh_thu_ngay_win
    WHERE cua_hang_id = 10
)
SELECT *
FROM lich_su
WHERE ngay >= DATE '2026-10-04'
ORDER BY ngay;
~~~

Lúc này `doanh_thu_truoc` của 04/10 là **1.300.000**. Mệnh đề lọc `cua_hang_id = 10` đặt trong CTE vẫn phù hợp vì ta chỉ cần chuỗi cửa hàng 10; lọc **mốc bắt đầu ngày** cần thực hiện sau khi `LAG` đã nhìn thấy các hàng lịch sử cần thiết.

**Nguyên tắc:** quyết định rõ một điều kiện `WHERE` là điều kiện **giới hạn dữ liệu để tính toán** hay chỉ là điều kiện **giới hạn hàng hiển thị sau tính toán**.

### 14.2. Kết hợp GROUP BY và LAG

Hàm cửa sổ hoạt động trên **tập hàng của cấp truy vấn sau các bước lọc, nhóm và tổng hợp thích hợp**. Nếu nguồn có nhiều giao dịch trong một ngày mà cần so sánh **tổng doanh thu từng ngày**, nên **tổng hợp trước**, sau đó dùng `LAG`.

~~~sql
-- Mẫu dùng bảng giao_dich giả định:
WITH doanh_thu_theo_ngay AS (
    SELECT
        cua_hang_id,
        ngay_giao_dich::date AS ngay,
        SUM(so_tien) AS doanh_thu
    FROM giao_dich
    WHERE trang_thai = 'THANH_CONG'
    GROUP BY cua_hang_id, ngay_giao_dich::date
)
SELECT
    cua_hang_id,
    ngay,
    doanh_thu,
    LAG(doanh_thu) OVER (
        PARTITION BY cua_hang_id
        ORDER BY ngay
    ) AS doanh_thu_ngay_truoc
FROM doanh_thu_theo_ngay
ORDER BY cua_hang_id, ngay;
~~~

Đây là **mẫu ý tưởng**, cần bảng `giao_dich` với các cột tương ứng mới thực thi được. `ngay_giao_dich::date` theo múi giờ của phiên nếu cột là `TIMESTAMPTZ` trong PostgreSQL; khi tính doanh thu theo ngày địa phương, hãy xác định múi giờ nghiệp vụ trước khi chuyển thành ngày.

## 15. LAG/LEAD và khung cửa sổ (window frame)

Người học hàm cửa sổ thường gặp:

~~~sql
OVER (
    PARTITION BY cua_hang_id
    ORDER BY ngay
    ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
)
~~~

Đây là một **khung cửa sổ** (*frame*) thường dùng cho phép cộng dồn, ví dụ `SUM(doanh_thu)`. Tuy nhiên `LAG` và `LEAD` không lấy hàng theo cách mà `SUM`, `FIRST_VALUE` hay `LAST_VALUE` bị giới hạn bởi khung. Trong PostgreSQL, **`LAG`/`LEAD` tìm theo vị trí trong partition đã sắp xếp, không bị hạn chế bởi frame hiện tại**.

Vì vậy, ví dụ:

~~~sql
SELECT
    cua_hang_id,
    ngay,
    doanh_thu,
    LAG(doanh_thu) OVER (
        PARTITION BY cua_hang_id
        ORDER BY ngay
    ) AS doanh_thu_truoc
FROM doanh_thu_ngay_win;
~~~

là đủ để lấy một hàng trước; không cần thêm `ROWS BETWEEN 1 PRECEDING AND 1 PRECEDING` để “bắt” LAG chỉ nhìn một hàng. Độ lệch của `LAG` đã do **đối số `offset`** quy định.

### 15.1. LAG khác phép tổng hợp trên frame

Một phép tổng hợp “tổng doanh thu hai hàng gần nhất” có thể viết:

~~~sql
SELECT
    cua_hang_id,
    ngay,
    doanh_thu,
    SUM(doanh_thu) OVER (
        PARTITION BY cua_hang_id
        ORDER BY ngay
        ROWS BETWEEN 1 PRECEDING AND CURRENT ROW
    ) AS tong_hai_lan_ghi_nhan
FROM doanh_thu_ngay_win
ORDER BY cua_hang_id, ngay;
~~~

`SUM` trên frame tổng hợp các giá trị **của các hàng được frame bao phủ**, trong khi `LAG` lấy **giá trị của một hàng ở vị trí cụ thể**. Nếu cần so sánh với trung bình trượt, hãy sử dụng `AVG(...) OVER (... ROWS ...)`, không cố thay bằng `LAG`.

### 15.2. ROWS và RANGE cũng khác nhau

`ROWS` xác định frame bằng số hàng vật lý trong thứ tự. `RANGE` thường dựa trên quan hệ với giá trị của khóa sắp xếp và có những quy tắc về hàng đồng hạng. Khi tính tổng hoặc trung bình trượt, cách chọn frame có thể thay đổi kết quả; nhưng với `LAG`/`LEAD`, vấn đề chính cần xác định là **partition, thứ tự và offset**.

## 16. Cửa sổ có tên với WINDOW

Khi nhiều hàm cửa sổ dùng **cùng một phân nhóm và thứ tự**, PostgreSQL hỗ trợ mệnh đề `WINDOW` để đặt tên cho định nghĩa đó:

~~~sql
SELECT
    cua_hang_id,
    ngay,
    doanh_thu,
    LAG(doanh_thu) OVER w AS doanh_thu_truoc,
    LEAD(doanh_thu) OVER w AS doanh_thu_sau,
    LAG(ngay) OVER w AS ngay_truoc,
    LEAD(ngay) OVER w AS ngay_sau
FROM doanh_thu_ngay_win
WINDOW w AS (
    PARTITION BY cua_hang_id
    ORDER BY ngay
)
ORDER BY cua_hang_id, ngay;
~~~

`w` là tên **cửa sổ**, không phải CTE hoặc bảng. Cách viết này giúp tránh lặp đoạn `PARTITION BY cua_hang_id ORDER BY ngay` bốn lần và giảm nguy cơ một biểu thức bị gõ khác thứ tự so với các biểu thức còn lại.

**Chú ý:** Mệnh đề `WINDOW` trong PostgreSQL thuộc cấu trúc câu SELECT, thường đặt sau `WHERE`/`GROUP BY`/`HAVING` và trước `ORDER BY` ngoài cùng. Một số DBMS hỗ trợ named window với cú pháp tương ứng, trong khi SQL Server truyền thống thường viết `OVER (...)` trực tiếp cho từng hàm; không nên mặc định mọi phiên bản hỗ trợ `WINDOW w AS (...)`.

## 17. Dùng LAG/LEAD trong phân tích chuỗi thời gian và báo cáo

### 17.1. So sánh hai lần ghi nhận theo sản phẩm

Giả sử bảng có cột `ma_san_pham`, `ngay`, `gia_ban`. Muốn theo dõi thay đổi giá của từng sản phẩm:

~~~sql
-- Mẫu khi bảng lich_su_gia tồn tại:
SELECT
    ma_san_pham,
    ngay,
    gia_ban,
    LAG(gia_ban) OVER (
        PARTITION BY ma_san_pham
        ORDER BY ngay, id
    ) AS gia_truoc,
    LEAD(gia_ban) OVER (
        PARTITION BY ma_san_pham
        ORDER BY ngay, id
    ) AS gia_sau
FROM lich_su_gia;
~~~

Điều kiện `PARTITION BY ma_san_pham` giữ giá của từng sản phẩm độc lập; `ORDER BY ngay, id` xác định thứ tự khi một sản phẩm có nhiều lần đổi giá cùng ngày. Khi bảng giá có cửa hàng hoặc khu vực, cần thêm các cột đó vào partition nếu giá được xác định theo từng thị trường.

### 17.2. Phát hiện thay đổi số dư tài khoản

Nếu có bảng `so_du_tai_khoan(account_id, thoi_diem, sequence_id, so_du)`:

~~~sql
-- Mẫu trên một bảng giả định:
SELECT
    account_id,
    thoi_diem,
    so_du,
    so_du - LAG(so_du) OVER (
        PARTITION BY account_id
        ORDER BY thoi_diem, sequence_id
    ) AS thay_doi_so_du
FROM so_du_tai_khoan;
~~~

Chênh lệch giữa hai số dư là **thay đổi ròng giữa hai lần chụp số dư**. Nó không nhất thiết bằng **một giao dịch riêng lẻ**, vì có thể có nhiều giao dịch giữa hai lần chụp. Khi đối soát tài chính, cần xác định loại dữ liệu và cách sinh bản ghi trước khi suy ra số tiền giao dịch.

### 17.3. Đo thời gian giữa hai sự kiện

Trên bảng sự kiện đã tạo:

~~~sql
SELECT
    don_hang_id,
    id,
    thoi_diem,
    LEAD(thoi_diem) OVER (
        PARTITION BY don_hang_id
        ORDER BY thoi_diem, id
    ) - thoi_diem AS khoang_den_su_kien_sau
FROM su_kien_don_win
ORDER BY don_hang_id, thoi_diem, id;
~~~

Với PostgreSQL, phép `TIMESTAMPTZ - TIMESTAMPTZ` trả một **`INTERVAL`**. Hai sự kiện 2 và 3 của đơn 101 cùng thời điểm 09:00, nên khoảng cách từ sự kiện 2 đến sự kiện 3 là **0**. Bản ghi cuối mỗi đơn có khoảng cách `NULL` vì chưa có sự kiện tiếp theo.

Nếu dùng sự kiện để tính SLA hoặc thời gian xử lý, cần chú ý múi giờ, nguồn timestamp, sự kiện đến muộn và trường hợp thời gian bằng nhau.

### 17.4. So sánh tháng này với tháng trước

Khi nguồn là giao dịch chi tiết, cần **tổng hợp về một dòng cho mỗi tháng trước khi dùng LAG**. Ví dụ dữ liệu tổng hợp tháng độc lập:

~~~sql
WITH doanh_thu_thang AS (
    SELECT *
    FROM (VALUES
        (10, DATE '2026-08-01', 8000000::numeric),
        (10, DATE '2026-09-01', 9000000::numeric),
        (10, DATE '2026-10-01', 10000000::numeric),
        (20, DATE '2026-08-01', 4000000::numeric),
        (20, DATE '2026-10-01',  5500000::numeric)
    ) AS v(cua_hang_id, thang, tong_doanh_thu)
),
co_thang_truoc AS (
    SELECT
        cua_hang_id,
        thang,
        tong_doanh_thu,
        LAG(thang) OVER (
            PARTITION BY cua_hang_id ORDER BY thang
        ) AS thang_truoc,
        LAG(tong_doanh_thu) OVER (
            PARTITION BY cua_hang_id ORDER BY thang
        ) AS doanh_thu_truoc
    FROM doanh_thu_thang
)
SELECT
    cua_hang_id,
    thang,
    tong_doanh_thu,
    thang_truoc,
    doanh_thu_truoc,
    tong_doanh_thu - doanh_thu_truoc AS chenh_lech
FROM co_thang_truoc
ORDER BY cua_hang_id, thang;
~~~

Đối với cửa hàng 10, ba tháng liên tiếp có chênh lệch +1.000.000 giữa 08→09 và +1.000.000 giữa 09→10. Đối với cửa hàng 20, bản ghi 10/2026 được `LAG` so với **08/2026** vì **không có bản ghi 09/2026**. Muốn “tháng trước” đúng nghĩa lịch, phải kiểm tra `thang_truoc = (thang - INTERVAL '1 month')::date` trong ngữ cảnh ngày đầu tháng hoặc sinh đầy đủ bảng lịch tháng.

## 18. Hiệu năng: sắp xếp, partition và chỉ mục

`LAG`/`LEAD` thường cần xử lý các hàng theo **partition và thứ tự**. Hiệu năng có thể bị ảnh hưởng bởi:

- Số dòng đi vào phép tính cửa sổ;
- Số lượng partition và kích thước partition lớn nhất;
- Các cột của `ORDER BY`, đặc biệt với nhiều cột tie-breaker;
- Bộ nhớ dùng cho sắp xếp, khả năng phải dùng đĩa tạm;
- Chỉ mục, thống kê, phiên bản DBMS và kế hoạch thực thi.

### 18.1. Chỉ mục theo khóa partition + thứ tự

Với truy vấn:

~~~sql
LAG(doanh_thu) OVER (
    PARTITION BY cua_hang_id
    ORDER BY ngay
)
~~~

một chỉ mục B-tree theo `(cua_hang_id, ngay)` có thể hữu ích trong một số kế hoạch đọc. **Bảng thực hành đã có khóa chính `PRIMARY KEY (cua_hang_id, ngay)`**, và PostgreSQL tạo chỉ mục duy nhất tương ứng; không cần tạo thêm index trùng hệt chỉ vì học `LAG`.

Trên bảng sự kiện, nếu thường truy vấn theo `don_hang_id, thoi_diem, id`, có thể cân nhắc:

~~~sql
CREATE INDEX idx_su_kien_don_win_thu_tu
ON su_kien_don_win (don_hang_id, thoi_diem, id);
~~~

Việc thêm index không bảo đảm PostgreSQL luôn dùng index đó: bảng nhỏ có thể quét tuần tự và sắp xếp nhanh hơn; bảng lớn cần xem xét số dòng, selectivity, số cột và chi phí ghi.

### 18.2. Đừng dùng DISTINCT để “sửa” kết quả LAG

`LAG` giữ mỗi hàng nguồn. Nếu thấy nhiều dòng cho cùng cửa hàng, đó thường là **mức chi tiết theo ngày** hoặc theo sự kiện, không phải bản ghi bị nhân vô cớ. `DISTINCT` có thể loại mất những sự kiện hợp lệ hoặc che việc dữ liệu chưa được tổng hợp đúng grain.

### 18.3. Lọc dữ liệu đủ sớm, nhưng không mất lịch sử cần so sánh

Lọc đúng `cua_hang_id` trước khi tính window thường giảm số partition/hàng cần xử lý nếu chỉ quan tâm một cửa hàng. Nhưng lọc `ngay >= ...` trước `LAG` có thể khiến ngày đầu phạm vi thiếu **giá trị tham chiếu ngay trước mốc bắt đầu**, như đã thấy ở mục 14.1.

Khi tối ưu truy vấn theo khoảng thời gian, cần cân bằng giữa **hạn chế dữ liệu để đọc** và **giữ lại đủ hàng lịch sử cần thiết cho offset**. Nếu độ lệch tối đa là 1 hoặc 2, một chiến lược chỉ đọc thêm các hàng cận mốc có thể phù hợp, nhưng cách triển khai phải bảo đảm đúng với lịch thiếu và partition.

### 18.4. Kiểm tra kế hoạch bằng EXPLAIN

~~~sql
EXPLAIN
SELECT
    cua_hang_id,
    ngay,
    LAG(doanh_thu) OVER (
        PARTITION BY cua_hang_id
        ORDER BY ngay
    ) AS doanh_thu_truoc
FROM doanh_thu_ngay_win;
~~~

PostgreSQL có thể thể hiện các thao tác như `WindowAgg`, `Sort` hoặc một phương thức đọc cung cấp thứ tự phù hợp. Với truy vấn lớn, dùng `EXPLAIN (ANALYZE, BUFFERS)` trong môi trường cho phép để xem số hàng, chi phí thực và tài nguyên, vì **`ANALYZE` thực sự chạy câu lệnh**. Bộ dữ liệu 11 hàng chỉ có giá trị minh họa, không đại diện hiệu năng sản xuất.

## 19. Những khác biệt giữa PostgreSQL, MySQL, SQL Server và Oracle

Các DBMS này hỗ trợ `LAG`/`LEAD` ở những phiên bản hiện đại, nhưng nên đọc tài liệu theo **phiên bản máy chủ thực tế** khi chuyển mã.

| Khía cạnh | PostgreSQL | MySQL | SQL Server | Oracle Database |
| --- | --- | --- | --- | --- |
| `LAG(expr, offset, default)` | Có | Có trong MySQL 8.0+ | Có | Có |
| `LEAD(expr, offset, default)` | Có | Có trong MySQL 8.0+ | Có | Có |
| `OVER (PARTITION BY ... ORDER BY ...)` | Có | Có | Có | Có |
| `LAG`/`LEAD` bỏ qua NULL bằng chỉ thị `IGNORE NULLS` | Không hỗ trợ cú pháp đó | Không nên coi là được triển khai | SQL Server 2022+ có hỗ trợ | Có hỗ trợ |
| CTE để lọc sau window | `WITH ... SELECT` | `WITH ... SELECT` | `WITH ... SELECT` | `WITH ... SELECT` |
| Chỉ thị `WINDOW w AS (...)` | Có | Có trong phiên bản phù hợp | Không phải cú pháp phổ biến trên nhiều phiên bản SQL Server | Cú pháp/phạm vi hỗ trợ tùy phiên bản; dùng `OVER (...)` để dễ di chuyển |
| Khác biệt ngày giờ | `DATE - DATE` trả số ngày | `DATEDIFF` và hàm riêng | `DATEDIFF`/`DATEDIFF_BIG` | Phép toán `DATE`, timestamp/interval theo kiểu |

### 19.1. Cú pháp phổ biến

PostgreSQL:

~~~sql
SELECT
    cua_hang_id,
    ngay,
    doanh_thu,
    LAG(doanh_thu, 1, 0) OVER (
        PARTITION BY cua_hang_id ORDER BY ngay
    ) AS lan_truoc
FROM doanh_thu_ngay_win;
~~~

MySQL 8.0+ (mẫu trên bảng cùng tên nếu đã được tạo):

~~~sql
SELECT
    cua_hang_id,
    ngay,
    doanh_thu,
    LEAD(doanh_thu, 1, 0) OVER (
        PARTITION BY cua_hang_id ORDER BY ngay
    ) AS lan_sau
FROM doanh_thu_ngay_win;
~~~

SQL Server (mẫu trên bảng được tạo theo kiểu dữ liệu/cú pháp T-SQL):

~~~sql
SELECT
    cua_hang_id,
    ngay,
    doanh_thu,
    LAG(doanh_thu, 1, 0) OVER (
        PARTITION BY cua_hang_id ORDER BY ngay
    ) AS lan_truoc
FROM dbo.doanh_thu_ngay;
~~~

Oracle (mẫu trên bảng `DOANH_THU_NGAY` giả định):

~~~sql
SELECT
    cua_hang_id,
    ngay,
    doanh_thu,
    LEAD(doanh_thu, 1, 0) OVER (
        PARTITION BY cua_hang_id ORDER BY ngay
    ) AS lan_sau
FROM doanh_thu_ngay;
~~~

Các ví dụ này cho thấy cú pháp chính tương tự, **không ngụ ý** các lệnh tạo bảng PostgreSQL ở đầu bài chạy nguyên văn trên mọi DBMS.

### 19.2. ORDER BY phải đủ xác định thứ tự

Trên mọi DBMS, nếu các hàng cùng partition có **khóa `ORDER BY` trùng nhau**, hàm lấy hàng trước/sau có thể phụ thuộc thứ tự được chọn giữa các hàng đồng hạng. Vì vậy một khóa phân xử có ý nghĩa là yêu cầu **về tính đúng đắn**, không chỉ tối ưu hóa.

### 19.3. Kiểu trả về và giá trị mặc định

`default` cần tương thích với kiểu của `expr`. Với cột `NUMERIC`, dùng hằng số số; với cột `DATE`, dùng giá trị ngày hợp lệ; với `TEXT`, dùng nhãn văn bản. Quy tắc ép kiểu ngầm định khác nhau giữa PostgreSQL, MySQL, SQL Server và Oracle, nên cần `CAST` tường minh nếu việc chuyển dữ liệu có thể mơ hồ.

### 19.4. Không giả định hỗ trợ QUALIFY

Một số hệ phân tích dữ liệu có mệnh đề `QUALIFY` để lọc **sau khi** hàm cửa sổ được tính. PostgreSQL, SQL Server, MySQL và Oracle không nên được coi là có cùng cú pháp `QUALIFY` trong mọi phiên bản. Mẫu **CTE + SELECT ngoài + WHERE** là cách dễ hiểu và có khả năng di chuyển tương đối cao để lọc kết quả `LAG`/`LEAD`.

## 20. Những nhầm lẫn phổ biến

| Nhầm lẫn | Vì sao không đúng | Cách hiểu đúng |
| --- | --- | --- |
| “LAG luôn là ngày hôm qua.” | LAG lùi **một hàng**, bất kể ngày bị thiếu. | Kiểm tra `LAG(ngay)` hoặc bổ sung lịch. |
| “LEAD luôn là ngày mai.” | LEAD tiến **một hàng** theo thứ tự trong `OVER`. | Kiểm tra ngày của hàng sau. |
| “Không cần PARTITION BY vì đã ORDER BY cửa hàng.” | Dòng cuối cửa hàng này có thể thành “trước” của cửa hàng kia. | Chia partition theo đối tượng cần so sánh. |
| “ORDER BY cuối truy vấn quyết định hàng trước/sau.” | Thứ tự tính window nằm trong `OVER`. | Dùng `ORDER BY` ở cả vị trí cần thiết. |
| “Hai hàng trùng timestamp vẫn có thứ tự chắc chắn.” | Khóa ORDER BY không xác định một trật tự duy nhất. | Thêm khóa phân xử hợp lệ. |
| “OFFSET 2 nghĩa là 2 ngày.” | Nghĩa là **2 vị trí hàng**. | Tính chênh lệch ngày nếu cần khoảng thời gian. |
| “Tham số default thay mọi giá trị NULL.” | Chỉ thay khi **không có hàng ở vị trí offset**. | Phân biệt không có hàng và hàng có giá trị NULL. |
| “Doanh thu NULL nên coi bằng 0.” | NULL có thể nghĩa chưa biết hoặc chưa cập nhật. | Điền giá trị theo chính sách dữ liệu đã xác nhận. |
| “LAG bỏ qua NULL theo mặc định.” | PostgreSQL tôn trọng hàng có NULL. | Nếu cần giá trị không NULL gần nhất, dùng phương án riêng. |
| “Có thể dùng LAG trực tiếp trong WHERE.” | Window function không được dùng ở WHERE cùng cấp trong PostgreSQL. | Tính ở CTE, lọc ở SELECT ngoài. |
| “Lọc ngày đầu ra trước hay sau LAG như nhau.” | Lọc trước có thể loại hàng tham chiếu của ngày đầu hiển thị. | Giữ lịch sử trong CTE, lọc ngày hiển thị bên ngoài. |
| “LAG làm mất hoặc gộp các hàng.” | LAG không tự nhóm hàng. | Muốn tổng hợp, dùng GROUP BY hoặc window aggregate riêng. |
| “LAG nhận window frame giới hạn một hàng.” | Trong PostgreSQL, LAG dựa vào offset trên partition. | Frame chủ yếu liên quan đến các hàm khác như SUM/LAST_VALUE. |
| “Chia cho doanh thu trước bằng 0 cứ trả 100%.” | Tỷ lệ theo công thức thông thường không xác định. | Dùng `NULLIF`, nhãn hoặc chính sách nghiệp vụ riêng. |
| “Chỉ cần index là mọi window query đều nhanh.” | Còn chi phí sort, partition, số dòng, kế hoạch và dữ liệu. | Dùng `EXPLAIN` và đo workload thật. |

## 21. Bài tập thực hành có lời giải

Các bài dùng bảng `doanh_thu_ngay_win` ở mục 2 hoặc `su_kien_don_win` ở mục 12. Hãy xác định **partition**, **thứ tự**, **độ lệch** và **ngữ nghĩa `NULL`** trước khi đọc đáp án.

### Bài 1. Doanh thu lần trước theo từng cửa hàng

**Yêu cầu:** trả mã cửa hàng, ngày, doanh thu, doanh thu ở lần ghi nhận trước đó của **cùng cửa hàng**.

**Lời giải:**

~~~sql
SELECT
    cua_hang_id,
    ngay,
    doanh_thu,
    LAG(doanh_thu) OVER (
        PARTITION BY cua_hang_id
        ORDER BY ngay
    ) AS doanh_thu_truoc
FROM doanh_thu_ngay_win
ORDER BY cua_hang_id, ngay;
~~~

Ngày đầu mỗi cửa hàng có `doanh_thu_truoc = NULL`; tổng cộng vẫn **11 dòng**.

### Bài 2. Điều gì xảy ra nếu bỏ PARTITION BY?

~~~sql
SELECT
    cua_hang_id, ngay,
    LAG(doanh_thu) OVER (
        ORDER BY cua_hang_id, ngay
    ) AS doanh_thu_truoc
FROM doanh_thu_ngay_win
ORDER BY cua_hang_id, ngay;
~~~

**Câu hỏi:** Giá trị `doanh_thu_truoc` của cửa hàng 20 ngày 01/10 là bao nhiêu? Có đúng ý nghĩa không?

**Lời giải:** Giá trị là **800.000**, doanh thu của cửa hàng 10 ngày 07/10, vì đó là hàng đứng ngay trước theo `ORDER BY cua_hang_id, ngay` trên toàn tập. Nó **không đúng** yêu cầu so sánh trong từng cửa hàng. Sửa bằng `PARTITION BY cua_hang_id ORDER BY ngay`.

### Bài 3. LAG với độ lệch 2

**Yêu cầu:** ngày 04/10 của cửa hàng 10, `LAG(doanh_thu, 2)` trả giá trị nào?

**Lời giải:** **1.000.000**, vì hai hàng trước ngày 04/10 là ngày 01/10. Không phải giá trị ngày 02/10 hoặc ngày 02/10 tính theo “hai ngày trước”; độ lệch là **hai vị trí hàng**.

### Bài 4. Default có thay NULL của hàng trước không?

~~~sql
SELECT
    ngay,
    LAG(doanh_thu, 1, -1) OVER (
        ORDER BY ngay
    ) AS gia_tri
FROM doanh_thu_ngay_win
WHERE cua_hang_id = 10
ORDER BY ngay;
~~~

**Câu hỏi:** Ngày 01/10 và 06/10 trả gì?

**Lời giải:** Ngày 01/10 trả **`-1`** vì không có hàng trước. Ngày 06/10 trả **`NULL`**, vì hàng trước là ngày 05/10 **có tồn tại** nhưng `doanh_thu IS NULL`. Default chỉ dành cho trường hợp **hàng lân cận không tồn tại**.

### Bài 5. Tính doanh thu thay đổi tuyệt đối

**Yêu cầu:** tính `doanh_thu - doanh_thu_truoc` cho từng cửa hàng.

**Lời giải:**

~~~sql
WITH x AS (
    SELECT
        cua_hang_id,
        ngay,
        doanh_thu,
        LAG(doanh_thu) OVER (
            PARTITION BY cua_hang_id ORDER BY ngay
        ) AS doanh_thu_truoc
    FROM doanh_thu_ngay_win
)
SELECT
    cua_hang_id,
    ngay,
    doanh_thu - doanh_thu_truoc AS chenh_lech
FROM x
ORDER BY cua_hang_id, ngay;
~~~

Cửa hàng 10 ngày 02/10 là **+300.000**, ngày 04/10 là **-400.000**; cửa hàng 20 ngày 04/10 là **0**.

### Bài 6. Tính tỷ lệ thay đổi mà không chia cho 0

**Yêu cầu:** tỷ lệ tăng trưởng giữa hai lần ghi nhận của cửa hàng 10, làm tròn hai chữ số thập phân.

**Lời giải:**

~~~sql
WITH x AS (
    SELECT
        ngay,
        doanh_thu,
        LAG(doanh_thu) OVER (ORDER BY ngay) AS doanh_thu_truoc
    FROM doanh_thu_ngay_win
    WHERE cua_hang_id = 10
)
SELECT
    ngay,
    ROUND(
        (doanh_thu - doanh_thu_truoc) * 100.0
        / NULLIF(doanh_thu_truoc, 0),
        2
    ) AS ty_le_pct
FROM x
ORDER BY ngay;
~~~

Ngày 02/10 là **+30,00%**, ngày 04/10 khoảng **-30,77%**, ngày 07/10 **`NULL`** vì mẫu số 0. Đừng coi `NULL` là 0% nếu chưa có quy tắc báo cáo.

### Bài 7. Hàng trước không nhất thiết là ngày hôm qua

**Câu hỏi:** Ngày 04/10 cửa hàng 10 có `LAG(ngay)` là ngày nào? Nếu chỉ muốn chênh lệch với **ngày hôm qua**, có nên dùng nó không?

**Lời giải:** `LAG(ngay)` là **02/10** vì không có bản ghi 03/10. Chỉ tính chênh lệch với hôm qua khi `ngay_truoc = ngay - 1`, hoặc xây lịch đầy đủ và quy định cách xử lý ngày không có bản ghi.

### Bài 8. Tìm các lần doanh thu tăng

**Yêu cầu:** chỉ liệt kê những ngày có doanh thu tăng so với lần ghi nhận trước của cùng cửa hàng.

**Lời giải:**

~~~sql
WITH x AS (
    SELECT
        cua_hang_id,
        ngay,
        doanh_thu,
        LAG(doanh_thu) OVER (
            PARTITION BY cua_hang_id ORDER BY ngay
        ) AS doanh_thu_truoc
    FROM doanh_thu_ngay_win
)
SELECT cua_hang_id, ngay, doanh_thu
FROM x
WHERE doanh_thu > doanh_thu_truoc
ORDER BY cua_hang_id, ngay;
~~~

Kết quả có **4 dòng**: cửa hàng 10 ngày 02/10, 07/10; cửa hàng 20 ngày 03/10, 07/10. Không viết `LAG` trực tiếp trong `WHERE` cùng cấp.

### Bài 9. Lọc trước và sau khi tính LAG

**Yêu cầu:** chỉ hiển thị doanh thu từ 04/10 của cửa hàng 10, nhưng ngày 04/10 phải biết lần ghi nhận trước là 02/10.

**Lời giải:**

~~~sql
WITH x AS (
    SELECT
        ngay,
        doanh_thu,
        LAG(doanh_thu) OVER (
            ORDER BY ngay
        ) AS doanh_thu_truoc
    FROM doanh_thu_ngay_win
    WHERE cua_hang_id = 10
)
SELECT *
FROM x
WHERE ngay >= DATE '2026-10-04'
ORDER BY ngay;
~~~

Đặt điều kiện ngày **sau CTE** để LAG có thể dùng các hàng trước 04/10; giá trị doanh thu trước ngày 04/10 là **1.300.000**.

### Bài 10. Trạng thái trước và sau

**Yêu cầu:** mỗi sự kiện của đơn 101 có cột trạng thái trước và trạng thái sau.

**Lời giải:**

~~~sql
SELECT
    id,
    trang_thai,
    LAG(trang_thai) OVER (
        PARTITION BY don_hang_id
        ORDER BY thoi_diem, id
    ) AS trang_thai_truoc,
    LEAD(trang_thai) OVER (
        PARTITION BY don_hang_id
        ORDER BY thoi_diem, id
    ) AS trang_thai_sau
FROM su_kien_don_win
WHERE don_hang_id = 101
ORDER BY thoi_diem, id;
~~~

Đơn 101 có chuỗi **MOI → XAC_NHAN → DANG_GIAO → HOAN_TAT**. Cột `id` phân xử hai sự kiện có cùng thời điểm 09:00 theo quy ước dữ liệu mẫu.

### Bài 11. Phát hiện chuyển trạng thái

**Yêu cầu:** chỉ lấy các sự kiện có trạng thái khác sự kiện ngay trước, không tính sự kiện đầu mỗi đơn.

**Lời giải:**

~~~sql
WITH x AS (
    SELECT
        *,
        LAG(id) OVER (
            PARTITION BY don_hang_id ORDER BY thoi_diem, id
        ) AS id_truoc,
        LAG(trang_thai) OVER (
            PARTITION BY don_hang_id ORDER BY thoi_diem, id
        ) AS trang_thai_truoc
    FROM su_kien_don_win
)
SELECT don_hang_id, id, trang_thai_truoc, trang_thai
FROM x
WHERE id_truoc IS NOT NULL
  AND trang_thai IS DISTINCT FROM trang_thai_truoc
ORDER BY don_hang_id, id;
~~~

Có **4 chuyển trạng thái** trong bộ dữ liệu mẫu. `IS DISTINCT FROM` là phép so sánh null-safe của PostgreSQL.

### Bài 12. Thời gian đến sự kiện kế tiếp

**Yêu cầu:** tính khoảng thời gian từ mỗi sự kiện đến sự kiện kế tiếp của **cùng đơn**.

**Lời giải:**

~~~sql
SELECT
    don_hang_id,
    id,
    LEAD(thoi_diem) OVER (
        PARTITION BY don_hang_id
        ORDER BY thoi_diem, id
    ) - thoi_diem AS khoang_cho
FROM su_kien_don_win
ORDER BY don_hang_id, thoi_diem, id;
~~~

Kết quả là `INTERVAL` trong PostgreSQL. Ở sự kiện cuối mỗi đơn, `khoang_cho = NULL`; từ sự kiện 2 đến 3 của đơn 101 là **0** do cùng timestamp.

### Bài 13. Giữ NULL hay bỏ qua NULL?

**Yêu cầu:** với cửa hàng 10 ngày 06/10, muốn tìm **giá trị doanh thu khác NULL gần nhất trước ngày đó**. `LAG(doanh_thu)` thông thường trả bao nhiêu? Giá trị mong muốn là bao nhiêu?

**Lời giải:** `LAG(doanh_thu)` trả **`NULL`** vì ngày 05/10 có bản ghi với doanh thu `NULL`. Giá trị khác NULL gần nhất là **900.000** từ ngày 04/10. Có thể dùng truy vấn con có điều kiện `d2.doanh_thu IS NOT NULL AND d2.ngay < d.ngay ORDER BY d2.ngay DESC LIMIT 1` như mục 13. Không tự thêm `IGNORE NULLS` vào PostgreSQL vì cú pháp đó không được hỗ trợ cho `LAG`.

### Bài 14. Một hàng cho một ngày trước khi so sánh

**Yêu cầu:** nguồn `giao_dich` có nhiều giao dịch của cùng cửa hàng trong một ngày. Muốn so sánh **tổng doanh thu từng ngày** bằng LAG thì cần bước gì?

**Lời giải:** Phải **tổng hợp `SUM(so_tien)` theo `cua_hang_id` và ngày** trước khi dùng `LAG` trên kết quả tổng hợp. Nếu dùng LAG trực tiếp trên các giao dịch riêng lẻ, ta đang so sánh **giao dịch trước đó**, không phải **ngày trước đó**. Có thể tạo CTE `doanh_thu_theo_ngay` như mục 14.2.

### Bài 15. Đặt thứ tự đồng hạng

Hai sự kiện của cùng đơn có `thoi_diem = '2026-10-01 09:00:00+07'`. Vì sao `ORDER BY thoi_diem` một mình chưa đủ cho LAG/LEAD?

**Lời giải:** Hai hàng là **đồng hạng theo khóa sắp xếp**, nên không có thứ tự xác định giữa chúng chỉ từ timestamp. Cần thêm cột như `id` hoặc `so_thu_tu_su_kien` có ý nghĩa. Nếu thứ tự nghiệp vụ khác thứ tự ID, phải dùng đúng cột trình tự nghiệp vụ, không chỉ ép thứ tự kỹ thuật.

## 22. Bảng lựa chọn nhanh

| Câu hỏi | Mẫu SQL | Điểm phải xác định |
| --- | --- | --- |
| Giá trị của hàng trước | `LAG(x) OVER (... ORDER BY ...)` | Partition và thứ tự |
| Giá trị của hàng sau | `LEAD(x) OVER (... ORDER BY ...)` | Partition và thứ tự |
| Giá trị cách hai lần ghi nhận | `LAG(x, 2)` hoặc `LEAD(x, 2)` | Offset là số hàng, không phải thời gian |
| Giá trị mặc định khi không có hàng | `LAG(x, 1, mac_dinh)` | Không thay `NULL` của hàng có thật |
| Chênh lệch so với lần trước | `x - LAG(x) OVER (...)` hoặc CTE | `NULL` và thứ tự thời gian |
| Tỷ lệ tăng trưởng | `(x - x_truoc) / NULLIF(x_truoc, 0)` | Mẫu số 0, kiểu số và quy ước báo cáo |
| Chỉ lấy hàng tăng | CTE tạo `x_truoc`, ngoài `WHERE x > x_truoc` | Không dùng window function trực tiếp trong WHERE |
| Khoảng thời gian đến sự kiện sau | `LEAD(thoi_diem) ... - thoi_diem` | Timestamp, múi giờ, tie-breaker |
| So sánh đúng ngày hôm qua | `LAG(ngay)` + kiểm tra khoảng 1 ngày | Không tự cho hàng trước là ngày hôm qua |
| Tìm giá trị khác NULL gần nhất | Truy vấn tương quan, hoặc `IGNORE NULLS` nơi được hỗ trợ | Hành vi `NULL` của DBMS |
| Một chuỗi riêng cho mỗi khách/cửa hàng | `PARTITION BY ma_doi_tuong` | Đầy đủ khóa nhóm, tránh trộn dữ liệu |
| So sánh theo tổng ngày/tháng | `GROUP BY` trước, `LAG` sau | Grain nguồn phải đúng |
| Đoạn trạng thái liên tiếp | `LAG` tạo cờ thay đổi + `SUM` cộng dồn | CTE trung gian và thứ tự ổn định |
| Tối ưu LAG/LEAD | Index thích hợp, `EXPLAIN`, điều kiện lọc | Không làm mất hàng lịch sử cần để so sánh |

## 23. Kết luận

`LAG` và `LEAD` cho phép so sánh **nhiều hàng trong cùng chuỗi có thứ tự** mà không phải tự ghép bảng với chính nó. Chúng thường được dùng trong phân tích doanh thu, tồn kho, thay đổi trạng thái, lịch sử giá, đo khoảng thời gian và báo cáo tăng trưởng.

Hãy kiểm tra những ý chính khi viết một truy vấn:

1. **Mỗi hàng đại diện cho gì?** Một giao dịch, một ngày, một tháng hay một sự kiện? Nếu cần so sánh tổng theo ngày, hãy tổng hợp về một dòng mỗi ngày trước.
2. **Các hàng nào được phép so sánh với nhau?** Đặt đúng `PARTITION BY` theo khóa khách, cửa hàng, sản phẩm hoặc đối tượng nghiệp vụ.
3. **“Trước/sau” được xác định theo trường nào?** Đặt `ORDER BY` trong `OVER`, thêm khóa phân xử khi có hàng đồng hạng.
4. **Offset đo đơn vị gì?** Đó là **số hàng**; không mặc định là số ngày, số tháng hay khoảng thời gian.
5. **Có hàng nhưng giá trị `NULL`, hay không có hàng?** Đối số mặc định của `LAG`/`LEAD` chỉ giải quyết trường hợp không có hàng ở vị trí yêu cầu.
6. **Giá trị trước bằng 0 hoặc dữ liệu bị thiếu thì sao?** Dùng `NULLIF`, `CASE` và quy tắc xử lý dữ liệu rõ ràng trước khi tính chênh lệch/tỷ lệ.
7. **Cần lọc kết quả tính toán hay lọc nguồn trước khi tính?** CTE giúp tách hai giai đoạn để không vô tình làm mất hàng tham chiếu.

**Điểm cốt lõi:** `LAG` và `LEAD` không hiểu nghiệp vụ “hôm qua”, “lần trước hợp lệ” hay “trạng thái thực sự trước đó” nếu người viết chưa **định nghĩa đúng grain, partition, thứ tự và chính sách dữ liệu thiếu**. Khi bốn yếu tố đó rõ ràng, hai hàm trở thành công cụ ngắn gọn và mạnh mẽ để biến dữ liệu từng hàng thành thông tin về **sự thay đổi giữa các hàng**.
