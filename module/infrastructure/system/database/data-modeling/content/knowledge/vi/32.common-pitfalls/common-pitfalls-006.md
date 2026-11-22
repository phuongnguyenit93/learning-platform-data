# Mô hình thực thể–thuộc tính–giá trị (EAV) và chi phí của cấu trúc quá tổng quát

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Giải thích **Entity–Attribute–Value (EAV)** và xác định **grain** của mỗi hàng, thay vì nhầm một hàng thuộc tính với một thực thể nghiệp vụ.
- Phân tích đánh đổi giữa **linh hoạt khi thêm thuộc tính** và **chi phí kiểu dữ liệu, ràng buộc, truy vấn, chỉ mục, thống kê, vận hành và tiến hóa**.
- Phát hiện những lỗi EAV phổ biến: dùng TEXT cho mọi kiểu, ép kiểu lúc đọc, missing value nhập nhằng, multi-value không rõ grain, giá/số dư bị lưu như thuộc tính tùy ý.
- Viết truy vấn PostgreSQL với EAV, hiểu chi phí self-join/pivot và tránh nhân hàng hoặc cộng sai số đo.
- Phân biệt trường hợp nên dùng **cột định kiểu**, **bảng mở rộng theo category**, **typed EAV**, **JSONB/document** hoặc **read projection**.
- Thiết kế metadata có **đơn vị, required/allowed values, phân loại dữ liệu, owner và version**, cùng quy trình migration và kiểm thử.
- Đánh giá phương án qua workload, chính sách dữ liệu, dữ liệu lịch sử và các tiêu chí có thể đối soát.

Bài nằm trong chương **Lỗi thường gặp** của **DATABASE_DATA_MODELING**. Theo mục tiêu của module, một mô hình tốt phải chuyển đúng yêu cầu nghiệp vụ thành thực thể, quan hệ, ràng buộc, chuẩn hóa, khóa, chỉ mục và lược đồ vật lý; đồng thời so sánh relational, document, graph và phân tích để có cấu trúc dễ tiến hóa, kiểm chứng. EAV là một ví dụ rất rõ: **ít cột hơn không đồng nghĩa chi phí mô hình hóa ít hơn**.

> **Thông điệp:** EAV không mặc định sai. Nó có giá trị cho những thuộc tính thật sự động, thưa và được quản trị. Nhưng nếu dùng EAV để né việc xác định **kiểu, grain, bất biến, quyền và mẫu truy cập** của dữ liệu cốt lõi, tính phức tạp chỉ bị chuyển từ DDL sang hệ thống xung quanh.

## 1. Tình huống: “một bảng lưu được mọi loại thuộc tính”

Một sàn bán điện thoại, quần áo, sách và máy công nghiệp. Những loại hàng có thuộc tính rất khác nhau:

| Nhóm | Một vài thuộc tính |
| --- | --- |
| **Điện thoại** | storage_gb, color_code, has_nfc, screen_inches |
| **Áo** | size_code, fabric_code, color_code |
| **Sách** | isbn, author, page_count, language_code |
| **Máy công nghiệp** | voltage_v, power_w, maintenance_cycle_days |

Nhóm phát triển muốn người quản trị thêm thuộc tính mà không phải ALTER TABLE. Phương án được đề xuất:

~~~text
entities:
  entity_id | entity_type | name

attributes:
  attribute_id | name

values:
  entity_id | attribute_id | value
~~~

Ví dụ một biến thể điện thoại:

| entity_id | attribute | value |
| --- | --- | --- |
| P-101 | color_code | black |
| P-101 | storage_gb | 128 |
| P-101 | has_nfc | true |
| P-101 | screen_inches | 6.5 |

Muốn thêm **waterproof_rating = IP67**, chỉ cần thêm metadata và một hàng value. Không có migration thay cột.

Nhưng ngay khi giao diện cần tìm **điện thoại màu đen, dung lượng từ 128 GB, có NFC, sort theo giá**, câu hỏi mới xuất hiện:

- **128** là integer hay chuỗi **"128 GB"**?
- **true** là Boolean hay chuỗi **"TRUE"/"YES"/"1"** tùy nguồn?
- Thuộc tính thuộc **nhóm sản phẩm** hay **biến thể có thể bán**?
- Ai quyết định allowed values và required fields của điện thoại?
- Người dùng có được thêm **internal_cost, recipient_email** vào cùng bảng public không?
- Cần bao nhiêu join và index khi có hàng triệu biến thể?
- Nếu một attribute đổi đơn vị hoặc nghĩa, các API/search/ETL cũ còn đúng không?

**Cấu trúc EAV đã làm đơn giản thao tác thêm attribute, nhưng chưa giải quyết những câu hỏi nghiệp vụ ấy.**

## 2. EAV là gì, và grain của nó là gì?

EAV biểu diễn một giá trị bằng bộ ba:

~~~text
(entity, attribute, value)

entity     = thực thể được mô tả
attribute  = định nghĩa tính chất của thực thể
value      = giá trị hiện có cho tính chất đó
~~~

Một bảng có cột định kiểu:

| variant_id | color_code | storage_gb | has_nfc |
| --- | --- | ---: | --- |
| P-101 | black | 128 | true |
| P-102 | blue | 256 | false |

Biểu diễn EAV:

| variant_id | attribute_code | value_text |
| --- | --- | --- |
| P-101 | color_code | black |
| P-101 | storage_gb | 128 |
| P-101 | has_nfc | true |
| P-102 | color_code | blue |
| P-102 | storage_gb | 256 |
| P-102 | has_nfc | false |

**Grain minh họa: một hàng EAV là một giá trị hiện hành của một thuộc tính đơn trị, thuộc một variant trong một tenant.** Khóa có thể là **(tenant_id, variant_id, attribute_id)**.

Nếu một thuộc tính đa trị như **nhiều tác giả**, khóa ấy không còn biểu diễn đủ. Có thể dùng thực thể Author với bảng **book_authors** N:M, hoặc thiết kế value_id/position/cardinality riêng. **Không nhồi danh sách phân cách dấu phẩy vào value_text để giả vờ một quan hệ là một giá trị.**

Nếu cần lưu lịch sử, một value còn phải có **effective_from/effective_to**, version hoặc event ID. Không tự coi việc thêm hàng mỗi lần đổi là lịch sử đúng khi chưa có ràng buộc overlap và quy tắc current version.

### 2.1. EAV giải quyết những vấn đề thật nào?

- Thuộc tính **rất thưa**: mỗi loại thực thể chỉ có một nhóm nhỏ trong tập tất cả các trường.
- **Form cấu hình**: quản trị viên có thể định nghĩa một trường tùy chọn cho từng mẫu biểu.
- **Hệ thu thập dữ liệu**: thuộc tính và loại quan sát thường thay đổi, metadata có khả năng mô tả chúng.
- **Catalog đa nhóm**: hàng nghìn thuộc tính tùy chọn hiếm, không cần filter theo từng trường.
- **Sản phẩm nhiều tenant**: mỗi tenant có một số trường tùy biến, nếu hệ chấp nhận chi phí quản trị.

Tuy nhiên, nếu 90% tìm kiếm dựa trên 5 thuộc tính được định nghĩa ổn định, việc đưa cả 5 vào EAV có thể làm thiết kế khó truy vấn và khó đảm bảo đúng mà không tạo giá trị tương xứng.

### 2.2. EAV không tự động vi phạm hoặc bảo đảm chuẩn hóa

Trong một EAV đơn trị, có thể tồn tại phụ thuộc hàm **(entity_id, attribute_id) → value**. Metadata có **attribute_id → attribute definition**. Một thiết kế như vậy không nhất thiết vi phạm mọi dạng chuẩn hóa quan hệ.

Vấn đề là **kiểu và quy tắc của cột logic đã chuyển sang dữ liệu metadata**, nên database khó áp dụng NOT NULL/CHECK/FK riêng cho mỗi attribute. **Chuẩn hóa, kiểm chứng bất biến và hiệu suất truy vấn là các chiều đánh giá khác nhau**; không thể lấy nhãn “EAV là 3NF” hoặc “EAV không chuẩn hóa” để quyết định thay cho phân tích thực tế.

