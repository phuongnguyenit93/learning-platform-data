# Tìm hàng lớn nhất mỗi nhóm và xử lý đồng hạng

Trong báo cáo dữ liệu, một yêu cầu rất thường gặp là **tìm bản ghi có giá trị lớn nhất trong từng nhóm**. Ví dụ: mỗi khu vực có đơn bán hàng nào giá trị cao nhất, mỗi khách hàng có giao dịch gần đây nhất, mỗi sản phẩm có lần cập nhật giá mới nhất, hoặc mỗi phòng ban có nhân viên nhận mức lương cao nhất.

Vấn đề không chỉ là tính **MAX**. Nếu muốn hiển thị **toàn bộ thông tin của bản ghi đạt cực đại**, ta phải tìm lại hàng tương ứng. Hơn nữa, có thể có **hai hoặc nhiều hàng cùng đạt mức lớn nhất** (*đồng hạng*, *ties*). Khi đó, yêu cầu “lấy hàng lớn nhất mỗi nhóm” có ít nhất hai cách hiểu khác nhau:

- **Giữ tất cả đồng hạng:** trả về mọi hàng cùng đạt giá trị lớn nhất của nhóm.
- **Chỉ chọn một hàng đại diện:** thêm quy tắc phá hòa, ví dụ ưu tiên ngày mới nhất rồi mã bản ghi lớn nhất, để kết quả có tính xác định.

Hai cách hiểu này không tương đương. Câu SQL đúng phải phản ánh **quy tắc nghiệp vụ** trước khi chọn kỹ thuật thực hiện.

Bài học thuộc chương **Truy vấn con** của module **Database SQL**. Trọng tâm là các cách dùng **truy vấn con tương quan**, **truy vấn con tổng hợp kết hợp JOIN** và **NOT EXISTS**; sau đó đối chiếu với **hàm cửa sổ** như ROW_NUMBER, RANK, DENSE_RANK và cú pháp DISTINCT ON của PostgreSQL. Các ví dụ chính chạy trên **PostgreSQL 15 trở lên**.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt **MAX của một nhóm** với **hàng chứa giá trị MAX của nhóm**.
2. Viết truy vấn con tương quan để tìm mọi hàng đạt cực đại.
3. Tạo bảng kết quả **MAX theo nhóm** rồi JOIN trở lại bảng chi tiết.
4. Viết **NOT EXISTS** để tìm hàng không bị hàng nào trong cùng nhóm vượt qua.
5. Phân biệt **ROW_NUMBER**, **RANK** và **DENSE_RANK** khi có đồng hạng.
6. Chọn một hàng duy nhất theo thứ tự phá hòa **ổn định và xác định**.
7. Xử lý **NULL**, nhóm toàn NULL, và nhóm chưa có bản ghi.
8. Xem xét hiệu năng, chỉ mục và khác biệt cú pháp theo phương ngữ SQL.

## 2. Dữ liệu thực hành độc lập

Để không phụ thuộc vào bất kỳ bảng nào của bài khác, ta tạo hai **bảng tạm** trong PostgreSQL:

- **top_group_sales:** giao dịch bán hàng, gồm mã giao dịch, khu vực, người bán, ngày bán, tiền giao dịch và trạng thái.
- **top_group_regions:** danh sách khu vực cần báo cáo, kể cả một khu vực chưa có giao dịch nào.

~~~sql
CREATE TEMP TABLE top_group_sales (
    sale_id       INTEGER PRIMARY KEY,
    region        TEXT NOT NULL,
    seller_id     INTEGER NOT NULL,
    sold_on       DATE NOT NULL,
    amount_vnd    NUMERIC(12, 2),
    sale_status   TEXT NOT NULL
);

CREATE TEMP TABLE top_group_regions (
    region TEXT PRIMARY KEY
);

INSERT INTO top_group_regions(region)
VALUES
    ('Bac'),
    ('Nam'),
    ('Trung'),
    ('Tay'),
    ('Hai dao');

INSERT INTO top_group_sales
    (sale_id, region, seller_id, sold_on, amount_vnd, sale_status)
VALUES
    ( 1, 'Bac',   10, '2026-04-01', 500000, 'paid'),
    ( 2, 'Bac',   11, '2026-04-02', 900000, 'paid'),
    ( 3, 'Bac',   12, '2026-04-03', 900000, 'paid'),
    ( 4, 'Bac',   13, '2026-04-04', 300000, 'pending'),
    ( 5, 'Bac',   14, '2026-04-05', NULL,   'paid'),
    ( 6, 'Nam',   20, '2026-04-01', 750000, 'paid'),
    ( 7, 'Nam',   21, '2026-04-03', 600000, 'paid'),
    ( 8, 'Nam',   22, '2026-04-05', 750000, 'paid'),
    ( 9, 'Nam',   23, '2026-04-07', 100000, 'pending'),
    (10, 'Trung', 30, '2026-04-04', 400000, 'paid'),
    (11, 'Trung', 31, '2026-04-06', 400000, 'paid'),
    (12, 'Trung', 32, '2026-04-10', 200000, 'paid'),
    (13, 'Tay',   40, '2026-04-01', NULL,   'paid'),
    (14, 'Tay',   41, '2026-04-05', NULL,   'pending');
~~~

Chạy truy vấn để xem dữ liệu:

~~~sql
SELECT sale_id, region, seller_id, sold_on,
       amount_vnd, sale_status
FROM top_group_sales
ORDER BY region, sale_id;
~~~

Các đặc điểm được cố ý đưa vào dữ liệu:

| Khu vực | Số giao dịch | Số tiền cao nhất đã biết | Các sale_id cùng đạt cực đại |
| --- | ---: | ---: | --- |
| Bac | 5 | 900000 | **2, 3** |
| Nam | 4 | 750000 | **6, 8** |
| Trung | 3 | 400000 | **10, 11** |
| Tay | 2 | **NULL** | Không có giá trị tiền xác định |
| Hai dao | 0 | **NULL** | Không có bản ghi giao dịch |

**Tay** có hai giao dịch nhưng cả hai chưa có số tiền; **Hai dao** hoàn toàn không có giao dịch. Đây là hai tình huống khác nhau, dù kết quả MAX có thể đều là NULL.

> Các tên khu vực chỉ là mã minh họa. Bảng tạm chỉ tồn tại trong phiên kết nối hiện tại. Nếu tạo lại trong cùng phiên, hãy xóa riêng hai bảng tạm hoặc mở phiên mới. Không cần sửa bất kỳ bảng nghiệp vụ nào.

## 3. MAX theo nhóm chưa trả về hàng chi tiết

Trước hết, dùng GROUP BY và MAX để tìm **giá trị số tiền lớn nhất** của mỗi khu vực:

~~~sql
SELECT
    region,
    MAX(amount_vnd) AS max_amount_vnd
FROM top_group_sales
GROUP BY region
ORDER BY region;
~~~

Kết quả:

| region | max_amount_vnd |
| --- | ---: |
| Bac | 900000 |
| Nam | 750000 |
| Tay | NULL |
| Trung | 400000 |

Truy vấn trả **một dòng cho mỗi region có mặt trong bảng giao dịch**. Nó không cho biết **sale_id**, **seller_id** hay **sold_on** của bản ghi đạt cực đại.

### 3.1. Vì sao không thể tùy tiện SELECT thêm sale_id?

Ví dụ không hợp lệ theo quy tắc GROUP BY chặt chẽ của PostgreSQL:

~~~sql
-- Sai: sale_id không thuộc GROUP BY và không nằm trong hàm tổng hợp.
SELECT region, sale_id, MAX(amount_vnd)
FROM top_group_sales
GROUP BY region;
~~~

Một khu vực có thể có nhiều giao dịch. Cơ sở dữ liệu không thể tự biết **sale_id nào** bạn muốn đặt cạnh MAX(amount_vnd). Ngay cả khi hệ quản trị hoặc cấu hình SQL cho phép chọn cột không nhóm trong một số tình huống, **không nên xem sale_id được chọn tùy ý là sale_id của hàng cực đại**.

### 3.2. MAX của hai cột không có nghĩa cùng một hàng

~~~sql
SELECT
    region,
    MAX(amount_vnd) AS max_amount_vnd,
    MAX(sold_on) AS latest_date
FROM top_group_sales
GROUP BY region
ORDER BY region;
~~~

Ở Bac:

- **MAX(amount_vnd) = 900000**, thuộc các giao dịch 2 và 3.
- **MAX(sold_on) = 2026-04-05**, thuộc giao dịch 5, nhưng giao dịch 5 có **amount_vnd = NULL**.

Nếu đặt hai MAX cạnh nhau rồi kết luận có một giao dịch **900.000 đồng ngày 05/04**, bạn đã ghép **hai giá trị cực đại độc lập** thành một bản ghi không tồn tại.

**Bài toán tìm hàng lớn nhất** phải giữ quan hệ giữa giá trị cực đại và **các cột của chính hàng đó**.

### 3.3. MAX bỏ qua NULL

