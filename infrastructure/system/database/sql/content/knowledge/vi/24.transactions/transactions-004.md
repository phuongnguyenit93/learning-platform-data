# SAVEPOINT, ROLLBACK TO và RELEASE SAVEPOINT trong giao dịch SQL

Khi xử lý một giao dịch gồm nhiều bước, không phải bước nào cũng có cùng mức độ bắt buộc. Ví dụ, ứng dụng đã xác nhận đơn hàng, sau đó thử thêm dịch vụ gói quà. Nếu gói quà không được chấp nhận, ứng dụng có thể muốn **hủy riêng dịch vụ** nhưng vẫn **giữ bước xác nhận đơn** trong giao dịch đang mở. SQL cung cấp **điểm lưu (*savepoint*)** để thực hiện kiểu hoàn nguyên một phần này.

Ba câu lệnh quan trọng trong PostgreSQL và một số DBMS khác:

~~~sql
BEGIN;
-- Phần bắt buộc của giao dịch.

SAVEPOINT truoc_buoc_tuy_chon;
-- Phần tùy chọn có thể thất bại.

ROLLBACK TO SAVEPOINT truoc_buoc_tuy_chon;
RELEASE SAVEPOINT truoc_buoc_tuy_chon;

COMMIT;
~~~

**SAVEPOINT** đặt một mốc trong transaction; **ROLLBACK TO** hoàn nguyên các thay đổi sau mốc nhưng giữ transaction mở; **RELEASE SAVEPOINT** loại bỏ điểm lưu khi không cần quay về đó nữa. **RELEASE không phải COMMIT của transaction cha.**

Bài học thuộc **Database SQL → Giao dịch SQL**, sử dụng PostgreSQL làm môi trường thực hành chính, sau đó giải thích cách dùng tương ứng ở MySQL/InnoDB, SQL Server, Oracle và SQLite. Các ví dụ tập trung vào ranh giới hoàn nguyên, xử lý lỗi, nested savepoints, transaction trong ứng dụng, khóa, DDL, sự khác biệt phương ngữ và tình huống thực tế.

## 1. Một giao dịch có thể có nhiều mức hoàn nguyên

Giả sử transaction thực hiện ba phần: A (xác nhận đơn), B (thêm gói quà), C (ghi thông tin cần thiết). Nếu đặt savepoint giữa A và B, sau đó phát hiện B không phù hợp, có thể rollback riêng B và tiếp tục C.

~~~mermaid
flowchart LR
    A["BEGIN"] --> B["Thực hiện A"]
    B --> C["SAVEPOINT p"]
    C --> D["Thực hiện B"]
    D --> E{"B hợp lệ?"}
    E -->|"Không"| F["ROLLBACK TO p"]
    E -->|"Có"| G["RELEASE p"]
    F --> H["Tiếp tục C"]
    G --> H
    H --> I{"Toàn transaction hợp lệ?"}
    I -->|"Có"| J["COMMIT"]
    I -->|"Không"| K["ROLLBACK toàn bộ"]
~~~

| Thời điểm | A | B | Transaction |
| --- | --- | --- | --- |
| Sau khi làm A và lập savepoint | Có, chưa commit | Chưa có | Đang mở |
| Sau khi làm B | Có, chưa commit | Có, chưa commit | Đang mở |
| Sau **ROLLBACK TO p** | **Còn** | **Bị hủy** | **Vẫn mở** |
| Sau **RELEASE p** mà không rollback B | Còn | Còn | **Vẫn mở** |
| Sau **COMMIT** | Được xác nhận | Được xác nhận nếu chưa bị hủy | Kết thúc |
| Sau **ROLLBACK** toàn bộ | Bị hủy | Bị hủy | Kết thúc |

Điểm quan trọng: savepoint là **ranh giới hoàn nguyên**, không phải một transaction độc lập. Bất cứ thay đổi nào chưa được commit của transaction bên ngoài vẫn có thể bị hủy bởi **ROLLBACK** toàn bộ, kể cả thay đổi đã nằm trước savepoint hoặc đã được **RELEASE**.

### 1.1. Phân biệt statement, savepoint và transaction

- **Statement**: một câu SQL như INSERT, UPDATE, DELETE. DBMS có quy tắc xử lý một câu lệnh thất bại.
- **Savepoint**: mốc ở bên trong transaction, có thể hoàn nguyên một chuỗi statement sau mốc.
- **Transaction**: đơn vị công việc được xác nhận bằng COMMIT hoặc hủy bằng ROLLBACK toàn bộ.

Ví dụ một câu INSERT sai không có nghĩa ta tự động được giữ một nửa số hàng do chính statement ấy dự định thêm. Savepoint thường được dùng để hoàn nguyên **những statement đã hoàn thành trước một lỗi khác** trong phạm vi sau mốc.

## 2. Cú pháp PostgreSQL và ý nghĩa từng lệnh

~~~sql
BEGIN;

SAVEPOINT ten_moc;

-- Một hoặc nhiều câu SQL thuộc phần có thể hủy.

ROLLBACK TO SAVEPOINT ten_moc;

-- Có thể tiếp tục thực hiện SQL ở đây.

RELEASE SAVEPOINT ten_moc;

COMMIT;
~~~

| Câu lệnh | Công dụng | Kết thúc transaction? |
| --- | --- | --- |
| `BEGIN` | Mở transaction tường minh | Không |
| `SAVEPOINT p` | Ghi dấu trạng thái transaction tại một mốc | Không |
| `ROLLBACK TO SAVEPOINT p` | Hoàn nguyên những thay đổi sau mốc p | **Không** |
| `RELEASE SAVEPOINT p` | Bỏ mốc p mà không tự hoàn nguyên thay đổi | **Không** |
| `COMMIT` | Xác nhận mọi thay đổi còn lại | **Có** |
| `ROLLBACK` | Hủy toàn bộ thay đổi chưa commit | **Có** |

Trong PostgreSQL có thể viết rút gọn:

~~~sql
ROLLBACK TO p;
RELEASE p;
~~~

Tuy nhiên, viết đủ từ **SAVEPOINT** giúp người học phân biệt với **ROLLBACK** kết thúc toàn transaction.

### 2.1. Savepoint thuộc connection và transaction hiện tại

Savepoint không phải bảng hoặc checkpoint có thể lưu trữ lâu dài. Nó tồn tại trong **một transaction của một session/connection**. Các trường hợp không hợp lệ về mô hình:

- Tạo savepoint trên connection A nhưng chạy ROLLBACK TO trên connection B.
- COMMIT transaction rồi tiếp tục gọi ROLLBACK TO mốc của transaction cũ.
- Mở connection mới ngày hôm sau và cố hoàn nguyên dữ liệu đã commit hôm trước.
- Đặt savepoint sau khi xảy ra lỗi rồi kỳ vọng mốc mới ghi nhớ trạng thái trước lỗi.

Đặc biệt trong PostgreSQL, nếu client dùng **autocommit** và không có khối **BEGIN ... COMMIT**, một SAVEPOINT gọi ngoài transaction tường minh không tạo được mốc hữu ích xuyên qua các câu SQL tiếp theo; PostgreSQL có thể cảnh báo.

### 2.2. Tên savepoint là định danh SQL

Ví dụ:

~~~sql
SAVEPOINT truoc_goi_qua;
SAVEPOINT truoc_ghi_nhat_ky;
SAVEPOINT truoc_tinh_chiet_khau;
~~~

Tên nên thể hiện **bước được bảo vệ**, thay vì chỉ đặt `a`, `x` hoặc `s1` trong mã ứng dụng phức tạp. Không tạo tên SQL trực tiếp bằng cách nối dữ liệu đầu vào của người dùng; dùng tên tĩnh hoặc tên được sinh an toàn theo quy tắc của driver.

## 3. Dữ liệu thực hành PostgreSQL

Các ví dụ dùng **bảng tạm** để không đụng dữ liệu nghiệp vụ thật. Bảng TEMP chỉ tồn tại trong phiên PostgreSQL tương ứng; hãy sử dụng cùng một connection khi chạy các ví dụ.

~~~sql
CREATE TEMP TABLE don_hang_sp (
    id INTEGER PRIMARY KEY,
    ten_khach TEXT NOT NULL,
    tong_tien NUMERIC(12, 2) NOT NULL CHECK (tong_tien >= 0),
    trang_thai TEXT NOT NULL DEFAULT 'MOI'
        CHECK (trang_thai IN ('MOI', 'DA_XAC_NHAN', 'DA_HUY'))
);

INSERT INTO don_hang_sp (id, ten_khach, tong_tien, trang_thai)
VALUES
    (101, 'An',   150000, 'MOI'),
    (102, 'Bình',  70000, 'MOI'),
    (103, 'Chi',  300000, 'MOI');

CREATE TEMP TABLE dich_vu_sp (
    id INTEGER PRIMARY KEY,
    don_hang_id INTEGER NOT NULL REFERENCES don_hang_sp(id),
    ma_dich_vu TEXT NOT NULL,
    phi NUMERIC(12, 2) NOT NULL CHECK (phi >= 0),
    CONSTRAINT uq_dich_vu_sp UNIQUE (don_hang_id, ma_dich_vu)
);

CREATE TEMP TABLE tai_khoan_sp (
    id INTEGER PRIMARY KEY,
    chu_so_huu TEXT NOT NULL,
    so_du NUMERIC(12, 2) NOT NULL CHECK (so_du >= 0)
);

INSERT INTO tai_khoan_sp (id, chu_so_huu, so_du)
VALUES
    (1, 'An',   500000),
    (2, 'Bình', 200000);
~~~

Dữ liệu gồm ba đơn hàng đang ở trạng thái **MOI**, một bảng dịch vụ bổ sung trống và hai tài khoản có số dư tổng 700.000.

| Bảng | Mức chi tiết | Ràng buộc đáng chú ý |
| --- | --- | --- |
| `don_hang_sp` | Một dòng trên mỗi đơn | Khóa chính, trạng thái hợp lệ |
| `dich_vu_sp` | Một dịch vụ trên một đơn | FK đến đơn, phí không âm, UNIQUE theo đơn và dịch vụ |
| `tai_khoan_sp` | Một dòng trên mỗi tài khoản | Khóa chính, số dư không âm |

