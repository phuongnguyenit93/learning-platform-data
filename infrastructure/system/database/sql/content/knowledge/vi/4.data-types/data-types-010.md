# Kiểu JSON, mảng và kiểu mở rộng theo hệ quản trị trong SQL

Các kiểu dữ liệu SQL quen thuộc như `INTEGER`, `VARCHAR`, `DATE` và `DECIMAL` thích hợp với những giá trị có cấu trúc ổn định. Nhưng ứng dụng thực tế còn phải lưu cấu hình linh hoạt, danh sách phần tử, tọa độ địa lý, địa chỉ mạng, khoảng thời gian, tài liệu XML hoặc các giá trị chuyên ngành. Nhiều hệ quản trị cơ sở dữ liệu (DBMS) cung cấp **kiểu JSON**, **kiểu mảng** và **kiểu mở rộng/chuyên biệt** cho những tình huống này.

Mục tiêu của việc chọn các kiểu đó không phải là làm cho bảng ít cột nhất, mà là diễn đạt đúng ý nghĩa dữ liệu, truy vấn được hiệu quả và vẫn giữ được tính toàn vẹn. Một cột JSON có thể rất hữu ích cho thuộc tính thay đổi thường xuyên, nhưng không tự thay thế được các quan hệ, khóa ngoại và ràng buộc của mô hình dữ liệu quan hệ.

> Các ví dụ chính trong bài dùng **PostgreSQL** vì hệ này hỗ trợ rõ ràng cả `JSONB` lẫn mảng có kiểu phần tử. Cú pháp, kiểu lưu trữ, toán tử, chức năng chỉ mục và phiên bản hỗ trợ của MySQL, SQL Server, Oracle, SQLite không hoàn toàn tương đương. Khi chuyển DBMS, cần viết lại phần phụ thuộc hệ quản trị.

## 1. Phân biệt JSON, mảng SQL và cấu trúc quan hệ

Giả sử một sản phẩm có tên, giá, các nhãn và một số tùy chọn giao diện:

- `name` và `price` có cấu trúc cố định, được dùng trong hầu hết truy vấn: nên là **cột quan hệ riêng**.
- `tags` là danh sách ngắn các chuỗi cùng loại: có thể là **mảng SQL** nếu DBMS hỗ trợ và nghiệp vụ không cần quản lý từng nhãn như thực thể riêng.
- `display_options` chứa tùy chọn có tập khóa biến đổi theo loại sản phẩm: có thể là **JSON**.
- Nếu một sản phẩm thuộc nhiều danh mục, mỗi danh mục có mã, tên, quyền truy cập và thống kê: nên dùng **bảng danh mục và bảng liên kết**.

| Cấu trúc | Dạng dữ liệu | Điểm mạnh | Giới hạn cần cân nhắc |
|---|---|---|---|
| Cột quan hệ thông thường | `price NUMERIC(12,2)` | Kiểm tra kiểu, ràng buộc, truy vấn, JOIN rõ ràng | Thay đổi cấu trúc có thể cần migration |
| JSON | `{"theme":"dark","layout":{"columns":3}}` | Đối tượng lồng nhau, trường tùy chọn, cấu trúc linh hoạt | Ràng buộc từng trường phức tạp hơn; truy vấn và chỉ mục tùy DBMS |
| Mảng SQL | `ARRAY['sql','db']` | Nhiều giá trị đồng kiểu trong một cột | Không phù hợp khi phần tử cần khóa ngoại, thuộc tính, thứ tự nghiệp vụ phức tạp |
| Bảng con/bảng liên kết | Một dòng cho mỗi phần tử | Chuẩn hóa, tham chiếu, JOIN, kiểm soát riêng từng phần tử | Nhiều bảng và phép JOIN hơn |

**Linh hoạt về cấu trúc không đồng nghĩa không cần schema.** Dù lưu JSON, ứng dụng vẫn nên có hợp đồng dữ liệu: khóa nào được phép, loại dữ liệu nào hợp lệ, phiên bản định dạng và cách di trú khi cấu trúc thay đổi.

## 2. JSON trong cơ sở dữ liệu

### 2.1. JSON chứa những giá trị gì?

JSON là định dạng dữ liệu có cấu trúc cây, gồm đối tượng, mảng, chuỗi, số, `true`, `false` và `null`.

```json
{
  "channel": "mobile",
  "gift": true,
  "priority": 2,
  "shipping": {
    "method": "express",
    "pickupPoint": null
  },
  "coupons": ["WELCOME", "FREESHIP"]
}
```

Trường `shipping` là đối tượng lồng nhau; `coupons` là **mảng bên trong JSON**. Mảng này khác với **kiểu mảng SQL** như `TEXT[]` của PostgreSQL: JSON có thể chứa phần tử khác kiểu, còn mảng SQL có kiểu phần tử xác định.

JSON đặc biệt hữu ích khi cần lưu phản hồi tích hợp, cấu hình, thuộc tính mở rộng không đồng nhất hoặc ảnh chụp dữ liệu sự kiện. Nhưng các dữ liệu cốt lõi như số tiền thanh toán, mã khách hàng và trạng thái giao dịch thường vẫn nên nằm trong cột có kiểu và ràng buộc riêng.

### 2.2. PostgreSQL: `JSON` và `JSONB`