## 3. EAV không phải thay thế mọi thực thể và quan hệ

Một thiết kế sai thường cố lưu:

~~~text
order:
  buyer_id = "C-101"
  product_ids = "P-1,P-2,P-3"
  payment_status = "PAID"
  shipment_ids = "S-9,S-10"
~~~

Nhưng:

- Một Order có nhiều **OrderLine**, mỗi dòng có quantity, variant và giá đã chốt.
- Một Order có nhiều **Shipment**, mỗi shipment có người nhận và vòng đời riêng.
- Một Order có thể có nhiều **PaymentCapture** và **Refund**, không phải chỉ một chuỗi status.
- Buyer ID có quan hệ tới miền Identity với tenant và quyền truy cập.
- Một trường đa giá trị cần **grain, khóa, thứ tự và quy tắc uniqueness** riêng.

EAV có thể phù hợp cho **thuộc tính mô tả linh hoạt**; các quan hệ nghiệp vụ và sự kiện cần entity/relationship có cấu trúc.

Một phương án hybrid:

~~~text
catalog_products:
  product_id
  product_name

catalog_variants:
  variant_id, product_id, sku
  list_price_amount, currency_code

phone_specifications:
  variant_id, storage_gb, has_nfc, color_code

variant_optional_attributes:
  variant_id, attribute_id, typed_value

order_lines:
  order_id, line_no, variant_id, quantity
  unit_price_at_confirmation
~~~

Các thuộc tính **cốt lõi** được đặt ở nơi có thể dùng kiểu, FK và CHECK. Phần **động, thưa** có thể tiếp tục dùng EAV có quản trị.

## 4. Ví dụ PostgreSQL: EAV tối thiểu với value_text

Schema sau cố tình dùng TEXT cho các value để minh họa vấn đề. Nó **không được coi là thiết kế mặc định cho hệ catalog sản xuất**.

~~~sql
CREATE SCHEMA catalog;

CREATE TABLE catalog.variants (
    tenant_id BIGINT NOT NULL,
    variant_id UUID NOT NULL,
    category_code TEXT NOT NULL,
    sku TEXT NOT NULL,
    display_name TEXT NOT NULL,
    list_price_amount NUMERIC(18, 2) NOT NULL,
    currency_code CHAR(3) NOT NULL,

    CONSTRAINT pk_catalog_variants
        PRIMARY KEY (tenant_id, variant_id),
    CONSTRAINT uq_catalog_variants_sku
        UNIQUE (tenant_id, sku),
    CONSTRAINT ck_catalog_variants_price
        CHECK (list_price_amount >= 0)
);

CREATE TABLE catalog.attribute_definitions (
    tenant_id BIGINT NOT NULL,
    attribute_id UUID NOT NULL,
    attribute_code TEXT NOT NULL,
    value_kind TEXT NOT NULL,
    unit_code TEXT,
    is_searchable BOOLEAN NOT NULL DEFAULT FALSE,

    CONSTRAINT pk_attribute_definitions
        PRIMARY KEY (tenant_id, attribute_id),
    CONSTRAINT uq_attribute_definitions_code
        UNIQUE (tenant_id, attribute_code),
    CONSTRAINT ck_attribute_value_kind
        CHECK (value_kind IN ('TEXT', 'NUMBER', 'BOOLEAN'))
);

CREATE TABLE catalog.variant_attribute_eav (
    tenant_id BIGINT NOT NULL,
    variant_id UUID NOT NULL,
    attribute_id UUID NOT NULL,
    value_text TEXT NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT pk_variant_attribute_eav
        PRIMARY KEY (tenant_id, variant_id, attribute_id),
    CONSTRAINT fk_eav_variant
        FOREIGN KEY (tenant_id, variant_id)
        REFERENCES catalog.variants(tenant_id, variant_id),
    CONSTRAINT fk_eav_definition
        FOREIGN KEY (tenant_id, attribute_id)
        REFERENCES catalog.attribute_definitions(tenant_id, attribute_id)
);
~~~

Schema bảo đảm:

- Một giá trị thuộc **variant** và **attribute** tồn tại trong cùng tenant.
- Mỗi cặp **variant–attribute** có tối đa một giá trị hiện hành.
- **attribute_code** duy nhất trong tenant.
- Giá niêm yết có NUMERIC và CHECK độc lập với EAV.

Nhưng chưa bảo đảm:

- NUMBER phải có value_text parse được thành số.
- BOOLEAN phải có true/false hợp lệ.
- Storage của điện thoại nằm trong allowed values.
- Thuộc tính bắt buộc của category phải có hàng.
- Thuộc tính chỉ gán cho category được phép.
- Đơn vị được chuẩn hóa hay được chuyển đổi đúng.
- Multi-valued/temporal rules hoặc điều kiện chéo giữa hai attribute.
- Quyền đọc/ghi từng attribute cho từng consumer.

**FK xác minh hàng metadata tồn tại, không thực thi mọi quy tắc nghiệp vụ của metadata ấy.**

### 4.1. Một vài giá trị sai nhưng không bị schema demo chặn

| variant | attribute | value_text | value_kind |
| --- | --- | --- | --- |
| P-101 | storage_gb | 128 | NUMBER |
| P-102 | storage_gb | 256 | NUMBER |
| P-103 | storage_gb | 128 GB | NUMBER |
| P-104 | has_nfc | YES | BOOLEAN |
| P-105 | screen_inches | unknown | NUMBER |

Các hàng cuối vẫn có thể được INSERT vào **variant_attribute_eav**, vì TEXT chấp nhận chúng. Chỉ kiểm tra ở giao diện nhập liệu không đủ: dữ liệu có thể đến từ import, CDC, job sửa, API cũ hoặc batch migration.

## 5. Query nhiều thuộc tính: từ cột thành self-join

Một truy vấn tìm điện thoại **màu đen, dung lượng ít nhất 128 GB, có NFC** có thể dùng bảng định kiểu phone_specifications:

~~~sql
-- Minh họa sau khi tạo phone_specifications ở phần 9.
SELECT v.variant_id, v.sku, v.list_price_amount
FROM catalog.variants AS v
JOIN catalog.phone_specifications AS s
  ON s.tenant_id = v.tenant_id
 AND s.variant_id = v.variant_id
WHERE v.tenant_id = $1
  AND v.category_code = 'PHONE'
  AND s.color_code = 'black'
  AND s.storage_gb >= 128
  AND s.has_nfc = TRUE
ORDER BY v.list_price_amount, v.variant_id
LIMIT 20;
~~~

EAV đòi hỏi các phép nối trên nhiều hàng:

~~~sql
-- Cố ý minh họa rủi ro CAST khi value_text chưa được validate.
SELECT v.variant_id, v.sku, v.list_price_amount
FROM catalog.variants AS v
JOIN catalog.variant_attribute_eav AS color_v
  ON color_v.tenant_id = v.tenant_id
 AND color_v.variant_id = v.variant_id
JOIN catalog.attribute_definitions AS color_d
  ON color_d.tenant_id = color_v.tenant_id
 AND color_d.attribute_id = color_v.attribute_id
 AND color_d.attribute_code = 'color_code'
JOIN catalog.variant_attribute_eav AS storage_v
  ON storage_v.tenant_id = v.tenant_id
 AND storage_v.variant_id = v.variant_id
JOIN catalog.attribute_definitions AS storage_d
  ON storage_d.tenant_id = storage_v.tenant_id
 AND storage_d.attribute_id = storage_v.attribute_id
 AND storage_d.attribute_code = 'storage_gb'
JOIN catalog.variant_attribute_eav AS nfc_v
  ON nfc_v.tenant_id = v.tenant_id
 AND nfc_v.variant_id = v.variant_id
JOIN catalog.attribute_definitions AS nfc_d
  ON nfc_d.tenant_id = nfc_v.tenant_id
 AND nfc_d.attribute_id = nfc_v.attribute_id
 AND nfc_d.attribute_code = 'has_nfc'
WHERE v.tenant_id = $1
  AND v.category_code = 'PHONE'
  AND color_v.value_text = 'black'
  AND storage_v.value_text::NUMERIC >= 128
  AND nfc_v.value_text = 'true'