~~~sql
SELECT id, trang_thai FROM don_hang_sp ORDER BY id;
SELECT id, don_hang_id, ma_dich_vu FROM dich_vu_sp ORDER BY id;
SELECT id, so_du FROM tai_khoan_sp ORDER BY id;
~~~

Nhiều ví dụ trong bài sẽ dùng **ROLLBACK toàn bộ ở cuối** để phục hồi dữ liệu mẫu. Những ví dụ dùng COMMIT được ghi chú riêng vì chúng làm thay đổi dữ liệu trong phiên thực hành.

## 4. Bài thực hành: giữ bước chính, hủy bước tùy chọn

Giả sử việc xác nhận đơn 101 là bắt buộc; gói quà là tùy chọn và khách đổi ý.

~~~sql
BEGIN;

UPDATE don_hang_sp
SET trang_thai = 'DA_XAC_NHAN'
WHERE id = 101;

-- Đặt mốc SAU khi đã làm bước bắt buộc.
SAVEPOINT truoc_goi_qua;

INSERT INTO dich_vu_sp (id, don_hang_id, ma_dich_vu, phi)
VALUES (1001, 101, 'GOI_QUA', 30000);

-- Hủy riêng phần vừa thêm.
ROLLBACK TO SAVEPOINT truoc_goi_qua;

-- Kiểm tra trong transaction vẫn mở.
SELECT id, trang_thai
FROM don_hang_sp
WHERE id = 101;

SELECT id, ma_dich_vu
FROM dich_vu_sp
WHERE id = 1001;

RELEASE SAVEPOINT truoc_goi_qua;

-- Chỉ dành cho demo: hủy tất cả để phục hồi dữ liệu mẫu.
ROLLBACK;
~~~

Ngay sau ROLLBACK TO:

- Đơn 101 đang là **DA_XAC_NHAN** trong transaction vì cập nhật diễn ra **trước savepoint**.
- Dịch vụ 1001 **không còn** vì được INSERT **sau savepoint**.
- Transaction vẫn **đang mở**.
- Savepoint vẫn có thể được tham chiếu cho đến khi RELEASE hoặc transaction kết thúc.

Sau ROLLBACK cuối, cả bước xác nhận đơn cũng bị hủy, đơn trở về MOI. Điều đó cho thấy rõ khác biệt giữa **ROLLBACK TO** và **ROLLBACK** toàn bộ.

### 4.1. Nếu muốn chấp nhận phần chính

Cùng tình huống nhưng chọn COMMIT sau khi hủy gói quà:

~~~sql
BEGIN;

UPDATE don_hang_sp
SET trang_thai = 'DA_XAC_NHAN'
WHERE id = 101;

SAVEPOINT optional_service;

INSERT INTO dich_vu_sp (id, don_hang_id, ma_dich_vu, phi)
VALUES (1002, 101, 'GOI_QUA', 30000);

ROLLBACK TO SAVEPOINT optional_service;
RELEASE SAVEPOINT optional_service;

COMMIT;
~~~

Sau COMMIT, đơn 101 giữ DA_XAC_NHAN, nhưng dịch vụ 1002 không tồn tại. **Nếu chạy đoạn này, trạng thái đơn 101 được thay đổi bền vững trong phiên thử**, nên những ví dụ tiếp theo muốn xuất phát từ MOI cần đặt lại dữ liệu hoặc dùng phiên mới.

### 4.2. Đặt mốc trước bước chính cho kết quả khác

~~~sql
BEGIN;

SAVEPOINT truoc_xac_nhan;

UPDATE don_hang_sp
SET trang_thai = 'DA_XAC_NHAN'
WHERE id = 102;

INSERT INTO dich_vu_sp (id, don_hang_id, ma_dich_vu, phi)
VALUES (1003, 102, 'GOI_QUA', 30000);

ROLLBACK TO SAVEPOINT truoc_xac_nhan;
RELEASE SAVEPOINT truoc_xac_nhan;
ROLLBACK;
~~~

Ở đây **cả UPDATE đơn 102 và INSERT dịch vụ 1003** đều bị hoàn nguyên vì cả hai nằm sau savepoint. SQL không hiểu bước nào quan trọng hơn; tác dụng của mốc phụ thuộc **vị trí đặt mốc**.

## 5. RELEASE SAVEPOINT không có nghĩa là COMMIT

Ví dụ:

~~~sql
BEGIN;

SAVEPOINT p1;

INSERT INTO dich_vu_sp (id, don_hang_id, ma_dich_vu, phi)
VALUES (1101, 101, 'GOI_QUA', 30000);

RELEASE SAVEPOINT p1;

-- Hàng vẫn xuất hiện trong transaction.
SELECT id FROM dich_vu_sp WHERE id = 1101;

-- Nhưng toàn transaction vẫn có thể bị hủy.
ROLLBACK;
~~~

Kết quả sau ROLLBACK cuối: dịch vụ 1101 **không tồn tại**. RELEASE chỉ có nghĩa **không còn cần mốc p1**; nó không làm dữ liệu an toàn trước một rollback toàn transaction.

Một cách nhớ:

| Lệnh | Có hủy thay đổi sau mốc? | Có bỏ mốc? | Có commit transaction cha? |
| --- | --- | --- | --- |
| `SAVEPOINT p` | Không | Tạo mốc | Không |
| `ROLLBACK TO p` | **Có** | **Giữ p** trong PostgreSQL | Không |
| `RELEASE p` | **Không** | **Có** | **Không** |
| `COMMIT` | Không | Tất cả mốc mất hiệu lực | **Có** |
| `ROLLBACK` | Hủy toàn bộ chưa commit | Tất cả mốc mất hiệu lực | Không, vì giao dịch bị hủy |

**Ngoại lệ của SQLite:** khi SAVEPOINT ngoài cùng được dùng **ngoài một BEGIN** để khởi đầu transaction, RELEASE điểm ngoài cùng ấy có thể commit. Cần phân biệt trường hợp đó với RELEASE điểm bên trong một transaction đã mở; xem mục phương ngữ.

### 5.1. Không quay về mốc đã release

~~~sql
BEGIN;
SAVEPOINT p;
RELEASE SAVEPOINT p;

-- Không hợp lệ: p không còn tồn tại.
-- ROLLBACK TO SAVEPOINT p;

ROLLBACK;
~~~

Nếu muốn có điểm quay lại cho các statement tương lai, phải đặt **savepoint mới trước các statement đó**.

## 6. ROLLBACK TO giữ chính điểm lưu trong PostgreSQL

Một điểm dễ bỏ sót: sau **ROLLBACK TO p**, savepoint **p còn tồn tại**, nên có thể dùng lại.

~~~sql
BEGIN;
SAVEPOINT thu_dich_vu;

INSERT INTO dich_vu_sp (id, don_hang_id, ma_dich_vu, phi)
VALUES (1201, 101, 'GOI_QUA', 30000);

ROLLBACK TO SAVEPOINT thu_dich_vu;

-- Thử phương án thứ hai.
INSERT INTO dich_vu_sp (id, don_hang_id, ma_dich_vu, phi)
VALUES (1202, 101, 'GOI_QUA', 20000);

ROLLBACK TO SAVEPOINT thu_dich_vu;

SELECT COUNT(*) AS so_dich_vu_con_lai
FROM dich_vu_sp
WHERE id IN (1201, 1202);

RELEASE SAVEPOINT thu_dich_vu;
ROLLBACK;
~~~

Cột `so_dich_vu_con_lai` bằng **0**; cả hai lần thử đều bị hoàn nguyên. Với PostgreSQL, một ROLLBACK TO mốc không tự động xóa mốc ấy.

Tuy vậy, không nên mở transaction trong hàng chục phút chỉ để thử vô số phương án thông qua savepoint. Một transaction dài có chi phí khóa, snapshot và tài nguyên riêng.

## 7. Nhiều savepoint lồng nhau

Một transaction có thể có nhiều điểm lưu:

~~~sql
BEGIN;

-- A: xác nhận đơn 101.
UPDATE don_hang_sp
SET trang_thai = 'DA_XAC_NHAN'
WHERE id = 101;

SAVEPOINT sau_a;

-- B: xác nhận đơn 102.
UPDATE don_hang_sp
SET trang_thai = 'DA_XAC_NHAN'
WHERE id = 102;

SAVEPOINT sau_b;

-- C: thêm dịch vụ.
INSERT INTO dich_vu_sp (id, don_hang_id, ma_dich_vu, phi)
VALUES (1301, 101, 'GOI_QUA', 30000);

-- Hủy C, giữ A và B.
ROLLBACK TO SAVEPOINT sau_b;
RELEASE SAVEPOINT sau_b;

-- Hủy B, còn A.
ROLLBACK TO SAVEPOINT sau_a;
RELEASE SAVEPOINT sau_a;

SELECT id, trang_thai
FROM don_hang_sp
WHERE id IN (101, 102)
ORDER BY id;

ROLLBACK;
~~~

Tại câu SELECT trong transaction, đơn 101 đã xác nhận; đơn 102 vẫn MOI; dịch vụ 1301 không có. ROLLBACK toàn bộ sau đó trả mọi thứ về trạng thái trước khi bắt đầu.

### 7.1. Quay về mốc cũ sẽ loại các mốc mới

Giả sử:

~~~text
BEGIN
  SAVEPOINT a
    SAVEPOINT b
      SAVEPOINT c
~~~

Khi chạy **ROLLBACK TO b** trên PostgreSQL:

- Những thay đổi sau b bị hoàn nguyên.
- Các savepoint tạo **sau b** (ở đây là c) bị loại bỏ.
- **b vẫn tồn tại**, có thể quay về tiếp.
- **a vẫn tồn tại**.

Khi chạy **RELEASE b**, PostgreSQL bỏ b và các mốc được thiết lập sau b, nhưng không hủy dữ liệu còn tồn tại trong transaction. Mốc a vẫn có thể dùng để hoàn nguyên phần thay đổi sau nó.

### 7.2. Theo dõi sự tồn tại của mốc

| Hành động | Mốc có thể tham chiếu sau hành động |
| --- | --- |
| Tạo a, rồi b, rồi c | a, b, c |
| ROLLBACK TO b | a, b |
| RELEASE b | a |
| ROLLBACK TO a | a |
| COMMIT hoặc ROLLBACK toàn bộ | Không còn mốc thuộc transaction đã kết thúc |

