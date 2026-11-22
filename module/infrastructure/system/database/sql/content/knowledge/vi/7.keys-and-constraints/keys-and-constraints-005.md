# CHECK cho miền giá trị và quan hệ giữa các cột trong SQL

Một bảng SQL không chỉ cần cột và kiểu dữ liệu; nó còn cần **quy tắc xác định bản ghi nào được phép tồn tại**. Chẳng hạn, cột `so_luong` là số nguyên không có nghĩa mọi số nguyên đều hợp lệ: một đơn đặt hàng có thể yêu cầu số lượng **lớn hơn 0**. Tương tự, hai cột ngày bắt đầu và ngày kết thúc có thể đều là kiểu `DATE`, nhưng ngày kết thúc phải **không trước ngày bắt đầu**.

Ràng buộc **`CHECK`** giúp cơ sở dữ liệu thực thi những quy tắc này mỗi khi dữ liệu được thêm hoặc sửa. CHECK có thể kiểm tra **miền giá trị của một cột** hoặc **mối quan hệ giữa nhiều cột của cùng một dòng**. Đây là một phần quan trọng của nhóm *khóa và ràng buộc* trong thiết kế cơ sở dữ liệu quan hệ.

Bài học dùng cú pháp **PostgreSQL** cho các ví dụ thực hành và chỉ rõ khác biệt đáng chú ý ở MySQL/MariaDB, SQL Server, Oracle và SQLite. Tên bảng, dữ liệu và ngày tháng đều là ví dụ dành cho môi trường học tập.

## 1. CHECK là gì?

`CHECK` là một ràng buộc kiểm tra (*check constraint*) chứa một biểu thức điều kiện. Khi một hàng được thêm hoặc cập nhật, hệ quản trị đánh giá biểu thức đó để quyết định có chấp nhận hàng hay không.

Ví dụ:

~~~sql
CREATE TABLE san_pham_demo (
    id INTEGER PRIMARY KEY,
    ten VARCHAR(100) NOT NULL,
    gia NUMERIC(12, 2) NOT NULL,
    CONSTRAINT ck_san_pham_gia
        CHECK (gia >= 0)
);
~~~

Ở đây, `gia` là số thập phân chính xác, nhưng ràng buộc yêu cầu thêm rằng **giá không âm**.

~~~sql
-- Hợp lệ.
INSERT INTO san_pham_demo (id, ten, gia)
VALUES (1, 'Sách SQL', 120000);

-- Không hợp lệ: gia < 0.
INSERT INTO san_pham_demo (id, ten, gia)
VALUES (2, 'Bút', -5000);
~~~

Khi dòng thứ hai bị từ chối, bảng vẫn tồn tại và dòng hợp lệ trước đó vẫn có thể tồn tại, tùy ranh giới transaction đang sử dụng. PostgreSQL thường báo lỗi thuộc nhóm `check_violation` với SQLSTATE `23514`; tên `ck_san_pham_gia` trong thông báo giúp nhận ra quy tắc bị vi phạm.

### 1.1. CHECK kiểm tra những gì?

| Quy tắc nghiệp vụ | Biểu thức CHECK minh họa |
|---|---|
| Số lượng phải dương | `CHECK (so_luong > 0)` |
| Giá không âm | `CHECK (gia >= 0)` |
| Điểm trong khoảng 0–100 | `CHECK (diem BETWEEN 0 AND 100)` |
| Trạng thái thuộc một danh sách | `CHECK (trang_thai IN ('NEW', 'PAID', 'CANCELLED'))` |
| Phần trăm chiết khấu hợp lệ | `CHECK (ty_le_giam >= 0 AND ty_le_giam <= 100)` |
| Ngày kết thúc sau ngày bắt đầu | `CHECK (ngay_ket_thuc >= ngay_bat_dau)` |
| Giảm giá không vượt giá trị đơn | `CHECK (giam_gia <= so_luong * don_gia)` |
| Đơn đã thanh toán phải có thời điểm thanh toán | `CHECK (trang_thai <> 'PAID' OR ngay_thanh_toan IS NOT NULL)` |

Một số ví dụ dùng cột đơn lẻ; các ví dụ cuối so sánh nhiều cột trong **cùng một hàng**. CHECK không nhằm đếm dữ liệu ở các hàng khác hay tra cứu bảng tham chiếu.

### 1.2. CHECK khác những ràng buộc còn lại

| Ràng buộc | Nhiệm vụ chính | Ví dụ |
|---|---|---|
| `NOT NULL` | Bắt buộc cột có giá trị | `email VARCHAR(255) NOT NULL` |
| `UNIQUE` | Không cho trùng cột hoặc tổ hợp cột theo ngữ nghĩa DBMS | `UNIQUE (email)` |
| `PRIMARY KEY` | Định danh duy nhất một hàng, không NULL | `PRIMARY KEY (id)` |
| `FOREIGN KEY` | Bảo đảm giá trị tham chiếu khóa hợp lệ ở bảng khác | `FOREIGN KEY (khach_hang_id) REFERENCES khach_hang(id)` |
| `CHECK` | Kiểm tra biểu thức về miền giá trị và mối quan hệ trong hàng | `CHECK (gia >= 0)` |
| `DEFAULT` | Cung cấp giá trị khi lệnh chèn không chỉ định cột | `DEFAULT 0` |

CHECK có thể diễn đạt những quy tắc mà kiểu dữ liệu hoặc khóa không tự đảm bảo. Tuy nhiên, hãy dùng đúng ràng buộc chuyên biệt: **không thay khóa ngoại bằng CHECK**, không dùng CHECK để cố thay UNIQUE giữa nhiều hàng.

## 2. Điều quan trọng nhất: CHECK và logic ba giá trị

SQL có ba kết quả khi đánh giá một điều kiện:

- **TRUE**: biểu thức đúng.
- **FALSE**: biểu thức sai.
- **UNKNOWN**: chưa xác định được đúng hay sai, thường do có `NULL`.

Trong PostgreSQL và nhiều hệ quản trị quan hệ, quy tắc CHECK là:

| Kết quả biểu thức | Hàng có vượt qua CHECK không? |
|---|---|
| TRUE | Có |
| FALSE | **Không** — vi phạm CHECK |
| UNKNOWN / NULL | Có, theo ngữ nghĩa CHECK thông thường |

Đây là điểm rất dễ bị hiểu nhầm. CHECK **không yêu cầu biểu thức luôn TRUE**; nó chỉ từ chối hàng khi biểu thức đánh giá thành **FALSE**. Vì vậy:

~~~sql
CREATE TABLE diem_demo (
    id INTEGER PRIMARY KEY,
    diem INTEGER CHECK (diem BETWEEN 0 AND 100)
);
~~~

Các câu sau minh họa:

~~~sql
INSERT INTO diem_demo VALUES (1, 80);    -- Hợp lệ: TRUE
INSERT INTO diem_demo VALUES (2, 150);   -- Bị từ chối: FALSE
INSERT INTO diem_demo VALUES (3, NULL);  -- Hợp lệ: UNKNOWN
~~~

Biểu thức `NULL BETWEEN 0 AND 100` trả UNKNOWN, nên CHECK không từ chối dòng thứ ba.

### 2.1. Muốn bắt buộc có giá trị thì thêm NOT NULL

~~~sql
CREATE TABLE diem_bat_buoc (
    id INTEGER PRIMARY KEY,
    diem INTEGER NOT NULL
        CONSTRAINT ck_diem_bat_buoc
        CHECK (diem BETWEEN 0 AND 100)
);
~~~

Hai ràng buộc độc lập:

1. `NOT NULL` từ chối dữ liệu thiếu.
2. `CHECK (diem BETWEEN 0 AND 100)` từ chối dữ liệu ngoài khoảng.

Ví dụ `diem = NULL` vi phạm NOT NULL; `diem = 150` vi phạm CHECK.

Có thể viết `CHECK (diem IS NOT NULL AND diem BETWEEN 0 AND 100)` để biểu thức sai khi NULL, nhưng dùng `NOT NULL` riêng thường rõ nghĩa hơn và được nhiều công cụ/optimizer nhận diện trực tiếp.

### 2.2. Vì sao không viết CHECK (x = NULL)?

Trong SQL thông thường, phép so sánh `x = NULL` cho UNKNOWN, kể cả x cũng là NULL. Vì thế:

~~~sql
-- Sai ý định: không thể kiểm tra x phải NULL theo cách này.
CHECK (x = NULL)
~~~

không thể hiện đúng quy tắc cần kiểm tra. Dùng:

~~~sql
CHECK (x IS NULL)
~~~

nếu nghiệp vụ thật sự yêu cầu x phải NULL, hoặc `NOT NULL` nếu nghiệp vụ yêu cầu x phải có giá trị.

### 2.3. NULL trong CHECK giữa nhiều cột

Ví dụ:

~~~sql
CHECK (ngay_ket_thuc >= ngay_bat_dau)
~~~

Nếu cả hai ngày đều không NULL, điều kiện kiểm tra thứ tự đúng như mong muốn. Nhưng nếu `ngay_ket_thuc` NULL, phép so sánh cho UNKNOWN và hàng **được phép** tồn tại.

Điều đó có thể **đúng** nếu ngày kết thúc là tùy chọn. Nếu cả hai ngày đều bắt buộc, cần đặt `NOT NULL` trên cả hai cột.

Khi thiết kế CHECK, hãy hỏi: **“Trường nào được phép NULL? Nếu một trường NULL, quy tắc có cần từ chối hàng không?”**

## 3. Cú pháp CHECK ở mức cột và mức bảng

### 3.1. CHECK đặt ngay sau cột

~~~sql
CREATE TABLE kho_demo (
    id INTEGER PRIMARY KEY,
    so_luong INTEGER NOT NULL CHECK (so_luong >= 0),
    gia_nhap NUMERIC(12,2) NOT NULL CHECK (gia_nhap >= 0)
);
~~~

Cách này ngắn gọn, phù hợp với quy tắc chỉ liên quan một cột.

### 3.2. CHECK ở mức bảng

~~~sql
CREATE TABLE kho_demo_co_ten (
    id INTEGER PRIMARY KEY,
    so_luong INTEGER NOT NULL,
    gia_nhap NUMERIC(12,2) NOT NULL,
    CONSTRAINT ck_kho_so_luong
        CHECK (so_luong >= 0),
    CONSTRAINT ck_kho_gia_nhap
        CHECK (gia_nhap >= 0)
);
~~~

Ràng buộc ở mức bảng đặt tên tường minh bằng `CONSTRAINT ten`. Tên giúp nhận diện quy tắc trong lỗi và trong lệnh `ALTER TABLE ... DROP CONSTRAINT`.

### 3.3. CHECK so sánh nhiều cột

~~~sql
CREATE TABLE chuong_trinh_giam_gia (
    id INTEGER PRIMARY KEY,
    ngay_bat_dau DATE NOT NULL,
    ngay_ket_thuc DATE NOT NULL,
    ty_le_giam NUMERIC(5,2) NOT NULL,
    CONSTRAINT ck_ngay_chuong_trinh
        CHECK (ngay_ket_thuc >= ngay_bat_dau),
    CONSTRAINT ck_ty_le_giam
        CHECK (ty_le_giam BETWEEN 0 AND 100)
);
~~~

`ck_ngay_chuong_trinh` so sánh **hai cột của cùng hàng**. Không cần một khóa ngoại chỉ để kiểm tra rằng ngày kết thúc không được trước ngày bắt đầu.

~~~sql
-- Hợp lệ.
INSERT INTO chuong_trinh_giam_gia
    (id, ngay_bat_dau, ngay_ket_thuc, ty_le_giam)
VALUES (1, DATE '2026-11-01', DATE '2026-11-30', 15);

-- Bị từ chối: ngày kết thúc trước ngày bắt đầu.
INSERT INTO chuong_trinh_giam_gia
    (id, ngay_bat_dau, ngay_ket_thuc, ty_le_giam)
VALUES (2, DATE '2026-11-30', DATE '2026-11-01', 15);
~~~

Quy tắc đọc là “**mỗi hàng** của bảng phải có ngày kết thúc không trước ngày bắt đầu”.

## 4. Dùng CHECK để giới hạn miền giá trị

Miền giá trị (*domain*) là tập giá trị nghiệp vụ cho phép của một thuộc tính. Kiểu dữ liệu chỉ giới hạn bước đầu: `INTEGER` chấp nhận cả số âm, nhưng `so_luong` có thể phải lớn hơn 0.

### 4.1. Khoảng số và dấu biên

~~~sql
CREATE TABLE danh_gia_demo (
    id INTEGER PRIMARY KEY,
    diem INTEGER NOT NULL
        CHECK (diem BETWEEN 1 AND 5),
    ty_le NUMERIC(5,2) NOT NULL
        CHECK (ty_le >= 0 AND ty_le <= 100)
);
~~~

`BETWEEN 1 AND 5` bao gồm cả **1 và 5**. Nó tương đương `diem >= 1 AND diem <= 5` trong trường hợp các toán hạng phù hợp và không có NULL.

| Giá trị `diem` | Hợp lệ? | Giải thích |
|---:|---|---|
| 1 | Có | Biên dưới được tính |
| 3 | Có | Nằm trong khoảng |
| 5 | Có | Biên trên được tính |
| 0 | Không | Dưới 1 |
| 6 | Không | Trên 5 |
| NULL | Không | Do `NOT NULL` |

Khi giới hạn phần trăm hoặc số tiền, chú ý kiểu số và độ chính xác. `NUMERIC(5,2)` kiểm soát khả năng biểu diễn số, còn `CHECK` kiểm soát quy tắc nghiệp vụ.

### 4.2. Danh sách trạng thái bằng IN

~~~sql
CREATE TABLE ve_demo (
    id INTEGER PRIMARY KEY,
    trang_thai VARCHAR(20) NOT NULL DEFAULT 'NEW',
    CONSTRAINT ck_ve_trang_thai
        CHECK (trang_thai IN ('NEW', 'PAID', 'CANCELLED'))
);
~~~

Với thiết kế này, chỉ ba trạng thái được cho phép theo quy tắc so sánh chuỗi của DBMS.

~~~sql
INSERT INTO ve_demo (id, trang_thai)
VALUES (1, 'PAID');       -- Hợp lệ.

INSERT INTO ve_demo (id, trang_thai)
VALUES (2, 'REFUNDED');   -- Bị từ chối nếu chưa mở rộng CHECK.
~~~

Danh sách `IN (...)` phù hợp với tập trạng thái tương đối nhỏ, ổn định. Nếu tập trạng thái có nhiều thuộc tính riêng, thường xuyên thay đổi, hoặc cần quản lý quan hệ đến bảng trạng thái, có thể dùng bảng tra cứu cùng `FOREIGN KEY`. Không nên cố dùng CHECK để truy vấn bảng tra cứu khác.

### 4.3. Giới hạn độ dài hoặc dạng chuỗi

~~~sql
CREATE TABLE ma_khuyen_mai_demo (
    id INTEGER PRIMARY KEY,
    ma VARCHAR(30) NOT NULL,
    CONSTRAINT ck_ma_khuyen_mai_khong_trong
        CHECK (char_length(trim(ma)) > 0)
);
~~~

Điều kiện này từ chối chuỗi rỗng hoặc chuỗi chỉ có khoảng trắng theo hành vi `trim` của PostgreSQL. `NOT NULL` tự nó không từ chối chuỗi rỗng `''`.

Khi muốn kiểm soát mẫu ký tự, PostgreSQL có toán tử biểu thức chính quy:

~~~sql
CREATE TABLE ma_van_don_demo (
    id INTEGER PRIMARY KEY,
    ma VARCHAR(20) NOT NULL,
    CONSTRAINT ck_ma_van_don
        CHECK (ma ~ '^[A-Z]{2}-[0-9]{4}$')
);
~~~

Ví dụ `AB-1234` hợp lệ theo biểu thức này, còn `A-1234` không hợp lệ. `~` là cú pháp regex của PostgreSQL, không phải một toán tử SQL có cùng cú pháp ở mọi DBMS. CHECK dạng mẫu ký tự chỉ kiểm tra định dạng theo quy ước; nó không thay thế việc xác nhận mã có thực sự được cấp bởi hệ thống bên ngoài hay không.

### 4.4. Phân biệt CHECK với kiểu ENUM hoặc bảng tham chiếu

Có ba hướng mô hình hóa trạng thái:

- **CHECK + kiểu chuỗi**: dễ đọc, phù hợp tập giá trị nhỏ và ổn định.
- **Kiểu ENUM** của DBMS hỗ trợ: miền giá trị nằm trong định nghĩa kiểu riêng; cách bổ sung giá trị và tính di động khác nhau.
- **Bảng tra cứu + FOREIGN KEY**: mỗi trạng thái có dòng riêng, có thể thêm mô tả, thứ tự hiển thị hoặc metadata.

Không nên mặc định phương án nào tốt nhất cho mọi nghiệp vụ. Hãy xét nhu cầu thay đổi trạng thái, quyền quản trị, khả năng JOIN và khả năng di chuyển DBMS.

## 5. CHECK cho quan hệ giữa các cột

Đây là nhóm quy tắc mà `CHECK` đặc biệt hữu ích. Mỗi giá trị có thể hợp lệ khi xem riêng nhưng **tổ hợp giá trị lại vô lý**.

### 5.1. Ngày bắt đầu và kết thúc

