# Nạp dữ liệu qua bảng trung gian trước khi xác nhận

Nhập dữ liệu vào cơ sở dữ liệu không phải lúc nào cũng đơn giản như một câu **INSERT INTO ... VALUES (...)**. Trong ứng dụng thật, dữ liệu có thể đến từ tệp CSV, Excel, hệ thống đối tác, hàng đợi sự kiện hoặc một lần đồng bộ định kỳ. Dữ liệu đầu vào có thể sai kiểu, trùng khóa, thiếu mã danh mục, chứa khoảng trắng thừa hoặc chưa được người phụ trách phê duyệt. Nếu ghi thẳng vào bảng nghiệp vụ, một lần nhập lỗi có thể làm phát sinh bản ghi sai, thay đổi những sản phẩm đang hoạt động hoặc buộc người vận hành phải sửa thủ công.

**Nạp qua bảng trung gian** (*staging table*) là một mẫu truy vấn giúp tách **nhận dữ liệu** khỏi **xác nhận dữ liệu**:

1. Tiếp nhận các hàng nguồn vào một **bảng staging**.
2. Chuẩn hóa và **kiểm tra chất lượng** mà chưa thay đổi bảng nghiệp vụ.
3. Phân loại những hàng được chấp nhận, những hàng bị từ chối và lý do.
4. Cho hệ thống hoặc người có thẩm quyền **xem trước và duyệt** theo chính sách.
5. Chỉ sau khi được phép mới **INSERT/UPSERT vào bảng đích trong một transaction**.
6. Lưu dấu vết batch, kết quả và lỗi để phục vụ kiểm tra hoặc chạy lại có kiểm soát.

Bài học thuộc chương **Thêm dữ liệu** của module **Database SQL**. Ví dụ chính dùng **PostgreSQL 15+** với các bảng tạm độc lập, nên có thể thực hành mà không sửa dữ liệu nghiệp vụ thật. Phần sau mở rộng sang bảng staging lâu dài, tải CSV, chạy lại batch, cạnh tranh giữa nhiều tiến trình và sự khác biệt theo phương ngữ.

## 1. Kết quả cần đạt

Sau bài này, bạn có thể:

- Giải thích vai trò riêng của **bảng raw staging**, **bảng đã chuẩn hóa/kiểm tra**, **bảng đích** và **nhật ký import**.
- Thiết kế khóa **batch_id + row_no** để truy vết từng dòng trong một lần nhập.
- Đọc dữ liệu nguồn dạng TEXT trước khi **CAST sang kiểu đích**, tránh để một giá trị sai làm hỏng toàn bộ việc nhận file.
- Kiểm tra trường bắt buộc, miền giá trị, kiểu số, mã tham chiếu và trùng khóa trước khi công bố dữ liệu.
- Phân biệt chính sách **all-or-nothing** với **chấp nhận một phần và cách ly dòng lỗi**.
- Dùng **INSERT ... SELECT**, **ON CONFLICT** và **BEGIN/COMMIT/ROLLBACK** để công bố dữ liệu có kiểm soát.
- Hiểu vì sao **phê duyệt nghiệp vụ** và **COMMIT giao dịch** là hai quyết định khác nhau.
- Thiết kế nhập lại batch không gây thay đổi ngoài ý muốn và xử lý xung đột với dữ liệu đích.
- Nhận diện giới hạn của staging tạm theo phiên, thời điểm kiểm tra, khóa đồng thời và hiệu năng với tệp lớn.

## 2. Ba trạng thái khác nhau: đã nhận, đã duyệt và đã công bố

Hãy xét một tệp cập nhật danh mục sản phẩm. Bộ phận vận hành gửi 10 dòng. Trong đó 3 dòng đạt yêu cầu, 7 dòng có vấn đề như mã sản phẩm trùng, giá không hợp lệ hoặc danh mục không tồn tại.

Nếu nhập trực tiếp vào bảng **products**, ta có thể gặp các tình huống:

- Một bản ghi lỗi vi phạm CHECK hoặc FOREIGN KEY khiến câu INSERT thất bại.
- Lệnh ép kiểu từ 'abc' sang NUMERIC báo lỗi trước khi kịp liệt kê đầy đủ các dòng có vấn đề.
- Một mã sản phẩm lặp trong cùng tệp làm UPSERT cập nhật không xác định hoặc gây lỗi.
- Bộ phận nghiệp vụ chưa có cơ hội so sánh dữ liệu mới với dữ liệu đang sử dụng.
- Không rõ hàng nào đã được áp dụng và hàng nào bị bỏ qua khi xử lý thủ công.

Thiết kế staging phân biệt ba mốc:

| Mốc | Dữ liệu đang ở đâu? | Điều gì đã được xác nhận? |
| --- | --- | --- |
| **Đã nhận (staged)** | Bảng staging | Hệ thống đã lưu được bản ghi nguồn, **chưa công nhận đúng** |
| **Đã kiểm tra/duyệt (reviewed/approved)** | Kết quả kiểm tra và trạng thái batch | Đã quyết định hàng nào đủ điều kiện và được phép áp dụng |
| **Đã công bố (published/committed)** | Bảng nghiệp vụ đích | Transaction ghi đích đã COMMIT thành công |

Điểm cần phân biệt:

- **Approval** là quyết định nghiệp vụ hoặc kiểm soát vận hành: có được áp dụng những thay đổi này không?
- **COMMIT** là thao tác của hệ quản trị để xác nhận thay đổi trong **giao dịch dữ liệu**.
- Một batch có thể được nghiệp vụ phê duyệt nhưng vẫn chưa được ghi vào bảng đích.
- Một lệnh ghi có thể được COMMIT dù người vận hành chưa hề thực hiện phê duyệt, nếu ứng dụng thiết kế thiếu bước kiểm soát.

**Mẫu staging đúng không chỉ là thêm một bảng; đó là xác định rõ ranh giới giữa dữ liệu chưa tin cậy và dữ liệu được phép phục vụ nghiệp vụ.**

## 3. Luồng tổng quát của một batch nhập

~~~text
CSV / API / hệ thống đối tác
             |
             v
    [1] RAW STAGING
    batch_id + row_no
    giữ giá trị gốc
             |
             v
    [2] NORMALIZE
    trim, chuẩn hóa mã,
    chuyển định dạng có điều kiện
             |
             v
    [3] VALIDATE
    required / type / range
    FK / duplicate / business rule
             |
       +-----+------+
       |            |
       v            v
  VALID ROWS     REJECTED ROWS
       |         + reason code
       |            |
       +-----+------+----> [4] PREVIEW / APPROVAL
                                |
                                v
                        [5] TRANSACTION
                        BEGIN
                        lock batch
                        record rejects
                        INSERT / UPSERT valid
                        set status PUBLISHED
                        COMMIT
                                |
                +---------------+--------------+
                |                              |
                v                              v
           bảng đích                     audit / báo cáo
~~~

Một số hệ thống chọn **chặn cả batch nếu có bất kỳ lỗi nào**; một số khác **chỉ chấp nhận các dòng hợp lệ**. Cả hai đều có thể dùng staging, nhưng chính sách phải được quyết định trước và thể hiện trong trạng thái batch cũng như báo cáo kết quả.

## 4. Dữ liệu thực hành: nhập danh mục sản phẩm

Chúng ta tạo:

- **demo_categories:** danh mục ngành hàng đã được công nhận.
- **demo_products:** bảng đích lưu sản phẩm chính thức.
- **demo_import_batches:** trạng thái của từng lần nạp.
- **demo_product_stage:** hàng thô từ file, cố ý lưu trường cần kiểm tra bằng TEXT.
- **demo_product_rejections:** hàng không được áp dụng và mã lý do.

Tất cả bảng đều là **TEMP TABLE** cho buổi thực hành. Trong sản phẩm thật, staging và audit cần tồn tại qua nhiều phiên nếu việc duyệt/phê duyệt kéo dài hoặc do người khác thực hiện.

### 4.1. Tạo danh mục và bảng sản phẩm đích

~~~sql
CREATE TEMP TABLE demo_categories (
    category_code TEXT PRIMARY KEY,
    category_name TEXT NOT NULL
);

INSERT INTO demo_categories(category_code, category_name)
VALUES
    ('VPP', 'Van phong pham'),
    ('DT',  'Dien tu');

CREATE TEMP TABLE demo_products (
    sku            TEXT PRIMARY KEY,
    product_name   TEXT NOT NULL,
    category_code  TEXT NOT NULL
        REFERENCES demo_categories(category_code),
    unit_price_vnd NUMERIC(12, 2) NOT NULL
        CHECK (unit_price_vnd > 0),
    active_flag    BOOLEAN NOT NULL DEFAULT TRUE,
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    CHECK (sku = UPPER(BTRIM(sku))),
    CHECK (LENGTH(sku) BETWEEN 1 AND 30),
    CHECK (LENGTH(BTRIM(product_name)) BETWEEN 1 AND 120)
);

-- Sản phẩm này đã tồn tại, để minh họa cập nhật có kiểm soát.
INSERT INTO demo_products
    (sku, product_name, category_code, unit_price_vnd, active_flag)
VALUES
    ('P-107', 'Sac pin cu', 'DT', 160000, TRUE);
~~~

Bảng đích có các bảo vệ cuối cùng:

- **PRIMARY KEY(sku)** ngăn nhiều bản ghi cùng SKU.
- **FOREIGN KEY(category_code)** ngăn sản phẩm tham chiếu ngành hàng không tồn tại.
- **CHECK(unit_price_vnd > 0)** ngăn giá không dương.
- **NOT NULL** ngăn các trường bắt buộc bị bỏ trống ở mức dữ liệu.
- **CHECK** về dạng SKU/độ dài tên buộc dữ liệu phải theo những quy ước tối thiểu.

Những ràng buộc này **không thay thế staging**. Chúng là **hàng rào cuối cùng** nếu dữ liệu hoặc quy tắc kiểm tra trước đó có lỗi.

### 4.2. Tạo batch, staging và nơi lưu dòng từ chối

~~~sql
CREATE TEMP TABLE demo_import_batches (
    batch_id        TEXT PRIMARY KEY,
    source_filename TEXT NOT NULL,
    import_policy   TEXT NOT NULL
        CHECK (import_policy IN ('STRICT', 'PARTIAL')),
    status          TEXT NOT NULL
        CHECK (status IN ('STAGED', 'APPROVED', 'PUBLISHED', 'CANCELLED')),
    expected_rows   INTEGER NOT NULL CHECK (expected_rows >= 0),
    received_at     TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    approved_at     TIMESTAMPTZ,
    published_at    TIMESTAMPTZ
);

CREATE TEMP TABLE demo_product_stage (
    batch_id          TEXT NOT NULL
        REFERENCES demo_import_batches(batch_id),
    row_no            INTEGER NOT NULL CHECK (row_no > 0),
    raw_sku           TEXT,
    raw_product_name  TEXT,
    raw_category_code TEXT,
    raw_unit_price    TEXT,
    raw_active        TEXT,
    received_at       TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    PRIMARY KEY (batch_id, row_no)
);

CREATE TEMP TABLE demo_product_rejections (
    batch_id    TEXT NOT NULL
        REFERENCES demo_import_batches(batch_id),
    row_no      INTEGER NOT NULL,
    error_code  TEXT NOT NULL,
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    PRIMARY KEY (batch_id, row_no)
);

INSERT INTO demo_import_batches
    (batch_id, source_filename, import_policy, status, expected_rows)
VALUES
    ('CAT-2026-09-A', 'catalog-2026-09.csv', 'PARTIAL', 'STAGED', 10);
~~~

Hai cột **batch_id, row_no** tạo định danh của một dòng trong nguồn nhập: row_no = 1 ở batch A **không phải** row_no = 1 ở batch B. Bảng staging chưa có những ràng buộc nghiệp vụ như giá NUMERIC hay category_code phải nằm trong demo_categories, vì nhiệm vụ của nó là **lưu và quan sát đầu vào**, kể cả đầu vào chưa hợp lệ.

**Lưu ý:** dùng TEXT trong raw staging không bảo đảm mọi file đều nạp được. CSV sai cấu trúc nghiêm trọng, sai dấu phân tách hoặc không khớp số cột vẫn có thể thất bại ở bước đọc file. Staging TEXT chủ yếu giúp các **lỗi nội dung ô** như 'abc' thay vì giá số được ghi nhận để phân loại.