Các điểm lưu tạo một cấu trúc theo thứ tự thời gian, không phải ba bản sao độc lập của database.

## 8. Tên savepoint trùng nhau

Tên savepoint trùng có thể được xử lý **khác nhau giữa DBMS**.

Trong PostgreSQL, tạo savepoint mới cùng tên sẽ **che** mốc cũ khi tham chiếu theo tên; release mốc gần nhất có thể làm mốc cũ cùng tên được tham chiếu lại theo quy tắc PostgreSQL.

~~~sql
BEGIN;

SAVEPOINT thu;
UPDATE don_hang_sp
SET trang_thai = 'DA_XAC_NHAN'
WHERE id = 101;

SAVEPOINT thu;
UPDATE don_hang_sp
SET trang_thai = 'DA_XAC_NHAN'
WHERE id = 102;

ROLLBACK TO SAVEPOINT thu;  -- Mốc "thu" gần nhất.
RELEASE SAVEPOINT thu;

ROLLBACK TO SAVEPOINT thu;  -- Mốc "thu" cũ.
RELEASE SAVEPOINT thu;

ROLLBACK;
~~~

Trong MySQL, savepoint cùng tên sẽ **thay thế** mốc cũ cùng tên theo quy tắc InnoDB. Oracle có cơ chế tái định vị savepoint cùng tên; SQL Server cũng có quy tắc tham chiếu mốc cùng tên gần nhất.

**Khuyến nghị:** sử dụng tên rõ nghĩa và riêng biệt trong transaction, đặc biệt khi một framework hoặc thư viện cũng tự tạo savepoint.

## 9. Khôi phục sau lỗi SQL trong PostgreSQL

Trong PostgreSQL, nếu một câu SQL gặp lỗi bên trong transaction, transaction thường chuyển sang trạng thái **aborted**: những câu lệnh bình thường tiếp theo có thể bị từ chối với thông báo kiểu:

~~~text
current transaction is aborted,
commands ignored until end of transaction block
~~~

Nếu trước lỗi đã có một savepoint hợp lệ, **ROLLBACK TO** có thể phục hồi trạng thái transaction để tiếp tục những phần công việc còn được phép.

### 9.1. Ví dụ lỗi khóa ngoại

Chạy tuần tự các đoạn dưới đây trên **cùng connection**, không gộp thành một script tự động có chế độ dừng ngay khi lỗi:

~~~sql
BEGIN;

UPDATE don_hang_sp
SET trang_thai = 'DA_XAC_NHAN'
WHERE id = 101;

SAVEPOINT truoc_tuy_chon;

INSERT INTO dich_vu_sp (id, don_hang_id, ma_dich_vu, phi)
VALUES (1401, 101, 'GOI_QUA', 30000);
~~~

Câu tiếp theo **cố ý thất bại** vì đơn 999 không tồn tại:

~~~sql
INSERT INTO dich_vu_sp (id, don_hang_id, ma_dich_vu, phi)
VALUES (1402, 999, 'BAO_HIEM', 10000);
~~~

Sau khi PostgreSQL báo lỗi, sử dụng:

~~~sql
ROLLBACK TO SAVEPOINT truoc_tuy_chon;

SELECT id FROM dich_vu_sp WHERE id IN (1401, 1402);
SELECT id, trang_thai FROM don_hang_sp WHERE id = 101;

RELEASE SAVEPOINT truoc_tuy_chon;
ROLLBACK;
~~~

Trong transaction sau rollback-to:

- Dịch vụ 1401 (được chèn thành công nhưng **sau mốc**) cũng bị hủy.
- Dịch vụ 1402 không được tạo vì vi phạm khóa ngoại.
- Đơn 101 vẫn đang DA_XAC_NHAN vì được sửa **trước mốc**.
- Transaction có thể chạy câu SQL bình thường trở lại.

**Lưu ý client:** một số công cụ như psql ở chế độ dừng trên lỗi, trình chạy migration, ORM hoặc driver có thể ngắt cả chuỗi câu SQL khi nhận lỗi. Ứng dụng cần bắt exception và chủ động gửi ROLLBACK TO trên connection phù hợp khi error class cho phép tiếp tục.

### 9.2. Không thể tạo mốc sau lỗi để cứu quá khứ

Nếu transaction PostgreSQL đã aborted và trước lỗi **không có savepoint**, bạn không thể giả định đặt một savepoint mới rồi rollback-to để phục hồi trạng thái trước lỗi. Cách thông thường là **ROLLBACK toàn transaction và bắt đầu lại**.

Mốc phải được thiết lập **trước các thao tác có thể cần hoàn nguyên**.

### 9.3. RELEASE không giải quyết lỗi

Sau lỗi, **RELEASE p** không phải lệnh thay thế cho **ROLLBACK TO p**. Release không hoàn nguyên statement có vấn đề. Trên PostgreSQL, khi transaction đã aborted, cần sử dụng cách phục hồi giao dịch hợp lệ như ROLLBACK TO savepoint đã được tạo trước lỗi hoặc ROLLBACK toàn bộ.

### 9.4. Không phải mọi lỗi đều cứu được bằng savepoint

Một số lỗi có thể làm connection bị mất, backend bị kết thúc, server phải hủy transaction, hoặc transaction không còn trạng thái cho phép tiếp tục. Trong tình huống đó không có transaction còn sống để rollback về mốc.

Vì vậy, chương trình phải phân loại **lỗi constraint có thể xử lý**, **lỗi xung đột cần retry**, **lỗi giao dịch/connection nghiêm trọng**, thay vì âm thầm bỏ mọi SQLException.

## 10. Statement atomicity khác rollback một nhóm statement

Giả sử một thao tác gồm ba câu:

~~~text
SAVEPOINT p
  INSERT A
  UPDATE B
  INSERT C
~~~

Nếu INSERT C thất bại, **ROLLBACK TO p** hoàn nguyên cả A và B nếu chúng đã thực hiện thành công sau p. Đây là tính chất hữu ích khi muốn hủy **cả nhóm**.

Nếu yêu cầu là **giữ A và B nhưng hủy riêng C**, hãy đặt một savepoint khác **ngay trước C**, hoặc tách nhóm theo thiết kế.

~~~sql
BEGIN;

SAVEPOINT truoc_nhom;
UPDATE don_hang_sp
SET trang_thai = 'DA_XAC_NHAN'
WHERE id = 101;

SAVEPOINT truoc_dich_vu;
INSERT INTO dich_vu_sp (id, don_hang_id, ma_dich_vu, phi)
VALUES (1501, 101, 'GOI_QUA', 30000);

ROLLBACK TO SAVEPOINT truoc_dich_vu;
RELEASE SAVEPOINT truoc_dich_vu;

-- Bước xác nhận đơn vẫn còn trong transaction.
SELECT id, trang_thai FROM don_hang_sp WHERE id = 101;

ROLLBACK TO SAVEPOINT truoc_nhom;
RELEASE SAVEPOINT truoc_nhom;
ROLLBACK;
~~~

Mỗi savepoint bảo vệ **phạm vi thời gian** từ lúc tạo mốc, không phải tự chọn các dòng thuộc một chức năng nghiệp vụ.

## 11. SAVEPOINT không phải nested COMMIT

Có khi người ta gọi savepoint là “nested transaction”. Cách nói này tiện nhưng **không hoàn toàn chính xác**.

| Thuộc tính | Savepoint | Transaction độc lập thực sự |
| --- | --- | --- |
| Có mốc rollback riêng | Có | Có |
| Commit bền vững không cần transaction cha | **Không** | Có thể, tùy cơ chế |
| Bị ROLLBACK toàn transaction cha hủy | **Có** | Không nhất thiết với autonomous transaction |
| Thuộc cùng connection/transaction cha | Có | Có thể khác tùy mô hình |
| Dùng để bảo vệ một nhóm statement tùy chọn | Phù hợp | Có thể quá mạnh và gây vấn đề nhất quán |

Ví dụ:

~~~text
BEGIN
  Cập nhật A
  SAVEPOINT p
    Cập nhật B
  RELEASE p
  Cập nhật C
ROLLBACK
~~~

Kết quả: **A, B và C đều bị hủy**. RELEASE không biến B thành dữ liệu đã commit.

### 11.1. Gọi BEGIN lần nữa không thay cho SAVEPOINT

Trong PostgreSQL, một BEGIN khi transaction đã mở không tạo transaction bên trong độc lập với rollback riêng. Trong SQL Server, nhiều BEGIN TRANSACTION làm tăng @@TRANCOUNT nhưng cũng không nên coi là hệ thống nested transaction với commit độc lập hoàn toàn.

Muốn rollback một đoạn thay đổi trong transaction, dùng cơ chế savepoint tương ứng của DBMS.

## 12. Ranh giới nghiệp vụ: ví dụ chuyển tiền

Chuyển 100.000 từ An sang Bình gồm **hai bước bắt buộc**:

1. Trừ 100.000 khỏi An;
2. Cộng 100.000 cho Bình.

Hai bước **phải cùng thành công** theo nghiệp vụ chuyển khoản. Phần thêm dịch vụ hoặc ghi chú có thể là bước tùy chọn **sau hai bước bắt buộc**.

~~~sql
BEGIN;

UPDATE tai_khoan_sp
SET so_du = so_du - 100000
WHERE id = 1 AND so_du >= 100000;

UPDATE tai_khoan_sp
SET so_du = so_du + 100000
WHERE id = 2;

SAVEPOINT truoc_tuy_chon;

INSERT INTO dich_vu_sp (id, don_hang_id, ma_dich_vu, phi)
VALUES (1601, 101, 'GOI_QUA', 10000);

ROLLBACK TO SAVEPOINT truoc_tuy_chon;
RELEASE SAVEPOINT truoc_tuy_chon;

SELECT id, so_du FROM tai_khoan_sp ORDER BY id;

ROLLBACK;
~~~

Ngay trước ROLLBACK toàn bộ, hai số dư là **400.000** và **300.000**, tổng 700.000; dịch vụ 1601 đã bị hủy.