PostgreSQL có hai kiểu JSON quan trọng:

| Tiêu chí | `JSON` | `JSONB` |
|---|---|---|
| Cách lưu | Văn bản JSON đã kiểm tra cú pháp | Biểu diễn nhị phân đã phân tích |
| Giữ nguyên định dạng đầu vào | Giữ khoảng trắng, thứ tự khóa và khóa trùng trong văn bản | Không giữ nguyên thứ tự khóa/khoảng trắng; với khóa trùng, chỉ giữ một giá trị |
| Chi phí ghi/đọc | Không cần chuyển đổi sang biểu diễn `JSONB` khi ghi; thao tác lại có thể phải phân tích | Có chi phí chuyển đổi khi ghi, thuận lợi cho nhiều thao tác tìm kiếm |
| Khả năng lập chỉ mục nội dung | Ít toán tử và chiến lược chỉ mục hơn | Hỗ trợ nhiều toán tử và chỉ mục GIN hữu ích |
| Phù hợp | Cần lưu lại văn bản JSON gần nguyên dạng | Cần tìm kiếm, lọc, đối chiếu trường JSON thường xuyên |

Ví dụ bảng đơn hàng vừa có cột quan hệ vừa có metadata linh hoạt:

```sql
CREATE TABLE orders (
    order_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    customer_id BIGINT NOT NULL,
    total_amount NUMERIC(14, 2) NOT NULL
        CHECK (total_amount >= 0),
    status VARCHAR(16) NOT NULL
        CHECK (status IN ('PENDING', 'PAID', 'CANCELLED')),
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT ck_metadata_object
        CHECK (jsonb_typeof(metadata) = 'object')
);
```

Cột `metadata` dùng cho thông tin phụ như kênh đặt hàng hay tùy chọn giao hàng. Các giá trị bắt buộc cho tính tiền và quản lý trạng thái vẫn là cột độc lập để được kiểm tra kiểu và dùng chỉ mục trực tiếp.

```sql
INSERT INTO orders (customer_id, total_amount, status, metadata)
VALUES (
    101,
    199000.00,
    'PENDING',
    '{
      "channel": "mobile",
      "gift": true,
      "shipping": {"method": "express"},
      "coupons": ["WELCOME"]
    }'::jsonb
);
```

PostgreSQL chỉ chấp nhận JSON có cú pháp hợp lệ cho cột `JSONB`, nhưng **không mặc định bảo đảm** rằng khóa `gift` luôn là boolean hay `shipping.method` luôn có mặt. Cần định nghĩa thêm quy tắc nếu ứng dụng yêu cầu.

### 2.3. Truy vấn trường JSON bằng PostgreSQL

Các toán tử thường dùng:

| Toán tử | Ý nghĩa | Kiểu kết quả |
|---|---|---|
| `->` | Lấy trường đối tượng hoặc phần tử mảng theo chỉ số | JSON/JSONB |
| `->>` | Lấy giá trị dưới dạng văn bản | `TEXT` |
| `#>` | Lấy giá trị theo đường dẫn gồm nhiều bước | JSON/JSONB |
| `#>>` | Lấy giá trị dạng văn bản theo đường dẫn | `TEXT` |
| `@>` với `JSONB` | Chứa cấu trúc JSON ở vế phải | `BOOLEAN` |
| `?` với `JSONB` | Có khóa chuỗi hoặc phần tử chuỗi ở cấp ngoài cùng | `BOOLEAN` |

```sql
-- Lấy tên kênh dưới dạng chuỗi.
SELECT order_id, metadata ->> 'channel' AS channel
FROM orders;

-- Lấy trường lồng nhau.
SELECT order_id,
       metadata #>> '{shipping,method}' AS shipping_method
FROM orders;

-- Lọc các đơn đặt từ ứng dụng di động.
SELECT order_id, total_amount
FROM orders
WHERE metadata @> '{"channel":"mobile"}'::jsonb;

-- Kiểm tra khóa gift xuất hiện ở cấp ngoài cùng.
SELECT order_id
FROM orders
WHERE metadata ? 'gift';

-- Kiểm tra coupons chứa WELCOME.
SELECT order_id
FROM orders
WHERE metadata @> '{"coupons":["WELCOME"]}'::jsonb;
```

**Chú ý về kiểu dữ liệu:** `metadata ->> 'priority'` trả về văn bản. Nếu muốn so sánh số học, phải chuyển kiểu có kiểm soát, ví dụ `(metadata ->> 'priority')::integer`. Phép ép kiểu có thể lỗi nếu JSON chứa chuỗi không phải số; vì vậy nên kiểm tra cấu trúc ngay khi ghi hoặc có ràng buộc thích hợp.

**Chú ý về `NULL`:** cần phân biệt SQL `NULL` (không có giá trị cột), JSON `null` (một giá trị nằm trong tài liệu JSON) và **khóa không tồn tại**. Phép lấy trường không tồn tại thường cho SQL `NULL`; muốn phân biệt một khóa có tồn tại hay không có thể dùng toán tử kiểm tra khóa rồi kiểm tra kiểu JSON, tùy mục đích.

### 2.4. Mở phần tử JSON thành nhiều dòng

