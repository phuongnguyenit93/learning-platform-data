# Lựa chọn bảng quan hệ, jsonb hoặc mô hình kết hợp

Một nền tảng thương mại điện tử bán điện thoại, giày và sách. Mọi sản phẩm đều có mã SKU, giá bán, trạng thái và đơn vị sở hữu. Nhưng điện thoại có dung lượng RAM, loại màn hình; giày có cỡ và chất liệu; sách có ISBN, tác giả và số trang. Nên tạo hàng trăm cột có thể `NULL` trong một bảng, tạo một bảng cho mỗi loại, hay đưa toàn bộ thông tin vào một cột `jsonb`?

Ở một hệ thống khác, mỗi đơn hàng cần lưu địa chỉ nhận hàng **tại thời điểm mua**, không được tự thay đổi khi khách cập nhật hồ sơ. Một hệ thống tích hợp nhận webhook với cấu trúc thay đổi theo phiên bản API. Một nghiệp vụ kế toán lại cần bảo đảm tổng tiền, khóa ngoại và tính duy nhất của mã giao dịch. Ba tình huống này có **những yêu cầu dữ liệu khác nhau**, nên không có một câu trả lời “luôn dùng quan hệ” hay “luôn dùng JSON” cho tất cả.

PostgreSQL cho phép kết hợp những đặc tính của cơ sở dữ liệu quan hệ với kiểu **`jsonb`** — JSON được phân tích thành dạng nhị phân có thể truy vấn và lập chỉ mục. Lựa chọn tốt không chỉ dựa trên việc schema có linh hoạt hay không, mà còn dựa vào **bất biến dữ liệu, mẫu truy cập, cập nhật đồng thời, tăng trưởng, khả năng lập chỉ mục, lịch sử và chi phí vận hành**.

Trong bài này, chúng ta sẽ:

1. Xác định khi nào chọn **bảng/cột quan hệ**, **`jsonb`**, hoặc **mô hình kết hợp**.
2. Phân biệt `json`, `jsonb`, SQL array, bảng con và bảng nối nhiều-nhiều.
3. Thiết kế một **product catalog đa tenant** theo ba cách và nêu trade-off.
4. Sử dụng `->`, `->>`, `#>`, `#>>`, `?`, `@>`, JSONPath và `jsonb_set`.
5. Kiểm tra các kiểu `NULL`, thiếu khóa JSON, validation và những giới hạn của `CHECK`.
6. Lập chỉ mục **B-tree expression/generated column**, **GIN jsonb_ops/jsonb_path_ops** và partial index.
7. Truy vấn JSON array, so sánh với SQL array/bảng liên kết.
8. Xử lý cập nhật đồng thời, thay đổi cấu trúc payload, lưu snapshot và lịch sử.
9. Phân tích `TOAST`, MVCC/WAL, thống kê, query planner, migration và JDBC/Spring.
10. Làm lab PostgreSQL và các bài tập quyết định mô hình theo yêu cầu nghiệp vụ.

> **Môi trường:** Các ví dụ hướng tới PostgreSQL hiện đại. Một số cú pháp như JSONPath cần PostgreSQL 12+, còn tính năng generated columns và khả năng planner/index có khác biệt theo phiên bản. Chạy các lệnh tạo bảng, cập nhật và migration trong database thực hành. Mục tiêu là chọn cấu trúc phù hợp và hiểu hậu quả, không mặc định JSONB nhanh hơn hay chậm hơn quan hệ trong mọi workload.

## 1. Mô hình quan hệ và jsonb giải quyết những bài toán gì?

**Mô hình quan hệ** lưu dữ liệu trong những bảng có cột được khai báo kiểu rõ ràng. PostgreSQL có thể thực thi trực tiếp:

- `PRIMARY KEY` và `UNIQUE`.
- `NOT NULL` và `CHECK`.
- `FOREIGN KEY` giữa các bảng.
- Quy tắc transaction, isolation và khóa.
- Chỉ mục B-tree, GiST, GIN... theo cột/biểu thức.
- Thống kê planner theo cột và các tổ hợp được cấu hình.

**`jsonb`** lưu giá trị JSON trong một cột PostgreSQL:

```json
{
  "color": "black",
  "screen_inches": 6.7,
  "connectivity": ["wifi", "5g"],
  "warranty": {
    "months": 24,
    "provider": "manufacturer"
  }
}
```

Những giá trị JSON có thể là **object**, **array**, **string**, **number**, **boolean** hoặc **JSON null**. PostgreSQL cung cấp operators/functions để đọc, lọc và sửa cấu trúc đó.

**Mô hình kết hợp** giữ những thông tin có cấu trúc và ràng buộc mạnh trong các cột quan hệ, đồng thời sử dụng một hoặc vài cột `jsonb` cho những phần thông tin biến thiên hoặc snapshot:

```text
products
├── product_id           BIGINT PRIMARY KEY
├── tenant_id            BIGINT NOT NULL
├── sku                  TEXT NOT NULL
├── name                 TEXT NOT NULL
├── current_price        NUMERIC NOT NULL
├── status               TEXT NOT NULL
├── category_id          BIGINT (FOREIGN KEY)
└── attributes           JSONB NOT NULL
    ├── color
    ├── size
    └── category-specific keys
```

Không nên chọn trước kiểu dữ liệu rồi mới cố ép mọi quy tắc nghiệp vụ vào đó. Hãy xác định **các quy tắc phải được bảo đảm** trước.

## 2. Ba lựa chọn không phải ba phe đối lập

| Tiêu chí | Quan hệ | `jsonb` là dữ liệu chính | Kết hợp |
|---|---|---|---|
| Cấu trúc ổn định, chung cho mọi hàng | Rất phù hợp | Có thể dùng nhưng dễ mất kiểm soát | Đưa vào cột chuẩn |
| Thuộc tính tùy biến/thường thay đổi | Cần nhiều schema migrations hoặc bảng con | Linh hoạt | Thường phù hợp nhất |
| PK/FK/UNIQUE/NOT NULL mạnh | Hỗ trợ trực tiếp | Cần bổ sung/thiết kế riêng | Áp dụng ở phần core |
| Truy vấn JOIN nhiều đối tượng | Tự nhiên | Truy vấn nested khó hơn | Quan hệ cho identities/relations |
| Document được lấy/ghi nguyên khối | Có thể tách nhiều bảng | Thuận tiện | JSON snapshot/metadata |
| Cập nhật một trường nhỏ thường xuyên | Tự nhiên theo cột | Có thể tạo version của cả JSON value | Đưa trường nóng ra cột |
| Thống kê/filter/range/sort | Dễ tối ưu từng cột | Cần expression/generated/index phù hợp | Chủ động chọn chỗ tối ưu |
| Schema evolution | Migration có kiểm soát | Linh hoạt nhưng dễ lệch schema | Phân tách thay đổi ổn định và biến động |
| Báo cáo, BI, analytics | Thuận tiện | Cần trích xuất/cast/normalize | Đưa dimension quan trọng ra cột |

### Quy tắc thực dụng

Nếu một thuộc tính là **định danh**, **khóa liên kết**, **đối tượng của ràng buộc mạnh**, hoặc **được lọc/sắp xếp/join rất thường xuyên**, hãy bắt đầu bằng **cột quan hệ có kiểu rõ ràng**.

Nếu một thuộc tính là **payload ít dự đoán trước**, **metadata tùy chọn**, **cấu trúc thừa kế từ API bên ngoài**, hoặc **snapshot cần giữ nguyên ngữ cảnh**, `jsonb` có thể hợp lý.

Nếu một đối tượng chứa **cả hai loại**, mô hình kết hợp thường phù hợp hơn việc buộc tất cả dữ liệu vào một bên.

## 3. Các câu hỏi cần trả lời trước khi thiết kế

1. **Dữ liệu nào xuất hiện trên mọi bản ghi?** Ví dụ SKU, trạng thái, tenant.
2. **Dữ liệu nào bắt buộc?** Có cần `NOT NULL`/`CHECK` hoặc ràng buộc dạng số?
3. **Dữ liệu nào là khóa tham chiếu?** Có FK sang customer, product, warehouse hay không?
4. **Độ biến thiên ra sao?** 5 loại sản phẩm ổn định hay 500 loại với nhiều thuộc tính mở?
5. **Truy vấn nào phổ biến?** Lookup theo SKU, lọc RAM, sort theo giá, tìm trong mảng tag, full-text?
6. **Tần suất cập nhật?** Giá và stock thay đổi mỗi phút, mô tả kỹ thuật mỗi tháng?
7. **Có cần truy vấn lịch sử?** Cần ảnh chụp tại thời điểm đặt hàng hay trạng thái hiện tại?
8. **Dữ liệu có được phân tích bởi SQL/BI không?** Có GROUP BY, SUM, JOIN theo attribute?
9. **Ai kiểm soát schema?** Đội backend, bên tích hợp bên ngoài hay từng tenant?
10. **Sai dữ liệu có chi phí gì?** Giá sai hoặc customer_id không tồn tại khác với thiếu tùy chọn UI.
11. **Dung lượng và tăng trưởng?** Có document vài KB hay payload hàng MB?
12. **Cần tương thích ngược bao lâu?** Client cũ còn gửi phiên bản JSON nào?

Một quyết định tốt thường có thể giải thích **từ các câu hỏi trên**, không phải từ khẩu hiệu “NoSQL linh hoạt hơn”.

## 4. PostgreSQL json khác jsonb ở đâu?

PostgreSQL có hai kiểu: `json` và `jsonb`.

| Tính chất | `json` | `jsonb` |
|---|---|---|
| Cách lưu | Văn bản JSON đầu vào hợp lệ | Biểu diễn nhị phân đã phân tích |
| Giữ whitespace/format đầu vào | Có theo lưu trữ text gốc | Không |
| Thứ tự khóa trong object | Giữ biểu diễn đầu vào | Không bảo đảm |
| Các khóa object trùng nhau | Văn bản ban đầu có thể còn trùng | Các key trùng được gộp, giá trị cuối chiếm ưu thế |
| Truy vấn/xử lý cấu trúc | Có functions/operators nhất định | Nhiều operators/indexing chuyên dụng hơn |
| GIN indexing của document | Không tương đương `jsonb` | Được hỗ trợ |
| Dùng cho document có query/update | Thường ít thuận tiện hơn | Thường là lựa chọn chính |

Ví dụ:

```sql
SELECT
    '{"b":2, "a":1, "a":3}'::json  AS original_json,
    '{"b":2, "a":1, "a":3}'::jsonb AS parsed_jsonb;
```

Với `jsonb`, object không còn giữ đầy đủ format và duplicate key ban đầu. Nếu hệ thống cần bảo tồn **nguyên văn payload**, chữ ký của chuỗi byte, whitespace hoặc thứ tự key để audit/signature verification, có thể cần lưu **raw text/bytes** riêng.

### Không đồng nhất JSONB với “schema-free”

`jsonb` chỉ cho phép lưu cấu trúc linh hoạt. Ứng dụng vẫn có **schema thực tế**: nó mong đợi keys, kiểu dữ liệu, version, quy tắc bắt buộc và compatibility. Không khai báo chúng rõ ràng có thể biến schema thành những giả định ẩn trong code.

## 5. Các kiểu giá trị bên trong jsonb

```sql
SELECT
    jsonb_typeof('{}'::jsonb) AS object_type,
    jsonb_typeof('[]'::jsonb) AS array_type,
    jsonb_typeof('"hello"'::jsonb) AS string_type,
    jsonb_typeof('10'::jsonb) AS number_type,
    jsonb_typeof('true'::jsonb) AS bool_type,
    jsonb_typeof('null'::jsonb) AS json_null_type;
```

Các kết quả lần lượt là `object`, `array`, `string`, `number`, `boolean` và `null` (các tên kiểu được trả dưới dạng text).

Điểm dễ nhầm:

- **SQL `NULL`** là trạng thái thiếu giá trị của một ô SQL.
- **JSON `null`** là một giá trị JSON nằm **trong tài liệu**.
- **Không có key** là trạng thái object không chứa key ấy.

Ba trạng thái trên có thể mang ý nghĩa nghiệp vụ khác nhau.

## 6. Phân biệt SQL NULL, JSON null và thiếu khóa

```sql
SELECT
    jsonb_typeof('null'::jsonb) AS json_null_kind,
    jsonb_typeof(NULL::jsonb)   AS sql_null_kind,
    ('{"color":null}'::jsonb ? 'color') AS has_color_key,
    ('{}'::jsonb ? 'color') AS missing_color_key,
    '{"color":null}'::jsonb -> 'color' AS color_json,
    '{"color":null}'::jsonb ->> 'color' AS color_text;
```

Giải thích:

- `jsonb_typeof('null'::jsonb)` trả chuỗi `'null'`.
- `jsonb_typeof(NULL::jsonb)` trả SQL NULL.
- `? 'color'` là true nếu key tồn tại, **kể cả khi value là JSON null**.
- `->` giữ kết quả dạng JSON/JSONB; key thiếu có thể trả SQL NULL.
- `->>` chuyển sang text; JSON null và key thiếu thường đều cho SQL NULL ở bước trích text.

### Hệ quả thiết kế

Nếu nghiệp vụ cần:

1. “Khách hàng chưa gửi trường `color`.”
2. “Khách hàng **chủ ý xóa** `color` bằng JSON null.”

thì không chỉ dùng `attributes->>'color' IS NULL` để phân biệt. Cần xét `attributes ? 'color'` hoặc giao thức PATCH có ý nghĩa rõ ràng.

## 7. Bài toán mẫu: danh mục sản phẩm đa tenant

Một hệ thống có:

- **Core data:** product_id, tenant_id, SKU, tên, category, trạng thái, giá.
- **Thuộc tính biến động:** màu sắc, RAM, kích cỡ, vật liệu, thông số pin, số trang.
- **Quan hệ:** sản phẩm thuộc category; sản phẩm có nhiều tags; hàng tồn kho theo từng kho.
- **Snapshot:** dữ liệu tên/giá/thuế/địa chỉ tại lúc đặt hàng.

Sơ đồ lựa chọn:

```text
tenants ──┐
          │
categories ├── products
           │    ├── cột typed: sku, price, status, ...
           │    └── attributes JSONB: color, ram, ...
           │
           ├── product_tags ── tags
           │
           └── inventory (product_id, warehouse_id, quantity)

orders ── order_items
             ├── product_id (FK tới sản phẩm)
             ├── unit_price NUMERIC
             └── product_snapshot JSONB
```

Đây là mô hình **kết hợp**: không dùng một JSON khổng lồ thay thế mọi thực thể và quan hệ.

## 8. Chuẩn bị schema lab