**Cảnh báo:** đây là bài minh họa vị trí savepoint, **không phải chương trình tài chính production**. Ứng dụng thật phải kiểm tra số hàng bị ảnh hưởng sau mỗi UPDATE, bảo vệ thao tác đồng thời, có bút toán đối ứng, chống thực thi trùng, khóa/idempotency và các ràng buộc nghiệp vụ khác.

Nếu câu trừ tiền tác động **0 hàng** vì không đủ số dư, không được tiếp tục cộng tiền như thể chuyển khoản thành công.

### 12.1. Cách đặt mốc nguy hiểm

~~~text
BEGIN
Trừ 100.000 của An
SAVEPOINT p
Cộng 100.000 cho Bình
Nếu câu cộng lỗi: ROLLBACK TO p
COMMIT
~~~

Nếu thực thi theo hướng trên, có nguy cơ **commit bước trừ tiền nhưng bỏ bước cộng tiền**. Cú pháp SAVEPOINT không thể thay thế việc xác định **ranh giới nguyên tử của nghiệp vụ**.

## 13. Import dữ liệu có các bước tùy chọn

Trong quá trình nhập hàng loạt, đôi khi mỗi bản ghi có một phần bổ sung không quan trọng. Có thể tạo savepoint trước phần tùy chọn, rồi chọn commit hoặc rollback nhóm ấy.

~~~sql
BEGIN;

SAVEPOINT dich_vu_mot;
INSERT INTO dich_vu_sp (id, don_hang_id, ma_dich_vu, phi)
VALUES (1701, 101, 'GOI_QUA', 30000);
RELEASE SAVEPOINT dich_vu_mot;

SAVEPOINT dich_vu_hai;
INSERT INTO dich_vu_sp (id, don_hang_id, ma_dich_vu, phi)
VALUES (1702, 101, 'BAO_HIEM', 10000);
RELEASE SAVEPOINT dich_vu_hai;

SAVEPOINT dich_vu_ba;
INSERT INTO dich_vu_sp (id, don_hang_id, ma_dich_vu, phi)
VALUES (1703, 101, 'THIEP_CHUC_MUNG', 5000);
ROLLBACK TO SAVEPOINT dich_vu_ba;
RELEASE SAVEPOINT dich_vu_ba;

SELECT id, ma_dich_vu
FROM dich_vu_sp
WHERE id IN (1701, 1702, 1703)
ORDER BY id;

ROLLBACK;
~~~

Trong transaction, chỉ có hai dịch vụ đầu; dịch vụ thứ ba đã bị hoàn nguyên. Nếu COMMIT, hai dịch vụ đầu sẽ còn tồn tại.

### 13.1. Một savepoint mỗi hàng không phải luôn tốt

Với hàng triệu dòng, tạo quá nhiều savepoint trong transaction dài có thể làm tăng metadata, thời gian giữ khóa và tài nguyên transaction. Nên cân nhắc:

- Validate và chuẩn hóa trước khi ghi;
- Dùng staging table để phân loại hàng hợp lệ;
- Chia batch và COMMIT ở những ranh giới phù hợp;
- Sử dụng cơ chế upsert/ignore conflict nếu đúng nghiệp vụ;
- Dùng tính năng bulk insert và báo lỗi theo dòng của công cụ/driver tương ứng.

Nếu yêu cầu là **toàn file thành công hoặc toàn file thất bại**, không nên tùy tiện COMMIT từng batch. Nếu được phép thành công một phần, cần **báo rõ dòng thành công, dòng lỗi và cách khôi phục**.

### 13.2. Ghi log lỗi ở đâu?

Log lỗi được INSERT vào **cùng transaction** vẫn có thể bị ROLLBACK toàn bộ, dù đoạn log đã được RELEASE khỏi một savepoint. Muốn lưu log bền vững khi giao dịch chính thất bại, cần thiết kế cách ghi log **sau transaction** hoặc ở một cơ chế độc lập phù hợp; phải cân nhắc nhất quán giữa log và dữ liệu.

## 14. SAVEPOINT không vô hiệu hóa ràng buộc

Ràng buộc UNIQUE, FOREIGN KEY, CHECK và NOT NULL vẫn áp dụng trong transaction. Savepoint chỉ giúp **quay về trước thao tác sai**, không làm thao tác đó trở nên hợp lệ.

~~~sql
BEGIN;
SAVEPOINT truoc_dich_vu;

INSERT INTO dich_vu_sp (id, don_hang_id, ma_dich_vu, phi)
VALUES (1801, 101, 'GOI_QUA', 30000);

-- Nếu chạy, câu sau vi phạm UNIQUE (don_hang_id, ma_dich_vu):
-- INSERT INTO dich_vu_sp
--     (id, don_hang_id, ma_dich_vu, phi)
-- VALUES (1802, 101, 'GOI_QUA', 40000);

ROLLBACK TO SAVEPOINT truoc_dich_vu;
RELEASE SAVEPOINT truoc_dich_vu;
ROLLBACK;
~~~

Khi quay về trước INSERT 1801, cặp UNIQUE vừa sử dụng không còn tồn tại trong transaction, nên có thể thử một giá trị khác khi không có xung đột bên ngoài.

### 14.1. Ràng buộc có thể được kiểm tra ở COMMIT

PostgreSQL hỗ trợ **DEFERRABLE constraints** ở những loại constraint phù hợp. Một số vi phạm có thể được kiểm tra muộn khi đổi chế độ constraint hoặc khi COMMIT.

Nếu lỗi chỉ xuất hiện khi transaction đã chuẩn bị kết thúc, không thể mặc định sẽ có cơ hội “rollback tới savepoint sau COMMIT”. Khi nghiệp vụ cần kiểm tra sớm để xử lý bằng savepoint, có thể phải **chủ động thực hiện kiểm tra constraints ở thời điểm thích hợp trước COMMIT**, trong phạm vi DBMS cho phép.

## 15. SAVEPOINT và cơ chế khóa

Rollback về savepoint có thể ảnh hưởng đến **khóa** đã được lấy trong transaction. Đây là phần có khác biệt đáng kể giữa các hệ quản trị.

### 15.1. PostgreSQL

Ở PostgreSQL, khóa được lấy **sau savepoint** thường có thể được giải phóng khi rollback về mốc tương ứng, trong khi khóa lấy **trước mốc** tiếp tục được giữ theo quy tắc transaction.

~~~sql
BEGIN;

SELECT id FROM don_hang_sp WHERE id = 101 FOR UPDATE;

SAVEPOINT sau_khoa_101;

SELECT id FROM don_hang_sp WHERE id = 102 FOR UPDATE;

ROLLBACK TO SAVEPOINT sau_khoa_101;
RELEASE SAVEPOINT sau_khoa_101;

ROLLBACK;
~~~

Đừng suy rằng sau ROLLBACK TO, transaction không còn giữ bất kỳ khóa nào: khóa hàng 101 đã có **trước mốc** có thể vẫn còn.

### 15.2. MySQL/InnoDB

Trong InnoDB, ROLLBACK TO SAVEPOINT hoàn nguyên dữ liệu, nhưng **không nhất thiết giải phóng tất cả row lock được lưu trong bộ nhớ sau savepoint**. Những trường hợp khóa liên quan đến hàng mới chèn có cơ chế riêng. Vì vậy, không sao chép giả định về việc giải phóng khóa từ PostgreSQL sang MySQL.

### 15.3. SQL Server

SQL Server có quy tắc riêng: rollback đến savepoint có thể nhả khóa sau điểm lưu, **ngoại trừ một số lock escalation và conversion**; những khóa này không nhất thiết quay trở về mức cũ. Ngoài ra transaction có thể rơi vào trạng thái uncommittable mà rollback-to không cứu được.

### 15.4. Savepoint không ngăn lost update

Nếu hai transaction cùng thay đổi một hàng, savepoint không tự giải quyết **lost update**, deadlock, phantom hoặc race condition. Vẫn cần khóa, cột version, kiểm tra affected rows, isolation level và thiết kế concurrency thích hợp.

## 16. Điều gì KHÔNG được hoàn nguyên?

Một savepoint chỉ quản lý phạm vi transaction database. Không phải mọi hiệu ứng xảy ra sau savepoint đều rollback được.

| Hiệu ứng | ROLLBACK TO có tự hoàn nguyên? | Lý do |
| --- | --- | --- |
| INSERT/UPDATE/DELETE hàng thông thường thuộc transaction | Thông thường **có** nếu sau mốc | Dữ liệu nằm trong transaction |
| Giá trị PostgreSQL sequence đã cấp bằng `nextval()` | **Không** | Sequence allocation không rollback cùng row DML |
| Email đã gửi | **Không** | Hệ thống email ở ngoài database |
| HTTP request đã gọi | **Không** | API ngoài có transaction riêng |
| File đã ghi lên filesystem | **Không tự động** | Không thuộc transaction SQL |
| Thay đổi session khác đã COMMIT | **Không** | Không thuộc transaction hiện tại |
| DDL gây implicit COMMIT | **Không theo cách mong muốn** | Transaction/mốc có thể đã kết thúc |
| Autonomous transaction đã COMMIT trong Oracle | **Không cùng transaction cha** | Có ranh giới commit độc lập |

### 16.1. Sequence không quay ngược

Ví dụ PostgreSQL:

~~~sql
CREATE TEMP SEQUENCE so_demo_sp START WITH 1;

BEGIN;
SAVEPOINT truoc_cap_so;

SELECT nextval('so_demo_sp') AS so_dau;

ROLLBACK TO SAVEPOINT truoc_cap_so;
RELEASE SAVEPOINT truoc_cap_so;

SELECT nextval('so_demo_sp') AS so_tiep;

ROLLBACK;
~~~

Lần gọi tiếp theo không nhất thiết trả lại số lần đầu. Khoảng trống trong sequence/IDENTITY có thể xuất hiện dù transaction được rollback. Không dùng savepoint để “đảm bảo ID liên tiếp tuyệt đối”.

### 16.2. Email không thể thu hồi bằng ROLLBACK TO

~~~text
BEGIN
  SAVEPOINT p
  UPDATE đơn hàng
  Gửi email "đơn đã xác nhận"
  ROLLBACK TO p
COMMIT
~~~