Một mảng JSON chứa nhiều phần tử có thể được duyệt bằng hàm dành riêng cho DBMS. PostgreSQL hỗ trợ `jsonb_array_elements` và `jsonb_array_elements_text`:

```sql
SELECT
    o.order_id,
    coupon.value AS coupon_code
FROM orders AS o
CROSS JOIN LATERAL jsonb_array_elements_text(
    o.metadata -> 'coupons'
) AS coupon(value)
WHERE jsonb_typeof(o.metadata -> 'coupons') = 'array';
```

Trong thực tế, nên bảo đảm trường `coupons` là mảng ngay tại lúc ghi, hoặc thiết kế truy vấn xử lý trường thiếu/sai loại một cách an toàn. Nếu mỗi coupon cần theo dõi hiệu lực, số lần dùng hoặc khóa ngoại đến bảng coupon, **bảng `order_coupons` sẽ phù hợp hơn** so với giấu toàn bộ quan hệ trong JSON.

### 2.5. Chỉ mục JSON và chi phí truy vấn

PostgreSQL có thể dùng GIN cho một số thao tác trên `JSONB`:

```sql
-- Hữu ích cho nhiều truy vấn chứa JSON dùng toán tử @>.
CREATE INDEX idx_orders_metadata_gin
ON orders USING GIN (metadata);

-- Hữu ích khi thường lọc/sắp theo một khóa cụ thể.
CREATE INDEX idx_orders_channel
ON orders ((metadata ->> 'channel'));
```

Không nên tạo chỉ mục cho mọi trường JSON. Chỉ mục tiêu tốn dung lượng và làm tăng chi phí `INSERT`/`UPDATE`. Chọn loại chỉ mục theo toán tử thực sự dùng, độ chọn lọc và kết quả `EXPLAIN` trên dữ liệu thực tế. Ví dụ, chỉ mục biểu thức `metadata ->> 'channel'` thích hợp cho phép so sánh giá trị chuỗi cụ thể; chỉ mục GIN phục vụ những phép tìm kiếm cấu trúc JSON được hỗ trợ. Tùy truy vấn, người dùng có thể cân nhắc các lớp toán tử GIN khác nhau như `jsonb_ops` và `jsonb_path_ops`.

## 3. Kiểu mảng SQL

### 3.1. Mảng SQL có ý nghĩa gì?

Một mảng SQL là tập hợp các phần tử trong **một giá trị cột**, thường cùng kiểu dữ liệu. PostgreSQL hỗ trợ khai báo `INTEGER[]`, `TEXT[]`, `UUID[]`, v.v. Ví dụ một bài viết có một số nhãn đơn giản:

```sql
CREATE TABLE articles (
    article_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    title TEXT NOT NULL,
    tags TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[]
);

INSERT INTO articles (title, tags)
VALUES
    ('SQL căn bản', ARRAY['sql', 'database']),
    ('Tối ưu truy vấn', ARRAY['sql', 'performance']),
    ('Giới thiệu Java', ARRAY['java']);
```

Đối với PostgreSQL, `TEXT[]` thể hiện mỗi phần tử là chuỗi. Tuy nhiên, mảng không bắt buộc có độ dài cố định; hệ quản trị vẫn cần những ràng buộc bổ sung nếu số phần tử hoặc nội dung từng phần tử bị giới hạn bởi nghiệp vụ.

### 3.2. Truy cập, tìm kiếm và trải phẳng mảng

```sql
-- Phần tử đầu tiên của mảng trong PostgreSQL mặc định có chỉ số 1.
SELECT article_id, tags[1] AS first_tag
FROM articles;

-- 'sql' bằng ít nhất một phần tử.
SELECT article_id, title
FROM articles
WHERE 'sql' = ANY(tags);

-- Mảng tags chứa tất cả phần tử bên phải.
SELECT article_id, title
FROM articles
WHERE tags @> ARRAY['sql']::TEXT[];

-- Có ít nhất một phần tử chung.
SELECT article_id, title
FROM articles
WHERE tags && ARRAY['performance', 'database']::TEXT[];

-- Mỗi nhãn thành một dòng kết quả.
SELECT a.article_id, tag.value
FROM articles AS a
CROSS JOIN LATERAL unnest(a.tags) AS tag(value);
```

Trong PostgreSQL, `@>` biểu diễn mảng chứa các phần tử bên phải, còn `&&` kiểm tra hai mảng có phần tử giao nhau. Có thể hỗ trợ một số phép tìm kiếm mảng bằng GIN:

```sql
CREATE INDEX idx_articles_tags_gin
ON articles USING GIN (tags);
```

Giống JSON, hiệu quả thực tế phụ thuộc số lượng phần tử, độ chọn lọc, truy vấn và thống kê. Không nên suy ra rằng chỉ mục GIN luôn nhanh hơn quét bảng.

### 3.3. `NULL`, mảng rỗng và phần tử `NULL`

Ba giá trị sau không giống nhau:

```sql
SELECT
    NULL::TEXT[]                    AS unknown_tags,
    ARRAY[]::TEXT[]                AS empty_tags,
    ARRAY['sql', NULL]::TEXT[]      AS tags_with_null;
```

- `NULL::TEXT[]`: toàn bộ giá trị mảng không được biết/không hiện diện.
- `ARRAY[]::TEXT[]`: có mảng, nhưng hiện không có phần tử nào.
- `ARRAY['sql', NULL]::TEXT[]`: mảng chứa hai phần tử, trong đó một phần tử là `NULL`.

