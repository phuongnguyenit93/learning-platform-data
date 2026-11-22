# Ranh giới giao dịch và ý nghĩa nguyên tử của nhóm thay đổi trong SQL

Trong hệ thống thực tế, một thao tác nghiệp vụ có thể cần thay đổi **nhiều hàng và nhiều bảng**. Chuyển tiền phải vừa giảm số dư tài khoản gửi vừa tăng số dư tài khoản nhận. Tạo đơn hàng có thể đồng thời tạo đầu đơn, thêm chi tiết, trừ tồn kho và ghi nhật ký. Nếu chỉ một bước thành công rồi bước khác thất bại, cơ sở dữ liệu có thể rơi vào trạng thái **không phản ánh đúng nghiệp vụ**.

**Giao dịch SQL (*transaction*)** là ranh giới giúp nhóm các thay đổi được xử lý như một đơn vị. Thuộc tính **nguyên tử (*atomicity*)** có nghĩa: đối với những thay đổi nằm trong **cùng giao dịch hỗ trợ transaction**, sau khi giao dịch kết thúc thành công hoặc bị hủy, các thay đổi ấy **được xác nhận cùng nhau hoặc bị hoàn tác cùng nhau**. Không có trạng thái commit “chỉ một nửa nhóm thay đổi”.

Ví dụ mong muốn:

~~~text
Chuyển 250 từ tài khoản An sang tài khoản Bình

Trước:
  An    1000
  Bình   400
  Tổng  1400

Trong một transaction:
  Bước 1: An   -250
  Bước 2: Bình +250
  Bước 3: Ghi nhật ký chuyển tiền

Nếu tất cả bước hợp lệ:
  COMMIT
  An     750
  Bình   650
  Tổng  1400

Nếu một bước thất bại:
  ROLLBACK
  An    1000
  Bình   400
  Tổng  1400
~~~

Ngược lại, nếu mỗi bước tự commit riêng, thao tác có thể giảm 250 của An nhưng không tăng số dư Bình. **Đó là lỗi chia sai ranh giới giao dịch**, không phải lỗi của phép cộng trừ.

Bài học thuộc chương **Giao dịch SQL** của module **Database SQL**. Các ví dụ chính dùng **PostgreSQL**, tập trung vào ranh giới giao dịch, `BEGIN`/`COMMIT`/`ROLLBACK`, thao tác nhiều bảng, sự khác nhau giữa nguyên tử và đúng nghiệp vụ, giao dịch lồng bằng savepoint, ứng dụng Java/JDBC và những giới hạn khi có nhiều kết nối hoặc hệ thống ngoài database.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích **transaction boundary**: giao dịch bắt đầu ở đâu, kết thúc ở đâu, những statement nào cùng nằm trong đó.
2. Phân biệt **một SQL statement**, **một transaction** và **một nghiệp vụ**; biết khi nào ba phạm vi trùng nhau hoặc khác nhau.
3. Viết và đọc `BEGIN`, `COMMIT`, `ROLLBACK` trên PostgreSQL.
4. Hiểu vì sao autocommit có thể khiến các thay đổi liên quan bị commit tách rời.
5. Thiết kế một nhóm thao tác chuyển tiền/tạo đơn theo nguyên tắc **all-or-nothing**.
6. Nhận ra rằng **statement chạy không lỗi** nhưng trả **0 hàng bị thay đổi** có thể vẫn là thất bại nghiệp vụ và cần chủ động rollback.
7. Giải thích vai trò của khóa ngoại, CHECK, UNIQUE, mã yêu cầu và điều kiện cập nhật trong việc giữ tính đúng đắn.
8. Dùng `SAVEPOINT`/`ROLLBACK TO SAVEPOINT` để hoàn tác một phần trong transaction nhưng vẫn hiểu rằng **chỉ COMMIT ngoài cùng** mới xác nhận nhóm thay đổi.
9. Phân biệt **atomicity**, **consistency**, **isolation** và **durability**; không nhầm transaction với cơ chế phân quyền hay việc gửi email/thanh toán ngoài database.
10. Thiết kế transaction JDBC dùng **cùng Connection**, kiểm tra số hàng cập nhật và xử lý lỗi đúng.
11. Biết những điều cần kiểm tra khi chuyển SQL giữa PostgreSQL, MySQL, SQL Server, Oracle và SQLite.

## 2. “Ranh giới giao dịch” là gì?

Ranh giới giao dịch gồm **điểm bắt đầu**, **các thao tác thuộc cùng nhóm** và **điểm kết thúc**:

~~~text
          Ranh giới giao dịch
    ┌───────────────────────────────┐
    │ BEGIN                         │
    │                               │
    │ UPDATE bảng A                 │
    │ INSERT bảng B                 │
    │ UPDATE bảng C                 │
    │                               │
    │ COMMIT hoặc ROLLBACK          │
    └───────────────────────────────┘
~~~

- **`BEGIN`** mở một transaction rõ ràng trong PostgreSQL.
- Các statement sau đó chạy **trong cùng transaction của kết nối hiện tại**, cho tới khi kết thúc transaction.
- **`COMMIT`** yêu cầu xác nhận những thay đổi của transaction.
- **`ROLLBACK`** hủy những thay đổi chưa commit thuộc transaction.
- Sau COMMIT/ROLLBACK, các statement tiếp theo bắt đầu transaction mới theo chế độ phiên/driver.

Một transaction cũng có thể được mở và đóng ngầm theo cách DBMS hoặc client quản lý, đặc biệt khi **autocommit** bật.

### 2.1. Ví dụ đơn giản

~~~sql
BEGIN;

UPDATE tai_khoan
SET so_du = so_du - 250
WHERE id = 1;

UPDATE tai_khoan
SET so_du = so_du + 250
WHERE id = 2;

COMMIT;
~~~

`tai_khoan` ở ví dụ khái niệm này là tên bảng minh họa. Phần 5 sẽ tạo bảng `tx_tai_khoan` có dữ liệu thực hành và bổ sung các điều kiện để tránh trừ vượt số dư.

Hai UPDATE nằm giữa BEGIN và COMMIT nên cùng thuộc **một giao dịch**. Nếu dùng ROLLBACK trước COMMIT, cả hai thay đổi chưa xác nhận sẽ bị hoàn tác.

### 2.2. Một statement không nhất thiết là một transaction nhiều bước

Một lệnh INSERT có thể tạo nhiều hàng:

~~~sql
INSERT INTO bang_mau (ma, ten)
VALUES
    ('A', 'Alpha'),
    ('B', 'Beta');
~~~

Lệnh này chỉ là **một statement**. Trên các bảng transactional và DBMS phù hợp, statement có tính nguyên tử của chính nó; nếu một hàng vi phạm ràng buộc làm cả statement thất bại, thông thường không commit một nửa các hàng của statement.

Nhưng khi bạn viết ba statement riêng biệt và mỗi statement autocommit, chúng **không cùng một transaction nhiều bước**:

~~~text
INSERT bảng cha  → commit riêng
INSERT dòng con  → commit riêng
UPDATE tồn kho   → commit riêng
~~~

Vì vậy, tính nguyên tử của từng statement **không thay thế** transaction bao trùm một nghiệp vụ gồm nhiều statement.

### 2.3. Giao dịch là phạm vi lưu trữ, nghiệp vụ là phạm vi ý nghĩa

Một nghiệp vụ “tạo đơn” có thể gồm:

- Ghi bản ghi đơn.
- Ghi các dòng đơn.
- Trừ hàng tồn kho.
- Ghi nhật ký thay đổi.
- Gửi email xác nhận.
- Gọi dịch vụ thanh toán.

Những thay đổi trong **cùng một database transaction** được quản lý theo ACID của DBMS. Nhưng việc gửi email hay gọi API thanh toán thuộc **hệ thống khác**, không tự bị ROLLBACK chỉ vì transaction database bị hủy.

Do đó, đừng suy ra rằng “tôi đã có BEGIN/COMMIT, nên mọi việc trong hàm Java đều nguyên tử”. Ta cần xác định **tài nguyên nào thực sự nằm trong transaction**.

## 3. ACID và trọng tâm Atomicity

Một transaction thường được mô tả bằng bốn thuộc tính ACID:

| Thuộc tính | Câu hỏi chính | Ví dụ chuyển tiền |
|---|---|---|
| **Atomicity – Nguyên tử** | Các thay đổi có cùng commit hoặc cùng rollback không? | Không để chỉ trừ An mà quên cộng Bình |
| **Consistency – Nhất quán** | Các ràng buộc và bất biến được bảo vệ thế nào? | Không cho số dư âm theo CHECK; tổng tiền của nghiệp vụ cần được kiểm tra |
| **Isolation – Cô lập** | Transaction đồng thời quan sát và ảnh hưởng nhau ra sao? | Hai lệnh chuyển tiền cạnh tranh cùng một tài khoản |
| **Durability – Bền vững** | Sau khi commit thành công, DBMS bảo đảm lưu giữ thế nào? | Giao dịch đã commit không biến mất khi session kết thúc bình thường |

**Atomicity không đồng nghĩa Consistency.** Database có thể commit **cả hai câu UPDATE sai** nếu chúng hợp lệ về mặt SQL và ràng buộc. Ví dụ:

~~~sql
BEGIN;

UPDATE tai_khoan SET so_du = so_du - 250 WHERE id = 1;
UPDATE tai_khoan SET so_du = so_du + 200 WHERE id = 2;

COMMIT;
~~~

Hai UPDATE có thể được commit cùng nhau, tức **nguyên tử**, nhưng chênh lệch 50 giữa tiền trừ và tiền cộng có thể vi phạm quy tắc chuyển tiền. Transaction không tự biết khoản chuyển phải cân bằng trừ khi bạn lập trình và ràng buộc đúng.

Tương tự, một transaction có thể commit đúng số tiền vào **tài khoản nhận sai** nếu dùng nhầm ID mà các ràng buộc vẫn cho phép. **Nguyên tử bảo vệ nhóm thay đổi**, không tự xác minh nghiệp vụ.

### 3.1. Atomicity áp dụng cho những gì?

Trên PostgreSQL với các bảng transactional thông thường, một transaction có thể bao gồm:

- INSERT, UPDATE, DELETE trên nhiều bảng.
- Các thay đổi quan hệ được DBMS quản lý.
- Một số thao tác DDL được PostgreSQL cho phép trong transaction.
- Những thay đổi qua trigger chạy trong giao dịch phù hợp.

Nhưng không nên coi các việc sau tự được hoàn tác hoàn toàn chỉ bằng ROLLBACK:

- Giá trị sequence đã cấp bằng `nextval` hoặc identity.
- Email đã gửi, thông báo push đã phát.
- File đã ghi ngoài cơ sở dữ liệu.
- Lời gọi đến hệ thống thanh toán hoặc API ngoài.
- Tác động trên một kết nối/database/engine không thuộc cùng transaction.

Các ngoại lệ và chi tiết phụ thuộc DBMS, loại đối tượng và kiến trúc hệ thống.

## 4. Autocommit: vì sao nhiều statement có thể thành nhiều giao dịch?

Trong nhiều SQL client và JDBC, chế độ **autocommit** thường làm mỗi statement thành công được xác nhận theo ranh giới riêng nếu không mở transaction rõ ràng.

Ví dụ nguy hiểm:

~~~text
autocommit = ON

UPDATE An -250      → statement thành công, commit
UPDATE Bình +250    → bị lỗi kết nối, không thực hiện

Kết quả: chỉ An bị trừ tiền.
~~~

Database không hề phá vỡ atomicity: **đã có hai giao dịch riêng**. Lỗi nằm ở việc ứng dụng đặt ranh giới khác với nghiệp vụ.

### 4.1. BEGIN gom các statement lại

~~~sql
BEGIN;

UPDATE tx_tai_khoan
SET so_du = so_du - 250
WHERE id = 1;

UPDATE tx_tai_khoan
SET so_du = so_du + 250
WHERE id = 2;

COMMIT;
~~~

Trong PostgreSQL, BEGIN tạo transaction rõ ràng, các statement ở giữa không được commit độc lập. Nếu một bước thất bại và bạn ROLLBACK, những thay đổi trước đó trong transaction cũng được hủy.

**Lưu ý:** đoạn ví dụ này chưa kiểm tra số dư và số hàng bị tác động; phần thực hành sẽ bổ sung các điều kiện cần để dùng đúng nghiệp vụ.

### 4.2. Khi nào một transaction tự kết thúc?

Có những tình huống:

- Client gửi `COMMIT` hoặc `ROLLBACK`.
- Một framework quản lý transaction kết thúc khối xử lý.
- Một kết nối đóng bất thường khi còn transaction chưa commit: PostgreSQL sẽ hủy các thay đổi chưa xác nhận của transaction đó.
- Một statement lỗi làm PostgreSQL đánh dấu transaction đang mở là aborted; phải rollback hoặc khôi phục bằng savepoint trước khi tiếp tục.

Không nên dựa vào ngắt kết nối để thay `ROLLBACK`. Nếu mất mạng lúc COMMIT đã được gửi, **ứng dụng có thể không biết chắc COMMIT có thành công hay không**; đó là bài toán xử lý kết quả không xác định và retry an toàn.

### 4.3. SQL client có thể quản lý transaction theo cách riêng

Một trình quản lý cơ sở dữ liệu có thể có nút **Auto-commit**, **Commit**, **Rollback**, hoặc tự bọc script trong transaction. Vì vậy, khi thực hành:

1. Xác định client đang autocommit hay manual commit.
2. Không trộn một transaction đang mở do client với `BEGIN` khác nếu không hiểu hành vi.
3. Quan sát cách client xử lý lỗi.
4. Chạy ví dụ trong database thử nghiệm, tránh bảng sản xuất.

Trong PostgreSQL, `BEGIN` khi transaction đã mở **không tạo một transaction độc lập lồng bên trong**; PostgreSQL có thể chỉ cảnh báo đang trong transaction. Muốn điểm quay lại nội bộ, dùng **SAVEPOINT**.

## 5. Chuẩn bị bộ dữ liệu thực hành PostgreSQL

Các ví dụ tạo ba tài khoản, nhật ký giao dịch, sản phẩm và đơn hàng. Toàn bộ bảng dùng tiền tố `tx_` và đều là **TEMP TABLE** để giới hạn trong phiên kết nối thực hành.

**Chạy trong một database thử nghiệm trên cùng một connection PostgreSQL.** Nếu mở connection khác, các bảng TEMP này không tự xuất hiện. Sau khi tạo dữ liệu, những ví dụ ghi dữ liệu đều được hướng dẫn dùng ROLLBACK để giữ dữ liệu gốc.

### 5.1. Bảng tài khoản

~~~sql
CREATE TEMP TABLE tx_tai_khoan (
    id INTEGER PRIMARY KEY,
    chu_tai_khoan TEXT NOT NULL,
    so_du NUMERIC(14,2) NOT NULL CHECK (so_du >= 0),
    trang_thai TEXT NOT NULL DEFAULT 'ACTIVE'
        CHECK (trang_thai IN ('ACTIVE', 'BLOCKED'))
);

INSERT INTO tx_tai_khoan
    (id, chu_tai_khoan, so_du, trang_thai)
VALUES
    (1, 'An',   1000.00, 'ACTIVE'),
    (2, 'Bình',  400.00, 'ACTIVE'),
    (3, 'Chi',   150.00, 'ACTIVE');
~~~

Tổng số dư ban đầu:

\[
1000 + 400 + 150 = 1550
\]

`CHECK (so_du >= 0)` ngăn hàng bị ghi số dư âm. Tuy nhiên, nó **không ngăn** một transaction chuyển tiền đến sai tài khoản hoặc ghi nhật ký sai nếu mọi dữ liệu vẫn thỏa CHECK.

### 5.2. Bảng nhật ký chuyển động số dư

~~~sql
CREATE TEMP TABLE tx_bien_dong (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    ma_giao_dich TEXT NOT NULL,
    tai_khoan_id INTEGER NOT NULL
        REFERENCES tx_tai_khoan(id),
    loai TEXT NOT NULL
        CHECK (loai IN ('DEBIT', 'CREDIT')),
    so_tien NUMERIC(14,2) NOT NULL
        CHECK (so_tien > 0),
    ghi_luc TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (ma_giao_dich, tai_khoan_id, loai)
);
~~~

Mỗi lần chuyển tiền trong ví dụ sẽ ghi:

- Một dòng `DEBIT` cho tài khoản gửi.
- Một dòng `CREDIT` cho tài khoản nhận.

`id` là khóa kỹ thuật tự sinh; `ma_giao_dich` nhận diện một lần chuyển tiền. Ràng buộc UNIQUE trên ba cột ngăn ghi trùng cùng loại chuyển động của cùng tài khoản trong cùng mã giao dịch, nhưng **chưa đủ để chứng minh toàn bộ giao dịch cân bằng**.

### 5.3. Bảng yêu cầu chuyển tiền

~~~sql
CREATE TEMP TABLE tx_chuyen_tien (
    ma_giao_dich TEXT PRIMARY KEY,
    tai_khoan_gui INTEGER NOT NULL
        REFERENCES tx_tai_khoan(id),
    tai_khoan_nhan INTEGER NOT NULL
        REFERENCES tx_tai_khoan(id),
    so_tien NUMERIC(14,2) NOT NULL CHECK (so_tien > 0),
    tao_luc TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (tai_khoan_gui <> tai_khoan_nhan)
);
~~~

`ma_giao_dich` duy nhất giúp nhận diện một yêu cầu khi thử lại, nhưng hệ thống thực còn phải kiểm tra **yêu cầu trùng mã có cùng nội dung hay không**, transaction trước đã hoàn tất chưa và có cần phản hồi lại kết quả cũ.

### 5.4. Bảng hàng tồn và đơn hàng

~~~sql
CREATE TEMP TABLE tx_san_pham (
    id INTEGER PRIMARY KEY,
    ten TEXT NOT NULL,
    ton_kho INTEGER NOT NULL CHECK (ton_kho >= 0),
    don_gia NUMERIC(12,2) NOT NULL CHECK (don_gia >= 0)
);

INSERT INTO tx_san_pham
    (id, ten, ton_kho, don_gia)
VALUES
    (10, 'Sách SQL', 10, 100.00),
    (20, 'Bút',       4,  20.00);