Database có thể không giữ UPDATE, nhưng email **đã gửi**. Khi cần đồng bộ DB với thông báo, cân nhắc **transactional outbox**, idempotency và cách phát sự kiện sau commit; savepoint không thay thế thiết kế nhất quán giữa các hệ thống.

## 17. DDL và implicit COMMIT

### 17.1. PostgreSQL: nhiều DDL thuộc transaction

Trong PostgreSQL, nhiều DDL thông dụng có thể được rollback khi nằm trong transaction:

~~~sql
BEGIN;
SAVEPOINT truoc_bang_thu;

CREATE TEMP TABLE bang_thu_sau_savepoint (
    id INTEGER PRIMARY KEY
);

ROLLBACK TO SAVEPOINT truoc_bang_thu;
RELEASE SAVEPOINT truoc_bang_thu;
ROLLBACK;
~~~

Bảng tạm được tạo sau mốc có thể bị hoàn nguyên và không còn tồn tại sau ROLLBACK TO. **Tuy nhiên không phải mọi lệnh PostgreSQL đều được phép chạy trong transaction block**, đặc biệt một số lệnh quản trị.

### 17.2. MySQL và Oracle: nhiều DDL implicit COMMIT

Nhiều câu **CREATE TABLE, ALTER TABLE** và DDL khác trong MySQL hoặc Oracle có thể gây **implicit COMMIT** theo quy tắc của server. Khi ấy savepoint trước DDL không còn để rollback theo cách mong đợi.

~~~sql
-- Không coi đây là mô hình dùng chung mọi DBMS:
-- BEGIN;
-- SAVEPOINT p;
-- ALTER TABLE ...;
-- ROLLBACK TO SAVEPOINT p;
~~~

Cần xác nhận hỗ trợ transactional DDL theo **DBMS và phiên bản**, nhất là khi thực hiện migration schema.

## 18. MySQL/InnoDB và MariaDB

Với bảng sử dụng storage engine giao dịch như InnoDB:

~~~sql
START TRANSACTION;

UPDATE don_hang
SET trang_thai = 'DA_XAC_NHAN'
WHERE id = 101;

SAVEPOINT truoc_dich_vu;

INSERT INTO dich_vu
    (id, don_hang_id, ma_dich_vu, phi)
VALUES
    (1901, 101, 'GOI_QUA', 30000);

ROLLBACK TO SAVEPOINT truoc_dich_vu;
RELEASE SAVEPOINT truoc_dich_vu;

COMMIT;
~~~

Đoạn này là **mẫu MySQL/MariaDB**, giả định bảng tương ứng đã được tạo. Cú pháp cốt lõi của SAVEPOINT, ROLLBACK TO và RELEASE khá gần PostgreSQL.

Những điểm cần chú ý:

- Cần **transaction đang hoạt động**; bắt đầu rõ bằng START TRANSACTION hoặc cấu hình autocommit phù hợp.
- Các bảng cần dùng **engine hỗ trợ transaction**. Không giả định mọi engine cho phép rollback dữ liệu.
- Nếu SAVEPOINT cùng tên đã tồn tại, MySQL có thể **thay thế mốc cũ**.
- Nhiều DDL gây **implicit COMMIT**.
- InnoDB có **quy tắc giữ/nhả row lock** khác PostgreSQL sau rollback-to.
- Không nhầm RELEASE SAVEPOINT với COMMIT của transaction ngoài cùng.

## 19. SQL Server: SAVE TRANSACTION thay cho SAVEPOINT

SQL Server sử dụng **SAVE TRANSACTION** để tạo mốc, và **ROLLBACK TRANSACTION tên_mốc** để quay về đó:

~~~sql
BEGIN TRANSACTION;

UPDATE dbo.DonHang
SET TrangThai = N'DA_XAC_NHAN'
WHERE Id = 101;

SAVE TRANSACTION TruocDichVu;

INSERT INTO dbo.DichVu
    (Id, DonHangId, MaDichVu, Phi)
VALUES
    (2001, 101, N'GOI_QUA', 30000);

ROLLBACK TRANSACTION TruocDichVu;

COMMIT TRANSACTION;
~~~

Đây là **T-SQL**, không chạy trên PostgreSQL. SQL Server **không có RELEASE SAVEPOINT tương đương trực tiếp** trong cú pháp SQL thông thường.

### 19.1. SAVE TRANSACTION không tăng @@TRANCOUNT

~~~sql
BEGIN TRANSACTION;
SAVE TRANSACTION p;
ROLLBACK TRANSACTION p;
COMMIT TRANSACTION;
~~~

SAVE TRANSACTION không phải BEGIN TRANSACTION lồng thực sự. **ROLLBACK TRANSACTION p** không giảm @@TRANCOUNT như rollback toàn bộ transaction.

### 19.2. XACT_STATE và lỗi không thể phục hồi cục bộ

SQL Server có hàm `XACT_STATE()`:

| Giá trị | Tình trạng transaction | Cách nhìn |
| ---: | --- | --- |
| 1 | Transaction tồn tại, có thể commit | Có thể cân nhắc rollback đến savepoint hợp lệ |
| 0 | Không có transaction hoạt động | Không có savepoint transaction để rollback |
| -1 | Transaction uncommittable | Không thể rollback-to rồi commit; cần rollback toàn bộ |

Mẫu xử lý trong T-SQL CATCH (phải gắn với hợp đồng **ai sở hữu transaction**):

~~~sql
IF XACT_STATE() = 1
BEGIN
    ROLLBACK TRANSACTION TruocDichVu;
END
ELSE IF XACT_STATE() = -1
BEGIN
    ROLLBACK TRANSACTION;
END;
~~~

Một số lỗi, đặc biệt với thiết lập XACT_ABORT và hành vi tương ứng, có thể đặt transaction vào trạng thái không thể commit. Không mặc định **mọi lỗi trong TRY...CATCH đều cứu được bằng savepoint**. Nếu procedure được gọi trong transaction của caller, phải tránh tùy tiện full rollback/commit transaction thuộc caller mà không có hợp đồng rõ.

### 19.3. Tên mốc trùng và giới hạn

SQL Server có thể dùng tên mốc trùng; ROLLBACK TRANSACTION theo tên thường hướng đến mốc gần nhất thích hợp. Có những giới hạn đối với savepoint trong distributed transaction; cần đọc tài liệu chính thức khi sử dụng TransactionScope hoặc giao dịch phân tán.

## 20. Oracle Database: SAVEPOINT và ROLLBACK TO

Oracle có mẫu:

~~~sql
-- Giả định bảng DON_HANG và DICH_VU đã tồn tại.
UPDATE don_hang
SET trang_thai = 'DA_XAC_NHAN'
WHERE id = 101;

SAVEPOINT truoc_dich_vu;

INSERT INTO dich_vu
    (id, don_hang_id, ma_dich_vu, phi)
VALUES
    (2101, 101, 'GOI_QUA', 30000);

ROLLBACK TO SAVEPOINT truoc_dich_vu;

COMMIT;
~~~

Oracle **không có câu RELEASE SAVEPOINT trực tiếp như PostgreSQL**. SAVEPOINT được quản lý trong transaction; commit/rollback toàn bộ làm các mốc mất hiệu lực.

Trong Oracle SQL, DML thường bắt đầu một transaction theo quy tắc của Oracle; đừng sao chép **BEGIN;** trong PostgreSQL sang Oracle với kỳ vọng đó là cú pháp bắt đầu transaction tương đương. Trong PL/SQL, **BEGIN ... END** là cấu trúc block, khác ý nghĩa BEGIN TRANSACTION của PostgreSQL.

### 20.1. Oracle và DDL

Nhiều DDL Oracle có **implicit COMMIT**. Nếu tạo savepoint rồi thực thi DDL gây commit, không thể tiếp tục rollback về mốc trước như thể DDL là một thay đổi giao dịch PostgreSQL thông thường.

### 20.2. Autonomous transaction

Một **autonomous transaction** trong PL/SQL có thể commit độc lập. Nếu procedure hoặc trigger sử dụng cơ chế đó, rollback về savepoint trong transaction gọi nó **không tự hủy thay đổi đã được autonomous transaction commit**. Đây là khác biệt quan trọng khi hệ thống có audit/log độc lập.

## 21. SQLite: trường hợp RELEASE ngoài cùng có thể COMMIT

SQLite hỗ trợ:

~~~sql
BEGIN;

SAVEPOINT p;
-- Các thay đổi SQLite.
ROLLBACK TO SAVEPOINT p;
RELEASE SAVEPOINT p;

COMMIT;
~~~

Khi SAVEPOINT nằm bên trong một transaction mở bằng BEGIN, RELEASE p **không commit transaction bên ngoài**.

Nhưng SQLite có khả năng đặc biệt: **SAVEPOINT ngoài cùng, khi chưa có BEGIN**, có thể **tự mở một transaction**:

~~~sql
-- SQLite, không có BEGIN trước đoạn này.
SAVEPOINT transaction_ngoai_cung;

INSERT INTO don_hang (id, trang_thai)
VALUES (2201, 'MOI');

RELEASE SAVEPOINT transaction_ngoai_cung;
~~~

Trong trường hợp đó, RELEASE điểm lưu ngoài cùng **có thể commit transaction mà nó đã mở**.

Phân biệt rõ:

| SQLite | Tác dụng RELEASE |
| --- | --- |
| SAVEPOINT p bên trong BEGIN ... COMMIT | Chỉ bỏ mốc p; transaction BEGIN vẫn mở |
| SAVEPOINT p ngoài BEGIN, là savepoint ngoài cùng khởi đầu transaction | RELEASE ngoài cùng có thể kết thúc/commit transaction |
| ROLLBACK TO p | Hoàn nguyên về p, **không tự kết thúc transaction**, giữ mốc theo quy tắc SQLite |

SQLite có cơ chế khóa/writer transaction và handling lỗi riêng. Không giả định SQLite có mọi khả năng nested DML CTE hoặc khóa theo hàng như PostgreSQL.

## 22. Bảng so sánh cú pháp và semantics