~~~sql
CREATE TABLE hop_dong_demo (
    id INTEGER PRIMARY KEY,
    ngay_bat_dau DATE NOT NULL,
    ngay_ket_thuc DATE,
    CONSTRAINT ck_hop_dong_thoi_han
        CHECK (ngay_ket_thuc IS NULL
               OR ngay_ket_thuc >= ngay_bat_dau)
);
~~~

Thiết kế trên thể hiện rõ:

- Ngày bắt đầu bắt buộc.
- Ngày kết thúc có thể chưa xác định.
- Nếu có ngày kết thúc, ngày đó phải bằng hoặc sau ngày bắt đầu.

Ví dụ:

| ngay_bat_dau | ngay_ket_thuc | Hợp lệ? |
|---|---|---|
| 2026-01-01 | 2026-12-31 | Có |
| 2026-01-01 | 2026-01-01 | Có |
| 2026-06-01 | 2026-05-31 | Không |
| 2026-01-01 | NULL | Có |

Do `ngay_bat_dau` có `NOT NULL`, không phát sinh trường hợp ngày bắt đầu thiếu. Nếu nghiệp vụ yêu cầu cả hai ngày cùng xuất hiện hoặc cùng vắng mặt, cần một biểu thức khác.

### 5.2. Hai cột cùng NULL hoặc cùng có giá trị

Giả sử đặt lịch tùy chọn: có lịch thì phải có **cả** thời điểm bắt đầu lẫn kết thúc, và thời điểm kết thúc phải sau bắt đầu.

~~~sql
CREATE TABLE lich_hen_demo (
    id INTEGER PRIMARY KEY,
    bat_dau_luc TIMESTAMP,
    ket_thuc_luc TIMESTAMP,
    CONSTRAINT ck_lich_hen_cap_thoi_diem
        CHECK (
            (bat_dau_luc IS NULL AND ket_thuc_luc IS NULL)
            OR
            (bat_dau_luc IS NOT NULL
             AND ket_thuc_luc IS NOT NULL
             AND ket_thuc_luc > bat_dau_luc)
        )
);
~~~

| bat_dau_luc | ket_thuc_luc | Hợp lệ? |
|---|---|---|
| NULL | NULL | Có — chưa lên lịch |
| 09:00 | 10:00 cùng ngày | Có |
| 09:00 | 09:00 cùng ngày | Không |
| 10:00 | 09:00 cùng ngày | Không |
| 09:00 | NULL | Không |
| NULL | 10:00 | Không |

Cách viết `IS NULL` và `IS NOT NULL` rõ ràng giúp tránh trường hợp UNKNOWN vô tình vượt CHECK. Đây là ràng buộc về **sự đầy đủ của một nhóm cột**.

### 5.3. Số tiền giảm không vượt tổng tiền gốc

~~~sql
CREATE TABLE dong_hang_demo (
    id INTEGER PRIMARY KEY,
    so_luong INTEGER NOT NULL CHECK (so_luong > 0),
    don_gia NUMERIC(12,2) NOT NULL CHECK (don_gia >= 0),
    giam_gia NUMERIC(12,2) NOT NULL DEFAULT 0,
    CONSTRAINT ck_dong_hang_giam_gia
        CHECK (giam_gia >= 0
               AND giam_gia <= so_luong * don_gia)
);
~~~

Giả sử `so_luong = 2` và `don_gia = 100000` thì tổng tiền trước giảm là `200000`. Khi đó `giam_gia = 50000` hợp lệ, còn `giam_gia = 250000` bị từ chối.

Điều kiện CHECK được kiểm tra lại khi **bất kỳ cột liên quan nào thay đổi**. Ví dụ, nếu giảm số lượng từ 2 xuống 1 trong khi giữ giảm giá 150000, dòng có thể trở nên bất hợp lệ và UPDATE bị từ chối.

Nếu tổng tiền được lưu thành một cột dẫn xuất, hãy cân nhắc cột sinh (*generated column*) hoặc tính khi truy vấn thay vì duy trì nhiều giá trị trùng thông tin dễ lệch nhau. CHECK bảo vệ quan hệ, nhưng không tự tính hoặc cập nhật dữ liệu thay bạn.

### 5.4. Điều kiện “nếu A thì B”

Ví dụ: **đơn có trạng thái PAID phải có ngày thanh toán**.

~~~sql
CREATE TABLE thanh_toan_demo (
    id INTEGER PRIMARY KEY,
    trang_thai VARCHAR(20) NOT NULL
        CHECK (trang_thai IN ('NEW', 'PAID', 'CANCELLED')),
    ngay_thanh_toan DATE,
    CONSTRAINT ck_paid_can_ngay
        CHECK (
            trang_thai <> 'PAID'
            OR ngay_thanh_toan IS NOT NULL
        )
);
~~~

Đây là cách viết logic của mệnh đề kéo theo:

\[
A \Rightarrow B \equiv \neg A \lor B
\]

Trong đó A là “`trang_thai = 'PAID'`”, B là “`ngay_thanh_toan IS NOT NULL`”.

| trang_thai | ngay_thanh_toan | Hợp lệ? |
|---|---|---|
| NEW | NULL | Có |
| NEW | 2026-11-10 | Có theo quy tắc hiện tại |
| PAID | 2026-11-10 | Có |
| PAID | NULL | **Không** |
| CANCELLED | NULL | Có |

Chú ý rằng CHECK trên **chỉ đặt điều kiện một chiều**: PAID bắt buộc có ngày, nhưng có ngày chưa bắt buộc phải PAID. Nếu nghiệp vụ yêu cầu **tương đương hai chiều**, dùng quy tắc mạnh hơn:

~~~sql
CONSTRAINT ck_paid_iff_ngay
CHECK (
    (trang_thai = 'PAID' AND ngay_thanh_toan IS NOT NULL)
    OR
    (trang_thai <> 'PAID' AND ngay_thanh_toan IS NULL)
)
~~~

Đây là **đoạn khai báo ràng buộc để đưa vào CREATE/ALTER TABLE**, không phải câu SQL chạy độc lập. Vì `trang_thai` có `NOT NULL`, các phép so sánh với `'PAID'` không cho UNKNOWN.

### 5.5. Đúng một trong hai cột phải có giá trị

Giả sử một liên hệ cần **email hoặc số điện thoại, nhưng không được đồng thời có cả hai**:

~~~sql
CREATE TABLE kenh_lien_he_demo (
    id INTEGER PRIMARY KEY,
    email VARCHAR(255),
    dien_thoai VARCHAR(30),
    CONSTRAINT ck_chon_dung_mot_kenh
        CHECK (
            (email IS NOT NULL AND dien_thoai IS NULL)
            OR
            (email IS NULL AND dien_thoai IS NOT NULL)
        )
);
~~~

| email | dien_thoai | Hợp lệ? |
|---|---|---|
| 'a@example.test' | NULL | Có |
| NULL | '0900000000' | Có |
| NULL | NULL | Không |
| 'a@example.test' | '0900000000' | Không |

Đây là quan hệ **XOR (exclusive OR)**. Nếu chỉ cần **ít nhất một** trong hai cột có giá trị và cho phép cả hai cùng có, dùng:

~~~sql
CHECK (email IS NOT NULL OR dien_thoai IS NOT NULL)
~~~

Nếu chỉ dùng `IS NOT NULL`, chuỗi rỗng `''` vẫn được xem là có giá trị trong PostgreSQL. Khi cần loại chuỗi rỗng/khoảng trắng, phải kết hợp thêm quy tắc dữ liệu chuỗi.

### 5.6. Quy tắc tùy thuộc một cột phân loại

Giả sử khách hàng có hai loại: `PERSONAL` và `BUSINESS`. Chỉ doanh nghiệp phải có mã số thuế; cá nhân không sử dụng cột này.

~~~sql
CREATE TABLE khach_hang_loai_demo (
    id INTEGER PRIMARY KEY,
    loai VARCHAR(20) NOT NULL
        CHECK (loai IN ('PERSONAL', 'BUSINESS')),
    ma_so_thue VARCHAR(30),
    CONSTRAINT ck_ma_so_thue_theo_loai
        CHECK (
            (loai = 'BUSINESS' AND ma_so_thue IS NOT NULL)
            OR
            (loai = 'PERSONAL' AND ma_so_thue IS NULL)
        )
);
~~~

Một doanh nghiệp có mã số thuế sẽ hợp lệ; doanh nghiệp thiếu mã sẽ bị từ chối. Cá nhân có mã số thuế lại cũng bị từ chối **theo mô hình giả định của bài**. Nếu nghiệp vụ thực cho phép mã số thuế đối với cá nhân, cần đổi quy tắc, không áp dụng cứng ví dụ.

Có thể viết cùng quy tắc bằng `CASE`:

~~~sql
CONSTRAINT ck_ma_so_thue_theo_loai
CHECK (
    CASE
        WHEN loai = 'BUSINESS'
            THEN ma_so_thue IS NOT NULL
        ELSE ma_so_thue IS NULL
    END
)
~~~