ORDER BY v.list_price_amount, v.variant_id
LIMIT 20;
~~~

**Nhược điểm không chỉ là SQL dài:**

1. **Nhiều self-join** để tạo những “cột” logic.
2. Metadata phải được nối để xác định attribute nào đang đọc.
3. **storage_v.value_text::NUMERIC** có thể lỗi với **"128 GB"** hoặc **"unknown"**.
4. TEXT sort là từ điển: **"100"** có thể đứng trước **"20"**, không theo số.
5. Bộ tối ưu phải ước lượng các attribute rất khác nhau trên cùng bảng.
6. Filter Boolean phụ thuộc biểu diễn text thống nhất.
7. Một lần đổi code/type metadata có thể phá query, index hoặc consumer.

Không nên chỉ gắn một biểu thức regex trong WHERE rồi tin rằng database luôn kiểm tra regex **trước** phép cast theo thứ tự đã viết. Phép đánh giá biểu thức của SQL có thể được tối ưu; **bảo vệ bằng typed storage/validator tại lúc ghi** đáng tin hơn.

### 5.1. Pivot và phép nhóm không tự miễn phí

Có thể gộp từng attribute thành một cột logic:

~~~sql
SELECT
    av.tenant_id,
    av.variant_id
FROM catalog.variant_attribute_eav AS av
JOIN catalog.attribute_definitions AS d
  ON d.tenant_id = av.tenant_id
 AND d.attribute_id = av.attribute_id
WHERE av.tenant_id = $1
  AND d.attribute_code IN ('color_code', 'has_nfc')
GROUP BY av.tenant_id, av.variant_id
HAVING
    MAX(av.value_text) FILTER (
        WHERE d.attribute_code = 'color_code'
    ) = 'black'
    AND MAX(av.value_text) FILTER (
        WHERE d.attribute_code = 'has_nfc'
    ) = 'true';
~~~

**MAX** ở đây chỉ đưa một single-valued attribute qua phép nhóm; nó không mang ý nghĩa lấy “màu lớn nhất”. Nếu một attribute có nhiều giá trị hoặc nhiều version, phép nhóm phải thay đổi theo grain và logic chọn phiên bản.

Một màn hình có 15 filter có thể khiến query pivot chứa nhiều biểu thức, cần xử lý attribute vắng mặt và type. **Không mặc định pivot nhanh hơn self-join**: kiểm tra qua EXPLAIN và dữ liệu đại diện.

### 5.2. Tránh nhân hàng với EXISTS khi chỉ cần điều kiện tồn tại

Nếu chỉ cần kiểm tra **có** một attribute đúng giá trị, EXISTS có thể giúp tránh lặp hàng kết quả do quan hệ có nhiều giá trị:

~~~sql
SELECT v.variant_id, v.sku
FROM catalog.variants AS v
WHERE v.tenant_id = $1
  AND EXISTS (
      SELECT 1
      FROM catalog.variant_attribute_eav AS av
      JOIN catalog.attribute_definitions AS d
        ON d.tenant_id = av.tenant_id
       AND d.attribute_id = av.attribute_id
      WHERE av.tenant_id = v.tenant_id
        AND av.variant_id = v.variant_id
        AND d.attribute_code = 'color_code'
        AND av.value_text = 'black'
  )
  AND EXISTS (
      SELECT 1
      FROM catalog.variant_attribute_eav AS av
      JOIN catalog.attribute_definitions AS d
        ON d.tenant_id = av.tenant_id
       AND d.attribute_id = av.attribute_id
      WHERE av.tenant_id = v.tenant_id
        AND av.variant_id = v.variant_id
        AND d.attribute_code = 'has_nfc'
        AND av.value_text = 'true'
  );
~~~

EXISTS bảo vệ **ngữ nghĩa điều kiện tồn tại**, không xóa chi phí truy cập EAV. Vẫn cần index và số liệu thực tế.

### 5.3. JOIN gây sai COUNT/SUM, không chỉ chậm

Một variant có:

~~~text
3 tags
4 warehouses
2 campaigns
~~~

Nếu JOIN mọi quan hệ 1:N và EAV liên quan, có thể có **3 × 4 × 2 = 24 hàng** đại diện cùng một variant. SUM(list_price_amount) hoặc COUNT(*) trên kết quả ấy không còn là tổng giá hoặc số variant.

Cần **nhóm đúng grain trước khi nối**, dùng EXISTS cho filter, hoặc tạo read projection **một hàng/variant**. Không dùng SUM(DISTINCT price) như cách sửa tổng quát vì hai variant có thể có cùng giá.

## 6. Validation: EAV chuyển ràng buộc từ DDL sang metadata

Một cột có khai báo:

~~~sql
storage_gb INTEGER NOT NULL
  CHECK (storage_gb IN (64, 128, 256, 512));
~~~

cho database biết kiểu, tính bắt buộc và tập hợp lệ. Khi chuyển storage_gb thành **attribute_code = storage_gb, value_text = "128"**, những thông tin ấy chủ yếu nằm ở metadata và code.

| Bất biến | Cột typed | EAV generic cần gì thêm? |
| --- | --- | --- |
| **Đúng kiểu** | INTEGER/BOOLEAN/DATE | Parse và kiểm tra theo attribute |
| **Không thiếu** | NOT NULL | Kiểm tra required theo category/version |
| **Khoảng/tập hợp lệ** | CHECK/enum/FK | Rule theo attribute có owner |
| **Một giá trị** | PK/UNIQUE | Cardinality single/multi-valued |
| **Quan hệ tham chiếu** | FOREIGN KEY | Reference type hoặc bảng quan hệ |
| **Đơn vị** | Kiểu/cột unit rõ | Metadata + conversion |
| **Điều kiện chéo** | Domain logic/transaction | Rule engine trên nhiều value |
| **Thời gian hiệu lực** | Range/EXCLUDE | Version và overlap rule |
| **Phân quyền** | Role/view/column access | Attribute policy và scope |
| **Chỉ mục** | Typed column + statistics | Index chung, expression hoặc projection |

**Schema typed cũng không tự giải mọi invariant liên bảng**, nhưng EAV làm nhiều quy tắc đơn giản trở thành logic ở lớp ghi và dữ liệu metadata.

### 6.1. Một attribute bắt buộc bị thiếu có nghĩa gì?

Điện thoại bắt buộc có storage_gb; nhưng variant không có hàng storage_gb. **value_text NOT NULL** không chặn được, vì không có hàng nào để kiểm tra.

Có thể quản lý bảng quy tắc:

~~~text
category_attribute_rules:
  tenant_id
  category_code
  attribute_id
  is_required
  min_occurrences
  max_occurrences
  validation_version
~~~

Nếu bảng rules đã tồn tại và đơn giản hóa rằng required là đơn trị, có thể tìm thiếu:

~~~sql
-- Bảng category_attribute_rules là thành phần bổ sung
-- chưa được khai báo trong schema tối thiểu phần 4.
SELECT
    v.tenant_id,
    v.variant_id,
    d.attribute_code AS missing_required_attribute
FROM catalog.variants AS v
JOIN catalog.category_attribute_rules AS r
  ON r.tenant_id = v.tenant_id
 AND r.category_code = v.category_code
 AND r.is_required = TRUE
JOIN catalog.attribute_definitions AS d
  ON d.tenant_id = r.tenant_id
 AND d.attribute_id = r.attribute_id
LEFT JOIN catalog.variant_attribute_eav AS av
  ON av.tenant_id = v.tenant_id
 AND av.variant_id = v.variant_id
 AND av.attribute_id = r.attribute_id
WHERE av.attribute_id IS NULL;
~~~

Truy vấn chỉ kiểm tra **coverage**, chưa xác minh value đúng kiểu hoặc thuộc phạm vi hợp lệ. **Rules thay đổi theo thời gian** cần version/effective time nếu muốn đánh giá đúng các bản ghi cũ.

### 6.2. Missing, null, unknown và not applicable khác nhau

Không có hàng EAV có thể nghĩa là:

- Thuộc tính **không áp dụng** cho category.
- Chưa nhập, **không biết**.
- Đã bị validation từ chối.
- Dữ liệu **đến muộn** hoặc pipeline chưa đồng bộ.
- Thuộc tính bị ẩn theo quyền.
- Đã có yêu cầu xóa hoặc không được giữ nữa.

**Không chèn chuỗi "NULL" hoặc "N/A" vào TEXT rồi coi nó là SQL NULL**. Cần mô hình presence/reason hoặc quy tắc cụ thể, không để dashboard tự điền 0 cho mọi thiếu hụt.

## 7. Kiểu, đơn vị và bản chất số đo

Một attribute weight có các value:

~~~text
"2.5"
"2500 g"
"2,5"
"2.50kg"
"unknown"
~~~

Có thể có cùng ý định đo khối lượng nhưng **cú pháp và đơn vị khác**. Nếu cộng hoặc so sánh text trực tiếp, kết quả không đáng tin.

Metadata cho một attribute nghiêm túc cần:

- **Kiểu:** số nguyên/thập phân/Boolean/text/date/timestamp/enum/reference.
- **Đơn vị chuẩn:** kg, g, GB hay GiB, V, A, °C.
- **Độ chính xác:** scale/precision/rounding.
- **Phạm vi hợp lệ và danh sách cho phép.**
- **Cardinality:** một hay nhiều giá trị; có thứ tự hay không.
- **Required/optional theo loại đối tượng và trạng thái.**
- **Nguồn chuẩn, owner và quyền ghi.**
- **Phân loại nhạy cảm, API audience, retention.**
- **Version/effective time của định nghĩa.**

Nếu producer A dùng **GB** và producer B dùng **GiB**, hai giá trị 128 chưa chắc đồng nghĩa. Cần normalization/conversion và lưu provenance khi cần.

### 7.1. Không ép dữ liệu tài chính hoặc tồn kho vào generic NUMBER

**captured_amount** không chỉ là một số: nó có currency, trạng thái capture, payment attempt, idempotency, event time và nghĩa vụ đối soát. **on_hand_quantity** là tồn kho tại một kho/variant/thời điểm, không phải số lượng có thể cộng qua các ngày.

Một value_kind = NUMBER không tạo ra các bất biến ấy. Giá, tồn kho, payment, balance và giao dịch nên có entity, fact hoặc ledger theo grain nghiệp vụ, không phải EAV chỉ để tránh tạo bảng.

## 8. Chỉ mục và statistics: linh hoạt có chi phí vật lý

Giả sử 300.000 variant, trung bình 40 attribute có value/variant:

- Khoảng **12 triệu hàng** trong bảng EAV.
- Mỗi hàng chứa tenant, variant_id, attribute_id, value_text và metadata.
- PK và index phụ làm tăng dung lượng, I/O, WAL và công việc bảo trì.
- Truy vấn filter 4–6 attribute có thể lặp lại thao tác truy cập và JOIN nhiều lần.

Không thể kết luận chắc EAV dùng nhiều byte hơn bảng rộng trong mọi engine. Bảng rộng có NULL, compression, TOAST, index và tỷ lệ điền thực tế; **phải đo với dữ liệu tương ứng**.

### 8.1. Chỉ mục phục vụ query khác nhau

PK **(tenant_id, variant_id, attribute_id)** hợp đọc toàn bộ thuộc tính của **một variant**.

Filter mọi variant theo một thuộc tính và giá trị có thể cần:

~~~sql
CREATE INDEX ix_eav_attr_text_variant
ON catalog.variant_attribute_eav
   (tenant_id, attribute_id, value_text, variant_id);
~~~

Nhưng index TEXT này không biến **value_text::NUMERIC** thành numeric range index đúng. Một expression index ép kiểu toàn bảng có thể lỗi ngay khi có value không phải số, hoặc bị sai vì áp cho attributes khác nhau. Khi có typed EAV, numeric range index trên cột NUMERIC phù hợp hơn.

Một index chung còn gặp:

- TEXT trộn màu, dung lượng, ISBN, voltage, email và ngày.
- Selectivity của từng attribute khác nhau rất mạnh.
- Planner khó ước lượng correlation của nhiều thuộc tính trong cùng variant.
- Write amplification và index bloat khi nhiều value được đổi.
- Hàng nghìn attribute động có thể tạo **cardinality lớn** và overhead metadata.

Không tạo vô số index trên từng attribute một cách máy móc. Chỉ tối ưu những predicate thật sự phổ biến, có mục tiêu SLO và bằng chứng đo.

### 8.2. Sort, pagination và attribute vắng mặt

Sort theo storage_gb dưới dạng TEXT có thể đặt **"100"** trước **"20"** theo từ điển. Pagination theo nhiều thuộc tính phải có **tie-breaker ổn định**, ví dụ variant_id, và xác định cách sort NULL/missing.

Một thay đổi attribute giữa hai request có thể làm kết quả chuyển trang bị lặp/bỏ. Nếu API cam kết phân trang nhất quán, cần định nghĩa cursor/snapshot; không mặc định một OFFSET trên kết quả EAV động sẽ ổn.

### 8.3. Schema không đổi nhưng chi phí vẫn tăng

Thêm một thuộc tính mới có thể làm tăng số hàng ghi, lượng index, thời gian build search projection, số phép lọc UI, độ phức tạp cache và vận hành backfill. **Không ALTER TABLE không nghĩa là thay đổi rẻ**, đặc biệt khi thuộc tính mới được đưa vào filter/sort bắt buộc hoặc quyết định nghiệp vụ quan trọng.

## 9. Phương án A — Cột định kiểu cho thuộc tính cốt lõi

Với điện thoại, nếu các trường **color_code, storage_gb, has_nfc** ổn định và được lọc thường xuyên:

~~~sql
CREATE TABLE catalog.phone_specifications (
    tenant_id BIGINT NOT NULL,
    variant_id UUID NOT NULL,
    color_code TEXT NOT NULL,
    storage_gb INTEGER NOT NULL,
    has_nfc BOOLEAN NOT NULL,
    screen_inches NUMERIC(4, 2),

    CONSTRAINT pk_phone_specifications
        PRIMARY KEY (tenant_id, variant_id),
    CONSTRAINT fk_phone_specs_variant
        FOREIGN KEY (tenant_id, variant_id)
        REFERENCES catalog.variants (tenant_id, variant_id),
    CONSTRAINT ck_phone_storage
        CHECK (storage_gb IN (64, 128, 256, 512, 1024)),
    CONSTRAINT ck_phone_screen
        CHECK (screen_inches IS NULL OR screen_inches > 0)
);

CREATE INDEX ix_phone_specs_search
ON catalog.phone_specifications
   (tenant_id, color_code, has_nfc, storage_gb, variant_id);
~~~

Lợi ích:

- INTEGER và BOOLEAN được kiểm tra ngay khi ghi.
- NOT NULL/CHECK có thể diễn đạt điều kiện rõ.
- Index theo predicate và khoảng số học.
- SQL/API dễ hiểu, dễ đối soát hơn.
- Thêm/đổi cột đi qua migration và review chính thức.

Giới hạn:

- Thêm thuộc tính cốt lõi thường cần deploy schema và code.
- Ví dụ chưa chặn được việc gán phone_specifications cho variant không thuộc PHONE: cần category constraint/composite FK hoặc validation nghiệp vụ có giao dịch.
- Nếu hàng trăm category có đặc điểm riêng, nhiều bảng extension có thể tăng chi phí bảo trì.

**Một bảng riêng theo nhóm không tự là thiết kế tốt**; chỉ thêm khi nó làm rõ grain/ràng buộc/quyền và phục vụ workload đã xác định.

## 10. Phương án B — EAV có kiểu cho giá trị linh hoạt

Nếu vẫn cần thuộc tính numeric động, có thể tránh value_text chung bằng bảng typed. Ví dụ dùng FK composite để xác minh attribute thực sự có value_kind NUMBER:

~~~sql
ALTER TABLE catalog.attribute_definitions
ADD CONSTRAINT uq_attr_definition_kind
UNIQUE (tenant_id, attribute_id, value_kind);