```sql
CREATE SCHEMA IF NOT EXISTS lesson_model_choice;

CREATE TABLE lesson_model_choice.tenants (
    tenant_id BIGINT PRIMARY KEY,
    tenant_name TEXT NOT NULL
);

CREATE TABLE lesson_model_choice.categories (
    category_id BIGINT PRIMARY KEY,
    category_name TEXT NOT NULL UNIQUE
);

INSERT INTO lesson_model_choice.tenants (
    tenant_id, tenant_name
)
VALUES
    (1, 'Tenant One'),
    (2, 'Tenant Two');

INSERT INTO lesson_model_choice.categories (
    category_id, category_name
)
VALUES
    (10, 'Điện thoại'),
    (20, 'Giày'),
    (30, 'Sách');
```

Các dữ liệu minh họa dùng mã số và tên giả, không mang ý nghĩa dữ liệu khách hàng thực.

## 9. Phương án A — Bảng quan hệ thuần

Một cách là khai báo những cột phổ biến của mọi loại sản phẩm:

```sql
CREATE TABLE lesson_model_choice.products_wide (
    product_id BIGINT PRIMARY KEY,
    tenant_id BIGINT NOT NULL
        REFERENCES lesson_model_choice.tenants(tenant_id),
    category_id BIGINT NOT NULL
        REFERENCES lesson_model_choice.categories(category_id),
    sku TEXT NOT NULL,
    product_name TEXT NOT NULL,
    price NUMERIC(12,2) NOT NULL CHECK (price >= 0),
    phone_ram_gb INTEGER,
    shoe_size_eu NUMERIC(4,1),
    book_isbn TEXT,
    book_pages INTEGER,
    color TEXT,
    material TEXT,
    CONSTRAINT uq_products_wide_tenant_sku
        UNIQUE (tenant_id, sku)
);
```

### Ưu điểm

- Cột có kiểu rõ; `price` là numeric, `phone_ram_gb` là integer.
- Dễ tạo `CHECK` và indexes trực tiếp.
- Truy vấn BI/report thường đơn giản.
- PostgreSQL thu thập statistics trên cột thông thường.

### Nhược điểm

- Phần lớn hàng có nhiều cột không áp dụng nên `NULL`.
- Mỗi loại sản phẩm thêm attributes mới có thể kéo theo DDL.
- Những quy tắc “cột này chỉ áp dụng cho category X” cần constraints phức tạp.
- Bảng có thể phình to về schema, khó quản trị.

**Đừng kết luận bảng rộng luôn sai.** Nếu chỉ có vài thuộc tính ổn định, nhiều cột nullable vẫn có thể đơn giản và hiệu quả hơn JSONB phức tạp.

## 10. Phương án A2 — Tách bảng theo loại

Có thể giữ bảng core chung rồi tạo bảng con:

```sql
CREATE TABLE lesson_model_choice.products_base (
    product_id BIGINT PRIMARY KEY,
    tenant_id BIGINT NOT NULL
        REFERENCES lesson_model_choice.tenants(tenant_id),
    category_id BIGINT NOT NULL
        REFERENCES lesson_model_choice.categories(category_id),
    sku TEXT NOT NULL,
    product_name TEXT NOT NULL,
    price NUMERIC(12,2) NOT NULL CHECK (price >= 0),
    UNIQUE (tenant_id, sku)
);

CREATE TABLE lesson_model_choice.phone_details (
    product_id BIGINT PRIMARY KEY
        REFERENCES lesson_model_choice.products_base(product_id)
        ON DELETE CASCADE,
    ram_gb INTEGER NOT NULL CHECK (ram_gb > 0),
    screen_inches NUMERIC(4,1) NOT NULL
        CHECK (screen_inches > 0)
);

CREATE TABLE lesson_model_choice.book_details (
    product_id BIGINT PRIMARY KEY
        REFERENCES lesson_model_choice.products_base(product_id)
        ON DELETE CASCADE,
    isbn TEXT NOT NULL,
    page_count INTEGER NOT NULL CHECK (page_count > 0)
);
```

### Khi nào tốt?

- Có số ít loại sản phẩm với cấu trúc khá ổn định.
- Mỗi loại có bất biến dữ liệu riêng và được query thường xuyên.
- Cần FK/UNIQUE đối với thuộc tính chuyên biệt.
- Muốn kiểm soát kiểu mạnh tại database.

### Cần cẩn thận

FK trên `phone_details.product_id` bảo đảm parent tồn tại, nhưng **không tự chứng minh parent.category_id=10**. Nếu cần ràng buộc xuyên bảng “đúng loại” chặt chẽ, phải thiết kế thêm cơ chế phù hợp (khóa kết hợp, constraints/trigger có kiểm soát hoặc cấu trúc dữ liệu khác).

Không dùng table inheritance như một lối tắt thay thế tự động mọi ràng buộc phân loại.

## 11. Phương án B — Toàn bộ document trong jsonb

```sql
CREATE TABLE lesson_model_choice.products_document (
    document_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    payload JSONB NOT NULL
        CHECK (jsonb_typeof(payload) = 'object')
);
```

Ví dụ document:

```sql
INSERT INTO lesson_model_choice.products_document(payload)
VALUES (
    '{
      "tenant_id": 1,
      "sku": "PHONE-A",
      "name": "Điện thoại A",
      "category": "phone",
      "price": 12990000,
      "attributes": {
        "ram_gb": 8,
        "screen_inches": 6.5
      }
    }'::jsonb
);
```

### Ưu điểm

- Dễ nhận và lưu document từ API bên ngoài.
- Mỗi document có cấu trúc khác nhau.
- Có thể bổ sung key mới mà không ALTER TABLE.
- Trả payload JSON lại cho client thuận tiện.

### Rủi ro

- `tenant_id`, `sku`, `price` nằm trong JSON, không tự có FK/UNIQUE/NOT NULL theo đúng ngữ nghĩa mong muốn.
- Cùng một key có thể là number ở hàng này, string ở hàng khác.
- Query và index trên nested key cần thiết kế thêm.
- Cập nhật nhỏ có thể làm thay đổi cả giá trị JSONB/tuple version.
- Truy vấn BI/joins/casts ngày càng phức tạp.
- Schema thực tế có thể trôi theo từng producer.

**Mô hình document là lựa chọn có ý thức**, phù hợp khi document là đơn vị chính và ít cần những bất biến xuyên document; không phải một cách miễn phí để tránh thiết kế schema.

## 12. Phương án C — Mô hình kết hợp

Tạo bảng sản phẩm có core typed columns và `attributes`:

```sql
CREATE TABLE lesson_model_choice.products (
    product_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id BIGINT NOT NULL
        REFERENCES lesson_model_choice.tenants(tenant_id),
    category_id BIGINT NOT NULL
        REFERENCES lesson_model_choice.categories(category_id),
    sku TEXT NOT NULL,
    product_name TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'ACTIVE'
        CHECK (status IN ('ACTIVE', 'INACTIVE')),
    price NUMERIC(12,2) NOT NULL
        CHECK (price >= 0),
    attributes JSONB NOT NULL DEFAULT '{}'::jsonb
        CHECK (jsonb_typeof(attributes) = 'object'),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_products_tenant_sku
        UNIQUE (tenant_id, sku)
);
```

### Vì sao các cột được chọn?

- `product_id`: định danh kỹ thuật ổn định, PK.
- `tenant_id`: phạm vi sở hữu và FK.
- `category_id`: quan hệ phân loại tới bảng category.
- `sku`: business key duy nhất **trong tenant**.
- `product_name`: dữ liệu cốt lõi thường hiển thị.
- `status`: vòng đời có tập giá trị được kiểm soát.
- `price`: numeric dùng phép tính/range/sort, phải có CHECK.
- `attributes`: thuộc tính kỹ thuật khác nhau theo danh mục.

Không để những trường tài chính quan trọng “chìm” trong JSON chỉ vì chúng có thể được biểu diễn thành JSON number.

## 13. Dữ liệu mẫu cho mô hình kết hợp

```sql
INSERT INTO lesson_model_choice.products (
    tenant_id, category_id, sku,
    product_name, price, attributes
)
VALUES
    (
      1, 10, 'PHONE-A', 'Điện thoại A', 12990000,
      '{
        "brand":"Acme",
        "color":"black",
        "ram_gb":8,
        "screen_inches":6.5,
        "connectivity":["wifi","5g"],
        "warranty":{"months":24,"provider":"manufacturer"}
      }'::jsonb
    ),
    (
      1, 10, 'PHONE-B', 'Điện thoại B', 18990000,
      '{
        "brand":"Acme",
        "color":"silver",
        "ram_gb":16,
        "screen_inches":6.7,
        "connectivity":["wifi","bluetooth","5g"],
        "warranty":{"months":36}
      }'::jsonb
    ),
    (
      1, 20, 'SHOE-A', 'Giày A', 1250000,
      '{
        "brand":"FootCo",
        "color":"black",
        "sizes_eu":[39,40,41,42],
        "material":"leather"
      }'::jsonb
    ),
    (
      1, 30, 'BOOK-A', 'Sách A', 185000,
      '{
        "isbn":"9780000000001",
        "author":"Tác giả A",
        "pages":320,
        "language":"vi"
      }'::jsonb
    ),
    (
      2, 10, 'PHONE-A', 'Điện thoại tenant 2', 15990000,
      '{
        "brand":"OtherBrand",
        "color":"blue",
        "ram_gb":12
      }'::jsonb
    );
```

Hai tenant được phép dùng cùng SKU vì khóa duy nhất là `(tenant_id, sku)`, không phải `sku` đơn lẻ.

## 14. Truy vấn core columns như quan hệ bình thường

```sql
SELECT
    product_id,
    tenant_id,
    sku,
    product_name,
    price,
    status
FROM lesson_model_choice.products
WHERE tenant_id = 1
  AND status = 'ACTIVE'
  AND price BETWEEN 1000000 AND 15000000
ORDER BY price, product_id;
```

Vì `price` là `NUMERIC`, PostgreSQL so sánh theo số; không cần lấy text từ JSON rồi ép kiểu trong từng predicate.

### Chỉ mục B-tree phù hợp

```sql
CREATE INDEX ix_products_tenant_status_price
ON lesson_model_choice.products (
    tenant_id,
    status,
    price
);
```

Index này có thể hỗ trợ lọc tenant/status và range/sort giá khi planner đánh giá phù hợp.

Không giả định cứ có index là query luôn dùng index. Trên bảng rất nhỏ, Seq Scan có thể rẻ hơn.

## 15. Đọc khóa JSON bằng -> và ->>

`->` trích phần tử dưới dạng JSONB, `->>` trích thành SQL text.

```sql
SELECT
    sku,
    attributes -> 'brand' AS brand_json,
    attributes ->> 'brand' AS brand_text,
    attributes -> 'ram_gb' AS ram_json,
    attributes ->> 'ram_gb' AS ram_text
FROM lesson_model_choice.products
WHERE category_id = 10;
```

Nếu `attributes` chứa:

```json
{"brand":"Acme","ram_gb":16}
```

thì:

- `attributes->'brand'` là JSON string `"Acme"`.
- `attributes->>'brand'` là SQL text `Acme`.
- `attributes->'ram_gb'` là JSON number `16`.
- `attributes->>'ram_gb'` là SQL text `16`.

### Vì sao khác biệt quan trọng?

```sql
WHERE attributes ->> 'ram_gb' = '16'
```

so sánh **text**, không phải số. Nếu muốn so sánh numeric, cần kiểu/cast phù hợp và bảo đảm dữ liệu hợp lệ.

## 16. Truy vấn nested JSON với #> và #>>

`#>`/`#>>` nhận path dưới dạng mảng text:

```sql
SELECT
    sku,
    attributes #> '{warranty,months}'
        AS months_json,
    attributes #>> '{warranty,provider}'
        AS provider_text
FROM lesson_model_choice.products
WHERE category_id = 10;
```

Tương đương lối đi từng bước:

```sql
SELECT
    sku,
    attributes -> 'warranty' ->> 'months'
        AS warranty_months_text
FROM lesson_model_choice.products
WHERE category_id = 10;
```

### Key không tồn tại

Nếu không có `warranty.provider`, phép trích xuất sẽ thường trả SQL NULL thay vì báo lỗi missing key. Điều này thuận tiện cho dữ liệu tùy chọn, nhưng có thể **che data quality issue** nếu nghiệp vụ xem trường ấy là bắt buộc.

### Không tùy tiện cast nested value

`(attributes #>> '{warranty,months}')::int` có thể lỗi khi producer gửi `"unknown"` hoặc object thay vì number/string số. Nếu trường đó trở nên quan trọng, hãy kiểm soát schema và tạo cột typed/generated phù hợp.

## 17. jsonb_typeof và validation nhẹ

Giả sử phone yêu cầu `ram_gb` là number, có thể kiểm tra:

```sql
SELECT
    sku,
    jsonb_typeof(attributes -> 'ram_gb') AS ram_type,
    attributes -> 'ram_gb' AS ram_value
FROM lesson_model_choice.products
WHERE category_id = 10;
```

Nếu key bị thiếu, `jsonb_typeof(attributes -> 'ram_gb')` là SQL NULL.

### CHECK cơ bản cho JSON object

Trong bảng hybrid đã có:

```sql
attributes JSONB NOT NULL
CHECK (jsonb_typeof(attributes) = 'object')
```

Điều này chặn một payload top-level array/string/number, nhưng **không chặn** document object thiếu những keys nghiệp vụ.

### Cần xem đặc tính SQL CHECK

Một `CHECK` chỉ từ chối khi expression trả **FALSE**. Nếu expression trả **SQL NULL/UNKNOWN**, constraint có thể được coi là không vi phạm. Ví dụ:

```sql
CHECK (jsonb_typeof(attributes -> 'ram_gb') = 'number')
```

không tự đủ mạnh để bắt buộc key `ram_gb` tồn tại, vì key thiếu khiến expression có thể trả NULL. Muốn bắt buộc:

```sql
CHECK (
    attributes ? 'ram_gb'
    AND jsonb_typeof(attributes -> 'ram_gb') = 'number'
)
```

Trong trường hợp thuộc tính chỉ áp dụng cho phone, cần thêm điều kiện theo category, đồng thời xem xét sự thay đổi loại category.

## 18. Validation theo danh mục: có những giới hạn nào?

Một rule mong muốn:

```text
Nếu category=PHONE:
  ram_gb phải là JSON number > 0
  screen_inches phải là JSON number > 0

Nếu category=BOOK:
  isbn phải có format hợp lệ
  pages phải là integer > 0
```

Với ba loại sản phẩm nhỏ và cố định, ràng buộc trong các bảng chuyên biệt như `phone_details` có thể rõ ràng hơn nhiều.

Với hàng trăm loại biến động, có thể dùng:

- Application-side schema validation có version rõ ràng.
- PostgreSQL constraints cho những bất biến cốt lõi, đơn giản.
- Trigger/extension kiểm tra JSON Schema khi môi trường cho phép.
- Bảng định nghĩa category attributes kết hợp validation logic.
- Pipeline kiểm tra dữ liệu đầu vào và tests contract.

**PostgreSQL không tự bảo đảm mọi document trong một cột jsonb tuân thủ một JSON Schema đầy đủ chỉ vì kiểu cột là jsonb.** JSONB bảo đảm cú pháp/giá trị hợp lệ, không biết quy tắc nghiệp vụ của bạn.