### 4.3. Nạp 10 dòng thô từ file giả lập

Trong ví dụ không cần chuẩn bị file ngoài; dùng INSERT để mô phỏng nội dung đã được tách từ CSV:

~~~sql
INSERT INTO demo_product_stage
    (batch_id, row_no, raw_sku, raw_product_name,
     raw_category_code, raw_unit_price, raw_active)
VALUES
    ('CAT-2026-09-A',  1, ' p-100 ', 'So tay',       'vpp',  '120000',  'yes'),
    ('CAT-2026-09-A',  2, 'P-101',   'Chuot',         'DT',   '250000',  'true'),
    ('CAT-2026-09-A',  3, 'P-102',   'USB 64GB',      'dt',   '90000',   '1'),
    ('CAT-2026-09-A',  4, ' p-101 ', 'Chuot gaming',  'DT',   '270000',  'true'),
    ('CAT-2026-09-A',  5, 'P-103',   'Sach',          'SACH', '45000',   'yes'),
    ('CAT-2026-09-A',  6, 'P-104',   'Loa',           'DT',   'abc',     'true'),
    ('CAT-2026-09-A',  7, '   ',     'But bi',        'VPP',  '85000',   'yes'),
    ('CAT-2026-09-A',  8, 'P-105',   'Nhan dan',      'VPP',  '0',       'yes'),
    ('CAT-2026-09-A',  9, 'P-106',   'Bang trang',    'VPP',  '350000',  'maybe'),
    ('CAT-2026-09-A', 10, 'P-107',   'Sac pin USB-C', 'DT',   '180000',  'false');
~~~

Giải thích nhanh các hàng:

| row_no | Tình huống | Điều cần xử lý |
| ---: | --- | --- |
| 1 | SKU có khoảng trắng, chữ thường; category vpp | Chuẩn hóa thành **P-100 / VPP** |
| 2 và 4 | Hai dòng cùng SKU sau khi chuẩn hóa | Phát hiện **trùng khóa trong cùng batch** |
| 3 | Giá hợp lệ, active = 1, category dt | Chuyển đổi hợp lệ |
| 5 | Category SACH chưa có trong danh mục | Từ chối do **tham chiếu không tồn tại** |
| 6 | Giá 'abc' | Từ chối do **không chuyển được thành số** |
| 7 | SKU chỉ gồm khoảng trắng | Từ chối do **thiếu khóa** |
| 8 | Giá bằng 0 | Từ chối do **vi phạm miền giá trị** |
| 9 | Active = 'maybe' | Từ chối do **không rõ boolean** |
| 10 | SKU P-107 đã có ở bảng đích | **Cập nhật** nếu được phê duyệt |

Số lượng dự kiến: **10 dòng raw, 3 dòng hợp lệ, 7 dòng bị từ chối**. Chính sách ví dụ là **PARTIAL**: sau khi xem xét, có thể công bố đúng 3 dòng hợp lệ và lưu lý do loại 7 dòng còn lại.

## 5. Đọc dữ liệu raw mà chưa ép kiểu

Trước khi xác nhận, người vận hành cần nhìn thấy **đúng giá trị nguồn**:

~~~sql
SELECT
    row_no,
    raw_sku,
    raw_product_name,
    raw_category_code,
    raw_unit_price,
    raw_active
FROM demo_product_stage
WHERE batch_id = 'CAT-2026-09-A'
ORDER BY row_no;
~~~

**Không vội CAST(raw_unit_price AS NUMERIC)** trong truy vấn này: dòng 6 có giá 'abc' nên phép CAST sẽ báo lỗi. Mục tiêu ở bước nhận là lưu đủ dữ liệu để sửa hoặc báo lại nhà cung cấp, **không phải cố ép tất cả thành kiểu đích**.

### 5.1. Một batch cần những metadata nào?

Trong dự án thực tế, ngoài batch_id và row_no, thường lưu:

- **Tên nguồn/tệp**, ngày giờ nhận, người tải lên, phiên bản định dạng.
- **Checksum của tệp** hoặc một dấu vân tay nội dung để phát hiện nạp trùng.
- Tổng dòng được khai báo, tổng dòng thực nhận.
- Danh tính người duyệt, ngày duyệt, chính sách STRICT/PARTIAL.
- Trạng thái **STAGED, VALIDATED, APPROVED, PUBLISHED, FAILED/CANCELLED** và các sự kiện chuyển trạng thái.
- Tổng số hàng được chèn mới, cập nhật, bỏ qua, bị từ chối.

Trong bảng thực hành, chúng ta chỉ dùng vài trường thiết yếu. Không nên suy ra rằng bản thiết kế ví dụ đã đủ để làm hệ thống audit/đối soát chính thức.

### 5.2. Coi batch là đơn vị vận hành

Thay vì chỉ ghi "nạp 100 sản phẩm", hãy biết **100 sản phẩm ấy thuộc batch nào**. Batch giúp:

1. Phân biệt dữ liệu của hai tệp đến gần nhau.
2. Xem trước và phê duyệt **đúng một lần nhập**.
3. Truy ngược một sản phẩm đã cập nhật từ tệp nào, dòng nào.
4. Chỉ công bố hoặc hủy một tập dữ liệu đã xác định.
5. Chạy lại có kiểm soát khi bị lỗi mạng hoặc mất kết nối.

## 6. Chuẩn hóa trước khi kiểm tra

Chuẩn hóa (*normalization*) giúp diễn đạt cùng một giá trị theo một quy ước. Ví dụ:

~~~text
' p-100 '  → 'P-100'
'vpp'      → 'VPP'
'  So tay '→ 'So tay'
'YES'      → 'yes'
~~~

Trên PostgreSQL, có thể dùng:

~~~sql
SELECT
    row_no,
    NULLIF(UPPER(BTRIM(raw_sku)), '') AS sku,
    NULLIF(BTRIM(raw_product_name), '') AS product_name,
    NULLIF(UPPER(BTRIM(raw_category_code)), '') AS category_code,
    NULLIF(BTRIM(raw_unit_price), '') AS price_text,
    LOWER(NULLIF(BTRIM(raw_active), '')) AS active_text
FROM demo_product_stage
WHERE batch_id = 'CAT-2026-09-A'
ORDER BY row_no;
~~~

Các hàm:

- **BTRIM(text)** bỏ khoảng trắng ở hai đầu theo bộ ký tự được cung cấp hoặc mặc định tương ứng.
- **UPPER** chuyển mã SKU/category sang chữ hoa để đối chiếu không phân biệt cách gõ chữ thường.
- **LOWER** thống nhất giá trị boolean dưới dạng văn bản.
- **NULLIF(value, '')** chuyển chuỗi rỗng sau khi trim thành NULL, giúp kiểm tra trường bắt buộc.

Đây là những quy tắc **do bài toán sản phẩm quy định**. Không phải mã định danh nào cũng được phép chuyển thành chữ hoa: ví dụ mã bí mật, mật khẩu, token hay ID phân biệt hoa/thường **không được** chuẩn hóa tùy tiện. Cần xác định quy ước của nguồn và bảng đích.

### 6.1. Chuẩn hóa không đồng nghĩa tự đoán

Giá '120000' có thể được đọc theo quy tắc nhập số. Nhưng chuỗi **'120,000'** có thể mang nghĩa "một trăm hai mươi nghìn" ở một định dạng hoặc "một trăm hai mươi phẩy không" ở định dạng khác.

Vì vậy, không nên xóa mọi dấu phẩy hay ký tự tiền tệ mà không có **hợp đồng dữ liệu nguồn**. Trong bài này, giá được chấp nhận là **chữ số thập phân không âm, phần lẻ nếu có dùng dấu chấm và tối đa 2 chữ số**.

## 7. Chuyển kiểu số và boolean một cách có điều kiện

Nếu viết:

~~~sql
SELECT raw_unit_price::NUMERIC(12, 2)
FROM demo_product_stage;
~~~

truy vấn sẽ thất bại tại dòng có raw_unit_price = 'abc'. Muốn phân loại từng dòng, trước tiên kiểm tra định dạng rồi **mới CAST**:

~~~sql
CASE
    WHEN price_text ~ '^[0-9]{1,10}([.][0-9]{1,2})?$'
    THEN price_text::NUMERIC(12, 2)
    ELSE NULL::NUMERIC(12, 2)
END AS unit_price_vnd
~~~

Trong PostgreSQL, toán tử **~** kiểm tra biểu thức chính quy. Biểu thức trên chấp nhận:

- Từ **1 tới 10 chữ số phần nguyên**.
- Phần thập phân là tùy chọn, bắt đầu bằng dấu chấm.
- Nếu có phần thập phân, chỉ nhận **1 hoặc 2 chữ số**.

Giới hạn 10 chữ số phần nguyên phù hợp với kiểu **NUMERIC(12,2)** của bảng đích: tối đa 12 chữ số có nghĩa, trong đó 2 chữ số dành cho phần thập phân. Đây là quy tắc **nghiêm ngặt của định dạng nhập**; một chuỗi có nhiều số 0 ở đầu có thể bị từ chối dù giá trị số sau khi CAST vẫn nhỏ. Nếu nguồn cho phép số 0 ở đầu, cần điều chỉnh quy tắc cho phù hợp.

**Giá 0** qua được kiểm tra định dạng, nhưng sẽ bị từ chối bởi **quy tắc nghiệp vụ unit_price_vnd > 0** ở bước sau. Hai loại kiểm tra khác nhau:

| Loại | Câu hỏi | Ví dụ |
| --- | --- | --- |
| **Định dạng/kiểu** | Chuỗi có chuyển thành số hợp lệ được không? | 'abc' → không |
| **Miền giá trị** | Số đã chuyển có đáp ứng quy tắc không? | 0 → không |

### 7.1. Boolean từ nguồn văn bản

Giả sử nguồn chỉ hỗ trợ các giá trị:

~~~text
true, false, 1, 0, yes, no
~~~

Ta định nghĩa:

~~~sql
CASE
    WHEN active_text IN ('true', '1', 'yes') THEN TRUE
    WHEN active_text IN ('false', '0', 'no') THEN FALSE
    ELSE NULL::BOOLEAN
END AS active_flag
~~~

Chuỗi **'maybe'** trở thành NULL trong **kết quả kiểm tra trung gian**, sau đó nhận mã lỗi **INVALID_ACTIVE**. Ở đây NULL là **dấu hiệu chuyển đổi thất bại**, không phải giá trị hợp lệ được ghi vào cột active_flag NOT NULL của bảng sản phẩm.

Nếu trường raw_active thật sự bị bỏ trống và hệ thống cho phép giá trị mặc định TRUE, hãy định nghĩa rõ quy tắc đó. Không tự động coi một câu trả lời không hiểu được là FALSE hoặc TRUE.

## 8. Kiểm tra đủ các quy tắc và lưu kết quả review

Ta tạo bảng tạm **demo_product_review** từ dữ liệu raw đã chuẩn hóa, chuyển kiểu và kiểm tra. Bảng này chỉ chứa kết quả của **batch CAT-2026-09-A** tại thời điểm chạy câu lệnh; nó là **ảnh chụp kết quả kiểm tra**, không phải một VIEW tự cập nhật.

~~~sql
CREATE TEMP TABLE demo_product_review AS
WITH
    normalized AS (
        SELECT
            batch_id,
            row_no,
            NULLIF(UPPER(BTRIM(raw_sku)), '') AS sku,
            NULLIF(BTRIM(raw_product_name), '') AS product_name,
            NULLIF(UPPER(BTRIM(raw_category_code)), '') AS category_code,
            NULLIF(BTRIM(raw_unit_price), '') AS price_text,
            LOWER(NULLIF(BTRIM(raw_active), '')) AS active_text
        FROM demo_product_stage
        WHERE batch_id = 'CAT-2026-09-A'
    ),
    parsed AS (
        SELECT
            n.*,
            CASE
                WHEN n.price_text ~
                     '^[0-9]{1,10}([.][0-9]{1,2})?$'
                THEN n.price_text::NUMERIC(12, 2)
                ELSE NULL::NUMERIC(12, 2)
            END AS unit_price_vnd,
            CASE
                WHEN n.active_text IN ('true', '1', 'yes')
                    THEN TRUE
                WHEN n.active_text IN ('false', '0', 'no')
                    THEN FALSE
                ELSE NULL::BOOLEAN
            END AS active_flag
        FROM normalized AS n
    ),
    counted AS (
        SELECT
            p.*,
            COUNT(*) OVER (
                PARTITION BY p.batch_id, p.sku
            ) AS sku_occurrences
        FROM parsed AS p
    )