Trong các hệ SQL thông dụng, MAX(amount_vnd) bỏ qua những giá trị NULL:

- Bac có một giao dịch NULL nhưng MAX vẫn là **900000**.
- Tay chỉ có giá trị NULL nên MAX là **NULL**.
- Nếu nguồn không có hàng, MAX trên tập rỗng cũng cho NULL.

NULL có nghĩa là chưa biết giá trị, **không đồng nghĩa với số 0**. Không nên dùng COALESCE(amount_vnd, 0) để thay đổi cách tìm cực đại nếu chưa có quy tắc nghiệp vụ cho phép coi thiếu số tiền là 0.

## 4. Cách 1 — Truy vấn con tương quan với MAX

**Truy vấn con tương quan** (*correlated subquery*) là truy vấn con dùng một giá trị từ hàng của truy vấn ngoài. Để tìm mọi giao dịch bằng số tiền lớn nhất **trong chính khu vực của nó**, viết:

~~~sql
SELECT
    s.sale_id,
    s.region,
    s.seller_id,
    s.sold_on,
    s.amount_vnd
FROM top_group_sales AS s
WHERE s.amount_vnd = (
    SELECT MAX(x.amount_vnd)
    FROM top_group_sales AS x
    WHERE x.region = s.region
)
ORDER BY s.region, s.sale_id;
~~~

Đọc từ trong ra ngoài:

1. Xét một hàng **s** của bảng ngoài.
2. Truy vấn con tìm MAX(amount_vnd) của **mọi hàng x có x.region = s.region**.
3. Bảng ngoài chỉ giữ hàng nếu **s.amount_vnd bằng MAX vừa tìm**.
4. Nếu có nhiều hàng đạt cùng MAX, **tất cả đều thỏa điều kiện**.

Kết quả:

| sale_id | region | seller_id | sold_on | amount_vnd |
| ---: | --- | ---: | --- | ---: |
| 2 | Bac | 11 | 2026-04-02 | 900000 |
| 3 | Bac | 12 | 2026-04-03 | 900000 |
| 6 | Nam | 20 | 2026-04-01 | 750000 |
| 8 | Nam | 22 | 2026-04-05 | 750000 |
| 10 | Trung | 30 | 2026-04-04 | 400000 |
| 11 | Trung | 31 | 2026-04-06 | 400000 |

Có **6 hàng**, không phải 3. Đây là hành vi đúng khi yêu cầu **giữ tất cả giao dịch đồng hạng**.

### 4.1. Vai trò của điều kiện tương quan

Điều kiện:

~~~sql
WHERE x.region = s.region
~~~

đảm bảo MAX được tính **trong cùng một khu vực** với hàng s đang xét. Nếu bỏ điều kiện này:

~~~sql
-- Sai yêu cầu "mỗi nhóm": chỉ tìm MAX toàn bảng.
WHERE s.amount_vnd = (
    SELECT MAX(x.amount_vnd)
    FROM top_group_sales AS x
)
~~~

ta chỉ tìm các giao dịch có số tiền bằng **900000**, tức giao dịch cực đại **toàn bộ bảng**, không còn cực đại của từng region.

### 4.2. Phân biệt truy vấn con tương quan và không tương quan

Trong ví dụ chính, subquery tham chiếu **s.region** từ truy vấn ngoài, nên là **tương quan**. Trong ví dụ MAX toàn bảng, subquery không dùng bất kỳ cột nào từ truy vấn ngoài, nên là **không tương quan**.

Điều này mô tả **quan hệ logic** giữa hai cấp truy vấn, **không có nghĩa PostgreSQL bắt buộc chạy truy vấn con một lần cho từng hàng một cách máy móc**. Bộ tối ưu có thể biến đổi kế hoạch thực thi khi phù hợp.

### 4.3. Vì sao Tay không xuất hiện?

Ở Tay, MAX(amount_vnd) là NULL; s.amount_vnd cũng là NULL. Nhưng:

~~~sql
NULL = NULL
~~~

trả **UNKNOWN**, không phải TRUE. Điều kiện WHERE chỉ giữ TRUE, nên **không có giao dịch Tay** trong kết quả.

Đây là hành vi hợp lý nếu định nghĩa cực đại yêu cầu phải có **số tiền xác định**. Nếu nghiệp vụ muốn vẫn trả một hàng đại diện cho khu vực có toàn bộ số tiền NULL, cần một chiến lược khác ở các phần sau.

## 5. Cách 2 — GROUP BY MAX rồi JOIN trở lại bảng chi tiết

Một phương pháp rất phổ biến là dùng **bảng dẫn xuất** (*derived table*) để tính MAX theo nhóm, sau đó **JOIN** với bảng chi tiết:

~~~sql
SELECT
    s.sale_id,
    s.region,
    s.seller_id,
    s.sold_on,
    s.amount_vnd
FROM top_group_sales AS s
JOIN (
    SELECT region, MAX(amount_vnd) AS max_amount_vnd
    FROM top_group_sales
    GROUP BY region
) AS m
    ON s.region = m.region
   AND s.amount_vnd = m.max_amount_vnd
ORDER BY s.region, s.sale_id;
~~~

Truy vấn được chia thành hai bước logic:

~~~text
top_group_sales
       |
       +--> GROUP BY region + MAX(amount_vnd)
       |                 |
       |           (region, max_amount_vnd)
       |                 |
       +---------------- JOIN theo region và số tiền
                             |
                       Các hàng cực đại
~~~

Bảng dẫn xuất m có **một dòng cho mỗi region** xuất hiện trong dữ liệu:

| m.region | m.max_amount_vnd |
| --- | ---: |
| Bac | 900000 |
| Nam | 750000 |
| Trung | 400000 |
| Tay | NULL |

Khi nối trở lại, hai giao dịch cùng MAX ở Bac **đều khớp một dòng m của Bac**; tương tự Nam và Trung. Kết quả vẫn là **6 giao dịch 2, 3, 6, 8, 10, 11**.

### 5.1. Có thể viết bằng CTE

Để dễ đọc:

~~~sql
WITH maximum_per_region AS (
    SELECT region, MAX(amount_vnd) AS max_amount_vnd
    FROM top_group_sales
    GROUP BY region
)
SELECT
    s.sale_id, s.region, s.seller_id,
    s.sold_on, s.amount_vnd
FROM top_group_sales AS s
JOIN maximum_per_region AS m
    ON s.region = m.region
   AND s.amount_vnd = m.max_amount_vnd
ORDER BY s.region, s.sale_id;
~~~

CTE **không đổi ý nghĩa** của phương pháp: ta vẫn tạo một tập MAX theo region rồi ghép lại để lấy các cột của hàng chi tiết.

### 5.2. Không quên ghép cả khóa nhóm và giá trị MAX

Chỉ nối theo số tiền:

~~~sql
-- Không đủ điều kiện: một số tiền cực đại có thể xuất hiện ở nhóm khác.
ON s.amount_vnd = m.max_amount_vnd
~~~

có thể ghép nhầm khi hai region khác nhau tình cờ có cùng mức MAX. Điều kiện đúng là **cùng region** và **cùng số tiền MAX của region ấy**.

Ngược lại, chỉ nối theo region mà không kiểm tra số tiền sẽ trả **mọi giao dịch của region**, không phải chỉ giao dịch lớn nhất.

### 5.3. Đừng nhầm JOIN làm dữ liệu nhân đôi với đồng hạng hợp lệ

Nếu trong kết quả có hai giao dịch Bac, đó là vì **hai hàng gốc khác nhau cùng đạt cực đại**. Không dùng SELECT DISTINCT để tùy tiện ép thành một hàng: chúng có sale_id, seller_id và ngày giao dịch khác nhau.

Nếu yêu cầu là **một hàng duy nhất mỗi khu vực**, cần **quy tắc chọn hàng đại diện**, không phải phép loại trùng vô điều kiện.

## 6. Cách 3 — NOT EXISTS: tìm hàng không bị vượt qua

Một cách nhìn khác: **hàng đạt cực đại** là hàng **không tồn tại hàng nào trong cùng nhóm có giá trị lớn hơn nó**.

Ta có thể diễn đạt trực tiếp với **NOT EXISTS**:

~~~sql
SELECT
    s.sale_id,
    s.region,
    s.seller_id,
    s.sold_on,
    s.amount_vnd
FROM top_group_sales AS s
WHERE s.amount_vnd IS NOT NULL
  AND NOT EXISTS (
      SELECT 1
      FROM top_group_sales AS x
      WHERE x.region = s.region
        AND x.amount_vnd > s.amount_vnd
  )
ORDER BY s.region, s.sale_id;
~~~

Diễn giải:

- Chỉ xét hàng s có **amount_vnd xác định**.
- Nếu còn một hàng x cùng region với **amount_vnd > s.amount_vnd**, s không thể là hàng lớn nhất.
- Nếu **không tồn tại** hàng x lớn hơn, s là một trong các hàng đạt cực đại.
- Hai hàng đồng hạng không loại nhau, vì quan hệ so sánh dùng **>**, không phải **>=**.