## 19. Kiểm tra có key bằng ? và giá trị bằng @>

`?` kiểm tra key **tại cấp trên cùng** của object hoặc string element thích hợp của array; nó không tự tìm key ở mọi độ sâu.

```sql
SELECT
    sku,
    attributes ? 'brand' AS has_brand,
    attributes ? 'warranty' AS has_warranty,
    attributes ? 'months' AS has_top_level_months
FROM lesson_model_choice.products;
```

Trong document có `{"warranty":{"months":24}}`, `attributes ? 'months'` có thể là FALSE vì `months` nằm **bên trong warranty**, không ở top-level.

### JSONB containment

```sql
SELECT sku, product_name
FROM lesson_model_choice.products
WHERE attributes @> '{"brand":"Acme"}'::jsonb;
```

`@>` kiểm tra document bên trái **chứa cấu trúc/giá trị JSON** bên phải theo quy tắc containment của `jsonb`.

Cho nested object:

```sql
SELECT sku
FROM lesson_model_choice.products
WHERE attributes @> '{"warranty":{"months":24}}'::jsonb;
```

### Đúng kiểu JSON

`{"ram_gb":16}` khác `{"ram_gb":"16"}` về kiểu number vs string. Truy vấn containment theo number không nên dùng để tìm dữ liệu producer đã vô tình ghi thành string rồi coi cả hai là tương đương.

## 20. Truy vấn JSON array

Document:

```json
{
  "connectivity": ["wifi", "bluetooth", "5g"]
}
```

Lọc những sản phẩm có `wifi`:

```sql
SELECT sku, product_name
FROM lesson_model_choice.products
WHERE attributes @> '{"connectivity":["wifi"]}'::jsonb;
```

Với containment, thứ tự phần tử array không phải điều kiện bắt buộc giống nhau như một phép so sánh array theo vị trí. Nó phù hợp với ý định “có phần tử” chứ không phải “danh sách đúng thứ tự này”.

### Kiểm tra key trong nested array

```sql
SELECT sku
FROM lesson_model_choice.products
WHERE attributes -> 'connectivity' ? '5g';
```

Ở đây `?` áp dụng lên **mảng được trích ra**, không phải top-level object.

Nếu `connectivity` bị thiếu hoặc không phải array như kỳ vọng, cần xử lý data quality; không coi việc query không thấy hàng là xác nhận payload đúng schema.

## 21. Mở mảng thành các hàng với jsonb_array_elements

```sql
SELECT
    p.sku,
    entry.value AS connectivity_value
FROM lesson_model_choice.products AS p
CROSS JOIN LATERAL jsonb_array_elements(
    p.attributes -> 'connectivity'
) AS entry(value)
WHERE p.category_id = 10
  AND jsonb_typeof(
      p.attributes -> 'connectivity'
  ) = 'array'
ORDER BY p.sku, entry.value;
```

`LATERAL` cho phép hàm bên phải dùng `p.attributes`. Mỗi phần tử JSON array trở thành một hàng.

### Cẩn thận khi dữ liệu bẩn

`jsonb_array_elements` yêu cầu input là JSON array; nếu gặp một JSON scalar/object không hợp lệ có thể báo lỗi. Điều kiện lọc trong SQL không nên được coi là lời hứa thứ tự đánh giá giúp mọi biểu thức an toàn trong mọi plan. Với data không đáng tin, chuẩn hóa input thành array bằng `CASE`:

```sql
SELECT
    p.sku,
    x.value
FROM lesson_model_choice.products AS p
CROSS JOIN LATERAL jsonb_array_elements(
    CASE
      WHEN jsonb_typeof(
          p.attributes -> 'connectivity'
      ) = 'array'
      THEN p.attributes -> 'connectivity'
      ELSE '[]'::jsonb
    END
) AS x(value);
```

Query này cho kết quả rỗng với key không phải array, nhưng **không thay thế validation**: dữ liệu sai dạng cần được ghi nhận/khắc phục tại ingest.

## 22. Các giá trị JSON không luôn nên được đưa ra bảng

Nếu một document có:

```json
{
  "resolution": {"width": 2560, "height": 1440},
  "certifications": ["A", "B"],
  "ui_hints": {"badge": "new"}
}
```

và ứng dụng chỉ hiển thị toàn bộ metadata ở màn chi tiết, **không filter/join/aggregate** theo các thuộc tính ấy, `jsonb` có thể rất phù hợp.

Tách mọi key thành một bảng riêng tạo ra:

- Nhiều JOIN chỉ để hiển thị một document.
- DDL cho những thuộc tính đổi liên tục.
- Hàng liên kết và indexes không cần thiết.
- Độ phức tạp cho code/ORM.

**Chuẩn hóa dữ liệu là công cụ để quản lý bất biến và quan hệ, không phải yêu cầu tách mọi object JSON thành các bảng dù không có lợi.**

## 23. Nhưng giá trị dùng JOIN cần được cân nhắc kỹ

Nếu trong JSON có:

```json
{"supplier_id": 1001}
```

và `supplier_id` phải tham chiếu bảng `suppliers`, giữ nó chỉ trong JSON sẽ không tự có **FOREIGN KEY** thông thường trên trường nested.

Một thiết kế dễ quản lý:

```sql
CREATE TABLE lesson_model_choice.suppliers (
    supplier_id BIGINT PRIMARY KEY,
    supplier_name TEXT NOT NULL
);

CREATE TABLE lesson_model_choice.product_suppliers (
    product_id BIGINT NOT NULL
        REFERENCES lesson_model_choice.products(product_id),
    supplier_id BIGINT NOT NULL
        REFERENCES lesson_model_choice.suppliers(supplier_id),
    PRIMARY KEY (product_id, supplier_id)
);
```

### Lợi ích

- Referential integrity.
- Một sản phẩm có nhiều suppliers.
- Truy vấn tất cả sản phẩm của supplier rõ ràng.
- Indexes và query plan theo khóa quan hệ.
- Tránh lỗi supplier_id trỏ đối tượng không tồn tại.

Nếu supplier chỉ là **tên gốc từ payload bên ngoài**, không phải một thực thể local có FK, lưu JSON có thể lại hợp lý.

## 24. Quan hệ nhiều-nhiều: bảng nối hay JSON array?

Giả sử sản phẩm có tags được dùng bởi bộ lọc, quản trị và thống kê.

**Phương án JSON array:**

```json
{"tags": ["new", "featured", "seasonal"]}
```

**Phương án quan hệ:**

```sql
CREATE TABLE lesson_model_choice.tags (
    tag_id BIGINT PRIMARY KEY,
    tag_code TEXT NOT NULL UNIQUE
);

CREATE TABLE lesson_model_choice.product_tags (
    product_id BIGINT NOT NULL
        REFERENCES lesson_model_choice.products(product_id)
        ON DELETE CASCADE,
    tag_id BIGINT NOT NULL
        REFERENCES lesson_model_choice.tags(tag_id),
    PRIMARY KEY (product_id, tag_id)
);
```

### Khi nào dùng bảng nối?

- Tag là thực thể có metadata, quyền, trạng thái riêng.
- Tag cần đổi tên mà không phải sửa mọi document.
- Cần FK, uniqueness và báo cáo đếm sản phẩm/tag.
- Có quan hệ nhiều-nhiều thực sự.
- Danh sách tags tăng và thay đổi liên tục.

### Khi nào JSON array vẫn phù hợp?

- Tags chỉ là metadata hiển thị/tùy biến.
- Không có từ điển tag trung tâm.
- Không cần FK hay quản trị riêng.
- Chủ yếu đọc toàn bộ document và thỉnh thoảng lọc containment.

Không có một câu trả lời duy nhất; quyết định phụ thuộc **vai trò của phần tử trong array**.

## 25. SQL array và JSON array khác nhau

PostgreSQL còn có SQL array, chẳng hạn `TEXT[]`:

```sql
CREATE TABLE lesson_model_choice.article_labels (
    article_id BIGINT PRIMARY KEY,
    labels TEXT[] NOT NULL DEFAULT ARRAY[]::text[]
);

INSERT INTO lesson_model_choice.article_labels (
    article_id, labels
)
VALUES
    (1, ARRAY['postgresql','database']),
    (2, ARRAY['json','postgresql']);
```

Truy vấn:

```sql
SELECT *
FROM lesson_model_choice.article_labels
WHERE labels @> ARRAY['postgresql']::text[];
```

Với SQL array:

- Kiểu phần tử thống nhất `TEXT[]`.
- Hỗ trợ toán tử array và GIN index khi cần.
- Không tự ràng buộc FK tới từng phần tử array.
- Không tự đảm bảo mỗi element xuất hiện một lần.
- Không thích hợp thay mọi quan hệ có thuộc tính riêng.

Với JSON array:

- Có thể chứa đối tượng nested, nhiều kiểu JSON theo tài liệu.
- Hợp cho payload document.
- Cần validation để tránh array lẫn kiểu không mong muốn.
- Query/extract/cast khác với SQL array.

**Nếu phần tử có khóa ngoại, trạng thái, thứ tự nghiệp vụ, quyền hoặc lifecycle riêng, hãy cân nhắc bảng con/bảng nối** thay vì cả SQL array lẫn JSON array.

## 26. Mảng có thứ tự và mảng như tập hợp

Một danh sách:

```json
["first","second","third"]
```

có thể mang ý nghĩa **thứ tự** (các bước workflow).

Nhưng danh sách:

```json
["wifi","5g","bluetooth"]
```

có thể chỉ là **tập tính năng**, thứ tự không quan trọng.

Nếu thứ tự là bất biến quan trọng và từng phần tử có thuộc tính, bảng:

```sql
CREATE TABLE lesson_model_choice.workflow_steps (
    workflow_id BIGINT NOT NULL,
    step_no INTEGER NOT NULL CHECK (step_no > 0),
    step_code TEXT NOT NULL,
    PRIMARY KEY (workflow_id, step_no)
);
```

có thể phù hợp hơn để ràng buộc số thứ tự và query từng bước.

### Cạm bẫy JSONB containment

`@>` trên JSONB array kiểm tra containment, không bảo đảm array có đúng **thứ tự** như ở vế phải. Nếu workflow đòi thứ tự, containment không phải kiểm tra tương đương toàn bộ chuỗi bước.

## 27. JSONB indexing: bắt đầu từ truy vấn thực tế

Đừng tạo một index GIN lên `attributes` chỉ vì “đã dùng JSONB”.

Trước hết phân loại các query:

1. `WHERE tenant_id = ? AND sku = ?` → B-tree unique trên cột quan hệ.
2. `WHERE price BETWEEN ? AND ?` → B-tree theo các cột typed.
3. `WHERE attributes @> '{"brand":"Acme"}'` → GIN có thể hỗ trợ containment.
4. `WHERE attributes ? 'color'` → GIN với operator class hỗ trợ key-existence.
5. `WHERE attributes->>'brand' = 'Acme'` → Expression B-tree có thể phù hợp.
6. `ORDER BY (attributes->>'ram_gb')::integer` → Expression/generated typed column và index phù hợp.

Một index phù hợp **operator và biểu thức của query**. Không phải GIN index tự hỗ trợ hiệu quả mọi so sánh range/sort của nested JSON.

## 28. GIN index trên jsonb

```sql
CREATE INDEX ix_products_attributes_gin
ON lesson_model_choice.products
USING GIN (attributes);
```

Operator class mặc định cho `jsonb` thường là **`jsonb_ops`**. Nó hỗ trợ nhiều operators, gồm containment và key-existence theo phạm vi operator class.

Ví dụ:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT product_id, sku
FROM lesson_model_choice.products
WHERE attributes @> '{"brand":"Acme"}'::jsonb;
```

Khi dữ liệu đủ lớn và predicate đủ chọn lọc, planner có thể cân nhắc GIN index. Với 5 sản phẩm lab, Seq Scan thường vẫn hợp lý.

### GIN không làm JSONB thành “bảng có cột ngầm”

GIN tạo các index entries phục vụ những phép tìm kiếm phù hợp, nhưng:

- Không tự ép kiểu/schema keys.
- Không tự có FK hay UNIQUE trên giá trị nested.
- Không giúp mọi `ORDER BY` numeric range.
- Có chi phí bộ nhớ/disk/WAL/insert/update.

## 29. jsonb_ops và jsonb_path_ops

PostgreSQL có các operator classes GIN quan trọng:

| Tính chất | `jsonb_ops` | `jsonb_path_ops` |
|---|---|---|
| Mặc định của GIN `jsonb` | Có | Không |
| `@>` containment | Hỗ trợ | Hỗ trợ |
| `?`, `?|`, `?&` key-existence | Hỗ trợ | Không hỗ trợ các toán tử này |
| JSONPath `@?`, `@@` ở phiên bản hỗ trợ | Hỗ trợ | Hỗ trợ theo quy tắc index |
| Kích thước và mức đặc hiệu | Có thể lớn hơn do nhiều entries | Thường nhỏ/đặc hiệu hơn cho containment |
| Tìm cấu trúc rỗng | Có đặc điểm khác | Có giới hạn đáng chú ý với những cấu trúc không chứa giá trị |

Index với path ops:

```sql
CREATE INDEX ix_products_attrs_path
ON lesson_model_choice.products
USING GIN (attributes jsonb_path_ops);
```

**Trong lab không nhất thiết giữ đồng thời cả hai GIN indexes** nếu chúng phục vụ workload trùng lặp. Lựa chọn nên dựa trên operator thực tế, kích thước index và hiệu năng đọc/ghi.

### Quy tắc chọn

Nếu ứng dụng cần `attributes ? 'key'` trực tiếp, `jsonb_path_ops` không thay thế hoàn toàn `jsonb_ops`.

Nếu workload chủ yếu là containment `@>` và cần index đặc hiệu hơn, path ops có thể đáng thử. Nhưng nó có giới hạn khi tìm các cấu trúc rỗng và cần kiểm tra các điều kiện cụ thể.

## 30. GIN trên toàn document hay expression index cho một key?

Giả sử query rất thường xuyên:

```sql
SELECT product_id, sku
FROM lesson_model_choice.products
WHERE tenant_id = 1
  AND attributes->>'brand' = 'Acme';
```

Một expression B-tree:

```sql
CREATE INDEX ix_products_tenant_brand
ON lesson_model_choice.products (
    tenant_id,
    (attributes ->> 'brand')
);
```

Nó phù hợp với phép equality trên expression `attributes->>'brand'` cùng tenant.

### So sánh

**GIN full document** thích hợp cho nhiều keys và query containment đa dạng.

**Expression B-tree** thích hợp nếu một vài keys ổn định được lọc bằng equality/range/sort thường xuyên.

**Generated column** thích hợp nếu một key đã trở nên cốt lõi và cần kiểu/ràng buộc minh bạch.

Không giữ thêm cả GIN và hàng chục expression indexes nếu chi phí ghi/dung lượng vượt lợi ích truy vấn. Dùng workload thực tế để quyết định.

## 31. Index cho số nằm trong JSONB

Giả sử điện thoại cần lọc:

```sql
SELECT
    sku,
    (attributes ->> 'ram_gb')::integer AS ram_gb
