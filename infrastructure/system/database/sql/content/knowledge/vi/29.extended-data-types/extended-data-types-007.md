# Cập nhật một phần tài liệu JSON theo hệ quản trị trong SQL

Một hồ sơ khách hàng có thể lưu các thuộc tính linh hoạt trong một cột JSON:

~~~json
{
  "ten": "An",
  "dia_chi": {
    "thanh_pho": "Hà Nội",
    "quan": "Ba Đình"
  },
  "cai_dat": {
    "chu_de": "sang",
    "nhan_email": true
  },
  "diem": 12,
  "tags": ["web", "vip"]
}
~~~

Người dùng chỉ đổi giao diện từ `"sang"` sang `"toi"`. Nếu ứng dụng đọc toàn bộ JSON, sửa một thuộc tính rồi ghi lại cả tài liệu, chương trình có thể phải truyền nhiều dữ liệu không cần thiết và có nguy cơ **ghi đè thay đổi đồng thời** của một yêu cầu khác. Nhiều hệ quản trị hỗ trợ câu SQL cập nhật **một đường dẫn (*path*)** trong tài liệu JSON:

~~~sql
-- PostgreSQL:
UPDATE ho_so_khach
SET tai_lieu = jsonb_set(
    tai_lieu,
    '{cai_dat,chu_de}',
    to_jsonb('toi'::text)
)
WHERE id = 101;
~~~

Nhưng không có **một cú pháp thống nhất** cho mọi DBMS. PostgreSQL dùng `jsonb_set` và các toán tử `jsonb`; MySQL có `JSON_SET`/`JSON_REPLACE`/`JSON_REMOVE`; SQL Server có `JSON_MODIFY`; Oracle có `JSON_TRANSFORM` và `JSON_MERGEPATCH`; SQLite có `json_set`/`json_insert`/`json_remove`/`json_patch`.

Bài học thuộc **Database SQL → Dữ liệu mở rộng → Cập nhật một phần tài liệu JSON theo hệ quản trị**. Mục tiêu là biết **chọn hàm đúng cho mục đích thêm/sửa/xóa, xử lý key thiếu và JSON null, thao tác mảng, cập nhật an toàn khi có nhiều người dùng**, đồng thời không nhầm **cập nhật một phần về logic** với **ghi một phần ở mức lưu trữ vật lý**.

## 1. Vì sao dữ liệu JSON cần thao tác cập nhật theo đường dẫn?

JSON phù hợp với một số dữ liệu có cấu trúc thay đổi theo sản phẩm: cài đặt cá nhân, thuộc tính sản phẩm biến thiên, metadata sự kiện, cấu hình tích hợp, payload từ hệ thống ngoài. Tuy nhiên, nhiều thuộc tính thường được sửa riêng lẻ.

Ví dụ một request:

~~~text
Đổi chủ đề sang "toi"
~~~

không nhất thiết cần đọc/ghi lại:

~~~text
Tên, địa chỉ, thiết bị, lịch sử, tag,
các thuộc tính bổ sung của toàn hồ sơ.
~~~

Câu SQL lý tưởng thể hiện **đúng ý định**:

~~~text
Tìm hàng có id = 101 và đúng tổ chức
  → thay giá trị tại $.cai_dat.chu_de
  → giữ nguyên các nhánh không liên quan về mặt logic
  → kiểm tra phiên bản nếu cần
  → COMMIT như một transaction SQL
~~~

### 1.1. Hai nghĩa của “cập nhật một phần”

| Khái niệm | Ý nghĩa | Có tự suy ra từ câu SQL cập nhật path không? |
| --- | --- | --- |
| **Logical partial update** | Chỉ sửa/thêm/xóa những nhánh JSON được chỉ định | Thường **có** nếu hàm được dùng đúng |
| **Physical partial update** | Engine ghi lại ít byte hơn toàn bộ JSON ở tầng lưu trữ | **Không bảo đảm** |
| **Partial binary logging/replication** | Log hoặc truyền các thay đổi JSON dưới dạng delta | Cần cơ chế và cấu hình riêng |
| **Optimistic concurrency** | Phát hiện việc người khác sửa hàng kể từ khi mình đọc | **Không tự có** chỉ vì dùng JSON_SET |
| **JSON Patch** | Định dạng thao tác theo tiêu chuẩn RFC 6902 | **Không đồng nghĩa** hàm JSON_SET của DBMS |

Ví dụ `jsonb_set` ở PostgreSQL diễn tả **thay một giá trị logic** nhưng vẫn tham gia cơ chế MVCC và có thể tạo **phiên bản hàng mới**; không có lời hứa “chỉ thay vài byte tại vị trí cũ trên đĩa”.

### 1.2. Khi nào không nên đặt thuộc tính trong JSON?

Các cột được JOIN, lọc theo chỉ mục và kiểm tra nghiệp vụ ở phần lớn truy vấn—ví dụ `to_chuc_id`, `khach_hang_id`, `trang_thai`, `so_du`—thường nên là **cột quan hệ có kiểu rõ**. JSON không thay thế khóa ngoại, CHECK, UNIQUE, thiết kế quan hệ và transaction.

Một mô hình kết hợp rất thường gặp:

~~~sql
CREATE TABLE ho_so_khach (
    id BIGINT PRIMARY KEY,
    to_chuc_id INTEGER NOT NULL,
    phien_ban BIGINT NOT NULL DEFAULT 0,
    tai_lieu JSONB NOT NULL
);
~~~

Các khóa nghiệp vụ cốt lõi nằm ở **cột SQL**, còn `tai_lieu` chứa thuộc tính mở rộng. Đây là điểm xuất phát của các ví dụ PostgreSQL tiếp theo.

## 2. Hiểu path, object, array, giá trị và sự vắng mặt

Đường dẫn xác định vị trí cần chỉnh sửa trong tài liệu.

~~~json
{
  "cai_dat": {
    "chu_de": "sang",
    "nhan_email": true
  },
  "tags": ["web", "vip"]
}
~~~

| Vị trí | PostgreSQL `text[]` path | SQL/JSON-style path ở MySQL/SQL Server/SQLite/Oracle |
| --- | --- | --- |
| Chủ đề | `'{cai_dat,chu_de}'` | `'$.cai_dat.chu_de'` |
| Nhận email | `'{cai_dat,nhan_email}'` | `'$.cai_dat.nhan_email'` |
| Tag đầu tiên | `'{tags,0}'` | `'$.tags[0]'` |
| Tag thứ hai | `'{tags,1}'` | `'$.tags[1]'` |
| Toàn nhánh cài đặt | `'{cai_dat}'` | `'$.cai_dat'` |
| Một key top-level | `'{ten}'` | `'$.ten'` |

**Không nhầm cú pháp:** PostgreSQL `jsonb_set` nhận path **mảng TEXT**, không phải string `'$.cai_dat.chu_de'`. Ngược lại, `JSON_SET` MySQL và `json_set` SQLite dùng path string bắt đầu từ `$`.

### 2.1. Chỉ số phần tử mảng thường bắt đầu từ 0

Với:

~~~json
"tags": ["web", "vip"]
~~~

`tags[0]` là `"web"` và `tags[1]` là `"vip"`. Chỉ số mảng **không phải ID ổn định**: khi chèn hoặc xóa phần tử trước nó, chỉ số của phần tử khác sẽ thay đổi.

### 2.2. Bốn trạng thái dễ nhầm

Trong ứng dụng SQL+JSON cần tách rõ:

1. **Key vắng mặt:** `{"ten":"An"}` không có thuộc tính `biet_danh`.
2. **Giá trị JSON null:** `{"biet_danh":null}` có key nhưng giá trị là JSON null.
3. **SQL NULL:** giá trị không có ở tầng cột/biểu thức SQL; ví dụ kết quả tìm path không tồn tại có thể là SQL NULL.
4. **Chuỗi "null":** `{"biet_danh":"null"}` chứa bốn ký tự chữ, khác JSON null.

Các hàm JSON trong mỗi DBMS có quy tắc khác nhau với SQL NULL/JSON null. Không chuyển đổi qua lại bằng suy đoán. Khi bài toán cần **xóa thuộc tính**, nên dùng **hàm xóa đường dẫn** của DBMS thay vì mặc định truyền SQL NULL vào hàm đặt giá trị.

### 2.3. Object và array khác nhau về “cập nhật”

- **Object** chứa các cặp key/value; cập nhật một key có thể thay giá trị của key đó.
- **Array** chứa các phần tử có thứ tự; cập nhật chỉ số là **thay một phần tử**, không phải tìm theo business key.
- **Thêm vào cuối array** khác với **thay phần tử tại vị trí cuối hiện tại**.
- **Xóa một phần tử array** có thể khiến chỉ số sau đó thay đổi.
- **Thay cả object** khác với **trộn các key trong object**; một số toán tử gộp JSON chỉ là *shallow merge*.

## 3. Dữ liệu thực hành PostgreSQL tự chứa

Sử dụng một **schema riêng trên database thử nghiệm**, không chạy trên production. Cần quyền tạo schema/bảng. Tên schema `bai366` được chọn để tách khỏi các bài thực hành khác.

~~~sql
CREATE SCHEMA bai366;

CREATE TABLE bai366.ho_so (
    id BIGINT PRIMARY KEY,
    to_chuc_id INTEGER NOT NULL,
    tai_lieu JSONB NOT NULL,
    phien_ban BIGINT NOT NULL DEFAULT 0
        CHECK (phien_ban >= 0),
    cap_nhat_luc TIMESTAMPTZ NOT NULL
        DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT ck_tai_lieu_la_object
        CHECK (jsonb_typeof(tai_lieu) = 'object')
);

CREATE INDEX idx_ho_so_to_chuc
ON bai366.ho_so (to_chuc_id, id);

INSERT INTO bai366.ho_so
    (id, to_chuc_id, tai_lieu)
VALUES
(
    101,
    10,
    '{
      "ten": "An",
      "dia_chi": {
        "thanh_pho": "Hà Nội",
        "quan": "Ba Đình"
      },
      "cai_dat": {
        "chu_de": "sang",
        "nhan_email": true
      },
      "diem": 12,
      "tags": ["web", "vip"],
      "thiet_bi": [
        {"id":"dt-an","loai":"dien_thoai","da_tin_cay":true},
        {"id":"lap-an","loai":"laptop","da_tin_cay":false}
      ]
    }'::jsonb
),
(
    102,
    10,
    '{
      "ten":"Bình",
      "dia_chi":{"thanh_pho":"Đà Nẵng"},
      "cai_dat":{"chu_de":"toi","nhan_email":false},
      "diem":0,
      "tags":[],
      "thiet_bi":[]
    }'::jsonb
),
(
    103,
    20,
    '{
      "ten":"Chi",
      "cai_dat":{},
      "tags":["app"],
      "thiet_bi":[]
    }'::jsonb
);

SELECT
    id,
    to_chuc_id,
    phien_ban,
    tai_lieu #>> '{cai_dat,chu_de}' AS chu_de,
    tai_lieu #>> '{dia_chi,thanh_pho}' AS thanh_pho
FROM bai366.ho_so
ORDER BY id;
~~~

Kết quả logic ban đầu:

| id | to_chuc_id | phien_ban | chu_de | thanh_pho |
| ---: | ---: | ---: | --- | --- |
| 101 | 10 | 0 | sang | Hà Nội |
| 102 | 10 | 0 | toi | Đà Nẵng |
| 103 | 20 | 0 | NULL (path không có) | NULL (nhánh không có) |

Ba JSON documents cố ý khác nhau:

- Hồ sơ 101 đầy đủ nhánh, có hai tags và hai thiết bị.
- Hồ sơ 102 có mảng rỗng và nhánh cài đặt có sẵn.
- Hồ sơ 103 **không có `dia_chi`**, dùng để xem điều kiện tạo nhánh trung gian.

**Quy ước thử nghiệm:** các thao tác UPDATE mẫu thường đặt trong `BEGIN ... ROLLBACK`, vì mục tiêu là quan sát thay đổi **trong transaction** mà không làm lệch dữ liệu đầu bài. Khi muốn giữ thay đổi, dùng COMMIT có chủ đích; không chạy tất cả ví dụ rồi kỳ vọng hồ sơ luôn trở về phiên bản 0 nếu đã COMMIT trước đó.

## 4. Trước khi cập nhật: đọc JSON với kiểu đúng

PostgreSQL có các toán tử giúp quan sát dữ liệu:

~~~sql
SELECT
    id,
    tai_lieu -> 'cai_dat' AS cai_dat_json,
    tai_lieu ->> 'ten' AS ten_text,
    tai_lieu #> '{dia_chi,thanh_pho}' AS thanh_pho_json,
    tai_lieu #>> '{dia_chi,thanh_pho}' AS thanh_pho_text
FROM bai366.ho_so
ORDER BY id;
~~~

Phân biệt:

| Toán tử | Đầu ra | Ví dụ |
| --- | --- | --- |
| `->` | JSONB tại key/chỉ số trực tiếp | `tai_lieu -> 'tags'` |
| `->>` | TEXT ở key/chỉ số trực tiếp | `tai_lieu ->> 'ten'` |
| `#>` | JSONB ở đường dẫn nhiều cấp | `tai_lieu #> '{cai_dat,chu_de}'` |
| `#>>` | TEXT ở đường dẫn nhiều cấp | `tai_lieu #>> '{cai_dat,chu_de}'` |
| `?` | Kiểm tra key hoặc string element ở **cấp top-level** của giá trị JSONB bên trái | `tai_lieu ? 'cai_dat'` |
| `jsonb_typeof` | Kiểu JSON ở vị trí đang xét | `jsonb_typeof(tai_lieu->'tags')` |

Với key vắng mặt, các toán tử truy cập path thường trả **SQL NULL**. Với JSON null có thực, biểu thức `#>` cho giá trị JSONB `null`, trong khi `#>>` chuyển thành SQL TEXT/NULL theo ngữ nghĩa truy xuất scalar.

### 4.1. Đừng dùng ->> để xây giá trị JSON mới

`tai_lieu ->> 'tags'` biến JSON array thành TEXT trình bày, không phải JSON array có cấu trúc. Nếu muốn nối mảng, lấy `tai_lieu -> 'tags'` (JSONB), không lấy `->>` rồi nối chuỗi.

### 4.2. Kiểm tra kiểu JSON trước khi làm phép toán

~~~sql
SELECT
    id,
    jsonb_typeof(tai_lieu->'diem') AS kieu_diem,
    jsonb_typeof(tai_lieu->'tags') AS kieu_tags,
    jsonb_typeof(tai_lieu->'dia_chi') AS kieu_dia_chi
FROM bai366.ho_so
ORDER BY id;
~~~

Khi path không tồn tại, `jsonb_typeof(SQL NULL)` trả SQL NULL; với JSON null thực, kết quả TEXT là `'null'`. Đây là cách hữu ích để phân biệt **absent** và **JSON null**.