CREATE TEMP TABLE tx_don_hang (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    ma_don TEXT NOT NULL UNIQUE,
    khach_hang TEXT NOT NULL,
    tao_luc TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TEMP TABLE tx_dong_don (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    don_hang_id BIGINT NOT NULL
        REFERENCES tx_don_hang(id),
    san_pham_id INTEGER NOT NULL
        REFERENCES tx_san_pham(id),
    so_luong INTEGER NOT NULL CHECK (so_luong > 0),
    don_gia NUMERIC(12,2) NOT NULL CHECK (don_gia >= 0),
    UNIQUE (don_hang_id, san_pham_id)
);
~~~

Mô hình:

~~~text
tx_tai_khoan (1) ─── (N) tx_bien_dong
        │
        └── tx_chuyen_tien (tài khoản gửi / nhận)

tx_don_hang (1) ─── (N) tx_dong_don (N) ─── (1) tx_san_pham
                                               │
                                               └── ton_kho
~~~

Các bảng tạm giúp thực hành an toàn nhưng không làm giao dịch “giả”. Các UPDATE, INSERT, DELETE bên trong transaction vẫn thay đổi dữ liệu thật của phiên thử nghiệm cho tới khi COMMIT hoặc ROLLBACK.

### 5.5. Trạng thái gốc để đối chiếu

~~~sql
SELECT id, chu_tai_khoan, so_du, trang_thai
FROM tx_tai_khoan
ORDER BY id;

SELECT id, ten, ton_kho
FROM tx_san_pham
ORDER BY id;

SELECT COUNT(*) AS so_don FROM tx_don_hang;
SELECT COUNT(*) AS so_bien_dong FROM tx_bien_dong;
~~~

Kỳ vọng:

| Tài khoản | Số dư |
|---|---:|
| An (1) | 1000.00 |
| Bình (2) | 400.00 |
| Chi (3) | 150.00 |

Tồn kho Sách SQL là 10, Bút là 4. Chưa có đơn hàng hoặc dòng biến động.

## 6. BEGIN, COMMIT và ROLLBACK từng bước

### 6.1. Bắt đầu, cập nhật, đọc trong transaction, rồi hoàn tác

~~~sql
BEGIN;

UPDATE tx_tai_khoan
SET so_du = so_du - 100
WHERE id = 1;

SELECT id, chu_tai_khoan, so_du
FROM tx_tai_khoan
WHERE id = 1;

ROLLBACK;

SELECT id, chu_tai_khoan, so_du
FROM tx_tai_khoan
WHERE id = 1;
~~~

Diễn biến trong cùng kết nối:

| Thời điểm | Số dư An |
|---|---:|
| Trước BEGIN | 1000 |
| Sau UPDATE, trước ROLLBACK | 900 |
| Sau ROLLBACK | 1000 |

Trong transaction, kết nối của bạn có thể **đọc thấy thay đổi do chính transaction tạo ra** dù chưa commit. Đây là hành vi quan trọng: `SELECT` sau UPDATE trong cùng kết nối không có nghĩa hàng đã được người khác nhìn thấy.

### 6.2. Khi dùng COMMIT thay ROLLBACK

Nếu thay `ROLLBACK` bằng `COMMIT` ở ví dụ trên, số dư 900 được xác nhận. Nhưng đó là thao tác chỉ trừ tiền ở An; nó có thể **sai nghiệp vụ** dù COMMIT thành công.

Trong bài, bạn nên dùng ROLLBACK ở những tình huống chỉ kiểm tra cơ chế, để các phần sau tiếp tục có dữ liệu gốc.

### 6.3. ROLLBACK không quay ngược commit cũ

~~~text
BEGIN → UPDATE → COMMIT → ROLLBACK
~~~

Sau `COMMIT`, transaction cũ đã kết thúc. Một `ROLLBACK` về sau **không thể hoàn tác** các cập nhật đã commit của transaction ấy.

Muốn sửa dữ liệu đã commit, cần một thao tác bù trừ hợp lệ hoặc khôi phục dữ liệu theo chính sách backup/recovery, chứ không thể ra lệnh rollback “về một giao dịch đã đóng”.

## 7. Chuyển tiền: nhóm thay đổi phải cùng nằm trong transaction

Yêu cầu: chuyển **250.00** từ An (ID 1) sang Bình (ID 2), đồng thời ghi thông tin yêu cầu và hai dòng biến động.

### 7.1. Xác định trước các bất biến cần giữ

Với ví dụ cơ bản:

- Tài khoản gửi và nhận **phải tồn tại**.
- Hai tài khoản khác nhau.
- Cả hai đang ACTIVE.
- Số tiền phải **lớn hơn 0**.
- Số dư An phải **đủ tiền**.
- Giảm ở An và tăng ở Bình phải **cùng số tiền**.
- Ghi đủ một yêu cầu và hai dòng nhật ký.
- Các thao tác hoặc **được xác nhận cùng nhau**, hoặc **không có thay đổi**.

Các CHECK và FOREIGN KEY giúp một số điều kiện; các điều kiện còn lại cần logic SQL/ứng dụng.

### 7.2. Giao dịch mẫu có nhiều statement

~~~sql
BEGIN;

-- 1. Tạo mã yêu cầu; nếu trùng sẽ gặp UNIQUE.
INSERT INTO tx_chuyen_tien
    (ma_giao_dich, tai_khoan_gui, tai_khoan_nhan, so_tien)
VALUES ('CT-DEMO-01', 1, 2, 250.00);

-- 2. Trừ người gửi nếu tài khoản ACTIVE và còn đủ tiền.
UPDATE tx_tai_khoan
SET so_du = so_du - 250.00
WHERE id = 1
  AND trang_thai = 'ACTIVE'
  AND so_du >= 250.00
RETURNING id, so_du;

-- 3. Cộng người nhận nếu tài khoản ACTIVE.
UPDATE tx_tai_khoan
SET so_du = so_du + 250.00
WHERE id = 2
  AND trang_thai = 'ACTIVE'
RETURNING id, so_du;

-- 4. Ghi đủ hai chuyển động.
INSERT INTO tx_bien_dong
    (ma_giao_dich, tai_khoan_id, loai, so_tien)
VALUES
    ('CT-DEMO-01', 1, 'DEBIT', 250.00),
    ('CT-DEMO-01', 2, 'CREDIT', 250.00)
RETURNING id, ma_giao_dich, tai_khoan_id, loai, so_tien;

-- 5. Chỉ sau khi kiểm tra cả hai UPDATE đã tác động
--    chính xác một hàng, INSERT đã ghi đúng hai dòng
--    và các điều kiện nghiệp vụ đều đạt thì mới COMMIT.
--    Bài tập mô phỏng nên hoàn tác:
ROLLBACK;
~~~

**Quan trọng:** đây là một script minh họa trình tự với con số hợp lệ trên dữ liệu mẫu, **không phải thủ tục SQL tự động dừng khi UPDATE trả 0 hàng**. Trong hệ thống thật, ứng dụng hoặc stored procedure phải kiểm tra số hàng được UPDATE trước khi cho phép bước tiếp theo và COMMIT.

### 7.3. Kết quả mong đợi trước ROLLBACK

Nếu bộ dữ liệu chưa thay đổi:

- INSERT yêu cầu: 1 hàng.
- UPDATE An: 1 hàng, số dư 750.
- UPDATE Bình: 1 hàng, số dư 650.
- INSERT nhật ký: 2 hàng, một DEBIT và một CREDIT.
- Tổng số dư ba tài khoản vẫn là **1550** (Chi vẫn 150).

Kiểm tra có thể đặt trước ROLLBACK:

~~~sql
SELECT id, chu_tai_khoan, so_du
FROM tx_tai_khoan
ORDER BY id;

SELECT ma_giao_dich, tai_khoan_id, loai, so_tien
FROM tx_bien_dong
WHERE ma_giao_dich = 'CT-DEMO-01'
ORDER BY tai_khoan_id;
~~~

Sau ROLLBACK, số dư trở về 1000 và 400; các hàng `tx_chuyen_tien` và `tx_bien_dong` tạo trong transaction cũng không còn. Tuy nhiên, sequence của `tx_bien_dong.id` có thể đã dùng một vài số và **không hoàn tác giá trị đã cấp**.

### 7.4. Vì sao transaction nên bao trùm cả nhật ký?

Nếu chỉ hai UPDATE nằm trong transaction nhưng nhật ký được ghi sau COMMIT bằng một statement khác, có thể xảy ra trạng thái tiền đã chuyển nhưng chưa ghi đủ lịch sử. Ngược lại, ghi nhật ký trước khi chuyển tiền và commit riêng có thể tạo lịch sử không tương ứng.

Khi nhật ký là dữ liệu quan hệ phải nhất quán với số dư, nên đưa nó vào **cùng transaction**. Nếu nhật ký là sự kiện gửi ra hệ thống bên ngoài, cần thiết kế bảo đảm phát sự kiện riêng (ví dụ transactional outbox), được bàn ở phần sau.

## 8. Điều kiện không đạt không tự gây lỗi: UPDATE trả 0 hàng

Đây là điểm dễ bỏ sót nhất khi sử dụng transaction.

Giả sử An chỉ có **1000**, nhưng ứng dụng yêu cầu chuyển **2000**. UPDATE có điều kiện:

~~~sql
BEGIN;

UPDATE tx_tai_khoan
SET so_du = so_du - 2000.00
WHERE id = 1
  AND so_du >= 2000.00
RETURNING id, so_du;

ROLLBACK;
~~~

Kết quả: **0 hàng được cập nhật**, vì `so_du >= 2000` là FALSE. PostgreSQL không nhất thiết báo lỗi: UPDATE khớp 0 hàng vẫn là một câu lệnh hợp lệ.

### 8.1. Nguy cơ commit một phần nếu bỏ qua 0 hàng

Quy trình sai:

~~~sql
BEGIN;

UPDATE tx_tai_khoan
SET so_du = so_du - 2000.00
WHERE id = 1 AND so_du >= 2000.00;
-- 0 hàng, không lỗi SQL.

UPDATE tx_tai_khoan
SET so_du = so_du + 2000.00
WHERE id = 2;
-- 1 hàng, Bình được cộng 2000.

COMMIT;
-- Database có thể commit, dù nghiệp vụ chuyển tiền sai.
~~~

**Không chạy đoạn sai này trên dữ liệu cần giữ.** Nó cho thấy: **atomicity chỉ bảo đảm tất cả thay đổi đã thực sự được thực hiện trong transaction cùng commit hoặc rollback; nó không tự tạo thay đổi bị bỏ qua**.

Ở quy trình sai, statement trừ tiền **không thay đổi hàng nào**, còn statement cộng tiền thay đổi một hàng. COMMIT xác nhận toàn bộ những thay đổi hiện có — tức là chỉ cộng Bình 2000.

### 8.2. Cách xử lý đúng

Sau UPDATE có điều kiện, phải kiểm tra:

~~~text
Số hàng trừ người gửi = 1?
    Không → ROLLBACK và báo không đủ tiền / sai ID.
    Có   → tiếp tục.

Số hàng cộng người nhận = 1?
    Không → ROLLBACK và báo tài khoản nhận không hợp lệ.
    Có   → ghi nhật ký, kiểm tra đủ dòng, COMMIT.
~~~

Trong ứng dụng JDBC, `executeUpdate()` trả số hàng bị ảnh hưởng theo API/driver, hoặc PostgreSQL `RETURNING` cho biết hàng cụ thể. Với PL/pgSQL, có thể dùng `GET DIAGNOSTICS ... = ROW_COUNT` hoặc `FOUND` theo cách phù hợp.

### 8.3. Ràng buộc CHECK có thể chặn số dư âm, nhưng chưa đủ

Nếu viết:

~~~sql
UPDATE tx_tai_khoan
SET so_du = so_du - 2000.00
WHERE id = 1;
~~~

với dữ liệu mẫu, CHECK `so_du >= 0` sẽ từ chối số dư âm. Nhưng chỉ nhờ lỗi CHECK để kiểm tra điều kiện “đủ tiền” không phải thiết kế toàn diện. Điều kiện `WHERE so_du >= so_tien` làm rõ mục đích; CHECK là tuyến bảo vệ cấp database.

Cũng vậy, CHECK không đảm bảo tài khoản nhận được cộng đúng số tiền. Cần ràng buộc và logic nghiệp vụ đầy đủ.

## 9. Lỗi statement làm transaction PostgreSQL ra sao?

Trong transaction PostgreSQL, khi một statement gây lỗi SQL thông thường mà không có savepoint xử lý, transaction bị đánh dấu **aborted**. Những statement sau đó sẽ không thực thi như bình thường cho tới khi ROLLBACK.

### 9.1. Ví dụ cố ý vi phạm CHECK

~~~sql
BEGIN;

UPDATE tx_tai_khoan
SET so_du = so_du - 100.00
WHERE id = 1;

-- Vi phạm CHECK nếu An còn 900.
UPDATE tx_tai_khoan
SET so_du = -1
WHERE id = 2;

-- Transaction lúc này đã lỗi.
-- PostgreSQL yêu cầu kết thúc bằng ROLLBACK:
ROLLBACK;
~~~

Vì statement thứ hai cố ghi số dư âm, PostgreSQL báo lỗi ràng buộc CHECK. Khi ROLLBACK, thay đổi trừ 100 ở An trước đó cũng bị hoàn tác.

### 9.2. Lỗi SQL khác 0 hàng

So sánh:

| Trường hợp | Có nhất thiết phát sinh lỗi PostgreSQL? | Quyết định nghiệp vụ |
|---|---|---|
| UPDATE khớp 0 hàng | Không | Thường phải kiểm tra và rollback nếu cần đúng 1 |
| UPDATE khớp 1 hàng, giá trị hợp lệ | Không | Có thể tiếp tục nếu đúng mục tiêu |
| INSERT vi phạm FOREIGN KEY | Có | Transaction cần rollback hoặc xử lý savepoint |
| UPDATE vi phạm CHECK | Có | Transaction cần rollback hoặc xử lý savepoint |
| INSERT trùng UNIQUE | Có, nếu không có nhánh xử lý xung đột | Quyết định retry/idempotency |
| Lệnh SQL sai cú pháp | Có | Sửa lỗi, kết thúc transaction lỗi |

Do đó, ứng dụng phải xử lý **hai lớp thất bại**:

1. Thất bại kỹ thuật: exception, lỗi ràng buộc, deadlock, timeout.
2. Thất bại nghiệp vụ: 0 hàng, sai số lượng dòng, thiếu tài khoản, trạng thái không cho phép, số tiền không cân bằng.

### 9.3. Sau lỗi cần ROLLBACK rõ ràng

Nếu bạn chạy:

~~~sql
BEGIN;
UPDATE ...;
INSERT ...;   -- lỗi
SELECT ...;   -- có thể nhận thông báo transaction bị aborted
COMMIT;       -- không thể commit thành công như một transaction hợp lệ
~~~

thì cách phục hồi thông thường là `ROLLBACK` và bắt đầu một transaction mới. Không tiếp tục thực thi các bước kinh doanh như thể INSERT lỗi chưa từng xảy ra.

Trong chương trình Java, dùng khối `try/catch` gọi rollback khi statement hoặc kiểm tra nghiệp vụ thất bại.

## 10. Tạo đơn hàng và trừ tồn kho: ranh giới xuyên nhiều bảng

Nghiệp vụ: khách An mua **2 Sách SQL**, cần:

1. Tạo đơn cha.
2. Tạo dòng đơn.
3. Trừ 2 đơn vị tồn kho Sách.
4. Chỉ COMMIT nếu cả ba bước hoàn tất.

### 10.1. Vì sao ba thao tác phải nằm cùng transaction?

Nếu chỉ tạo đơn + dòng rồi commit mà chưa trừ tồn kho, có thể bán vượt số lượng tồn. Nếu trừ tồn trước rồi đơn bị lỗi, kho bị mất hàng không có đơn tương ứng.

Ranh giới đúng:

~~~text
BEGIN
    ├── INSERT tx_don_hang
    ├── INSERT tx_dong_don
    ├── UPDATE tx_san_pham.ton_kho
    ├── kiểm tra số dòng / điều kiện nghiệp vụ
    └── COMMIT hoặc ROLLBACK
~~~

### 10.2. Tạo cha và dòng con bằng RETURNING trong một statement

PostgreSQL có thể truyền ID đơn vừa sinh qua data-modifying CTE:

~~~sql
BEGIN;

WITH don_moi AS (
    INSERT INTO tx_don_hang (ma_don, khach_hang)
    VALUES ('DON-DEMO-01', 'An')
    RETURNING id
)
INSERT INTO tx_dong_don
    (don_hang_id, san_pham_id, so_luong, don_gia)
SELECT
    d.id,
    sp.id,
    2,
    sp.don_gia
FROM don_moi AS d
JOIN tx_san_pham AS sp
    ON sp.id = 10
RETURNING
    don_hang_id,
    san_pham_id,
    so_luong,
    don_gia;

-- Kiểm tra INSERT đã trả đúng một dòng con trước khi tiếp tục.

UPDATE tx_san_pham
SET ton_kho = ton_kho - 2
WHERE id = 10
  AND ton_kho >= 2
RETURNING id, ton_kho;

-- Nếu cả INSERT con và UPDATE kho đều tác động đúng một hàng
-- cùng các điều kiện nghiệp vụ đều đạt, ứng dụng mới COMMIT.
-- Ví dụ này hoàn tác để giữ dữ liệu thử nghiệm:
ROLLBACK;
~~~

Trên dữ liệu ban đầu, sau UPDATE tạm, tồn Sách từ **10 xuống 8**. Sau ROLLBACK, đơn mới và dòng đơn biến mất; tồn Sách trở lại 10.

### 10.3. Nếu UPDATE tồn kho trả 0 hàng?

Điều kiện:

~~~sql
WHERE id = 10 AND ton_kho >= 2
~~~

có thể trả 0 hàng nếu sản phẩm không tồn tại, bị đổi trạng thái hoặc không đủ tồn. SQL không nhất thiết báo lỗi. **Không được COMMIT đơn và dòng đơn khi việc trừ tồn kho không thành công** nếu nghiệp vụ yêu cầu xuất kho đồng thời.

Đây cũng là ví dụ vì sao transaction **chưa đủ**: ứng dụng phải kiểm tra số hàng UPDATE, rồi rollback khi không đạt.

### 10.4. Trừ tồn theo số lượng hiện tại, không dựa trên SELECT cũ

Cách kém an toàn:

~~~text
SELECT ton_kho = 10
Ứng dụng tự tính: 10 - 2 = 8
UPDATE tx_san_pham SET ton_kho = 8 WHERE id = 10
~~~

Nếu một transaction khác cũng trừ hàng ở giữa, việc ghi `8` theo giá trị đã đọc cũ có thể ghi đè cập nhật của người khác.

Cách tốt hơn cho thao tác trừ đơn giản:

~~~sql
UPDATE tx_san_pham
SET ton_kho = ton_kho - 2
WHERE id = 10
  AND ton_kho >= 2
RETURNING ton_kho;
~~~

Đây là một cập nhật tương đối có điều kiện. PostgreSQL dùng khóa hàng và đánh giá điều kiện theo cơ chế MVCC/cô lập phù hợp, giúp tránh nhiều trường hợp ghi đè mất cập nhật khi các transaction cùng trừ tồn. Tuy nhiên, cần xử lý chờ khóa, deadlock, lỗi serialization và các bất biến khác của hệ thống.

### 10.5. Giá tiền và số lượng con cũng là nghiệp vụ

Một transaction có thể commit đơn có **giá sai** hoặc **thiếu dòng sản phẩm** nếu ứng dụng không kiểm tra. Vì thế, trước COMMIT, phải xác định:

- Đã tạo đúng một đơn.
- Đã tạo đủ số dòng và số lượng theo request.
- Sản phẩm đúng ID.
- Trừ tồn đúng số lượng.
- Giá đã lưu phản ánh quy tắc được duyệt.
- Không có vi phạm UNIQUE/FK/CHECK hoặc quyền thao tác.

Atomicity giúp các bước được xác nhận cùng nhau, còn việc **đó có phải tập bước đúng hay không** là trách nhiệm logic nghiệp vụ.

## 11. Một hay nhiều statement: ranh giới không đồng nghĩa với số dòng SQL

Có các cách tổ chức khác nhau:

### 11.1. Một statement duy nhất

~~~sql
UPDATE tx_tai_khoan
SET so_du = so_du + 100
WHERE id = 2;
~~~

Đây là một statement tác động một hàng. Nếu chỉ cần một thay đổi đơn giản, transaction ngầm của DBMS thường đủ.

### 11.2. Nhiều statement trong một transaction

~~~sql
BEGIN;
UPDATE ...;
INSERT ...;
DELETE ...;
COMMIT;
~~~

Ba statement được xác nhận chung nếu transaction hoàn tất. Đây là mẫu cho một nghiệp vụ gồm các ghi chép liên quan.

### 11.3. Nhiều statement nhưng ba lần commit

~~~text
BEGIN → UPDATE A → COMMIT
BEGIN → INSERT B → COMMIT
BEGIN → UPDATE C → COMMIT
~~~

Có ba transaction, không phải một. Nếu bước C lỗi, hai thay đổi A và B đã commit **không bị ROLLBACK của C hoàn tác**.

### 11.4. Một transaction quá lớn cũng không luôn tốt

Ngược lại, không nên gom cả một đợt xử lý kéo dài hàng giờ, giao diện chờ người dùng và nhiều API bên ngoài vào một transaction DB quá lớn.

Transaction giữ tài nguyên, phiên bản hàng, khóa và bộ nhớ liên quan tùy DBMS. Một transaction quá dài có thể làm tăng chờ khóa, bloat, áp lực WAL hoặc nguy cơ deadlock.

**Ranh giới tốt** thường là phạm vi nhỏ nhất đủ để duy trì các bất biến cần nguyên tử, chứ không phải toàn bộ quy trình nghiệp vụ từ lúc mở màn hình đến khi gửi thông báo.

## 12. SAVEPOINT: hoàn tác một phần, không phải transaction độc lập

PostgreSQL không hỗ trợ nested transaction độc lập chỉ bằng cách viết nhiều `BEGIN`. Khi muốn có **mốc quay lại** bên trong transaction, dùng `SAVEPOINT`.

### 12.1. Ví dụ savepoint

~~~sql
BEGIN;

UPDATE tx_tai_khoan
SET so_du = so_du + 50
WHERE id = 3;
-- Chi: 150 → 200.

SAVEPOINT truoc_thu_nghiem;

UPDATE tx_tai_khoan
SET so_du = so_du + 70
WHERE id = 3;
-- Chi: 200 → 270.

ROLLBACK TO SAVEPOINT truoc_thu_nghiem;
-- Chi trở về 200 trong transaction.

SELECT id, so_du
FROM tx_tai_khoan
WHERE id = 3;

-- Bài tập chỉ quan sát:
ROLLBACK;
~~~

Diễn biến:

| Bước | Số dư Chi được thấy trong connection |
|---|---:|
| Ban đầu | 150 |
| Sau UPDATE +50 | 200 |
| Sau SAVEPOINT và UPDATE +70 | 270 |
| Sau ROLLBACK TO SAVEPOINT | 200 |
| Sau ROLLBACK ngoài cùng | 150 |

### 12.2. RELEASE SAVEPOINT không phải COMMIT

~~~sql
BEGIN;
SAVEPOINT sp1;
UPDATE tx_tai_khoan SET so_du = so_du + 10 WHERE id = 3;
RELEASE SAVEPOINT sp1;
ROLLBACK;
~~~

Sau `RELEASE SAVEPOINT`, thay đổi +10 **chưa được commit độc lập**. Khi `ROLLBACK` transaction ngoài cùng, thay đổi vẫn bị hủy.

`RELEASE SAVEPOINT` chỉ giải phóng mốc quay lại; **COMMIT của transaction ngoài cùng** mới xác nhận phần thay đổi còn lại.

### 12.3. Khi nào rollback một phần hợp lý?

Ví dụ nhập dữ liệu gồm nhiều dòng bổ sung, một dòng tùy chọn có thể bỏ qua nhưng cả nghiệp vụ vẫn hợp lệ. Có thể đặt SAVEPOINT trước thao tác tùy chọn và quay lại nếu lỗi.

Nhưng nếu nghiệp vụ **phải chuyển đủ 250 từ An sang Bình**, không được rollback bước cộng Bình rồi commit bước trừ An. Savepoint **không cho phép phá vỡ bất biến** mà nghiệp vụ yêu cầu.

### 12.4. Xử lý lỗi SQL với SAVEPOINT

Trong PostgreSQL, khi statement lỗi trong transaction, bạn có thể quay lại savepoint đã tạo trước statement lỗi:

~~~sql
BEGIN;

SAVEPOINT truoc_lenh;

-- Thử một statement có nguy cơ lỗi.
UPDATE tx_tai_khoan
SET so_du = -10
WHERE id = 1;
-- CHECK thất bại.

ROLLBACK TO SAVEPOINT truoc_lenh;

-- Sau khi quay về savepoint, transaction có thể tiếp tục
-- với các thao tác hợp lệ khác.

ROLLBACK;
~~~

Đoạn này cố tình làm CHECK thất bại. Nếu SQL client dừng script ở lỗi đầu tiên, bạn có thể cần chạy riêng `ROLLBACK TO SAVEPOINT` trong cùng connection. Với thao tác nghiệp vụ phải hoàn thành toàn bộ, thường nên ROLLBACK cả transaction thay vì bỏ qua lỗi.

## 13. Phạm vi transaction gắn với Connection

Trong phần lớn ứng dụng truy cập một RDBMS qua JDBC, transaction thuộc về **một connection/session**, không tự truyền sang connection khác.

### 13.1. Hai connection không đồng nghĩa một transaction

~~~text
Connection A:
    BEGIN
    UPDATE An -250        (chưa commit)

Connection B:
    UPDATE Bình +250
    COMMIT                (commit riêng)

Connection A:
    ROLLBACK

Kết quả:
    An giữ nguyên.
    Bình đã +250.
~~~

Nếu connection B có thể thực hiện cập nhật độc lập, thao tác trên B không bị rollback cùng A. Dù hai connection kết nối cùng PostgreSQL database, chúng thường vẫn là **hai transaction khác nhau**.

### 13.2. Không thể “gửi thêm statement” vào transaction đã COMMIT

Sau COMMIT, transaction cũ đóng. Nếu ứng dụng sau đó gọi repository khác mà không có một transaction bao trùm, repository ấy không thể mở rộng transaction cũ.

Đây là lý do trong các hệ thống Java nhiều tầng, **service nghiệp vụ** thường là nơi đặt ranh giới transaction, còn các repository thực thi SQL trong ngữ cảnh ấy.

### 13.3. Cùng Connection chưa đủ nếu bật auto-commit

Nếu dùng cùng connection nhưng `autoCommit = true` và không tắt hoặc không mở transaction theo API, các statement có thể vẫn commit riêng.

Điều kiện cần là:

1. Cùng connection/transaction manager đúng ngữ cảnh.
2. Một ranh giới transaction rõ ràng bao phủ các statement.
3. Kiểm tra kết quả từng bước.
4. Commit hoặc rollback đúng lúc.

## 14. JDBC: transaction đa bước trên một Connection

Ví dụ Java 17+ dùng PostgreSQL JDBC driver. Hàm minh họa chuyển tiền 250 từ tài khoản gửi sang tài khoản nhận, ghi đầu giao dịch và hai biến động, tất cả trong một transaction.

Để tránh gây xung đột ranh giới giao dịch, phương thức dưới giả định **được phép quản lý transaction của Connection** và Connection ban đầu đang ở chế độ auto-commit. Trong ứng dụng có Spring/JTA/transaction manager, hãy để transaction manager quản lý thay vì tự tắt/bật auto-commit lồng lên giao dịch của framework.

### 14.1. Phương thức chuyển tiền

~~~java
import java.math.BigDecimal;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.SQLException;

public final class TransferService {

    private TransferService() {}

    public static void transfer(
            Connection conn,
            String transferCode,
            int senderId,
            int receiverId,
            BigDecimal amount
    ) throws SQLException {

        if (amount == null || amount.signum() <= 0) {
            throw new IllegalArgumentException(
                "Số tiền phải lớn hơn 0"
            );
        }
        if (senderId == receiverId) {
            throw new IllegalArgumentException(
                "Tài khoản gửi phải khác tài khoản nhận"
            );
        }

        boolean oldAutoCommit = conn.getAutoCommit();
        if (!oldAutoCommit) {
            throw new IllegalStateException(
                "Connection đã có transaction do bên ngoài quản lý"
            );
        }

        conn.setAutoCommit(false);

        try {
            insertTransfer(
                conn, transferCode, senderId, receiverId, amount
            );

            int debitRows = updateBalance(
                conn, senderId, amount.negate(), amount
            );
            if (debitRows != 1) {
                throw new SQLException(
                    "Không trừ được đúng một tài khoản gửi"
                );
            }

            int creditRows = updateBalance(
                conn, receiverId, amount, null
            );
            if (creditRows != 1) {
                throw new SQLException(
                    "Không cộng được đúng một tài khoản nhận"
                );
            }

            insertMovement(
                conn, transferCode, senderId, "DEBIT", amount
            );
            insertMovement(
                conn, transferCode, receiverId, "CREDIT", amount
            );

            conn.commit();

        } catch (SQLException | RuntimeException ex) {
            try {
                conn.rollback();
            } catch (SQLException rollbackError) {
                ex.addSuppressed(rollbackError);
            }
            throw ex;

        } finally {
            conn.setAutoCommit(oldAutoCommit);
        }
    }

    private static void insertTransfer(
            Connection conn,
            String code,
            int senderId,
            int receiverId,
            BigDecimal amount
    ) throws SQLException {

        String sql = """
            INSERT INTO tx_chuyen_tien
                (ma_giao_dich, tai_khoan_gui, tai_khoan_nhan, so_tien)
            VALUES (?, ?, ?, ?)
            """;

        try (PreparedStatement ps = conn.prepareStatement(sql)) {
            ps.setString(1, code);
            ps.setInt(2, senderId);
            ps.setInt(3, receiverId);
            ps.setBigDecimal(4, amount);

            if (ps.executeUpdate() != 1) {
                throw new SQLException(
                    "Không ghi được yêu cầu chuyển tiền"
                );
            }
        }
    }

    private static int updateBalance(
            Connection conn,
            int accountId,
            BigDecimal delta,
            BigDecimal minimumBalance
    ) throws SQLException {

        String sql = """
            UPDATE tx_tai_khoan
            SET so_du = so_du + ?
            WHERE id = ?
              AND trang_thai = 'ACTIVE'
              AND (? IS NULL OR so_du >= ?)
            """;

        try (PreparedStatement ps = conn.prepareStatement(sql)) {
            ps.setBigDecimal(1, delta);
            ps.setInt(2, accountId);
            ps.setBigDecimal(3, minimumBalance);
            ps.setBigDecimal(4, minimumBalance);
            return ps.executeUpdate();
        }
    }

    private static void insertMovement(
            Connection conn,
            String code,
            int accountId,
            String type,
            BigDecimal amount
    ) throws SQLException {

        String sql = """
            INSERT INTO tx_bien_dong
                (ma_giao_dich, tai_khoan_id, loai, so_tien)
            VALUES (?, ?, ?, ?)
            """;

        try (PreparedStatement ps = conn.prepareStatement(sql)) {
            ps.setString(1, code);
            ps.setInt(2, accountId);
            ps.setString(3, type);
            ps.setBigDecimal(4, amount);

            if (ps.executeUpdate() != 1) {
                throw new SQLException(
                    "Không ghi được biến động"
                );
            }
        }
    }
}
~~~

### 14.2. Vì sao mã dùng BigDecimal?

Số tiền nên tránh biểu diễn bằng `double` khi yêu cầu độ chính xác thập phân. Trong ví dụ PostgreSQL, `NUMERIC(14,2)` và Java `BigDecimal` phù hợp để truyền số tiền mà không dựa vào phép tính nhị phân xấp xỉ của kiểu floating-point.

Tuy nhiên, hệ thống thật phải có quy tắc **đơn vị tiền, số chữ số thập phân, làm tròn và giới hạn giá trị**; không chỉ chọn BigDecimal là đủ.

### 14.3. Vì sao điều kiện UPDATE có (? IS NULL OR so_du >= ?)?

Phương thức `updateBalance` được dùng cho hai trường hợp:

- Trừ tiền: `delta = -amount` và `minimumBalance = amount`. Điều kiện kiểm tra đủ số dư.
- Cộng tiền: `delta = amount` và `minimumBalance = null`. Không cần kiểm tra đủ tiền.

Hai lần gọi đều yêu cầu đúng **1 hàng cập nhật**. Nếu tài khoản bị BLOCKED, không tồn tại, hoặc không đủ tiền ở bước trừ, câu UPDATE trả 0 hàng, ứng dụng ném exception để rollback.

Với SQL PostgreSQL, trong một số tình huống bind tham số NULL không có kiểu rõ ràng, dạng `? IS NULL` có thể khiến driver cần thông tin kiểu. Để tránh sự phụ thuộc ấy trong mã sản xuất, bạn có thể dùng **hai câu UPDATE riêng**, một câu có điều kiện `so_du >= ?` cho trừ tiền và một câu không có điều kiện đó cho cộng tiền; dùng `setNull(..., Types.NUMERIC)` hoặc ép kiểu phù hợp khi thực sự cần parameter nullable. Bài học nhấn mạnh ranh giới giao dịch, không yêu cầu phải gộp hai dạng cập nhật vào một SQL.

### 14.4. Vì sao cần bắt cả SQLException và RuntimeException?

Các lời gọi JDBC có thể ném `SQLException`; logic ứng dụng có thể ném `RuntimeException` trong lúc thao tác. Nếu lỗi xảy ra trước COMMIT, phương thức cần nỗ lực ROLLBACK để không để lại transaction mở.

Ví dụ dùng `ex.addSuppressed(rollbackError)` để giữ lỗi rollback kèm theo lỗi ban đầu. `finally` cố gắng phục hồi chế độ auto-commit; nếu connection hỏng, tầng quản lý connection pool cũng cần loại bỏ/đóng connection phù hợp.

### 14.5. Mẫu tối giản cho việc hiểu transaction JDBC

Nếu chưa cần đọc toàn bộ ví dụ, hãy nhớ lõi cấu trúc:

~~~java
boolean oldAutoCommit = conn.getAutoCommit();
conn.setAutoCommit(false);

try {
    // INSERT / UPDATE / DELETE trên cùng conn.
    // Kiểm tra số hàng và điều kiện nghiệp vụ.
    conn.commit();
} catch (SQLException | RuntimeException ex) {
    try {
        conn.rollback();
    } catch (SQLException rollbackError) {
        ex.addSuppressed(rollbackError);
    }
    throw ex;
} finally {
    conn.setAutoCommit(oldAutoCommit);
}
~~~

Đây là mẫu điều khiển dành cho **phương thức sở hữu transaction**. Nếu connection đã trong transaction do bên khác quản lý, không tự ý COMMIT hay ROLLBACK. Với frameworks, ưu tiên transaction manager của framework.

## 15. Transaction với Spring: ranh giới ở tầng service

Trong ứng dụng Spring, bạn có thể thường thấy:

~~~java
@Service
public class OrderService {

    private final OrderRepository orderRepository;
    private final InventoryRepository inventoryRepository;

    public OrderService(
            OrderRepository orderRepository,
            InventoryRepository inventoryRepository
    ) {
        this.orderRepository = orderRepository;
        this.inventoryRepository = inventoryRepository;
    }

    @Transactional
    public long placeOrder(OrderRequest request) {
        long orderId = orderRepository.insertOrder(request);

        for (OrderLineRequest line : request.lines()) {
            orderRepository.insertLine(orderId, line);

            int changed = inventoryRepository.decreaseIfEnough(
                line.productId(), line.quantity()
            );

            if (changed != 1) {
                throw new IllegalStateException(
                    "Không đủ tồn kho hoặc sản phẩm không tồn tại"
                );
            }
        }

        return orderId;
    }
}
~~~

Đây là **mẫu ý tưởng**, không phải chương trình có đủ class/import/configuration để chạy ngay. Điểm chính:

- `@Transactional` định nghĩa ranh giới transaction phù hợp với Spring transaction manager đã cấu hình.
- Các repository phải dùng nguồn dữ liệu/connection được tham gia cùng transaction ấy.
- Nếu một bước thất bại, cơ chế rollback cần được cấu hình phù hợp.

### 15.1. Đừng mặc định mọi exception đều rollback như nhau

Trong cấu hình Spring phổ biến, các exception unchecked như `RuntimeException` thường kích hoạt rollback theo mặc định; checked exception có thể cần `rollbackFor` hoặc quy tắc riêng.

Không nên viết `catch (Exception e) { log(e); return success; }` trong một phương thức @Transactional rồi giả định framework tự nhận biết đây là thất bại và rollback. Nếu bạn nuốt exception và trả về bình thường, transaction manager có thể COMMIT.

### 15.2. Self-invocation và proxy transaction

Ở nhiều cấu hình Spring dùng proxy, một lời gọi phương thức `@Transactional` thông qua `this.method()` **bên trong cùng đối tượng** có thể không đi qua proxy transaction, nên annotation ở phương thức được gọi không tự tạo ranh giới như người lập trình mong đợi.

Vì thế, ranh giới service phải được thiết kế và xác minh theo cơ chế transaction thực tế của framework, không chỉ “thấy annotation là đủ”.

### 15.3. Nhiều database không tự có một giao dịch chung

Nếu hai repository ghi vào hai database khác nhau qua hai transaction manager độc lập, một `@Transactional` bình thường không mặc nhiên tạo transaction phân tán nguyên tử giữa chúng. Cần kiến trúc giao dịch phân tán hoặc quy trình bù trừ phù hợp, tùy bài toán.

## 16. Isolation: giao dịch đồng thời không chỉ là COMMIT/ROLLBACK

Nguyên tử trả lời “nhóm thay đổi có được commit cùng nhau không?”. **Isolation** trả lời “hai transaction đang chạy đồng thời ảnh hưởng nhau thế nào?”.

### 16.1. Hai lần rút tiền cùng lúc

Giả sử An có 1000; transaction A và B đều muốn rút 700.

Nếu ứng dụng làm:

~~~text
A: SELECT so_du → 1000
B: SELECT so_du → 1000
A: tính 1000 - 700 = 300
B: tính 1000 - 700 = 300
A: UPDATE so_du = 300
B: UPDATE so_du = 300
~~~

đây là nguy cơ **lost update** hoặc quyết định dựa trên dữ liệu cũ nếu không có cơ chế kiểm soát phù hợp. Hai lần rút tổng 1400 nhưng số dư cuối có thể chỉ thể hiện một lần rút.

Một cách tốt hơn:

~~~sql
UPDATE tx_tai_khoan
SET so_du = so_du - 700
WHERE id = 1
  AND so_du >= 700
RETURNING id, so_du;
~~~

Với PostgreSQL và các mức cô lập thông dụng, các UPDATE cùng một hàng phải xử lý khóa/phiên bản cạnh tranh; chỉ một transaction có thể trừ thành công khi số dư không còn đủ cho lần thứ hai. Ứng dụng vẫn phải xử lý việc **0 hàng được cập nhật** hoặc lỗi cạnh tranh/serialization, không chỉ cho rằng transaction nào cũng thành công.

### 16.2. READ COMMITTED: SELECT có thể khác nhau

Ở PostgreSQL, mức cô lập mặc định `READ COMMITTED` thường cho phép **mỗi statement** thấy snapshot dữ liệu được commit phù hợp tại thời điểm statement bắt đầu.

Ví dụ:

~~~text
Connection A: BEGIN
Connection A: SELECT số dư An → 1000

Connection B: UPDATE An -100, COMMIT

Connection A: SELECT số dư An → có thể thấy 900
Connection A: COMMIT
~~~

Hai SELECT cùng transaction A có thể thấy giá trị khác nhau dưới READ COMMITTED. Vì vậy, **BEGIN không đồng nghĩa chụp bất biến mọi dữ liệu đến cuối transaction**.

### 16.3. REPEATABLE READ và SERIALIZABLE

PostgreSQL còn cung cấp các mức cô lập mạnh hơn:

- **REPEATABLE READ**: giúp transaction dùng snapshot nhất quán hơn; các tình huống cập nhật cạnh tranh có thể dẫn đến lỗi phải thử lại.
- **SERIALIZABLE**: hướng tới hành vi tương đương một thứ tự thực thi tuần tự hợp lệ; PostgreSQL có thể phát hiện xung đột và hủy một transaction bằng lỗi serialization.

Mức cô lập không tự thay thế điều kiện nghiệp vụ, kiểm tra số hàng, FK/UNIQUE hay việc xử lý retry. Mức cao hơn cũng có chi phí và khả năng abort, nên chọn theo bất biến cần bảo vệ.

### 16.4. SELECT FOR UPDATE

Khi cần khóa một hàng để kiểm tra rồi cập nhật trong cùng transaction:

~~~sql
BEGIN;

SELECT id, so_du, trang_thai
FROM tx_tai_khoan
WHERE id = 1
FOR UPDATE;

-- Thực hiện logic nghiệp vụ và UPDATE phù hợp
-- trong thời gian transaction còn mở.

ROLLBACK;
~~~

`FOR UPDATE` khóa hàng đọc được trong PostgreSQL, giúp hạn chế các transaction khác sửa/xóa hàng ấy cho tới khi transaction của bạn kết thúc. Nhưng nó không tự khóa mọi hàng mới thỏa điều kiện lọc trong tương lai.

Tránh giữ transaction có FOR UPDATE trong lúc chờ người dùng nhấn nút, gọi API chậm hoặc xử lý công việc không cần thiết.

## 17. Deadlock và thứ tự khóa

Hai transaction có thể khóa tài nguyên theo thứ tự ngược nhau:

~~~text
Transaction A:
  Khóa tài khoản 1
  Muốn khóa tài khoản 2

Transaction B:
  Khóa tài khoản 2
  Muốn khóa tài khoản 1

→ Có thể deadlock.
~~~

DBMS thường có cơ chế phát hiện deadlock và hủy một transaction để phá vòng chờ. PostgreSQL có thể trả SQLSTATE `40P01` cho deadlock. Ứng dụng cần rollback và có thể retry cả transaction theo chính sách phù hợp.

### 17.1. Giảm nguy cơ bằng thứ tự khóa nhất quán

Với chuyển tiền giữa hai tài khoản, một nguyên tắc thực hành là **khóa tài khoản theo ID tăng dần**, bất kể chiều chuyển tiền:

~~~sql
BEGIN;

SELECT id, so_du
FROM tx_tai_khoan
WHERE id IN (1, 2)
ORDER BY id
FOR UPDATE;

-- Sau khi khóa, thực hiện kiểm tra và UPDATE có điều kiện.

ROLLBACK;
~~~

Cách tiếp cận **thống nhất thứ tự truy cập khóa** có thể giảm deadlock, nhưng không có lời hứa loại hết mọi deadlock: trigger, FK, các bảng khác và kế hoạch truy cập cũng có thể ảnh hưởng.

### 17.2. Retry phải retry cả transaction

Nếu transaction bị hủy vì deadlock hoặc serialization failure, không chỉ chạy lại **statement cuối cùng** trên một ngữ cảnh giao dịch đã thất bại. Cần khởi tạo transaction mới và chạy lại **toàn bộ logic kiểm tra + thay đổi** cần thiết, đồng thời xử lý idempotency khi có khả năng commit trước đó không rõ.

## 18. Khi COMMIT gặp sự cố mạng: không biết chắc kết quả

Tình huống:

~~~text
Ứng dụng → gửi COMMIT
Database → COMMIT thành công
Mạng đứt trước khi phản hồi tới ứng dụng
Ứng dụng → thấy timeout / mất kết nối
~~~

Ứng dụng có thể **không biết** transaction đã commit hay chưa. Việc chạy lại “chuyển tiền” với **mã giao dịch mới** có thể chuyển tiền lần thứ hai.

### 18.1. Mã nghiệp vụ duy nhất giúp xử lý retry

Bảng `tx_chuyen_tien` có khóa chính `ma_giao_dich`. Khi request được gửi lại với **cùng mã**, một INSERT lặp có thể bị UNIQUE chặn nếu transaction trước đã commit.

Nhưng không nên đơn giản bắt lỗi unique rồi trả “thành công”: cần xác thực cùng mã giao dịch thuộc đúng người, đúng tài khoản, đúng số tiền, và trạng thái ghi nhận đã đầy đủ.

### 18.2. ON CONFLICT DO NOTHING chưa đủ cho toàn bộ nghiệp vụ

~~~sql
INSERT INTO tx_chuyen_tien
    (ma_giao_dich, tai_khoan_gui, tai_khoan_nhan, so_tien)
VALUES ('CT-RETRY-01', 1, 2, 250)
ON CONFLICT (ma_giao_dich) DO NOTHING
RETURNING ma_giao_dich;
~~~

Nếu mã đã tồn tại, PostgreSQL có thể trả **0 hàng**. Không được tiếp tục trừ/cộng tiền như thể một transfer mới được tạo; ứng dụng phải rẽ sang nhánh **đối chiếu kết quả request cũ**.

Một transaction nhiều bảng cần idempotency bao trùm **đầu yêu cầu, số dư và nhật ký**, không chỉ một lệnh INSERT tránh trùng.

### 18.3. Atomicity và exactly-once là hai vấn đề khác

Atomicity chỉ quy định cách các thay đổi trong **một transaction** được xác nhận hoặc hủy. Nó không tự bảo đảm API bên ngoài chỉ gọi đúng một lần khi có retry, mạng chập chờn hoặc nhiều worker xử lý.

Muốn tránh chuyển tiền lặp, còn cần khóa nghiệp vụ, kiểm tra trạng thái, phương thức idempotent hoặc cơ chế nhất quán phân tán phù hợp.

## 19. Database transaction không rollback email hoặc API ngoài

Giả sử workflow:

~~~text
BEGIN
  INSERT đơn hàng
  Gửi email "Đặt hàng thành công"  ← dịch vụ mail ngoài DB
  UPDATE tồn kho → thất bại
ROLLBACK
~~~

Database có thể xóa đơn được INSERT trong transaction, nhưng **email đã gửi không tự thu hồi**. Người dùng có thể nhận email về một đơn không tồn tại.

### 19.1. Không gửi tác động không thể rollback giữa transaction một cách tùy tiện

Một hướng thiết kế là:

- Hoàn tất dữ liệu transaction trước khi phát thông báo.
- Sau COMMIT mới gửi thông báo khi chấp nhận rủi ro mất thông báo.
- Hoặc dùng **transactional outbox**: ghi một sự kiện cần gửi vào bảng outbox **trong cùng transaction**, rồi một worker ngoài transaction gửi email và đánh dấu trạng thái theo cơ chế retry.

### 19.2. Outbox giải quyết phạm vi nào?

Ví dụ:

~~~text
BEGIN
  INSERT đơn hàng
  UPDATE tồn kho
  INSERT outbox_event ("ORDER_CREATED")
COMMIT

Worker riêng:
  Đọc outbox đã commit
  Gửi email / sự kiện
  Đánh dấu hoặc retry
~~~

Database transaction bảo đảm đơn, kho và **bản ghi outbox** cùng tồn tại hoặc cùng không tồn tại. Nhưng gửi email có thể bị thử lại, nên phía consumer cần idempotency/deduplication phù hợp.

Outbox **không tự biến email hay API thành một phần rollback được**. Nó là cơ chế tổ chức tính nhất quán giữa thay đổi DB và việc gửi sự kiện có khả năng thất bại.

### 19.3. Tác động thực tế khác

Tương tự đối với:

- Ghi file lên object storage.
- Gửi SMS.
- Gọi API thanh toán.
- Cập nhật cache ngoài database.
- Phát message lên broker.

Nếu cần tính đúng đắn xuyên hệ thống, phải thiết kế theo khả năng transactional của từng tài nguyên, hoặc dùng saga/compensation, outbox/inbox, idempotency, 2PC khi phù hợp. Một `BEGIN` đơn thuần trong PostgreSQL không tự bao trùm những hệ thống ấy.

## 20. Giao dịch lồng, điểm lưu và ranh giới thư viện

Một phương thức ứng dụng có thể gọi nhiều lớp:

~~~text
OrderService.createOrder()
    ├── OrderRepository.insertOrder()
    ├── OrderLineRepository.insertLines()
    └── InventoryRepository.decreaseStock()
~~~

**Ranh giới nghiệp vụ** thường đặt ở service và bao trùm các repository. Các repository không nên tự COMMIT nếu service yêu cầu cả nhóm nguyên tử.

### 20.1. Lỗi khi mỗi repository commit riêng

~~~text
OrderRepository.insertOrder():
    BEGIN; INSERT; COMMIT;

InventoryRepository.decreaseStock():
    BEGIN; UPDATE; ROLLBACK;
~~~

Đơn vẫn tồn tại sau khi kho thất bại. Hai phương thức có hai transaction riêng, bất kể chúng được gọi liên tiếp trong cùng service.

### 20.2. SAVEPOINT không có ý nghĩa “commit phần con”

Nếu một thư viện tạo savepoint rồi RELEASE sau khi thành công, transaction ngoài vẫn có thể ROLLBACK toàn bộ. Không nên gọi savepoint là “transaction con đã commit độc lập”.

### 20.3. Transaction propagation do framework quyết định

Các framework có cơ chế propagation: tham gia transaction hiện có, yêu cầu transaction mới, tạo savepoint hoặc chạy không có transaction. Một nhánh “REQUIRES_NEW” ở framework có thể tạo transaction riêng và COMMIT ngay cả khi transaction ngoài rollback sau đó.

Vì thế phải biết cấu hình transaction thực tế; **một call stack Java không mặc nhiên là một transaction duy nhất**.

## 21. Ranh giới giao dịch khi có DDL

Trong PostgreSQL, nhiều DDL như `CREATE TABLE` hoặc `ALTER TABLE` có thể chạy trong transaction và được rollback nếu chưa commit.

Ví dụ:

~~~sql
BEGIN;

CREATE TEMP TABLE tx_bang_thu (
    id INTEGER PRIMARY KEY
);

INSERT INTO tx_bang_thu (id) VALUES (1);

ROLLBACK;

-- Sau rollback, bảng được tạo trong transaction cũng không còn
-- trong phiên PostgreSQL, nếu trước đó nó chưa tồn tại.
~~~

Nhưng **không phải mọi lệnh quản trị PostgreSQL đều được phép chạy trong transaction**. Ví dụ `CREATE DATABASE` không được thực thi bên trong transaction block thông thường.

### 21.1. Khác biệt lớn giữa các DBMS

Một số DBMS như MySQL có những DDL gây **implicit commit** hoặc không rollback theo cùng cách PostgreSQL, dù các bảng dữ liệu giao dịch sử dụng InnoDB. SQL Server, Oracle và SQLite cũng có các quy tắc riêng.

Không gộp câu DDL nguy hiểm vào migration cùng DML rồi giả định `ROLLBACK` luôn có thể quay lại mọi thứ trên mọi DBMS. Hãy xác nhận cơ chế transaction của lệnh và hệ quản trị cụ thể.

### 21.2. Sequence và IDENTITY không bảo đảm hoàn tác số đã cấp

Trong PostgreSQL, giá trị sequence đã cấp có thể **không được trả về** khi transaction rollback. Vì vậy, sau một transaction INSERT lỗi rồi rollback, ID mới tiếp theo có thể nhảy qua một số.

Điều này **không vi phạm atomicity của dữ liệu nghiệp vụ**: các bản ghi được chèn trong transaction đã hủy không được commit, nhưng sequence là loại đối tượng có ngữ nghĩa cấp phát riêng.

## 22. Phân biệt atomicity với “an toàn tuyệt đối”

Một transaction có thể nguyên tử nhưng vẫn sai:

### 22.1. Sai đối tượng

~~~sql
BEGIN;
UPDATE tx_tai_khoan SET so_du = so_du - 50 WHERE id = 1;
UPDATE tx_tai_khoan SET so_du = so_du + 50 WHERE id = 3;
COMMIT;
~~~

Nếu nghiệp vụ cần nhận ở ID 2 nhưng lập trình dùng ID 3, database có thể commit cả hai. Atomicity không biết ID 3 là tài khoản nhận không đúng.

### 22.2. Sai số tiền

~~~sql
BEGIN;
UPDATE tx_tai_khoan SET so_du = so_du - 100 WHERE id = 1;
UPDATE tx_tai_khoan SET so_du = so_du + 90 WHERE id = 2;
COMMIT;
~~~

Có thể commit thành công nhưng tổng giảm 10. Phải kiểm tra sự cân bằng của chuyển tiền.

### 22.3. Sai số lượng hàng

~~~sql
BEGIN;
UPDATE tx_tai_khoan SET so_du = so_du - 100 WHERE id = 999;
UPDATE tx_tai_khoan SET so_du = so_du + 100 WHERE id = 2;
COMMIT;
~~~

UPDATE đầu có thể tác động 0 hàng, UPDATE sau một hàng, gây tạo tiền từ không. Cần kiểm tra affected rows và rollback khi kết quả không đúng.

### 22.4. Sai tác động bên ngoài

Nếu email đã gửi giữa transaction nhưng COMMIT thất bại, email vẫn có thể đến nơi. Bảo đảm nguyên tử của database không bao phủ việc gửi ngoài DB.

### 22.5. Sai khi nhiều luồng cùng chạy

Hai transaction cùng đúng nếu chạy một mình vẫn có thể xung đột khi đồng thời. Cần mức cô lập, khóa, ràng buộc, optimistic concurrency hoặc cơ chế retry thích hợp.

**Kết luận:** nguyên tử là **một nền tảng** cho tính đúng đắn, không phải giấy bảo đảm mọi nghiệp vụ sẽ đúng nếu chỉ viết BEGIN và COMMIT.

## 23. ROLLBACK và trạng thái quan sát của nhiều kết nối

### 23.1. Cùng connection có thể đọc thay đổi chưa commit

~~~sql
BEGIN;
UPDATE tx_tai_khoan SET so_du = 900 WHERE id = 1;
SELECT so_du FROM tx_tai_khoan WHERE id = 1;
ROLLBACK;
~~~

Trong chính transaction, SELECT sau UPDATE thấy 900. Sau rollback lại 1000.

### 23.2. Kết nối khác thường không đọc thấy dữ liệu chưa commit

Ở PostgreSQL, một connection khác sẽ không đọc được thay đổi chưa commit như “dirty read” ở chế độ thông thường. Nó có thể thấy giá trị cũ hoặc bị tác động bởi khóa/đồng thời theo loại thao tác và isolation.

**Dữ liệu bảng TEMP của bài chỉ tồn tại trong session tạo ra**, nên không thể dùng connection B đọc cùng bảng TEMP để quan sát trực tiếp ví dụ này. Để thực hành hai connection, phải tạo **bảng thường trong database thử nghiệm** và có quyền truy cập cả hai session, sau đó xóa khi kết thúc theo quy trình an toàn.

### 23.3. PostgreSQL READ UNCOMMITTED

Dù PostgreSQL chấp nhận tên isolation `READ UNCOMMITTED` trong cú pháp, hành vi thực tế được xử lý tương tự READ COMMITTED. Không nên mong đọc được dữ liệu chưa commit giữa hai kết nối PostgreSQL bằng cách đổi isolation sang READ UNCOMMITTED.

## 24. Tính nguyên tử khi một statement cập nhật nhiều hàng

Ngay cả một statement UPDATE tác động nhiều hàng cũng có tính nguyên tử ở mức statement trên một bảng transactional thông thường.

Ví dụ:

~~~sql
BEGIN;

UPDATE tx_tai_khoan
SET so_du = so_du + 10
WHERE id IN (1, 2, 3)
RETURNING id, so_du;

ROLLBACK;
~~~

Nếu thành công, ba hàng được cập nhật trong transaction; rollback hủy cả ba. Nếu statement bị lỗi ràng buộc ở một hàng, PostgreSQL không commit một nửa các thay đổi của cùng statement đó.

### 24.1. Cần phân biệt SQL statement thành công với nghiệp vụ thành công

Nếu một ID không tồn tại, UPDATE có thể chỉ tác động hai hàng mà không có lỗi. Statement nguyên tử ở mức hai hàng thực sự được cập nhật, nhưng nghiệp vụ “cập nhật đúng ba tài khoản” chưa đạt.

Phải kiểm tra:

~~~text
Expected affected IDs = {1, 2, 3}
Actual affected IDs   = {1, 3}
→ Không nên COMMIT nếu nghiệp vụ cần đủ ba.
~~~

### 24.2. So tập ID có thể quan trọng hơn chỉ COUNT

Hai tập `{1, 2, 3}` và `{1, 3, 4}` đều có ba phần tử. Chỉ kiểm tra affected rows = 3 chưa phát hiện nhầm tài khoản. Với thao tác nhạy cảm, lấy ID thực tế từ `RETURNING` và so với tập đã duyệt hoặc dùng khóa nghiệp vụ được xác thực.

## 25. Trường hợp đặc biệt: xóa cha–con trong một transaction

Giả sử một đơn có dòng chi tiết và FK từ `tx_dong_don.don_hang_id` đến `tx_don_hang.id`, **không cấu hình ON DELETE CASCADE**. Muốn xóa đơn và dòng của nó theo một nghiệp vụ đã cho phép:

~~~sql
BEGIN;

-- Bước 1: xóa dòng con.
DELETE FROM tx_dong_don
WHERE don_hang_id = :don_hang_id;

-- Bước 2: xóa cha.
DELETE FROM tx_don_hang
WHERE id = :don_hang_id;

-- Chỉ COMMIT sau khi kiểm tra các điều kiện nghiệp vụ.
COMMIT;
~~~

`:don_hang_id` là **tham số minh họa**, không phải cú pháp SQL thuần PostgreSQL dán trực tiếp vào mọi client. Trong JDBC dùng `?` và cùng Connection.

### 25.1. Vì sao con trước, cha sau?

Nếu FK chặn xóa cha khi vẫn còn con, cố DELETE cha trước sẽ lỗi. Xóa con rồi cha trong **cùng transaction** cho phép hoàn tác cả hai nếu bước sau thất bại.

### 25.2. DELETE 0 hàng cũng cần xem xét

Nếu đơn không tồn tại, DELETE cha có thể xóa 0 hàng mà không lỗi. Nếu nghiệp vụ bắt buộc xóa đúng một đơn, phải phát hiện và quyết định rollback/không commit.

### 25.3. CASCADE thay đổi hậu quả, không thay đổi ranh giới

Nếu FK được định nghĩa `ON DELETE CASCADE`, DELETE cha có thể tự xóa con phù hợp trong cùng statement/transaction. Vẫn cần xem trước các bảng bị ảnh hưởng và quyền xóa; atomicity không tự xác nhận rằng việc xóa dây chuyền là đúng nghiệp vụ.

### 25.4. Xóa mềm cũng cần transaction

Nếu chỉ cập nhật trạng thái hủy đơn nhưng phải hoàn tồn kho và ghi nhật ký, đó vẫn là **nhóm thay đổi** cần transaction, dù không có DELETE vật lý.

## 26. Các hệ quản trị SQL có gì khác nhau?

| DBMS | Bắt đầu transaction | Xác nhận/hủy | Lưu ý |
|---|---|---|---|
| **PostgreSQL** | `BEGIN` hoặc `START TRANSACTION` | `COMMIT` / `ROLLBACK` | MVCC, SAVEPOINT; nhiều DDL transactional; lỗi statement thường khiến transaction aborted |
| **MySQL (InnoDB)** | `START TRANSACTION` / `BEGIN` | `COMMIT` / `ROLLBACK` | Xác nhận bảng đang dùng engine transactional; nhiều DDL implicit commit |
| **MariaDB** | `START TRANSACTION` | `COMMIT` / `ROLLBACK` | Chi tiết phụ thuộc storage engine và phiên bản |
| **SQL Server** | `BEGIN TRANSACTION` | `COMMIT TRANSACTION` / `ROLLBACK TRANSACTION` | Chú ý `@@TRANCOUNT`, `XACT_STATE()`, `SET XACT_ABORT` và savepoint |
| **Oracle** | Transaction thường bắt đầu ngầm khi DML đầu tiên chạy | `COMMIT` / `ROLLBACK` | DDL thường implicit commit; SAVEPOINT được hỗ trợ |
| **SQLite** | `BEGIN`, `BEGIN IMMEDIATE` hoặc `BEGIN EXCLUSIVE` tùy chế độ | `COMMIT` / `ROLLBACK` | Cơ chế khóa/đồng thời khác server RDBMS; DDL có thể transactional theo ngữ cảnh |

### 26.1. PostgreSQL: BEGIN/COMMIT

~~~sql
BEGIN;
UPDATE tx_tai_khoan SET so_du = so_du + 10 WHERE id = 3;
COMMIT;
~~~

Nếu chạy thật trong phiên thực hành, Chi sẽ tăng từ 150 lên 160. Những ví dụ tiếp theo dùng dữ liệu gốc cần ROLLBACK hoặc tái tạo bộ dữ liệu nếu đã COMMIT thao tác thay đổi.

### 26.2. MySQL: engine phải hỗ trợ transaction

Trên bảng InnoDB:

~~~sql
START TRANSACTION;

UPDATE tai_khoan
SET so_du = so_du - 100
WHERE id = 1 AND so_du >= 100;

UPDATE tai_khoan
SET so_du = so_du + 100
WHERE id = 2;

COMMIT;
~~~

Vẫn phải kiểm tra số hàng thay đổi như phần PostgreSQL. Nếu một bảng dùng storage engine không có transaction, không thể giả định ROLLBACK sẽ hoàn tác nó chỉ vì đã viết START TRANSACTION.

### 26.3. SQL Server: BEGIN TRANSACTION

~~~sql
BEGIN TRANSACTION;

UPDATE dbo.TaiKhoan
SET SoDu = SoDu - 100
WHERE Id = 1 AND SoDu >= 100;

UPDATE dbo.TaiKhoan
SET SoDu = SoDu + 100
WHERE Id = 2;

COMMIT TRANSACTION;
~~~

SQL Server có các công cụ kiểm tra tình trạng transaction như `@@TRANCOUNT`, `XACT_STATE()` và `TRY...CATCH`. Không nên áp dụng trực tiếp giả định “một lỗi làm mọi statement sau bị từ chối cho tới ROLLBACK” của PostgreSQL cho mọi cấu hình SQL Server; `SET XACT_ABORT` và loại lỗi ảnh hưởng hành vi.

### 26.4. Oracle: DDL có thể commit ngầm

Oracle thường quản lý transaction bắt đầu bởi DML mà không cần một lệnh `BEGIN TRANSACTION` theo cú pháp PostgreSQL. Trong PL/SQL, `BEGIN ... END` là khối lập trình, **không đồng nghĩa bắt đầu SQL transaction mới**.

Nếu chèn DDL vào quy trình, nhiều lệnh DDL Oracle có implicit commit. Vì vậy, ranh giới rollback cần được nghiên cứu theo Oracle chứ không thể sao chép logic PostgreSQL.

### 26.5. SQLite: khóa và concurrency khác PostgreSQL

SQLite hỗ trợ transaction nhưng cơ chế quản lý người đọc/người ghi và các chế độ BEGIN có điểm riêng. Trong ứng dụng nhiều luồng hoặc nhiều tiến trình, có thể gặp `SQLITE_BUSY` hoặc những tình huống chờ khóa; cần timeout/retry phù hợp.

**Nguyên tắc chung vẫn là:** chọn ranh giới transaction đúng với nghiệp vụ và kiểm tra các thay đổi thực tế trước COMMIT.

## 27. Lỗi và hiểu lầm thường gặp

| Hiểu lầm | Vì sao sai? | Cách xử lý |
|---|---|---|
| Có BEGIN là nghiệp vụ tự đúng | BEGIN chỉ mở transaction | Kiểm tra bất biến, số hàng, ID, điều kiện |
| Mọi statement cùng chạy trong một hàm Java nên nguyên tử | Có thể dùng nhiều connection hoặc autocommit | Dùng cùng transaction/connection |
| UPDATE 0 hàng sẽ gây rollback | 0 hàng thường không phải lỗi SQL | Kiểm tra affected rows và rollback chủ động |
| COMMIT một transaction thì mọi API/email cũng commit | Tài nguyên ngoài DB không nằm trong transaction | Outbox/idempotency/compensation |
| ROLLBACK sau COMMIT hủy được dữ liệu | Transaction đã đóng | Thiết kế bù trừ hoặc recovery |
| Mỗi repository commit riêng vẫn bảo vệ được đơn hàng | Ranh giới chia thành nhiều transaction | Transaction ở tầng service nghiệp vụ |
| ROLLBACK trả lại số sequence đã cấp | Sequence thường không rollback | Chấp nhận khoảng trống ID |
| SAVEPOINT là transaction con commit độc lập | RELEASE không phải COMMIT ngoài cùng | Hiểu savepoint là điểm hoàn tác |
| Hai Connection tự dùng chung transaction | Mỗi connection có session/transaction riêng | Transaction manager/connection nhất quán |
| BEGIN cố định mọi SELECT đến cuối | READ COMMITTED có thể thấy snapshot mới | Chọn isolation hoặc locking phù hợp |
| Atomicity tự chặn lost update | Isolation/concurrency là thuộc tính khác | UPDATE có điều kiện, khóa, version, retry |
| CHECK >= 0 bảo đảm chuyển tiền cân bằng | CHECK chỉ kiểm tra số dư mỗi hàng | Logic cân bằng debit/credit |
| Nếu statement không lỗi thì chắc đã chèn đủ | INSERT SELECT / UPDATE WHERE có thể 0 hàng | Kiểm tra số hàng và khóa |
| Giữ khóa trong lúc chờ người dùng là an toàn | Có thể gây chờ và deadlock kéo dài | Transaction ngắn, xác thực lại |
| MySQL/Oracle/PostgreSQL rollback DDL giống nhau | Có khác biệt implicit commit | Kiểm tra DBMS/engine |
| Lỗi mạng sau COMMIT nghĩa chắc chắn rollback | Có thể COMMIT đã thành công | Idempotency và xác minh kết quả |
| Retry chỉ statement cuối sau deadlock | Transaction có thể đã bị hủy | Retry cả workflow trong transaction mới |
| Xóa cha rồi con luôn được | FK có thể chặn | Chính sách FK, xóa con trước hoặc CASCADE phù hợp |

## 28. Bài tập có lời giải

Các bài sử dụng bảng `tx_tai_khoan`, `tx_bien_dong`, `tx_chuyen_tien`, `tx_san_pham`, `tx_don_hang` và `tx_dong_don` đã tạo ở phần 5. Khi bài yêu cầu làm thay đổi dữ liệu, hãy dùng **BEGIN ... ROLLBACK** để trạng thái mẫu không bị thay đổi cho bài sau.

### Bài 1. Xác định các ranh giới

**Đề bài:** Cho:

~~~sql
BEGIN;
UPDATE A SET x = 1;
UPDATE B SET y = 2;
COMMIT;

BEGIN;
UPDATE C SET z = 3;
ROLLBACK;
~~~

Hỏi có mấy transaction? Thay đổi nào được xác nhận?

**Đáp án:** Hai transaction. Các UPDATE trên A và B nằm cùng transaction thứ nhất và được commit. UPDATE C thuộc transaction thứ hai và bị rollback. Không thể dùng ROLLBACK thứ hai để hủy A/B đã commit.

### Bài 2. Tính nguyên tử chuyển tiền

**Đề bài:** An có 1000, Bình có 400. Chuyển 250 thành công trong một transaction thì hai số dư là bao nhiêu?

**Đáp án:** An 750, Bình 650. Tổng An+Bình ban đầu 1400 và sau chuyển vẫn 1400. Nếu rollback trước commit, trở về An 1000, Bình 400.

### Bài 3. Quan sát rồi ROLLBACK

~~~sql
BEGIN;

UPDATE tx_tai_khoan
SET so_du = so_du - 50
WHERE id = 1;

SELECT id, so_du
FROM tx_tai_khoan
WHERE id = 1;

ROLLBACK;

SELECT id, so_du
FROM tx_tai_khoan
WHERE id = 1;
~~~

**Đáp án:** SELECT đầu trong transaction thấy 950; SELECT sau ROLLBACK thấy 1000 khi dữ liệu mẫu chưa bị thay đổi trước đó.

### Bài 4. Vì sao UPDATE 0 hàng không tự rollback?

~~~sql
BEGIN;

UPDATE tx_tai_khoan
SET so_du = so_du - 2000
WHERE id = 1 AND so_du >= 2000
RETURNING id;

ROLLBACK;
~~~

**Đáp án:** UPDATE trả 0 hàng vì An chỉ có 1000. Không có lỗi bắt buộc; ứng dụng cần nhìn kết quả 0 và chủ động rollback nếu nghiệp vụ yêu cầu rút/chuyển đúng một tài khoản.

### Bài 5. Tìm lỗi chuyển tiền

**Đề bài:** Trong transaction, UPDATE An -200 khớp 0 hàng nhưng UPDATE Bình +200 khớp 1 hàng. Ứng dụng COMMIT vì không có exception. Có vấn đề gì?

**Đáp án:** Có. Transaction nguyên tử với **những thay đổi thực sự được thực hiện**, nhưng thiếu bước trừ; tổng số dư bị tăng 200. Phải kiểm tra affected rows = 1 ở cả hai bước và rollback nếu không đúng.

### Bài 6. Check constraint và rollback

~~~sql
BEGIN;

UPDATE tx_tai_khoan
SET so_du = so_du - 100
WHERE id = 1;

UPDATE tx_tai_khoan
SET so_du = -1
WHERE id = 2;

ROLLBACK;
~~~

**Đáp án:** UPDATE thứ hai vi phạm CHECK `so_du >= 0`, PostgreSQL báo lỗi và transaction cần rollback. Sau ROLLBACK, số dư An vẫn 1000, Bình 400.

### Bài 7. Đặt ranh giới tạo đơn–kho

**Đề bài:** tạo một đơn cho An và trừ 2 Sách SQL. Thao tác INSERT đơn thành công nhưng UPDATE kho trả 0 hàng. Có nên COMMIT không?

**Đáp án:** Không, nếu nghiệp vụ yêu cầu đơn phải được đảm bảo bằng tồn kho ngay khi tạo. ROLLBACK transaction bao trùm cả INSERT đơn, INSERT dòng đơn và UPDATE tồn kho, hoặc dùng chính sách đặt hàng chờ tồn kho được thiết kế rõ.

### Bài 8. SAVEPOINT giữ lại thay đổi nào?

~~~sql
BEGIN;
UPDATE tx_tai_khoan SET so_du = so_du + 10 WHERE id = 3;
SAVEPOINT sp;
UPDATE tx_tai_khoan SET so_du = so_du + 20 WHERE id = 3;
ROLLBACK TO SAVEPOINT sp;
SELECT so_du FROM tx_tai_khoan WHERE id = 3;
ROLLBACK;
~~~

**Đáp án:** SELECT trong transaction trả 160 (150 + 10). Sau ROLLBACK ngoài cùng, số dư Chi trở về 150.

### Bài 9. RELEASE SAVEPOINT có commit không?

**Đề bài:** Một transaction có SAVEPOINT, UPDATE +30, RELEASE SAVEPOINT, sau đó ROLLBACK ngoài cùng. UPDATE +30 còn không?

**Đáp án:** Không. RELEASE giải phóng savepoint nhưng không commit phần thay đổi độc lập. ROLLBACK ngoài cùng hủy thay đổi chưa commit.

### Bài 10. Ba connection hay một transaction?

**Đề bài:** Connection A trừ An, Connection B cộng Bình; hai bên đều commit riêng. Đây có phải một giao dịch nguyên tử chuyển tiền không?

**Đáp án:** Không. Đó là hai transaction riêng. Transaction A rollback không tự rollback B. Nếu cùng một RDBMS, hãy dùng một transaction/connection thích hợp; nếu khác hệ thống, cần mô hình giao dịch phân tán hoặc bù trừ.

### Bài 11. Dữ liệu thiếu không gây lỗi SQL

**Đề bài:** ứng dụng muốn cập nhật tài khoản ID 999 nhưng UPDATE WHERE id = 999 trả 0 hàng. Có nên trả kết quả “đã cập nhật” chỉ vì statement thực thi thành công?

**Đáp án:** Không. Cần kiểm tra số hàng/kết quả RETURNING và báo không tìm thấy tài khoản hoặc xử lý theo quy tắc nghiệp vụ.

### Bài 12. Ranh giới của email

**Đề bài:** INSERT đơn trong transaction, gửi email, UPDATE kho thất bại và ROLLBACK. Email có tự bị hủy không?

**Đáp án:** Không. Email là tác động ngoài DB. Có thể dùng outbox để chỉ ghi sự kiện email trong cùng DB transaction, sau đó worker gửi sau khi commit; worker vẫn cần idempotency/retry.

### Bài 13. Lost update

**Đề bài:** A và B cùng đọc số dư 1000, mỗi bên muốn rút 700, rồi ghi cố định 300. Vì sao sai?

**Đáp án:** Cả hai dùng giá trị cũ để tính và có nguy cơ ghi đè/làm mất một lần rút. Dùng UPDATE tương đối có điều kiện `so_du = so_du - 700 WHERE so_du >= 700`, kiểm tra đúng 1 hàng và xử lý concurrency/rollback.

### Bài 14. Không rõ COMMIT sau timeout

**Đề bài:** client gửi COMMIT chuyển tiền, sau đó mất kết nối, không nhận được phản hồi. Có thể kết luận chắc chắn rollback và gửi lại bằng mã mới không?

**Đáp án:** Không. COMMIT có thể đã thành công. Cần kiểm tra yêu cầu theo mã idempotency ổn định và dùng quy trình retry an toàn; mã mới có thể chuyển tiền hai lần.

### Bài 15. Khác biệt giữa atomicity và consistency

**Đề bài:** trong một transaction, An bị trừ 250, Bình chỉ được cộng 200, cả hai UPDATE thành công và COMMIT. Atomicity có bị phá không?

**Đáp án:** Không nhất thiết. Cả hai thay đổi được commit cùng nhau, nên atomicity không bị phá. Nhưng bất biến chuyển tiền bị sai vì thiếu 50; đó là lỗi logic/consistency, cần kiểm tra khoản ghi nợ và ghi có cân bằng.

### Bài 16. Xóa đơn có dòng con

**Đề bài:** bảng tx_dong_don có FK đến tx_don_hang, không ON DELETE CASCADE. Muốn xóa toàn bộ đơn đã phê duyệt cùng các dòng thì cần làm gì?

**Đáp án:** Kiểm tra tập đơn, quyền xóa và các phụ thuộc; xóa dòng con rồi xóa đơn cha trong một transaction (hoặc dùng CASCADE nếu schema/ nghiệp vụ thiết kế vậy), kiểm tra affected rows, rollback khi không đạt điều kiện. Không xóa cha trước và bỏ qua lỗi FK.

### Bài 17. PostgreSQL DDL và sequence

**Đề bài:** trong transaction tạo bảng mới, INSERT một hàng dùng identity, rồi ROLLBACK. Bảng có thể bị rollback; giá trị sequence vừa cấp có chắc được tái sử dụng không?

**Đáp án:** Với DDL phù hợp trong PostgreSQL, tạo bảng có thể được rollback. Nhưng không nên giả định mọi giá trị sequence đã cấp đều được trả lại khi transaction hủy. ID có thể có khoảng trống; đó không phải lỗi mất dữ liệu đã commit.

### Bài 18. Thiết kế ranh giới phù hợp

**Đề bài:** một API đặt hàng thực hiện tạo đơn, ghi dòng, trừ tồn kho, cập nhật lịch sử trong cùng PostgreSQL, rồi gửi SMS. Hãy đề xuất ranh giới.

**Đáp án:** Đặt **tạo đơn + dòng + trừ kho + audit/outbox** trong một database transaction; mỗi bước phải kiểm tra đủ kết quả. COMMIT nếu toàn bộ đúng, ROLLBACK nếu thất bại. Gửi SMS ngoài transaction sau commit hoặc thông qua worker đọc outbox; không coi SMS là thao tác rollback được bằng PostgreSQL.

## 29. Checklist thiết kế transaction nghiệp vụ

Trước khi hoàn thiện một workflow có nhiều thay đổi SQL, hãy tự hỏi:

1. **Một nghiệp vụ nào phải thành công hoặc thất bại nguyên khối?**
2. **Những bảng/hàng nào cùng thuộc bất biến ấy?**
3. **Transaction bắt đầu ở đâu và kết thúc ở đâu?**
4. **Autocommit đang bật hay tắt?**
5. **Các statement có dùng cùng Connection/transaction manager không?**
6. **Một bước trả 0 hàng có được coi là thất bại không?** Nếu có, kiểm tra và rollback chủ động.
7. **Có cần đúng số lượng và đúng tập khóa không?** Đừng chỉ kiểm tra query không exception.
8. **Ràng buộc CHECK/FK/UNIQUE đã có chưa?** Chúng bảo vệ cấu trúc, không thay thế nghiệp vụ.
9. **Có trạng thái/cột nào thay đổi giữa các statement do transaction khác không?**
10. **Cập nhật có điều kiện và khóa hàng có phù hợp không?**
11. **Có khả năng deadlock/serialization failure?** Nếu có, retry phải bao trùm transaction.
12. **Lỗi trong PostgreSQL có làm transaction aborted không?** Cần rollback/savepoint đúng.
13. **Có đang dùng SAVEPOINT mà tưởng nó là COMMIT độc lập không?**
14. **Bước nào là email, API thanh toán, file hay message broker ngoài DB?**
15. **Nếu response của COMMIT bị mất, có cách nhận diện lại giao dịch đã hoàn tất không?**
16. **Có mã request/khóa nghiệp vụ để xử lý retry không?**
17. **Transaction có bị giữ mở quá lâu khi gọi mạng hoặc chờ người dùng không?**
18. **DDL và sequence có quy tắc rollback nào khác không?**
19. **Nếu dùng DBMS khác, engine và cú pháp transaction đã được xác nhận chưa?**
20. **Khi commit xong, ứng dụng có trả đúng trạng thái và định danh nghiệp vụ không?**

## 30. Tổng kết

**Ranh giới giao dịch** xác định chính xác **những thay đổi nào được xử lý như một đơn vị**. Thuộc tính **nguyên tử** bảo đảm các thay đổi bên trong một transaction hợp lệ **được xác nhận cùng nhau hoặc bị hủy cùng nhau**.

- `BEGIN` mở transaction rõ ràng; `COMMIT` xác nhận thay đổi; `ROLLBACK` hủy thay đổi chưa commit.
- **Autocommit** có thể khiến các statement nối tiếp thuộc các transaction riêng. Nếu một nghiệp vụ cần nhiều bước cùng thành công, phải chủ động mở một transaction bao trùm tất cả bước liên quan.
- Chuyển tiền, tạo đơn–dòng đơn–trừ kho và xóa cha–con là những tình huống kinh điển cần ranh giới nguyên tử.
- **SQL không báo lỗi chưa chắc nghiệp vụ thành công**: UPDATE/DELETE/INSERT SELECT có thể tác động 0 hoặc ít hàng hơn dự kiến. Ứng dụng phải kiểm tra số hàng và tập khóa, rồi rollback khi không đạt yêu cầu.
- CHECK, FK, UNIQUE, điều kiện UPDATE và mức cô lập bảo vệ những khía cạnh khác nhau; **atomicity không tự bảo đảm dữ liệu đúng về số tiền, người nhận hay quyền thao tác**.
- `SAVEPOINT` cho phép quay lại một phần bên trong transaction, nhưng **không commit phần con độc lập**.
- Transaction gắn với connection/transaction manager; hai connection độc lập không tự có một transaction chung.
- Gửi email, gọi API ngoài, cấp sequence và DDL trong một số hệ quản trị có ngữ nghĩa khác thay đổi dữ liệu trong transaction; không giả định ROLLBACK hoàn tác mọi tác dụng phụ.
- Khi có đồng thời, cần điều kiện cập nhật đúng, cơ chế khóa/cô lập và retry hợp lý; khi response COMMIT không rõ, cần idempotency để tránh thực hiện nghiệp vụ hai lần.

Khi xác định đúng **bất biến nghiệp vụ → phạm vi thay đổi → ranh giới transaction → điều kiện xác nhận/hoàn tác**, bạn sẽ thiết kế được thao tác dữ liệu nhiều bước đáng tin cậy, thay vì chỉ đặt `BEGIN` và `COMMIT` quanh một nhóm câu SQL rồi hy vọng chúng luôn đúng.