FROM lesson_model_choice.products
WHERE category_id = 10
  AND (attributes ->> 'ram_gb')::integer >= 12;
```

Giá trị trích từ `->>` là text, nên cần cast.

Một index:

```sql
CREATE INDEX ix_products_phone_ram
ON lesson_model_choice.products (
    ((attributes ->> 'ram_gb')::integer)
)
WHERE category_id = 10;
```

### Điều kiện bắt buộc

Tất cả rows đủ điều kiện partial index phải có giá trị có thể cast sang integer hoặc NULL theo ngữ nghĩa cho phép. Nếu một sản phẩm phone chứa:

```json
{"ram_gb": "unknown"}
```

thì việc tạo/cập nhật index có thể thất bại vì cast không hợp lệ. **Không dùng expression index để “hy vọng dữ liệu tự đúng kiểu”**; phải validation dữ liệu trước.

### Vì sao partial index?

`ram_gb` chỉ có ý nghĩa với phone (`category_id=10`). Index toàn bảng trên một biểu thức nullable ở phần lớn category có thể ít phù hợp hơn một partial index.

### Khi nào đưa hẳn thành cột?

Nếu RAM là filter/sort quan trọng, được thống kê báo cáo và phải có check/range theo loại, một cột typed/generated hoặc bảng `phone_details` có thể đơn giản hơn nhiều về lâu dài.

## 32. Generated column để đưa key JSON ra typed column

PostgreSQL hỗ trợ generated columns theo khả năng phiên bản. Với **stored generated column**:

```sql
CREATE TABLE lesson_model_choice.devices (
    device_id BIGINT PRIMARY KEY,
    details JSONB NOT NULL
        CHECK (jsonb_typeof(details) = 'object'),
    brand TEXT GENERATED ALWAYS AS (
        details ->> 'brand'
    ) STORED
);

CREATE INDEX ix_devices_brand
ON lesson_model_choice.devices (brand);
```

Khi `details` thay đổi, `brand` được tính từ expression theo cơ chế generated column.

### Lợi ích

- Query `WHERE brand = ?` rõ ràng.
- Có thống kê/index trên typed column.
- Không phải copy thủ công hai giá trị khi update.
- Có thể bổ sung ràng buộc phù hợp với column.

### Giới hạn

- Expression generated phải tuân thủ quy tắc PostgreSQL về tính bất biến, tham chiếu và kiểu dữ liệu.
- Stored column có chi phí lưu trữ và tính lại.
- Dữ liệu bẩn/cast sai có thể khiến write hoặc migration thất bại.
- Một số biến thể generated columns khác nhau theo PostgreSQL major version.

Nếu thông tin đã đủ ổn định, đôi khi **đổi hẳn thành cột bình thường** còn dễ hiểu hơn.

## 33. JSONPath cho truy vấn nested phức tạp

PostgreSQL 12+ hỗ trợ SQL/JSON path ở mức phù hợp.

Ví dụ:

```sql
SELECT sku
FROM lesson_model_choice.products
WHERE attributes @? '$.warranty.months ? (@ >= 24)';
```

`@?` kiểm tra xem biểu thức JSONPath có kết quả phù hợp.

### Tại sao cần JSONPath?

Các truy vấn nested array/object với điều kiện cấu trúc phức tạp đôi khi rõ hơn khi dùng JSONPath.

### Cẩn thận về indexing

GIN jsonb indexes có thể hỗ trợ **một số dạng điều kiện JSONPath** theo operator class và phiên bản, nhưng không có nghĩa mọi biểu thức JSONPath với range/computation đều indexable.

Đọc `EXPLAIN` và kiểm tra query thực tế, không giả định vì có `@?` thì index chắc chắn được dùng.

### JSONPath không là validation tự động

Query “tìm tài liệu có warranty.months >=24” không đảm bảo những tài liệu thiếu trường đó đều hợp lệ về nghiệp vụ. Validation schema vẫn là phần riêng.

## 34. Cập nhật một key với jsonb_set

Để đổi màu:

```sql
UPDATE lesson_model_choice.products
SET attributes = jsonb_set(
        attributes,
        '{color}',
        to_jsonb('red'::text),
        true
    ),
    updated_at = now()
WHERE tenant_id = 1
  AND sku = 'PHONE-A';
```

Giải thích:

- `attributes` là document hiện tại.
- `'{color}'` là path kiểu `text[]`.
- `to_jsonb('red'::text)` tạo JSON string value.
- Tham số `true` cho phép thêm key cuối nếu nó thiếu trong trường hợp path hợp lệ.

### Không hiểu là UPDATE vật lý một byte tại chỗ

Về mặt SQL, bạn cập nhật một key. Nhưng PostgreSQL dùng MVCC: câu `UPDATE` tạo phiên bản hàng mới; giá trị `jsonb` có thể được xây lại và chịu chi phí ghi/TOAST/index maintenance phù hợp.

Nếu một trường được cập nhật **liên tục với tần suất cao**, đặt nó trong JSON document lớn có thể tốn hơn so với cột typed hoặc bảng quan hệ riêng.

## 35. jsonb_set nested path và trường cha bị thiếu

`jsonb_set` có quy tắc về những thành phần path đã tồn tại. Ví dụ:

```sql
SELECT jsonb_set(
    '{}'::jsonb,
    '{warranty,months}',
    '24'::jsonb,
    true
);
```

Không nên giả định câu trên tự tạo mọi object trung gian `warranty` trong mọi trường hợp. Tham số `create_if_missing` không đồng nghĩa “tự xây cả cây object khi mọi ancestor đều thiếu”.

Nếu muốn xây object rõ ràng:

```sql
SELECT
    '{}'::jsonb ||
    jsonb_build_object(
        'warranty',
        jsonb_build_object('months', 24)
    ) AS merged;
```

### Phép || chỉ merge ở mức top-level phù hợp

`jsonb || jsonb` nối/merge cấu trúc theo quy tắc của operator, **không phải recursive deep merge**. Với hai object chứa cùng key `warranty`, object bên phải có thể thay thế toàn bộ value của key đó, không chỉ một subkey.

Khi cập nhật nested object cần bảo toàn sibling keys, dùng `jsonb_set`/cấu trúc có kiểm soát.

## 36. Xóa một key bằng toán tử -

```sql
SELECT
    '{"color":"red","brand":"Acme"}'::jsonb
      - 'color' AS without_color;
```

Kết quả JSONB conceptually:

```json
{"brand":"Acme"}
```

Có thể cập nhật:

```sql
UPDATE lesson_model_choice.products
SET attributes = attributes - 'color',
    updated_at = now()
WHERE tenant_id = 1
  AND sku = 'PHONE-A';
```

Với path nested, PostgreSQL còn hỗ trợ `#-` dùng text[] path:

```sql
SELECT
    '{"warranty":{"months":24,"provider":"Acme"}}'::jsonb
      #- '{warranty,provider}';
```

### Xóa key khác gán JSON null

`attributes - 'color'` làm **thiếu key**.

`jsonb_set(attributes,'{color}','null'::jsonb)` để key tồn tại nhưng value là JSON null. API PATCH, validation và các truy vấn `?` có thể phân biệt hai trạng thái.

## 37. JSONB và concurrency: lost update ở application

Một lỗi phổ biến:

```text
T1 đọc attributes = {"views": 10, "color": "black"}
T2 đọc attributes = {"views": 10, "color": "black"}

T1 sửa color trên object trong Java rồi UPDATE cả attributes
T2 tăng views trên object cũ rồi UPDATE cả attributes

Kết quả cuối có thể làm mất thay đổi từ T1 hoặc T2.
```

### Điều sai

Read-modify-write cả JSON document ở application mà không có transaction isolation/optimistic locking phù hợp.

### Cách tốt hơn khi chỉ sửa một key

Dùng một `UPDATE` tính giá trị mới từ **cột hiện tại trong database**:

```sql
UPDATE lesson_model_choice.products
SET attributes = jsonb_set(
        attributes,
        '{color}',
        to_jsonb('blue'::text),
        true
    )
WHERE product_id = 1;
```

Khi nhiều updates cùng hàng, PostgreSQL cần điều phối row-level locking và thực thi expression trên row version thích hợp theo isolation semantics. Đây là cách an toàn hơn nhiều so với việc overwrite cả document bằng snapshot cũ từ client.

**Nhưng** nếu nghiệp vụ cần bảo đảm điều kiện phức tạp qua nhiều hàng, vẫn cần transaction/locking/constraint tương ứng; `jsonb_set` không tự giải quyết mọi race.

## 38. Tăng counter JSON trong một UPDATE

Ví dụ một counter `views` trong document:

```sql
UPDATE lesson_model_choice.products
SET attributes = jsonb_set(
        attributes,
        '{views}',
        to_jsonb(
            COALESCE(
                (attributes ->> 'views')::bigint,
                0
            ) + 1
        ),
        true
    )
WHERE product_id = 1;
```

Đây là một statement tăng giá trị từ document hiện tại, chứ không đọc 10 về Java rồi ghi 11 mặc kệ transaction khác.

### Nhưng có nên lưu views trong JSONB?

Nếu views tăng hàng nghìn lần mỗi giây, mỗi UPDATE tác động row JSONB và tạo áp lực lock/MVCC/WAL. Thường tốt hơn:

- Dùng một cột counter riêng khi phù hợp.
- Dùng bảng counters chia theo key/partition để tránh hot row.
- Gom sự kiện và cập nhật định kỳ.
- Lưu events để aggregate ở hệ thống analytics.

**Việc một thứ có thể viết thành JSONB không có nghĩa đó là nơi lưu tối ưu cho tần suất cập nhật cao.**

## 39. Optimistic locking với version column

Trong một mô hình kết hợp, có thể thêm version để phát hiện cập nhật trên stale document:

```sql
CREATE TABLE lesson_model_choice.editable_documents (
    document_id BIGINT PRIMARY KEY,
    version BIGINT NOT NULL DEFAULT 0,
    payload JSONB NOT NULL
        CHECK (jsonb_typeof(payload) = 'object')
);
```

Khi client đã đọc `version=5`:

```sql
UPDATE lesson_model_choice.editable_documents
SET payload = '{"color":"blue"}'::jsonb,
    version = version + 1
WHERE document_id = 10
  AND version = 5
RETURNING version;
```

Nếu có 0 hàng được cập nhật, version đã thay đổi hoặc document không tồn tại; application phải phân biệt và xử lý conflict (reload/merge/retry hợp lý).

### Không retry mù quáng

Nếu hai người sửa những thông tin có ý nghĩa khác nhau, conflict cần chính sách merge/UX. Tự ghi đè với bản đọc mới mà không xét ý định user có thể mất dữ liệu.

## 40. Vì sao một JSONB document lớn có thể tốn hơn nhiều cột nhỏ?

PostgreSQL lưu hàng theo cơ chế MVCC. Khi một hàng cập nhật:

- Tạo row version mới.
- Có thể phải tạo lại giá trị JSONB đã chỉnh sửa.
- Có thể phát sinh WAL cho heap, index hoặc TOAST.
- Có thể phải ghi lại các phần dữ liệu TOAST tùy cơ chế lưu trữ/thao tác.
- Có thể làm tăng dead tuples và nhu cầu VACUUM.

Một JSONB object chứa 200 thuộc tính mà ứng dụng cập nhật 1 thuộc tính mỗi giây có thể tạo chi phí cao hơn mô hình tách trường nóng ra cột/bảng riêng.

### Không diễn giải thành “mỗi UPDATE luôn ghi nguyên 200 thuộc tính ra đĩa”

Chi phí vật lý thực tế phụ thuộc kích thước, compression/TOAST, HOT update eligibility, index entries và storage details. PostgreSQL có tối ưu nội bộ; muốn kết luận phải đo `EXPLAIN (ANALYZE, BUFFERS, WAL)` và thống kê storage.

Quy tắc thiết kế là **cân nhắc tần suất update và kích thước document**, không dựa vào một câu tuyệt đối về số bytes.

## 41. TOAST và kích thước JSONB

PostgreSQL có cơ chế **TOAST** để xử lý giá trị column lớn, có thể nén/lưu ngoài trang heap tùy chiến lược storage và kích thước.

Để xem kích thước biểu diễn:

```sql
SELECT
    sku,
    pg_column_size(attributes) AS stored_value_bytes
FROM lesson_model_choice.products
ORDER BY stored_value_bytes DESC;
```

### Chú ý ý nghĩa kích thước

`pg_column_size` phản ánh kích thước lưu trữ giá trị theo cơ chế PostgreSQL và có những chi tiết liên quan compression/TOAST. Không coi nó bằng kích thước HTTP JSON string sau serialization hoặc tổng bytes được ghi trong mỗi UPDATE.

### Khi document quá lớn

- Đọc một vài keys có thể đòi truy cập cấu trúc TOAST/giải nén tùy trường hợp.
- Update thường xuyên có thể tạo WAL/bloat.
- Query lấy cả document qua JDBC tăng network payload.
- GIN indexes trên nhiều keys/values có thể lớn.
- Backup/replication mang chi phí tương ứng với dữ liệu cập nhật.

Đừng nhúng file ảnh/video/base64 lớn vào JSONB nếu object storage/large-object design phù hợp hơn với hệ thống.

## 42. HOT update và indexes trên jsonb

PostgreSQL có **Heap-Only Tuple (HOT) update** trong những điều kiện phù hợp, giúp tránh cập nhật các index entries khi các điều kiện liên quan được thỏa.

Nếu bạn có GIN index trên toàn `attributes` và liên tục cập nhật `attributes`, khả năng HOT update có thể bị ảnh hưởng do cột liên quan index thay đổi.

### So sánh mô hình

**Một bảng:**

```text
products(product_id, price, stock, attributes JSONB)
GIN(attributes)
```

**Tách trường nóng:**

```text
products(product_id, price, attributes JSONB)
inventory(product_id, warehouse_id, quantity)
```

Với tồn kho cập nhật liên tục và attributes hiếm đổi, cách tách có thể:

- Giảm row width ở bảng cập nhật nóng.
- Hạn chế tác động của cập nhật stock lên GIN index attributes.
- Cải thiện lock granularity theo kho.
- Giữ semantics quan hệ cho warehouse.

Không có kết luận mặc định rằng tách luôn nhanh hơn; cần benchmark và đánh giá JOIN overhead/lifecycle.

## 43. Tồn kho nên là quan hệ, không phải object lồng quá sâu

Đây là mô hình dễ gặp nhưng khó ràng buộc:

```json
{
  "inventory": {
    "warehouse_10": 20,
    "warehouse_11": 15
  }
}
```

Hệ thống cần:

- FK warehouse tồn tại.
- `quantity >= 0`.
- Một product/warehouse chỉ có một dòng tồn kho.
- Giao dịch trừ tồn theo kho và tránh oversell.

