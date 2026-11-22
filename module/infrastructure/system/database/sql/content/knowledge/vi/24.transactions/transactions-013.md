# Thực hành chuyển tiền với kiểm tra bất biến và rollback trong SQL

Một giao dịch chuyển tiền tưởng như chỉ cần hai câu `UPDATE`:

~~~sql
UPDATE tai_khoan SET so_du = so_du - 250 WHERE id = 1;
UPDATE tai_khoan SET so_du = so_du + 250 WHERE id = 2;
~~~

Nhưng hai câu lệnh chạy được **không có nghĩa chuyển tiền đã đúng**. Điều gì xảy ra nếu người gửi không đủ tiền, người nhận không tồn tại, một câu UPDATE tác động 0 hàng, hoặc kết nối bị ngắt sau khi mới trừ người gửi? Điều gì xảy ra nếu cả hai câu cùng thành công nhưng số tiền trừ khác số tiền cộng?

Bài học này thực hành một quy trình cụ thể: **chuyển 250 đơn vị từ An sang Bình**, lưu lệnh chuyển tiền và hai bút toán biến động, kiểm tra các **bất biến dữ liệu**, rồi **COMMIT khi tất cả điều kiện thỏa** hoặc **ROLLBACK khi có bất kỳ thất bại nào**.

Các nội dung chính:

- Thiết lập dữ liệu và ràng buộc bằng PostgreSQL.
- Viết transaction `BEGIN ... COMMIT/ROLLBACK`.
- Kiểm tra số dư người gửi, tài khoản nhận và số hàng thực sự được cập nhật.
- Chứng minh **tổng số dư không đổi** và **ghi nợ bằng ghi có** trong phạm vi thao tác.
- Phân biệt **lỗi SQL** với **thất bại nghiệp vụ không gây lỗi**, đặc biệt là UPDATE tác động 0 hàng.
- Tự động từ chối và rollback bằng `RAISE EXCEPTION` trong PL/pgSQL.
- Chạy các tình huống giả lập: chuyển hợp lệ, không đủ tiền, nhận sai tài khoản, tài khoản bị khóa, mã giao dịch trùng và lỗi giữa chừng.
- Xử lý đồng thời, khóa hàng, thử lại giao dịch, savepoint và giao dịch JDBC trong ứng dụng Java.

Bài thuộc chương **Giao dịch SQL** của module **Database SQL**. Các câu SQL thực hành sử dụng **PostgreSQL** và **bảng tạm**, phù hợp chạy trong database học tập. Đây là mô hình giúp hiểu atomicity và bất biến, **không phải thiết kế đầy đủ cho hệ thống ngân hàng sản xuất** với sổ cái kép, nhiều loại tiền, quy định kế toán và tích hợp thanh toán bên ngoài.

## 1. Mục tiêu và tiêu chí thành công

Sau khi học, bạn có thể:

1. Diễn đạt đúng điều kiện chuyển tiền thành các **bất biến có thể kiểm tra**.
2. Tạo ba bảng liên quan: tài khoản, lệnh chuyển tiền, bút toán.
3. Đọc trạng thái **trước**, **trong** và **sau** transaction.
4. Dùng `UPDATE ... WHERE so_du >= so_tien RETURNING` để không tự ý cho số dư âm.
5. Kiểm tra **chính xác một hàng** ở mỗi UPDATE; không coi “không có exception” là thành công.
6. Xử lý lỗi ràng buộc `CHECK`, `FOREIGN KEY`, `UNIQUE` bằng rollback.
7. Viết một khối PL/pgSQL kiểm tra kết quả từng bước và `RAISE EXCEPTION` nếu bất biến không đạt.
8. Dùng `SAVEPOINT` và hiểu giới hạn của việc rollback từng phần.
9. Tránh lỗi khi hai giao dịch chuyển tiền chạy đồng thời.
10. Viết mã JDBC giữ cùng một `Connection` và chỉ `commit()` sau khi đủ điều kiện.
11. Giải thích sự khác nhau giữa **atomicity**, **isolation**, **idempotency** và các tác động ngoài database.
12. Tự thực hành các kịch bản có lời giải để kiểm tra hiểu biết.

## 2. Thế nào là bất biến khi chuyển tiền?

**Bất biến (*invariant*)** là điều kiện phải tiếp tục đúng ở một trạng thái hợp lệ của hệ thống, hoặc phải đúng tại ranh giới nghiệp vụ mà bạn xác định.

Xét hai tài khoản:

| Tài khoản | Số dư trước | Biến động | Số dư sau |
|---|---:|---:|---:|
| An (gửi) | 1000 | -250 | 750 |
| Bình (nhận) | 400 | +250 | 650 |
| **Tổng** | **1400** | **0** | **1400** |

Các điều kiện có thể diễn đạt:

**Bất biến A — không tạo hoặc làm mất tiền trong chuyển khoản nội bộ:**

\[
S_{\mathrm{An,trước}} + S_{\mathrm{Bình,trước}}
=
S_{\mathrm{An,sau}} + S_{\mathrm{Bình,sau}}
\]

Tức:

\[
1000 + 400 = 750 + 650 = 1400
\]

**Bất biến B — ghi nợ và ghi có phải bằng nhau:**

\[
\text{DEBIT} = \text{CREDIT} = 250
\]

Ở đây, cột số tiền bút toán được lưu **dương** và cột loại bút toán cho biết chiều ghi nợ/ghi có. Nếu dùng hệ thống ghi biến động có dấu, tổng đại số phải bằng 0:

\[
(-250) + 250 = 0
\]

**Bất biến C — tài khoản hợp lệ và đủ tiền:**

- Cả hai tài khoản tồn tại.
- Tài khoản gửi và nhận **khác nhau**.
- Cả hai đang ở trạng thái **ACTIVE**.
- Số tiền chuyển **lớn hơn 0**.
- Người gửi có số dư đủ để trừ.
- Số dư sau chuyển **không âm**.

**Bất biến D — ghi nhận đầy đủ một nghiệp vụ:**

- Có đúng một bản ghi lệnh chuyển tiền cho mã yêu cầu.
- Có một bút toán **DEBIT** cho tài khoản gửi.
- Có một bút toán **CREDIT** cho tài khoản nhận.
- Hai bút toán cùng mã giao dịch, cùng số tiền.
- Bản ghi lệnh, thay đổi số dư và bút toán phải **cùng tồn tại sau COMMIT**, hoặc **cùng không tồn tại nếu ROLLBACK**.

**Bất biến E — không xử lý trùng một yêu cầu:**

Một `ma_chuyen` đã được dùng để hoàn thành nghiệp vụ không được vô tình chuyển tiền thêm lần nữa khi client gửi lại.

### 2.1. Bất biến nào database tự kiểm tra?

| Điều kiện | Có thể đặt ở schema? | Có cần logic transaction? |
|---|---|---|
| Mỗi tài khoản có ID duy nhất | PRIMARY KEY | Không thay thế kiểm tra quyền |
| Số dư không âm | CHECK | Cần kiểm tra UPDATE có đủ số dư |
| Số tiền chuyển dương | CHECK | Cần xác thực request |
| ID gửi/nhận tồn tại | FOREIGN KEY | Cần kiểm tra trạng thái ACTIVE |
| ID gửi khác ID nhận | CHECK | Cần xác thực ngoài nếu có đặc thù |
| Mã chuyển không trùng | PRIMARY KEY/UNIQUE | Cần thiết kế retry/idempotency |
| Chính xác một UPDATE ghi nợ và một UPDATE ghi có | Không tự suy ra từ FK đơn giản | **Có**, kiểm tra row count |
| Hai bút toán tồn tại và cân bằng | UNIQUE/CHECK hỗ trợ một phần | **Có**, logic hoàn tất |
| Tổng số dư không đổi | Không tự được chứng minh bởi CHECK từng hàng | **Có**, kiểm tra số tiền/hiệu ứng |

**Atomicity** bảo đảm các thay đổi thuộc cùng transaction được xác nhận cùng nhau hoặc hủy cùng nhau. Nhưng atomicity **không tự kiểm tra bất biến**. Nếu UPDATE người gửi khớp 0 hàng và UPDATE người nhận khớp 1 hàng, COMMIT vẫn có thể thành công nếu ứng dụng không phát hiện.

## 3. Phân biệt giao dịch và nhóm câu SQL

Trong PostgreSQL:

~~~sql
BEGIN;

-- Các statement của một nghiệp vụ nằm ở đây.

COMMIT;
~~~

hoặc:

~~~sql
BEGIN;

-- Các statement cần hoàn tác.

ROLLBACK;
~~~

- `BEGIN` mở một transaction rõ ràng.
- `COMMIT` xác nhận các thay đổi trong transaction.
- `ROLLBACK` hủy các thay đổi chưa commit của transaction.
- Mỗi statement có thể thành công hoặc thất bại riêng, nhưng transaction là **ranh giới commit/rollback chung**.

Nếu autocommit bật và ứng dụng chạy hai UPDATE như hai statement riêng, hai statement có thể thuộc **hai transaction khác nhau**. Câu trừ tiền được commit rồi câu cộng tiền lỗi sẽ để lại mất cân bằng. Muốn **hai bước cùng thuộc một nghiệp vụ nguyên tử**, mở transaction bao trùm chúng.

### 3.1. Nguyên tử không có nghĩa tự động đúng về số tiền

Ví dụ cố ý sai:

~~~sql
BEGIN;

UPDATE tai_khoan
SET so_du = so_du - 250
WHERE id = 1;

UPDATE tai_khoan
SET so_du = so_du + 200
WHERE id = 2;

COMMIT;
~~~

Nếu mọi câu hợp lệ, hai thay đổi có thể cùng commit — tính nguyên tử vẫn được giữ — nhưng tổng số dư giảm 50. Do vậy cần kiểm tra **số tiền thực sự trừ/cộng**, chứ không chỉ xem có BEGIN/COMMIT.

### 3.2. Một statement khớp 0 hàng cũng là statement hợp lệ

~~~sql
UPDATE tai_khoan
SET so_du = so_du - 250
WHERE id = 999;
~~~

Nếu không tồn tại ID 999, UPDATE có thể trả **0 hàng**, không ném lỗi SQL. Transaction không tự hiểu “thiếu tài khoản gửi” là thất bại nghiệp vụ; ứng dụng phải chủ động nhận biết và rollback.

## 4. Tạo bộ dữ liệu thực hành PostgreSQL

Dùng một database thử nghiệm và **giữ cùng phiên kết nối** trong toàn bộ bài. Các bảng là `TEMP TABLE`, không xuất hiện ở kết nối khác và thường mất khi phiên kết thúc. Đừng chạy các ví dụ gây lỗi trên tài khoản/dữ liệu thật.

### 4.1. Bảng tài khoản

~~~sql
CREATE TEMP TABLE ct308_tai_khoan (
    id INTEGER PRIMARY KEY,
    chu_so_huu TEXT NOT NULL,
    so_du NUMERIC(14,2) NOT NULL CHECK (so_du >= 0),
    trang_thai TEXT NOT NULL
        CHECK (trang_thai IN ('ACTIVE', 'BLOCKED'))
);

INSERT INTO ct308_tai_khoan
    (id, chu_so_huu, so_du, trang_thai)
VALUES
    (1, 'An',   1000.00, 'ACTIVE'),
    (2, 'Bình',  400.00, 'ACTIVE'),
    (3, 'Chi',   150.00, 'BLOCKED');
~~~

Trạng thái ban đầu:

| id | chủ sở hữu | số dư | trạng thái |
|---:|---|---:|---|
| 1 | An | 1000.00 | ACTIVE |
| 2 | Bình | 400.00 | ACTIVE |
| 3 | Chi | 150.00 | BLOCKED |

**Tổng toàn bộ ba tài khoản** = 1000 + 400 + 150 = **1550**.

Ở ví dụ thành công, chỉ An và Bình được thay đổi; Chi vẫn có 150. Bất biến tổng toàn bộ hệ thống cũng là 1550, nhưng việc kiểm tra **tổng cặp tài khoản gửi–nhận** là cách dễ kiểm soát hơn khi có các transaction độc lập khác.

### 4.2. Bảng lệnh chuyển tiền