SELECT
    c.*,
    CASE
        WHEN c.sku IS NULL
            THEN 'MISSING_SKU'
        WHEN LENGTH(c.sku) > 30
            THEN 'SKU_TOO_LONG'
        WHEN c.product_name IS NULL
            THEN 'MISSING_NAME'
        WHEN LENGTH(c.product_name) > 120
            THEN 'NAME_TOO_LONG'
        WHEN c.category_code IS NULL
          OR NOT EXISTS (
              SELECT 1
              FROM demo_categories AS cat
              WHERE cat.category_code = c.category_code
          )
            THEN 'UNKNOWN_CATEGORY'
        WHEN c.unit_price_vnd IS NULL
            THEN 'INVALID_PRICE'
        WHEN c.unit_price_vnd <= 0
            THEN 'NON_POSITIVE_PRICE'
        WHEN c.active_flag IS NULL
            THEN 'INVALID_ACTIVE'
        WHEN c.sku_occurrences > 1
            THEN 'DUPLICATE_SKU_IN_BATCH'
        ELSE NULL
    END AS error_code
FROM counted AS c;
~~~

CTE này có bốn vai trò riêng:

1. **normalized:** chuẩn hóa giá trị văn bản theo quy ước.
2. **parsed:** chuyển giá và cờ hoạt động một cách có điều kiện.
3. **counted:** đếm số lần SKU đã chuẩn hóa xuất hiện trong batch.
4. **SELECT cuối:** gắn một **mã lỗi ưu tiên** hoặc NULL nếu dòng hợp lệ.

### 8.1. Vì sao kiểm tra trùng sau khi chuẩn hóa?

Hai giá trị:

~~~text
'P-101'
' p-101 '
~~~

khác nhau trong nguồn thô nhưng đều trở thành **P-101**. Nếu đếm trùng trên raw_sku, hệ thống có thể bỏ sót xung đột. Cách đếm:

~~~sql
COUNT(*) OVER (PARTITION BY batch_id, sku)
~~~

đảm bảo những hàng cùng batch có cùng **SKU chuẩn hóa** được phát hiện.

### 8.2. Vì sao NOT EXISTS kiểm tra danh mục?

~~~sql
NOT EXISTS (
    SELECT 1
    FROM demo_categories AS cat
    WHERE cat.category_code = c.category_code
)
~~~

Điều này cho phép gắn mã lỗi **UNKNOWN_CATEGORY** trước khi đưa dữ liệu vào bảng đích. Nếu chỉ trông chờ FOREIGN KEY khi INSERT, toàn bộ lệnh ghi có thể thất bại nhưng không trả một báo cáo dễ đọc về từng dòng sai.

**Lưu ý cạnh tranh đồng thời:** nếu category hợp lệ khi review nhưng bị thay đổi/xóa trước khi công bố, kết quả review có thể cũ. Ràng buộc FOREIGN KEY tại bảng đích vẫn là lớp bảo vệ bắt buộc, và quy trình quan trọng cần chính sách kiểm tra lại khi công bố.

### 8.3. Chỉ một mã lỗi hay nhiều mã lỗi trên một dòng?

Ví dụ dùng **CASE** theo thứ tự, nên mỗi dòng chỉ có **một lỗi ưu tiên**. Nếu dòng vừa thiếu SKU vừa sai giá, CASE sẽ trả **MISSING_SKU** mà chưa liệt kê thêm lỗi giá.

Hệ thống thực có thể lưu **nhiều lỗi cho cùng một dòng**, chẳng hạn bảng errors với khóa **(batch_id, row_no, error_code)** hoặc một mảng mã lỗi. Đó là lựa chọn giao diện kiểm soát chất lượng; điều quan trọng là **không coi việc chỉ ghi một lý do là chứng minh các trường khác đều hợp lệ**.

## 9. Xem trước số lượng chấp nhận và từ chối

Sau khi tạo demo_product_review:

~~~sql
SELECT
    row_no,
    sku,
    product_name,
    category_code,
    unit_price_vnd,
    active_flag,
    error_code
FROM demo_product_review
ORDER BY row_no;
~~~

Các mã kết quả dự kiến:

| row_no | SKU đã chuẩn hóa | error_code | Xử lý |
| ---: | --- | --- | --- |
| 1 | P-100 | NULL | Được chấp nhận |
| 2 | P-101 | DUPLICATE_SKU_IN_BATCH | Từ chối |
| 3 | P-102 | NULL | Được chấp nhận |
| 4 | P-101 | DUPLICATE_SKU_IN_BATCH | Từ chối |
| 5 | P-103 | UNKNOWN_CATEGORY | Từ chối |
| 6 | P-104 | INVALID_PRICE | Từ chối |
| 7 | NULL | MISSING_SKU | Từ chối |
| 8 | P-105 | NON_POSITIVE_PRICE | Từ chối |
| 9 | P-106 | INVALID_ACTIVE | Từ chối |
| 10 | P-107 | NULL | Được chấp nhận |

Tổng hợp trạng thái:

~~~sql
SELECT
    COUNT(*) AS total_rows,
    COUNT(*) FILTER (WHERE error_code IS NULL) AS valid_rows,
    COUNT(*) FILTER (WHERE error_code IS NOT NULL) AS rejected_rows
FROM demo_product_review;
~~~

Kết quả:

| total_rows | valid_rows | rejected_rows |
| ---: | ---: | ---: |
| **10** | **3** | **7** |

Thống kê theo lý do:

~~~sql
SELECT
    COALESCE(error_code, 'VALID') AS row_result,
    COUNT(*) AS row_count
FROM demo_product_review
GROUP BY error_code
ORDER BY row_result;
~~~

Ở bộ dữ liệu này, **DUPLICATE_SKU_IN_BATCH = 2**, còn mỗi lỗi **MISSING_SKU, UNKNOWN_CATEGORY, INVALID_PRICE, NON_POSITIVE_PRICE, INVALID_ACTIVE** có 1 dòng.

### 9.1. Xem nguồn thô bên cạnh kết quả kiểm tra

Để xử lý phản hồi từ đơn vị cung cấp dữ liệu:

~~~sql
SELECT
    s.row_no,
    s.raw_sku,
    s.raw_unit_price,
    s.raw_active,
    r.sku AS normalized_sku,
    r.error_code
FROM demo_product_stage AS s
JOIN demo_product_review AS r
    ON r.batch_id = s.batch_id
   AND r.row_no = s.row_no
WHERE s.batch_id = 'CAT-2026-09-A'
  AND r.error_code IS NOT NULL
ORDER BY s.row_no;
~~~

Không nên chỉ trả “7 dòng không hợp lệ”. **row_no, giá trị gốc và mã lỗi** là thông tin cần thiết để sửa file và đối chiếu với hệ thống gửi.

## 10. Quyết định xử lý mã trùng trong cùng batch

Một sản phẩm P-101 xuất hiện ở **hai dòng** với giá 250.000 và 270.000 đồng. Có ít nhất ba chính sách hợp lý:

1. **Từ chối tất cả dòng trùng:** yêu cầu bên gửi quyết định giá nào đúng.
2. **Giữ dòng cuối trong file:** phù hợp nếu hợp đồng dữ liệu nói rằng bản ghi phía sau có ưu tiên cao hơn.
3. **Giữ dòng có phiên bản/thời điểm cập nhật mới nhất:** phù hợp nếu nguồn cung cấp trường version hoặc updated_at đáng tin cậy.

Ví dụ chính chọn **từ chối cả hai dòng trùng**. Vì giá đang khác nhau, việc tự chọn dòng đầu hoặc dòng cuối mà không có quy tắc sẽ làm thay đổi dữ liệu có thể không được phê duyệt.

Nếu nghiệp vụ rõ ràng quy định “dòng có row_no lớn nhất thắng”, có thể đánh số:

~~~sql
SELECT
    batch_id,
    row_no,
    sku,
    unit_price_vnd,
    ROW_NUMBER() OVER (
        PARTITION BY batch_id, sku
        ORDER BY row_no DESC
    ) AS sku_choice
FROM demo_product_review
WHERE sku IS NOT NULL
ORDER BY sku, row_no;
~~~

Với P-101, row_no = 4 nhận sku_choice = 1, còn row_no = 2 nhận 2. **Đây chỉ là minh họa một chính sách thay thế**, không tự động biến P-101 thành dòng hợp lệ trong bảng review đã tạo. Nếu chọn chính sách “giữ dòng cuối”, phải **thiết kế lại bước kiểm tra** và bảo đảm chỉ có một dòng/sku được đưa vào UPSERT.

> Trong PostgreSQL, một lệnh INSERT ... ON CONFLICT DO UPDATE có nhiều dòng đầu vào cùng khóa đích có thể thất bại vì cùng một hàng đích bị tác động nhiều lần trong một lệnh. Không dùng UPSERT như một cách thay thế cho quyết định xử lý trùng SKU trong **chính batch**.

## 11. Phê duyệt batch: khác với COMMIT

Trước khi cập nhật bảng đích, người vận hành cần xem:

- Tệp có đúng nguồn và số dòng dự kiến không?
- Có bao nhiêu hàng hợp lệ và bị từ chối?
- Những thay đổi đối với SKU đã tồn tại có hợp lệ không?
- Chính sách nhập một phần có được người phụ trách chấp thuận không?
- Batch có bị sửa sau khi review không?

Ở ví dụ này, giả sử người có thẩm quyền **chấp nhận chỉ áp dụng 3 dòng hợp lệ** và ghi lại 7 dòng bị loại. Ta đổi trạng thái batch từ STAGED sang APPROVED:

~~~sql
UPDATE demo_import_batches
SET
    status = 'APPROVED',
    approved_at = clock_timestamp()
WHERE batch_id = 'CAT-2026-09-A'
  AND status = 'STAGED';
~~~

Đây chỉ là **mô phỏng bước phê duyệt** để tiếp tục thực hành. Trong hệ thống thật, không nên coi việc bất kỳ người có quyền UPDATE bảng batch đều có thể tự gán APPROVED là một quy trình duyệt đủ an toàn. Cần **phân quyền, người duyệt, bản ghi yêu cầu thay đổi và dấu vết audit** tương ứng với rủi ro của dữ liệu.

### 11.1. Snapshot được duyệt không được âm thầm thay đổi

**demo_product_review** là bảng tạm được tạo tại một thời điểm. Nếu sau đó có người sửa demo_product_stage hoặc demo_categories, review **không tự cập nhật**.

Trong quy trình có khoảng cách thời gian giữa review và publish, nên:

1. Khóa nội dung batch sau khi gửi duyệt, hoặc lưu **phiên bản/checksum**.
2. Ghi nhận người duyệt đã xem **đúng bộ kết quả kiểm tra nào**.
3. Khi công bố, **kiểm tra lại** những ràng buộc phụ thuộc dữ liệu bên ngoài nếu cần.
4. Bảo vệ bảng đích bằng PRIMARY KEY, FOREIGN KEY, NOT NULL và CHECK.
5. Bảo đảm job công bố không dùng một review **đã lỗi thời** so với bản dữ liệu được duyệt.

Ở buổi thực hành, chúng ta tiếp tục ngay trong cùng phiên với dữ liệu không bị chỉnh sửa. Không suy ra rằng mô hình TEMP TABLE này đáp ứng quy trình duyệt kéo dài nhiều giờ hoặc qua nhiều người.

## 12. Công bố các dòng hợp lệ trong một transaction

Sau khi batch có trạng thái APPROVED, thao tác công bố cần đảm bảo **các thay đổi liên quan được COMMIT cùng nhau**: ghi lỗi, ghi sản phẩm được chấp nhận, cập nhật trạng thái batch.

### 12.1. Toàn bộ câu lệnh công bố có thể chạy liên tiếp

~~~sql
BEGIN;

-- Khóa batch và xác nhận đây vẫn là batch đã được duyệt.
DO $$
DECLARE
    v_status   TEXT;
    v_expected INTEGER;
    v_actual   INTEGER;
