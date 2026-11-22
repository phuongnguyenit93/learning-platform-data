# Chuyển thực thể mạnh và thực thể yếu thành bảng

## Mục tiêu học tập

Khi thiết kế cơ sở dữ liệu, sơ đồ thực thể–liên kết (ER) giúp mô tả những đối tượng nghiệp vụ và mối liên hệ giữa chúng. Tuy nhiên, cơ sở dữ liệu quan hệ cần các **bảng, cột, khóa và ràng buộc cụ thể**. Một bước ánh xạ quan trọng là phân biệt **thực thể mạnh** (*strong entity*) với **thực thể yếu** (*weak entity*) để không làm mất ý nghĩa định danh và phụ thuộc tồn tại.

Sau bài học, người học có thể:

1. Nhận biết thực thể mạnh, thực thể yếu, **thực thể chủ sở hữu**, **mối liên kết định danh** và **khóa bộ phận**.
2. Chuyển thực thể mạnh thành bảng với khóa chính thích hợp và chuyển thực thể yếu thành bảng với khóa chính gồm khóa chủ sở hữu cộng khóa bộ phận.
3. Thiết lập chính xác **PRIMARY KEY**, **FOREIGN KEY**, **NOT NULL**, **UNIQUE** và các ràng buộc nghiệp vụ bổ sung trong SQL.
4. Xử lý trường hợp chủ sở hữu có khóa ghép, nhiều tầng thực thể yếu và bảng dùng định danh thay thế (*surrogate key*).
5. Phân biệt thực thể yếu với một thực thể mạnh có khóa ngoại, bảng nối quan hệ N–N và bảng phụ thuộc vòng đời nhưng có định danh độc lập.
6. Kiểm chứng mô hình bằng dữ liệu hợp lệ, phản ví dụ và các thao tác thêm, sửa, xóa.

**Bối cảnh học tập:** Bài thuộc chương **Mô hình quan hệ**, trong module **DATABASE_DATA_MODELING**. Mục tiêu của module là rèn kỹ năng chuyển yêu cầu nghiệp vụ thành mô hình dữ liệu rõ ràng, từ thực thể, quan hệ và ràng buộc đến chuẩn hóa, khóa, chỉ mục và lược đồ vật lý; đồng thời so sánh cách mô hình hóa quan hệ, document, đồ thị và phân tích để lựa chọn cấu trúc phù hợp, dễ tiến hóa và kiểm chứng. Bài này tập trung vào bước ánh xạ **mô hình ER sang mô hình quan hệ**, chưa đi sâu tối ưu chỉ mục hoặc hệ thống phi quan hệ.

## 1. Từ câu chuyện nghiệp vụ đến thực thể

Xét một hệ thống bán hàng với các yêu cầu:

- Mỗi khách hàng có một mã khách hàng duy nhất.
- Mỗi đơn hàng có mã đơn riêng, thuộc về một khách hàng.
- Một đơn hàng chứa nhiều **dòng hàng**; mỗi dòng có số thứ tự 1, 2, 3, ... **trong chính đơn đó**.
- Dòng số 1 có thể tồn tại ở nhiều đơn khác nhau; số thứ tự dòng đứng riêng không định danh được dòng hàng.
- Một dòng hàng không có ý nghĩa khi tách khỏi đơn hàng sở hữu nó.
- Mỗi dòng chứa sản phẩm, số lượng và **đơn giá đã chốt** tại thời điểm mua.

Ở đây, **ĐƠN_HÀNG** là ví dụ điển hình cho **thực thể mạnh**: có thể dùng mã đơn để định danh một đơn hàng mà không cần mã của thực thể khác. **DÒNG_ĐƠN_HÀNG** là ví dụ điển hình cho **thực thể yếu**: muốn chỉ đúng dòng nào phải biết **đơn hàng** và **số dòng trong đơn**.

Ví dụ:

| Mã đơn | Số dòng | Sản phẩm | Số lượng |
| --- | ---: | --- | ---: |
| DH101 | 1 | SP10 | 2 |
| DH101 | 2 | SP20 | 1 |
| DH102 | 1 | SP20 | 3 |

Khóa **số dòng = 1** xuất hiện hai lần, nhưng mỗi bộ **(mã đơn, số dòng)** là duy nhất. Điều đó gợi ý cách định danh **dòng đơn** phải bao gồm cả khóa chủ sở hữu.

## 2. Thực thể mạnh và thực thể yếu là gì?

### 2.1. Thực thể mạnh (*strong entity*)

Một kiểu thực thể mạnh có **khóa định danh riêng** mà không cần mượn khóa của một thực thể chủ sở hữu thông qua mối liên kết định danh. Ví dụ:

- **KHACH_HANG(ma_kh, ho_ten, email)** với khóa ứng viên ma_kh.
- **SAN_PHAM(ma_sp, sku, ten_sp)** với khóa ứng viên ma_sp.
- **DON_HANG(ma_dh, ma_kh, ngay_dat)** với khóa ứng viên ma_dh.

Đơn hàng có thể có khóa ngoại ma_kh tham chiếu khách hàng, nhưng nó vẫn là thực thể mạnh **theo cách định danh đang thiết kế**: mã ma_dh đủ xác định đơn hàng, không phải kết hợp mã khách với số thứ tự đơn theo khách.

Điều này minh họa một phân biệt quan trọng: **có khóa ngoại** hoặc **phụ thuộc nghiệp vụ vào thực thể khác** chưa đủ để kết luận một thực thể là yếu.

### 2.2. Thực thể yếu (*weak entity*)

Trong ký pháp ER cổ điển, kiểu thực thể yếu thường có các đặc điểm:

1. **Không có khóa định danh đầy đủ độc lập** trong mô hình đang xét.
2. Có **thực thể chủ sở hữu** (*owner*, hay *identifying entity*).
3. Tham gia **toàn phần** vào một **mối liên kết định danh** (*identifying relationship*): mỗi thể hiện yếu phải gắn với chủ sở hữu phù hợp.
4. Thường có **khóa bộ phận** (*partial key*, *discriminator*) để phân biệt các thể hiện yếu **trong phạm vi cùng chủ sở hữu**.

Với DONG_DON_HANG:

- Chủ sở hữu là DON_HANG.
- Mối liên kết định danh là “một dòng thuộc một đơn”.
- Khóa bộ phận là **so_dong**.
- Định danh đầy đủ là **(ma_dh, so_dong)**.

Khái niệm **toàn phần** ở đây hướng từ thực thể yếu tới chủ sở hữu: **mọi dòng hàng đều phải thuộc một đơn**. Nó không nhất thiết có nghĩa **mọi đơn đều phải có dòng ngay tại mọi thời điểm**. Hệ thống có thể cho phép tạo đơn nháp rỗng, rồi yêu cầu ít nhất một dòng trước khi xác nhận.

### 2.3. Khóa bộ phận khác khóa chính

**Khóa bộ phận** chỉ phân biệt các thực thể yếu **cùng một chủ sở hữu**. Nó chưa đủ để định danh trên toàn bộ tập thực thể yếu.

\[
\text{Định danh DòngĐơn} =
(\text{Định danh ĐơnHàng},\ \text{SốDòng})
\]

Số dòng 1 của DH101 và số dòng 1 của DH102 là **hai dòng khác nhau**. Do đó không được đặt PRIMARY KEY chỉ trên so_dong khi chuyển DONG_DON_HANG thành bảng.

**Lưu ý về thuật ngữ:** Khóa bộ phận không phải *partial index* của PostgreSQL. Đây là hai khái niệm khác nhau: một khái niệm ở mô hình ER, một khái niệm ở cấu trúc chỉ mục SQL.