~~~sql
CREATE TEMP TABLE ct308_lenh_chuyen (
    ma_chuyen TEXT PRIMARY KEY,
    tai_khoan_gui INTEGER NOT NULL
        REFERENCES ct308_tai_khoan(id),
    tai_khoan_nhan INTEGER NOT NULL
        REFERENCES ct308_tai_khoan(id),
    so_tien NUMERIC(14,2) NOT NULL CHECK (so_tien > 0),
    tao_luc TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (tai_khoan_gui <> tai_khoan_nhan)
);
~~~

`ma_chuyen` là **mã yêu cầu nghiệp vụ** cần duy nhất. Cột này không phải sequence; ứng dụng phải tạo một token ổn định cho **cùng một yêu cầu** để hỗ trợ phát hiện retry.

Các FOREIGN KEY đảm bảo ID tài khoản tồn tại lúc ghi theo ngữ nghĩa ràng buộc, nhưng chưa đảm bảo tài khoản đang ACTIVE.

### 4.3. Bảng bút toán biến động

~~~sql
CREATE TEMP TABLE ct308_but_toan (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    ma_chuyen TEXT NOT NULL
        REFERENCES ct308_lenh_chuyen(ma_chuyen),
    tai_khoan_id INTEGER NOT NULL
        REFERENCES ct308_tai_khoan(id),
    loai TEXT NOT NULL CHECK (loai IN ('DEBIT', 'CREDIT')),
    so_tien NUMERIC(14,2) NOT NULL CHECK (so_tien > 0),
    ghi_luc TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (ma_chuyen, loai)
);
~~~

Với mỗi mã chuyển tiền, ta cho phép tối đa **một** DEBIT và tối đa **một** CREDIT. Đây là mô hình sổ ghi biến động đơn giản:

~~~text
ct308_lenh_chuyen
    ma_chuyen (PK)
         │
         └── ct308_but_toan
                 (DEBIT)
                 (CREDIT)

ct308_tai_khoan
    id (PK)
         │
         ├── lệnh gửi
         ├── lệnh nhận
         └── bút toán
~~~

Ràng buộc UNIQUE `(ma_chuyen, loai)` **không bắt buộc cả hai dòng cùng tồn tại**. Nó chỉ chặn trùng hai dòng cùng loại. Quy tắc “phải có một DEBIT và một CREDIT” còn cần logic transaction.

### 4.4. Kiểm tra trạng thái gốc

~~~sql
SELECT
    id,
    chu_so_huu,
    so_du,
    trang_thai
FROM ct308_tai_khoan
ORDER BY id;

SELECT
    COUNT(*) AS so_lenh_chuyen
FROM ct308_lenh_chuyen;

SELECT
    COUNT(*) AS so_but_toan
FROM ct308_but_toan;

SELECT
    SUM(so_du) AS tong_so_du
FROM ct308_tai_khoan;
~~~

Kết quả kỳ vọng:

- 3 tài khoản, số dư An 1000, Bình 400, Chi 150.
- Chưa có lệnh chuyển tiền: 0 hàng.
- Chưa có bút toán: 0 hàng.
- Tổng số dư: 1550.

**Quy ước thực hành:** các ví dụ thay đổi dữ liệu thường kết thúc bằng `ROLLBACK`. Nếu bạn thay bằng `COMMIT`, dữ liệu sẽ đổi và một số `ma_chuyen` cố định trong bài có thể bị trùng khi chạy lại. Khi ấy hãy tạo phiên thực hành mới với các bảng TEMP được thiết lập lại.

## 5. Xem trước nghiệp vụ trước khi ghi

Yêu cầu: chuyển `250.00` từ tài khoản ID 1 sang ID 2.

### 5.1. SELECT kiểm tra hai tài khoản

~~~sql
SELECT
    id,
    chu_so_huu,
    so_du,
    trang_thai
FROM ct308_tai_khoan
WHERE id IN (1, 2)
ORDER BY id;
~~~

Kết quả có đúng hai hàng An và Bình, đều ACTIVE.

### 5.2. SELECT mô phỏng số dư sau chuyển

~~~sql
SELECT
    id,
    chu_so_huu,
    so_du AS so_du_truoc,
    CASE
        WHEN id = 1 THEN so_du - 250.00
        WHEN id = 2 THEN so_du + 250.00
        ELSE so_du
    END AS so_du_du_kien
FROM ct308_tai_khoan
WHERE id IN (1, 2)
ORDER BY id;
~~~

| ID | Số dư trước | Số dư dự kiến |
|---:|---:|---:|
| 1 | 1000 | 750 |
| 2 | 400 | 650 |

Câu SELECT **chỉ tính giá trị**, chưa ghi vào bảng.

### 5.3. Kiểm tra bất biến dự kiến bằng truy vấn

~~~sql
SELECT
    SUM(so_du) AS tong_truoc,
    SUM(
        CASE
            WHEN id = 1 THEN so_du - 250.00
            WHEN id = 2 THEN so_du + 250.00
        END
    ) AS tong_du_kien
FROM ct308_tai_khoan
WHERE id IN (1, 2);
~~~

Kết quả: cả hai tổng bằng **1400**.

Tuy nhiên, tổng đúng chưa chứng minh đủ tất cả điều kiện. Nếu chỉ tìm thấy một tài khoản, biểu thức tổng có thể không thể hiện lỗi bằng cách bạn kỳ vọng. Cần **kiểm tra đúng hai tài khoản và đúng ID/trạng thái**, không chỉ một tổng.

### 5.4. Kiểm tra tiền đủ trước khi trừ

~~~sql
SELECT
    id,
    so_du,
    (so_du >= 250.00) AS du_tien,
    (trang_thai = 'ACTIVE') AS duoc_phep
FROM ct308_tai_khoan
WHERE id = 1;
~~~

Kết quả `du_tien = true` và `duoc_phep = true` trên dữ liệu gốc.

SELECT tiền kiểm hữu ích cho giao diện, nhưng không nên dựa hoàn toàn vào nó vì số dư có thể thay đổi trước UPDATE. Điều kiện **`so_du >= 250.00` phải được kiểm tra ngay trong UPDATE ghi nợ** hoặc dưới cơ chế khóa phù hợp.

## 6. Chuyển tiền thành công trong một transaction

Đây là tình huống cơ bản để nhìn thấy toàn bộ ranh giới.

### 6.1. Mở transaction và ghi lệnh

~~~sql
BEGIN;

INSERT INTO ct308_lenh_chuyen
    (ma_chuyen, tai_khoan_gui, tai_khoan_nhan, so_tien)
VALUES ('LAB-SUCCESS-01', 1, 2, 250.00)
RETURNING ma_chuyen, tai_khoan_gui, tai_khoan_nhan, so_tien;
~~~

Kết quả: một lệnh chuyển tiền chưa commit.

### 6.2. Trừ số dư người gửi bằng UPDATE có điều kiện

~~~sql
UPDATE ct308_tai_khoan
SET so_du = so_du - 250.00
WHERE id = 1
  AND trang_thai = 'ACTIVE'
  AND so_du >= 250.00
RETURNING id, chu_so_huu, so_du;
~~~

Kết quả đúng **một hàng**, ID 1 và số dư mới **750.00**.

Bốn điểm quan trọng:

- `id = 1` chỉ đúng người gửi.
- `trang_thai = 'ACTIVE'` cấm gửi từ tài khoản bị khóa.
- `so_du >= 250` không trừ khi thiếu tiền.
- `RETURNING` chứng minh hàng nào thực sự được UPDATE và giá trị sau cập nhật.

**Điều kiện nghiệp vụ:** nếu RETURNING không có đúng một hàng, bạn phải dừng và rollback; không chạy tiếp bước cộng người nhận chỉ vì SQL không báo lỗi.

### 6.3. Cộng số dư người nhận

~~~sql
UPDATE ct308_tai_khoan
SET so_du = so_du + 250.00
WHERE id = 2
  AND trang_thai = 'ACTIVE'
RETURNING id, chu_so_huu, so_du;
~~~

Kết quả đúng một hàng: ID 2, số dư **650.00**.

Nếu nhận 0 hàng vì người nhận không tồn tại hoặc bị BLOCKED, quy trình phải rollback cả bước trừ trước đó.

### 6.4. Ghi hai bút toán

~~~sql
INSERT INTO ct308_but_toan
    (ma_chuyen, tai_khoan_id, loai, so_tien)
VALUES
    ('LAB-SUCCESS-01', 1, 'DEBIT',  250.00),
    ('LAB-SUCCESS-01', 2, 'CREDIT', 250.00)
RETURNING ma_chuyen, tai_khoan_id, loai, so_tien;
~~~

Kết quả đúng hai dòng:

| ma_chuyen | tai_khoan_id | loai | so_tien |
|---|---:|---|---:|
| LAB-SUCCESS-01 | 1 | DEBIT | 250 |
| LAB-SUCCESS-01 | 2 | CREDIT | 250 |

### 6.5. Quan sát ngay trong transaction

~~~sql
SELECT id, chu_so_huu, so_du
FROM ct308_tai_khoan
ORDER BY id;

SELECT
    ma_chuyen,
    loai,
    tai_khoan_id,
    so_tien
FROM ct308_but_toan
WHERE ma_chuyen = 'LAB-SUCCESS-01'
ORDER BY loai;
~~~

Số dư trong kết nối hiện tại:

| Tài khoản | Số dư |
|---|---:|
| An | 750 |
| Bình | 650 |
| Chi | 150 |

Tổng vẫn bằng **1550**.

### 6.6. Hoàn tác bài thực hành

~~~sql
ROLLBACK;
~~~

Sau rollback, kiểm tra:

~~~sql
SELECT id, so_du
FROM ct308_tai_khoan
ORDER BY id;

SELECT COUNT(*) AS so_lenh
FROM ct308_lenh_chuyen
WHERE ma_chuyen = 'LAB-SUCCESS-01';

SELECT COUNT(*) AS so_but_toan
FROM ct308_but_toan
WHERE ma_chuyen = 'LAB-SUCCESS-01';
~~~

Kỳ vọng: số dư An/Bình quay về **1000/400**; không còn lệnh chuyển và bút toán mã `LAB-SUCCESS-01`.

### 6.7. Nếu muốn xác nhận thật sự bằng COMMIT?

Trong một phiên thử nghiệm mới, bạn có thể thay `ROLLBACK` bằng `COMMIT` **sau khi đã kiểm tra đầy đủ**. Khi COMMIT thành công:

- An còn 750.
- Bình có 650.
- Chi giữ 150.
- Có một lệnh chuyển và hai bút toán cùng mã.

`ROLLBACK` được chạy **sau** COMMIT ở một transaction khác không thể hủy lệnh đã commit. Vì vậy tài liệu mặc định ROLLBACK để bạn có thể lặp bài.

## 7. Kiểm tra tổng số dư như thế nào?

Với chuyển khoản nội bộ không thu phí trong ví dụ:

\[
T_{\text{trước}} = T_{\text{sau}}
\]

Trước: `1000 + 400 + 150 = 1550`. Trong transaction thành công: `750 + 650 + 150 = 1550`.

### 7.1. Truy vấn tổng toàn bộ

~~~sql
SELECT
    COUNT(*) AS so_tai_khoan,
    SUM(so_du) AS tong_so_du
FROM ct308_tai_khoan;
~~~

Sau hai UPDATE thành công nhưng trước rollback, kết quả là 3 tài khoản, tổng **1550**.

### 7.2. Truy vấn tổng của riêng cặp gửi–nhận

~~~sql
SELECT
    SUM(so_du) AS tong_cap_tai_khoan
FROM ct308_tai_khoan
WHERE id IN (1, 2);
~~~

Kết quả trước và trong giao dịch là **1400**. Cách này tập trung vào hai tài khoản chịu tác động, tránh dùng thay đổi ở những tài khoản khác làm nhiễu minh họa.

### 7.3. Một tổng bằng nhau chưa đủ

Giả sử bạn trừ nhầm 250 của An, cộng nhầm 250 cho Chi thay vì Bình. Tổng toàn bộ vẫn là 1550, nhưng giao dịch **đã chuyển nhầm người nhận**.

Vì vậy, kiểm tra bất biến cần nhiều tầng:

- Tổng cặp gửi–nhận không đổi.
- **Đúng ID người gửi và ID người nhận**.
- Số dư mỗi bên thay đổi đúng dấu, đúng lượng.
- Bút toán có loại, mã, số tiền và tài khoản tương ứng.
- Mỗi UPDATE thật sự tác động đúng một hàng.

Tổng cộng không đổi là một điều kiện hữu ích, **không phải điều kiện đủ** để xác nhận giao dịch đúng.