BEGIN
    SELECT status, expected_rows
    INTO v_status, v_expected
    FROM demo_import_batches
    WHERE batch_id = 'CAT-2026-09-A'
    FOR UPDATE;

    IF v_status IS DISTINCT FROM 'APPROVED' THEN
        RAISE EXCEPTION
            'Batch CAT-2026-09-A khong o trang thai APPROVED: %',
            v_status;
    END IF;

    SELECT COUNT(*)
    INTO v_actual
    FROM demo_product_stage
    WHERE batch_id = 'CAT-2026-09-A';

    IF v_actual <> v_expected THEN
        RAISE EXCEPTION
            'So dong thuc te % khac du kien %',
            v_actual, v_expected;
    END IF;
END;
$$;

-- Ghi dấu vết các dòng bị từ chối.
DELETE FROM demo_product_rejections
WHERE batch_id = 'CAT-2026-09-A';

INSERT INTO demo_product_rejections
    (batch_id, row_no, error_code)
SELECT batch_id, row_no, error_code
FROM demo_product_review
WHERE batch_id = 'CAT-2026-09-A'
  AND error_code IS NOT NULL;

-- Chỉ ghi những dòng đã vượt qua kiểm tra.
INSERT INTO demo_products
    (sku, product_name, category_code,
     unit_price_vnd, active_flag)
SELECT
    sku,
    product_name,
    category_code,
    unit_price_vnd,
    active_flag
FROM demo_product_review
WHERE batch_id = 'CAT-2026-09-A'
  AND error_code IS NULL
ON CONFLICT (sku) DO UPDATE
SET
    product_name   = EXCLUDED.product_name,
    category_code  = EXCLUDED.category_code,
    unit_price_vnd = EXCLUDED.unit_price_vnd,
    active_flag    = EXCLUDED.active_flag,
    updated_at     = clock_timestamp()
WHERE (
    demo_products.product_name,
    demo_products.category_code,
    demo_products.unit_price_vnd,
    demo_products.active_flag
) IS DISTINCT FROM (
    EXCLUDED.product_name,
    EXCLUDED.category_code,
    EXCLUDED.unit_price_vnd,
    EXCLUDED.active_flag
);

-- Batch chỉ được đánh dấu đã công bố cùng transaction ghi đích.
UPDATE demo_import_batches
SET
    status = 'PUBLISHED',
    published_at = clock_timestamp()
WHERE batch_id = 'CAT-2026-09-A'
  AND status = 'APPROVED';

COMMIT;
~~~

Khi **COMMIT thành công**, ba phần đã được thay đổi trong cùng giao dịch:

1. Bảng lỗi ghi nhận **7 dòng bị từ chối**.
2. Bảng sản phẩm áp dụng **3 dòng hợp lệ**: **P-100, P-102, P-107**.
3. Batch chuyển sang trạng thái **PUBLISHED**.

Trong dữ liệu mẫu:

- **P-100** và **P-102** là **hai sản phẩm mới**.
- **P-107** đã tồn tại, nên được **cập nhật** thành tên “Sac pin USB-C”, giá 180.000 đồng và active_flag = FALSE.
- Hai dòng P-101 không được dùng để chọn một giá bất kỳ vì chính sách review đã từ chối cả hai.

**Nếu một câu lệnh trong transaction thất bại**, giao dịch không được COMMIT thành công theo luồng thông thường; trong PostgreSQL sau lỗi, cần **ROLLBACK** để hủy giao dịch bị lỗi. Không nên tiếp tục thử COMMIT một transaction đang ở trạng thái lỗi.

### 12.2. Vì sao dùng ON CONFLICT?

**ON CONFLICT (sku)** biểu thị quy tắc:

- Nếu SKU chưa có, **INSERT**.
- Nếu SKU đã tồn tại, **UPDATE những trường đã được phê duyệt**.

Trong PostgreSQL, **EXCLUDED.column_name** là giá trị từ hàng đầu vào đã cố INSERT nhưng gặp xung đột khóa duy nhất. Đây là cú pháp PostgreSQL, không phải cú pháp chung cho mọi hệ SQL.

Phần:

~~~sql
WHERE (
    demo_products.product_name,
    demo_products.category_code,
    demo_products.unit_price_vnd,
    demo_products.active_flag
) IS DISTINCT FROM (
    EXCLUDED.product_name,
    EXCLUDED.category_code,
    EXCLUDED.unit_price_vnd,
    EXCLUDED.active_flag
)
~~~

chỉ UPDATE khi có ít nhất một trường thực sự khác nhau, tránh một số lần ghi và đổi updated_at không cần thiết. Đây là quy tắc so sánh theo các cột được chọn; nếu hệ thống có thêm trường cần cập nhật, phải xem lại danh sách này.

**Không phải mọi import đều nên UPDATE.** Nếu batch chỉ được phép thêm SKU mới, có thể dùng **ON CONFLICT (sku) DO NOTHING** hoặc coi SKU đã tồn tại là một lỗi cần duyệt. Quy tắc “cập nhật khi trùng” là một lựa chọn nghiệp vụ, không phải mặc định của staging.

### 12.3. Kiểm tra kết quả sau công bố

~~~sql
SELECT
    sku,
    product_name,
    category_code,
    unit_price_vnd,
    active_flag
FROM demo_products
ORDER BY sku;
~~~

Kết quả:

| sku | product_name | category_code | unit_price_vnd | active_flag |
| --- | --- | --- | ---: | --- |
| P-100 | So tay | VPP | 120000 | TRUE |
| P-102 | USB 64GB | DT | 90000 | TRUE |
| P-107 | Sac pin USB-C | DT | 180000 | FALSE |

Tổng số hàng của bảng sản phẩm là **3** vì ban đầu có một SKU P-107, sau đó thêm hai SKU và cập nhật P-107. **Ba hàng hợp lệ không đồng nghĩa ba hàng INSERT mới.**

Kiểm tra trạng thái và số lỗi:

~~~sql
SELECT batch_id, import_policy, status, expected_rows
FROM demo_import_batches;

SELECT
    batch_id,
    COUNT(*) AS rejected_rows
FROM demo_product_rejections
GROUP BY batch_id;
~~~

Kết quả trạng thái là **PUBLISHED**, số dòng bị từ chối là **7**.

### 12.4. Mối liên hệ giữa phê duyệt và transaction

Người duyệt quyết định **cho phép áp dụng những gì**; transaction đảm bảo **các thao tác ghi tương ứng được áp dụng cùng nhau hoặc cùng bị hủy**. Nếu ghi sản phẩm thành công nhưng ghi trạng thái batch thất bại mà không có transaction, hệ thống có thể rơi vào trạng thái khó khôi phục: dữ liệu đích đã thay đổi nhưng batch vẫn hiển thị chưa công bố.

Vì vậy, đối với một batch có nhiều bảng đích hoặc bảng audit, **đặt các thay đổi phải nhất quán vào cùng transaction** là một nguyên tắc quan trọng.

## 13. Chính sách STRICT: hoặc tất cả hợp lệ, hoặc không công bố gì

Không phải nghiệp vụ nào cũng cho phép nhập một phần. Ví dụ danh mục định mức kế toán hoặc bảng giá có hiệu lực đồng thời có thể yêu cầu **tất cả các dòng hợp lệ mới được công bố**.

Quy tắc STRICT có thể kiểm tra:

~~~sql
SELECT
    COUNT(*) AS total_rows,
    COUNT(*) FILTER (WHERE error_code IS NOT NULL) AS error_rows
FROM demo_product_review;
~~~

Nếu error_rows **lớn hơn 0**, **không cấp phép công bố**. Với dữ liệu hiện tại error_rows = 7, nên chính sách STRICT phải từ chối cả batch.

Ví dụ dùng PostgreSQL để chặn transaction:

~~~sql
-- Minh họa STRICT; với batch dữ liệu mẫu hiện tại, DO sẽ RAISE EXCEPTION.
-- Không chạy như quy trình công bố thành công khi vẫn còn 7 lỗi.
BEGIN;

DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM demo_product_review
        WHERE error_code IS NOT NULL
    ) THEN
        RAISE EXCEPTION
            'STRICT import: batch con dong loi, khong duoc cong bo';
    END IF;
END;
$$;

-- Chỉ được viết các lệnh INSERT chính thức sau khi điều kiện
-- STRICT đã được xác nhận là đạt trong transaction.

ROLLBACK;
~~~

Nếu chạy khối trên với dữ liệu lỗi, PostgreSQL sẽ báo exception; **ROLLBACK** kết thúc giao dịch đang lỗi. Trong ứng dụng thật, phần kiểm tra và phần ghi bảng đích cần được thực hiện theo một quy trình điều khiển rõ ràng, không dựa vào việc con người bỏ qua thông báo lỗi.

So sánh hai chính sách:

| Khía cạnh | STRICT / all-or-nothing | PARTIAL / nhập một phần |
| --- | --- | --- |
| Một hàng sai | **Chặn toàn bộ batch** | Từ chối hàng sai, có thể giữ hàng hợp lệ |
| Phù hợp | Bộ dữ liệu phải nhất quán toàn lô | Dữ liệu độc lập từng hàng |
| Sửa lỗi | Sửa batch rồi kiểm tra lại | Sửa các hàng bị từ chối và nhập lại có kiểm soát |
| Rủi ro nghiệp vụ | Trì hoãn toàn bộ khi một dòng sai | Một số hàng có thể được công bố trước các hàng khác |
| Cần báo cáo | Mã lỗi từng dòng, trạng thái batch | Mã lỗi, số hàng chấp nhận, số hàng từ chối và đối soát |

Với dữ liệu có quan hệ chặt chẽ, ví dụ **đơn hàng và các dòng đơn**, chấp nhận một phần **một cách tùy tiện** có thể tạo đơn thiếu chi tiết. Khi đó cần một chính sách theo **đơn vị nghiệp vụ**, không chỉ theo hàng CSV.

## 14. Bảng staging tạm và staging lâu dài

Trong thực hành, **CREATE TEMP TABLE** là lựa chọn an toàn và dễ dọn dẹp. Nhưng cần hiểu vòng đời:

| Loại | Vòng đời | Tình huống phù hợp |
| --- | --- | --- |
| **TEMP TABLE** | Gắn với phiên DB, theo quy tắc hệ quản trị | Thử nghiệm, phép biến đổi trung gian trong một kết nối |
| **Bảng staging thông thường** | Tồn tại lâu dài tới khi được xóa theo chính sách | Nạp dữ liệu qua nhiều phiên, duyệt bởi người khác, audit và retry |
| **Bảng review snapshot** | Tùy thiết kế: tạm hoặc bền vững | Đối chiếu bộ dữ liệu đã kiểm tra/phê duyệt |
| **Bảng đích nghiệp vụ** | Dữ liệu được công bố chính thức | Đọc bởi ứng dụng, API, báo cáo |

Một tiến trình tải CSV, người khác duyệt trên giao diện web, và job nền công bố sau vài giờ **không thể chỉ dựa vào bảng TEMP thuộc kết nối của tiến trình tải**, vì các kết nối không chia sẻ cùng bảng tạm theo cách đó.

**Thiết kế sản xuất thường dùng schema staging riêng**, ví dụ:

~~~sql
-- Mẫu ý tưởng trên PostgreSQL, không cần chạy trong bài thực hành:
CREATE SCHEMA IF NOT EXISTS staging;

CREATE TABLE staging.product_rows (
    batch_id   TEXT NOT NULL,
    row_no     INTEGER NOT NULL,
    raw_sku    TEXT,
    raw_price  TEXT,
    received_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (batch_id, row_no)
);
~~~

Trong hệ thống thật, thêm khóa ngoại batch, vai trò phân quyền, audit, chính sách xóa theo thời hạn và các ràng buộc phù hợp. Đoạn trên chỉ minh họa **bảng staging bền vững**, không phải schema sản xuất hoàn chỉnh.

### 14.1. Bảo vệ thông tin nhạy cảm ở staging

Bảng raw có thể chứa PII, mã định danh hoặc dữ liệu đối tác chưa công bố. Không nên coi staging là một vùng “ai cũng có thể xem” chỉ vì dữ liệu chưa chính thức. Cần:

- Phân quyền theo vai trò nhập, duyệt, công bố và điều tra lỗi.
- Mã hóa và chính sách lưu trữ/xóa phù hợp.
- Hạn chế xuất nguyên bản các dòng chứa thông tin cá nhân.
- Không dùng nội dung raw từ nguồn làm SQL động không kiểm soát.
- Ghi sự kiện phê duyệt và thay đổi trạng thái theo quyền hạn.

**Dữ liệu chưa tin cậy vẫn cần bảo vệ về an toàn thông tin.**

## 15. Nạp CSV vào bảng trung gian bằng COPY hoặc \copy

Ví dụ dùng INSERT để không cần file ngoài. Trong PostgreSQL, có thể dùng **COPY** để nạp dữ liệu từ CSV vào bảng staging theo cột xác định.

Giả sử file có các cột:

~~~text
batch_id,row_no,raw_sku,raw_product_name,raw_category_code,raw_unit_price,raw_active
CAT-2026-09-A,1, p-100 ,So tay,vpp,120000,yes
CAT-2026-09-A,2,P-101,Chuot,DT,250000,true
...
~~~

Lệnh SQL **COPY** dạng server-side:

~~~sql
-- Đường dẫn chỉ là ví dụ, tệp thực tế phải tồn tại trên máy DB server.
COPY demo_product_stage
    (batch_id, row_no, raw_sku, raw_product_name,
     raw_category_code, raw_unit_price, raw_active)
FROM '/server/path/catalog.csv'
WITH (FORMAT CSV, HEADER TRUE);
~~~

**COPY ... FROM '/server/path/...'** đọc file từ **phía máy chủ PostgreSQL** và chịu các yêu cầu quyền truy cập tương ứng. Không nên nghĩ nó đọc được đường dẫn trên máy tính của người dùng chỉ vì người dùng nhập đường dẫn đó.

Nếu dùng **psql**, có thể dùng lệnh meta-command **\copy** để nạp từ phía client:

~~~text
\copy demo_product_stage (batch_id, row_no, raw_sku, raw_product_name, raw_category_code, raw_unit_price, raw_active) FROM '/client/path/catalog.csv' WITH (FORMAT csv, HEADER true)
~~~

**\copy là lệnh của psql**, không phải cú pháp SQL chuẩn gửi qua mọi driver. Khi nhập qua ứng dụng, có thể dùng các API COPY/streaming tương ứng của driver hoặc cơ chế bulk insert được hệ quản trị hỗ trợ.

### 15.1. Đọc file chưa đồng nghĩa công bố

Khi COPY hoàn tất, dữ liệu mới chỉ ở **demo_product_stage**. Hệ thống **chưa** tự:

- Chuyển raw_unit_price thành NUMERIC.
- Quyết định SKU nào được cập nhật.
- Xác nhận category tồn tại.
- Giải quyết duplicate.
- Duyệt chính sách nhập partial/strict.

Chính các bước chuẩn hóa, validation, review và transaction mới thực hiện những điều đó.

### 15.2. Lỗi CSV ở cấp cấu trúc

Staging với các cột TEXT giúp chịu được lỗi **nội dung**, nhưng file bị lỗi cú pháp CSV có thể vẫn khiến COPY thất bại: hàng thiếu thừa cột, dấu ngoặc kép không đóng, dấu phân cách bị hiểu sai hoặc sai encoding.

Nếu nguồn không bảo đảm cấu trúc CSV ổn định, có thể cần một **bước nhận file và phân tích cú pháp riêng** trước khi INSERT vào staging, hoặc dùng cơ chế import có hỗ trợ lưu lỗi từng hàng. Cần phân biệt **lỗi parse file** với **lỗi giá trị trong một cột đã parse thành công**.

## 16. Nạp lại, xử lý lỗi mạng và tính idempotent

Một tiến trình nhập có thể bị mất kết nối ngay sau khi gửi COMMIT. Ứng dụng không biết chắc batch đã được công bố hay chưa. Nếu chạy lại mù quáng, nó có thể cập nhật lại cùng dữ liệu, ghi trùng audit hoặc gây side effect.

**Idempotent** trong ngữ cảnh nhập dữ liệu có nghĩa: cùng một yêu cầu logic được gửi lặp lại **không tạo thêm những tác động nghiệp vụ ngoài dự kiến**.

Các lớp bảo vệ:

1. **batch_id duy nhất** trong bảng batches.
2. **(batch_id, row_no) duy nhất** trong raw staging.
3. **SKU duy nhất** trong bảng sản phẩm.
4. **Trạng thái batch** ngăn công bố lại một batch đã PUBLISHED.
5. **ON CONFLICT** xác định hành vi khi sản phẩm đã tồn tại.
6. **Transaction** gom cập nhật sản phẩm, lỗi và trạng thái thành một đơn vị.

Trong câu công bố phần 12, khối DO yêu cầu batch phải ở trạng thái **APPROVED**. Sau COMMIT thành công, status = **PUBLISHED**, nên chạy lại nguyên quy trình sẽ **bị chặn** tại bước kiểm tra trạng thái.

Nếu job báo lỗi do mất kết nối, hãy **đọc lại trạng thái batch và dữ liệu audit** trước khi quyết định thử công bố lại. Không thể suy luận chỉ từ việc client không nhận được phản hồi rằng COMMIT chắc chắn đã thất bại.

### 16.1. ON CONFLICT không đủ để bảo đảm idempotency toàn quy trình

ON CONFLICT có thể xử lý lặp SKU, nhưng không tự xử lý:

- Việc ghi lại log thông báo/email hai lần.
- Một batch được người khác duyệt lại sau khi nội dung thay đổi.
- Hai job dùng cùng batch nhưng đọc hai snapshot dữ liệu khác nhau.
- Một UPSERT cập nhật updated_at liên tục dù giá trị không đổi.
- Các bảng phụ có thao tác INSERT không có khóa chống trùng.

Thiết kế đúng cần **khóa nghiệp vụ, trạng thái batch và kiểm soát transaction** chứ không chỉ một mệnh đề SQL.

### 16.2. Xác thực nội dung khi nạp lại tệp

Nếu một tệp đã nhập với batch_id cố định, lần thử lại có thể dùng:

~~~sql
-- Minh họa ý tưởng chống trùng dòng nạp:
INSERT INTO demo_product_stage
    (batch_id, row_no, raw_sku, raw_product_name,
     raw_category_code, raw_unit_price, raw_active)
VALUES
    ('CAT-2026-09-A', 1, ' p-100 ', 'So tay', 'vpp', '120000', 'yes')
ON CONFLICT (batch_id, row_no) DO NOTHING;
~~~

Nhưng **DO NOTHING** chỉ tránh lỗi khóa; nếu cùng batch_id/row_no mà nội dung mới **khác**, lệnh này sẽ âm thầm giữ dữ liệu cũ. Với hệ thống yêu cầu tính toàn vẹn của tệp, cần kiểm tra **checksum/dấu vân tay** hoặc so sánh các trường trước khi chấp nhận lần retry.

**Không dùng một batch_id cũ để nạp một phiên bản file khác** mà không có quy tắc version rõ ràng.

## 17. Khi dữ liệu lỗi được sửa sau review

Giả sử nhà cung cấp sửa:

- row_no 6: giá 'abc' thành '90000'.
- row_no 9: active 'maybe' thành 'true'.
- row_no 5: category SACH được thay bằng VPP hoặc được cấp danh mục mới.

Ta không nên chỉ sửa trực tiếp vài cột trong **demo_product_review** rồi công bố, vì review là **kết quả dẫn xuất** từ raw staging và các quy tắc kiểm tra. Làm như vậy sẽ mất khả năng chứng minh kết quả kiểm tra ứng với đầu vào nào.

Một chu trình sửa đúng thường là:

1. Nhận lại tệp đã sửa hoặc tạo **phiên bản batch mới**.
2. Ghi lại nguồn và người thực hiện thay đổi.
3. Nạp raw staging của phiên bản mới.
4. Chạy lại chuẩn hóa/validation, tạo kết quả review mới.
5. Xem xét lại những hàng đã từng bị từ chối hoặc bị thay đổi.
6. Phê duyệt phiên bản chính xác sẽ được công bố.

**Không công bố bằng review snapshot cũ sau khi raw data đã được sửa.** Trong ví dụ chúng ta đã công bố batch A; nếu muốn thực hành với file sửa, nên tạo **batch B** riêng để không phá vỡ ý nghĩa trạng thái PUBLISHED.

### 17.1. Cách ly lỗi (quarantine) cần giữ đủ thông tin

Bảng demo_product_rejections chỉ ghi **batch_id, row_no, error_code**. Giá trị nguồn vẫn có trong demo_product_stage cùng phiên thực hành, nên có thể JOIN để điều tra.

Trong sản phẩm thật, nếu staging sẽ được xóa sớm, bảng quarantine phải đủ thông tin để truy vết hoặc có tham chiếu tới **tệp nguồn được lưu bền vững**. Mã lỗi nên ổn định cho hệ thống và có bảng diễn giải thông điệp dễ hiểu cho người nhập dữ liệu.

## 18. Đừng nhầm lỗi batch với lỗi transaction

Có ba loại thất bại thường bị gộp chung:

| Loại | Ví dụ | Cách xử lý |
| --- | --- | --- |
| **Lỗi dữ liệu đầu vào** | Giá 'abc', SKU trống, category lạ | Gắn lỗi theo dòng, yêu cầu sửa nguồn hoặc dùng PARTIAL |
| **Lỗi kiểm soát nghiệp vụ** | Batch chưa được duyệt, bị thay đổi sau duyệt | Chặn công bố, không tự nâng trạng thái |
| **Lỗi trong transaction ghi đích** | Vi phạm ràng buộc, deadlock, lỗi kết nối | ROLLBACK/đọc lại trạng thái, retry theo chính sách an toàn |

Lỗi dữ liệu có thể đã được phát hiện ở staging, nhưng bảng đích vẫn có thể từ chối một bản ghi vì **ràng buộc cuối**. Đây không phải mâu thuẫn: staging là lớp kiểm tra dễ hiểu, còn ràng buộc database là lớp giữ toàn vẹn khi có thay đổi đồng thời hoặc trường hợp chưa được lường trước.

### 18.1. Không dùng SAVEPOINT để vô tình tạo nhập một phần

Một số hệ cho phép dùng **SAVEPOINT** để xử lý lỗi từng nhóm nhỏ. Kỹ thuật này hữu ích trong một số import, nhưng không nên tự động chuyển chính sách **STRICT** thành “dòng nào không lỗi thì giữ” chỉ vì có thể ROLLBACK TO SAVEPOINT rồi tiếp tục.

**Ranh giới atomicity phải theo đơn vị nghiệp vụ.** Nếu cần nhận cả đơn hàng và các dòng chi tiết như một thực thể, có thể cần SAVEPOINT/transaction theo **đơn** chứ không theo từng hàng CSV.

## 19. Kiểm tra đồng thời: hai job cùng công bố một dữ liệu

Trong môi trường có nhiều worker, có thể xảy ra:

~~~text
Worker A                         Worker B
   |                                |
đọc batch APPROVED             đọc batch APPROVED
   |                                |
ghi sản phẩm                   ghi sản phẩm
   |                                |
cập nhật status                cập nhật status
~~~

Nếu cả hai đọc trạng thái mà không khóa và không có quy tắc quản lý, cùng một batch có thể bị xử lý hai lần hoặc ghi đè qua lại.

### 19.1. Khóa batch khi công bố

Trong ví dụ, ta sử dụng:

~~~sql
SELECT status, expected_rows
FROM demo_import_batches
WHERE batch_id = 'CAT-2026-09-A'
FOR UPDATE;
~~~

**FOR UPDATE** đặt khóa hàng batch trong transaction theo cơ chế PostgreSQL. Nếu hai transaction muốn khóa cùng hàng batch, chúng phải chờ hoặc xử lý theo quy tắc khóa của hệ. Sau khi transaction thứ nhất COMMIT và batch chuyển PUBLISHED, transaction thứ hai cần **đọc lại và nhận thấy batch không còn APPROVED**.

**Lưu ý:** locking batch chỉ ngăn hai job tranh nhau **cùng batch đó**. Hai **batch khác nhau** vẫn có thể cùng chứa SKU P-107 và cùng muốn cập nhật nó. Ràng buộc PRIMARY KEY và cơ chế xung đột ghi sẽ bảo vệ tính nhất quán ở mức database, nhưng quy tắc **batch nào thắng** cần được xác định theo nghiệp vụ.

