# RETURNING, OUTPUT và các cơ chế lấy dữ liệu sau khi INSERT theo phương ngữ SQL

Khi một ứng dụng thêm khách hàng, đơn hàng hoặc bản ghi sự kiện vào cơ sở dữ liệu, thao tác `INSERT` không chỉ có ý nghĩa “lưu được một dòng”. Ứng dụng thường cần biết **ID thực tế vừa được sinh**, **thời điểm tạo do database gán**, **trạng thái mặc định**, **giá trị do biểu thức sinh** hoặc một số thông tin khác của bản ghi vừa ghi thành công.

Ví dụ:

~~~sql
INSERT INTO khach_hang (ten) VALUES ('An');
~~~

Giả sử `id` là khóa tự sinh và `trang_thai` có `DEFAULT 'MOI'`. Sau câu lệnh, chương trình cần lấy được một kết quả kiểu:

~~~text
id = 1257
ten = 'An'
trang_thai = 'MOI'
tao_luc = <thời điểm database ghi nhận>
~~~

**Số 1257 chỉ là minh họa:** trong database thật không được dự đoán ID tự sinh từ số dòng hiện có hoặc từ ID của bản ghi trước.

Những hệ quản trị khác nhau có cơ chế trả về dữ liệu của hàng vừa thêm:

- **PostgreSQL:** `INSERT ... RETURNING ...`.
- **SQL Server:** `INSERT ... OUTPUT INSERTED....` hoặc `OUTPUT ... INTO ...`.
- **Oracle Database:** thường dùng `INSERT ... RETURNING ... INTO ...` với biến PL/SQL hoặc biến bind của driver.
- **MariaDB:** hỗ trợ `INSERT ... RETURNING` từ phiên bản 10.5.
- **SQLite:** hỗ trợ `RETURNING` từ phiên bản 3.35.0.
- **MySQL:** trong cú pháp `INSERT` của MySQL 8.4 không có `RETURNING` theo cách trên; thường dùng **`LAST_INSERT_ID()`**, API lấy generated keys của driver hoặc truy vấn lại bằng khóa nghiệp vụ duy nhất.

Bài học này nằm trong chương **Thêm dữ liệu** của Database SQL, nên trọng tâm là lấy kết quả **ngay sau thao tác INSERT**. Các ví dụ `UPDATE`, `DELETE` và `MERGE` được đưa vào khi cần giúp phân biệt giá trị trước/sau và phạm vi hỗ trợ của từng phương ngữ.

## 1. Vì sao cần lấy dữ liệu của bản ghi vừa thêm?

Một câu `INSERT` có thể tạo ra nhiều giá trị **không được ứng dụng gửi lên trực tiếp**.

| Nguồn giá trị | Ví dụ | Vì sao ứng dụng cần lấy lại? |
| --- | --- | --- |
| ID tự sinh | `IDENTITY`, `AUTO_INCREMENT`, sequence | Dùng làm khóa ngoại cho đơn hàng, địa chỉ, chi tiết |
| Giá trị `DEFAULT` | `trang_thai = 'MOI'` | Hiển thị đúng trạng thái database chấp nhận |
| Thời gian do database gán | `DEFAULT CURRENT_TIMESTAMP` | Tránh tự đoán thời điểm từ đồng hồ ứng dụng |
| UUID do database tạo | `DEFAULT gen_random_uuid()` ở PostgreSQL | Trả định danh mới cho API |
| Giá trị chuẩn hóa | Cột được tính, logic trigger thích hợp | Phản ánh giá trị mà thao tác ghi đã tạo |
| Khóa nghiệp vụ | `ma_yeu_cau`, `ma_don` | Đối chiếu đầu vào và hàng kết quả trong thao tác hàng loạt |

Chẳng hạn:

~~~mermaid
flowchart LR
    A["Ứng dụng\nGửi tên và mã yêu cầu"] --> B["INSERT"]
    B --> C["Database\nSinh ID, áp DEFAULT,\nkiểm tra ràng buộc"]
    C --> D["Kết quả RETURNING / OUTPUT\nID, trạng thái, thời điểm"]
    D --> E["Ứng dụng\nĐọc đúng khóa đã tạo"]
~~~

Nếu database có khả năng trả dữ liệu của chính câu lệnh ghi, thường **không cần một câu `SELECT` riêng** chỉ để đoán bản ghi nào vừa được tạo. Tuy nhiên, lấy được giá trị trả về không có nghĩa giao dịch đã được **`COMMIT`**; hai vấn đề này phải được phân biệt.

### 1.1. Ba khái niệm dễ bị đánh đồng

1. **Số hàng bị tác động (*affected row count*):** ví dụ “đã chèn 1 hàng”; không cho biết ID hay thời gian được sinh.
2. **Khóa tự sinh (*generated key*):** thường là một ID, có thể lấy qua câu SQL hoặc API của driver.
3. **Hàng được trả về (*returned row*):** tập cột/biểu thức từ bản ghi bị tác động, có thể gồm ID, trạng thái, thời điểm, cột tính toán.

Một API trả `affectedRows = 1` không đồng nghĩa nó đã trả `id`. Ngược lại, một mệnh đề `RETURNING` có thể trả **nhiều cột, nhiều hàng**.

### 1.2. Hai mẫu nghiệp vụ

**Thêm một khách rồi tạo một đơn:**

~~~text
INSERT khách → lấy khach_hang_id thực tế → INSERT đơn với FK đó
~~~

**Thêm nhiều khách trong một batch:**

~~~text
Gửi (ma_yeu_cau, ten) của nhiều khách
→ nhận nhiều (ma_yeu_cau, id)
→ ghép kết quả về đúng bản ghi yêu cầu ban đầu
~~~

Trong trường hợp batch, việc **đối chiếu đầu vào–đầu ra** thường quan trọng không kém việc lấy được ID.

## 2. Bộ dữ liệu thực hành PostgreSQL

Ta tạo hai bảng tạm để minh họa quan hệ khách hàng–đơn hàng. Dùng **cùng một phiên kết nối PostgreSQL** cho các ví dụ; bảng tạm không tồn tại khi phiên kết thúc.