| Khía cạnh | PostgreSQL | MySQL/InnoDB | SQL Server | Oracle | SQLite |
| --- | --- | --- | --- | --- | --- |
| Tạo điểm lưu | `SAVEPOINT p` | `SAVEPOINT p` | `SAVE TRANSACTION p` | `SAVEPOINT p` | `SAVEPOINT p` |
| Quay về mốc | `ROLLBACK TO SAVEPOINT p` | `ROLLBACK TO SAVEPOINT p` | `ROLLBACK TRANSACTION p` | `ROLLBACK TO SAVEPOINT p` | `ROLLBACK TO SAVEPOINT p` |
| Có RELEASE SAVEPOINT trực tiếp? | Có | Có | **Không** | **Không** | Có |
| Quay về mốc giữ transaction mở? | Có | Có | Có nếu transaction còn hợp lệ | Có | Có |
| RELEASE điểm lưu bên trong có commit cha? | Không | Không | Không áp dụng | Không áp dụng | Không |
| SAVEPOINT ngoài BEGIN có thể mở transaction? | Không theo cách dùng thông thường | Cần transaction có hiệu lực | Cần transaction | Transaction được quản lý theo DML | **Có** |
| DDL thường có implicit COMMIT? | Nhiều DDL transactional, có ngoại lệ | Có nhiều trường hợp | Tùy lệnh/thiết lập | Có nhiều trường hợp | Nhiều DDL transactional, có ngoại lệ |
| Sau lỗi SQL có điều kiện phục hồi riêng? | Lỗi thường làm transaction aborted; dùng ROLLBACK TO trước lỗi | Tùy loại lỗi/engine | Xét XACT_STATE | Theo quy tắc Oracle | Theo loại lỗi/conflict mode |

Không nên chỉ thay tên câu lệnh khi chuyển DBMS: cần xem **quy tắc lỗi, transaction state, DDL, locks, tên trùng và khả năng hỗ trợ của driver**.

## 23. Java/JDBC: quản lý savepoint qua Connection

Trong Java, JDBC cung cấp các thao tác:

- `Connection.setAutoCommit(false)`;
- `Connection.setSavepoint(name)`;
- `Connection.rollback(savepoint)`;
- `Connection.releaseSavepoint(savepoint)`;
- `Connection.commit()` hoặc `Connection.rollback()`.

Mẫu Java dùng PostgreSQL và các bảng tạm trong cùng connection:

~~~java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.Savepoint;
import java.sql.SQLException;
import javax.sql.DataSource;

public final class XuLyGiaoDich {
    public static void xacNhan(DataSource ds, int donId)
            throws SQLException {
        try (Connection conn = ds.getConnection()) {
            boolean oldAutoCommit = conn.getAutoCommit();
            conn.setAutoCommit(false);

            try {
                // Phần bắt buộc.
                try (PreparedStatement ps = conn.prepareStatement(
                        "UPDATE don_hang_sp " +
                        "SET trang_thai = 'DA_XAC_NHAN' " +
                        "WHERE id = ? AND trang_thai = 'MOI'")) {
                    ps.setInt(1, donId);
                    int count = ps.executeUpdate();
                    if (count != 1) {
                        throw new SQLException(
                                "Không xác nhận đúng một đơn");
                    }
                }

                // Phần gói quà được phép bỏ nếu gặp lỗi dữ liệu.
                Savepoint beforeOptional =
                        conn.setSavepoint("truoc_goi_qua");

                try {
                    try (PreparedStatement ps = conn.prepareStatement(
                            "INSERT INTO dich_vu_sp " +
                            "(id, don_hang_id, ma_dich_vu, phi) " +
                            "VALUES (?, ?, ?, ?)")) {
                        ps.setInt(1, 2301);
                        ps.setInt(2, donId);
                        ps.setString(3, "GOI_QUA");
                        ps.setBigDecimal(4,
                            new java.math.BigDecimal("30000"));
                        ps.executeUpdate();
                    }
                    conn.releaseSavepoint(beforeOptional);
                } catch (SQLException optionalError) {
                    // Chỉ làm thế này khi nghiệp vụ thực sự cho phép
                    // bỏ phần tùy chọn và lỗi có thể phục hồi.
                    conn.rollback(beforeOptional);
                    conn.releaseSavepoint(beforeOptional);
                }

                conn.commit();
            } catch (SQLException | RuntimeException mainError) {
                try {
                    conn.rollback();
                } catch (SQLException rollbackError) {
                    mainError.addSuppressed(rollbackError);
                }
                throw mainError;
            } finally {
                conn.setAutoCommit(oldAutoCommit);
            }
        }
    }
}
~~~

Đây là **mẫu khái niệm JDBC** chứ chưa phải code production dùng nguyên xi cho mọi DBMS. Nó giả định driver hỗ trợ named savepoint/release, phần gói quà thật sự có thể bỏ, connection đã mở tới đúng database và bảng tạm tồn tại trong session ấy. Trong ứng dụng thật, cần phân loại SQLException trước khi quyết định chỉ rollback phần tùy chọn.

### 23.1. Không nuốt mọi SQLException

Lỗi ràng buộc dữ liệu của bước tùy chọn có thể được xử lý cục bộ. Nhưng lỗi mất kết nối, backend bị dừng, transaction đã bị hủy hoặc lỗi hệ thống nghiêm trọng phải được **đưa ra tầng xử lý transaction**, không âm thầm bỏ qua rồi báo thành công.

### 23.2. Cùng connection

Savepoint thuộc transaction của **một connection**. Kết nối A tạo savepoint thì kết nối B **không thể** rollback về mốc ấy. Khi dùng connection pool, ORM hoặc transaction manager, cần để một **transaction owner** điều phối connection và ranh giới commit.

### 23.3. releaseSavepoint phụ thuộc driver/DBMS

JDBC có API release, nhưng SQL Server và Oracle không có cú pháp RELEASE tương đương trực tiếp trong SQL thông thường. Kiểm tra hành vi/hỗ trợ của driver nếu chương trình muốn chạy nhiều DBMS.

### 23.4. Auto-commit khi cleanup

Một số driver có thể commit transaction còn mở khi chuyển từ auto-commit false sang true. Vì thế, trước khi khôi phục chế độ connection, phải đảm bảo **transaction đã được commit hoặc rollback có chủ đích**. Tránh để lỗi cleanup che mất lỗi thực sự; với connection pool còn phải đảm bảo connection không trở lại pool trong trạng thái giao dịch mơ hồ.

## 24. Framework/ORM và nested transaction

Một framework có thể cung cấp cú pháp **nested transaction** nhưng triển khai dưới dạng savepoint:

~~~text
Transaction ngoài:
  UPDATE đơn
  Nested scope:
    INSERT dịch vụ
    Nếu lỗi: rollback nested scope
  COMMIT transaction ngoài
~~~

Khi nested scope “commit”, framework có thể chỉ **release savepoint**. Điều đó có nghĩa dữ liệu vẫn bị rollback nếu transaction ngoài bị hủy. **Tên API chứa chữ commit không chứng minh đã durable commit** khi nó đại diện cho scope lồng.

### 24.1. PostgreSQL PL/pgSQL sử dụng EXCEPTION block

Trong PL/pgSQL, các khối **BEGIN ... EXCEPTION ... END** dùng cơ chế subtransaction để hoàn nguyên thay đổi trong khối khi bắt lỗi:

~~~sql
-- Mẫu PostgreSQL.
DO $$
BEGIN
    UPDATE don_hang_sp
    SET trang_thai = 'DA_XAC_NHAN'
    WHERE id = 101;

    BEGIN
        INSERT INTO dich_vu_sp
            (id, don_hang_id, ma_dich_vu, phi)
        VALUES (2401, 999, 'GOI_QUA', 30000);
    EXCEPTION WHEN foreign_key_violation THEN
        RAISE NOTICE 'Dich vu tuy chon khong hop le';
    END;
END
$$;
~~~

Đoạn INSERT sai FK ở khối con bị hoàn nguyên theo cơ chế EXCEPTION, còn UPDATE ngoài khối con có thể được giữ nếu transaction chính thành công.

**Đây không phải cú pháp tạo savepoint SQL thủ công bên trong PL/pgSQL.** Trong PostgreSQL, PL/pgSQL không dùng các câu SAVEPOINT/ROLLBACK TO/RELEASE trực tiếp theo cùng cách client gửi chúng; khối EXCEPTION là mẫu tương đương thích hợp cho xử lý lỗi cục bộ.

Nếu muốn thử DO không làm thay đổi dữ liệu mẫu, hãy gọi nó trong transaction do client mở rồi ROLLBACK.

## 25. Isolation, snapshot và tính quan sát dữ liệu

Savepoint không phải **bản sao trạng thái của toàn hệ thống tại một thời điểm**. Nó chủ yếu quản lý thay đổi của transaction hiện tại.

Ví dụ:

~~~text
Transaction A:
  BEGIN
  SAVEPOINT p
  SELECT ...

Transaction B:
  UPDATE một hàng
  COMMIT

Transaction A:
  ROLLBACK TO p
  SELECT ...
~~~

Ở mức **READ COMMITTED**, mỗi statement trong PostgreSQL có thể quan sát dữ liệu mới được transaction khác commit, nên SELECT sau rollback về mốc không nhất thiết trả đúng ảnh dữ liệu từng đọc trước đó.

Ở **REPEATABLE READ** và **SERIALIZABLE**, các quy tắc snapshot/xung đột của isolation level áp dụng; SAVEPOINT không biến transaction thành một máy quay thời gian cho mọi trạng thái database.

Phân biệt ba loại nhu cầu:

| Nhu cầu | Công cụ liên quan |
| --- | --- |
| Hủy phần thay đổi của chính transaction | SAVEPOINT và ROLLBACK TO |
| Kiểm soát cạnh tranh giữa transaction | Khóa, isolation, version, constraint |
| Khôi phục database sau sự cố hoặc về thời điểm lịch sử | Backup, point-in-time recovery, audit, snapshot hệ thống |

Không dùng SAVEPOINT như một cơ chế thay cho backup.

## 26. Hiệu năng và ranh giới transaction

SAVEPOINT không làm transaction ngắn lại. Một transaction mở lâu và có nhiều savepoint vẫn có thể:

- Giữ khóa và tạo lock wait;
- Tạo gánh nặng metadata/subtransaction;
- Ảnh hưởng xử lý phiên bản dữ liệu cũ ở hệ MVCC;
- Khiến rollback phức tạp và đắt hơn;
- Chứa nhiều thay đổi chưa durable commit;
- Tăng rủi ro khi công việc còn gọi API hoặc chờ thao tác người dùng.

