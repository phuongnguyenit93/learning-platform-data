# CROSS JOIN và tích Descartes có chủ đích trong SQL

Khi học kết nối bảng (*JOIN*), chúng ta thường được hướng dẫn nối những hàng có quan hệ với nhau, chẳng hạn nối đơn hàng với khách hàng qua khóa ngoại. Tuy nhiên, có những bài toán cần **kết hợp mọi hàng của tập thứ nhất với mọi hàng của tập thứ hai**, ngay cả khi hai tập không có khóa liên kết trực tiếp.

Ví dụ:

- Một cửa hàng có **2 sản phẩm**, **3 màu** và **2 cỡ**. Muốn liệt kê *toàn bộ tổ hợp sản phẩm–màu–cỡ* có thể bán, cần tạo `2 × 3 × 2 = 12` dòng.
- Một lịch trực có **5 ngày làm việc** và **3 ca mỗi ngày**, nên có `5 × 3 = 15` vị trí lịch cần phân công.
- Một danh sách báo cáo cần **mọi chi nhánh × mọi tháng**, kể cả những cặp chi nhánh–tháng chưa phát sinh giao dịch.

Trong những tình huống ấy, **`CROSS JOIN`** không phải lỗi; nó là công cụ đúng để tạo **tích Descartes (Cartesian product)** một cách có chủ đích. Ngược lại, nếu bạn vô tình kết hợp các bảng lớn mà không có điều kiện nối, số hàng có thể tăng rất mạnh và làm báo cáo sai hoặc truy vấn tốn tài nguyên.

Bài học thuộc chương **Kết nối bảng** của module **Database SQL**. Các ví dụ chạy chủ yếu trên **PostgreSQL**, sử dụng bảng tạm và dữ liệu mẫu để bạn hiểu rõ số hàng, thứ tự xử lý, giới hạn và cách kết hợp CROSS JOIN với những loại JOIN khác.

## 1. CROSS JOIN là gì?

Giả sử có hai tập:

~~~text
Tập A:  Sản phẩm P1, P2
Tập B:  Màu Đỏ, Xanh, Đen
~~~

Tích Descartes của hai tập là tất cả các cặp có thể tạo ra:

~~~text
(P1, Đỏ)    (P1, Xanh)    (P1, Đen)
(P2, Đỏ)    (P2, Xanh)    (P2, Đen)
~~~

Một cách viết SQL:

~~~sql
SELECT
    p.ten AS san_pham,
    m.ten AS mau
FROM san_pham AS p
CROSS JOIN mau AS m;
~~~

Ở đây `san_pham` và `mau` chỉ là tên minh họa; phần 3 sẽ tạo các bảng mẫu với tiền tố `xj_`.

**Ngữ nghĩa:** với **mỗi hàng của bảng bên trái**, kết hợp với **từng hàng của bảng bên phải**. Không cần có khóa ngoại hay điều kiện `ON`.

### 1.1. Công thức số hàng

Nếu tập A có \(n\) hàng và tập B có \(m\) hàng thì:

\[
|A \times B| = n \times m
\]

Ví dụ:

| Số hàng A | Số hàng B | Kết quả CROSS JOIN |
|---:|---:|---:|
| 2 | 3 | 6 |
| 5 | 3 | 15 |
| 1 | 100 | 100 |
| 0 | 100 | 0 |
| 1.000 | 2.000 | 2.000.000 |

Khi kết hợp ba nguồn độc lập:

\[
|A \times B \times C| = |A| \times |B| \times |C|
\]

Nếu có 2 sản phẩm × 3 màu × 2 cỡ, kết quả có **12 hàng**. Nếu bất kỳ nguồn nào có 0 hàng, kết quả CROSS JOIN cũng có **0 hàng**.

Công thức này đếm số hàng của tập kết quả **trước khi áp dụng các điều kiện lọc tiếp theo** và trước khi một số phép xử lý như `DISTINCT`, `GROUP BY` hay `LIMIT` làm thay đổi số hàng trả về.

### 1.2. CROSS JOIN không có điều kiện ON

Cú pháp thông thường:

~~~sql
SELECT ...
FROM bang_a AS a
CROSS JOIN bang_b AS b;
~~~

Không viết:

~~~sql
-- Cú pháp không phù hợp cho CROSS JOIN thông thường:
SELECT ...
FROM bang_a AS a
CROSS JOIN bang_b AS b ON a.id = b.a_id;
~~~

Nếu cần điều kiện nối xác định những hàng nào liên quan, thường dùng `INNER JOIN ... ON ...` hoặc `LEFT JOIN ... ON ...`. Nếu thực sự muốn tạo mọi tổ hợp trước rồi lọc ở `WHERE`, việc đó có thể làm được về mặt ngữ nghĩa; nhưng cần hiểu kết quả và chi phí, thay vì cố đặt `ON` sau `CROSS JOIN`.

### 1.3. Tích Descartes là một phép toán logic

CROSS JOIN tạo **tập kết quả logic** với mọi tổ hợp. Nó không nhất thiết bắt DBMS xây dựng và lưu vật lý một bảng trung gian chứa toàn bộ các cặp trước khi tiếp tục. Bộ tối ưu có thể thay đổi kế hoạch thực thi, đẩy điều kiện lọc và tránh tính những phần không cần thiết khi ngữ nghĩa cho phép.

Tuy nhiên, **nguy cơ bùng nổ số hàng vẫn có thật**. Đừng dựa vào tối ưu hóa để biện minh cho việc CROSS JOIN các bảng khổng lồ mà không có mục đích rõ ràng.

## 2. CROSS JOIN khác INNER JOIN và LEFT JOIN thế nào?

| Loại JOIN | Tiêu chí ghép hàng | Khi không có hàng khớp | Ví dụ mục đích |
|---|---|---|---|
| `CROSS JOIN` | Không cần điều kiện: mọi tổ hợp | Nếu một nguồn rỗng, không có tổ hợp | Sản phẩm × màu × cỡ |
| `INNER JOIN ... ON` | Chỉ những cặp thỏa điều kiện | Loại hàng không có cặp khớp | Đơn hàng có khách hàng hợp lệ |
| `LEFT JOIN ... ON` | Giữ mọi hàng bên trái, thêm hàng phải nếu khớp | Bên phải có các cột NULL | Hiển thị khách hàng chưa có đơn |
| `FULL OUTER JOIN ... ON` | Giữ hàng không khớp ở cả hai bên (DBMS hỗ trợ) | Phía không có dữ liệu là NULL | Đối chiếu hai tập dữ liệu |

Ví dụ, nếu một sản phẩm chỉ đang được bán với màu Đỏ, `INNER JOIN` vào bảng biến thể có sẵn có thể chỉ trả màu Đỏ. `CROSS JOIN` với danh sách màu trả **mọi màu** theo danh mục, kể cả màu chưa được bán.

Vì vậy, hai câu hỏi khác nhau:

1. **“Có những tổ hợp đã được khai báo?”** → thường JOIN bảng biến thể thực tế.
2. **“Có thể xét những tổ hợp nào từ các tập danh mục?”** → CROSS JOIN các tập danh mục, sau đó so sánh với biến thể thực tế nếu cần.

### 2.1. INNER JOIN ON TRUE và cú pháp dấu phẩy

Về ngữ nghĩa tổ hợp:

~~~sql
FROM bang_a AS a
CROSS JOIN bang_b AS b
~~~

thường tương đương:

~~~sql
FROM bang_a AS a
INNER JOIN bang_b AS b
    ON TRUE
~~~

Và cú pháp SQL cũ:

~~~sql
FROM bang_a AS a, bang_b AS b
~~~

cũng thường cho tích Descartes. Tuy nhiên, **`CROSS JOIN` tường minh dễ đọc hơn** vì cho biết bạn thật sự muốn mọi cặp hàng. Cú pháp dấu phẩy còn có những quy tắc ưu tiên/khả năng tham chiếu tên khác khi trộn với `JOIN ... ON`; trong mã hiện đại nên tránh dùng dấu phẩy để tạo quan hệ phức tạp.

## 3. Tạo dữ liệu thực hành tự chứa

Hãy thực hành trong **database PostgreSQL thử nghiệm**. Các bảng dưới đây đều là `TEMP TABLE`, chỉ dùng trong phiên kết nối hiện tại. Nếu trình quản lý SQL mở kết nối mới, bạn cần tạo lại dữ liệu mẫu trong kết nối đó.

### 3.1. Tạo ba danh mục độc lập

~~~sql
CREATE TEMP TABLE xj_san_pham (
    id INTEGER PRIMARY KEY,
    ten VARCHAR(100) NOT NULL
);

CREATE TEMP TABLE xj_mau (
    id INTEGER PRIMARY KEY,
    ten VARCHAR(30) NOT NULL
);

CREATE TEMP TABLE xj_co (
    ma_co VARCHAR(5) PRIMARY KEY,
    thu_tu INTEGER NOT NULL
);

INSERT INTO xj_san_pham (id, ten) VALUES
    (1, 'Áo thun'),
    (2, 'Áo khoác');

INSERT INTO xj_mau (id, ten) VALUES
    (10, 'Đỏ'),
    (20, 'Xanh'),
    (30, 'Đen');

INSERT INTO xj_co (ma_co, thu_tu) VALUES
    ('S', 1),
    ('M', 2);
~~~

Ba bảng có:

| Bảng | Số hàng | Giá trị |
|---|---:|---|
| `xj_san_pham` | 2 | Áo thun, Áo khoác |
| `xj_mau` | 3 | Đỏ, Xanh, Đen |
| `xj_co` | 2 | S, M |

Ba bảng này là các **tập danh mục độc lập**. Chúng không có khóa ngoại giữa nhau, vì không lưu quan hệ “một màu thuộc một sản phẩm” hay “một cỡ thuộc một màu”.