## 3. Biểu diễn trên sơ đồ ER

Trong ký pháp Chen truyền thống:

- Thực thể mạnh: hình chữ nhật đơn.
- Thực thể yếu: hình chữ nhật đôi.
- Mối liên kết định danh: hình thoi đôi.
- Tham gia toàn phần của thực thể yếu: đường nối đôi.
- Khóa bộ phận: gạch dưới nét đứt (tùy biến thể ký pháp).

Các công cụ vẽ ER khác có thể dùng đường liền hoặc ký hiệu riêng cho liên kết định danh. Vì vậy, ngoài sơ đồ, luôn cần ghi bằng lời **định danh được tạo từ những thuộc tính nào**.

Sơ đồ Mermaid dưới đây nhấn mạnh **liên kết chủ sở hữu** và cấu trúc cột. Mermaid ER không tái hiện đầy đủ hình chữ nhật đôi/hình thoi đôi kiểu Chen; phần **(ma_dh, so_dong)** mới là tiêu chí định danh cần kiểm tra.

~~~~mermaid
erDiagram
    KHACH_HANG ||--o{ DON_HANG : dat
    DON_HANG ||--o{ DONG_DON_HANG : so_huu
    SAN_PHAM ||--o{ DONG_DON_HANG : xuat_hien_trong

    KHACH_HANG {
        varchar ma_kh PK
        varchar ho_ten
        varchar email
    }
    DON_HANG {
        varchar ma_dh PK
        varchar ma_kh FK
        date ngay_dat
        varchar trang_thai
    }
    SAN_PHAM {
        varchar ma_sp PK
        varchar ten_sp
        decimal gia_hien_tai
    }
    DONG_DON_HANG {
        varchar ma_dh PK,FK
        int so_dong PK
        varchar ma_sp FK
        int so_luong
        decimal don_gia
    }
~~~~

Diễn giải:

- DON_HANG được định danh bởi **ma_dh**.
- DONG_DON_HANG được định danh bởi cặp **(ma_dh, so_dong)**. Cột ma_dh vừa là **thành phần khóa chính**, vừa là **khóa ngoại** đến DON_HANG.
- Mỗi dòng đơn liên kết với một SAN_PHAM, nhưng ma_sp **không thuộc khóa định danh dòng** trong quy tắc này. Sản phẩm được chọn có thể thay đổi lúc chỉnh đơn nháp mà không thay đổi số định danh dòng.
- KHACH_HANG và SAN_PHAM là thực thể mạnh; việc chúng được tham chiếu không biến chúng thành thực thể yếu.

## 4. Quy tắc ánh xạ thực thể mạnh thành bảng

Với một kiểu thực thể mạnh E, quy trình cơ bản:

1. **Tạo một bảng** tương ứng với E.
2. Chuyển các **thuộc tính đơn trị** cần lưu thành cột, xác định miền giá trị và khả năng NULL.
3. Chọn một **khóa ứng viên** làm PRIMARY KEY.
4. Giữ ràng buộc cho các **khóa ứng viên còn lại** nếu nghiệp vụ có nhiều định danh hợp lệ.
5. Chuyển những quan hệ với thực thể khác thành khóa ngoại hoặc bảng liên kết tùy bội số và tính chất quan hệ.

Ví dụ khái niệm:

~~~~text
Thực thể mạnh KHÁCH_HÀNG:
  ma_kh (định danh), ho_ten, email

   ↓ ánh xạ

KHACH_HANG(ma_kh PK, ho_ten, email)
~~~~

SQL minh họa:

~~~~sql
CREATE TABLE khach_hang (
    ma_kh VARCHAR(20) PRIMARY KEY,
    ho_ten VARCHAR(120) NOT NULL,
    email VARCHAR(254)
);
~~~~

Trong mô hình này, email có thể thiếu nên **không** được mặc nhiên coi là khóa ứng viên. Nếu doanh nghiệp yêu cầu email duy nhất khi có giá trị, có thể bổ sung ràng buộc tương ứng.

Đối với thuộc tính có cấu trúc hoặc đa trị, cần quyết định cách mô hình hóa thích hợp. Ví dụ một khách có nhiều số điện thoại thường không nên ép vào một ô chuỗi phân cách bằng dấu phẩy nếu nghiệp vụ cần truy vấn từng số. Đó là vấn đề ánh xạ thuộc tính, được xem xét riêng với bài toán định danh thực thể yếu.

## 5. Quy tắc ánh xạ thực thể yếu thành bảng

Giả sử W là kiểu thực thể yếu, E là thực thể chủ sở hữu, và P là khóa bộ phận của W. Với dạng liên kết định danh phổ biến **mỗi W thuộc đúng một E**:

1. **Tạo một bảng riêng cho W.**
2. Đưa các thuộc tính của W, bao gồm khóa bộ phận P, thành cột.
3. **Đưa khóa chính của bảng E sang bảng W** làm khóa ngoại tham chiếu chủ sở hữu.
4. **Đặt khóa chính của W bằng tổ hợp khóa chủ sở hữu và khóa bộ phận.**
5. Buộc các thành phần định danh **NOT NULL** (PRIMARY KEY SQL đã bao hàm yêu cầu này).
6. Chọn hành vi xóa/cập nhật chủ sở hữu phù hợp với vòng đời dữ liệu.

Viết khái quát:

\[
PK(W) = PK(E) \cup P
\]

Ký hiệu hợp ở đây mang ý nghĩa **kết hợp các thuộc tính khóa**, có phân biệt tên cột nếu hai phía trùng tên. Nếu PK của E gồm nhiều cột, phải chuyển **đầy đủ các thành phần** sang W.

Ví dụ:

~~~~text
DON_HANG(ma_dh PK, ma_kh FK, ngay_dat)
DONG_DON_HANG(
    ma_dh,       -- PK thành phần 1; FK tới DON_HANG
    so_dong,     -- PK thành phần 2, khóa bộ phận
    ma_sp,       -- FK tới SAN_PHAM
    so_luong,
    don_gia
)

PK(DONG_DON_HANG) = (ma_dh, so_dong)
FK(DONG_DON_HANG.ma_dh) → DON_HANG.ma_dh
~~~~

### Những ràng buộc tạo được bằng cách này

| Yêu cầu | Cách ánh xạ | Hệ quả |
| --- | --- | --- |
| Mỗi đơn có mã duy nhất | PRIMARY KEY trên DON_HANG.ma_dh | Không có hai đơn trùng mã |
| Mỗi dòng thuộc một đơn tồn tại | FK từ DONG_DON_HANG.ma_dh đến DON_HANG.ma_dh | Không tạo dòng mồ côi |
| Dòng phải có chủ sở hữu | ma_dh thuộc PK, không NULL | Không tạo dòng thiếu mã đơn |
| Số dòng không trùng trong một đơn | PK(ma_dh, so_dong) | Cùng đơn không có hai dòng số 1 |
| Các đơn khác nhau có thể dùng số dòng giống nhau | Không đặt UNIQUE(so_dong) toàn bảng | DH101 và DH102 cùng có dòng 1 |
| Dòng tham chiếu sản phẩm | FK từ ma_sp tới SAN_PHAM.ma_sp | Không chọn sản phẩm không tồn tại |
| Số lượng phải dương | CHECK(so_luong > 0) và NOT NULL | Chặn số lượng âm, 0 hoặc thiếu |

**Quan trọng:** Không cần tạo thêm một bảng chỉ để biểu diễn **mối liên kết định danh 1–N** giữa đơn và dòng, nếu bảng yếu đã chứa khóa chủ sở hữu. Việc tách thành bảng nối vô nghĩa có thể làm loãng hoặc mất ràng buộc định danh vốn cần nằm trực tiếp trong DONG_DON_HANG.

## 6. Ví dụ PostgreSQL hoàn chỉnh và có thể kiểm tra

Đoạn DDL dưới đây tạo bốn bảng để minh họa đồng thời thực thể mạnh, thực thể yếu, FK và các ràng buộc giá trị. Các lệnh dùng cú pháp **PostgreSQL**; chạy trên cơ sở dữ liệu thử nghiệm trống theo thứ tự đã trình bày.

~~~~sql
CREATE TABLE khach_hang (
    ma_kh VARCHAR(20) PRIMARY KEY,
    ho_ten VARCHAR(120) NOT NULL
);

CREATE TABLE san_pham (
    ma_sp VARCHAR(20) PRIMARY KEY,
    ten_sp VARCHAR(150) NOT NULL,
    gia_hien_tai NUMERIC(12, 2) NOT NULL,
    CONSTRAINT ck_sp_gia CHECK (gia_hien_tai >= 0)
);

CREATE TABLE don_hang (
    ma_dh VARCHAR(20) PRIMARY KEY,
    ma_kh VARCHAR(20) NOT NULL,
    ngay_dat DATE NOT NULL,
    trang_thai VARCHAR(20) NOT NULL DEFAULT 'nhap',
    CONSTRAINT fk_don_khach
        FOREIGN KEY (ma_kh) REFERENCES khach_hang(ma_kh)
        ON DELETE RESTRICT,
    CONSTRAINT ck_don_trang_thai
        CHECK (trang_thai IN ('nhap', 'xac_nhan', 'huy'))
);

CREATE TABLE dong_don_hang (
    ma_dh VARCHAR(20) NOT NULL,
    so_dong INTEGER NOT NULL,
    ma_sp VARCHAR(20) NOT NULL,
    so_luong INTEGER NOT NULL,
    don_gia NUMERIC(12, 2) NOT NULL,
    CONSTRAINT pk_dong_don PRIMARY KEY (ma_dh, so_dong),
    CONSTRAINT fk_dong_don
        FOREIGN KEY (ma_dh) REFERENCES don_hang(ma_dh)
        ON DELETE CASCADE,
    CONSTRAINT fk_dong_san_pham
        FOREIGN KEY (ma_sp) REFERENCES san_pham(ma_sp)
        ON DELETE RESTRICT,
    CONSTRAINT ck_dong_stt CHECK (so_dong > 0),
    CONSTRAINT ck_dong_so_luong CHECK (so_luong > 0),
    CONSTRAINT ck_dong_gia CHECK (don_gia >= 0)
);
~~~~

**Ý nghĩa của ba lựa chọn khác nhau:** DON_HANG là thực thể mạnh dù **ma_kh** là FK bắt buộc. DONG_DON_HANG là thực thể yếu vì khóa của nó **chứa ma_dh của chủ sở hữu** và khóa bộ phận **so_dong**. Còn **ma_sp** là FK tới một thực thể mạnh khác, không tham gia định danh dòng theo quy tắc nghiệp vụ của ví dụ.

### 6.1. Nạp dữ liệu

~~~~sql
INSERT INTO khach_hang (ma_kh, ho_ten) VALUES
    ('KH01', 'Nguyễn An'),
    ('KH02', 'Trần Bình');

INSERT INTO san_pham (ma_sp, ten_sp, gia_hien_tai) VALUES
    ('SP10', 'Sổ tay', 120000),
    ('SP20', 'Bút viết', 45000);

INSERT INTO don_hang (ma_dh, ma_kh, ngay_dat, trang_thai) VALUES
    ('DH101', 'KH01', DATE '2026-10-01', 'xac_nhan'),
    ('DH102', 'KH02', DATE '2026-10-02', 'nhap');

INSERT INTO dong_don_hang
    (ma_dh, so_dong, ma_sp, so_luong, don_gia)
VALUES
    ('DH101', 1, 'SP10', 2, 115000),
    ('DH101', 2, 'SP20', 1, 45000),
    ('DH102', 1, 'SP20', 3, 45000);
~~~~

### 6.2. Truy vấn danh tính dòng và tổng tiền

~~~~sql
SELECT
    dh.ma_dh,
    kh.ho_ten,
    dd.so_dong,
    sp.ten_sp,
    dd.so_luong,
    dd.don_gia,
    dd.so_luong * dd.don_gia AS thanh_tien
FROM dong_don_hang AS dd
JOIN don_hang AS dh ON dh.ma_dh = dd.ma_dh
JOIN khach_hang AS kh ON kh.ma_kh = dh.ma_kh
JOIN san_pham AS sp ON sp.ma_sp = dd.ma_sp
ORDER BY dh.ma_dh, dd.so_dong;
~~~~

| ma_dh | ho_ten | so_dong | ten_sp | so_luong | don_gia | thanh_tien |
| --- | --- | ---: | --- | ---: | ---: | ---: |
| DH101 | Nguyễn An | 1 | Sổ tay | 2 | 115000 | 230000 |
| DH101 | Nguyễn An | 2 | Bút viết | 1 | 45000 | 45000 |
| DH102 | Trần Bình | 1 | Bút viết | 3 | 45000 | 135000 |

Từ đó, tổng tiền của DH101 bằng **275000**, DH102 bằng **135000**. Đơn giá lịch sử của SP10 là **115000** ở dòng đơn, dù giá niêm yết hiện tại là **120000**. Bảo toàn thông tin lịch sử là một lý do nên đưa **don_gia** vào DONG_DON_HANG, thay vì luôn lấy từ SAN_PHAM.

### 6.3. Kiểm tra ràng buộc bằng phản ví dụ

Các lệnh sau được thiết kế để **thất bại khi chạy riêng từng lệnh** sau bước nạp dữ liệu:

~~~~sql
-- Lỗi khóa chính ghép: dòng 1 của DH101 đã tồn tại.
INSERT INTO dong_don_hang (ma_dh, so_dong, ma_sp, so_luong, don_gia)
VALUES ('DH101', 1, 'SP20', 1, 45000);

-- Lỗi FK: không có đơn DH999.
INSERT INTO dong_don_hang (ma_dh, so_dong, ma_sp, so_luong, don_gia)
VALUES ('DH999', 1, 'SP10', 1, 115000);

-- Lỗi FK: sản phẩm SP999 không tồn tại.
INSERT INTO dong_don_hang (ma_dh, so_dong, ma_sp, so_luong, don_gia)
VALUES ('DH101', 3, 'SP999', 1, 10000);

-- Lỗi CHECK: số lượng phải lớn hơn 0.
INSERT INTO dong_don_hang (ma_dh, so_dong, ma_sp, so_luong, don_gia)
VALUES ('DH101', 3, 'SP10', 0, 115000);

-- Lỗi NOT NULL: dòng yếu bắt buộc phải có mã đơn.
INSERT INTO dong_don_hang (ma_dh, so_dong, ma_sp, so_luong, don_gia)
VALUES (NULL, 3, 'SP10', 1, 115000);
~~~~

**Trường hợp hợp lệ cần thử:** Thêm dòng số 2 cho DH102 là hợp lệ dù DH101 đã có dòng số 2, vì khóa chính kiểm tra **cặp (ma_dh, so_dong)**.

~~~~sql
INSERT INTO dong_don_hang (ma_dh, so_dong, ma_sp, so_luong, don_gia)
VALUES ('DH102', 2, 'SP10', 1, 120000);
~~~~

Lưu ý các ví dụ dùng **ON DELETE CASCADE** cho dòng đơn chỉ để minh họa vòng đời phụ thuộc. Trong hệ thống cần lưu hóa đơn hoặc lịch sử kế toán, việc xóa vật lý đơn hàng có thể bị cấm theo nghiệp vụ, và việc dùng CASCADE phải được xem xét lại.

## 7. Trường hợp khóa chủ sở hữu là khóa ghép

Quy tắc ánh xạ thực thể yếu không giới hạn chủ sở hữu phải có khóa một cột. Khi chủ sở hữu có **khóa chính ghép**, thực thể yếu cần tiếp nhận **đầy đủ các thành phần khóa** của chủ.

Giả sử các số hóa đơn chỉ duy nhất **trong từng công ty**:

~~~~text
HOA_DON(tenant_id, so_hd, ngay_lap)
PK = (tenant_id, so_hd)

DONG_HOA_DON(tenant_id, so_hd, so_dong, noi_dung, so_tien)
PK = (tenant_id, so_hd, so_dong)
FK (tenant_id, so_hd) → HOA_DON(tenant_id, so_hd)
~~~~

Một bảng minh họa:

| tenant_id | so_hd | so_dong | noi_dung |
| ---: | --- | ---: | --- |
| 1 | HD001 | 1 | Dịch vụ A |
| 1 | HD001 | 2 | Dịch vụ B |
| 2 | HD001 | 1 | Dịch vụ C |

Số hóa đơn HD001 xuất hiện ở hai tenant; số dòng 1 cũng xuất hiện ở nhiều hóa đơn. Chỉ **bộ ba (tenant_id, so_hd, so_dong)** mới định danh duy nhất dòng hóa đơn toàn hệ thống.

~~~~sql
CREATE TABLE hoa_don (
    tenant_id BIGINT NOT NULL,
    so_hd VARCHAR(30) NOT NULL,
    ngay_lap DATE NOT NULL,
    PRIMARY KEY (tenant_id, so_hd)
);

CREATE TABLE dong_hoa_don (
    tenant_id BIGINT NOT NULL,
    so_hd VARCHAR(30) NOT NULL,
    so_dong INTEGER NOT NULL CHECK (so_dong > 0),
    noi_dung VARCHAR(200) NOT NULL,
    so_tien NUMERIC(14, 2) NOT NULL CHECK (so_tien >= 0),
    CONSTRAINT pk_dong_hoa_don
        PRIMARY KEY (tenant_id, so_hd, so_dong),
    CONSTRAINT fk_dong_hoa_don
        FOREIGN KEY (tenant_id, so_hd)
        REFERENCES hoa_don (tenant_id, so_hd)
        ON DELETE RESTRICT
);
~~~~

Nếu bỏ **tenant_id** khỏi FK, hệ thống có thể tham chiếu nhầm số hóa đơn của công ty khác; hơn nữa **so_hd** không phải khóa duy nhất toàn bảng, nên không thể là đích FK hợp lệ trong thiết kế này.

**Ghi chú mô hình:** HOA_DON trong ví dụ được xem là một loại thực thể có định danh logic **(tenant_id, so_hd)**. Việc một thực thể mạnh có khóa ghép vẫn có thể xảy ra; muốn phân loại nó là yếu hay mạnh đối với TENANT còn phải xét **mối liên kết định danh và ý nghĩa nghiệp vụ trong sơ đồ ER gốc**. Điểm cốt lõi của ví dụ là **dòng yếu kế thừa toàn bộ khóa của chủ sở hữu**, không tự ý rút gọn.

## 8. Chuỗi nhiều tầng thực thể yếu

Một thực thể yếu cũng có thể đóng vai trò **chủ sở hữu cho thực thể yếu khác**. Ví dụ trong quản lý xây dựng:

- **DU_AN** có mã dự án toàn cục.
- **HANG_MUC** có số hạng mục chỉ duy nhất trong từng dự án.
- **CONG_VIEC** có số công việc chỉ duy nhất trong từng hạng mục.

~~~~text
DU_AN(ma_du_an PK)

HANG_MUC(ma_du_an, so_hang_muc, ten_hang_muc)
PK = (ma_du_an, so_hang_muc)
FK ma_du_an → DU_AN.ma_du_an

CONG_VIEC(ma_du_an, so_hang_muc, so_cong_viec, mo_ta)
PK = (ma_du_an, so_hang_muc, so_cong_viec)
FK (ma_du_an, so_hang_muc)
    → HANG_MUC(ma_du_an, so_hang_muc)
~~~~

Không được đặt FK của CONG_VIEC chỉ tới DU_AN: công việc còn phải thuộc **đúng hạng mục** của dự án, và sự tồn tại của hạng mục cần được kiểm chứng. Mỗi tầng tiếp nhận **đầy đủ khóa của chủ sở hữu trực tiếp** và thêm khóa bộ phận của chính nó.

~~~~sql
CREATE TABLE du_an (
    ma_du_an VARCHAR(20) PRIMARY KEY
);

CREATE TABLE hang_muc (
    ma_du_an VARCHAR(20) NOT NULL,
    so_hang_muc INTEGER NOT NULL CHECK (so_hang_muc > 0),
    ten_hang_muc VARCHAR(120) NOT NULL,
    PRIMARY KEY (ma_du_an, so_hang_muc),
    FOREIGN KEY (ma_du_an) REFERENCES du_an(ma_du_an)
);

CREATE TABLE cong_viec (
    ma_du_an VARCHAR(20) NOT NULL,
    so_hang_muc INTEGER NOT NULL,
    so_cong_viec INTEGER NOT NULL CHECK (so_cong_viec > 0),
    mo_ta VARCHAR(200) NOT NULL,
    PRIMARY KEY (ma_du_an, so_hang_muc, so_cong_viec),
    FOREIGN KEY (ma_du_an, so_hang_muc)
        REFERENCES hang_muc(ma_du_an, so_hang_muc)
);
~~~~

Cách kế thừa khóa nhiều tầng rất rõ ràng ở mức logic nhưng làm **khóa dài dần**. Ở bước vật lý, có thể cân nhắc surrogate key cho những cấp sâu để giảm chi phí tham chiếu, miễn là các ràng buộc định danh theo nghiệp vụ vẫn được bảo vệ.

## 9. Có thể dùng surrogate key cho bảng thực thể yếu không?

Trong một hệ thống thực tế, lập trình viên có thể muốn cấp **id duy nhất toàn cục** cho mỗi dòng đơn để đơn giản hóa API và FK từ bảng khác. Khi đó có thể dùng:

~~~~text
DONG_DON_HANG(
    id PK,
    ma_dh FK NOT NULL,
    so_dong NOT NULL,
    ...
)

UNIQUE(ma_dh, so_dong)
~~~~

Đây là **cách triển khai vật lý khác** của cùng quy tắc nghiệp vụ “một dòng được đánh số trong một đơn”:

~~~~sql
CREATE TABLE dong_don_hang_id (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    ma_dh VARCHAR(20) NOT NULL
        REFERENCES don_hang(ma_dh) ON DELETE RESTRICT,
    so_dong INTEGER NOT NULL CHECK (so_dong > 0),
    ma_sp VARCHAR(20) NOT NULL REFERENCES san_pham(ma_sp),
    so_luong INTEGER NOT NULL CHECK (so_luong > 0),
    don_gia NUMERIC(12, 2) NOT NULL CHECK (don_gia >= 0),
    CONSTRAINT ak_dong_don_hang_id UNIQUE (ma_dh, so_dong)
);
~~~~

Trong bảng này:

- **id** là PK hệ thống cấp (*surrogate key*).
- **(ma_dh, so_dong)** vẫn là khóa ứng viên nghiệp vụ được thực thi bằng UNIQUE, cộng NOT NULL.
- **ma_dh** vẫn là FK bắt buộc đến chủ sở hữu.
- Không thể có hai dòng cùng so_dong trong cùng ma_dh; cũng không thể có dòng mồ côi.

**Không được** bỏ UNIQUE(ma_dh, so_dong) chỉ vì đã có PK(id): nếu bỏ, hai dòng cùng số thứ tự trong một đơn sẽ hợp lệ ở mức SQL, trái với yêu cầu nghiệp vụ.

### Thực thể yếu khái niệm và bảng có id độc lập

Trong cách hiểu ER cổ điển, thực thể yếu được **định danh qua khóa của chủ sở hữu kết hợp khóa bộ phận**. Khi thêm id toàn cục và chọn id làm PK, lược đồ SQL đã có một cách định danh độc lập về mặt kỹ thuật. Tuy vậy, **sự phụ thuộc tồn tại và tính duy nhất theo chủ sở hữu của nghiệp vụ không biến mất**; ta vẫn phải giữ NOT NULL, FK và UNIQUE(ma_dh, so_dong). Vì thế khi thảo luận, nên nói rõ đang phân loại **thực thể trong mô hình khái niệm** hay **khóa chính của bảng đã triển khai**.

Hai cách có những đánh đổi:

| Tiêu chí | PK ghép (ma_dh, so_dong) | PK id và UNIQUE(ma_dh, so_dong) |
| --- | --- | --- |
| Thể hiện định danh nghiệp vụ | Trực tiếp ngay trong PK | Qua alternate key |
| Khóa ngoại từ bảng khác đến dòng | Phải truyền ma_dh và so_dong | Có thể chỉ cần id |
| Kích thước khóa và số lượng chỉ mục | Không cần id riêng | Có thêm id và ràng buộc UNIQUE |
| Khả năng thay đổi số dòng | Là thay đổi PK và các FK liên quan | PK id ổn định, nhưng UNIQUE nghiệp vụ phải cập nhật |
| Bảo vệ quan hệ thuộc đơn | Qua PK chứa ma_dh và FK | Qua FK NOT NULL cùng UNIQUE |
| Ý nghĩa logic của dòng | Được nhận diện trong phạm vi đơn | Vẫn cần quy tắc nhận diện dòng trong phạm vi đơn |

Chọn cách nào phụ thuộc vào quy tắc nghiệp vụ, cách tham chiếu giữa các bảng, mức độ ổn định của số dòng và truy vấn thực tế. **Thêm surrogate key không tự động tốt hơn**, và cũng không phải lý do để bỏ ràng buộc đã có.

## 10. Thực thể yếu khác với thực thể mạnh có FK như thế nào?

Xét lại DON_HANG(ma_dh, ma_kh, ngay_dat):

- Đơn hàng **thuộc khách hàng** về mặt nghiệp vụ.
- Đơn có **ma_dh duy nhất toàn cục** nên định danh không cần kết hợp ma_kh.
- Vì vậy, trong mô hình hiện tại, DON_HANG có thể được xem là **thực thể mạnh** dù ma_kh là FK bắt buộc.

Nếu thay quy tắc thành “mỗi khách hàng có một số thứ tự đơn riêng, số thứ tự này được dùng lại giữa các khách”, mô hình có thể đổi thành:

~~~~text
DON_HANG(ma_kh, so_don_theo_khach, ngay_dat)
PK = (ma_kh, so_don_theo_khach)
FK ma_kh → KHACH_HANG.ma_kh
~~~~

Khi đó một đơn chỉ được định danh bằng **khách hàng + số đơn trong phạm vi khách**, và đơn có thể được mô hình hóa như thực thể yếu đối với khách hàng trong một mô hình ER thích hợp.

Từ hai ví dụ trên có thể rút ra tiêu chí:

| Câu hỏi | Thực thể mạnh có FK | Thực thể yếu cổ điển |
| --- | --- | --- |
| Có thể định danh mà không cần khóa chủ sở hữu không? | Có, theo khóa riêng của thực thể | Không, cần khóa chủ sở hữu và khóa bộ phận |
| FK tới thực thể khác có thể có không? | Có | Có, trong mối liên kết định danh |
| Mọi bản ghi có thể bắt buộc có bản ghi cha không? | Có thể | Có, theo sự tham gia toàn phần vào liên kết định danh |
| PK khi ánh xạ truyền thống | Khóa của chính thực thể | Khóa chủ sở hữu cộng khóa bộ phận |
| Ví dụ | Đơn có mã đơn toàn cục | Dòng số thứ tự trong một đơn |

**Phụ thuộc vòng đời khác phụ thuộc định danh.** Một tệp đính kèm có id toàn cục vẫn có thể bắt buộc thuộc một hồ sơ và bị xóa theo hồ sơ, nhưng không vì vậy mà tự động là thực thể yếu theo định nghĩa ER. Phải kiểm tra **cơ chế định danh** của tệp đính kèm trong mô hình.

## 11. Bảng nối N–N có phải thực thể yếu không?

Giả sử có SINH_VIEN(ma_sv) và LOP_HOC(ma_lop), một sinh viên học nhiều lớp, mỗi lớp có nhiều sinh viên. Mối liên kết **N–N** thường được ánh xạ thành:

~~~~text
DANG_KY(ma_sv, ma_lop, ngay_dang_ky, trang_thai)
PK = (ma_sv, ma_lop)   -- nếu mỗi sinh viên chỉ đăng ký một lần mỗi lớp
FK ma_sv → SINH_VIEN.ma_sv
FK ma_lop → LOP_HOC.ma_lop
~~~~

Bảng DANG_KY **có PK gồm hai FK**, nhưng không nhất thiết phải được gọi là thực thể yếu theo mọi ký pháp ER. Nó là **bảng liên kết** (*junction table*) hoặc biểu diễn của **thực thể kết hợp** (*associative entity*). Hai khái niệm liên quan nhưng không đồng nhất:

- Thực thể yếu cổ điển thường có **mối liên kết định danh với một chủ sở hữu** và khóa bộ phận phân biệt trong phạm vi chủ đó.
- Bảng nối N–N ghi nhận **một sự liên kết giữa các thực thể**, thường có khóa là tổ hợp khóa của **các phía tham gia**.
- Một thực thể kết hợp có thể vừa phụ thuộc tồn tại vào các phía tham gia vừa có thuộc tính riêng như ngày đăng ký và điểm; tùy mô hình và ký pháp, cách phân loại có thể khác.

Nếu cho phép sinh viên đăng ký lại lớp ở nhiều đợt, khóa **(ma_sv, ma_lop)** không còn đủ. Cần bổ sung **ma_dot** hoặc định danh lần đăng ký và ràng buộc phù hợp. Bất kể gọi là thực thể yếu hay kết hợp, **khóa phải phản ánh đúng sự kiện nghiệp vụ**.

## 12. Thuộc tính của mối liên kết định danh đặt ở đâu?

Giả sử mối liên kết định danh DON_HANG — DONG_DON_HANG có thêm thông tin “thời điểm dòng được thêm vào đơn”. Mỗi dòng thuộc **đúng một** đơn; thông tin này gắn với sự tồn tại của chính dòng trong đơn. Khi ánh xạ, thường có thể đặt thuộc tính:

~~~~text
DONG_DON_HANG(
    ma_dh,
    so_dong,
    ma_sp,
    so_luong,
    don_gia,
    thoi_diem_them
)
~~~~

Không cần một bảng chỉ chứa ma_dh, so_dong và thoi_diem_them nếu **mỗi dòng có đúng một quan hệ định danh với chủ sở hữu** và không có yêu cầu tách vòng đời hoặc lịch sử riêng.

Ngược lại, nếu một bản ghi có thể liên kết **nhiều thực thể cùng loại** hoặc mối liên kết có vòng đời độc lập, có thể cần bảng liên kết hoặc một thực thể riêng. Ví dụ lịch sử **chuyển dòng hàng qua các lô giao** có thể là các sự kiện giao hàng độc lập; không nên nhồi danh sách lô giao vào một cột của dòng đơn.

## 13. Tính toàn vẹn và vòng đời: FK bảo đảm điều gì?

### 13.1. Tham gia toàn phần từ thực thể yếu về phía chủ

Trong mô hình DONG_DON_HANG:

- **NOT NULL(ma_dh)** yêu cầu dòng có mã đơn.
- **FOREIGN KEY(ma_dh) REFERENCES DON_HANG(ma_dh)** yêu cầu mã đơn tồn tại.
- **PRIMARY KEY(ma_dh, so_dong)** yêu cầu định danh dòng vừa đủ và không trùng.

Ba điều kiện trên là cách thực thi thông thường của **tham gia toàn phần vào mối liên kết định danh**.

Nhưng chúng **không bảo đảm mọi đơn đều có ít nhất một dòng**. Đây là một yêu cầu ngược chiều: từ chủ sở hữu sang tập bản ghi con. Nếu quy tắc là “đơn ở trạng thái xac_nhan phải có dòng”, cần kiểm tra khi chuyển trạng thái, thường trong một **giao dịch** có kiểm soát đồng thời, hoặc bằng cơ chế cơ sở dữ liệu phù hợp.

### 13.2. Khóa ngoại và NULL

Khóa ngoại một cột có thể chấp nhận NULL nếu cột tham chiếu cho phép NULL. Điều này **không phù hợp với thực thể yếu bắt buộc có chủ sở hữu**.

Với FK ghép, mặc định SQL **MATCH SIMPLE** thường cho phép bỏ qua kiểm tra tham chiếu nếu một thành phần là NULL. Bởi vậy, các cột thuộc định danh của thực thể yếu nên được khai báo NOT NULL hoặc đặt trực tiếp trong PRIMARY KEY. Khi nghiệp vụ yêu cầu “tất cả thành phần cùng thiếu hoặc tất cả đều có”, cần xem xét MATCH FULL và hỗ trợ thực tế của DBMS.

### 13.3. Chọn hành vi khi chủ sở hữu bị xóa

| Chính sách FK | Hành vi với bản ghi yếu | Khi phù hợp |
| --- | --- | --- |
| ON DELETE CASCADE | Xóa các dòng yếu khi xóa chủ | Dữ liệu phụ hoàn toàn, không cần lịch sử độc lập |
| ON DELETE RESTRICT | Chặn xóa chủ nếu còn dòng yếu | Đơn hàng, hóa đơn, dữ liệu cần lưu vết |
| ON DELETE NO ACTION | Từ chối trạng thái vi phạm FK, thời điểm kiểm tra tùy DBMS/ràng buộc | Giao dịch thay đổi nhiều dòng |
| ON DELETE SET NULL | Đặt FK yếu thành NULL | **Thường không phù hợp** với FK định danh NOT NULL |
| Xóa mềm ở cấp ứng dụng | Giữ bản ghi, đánh dấu đã ngừng hoạt động/hủy | Cần truy xuất lịch sử và không muốn xóa vật lý |

Tính chất “yếu” không tự động quy định phải dùng CASCADE. **Định danh phụ thuộc chủ sở hữu** và **chính sách lưu giữ dữ liệu** là hai quyết định khác nhau.

### 13.4. Cập nhật định danh chủ sở hữu hoặc khóa bộ phận

Nếu đổi ma_dh đang được tham chiếu, phải bảo toàn khóa ngoại của các dòng. Có thể dùng ON UPDATE CASCADE trong những trường hợp phù hợp, hoặc quy định mã đơn bất biến. Nếu đổi so_dong, bạn đang đổi **một thành phần PK**, ảnh hưởng mọi bảng khác tham chiếu dòng. Đây là lý do một số hệ thống chọn **id ổn định** cho dòng ở mức vật lý, song vẫn giữ UNIQUE(ma_dh, so_dong) theo nghiệp vụ.

### 13.5. Khóa, chỉ mục và truy vấn

Trong PostgreSQL, PRIMARY KEY tạo chỉ mục duy nhất. Chỉ mục PK(ma_dh, so_dong) thường hỗ trợ các truy vấn tìm dòng theo ma_dh vì ma_dh là cột đầu. PostgreSQL **không tự tạo chỉ mục trên mọi FK của bảng con**; nếu thường lọc dòng theo sản phẩm, cân nhắc chỉ mục riêng:

~~~~sql
CREATE INDEX ix_dong_don_hang_ma_sp
    ON dong_don_hang (ma_sp);
~~~~

Chỉ mục phải dựa vào truy vấn và chi phí cập nhật dữ liệu. Điều này thuộc bước tối ưu **lược đồ vật lý**, còn quyết định PK và FK trước hết phải giữ đúng **ngữ nghĩa logic**.

## 14. Quy trình ánh xạ có thể áp dụng cho bài toán mới

Khi nhận một sơ đồ ER hoặc yêu cầu mô tả bằng lời, có thể thực hiện theo trình tự:

1. **Liệt kê thực thể và ý nghĩa của từng thể hiện.** Một bản ghi đại diện cho khách hàng, đơn, dòng đơn, phòng khách sạn hay một lần đăng ký?
2. **Xác định định danh độc lập.** Thực thể nào có khóa ứng viên đủ định danh mà không cần mượn khóa của chủ sở hữu thông qua quan hệ định danh?
3. **Nhận diện thực thể yếu.** Tìm thực thể cần biết chủ sở hữu mới xác định được một thể hiện, cùng mối liên kết định danh có tham gia toàn phần.
4. **Xác định khóa bộ phận.** Hỏi “trong phạm vi cùng một chủ, những thuộc tính nào phân biệt được các thể hiện yếu?”.
5. **Ánh xạ bảng mạnh.** Đưa các thuộc tính đơn trị, khóa chính và các khóa ứng viên khác vào bảng cùng miền giá trị/ràng buộc tương ứng.
6. **Ánh xạ bảng yếu.** Sao chép **đầy đủ khóa chủ sở hữu** làm FK, cộng khóa bộ phận tạo PK ghép; đặt các cột bắt buộc NOT NULL.
7. **Ánh xạ các liên kết khác.** Ví dụ dòng đơn tham chiếu sản phẩm là FK bổ sung; liên kết N–N có thể cần bảng nối.
8. **Quyết định vòng đời và thay đổi khóa.** Nêu rõ chính sách xóa chủ, cập nhật mã, chỉnh số thứ tự và xử lý dữ liệu lịch sử.
9. **Kiểm tra ràng buộc không diễn đạt được bằng PK/FK đơn giản.** Ví dụ đơn đã xác nhận phải có ít nhất một dòng, hoặc chủ sở hữu phải ở cùng tenant.
10. **Kiểm thử bằng phản ví dụ, sau đó tối ưu vật lý.** Thử mã chủ không tồn tại, trùng khóa bộ phận trong một chủ và cùng khóa bộ phận ở các chủ khác nhau.

### Bộ câu hỏi kiểm tra trước khi chốt lược đồ

| Câu hỏi | Dấu hiệu mô hình đúng |
| --- | --- |
| Nếu bỏ khóa chủ sở hữu, bảng yếu còn định danh được từng dòng không? | **Không**, theo cách nhận diện bằng khóa bộ phận của mô hình ER |
| Hai chủ khác nhau có thể có cùng khóa bộ phận không? | **Có**, khi nghiệp vụ cho phép |
| Hai dòng yếu cùng chủ có được trùng khóa bộ phận không? | **Không** |
| Dòng yếu có thể không có chủ không? | **Không**, nếu tham gia toàn phần vào mối liên kết định danh |
| FK của dòng có tham chiếu đúng toàn bộ khóa chủ không? | **Có**, kể cả khóa cha gồm nhiều cột |
| Có lưu lặp thông tin của chủ trong mỗi dòng yếu không cần thiết không? | Nên tránh khi thuộc tính đó phụ thuộc vào khóa của chủ, trừ nhu cầu lịch sử được mô hình hóa rõ |
| Nếu dùng id tự sinh, còn UNIQUE theo chủ và khóa bộ phận không? | **Có**, nếu quy tắc nghiệp vụ vẫn giữ nguyên |
| Nếu xóa chủ, điều gì xảy ra với con và lịch sử? | Có chính sách cụ thể phù hợp với vòng đời |

## 15. Những sai lầm phổ biến

| Sai lầm | Hậu quả | Hướng khắc phục |
| --- | --- | --- |
| Xem mọi bảng có FK là thực thể yếu | Phân loại sai DON_HANG chỉ vì có ma_kh | Xét **cách định danh**, không chỉ sự hiện diện của FK |
| Dùng so_dong làm PK độc lập | Hai đơn không được cùng có dòng số 1 | Dùng PK(ma_dh, so_dong) |
| Dùng UNIQUE(so_dong) toàn bảng | Hạn chế sai phạm vi duy nhất | Dùng UNIQUE hoặc PK ghép theo chủ |
| Chỉ dùng PK(id) cho dòng và bỏ UNIQUE(ma_dh, so_dong) | Cho phép trùng số dòng trong cùng đơn | Giữ alternate key nghiệp vụ |
| Cho ma_dh NULL trên dòng yếu | Dòng có thể không có chủ sở hữu | Buộc NOT NULL và FK |
| Có khóa cha ghép nhưng chỉ tham chiếu một cột | Khó xác định đúng chủ, có thể sai tenant | Truyền đầy đủ các thành phần khóa cha |
| Dùng ma_sp như thành phần khóa dòng mà không xác minh nghiệp vụ | Không thể đặt cùng sản phẩm ở hai dòng của đơn | Định danh dòng bằng khóa bộ phận ổn định, ví dụ so_dong |
| Dùng ON DELETE CASCADE mặc định | Có thể xóa nhầm dữ liệu lịch sử | Quyết định chính sách lưu trữ trước |
| Coi FK bảo đảm mỗi chủ phải có con | Có thể tồn tại đơn không có dòng | Thêm kiểm soát giao dịch/trạng thái khi cần |
| Chọn khóa bộ phận là trường hiển thị thường xuyên đổi | Mỗi lần sắp xếp dòng kéo theo đổi khóa | Tách định danh ổn định khỏi vị trí hiển thị nếu cần |

### Ví dụ bổ sung: khách sạn và số phòng

Một khách sạn có mã duy nhất **ma_ks**, các phòng được đánh số **101**, **102** trong từng khách sạn. **PHONG** là thực thể yếu nếu nghiệp vụ định danh phòng bằng **(ma_ks, so_phong)**.

~~~~text
KHACH_SAN(ma_ks PK, ten_ks)
PHONG(ma_ks, so_phong, loai_phong, trang_thai)
PK(PHONG) = (ma_ks, so_phong)
FK(PHONG.ma_ks) → KHACH_SAN.ma_ks
~~~~

Phòng 101 tại KS01 và phòng 101 tại KS02 được phép cùng tồn tại. Việc **so_phong** là chuỗi hay số nguyên phụ thuộc quy tắc mã phòng (một số khách sạn dùng A101, B02), không làm thay đổi yêu cầu **duy nhất trong phạm vi khách sạn**.

### Ví dụ bổ sung: người phụ thuộc của nhân viên

Nếu một nhân viên có nhiều người phụ thuộc, hệ thống có thể cấp **so_nguoi_phu_thuoc** trong phạm vi nhân viên:

~~~~text
NHAN_VIEN(ma_nv PK, ho_ten)
NGUOI_PHU_THUOC(ma_nv, so_nguoi_phu_thuoc, ho_ten, moi_quan_he)
PK = (ma_nv, so_nguoi_phu_thuoc)
FK ma_nv → NHAN_VIEN.ma_nv
~~~~

Không nên dùng **ho_ten người phụ thuộc** làm khóa bộ phận nếu có thể có hai người cùng tên. Số thứ tự nội bộ ổn định thường phù hợp hơn. Khi nghiệp vụ đổi sang định danh người phụ thuộc bằng mã toàn cục, cần đánh giá lại cách phân loại và ràng buộc thay vì giữ nguyên mô hình theo thói quen.

## 16. Bài tập thực hành có đáp án

### Bài 1 — Ánh xạ khách sạn và phòng

Yêu cầu: Mỗi khách sạn có ma_ks duy nhất. Mỗi phòng có so_phong chỉ duy nhất trong khách sạn; mọi phòng phải thuộc một khách sạn. Hãy xác định thực thể mạnh/yếu, khóa bộ phận, PK và FK.

**Đáp án:**

~~~~text
KHACH_SAN(ma_ks PK, ten_ks)                 -- thực thể mạnh
PHONG(ma_ks, so_phong, loai_phong)          -- thực thể yếu
PK(PHONG) = (ma_ks, so_phong)
FK(PHONG.ma_ks) → KHACH_SAN.ma_ks
Khóa bộ phận của PHONG = so_phong
~~~~

Trong SQL, đặt NOT NULL cho ma_ks và so_phong; PRIMARY KEY ghép đã bao hàm NOT NULL cho hai cột này.

### Bài 2 — Vì sao DON_HANG vẫn có thể là thực thể mạnh?

Yêu cầu: Mỗi đơn có ma_dh duy nhất toàn hệ thống và luôn có ma_kh tham chiếu khách hàng. Một đồng nghiệp nói DON_HANG là thực thể yếu chỉ vì có FK ma_kh.

**Đáp án:** Nhận xét đó chưa đúng. DON_HANG đã có định danh độc lập **ma_dh**. Khóa ngoại và bắt buộc thuộc về khách hàng thể hiện sự liên hệ và phụ thuộc tồn tại, chưa chứng minh đơn cần **khóa khách + khóa bộ phận** để được định danh. Theo quy tắc đang xét, DON_HANG có thể được mô hình hóa là thực thể mạnh.

### Bài 3 — Khóa chính sai phạm vi

Đề xuất:

~~~~sql
CREATE TABLE dong_don_sai (
    ma_dh VARCHAR(20) NOT NULL REFERENCES don_hang(ma_dh),
    so_dong INTEGER PRIMARY KEY,
    ma_sp VARCHAR(20) NOT NULL
);
~~~~

**Câu hỏi:** Thiết kế này sai ở đâu? Sửa thế nào?

**Đáp án:** PK chỉ trên so_dong nên không thể có dòng số 1 ở hai đơn khác nhau. Phải chuyển thành **PRIMARY KEY(ma_dh, so_dong)** và giữ FK ma_dh, hoặc dùng id làm PK nhưng có **UNIQUE(ma_dh, so_dong)**.

### Bài 4 — Dùng surrogate key nhưng vẫn phải bảo toàn nghiệp vụ

Đề xuất:

~~~~sql
CREATE TABLE dong_don_id_sai (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    ma_dh VARCHAR(20) NOT NULL REFERENCES don_hang(ma_dh),
    so_dong INTEGER NOT NULL,
    ma_sp VARCHAR(20) NOT NULL
);
~~~~

**Câu hỏi:** Dù có PK(id), lược đồ còn thiếu gì so với yêu cầu “mỗi số dòng chỉ xuất hiện một lần trong một đơn”?

**Đáp án:** Thiếu **UNIQUE(ma_dh, so_dong)**. Bổ sung:

~~~~sql
ALTER TABLE dong_don_id_sai
ADD CONSTRAINT ak_dong_don_theo_don
UNIQUE (ma_dh, so_dong);
~~~~

Nên thêm CHECK(so_dong > 0) nếu quy tắc đánh số yêu cầu số dòng dương.

### Bài 5 — FK ghép để không lẫn dữ liệu tenant

Cho HOA_DON(tenant_id, so_hd, ngay_lap) có PK(tenant_id, so_hd), DONG_HOA_DON có so_dong chỉ duy nhất trong một hóa đơn.

**Câu hỏi:** Khóa chính và khóa ngoại của DONG_HOA_DON là gì?

**Đáp án:** **PK(tenant_id, so_hd, so_dong)** và **FOREIGN KEY(tenant_id, so_hd) REFERENCES HOA_DON(tenant_id, so_hd)**. Nếu bỏ tenant_id sẽ mất điều kiện phân biệt hóa đơn của những tenant khác nhau.

### Bài 6 — Hai tầng thực thể yếu

DU_AN có ma_du_an; mỗi hạng mục có so_hang_muc trong dự án; mỗi công việc có so_cong_viec trong hạng mục.

**Câu hỏi:** Nếu chỉ đặt PK(ma_du_an, so_cong_viec) cho CONG_VIEC thì thiếu gì?

**Đáp án:** Thiếu **so_hang_muc**. Công việc số 1 có thể xuất hiện ở hai hạng mục khác nhau của cùng dự án. PK đúng theo giả định là **(ma_du_an, so_hang_muc, so_cong_viec)**; FK ghép đến HANG_MUC phải gồm **(ma_du_an, so_hang_muc)**.

### Bài 7 — Chọn chính sách xóa

Một đơn đã xuất hóa đơn và phải lưu lịch sử. Dòng đơn là thực thể yếu. Người thiết kế cho rằng cứ là thực thể yếu thì FK bắt buộc dùng ON DELETE CASCADE.

**Đáp án:** Không đúng. Thực thể yếu phải có chủ sở hữu để định danh, nhưng **cách lưu trữ lịch sử** là quy tắc khác. Với đơn phải lưu vết, có thể chọn **RESTRICT** hoặc ngăn xóa vật lý qua trạng thái/phân quyền; CASCADE chỉ hợp lý khi nghiệp vụ cho phép xóa cả đơn lẫn dòng.

### Bài 8 — Tham gia toàn phần và đơn rỗng

Hệ thống dùng PRIMARY KEY(ma_dh, so_dong) và FOREIGN KEY(ma_dh) cho DONG_DON_HANG. Nhưng một đơn đang ở trạng thái **xac_nhan** vẫn có thể không có dòng.

**Câu hỏi:** Đây có phải lỗi của FK không? Cần kiểm soát ở đâu?

**Đáp án:** Không. FK chỉ kiểm tra **mỗi dòng có một đơn hợp lệ**, không kiểm tra **mỗi đơn phải có dòng**. Điều kiện “chỉ được xác nhận đơn có ít nhất một dòng” phải được kiểm tra lúc chuyển trạng thái, tốt nhất trong cơ chế giao dịch bảo đảm điều kiện không bị thay đổi đồng thời ngoài ý muốn.

### Bài 9 — Phân biệt bảng nối với thực thể yếu

SINH_VIEN và LOP_HOC liên kết N–N qua DANG_KY(ma_sv, ma_lop, ngay_dang_ky). Một sinh viên chỉ đăng ký một lần cho mỗi lớp.

**Câu hỏi:** Vì sao DANG_KY có PK(ma_sv, ma_lop) nhưng không nhất thiết được mô tả là thực thể yếu theo mọi cách vẽ ER?

**Đáp án:** DANG_KY có thể là **bảng nối** của liên kết N–N hoặc một **thực thể kết hợp**. Khóa gồm hai FK phản ánh định danh của **sự liên kết giữa hai phía**, còn ví dụ thực thể yếu cổ điển thường có một chủ sở hữu và khóa bộ phận. Quyết định khái niệm cần dựa trên ý nghĩa thực thể và ký pháp ER; PK ghép hai FK một mình chưa đủ để kết luận.

## 17. Ghi nhớ các quy tắc cốt lõi

| Khái niệm | Cách kiểm tra |
| --- | --- |
| **Thực thể mạnh** | Có khóa định danh riêng, không phải mượn khóa chủ sở hữu thông qua liên kết định danh |
| **Thực thể yếu** | Cần chủ sở hữu và khóa bộ phận để định danh trong mô hình ER cổ điển |
| **Chủ sở hữu** | Thực thể cung cấp thành phần định danh cho thực thể yếu |
| **Liên kết định danh** | Liên kết làm cơ sở để nhận diện từng thể hiện yếu |
| **Tham gia toàn phần của thực thể yếu** | Mọi bản ghi yếu phải gắn với chủ sở hữu thích hợp |
| **Khóa bộ phận** | Chỉ phân biệt được các bản ghi yếu trong phạm vi cùng chủ |
| **PK của bảng yếu truyền thống** | Khóa chủ sở hữu **cộng** khóa bộ phận |
| **FK của bảng yếu** | Tham chiếu đầy đủ khóa chủ, các thành phần bắt buộc |
| **Chủ có khóa ghép** | Truyền **tất cả** thành phần khóa sang bảng yếu |
| **Nhiều tầng thực thể yếu** | Mỗi tầng kế thừa khóa của chủ trực tiếp và bổ sung khóa bộ phận |
| **Surrogate PK cho bảng yếu** | Vẫn giữ FK NOT NULL và UNIQUE theo chủ + khóa bộ phận nếu nghiệp vụ yêu cầu |
| **Có FK không đồng nghĩa là yếu** | Xét cơ chế định danh, không chỉ liên kết hoặc phụ thuộc vòng đời |
| **ON DELETE CASCADE** | Là chính sách vòng đời, không phải điều kiện bắt buộc của thực thể yếu |

Khi chuyển ER sang bảng, hãy bắt đầu bằng việc hỏi **một thể hiện được định danh bằng thông tin nào và thông tin đó duy nhất trong phạm vi nào**. Với thực thể mạnh, chọn khóa chính độc lập từ các khóa ứng viên phù hợp. Với thực thể yếu, dùng **khóa chủ sở hữu cộng khóa bộ phận** để định danh, đồng thời thiết lập khóa ngoại và các điều kiện không NULL. Từ nền tảng đó, việc phân tích chuẩn hóa, ràng buộc nghiệp vụ, chỉ mục và lược đồ vật lý sẽ có cơ sở rõ ràng để kiểm chứng và tiến hóa.