### 26.1. Một triệu hàng: savepoint hay commit từng batch?

**Chiến lược A:** một transaction dài, tạo savepoint sau mỗi 1000 dòng. Nếu transaction ngoài bị rollback, **toàn bộ các thay đổi chưa commit có thể mất**.

**Chiến lược B:** xử lý từng 1000 dòng trong transaction riêng, COMMIT từng batch. Phần đã commit **không bị rollback bởi batch khác**, nhưng toàn job **không còn tính nguyên tử tất-cả-hoặc-không-gì**.

| Mục tiêu | SAVEPOINT trong một transaction | COMMIT theo batch |
| --- | --- | --- |
| Hoàn nguyên bước tùy chọn | Phù hợp | Không phải công cụ trực tiếp |
| Giữ tính nguyên tử của một transaction lớn | Có thể, nhưng tốn tài nguyên | Không nếu commit từng batch |
| Có tiến độ bền vững giữa các batch | Chưa, nếu chưa commit ngoài | Có sau mỗi commit |
| Giảm thời gian giữ transaction | Không | Có thể |
| Retry lỗi cục bộ | Có nếu đặt mốc và lỗi có thể phục hồi | Có bằng retry transaction batch |

Chọn công cụ theo **yêu cầu nghiệp vụ và vận hành**, không vì nghe savepoint giống “commit tạm”.

## 27. Các lỗi thường gặp

| Sai lầm | Vì sao không đúng | Cách xử lý |
| --- | --- | --- |
| “SAVEPOINT là commit cục bộ.” | Mốc không xác nhận dữ liệu bền vững. | Chỉ COMMIT transaction ngoài cùng mới xác nhận. |
| “RELEASE hủy thay đổi sau mốc.” | Release bỏ mốc, không hoàn nguyên dữ liệu. | Dùng ROLLBACK TO để hủy. |
| “ROLLBACK TO kết thúc transaction.” | Nó giữ transaction mở. | Dùng ROLLBACK không tên nếu muốn hủy toàn bộ. |
| “ROLLBACK TO xóa chính mốc.” | PostgreSQL giữ mốc. | RELEASE khi không cần quay lại. |
| “RELEASE xong vẫn quay về mốc được.” | Mốc không còn. | Tạo mốc mới trước đoạn muốn bảo vệ. |
| “COMMIT rồi vẫn rollback tới mốc cũ.” | Savepoint mất hiệu lực khi transaction kết thúc. | Chỉ rollback trong transaction đang mở. |
| “Sau lỗi PostgreSQL đặt mốc mới để cứu.” | Lỗi có thể đã làm transaction aborted. | Đặt mốc **trước** bước rủi ro. |
| “Sau lỗi chỉ cần RELEASE.” | Release không cứu aborted transaction. | ROLLBACK TO mốc hợp lệ. |
| “Rollback-to luôn cứu mọi lỗi.” | Connection hoặc transaction có thể đã hỏng hoàn toàn. | Phân loại lỗi, full rollback/retry khi cần. |
| “Giữ nửa giao dịch chuyển tiền vẫn đúng.” | Vi phạm ranh giới nguyên tử nghiệp vụ. | Đặt mốc ngoài nhóm thay đổi bắt buộc. |
| “Sequence quay lại khi rollback.” | PostgreSQL sequence không rollback như row DML. | Chấp nhận ID có khoảng trống. |
| “Có thể thu hồi email bằng ROLLBACK TO.” | Email nằm ngoài DB. | Outbox/idempotency/phát sau commit. |
| “Mọi khóa đều nhả sau rollback-to.” | Còn khóa trước mốc và ngoại lệ DBMS. | Hiểu semantics lock cụ thể. |
| “DDL ở mọi DBMS rollback được.” | MySQL/Oracle có implicit commit cho nhiều DDL. | Xác minh từng loại DDL. |
| “SQL Server dùng SAVEPOINT p.” | SQL Server dùng SAVE TRANSACTION p. | Viết cú pháp T-SQL. |
| “SQL Server có RELEASE SAVEPOINT.” | Không có câu tương đương trực tiếp. | Quản lý mốc qua transaction. |
| “SQL Server XACT_STATE=-1 vẫn COMMIT được sau rollback-to.” | Transaction uncommittable. | Full rollback. |
| “SQLite RELEASE ngoài cùng không bao giờ commit.” | SAVEPOINT ngoài BEGIN có thể mở transaction. | Phân biệt mốc ngoài cùng và mốc lồng. |
| “Tên trùng hoạt động giống nhau ở mọi hệ.” | PostgreSQL, MySQL và Oracle khác semantics. | Dùng tên duy nhất. |
| “Savepoint dùng được trên connection khác.” | Mốc thuộc transaction của connection tạo nó. | Duy trì đúng connection. |
| “Nhiều savepoint thay cho nhiều commit.” | Savepoint không durable, transaction vẫn dài. | Thiết kế transaction/batch phù hợp. |

## 28. Bài tập thực hành có lời giải

Các bài dùng bảng PostgreSQL ở mục 3, trừ khi ghi rõ phương ngữ khác. Câu lệnh có **ROLLBACK** cuối dùng để phục hồi dữ liệu mẫu. Nếu trước đó đã chạy ví dụ có COMMIT, trạng thái thực tế trong session có thể khác giá trị ban đầu.

### Bài 1. Phạm vi rollback

Cho chuỗi: BEGIN; thay đổi A; SAVEPOINT p; thay đổi B; ROLLBACK TO p. **Hỏi:** A và B còn không?

**Lời giải:** A còn trong transaction; B bị hoàn nguyên; transaction vẫn mở. COMMIT sẽ giữ A, còn ROLLBACK toàn bộ sẽ hủy A.

### Bài 2. Giữ xác nhận đơn, bỏ dịch vụ

**Yêu cầu:** UPDATE đơn 102 rồi chèn dịch vụ 2802; rollback riêng dịch vụ.

~~~sql
BEGIN;
UPDATE don_hang_sp
SET trang_thai = 'DA_XAC_NHAN'
WHERE id = 102;

SAVEPOINT truoc_goi_qua;
INSERT INTO dich_vu_sp (id, don_hang_id, ma_dich_vu, phi)
VALUES (2802, 102, 'GOI_QUA', 30000);

ROLLBACK TO SAVEPOINT truoc_goi_qua;
RELEASE SAVEPOINT truoc_goi_qua;

SELECT trang_thai FROM don_hang_sp WHERE id = 102;
SELECT id FROM dich_vu_sp WHERE id = 2802;
ROLLBACK;
~~~

**Lời giải:** Trước ROLLBACK cuối, đơn 102 đã DA_XAC_NHAN, dịch vụ 2802 không có. ROLLBACK cuối hủy nốt trạng thái xác nhận.

### Bài 3. RELEASE không phải COMMIT

~~~sql
BEGIN;
SAVEPOINT p;
INSERT INTO dich_vu_sp (id, don_hang_id, ma_dich_vu, phi)
VALUES (2803, 101, 'GOI_QUA', 30000);
RELEASE SAVEPOINT p;
ROLLBACK;
~~~

**Hỏi:** sau khi kết thúc, hàng 2803 còn không?

**Đáp án:** Không. RELEASE bỏ mốc, nhưng ROLLBACK toàn bộ vẫn hủy INSERT.

### Bài 4. Dùng ROLLBACK TO hai lần

**Yêu cầu:** tạo một mốc rồi thử hai giá gói quà; cả hai lần thử đều rollback về cùng mốc.

~~~sql
BEGIN;
SAVEPOINT p;

INSERT INTO dich_vu_sp (id, don_hang_id, ma_dich_vu, phi)
VALUES (2804, 101, 'GOI_QUA', 30000);
ROLLBACK TO SAVEPOINT p;

INSERT INTO dich_vu_sp (id, don_hang_id, ma_dich_vu, phi)
VALUES (2805, 101, 'GOI_QUA', 20000);
ROLLBACK TO SAVEPOINT p;

RELEASE SAVEPOINT p;
ROLLBACK;
~~~

**Đáp án:** Cả hai lần quay về mốc p đều hợp lệ trong PostgreSQL vì ROLLBACK TO giữ chính mốc ấy.

### Bài 5. Mốc đã RELEASE

**Câu hỏi:** sau SAVEPOINT p; RELEASE p; tại sao ROLLBACK TO p không hợp lệ?

**Đáp án:** Điểm lưu p đã bị xóa khỏi transaction. Muốn có đường hoàn nguyên riêng, phải lập điểm lưu mới trước các statement tương ứng.

### Bài 6. Ba điểm lưu

**Câu hỏi:** SAVEPOINT a; SAVEPOINT b; SAVEPOINT c; ROLLBACK TO b; còn những mốc nào?

**Đáp án:** Trong PostgreSQL, a và b còn, c bị loại bỏ. Thay đổi sau b đã bị hoàn nguyên.

### Bài 7. Quay về mốc đầu

**Câu hỏi:** A xảy ra trước p1, B sau p1, C sau p2; nếu ROLLBACK TO p1 thì sao?

**Đáp án:** A còn; B và C bị hoàn nguyên; p2 (mốc mới hơn p1) không còn; p1 vẫn có hiệu lực.

### Bài 8. Lỗi khóa ngoại

**Câu hỏi:** đã đặt mốc trước một INSERT dịch vụ tham chiếu đơn 999, PostgreSQL báo FK violation. Có thể tiếp tục transaction không?

**Đáp án:** Nếu savepoint đã được tạo trước lỗi và transaction/connection còn hợp lệ, chạy ROLLBACK TO mốc ấy để khôi phục trạng thái rồi quyết định tiếp tục hay hủy. Không tự tạo mốc sau lỗi rồi mong cứu transaction.

### Bài 9. Tên SAVEPOINT trùng

**Câu hỏi:** có nên chủ động dùng cùng tên cho mọi savepoint trong ứng dụng đa DBMS không?

**Đáp án:** Không nên. PostgreSQL có cơ chế che/lộ điểm cũ; MySQL thay thế điểm cũ cùng tên; hệ khác có quy tắc riêng. Dùng tên mô tả và duy nhất trong phạm vi transaction.