### 3.2. Một bảng biến thể đã khai báo

Ta còn cần dữ liệu thực tế để sau này tìm **tổ hợp chưa được tạo**:

~~~sql
CREATE TEMP TABLE xj_bien_the (
    san_pham_id INTEGER NOT NULL
        REFERENCES xj_san_pham(id),
    mau_id INTEGER NOT NULL
        REFERENCES xj_mau(id),
    ma_co VARCHAR(5) NOT NULL
        REFERENCES xj_co(ma_co),
    ton_kho INTEGER NOT NULL CHECK (ton_kho >= 0),
    PRIMARY KEY (san_pham_id, mau_id, ma_co)
);

INSERT INTO xj_bien_the
    (san_pham_id, mau_id, ma_co, ton_kho)
VALUES
    (1, 10, 'S', 5),
    (1, 10, 'M', 2),
    (1, 20, 'M', 0),
    (2, 20, 'S', 3),
    (2, 30, 'M', 7);
~~~

Bảng biến thể có **5 hàng** trong tổng **12 tổ hợp lý thuyết**. Trong đó:

- Có **4 tổ hợp đã khai báo và tồn kho dương**.
- Có **1 tổ hợp đã khai báo nhưng tồn kho bằng 0**: Áo thun, Xanh, M.
- Có **7 tổ hợp chưa được khai báo**.

Ba trạng thái “chưa tạo”, “đã tạo nhưng hết hàng” và “đã tạo còn hàng” **không giống nhau**. Chúng ta sẽ dùng CROSS JOIN với LEFT JOIN để phân biệt ở phần 7.

## 4. CROSS JOIN hai danh mục: sản phẩm × màu

~~~sql
SELECT
    sp.id AS san_pham_id,
    sp.ten AS san_pham,
    m.id AS mau_id,
    m.ten AS mau
FROM xj_san_pham AS sp
CROSS JOIN xj_mau AS m
ORDER BY sp.id, m.id;
~~~

Kết quả:

| san_pham_id | san_pham | mau_id | mau |
|---:|---|---:|---|
| 1 | Áo thun | 10 | Đỏ |
| 1 | Áo thun | 20 | Xanh |
| 1 | Áo thun | 30 | Đen |
| 2 | Áo khoác | 10 | Đỏ |
| 2 | Áo khoác | 20 | Xanh |
| 2 | Áo khoác | 30 | Đen |

Vì có 2 sản phẩm và 3 màu:

\[
2 \times 3 = 6
\]

**Mỗi sản phẩm xuất hiện ba lần**, mỗi lần kết hợp với một màu khác nhau. Đây là hành vi đúng, không phải dữ liệu bị nhân đôi do lỗi, miễn là mục tiêu của bạn thực sự là tạo mọi cặp sản phẩm–màu.

### 4.1. CROSS JOIN không tự bảo đảm thứ tự dòng

Nếu bỏ `ORDER BY`, hệ quản trị SQL **không cam kết** kết quả hiển thị theo thứ tự sản phẩm rồi màu, ngay cả khi bạn thấy nó tình cờ như vậy trong vài lần chạy.

Muốn kiểm tra từng cặp dễ dàng, hãy luôn sắp xếp rõ:

~~~sql
ORDER BY sp.id, m.id
~~~

CROSS JOIN quyết định **những cặp hàng nào xuất hiện**; ORDER BY quyết định **thứ tự trình bày**.

### 4.2. Số hàng không phụ thuộc vào giá trị có giống nhau hay không

Giả sử hai màu khác nhau vô tình cùng tên hiển thị “Xanh” nhưng có hai ID khác nhau. CROSS JOIN vẫn tạo một cặp cho **mỗi hàng danh mục**. SQL xử lý bảng theo ngữ nghĩa nhiều tập (*bag semantics*), nên hàng trùng giá trị trình bày không tự biến mất.

Nếu kết quả có những hàng giống nhau trên các cột SELECT, `DISTINCT` có thể loại trùng kết quả, nhưng đó là một phép xử lý khác và không nên dùng để che giấu dữ liệu danh mục sai hoặc JOIN thiếu điều kiện.

## 5. CROSS JOIN nhiều danh mục: sản phẩm × màu × cỡ

~~~sql
SELECT
    sp.id AS san_pham_id,
    sp.ten AS san_pham,
    m.id AS mau_id,
    m.ten AS mau,
    c.ma_co
FROM xj_san_pham AS sp
CROSS JOIN xj_mau AS m
CROSS JOIN xj_co AS c
ORDER BY sp.id, m.id, c.thu_tu;
~~~

Kết quả đầy đủ gồm **12 dòng**:

| STT | Sản phẩm | Màu | Cỡ |
|---:|---|---|---|
| 1 | Áo thun | Đỏ | S |
| 2 | Áo thun | Đỏ | M |
| 3 | Áo thun | Xanh | S |
| 4 | Áo thun | Xanh | M |
| 5 | Áo thun | Đen | S |
| 6 | Áo thun | Đen | M |
| 7 | Áo khoác | Đỏ | S |
| 8 | Áo khoác | Đỏ | M |
| 9 | Áo khoác | Xanh | S |
| 10 | Áo khoác | Xanh | M |
| 11 | Áo khoác | Đen | S |
| 12 | Áo khoác | Đen | M |

Số hàng là:

\[
2\ \text{sản phẩm} \times 3\ \text{màu} \times 2\ \text{cỡ} = 12
\]

Có thể kiểm tra bằng truy vấn đếm:

~~~sql
SELECT COUNT(*) AS so_to_hop
FROM xj_san_pham AS sp
CROSS JOIN xj_mau AS m
CROSS JOIN xj_co AS c;
~~~

Kết quả: `12`.

### 5.1. Khi nào tạo toàn bộ tổ hợp là hợp lý?

CROSS JOIN này phù hợp nếu mục tiêu là:

- Thiết kế **ma trận khả năng** để người quản lý chọn biến thể cần bán.
- Xác định **những biến thể chưa được khai báo** so với danh mục.
- Sinh danh sách kiểm tra để biết có tổ hợp nào cần cấu hình tồn kho, giá hoặc hình ảnh.
- Chuẩn bị tập dữ liệu ứng viên trước khi áp dụng quy tắc nghiệp vụ cụ thể.

Nhưng không phải mọi sản phẩm đều luôn có đủ mọi màu/cỡ trong thực tế. Nếu một dòng kết quả nghĩa là “biến thể được phép bán”, bạn còn cần kiểm tra **ràng buộc khả dụng** giữa sản phẩm và màu/cỡ, thay vì coi tất cả cặp là hàng hóa thực có.

**Tích Descartes chỉ tạo các ứng viên kết hợp, không tự chứng minh các tổ hợp đó hợp lệ về nghiệp vụ.**

## 6. Lọc kết quả CROSS JOIN khi chỉ cần một phần tổ hợp

Giả sử bạn chỉ muốn các tổ hợp của **Áo thun** và cỡ **M**:

~~~sql
SELECT
    sp.ten AS san_pham,
    m.ten AS mau,
    c.ma_co
FROM xj_san_pham AS sp
CROSS JOIN xj_mau AS m
CROSS JOIN xj_co AS c
WHERE sp.id = 1
  AND c.ma_co = 'M'
ORDER BY m.id;
~~~

Kết quả:

| san_pham | mau | ma_co |
|---|---|---|
| Áo thun | Đỏ | M |
| Áo thun | Xanh | M |
| Áo thun | Đen | M |

Có 1 sản phẩm × 3 màu × 1 cỡ = **3 hàng** sau khi lọc.

### 6.1. WHERE lọc các tổ hợp đã được xác định về logic

Cách hiểu logic:

1. Xác định nguồn tổ hợp từ các danh mục.
2. Chỉ giữ tổ hợp thỏa `sp.id = 1` và `c.ma_co = 'M'`.
3. Trả những cột được chọn và sắp xếp theo màu.

Bộ tối ưu có thể đẩy điều kiện lọc gần nguồn, nên không nhất thiết tạo vật lý cả 12 tổ hợp rồi mới bỏ 9 tổ hợp. Tuy nhiên, kết quả **có ý nghĩa tương đương** với việc xét tập tổ hợp và áp dụng điều kiện.

### 6.2. Lọc trước nguồn khi phạm vi đã biết

Để diễn đạt rõ tập nhỏ ngay từ đầu, bạn cũng có thể dùng bảng dẫn xuất:

~~~sql
SELECT
    sp.ten AS san_pham,
    m.ten AS mau,
    c.ma_co
FROM (
    SELECT id, ten
    FROM xj_san_pham
    WHERE id = 1
) AS sp
CROSS JOIN xj_mau AS m
CROSS JOIN (
    SELECT ma_co, thu_tu
    FROM xj_co
    WHERE ma_co = 'M'
) AS c
ORDER BY m.id;
~~~

Trong ví dụ nhỏ này, hai truy vấn trả cùng dữ liệu. Với tập lớn và các quy tắc phức tạp, việc thể hiện **phạm vi đầu vào** rõ ràng giúp người đọc dễ kiểm soát số tổ hợp dự kiến.

Không nên kết luận bảng dẫn xuất luôn nhanh hơn WHERE trực tiếp; hiệu năng tùy bộ tối ưu và kế hoạch thực thi.

## 7. CROSS JOIN + LEFT JOIN để tìm tổ hợp còn thiếu

Đây là một ứng dụng rất thực tế của tích Descartes có chủ đích:

> Tạo **toàn bộ tổ hợp kỳ vọng** rồi so sánh với **những tổ hợp đã được khai báo**.

Ta có:

- 12 tổ hợp kỳ vọng từ sản phẩm × màu × cỡ.
- 5 hàng biến thể đã được khai báo trong `xj_bien_the`.

### 7.1. Ghép mọi tổ hợp với dữ liệu thực tế

~~~sql
SELECT
    sp.ten AS san_pham,
    m.ten AS mau,
    c.ma_co,
    bt.ton_kho
FROM xj_san_pham AS sp
CROSS JOIN xj_mau AS m
CROSS JOIN xj_co AS c
LEFT JOIN xj_bien_the AS bt
    ON bt.san_pham_id = sp.id
   AND bt.mau_id = m.id
   AND bt.ma_co = c.ma_co
ORDER BY sp.id, m.id, c.thu_tu;
~~~

Phía trái của LEFT JOIN là **toàn bộ 12 tổ hợp**. Phía phải cung cấp số lượng tồn kho nếu đã có biến thể phù hợp. Những tổ hợp chưa có trong `xj_bien_the` sẽ hiện `ton_kho = NULL` vì không có hàng ghép.

Ví dụ vài dòng:

| san_pham | mau | ma_co | ton_kho |
|---|---|---|---:|
| Áo thun | Đỏ | S | 5 |
| Áo thun | Đỏ | M | 2 |
| Áo thun | Xanh | S | NULL |
| Áo thun | Xanh | M | 0 |
| Áo thun | Đen | S | NULL |
| Áo khoác | Xanh | S | 3 |
| Áo khoác | Đen | M | 7 |

Ở đây, **NULL và 0 khác nhau hoàn toàn**:

- `ton_kho = NULL` sau JOIN: **chưa có hàng biến thể khớp**.
- `ton_kho = 0`: **đã khai báo biến thể**, nhưng tồn kho bằng 0.

Không nên viết `COALESCE(bt.ton_kho, 0)` rồi kết luận mọi 0 đều là “đã tạo nhưng hết hàng”, vì thao tác ấy gộp hai tình trạng khác nhau.

### 7.2. Gắn nhãn tình trạng từng tổ hợp

~~~sql
SELECT
    sp.ten AS san_pham,
    m.ten AS mau,
    c.ma_co,
    CASE
        WHEN bt.san_pham_id IS NULL
            THEN 'CHUA_TAO'
        WHEN bt.ton_kho = 0
            THEN 'HET_HANG'
        ELSE 'CON_HANG'
    END AS tinh_trang,
    bt.ton_kho
FROM xj_san_pham AS sp
CROSS JOIN xj_mau AS m
CROSS JOIN xj_co AS c
LEFT JOIN xj_bien_the AS bt
    ON bt.san_pham_id = sp.id
   AND bt.mau_id = m.id
   AND bt.ma_co = c.ma_co
ORDER BY sp.id, m.id, c.thu_tu;
~~~

Khi kiểm tra **khóa không thể NULL của bảng bên phải** như `bt.san_pham_id`, ta phân biệt được trường hợp **không tìm thấy dòng**. Bảng `xj_bien_the` có `PRIMARY KEY (san_pham_id, mau_id, ma_co)` nên mỗi tổ hợp khớp tối đa một hàng; do đó LEFT JOIN không nhân tổ hợp do dữ liệu biến thể trùng khóa.

### 7.3. Chỉ liệt kê tổ hợp chưa khai báo

~~~sql
SELECT
    sp.ten AS san_pham,
    m.ten AS mau,
    c.ma_co
FROM xj_san_pham AS sp
CROSS JOIN xj_mau AS m
CROSS JOIN xj_co AS c
LEFT JOIN xj_bien_the AS bt
    ON bt.san_pham_id = sp.id
   AND bt.mau_id = m.id
   AND bt.ma_co = c.ma_co
WHERE bt.san_pham_id IS NULL
ORDER BY sp.id, m.id, c.thu_tu;
~~~

Kết quả có **7 tổ hợp**:

| Sản phẩm | Màu | Cỡ |
|---|---|---|
| Áo thun | Xanh | S |
| Áo thun | Đen | S |
| Áo thun | Đen | M |
| Áo khoác | Đỏ | S |
| Áo khoác | Đỏ | M |
| Áo khoác | Xanh | M |
| Áo khoác | Đen | S |

Đây là mô hình **anti-join** thông qua `LEFT JOIN ... WHERE khoa_ben_phai IS NULL`. Nó hữu ích để tìm những cặp **cần có theo thiết kế** nhưng **chưa xuất hiện trong bảng dữ liệu thực tế**.

### 7.4. Đếm số tổ hợp ở từng tình trạng

~~~sql
SELECT
    COUNT(*) AS tong_to_hop,
    COUNT(bt.san_pham_id) AS da_khai_bao,
    COUNT(*) - COUNT(bt.san_pham_id) AS chua_khai_bao,
    COUNT(*) FILTER (
        WHERE bt.san_pham_id IS NOT NULL AND bt.ton_kho = 0
    ) AS het_hang,
    COUNT(*) FILTER (
        WHERE bt.san_pham_id IS NOT NULL AND bt.ton_kho > 0
    ) AS con_hang
FROM xj_san_pham AS sp
CROSS JOIN xj_mau AS m
CROSS JOIN xj_co AS c
LEFT JOIN xj_bien_the AS bt
    ON bt.san_pham_id = sp.id
   AND bt.mau_id = m.id
   AND bt.ma_co = c.ma_co;
~~~

Kết quả:

| tong_to_hop | da_khai_bao | chua_khai_bao | het_hang | con_hang |
|---:|---:|---:|---:|---:|
| 12 | 5 | 7 | 1 | 4 |

`FILTER (WHERE ...)` là cú pháp được PostgreSQL hỗ trợ. Đối với hệ quản trị không hỗ trợ FILTER, có thể dùng `SUM(CASE WHEN dieu_kien THEN 1 ELSE 0 END)` trên tập có dòng đầu vào, hoặc `COUNT(CASE WHEN dieu_kien THEN 1 END)` tùy trường hợp.

## 8. CROSS JOIN để tạo lịch ngày × ca

Bài toán khác: một nhóm cần tạo **mọi vị trí ca làm việc** trên các ngày làm việc trong một tuần. Trước tiên, tạo tập ngày và tập ca, sau đó CROSS JOIN để có tất cả cặp ngày–ca.

### 8.1. Tạo danh mục ca

~~~sql
CREATE TEMP TABLE xj_ca (
    ma_ca VARCHAR(10) PRIMARY KEY,
    ten_ca VARCHAR(30) NOT NULL,
    thu_tu INTEGER NOT NULL
);

INSERT INTO xj_ca (ma_ca, ten_ca, thu_tu) VALUES
    ('SANG', 'Buổi sáng', 1),
    ('CHIEU', 'Buổi chiều', 2),
    ('TOI', 'Buổi tối', 3);
~~~

Có **3 ca** trong danh mục.

### 8.2. PostgreSQL: sinh ngày với generate_series

PostgreSQL có hàm `generate_series` dùng để tạo dãy số hoặc mốc thời gian. Lấy tuần từ thứ Hai **16/11/2026** đến Chủ nhật **22/11/2026**:

~~~sql
SELECT g.ngay::DATE AS ngay
FROM generate_series(
    TIMESTAMP '2026-11-16 00:00:00',
    TIMESTAMP '2026-11-22 00:00:00',
    INTERVAL '1 day'
) AS g(ngay)
ORDER BY g.ngay;
~~~

Truy vấn trả **7 ngày**. Hai đầu mút được bao gồm khi bước nhảy phù hợp.

### 8.3. Tạo mọi cặp ngày × ca

~~~sql
WITH cac_ngay AS (
    SELECT g.ngay::DATE AS ngay
    FROM generate_series(
        TIMESTAMP '2026-11-16 00:00:00',
        TIMESTAMP '2026-11-22 00:00:00',
        INTERVAL '1 day'
    ) AS g(ngay)
)
SELECT
    d.ngay,
    ca.ma_ca,
    ca.ten_ca
FROM cac_ngay AS d
CROSS JOIN xj_ca AS ca
ORDER BY d.ngay, ca.thu_tu;
~~~

Số hàng:

\[
7\ \text{ngày} \times 3\ \text{ca} = 21\ \text{vị trí lịch}
\]

CROSS JOIN này **không phân công nhân viên**; nó chỉ tạo danh sách vị trí cần phân công, từ đó phần mềm có thể ghép thêm lịch đã phân công hoặc trạng thái ca.

### 8.4. Chỉ tạo ngày làm việc

Trong PostgreSQL, `EXTRACT(ISODOW FROM timestamp)` cho thứ trong tuần theo quy ước thứ Hai = 1, Chủ nhật = 7.

~~~sql
WITH ngay_lam AS (
    SELECT g.ngay::DATE AS ngay
    FROM generate_series(
        TIMESTAMP '2026-11-16 00:00:00',
        TIMESTAMP '2026-11-22 00:00:00',
        INTERVAL '1 day'
    ) AS g(ngay)
    WHERE EXTRACT(ISODOW FROM g.ngay) BETWEEN 1 AND 5
)
SELECT
    d.ngay,
    ca.ma_ca
FROM ngay_lam AS d
CROSS JOIN xj_ca AS ca
ORDER BY d.ngay, ca.thu_tu;
~~~

Tuần đã chọn có **5 ngày thứ Hai đến thứ Sáu**, mỗi ngày 3 ca, nên trả **15 dòng**.

Đây là ví dụ tổ chức tốt: **lọc tập ngày cần thiết rồi mới biểu diễn tích Descartes với tập ca**. Về ngữ nghĩa, cả tuần 21 vị trí và tuần làm việc 15 vị trí là hai phạm vi khác nhau.

