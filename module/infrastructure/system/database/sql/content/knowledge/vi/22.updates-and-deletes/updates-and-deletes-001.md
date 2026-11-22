# UPDATE với điều kiện lọc và biểu thức tính giá trị mới trong SQL

> **Module:** Database SQL  
> **Chương:** Cập nhật và xóa  
> **Bài học:** UPDATE với điều kiện lọc và biểu thức tính giá trị mới

Dữ liệu trong ứng dụng luôn thay đổi: giá sản phẩm tăng hoặc giảm, tồn kho được điều chỉnh, đơn hàng chuyển trạng thái, địa chỉ được cập nhật, số dư thay đổi và các bản ghi nghiệp vụ được hiệu chỉnh. Lệnh **UPDATE** cho phép thay đổi giá trị cột của những hàng đã tồn tại trong bảng. Lệnh này rất mạnh nhưng cũng nguy hiểm: thiếu một điều kiện WHERE có thể sửa cả bảng; một biểu thức số học sai có thể tạo giá âm; một phép cập nhật dựa trên giá trị cũ có thể bị tính hai lần nếu ứng dụng retry; và nhiều giao dịch đồng thời có thể gây mất cập nhật.

Bài học tập trung vào hai quyết định không thể tách rời:

1. **Hàng nào được phép sửa?** — Điều kiện WHERE, khóa định danh, trạng thái, NULL, thời gian và phạm vi quyền.
2. **Giá trị mới được xác định thế nào?** — Hằng số, giá trị cũ, biểu thức số học, CASE, COALESCE, kết quả subquery hoặc dữ liệu bảng khác.

Các ví dụ sửa dữ liệu phải được thực hành trong cơ sở dữ liệu **thử nghiệm**, không chạy trực tiếp trên hệ thống production.

---

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

- Viết đúng cú pháp cơ bản **UPDATE ... SET ... WHERE ...** và phân biệt với INSERT, DELETE.
- Dùng WHERE để lựa chọn chính xác hàng theo khóa, trạng thái, nhóm, khoảng thời gian và điều kiện kết hợp.
- Cập nhật một hoặc nhiều cột bằng giá trị cố định hoặc biểu thức dựa trên giá trị đang lưu.
- Sử dụng CASE, COALESCE, ROUND và hàm ngày giờ trong SET.
- Hiểu hành vi NULL và logic ba giá trị trong UPDATE.
- Viết UPDATE với EXISTS, NOT EXISTS, scalar subquery và UPDATE JOIN/FROM theo phương ngữ.
- Phòng tránh lỗi UPDATE từ bảng nguồn có nhiều dòng khớp một hàng đích.
- Xem trước tập hàng và giá trị mới, kiểm tra số hàng ảnh hưởng, dùng COMMIT/ROLLBACK.
- Phòng tránh lost update bằng cập nhật tương đối tại DB và optimistic locking.
- Biết khi nào cần ràng buộc, audit, phiên bản dữ liệu, idempotency và giao dịch.
- Phân biệt cú pháp PostgreSQL, MySQL, SQL Server, Oracle và SQLite.
- Thực hiện UPDATE tham số hóa từ Java/JDBC.
- Thiết kế test cho giá trị biên, NULL, số âm, nhiều hàng, lỗi constraint và thao tác đồng thời.

## 2. Cú pháp cơ bản và ý nghĩa

Mẫu SQL:

~~~sql
UPDATE ten_bang
SET ten_cot_1 = bieu_thuc_1,
    ten_cot_2 = bieu_thuc_2
WHERE dieu_kien;
~~~

- **UPDATE ten_bang** xác định bảng có các hàng cần sửa.
- **SET** định nghĩa giá trị mới của một hoặc nhiều cột.
- **WHERE** chọn hàng thỏa điều kiện.
- **Bieu_thuc** có thể là literal, công thức trên cột cũ, CASE, hàm hoặc subquery mà DBMS cho phép.

Ví dụ:

~~~sql
UPDATE san_pham
SET gia_ban = 120000
WHERE ma_san_pham = 'P01';
~~~

Câu này đặt giá P01 thành **120000**, bất kể giá trước đó.

Trong khi:

~~~sql
UPDATE san_pham
SET gia_ban = gia_ban * 1.10
WHERE ma_san_pham = 'P01';
~~~

tăng giá P01 **10% tính từ giá đang lưu**.

### 2.1. UPDATE không tự tạo hàng

Nếu không có P99:

~~~sql
UPDATE san_pham
SET gia_ban = 50000
WHERE ma_san_pham = 'P99';
~~~

thường không sửa hàng nào. Muốn “chưa có thì thêm, có rồi thì sửa”, cần cơ chế UPSERT/MERGE theo DBMS.

### 2.2. UPDATE có thể tác động nhiều hàng

~~~sql
UPDATE san_pham
SET trang_thai = 'TAM_NGUNG'
WHERE ma_danh_muc = 'A';
~~~

Nếu có 500 hàng thuộc A, có thể cập nhật 500 hàng. SQL không yêu cầu UPDATE chỉ sửa một hàng.

| Lệnh | Hành động |
|---|---|
| INSERT | Thêm bản ghi |
| UPDATE | Sửa bản ghi đã có |
| DELETE | Xóa bản ghi |
| MERGE/UPSERT theo DBMS | Phối hợp chèn và sửa theo điều kiện khớp |

## 3. Chuẩn bị bảng và dữ liệu mẫu

Giả sử bảng:

~~~sql
CREATE TABLE san_pham (
    ma_san_pham VARCHAR(20) PRIMARY KEY,
    ten_san_pham VARCHAR(100) NOT NULL,
    ma_danh_muc VARCHAR(20),
    gia_ban DECIMAL(12, 2) NOT NULL,
    so_luong_ton INTEGER NOT NULL,
    trang_thai VARCHAR(20) NOT NULL,
    phien_ban INTEGER NOT NULL DEFAULT 1,
    ngay_cap_nhat TIMESTAMP,
    CONSTRAINT ck_gia CHECK (gia_ban >= 0),
    CONSTRAINT ck_ton CHECK (so_luong_ton >= 0)
);
~~~

Dữ liệu thử:

| Mã | Tên | Danh mục | Giá | Tồn kho | Trạng thái | Phiên bản |
|---|---|---|---:|---:|---|---:|
| P01 | Bút bi | A | 100000.00 | 10 | ACTIVE | 1 |
| P02 | Sổ tay | A | 200000.00 | 0 | ACTIVE | 1 |
| P03 | Thước | B | 50000.00 | 20 | ACTIVE | 1 |
| P04 | Hộp đựng | B | 80000.00 | 4 | STOP | 1 |
| P05 | Hàng khác | NULL | 0.00 | 3 | ACTIVE | 1 |

Một cách nạp dữ liệu trên DBMS hỗ trợ INSERT nhiều nhóm VALUES:

~~~sql
INSERT INTO san_pham (
    ma_san_pham, ten_san_pham, ma_danh_muc,
    gia_ban, so_luong_ton, trang_thai, phien_ban
)
VALUES
 ('P01', 'Bút bi',   'A', 100000.00, 10, 'ACTIVE', 1),
 ('P02', 'Sổ tay',   'A', 200000.00,  0, 'ACTIVE', 1),
 ('P03', 'Thước',    'B',  50000.00, 20, 'ACTIVE', 1),
 ('P04', 'Hộp đựng', 'B',  80000.00,  4, 'STOP',   1),
 ('P05', 'Hàng khác',NULL,     0.00, 3, 'ACTIVE', 1);
~~~

Oracle 19c có cách nạp nhiều dòng khác, ví dụ INSERT ALL hoặc từng INSERT. Để dự đoán kết quả trong các phần sau, **mỗi ví dụ độc lập được tính từ bảng ban đầu**, trừ khi ghi rõ các thao tác nối tiếp.

Kiểm tra dữ liệu:

~~~sql
SELECT ma_san_pham, gia_ban, so_luong_ton, trang_thai
FROM san_pham
ORDER BY ma_san_pham;
~~~

## 4. Gán giá trị cố định cho một cột

Câu cập nhật đơn giản:

~~~sql
UPDATE san_pham
SET trang_thai = 'ACTIVE'
WHERE ma_san_pham = 'P04';
~~~

P04 từ STOP thành ACTIVE.

Cột không được liệt kê trong SET không bị câu lệnh gán lại trực tiếp. Tuy nhiên, **trigger**, cột tự động cập nhật, cơ chế audit hoặc hiệu ứng của ràng buộc có thể phát sinh thay đổi bổ sung theo thiết kế DBMS.

### 4.1. Chọn khóa đáng tin cậy

Để sửa một sản phẩm, ưu tiên mã định danh:

~~~sql
WHERE ma_san_pham = 'P04'
~~~

Không nên chỉ tìm theo tên hiển thị:

~~~sql
WHERE ten_san_pham = 'Hộp đựng'
~~~

vì tên có thể trùng, đổi hoặc chứa khác biệt về dấu và collation.

### 4.2. UPDATE với điều kiện không thỏa

Nếu P01 đang ACTIVE:

~~~sql
UPDATE san_pham
SET trang_thai = 'ACTIVE'
WHERE ma_san_pham = 'P01'
  AND trang_thai = 'STOP';
~~~

không có hàng thỏa. Câu lệnh có thể chạy thành công về cú pháp mà **không đổi dữ liệu**.

## 5. Nguy cơ lớn nhất: quên WHERE

Câu sau hợp lệ ở nhiều hệ:

~~~sql
UPDATE san_pham
SET trang_thai = 'STOP';
~~~

Nó có thể sửa **tất cả sản phẩm**.

Nếu chỉ muốn dừng một danh mục:

~~~sql
UPDATE san_pham
SET trang_thai = 'STOP'
WHERE ma_danh_muc = 'B';
~~~

Nếu chỉ muốn dừng một sản phẩm:

~~~sql
UPDATE san_pham
SET trang_thai = 'STOP'
WHERE ma_san_pham = 'P03';
~~~

**WHERE quyết định phạm vi tác động**. Một điều kiện đúng cú pháp nhưng quá rộng vẫn gây sai dữ liệu.

### 5.1. Xem trước trước khi sửa

~~~sql
SELECT
    ma_san_pham,
    ma_danh_muc,
    trang_thai
FROM san_pham
WHERE ma_danh_muc = 'A'
  AND trang_thai = 'ACTIVE'
ORDER BY ma_san_pham;
~~~

Trên dữ liệu mẫu, trả P01 và P02. Sau đó mới chạy:

~~~sql
UPDATE san_pham
SET trang_thai = 'REVIEW'
WHERE ma_danh_muc = 'A'
  AND trang_thai = 'ACTIVE';
~~~

Lưu ý: SELECT xem trước **không khóa cố định dữ liệu**. Một transaction khác có thể sửa bảng giữa SELECT và UPDATE; muốn nhất quán phải có isolation/locking thích hợp.

## 6. Kết hợp AND, OR và dấu ngoặc

~~~sql
UPDATE san_pham
SET trang_thai = 'REVIEW'
WHERE (ma_danh_muc = 'A' OR ma_danh_muc = 'B')
  AND trang_thai = 'ACTIVE';
~~~

Câu này chọn P01, P02, P03; không chọn P04 vì STOP, không chọn P05 vì không thuộc A/B.

Nếu bỏ ngoặc:

~~~sql
WHERE ma_danh_muc = 'A'
   OR ma_danh_muc = 'B'
  AND trang_thai = 'ACTIVE'
~~~

**AND thường có độ ưu tiên cao hơn OR**. Câu trên tương đương:

~~~sql
WHERE ma_danh_muc = 'A'
   OR (ma_danh_muc = 'B' AND trang_thai = 'ACTIVE')
~~~

Nó có thể chọn cả sản phẩm A đang STOP, không đúng ý định ban đầu.

### 6.1. Chỉ sửa khi còn ở trạng thái cho phép

~~~sql
UPDATE don_hang
SET trang_thai = 'DA_GIAO'
WHERE ma_don = 'D001'
  AND trang_thai = 'DANG_GIAO';
~~~

Điều kiện trạng thái cũ thể hiện một phần **state transition**. Nếu đơn đã bị hủy hoặc giao xong, UPDATE không khớp, tránh chuyển từ trạng thái không hợp lệ một cách tùy ý.

## 7. NULL trong WHERE: logic ba giá trị

Trong SQL, phép so sánh với NULL thường trả **UNKNOWN**, không phải TRUE hay FALSE.

~~~sql
WHERE ma_danh_muc = NULL
~~~

không phải cách tìm sản phẩm chưa có danh mục.

Đúng:

~~~sql
UPDATE san_pham
SET ma_danh_muc = 'KHAC'
WHERE ma_danh_muc IS NULL;
~~~

Với dữ liệu mẫu, chỉ P05 đổi danh mục.

### 7.1. Phủ định không tự chọn NULL

~~~sql
WHERE ma_danh_muc <> 'A'
~~~

chỉ chắc chắn chọn các giá trị khác A **và không NULL**. P05 có ma_danh_muc NULL không được chọn vì NULL <> 'A' là UNKNOWN.

Nếu nghiệp vụ muốn cả NULL:

~~~sql
WHERE ma_danh_muc <> 'A'
   OR ma_danh_muc IS NULL
~~~

### 7.2. NOT IN có thể bị ảnh hưởng bởi NULL

~~~sql
UPDATE san_pham
SET trang_thai = 'REVIEW'
WHERE ma_danh_muc NOT IN (
    SELECT ma_danh_muc FROM danh_muc_cam
);
~~~

Nếu truy vấn con có NULL, điều kiện NOT IN có thể không trả các hàng tưởng là “không thuộc danh sách”. Với ý định “không có hàng liên quan”, cân nhắc NOT EXISTS:

~~~sql
UPDATE san_pham
SET trang_thai = 'REVIEW'
WHERE NOT EXISTS (
    SELECT 1
    FROM danh_muc_cam c
    WHERE c.ma_danh_muc = san_pham.ma_danh_muc
);
~~~

Dù vậy, ma_danh_muc của sản phẩm NULL không khớp bằng phép bằng với NULL trong bảng con; cần xác định riêng chính sách với khóa NULL.

## 8. Gán giá trị mới dựa trên giá trị cũ

~~~sql
UPDATE san_pham
SET so_luong_ton = so_luong_ton + 5
WHERE ma_san_pham = 'P01';
~~~

P01 từ 10 lên **15**.

~~~sql
UPDATE san_pham
SET so_luong_ton = so_luong_ton - 2
WHERE ma_san_pham = 'P01';
~~~

P01 từ 10 xuống **8**, nếu tính độc lập từ dữ liệu ban đầu.

Phân biệt:

| Biểu thức SET | Ý nghĩa |
|---|---|
| so_luong_ton = 5 | Đặt tồn thành đúng 5 |
| so_luong_ton = so_luong_ton + 5 | Tăng thêm 5 |
| so_luong_ton = so_luong_ton - 5 | Giảm 5 |
| gia_ban = gia_ban * 1.10 | Tăng 10% |
| gia_ban = gia_ban * 0.90 | Giảm 10% |
| gia_ban = gia_ban + 10000 | Tăng 10000 đơn vị tiền |

Một hàng có giá 100000 sau tăng 10% thành 110000; hàng giá 200000 thành 220000. Mỗi hàng được tính theo giá trị của **chính hàng đó**, không dựa trên giá đã cập nhật của hàng khác.

## 9. Tăng giảm giá theo phần trăm

Giả sử tăng giá 10% cho danh mục A đang ACTIVE:

~~~sql
UPDATE san_pham
SET gia_ban = ROUND(gia_ban * 1.10, 2)
WHERE ma_danh_muc = 'A'
  AND trang_thai = 'ACTIVE';
~~~

Kết quả dự kiến:

| Mã | Giá cũ | Giá mới |
|---|---:|---:|
| P01 | 100000.00 | 110000.00 |
| P02 | 200000.00 | 220000.00 |

Giảm 15% cho P03:

~~~sql
UPDATE san_pham
SET gia_ban = ROUND(gia_ban * 0.85, 2)
WHERE ma_san_pham = 'P03';
~~~

P03 từ 50000 xuống 42500.

### 9.1. DECIMAL quan trọng với tiền

Với đơn giá và tiền tệ, nên dùng kiểu số thập phân chính xác như **DECIMAL/NUMERIC** với precision và scale hợp lý. FLOAT/DOUBLE có sai số biểu diễn nhị phân nên cần thận trọng cho giá trị tiền.

Ví dụ cột:

~~~sql
gia_ban DECIMAL(12, 2)
~~~

cho phép lưu giá tới mức độ chính xác theo quy định kiểu, nhưng không tự bảo đảm công thức tài chính đúng.

### 9.2. Làm tròn không phải chi tiết phụ

Cần thống nhất:

- Làm tròn **half-up**, **half-even** hay quy tắc khác?
- Làm tròn mỗi dòng hay sau khi tính tổng?
- Độ chính xác phù hợp loại tiền?
- Các literal số có bị chuyển kiểu hay chia nguyên không?

Trong các DBMS khác nhau, ROUND, ép kiểu và kết quả nhân có thể có khác biệt theo kiểu dữ liệu, nên thử trên hệ đích.

### 9.3. Cẩn thận phép chia nguyên

~~~sql
SET gia_ban = gia_ban * (110 / 100)
~~~

có thể không cho hệ số 1.10 trong mọi hệ nếu 110 và 100 được tính bằng chia nguyên. Dùng literal thập phân hoặc CAST đúng kiểu:

~~~sql
SET gia_ban = gia_ban * CAST(1.10 AS DECIMAL(5, 2))
~~~

và kiểm soát giới hạn giá trị mới.

## 10. Tránh cập nhật tồn kho thành âm

Nếu P01 còn 10, câu:

~~~sql
UPDATE san_pham
SET so_luong_ton = so_luong_ton - 12
WHERE ma_san_pham = 'P01';
~~~

có thể tạo -2 và bị CHECK từ chối. Tốt hơn là **chỉ cập nhật khi đủ tồn**:

~~~sql
UPDATE san_pham
SET so_luong_ton = so_luong_ton - 2
WHERE ma_san_pham = 'P01'
  AND so_luong_ton >= 2;
~~~

Nếu yêu cầu trừ 12, điều kiện không thỏa và không hàng nào được sửa.

### 10.1. Kiểm tra tham số số lượng

Biểu thức:

~~~sql
so_luong_ton = so_luong_ton - :qty
~~~

với qty = -3 sẽ **tăng** tồn thêm 3. Vì vậy, phải xác thực **qty > 0** ở tầng ứng dụng và/hoặc tầng cơ sở dữ liệu.

### 10.2. CHECK và WHERE có vai trò khác nhau

- **WHERE stock >= qty**: giới hạn hàng được phép sửa.
- **CHECK(stock >= 0)**: từ chối giá trị mới vi phạm bất biến nếu DBMS thực thi constraint.
- **Giao dịch và locking**: đảm bảo các bước liên quan không bị cạnh tranh sai.

Không dùng một lớp bảo vệ để thay thế toàn bộ lớp còn lại.

## 11. Cập nhật nhiều cột một lần

~~~sql
UPDATE san_pham
SET trang_thai = 'HET_HANG',
    phien_ban = phien_ban + 1,
    ngay_cap_nhat = CURRENT_TIMESTAMP
WHERE ma_san_pham = 'P02'
  AND so_luong_ton = 0;
~~~

Câu này vừa đổi trạng thái, vừa tăng phiên bản, vừa ghi thời điểm.

### 11.1. SET có luôn đọc giá trị cũ không?

Nhiều DBMS đánh giá biểu thức các cột trong SET theo giá trị cũ của hàng. Nhưng **MySQL single-table UPDATE** có quy tắc thứ tự gán cột (thường trái sang phải) có thể khiến hành vi khác. Ví dụ:

~~~sql
UPDATE bang_mau
SET a = b,
    b = a
WHERE id = 1;
~~~

không nên được coi là cách **hoán đổi a và b khả chuyển**. Nếu cần hoán đổi hai cột, phải xác minh cách thực hiện trên DBMS đích hoặc dùng phương án tường minh để lấy hai giá trị gốc.

### 11.2. Phụ thuộc chéo giữa các cột

Nếu trong một câu SET vừa đổi don_gia vừa tính thanh_tien, cần biết thanh_tien phải tính từ **đơn giá cũ hay mới**. Nên dùng công thức tường minh hoặc tính trước biểu thức đã được thống nhất, không dựa vào thứ tự đánh giá vô tình.

## 12. CASE: tính giá trị mới theo điều kiện

Cú pháp:

~~~sql
CASE
    WHEN dieu_kien_1 THEN gia_tri_1
    WHEN dieu_kien_2 THEN gia_tri_2
    ELSE gia_tri_mac_dinh
END
~~~

Ví dụ phân loại trạng thái tồn kho:

~~~sql
UPDATE san_pham
SET trang_thai = CASE
    WHEN so_luong_ton = 0 THEN 'HET_HANG'
    WHEN so_luong_ton < 5 THEN 'SAP_HET'
    ELSE 'ACTIVE'
END
WHERE trang_thai IN ('ACTIVE', 'HET_HANG', 'SAP_HET');
~~~

Dự đoán từ bảng mẫu:

| Mã | Tồn | Trạng thái sau |
|---|---:|---|
| P01 | 10 | ACTIVE |
| P02 | 0 | HET_HANG |
| P03 | 20 | ACTIVE |
| P04 | 4 | STOP, không sửa |
| P05 | 3 | SAP_HET |

**WHERE** quyết định hàng nào được xét. **CASE** quyết định giá trị được gán cho hàng đã được chọn.

### 12.1. Thứ tự WHEN rất quan trọng

Sai khi muốn phân biệt hết hàng:

~~~sql
CASE
    WHEN so_luong_ton < 5 THEN 'SAP_HET'
    WHEN so_luong_ton = 0 THEN 'HET_HANG'
    ELSE 'ACTIVE'
END
~~~

Bởi 0 < 5 nên số lượng bằng 0 bị nhánh đầu bắt trước. Đúng hơn là kiểm tra **= 0 trước**, sau đó kiểm tra **< 5**.

### 12.2. Thiếu ELSE có thể tạo NULL

~~~sql
SET trang_thai = CASE
    WHEN so_luong_ton = 0 THEN 'HET_HANG'
END
~~~

Nếu hàng không thỏa WHEN, CASE trả NULL. Nếu cột NOT NULL, lệnh có thể lỗi; nếu nullable, trạng thái cũ có thể mất.

Nếu muốn giữ nguyên khi không thỏa:

~~~sql
ELSE trang_thai
~~~

hoặc dùng WHERE giới hạn phạm vi.

### 12.3. CASE cho nhiều nhóm tỷ lệ

~~~sql
UPDATE san_pham
SET gia_ban = ROUND(
    gia_ban * CASE
        WHEN ma_danh_muc = 'A' THEN 1.10
        WHEN ma_danh_muc = 'B' THEN 1.05
        ELSE 1.00
    END,
    2
)
WHERE trang_thai = 'ACTIVE';
~~~

A tăng 10%, B tăng 5%, danh mục khác giữ giá; P04 STOP không thuộc phạm vi UPDATE.

## 13. COALESCE và dữ liệu thiếu

COALESCE trả biểu thức đầu tiên không NULL.

~~~sql
UPDATE san_pham
SET ma_danh_muc = COALESCE(ma_danh_muc, 'KHAC')
WHERE ma_danh_muc IS NULL;
~~~

Ở đây tương đương đặt trực tiếp 'KHAC' vì WHERE chỉ nhận các hàng đang NULL.

### 13.1. NULL cộng số vẫn NULL

Nếu tồn kho nullable:

~~~sql
SET so_luong_ton = so_luong_ton + 5
~~~

và so_luong_ton NULL, kết quả thường là NULL.

Có thể viết:

~~~sql
SET so_luong_ton = COALESCE(so_luong_ton, 0) + 5
~~~

nhưng **chỉ đúng nếu NULL về nghiệp vụ nghĩa là 0**. Nếu NULL nghĩa là “chưa kiểm kê”, đổi thành 0 làm mất thông tin quan trọng.

### 13.2. NULL khác chuỗi rỗng

~~~sql
UPDATE khach_hang
SET ghi_chu = NULL
WHERE ma_khach = 'K1';
~~~

khác:

~~~sql
UPDATE khach_hang
SET ghi_chu = ''
WHERE ma_khach = 'K1';
~~~

Nhiều DBMS phân biệt NULL với chuỗi rỗng, trong khi Oracle truyền thống thường coi chuỗi rỗng như NULL ở nhiều ngữ cảnh. Phải xác định quy tắc khi chuyển dữ liệu giữa các hệ.

## 14. Biểu thức dùng nhiều cột

Giả sử bảng chi_tiet_don có:

~~~text
ma_don, ma_san_pham, so_luong, don_gia, ty_le_giam, thanh_tien
~~~

Trong đó ty_le_giam là hệ số từ 0 tới 1:

~~~sql
UPDATE chi_tiet_don
SET thanh_tien = ROUND(
    so_luong * don_gia * (1 - ty_le_giam),
    2
)
WHERE ma_don = 'D001';
~~~

Nếu ty_le_giam lưu **10** để chỉ 10%, công thức trên sai. Cần chuẩn hóa kiểu lưu tỷ lệ hoặc chia cho 100 với kiểu thập phân phù hợp.

Các điều cần kiểm tra:

1. Đơn vị tiền và đơn vị số lượng.
2. NULL của so_luong/don_gia/ty_le_giam.
3. Số âm và khoảng giá trị cho phép.
4. Làm tròn và overflow.
5. Tác động khi cùng câu lệnh vừa đổi don_gia vừa tính thanh_tien.

SQL không thể tự nhận biết biểu thức hợp lệ về **đơn vị đo và chính sách nghiệp vụ**.

## 15. WHERE theo khoảng số và giá trị biên

Giảm 5% cho giá thuộc **[50000,100000)**:

~~~sql
UPDATE san_pham
SET gia_ban = ROUND(gia_ban * 0.95, 2)
WHERE gia_ban >= 50000
  AND gia_ban < 100000;
~~~

P03 và P04 được chọn từ dữ liệu mẫu. P01 giá đúng 100000 **không** được chọn.

### 15.1. BETWEEN có cả hai cận

~~~sql
WHERE gia_ban BETWEEN 50000 AND 100000
~~~

thường tương đương:

~~~sql
WHERE gia_ban >= 50000
  AND gia_ban <= 100000
~~~

Vì vậy P01 lại được chọn. Đây là lỗi ranh giới phổ biến khi viết UPDATE theo chính sách giá.

### 15.2. Không nhầm số tiền với phần trăm

- Giảm 10%: gia_ban * 0.90.
- Giảm 10000: gia_ban - 10000.
- Giảm 10 điểm phần trăm của một tỷ lệ: rate - 0.10, không phải rate * 0.90.

Hãy viết câu mô tả nghiệp vụ và đơn vị trước khi biến thành công thức SET.

## 16. Cập nhật theo thời gian

Giả sử muốn đổi trạng thái đơn đặt trong **ngày 10/04/2026**:

~~~sql
UPDATE don_hang
SET trang_thai = 'CAN_DOI_SOAT'
WHERE thoi_diem_dat >= :report_start
  AND thoi_diem_dat < :report_end
  AND trang_thai = 'MOI';
~~~

Với **report_start** là đầu ngày 10/04 và **report_end** là đầu ngày 11/04 theo múi giờ nghiệp vụ, khoảng nửa mở **[start,end)** bao phủ cả ngày mà không cần đoán độ chính xác phần giây.

Không nên viết điều kiện đến **23:59:59.999** nếu cột có thể có độ chính xác khác hoặc cao hơn.

### 16.1. Giá trị ngày giờ hiện tại

~~~sql
UPDATE don_hang
SET ngay_cap_nhat = CURRENT_TIMESTAMP
WHERE ma_don = 'D001';
~~~

CURRENT_TIMESTAMP được hỗ trợ rộng rãi nhưng kiểu, độ chính xác và timezone khi hiển thị có thể khác theo hệ.

### 16.2. Cộng bảy ngày theo DBMS

**PostgreSQL:**

~~~sql
UPDATE hop_dong
SET ngay_het_han = ngay_het_han + INTERVAL '7 days'
WHERE ma_hop_dong = 'HD01';
~~~

**MySQL:**

~~~sql
UPDATE hop_dong
SET ngay_het_han = DATE_ADD(ngay_het_han, INTERVAL 7 DAY)
WHERE ma_hop_dong = 'HD01';
~~~

**SQL Server:**

~~~sql
UPDATE hop_dong
SET ngay_het_han = DATEADD(day, 7, ngay_het_han)
WHERE ma_hop_dong = 'HD01';
~~~

**Oracle Database:** với cột DATE, cộng số ngày:

~~~sql
UPDATE hop_dong
SET ngay_het_han = ngay_het_han + 7
WHERE ma_hop_dong = 'HD01';
~~~

**SQLite:** khi cột đang lưu thời gian theo định dạng các hàm datetime hiểu:

~~~sql
UPDATE hop_dong
SET ngay_het_han = datetime(ngay_het_han, '+7 days')
WHERE ma_hop_dong = 'HD01';
~~~

Các mẫu trên **không chuyển nguyên văn giữa DBMS**; với SQLite lưu DATE dạng văn bản ngày, có thể dùng date(...) để giữ đúng định dạng.

### 16.3. Bảy ngày không phải bảy ngày làm việc

Nếu hợp đồng cần **thêm năm ngày làm việc**, phải dùng lịch làm việc/ngày lễ. Cộng bảy ngày lịch không tự xử lý ngày nghỉ.

### 16.4. DST và múi giờ

Ở vùng có đổi giờ mùa hè, một ngày địa phương có thể dài 23 hoặc 25 giờ. Để UPDATE theo **ngày lịch địa phương**, hãy xác định đầu hai ngày liên tiếp trong múi giờ nghiệp vụ rồi chuyển sang kiểu thời điểm đang lưu, không luôn cộng cố định 24 giờ vào một instant.

## 17. Cập nhật chuỗi bằng hàm

Chuẩn hóa khoảng trắng:

~~~sql
UPDATE khach_hang
SET ten_hien_thi = TRIM(ten_hien_thi)
WHERE ten_hien_thi IS NOT NULL;
~~~

Chuẩn hóa mã theo chữ hoa:

~~~sql
UPDATE san_pham
SET ma_nhom_hien_thi = UPPER(ma_nhom_hien_thi)
WHERE ma_nhom_hien_thi IS NOT NULL;
~~~

Không dùng UPPER/LOWER máy móc cho mọi định danh: Unicode, collation, dấu và quy tắc hoa thường có thể mang ý nghĩa nghiệp vụ.

### 17.1. Nối chuỗi khác nhau giữa DBMS

PostgreSQL/Oracle/SQLite thường hỗ trợ toán tử nối **||**. SQL Server thường dùng **+** hoặc CONCAT, MySQL thường dùng CONCAT. Khi cột hiện tại NULL, việc nối cũng cần chính sách NULL rõ.

Ví dụ ý tưởng đa hệ khi CONCAT được hỗ trợ đúng:

~~~sql
SET ghi_chu = CONCAT(COALESCE(ghi_chu, ''), ' [DA_XAC_NHAN]')
~~~

Chạy lại câu lệnh có thể nối thêm hậu tố lần nữa. Nếu phải không lặp, cần điều kiện idempotency hoặc kiểm tra trạng thái ghi chú.

## 18. Scalar subquery trong SET

Giả sử có bảng danh_muc:

~~~sql
CREATE TABLE danh_muc (
    ma_danh_muc VARCHAR(20) PRIMARY KEY,
    ty_le_tang DECIMAL(5, 4) NOT NULL
);
~~~

Dữ liệu:

| Mã danh mục | Tỷ lệ tăng |
|---|---:|
| A | 0.1000 |
| B | 0.0500 |

Muốn tăng giá theo bảng tỷ lệ:

~~~sql
UPDATE san_pham
SET gia_ban = ROUND(
    gia_ban * (
        1 + (
            SELECT d.ty_le_tang
            FROM danh_muc d
            WHERE d.ma_danh_muc = san_pham.ma_danh_muc
        )
    ),
    2
)
WHERE trang_thai = 'ACTIVE'
  AND EXISTS (
      SELECT 1
      FROM danh_muc d
      WHERE d.ma_danh_muc = san_pham.ma_danh_muc
  );
~~~

### 18.1. Scalar subquery phải có đúng cardinality

Một subquery dùng ở vị trí giá trị đơn lẻ được kỳ vọng trả:

- **Một dòng, một cột:** dùng giá trị đó.
- **Không có dòng:** thường cho NULL.
- **Nhiều dòng:** nhiều DBMS báo lỗi vì không thể coi nhiều hàng là một giá trị duy nhất.

Bảng danh_muc có PRIMARY KEY để bảo đảm một tỷ lệ cho mỗi danh mục.

### 18.2. Vì sao thêm EXISTS?

Nếu không có danh mục tương ứng, subquery không có giá trị, phép tính với NULL có thể cho NULL rồi cố gán vào gia_ban NOT NULL. EXISTS giúp chỉ cập nhật sản phẩm có nguồn tỷ lệ.

Nếu nghiệp vụ cho phép danh mục thiếu tỷ lệ và vẫn giữ giá, có thể dùng COALESCE, nhưng **chỉ khi đây là chính sách có chủ đích**.

## 19. EXISTS và NOT EXISTS trong WHERE

Nếu chỉ cần biết một sản phẩm có **ít nhất một đơn đang chờ giao**:

~~~sql
UPDATE san_pham
SET trang_thai = 'TAM_GIU'
WHERE trang_thai = 'ACTIVE'
  AND EXISTS (
      SELECT 1
      FROM chi_tiet_don ct
      JOIN don_hang d
        ON d.ma_don = ct.ma_don
      WHERE ct.ma_san_pham = san_pham.ma_san_pham
        AND d.trang_thai = 'CHO_GIAO'
  );
~~~

EXISTS kiểm tra **sự tồn tại**, không cần lấy dữ liệu nguồn để SET. Một sản phẩm có 50 đơn chờ giao vẫn là **một hàng đích** được xét cập nhật.

Ngược lại:

~~~sql
UPDATE san_pham
SET trang_thai = 'CHUA_TUNG_BAN'
WHERE NOT EXISTS (
    SELECT 1
    FROM chi_tiet_don ct
    WHERE ct.ma_san_pham = san_pham.ma_san_pham
);
~~~

đánh dấu sản phẩm không có dòng tương ứng trong chi tiết đơn. Nhưng “chưa từng bán” có tính đơn hủy, dữ liệu archive và đơn test hay không là một **quy tắc nghiệp vụ** cần mô tả rõ.

### 19.1. Khi nào dùng EXISTS thay vì UPDATE JOIN?

Nếu không cần cột từ bảng kia để tính giá mới, EXISTS thường diễn đạt “có/không có quan hệ” trực tiếp hơn và giảm rủi ro do bảng nguồn có nhiều dòng khớp.

Nếu SET cần lấy tỷ lệ, giá hoặc số lượng từ bảng khác, dùng subquery hoặc cú pháp UPDATE FROM/JOIN phù hợp, sau khi bảo đảm tính duy nhất của giá trị nguồn.

## 20. UPDATE từ bảng khác theo phương ngữ

### 20.1. PostgreSQL — UPDATE ... FROM

~~~sql
UPDATE san_pham AS p
SET gia_ban = ROUND(p.gia_ban * (1 + d.ty_le_tang), 2)
FROM danh_muc AS d
WHERE d.ma_danh_muc = p.ma_danh_muc
  AND p.trang_thai = 'ACTIVE';
~~~

### 20.2. SQL Server — UPDATE alias FROM JOIN

~~~sql
UPDATE p
SET p.gia_ban = ROUND(p.gia_ban * (1 + d.ty_le_tang), 2)
FROM dbo.san_pham AS p
JOIN dbo.danh_muc AS d
    ON d.ma_danh_muc = p.ma_danh_muc
WHERE p.trang_thai = 'ACTIVE';
~~~

### 20.3. MySQL — UPDATE JOIN SET

~~~sql
UPDATE san_pham AS p
JOIN danh_muc AS d
  ON d.ma_danh_muc = p.ma_danh_muc
SET p.gia_ban = ROUND(p.gia_ban * (1 + d.ty_le_tang), 2)
WHERE p.trang_thai = 'ACTIVE';
~~~

### 20.4. Oracle — correlated subquery hoặc MERGE

Oracle phổ biến có thể dùng scalar subquery như phần 18 hoặc MERGE:

~~~sql
MERGE INTO san_pham p
USING danh_muc d
ON (p.ma_danh_muc = d.ma_danh_muc)
WHEN MATCHED THEN
    UPDATE SET p.gia_ban =
        ROUND(p.gia_ban * (1 + d.ty_le_tang), 2)
    WHERE p.trang_thai = 'ACTIVE';
~~~

MERGE có quy tắc riêng về việc nguồn khớp đích, tính xác định và cột xuất hiện trong ON. Không xem nó là cú pháp thay thế nguyên văn cho mọi UPDATE JOIN.

### 20.5. SQLite — UPDATE FROM phiên bản mới

SQLite 3.33.0+ có UPDATE FROM theo phong cách gần PostgreSQL:

~~~sql
UPDATE san_pham AS p
SET gia_ban = ROUND(p.gia_ban * (1 + d.ty_le_tang), 2)
FROM danh_muc AS d
WHERE d.ma_danh_muc = p.ma_danh_muc
  AND p.trang_thai = 'ACTIVE';
~~~

Tính chính xác kiểu DECIMAL trong SQLite cần xem xét riêng vì hệ thống kiểu có tính linh hoạt.

| DBMS | Cách cập nhật nguồn liên quan phổ biến |
|---|---|
| PostgreSQL | UPDATE target SET ... FROM source WHERE ... |
| SQL Server | UPDATE alias SET ... FROM target JOIN source |
| MySQL | UPDATE target JOIN source SET ... WHERE ... |
| Oracle | Scalar subquery/MERGE tùy phiên bản |
| SQLite mới | UPDATE target SET ... FROM source WHERE ... |

## 21. Một hàng đích khớp nhiều dòng nguồn

Giả sử bảng khuyen_mai có:

| Danh mục | Tỷ lệ tăng |
|---|---:|
| A | 0.10 |
| A | 0.20 |

Nếu UPDATE sản phẩm A bằng JOIN, mỗi hàng P01/P02 có thể khớp **hai tỷ lệ**. Kết quả giá được chọn có thể **không xác định** hoặc phát sinh lỗi, tùy DBMS và câu lệnh.

Không được coi “UPDATE chạy thành công” là bằng chứng kết quả đúng.

### 21.1. Giải pháp 1: bảo đảm nguồn duy nhất

Nếu nghiệp vụ chỉ cho một tỷ lệ mỗi danh mục:

~~~sql
UNIQUE (ma_danh_muc)
~~~

trên nguồn là ràng buộc phù hợp.

### 21.2. Giải pháp 2: chọn một nguồn theo quy tắc rõ

Nếu nghiệp vụ muốn mức tăng cao nhất:

~~~sql
SELECT ma_danh_muc, MAX(ty_le_tang) AS ty_le_tang
FROM khuyen_mai
GROUP BY ma_danh_muc;
~~~

Sau đó JOIN với kết quả nhóm. Nhưng **MAX chỉ đúng nếu chính sách yêu cầu MAX**. Với chương trình có thời gian hiệu lực/độ ưu tiên, có thể phải chọn bản ghi mới nhất hợp lệ thay vì giá trị lớn nhất.

### 21.3. Xác định grain

Trước khi cập nhật từ JOIN, hỏi:

> Mỗi **hàng đích định danh bởi ma_san_pham** có đúng **một** tập giá trị nguồn để gán hay chưa?

Nếu chưa, phải giải quyết vấn đề cardinality trước.

## 22. UPDATE bằng kết quả tổng hợp

Giả sử bảng khach_hang có cột tong_so_don, còn don_hang lưu ma_khach:

~~~sql
UPDATE khach_hang
SET tong_so_don = (
    SELECT COUNT(*)
    FROM don_hang d
    WHERE d.ma_khach = khach_hang.ma_khach
);
~~~

COUNT(*) luôn trả một giá trị số kể cả không có dòng (0), khác scalar subquery chọn một cột thông thường có thể trả NULL khi không có hàng.

### 22.1. Hiệu năng của correlated subquery

Trên bảng lớn, truy vấn tương quan có thể tốn chi phí. Cân nhắc:

- Chỉ mục trên don_hang.ma_khach.
- Nhóm trước bằng GROUP BY rồi UPDATE FROM/JOIN.
- Chỉ sửa những khách liên quan đến đơn vừa thay đổi.
- Execution plan và thống kê DBMS.

### 22.2. Dữ liệu tổng hợp có thể lỗi thời

Nếu cùng lúc có INSERT/DELETE đơn hàng, tong_so_don lưu sẵn có thể không còn khớp. Phải có cơ chế duy trì nhất quán hoặc tính tổng hợp lại khi cần.

## 23. UPDATE tự tham chiếu cùng bảng

Ví dụ ý tưởng đánh dấu sản phẩm giá cao hơn trung bình:

~~~sql
UPDATE san_pham
SET trang_thai = 'GIA_CAO'
WHERE gia_ban > (
    SELECT AVG(gia_ban)
    FROM san_pham
);
~~~