Thiết kế quan hệ:

```sql
CREATE TABLE lesson_model_choice.warehouses (
    warehouse_id BIGINT PRIMARY KEY,
    warehouse_name TEXT NOT NULL
);

CREATE TABLE lesson_model_choice.inventory (
    product_id BIGINT NOT NULL
        REFERENCES lesson_model_choice.products(product_id),
    warehouse_id BIGINT NOT NULL
        REFERENCES lesson_model_choice.warehouses(warehouse_id),
    quantity INTEGER NOT NULL CHECK (quantity >= 0),
    PRIMARY KEY (product_id, warehouse_id)
);
```

### Cập nhật tồn kho nguyên tử

```sql
UPDATE lesson_model_choice.inventory
SET quantity = quantity - 1
WHERE product_id = 1
  AND warehouse_id = 10
  AND quantity >= 1
RETURNING quantity;
```

Nếu không có hàng, giao dịch không trừ được vì warehouse/product không khớp hoặc tồn kho không đủ; application xử lý theo nghiệp vụ.

Tình huống này cần **khóa và constraint đáng tin cậy**, không chỉ flex schema.

## 44. Đơn hàng: snapshot JSONB kết hợp cột quan hệ

Một đơn hàng đã được chốt phải giữ **giá và thông tin sản phẩm tại thời điểm đặt**, kể cả sau khi catalog thay đổi.

```sql
CREATE TABLE lesson_model_choice.orders (
    order_id BIGINT PRIMARY KEY,
    tenant_id BIGINT NOT NULL
        REFERENCES lesson_model_choice.tenants(tenant_id),
    ordered_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    order_status TEXT NOT NULL
        CHECK (order_status IN ('NEW','PAID','CANCELLED'))
);

CREATE TABLE lesson_model_choice.order_items (
    order_id BIGINT NOT NULL
        REFERENCES lesson_model_choice.orders(order_id),
    line_no INTEGER NOT NULL CHECK (line_no > 0),
    product_id BIGINT NOT NULL
        REFERENCES lesson_model_choice.products(product_id),
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    unit_price NUMERIC(12,2) NOT NULL
        CHECK (unit_price >= 0),
    product_snapshot JSONB NOT NULL
        CHECK (jsonb_typeof(product_snapshot) = 'object'),
    PRIMARY KEY (order_id, line_no)
);
```

### Vì sao lưu cả product_id và snapshot?

- `product_id` là FK tới sản phẩm hiện tại, cho truy vấn quan hệ.
- `unit_price` là giá chốt để tính tiền chính xác.
- `product_snapshot` lưu tên/thông số/ảnh/metadata khi mua.
- `quantity` là số nguyên có CHECK.

Nếu chỉ lưu `product_id` rồi truy vấn `products.price` khi hiển thị đơn cũ, giá có thể thay đổi — sai lịch sử giao dịch. Nếu chỉ lưu toàn bộ vào JSON mà không có cột unit_price typed, tính toán doanh thu/thuế có thể khó kiểm soát.

### Snapshot nên bất biến theo nghiệp vụ

Ứng dụng cần quy định khi nào snapshot được phép sửa (ví dụ chỉnh trước thanh toán) và không được thay bằng catalog mới sau khi đơn đã hoàn tất.

## 45. Tạo order item với snapshot nhất quán

Ví dụ insert order:

```sql
INSERT INTO lesson_model_choice.orders (
    order_id, tenant_id, order_status
)
VALUES (1001, 1, 'NEW');
```

Đưa một product vào item và tạo snapshot:

```sql
INSERT INTO lesson_model_choice.order_items (
    order_id, line_no,
    product_id, quantity,
    unit_price, product_snapshot
)
SELECT
    1001,
    1,
    p.product_id,
    2,
    p.price,
    jsonb_build_object(
        'sku', p.sku,
        'name', p.product_name,
        'attributes', p.attributes
    )
FROM lesson_model_choice.products AS p
WHERE p.tenant_id = 1
  AND p.sku = 'PHONE-A';
```

### Nhưng transaction thực tế phức tạp hơn

Ví dụ trên minh họa cách dựng snapshot, **không phải toàn bộ checkout transaction**. Một hệ thống thật phải xét:

- Kiểm tra tồn kho/giữ chỗ.
- Tính tax/discount/shipping tại thời điểm chốt.
- Tính toàn vẹn của tenant giữa order và product.
- Giá có thể thay đổi đồng thời.
- Idempotency của request.
- Commit/rollback và các bước thanh toán bên ngoài.

Snapshot JSONB không tự tạo atomicity giữa checkout và payment gateway.

## 46. Lưu sự kiện webhook: jsonb thường rất hợp lý

Payload từ đối tác:

```json
{
  "event_id": "evt_123",
  "event_type": "shipment.delivered",
  "version": "2026-01",
  "occurred_at": "2026-11-14T03:00:00Z",
  "data": {
    "shipment_id": "ship_99",
    "carrier": "Carrier A",
    "delivered_at": "2026-11-14T02:59:00Z"
  }
}
```

Thiết kế:

```sql
CREATE TABLE lesson_model_choice.webhook_events (
    inbound_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    provider TEXT NOT NULL,
    external_event_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    received_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    payload JSONB NOT NULL
        CHECK (jsonb_typeof(payload) = 'object'),
    processing_status TEXT NOT NULL DEFAULT 'PENDING'
        CHECK (processing_status IN (
            'PENDING','PROCESSED','FAILED'
        )),
    UNIQUE (provider, external_event_id)
);
```

### Vì sao hybrid tốt?

- `provider`/`external_event_id`: khóa idempotency typed và unique.
- `event_type`: lọc/route job.
- `received_at`: index/range/retention.
- `processing_status`: worker state.
- `payload`: lưu document từ bên ngoài thay đổi theo version.

Không nhất thiết chuyển mọi nested field của event thành cột ngay khi ingest, nhất là khi event chưa được xác thực/chuẩn hóa.

## 47. Lưu raw payload và signature: jsonb có đủ không?

Nhiều webhook providers ký dựa trên **chuỗi bytes HTTP body gốc**. JSONB có thể:

- Bỏ whitespace.
- Thay thứ tự các object keys khi hiển thị.
- Gộp duplicate keys.
- Thay biểu diễn numeric theo quy tắc JSONB.

Vì thế **không dùng `payload::text` từ jsonb để xác minh lại chữ ký yêu cầu raw bytes** nếu chữ ký yêu cầu bytes gốc.

Có thể lưu riêng raw payload bytes/text khi có yêu cầu audit/signature:

```sql
-- Ví dụ schema riêng cho nhu cầu lưu raw:
CREATE TABLE lesson_model_choice.raw_inbound_payloads (
    inbound_id BIGINT PRIMARY KEY,
    raw_body BYTEA NOT NULL,
    parsed_body JSONB,
    received_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

Việc xác minh chữ ký phải làm theo đặc tả của provider, dùng raw bytes và thuật toán bảo mật phù hợp.

## 48. JSONB và schema evolution

Ngày đầu document có:

```json
{"brand":"Acme","ram_gb":8}
```

Sau đó phiên bản mới:

```json
{"brand":"Acme","memory":{"ram_gb":8,"storage_gb":256}}
```

Một query cũ:

```sql
WHERE (attributes->>'ram_gb')::integer >= 8
```

có thể bỏ qua bản ghi mới, vì `ram_gb` đã chuyển vào `memory`.

**“Không cần ALTER TABLE” không đồng nghĩa “không cần migration”.** Bạn vẫn phải xử lý:

- Schema/version của payload.
- Readers cũ và mới.
- Index definitions.
- Validation.
- Backfill dữ liệu cũ.
- BI/reporting.
- Ứng dụng mobile/client cũ.

Nên gắn version rõ ràng khi cấu trúc có thay đổi lớn.

## 49. Quản lý phiên bản schema JSON

Một cách:

```json
{
  "schema_version": 2,
  "memory": {
    "ram_gb": 8,
    "storage_gb": 256
  }
}
```

Nhưng nếu version là trường hệ thống được query/route rất thường xuyên, đặt nó thành **cột quan hệ** cũng có thể phù hợp:

```sql
CREATE TABLE lesson_model_choice.versioned_payloads (
    payload_id BIGINT PRIMARY KEY,
    schema_version INTEGER NOT NULL
        CHECK (schema_version > 0),
    payload JSONB NOT NULL
        CHECK (jsonb_typeof(payload) = 'object')
);
```

### Chiến lược đọc

- Parser biết những phiên bản còn hỗ trợ.
- Normalize version cũ về một data transfer model thống nhất.
- Giới hạn thời hạn hỗ trợ version quá cũ.
- Báo lỗi/đưa vào dead-letter queue nếu version không nhận diện.
- Không lặng lẽ xem missing key là 0 khi điều đó thay đổi nghiệp vụ.

## 50. Migration từ JSONB sang cột quan hệ

Một thuộc tính ban đầu chỉ là metadata, sau đó trở thành filter quan trọng.

Ví dụ `brand`:

**Bước 1 — Thêm cột mới:**

```sql
ALTER TABLE lesson_model_choice.products
ADD COLUMN brand TEXT;
```

**Bước 2 — Backfill theo JSON:**

```sql
UPDATE lesson_model_choice.products
SET brand = attributes ->> 'brand'
WHERE brand IS NULL
  AND attributes ? 'brand';
```

**Bước 3 — Kiểm tra:**

```sql
SELECT
    product_id,
    sku,
    brand,
    attributes ->> 'brand' AS brand_in_json
FROM lesson_model_choice.products
ORDER BY product_id;
```

**Bước 4 — Thiết kế dual-read/dual-write hoặc cutover có kiểm soát.**

**Bước 5 — Chuyển query/index sang cột.**

**Bước 6 — Nếu cần và dữ liệu hợp lệ, bổ sung NOT NULL/CHECK/UNIQUE.**

### Cảnh báo race trong migration

Nếu producer vẫn ghi vào `attributes.brand` trong lúc backfill, cột `brand` có thể bị stale. Cần một kế hoạch nhất quán:

- Tạm dừng ghi tại thời điểm chuyển.
- Dual-write với transaction phù hợp.
- Trigger đồng bộ có kiểm soát.
- Backfill có kiểm tra chênh lệch, rồi chuyển source of truth.

Không copy một lần rồi mặc định mọi dữ liệu từ đó đồng bộ vĩnh viễn.

## 51. Migration ngược: từ cột quan hệ sang JSONB

Giả sử một nhóm thuộc tính rất ít dùng và nay biến động mạnh. Có thể:

1. Tạo cột `metadata JSONB NOT NULL DEFAULT '{}'`.
2. Backfill từ các cột hiện tại bằng `jsonb_build_object`.
3. Chuyển readers/writers.
4. Theo dõi consistency.
5. Chỉ drop cột cũ khi đã có kế hoạch rollback và không còn phụ thuộc.

Ví dụ:

```sql
SELECT jsonb_build_object(
    'sku', sku,
    'display_name', product_name,
    'price', price
)
FROM lesson_model_choice.products
LIMIT 3;
```

Đây là minh họa tạo JSON, **không khuyến nghị đưa SKU/giá khỏi cột quan hệ**. Chúng là những giá trị cốt lõi của mô hình mẫu.

### Chuyển kiểu cần xem dữ liệu hiện có

Không phải mọi `TEXT` đều là JSON hợp lệ; không áp dụng `::jsonb` tùy tiện cho cột chứa string thông thường. Nếu muốn lưu chuỗi text thành JSON string, dùng `to_jsonb(text_column)` thay vì coi text là JSON document.

## 52. Chọn nguồn dữ liệu chuẩn (*source of truth*)

Một bẫy của mô hình hybrid:

```text
products.price = 100
attributes.price = 120
```

Ứng dụng hiển thị 120 còn checkout tính 100. Đây là lỗi do **duplicate source of truth**.

Nguyên tắc:

- Mỗi thuộc tính nghiệp vụ quan trọng nên có **một nguồn chuẩn**.
- Nếu sao chép để cache/snapshot, phải nêu semantics và thời điểm.
- Snapshot quá khứ không nên được hiểu là giá hiện tại.
- Generated column có thể tránh dual-write khi expression cho phép.
- Nếu dual-write migration tạm thời, cần quy tắc reconciliation và kế hoạch loại một bản.

### Mô hình rõ ràng

```text
current_price ở products.price
  └── source of truth cho giá hiện tại

product_snapshot.price ở order_items
  └── snapshot bất biến của giao dịch quá khứ
```

Hai giá trị khác nhau là **chủ ý đúng** nếu thuộc hai thời điểm khác nhau, không phải inconsistency.

## 53. JSONB và audit/history

Một bản ghi JSONB có thể được sửa nhiều lần. Nếu cần biết:

- Ai đổi giá?
- Thuộc tính nào thay đổi?
- Từ giá trị nào sang giá trị nào?
- Hiệu lực từ thời điểm nào?

thì một cột `attributes` hiện tại không đủ.

Thiết kế history riêng:

```sql
CREATE TABLE lesson_model_choice.product_attribute_history (
    history_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    product_id BIGINT NOT NULL
        REFERENCES lesson_model_choice.products(product_id),
    changed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    changed_by TEXT,
    old_attributes JSONB NOT NULL,
    new_attributes JSONB NOT NULL
);
```

### Snapshot vs events

Lưu **old/new full document** dễ audit nhưng có thể tốn dung lượng. Lưu **patch/diff** tiết kiệm hơn ở một số workload, nhưng replay và truy vấn lịch sử phức tạp hơn.

Chọn theo:

- Yêu cầu pháp lý/kiểm toán.
- Thời gian lưu.
- Khả năng reconstruct.
- Tần suất thay đổi.
- Dung lượng và truy vấn theo thời gian.

Không mặc định JSONB tự cung cấp hệ thống auditing có actor/timestamp chính xác.

## 54. Ràng buộc toàn vẹn đa tenant

Nếu product có `tenant_id` còn order cũng có `tenant_id`, một `FOREIGN KEY(product_id)` đơn lẻ không tự ngăn order của tenant 1 tham chiếu product của tenant 2.

Có thể thiết kế **composite keys/FKs**:

```sql
ALTER TABLE lesson_model_choice.products
ADD CONSTRAINT uq_products_tenant_id_product_id
UNIQUE (tenant_id, product_id);
```

Một bảng tham chiếu cần có cả cột tenant/product và FK kết hợp:

```sql
CREATE TABLE lesson_model_choice.tenant_product_watchlist (
    tenant_id BIGINT NOT NULL,
    product_id BIGINT NOT NULL,
    added_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, product_id),
    FOREIGN KEY (tenant_id, product_id)
        REFERENCES lesson_model_choice.products(
            tenant_id, product_id
        )
);
```

### Vì sao không để tenant_id chỉ trong JSON?

Phạm vi tenant là yếu tố **bảo mật và toàn vẹn**. Nếu chỉ nằm ở nested JSON, FK/composite uniqueness/RLS policies có thể khó kiểm soát hơn.

**Không coi JSON chứa đúng tenant_id là kiểm soát ủy quyền.** Row-level security và application authorization phải được thiết kế/kiểm tra độc lập.

## 55. Chọn schema cho truy vấn BI và báo cáo

Một báo cáo doanh thu theo tenant/category:

```sql
SELECT
    p.tenant_id,
    p.category_id,
    COUNT(*) AS product_count,
    AVG(p.price) AS average_price