Đây là hai cách diễn đạt **cùng một yêu cầu trong ví dụ**; nên chọn cách người đọc dễ hiểu nhất. Với quy tắc phức tạp hơn, nhiều CHECK độc lập có tên rõ nghĩa thường dễ bảo trì hơn một biểu thức rất dài.

## 6. Bộ bảng thực hành hoàn chỉnh: đơn hàng

Phần này dùng PostgreSQL. Hãy chạy trên **database thử nghiệm** chưa có schema `check_lab`; đừng tạo hoặc xóa đối tượng này trong một hệ thống đang chứa dữ liệu cần giữ.

### 6.1. Tạo schema và bảng

~~~sql
CREATE SCHEMA check_lab;

CREATE TABLE check_lab.don_hang (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    ma_don VARCHAR(30) NOT NULL UNIQUE,
    trang_thai VARCHAR(20) NOT NULL DEFAULT 'NEW',
    so_luong INTEGER NOT NULL,
    don_gia NUMERIC(12,2) NOT NULL,
    giam_gia NUMERIC(12,2) NOT NULL DEFAULT 0,
    ngay_dat DATE NOT NULL,
    ngay_giao DATE,
    ngay_thanh_toan DATE,

    CONSTRAINT ck_don_trang_thai
        CHECK (trang_thai IN ('NEW', 'PAID', 'CANCELLED')),

    CONSTRAINT ck_don_so_luong
        CHECK (so_luong > 0),

    CONSTRAINT ck_don_don_gia
        CHECK (don_gia >= 0),

    CONSTRAINT ck_don_giam_gia
        CHECK (giam_gia >= 0
               AND giam_gia <= so_luong * don_gia),

    CONSTRAINT ck_don_ngay_giao
        CHECK (ngay_giao IS NULL
               OR ngay_giao >= ngay_dat),

    CONSTRAINT ck_don_paid
        CHECK (trang_thai <> 'PAID'
               OR ngay_thanh_toan IS NOT NULL)
);
~~~

Bảng này có những lớp bảo vệ:

1. `PRIMARY KEY` bảo vệ ID duy nhất.
2. `UNIQUE` bảo vệ mã đơn riêng biệt.
3. `NOT NULL` bắt buộc có những trường cốt lõi.
4. CHECK giới hạn trạng thái, số lượng và giá.
5. CHECK giữa nhiều cột bảo đảm giảm giá và thứ tự ngày.
6. CHECK có điều kiện bảo đảm đơn PAID có ngày thanh toán.

### 6.2. Dữ liệu hợp lệ

~~~sql
INSERT INTO check_lab.don_hang (
    ma_don, trang_thai, so_luong, don_gia, giam_gia,
    ngay_dat, ngay_giao, ngay_thanh_toan
)
VALUES
    (
        'DH-001', 'NEW', 2, 120000, 10000,
        DATE '2026-11-10', NULL, NULL
    ),
    (
        'DH-002', 'PAID', 1, 30000, 0,
        DATE '2026-11-11', DATE '2026-11-13',
        DATE '2026-11-11'
    ),
    (
        'DH-003', 'CANCELLED', 3, 15000, 0,
        DATE '2026-11-12', NULL, NULL
    );
~~~

Xem dữ liệu và tổng tiền sau giảm:

~~~sql
SELECT
    ma_don,
    trang_thai,
    so_luong,
    don_gia,
    giam_gia,
    so_luong * don_gia - giam_gia AS thanh_tien,
    ngay_dat,
    ngay_giao,
    ngay_thanh_toan
FROM check_lab.don_hang
ORDER BY ma_don;
~~~

| ma_don | trang_thai | so_luong | don_gia | giam_gia | thanh_tien |
|---|---|---:|---:|---:|---:|
| DH-001 | NEW | 2 | 120000 | 10000 | 230000 |
| DH-002 | PAID | 1 | 30000 | 0 | 30000 |
| DH-003 | CANCELLED | 3 | 15000 | 0 | 45000 |

Dòng CANCELLED vẫn có `thanh_tien` tính toán từ cột số: truy vấn này minh họa phép tính số học, **không đồng nghĩa khách hàng thực sự phải thanh toán tiền cho đơn đã hủy**. Nếu cần quy tắc tính doanh thu hoặc tiền hoàn, phải mô hình hóa riêng theo nghiệp vụ.

### 6.3. Xem lỗi của từng ràng buộc

Hãy chạy **từng câu riêng lẻ trong chế độ autocommit** hoặc chủ động dùng transaction/savepoint, vì một lỗi trong transaction PostgreSQL có thể khiến các câu sau bị từ chối cho đến khi rollback.

~~~sql
-- Vi phạm miền giá trị: so_luong phải > 0.
INSERT INTO check_lab.don_hang
    (ma_don, so_luong, don_gia, ngay_dat)
VALUES ('DH-BAD-QTY', 0, 10000, DATE '2026-11-14');
~~~

~~~sql
-- Vi phạm quan hệ giữa cột: giảm giá vượt 2 * 10000.
INSERT INTO check_lab.don_hang
    (ma_don, so_luong, don_gia, giam_gia, ngay_dat)
VALUES ('DH-BAD-DISCOUNT', 2, 10000, 30000, DATE '2026-11-14');
~~~

~~~sql
-- Vi phạm quy tắc PAID phải có ngày thanh toán.
INSERT INTO check_lab.don_hang
    (ma_don, trang_thai, so_luong, don_gia, ngay_dat)
VALUES ('DH-BAD-PAID', 'PAID', 1, 10000, DATE '2026-11-14');
~~~

~~~sql
-- Vi phạm thứ tự ngày.
INSERT INTO check_lab.don_hang
    (ma_don, so_luong, don_gia, ngay_dat, ngay_giao)
VALUES (
    'DH-BAD-DATE', 1, 10000,
    DATE '2026-11-14', DATE '2026-11-12'
);
~~~

PostgreSQL sẽ báo lỗi vi phạm CHECK và có thể nêu tên `ck_don_so_luong`, `ck_don_giam_gia`, `ck_don_paid` hoặc `ck_don_ngay_giao` tương ứng. Mỗi lệnh thất bại không nên thêm dòng sai vào bảng.

### 6.4. CHECK cũng được đánh giá khi UPDATE

~~~sql
-- Hợp lệ: ngày giao không trước ngày đặt.
UPDATE check_lab.don_hang
SET ngay_giao = DATE '2026-11-12'
WHERE ma_don = 'DH-001';
~~~

Sau đó:

~~~sql
-- Bị từ chối: ngày giao sớm hơn ngày đặt.
UPDATE check_lab.don_hang
SET ngay_giao = DATE '2026-11-09'
WHERE ma_don = 'DH-001';
~~~

CHECK bảo vệ **trạng thái cuối của hàng sau mỗi statement được kiểm tra**, không chỉ dữ liệu chèn ban đầu. Nếu cập nhật nhiều cột của **cùng một dòng trong một UPDATE**, hãy đưa toàn bộ giá trị cuối cùng hợp lệ vào chung một câu:

~~~sql
UPDATE check_lab.don_hang
SET trang_thai = 'PAID',
    ngay_thanh_toan = DATE '2026-11-12'
WHERE ma_don = 'DH-001';
~~~

Câu trên hợp lệ. Ngược lại, một UPDATE chỉ đổi `trang_thai` sang PAID khi `ngay_thanh_toan` đang NULL sẽ bị từ chối; không thể dựa vào ý định “lệnh kế tiếp sẽ điền ngày” để cho hàng tồn tại tạm thời ở trạng thái vi phạm CHECK.

### 6.5. Một statement sửa nhiều hàng thì sao?

~~~sql
-- Minh họa nguy cơ: nếu kết quả tạo ra bất kỳ hàng vi phạm CHECK,
-- PostgreSQL sẽ từ chối cả statement.
UPDATE check_lab.don_hang
SET giam_gia = 999999;
~~~

Với dữ liệu mẫu, giá trị giảm vượt tổng tiền cho nhiều dòng. Trong PostgreSQL, một statement cập nhật nhiều dòng là nguyên tử: nếu CHECK thất bại, **không có một phần cập nhật của statement đó được chấp nhận**. Đây là một lý do nên đặt quy tắc toàn vẹn ở database thay vì chỉ kiểm tra từng dòng ở giao diện.

## 7. Thêm CHECK vào bảng đã tồn tại

Trong hệ thống thực tế, bạn thường gặp bảng đã có dữ liệu và cần tăng cường ràng buộc sau này.

### 7.1. ALTER TABLE ADD CONSTRAINT

Giả sử bảng `nhan_vien_demo` đang có cột `luong`:

~~~sql
CREATE TABLE nhan_vien_demo (
    id INTEGER PRIMARY KEY,
    luong NUMERIC(12,2)
);
~~~

Để thêm quy tắc lương không âm:

~~~sql
ALTER TABLE nhan_vien_demo
ADD CONSTRAINT ck_nhan_vien_luong
CHECK (luong >= 0);
~~~

Vì `luong` chưa có NOT NULL, NULL vẫn được chấp nhận. Nếu nghiệp vụ yêu cầu lương bắt buộc, có thể bổ sung `NOT NULL` sau khi xử lý dữ liệu đang thiếu:

~~~sql
ALTER TABLE nhan_vien_demo
ALTER COLUMN luong SET NOT NULL;
~~~

### 7.2. Nếu dữ liệu cũ đang vi phạm

Ví dụ:

~~~sql
INSERT INTO nhan_vien_demo (id, luong)
VALUES (1, 12000000), (2, -100000);
~~~

Nếu thêm CHECK lúc bảng còn dòng có lương âm, việc thêm ràng buộc theo cách thông thường trên PostgreSQL sẽ thất bại. Bạn cần tìm và xử lý bản ghi cũ theo quy tắc nghiệp vụ, rồi mới đặt CHECK.

Truy vấn kiểm tra cho ví dụ:

~~~sql
SELECT id, luong
FROM nhan_vien_demo
WHERE luong < 0;
~~~

Nếu không cho phép NULL, kiểm tra thêm:

~~~sql
SELECT id, luong
FROM nhan_vien_demo
WHERE luong IS NULL;
~~~

Không nên sửa dữ liệu âm thành 0 một cách máy móc nếu chưa hiểu đây là lỗi nhập liệu, khoản điều chỉnh hay một quy tắc nghiệp vụ khác. Hãy xác nhận ngữ nghĩa trước khi migration.

### 7.3. PostgreSQL: NOT VALID và VALIDATE CONSTRAINT

Với bảng lớn, PostgreSQL cho phép thêm CHECK mà **chưa quét xác minh toàn bộ dữ liệu cũ** ngay trong bước tạo:

~~~sql
ALTER TABLE nhan_vien_demo
ADD CONSTRAINT ck_nhan_vien_luong
CHECK (luong >= 0) NOT VALID;
~~~

Sau khi thêm bằng `NOT VALID`:

- Dữ liệu **đã tồn tại trước đó** có thể vẫn vi phạm ràng buộc.
- Các hàng **mới chèn** và các hàng **được cập nhật** phải tuân thủ CHECK.
- Ràng buộc chưa được xác nhận là hợp lệ cho toàn bộ bảng.

Sau khi xử lý dòng cũ, chạy:

~~~sql
ALTER TABLE nhan_vien_demo
VALIDATE CONSTRAINT ck_nhan_vien_luong;
~~~

Nếu còn dữ liệu vi phạm, bước xác nhận sẽ thất bại và cần tiếp tục xử lý. Việc sử dụng `NOT VALID` là cơ chế migration của PostgreSQL, **không có nghĩa tắt CHECK cho những thao tác ghi mới**.

Lưu ý trong ví dụ này: hãy chọn **một** hướng thêm ràng buộc: thêm trực tiếp ở mục 7.1, **hoặc** thêm `NOT VALID` ở mục 7.3. Không chạy cả hai với cùng tên trên một bảng đã có ràng buộc đó; sẽ gặp lỗi trùng tên ràng buộc.

### 7.4. Đổi hoặc bỏ CHECK đã có

Trong PostgreSQL, khi cần sửa biểu thức CHECK, một phương án phổ biến là tạo migration có kiểm soát để **bỏ ràng buộc cũ và thêm ràng buộc mới**:

~~~sql
-- Chỉ là ví dụ khi muốn đổi phạm vi lương.
ALTER TABLE nhan_vien_demo
DROP CONSTRAINT ck_nhan_vien_luong;

ALTER TABLE nhan_vien_demo
ADD CONSTRAINT ck_nhan_vien_luong
CHECK (luong BETWEEN 0 AND 1000000000);
~~~

Trên môi trường thực tế, cần cân nhắc thực hiện các bước phù hợp trong transaction, xác minh dữ liệu trước và tránh khoảng thời gian cho phép ghi dữ liệu sai quy tắc. Việc thay CHECK có thể ảnh hưởng các lệnh INSERT/UPDATE hiện hữu của ứng dụng.

Đổi tên constraint, nếu chỉ muốn đổi tên mà giữ quy tắc, cũng có cú pháp PostgreSQL:

~~~sql
ALTER TABLE nhan_vien_demo
RENAME CONSTRAINT ck_nhan_vien_luong
TO ck_nhan_vien_luong_hop_le;
~~~

Đừng thay đổi tên hoặc quy tắc chỉ vì nhận được lỗi: trước hết xem bản ghi và mục tiêu nghiệp vụ.

## 8. CHECK không thể thay tất cả quy tắc toàn vẹn

Một CHECK thông thường được đánh giá trên **một hàng**. Một số yêu cầu cần đọc dữ liệu khác, kiểm soát liên tiếp nhiều giao dịch hoặc so sánh nhiều hàng; đó không phải vai trò phù hợp của CHECK.

### 8.1. Không dùng CHECK để tra dữ liệu ở bảng khác

Ví dụ yêu cầu: “`don_hang.khach_hang_id` phải trỏ tới một khách hàng có thật”.

Đây là nhiệm vụ của `FOREIGN KEY`:

~~~sql
CREATE TABLE khach_hang_fk_demo (
    id INTEGER PRIMARY KEY,
    ten VARCHAR(100) NOT NULL
);

CREATE TABLE don_hang_fk_demo (
    id INTEGER PRIMARY KEY,
    khach_hang_id INTEGER NOT NULL,
    CONSTRAINT fk_don_khach
        FOREIGN KEY (khach_hang_id)
        REFERENCES khach_hang_fk_demo(id)
);
~~~

Không cố viết `CHECK (EXISTS (SELECT ...))` trong PostgreSQL: CHECK không hỗ trợ truy vấn con tham chiếu bảng khác theo cách đó. Dù một hệ cho phép gọi hàm tự định nghĩa từ CHECK, việc hàm đọc dữ liệu ngoài hàng tạo ra vấn đề về tính ổn định khi hàng liên quan thay đổi.

### 8.2. Không dùng CHECK để ngăn trùng dữ liệu giữa các hàng

Yêu cầu: “email không được trùng” là nhiệm vụ của `UNIQUE`:

~~~sql
CREATE TABLE nguoi_dung_unique_demo (
    id INTEGER PRIMARY KEY,
    email VARCHAR(255) NOT NULL UNIQUE
);
~~~

CHECK chỉ nhìn điều kiện của hàng hiện tại, nên không tự bảo đảm rằng giá trị email mới không trùng hàng khác.

### 8.3. Không dùng CHECK để giới hạn số hàng của một nhóm

Ví dụ: “mỗi phòng chỉ tối đa 10 nhân viên”. Điều kiện này cần **đếm các hàng khác** và có thể bị ảnh hưởng bởi thao tác đồng thời. Cần thiết kế cách kiểm soát phù hợp: thao tác transaction có khóa, trigger, mô hình dữ liệu chuyên biệt hoặc kiểm soát nghiệp vụ với cơ chế đồng bộ bảo đảm tính đúng đắn. CHECK trên từng hàng không thể trực tiếp biểu đạt “COUNT của phòng không vượt 10”.

### 8.4. Không dùng CHECK để so sánh với thời điểm thay đổi liên tục

Một ý tưởng thường gặp:

~~~sql
-- Không nên dùng quy tắc thay đổi theo thời gian làm CHECK cố định.
CHECK (ngay_het_han >= CURRENT_DATE)
~~~

Giả sử hôm nay điều kiện đúng; ngày mai hàng có thể trở nên “hết hạn” dù không ai cập nhật hàng. CHECK thường được kiểm tra khi **ghi dữ liệu**, không liên tục kiểm tra lại theo thời gian trôi. PostgreSQL còn giả định biểu thức CHECK là bất biến với cùng dữ liệu hàng cho mục đích toàn vẹn. Điều kiện phụ thuộc thời gian, cấu hình phiên hoặc trạng thái bên ngoài có thể gây sai lệch.

Nếu yêu cầu “khi tạo, ngày hết hạn không được ở quá khứ”, nên kiểm tra ở điểm thực hiện thao tác, hoặc dùng trigger/cơ chế phù hợp khi cần database cưỡng chế và có kiểm soát thời điểm. Để biết **hiện tại có hết hạn không**, truy vấn `ngay_het_han < CURRENT_DATE` là câu hỏi tại thời điểm đọc, không cần cập nhật CHECK mỗi ngày.

### 8.5. Không che giấu điều kiện ngoài hàng trong hàm tùy biến

PostgreSQL cho phép CHECK gọi một số hàm, nhưng hệ thống xem CHECK như biểu thức ổn định đối với giá trị của hàng. Nếu hàm đọc bảng khác, dùng trạng thái bên ngoài hoặc sau đó thay đổi cách hoạt động, các hàng đã lưu có thể bị vi phạm mà PostgreSQL không tự kiểm tra lại.

