# Bài toán phù hợp với trigger và chi phí logic ngầm trong SQL

Một câu lệnh SQL có vẻ rất đơn giản:

~~~sql
UPDATE don_hang
SET trang_thai = 'DA_GIAO'
WHERE ma_don = 'DH349-002';
~~~

Người đọc có thể nghĩ database chỉ cần đổi một cột của một hàng. Nhưng nếu bảng `don_hang` có nhiều **trigger**, câu UPDATE ấy có thể còn tự động: kiểm tra quy tắc chuyển trạng thái, cập nhật thời gian, ghi một bản lịch sử, thêm sự kiện vào outbox, cập nhật bảng thống kê, chạm tới các bảng khác và lấy thêm khóa. Câu SQL được ứng dụng gửi đi chỉ thể hiện **tác động trực tiếp**; nó không cho thấy mọi thao tác sẽ phát sinh bên trong database.

Đó là **hai mặt của trigger**:

- **Lợi ích:** thực thi logic ở sát dữ liệu, trên nhiều đường ghi khác nhau, trong cùng ranh giới transaction khi cơ chế DBMS hỗ trợ. Trigger rất hữu ích cho những bất biến, metadata hay sự kiện phát sinh **bắt buộc đi cùng** một thay đổi dữ liệu.
- **Chi phí:** tạo ra **logic ngầm** (*hidden/implicit logic*): tác động khó thấy từ SQL gọi, thêm I/O và CPU, tăng khóa, làm việc debug phức tạp, có thể gây đệ quy hoặc làm một câu DML thất bại ngoài dự đoán.

Bài học này thuộc **Database SQL → Trigger**. Ta sẽ trả lời: **Khi nào trigger là công cụ đúng? Khi nào CHECK/FOREIGN KEY/DEFAULT/GENERATED COLUMN, SQL trực tiếp, stored procedure, ứng dụng, CDC hoặc job bất đồng bộ phù hợp hơn? Làm thế nào nhận diện và kiểm soát chi phí logic ngầm?**

Ví dụ chính dùng **PostgreSQL**, rồi so sánh MySQL/MariaDB, SQL Server, Oracle và SQLite. Mục tiêu không phải viết trigger bằng mọi giá, mà là **thiết kế database có thể hiểu, đo lường, sửa lỗi và vận hành an toàn**.

## 1. Trigger là gì, và “logic ngầm” nghĩa là gì?

**Trigger** là đoạn logic do database tự gọi khi một **sự kiện đã khai báo** xảy ra trên đối tượng hoặc hệ thống tương ứng. Với DML trigger thông thường, sự kiện là:

- `INSERT`: thêm hàng;
- `UPDATE`: sửa hàng;
- `DELETE`: xóa hàng.

Tùy DBMS, còn có trigger cho `TRUNCATE`, DDL, logon, sự kiện hệ thống hoặc các ngữ cảnh khác.

Một luồng đơn giản:

~~~mermaid
flowchart TD
    A["Ứng dụng gửi UPDATE don_hang"] --> B["BEFORE trigger\nkiểm tra / sửa NEW"]
    B --> C["Database thực thi UPDATE"]
    C --> D["AFTER trigger\nlịch sử / outbox"]
    D --> E["Câu UPDATE thành công hoặc lỗi"]
    E --> F{"Transaction"}
    F -->|"COMMIT"| G["Dữ liệu và thay đổi trigger cùng được xác nhận"]
    F -->|"ROLLBACK"| H["Dữ liệu và thay đổi trigger trong transaction bị hủy"]
~~~

**Logic ngầm** không nhất thiết xấu. Nó có nghĩa người viết `UPDATE` **không nhìn thấy đầy đủ** mọi bước từ chính câu UPDATE ấy. Khi đọc một câu DML cần biết rằng schema có thể chứa trigger, foreign key cascade, generated columns và các ràng buộc khác.

### 1.1. Trigger không phải stored procedure được gọi trực tiếp

Stored procedure thường được gọi có chủ đích:

~~~sql
CALL xac_nhan_don(101);
~~~

Trigger tự chạy khi một sự kiện xảy ra:

~~~sql
UPDATE don_hang
SET trang_thai = 'DA_XAC_NHAN'
WHERE id = 101;
-- Nếu bảng có trigger liên quan, chúng có thể chạy tự động.
~~~

Trong PostgreSQL, trigger thường thực thi **trigger function** có kiểu trả về `trigger`, nhưng người dùng **không gọi function ấy bằng SELECT như một hàm thông thường**. Database gọi nó trong ngữ cảnh sự kiện, cung cấp `NEW`, `OLD`, `TG_OP` và các biến ngữ cảnh.

### 1.2. Trigger không tự đồng nghĩa “chạy ở background”

Một ngộ nhận phổ biến là AFTER trigger chạy sau khi transaction đã commit. Với **PostgreSQL AFTER trigger thông thường**, logic vẫn thuộc xử lý transaction, **không phải job bất đồng bộ tự động sau COMMIT**. Nếu trigger thực thi một câu INSERT vào bảng khác, cả hai thay đổi có thể cùng commit hoặc cùng rollback.

Tên **AFTER** ở đây nghĩa là sau thao tác dữ liệu liên quan trong trình tự xử lý trigger, **không phải** sau khi transaction đã thành công bền vững. Thứ tự thực tế của trigger, constraint checks và deferred triggers cần xem theo DBMS.

## 2. Khung quyết định trước khi tạo trigger

Không bắt đầu bằng câu “Có thể viết trigger không?” mà bắt đầu bằng **tính chất của quy tắc**:

| Câu hỏi | Nếu câu trả lời là “có” | Hướng suy nghĩ |
| --- | --- | --- |
| Quy tắc bắt buộc đúng dù dữ liệu được ghi từ nhiều ứng dụng? | Có | Ưu tiên constraint; cân nhắc trigger nếu constraint không biểu đạt được |
| Quy tắc chỉ kiểm tra một cột/hàng bằng biểu thức tĩnh? | Có | `NOT NULL`, `CHECK`, kiểu dữ liệu, `DEFAULT` thường đơn giản hơn |
| Quy tắc là quan hệ giữa các hàng qua khóa? | Có | `UNIQUE`, `PRIMARY KEY`, `FOREIGN KEY` trước |
| Cần ghi lịch sử cùng transaction với thay đổi nguồn? | Có | AFTER trigger có thể phù hợp, nhưng cần thiết kế audit và quyền |
| Cần phát thông điệp ra hệ ngoài sau COMMIT? | Có | Transactional outbox + worker/CDC; **không gửi email trực tiếp từ trigger** |
| Cần thay đổi `NEW` trước khi ghi hàng? | Có | BEFORE row trigger có thể phù hợp |
| Cần xử lý tập hàng lớn theo đợt? | Có | SQL theo tập, statement trigger/transition table hoặc job batch thường hiệu quả hơn row trigger |
| Logic dài, phụ thuộc API bên ngoài, cần retry độc lập? | Có | Thường để ứng dụng/job riêng xử lý |
| Logic phải dễ tìm trong lời gọi nghiệp vụ? | Có | Stored procedure/service tường minh có thể tốt hơn |
| Tần suất ghi rất cao và bảng nóng? | Có | Đánh giá kỹ I/O, khóa, WAL, replication và tác động của trigger |

### 2.1. Những bài toán thường tương đối phù hợp

- **Audit ở tầng database:** ghi ai/đối tượng/thời điểm/thay đổi vào bảng lịch sử trong cùng transaction.
- **Duy trì metadata:** cập nhật thời điểm sửa, phiên bản hoặc giá trị dẫn xuất khi không có cơ chế khai báo tốt hơn.
- **Bảo vệ chuyển trạng thái:** ví dụ không cho đơn đã giao quay lại “mới”, nếu quy tắc thật sự phải được thực thi ở mọi đường cập nhật.
- **Transactional outbox:** tạo bản ghi sự kiện cùng transaction, để worker công bố **sau khi commit**.
- **Kiểm tra một quy tắc phức tạp không diễn đạt được bằng constraint thuần**, với điều kiện có thiết kế concurrency an toàn.
- **Đồng bộ cấu trúc phụ trợ nhỏ** trong phạm vi được chứng minh là đúng/đủ nhanh, ví dụ một bảng báo cáo đơn giản; cần đánh giá khả năng thay bằng truy vấn/tổng hợp theo lô.

### 2.2. Những bài toán thường không phù hợp

- Gửi email, SMS, gọi HTTP hoặc chờ API ngay trong trigger.
- Thực hiện logic phức tạp kéo dài nhiều giây/phút cho từng hàng.
- Dùng trigger để che giấu toàn bộ quy trình nghiệp vụ đáng lẽ cần lời gọi tường minh.
- Dùng trigger thay cho mọi constraint đơn giản.
- Cập nhật tổng lớn bằng cách truy vấn lại toàn bộ bảng con **cho mỗi hàng** mà không xem tải ghi.
- Dựa vào trigger để “chữa” lỗi thiết kế khóa ngoại hay phân quyền.
- Giả định trigger có thể điều khiển chính xác mọi đường ghi, kể cả bulk load, replication, TRUNCATE, DDL và sửa dữ liệu ngoài DB mà chưa kiểm tra phiên bản/engine.

**Tiêu chuẩn lựa chọn:** quy tắc có cần **gắn chặt với thay đổi dữ liệu**, phạm vi ảnh hưởng có **nhỏ và dự đoán được**, và chi phí/vận hành có thể **quan sát được** hay không?

## 3. Bộ dữ liệu thực hành PostgreSQL

Các ví dụ dùng schema `bai349` trong **database thử nghiệm**. Cần quyền `CREATE SCHEMA`/`CREATE TABLE` phù hợp. Chỉ chạy trên môi trường bạn được phép tạo và thay đổi dữ liệu.

~~~sql
CREATE SCHEMA bai349;

