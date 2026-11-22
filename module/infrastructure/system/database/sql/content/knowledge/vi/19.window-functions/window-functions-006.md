# FIRST_VALUE, LAST_VALUE và NTH_VALUE theo hệ quản trị SQL

> **Module:** Database SQL  
> **Chương:** Hàm cửa sổ  
> **Bài học:** FIRST_VALUE, LAST_VALUE và NTH_VALUE theo hệ quản trị

Các báo cáo phân tích thường cần biết **giá trị đầu tiên**, **giá trị cuối cùng** hoặc **giá trị ở vị trí thứ N** trong một nhóm dữ liệu đã được sắp xếp. Ví dụ: giá trị giao dịch đầu và cuối của mỗi khách hàng, mức lương tại thời điểm đầu kỳ, giá đóng cửa gần nhất, hay khoản thanh toán thứ ba. Đây là những bài toán phù hợp với các hàm cửa sổ **FIRST_VALUE**, **LAST_VALUE** và **NTH_VALUE**.

Điểm khó nhất thường **không phải tên hàm**, mà là xác định **thứ tự (ORDER BY)**, **phân vùng (PARTITION BY)** và đặc biệt **khung cửa sổ (window frame)**. Chỉ thiếu một mệnh đề khung, **LAST_VALUE** có thể trả giá trị của *dòng hiện tại*, dù người viết muốn giá trị cuối của *toàn bộ nhóm*. Bên cạnh đó, các hệ quản trị SQL không hỗ trợ đồng nhất hàm thứ N và cơ chế bỏ qua NULL.

---

## 1. Mục tiêu học tập

Sau khi học, bạn có thể:

- Hiểu hàm cửa sổ khác hàm tổng hợp có GROUP BY như thế nào.
- Đọc và viết cú pháp **FIRST_VALUE(expr)**, **LAST_VALUE(expr)**, **NTH_VALUE(expr, n)** cùng **OVER(...)**.
- Xác định chính xác một **partition**, thứ tự các dòng và **frame** mà hàm nhìn thấy tại mỗi dòng kết quả.
- Giải thích vì sao **FIRST_VALUE** thường “có vẻ đúng” với frame mặc định, còn **LAST_VALUE** dễ tạo kết quả bất ngờ.
- Phân biệt **ROWS**, **RANGE**, **CURRENT ROW**, **UNBOUNDED PRECEDING** và **UNBOUNDED FOLLOWING**.
- Dự đoán tác động của các dòng **đồng hạng ORDER BY (peers)** và viết tiêu chí phá hòa ổn định.
- Phân biệt thứ tự thứ N **tính từ đầu** với thứ N **tính từ cuối**, và phân biệt vị trí thứ N của khung với thứ N **khác NULL**.
- Hiểu **RESPECT NULLS** và **IGNORE NULLS** theo phương ngữ và cách mô phỏng khi DBMS không hỗ trợ.
- Biết những khác biệt chủ yếu giữa PostgreSQL, MySQL, SQL Server, Oracle, SQLite và một số hệ phân tích.
- Dùng các hàm này trong báo cáo, kiểm tra dữ liệu, truy vấn giá trị tại mốc thời gian và ứng dụng Java/JDBC.
- Tránh các lỗi thường gặp khi dùng chúng cùng **WHERE**, **GROUP BY**, **ROW_NUMBER**, **MIN/MAX** hoặc một kiểu dữ liệu thời gian.

## 2. Hàm cửa sổ khác GROUP BY thế nào?

Giả sử bảng **giao_dich** chứa nhiều giao dịch của mỗi khách. Nếu viết:

~~~sql
SELECT
    ma_khach,
    MIN(so_tien) AS so_tien_nho_nhat,
    MAX(so_tien) AS so_tien_lon_nhat
FROM giao_dich
GROUP BY ma_khach;
~~~

kết quả có **một dòng cho mỗi khách**, nhưng MIN/MAX trả **giá trị nhỏ nhất/lớn nhất**, không phải tiền của giao dịch đầu/cuối theo thời gian.

Ngược lại:

~~~sql
SELECT
    ma_khach,
    ngay_giao_dich,
    so_tien,
    FIRST_VALUE(so_tien) OVER (
        PARTITION BY ma_khach
        ORDER BY ngay_giao_dich, ma_giao_dich
        ROWS BETWEEN UNBOUNDED PRECEDING
                 AND UNBOUNDED FOLLOWING
    ) AS tien_giao_dich_dau
FROM giao_dich;
~~~

vẫn giữ **một dòng cho mỗi giao dịch**, đồng thời bổ sung **giá trị của giao dịch đầu tiên trong nhóm khách** vào mỗi dòng.

Đó là khác biệt quan trọng:

| Công cụ | Mức chi tiết đầu ra | Câu hỏi được trả lời |
|---|---|---|
| GROUP BY + MIN(so_tien) | Một dòng/khách | Số tiền nhỏ nhất của khách |
| GROUP BY + MAX(so_tien) | Một dòng/khách | Số tiền lớn nhất của khách |
| FIRST_VALUE(so_tien) OVER(...) | Giữ từng giao dịch | Số tiền ở dòng đầu theo thứ tự đã chọn |
| LAST_VALUE(so_tien) OVER(...) | Giữ từng giao dịch | Số tiền ở dòng cuối của khung đã chọn |
| NTH_VALUE(so_tien, 3) OVER(...) | Giữ từng giao dịch | Số tiền ở dòng thứ ba của khung đã chọn |

Một hàm cửa sổ **không tự gom các giao dịch thành một dòng**. Nếu muốn một dòng mỗi khách, cần bước lọc/chọn dòng ở truy vấn ngoài hoặc cách tổng hợp phù hợp.

## 3. Bộ dữ liệu dùng xuyên suốt bài

Giả sử bảng có cấu trúc:

~~~sql
CREATE TABLE giao_dich (
    ma_giao_dich INTEGER PRIMARY KEY,
    ma_khach VARCHAR(20) NOT NULL,
    ngay_giao_dich DATE NOT NULL,
    so_tien DECIMAL(12, 2)
);
~~~

Dữ liệu:

| ma_giao_dich | ma_khach | ngay_giao_dich | so_tien |
|---:|---|---|---:|
| 101 | A | 2026-01-01 | 100 |
| 102 | A | 2026-01-05 | NULL |
| 103 | A | 2026-01-05 | 300 |
| 104 | A | 2026-01-09 | 400 |
| 201 | B | 2026-02-01 | NULL |
| 202 | B | 2026-02-03 | 200 |
| 203 | B | 2026-02-10 | 300 |
| 301 | C | 2026-03-01 | 500 |

Dữ liệu cố tình có những tình huống cần quan sát:

- Khách **A** có bốn giao dịch, trong đó 102 và 103 **cùng ngày** nhưng khác mã.
- Giao dịch 102 của A có **so_tien NULL**.
- Khách **B** có giao dịch **đầu tiên là NULL**.
- Khách **C** chỉ có **một giao dịch**, nên không có dòng thứ hai hoặc thứ ba.

Các truy vấn minh họa dùng thứ tự:

~~~sql
ORDER BY ngay_giao_dich ASC, ma_giao_dich ASC
~~~

Vì **ma_giao_dich** là khóa chính, cặp ngày và mã tạo thứ tự xác định trong mỗi khách. Đây là quy tắc nghiệp vụ của ví dụ: “trước/sau” được hiểu là **ngày trước, nếu cùng ngày thì mã nhỏ trước**.

### 3.1. Nạp dữ liệu trong hệ hỗ trợ INSERT nhiều nhóm VALUES

~~~sql
INSERT INTO giao_dich
    (ma_giao_dich, ma_khach, ngay_giao_dich, so_tien)
VALUES
    (101, 'A', '2026-01-01', 100),
    (102, 'A', '2026-01-05', NULL),
    (103, 'A', '2026-01-05', 300),
    (104, 'A', '2026-01-09', 400),
    (201, 'B', '2026-02-01', NULL),
    (202, 'B', '2026-02-03', 200),
    (203, 'B', '2026-02-10', 300),
    (301, 'C', '2026-03-01', 500);
~~~

Đây là bộ dữ liệu khái niệm. Cú pháp INSERT nhiều hàng và cách chuyển literal chuỗi sang DATE khác nhau theo DBMS; Oracle 19c có thể cần INSERT ALL hoặc các INSERT riêng. Khi chạy trên hệ cụ thể, cần nạp ngày với kiểu DATE thích hợp.

## 4. Ba thành phần quyết định kết quả: partition, order và frame

Một lời gọi thường có dạng:

~~~sql
HAM_GIA_TRI(bieu_thuc) OVER (
    PARTITION BY khoa_nhom
    ORDER BY tieu_chi_thu_tu
    ROWS BETWEEN ... AND ...
)
~~~

### 4.1. PARTITION BY chia các dòng thành nhóm phân tích

~~~sql
PARTITION BY ma_khach
~~~

có nghĩa giao dịch của A được tính riêng với B và C. Trong cùng một kết quả SELECT, **partition** không làm biến mất dòng như GROUP BY.

Nếu bỏ PARTITION BY, toàn bộ các dòng có thể thuộc **một partition duy nhất**. Khi đó FIRST_VALUE có thể trả giao dịch 101 của A cho cả giao dịch khách B, không đúng yêu cầu “theo từng khách”.

Nếu cần phân tích trong từng cặp **(ma_khach, nam)**, có thể đưa cả hai biểu thức vào PARTITION BY, với cú pháp trích xuất năm phù hợp DBMS.

### 4.2. ORDER BY định nghĩa “đầu”, “cuối” và “thứ N”

~~~sql
ORDER BY ngay_giao_dich, ma_giao_dich
~~~

xác định thứ tự các giao dịch của một khách.

Với khách A, thứ tự là:

~~~text
Vị trí 1: giao dịch 101, tiền 100
Vị trí 2: giao dịch 102, tiền NULL
Vị trí 3: giao dịch 103, tiền 300
Vị trí 4: giao dịch 104, tiền 400
~~~

Nếu đảo:

~~~sql
ORDER BY ngay_giao_dich DESC, ma_giao_dich DESC
~~~

thì vị trí 1 trở thành 104 và vị trí cuối trở thành 101. Không có khái niệm “giao dịch đầu tiên” khi chưa nêu **tiêu chí sắp xếp**.

### 4.3. Window frame xác định những dòng đang được phép nhìn thấy

Trong một partition, frame là tập dòng theo quy tắc ranh giới ở **mỗi dòng hiện tại**.

Ví dụ:

~~~sql
ROWS BETWEEN UNBOUNDED PRECEDING
         AND UNBOUNDED FOLLOWING
~~~

có nghĩa **toàn bộ các dòng trong partition**, từ đầu đến cuối, ở mọi dòng hiện tại.

Còn:

~~~sql
ROWS BETWEEN UNBOUNDED PRECEDING
         AND CURRENT ROW
~~~

có nghĩa từ dòng đầu đến **dòng hiện tại**, nên frame **mở rộng dần** khi đi qua các dòng.

**Phân biệt rất quan trọng:** partition là phạm vi nhóm lớn; frame là phạm vi con mà hàm FIRST_VALUE/LAST_VALUE/NTH_VALUE đánh giá tại **dòng hiện tại**.

## 5. FIRST_VALUE: giá trị của dòng đầu tiên trong frame

Cú pháp khái niệm:

~~~sql
FIRST_VALUE(bieu_thuc) OVER (
    PARTITION BY ...
    ORDER BY ...
    ROWS BETWEEN ...
)
~~~

Hàm trả **giá trị biểu thức tại dòng đầu của frame** sau khi sắp xếp. Nó **không** trả giá trị nhỏ nhất trừ khi chính thứ tự được chọn tình cờ làm dòng đầu mang giá trị nhỏ nhất.

### 5.1. Giao dịch đầu tiên của mỗi khách

~~~sql
SELECT
    ma_giao_dich,
    ma_khach,
    ngay_giao_dich,
    so_tien,
    FIRST_VALUE(so_tien) OVER (
        PARTITION BY ma_khach
        ORDER BY ngay_giao_dich, ma_giao_dich
        ROWS BETWEEN UNBOUNDED PRECEDING
                 AND UNBOUNDED FOLLOWING
    ) AS so_tien_dau
FROM giao_dich
ORDER BY ma_khach, ngay_giao_dich, ma_giao_dich;
~~~

Kết quả:

| ma_giao_dich | ma_khach | so_tien | so_tien_dau |
|---:|---|---:|---:|
| 101 | A | 100 | 100 |
| 102 | A | NULL | 100 |
| 103 | A | 300 | 100 |
| 104 | A | 400 | 100 |
| 201 | B | NULL | NULL |
| 202 | B | 200 | NULL |
| 203 | B | 300 | NULL |
| 301 | C | 500 | 500 |

**B có so_tien_dau = NULL** vì **dòng đầu tiên** của B là giao dịch 201 có số tiền NULL. FIRST_VALUE mặc định ở nhiều DBMS **tôn trọng NULL (RESPECT NULLS)**; nó không tự tìm dòng không NULL đầu tiên.

### 5.2. FIRST_VALUE không giống MIN

Khách A có giá trị 100, NULL, 300, 400: số đầu tiên (không tính việc loại NULL) cũng là số nhỏ nhất trong mẫu, nhưng đó chỉ là sự trùng hợp.

Giả sử tiền lần lượt **400, 100, 500** theo thời gian:

- **FIRST_VALUE(so_tien) ORDER BY ngay** → 400.
- **MIN(so_tien)** → 100.

FIRST_VALUE trả giá trị ở vị trí đầu **theo thứ tự nghiệp vụ**, còn MIN so sánh giá trị của biểu thức.

### 5.3. FIRST_VALUE khi không có thứ tự duy nhất

Nếu hai dòng có cùng ngay_giao_dich, nhưng OVER chỉ ghi:

~~~sql
ORDER BY ngay_giao_dich
~~~

thì giữa các dòng đồng ngày **không có tiêu chí phân định trước/sau**. FIRST_VALUE vẫn có thể cho kết quả trực quan nếu giao dịch đầu thuộc một ngày duy nhất, nhưng trong trường hợp **hai dòng cùng thời điểm sớm nhất**, giá trị “đầu” giữa chúng có thể **không xác định**.

Nên viết:

~~~sql
ORDER BY ngay_giao_dich, ma_giao_dich
~~~

nếu mã giao dịch duy nhất và chấp nhận làm khóa phá hòa. Có thể dùng timestamp, số thứ tự sự kiện hoặc khóa nghiệp vụ khác phù hợp hơn, nhưng **không dựa vào thứ tự vật lý vô tình của bảng**.

## 6. LAST_VALUE: giá trị của dòng cuối cùng trong frame

Cú pháp:

~~~sql
LAST_VALUE(bieu_thuc) OVER (
    PARTITION BY ...
    ORDER BY ...
    ROWS BETWEEN ...
)
~~~

**LAST_VALUE không tự hiểu “cuối của toàn partition”.** Nó trả **giá trị ở dòng cuối của frame hiện tại**. Vì vậy, nó thường bị dùng sai khi frame không được nêu rõ.

### 6.1. Muốn giá trị cuối của toàn bộ khách, phải nêu full frame

~~~sql
SELECT
    ma_giao_dich,
    ma_khach,
    so_tien,
    LAST_VALUE(so_tien) OVER (
        PARTITION BY ma_khach
        ORDER BY ngay_giao_dich, ma_giao_dich
        ROWS BETWEEN UNBOUNDED PRECEDING
                 AND UNBOUNDED FOLLOWING
    ) AS so_tien_cuoi
FROM giao_dich
ORDER BY ma_khach, ngay_giao_dich, ma_giao_dich;
~~~

Kết quả:

| ma_giao_dich | ma_khach | so_tien | so_tien_cuoi |
|---:|---|---:|---:|
| 101 | A | 100 | 400 |
| 102 | A | NULL | 400 |
| 103 | A | 300 | 400 |
| 104 | A | 400 | 400 |
| 201 | B | NULL | 300 |
| 202 | B | 200 | 300 |
| 203 | B | 300 | 300 |
| 301 | C | 500 | 500 |

Dù đang hiển thị dòng 101 của khách A, **LAST_VALUE = 400** vì frame bao gồm cả giao dịch 104 nằm cuối partition.

### 6.2. Lỗi nổi tiếng: LAST_VALUE với frame mặc định

Khi có ORDER BY nhưng không ghi frame, các DBMS phổ biến thường dùng ngữ nghĩa tương tự:

~~~sql
RANGE BETWEEN UNBOUNDED PRECEDING
          AND CURRENT ROW
~~~

Theo quy tắc RANGE, CURRENT ROW còn có ý nghĩa liên quan đến **nhóm các dòng đồng thứ tự (peers)**. Nếu thứ tự là duy nhất, frame này tương đương về các dòng với tập từ đầu đến dòng hiện tại.

Ví dụ minh họa có thứ tự duy nhất:

~~~sql
SELECT
    ma_giao_dich,
    ma_khach,
    so_tien,
    LAST_VALUE(so_tien) OVER (
        PARTITION BY ma_khach
        ORDER BY ngay_giao_dich, ma_giao_dich
        ROWS BETWEEN UNBOUNDED PRECEDING
                 AND CURRENT ROW
    ) AS gia_tri_cuoi_den_hien_tai
FROM giao_dich;
~~~

Với khách A:

| ma_giao_dich | so_tien | gia_tri_cuoi_den_hien_tai |
|---:|---:|---:|
| 101 | 100 | 100 |
| 102 | NULL | NULL |
| 103 | 300 | 300 |
| 104 | 400 | 400 |

Đây là kết quả đúng của câu hỏi **“giá trị cuối tính đến dòng hiện tại”**. Nhưng nếu bạn muốn **“giao dịch cuối cùng trong toàn lịch sử của khách”**, kết quả đó là **sai yêu cầu**.

**Quy tắc nhớ:** khi muốn LAST_VALUE của **toàn partition**, ghi rõ:

~~~sql
ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING
~~~

Không nên chỉ dựa vào PARTITION BY và ORDER BY rồi nghĩ hàm tự nhìn toàn bộ partition.

### 6.3. Frame mặc định có thể bao gồm cả những dòng “đồng hạng”

Với khách A, hai giao dịch **102** và **103** cùng ngày 2026-01-05. Nếu chỉ viết:

~~~sql
LAST_VALUE(so_tien) OVER (
    PARTITION BY ma_khach
    ORDER BY ngay_giao_dich
)
~~~

và DBMS dùng frame mặc định **RANGE ... CURRENT ROW**, frame của cả hai dòng cùng ngày có thể bao gồm **toàn bộ nhóm peer ngày 2026-01-05**, không chỉ những dòng được thấy “ở trước” theo thứ tự hiển thị.

Kết quả LAST_VALUE của peer group có thể phụ thuộc vào cách các dòng đồng ngày được sắp bên trong nhóm, trừ khi có quy tắc phá hòa. Vì vậy:

- **ROWS** xác định frame theo vị trí dòng.
- **RANGE** xác định frame theo giá trị ORDER BY và nhóm peer.
- Khi ORDER BY chưa duy nhất, **cả cách chọn dòng đầu/cuối trong các peer vẫn có thể không ổn định**.

Muốn thứ tự xác định, thêm khóa phụ **ma_giao_dich**; muốn cuối cả partition, thêm full frame.

## 7. NTH_VALUE: giá trị ở vị trí thứ N trong frame

Cú pháp phổ biến ở DBMS có hỗ trợ:

~~~sql
NTH_VALUE(bieu_thuc, N) OVER (
    PARTITION BY ...
    ORDER BY ...
    ROWS BETWEEN ...
)
~~~

Hàm trả giá trị biểu thức tại **dòng thứ N của frame**, tính từ **1** theo thứ tự đã chọn, trừ khi phương ngữ có tùy chọn tính từ cuối.

- **N = 1**: dòng đầu của frame, tương tự FIRST_VALUE với cùng quy tắc.
- **N = 2**: dòng thứ hai.
- **N = 3**: dòng thứ ba.
- Nếu frame có **ít hơn N dòng**: thường trả **NULL**.
- Nếu dòng thứ N có **giá trị biểu thức NULL**: cũng trả **NULL** trong chế độ RESPECT NULLS.

**N không bắt đầu từ 0.** N = 0 hoặc số âm thường không hợp lệ; mức kiểm tra biểu thức N và cú pháp truyền tham số có thể khác theo DBMS.

### 7.1. Giao dịch thứ ba của mỗi khách

~~~sql
SELECT
    ma_giao_dich,
    ma_khach,
    so_tien,
    NTH_VALUE(so_tien, 3) OVER (
        PARTITION BY ma_khach
        ORDER BY ngay_giao_dich, ma_giao_dich
        ROWS BETWEEN UNBOUNDED PRECEDING
                 AND UNBOUNDED FOLLOWING
    ) AS so_tien_giao_dich_thu_ba
FROM giao_dich
ORDER BY ma_khach, ngay_giao_dich, ma_giao_dich;
~~~

Kết quả ở DBMS hỗ trợ NTH_VALUE:

| ma_giao_dich | ma_khach | so_tien | so_tien_giao_dich_thu_ba |
|---:|---|---:|---:|
| 101 | A | 100 | 300 |
| 102 | A | NULL | 300 |
| 103 | A | 300 | 300 |
| 104 | A | 400 | 300 |
| 201 | B | NULL | 300 |
| 202 | B | 200 | 300 |
| 203 | B | 300 | 300 |
| 301 | C | 500 | NULL |

C chỉ có **một giao dịch**, nên không có dòng thứ ba. NTH_VALUE(...,3) trả NULL; đó là **không có vị trí thứ ba**, không nhất thiết là dữ liệu hỏng.

### 7.2. Cửa sổ đang mở rộng: NTH_VALUE có thể “chưa xuất hiện”

Nếu dùng frame:

~~~sql
ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
~~~

thì khách A có:

| Dòng hiện tại | Số dòng trong frame | NTH_VALUE(so_tien, 3) |
|---:|---:|---:|
| 101 | 1 | NULL |
| 102 | 2 | NULL |
| 103 | 3 | 300 |
| 104 | 4 | 300 |

Hàm không trả tiền của giao dịch thứ ba **trước khi dòng thứ ba nằm trong frame**. Với frame có peer theo RANGE, thời điểm “đủ N dòng” có thể khác cách hiểu từng dòng như trên.

### 7.3. NTH_VALUE(so_tien, 2) của khách A là NULL vì sao?

Với full frame và mặc định RESPECT NULLS, vị trí thứ hai của khách A là giao dịch **102**, có **so_tien = NULL**. Do đó:

~~~text
NTH_VALUE(so_tien, 2) = NULL
~~~

Đây **không phải** vì thiếu giao dịch thứ hai; nó có tồn tại nhưng số tiền bị thiếu.

Muốn phân biệt hai nguyên nhân “không đủ N dòng” và “dòng thứ N có NULL”, có thể kết hợp **COUNT(*) OVER(PARTITION BY ...)** và số thứ tự dòng.

## 8. Bảng tổng hợp ba hàm với full frame

Với khung:

~~~sql
PARTITION BY ma_khach
ORDER BY ngay_giao_dich, ma_giao_dich
ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING
~~~

mỗi dòng cùng khách nhận cùng bộ giá trị:

| Khách | FIRST_VALUE(so_tien) | LAST_VALUE(so_tien) | NTH_VALUE(so_tien,2) | NTH_VALUE(so_tien,3) |
|---|---:|---:|---:|---:|
| A | 100 | 400 | NULL | 300 |
| B | NULL | 300 | 200 | 300 |
| C | 500 | 500 | NULL | NULL |

Bảng này giả định hành vi **RESPECT NULLS** mặc định, như ở nhiều DBMS. Ở hệ có tùy chọn IGNORE NULLS, nếu bật nó thì kết quả có thể thay đổi đáng kể.

Đặt câu hỏi để đọc đúng từng giá trị:

1. **Partition là ai?** Khách A, B hay C.
2. **Thứ tự là gì?** Theo ngày, rồi mã giao dịch.
3. **Frame gồm những dòng nào?** Toàn partition.
4. **Bỏ qua NULL hay giữ NULL theo vị trí?** Đang RESPECT.
5. **N đếm từ 1 hay từ cuối?** NTH_VALUE thường từ đầu, N = 2 hoặc 3.

## 9. Khung cửa sổ: ROWS và RANGE khác nhau ra sao?

### 9.1. ROWS: dựa trên vị trí dòng

Ví dụ:

~~~sql
ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
~~~

tạo frame gồm **tối đa ba dòng theo thứ tự**: hai dòng trước và dòng hiện tại. Ở đầu partition, nếu chưa có đủ hai dòng trước, frame nhỏ hơn ba dòng.

Giả sử khách A theo thứ tự 101, 102, 103, 104:

| Dòng hiện tại | Frame ROWS 2 PRECEDING ... CURRENT ROW |
|---:|---|
| 101 | {101} |
| 102 | {101, 102} |
| 103 | {101, 102, 103} |
| 104 | {102, 103, 104} |

Trong frame đó:

- FIRST_VALUE(so_tien) ở dòng 104 là **NULL** (giá trị dòng 102).
- LAST_VALUE(so_tien) ở dòng 104 là **400**.
- NTH_VALUE(so_tien,2) ở dòng 104 là **300**.

Đây là hành vi **cửa sổ trượt**, không phải giá trị đầu/cuối toàn lịch sử.

### 9.2. RANGE: dựa trên giá trị thứ tự và nhóm peer

Một frame thường gặp:

~~~sql
RANGE BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
~~~

Theo ngữ nghĩa chuẩn cho frame dựa trên ORDER BY, **CURRENT ROW** ở RANGE bao gồm cả các dòng có giá trị sắp xếp bằng nhau (peer group) ở cận hiện tại.

Ví dụ hai giao dịch cùng ngày 2026-01-05 có thể cùng nằm trong frame của nhau khi ORDER BY chỉ có **ngay_giao_dich**. Hành vi này khác ROWS, vốn xét từng vị trí dòng.

### 9.3. GROUPS: theo nhóm peer

Một số DBMS còn hỗ trợ:

~~~sql
GROUPS BETWEEN 1 PRECEDING AND CURRENT ROW
~~~

GROUPS di chuyển theo **nhóm đồng hạng ORDER BY**, không theo từng dòng hay khoảng giá trị kiểu RANGE. Không phải mọi hệ quản trị hỗ trợ GROUPS ở cùng phiên bản.

Khi mới học ba hàm giá trị, hãy dùng **ROWS với ranh giới tường minh** để dễ dự đoán. Khi nhu cầu thật sự liên quan đến nhóm peer, mới cân nhắc RANGE/GROUPS và kiểm tra phương ngữ.