Sự khác biệt ảnh hưởng đến phép kiểm tra, so sánh và hàm xử lý mảng. Chẳng hạn, `cardinality(ARRAY[]::TEXT[])` trong PostgreSQL là `0`, trong khi `cardinality(NULL::TEXT[])` trả về SQL `NULL`.

Mảng của PostgreSQL có thể đa chiều; cú pháp truy cập thường bắt đầu từ chỉ số 1, nhưng PostgreSQL có thể biểu diễn mảng với cận dưới khác mặc định. Nếu ứng dụng cần khả năng di chuyển qua DBMS, không nên giả định rằng mọi hệ đều dùng `tags[1]`.

### 3.4. Khi nào không nên dùng mảng?

Giả sử mỗi tác giả có nhiều kỹ năng. Nếu chỉ hiển thị vài nhãn kỹ năng không có thuộc tính riêng, `TEXT[]` có thể hợp lý. Nhưng nếu cần lưu `skill_id`, cấp độ, ngày đạt chứng chỉ và JOIN đến danh mục kỹ năng thì nên chuẩn hóa:

```sql
CREATE TABLE skills (
    skill_id BIGINT PRIMARY KEY,
    skill_name VARCHAR(100) NOT NULL UNIQUE
);

CREATE TABLE author_skills (
    author_id BIGINT NOT NULL,
    skill_id BIGINT NOT NULL REFERENCES skills(skill_id),
    proficiency_level SMALLINT NOT NULL
        CHECK (proficiency_level BETWEEN 1 AND 5),
    PRIMARY KEY (author_id, skill_id)
);
```

Trong ví dụ này `author_id` giả định bảng tác giả được tạo ở phần khác của hệ thống; có thể bổ sung khóa ngoại tới bảng tác giả khi tích hợp schema. Cách tổ chức một dòng cho một quan hệ giúp kiểm soát và truy vấn từng kỹ năng rõ ràng. Nếu cố lưu mọi thông tin này dưới dạng mảng JSON, việc bảo đảm khóa ngoại, duy nhất và tính nhất quán sẽ phức tạp hơn.

## 4. Kiểu mở rộng và kiểu chuyên biệt theo hệ quản trị

“Kiểu mở rộng” có thể là **kiểu có sẵn riêng của một DBMS**, **kiểu do người dùng định nghĩa**, hoặc **kiểu đến từ một extension/plugin phải cài đặt**. Ba trường hợp này cần phân biệt, vì ảnh hưởng trực tiếp đến quyền triển khai, migration và khả năng chuyển đổi dữ liệu.

### 4.1. UUID: mã định danh không mang ý nghĩa số học

PostgreSQL có kiểu `UUID` chuyên lưu định danh 128-bit:

```sql
CREATE TABLE api_clients (
    client_id UUID PRIMARY KEY,
    client_name TEXT NOT NULL
);
```

Có thể tạo UUID tại ứng dụng hoặc nhờ chức năng DBMS tùy phiên bản và cấu hình. UUID giúp sinh ID ở nhiều hệ thống mà không cần lấy số thứ tự từ một trung tâm. Tuy nhiên, **UUID không bảo mật thông tin** và không tự thay thế phân quyền. Loại UUID và thứ tự chèn có thể ảnh hưởng đến độ cục bộ của chỉ mục. Các hệ quản trị khác có thể dùng kiểu bản địa riêng (ví dụ `uniqueidentifier` trong SQL Server) hoặc biểu diễn nhị phân/chuỗi.

### 4.2. `ENUM` và `DOMAIN`: giới hạn miền giá trị

PostgreSQL cho phép định nghĩa tập giá trị liệt kê:

```sql
CREATE TYPE order_state AS ENUM ('PENDING', 'PAID', 'CANCELLED');

CREATE TABLE payment_events (
    event_id BIGINT PRIMARY KEY,
    state order_state NOT NULL
);
```

Cách này diễn đạt rõ tập giá trị, nhưng mỗi lần thêm/sửa trạng thái cần quản lý migration cho kiểu. Nếu trạng thái có mô tả, thứ tự hiển thị, quyền thay đổi hoặc cần tham chiếu từ nhiều bảng, một bảng danh mục trạng thái có thể dễ mở rộng hơn.

PostgreSQL cũng có `DOMAIN`, tức kiểu dữ liệu do người dùng tạo từ kiểu cơ sở và một tập quy tắc:

```sql
CREATE DOMAIN nonnegative_amount AS NUMERIC(14, 2)
CHECK (VALUE >= 0);

CREATE TABLE wallets (
    wallet_id BIGINT PRIMARY KEY,
    balance nonnegative_amount NOT NULL
);
```

`DOMAIN` hữu ích khi cùng một quy tắc miền giá trị được áp dụng nhất quán ở nhiều cột. Cần xem xét ngữ nghĩa `NULL` riêng: quy tắc trong `CHECK` không tự biến một cột thành `NOT NULL`.

### 4.3. Khoảng giá trị: range types