Lưu ý: “ngày làm việc” ở đây chỉ được định nghĩa là thứ Hai đến thứ Sáu. Các dịp nghỉ lễ và lịch nghỉ đặc thù của tổ chức không được xử lý tự động; hệ thống thực tế cần thêm lịch ngày nghỉ.

### 8.5. Tạo lưới thiếu dữ liệu cho báo cáo

Một ví dụ tương tự là **chi nhánh × tháng**, để mọi chi nhánh đều có hàng cho mỗi tháng, kể cả tháng chưa phát sinh doanh thu.

Mẫu logic:

~~~sql
SELECT
    cn.ma_chi_nhanh,
    th.thang,
    COALESCE(dt.doanh_thu, 0) AS doanh_thu_hien_thi
FROM chi_nhanh AS cn
CROSS JOIN danh_muc_thang AS th
LEFT JOIN doanh_thu_thang AS dt
    ON dt.ma_chi_nhanh = cn.ma_chi_nhanh
   AND dt.thang = th.thang;
~~~

Các bảng trong câu này là **tên minh họa**, chưa được tạo trong bộ dữ liệu `xj_`. Mẫu phù hợp khi bạn muốn biết **lưới kết hợp đầy đủ** rồi ghép dữ liệu phát sinh.

Nên phân biệt:

- Không có hàng doanh thu tháng: `dt` không khớp và các cột bên phải là NULL.
- Có hàng doanh thu bằng 0: bản ghi thực có giá trị 0.

`COALESCE` có thể giúp hiển thị 0 nếu nghiệp vụ muốn, nhưng đừng dùng nó để xóa mất dấu vết thiếu dữ liệu trong những báo cáo cần kiểm soát chất lượng.

## 9. CROSS JOIN để tạo các cặp của cùng một tập

Một trường hợp khác là liệt kê mọi cặp có thể ghép giữa các thành viên, ví dụ tạo danh sách cặp người để xét phân công đôi.

### 9.1. Tạo tập thành viên

~~~sql
CREATE TEMP TABLE xj_thanh_vien (
    id INTEGER PRIMARY KEY,
    ho_ten VARCHAR(100) NOT NULL
);

INSERT INTO xj_thanh_vien (id, ho_ten) VALUES
    (1, 'An'),
    (2, 'Bình'),
    (3, 'Chi');
~~~

Tự CROSS JOIN bảng với chính nó:

~~~sql
SELECT
    a.id AS id_a,
    b.id AS id_b
FROM xj_thanh_vien AS a
CROSS JOIN xj_thanh_vien AS b
ORDER BY a.id, b.id;
~~~

Vì có 3 thành viên, kết quả có:

\[
3 \times 3 = 9\ \text{cặp có thứ tự}
\]

Bao gồm cả `(1,1)`, `(2,2)`, `(3,3)` — ghép mỗi người với chính mình — và cả `(1,2)` lẫn `(2,1)`.

### 9.2. Loại cặp một người với chính mình

~~~sql
SELECT
    a.ho_ten AS nguoi_a,
    b.ho_ten AS nguoi_b
FROM xj_thanh_vien AS a
CROSS JOIN xj_thanh_vien AS b
WHERE a.id <> b.id
ORDER BY a.id, b.id;
~~~

Kết quả có **6 cặp có hướng**. Ví dụ `(An, Bình)` và `(Bình, An)` là hai dòng khác nhau.

Nếu cặp người không có thứ tự (đội hai người), chỉ cần **mỗi cặp đúng một lần**:

~~~sql
SELECT
    a.ho_ten AS nguoi_1,
    b.ho_ten AS nguoi_2
FROM xj_thanh_vien AS a
CROSS JOIN xj_thanh_vien AS b
WHERE a.id < b.id
ORDER BY a.id, b.id;
~~~

Kết quả:

| nguoi_1 | nguoi_2 |
|---|---|
| An | Bình |
| An | Chi |
| Bình | Chi |

Có **3 cặp không phân biệt thứ tự**. Công thức tổng quát với \(n\) thành viên:

\[
\frac{n(n-1)}{2}
\]

Với \(n=3\), kết quả là \(3\).

### 9.3. Khi nào dùng JOIN ... ON thay vì CROSS JOIN ... WHERE?

Câu sau có cùng ý nghĩa trong bài toán cặp người:

~~~sql
SELECT
    a.ho_ten,
    b.ho_ten
FROM xj_thanh_vien AS a
JOIN xj_thanh_vien AS b
    ON a.id < b.id
ORDER BY a.id, b.id;
~~~

Nếu mục tiêu là **liệt kê mọi ứng viên rồi lọc điều kiện tạo cặp**, `CROSS JOIN ... WHERE` giúp diễn đạt ý tưởng tổ hợp. Nếu mục tiêu chính là **liên kết những cặp thỏa điều kiện**, `INNER JOIN ... ON` có thể truyền đạt ý định ngắn gọn hơn.

Không có quy tắc rằng CROSS JOIN luôn cần được ưu tiên trong mọi bài toán sinh cặp; hãy chọn cú pháp giúp người đọc hiểu rõ điều kiện và mức chi tiết kết quả.

## 10. CROSS JOIN với một bảng tham số chỉ có một hàng

Đôi khi muốn áp dụng **một giá trị cấu hình** lên tất cả dòng nguồn, có thể CROSS JOIN với một bảng dẫn xuất đúng **một hàng**.

Ví dụ tính giá minh họa sau khi cộng 10%:

~~~sql
SELECT
    sp.id,
    sp.ten,
    cfg.ty_le AS ty_le_minh_hoa
FROM xj_san_pham AS sp
CROSS JOIN (
    SELECT 0.10::NUMERIC AS ty_le
) AS cfg
ORDER BY sp.id;
~~~

Bảng dẫn xuất `cfg` có **một hàng**, nên:

\[
2\ \text{sản phẩm} \times 1\ \text{hàng cấu hình} = 2\ \text{hàng}
\]

Một ứng dụng thực tế có thể kết hợp giá tiền thật với tỷ lệ cấu hình:

~~~sql
-- Mẫu với một bảng sản phẩm có cột don_gia thực tế.
SELECT
    sp.id,
    sp.don_gia,
    sp.don_gia * (1 + cfg.ty_le) AS gia_sau_ty_le
FROM bang_san_pham_co_gia AS sp
CROSS JOIN (
    SELECT 0.10::NUMERIC AS ty_le
) AS cfg;
~~~

Bảng `bang_san_pham_co_gia` chỉ là **nguồn minh họa**, không nằm trong bộ dữ liệu đã tạo. 10% ở ví dụ là tỷ lệ giả định để học SQL, không phải chính sách thuế hoặc giá áp dụng ngoài đời.

**Cảnh báo:** nếu truy vấn tham số bất ngờ trả **2 hàng** thay vì 1, mỗi sản phẩm bị nhân đôi. Nếu trả **0 hàng**, toàn bộ kết quả trở thành 0 hàng. Khi dùng CROSS JOIN cho cấu hình, hãy bảo đảm nguồn cấu hình thật sự có đúng một hàng theo thiết kế.

### 10.1. VALUES làm nguồn dữ liệu nhỏ

Có thể tạo bảng danh mục rất nhỏ ngay trong câu SQL bằng `VALUES`:

~~~sql
SELECT
    sp.ten,
    co.ma_co
FROM xj_san_pham AS sp
CROSS JOIN (
    VALUES ('S'), ('M')
) AS co(ma_co)
ORDER BY sp.id, co.ma_co;
~~~

Kết quả có **2 × 2 = 4 hàng**. Cách này hợp lý khi tập giá trị ngắn và thuộc logic truy vấn, không cần quản lý như bảng danh mục lâu dài. Nếu tập giá trị được dùng lại thường xuyên, bảng danh mục riêng sẽ dễ quản trị hơn.

## 11. CROSS JOIN LATERAL: khi nguồn thứ hai phụ thuộc nguồn thứ nhất

**CROSS JOIN thông thường** phù hợp nhất khi hai tập độc lập. Nhưng đôi lúc bạn cần tạo một danh sách phụ cho **từng hàng của tập trước**, ví dụ mỗi nhân viên có khoảng ngày công tác khác nhau. PostgreSQL có thể dùng `LATERAL` để nguồn bên phải tham chiếu cột của nguồn bên trái.

### 11.1. Tạo danh sách ngày riêng cho từng hàng

~~~sql
WITH cong_tac AS (
    SELECT *
    FROM (
        VALUES
            (1, DATE '2026-11-16', DATE '2026-11-18'),
            (2, DATE '2026-11-17', DATE '2026-11-17')
    ) AS v(id, tu_ngay, den_ngay)
)
SELECT
    ct.id,
    g.ngay::DATE AS ngay_cong_tac
FROM cong_tac AS ct
CROSS JOIN LATERAL generate_series(
    ct.tu_ngay::TIMESTAMP,
    ct.den_ngay::TIMESTAMP,
    INTERVAL '1 day'
) AS g(ngay)
ORDER BY ct.id, g.ngay;
~~~

Kết quả:

| id | ngay_cong_tac |
|---:|---|
| 1 | 2026-11-16 |
| 1 | 2026-11-17 |
| 1 | 2026-11-18 |
| 2 | 2026-11-17 |

Người/đợt 1 có ba ngày; người/đợt 2 có một ngày. Đây **không phải** \(2 \times 3\) ngày của một tập chung, vì khoảng ngày được sinh riêng cho mỗi hàng.

### 11.2. Điều gì xảy ra nếu một hàng không sinh ra ngày?

Với `CROSS JOIN LATERAL`, nếu nguồn bên phải trả 0 hàng cho một hàng bên trái, hàng đó **không xuất hiện** trong kết quả. Nếu cần giữ hàng bên trái ngay cả khi nguồn phụ không sinh hàng nào, PostgreSQL hỗ trợ:

~~~sql
LEFT JOIN LATERAL (
    SELECT g.ngay::DATE AS ngay
    FROM generate_series(
        ct.tu_ngay::TIMESTAMP,
        ct.den_ngay::TIMESTAMP,
        INTERVAL '1 day'
    ) AS g(ngay)
) AS ds_ngay ON TRUE
~~~

Đây là **đoạn để đặt trong một FROM có alias `ct` đã được khai báo**, không phải statement SQL độc lập. `LEFT JOIN LATERAL ... ON TRUE` giữ hàng trái và để các cột của nguồn phụ là NULL khi không có hàng khớp.

`LATERAL` là khái niệm mở rộng, không cần thiết để hiểu ví dụ sản phẩm × màu × cỡ. SQL Server có cơ chế tương tự qua `CROSS APPLY` và `OUTER APPLY`; cách triển khai và cú pháp khác nhau theo DBMS.

## 12. NULL, tập rỗng và hàng trùng trong tích Descartes

### 12.1. NULL không tự ngăn một hàng tham gia

CROSS JOIN **không có điều kiện so sánh khóa**. Vì vậy, nếu một dòng của tập A có cột nullable, nó vẫn được kết hợp với từng dòng của tập B; giá trị NULL chỉ được mang theo trong cột kết quả.

Ví dụ chạy độc lập trong PostgreSQL:

~~~sql
SELECT a.ma, b.nhom
FROM (
    VALUES
        (1),
        (NULL::INTEGER)
) AS a(ma)
CROSS JOIN (
    VALUES ('X'), ('Y')
) AS b(nhom)
ORDER BY a.ma NULLS LAST, b.nhom;
~~~

Kết quả có **4 hàng**:

| ma | nhom |
|---|---|
| 1 | X |
| 1 | Y |
| NULL | X |
| NULL | Y |

Nếu đây là `INNER JOIN ... ON a.ma = b.ma`, phép so sánh NULL lại có ảnh hưởng đến khả năng khớp; CROSS JOIN **không thực hiện phép so sánh đó**, nên NULL không làm giảm số tổ hợp.

### 12.2. Một bên không có hàng → kết quả rỗng

~~~sql
SELECT
    a.id,
    b.ma
FROM xj_san_pham AS a
CROSS JOIN (
    SELECT 'X'::TEXT AS ma
    WHERE FALSE
) AS b;
~~~

Bảng dẫn xuất bên phải trả 0 dòng. Số tổ hợp bằng:

\[
2 \times 0 = 0
\]

CROSS JOIN không giữ hàng bên trái khi bên phải rỗng. Đây là khác biệt quan trọng so với một `LEFT JOIN` thích hợp.

### 12.3. Hàng trùng vẫn được nhân theo số lần xuất hiện

~~~sql
SELECT a.x, b.y
FROM (
    VALUES (1), (1)
) AS a(x)
CROSS JOIN (
    VALUES ('A'), ('B')
) AS b(y);
~~~

Có 2 hàng ở A (dù cùng giá trị x = 1) và 2 hàng ở B, nên kết quả có **4 hàng**, trong đó các cặp giá trị (1, A) và (1, B) mỗi cặp xuất hiện hai lần.

Nếu muốn loại những dòng trùng về mặt giá trị, `SELECT DISTINCT` có thể thay đổi số hàng đầu ra; nhưng trước hết cần biết liệu những hàng A giống nhau có thực sự đại diện cho **hai bản ghi nghiệp vụ khác nhau** hay không.

### 12.4. COUNT(*) khi CROSS JOIN

`COUNT(*)` trên một CROSS JOIN đếm tất cả tổ hợp trả về. Với nguồn đã được lọc, số hàng bằng tích **số hàng sau lọc** khi không có điều kiện ghép phụ.

Nếu cần biết kích thước từng nguồn trước khi chạy:

~~~sql
SELECT
    (SELECT COUNT(*) FROM xj_san_pham) AS so_san_pham,
    (SELECT COUNT(*) FROM xj_mau) AS so_mau,
    (SELECT COUNT(*) FROM xj_co) AS so_co;
~~~

Kết quả: `2, 3, 2`. Bạn có thể tính \(2 \times 3 \times 2 = 12\) để ước lượng kích thước tổ hợp, mà không cần in toàn bộ danh sách.

## 13. CROSS JOIN vô tình: lỗi thiếu điều kiện nối

Đây là trường hợp nguy hiểm nhất khi học JOIN. Một lập trình viên định nối đơn hàng với khách hàng qua ID nhưng vô tình quên điều kiện:

~~~sql
-- Ví dụ SAI Ý ĐỊNH: mỗi đơn bị ghép với mọi khách hàng.
SELECT dh.id, kh.ho_ten
FROM don_hang AS dh
CROSS JOIN khach_hang AS kh;
~~~

Giả sử có **10.000 đơn** và **2.000 khách hàng**:

\[
10000 \times 2000 = 20.000.000\ \text{hàng}
\]

Khi đó mỗi đơn được gắn với **2.000 khách hàng**, hoàn toàn sai ý nghĩa “khách hàng đã đặt đơn”.

Truy vấn đúng thường là:

~~~sql
SELECT dh.id, kh.ho_ten
FROM don_hang AS dh
JOIN khach_hang AS kh
    ON kh.id = dh.khach_hang_id;
~~~

Hai bảng `don_hang` và `khach_hang` là **tên ví dụ**, chưa được tạo trong bộ dữ liệu `xj_`. Điều quan trọng là điều kiện `ON kh.id = dh.khach_hang_id` xác định quan hệ giữa hai thực thể.

### 13.1. Cú pháp dấu phẩy dễ che giấu tích Descartes

~~~sql
-- Dễ gây lỗi khi quên WHERE:
SELECT dh.id, kh.ho_ten
FROM don_hang AS dh, khach_hang AS kh;
~~~

Câu này có ngữ nghĩa tích Descartes. Trong các câu SQL cũ, có thể thấy:

~~~sql
SELECT dh.id, kh.ho_ten
FROM don_hang AS dh, khach_hang AS kh
WHERE kh.id = dh.khach_hang_id;
~~~

Nó có thể cho kết quả tương đương INNER JOIN đối với điều kiện này, nhưng ý định quan hệ **ít tường minh hơn**. Nên ưu tiên `JOIN ... ON ...` cho quan hệ khóa và `CROSS JOIN` cho tích Descartes có chủ đích.

### 13.2. INNER JOIN thiếu ON là lỗi cú pháp ở một số DBMS

Ở PostgreSQL, viết `JOIN bang_b` mà không có `ON`/`USING` theo cú pháp INNER JOIN thông thường sẽ gây lỗi cú pháp. Điều đó khác với dấu phẩy trong `FROM`, vốn có thể tạo tích Descartes dù thiếu điều kiện lọc.

Một số hệ quản trị cho phép hình thức JOIN không có điều kiện trong những ngữ cảnh nhất định. Vì vậy, quan trọng nhất là đọc rõ **mục tiêu dữ liệu** và **số hàng dự kiến**, không chỉ dựa vào việc câu SQL có chạy thành công hay không.

### 13.3. Cách nhận ra JOIN bị nhân hàng ngoài ý muốn

Dấu hiệu thường gặp:

- Số hàng tăng mạnh sau khi thêm một bảng.
- Tổng doanh thu tăng bất thường.
- Mỗi đơn xuất hiện nhiều lần cùng nhiều khách hàng khác nhau.
- `COUNT(*)` lớn hơn nhiều so với số thực thể dự kiến.
- Khóa chính của thực thể cần hiển thị lặp nhiều lần, dù bạn muốn một hàng mỗi thực thể.

Khi nghi ngờ, hãy kiểm tra từng nguồn, điều kiện nối và mức chi tiết:

~~~sql
SELECT
    COUNT(*) AS so_to_hop
FROM xj_san_pham AS sp
CROSS JOIN xj_mau AS m
CROSS JOIN xj_co AS c;
~~~

Với ví dụ đang học, `12` là đúng. Nhưng nếu bạn mong **chỉ 5 biến thể đã được khai báo**, nên đọc trực tiếp từ `xj_bien_the` hoặc JOIN các danh mục với bảng biến thể theo khóa, chứ không CROSS JOIN rồi mặc định mọi tổ hợp đều là hàng tồn kho thực tế.

## 14. Kiểm soát số hàng và hiệu năng

### 14.1. Hiệu ứng nhân của nhiều bảng

Số tổ hợp tăng theo tích kích thước các nguồn:

| Nguồn A | Nguồn B | Nguồn C | Tổng |
|---:|---:|---:|---:|
| 2 | 3 | 2 | 12 |
| 100 | 20 | 5 | 10.000 |
| 1.000 | 1.000 | 10 | 10.000.000 |
| 10.000 | 10.000 | 5 | 500.000.000 |

Một lưới 500 triệu hàng có thể tạo tải lớn khi JOIN, sắp xếp, truyền qua mạng hoặc hiển thị. Dù DBMS tối ưu việc thực thi, không nên tạo một CROSS JOIN khổng lồ chỉ để rồi giới hạn vài dòng ở cuối nếu có cách thu hẹp dữ liệu ngay từ đầu.

### 14.2. Ước lượng trước bằng COUNT

~~~sql
SELECT
    p.so_san_pham,
    m.so_mau,
    c.so_co,
    p.so_san_pham * m.so_mau * c.so_co AS so_to_hop_du_kien
FROM
    (SELECT COUNT(*) AS so_san_pham FROM xj_san_pham) AS p
CROSS JOIN
    (SELECT COUNT(*) AS so_mau FROM xj_mau) AS m
CROSS JOIN
    (SELECT COUNT(*) AS so_co FROM xj_co) AS c;