Kết quả vẫn gồm **2, 3, 6, 8, 10, 11**.

### 6.1. Vì sao phải có IS NOT NULL?

Nếu bỏ:

~~~sql
WHERE s.amount_vnd IS NOT NULL
~~~

thì một hàng s có amount_vnd NULL sẽ không tìm thấy x thỏa **x.amount_vnd > NULL**, vì phép so sánh đó luôn UNKNOWN. Truy vấn con không có hàng thỏa, **NOT EXISTS trở thành TRUE**, và hàng thiếu tiền có thể bị coi nhầm là cực đại.

Vì vậy, khi định nghĩa “số tiền lớn nhất có thật”, **phải loại giá trị NULL hoặc xử lý nó bằng một quy tắc tường minh**. Nếu amount_vnd đã được khai báo NOT NULL trong schema, điều kiện phụ không cần thiết; nhưng bộ dữ liệu ví dụ cố ý cho phép NULL.

### 6.2. Khi nào NOT EXISTS thuận tiện?

NOT EXISTS đặc biệt rõ ràng nếu định nghĩa “tốt nhất” là **không có hàng nào vượt trội** theo một quan hệ so sánh phức tạp. Ví dụ, tìm giá tốt nhất theo một số tiêu chí, hoặc chọn hàng mà không hàng nào có điểm cao hơn trong cùng nhóm.

Tuy nhiên, với nhiều tiêu chí **không tạo thứ tự toàn phần**, có thể có nhiều hàng không bị vượt trội nhưng không có cùng một giá trị đơn giản. Khi đó bài toán trở thành tìm các hàng **không bị chi phối** (*non-dominated rows*), không còn hoàn toàn giống MAX một cột. Cần phát biểu rõ quan hệ “vượt qua” trước khi viết NOT EXISTS.

## 7. Ba phương pháp truy vấn con có cùng mục tiêu, nhưng khác cách diễn đạt

| Cách | Ý tưởng | Giữ mọi đồng hạng? | Chú ý NULL |
| --- | --- | --- | --- |
| **Tương quan với MAX** | s.amount = MAX(amount của nhóm s) | Có | MAX toàn NULL ⇒ phép = NULL không TRUE |
| **GROUP BY MAX + JOIN** | Tính bảng MAX theo nhóm rồi JOIN về chi tiết | Có | JOIN bằng NULL không khớp |
| **NOT EXISTS** | Không có hàng cùng nhóm lớn hơn s | Có nếu dùng > | Cần chặn s.amount NULL khi tìm cực đại số |

Không có cách nào **luôn nhanh nhất** trên mọi bộ dữ liệu. Bộ tối ưu, chỉ mục, tần suất lặp nhóm và số lượng hàng quyết định kế hoạch thực thi thực tế.

Trong truy vấn nghiệp vụ, nên chọn cách có **ý nghĩa rõ ràng**, dễ chứng minh đúng và phù hợp với khả năng quản lý của dự án; sau đó mới đo đạc hiệu năng.

## 8. Đồng hạng: giữ tất cả hay chỉ lấy một hàng?

Với dữ liệu mẫu, Bac có **hai giao dịch cùng 900.000**, Nam có **hai giao dịch cùng 750.000**, Trung có **hai giao dịch cùng 400.000**.

Nếu yêu cầu của phòng kinh doanh là **“liệt kê tất cả người bán đạt doanh số giao dịch cao nhất trong từng khu vực”**, cần trả **đủ hai người ở mỗi khu vực**. Truy vấn MAX tương quan, MAX + JOIN hoặc NOT EXISTS phù hợp.

Nếu yêu cầu của giao diện là **“mỗi khu vực chỉ hiển thị một giao dịch tiêu biểu”**, bạn phải xác định cách phá hòa. Ví dụ:

1. Ưu tiên **số tiền cao nhất**.
2. Nếu bằng tiền, ưu tiên **ngày bán mới hơn**.
3. Nếu cùng cả ngày, ưu tiên **sale_id lớn hơn** để luôn chọn đúng một hàng.

Thứ tự ba tiêu chí đó dẫn tới các hàng đại diện:

| region | Giao dịch được chọn | Lý do |
| --- | ---: | --- |
| Bac | **3** | 900.000 đồng, ngày 03/04 mới hơn đơn 2 |
| Nam | **8** | 750.000 đồng, ngày 05/04 mới hơn đơn 6 |
| Trung | **11** | 400.000 đồng, ngày 06/04 mới hơn đơn 10 |
| Tay | **14** nếu cho phép chọn đại diện dù tiền NULL | Cả hai tiền NULL, ngày 05/04 mới hơn |

**Hai mục tiêu không nên trộn lẫn:** một truy vấn phá hòa để trả đúng một hàng sẽ **loại có chủ ý những hàng đồng hạng khác**. Không được nói nó đã “liệt kê tất cả đồng hạng”.

## 9. Cách 4 — Truy vấn con tương quan chọn một sale_id

Vẫn dùng truy vấn con, nhưng thay vì so sánh tiền với MAX, ta **chọn mã giao dịch đứng đầu theo thứ tự rõ ràng**:

~~~sql
SELECT
    s.sale_id,
    s.region,
    s.seller_id,
    s.sold_on,
    s.amount_vnd
FROM top_group_sales AS s
WHERE s.sale_id = (
    SELECT x.sale_id
    FROM top_group_sales AS x
    WHERE x.region = s.region
    ORDER BY
        x.amount_vnd DESC NULLS LAST,
        x.sold_on DESC,
        x.sale_id DESC
    LIMIT 1
)
ORDER BY s.region;
~~~

Trong PostgreSQL, **LIMIT 1** đảm bảo subquery trả tối đa một sale_id; vì **sale_id là PRIMARY KEY**, thứ tự phá hòa đến sale_id là thứ tự xác định duy nhất. Kết quả có bốn hàng:

| region | sale_id | amount_vnd | sold_on |
| --- | ---: | ---: | --- |
| Bac | 3 | 900000 | 2026-04-03 |
| Nam | 8 | 750000 | 2026-04-05 |
| Tay | 14 | NULL | 2026-04-05 |
| Trung | 11 | 400000 | 2026-04-06 |

Với nhóm Tay, truy vấn chọn giao dịch 14 vì **NULLS LAST** để các giá trị số đã biết được ưu tiên khi có; trong nhóm Tay toàn NULL nên **ngày mới nhất** quyết định. Điều này **không chứng minh đơn 14 có số tiền lớn nhất đã biết**. Nó chỉ là **một hàng đại diện theo thứ tự đã khai báo**.

Nếu chỉ chấp nhận hàng có số tiền xác định, thêm điều kiện ngay trong subquery và ngoài:

~~~sql
SELECT s.sale_id, s.region, s.sold_on, s.amount_vnd
FROM top_group_sales AS s
WHERE s.amount_vnd IS NOT NULL
  AND s.sale_id = (
      SELECT x.sale_id
      FROM top_group_sales AS x
      WHERE x.region = s.region
        AND x.amount_vnd IS NOT NULL
      ORDER BY x.amount_vnd DESC,
               x.sold_on DESC,
               x.sale_id DESC
      LIMIT 1
  )
ORDER BY s.region;
~~~

Lúc này chỉ có ba khu vực **Bac, Nam, Trung**; Tay không có hàng đủ điều kiện.

### Vì sao ORDER BY phải có khóa phá hòa duy nhất?

Nếu chỉ viết **ORDER BY amount_vnd DESC LIMIT 1**, khi hai giao dịch cùng 900.000, PostgreSQL **không có nghĩa vụ** chọn sale_id 2 hay 3 theo một thứ tự ổn định. Các lần chạy hoặc kế hoạch thực thi có thể chọn khác nhau.

Thêm **sold_on DESC** làm rõ ưu tiên gần nhất; thêm **sale_id DESC** phá hòa cuối cùng vì sale_id duy nhất. Nếu không có cột duy nhất hoặc quy tắc phân biệt thêm, hãy chấp nhận rằng bài toán “chọn đúng một” cần quy ước bổ sung.

## 10. Cách 5 — Hàm cửa sổ: ROW_NUMBER, RANK và DENSE_RANK

**Hàm cửa sổ** (*window function*) là một cách rất tiện để tìm hàng lớn nhất mỗi nhóm. Khác với GROUP BY làm giảm số dòng, hàm cửa sổ có thể **gắn một thứ hạng lên mỗi hàng**, giữ nguyên các cột chi tiết.

Ta định nghĩa một cửa sổ theo region:

~~~sql
PARTITION BY region
ORDER BY amount_vnd DESC NULLS LAST
~~~

Trong đó:

- **PARTITION BY region** chia các hàng thành nhóm khu vực để tính thứ hạng riêng.
- **ORDER BY amount_vnd DESC NULLS LAST** xếp tiền lớn trước và tiền NULL sau.

Ba hàm thường dùng là:

| Hàm | Nếu hai hàng có cùng điểm xếp hạng | Ví dụ thứ hạng |
| --- | --- | --- |
| **ROW_NUMBER()** | Vẫn gán số liên tiếp khác nhau cho từng hàng | 1, 2, 3, 4 |
| **RANK()** | Hàng đồng hạng nhận cùng số, sau đó có khoảng nhảy | 1, 1, 3, 4 |
| **DENSE_RANK()** | Hàng đồng hạng nhận cùng số, không có khoảng nhảy | 1, 1, 2, 3 |

### 10.1. Quan sát ba thứ hạng trên dữ liệu có tiền xác định

~~~sql
SELECT
    region,
    sale_id,
    amount_vnd,
    ROW_NUMBER() OVER (
        PARTITION BY region
        ORDER BY amount_vnd DESC, sold_on DESC, sale_id DESC
    ) AS row_num,
    RANK() OVER (
        PARTITION BY region
        ORDER BY amount_vnd DESC
    ) AS amount_rank,
    DENSE_RANK() OVER (
        PARTITION BY region
        ORDER BY amount_vnd DESC
    ) AS amount_dense_rank
FROM top_group_sales
WHERE amount_vnd IS NOT NULL
ORDER BY region, amount_vnd DESC, sold_on DESC, sale_id DESC;
~~~

Đối với Bac, ta có:

| sale_id | amount_vnd | row_num | amount_rank | amount_dense_rank |
| ---: | ---: | ---: | ---: | ---: |
| 3 | 900000 | 1 | 1 | 1 |
| 2 | 900000 | 2 | 1 | 1 |
| 1 | 500000 | 3 | 3 | 2 |
| 4 | 300000 | 4 | 4 | 3 |

**ROW_NUMBER** dùng cả ngày và mã để tạo thứ tự xác định; **RANK** và **DENSE_RANK** trong ví dụ cố ý chỉ xếp theo **amount_vnd**, để hai giao dịch cùng 900.000 thực sự được coi là **đồng hạng về tiền**.

### 10.2. Chọn đúng một hàng với ROW_NUMBER

~~~sql
WITH ranked AS (
    SELECT
        s.*,
        ROW_NUMBER() OVER (
            PARTITION BY region
            ORDER BY
                amount_vnd DESC NULLS LAST,
                sold_on DESC,
                sale_id DESC
        ) AS rn
    FROM top_group_sales AS s
)
SELECT sale_id, region, seller_id, sold_on, amount_vnd
FROM ranked
WHERE rn = 1
ORDER BY region;
~~~

Kết quả là **3, 8, 14, 11**, một giao dịch cho mỗi khu vực **có hàng trong bảng sales**. Có thể loại Tay nếu yêu cầu chỉ lấy giá trị tiền đã biết bằng cách thêm **WHERE amount_vnd IS NOT NULL** trong CTE ranked.

**Vì sao cần CTE?** Trong PostgreSQL, ta không thể dùng trực tiếp giá trị ROW_NUMBER của chính danh sách SELECT trong WHERE cùng cấp. CTE (hoặc truy vấn con dẫn xuất) tạo thứ hạng trước; truy vấn bên ngoài mới lọc **rn = 1**.

### 10.3. Giữ mọi hàng đồng hạng với RANK

~~~sql
WITH ranked AS (
    SELECT
        s.*,
        RANK() OVER (
            PARTITION BY region
            ORDER BY amount_vnd DESC
        ) AS amount_rank
    FROM top_group_sales AS s
    WHERE amount_vnd IS NOT NULL
)
SELECT sale_id, region, seller_id, sold_on, amount_vnd
FROM ranked
WHERE amount_rank = 1
ORDER BY region, sale_id;
~~~

Kết quả trở lại **sáu giao dịch 2, 3, 6, 8, 10, 11**: tất cả những hàng đồng hạng cao nhất trong ba khu vực có số tiền xác định.

Nếu không lọc **amount_vnd IS NOT NULL** trong CTE, nhóm Tay có hai hàng NULL. Theo quy tắc sắp xếp của cửa sổ, cả hai cùng mức tiền NULL có thể nhận **RANK = 1**, dù không có cực đại số xác định. Vì vậy, cần quyết định trước cách xử lý NULL.

### 10.4. DENSE_RANK và “top N mức giá”

Với **DENSE_RANK**, khi chọn:

~~~sql
WITH ranked AS (
    SELECT
        s.*,
        DENSE_RANK() OVER (
            PARTITION BY region
            ORDER BY amount_vnd DESC
        ) AS price_level
    FROM top_group_sales AS s
    WHERE amount_vnd IS NOT NULL
)
SELECT region, sale_id, amount_vnd, price_level
FROM ranked
WHERE price_level <= 2
ORDER BY region, price_level, sale_id;
~~~

ta lấy **hai mức tiền khác nhau cao nhất của mỗi khu vực**, giữ mọi giao dịch cùng mức:

- Bac: giao dịch **2, 3** ở mức 900.000 và giao dịch **1** ở mức 500.000.
- Nam: giao dịch **6, 8** ở mức 750.000 và giao dịch **7** ở mức 600.000.
- Trung: giao dịch **10, 11** ở mức 400.000 và giao dịch **12** ở mức 200.000.

Nếu dùng **ROW_NUMBER <= 2**, mỗi khu vực có **tối đa hai hàng**, có thể lấy cả hai hàng đồng hạng cao nhất và không lấy mức tiền thứ hai khác biệt.

Nếu dùng **RANK <= 2**, một nhóm có hai hàng đồng hạng vị trí 1 sẽ có thứ hạng tiếp theo là 3, nên **mức tiền thứ hai có thể bị loại**. Cần hiểu “top N hàng”, “top N thứ hạng” và “top N mức giá khác nhau” là ba yêu cầu khác nhau.

### 10.5. Đừng vô tình phá đồng hạng của RANK

Nếu viết:

~~~sql
RANK() OVER (
    PARTITION BY region
    ORDER BY amount_vnd DESC, sale_id DESC
)
~~~

thì hai giao dịch cùng amount_vnd nhưng **khác sale_id** không còn đồng hạng theo toàn bộ danh sách ORDER BY. Khi sale_id là duy nhất, mỗi hàng sẽ có thứ tự riêng và **RANK = 1 chỉ còn một hàng**.

Nếu mục tiêu là **giữ mọi hàng có số tiền lớn nhất**, cửa sổ RANK phải xếp hạng theo **đúng tiêu chí cần coi là đồng hạng**, ví dụ chỉ **amount_vnd**.

## 11. Cách 6 — DISTINCT ON của PostgreSQL

PostgreSQL có cú pháp riêng **DISTINCT ON**, thường rất gọn để giữ **hàng đứng đầu mỗi nhóm**:

~~~sql
SELECT DISTINCT ON (region)
    region,
    sale_id,
    seller_id,
    sold_on,
    amount_vnd
FROM top_group_sales
ORDER BY
    region,
    amount_vnd DESC NULLS LAST,
    sold_on DESC,
    sale_id DESC;
~~~

Kết quả là **một hàng cho mỗi region có giao dịch**, theo đúng thứ tự đã định: sale_id **3, 8, 14, 11** tương ứng Bac, Nam, Tay, Trung.

**DISTINCT ON (region)** có ý nghĩa “sau khi xếp theo ORDER BY, giữ hàng đầu tiên của từng region”. Trong PostgreSQL, các biểu thức DISTINCT ON phải phù hợp với **phần đầu của ORDER BY**, vì thế truy vấn dùng **ORDER BY region, ...**.

Nếu cần bỏ nhóm không có số tiền xác định:

~~~sql
SELECT DISTINCT ON (region)
    region, sale_id, sold_on, amount_vnd
FROM top_group_sales
WHERE amount_vnd IS NOT NULL
ORDER BY region,
         amount_vnd DESC,
         sold_on DESC,
         sale_id DESC;
~~~

Truy vấn chỉ giữ **3, 8, 11**.

**DISTINCT ON không có nghĩa là giữ mọi đồng hạng.** Nó chỉ chọn **một hàng** của mỗi nhóm theo thứ tự; nếu thứ tự không phá hòa đầy đủ, hàng được chọn có thể không ổn định.

Đây là **cú pháp PostgreSQL**, không phải một giải pháp di động nguyên văn sang MySQL, SQL Server hay SQLite. Khi viết đa phương ngữ, **ROW_NUMBER** hoặc truy vấn con tương quan thường dễ chuyển đổi hơn.

## 12. Nhóm không có bản ghi và nhóm toàn NULL

Đến đây, chúng ta chủ yếu nhóm trực tiếp từ **top_group_sales**. Vì vậy, region **Hai dao** không xuất hiện ở GROUP BY: nó chưa có giao dịch nào để hình thành nhóm từ bảng này.

Nếu báo cáo cần hiển thị **toàn bộ khu vực đã cấu hình**, kể cả không phát sinh giao dịch, hãy bắt đầu từ bảng **top_group_regions**.