**Không phải mọi DBMS chấp nhận cùng dạng tự đọc bảng đích trong subquery.** MySQL có những giới hạn cho UPDATE đọc lại bảng đích trực tiếp; cần derived table/CTE hoặc cách viết phù hợp. Phải kiểm tra liệu giá trung bình được xác định từ snapshot nào và kế hoạch thực thi ra sao.

Nếu yêu cầu dùng một mức giá trung bình cố định **trước khi cập nhật**, nên xác định nó rõ ràng bằng transaction/CTE/nguồn tính toán thích hợp thay vì phụ thuộc hành vi không được mô tả.

## 24. UPDATE và transaction

Một giao dịch có thể nhóm nhiều câu lệnh thành một đơn vị logic:

~~~sql
BEGIN;

UPDATE san_pham
SET gia_ban = ROUND(gia_ban * 1.10, 2)
WHERE ma_danh_muc = 'A'
  AND trang_thai = 'ACTIVE';

SELECT ma_san_pham, gia_ban
FROM san_pham
WHERE ma_danh_muc = 'A'
ORDER BY ma_san_pham;

-- Nếu chấp nhận thay đổi:
COMMIT;

-- Hoặc nếu muốn hủy trước commit:
-- ROLLBACK;
~~~

Đoạn mã minh họa **hai lựa chọn**, không yêu cầu COMMIT và ROLLBACK cùng chạy nối tiếp trong một transaction.

### 24.1. Khác biệt cách bắt đầu

| DBMS | Cách thường gặp |
|---|---|
| PostgreSQL | BEGIN |
| MySQL | START TRANSACTION |
| SQL Server | BEGIN TRANSACTION |
| Oracle | Transaction DML thường bắt đầu ngầm; COMMIT/ROLLBACK rõ |
| SQLite | BEGIN |

Autocommit, loại bảng, DDL trong transaction, trigger và lỗi có những hành vi khác nhau. Cần hiểu môi trường thực tế trước khi nghĩ UPDATE luôn có thể ROLLBACK.

### 24.2. ROLLBACK sau COMMIT không đảo thay đổi cũ

ROLLBACK khi transaction còn mở thường có thể hoàn tác DML của transaction đó. Sau khi đã COMMIT, một ROLLBACK mới **không tự khôi phục dữ liệu trước commit**. Đối với UPDATE quan trọng cần kế hoạch backup, audit hoặc undo script.

### 24.3. SELECT trước UPDATE chưa khóa dữ liệu

Hai giao dịch có thể sửa cùng dữ liệu giữa lúc bạn preview và lúc chạy UPDATE. Khi cần tập hàng ổn định, dùng isolation, khóa hoặc version predicate phù hợp.

## 25. Kiểm tra số hàng được cập nhật

Câu UPDATE dùng mã duy nhất thường kỳ vọng **tối đa 1 hàng**. Nếu kết quả 0, có thể do:

- Mã không tồn tại.
- Trạng thái cũ không thỏa.
- Tồn kho không đủ.
- Phiên bản không khớp.
- Hàng đã bị sửa/xóa bởi giao dịch khác.

Nếu phạm vi danh mục, số hàng có thể nhiều và phải được đánh giá theo yêu cầu.

### 25.1. Matched rows khác changed rows

Ví dụ P01 đã ACTIVE:

~~~sql
UPDATE san_pham
SET trang_thai = 'ACTIVE'
WHERE ma_san_pham = 'P01';
~~~

Có một hàng **khớp WHERE**, nhưng giá trị cuối không thay đổi. DBMS/driver có thể báo số hàng **matched** hoặc **changed** khác nhau theo cấu hình và giao diện. Không giả định số trả về luôn có cùng ý nghĩa trên mọi hệ.

### 25.2. Chỉ sửa khi khác giá trị

~~~sql
UPDATE san_pham
SET trang_thai = 'ACTIVE'
WHERE ma_san_pham = 'P01'
  AND (
      trang_thai IS NULL
      OR trang_thai <> 'ACTIVE'
  );
~~~

Nếu cột NOT NULL, có thể bỏ nhánh IS NULL. Ở DBMS có IS DISTINCT FROM, có thể dùng điều kiện null-safe phù hợp.

Trigger và cột updated_at tự động có thể vẫn tạo tác động khi SET giá trị không đổi; cần hiểu cấu hình.

## 26. RETURNING, OUTPUT và giá trị sau UPDATE

### 26.1. PostgreSQL

~~~sql
UPDATE san_pham
SET gia_ban = ROUND(gia_ban * 1.10, 2)
WHERE ma_san_pham = 'P01'
RETURNING ma_san_pham, gia_ban, phien_ban;
~~~

RETURNING cho biết hàng và giá trị sau khi cập nhật. Khả năng trả giá trị cũ/mới đồng thời có cú pháp riêng theo phiên bản; không mặc định mọi PostgreSQL đều hỗ trợ cùng một dạng alias cho OLD/NEW.

### 26.2. SQLite 3.35+

~~~sql
UPDATE san_pham
SET so_luong_ton = so_luong_ton + 5
WHERE ma_san_pham = 'P01'
RETURNING ma_san_pham, so_luong_ton;
~~~

### 26.3. SQL Server

~~~sql
UPDATE dbo.san_pham
SET gia_ban = gia_ban * 1.10
OUTPUT
    deleted.ma_san_pham,
    deleted.gia_ban AS gia_cu,
    inserted.gia_ban AS gia_moi
WHERE ma_san_pham = 'P01';
~~~

OUTPUT có thể lấy giá trị từ các pseudo-table inserted/deleted. Khi bảng có trigger, có thể có giới hạn đối với OUTPUT trực tiếp; phải kiểm tra cấu hình.

### 26.4. Oracle

Oracle hỗ trợ RETURNING ... INTO theo ngữ cảnh PL/SQL/biến OUT:

~~~sql
UPDATE san_pham
SET gia_ban = gia_ban * 1.10
WHERE ma_san_pham = :ma
RETURNING gia_ban INTO :gia_moi;
~~~

Không nhầm nó với một SELECT trả ResultSet giống PostgreSQL.

### 26.5. MySQL

Trong các phiên bản MySQL thông dụng, UPDATE không có RETURNING tổng quát theo cùng cú pháp PostgreSQL. Có thể lấy row count, sau đó SELECT trong transaction hoặc dùng cơ chế khác phù hợp. MariaDB và MySQL là hai sản phẩm với tập tính năng khác nhau.

## 27. Lost update và hai người sửa cùng hàng

Giả sử P01 tồn kho 10. Hai giao dịch cùng đọc 10:

~~~text
T1 đọc 10, bán 2 -> ứng dụng tính 8.
T2 đọc 10, bán 3 -> ứng dụng tính 7.
T1 ghi tồn = 8.
T2 ghi tồn = 7.
~~~

Kết quả cuối thành 7, dù tổng đã bán là 5 và tồn đúng phải là **5**. Đây là dạng **lost update**: một lần sửa bị ghi đè.

### 27.1. Cập nhật tương đối tại database

Thay vì đọc rồi gửi giá trị tuyệt đối:

~~~sql
UPDATE san_pham
SET so_luong_ton = so_luong_ton - 2
WHERE ma_san_pham = 'P01'
  AND so_luong_ton >= 2;
~~~

Giao dịch khác dùng phép trừ 3 tương tự. Trong hệ DBMS có giao dịch và khóa hàng phù hợp, các phép UPDATE này có thể được xử lý tuần tự trên hàng, giảm nguy cơ ghi đè giá trị cũ từ ứng dụng.

Tuy nhiên, **toàn bộ nghiệp vụ** còn cần transaction, cách ly, xử lý deadlock/timeout, retry và đồng bộ với đơn hàng.

### 27.2. Optimistic locking bằng version

Ứng dụng đọc P01 có phien_ban = 1. Khi sửa:

~~~sql
UPDATE san_pham
SET so_luong_ton = so_luong_ton - 2,
    phien_ban = phien_ban + 1,
    ngay_cap_nhat = CURRENT_TIMESTAMP
WHERE ma_san_pham = 'P01'
  AND phien_ban = 1
  AND so_luong_ton >= 2;
~~~

Nếu một giao dịch khác đã tăng phiên bản, WHERE không còn khớp. Ứng dụng phải coi 0 hàng là **có thể có xung đột hoặc không đủ điều kiện**, không tự trả thành công.

Mọi đường code cạnh tranh trên cùng thực thể phải duy trì version nhất quán. Nếu một UPDATE sửa hàng nhưng quên tăng phien_ban, cơ chế optimistic lock có thể mất tác dụng.

### 27.3. Pessimistic locking

PostgreSQL/MySQL/Oracle có cú pháp SELECT ... FOR UPDATE để khóa dòng theo quy tắc sản phẩm. SQL Server dùng cơ chế lock hints khác, SQLite dùng cơ chế transaction/ghi riêng. Khóa giúp điều phối nhưng có thể tăng contention hoặc deadlock; cần transaction ngắn và xử lý lỗi.

## 28. Không cho phép job tăng giá chạy lặp

Giả sử một chương trình tăng giá 10%:

~~~sql
UPDATE san_pham
SET gia_ban = gia_ban * 1.10
WHERE ma_danh_muc = 'A';
~~~

P01: 100000 → 110000 sau lần đầu; nếu chạy lại: **121000**.

Câu lệnh này **không idempotent**.

| SET | Chạy lại có cùng giá cuối? |
|---|---|
| trang_thai = 'ACTIVE' | Thường có, xét riêng audit/trigger |
| so_luong_ton = so_luong_ton + 5 | Không |
| gia_ban = gia_ban * 1.10 | Không |
| gia_ban = gia_goc * 1.10 | Có thể, nếu gia_goc cố định và đúng nghiệp vụ |

Các cách kiểm soát:

- Mã chiến dịch và bảng đánh dấu đã áp dụng với UNIQUE.
- Idempotency key cho yêu cầu ghi nghiệp vụ.
- Cờ/phiên bản phù hợp, được cập nhật cùng giao dịch.
- Lấy giá từ giá gốc bất biến nếu yêu cầu là một giá dựa trên chuẩn.

Chỉ SELECT “chưa áp dụng” trước UPDATE nhưng không có ràng buộc/transaction vẫn có thể lỗi khi chạy đồng thời.

## 29. UPDATE theo danh sách ID và phân quyền

~~~sql
UPDATE san_pham
SET trang_thai = 'REVIEW'
WHERE ma_san_pham IN ('P01', 'P03', 'P05');
~~~