~~~

Vì mỗi bảng dẫn xuất đếm trả **một hàng**, CROSS JOIN ba kết quả đếm cũng chỉ trả **một hàng**, có số tổ hợp dự kiến là 12.

Đây là một tình huống CROSS JOIN đặc biệt hữu ích: **kết hợp nhiều chỉ số dạng một hàng** mà không cần khóa JOIN giả tạo.

### 14.3. LIMIT chỉ giới hạn kết quả, không thay thế thiết kế đúng

~~~sql
SELECT
    sp.ten,
    m.ten,
    c.ma_co
FROM xj_san_pham AS sp
CROSS JOIN xj_mau AS m
CROSS JOIN xj_co AS c
ORDER BY sp.id, m.id, c.thu_tu
LIMIT 5;
~~~

Truy vấn trả **5 hàng**, nhưng nguồn logic ban đầu có **12 tổ hợp**. Với tập lớn, `LIMIT` có thể giúp giảm số hàng gửi về, nhưng không có nghĩa cơ sở dữ liệu chắc chắn không cần xử lý phần lớn dữ liệu trước đó, nhất là khi có `ORDER BY`, tổng hợp hoặc điều kiện khác.

Nên lọc phạm vi tập đầu vào và đặt điều kiện theo nghiệp vụ trước khi kết quả trở nên quá lớn.

### 14.4. EXPLAIN để xem kế hoạch

Trên PostgreSQL:

~~~sql
EXPLAIN
SELECT
    sp.id,
    m.id,
    c.ma_co
FROM xj_san_pham AS sp
CROSS JOIN xj_mau AS m
CROSS JOIN xj_co AS c;
~~~

`EXPLAIN` hiển thị kế hoạch dự kiến. Các bước thực tế có thể sử dụng nested loop, materialize hoặc những lựa chọn khác của bộ tối ưu. Không nên đọc sơ đồ logic và khẳng định mỗi CROSS JOIN phải xuất hiện bằng một bảng trung gian vật lý.

`EXPLAIN ANALYZE` thực thi truy vấn để đo đạc, nên chỉ dùng khi hiểu ảnh hưởng của statement đang phân tích và môi trường được phép chạy.

### 14.5. Index có giúp CROSS JOIN nhanh không?

Index **không làm biến mất** số tổ hợp cần trả. Với một CROSS JOIN thuần túy tạo mọi cặp, không có điều kiện khóa để index giúp loại các cặp không cần thiết.

Index có thể hữu ích ở các bước liên quan:

- Lọc tập nguồn trước khi kết hợp.
- Ghép tổ hợp với bảng dữ liệu thực qua `LEFT JOIN ... ON`.
- Sắp xếp hoặc truy cập tập có cấu trúc phù hợp.
- Xác minh khóa duy nhất của bảng biến thể.

Trong bộ dữ liệu mẫu, `xj_bien_the` có khóa chính tổng hợp giúp tra cứu đúng cặp `(san_pham_id, mau_id, ma_co)`. Nhưng hiệu năng thực tế vẫn cần được đánh giá trên dữ liệu và kế hoạch của hệ quản trị.

## 15. Chỉ tạo tổ hợp hợp lệ về nghiệp vụ

Một CROSS JOIN sản phẩm × màu × cỡ trả **mọi ứng viên**, nhưng không phải sản phẩm nào cũng hỗ trợ mọi màu, mọi cỡ.

Giả sử một loại sản phẩm chỉ bán cỡ M; một loại khác có cả S và M. Có thể biểu diễn tập cỡ hợp lệ bằng **bảng quan hệ sản phẩm–cỡ**, rồi kết hợp với tập màu khi yêu cầu cho phép mọi màu của mỗi sản phẩm:

~~~sql
CREATE TEMP TABLE xj_co_hop_le (
    san_pham_id INTEGER NOT NULL
        REFERENCES xj_san_pham(id),
    ma_co VARCHAR(5) NOT NULL
        REFERENCES xj_co(ma_co),
    PRIMARY KEY (san_pham_id, ma_co)
);

INSERT INTO xj_co_hop_le (san_pham_id, ma_co) VALUES
    (1, 'S'),
    (1, 'M'),
    (2, 'M');
~~~

Truy vấn:

~~~sql
SELECT
    sp.ten AS san_pham,
    m.ten AS mau,
    co.ma_co
FROM xj_san_pham AS sp
JOIN xj_co_hop_le AS co
    ON co.san_pham_id = sp.id
CROSS JOIN xj_mau AS m
ORDER BY sp.id, m.id, co.ma_co;
~~~

Bảng `xj_co_hop_le` có 3 cặp sản phẩm–cỡ hợp lệ. Với 3 màu mỗi cặp, kết quả có **9 tổ hợp**, không phải 12.

Cách đọc:

1. `JOIN` xác định các **cặp sản phẩm–cỡ được phép**.
2. `CROSS JOIN xj_mau` tạo mọi màu cho mỗi cặp hợp lệ.
3. Kết quả là **các tổ hợp được phép theo hai quy tắc đã mô hình hóa**, chưa xét tồn kho thực tế.

Nếu một số màu cũng chỉ hợp lệ cho một vài sản phẩm, cần thêm bảng quan hệ hoặc điều kiện tương ứng. **CROSS JOIN không thể tự suy đoán những quy tắc này.**

## 16. Khi nào nên INSERT từ CROSS JOIN?

Có thể dùng CROSS JOIN làm nguồn cho `INSERT ... SELECT` để tạo nhiều bản ghi, ví dụ tạo các vị trí lịch hoặc khởi tạo ma trận biến thể.

Tuy nhiên, đây là thao tác **ghi dữ liệu**, khác với SELECT chỉ quan sát tổ hợp.

Ví dụ PostgreSQL, nếu bạn **cố ý** muốn khởi tạo tất cả biến thể chưa có với tồn kho 0 trong môi trường thử nghiệm:

~~~sql
-- Chỉ dùng khi chính sách nghiệp vụ thực sự yêu cầu mọi tổ hợp.
INSERT INTO xj_bien_the
    (san_pham_id, mau_id, ma_co, ton_kho)
SELECT
    sp.id,
    m.id,
    c.ma_co,
    0
FROM xj_san_pham AS sp
CROSS JOIN xj_mau AS m
CROSS JOIN xj_co AS c
ON CONFLICT (san_pham_id, mau_id, ma_co) DO NOTHING;
~~~

`ON CONFLICT ... DO NOTHING` là cú pháp PostgreSQL, dùng khóa duy nhất để bỏ qua cặp đã tồn tại. Trong bộ dữ liệu ban đầu, nếu chạy lệnh này, **7 tổ hợp còn thiếu sẽ được tạo với tồn kho 0**. Các truy vấn ở phần 7 sau đó sẽ cho kết quả khác vì không còn cặp “chưa khai báo”.

Vì vậy, **đừng chạy lệnh INSERT này trước khi làm xong các ví dụ cần phân biệt tổ hợp thiếu và tổ hợp đã có**. Trong hệ thống thật, tạo hàng loạt mọi tổ hợp có thể là quyết định nghiệp vụ sai nếu một số sản phẩm không bán đủ mọi màu/cỡ.

### 16.1. Vì sao cần kiểm soát khối lượng trước khi INSERT?

Một SELECT có 500 triệu tổ hợp có thể chỉ làm ứng dụng chậm khi đọc. Một `INSERT ... SELECT` trên cùng nguồn có thể tạo **500 triệu bản ghi**, chiếm dung lượng, tác động tới chỉ mục và giao dịch.

Trước khi dùng CROSS JOIN để ghi, cần xác định:

- Mọi tổ hợp có thật sự cần được tạo không?
- Có thể giới hạn danh mục hoặc lọc những tổ hợp hợp lệ trước không?
- Khóa duy nhất và chính sách xử lý trùng đã phù hợp chưa?
- Số lượng hàng dự kiến có được chấp nhận không?
- Có kế hoạch transaction, kiểm soát lỗi và hoàn tác ở môi trường đang dùng không?

Không dùng CROSS JOIN như một cách “lấp đầy database” chỉ vì nó tạo dữ liệu nhanh.

## 17. Những lỗi và hiểu nhầm thường gặp

| Hiểu nhầm hoặc lỗi | Vì sao sai? | Cách khắc phục |
|---|---|---|
| “CROSS JOIN luôn là JOIN sai” | Có những bài toán cần mọi tổ hợp | Dùng khi mục tiêu rõ ràng là tích Descartes |
| “CROSS JOIN tìm những bản ghi có khóa khớp” | CROSS JOIN không dùng điều kiện nối | Dùng INNER/LEFT JOIN với ON khi cần quan hệ |
| “CROSS JOIN với bảng rỗng vẫn giữ bảng trái” | Không có tổ hợp nếu một nguồn rỗng | Dùng LEFT JOIN phù hợp nếu cần giữ hàng trái |
| “NULL khiến hàng không tham gia CROSS JOIN” | Không có so sánh khóa nên hàng NULL vẫn được tổ hợp | Phân biệt với INNER JOIN có điều kiện |
| “CROSS JOIN loại các hàng trùng nhau” | SQL thường giữ hàng trùng theo bag semantics | Xem dữ liệu nguồn hoặc dùng DISTINCT khi đúng nghiệp vụ |
| “Mọi tổ hợp sản phẩm × cỡ đều bán được” | Tích Descartes chỉ tạo ứng viên | Thêm bảng/quy tắc khả dụng |
| “CROSS JOIN làm có tồn kho” | Tổ hợp chưa khai báo không phải hàng tồn kho | LEFT JOIN với biến thể thật |
| “NULL tồn kho nghĩa là hết hàng” | NULL sau LEFT JOIN có thể nghĩa là chưa có bản ghi | Kiểm tra khóa phía phải, phân biệt với ton_kho = 0 |
| “LIMIT 10 nghĩa DBMS chỉ phải tính 10 tổ hợp” | SORT/Filter/Join có thể cần xử lý nhiều hơn | Thu hẹp nguồn, xem EXPLAIN |
| “SELECT * sẽ dễ kiểm tra hơn” | Nhiều cột trùng tên, kết quả quá rộng | Chọn cột cần thiết và đặt alias |
| “Dấu phẩy trong FROM dễ đọc như JOIN tường minh” | Dễ quên điều kiện và tạo tích Descartes vô tình | Viết CROSS JOIN hoặc JOIN ... ON rõ ràng |
| “SUM sau khi CROSS JOIN vẫn giữ nguyên” | Giá trị có thể bị nhân theo số tổ hợp | Tổng hợp ở đúng cấp trước khi JOIN |
| “Thứ tự dòng do CROSS JOIN quyết định” | SQL không bảo đảm thứ tự nếu thiếu ORDER BY | Đặt ORDER BY cuối cùng |
| “Chỉ cần index là hết nguy cơ bùng nổ số hàng” | Index không thay số tổ hợp phải xuất | Ước lượng kích thước và giới hạn phạm vi |
| “CROSS JOIN các bảng lớn luôn ổn nếu truy vấn hợp lệ” | Kết quả đúng cú pháp có thể cực lớn | Xác định mục tiêu và chi phí trước khi chạy |