PostgreSQL có các kiểu khoảng như `int4range`, `numrange`, `daterange`, `tsrange` và `tstzrange`. Một khoảng lưu **cả cận dưới, cận trên và thông tin đóng/mở của hai cận**. Dạng này hữu ích khi hỏi một thời điểm có nằm trong khung thời gian hay hai khoảng có giao nhau không.

```sql
CREATE TABLE promotions (
    promotion_id BIGINT PRIMARY KEY,
    active_period TSTZRANGE NOT NULL
);

INSERT INTO promotions (promotion_id, active_period)
VALUES (
    1,
    tstzrange(
        '2026-11-01 00:00:00+07',
        '2026-12-01 00:00:00+07',
        '[)'
    )
);

-- Khoảng ưu đãi có chứa thời điểm chỉ định?
SELECT promotion_id
FROM promotions
WHERE active_period @> TIMESTAMPTZ '2026-11-14 09:00:00+07';
```

Ký hiệu `[)` nghĩa là **bao gồm cận dưới, loại trừ cận trên**. Chọn quy ước cận nhất quán giúp tránh tính trùng ở các khoảng kề nhau. PostgreSQL hỗ trợ GiST cho một số phép truy vấn khoảng và ràng buộc loại trừ (`EXCLUDE`) trong các bài toán chống lịch trùng; cú pháp và khả năng đó không thể coi là SQL phổ quát.

### 4.4. Địa chỉ mạng

PostgreSQL cung cấp `INET`, `CIDR` và `MACADDR` để lưu và thao tác với địa chỉ/mạng:

```sql
CREATE TABLE access_logs (
    log_id BIGINT PRIMARY KEY,
    client_ip INET NOT NULL,
    logged_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

INSERT INTO access_logs (log_id, client_ip)
VALUES (1, '192.0.2.10');
```

Các kiểu này biểu diễn đúng cấu trúc địa chỉ mạng hơn việc dùng chuỗi tùy ý. PostgreSQL còn cung cấp các toán tử mạng để so sánh hoặc kiểm tra một địa chỉ thuộc một dải mạng. Khi chuyển sang DBMS khác, có thể phải dùng kiểu nhị phân/chuỗi và các hàm bổ trợ tương ứng.

### 4.5. Dữ liệu không gian (GIS)

Các DBMS khác nhau có hệ kiểu và hàm không gian khác nhau: PostgreSQL thường dùng phần mở rộng **PostGIS**, SQL Server có `geometry` và `geography`, MySQL có họ kiểu hình học. Tọa độ địa lý cần được gắn với hệ quy chiếu; không thể mặc định rằng các hệ tọa độ dùng cùng đơn vị đo.

Ví dụ PostgreSQL khi đã cài và được cấp quyền sử dụng PostGIS:

```sql
-- Chỉ thực hiện trong môi trường đã cài PostGIS và có quyền phù hợp.
CREATE EXTENSION IF NOT EXISTS postgis;

CREATE TABLE stores (
    store_id BIGINT PRIMARY KEY,
    location GEOGRAPHY(POINT, 4326) NOT NULL
);

INSERT INTO stores (store_id, location)
VALUES (1, ST_SetSRID(ST_MakePoint(106.7009, 10.7769), 4326));

CREATE INDEX idx_stores_location
ON stores USING GIST (location);
```

Ở `ST_MakePoint`, thứ tự thường là **kinh độ, vĩ độ** khi dùng tọa độ EPSG:4326. `GEOGRAPHY` trong PostGIS hỗ trợ các phép tính dựa trên bề mặt Trái Đất; lựa chọn giữa `geometry` và `geography` phụ thuộc phép toán và dữ liệu thực tế.

### 4.6. XML, tìm kiếm toàn văn, nhị phân và các kiểu khác

| Nhu cầu | Ví dụ kiểu/công cụ | Lưu ý |
|---|---|---|
| Tài liệu XML có cấu trúc | `XML` (PostgreSQL, SQL Server, Oracle có hỗ trợ khác nhau) | Có công cụ truy vấn/kiểm tra XML riêng; không nên coi XML giống JSON |
| Tìm kiếm toàn văn | `TSVECTOR`/`TSQUERY` (PostgreSQL) | Chứa dữ liệu/phép truy vấn chuyên biệt cho full-text search |
| Cặp khóa-giá trị dạng chuỗi | `HSTORE` (extension PostgreSQL) | Dữ liệu phẳng; JSONB thường linh hoạt hơn khi cần lồng nhau |
| Dữ liệu nhị phân | `BYTEA` (PostgreSQL), `VARBINARY` (nhiều DBMS) | Cần chiến lược dung lượng, truyền tải và phân quyền |
| Vector biểu diễn ngữ nghĩa | `VECTOR` trong extension `pgvector` của PostgreSQL | Cần cài extension, xác định số chiều và chiến lược chỉ mục tìm gần đúng |
| Kiểu ghép | Composite type của PostgreSQL, object type trong Oracle | Hữu ích ở một số mô hình, nhưng tăng mức phụ thuộc DBMS |

Không nên chọn kiểu chuyên biệt chỉ vì nó tồn tại. Phải xác định cách truy vấn, kiểm tra miền giá trị, chỉ mục, sao lưu, migration và cách driver ứng dụng ánh xạ kiểu đó.

## 5. Mức hỗ trợ khác nhau giữa các DBMS