FROM lesson_model_choice.products AS p
GROUP BY p.tenant_id, p.category_id
ORDER BY p.tenant_id, p.category_id;
```

Quan hệ làm cho filter/aggregate có kiểu rõ.

Nếu cần báo cáo RAM trung bình điện thoại:

```sql
SELECT
    p.tenant_id,
    AVG((p.attributes ->> 'ram_gb')::numeric)
        AS average_ram_gb
FROM lesson_model_choice.products AS p
WHERE p.category_id = 10
  AND jsonb_typeof(
      p.attributes -> 'ram_gb'
  ) = 'number'
GROUP BY p.tenant_id;
```

### Vấn đề data quality

Nếu một hàng phone có `"ram_gb":"unknown"`, cast ở query có thể lỗi nếu thực thi theo đường không bảo đảm được dữ liệu hợp lệ; nên có validation/normalization trước khi chạy báo cáo trên dữ liệu không tin cậy. Với các chỉ tiêu BI chính thức, đưa trường sang cột typed hoặc staging có kiểm tra thường dễ quản trị hơn.

### BI có cần JSONB không?

Raw JSONB vẫn hữu ích để audit/integration. Nhưng mart/reporting tables có cột typed thường giúp sử dụng SQL/BI tools đơn giản, ổn định hơn.

## 56. EAV (Entity–Attribute–Value) có phải phương án thay JSONB?

Mô hình EAV:

```text
product_id | attribute_name | attribute_value
-----------+----------------+----------------
1          | color          | black
1          | ram_gb         | 8
1          | screen_inches  | 6.5
```

Nó rất linh hoạt nhưng gây trade-off:

- Nhiều hàng và JOIN/pivot cho một product.
- Value có thể phải lưu text, mất type safety nếu không thiết kế phức tạp.
- Khó CHECK theo loại và unique constraints theo semantics.
- Range sort numeric trên text dễ sai.
- Query filtering nhiều attributes có thể đắt.

**EAV không tự ưu việt hơn JSONB hay relational child tables.** Nó có thể phù hợp khi attributes có metadata quản trị/lifecycle riêng, được query độc lập và mô hình hóa cẩn thận.

### Nếu attributes là dữ liệu định nghĩa nghiệp vụ

Một bảng `attribute_definitions` với type, unit, allowed values có thể giúp validate EAV và JSONB; nhưng validation động trong database thường cần nhiều logic hơn những constraint cơ bản.

## 57. Indexing và kế hoạch truy vấn trên JSONB

Sử dụng:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT
    product_id,
    sku
FROM lesson_model_choice.products
WHERE tenant_id = 1
  AND attributes @> '{"brand":"Acme"}'::jsonb;
```

Kiểm tra:

- `Seq Scan` hay `Bitmap Index Scan`/`Bitmap Heap Scan`?
- Có dùng GIN index không?
- Estimated rows vs actual rows?
- Shared buffer reads/hits?
- Predicate filter được áp dụng ở đâu?
- Thời gian planning/execution?

Với bảng mẫu chỉ 5 hàng, **Seq Scan có thể là tối ưu**. Đừng coi việc planner bỏ GIN là bằng chứng index không hoạt động.

### Các giới hạn thực tế

GIN phù hợp với nhiều phép tồn tại/chứa nhưng không tự biến mọi range query:

```sql
WHERE (attributes->>'ram_gb')::int >= 12
ORDER BY (attributes->>'ram_gb')::int
```

thành một index range scan. Với workload kiểu này, B-tree expression/generated column phù hợp hơn.

## 58. Query JSONB nhiều điều kiện

Ví dụ:

```sql
SELECT sku
FROM lesson_model_choice.products
WHERE tenant_id = 1
  AND category_id = 10
  AND attributes @> '{"brand":"Acme"}'::jsonb
  AND (attributes ->> 'ram_gb')::integer >= 8;
```

Planner có thể dùng:

- Filter tenant/category qua B-tree.
- GIN containment index cho brand.
- Expression B-tree cho RAM.
- Bitmap index combination trong một số trường hợp.
- Hoặc Seq Scan nếu bảng nhỏ/chọn lọc thấp.

**Không có một index duy nhất tối ưu mọi điều kiện.** Khi workload quan trọng, cân nhắc chuẩn hóa những filter keys thành cột typed để tổ hợp điều kiện/index dễ dự đoán.

### Đừng tạo index bùng nổ theo mỗi JSON key

Nếu khách hàng có 500 thuộc tính tùy biến, tạo 500 B-tree indexes rất tốn kém. Cần phân cấp:

1. Core fields luôn typed.
2. 5–10 JSON keys phổ biến có indexes phù hợp.
3. Metadata ít tìm kiếm chỉ lưu JSONB.
4. Những search use cases quá rộng có thể cần search index/service riêng nếu PostgreSQL không còn đáp ứng hợp lý.

## 59. JSONB và thống kê planner

PostgreSQL thu thập statistics cho cột quan hệ như `price`, `tenant_id` và một số expression khi có index/statistics phù hợp. Với những keys tùy ý nằm sâu trong JSONB, cardinality/selectivity estimates có thể khó hơn.

Hệ quả:

- Planner có thể ước lượng sai tỷ lệ brand/category.
- Có thể chọn Seq Scan thay vì index scan hoặc ngược lại.
- Cardinality estimates sai ảnh hưởng joins/aggregates.

### Cách cải thiện

- `ANALYZE` sau khi dữ liệu thay đổi đáng kể.
- Expression index/statistics cho các keys quan trọng.
- Generated typed columns với statistics.
- Viết predicates khớp operator/index.
- Quan sát `EXPLAIN (ANALYZE, BUFFERS)` trên dữ liệu đại diện.

Không tăng `default_statistics_target` toàn server một cách mù quáng nếu bottleneck đến từ thiết kế query/JSON key extraction.

## 60. GIN index và chi phí ghi

GIN index trên `attributes` cho phép nhiều cách tìm kiếm, nhưng có chi phí:

- Tạo index có thể mất thời gian và không gian lưu trữ.
- Chèn/cập nhật document cần duy trì index entries.
- WAL/index bloat và vacuum/maintenance có thể bị ảnh hưởng.
- Khi thay đổi document rất thường xuyên, chi phí ghi có thể lớn.
- Những cấu hình GIN như fastupdate/pending list cần hiểu khi tuning theo workload.

### Một index không phải tối ưu miễn phí

Với product catalog mà attributes được đọc hàng nghìn lần và cập nhật vài lần/ngày, GIN có thể rất đáng giá.

Với counter/tồn kho được cập nhật hàng nghìn lần mỗi giây, JSONB+GIN cho mọi update thường là lựa chọn cần xem lại.

**Đọc/ghi ratio là một phần của quyết định mô hình hóa**, không chỉ của việc chọn index.

## 61. Sử dụng partial index cho JSONB

Giả sử chỉ sản phẩm active cần lọc theo brand:

```sql
CREATE INDEX ix_active_products_brand
ON lesson_model_choice.products (
    tenant_id,
    (attributes ->> 'brand')
)
WHERE status = 'ACTIVE';
```

Index có thể nhỏ hơn nếu nhiều sản phẩm inactive.

### Query cần phù hợp predicate

```sql
SELECT sku
FROM lesson_model_choice.products
WHERE tenant_id = 1
  AND status = 'ACTIVE'
  AND attributes ->> 'brand' = 'Acme';
```

Planner có thể sử dụng index nếu nó chứng minh query predicate hàm ý phần `WHERE status='ACTIVE'` của partial index.

### Prepared statements

Một query tổng quát `status = $1` không phải luôn được chứng minh tương đương predicate cụ thể trong generic plan. Cần đo query thật với cơ chế prepared statement của driver/server.

## 62. Unique constraint trên nested JSON key

Nếu `external_code` nằm trong JSON và phải unique theo tenant, có thể tạo unique expression index:

```sql
CREATE UNIQUE INDEX ux_products_tenant_external_code
ON lesson_model_choice.products (
    tenant_id,
    (attributes ->> 'external_code')
);
```

### NULL semantics

Nếu key bị thiếu hoặc value JSON null, `->>` trả SQL NULL. Unique index mặc định cho phép nhiều NULL; vì vậy index trên không đảm bảo **tối đa một document thiếu external_code**.

Trên PostgreSQL 15+, có thể cân nhắc `NULLS NOT DISTINCT` nếu nghiệp vụ thực sự muốn coi missing/null như một khóa trùng. Nhưng cần xem semantics: missing và explicit JSON null có thể đều trích thành SQL NULL.

### Nên đưa thành cột?

Nếu `external_code` là business key bắt buộc, có FK hoặc rất nhiều UPSERT, cột typed với `NOT NULL`/`UNIQUE` thường rõ ràng hơn một expression index ẩn tính duy nhất trong nested JSON.

## 63. Full-text search và JSONB

Không dùng `attributes @> ...` để thay mọi bài toán search text.

Ví dụ sản phẩm cần tìm từ khóa trong tên/mô tả:

- B-tree thích hợp cho equality/range/order.
- `pg_trgm` (extension) có thể giúp tìm substring/ILIKE phù hợp.
- Full-text search với `tsvector`/GIN phù hợp cho tìm kiếm ngôn ngữ theo nhu cầu.
- GIN jsonb thích hợp cho JSON containment/existence, không tự trở thành một search engine ngôn ngữ.

### Khi metadata có nhiều text fields

Có thể tạo một search document được chuẩn hóa từ core columns và các text attributes cần tìm, sau đó index theo cơ chế full-text phù hợp.

Không tự tạo index JSONB full document rồi tin mọi query `ILIKE '%term%'` trên một nested field sẽ chạy nhanh.

## 64. Thiết kế API: serialize JSONB và typed fields

Một API có thể trả:

```json
{
  "id": 42,
  "sku": "PHONE-A",
  "name": "Điện thoại A",
  "price": "12990000.00",
  "status": "ACTIVE",
  "attributes": {
    "brand": "Acme",
    "ram_gb": 8
  }
}
```

### Vì sao price đôi khi là string trong JSON API?

Một API có thể chủ động serialize decimal dạng string để tránh mất chính xác khi client xử lý IEEE-754 floating point; đó là **lựa chọn giao thức**. Trong PostgreSQL, `price` vẫn là `NUMERIC`, không phải vì API trả string mà database cần lưu text.

### Hạn chế “mở” toàn bộ JSON trực tiếp vào API

Nếu raw `attributes` chứa nội bộ:

```json
{"internal_cost": 9000000, "supplier_token": "..."}
```

thì trả nguyên document cho client có thể lộ thông tin. Cần DTO/serialization có chọn lọc và authorization.

**JSONB không có field-level access control tự động theo từng key** chỉ vì cột mang kiểu document.

## 65. JDBC: lưu JSONB bằng PreparedStatement

Với PostgreSQL JDBC driver, ứng dụng có thể dùng kiểu `PGobject` để bind JSONB:

```java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.SQLException;
import org.postgresql.util.PGobject;

public final class ProductWriter {
    public static void insert(
            Connection conn,
            long tenantId,
            long categoryId,
            String sku,
            String name,
            java.math.BigDecimal price,
            String attributesJson
    ) throws SQLException {
        PGobject json = new PGobject();
        json.setType("jsonb");
        json.setValue(attributesJson);

        String sql = """
            INSERT INTO lesson_model_choice.products(
                tenant_id, category_id, sku,
                product_name, price, attributes
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """;

        try (PreparedStatement ps = conn.prepareStatement(sql)) {
            ps.setLong(1, tenantId);
            ps.setLong(2, categoryId);
            ps.setString(3, sku);
            ps.setString(4, name);
            ps.setBigDecimal(5, price);
            ps.setObject(6, json);
            ps.executeUpdate();
        }
    }
}
```

Giả định đã có driver PG JDBC, connection và xử lý transaction tương ứng. `PGobject` chỉ giúp driver biết kiểu truyền; PostgreSQL vẫn parse/validate JSON theo khả năng của kiểu `jsonb`.

### Không ghép JSON thẳng vào SQL string

Không viết:

```java
String sql = "INSERT ... VALUES ('" + rawJson + "')";
```

Lối này dễ gây SQL injection/escaping errors và không tận dụng prepared statement. Hãy bind JSON value như parameter.

## 66. JDBC: đọc JSONB và parse bằng Jackson

`ResultSet.getString(...)` có thể lấy biểu diễn JSON cho cột, rồi Jackson parse:

```java
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import com.fasterxml.jackson.core.JsonProcessingException;

public final class ProductReader {
    private static final ObjectMapper JSON =
        new ObjectMapper();

    public static JsonNode readAttributes(
            Connection connection,
            long productId
    ) throws SQLException, JsonProcessingException {
        String sql = """
            SELECT attributes
            FROM lesson_model_choice.products
            WHERE product_id = ?
            """;

        try (PreparedStatement ps =
                connection.prepareStatement(sql)) {
            ps.setLong(1, productId);
            try (ResultSet rs = ps.executeQuery()) {
                if (!rs.next()) {
                    return null; // Không tìm thấy product.
                }
                return JSON.readTree(
                    rs.getString("attributes")
                );
            }
        }
    }
}
```

### Lưu ý

- `JsonNode` từ Jackson là object trong Java, không phải row schema tự động.
- Kiểm tra kiểu, key missing, null và schema_version.
- Không đọc document vài MB nếu endpoint chỉ cần `product_name` và `price`.
- Không trả toàn bộ attributes cho client nếu chứa nội dung nội bộ.
- PreparedStatement phải bind tất cả giá trị đầu vào thay vì nối chuỗi.

## 67. JDBC: query nested JSON an toàn

Ví dụ filter theo brand:

```java
String sql = """
    SELECT product_id, sku
    FROM lesson_model_choice.products
    WHERE tenant_id = ?
      AND attributes ->> 'brand' = ?
    ORDER BY product_id
    """;

try (PreparedStatement ps = conn.prepareStatement(sql)) {
    ps.setLong(1, tenantId);
    ps.setString(2, brand);

    try (ResultSet rs = ps.executeQuery()) {
        while (rs.next()) {
            long id = rs.getLong("product_id");
            String sku = rs.getString("sku");
            // Xử lý dữ liệu.
        }
    }
}
```

### Dynamic JSON key/path

Không ghép bừa JSON keys hoặc SQL identifier do người dùng nhập vào SQL. Nếu cần filter theo thuộc tính động:

- Dùng whitelist các keys được hỗ trợ.
- Sử dụng hàm/operator cho phép path/value dưới dạng parameter khi phù hợp.
- Giới hạn độ sâu/độ dài path.
- Không chấp nhận SQL fragments tùy ý từ client.
- Kiểm tra kiểu dữ liệu và limits để tránh query quá nặng.

