# Khóa ứng viên, khóa chính, khóa ứng viên không được chọn và khóa ngoại

## Mục tiêu học tập

Khi chuyển yêu cầu nghiệp vụ sang mô hình logic quan hệ, câu hỏi “một bản ghi được nhận diện bằng gì?” quan trọng không kém câu hỏi “bản ghi có những thuộc tính nào?”. **Khóa** giúp định danh bộ, ngăn dữ liệu trùng trái quy tắc và liên kết các quan hệ. Khóa chọn sai có thể làm mất dữ liệu hợp lệ, cho phép bản ghi mâu thuẫn hoặc tạo tham chiếu sai ngay cả khi lệnh SQL chạy thành công.

Bài thuộc chương **Mô hình quan hệ** của module **DATABASE_DATA_MODELING**. Trong phạm vi module, người học rèn kỹ năng chuyển yêu cầu nghiệp vụ thành mô hình dữ liệu rõ ràng, từ thực thể, quan hệ, ràng buộc đến chuẩn hóa, khóa, chỉ mục và lược đồ vật lý; sau đó có cơ sở so sánh cách mô hình hóa quan hệ, document, đồ thị và dữ liệu phân tích.

Sau bài này, bạn có thể:

1. Phân biệt **siêu khóa**, **khóa ứng viên**, **khóa chính**, **khóa ứng viên không được chọn** và **khóa ngoại**.
2. Xác định khóa ứng viên từ **quy tắc cho mọi trạng thái dữ liệu hợp lệ**, không dựa vào vài dòng dữ liệu mẫu.
3. Chứng minh một khóa ghép là tối thiểu và biết khi nào khóa cần thay đổi theo nghiệp vụ.
4. Biểu diễn liên kết 1–N, N–N, khóa ngoại ghép và khóa ngoại tham chiếu cả khóa chính lẫn khóa ứng viên không được chọn.
5. Ánh xạ thiết kế logic thành ràng buộc **PRIMARY KEY**, **UNIQUE**, **NOT NULL**, **FOREIGN KEY** trong PostgreSQL.
6. Kiểm chứng lựa chọn khóa, chính sách xóa/cập nhật và tác động tới chỉ mục khi triển khai vật lý.

## 1. Ví dụ xuyên suốt: định danh khách hàng và đơn hàng

Giả sử hệ thống bán hàng có các yêu cầu:

- Mỗi khách hàng có một **mã khách hàng** duy nhất do hệ thống cấp.
- Mỗi khách hàng phải có một **email** và không hai khách hàng dùng cùng email. Đây là **giả định riêng của bài**, không phải quy tắc phổ quát.
- Hai khách hàng có thể cùng họ tên.
- Mỗi đơn hàng có một **số đơn** duy nhất và thuộc về đúng một khách hàng.
- Một đơn có nhiều dòng hàng; số dòng bắt đầu từ 1 và duy nhất **trong từng đơn**.
- Mỗi dòng chọn một sản phẩm, có số lượng dương và đơn giá tại thời điểm mua.

Một lược đồ logic sơ bộ:

~~~~text
KHACH_HANG(id, ma_khach, email, ho_ten)
SAN_PHAM(id, sku, ten_san_pham, gia_niem_yet)
DON_HANG(id, so_don, ma_khach, ngay_dat)
DONG_DON_HANG(don_hang_id, so_dong, san_pham_sku, so_luong, don_gia)
~~~~

Nếu **id**, **ma_khach** và **email** đều bắt buộc và duy nhất, cả ba đều có thể nhận diện một khách hàng. Nhưng chỉ **một** được chọn làm khóa chính; những khóa ứng viên còn lại vẫn cần bảo đảm duy nhất. Ngược lại, **ho_ten** không thể làm định danh vì có thể trùng.

## 2. Siêu khóa và khóa ứng viên trong mô hình quan hệ

Xét lược đồ \(R(A_1,A_2,\ldots,A_n)\) với trạng thái quan hệ là tập các bộ thỏa mọi ràng buộc.

### 2.1. Siêu khóa (superkey)

Một tập thuộc tính **K** là siêu khóa nếu hai bộ có cùng giá trị trên K thì phải là cùng một bộ trong **mọi trạng thái hợp lệ**:

\[
\forall t_1,t_2\in r(R),\quad t_1[K]=t_2[K]\Rightarrow t_1=t_2
\]

Theo giả định của KHACH_HANG:

- **{id}**, **{ma_khach}**, **{email}** đều là siêu khóa.
- **{id, ho_ten}** cũng là siêu khóa vì thêm họ tên vào một định danh duy nhất không làm mất tính duy nhất.

Tập toàn bộ các thuộc tính luôn là siêu khóa của một quan hệ toán học thuần túy vì quan hệ là tập các bộ, không có hai bộ hoàn toàn giống nhau. Nhưng nhiều siêu khóa chứa thuộc tính không cần thiết cho định danh.

### 2.2. Khóa ứng viên (candidate key)

**Khóa ứng viên** là siêu khóa **tối thiểu theo phép bao hàm tập hợp**: nếu bỏ bất kỳ thành phần nào, tập còn lại không đủ định danh.

\[
K\text{ là siêu khóa}\quad\land\quad
\forall K'\subsetneq K,\ K'\text{ không là siêu khóa}
\]

Trong ví dụ:

- **{id}**, **{ma_khach}**, **{email}** là khóa ứng viên.
- **{id, ho_ten}** chỉ là siêu khóa, **không** là khóa ứng viên vì bỏ **ho_ten** vẫn định danh được bằng **id**.

**Tối thiểu không đồng nghĩa với ít cột nhất trong tất cả khóa ứng viên.** Khóa ghép ba thành phần vẫn có thể tối thiểu nếu thiếu bất kỳ thành phần nào đều mất tính duy nhất, dù quan hệ cũng có khóa ứng viên khác chỉ gồm một cột.

Không thể chứng minh khóa chỉ bằng vài bản ghi mẫu. Nếu hiện tại mọi khách hàng có tên khác nhau, **ho_ten** vẫn không phải khóa khi quy tắc cho phép người trùng tên.

### 2.3. Phụ thuộc hàm giúp tìm khóa

Phụ thuộc hàm \(X\rightarrow Y\) diễn tả X xác định giá trị Y trong mọi trạng thái hợp lệ. Nếu **ma_khach** là khóa ứng viên của KHACH_HANG thì:

\[
ma\_khach\rightarrow id,email,ho\_ten
\]

Có thể tìm **bao đóng thuộc tính** \(X^+\): tập thuộc tính suy ra được từ X theo các phụ thuộc hàm. Nếu bao đóng chứa mọi thuộc tính của R thì X là siêu khóa theo tập phụ thuộc hàm đang xét; sau đó thử loại từng thuộc tính của X để xác nhận tính tối thiểu.

Ví dụ quan hệ DANG_KY(ma_sv, ma_mon, hoc_ky, diem) với quy tắc **mỗi sinh viên chỉ có một bản ghi đăng ký cho mỗi môn trong mỗi học kỳ**:

\[
(ma\_sv,ma\_mon,hoc\_ky)\rightarrow diem
\]

Nếu không có phụ thuộc hàm bổ sung, bộ ba **{ma_sv, ma_mon, hoc_ky}** là khóa ứng viên. Bỏ **hoc_ky** làm hai học kỳ va chạm; bỏ **ma_mon** làm các môn va chạm; bỏ **ma_sv** làm hai sinh viên va chạm. Nếu nghiệp vụ sau này cho phép cùng sinh viên đăng ký nhiều lớp của một môn trong một học kỳ, phải bổ sung định danh lớp hoặc lần đăng ký.

## 3. Khóa chính và khóa ứng viên không được chọn

### 3.1. Khóa chính (primary key, PK)

**Khóa chính** là **một khóa ứng viên** được chọn làm định danh chính thức của các bộ. Ràng buộc **PRIMARY KEY** trong SQL bảo đảm khóa duy nhất và **không NULL**. Một bảng có tối đa **một ràng buộc PRIMARY KEY**, nhưng ràng buộc đó có thể bao gồm nhiều cột.

Giả sử chọn **KHACH_HANG.id** làm PK vì id do hệ thống tạo, ngắn và ít thay đổi. Điều này **không** cho phép hai khách hàng có cùng mã khách hoặc email nếu nghiệp vụ đã quy định những thuộc tính này duy nhất.

### 3.2. Khóa ứng viên không được chọn (alternate key, AK)

**Alternate key** là **mỗi khóa ứng viên còn lại sau khi đã chọn một khóa chính**. Các alternate key vẫn phải định danh được bộ. Từ “alternate” mô tả việc lựa chọn PK, **không** biểu thị khóa yếu hơn về khả năng định danh.

| Tập thuộc tính | Phân loại | Lý do |
| --- | --- | --- |
| {id} | Khóa ứng viên được chọn làm **PK** | Bắt buộc, duy nhất |
| {ma_khach} | **Alternate key** | Mã nghiệp vụ bắt buộc, duy nhất |
| {email} | **Alternate key** | Email bắt buộc, duy nhất theo giả định |
| {ho_ten} | Không phải khóa | Cho phép trùng họ tên |
| {id, ho_ten} | Siêu khóa, không phải khóa ứng viên | Có thành phần thừa |

SQL không có cú pháp chuẩn **ALTERNATE KEY** riêng. Thường thực thi alternate key bằng **UNIQUE** kết hợp **NOT NULL**, hoặc ràng buộc tương đương bảo đảm tính duy nhất và bắt buộc.

~~~~sql
CREATE TABLE khach_hang (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    ma_khach VARCHAR(20) NOT NULL UNIQUE,
    email VARCHAR(254) NOT NULL UNIQUE,
    ho_ten VARCHAR(120) NOT NULL
);
~~~~

**Cẩn thận với NULL:** Trong PostgreSQL, UNIQUE thông thường có thể cho phép nhiều dòng có giá trị NULL. Vì vậy **email UNIQUE nhưng có thể NULL** chưa đủ làm khóa ứng viên định danh luôn có giá trị. Nếu email chỉ là thông tin tùy chọn, vẫn có thể cần quy tắc “không trùng khi được cung cấp”, nhưng phải phân biệt quy tắc này với khóa ứng viên bắt buộc.

## 4. Khóa ngoại: ràng buộc tham chiếu

**Khóa ngoại (foreign key, FK)** là một tập thuộc tính của quan hệ **tham chiếu** (bảng con) trỏ tới khóa được phép tham chiếu ở quan hệ **được tham chiếu** (bảng cha), hoặc thỏa quy tắc NULL dành cho khóa ngoại.

Trong ví dụ:

~~~~text
DON_HANG.ma_khach           → KHACH_HANG.ma_khach
DONG_DON_HANG.don_hang_id   → DON_HANG.id
DONG_DON_HANG.san_pham_sku  → SAN_PHAM.sku
~~~~

Ba nguyên tắc:

1. **FK không nhất thiết trỏ vào PK.** FK có thể trỏ tới một khóa ứng viên không được chọn được thực thi bằng ràng buộc duy nhất phù hợp. DON_HANG.ma_khach trỏ tới KHACH_HANG.ma_khach, dù PK của khách hàng là id.
2. **FK ở bảng con không nhất thiết duy nhất.** Nhiều đơn có thể cùng trỏ tới một khách hàng. Nếu đặt UNIQUE lên DON_HANG.ma_khach, vô tình chỉ cho một khách có tối đa một đơn.
3. **FK không tự bắt buộc có giá trị.** Nếu cột con cho phép NULL, FK có thể chấp nhận giá trị thiếu. Quy tắc “đơn phải thuộc một khách hàng” cần **ma_khach NOT NULL** cùng **FOREIGN KEY**.

Khi ghi đơn có ma_khach là **KH999** nhưng không có khách KH999, FK phải từ chối thao tác. Một câu JOIN giữa hai bảng chỉ ghép dữ liệu khi đọc; nó **không bảo vệ tính toàn vẹn tham chiếu khi ghi**.

Trong SQL, đích tham chiếu thường phải có PRIMARY KEY hoặc ràng buộc UNIQUE phù hợp. PostgreSQL còn hỗ trợ một số trường hợp dựa trên chỉ mục duy nhất không phải chỉ mục bộ phận. Không thể dùng một cột có nhiều giá trị trùng làm đích tham chiếu và trông đợi FK xác định được đúng bản ghi cha.

Chọn tham chiếu PK hay alternate key là quyết định thiết kế: mã nghiệp vụ ổn định có thể là đích tốt; nếu mã thường thay đổi, tham chiếu PK ổn định thường giảm chi phí cập nhật.

## 5. Khóa ghép và tính tối thiểu

Các dòng đơn ví dụ:

| don_hang_id | so_dong | san_pham_sku | so_luong |
| ---: | ---: | --- | ---: |
| 101 | 1 | SP001 | 2 |
| 101 | 2 | SP002 | 1 |
| 102 | 1 | SP002 | 3 |

**so_dong = 1** không duy nhất toàn bảng; **don_hang_id = 101** cũng lặp lại. Nhưng cặp **(don_hang_id, so_dong)** là khóa ứng viên theo quy tắc “mỗi số dòng chỉ xuất hiện một lần trong cùng đơn”.

~~~~text
DONG_DON_HANG(don_hang_id, so_dong, san_pham_sku, so_luong, don_gia)
PK = (don_hang_id, so_dong)
FK don_hang_id  → DON_HANG.id
FK san_pham_sku → SAN_PHAM.sku
~~~~

Đây là **một khóa chính ghép**, không phải hai khóa chính độc lập:

~~~~sql
CONSTRAINT pk_dong_don_hang
    PRIMARY KEY (don_hang_id, so_dong)
~~~~

Không nên dùng **(don_hang_id, san_pham_sku)** làm khóa nếu cho phép cùng một sản phẩm xuất hiện ở nhiều dòng vì phân đợt giao hoặc mức chiết khấu khác nhau. Mỗi bộ phải được định danh phù hợp với **sự kiện nghiệp vụ** mà nó biểu diễn.

## 6. Khóa ngoại ghép và phạm vi tenant

Trong ứng dụng nhiều tổ chức (*tenant*), mã phòng **KT** có thể xuất hiện ở nhiều tổ chức:

~~~~text
PHONG_BAN(tenant_id, ma_phong, ten_phong)
PK = (tenant_id, ma_phong)

NHAN_VIEN(tenant_id, ma_nv, ma_phong, ho_ten)
PK = (tenant_id, ma_nv)
FK (tenant_id, ma_phong)
   → PHONG_BAN(tenant_id, ma_phong)
~~~~

Nếu chỉ liên kết bằng ma_phong, nhân viên của tenant A có thể được liên kết nhầm sang phòng cùng mã của tenant B. FK ghép giữ **cả tenant_id và ma_phong**, bảo đảm tham chiếu đúng tổ chức.

~~~~sql
CREATE TABLE phong_ban (
    tenant_id BIGINT NOT NULL,
    ma_phong VARCHAR(20) NOT NULL,
    ten_phong VARCHAR(100) NOT NULL,
    PRIMARY KEY (tenant_id, ma_phong)
);

CREATE TABLE nhan_vien (
    tenant_id BIGINT NOT NULL,
    ma_nv VARCHAR(20) NOT NULL,
    ma_phong VARCHAR(20) NOT NULL,
    ho_ten VARCHAR(100) NOT NULL,
    PRIMARY KEY (tenant_id, ma_nv),
    FOREIGN KEY (tenant_id, ma_phong)
        REFERENCES phong_ban (tenant_id, ma_phong)
);
~~~~

Trong FK ghép, cần khai báo đúng cặp thuộc tính tương ứng. Hai thuộc tính cùng kiểu không đương nhiên mang cùng ý nghĩa.