### 17.1. Tổng tiền bị nhân do CROSS JOIN

Giả sử có bảng doanh thu 100 dòng và bảng danh mục 12 tháng. Nếu CROSS JOIN rồi cộng số tiền trên tập kết quả mà không phân nhóm đúng, **mỗi giá trị doanh thu có thể bị lặp 12 lần**:

~~~sql
-- Mẫu SAI Ý ĐỊNH nếu muốn tổng doanh thu thực.
SELECT SUM(dt.so_tien)
FROM doanh_thu AS dt
CROSS JOIN danh_muc_thang AS th;
~~~

Bảng ở đây là **tên minh họa**; ví dụ không chạy trong bộ dữ liệu `xj_`. Tổng số tiền sẽ bị nhân với số dòng của danh mục tháng nếu mọi dòng doanh thu đều được kết hợp với mọi tháng.

Muốn báo cáo theo tháng, phải JOIN đúng điều kiện tháng hoặc tổng hợp trước khi kết hợp với lưới chi nhánh–tháng. Không nên chữa tổng bị nhân bằng `SUM(DISTINCT so_tien)`: hai giao dịch khác nhau có thể có cùng số tiền, nên DISTINCT sẽ loại nhầm dữ liệu hợp lệ.

### 17.2. CROSS JOIN và DISTINCT không thể hiện cùng ý định

CROSS JOIN trả mọi **cặp hàng**. DISTINCT chỉ loại những dòng có cùng **giá trị trên các cột được chọn**. Nếu chỉ SELECT `sp.ten` từ sản phẩm CROSS JOIN màu, bạn sẽ thấy tên sản phẩm lặp theo số màu. Nếu thêm DISTINCT, tên có thể chỉ còn mỗi sản phẩm một lần — nhưng lúc đó bạn đã **không còn quan sát các tổ hợp màu** nữa.

Khi thấy các hàng lặp, hãy hỏi trước **mỗi hàng đáng lẽ đại diện cho điều gì**.

## 18. Khác biệt cú pháp giữa các hệ quản trị

`CROSS JOIN` là cú pháp phổ biến trong SQL quan hệ. Các DBMS lớn đều có cách biểu diễn tích Descartes, nhưng những phần **sinh dãy ngày, bảng dẫn xuất, LATERAL, phân trang và thao tác INSERT khi trùng khóa** có thể khác nhau.

| Hệ quản trị | CROSS JOIN | Điều cần chú ý |
|---|---|---|
| **PostgreSQL** | `FROM a CROSS JOIN b` | Có `generate_series` cho nhiều kiểu dữ liệu, `LATERAL`, `FILTER`, `ON CONFLICT` |
| **MySQL/MariaDB** | Hỗ trợ CROSS JOIN | Hàm sinh dãy ngày và cú pháp xử lý trùng khác; cần xem phiên bản về LATERAL |
| **SQL Server** | Hỗ trợ CROSS JOIN | Có `CROSS APPLY` và `OUTER APPLY` cho nguồn phụ thuộc; dùng công cụ sinh chuỗi/ngày phù hợp phiên bản |
| **Oracle** | Hỗ trợ CROSS JOIN | Có thể dùng `CONNECT BY` hoặc cơ chế sinh dãy khác; cần chú ý cú pháp alias và các hàm ngày |
| **SQLite** | Hỗ trợ CROSS JOIN | Có thể dùng `VALUES` hoặc CTE đệ quy để sinh tập nhỏ; tính năng bảng tạm và ngày khác PostgreSQL |

### 18.1. Cú pháp hai bảng tương đối di động

~~~sql
SELECT
    a.ma,
    b.nhom
FROM bang_a AS a
CROSS JOIN bang_b AS b;
~~~

Đây là cấu trúc dễ chuyển đổi giữa nhiều hệ, miễn bảng và cột có tồn tại. Những phần nâng cao như `generate_series`, `::DATE`, `ON CONFLICT` cần được điều chỉnh theo DBMS.

### 18.2. SQL Server: tạo tổ hợp bằng VALUES

Ví dụ T-SQL với danh sách ngắn:

~~~sql
SELECT
    p.ten_san_pham,
    c.ma_co
FROM (
    VALUES
        (N'Áo thun'),
        (N'Áo khoác')
) AS p(ten_san_pham)
CROSS JOIN (
    VALUES ('S'), ('M')
) AS c(ma_co)
ORDER BY p.ten_san_pham, c.ma_co;
~~~

Kết quả có **4 tổ hợp**. Tiền tố `N` trước chuỗi Unicode là cách viết T-SQL thường dùng cho ký tự tiếng Việt. Cách tạo bảng tạm và các kiểu dữ liệu khác PostgreSQL nên không thể chạy nguyên văn toàn bộ script `CREATE TEMP TABLE` của bài trên SQL Server.

### 18.3. MySQL/MariaDB: không bắt buộc có khóa chung

~~~sql
SELECT
    p.ten_san_pham,
    c.ma_co
FROM san_pham AS p
CROSS JOIN co AS c;
~~~

Câu này tạo mọi cặp từ hai bảng danh mục. Bảng `san_pham` và `co` ở đây là tên minh họa. MySQL và MariaDB có cú pháp `CROSS JOIN`, nhưng chi tiết xử lý JOIN và các giới hạn tính năng khác có thể phụ thuộc phiên bản.

### 18.4. Oracle và SQLite

Cả Oracle và SQLite đều hỗ trợ cú pháp CROSS JOIN hai nguồn. Nhưng các ví dụ PostgreSQL có `generate_series`, `FILTER` hoặc ép kiểu `::DATE` không đương nhiên chạy nguyên vẹn ở những hệ này.

Trong Oracle, cú pháp bí danh bảng thường không dùng `AS` trước alias bảng như PostgreSQL. SQLite có cách xử lý chuỗi/ngày và kiểu dữ liệu linh hoạt khác; việc sinh lịch ngày thường cần cấu trúc phù hợp với SQLite thay vì sao chép hàm PostgreSQL.

### 18.5. Khi chuyển DBMS, kiểm tra những điểm sau

1. Tập nguồn được tạo bằng `VALUES`, bảng tạm, CTE hay bảng thật?
2. Cú pháp alias bảng hoặc bảng dẫn xuất khác nhau không?
3. Có dùng `LATERAL`, `APPLY` hoặc truy vấn phụ thuộc không?
4. Việc tạo ngày với `generate_series` có cần thay cách không?
5. Cú pháp xử lý trùng khi `INSERT ... SELECT` là gì?
6. Các kiểu dữ liệu ngày, số và xử lý NULL có khác không?
7. Kế hoạch JOIN với tập lớn và khả năng tối ưu hóa có phù hợp môi trường không?

Đừng đánh đồng **ý nghĩa tích Descartes** — rất phổ biến — với **toàn bộ cú pháp và công cụ phụ trợ** của PostgreSQL.

## 19. Bài tập thực hành có lời giải

Dùng các bảng `xj_san_pham`, `xj_mau`, `xj_co` và `xj_bien_the` đã tạo ở phần 3. Các bài chỉ đọc dữ liệu trừ khi ghi rõ; nên hoàn thành bài tập trước khi chạy ví dụ `INSERT ... SELECT` ở phần 16, vì thao tác đó làm thay đổi số biến thể chưa khai báo.

### Bài 1. Dự đoán số hàng của CROSS JOIN

**Đề bài:** Có 2 sản phẩm, 3 màu, 2 cỡ. Hỏi số hàng khi CROSS JOIN lần lượt hai nguồn và ba nguồn?

**Đáp án:**

- Sản phẩm × màu: \(2 \times 3 = 6\).
- Sản phẩm × màu × cỡ: \(2 \times 3 \times 2 = 12\).

Truy vấn kiểm tra:

~~~sql
SELECT COUNT(*) AS so_to_hop
FROM xj_san_pham AS sp
CROSS JOIN xj_mau AS m
CROSS JOIN xj_co AS c;
~~~

Kết quả: `12`.

### Bài 2. Liệt kê mọi sản phẩm × cỡ

**Yêu cầu:** không xét màu, trả tên sản phẩm và cỡ, sắp theo sản phẩm rồi thứ tự cỡ.

~~~sql
SELECT
    sp.ten,
    c.ma_co