**Parameterized values bảo vệ giá trị; còn cấu trúc SQL/identifier động vẫn phải được kiểm soát.**

## 68. Spring/JPA và JSONB: chọn ánh xạ hợp lý

Một ứng dụng Spring có thể:

- Dùng JDBC/JdbcTemplate và Jackson.
- Dùng Hibernate mappings hỗ trợ JSON theo phiên bản ORM cụ thể.
- Lưu attributes dưới dạng JSON string hoặc JsonNode theo lớp mapping.
- Dùng native SQL cho các operators `@>`, `?`, `jsonb_set` phù hợp.

### Tránh giả định ORM tự bảo vệ ràng buộc

Một field Java `Map<String,Object> attributes` không tự có:

- CHECK để bảo đảm JSON object.
- FK cho nested ids.
- Unique constraint cho business key.
- Validation versioned JSON schema.
- Concurrency safety cho read-modify-write.

Database constraints và migrations vẫn quan trọng.

### Dirty checking và overwrite

Một ORM có thể serialize lại cả document khi object thay đổi. Trong workload concurrent, cần hiểu transaction isolation, optimistic locking (`@Version`) và cách ORM sinh UPDATE.

Không bắt exception rồi tiếp tục dùng transaction Hibernate bị lỗi mà không rollback.

## 69. Security: JSONB không thay cho RLS

Một bảng đa tenant nên phân biệt:

- **Authentication:** ai đang đăng nhập?
- **Authorization:** user được phép truy cập tenant/product nào?
- **RLS/SQL filter:** bảo vệ dữ liệu ở database.
- **JSON validation:** payload có dạng/giá trị hợp lệ?

Nếu `tenant_id` nằm trong typed column, PostgreSQL có thể áp dụng chính sách RLS và indexing rõ ràng hơn. Đưa tenant_id vào `attributes.tenant_id` không làm authorization tự an toàn.

### Kiểu dữ liệu không quyết định quyền

JSONB là hình thức lưu dữ liệu, không phải lớp bảo mật. Những keys như internal notes, cost price, access token cần được tách/bảo vệ theo sensitivity và chính sách truy xuất.

### Audit SQL

Không log nguyên document chưa redact nếu có token/PII. Chỉ lưu identifiers, schema version, hash hoặc các fields cho phép theo retention policy.

## 70. Dữ liệu nhạy cảm và encryption

Nếu payload chứa thông tin cá nhân hoặc secrets:

- Tránh đưa token/password vào JSONB plain text không cần thiết.
- Bảo vệ bằng quyền database/ứng dụng.
- Dùng encryption at rest/in transit và key management phù hợp khi yêu cầu.
- Xem khả năng mã hóa theo trường ở tầng ứng dụng.
- Không tạo GIN index trên dữ liệu nhạy cảm rồi mở quyền truy vấn tùy ý.

**Encryption có trade-off:** dữ liệu mã hóa có thể không hỗ trợ containment/range queries như JSONB thông thường. Lựa chọn cần dựa trên nhu cầu bảo mật trước, không hy sinh dữ liệu nhạy cảm chỉ để có index dễ hơn.

## 71. Schema drift: khi cùng một key đổi kiểu

Ví dụ:

```json
{"ram_gb": 8}
```

và:

```json
{"ram_gb": "8 GB"}
```

hoặc:

```json
{"ram_gb": null}
```

Nếu query dùng:

```sql
(attributes ->> 'ram_gb')::integer
```

thì `"8 GB"` gây lỗi cast. Một SQL report có thể thất bại chỉ vì một producer gửi sai type.

### Biện pháp

1. Xác định schema/key types theo version.
2. Validate khi ingest.
3. Trả lỗi hoặc đưa vào quarantine payload sai.
4. Backfill/sửa dữ liệu lịch sử.
5. Đưa key quan trọng sang typed columns.
6. Theo dõi tỷ lệ missing/wrong types.

**Không dùng `COALESCE(...,0)` để che mọi trường hợp sai dữ liệu**, nhất là số liệu tài chính/kỹ thuật cần chính xác.

## 72. Thiết kế mô hình cho sự kiện lịch sử

Với event sourcing/log:

```sql
CREATE TABLE lesson_model_choice.business_events (
    event_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id BIGINT NOT NULL,
    aggregate_type TEXT NOT NULL,
    aggregate_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    event_version INTEGER NOT NULL CHECK (event_version > 0),
    occurred_at TIMESTAMPTZ NOT NULL,
    received_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    payload JSONB NOT NULL
        CHECK (jsonb_typeof(payload) = 'object')
);

CREATE INDEX ix_business_events_aggregate_time
ON lesson_model_choice.business_events (
    tenant_id,
    aggregate_type,
    aggregate_id,
    occurred_at
);
```

Đây là hybrid:

- Envelope metadata typed để lọc/định tuyến/đảm bảo thời gian.
- Payload document riêng theo event type/version.

### Event log khác bảng current state

Một bảng append-only event có thể giữ nhiều events cho cùng aggregate, trong khi current state là projection riêng. Không dùng JSONB payload như lý do bỏ quy tắc idempotency/order/version.

## 73. Định nghĩa metadata tùy biến của tenant

Một platform cho phép từng tenant tự khai báo thuộc tính sản phẩm:

```text
Tenant 1:
  custom.color
  custom.shipping_class

Tenant 2:
  custom.material
  custom.certification
```

JSONB là nơi lưu linh hoạt:

```json
{
  "custom": {
    "shipping_class": "fragile",
    "color": "black"
  }
}
```

Nhưng vẫn cần **attribute definition registry** ở cấp tenant:

```sql
CREATE TABLE lesson_model_choice.attribute_definitions (
    tenant_id BIGINT NOT NULL
        REFERENCES lesson_model_choice.tenants(tenant_id),
    attribute_code TEXT NOT NULL,
    value_type TEXT NOT NULL
        CHECK (value_type IN (
            'string','number','boolean','array'
        )),
    is_required BOOLEAN NOT NULL DEFAULT FALSE,
    PRIMARY KEY (tenant_id, attribute_code)
);
```

### Vì sao cần registry?

- UI biết field type.
- Validation biết allowed values.
- Search biết fields nào được phép filter.
- Có thể quản trị quyền/quota số attributes.
- Thống kê data quality.

Registry **không tự làm CHECK động trên mọi JSON key** chỉ vì nó tồn tại; application/trigger/validation pipeline vẫn phải thực thi quy tắc.

## 74. Giới hạn tùy biến để tránh document phát triển vô hạn

Một hệ thống cho phép key tùy ý cần giới hạn:

- Số lượng keys mỗi document.
- Độ sâu nested structure.
- Kích thước payload.
- Kiểu value và tối đa array length.
- Tên key hợp lệ.
- Những key được dùng filter.
- Quyền sửa một số keys.
- Tần suất cập nhật.

Nếu không, một khách hàng có thể tạo document rất lớn, tăng:

- Dung lượng bảng/TOAST.
- WAL khi update.
- Thời gian parse/serialize.
- Kích thước GIN indexes.
- Chi phí query/backup/replication.

**Schema linh hoạt cần governance tương ứng.**

## 75. Versioning và migration trong môi trường nhiều service

Một producer service bắt đầu gửi `memory.ram_gb` thay `ram_gb`. Một consumer service cũ vẫn đọc key cũ.

Chiến lược an toàn:

1. Định nghĩa schema version mới.
2. Cập nhật consumer để đọc **cả cũ và mới** theo version.
3. Cập nhật producer gửi định dạng mới.
4. Backfill tài liệu cũ khi cần.
5. Kiểm tra dữ liệu/usage còn ở version cũ.
6. Chỉ dừng hỗ trợ format cũ khi đã đủ điều kiện.

### Có thể dùng dual fields tạm thời?

Có, nhưng phải giới hạn thời gian và định nghĩa source-of-truth:

```json
{
  "schema_version": 2,
  "ram_gb": 8,
  "memory": {"ram_gb": 8}
}
```

Hai field có thể mâu thuẫn nếu producer không đồng bộ. Tốt hơn là có logic chuyển đổi version rõ ràng thay vì giữ duplication vĩnh viễn.

## 76. Mô hình JSONB không tự giảm số JOIN một cách có lợi

Một lý do dùng JSONB là “lấy một document khỏi cần JOIN”. Điều đó có thể đúng với view snapshot, nhưng **denormalization** có chi phí:

- Giá/tên supplier thay đổi, phải cập nhật nhiều documents.
- Có nguy cơ stale data.
- Không có FK tới nested ids.
- Document lớn qua network.
- Query danh sách theo supplier có thể tốn hơn join indexed.

### Khi denormalization có ích

- Dữ liệu là snapshot lịch sử và **không cần cập nhật theo nguồn mới**.
- Payload được đọc cùng nhau rất thường xuyên.
- Số lượng bản sao được kiểm soát.
- Quy tắc cập nhật/caching rõ ràng.

Không dùng JSONB để copy hàng loạt cả catalog, suppliers, warehouses và inventory chỉ nhằm tránh một vài JOIN.

## 77. Mô hình hỗn hợp và giao dịch

PostgreSQL có transaction ACID cho cả typed columns và `jsonb` trong cùng một transaction:

```sql
BEGIN;

UPDATE lesson_model_choice.products
SET price = price + 100000,
    attributes = jsonb_set(
        attributes,
        '{promotion_note}',
        to_jsonb('price updated'::text),
        true
    )
WHERE tenant_id = 1
  AND sku = 'PHONE-A';

COMMIT;
```

Nếu transaction rollback, thay đổi các cột trong row sẽ rollback theo cơ chế PostgreSQL. Không có chuyện JSONB “nằm ngoài transaction” chỉ vì cấu trúc dạng document.

### Nhưng external side effects thì khác

HTTP calls, email hoặc thao tác hệ thống ngoài database không tự rollback với transaction PostgreSQL. Sử dụng outbox/idempotency khi cần nhất quán giữa database và hệ ngoài.

## 78. Query planner không biết ý nghĩa nghiệp vụ của JSON key

Một key:

```json
{"stock": 5}
```

không tự nói cho PostgreSQL rằng:

- Stock không được âm.
- Stock thuộc một warehouse.
- Chỉ một hàng tồn kho/product/warehouse.
- Các cập nhật cần chống oversell.

Tương tự, `{"price": 100}` không tự có numeric precision hay currency semantics.

**Ràng buộc nghiệp vụ là phần thiết kế riêng.** Với trường có hậu quả lớn khi sai, typed columns và constraints giúp đưa quy tắc xuống gần dữ liệu hơn.

## 79. Mẫu quyết định: lựa chọn theo 6 tiêu chí

Một bảng scorecard:

| Câu hỏi | Quan hệ mạnh | JSONB mạnh | Kết hợp |
|---|---|---|---|
| Bất biến có FK/UNIQUE/CHECK chặt? | Có | Không phải thế mạnh mặc định | Core ở cột |
| Cấu trúc thay đổi mỗi tenant/version? | Tốn schema/migrations | Có | Attributes ở JSONB |
| Truy vấn range/sort/aggregate thường xuyên? | Có | Cần cast/index | Hot query keys ở cột |
| Đọc/ghi nguyên payload thường xuyên? | Phải reconstruct | Có | Snapshot/payload |
| Cập nhật một field nóng liên tục? | Có thể tách/khóa rõ | Update document có chi phí | Field nóng ở cột/bảng |
| Phân tích BI/FK/joins nhiều? | Có | Phức tạp hơn | Quan hệ cho dimensions |

### Một quy tắc ngắn

> **Đưa bất biến cốt lõi và quan hệ giữa các thực thể vào schema quan hệ; đưa metadata biến thiên, ít ràng buộc và snapshot vào jsonb; chỉ chuyển dữ liệu qua ranh giới khi có bằng chứng về yêu cầu hoặc hiệu năng.**

Đây là gợi ý, không phải luật tuyệt đối. Một hệ thống document-centric có thể dùng `jsonb` làm nguồn chính hợp lý; một hệ thống kế toán giao dịch thường cần quan hệ nhiều hơn.

## 80. Các sai lầm phổ biến

**“Có JSONB thì không cần schema.”** Sai. Schema vẫn tồn tại dưới dạng contract ở application/producer/consumer và cần versioning/validation.

**“JSONB luôn nhanh hơn JOIN.”** Không. Tùy data volume, index, update rate và query.

**“PostgreSQL JSONB là NoSQL database hoàn toàn khác ACID.”** Không. JSONB là kiểu dữ liệu nằm trong PostgreSQL transactional engine.

**“JSONB giữ đúng raw JSON bytes và thứ tự keys.”** Không. Dùng raw text/bytea nếu cần xác minh chữ ký hoặc bảo tồn biểu diễn.

**“JSON number và JSON string tự bằng nhau.”** Không. `{"ram":8}` khác `{"ram":"8"}` về type.

**“Không có key và key:null là giống nhau.”** Không. `?` có thể phân biệt sự tồn tại key.

**“SQL NULL và JSON null là một.”** Không. Chúng có ngữ nghĩa riêng.

**“attributes->>'ram_gb' đã là integer.”** Không. `->>` trả SQL text.

**“Cast JSON text sang int luôn an toàn.”** Không. Dữ liệu sai kiểu hoặc text không chuyển được sẽ báo lỗi.

**“CHECK(jsonb_typeof(x->'k')='number') bắt buộc key.”** Không đủ; missing key có thể trả SQL NULL và CHECK không tự từ chối UNKNOWN.

**“GIN index làm mọi điều kiện trên JSON nhanh.”** Không. Operator class, expression và filter selectivity quyết định.

**“jsonb_path_ops hỗ trợ mọi toán tử của jsonb_ops.”** Không. Key-existence `?`/`?|`/`?&` có khác biệt.

**“GIN index hỗ trợ tốt ORDER BY (json->>'score')::int.”** Không mặc định. Cân nhắc B-tree expression/generated typed field.

**“Index expression cast sẽ sửa dữ liệu bẩn.”** Không. Nó có thể thất bại khi cast không hợp lệ.

**“Partial index hoạt động cho mọi parameterized query.”** Không. Planner cần chứng minh predicate phù hợp, generic plan có giới hạn.

**“jsonb_set sửa một byte tại chỗ không có WAL.”** Không. UPDATE theo MVCC và storage/index/TOAST có chi phí.

**“Đặt stock trong JSONB làm tránh race.”** Không. Race/lost updates vẫn cần transaction, atomic UPDATE/locking.

**“JSONB tự đảm bảo foreign key tới supplier_id nested.”** Không. Cần thiết kế khóa/constraint phù hợp.

**“JSON array thay thế mọi bảng nối.”** Không. Quan hệ nhiều-nhiều có metadata/FK/lifecycle riêng thường hợp với bảng nối.

**“SQL array có FK tự động tới từng element.”** Không.

**“Thêm column và backfill một lần là migration hoàn tất.”** Không nếu còn writer cũ hoặc consumers chưa đổi.