### Bài 10. Sequence

**Câu hỏi:** gọi nextval sau savepoint rồi rollback-to. ID ấy có chắc được cấp lại ở lần sau?

**Đáp án:** Không. PostgreSQL sequence allocation không rollback giống dữ liệu hàng thông thường, nên ID có thể nhảy.

### Bài 11. MySQL/InnoDB

**Yêu cầu:** viết mẫu MySQL đặt, rollback và release điểm lưu.

~~~sql
START TRANSACTION;
SAVEPOINT p;
-- DML trên bảng InnoDB.
ROLLBACK TO SAVEPOINT p;
RELEASE SAVEPOINT p;
COMMIT;
~~~

**Đáp án:** Cú pháp đúng kiểu MySQL; cần transaction và storage engine transactional. RELEASE không commit transaction ngoài cùng.

### Bài 12. SQL Server

**Yêu cầu:** tạo savepoint p và rollback về p trong T-SQL.

~~~sql
BEGIN TRANSACTION;
SAVE TRANSACTION p;
-- DML phù hợp.
ROLLBACK TRANSACTION p;
COMMIT TRANSACTION;
~~~

**Đáp án:** SQL Server không viết SAVEPOINT p và không có RELEASE SAVEPOINT như PostgreSQL.

### Bài 13. XACT_STATE = -1

**Câu hỏi:** trong SQL Server, transaction đã uncommittable. ROLLBACK TRANSACTION p có thể giúp COMMIT phần trước p không?

**Đáp án:** Không. Khi XACT_STATE() = -1, transaction không thể commit và cần rollback toàn bộ.

### Bài 14. Oracle

**Câu hỏi:** Oracle có cú pháp RELEASE SAVEPOINT p không?

**Đáp án:** Không có cú pháp trực tiếp tương đương trong Oracle SQL. Oracle dùng SAVEPOINT p và ROLLBACK TO SAVEPOINT p; điểm lưu được giải phóng khi transaction kết thúc.

### Bài 15. SQLite ngoài BEGIN

**Câu hỏi:** vì sao RELEASE một savepoint có thể commit trong SQLite?

**Đáp án:** SAVEPOINT ngoài cùng đặt khi chưa có BEGIN có thể tự **mở transaction**. RELEASE mốc ngoài cùng ấy có thể commit transaction đó. Trường hợp SAVEPOINT nằm bên trong BEGIN thì RELEASE không commit transaction cha.

### Bài 16. Email đã gửi

**Tình huống:** sau SAVEPOINT p, cập nhật đơn và gửi email; ROLLBACK TO p. Email có bị thu hồi không?

**Đáp án:** Không. SQL rollback không điều khiển hệ thống email. Dùng outbox/idempotency hoặc quy trình gửi phù hợp sau commit.

### Bài 17. Chuyển tiền

**Tình huống:** trừ tiền khỏi An, tạo savepoint, cộng tiền cho Bình nhưng câu cộng lỗi, rollback-to rồi commit. Vấn đề gì?

**Đáp án:** Có nguy cơ commit **chỉ vế trừ tiền**; không bảo đảm nguyên tử chuyển khoản. Hai cập nhật bắt buộc phải thành công cùng nhau hoặc rollback tương ứng.

### Bài 18. Giao dịch dài

**Câu hỏi:** một triệu hàng được xử lý trong transaction duy nhất với savepoint sau mỗi 1000 hàng. Có phải đã commit bền vững từng lô?

**Đáp án:** Chưa. Chỉ COMMIT transaction ngoài cùng mới xác nhận. Muốn tiến độ durable theo lô cần ranh giới transaction và commit riêng, đồng thời chấp nhận toàn job không còn nguyên tử.

### Bài 19. Ví dụ COMMIT chủ đích

~~~sql
BEGIN;
UPDATE don_hang_sp
SET trang_thai = 'DA_XAC_NHAN'
WHERE id = 103;

SAVEPOINT p;
INSERT INTO dich_vu_sp (id, don_hang_id, ma_dich_vu, phi)
VALUES (2819, 103, 'GOI_QUA', 25000);

ROLLBACK TO SAVEPOINT p;
RELEASE SAVEPOINT p;
COMMIT;
~~~

**Câu hỏi:** sau commit điều gì còn?

**Đáp án:** Đơn 103 đã xác nhận; dịch vụ 2819 không tồn tại. Đây là bài **có COMMIT**, dữ liệu thực hành được giữ khác trạng thái ban đầu.

### Bài 20. Thiết kế xử lý lỗi bước tùy chọn

**Yêu cầu:** mô tả trình tự an toàn khi phần chính A bắt buộc và phần B tùy chọn có thể lỗi.

**Gợi ý lời giải:** BEGIN; thực hiện A và kiểm tra affected rows; SAVEPOINT before_B; thử B; nếu thành công thì RELEASE nơi hỗ trợ; nếu lỗi dữ liệu được phép bỏ thì ROLLBACK TO before_B, dọn mốc và ghi nhận kết quả; lỗi nghiêm trọng thì full ROLLBACK; kiểm tra bất biến cuối transaction; COMMIT khi hợp lệ; chỉ phát kết quả cuối ra ngoài sau trạng thái commit đáng tin cậy.

## 29. Bảng ghi nhớ nhanh

| Mục tiêu | PostgreSQL | Ý nghĩa |
| --- | --- | --- |
| Mở transaction | `BEGIN` | Giao dịch tường minh |
| Đặt mốc | `SAVEPOINT p` | Bắt đầu vùng có thể hoàn nguyên |
| Quay về mốc | `ROLLBACK TO SAVEPOINT p` | Hủy phần sau p, giữ transaction mở |
| Thử lại từ cùng mốc | DML rồi ROLLBACK TO p lần nữa | Trong PostgreSQL mốc p vẫn tồn tại |
| Bỏ mốc | `RELEASE SAVEPOINT p` | Không commit dữ liệu |
| Chấp nhận tất cả thay đổi còn lại | `COMMIT` | Kết thúc giao dịch |
| Hủy toàn bộ | `ROLLBACK` | Kết thúc giao dịch |
| Cứu transaction PostgreSQL sau lỗi cục bộ | `ROLLBACK TO p` với p đặt trước lỗi | Chỉ khi transaction còn hợp lệ |
| Tạo mốc trên SQL Server | `SAVE TRANSACTION p` | Cú pháp T-SQL |
| Quay về mốc trên Oracle | `ROLLBACK TO SAVEPOINT p` | Oracle không có RELEASE trực tiếp |
| RELEASE outermost SAVEPOINT SQLite ngoài BEGIN | Có thể commit | Ngoại lệ phải nhớ |

## 30. Tài liệu chính thức

Khi triển khai, nên đối chiếu **đúng DBMS, phiên bản, storage engine và driver**:

- PostgreSQL: [SAVEPOINT](https://www.postgresql.org/docs/current/sql-savepoint.html), [ROLLBACK TO SAVEPOINT](https://www.postgresql.org/docs/current/sql-rollback-to.html), [RELEASE SAVEPOINT](https://www.postgresql.org/docs/current/sql-release-savepoint.html).
- MySQL: [SAVEPOINT, ROLLBACK TO SAVEPOINT and RELEASE SAVEPOINT](https://dev.mysql.com/doc/refman/8.4/en/savepoint.html), [Implicit Commit](https://dev.mysql.com/doc/refman/8.4/en/implicit-commit.html).
- SQL Server: [SAVE TRANSACTION](https://learn.microsoft.com/en-us/sql/t-sql/language-elements/save-transaction-transact-sql), [ROLLBACK TRANSACTION](https://learn.microsoft.com/en-us/sql/t-sql/language-elements/rollback-transaction-transact-sql), [XACT_STATE](https://learn.microsoft.com/en-us/sql/t-sql/functions/xact-state-transact-sql).
- Oracle Database: [SAVEPOINT](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/SAVEPOINT.html), [ROLLBACK](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/ROLLBACK.html).
- SQLite: [SAVEPOINT](https://www.sqlite.org/lang_savepoint.html), [Transactions](https://www.sqlite.org/lang_transaction.html).
- Java JDBC: [Connection](https://docs.oracle.com/en/java/javase/21/docs/api/java.sql/java/sql/Connection.html), [Savepoint](https://docs.oracle.com/en/java/javase/21/docs/api/java.sql/java/sql/Savepoint.html).

## 31. Kết luận

**SAVEPOINT, ROLLBACK TO và RELEASE SAVEPOINT** giúp chia một giao dịch SQL thành những đoạn có thể hoàn nguyên riêng, nhưng không phá bỏ ranh giới tính nguyên tử của transaction bên ngoài:

1. Đặt **SAVEPOINT trước bước có thể cần hủy**, dựa trên yêu cầu nghiệp vụ.
2. Dùng **ROLLBACK TO** để hoàn nguyên phần sau mốc; trong PostgreSQL, savepoint vẫn tồn tại và transaction vẫn mở.
3. Dùng **RELEASE** khi không còn cần mốc; những thay đổi còn tồn tại vẫn có thể bị full ROLLBACK.
4. Chỉ **COMMIT** mới xác nhận thay đổi còn lại của transaction.
5. Sau lỗi SQL, chỉ tiếp tục từ savepoint nếu **mốc đã có trước lỗi** và DBMS/transaction vẫn cho phép phục hồi.
6. SAVEPOINT không hoàn nguyên side effect ngoài DB, sequence đã cấp, thay đổi transaction khác hoặc mọi trường hợp DDL implicit commit.
7. **SQL Server, Oracle, SQLite và MySQL có những khác biệt thực sự về cú pháp và semantics**, đặc biệt RELEASE, transaction state và khóa.
8. Không dùng savepoint để commit riêng một vế của nghiệp vụ bắt buộc như chuyển tiền; cũng không dùng nó thay cho backup hoặc commit theo batch.

**Nguyên tắc cốt lõi:** một savepoint là **đường quay lại bên trong giao dịch đang mở**, không phải giao dịch đã hoàn tất. Hãy chỉ hoàn nguyên những bước mà nghiệp vụ cho phép hủy riêng, rồi kiểm tra và commit transaction cha một cách có chủ đích.