CREATE TABLE bai349.don_hang (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    ma_don TEXT NOT NULL UNIQUE,
    to_chuc_id INTEGER NOT NULL,
    ten_khach TEXT NOT NULL,
    trang_thai TEXT NOT NULL DEFAULT 'MOI'
        CHECK (trang_thai IN (
            'MOI', 'DA_XAC_NHAN', 'DA_GIAO', 'DA_HUY'
        )),
    tong_tien NUMERIC(12,2) NOT NULL
        CHECK (tong_tien >= 0),
    tao_luc TIMESTAMPTZ NOT NULL
        DEFAULT CURRENT_TIMESTAMP,
    cap_nhat_luc TIMESTAMPTZ NOT NULL
        DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE bai349.san_pham (
    id INTEGER PRIMARY KEY,
    ten TEXT NOT NULL,
    gia_hien_tai NUMERIC(12,2) NOT NULL
        CHECK (gia_hien_tai >= 0),
    ton_kho INTEGER NOT NULL CHECK (ton_kho >= 0)
);

CREATE TABLE bai349.chi_tiet_don (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    don_hang_id BIGINT NOT NULL
        REFERENCES bai349.don_hang(id),
    san_pham_id INTEGER NOT NULL
        REFERENCES bai349.san_pham(id),
    so_luong INTEGER NOT NULL CHECK (so_luong > 0),
    don_gia NUMERIC(12,2) NOT NULL CHECK (don_gia >= 0)
);

CREATE INDEX idx_chi_tiet_don_don_id
ON bai349.chi_tiet_don (don_hang_id);

INSERT INTO bai349.don_hang
    (ma_don, to_chuc_id, ten_khach, trang_thai, tong_tien)
VALUES
    ('DH349-001', 10, 'An',   'MOI',           250000),
    ('DH349-002', 10, 'Bình', 'DA_XAC_NHAN',   650000),
    ('DH349-003', 10, 'Chi',  'DA_GIAO',       450000),
    ('DH349-004', 20, 'Dung', 'MOI',           310000);

INSERT INTO bai349.san_pham
    (id, ten, gia_hien_tai, ton_kho)
VALUES
    (1, 'Sổ tay',  50000, 100),
    (2, 'Bút',     20000, 200),
    (3, 'Ba lô',  250000,  20);

SELECT id, ma_don, to_chuc_id, trang_thai, tong_tien
FROM bai349.don_hang
ORDER BY ma_don;
~~~

Các mã đơn `DH349-001` đến `DH349-004` là **khóa nghiệp vụ dễ đọc** trong các ví dụ. Cột `id` được database sinh; không giả định ID luôn bắt đầu từ 1 trong mọi môi trường.

**Dọn sau thực hành:** sau khi kiểm tra schema chỉ thuộc bài học và được phép xóa, có thể dùng:

~~~sql
-- CHỈ dành cho schema demo trên database thử nghiệm:
-- DROP SCHEMA bai349 CASCADE;
~~~

Lệnh `DROP SCHEMA ... CASCADE` có tính phá hủy dữ liệu; không dùng nếu schema đã chứa đối tượng thật ngoài bài tập.

## 4. BEFORE, AFTER, INSTEAD OF: thời điểm trigger có ý nghĩa gì?

Trong PostgreSQL, trigger có thể được khai báo ở các thời điểm khác nhau:

| Loại | Mục đích thường gặp | Điều cần lưu ý |
| --- | --- | --- |
| `BEFORE INSERT/UPDATE/DELETE` trên bảng | Kiểm tra hoặc thay đổi hàng trước thao tác | BEFORE ROW có thể sửa `NEW` hoặc bỏ qua hàng qua giá trị trả về |
| `AFTER INSERT/UPDATE/DELETE` | Audit, outbox, tác động phụ thuộc cần biết thao tác đã qua bước thay đổi dữ liệu | Vẫn thuộc transaction; có thể khiến statement thất bại |
| `INSTEAD OF` trên view phù hợp | Thay hành vi DML trên view bằng logic tùy chỉnh | Semantics khác trigger trên bảng |
| `BEFORE/AFTER ... FOR EACH STATEMENT` | Làm việc một lần mỗi câu SQL | Không tự có `NEW`/`OLD` của từng hàng; có thể dùng transition tables trong trường hợp hỗ trợ |
| Constraint trigger được hoãn | Kiểm tra điều kiện ở thời điểm hoãn phù hợp | Có cú pháp và giới hạn riêng, không phải AFTER trigger thường |

### 4.1. FOR EACH ROW và FOR EACH STATEMENT

~~~sql
CREATE TRIGGER trg_vi_du_row
AFTER UPDATE ON mot_bang
FOR EACH ROW
EXECUTE FUNCTION mot_trigger_function();

CREATE TRIGGER trg_vi_du_statement
AFTER UPDATE ON mot_bang
FOR EACH STATEMENT
EXECUTE FUNCTION mot_trigger_function();
~~~

Đây là **mẫu cú pháp**, chưa chạy được vì các đối tượng ví dụ chưa tồn tại.

Nếu một UPDATE thay đổi **10.000 hàng**:

- Một row trigger có thể chạy **10.000 lần**.
- Một statement trigger thông thường chạy **một lần cho câu UPDATE**, kể cả khi UPDATE không tác động hàng nào.
- Một statement trigger không mặc nhiên biết toàn bộ ID đã thay đổi; cần sử dụng cơ chế phù hợp như **transition tables** ở PostgreSQL.

### 4.2. NEW, OLD và TG_OP

Trong PostgreSQL PL/pgSQL trigger function:

- `NEW`: hàng mới với INSERT/UPDATE ở row-level trigger.
- `OLD`: hàng cũ với UPDATE/DELETE ở row-level trigger.
- `TG_OP`: tên thao tác đang kích hoạt, ví dụ `INSERT`, `UPDATE`, `DELETE`.
- `TG_TABLE_SCHEMA` và `TG_TABLE_NAME`: thông tin đối tượng kích hoạt.
- `TG_WHEN` và `TG_LEVEL`: thời điểm và cấp kích hoạt theo ngữ cảnh.

Trong `BEFORE INSERT/UPDATE FOR EACH ROW`, function thường **RETURN NEW** để tiếp tục với hàng có thể đã được điều chỉnh. Trong `BEFORE DELETE`, thường **RETURN OLD** để tiếp tục xóa. `RETURN NULL` ở BEFORE ROW có thể khiến thao tác trên hàng ấy **bị bỏ qua**, tạo ra thay đổi hành vi không hiển thị rõ trong DML.

Đối với AFTER ROW và STATEMENT triggers, PostgreSQL **bỏ qua giá trị trả về** của trigger function; thông dụng viết `RETURN NULL`.

## 5. Bài toán phù hợp 1: tự ghi thời điểm cập nhật

Bảng `bai349.don_hang` đã có cột `cap_nhat_luc`. Nếu nhiều ứng dụng cùng sửa đơn hàng, ta muốn thời điểm sửa được quản lý tập trung trong database.

### 5.1. BEFORE UPDATE trigger

~~~sql
CREATE FUNCTION bai349.fn_set_cap_nhat_luc()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF (
        NEW.ma_don,
        NEW.to_chuc_id,
        NEW.ten_khach,
        NEW.trang_thai,
        NEW.tong_tien
    ) IS DISTINCT FROM (
        OLD.ma_don,
        OLD.to_chuc_id,
        OLD.ten_khach,
        OLD.trang_thai,
        OLD.tong_tien
    ) THEN
        NEW.cap_nhat_luc := statement_timestamp();
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_set_cap_nhat_luc
BEFORE UPDATE ON bai349.don_hang
FOR EACH ROW
EXECUTE FUNCTION bai349.fn_set_cap_nhat_luc();
~~~

Ý nghĩa:

1. Khi UPDATE hàng, database gọi function **trước khi ghi hàng mới**.
2. Function chỉ cập nhật `cap_nhat_luc` nếu những **cột nghiệp vụ được liệt kê** thực sự đổi.
3. `RETURN NEW` cho phép UPDATE tiếp tục.
4. `statement_timestamp()` phản ánh thời gian bắt đầu statement trong PostgreSQL; không phải đồng hồ tuyệt đối duy nhất/đơn điệu cho mọi thao tác.

Thử:

~~~sql
BEGIN;

SELECT ma_don, cap_nhat_luc
FROM bai349.don_hang
WHERE ma_don = 'DH349-001';

UPDATE bai349.don_hang
SET tong_tien = tong_tien + 10000
WHERE ma_don = 'DH349-001';

SELECT ma_don, tong_tien, cap_nhat_luc
FROM bai349.don_hang
WHERE ma_don = 'DH349-001';

ROLLBACK;
~~~

Đây là một ví dụ **hợp lý với trigger** vì nhiều đường cập nhật cùng cần thực hiện một quy tắc metadata nhỏ.

### 5.2. Chi phí và góc khuất ngay cả trong trigger đơn giản

- Mỗi hàng UPDATE kích hoạt function một lần.
- PostgreSQL có thể vẫn tạo phiên bản hàng mới cho UPDATE dù các giá trị nghiệp vụ không đổi; trigger không tự biến một no-op UPDATE thành miễn phí.
- `cap_nhat_luc` không nên là một “khóa phiên bản chính xác tuyệt đối” cho optimistic locking nếu hai thao tác có cùng độ phân giải thời gian.
- Nếu ứng dụng cần điều khiển timestamp để nhập lịch sử, trigger **cố ghi đè** có thể không phù hợp.
- Nếu cột mới được thêm vào bảng nhưng không nằm trong danh sách so sánh, trigger trên **sẽ không coi sự thay đổi cột ấy là thay đổi nghiệp vụ**; đây là gánh nặng bảo trì.

### 5.3. Khi DEFAULT hoặc generated value đủ dùng

`DEFAULT CURRENT_TIMESTAMP` chỉ gán lúc INSERT nếu giá trị không được cung cấp; nó **không tự sửa timestamp khi UPDATE** trong PostgreSQL. Vì thế một BEFORE UPDATE trigger có thể hợp lý.

Nhưng nếu yêu cầu là một giá trị **luôn tính từ các cột của chính hàng theo biểu thức cho phép**, hãy cân nhắc **generated column** thay vì tạo trigger chỉ để sao chép công thức. Generated column có phạm vi và giới hạn khác nhau theo DBMS.

## 6. Bài toán phù hợp 2: kiểm soát chuyển trạng thái nghiệp vụ

`CHECK (trang_thai IN (...))` giới hạn **tập trạng thái hợp lệ**, nhưng **không nhìn thấy giá trị OLD** để biết bước chuyển `MOI → DA_GIAO` có được phép hay không.

Giả sử luật chuyển trạng thái:

| Trạng thái cũ | Trạng thái mới được phép |
| --- | --- |
| `MOI` | `DA_XAC_NHAN`, `DA_HUY` |
| `DA_XAC_NHAN` | `DA_GIAO`, `DA_HUY` |
| `DA_GIAO` | Không chuyển tiếp |
| `DA_HUY` | Không chuyển tiếp |
| Không thay đổi trạng thái | Cho phép |

### 6.1. BEFORE UPDATE guard

~~~sql
CREATE FUNCTION bai349.fn_kiem_tra_chuyen_trang_thai()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF NEW.trang_thai IS NOT DISTINCT FROM OLD.trang_thai THEN
        RETURN NEW;
    END IF;

    IF (
        OLD.trang_thai = 'MOI'
        AND NEW.trang_thai IN ('DA_XAC_NHAN', 'DA_HUY')
    ) OR (
        OLD.trang_thai = 'DA_XAC_NHAN'
        AND NEW.trang_thai IN ('DA_GIAO', 'DA_HUY')
    ) THEN
        RETURN NEW;
    END IF;

    RAISE EXCEPTION
        'Chuyen trang thai khong hop le: % -> % (don %)',
        OLD.trang_thai, NEW.trang_thai, OLD.ma_don;
END;
$$;

CREATE TRIGGER trg_kiem_tra_chuyen_trang_thai
BEFORE UPDATE OF trang_thai ON bai349.don_hang
FOR EACH ROW
EXECUTE FUNCTION bai349.fn_kiem_tra_chuyen_trang_thai();
~~~

Một cập nhật hợp lệ:

~~~sql
BEGIN;

UPDATE bai349.don_hang
SET trang_thai = 'DA_XAC_NHAN'
WHERE ma_don = 'DH349-001';

SELECT ma_don, trang_thai
FROM bai349.don_hang
WHERE ma_don = 'DH349-001';

ROLLBACK;
~~~

Một cập nhật **cố ý lỗi**:

~~~sql
-- Chạy riêng trên database thử nghiệm:
-- UPDATE bai349.don_hang
-- SET trang_thai = 'MOI'
-- WHERE ma_don = 'DH349-003';
--
-- Vì DH349-003 ban đầu là DA_GIAO nên trigger từ chối.
~~~

### 6.2. Vì sao trigger có thể phù hợp?

Quy tắc cần **so sánh OLD và NEW của cùng hàng**. Nếu database được ghi từ nhiều chương trình, một guard ở database giúp bảo vệ mọi đường UPDATE thông thường thay vì phụ thuộc từng ứng dụng nhớ kiểm tra.

Tuy nhiên, không nên dùng trigger **thay thế mọi validation**. Ứng dụng vẫn cần kiểm tra quyền xác nhận/giao hàng, hiển thị lỗi rõ ràng, và có thể cung cấp procedure `xac_nhan_don` hoặc `giao_don` làm API nghiệp vụ tường minh.

### 6.3. Hạn chế khi quy tắc liên quan nhiều hàng

Nếu quy tắc là “tổng số hàng đang đặt không được vượt kho khả dụng”, chỉ đọc `SELECT SUM(...)` trong trigger một cách ngây thơ có thể **không an toàn khi hai transaction đồng thời** cùng thấy tồn kho trước cập nhật của nhau.

Cần thiết kế thêm:

- Lock đúng các hàng/nguồn tài nguyên chung;
- DML nguyên tử có điều kiện, ví dụ `UPDATE san_pham SET ton_kho = ton_kho - :n WHERE id=:id AND ton_kho >= :n RETURNING ...`;
- Ràng buộc database có thể biểu đạt;
- Isolation/retry phù hợp;
- Quy tắc lock order để giảm deadlock.

**Trigger không tự bảo đảm serializability hoặc loại bỏ race condition** chỉ vì nó chạy trong database.

## 7. Bài toán phù hợp 3: audit thay đổi dữ liệu trong cùng transaction

Nếu một đơn thay đổi trạng thái hoặc số tiền, ta muốn có bằng chứng về **giá trị trước/sau**. Một AFTER row trigger có thể ghi vào bảng lịch sử bất cứ khi nào bảng nguồn bị INSERT, UPDATE hoặc DELETE thông thường.

### 7.1. Tạo bảng audit

~~~sql
CREATE TABLE bai349.lich_su_don (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    ma_don TEXT NOT NULL,
    thao_tac TEXT NOT NULL
        CHECK (thao_tac IN ('INSERT', 'UPDATE', 'DELETE')),
    truoc JSONB,
    sau JSONB,
    nguoi_thuc_thi TEXT NOT NULL,
    thay_doi_luc TIMESTAMPTZ NOT NULL
        DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_lich_su_don_ma_luc
ON bai349.lich_su_don (ma_don, thay_doi_luc DESC, id DESC);
~~~

### 7.2. AFTER ROW trigger function

~~~sql
CREATE FUNCTION bai349.fn_audit_don_hang()
RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
    v_ma_don TEXT;
    v_truoc JSONB;
    v_sau JSONB;
BEGIN
    IF TG_OP = 'INSERT' THEN
        v_ma_don := NEW.ma_don;
        v_truoc := NULL;
        v_sau := to_jsonb(NEW);

    ELSIF TG_OP = 'UPDATE' THEN
        v_ma_don := NEW.ma_don;
        v_truoc := to_jsonb(OLD);
        v_sau := to_jsonb(NEW);

    ELSIF TG_OP = 'DELETE' THEN
        v_ma_don := OLD.ma_don;
        v_truoc := to_jsonb(OLD);
        v_sau := NULL;
    END IF;

    INSERT INTO bai349.lich_su_don
        (ma_don, thao_tac, truoc, sau,
         nguoi_thuc_thi, thay_doi_luc)
    VALUES
        (v_ma_don, TG_OP, v_truoc, v_sau,
         CURRENT_USER, clock_timestamp());

    RETURN NULL;
END;
$$;

CREATE TRIGGER trg_audit_don_hang
AFTER INSERT OR UPDATE OR DELETE
ON bai349.don_hang
FOR EACH ROW
EXECUTE FUNCTION bai349.fn_audit_don_hang();
~~~

Trigger được tạo **sau** bốn hàng demo ban đầu, nên các hàng ấy **không có lịch sử INSERT trước đó**. Trigger không quay ngược thời gian để audit dữ liệu có trước lúc kích hoạt.

Thử:

~~~sql
BEGIN;

UPDATE bai349.don_hang
SET tong_tien = tong_tien + 5000
WHERE ma_don = 'DH349-001';

SELECT
    id, ma_don, thao_tac,
    truoc->>'tong_tien' AS tong_truoc,
    sau->>'tong_tien' AS tong_sau,
    nguoi_thuc_thi, thay_doi_luc
FROM bai349.lich_su_don
WHERE ma_don = 'DH349-001'
ORDER BY id DESC;

ROLLBACK;
~~~

Trong transaction, có một dòng audit tương ứng. Sau `ROLLBACK`, **cả UPDATE đơn lẫn INSERT lịch sử đều bị hủy**.

### 7.3. Điểm mạnh của audit trigger

- Áp dụng cho nhiều đường DML thông thường, không cần từng endpoint tự INSERT lịch sử.
- Có thể ghi **trước/sau** theo cùng transaction.
- Một lỗi ghi audit có thể chặn thao tác nguồn, nếu đó là yêu cầu “không thay đổi được nếu không audit được”.
- Lịch sử nằm cùng DB, dễ JOIN theo khóa và truy vấn theo thời gian.

### 7.4. Chi phí và giới hạn của ví dụ audit

Ví dụ `to_jsonb(OLD/NEW)` giúp minh họa nhưng **không phải chính sách production mặc định**:

1. **Dữ liệu nhạy cảm:** snapshot có thể chứa tên, địa chỉ, token hoặc thông tin không cần lưu. Nên **liệt kê trường cần audit**, mã hóa/ẩn dữ liệu phù hợp và đặt retention.
2. **Kích thước:** mỗi UPDATE ghi thêm một hàng lịch sử, cộng index, WAL, backup và replication.
3. **No-op UPDATE:** một câu `SET tong_tien=tong_tien` vẫn có thể kích hoạt row audit dù giá trị nghiệp vụ không đổi.
4. **Quyền:** `CURRENT_USER` thường là **database role**, không chắc là danh tính người dùng cuối. Cần thiết kế danh tính actor được xác thực từ ứng dụng, không tin input tùy ý.
5. **Khả năng giả mạo:** người dùng có quyền sửa/xóa bảng audit hoặc tắt trigger có thể phá vỡ giá trị kiểm toán. Muốn audit chống giả mạo phải xét quyền, log bất biến/tamper evidence, sao lưu và kênh độc lập.
6. **Ranh giới transaction:** một transaction bị rollback sẽ **không có audit row durable**, điều đó đúng cho audit **thay đổi đã commit**, nhưng không ghi được mọi **nỗ lực cập nhật thất bại**.
7. **Đường ghi đặc biệt:** TRUNCATE, replication, bulk load hoặc tác vụ quản trị có semantics trigger khác nhau; cần kiểm tra khả năng bao phủ thật.

### 7.5. Khi cần audit “ai đã thử làm gì, kể cả thất bại”

Một transaction bị ROLLBACK có thể hủy luôn dòng audit. Nếu yêu cầu pháp lý cần ghi cả **nỗ lực bị từ chối**, không thể dựa hoàn toàn vào một bảng audit transactionally coupled theo mẫu trên. Có thể cần **log truy cập/statement/audit ở tầng database server hoặc hệ thống độc lập**, với chính sách bảo mật và tính toàn vẹn rõ ràng.

## 8. Bài toán phù hợp 4: transactional outbox, không gửi email trong trigger

Giả sử đơn chuyển sang `DA_GIAO` thì hệ thống phải gửi sự kiện để dịch vụ khác cập nhật trạng thái giao vận. Nếu trigger **gọi API trực tiếp**:

~~~text
UPDATE đơn → Trigger gọi HTTP → API trả thành công
                ↓
             Transaction SQL sau đó ROLLBACK
~~~

hệ thống bên ngoài có thể đã nhận thông báo, nhưng database **không commit** thay đổi. Nếu HTTP bị chậm, transaction giữ tài nguyên/khóa quá lâu. Nếu HTTP timeout sau khi bên nhận đã nhận, có thể phát lại sự kiện trùng.

### 8.1. Bảng outbox

Một cách phù hợp hơn là trigger **ghi một row sự kiện trong cùng database transaction**, còn worker gửi đi **sau khi hàng outbox đã commit**.

~~~sql
CREATE TABLE bai349.outbox_su_kien (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    khoa_su_kien TEXT NOT NULL UNIQUE,
    loai_su_kien TEXT NOT NULL,
    ma_don TEXT NOT NULL,
    payload JSONB NOT NULL,
    tao_luc TIMESTAMPTZ NOT NULL
        DEFAULT CURRENT_TIMESTAMP,
    gui_luc TIMESTAMPTZ
);

CREATE INDEX idx_outbox_chua_gui
ON bai349.outbox_su_kien (id)
WHERE gui_luc IS NULL;
~~~

### 8.2. AFTER UPDATE trigger cho sự kiện “đã giao”

~~~sql
CREATE FUNCTION bai349.fn_ghi_outbox_da_giao()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    INSERT INTO bai349.outbox_su_kien
        (khoa_su_kien, loai_su_kien, ma_don, payload)
    VALUES (
        'DON_DA_GIAO:' || NEW.ma_don,
        'DON_DA_GIAO',
        NEW.ma_don,
        jsonb_build_object(
            'ma_don', NEW.ma_don,
            'to_chuc_id', NEW.to_chuc_id,
            'trang_thai', NEW.trang_thai
        )
    )
    ON CONFLICT (khoa_su_kien) DO NOTHING;

    RETURN NULL;
END;
$$;

CREATE TRIGGER trg_outbox_don_da_giao
AFTER UPDATE OF trang_thai
ON bai349.don_hang
FOR EACH ROW
WHEN (
    OLD.trang_thai IS DISTINCT FROM NEW.trang_thai
    AND NEW.trang_thai = 'DA_GIAO'
)
EXECUTE FUNCTION bai349.fn_ghi_outbox_da_giao();
~~~

Trigger chỉ tạo **dữ liệu outbox**. Không phát tin nhắn, không gọi mạng và không COMMIT bên trong trigger.

Thử trên đơn đã xác nhận:

~~~sql
BEGIN;

UPDATE bai349.don_hang
SET trang_thai = 'DA_GIAO'
WHERE ma_don = 'DH349-002';

SELECT id, khoa_su_kien, loai_su_kien, payload
FROM bai349.outbox_su_kien
WHERE ma_don = 'DH349-002'
ORDER BY id;

ROLLBACK;
~~~

Khi transaction còn mở, hàng outbox xuất hiện cùng với trạng thái DA_GIAO. Sau ROLLBACK, **cả hai bị hủy**. Nếu COMMIT, worker khác có thể đọc sự kiện đã commit để gửi.

### 8.3. Vì sao đây là bài toán trigger hợp lý?

Sự kiện “đơn vừa chuyển thành DA_GIAO” là **hậu quả bắt buộc của việc đổi trạng thái** và cần được ghi **cùng transaction**. Trigger giúp mọi đường cập nhật thông thường không quên tạo outbox row.

Nhưng đôi khi tốt hơn là **stored procedure/service ghi cả đơn lẫn outbox tường minh** nếu mọi đường ghi đều được chuẩn hóa qua một API và dễ kiểm soát. Trigger không phải điều kiện bắt buộc để làm transactional outbox.

### 8.4. Outbox không tự cho exactly-once delivery

Ví dụ dùng khóa `DON_DA_GIAO:ma_don` nhằm hạn chế tạo sự kiện trùng theo một quy tắc cụ thể. Nhưng:

- Worker có thể gửi thành công rồi crash trước khi đánh dấu `gui_luc` → gửi lại.
- Hệ thống bên nhận có thể nhận trùng.
- Nếu một nghiệp vụ cho phép nhiều lần chuyển sang DA_GIAO sau hoàn trả/tái giao, khóa sự kiện trên **ma_don** không còn diễn đạt đúng; cần khóa theo **event id hoặc version**.
- Worker cần retry/backoff, idempotent consumer, dead-letter hoặc kiểm tra trạng thái theo chính sách.
- Không dùng “đánh dấu gửi rồi gửi sau” nếu điều đó làm mất sự kiện khi worker crash.

**Transactional outbox thường cho khả năng phát ít nhất một lần**, với tính nhất quán DB tốt hơn nhưng vẫn cần giải quyết **trùng lặp và thứ tự**.

## 9. Bài toán có thể phù hợp: ghi log theo cả câu INSERT bằng transition table

Row trigger chạy **mỗi hàng**. Với một INSERT thêm hàng nghìn chi tiết đơn, nếu mục tiêu chỉ là ghi **tổng số hàng và tổng số lượng của một statement**, sẽ rất lãng phí nếu thêm một log row cho mỗi hàng.

PostgreSQL hỗ trợ **transition tables** trong những loại AFTER trigger phù hợp, cho phép xem tập hàng được thêm/thay đổi/xóa của statement.

### 9.1. Tạo bảng thống kê lượt thêm chi tiết

~~~sql
CREATE TABLE bai349.nhat_ky_lenh_chi_tiet (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    so_dong INTEGER NOT NULL,
    tong_so_luong BIGINT NOT NULL,
    ghi_luc TIMESTAMPTZ NOT NULL
        DEFAULT CURRENT_TIMESTAMP
);
~~~

### 9.2. AFTER INSERT FOR EACH STATEMENT

~~~sql
CREATE FUNCTION bai349.fn_ghi_lo_chi_tiet()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    INSERT INTO bai349.nhat_ky_lenh_chi_tiet
        (so_dong, tong_so_luong, ghi_luc)
    SELECT
        COUNT(*)::INTEGER,
        COALESCE(SUM(so_luong), 0)::BIGINT,
        statement_timestamp()
    FROM chi_tiet_moi
    HAVING COUNT(*) > 0;

    RETURN NULL;
END;
$$;

CREATE TRIGGER trg_ghi_lo_chi_tiet
AFTER INSERT ON bai349.chi_tiet_don
REFERENCING NEW TABLE AS chi_tiet_moi
FOR EACH STATEMENT
EXECUTE FUNCTION bai349.fn_ghi_lo_chi_tiet();
~~~

### 9.3. Thử một INSERT thêm hai dòng chi tiết

~~~sql
BEGIN;

INSERT INTO bai349.chi_tiet_don
    (don_hang_id, san_pham_id, so_luong, don_gia)
SELECT
    d.id,
    p.id,
    x.so_luong,
    p.gia_hien_tai
FROM (
    VALUES
        ('DH349-001', 1, 2),
        ('DH349-001', 2, 3)
) AS x(ma_don, san_pham_id, so_luong)
JOIN bai349.don_hang AS d
  ON d.ma_don = x.ma_don
JOIN bai349.san_pham AS p
  ON p.id = x.san_pham_id;

SELECT id, so_dong, tong_so_luong
FROM bai349.nhat_ky_lenh_chi_tiet
ORDER BY id DESC;

ROLLBACK;
~~~

Với ví dụ không có lỗi, **một statement INSERT hai dòng** tạo **một log row**: `so_dong = 2` và `tong_so_luong = 5`. Nếu thay bằng hai statement INSERT riêng biệt, statement trigger có thể ghi hai log rows.

### 9.4. Chi tiết về transition tables

- Trong PostgreSQL, chúng được khai báo bằng `REFERENCING NEW TABLE AS ...` hoặc `OLD TABLE AS ...` ở những loại **AFTER** triggers phù hợp.
- Không phải mọi sự kiện, bảng, loại trigger hoặc cú pháp `UPDATE OF cot` đều kết hợp tùy ý với transition tables.
- Statement trigger vẫn được gọi nếu câu INSERT ảnh hưởng **0 hàng**; ví dụ dùng `HAVING COUNT(*) > 0` để không ghi một dòng log trống.
- Transition table đại diện tập hàng ở phạm vi **sự kiện/statement cụ thể** theo semantics PostgreSQL. Nó không phải một bảng bền vững có thể query lại sau transaction.
- Nếu nhu cầu là audit chi tiết từng hàng, bảng tổng hợp chỉ có số lượng **không thay thế** audit OLD/NEW của từng hàng.

**Góc nhìn hiệu năng:** thay việc N row trigger insert thành **một statement-level insert tổng hợp** có thể giảm overhead, nhưng không phải mọi rule row-level đều chuyển thành statement trigger dễ dàng.

## 10. Chi phí ngầm thứ nhất: write amplification

Một câu DML có thể tạo nhiều bản ghi vật lý hơn số hàng người gọi dự tính.

Ví dụ với một UPDATE trạng thái hợp lệ của một đơn:

~~~sql
UPDATE bai349.don_hang
SET trang_thai = 'DA_GIAO'
WHERE ma_don = 'DH349-002';
~~~

Với các trigger demo đã tạo:

1. BEFORE guard trạng thái kiểm tra OLD/NEW.
2. BEFORE metadata function có thể cập nhật `cap_nhat_luc`.
3. Database cập nhật hàng trong `don_hang` và các index liên quan.
4. AFTER audit function INSERT một dòng `lich_su_don`.
5. AFTER outbox function INSERT một dòng `outbox_su_kien` khi chuyển DA_GIAO.
6. Index trên lịch sử/outbox cần được cập nhật.
7. WAL, buffer, khóa và replication có thể chịu chi phí cho các thay đổi bổ sung.

**Một UPDATE logic có thể dẫn đến nhiều row writes.** Nếu mỗi lô sửa 100.000 đơn, audit có thể thêm 100.000 dòng; outbox có thể thêm tới 100.000 dòng cho sự kiện tương ứng. Đây là **hệ số nhân ghi** (*write amplification*), không hiện rõ chỉ từ SQL gọi.

### 10.1. Bảng tính tư duy

| Thành phần | Khi 1 đơn đổi DA_XAC_NHAN → DA_GIAO | Khi 10.000 đơn được đổi |
| --- | ---: | ---: |
| Hàng nguồn cập nhật | 1 | 10.000 |
| BEFORE status guard | 1 lượt | 10.000 lượt |
| BEFORE updated timestamp | 1 lượt | 10.000 lượt |
| AFTER audit | 1 lượt + 1 audit row | 10.000 lượt + 10.000 audit rows |
| AFTER outbox | 1 lượt + tối đa 1 event row | 10.000 lượt + tối đa 10.000 event rows |
| Index maintenance | Theo số index liên quan | Tăng theo khối lượng ghi |
| WAL/redo/undo | Có | Có thể tăng mạnh |

Các con số trên chỉ mô tả **quy mô hoạt động logic của thiết kế demo**, không phải phép đo thời gian hoặc số byte WAL cố định. Nếu nhiều row không thỏa điều kiện, bị trigger bỏ qua hoặc bị transaction rollback, số thực tế khác.

### 10.2. “Chi phí ẩn” vẫn nằm trong độ trễ giao dịch

Ở PostgreSQL, trigger đồng bộ thường chạy trong cùng statement/transaction. Nếu trigger làm công việc tốn 300 ms, caller thường thấy câu DML hoặc transaction chậm tương ứng. Trigger **không tự chuyển chi phí sang background** chỉ vì không nằm trong source code của câu UPDATE.

## 11. Chi phí ngầm thứ hai: N+1 và tổng hợp lại toàn bộ trên từng hàng

Một pattern nguy hiểm là: mỗi khi thêm một chi tiết đơn, trigger **quét lại mọi chi tiết của đơn** để tính tổng rồi cập nhật đơn cha.

Pseudo-SQL:

~~~sql
-- PSEUDOCODE minh họa anti-pattern, không phải function hoàn chỉnh:
-- AFTER INSERT FOR EACH ROW ON chi_tiet_don
--   UPDATE don_hang
--   SET tong_tien = (
--       SELECT COALESCE(SUM(so_luong * don_gia), 0)
--       FROM chi_tiet_don
--       WHERE don_hang_id = NEW.don_hang_id
--   )
--   WHERE id = NEW.don_hang_id;
~~~

Nếu thêm 100 chi tiết của cùng đơn trong một lệnh, row trigger có thể chạy 100 lần và nhiều lần tổng hợp lại tập chi tiết liên quan. Khi càng thêm nhiều hàng, chi phí có thể tăng mạnh, gây tranh chấp trên cùng hàng đơn cha.

### 11.1. Ngay cả “delta update” cũng cần concurrency design

Một biến thể là cộng chênh lệch:

~~~sql
-- Mẫu tư duy cho trường hợp INSERT chi tiết:
-- UPDATE don_hang
-- SET tong_tien = tong_tien + NEW.so_luong * NEW.don_gia
-- WHERE id = NEW.don_hang_id;
~~~

Nó tránh SUM lại toàn bộ, nhưng các trường hợp phải xem xét:

- UPDATE chi tiết thay đổi đơn giá hoặc số lượng: delta là **NEW − OLD**.
- DELETE chi tiết: phải trừ OLD.
- UPDATE chuyển chi tiết từ đơn A sang đơn B: phải điều chỉnh **cả hai đơn**.
- Các trigger khác cũng cập nhật tổng tiền, có nguy cơ cộng/trừ hai lần.
- Cập nhật nhiều đơn theo thứ tự khóa khác nhau có thể tạo deadlock.
- Hai transaction cùng thêm chi tiết cho một đơn có thể tranh chấp một hàng tổng; cần hiểu isolation/lock và bảo vệ bất biến.
- Nếu ai đó sửa `tong_tien` trực tiếp, dữ liệu suy dẫn có thể lệch.
- Phải đối soát lại bảng tổng từ nguồn chi tiết theo định kỳ nếu chấp nhận denormalization.

### 11.2. Những lựa chọn thay thế

| Phương án | Ưu điểm | Nhược điểm |
| --- | --- | --- |
| `SELECT SUM(...) GROUP BY don_hang_id` khi cần | Không lưu giá trị suy dẫn | Truy vấn đọc có thể tốn nếu dữ liệu lớn |
| View cho tổng tiền | Logic rõ và có thể tái dùng | Vẫn có chi phí tổng hợp |
| Materialized view/bảng tổng theo lô | Đọc nhanh, chi phí được gom | Có độ trễ làm mới và consistency contract |
| Trigger row-level cộng delta | Dữ liệu tổng có thể gần như tức thời | Khóa hàng nóng, nhiều trường hợp UPDATE/DELETE |
| Statement trigger với transition table | Có thể gom thay đổi theo lô | Phức tạp hơn và không luôn áp dụng |
| Stored procedure cập nhật chi tiết + tổng trong một transaction | Dòng nghiệp vụ tường minh | Phải bảo đảm mọi đường ghi đi qua procedure |

**Không có lựa chọn luôn đúng.** Nên thiết kế theo tần suất đọc/ghi, yêu cầu tính nhất quán và khả năng kiểm thử.

## 12. Chi phí ngầm thứ ba: khóa và deadlock

Một trigger có thể làm transaction lấy thêm khóa **ngoài bảng người gọi đang sửa**.

Ví dụ:

~~~text
Transaction A:
  UPDATE don_hang(id=1)       -- khóa đơn 1
  Trigger UPDATE tong_ket      -- muốn khóa tổng kết tổ chức 10

Transaction B:
  UPDATE tong_ket tổ chức 10  -- khóa tổng kết
  Trigger/ứng dụng UPDATE don_hang(id=1) -- muốn khóa đơn 1
~~~

Hai transaction có thể chờ khóa của nhau và tạo **deadlock**. DBMS có thể phát hiện và hủy một transaction, nhưng ứng dụng vẫn phải rollback/retry phù hợp.

### 12.1. Lock footprint có thể rộng hơn SQL hiển thị

Một câu:

~~~sql
UPDATE bai349.don_hang
SET trang_thai = 'DA_XAC_NHAN'
WHERE ma_don = 'DH349-001';
~~~

có thể cần:

- Khóa hàng `don_hang`;
- Khóa trên các hàng/bảng khác được trigger INSERT/UPDATE;
- Kiểm tra ràng buộc khóa ngoại, unique và index;
- Ghi WAL/redo/undo;
- Đợi transaction khác ở các tài nguyên mà ứng dụng không đoán ra chỉ từ câu UPDATE.

Trigger không tự tạo deadlock, nhưng nó **mở rộng đồ thị phụ thuộc khóa**.

### 12.2. Cách giảm rủi ro

- Giữ trigger ngắn, truy vấn có index phù hợp.
- Tránh cập nhật hàng tổng **nóng** từ mọi thao tác nhỏ.
- Giữ thứ tự lấy khóa nhất quán giữa các đường ghi.
- Không gọi API mạng hoặc sleep trong transaction.
- Dùng timeout, quan sát lock wait và deadlock logs.
- Retry những lỗi có thể retry bằng **toàn transaction**, có backoff và idempotency.
- Xem xét chuyển thống kê không bắt buộc chính xác tức thời sang batch/CDC.

Không giải quyết deadlock bằng cách tự động tắt trigger trên production.

## 13. Chi phí ngầm thứ tư: trigger đệ quy và vòng gọi dây chuyền

Nếu trigger cập nhật **chính bảng đang kích hoạt**, có thể dẫn tới vòng lặp không kết thúc:

~~~text
UPDATE don_hang
 → AFTER UPDATE trigger
    → UPDATE don_hang
       → AFTER UPDATE trigger
          → UPDATE don_hang
             → ...
~~~

Ví dụ anti-pattern:

~~~sql
-- KHÔNG chạy:
-- CREATE FUNCTION bai349.fn_loi_de_quy()
-- RETURNS trigger LANGUAGE plpgsql AS $$
-- BEGIN
--     UPDATE bai349.don_hang
--     SET cap_nhat_luc = CURRENT_TIMESTAMP
--     WHERE id = NEW.id;
--     RETURN NULL;
-- END;
-- $$;
--
-- CREATE TRIGGER trg_de_quy
-- AFTER UPDATE ON bai349.don_hang
-- FOR EACH ROW EXECUTE FUNCTION bai349.fn_loi_de_quy();
~~~

### 13.1. Giải pháp tốt hơn cho updated_at

Thay vì AFTER UPDATE lại thực hiện UPDATE lên **cùng hàng**, dùng **BEFORE UPDATE** và sửa trực tiếp:

~~~sql
NEW.cap_nhat_luc := statement_timestamp();
RETURN NEW;
~~~

Hành động nằm trong bản ghi NEW của cùng phép UPDATE, tránh một UPDATE bổ sung làm kích hoạt chuỗi mới.

### 13.2. Guard và WHEN để hạn chế kích hoạt không cần thiết

Ví dụ trigger outbox có:

~~~sql
WHEN (
    OLD.trang_thai IS DISTINCT FROM NEW.trang_thai
    AND NEW.trang_thai = 'DA_GIAO'
)
~~~

Nhờ đó, một UPDATE không thay đổi trạng thái sẽ **không gọi function outbox**. Việc kiểm tra `WHEN` vẫn có chi phí đánh giá, nhưng nhẹ hơn gửi INSERT outbox cho mọi UPDATE.

Với trigger guard, dùng điều kiện trạng thái cũ/mới hoặc **cột phát sinh thật sự** thay vì cập nhật cùng bảng rồi chặn đệ quy bằng một biến ngầm.

### 13.3. pg_trigger_depth() không phải thuốc chữa chung

PostgreSQL có `pg_trigger_depth()` cho biết độ sâu trigger hiện tại. Một số code dùng nó làm điều kiện “chỉ chạy ở depth 1”. Nhưng **bỏ qua trigger theo độ sâu** có thể vô tình bỏ kiểm tra nghiệp vụ khi DML hợp lệ được gây ra từ một trigger khác.

Nếu cơ chế yêu cầu “không cập nhật ngược lại”, hãy thiết kế dependency **một chiều**, BEFORE sửa NEW, WHEN rõ nghĩa hoặc chuyển logic sang procedure tường minh. Chỉ dùng depth guard khi đã phân tích đầy đủ chuỗi gọi.

## 14. Chi phí ngầm thứ năm: thứ tự trigger và phụ thuộc khó thấy

Khi nhiều trigger cùng khai báo trên một bảng/sự kiện, thứ tự thực thi có thể ảnh hưởng kết quả.

Trong PostgreSQL, **các trigger cùng loại trên cùng một sự kiện được kích hoạt theo thứ tự tên** theo quy tắc hệ quản trị. Tuy nhiên, thiết kế business logic dựa vào việc ai đó đặt tên trigger “a_”, “b_” để điều phối pipeline nhiều bước là **dễ vỡ**.

### 14.1. Tương tác giữa BEFORE triggers

Nếu có hai BEFORE UPDATE triggers:

1. Trigger A chuẩn hóa `NEW.trang_thai`.
2. Trigger B kiểm tra chuyển trạng thái dựa trên OLD/NEW.

B sẽ nhìn thấy giá trị NEW đã được A thay đổi khi thứ tự thực thi tương ứng. Đổi tên hoặc thêm trigger mới có thể thay đổi cách dữ liệu được đánh giá.

**Khuyến nghị:** nếu những bước phải được điều phối chặt chẽ, cân nhắc gộp vào một function rõ thứ tự hoặc dùng procedure/service. Không chia quy trình nghiệp vụ thành nhiều trigger nhỏ nhưng phụ thuộc ngầm vào tên.

### 14.2. AFTER trigger và dữ liệu đã bị BEFORE trigger sửa

Audit AFTER ROW thường nhìn thấy giá trị hàng đã qua các BEFORE triggers; nếu BEFORE tự thêm timestamp, audit có thể ghi luôn timestamp mới. Điều này hữu ích, nhưng có thể làm số lượng trường khác nhau giữa snapshot OLD và NEW nhiều hơn người dùng kỳ vọng.

### 14.3. Đừng giả định thứ tự trigger giống nhau giữa DBMS

SQL Server, MySQL, Oracle và SQLite có cơ chế chỉ định/giới hạn thứ tự trigger khác nhau. Có hệ hỗ trợ khai báo first/last hoặc FOLLOWS/PRECEDES, có hệ có thứ tự riêng. Không chuyển thiết kế lệ thuộc thứ tự trigger PostgreSQL sang DBMS khác mà không xét lại.

## 15. Một câu UPDATE nhiều hàng có thể kích hoạt bao nhiêu logic?

Ví dụ:

~~~sql
UPDATE bai349.don_hang
SET tong_tien = tong_tien * 1.05
WHERE to_chuc_id = 10;
~~~

Nếu có 3 đơn tổ chức 10 thì ba row-level BEFORE updated_at triggers và ba AFTER audit triggers có thể được gọi. Nếu bảng có 100.000 đơn cùng tổ chức, mỗi loại tương ứng có thể được gọi **100.000 lần**.

### 15.1. Tránh viết trigger như thể chỉ có một hàng

Một số DBMS cung cấp row-level NEW/OLD trực tiếp; số khác dùng bảng transition `inserted/deleted` cho **nhiều hàng**. Việc xử lý đúng multirow DML là bắt buộc.

### 15.2. Khi UPDATE ảnh hưởng 0 hàng

Trong PostgreSQL, **FOR EACH STATEMENT** trigger vẫn có thể được gọi khi câu SQL không làm thay đổi hàng nào; **FOR EACH ROW** trigger sẽ không được gọi vì không có hàng tác động.

Nếu statement trigger có side effect như log “đã xử lý 100 đơn”, nó phải **đếm tập hàng thực sự** hoặc kiểm tra điều kiện, không chỉ nhìn thấy câu lệnh đã được gửi.

### 15.3. Cảnh báo về DELETE rồi TRUNCATE

Trong PostgreSQL:

~~~sql
DELETE FROM bai349.don_hang
WHERE ma_don = 'DH349-004';
~~~

là DML DELETE và có thể kích hoạt DELETE triggers tương ứng.

Còn:

~~~sql
-- Không chạy trên bảng thực hành vì có quan hệ dữ liệu:
-- TRUNCATE TABLE bai349.don_hang;
~~~

là **TRUNCATE**, không phải “DELETE hàng loạt” về mặt sự kiện trigger. PostgreSQL có TRUNCATE triggers riêng ở mức statement, nhưng **row-level DELETE triggers không được gọi cho từng hàng bởi TRUNCATE**. Vì vậy, audit DELETE theo từng hàng có thể **không bao phủ** một TRUNCATE do quản trị viên thực hiện.

Đây là lý do cần kiểm tra toàn bộ đường thay đổi dữ liệu và quyền thao tác đặc biệt nếu audit là yêu cầu bắt buộc.

## 16. Bulk load, COPY, cascade, partition và replication

Trigger có thể bị ảnh hưởng bởi những đường ghi dữ liệu không giống một INSERT/UPDATE thông thường từ ứng dụng.

### 16.1. COPY không đồng nghĩa tắt trigger

Trong PostgreSQL, `COPY FROM` thông thường vẫn thực hiện insert theo cơ chế dẫn tới kích hoạt triggers/ràng buộc phù hợp. Do đó, tải dữ liệu hàng triệu dòng có thể gây chi phí trigger lớn dù câu SQL chỉ là một lệnh COPY.

Đừng giả định “bulk load = không gọi trigger” nếu chưa xác minh chính xác cơ chế tải, quyền và DBMS.

### 16.2. Cascade từ khóa ngoại

Một DELETE/UPDATE trên bảng cha có thể dẫn tới thay đổi bảng con qua `ON DELETE CASCADE` hoặc `ON UPDATE CASCADE`. Những thay đổi đó có thể liên quan trigger ở bảng con theo quy tắc DBMS.

Ví dụ một câu DELETE **một hàng cha** có thể tạo ra rất nhiều DELETE ở bảng con, cộng các audit triggers của bảng con. Vì vậy chi phí của câu SQL **không chỉ phụ thuộc số hàng khớp WHERE trên bảng cha**.

### 16.3. Partitioned tables

Với bảng phân vùng, cách trigger được tạo/clone xuống partition, di chuyển hàng qua partition và xử lý statement/row triggers có chi tiết theo phiên bản PostgreSQL. Không mặc định trigger chỉ trên parent luôn có hiệu lực y hệt mọi loại thao tác trên partition.

### 16.4. Logical replication và replica-role

Trong PostgreSQL, các user triggers có quy tắc kích hoạt khác nhau khi thay đổi được áp dụng bởi logical replication trên subscriber, chịu ảnh hưởng cấu hình trigger và replication role. **Không mặc định trigger audit/outbox trên subscriber sẽ chạy y hệt publisher.**

Trong replication vật lý, replay WAL không phải một luồng câu DML ứng dụng mới để row trigger tự chạy lại từng thao tác. Khi thiết kế sự kiện và audit, phải xác định **nơi nào là nguồn chân lý để trigger phát sinh**.

### 16.5. Không tắt trigger để lách ràng buộc

Các khả năng như `ALTER TABLE ... DISABLE TRIGGER` hoặc cấu hình liên quan replication có thể ảnh hưởng cả tính toàn vẹn và audit. Đó là hành động quản trị nhạy cảm, không nên coi là cách “tối ưu nhanh” để tránh lỗi. Sau khi tắt trigger để bảo trì có kiểm soát, cần quy trình đối soát và xác nhận dữ liệu theo chính sách tổ chức.

## 17. Khi constraint khai báo tốt hơn trigger

Trước khi tạo trigger kiểm tra dữ liệu, hãy tự hỏi: **có constraint đơn giản nào diễn đạt được quy tắc không?**

### 17.1. NOT NULL, CHECK và DEFAULT

~~~sql
CREATE TABLE bai349.yeu_cau_mau (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    so_luong INTEGER NOT NULL CHECK (so_luong > 0),
    trang_thai TEXT NOT NULL DEFAULT 'MOI'
        CHECK (trang_thai IN ('MOI', 'DA_XU_LY'))
);
~~~

Không cần BEFORE INSERT trigger chỉ để gán trạng thái MOI hoặc từ chối `so_luong <= 0`. Constraint và DEFAULT rõ ràng hơn trong schema, dễ đọc, được engine áp dụng theo semantics tương ứng.

### 17.2. UNIQUE và FOREIGN KEY

~~~sql
CREATE TABLE bai349.ma_dinh_danh_mau (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    ma TEXT NOT NULL UNIQUE
);
~~~

Nếu yêu cầu là “mã không được trùng”, **UNIQUE constraint** phù hợp hơn trigger:

~~~text
BEFORE INSERT:
  SELECT COUNT(*) FROM bang WHERE ma=NEW.ma
  Nếu COUNT>0 thì chặn
~~~

Cách tự SELECT để kiểm tra trùng có thể **race** khi hai transaction đồng thời cùng thấy chưa có mã. UNIQUE index/constraint được DBMS thiết kế để bảo vệ quy tắc dưới concurrency theo ngữ nghĩa phù hợp.

Với quan hệ cha–con, hãy ưu tiên `FOREIGN KEY`, không viết trigger thủ công để kiểm tra “ID cha có tồn tại không” nếu constraint có thể biểu đạt được.

### 17.3. Generated columns

Nếu một cột là hàm thuần của các cột trên cùng hàng, chẳng hạn `thanh_tien = so_luong * don_gia`, DBMS có generated column trong những phiên bản/điều kiện nhất định. Trigger BEFORE INSERT/UPDATE chỉ để tính lại công thức có thể tạo gánh nặng bảo trì không cần thiết.

Không phải mọi phép tính tổng từ **nhiều hàng bảng con** đều có thể được đưa vào generated column; đó là loại vấn đề riêng.

## 18. Khi SQL trực tiếp hoặc stored procedure tốt hơn trigger

Giả sử “xác nhận đơn hàng” gồm:

1. Kiểm tra quyền và trạng thái.
2. Kiểm tra tồn kho.
3. Trừ kho.
4. Ghi trạng thái đơn.
5. Ghi outbox event.
6. Hoàn tất transaction.

Đây là **quy trình nghiệp vụ nhiều bước**, có thứ tự và nhiều khả năng lỗi. Nếu giấu toàn bộ trong trigger của `UPDATE don_hang SET trang_thai='DA_XAC_NHAN'`, người gọi khó nhận thấy nó đang làm nhiều điều quan trọng.

### 18.1. Mẫu tường minh

~~~sql
-- Mẫu ý tưởng PostgreSQL, không phải transaction hoàn chỉnh:
BEGIN;

UPDATE bai349.san_pham
SET ton_kho = ton_kho - 2
WHERE id = 1
  AND ton_kho >= 2
RETURNING id, ton_kho;

-- Ứng dụng/procedure PHẢI kiểm tra số hàng RETURNING.
-- Chỉ tiếp tục nếu giữ được bất biến tồn kho.

UPDATE bai349.don_hang
SET trang_thai = 'DA_XAC_NHAN'
WHERE ma_don = 'DH349-001'
  AND trang_thai = 'MOI'
RETURNING id, trang_thai;

-- Kiểm tra số hàng thực tế và các điều kiện khác.
-- ROLLBACK khi có bước bắt buộc không thành công.
ROLLBACK;
~~~

Ví dụ dùng ROLLBACK để không thay đổi demo. Một procedure hoặc service có thể điều phối đầy đủ từng bước, phân loại lỗi, kiểm tra số hàng và COMMIT có chủ đích. Trigger vẫn có thể bổ sung audit/outbox **nhỏ, nhất quán và bắt buộc**.

### 18.2. Phân vai hợp lý

- **Constraint:** bảo vệ bất biến đơn giản/tính toàn vẹn quan hệ.
- **SQL trực tiếp/procedure/service:** thực hiện workflow có chủ đích, nhiều bước.
- **Trigger:** thực hiện một phần logic bắt buộc gắn với thao tác bảng và khó bảo đảm được nếu phân tán ở nhiều đường ghi.
- **Worker/outbox/CDC:** tác vụ liên hệ hệ khác, có thể chậm, cần retry.
- **Báo cáo/materialized view:** tính tổng, truy vấn phân tích và chấp nhận độ trễ nếu nghiệp vụ cho phép.

Không nhất thiết phải chọn **một công cụ duy nhất cho toàn bộ hệ thống**.

## 19. Trigger có làm dữ liệu đồng bộ với hệ thống ngoài không?

Không tự động. Nếu trigger ghi trực tiếp vào database khác thông qua một cơ chế ngoài DB, hoặc gọi HTTP/SMTP, không có gì bảo đảm cả hai hệ thống cùng COMMIT hay cùng ROLLBACK trừ khi có thiết kế giao dịch phân tán thực sự và tất cả bên tham gia hỗ trợ.

### 19.1. Ba trạng thái sự kiện dễ nhầm

| Trạng thái | Ý nghĩa |
| --- | --- |
| Trigger đã chạy | Logic trong trigger được thực thi trong ngữ cảnh statement/transaction |
| Transaction đã COMMIT | Dữ liệu database trong transaction đã được xác nhận |
| Consumer đã xử lý sự kiện | Hệ thống khác đã nhận và xử lý thành công theo hợp đồng riêng |

Ba trạng thái này **không đồng nhất**.

### 19.2. Tình huống lỗi

~~~text
UPDATE đơn
 → Trigger INSERT outbox
 → COMMIT database
 → Worker gửi message
 → Consumer nhận message
 → Worker crash trước khi đánh dấu đã gửi
 → Worker gửi lại
~~~

Không mất dữ liệu outbox, nhưng có thể **gửi trùng**. Consumer cần idempotency và event identifier. Trigger là một phần của hệ thống sự kiện đáng tin cậy, **không phải toàn bộ hệ thống**.

## 20. Bảo mật trigger và quyền thực thi

Trigger chạy ở tầng DB và có thể truy cập bảng ngoài những gì câu DML trực tiếp hiển thị. Đây là lợi ích đóng gói, nhưng cũng là **bề mặt bảo mật**.

### 20.1. PostgreSQL SECURITY DEFINER trigger function

Một trigger function có thể được khai báo theo quyền thực thi của người định nghĩa trong những điều kiện phù hợp. Điều này có thể giúp ghi audit dù caller không được phép trực tiếp ghi bảng audit, nhưng cần cân nhắc:

- Chủ sở hữu function có quyền tới những bảng nào?
- Đã cố định `search_path` an toàn chưa?
- Function có dùng dynamic SQL hay đối tượng schema không được bảo vệ?
- `CURRENT_USER` phản ánh DB identity nào khi chạy quyền definer?
- Caller có thể truyền dữ liệu giả về actor/tenant hay không?
- Vai trò nào có quyền `ALTER TABLE` hoặc `DISABLE TRIGGER`?
- Row-level security được áp dụng ra sao trong ngữ cảnh routine?

Không cấp quyền tạo/đổi trigger, tạo function hay sửa audit cho vai trò ứng dụng thông thường nếu không cần.

### 20.2. Gắn người dùng cuối vào audit

Một connection pool có thể dùng cùng một DB role cho hàng nghìn người dùng. Khi đó `CURRENT_USER` chỉ là role dịch vụ, **không tự nhận diện người dùng thật**.

Nếu ứng dụng truyền actor id bằng session variable hoặc tham số, phải bảo vệ tính đáng tin của nguồn ấy và lifecycle của connection; không để người dùng tự gán một chuỗi tùy ý rồi coi audit là chứng cứ chống giả mạo.

### 20.3. SQL injection vẫn có thể xảy ra

Một trigger function dùng dynamic SQL bằng cách nối trực tiếp input vào tên bảng hoặc giá trị có thể tạo injection. Ưu tiên SQL tĩnh; khi buộc dùng dynamic SQL, quote identifier qua `format('%I', ...)` và bind giá trị bằng `USING` theo cú pháp PL/pgSQL.

Trigger không tự làm câu SQL an toàn chỉ vì nó được lưu trong database.

## 21. Quan sát trigger: đừng chỉ EXPLAIN câu SQL chính

Một khó khăn của logic ngầm là không thể tối ưu thứ bạn **chưa biết đang chạy**.

### 21.1. Xem trigger hiện có trên bảng PostgreSQL

~~~sql
SELECT
    t.tgname AS ten_trigger,
    t.tgenabled AS trang_thai_bat,
    pg_get_triggerdef(t.oid, true) AS dinh_nghia
FROM pg_trigger AS t
WHERE t.tgrelid = 'bai349.don_hang'::regclass
  AND NOT t.tgisinternal
ORDER BY t.tgname;
~~~

`pg_trigger` là system catalog. Điều kiện `NOT t.tgisinternal` loại những trigger nội bộ của hệ quản trị khỏi danh sách ví dụ. `tgenabled` cần được giải thích theo các trạng thái quy định của PostgreSQL; không suy đơn giản mọi trạng thái khác nhau đều có nghĩa “tắt hoàn toàn”.

Có thể xem phần thân trigger function tương ứng bằng công cụ quản trị hoặc system catalog `pg_proc`, nhưng phải có quyền phù hợp.

### 21.2. EXPLAIN ANALYZE với UPDATE

~~~sql
BEGIN;

EXPLAIN (ANALYZE, BUFFERS)
UPDATE bai349.don_hang
SET tong_tien = tong_tien + 1000
WHERE ma_don = 'DH349-001';

ROLLBACK;
~~~

**Cực kỳ quan trọng:** `EXPLAIN ANALYZE` **thực thi thật** câu UPDATE. Nó có thể chạy trigger, tạo audit, dùng sequence, gọi function có side effect. Bọc ROLLBACK trong database thử nghiệm giúp hoàn nguyên dữ liệu transaction, **không bảo đảm thu hồi side effect ngoài database**.

Trong PostgreSQL, kết quả plan của DML có thể có những dòng thống kê dạng:

~~~text
Trigger trg_audit_don_hang: time=... calls=...
Trigger trg_set_cap_nhat_luc: time=... calls=...
~~~

Đây là **mẫu hình có thể xuất hiện**, không phải output đo được của bài. Với ngữ cảnh khác, plan hoặc format có thể khác.

### 21.3. Chỉ đo tổng thời gian là chưa đủ

Cần quan sát:

- Thời gian statement và transaction end-to-end;
- Số lần gọi row trigger;
- Thời gian của từng trigger/function;
- Số row writes ở bảng phụ;
- WAL volume, buffer reads/writes;
- Lock waits, deadlocks, contention trên hàng hot;
- Kích thước audit/outbox, tốc độ tăng index;
- Replication lag;
- Số sự kiện đang chờ worker;
- Tỷ lệ lỗi trigger, retry và timeout.

Nếu mỗi ngày INSERT 1 triệu đơn, audit row cũng có thể tăng 1 triệu/ngày. Retention, backup và chi phí lưu trữ cần được tính trước.

### 21.4. Thống kê function và log

PostgreSQL cung cấp các cơ chế như `pg_stat_user_functions` khi cấu hình `track_functions` phù hợp, `pg_stat_statements` khi có extension/quyền phù hợp, log statement/lock và những công cụ giám sát khác.

Tuy nhiên, thống kê truy vấn bên trong PL/pgSQL có thể được gộp/ghi nhận khác tùy công cụ và cấu hình; không mặc định một dashboard SQL cấp ứng dụng tự hiển thị đủ mọi query do trigger gây ra.

## 22. Kiểm thử trigger theo transaction và nhiều hàng

Trigger là một phần **hợp đồng dữ liệu**, nên phải kiểm tra cả đường thành công lẫn lỗi.

### 22.1. Test rollback cho audit/outbox

~~~sql
BEGIN;

UPDATE bai349.don_hang
SET trang_thai = 'DA_GIAO'
WHERE ma_don = 'DH349-002';

SELECT COUNT(*) AS so_audit
FROM bai349.lich_su_don
WHERE ma_don = 'DH349-002';

SELECT COUNT(*) AS so_outbox
FROM bai349.outbox_su_kien
WHERE ma_don = 'DH349-002';

ROLLBACK;
~~~

Ngay trong transaction, có thể thấy hàng vừa được INSERT bởi trigger; sau ROLLBACK, các thay đổi thuộc transaction bị hoàn nguyên.

**Đừng chỉ kiểm tra sau UPDATE thành công; phải kiểm tra sau ROLLBACK, sau lỗi constraint và sau retry.**

### 22.2. Test multirow

~~~sql
BEGIN;

UPDATE bai349.don_hang
SET tong_tien = tong_tien + 1000
WHERE to_chuc_id = 10;

SELECT ma_don, thao_tac, COUNT(*) AS so_ban_audit
FROM bai349.lich_su_don
GROUP BY ma_don, thao_tac
ORDER BY ma_don, thao_tac;

ROLLBACK;
~~~

Nếu đã có log từ các bài trước được COMMIT, số đếm trong ví dụ bao gồm cả log cũ; để kiểm thử chính xác cần **cô lập dữ liệu test** hoặc ghi nhận mốc trước statement.

### 22.3. Test UPDATE không đổi dữ liệu

~~~sql
BEGIN;

UPDATE bai349.don_hang
SET tong_tien = tong_tien
WHERE ma_don = 'DH349-001';

SELECT id, thao_tac
FROM bai349.lich_su_don
WHERE ma_don = 'DH349-001'
ORDER BY id DESC;

ROLLBACK;
~~~

Row trigger audit mẫu **vẫn có thể ghi lịch sử UPDATE**, vì statement UPDATE đã tác động hàng dù giá trị nghiệp vụ không khác. Nếu yêu cầu là chỉ audit thay đổi thực sự, cần bổ sung điều kiện so sánh OLD/NEW thích hợp, xem tính đúng với cột metadata và NULL.

### 22.4. Test lỗi trong trigger có làm hỏng statement?

Một trigger có thể `RAISE EXCEPTION` nếu dữ liệu vi phạm quy tắc. Lỗi có thể khiến statement và transaction PostgreSQL chuyển sang trạng thái thất bại; ứng dụng phải rollback phù hợp.

Không ngầm nuốt lỗi quan trọng trong trigger rồi `RETURN NEW` như thể dữ liệu đã hợp lệ. Với trigger audit bắt buộc, lỗi ghi audit thường phải làm thao tác nguồn thất bại theo hợp đồng.

### 22.5. Test concurrent sessions

Hai session cùng chuyển trạng thái hoặc sửa các bảng phụ cần được thử với:

- Đường khóa cạnh tranh;
- Thứ tự lock khác nhau;
- Timeout, deadlock và retry;
- Tính nhất quán của tổng hợp/stock;
- Idempotency khi worker gửi outbox;
- Transaction isolation của DBMS thực tế.

**Một bài test một session không chứng minh trigger đúng khi chạy song song.**

## 23. Vì sao trigger khiến debugging khó hơn?

Một lỗi có thể xuất hiện ở chỗ bất ngờ:

~~~text
Ứng dụng:
  UPDATE don_hang SET trang_thai='DA_XAC_NHAN' ...

Database:
  BEFORE trigger kiểm tra trạng thái
  AFTER trigger ghi audit
  AFTER trigger cập nhật bảng tổng
  Bảng tổng vi phạm UNIQUE hoặc CHECK
  → Toàn câu UPDATE lỗi
~~~

Từ góc nhìn ứng dụng, lỗi xuất hiện ở UPDATE đơn nhưng nguyên nhân nằm trong **trigger hoặc bảng phụ**.

### 23.1. Một quy trình debug có hệ thống

1. Ghi lại **câu DML và tham số** gây lỗi, không ghi lộ thông tin nhạy cảm.
2. Xác định DBMS, phiên bản, isolation level và transaction boundary.
3. Liệt kê **trigger của bảng** và những trigger của bảng phụ có thể bị gọi tiếp.
4. Đọc trigger definition và các trigger functions.
5. Xem bảng nào, cột nào và index/constraint nào bị thay đổi ngầm.
6. Reproduce trên dữ liệu thử nghiệm có thể rollback.
7. Dùng EXPLAIN/ANALYZE một cách an toàn, quan sát lock wait và số lần trigger thực thi.
8. Sửa logic ở nơi **sở hữu quy tắc nghiệp vụ**; không vá ứng dụng bằng cách che lỗi.
9. Thêm kiểm thử regression cho single-row, multirow, 0-row, rollback và concurrency.
10. Đối soát dữ liệu lịch sử nếu bug trigger đã tồn tại trên production.

### 23.2. Versioning và thay đổi schema

Một trigger function phụ thuộc cột tên `trang_thai`. Khi migration đổi tên/kiểu cột, function có thể lỗi ở runtime nếu chưa được cập nhật và kiểm tra. Do đó thay đổi schema phải được triển khai cùng phiên bản trigger và các đối tượng phụ thuộc.

Trigger cũng ảnh hưởng cách backfill: một UPDATE khối lượng lớn có thể kích hoạt audit/outbox cho **hàng triệu dữ liệu lịch sử**, dù mục đích chỉ sửa một cột kỹ thuật. Cần thiết kế kế hoạch migration/backfill biết rõ các side effects.

## 24. So sánh PostgreSQL và MySQL/MariaDB

MySQL có DML triggers với cú pháp `BEFORE/AFTER INSERT/UPDATE/DELETE`, nhưng mô hình triển khai khác PostgreSQL.

### 24.1. MySQL row trigger

Ví dụ MySQL, giả sử bảng `don_hang` đã có các cột tương ứng:

~~~sql
-- Trong MySQL CLI, DELIMITER là lệnh phía client để nhập
-- khối nhiều câu; không phải một từ khóa SQL server.
DELIMITER $$

CREATE TRIGGER trg_don_hang_cap_nhat_luc
BEFORE UPDATE ON don_hang
FOR EACH ROW
BEGIN
    IF NOT (NEW.trang_thai <=> OLD.trang_thai)
       OR NOT (NEW.tong_tien <=> OLD.tong_tien) THEN
        SET NEW.cap_nhat_luc = CURRENT_TIMESTAMP;
    END IF;
END$$

DELIMITER ;
~~~

`<=>` là toán tử so sánh **NULL-safe** của MySQL, tránh chuyện hai NULL bị đánh giá UNKNOWN. `FOR EACH ROW` là cấp kích hoạt trọng tâm của MySQL DML triggers; MySQL không có cú pháp statement-level DML trigger tương đương PostgreSQL `FOR EACH STATEMENT` trong trường hợp thông dụng.

### 24.2. Không chép trigger function PostgreSQL sang MySQL

PostgreSQL:

~~~sql
CREATE FUNCTION ... RETURNS trigger LANGUAGE plpgsql ...;
CREATE TRIGGER ... EXECUTE FUNCTION ...;
~~~

MySQL:

~~~sql
CREATE TRIGGER ...
BEFORE/AFTER UPDATE ON ...
FOR EACH ROW
BEGIN
   -- Thân stored program phù hợp MySQL.
END;
~~~

MySQL không dùng `RETURNS trigger LANGUAGE plpgsql`. MySQL còn có giới hạn về việc trigger sửa **chính bảng đang được sử dụng bởi statement kích hoạt**, transaction control và một số thao tác khác.

### 24.3. Tính chất engine/rollback

Với InnoDB transactional tables, các thao tác trong trigger thường tham gia transaction của DML. Nhưng nếu sử dụng storage engine không có tính transaction phù hợp, không thể dựa vào rollback như PostgreSQL/InnoDB. Không khái quát “MySQL trigger rollback được mọi thao tác trên mọi engine”.

### 24.4. Row-level overhead

Vì MySQL triggers thường chạy **cho từng hàng**, một UPDATE 100.000 hàng có thể gọi trigger 100.000 lần. Khi có audit/outbox, cần đặc biệt tính chi phí ghi và mức độ nóng của bảng phụ.

## 25. SQL Server: inserted và deleted là tập hàng

SQL Server có `AFTER` và `INSTEAD OF` DML triggers; nó không có mô hình `BEFORE ROW` PL/pgSQL trực tiếp giống PostgreSQL. Điểm cực kỳ quan trọng là **`inserted` và `deleted` là các bảng logic chứa nhiều hàng**, không phải một biến NEW/OLD duy nhất.

### 25.1. Audit set-based cho UPDATE

Ví dụ SQL Server (giả định các bảng tương ứng đã tồn tại):

~~~sql
CREATE OR ALTER TRIGGER dbo.trg_AuditDonHang
ON dbo.DonHang
AFTER UPDATE
AS
BEGIN
    SET NOCOUNT ON;

    INSERT INTO dbo.LichSuDonHang
        (DonHangId, TrangThaiTruoc, TrangThaiSau,
         ThoiDiem)
    SELECT
        i.Id,
        d.TrangThai,
        i.TrangThai,
        SYSUTCDATETIME()
    FROM inserted AS i
    JOIN deleted AS d
      ON d.Id = i.Id
    WHERE
        i.TrangThai <> d.TrangThai
        OR (i.TrangThai IS NULL AND d.TrangThai IS NOT NULL)
        OR (i.TrangThai IS NOT NULL AND d.TrangThai IS NULL);
END;
~~~

Đây là cú pháp T-SQL, không chạy nguyên văn trên PostgreSQL. Ví dụ dùng so sánh NULL tường minh để dễ hiểu; SQL Server phiên bản hỗ trợ `IS DISTINCT FROM` còn có thể viết ngắn hơn.

Nếu UPDATE tác động 500 hàng, `inserted` và `deleted` có thể chứa **500 hàng** tương ứng. Không viết:

~~~sql
-- Anti-pattern T-SQL:
-- SELECT @Id = Id FROM inserted;
-- UPDATE ... WHERE Id = @Id;
~~~

rồi giả định `inserted` luôn có đúng một hàng. Cách gán scalar như vậy có thể xử lý **chỉ một ID không xác định** trong tập nhiều hàng, gây thiếu audit hoặc sai dữ liệu.

### 25.2. SQL Server trigger không phải tự chạy sau COMMIT

AFTER trigger của SQL Server thông thường vẫn liên quan transaction và có thể khiến câu DML thất bại. Nó không phải một worker hậu commit.

Một số chức năng như Service Broker, CDC, SQL Server Audit hoặc Change Tracking phục vụ mục đích khác; chọn theo yêu cầu audit, tích hợp, độ trễ và khả năng quan sát.

### 25.3. Thứ tự trigger và recursion

SQL Server có cơ chế cấu hình recursion/nested triggers và có thể điều chỉnh trigger order trong những giới hạn phù hợp, nhưng không chuyển trực tiếp các quy tắc PostgreSQL về `TG_OP`, `NEW`, `OLD` sang T-SQL.

## 26. Oracle: row triggers, statement triggers và compound triggers

Oracle PL/SQL hỗ trợ trigger ở mức hàng và mức câu lệnh, cũng như **compound triggers** trong những trường hợp phù hợp.

### 26.1. Row trigger Oracle

~~~sql
CREATE OR REPLACE TRIGGER trg_don_hang_cap_nhat
BEFORE UPDATE ON don_hang
FOR EACH ROW
BEGIN
    :NEW.cap_nhat_luc := SYSTIMESTAMP;
END;
/
~~~

Mẫu dùng Oracle, giả định bảng tương ứng đã có. Trong Oracle, tham chiếu giá trị hàng dùng `:NEW` và `:OLD` trong row trigger; `/` là dấu thực thi block của các client Oracle kiểu SQL*Plus/SQLcl, không phải cú pháp PostgreSQL.

### 26.2. Mutating table

Một vấn đề đặc trưng Oracle là **mutating-table error** như `ORA-04091` khi row-level trigger truy vấn hoặc sửa bảng đang bị thay đổi trong những ngữ cảnh không cho phép.

Điều này nhấn mạnh: “trigger chạy trong DB” không có nghĩa nó được phép đọc/ghi bất kỳ bảng nào theo bất kỳ cách nào. Phải thiết kế theo semantics của engine.

### 26.3. Compound trigger có thể gom logic

Oracle compound trigger có thể dùng các pha như BEFORE STATEMENT, BEFORE EACH ROW, AFTER EACH ROW, AFTER STATEMENT để gom trạng thái theo statement trong những ngữ cảnh được hỗ trợ. Nó có thể giúp giải quyết một số trường hợp cần xử lý theo tập hoặc tránh các thiết kế row trigger không phù hợp.

Tuy nhiên, compound trigger không tự làm quy tắc đa hàng **an toàn với concurrency**; vẫn phải xem khóa, isolation và business invariants.

### 26.4. Autonomous transaction không phải giải pháp audit mặc định

Oracle có autonomous transactions cho những nhu cầu đặc biệt. Nếu một trigger dùng autonomous transaction ghi audit, audit có thể **commit độc lập** ngay cả khi transaction nguồn rollback. Đó có thể đúng cho log “nỗ lực xảy ra”, nhưng sai với audit “thay đổi dữ liệu đã commit”.

Không bật autonomous transaction chỉ để “đảm bảo có log” mà chưa xác định yêu cầu audit và tác động nhất quán.

## 27. SQLite: trigger trên bảng/view và RAISE

SQLite có `CREATE TRIGGER` cho DML; nhiều hành vi được thực thi theo **từng hàng**, không có statement-level trigger thông thường tương ứng PostgreSQL.

### 27.1. SQLite AFTER UPDATE audit

~~~sql
-- SQLite; giả định don_hang và lich_su_don đã tồn tại:
CREATE TRIGGER trg_don_hang_audit
AFTER UPDATE ON don_hang
FOR EACH ROW
WHEN OLD.trang_thai IS NOT NEW.trang_thai
BEGIN
    INSERT INTO lich_su_don
        (don_hang_id, trang_thai_truoc, trang_thai_sau)
    VALUES
        (NEW.id, OLD.trang_thai, NEW.trang_thai);
END;
~~~

Trong SQLite, `IS NOT` có semantics so sánh khác NULL phù hợp với ví dụ; đây không phải phép so sánh mà có thể chép nguyên vào mọi DBMS.

### 27.2. BEFORE UPDATE và NEW

SQLite có các lưu ý quan trọng về hành vi BEFORE triggers, đặc biệt trong những trường hợp trigger sửa/xóa hàng đang được thao tác. Không giả định có thể gán trực tiếp `NEW.cap_nhat_luc := ...` như trong PostgreSQL/Oracle. Thiết kế updated_at có thể cần một cách khác, cân nhắc trigger AFTER với guard và recursion settings, hoặc cập nhật rõ ở ứng dụng.

### 27.3. RAISE trong trigger

SQLite có `RAISE(ABORT, 'message')` và những biến thể khác trong ngữ cảnh trigger, giúp từ chối thao tác khi điều kiện không hợp lệ:

~~~sql
-- Mẫu ý tưởng SQLite:
CREATE TRIGGER trg_khong_quay_lai_moi
BEFORE UPDATE OF trang_thai ON don_hang
FOR EACH ROW
WHEN OLD.trang_thai = 'DA_GIAO'
 AND NEW.trang_thai <> OLD.trang_thai
BEGIN
    SELECT RAISE(ABORT, 'Don da giao khong duoc doi trang thai');
END;
~~~

Khi chạy thật, cần kiểm tra phiên bản SQLite và cách conflict resolution/rollback của từng dạng RAISE.

### 27.4. SQLite không phải PostgreSQL thu nhỏ

SQLite trigger body có các hạn chế cú pháp và điều kiện thực thi riêng; ứng dụng thường là chủ sở hữu transaction. Không mặc định có trigger functions với `LANGUAGE plpgsql`, transition tables hoặc statement-level triggers như PostgreSQL.

## 28. Bảng so sánh trigger theo phương ngữ

| Chủ đề | PostgreSQL | MySQL/MariaDB | SQL Server | Oracle | SQLite |
| --- | --- | --- | --- | --- | --- |
| DML trigger cơ bản | BEFORE/AFTER/INSTEAD OF (view) | BEFORE/AFTER | AFTER/INSTEAD OF | BEFORE/AFTER/INSTEAD OF và loại đặc thù | BEFORE/AFTER/INSTEAD OF (view) |
| FOR EACH ROW | Có | Có | Logic dựa trên tập inserted/deleted, không cùng mô hình ROW PG | Có | Có |
| FOR EACH STATEMENT | Có | Không cùng cú pháp thông dụng | Một lần cho statement, inserted/deleted là tập | Có | Không có mô hình tương đương thông thường |
| Hàng cũ/mới | `OLD`/`NEW` | `OLD`/`NEW` | `deleted`/`inserted` | `:OLD`/`:NEW` | `OLD`/`NEW` |
| Code body | Trigger function (PL/pgSQL, v.v.) | Thân trigger stored program | T-SQL trigger body | PL/SQL | SQL statements trong trigger |
| Transition table | `REFERENCING OLD/NEW TABLE` ở trường hợp hỗ trợ | Không như PG | `inserted/deleted` sẵn là bảng logic | Compound trigger/collection tùy thiết kế | Không giống PG |
| Audit theo transaction | Có | Với engine transactional phù hợp | Có | Có; autonomous là ngoại lệ đặc biệt | Theo transaction SQLite |
| Rủi ro nổi bật | Row overhead, recursive DML, trigger order, replication | Row overhead, hạn chế self-update/engine | Sai khi giả định inserted có một hàng | Mutating table, autonomous transaction | BEFORE semantics và recursive triggers |

Tất cả các hệ đều cần phân biệt **sự kiện, mức kích hoạt, phạm vi transaction và concurrency**. Đừng mang nguyên đoạn trigger của DBMS này sang DBMS khác chỉ vì cùng dùng từ `CREATE TRIGGER`.

## 29. Những sai lầm thường gặp

| Sai lầm | Vì sao nguy hiểm | Hướng xử lý |
| --- | --- | --- |
| “AFTER trigger nghĩa là chạy sau COMMIT.” | Nhiều DBMS thực thi trong transaction. | Phân biệt thời điểm DML với commit. |
| “Câu UPDATE một hàng chỉ ghi một hàng.” | Audit/outbox/summary và index tạo writes bổ sung. | Lập bản đồ side effects, đo write amplification. |
| “Trigger luôn nhanh vì ở trong DB.” | Có CPU, I/O, lock và WAL thật. | EXPLAIN/monitor, tối giản logic. |
| “Mỗi hàng trong multirow DML chỉ cần một biến ID.” | SQL Server inserted/deleted có nhiều hàng; PG row trigger nhiều lần. | Thiết kế set-based hoặc loop đúng cấp. |
| “Dùng trigger kiểm tra UNIQUE thay constraint.” | SELECT kiểm tra có thể race. | UNIQUE constraint/index. |
| “COUNT/SUM trong row trigger luôn an toàn đồng thời.” | Có race và hot-row contention. | Lock/isolation hoặc giải pháp tổng hợp khác. |
| “Gửi HTTP trong trigger để đảm bảo delivery.” | External side effect không rollback và giữ transaction lâu. | Transactional outbox + worker. |
| “Audit trigger ghi được cả rollback.” | Audit row cùng transaction cũng rollback. | Audit-attempt riêng nếu cần. |
| “User CURRENT_USER là khách cuối.” | Connection pool dùng DB role chung. | Authenticated actor context. |
| “Audit JSON toàn bộ hàng luôn hợp lý.” | Có PII, chi phí lưu lớn, retention khó. | Chỉ ghi trường cần, quản lý quyền/retention. |
| “Row trigger tự tránh đệ quy.” | Trigger update cùng bảng có thể lặp vô hạn. | BEFORE sửa NEW hoặc thiết kế một chiều. |
| “pg_trigger_depth() luôn giải quyết recursion.” | Có thể bỏ qua trigger nghiệp vụ hợp lệ. | Guard logic tường minh và dependency rõ. |
| “Tên trigger không ảnh hưởng gì.” | Một số DBMS có thứ tự phụ thuộc tên/cấu hình. | Tránh dựa vào trật tự ngầm. |
| “COPY/bulk load chắc không chạy trigger.” | Semantics tùy DBMS; PostgreSQL COPY FROM kích hoạt trigger phù hợp. | Kiểm tra đường ghi thật. |
| “TRUNCATE tương đương DELETE từng hàng.” | Row DELETE trigger không bao phủ TRUNCATE. | Chính sách quyền/triggers riêng cho TRUNCATE. |
| “Trigger chạy cả trên logical subscriber như publisher.” | Replica-role/replication semantics khác. | Xác định nguồn phát sinh sự kiện. |
| “Bắt mọi lỗi trigger rồi RETURN NEW.” | Có thể bỏ qua bất biến và tạo trạng thái sai. | Phân loại lỗi, cho lỗi quan trọng lan lên. |
| “Tắt trigger để import nhanh luôn an toàn.” | Có thể mất audit và constraint. | Quy trình nhập/đối soát có kiểm soát. |
| “Trigger có thể thay thế phân quyền.” | Definer/SQL động có thể mở lỗ hổng. | Least privilege, kiểm tra tenant và search_path. |
| “Chỉ cần test INSERT một hàng.” | UPDATE nhiều hàng, rollback, concurrency có behavior khác. | Test multirow/0-row/rollback/retry/DDL. |
| “Trigger luôn là nơi tốt nhất cho workflow.” | Có thể che giấu quy trình nhiều bước quan trọng. | Procedure/service tường minh cho orchestration. |
| “Một bản ghi outbox là exactly-once.” | Worker/consumer có thể xử lý trùng. | Event id và idempotency. |
| “EXPLAIN ANALYZE chỉ mô phỏng UPDATE.” | Nó thực thi UPDATE và trigger. | Thử trong transaction/database test. |
| “Thêm trigger không cần sửa migration hay tài liệu.” | Tạo dependency ngầm và rủi ro backfill. | Versioning, docs, runbook và regression tests. |

## 30. Tình huống ra quyết định: chọn đúng công cụ

### Tình huống A: mọi đơn cần có ngày tạo

**Yêu cầu:** khi INSERT nếu không truyền thời gian thì gán ngày tạo.

**Giải pháp ưu tiên:** `DEFAULT CURRENT_TIMESTAMP`. Không cần BEFORE INSERT trigger chỉ để làm đúng điều mà DEFAULT đã diễn đạt rõ.

### Tình huống B: cập nhật ngày sửa khi cột nghiệp vụ đổi

**Yêu cầu:** nhiều hệ thống ghi cùng bảng, cùng quy tắc timestamp.

**Có thể dùng:** BEFORE UPDATE trigger sửa `NEW.cap_nhat_luc`. Cần xác định no-op update, dữ liệu import lịch sử và mức chính xác thời gian.

### Tình huống C: giới hạn số lượng phải > 0

**Giải pháp ưu tiên:** `CHECK (so_luong > 0)` cùng `NOT NULL`. Constraint là hợp đồng rõ, không cần trigger.

### Tình huống D: trạng thái chuyển hợp lệ

**Có thể dùng:** BEFORE UPDATE trigger so sánh OLD/NEW nếu phải bảo vệ tại database. Đồng thời, API nghiệp vụ tường minh/procedure vẫn có ích cho quyền và workflow.

### Tình huống E: cần ghi lịch sử trước/sau của mọi UPDATE

**Có thể dùng:** AFTER ROW audit trigger. Tính rõ chi phí lưu lịch sử, quyền, PII, trường hợp rollback và đường ghi đặc biệt. Nếu yêu cầu forensic/tamper-evident cao, cần cơ chế audit bổ sung.

### Tình huống F: đơn đã giao cần thông báo sang hệ vận chuyển

**Không nên:** gọi HTTP trong trigger. **Có thể:** ghi outbox trong transaction, worker gửi sau commit. Hoặc ứng dụng ghi outbox tường minh cùng transaction nếu kiểm soát tất cả đường ghi.

### Tình huống G: mỗi đơn có 10.000 chi tiết, cần tổng tiền tức thời

**Cần phân tích:** tổng hợp on-read, bảng tổng với delta, statement transition table, materialized view hay procedure. Row trigger SUM lại mọi chi tiết 10.000 lần rất dễ tạo chi phí lớn.

### Tình huống H: chuẩn hóa dữ liệu bằng lower/trim trên INSERT

**Tùy yêu cầu:** nếu giá trị chuẩn hóa phải luôn được lưu ở DB và nhiều đường ghi, BEFORE trigger có thể phù hợp. Nhưng nếu có kiểu dữ liệu, collation, expression index, generated column hoặc validation rõ hơn thì cân nhắc chúng trước.

## 31. Bài tập thực hành có lời giải

Các bài PostgreSQL dưới đây dựa trên schema `bai349` ở mục 3 và các trigger đã định nghĩa. Những bài có DML nên chạy trên **database thử nghiệm**. Để giữ dữ liệu mẫu, dùng `BEGIN ... ROLLBACK`. Các ví dụ tạo trigger mới ở một số bài chỉ mang tính mẫu cần đặt trên đối tượng thích hợp, không giả định bạn muốn cài tất cả cùng lúc.

### Bài 1. Nhận diện logic ngầm

**Câu hỏi:** UPDATE trạng thái đơn có ba trigger: BEFORE guard, AFTER audit, AFTER outbox. Câu UPDATE có thể tạo bao nhiêu thao tác bổ sung?

**Lời giải:** Ít nhất có ba lần kích hoạt logic trigger theo điều kiện; có thể thêm một audit row và một outbox row (nếu trạng thái mới DA_GIAO), cùng công việc cập nhật index/WAL/khóa. Số thao tác thực tế tùy điều kiện trigger và số hàng UPDATE.

### Bài 2. Thời điểm AFTER là gì?

**Câu hỏi:** AFTER UPDATE trigger gửi email có bảo đảm email chỉ gửi sau COMMIT không?

**Lời giải:** Không. AFTER không đồng nghĩa sau transaction commit; gửi email trong trigger có nguy cơ thông báo về thay đổi sau đó bị rollback.

### Bài 3. Constraint hay trigger?

**Yêu cầu:** đảm bảo `tong_tien >= 0`.

**Lời giải:**

~~~sql
-- Đã có trong schema demo:
-- tong_tien NUMERIC(12,2) NOT NULL CHECK (tong_tien >= 0)
~~~

Dùng CHECK và NOT NULL thay vì trigger đọc NEW.tong_tien rồi RAISE EXCEPTION.

### Bài 4. Chặn trạng thái không hợp lệ

**Yêu cầu:** đơn DA_GIAO không thể quay về MOI.

**Lời giải:** BEFORE UPDATE trigger `fn_kiem_tra_chuyen_trang_thai` kiểm tra OLD/NEW đã diễn đạt rule này. Dùng nó như một phần của policy, vẫn kiểm soát quyền caller.

### Bài 5. Audit khi UPDATE không đổi giá trị

**Câu hỏi:** `UPDATE ... SET tong_tien = tong_tien` có thể tạo log audit không?

**Lời giải:** Có, với AFTER UPDATE ROW trigger audit mẫu vì nó được kích hoạt theo thao tác DML, không tự so sánh toàn bộ giá trị nghiệp vụ. Nếu chỉ muốn log khi thay đổi thực tế, thêm kiểm tra OLD/NEW/WHEN phù hợp.

### Bài 6. Ghi metadata theo hàng mới

**Yêu cầu:** tự gán `cap_nhat_luc` khi UPDATE.

**Lời giải:** BEFORE ROW trigger sửa `NEW.cap_nhat_luc` rồi `RETURN NEW`. Không dùng AFTER ROW trigger UPDATE lại cùng bảng chỉ để đổi timestamp.

### Bài 7. Transaction rollback

**Yêu cầu:** UPDATE một đơn rồi xem audit trong transaction, sau đó hủy.

~~~sql
BEGIN;

UPDATE bai349.don_hang
SET tong_tien = tong_tien + 1000
WHERE ma_don = 'DH349-001';

SELECT id, ma_don, thao_tac
FROM bai349.lich_su_don
WHERE ma_don = 'DH349-001'
ORDER BY id DESC;

ROLLBACK;
~~~

**Lời giải:** Audit row trong transaction cũng bị rollback, không còn durable sau ROLLBACK.

### Bài 8. Transactional outbox

**Câu hỏi:** outbox row được trigger thêm, worker nên gửi trước hay sau khi commit?

**Lời giải:** Worker độc lập nên đọc **những outbox rows đã commit**, gửi rồi quản lý trạng thái gửi/retry. Gửi trước commit có thể phát thông báo của thay đổi sau đó không tồn tại.

### Bài 9. Exactly once?

**Câu hỏi:** OUTBOX khóa `DON_DA_GIAO:ma_don` có đảm bảo consumer nhận đúng một lần không?

**Lời giải:** Không. Khóa có thể hạn chế tạo event row trùng theo một business rule, nhưng worker có thể gửi lại sau crash. Consumer cần idempotency theo event ID và chính sách retry.

### Bài 10. Row và statement

**Câu hỏi:** một UPDATE thay đổi 500 hàng; có bao nhiêu lần kích hoạt row trigger và statement trigger cùng event?

**Lời giải:** Row trigger có thể chạy 500 lần; statement trigger một lần cho câu UPDATE. Với UPDATE 0 hàng, row trigger không chạy nhưng statement trigger vẫn có thể chạy.

### Bài 11. Transition table

**Câu hỏi:** vì sao `fn_ghi_lo_chi_tiet` dùng `REFERENCING NEW TABLE`?

**Lời giải:** Statement trigger cần biết **tập hàng INSERT thực sự** để đếm và SUM một lần cho cả statement, thay vì ghi một log row cho từng hàng.

### Bài 12. INSERT hai dòng chi tiết

**Yêu cầu:** thực hành INSERT hai chi tiết từ dữ liệu demo rồi xem log statement.

**Lời giải:** Chạy đoạn INSERT...SELECT trong mục 9.3; trong transaction sẽ có một log với `so_dong = 2`, `tong_so_luong = 5`, nếu cả hai hàng được thêm thành công.

### Bài 13. N+1 trong tổng hợp

**Câu hỏi:** tại sao row trigger SUM lại mọi chi tiết đơn cho từng chi tiết mới có thể rất chậm?

**Lời giải:** Một lệnh nhiều hàng kích hoạt nhiều lần quét/tổng hợp, cộng cập nhật hàng đơn cha và lock contention. Cân nhắc delta an toàn, statement trigger, batch aggregation hoặc tính khi đọc.

### Bài 14. Delta khi UPDATE

**Yêu cầu:** chi tiết đổi từ 2 sản phẩm × 50.000 sang 3 sản phẩm × 50.000. Delta là bao nhiêu?

**Lời giải:** Giá trị cũ 100.000, mới 150.000; **delta = +50.000**. Nếu chỉ cộng giá trị NEW (150.000) thì tổng bị cộng dư 100.000. Khi UPDATE thay cả parent ID, còn phải trừ ở parent cũ và cộng parent mới.

### Bài 15. Tranh chấp tồn kho

**Câu hỏi:** hai transaction cùng đọc `ton_kho=5` rồi mỗi cái đặt 4 chiếc. Chỉ kiểm tra trong trigger bằng SELECT có đủ không?

**Lời giải:** Không. Cần khóa/UPDATE có điều kiện nguyên tử, isolation/retry phù hợp. Nếu cả hai dựa trên dữ liệu cũ và không đồng bộ, có thể bán quá tồn.

### Bài 16. Đệ quy

**Câu hỏi:** AFTER UPDATE trigger tự chạy UPDATE lên cùng hàng có nguy cơ gì?

**Lời giải:** Kích hoạt lại AFTER UPDATE trigger lặp, có thể tạo vòng vô hạn hoặc nhiều row versions. Ưu tiên BEFORE sửa NEW, hoặc guard điều kiện và thiết kế dependency rõ.

### Bài 17. pg_trigger_depth()

**Câu hỏi:** có nên thêm `IF pg_trigger_depth()>1 THEN RETURN NULL; END IF` vào mọi trigger?

**Lời giải:** Không. Nó có thể khiến một đường ghi hợp lệ do trigger khác kích hoạt **không được audit/kiểm tra**. Sửa thiết kế recursion và xác định rule trước.

### Bài 18. SQL Server inserted/deleted

**Câu hỏi:** vì sao không gán `SELECT @Id = Id FROM inserted` rồi audit một ID?

**Lời giải:** `inserted` có thể có nhiều hàng cho một statement. Gán scalar không xử lý toàn bộ tập; cần câu INSERT...SELECT set-based JOIN inserted/deleted.

### Bài 19. MySQL khác PostgreSQL thế nào?

**Câu hỏi:** MySQL có dùng `CREATE FUNCTION ... RETURNS trigger LANGUAGE plpgsql` không?

**Lời giải:** Không. MySQL định nghĩa body trực tiếp trong `CREATE TRIGGER ... FOR EACH ROW ...`, với cú pháp stored program của MySQL.

### Bài 20. Oracle mutating table

**Câu hỏi:** lỗi ORA-04091 liên quan gì đến trigger?

**Lời giải:** Một row-level trigger Oracle có thể không được phép truy vấn/sửa bảng đang mutating theo cách lập trình, gây lỗi. Cần thay thiết kế, có thể dùng compound trigger hoặc SQL/constraint thích hợp.

### Bài 21. SQLite trước/sau

**Câu hỏi:** có thể viết `NEW.cap_nhat_luc := now()` trong SQLite BEFORE trigger như PostgreSQL không?

**Lời giải:** Không theo cú pháp PostgreSQL. SQLite có semantics và hạn chế BEFORE trigger khác, phải thiết kế theo SQLite thay vì chép đoạn PL/pgSQL.

### Bài 22. Audit và PII

**Câu hỏi:** `to_jsonb(NEW)` có nên được dùng cho audit bảng chứa mật khẩu, token, địa chỉ không?

**Lời giải:** Không mặc định. Cần chọn trường được phép lưu, che/mã hóa dữ liệu, retention, quyền truy cập và kiểm soát cả backup/replica.

### Bài 23. Bulk load

**Câu hỏi:** dùng PostgreSQL COPY FROM một triệu hàng có bỏ qua mọi trigger tự động không?

**Lời giải:** Không. COPY FROM thông thường kích hoạt những trigger/ràng buộc INSERT phù hợp, nên phải dự toán chi phí. Không tắt trigger để tăng tốc nếu chưa có quy trình kiểm soát và đối soát.

### Bài 24. TRUNCATE

**Câu hỏi:** audit chỉ bằng AFTER DELETE FOR EACH ROW có ghi lại từng hàng nếu quản trị viên chạy TRUNCATE không?

**Lời giải:** Không. PostgreSQL TRUNCATE là sự kiện khác, không chạy row-level DELETE trigger cho từng hàng. Cần quyền/quy tắc TRUNCATE riêng nếu muốn chặn hoặc ghi nhận.

### Bài 25. Debug câu UPDATE chậm

**Yêu cầu:** nêu cách tìm trigger liên quan mà không nhìn source code của ứng dụng.

**Lời giải:** Truy vấn `pg_trigger` với `pg_get_triggerdef` như mục 21.1, đọc trigger functions, đo bằng EXPLAIN (ANALYZE, BUFFERS) trên database thử nghiệm và quan sát số lần calls, lock waits, WAL/rows phụ.

### Bài 26. EXPLAIN ANALYZE có an toàn mặc định không?

**Câu hỏi:** `EXPLAIN ANALYZE DELETE ...` có thực sự xóa hàng không?

**Lời giải:** Có. EXPLAIN ANALYZE **thực thi** DML. Dùng trên môi trường kiểm soát, bọc transaction/rollback khi hợp lệ, và nhớ các side effects ngoài transaction có thể không thu hồi.

### Bài 27. Versioning trigger khi migration

**Tình huống:** đổi tên cột `trang_thai` thành `tinh_trang`. Điều gì cần thay ngoài câu UPDATE của ứng dụng?

**Lời giải:** Kiểm tra trigger definitions/functions phụ thuộc OLD/NEW, các predicate, index/constraints, outbox payload, audit schema, tài liệu và tests. Migration không cập nhật trigger có thể khiến DML runtime lỗi.

### Bài 28. Chọn công cụ cho quy tắc nghiệp vụ

**Tình huống:** xác nhận đơn, trừ kho, ghi outbox, kiểm tra quyền, sau đó gọi vận chuyển bên ngoài.

**Gợi ý:** Dùng transaction/procedure/service tường minh cho các bước bắt buộc và kiểm tra quyền; dùng constraint và DML tồn kho có điều kiện nguyên tử; ghi outbox cùng transaction (qua trigger nhỏ hoặc code tường minh); worker xử lý gọi vận chuyển sau commit với retry/idempotency.

## 32. Checklist thiết kế và vận hành trigger

Trước khi tạo hoặc thay đổi trigger trên bảng có tải thật, nên tự trả lời:

1. **Rule thuộc lớp nào?** Constraint, generated column, SQL query, procedure, application, CDC hay trigger?
2. **Vì sao rule phải nằm trong trigger?** Có nhiều đường ghi và cần gắn bắt buộc với thay đổi không?
3. **Sự kiện chính xác là gì?** INSERT, UPDATE, DELETE hay TRUNCATE/DDL?
4. **Thời điểm nào?** BEFORE để chỉnh NEW/guard, AFTER để ghi hậu quả trong transaction?
5. **Cấp nào?** ROW hay STATEMENT; có cần transition tables không?
6. **Multirow DML có hoạt động đúng không?** Trên 0, 1 và rất nhiều hàng?
7. **Đã tính tất cả bảng/index bị ghi ngầm chưa?**
8. **Trigger có truy vấn lại một tập lớn cho mỗi hàng không?**
9. **Có update cùng bảng hoặc chuỗi gọi gây recursion không?**
10. **Các trigger cùng event có phụ thuộc thứ tự không?**
11. **Có khóa thêm hàng nóng hoặc thay đổi thứ tự lock không?**
12. **Concurrency có bảo đảm bất biến không?** Có dùng lock/isolation đúng?
13. **Khi lỗi trigger, caller và transaction sẽ ở trạng thái nào?**
14. **Cần audit thay đổi đã commit hay cả nỗ lực thất bại?**
15. **Có side effect ngoài database không?** Nếu có, dùng outbox/worker phù hợp.
16. **Outbox có event ID, retry và idempotent consumer không?**
17. **PII và retention trong audit/outbox có được kiểm soát không?**
18. **Quyền trigger function, SECURITY DEFINER và search_path đã an toàn chưa?**
19. **Bulk load, cascade, partitioning và replication có semantics như mong đợi không?**
20. **Có cho phép TRUNCATE hoặc DISABLE TRIGGER không?** Ai được quyền?
21. **Có test rollback và repeated request không?**
22. **Có test concurrency/locks/deadlock không?**
23. **Có thống kê thời gian trigger, số lần gọi, WAL và latency không?**
24. **Có quy trình versioning, migration, backfill và khôi phục không?**
25. **Nếu người khác chỉ đọc câu DML, họ có tìm ra tài liệu side effects ở đâu?**

### 32.1. Quy tắc tài liệu hóa

Mỗi trigger quan trọng nên có ít nhất:

- Tên trigger và bảng/sự kiện kích hoạt;
- Rule nghiệp vụ được bảo vệ và lý do không dùng constraint đơn giản;
- Các bảng/đối tượng phụ bị đọc hoặc thay đổi;
- Điều kiện WHEN và những trường hợp bỏ qua;
- Kỳ vọng transaction/rollback;
- Chi phí ước lượng theo số hàng;
- Ràng buộc concurrency, lock order, idempotency;
- Quy trình triển khai/disable/reenable/đối soát;
- Bộ test đặc trưng và người sở hữu logic.

Nếu không thể viết rõ những nội dung ấy, trigger đang có nguy cơ trở thành **“ma thuật trong database”** mà khó đội nào bảo trì.

## 33. Tài liệu tham khảo chính thức

Khi triển khai cần đối chiếu **đúng DBMS và phiên bản**:

- **PostgreSQL:** [CREATE TRIGGER](https://www.postgresql.org/docs/current/sql-createtrigger.html), [PL/pgSQL Trigger Functions](https://www.postgresql.org/docs/current/plpgsql-trigger.html), [Triggers](https://www.postgresql.org/docs/current/triggers.html), [CREATE FUNCTION](https://www.postgresql.org/docs/current/sql-createfunction.html), [EXPLAIN](https://www.postgresql.org/docs/current/sql-explain.html), [Explicit Locking](https://www.postgresql.org/docs/current/explicit-locking.html), [Logical Replication](https://www.postgresql.org/docs/current/logical-replication.html).
- **MySQL:** [CREATE TRIGGER](https://dev.mysql.com/doc/refman/8.4/en/create-trigger.html), [Stored Program Restrictions](https://dev.mysql.com/doc/refman/8.4/en/stored-program-restrictions.html).
- **SQL Server:** [CREATE TRIGGER](https://learn.microsoft.com/en-us/sql/t-sql/statements/create-trigger-transact-sql), [Use the inserted and deleted tables](https://learn.microsoft.com/en-us/sql/relational-databases/triggers/use-the-inserted-and-deleted-tables), [Create DML Triggers to Handle Multiple Rows of Data](https://learn.microsoft.com/en-us/sql/relational-databases/triggers/create-dml-triggers-to-handle-multiple-rows-of-data).
- **Oracle:** [PL/SQL Triggers](https://docs.oracle.com/en/database/oracle/oracle-database/19/lnpls/plsql-triggers.html), [CREATE TRIGGER](https://docs.oracle.com/en/database/oracle/oracle-database/19/lnpls/CREATE-TRIGGER-statement.html).
- **SQLite:** [CREATE TRIGGER](https://www.sqlite.org/lang_createtrigger.html), [Transactions](https://www.sqlite.org/lang_transaction.html).

Đây là nguồn học và đối chiếu semantics; không có một “cú pháp trigger SQL chuẩn” đủ để sao chép nguyên code giữa các hệ quản trị.

## 34. Kết luận

Trigger phù hợp nhất khi một quy tắc **thực sự phải gắn với thay đổi dữ liệu tại database**, đặc biệt khi nhiều đường ghi cùng cần thực hiện nó, và chi phí tác dụng phụ **nhỏ, ổn định, đo được**. Các ví dụ điển hình là metadata cập nhật, kiểm tra chuyển trạng thái cần OLD/NEW, audit transactionally coupled và ghi bản tin outbox trong cùng transaction.

Tuy nhiên, trigger có một **chi phí kiến trúc khó thấy**:

1. **Một câu DML có thể làm nhiều việc hơn người gọi nhìn thấy**: thêm audit/outbox rows, sửa bảng khác, lấy khóa và tăng WAL.
2. **Row triggers nhân chi phí theo số hàng**; một UPDATE 100.000 hàng có thể kích hoạt function 100.000 lần.
3. **Logic ngầm có thể làm câu SQL lỗi hoặc chậm** do bảng phụ, FK, khóa hoặc deadlock.
4. **Đệ quy và thứ tự trigger** tạo quan hệ phụ thuộc khó phát hiện.
5. **Bulk load, TRUNCATE, cascade, partitioning và replication** không thể mặc định được bao phủ như DML thông thường.
6. **Trigger không thay thế constraint, transaction owner, bảo mật, idempotency hoặc worker bất đồng bộ**.
7. **Phải quan sát và tài liệu hóa side effects** với đầy đủ kiểm thử single-row, multirow, rollback, concurrency và migration.

**Câu hỏi thiết kế quan trọng nhất không phải “Có viết được trigger không?” mà là “Nếu một người khác chỉ nhìn thấy INSERT/UPDATE/DELETE, họ có hiểu được mọi việc database sẽ tự làm, chi phí của chúng và cách khôi phục khi lỗi không?”**. Trigger tốt là trigger có trách nhiệm rõ, hiệu ứng nhỏ và được kiểm soát; trigger xấu là nơi chôn giấu quy trình nghiệp vụ mà không ai dự đoán được.