Dấu IN chọn những hàng có mã trong danh sách; trùng ID trong danh sách không có nghĩa hàng được cập nhật nhiều lần.

Cần xử lý:

- Danh sách rỗng (IN () không hợp lệ ở nhiều hệ).
- Danh sách quá lớn vượt giới hạn tham số.
- ID không tồn tại, không có quyền hoặc đã bị xóa.
- Khóa cùng tên ở các tenant khác nhau.

### 29.1. Multi-tenant phải có phạm vi đáng tin

~~~sql
UPDATE san_pham
SET trang_thai = 'REVIEW'
WHERE tenant_id = ?
  AND ma_san_pham = ?;
~~~

Đây là mẫu cho bảng thực tế có cột tenant_id. Tenant phải lấy từ **ngữ cảnh xác thực của server**, không tin dữ liệu tenant do client tùy ý gửi.

## 30. UPDATE theo batch

Không có cú pháp giới hạn số hàng UPDATE khả chuyển cho mọi DBMS.

**MySQL** hỗ trợ ORDER BY/LIMIT cho single-table UPDATE theo quy tắc phiên bản:

~~~sql
UPDATE cong_viec
SET trang_thai = 'DANG_XU_LY'
WHERE trang_thai = 'CHO'
ORDER BY ma_cong_viec
LIMIT 100;
~~~

**SQL Server** có UPDATE TOP(...), nhưng TOP không tự bảo đảm thứ tự; cần chọn ID ổn định nếu muốn đúng 100 hàng đầu.

**PostgreSQL** thường dùng CTE chọn khóa:

~~~sql
WITH duoc_chon AS (
    SELECT id
    FROM cong_viec
    WHERE trang_thai = 'CHO'
    ORDER BY id
    LIMIT 100
)
UPDATE cong_viec AS c
SET trang_thai = 'DANG_XU_LY'
FROM duoc_chon AS d
WHERE c.id = d.id;
~~~

Trong môi trường nhiều worker, mẫu CTE trên chưa đủ bảo vệ việc hai worker cùng lấy một job. Có thể cần FOR UPDATE SKIP LOCKED hoặc cơ chế cạnh tranh phù hợp DBMS.

**Đừng dùng OFFSET tăng liên tục** trên tập dữ liệu mà chính UPDATE làm đổi điều kiện WHERE: có thể bỏ sót dòng vì dữ liệu được xử lý rời khỏi tập đang phân trang.

## 31. Constraint, trigger và quan hệ khóa ngoại

UPDATE không chỉ bị chi phối bởi WHERE/SET:

- **NOT NULL** từ chối giá trị NULL không hợp lệ.
- **CHECK** có thể chặn giá/tồn âm.
- **UNIQUE/PRIMARY KEY** chặn khóa trùng.
- **FOREIGN KEY** chặn tham chiếu cha không tồn tại.
- **ON UPDATE CASCADE** có thể thay đổi khóa ngoại của hàng con khi khóa cha đổi, tùy thiết kế.
- **Trigger** có thể ghi audit hoặc thay đổi dữ liệu phụ.
- **Generated/computed column** có thể không cho phép SET trực tiếp.
- **View** có thể chỉ cập nhật được theo những điều kiện nhất định.

### 31.1. Đổi khóa chính là thao tác nhạy cảm

~~~sql
UPDATE san_pham
SET ma_san_pham = 'P99'
WHERE ma_san_pham = 'P01';
~~~

Nếu P01 đang được đơn hàng tham chiếu, UPDATE có thể bị chặn bởi FK hoặc gây cascade. Đừng sửa mã định danh khi nhu cầu chỉ là thay đổi **tên hiển thị**.

### 31.2. UPDATE và soft delete

~~~sql
UPDATE san_pham
SET trang_thai = 'DA_XOA'
WHERE ma_san_pham = 'P01';
~~~

được gọi là **soft delete** khi ứng dụng ẩn bản ghi nhưng không xóa vật lý. Nó khác DELETE:

- Quan hệ FK vẫn tồn tại.
- Truy vấn đọc phải lọc trạng thái.
- UNIQUE có thể vẫn giữ chỗ cho khóa của hàng đã xóa mềm.
- Quy trình xóa dữ liệu thực sự/audit cần được thiết kế riêng.

## 32. Quy trình kiểm soát trước và sau UPDATE

**Bước 1 — Xác định rõ điều kiện nghiệp vụ.**

Ví dụ: “Tăng 10% giá các sản phẩm ACTIVE thuộc danh mục A, đúng một lần trong chiến dịch”.

**Bước 2 — SELECT xem trước đúng tập hàng.**

~~~sql
SELECT ma_san_pham, gia_ban, trang_thai
FROM san_pham
WHERE ma_danh_muc = 'A'
  AND trang_thai = 'ACTIVE';
~~~

**Bước 3 — Tính thử giá mới bằng SELECT, không sửa dữ liệu.**

~~~sql
SELECT
    ma_san_pham,
    gia_ban AS gia_cu,
    ROUND(gia_ban * 1.10, 2) AS gia_du_kien
FROM san_pham
WHERE ma_danh_muc = 'A'
  AND trang_thai = 'ACTIVE';
~~~

**Bước 4 — Đảm bảo cơ chế chiến dịch/idempotency và transaction phù hợp.**

**Bước 5 — UPDATE đúng điều kiện.**

~~~sql
UPDATE san_pham
SET gia_ban = ROUND(gia_ban * 1.10, 2)
WHERE ma_danh_muc = 'A'
  AND trang_thai = 'ACTIVE';
~~~

**Bước 6 — Kiểm tra số hàng và giá trị sau sửa**, có thể dùng RETURNING/OUTPUT tùy DBMS.

**Bước 7 — COMMIT hoặc ROLLBACK** theo chính sách, lưu audit/backup nếu thay đổi quan trọng.

Preview là bước cần thiết nhưng **không thay thế kiểm soát concurrency**.

## 33. UPDATE qua Java/JDBC

Ví dụ trừ kho bằng PreparedStatement:

~~~java
String sql = """
    UPDATE san_pham
    SET so_luong_ton = so_luong_ton - ?,
        phien_ban = phien_ban + 1
    WHERE ma_san_pham = ?
      AND so_luong_ton >= ?
      AND phien_ban = ?
      AND trang_thai = 'ACTIVE'
    """;

int quantity = 2;
String productId = "P01";
int expectedVersion = 1;

if (quantity <= 0) {
    throw new IllegalArgumentException("So luong phai > 0");
}

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setInt(1, quantity);
    ps.setString(2, productId);
    ps.setInt(3, quantity);
    ps.setInt(4, expectedVersion);

    int affected = ps.executeUpdate();
    if (affected == 1) {
        System.out.println("Cap nhat thanh cong");
    } else {
        System.out.println(
            "Khong ton tai, khong du ton, hoac xung dot phien ban"
        );
    }
}
~~~

Trong ứng dụng có tenant, thêm điều kiện tenant vào WHERE. Nếu trừ kho phải đi cùng INSERT đơn hàng, hai thao tác cần nằm trong **cùng transaction** khi dùng một database.

### 33.1. Vì sao dùng PreparedStatement?

- Tránh nối dữ liệu người dùng vào SQL và giảm nguy cơ SQL injection.
- Bind đúng kiểu số/chuỗi/ngày giờ.
- Dễ kiểm soát điều kiện cập nhật.
- Dễ kiểm tra row count và lỗi SQL.

PreparedStatement thường **không dùng để bind tên bảng/cột**. Nếu UI cho phép chọn cột cập nhật, server phải có danh sách tên cột được phép (allowlist), không nối chuỗi tùy ý.

### 33.2. Quy ước affected rows

Không chỉ xét số trả về; khi kết quả 0, có thể cần đọc lại hàng để phân biệt tồn tại, thiếu tồn, sai phiên bản, sai trạng thái. Với các DBMS/driver, **matched rows** và **changed rows** có thể được báo khác nhau khi gán lại giá trị không đổi.

## 34. Tình huống tổng hợp: trừ tồn kho và ghi đơn

Một người mua hai P01:

~~~text
BẮT ĐẦU TRANSACTION
    |
    +-- Kiểm tra input qty > 0, tenant và quyền
    |
    +-- UPDATE kho:
    |   stock = stock - qty
    |   WHERE product = P01
    |     AND stock >= qty
    |     AND status = ACTIVE
    |     AND tenant = currentTenant
    |
    +-- Nếu row count không đúng kỳ vọng:
    |       ROLLBACK, phản hồi phù hợp
    |
    +-- INSERT đơn/chi tiết đơn, cùng idempotency key
    |
    +-- Nếu constraint/INSERT lỗi:
    |       ROLLBACK
    |
    +-- Nếu mọi bước thành công:
            COMMIT
~~~

Nếu trừ kho được COMMIT nhưng ghi đơn thất bại, hệ thống mất hàng mà không có đơn tương ứng. Nếu ghi đơn COMMIT trước nhưng trừ kho thất bại, đơn có thể tồn tại dù không đủ hàng.

Khi các bước nằm **cùng cơ sở dữ liệu giao dịch**, transaction giúp bảo đảm tính nguyên tử. Nếu có thanh toán qua dịch vụ bên ngoài, một transaction SQL thường không thể tự rollback tác động ngoài hệ thống; cần mô hình saga/outbox/idempotency theo kiến trúc.

### 34.1. Retry có thể trừ kho hai lần

Client mất kết nối sau COMMIT, gửi lại yêu cầu. Nếu ứng dụng không nhận diện yêu cầu đã xử lý, nó có thể trừ kho lần nữa. Cần **request_id duy nhất** hoặc idempotency key được kiểm soát tại DB và xử lý retry nhất quán.

## 35. Các lỗi thường gặp