### 9.4. Những ranh giới thường gặp

| Ranh giới | Ý nghĩa |
|---|---|
| UNBOUNDED PRECEDING | Đầu partition hoặc đầu phạm vi frame |
| N PRECEDING | N dòng/đơn vị trước, tùy ROWS/RANGE/GROUPS |
| CURRENT ROW | Dòng hiện tại hoặc nhóm peer, tùy frame mode |
| N FOLLOWING | N dòng/đơn vị sau |
| UNBOUNDED FOLLOWING | Cuối partition |

Với FIRST_VALUE/LAST_VALUE/NTH_VALUE, thay đổi frame có thể thay đổi **dòng mà hàm được quyền chọn**, dù PARTITION BY và ORDER BY không đổi.

## 10. Hai mẫu frame nên nhớ

### 10.1. Giá trị đầu/cuối/thứ N của toàn partition

~~~sql
OVER (
    PARTITION BY ma_khach
    ORDER BY ngay_giao_dich, ma_giao_dich
    ROWS BETWEEN UNBOUNDED PRECEDING
             AND UNBOUNDED FOLLOWING
)
~~~

Sử dụng khi báo cáo muốn một giá trị cố định cho cả khách: **giao dịch đầu**, **giao dịch cuối**, **giao dịch thứ ba**.

### 10.2. Giá trị đầu/cuối tính đến dòng hiện tại

~~~sql
OVER (
    PARTITION BY ma_khach
    ORDER BY ngay_giao_dich, ma_giao_dich
    ROWS BETWEEN UNBOUNDED PRECEDING
             AND CURRENT ROW
)
~~~

Sử dụng khi báo cáo muốn theo tiến trình: **giá trị đầu kể từ lúc bắt đầu đến nay**, **giá trị gần nhất đến hiện tại**, hoặc **giá trị thứ N sau khi lịch sử đủ N dòng**.

**Mỗi mẫu đều đúng trong một bài toán khác nhau.** Lỗi không nằm ở frame mặc định “sai về SQL”, mà ở việc nó **không phù hợp với ý định** của người viết truy vấn.

## 11. IGNORE NULLS và RESPECT NULLS

Một số hệ quản trị cho phép xác định cách các hàm giá trị xử lý NULL:

- **RESPECT NULLS:** NULL vẫn được tính là vị trí trong thứ tự/frame. Nếu dòng được chọn có giá trị NULL, kết quả NULL.
- **IGNORE NULLS:** bỏ qua các giá trị NULL của **biểu thức đang xét** khi tìm phần tử đầu/cuối/thứ N, theo quy tắc và cú pháp DBMS.

Không nên hiểu **IGNORE NULLS** là xóa toàn bộ dòng khỏi kết quả SELECT; các dòng vẫn có thể được hiển thị, chỉ quá trình **chọn giá trị từ frame** thay đổi.

### 11.1. Ví dụ FIRST_VALUE của khách B

Giao dịch B theo thứ tự:

~~~text
201: NULL
202: 200
203: 300
~~~

Với full frame:

- **FIRST_VALUE RESPECT NULLS** → NULL.
- **FIRST_VALUE IGNORE NULLS** → 200.

Trong trường hợp này, **giá trị đầu tiên** khác **giá trị không NULL đầu tiên**.

### 11.2. Ví dụ LAST_VALUE khi cuối partition có NULL

Giả sử một khách D có:

~~~text
Ngày 1: 100
Ngày 2: 200
Ngày 3: NULL
~~~

Với full frame:

- **LAST_VALUE RESPECT NULLS** → NULL.
- **LAST_VALUE IGNORE NULLS** → 200.

Khi báo cáo “số đo mới nhất”, cần quyết định xem giá trị NULL có nghĩa là **bản ghi mới nhất chưa có đo đạc** hay muốn “giá trị đo gần nhất có dữ liệu”. Hai yêu cầu khác nhau.

### 11.3. NTH_VALUE IGNORE NULLS

Khách A:

~~~text
Vị trí gốc: 100, NULL, 300, 400
Chỉ giá trị không NULL: 100, 300, 400
~~~

Với full frame:

- **NTH_VALUE(so_tien, 2) RESPECT NULLS** → NULL.
- **NTH_VALUE(so_tien, 2) IGNORE NULLS** → 300.
- **NTH_VALUE(so_tien, 3) IGNORE NULLS** → 400.

Khi bỏ qua NULL, **N** được đếm theo dãy giá trị còn lại, không còn trùng vị trí dòng N ban đầu.

### 11.4. Không phải hệ quản trị nào cũng hỗ trợ IGNORE NULLS

Trong các phiên bản phổ biến:

- **Oracle Database** hỗ trợ tùy chọn **IGNORE NULLS / RESPECT NULLS** cho những hàm liên quan.
- **SQL Server 2022 trở lên** hỗ trợ tùy chọn này ở **FIRST_VALUE/LAST_VALUE**; các bản cũ hơn không có cùng cú pháp.
- **PostgreSQL** không triển khai cú pháp IGNORE NULLS cho FIRST_VALUE, LAST_VALUE, NTH_VALUE theo tài liệu truyền thống; hành vi như RESPECT NULLS.
- **MySQL 8.0** có cú pháp NULL treatment nhưng **IGNORE NULLS chưa được triển khai ở các bản phổ biến**, nên có thể báo lỗi nếu dùng; chỉ RESPECT NULLS/giá trị mặc định hoạt động.
- **SQLite** không có cú pháp IGNORE NULLS tương đương cho ba hàm trong bộ window functions phổ biến.
- **BigQuery** và một số hệ phân tích có hỗ trợ biến thể IGNORE NULLS, nhưng **vị trí từ khóa trong cú pháp có thể khác Oracle và SQL Server**.

Vì vậy, **không sao chép nguyên đoạn IGNORE NULLS giữa các DBMS**. Phải đối chiếu tài liệu và phiên bản thực tế.

## 12. NTH_VALUE tính từ đầu hay từ cuối?

Thông thường, **NTH_VALUE(expr, N)** chọn dòng thứ N **từ đầu frame**. Một số phương ngữ hỗ trợ thêm:

~~~sql
NTH_VALUE(expr, N) FROM LAST ...
~~~

để đếm ngược từ **cuối frame**.

Ví dụ khách A theo thứ tự thời gian:

~~~text
1: 100
2: NULL
3: 300
4: 400
~~~

Với full frame:

- **Thứ hai từ đầu** → NULL.
- **Thứ hai từ cuối** → 300.
- **Thứ ba từ cuối** → NULL.

### 12.1. Oracle: FROM FIRST / FROM LAST

Oracle có cú pháp theo ý tưởng:

~~~sql
NTH_VALUE(so_tien, 2) FROM LAST
    OVER (
        PARTITION BY ma_khach
        ORDER BY ngay_giao_dich, ma_giao_dich
        ROWS BETWEEN UNBOUNDED PRECEDING
                 AND UNBOUNDED FOLLOWING
    )
~~~

Cú pháp thực tế còn có vị trí tùy chọn RESPECT/IGNORE NULLS giữa phần hàm và OVER. Với khách A, giá trị thứ hai từ cuối là **300**.

**Cảnh báo quan trọng:** nếu dùng **FROM LAST** nhưng frame mặc định chỉ kéo tới CURRENT ROW, “cuối” sẽ là **cuối của frame ở từng dòng hiện tại**, không phải cuối toàn partition. Khi cần N-th từ cuối toàn bộ lịch sử, **luôn chỉ rõ full frame**.

### 12.2. MySQL: FROM LAST không đồng nghĩa được thực thi

Trong các phiên bản MySQL 8.0 phổ biến, cú pháp NTH_VALUE có nhắc đến FROM FIRST/FROM LAST, nhưng **FROM LAST có thể được bộ phân tích cú pháp nhận mà chưa được thực thi**, dẫn tới lỗi. Không nên suy ra hỗ trợ đầy đủ chỉ vì parser chấp nhận từ khóa.

### 12.3. Cách khả chuyển hơn: đảo ORDER BY

Nếu DBMS hỗ trợ NTH_VALUE nhưng không hỗ trợ FROM LAST, có thể đảo thứ tự:

~~~sql
NTH_VALUE(so_tien, 2) OVER (
    PARTITION BY ma_khach
    ORDER BY ngay_giao_dich DESC, ma_giao_dich DESC
    ROWS BETWEEN UNBOUNDED PRECEDING
             AND UNBOUNDED FOLLOWING
)
~~~

Khi thứ tự thời gian tăng dần ban đầu được đảo hoàn toàn, **dòng thứ hai của thứ tự giảm dần** là **dòng thứ hai từ cuối** của thứ tự tăng dần.

Để tương đương thật sự, cần đảm bảo:

1. **Đảo tất cả các khóa ORDER BY**, gồm khóa phá hòa.
2. Xác định quy tắc **NULLS FIRST/LAST** nếu khóa sắp xếp có thể NULL.
3. Dùng **cùng full frame** nếu muốn tính trên toàn partition.
4. Xác định có **IGNORE NULLS** hay không; đảo thứ tự không tự bỏ NULL.
5. Không nhầm “thứ hai mới nhất” với “giá trị lớn thứ hai”: đó là hai định nghĩa khác nhau.

## 13. So sánh theo hệ quản trị: bảng tổng quan

Bảng dưới đây phản ánh hỗ trợ thường gặp; một số tính năng thay đổi theo phiên bản, nên luôn xác minh trên server đích.

| DBMS | FIRST_VALUE | LAST_VALUE | NTH_VALUE | IGNORE NULLS | Ghi chú |
|---|---|---|---|---|---|
| **PostgreSQL** | Có | Có | Có | Chưa có cú pháp IGNORE NULLS tương ứng trong bản phổ biến | Chú ý default frame; có ROWS, RANGE, GROUPS tùy phiên bản |
| **MySQL 8.0+** | Có | Có | Có | IGNORE NULLS chưa được triển khai ở các bản phổ biến | NTH_VALUE FROM LAST không hỗ trợ đầy đủ; CAST/kiểu và SQL mode cần chú ý |
| **SQL Server** | Có từ 2012 | Có từ 2012 | Không có hàm NTH_VALUE trực tiếp trong những bản phổ biến | FIRST/LAST hỗ trợ IGNORE NULLS từ 2022 | Dùng ROW_NUMBER để mô phỏng NTH |
| **Oracle Database** | Có | Có | Có | Có | Có FROM FIRST/FROM LAST cho NTH_VALUE; chú ý frame |
| **SQLite 3.25+** | Có | Có | Có | Không có tùy chọn IGNORE NULLS tương đương | Ba hàm này tôn trọng frame; khác với lag/lead |
| **BigQuery** | Có | Có | Có | Có theo cú pháp GoogleSQL | Tên và vị trí tùy chọn NULL khác các hệ khác |

**Không thể thay thế đánh giá phiên bản chỉ bằng tên sản phẩm.** Ví dụ “SQL Server” chưa đủ để kết luận có IGNORE NULLS; “MySQL 5.7” chưa có hệ window functions như MySQL 8; một sản phẩm lưu trữ dữ liệu dạng SQL tương thích khác có thể có cú pháp hoặc giới hạn riêng.

## 14. PostgreSQL: ba hàm và bẫy frame

PostgreSQL hỗ trợ ba hàm:

~~~sql
SELECT
    ma_khach,
    ma_giao_dich,
    so_tien,
    FIRST_VALUE(so_tien) OVER w AS tien_dau,
    LAST_VALUE(so_tien) OVER w AS tien_cuoi,
    NTH_VALUE(so_tien, 3) OVER w AS tien_thu_ba
FROM giao_dich
WINDOW w AS (
    PARTITION BY ma_khach
    ORDER BY ngay_giao_dich, ma_giao_dich
    ROWS BETWEEN UNBOUNDED PRECEDING
             AND UNBOUNDED FOLLOWING
)
ORDER BY ma_khach, ngay_giao_dich, ma_giao_dich;
~~~

**WINDOW w AS (...)** đặt tên một window specification để tái sử dụng. Tính hỗ trợ cú pháp WINDOW có thể khác các DBMS; nếu muốn khả chuyển cao hơn, lặp đầy đủ OVER(...) hoặc dùng một truy vấn trung gian.

### 14.1. NULL

Ở các phiên bản PostgreSQL phổ biến, FIRST_VALUE/LAST_VALUE/NTH_VALUE hoạt động theo **RESPECT NULLS**; không có tùy chọn IGNORE NULLS tương đương Oracle.

Để lấy **giá trị không NULL đầu tiên**, có thể tạo một thứ tự ưu tiên dòng không NULL:

~~~sql
SELECT
    ma_giao_dich,
    ma_khach,
    so_tien,
    FIRST_VALUE(so_tien) OVER (
        PARTITION BY ma_khach
        ORDER BY
            CASE WHEN so_tien IS NULL THEN 1 ELSE 0 END,
            ngay_giao_dich,
            ma_giao_dich
        ROWS BETWEEN UNBOUNDED PRECEDING
                 AND UNBOUNDED FOLLOWING
    ) AS tien_khong_null_dau
FROM giao_dich;
~~~

Trên mỗi khách, các dòng không NULL được đặt trước, rồi sắp theo thời gian tăng dần. Vì chỉ lấy một giá trị, kết quả tương đương **giá trị không NULL đầu tiên của toàn partition theo thứ tự thời gian**, nếu các khóa phá hòa xác định.