### 12.1. Hiển thị MAX của cả nhóm không có giao dịch

~~~sql
SELECT
    r.region,
    COUNT(s.sale_id) AS sale_count,
    COUNT(s.amount_vnd) AS known_amount_count,
    MAX(s.amount_vnd) AS max_amount_vnd
FROM top_group_regions AS r
LEFT JOIN top_group_sales AS s
    ON s.region = r.region
GROUP BY r.region
ORDER BY r.region;
~~~

Kết quả:

| region | sale_count | known_amount_count | max_amount_vnd |
| --- | ---: | ---: | ---: |
| Bac | 5 | 4 | 900000 |
| Hai dao | 0 | 0 | NULL |
| Nam | 4 | 4 | 750000 |
| Tay | 2 | 0 | NULL |
| Trung | 3 | 3 | 400000 |

**Hai dao** có sale_count = 0 nên chưa có giao dịch. **Tay** có sale_count = 2 nhưng known_amount_count = 0, nghĩa là **có giao dịch nhưng chưa biết số tiền**. Hai trường hợp MAX đều NULL nhưng ý nghĩa rất khác.

**COUNT(s.sale_id)** được dùng thay COUNT(*) vì LEFT JOIN tạo một hàng bổ sung có cột sales NULL cho khu vực không khớp; COUNT(*) ở nhóm Hai dao sẽ là 1, không phải số giao dịch thực.

### 12.2. Trả một hàng tiêu biểu cho mỗi khu vực bằng LEFT JOIN LATERAL

PostgreSQL hỗ trợ **LATERAL**: truy vấn con trong FROM có thể tham chiếu đến hàng từ nguồn trước nó. Kết hợp **LEFT JOIN LATERAL**, ta có thể giữ đủ năm khu vực và chọn tối đa một giao dịch:

~~~sql
SELECT
    r.region,
    s.sale_id,
    s.seller_id,
    s.sold_on,
    s.amount_vnd
FROM top_group_regions AS r
LEFT JOIN LATERAL (
    SELECT
        x.sale_id,
        x.seller_id,
        x.sold_on,
        x.amount_vnd
    FROM top_group_sales AS x
    WHERE x.region = r.region
    ORDER BY
        x.amount_vnd DESC NULLS LAST,
        x.sold_on DESC,
        x.sale_id DESC
    LIMIT 1
) AS s ON TRUE
ORDER BY r.region;
~~~

Kết quả gồm **năm hàng**:

| region | sale_id | amount_vnd | Ý nghĩa |
| --- | ---: | ---: | --- |
| Bac | 3 | 900000 | Giao dịch số tiền cao nhất, phá hòa theo ngày |
| Hai dao | NULL | NULL | Không có bất kỳ giao dịch nào |
| Nam | 8 | 750000 | Giao dịch số tiền cao nhất, phá hòa theo ngày |
| Tay | 14 | NULL | Chọn giao dịch đại diện, nhưng tiền chưa biết |
| Trung | 11 | 400000 | Giao dịch số tiền cao nhất, phá hòa theo ngày |

Vì dùng **LEFT JOIN**, khu vực Hai dao vẫn có một hàng dù truy vấn con không tìm được bản ghi. Với Tay, truy vấn con tìm được hai hàng, rồi chọn hàng đứng đầu theo ngày.

Nếu yêu cầu **chỉ nhận diện cực đại khi có tiền xác định**, thêm:

~~~sql
AND x.amount_vnd IS NOT NULL
~~~

vào điều kiện WHERE **bên trong LATERAL**. Lúc này Tay và Hai dao đều có sale_id NULL, nhưng bạn vẫn có thể dựa vào sale_count/known_amount_count từ một báo cáo kiểm soát riêng để phân biệt hai nguyên nhân.

### 12.3. Không tự coi NULL bằng NULL trong JOIN MAX

Một số người cố thay:

~~~sql
s.amount_vnd = m.max_amount_vnd
~~~

bằng phép so sánh null-safe như:

~~~sql
s.amount_vnd IS NOT DISTINCT FROM m.max_amount_vnd
~~~

Trong PostgreSQL, thay đổi này có thể làm **cả hai giao dịch Tay với amount NULL** khớp max_amount NULL. Điều đó là một **quy ước coi hai giá trị thiếu là không khác nhau**, chứ **không phải** bằng chứng các giao dịch ấy có cùng cực đại số thực.

Nếu mục tiêu là tìm “số tiền lớn nhất đã biết”, cách rõ ràng là lọc **IS NOT NULL**. Nếu mục tiêu là “lấy mọi hàng cùng mức độ thiếu thông tin ở nhóm chưa có giá trị”, hãy diễn đạt thành một yêu cầu khác và ghi chú rõ.

## 13. Bài toán "gần đây nhất mỗi nhóm" và đồng hạng thời gian

Không phải bài toán cực đại nào cũng liên quan đến tiền. Ví dụ: **giao dịch gần đây nhất trong mỗi khu vực**.

Muốn **giữ tất cả giao dịch có ngày lớn nhất**, dùng subquery tương quan:

~~~sql
SELECT
    s.region, s.sale_id, s.sold_on, s.amount_vnd
FROM top_group_sales AS s
WHERE s.sold_on = (
    SELECT MAX(x.sold_on)
    FROM top_group_sales AS x
    WHERE x.region = s.region
)
ORDER BY s.region, s.sale_id;
~~~

Với dữ liệu hiện tại:

| region | sale_id | sold_on |
| --- | ---: | --- |
| Bac | 5 | 2026-04-05 |
| Nam | 9 | 2026-04-07 |
| Tay | 14 | 2026-04-05 |
| Trung | 12 | 2026-04-10 |

Đây là **ngày mới nhất**, không phải **tiền lớn nhất**. Ở Bac, giao dịch mới nhất là 5 có tiền NULL, trong khi giao dịch tiền lớn nhất là 2 và 3.

Nếu nhiều giao dịch có cùng ngày gần nhất, truy vấn trên sẽ trả **nhiều hàng**. Muốn đúng một hàng gần nhất, dùng ROW_NUMBER:

~~~sql
WITH latest AS (
    SELECT
        s.*,
        ROW_NUMBER() OVER (
            PARTITION BY region
            ORDER BY sold_on DESC, sale_id DESC
        ) AS rn
    FROM top_group_sales AS s
)
SELECT region, sale_id, sold_on, amount_vnd
FROM latest
WHERE rn = 1
ORDER BY region;
~~~

Lúc này sale_id lớn hơn đóng vai trò **phá hòa nếu hai bản ghi cùng ngày**.

### Không ghép MAX(amount) và MAX(date) để lấy một giao dịch

Khi cần **giao dịch tiền lớn nhất, nếu cùng tiền chọn giao dịch mới nhất**, phải sắp thứ tự:

~~~sql
ORDER BY amount_vnd DESC NULLS LAST, sold_on DESC, sale_id DESC
~~~

Không phải:

~~~sql
-- Không chỉ ra được một giao dịch có cả hai cực đại độc lập.
SELECT region, MAX(amount_vnd), MAX(sold_on)
FROM top_group_sales
GROUP BY region;
~~~

Điều kiện phá hòa phải được áp dụng **trên những hàng cùng đạt tiêu chí chính**, chứ không lấy cực đại riêng rẽ ở mỗi cột rồi ghép.

## 14. Phân nhóm theo nhiều cột

Nhiều báo cáo cần tìm cực đại cho **mỗi cặp (region, sale_status)** chứ không chỉ region. Cơ chế giống nhau, nhưng mọi khóa nhóm phải được đưa vào điều kiện tương quan hoặc JOIN.

### 14.1. Truy vấn con tương quan với khóa ghép

~~~sql
SELECT
    s.region,
    s.sale_status,
    s.sale_id,
    s.amount_vnd
FROM top_group_sales AS s
WHERE s.amount_vnd = (
    SELECT MAX(x.amount_vnd)
    FROM top_group_sales AS x
    WHERE x.region = s.region
      AND x.sale_status = s.sale_status
)
ORDER BY s.region, s.sale_status, s.sale_id;
~~~

Mỗi cặp **(region, sale_status)** có MAX độc lập. Ví dụ:

- Bac/paid có số tiền cao nhất **900000**, gồm sale_id **2, 3**.
- Bac/pending có số tiền cao nhất **300000**, gồm sale_id **4**.
- Nam/paid có số tiền cao nhất **750000**, gồm sale_id **6, 8**.
- Nam/pending có số tiền cao nhất **100000**, gồm sale_id **9**.

Những nhóm có toàn tiền NULL không trả hàng từ điều kiện bằng MAX.

### 14.2. JOIN bảng MAX theo hai cột

~~~sql
WITH maxima AS (
    SELECT
        region,
        sale_status,
        MAX(amount_vnd) AS max_amount_vnd
    FROM top_group_sales
    GROUP BY region, sale_status
)
SELECT
    s.region,
    s.sale_status,
    s.sale_id,
    s.amount_vnd