Theo quy tắc **MATCH SIMPLE** thường là mặc định, khi một thành phần FK ghép là NULL, kiểm tra tham chiếu có thể được bỏ qua. **MATCH FULL** (khi DBMS hỗ trợ) chỉ cho phép tất cả thành phần cùng NULL hoặc tất cả không NULL và khớp khóa cha. Trong ví dụ nhân viên, cả tenant_id và ma_phong đều **NOT NULL** nên không phát sinh trường hợp FK thiếu thành phần.

## 7. Sơ đồ ER cho các khóa

Sơ đồ sử dụng **PK** (khóa chính), **UK** (ràng buộc duy nhất của alternate key), **FK** (khóa ngoại). Những thuộc tính UK trong ví dụ đều được giả định bắt buộc.

~~~~mermaid
erDiagram
    KHACH_HANG ||--o{ DON_HANG : dat
    DON_HANG ||--o{ DONG_DON_HANG : co
    SAN_PHAM ||--o{ DONG_DON_HANG : duoc_chon

    KHACH_HANG {
        bigint id PK
        string ma_khach UK
        string email UK
        string ho_ten
    }
    DON_HANG {
        bigint id PK
        string so_don UK
        string ma_khach FK
        datetime ngay_dat
    }
    SAN_PHAM {
        bigint id PK
        string sku UK
        string ten_san_pham
        decimal gia_niem_yet
    }
    DONG_DON_HANG {
        bigint don_hang_id PK,FK
        integer so_dong PK
        string san_pham_sku FK
        integer so_luong
        decimal don_gia
    }
~~~~

Một khách có thể có nhiều đơn, mỗi đơn có nhiều dòng, mỗi sản phẩm có thể xuất hiện trong nhiều dòng. Sơ đồ cho phép đơn **tạm thời không có dòng**; nếu quy tắc yêu cầu “chỉ xác nhận đơn khi có ít nhất một dòng” thì cần kiểm tra thêm ở bước chuyển trạng thái. FK không tự bảo đảm sự tồn tại của bản ghi con.

## 8. Ánh xạ mô hình logic sang PostgreSQL

Các lệnh sau minh họa một cơ sở dữ liệu thử nghiệm độc lập. Ràng buộc được đặt tên để dễ xác định quy tắc bị vi phạm. Các bảng được tạo theo đúng thứ tự cha trước, con sau.

~~~~sql
CREATE TABLE khach_hang (
    id BIGINT GENERATED ALWAYS AS IDENTITY,
    ma_khach VARCHAR(20) NOT NULL,
    email VARCHAR(254) NOT NULL,
    ho_ten VARCHAR(120) NOT NULL,
    CONSTRAINT pk_khach_hang PRIMARY KEY (id),
    CONSTRAINT ak_khach_hang_ma UNIQUE (ma_khach),
    CONSTRAINT ak_khach_hang_email UNIQUE (email),
    CONSTRAINT ck_khach_hang_ten CHECK (btrim(ho_ten) <> '')
);

CREATE TABLE san_pham (
    id BIGINT GENERATED ALWAYS AS IDENTITY,
    sku VARCHAR(40) NOT NULL,
    ten_san_pham VARCHAR(200) NOT NULL,
    gia_niem_yet NUMERIC(12, 2) NOT NULL,
    CONSTRAINT pk_san_pham PRIMARY KEY (id),
    CONSTRAINT ak_san_pham_sku UNIQUE (sku),
    CONSTRAINT ck_san_pham_gia CHECK (gia_niem_yet >= 0)
);

CREATE TABLE don_hang (
    id BIGINT GENERATED ALWAYS AS IDENTITY,
    so_don VARCHAR(30) NOT NULL,
    ma_khach VARCHAR(20) NOT NULL,
    ngay_dat TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT pk_don_hang PRIMARY KEY (id),
    CONSTRAINT ak_don_hang_so UNIQUE (so_don),
    CONSTRAINT fk_don_hang_khach
        FOREIGN KEY (ma_khach)
        REFERENCES khach_hang (ma_khach)
        ON UPDATE CASCADE
        ON DELETE RESTRICT
);

CREATE TABLE dong_don_hang (
    don_hang_id BIGINT NOT NULL,
    so_dong INTEGER NOT NULL,
    san_pham_sku VARCHAR(40) NOT NULL,
    so_luong INTEGER NOT NULL,
    don_gia NUMERIC(12, 2) NOT NULL,
    CONSTRAINT pk_dong_don_hang PRIMARY KEY (don_hang_id, so_dong),
    CONSTRAINT fk_dong_don_hang_don
        FOREIGN KEY (don_hang_id)
        REFERENCES don_hang (id)
        ON DELETE CASCADE,
    CONSTRAINT fk_dong_don_hang_san_pham
        FOREIGN KEY (san_pham_sku)
        REFERENCES san_pham (sku)
        ON UPDATE CASCADE
        ON DELETE RESTRICT,
    CONSTRAINT ck_dong_so CHECK (so_dong > 0),
    CONSTRAINT ck_dong_so_luong CHECK (so_luong > 0),
    CONSTRAINT ck_dong_don_gia CHECK (don_gia >= 0)
);
~~~~

### 8.1. Đọc các ràng buộc trong DDL

| Ràng buộc | Ý nghĩa |
| --- | --- |
| PRIMARY KEY trên id | Mỗi khách, sản phẩm, đơn có định danh hệ thống duy nhất và không NULL |
| UNIQUE + NOT NULL trên ma_khach | Mã khách là alternate key |
| UNIQUE + NOT NULL trên email | Email là alternate key theo giả định nghiệp vụ |
| UNIQUE + NOT NULL trên so_don | Số đơn là alternate key dù PK là id |
| FK DON_HANG.ma_khach | Mỗi đơn tham chiếu một mã khách có tồn tại |
| PK (don_hang_id, so_dong) | Không trùng số dòng trong cùng đơn |
| FK DONG_DON_HANG.san_pham_sku | Dòng hàng trỏ tới SKU đang tồn tại |
| CHECK so_luong > 0 | Không cho số lượng bằng không hoặc âm |

**Giới hạn cần nhận thức:** DDL này không chứng minh email có thể nhận thư, không kiểm tra SKU còn đang bán, không bảo đảm mọi đơn đã xác nhận phải có ít nhất một dòng và không tự thực thi quy trình thanh toán. Ràng buộc khóa là một phần quan trọng của mô hình nhưng không thay thế toàn bộ quy tắc nghiệp vụ.

### 8.2. Dữ liệu mẫu

~~~~sql
INSERT INTO khach_hang (ma_khach, email, ho_ten) VALUES
    ('KH001', 'an@example.com', 'Nguyễn An'),
    ('KH002', 'binh@example.com', 'Trần Bình');

INSERT INTO san_pham (sku, ten_san_pham, gia_niem_yet) VALUES
    ('SP001', 'Sổ tay', 35000),
    ('SP002', 'Bút', 10000);

INSERT INTO don_hang (so_don, ma_khach) VALUES
    ('DH001', 'KH001'),
    ('DH002', 'KH001');

-- Tìm id đơn bằng alternate key so_don.
-- Không giả định số identity được sinh ra là bao nhiêu.
INSERT INTO dong_don_hang
    (don_hang_id, so_dong, san_pham_sku, so_luong, don_gia)
SELECT id, 1, 'SP001', 2, 35000
FROM don_hang
WHERE so_don = 'DH001';

INSERT INTO dong_don_hang
    (don_hang_id, so_dong, san_pham_sku, so_luong, don_gia)
SELECT id, 2, 'SP002', 3, 10000
FROM don_hang
WHERE so_don = 'DH001';

SELECT
    dh.so_don,
    kh.ma_khach,
    kh.ho_ten,
    dd.so_dong,
    dd.san_pham_sku,
    dd.so_luong,
    dd.don_gia
FROM don_hang AS dh
JOIN khach_hang AS kh
    ON kh.ma_khach = dh.ma_khach
JOIN dong_don_hang AS dd
    ON dd.don_hang_id = dh.id
ORDER BY dh.so_don, dd.so_dong;
~~~~

Kết quả JOIN:

| so_don | ma_khach | ho_ten | so_dong | san_pham_sku | so_luong | don_gia |
| --- | --- | --- | ---: | --- | ---: | ---: |
| DH001 | KH001 | Nguyễn An | 1 | SP001 | 2 | 35000 |
| DH001 | KH001 | Nguyễn An | 2 | SP002 | 3 | 10000 |

Đơn DH002 chưa có dòng chi tiết nên không xuất hiện trong **INNER JOIN**. Nếu cần xem cả đơn chưa có dòng, dùng **LEFT JOIN**. Sự khác nhau này đến từ phép nối, không phải lỗi khóa.

### 8.3. Thử các trường hợp bị từ chối

~~~~sql
-- Cố ý vi phạm alternate key: trùng mã khách.
INSERT INTO khach_hang (ma_khach, email, ho_ten)
VALUES ('KH001', 'another@example.com', 'Người khác');

-- Cố ý vi phạm alternate key: trùng email.
INSERT INTO khach_hang (ma_khach, email, ho_ten)
VALUES ('KH003', 'an@example.com', 'Người khác');

-- Cố ý vi phạm FK: không có khách mã KH999.
INSERT INTO don_hang (so_don, ma_khach)
VALUES ('DH999', 'KH999');

-- Cố ý vi phạm alternate key: trùng số đơn.
INSERT INTO don_hang (so_don, ma_khach)
VALUES ('DH001', 'KH002');
~~~~

**Chạy riêng từng lệnh thử lỗi**, thay vì dùng chúng làm dữ liệu khởi tạo. Các lỗi cho biết cơ sở dữ liệu bảo vệ ràng buộc ngay cả khi ứng dụng bỏ qua bước kiểm tra trước.

## 9. Chính sách xóa, cập nhật và khóa ngoại

Một FK đúng phải có quy tắc rõ ràng khi hàng cha bị xóa hoặc khóa được tham chiếu thay đổi.

| Chính sách | Hành vi | Ví dụ cân nhắc |
| --- | --- | --- |
| ON DELETE RESTRICT | Chặn xóa cha còn bản ghi con tham chiếu | Khách hàng đã có đơn, sản phẩm đã bán |
| ON DELETE NO ACTION | Không cho trạng thái vi phạm FK; thời điểm kiểm tra có thể khác RESTRICT khi DBMS hỗ trợ trì hoãn | Giao dịch cần đổi nhiều bản ghi |
| ON DELETE CASCADE | Xóa các hàng con khi xóa hàng cha | Dòng đơn phụ thuộc hoàn toàn vào đơn nếu cho phép xóa |
| ON DELETE SET NULL | Đặt FK con thành NULL | Liên kết tùy chọn, cột FK cho phép NULL |
| ON UPDATE CASCADE | Tự sửa giá trị FK con khi khóa cha đổi | Mã nghiệp vụ được phép cập nhật |

Trong ví dụ, **xóa khách hàng đang có đơn** bị chặn để bảo vệ lịch sử; nếu được phép xóa một đơn thì các dòng của nó bị xóa theo. Với hệ thống kế toán, đơn đã chốt thường không nên bị xóa vật lý; quy trình hủy hoặc lưu trữ phải được quyết định riêng.

Khi **ma_khach** hoặc **sku** thay đổi, **ON UPDATE CASCADE** có thể duy trì liên kết. Nếu mã được quy định bất biến thì cần kiểm soát thao tác sửa thay vì dựa vào CASCADE để thay mã thường xuyên.

Không nên dùng **ON DELETE SET NULL** với một cột FK bắt buộc có NOT NULL; hai quy tắc sẽ xung đột khi thao tác xóa xảy ra.

**FK tự tham chiếu** cũng hợp lệ: ví dụ NHAN_VIEN.ma_quan_ly tham chiếu NHAN_VIEN.ma_nv. Mô hình phải quyết định người đứng đầu có thể không có quản lý hay không, và nếu yêu cầu cấu trúc cây thì phải có cách ngăn chu trình.

## 10. Khóa và chỉ mục: ràng buộc logic so với cấu trúc vật lý

**Khóa** diễn đạt quy tắc duy nhất và tham chiếu. **Chỉ mục** là cấu trúc hỗ trợ tìm kiếm và thực thi ràng buộc. Trong PostgreSQL, ràng buộc **PRIMARY KEY** và **UNIQUE** sẽ tạo chỉ mục duy nhất tương ứng, nhưng khai báo **FOREIGN KEY ở bảng con không tự tạo chỉ mục trên cột FK**.

Nếu thường tìm đơn theo khách hoặc tìm dòng bán của một sản phẩm, có thể cân nhắc:

~~~~sql
CREATE INDEX ix_don_hang_ma_khach
    ON don_hang (ma_khach);

CREATE INDEX ix_dong_don_hang_san_pham_sku
    ON dong_don_hang (san_pham_sku);
~~~~

Không thêm mọi chỉ mục một cách máy móc. Cần đánh giá kiểu truy vấn, kích thước dữ liệu, thống kê, kế hoạch thực thi và chi phí ghi. Ví dụ, PK ghép **(don_hang_id, so_dong)** đã có chỉ mục bắt đầu bằng **don_hang_id**, nên nhiều truy vấn theo đơn có thể tận dụng chỉ mục sẵn có.

## 11. Khóa tự nhiên, khóa hệ thống cấp và khóa nghiệp vụ

Đây là các khái niệm dựa vào **nguồn gốc và ý nghĩa giá trị định danh**, khác với vai trò **PK/alternate key**.

| Khái niệm | Đặc điểm | Ví dụ |
| --- | --- | --- |
| Khóa tự nhiên (natural key) | Có ý nghĩa trong nghiệp vụ | SKU được quản trị ổn định, mã phân loại chính thức |
| Khóa thay thế do hệ thống cấp (surrogate key) | Mã sinh nhằm định danh, không cần có nghĩa nghiệp vụ | id BIGINT identity, UUID |
| Khóa nghiệp vụ (business key) | Mã định danh theo quy tắc vận hành | ma_khach, so_don |
| Khóa chính (primary key) | Một khóa ứng viên được chọn làm PK | KHACH_HANG.id |
| Alternate key | Khóa ứng viên không được chọn làm PK | KHACH_HANG.ma_khach |

**Surrogate key và alternate key không đồng nghĩa**, dù đôi khi cùng bị dịch ngắn thành “khóa thay thế”:

- **Surrogate** chỉ **nguồn gốc/ý nghĩa** định danh.
- **Alternate** chỉ **vai trò so với PK đã chọn**.

Khóa hệ thống cấp thường hữu ích khi mã nghiệp vụ dài, có thể đổi, gồm nhiều thành phần hoặc trùng giữa các nguồn dữ liệu. Nhưng surrogate PK **không thay thế UNIQUE cho mã nghiệp vụ**. Nếu hai hàng mang cùng ma_khach là lỗi, việc hai hàng có id khác nhau không giải quyết được lỗi đó.

Ngược lại, khóa tự nhiên có thể phù hợp nếu ngắn, bất biến và duy nhất lâu dài. Email, số điện thoại hoặc tên người **không mặc nhiên** đáp ứng các điều kiện này; có tổ chức cho nhiều người chung email hoặc một người nhiều email.

**Phạm vi duy nhất phải rõ:** số đơn có thể chỉ duy nhất trong năm, hoặc mã đối tác chỉ duy nhất trong một tenant. Khi đó **(nam, so_thu_tu)** hoặc **(tenant_id, ma_doi_tac)** mới có thể là khóa ứng viên, còn số thứ tự hoặc mã nội bộ đứng riêng không đủ.

## 12. Các lỗi thiết kế khóa thường gặp

| Sai lầm | Hệ quả | Cách xử lý |
| --- | --- | --- |
| Chọn họ tên làm khóa vì dữ liệu mẫu không trùng | Va chạm khi có người trùng tên | Chọn định danh theo quy tắc nghiệp vụ lâu dài |
| Có PK id rồi bỏ UNIQUE của mã khách | Cho phép trùng mã nghiệp vụ | Duy trì ràng buộc alternate key |
| Chỉ dùng UNIQUE mà không xét NULL | Có thể nhận nhiều dòng thiếu mã | Dùng NOT NULL khi là định danh bắt buộc |
| Khóa dòng đơn bằng (ma_dh, ma_sp) dù sản phẩm có thể lặp | Chặn sự kiện hợp lệ | Dùng (don_hang_id, so_dong) hoặc định danh dòng |
| FK nhưng thiếu NOT NULL cho liên kết bắt buộc | Cho phép con không có cha | Kết hợp NOT NULL và FOREIGN KEY |
| FK chỉ theo ma_phong trong dữ liệu nhiều tenant | Có thể liên kết nhầm tổ chức | Dùng khóa ngoại ghép có tenant_id |
| Chọn CASCADE cho lịch sử giao dịch | Dễ xóa mất dữ liệu cần lưu | Xác định chính sách lưu trữ, dùng RESTRICT khi cần |
| Nghĩ FK tự tạo chỉ mục cột con | Truy vấn liên quan có thể chậm | Đánh giá chỉ mục theo truy vấn thực tế |
| Kiểm tra trùng ở ứng dụng rồi mới INSERT | Hai tiến trình đồng thời có thể cùng vượt kiểm tra | Dùng UNIQUE trong DB và xử lý lỗi |

### Lỗi tranh chấp “kiểm tra rồi chèn”

Hai tiến trình có thể đồng thời chạy:

~~~~sql
SELECT 1
FROM khach_hang
WHERE ma_khach = 'KH010';
-- Cả hai cùng thấy chưa có dòng KH010.
~~~~

Sau đó cả hai cùng INSERT KH010. Việc kiểm tra trước ở ứng dụng **không bảo đảm tính duy nhất** trong truy cập đồng thời. Ràng buộc **UNIQUE(ma_khach)** ở cơ sở dữ liệu là điểm bảo vệ cuối; ít nhất một thao tác sẽ không thể cùng tạo thành hai mã trùng trong trạng thái đã xác nhận hợp lệ. Ứng dụng cần xử lý lỗi duy nhất để trả thông báo phù hợp.

## 13. Quy trình tìm và chọn khóa từ yêu cầu nghiệp vụ

1. **Xác định ý nghĩa một bộ.** Ví dụ một bộ DONG_DON_HANG là một dòng cụ thể của một đơn.
2. **Liệt kê định danh có thể có** và phạm vi duy nhất: toàn hệ thống, theo tenant, theo năm hay theo đơn.
3. **Viết quy tắc duy nhất có thể kiểm chứng.** Ví dụ “hai dòng trong cùng đơn không có cùng so_dong”.
4. **Xác nhận ngoại lệ và tiến hóa.** Có nhập lại, hủy, đổi mã, chuyển tenant, đăng ký nhiều lần không?
5. **Chứng minh tính tối thiểu.** Thử bỏ lần lượt từng thành phần của mỗi siêu khóa.
6. **Chọn một khóa ứng viên làm PK** dựa trên tính ổn định, kích thước và chi phí tham chiếu.
7. **Giữ ràng buộc cho alternate key**, thường bằng UNIQUE cùng NOT NULL khi bắt buộc.
8. **Khai báo FK đúng đích và đúng phạm vi**, quyết định khả năng NULL và xử lý khi sửa/xóa.
9. **Kiểm thử trạng thái hợp lệ và bất hợp lệ**, bao gồm trùng mã, thiếu cha, trùng dòng trong cùng đơn và cùng số dòng ở hai đơn khác nhau.
10. **Sau đó tối ưu lược đồ vật lý**: chọn kiểu dữ liệu, chỉ mục và kiểm tra kế hoạch truy vấn.

## 14. Bài tập tự kiểm tra

### Bài 1 — Phân loại khóa

NHAN_VIEN(id, ma_nv, email, ho_ten) có id, ma_nv, email bắt buộc và duy nhất, họ tên có thể trùng. Chọn id làm PK.

**Câu hỏi:** Liệt kê khóa ứng viên và alternate key. Tập **{id, ma_nv}** có phải khóa ứng viên không?

**Đáp án:** Khóa ứng viên là **{id}**, **{ma_nv}**, **{email}**. Alternate key là **{ma_nv}** và **{email}**. **{id, ma_nv}** chỉ là siêu khóa vì bỏ ma_nv vẫn duy nhất; tập không tối thiểu.

### Bài 2 — Khóa ghép cho lần thi

DIEM_THI(ma_sv, ma_mon, lan_thi, diem): mỗi sinh viên có thể thi một môn nhiều lần; lan_thi là số thứ tự trong phạm vi cặp sinh viên–môn.

**Câu hỏi:** Khóa tự nhiên phù hợp là gì? Có thể dùng **(ma_sv, ma_mon)** không?

**Đáp án:** **(ma_sv, ma_mon, lan_thi)** là khóa ứng viên theo giả định. Cặp **(ma_sv, ma_mon)** không đủ vì có thể nhiều lần thi. Nếu id được chọn làm PK, vẫn nên ràng buộc UNIQUE cho bộ ba nghiệp vụ và NOT NULL cho các thành phần.

### Bài 3 — PK không bảo đảm mã nghiệp vụ duy nhất

~~~~sql
CREATE TABLE doi_tac (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    ma_doi_tac VARCHAR(30) NOT NULL,
    ten VARCHAR(100) NOT NULL
);
~~~~

**Câu hỏi:** Có ngăn hai đối tác cùng mã DT001 không? Sửa thế nào?

**Đáp án:** Không. Hai hàng có thể khác id nhưng trùng ma_doi_tac. Bổ sung:

~~~~sql
ALTER TABLE doi_tac
ADD CONSTRAINT ak_doi_tac_ma UNIQUE (ma_doi_tac);
~~~~

### Bài 4 — FK tham chiếu alternate key

KHACH_HANG(id PK, ma_khach UNIQUE NOT NULL, ho_ten) và DON_HANG(id PK, ma_khach NOT NULL).

**Câu hỏi:** Viết FK để mã khách trong đơn tham chiếu mã khách ở bảng khách hàng, dù đó không phải PK.

**Đáp án tham khảo:**

~~~~sql
ALTER TABLE don_hang
ADD CONSTRAINT fk_don_hang_khach
FOREIGN KEY (ma_khach)
REFERENCES khach_hang (ma_khach);
~~~~

Khóa được tham chiếu là alternate key được bảo đảm duy nhất.

### Bài 5 — Tránh tham chiếu sai tenant

PHONG_BAN(tenant_id, ma_phong, ten_phong) có PK **(tenant_id, ma_phong)**. NHAN_VIEN(tenant_id, ma_nv, ma_phong) phải thuộc phòng của chính tenant.

**Câu hỏi:** Vì sao FK chỉ gồm ma_phong là sai? FK đúng là gì?

**Đáp án:** Mã phòng chỉ duy nhất trong mỗi tenant. Cần **FOREIGN KEY (tenant_id, ma_phong) REFERENCES phong_ban(tenant_id, ma_phong)**, kết hợp NOT NULL cho các cột khi mọi nhân viên phải thuộc một phòng.

### Bài 6 — Xóa khách hàng có lịch sử giao dịch

Hệ thống kế toán phải giữ đơn đã chốt. Người quản trị đề xuất ON DELETE CASCADE từ đơn đến khách để xóa nhanh thông tin khi khách ngừng sử dụng.

**Câu hỏi:** Có nên chấp nhận ngay không?

**Đáp án:** Không nên khi chưa làm rõ yêu cầu lưu trữ. Xóa dây chuyền có thể mất lịch sử giao dịch; thường dùng RESTRICT, trạng thái ngừng hoạt động hoặc quy trình ẩn danh phù hợp. Chỉ dùng CASCADE nếu nghiệp vụ thật sự cho phép xóa toàn bộ hàng con.

### Bài 7 — UNIQUE và truy cập đồng thời

Hai yêu cầu cùng kiểm tra chưa có mã KH010 rồi đồng thời INSERT.

**Câu hỏi:** Kiểm tra tại ứng dụng có đủ không?

**Đáp án:** Không. Cần UNIQUE(ma_khach), cùng NOT NULL nếu mã bắt buộc, để cơ sở dữ liệu bảo vệ ràng buộc; ứng dụng bắt lỗi ghi trùng và trả phản hồi hợp lý.

### Bài 8 — Surrogate key và alternate key

SAN_PHAM(id BIGINT PK, sku VARCHAR(40) UNIQUE NOT NULL, ten_san_pham), id do hệ thống sinh.

**Câu hỏi:** Cột nào là surrogate key và cột nào là alternate key?

**Đáp án:** id là surrogate key đồng thời là PK. sku là alternate key. **Surrogate** mô tả nguồn gốc định danh, **alternate** mô tả vai trò khóa ứng viên so với PK.

## 15. Tóm tắt

| Khái niệm | Tiêu chí phân biệt | Ví dụ |
| --- | --- | --- |
| **Siêu khóa** | Tập thuộc tính định danh duy nhất, có thể dư thành phần | {id, ho_ten} |
| **Khóa ứng viên** | Siêu khóa **tối thiểu** | {id}, {ma_khach}, {email} |
| **Khóa chính** | Một khóa ứng viên được chọn làm PK | KHACH_HANG.id |
| **Khóa ứng viên không được chọn** | Khóa ứng viên còn lại, vẫn phải duy nhất | KHACH_HANG.ma_khach |
| **Khóa ngoại** | Tham chiếu đến khóa hợp lệ ở cùng hoặc khác quan hệ | DON_HANG.ma_khach → KHACH_HANG.ma_khach |
| **Khóa ghép** | Khóa gồm nhiều thành phần, mỗi thành phần đều cần thiết | (don_hang_id, so_dong) |
| **Surrogate key** | Định danh do hệ thống cấp, không cần nghĩa nghiệp vụ | id identity |
| **Natural/business key** | Định danh theo quy tắc nghiệp vụ | ma_khach, sku |

Khóa chỉ có giá trị khi xuất phát từ **ý nghĩa của mỗi bộ, quy tắc duy nhất và các trạng thái dữ liệu hợp lệ**. Hãy tìm mọi khóa ứng viên, chọn một khóa làm PK, bảo vệ các khóa ứng viên không được chọn và khai báo FK để bảo toàn liên kết. Từ đó, chuẩn hóa, lựa chọn chỉ mục và thiết kế lược đồ vật lý mới có cơ sở rõ ràng để kiểm chứng khi yêu cầu thay đổi.