### 19.2. Cạnh tranh giữa các batch khác nhau

Ví dụ:

- Batch A muốn cập nhật SKU P-107 thành 180.000.
- Batch B muốn cập nhật SKU P-107 thành 175.000.

Nếu dùng UPSERT “ai COMMIT sau thì thắng”, giá cuối phụ thuộc trình tự xử lý. Điều đó có thể **không phù hợp** khi dữ liệu B cũ hơn A về mặt nghiệp vụ.

Những phương án có thể cân nhắc:

- Có **source_version** hoặc **effective_at** và chỉ cập nhật nếu phiên bản mới hơn.
- Dùng điều kiện so sánh **updated_at nguồn**, không phải thời điểm job chạy.
- Tách luồng phê duyệt khi SKU có thay đổi xung đột.
- Chặn hai batch chồng lấn SKU cùng công bố nếu yêu cầu kiểm soát nghiêm ngặt.
- Cân nhắc mức cô lập và cơ chế retry khi deadlock/xung đột.

Không nên để **thứ tự mạng hoặc thứ tự chạy worker** âm thầm trở thành quy tắc quyết định giá sản phẩm.

## 20. Phê duyệt bản ghi đã có: xem trước UPDATE và INSERT

Trong cùng batch, không phải mọi dòng hợp lệ đều là sản phẩm mới. Trước khi duyệt, nên hiển thị sự khác nhau giữa **chèn mới**, **cập nhật** và **không thay đổi**.

Ví dụ truy vấn xem trước:

~~~sql
SELECT
    r.row_no,
    r.sku,
    CASE
        WHEN p.sku IS NULL THEN 'INSERT'
        WHEN (
            p.product_name,
            p.category_code,
            p.unit_price_vnd,
            p.active_flag
        ) IS DISTINCT FROM (
            r.product_name,
            r.category_code,
            r.unit_price_vnd,
            r.active_flag
        ) THEN 'UPDATE'
        ELSE 'UNCHANGED'
    END AS proposed_action,
    p.unit_price_vnd AS old_price_vnd,
    r.unit_price_vnd AS new_price_vnd,
    p.active_flag AS old_active,
    r.active_flag AS new_active
FROM demo_product_review AS r
LEFT JOIN demo_products AS p
    ON p.sku = r.sku
WHERE r.error_code IS NULL
ORDER BY r.row_no;
~~~

**Nếu chạy trước phần 12**, kết quả dự kiến:

| row_no | sku | proposed_action | old_price_vnd | new_price_vnd |
| ---: | --- | --- | ---: | ---: |
| 1 | P-100 | INSERT | NULL | 120000 |
| 3 | P-102 | INSERT | NULL | 90000 |
| 10 | P-107 | UPDATE | 160000 | 180000 |

**Nếu chạy sau phần 12**, ba SKU đã có giá trị đích tương ứng, nên có thể được phân loại **UNCHANGED**. Điều này cho thấy **preview là ảnh chụp theo thời điểm**: khi bảng đích đã thay đổi, câu trả lời "sẽ INSERT hay UPDATE" cũng thay đổi.

Trong workflow có phê duyệt lâu, cần quyết định liệu người duyệt chấp thuận **giá trị mới tuyệt đối** hay chấp thuận **một thay đổi từ giá trị cũ đã xem**. Nếu cần kiểm tra giá trị cũ, phải dùng cơ chế **optimistic concurrency** hoặc điều kiện cập nhật so với phiên bản dữ liệu đã duyệt.

## 21. INSERT ... SELECT khác INSERT ... VALUES ở quy trình staging

**INSERT ... VALUES** phù hợp cho vài hàng rõ ràng:

~~~sql
INSERT INTO demo_categories(category_code, category_name)
VALUES ('PK', 'Phu kien');
~~~

**INSERT ... SELECT** phù hợp khi dữ liệu đầu vào là một tập đã có trong bảng hoặc kết quả truy vấn:

~~~sql
-- Minh họa ý tưởng; cần áp dụng theo trạng thái và transaction phù hợp.
INSERT INTO demo_products
    (sku, product_name, category_code, unit_price_vnd, active_flag)
SELECT
    sku, product_name, category_code, unit_price_vnd, active_flag
FROM demo_product_review
WHERE error_code IS NULL
ON CONFLICT (sku) DO NOTHING;
~~~

Câu INSERT ... SELECT có thể đưa **nhiều hàng hợp lệ** vào đích bằng một lệnh, và phần SELECT có thể biểu diễn những điều kiện đủ điều kiện. Tuy nhiên, ví dụ này dùng **DO NOTHING**, khác với chính sách UPSERT cập nhật P-107 của phần 12. **Không chạy lại câu này sau khi batch PUBLISHED và coi đó là một lần nhập mới**.

**Bài học chính:** khi đã có staging, bước công bố thường là **INSERT INTO target(columns) SELECT ... FROM approved_rows**, không phải viết lại hàng loạt VALUES bằng tay.

## 22. Khi nhập dữ liệu có quan hệ cha-con

Một dạng nhập khó hơn là **đơn hàng và dòng đơn hàng**. Tệp có thể gồm:

~~~text
orders.csv:
external_order_no, customer_code, ordered_on
EXT-001, C-10, 2026-09-01

order_items.csv:
external_order_no, line_no, sku, quantity
EXT-001, 1, P-100, 2
EXT-001, 2, P-102, 1
~~~

Nếu chèn từng dòng đơn hàng trước khi đơn cha tồn tại, FOREIGN KEY có thể không cho phép. Nếu chèn đơn cha trước nhưng dòng con sai và đã COMMIT, hệ thống có thể có **đơn thiếu chi tiết**.

Một quy trình staging hợp lý:

1. Nạp **orders_raw** và **order_items_raw** gắn cùng batch_id.
2. Kiểm tra **mã đơn ngoài**, khách hàng, SKU, quantity, số dòng và quy tắc không trùng **(external_order_no, line_no)**.
3. Kiểm tra **mỗi dòng hàng có đơn cha trong batch hoặc bảng đích**.
4. Quyết định **đơn vị chấp nhận**: toàn bộ batch, từng đơn, hay từng nhóm nghiệp vụ.
5. Trong transaction, ghi đơn cha trước và tạo **bảng ánh xạ mã đơn ngoài → order_id nội bộ**.
6. Ghi dòng con theo order_id đã được ánh xạ.
7. Chỉ COMMIT khi các ràng buộc và đối soát của toàn đơn vị nhập đạt yêu cầu.

Ví dụ hình dung:

~~~text
stg_orders             ─► validated_orders    ─► orders(id)
external_order_no                              │
                                               │ mapping
stg_order_items        ─► validated_items     ─► order_items(order_id)
external_order_no + line_no
~~~

**Không ghép dòng con vào đơn bằng cách đoán thứ tự auto-increment.** Nếu bảng đích cấp khóa nội bộ, cần dùng **RETURNING** của PostgreSQL hoặc một bảng/CTE ánh xạ đáng tin cậy dựa trên khóa nguồn. Trong PostgreSQL, các lệnh INSERT có thể dùng **RETURNING** để thu nhận hàng đã ghi, nhưng cách liên kết lại với khóa nguồn cần được thiết kế rõ; đừng giả định ID tự tăng của các hàng sẽ tương ứng trực tiếp thứ tự file.

### 22.1. Chính sách PARTIAL phải chọn đúng ranh giới

Giả sử đơn EXT-001 có hai dòng hàng nhưng dòng thứ hai sai SKU. Nếu chính sách PARTIAL áp theo **dòng CSV**, hệ thống có thể nhập đơn chỉ còn dòng thứ nhất, làm sai tổng tiền hoặc số lượng. Với loại dữ liệu này, chính sách an toàn hơn có thể là **từ chối toàn bộ đơn EXT-001**, đồng thời vẫn cho phép nhập một đơn EXT-002 hoàn toàn hợp lệ.

Vì vậy, **đơn vị được duyệt** không nhất thiết là một hàng staging; có thể là **một đơn hàng, hợp đồng, hồ sơ, giao dịch hoặc nhóm liên quan**.

## 23. Kiểm tra ngày, số và encoding trong dữ liệu nhập

Đọc tất cả trường raw thành TEXT giúp giữ được giá trị nguồn, nhưng cần một **hợp đồng định dạng** cho từng trường.

### 23.1. Ngày tháng

Giả sử nguồn gửi ngày dạng ISO **YYYY-MM-DD**. Có thể dùng kiểm tra định dạng rồi chuyển kiểu, nhưng chỉ regex không đủ đảm bảo ngày tồn tại:

~~~text
2026-02-28  → ngày hợp lệ
2026-02-31  → nhìn đúng mẫu chữ số, nhưng ngày không tồn tại
~~~

Trên PostgreSQL, thao tác CAST sai ngày có thể báo lỗi. Khi cần phân loại **từng dòng lỗi ngày** mà không hủy cả batch, cân nhắc một hàm chuyển đổi an toàn với xử lý exception ở lớp ứng dụng hoặc stored procedure được thiết kế cho dữ liệu nhập. Không chỉ dùng regex rồi giả định CAST sẽ luôn thành công.

### 23.2. Số thập phân

Kiểu **NUMERIC(12,2)** phù hợp với tiền cần độ chính xác thập phân. Không nên dùng FLOAT/DOUBLE chỉ vì nguồn là chuỗi số, rồi so sánh chính xác tiền ở ngưỡng thập phân.

Phải phân biệt **giá không hợp lệ về định dạng** với **giá hợp lệ nhưng không được phép**. Trong ví dụ:

- 'abc' → INVALID_PRICE.
- '0' → NON_POSITIVE_PRICE.
- '90000' → giá 90000.00 hợp lệ.

### 23.3. Encoding và khoảng trắng đặc biệt

Văn bản tiếng Việt có thể chứa ký tự Unicode, dấu cách không ngắt (non-breaking space), ký tự điều khiển hoặc dữ liệu không theo chuẩn nguồn. BTRIM mặc định không phải một giải pháp làm sạch mọi ký tự Unicode có thể nhìn giống khoảng trắng.

Nếu hợp đồng dữ liệu yêu cầu chuẩn Unicode hoặc loại ký tự điều khiển, cần xây dựng quy tắc kiểm tra riêng, cân nhắc ảnh hưởng đến mã định danh. **Không thay đổi tự động những trường nhạy cảm hoặc khóa nghiệp vụ nếu chưa biết hậu quả.**

## 24. Kiểm soát số dòng và đối soát sau mỗi bước

Một quy trình nhập cần đối soát:

~~~text
Tổng hàng raw
    = hàng chấp nhận + hàng bị từ chối

Hàng chấp nhận
    = hàng mới + hàng cập nhật + hàng đã có giá trị giống nhau
      (theo quy tắc publish thực tế)
~~~

Trong ví dụ:

~~~text
Raw:                   10 dòng
Chấp nhận:              3 dòng
Từ chối:                7 dòng
INSERT mới:             2 SKU
UPDATE đã tồn tại:      1 SKU
Tổng SKU sau publish:   3 SKU
~~~

**Không nhầm số hàng hợp lệ với số INSERT mới.** Một hàng hợp lệ có thể cập nhật SKU đã có; một hàng được phép nhưng mọi cột giống đích có thể không tạo một UPDATE thực tế do điều kiện IS DISTINCT FROM.

Một số phép đối soát:

~~~sql
SELECT
    (SELECT COUNT(*) FROM demo_product_stage
     WHERE batch_id = 'CAT-2026-09-A') AS raw_count,
    (SELECT COUNT(*) FROM demo_product_review
     WHERE error_code IS NULL) AS valid_count,
    (SELECT COUNT(*) FROM demo_product_review
     WHERE error_code IS NOT NULL) AS invalid_count,
    (SELECT COUNT(*) FROM demo_product_rejections
     WHERE batch_id = 'CAT-2026-09-A') AS recorded_rejections;
~~~

Trong thực hành **review chỉ chứa một batch**, nên hai COUNT ở bảng review không cần thêm batch_id để ra số đúng. Nhưng trong thiết kế nhiều batch, **mọi phép đối soát phải lọc cùng batch_id**; không nên dựa vào bảng review tình cờ chỉ có dữ liệu của một lần nhập.

### 24.1. Không tổng hợp sai khi một bản ghi có nhiều lý do lỗi