FROM top_group_sales AS s
JOIN maxima AS m
    ON m.region = s.region
   AND m.sale_status = s.sale_status
   AND m.max_amount_vnd = s.amount_vnd
ORDER BY s.region, s.sale_status, s.sale_id;
~~~

Nếu chỉ ghép theo region mà bỏ **sale_status**, một hàng pending có thể bị so với MAX của nhóm paid, hoặc JOIN nhiều lần vào các nhóm trạng thái khác. **Đủ khóa nhóm** là điều kiện cần để kết quả đúng.

### 14.3. ROW_NUMBER với PARTITION BY nhiều cột

~~~sql
WITH ranked AS (
    SELECT
        s.*,
        ROW_NUMBER() OVER (
            PARTITION BY region, sale_status
            ORDER BY amount_vnd DESC NULLS LAST,
                     sold_on DESC,
                     sale_id DESC
        ) AS rn
    FROM top_group_sales AS s
)
SELECT region, sale_status, sale_id, amount_vnd
FROM ranked
WHERE rn = 1
ORDER BY region, sale_status;
~~~

Lần này kết quả là **một giao dịch cho mỗi tổ hợp region và sale_status có trong bảng**, theo thứ tự phá hòa. Nếu mục tiêu là **tất cả đồng hạng**, chuyển sang RANK theo **amount_vnd** và quyết định chính sách NULL.

## 15. Chỉ xét một tập giao dịch hợp lệ: lọc đúng trước khi tìm MAX

Giả sử phòng kinh doanh chỉ muốn tìm **giao dịch lớn nhất đã thanh toán** trong từng khu vực. Các giao dịch pending phải được loại **khỏi tập tham gia so sánh**, chứ không chỉ loại khỏi danh sách kết quả sau khi đã tính MAX.

Truy vấn con tương quan:

~~~sql
SELECT
    s.region, s.sale_id, s.amount_vnd, s.sale_status
FROM top_group_sales AS s
WHERE s.sale_status = 'paid'
  AND s.amount_vnd IS NOT NULL
  AND s.amount_vnd = (
      SELECT MAX(x.amount_vnd)
      FROM top_group_sales AS x
      WHERE x.region = s.region
        AND x.sale_status = 'paid'
  )
ORDER BY s.region, s.sale_id;
~~~

Hai điều kiện **sale_status = 'paid'** có vai trò khác nhau:

1. Ở bảng ngoài, chỉ xuất giao dịch paid.
2. Ở truy vấn con, MAX được tính **trong tập paid**, không phải toàn bộ giao dịch của khu vực.

Với bộ dữ liệu mẫu, nhóm cực đại tình cờ không thay đổi. Nhưng nếu một ngày xuất hiện giao dịch pending giá trị cao hơn mọi giao dịch paid, thiếu bộ lọc trong truy vấn con sẽ khiến **không giao dịch paid nào đạt MAX của tất cả trạng thái**, và khu vực ấy biến mất khỏi kết quả.

Một cách dễ kiểm soát là định nghĩa tập đầu vào **một lần** trong CTE:

~~~sql
WITH eligible_sales AS (
    SELECT *
    FROM top_group_sales
    WHERE sale_status = 'paid'
      AND amount_vnd IS NOT NULL
),
maxima AS (
    SELECT region, MAX(amount_vnd) AS max_amount_vnd
    FROM eligible_sales
    GROUP BY region
)
SELECT
    s.region, s.sale_id, s.amount_vnd
FROM eligible_sales AS s
JOIN maxima AS m
    ON m.region = s.region
   AND m.max_amount_vnd = s.amount_vnd
ORDER BY s.region, s.sale_id;
~~~

CTE giúp đảm bảo **đầu vào tính MAX** và **đầu vào tìm hàng chi tiết** tuân theo cùng tiêu chuẩn đủ điều kiện.

## 16. Phân biệt "top 1", "top N" và "top N với đồng hạng"

Trước khi viết SQL, hãy xác định câu hỏi muốn một trong những loại kết quả sau:

| Yêu cầu | Công cụ phù hợp | Kết quả khi hai hàng cùng cao nhất |
| --- | --- | --- |
| **Giá trị MAX** của nhóm | GROUP BY + MAX | Một giá trị số cho mỗi nhóm |
| **Mọi hàng bằng MAX** | Correlated MAX, MAX + JOIN, NOT EXISTS, RANK = 1 | Giữ **cả hai** |
| **Một hàng đại diện** của nhóm | ROW_NUMBER = 1, DISTINCT ON, subquery ORDER BY LIMIT 1 | Chọn **một** theo quy tắc phá hòa |
| **Đúng N hàng đầu** mỗi nhóm | ROW_NUMBER <= N | Tối đa N hàng, có thể cắt giữa đồng hạng |
| **Top N thứ hạng** có đồng hạng | RANK <= N | Có thể ít hoặc nhiều hơn N hàng |
| **Top N mức giá khác nhau** | DENSE_RANK <= N | Có thể nhiều hơn N hàng |

Ví dụ nếu một bảng có giá trị tiền **900, 900, 500, 300**:

- **ROW_NUMBER <= 2:** lấy đúng hai hàng đầu; cả hai có 900.
- **RANK <= 2:** cũng lấy hai hàng 900 vì hạng tiếp theo là 3.
- **DENSE_RANK <= 2:** lấy **ba hàng** gồm hai hàng 900 và một hàng 500.

Nếu muốn “top 2 mức giá” nhưng giới hạn chỉ hai hàng, hai yêu cầu đã **mâu thuẫn khi có đồng hạng**. Cần quyết định ưu tiên số hàng hay giữ đầy đủ đồng hạng.

### FETCH FIRST ... WITH TIES không tự chia theo nhóm

Một số hệ hỗ trợ cú pháp **FETCH FIRST n ROWS WITH TIES** hoặc cơ chế tương tự. Khi dùng ở truy vấn kết quả chung, nó giữ đồng hạng ở **ranh giới của ORDER BY toàn kết quả**, **không tự reset n cho từng region**.

Vì vậy, không thể thay ngay bài toán **mỗi nhóm lấy một hạng cao nhất** bằng một lệnh FETCH FIRST 1 ROW WITH TIES trên toàn bảng. Muốn hạng tính lại cho từng khu vực, dùng **PARTITION BY** hoặc truy vấn con theo nhóm.

## 17. Hiệu năng và chỉ mục

Cùng một kết quả logic có thể được tạo bằng nhiều cấu trúc SQL, nhưng kế hoạch thực thi còn phụ thuộc vào quy mô và chỉ mục.

### 17.1. Chỉ mục phục vụ việc tìm giao dịch lớn theo khu vực

Trong PostgreSQL có thể tạo:

~~~sql
CREATE INDEX idx_top_group_sales_region_amount
    ON top_group_sales (
        region,
        amount_vnd DESC NULLS LAST,
        sold_on DESC,
        sale_id DESC
    );
~~~

Ý nghĩa:

- **region** là khóa nhóm để tìm theo một khu vực.
- **amount_vnd DESC NULLS LAST** khớp ưu tiên tiền cao nhất có giá trị.
- **sold_on DESC, sale_id DESC** là các tiêu chí phá hòa khi cần một hàng.

Một truy vấn kiểu:

~~~sql
SELECT sale_id, sold_on, amount_vnd
FROM top_group_sales
WHERE region = 'Bac'
ORDER BY amount_vnd DESC NULLS LAST,
         sold_on DESC,
         sale_id DESC
LIMIT 1;
~~~

có thể được hỗ trợ tốt bởi chỉ mục ghép đó trên bảng lớn. Chỉ mục cũng có thể giúp các dạng truy vấn khác, nhưng **không có bảo đảm rằng mọi truy vấn MAX/NOT EXISTS/window đều dùng chỉ mục ấy theo cùng cách**.

Với bảng ví dụ chỉ 14 hàng, PostgreSQL có thể chọn **quét tuần tự** vì chi phí rất thấp. Điều này không chứng minh chỉ mục vô dụng; cần xem kế hoạch trên dữ liệu đại diện.

### 17.2. So sánh bằng EXPLAIN

~~~sql
EXPLAIN
SELECT s.sale_id, s.region, s.amount_vnd
FROM top_group_sales AS s
WHERE s.amount_vnd = (
    SELECT MAX(x.amount_vnd)
    FROM top_group_sales AS x
    WHERE x.region = s.region
);
~~~

Hoặc:

~~~sql
EXPLAIN
WITH maxima AS (
    SELECT region, MAX(amount_vnd) AS max_amount_vnd
    FROM top_group_sales
    GROUP BY region
)
SELECT s.sale_id, s.region, s.amount_vnd
FROM top_group_sales AS s
JOIN maxima AS m
    ON m.region = s.region
   AND m.max_amount_vnd = s.amount_vnd;
~~~