| DBMS | JSON | Mảng SQL | Một số kiểu/công cụ đặc trưng |
|---|---|---|---|
| **PostgreSQL** | `JSON`, `JSONB` và nhiều toán tử; hỗ trợ GIN cho JSONB | Có kiểu mảng gốc như `TEXT[]`, `INTEGER[]` | `UUID`, `ENUM`, `DOMAIN`, range, `INET`, `TSVECTOR`; PostGIS/pgvector qua extension |
| **MySQL** | Kiểu `JSON` gốc, các hàm như `JSON_EXTRACT`; chỉ mục có thể cần cột sinh hoặc biểu thức theo phiên bản | Không có kiểu mảng SQL tổng quát như PostgreSQL; thường biểu diễn mảng trong JSON | `ENUM`, `SET`, kiểu không gian; một số cơ chế phụ thuộc phiên bản |
| **SQL Server** | Các hàm như `ISJSON`, `JSON_VALUE`, `OPENJSON`; kiểu JSON gốc và khả năng chỉ mục tùy phiên bản/ấn bản | Không có kiểu cột mảng tổng quát tương ứng `TEXT[]` | `uniqueidentifier`, `geometry`, `geography`, `hierarchyid`, `xml` |
| **Oracle Database** | Hỗ trợ SQL/JSON; kiểu JSON chuyên dụng ở các phiên bản phù hợp | Có collection types như `VARRAY`, nested table, nhưng cách dùng khác mảng PostgreSQL | `XMLType`, object types, kiểu không gian và kiểu chuyên dụng khác |
| **SQLite** | Các hàm JSON như `json_extract`/`json_each`; có biểu diễn JSONB nội bộ ở các phiên bản hỗ trợ, khác JSONB của PostgreSQL | Không có kiểu cột mảng SQL gốc; thường dùng JSON hoặc bảng con | Hệ kiểu động dựa vào storage class và type affinity; extension tùy môi trường |

Bảng trên mô tả **khả năng theo họ DBMS**, không phải cam kết cho mọi phiên bản hoặc cấu hình. Đặc biệt, tính năng JSON của SQL Server, Oracle và SQLite đã phát triển theo phiên bản; cần tra phiên bản đang chạy, edition, extension được bật và khả năng hỗ trợ chỉ mục trước khi viết migration.

Cùng một ý định truy vấn một trường JSON có thể được viết rất khác:

```sql
-- PostgreSQL (metadata kiểu JSONB)
SELECT metadata ->> 'channel' FROM orders;

-- MySQL (metadata kiểu JSON)
SELECT JSON_UNQUOTE(JSON_EXTRACT(metadata, '$.channel'))
FROM orders;

-- SQL Server (metadata dùng kiểu được phiên bản hỗ trợ)
SELECT JSON_VALUE(metadata, '$.channel')
FROM orders;

-- SQLite (metadata lưu JSON bằng kiểu lưu trữ hỗ trợ)
SELECT json_extract(metadata, '$.channel')
FROM orders;
```

Ví dụ trên minh họa **cú pháp tách giá trị** chứ không bảo đảm cùng kiểu kết quả, hành vi với `NULL`, đường dẫn thiếu hoặc cách tối ưu truy vấn giữa các DBMS.

## 6. Quy tắc quyết định: JSON, mảng hay bảng quan hệ?

Hãy bắt đầu bằng nhu cầu truy vấn và bất biến nghiệp vụ.

### Tình huống A: thuộc tính sản phẩm không giống nhau

Một cửa hàng bán sách, laptop và quần áo. Mỗi loại có thuộc tính phụ riêng, chẳng hạn ISBN, dung lượng RAM hoặc bảng size. Các cột chung (mã sản phẩm, tên, giá, trạng thái) nên có kiểu quan hệ; thông số linh hoạt có thể nằm trong `attributes JSONB`. Nếu thường lọc theo RAM hoặc ISBN và cần ràng buộc chặt, cân nhắc cột riêng, bảng mở rộng theo loại sản phẩm hoặc chỉ mục biểu thức.

### Tình huống B: thẻ tìm kiếm đơn giản

Một bài viết có vài nhãn chuỗi. Trong PostgreSQL, `TEXT[]` và GIN có thể đủ gọn và hữu ích. Nếu nhãn cần mô tả, phân loại, quyền quản trị hoặc báo cáo tập trung, nên có bảng `tags` và bảng `article_tags`, không chỉ mảng chuỗi.

### Tình huống C: đơn hàng với nhiều dòng sản phẩm

Không nên chỉ lưu các dòng đơn hàng trong JSON của bảng `orders` nếu cần khóa ngoại sản phẩm, số lượng, đơn giá và đối soát. Thiết kế `orders` + `order_items` với một dòng mỗi sản phẩm giúp kiểm soát ràng buộc, lập chỉ mục và thực hiện giao dịch. JSON chỉ nên giữ metadata bổ sung hoặc bản chụp phụ theo mục tiêu hệ thống.

### Tình huống D: vị trí cửa hàng hoặc khung lịch

Khi cần tính khoảng cách địa lý hoặc kiểm tra các khoảng thời gian giao nhau, kiểu chuyên biệt (GIS/range) có thể diễn đạt phép toán và dùng chỉ mục tốt hơn cách lưu tọa độ/khung lịch trong chuỗi. Đổi lại, hệ thống phải chấp nhận phụ thuộc DBMS hoặc xây lớp trừu tượng phù hợp.