**Lưu ý:** cách này **thay đổi thứ tự trong window** để chọn giá trị. Nó không nên dùng nguyên dạng khi bạn muốn tính toán một frame trượt ban đầu hoặc khi NTH_VALUE phải tôn trọng một tập dòng đặc biệt. Với các bài toán đó, cần thiết kế lại frame/CTE theo đúng ngữ nghĩa.

### 14.2. NULL cuối cùng có thể được bỏ qua bằng thứ tự đảo

Muốn **giá trị không NULL mới nhất** của mỗi khách:

~~~sql
FIRST_VALUE(so_tien) OVER (
    PARTITION BY ma_khach
    ORDER BY
        CASE WHEN so_tien IS NULL THEN 1 ELSE 0 END,
        ngay_giao_dich DESC,
        ma_giao_dich DESC
    ROWS BETWEEN UNBOUNDED PRECEDING
             AND UNBOUNDED FOLLOWING
)
~~~

Trong danh sách không NULL, dòng mới nhất được đặt đầu. Đây là cách mô phỏng ở mức **toàn partition** khi IGNORE NULLS không có sẵn, không phải công thức có thể thay thế tùy ý cho mọi frame.

## 15. MySQL 8: FIRST_VALUE/LAST_VALUE/NTH_VALUE

MySQL 8.0 có các hàm cửa sổ này:

~~~sql
SELECT
    ma_khach,
    ma_giao_dich,
    so_tien,
    FIRST_VALUE(so_tien) OVER w AS tien_dau,
    LAST_VALUE(so_tien) OVER w AS tien_cuoi,
    NTH_VALUE(so_tien, 2) OVER w AS tien_thu_hai
FROM giao_dich
WINDOW w AS (
    PARTITION BY ma_khach
    ORDER BY ngay_giao_dich, ma_giao_dich
    ROWS BETWEEN UNBOUNDED PRECEDING
             AND UNBOUNDED FOLLOWING
)
ORDER BY ma_khach, ngay_giao_dich, ma_giao_dich;
~~~

MySQL hỗ trợ đặt tên cửa sổ bằng WINDOW trong dòng 8.0; cần kiểm tra giới hạn cú pháp nếu muốn dùng WINDOW cùng những mệnh đề khác.

### 15.1. RESPECT NULLS là hành vi thông thường

Hệ MySQL 8.0 mô tả cách tôn trọng NULL; IGNORE NULLS có thể được nhận diện ở mức cú pháp nhưng chưa được hỗ trợ thực thi. Không đưa **IGNORE NULLS** vào câu SQL MySQL mà chưa xác minh phiên bản.

### 15.2. NTH_VALUE và FROM LAST

Muốn “thứ hai từ cuối”, dùng **ORDER BY giảm dần + full frame** thay vì trông chờ FROM LAST trên MySQL 8.0:

~~~sql
SELECT
    ma_giao_dich,
    ma_khach,
    NTH_VALUE(so_tien, 2) OVER (
        PARTITION BY ma_khach
        ORDER BY ngay_giao_dich DESC, ma_giao_dich DESC
        ROWS BETWEEN UNBOUNDED PRECEDING
                 AND UNBOUNDED FOLLOWING
    ) AS tien_thu_hai_tu_cuoi
FROM giao_dich;
~~~

### 15.3. N là vị trí, không phải tham số tùy ý cho mọi phiên bản

Một số phiên bản MySQL giới hạn dạng biểu thức được phép dùng làm **N** và yêu cầu N là số nguyên dương không NULL. Nếu muốn vị trí do người dùng chọn, cần truyền tham số đúng kiểu và kiểm tra tài liệu phiên bản, thay vì ghép chuỗi N vào câu SQL.

## 16. SQL Server: FIRST_VALUE/LAST_VALUE có, NTH_VALUE cần mô phỏng

SQL Server hỗ trợ FIRST_VALUE/LAST_VALUE với OVER và frame tường minh:

~~~sql
SELECT
    ma_khach,
    ma_giao_dich,
    so_tien,
    FIRST_VALUE(so_tien) OVER (
        PARTITION BY ma_khach
        ORDER BY ngay_giao_dich, ma_giao_dich
        ROWS BETWEEN UNBOUNDED PRECEDING
                 AND UNBOUNDED FOLLOWING
    ) AS tien_dau,
    LAST_VALUE(so_tien) OVER (
        PARTITION BY ma_khach
        ORDER BY ngay_giao_dich, ma_giao_dich
        ROWS BETWEEN UNBOUNDED PRECEDING
                 AND UNBOUNDED FOLLOWING
    ) AS tien_cuoi
FROM giao_dich;
~~~

Không có từ khóa SQL Server riêng để biến LAST_VALUE thành “cuối toàn partition” một cách tự động. Mệnh đề **ROWS ... UNBOUNDED FOLLOWING** vẫn là cách diễn đạt rõ ràng.

### 16.1. SQL Server 2022+ và IGNORE NULLS

Ở SQL Server 2022 trở lên, có thể dùng tùy chọn NULL trên FIRST_VALUE/LAST_VALUE theo cú pháp T-SQL:

~~~sql
FIRST_VALUE(so_tien) IGNORE NULLS OVER (
    PARTITION BY ma_khach
    ORDER BY ngay_giao_dich, ma_giao_dich
    ROWS BETWEEN UNBOUNDED PRECEDING
             AND UNBOUNDED FOLLOWING
)
~~~

Với B, kết quả sẽ chọn **200** thay vì NULL.

Ở SQL Server 2019 và những bản cũ hơn, **không được giả định IGNORE NULLS hoạt động**. Có thể mô phỏng bằng window order phù hợp hoặc CTE lọc các dòng có giá trị.

### 16.2. Mô phỏng NTH_VALUE bằng ROW_NUMBER + window aggregate

Đối với cột **so_tien** là kiểu số hỗ trợ MAX:

~~~sql
WITH xep_hang AS (
    SELECT
        g.*,
        ROW_NUMBER() OVER (
            PARTITION BY ma_khach
            ORDER BY ngay_giao_dich, ma_giao_dich
        ) AS so_thu_tu
    FROM giao_dich g
)
SELECT
    ma_giao_dich,
    ma_khach,
    so_tien,
    MAX(
        CASE
            WHEN so_thu_tu = 3 THEN so_tien
            ELSE NULL
        END
    ) OVER (
        PARTITION BY ma_khach
    ) AS tien_thu_ba
FROM xep_hang
ORDER BY ma_khach, ngay_giao_dich, ma_giao_dich;
~~~

Trong mỗi khách, chỉ **một dòng** có so_thu_tu = 3 (nếu tồn tại). MAX trên biểu thức CASE sẽ truyền giá trị số tiền của dòng đó tới toàn partition.

Kết quả tương đương **NTH_VALUE(so_tien, 3) trên full frame, RESPECT NULLS**, với điều kiện:

- Thứ tự ROW_NUMBER là thứ tự mong muốn.
- Mỗi partition xác định duy nhất dòng số 3 nhờ ORDER BY có khóa phá hòa.
- Kiểu biểu thức hỗ trợ tổng hợp MAX.
- Nếu dòng thứ ba có so_tien NULL hoặc không tồn tại, kết quả là NULL, giống NTH_VALUE theo ngữ nghĩa đã chọn.

**Đừng dùng MAX(so_tien) đơn thuần** để thay NTH_VALUE: MAX chọn giá trị lớn nhất, không phải dòng thứ ba.

### 16.3. Nếu không dùng MAX được, JOIN lại dòng có số thứ tự

Một mẫu khác:

~~~sql
WITH xep_hang AS (
    SELECT
        g.*,
        ROW_NUMBER() OVER (
            PARTITION BY ma_khach
            ORDER BY ngay_giao_dich, ma_giao_dich
        ) AS so_thu_tu
    FROM giao_dich g
),
dong_thu_ba AS (
    SELECT ma_khach, so_tien
    FROM xep_hang
    WHERE so_thu_tu = 3
)
SELECT
    x.ma_giao_dich,
    x.ma_khach,
    x.so_tien,
    n.so_tien AS tien_thu_ba
FROM xep_hang x
LEFT JOIN dong_thu_ba n
    ON n.ma_khach = x.ma_khach;
~~~

Ở bộ dữ liệu minh họa, **ma_khach NOT NULL**, nên phép JOIN bằng an toàn cho khóa partition. Nếu khóa partition có thể NULL, GROUP BY và PARTITION BY xem các NULL là một nhóm, nhưng **NULL = NULL trong JOIN không TRUE**; muốn mô phỏng chính xác phải dùng điều kiện null-safe hoặc cơ chế kết nối khác phù hợp DBMS.

## 17. Oracle Database: hỗ trợ ba hàm và FROM LAST

Oracle hỗ trợ FIRST_VALUE, LAST_VALUE và NTH_VALUE như những hàm phân tích.

~~~sql
SELECT
    ma_khach,
    ma_giao_dich,
    so_tien,
    FIRST_VALUE(so_tien) OVER (
        PARTITION BY ma_khach
        ORDER BY ngay_giao_dich, ma_giao_dich
        ROWS BETWEEN UNBOUNDED PRECEDING
                 AND UNBOUNDED FOLLOWING
    ) AS tien_dau,
    LAST_VALUE(so_tien) OVER (
        PARTITION BY ma_khach
        ORDER BY ngay_giao_dich, ma_giao_dich
        ROWS BETWEEN UNBOUNDED PRECEDING
                 AND UNBOUNDED FOLLOWING
    ) AS tien_cuoi,
    NTH_VALUE(so_tien, 3) FROM FIRST OVER (
        PARTITION BY ma_khach
        ORDER BY ngay_giao_dich, ma_giao_dich
        ROWS BETWEEN UNBOUNDED PRECEDING
                 AND UNBOUNDED FOLLOWING
    ) AS tien_thu_ba
FROM giao_dich;
~~~

### 17.1. IGNORE NULLS trong Oracle

Ví dụ ý tưởng: giá trị số tiền đầu tiên không NULL theo khách.

~~~sql
FIRST_VALUE(so_tien) IGNORE NULLS OVER (
    PARTITION BY ma_khach
    ORDER BY ngay_giao_dich, ma_giao_dich
    ROWS BETWEEN UNBOUNDED PRECEDING
             AND UNBOUNDED FOLLOWING
)
~~~

Oracle có các tùy chọn IGNORE/RESPECT NULLS cho những hàm liên quan; vị trí cú pháp của NTH_VALUE kết hợp FROM FIRST/FROM LAST và NULL treatment cần viết theo quy tắc của Oracle.

### 17.2. NTH_VALUE FROM LAST

Muốn số tiền của dòng thứ hai tính từ **cuối**:

~~~sql
NTH_VALUE(so_tien, 2) FROM LAST OVER (
    PARTITION BY ma_khach
    ORDER BY ngay_giao_dich, ma_giao_dich
    ROWS BETWEEN UNBOUNDED PRECEDING
             AND UNBOUNDED FOLLOWING
)
~~~

Cần nêu **full frame** để tránh việc “cuối” thay đổi theo dòng hiện tại.

### 17.3. Oracle còn có KEEP (DENSE_RANK ...)

Oracle cũng có các mẫu aggregate như **MIN/MAX(...) KEEP (DENSE_RANK FIRST/LAST ORDER BY ...)** để lấy giá trị thuộc nhóm thứ hạng đầu/cuối. Đây là công cụ khác về mặt ngữ nghĩa, đặc biệt khi có nhiều dòng đồng hạng và cần trả một dòng mỗi nhóm.

Không nên tự coi KEEP, FIRST_VALUE hay ROW_NUMBER là đồng nghĩa trong mọi trường hợp: phải xác định cách chọn khi đồng hạng và cấp chi tiết đầu ra.

## 18. SQLite: ba hàm giá trị tôn trọng frame

SQLite từ phiên bản hỗ trợ window functions (dòng 3.25.0 trở lên) có FIRST_VALUE, LAST_VALUE, NTH_VALUE.

~~~sql
SELECT
    ma_khach,
    ma_giao_dich,
    so_tien,
    first_value(so_tien) OVER (
        PARTITION BY ma_khach
        ORDER BY ngay_giao_dich, ma_giao_dich
        ROWS BETWEEN UNBOUNDED PRECEDING
                 AND UNBOUNDED FOLLOWING
    ) AS tien_dau,
    last_value(so_tien) OVER (
        PARTITION BY ma_khach
        ORDER BY ngay_giao_dich, ma_giao_dich
        ROWS BETWEEN UNBOUNDED PRECEDING
                 AND UNBOUNDED FOLLOWING
    ) AS tien_cuoi,
    nth_value(so_tien, 3) OVER (
        PARTITION BY ma_khach
        ORDER BY ngay_giao_dich, ma_giao_dich
        ROWS BETWEEN UNBOUNDED PRECEDING
                 AND UNBOUNDED FOLLOWING
    ) AS tien_thu_ba
FROM giao_dich;
~~~

Trong SQLite, **lag/lead** và ba hàm FIRST_VALUE/LAST_VALUE/NTH_VALUE không hoàn toàn giống nhau về frame: **lag/lead** có cách tham chiếu tương đối đến các hàng partition, còn **ba hàm giá trị này tôn trọng frame specification**. Đây là lý do cần nắm frame ngay cả khi đã quen LAG/LEAD.