**EXPLAIN** trình bày kế hoạch dự kiến. **EXPLAIN ANALYZE** thực thi truy vấn để lấy số liệu đo đạc, nên cần thận trọng với câu lệnh có thay đổi dữ liệu hoặc truy vấn nặng trong môi trường sản xuất. Các ví dụ ở đây là SELECT thuần.

Không nên suy luận “truy vấn con tương quan luôn chậm vì chạy một lần cho mỗi hàng”. Bộ tối ưu có thể tái cấu trúc hoặc tận dụng chỉ mục; ngược lại, một truy vấn được viết gọn vẫn có thể phải xử lý rất nhiều hàng. Hãy đo đạc thay vì phỏng đoán.

### 17.3. Khi có rất nhiều nhóm nhưng mỗi nhóm ít hàng

**GROUP BY MAX + JOIN** có thể phù hợp khi cần tính một lượt MAX cho nhiều nhóm và lấy mọi hàng đạt cực đại.

**ROW_NUMBER** có thể thuận tiện khi cần một hàng cùng các cột chi tiết và thứ tự phá hòa.

**LEFT JOIN LATERAL ... LIMIT 1** có thể hữu ích khi có sẵn danh sách nhóm cần xét và chỉ muốn một hàng mỗi nhóm, đặc biệt nếu có chỉ mục hỗ trợ tìm nhanh theo khóa nhóm. Hiệu quả thực tế phụ thuộc số nhóm, độ phân bố dữ liệu và kế hoạch thực thi.

### 17.4. Đúng trước, nhanh sau

Một truy vấn rất nhanh nhưng **vô tình loại đồng hạng** hoặc **coi NULL là cực đại** vẫn là truy vấn sai. Bước đầu tiên nên là xác định kết quả mong đợi, đặc biệt với **đồng hạng, dữ liệu thiếu, nhóm rỗng và điều kiện lọc**; sau đó mới tối ưu.

## 18. Khác biệt theo phương ngữ SQL

Ý tưởng **MAX theo nhóm rồi lấy hàng chi tiết** dùng được rộng rãi, nhưng cú pháp chọn một hàng và xử lý NULL khác nhau.

| Hệ quản trị | MAX + subquery / JOIN | ROW_NUMBER, RANK | Cú pháp chọn hàng đầu | Lưu ý |
| --- | --- | --- | --- | --- |
| **PostgreSQL 15+** | Có | Có | LIMIT, FETCH; **DISTINCT ON** riêng PostgreSQL | Có **NULLS FIRST/LAST**, LATERAL |
| **MySQL 8.0** | Có | Có (window functions trong 8.0) | LIMIT | Không dùng nguyên văn DISTINCT ON; cách xử lý NULL trong ORDER BY khác |
| **SQL Server** | Có | Có | TOP, OFFSET ... FETCH | Có **CROSS/OUTER APPLY** cho truy vấn con theo nhóm |
| **SQLite 3.25+** | Có | Có window functions | LIMIT | DISTINCT ON không có; cần kiểm tra phiên bản SQLite |
| **Oracle Database** | Có | Có | FETCH FIRST ... ROWS; có các cơ chế chọn hàng đặc thù | Không sao chép nguyên cú pháp LIMIT của PostgreSQL |

### 18.1. ROW_NUMBER là lựa chọn thường dễ chuyển đổi

Một công thức khá phổ biến giữa các RDBMS hiện đại:

~~~sql
WITH ranked AS (
    SELECT
        s.*,
        ROW_NUMBER() OVER (
            PARTITION BY region
            ORDER BY amount_vnd DESC, sold_on DESC, sale_id DESC
        ) AS rn
    FROM sales AS s
)
SELECT *
FROM ranked
WHERE rn = 1;
~~~

Tuy vậy, ở đây vẫn cần quyết định **NULL trong ORDER BY**. Trong PostgreSQL, **DESC mặc định thường đặt NULL trước**, trong khi các hệ khác có thể đặt NULL theo quy tắc khác. Nếu muốn ưu tiên giá trị không NULL một cách rõ và dễ chuyển đổi, có thể sắp bằng CASE:

~~~sql
ORDER BY
    CASE WHEN amount_vnd IS NULL THEN 1 ELSE 0 END ASC,
    amount_vnd DESC,
    sold_on DESC,
    sale_id DESC
~~~

Cách này đẩy hàng amount_vnd NULL xuống sau hàng có số tiền, không dựa vào tùy chọn NULLS LAST mà một số hệ không hỗ trợ. Với phiên bản và bộ tối ưu cụ thể, cách viết này có thể tác động khả năng tận dụng chỉ mục, nên cần xem kế hoạch nếu hiệu năng là yêu cầu quan trọng.

### 18.2. SQL Server: TOP và OUTER APPLY

Nếu SQL Server cần một giao dịch đại diện cho mỗi khu vực trong bảng danh mục, có thể dùng **OUTER APPLY**:

~~~sql
-- Ví dụ SQL Server, giả định dbo.regions và dbo.sales tồn tại.
SELECT
    r.region,
    s.sale_id,
    s.sold_on,
    s.amount_vnd
FROM dbo.regions AS r
OUTER APPLY (
    SELECT TOP (1)
        x.sale_id, x.sold_on, x.amount_vnd
    FROM dbo.sales AS x
    WHERE x.region = r.region
    ORDER BY
        CASE WHEN x.amount_vnd IS NULL THEN 1 ELSE 0 END,
        x.amount_vnd DESC,
        x.sold_on DESC,
        x.sale_id DESC
) AS s;
~~~

**OUTER APPLY** có mục đích gần với **LEFT JOIN LATERAL** của PostgreSQL: giữ cả khu vực không tìm thấy giao dịch. Cú pháp và kế hoạch thực thi là của SQL Server; không chạy nguyên văn trên PostgreSQL.

### 18.3. MySQL 8.0 và SQLite: subquery hoặc cửa sổ

Ví dụ phân hạng có đồng hạng bằng RANK:

~~~sql
WITH ranked AS (
    SELECT
        s.*,
        RANK() OVER (
            PARTITION BY region
            ORDER BY amount_vnd DESC
        ) AS amount_rank
    FROM sales AS s
    WHERE amount_vnd IS NOT NULL
)
SELECT region, sale_id, amount_vnd
FROM ranked
WHERE amount_rank = 1;
~~~

Trong MySQL 8.0 và SQLite có window functions, ý tưởng có thể áp dụng với schema tương ứng. Nếu dùng SQLite cũ trước khi hỗ trợ window functions, cách **MAX tương quan**, **MAX + JOIN** hoặc **NOT EXISTS** là những phương án cần cân nhắc.

### 18.4. DISTINCT ON chỉ là tiện ích của PostgreSQL

~~~sql
SELECT DISTINCT ON (region) *
FROM top_group_sales
ORDER BY region, amount_vnd DESC NULLS LAST,
         sold_on DESC, sale_id DESC;
~~~

Đây không phải cú pháp SQL di động sang MySQL, SQL Server hay SQLite. Khi port, thường thay bằng ROW_NUMBER() với PARTITION BY và lọc rn = 1.

## 19. Những sai lầm thường gặp

| Hiểu nhầm hoặc cách viết sai | Hệ quả | Hướng xử lý |
| --- | --- | --- |
| SELECT region, sale_id, MAX(amount) GROUP BY region | Không xác định được sale_id thuộc MAX, hoặc bị hệ quản trị từ chối | Dùng subquery, JOIN hoặc cửa sổ để lấy hàng chi tiết |
| MAX(amount) và MAX(date) được coi là một bản ghi | Ghép hai cực đại độc lập, có thể tạo bản ghi tưởng tượng | Chọn hàng theo thứ tự nhiều tiêu chí |
| Bỏ điều kiện x.region = s.region trong subquery | Tìm MAX toàn bảng thay vì mỗi nhóm | Viết rõ khóa tương quan |
| JOIN bảng MAX chỉ theo amount | Ghép nhầm giữa các nhóm cùng số tiền | JOIN theo cả khóa nhóm và giá trị MAX |
| Dùng ROW_NUMBER = 1 để liệt kê **mọi đồng hạng** | Mất những hàng cùng cao nhất | Dùng RANK = 1, MAX + JOIN, hoặc tương quan MAX |
| Dùng RANK ORDER BY amount, sale_id nhưng muốn đồng hạng theo amount | sale_id duy nhất phá đồng hạng | RANK chỉ theo những tiêu chí định nghĩa đồng hạng |
| ORDER BY amount DESC LIMIT 1 không có phá hòa | Hàng được chọn khi bằng tiền có thể không ổn định | Thêm ngày và khóa chính duy nhất vào ORDER BY |
| Không xét NULL trong NOT EXISTS | Hàng có amount NULL có thể bị xem là không ai vượt qua | Lọc IS NOT NULL hoặc định nghĩa quy tắc thiếu dữ liệu |
| Coi NULL = NULL là TRUE trong JOIN MAX | Nhầm nhóm toàn NULL với cực đại thực | Xác định ý nghĩa NULL trước khi dùng so sánh null-safe |
| Quên nhóm không có giao dịch | Danh mục nhóm không xuất hiện từ GROUP BY fact | Bắt đầu từ bảng danh mục với LEFT JOIN/LATERAL |
| Dùng COUNT(*) sau LEFT JOIN để đếm fact | Nhóm rỗng có thể bị đếm thành 1 | COUNT(khóa bản ghi fact) |
| Lọc trạng thái ở ngoài nhưng MAX tính tất cả trạng thái | Không tìm đúng cực đại trong tập hợp đủ điều kiện | Lọc cùng tập nguồn, cân nhắc CTE |
| Dùng DENSE_RANK <= 2 mà mong đúng hai hàng | Có thể trả hơn hai hàng vì đồng hạng | Xác định top N hàng hay top N mức giá |
| Dùng FETCH FIRST 1 WITH TIES toàn bảng để lấy mỗi nhóm | Chỉ xử lý toàn bộ kết quả, không reset theo nhóm | Dùng PARTITION BY hoặc subquery theo khóa nhóm |
| Quên NULLS LAST khi sắp DESC trên PostgreSQL | NULL có thể được ưu tiên hơn số tiền đã biết | Viết NULLS LAST hoặc CASE xử lý NULL |
| Dùng DISTINCT tùy ý để loại hàng cùng MAX | Che mất giao dịch đồng hạng có thật | Giữ mọi hàng hoặc chọn đại diện có quy tắc |
| Nhầm tối ưu hóa với tính đúng | Truy vấn nhanh nhưng trả sai tập hàng | Xác định nghiệp vụ/NULL/đồng hạng trước, rồi EXPLAIN |