## 5. PostgreSQL: jsonb_set cập nhật giá trị ở một path

Cú pháp cốt lõi:

~~~sql
jsonb_set(
    target      jsonb,
    path        text[],
    new_value   jsonb,
    create_if_missing boolean DEFAULT true
)
~~~

Câu UPDATE an toàn hơn nên có cả **phạm vi tổ chức** và khóa hàng:

~~~sql
BEGIN;

UPDATE bai366.ho_so
SET
    tai_lieu = jsonb_set(
        tai_lieu,
        '{cai_dat,chu_de}',
        to_jsonb('toi'::text),
        false
    ),
    phien_ban = phien_ban + 1,
    cap_nhat_luc = clock_timestamp()
WHERE id = 101
  AND to_chuc_id = 10
RETURNING
    id,
    phien_ban,
    tai_lieu #>> '{cai_dat,chu_de}' AS chu_de_moi;

ROLLBACK;
~~~

Trong transaction, `chu_de_moi = 'toi'` và `phien_ban = 1`. Sau ROLLBACK, bản ghi quay về giá trị cũ và phiên bản cũ.

**Giải nghĩa đối số:**

- `tai_lieu`: tài liệu JSONB hiện có.
- `'{cai_dat,chu_de}'`: path hai cấp, được chuyển thành `text[]`.
- `to_jsonb('toi'::text)`: chuyển chuỗi SQL thành **JSON string** `"toi"`.
- `false`: **không tạo key mới** nếu phần cuối path chưa tồn tại.
- `WHERE id=101 AND to_chuc_id=10`: không cập nhật hồ sơ ngoài phạm vi tổ chức.

### 5.1. create_if_missing = true và false

~~~sql
-- Có thể tạo key 'ngon_ngu' chưa có trong object cai_dat.
SELECT jsonb_set(
    '{"cai_dat":{"chu_de":"sang"}}'::jsonb,
    '{cai_dat,ngon_ngu}',
    '"vi"'::jsonb,
    true
) AS co_key_moi;

-- Không tạo key vì create_if_missing=false.
SELECT jsonb_set(
    '{"cai_dat":{"chu_de":"sang"}}'::jsonb,
    '{cai_dat,ngon_ngu}',
    '"vi"'::jsonb,
    false
) AS khong_them_key;
~~~

Kết quả logic:

~~~json
{"cai_dat":{"chu_de":"sang","ngon_ngu":"vi"}}
~~~

và:

~~~json
{"cai_dat":{"chu_de":"sang"}}
~~~

**Đừng nhầm:** `create_if_missing=true` không có nghĩa PostgreSQL sẽ tự tạo **mọi object trung gian chưa tồn tại** trong path dài.

### 5.2. Vì sao phải dùng to_jsonb?

~~~sql
SELECT
    to_jsonb('toi'::text) AS chuoi_json,
    to_jsonb(12::integer) AS so_json,
    to_jsonb(true::boolean) AS bool_json;
~~~

Kết quả JSON tương ứng là `"toi"`, `12`, `true`, **khác kiểu dữ liệu**. Nếu truyền `'"12"'::jsonb` thì đó là **chuỗi**, không phải số 12.

Các câu sau có khác biệt rõ:

~~~sql
SELECT
    jsonb_set('{}'::jsonb, '{diem}', '12'::jsonb) AS diem_la_so,
    jsonb_set('{}'::jsonb, '{diem}', '"12"'::jsonb) AS diem_la_chuoi;
~~~

Không nối chuỗi JSON bằng tay từ input người dùng để tự tạo `"..."`. Hãy bind tham số đúng kiểu và dùng `to_jsonb` hoặc các JSON construction functions.

## 6. PostgreSQL: khi nhánh cha chưa tồn tại

Hồ sơ 103 không có `dia_chi`. Nếu chạy:

~~~sql
SELECT jsonb_set(
    '{"ten":"Chi"}'::jsonb,
    '{dia_chi,thanh_pho}',
    '"Huế"'::jsonb,
    true
);
~~~

kết quả vẫn là tài liệu gốc. Lý do: `jsonb_set` không tự tạo các bước **trung gian** của path khi nhánh cha chưa tồn tại.

### 6.1. Cách đơn giản: thêm cả object cha

~~~sql
BEGIN;

UPDATE bai366.ho_so
SET tai_lieu = jsonb_set(
    tai_lieu,
    '{dia_chi}',
    jsonb_build_object('thanh_pho', 'Huế'),
    true
)
WHERE id = 103
  AND to_chuc_id = 20
  AND NOT (tai_lieu ? 'dia_chi')
RETURNING id, tai_lieu->'dia_chi' AS dia_chi;

ROLLBACK;
~~~

Trong transaction, `dia_chi` là object chứa `thanh_pho = "Huế"`. Điều kiện `NOT (tai_lieu ? 'dia_chi')` giúp tránh ghi đè một object đã tồn tại.

### 6.2. Cách tổng quát: đảm bảo object trung gian

Nếu nghiệp vụ muốn cập nhật thành phố nhưng **giữ các key khác trong địa chỉ hiện có**:

~~~sql
BEGIN;

UPDATE bai366.ho_so
SET tai_lieu = jsonb_set(
    CASE
        WHEN jsonb_typeof(tai_lieu->'dia_chi') = 'object'
            THEN tai_lieu
        WHEN NOT (tai_lieu ? 'dia_chi')
            THEN jsonb_set(
                tai_lieu,
                '{dia_chi}',
                '{}'::jsonb,
                true
            )
        ELSE tai_lieu
    END,
    '{dia_chi,thanh_pho}',
    to_jsonb('Huế'::text),
    true
)
WHERE id = 103
  AND to_chuc_id = 20
  AND (
      NOT (tai_lieu ? 'dia_chi')
      OR jsonb_typeof(tai_lieu->'dia_chi') = 'object'
  )
RETURNING id, tai_lieu->'dia_chi' AS dia_chi;

ROLLBACK;
~~~

Ví dụ này chỉ cho phép tạo object khi **key vắng mặt**, hoặc cập nhật object đã có. Nếu `dia_chi` tồn tại nhưng là JSON string/number/null/array, nó **không âm thầm thay kiểu dữ liệu**; hàng ấy không khớp WHERE.

**Nguyên tắc:** xử lý key thiếu và sai kiểu theo hợp đồng rõ ràng. Không tự ghi đè một giá trị bất ngờ bằng `{}` chỉ để UPDATE không báo lỗi.

## 7. PostgreSQL: xóa key khác với đặt JSON null

Hai mong muốn:

- “Bỏ hoàn toàn biệt danh” → **xóa thuộc tính**.
- “Đã xác nhận biệt danh chưa biết” → **giữ key, giá trị JSON null**.

### 7.1. Xóa key bằng #- và -

~~~sql
SELECT
    '{"ten":"An","dia_chi":{"thanh_pho":"Hà Nội","quan":"Ba Đình"}}'::jsonb
        #- '{dia_chi,quan}' AS bo_quan;

SELECT
    '{"ten":"An","ghi_chu":"kiem_tra"}'::jsonb
        - 'ghi_chu' AS bo_key_cap_cao_nhat;
~~~

`#-` xóa phần tử tại **path nhiều cấp**. `- 'ghi_chu'` xóa key trực tiếp ở **object top-level** (hoặc dùng nghĩa tương ứng trên array nếu operand khác). Không đồng nhất hai toán tử khi path nhiều cấp.

Ứng dụng:

~~~sql
BEGIN;

UPDATE bai366.ho_so
SET tai_lieu = tai_lieu #- '{dia_chi,quan}'
WHERE id = 101 AND to_chuc_id = 10
RETURNING tai_lieu->'dia_chi' AS dia_chi_sau_xoa;

ROLLBACK;
~~~

Địa chỉ giữ `thanh_pho` nhưng không còn `quan`.

### 7.2. Ghi JSON null có chủ đích

~~~sql
SELECT jsonb_set(
    '{"ten":"An"}'::jsonb,
    '{biet_danh}',
    'null'::jsonb,
    true
) AS co_key_null;
~~~

Kết quả:

~~~json
{"ten":"An","biet_danh":null}
~~~

Kiểm tra sự khác nhau:

~~~sql
SELECT
    '{"biet_danh":null}'::jsonb ? 'biet_danh' AS key_ton_tai,
    jsonb_typeof(
        '{"biet_danh":null}'::jsonb -> 'biet_danh'
    ) AS kieu_json,
    '{}'::jsonb ? 'biet_danh' AS key_vang_mat;
~~~

Kết quả lần lượt: `true`, `'null'`, `false`.

### 7.3. jsonb_set_lax và SQL NULL

PostgreSQL các phiên bản hỗ trợ `jsonb_set_lax` cho phép chọn hành vi khi **new_value là SQL NULL**:

~~~sql
SELECT jsonb_set_lax(
    '{"biet_danh":"An A."}'::jsonb,
    '{biet_danh}',
    NULL::jsonb,
    true,
    'delete_key'
) AS da_xoa;
~~~

`'delete_key'` là một chính sách có thể chọn; các lựa chọn khác của `jsonb_set_lax` có thể xử lý SQL NULL thành JSON null, trả target không đổi hoặc ném lỗi. Đây là tính năng PostgreSQL ở các phiên bản phù hợp (được giới thiệu từ PostgreSQL 14); không dùng nếu version đang vận hành chưa hỗ trợ.

**Không truyền SQL NULL vào `jsonb_set` thông thường rồi kỳ vọng nó xóa key.** Hãy dùng `#-`/`-` hoặc `jsonb_set_lax` với chính sách rõ ràng.

## 8. PostgreSQL: cập nhật nhiều path

`jsonb_set` sửa **một path cho mỗi lần gọi**. Muốn đổi cả chủ đề và cài đặt nhận email trong **một UPDATE**, lồng các hàm:

~~~sql
BEGIN;

UPDATE bai366.ho_so
SET tai_lieu = jsonb_set(
    jsonb_set(
        tai_lieu,
        '{cai_dat,chu_de}',
        to_jsonb('toi'::text),
        true
    ),
    '{cai_dat,nhan_email}',
    to_jsonb(false::boolean),
    true
)
WHERE id = 101
  AND to_chuc_id = 10
RETURNING
    id,
    tai_lieu->'cai_dat' AS cai_dat_moi;

ROLLBACK;
~~~

Mỗi lần `jsonb_set` trả một JSONB document mới ở mức biểu thức SQL. Lần bên ngoài nhận kết quả lần bên trong; đây là một **biểu thức duy nhất trong UPDATE**, không phải hai transaction.

### 8.1. Tránh nhầm với toán tử ||

PostgreSQL có toán tử `jsonb || jsonb` để nối/gộp **ở cấp trên cùng**, không thực hiện recursive deep merge cho mọi object lồng.

~~~sql
SELECT
    '{"cai_dat":{"chu_de":"sang","nhan_email":true}}'::jsonb
    ||
    '{"cai_dat":{"chu_de":"toi"}}'::jsonb
    AS gop_cap_cao_nhat;
~~~

Kết quả:

~~~json
{"cai_dat":{"chu_de":"toi"}}
~~~

Key `nhan_email` **bị mất** vì toàn object `cai_dat` ở phía phải đã thay thế object cùng key ở phía trái. Đây là **shallow merge**, không phải cập nhật riêng `cai_dat.chu_de`.

Nếu mục tiêu là giữ `nhan_email`, dùng `jsonb_set` với path cụ thể, hoặc xây dựng một phép merge sâu có semantics được xác định rõ.

### 8.2. Xây object JSON từ dữ liệu SQL

~~~sql
SELECT jsonb_build_object(
    'chu_de', 'toi',
    'nhan_email', false,
    'so_mau', 3
) AS object_json;
~~~

`jsonb_build_object` giúp tạo object đúng kiểu hơn việc nối chuỗi JSON. Nhưng nếu dùng nó để thay **toàn nhánh `cai_dat`**, các key chưa được liệt kê có thể bị mất—dù phép xây JSON là hợp lệ.

## 9. PostgreSQL: thao tác array theo vị trí

Tài liệu của An có:

~~~json
"tags": ["web", "vip"]
~~~

### 9.1. Thay một phần tử

~~~sql
BEGIN;

UPDATE bai366.ho_so
SET tai_lieu = jsonb_set(
    tai_lieu,
    '{tags,1}',
    '"khach_than_thiet"'::jsonb,
    false
)
WHERE id = 101 AND to_chuc_id = 10
RETURNING tai_lieu->'tags' AS tags_moi;

ROLLBACK;
~~~

Trong transaction, tags là:

~~~json
["web", "khach_than_thiet"]
~~~

`'{tags,1}'` trỏ đến phần tử **thứ hai**. Đây là **thay phần tử**, không phải chèn một phần tử mới vào vị trí 1.

### 9.2. Chèn phần tử trước vị trí 1

PostgreSQL có `jsonb_insert`:

~~~sql
BEGIN;

UPDATE bai366.ho_so
SET tai_lieu = jsonb_insert(
    tai_lieu,
    '{tags,1}',
    '"uu_tien"'::jsonb,
    false
)
WHERE id = 101 AND to_chuc_id = 10
RETURNING tai_lieu->'tags';

ROLLBACK;
~~~

Kết quả logic:

~~~json
["web", "uu_tien", "vip"]
~~~

Đối số cuối `false` có nghĩa **chèn trước phần tử được chỉ tới**; khi là `true`, ý nghĩa là chèn **sau** đối với vị trí mảng phù hợp.

### 9.3. Nối vào cuối array

Với JSONB arrays, `||` có semantics nối mảng:

~~~sql
BEGIN;

UPDATE bai366.ho_so
SET tai_lieu = jsonb_set(
    tai_lieu,
    '{tags}',
    (tai_lieu->'tags') || jsonb_build_array('mobile'),
    false
)
WHERE id = 101
  AND to_chuc_id = 10
  AND jsonb_typeof(tai_lieu->'tags') = 'array'
RETURNING tai_lieu->'tags';

ROLLBACK;
~~~

Kết quả:

~~~json
["web", "vip", "mobile"]
~~~

**Điều kiện kiểu rất quan trọng:** nếu `tags` vắng mặt, là JSON null hoặc là object, phép nối có thể có kết quả không mong đợi hoặc cần cách xử lý khác. Điều kiện `jsonb_typeof(...)= 'array'` làm ví dụ chỉ xử lý hồ sơ có mảng hợp lệ.

### 9.4. Xóa phần tử mảng

~~~sql
SELECT
    '{"tags":["web","vip","mobile"]}'::jsonb
        #- '{tags,1}' AS xoa_tag_thu_hai;
~~~

Kết quả:

~~~json
{"tags":["web","mobile"]}
~~~

Sau xóa, `"mobile"` chuyển từ index 2 thành index 1. Các code giữ vị trí cũ có thể cập nhật nhầm phần tử.

### 9.5. Tránh ghi trùng tag

Nếu tags là mảng các chuỗi và nghiệp vụ không cho trùng:

~~~sql
BEGIN;

UPDATE bai366.ho_so
SET tai_lieu = jsonb_set(
    tai_lieu,
    '{tags}',
    (tai_lieu->'tags') || jsonb_build_array('vip'),
    false
)
WHERE id = 101
  AND to_chuc_id = 10
  AND jsonb_typeof(tai_lieu->'tags') = 'array'
  AND NOT ((tai_lieu->'tags') ? 'vip')
RETURNING id, tai_lieu->'tags';

ROLLBACK;
~~~

Vì hồ sơ 101 đã có `"vip"`, UPDATE trả **0 hàng**. Toán tử `?` trên giá trị JSONB array có thể kiểm tra string element **ở cấp top-level của mảng ấy**. Không dùng cách này để tìm một key lồng bên trong các object con mà không xét cấu trúc.

## 10. PostgreSQL: cập nhật object trong array bằng ID thay vì vị trí

Ví dụ:

~~~json
"thiet_bi": [
  {"id":"dt-an","loai":"dien_thoai","da_tin_cay":true},
  {"id":"lap-an","loai":"laptop","da_tin_cay":false}
]
~~~

Một thao tác ngắn:

~~~sql
SELECT jsonb_set(
    '{"thiet_bi":[{"id":"dt-an","da_tin_cay":true},{"id":"lap-an","da_tin_cay":false}]}'::jsonb,
    '{thiet_bi,1,da_tin_cay}',
    'true'::jsonb,
    false
);
~~~

sửa phần tử thứ hai. Nhưng nếu mảng được reorder trước đó, vị trí 1 có thể không còn là laptop.

### 10.1. Mẫu chọn theo business key rồi dựng lại array

Khi cần tìm theo `id` của phần tử object, có thể phân rã array, sửa đúng phần tử, rồi kết hợp lại theo thứ tự gốc:

~~~sql
BEGIN;

UPDATE bai366.ho_so AS h
SET tai_lieu = jsonb_set(
    h.tai_lieu,
    '{thiet_bi}',
    (
        SELECT COALESCE(
            jsonb_agg(
                CASE
                    WHEN e.phan_tu->>'id' = 'lap-an'
                    THEN jsonb_set(
                        e.phan_tu,
                        '{da_tin_cay}',
                        'true'::jsonb,
                        true
                    )
                    ELSE e.phan_tu
                END
                ORDER BY e.vi_tri
            ),
            '[]'::jsonb
        )
        FROM jsonb_array_elements(h.tai_lieu->'thiet_bi')
             WITH ORDINALITY AS e(phan_tu, vi_tri)
    ),
    false
)
WHERE h.id = 101
  AND h.to_chuc_id = 10
  AND jsonb_typeof(h.tai_lieu->'thiet_bi') = 'array'
RETURNING h.tai_lieu->'thiet_bi';

ROLLBACK;
~~~

**Giải thích:**

- `jsonb_array_elements` mở mảng thành nhiều hàng JSONB.
- `WITH ORDINALITY` gắn số thứ tự **bắt đầu từ 1 trong kết quả SQL**, khác index JSON array bắt đầu từ 0.
- `CASE` sửa object có `id='lap-an'`.
- `jsonb_agg(... ORDER BY vi_tri)` dựng mảng và **giữ thứ tự**.
- `COALESCE(..., '[]'::jsonb)` xử lý mảng rỗng.
- `jsonb_set` gán lại nhánh `thiet_bi`.

Cách này chính xác về **business key** nhưng có thể cần **xây lại cả mảng**. Nếu mảng lớn, cập nhật thường xuyên theo ID và cần ràng buộc duy nhất, hãy cân nhắc **bảng con quan hệ `thiet_bi(khach_id, thiet_bi_id, ...)`** thay vì array JSON.

### 10.2. Phải kiểm tra phần tử đích có tồn tại không

Mẫu trên vẫn dựng lại mảng dù không có thiết bị `lap-an`. Nếu nghiệp vụ yêu cầu “không tìm thấy thì báo lỗi”, nên có điều kiện bổ sung và kiểm tra số hàng/giá trị trước-sau, không báo thành công mù quáng.

## 11. PostgreSQL: tăng một số trong JSON mà không read–modify–write ở ứng dụng

Hồ sơ 101 có:

~~~json
"diem": 12
~~~

Tăng điểm bằng SQL:

~~~sql
BEGIN;

UPDATE bai366.ho_so
SET
    tai_lieu = jsonb_set(
        tai_lieu,
        '{diem}',
        to_jsonb(((tai_lieu->>'diem')::INTEGER + 1)),
        false
    ),
    phien_ban = phien_ban + 1
WHERE id = 101
  AND to_chuc_id = 10
  AND jsonb_typeof(tai_lieu->'diem') = 'number'
RETURNING
    id,
    tai_lieu->'diem' AS diem_moi,
    phien_ban;

ROLLBACK;
~~~

Kết quả trong transaction là điểm **13**, phiên bản **1**.

**Tại sao không nên làm trong ứng dụng?**

~~~text
Client A đọc diem=12
Client B đọc diem=12
Client A ghi toàn JSON với diem=13
Client B ghi toàn JSON với diem=13
Kỳ vọng sau 2 lần +1: 14
Thực tế có thể: 13 (lost update)
~~~

Với câu UPDATE dựa trên **giá trị cột hiện tại ở database**, các cập nhật cùng hàng phải tuân theo cơ chế khóa/MVCC của DBMS; trong nhiều trường hợp nó tránh được lỗi ghi đè theo mẫu client đọc rồi gửi JSON cũ. Nhưng không xem đó là **bảo đảm cho mọi bất biến nghiệp vụ hoặc isolation level**. Nếu caller có dữ liệu đã đọc trước đó và kỳ vọng phiên bản không đổi, cần **optimistic concurrency control**.

### 11.1. Cẩn thận với dữ liệu JSON sai kiểu

`(tai_lieu->>'diem')::INTEGER` sẽ lỗi nếu giá trị không chuyển được sang integer hoặc nằm ngoài phạm vi integer. Điều kiện `jsonb_typeof(...)= 'number'` chỉ xác nhận kiểu JSON number, **không chứng minh giá trị nằm trong giới hạn INTEGER**, cũng không đảm bảo số không có phần thập phân.

Với production, cần schema validation, miền giá trị, có thể dùng NUMERIC thay INTEGER và phân loại lỗi. Không đổi kiểu từ số sang string bằng cách nối `'1'` rồi cộng theo cách của JSON.

## 12. PostgreSQL: tránh ghi đè toàn tài liệu bằng version column

Nếu ứng dụng phải đọc tài liệu, chỉnh nhiều thuộc tính rồi gửi lại, dùng một **cột phiên bản** để phát hiện cập nhật cạnh tranh.

~~~sql
BEGIN;

UPDATE bai366.ho_so
SET
    tai_lieu = jsonb_set(
        tai_lieu,
        '{cai_dat,chu_de}',
        to_jsonb('toi'::text),
        true
    ),
    phien_ban = phien_ban + 1,
    cap_nhat_luc = clock_timestamp()
WHERE id = 101
  AND to_chuc_id = 10
  AND phien_ban = 0
RETURNING
    id,
    phien_ban,
    tai_lieu #>> '{cai_dat,chu_de}' AS chu_de_moi;

ROLLBACK;
~~~

Nếu một transaction khác đã commit và tăng `phien_ban` lên 1, câu UPDATE với `phien_ban=0` sẽ ảnh hưởng **0 hàng**. Ứng dụng phải đọc lại, quyết định merge/retry hoặc báo conflict; **không coi 0 hàng là thành công**.

### 12.1. Quy tắc để version thực sự có tác dụng

- **Mọi đường ghi** có thể cạnh tranh đều phải cập nhật `phien_ban` theo cùng chính sách.
- Client giữ version của tài liệu đã đọc và truyền lại khi ghi.
- UPDATE gồm cả `id`, `to_chuc_id` và version; nếu version sai thì không ghi.
- Kiểm tra `RETURNING` hoặc affected rows.
- Nếu retry, phải tránh tác dụng phụ trùng và xem xét những chỉnh sửa đã xảy ra.
- Version chỉ bảo vệ **hàng**; nghiệp vụ nhiều hàng vẫn cần transaction/constraints/isolation.

### 12.2. SQL path update cũng có nguy cơ xung đột logic

Hai người cùng sửa `cai_dat.chu_de`: dù cả hai dùng `jsonb_set`, một người có thể ghi đè kết quả của người kia nếu không có hợp đồng giải quyết xung đột. Cập nhật theo path **giảm phạm vi sửa**, không giải quyết ý nghĩa “ai là người thắng” nếu cùng sửa một giá trị.

## 13. PostgreSQL: UPDATE nhiều hàng theo điều kiện JSON

Ví dụ đổi theme cho các hồ sơ thuộc tổ chức 10 **đang dùng theme sáng**:

~~~sql
BEGIN;

UPDATE bai366.ho_so
SET
    tai_lieu = jsonb_set(
        tai_lieu,
        '{cai_dat,chu_de}',
        '"toi"'::jsonb,
        false
    ),
    phien_ban = phien_ban + 1
WHERE to_chuc_id = 10
  AND tai_lieu #>> '{cai_dat,chu_de}' = 'sang'
RETURNING id, tai_lieu->'cai_dat' AS cai_dat;

ROLLBACK;
~~~

Trên dữ liệu ban đầu, chỉ hồ sơ **101** được chọn. Hồ sơ 102 đang là `toi` nên không sửa; hồ sơ 103 thuộc tổ chức 20.

### 13.1. Lọc JSON bằng containment

PostgreSQL JSONB hỗ trợ `@>`:

~~~sql
SELECT id
FROM bai366.ho_so
WHERE tai_lieu @> '{"cai_dat":{"chu_de":"sang"}}'::jsonb;
~~~

Câu này kiểm tra JSON bên trái chứa cấu trúc yêu cầu của JSON bên phải. Với các workload phù hợp, có thể tạo GIN index để hỗ trợ containment, nhưng không đồng nghĩa mọi loại tìm kiếm JSON đều dùng GIN hiệu quả.

### 13.2. Path update không tự giới hạn tenant

Một câu:

~~~sql
UPDATE bai366.ho_so
SET tai_lieu = jsonb_set(...);
~~~

thiếu điều kiện sẽ có thể cập nhật **tất cả các hàng**. Cần luôn kiểm tra `WHERE id`, `to_chuc_id`, phân quyền và Row-Level Security khi phù hợp. JSON path chỉ giới hạn **trường trong một tài liệu**, không giới hạn **hàng nào được cập nhật**.

## 14. MySQL: JSON_SET, JSON_REPLACE, JSON_INSERT và JSON_REMOVE

MySQL với cột kiểu `JSON` cung cấp những hàm có mục đích khác nhau:

| Hàm MySQL | Path đã tồn tại | Path cuối chưa tồn tại nhưng có thể thêm |
| --- | --- | --- |
| `JSON_SET` | **Thay giá trị** | **Thêm** khi hợp lệ |
| `JSON_REPLACE` | **Thay giá trị** | Không thêm |
| `JSON_INSERT` | Giữ giá trị cũ | **Thêm** khi hợp lệ |
| `JSON_REMOVE` | **Xóa** đường dẫn | Không làm thay đổi nếu không có path hợp lệ |
| `JSON_ARRAY_APPEND` | Thêm vào mảng tại path | Phụ thuộc path/kiểu đầu vào |
| `JSON_ARRAY_INSERT` | Chèn theo chỉ số mảng | Phụ thuộc vị trí và cấu trúc |

Đây là các hàm **MySQL**, không dùng trực tiếp trong PostgreSQL.

### 14.1. Cú pháp MySQL tự chứa

Tạo một bảng demo MySQL riêng:

~~~sql
CREATE TABLE ho_so_json_demo (
    id BIGINT PRIMARY KEY,
    to_chuc_id INT NOT NULL,
    tai_lieu JSON NOT NULL,
    phien_ban BIGINT NOT NULL DEFAULT 0
) ENGINE=InnoDB;

INSERT INTO ho_so_json_demo
    (id, to_chuc_id, tai_lieu)
VALUES
(
    101,
    10,
    JSON_OBJECT(
        'ten', 'An',
        'cai_dat', JSON_OBJECT(
            'chu_de', 'sang',
            'nhan_email', JSON_EXTRACT('true', '$')
        ),
        'tags', JSON_ARRAY('web', 'vip'),
        'diem', 12
    )
);

SELECT JSON_EXTRACT(tai_lieu, '$.cai_dat.chu_de') AS theme_json,
       JSON_UNQUOTE(
           JSON_EXTRACT(tai_lieu, '$.cai_dat.chu_de')
       ) AS theme_text
FROM ho_so_json_demo
WHERE id = 101;
~~~

`JSON_EXTRACT` trả giá trị JSON; `JSON_UNQUOTE` thuận tiện khi cần chuỗi SQL hiển thị không có dấu nháy JSON. MySQL cũng có toán tử `->` và `->>` ở những ngữ cảnh được hỗ trợ.

### 14.2. JSON_SET: thêm hoặc sửa

~~~sql
START TRANSACTION;

UPDATE ho_so_json_demo
SET tai_lieu = JSON_SET(
    tai_lieu,
    '$.cai_dat.chu_de', 'toi',
    '$.cai_dat.ngon_ngu', 'vi'
)
WHERE id = 101
  AND to_chuc_id = 10;

SELECT JSON_EXTRACT(tai_lieu, '$.cai_dat')
FROM ho_so_json_demo
WHERE id = 101;

ROLLBACK;
~~~

Câu MySQL có thể nhận **nhiều cặp path/value** trong một `JSON_SET`, không cần lồng hai hàm cho trường hợp đơn giản như PostgreSQL.

Kết quả logic mong muốn trong transaction:

~~~json
{"chu_de":"toi","nhan_email":true,"ngon_ngu":"vi"}
~~~

MySQL `JSON_SET` đánh giá những cặp path/value theo thứ tự trong cùng lời gọi; các path sau có thể chịu ảnh hưởng của thay đổi trước. Nếu các path chồng lấn nhau, cần kiểm tra kết quả, không suy rằng mọi cập nhật được áp dụng song song trên một bản JSON bất biến.

### 14.3. JSON_REPLACE và JSON_INSERT

~~~sql
SELECT
    JSON_REPLACE('{"a":1}' , '$.a', 2, '$.b', 3)
        AS replace_khong_them_b,
    JSON_INSERT('{"a":1}' , '$.a', 2, '$.b', 3)
        AS insert_khong_ghi_de_a;
~~~

Kết quả logic:

~~~json
{"a":2}
~~~

và:

~~~json
{"a":1,"b":3}
~~~

Lựa chọn rõ ràng:

- Muốn **bắt buộc đã có key để sửa** → `JSON_REPLACE` (nhưng nếu key thiếu, hàm có thể giữ nguyên JSON; ứng dụng vẫn cần phát hiện **0 tác động logic**).
- Muốn **chỉ thêm khi key chưa có** → `JSON_INSERT`.
- Muốn **thêm hoặc sửa** → `JSON_SET`.

### 14.4. JSON_REMOVE xóa thuộc tính

~~~sql
SELECT JSON_REMOVE(
    '{"cai_dat":{"chu_de":"sang","nhan_email":true}}',
    '$.cai_dat.nhan_email'
) AS cai_dat_sau_xoa;
~~~

Kết quả:

~~~json
{"cai_dat":{"chu_de":"sang"}}
~~~

MySQL không dùng hàm `JSON_REMOVE` với một giá trị mới. Nó chỉ nhận JSON document và một hay nhiều path cần xóa.

### 14.5. Tạo JSON object/array đúng kiểu

~~~sql
SELECT
    JSON_SET(
        '{"profile":{}}',
        '$.profile.flags',
        JSON_ARRAY('web','vip')
    ) AS flags_la_mang,
    JSON_SET(
        '{}',
        '$.settings',
        JSON_OBJECT('chu_de','toi')
    ) AS settings_la_object;
~~~

Nếu truyền trực tiếp một SQL string chứa các ký tự `[1,2]`, MySQL có thể lưu nó như một **JSON string**, chứ không phải array, tùy hàm/ngữ cảnh. Hãy dùng `JSON_ARRAY`, `JSON_OBJECT`, `JSON_EXTRACT`/kiểu JSON rõ ràng khi cần chèn **JSON có cấu trúc**.

### 14.6. Phụ huynh path thiếu

Nếu `$.dia_chi` chưa tồn tại hoặc có kiểu không phải object, đừng mặc định `JSON_SET(doc,'$.dia_chi.thanh_pho','Huế')` sẽ xây toàn bộ chuỗi object theo ý bạn. Việc thêm path phụ thuộc cấu trúc hiện có; path không thể thêm hợp lệ có thể bị bỏ qua.

Một đường rõ hơn là **tạo object cha trước**, rồi cập nhật key con khi cần, và kiểm tra kết quả:

~~~sql
-- Trường hợp biết chắc dia_chi còn vắng mặt:
SELECT JSON_SET(
    '{"ten":"Chi"}',
    '$.dia_chi',
    JSON_OBJECT('thanh_pho','Huế')
);
~~~

Nếu `dia_chi` đang có dữ liệu, việc thay cả object sẽ **làm mất các key khác**; phải kiểm tra trường hợp trước đó hoặc dùng cập nhật theo path con khi object cha đã có.

## 15. MySQL: mảng JSON và thêm phần tử

Mảng MySQL dùng path kiểu `$.tags[0]`, `$.tags[1]`.

### 15.1. Thay phần tử tại vị trí hiện tại

~~~sql
SELECT JSON_SET(
    '{"tags":["web","vip"]}',
    '$.tags[1]',
    'khach_than_thiet'
) AS tags_sau_sua;
~~~

Kết quả:

~~~json
{"tags":["web","khach_than_thiet"]}
~~~

### 15.2. Thêm vào cuối

~~~sql
SELECT JSON_ARRAY_APPEND(
    '{"tags":["web","vip"]}',
    '$.tags',
    'mobile'
) AS tags_moi;
~~~

Kết quả:

~~~json
{"tags":["web","vip","mobile"]}
~~~

### 15.3. Chèn tại vị trí mảng

~~~sql
SELECT JSON_ARRAY_INSERT(
    '{"tags":["web","vip"]}',
    '$.tags[1]',
    'uu_tien'
) AS tags_chen;
~~~

Kết quả:

~~~json
{"tags":["web","uu_tien","vip"]}
~~~

Không nhầm `JSON_ARRAY_INSERT` với `JSON_SET`: một hàm **chèn và dịch phần tử**, một hàm **thay giá trị tại vị trí** khi path tồn tại.

### 15.4. Xóa phần tử

~~~sql
SELECT JSON_REMOVE(
    '{"tags":["web","vip","mobile"]}',
    '$.tags[1]'
) AS tags_sau_xoa;
~~~

Kết quả:

~~~json
{"tags":["web","mobile"]}
~~~

Index của các phần tử phía sau thay đổi. Khi cùng một lời gọi có nhiều path xóa array, việc áp dụng lần lượt có thể khiến các chỉ số mới khác với chỉ số bạn nghĩ từ array ban đầu. Cần đặc biệt thận trọng với multi-remove theo index.

## 16. MySQL: khi nào partial update thực sự được tối ưu ở mức lưu trữ?

MySQL InnoDB hỗ trợ những **tối ưu cập nhật một phần JSON** trong một số trường hợp. Điều này khác với việc SQL đơn thuần có tên `JSON_SET`.

Các điều kiện quan trọng của nhóm tối ưu này gồm:

- Cột đích phải là **JSON column** thích hợp;
- UPDATE sửa cột dựa trên **giá trị hiện tại của chính cột ấy**, với các hàm được tối ưu như `JSON_SET`, `JSON_REPLACE` hoặc `JSON_REMOVE` theo giới hạn hỗ trợ;
- Tối ưu thường nhắm vào **thay/xóa giá trị đã có**, không thể mặc định thêm key/phần tử mới sẽ được ghi tại chỗ;
- Kích thước giá trị mới và **không gian có thể sử dụng** trong dạng lưu trữ có ảnh hưởng;
- Storage engine, phiên bản, kiểu thay đổi và điều kiện cụ thể quyết định việc có thực sự áp dụng tối ưu hay không.

Ví dụ một câu có **tiềm năng** hưởng lợi:

~~~sql
UPDATE ho_so_json_demo
SET tai_lieu = JSON_REPLACE(
    tai_lieu,
    '$.cai_dat.chu_de',
    'toi'
)
WHERE id = 101;
~~~

Không có nghĩa **mọi lần** chạy câu ấy đều bảo đảm thay đúng vài byte.

### 16.1. Quan sát dung lượng JSON của MySQL

Với phiên bản hỗ trợ:

~~~sql
SELECT
    JSON_STORAGE_SIZE(tai_lieu) AS bytes_luu_tru,
    JSON_STORAGE_FREE(tai_lieu) AS bytes_trong
FROM ho_so_json_demo
WHERE id = 101;
~~~

Các hàm này hỗ trợ tìm hiểu dung lượng lưu trữ nhị phân JSON và phần dung lượng giải phóng từ partial updates trong các trường hợp phù hợp. Chúng **không thay thế phép đo I/O, WAL/redo/binlog hay thời gian end-to-end**.

### 16.2. Partial update ở replication/binlog là một lớp khác

MySQL có cơ chế/cấu hình **partial JSON binary logging** trong các phiên bản và chế độ binlog phù hợp, ví dụ tùy chọn liên quan `binlog_row_value_options=PARTIAL_JSON`. Việc một câu UPDATE được viết bằng `JSON_SET` **không tự chứng minh** cả storage engine và binary log đều lưu delta tối ưu.

Cần xem tài liệu của phiên bản MySQL, chế độ binlog, khả năng replica hiểu định dạng và cấu hình ứng dụng. Không bật tùy chọn trên production chỉ dựa vào tên chức năng.

## 17. SQL Server: JSON_MODIFY trong UPDATE

SQL Server có `JSON_MODIFY(json_expression, path, newValue)` để sửa một path trong JSON document. Trong những phiên bản thường dùng, tài liệu JSON hay được lưu trong `NVARCHAR(MAX)` có ràng buộc `ISJSON`; khả năng **native JSON data type** và các đặc tính liên quan tùy phiên bản/edition.

### 17.1. Bảng demo SQL Server

~~~sql
CREATE TABLE dbo.HoSoJsonDemo (
    Id BIGINT NOT NULL PRIMARY KEY,
    ToChucId INT NOT NULL,
    TaiLieu NVARCHAR(MAX) NOT NULL,
    PhienBan BIGINT NOT NULL DEFAULT 0,
    CONSTRAINT CK_HoSoJsonDemo_IsJson CHECK (ISJSON(TaiLieu) = 1)
);

INSERT INTO dbo.HoSoJsonDemo
    (Id, ToChucId, TaiLieu)
VALUES
(
    101,
    10,
    N'{
       "ten":"An",
       "cai_dat":{"chu_de":"sang","nhan_email":true},
       "tags":["web","vip"]
    }'
);
~~~

Tất cả ví dụ trong mục SQL Server giả định sử dụng bảng này, **không dùng cú pháp PostgreSQL trên SQL Server**.

### 17.2. Sửa path đã có

~~~sql
BEGIN TRANSACTION;

UPDATE dbo.HoSoJsonDemo
SET
    TaiLieu = JSON_MODIFY(
        TaiLieu,
        '$.cai_dat.chu_de',
        N'toi'
    ),
    PhienBan = PhienBan + 1
WHERE Id = 101
  AND ToChucId = 10;

SELECT
    Id,
    JSON_VALUE(TaiLieu, '$.cai_dat.chu_de') AS ChuDe
FROM dbo.HoSoJsonDemo
WHERE Id = 101;

ROLLBACK TRANSACTION;
~~~

`JSON_MODIFY` trả JSON document sau khi cập nhật. `JSON_VALUE` dùng để lấy **scalar** dưới dạng SQL phù hợp; `JSON_QUERY` dùng cho JSON object/array fragment.

### 17.3. Lax và strict

SQL Server JSON_MODIFY hỗ trợ **path mode**:

- **lax** (thường là mặc định): có thể thêm key chưa có, và khi newValue là SQL NULL với một property object đang tồn tại, **có thể xóa property**.
- **strict**: yêu cầu path được chỉ định tồn tại trong các trường hợp phù hợp, không tự thêm key; với một object property tồn tại, SQL NULL có thể được ghi thành **JSON null** thay vì xóa.

Ví dụ minh họa với property object:

~~~sql
DECLARE @doc NVARCHAR(MAX) = N'{"biet_danh":"An A."}';

SELECT
    JSON_MODIFY(@doc, '$.biet_danh', NULL)
        AS LaxCoTheXoaKey,
    JSON_MODIFY(@doc, 'strict $.biet_danh', NULL)
        AS StrictGhiJsonNull;
~~~

Kết quả logic:

~~~json
{}
~~~

và:

~~~json
{"biet_danh":null}
~~~

**Điểm đặc biệt quan trọng:** không suy từ `JSON_MODIFY(...,NULL)` của SQL Server sang `jsonb_set(...,NULL)` của PostgreSQL hoặc `JSON_SET(...,NULL)` của MySQL. Semantics SQL NULL/JSON null **khác theo hàm và DBMS**.

### 17.4. Chèn object JSON, tránh biến object thành chuỗi

~~~sql
DECLARE @doc NVARCHAR(MAX) = N'{"ten":"Chi"}';

SELECT JSON_MODIFY(
    @doc,
    '$.dia_chi',
    JSON_QUERY(N'{"thanh_pho":"Huế"}')
) AS CoDiaChi;
~~~

`JSON_QUERY` cho SQL Server biết giá trị mới là một **JSON fragment**, không phải một chuỗi cần escape rồi đặt trong dấu nháy.

Nếu đưa trực tiếp `N'{"thanh_pho":"Huế"}'` như một string thông thường, JSON_MODIFY có thể escape nội dung và ghi thành **JSON string**, không phải object.

### 17.5. Thêm phần tử mảng bằng append

~~~sql
DECLARE @doc NVARCHAR(MAX) = N'{"tags":["web","vip"]}';

SELECT JSON_MODIFY(
    @doc,
    'append $.tags',
    N'mobile'
) AS TagsMoi;
~~~

Kết quả:

~~~json
{"tags":["web","vip","mobile"]}
~~~

`'append $.tags'` là cú pháp path mode đặc thù SQL Server. Không dùng nó làm path trong `jsonb_set` PostgreSQL hoặc `json_set` SQLite.

### 17.6. Sửa hai path bằng cách lồng JSON_MODIFY

~~~sql
UPDATE dbo.HoSoJsonDemo
SET TaiLieu = JSON_MODIFY(
    JSON_MODIFY(
        TaiLieu,
        '$.cai_dat.chu_de',
        N'toi'
    ),
    '$.cai_dat.nhan_email',
    CAST(0 AS BIT)
)
WHERE Id = 101 AND ToChucId = 10;
~~~

Khi được truyền kiểu BIT phù hợp, SQL Server diễn đạt JSON boolean tương ứng. Không truyền chuỗi `'false'` nếu nghiệp vụ yêu cầu **boolean false** thay vì JSON string.

### 17.7. Nhánh cha thiếu và sửa array

Ở lax mode, SQL Server không bảo đảm tạo được **mọi đường dẫn trung gian**. Hãy chuẩn hóa/tạo parent object có kiểm soát trước khi cập nhật child path. JSON_MODIFY có thể thay array item theo index hoặc append vào array, nhưng **xóa phần tử mà vẫn dồn các index** không có cùng cơ chế trực tiếp đơn giản như `JSON_REMOVE(...,'$.tags[1]')` ở MySQL/SQLite. Khi cần thao tác mảng phức tạp, thường phải phân rã và xây lại array qua cơ chế JSON/query phù hợp với phiên bản, hoặc lưu collection trong bảng con.

## 18. Oracle Database: JSON_TRANSFORM và JSON_MERGEPATCH

Oracle có nhiều tính năng SQL/JSON; **khả năng và cú pháp chính xác phụ thuộc phiên bản**. Với môi trường hỗ trợ `JSON_TRANSFORM`, đây là công cụ hướng tới sửa nhiều vị trí trong tài liệu.

### 18.1. JSON_TRANSFORM

Ví dụ ý tưởng trên bảng Oracle `ho_so_khach` có cột `tai_lieu` chứa tài liệu JSON hợp lệ:

~~~sql
UPDATE ho_so_khach
SET tai_lieu = JSON_TRANSFORM(
    tai_lieu,
    SET '$.cai_dat.chu_de' = 'toi',
    REMOVE '$.cai_dat.ghi_chu'
)
WHERE id = 101
  AND to_chuc_id = 10;
~~~

`JSON_TRANSFORM` dùng danh sách operations như `SET`, `REMOVE` và các operation khác được phiên bản hỗ trợ. Điều này khác PostgreSQL phải lồng `jsonb_set` nếu sửa nhiều path, và khác SQL Server `JSON_MODIFY` sửa một path trong một lời gọi.

**Lưu ý:** Oracle hỗ trợ JSON_TRANSFORM trong những phiên bản/phân nhánh từ 21c trở đi và những bản có tính năng tương ứng; cần kiểm tra tài liệu DBMS thực tế thay vì giả định mọi Oracle 19c đều có cùng câu lệnh.

### 18.2. JSON_MERGEPATCH và RFC 7396

Oracle hỗ trợ `JSON_MERGEPATCH` theo kiểu **JSON Merge Patch**. Ví dụ:

~~~sql
SELECT JSON_MERGEPATCH(
    '{"cai_dat":{"chu_de":"sang","nhan_email":true}}',
    '{"cai_dat":{"chu_de":"toi"}}'
) AS TaiLieuMoi
FROM dual;
~~~

Kết quả logic:

~~~json
{"cai_dat":{"chu_de":"toi","nhan_email":true}}
~~~

Khác toán tử `jsonb ||` PostgreSQL ở mục 8, **Merge Patch** trộn các object lồng theo quy tắc RFC 7396.

### 18.3. JSON null trong merge patch có nghĩa xóa

~~~sql
SELECT JSON_MERGEPATCH(
    '{"ten":"An","biet_danh":"An A."}',
    '{"biet_danh":null}'
) AS KhongConBietDanh
FROM dual;
~~~

Kết quả:

~~~json
{"ten":"An"}
~~~

Theo RFC 7396, **null trong patch object báo xóa key**, không phải yêu cầu đặt JSON null làm giá trị. Vì vậy Merge Patch không phải công cụ phù hợp nếu ý định là thêm key có giá trị JSON null như một giá trị giữ nguyên.

### 18.4. Mảng trong Merge Patch thường được thay cả mảng

Ví dụ:

~~~sql
SELECT JSON_MERGEPATCH(
    '{"tags":["web","vip"]}',
    '{"tags":["mobile"]}'
) AS TagsMoi
FROM dual;
~~~

Kết quả:

~~~json
{"tags":["mobile"]}
~~~

Nó **không nối thêm** `"mobile"` vào array cũ. Nếu muốn cập nhật array một phần, cần operation thích hợp như JSON_TRANSFORM được DBMS hỗ trợ hoặc thiết kế theo bảng con.

### 18.5. Oracle có khác biệt về kiểu JSON

Oracle có nhiều cách lưu dữ liệu JSON, gồm cột ký tự/LOB có kiểm tra JSON và **native JSON data type** ở những phiên bản phù hợp. Kết quả RETURNING, encoding, hỗ trợ patch/transform, tối ưu và chỉ mục có thể khác theo phiên bản. Không áp dụng nguyên cú pháp PostgreSQL `::jsonb` hay MySQL `JSON_SET` cho Oracle.

## 19. SQLite: json_set, json_insert, json_replace, json_remove

SQLite có các hàm JSON (JSON1 và các tính năng liên quan) có tên viết thường phổ biến trong tài liệu:

~~~sql
json_set(X, P1, V1, P2, V2, ...)
json_insert(X, P1, V1, ...)
json_replace(X, P1, V1, ...)
json_remove(X, P1, P2, ...)
~~~

Các tên này gần giống MySQL, nhưng **chi tiết biểu diễn JSON và quy tắc value arguments khác**. SQLite có thể lưu JSON ở TEXT hoặc SQLite JSONB tùy chức năng/phiên bản; SQLite JSONB **không tương thích nhị phân với PostgreSQL JSONB**.

### 19.1. Bảng demo SQLite

~~~sql
CREATE TABLE ho_so_json_demo (
    id INTEGER PRIMARY KEY,
    to_chuc_id INTEGER NOT NULL,
    tai_lieu TEXT NOT NULL CHECK (json_valid(tai_lieu)),
    phien_ban INTEGER NOT NULL DEFAULT 0
);

INSERT INTO ho_so_json_demo
    (id, to_chuc_id, tai_lieu)
VALUES (
    101,
    10,
    '{"ten":"An","cai_dat":{"chu_de":"sang","nhan_email":true},' ||
    '"tags":["web","vip"],"diem":12}'
);
~~~

### 19.2. json_set sửa hoặc thêm key

~~~sql
BEGIN;

UPDATE ho_so_json_demo
SET
    tai_lieu = json_set(
        tai_lieu,
        '$.cai_dat.chu_de', 'toi',
        '$.cai_dat.ngon_ngu', 'vi'
    ),
    phien_ban = phien_ban + 1
WHERE id = 101
  AND to_chuc_id = 10;

SELECT
    json_extract(tai_lieu, '$.cai_dat.chu_de') AS chu_de
FROM ho_so_json_demo
WHERE id = 101;

ROLLBACK;
~~~

Câu `json_set` có thể sửa **nhiều path** trong một lời gọi giống MySQL. Kết quả logic phần cài đặt có theme `"toi"` và thêm ngôn ngữ `"vi"`.

### 19.3. json_insert và json_replace

~~~sql
SELECT json_insert('{"a":1}', '$.a', 2, '$.b', 3);
-- {"a":1,"b":3}

SELECT json_replace('{"a":1}', '$.a', 2, '$.b', 3);
-- {"a":2}
~~~

`json_insert` không đè path đã có; `json_replace` không thêm path chưa có; `json_set` có thể làm cả hai trong trường hợp path hợp lệ.

### 19.4. Giá trị cấu trúc phải đi qua json()/json_array()

Trong SQLite, một argument value truyền trực tiếp như **SQL string** thường được hiểu là **JSON string**, ngay cả khi string trông giống JSON:

~~~sql
SELECT
    json_set('{}', '$.tags', '["web","vip"]')
        AS ChuoiKhongPhaiMang,
    json_set('{}', '$.tags', json('["web","vip"]'))
        AS MangJsonThucSu;
~~~

Kết quả logic:

~~~json
{"tags":"[\"web\",\"vip\"]"}
~~~

và:

~~~json
{"tags":["web","vip"]}
~~~

Tương tự với boolean:

~~~sql
SELECT json_set(
    '{"cai_dat":{}}',
    '$.cai_dat.nhan_email',
    json('false')
);
~~~

Đầu ra có JSON boolean `false`, không phải chuỗi `"false"`. SQLite có quy tắc đặc biệt khi value argument đến trực tiếp từ các hàm JSON hoặc toán tử JSON được nhận diện; hãy dựa vào tài liệu/hàm tạo JSON, không đoán từ nội dung chuỗi.

### 19.5. Append array bằng $[#]

SQLite hỗ trợ path `$[#]` biểu diễn vị trí **sau phần tử cuối** trong ngữ cảnh phù hợp:

~~~sql
SELECT json_insert(
    '{"tags":["web","vip"]}',
    '$.tags[#]',
    'mobile'
) AS TagsMoi;
~~~

Kết quả:

~~~json
{"tags":["web","vip","mobile"]}
~~~

`#` trong SQLite JSON path là cú pháp đặc thù; đừng mang nguyên `'$[#]'` sang MySQL/SQL Server/Oracle mà không kiểm tra.

### 19.6. Xóa key hoặc phần tử array

~~~sql
SELECT json_remove(
    '{"cai_dat":{"chu_de":"sang","nhan_email":true}}',
    '$.cai_dat.nhan_email'
);

SELECT json_remove(
    '{"tags":["web","vip","mobile"]}',
    '$.tags[1]'
);
~~~

Kết quả logic lần lượt:

~~~json
{"cai_dat":{"chu_de":"sang"}}
~~~

và:

~~~json
{"tags":["web","mobile"]}
~~~

Array bị thu gọn, phần tử phía sau dịch vị trí.

## 20. SQLite json_patch và jsonb_* không phải PostgreSQL jsonb_set

SQLite có `json_patch(target, patch)` theo kiểu RFC 7396 Merge Patch:

~~~sql
SELECT json_patch(
    '{"cai_dat":{"chu_de":"sang","nhan_email":true}}',
    '{"cai_dat":{"chu_de":"toi"}}'
);
~~~

Kết quả logic:

~~~json
{"cai_dat":{"chu_de":"toi","nhan_email":true}}
~~~

Xóa key:

~~~sql
SELECT json_patch(
    '{"ten":"An","biet_danh":"An A."}',
    '{"biet_danh":null}'
);
-- {"ten":"An"}
~~~

Như Oracle JSON_MERGEPATCH, giá trị null trong **patch object** có ý nghĩa **xóa**, và array thường **thay nguyên mảng** chứ không sửa các chỉ số tùy ý.

### 20.1. SQLite JSONB

Ở các phiên bản SQLite hỗ trợ JSONB (giới thiệu từ SQLite 3.45), có các hàm như `jsonb_set`, `jsonb_insert`, `jsonb_replace`, `jsonb_remove` và `jsonb_patch` theo cơ chế SQLite. Nhưng:

- SQLite JSONB là **định dạng nhị phân riêng** của SQLite, không thể copy byte-for-byte vào PostgreSQL JSONB.
- SQLite `jsonb_set(X, '$.path', value)` **khác chữ ký** với PostgreSQL `jsonb_set(target, text[], jsonb, bool)`.
- Chọn họ hàm `json_*` hay `jsonb_*` cần phù hợp với kiểu dữ liệu và chain xử lý của SQLite, không suy đoán một cái luôn nhanh hơn trong mọi query.
- Tối ưu binary JSON ở SQLite không mặc nhiên giống tối ưu partial update của InnoDB.

## 21. JSON Patch (RFC 6902) và JSON Merge Patch (RFC 7396)

Hai chuẩn thường xuất hiện trong REST APIs và hệ thống trao đổi dữ liệu, nhưng **không đồng nghĩa các hàm cập nhật JSON của SQL**.

### 21.1. JSON Patch — danh sách thao tác

RFC 6902 mô tả một mảng các thao tác:

~~~json
[
  {"op":"replace","path":"/cai_dat/chu_de","value":"toi"},
  {"op":"add","path":"/tags/-","value":"mobile"},
  {"op":"remove","path":"/dia_chi/quan"},
  {"op":"test","path":"/ten","value":"An"}
]
~~~

Các thao tác tiêu biểu: `add`, `remove`, `replace`, `move`, `copy`, `test`. Path dùng **JSON Pointer**, ví dụ `/cai_dat/chu_de`, **khác** path `$.cai_dat.chu_de` của SQL/JSON hoặc text[] PostgreSQL. Trong JSON Pointer, ký tự `~` và `/` ở token có quy tắc escape `~0` và `~1`.

Một API nhận RFC 6902 patch phải **thực thi đúng thứ tự, xử lý lỗi/test, và tuân theo semantics JSON Pointer**. Không thay mảng patch bằng một lời gọi `JSON_SET` bất kỳ rồi cho rằng đã thực thi đủ tiêu chuẩn.

### 21.2. JSON Merge Patch — một tài liệu mẫu thay đổi

RFC 7396 dùng một object patch:

~~~json
{
  "cai_dat": {"chu_de": "toi"},
  "dia_chi": {"quan": null}
}
~~~

Nó diễn đạt **gộp các object lồng và xóa key khi patch value là null**. Đó là cơ sở của `JSON_MERGEPATCH` Oracle và `json_patch` SQLite.

**Giới hạn lớn:** Merge Patch không biểu đạt “thêm vào cuối array” hoặc “sửa duy nhất phần tử array có id='abc'” theo cùng cách JSON Patch; array thường được **thay cả**. Nó cũng không biểu đạt rõ “giữ key nhưng đổi thành JSON null” trong object patch, vì null có semantics xóa.

### 21.3. SQL JSON functions là một lớp khác

| Công cụ | Cú pháp path | Mục đích |
| --- | --- | --- |
| PostgreSQL `jsonb_set` | `'{cai_dat,chu_de}'::text[]` | Sửa giá trị tại path |
| MySQL `JSON_SET` | `'$.cai_dat.chu_de'` | Thêm/sửa path |
| SQL Server `JSON_MODIFY` | `'$.cai_dat.chu_de'` | Sửa path, có lax/strict/append |
| Oracle `JSON_TRANSFORM` | SQL/JSON path | Danh sách phép biến đổi theo phiên bản |
| SQLite `json_set` | `'$.cai_dat.chu_de'` | Thêm/sửa path |
| RFC 6902 JSON Patch | `'/cai_dat/chu_de'` | Chuỗi thao tác add/remove/replace/test... |
| RFC 7396 Merge Patch | Object patch lồng | Gộp object/xóa key bằng null |

Nếu API nhận một loại patch chuẩn, backend cần **chuyển đổi và kiểm tra semantics đầy đủ** trước khi áp dụng câu SQL.

## 22. Bảng so sánh các hệ quản trị

| Nhiệm vụ | PostgreSQL | MySQL | SQL Server | Oracle | SQLite |
| --- | --- | --- | --- | --- | --- |
| Đổi key có sẵn | `jsonb_set` | `JSON_SET` hoặc `JSON_REPLACE` | `JSON_MODIFY` | `JSON_TRANSFORM SET` | `json_set` hoặc `json_replace` |
| Chỉ thêm key mới | `jsonb_insert` hoặc điều kiện/path phù hợp | `JSON_INSERT` | `JSON_MODIFY` lax với điều kiện kiểm soát | `JSON_TRANSFORM INSERT` ở phiên bản phù hợp | `json_insert` |
| Xóa key | `-`, `#-`, hoặc `jsonb_set_lax` | `JSON_REMOVE` | `JSON_MODIFY` với SQL NULL/lax cho object property | `JSON_TRANSFORM REMOVE` hoặc Merge Patch null | `json_remove` hoặc json_patch null |
| Đặt JSON null | `'null'::jsonb` | Giá trị JSON null được tạo/typed phù hợp | `JSON_MODIFY` strict với property tồn tại trong ngữ cảnh tương ứng | Operation/value JSON null theo Oracle | `json('null')` |
| Thêm cuối array | Nối JSONB arrays/`jsonb_insert` theo path | `JSON_ARRAY_APPEND` | `JSON_MODIFY(...,'append $.a',...)` | JSON_TRANSFORM APPEND trong phiên bản hỗ trợ | `json_insert(...,'$.a[#]',...)` |
| Nhiều path trong một lời gọi | Lồng các `jsonb_set` | Nhiều path/value trong `JSON_SET` | Lồng `JSON_MODIFY` | Nhiều operations trong `JSON_TRANSFORM` | Nhiều path/value trong `json_set` |
| Deep merge kiểu RFC 7396 | Không phải `jsonb ||`; cần triển khai/extension phù hợp | `JSON_MERGE_PATCH` | Không có phép SQL dùng chung mọi version, cần triển khai | `JSON_MERGEPATCH` | `json_patch` |
| Giá trị JSON native | `jsonb`/`json` | `JSON` | Thường NVARCHAR JSON; native type tùy version | JSON/native hoặc text/LOB tùy version | TEXT JSON hoặc SQLite JSONB tùy version |
| Tối ưu physical partial JSON update | Không bảo đảm in-place do gọi `jsonb_set` | InnoDB có tối ưu riêng theo điều kiện | Tùy kiểu lưu/engine/version, không suy từ JSON_MODIFY | Tùy kiểu lưu/phiên bản | Không suy từ json_set/jsonb_set |
| Index truy vấn JSON | GIN, expression B-tree... | Generated/functional indexes, JSON indexing theo version | Computed/JSON index tùy version | JSON search/multivalue/function-based indexes | Expression indexes, generated columns |
| Concurrency | Transaction/MVCC + version nếu cần | InnoDB locks/MVCC + version | Lock/isolation + version | Transaction/locking + version | Transaction/writer locking + version |