SQLite không có tùy chọn IGNORE NULLS cho ba hàm này trong cú pháp phổ biến. Nếu muốn giá trị không NULL đầu/cuối, có thể dùng thứ tự ưu tiên không NULL hoặc bước lọc trước đó.

### 18.1. NTH_VALUE không phải LAG với offset N

- **NTH_VALUE(expr, 3)** chọn dòng **thứ ba của frame**.
- **LAG(expr, 3)** lấy giá trị **ba dòng trước dòng hiện tại** trong partition theo quy tắc của LAG.
- **LEAD(expr, 3)** lấy giá trị **ba dòng sau dòng hiện tại**.

Đây là ba câu hỏi khác nhau, ngay cả khi tại vài dòng cụ thể chúng tình cờ cho cùng giá trị.

## 19. BigQuery và các hệ phân tích

Trong GoogleSQL của BigQuery, FIRST_VALUE, LAST_VALUE và NTH_VALUE thuộc nhóm navigation functions. BigQuery hỗ trợ các cách chỉ định **RESPECT NULLS / IGNORE NULLS**, nhưng cú pháp đặt từ khóa có thể nằm **bên trong danh sách đối số**.

Ví dụ minh họa theo kiểu BigQuery:

~~~sql
FIRST_VALUE(so_tien IGNORE NULLS) OVER (
    PARTITION BY ma_khach
    ORDER BY ngay_giao_dich, ma_giao_dich
    ROWS BETWEEN UNBOUNDED PRECEDING
             AND UNBOUNDED FOLLOWING
)
~~~

Với NTH_VALUE:

~~~sql
NTH_VALUE(so_tien, 2 IGNORE NULLS) OVER (
    PARTITION BY ma_khach
    ORDER BY ngay_giao_dich, ma_giao_dich
    ROWS BETWEEN UNBOUNDED PRECEDING
             AND UNBOUNDED FOLLOWING
)
~~~

Các ví dụ này **không thể chuyển nguyên văn** sang Oracle hoặc SQL Server vì vị trí cú pháp NULL treatment khác.

Trong các dịch vụ phân tích khác như Snowflake, Databricks SQL, Trino hoặc DuckDB, khả năng hỗ trợ có thể khác theo sản phẩm và phiên bản. Khi chuyển câu truy vấn, cần kiểm tra **tên hàm, syntax NULL treatment, FROM LAST, default frame, các kiểu được chấp nhận** chứ không chỉ kiểm tra có từ khóa OVER.

## 20. Kết quả không ổn định khi ORDER BY có giá trị trùng

Giả sử hai giao dịch đầu của khách Z cùng ngày, với số tiền 100 và 200:

~~~text
ma_giao_dich | ngay_giao_dich | so_tien
-------------+----------------+--------
1            | 2026-01-01     | 100
2            | 2026-01-01     | 200
~~~

Nếu viết:

~~~sql
FIRST_VALUE(so_tien) OVER (
    PARTITION BY ma_khach
    ORDER BY ngay_giao_dich
    ROWS BETWEEN UNBOUNDED PRECEDING
             AND UNBOUNDED FOLLOWING
)
~~~

thì cả hai dòng cùng giá trị ORDER BY. DBMS không có nghĩa vụ coi mã 1 đi trước mã 2 khi mã không nằm trong ORDER BY; FIRST_VALUE có thể trả 100 hoặc 200 tùy kế hoạch/thứ tự không ràng buộc.

Sửa bằng tiêu chí rõ:

~~~sql
ORDER BY ngay_giao_dich, ma_giao_dich
~~~

Khi đó mã 1 được ưu tiên.

### 20.1. ORDER BY ở cuối SELECT không sửa được OVER thiếu khóa phá hòa

~~~sql
SELECT
    FIRST_VALUE(so_tien) OVER (
        PARTITION BY ma_khach
        ORDER BY ngay_giao_dich
    ) AS tien_dau
FROM giao_dich
ORDER BY ma_giao_dich;
~~~

ORDER BY cuối chỉ sắp xếp **các dòng kết quả**. Nó không bổ sung ma_giao_dich vào thứ tự dùng **bên trong** FIRST_VALUE. Muốn hàm xác định, phải thêm khóa ở **ORDER BY của OVER(...)**.

### 20.2. Nếu có timestamp trùng?

Dùng timestamp thay date vẫn có thể trùng trong những hệ thống gửi nhiều sự kiện cùng thời điểm. Nên có **event_id**, sequence do hệ thống nguồn cung cấp hoặc tiêu chí nghiệp vụ xác định rõ. Nếu bản thân nghiệp vụ không xác định trước/sau của hai sự kiện đồng hạng, hãy chấp nhận rằng “dòng đầu/ cuối duy nhất” chưa được định nghĩa và trình bày kết quả đồng hạng thay vì chọn tùy tiện.

## 21. FIRST/LAST theo thời gian khác MIN/MAX theo số tiền

Xét dữ liệu một khách:

| Thời điểm | so_tien |
|---|---:|
| 01/01 | 500 |
| 03/01 | 100 |
| 05/01 | 300 |

Khi ORDER BY thời điểm tăng dần, full frame:

- **FIRST_VALUE(so_tien)** = 500.
- **LAST_VALUE(so_tien)** = 300.
- **MIN(so_tien)** = 100.
- **MAX(so_tien)** = 500.
- **NTH_VALUE(so_tien, 2)** = 100.

Ví dụ MIN tình cờ bằng NTH thứ hai và MAX bằng FIRST, nhưng không có quan hệ cố định. Một thay đổi thứ tự thời gian sẽ đổi các hàm vị trí mà không nhất thiết đổi MIN/MAX.

### 21.1. Giá trị lớn thứ hai là câu hỏi khác

Muốn giá trị lớn thứ hai, phải xác định **có tính trùng giá trị không**, rồi sắp theo giá trị:

~~~sql
NTH_VALUE(so_tien, 2) OVER (
    PARTITION BY ma_khach
    ORDER BY so_tien DESC, ma_giao_dich
    ROWS BETWEEN UNBOUNDED PRECEDING
             AND UNBOUNDED FOLLOWING
)
~~~

Đây là **dòng thứ hai theo số tiền giảm dần**, không hẳn là **giá trị phân biệt lớn thứ hai**. Nếu có hai dòng cùng 500, NTH_VALUE thứ hai có thể vẫn là 500.

Nếu muốn **giá trị phân biệt lớn thứ hai**, có thể lọc DISTINCT số tiền rồi dùng DENSE_RANK hoặc ROW_NUMBER trên tập giá trị phân biệt phù hợp. Khi số tiền NULL, cần quy định có bỏ qua không.

## 22. Cách lấy giao dịch đầu/cuối mà vẫn giữ nguyên thông tin cùng dòng

FIRST_VALUE có thể áp dụng cho nhiều cột, nhưng phải dùng **cùng ORDER BY và frame** để các cột thuộc cùng dòng.

~~~sql
SELECT
    ma_khach,
    ma_giao_dich,
    so_tien,
    FIRST_VALUE(ma_giao_dich) OVER (
        PARTITION BY ma_khach
        ORDER BY ngay_giao_dich, ma_giao_dich
        ROWS BETWEEN UNBOUNDED PRECEDING
                 AND UNBOUNDED FOLLOWING
    ) AS ma_giao_dich_dau,
    FIRST_VALUE(so_tien) OVER (
        PARTITION BY ma_khach
        ORDER BY ngay_giao_dich, ma_giao_dich
        ROWS BETWEEN UNBOUNDED PRECEDING
                 AND UNBOUNDED FOLLOWING
    ) AS so_tien_dau
FROM giao_dich;
~~~

Với A, ma_giao_dich_dau = 101 và so_tien_dau = 100, cùng thuộc dòng giao dịch 101.

### 22.1. Nguy cơ lệch dòng khi mỗi cột có ORDER BY khác

Nếu một FIRST_VALUE chọn mã theo **ngày**, còn FIRST_VALUE khác chọn tiền theo **số tiền tăng dần**, hai giá trị có thể thuộc **hai giao dịch khác nhau**. Không thể coi chúng là một bản ghi đại diện duy nhất.

### 22.2. Khi muốn trả đúng một dòng giao dịch đầu/cuối

Một lựa chọn rõ ràng:

~~~sql
WITH xep_hang AS (
    SELECT
        g.*,
        ROW_NUMBER() OVER (
            PARTITION BY ma_khach
            ORDER BY ngay_giao_dich DESC, ma_giao_dich DESC
        ) AS rn_moi_nhat
    FROM giao_dich g
)
SELECT
    ma_khach,
    ma_giao_dich,
    ngay_giao_dich,
    so_tien
FROM xep_hang
WHERE rn_moi_nhat = 1;
~~~

Truy vấn trả đúng **một dòng mới nhất mỗi khách** khi khóa phá hòa duy nhất. Nếu có nhiều dòng đồng thời điểm và muốn giữ tất cả đồng hạng, cân nhắc RANK/DENSE_RANK thay vì ROW_NUMBER.

**FIRST_VALUE/LAST_VALUE** hữu ích khi muốn **lặp giá trị phân tích trên mọi dòng**; **ROW_NUMBER + lọc ngoài** hữu ích khi muốn **chọn một dòng cụ thể**.

## 23. WHERE, GROUP BY, HAVING và window functions

Theo mô hình xử lý logic SQL, các hàm cửa sổ được đánh giá sau bước hình thành tập dòng cho SELECT ở query block đó. Vì vậy, trong đa số DBMS:

- Không dùng trực tiếp **FIRST_VALUE/LAST_VALUE/NTH_VALUE** trong WHERE cùng cấp.
- Không dùng trực tiếp chúng trong HAVING như điều kiện trên từng dòng trước window.
- Có thể dùng trong SELECT và, theo các giới hạn của DBMS, ORDER BY.
- Nếu cần lọc theo kết quả hàm cửa sổ, dùng **CTE hoặc bảng dẫn xuất**.

### 23.1. Lọc giao dịch có tiền khác giá trị đầu tiên của khách

~~~sql
WITH x AS (
    SELECT
        g.*,
        FIRST_VALUE(so_tien) OVER (
            PARTITION BY ma_khach
            ORDER BY ngay_giao_dich, ma_giao_dich
            ROWS BETWEEN UNBOUNDED PRECEDING
                     AND UNBOUNDED FOLLOWING
        ) AS tien_dau
    FROM giao_dich g
)
SELECT *
FROM x
WHERE so_tien IS DISTINCT FROM tien_dau;
~~~

**IS DISTINCT FROM** xử lý so sánh hai NULL theo ngữ nghĩa null-safe ở DBMS hỗ trợ như PostgreSQL. Nếu DBMS không có cú pháp này hoặc có cú pháp khác, cần viết điều kiện so sánh NULL riêng. Không thay bằng **so_tien <> tien_dau** nếu yêu cầu phân biệt giá trị NULL và không NULL.

### 23.2. GROUP BY thay đổi tập đầu vào của window

Nếu trước khi gọi window function bạn GROUP BY theo khách và tháng, thì **dòng** mà FIRST_VALUE thấy có thể là **một dòng tổng hợp mỗi tháng**, không còn là từng giao dịch gốc.

Ví dụ ý định: “Doanh thu tháng đầu và tháng cuối của mỗi khách”:

1. Tổng hợp doanh thu theo **khách–tháng**.
2. Dùng FIRST_VALUE/LAST_VALUE trên kết quả **đã tổng hợp** theo thứ tự tháng.

Không được dùng cùng cú pháp nhưng nhầm đó là tiền của **giao dịch đầu/cuối**. Cần xác định rõ *grain* của nguồn đưa vào window.

## 24. NULL trong ORDER BY khác NULL trong biểu thức giá trị

Có hai vị trí khác nhau có thể chứa NULL:

1. **ORDER BY expression** có NULL: quyết định dòng nằm ở đầu hay cuối thứ tự.
2. **value expression** có NULL: quyết định giá trị FIRST/LAST/NTH trả về.

Ví dụ:

~~~sql
FIRST_VALUE(so_tien) OVER (
    PARTITION BY ma_khach
    ORDER BY ngay_giao_dich, ma_giao_dich
    ROWS BETWEEN UNBOUNDED PRECEDING
             AND UNBOUNDED FOLLOWING
)
~~~

Nếu **so_tien NULL** ở dòng đầu nhưng ngày không NULL, FIRST_VALUE mặc định trả NULL. Nếu **ngay_giao_dich NULL**, vấn đề còn nằm ở thứ tự: một số DBMS mặc định đưa NULL lên đầu khi ASC, số khác đưa xuống cuối.

### 24.1. Đặt quy tắc NULL trong thứ tự tường minh

Một mẫu khả chuyển tương đối:

~~~sql
ORDER BY
    CASE WHEN ngay_giao_dich IS NULL THEN 1 ELSE 0 END,
    ngay_giao_dich,
    ma_giao_dich
~~~

Các dòng ngày không NULL được ưu tiên trước, ngày NULL đứng sau. Nếu DBMS hỗ trợ **NULLS FIRST / NULLS LAST** trong ORDER BY của window, có thể dùng cú pháp đó theo phiên bản.

**Quan trọng:** chuyển ngày NULL xuống cuối **không** đồng nghĩa bỏ qua số tiền NULL. Hai quy tắc này độc lập.

## 25. NTH_VALUE và vị trí động do người dùng chọn

Giả sử màn hình cho phép chọn **N = 1, 2, 3, ...**. Về nghiệp vụ cần kiểm tra:

- N có phải số nguyên dương không?
- N có vượt số dòng của partition không?
- Đếm cả dòng NULL hay chỉ các giá trị không NULL?
- Đếm từ đầu hay từ cuối?
- Cần kết quả lặp trên mọi dòng hay chỉ một dòng?

Trong SQL, một số DBMS yêu cầu N là biểu thức có dạng/giá trị được cho phép và có thể từ chối N NULL hoặc <= 0. Với MySQL và các phiên bản khác, kiểm tra quy tắc tham số N thay vì ghép trực tiếp input thành SQL.

### 25.1. Tham số hóa qua JDBC

Ví dụ về cú pháp có tham số cho DBMS hỗ trợ NTH_VALUE:

~~~java
String sql = """
    SELECT
        ma_giao_dich,
        ma_khach,
        NTH_VALUE(so_tien, ?) OVER (
            PARTITION BY ma_khach
            ORDER BY ngay_giao_dich, ma_giao_dich
            ROWS BETWEEN UNBOUNDED PRECEDING
                     AND UNBOUNDED FOLLOWING
        ) AS so_tien_thu_n
    FROM giao_dich
    """;

int n = 3;
if (n < 1) {
    throw new IllegalArgumentException("N phai >= 1");
}

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setInt(1, n);
    try (ResultSet rs = ps.executeQuery()) {
        while (rs.next()) {
            // Đọc kết quả theo quy tắc DBMS và kiểu dữ liệu.
        }
    }
}
~~~

**Lưu ý:** khả năng dùng placeholder **?** ở vị trí N của NTH_VALUE là **phụ thuộc DBMS/driver/phiên bản**. Ví dụ minh họa cách triển khai khi sản phẩm hỗ trợ bind tại vị trí đó; nếu DBMS yêu cầu literal, ứng dụng phải **kiểm tra chặt và xây dựng danh sách giá trị cho phép**, không nối dữ liệu tùy ý của người dùng vào SQL.

### 25.2. N vượt số giao dịch

Nếu C chỉ có một giao dịch và N = 3, kết quả NTH_VALUE thường là NULL. Để thông báo “không đủ giao dịch”, cần một cột số lượng:

~~~sql
COUNT(*) OVER (PARTITION BY ma_khach) AS tong_so_giao_dich
~~~

Ứng dụng có thể phân biệt:

- tong_so_giao_dich < N → **chưa có dòng thứ N**.
- tong_so_giao_dich >= N và NTH_VALUE trả NULL → **dòng thứ N có giá trị NULL**, trong RESPECT NULLS.

Nếu dùng IGNORE NULLS, phải đếm **số giá trị biểu thức không NULL**, không chỉ COUNT(*).

## 26. Giả lập NTH_VALUE bỏ qua NULL

Một hướng khả chuyển hơn là đánh số riêng những dòng có giá trị **so_tien IS NOT NULL**, rồi mang giá trị thứ N tới các dòng cùng khách.

Ví dụ tìm **số tiền không NULL thứ hai** mỗi khách:

~~~sql
WITH so_tien_co_du_lieu AS (
    SELECT
        ma_khach,
        so_tien,
        ROW_NUMBER() OVER (
            PARTITION BY ma_khach
            ORDER BY ngay_giao_dich, ma_giao_dich
        ) AS rn_khong_null
    FROM giao_dich
    WHERE so_tien IS NOT NULL
),
gia_tri_thu_hai AS (
    SELECT
        ma_khach,
        so_tien
    FROM so_tien_co_du_lieu
    WHERE rn_khong_null = 2
)
SELECT
    g.ma_giao_dich,
    g.ma_khach,
    g.so_tien,
    t.so_tien AS tien_khong_null_thu_hai
FROM giao_dich g
LEFT JOIN gia_tri_thu_hai t
    ON t.ma_khach = g.ma_khach
ORDER BY g.ma_khach, g.ngay_giao_dich, g.ma_giao_dich;
~~~

Với dữ liệu:

- A có dãy không NULL **100, 300, 400** → thứ hai là **300**.
- B có dãy không NULL **200, 300** → thứ hai là **300**.
- C chỉ có **500** → thứ hai không tồn tại, kết quả NULL.

Cách này mô phỏng **NTH_VALUE(..., 2 IGNORE NULLS) trên full partition** nếu so khớp partition và thứ tự như ví dụ. Nó không tương đương với một NTH_VALUE trên **frame trượt theo dòng hiện tại**, bởi vì CTE đã lấy giá trị thứ hai trong **toàn bộ partition**.

### 26.1. Khóa partition có thể NULL

Trong ví dụ, **ma_khach NOT NULL**. Nếu ma_khach có NULL và PARTITION BY gộp các dòng NULL thành một nhóm, LEFT JOIN bằng dấu **=** sẽ không nối các nhóm NULL. Khi đó cần điều kiện null-safe phù hợp DBMS hoặc thiết kế lại truy vấn bằng aggregate window.

## 27. FIRST_VALUE IGNORE NULLS với frame trượt: không dùng mẹo sai

Giả sử cần **giá trị không NULL đầu tiên trong ba giao dịch gần nhất**, chứ không phải giá trị không NULL đầu tiên của toàn khách.

Frame:

~~~sql
ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
~~~

Nếu chuyển NULL xuống cuối **toàn partition** bằng CASE trong ORDER BY, bạn đã **thay đổi tập các dòng trong frame trượt**. Kết quả không còn là “ba giao dịch gần nhất theo thời gian”.

Cách đúng cần giữ nguyên frame thời gian rồi áp dụng **IGNORE NULLS trên chính frame đó** nếu DBMS hỗ trợ. Nếu không, phải thiết kế thuật toán khác giữ đúng phạm vi mỗi frame, ví dụ:

- CTE đánh số dòng và truy vấn tương quan chỉ lấy các dòng có số thứ tự từ rn−2 đến rn.
- Lateral join / APPLY (ở hệ hỗ trợ) để lấy giá trị đầu tiên không NULL trong đúng đoạn hàng.
- Một biểu thức phân tích khác đã chứng minh tương đương theo DBMS.

**Nguyên tắc:** thủ thuật “sắp NULL xuống cuối” rất hữu ích khi chọn một giá trị của **toàn partition**, nhưng không tự bảo toàn ngữ nghĩa các **khung động**.

## 28. So sánh với LAG, LEAD, ROW_NUMBER và RANK

| Hàm | Trả lời câu hỏi | Phụ thuộc frame? |
|---|---|---|
| FIRST_VALUE(expr) | Giá trị đầu của frame | Có |
| LAST_VALUE(expr) | Giá trị cuối của frame | Có |
| NTH_VALUE(expr,n) | Giá trị thứ n của frame | Có |
| LAG(expr,k) | Giá trị k dòng trước dòng hiện tại theo thứ tự | Hành vi riêng; không diễn giải như FIRST/LAST của frame |
| LEAD(expr,k) | Giá trị k dòng sau dòng hiện tại | Hành vi riêng |
| ROW_NUMBER() | Số thứ tự duy nhất của dòng trong partition | Theo thứ tự, không chọn giá trị nth từ frame |
| RANK() | Hạng có khoảng trống khi đồng hạng | Theo peer group |
| DENSE_RANK() | Hạng không có khoảng trống khi đồng hạng | Theo peer group |

### 28.1. NTH_VALUE không phải RANK

Giả sử các số tiền theo thứ tự giảm dần là:

~~~text
500, 500, 300, 200
~~~

**NTH_VALUE(so_tien,2)** theo thứ tự tiền giảm dần trả **500** vì dòng thứ hai cũng mang 500.

Nhưng **DENSE_RANK = 2** chỉ giá trị **300** vì hạng phân biệt thứ hai là 300.

### 28.2. NTH_VALUE không phải LEAD

Trên khách A:

- NTH_VALUE(so_tien,3) full frame = 300 **ở mọi dòng**.
- LEAD(so_tien,1) ở dòng 101 trả giá trị dòng 102 là NULL; ở dòng 102 trả 300; ở dòng 103 trả 400; ở dòng 104 không có dòng tiếp theo nên trả NULL nếu không có giá trị mặc định.

NTH_VALUE cố định một **vị trí trong frame**; LEAD tìm một **vị trí tương đối so với dòng hiện tại**.

## 29. Hiệu năng và khả năng sử dụng chỉ mục

Các hàm cửa sổ thường cần sắp xếp hoặc duyệt dữ liệu theo:

~~~sql
PARTITION BY ma_khach
ORDER BY ngay_giao_dich, ma_giao_dich
~~~

Một chỉ mục có thể hữu ích trên:

~~~sql
CREATE INDEX idx_giao_dich_khach_ngay_ma
ON giao_dich (ma_khach, ngay_giao_dich, ma_giao_dich);
~~~

Khả năng dùng chỉ mục phụ thuộc DBMS, số dòng, điều kiện WHERE và kế hoạch thực thi. Chỉ mục này **không bảo đảm mọi truy vấn window đều tránh SORT**.

### 29.1. Frame full partition có thể cần nhìn trước tương lai

Để tính LAST_VALUE toàn partition cho dòng đầu, DBMS cần biết dòng cuối của partition. Một kế hoạch có thể phải giữ dữ liệu đệm hoặc xử lý sắp xếp/partition. Mức tốn tài nguyên phụ thuộc độ rộng hàng, số dòng và bộ tối ưu.

### 29.2. Tránh tính nhiều window khác nhau không cần thiết

Nếu SELECT có nhiều hàm với cùng PARTITION/ORDER/frame, dùng **WINDOW clause** khi hệ quản trị hỗ trợ hoặc biểu thức OVER nhất quán để bộ tối ưu có cơ hội dùng chung xử lý. Nếu khác thứ tự ASC/DESC, hệ có thể cần thêm các bước sắp xếp.

### 29.3. Tối ưu đúng nghiệp vụ

Nếu cần **mỗi khách chỉ một giao dịch mới nhất**, truy vấn dùng ROW_NUMBER rồi rn=1, hoặc cơ chế truy vấn top-per-group khác, có thể đơn giản hơn việc tính LAST_VALUE trên **mọi giao dịch** rồi DISTINCT.

Nếu cần **lặp giá trị đầu/cuối trên mọi giao dịch** để tính chênh lệch, FIRST_VALUE/LAST_VALUE là công cụ tự nhiên.

### 29.4. Đừng bỏ khóa phá hòa vì muốn truy vấn nhanh

Bỏ **ma_giao_dich** khỏi ORDER BY có thể thay đổi thứ tự khi cùng ngày, khiến kết quả FIRST/LAST/NTH không ổn định. Hiệu năng phải được cải thiện bằng thiết kế chỉ mục và kế hoạch phù hợp, không đánh đổi tính xác định nếu nghiệp vụ cần một giá trị rõ ràng.

## 30. Tình huống thực tế: thay đổi từ giao dịch đầu tới cuối

Giả sử cần biết chênh lệch tiền giữa giao dịch đầu và cuối của mỗi khách, nhưng vẫn hiển thị mọi giao dịch:

~~~sql
WITH x AS (
    SELECT
        ma_giao_dich,
        ma_khach,
        ngay_giao_dich,
        so_tien,
        FIRST_VALUE(so_tien) OVER (
            PARTITION BY ma_khach
            ORDER BY ngay_giao_dich, ma_giao_dich
            ROWS BETWEEN UNBOUNDED PRECEDING
                     AND UNBOUNDED FOLLOWING
        ) AS tien_dau,
        LAST_VALUE(so_tien) OVER (
            PARTITION BY ma_khach
            ORDER BY ngay_giao_dich, ma_giao_dich
            ROWS BETWEEN UNBOUNDED PRECEDING
                     AND UNBOUNDED FOLLOWING
        ) AS tien_cuoi
    FROM giao_dich
)
SELECT
    ma_giao_dich,
    ma_khach,
    so_tien,
    tien_dau,
    tien_cuoi,
    tien_cuoi - tien_dau AS chenh_lech
FROM x
ORDER BY ma_khach, ma_giao_dich;
~~~

Với khách A: **tien_dau = 100**, **tien_cuoi = 400**, chênh lệch **300**. Với khách B: **tien_dau = NULL**, **tien_cuoi = 300**, nên **chenh_lech = NULL** theo phép trừ có NULL.

Không tự dùng COALESCE(tien_dau,0) để biến NULL thành số 0 nếu giá trị đầu **thực sự chưa biết**. Điều đó sẽ khiến báo cáo cho chênh lệch 300 nhưng không phản ánh dữ liệu thực tế.

### 30.1. Chênh lệch giữa giá trị có dữ liệu đầu/cuối

Nếu nghiệp vụ muốn bỏ qua các giao dịch có so_tien NULL, cần dùng **IGNORE NULLS** ở DBMS hỗ trợ hoặc mô phỏng chọn hai dòng không NULL đầu/cuối. Khi đó B có giá trị đầu có dữ liệu = 200, cuối có dữ liệu = 300, chênh lệch = 100.

Hai báo cáo có ý nghĩa khác nhau:

- **Giá trị của giao dịch đầu:** có thể NULL.
- **Giá trị đầu tiên được ghi nhận không NULL:** có thể nằm ở giao dịch thứ hai hoặc muộn hơn.

Không đặt cùng một tên cột báo cáo cho cả hai mà không giải thích.

## 31. Tình huống thực tế: giá trị thứ N trong lịch sử sự kiện

Một hệ thống theo dõi trạng thái cần lấy **trạng thái tại lần thay đổi thứ ba** của mỗi thiết bị.