CREATE TABLE catalog.variant_numeric_attributes (
    tenant_id BIGINT NOT NULL,
    variant_id UUID NOT NULL,
    attribute_id UUID NOT NULL,
    value_kind TEXT NOT NULL DEFAULT 'NUMBER',
    value_numeric NUMERIC(18, 4) NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT pk_variant_numeric_attributes
        PRIMARY KEY (tenant_id, variant_id, attribute_id),
    CONSTRAINT fk_numeric_variant
        FOREIGN KEY (tenant_id, variant_id)
        REFERENCES catalog.variants (tenant_id, variant_id),
    CONSTRAINT ck_numeric_kind
        CHECK (value_kind = 'NUMBER'),
    CONSTRAINT fk_numeric_definition_kind
        FOREIGN KEY (tenant_id, attribute_id, value_kind)
        REFERENCES catalog.attribute_definitions
            (tenant_id, attribute_id, value_kind)
);

CREATE INDEX ix_numeric_attr_range
ON catalog.variant_numeric_attributes
   (tenant_id, attribute_id, value_numeric, variant_id);
~~~

Typed EAV có lợi:

- NUMERIC thực sự là numeric; không thể lưu **"hello"** trong value_numeric.
- CHECK + FK composite chỉ cho giá trị NUMBER tham chiếu metadata NUMBER.
- Range filter có thể dùng index numeric.
- Một attribute cần thêm không nhất thiết tạo cột mới.

Nhưng **không tự giải quyết**:

- Giá trị NUMBER của storage_gb phải là một trong những dung lượng hợp lệ.
- Voltage, temperature và battery capacity có range khác nhau.
- Đơn vị chuẩn, category applicability, required fields.
- Mối quan hệ đa giá trị hoặc thời gian.
- Quyền theo attribute, metadata version và consumer compatibility.
- Chồng chéo khi cùng attribute đang được lưu ở bảng TEXT và NUMBER trong migration.

Một truy vấn typed:

~~~sql
SELECT v.variant_id, v.sku,
       n.value_numeric AS battery_capacity_mah
FROM catalog.variants AS v
JOIN catalog.variant_numeric_attributes AS n
  ON n.tenant_id = v.tenant_id
 AND n.variant_id = v.variant_id
JOIN catalog.attribute_definitions AS d
  ON d.tenant_id = n.tenant_id
 AND d.attribute_id = n.attribute_id
WHERE v.tenant_id = $1
  AND d.attribute_code = 'battery_capacity_mah'
  AND n.value_numeric >= 4000
ORDER BY n.value_numeric, v.variant_id;
~~~

**Typed EAV sửa được một phần vấn đề kiểu và cast, không loại bỏ chi phí metadata-driven modeling.**

## 11. Phương án C — JSONB/document cho thuộc tính tùy chọn

Một lựa chọn khác là đặt những thuộc tính linh hoạt, ít được JOIN hoặc filter, trong một JSONB object gắn với variant:

~~~sql
CREATE TABLE catalog.variant_optional_properties (
    tenant_id BIGINT NOT NULL,
    variant_id UUID NOT NULL,
    properties JSONB NOT NULL,

    CONSTRAINT pk_variant_optional_properties
        PRIMARY KEY (tenant_id, variant_id),
    CONSTRAINT fk_optional_properties_variant
        FOREIGN KEY (tenant_id, variant_id)
        REFERENCES catalog.variants (tenant_id, variant_id),
    CONSTRAINT ck_optional_properties_object
        CHECK (jsonb_typeof(properties) = 'object')
);

CREATE INDEX ix_optional_properties_gin
    ON catalog.variant_optional_properties
    USING GIN (properties jsonb_path_ops);
~~~

Một object minh họa:

~~~json
{
  "waterproofRating": "IP67",
  "releaseRegion": "VN",
  "supportedLanguages": ["vi", "en"]
}
~~~

Một điều kiện containment có thể sử dụng loại GIN index trong ví dụ:

~~~sql
SELECT variant_id
FROM catalog.variant_optional_properties
WHERE properties @> '{"releaseRegion":"VN"}'::jsonb;
~~~

**JSONB có ưu điểm gì so với EAV nhiều hàng?**

- Những thuộc tính tùy chọn thường được đọc cùng nhau nằm trong một document.
- JSON hỗ trợ các kiểu cơ bản **number, string, Boolean, array, object, null**, thay vì một TEXT cho mọi loại.
- Có thể dùng toán tử JSON và GIN index cho các truy vấn phù hợp.
- Các trường ít dùng có thể được thêm mà không phải thêm cột relational.

**Vấn đề nào vẫn tồn tại?**

- Producer có thể gửi **storageGb: "128"** ở một bản ghi và **storageGb: 128** ở bản ghi khác; JSON type khác nhau.
- Sai chính tả, thiếu required field, khoảng giá trị sai, đơn vị không thống nhất vẫn có thể được lưu.
- JSONB GIN **jsonb_path_ops** hỗ trợ một số toán tử như containment, **không tự tối ưu mọi phép ->>**, sắp xếp theo số hoặc range query. Có thể cần expression index typed hoặc cột riêng.
- Thay đổi một key có thể gây xung đột khi nhiều producer cùng cập nhật document.
- Một object lớn không có hợp đồng quyền có thể trộn PII, bí mật và trường public.
- Khi dữ liệu được đưa vào analytics, vẫn cần flatten, xác nhận grain và định nghĩa metric.

**JSONB là cách lưu linh hoạt, không phải một validator nghiệp vụ tự động.** Nó phù hợp cho tập thuộc tính thưa và ít bị lọc; trường quan trọng cần constraints hoặc schema validation có thẩm quyền.

## 12. So sánh các hướng theo nhu cầu thực tế

| Tiêu chí | Cột relational typed | EAV TEXT | EAV typed | JSONB/document |
| --- | --- | --- | --- | --- |
| Thuộc tính quan trọng, ổn định | Rất phù hợp | Thường khó kiểm soát | Có thể nhưng nhiều mapping | Cần validation ngoài |
| Thuộc tính hiếm, thay đổi liên tục | Dễ tăng schema | Linh hoạt | Linh hoạt, đúng kiểu tốt hơn | Linh hoạt, đọc object thuận |
| Numeric range filter thường xuyên | Typed index rõ | Cast/rủi ro lỗi | Numeric index | Expression index/projection |
| Required/unique/allowed values | DDL rõ hơn | Metadata + validator | Typed nhưng vẫn cần rules | JSON schema/application/constraints |
| Nhiều giá trị/quan hệ thật | Bảng con 1:N/N:M | Cần grain bổ sung | Cần grain bổ sung | Array nhưng FK/order cần thiết kế |
| Tìm theo 6 thuộc tính | SQL ngắn, index dễ xét | Nhiều join/pivot | Nhiều join/pivot | JSON extraction và index tương ứng |
| Báo cáo grain rõ | Relational dễ diễn đạt | Phải chuyển/pivot | Phải chuyển/pivot | Flatten và data dictionary |
| Tiến hóa field | Migration DDL | Metadata/data migration | Metadata/data migration | Document/schema migration |
| Quyền theo field | Role/view/API | Policy theo attribute | Policy theo attribute | Policy theo key và contract |
| Chi phí vận hành | Migration khi đổi core | Dễ tăng hàng/index | Nhiều họ bảng + validator | Schema drift, index, cập nhật document |

Không có cột nào “chiến thắng tất cả”. Một mô hình **hybrid** thường là lựa chọn cân bằng:

~~~text
Core entities + domain relations:
  ID, tenant, trạng thái, giá, kho, lệnh nghiệp vụ

Typed category extensions:
  thông số phổ biến và có rule chặt

Flexible attributes:
  phần hiếm, thưa, có metadata/validator

Read model / search projection:
  một hàng/variant cho bộ lọc, sort và pagination quan trọng

Analytics:
  fact/dimension đúng grain, định nghĩa metric, lineage
~~~

Nếu workload nhỏ, không cần tạo cùng lúc typed EAV, JSONB và search engine. **Chỉ thêm lớp khi lợi ích đã được chứng minh bằng use case và phép đo.**

## 13. EAV và các mô hình dữ liệu khác: ranh giới ý nghĩa

### 13.1. Quan hệ (*relational*)