Bảng này là **bản đồ lựa chọn chức năng**, không phải lời khẳng định mọi phiên bản đều hỗ trợ toàn bộ syntax. Với một triển khai thật phải đọc tài liệu và kiểm tra behavior của phiên bản, đặc biệt ở các mục **NULL, array, missing parent, transaction và physical optimization**.

## 23. Cập nhật một phần JSON và concurrency: ba tình huống khác nhau

### 23.1. Hai người sửa hai path khác nhau

~~~text
Client A sửa $.cai_dat.chu_de = "toi"
Client B sửa $.dia_chi.thanh_pho = "Huế"
~~~

Nếu cả hai gửi toàn tài liệu lấy từ bản đã đọc cũ, người ghi sau có thể **làm mất sửa đổi** của người ghi trước.

Nếu cả hai dùng SQL update path **trên cột hiện tại**, engine có thể thực thi tuần tự các update hàng theo cơ chế transaction và giữ hai sửa đổi logic, tùy isolation, điều kiện WHERE và retry. Nhưng đây vẫn là **cùng một hàng**: có thể phát sinh lock contention, serialization error hoặc xung đột khác theo DBMS.

### 23.2. Hai người sửa cùng path

~~~text
Client A: chu_de = "toi"
Client B: chu_de = "sang"
~~~

Dù dùng JSON path update, hệ thống vẫn cần policy: last writer wins, optimistic conflict, thứ tự thời gian hợp lệ, quyền của từng người hoặc merge. **Path không tự quyết định** chính sách giải quyết xung đột.

### 23.3. Một người tăng số, một người đặt lại số

~~~text
Client A: diem = diem + 1
Client B: diem = 0
~~~

Hai thao tác có **ý nghĩa không giao hoán**: thứ tự commit ảnh hưởng kết quả. Không thể chỉ nói “đều là partial update nên an toàn”. Với bộ đếm quan trọng, cần API nghiệp vụ và invariant rõ, thậm chí tách bộ đếm thành cột numeric có constraint/transaction phù hợp.

### 23.4. Optimistic concurrency pattern đa DBMS

Ý tưởng chung:

~~~sql
-- PSEUDOCODE độc lập phương ngữ, chỉ để hiểu mẫu:
UPDATE ho_so
SET tai_lieu = UPDATE_JSON_PATH(tai_lieu, path, value),
    phien_ban = phien_ban + 1
WHERE id = :id
  AND to_chuc_id = :tenant
  AND phien_ban = :version_da_doc;
~~~

Nếu affected rows = 0, có thể là không tồn tại, sai tenant hoặc conflict; ứng dụng cần phân loại an toàn theo quyền truy cập. Không mở rộng response để tiết lộ sự tồn tại của bản ghi ở tenant khác.

## 24. Transaction và tính nhất quán khi JSON liên quan bảng khác

Giả sử `tai_lieu` có:

~~~json
{"gio_hang":{"san_pham":[{"id":1,"so_luong":2}]}}
~~~

và bảng quan hệ `san_pham` có tồn kho. Việc sửa JSON giỏ hàng **không tự điều chỉnh tồn kho** và không tự tạo FK đến `san_pham.id` bên trong array.

Nếu chuyển từ giỏ hàng sang đặt hàng thật, cần một transaction:

1. Xác thực người dùng và tenant.
2. Kiểm tra giá/sản phẩm/stock từ nguồn đáng tin.
3. Trừ tồn kho bằng DML có điều kiện và kiểm tra affected rows.
4. Tạo đơn và chi tiết đơn trong bảng có FK/constraints.
5. Cập nhật trạng thái giỏ hàng hoặc JSON metadata nếu cần.
6. Ghi outbox/event cùng transaction khi phù hợp.
7. COMMIT nếu mọi bước bắt buộc hợp lệ; ROLLBACK nếu thất bại.

**Cập nhật một phần JSON không thay thế transaction qua nhiều bảng**, không thay thế FK hoặc chống oversell.

### 24.1. JSON “thuộc tính mở rộng” và JSON “nguồn sự thật”

Nếu dữ liệu JSON là **nguồn sự thật duy nhất** của một quan hệ quan trọng, cần thêm cách bảo vệ:

- Quy tắc phiên bản của schema JSON;
- Kiểm tra kiểu và key bắt buộc;
- Khả năng query/index;
- Tính duy nhất của ID trong array;
- Quan hệ với bảng khác;
- Migration khi JSON schema thay đổi;
- Công cụ đối soát/khôi phục.

Nếu quan hệ phức tạp, bảng quan hệ chuẩn hóa thường an toàn hơn mảng các object với ID nằm sâu trong JSON.

## 25. JSON path, SQL injection và kiểm soát tên thuộc tính

Một API có thể nhận input như:

~~~json
{
  "path": "$.cai_dat.chu_de",
  "value": "toi"
}
~~~

**Không nên cho phép mọi path do client cung cấp** rồi áp dụng thẳng vào bất kỳ hồ sơ nào. Kể cả khi cú pháp được bind an toàn, người dùng có thể yêu cầu sửa các trường nhạy cảm như quyền truy cập hoặc hạn mức.

### 25.1. Dùng whitelist đường dẫn nghiệp vụ

Ví dụ:

| Tên trường API được phép sửa | JSON path nội bộ | Kiểu |
| --- | --- | --- |
| `theme` | `cai_dat.chu_de` | TEXT thuộc tập {sang, toi} |
| `receiveEmail` | `cai_dat.nhan_email` | BOOLEAN |
| `city` | `dia_chi.thanh_pho` | TEXT không rỗng |
| `tags` | Không cho phép ghi cả mảng tùy tiện | Thao tác add/remove có kiểm tra |

Không nhận path như `$.quyen.admin` hoặc `$.diem` chỉ vì client biết cách viết path.

### 25.2. Bind giá trị khác với bind SQL identifier

Giá trị SQL nên được truyền bằng prepared statement/binding:

~~~sql
-- Ý tưởng tham số PostgreSQL:
UPDATE bai366.ho_so
SET tai_lieu = jsonb_set(
    tai_lieu,
    ARRAY['cai_dat', 'chu_de']::text[],
    to_jsonb($1::text),
    false
)
WHERE id = $2
  AND to_chuc_id = $3;
~~~

`$1`, `$2`, `$3` ở đây là placeholder theo cách gửi statement của PostgreSQL driver. App nên validate `$1` trong tập cho phép.

Với DBMS dùng JSON path là string, có phiên bản hỗ trợ bind path parameter trong hàm, nhưng vẫn cần xét **quy tắc path grammar, wildcard, lax/strict và các đường dẫn được phép**. Bind chống injection **không tự cấp quyền nghiệp vụ**.

### 25.3. Key JSON chứa dấu chấm, khoảng trắng hoặc ký tự đặc biệt

Một key JSON có tên `"a.b"` là **một key**, không tự tương đương hai cấp `a → b`. SQL/JSON path có cú pháp quote key đặc biệt; PostgreSQL dùng mảng path với từng segment riêng:

~~~sql
SELECT jsonb_set(
    '{"a.b":1}'::jsonb,
    ARRAY['a.b']::text[],
    '2'::jsonb,
    false
) AS updated;
~~~

Kết quả:

~~~json
{"a.b":2}
~~~

Đừng nối một string từ các segment chưa escape rồi coi nó là path đúng; phân biệt **path segments** với **tên key có dấu đặc biệt**.

## 26. JSON NULL, SQL NULL, key vắng mặt và xóa trong từng DBMS

Đây là nguồn bug nổi bật nhất khi chuyển ứng dụng:

| Ý định | PostgreSQL | MySQL | SQL Server | Oracle/SQLite |
| --- | --- | --- | --- | --- |
| Key **vắng mặt** | Kiểm tra `?` ở object hoặc path operators | `JSON_CONTAINS_PATH` theo path | `JSON_PATH_EXISTS` ở version hỗ trợ hoặc cách kiểm tra chuyên biệt | JSON_EXISTS/json_type/cơ chế phù hợp |
| Key có **JSON null** | `'null'::jsonb` | JSON value null được tạo đúng kiểu | Với object property tồn tại, JSON_MODIFY strict/NULL có semantics tương ứng | JSON value null theo operation; SQLite `json('null')` |
| **Xóa** key | `-`/`#-` hoặc jsonb_set_lax delete_key | `JSON_REMOVE` | JSON_MODIFY lax với SQL NULL cho object property | Oracle REMOVE/merge patch null; SQLite json_remove/json_patch null |
| **Không làm gì khi path thiếu** | `jsonb_set(...,false)` hoặc điều kiện WHERE | `JSON_REPLACE` | strict có thể báo lỗi nếu không có path | `json_replace` SQLite; Oracle REPLACE ở phiên bản hỗ trợ |
| **Thêm khi path thiếu** | `jsonb_set(...,true)` khi parent hợp lệ | `JSON_INSERT` hoặc JSON_SET | JSON_MODIFY lax khi có thể thêm | JSON_TRANSFORM INSERT/SET; SQLite json_insert/json_set |

**Không xây “one helper supports all databases” bằng cách đổi tên hàm mà không viết test NULL/missing riêng cho từng DBMS.**

### 26.1. Khi nào nên dùng NULL?

Quy tắc nghiệp vụ cần quyết định:

- **Không có key** = chưa cung cấp/thông tin không áp dụng?
- **JSON null** = người dùng chủ động xóa giá trị hay giá trị chưa biết?
- **SQL NULL column** = cả tài liệu không tồn tại?
- **Trạng thái chuẩn hóa** = nên có cột SQL riêng thay vì một JSON null?

Một API PATCH có thể cần phân biệt “không gửi field” và “gửi field với null”. Hợp đồng API phải xác định **null là đặt JSON null hay yêu cầu xóa**; nếu dùng RFC 7396, null trong object patch mang nghĩa xóa.

## 27. Chỉ mục và truy vấn JSON sau khi cập nhật

Partial update không miễn phí cho các index trên thuộc tính JSON. Khi giá trị trong JSON thay đổi, index biểu thức/generated column liên quan có thể cần bảo trì.

### 27.1. PostgreSQL expression index

Nếu thường lọc theo thành phố:

~~~sql
CREATE INDEX idx_ho_so_thanh_pho
ON bai366.ho_so (
    (tai_lieu #>> '{dia_chi,thanh_pho}')
);

SELECT id
FROM bai366.ho_so
WHERE tai_lieu #>> '{dia_chi,thanh_pho}' = 'Hà Nội';
~~~

B-tree expression index có thể giúp lọc scalar text. Nếu UPDATE đổi thành phố, index cũng có công việc cập nhật tương ứng.

### 27.2. PostgreSQL GIN cho containment

~~~sql
CREATE INDEX idx_ho_so_tai_lieu_gin
ON bai366.ho_so USING GIN (tai_lieu);

SELECT id
FROM bai366.ho_so
WHERE tai_lieu @> '{"cai_dat":{"chu_de":"sang"}}'::jsonb;
~~~

GIN giúp những kiểu truy vấn JSONB nhất định; không tự tối ưu mọi phép toán như `#>>` so sánh text hoặc phép sort numeric. Chọn operator class (ví dụ jsonb_ops/jsonb_path_ops) và index theo **query workload**, không chỉ vì cột là JSONB.

### 27.3. MySQL generated/functional index

MySQL có thể dùng **generated column** hoặc functional index theo phiên bản để phục vụ JSON path:

~~~sql
-- Ý tưởng MySQL: generated scalar column có thể index.
ALTER TABLE ho_so_json_demo
ADD COLUMN chu_de VARCHAR(30)
    GENERATED ALWAYS AS (
        JSON_UNQUOTE(
            JSON_EXTRACT(tai_lieu, '$.cai_dat.chu_de')
        )
    ) STORED;

CREATE INDEX idx_chu_de
ON ho_so_json_demo (chu_de);
~~~

Định nghĩa generated column phải tuân thủ version/collation/kiểu biểu thức. Nếu JSON path đổi, giá trị generated column/index cũng cần được cập nhật theo quy tắc engine.

### 27.4. SQL Server computed column

Một kỹ thuật SQL Server phổ biến:

~~~sql
ALTER TABLE dbo.HoSoJsonDemo
ADD ChuDe AS
    JSON_VALUE(TaiLieu, '$.cai_dat.chu_de');

CREATE INDEX IX_HoSoJsonDemo_ChuDe
ON dbo.HoSoJsonDemo (ChuDe);
~~~

Cần xét giới hạn độ dài giá trị khóa, collation và tính chất biểu thức; không mặc định mọi JSON_VALUE đều phù hợp đưa thẳng vào index ở production.

### 27.5. SQLite expression index

~~~sql
CREATE INDEX idx_ho_so_json_theme
ON ho_so_json_demo (
    json_extract(tai_lieu, '$.cai_dat.chu_de')
);
~~~

Đối với SQLite, biểu thức query phải tương thích với expression index để planner khai thác. Với những dữ liệu quan trọng cần lọc/JOIN thường xuyên, cân nhắc **cột scalar SQL riêng**.

### 27.6. Oracle

Oracle có **function-based indexes, JSON search indexes** và các chiến lược chuyên biệt cho SQL/JSON theo phiên bản. Chọn index dựa trên biểu thức JSON_VALUE/JSON_EXISTS/JSON_QUERY, kiểu lưu và workload; không suy rằng mọi update JSON đều bảo trì index giống nhau giữa Oracle native JSON và kiểu text/LOB.

## 28. Hiệu năng: partial patch không tự giải quyết write amplification

Đánh giá một câu JSON update nên tính các lớp:

1. **Câu SQL và số hàng:** bao nhiêu row thực sự khớp WHERE?
2. **Định dạng JSON:** TEXT, JSONB, binary JSON hay kiểu khác?
3. **Chi phí tạo kết quả JSON mới:** dựng lại nhánh hoặc mảng có kích thước bao nhiêu?
4. **Chi phí lưu trữ:** row version, page write, WAL/redo/undo, compression/TOAST/LOB?
5. **Index maintenance:** index nào trên JSON/path bị ảnh hưởng?
6. **Concurrency:** row locks, contention, retry, serialization failures?
7. **Replication:** binary log/WAL/change stream ghi delta hay full value?
8. **Ứng dụng:** client có phải gửi/nhận cả JSON không?
9. **Truy vấn sau cập nhật:** index của path mới có được dùng hiệu quả không?
10. **Tổng chi phí vận hành:** storage, backup, VACUUM/maintenance, giám sát.

### 28.1. PostgreSQL jsonb_set

PostgreSQL `jsonb_set` trả giá trị JSONB sau biến đổi; một UPDATE thường tạo **phiên bản hàng mới theo MVCC** và có thể cần xử lý lại giá trị JSONB, index và WAL tùy trường hợp. Do đó không gọi nó là một “in-place byte patch” được bảo đảm.

### 28.2. MySQL JSON_SET

MySQL/InnoDB có tối ưu cập nhật JSON nhị phân một phần **trong các điều kiện cụ thể**. Khi thêm field mới, thay giá trị lớn hơn không gian phù hợp hoặc cách viết SQL không thỏa điều kiện, engine có thể phải ghi lại nhiều hơn. Tối ưu storage và partial binary logging là **hai chủ đề khác nhau**.

### 28.3. SQL Server JSON_MODIFY

JSON_MODIFY trả một JSON document biến đổi, nhưng không tự chứng minh `NVARCHAR(MAX)` chỉ ghi một vài byte ở tầng lưu trữ. Native JSON và các tối ưu mới phụ thuộc phiên bản, nên đọc tài liệu engine và đo transaction log/CPU/I/O.

### 28.4. SQLite JSON/JSONB

SQLite `json_set` trả JSON text, `jsonb_set` trả SQLite JSONB theo nhóm hàm/version phù hợp. Không coi SQLite JSONB là PostgreSQL JSONB và cũng không kết luận JSONB luôn “partial update vật lý” chỉ từ tên hàm.

### 28.5. Đo bằng workload thật, không bằng tên function

Với PostgreSQL có thể dùng:

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
UPDATE bai366.ho_so
SET tai_lieu = jsonb_set(
    tai_lieu,
    '{cai_dat,chu_de}',
    '"toi"'::jsonb,
    false
)
WHERE id = 101;
~~~

**Cảnh báo:** `EXPLAIN ANALYZE` **thực thi thật** UPDATE. Trên database thử nghiệm, có thể bọc `BEGIN ... ROLLBACK`; tuy nhiên sequence và side effects bên ngoài transaction không nhất thiết rollback. Trong STEP 4 của bài này, ví dụ chỉ dùng để giảng giải, không yêu cầu chạy kiểm thử.

So sánh cần đo dữ liệu đại diện: độ lớn JSON, độ sâu path, tỷ lệ update, index, I/O và concurrency. Không lấy thời gian trên ba hàng demo làm benchmark production.

## 29. Quy trình thiết kế một API PATCH hồ sơ an toàn

Ví dụ API nhận:

~~~json
{
  "profileId": 101,
  "version": 7,
  "change": {
    "theme": "toi"
  }
}
~~~

Một quy trình hợp lý:

~~~mermaid
flowchart TD
    A["Nhận yêu cầu PATCH"] --> B["Xác thực caller/tenant"]
    B --> C["Validate field và kiểu"]
    C --> D["Ánh xạ field → JSON path đã cho phép"]
    D --> E["UPDATE JSON path + version trong transaction"]
    E --> F{"Affected rows?"}
    F -->|"1"| G["RETURNING giá trị mới / COMMIT"]
    F -->|"0"| H["Không tồn tại/không có quyền/conflict\nphân loại an toàn"]
    F -->|"Lỗi"| I["ROLLBACK + xử lý/retry theo loại lỗi"]
    G --> J["Trả response"]
~~~

### 29.1. Không để client gửi nguyên path tùy ý

Thay vì nhận:

~~~json
{"path":"$.quyen.admin","value":true}
~~~

nên nhận một trường API đã được whitelist:

~~~json
{"theme":"toi"}
~~~

Server tự ánh xạ sang `'{cai_dat,chu_de}'::text[]` hoặc `'$.cai_dat.chu_de'` theo DBMS, đồng thời bind tham số.

### 29.2. Có hợp đồng “không gửi” khác “gửi null”

Ví dụ:

- `{}`: không đổi theme.
- `{"theme":"toi"}`: đặt theme thành `toi`.
- `{"theme":null}`: quy định rõ là xóa key hay đặt JSON null hay bị từ chối.

Không để null vô tình thực hiện **xóa** ở SQL Server/merge patch khi API thực ra muốn giữ một key có JSON null.

### 29.3. Có version hoặc điều kiện trạng thái

Các API cộng điểm, đổi quyền, chuyển trạng thái hoặc sửa cấu hình chung cần kiểm soát xung đột, không dùng last writer wins mặc định nếu điều đó làm mất cập nhật quan trọng.

### 29.4. Đảm bảo rollback và đồng bộ hệ ngoài

Nếu việc đổi cấu hình cần phát sự kiện, có thể ghi transactional outbox trong cùng transaction rồi phát sau commit. Không gửi email/HTTP giữa UPDATE và COMMIT rồi nghĩ rollback JSON sẽ hoàn nguyên sự kiện đã gửi.

## 30. Các lỗi hay gặp khi cập nhật JSON

| Lỗi/ngộ nhận | Hậu quả | Cách làm đúng |
| --- | --- | --- |
| “jsonb_set nhận '$.a.b'.” | Sai kiểu path ở PostgreSQL | Dùng `text[]` như `'{a,b}'`. |
| “JSON_SET nào cũng dùng như nhau.” | Sai semantics giữa MySQL/SQLite và PG | Xem chữ ký từng DBMS. |
| “create_if_missing=true sẽ tạo mọi object cha.” | Path sâu không có parent có thể không đổi | Tạo/kiểm tra parent trước. |
| “JSON null giống SQL NULL.” | Ghi sai kiểu hoặc xóa key ngoài ý muốn | Phân biệt rõ literal, kiểu và hàm xóa. |
| “Đặt 'false' sẽ được JSON boolean.” | Lưu JSON string thay boolean | Dùng typed JSON boolean phù hợp DBMS. |
| “Đặt '[1,2]' là tạo array.” | Có thể tạo string chứa dấu ngoặc | Dùng JSON_ARRAY/JSON_QUERY/json()/jsonb_build_array. |
| “|| của PostgreSQL là deep merge.” | Mất key của object lồng | Dùng jsonb_set cho path cụ thể hoặc merge sâu có quy tắc. |
| “Merge Patch null là đặt JSON null.” | Xóa key theo RFC 7396 | Dùng thao tác set JSON null khác. |
| “JSON Patch path và SQL path giống nhau.” | Nhầm `/a/b` với `$.a.b` | Phân biệt RFC 6902 và SQL/JSON path. |
| “Append array và replace array element như nhau.” | Ghi đè phần tử thay vì thêm | Chọn ARRAY_APPEND/append/`$[#]`/jsonb_insert thích hợp. |
| “Array index luôn xác định đúng thiết bị.” | Reorder làm sửa nhầm object | Chọn theo ID hoặc đưa collection ra bảng con. |
| “Xóa index 1 không làm đổi index 2.” | Index sau xóa dịch chuyển | Recompute path theo trạng thái mới. |
| “Cập nhật một path không cần WHERE tenant.” | Có thể sửa dữ liệu sai tổ chức | Luôn lọc khóa và tenant. |
| “Partial update tránh mọi lost update.” | Hai client vẫn ghi đè khi cùng sửa hoặc gửi doc cũ | Dùng version, kiểm tra affected rows, transaction. |
| “UPDATE ảnh hưởng 0 hàng vẫn thành công.” | Bỏ qua conflict/không tồn tại | Kiểm tra RETURNING/ROW_COUNT. |
| “Gọi jsonb_set thì đĩa chỉ thay vài byte.” | Dự đoán I/O sai | Phân biệt logical/physical, đo engine. |
| “InnoDB JSON_SET luôn là physical partial update.” | Sai điều kiện size/path/storage | Kiểm tra điều kiện tối ưu, dùng metrics. |
| “SQLite JSONB là PostgreSQL JSONB.” | Không tương thích định dạng và chữ ký | Sử dụng API của từng engine. |
| “JSON array lưu ID thay FK.” | Không có FK/UNIQUE tự nhiên cho phần tử lồng | Chuẩn hóa khi dữ liệu quan hệ quan trọng. |
| “Thêm GIN là tối ưu mọi JSON query.” | Tốn ghi/index mà query vẫn chậm | Thiết kế index theo operator và workload. |
| “Đưa SQL NULL vào JSON_MODIFY luôn xóa mọi path.” | Lax/strict/object/array có khác biệt | Viết test và chọn thao tác rõ nghĩa. |
| “Path do client truyền là an toàn nếu bind.” | Vẫn có thể sửa key nhạy cảm | Whitelist và authorization theo field. |
| “EXPLAIN ANALYZE UPDATE chỉ mô phỏng.” | Làm thay đổi dữ liệu thật | Thực hành trên DB test, có rollback khi phù hợp. |
| “Một UPDATE JSON là một transaction hoàn chỉnh cho nhiều bảng.” | Bất biến chéo bảng có thể sai | Dùng transaction và constraints. |

## 31. Bài tập thực hành có lời giải

Các bài PostgreSQL dựa trên `bai366.ho_so` ở mục 3, trừ khi ghi rõ một hệ quản trị khác. Để tránh biến đổi dữ liệu mẫu, phần lớn câu UPDATE được bọc `BEGIN ... ROLLBACK`. Những câu SQL của MySQL, SQL Server, Oracle và SQLite **chỉ chạy trên hệ tương ứng**.

### Bài 1. Cập nhật theme có sẵn ở PostgreSQL

**Yêu cầu:** đặt theme của hồ sơ 101 thành `toi` nhưng không thêm key nếu chưa tồn tại.

~~~sql
BEGIN;

UPDATE bai366.ho_so
SET tai_lieu = jsonb_set(
    tai_lieu,
    '{cai_dat,chu_de}',
    to_jsonb('toi'::text),
    false
)
WHERE id = 101 AND to_chuc_id = 10
RETURNING tai_lieu #>> '{cai_dat,chu_de}' AS theme;

ROLLBACK;
~~~

**Đáp án:** Trong transaction, theme là `toi`. `false` không tạo key cuối nếu path chưa có.

### Bài 2. Thêm một key trong object đã tồn tại

**Yêu cầu:** thêm `cai_dat.ngon_ngu = "vi"` cho hồ sơ 101.

~~~sql
BEGIN;

UPDATE bai366.ho_so
SET tai_lieu = jsonb_set(
    tai_lieu,
    '{cai_dat,ngon_ngu}',
    '"vi"'::jsonb,
    true
)
WHERE id = 101 AND to_chuc_id = 10
RETURNING tai_lieu->'cai_dat';

ROLLBACK;
~~~

**Đáp án:** Key `ngon_ngu` được thêm vào object `cai_dat` hiện có, các key cài đặt khác vẫn giữ.

### Bài 3. Path thiếu parent

**Câu hỏi:** tại sao `jsonb_set('{"ten":"Chi"}'::jsonb, '{dia_chi,thanh_pho}', '"Huế"'::jsonb, true)` không tự tạo đủ địa chỉ?

**Đáp án:** `jsonb_set` không tự xây toàn bộ các object trung gian. Cần tạo `dia_chi` object trước hoặc áp dụng quy trình đảm bảo parent với kiểm tra kiểu dữ liệu.

### Bài 4. Xóa key lồng

**Yêu cầu:** bỏ quận khỏi địa chỉ hồ sơ 101, giữ thành phố.

~~~sql
BEGIN;

UPDATE bai366.ho_so
SET tai_lieu = tai_lieu #- '{dia_chi,quan}'
WHERE id = 101 AND to_chuc_id = 10
RETURNING tai_lieu->'dia_chi';

ROLLBACK;
~~~

**Đáp án:** Chỉ key `quan` bị loại khỏi object `dia_chi`.

### Bài 5. Giữ key nhưng đặt JSON null

**Yêu cầu:** thêm `biet_danh: null` vào hồ sơ 101.

~~~sql
SELECT jsonb_set(
    '{"ten":"An"}'::jsonb,
    '{biet_danh}',
    'null'::jsonb,
    true
);
~~~

**Đáp án:** `{"ten":"An","biet_danh":null}`, key tồn tại và có giá trị JSON null.

### Bài 6. SQL NULL có phải JSON null?

**Câu hỏi:** `jsonb_set(doc, path, NULL::jsonb)` có giống `jsonb_set(doc,path,'null'::jsonb)` không?

**Đáp án:** Không. SQL NULL là giá trị NULL của biểu thức SQL; `'null'::jsonb` là một giá trị JSONB chứa JSON null. Dùng `jsonb_set_lax` khi cần chính sách đặc biệt với SQL NULL hoặc toán tử xóa riêng.

### Bài 7. Cập nhật hai trường một lần

**Yêu cầu:** theme thành toi và nhận email thành false.

~~~sql
SELECT jsonb_set(
    jsonb_set(
        '{"cai_dat":{"chu_de":"sang","nhan_email":true}}'::jsonb,
        '{cai_dat,chu_de}',
        '"toi"'::jsonb
    ),
    '{cai_dat,nhan_email}',
    'false'::jsonb
);
~~~

**Đáp án:** Cả hai key đổi theo path, vẫn là một kết quả JSONB.

### Bài 8. Shallow merge có nguy cơ gì?

**Câu hỏi:** kết quả của `'{"a":{"x":1,"y":2}}'::jsonb || '{"a":{"x":3}}'::jsonb`?

**Đáp án:** `{"a":{"x":3}}`. Key `y` mất vì phép `||` thay object ở key a theo mức trên cùng, không recursive merge.

### Bài 9. Thay tag thứ hai

~~~sql
SELECT jsonb_set(
    '{"tags":["web","vip"]}'::jsonb,
    '{tags,1}',
    '"uu_tien"'::jsonb,
    false
);
~~~

**Đáp án:** `{"tags":["web","uu_tien"]}`; mảng không dài thêm.

### Bài 10. Chèn tag trước vị trí 1

~~~sql
SELECT jsonb_insert(
    '{"tags":["web","vip"]}'::jsonb,
    '{tags,1}',
    '"moi"'::jsonb,
    false
);
~~~

**Đáp án:** `{"tags":["web","moi","vip"]}`.

### Bài 11. Append tag vào cuối trong PostgreSQL

~~~sql
SELECT jsonb_set(
    '{"tags":["web","vip"]}'::jsonb,
    '{tags}',
    '["web","vip"]'::jsonb || '["mobile"]'::jsonb,
    false
);
~~~

**Đáp án:** `{"tags":["web","vip","mobile"]}`. Khi làm với một cột thật, có thể dùng `tai_lieu->'tags'` thay phần array hardcoded và phải kiểm tra kiểu.

### Bài 12. Xóa tag làm đổi index

**Câu hỏi:** xóa `tags[1]` khỏi `["web","vip","mobile"]` thì phần tử nào ở index 1?

**Đáp án:** `"mobile"`. Mảng mới là `["web","mobile"]`.

### Bài 13. Tăng counter

**Yêu cầu:** tăng `diem` từ 12 thành 13 bằng SQL PostgreSQL, giữ JSON number.

~~~sql
SELECT jsonb_set(
    '{"diem":12}'::jsonb,
    '{diem}',
    to_jsonb(
        (('{"diem":12}'::jsonb)->>'diem')::INTEGER + 1
    ),
    false
);
~~~

**Đáp án:** `{"diem":13}`. Trong UPDATE trên cột, lấy giá trị hiện tại từ chính cột và kiểm tra miền dữ liệu.

### Bài 14. Optimistic version

**Yêu cầu:** câu UPDATE chỉ sửa khi `phien_ban=0`.

~~~sql
BEGIN;

UPDATE bai366.ho_so
SET
    tai_lieu = jsonb_set(
        tai_lieu,
        '{cai_dat,chu_de}',
        '"toi"'::jsonb,
        true
    ),
    phien_ban = phien_ban + 1
WHERE id = 101
  AND to_chuc_id = 10
  AND phien_ban = 0
RETURNING id, phien_ban;

ROLLBACK;
~~~

**Đáp án:** Có hàng trả về khi version khớp. Nếu không có hàng, phải phân loại không tồn tại/sai quyền/conflict, không báo thành công.

### Bài 15. Lọc theo JSON trước khi UPDATE

**Yêu cầu:** chỉ đổi những hồ sơ của tổ chức 10 đang có theme sáng.

~~~sql
BEGIN;

UPDATE bai366.ho_so
SET tai_lieu = jsonb_set(
    tai_lieu,
    '{cai_dat,chu_de}',
    '"toi"'::jsonb,
    false
)
WHERE to_chuc_id = 10
  AND tai_lieu #>> '{cai_dat,chu_de}' = 'sang'
RETURNING id;

ROLLBACK;
~~~

**Đáp án:** Với dataset ban đầu, chỉ `id=101` được cập nhật.

### Bài 16. MySQL JSON_SET

**Yêu cầu:** đổi `cai_dat.chu_de` và thêm `cai_dat.ngon_ngu` trong cùng hàm.

~~~sql
SELECT JSON_SET(
    '{"cai_dat":{"chu_de":"sang"}}',
    '$.cai_dat.chu_de', 'toi',
    '$.cai_dat.ngon_ngu', 'vi'
);
~~~

**Đáp án:** `{"cai_dat":{"chu_de":"toi","ngon_ngu":"vi"}}`.

### Bài 17. MySQL JSON_REPLACE vs JSON_INSERT

**Câu hỏi:** với `{"a":1}`, JSON_REPLACE cho `$.b=2` và JSON_INSERT cho `$.a=3` có làm gì?

**Đáp án:** JSON_REPLACE không thêm b; JSON_INSERT không ghi đè a. Muốn thêm hoặc sửa, dùng JSON_SET trong trường hợp hợp lệ.

### Bài 18. MySQL thêm tag vào cuối

~~~sql
SELECT JSON_ARRAY_APPEND(
    '{"tags":["web"]}',
    '$.tags',
    'mobile'
);
~~~

**Đáp án:** `{"tags":["web","mobile"]}`.

### Bài 19. MySQL physical partial update

**Câu hỏi:** có thể kết luận JSON_SET luôn chỉ ghi vài byte vật lý không?

**Đáp án:** Không. Tối ưu của InnoDB phụ thuộc kiểu cột, hàm, path, kích thước, không gian có thể dùng và version. Cần phân biệt logic sửa một path với storage/binlog delta.

### Bài 20. SQL Server JSON_MODIFY

~~~sql
DECLARE @doc NVARCHAR(MAX) =
    N'{"cai_dat":{"chu_de":"sang"}}';

SELECT JSON_MODIFY(
    @doc,
    '$.cai_dat.chu_de',
    N'toi'
) AS Moi;
~~~

**Đáp án:** Theme đổi sang JSON string `"toi"`.

### Bài 21. SQL Server NULL và lax/strict

**Câu hỏi:** JSON_MODIFY với newValue SQL NULL cho một object property đã tồn tại khác nhau ra sao giữa lax và strict?

**Đáp án:** Với ngữ cảnh hỗ trợ, lax có thể **xóa property**, strict đặt **JSON null**. Phải kiểm tra path tồn tại và kiểu target, không khái quát cho mọi tình huống array.

### Bài 22. SQL Server chèn object

**Yêu cầu:** đặt JSON object địa chỉ thay vì string chứa dấu ngoặc.

~~~sql
SELECT JSON_MODIFY(
    N'{"ten":"Chi"}',
    '$.dia_chi',
    JSON_QUERY(N'{"thanh_pho":"Huế"}')
);
~~~

**Đáp án:** `dia_chi` là object JSON. `JSON_QUERY` giúp tránh escape như một string.

### Bài 23. Oracle Merge Patch giữ sibling key?

~~~sql
SELECT JSON_MERGEPATCH(
    '{"a":{"x":1,"y":2}}',
    '{"a":{"x":3}}'
)
FROM dual;
~~~

**Đáp án:** `{"a":{"x":3,"y":2}}` theo RFC 7396. Khác PostgreSQL `jsonb ||`.

### Bài 24. Oracle Merge Patch null

**Câu hỏi:** patch `{"a":null}` trên object đang có key a là đặt a thành JSON null hay xóa a?

**Đáp án:** **Xóa key a** theo merge patch semantics.

### Bài 25. SQLite json_set và value string

~~~sql
SELECT
    json_set('{}', '$.x', '[1,2]') AS x_la_chuoi,
    json_set('{}', '$.x', json('[1,2]')) AS x_la_mang;
~~~

**Đáp án:** Lần đầu là JSON string chứa `[1,2]`; lần sau là JSON array thực sự.

### Bài 26. SQLite thêm cuối mảng

~~~sql
SELECT json_insert(
    '{"tags":["web"]}',
    '$.tags[#]',
    'mobile'
);
~~~

**Đáp án:** `{"tags":["web","mobile"]}`. Path `[#]` là cú pháp SQLite.

### Bài 27. JSONB giữa PostgreSQL và SQLite

**Câu hỏi:** dữ liệu SQLite JSONB có thể sao chép nguyên byte vào cột PostgreSQL JSONB không?

**Đáp án:** Không. Hai định dạng JSONB là các binary representations khác nhau. Chuyển đổi qua giao diện JSON/logical value phù hợp, không coi cùng tên là tương thích file.

### Bài 28. RFC 6902 vs RFC 7396

**Câu hỏi:** cách chuẩn nào dùng `{"op":"replace","path":"/a","value":1}`; cách nào dùng `{"a":null}` để xóa key?

**Đáp án:** Mẫu đầu thuộc **JSON Patch RFC 6902**; mẫu thứ hai là **JSON Merge Patch RFC 7396**. Hai path/semantics khác nhau.

### Bài 29. Cập nhật array object theo ID

**Tình huống:** mảng thiết bị có phần tử với `id='lap-an'`, thứ tự có thể đổi. Có nên luôn dùng `thiet_bi[1]` để sửa thiết bị đó?

**Đáp án:** Không. Chỉ số mảng là vị trí, có thể đổi. Có thể dùng truy vấn tìm/rebuild theo ID với `jsonb_array_elements` và `jsonb_agg` ở PostgreSQL, hoặc chuẩn hóa thiết bị sang bảng con nếu cập nhật theo ID thường xuyên.

### Bài 30. Chọn mô hình dữ liệu

**Tình huống:** trường `han_muc_tin_dung` của khách hàng thường được lọc, có quy tắc numeric, quyền riêng và cần transaction với bảng thanh toán. Đưa vào JSON có phải luôn hợp lý?

**Đáp án:** Không. Đây là trường có ngữ nghĩa mạnh, nên cân nhắc cột SQL riêng, constraint, index và kiểm soát transaction. JSON phù hợp hơn với metadata mở rộng ít ràng buộc quan hệ.

### Bài 31. Bảo vệ tenant

**Câu hỏi:** câu `UPDATE ho_so SET tai_lieu=... WHERE id=101` đã đủ an toàn cho ứng dụng nhiều tổ chức chưa?

**Đáp án:** Chưa chắc. Nên kiểm tra `to_chuc_id` theo context đã xác thực, quyền từng trường và chính sách RLS khi phù hợp. JSON path không bảo vệ việc sửa nhầm **hàng**.

### Bài 32. Đo hiệu năng

**Câu hỏi:** làm thế nào chứng minh một partial JSON update tốt hơn ghi lại toàn bộ document?

**Đáp án:** Đo trên dữ liệu đại diện: end-to-end latency, CPU/I/O, WAL/redo/binlog, rows/index updates, lock waits, kích thước JSON và concurrency. Không suy kết quả từ tên JSON_SET hay một bảng demo chỉ ba hàng.

## 32. Checklist khi triển khai cập nhật JSON trong SQL

Trước khi đưa thao tác JSON path update vào production, kiểm tra:

1. **DBMS/version/storage engine** nào đang chạy? Các hàm có tồn tại không?
2. JSON được lưu dạng **native JSON/JSONB/TEXT/LOB**? Có JSON validation không?
3. Mục tiêu là **set, replace-only, insert-only, remove, append hay merge patch**?
4. Path là **text[] PostgreSQL, SQL/JSON path hay JSON Pointer RFC 6902**?
5. Key cha đã tồn tại và có đúng **object/array type** chưa?
6. Key cuối vắng mặt có được phép thêm không?
7. Đặt JSON null khác xóa key như thế nào trong DBMS đó?
8. Giá trị boolean, number, string, object, array được tạo đúng kiểu JSON chưa?
9. Với array, thao tác theo **index vị trí** hay **ID nghiệp vụ**?
10. Xóa/chèn array có làm thay đổi index của phần tử khác không?
11. Có giữ được **các sibling keys** không, hay vô tình thay cả object?
12. Dùng merge patch có chấp nhận **null=xóa** và **array=thay cả** không?
13. `WHERE` có lọc đúng **id, tenant, trạng thái và version** không?
14. Có kiểm tra affected rows/RETURNING và xử lý conflict an toàn không?
15. Cần transaction cùng những bảng quan hệ nào?
16. Có thể bị lost update hoặc race về bộ đếm, điểm số, quyền không?
17. Path từ client có whitelist và quyền theo field chưa?
18. Giá trị được bind, không nối chuỗi JSON/SQL tùy tiện?
19. Có schema validation hoặc CHECK cho các nhánh quan trọng không?
20. Query JSON có index phù hợp và ràng buộc kiểu/collation không?
21. Update có tạo write amplification trên index/WAL không?
22. “Partial” ở đây là **logical** hay **physical/binlog** đã được đo?
23. Có tài liệu hóa sự khác nhau giữa MySQL/SQL Server/PostgreSQL/Oracle/SQLite không?
24. Có test input NULL, missing, wrong type, empty array, nested parent missing không?
25. Có test concurrency, retry, rollback, permissions và migration JSON schema không?

## 33. Tài liệu tham khảo chính thức

Khi triển khai, hãy đối chiếu tài liệu theo **đúng phiên bản** database đang dùng:

- **PostgreSQL:** [JSON Functions and Operators](https://www.postgresql.org/docs/current/functions-json.html), [JSON Types](https://www.postgresql.org/docs/current/datatype-json.html), [Concurrency Control](https://www.postgresql.org/docs/current/mvcc.html).
- **MySQL:** [JSON Modification Functions](https://dev.mysql.com/doc/refman/8.4/en/json-modification-functions.html), [Partial Updates of JSON Values](https://dev.mysql.com/doc/refman/8.4/en/json.html#json-partial-updates), [Partial JSON Binary Logging](https://dev.mysql.com/doc/refman/8.4/en/json.html).
- **SQL Server:** [JSON_MODIFY](https://learn.microsoft.com/en-us/sql/t-sql/functions/json-modify-transact-sql), [JSON functions](https://learn.microsoft.com/en-us/sql/relational-databases/json/json-data-sql-server), [JSON_VALUE](https://learn.microsoft.com/en-us/sql/t-sql/functions/json-value-transact-sql), [JSON_QUERY](https://learn.microsoft.com/en-us/sql/t-sql/functions/json-query-transact-sql).
- **Oracle Database:** [JSON_TRANSFORM](https://docs.oracle.com/en/database/oracle/oracle-database/21/adjsn/oracle-sql-function-json_transform.html), [JSON_MERGEPATCH](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/JSON_MERGEPATCH.html), [SQL/JSON Language](https://docs.oracle.com/en/database/oracle/oracle-database/21/adjsn/index.html).
- **SQLite:** [JSON Functions and Operators](https://www.sqlite.org/json1.html), [SQLite Transactions](https://www.sqlite.org/lang_transaction.html).
- **IETF RFC:** [RFC 6902 — JSON Patch](https://www.rfc-editor.org/rfc/rfc6902), [RFC 7396 — JSON Merge Patch](https://www.rfc-editor.org/rfc/rfc7396), [RFC 6901 — JSON Pointer](https://www.rfc-editor.org/rfc/rfc6901).

## 34. Kết luận

**Cập nhật một phần tài liệu JSON theo hệ quản trị** là việc diễn đạt một thao tác có mục tiêu rõ ràng lên **path của JSON**, thay vì luôn gửi lại toàn bộ document từ ứng dụng. Nhưng mỗi DBMS có syntax và semantics riêng:

- **PostgreSQL:** `jsonb_set`, `jsonb_insert`, `-`, `#-`, `jsonb_set_lax`; path `text[]` và JSONB đúng kiểu.
- **MySQL/InnoDB:** `JSON_SET`, `JSON_REPLACE`, `JSON_INSERT`, `JSON_REMOVE`, `JSON_ARRAY_APPEND`; có những tối ưu **physical partial JSON update** khi đáp ứng điều kiện.
- **SQL Server:** `JSON_MODIFY` với **lax/strict**, `append`, `JSON_QUERY` để chèn object/array; đặc biệt cẩn thận với SQL NULL.
- **Oracle:** `JSON_TRANSFORM` cho operations theo path, `JSON_MERGEPATCH` cho RFC 7396 khi phiên bản hỗ trợ.
- **SQLite:** `json_set`/`json_insert`/`json_replace`/`json_remove`/`json_patch`, cú pháp append `$[#]` và JSONB riêng của SQLite.

Ba nguyên tắc quan trọng:

1. **Đúng logic JSON trước:** phân biệt thêm/sửa/xóa, JSON null với key vắng mặt, scalar với object/array và chỉ số với ID nghiệp vụ.
2. **Đúng transaction và quyền:** giới hạn tenant/field, bind tham số, kiểm tra affected rows, version và concurrency; không dùng partial JSON update để thay thế constraints hoặc transaction giữa nhiều bảng.
3. **Đúng kỳ vọng hiệu năng:** cập nhật một path ở SQL **không chứng minh** database chỉ ghi vài byte; hãy đo I/O, index, replication và contention trên workload thật.

**Câu hỏi tốt nhất trước mỗi UPDATE JSON là:** “Tôi muốn thay đổi **những path nào, theo semantics nào, trên đúng hàng nào**, và có bảo đảm không ghi đè dữ liệu cùng lúc hoặc mất các nhánh khác không?” Trả lời được bốn điều đó rồi mới chọn hàm cụ thể cho hệ quản trị đang sử dụng.