### 7.4. Kiểm tra tổng ở môi trường có nhiều transaction

Trên hệ thống thật, một SELECT tổng toàn bộ trước và sau vài statement ở mức cô lập `READ COMMITTED` có thể nhìn thấy thay đổi được commit từ các transaction khác. Vì vậy, phép so tổng toàn hệ thống trong hai SELECT rời nhau **không phải bằng chứng độc lập tuyệt đối** rằng transaction của bạn cân bằng.

Đối với giao dịch đã khóa đúng cặp tài khoản, có thể kiểm tra tổng cặp dưới điều kiện khóa phù hợp và dùng chính kết quả UPDATE để xác minh. Trong hệ thống sổ cái, nên có cơ chế đối soát chuyên biệt thay vì dùng tổng tức thời toàn bảng làm chốt an toàn duy nhất.

## 8. Kiểm tra ghi nợ và ghi có bằng truy vấn tổng hợp

Với bút toán đã ghi trong transaction:

~~~sql
SELECT
    ma_chuyen,
    COUNT(*) AS so_but_toan,
    COUNT(*) FILTER (
        WHERE loai = 'DEBIT'
    ) AS so_debit,
    COUNT(*) FILTER (
        WHERE loai = 'CREDIT'
    ) AS so_credit,
    SUM(so_tien) FILTER (
        WHERE loai = 'DEBIT'
    ) AS tong_debit,
    SUM(so_tien) FILTER (
        WHERE loai = 'CREDIT'
    ) AS tong_credit
FROM ct308_but_toan
WHERE ma_chuyen = 'LAB-SUCCESS-01'
GROUP BY ma_chuyen;
~~~

Với dữ liệu đã chèn và chưa rollback:

| Số bút toán | Số DEBIT | Số CREDIT | Tổng DEBIT | Tổng CREDIT |
|---:|---:|---:|---:|---:|
| 2 | 1 | 1 | 250 | 250 |

### 8.1. Bất biến bút toán cân bằng

~~~sql
SELECT
    ma_chuyen,
    SUM(
        CASE
            WHEN loai = 'CREDIT' THEN so_tien
            WHEN loai = 'DEBIT' THEN -so_tien
            ELSE 0
        END
    ) AS chenhlech
FROM ct308_but_toan
WHERE ma_chuyen = 'LAB-SUCCESS-01'
GROUP BY ma_chuyen;
~~~

Kết quả đúng: `chenhlech = 0`.

Nhưng **chênh lệch 0 không tự chứng minh đủ hai dòng**: tập bút toán rỗng không có hàng GROUP BY, hoặc hai dòng sai tài khoản có thể vẫn cân bằng. Cần kiểm tra đủ số lượng, đúng loại, đúng tài khoản và đúng số tiền trong lệnh gốc.

### 8.2. Truy vấn đối chiếu bút toán với lệnh chuyển

~~~sql
SELECT
    lc.ma_chuyen,
    lc.tai_khoan_gui,
    lc.tai_khoan_nhan,
    lc.so_tien AS so_tien_lenh,
    COUNT(bt.id) AS so_but_toan,
    COUNT(bt.id) FILTER (
        WHERE bt.loai = 'DEBIT'
          AND bt.tai_khoan_id = lc.tai_khoan_gui
          AND bt.so_tien = lc.so_tien
    ) AS debit_dung,
    COUNT(bt.id) FILTER (
        WHERE bt.loai = 'CREDIT'
          AND bt.tai_khoan_id = lc.tai_khoan_nhan
          AND bt.so_tien = lc.so_tien
    ) AS credit_dung
FROM ct308_lenh_chuyen AS lc
LEFT JOIN ct308_but_toan AS bt
    ON bt.ma_chuyen = lc.ma_chuyen
WHERE lc.ma_chuyen = 'LAB-SUCCESS-01'
GROUP BY
    lc.ma_chuyen,
    lc.tai_khoan_gui,
    lc.tai_khoan_nhan,
    lc.so_tien;
~~~

Một lệnh hợp lệ theo mô hình này phải có:

- `so_but_toan = 2`.
- `debit_dung = 1`.
- `credit_dung = 1`.

Đây là một ví dụ minh họa đối soát. Hệ thống thực thường còn có trạng thái xử lý, phí, tiền tệ, lịch sử bất biến và yêu cầu audit khắt khe hơn.

## 9. Rủi ro lớn: UPDATE 0 hàng không gây lỗi

Giả sử An có 1000 nhưng người dùng yêu cầu chuyển **2000**.

### 9.1. UPDATE có điều kiện trả 0 hàng

~~~sql
BEGIN;

UPDATE ct308_tai_khoan
SET so_du = so_du - 2000.00
WHERE id = 1
  AND trang_thai = 'ACTIVE'
  AND so_du >= 2000.00
RETURNING id, so_du;

ROLLBACK;
~~~

Không có hàng RETURNING, vì điều kiện đủ tiền không đạt. Đây thường là **statement hợp lệ**, không phải một exception tự động.

### 9.2. Một ví dụ nguy hiểm nếu bỏ qua row count

~~~sql
-- KHÔNG dùng để COMMIT trong nghiệp vụ thật!
BEGIN;

UPDATE ct308_tai_khoan
SET so_du = so_du - 2000
WHERE id = 1 AND so_du >= 2000;
-- 0 hàng

UPDATE ct308_tai_khoan
SET so_du = so_du + 2000
WHERE id = 2;
-- 1 hàng

-- Ví dụ an toàn: ROLLBACK, tuyệt đối không COMMIT.
ROLLBACK;
~~~

Nếu COMMIT quy trình sai này, Bình sẽ tăng 2000 còn An không giảm. Database **không vi phạm atomicity**: nó commit những thay đổi thực sự được thực hiện trong transaction, nhưng nghiệp vụ đã sai.

### 9.3. Điều kiện cần để COMMIT

Trong ví dụ, tối thiểu phải đúng:

~~~text
Rows INSERT lệnh = 1
Rows UPDATE gửi = 1
Rows UPDATE nhận = 1
Rows INSERT bút toán = 2
DEBIT đúng tài khoản gửi và đúng tiền
CREDIT đúng tài khoản nhận và đúng tiền
Tổng cặp gửi–nhận không đổi
Không có lỗi ràng buộc hoặc vi phạm nghiệp vụ
→ mới COMMIT
~~~

**Nếu một điều kiện không đạt, ROLLBACK.** Đừng chỉ kiểm tra việc statement có thông báo “success” từ SQL client.

## 10. Để SQL tự từ chối: kiểm tra ROW_COUNT và RAISE EXCEPTION

Trong một ứng dụng có nhiều statement, bạn thường kiểm tra kết quả bằng JDBC hoặc transaction manager. Khi muốn thử nghiệm logic **ngay trong PostgreSQL**, có thể dùng một khối **PL/pgSQL `DO`** để kiểm tra số hàng và ném lỗi khi thất bại.

`DO` không tự mở một transaction mới nếu nó chạy trong `BEGIN ...`. Các lệnh trong DO thuộc cùng transaction hiện tại. Khi một `RAISE EXCEPTION` không được bắt làm statement thất bại, PostgreSQL đánh dấu transaction hiện tại lỗi và bạn cần `ROLLBACK`.

### 10.1. Khối kiểm tra chuyển tiền an toàn

Ví dụ đầy đủ dưới đây dùng mã `LAB-CHECKED-01`, chuyển 250 từ An sang Bình. Nó khóa cặp tài khoản theo thứ tự ID, kiểm tra số dư tổng cặp, ghi một lệnh chuyển, thực hiện hai UPDATE có điều kiện, ghi đủ hai bút toán và ném lỗi nếu bất kỳ điều kiện nào không đúng.

~~~sql
BEGIN;

DO $$
DECLARE
    v_ma TEXT := 'LAB-CHECKED-01';
    v_gui INTEGER := 1;
    v_nhan INTEGER := 2;
    v_tien NUMERIC(14,2) := 250.00;

    v_so_hang INTEGER;
    v_tong_truoc NUMERIC(14,2);
    v_tong_sau NUMERIC(14,2);
BEGIN
    -- Kiểm tra đầu vào trước khi ghi.
    IF v_tien <= 0 THEN
        RAISE EXCEPTION 'Số tiền phải dương';
    END IF;

    IF v_gui = v_nhan THEN
        RAISE EXCEPTION 'Không thể chuyển cho cùng tài khoản';
    END IF;

    -- Khóa những tài khoản hiện tồn tại theo thứ tự ID.
    -- Các UPDATE bên dưới vẫn phải kiểm tra đúng 1 hàng.
    PERFORM id
    FROM ct308_tai_khoan
    WHERE id IN (v_gui, v_nhan)
    ORDER BY id
    FOR UPDATE;

    -- Tổng cặp trước thay đổi, sau khi đã khóa.
    SELECT SUM(so_du)
    INTO v_tong_truoc
    FROM ct308_tai_khoan
    WHERE id IN (v_gui, v_nhan);

    -- Mã lệnh PRIMARY KEY: trùng mã sẽ gây lỗi.
    INSERT INTO ct308_lenh_chuyen
        (ma_chuyen, tai_khoan_gui, tai_khoan_nhan, so_tien)
    VALUES
        (v_ma, v_gui, v_nhan, v_tien);

    -- Trừ đúng người gửi, chỉ khi ACTIVE và đủ tiền.
    UPDATE ct308_tai_khoan
    SET so_du = so_du - v_tien
    WHERE id = v_gui
      AND trang_thai = 'ACTIVE'
      AND so_du >= v_tien;

    GET DIAGNOSTICS v_so_hang = ROW_COUNT;

    IF v_so_hang <> 1 THEN
        RAISE EXCEPTION
            'Không trừ được đúng một tài khoản gửi';
    END IF;

    -- Cộng đúng người nhận, chỉ khi ACTIVE.
    UPDATE ct308_tai_khoan
    SET so_du = so_du + v_tien
    WHERE id = v_nhan
      AND trang_thai = 'ACTIVE';

    GET DIAGNOSTICS v_so_hang = ROW_COUNT;

    IF v_so_hang <> 1 THEN
        RAISE EXCEPTION
            'Không cộng được đúng một tài khoản nhận';
    END IF;

    -- Ghi 2 dòng biến động cùng mã và cùng số tiền.
    INSERT INTO ct308_but_toan
        (ma_chuyen, tai_khoan_id, loai, so_tien)
    VALUES
        (v_ma, v_gui,  'DEBIT',  v_tien),
        (v_ma, v_nhan, 'CREDIT', v_tien);

    GET DIAGNOSTICS v_so_hang = ROW_COUNT;

    IF v_so_hang <> 2 THEN
        RAISE EXCEPTION 'Không ghi đủ hai bút toán';
    END IF;

    -- Kiểm tra bất biến tổng cặp tài khoản.
    SELECT SUM(so_du)
    INTO v_tong_sau
    FROM ct308_tai_khoan
    WHERE id IN (v_gui, v_nhan);

    IF v_tong_truoc IS DISTINCT FROM v_tong_sau THEN
        RAISE EXCEPTION
            'Bất biến tổng số dư bị phá: % <> %',
            v_tong_truoc,
            v_tong_sau;
    END IF;

    RAISE NOTICE
        'Đã thực hiện trong transaction: %, tổng cặp = %',
        v_ma,
        v_tong_sau;
END
$$;

-- Cùng connection có thể kiểm tra thay đổi chưa commit.
SELECT id, chu_so_huu, so_du
FROM ct308_tai_khoan
ORDER BY id;

SELECT ma_chuyen, tai_khoan_id, loai, so_tien
FROM ct308_but_toan
WHERE ma_chuyen = 'LAB-CHECKED-01'
ORDER BY loai;

-- Trong bài thực hành, không giữ thay đổi:
ROLLBACK;
~~~

### 10.2. Kết quả thành công dự kiến

Sau khối DO nhưng trước ROLLBACK:

- An: 750.
- Bình: 650.
- Chi: 150.
- Tổng cặp An–Bình: 1400, bằng trước.
- Lệnh chuyển `LAB-CHECKED-01`: 1 hàng.
- Hai bút toán: DEBIT 250 ở An và CREDIT 250 ở Bình.

Sau ROLLBACK: số dư và số hàng quay lại dữ liệu ban đầu. Những giá trị identity đã cấp cho bút toán có thể không được hoàn trả vào sequence.

### 10.3. Vì sao GET DIAGNOSTICS cần nằm ngay sau UPDATE?