Khi thay đổi nội dung một hàm được dùng trong CHECK, phải có kế hoạch kiểm tra lại dữ liệu và quản lý ràng buộc, nhất là với backup/restore. Những quy tắc chỉ phụ thuộc các cột hiện tại và hàm xác định rõ thường an toàn, dễ hiểu hơn.

### 8.6. CHECK không phải luật cho cả transaction

Trong PostgreSQL, CHECK không phải loại constraint có thể `DEFERRABLE` để chờ đến COMMIT như một số ràng buộc khác. Một hàng phải thỏa CHECK ở thời điểm statement kiểm tra.

Nếu cần thay đổi hai cột phụ thuộc nhau, hãy cập nhật chúng **trong một statement** thành trạng thái cuối hợp lệ. Nếu quy trình bắt buộc đi qua trạng thái trung gian vi phạm giữa các statement, cần thiết kế lại quy trình hoặc cơ chế ràng buộc cho phù hợp; không giả định `SET CONSTRAINTS ALL DEFERRED` sẽ trì hoãn CHECK PostgreSQL.

## 9. Thực thi CHECK trong môi trường nhiều ứng dụng

### 9.1. Vì sao kiểm tra ở ứng dụng chưa đủ?

Một ứng dụng web có thể kiểm tra số lượng trước khi gửi INSERT:

~~~text
Form/UI kiểm tra so_luong > 0
            ↓
API kiểm tra so_luong > 0
            ↓
Database CHECK (so_luong > 0)
~~~

Nhiều đường ghi khác nhau có thể tồn tại: ứng dụng web, tác vụ nhập dữ liệu, script vận hành, API khác, công cụ quản trị. CHECK ở database giúp bảo vệ quy tắc ngay cả khi một đường ghi không có cùng logic kiểm tra.

Tuy nhiên, chỉ database từ chối dữ liệu chưa tạo trải nghiệm người dùng tốt. Ứng dụng vẫn nên trả thông báo dễ hiểu, ví dụ “Số lượng phải lớn hơn 0”, đồng thời xử lý ngoại lệ từ database.

### 9.2. CHECK hoạt động với UPDATE và ghi hàng loạt

Không chỉ `INSERT`, một câu `UPDATE` cũng phải tuân thủ CHECK. Trong PostgreSQL, nếu một statement ghi nhiều hàng khiến ít nhất một hàng vi phạm, statement bị từ chối và không cập nhật một phần dữ liệu của chính statement đó.

Tùy chế độ nhập dữ liệu của mỗi DBMS, việc nạp dữ liệu hàng loạt có thể dùng cơ chế đặc biệt; cần xác nhận rằng các ràng buộc vẫn được thực thi và không có tùy chọn bỏ qua kiểm tra. Khi kiểm soát chất lượng dữ liệu, đừng chỉ tin rằng import “thành công” mà không xem các cảnh báo hoặc cấu hình kiểm tra.

### 9.3. CHECK và transaction

Ví dụ PostgreSQL:

~~~sql
BEGIN;

UPDATE check_lab.don_hang
SET trang_thai = 'PAID'
WHERE ma_don = 'DH-003';

-- Dòng DH-003 có ngay_thanh_toan NULL:
-- UPDATE thất bại vì ck_don_paid.

ROLLBACK;
~~~

Một lỗi trong transaction PostgreSQL thường khiến transaction vào trạng thái thất bại, và bạn cần `ROLLBACK` (hoặc rollback về savepoint thích hợp) để làm việc tiếp.

Đối với các lệnh có khả năng lỗi trong bài học, hãy thực thi từng lệnh riêng hoặc sử dụng savepoint nếu muốn nghiên cứu nhiều lỗi trong một phiên.

### 9.4. Không nên lạm dụng CHECK thành biểu thức quá khó đọc

Một CHECK khổng lồ kết hợp nhiều quy tắc sẽ khó xác định lỗi và khó sửa. Nếu các quy tắc có thể tách độc lập, hãy dùng các constraint có tên riêng:

~~~sql
CONSTRAINT ck_gia CHECK (gia >= 0),
CONSTRAINT ck_so_luong CHECK (so_luong > 0),
CONSTRAINT ck_giam_gia
    CHECK (giam_gia >= 0 AND giam_gia <= gia * so_luong)
~~~

Đây là **các thành phần để khai báo trong CREATE TABLE**, không phải SQL độc lập. Việc tách giúp thấy rõ chính xác quy tắc nào bị vi phạm.

## 10. Đọc và điều tra lỗi CHECK

Ví dụ khi lệnh ghi trái quy tắc của PostgreSQL:

~~~text
ERROR: new row for relation "don_hang" violates check constraint "ck_don_giam_gia"
DETAIL: Failing row contains (...)
SQLSTATE: 23514
~~~

Không phải mọi client đều hiển thị toàn bộ `DETAIL` hoặc `SQLSTATE`. Có thể phải mở phần chi tiết lỗi trong IDE hoặc SQL client.

Khi gặp lỗi:

1. **Xác định constraint nào thất bại** từ thông báo và tên ràng buộc.
2. **Đọc định nghĩa CHECK** để hiểu phạm vi giá trị hợp lệ.
3. **Xem các cột đầu vào** và các giá trị cũ nếu đây là UPDATE.
4. **Kiểm tra NULL, dấu biên và đơn vị** (ví dụ 0–1 hay 0–100 cho tỷ lệ).
5. **Sửa dữ liệu hoặc nghiệp vụ** theo quy tắc đã thống nhất; chỉ sửa CHECK nếu quy tắc nghiệp vụ thực sự thay đổi.
6. **Kiểm tra transaction**: một lỗi trước có thể khiến các lệnh sau bị từ chối do trạng thái transaction đã thất bại.

### 10.1. Xem định nghĩa constraint trong PostgreSQL

Query catalog dưới đây lấy các CHECK của một bảng mẫu:

~~~sql
SELECT
    c.conname AS ten_rang_buoc,
    pg_get_constraintdef(c.oid) AS dinh_nghia
FROM pg_constraint AS c
JOIN pg_class AS t
    ON t.oid = c.conrelid
JOIN pg_namespace AS n
    ON n.oid = t.relnamespace
WHERE n.nspname = 'check_lab'
  AND t.relname = 'don_hang'
  AND c.contype = 'c'
ORDER BY c.conname;
~~~

Đây là cách dùng catalog riêng của PostgreSQL. Trong `psql`, lệnh meta:

~~~text
\d check_lab.don_hang
~~~

cũng giúp xem cột và ràng buộc. Lệnh `\d` không phải SQL chuẩn nên không chạy trong mọi DB client.

### 10.2. Phân biệt lỗi CHECK với lỗi ràng buộc khác

| Ví dụ tình huống | Ràng buộc thường báo lỗi |
|---|---|
| `so_luong = -1` | CHECK |
| `so_luong = NULL` nhưng cột NOT NULL | NOT NULL |
| Hai hàng có `ma_don` giống nhau | UNIQUE |
| Hai hàng có `id` giống nhau | PRIMARY KEY |
| `khach_hang_id` trỏ tới ID không tồn tại | FOREIGN KEY |
| Kiểu số nhận chuỗi không thể chuyển thành số | Lỗi chuyển kiểu trước khi đánh giá CHECK |

Không nên suy từ việc “giá trị không hợp lệ” mà kết luận lỗi luôn là CHECK. Tên ràng buộc và mã lỗi cho biết lớp kiểm tra cụ thể.

## 11. CHECK giữa các hệ quản trị SQL

Ngữ nghĩa của CHECK dựa trên điều kiện logic là phổ biến, nhưng **mức độ hỗ trợ và cú pháp đặc biệt phụ thuộc hệ quản trị, phiên bản, chế độ vận hành**.

| Hệ quản trị | Cách khai báo phổ biến | Lưu ý |
|---|---|---|
| **PostgreSQL** | `CHECK (bieu_thuc)`, `CONSTRAINT ten CHECK (...)` | Hỗ trợ CHECK ở mức cột/bảng; có `NOT VALID` và `VALIDATE CONSTRAINT` |
| **MySQL** | `CHECK (bieu_thuc)` | MySQL từ **8.0.16** mới thực thi CHECK theo cách thông thường; các bản cũ có thể phân tích cú pháp nhưng bỏ qua |
| **MariaDB** | `CHECK (bieu_thuc)` | Hỗ trợ cưỡng chế CHECK tùy phiên bản; cần xác nhận bản đang dùng, đặc biệt hệ cũ |
| **SQL Server** | `CONSTRAINT ten CHECK (bieu_thuc)` | Có cơ chế `WITH CHECK`/`WITH NOCHECK` và trạng thái tin cậy của constraint |
| **Oracle** | `CONSTRAINT ten CHECK (bieu_thuc)` | Hỗ trợ CHECK; có cơ chế ENABLE/DISABLE và VALIDATE/NOVALIDATE tùy trường hợp |
| **SQLite** | `CHECK (bieu_thuc)` trong CREATE TABLE | CHECK thường được thực thi, nhưng có cài đặt có thể bỏ qua CHECK; thay đổi ràng buộc cho bảng cũ thường phải tái tạo bảng theo quy trình |