~~~sql
CREATE TEMP TABLE khach_hang_ret (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    ma_yeu_cau TEXT NOT NULL UNIQUE,
    ten TEXT NOT NULL,
    email TEXT,
    trang_thai TEXT NOT NULL DEFAULT 'MOI'
        CHECK (trang_thai IN ('MOI', 'DA_XAC_MINH', 'TAM_KHOA')),
    tao_luc TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    da_xac_minh BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE TEMP TABLE don_hang_ret (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    khach_hang_id BIGINT NOT NULL
        REFERENCES khach_hang_ret(id),
    ma_don TEXT NOT NULL UNIQUE,
    gia_tri NUMERIC(12, 2) NOT NULL
        CHECK (gia_tri >= 0),
    trang_thai TEXT NOT NULL DEFAULT 'MOI',
    tao_luc TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
~~~

Các cột quan trọng:

| Cột | Vai trò | Nguồn giá trị |
| --- | --- | --- |
| `khach_hang_ret.id` | Khóa chính nội bộ | `GENERATED ALWAYS AS IDENTITY` |
| `khach_hang_ret.ma_yeu_cau` | Khóa đối chiếu đầu vào, duy nhất | Ứng dụng gửi |
| `khach_hang_ret.ten` | Tên khách | Ứng dụng gửi |
| `khach_hang_ret.trang_thai` | Trạng thái ban đầu | `DEFAULT 'MOI'` nếu bị bỏ qua |
| `khach_hang_ret.tao_luc` | Thời điểm tạo | `DEFAULT CURRENT_TIMESTAMP` |
| `khach_hang_ret.da_xac_minh` | Cờ xác minh | `DEFAULT FALSE` |
| `don_hang_ret.khach_hang_id` | Khóa ngoại | Lấy từ ID khách vừa chèn |
| `don_hang_ret.id` | Khóa chính đơn | `IDENTITY` |

`ma_yeu_cau` dùng để **đối chiếu và minh họa tính duy nhất**. Nó không thay thế cơ chế idempotency hoàn chỉnh của ứng dụng; một hệ thống thật phải quy định phạm vi duy nhất, vòng đời khóa và cách xử lý một yêu cầu lặp với nội dung khác.

**Lưu ý về kết quả mẫu:** các ID và thời điểm dưới đây do database sinh ra trong lúc chạy, nên bài chủ yếu mô tả **tên cột, số hàng và ý nghĩa kết quả**, không giả định ID bắt đầu từ 1 hoặc thời gian luôn cố định.

## 3. PostgreSQL: INSERT ... RETURNING cơ bản

Cú pháp thường dùng:

~~~sql
INSERT INTO ten_bang (cot_1, cot_2, ...)
VALUES (gia_tri_1, gia_tri_2, ...)
RETURNING cot_a, cot_b, ...;
~~~

Ví dụ:

~~~sql
INSERT INTO khach_hang_ret (ma_yeu_cau, ten, email)
VALUES ('REQ-KH-001', 'An', 'an@example.test')
RETURNING
    id,
    ma_yeu_cau,
    ten,
    trang_thai,
    tao_luc,
    da_xac_minh;
~~~

Kết quả trả về là **một hàng** tương ứng với khách vừa được chèn, gồm:

~~~text
id            = <ID do database sinh>
ma_yeu_cau    = REQ-KH-001
ten           = An
trang_thai    = MOI
tao_luc       = <TIMESTAMPTZ do database gán>
da_xac_minh   = false
~~~

**Tác dụng của `RETURNING`:** câu lệnh vừa ghi dữ liệu vừa **trả tập kết quả của những hàng được tác động**, không buộc ứng dụng phải đoán ID hoặc thực hiện một `SELECT` riêng chỉ để lấy giá trị mặc định.

### 3.1. RETURNING * và danh sách cột

~~~sql
INSERT INTO khach_hang_ret (ma_yeu_cau, ten)
VALUES ('REQ-KH-002', 'Bình')
RETURNING *;
~~~

`RETURNING *` trả **mọi cột đầu ra của bảng mục tiêu**, có thể hữu ích khi thực hành. Trong API sản xuất, thường nên chọn cột tường minh:

~~~sql
RETURNING id, ma_yeu_cau, trang_thai, tao_luc
~~~

Lý do: giảm dữ liệu trả về, tránh vô tình làm lộ cột nội bộ hoặc nhạy cảm, đồng thời giúp giao diện trả kết quả ổn định nếu sau này bảng thêm cột.

### 3.2. Biểu thức và bí danh trong RETURNING

`RETURNING` ở PostgreSQL hỗ trợ danh sách biểu thức tương tự danh sách biểu thức của `SELECT`:

~~~sql
INSERT INTO khach_hang_ret (ma_yeu_cau, ten)
VALUES ('REQ-KH-003', 'Chi')
RETURNING
    id,
    upper(ten) AS ten_viet_hoa,
    (id::text || ':' || ma_yeu_cau) AS ma_tham_chieu,
    CASE
        WHEN da_xac_minh THEN 'DA_XAC_MINH'
        ELSE 'CHUA_XAC_MINH'
    END AS tinh_trang;
~~~

Các biểu thức chỉ tạo **cột của tập kết quả trả về**. Ví dụ `ten_viet_hoa` không tự động ghi tên in hoa trở lại bảng; muốn cập nhật cột vật lý phải có logic ghi riêng.

### 3.3. RETURNING không phải một SELECT độc lập

`RETURNING` là **mệnh đề của câu INSERT đang chạy**:

~~~sql
INSERT INTO khach_hang_ret (ma_yeu_cau, ten)
VALUES ('REQ-KH-004', 'Dung')
RETURNING id;
~~~

Không viết:

~~~sql
-- Sai kiểu cú pháp:
-- INSERT ...;
-- RETURNING id;
~~~

Và không đặt `RETURNING` ở một vị trí tùy ý giữa `VALUES`, `ON CONFLICT` và các mệnh đề khác. Với `INSERT` PostgreSQL, `RETURNING` thường đặt **cuối câu INSERT**.

## 4. RETURNING với DEFAULT, IDENTITY, NULL và thời gian

Phần lớn giá trị cần lấy sau khi INSERT xuất phát từ **quy tắc của schema**.

### 4.1. Bỏ qua cột để database áp dụng DEFAULT

~~~sql
INSERT INTO khach_hang_ret (ma_yeu_cau, ten)
VALUES ('REQ-KH-005', 'Em')
RETURNING
    id,
    trang_thai,
    tao_luc,
    da_xac_minh;
~~~

`trang_thai` trả `'MOI'`, `da_xac_minh` trả `FALSE`, `tao_luc` có giá trị thời gian do database gán, còn `id` là khóa `IDENTITY` vừa sinh.

Có thể chỉ rõ `DEFAULT`:

~~~sql
INSERT INTO khach_hang_ret
    (ma_yeu_cau, ten, trang_thai, da_xac_minh)
VALUES
    ('REQ-KH-006', 'Giang', DEFAULT, DEFAULT)
RETURNING id, trang_thai, da_xac_minh;
~~~

Trong các cột này, việc bỏ cột và dùng `DEFAULT` có tác dụng tương ứng.

### 4.2. Giá trị NULL không đồng nghĩa DEFAULT

Hai câu sau **khác nhau**:

~~~sql
-- Dùng mặc định:
INSERT INTO khach_hang_ret (ma_yeu_cau, ten)
VALUES ('REQ-KH-007', 'Hà')
RETURNING trang_thai;

-- Bị từ chối bởi NOT NULL nếu chạy:
-- INSERT INTO khach_hang_ret (ma_yeu_cau, ten, trang_thai)
-- VALUES ('REQ-KH-008', 'Hải', NULL);
~~~

Khi ứng dụng **gửi `NULL` tường minh**, database không tự chuyển nó thành `DEFAULT 'MOI'` chỉ vì cột có default. Với cột cho phép `NULL`, chèn `NULL` thường lưu `NULL`; với cột `NOT NULL`, câu chèn thất bại.

Vì vậy, khi thiết kế DTO hoặc ORM, hãy quyết định rõ trường **không được truyền** khác với trường **được truyền bằng `null`** như thế nào.

### 4.3. IDENTITY không bảo đảm liên tục

`GENERATED ALWAYS AS IDENTITY` nhờ database quản lý khóa. Giá trị được sinh từ sequence có thể **bị nhảy** khi giao dịch thất bại, rollback, tranh chấp, cache hoặc các đặc tính cấp số.

Không viết code kiểu:

~~~sql
-- Sai về an toàn và tính đúng:
-- SELECT MAX(id) + 1 FROM khach_hang_ret;
-- INSERT INTO khach_hang_ret (id, ...) VALUES (<giá trị vừa đoán>, ...);
~~~

`MAX(id)+1` không phải cách lấy ID vừa sinh và có thể gây tranh chấp khi nhiều kết nối chèn đồng thời. Với khóa sinh tự động, hãy để database cấp rồi nhận lại qua cơ chế tương ứng.

### 4.4. CURRENT_TIMESTAMP và thời điểm ghi thực tế

Trong PostgreSQL, `CURRENT_TIMESTAMP` phản ánh **thời điểm bắt đầu giao dịch**. Nếu một giao dịch thực hiện nhiều câu INSERT ở những thời điểm khác nhau, các hàng có thể cùng `tao_luc` khi dùng default này. Nếu cần thời gian đồng hồ tại thời điểm đánh giá, PostgreSQL có `clock_timestamp()` với ngữ nghĩa khác.

`RETURNING tao_luc` giúp lấy **đúng giá trị đã được lưu theo định nghĩa cột**. Không suy rằng timestamp luôn là thời điểm gói tin đi đến ứng dụng hoặc là một thời điểm duy nhất cho mọi hàng.

## 5. PostgreSQL: chèn nhiều hàng và trả nhiều hàng

Đối với câu `INSERT ... VALUES` nhiều hàng:

~~~sql
INSERT INTO khach_hang_ret (ma_yeu_cau, ten)
VALUES
    ('REQ-BATCH-001', 'Hồng'),
    ('REQ-BATCH-002', 'Lan'),
    ('REQ-BATCH-003', 'Minh')
RETURNING
    id,
    ma_yeu_cau,
    ten,
    trang_thai;
~~~

Kết quả có **ba hàng** nếu cả ba hàng được chèn thành công. Mỗi hàng mang ID và dữ liệu của một khách vừa được thêm.

### 5.1. Không gán ID cho input theo vị trí trả về

Giả sử client gửi:

~~~text
Input 0: REQ-BATCH-001 / Hồng
Input 1: REQ-BATCH-002 / Lan
Input 2: REQ-BATCH-003 / Minh
~~~

Không nên giả định rằng:

~~~text
Output[0] luôn ứng với Input[0]
Output[1] luôn ứng với Input[1]
Output[2] luôn ứng với Input[2]
~~~

**Thứ tự hàng trả về không phải hợp đồng ánh xạ có thể dựa vào cho mọi kiểu INSERT, kế hoạch thực thi và DBMS.** Đặc biệt khi nguồn đến từ `INSERT ... SELECT`, bị lọc hoặc xảy ra xử lý xung đột, việc gán theo vị trí là không đáng tin.

Trong ví dụ, hãy ánh xạ dựa trên **`ma_yeu_cau` duy nhất**:

| Dữ liệu input | Cột để tìm lại hàng kết quả | Dữ liệu lấy từ output |
| --- | --- | --- |
| `REQ-BATCH-001` | `ma_yeu_cau` | `id` và `trang_thai` thực tế |
| `REQ-BATCH-002` | `ma_yeu_cau` | `id` và `trang_thai` thực tế |
| `REQ-BATCH-003` | `ma_yeu_cau` | `id` và `trang_thai` thực tế |

Tốt nhất, khóa đối chiếu phải có **ràng buộc duy nhất** hoặc một quan hệ ánh xạ được bảo đảm theo thiết kế. Không dùng `ten` để ánh xạ: nhiều người có thể trùng tên.

### 5.2. Khác biệt giữa số input và số hàng trả về

Một lệnh thường có thể sinh **số hàng output ít hơn input**, ví dụ dùng `ON CONFLICT DO NOTHING` trong PostgreSQL. Vì thế, không viết code bắt buộc “gửi 100 hàng luôn nhận đúng 100 ID” nếu câu lệnh có thể bỏ qua trùng khóa.

Cần xác định **mỗi input đã được chèn, được cập nhật hay bị bỏ qua**, dựa trên chính sách xung đột và khóa đối chiếu.

### 5.3. INSERT ... SELECT cũng dùng RETURNING

~~~sql
WITH nguon (ma_yeu_cau, ten) AS (
    VALUES
        ('REQ-SRC-001', 'Ngân'),
        ('REQ-SRC-002', 'Phúc')
)
INSERT INTO khach_hang_ret (ma_yeu_cau, ten)
SELECT ma_yeu_cau, ten
FROM nguon
RETURNING id, ma_yeu_cau, ten;
~~~

`RETURNING` trả các hàng đã được chèn vào **bảng đích**, không phải một bản sao nguyên trạng của bảng nguồn. Trong PostgreSQL, danh sách `RETURNING` của INSERT thông thường nên dựa vào **cột của bảng đích**. Nếu cần trả một mã request đầu vào, hãy lưu nó vào cột đích có chủ đích như `ma_yeu_cau`.

## 6. PostgreSQL: ON CONFLICT kết hợp RETURNING

Trong ứng dụng có ràng buộc `UNIQUE`, một yêu cầu có thể được gửi lại. PostgreSQL có cơ chế `ON CONFLICT`.

### 6.1. DO NOTHING: không chèn thì không có hàng RETURNING

Khách `REQ-KH-001` đã được chèn ở mục 3:

~~~sql
INSERT INTO khach_hang_ret (ma_yeu_cau, ten)
VALUES ('REQ-KH-001', 'An')
ON CONFLICT (ma_yeu_cau) DO NOTHING
RETURNING id, ma_yeu_cau;
~~~

Nếu khóa duy nhất đã tồn tại, câu lệnh **không chèn hàng**; `RETURNING` trả **0 hàng**. Nó không tự trả ID của hàng cũ bị xung đột.

Ứng dụng cần phân biệt:

- **Một hàng được trả:** thao tác thêm đã tạo bản ghi trong nhánh này.
- **Không có hàng được trả:** có thể do xung đột bị bỏ qua; cần quy định xử lý tiếp theo nếu vẫn cần ID hiện có.

Đừng gọi một `ResultSet` rỗng là “database mất ID”.

### 6.2. DO UPDATE: trả hàng được thêm hoặc cập nhật

~~~sql
INSERT INTO khach_hang_ret (ma_yeu_cau, ten)
VALUES ('REQ-KH-001', 'An Mới')
ON CONFLICT (ma_yeu_cau)
DO UPDATE SET ten = EXCLUDED.ten
RETURNING id, ma_yeu_cau, ten, trang_thai;
~~~

Nếu hàng đã tồn tại, nó được **cập nhật** tên và `RETURNING` trả giá trị sau khi thao tác cập nhật của câu lệnh hoàn tất theo ngữ nghĩa PostgreSQL.

Tuy nhiên:

> Không nên dùng `DO UPDATE` chỉ để “lấy ID cũ” một cách máy móc.

Việc cập nhật có thể kích hoạt trigger, audit, lock, cập nhật timestamp hoặc phát sinh tác động nghiệp vụ. Trong hệ thống idempotent, nên định nghĩa rõ **payload trùng được chấp nhận**, **payload khác phải bị từ chối hay được cập nhật**, và cơ chế lấy lại ID của yêu cầu cũ.

### 6.3. DO UPDATE ... WHERE có thể không trả hàng

~~~sql
INSERT INTO khach_hang_ret (ma_yeu_cau, ten)
VALUES ('REQ-KH-001', 'An Mới Hơn')
ON CONFLICT (ma_yeu_cau)
DO UPDATE SET ten = EXCLUDED.ten
WHERE khach_hang_ret.ten IS DISTINCT FROM EXCLUDED.ten
RETURNING id, ma_yeu_cau, ten;
~~~

Nếu điều kiện `WHERE` của nhánh cập nhật **không thỏa**, hàng có thể bị khóa phục vụ xử lý xung đột nhưng **không được cập nhật**, vì thế không có hàng tương ứng trong `RETURNING`.

Đây là một lý do khác khiến số hàng đầu ra không luôn bằng số hàng đầu vào.

### 6.4. Lựa chọn đúng cho idempotency

Một cách thiết kế thường gặp là:

1. Tạo **khóa yêu cầu duy nhất** do client gửi hoặc server cấp trước, bảo đảm cùng thao tác logic mang cùng khóa.
2. Kiểm tra/ghi bằng ràng buộc `UNIQUE` ở database.
3. Nếu khóa đã tồn tại, **kiểm tra nội dung yêu cầu** và trả kết quả đã lưu hoặc thông báo trùng không hợp lệ theo chính sách.
4. Không suy diễn rằng chỉ một câu `ON CONFLICT DO NOTHING RETURNING` đủ xử lý mọi vấn đề đồng thời; khi đọc lại kết quả có thể cần giao dịch, mức cô lập phù hợp hoặc cơ chế khóa riêng.

## 7. PostgreSQL: lấy ID khách để tạo đơn hàng

Một tình huống điển hình là cần ID của hàng cha để chèn hàng con.

### 7.1. Hai câu INSERT trong một giao dịch

Ở tầng ứng dụng, ta có thể làm:

~~~text
BEGIN
INSERT khách ... RETURNING id
Đọc id từ kết quả
INSERT đơn ... (khach_hang_id = id vừa đọc)
COMMIT
~~~

Ví dụ SQL thủ công với biến ID do ứng dụng quản lý sẽ phụ thuộc driver. **Không** lấy `MAX(id)`, **không** lấy `id` của “bản ghi cuối bảng” bằng một `SELECT` không có khóa.

Ưu điểm: rõ từng bước, dễ áp dụng trong API. Yêu cầu quan trọng là dùng **cùng transaction và connection** cho những thao tác cần ràng buộc nguyên tử.

### 7.2. PostgreSQL: data-modifying CTE đưa ID trực tiếp sang INSERT tiếp theo

PostgreSQL hỗ trợ một câu SQL kết hợp hai thao tác thông qua `WITH` và `RETURNING`:

~~~sql
WITH
khach_moi AS (
    INSERT INTO khach_hang_ret (ma_yeu_cau, ten)
    VALUES ('REQ-CHA-001', 'Quỳnh')
    RETURNING id AS khach_hang_id, ma_yeu_cau
),
don_moi AS (
    INSERT INTO don_hang_ret
        (khach_hang_id, ma_don, gia_tri)
    SELECT
        khach_hang_id,
        'DON-GHEP-001',
        250000
    FROM khach_moi
    RETURNING
        id AS don_hang_id,
        khach_hang_id,
        ma_don,
        trang_thai,
        tao_luc
)
SELECT
    k.khach_hang_id,
    k.ma_yeu_cau,
    d.don_hang_id,
    d.ma_don,
    d.trang_thai,
    d.tao_luc
FROM khach_moi AS k
JOIN don_moi AS d
    ON d.khach_hang_id = k.khach_hang_id;
~~~

**Luồng dữ liệu:**

~~~mermaid
flowchart TD
    A["INSERT khach_hang_ret"] --> B["RETURNING khach_hang_id"]
    B --> C["INSERT don_hang_ret\nnhận FK từ khach_moi"]
    C --> D["RETURNING don_hang_id, ma_don"]
    B --> E["SELECT kết quả cha + con"]
    D --> E
~~~

Ở đây, dữ liệu trao đổi giữa hai phần DML đi qua **đầu ra `RETURNING` của CTE**, không phải một truy vấn đọc tùy tiện vào bảng đích vừa ghi.

**Lưu ý nâng cao của PostgreSQL:** data-modifying CTE có quy tắc thực thi và snapshot riêng; các nhánh DML không nên cùng cố thay đổi một hàng, và thứ tự tác động vật lý giữa các nhánh không phải thứ có thể dựa vào ngoài quan hệ dữ liệu được truyền qua `RETURNING`. Khi xử lý nghiệp vụ phức tạp, có thể lựa chọn giao dịch nhiều lệnh rõ ràng hơn.

### 7.3. Vì sao không thể chép nguyên mẫu này sang SQLite?

SQLite có `INSERT ... RETURNING`, nhưng **không hỗ trợ dùng kết quả DML RETURNING như một bảng/CTE đầu vào cho câu SELECT khác** theo cách data-modifying CTE ở PostgreSQL. Cần dùng các lệnh của driver và giao dịch riêng, hoặc cấu trúc được SQLite hỗ trợ.

**Tên cùng là `RETURNING` không đồng nghĩa khả năng kết hợp DML với WITH giống nhau giữa các DBMS.**

## 8. PostgreSQL: RETURNING còn dùng cho UPDATE và DELETE

Dù bài tập trung vào thêm dữ liệu, hiểu sự khác biệt này giúp tránh nhầm “hàng vừa thêm” với “hàng bị thay đổi”.

### 8.1. UPDATE ... RETURNING

~~~sql
UPDATE khach_hang_ret
SET trang_thai = 'DA_XAC_MINH',
    da_xac_minh = TRUE
WHERE ma_yeu_cau = 'REQ-KH-001'
RETURNING id, ma_yeu_cau, trang_thai, da_xac_minh;
~~~

`RETURNING` ở ví dụ này trả **giá trị mới của hàng được cập nhật**. Nếu `WHERE` không khớp hàng nào, kết quả trả về **0 hàng**.

### 8.2. DELETE ... RETURNING

~~~sql
DELETE FROM khach_hang_ret
WHERE ma_yeu_cau = 'REQ-KH-007'
RETURNING id, ma_yeu_cau, ten;
~~~

`DELETE ... RETURNING` trả dữ liệu của **hàng vừa bị xóa**, không phải giá trị sau xóa (vì hàng không còn tồn tại).

Với lệnh ghi trong môi trường thực, cần kiểm tra khóa, quyền và phạm vi `WHERE`. Không dùng ví dụ DELETE trên dữ liệu sản xuất nếu chưa hiểu ràng buộc khóa ngoại, cascade và các hệ quả nghiệp vụ.

### 8.3. Các phiên bản PostgreSQL mới và MERGE

PostgreSQL hiện đại còn hỗ trợ `RETURNING` cho `MERGE` ở phiên bản tương ứng. Một số phiên bản mới hỗ trợ tham chiếu trực tiếp **giá trị cũ và mới** trong danh sách `RETURNING`, nhưng cách viết/khả năng hỗ trợ phụ thuộc **phiên bản máy chủ**.

Đối với thao tác thêm dữ liệu cơ bản, mẫu an toàn dễ hiểu vẫn là:

~~~sql
INSERT INTO ... VALUES (...)
RETURNING id, cot_mac_dinh, cot_thoi_gian;
~~~

Đừng tự chép cú pháp `OLD`/`NEW` của tài liệu PostgreSQL mới vào một máy chủ cũ mà chưa xác nhận phiên bản.

## 9. SQL Server: OUTPUT INSERTED thay cho RETURNING

SQL Server dùng **`OUTPUT`** để trả dữ liệu của các hàng bị `INSERT`, `UPDATE`, `DELETE` hoặc `MERGE`. Với INSERT, giá trị sau thao tác được tham chiếu bằng tiền tố **`INSERTED.`**.

### 9.1. Bảng minh họa T-SQL

Đoạn sau là cú pháp **SQL Server**, không chạy trực tiếp trên PostgreSQL:

~~~sql
CREATE TABLE dbo.KhachHangOutputDemo (
    Id BIGINT IDENTITY(1,1) PRIMARY KEY,
    MaYeuCau NVARCHAR(40) NOT NULL UNIQUE,
    Ten NVARCHAR(100) NOT NULL,
    TrangThai NVARCHAR(20) NOT NULL
        CONSTRAINT DF_KhachHangDemo_TrangThai DEFAULT N'MOI',
    TaoLuc DATETIME2(3) NOT NULL
        CONSTRAINT DF_KhachHangDemo_TaoLuc DEFAULT SYSUTCDATETIME()
);
~~~

`Id` do `IDENTITY(1,1)` sinh, `TrangThai` dùng default `N'MOI'`, còn `TaoLuc` dùng `SYSUTCDATETIME()` của SQL Server.

### 9.2. INSERT ... OUTPUT INSERTED...

~~~sql
INSERT INTO dbo.KhachHangOutputDemo (MaYeuCau, Ten)
OUTPUT
    INSERTED.Id,
    INSERTED.MaYeuCau,
    INSERTED.TrangThai,
    INSERTED.TaoLuc
VALUES (N'REQ-SQL-001', N'An');
~~~

Cách đọc:

- `INSERT INTO ... (MaYeuCau, Ten)`: xác định bảng đích và dữ liệu cần ghi.
- `OUTPUT INSERTED.Id, ...`: yêu cầu trả cột của **hàng vừa được chèn**.
- `VALUES (...)`: dữ liệu đầu vào.

**Thứ tự cú pháp cần nhớ:** trong SQL Server, `OUTPUT` nằm **trước phần `VALUES` hoặc nguồn dữ liệu của INSERT**, không phải sau `VALUES` như `RETURNING` trong PostgreSQL.

So sánh hai câu tương ứng:

~~~sql
-- PostgreSQL:
INSERT INTO khach_hang_ret (ma_yeu_cau, ten)
VALUES ('REQ-PG-X', 'An')
RETURNING id, trang_thai;
~~~

~~~sql
-- SQL Server:
INSERT INTO dbo.KhachHangOutputDemo (MaYeuCau, Ten)
OUTPUT INSERTED.Id, INSERTED.TrangThai
VALUES (N'REQ-MS-X', N'An');
~~~

Một câu có ý nghĩa gần nhau, nhưng **khác chính tả tên cột, cú pháp đặt mệnh đề và khả năng xử lý trigger**.

### 9.3. OUTPUT INSERTED.* và danh sách cột

SQL Server hỗ trợ xuất nhiều cột của hàng `INSERTED`. Tuy nhiên trong API thực tế, nên chỉ trả những cột cần thiết:

~~~sql
OUTPUT INSERTED.Id, INSERTED.TrangThai
~~~

Trả toàn bộ hàng có thể tạo tải mạng không cần thiết hoặc làm lộ dữ liệu mà caller không nên thấy. Một câu DML không nên trở thành kênh tự động trả mọi thông tin cá nhân chỉ vì `OUTPUT INSERTED.*` thuận tiện.

## 10. SQL Server: OUTPUT INTO lưu kết quả vào biến bảng

Ngoài việc trả trực tiếp một result set cho client, SQL Server có thể đưa kết quả `OUTPUT` vào **table variable** hoặc bảng đích được cho phép:

~~~sql
DECLARE @KetQua TABLE (
    Id BIGINT,
    MaYeuCau NVARCHAR(40),
    TrangThai NVARCHAR(20),
    TaoLuc DATETIME2(3)
);

INSERT INTO dbo.KhachHangOutputDemo (MaYeuCau, Ten)
OUTPUT
    INSERTED.Id,
    INSERTED.MaYeuCau,
    INSERTED.TrangThai,
    INSERTED.TaoLuc
INTO @KetQua (Id, MaYeuCau, TrangThai, TaoLuc)
VALUES (N'REQ-SQL-002', N'Bình');

SELECT Id, MaYeuCau, TrangThai, TaoLuc
FROM @KetQua;
~~~

`@KetQua` là **biến bảng trong batch/phạm vi T-SQL tương ứng**, không phải bảng khách hàng vật lý mới. Nó có thể được xử lý tiếp, lọc hoặc kết hợp với những tập dữ liệu khác theo cú pháp SQL Server.

### 10.1. Trigger: lưu ý quan trọng khi dùng OUTPUT

Theo quy tắc SQL Server, nếu bảng mục tiêu có **trigger đang bật cho loại DML tương ứng**, mệnh đề **`OUTPUT` trực tiếp không có `INTO`** có thể bị từ chối. **`OUTPUT ... INTO`** là một cơ chế thường dùng để ghi nhận kết quả trong trường hợp này, nhưng bản thân bảng đích của `INTO` cũng chịu những hạn chế về trigger, ràng buộc và loại đối tượng.

Một khác biệt quan trọng nữa: trong SQL Server, các giá trị từ `OUTPUT INSERTED` phản ánh hàng **sau thao tác DML nhưng trước khi các trigger được thực thi**. Nếu trigger tiếp tục sửa dữ liệu, **đầu ra OUTPUT không mặc nhiên là ảnh chụp cuối cùng sau mọi trigger**.

Không nên tự suy luận rằng `OUTPUT` và `RETURNING` của PostgreSQL có cùng thứ tự xử lý với trigger.

### 10.2. OUTPUT có thể trả kết quả dù câu lệnh gặp lỗi

Tài liệu SQL Server cảnh báo rằng `OUTPUT` có thể phát ra hàng cho client ngay cả khi câu lệnh gặp lỗi và bị rollback. Vì vậy:

**Chỉ sử dụng dữ liệu OUTPUT như một kết quả ghi thành công khi toàn bộ câu lệnh và giao dịch đã được xác nhận thành công.**

Đừng đưa một ID vào hệ thống khác hoặc trả “đã tạo thành công” chỉ vì driver đã nhận được một hàng OUTPUT nhưng lệnh ghi sau đó báo lỗi.

## 11. SQL Server: INSERTED và DELETED trong UPDATE, DELETE

SQL Server phân biệt hai hình ảnh logic:

- **`INSERTED`**: giá trị mới sau thao tác chèn/cập nhật.
- **`DELETED`**: giá trị trước khi cập nhật hoặc trước khi xóa.

Ví dụ `UPDATE`:

~~~sql
UPDATE dbo.KhachHangOutputDemo
SET TrangThai = N'DA_XAC_MINH'
OUTPUT
    DELETED.Id,
    DELETED.TrangThai AS TrangThaiCu,
    INSERTED.TrangThai AS TrangThaiMoi
WHERE MaYeuCau = N'REQ-SQL-001';
~~~

Trong `UPDATE`, cả giá trị trước và sau có thể hữu ích cho audit. Với `DELETE`:

~~~sql
DELETE FROM dbo.KhachHangOutputDemo
OUTPUT DELETED.Id, DELETED.MaYeuCau
WHERE MaYeuCau = N'REQ-SQL-002';
~~~

`DELETED` ở ví dụ xóa là giá trị **trước khi hàng bị loại khỏi bảng**.

### 11.1. OUTPUT trong thao tác nhiều hàng

~~~sql
INSERT INTO dbo.KhachHangOutputDemo (MaYeuCau, Ten)
OUTPUT INSERTED.Id, INSERTED.MaYeuCau
VALUES
    (N'REQ-SQL-B1', N'Chi'),
    (N'REQ-SQL-B2', N'Dung');
~~~

SQL Server **không bảo đảm thứ tự các hàng được thay đổi hoặc thứ tự hàng OUTPUT** tương ứng với thứ tự các hàng trong danh sách input. Để đối chiếu, sử dụng `MaYeuCau` duy nhất được ghi vào bảng đích, không ghép hai mảng theo chỉ số.

Đặc biệt với `INSERT ... SELECT`, `OUTPUT` của INSERT thông thường nên tham chiếu các cột `INSERTED` hợp lệ; không mặc định mọi cột của nguồn SELECT đều truy cập được trong OUTPUT. Nếu cần mã tương quan, hãy bảo đảm nó được lưu hoặc có chiến lược mapping rõ ràng.

## 12. SQL Server: SCOPE_IDENTITY, @@IDENTITY và IDENT_CURRENT

Khi chỉ cần **một giá trị identity** của một INSERT, SQL Server còn có các hàm tiện ích:

~~~sql
INSERT INTO dbo.KhachHangOutputDemo (MaYeuCau, Ten)
VALUES (N'REQ-SQL-003', N'Em');

SELECT CAST(SCOPE_IDENTITY() AS BIGINT) AS IdVuaSinh;
~~~

`SCOPE_IDENTITY()` lấy giá trị identity gần nhất được tạo trong **cùng phiên và cùng scope** (ví dụ cùng batch hoặc stored procedure theo định nghĩa scope của SQL Server).

| Cơ chế | Phạm vi | Rủi ro nếu dùng sai |
| --- | --- | --- |
| `OUTPUT INSERTED.Id` | Những hàng do chính câu DML tác động | Cần xét trigger, thứ tự, lỗi và transaction |
| `SCOPE_IDENTITY()` | Identity gần nhất của cùng phiên và scope | Chỉ là một giá trị, không trả nhiều cột/nhiều ID của batch |
| `@@IDENTITY` | Identity gần nhất trong phiên, không bị giới hạn scope theo cách trên | Có thể lấy ID được tạo bên trong trigger ở bảng khác |
| `IDENT_CURRENT('dbo.Table')` | Identity hiện tại của bảng được chỉ định, **không gắn riêng phiên caller** | Có thể chịu tác động từ phiên khác; không dùng để nhận diện bản ghi của chính request |

Với API cần trả nhiều cột hoặc chèn nhiều hàng, `OUTPUT INSERTED....` thường thể hiện ý định rõ hơn so với một hàm chỉ trả identity.

**Không dùng `@@IDENTITY` hoặc `IDENT_CURRENT` như một cách an toàn chung để xác định ID của câu INSERT vừa thực hiện.** Chúng có ngữ nghĩa phạm vi khác, đặc biệt khi trigger và nhiều kết nối cùng hoạt động.

## 13. Oracle Database: RETURNING ... INTO

Oracle sử dụng cú pháp **`RETURNING ... INTO ...`** để đưa giá trị từ DML vào **biến PL/SQL** hoặc **biến bind của client/driver**. Đây không phải đúng kiểu “thêm `RETURNING id` rồi nhận result set như PostgreSQL”.

### 13.1. Bảng minh họa Oracle

~~~sql
CREATE TABLE khach_hang_oracle_demo (
    id NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    ma_yeu_cau VARCHAR2(40) NOT NULL UNIQUE,
    ten VARCHAR2(100) NOT NULL,
    trang_thai VARCHAR2(20) DEFAULT 'MOI' NOT NULL,
    tao_luc TIMESTAMP WITH TIME ZONE
        DEFAULT SYSTIMESTAMP NOT NULL
);
~~~

Cú pháp này dành cho **Oracle**, không chạy nguyên văn trên PostgreSQL, MySQL hay SQL Server.

### 13.2. Nhận giá trị vào biến PL/SQL

~~~sql
SET SERVEROUTPUT ON

DECLARE
    v_id khach_hang_oracle_demo.id%TYPE;
    v_trang_thai khach_hang_oracle_demo.trang_thai%TYPE;
BEGIN
    INSERT INTO khach_hang_oracle_demo (ma_yeu_cau, ten)
    VALUES ('REQ-ORA-001', 'An')
    RETURNING id, trang_thai INTO v_id, v_trang_thai;

    DBMS_OUTPUT.PUT_LINE(
        'ID=' || v_id || ', TrangThai=' || v_trang_thai
    );
END;
/
~~~

Giải thích:

1. `DECLARE` định nghĩa hai biến để chứa ID và trạng thái.
2. `INSERT ... VALUES` tạo hàng.
3. `RETURNING id, trang_thai INTO v_id, v_trang_thai` gán giá trị trả về vào biến.
4. `DBMS_OUTPUT.PUT_LINE` minh họa cách in kết quả trong công cụ hỗ trợ `DBMS_OUTPUT`.

`SET SERVEROUTPUT ON` là lệnh của một số **SQL client Oracle** như SQL*Plus/SQLcl, **không phải cú pháp SQL chuẩn nằm trong PL/SQL block**. Dấu `/` cũng là ký hiệu thực thi block của các công cụ tương ứng. Khi dùng driver ứng dụng, cách truyền và nhận dữ liệu khác.

### 13.3. RETURNING vào biến bind của ứng dụng

Mẫu tổng quát:

~~~sql
INSERT INTO khach_hang_oracle_demo (ma_yeu_cau, ten)
VALUES (:ma_yeu_cau, :ten)
RETURNING id INTO :id_moi;
~~~

Ứng dụng phải **khai báo và bind `:id_moi` là tham số đầu ra** theo API driver Oracle phù hợp. Không coi nó như một biến có sẵn trong SQL worksheet.

### 13.4. Nhiều hàng: BULK COLLECT INTO khi phù hợp

Trong PL/SQL, một câu DML ảnh hưởng nhiều hàng có thể dùng `RETURNING ... BULK COLLECT INTO` để đưa các giá trị vào collection:

~~~sql
DECLARE
    TYPE t_ids IS TABLE OF khach_hang_oracle_demo.id%TYPE;
    v_ids t_ids;
BEGIN
    UPDATE khach_hang_oracle_demo
    SET trang_thai = 'DA_XAC_MINH'
    WHERE ma_yeu_cau LIKE 'REQ-ORA-%'
    RETURNING id BULK COLLECT INTO v_ids;

    FOR i IN 1 .. v_ids.COUNT LOOP
        DBMS_OUTPUT.PUT_LINE('ID=' || v_ids(i));
    END LOOP;
END;
/
~~~

Đây là ví dụ **UPDATE nhiều hàng để minh họa cú pháp bulk output**, không phải lời khuyên cập nhật toàn bộ khách theo tiền tố trong hệ thống thật.

Oracle có nhiều hạn chế và quy tắc riêng giữa **static DML, dynamic SQL, `FORALL`, biến bind và `BULK COLLECT`**. Không suy rằng một `INSERT ... VALUES (...), (...)` kiểu PostgreSQL cộng `RETURNING` sẽ tự hoạt động giống nhau ở mọi phiên bản Oracle.

### 13.5. Không có hàng trả về thì sao?

Với DML không tác động hàng nào, biến của `RETURNING INTO` không mặc nhiên chứa một ID hợp lệ. Trong PL/SQL có thể dùng **`SQL%ROWCOUNT`** sau DML để biết số hàng bị ảnh hưởng và xử lý trường hợp không có hàng.

**Quy tắc chung:** chỉ dùng giá trị đầu ra khi thao tác DML thực sự thành công và có số hàng như nghiệp vụ kỳ vọng.

## 14. MySQL: LAST_INSERT_ID và generated keys

MySQL cần được phân biệt rõ với MariaDB. Trong MySQL 8.4, không nên viết:

~~~sql
-- Không phải cú pháp INSERT thông thường của MySQL 8.4:
-- INSERT INTO khach_mysql (ten) VALUES ('An') RETURNING id;
~~~

Thay vào đó, MySQL có **`AUTO_INCREMENT`** và `LAST_INSERT_ID()`.

### 14.1. Bảng minh họa MySQL

~~~sql
CREATE TABLE khach_mysql_demo (
    id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    ma_yeu_cau VARCHAR(40) NOT NULL UNIQUE,
    ten VARCHAR(100) NOT NULL,
    trang_thai VARCHAR(20) NOT NULL DEFAULT 'MOI',
    tao_luc DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6)
);
~~~

### 14.2. Chèn một hàng và lấy ID

~~~sql
INSERT INTO khach_mysql_demo (ma_yeu_cau, ten)
VALUES ('REQ-MY-001', 'An');

SELECT LAST_INSERT_ID() AS id_moi;
~~~

`LAST_INSERT_ID()` trả giá trị `AUTO_INCREMENT` đầu tiên được sinh thành công bởi thao tác chèn gần nhất có phát sinh giá trị như vậy **trên chính kết nối đó**, theo quy tắc MySQL.

**Điều kiện cực kỳ quan trọng:** phải đọc giá trị trên **cùng connection** đã thực hiện `INSERT`. Khi dùng connection pool, không được trả connection về pool rồi mượn một connection bất kỳ để chạy `SELECT LAST_INSERT_ID()`.

### 14.3. Lấy thêm DEFAULT bằng SELECT theo ID

Nếu chỉ có `LAST_INSERT_ID()`, ứng dụng đã biết ID, nhưng có thể cần trạng thái và thời điểm mặc định:

~~~sql
INSERT INTO khach_mysql_demo (ma_yeu_cau, ten)
VALUES ('REQ-MY-002', 'Bình');

SELECT
    id,
    ma_yeu_cau,
    trang_thai,
    tao_luc
FROM khach_mysql_demo
WHERE id = LAST_INSERT_ID();
~~~

Ở đây, việc `SELECT` thêm một lần có thể cần thiết vì **`LAST_INSERT_ID()` chỉ trả khóa tự sinh**, không phải một result set đầy đủ giống `RETURNING id, trang_thai, tao_luc`.

Trong ứng dụng có giao dịch gồm nhiều lệnh, nên lưu ID vừa nhận vào biến ứng dụng sớm và dùng chính ID đó để đọc hoặc ghi bảng con. Không dựa vào `LAST_INSERT_ID()` sau các thao tác chèn khác trên cùng connection nếu chúng có thể làm thay đổi giá trị theo ngữ nghĩa MySQL.

### 14.4. LAST_INSERT_ID khác MAX(id)

`LAST_INSERT_ID()` là giá trị theo **connection**: một connection khác tạo ID mới không tự làm giá trị của connection hiện tại thay đổi.

Ngược lại:

~~~sql
-- Không dùng để xác định hàng của chính request:
-- SELECT MAX(id) FROM khach_mysql_demo;
~~~

`MAX(id)` đọc giá trị lớn nhất hiện có trong bảng theo mức cô lập giao dịch và trạng thái quan sát được. Trong hệ thống nhiều kết nối, đó **không bảo đảm** là ID của request vừa chèn.

### 14.5. Chèn nhiều hàng không trả toàn bộ ID qua LAST_INSERT_ID

~~~sql
INSERT INTO khach_mysql_demo (ma_yeu_cau, ten)
VALUES
    ('REQ-MY-B1', 'Chi'),
    ('REQ-MY-B2', 'Dung'),
    ('REQ-MY-B3', 'Em');

SELECT LAST_INSERT_ID() AS id_dau_tien;
~~~

Với thao tác chèn nhiều hàng, `LAST_INSERT_ID()` cho biết **giá trị tự sinh đầu tiên**, **không trả một danh sách ba ID**.

Không được tự suy rằng ba ID chắc chắn là `id_dau_tien`, `id_dau_tien+1`, `id_dau_tien+2` ở mọi môi trường. Các quy tắc cấp ID, xung đột, trigger, cơ chế chèn và đồng thời có thể làm giả định đó sai.

Muốn ánh xạ từng input, có thể dùng **khóa yêu cầu duy nhất đã lưu** rồi truy vấn lại hoặc dùng khả năng **generated keys** của driver nếu được triển khai, nhưng phải xác nhận driver thực sự trả được **danh sách đầy đủ** và cách ánh xạ.

### 14.6. INSERT thất bại và LAST_INSERT_ID

Nếu thao tác `INSERT` gặp lỗi, không được tiếp tục dùng `LAST_INSERT_ID()` như thể nó là ID của bản ghi mới: giá trị đó có thể không đại diện cho một lần chèn thành công, hoặc phụ thuộc trạng thái trước.

Sau một `ROLLBACK` thủ công, giá trị `LAST_INSERT_ID()` trên connection cũng **không nhất thiết quay trở lại giá trị trước transaction**. Một ID được sinh ra rồi rollback không chứng minh bản ghi còn tồn tại.

**Kết luận ở MySQL:** kiểm tra kết quả DML, dùng đúng connection, lấy khóa ngay và xác nhận transaction thành công.

## 15. MariaDB: INSERT ... RETURNING

**MariaDB không phải tên gọi khác của MySQL** về mọi cú pháp DML. MariaDB hỗ trợ `INSERT ... RETURNING` từ **MariaDB 10.5.0**.

Ví dụ trên MariaDB:

~~~sql
CREATE TABLE khach_mariadb_demo (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    ma_yeu_cau VARCHAR(40) NOT NULL UNIQUE,
    ten VARCHAR(100) NOT NULL,
    trang_thai VARCHAR(20) NOT NULL DEFAULT 'MOI'
);

INSERT INTO khach_mariadb_demo (ma_yeu_cau, ten)
VALUES ('REQ-MARIA-001', 'An')
RETURNING id, ma_yeu_cau, trang_thai;
~~~

Ở phiên bản hỗ trợ, câu lệnh trả các giá trị của hàng đã được chèn, gồm ID `AUTO_INCREMENT` và default.

### 15.1. Multirow INSERT

~~~sql
INSERT INTO khach_mariadb_demo (ma_yeu_cau, ten)
VALUES
    ('REQ-MARIA-B1', 'Bình'),
    ('REQ-MARIA-B2', 'Chi')
RETURNING id, ma_yeu_cau, ten;
~~~

Cũng cần ánh xạ đầu ra dựa trên **khóa nghiệp vụ**, không chỉ theo thứ tự hàng trả.

**Quan trọng:** cú pháp `RETURNING` của các thao tác `UPDATE`, `DELETE` và tính năng mở rộng khác có phạm vi hỗ trợ **không đồng nhất giữa các phiên bản MariaDB**. Khi mục tiêu là di chuyển ứng dụng, phải kiểm tra riêng phiên bản/câu lệnh được dùng, không suy từ khả năng `INSERT ... RETURNING` rằng tất cả DML đều có cùng cú pháp.

## 16. SQLite: RETURNING từ phiên bản 3.35

SQLite bổ sung `RETURNING` ở phiên bản **3.35.0 (tháng 3/2021)**. Cú pháp lấy dữ liệu sau `INSERT` gần với PostgreSQL:

~~~sql
CREATE TABLE khach_sqlite_demo (
    id INTEGER PRIMARY KEY,
    ma_yeu_cau TEXT NOT NULL UNIQUE,
    ten TEXT NOT NULL,
    trang_thai TEXT NOT NULL DEFAULT 'MOI',
    tao_luc TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

INSERT INTO khach_sqlite_demo (ma_yeu_cau, ten)
VALUES ('REQ-SQLITE-001', 'An')
RETURNING id, ma_yeu_cau, trang_thai, tao_luc;
~~~

SQLite có thể trả một hoặc nhiều hàng đầu ra của thao tác ghi tương ứng.

### 16.1. Những khác biệt quan trọng so với PostgreSQL

- SQLite không cho phép dùng một DML `RETURNING` như **subquery/CTE tạo bảng** để tiếp tục `SELECT` hoặc `INSERT` bảng khác theo cách PostgreSQL hỗ trợ.
- Thứ tự các hàng đầu ra của `RETURNING` **không được bảo đảm**.
- Giá trị `RETURNING` không bao gồm **những thay đổi được thực hiện sau đó bởi `AFTER` trigger** trên chính hàng.
- Có các hạn chế về `RETURNING` trong trigger, virtual table và các dạng biểu thức; phải kiểm tra tài liệu theo phiên bản SQLite.

Vì vậy, code dùng PostgreSQL:

~~~sql
-- Không chép nguyên sang SQLite:
-- WITH tao_khach AS (
--     INSERT INTO khach (...) VALUES (...)
--     RETURNING id
-- )
-- INSERT INTO don (...) SELECT id FROM tao_khach;
~~~

không phải một mẫu chuyển đổi tự động. Trong SQLite, có thể thực hiện các thao tác liên tiếp trên **cùng connection và transaction** bằng API của ứng dụng.

### 16.2. last_insert_rowid không đồng nghĩa RETURNING

SQLite còn có API/câu SQL lấy ID của lần chèn gần nhất trên một connection, nhưng nó **không trả nhiều cột của hàng vừa chèn** như `RETURNING`. Với SQLite từ 3.35, `RETURNING` thường là cách trực tiếp hơn khi cần các cột default; cần xét đặc tính bảng, trigger và cách driver tiêu thụ result set.

## 17. Bảng đối chiếu các phương ngữ

| Hệ quản trị | Cơ chế INSERT trả kết quả | Đối tượng thường lấy | Chú ý đặc thù |
| --- | --- | --- | --- |
| **PostgreSQL** | `INSERT ... RETURNING id, ...` | Một result set với các hàng được chèn | Kết hợp `ON CONFLICT`; hỗ trợ DML CTE theo quy tắc riêng |
| **SQL Server** | `INSERT ... OUTPUT INSERTED.Id, ... VALUES ...` | Result set hoặc `OUTPUT INTO` | Vị trí OUTPUT trước VALUES; trigger và thứ tự đầu ra |
| **Oracle** | `INSERT ... RETURNING id INTO :out_id` | Biến PL/SQL/OUT bind | Cơ chế `INTO` khác result set; bulk có quy tắc riêng |
| **MySQL 8.4** | `INSERT` rồi `LAST_INSERT_ID()` hoặc API driver | ID `AUTO_INCREMENT` | Phải dùng cùng connection; multirow chỉ có giá trị đầu tiên qua hàm |
| **MariaDB 10.5+** | `INSERT ... RETURNING ...` | Result set hàng vừa chèn | Không đồng nhất cú pháp với MySQL |
| **SQLite 3.35+** | `INSERT ... RETURNING ...` | Result set hàng vừa chèn | Không dùng RETURNING như bảng trong data-modifying CTE PostgreSQL |

### 17.1. Cú pháp đối chiếu ngắn gọn

**PostgreSQL:**

~~~sql
INSERT INTO bang (ten)
VALUES ('An')
RETURNING id, trang_thai;
~~~

**SQL Server:**

~~~sql
INSERT INTO bang (ten)
OUTPUT INSERTED.id, INSERTED.trang_thai
VALUES (N'An');
~~~

**Oracle với OUT bind:**

~~~sql
INSERT INTO bang (ten)
VALUES (:ten)
RETURNING id, trang_thai INTO :id_moi, :trang_thai_moi;
~~~

**MySQL:**

~~~sql
INSERT INTO bang (ten) VALUES ('An');
SELECT LAST_INSERT_ID() AS id_moi;
~~~

**MariaDB / SQLite ở phiên bản hỗ trợ:**

~~~sql
INSERT INTO bang (ten)
VALUES ('An')
RETURNING id, trang_thai;
~~~

Các mẫu chỉ thể hiện **vị trí và ý nghĩa mệnh đề**, giả định bảng đã có cột tương ứng theo DBMS. Không chép tên bảng, kiểu chuỗi, cú pháp identity hoặc ký hiệu bind nguyên xi qua hệ khác.

## 18. Batch INSERT: cần kết quả theo từng input, không chỉ theo từng hàng được ghi

Chèn nhiều hàng là trường hợp dễ phát sinh lỗi **ánh xạ** nhất.

Giả sử API nhận:

| request_key | ten |
| --- | --- |
| `r-001` | An |
| `r-002` | Bình |
| `r-003` | Chi |

Ứng dụng mong nhận:

| request_key | generated_id | trạng thái |
| --- | --- | --- |
| `r-001` | ID tương ứng | Thành công/bị bỏ qua/lỗi |
| `r-002` | ID tương ứng | Thành công/bị bỏ qua/lỗi |
| `r-003` | ID tương ứng | Thành công/bị bỏ qua/lỗi |

Một `RETURNING id` chỉ cho biết **những ID được trả về**, chưa chắc đủ để biết mỗi ID ứng với input nào. Khi input có thể bị lọc hoặc xung đột, phải lưu/giữ **khóa tương quan**.

### 18.1. Lưu request_key cùng dữ liệu đích

Trong PostgreSQL:

~~~sql
INSERT INTO khach_hang_ret (ma_yeu_cau, ten)
VALUES
    ('r-001', 'An'),
    ('r-002', 'Bình'),
    ('r-003', 'Chi')
ON CONFLICT (ma_yeu_cau) DO NOTHING
RETURNING ma_yeu_cau, id;
~~~

Nếu `r-002` đã tồn tại, câu này có thể chỉ trả hai hàng `r-001` và `r-003` (trong điều kiện các hàng đó được chèn). Ứng dụng dùng `ma_yeu_cau` để biết **input nào vừa tạo bản ghi**, sau đó xử lý input bị bỏ qua theo chính sách.

### 18.2. Thứ tự tự sinh không phải khóa tương quan

Không dùng công thức:

~~~text
generated_id[i] = first_generated_id + i
~~~

như một quy tắc chung. Kể cả khi các ID của một ví dụ đơn giản trông tăng đều, điều đó không tạo hợp đồng cho batch insert dưới các quy tắc cấp số, xung đột và đồng thời.

### 18.3. Lấy thêm các cột là kết quả ghi thực tế

Nếu cần trả cả thời điểm và trạng thái, chọn chúng trong `RETURNING`/`OUTPUT`, hoặc đọc lại bằng khóa cụ thể khi DBMS không có tính năng tương đương:

~~~sql
-- PostgreSQL
RETURNING ma_yeu_cau, id, trang_thai, tao_luc;
~~~

Với MySQL, có thể dùng một câu `SELECT` theo danh sách **`ma_yeu_cau` duy nhất** sau khi INSERT, nhưng phải bảo đảm lệnh ghi thành công, trạng thái giao dịch và quy tắc xử lý bản ghi cũ/trùng. Đó là một chiến lược khác về số round-trip và khả năng nhìn thấy dữ liệu so với RETURNING trực tiếp.

## 19. Đồng thời, transaction và tính nguyên tử

Một mệnh đề trả dữ liệu của DML giúp giảm thao tác phụ, nhưng **không giải quyết mọi vấn đề concurrency và transaction**.

### 19.1. Dữ liệu trả về chưa đồng nghĩa COMMIT

Trong PostgreSQL:

~~~sql
BEGIN;

INSERT INTO khach_hang_ret (ma_yeu_cau, ten)
VALUES ('REQ-ROLLBACK-001', 'Khách Thử')
RETURNING id, ma_yeu_cau;

ROLLBACK;
~~~

Câu `INSERT` có thể trả một ID khi thực thi trong giao dịch, nhưng **`ROLLBACK` hủy hàng vừa ghi**. ID có thể vẫn bị tiêu thụ trong sequence; việc nhìn thấy ID trả về không chứng minh bản ghi còn tồn tại sau rollback.

Không gửi một thông báo “đã hoàn tất thanh toán” hoặc phát một sự kiện không thể thu hồi ra hệ thống khác **chỉ vì đã nhận ID trước COMMIT**. Với tích hợp nhiều hệ, cân nhắc **transactional outbox** hoặc cơ chế phát sự kiện có thể kiểm soát tính nhất quán.

### 19.2. Cùng connection trong các cơ chế lấy ID theo phiên

Với MySQL `LAST_INSERT_ID()` và các API “last inserted ID” theo connection, phải giữ đúng **session/connection**. PostgreSQL `RETURNING` và SQL Server `OUTPUT` trả dữ liệu trong kết quả của chính câu lệnh, giúp giảm phụ thuộc vào một truy vấn lấy ID riêng; nhưng ứng dụng vẫn cần quản lý transaction cho các bước sau.

### 19.3. Tránh đoán hàng bằng ORDER BY id DESC LIMIT 1

~~~sql
-- Sai ý định nếu dùng để tìm hàng vừa được chính mình chèn:
-- SELECT id FROM khach_hang_ret ORDER BY id DESC LIMIT 1;
~~~

Trong môi trường nhiều session, một connection khác có thể chèn bản ghi trước khi truy vấn trên chạy; ngay cả khi không có concurrency, ID cao nhất chưa chắc là “hàng thuộc request hiện tại”.

Hãy dùng:

- Result set **`RETURNING`** của chính câu INSERT;
- **`OUTPUT INSERTED`** trong SQL Server;
- **`RETURNING INTO`**/OUT bind trong Oracle;
- **`LAST_INSERT_ID()` trên cùng connection** nếu đúng loại insert MySQL;
- Khóa **duy nhất, có chủ đích** để đọc lại khi cần.

### 19.4. Xử lý câu INSERT thất bại

Nếu câu INSERT vi phạm `UNIQUE`, `NOT NULL`, `CHECK`, khóa ngoại hoặc bị hủy vì lỗi, ứng dụng không được coi ID/rowcount cũ là kết quả thành công của lệnh mới.

Với PostgreSQL, một lỗi SQL trong transaction thường đưa transaction vào trạng thái cần rollback hoặc rollback tới savepoint trước khi tiếp tục. Với các DBMS khác, hành vi phụ thuộc loại lỗi, transaction và driver.

Mẫu thực hành đúng:

~~~text
Bắt đầu transaction nếu nghiệp vụ gồm nhiều lệnh
Thực thi INSERT có cơ chế lấy ID
Kiểm tra lỗi và số hàng/output hợp lệ
Thực hiện các lệnh phụ thuộc trên cùng transaction
COMMIT thành công
Chỉ khi đó xác nhận thành công ra bên ngoài
~~~

## 20. Trigger, computed column và “giá trị cuối cùng”

Một điểm khó là **giá trị trả về xuất hiện ở thời điểm nào so với trigger**.

| Trường hợp | Lưu ý |
| --- | --- |
| PostgreSQL `RETURNING` | Thường phản ánh hàng sau các chỉnh sửa do **BEFORE row trigger** liên quan thực hiện; không tự bảo đảm gồm mọi thay đổi phát sinh về sau từ những thao tác trigger riêng |
| SQL Server `OUTPUT INSERTED` | Theo tài liệu phản ánh giá trị sau DML nhưng **trước trigger**; có hạn chế OUTPUT trực tiếp khi target có trigger đang bật |
| SQLite `RETURNING` | Không phản ánh thay đổi **sau đó** do `AFTER` trigger cập nhật hàng |
| Oracle `RETURNING INTO` | Cần xét loại trigger, thời điểm thực thi và phiên bản/định nghĩa của DML; không suy đồng nhất với SQL Server |
| MySQL `LAST_INSERT_ID()` | Chỉ là cơ chế nhận ID, không cung cấp ảnh chụp tất cả cột sau trigger |

Ví dụ nghiệp vụ: bảng có default `trang_thai='MOI'`, nhưng một trigger có thể chuẩn hóa dữ liệu hoặc thay đổi một số cột. Trước khi xây dựng API trả “trạng thái cuối cùng”, cần phân biệt:

1. Giá trị do chính câu INSERT ghi;
2. Giá trị được trigger **BEFORE** điều chỉnh trước khi ghi;
3. Những thay đổi phụ thêm do trigger **AFTER** hoặc một quy trình khác thực hiện;
4. Trạng thái đã `COMMIT` cuối cùng, có thể còn phụ thuộc các lệnh sau.

Nếu hợp đồng API yêu cầu **giá trị cuối cùng đã ổn định sau toàn bộ quy trình**, một câu `RETURNING` đơn lẻ không phải lúc nào cũng đủ. Có thể cần truy vấn lại theo khóa ở thời điểm thích hợp và bảo đảm transaction/điều kiện đồng thời phù hợp.

### 20.1. DEFAULT và generated/computed column

Khi một cột được database tính, `RETURNING` hoặc `OUTPUT` thường là cách thuận tiện để xem giá trị tính được tại thời điểm thao tác:

~~~sql
-- PostgreSQL: ví dụ độc lập với cột generated stored.
CREATE TEMP TABLE chi_tiet_tinh_tien_ret (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    so_luong INTEGER NOT NULL CHECK (so_luong > 0),
    don_gia NUMERIC(12,2) NOT NULL CHECK (don_gia >= 0),
    thanh_tien NUMERIC(14,2)
        GENERATED ALWAYS AS (so_luong * don_gia) STORED
);

INSERT INTO chi_tiet_tinh_tien_ret (so_luong, don_gia)
VALUES (3, 125000)
RETURNING id, so_luong, don_gia, thanh_tien;
~~~

`thanh_tien` trả **375000.00** theo biểu thức định nghĩa. Ứng dụng không phải tự tính lại công thức tại nơi lấy ID. Trong một schema thật, cần quan tâm làm tròn, kiểu số, thuế, chiết khấu và các quy tắc tiền tệ riêng.

## 21. JDBC và driver: API ứng dụng nhận giá trị như thế nào?

Không chỉ SQL khác nhau; **cách driver trả kết quả** cũng có thể khác. Cần kiểm tra hỗ trợ theo phiên bản database và driver.

### 21.1. JDBC với PostgreSQL RETURNING

Ví dụ Java sử dụng `PreparedStatement` để trả một ID và trạng thái, các dấu `?` là **tham số bind**:

~~~java
String sql = """
    INSERT INTO khach_hang_ret (ma_yeu_cau, ten)
    VALUES (?, ?)
    RETURNING id, trang_thai
    """;

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setString(1, "REQ-JDBC-PG-001");
    ps.setString(2, "Khách Java");

    try (ResultSet rs = ps.executeQuery()) {
        if (!rs.next()) {
            throw new SQLException("Không có hàng RETURNING");
        }

        long id = rs.getLong("id");
        String trangThai = rs.getString("trang_thai");
        // Sử dụng id và trangThai trong transaction hiện tại.
    }
}
~~~

`executeQuery()` phù hợp khi câu SQL thực sự trả **`ResultSet`**. Không nên mặc định mọi driver cho phép dùng `executeUpdate()` rồi vẫn đọc được các hàng `RETURNING`; lựa chọn phương thức phải phù hợp driver/câu SQL.

### 21.2. JDBC với generated keys

Một hướng khác là yêu cầu driver trả **generated keys**:

~~~java
String sql = """
    INSERT INTO khach_mysql_demo (ma_yeu_cau, ten)
    VALUES (?, ?)
    """;

try (PreparedStatement ps = connection.prepareStatement(
        sql, Statement.RETURN_GENERATED_KEYS)) {
    ps.setString(1, "REQ-JDBC-MY-001");
    ps.setString(2, "Khách Java");

    int affectedRows = ps.executeUpdate();
    if (affectedRows != 1) {
        throw new SQLException("Không chèn đúng một hàng");
    }

    try (ResultSet keys = ps.getGeneratedKeys()) {
        if (!keys.next()) {
            throw new SQLException("Driver không trả generated key");
        }
        long id = keys.getLong(1);
        // Dùng ID được trả về bởi driver.
    }
}
~~~

Ví dụ này chỉ minh họa **JDBC trên bảng MySQL** đã tạo ở mục 14.1 và giả định phiên bản driver có hỗ trợ phù hợp. Không coi `getGeneratedKeys()` là cách chuẩn trả **mọi cột default** của hàng sau INSERT. Hành vi với batch, nhiều khóa và tên cột trả về có thể khác theo driver.

### 21.3. Chèn hàng loạt bằng JDBC

Khi dùng `addBatch()`/`executeBatch()`, nhiều driver có cơ chế trả generated keys, nhưng **không được suy từ API chung rằng luôn có đúng một ID theo đúng thứ tự input**.

Cần kiểm tra:

- Driver có trả generated keys khi batch không?
- Bảng có trigger/UPSERT khiến số hàng bị tác động khác input không?
- Các lỗi trong batch có được xử lý toàn bộ hay một phần?
- Có mã tương quan để gắn ID với từng input không?
- Transaction có được rollback khi một phần batch lỗi không?

Nếu cần hợp đồng “mỗi input nhận chính xác kết quả riêng”, có thể cần đổi chiến lược: dùng khóa tương quan, đưa dữ liệu vào staging table hoặc chia batch có kiểm soát và báo cáo trạng thái từng hàng.

### 21.4. Luôn bind tham số, không nối chuỗi SQL từ input

Không tạo câu `INSERT` bằng phép cộng chuỗi với tên khách, email hoặc mã yêu cầu chưa được kiểm soát. `RETURNING`/`OUTPUT` **không làm SQL injection biến mất**; hãy dùng prepared statement, bind variables hoặc API tương đương cho từng DBMS.

## 22. Tối ưu hiệu năng và chi phí trả dữ liệu

### 22.1. Lợi ích và giới hạn của một round-trip

Một lệnh:

~~~sql
INSERT INTO khach_hang_ret (ma_yeu_cau, ten)
VALUES ('REQ-SPEED-001', 'Khách Nhanh')
RETURNING id, trang_thai;
~~~

có thể trả hai cột cần thiết trong **cùng câu lệnh chèn**, giảm nhu cầu gửi một câu truy vấn khác chỉ để lấy ID/trạng thái.

Tuy nhiên, không có quy tắc “có RETURNING là luôn nhanh hơn mọi cách khác”:

- Trả nhiều hàng hoặc BLOB/JSON lớn làm tăng dữ liệu truyền qua mạng.
- Dùng `RETURNING *` có thể tốn tài nguyên hơn trả ID và hai cột cần thiết.
- Trigger, index, kiểm tra ràng buộc và xử lý xung đột vẫn có chi phí.
- ORM có thể thực thi các lệnh khác để đồng bộ entity, lazy loading hoặc cascade.
- Hành vi của database và driver khác nhau theo phương ngữ/phiên bản.

### 22.2. Không thay SELECT bằng RETURNING một cách mù quáng

Nếu yêu cầu là **đọc tất cả đơn hàng của một khách**, `RETURNING` không phù hợp vì nó chỉ gắn với các hàng đang bị thao tác DML. Dùng `SELECT` cho nhu cầu đọc; dùng `RETURNING`/`OUTPUT` để nhận thông tin của thao tác ghi.

Nếu cần báo cáo trước/sau của một tập dữ liệu không bị thay đổi, hãy viết truy vấn đọc thay vì cố cập nhật rồi hoàn nguyên chỉ để có output.

### 22.3. EXPLAIN và khả năng đo

Ở PostgreSQL, có thể dùng kế hoạch thực thi cho `INSERT ... RETURNING` theo cú pháp phù hợp. Nhưng `EXPLAIN ANALYZE` **thực sự thực thi câu lệnh**; nếu có thao tác ghi, nên chạy trong transaction có `ROLLBACK` ở môi trường kiểm soát và vẫn chú ý sequence/side effect ngoài giao dịch.

Ví dụ định hướng:

~~~sql
BEGIN;

EXPLAIN (ANALYZE, BUFFERS)
INSERT INTO khach_hang_ret (ma_yeu_cau, ten)
VALUES ('REQ-EXPLAIN-001', 'Khách Đo')
RETURNING id, trang_thai;

ROLLBACK;
~~~

Không xem `ROLLBACK` là cơ chế “không có tác dụng phụ gì”: sequence, các hệ thống bên ngoài hoặc hành vi khác có thể không được hoàn nguyên như dữ liệu hàng thông thường. Hãy hạn chế thử nghiệm trên môi trường sản xuất.

## 23. Quyền truy cập và dữ liệu nhạy cảm

Việc có quyền `INSERT` **không mặc nhiên đồng nghĩa** caller được đọc mọi cột của bảng bằng `RETURNING *`.

Ví dụ PostgreSQL có thể cần **quyền `SELECT` đối với các cột được sử dụng trong `RETURNING`**, ngoài quyền thao tác ghi. Thiết kế quyền trên từng bảng/cột phải phù hợp tài khoản ứng dụng.

Mẫu trả ít cột:

~~~sql
INSERT INTO khach_hang_ret (ma_yeu_cau, ten, email)
VALUES ('REQ-PUBLIC-001', 'Khách Công Khai', 'public@example.test')
RETURNING id, ma_yeu_cau, trang_thai;
~~~

Không cần trả `email` chỉ vì bảng có cột email, nếu API chỉ cần ID và trạng thái.

Với hệ thống nhiều tổ chức, điều kiện định danh và phân quyền có thể yêu cầu khóa như `(to_chuc_id, ma_yeu_cau)`; một ID tự sinh **không phải chứng cứ người gọi có quyền truy cập** hàng đó. Vấn đề bảo mật phải được giải quyết bằng kiểm soát quyền truy cập, xác thực, ràng buộc phạm vi và chính sách dữ liệu riêng.

## 24. Các lỗi thường gặp khi lấy dữ liệu sau INSERT

| Lỗi | Hậu quả | Cách làm phù hợp |
| --- | --- | --- |
| Dùng `RETURNING` của PostgreSQL trên MySQL | Sai cú pháp ở MySQL thông thường | Dùng `LAST_INSERT_ID()`/generated keys hoặc cơ chế MySQL tương ứng |
| Đặt `OUTPUT` sau `VALUES` trong SQL Server | Sai vị trí cú pháp T-SQL | Viết `INSERT ... OUTPUT INSERTED... VALUES ...` |
| Dùng `RETURNING id` mà quên `INTO` ở Oracle | Không phù hợp cách nhận giá trị Oracle trong ngữ cảnh tương ứng | Dùng `RETURNING id INTO :id_moi` và OUT bind |
| Coi MariaDB và MySQL hỗ trợ INSERT RETURNING như nhau | Ứng dụng không chạy khi đổi server | Kiểm tra chính xác DBMS/phiên bản |
| Chỉ đọc số hàng ảnh hưởng rồi đoán ID | ID không được trả về | Dùng RETURNING/OUTPUT/generated keys |
| `SELECT MAX(id)` sau INSERT | Có thể lấy ID của hàng khác | Lấy ID từ cơ chế gắn với câu lệnh/connection |
| Chạy `LAST_INSERT_ID()` trên connection khác | Có thể nhận giá trị không liên quan | Giữ nguyên connection và transaction cần thiết |
| Cho rằng `LAST_INSERT_ID()` trả mọi ID của batch | Chỉ trả giá trị đầu tiên theo ngữ nghĩa MySQL | Dùng khóa đối chiếu/driver hỗ trợ đầy đủ |
| Ghép kết quả batch theo thứ tự output | Có thể gán nhầm ID cho input | Trả khóa tương quan duy nhất cùng ID |
| Dùng `DO NOTHING RETURNING` và luôn kỳ vọng một hàng | Xung đột bị bỏ qua trả 0 hàng | Xử lý nhánh không có hàng rõ ràng |
| Dùng `DO UPDATE` chỉ để lấy ID cũ | Có thể gây cập nhật, audit, trigger | Thiết kế idempotency và truy vấn lại theo unique key |
| Trả `RETURNING *` qua API | Lộ dữ liệu hoặc tăng tải | Chọn cột cần thiết, kiểm soát quyền |
| Xem ID trả về là COMMIT thành công | Rollback có thể xóa hàng dù ID đã sinh | Kiểm tra transaction commit |
| Không kiểm tra lỗi sau OUTPUT SQL Server | Có thể dùng output của câu DML bị rollback | Chỉ tin output khi toàn lệnh và transaction thành công |
| Coi RETURNING là ảnh chụp sau mọi AFTER trigger | Trả thông tin chưa phản ánh cập nhật phát sinh sau | Xác định thời điểm trigger và đọc lại khi cần |
| Dùng `NULL` thay vì bỏ cột có `DEFAULT` | Có thể lưu NULL hoặc vi phạm NOT NULL | Phân biệt omitted, DEFAULT và NULL |
| Cho rằng DML RETURNING là CTE ở mọi DBMS | SQLite/Oracle/MySQL không có cùng khả năng | Chọn chiến lược transaction và API theo hệ |
| Nhầm `RETURNING id` với `RETURNING *` | Thiếu các cột default mà API cần | Chọn rõ danh sách cột đầu ra |

## 25. Bài tập thực hành có lời giải

Các bài PostgreSQL sử dụng hai bảng tạm `khach_hang_ret`, `don_hang_ret` đã tạo ở mục 2, trừ khi ghi rõ phương ngữ khác. Có thể dùng **mã yêu cầu mới** khi chạy lại để tránh lỗi khóa duy nhất. Giá trị ID/timestamp trong kết quả là do database quyết định.

### Bài 1. Thêm khách và lấy ID

**Yêu cầu:** thêm khách tên “Phương” với mã `BT-KH-01`, nhận ID mới và trạng thái mặc định.

**Lời giải:**

~~~sql
INSERT INTO khach_hang_ret (ma_yeu_cau, ten)
VALUES ('BT-KH-01', 'Phương')
RETURNING id, ma_yeu_cau, trang_thai;
~~~

Nếu chèn thành công, có **một hàng kết quả**, `trang_thai = 'MOI'`; ID phụ thuộc trạng thái sequence.

### Bài 2. Lấy thời điểm tạo từ database

**Yêu cầu:** không truyền thời gian từ ứng dụng; trả thời gian database gán.

**Lời giải:**

~~~sql
INSERT INTO khach_hang_ret (ma_yeu_cau, ten)
VALUES ('BT-KH-02', 'Quang')
RETURNING id, tao_luc;
~~~

`tao_luc` lấy từ `DEFAULT CURRENT_TIMESTAMP`. Không tự thay bằng thời gian đọc ở phía ứng dụng nếu yêu cầu là giá trị database đã lưu.

### Bài 3. RETURNING * có thay đổi bảng không?

**Câu hỏi:** `RETURNING upper(ten) AS ten_hoa` có làm cột `ten` trong bảng được chuyển sang chữ hoa không?

**Lời giải:** **Không.** Đó là **biểu thức của đầu ra**. Muốn sửa dữ liệu cột `ten`, phải thiết kế giá trị được chèn, một `UPDATE` hoặc cơ chế chuẩn hóa hợp lệ khác.

### Bài 4. DEFAULT khác NULL

**Câu hỏi:** tại sao câu này bị từ chối?

~~~sql
-- INSERT INTO khach_hang_ret
--     (ma_yeu_cau, ten, trang_thai)
-- VALUES ('BT-KH-04', 'Sơn', NULL);
~~~

**Lời giải:** `trang_thai` có `NOT NULL`; việc truyền `NULL` tường minh không làm `DEFAULT 'MOI'` được áp dụng. Hãy **bỏ cột** hoặc dùng `DEFAULT` nếu muốn giá trị mặc định.

### Bài 5. Chèn ba khách và ánh xạ đúng

**Yêu cầu:** chèn ba khách, trả ID và mã yêu cầu để ứng dụng đối chiếu.

**Lời giải:**

~~~sql
INSERT INTO khach_hang_ret (ma_yeu_cau, ten)
VALUES
    ('BT-B1', 'An'),
    ('BT-B2', 'Bình'),
    ('BT-B3', 'Chi')
RETURNING ma_yeu_cau, id, trang_thai;
~~~

Dùng `ma_yeu_cau` để ánh xạ kết quả. Không dựa vào thứ tự ba hàng output hoặc giả định ID liên tiếp.

### Bài 6. ON CONFLICT DO NOTHING

**Yêu cầu:** thử chèn lại `BT-B1`, nếu đã tồn tại thì không đổi hàng cũ; nhận ID **chỉ nếu thực sự chèn**.

**Lời giải:**

~~~sql
INSERT INTO khach_hang_ret (ma_yeu_cau, ten)
VALUES ('BT-B1', 'An')
ON CONFLICT (ma_yeu_cau) DO NOTHING
RETURNING id, ma_yeu_cau;
~~~

Nếu `BT-B1` đã tồn tại, **không có hàng RETURNING**. Điều này không có nghĩa hàng cũ không tồn tại.

### Bài 7. INSERT ... SELECT ... RETURNING

**Yêu cầu:** dùng CTE nguồn để chèn hai khách và nhận ID thực tế.

**Lời giải:**

~~~sql
WITH nguon (ma_yeu_cau, ten) AS (
    VALUES
        ('BT-SRC-01', 'Trang'),
        ('BT-SRC-02', 'Vân')
)
INSERT INTO khach_hang_ret (ma_yeu_cau, ten)
SELECT ma_yeu_cau, ten
FROM nguon
RETURNING id, ma_yeu_cau;
~~~

Hai hàng được trả nếu cả hai được chèn thành công. `ma_yeu_cau` từ bảng đích giúp đối chiếu từng hàng.

### Bài 8. Chèn cha rồi chèn con

**Yêu cầu:** trong PostgreSQL, thêm một khách rồi tạo một đơn tham chiếu đến ID mới bằng một câu SQL sử dụng data-modifying CTE.

**Lời giải:**

~~~sql
WITH khach_moi AS (
    INSERT INTO khach_hang_ret (ma_yeu_cau, ten)
    VALUES ('BT-CHA-01', 'Khách Cha')
    RETURNING id
)
INSERT INTO don_hang_ret
    (khach_hang_id, ma_don, gia_tri)
SELECT
    id, 'BT-DON-01', 150000
FROM khach_moi
RETURNING id AS don_hang_id, khach_hang_id, ma_don;
~~~

Chỉ ID khách được database sinh cho câu INSERT đầu mới được đưa vào `khach_hang_id` của đơn. Không cần `MAX(id)` hoặc dự đoán số tiếp theo.

### Bài 9. SQL Server OUTPUT

**Yêu cầu:** viết INSERT SQL Server để nhận ID và thời điểm sau ghi.

**Lời giải T-SQL:**

~~~sql
INSERT INTO dbo.KhachHangOutputDemo (MaYeuCau, Ten)
OUTPUT INSERTED.Id, INSERTED.TaoLuc
VALUES (N'BT-SQL-01', N'Hương');
~~~

`OUTPUT` đứng trước `VALUES`. Đây là cú pháp SQL Server, không dùng trực tiếp trên PostgreSQL.

### Bài 10. SQL Server OUTPUT INTO khi có trigger

**Yêu cầu:** lưu ID mới của hàng vào một biến bảng rồi đọc lại.

**Lời giải:**

~~~sql
DECLARE @IdMoi TABLE (Id BIGINT);

INSERT INTO dbo.KhachHangOutputDemo (MaYeuCau, Ten)
OUTPUT INSERTED.Id INTO @IdMoi (Id)
VALUES (N'BT-SQL-02', N'Khánh');

SELECT Id FROM @IdMoi;
~~~

Đây là mẫu `OUTPUT INTO`; khi target có trigger, vẫn phải kiểm tra những hạn chế của SQL Server và hiểu rằng output không tự bao gồm mọi cập nhật từ trigger sau đó.

### Bài 11. Oracle RETURNING INTO

**Yêu cầu:** viết Oracle PL/SQL chèn một khách và lấy ID vào biến.

**Lời giải:**

~~~sql
DECLARE
    v_id khach_hang_oracle_demo.id%TYPE;
BEGIN
    INSERT INTO khach_hang_oracle_demo (ma_yeu_cau, ten)
    VALUES ('BT-ORA-01', 'Linh')
    RETURNING id INTO v_id;

    DBMS_OUTPUT.PUT_LINE('ID=' || v_id);
END;
/
~~~

Với ứng dụng, có thể dùng biến bind `:id_moi` dạng OUT theo driver Oracle thay cho biến PL/SQL cục bộ.

### Bài 12. MySQL lấy AUTO_INCREMENT

**Yêu cầu:** chèn một khách và lấy ID sinh tự động trong MySQL.

**Lời giải:**

~~~sql
INSERT INTO khach_mysql_demo (ma_yeu_cau, ten)
VALUES ('BT-MY-01', 'Mai');

SELECT LAST_INSERT_ID() AS id_moi;
~~~

Hai câu phải chạy trên **cùng connection**. Không dùng `MAX(id)` thay cho `LAST_INSERT_ID()`.

### Bài 13. MySQL batch có thể lấy mọi ID bằng LAST_INSERT_ID không?

**Câu hỏi:** sau `INSERT ... VALUES (...), (...), (...)`, `SELECT LAST_INSERT_ID()` có trả ba hàng ID không?

**Lời giải:** **Không.** Nó trả **một giá trị**, thường là ID tự sinh **đầu tiên** của câu INSERT nhiều hàng theo quy tắc MySQL. Cần driver/generated keys hỗ trợ hoặc ánh xạ bằng khóa yêu cầu duy nhất nếu muốn biết ID từng input.

### Bài 14. SQLite RETURNING với nhiều hàng

**Yêu cầu:** chèn hai khách SQLite và nhận `id`, `ma_yeu_cau`.

**Lời giải:**

~~~sql
INSERT INTO khach_sqlite_demo (ma_yeu_cau, ten)
VALUES
    ('BT-SQLITE-01', 'Nam'),
    ('BT-SQLITE-02', 'Oanh')
RETURNING id, ma_yeu_cau;
~~~

Câu này cần SQLite 3.35+. Không dựa vào thứ tự hàng trả để ánh xạ; dùng `ma_yeu_cau`.

### Bài 15. MariaDB khác MySQL

**Câu hỏi:** tại sao `INSERT ... RETURNING` chạy trên MariaDB 10.5+ nhưng không nên coi là cú pháp tương đương trên MySQL 8.4?

**Lời giải:** MariaDB và MySQL **có lộ trình tính năng khác nhau**. MariaDB hỗ trợ `INSERT ... RETURNING`, còn MySQL 8.4 thường dùng `LAST_INSERT_ID()` hoặc cơ chế driver để nhận ID. Phải kiểm tra **DBMS và phiên bản thực tế**, không chỉ tên “SQL”.

### Bài 16. Transaction rollback

**Yêu cầu:** giải thích vì sao đã nhận `RETURNING id` nhưng ngay sau `ROLLBACK` không thể xem là đã lưu thành công.

**Lời giải:** `RETURNING` báo dữ liệu do thao tác DML sinh ra **trong lúc thực thi**, còn `ROLLBACK` có thể hủy hàng. Việc sequence vẫn có khoảng nhảy là bình thường. Chỉ xác nhận nghiệp vụ sau khi **giao dịch thành công** và đáp ứng mọi điều kiện cần thiết.

### Bài 17. Trigger chỉnh sửa sau INSERT

**Câu hỏi:** SQL Server `OUTPUT INSERTED.TrangThai` có mặc nhiên phản ánh mọi chỉnh sửa do AFTER trigger thực hiện sau đó không?

**Lời giải:** **Không.** Theo quy tắc SQL Server, OUTPUT phản ánh dữ liệu sau DML nhưng trước trigger. Nếu API cần giá trị cuối cùng sau những thao tác phụ của trigger, phải xác định lại quy trình đọc và thời điểm giao dịch phù hợp.

### Bài 18. Thiết kế endpoint tạo khách

**Yêu cầu:** một endpoint tạo khách cần trả `id`, `ma_yeu_cau`, `trang_thai`, `tao_luc`. Hãy đề xuất cơ chế cho từng DBMS và hai nguyên tắc an toàn.

**Gợi ý lời giải:**

| Hệ | Cơ chế |
| --- | --- |
| PostgreSQL | `INSERT ... RETURNING id, ma_yeu_cau, trang_thai, tao_luc` |
| SQL Server | `INSERT ... OUTPUT INSERTED.Id, INSERTED.MaYeuCau, INSERTED.TrangThai, INSERTED.TaoLuc VALUES ...` |
| Oracle | `RETURNING ... INTO` với OUT bind/PLSQL |
| MariaDB 10.5+ | `INSERT ... RETURNING ...` |
| SQLite 3.35+ | `INSERT ... RETURNING ...` |
| MySQL | INSERT + generated ID trên cùng connection, rồi SELECT các cột cần thiết theo ID hoặc unique key |

Hai nguyên tắc cần giữ: **(1)** bind input an toàn và dùng khóa tương quan duy nhất, **(2)** chỉ xác nhận tạo thành công khi lệnh và transaction đã thành công. Nếu bảng có trigger hoặc xử lý hậu ghi, cần xác định liệu dữ liệu trả về đã là trạng thái cuối theo hợp đồng API chưa.

## 26. Checklist thiết kế chức năng “tạo và trả bản ghi”

Trước khi đưa vào mã ứng dụng, hãy tự trả lời:

1. **Máy chủ thực sự là DBMS và phiên bản nào?** PostgreSQL, SQL Server, Oracle, MySQL, MariaDB và SQLite không dùng hoàn toàn cùng cú pháp.
2. **Cần trả gì?** Chỉ ID hay ID, thời gian, trạng thái, cột tính toán, mã yêu cầu?
3. **Ai sinh khóa?** Database identity/auto-increment, sequence, UUID database, UUID client hay khóa nghiệp vụ?
4. **Một hay nhiều hàng?** Nếu nhiều hàng, ánh xạ input–output bằng khóa nào và có nhánh xung đột không?
5. **Có `DEFAULT`, `NOT NULL`, `CHECK`, trigger không?** Giá trị trả về có phản ánh chính xác giai đoạn cần thiết của quy trình?
6. **Có giao dịch nhiều bước không?** Nếu sau INSERT còn tạo bảng con, đảm bảo toàn bộ transaction được xử lý đúng.
7. **Driver nhận kết quả thế nào?** `ResultSet`, generated keys, OUT bind hay table variable?
8. **Có quyền đọc các cột trả về không?** Không lạm dụng `RETURNING *` hoặc `OUTPUT INSERTED.*`.
9. **Nếu không có hàng được trả thì sao?** Xử lý rõ xung đột `DO NOTHING`, điều kiện update không thỏa, câu lệnh lỗi.
10. **Nếu phải đọc lại một lần nữa thì dùng khóa nào?** Không dùng `MAX(id)`; dùng ID đã nhận hoặc khóa nghiệp vụ unique theo đúng transaction/connection.

## 27. Tài liệu tham khảo chính thức

Các đặc tính cú pháp và hạn chế phụ thuộc phiên bản. Khi triển khai thực tế, nên đối chiếu tài liệu của hệ quản trị đang dùng:

- **PostgreSQL:** [INSERT và RETURNING](https://www.postgresql.org/docs/current/sql-insert.html), [Returning Data from Modified Rows](https://www.postgresql.org/docs/current/dml-returning.html).
- **SQL Server:** [OUTPUT clause (Transact-SQL)](https://learn.microsoft.com/en-us/sql/t-sql/queries/output-clause-transact-sql).
- **Oracle Database:** [RETURNING INTO Clause (PL/SQL)](https://docs.oracle.com/en/database/oracle/oracle-database/26/lnpls/RETURNING-INTO-clause.html) và [Bulk SQL and Bulk Binding](https://docs.oracle.com/en/database/oracle/oracle-database/26/lnpls/bulk-sql-and-bulk-binding.html).
- **MySQL:** [INSERT Statement — MySQL 8.4](https://dev.mysql.com/doc/refman/8.4/en/insert.html), [LAST_INSERT_ID — MySQL 8.4](https://dev.mysql.com/doc/refman/8.4/en/information-functions.html).
- **MariaDB:** [INSERT ... RETURNING](https://mariadb.com/docs/server/reference/sql-statements/data-manipulation/inserting-loading-data/insertreturning).
- **SQLite:** [RETURNING clause](https://www.sqlite.org/lang_returning.html).

## 28. Kết luận

`RETURNING`, `OUTPUT` và các cơ chế tương đương giải quyết cùng một nhu cầu: **sau khi thêm dữ liệu, ứng dụng biết chính xác database đã tạo ra những giá trị nào**. Chúng đặc biệt hữu ích với khóa tự sinh, giá trị `DEFAULT`, thời gian tạo, khóa ngoại cho bảng con và API tạo tài nguyên.

Những điểm cần ghi nhớ:

- **PostgreSQL:** `INSERT ... RETURNING id, ...` trả những hàng vừa chèn và hỗ trợ nhiều biểu thức/cột.
- **SQL Server:** `INSERT ... OUTPUT INSERTED.Id, ... VALUES ...`; dùng `OUTPUT ... INTO` khi cần lưu kết quả trung gian và xét các hạn chế về trigger.
- **Oracle:** `RETURNING ... INTO` đưa dữ liệu vào biến PL/SQL hoặc OUT bind; xử lý nhiều hàng có cơ chế bulk riêng.
- **MySQL:** `LAST_INSERT_ID()` là cơ chế theo connection cho khóa `AUTO_INCREMENT`; không tương đương result set đầy đủ của RETURNING, đặc biệt khi INSERT nhiều hàng.
- **MariaDB và SQLite:** có `INSERT ... RETURNING` ở phiên bản hỗ trợ nhưng không đồng nhất mọi khả năng nâng cao với PostgreSQL.
- **Batch:** cần khóa tương quan như `ma_yeu_cau` để ghép từng input với đúng output; không dựa vào thứ tự trả hàng hoặc ID tăng đều.
- **Transaction:** ID được trả về không chứng minh hàng đã `COMMIT`; luôn xử lý lỗi, rollback và điều kiện đồng thời.
- **Trigger và quyền:** đầu ra không nhất thiết là trạng thái cuối sau mọi thao tác phụ; chọn đúng cột và bảo vệ dữ liệu nhạy cảm.

**Nguyên tắc quan trọng nhất:** đừng hỏi database “ID lớn nhất bây giờ là bao nhiêu?” để đoán ID vừa tạo. Hãy dùng **cơ chế trả kết quả được gắn với chính câu INSERT** hoặc một phương án lấy generated key/đọc lại bằng khóa duy nhất đúng với **DBMS, phiên bản, connection và transaction** đang sử dụng.