Relational schema có PK/FK, UNIQUE, CHECK, NOT NULL, type và index trực tiếp trên cột. Điều đó giúp database kiểm soát nhiều bất biến.

EAV là **một cách biểu diễn dữ liệu trên relational database**, không phải một database model hoàn toàn khác. Vì thế phải đánh giá nó dựa trên cả **data integrity và workload** chứ không phải “SQL không linh hoạt”.

### 13.2. Document

Document có thể lưu thuộc tính động trong object hoặc subdocument, nhưng vẫn cần quy định về:

- Grain ở document và nested array.
- ID, version, schema và đơn vị.
- Consumer nào được phép xem từng key.
- Chỉ mục cho filter cần thiết.
- Mối quan hệ ra ngoài document, tránh copy nhiều lịch sử không kiểm soát.

Không phải cứ lưu một mảng authors trong JSON là có quan hệ Author–Book đã được kiểm tra. Nếu muốn truy vấn nhiều-nhiều, unique và vai trò tác giả, có thể cần một collection/bảng quan hệ riêng.

### 13.3. Graph

Graph phù hợp các quan hệ linh hoạt **Customer–PLACED–Order**, **Product–BELONGS_TO–Category**, **Device–INSTALLED_AT–Site**. Nhưng một cạnh **RELATED_TO** cùng property **value** không tự bảo đảm semantics. Đưa mọi sự kiện và quan hệ thành **attribute_value** trên node có thể làm mất hướng cạnh, cardinality, quyền và effective time.

**Thuộc tính đơn trị của node** khác **quan hệ giữa hai thực thể**. Không dùng EAV để né mô hình cạnh thực sự.

### 13.4. Analytical/columnar

Warehouse thường cần:

~~~text
fact_order_line_confirmed:
  tenant_id, order_id, line_no, variant_id
  quantity, line_net_amount, confirmed_at, currency_code

dim_product_variant:
  variant_key, variant_id
  storage_gb, color_code, has_nfc
  effective_from, effective_to
~~~

Nếu dữ liệu catalog ở EAV, pipeline có thể pivot những attribute **đã được xác minh** sang dimension typed. Cần xác định:

- Dimension grain một variant hiện hành hay một **version** của variant (SCD Type 2)?
- Thuộc tính có đúng **thời điểm mua** hay đang lấy giá trị hiện nay?
- Làm sao tránh JOIN fact với nhiều version mà không as-of, gây nhân doanh thu?
- Những attribute nào thực sự cần báo cáo và có được phép xuất không?
- Null/missing/unknown được chuyển ra dimension thế nào?

Một thuộc tính **on_hand_quantity** là snapshot tồn kho, không được SUM xuyên nhiều ngày như một dòng sự kiện. Việc EAV có value_numeric không biến state thành flow.

## 14. Tiến hóa metadata cũng là tiến hóa schema

Đội sản phẩm muốn đổi **storage_gb** thành **storage_capacity_gib**. Nhìn trên EAV có vẻ chỉ cần UPDATE một hàng metadata. Nhưng GB và GiB là hai đơn vị khác nhau; nếu đổi tên mà giữ nguyên mọi số, dữ liệu có thể bị diễn giải sai.

Ngoài ra còn:

- API và search filter vẫn dùng attribute_code cũ.
- Cache/projection chứa tên field cũ.
- ETL/analytics dùng code để pivot.
- Index và validation có thể dựa trên loại NUMBER và allowed values cũ.
- Một số hàng cũ có đơn vị khác dù cùng code.
- Quyền công bố có thể đổi theo sensitivity.
- Lịch sử giao dịch cần đọc theo định nghĩa tại thời điểm được ghi.

### 14.1. Attribute definition cần quản trị, không chỉ tên

Một hợp đồng metadata mở rộng có thể là:

~~~text
attribute_definition:
  attribute_id           -- ID ổn định trong phạm vi đã công bố
  attribute_code         -- tên được consumer dùng
  value_kind
  canonical_unit
  allowed_values
  range_min, range_max
  applicable_categories
  is_required
  is_searchable
  sensitivity_class
  source_of_truth
  owner
  definition_version
  effective_from
  effective_to
~~~

Không phải mỗi hệ phải có tất cả trường này, nhưng những field liên quan trực tiếp tới validation, quyền và compatibility không thể bị bỏ mặc.

**Đổi metadata có thể breaking không kém ALTER TABLE.** Cần quy trình **expand → chuyển dữ liệu/validator → validate → chuyển reader/writer → ngừng cấu trúc cũ**.

### 14.2. Phân biệt các kiểu thay đổi

| Thay đổi | Nghĩa | Hành động phù hợp |
| --- | --- | --- |
| **colour → color_code** | Có thể là đổi tên thuần túy | Alias/version nếu cùng giá trị thực |
| **weight_kg → weight_g** | Đổi đơn vị | Chuyển đổi có kiểm chứng, precision, provenance |
| **TEXT → NUMBER** | Đổi kiểu | Parse/loại lỗi/backfill |
| **product-level → variant-level** | Đổi grain | Thiết kế quan hệ mới và phân bổ đúng |
| **single → multi-valued** | Đổi cardinality | Khóa/value_id/position hoặc bảng quan hệ |
| **current → historical** | Đổi trục thời gian | Version/effective interval |
| **public → restricted** | Đổi quyền | Thu hồi khỏi API, index, log, export và consumer |

Đổi **storage_gb** thành **battery_capacity_mah** không phải phép rename hợp lệ chỉ vì cùng là số. **Attribute ID cũng phải gắn với ngữ nghĩa ổn định**, không tái sử dụng mã của một khái niệm khác.

## 15. Bảo mật: một EAV chung có thể trở thành cửa hậu dữ liệu

Một admin tự tạo:

~~~text
customer_email
recipient_phone
internal_supplier_cost
fraud_review_score
access_token
private_note
~~~

Nếu API catalog tự trả **mọi attribute** cho consumer bên ngoài, dữ liệu nhạy cảm có thể bị phát tán dù database không thêm cột nào.

Cần kiểm soát:

- **Quyền tạo/sửa metadata** và việc gán sensitivity class.
- **Allowlist public fields theo consumer/purpose**, không phát SELECT *.
- **Object-level authorization** theo tenant và entity; UUID khó đoán không phải bằng chứng quyền.
- **Attribute-level policy** khi một nhóm field cần quyền đọc riêng.
- **Validation giá trị/độ dài** trước khi ghi, kể cả import và batch.
- **Giới hạn số attribute/tenant**, số hàng và giá trị để tránh cardinality không kiểm soát.
- **Audit và retention** theo loại thông tin.
- **Log, CDC, event bus, DLQ, cache, search index, export, backup** là các nơi có thể chứa giá trị EAV.
- **Không dùng EAV làm kho chứa secret** nếu không có cơ chế bảo vệ và quyền chuyên biệt.

PK/FK composite bảo vệ tham chiếu đúng tenant nhưng không tự hạn chế **ai được SELECT trong tenant**. Nếu thuộc tính public và restricted nằm cùng bảng, backend phải lọc trước khi dữ liệu đi ra ngoài; không đẩy toàn bộ JSON xuống frontend rồi chỉ ẩn trong UI.

## 16. Search projection: tối ưu đọc nhưng sinh trách nhiệm đồng bộ

Nếu search liên tục lọc theo **color, storage, has_nfc, price**, có thể tạo read projection một hàng/variant:

~~~text
catalog_search_projection:
  tenant_id
  variant_id
  sku
  category_code
  color_code
  storage_gb
  has_nfc
  list_price_amount
  currency_code
  source_variant_version
  projected_at
~~~

Ưu điểm:

- Query theo cột typed, index rõ, có thể sort/paginate dễ hơn.
- Giảm self-join trong đường đọc nhiều request.
- EAV hoặc JSONB có thể tiếp tục lưu những thuộc tính tùy chọn ít dùng.

Chi phí mới:

- Mỗi thay đổi giá trị nguồn phải cập nhật projection.
- **Độ trễ đồng bộ** nếu pipeline bất đồng bộ.
- Message trùng/sai thứ tự cần **idempotency và version check**.
- Metadata đổi cần rebuild/projection migration.
- Xóa giá trị EAV phải xóa/NULL value tương ứng trong projection; không giữ dữ liệu stale mãi.
- Phải có **watermark, freshness SLO, reconciliation và quyền truy cập**.