### 11.1. PostgreSQL

~~~sql
CREATE TABLE pg_check_demo (
    id INTEGER PRIMARY KEY,
    gia NUMERIC(12,2) NOT NULL,
    so_luong INTEGER NOT NULL,
    CONSTRAINT ck_pg_gia CHECK (gia >= 0),
    CONSTRAINT ck_pg_so_luong CHECK (so_luong > 0)
);
~~~

Các quy tắc trên được kiểm tra ở INSERT và UPDATE. Cột nullable cần xử lý rõ vì UNKNOWN không bị CHECK từ chối. PostgreSQL không hỗ trợ subquery bên trong CHECK để tham chiếu các dòng hoặc bảng khác.

### 11.2. MySQL và MariaDB

Ví dụ trên MySQL 8.0.16+:

~~~sql
CREATE TABLE mysql_check_demo (
    id INT PRIMARY KEY,
    so_luong INT NOT NULL,
    gia DECIMAL(12,2) NOT NULL,
    CONSTRAINT ck_mysql_so_luong CHECK (so_luong > 0),
    CONSTRAINT ck_mysql_gia CHECK (gia >= 0)
);
~~~

Nếu dùng một phiên MySQL rất cũ, câu `CHECK` có thể được chấp nhận khi phân tích cú pháp nhưng **không được thực thi**; do đó thử lệnh chèn sai trên môi trường kiểm thử là cách quan sát việc cưỡng chế của phiên bản thực tế. MySQL/MariaDB cũng có những giới hạn riêng về biểu thức được phép trong CHECK.

Trong hệ có chế độ SQL hoặc cấu hình đặc biệt, đừng nhầm CHECK với những quy tắc chuyển đổi kiểu dữ liệu (chẳng hạn giá trị số được chuyển từ chuỗi). Kiểm tra dữ liệu sau chuyển đổi có thể cho kết quả khác mong đợi từ dữ liệu đầu vào.

### 11.3. SQL Server

~~~sql
CREATE TABLE dbo.sqlserver_check_demo (
    id INT PRIMARY KEY,
    so_luong INT NOT NULL,
    gia DECIMAL(12,2) NOT NULL,
    CONSTRAINT ck_ss_so_luong CHECK (so_luong > 0),
    CONSTRAINT ck_ss_gia CHECK (gia >= 0)
);
~~~

SQL Server hỗ trợ kiểm tra mối quan hệ giữa các cột:

~~~sql
CREATE TABLE dbo.ky_han_demo (
    id INT PRIMARY KEY,
    bat_dau DATE NOT NULL,
    ket_thuc DATE NOT NULL,
    CONSTRAINT ck_ss_ky_han CHECK (ket_thuc >= bat_dau)
);
~~~

SQL Server có thể có CHECK ở trạng thái **disabled** hoặc **not trusted** nếu dùng các tùy chọn như `WITH NOCHECK` khi xử lý dữ liệu cũ. Điều đó ảnh hưởng tới việc cưỡng chế và khả năng optimizer tin tưởng constraint. Người quản trị cần kiểm tra trạng thái thực tế trước khi khẳng định toàn bộ dữ liệu đã hợp lệ.

### 11.4. Oracle

~~~sql
CREATE TABLE oracle_check_demo (
    id NUMBER(10) PRIMARY KEY,
    so_luong NUMBER(10) NOT NULL,
    gia NUMBER(12,2) NOT NULL,
    CONSTRAINT ck_oracle_so_luong CHECK (so_luong > 0),
    CONSTRAINT ck_oracle_gia CHECK (gia >= 0)
);
~~~

Oracle hỗ trợ CHECK giữa nhiều cột của cùng hàng và có những lựa chọn quản trị constraint như ENABLE/DISABLE, VALIDATE/NOVALIDATE theo phiên bản và cú pháp tương ứng. CHECK không thể thay khóa ngoại khi cần xác nhận một bản ghi ở bảng khác.

Cần lưu ý Oracle SQL lịch sử có xử lý chuỗi rỗng khác PostgreSQL, nên khi viết CHECK về cột chuỗi hãy kiểm tra behavior của phiên bản và kiểu cột thực tế.

### 11.5. SQLite

~~~sql
CREATE TABLE sqlite_check_demo (
    id INTEGER PRIMARY KEY,
    so_luong INTEGER NOT NULL CHECK (so_luong > 0),
    gia NUMERIC NOT NULL CHECK (gia >= 0)
);
~~~

SQLite có hệ thống kiểu linh hoạt hơn nhiều DBMS và không có mọi cú pháp `ALTER TABLE ... ADD CONSTRAINT` như PostgreSQL. Khi cần sửa CHECK ở một bảng cũ, quy trình thường là tạo bảng mới với ràng buộc mới, chuyển dữ liệu, quản lý FK/index/trigger liên quan rồi đổi bảng trong transaction theo cách được SQLite hỗ trợ.

SQLite còn có `PRAGMA ignore_check_constraints` có thể làm bỏ qua việc cưỡng chế CHECK khi bật. Nếu đang kiểm tra một SQLite database có vẻ nhận dữ liệu trái ràng buộc, cần xem cả định nghĩa bảng, chế độ runtime và dữ liệu đã tồn tại.

### 11.6. Không mang nguyên cú pháp đặc thù sang DBMS khác

Các chi tiết sau không nhất thiết tương đương:

- Regex `~` của PostgreSQL.
- `NOT VALID` và `VALIDATE CONSTRAINT` của PostgreSQL.
- `WITH NOCHECK` của SQL Server.
- Tên kiểu dữ liệu `NUMERIC`, `DECIMAL` và cách chuyển đổi dữ liệu.
- Cách xử lý NULL và chuỗi rỗng.
- Tính năng thêm hoặc sửa CHECK bằng `ALTER TABLE`.
- Khả năng các ràng buộc bị vô hiệu hóa khi nhập dữ liệu.

Với hệ quản trị mới, hãy xác minh phiên bản và thử quy tắc trên database test trước khi áp dụng migration.

## 12. Thiết kế CHECK theo nghiệp vụ thay vì đặt tùy tiện

Một biểu thức hợp lệ về cú pháp chưa chắc đúng về ý nghĩa.

### 12.1. Xác định biên trước khi viết biểu thức

Giả sử một điểm đánh giá có thang 0–100:

- Nếu cho phép 0 và 100, dùng `BETWEEN 0 AND 100`.
- Nếu điểm phải lớn hơn 0, dùng `diem > 0 AND diem <= 100`.
- Nếu được phép chưa có điểm, cột có thể nullable.
- Nếu bắt buộc có điểm, cần `NOT NULL`.

Việc “0 điểm” khác với “chưa chấm” nên không dùng 0 thay NULL một cách máy móc.

### 12.2. Đặt tên constraint thể hiện quy tắc

Tên `ck_don_giam_gia` giúp nhanh chóng hiểu rằng lỗi liên quan đến giảm giá. Một tên `check1` hoặc `constraint_123` sẽ khó đối chiếu khi bảng có nhiều quy tắc.

Một số dự án dùng cách đặt tên:

~~~text
ck_<bang>_<y_nghia>
ck_don_hang_so_luong_duong
ck_don_hang_giam_gia_hop_le
ck_hop_dong_thoi_han
~~~

Quy ước đặt tên không bắt buộc, nhưng nên thống nhất trong dự án.

### 12.3. Giữ đơn vị và công thức nhất quán

Nếu `ty_le_giam` lưu dưới dạng **phần trăm 0–100**, CHECK đúng có thể là `BETWEEN 0 AND 100`. Nếu lưu dưới dạng **hệ số 0–1**, CHECK phải là `BETWEEN 0 AND 1`. Hai cách đều hợp lệ nếu dùng nhất quán trong database, ứng dụng và báo cáo.

Nếu biểu thức so sánh số tiền:

~~~sql
CHECK (giam_gia <= so_luong * don_gia)
~~~

hãy bảo đảm `giam_gia` và `don_gia` cùng loại tiền tệ và đơn vị. CHECK không thể tự phát hiện hai giá trị dùng hai đồng tiền khác nhau nếu bạn chỉ lưu số.

### 12.4. Sắp xếp phụ thuộc khi thay đổi trạng thái

Giả sử quy tắc PAID yêu cầu ngày thanh toán. Một quy trình chuyển trạng thái nên cập nhật đồng thời các trường:

~~~sql
UPDATE check_lab.don_hang
SET trang_thai = 'PAID',
    ngay_thanh_toan = CURRENT_DATE
WHERE ma_don = 'DH-003';
~~~

Trong ví dụ này, việc `CURRENT_DATE` được dùng để **gán ngày tại lúc cập nhật** khác với việc đưa `CURRENT_DATE` vào CHECK để so sánh liên tục theo ngày. Sau khi đã lưu, CHECK chỉ cần xác minh rằng ngày thanh toán không NULL.

## 13. Bài tập tự luyện

Các bài dưới đây có thể làm trong một database PostgreSQL thử nghiệm. Để tránh phụ thuộc vào bảng đang dùng ở các phần trước, mỗi bài đặt tên riêng.

### Bài 1. Kiểm tra điểm và NULL

Cho bảng:

~~~sql
CREATE TABLE bai1_diem (
    id INTEGER PRIMARY KEY,
    diem INTEGER CHECK (diem BETWEEN 0 AND 10)
);
~~~

Dự đoán câu nào hợp lệ:

~~~sql
INSERT INTO bai1_diem VALUES (1, 0);
INSERT INTO bai1_diem VALUES (2, 10);
INSERT INTO bai1_diem VALUES (3, 11);
INSERT INTO bai1_diem VALUES (4, NULL);
~~~

**Đáp án:** dòng 1 và 2 hợp lệ vì `BETWEEN` gồm hai biên; dòng 3 vi phạm CHECK; dòng 4 vẫn hợp lệ vì CHECK trả UNKNOWN với NULL. Nếu muốn từ chối dòng 4, thêm `NOT NULL`.

### Bài 2. Khoảng thời gian tùy chọn

Một sự kiện có hai cột `bat_dau_luc` và `ket_thuc_luc`. Yêu cầu: hoặc cả hai NULL (chưa lên lịch), hoặc cả hai có giá trị và thời điểm kết thúc phải muộn hơn bắt đầu.

Viết bảng với CHECK.

**Lời giải:**

~~~sql
CREATE TABLE bai2_su_kien (
    id INTEGER PRIMARY KEY,
    bat_dau_luc TIMESTAMP,
    ket_thuc_luc TIMESTAMP,
    CONSTRAINT ck_bai2_cap_thoi_gian
        CHECK (
            (bat_dau_luc IS NULL AND ket_thuc_luc IS NULL)
            OR
            (bat_dau_luc IS NOT NULL
             AND ket_thuc_luc IS NOT NULL
             AND ket_thuc_luc > bat_dau_luc)
        )
);
~~~

Nếu một cột có giá trị và cột kia NULL, cả hai nhánh OR đều sai nên bị từ chối.

### Bài 3. Đúng một cách thanh toán

Một đơn thanh toán được bằng tiền mặt hoặc chuyển khoản. Hai cột `ma_giao_dich` và `so_bien_lai_tien_mat` cùng nullable. Hãy bảo đảm **đúng một** cột có giá trị.

**Lời giải:**

~~~sql
CREATE TABLE bai3_thanh_toan (
    id INTEGER PRIMARY KEY,
    ma_giao_dich VARCHAR(60),
    so_bien_lai_tien_mat VARCHAR(60),
    CONSTRAINT ck_bai3_mot_phuong_thuc
        CHECK (
            (ma_giao_dich IS NOT NULL
             AND so_bien_lai_tien_mat IS NULL)
            OR
            (ma_giao_dich IS NULL
             AND so_bien_lai_tien_mat IS NOT NULL)
        )
);
~~~

Nếu nghiệp vụ cho phép một phương thức chưa được chọn, phải điều chỉnh quy tắc thay vì giữ CHECK “đúng một”.

### Bài 4. Ràng buộc hai chiều

Một hồ sơ có `trang_thai` thuộc `'DRAFT'` hoặc `'APPROVED'` và `ngay_duyet` nullable. Quy tắc: **APPROVED khi và chỉ khi ngay_duyet có giá trị**.

**Lời giải:**

~~~sql
CREATE TABLE bai4_ho_so (
    id INTEGER PRIMARY KEY,
    trang_thai VARCHAR(20) NOT NULL
        CHECK (trang_thai IN ('DRAFT', 'APPROVED')),
    ngay_duyet DATE,
    CONSTRAINT ck_bai4_trang_thai_ngay
        CHECK (
            (trang_thai = 'APPROVED'
             AND ngay_duyet IS NOT NULL)
            OR
            (trang_thai = 'DRAFT'
             AND ngay_duyet IS NULL)
        )
);
~~~

`NOT NULL` và `IN` trên trạng thái giúp phép so sánh trạng thái không bị UNKNOWN.

### Bài 5. Tìm lỗi trong CHECK

Xét khai báo:

~~~sql
CREATE TABLE bai5_san_pham (
    id INTEGER PRIMARY KEY,
    so_luong INTEGER,
    CHECK (so_luong >= 0)
);
~~~

Yêu cầu nghiệp vụ là “số lượng phải là **số nguyên từ 0 trở lên, không được thiếu**”. Bảng có đáp ứng chưa?

**Đáp án:** Chưa. `so_luong = NULL` vẫn được chấp nhận, vì CHECK không từ chối UNKNOWN. Cần sửa cột thành `so_luong INTEGER NOT NULL CHECK (so_luong >= 0)`.

### Bài 6. Chọn CHECK, UNIQUE hay FOREIGN KEY

Xác định ràng buộc thích hợp:

| Yêu cầu | Ràng buộc phù hợp |
|---|---|
| Giá sản phẩm không âm | CHECK |
| Email khách hàng không trùng | UNIQUE |
| Mỗi đơn tham chiếu khách hàng tồn tại | FOREIGN KEY |
| ID đơn hàng duy nhất và không NULL | PRIMARY KEY |
| Ngày kết thúc không trước ngày bắt đầu | CHECK |
| Mã số thuế bắt buộc ở khách hàng doanh nghiệp | CHECK giữa các cột, kèm NOT NULL ở cột phân loại |
| Một phòng tối đa 10 nhân viên | Không thể bảo đảm bằng CHECK từng hàng; cần cơ chế khác |

Mục tiêu không phải dùng CHECK cho mọi việc, mà chọn ràng buộc diễn đạt đúng nhất quy tắc.

### Bài 7. Phát hiện dữ liệu cũ trước migration

Một bảng cũ có `so_luong` và `gia` nullable. Bạn cần thêm `NOT NULL` và `CHECK (so_luong > 0)`, `CHECK (gia >= 0)`. Hãy tìm hàng không hợp lệ trước.

**Lời giải:**

~~~sql
-- Giả định bảng ton_kho_cu(id, so_luong, gia) đã tồn tại.
SELECT id, so_luong, gia
FROM ton_kho_cu
WHERE so_luong IS NULL
   OR so_luong <= 0
   OR gia IS NULL
   OR gia < 0;
~~~

Đây là câu truy vấn cho bảng giả định; cần tạo bảng hoặc đổi tên thật trước khi chạy. Sau khi phát hiện dữ liệu lỗi, hãy quyết định cách xử lý có ý nghĩa nghiệp vụ, rồi mới thêm ràng buộc.

## 14. Ghi nhớ

**`CHECK` bảo vệ các quy tắc dữ liệu có thể kiểm tra từ giá trị của một hàng.** Nó hữu ích để giới hạn số lượng, giá, điểm, trạng thái và để kiểm tra quan hệ như “ngày kết thúc không trước ngày bắt đầu”, “giảm giá không vượt tổng tiền”, “đơn PAID phải có ngày thanh toán” hoặc “chỉ một trong hai trường được cung cấp”.

Cần nhớ bốn nguyên tắc:

1. **CHECK từ chối FALSE nhưng thông thường chấp nhận UNKNOWN.** Hãy dùng `NOT NULL` và kiểm tra NULL tường minh khi nghiệp vụ yêu cầu.
2. **CHECK được thực thi khi INSERT và UPDATE**, nên mối quan hệ giữa các cột phải hợp lệ sau mỗi thao tác được kiểm tra.
3. **CHECK không thay thế PRIMARY KEY, UNIQUE, FOREIGN KEY** và không phù hợp với quy tắc phải đọc nhiều hàng, tra bảng khác hoặc phụ thuộc thời gian thay đổi liên tục.
4. **Cú pháp và cách cưỡng chế CHECK phụ thuộc DBMS/phiên bản**; đặc biệt cần lưu ý MySQL cũ, các tùy chọn bỏ qua xác thực ràng buộc và quy trình thêm ràng buộc trên bảng đã có dữ liệu.

Khi đặt CHECK đúng chỗ và đặt tên quy tắc rõ ràng, cơ sở dữ liệu trở thành lớp bảo vệ nhất quán cho dữ liệu, kể cả khi có nhiều ứng dụng và công cụ cùng thực hiện thao tác ghi.