Sơ đồ quyết định đơn giản:

```text
Có quan hệ nhiều-nhiều, khóa ngoại, hoặc thuộc tính cho từng phần tử?
    Có  → Dùng bảng riêng/bảng liên kết.
    Không
      ↓
Dữ liệu là một cấu trúc lồng nhau với khóa tùy biến?
    Có  → Cân nhắc JSON và hợp đồng dữ liệu.
    Không
      ↓
Dữ liệu là danh sách ngắn các phần tử đồng kiểu?
    Có  → Cân nhắc mảng nếu DBMS hỗ trợ và ít phụ thuộc liên bảng.
    Không
      ↓
Cần toán tử chuyên biệt: mạng, địa lý, khoảng, toàn văn, vector?
    Có  → Xem kiểu/extension chuyên biệt của DBMS.
    Không → Ưu tiên kiểu SQL quan hệ thông thường.
```

Đây là định hướng ban đầu, không phải quy tắc tuyệt đối. Một thiết kế có thể kết hợp nhiều cách lưu để đáp ứng yêu cầu thực tế.

## 7. Ràng buộc và kiểm soát dữ liệu trong JSON/mảng

Một nhược điểm thường gặp của cột linh hoạt là dữ liệu có cú pháp hợp lệ nhưng sai **ngữ nghĩa**. Ví dụ `{"gift":"yes"}` là JSON hợp lệ dù nghiệp vụ yêu cầu boolean; `tags = ARRAY['sql', NULL]` có thể không hợp lệ nếu quy tắc không cho phần tử rỗng.

PostgreSQL có thể dùng `CHECK` để kiểm soát các quy tắc đơn giản:

```sql
CREATE TABLE products (
    product_id BIGINT PRIMARY KEY,
    attributes JSONB NOT NULL DEFAULT '{}'::jsonb,
    tags TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[],
    CONSTRAINT ck_attributes_object
        CHECK (jsonb_typeof(attributes) = 'object'),
    CONSTRAINT ck_tags_limit
        CHECK (cardinality(tags) <= 20),
    CONSTRAINT ck_tags_no_null
        CHECK (array_position(tags, NULL) IS NULL)
);
```

Ở đây `ck_attributes_object` chỉ kiểm tra JSON ngoài cùng là đối tượng, không xác nhận từng thuộc tính. Khi cấu trúc phức tạp, có thể xác thực hợp đồng JSON trong ứng dụng và thêm một số ràng buộc quan trọng trong DB. Với mảng, cần cân nhắc thêm tính duy nhất giữa các phần tử, thứ tự, số lượng và chuẩn hóa chữ hoa/thường theo nghiệp vụ.

**JSON `null` và SQL `NULL` cần được xử lý rõ ràng** khi thiết kế giá trị mặc định, điều kiện lọc và dữ liệu trả về API. Một trường không hiện diện cũng không mặc nhiên có nghĩa giống một trường tồn tại với giá trị `null`.

## 8. Tác động đến truy vấn, bảo trì và khả năng di chuyển

**Khả năng tìm kiếm.** Nếu thường lọc theo `status` hoặc `customer_id`, cột quan hệ có chỉ mục thông thường dễ hiểu và có tính phổ biến cao. Nếu thường tìm cấu trúc sâu trong JSON, cần loại chỉ mục và toán tử tương thích. Nếu phần tử phải JOIN với bảng khác, bảng liên kết thường giúp SQL rõ ràng hơn mảng/JSON.

**Chi phí cập nhật.** Cập nhật một phần JSON lớn hoặc mảng lớn có thể đòi hỏi ghi lại giá trị/cấu trúc lưu trữ tùy DBMS, kèm chi phí duy trì chỉ mục. Không giả định JSON phù hợp với mọi thao tác cập nhật phần tử liên tục. Tách thuộc tính cập nhật với tần suất cao ra cột/bảng riêng khi cần.

**Tính nhất quán.** Khóa ngoại, `UNIQUE`, `CHECK`, `NOT NULL` dễ thiết kế hơn khi mỗi thực thể có dòng và khóa riêng. Đối tượng lồng trong JSON có thể cần xác thực nhiều lớp, nhưng không cung cấp khóa ngoại cho từng trường một cách tự nhiên như mô hình quan hệ.

**Khả năng chuyển DBMS.** Các chuẩn SQL/JSON có ảnh hưởng đến nhiều sản phẩm, nhưng tên kiểu, toán tử JSON, đường dẫn, ép kiểu, chỉ mục và phần xử lý lỗi vẫn khác nhau. Mảng PostgreSQL, range hay PostGIS tạo giá trị lớn nhưng có thể phát sinh công việc migration đáng kể khi chuyển nhà cung cấp.

**Ánh xạ ứng dụng.** Cần kiểm tra driver/JDBC/ORM hỗ trợ kiểu đặc thù thế nào. Trong Java, JSON có thể được ánh xạ qua đối tượng hoặc chuỗi với bộ chuyển đổi phù hợp, mảng qua JDBC `Array` hoặc mapping riêng, UUID qua `UUID`. Không tự giả định rằng mọi kiểu tùy biến sẽ được JPA ánh xạ trực tiếp giống `VARCHAR` hoặc `INTEGER`.