Ví dụ chính lưu **một error_code mỗi hàng**, nên số dòng lỗi bằng số hàng từ chối. Nếu hệ thống lưu **nhiều lỗi cho một hàng**, COUNT(*) trên bảng errors có thể lớn hơn số hàng bị từ chối. Khi đó, cần đếm:

~~~sql
COUNT(DISTINCT (batch_id, row_no))
~~~

theo cú pháp phù hợp với PostgreSQL, hoặc nhóm theo khóa hàng rồi đếm. Phải phân biệt **số thông báo lỗi** với **số dòng không đạt**.

## 25. Hiệu năng: khi staging có hàng triệu dòng

Với tệp nhỏ, một bảng tạm và vài SELECT là đủ. Khi dữ liệu lên tới hàng triệu hoặc hàng chục triệu hàng, cần cân nhắc:

- **Bulk import** bằng COPY hoặc giao thức tương đương thay vì gửi từng INSERT nhỏ.
- Phân vùng hoặc đánh chỉ mục staging theo **batch_id** khi nhiều batch lưu cùng lúc.
- Chọn kiểu raw phù hợp, tránh lưu các payload lớn không cần thiết.
- Thực hiện chuẩn hóa/tổng hợp theo tập (set-based), tránh lặp truy vấn riêng cho từng hàng.
- Kiểm tra duplicate bằng khóa chuẩn hóa và chiến lược sắp xếp/hash phù hợp.
- Kiểm soát dữ liệu đầu vào trước khi JOIN nhiều bảng tham chiếu.
- Lựa chọn kích thước transaction, tác động WAL, lock, deadlock và thời gian giữ khóa.
- Theo dõi tỷ lệ reject, thời gian validation, thời gian publish và số hàng thực ghi.

### 25.1. Chỉ mục trên staging và bảng đích

Với staging nhiều batch:

~~~sql
-- Gợi ý trên bảng staging bền vững có nhiều batch:
CREATE INDEX idx_stage_batch_sku
ON staging.product_rows (batch_id, raw_sku);
~~~

Chỉ mục này có thể giúp tìm các hàng của batch, nhưng vì **raw_sku cần chuẩn hóa bằng UPPER/BTRIM**, một chỉ mục thông thường trên raw_sku không nhất thiết tối ưu cho tra cứu theo sku chuẩn hóa. Với hệ thống lớn, có thể thêm **cột chuẩn hóa được lưu rõ** hoặc expression index theo nhu cầu.

Trên bảng đích demo_products, PRIMARY KEY(sku) đã tạo cơ chế chỉ mục duy nhất phục vụ ON CONFLICT. Không cần thêm một chỉ mục giống hệt trên sku chỉ để "cho chắc".

**Lưu ý:** đoạn SQL trên dùng một bảng staging.product_rows **giả định đã tồn tại** như ở phần 14; không dùng để thực thi trên bộ bảng TEMP của bài mà chưa tạo schema tương ứng.

### 25.2. Transaction quá lớn

Một transaction gồm hàng triệu UPDATE có thể giữ nhiều khóa, tạo WAL và ảnh hưởng độ trễ ứng dụng. Tuy nhiên, tách ngẫu nhiên thành nhiều COMMIT có thể phá chính sách all-or-nothing.

Cần chọn **ranh giới atomicity** theo yêu cầu:

- Nếu phải **tất cả cùng thành công**, transaction lớn hoặc một thiết kế publish thay thế phải đảm bảo không công bố một phần.
- Nếu được phép **theo từng đơn vị độc lập**, có thể nhập từng batch nhỏ hoặc từng nhóm nghiệp vụ có audit rõ ràng.
- Nếu chuẩn bị bảng dữ liệu mới toàn bộ, có thể xem xét **build-and-swap** hoặc cơ chế thay phiên bản bảng theo đặc thù hệ quản trị, sau khi xác minh ràng buộc và thời điểm chuyển đổi.

Không chọn kích thước commit chỉ dựa vào số hàng; cần xét **yêu cầu nhất quán và khả năng phục hồi**.

### 25.3. EXPLAIN

~~~sql
EXPLAIN
SELECT
    batch_id,
    sku,
    COUNT(*) AS sku_rows
FROM demo_product_review
GROUP BY batch_id, sku
HAVING COUNT(*) > 1;
~~~

Trong PostgreSQL có thể quan sát phép quét và HashAggregate/GroupAggregate theo kế hoạch. **EXPLAIN ANALYZE** thực thi truy vấn để đo số liệu thật, vì vậy nên sử dụng trên dữ liệu đại diện và trong phạm vi kiểm soát khi câu truy vấn có thể tốn tài nguyên.

**Bài toán chính là tính đúng và công bố an toàn; tối ưu hóa phải dựa vào kế hoạch và dữ liệu đo được.**

## 26. Khác biệt theo hệ quản trị SQL

Khái niệm **staging → validate → approve → publish** có thể áp dụng ở nhiều hệ, nhưng cú pháp nạp file, UPSERT và bảng tạm khác nhau.

| Chủ đề | PostgreSQL | MySQL 8.0 | SQL Server | SQLite | Oracle Database |
| --- | --- | --- | --- | --- | --- |
| Bảng tạm | CREATE TEMP TABLE | CREATE TEMPORARY TABLE | #temp table hoặc tempdb | CREATE TEMP TABLE | Global/private temporary table theo phiên bản |
| Nạp file hàng loạt | COPY, psql \copy | LOAD DATA | BULK INSERT/BCP | Cơ chế import CLI/ứng dụng | SQL*Loader/external tables |
| UPSERT | **ON CONFLICT ... DO UPDATE** | **ON DUPLICATE KEY UPDATE** | UPDATE+INSERT/thiết kế MERGE có kiểm soát | **ON CONFLICT ... DO UPDATE** | **MERGE** hoặc cách cập nhật/chèn tương ứng |
| Bắt đầu transaction | BEGIN | START TRANSACTION | BEGIN TRANSACTION | BEGIN TRANSACTION | Giao dịch theo ngữ nghĩa Oracle |
| Kết thúc | COMMIT/ROLLBACK | COMMIT/ROLLBACK | COMMIT/ROLLBACK | COMMIT/ROLLBACK | COMMIT/ROLLBACK |
| Đếm có FILTER | COUNT(*) FILTER (WHERE ...) | Thường dùng SUM(CASE ...) | Thường dùng SUM(CASE ...) | FILTER ở các phiên bản hỗ trợ | CASE theo cú pháp phù hợp |

### 26.1. PostgreSQL: ON CONFLICT

~~~sql
INSERT INTO demo_products
    (sku, product_name, category_code, unit_price_vnd, active_flag)
SELECT
    sku, product_name, category_code, unit_price_vnd, active_flag
FROM demo_product_review
WHERE error_code IS NULL
ON CONFLICT (sku) DO UPDATE
SET
    product_name = EXCLUDED.product_name,
    unit_price_vnd = EXCLUDED.unit_price_vnd,
    category_code = EXCLUDED.category_code,
    active_flag = EXCLUDED.active_flag;
~~~

Mẫu này là cách viết set-based. Với hệ sản xuất, bổ sung điều kiện cập nhật, trạng thái batch và transaction như phần 12. Không dùng đoạn này để tự ý công bố lại batch sau khi đã PUBLISHED.

### 26.2. MySQL: ON DUPLICATE KEY UPDATE

MySQL hỗ trợ cơ chế **INSERT ... ON DUPLICATE KEY UPDATE** khi xung đột khóa unique/primary. Cú pháp tham chiếu giá trị đầu vào và các quy tắc xử lý xung đột có thể khác theo phiên bản MySQL 8.0; cần chọn cách tham chiếu hợp lệ trong phiên bản đang dùng.

Mẫu ý tưởng:

~~~sql
-- MySQL 8.0: dùng bảng staging/target tương ứng và cú pháp phù hợp phiên bản.
INSERT INTO products (sku, product_name, unit_price_vnd)
SELECT sku, product_name, unit_price_vnd
FROM accepted_products
ON DUPLICATE KEY UPDATE
    product_name = VALUES(product_name),
    unit_price_vnd = VALUES(unit_price_vnd);
~~~

**VALUES(column)** trong mệnh đề này là cú pháp cũ, đã bị khuyến cáo không nên dùng trong một số phiên bản MySQL 8.0 mới; khi viết code mới hãy đối chiếu tài liệu phiên bản để chọn alias/cách tham chiếu được hỗ trợ. Ví dụ chỉ nhằm minh họa khác biệt với **EXCLUDED** của PostgreSQL, không phải khuyến nghị sao chép nguyên mẫu vào hệ thống mới.

MySQL dùng **LOAD DATA** để nạp lượng lớn dữ liệu trong những trường hợp phù hợp. Phải chú ý encoding, escape, quyền file, cấu hình an toàn và transaction của engine lưu trữ.

### 26.3. SQL Server

SQL Server thường dùng:

~~~sql
BEGIN TRANSACTION;

-- Kiểm tra batch và lấy lock phù hợp.
-- UPDATE các sản phẩm tồn tại và INSERT các sản phẩm chưa tồn tại.
-- Ghi audit và trạng thái batch.

COMMIT TRANSACTION;
~~~

SQL Server có **MERGE**, nhưng với các yêu cầu đồng thời và tính đúng cao cần thiết kế điều kiện và mức khóa/cô lập cẩn thận, không mặc định MERGE tự xử lý mọi race condition. Có thể dùng UPDATE và INSERT được bảo vệ bằng transaction/unique constraint và cơ chế khóa phù hợp.

Khi tải file, **BULK INSERT** hoặc **BCP** có thể hữu ích. Bảng tạm dạng **#name** và khả năng truy cập giữa các phiên không giống bảng TEMP của PostgreSQL.

### 26.4. SQLite

SQLite hỗ trợ INSERT ... ON CONFLICT ... DO UPDATE ở các phiên bản hiện đại. Có thể dùng bảng TEMP để staging trong một kết nối, nhưng cơ chế concurrency và import file khác PostgreSQL.

Ví dụ ý tưởng:

~~~sql
INSERT INTO products (sku, product_name, unit_price_vnd)
SELECT sku, product_name, unit_price_vnd
FROM accepted_products
WHERE TRUE
ON CONFLICT(sku) DO UPDATE SET
    product_name = excluded.product_name,
    unit_price_vnd = excluded.unit_price_vnd;
~~~

**WHERE TRUE** trong ví dụ INSERT ... SELECT của SQLite giúp tránh một trường hợp mơ hồ phân tích cú pháp giữa JOIN/ON và UPSERT khi SELECT không có WHERE. Đây là chi tiết phương ngữ, không cần chèn WHERE TRUE vào PostgreSQL.

### 26.5. Oracle Database

Oracle thường dùng **MERGE** để đồng bộ dữ liệu nguồn với bảng đích, với điều kiện khớp và các nhánh UPDATE/INSERT. Mẫu:

~~~sql
-- Minh họa Oracle với hai bảng giả định:
MERGE INTO products p
USING accepted_products s
ON (p.sku = s.sku)
WHEN MATCHED THEN
    UPDATE SET p.product_name = s.product_name,
               p.unit_price_vnd = s.unit_price_vnd
WHEN NOT MATCHED THEN
    INSERT (sku, product_name, unit_price_vnd)
    VALUES (s.sku, s.product_name, s.unit_price_vnd);
~~~

Nguồn **accepted_products** phải có tối đa một bản ghi cho mỗi SKU hoặc theo khóa khớp thích hợp để tránh cập nhật không xác định. Cơ chế global/private temporary tables và kiểm soát commit của Oracle khác PostgreSQL; cần xem tài liệu phiên bản khi triển khai.

**Bất kể phương ngữ, các câu hỏi thiết kế vẫn giống nhau:** batch nào, dòng nào, lỗi gì, ai duyệt, ghi những gì, ghi trong transaction nào, và làm sao biết việc ghi đã hoàn tất.

## 27. Những lỗi thường gặp