`ROW_COUNT` trong PL/pgSQL chứa số hàng xử lý bởi **lệnh SQL gần nhất** có liên quan. Nếu bạn thực thi một SELECT/UPDATE/INSERT khác rồi mới đọc ROW_COUNT, con số có thể không còn là số hàng của UPDATE cần kiểm tra.

Đúng:

~~~sql
UPDATE ...;
GET DIAGNOSTICS v_so_hang = ROW_COUNT;
IF v_so_hang <> 1 THEN
    RAISE EXCEPTION 'Sai số hàng';
END IF;
~~~

Đoạn trên là **mẫu rút gọn**, không phải statement có thể chạy nguyên văn. Trong khối DO hoàn chỉnh, UPDATE phải có tên bảng, SET và WHERE cụ thể.

### 10.4. Vì sao dùng IS DISTINCT FROM?

Hai biểu thức so sánh:

~~~sql
v_tong_truoc <> v_tong_sau
~~~

và:

~~~sql
v_tong_truoc IS DISTINCT FROM v_tong_sau
~~~

khác nhau khi một trong hai giá trị là NULL. `IS DISTINCT FROM` trong PostgreSQL cho kết quả boolean xác định khi xét NULL. Bài sử dụng nó làm kiểm tra bất biến để không vô tình bỏ qua một trạng thái không có tổng như mong đợi.

### 10.5. Việc khóa có ý nghĩa gì?

`FOR UPDATE` yêu cầu khóa hàng đã chọn trong transaction, giúp hạn chế transaction khác sửa cùng hàng khi khóa còn hiệu lực. `ORDER BY id` đặt mục tiêu khóa theo thứ tự ổn định nhằm giảm một số nguy cơ deadlock khi nhiều thao tác chuyển tiền giữa hai tài khoản.

Tuy nhiên, việc khóa các hàng hiện tồn tại không tự bảo đảm mọi nghiệp vụ phân tán hay mọi tình huống concurrency đều an toàn. Các UPDATE có điều kiện, row count, khóa và chính sách thử lại **bổ sung cho nhau**.

### 10.6. Tại sao không viết COMMIT bên trong DO?

Khối `DO` chạy trong transaction do `BEGIN` ngoài mở. Bài không dùng `COMMIT`/`ROLLBACK` bên trong DO, vì việc kết thúc transaction phải được điều phối ở ranh giới đã thiết kế; PostgreSQL có giới hạn đối với transaction control trong DO khi chạy ở transaction block.

Khi khối DO hoàn tất mà không lỗi, ứng dụng hoặc người vận hành **vẫn có quyền lựa chọn** COMMIT hay ROLLBACK. Ví dụ thực hành mặc định ROLLBACK.

## 11. Thử thất bại: không đủ tiền và rollback toàn bộ

Ta muốn chuyển **2000** từ An sang Bình, trong khi An chỉ có 1000.

### 11.1. Thay tham số trong khối DO đã học

Trong ví dụ khối DO ở mục 10, đặt:

~~~sql
v_ma TEXT := 'LAB-INSUFFICIENT-01';
v_gui INTEGER := 1;
v_nhan INTEGER := 2;
v_tien NUMERIC(14,2) := 2000.00;
~~~

Đây là những dòng khai báo thay thế **ở phần DECLARE**, không phải SQL độc lập. Giữ các bước kiểm tra còn lại.

Diễn biến:

1. Khóa An và Bình.
2. Ghi lệnh chuyển trong transaction.
3. UPDATE người gửi có điều kiện `so_du >= 2000`.
4. Không hàng nào khớp.
5. `ROW_COUNT = 0`.
6. `RAISE EXCEPTION 'Không trừ được...'`.
7. PostgreSQL đánh dấu transaction lỗi; phải ROLLBACK.
8. Sau ROLLBACK, lệnh chuyển cũng không tồn tại.

### 11.2. Không nên chỉ kiểm tra SELECT trước

~~~sql
SELECT so_du FROM ct308_tai_khoan WHERE id = 1;
~~~

Bạn có thể đọc 1000 rồi xác định thiếu tiền, nhưng kết quả SELECT có thể cũ nếu có transaction khác. Điều kiện `WHERE so_du >= v_tien` **ngay trong UPDATE** giúp kiểm tra tại điểm ghi, không phải chỉ trong màn hình xem trước.

### 11.3. Trạng thái sau lỗi

Nếu chạy một DO có `RAISE EXCEPTION` trong transaction PostgreSQL, những câu kế tiếp có thể báo:

~~~text
current transaction is aborted,
commands ignored until end of transaction block
~~~

Hãy gửi:

~~~sql
ROLLBACK;
~~~

trong cùng kết nối. Nếu trình SQL client tự dừng kịch bản khi thấy lỗi, hãy thực hiện ROLLBACK riêng thay vì cho rằng script đã chạy đến dòng cuối.

### 11.4. Cần kiểm tra kết quả sau rollback

~~~sql
SELECT id, so_du
FROM ct308_tai_khoan
ORDER BY id;

SELECT COUNT(*)
FROM ct308_lenh_chuyen
WHERE ma_chuyen = 'LAB-INSUFFICIENT-01';
~~~

Kết quả kỳ vọng: An vẫn 1000, Bình 400, không có lệnh chuyển mới.

## 12. Thử thất bại: người nhận không tồn tại

Tình huống: chuyển 50 từ An sang tài khoản ID 999, không có trong bảng.

### 12.1. Khóa ngoại chặn bản ghi lệnh

~~~sql
BEGIN;

INSERT INTO ct308_lenh_chuyen
    (ma_chuyen, tai_khoan_gui, tai_khoan_nhan, so_tien)
VALUES ('LAB-NO-RECEIVER-01', 1, 999, 50.00);

-- FK tai_khoan_nhan từ chối vì ID 999 không tồn tại.
-- Sau lỗi, kết thúc transaction:
ROLLBACK;
~~~

PostgreSQL sẽ báo lỗi FOREIGN KEY (thường SQLSTATE `23503`). Không có yêu cầu chuyển hợp lệ được ghi. Nếu có những UPDATE trước lỗi ở cùng transaction, ROLLBACK sẽ hoàn tác chúng.

### 12.2. Nếu không có FK, row count còn quan trọng hơn

Giả sử bảng lệnh chuyển không khai báo FK và ứng dụng:

~~~sql
UPDATE ct308_tai_khoan
SET so_du = so_du + 50
WHERE id = 999
RETURNING id;
~~~

Truy vấn này đơn giản trả 0 hàng. Nếu chương trình không kiểm tra, nó có thể commit bước trừ An mà không cộng ai.

**Bảo vệ nhiều tầng:**

- FOREIGN KEY phát hiện mã tài khoản không tồn tại ở bảng phụ thuộc.
- UPDATE có điều kiện và `RETURNING` xác minh bản ghi bị thay đổi.
- Logic transaction dừng/rollback khi số hàng khác kỳ vọng.
- Phân quyền kiểm tra người yêu cầu có được chuyển từ/đến tài khoản ấy không.

FK không xác thực quyền; ID tồn tại không tự có nghĩa người dùng được phép thao tác.

## 13. Thử thất bại: tài khoản bị khóa

Tài khoản Chi (ID 3) có `trang_thai = 'BLOCKED'` và số dư 150.

### 13.1. Kiểm tra trước

~~~sql
SELECT
    id,
    chu_so_huu,
    so_du,
    trang_thai
FROM ct308_tai_khoan
WHERE id = 3;
~~~

Kết quả: Chi, 150, BLOCKED.

### 13.2. Không được ghi nợ tài khoản BLOCKED

~~~sql
BEGIN;

UPDATE ct308_tai_khoan
SET so_du = so_du - 50
WHERE id = 3
  AND trang_thai = 'ACTIVE'
  AND so_du >= 50
RETURNING id, so_du;

ROLLBACK;
~~~

RETURNING trả 0 hàng. Bài toán nghiệp vụ không được tiếp tục cộng tiền vào người nhận.

### 13.3. Tài khoản nhận bị khóa cũng phải được kiểm tra

Nếu chuyển từ An sang Chi, UPDATE người gửi có thể thành công nhưng UPDATE nhận:

~~~sql
UPDATE ct308_tai_khoan
SET so_du = so_du + 50
WHERE id = 3
  AND trang_thai = 'ACTIVE'
RETURNING id;
~~~

trả 0 hàng. Trong một transaction có đầy đủ kiểm tra, ứng dụng phải rollback bước trừ An đã chạy trước.

Điều kiện về trạng thái ở bên nhận có thể khác giữa các nghiệp vụ (có tổ chức cho phép nhận vào tài khoản tạm khóa hay không). Bài giả định **cả hai phía phải ACTIVE**; cần giữ quy tắc này nhất quán giữa kiểm tra và UPDATE.

## 14. Thử thất bại: lỗi xuất hiện sau bước ghi nợ

Một transaction có thể trừ tiền thành công rồi gặp lỗi khi ghi bút toán.

### 14.1. Cố ý tạo lỗi CHECK để thấy tính nguyên tử

~~~sql
BEGIN;

UPDATE ct308_tai_khoan
SET so_du = so_du - 100
WHERE id = 1
  AND so_du >= 100
RETURNING id, so_du;
-- An: 1000 → 900 trong transaction.

INSERT INTO ct308_lenh_chuyen
    (ma_chuyen, tai_khoan_gui, tai_khoan_nhan, so_tien)
VALUES ('LAB-FAIL-MIDDLE-01', 1, 2, 100);

-- Số tiền bút toán âm, vi phạm CHECK (so_tien > 0).
INSERT INTO ct308_but_toan
    (ma_chuyen, tai_khoan_id, loai, so_tien)
VALUES ('LAB-FAIL-MIDDLE-01', 1, 'DEBIT', -100);

ROLLBACK;
~~~

INSERT bút toán cuối vi phạm CHECK. PostgreSQL đánh dấu transaction bị lỗi; ROLLBACK hoàn tác cả UPDATE đầu và INSERT lệnh chuyển.

### 14.2. Vì sao không tiếp tục cộng Bình sau lỗi?

Khi transaction đã ở trạng thái aborted, PostgreSQL không thực thi các statement tiếp theo theo cách thông thường cho đến khi rollback hoặc phục hồi về savepoint hợp lệ. Đúng hơn nữa, nghiệp vụ chuyển tiền **đã thất bại** vì không thể ghi nhật ký hợp lệ, nên nên hủy toàn bộ thay đổi.

### 14.3. Kiểm tra lại trạng thái

~~~sql
SELECT id, so_du
FROM ct308_tai_khoan
ORDER BY id;

SELECT COUNT(*)
FROM ct308_lenh_chuyen
WHERE ma_chuyen = 'LAB-FAIL-MIDDLE-01';
~~~

Sau rollback: An 1000, Bình 400, không có lệnh mã thử lỗi.

## 15. Thử thất bại: mã giao dịch trùng và idempotency

Để ứng dụng không chuyển tiền hai lần khi người dùng nhấn nút hai lần hoặc mạng chập chờn, mỗi yêu cầu nên có **mã idempotency** được quản lý rõ.

### 15.1. UNIQUE bảo vệ một mã khỏi trùng lặp

`ct308_lenh_chuyen.ma_chuyen` là PRIMARY KEY. Nếu một transaction đã commit mã `PAY-REQ-001`, lần INSERT tiếp theo với cùng mã sẽ vi phạm UNIQUE, thay vì tạo bản ghi lệnh thứ hai.

Ví dụ minh họa thứ tự:

~~~text
Lần đầu:
  BEGIN
  INSERT lệnh PAY-REQ-001
  UPDATE số dư / INSERT bút toán
  COMMIT

Lần gửi lại:
  BEGIN
  INSERT lệnh PAY-REQ-001
  → xung đột PRIMARY KEY
  ROLLBACK / nhánh xử lý yêu cầu đã tồn tại
~~~

### 15.2. ON CONFLICT DO NOTHING không tự là “chuyển lại an toàn”

~~~sql
INSERT INTO ct308_lenh_chuyen
    (ma_chuyen, tai_khoan_gui, tai_khoan_nhan, so_tien)
VALUES ('PAY-REQ-001', 1, 2, 250)
ON CONFLICT (ma_chuyen) DO NOTHING
RETURNING ma_chuyen;
~~~

Nếu mã đã tồn tại, `RETURNING` trả **0 hàng**. Không được sau đó vẫn chạy hai UPDATE, vì như vậy **có thể chuyển tiền thêm lần nữa** dù INSERT bị bỏ qua.