**Bảo mật và dữ liệu nhạy cảm.** JSON không mã hóa dữ liệu tự động. Việc gom nhiều trường vào một cột có thể khiến ứng dụng vô tình trả về dữ liệu không cần thiết. Cần kiểm soát quyền truy cập, trường được phép xuất ra API và dữ liệu nhạy cảm; kiểu lưu trữ chỉ giải quyết vấn đề biểu diễn.

## 9. Cách thiết kế một cột linh hoạt có trách nhiệm

Khi chuẩn bị bổ sung JSON, mảng hoặc kiểu mở rộng, có thể đi qua các bước:

1. **Viết ý nghĩa nghiệp vụ**: kiểu dữ liệu đang mô tả thực thể, tập giá trị, tài liệu hay phép toán chuyên biệt nào?
2. **Lập mẫu dữ liệu** gồm tình huống phổ biến, trường thiếu, `NULL`, danh sách rỗng, giá trị lồng nhau và dữ liệu biên.
3. **Liệt kê truy vấn**: đọc toàn bộ, lọc theo trường, JOIN, tìm phần tử, cập nhật một phần, thống kê và sắp xếp.
4. **Xác định bất biến**: trường bắt buộc, kiểu, miền giá trị, thứ tự, số lượng, tính duy nhất và tham chiếu.
5. **Chọn biểu diễn**: cột quan hệ, JSON, mảng, bảng con hoặc kiểu chuyên biệt, có thể kết hợp.
6. **Thiết kế chỉ mục** theo truy vấn thực tế, kiểm tra bằng kế hoạch thực thi trên dữ liệu đại diện.
7. **Xác nhận mức hỗ trợ** của DBMS/version, driver, ORM, extension, công cụ migration và môi trường triển khai.
8. **Lập phương án thay đổi schema**: thêm khóa JSON mới, nâng phiên bản hợp đồng dữ liệu, chuyển cột JSON thành cột quan hệ, hoặc thay kiểu đặc thù khi chuyển DBMS.

Ví dụ, một bản ghi JSON có thể thêm thuộc tính `schemaVersion` nếu có nhiều phiên bản cấu trúc cần tồn tại đồng thời. Đây là lựa chọn thiết kế của ứng dụng, không phải trường bắt buộc của JSON hay DBMS.

## 10. Những hiểu nhầm cần tránh

| Hiểu nhầm | Giải thích đúng |
|---|---|
| “Có JSON thì không cần mô hình quan hệ.” | JSON linh hoạt nhưng không thay thế tự nhiên khóa ngoại, quan hệ và ràng buộc trên thực thể. |
| “JSON và JSONB giống nhau ở mọi DBMS.” | Kiểu, biểu diễn, chỉ mục và cú pháp phụ thuộc DBMS; JSONB của SQLite không đồng nghĩa JSONB PostgreSQL. |
| “Mảng JSON giống mảng SQL.” | Mảng JSON nằm trong tài liệu JSON; mảng SQL có kiểu phần tử và toán tử riêng tùy hệ. |
| “Lưu JSON chắc chắn nhanh hơn nhiều bảng.” | Tốc độ tùy truy vấn, chỉ mục, dữ liệu, kích thước và cách cập nhật; phải đo trên tải thực. |
| “Tất cả hệ quản trị đều có `TEXT[]` và toán tử `@>`.” | Đây là cú pháp/kiểu đặc thù phổ biến của PostgreSQL, không phải cú pháp chung. |
| “`JSONB` giữ nguyên văn bản đầu vào.” | PostgreSQL JSONB chuẩn hóa biểu diễn, không giữ nguyên mọi khoảng trắng, thứ tự khóa hay khóa trùng. |
| “Dữ liệu GIS chỉ cần hai cột số bất kỳ.” | Phải quản lý hệ tọa độ, cách đo, đơn vị và hàm chuyên biệt khi cần phép toán không gian. |
| “UUID đảm bảo bí mật và phân quyền.” | UUID là định danh; truy cập vẫn cần xác thực và phân quyền. |
| “Kiểu mở rộng tự có trên mọi máy DB.” | Một số kiểu là bản địa, một số cần cài extension, bật tính năng hoặc cấp quyền. |

## Kết luận

Chọn **JSON** khi cần biểu diễn đối tượng lồng nhau hoặc thuộc tính có cấu trúc biến đổi; chọn **mảng SQL** khi có một danh sách đồng kiểu và DBMS hỗ trợ tốt; chọn **kiểu mở rộng/chuyên biệt** khi dữ liệu có ngữ nghĩa và phép toán mà kiểu chung không đáp ứng hiệu quả. Với quan hệ nhiều-nhiều, khóa ngoại và dữ liệu giao dịch cốt lõi, bảng quan hệ vẫn là lựa chọn đáng tin cậy.

Trước khi sử dụng các kiểu phụ thuộc hệ quản trị, cần xác định chính xác phiên bản DBMS, cơ chế lưu trữ, hàm/toán tử truy vấn, ràng buộc, chỉ mục và mức hỗ trợ từ driver/ORM. Thiết kế tốt là thiết kế giúp **dữ liệu đúng, truy vấn dễ hiểu và thay đổi được một cách có kiểm soát**.