## 20. Bài tập thực hành

Sử dụng **top_group_sales** và **top_group_regions** ở phần 2, chạy trên PostgreSQL.

1. Tính MAX(amount_vnd) theo region. Vì sao Tay có MAX = NULL? Vì sao Hai dao không xuất hiện trong GROUP BY trên sales?
2. Dùng **truy vấn con tương quan** lấy mọi giao dịch có amount_vnd bằng MAX của region. Ghi lại sáu sale_id được chọn.
3. Viết lại bài 2 bằng **CTE MAX theo nhóm + JOIN**. Giải thích tại sao cần ghép cả region và amount_vnd.
4. Viết bài 2 bằng **NOT EXISTS**: không có giao dịch cùng khu vực có số tiền lớn hơn. Thêm điều kiện xử lý NULL đúng.
5. Xóa điều kiện s.amount_vnd IS NOT NULL trong truy vấn NOT EXISTS ở bài 4. Dự đoán vì sao giao dịch tiền NULL có thể bị coi nhầm là cực đại.
6. Viết ROW_NUMBER() OVER (PARTITION BY region ORDER BY amount_vnd DESC NULLS LAST, sold_on DESC, sale_id DESC). Chọn rn = 1 và giải thích vì sao các giao dịch **3, 8, 11, 14** được chọn.
7. Dùng RANK theo **amount_vnd DESC** (chỉ xét tiền không NULL) rồi lọc rank = 1. So sánh số hàng với ROW_NUMBER.
8. Tạo bảng xếp hạng cho Bac gồm ROW_NUMBER, RANK và DENSE_RANK. Giải thích dãy **1,2,3,4**, **1,1,3,4**, **1,1,2,3**.
9. Dùng DENSE_RANK <= 2 lấy hai **mức giá khác nhau** cao nhất mỗi khu vực; so sánh với ROW_NUMBER <= 2.
10. Thêm sale_id vào ORDER BY của RANK rồi lọc rank = 1. Vì sao số hàng đồng hạng giảm?
11. Dùng **DISTINCT ON (region)** của PostgreSQL chọn một giao dịch mỗi khu vực. Thêm ORDER BY để kết quả xác định.
12. Dùng LEFT JOIN từ **top_group_regions** sang sales, đếm **COUNT(sale_id)**, **COUNT(amount_vnd)** và tính MAX. Phân biệt Tay và Hai dao.
13. Dùng **LEFT JOIN LATERAL ... ORDER BY ... LIMIT 1** để hiện cả năm khu vực, kể cả Hai dao; giải thích cột sale_id NULL.
14. Viết truy vấn lấy **giao dịch có sold_on lớn nhất** của mỗi region. So sánh kết quả với giao dịch có amount_vnd lớn nhất.
15. Dùng MAX tương quan với **hai khóa nhóm (region, sale_status)**. Tại sao cần cả hai điều kiện tương quan?
16. Tạo một giao dịch **pending** số tiền rất lớn trong một region thực hành riêng, rồi chứng minh yêu cầu “MAX của giao dịch paid” cần lọc paid **bên trong tập tính MAX**.
17. Viết truy vấn chỉ chọn một hàng trong nhóm có amount_vnd xác định; nếu cả nhóm toàn NULL thì không trả giao dịch đại diện.
18. Tạo chỉ mục (region, amount_vnd DESC NULLS LAST, sold_on DESC, sale_id DESC) và dùng EXPLAIN cho một truy vấn top 1.
19. Chuyển truy vấn DISTINCT ON sang dạng ROW_NUMBER để có thể dùng ở một hệ SQL khác.
20. Viết cách chọn một hàng mỗi nhóm trên SQL Server với ROW_NUMBER hoặc OUTER APPLY + TOP (1).

### Tự kiểm tra

**Câu 1:** MAX(amount_vnd) theo khu vực có tự trả về sale_id của hàng đạt MAX không?

**Đáp án:** **Không.** MAX trả một giá trị tổng hợp; muốn lấy sale_id và các cột khác phải tìm lại hàng bằng subquery/JOIN, hoặc xếp hạng chi tiết.

**Câu 2:** Bac có hai giao dịch cùng 900.000. Truy vấn s.amount_vnd = MAX của Bac trả mấy hàng?

**Đáp án:** **Hai hàng**: sale_id 2 và 3.

**Câu 3:** ROW_NUMBER = 1 có phù hợp để liệt kê tất cả đồng hạng lớn nhất không?

**Đáp án:** **Không.** Nó chỉ giữ một hàng mỗi nhóm. Dùng RANK = 1 khi muốn mọi hàng cùng đạt tiêu chí xếp hạng.

**Câu 4:** Nếu chỉ ORDER BY amount_vnd DESC rồi LIMIT 1, kết quả khi đồng hạng có chắc chắn là một sale_id cụ thể không?

**Đáp án:** **Không.** Cần quy tắc phá hòa, lý tưởng đến một cột duy nhất như sale_id.

**Câu 5:** Vì sao NOT EXISTS cần xử lý s.amount_vnd NULL?

**Đáp án:** Vì không có phép so sánh x.amount_vnd > NULL nào trả TRUE; nếu không chặn, một hàng NULL có thể vượt qua NOT EXISTS dù chưa có số tiền xác định.

**Câu 6:** Vì sao Tay và Hai dao đều có MAX NULL nhưng không có cùng ý nghĩa?

**Đáp án:** Tay **có hai giao dịch nhưng thiếu số tiền**; Hai dao **không có giao dịch**. COUNT(sale_id) và COUNT(amount_vnd) giúp phân biệt.

**Câu 7:** Trong bài toán hai mức giá cao nhất, RANK và DENSE_RANK có luôn cùng kết quả không?

**Đáp án:** **Không.** Khi có đồng hạng ở mức giá đầu, RANK có khoảng nhảy còn DENSE_RANK không, nên DENSE_RANK <= 2 có thể bao gồm thêm mức giá thứ hai.

## 21. Ghi nhớ cốt lõi

**Tìm giá trị lớn nhất mỗi nhóm** chưa đồng nghĩa với **tìm hàng chứa giá trị lớn nhất**. Muốn lấy mọi hàng cực đại, có thể dùng **truy vấn con tương quan với MAX**, **GROUP BY MAX rồi JOIN trở lại bảng**, hoặc **NOT EXISTS** để chọn những hàng không bị vượt qua. Những phương pháp này đều có thể trả **nhiều hàng trong một nhóm khi đồng hạng**.

Nếu yêu cầu **đúng một hàng mỗi nhóm**, cần nêu quy tắc phá hòa, chẳng hạn **tiền lớn nhất → ngày mới nhất → sale_id lớn nhất**, rồi dùng **ROW_NUMBER = 1**, **DISTINCT ON** của PostgreSQL hoặc truy vấn con **ORDER BY ... LIMIT 1**. Nếu muốn **giữ mọi đồng hạng**, dùng **RANK = 1** theo đúng tiêu chí được coi là bằng hạng.

Luôn xử lý rõ **NULL**, **nhóm toàn NULL**, **nhóm không có hàng**, **khóa ghép nhiều cột** và **bộ lọc xác định tập đủ điều kiện**. Cuối cùng, xác minh hiệu năng theo hệ quản trị thực tế bằng chỉ mục và kế hoạch thực thi, nhưng **không đánh đổi tính đúng của kết quả lấy cú pháp ngắn hoặc tốc độ chưa được kiểm chứng**.