**Projection không có quyền tự tạo sự thật nghiệp vụ mới.** Nếu tồn kho hoặc giá quyết định lệnh giao dịch cần tính nhất quán tức thời, dùng nguồn authoritative/đường kiểm tra phù hợp, không chỉ dựa vào search index eventual stale.

### 16.1. Đối soát từ metadata linh hoạt sang typed projection

Một quy trình đối soát cần:

1. Chốt phạm vi tenant/variant và source checkpoint.
2. Dùng metadata version tương ứng để parse/đổi đơn vị.
3. So typed value với projection ở cùng version.
4. Phát hiện **missing, extra và mismatch**, kể cả attribute bị xóa.
5. Quarantine record invalid, không tự gán 0 hoặc chuỗi mặc định làm như đúng.
6. Recompute/bù trừ từ nguồn chuẩn còn sẵn.
7. Kiểm tra quyền: field restricted không xuất nhầm vào projection public.

Không gọi mọi khác biệt trong cửa sổ lag hợp lệ là lỗi vĩnh viễn, nhưng cũng không coi lag là lý do cho phép mismatch tồn tại vô hạn.

## 17. Quyết định bằng workload, không bằng cảm giác “linh hoạt”

Giả sử:

- **300.000 variant**, trung bình **40 value/variant** ⇒ khoảng **12 triệu hàng EAV**.
- 80% request detail chỉ cần 20 trường phổ biến.
- Search UI thường filter 6 attribute và sort theo storage/price.
- Mỗi tuần có attribute tùy chọn mới, nhưng bộ 6 attribute search chính ít đổi.
- Dashboard phân tích cần dữ liệu có grain variant hoặc order line đúng.

Bảng sau **hoàn toàn là số liệu giả định để thực hành so sánh**, không phải benchmark đo trong môi trường thật:

| Phương án | p95 search minh họa | Chi phí đáng lưu ý |
| --- | ---: | --- |
| EAV TEXT trực tiếp | 420 ms | Self-join, parse/cast, lỗi dữ liệu, index rộng |
| Typed EAV | 230 ms | Validator/rule và pivot còn phức tạp |
| Cột typed cho 6 filter chính | 85 ms | Migration khi cột quan trọng đổi |
| EAV + search projection | 70 ms | Pipeline, lag, replay và reconciliation |
| JSONB cho fields tùy chọn | 160 ms | Schema/key drift và index chuyên biệt |

**Không chọn chỉ dựa vào p95.** Cần đo thêm p99, tải đồng thời, CPU, I/O, số byte dữ liệu/index, tốc độ ingest, WAL, chi phí update, lỗi validation, thời gian rebuild và quyền truy cập.

### 17.1. Một bộ benchmark có thể thực hiện

1. Đọc detail một variant với 20 attribute.
2. Search có 2/4/6 filters với độ chọn lọc khác nhau.
3. Numeric range filter và sort, pagination ổn định.
4. Cập nhật một thuộc tính phổ biến, đo index writes và projection lag.
5. Import batch chứa giá trị sai kiểu/đơn vị/required.
6. Xóa attribute, kiểm tra cache/projection/analytics được cập nhật.
7. Đọc theo category với tập attribute rất khác nhau.
8. Kiểm tra COUNT/SUM khi JOIN các thuộc tính đa trị.
9. Đổi metadata version và thử migration/rollback.
10. Đọc từ role bị hạn chế để xác minh không lộ restricted attributes.

Dùng **EXPLAIN (ANALYZE, BUFFERS)** và dữ liệu có phân bố gần sản xuất. Một SQL nhanh trên 20 hàng không chứng minh thiết kế phù hợp cho 12 triệu rows.

## 18. Migration từ EAV quá tổng quát sang mô hình có chủ đích

Một hệ cũ lưu mọi thứ trong EAV: **giá, màu, dung lượng, tồn kho, ghi chú và custom fields**. Nhóm muốn giữ thuộc tính linh hoạt nhưng chuyển sự thật cốt lõi sang bảng typed.

Quy trình:

1. **Inventory dữ liệu**: attribute codes, types, số lượng, fill-rate, value distributions, category, owner, PII, consumer.
2. **Chốt grain và authority**: product, variant, inventory per warehouse, order line, payment? Không chuyển sai scope.
3. **Phân loại**: core fields, category-specific typed fields, optional metadata, derived fields, dữ liệu restricted.
4. **Thiết kế target schema**: PK/FK, NOT NULL, CHECK, units, currency, index, quyền và retention.
5. **Expand**: thêm bảng/cột mới nhưng chưa bỏ EAV cũ.
6. **Backfill có validate**: xử lý text sai, unit conversion, duplicate/missing; ghi lỗi riêng để quyết định.
7. **Đổi đường ghi có kiểm soát**: chỉ một nguồn chuẩn quyết định, tránh dual-write độc lập.
8. **Shadow read**: đối chiếu object detail, filter, sort, metric và quyền.
9. **Cutover từng nhóm** với telemetry, fallback và điểm rollback/forward-fix.
10. **Reconcile**: so giá trị, coverage, count, sum theo đúng grain và currency.
11. **Dừng writer legacy** và xử lý queued event/replay cũ.
12. **Contract**: gỡ EAV cho core fields sau khi không còn consumer, đúng retention và đủ bằng chứng.

### 18.1. Không ép value lỗi thành 0

Một thuộc tính **storage_gb** có:

~~~text
"128"
"128.0"
"128 GB"
"128GiB"
"unknown"
~~~

Không được INSERT tất cả thành 0 rồi tự coi migration thành công. Cần:

- Chọn đơn vị canonical và quy tắc chuyển đổi có chứng cứ.
- Xác định cách parse số, thập phân và rounding.
- Phân biệt **missing**, **unknown** và **invalid**.
- Đánh dấu record chưa thể công bố nếu thiếu giá trị bắt buộc.
- Có danh sách cần sửa từ nguồn có thẩm quyền.
- Thiết lập ngưỡng **cutover gate** và đối soát sau khi sửa.

### 18.2. Không đánh mất lịch sử giao dịch

Nếu **size_code**, màu, giá hay cấu hình variant đã tham gia một OrderLine được chốt, dữ liệu lịch sử phải giữ đúng **giá/variant/snapshot tại thời điểm giao dịch**. Chỉ giữ current EAV rồi tra lại khi xem hóa đơn cũ có thể làm sai sự thật.

Cần snapshot được chấp thuận, event nguồn hoặc dimension Type 2/as-of join theo nghiệp vụ; metadata rename không được tự sửa lịch sử chứng từ.

## 19. Checklist review EAV trước khi triển khai

| Câu hỏi | Bằng chứng cần có |
| --- | --- |
| Entity và grain của một value là gì? | Single/multi, tenant, thời gian |
| Thuộc tính cốt lõi nào đã ổn định? | Business invariants và access pattern |
| Tần suất thêm field thật sự bao nhiêu? | Dữ liệu thay đổi schema theo kỳ |
| Dữ liệu có thật sự sparse? | Fill-rate theo category |
| Có numeric range filter/sort? | Query workload và index |
| Kiểu được enforce ở đâu? | Typed storage/validator/test |
| Required/allowed values? | Metadata version và coverage |
| Quan hệ thật có bị giấu trong value? | PK/FK, N:M, domain entities |
| NULL/missing có nghĩa gì? | Unknown/not applicable/withheld |
| Thuộc tính multi-valued? | Value ID/position hoặc bảng quan hệ |
| Hiệu lực thời gian? | Version/range/as-of |
| Quyền PII/secret? | Attribute allowlist, auth, retention |
| Analytics có đúng grain? | Chống fan-out, additive rules |
| Metadata đổi thì sao? | Contract versioning và migration |
| Có projection và rebuild? | Source, checkpoint, idempotency |
| Có benchmark so phương án khác? | p95/p99, bytes/index, update cost |
| Ai là owner? | Đơn vị quản trị metadata/schema/SLO |

## 20. Bài tập vận dụng

### Bài 1 — NUMBER nhưng lưu TEXT bất kỳ