**“Schema version trong JSON tự làm client tương thích.”** Không. Cần conversion/validation/rollout.

**“Duplication price trong cột và JSON không ảnh hưởng.”** Sai nếu cả hai cùng bị coi là current source of truth.

**“JSONB là audit log tự động.”** Không. Cần actor/timestamp/history hoặc event records.

**“CTE/GIN/JSONB luôn là tối ưu.”** Không. Cần đo plan, memory, CPU, WAL, disk và concurrency.

**“JSONB phù hợp nhất với mọi metadata vì không cần migrations.”** Không. Phần metadata được filter/sort/chịu constraints thường xuyên có thể trở thành first-class columns.

**“Mọi trường nên chuẩn hóa vì relational là chuẩn.”** Không. Những document/snapshot ít query độc lập có thể nên ở JSONB.

## 81. Checklist cho buổi design review

Trước khi phê duyệt một schema có `jsonb`, trả lời:

1. Các khóa/quan hệ cốt lõi đã được tách thành cột typed và có PK/FK/UNIQUE chưa?
2. Những JSON keys nào bắt buộc, kiểu dữ liệu và allowed values là gì?
3. Sự khác nhau giữa missing key, JSON null và SQL NULL có được định nghĩa không?
4. Có versioning và chính sách tương thích ngược không?
5. Các queries quan trọng dùng operators nào, có index phù hợp không?
6. Có search/range/sort trên numeric JSON cần đưa ra typed field không?
7. Tài liệu có chứa foreign IDs hay collections nên thành bảng nối không?
8. Có trường nào cập nhật rất thường xuyên không?
9. Dung lượng doc và GIN index tăng thế nào khi có nhiều tenant?
10. Có thống kê planner/benchmark trên data distribution đại diện không?
11. Có phân biệt current state và immutable snapshot không?
12. Có nguồn sự thật duy nhất cho giá/status/identity không?
13. Có idempotency/unique keys và concurrency policy không?
14. Migrations/backfill/rollback sẽ thực hiện ra sao khi schema evolve?
15. JSONB có chứa secret hoặc dữ liệu không được phép trả cho client không?

Đây là checklist **thiết kế hệ thống**, không thay cho kiểm tra logic và chất lượng nội dung bài học trong các giai đoạn QA riêng của quy trình.

## 82. Quy trình giải quyết bài toán mô hình hóa thực tế

### Bước 1 — Viết bất biến trước

Ví dụ: “Mỗi tenant không có hai SKU giống nhau”, “giá hiện tại luôn >=0”, “mỗi product/warehouse có một số tồn”, “đơn hàng phải lưu giá lúc mua”.

### Bước 2 — Xác định entity và mối quan hệ

Tenant, product, category, supplier, warehouse, order, order item, tag.

### Bước 3 — Phân nhóm thuộc tính

- Core typed.
- Optional nhưng ổn định.
- Metadata tùy loại.
- Snapshot/historical.
- Event/raw inbound.

### Bước 4 — Chọn schema

Đưa keys, quan hệ và trường nóng vào cột/bảng; phần biến động vào jsonb nếu lợi ích thực.

### Bước 5 — Thiết kế validation

DB constraints cho core; schema version và validation contract cho JSON keys.

### Bước 6 — Thiết kế indexes theo workload

B-tree cho lookup/range/order, GIN cho containment/existence, expression/generated columns cho keys được dùng nhiều.

### Bước 7 — Tính write amplification/concurrency

Đánh giá document size, update frequency, HOT/TOAST/WAL, lost-update protection, connection pool.

### Bước 8 — Kiểm thử schema evolution

Producer cũ/mới, missing keys, explicit null, wrong type, backfill và rollback.

### Bước 9 — Chạy benchmark

Đo latency, buffer usage, index size, WAL, locks và throughput với dữ liệu đại diện.

### Bước 10 — Đánh giá vận hành

Retention/audit, bảo mật, migrations, backups và query observability.

## 83. Bài tập thực hành

### Bài 1 — Chọn mô hình

Một bảng khách hàng có customer_id, email, tên, ngày đăng ký và preferences JSON tùy ý. Đề xuất schema và giải thích trường nào là cột quan hệ, trường nào nên là JSONB.

### Bài 2 — Phân biệt json và jsonb

Chạy `SELECT '{"a":1,"a":2}'::json` và `::jsonb` tương ứng. Mô tả sự khác nhau về duplicate keys và khả năng bảo tồn đầu vào.

### Bài 3 — Kiểu JSON

Sử dụng `jsonb_typeof` với object, array, string, number, boolean và JSON null. So sánh với SQL NULL.

### Bài 4 — Missing key

Cho `{"color":null}` và `{}`. Dùng `?`, `->` và `->>` để phân biệt key hiện hữu nhưng null với key thiếu.

### Bài 5 — CHECK JSON object

Tạo bảng có `attributes JSONB NOT NULL CHECK(jsonb_typeof(attributes)='object')`. Thử chèn array, number và object. Trường hợp nào hợp lệ?

### Bài 6 — CHECK bắt buộc key

Viết CHECK đòi `attributes ? 'ram_gb'` và `jsonb_typeof(attributes->'ram_gb')='number'`. Giải thích tại sao chỉ so sánh jsonb_typeof chưa đủ.

### Bài 7 — Bảng quan hệ rộng

Phân tích `products_wide` có phone_ram_gb, shoe_size_eu, book_isbn. Khi nào nhiều cột nullable còn đơn giản hơn `jsonb`?

### Bài 8 — Bảng con theo loại

Thiết kế bảng `products_base` và `phone_details` có FK/PK/CHECK. Cần bổ sung gì nếu muốn bảo đảm một phone_details luôn tham chiếu product có category PHONE?

### Bài 9 — Hybrid catalog

Dùng bảng `products` mẫu. Thêm sản phẩm “giày” có thuộc tính riêng, giữ SKU/giá/status ở cột typed. Giải thích vì sao không cần ALTER TABLE.

### Bài 10 — Đọc nested key

Lấy `warranty.months` và `warranty.provider` từ `attributes` bằng `#>`/`#>>`. Khi provider thiếu thì query trả gì?

### Bài 11 — Lọc containment

Viết query tìm các sản phẩm brand Acme bằng `@>`. Thử query cùng key nhưng value số/string khác kiểu; mô tả kết quả.

### Bài 12 — Array containment

Tìm phone có connectivity chứa `wifi` bằng `@>`. Tại sao containment không phải phép so sánh đúng thứ tự mảng?

### Bài 13 — LATERAL unnest JSON

Dùng `jsonb_array_elements` để mở connectivity thành nhiều hàng. Xử lý key missing/not-array thế nào để tránh lỗi ở dữ liệu không đáng tin?

### Bài 14 — SQL array

Tạo bảng có `labels TEXT[]`. So sánh filter array containment với JSON array. Vì sao cả hai không tự bảo đảm FK đến bảng labels?

### Bài 15 — Bảng nối

Thiết kế `tags` và `product_tags`. Nêu ít nhất ba yêu cầu nghiệp vụ khiến bảng nối phù hợp hơn JSON array.

### Bài 16 — GIN index

Tạo GIN trên `attributes`, chạy `EXPLAIN (ANALYZE, BUFFERS)` với predicate `@>`. Tại sao trên 5 rows planner có thể vẫn chọn Seq Scan?

### Bài 17 — jsonb_ops/path_ops

So sánh operators được hỗ trợ. Nếu API dùng `attributes ? 'color'` rất thường xuyên, nên tránh giả định điều gì về `jsonb_path_ops`?

### Bài 18 — Expression B-tree

Tạo index trên `(tenant_id, attributes->>'brand')` và chạy query lọc cùng biểu thức. Khi nào expression index có thể có lợi hơn full-document GIN?

### Bài 19 — Numeric key

Tạo partial expression index cho `(attributes->>'ram_gb')::integer` của phone. Tại sao phải validate kiểu trước khi index/create/update?

### Bài 20 — Generated column

Tạo bảng `devices` có details JSONB và brand stored generated column. So sánh với ứng dụng tự dual-write brand vào cả cột và JSONB.

### Bài 21 — JSONPath

Lọc warranty.months >=24 bằng `@?`. Giải thích tại sao GIN không bảo đảm index hóa hiệu quả mọi điều kiện JSONPath.

### Bài 22 — jsonb_set

Đổi color của PHONE-A bằng `jsonb_set`. Vì sao một thay đổi logic nhỏ vẫn có chi phí MVCC/TOAST/WAL?

### Bài 23 — Nested update

Thử cập nhật `warranty.months` khi toàn bộ key `warranty` chưa tồn tại. Giải thích giới hạn của `create_if_missing` và cách dựng object cha rõ ràng.

### Bài 24 — Xóa key

So sánh `attributes - 'color'` với gán `"color":null`. Với API PATCH, hai thao tác nên mang ý nghĩa gì?

### Bài 25 — Concurrent JSON updates

Hai clients đọc cùng document rồi ghi lại cả document. Mô tả lost update. Đề xuất atomic UPDATE bằng `jsonb_set` hoặc version column.

### Bài 26 — Hot counter

Một trường `views` tăng 1000 lần/giây nằm trong JSONB có GIN. Hãy đề xuất mô hình thay thế và giải thích chi phí write amplification.

### Bài 27 — Inventory

Thiết kế bảng `inventory(product_id,warehouse_id,quantity)` với FK/PK/CHECK. Viết UPDATE trừ một đơn vị chỉ khi `quantity>=1`.

### Bài 28 — Order snapshot

Giải thích vì sao `order_items` lưu cả FK `product_id`, `unit_price` và `product_snapshot JSONB`. Nếu catalog đổi tên/giá sau khi mua, dữ liệu nào dùng hiển thị hóa đơn cũ?

### Bài 29 — Webhook payload

Thiết kế bảng webhook lưu `provider`, `external_event_id` unique, `event_type`, `received_at` và JSONB payload. Vì sao business key không nên chỉ nằm trong JSON?

### Bài 30 — Raw signature

Webhook provider ký raw HTTP body. Vì sao không thể dựa vào `payload::text` từ JSONB để xác minh chữ ký của bytes gốc?

### Bài 31 — Schema versioning

Producer chuyển `ram_gb` sang `memory.ram_gb`. Lập kế hoạch consumer rollout, backfill và tắt hỗ trợ version cũ.

### Bài 32 — Chuyển JSON key thành cột

Brand trở thành filter dùng hàng nghìn lần/giây. Mô tả thêm cột, backfill, đồng bộ với writer, index/cutover và rollback strategy.

### Bài 33 — Source of truth

Nếu giá tồn tại ở `products.price` và `attributes.price`, làm sao ngăn inconsistency? Vì sao `order_items.unit_price` có thể vẫn khác giá sản phẩm hiện tại mà không phải bug?

### Bài 34 — EAV

Đề xuất ba tiêu chí khiến EAV phù hợp, ba rủi ro của mô hình EAV text-based, rồi so với JSONB và bảng con.

### Bài 35 — BI/reporting

Viết query tính số sản phẩm và giá trung bình theo tenant/category bằng cột quan hệ. Viết tiếp báo cáo RAM trung bình phone từ JSONB; phân tích data quality/cast.

### Bài 36 — Query performance

So sánh `EXPLAIN` của lookup theo SKU, containment brand và numeric RAM range. Đề xuất index phù hợp từng query.

### Bài 37 — Partial index

Tạo partial index cho brand của sản phẩm ACTIVE. Tại sao generic prepared statement với `status=$1` có thể không dùng index như mong đợi?

### Bài 38 — UNIQUE nested key

Tạo unique expression index cho external_code trong JSON theo tenant. Khi key thiếu/JSON null, semantics UNIQUE mặc định là gì?

### Bài 39 — Data security

Một JSONB attributes chứa `supplier_token` và `internal_cost`. Thiết kế DTO và quyền truy cập để không lộ keys khi API trả product.

### Bài 40 — Tổng hợp kiến trúc

Một nền tảng đa tenant cần:

- SKU và external_id duy nhất trong tenant.
- Giá và tồn kho có ràng buộc chặt.
- Hàng nghìn thuộc tính tùy loại/tenant.
- Bộ lọc theo brand, RAM, price, active status.
- Lưu đơn hàng với giá/tên/thông số lúc mua.
- Nhận webhook từ nhiều providers với schema version khác nhau.
- Cập nhật tồn kho hàng nghìn lần/phút.

Hãy thiết kế **mô hình kết hợp**, giải thích vị trí của typed columns/FKs/JSONB/arrays/tables, indexes, validation schema, migration strategy, concurrency và audit/snapshot. Đồng thời nêu ít nhất ba trường hợp bạn **không** chọn JSONB dù dữ liệu có thể biểu diễn bằng JSON.

## Kết luận

**Bảng quan hệ, `jsonb` và mô hình kết hợp là những lựa chọn bổ sung nhau.** Dữ liệu có danh tính, khóa ngoại, quy tắc duy nhất, kiểu số chính xác, quan hệ nhiều-nhiều và tần suất cập nhật cao thường nên được biểu diễn bằng bảng/cột typed. Metadata linh hoạt, cấu trúc khác nhau theo category/tenant, payload từ API ngoài và snapshot lịch sử thường là những trường hợp `jsonb` phát huy lợi thế. SQL array có thể phù hợp cho danh sách phần tử đồng nhất đơn giản, còn bảng nối tốt hơn khi phần tử có quan hệ và lifecycle riêng.

Trong PostgreSQL, `jsonb` **không phải dữ liệu vô cấu trúc không ràng buộc**. Bạn vẫn phải quyết định các keys bắt buộc, phân biệt SQL NULL/JSON null/missing key, bảo vệ kiểu dữ liệu, xác định schema version và xử lý updates đồng thời. Các toán tử `->`, `->>`, `?`, `@>`, JSONPath, `jsonb_set` cùng GIN/expression indexes cho nhiều khả năng truy vấn, nhưng không thay thế `PRIMARY KEY`, `FOREIGN KEY`, `CHECK` và việc đưa những thuộc tính quan trọng ra cột typed.

Mô hình **kết hợp** thường mạnh nhất khi ranh giới rõ ràng: **core data quan hệ là nguồn chuẩn cho bất biến và JOIN; JSONB dành cho phần biến động hoặc snapshot có contract; các fields nóng/được dùng nhiều trong BI/search được mô hình hóa/index phù hợp**. Đừng che duplicate source-of-truth bằng cách lưu cùng dữ liệu ở nhiều nơi mà không có semantics.

Cuối cùng, lựa chọn phải được xác nhận bằng **workload thực**, không chỉ độ tiện khi INSERT document: xem khả năng lọc, index, thống kê planner, row width/TOAST, MVCC/WAL khi cập nhật, quyền truy cập, migration, phiên bản payload và áp lực concurrency. Một thiết kế tốt giúp PostgreSQL cưỡng chế điều cần đúng, đồng thời vẫn đủ linh hoạt để mở rộng dữ liệu mà không biến JSONB thành một kho chứa không có quy tắc.