Giả sử bảng **lich_su_trang_thai**:

~~~text
id_su_kien
ma_thiet_bi
thoi_diem
trang_thai
~~~

Nếu DBMS hỗ trợ NTH_VALUE, dùng:

~~~sql
SELECT
    ma_thiet_bi,
    id_su_kien,
    NTH_VALUE(trang_thai, 3) OVER (
        PARTITION BY ma_thiet_bi
        ORDER BY thoi_diem, id_su_kien
        ROWS BETWEEN UNBOUNDED PRECEDING
                 AND UNBOUNDED FOLLOWING
    ) AS trang_thai_lan_thu_ba
FROM lich_su_trang_thai;
~~~

Bài toán này có vài điểm phải xác định:

1. **Lần thứ ba** tính cả trạng thái NULL không?
2. Hai sự kiện có cùng thời điểm thì sự kiện nào trước? Dùng id_su_kien hay một sequence thực sự?
3. Một thiết bị chỉ có hai sự kiện thì biểu diễn kết quả không đủ dữ liệu ra sao?
4. Nếu lịch sử chứa sự kiện được ghi lại trễ, thứ tự **thoi_diem_su_kien** có khác **thoi_diem_nhap** không?
5. Nếu cần đúng một dòng mỗi thiết bị, có nên chọn hàng thứ ba trực tiếp bằng ROW_NUMBER rồi lọc, thay vì lặp giá trị NTH lên mọi dòng?

Các câu hỏi này quyết định tính đúng nghiệp vụ nhiều hơn việc thuộc lòng cú pháp.

## 32. Những sai lầm dễ mắc

| Ngộ nhận hoặc lỗi | Vấn đề | Cách xử lý |
|---|---|---|
| “LAST_VALUE luôn lấy cuối partition.” | Hàm lấy cuối **frame hiện tại** | Nêu full frame nếu muốn toàn partition |
| “FIRST_VALUE là MIN.” | Dòng đầu theo ORDER BY không phải giá trị nhỏ nhất | Chọn đúng hàm theo câu hỏi |
| “NTH_VALUE là giá trị phân biệt lớn thứ N.” | NTH đếm dòng theo frame, thường tính cả trùng | Nếu muốn distinct rank, dùng kỹ thuật hạng phù hợp |
| Bỏ PARTITION BY | Trộn khách/thiết bị khác nhau | Partition theo khóa nghiệp vụ |
| Bỏ ORDER BY hoặc ORDER BY chưa duy nhất | “Đầu/cuối/thứ N” không xác định | Nêu thứ tự và khóa phá hòa |
| Chỉ ORDER BY ở SELECT ngoài | Không quyết định thứ tự trong window | Thêm ORDER BY vào OVER |
| Dùng frame mặc định cho LAST_VALUE | Trả giá trị cuối đến CURRENT ROW/peer | ROWS UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING |
| Nghĩ ROWS và RANGE giống nhau | RANGE xét peer group, ROWS xét dòng | Xác định frame mode |
| Dùng RANGE chỉ ORDER BY ngày có nhiều dòng cùng ngày | LAST_VALUE có thể chọn dòng peer không ổn định | Khóa phụ duy nhất và frame rõ |
| “IGNORE NULLS nghĩa là bỏ dòng khỏi SELECT.” | Thay đổi chỉ cách chọn giá trị | Đọc NULL treatment đúng |
| Nghĩ mọi DBMS có IGNORE NULLS | PostgreSQL/SQLite/MySQL 8 có hạn chế | Kiểm tra tài liệu phiên bản |
| Nghĩ MySQL FROM LAST chắc chắn chạy | Một số cú pháp được parse nhưng chưa thực thi | Đảo ORDER BY + full frame |
| Gọi NTH_VALUE trong SQL Server phổ biến | Không có hàm trực tiếp | ROW_NUMBER + CASE/CTE |
| N = 0 | NTH thường đánh số từ 1 | Kiểm tra N nguyên dương |
| Kết quả NTH NULL nghĩa là thiếu dòng | Có thể dòng N tồn tại nhưng expr NULL | COUNT(*) + ROW_NUMBER để phân biệt |
| Dùng MAX(so_tien) thay NTH | MAX không chọn dòng vị trí thứ N | Xếp hạng theo vị trí |
| Dùng phép MAX trên kiểu không hỗ trợ | Mô phỏng NTH bằng MAX có thể lỗi kiểu | JOIN lại dòng rn = N |
| Dùng mẹo sắp NULL cuối trên frame trượt | Đã đổi cấu trúc frame | Giữ frame gốc, dùng cơ chế bỏ NULL đúng |
| GROUP BY rồi tưởng window còn thấy từng giao dịch | Window đang thấy dòng tổng hợp | Xác định grain của nguồn |
| Dùng WHERE trực tiếp với window function | Window chưa có ở bước WHERE cùng cấp | CTE/bảng dẫn xuất |
| NTH từ cuối nhưng chỉ đảo một khóa sort | Thứ tự không đảo hoàn toàn | Đảo toàn bộ khóa và NULL order |
| Bỏ qua NULL trong khóa ORDER BY | Dòng có ngày NULL có thể đứng khác nhau theo DBMS | NULLS FIRST/LAST hoặc CASE |
| Đồng thời đọc dữ liệu đang thay đổi | Kết quả đầu/cuối có thể khác snapshot | Chọn transaction/snapshot phù hợp |
| Nghĩ window tự trả một dòng mỗi partition | Window vẫn giữ từng dòng | Lọc ROW_NUMBER ngoài hoặc chọn tập kết quả khác |

## 33. Bộ ca kiểm thử khuyến nghị

Khi phát triển một báo cáo dùng FIRST/LAST/NTH, nên thử ít nhất:

| Trường hợp | Dữ liệu thử | Điều cần kiểm chứng |
|---|---|---|
| Một dòng | Khách C chỉ có 1 giao dịch | FIRST=LAST; NTH(2/3)=NULL |
| Hai dòng | Một khách chỉ có 2 giao dịch | NTH(3)=NULL |
| Ba dòng | Ba giao dịch ngày khác nhau | NTH(3) chọn đúng dòng thứ ba |
| Dòng đầu NULL | Khách B | FIRST RESPECT=NULL; IGNORE=200 |
| Dòng N NULL | Khách A, N=2 | Có vị trí N nhưng giá trị NULL |
| Dòng cuối NULL | Thêm giao dịch cuối thiếu tiền | LAST RESPECT khác LAST IGNORE |
| Thời điểm trùng | Khách A, 102 và 103 cùng ngày | Cần khóa phá hòa |
| N lớn hơn số dòng | N=10 cho khách A | NULL do thiếu vị trí |
| N=1 | Hàm NTH so với FIRST | Kết quả trùng khi cùng frame/NULL treatment |
| N từ cuối | N=2 từ cuối khách A | Trả 300 |
| Frame mặc định | Bỏ ROWS ... | LAST có thể không phải cuối partition |
| Frame trượt | ROWS 2 PRECEDING | Kết quả đổi theo dòng |
| Nhiều partition | A, B, C | Không trộn khách |
| PARTITION BY NULL | Khóa nhóm thiếu | Nhóm NULL và JOIN lại cần null-safe |
| Giá trị đồng hạng | Hai dòng cùng số tiền | Không nhầm thứ N dòng với hạng phân biệt |
| Timestamp có múi giờ | Hai nguồn thời gian khác vùng | Cần chuẩn hóa thứ tự sự kiện |
| Kiểu dữ liệu chuỗi | FIRST_VALUE(trang_thai) | Không dùng MAX giả lập khi ngữ nghĩa/kiểu không phù hợp |

### 33.1. Kiểm tra kết quả từ mẫu bài

Với full frame và thứ tự **ngay_giao_dich, ma_giao_dich**:

~~~text
A:
first = 100
last  = 400
nth2  = NULL
nth3  = 300

B:
first = NULL
last  = 300
nth2  = 200
nth3  = 300

C:
first = 500
last  = 500
nth2  = NULL
nth3  = NULL
~~~

Hãy dùng bộ giá trị này để dự đoán đầu ra trước khi chạy SQL. Nếu nhận kết quả khác, kiểm tra lại **ORDER BY, frame, NULL treatment và dữ liệu đã nạp**, không chỉ tên hàm.

## 34. Bài tập tự luyện

### Bài 1 — Chọn hàm đúng

Muốn lấy **số tiền của giao dịch đầu tiên theo ngày** của mỗi khách và lặp số tiền đó trên từng giao dịch, nên dùng MIN, FIRST_VALUE hay ROW_NUMBER?

<details>
<summary>Gợi ý đáp án</summary>

**FIRST_VALUE(so_tien) OVER(PARTITION BY ma_khach ORDER BY ngay_giao_dich, ma_giao_dich ...)** với frame phù hợp. MIN lấy số nhỏ nhất; ROW_NUMBER có thể giúp chọn dòng đầu nếu cần, nhưng không trực tiếp lặp số tiền đầu trên mọi dòng như FIRST_VALUE.

</details>

### Bài 2 — LAST_VALUE và khung mặc định

Trong khách A, nếu ORDER BY ngày/mã xác định và dùng frame từ đầu tới CURRENT ROW, LAST_VALUE(so_tien) ở giao dịch 101 bằng bao nhiêu?

<details>
<summary>Gợi ý đáp án</summary>

**100**, vì frame của giao dịch 101 chỉ chứa dòng đầu. Muốn lấy **400** (cuối toàn partition), dùng full frame tới **UNBOUNDED FOLLOWING**.

</details>

### Bài 3 — FIRST_VALUE khi đầu là NULL

Khách B có số tiền theo thứ tự NULL, 200, 300. FIRST_VALUE RESPECT NULLS trả gì ở full frame?

<details>
<summary>Gợi ý đáp án</summary>

**NULL**, vì dòng đầu là giao dịch có số tiền NULL.

</details>

### Bài 4 — IGNORE NULLS

Vẫn khách B: FIRST_VALUE IGNORE NULLS full frame trả gì?

<details>
<summary>Gợi ý đáp án</summary>

**200**, là số tiền không NULL đầu tiên theo thứ tự.

</details>

### Bài 5 — NTH_VALUE thứ ba

Khách A có tiền 100, NULL, 300, 400. NTH_VALUE(so_tien,3) RESPECT NULLS full frame trả gì?

<details>
<summary>Gợi ý đáp án</summary>

**300**, tại dòng thứ ba.

</details>

### Bài 6 — NTH thứ hai là NULL

Khách A có bốn giao dịch. Tại sao NTH_VALUE(so_tien,2) full frame vẫn trả NULL?

<details>
<summary>Gợi ý đáp án</summary>

Vì dòng thứ hai **tồn tại** nhưng giá trị so_tien của dòng đó là NULL. Không thể kết luận thiếu dòng thứ hai từ giá trị NTH_VALUE alone; cần COUNT/ROW_NUMBER.

</details>

### Bài 7 — NTH thứ N vượt số dòng

Khách C chỉ có một giao dịch. NTH_VALUE(so_tien,3) full frame trả gì?

<details>
<summary>Gợi ý đáp án</summary>

**NULL**, vì frame không có dòng thứ ba.

</details>

### Bài 8 — NTH thứ hai từ cuối

Khách A theo thứ tự ngày/mã có tiền 100, NULL, 300, 400. Giá trị thứ hai từ cuối là bao nhiêu?

<details>
<summary>Gợi ý đáp án</summary>

**300**. Nếu DBMS không có FROM LAST, dùng NTH_VALUE(so_tien,2) với **ORDER BY ngày DESC, mã DESC** và full frame.

</details>

### Bài 9 — Đếm từ 0 hay 1?

NTH_VALUE(expr,1) dùng để lấy gì?

<details>
<summary>Gợi ý đáp án</summary>

Giá trị ở **dòng đầu của frame**, tương tự FIRST_VALUE với cùng thứ tự, frame và chính sách NULL. Vị trí N bắt đầu từ 1, không từ 0.

</details>

### Bài 10 — Tie-breaking

Hai giao dịch cùng thời điểm nhưng tiền khác nhau. Vì sao ORDER BY thoi_diem chưa đủ để đảm bảo FIRST_VALUE xác định?

<details>
<summary>Gợi ý đáp án</summary>

Vì hai dòng có **cùng khóa sắp xếp**, DBMS không có quy tắc chọn dòng nào đứng trước trong nhóm đồng hạng. Thêm khóa duy nhất/sequence phù hợp nghiệp vụ vào ORDER BY của OVER.

</details>

### Bài 11 — ROWS và RANGE

Với hai dòng cùng ngày, frame RANGE UNBOUNDED PRECEDING TO CURRENT ROW có thể chứa những dòng nào ở cận CURRENT ROW?

<details>
<summary>Gợi ý đáp án</summary>

Có thể chứa **tất cả các dòng peer cùng giá trị ORDER BY** tại ranh giới đó, không chỉ một dòng vật lý hiện tại. Đây là khác biệt so với ROWS.

</details>

### Bài 12 — Chọn frame toàn partition

Viết mệnh đề frame để LAST_VALUE luôn xét từ đầu đến cuối partition.

<details>
<summary>Gợi ý đáp án</summary>

~~~sql
ROWS BETWEEN UNBOUNDED PRECEDING
         AND UNBOUNDED FOLLOWING
~~~

Đi kèm PARTITION BY và ORDER BY đúng.

</details>

### Bài 13 — SQL Server và NTH_VALUE