storage_gb có metadata NUMBER, value_text gồm **"128"**, **"256"**, **"128 GB"**, **"unknown"**.

**Câu hỏi:** FK có đảm bảo đúng kiểu không? ORDER BY value_text và CAST trực tiếp có vấn đề gì?

### Bài 2 — Thuộc tính required bị thiếu

PHONE bắt buộc has_nfc, nhưng variant P-101 không có hàng has_nfc.

**Câu hỏi:** Vì sao PK/NOT NULL trong EAV vẫn hợp lệ? Cần rule/coverage nào?

### Bài 3 — Nhiều tác giả trong một chuỗi

Một giá trị **authors = "An, Bình, Chi"** được lưu ở EAV của sách. Sau đó cần thống kê số sách theo tác giả và thứ tự đồng tác giả.

**Câu hỏi:** Thiếu quan hệ/grain nào?

### Bài 4 — Sáu filter trên search

UI cần filter color, storage, NFC, screen, battery, release region rồi sort theo storage.

**Câu hỏi:** Chi phí EAV TEXT là gì? Khi nào nên dùng typed columns, typed EAV hoặc read projection?

### Bài 5 — JOIN nhân số đo

Một variant có ba tags và hai campaigns. Báo cáo JOIN cả hai rồi SUM(list_price_amount).

**Câu hỏi:** Vì sao số bị nhân? Cách giữ grain?

### Bài 6 — JSONB và sai kiểu

Một producer ghi **storageGb: "128"** và một producer ghi **storageGb: 128** trong JSONB.

**Câu hỏi:** JSONB đã đủ chưa? Cần contract và validator nào?

### Bài 7 — Tồn kho theo thời gian

Hôm qua on_hand_quantity=25, hôm nay=20. Dashboard SUM hai snapshot và gọi tồn hiện tại 45.

**Câu hỏi:** Sai loại số đo gì? Nên mô hình balance và movement thế nào?

### Bài 8 — Đổi đơn vị

Metadata đổi từ **weight_kg** thành **weight_g** nhưng giữ value 2.5.

**Câu hỏi:** Vì sao đây không chỉ rename? Cách migration nào đúng?

### Bài 9 — EAV trộn PII với dữ liệu public

Một admin tạo attribute **recipient_email** và **internal_supplier_cost**. Public API trả mọi attribute.

**Câu hỏi:** Đường lộ nào và kiểm soát gì cần thêm?

### Bài 10 — Analytics lấy current dimension

Warehouse pivot các thuộc tính EAV **hiện tại** rồi JOIN fact bán hàng ba năm trước để báo màu sản phẩm lúc mua.

**Câu hỏi:** Kết quả có thể sai vì điều gì? Cần lưu lịch sử thế nào?

### Bài 11 — Chọn thiết kế

100.000 variants, 95% luôn có color_code, storage_gb, has_nfc; 90% search trên ba trường. Chỉ vài trường hiếm mới thêm hàng tháng.

**Câu hỏi:** Chọn mô hình nào và cần đo những gì?

### Bài 12 — Backfill bị lỗi 2%

Migration storage_gb sang INTEGER có 2% hàng không parse được. Nhóm định gán những hàng đó = 0 và cutover.

**Câu hỏi:** Chấp nhận được không? Đề xuất gate và cách xử lý.

### Bài 13 — Đổi tên attribute làm vỡ consumer

Metadata color_code được đổi thành colour, trong khi API, cache và ETL vẫn dùng color_code.

**Câu hỏi:** Đây có phải thay đổi schema về mặt hợp đồng không? Cách tương thích?

### Bài 14 — Typed EAV nhưng rule vẫn sai

Bảng typed numeric cho phép battery_capacity_mah = -500. Trong cùng bảng có temperature_celsius = -5 là giá trị hợp lệ.

**Câu hỏi:** Vì sao không thể CHECK(value_numeric >= 0) cho toàn bảng? Cần rule/thiết kế nào?

### Gợi ý lời giải

1. FK chỉ xác nhận attribute tồn tại, không validate value_text theo value_kind. Sort TEXT không theo số; cast có thể lỗi. Cần typed storage/validation và thống nhất unit trước khi query.
2. Thiếu hàng không vi phạm NOT NULL trên hàng không tồn tại. Dùng category_attribute_rules có version và kiểm tra required coverage trước khi publish.
3. Author là thực thể riêng; sách–tác giả có thể N:M với book_authors, PK/FK và author_order/role khi cần. Chuỗi phân cách dấu phẩy không là quan hệ tin cậy.
4. Self-join/pivot, kiểu TEXT, index và statistics khó. Đưa filter cốt lõi sang phone_specifications typed, dùng typed EAV/JSONB cho phần hiếm, projection khi workload/SLO cần.
5. JOIN 3 × 2 tạo 6 hàng/variant. Dùng EXISTS cho filter hoặc tổng hợp từng quan hệ trước khi JOIN; không SUM giá header sau fan-out.
6. Chưa. JSONB có kiểu JSON nhưng không bảo đảm producer thống nhất. Cần JSON schema/validator, required, range, unit và test compatibility.
7. on_hand_quantity là **snapshot**, không additive qua thời gian. Dùng balance ở SKU × warehouse × time và movement ledger cho dòng nhập/xuất, chọn đúng snapshot cuối kỳ.
8. 2.5 kg không phải 2.5 g. Cần conversion, metadata version, precision, mapping và cập nhật consumer; tránh đổi tên rồi diễn giải lại dữ liệu cũ.
9. Attribute public/restricted bị trộn trong response. Cần quyền tạo metadata, phân loại sensitivity, allowlist field, tenant/object/attribute authorization, audit và quản trị bản sao.
10. Giá trị hiện tại không chắc là giá trị lúc mua. Cần snapshot ở OrderLine hoặc SCD Type 2/temporal dimension với as-of join.
11. Ưu tiên cột typed cho ba trường ổn định/đọc nhiều; giữ EAV/JSONB cho trường hiếm. Đo p95/p99, index bytes, chi phí ghi, validation errors và migration overhead.
12. Không gán 0 khi không phải sự thật. Phân loại invalid, quarantine, sửa từ nguồn, theo dõi coverage và đạt validation gate rồi mới cutover.
13. Có: metadata là schema ở tầng ứng dụng. Dùng alias/version, hỗ trợ đọc cũ/mới, chuyển writer/ETL/cache và theo dõi consumer trước khi bỏ code cũ.
14. Rule theo attribute khác nhau: temperature âm có thể hợp lệ, pin dung lượng âm không. Dùng metadata validation đáng tin và/hoặc cột typed với CHECK theo miền; không áp CHECK chung sai.

## 21. Ghi nhớ

**EAV biến thuộc tính thành dữ liệu để tăng linh hoạt, nhưng không loại bỏ thiết kế mô hình.** Nó chuyển một phần schema thành **metadata, validator, phép nối/pivot, chỉ mục, kiểm soát quyền và quy trình tiến hóa**. Một INSERT thêm thuộc tính có thể rẻ; toàn bộ chi phí duy trì tính đúng và khả năng đọc của thuộc tính ấy thì không.

EAV tốt phải trả lời: **entity là gì, mỗi value có grain nào, kiểu/đơn vị/required/allowed value được kiểm tra ở đâu, ai có quyền đọc/ghi, filter nào cần nhanh, và metadata thay đổi thì điều gì xảy ra**.

**Dùng quan hệ/cột định kiểu cho sự thật cốt lõi**, nhất là định danh, giá, payment, tồn kho, trạng thái, chứng từ và bất biến nghiệp vụ. Dùng **typed EAV hoặc JSONB cho phần thật sự động, thưa và được quản trị**; thêm search projection khi phép đo workload cho thấy cần.

Trước khi chọn EAV, hãy hỏi: **“Chúng ta cần thêm thuộc tính mới thường xuyên đến mức nào, và sẵn sàng trả bao nhiêu chi phí để kiểm tra, tìm kiếm, tổng hợp, bảo vệ, thay đổi và khôi phục chúng?”**. Một mô hình tốt không chỉ **dễ thêm trường**, mà còn phải **dễ hiểu đúng và khó sử dụng sai**.