| Sai lầm | Hậu quả | Cách phòng tránh |
|---|---|---|
| Quên WHERE | Sửa toàn bộ bảng | Preview, transaction, kiểm tra phạm vi |
| WHERE theo tên không duy nhất | Sửa nhiều thực thể | Dùng khóa định danh |
| Thiếu tenant trong WHERE | Sửa dữ liệu sai tổ chức | Lọc tenant từ ngữ cảnh tin cậy |
| Sai ưu tiên AND/OR | Mở rộng phạm vi sửa | Thêm ngoặc rõ |
| WHERE cot = NULL | Không chọn NULL | IS NULL |
| WHERE cot <> x tưởng gồm NULL | Bỏ sót NULL | OR IS NULL khi cần |
| NOT IN với subquery có NULL | Có thể trả tập rỗng không mong muốn | NOT EXISTS/chính sách NULL |
| SET giá tuyệt đối thay vì tương đối | Sai công thức | Phân biệt gán với tính |
| SET tăng 10% chạy hai lần | Tăng lũy kế 21% | Idempotency/campaign |
| Trừ kho mà không kiểm tra đủ | Tồn âm/lỗi CHECK | WHERE stock >= qty |
| Chấp nhận qty âm | Phép trừ thành phép cộng | Validate input |
| Dùng FLOAT tùy tiện cho tiền | Sai số | DECIMAL/NUMERIC, ROUND rõ |
| CASE nhánh rộng trước nhánh hẹp | Phân loại sai | Sắp WHEN đúng ưu tiên |
| CASE thiếu ELSE | NULL ngoài dự kiến | ELSE cột cũ hoặc WHERE |
| COALESCE NULL thành 0 vô điều kiện | Che thiếu dữ liệu | Định nghĩa NULL |
| Subquery SET trả nhiều hàng | Lỗi hoặc không xác định | UNIQUE/chọn nguồn rõ |
| Subquery không hàng | Gán NULL | EXISTS hoặc chính sách thiếu |
| UPDATE JOIN một đích nhiều nguồn | Giá trị không xác định | Bảo đảm cardinality |
| Dùng UPDATE JOIN sai phương ngữ | Lỗi cú pháp | Kiểm tra DBMS/phiên bản |
| Hoán đổi hai cột bằng SET mà không kiểm chứng | Khác hành vi giữa hệ | Theo ngữ nghĩa DBMS |
| SELECT preview rồi tin không đổi | Race condition | Transaction/isolation/version |
| Không kiểm tra row count | Tưởng sửa thành công | Kiểm tra và phản hồi |
| Ghi giá trị tuyệt đối từ SELECT trước | Lost update | UPDATE tương đối/locking |
| Quên tăng version khi ghi | Optimistic lock sai | Quy tắc version nhất quán |
| COMMIT rồi nghĩ ROLLBACK đảo được | Không khôi phục | Backup/audit/recovery |
| Batch không có khóa/ID ổn định | Bỏ sót/trùng thao tác | Chọn khóa, locking |
| Lọc ngày đến 23:59:59 | Bỏ sót phần giây | Khoảng nửa mở |
| Đổi khóa chính tùy tiện | FK/cascade tác động | Hiểu ràng buộc |
| UPDATE bản giá lịch sử | Mất giá quá khứ | Phiên bản hiệu lực/as-of |

## 36. Bộ ca kiểm thử quan trọng

| Trường hợp | Điều cần xác minh |
|---|---|
| Một mã hợp lệ | Chỉ một hàng mục tiêu được sửa |
| Mã không tồn tại | Không tự INSERT, phản hồi phù hợp |
| Nhiều hàng cùng danh mục | Sửa đúng tập theo WHERE |
| Trạng thái không cho phép | Không sửa |
| Giá ở đúng cận dưới | Được chọn nếu >= |
| Giá ở đúng cận trên | Không được chọn nếu < |
| Cột lọc có NULL | Dùng IS NULL/chính sách đúng |
| Tồn kho vừa đủ | Sau trừ còn 0 |
| Tồn kho thiếu | Không trừ |
| Số lượng bằng 0 hoặc âm | Bị từ chối |
| Phép tăng giá chạy lại | Phát hiện việc không idempotent |
| Subquery không có nguồn | Không gán NULL sai |
| Subquery nhiều nguồn | Không chọn dữ liệu bất định |
| CASE nhiều WHEN cùng thỏa | Nhánh ưu tiên đúng |
| CASE không khớp | ELSE đúng |
| Decimal gần giới hạn | Không overflow/sai rounding |
| Gán giá trị không đổi | Hiểu matched/changed rows |
| Trigger/audit | Side effect đúng thiết kế |
| FK/UNIQUE/CHECK lỗi | Transaction xử lý đúng |
| Version đã thay đổi | UPDATE không ghi đè |
| Hai request cùng trừ kho | Không mất cập nhật |
| Transaction có lỗi giữa chừng | Không để dữ liệu dở dang |
| Tenant khác cùng ID | Không bị sửa |
| Thời điểm đúng biên ngày | Điều kiện [start,end) đúng |
| Retry sau timeout | Không áp dụng nghiệp vụ hai lần |

## 37. Bài tập thực hành có đáp án

Bộ dữ liệu là bảng san_pham ở phần 3, và mỗi bài độc lập từ dữ liệu ban đầu nếu không nói khác. Các câu UPDATE chỉ dành cho môi trường bài tập.

### Bài 1 — Đặt giá cố định

Đặt gia_ban của P01 thành 130000.

<details>
<summary>Đáp án</summary>

~~~sql
UPDATE san_pham
SET gia_ban = 130000
WHERE ma_san_pham = 'P01';
~~~

</details>

### Bài 2 — Tăng tồn kho

Tăng tồn của P03 thêm 7. Tồn mới là bao nhiêu?

<details>
<summary>Đáp án</summary>

~~~sql
UPDATE san_pham
SET so_luong_ton = so_luong_ton + 7
WHERE ma_san_pham = 'P03';
~~~

Tồn từ 20 lên **27**.

</details>

### Bài 3 — Tăng giá có lọc

Tăng 10% giá các sản phẩm ACTIVE thuộc danh mục A.

<details>
<summary>Đáp án</summary>

~~~sql
UPDATE san_pham
SET gia_ban = ROUND(gia_ban * 1.10, 2)
WHERE ma_danh_muc = 'A'
  AND trang_thai = 'ACTIVE';
~~~

P01 tăng lên 110000; P02 tăng lên 220000.

</details>

### Bài 4 — UPDATE thiếu WHERE

Nếu viết SET trang_thai='STOP' mà không có WHERE thì sao?

<details>
<summary>Đáp án</summary>

Có thể chuyển **toàn bộ hàng** thành STOP. Cần thêm điều kiện phạm vi và xem trước bằng SELECT.

</details>

### Bài 5 — Hết hàng

Chỉ những hàng ACTIVE có tồn bằng 0 chuyển thành HET_HANG. Mã nào được sửa?

<details>
<summary>Đáp án</summary>

~~~sql
UPDATE san_pham
SET trang_thai = 'HET_HANG'
WHERE trang_thai = 'ACTIVE'
  AND so_luong_ton = 0;
~~~

Chỉ **P02**.

</details>

### Bài 6 — CASE theo tồn

Tồn 0 là HET_HANG, từ 1 đến 4 là SAP_HET, còn lại ACTIVE. Không sửa STOP.

<details>
<summary>Đáp án</summary>

~~~sql
UPDATE san_pham
SET trang_thai = CASE
    WHEN so_luong_ton = 0 THEN 'HET_HANG'
    WHEN so_luong_ton < 5 THEN 'SAP_HET'
    ELSE 'ACTIVE'
END
WHERE trang_thai <> 'STOP';
~~~

P02 thành HET_HANG; P05 thành SAP_HET; P04 vẫn STOP.

</details>

### Bài 7 — NULL

Gán 'KHAC' cho mã danh mục đang NULL.

<details>
<summary>Đáp án</summary>

~~~sql
UPDATE san_pham
SET ma_danh_muc = 'KHAC'
WHERE ma_danh_muc IS NULL;
~~~

P05 đổi.

</details>

### Bài 8 — Phủ định và NULL

Vì sao WHERE ma_danh_muc <> 'A' bỏ qua P05?

<details>
<summary>Đáp án</summary>

Vì P05 có ma_danh_muc NULL; so sánh <> với NULL trả UNKNOWN. Nếu muốn lấy cả NULL, thêm **OR ma_danh_muc IS NULL**.

</details>

### Bài 9 — Giá trị biên

Giảm 5% cho giá từ 50000 đến dưới 100000. Những mã nào được chọn?

<details>
<summary>Đáp án</summary>

~~~sql
UPDATE san_pham
SET gia_ban = ROUND(gia_ban * 0.95, 2)
WHERE gia_ban >= 50000
  AND gia_ban < 100000;
~~~

P03 và P04; P01 có giá 100000 nên không thỏa cận trên.

</details>

### Bài 10 — Trừ kho an toàn

Trừ 6 tồn P01 nếu đủ.

<details>
<summary>Đáp án</summary>

~~~sql
UPDATE san_pham
SET so_luong_ton = so_luong_ton - 6
WHERE ma_san_pham = 'P01'
  AND so_luong_ton >= 6;
~~~

Tồn từ 10 còn 4.

</details>

### Bài 11 — Số lượng âm

Tại sao qty = -3 phải bị từ chối trước khi dùng stock = stock - qty?

<details>
<summary>Đáp án</summary>

Vì trừ số âm sẽ **tăng kho thêm 3**. Validate qty > 0 trước khi bind; constraint stock >= 0 không phát hiện lỗi nghiệp vụ này.

</details>

### Bài 12 — Không idempotent

P01 giá 100000. Chạy tăng giá 10% hai lần. Giá cuối là bao nhiêu?

<details>
<summary>Đáp án</summary>

100000 → 110000 → **121000**. Phép tính tương đối không idempotent; cần đánh dấu chiến dịch nếu chỉ muốn tăng một lần.

</details>

### Bài 13 — Nhiều cột

Chuyển P02 sang HET_HANG, tăng phiên bản một đơn vị và ghi timestamp.

<details>
<summary>Đáp án</summary>

~~~sql
UPDATE san_pham
SET trang_thai = 'HET_HANG',
    phien_ban = phien_ban + 1,
    ngay_cap_nhat = CURRENT_TIMESTAMP
WHERE ma_san_pham = 'P02'
  AND so_luong_ton = 0;
~~~

</details>

### Bài 14 — CASE thiếu ELSE

Có rủi ro gì nếu CASE chỉ có WHEN stock=0 THEN 'HET_HANG' và UPDATE toàn bảng?

<details>
<summary>Đáp án</summary>

Những hàng stock khác 0 có thể nhận NULL, làm hỏng trạng thái hoặc gây lỗi NOT NULL. Thêm ELSE hoặc WHERE giới hạn phạm vi.

</details>

### Bài 15 — Scalar subquery không có nguồn

Nếu SET gia = (SELECT gia_moi ...), nhưng subquery không trả dòng, điều gì xảy ra?

<details>
<summary>Đáp án</summary>

Scalar subquery thường trả NULL khi không có dòng. Cần EXISTS để tránh cập nhật hàng không có nguồn hoặc quy tắc default có chủ đích.

</details>

### Bài 16 — Nhiều nguồn khớp