| Lỗi | Hậu quả | Cách phòng tránh |
| --- | --- | --- |
| Ghi thẳng CSV vào bảng chính | Một dòng sai làm hỏng lệnh hoặc công bố dữ liệu chưa duyệt | Dùng raw staging |
| Ép kiểu trước khi phân loại | Giá 'abc' gây lỗi CAST cả truy vấn | Validate định dạng trước CAST |
| Chuẩn hóa sau khi kiểm tra trùng | Bỏ sót 'P-101' và ' p-101 ' | Normalize trước khi đếm duplicate |
| Coi staging TEXT là dữ liệu hợp lệ | Giá/cờ/danh mục có thể sai | Tách staging và validated rows |
| Chỉ dựa FOREIGN KEY khi publish | Khó báo lỗi từng dòng trước công bố | Kiểm tra tham chiếu + giữ FK ở đích |
| Không lưu batch_id/row_no | Không biết dòng nguồn gây lỗi | Khóa truy vết theo batch và số dòng |
| Gặp duplicate rồi tự chọn một dòng | Có thể dùng giá khác ý định đối tác | Định nghĩa chính sách trùng |
| Dùng ON CONFLICT để xử lý trùng ngay trong SELECT nguồn | Có thể lỗi khi cùng hàng đích bị tác động nhiều lần | Đảm bảo tối đa một nguồn/khóa |
| Nhập một phần nhưng ghi nhãn “toàn batch thành công” | Báo cáo sai trạng thái và đối soát | Thống kê accepted/rejected và policy |
| Cập nhật status PUBLISHED ở transaction khác | Có thể dữ liệu đích và batch lệch nhau | Ghi đích + audit + status cùng transaction |
| Duyệt một snapshot rồi âm thầm sửa raw | Nội dung công bố không còn là nội dung đã duyệt | Version/checksum, khóa nội dung, revalidate |
| Retry khi không biết COMMIT đã thành công | Có thể lặp side effect | Đọc lại batch status, idempotency key |
| Dùng TEMP cho quy trình duyệt nhiều phiên | Người duyệt không nhìn thấy dữ liệu sau khi kết nối import đóng | Dùng staging bền vững |
| Hai worker cùng xử lý batch | Công bố trùng hoặc cập nhật đua nhau | Lock batch, kiểm tra lại status |
| Hai batch cập nhật cùng SKU theo thứ tự bất kỳ | Giá cuối lệ thuộc worker chạy sau | Quy tắc version/effective date |
| Chấp nhận từng dòng item của một đơn | Đơn cha có thể thiếu dòng hợp lệ | Chọn đơn vị atomicity theo nghiệp vụ |
| Xóa staging ngay khi publish | Không điều tra được dòng bị từ chối | Lưu audit và retention phù hợp |
| Tưởng COPY tự kiểm tra nghiệp vụ | COPY chỉ nạp dữ liệu theo cấu trúc/kiểu bảng đích | Chuẩn hóa, validate và approve riêng |
| Thêm chỉ mục giống hệt PRIMARY KEY | Dư thừa và tăng chi phí ghi | Xem chỉ mục có sẵn |
| Không kiểm tra số lượng nguồn | Có thể thiếu hàng nhưng vẫn báo thành công | Đối soát expected_rows và actual_rows |

## 28. Bài tập thực hành

Các bài tập dưới đây sử dụng bộ bảng tạm **demo_*** từ phần 4. Nếu đã chạy công bố batch A, hãy dùng batch_id khác cho một lần nhập mới; không âm thầm sửa batch đã PUBLISHED.

1. Chỉ ra những cột nào trong **demo_product_stage** được giữ dạng TEXT và lý do không dùng NUMERIC/BOOLEAN ngay từ đầu.
2. Liệt kê 10 dòng raw của CAT-2026-09-A theo row_no. Dòng nào có giá không phải số?
3. Viết SELECT chuẩn hóa SKU bằng UPPER(BTRIM()) và NULLIF(). Hai giá trị SKU của dòng 2 và 4 sau chuẩn hóa là gì?
4. Viết biểu thức CASE chuyển raw_active thành BOOLEAN với các giá trị được chấp nhận. Dòng 9 sẽ nhận kết quả gì?
5. Viết CASE chỉ CAST giá khi regex hợp lệ. Phân biệt INVALID_PRICE và NON_POSITIVE_PRICE.
6. Dùng COUNT(*) OVER (PARTITION BY batch_id, sku) tìm SKU trùng trong batch. Vì sao phải dùng SKU chuẩn hóa?
7. Kiểm tra category_code của mỗi dòng so với demo_categories bằng EXISTS/NOT EXISTS. Dòng 5 bị từ chối vì lý do gì?
8. Tạo bảng review theo các CTE normalized, parsed, counted, validated. Kiểm tra tổng 10 dòng, 3 dòng hợp lệ và 7 dòng lỗi.
9. GROUP BY error_code để thống kê số dòng theo loại lỗi. Lỗi nào có 2 dòng?
10. JOIN review với bảng raw trên (batch_id, row_no) để trả row_no, raw_unit_price, sku đã chuẩn hóa và error_code của các dòng lỗi.
11. Viết truy vấn preview hành động INSERT/UPDATE/UNCHANGED khi so dòng hợp lệ với bảng đích. Vì sao P-107 là UPDATE trước khi công bố?
12. Mô phỏng người duyệt chấp nhận chính sách PARTIAL: chuyển batch từ STAGED sang APPROVED, nhưng chưa sửa demo_products.
13. Viết một transaction ghi rejection, UPSERT valid rows và đổi status thành PUBLISHED. Kiểm tra 2 SKU mới, 1 SKU cập nhật và 7 rejection.
14. Sau công bố, chạy SELECT kiểm tra P-107 có tên/giá/active_flag mới. Vì sao không có P-101?
15. Thử lại publish khi batch đã PUBLISHED. Giải thích vì sao phải bị chặn bởi trạng thái thay vì chỉ tin vào ON CONFLICT.
16. Nếu chuyển import_policy từ PARTIAL sang STRICT trước khi phê duyệt, batch A có được phép publish không? Vì sao?
17. Tạo batch B chỉ gồm ba dòng hợp lệ. Thiết kế cách kiểm tra **expected_rows = actual_rows** trước khi duyệt.
18. Tạo hai dòng cùng sku trong batch B nhưng giá khác nhau. Viết truy vấn dùng ROW_NUMBER để chọn hàng cuối, sau đó thảo luận liệu nghiệp vụ có thực sự cho phép cách giải quyết đó không.
19. Giả sử hai batch đồng thời cập nhật P-107 với hai giá khác nhau. Hãy nêu một cách bảo đảm phiên bản nguồn mới hơn được ưu tiên.
20. Giải thích tại sao CREATE TEMP TABLE không phù hợp nếu người tải CSV và người duyệt ở hai kết nối khác nhau cách nhau vài giờ.
21. Viết ví dụ \copy bằng psql để nạp các cột raw; giải thích đường dẫn file được đọc từ client hay database server.
22. Thiết kế bảng import_audit gồm batch_id, source_checksum, approved_by, approved_at, published_at và các số đếm. Cột nào cần khóa duy nhất?
23. Giả sử nguồn có một ngày không hợp lệ 2026-02-31. Vì sao regex định dạng ngày là chưa đủ để CAST an toàn?
24. Cho hai file orders và order_items, đề xuất mức chấp nhận là **từng đơn** hay **từng dòng**; giải thích tác động nếu một dòng item sai SKU.
25. Chọn một mẫu UPSERT trên MySQL, SQL Server, SQLite hoặc Oracle, rồi ghi rõ điểm khác PostgreSQL ON CONFLICT.
26. Nêu ba rủi ro nếu một lệnh COMMIT đã thành công nhưng ứng dụng không nhận được phản hồi, và cách dùng batch_id/status để xử lý retry.

### Câu hỏi tự kiểm tra

**Câu 1.** Một dòng đã nằm trong staging có được coi là sản phẩm hợp lệ và sẵn sàng phục vụ nghiệp vụ chưa?

**Đáp án:** **Chưa.** Staging chỉ xác nhận đã nhận dữ liệu. Cần chuẩn hóa, kiểm tra và phê duyệt trước khi ghi vào bảng đích.

**Câu 2.** Vì sao giữ raw_unit_price dưới dạng TEXT?

**Đáp án:** Để có thể lưu/điều tra giá sai như 'abc' và gắn lỗi theo hàng, thay vì để phép CAST sang NUMERIC làm toàn bộ thao tác đọc hoặc nạp thất bại trước khi có báo cáo.

**Câu 3.** Nếu hai dòng sau chuẩn hóa cùng SKU nhưng giá khác nhau, ON CONFLICT có tự quyết định giá nào đúng không?

**Đáp án:** **Không.** Phải có quy tắc trùng trong batch. Một câu UPSERT PostgreSQL còn có thể báo lỗi khi cùng một hàng đích bị tác động nhiều lần.

**Câu 4.** Có thể phê duyệt dữ liệu bằng cách chạy COMMIT không?

**Đáp án:** **Không.** COMMIT là thao tác transaction. Phê duyệt là quyết định quyền/nghiệp vụ, phải được kiểm soát riêng và thực hiện trước khi publish.

**Câu 5.** Nếu batch yêu cầu STRICT nhưng có một dòng sai, có được áp dụng những dòng còn lại không?

**Đáp án:** **Không.** Chính sách STRICT đòi hỏi toàn batch đạt yêu cầu trước khi công bố.

**Câu 6.** Một batch đã PUBLISHED, client mất kết nối và thử gửi lại. Chỉ PRIMARY KEY(sku) có đủ bảo đảm không có tác dụng phụ ngoài ý muốn không?

**Đáp án:** **Không.** Cần xem batch_id/status, audit, transaction và những side effect liên quan; không chỉ dựa vào khóa sản phẩm.

**Câu 7.** Tại sao bảng đích vẫn cần FOREIGN KEY/CHECK dù staging đã kiểm tra?

**Đáp án:** Vì việc kiểm tra trước có thể lỗi, bị bỏ qua hoặc trở nên cũ do dữ liệu thay đổi đồng thời. Ràng buộc bảng đích là lớp bảo vệ toàn vẹn tại thời điểm ghi.

**Câu 8.** Tại sao số hàng hợp lệ có thể khác số hàng INSERT mới?

**Đáp án:** Vì hàng hợp lệ có thể cập nhật SKU đã có hoặc không tạo thay đổi khi dữ liệu giống đích. Ví dụ batch A có 3 dòng hợp lệ nhưng chỉ thêm 2 SKU mới và cập nhật 1 SKU.

**Câu 9.** Khi dữ liệu có orders và order_items, chấp nhận từng dòng item có luôn phù hợp không?

**Đáp án:** **Không.** Có thể tạo đơn thiếu chi tiết. Nên chọn đơn vị chấp nhận theo toàn đơn hoặc tập nghiệp vụ cần nhất quán.

## 29. Ghi nhớ cốt lõi

**Nạp dữ liệu qua bảng trung gian trước khi xác nhận** là cách giữ ranh giới rõ ràng giữa **nguồn chưa tin cậy** và **bảng nghiệp vụ được công bố**:

~~~text
Nhận raw → Chuẩn hóa → Kiểm tra → Preview → Phê duyệt
                                                 |
                                                 v
                            BEGIN → INSERT/UPSERT + audit
                                                 |
                                                 v
                                    COMMIT → PUBLISHED
~~~

**Staging không tự thay thế ràng buộc của bảng đích**, và **COMMIT không tự thay thế phê duyệt nghiệp vụ**. Một import an toàn cần khóa batch, số dòng nguồn, lý do từ chối, chính sách STRICT/PARTIAL, biện pháp chống trùng SKU, transaction bao trùm các cập nhật liên quan và cơ chế chạy lại có kiểm soát.

Trong PostgreSQL, bộ công cụ thường dùng là **CREATE TEMP/CREATE TABLE staging**, **COPY hoặc INSERT**, **WITH/CASE/CAST có điều kiện**, **INSERT ... SELECT**, **ON CONFLICT**, **BEGIN/COMMIT/ROLLBACK** và ràng buộc **PRIMARY KEY/FOREIGN KEY/CHECK**. Với quy trình nhiều người hoặc kéo dài qua nhiều kết nối, dùng **bảng staging và audit bền vững**, lưu phiên bản/checksum dữ liệu đã được duyệt, và tránh công bố từ một snapshot đã thay đổi.

Mục tiêu không chỉ là “nạp được bao nhiêu hàng”, mà còn là **biết chính xác những hàng nào đã được chấp nhận, tại sao các hàng khác bị loại, ai cho phép áp dụng và hệ thống đã công bố kết quả nào một cách nhất quán**.