Quy tắc thực hành:

- Có đúng một hàng INSERT mới → mới xét thực hiện chuyển tiền, với transaction đủ điều kiện.
- Không có hàng vì conflict → không tự chuyển lại, chuyển sang nhánh **xác minh yêu cầu cũ**.
- Nội dung request mới trùng mã nhưng khác tài khoản/số tiền → báo xung đột nghiệp vụ; không coi là retry hợp lệ.

### 15.3. Mã giao dịch không bảo đảm mọi thứ đã hoàn tất nếu quy trình chia transaction

Nếu lệnh chuyển tiền được commit trước nhưng hai UPDATE ở transaction khác, bạn có thể có mã lệnh tồn tại mà tiền chưa chuyển. Vì vậy, **mã yêu cầu, số dư và bút toán phải cùng thuộc transaction nghiệp vụ**.

Idempotency là một phần của thiết kế **xử lý thử lại**; nó không thay thế atomicity.

### 15.4. Khi mất phản hồi COMMIT

~~~text
Ứng dụng gửi COMMIT
Database có thể đã commit
Mạng đứt trước khi client nhận phản hồi
Ứng dụng không biết chắc thành công hay thất bại
~~~

Không được tự suy luận “timeout nghĩa là rollback” rồi chuyển lại bằng mã mới. Cần dùng **cùng mã idempotency** và một quy trình tra cứu/xác minh kết quả. Thông tin truy vấn cũng phải được phân quyền; không trả chi tiết giao dịch của người khác chỉ vì họ biết mã.

## 16. Concurrent transfers: hai giao dịch cùng trừ một tài khoản

Giả sử An có 1000; hai request đồng thời:

- Giao dịch A chuyển 700 từ An sang Bình.
- Giao dịch B chuyển 500 từ An sang Chi (giả sử Chi được phép nhận trong ví dụ cạnh tranh này).

Tổng hai yêu cầu là 1200, vượt số dư.

### 16.1. Cách sai: đọc số dư rồi ghi giá trị tính sẵn

~~~text
A: SELECT so_du → 1000
B: SELECT so_du → 1000
A: tính 1000 - 700 = 300
B: tính 1000 - 500 = 500
A: UPDATE SET so_du = 300
B: UPDATE SET so_du = 500
~~~

Nếu không kiểm soát đồng thời, ứng dụng có thể ghi đè kết quả dựa trên số dư cũ (*lost update*) hoặc ghi nhận cả hai giao dịch mà số dư không phản ánh đầy đủ.

### 16.2. Cách phù hợp hơn: UPDATE tương đối có điều kiện

~~~sql
UPDATE ct308_tai_khoan
SET so_du = so_du - 700
WHERE id = 1
  AND trang_thai = 'ACTIVE'
  AND so_du >= 700
RETURNING id, so_du;
~~~

và giao dịch cạnh tranh:

~~~sql
UPDATE ct308_tai_khoan
SET so_du = so_du - 500
WHERE id = 1
  AND trang_thai = 'ACTIVE'
  AND so_du >= 500
RETURNING id, so_du;
~~~

Với PostgreSQL ở mức cô lập thông dụng, các UPDATE trên cùng hàng phải phối hợp khóa hàng và kiểm tra điều kiện theo quy tắc isolation. Nếu A trừ 700 và commit trước, B không còn đủ 500: UPDATE B có thể trả **0 hàng** sau khi chờ; ứng dụng phải ROLLBACK toàn bộ chuyển tiền B. Nếu B thành công trước, A có thể bị từ chối tương ứng.

**Không giả định cả hai thành công chỉ vì trước đó đều SELECT ra số dư 1000.**

### 16.3. Không thể thực hành hai connection trên cùng TEMP TABLE

Bảng `ct308_tai_khoan` của bài là bảng TEMP, chỉ thuộc session tạo ra. Connection B **không nhìn thấy** nó. Nếu muốn chạy bài cạnh tranh thực sự với hai kết nối, hãy tạo bảng thử nghiệm **thường** trong schema sandbox được phép, chuẩn bị dữ liệu hai bên cùng thấy, rồi dọn dẹp theo quy trình sau khi thực hành.

Không thử trên tài khoản thật hay database sản xuất.

### 16.4. Thứ tự khóa để giảm deadlock

Hai giao dịch chuyển hai chiều An↔Bình có thể lần lượt khóa các hàng theo thứ tự ngược nhau, dẫn tới deadlock. Một kỹ thuật là **khóa cả hai tài khoản theo thứ tự ID tăng dần** trước khi thay đổi:

~~~sql
BEGIN;

SELECT id, so_du, trang_thai
FROM ct308_tai_khoan
WHERE id IN (1, 2)
ORDER BY id
FOR UPDATE;

-- Sau đó kiểm tra đủ 2 hàng và thực hiện các UPDATE.

ROLLBACK;
~~~

Thống nhất thứ tự khóa có thể giảm deadlock, nhưng không loại bỏ mọi rủi ro vì trigger, FK, các bảng khác và các tài nguyên liên quan vẫn có thể tham gia.

### 16.5. Mức cô lập và việc thử lại

Ở `READ COMMITTED`, các statement liên tiếp trong cùng transaction có thể thấy snapshot khác nhau của những giao dịch đã commit. Ở các mức `REPEATABLE READ` hoặc `SERIALIZABLE` của PostgreSQL, transaction đồng thời có thể gặp lỗi serialization cần thử lại.

SQLSTATE thường gặp:

| SQLSTATE | Diễn giải |
|---|---|
| `40001` | serialization_failure |
| `40P01` | deadlock_detected |

Khi một transaction bị hủy do xung đột, hãy **retry cả đơn vị nghiệp vụ với transaction mới**, không chỉ chạy lại statement cuối trên một transaction đã lỗi. Việc retry còn cần mã idempotency để không chuyển tiền trùng nếu tình trạng COMMIT trước đó không rõ.

## 17. SAVEPOINT: rollback một phần có dùng được khi chuyển tiền?

`SAVEPOINT` là điểm đánh dấu bên trong transaction, cho phép hoàn tác phần thay đổi sau nó.

### 17.1. Ví dụ cơ chế

~~~sql
BEGIN;

UPDATE ct308_tai_khoan
SET so_du = so_du + 10
WHERE id = 1;
-- An: 1000 → 1010.

SAVEPOINT sau_buoc_mot;

UPDATE ct308_tai_khoan
SET so_du = so_du + 50
WHERE id = 1;
-- An: 1010 → 1060.

ROLLBACK TO SAVEPOINT sau_buoc_mot;
-- An trở lại 1010 trong transaction.

SELECT id, so_du
FROM ct308_tai_khoan
WHERE id = 1;

ROLLBACK;
-- An trở về 1000.
~~~

### 17.2. Vì sao không commit nửa chuyển tiền?

Không được dùng savepoint để:

~~~text
BEGIN
  Trừ An 250
  SAVEPOINT
  Cộng Bình thất bại
  ROLLBACK TO SAVEPOINT
  COMMIT phần trừ An
~~~

Vì nghiệp vụ yêu cầu **trừ và cộng thành một nhóm nguyên tử**. Savepoint chỉ phù hợp với những bước **có thể hủy riêng mà không phá bất biến của nghiệp vụ**. Nếu bước ghi có thất bại, phải rollback **toàn bộ chuyển tiền**, không giữ phần ghi nợ.

### 17.3. RELEASE SAVEPOINT không phải COMMIT

~~~sql
BEGIN;
SAVEPOINT sp1;
UPDATE ct308_tai_khoan
SET so_du = so_du + 10
WHERE id = 3;
RELEASE SAVEPOINT sp1;
ROLLBACK;
~~~

Thay đổi +10 vẫn bị rollback bởi transaction ngoài. `RELEASE SAVEPOINT` chỉ loại bỏ mốc quay lại, không xác nhận thay đổi độc lập.

### 17.4. Xử lý lỗi SQL tại savepoint

Trong PostgreSQL, khi một statement lỗi bên trong transaction, transaction thường vào trạng thái aborted. Nếu đã có savepoint trước statement lỗi, có thể dùng `ROLLBACK TO SAVEPOINT` để quay về trạng thái hợp lệ. Nhưng với một **chuyển tiền thất bại** thì việc giữ phần còn lại bằng savepoint thường không đúng nghiệp vụ; tốt nhất rollback toàn bộ.

## 18. Kiểm tra bất biến bằng một báo cáo đối soát

Sau một chuyển tiền thành công đã commit, nên có khả năng đối soát dữ liệu. Đoạn SQL dưới tìm lệnh có **số lượng bút toán không đúng** hoặc **tài khoản/giá trị của hai bút toán không khớp lệnh**.

~~~sql
SELECT
    lc.ma_chuyen,
    lc.tai_khoan_gui,
    lc.tai_khoan_nhan,
    lc.so_tien,

    COUNT(bt.id) AS so_but_toan,

    COUNT(bt.id) FILTER (
        WHERE bt.loai = 'DEBIT'
          AND bt.tai_khoan_id = lc.tai_khoan_gui
          AND bt.so_tien = lc.so_tien
    ) AS debit_hop_le,

    COUNT(bt.id) FILTER (
        WHERE bt.loai = 'CREDIT'
          AND bt.tai_khoan_id = lc.tai_khoan_nhan
          AND bt.so_tien = lc.so_tien
    ) AS credit_hop_le

FROM ct308_lenh_chuyen AS lc
LEFT JOIN ct308_but_toan AS bt
    ON bt.ma_chuyen = lc.ma_chuyen

GROUP BY
    lc.ma_chuyen,
    lc.tai_khoan_gui,
    lc.tai_khoan_nhan,
    lc.so_tien

HAVING
    COUNT(bt.id) <> 2
    OR COUNT(bt.id) FILTER (
        WHERE bt.loai = 'DEBIT'
          AND bt.tai_khoan_id = lc.tai_khoan_gui
          AND bt.so_tien = lc.so_tien
    ) <> 1
    OR COUNT(bt.id) FILTER (
        WHERE bt.loai = 'CREDIT'
          AND bt.tai_khoan_id = lc.tai_khoan_nhan
          AND bt.so_tien = lc.so_tien
    ) <> 1

ORDER BY lc.ma_chuyen;
~~~

Nếu mọi giao dịch đang lưu đều có đủ hai bút toán đúng theo cấu trúc đơn giản của bài, báo cáo này trả **0 hàng**. Những hàng trả về là **ứng viên bất thường** cần điều tra.

### 18.1. Vì sao đối soát không thay được transaction?

Nếu nghiệp vụ đã commit một lần ghi nợ sai mà không có ghi có, báo cáo có thể phát hiện **sau sự cố**, nhưng không tự hoàn tác được dữ liệu đã commit. Transaction với kiểm tra trước COMMIT là tuyến bảo vệ chủ động; đối soát là tuyến kiểm tra hậu kiểm.

### 18.2. Vì sao báo cáo không chứng minh đầy đủ hệ thống tài chính?

Mô hình chỉ có ba bảng thử nghiệm. Một hệ thống thật cần xác định cách tính số dư từ ledger, tiền tệ, thời điểm hiệu lực, phí, trạng thái, bút toán đảo, kiểm soát bất biến mạnh, audit bất biến và kết nối hệ thống ngoài. Không tự tuyên bố truy vấn trên là một bộ kiểm toán tài chính đầy đủ.

## 19. JDBC: chuyển tiền và rollback khi kiểm tra thất bại

Trong Java, transaction có thể được điều phối qua JDBC `Connection`:

- `setAutoCommit(false)` mở chế độ tự kiểm soát commit.
- Các statement dùng **chính Connection đó**.
- `executeUpdate()` cung cấp số hàng tác động.
- Ném exception nếu không đúng kỳ vọng.
- `commit()` chỉ chạy sau khi toàn bộ bước thành công.
- `rollback()` trong nhánh lỗi.

Đoạn code sau là ví dụ minh họa cho **PostgreSQL JDBC**, Java 17+, bảng `ct308_*` đã được tạo trong **cùng phiên Connection**. Một ứng dụng thật cần thêm xác thực quyền, tiền tệ, logging, mapping lỗi, retry và chính sách connection pool.

### 19.1. Mẫu dịch vụ đầy đủ

~~~java
import java.math.BigDecimal;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.SQLException;

public final class TransferService {

    private TransferService() {}