Một sản phẩm khớp hai mức tỷ lệ trong UPDATE JOIN. Có thể yên tâm DBMS tự chọn đúng mức không?

<details>
<summary>Đáp án</summary>

**Không.** Việc chọn giá trị có thể bất định hoặc báo lỗi. Cần ràng buộc nguồn duy nhất hoặc quy tắc lựa chọn rõ, ví dụ bản giá có hiệu lực theo thời điểm.

</details>

### Bài 17 — EXISTS

Đánh dấu sản phẩm đã có chi tiết đơn thành DA_CO_DON.

<details>
<summary>Đáp án</summary>

~~~sql
UPDATE san_pham
SET trang_thai = 'DA_CO_DON'
WHERE EXISTS (
    SELECT 1
    FROM chi_tiet_don ct
    WHERE ct.ma_san_pham = san_pham.ma_san_pham
);
~~~

</details>

### Bài 18 — Phương ngữ

Cú pháp UPDATE ... JOIN ... SET thuộc DBMS nào phổ biến?

<details>
<summary>Đáp án</summary>

**MySQL**. PostgreSQL dùng UPDATE ... SET ... FROM; SQL Server dùng UPDATE alias ... FROM ... JOIN; Oracle thường dùng subquery/MERGE.

</details>

### Bài 19 — Lost update

Tại sao hai giao dịch cùng đọc tồn 10, một ghi 8 và một ghi 7 có thể làm mất một lần trừ kho?

<details>
<summary>Đáp án</summary>

Hai giá trị mới được tính từ cùng giá trị cũ. Ghi sau có thể ghi đè ghi trước. Cần cập nhật tương đối tại DB, giao dịch/locking hoặc optimistic locking phù hợp.

</details>

### Bài 20 — Version

Viết UPDATE trừ 2 kho P01 chỉ khi phien_ban=4; sau đó tăng version.

<details>
<summary>Đáp án</summary>

~~~sql
UPDATE san_pham
SET so_luong_ton = so_luong_ton - 2,
    phien_ban = phien_ban + 1
WHERE ma_san_pham = 'P01'
  AND so_luong_ton >= 2
  AND phien_ban = 4;
~~~

Nếu không hàng nào được sửa, ứng dụng phải xử lý xung đột hoặc điều kiện không đáp ứng.

</details>

### Bài 21 — Preview

Viết SELECT hiển thị giá cũ và giá dự kiến sau tăng 10% cho ACTIVE thuộc A.

<details>
<summary>Đáp án</summary>

~~~sql
SELECT
    ma_san_pham,
    gia_ban AS gia_cu,
    ROUND(gia_ban * 1.10, 2) AS gia_moi
FROM san_pham
WHERE ma_danh_muc = 'A'
  AND trang_thai = 'ACTIVE';
~~~

</details>

### Bài 22 — ROLLBACK

Phát hiện UPDATE sai WHERE trong transaction chưa commit. Có thể làm gì?

<details>
<summary>Đáp án</summary>

Nếu thao tác thuộc transaction hỗ trợ rollback, dùng **ROLLBACK trước COMMIT**. Sau COMMIT cần phục hồi/đảo dữ liệu theo quy trình khác.

</details>

### Bài 23 — PostgreSQL RETURNING

Viết UPDATE tăng 10% giá P01 và trả giá mới.

<details>
<summary>Đáp án</summary>

~~~sql
UPDATE san_pham
SET gia_ban = ROUND(gia_ban * 1.10, 2)
WHERE ma_san_pham = 'P01'
RETURNING ma_san_pham, gia_ban;
~~~

</details>

### Bài 24 — Soft delete

Muốn ẩn P03 khỏi danh sách nhưng vẫn giữ quan hệ lịch sử, chọn UPDATE hay DELETE?

<details>
<summary>Đáp án</summary>

Có thể **UPDATE trang_thai = 'DA_XOA'** (soft delete). Cần lọc trạng thái khi đọc, giữ audit và hiểu constraint/FK vẫn còn.

</details>

### Bài 25 — Cận ngày

Vì sao lọc ngày bằng [đầu ngày, đầu ngày kế tiếp) thường tốt hơn cận trên 23:59:59?

<details>
<summary>Đáp án</summary>

Vì timestamp có phần giây và độ chính xác đa dạng. Cận trên loại trừ ở đầu ngày kế tiếp tránh bỏ sót giá trị sát cuối ngày, khi mốc được tính đúng múi giờ nghiệp vụ.

</details>

### Bài 26 — Thứ tự SET

Vì sao không mặc định SET a=b, b=a hoán đổi hai cột đúng trên mọi DBMS?

<details>
<summary>Đáp án</summary>

Một số hệ (đáng chú ý MySQL single-table UPDATE) có quy tắc thứ tự đánh giá gán cột khác. Cần phương án tương thích cụ thể và kiểm chứng giá trị cũ/mới.

</details>

### Bài 27 — Affected rows

P01 đã ACTIVE; UPDATE SET trang_thai='ACTIVE' WHERE id='P01'. Có thể kết luận giá trị thực sự đổi không?

<details>
<summary>Đáp án</summary>

**Không.** Hàng khớp WHERE nhưng trạng thái không đổi. Matched/changed row count và trigger/audit có thể khác theo DBMS/driver.

</details>

### Bài 28 — Multi-tenant

Hai tenant đều có mã sản phẩm P01. Cần thêm gì vào WHERE để không sửa sai tenant?

<details>
<summary>Đáp án</summary>

Thêm **tenant_id = :current_tenant** vào WHERE bên cạnh ma_san_pham = 'P01'. Tenant phải đến từ ngữ cảnh bảo mật đáng tin.

</details>

### Bài 29 — Dữ liệu lịch sử

Vì sao UPDATE đè giá cũ có thể khiến báo cáo đơn quá khứ sai?

<details>
<summary>Đáp án</summary>

Giá đã áp dụng trong quá khứ bị mất. Nếu cần lưu thay đổi theo thời gian, nên giữ phiên bản giá với khoảng valid_from/valid_to và truy vấn as-of.

</details>

### Bài 30 — Tổng hợp nghiệp vụ

Hãy viết UPDATE trừ 3 tồn P01, chỉ khi ACTIVE, đủ hàng, đúng tenant và phiên bản; đồng thời ghi thời điểm và tăng phiên bản.

<details>
<summary>Đáp án</summary>

~~~sql
UPDATE san_pham
SET so_luong_ton = so_luong_ton - ?,
    phien_ban = phien_ban + 1,
    ngay_cap_nhat = CURRENT_TIMESTAMP
WHERE tenant_id = ?
  AND ma_san_pham = ?
  AND trang_thai = 'ACTIVE'
  AND so_luong_ton >= ?
  AND phien_ban = ?;
~~~

Bind qty=3 ở hai vị trí tương ứng, tenant từ ngữ cảnh xác thực, mã P01, phiên bản đã đọc. Bảng thực tế giả định có cột tenant_id. Kiểm tra affected row count và đặt cập nhật cùng ghi đơn trong transaction phù hợp.

</details>

## 38. Kết luận và những nguyên tắc phải nhớ

1. **UPDATE** sửa hàng đã tồn tại; **SET** tính giá trị mới, **WHERE** giới hạn phạm vi sửa.
2. **Không có WHERE** có thể sửa cả bảng. Hãy SELECT xem trước, kiểm tra quyền và dùng transaction phù hợp.
3. **SET gia = 120000** khác **SET gia = gia * 1.10**; biểu thức tương đối không tự idempotent.
4. **CASE** định giá trị mới theo nhánh; **WHERE** chọn hàng. Thiếu ELSE có thể tạo NULL.
5. **NULL** chịu logic ba giá trị trong WHERE; IS NULL và quy tắc xử lý NULL phải rõ.
6. **DECIMAL/NUMERIC** và quy tắc ROUND quan trọng khi cập nhật tiền; giá trị mới phải nằm trong giới hạn kiểu/constraint.
7. **Scalar subquery** phải có cardinality phù hợp; UPDATE JOIN/FROM không được để một hàng đích có nhiều nguồn mâu thuẫn.
8. **PostgreSQL, SQL Server, MySQL, Oracle, SQLite** có cú pháp cập nhật từ bảng khác, xử lý thời gian, RETURNING/OUTPUT và giới hạn số hàng khác nhau.
9. Khi trừ tồn, dùng biểu thức tương đối và điều kiện **stock >= qty**, đồng thời validate qty > 0.
10. **Optimistic locking** với version giúp phát hiện hàng đã đổi; ứng dụng phải xử lý trường hợp 0 hàng.
11. **Transaction** giúp nhóm các bước liên quan, nhưng không thay thế idempotency, kiểm tra concurrency hoặc audit.
12. **Matched rows** và **changed rows** không đồng nghĩa ở mọi DBMS/driver.
13. Với hệ nhiều tenant, danh sách ID và batch, phạm vi quyền, khóa và điều kiện lọc phải đầy đủ.
14. Với giá và dữ liệu lịch sử, UPDATE đè có thể không phù hợp; cần mô hình phiên bản hiệu lực và truy vấn theo thời điểm.
15. Một UPDATE an toàn phải **chọn đúng hàng**, **tính đúng giá trị mới** và **giữ được tính nhất quán khi nhiều thao tác cùng diễn ra**.

### Tài liệu tham khảo theo hệ quản trị

Nên đối chiếu tài liệu chính thức đúng DBMS và phiên bản khi triển khai:

- **PostgreSQL Documentation:** UPDATE, UPDATE FROM, RETURNING, Explicit Locking, Transaction Isolation.
- **MySQL Reference Manual:** UPDATE Statement, InnoDB Locking, NULL Handling, Numeric Functions.
- **Microsoft Learn — Transact-SQL:** UPDATE, OUTPUT Clause, CASE, ROUND, Locking and Transaction Isolation.
- **Oracle Database SQL Language Reference:** UPDATE Statement, MERGE, RETURNING Clause, Constraints, Date Arithmetic.
- **SQLite Documentation:** UPDATE, UPDATE FROM, RETURNING Clause, Transactions, Date And Time Functions.
- **Java JDBC:** PreparedStatement, executeUpdate, Transaction Management.

**Câu hỏi tự kiểm tra trước khi chạy UPDATE:** **“Hàng nào sẽ đổi, giá trị mới được tính từ dữ liệu nào, và nếu chạy lại hoặc có người khác sửa đồng thời thì kết quả còn đúng không?”**. Trả lời được ba câu đó là nền tảng của thao tác UPDATE chính xác và an toàn.