FROM xj_san_pham AS sp
CROSS JOIN xj_co AS c
ORDER BY sp.id, c.thu_tu;
~~~

Kết quả:

| ten | ma_co |
|---|---|
| Áo thun | S |
| Áo thun | M |
| Áo khoác | S |
| Áo khoác | M |

Có \(2 \times 2 = 4\) hàng.

### Bài 3. Lọc chỉ những tổ hợp màu Đen

**Yêu cầu:** lấy tất cả sản phẩm và cỡ với màu Đen.

~~~sql
SELECT
    sp.ten AS san_pham,
    m.ten AS mau,
    c.ma_co
FROM xj_san_pham AS sp
CROSS JOIN xj_mau AS m
CROSS JOIN xj_co AS c
WHERE m.id = 30
ORDER BY sp.id, c.thu_tu;
~~~

Có **4 tổ hợp**: Áo thun–Đen–S/M và Áo khoác–Đen–S/M.

### Bài 4. Tìm những biến thể chưa khai báo

**Yêu cầu:** từ ma trận 12 tổ hợp, loại mọi tổ hợp đã có trong bảng `xj_bien_the`.

~~~sql
SELECT
    sp.ten,
    m.ten AS mau,
    c.ma_co
FROM xj_san_pham AS sp
CROSS JOIN xj_mau AS m
CROSS JOIN xj_co AS c
LEFT JOIN xj_bien_the AS bt
    ON bt.san_pham_id = sp.id
   AND bt.mau_id = m.id
   AND bt.ma_co = c.ma_co
WHERE bt.san_pham_id IS NULL
ORDER BY sp.id, m.id, c.thu_tu;
~~~

**Đáp án:** **7 tổ hợp chưa khai báo**. Nếu bạn đã chạy lệnh INSERT toàn bộ biến thể ở phần 16, kết quả bài này có thể là 0 vì dữ liệu mẫu đã bị thay đổi.

### Bài 5. Phân biệt hết hàng với chưa khai báo

**Yêu cầu:** chỉ lấy các biến thể đã khai báo có tồn kho bằng 0.

~~~sql
SELECT
    sp.ten AS san_pham,
    m.ten AS mau,
    bt.ma_co,
    bt.ton_kho
FROM xj_bien_the AS bt
JOIN xj_san_pham AS sp
    ON sp.id = bt.san_pham_id
JOIN xj_mau AS m
    ON m.id = bt.mau_id
WHERE bt.ton_kho = 0;
~~~

**Đáp án:** một dòng **Áo thun – Xanh – M – 0**. Bài này không cần CROSS JOIN vì đang hỏi **các biến thể thật đã khai báo**, không hỏi mọi tổ hợp lý thuyết.

### Bài 6. Đếm số tổ hợp theo sản phẩm

**Yêu cầu:** với mỗi sản phẩm, đếm tổng tổ hợp màu × cỡ có thể xét, số tổ hợp đã khai báo và số chưa khai báo.

~~~sql
SELECT
    sp.id,
    sp.ten,
    COUNT(*) AS tong_to_hop,
    COUNT(bt.san_pham_id) AS da_khai_bao,
    COUNT(*) - COUNT(bt.san_pham_id) AS chua_khai_bao
FROM xj_san_pham AS sp
CROSS JOIN xj_mau AS m
CROSS JOIN xj_co AS c
LEFT JOIN xj_bien_the AS bt
    ON bt.san_pham_id = sp.id
   AND bt.mau_id = m.id
   AND bt.ma_co = c.ma_co
GROUP BY sp.id, sp.ten
ORDER BY sp.id;
~~~

Kết quả:

| san_pham | tong_to_hop | da_khai_bao | chua_khai_bao |
|---|---:|---:|---:|
| Áo thun | 6 | 3 | 3 |
| Áo khoác | 6 | 2 | 4 |

Mỗi sản phẩm có 3 màu × 2 cỡ = 6 tổ hợp. Áo thun có 3 biến thể đã khai báo, Áo khoác có 2.

### Bài 7. Sinh ca cho ngày làm việc

**Yêu cầu:** từ 16/11/2026 đến 22/11/2026, chỉ lấy thứ Hai–thứ Sáu, mỗi ngày 3 ca trong bảng `xj_ca`.

~~~sql
WITH ngay_lam AS (
    SELECT g.ngay::DATE AS ngay
    FROM generate_series(
        TIMESTAMP '2026-11-16 00:00:00',
        TIMESTAMP '2026-11-22 00:00:00',
        INTERVAL '1 day'
    ) AS g(ngay)
    WHERE EXTRACT(ISODOW FROM g.ngay) BETWEEN 1 AND 5
)
SELECT
    d.ngay,
    ca.ma_ca
FROM ngay_lam AS d
CROSS JOIN xj_ca AS ca
ORDER BY d.ngay, ca.thu_tu;
~~~

**Đáp án:** **15 dòng**. Cần tạo `xj_ca` như phần 8 trước khi chạy.

### Bài 8. Mỗi cặp thành viên một lần

**Yêu cầu:** từ An, Bình, Chi, không ghép ai với chính mình và không lặp cả hai hướng.

~~~sql
SELECT
    a.ho_ten AS nguoi_1,
    b.ho_ten AS nguoi_2
FROM xj_thanh_vien AS a
CROSS JOIN xj_thanh_vien AS b
WHERE a.id < b.id
ORDER BY a.id, b.id;
~~~

**Đáp án:** ba cặp **An–Bình**, **An–Chi**, **Bình–Chi**. Cần tạo bảng `xj_thanh_vien` từ phần 9 trước khi chạy.

### Bài 9. Một nguồn rỗng sẽ tạo bao nhiêu tổ hợp?

~~~sql
SELECT COUNT(*) AS so_hang
FROM xj_san_pham AS sp
CROSS JOIN (
    SELECT id
    FROM xj_mau
    WHERE id = -1
) AS m;
~~~

Giả định không có màu ID -1, nguồn bên phải có 0 hàng, nên kết quả **0**. Một bảng trái có 2 hàng không thể tạo tổ hợp với nguồn có 0 hàng.

### Bài 10. Phát hiện JOIN sai ý định

Một lập trình viên muốn liệt kê **5 biến thể đã khai báo**, nhưng viết:

~~~sql
SELECT
    sp.ten,
    m.ten,
    c.ma_co
FROM xj_san_pham AS sp
CROSS JOIN xj_mau AS m
CROSS JOIN xj_co AS c;
~~~

Hỏi: truy vấn có đúng yêu cầu không?

**Đáp án:** Không. Nó trả **12 tổ hợp lý thuyết**, kể cả 7 tổ hợp chưa khai báo. Nếu cần 5 biến thể thật, phải đọc từ `xj_bien_the` và JOIN các danh mục theo khóa:

~~~sql
SELECT
    sp.ten AS san_pham,
    m.ten AS mau,
    bt.ma_co,
    bt.ton_kho
FROM xj_bien_the AS bt
JOIN xj_san_pham AS sp
    ON sp.id = bt.san_pham_id
JOIN xj_mau AS m
    ON m.id = bt.mau_id
ORDER BY sp.id, m.id, bt.ma_co;
~~~

CROSS JOIN không sai về cú pháp, nhưng **sai về ý nghĩa khi câu hỏi chỉ cần dữ liệu đã được khai báo**.

## 20. Checklist quyết định dùng CROSS JOIN

Khi cân nhắc viết `CROSS JOIN`, hãy tự hỏi:

1. **Bài toán có thực sự cần mọi tổ hợp không?** Hay bạn đang muốn liên kết các hàng có khóa ngoại?
2. **Mỗi nguồn đại diện cho tập gì?** Danh mục màu, cỡ, tháng, ca, tình huống kiểm thử hay bảng nghiệp vụ lớn?
3. **Số hàng của từng nguồn là bao nhiêu?** Tích các kích thước có phù hợp tài nguyên và yêu cầu hiển thị?
4. **Có nguồn nào rỗng không?** Nếu có, kết quả CROSS JOIN cũng rỗng.
5. **Có quy tắc nào loại các tổ hợp không hợp lệ không?** Hãy lọc hoặc JOIN danh mục quan hệ đúng chỗ.
6. **Có cần so sánh lưới đầy đủ với dữ liệu đã có không?** Khi đó thường dùng CROSS JOIN tạo lưới và LEFT JOIN đối chiếu.
7. **NULL và 0 mang ý nghĩa gì?** Đặc biệt khi tìm tổ hợp thiếu hoặc tổng hợp báo cáo.
8. **Kết quả có thể bị nhân khiến SUM/COUNT sai không?** Kiểm tra mức chi tiết và khóa của từng nguồn.
9. **Có đang dùng dấu phẩy trong FROM và quên điều kiện JOIN không?** Ưu tiên cú pháp tường minh.
10. **Nếu kết quả được INSERT vào bảng thật**, bạn đã xác nhận phạm vi, số hàng, khóa duy nhất và chính sách tạo tổ hợp chưa?
11. **Nếu cần thứ tự hiển thị**, bạn đã dùng ORDER BY ngoài cùng chưa?

**CROSS JOIN là phép kết hợp có chủ đích của mọi hàng từ các nguồn độc lập.** Nó đặc biệt hữu ích để tạo ma trận tổ hợp, lưới thời gian, vị trí lịch, cặp phần tử và phát hiện dữ liệu thiếu bằng cách đối chiếu với bảng thực tế. Nhưng khi mục tiêu chỉ là nối những bản ghi liên quan, hãy dùng JOIN có điều kiện phù hợp. Nắm chắc công thức số hàng và ý nghĩa của mỗi dòng kết quả sẽ giúp bạn tận dụng tích Descartes mà không tạo ra dữ liệu nhân bản hoặc truy vấn quá tải.