Trong SQL Server phổ biến không có NTH_VALUE trực tiếp, cách nào giúp chọn dòng thứ ba của mỗi khách?

<details>
<summary>Gợi ý đáp án</summary>

Dùng **ROW_NUMBER() OVER(PARTITION BY ma_khach ORDER BY ngay_giao_dich, ma_giao_dich)** trong CTE, sau đó lọc **rn=3** và JOIN lại, hoặc dùng **MAX(CASE WHEN rn=3 THEN so_tien END) OVER(PARTITION BY ma_khach)** nếu kiểu dữ liệu phù hợp.

</details>

### Bài 14 — MySQL FROM LAST

Có nên mặc định NTH_VALUE(...,2) FROM LAST chạy trên mọi MySQL 8.0 không?

<details>
<summary>Gợi ý đáp án</summary>

**Không.** Một số phiên bản MySQL nhận cú pháp nhưng chưa thực thi FROM LAST. Có thể đảo ORDER BY hoàn chỉnh và dùng full frame để lấy vị trí từ cuối.

</details>

### Bài 15 — PostgreSQL IGNORE NULLS

Trong PostgreSQL phổ biến, có thể viết FIRST_VALUE(so_tien) IGNORE NULLS như Oracle không?

<details>
<summary>Gợi ý đáp án</summary>

**Không** theo khả năng hỗ trợ thông thường của PostgreSQL. Với full partition, có thể đặt dòng không NULL lên trước bằng ORDER BY CASE WHEN so_tien IS NULL THEN 1 ELSE 0 END, rồi theo thời gian. Không dùng mẹo này máy móc cho frame trượt.

</details>

### Bài 16 — SQL Server 2019 và 2022

Tùy chọn IGNORE NULLS cho FIRST_VALUE/LAST_VALUE được bổ sung vào SQL Server từ bản nào?

<details>
<summary>Gợi ý đáp án</summary>

**SQL Server 2022**. Nếu dùng bản cũ hơn, cần hướng xử lý khác và kiểm tra đúng phiên bản/compatibility.

</details>

### Bài 17 — LAG khác NTH_VALUE

Vì sao LAG(so_tien,2) không phải NTH_VALUE(so_tien,2)?

<details>
<summary>Gợi ý đáp án</summary>

LAG lấy **giá trị hai dòng trước dòng hiện tại**, còn NTH_VALUE lấy **giá trị dòng thứ hai của frame**. Vị trí tham chiếu và sự phụ thuộc frame khác nhau.

</details>

### Bài 18 — Câu hỏi phân tích tháng

Nếu GROUP BY ma_khach và tháng trước khi gọi FIRST_VALUE trên các dòng đã tổng hợp, hàm sẽ chọn gì?

<details>
<summary>Gợi ý đáp án</summary>

Nó chọn giá trị ở **dòng tổng hợp tháng đầu** theo thứ tự của partition, không phải tiền của một giao dịch cụ thể đầu tiên. Cần xác định grain đầu vào của window.

</details>

### Bài 19 — Khóa partition nullable

Một CTE dùng PARTITION BY ma_khach, trong đó ma_khach có thể NULL; sau đó JOIN lại theo **a.ma_khach = b.ma_khach**. Trường hợp nào có thể bị bỏ sót?

<details>
<summary>Gợi ý đáp án</summary>

Các dòng thuộc **partition ma_khach NULL**, vì PARTITION BY xem chúng chung một nhóm nhưng phép **NULL = NULL** trong JOIN không TRUE. Cần xử lý khóa NULL bằng điều kiện null-safe hoặc thiết kế khác phù hợp.

</details>

### Bài 20 — Tiền đầu/cuối và thiếu dữ liệu

Khách B có tiền NULL, 200, 300. Báo cáo chênh lệch “tiền cuối − tiền đầu” theo RESPECT NULLS bằng bao nhiêu?

<details>
<summary>Gợi ý đáp án</summary>

**NULL**, vì đầu là NULL nên phép trừ không biết kết quả. Nếu nghiệp vụ muốn chênh lệch **giữa giá trị không NULL đầu và cuối**, phải chọn 200 và 300 theo chính sách IGNORE NULLS/mô phỏng, khi đó chênh lệch là 100.

</details>

### Bài 21 — Frame trượt

Với khách A theo thứ tự 101,102,103,104 và frame ROWS BETWEEN 2 PRECEDING AND CURRENT ROW, ở dòng 104 frame gồm những dòng nào? FIRST_VALUE(so_tien) bằng bao nhiêu?

<details>
<summary>Gợi ý đáp án</summary>

Frame gồm **102, 103, 104**; FIRST_VALUE lấy tiền dòng 102 là **NULL** theo RESPECT NULLS.

</details>

### Bài 22 — Đếm giao dịch không NULL

Nếu muốn lấy **giá trị không NULL thứ ba** của khách A, kết quả là gì? Vì sao khác NTH_VALUE RESPECT NULLS thứ ba?

<details>
<summary>Gợi ý đáp án</summary>

Dãy không NULL của A là **100, 300, 400**, nên giá trị không NULL thứ ba là **400**. NTH_VALUE(...,3) RESPECT NULLS trả **300** vì nó tính cả dòng 102 NULL như vị trí thứ hai.

</details>

### Bài 23 — ORDER BY ngoài cùng

Truy vấn có ORDER BY ma_giao_dich ở cuối nhưng window chỉ ORDER BY ngay_giao_dich. Liệu điều đó có đủ phá hòa các giao dịch cùng ngày trong FIRST_VALUE?

<details>
<summary>Gợi ý đáp án</summary>

**Không.** ORDER BY cuối chỉ sắp xếp kết quả. Khóa phá hòa phải nằm trong ORDER BY của OVER.

</details>

### Bài 24 — Một dòng mỗi khách

Muốn lấy đúng **một giao dịch mới nhất mỗi khách**, hàm ROW_NUMBER có thể giúp như thế nào?

<details>
<summary>Gợi ý đáp án</summary>

Trong CTE, dùng **ROW_NUMBER() OVER(PARTITION BY ma_khach ORDER BY ngay_giao_dich DESC, ma_giao_dich DESC)** rồi ở query ngoài lọc **rn=1**. Cách đó chọn một dòng thật với toàn bộ cột của nó.

</details>

## 35. Quy trình chọn và kiểm tra các hàm giá trị trong dự án

Khi nhận một yêu cầu như “lấy số đo cuối”, “trạng thái đầu”, “giá trị thứ ba”, có thể làm theo các bước sau.

### Bước 1 — Xác định đơn vị nhóm

- Theo **khách hàng**, **thiết bị**, **tài khoản** hay **danh mục**?
- Nếu cùng khách trong nhiều năm cần xử lý riêng, partition theo **khách–năm** hay khách toàn lịch sử?
- Khóa partition có thể NULL không?
- Có nhiều hệ nguồn/tenant dẫn tới cùng mã nhưng khác đối tượng không?

### Bước 2 — Xác định thứ tự mang ý nghĩa nghiệp vụ

- Theo **ngày phát sinh**, **timestamp**, **thứ tự nhập**, **sequence nguồn** hay **mức ưu tiên**?
- Khi bằng nhau, dùng khóa nào phá hòa?
- Ngày/timestamp có thể NULL không? Đưa NULL lên đầu hay cuối?
- Dữ liệu nạp trễ có làm thay đổi thứ tự sự kiện lịch sử không?

### Bước 3 — Xác định frame

- **Toàn bộ partition:** full frame tới UNBOUNDED FOLLOWING.
- **Từ đầu đến hiện tại:** UNBOUNDED PRECEDING TO CURRENT ROW.
- **Một số dòng gần nhất:** ROWS N PRECEDING TO CURRENT ROW.
- **Theo giá trị/ngày và peer:** cân nhắc RANGE/GROUPS khi đúng nhu cầu.

### Bước 4 — Xác định chính sách NULL và N

- Giữ NULL như một vị trí (**RESPECT**) hay bỏ qua NULL của giá trị (**IGNORE**)?
- N là số thứ tự từ **1**; n vượt số dòng xử lý thế nào?
- N tính từ đầu hay từ cuối?
- Nếu hai dòng đồng thời điểm, cần một dòng hay nhiều dòng đồng hạng?

### Bước 5 — Kiểm tra khả năng hỗ trợ DBMS

- Có hàm **NTH_VALUE** hay cần ROW_NUMBER?
- Có **IGNORE NULLS** hoặc **FROM LAST** không?
- NULL treatment nằm trong/ngoài ngoặc hàm?
- Frame mặc định là gì?
- Kiểu cột và cách truyền tham số N có được hỗ trợ không?

### Bước 6 — Kiểm thử và đánh giá kế hoạch

Dùng dữ liệu có **một dòng, nhiều dòng, thiếu dòng thứ N, NULL ở đầu/cuối/vị trí N, timestamp trùng, nhiều partition, frame trượt**. Sau đó đánh giá kế hoạch thực thi, chỉ mục và số lượng dòng trung gian.

Một truy vấn chạy mà không lỗi cú pháp chưa chứng minh giá trị “đầu”, “cuối” hay “thứ N” là **đúng theo nghiệp vụ**.

## 36. Ghi nhớ cuối bài

1. **FIRST_VALUE** trả biểu thức ở **dòng đầu trong frame**, **LAST_VALUE** trả biểu thức ở **dòng cuối trong frame**, **NTH_VALUE** trả biểu thức ở **dòng thứ N trong frame**.
2. **PARTITION BY** xác định nhóm; **ORDER BY trong OVER** xác định trước/sau; **frame** xác định tập dòng mà hàm được nhìn tại mỗi dòng.
3. **LAST_VALUE với frame mặc định** thường không phải cuối toàn partition. Khi cần giá trị cuối cố định cho cả nhóm, nêu **ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING**.
4. **NTH_VALUE đánh số từ 1**. Trả NULL có thể do frame không đủ N dòng hoặc dòng N mang giá trị NULL.
5. **ROWS** theo vị trí dòng; **RANGE** có liên quan giá trị sắp xếp và peer group. Hai chế độ có thể khác nhau khi ORDER BY trùng.
6. **ORDER BY thiếu khóa phá hòa** làm giá trị đầu/cuối/thứ N có thể không xác định. ORDER BY cuối SELECT không khắc phục được.
7. **FIRST_VALUE không phải MIN**, **LAST_VALUE không phải MAX**, và **NTH_VALUE không phải giá trị lớn thứ N phân biệt** nếu không có quy tắc sắp xếp/loại trùng riêng.
8. **IGNORE NULLS** và **RESPECT NULLS** thay đổi vị trí giá trị được chọn; hỗ trợ cú pháp khác giữa DBMS.
9. **PostgreSQL, MySQL 8+, Oracle, SQLite** có NTH_VALUE trong những phiên bản phổ biến; **SQL Server phổ biến** cần mô phỏng bằng ROW_NUMBER và một phép chọn/join phù hợp.
10. **Oracle** hỗ trợ NTH_VALUE FROM LAST; MySQL 8.0 không nên giả định FROM LAST hoạt động dù có mô tả cú pháp. Đảo ORDER BY với full frame là phương án hữu ích khi thích hợp.
11. Khi dùng **frame trượt**, không tự thay IGNORE NULLS bằng mẹo sắp NULL xuống cuối trên toàn partition, vì điều đó có thể đổi tập dòng trong frame.
12. Hàm cửa sổ **giữ các dòng chi tiết**; muốn một dòng mỗi nhóm thường cần lọc ROW_NUMBER hoặc thiết kế lại truy vấn.
13. Một kết quả đúng phụ thuộc **định nghĩa thứ tự nghiệp vụ, khung, chính sách NULL, độ ổn định khi đồng hạng và phiên bản DBMS** hơn là chỉ thuộc cú pháp tên hàm.

### Tài liệu tham khảo theo hệ quản trị

Khi triển khai, đối chiếu tài liệu chính thức **đúng phiên bản đang chạy**, nhất là những mục window function syntax, window frame, navigation functions, NULL treatment và giá trị đồng hạng:

- **PostgreSQL Documentation:** *Window Functions*, *Window Function Calls*, *SELECT — WINDOW Clause*, *Tutorial on Window Functions*.
- **MySQL Reference Manual:** *Window Function Descriptions*, *NTH_VALUE()*, *Window Function Concepts and Syntax*, *Window Frame Specification*.
- **Microsoft Learn — Transact-SQL:** *FIRST_VALUE*, *LAST_VALUE*, *OVER Clause*, *ROW_NUMBER*, *IGNORE NULLS and RESPECT NULLS (SQL Server 2022+)*.
- **Oracle Database SQL Language Reference:** *FIRST_VALUE*, *LAST_VALUE*, *NTH_VALUE*, *Analytic Functions*, *Windowing Clause*.
- **SQLite Documentation:** *Window Functions*, *Frame Specifications*, *Built-in Window Functions*.
- **Google Cloud BigQuery / GoogleSQL:** *Navigation Functions*, *Window Function Calls*, *Window Frame Clause*.

**Câu hỏi cuối cùng cần luôn tự trả lời:** **“Ở dòng đang xét, hàm nhìn thấy những dòng nào, theo thứ tự nào, có tính NULL không, và cần lấy giá trị tại vị trí nào?”**. Khi trả lời được bốn điểm đó, bạn sẽ dự đoán đúng phần lớn kết quả FIRST_VALUE, LAST_VALUE và NTH_VALUE trên các hệ quản trị SQL.