    public static void transfer(
            Connection conn,
            String code,
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
                "Tài khoản gửi và nhận phải khác nhau"
            );
        }

        boolean oldAutoCommit = conn.getAutoCommit();

        if (!oldAutoCommit) {
            throw new IllegalStateException(
                "Connection đang do transaction khác quản lý"
            );
        }

        conn.setAutoCommit(false);

        try {
            insertTransfer(
                conn, code, senderId, receiverId, amount
            );

            int debit = debitSender(
                conn, senderId, amount
            );
            if (debit != 1) {
                throw new SQLException(
                    "Không trừ được đúng một tài khoản gửi"
                );
            }

            int credit = creditReceiver(
                conn, receiverId, amount
            );
            if (credit != 1) {
                throw new SQLException(
                    "Không cộng được đúng một tài khoản nhận"
                );
            }

            insertEntry(
                conn, code, senderId, "DEBIT", amount
            );
            insertEntry(
                conn, code, receiverId, "CREDIT", amount
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
            INSERT INTO ct308_lenh_chuyen
                (ma_chuyen, tai_khoan_gui,
                 tai_khoan_nhan, so_tien)
            VALUES (?, ?, ?, ?)
            """;

        try (PreparedStatement ps =
                     conn.prepareStatement(sql)) {
            ps.setString(1, code);
            ps.setInt(2, senderId);
            ps.setInt(3, receiverId);
            ps.setBigDecimal(4, amount);

            requireOne(
                ps.executeUpdate(),
                "INSERT lệnh chuyển"
            );
        }
    }

    private static int debitSender(
            Connection conn,
            int senderId,
            BigDecimal amount
    ) throws SQLException {

        String sql = """
            UPDATE ct308_tai_khoan
            SET so_du = so_du - ?
            WHERE id = ?
              AND trang_thai = 'ACTIVE'
              AND so_du >= ?
            """;

        try (PreparedStatement ps =
                     conn.prepareStatement(sql)) {
            ps.setBigDecimal(1, amount);
            ps.setInt(2, senderId);
            ps.setBigDecimal(3, amount);
            return ps.executeUpdate();
        }
    }

    private static int creditReceiver(
            Connection conn,
            int receiverId,
            BigDecimal amount
    ) throws SQLException {

        String sql = """
            UPDATE ct308_tai_khoan
            SET so_du = so_du + ?
            WHERE id = ?
              AND trang_thai = 'ACTIVE'
            """;

        try (PreparedStatement ps =
                     conn.prepareStatement(sql)) {
            ps.setBigDecimal(1, amount);
            ps.setInt(2, receiverId);
            return ps.executeUpdate();
        }
    }

    private static void insertEntry(
            Connection conn,
            String code,
            int accountId,
            String kind,
            BigDecimal amount
    ) throws SQLException {

        String sql = """
            INSERT INTO ct308_but_toan
                (ma_chuyen, tai_khoan_id, loai, so_tien)
            VALUES (?, ?, ?, ?)
            """;

        try (PreparedStatement ps =
                     conn.prepareStatement(sql)) {
            ps.setString(1, code);
            ps.setInt(2, accountId);
            ps.setString(3, kind);
            ps.setBigDecimal(4, amount);

            requireOne(
                ps.executeUpdate(),
                "INSERT bút toán " + kind
            );
        }
    }

    private static void requireOne(
            int count,
            String operation
    ) throws SQLException {
        if (count != 1) {
            throw new SQLException(
                operation + ": cần đúng 1 hàng, nhận " + count
            );
        }
    }
}
~~~

### 19.2. Diễn giải transaction trong code

~~~text
setAutoCommit(false)
          │
          ▼
INSERT lệnh → phải 1
          │
          ▼
UPDATE gửi → phải 1
          │
          ▼
UPDATE nhận → phải 1
          │
          ▼
INSERT DEBIT → phải 1
          │
          ▼
INSERT CREDIT → phải 1
          │
    ┌─────┴──────┐
    ▼            ▼
Tất cả đúng    Có lỗi/sai số hàng
    │            │
  commit()     rollback()
~~~

Nếu `debitSender` trả 0, method ném exception **trước khi cộng Bình**. Nếu `creditReceiver` trả 0, rollback hoàn tác cả INSERT lệnh và UPDATE trừ An trước đó. Nếu INSERT CREDIT bị lỗi, rollback hủy các bước trước trong cùng transaction.

### 19.3. Vì sao dùng BigDecimal?

Ví dụ `so_du` dùng kiểu PostgreSQL `NUMERIC(14,2)`. Trong Java, `BigDecimal` phù hợp hơn `double` khi cần tính tiền với độ chính xác thập phân.

Cần có quy tắc miền giá trị, scale, rounding và currency ở hệ thống thật. BigDecimal không tự quyết định cách làm tròn hay định nghĩa tiền tệ.

### 19.4. Vì sao dùng PreparedStatement?

Các tham số `?` được truyền qua API typed như `setBigDecimal`, `setInt`, `setString`. Không nối trực tiếp giá trị người dùng vào chuỗi SQL để tránh SQL injection và lỗi định dạng.

### 19.5. Hạn chế của mẫu code

Mẫu trên có ràng buộc schema và kiểm tra số hàng, nhưng không phải chương trình ngân hàng hoàn chỉnh. Đặc biệt:

- Không kiểm tra trước/ sau **tổng cặp tài khoản** bằng truy vấn như khối DO, dù các bước cộng trừ đều dùng cùng `amount` và số hàng được kiểm soát.
- Không thực hiện cơ chế retry cho deadlock/serialization.
- Không xử lý riêng tình trạng COMMIT đã thành công nhưng phản hồi bị mất.
- Không kiểm tra người dùng có quyền chuyển tiền từ tài khoản nào.
- Không có cơ chế kiểm soát nhiều tiền tệ, hạn mức, ngày hiệu lực hoặc cấm gian lận.
- Không có hệ thống ledger bất biến và đối soát chuẩn sản xuất.

Các yêu cầu ấy phải được bổ sung theo kiến trúc và rủi ro nghiệp vụ.

### 19.6. Connection đang thuộc transaction ngoài

Mẫu code yêu cầu `getAutoCommit() == true` trước khi tự quản lý transaction. Nếu Connection đã do framework hoặc một service bên ngoài quản lý, tự ý `commit`/`rollback` hoặc đổi auto-commit có thể phá ranh giới transaction của bên ngoài.

Trong Spring, thường đặt `@Transactional` ở service nghiệp vụ và để repository tham gia transaction do Spring quản lý. Đừng kết hợp hai cách điều khiển một cách tùy tiện.

### 19.7. Phục hồi trạng thái Connection sau lỗi

`finally` gọi `setAutoCommit(oldAutoCommit)`. Lời gọi này cũng có thể thất bại khi connection hỏng. Trong code sản xuất, cần cơ chế connection pool đóng/loại bỏ connection bị lỗi và quản lý thông tin lỗi thích hợp.

## 20. Java/Spring: ranh giới transaction ở tầng service

Ví dụ ý tưởng:

~~~java
@Service
public class TransferApplicationService {

    private final AccountRepository accounts;
    private final TransferRepository transfers;
    private final EntryRepository entries;

    public TransferApplicationService(
            AccountRepository accounts,
            TransferRepository transfers,
            EntryRepository entries
    ) {
        this.accounts = accounts;
        this.transfers = transfers;
        this.entries = entries;
    }

    @Transactional
    public void transfer(TransferRequest request) {
        transfers.insertRequest(request);

        int debit = accounts.debitIfEnough(
            request.senderId(), request.amount()
        );
        if (debit != 1) {
            throw new IllegalStateException(
                "Không đủ tiền hoặc tài khoản gửi không hợp lệ"
            );
        }

        int credit = accounts.creditIfActive(
            request.receiverId(), request.amount()
        );
        if (credit != 1) {
            throw new IllegalStateException(
                "Tài khoản nhận không hợp lệ"
            );
        }

        entries.insertDebit(request);
        entries.insertCredit(request);
    }
}
~~~

Đây là mẫu cấu trúc, không phải file Java chạy độc lập: các loại `AccountRepository`, `TransferRequest` và các import/framework configuration cần được định nghĩa trong dự án thực.

Điểm chính:

- `@Transactional` đặt ranh giới ở tầng bao quát **toàn bộ nghiệp vụ**.
- Các repository phải dùng cùng transaction manager/data source phù hợp.
- Lỗi nghiệp vụ phải được thể hiện sao cho transaction **rollback**, không nuốt exception rồi trả thành công.
- Với Spring cấu hình phổ biến, unchecked exception thường kích hoạt rollback; checked exception có thể cần `rollbackFor` hoặc quy tắc rõ ràng.
- Khi dùng Spring proxy, tự gọi một method `@Transactional` bên trong cùng đối tượng (*self-invocation*) có thể không tạo ranh giới như mong đợi.
- Nếu một bước dùng datasource khác không tham gia transaction, nó **không tự** được rollback cùng các bảng còn lại.

### 20.1. Ví dụ nguy hiểm: repository commit riêng

~~~text
transfer():
  accountRepository.debit()       → transaction A, COMMIT
  accountRepository.credit()      → transaction B, lỗi/ROLLBACK
  ledgerRepository.insertEntry()  → transaction C, chưa chạy
~~~

Cả ba repository có thể đúng cú pháp SQL, nhưng **ranh giới nghiệp vụ sai**. Cần một transaction bao trùm các bước liên quan, không phải mỗi repository tự commit.

### 20.2. Lỗi bị bắt và bỏ qua

~~~java
@Transactional
public void transfer(...) {
    try {
        accounts.debit(...);
        accounts.credit(...);
    } catch (Exception ex) {
        // Chỉ log rồi return bình thường: nguy hiểm!
    }
}
~~~

Nếu phương thức hoàn tất bình thường, transaction manager có thể COMMIT những bước đã chạy, tùy cấu hình và trạng thái transaction. Không được “nuốt” lỗi của một chuyển tiền bắt buộc toàn vẹn. Cần ném lại hoặc đánh dấu rollback theo framework.

## 21. Các trường hợp sự cố cần xử lý rõ

| Kịch bản | Hành vi SQL có thể thấy | Kết quả nghiệp vụ đúng |
|---|---|---|
| Chuyển 250 An → Bình, cả hai ACTIVE, đủ tiền | Hai UPDATE mỗi cái 1 hàng | Cho phép COMMIT sau khi đủ bút toán |
| Chuyển 2000 từ An | UPDATE gửi 0 hàng | ROLLBACK toàn bộ |
| ID người gửi không tồn tại | FK hoặc UPDATE 0 hàng | ROLLBACK và báo ID không hợp lệ |
| ID người nhận không tồn tại | FK hoặc UPDATE nhận 0 hàng | ROLLBACK |
| Người gửi BLOCKED | UPDATE gửi 0 hàng | ROLLBACK |
| Người nhận BLOCKED | UPDATE nhận 0 hàng | ROLLBACK, hủy cả bước ghi nợ |
| Hai ID gửi/nhận giống nhau | CHECK lỗi hoặc xác thực nghiệp vụ | Từ chối, không chuyển |
| Số tiền bằng 0/âm | CHECK hoặc xác thực | Từ chối |
| Bút toán ghi nợ bị lỗi CHECK | Statement lỗi, transaction aborted | ROLLBACK toàn bộ |
| Mã chuyển trùng | PRIMARY KEY/UNIQUE | Không chuyển lại tùy tiện; xác minh retry |
| Transaction khác trừ cùng tài khoản | Chờ khóa, UPDATE 0 hàng hoặc lỗi tùy isolation | Xử lý đồng thời, rollback/retry phù hợp |
| Mất kết nối trước COMMIT | Transaction chưa commit có thể rollback | Xác minh lại; không đoán |
| Mất phản hồi sau khi gửi COMMIT | Không biết chắc đã commit chưa | Đối chiếu mã idempotency, không dùng mã mới tự động |
| Gửi email giữa transaction rồi ROLLBACK | Email ngoài DB có thể đã gửi | Outbox/điều phối ngoài DB |

**Nguyên tắc:** không đồng nhất “câu SQL thành công”, “không có exception”, “đã commit” và “nghiệp vụ đúng”.

## 22. Bảng tổng số dư và bút toán: hai loại kiểm tra độc lập

Một trong những mục tiêu thực hành quan trọng là biết dùng nhiều bất biến bổ trợ.

### 22.1. Kiểm tra tổng số dư

~~~sql
SELECT SUM(so_du) AS tong_toan_he
FROM ct308_tai_khoan;
~~~

Trong ví dụ cơ bản, trước và sau chuyển thành công đều là **1550**.

### 22.2. Kiểm tra bút toán cùng mã

~~~sql
SELECT
    ma_chuyen,
    COUNT(*) AS so_dong,
    SUM(
        CASE WHEN loai = 'CREDIT' THEN so_tien
             WHEN loai = 'DEBIT' THEN -so_tien
        END
    ) AS tong_dai_so
FROM ct308_but_toan
WHERE ma_chuyen = 'LAB-SUCCESS-01'
GROUP BY ma_chuyen;
~~~

Kết quả đúng: hai dòng, tổng đại số **0**.

### 22.3. Khi nào hai kiểm tra vẫn chưa đủ?

- Tổng số dư bằng nhau nhưng chuyển sai người nhận.
- Bút toán cân bằng nhưng ghi vào sai hai tài khoản.
- Lệnh ghi chuyển tiền 250 nhưng bút toán DEBIT/CREDIT đều 200: tổng bút toán vẫn 0.
- Chỉ một giao dịch có bút toán được ghi nhưng số dư chưa cập nhật.

Bởi vậy cần so bút toán **với bản ghi yêu cầu**, kiểm tra đúng ID và đúng số tiền, không chỉ so tổng.

### 22.4. Kiểm tra ở ranh giới nào?

Với nghiệp vụ chuyển tiền, kiểm tra nên diễn ra **trước khi COMMIT** trên trạng thái vừa sửa trong transaction. Báo cáo đối soát chạy sau đó cũng hữu ích để phát hiện sai sót do các quy trình khác hoặc dữ liệu cũ, nhưng không thay được kiểm tra tại thời điểm ghi.

## 23. PostgreSQL và các hệ quản trị khác

Mục tiêu nguyên tử và bất biến có thể áp dụng rộng rãi cho SQL, nhưng cú pháp và hành vi transaction khác nhau.

| DBMS | Transaction | Lấy hàng bị tác động | Lưu ý |
|---|---|---|---|
| **PostgreSQL** | `BEGIN/COMMIT/ROLLBACK` | `RETURNING`; `GET DIAGNOSTICS ROW_COUNT` trong PL/pgSQL | Statement lỗi thường làm transaction bị aborted; SAVEPOINT; MVCC |
| **MySQL InnoDB** | `START TRANSACTION/COMMIT/ROLLBACK` | `ROW_COUNT()`, affected rows của driver | Kiểm tra engine transactional; một số DDL implicit commit |
| **MariaDB** | `START TRANSACTION` | `ROW_COUNT()` và API driver; các biến thể RETURNING tùy lệnh/phiên bản | Khả năng hỗ trợ tùy engine và phiên bản |
| **SQL Server** | `BEGIN TRANSACTION` | `@@ROWCOUNT`, `OUTPUT INSERTED...` | `TRY...CATCH`, `XACT_STATE()`, `SET XACT_ABORT` ảnh hưởng xử lý lỗi |
| **Oracle** | Transaction DML ngầm, `COMMIT/ROLLBACK` | `SQL%ROWCOUNT` trong PL/SQL | PL/SQL BEGIN...END không phải lệnh mở SQL transaction; DDL thường implicit commit |
| **SQLite** | `BEGIN`, `COMMIT`, `ROLLBACK` | `RETURNING`, `changes()` | Cơ chế khóa khác server RDBMS; cần xét SQLITE_BUSY |

### 23.1. SQL Server: kiểm tra affected rows

Ví dụ T-SQL minh họa cách kiểm tra sau UPDATE:

~~~sql
BEGIN TRANSACTION;

UPDATE dbo.TaiKhoan
SET SoDu = SoDu - @amount
WHERE Id = @senderId
  AND TrangThai = 'ACTIVE'
  AND SoDu >= @amount;

IF @@ROWCOUNT <> 1
BEGIN
    ROLLBACK TRANSACTION;
    THROW 50001, 'Debit failed', 1;
END;

-- Tiếp tục UPDATE tài khoản nhận và kiểm tra @@ROWCOUNT,
-- ghi bút toán, rồi COMMIT khi đủ điều kiện.
~~~

Đây là **đoạn T-SQL minh họa** trong ngữ cảnh đã khai báo các biến `@amount` và `@senderId`. Lưu ý `@@ROWCOUNT` cần được đọc ngay sau câu DML liên quan. Không sao chép nguyên cú pháp `THROW` sang PostgreSQL.

### 23.2. MySQL/InnoDB

~~~sql
START TRANSACTION;

UPDATE tai_khoan
SET so_du = so_du - 250
WHERE id = 1
  AND trang_thai = 'ACTIVE'
  AND so_du >= 250;

SELECT ROW_COUNT() AS so_hang_ghi_no;

-- Chỉ tiếp tục khi đúng 1 hàng.
-- Sau đó UPDATE ghi có, kiểm tra, INSERT nhật ký.
-- COMMIT nếu đủ tất cả điều kiện; ngược lại ROLLBACK.
~~~

`ROW_COUNT()` theo dõi số hàng ảnh hưởng theo ngữ nghĩa của MySQL. Cần kiểm tra behavior driver/DBMS, đặc biệt các trường hợp UPDATE gán bằng giá trị cũ và cách báo matched vs changed rows. Ở ví dụ trừ tiền khác 0, điều kiện kỳ vọng vẫn là một hàng bị thay đổi.

### 23.3. Oracle PL/SQL

Trong PL/SQL, có thể kiểm tra `SQL%ROWCOUNT` ngay sau UPDATE; nếu không bằng 1 thì `RAISE_APPLICATION_ERROR` để báo thất bại và rollback theo transaction boundary đã chọn. Không nhầm `BEGIN ... END` của khối PL/SQL với `BEGIN TRANSACTION` trong PostgreSQL hoặc SQL Server.

### 23.4. ROLLBACK và DDL không đồng nhất

PostgreSQL cho phép nhiều DDL transactional, nhưng MySQL/Oracle có nhiều DDL implicit commit. Trên một số engine không có transaction, ROLLBACK cũng không có ý nghĩa giống InnoDB. Bài tập chuyển tiền nên dùng **bảng transactional**, tránh trộn DDL trong quy trình chuyển tiền rồi cho rằng mọi DBMS đều hoàn tác giống nhau.

### 23.5. SQLSTATE và lỗi xử lý

Trên PostgreSQL, có thể gặp:

| SQLSTATE | Ý nghĩa |
|---|---|
| `23503` | FOREIGN KEY violation |
| `23505` | UNIQUE violation |
| `23514` | CHECK violation |
| `40001` | serialization_failure |
| `40P01` | deadlock_detected |
| `25P02` | transaction đang aborted; cần rollback |
| `P0001` | lỗi PL/pgSQL do RAISE EXCEPTION mặc định |

Khi lập trình, nên phân biệt **lỗi cần trả về người dùng** (không đủ tiền, tài khoản bị khóa, mã trùng) và **lỗi hệ thống cần log/retry** (deadlock, mất kết nối, lỗi DB), nhưng không làm lộ thông tin tài khoản của người khác.

## 24. Bài tập thực hành có lời giải

Tất cả bài tập dùng schema TEMP `ct308_*` ở phần 4. Với bài có DML, sử dụng transaction và kết thúc bằng ROLLBACK để quay về số dư An 1000, Bình 400, Chi 150. Nếu trước đó đã COMMIT các ví dụ, cần tạo lại dữ liệu gốc trong phiên học phù hợp.

### Bài 1. Xác định tổng số dư ban đầu

**Yêu cầu:** liệt kê tài khoản và tổng số dư.

~~~sql
SELECT id, chu_so_huu, so_du, trang_thai
FROM ct308_tai_khoan
ORDER BY id;

SELECT SUM(so_du) AS tong
FROM ct308_tai_khoan;
~~~

**Đáp án:** An 1000 ACTIVE, Bình 400 ACTIVE, Chi 150 BLOCKED; tổng **1550**.

### Bài 2. Tính số dư sau chuyển 250

**Câu hỏi:** chuyển 250 từ An sang Bình, số dư sau và tổng cặp là bao nhiêu?

**Đáp án:** An 750, Bình 650, tổng cặp vẫn **1400**. Tổng ba tài khoản vẫn **1550** vì Chi không đổi.

### Bài 3. Dùng SELECT mô phỏng, không sửa dữ liệu

~~~sql
SELECT
    id,
    so_du AS truoc,
    CASE
        WHEN id = 1 THEN so_du - 250
        WHEN id = 2 THEN so_du + 250
    END AS du_kien
FROM ct308_tai_khoan
WHERE id IN (1, 2)
ORDER BY id;
~~~

**Đáp án:** ID 1 có dự kiến 750, ID 2 có dự kiến 650. Đây chỉ là SELECT, chưa thay đổi database.

### Bài 4. UPDATE trừ tiền có điều kiện

~~~sql
BEGIN;

UPDATE ct308_tai_khoan
SET so_du = so_du - 250
WHERE id = 1
  AND trang_thai = 'ACTIVE'
  AND so_du >= 250
RETURNING id, so_du;

ROLLBACK;
~~~

**Đáp án:** trong transaction, một hàng ID 1 trả 750; sau ROLLBACK, An lại 1000.

### Bài 5. Phát hiện không đủ tiền

~~~sql
BEGIN;

UPDATE ct308_tai_khoan
SET so_du = so_du - 2000
WHERE id = 1
  AND so_du >= 2000
RETURNING id;

ROLLBACK;
~~~

**Đáp án:** RETURNING **0 hàng**. Bất kỳ quy trình chuyển tiền nào yêu cầu ghi nợ thành công phải dừng và rollback, không cộng cho người nhận.

### Bài 6. Lỗi nếu bỏ qua UPDATE 0 hàng

**Tình huống:** ghi nợ An 2000 khớp 0 hàng, ghi có Bình 2000 khớp một hàng, rồi COMMIT.

**Đáp án:** số dư Bình tăng từ 400 lên 2400, An vẫn 1000. Bất biến tổng số dư bị phá. Đây là lỗi nghiệp vụ **dù transaction có tính atomic** đối với những thay đổi thực tế. Cần kiểm tra row count sau mỗi bước.

### Bài 7. Ghi hai bút toán đúng loại

~~~sql
BEGIN;

INSERT INTO ct308_lenh_chuyen
    (ma_chuyen, tai_khoan_gui, tai_khoan_nhan, so_tien)
VALUES ('BT-308-07', 1, 2, 50);

INSERT INTO ct308_but_toan
    (ma_chuyen, tai_khoan_id, loai, so_tien)
VALUES
    ('BT-308-07', 1, 'DEBIT', 50),
    ('BT-308-07', 2, 'CREDIT', 50);

SELECT
    ma_chuyen,
    COUNT(*) AS dem,
    SUM(
        CASE WHEN loai = 'CREDIT' THEN so_tien
             ELSE -so_tien END
    ) AS chenhlech
FROM ct308_but_toan
WHERE ma_chuyen = 'BT-308-07'
GROUP BY ma_chuyen;

ROLLBACK;
~~~

**Đáp án:** hai bút toán, chênh lệch **0**. Nhưng bài chỉ minh họa ghi bút toán; nó **chưa thực hiện UPDATE số dư**, nên không được COMMIT và gọi đây là chuyển tiền hoàn chỉnh.

### Bài 8. Vi phạm FOREIGN KEY

**Đề bài:** thử tạo lệnh chuyển cho người nhận ID 999.

~~~sql
BEGIN;

INSERT INTO ct308_lenh_chuyen
    (ma_chuyen, tai_khoan_gui, tai_khoan_nhan, so_tien)
VALUES ('BT-308-08', 1, 999, 50);

ROLLBACK;
~~~

**Đáp án:** bị từ chối do FK của tài khoản nhận. ROLLBACK kết thúc transaction lỗi, không có lệnh mới được lưu.

### Bài 9. Vi phạm CHECK

**Đề bài:** ghi một bút toán có `so_tien = -20` thì sao?

**Đáp án:** CHECK `so_tien > 0` từ chối hàng. Nếu lỗi xảy ra trong transaction PostgreSQL, cần rollback toàn bộ hoặc phục hồi savepoint phù hợp. Với chuyển tiền thực, phải rollback cả nhóm.

### Bài 10. Tài khoản bị khóa

~~~sql
SELECT id, trang_thai
FROM ct308_tai_khoan
WHERE id = 3;

BEGIN;

UPDATE ct308_tai_khoan
SET so_du = so_du - 50
WHERE id = 3
  AND trang_thai = 'ACTIVE'
  AND so_du >= 50
RETURNING id;

ROLLBACK;
~~~

**Đáp án:** Chi BLOCKED, UPDATE trả 0 hàng. Không được tiếp tục xử lý chuyển tiền từ Chi theo quy tắc bài.

### Bài 11. Kiểm tra số tiền ghi nợ–ghi có

**Đề bài:** lệnh chuyển 250 có hai bút toán: DEBIT 250, CREDIT 200. Tổng đại số bút toán là bao nhiêu?

\[
-250 + 200 = -50
\]

**Đáp án:** -50, không bằng 0. Bất biến cân bằng bút toán bị phá; transaction phải rollback. Trường hợp DEBIT 200, CREDIT 200 vẫn cân bằng 0 nhưng **khác số tiền lệnh 250**, nên cần đối chiếu cả request.

### Bài 12. Vì sao tổng số dư vẫn đúng mà nghiệp vụ sai?

**Đề bài:** trừ An 250 rồi cộng Chi 250 thay vì Bình.

**Đáp án:** tổng toàn hệ vẫn 1550, nhưng sai người nhận. Do đó phải kiểm tra ID người nhận và bút toán có đúng tài khoản `tai_khoan_nhan` của lệnh không, không chỉ kiểm tra tổng số dư.

### Bài 13. SAVEPOINT và ROLLBACK

~~~sql
BEGIN;
UPDATE ct308_tai_khoan
SET so_du = so_du + 20
WHERE id = 1;

SAVEPOINT moc;

UPDATE ct308_tai_khoan
SET so_du = so_du + 30
WHERE id = 1;

ROLLBACK TO SAVEPOINT moc;

SELECT so_du
FROM ct308_tai_khoan
WHERE id = 1;

ROLLBACK;
~~~

**Đáp án:** SELECT trong transaction thấy 1020. Sau ROLLBACK ngoài cùng, An về 1000. RELEASE SAVEPOINT không commit riêng phần đã giữ.

### Bài 14. Chuyển đồng thời vượt số dư

**Đề bài:** An có 1000, A muốn chuyển 700 và B muốn chuyển 500, hai giao dịch chạy đồng thời. Khi dùng UPDATE tương đối có `so_du >= amount`, có được commit cả hai không?

**Đáp án:** không, nếu cả hai thực sự cùng trừ tài khoản An và không có khoản nạp thêm. Sau một lần thành công, số dư còn 300 hoặc 500, không đủ cho lần còn lại. Bên còn lại phải thấy UPDATE 0 hàng hoặc lỗi cạnh tranh và rollback/retry theo chính sách.

### Bài 15. Trùng mã idempotency

**Đề bài:** một mã chuyển tiền đã commit. Lần gửi lại dùng `ON CONFLICT DO NOTHING RETURNING ma_chuyen` trả 0 hàng. Có được tiếp tục hai UPDATE không?

**Đáp án:** không. Phải xác minh đó có phải retry của cùng request không và trả kết quả cũ/nhánh xử lý phù hợp. Nếu vẫn ghi nợ/ghi có, có thể chuyển tiền hai lần.

### Bài 16. Mất kết nối sau COMMIT

**Đề bài:** server có thể đã commit chuyển tiền nhưng client không nhận phản hồi. Có chắc cần chạy lại bằng mã mới không?

**Đáp án:** không. Trạng thái commit có thể không xác định từ góc nhìn client. Tra cứu theo mã yêu cầu ổn định và quy trình idempotency trước khi quyết định retry; không tạo mã mới rồi chuyển lại một cách mù quáng.

### Bài 17. JDBC một Connection

**Đề bài:** hàm ghi nợ dùng Connection A, hàm ghi có dùng Connection B, mỗi bên tự commit. Có bảo đảm nguyên tử cho chuyển tiền không?

**Đáp án:** không. Hai Connection thường có hai transaction độc lập. Cần cùng Connection/transaction manager hoặc kiến trúc giao dịch phân tán/bù trừ nếu các bên thuộc tài nguyên khác nhau.

### Bài 18. Lựa chọn rollback hay savepoint

**Đề bài:** đã ghi nợ An, ghi có Bình thất bại. Có thể rollback riêng bước ghi có, giữ ghi nợ và commit không?

**Đáp án:** không đối với nghiệp vụ chuyển tiền phải cân bằng. Phải rollback **toàn bộ** thay đổi của transfer. Savepoint chỉ thích hợp nếu phần giữ lại vẫn hợp lệ theo bất biến.

### Bài 19. Tìm bút toán không khớp lệnh

**Yêu cầu:** với các mã đã lưu, tìm những lệnh thiếu hai bút toán hoặc tài khoản/số tiền bút toán sai.

**Đáp án gợi ý:** sử dụng `LEFT JOIN` lệnh chuyển–bút toán, `GROUP BY ma_chuyen`, `COUNT(bt.id)` và các COUNT FILTER kiểm tra đúng DEBIT/CREDIT cùng tài khoản, cùng số tiền như truy vấn phần 18. Nếu tập hoàn chỉnh, kết quả bất thường rỗng.

### Bài 20. Thiết kế transaction hoàn chỉnh

**Yêu cầu:** viết lại bằng lời các bước xử lý một request chuyển tiền thành công và thất bại.

**Đáp án:**

1. Xác thực request, quyền, tài khoản gửi/nhận và mã yêu cầu.
2. Bắt đầu transaction.
3. Khóa/kiểm tra những hàng cần thiết, phát hiện mã trùng.
4. INSERT lệnh chuyển.
5. UPDATE trừ tiền với điều kiện đủ tiền, kiểm tra đúng một hàng.
6. UPDATE cộng tiền, kiểm tra đúng một hàng.
7. INSERT hai bút toán, kiểm tra đầy đủ.
8. Đối chiếu ID, số tiền, bất biến cân bằng.
9. COMMIT nếu toàn bộ điều kiện đúng; nếu bất kỳ bước sai thì ROLLBACK.
10. Nếu mất phản hồi COMMIT, xác minh qua mã idempotency; không chuyển lặp tùy tiện.

## 25. Những lỗi thực hành thường gặp

| Lỗi | Vì sao nguy hiểm? | Cách xử lý |
|---|---|---|
| Hai UPDATE chạy autocommit riêng | Có thể chỉ một phía commit | Một transaction bao trùm |
| UPDATE gửi không kiểm tra đủ tiền | Có thể vi phạm CHECK hoặc âm số dư | WHERE đủ tiền, kiểm tra row count |
| UPDATE trả 0 hàng nhưng tiếp tục | Có thể tạo tiền cho người nhận | Thất bại nghiệp vụ → rollback |
| Chỉ kiểm tra tổng số dư | Có thể chuyển sai người nhận | Kiểm tra đúng ID và số tiền từng phía |
| Chỉ kiểm tra tổng DEBIT–CREDIT = 0 | Hai số tiền cùng sai vẫn cân bằng | So với bản ghi lệnh |
| Không ghi bút toán cùng transaction | Số dư và lịch sử có thể lệch | Gộp cùng ranh giới |
| Trùng mã rồi vẫn UPDATE | Có thể chuyển hai lần | Idempotency kiểm tra trạng thái |
| Dùng MAX(id) để lấy lệnh vừa sinh | Có thể nhầm giao dịch khác | RETURNING/generated keys |
| Dùng hai Connection | Không cùng transaction | Một Connection/transaction manager |
| Ném lỗi rồi nuốt exception trong Spring | Có thể commit phần đã làm | Propagate/mark rollback |
| Sau lỗi PostgreSQL tiếp tục query | Transaction có thể aborted | ROLLBACK hoặc savepoint phù hợp |
| COMMIT rồi mới kiểm tra bất biến | Đã quá muộn để rollback transaction ấy | Kiểm tra trước COMMIT |
| Giữ khóa trong lúc gọi API lâu | Dễ chờ khóa/deadlock | Transaction ngắn |
| Tự giả định timeout là rollback | Có thể thực tế đã commit | Truy vết mã idempotency |
| Sửa sequence để lấp khoảng trống | Có thể sinh trùng ID | Chấp nhận sequence gap |
| Kiểm tra dữ liệu TEMP bằng connection khác | Không nhìn thấy bảng TEMP | Cùng connection, hoặc dùng bảng sandbox thường cho lab đồng thời |
| Tin FK thay thế phân quyền | FK chỉ kiểm tra tham chiếu tồn tại | Xác minh quyền tài khoản |
| Xem SUM toàn hệ là bằng chứng tuyệt đối khi concurrent | Snapshot/transaction khác có thể làm số liệu biến động | Kiểm tra cặp đã khóa và bút toán đúng nghiệp vụ |

## 26. Checklist trước COMMIT một chuyển tiền

Hãy dùng danh sách câu hỏi này như một quy trình kiểm tra:

1. **Mã yêu cầu có duy nhất và ổn định khi retry không?**
2. **Người gửi và người nhận có phải hai tài khoản khác nhau không?**
3. **Cả hai ID có tồn tại và thuộc phạm vi được phép không?**
4. **Cả hai tài khoản đang ở trạng thái cho phép theo nghiệp vụ không?**
5. **Số tiền dương, đúng tiền tệ và độ chính xác không?**
6. **Đã dùng một transaction duy nhất cho cả nhóm thay đổi chưa?**
7. **Đã khóa/kiểm tra phù hợp với nguy cơ đồng thời chưa?**
8. **UPDATE ghi nợ có điều kiện đủ tiền ngay lúc ghi không?**
9. **UPDATE ghi nợ tác động đúng một hàng không?**
10. **UPDATE ghi có tác động đúng một hàng không?**
11. **Số tiền ghi nợ và ghi có có đúng bằng yêu cầu không?**
12. **Tài khoản bị trừ/cộng có đúng các ID trong lệnh không?**
13. **Có đúng một DEBIT và một CREDIT không?**
14. **Hai bút toán có cùng mã và khớp số tiền lệnh không?**
15. **Tổng số dư cặp tài khoản đã bảo toàn chưa?**
16. **Các ràng buộc FK/CHECK/UNIQUE có thành công không?**
17. **Nếu một statement trả 0 hàng, có nhánh rollback rõ ràng không?**
18. **Nếu một statement lỗi, có rollback transaction thay vì tiếp tục không?**
19. **Nếu COMMIT hoặc phản hồi bị lỗi, có cách xác minh bằng mã giao dịch không?**
20. **Có tác động ngoài DB cần xử lý riêng không?**
21. **Có cần ghi audit/outbox trong cùng transaction không?**
22. **Chỉ COMMIT sau khi tất cả điều kiện đạt; ngược lại rollback chưa?**

## 27. Tổng kết

Thực hành chuyển tiền giúp nhìn rõ **ba lớp bảo vệ khác nhau**:

1. **Ranh giới transaction:** gom thay đổi ghi nợ, ghi có, lệnh chuyển và bút toán vào **một đơn vị nguyên tử**.
2. **Bất biến dữ liệu:** số dư không âm; đúng tài khoản; ghi nợ = ghi có = số tiền yêu cầu; tổng tiền nội bộ được bảo toàn; số dòng tác động đúng kỳ vọng.
3. **Xử lý thất bại:** nếu điều kiện không đạt, UPDATE 0 hàng, ràng buộc lỗi hoặc xung đột đồng thời, **không COMMIT phần còn lại**; ROLLBACK toàn bộ và xử lý retry/idempotency phù hợp.

Trên PostgreSQL, `BEGIN`/`COMMIT`/`ROLLBACK` xác định ranh giới; `UPDATE ... WHERE so_du >= ... RETURNING` giúp xác minh thay đổi; PL/pgSQL `GET DIAGNOSTICS ROW_COUNT` và `RAISE EXCEPTION` giúp làm thất bại nghiệp vụ trở thành lỗi rõ ràng; JDBC/Spring đặt ranh giới và điều phối ở tầng service.

**Điểm quan trọng nhất:** một transaction có thể nguyên tử mà vẫn sai nghiệp vụ nếu không kiểm tra đủ số hàng và bất biến. Chỉ khi phối hợp **đúng ranh giới → đúng điều kiện → đúng bút toán → kiểm tra trước COMMIT → rollback khi thất bại**, thao tác chuyển tiền mới có nền tảng tin cậy để phát triển thành một hệ thống hoàn chỉnh.
