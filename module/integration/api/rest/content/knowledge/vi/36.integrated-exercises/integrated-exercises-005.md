# Phân trang keyset với bộ lọc, sắp xếp và dữ liệu thay đổi

## Mục tiêu và kết quả cần nộp

Bài thực hành tổng hợp này đặt bạn vào vai người phát triển REST API cho danh mục sản phẩm trong một hệ thống nhiều tenant. Bạn cần xây dựng **keyset pagination** (còn gọi là seek pagination) có bộ lọc, thứ tự sắp xếp xác định, cursor không thể bị sửa tùy ý và hành vi rõ ràng khi dữ liệu thay đổi giữa hai lượt gọi.

Sau khi hoàn thành, bạn phải có khả năng:

- Giải thích vì sao `OFFSET/LIMIT` dễ bị lặp hoặc bỏ sót bản ghi khi insert/delete trong lúc người dùng đang lật trang; hiểu keyset giải quyết được điều gì và **không** giải quyết được điều gì.
- Thiết kế `GET /api/v1/products` với `limit`, `status`, `categoryId`, khoảng giá, `sort` và `cursor`.
- Viết SQL cho **hai thứ tự**: `createdAt_desc` và `price_asc`, luôn có khóa phụ duy nhất (`id`) để phá hòa.
- Tạo/kiểm tra cursor opaque có chữ ký HMAC, gắn với bộ lọc, sort và tenant đã được xác thực; giới hạn `limit` và vòng đời cursor.
- Triển khai Java/Spring + PostgreSQL với SQL parameterized và danh sách sort được phép, không ghép raw SQL từ user.
- Chứng minh bằng integration test điều gì xảy ra khi insert, update, delete trong lúc đang phân trang; phân biệt **best-effort traversal** với **snapshot consistency**.
- Trả về response và lỗi HTTP có hợp đồng rõ ràng, bổ sung kiểm thử hiệu năng/SQL index và tài liệu OpenAPI.

**Sản phẩm cần nộp:** một endpoint REST, migration tạo bảng/index, service truy vấn keyset, cursor codec, OpenAPI fragment, test happy path + mutation + bảo mật, và báo cáo ngắn về lựa chọn consistency. Các đoạn code trong bài là ví dụ/khuôn mẫu, cần lắp ghép với Spring Boot, repository, security và cấu hình môi trường thực tế.

## 1. Bối cảnh bài toán và yêu cầu nghiệp vụ

Hệ thống có các sản phẩm:

| id | tenant_id | category_id | status | price_cents | created_at (UTC) |
| ---: | ---: | ---: | --- | ---: | --- |
| 106 | 7 | 10 | ACTIVE | 2500 | 2026-11-18 10:06:00 |
| 105 | 7 | 10 | ACTIVE | 1200 | 2026-11-18 10:05:00 |
| 104 | 7 | 10 | ACTIVE | 1200 | 2026-11-18 10:04:00 |
| 103 | 7 | 10 | ACTIVE | 990 | 2026-11-18 10:03:00 |
| 102 | 7 | 20 | ACTIVE | 3000 | 2026-11-18 10:02:00 |
| 101 | 7 | 10 | DRAFT | 1200 | 2026-11-18 10:01:00 |
| 201 | 8 | 10 | ACTIVE | 500 | 2026-11-18 10:07:00 |

`tenant_id` đến từ danh tính đã xác thực, **không** từ query parameter client gửi. Ngay cả khi một product ID của tenant khác có thể đoán được, API vẫn không được trả nó trong danh sách.

Các tiêu chí chấp nhận:

1. `GET /api/v1/products` mặc định trả tối đa 25 sản phẩm, giới hạn tối đa 100, không trả giá trị `limit <= 0`.
2. Lọc tùy chọn theo `status=ACTIVE|DRAFT`, `categoryId` và `minPriceCents`/`maxPriceCents`.
3. Hỗ trợ `sort=createdAt_desc` (mặc định) và `sort=price_asc`; thứ tự luôn xác định nhờ `id`.
4. Response gồm `items`, `nextCursor` và `hasMore`. Khi hết trang, `nextCursor=null` và `hasMore=false`.
5. Cursor chỉ hợp lệ với cùng **tenant + filter + sort**; thay đổi bất kỳ thành phần này khi dùng lại cursor phải bị từ chối có cấu trúc.
6. Không dùng `OFFSET` trong truy vấn trang tiếp theo; database được phép dùng index seek.
7. Dữ liệu có thể insert/update/delete giữa các request; API phải công bố **giới hạn nhất quán**, không hứa snapshot tuyệt đối nếu chưa thực hiện cơ chế snapshot.
8. Request sai tham số/cursor được trả `400` với Problem Details; request không được phép vẫn tuân thủ `401/403`; server không đưa SQL exception/raw cursor/credential ra response.

Lựa chọn nội dung trong bài: bảng PostgreSQL, Spring MVC, `NamedParameterJdbcTemplate` và Java 17+. Có thể thay bằng Spring Data JDBC/JPA/jOOQ nhưng phải giữ đúng semantics và kiểm chứng SQL thật của thư viện.

## 2. Tại sao OFFSET/LIMIT không đủ?

Giả sử truy vấn danh sách `created_at DESC, id DESC`, mỗi trang 3 phần tử:

```sql
SELECT id, created_at
FROM product
WHERE tenant_id = 7 AND status = 'ACTIVE'
ORDER BY created_at DESC, id DESC
LIMIT 3 OFFSET 0;
```

Lượt 1 trả `[106, 105, 104]`. Trước lượt 2, người khác thêm product `107` mới nhất. Danh sách trở thành `[107, 106, 105, 104, 103, 102]`. Request:

```sql
SELECT id, created_at
FROM product
WHERE tenant_id = 7 AND status = 'ACTIVE'
ORDER BY created_at DESC, id DESC
LIMIT 3 OFFSET 3;
```

Trả về `[104, 103, 102]`: **104 xuất hiện hai lần**. Nếu có phần tử ở trang trước bị xóa, `OFFSET` có thể làm **bỏ sót** một phần tử chưa xem. Ngoài ra, ở offset lớn, cơ sở dữ liệu có thể phải đi qua/bỏ nhiều hàng trước khi lấy trang mong muốn.

Keyset đặt câu hỏi khác: **“Lấy những hàng nằm sau khóa cuối của trang vừa xem trong cùng thứ tự”**.

Nếu khóa cuối là `(created_at=10:04:00, id=104)`, truy vấn sau dùng:

```sql
SELECT id, created_at
FROM product
WHERE tenant_id = 7
  AND status = 'ACTIVE'
  AND (created_at, id) < (
      TIMESTAMPTZ '2026-11-18 10:04:00+00', 104
  )
ORDER BY created_at DESC, id DESC
LIMIT 3;
```

Kết quả `[103, 102]` trong dữ liệu minh họa, dù product 107 vừa được insert ở **phía trước** mốc đã đi qua. Keyset tránh lỗi “dịch chỉ số” do insert ở đầu danh sách. Tuy nhiên, nếu một hàng **di chuyển khóa sort hoặc thay đổi điều kiện lọc**, vẫn có thể lặp/bỏ sót; chúng ta sẽ mô phỏng ở phần sau.

### Điều kiện để keyset đúng

- Có **thứ tự toàn phần, deterministic**: `ORDER BY created_at DESC, id DESC`, không chỉ `created_at DESC` vì nhiều hàng có thể cùng timestamp.
- Điều kiện “sau cursor” phải dùng **cùng thứ tự**: hai cột đều DESC thì `(created_at, id) < (lastCreatedAt, lastId)`.
- Tất cả bộ lọc phải được áp dụng giống nhau trên mỗi trang.
- Các cột khóa sort cần có semantics về `NULL` rõ ràng; bài này dùng `NOT NULL`.
- Sự ổn định của traversal còn phụ thuộc **khóa sort có bị sửa** hay không và việc membership (status/category/price) thay đổi.

## 3. Từ thứ tự sắp xếp đến điều kiện keyset

### Trường hợp A: thời điểm tạo giảm dần

```sql
ORDER BY created_at DESC, id DESC
```

Cursor lưu `lastCreatedAt` và `lastId`. Với trang tiếp theo:

```sql
AND (created_at, id) < (:lastCreatedAt, :lastId)
```

Tương đương:

```sql
AND (
  created_at < :lastCreatedAt
  OR (created_at = :lastCreatedAt AND id < :lastId)
)
```

### Trường hợp B: giá tăng dần

```sql
ORDER BY price_cents ASC, id ASC
```

Cursor lưu `lastPriceCents` và `lastId`. Trang tiếp theo:

```sql
AND (price_cents, id) > (:lastPriceCents, :lastId)
```

Với bảng dữ liệu tenant 7, category 10, status ACTIVE, thứ tự giá tăng là:

```text
(990,103) -> (1200,104) -> (1200,105) -> (2500,106)
```

Nếu trang đầu `limit=2` trả `[103,104]`, cursor là `(1200,104)`; trang sau bắt đầu ở `(1200,105)` chứ **không** bỏ qua mọi sản phẩm có giá 1200.

**Khi có hướng sort hỗn hợp**, ví dụ `ORDER BY priority DESC, created_at ASC, id ASC`, không thể áp dụng trực tiếp một phép so sánh tuple `<` hoặc `>` cho tất cả cột; phải triển khai biểu thức OR theo từng cột, chuẩn hóa hướng so sánh hoặc chọn một cấu trúc sort khác. Khi có `NULLS FIRST/LAST`, cần chính sách đối chiếu null riêng. Bài thực hành cố ý giới hạn hai kiểu sort với hướng thống nhất và trường `NOT NULL`.

| Sort | Khóa chính | Tiebreaker | Điều kiện trang kế | Rủi ro mutation |
| --- | --- | --- | --- | --- |
| `createdAt_desc` | `created_at DESC` | `id DESC` | `(created_at,id) < cursor` | Ít rủi ro nếu cả hai khóa bất biến |
| `price_asc` | `price_cents ASC` | `id ASC` | `(price_cents,id) > cursor` | Giá đổi có thể làm hàng di chuyển |

**Quy tắc quan trọng:** `id` phải duy nhất trong tập kết quả, còn `created_at`/`price_cents` được xác định rõ kiểu dữ liệu, precision, timezone và cách xử lý null. Nếu cùng một ID tồn tại ở nhiều tenant, chỉ so sánh trong phạm vi `tenant_id` đã lọc.

## 4. Hợp đồng REST và ví dụ response

Lần gọi đầu:

```http
GET /api/v1/products?status=ACTIVE&categoryId=10&sort=createdAt_desc&limit=2 HTTP/1.1
Host: api.example.com
Authorization: Bearer <test-access-token>
Accept: application/json
```

Response minh họa (cursor là chuỗi opaque rút gọn, không phải token thật):

```http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: private, no-store

{
  "items": [
    {"id":106,"categoryId":10,"status":"ACTIVE","priceCents":2500,
     "createdAt":"2026-11-18T10:06:00Z"},
    {"id":105,"categoryId":10,"status":"ACTIVE","priceCents":1200,
     "createdAt":"2026-11-18T10:05:00Z"}
  ],
  "nextCursor": "<opaque-signed-cursor>",
  "hasMore": true
}
```

Lần tiếp theo dùng **chính xác cùng filter và sort**:

```http
GET /api/v1/products?status=ACTIVE&categoryId=10&sort=createdAt_desc&limit=2&cursor=<url-encoded-cursor> HTTP/1.1
Authorization: Bearer <test-access-token>
Accept: application/json
```

```http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: private, no-store

{
  "items": [
    {"id":104,"categoryId":10,"status":"ACTIVE","priceCents":1200,
     "createdAt":"2026-11-18T10:04:00Z"},
    {"id":103,"categoryId":10,"status":"ACTIVE","priceCents":990,
     "createdAt":"2026-11-18T10:03:00Z"}
  ],
  "nextCursor": null,
  "hasMore": false
}
```

Trong dữ liệu ví dụ, product 101 bị loại vì DRAFT; 102 bị loại vì category 20; 201 thuộc tenant khác. Cursor ở response **được sinh từ phần tử cuối thực sự trả cho client**, không từ hàng “nhìn trước” thứ `limit+1`.

### Các tham số và quy ước bắt buộc

| Tham số | Kiểu | Quy ước |
| --- | --- | --- |
| `status` | Enum `ACTIVE` hoặc `DRAFT`; optional | Không truyền nghĩa là không lọc status |
| `categoryId` | Positive long; optional | Không truyền nghĩa là mọi category được phép |
| `minPriceCents` | Long ≥ 0; optional | Lọc `price_cents >= min` |
| `maxPriceCents` | Long ≥ 0; optional | Lọc `price_cents <= max` |
| `sort` | `createdAt_desc` hoặc `price_asc` | Mặc định `createdAt_desc` |
| `limit` | Integer 1–100 | Mặc định 25; không nhận `0`, âm hoặc >100 |
| `cursor` | Chuỗi Base64URL có chữ ký, optional | Opaque với client, chỉ do server cấp |

Trường hợp `minPriceCents > maxPriceCents` trả `400 INVALID_PRICE_RANGE`; sort lạ trả `400 INVALID_SORT`; cursor sai chữ ký, hết hạn hay không khớp context trả `400` cùng mã lỗi tương ứng. Không dùng `404` để báo “đã hết trang”; response cuối vẫn là `200` và `nextCursor=null`.

**Hợp đồng về limit:** trong bài, `limit` có thể thay đổi giữa các lượt trong khoảng hợp lệ; cursor **không** khóa theo limit vì giới hạn số hàng không ảnh hưởng vị trí seek. Nếu hệ thống chọn cố định page size trong cursor để dễ tối ưu/kiểm toán, phải kiểm tra và tài liệu hóa rõ khác biệt đó.

### Vì sao dùng `limit + 1`?

Truy vấn tối đa `limit+1` hàng để biết có trang tiếp theo:

1. Nếu lấy ≤ `limit` hàng, `hasMore=false` và `nextCursor=null`.
2. Nếu lấy `limit+1` hàng, trả **đúng `limit`** hàng đầu, `hasMore=true` và cursor từ **hàng thứ `limit`**.
3. Không đưa hàng nhìn trước vào response, không dùng khóa của nó làm cursor (sẽ bỏ sót nó khi lật trang).

`hasMore=true` chỉ xác nhận **tại thời điểm query** có ít nhất một hàng sau vị trí này; khi client gọi trang sau, dữ liệu có thể đã bị xóa hoặc thay đổi nên kết quả vẫn có thể rỗng. Nó không phải cam kết mọi request tương lai đều có dữ liệu.

## 5. Thiết kế dữ liệu PostgreSQL và index

Migration khởi đầu:

```sql
CREATE TABLE product (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    tenant_id BIGINT NOT NULL,
    category_id BIGINT NOT NULL,
    status VARCHAR(16) NOT NULL
        CHECK (status IN ('ACTIVE', 'DRAFT')),
    price_cents BIGINT NOT NULL CHECK (price_cents >= 0),
    name TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_product_tenant_created_id
    ON product (tenant_id, created_at DESC, id DESC);

CREATE INDEX idx_product_tenant_category_status_created_id
    ON product (
        tenant_id, category_id, status,
        created_at DESC, id DESC
    );

CREATE INDEX idx_product_tenant_category_status_price_id
    ON product (
        tenant_id, category_id, status,
        price_cents ASC, id ASC
    );
```

Index thứ hai và thứ ba phục vụ tốt các truy vấn **có equality filter** `tenant_id + category_id + status`. Với request chỉ lọc tenant, index đầu giúp thứ tự createdAt. Nếu workload phổ biến là `tenant_id + status` nhưng không có `category_id`, cần đo và có thể thêm index theo prefix đó: không mặc nhiên cho rằng index chứa category_id ở giữa sẽ luôn phục vụ tối ưu. Đừng tạo mọi tổ hợp index khi chưa có số liệu; mỗi index làm insert/update tốn thêm chi phí.

Giá lưu bằng đơn vị **cents** (số nguyên) để tránh so sánh số thực sai khác khi làm khóa sort. Nếu sản phẩm có nhiều currency, cần tách theo currency hoặc thống nhất quy tắc so sánh; không được sắp giá USD và VND trong một cột số mà không định nghĩa ngữ nghĩa. Trong ví dụ, `created_at`, `price_cents` và `id` đều `NOT NULL`.

### Dữ liệu thử nghiệm có thể tái lập

```sql
INSERT INTO product (
    id, tenant_id, category_id, status,
    price_cents, name, created_at
) VALUES
 (101, 7, 10, 'DRAFT',  1200, 'Draft item',
  '2026-11-18T10:01:00Z'),
 (102, 7, 20, 'ACTIVE', 3000, 'Other category',
  '2026-11-18T10:02:00Z'),
 (103, 7, 10, 'ACTIVE',  990, 'Mouse',
  '2026-11-18T10:03:00Z'),
 (104, 7, 10, 'ACTIVE', 1200, 'Keyboard A',
  '2026-11-18T10:04:00Z'),
 (105, 7, 10, 'ACTIVE', 1200, 'Keyboard B',
  '2026-11-18T10:05:00Z'),
 (106, 7, 10, 'ACTIVE', 2500, 'Headset',
  '2026-11-18T10:06:00Z'),
 (201, 8, 10, 'ACTIVE',  500, 'Other tenant',
  '2026-11-18T10:07:00Z');
```

Chạy trong database test cô lập hoặc rollback sau bài lab. Nếu môi trường dùng identity sequence và tự chèn ID cố định bằng `OVERRIDING SYSTEM VALUE` hoặc `BY DEFAULT`, cần điều chỉnh/đồng bộ sequence trước các insert tiếp theo. Ở đây `GENERATED BY DEFAULT` cho phép seed ID tường minh. **Không chạy câu lệnh seed trên bảng production**.

### Truy vấn keyset mặc định: createdAt_desc

```sql
SELECT id, category_id, status, price_cents,
       name, created_at
FROM product
WHERE tenant_id = :tenantId
  AND category_id = :categoryId
  AND status = :status
  AND created_at <= :asOf
  AND (created_at, id) < (:lastCreatedAt, :lastId)
ORDER BY created_at DESC, id DESC
LIMIT :fetchLimit;
```

Điều kiện `(created_at,id) < ...` chỉ có khi đã có cursor. `:fetchLimit` bằng `limit+1`, được kiểm tra tối đa 101. Các filter tùy chọn phải được **bỏ khỏi câu SQL nếu client không truyền** hoặc thể hiện theo cấu trúc được kiểm soát. Không thể lấy `:categoryId = null` rồi giữ nguyên điều kiện `category_id = :categoryId`: phép so sánh với `NULL` không trả những hàng mong đợi.

### Truy vấn thay thế: price_asc

```sql
SELECT id, category_id, status, price_cents,
       name, created_at
FROM product
WHERE tenant_id = :tenantId
  AND category_id = :categoryId
  AND status = :status
  AND price_cents >= :minPriceCents
  AND created_at <= :asOf
  AND (price_cents, id) > (:lastPriceCents, :lastId)
ORDER BY price_cents ASC, id ASC
LIMIT :fetchLimit;
```

Ở ví dụ này `minPriceCents` là filter có truyền; khi thiếu thì không có dòng điều kiện đó. Với `price_asc`, giá là **thuộc tính có thể đổi**, nên keyset có thể không còn bảo đảm mỗi ID xuất hiện tối đa một lần trong thời gian lật trang. Đây là một rủi ro về **consistency**, không phải lỗi cú pháp SQL.

### Kiểm tra planner

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT id, category_id, status, price_cents,
       name, created_at
FROM product
WHERE tenant_id = 7
  AND category_id = 10
  AND status = 'ACTIVE'
  AND (created_at, id) < (
      TIMESTAMPTZ '2026-11-18T10:05:00Z', 105
  )
ORDER BY created_at DESC, id DESC
LIMIT 3;
```

Quan sát số hàng đã đọc, buffers, index scan, sort và total execution time. Trên seed chỉ 7 hàng, PostgreSQL **có thể chọn sequential scan** vì bảng rất nhỏ; đó không đủ chứng minh index sai. Hãy thử dataset giả đủ lớn, phân bố filter thực tế, cập nhật statistics và so sánh các trang sâu. `EXPLAIN ANALYZE` thực thi truy vấn thật (ở đây là SELECT an toàn), nên không dùng `ANALYZE` tùy tiện với câu lệnh ghi dữ liệu trên production.

## 6. Cursor: hợp đồng bảo mật và tính nhất quán

Một cursor không nên chỉ là `lastId=105`, vì server còn cần biết **sort, filter, tenant, thời điểm snapshot tương đối** và cách phân biệt token hợp lệ với token giả.

Payload logic minh họa (chỉ để giải thích; không yêu cầu client đọc JSON này):

```json
{
  "v": 1,
  "tenant": 7,
  "sort": "createdAt_desc",
  "filterHash": "sha256-of-normalized-filters",
  "asOf": "2026-11-18T10:08:00Z",
  "lastCreatedAt": "2026-11-18T10:05:00Z",
  "lastPriceCents": null,
  "lastId": 105,
  "expiresAtEpochSeconds": 1795014000
}
```

Server tạo token theo ý tưởng:

```text
payloadBytes = UTF8(JSON(payload))
body = BASE64URL_NO_PADDING(payloadBytes)
signature = HMAC_SHA256(serverSecret, UTF8(body))
cursor = body + "." + BASE64URL_NO_PADDING(signature)
```

Mỗi lần sử dụng lại, server kiểm tra định dạng, chữ ký **trước khi tin nội dung**, version, expiry, tenant, filter hash và sort; cuối cùng kiểm tra các trường position phù hợp. Token nên có giới hạn độ dài để tránh parse đầu vào quá lớn.

**HMAC bảo vệ tính toàn vẹn, không mã hóa.** Người có cursor vẫn có thể giải mã Base64URL để đọc payload. Do đó không đặt access token, email, số thẻ, session ID hay PII vào cursor. Cursor cũng **không phải credential phân quyền**: request có cursor vẫn phải xác thực và chỉ truy vấn trong tenant hiện tại.

### Chuẩn hóa bộ lọc trước khi hash

Hai request có cùng ý nghĩa nên cho ra cùng filter hash:

```text
?status=ACTIVE&categoryId=10&minPriceCents=1000
?categoryId=10&minPriceCents=1000&status=ACTIVE
```

Thứ tự query parameter không quan trọng. Server parse **thành kiểu dữ liệu chuẩn hóa** (enum, long, range) rồi tính fingerprint từ một representation có thứ tự trường cố định. Phân biệt rõ `null` (không lọc) với chuỗi rỗng hoặc invalid; normalize default sort. Không hash raw query string, vì thứ tự tham số, encoding và giá trị mặc định sẽ tạo mismatch không cần thiết.

Ví dụ dạng canonical logic:

```text
filter-v1
status=ACTIVE
categoryId=10
minPriceCents=1000
maxPriceCents=null
```

Sort và tenant được kiểm tra riêng trong token; cũng có thể đưa chúng vào context hash, miễn có contract ổn định và cùng cách xử lý trên mọi instance. Nếu thay đổi thuật toán canonicalization, hãy tăng `v` và xác định thời gian hỗ trợ cursor phiên bản cũ.

### Khi nào trả lỗi?

| Lỗi | HTTP gợi ý | Problem Details `code` |
| --- | --- | --- |
| Cursor bị sửa byte/chữ ký không hợp lệ | `400` | `INVALID_CURSOR` |
| Cursor giải mã được nhưng đã hết hạn | `400` | `CURSOR_EXPIRED` |
| Cursor dùng với filter hoặc sort khác | `400` | `CURSOR_CONTEXT_MISMATCH` |
| Cursor tenant khác dù đã được ký | `400` hoặc `403` theo chính sách, không rò thông tin | `INVALID_CURSOR` |
| Sort không nằm trong allowlist | `400` | `INVALID_SORT` |
| `limit=0` hoặc `limit>100` | `400` | `INVALID_LIMIT` |
| Đã xác thực nhưng không được đọc category | `403` hoặc `404` theo chính sách | `FORBIDDEN` / `NOT_FOUND` |

Không đưa raw cursor, stack trace, HMAC secret hoặc SQL vào `detail`. Nếu token hết hạn, client thường phải **bắt đầu traversal mới**, không sửa timestamp/signature bằng tay. Nếu cần tiếp tục từ một checkpoint lâu dài, hãy thiết kế cơ chế checkpoint riêng thay vì kéo TTL cursor lên vô hạn.

### Rotation và vận hành

Secret ký cursor được giữ trong secret manager; mọi replica dùng key/phiên bản tương thích. Khi xoay khóa, có thể thêm `kid` vào token envelope, cho phép xác minh key cũ trong thời gian TTL còn hiệu lực, rồi loại bỏ an toàn. Đừng log token nguyên văn nếu nó mang metadata liên kết người dùng, dù bản thân nó không phải bearer credential.

## 7. Java/Spring: tách controller, parser, codec và repository

Một cách tổ chức implementation:

```text
ProductController
  └── ProductPageService
        ├── ProductFilterParser / canonical fingerprint
        ├── SignedCursorCodec
        ├── ProductQueryRepository
        └── Clock + tenant from verified identity

HTTP request
  → authenticate + resolve tenant
  → validate/normalize filters + sort + limit
  → verify cursor signature, expiry and context
  → query (limit+1), build new signed cursor
  → 200 page or typed 400 Problem Details
```

### 7.1. DTO và controller

```java
import java.time.Instant;
import java.util.List;
import org.springframework.http.CacheControl;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.*;

record ProductDto(
    long id, long categoryId, String status,
    long priceCents, String name, Instant createdAt
) {}

record ProductPage(
    List<ProductDto> items, String nextCursor, boolean hasMore
) {}

@RestController
@RequestMapping("/api/v1/products")
class ProductController {
    private final ProductPageService pages;
    private final TenantResolver tenantResolver;

    ProductController(ProductPageService pages, TenantResolver tenantResolver) {
        this.pages = pages;
        this.tenantResolver = tenantResolver;
    }

    @GetMapping
    ResponseEntity<ProductPage> list(
            @RequestParam(required = false) String status,
            @RequestParam(required = false) Long categoryId,
            @RequestParam(required = false) Long minPriceCents,
            @RequestParam(required = false) Long maxPriceCents,
            @RequestParam(defaultValue = "createdAt_desc") String sort,
            @RequestParam(defaultValue = "25") int limit,
            @RequestParam(required = false) String cursor,
            Authentication authentication) {

        long tenantId =
            tenantResolver.verifiedTenantId(authentication);
        ProductPage result = pages.list(
            tenantId, status, categoryId,
            minPriceCents, maxPriceCents,
            sort, limit, cursor
        );
        return ResponseEntity.ok()
            .cacheControl(CacheControl.noStore())
            .body(result);
    }
}
```

Đây là khung MVC, không phải một ứng dụng độc lập. `TenantResolver` phải dùng principal/claim đã được **xác minh chữ ký và quyền**, không tin `tenantId` trong query hoặc một header tùy ý do client gửi. `ProductPageService` kiểm tra điều kiện trước khi gửi SQL. Mẫu trả `no-store` vì danh sách có dữ liệu theo tenant và dễ thay đổi; hệ thống cache được thiết kế riêng có thể dùng `ETag`/cache policy khác nếu định nghĩa invalidation rõ ràng.

Nếu `limit=abc`, Spring thường chuyển đổi tham số thất bại và trả `400`; `limit=0` hoặc `limit=101` chuyển kiểu được nhưng vẫn phải bị service từ chối. Dùng `int` ở controller không làm giới hạn 1–100 xuất hiện tự động.

### 7.2. Enum sort và bộ lọc đã chuẩn hóa

```java
enum ProductSort {
    CREATED_AT_DESC("createdAt_desc"),
    PRICE_ASC("price_asc");

    private final String wireValue;
    ProductSort(String wireValue) {
        this.wireValue = wireValue;
    }
    String wireValue() {
        return wireValue;
    }
    static ProductSort parse(String raw) {
        for (ProductSort option : values()) {
            if (option.wireValue.equals(raw)) return option;
        }
        throw new InvalidQueryException("INVALID_SORT");
    }
}

record ProductFilters(
    String status, Long categoryId,
    Long minPriceCents, Long maxPriceCents
) {
    static ProductFilters normalized(
            String status, Long categoryId,
            Long minPriceCents, Long maxPriceCents) {

        if (status != null
                && !status.equals("ACTIVE")
                && !status.equals("DRAFT")) {
            throw new InvalidQueryException("INVALID_STATUS");
        }
        if (categoryId != null && categoryId <= 0) {
            throw new InvalidQueryException("INVALID_CATEGORY");
        }
        if ((minPriceCents != null && minPriceCents < 0)
                || (maxPriceCents != null && maxPriceCents < 0)
                || (minPriceCents != null && maxPriceCents != null
                    && minPriceCents > maxPriceCents)) {
            throw new InvalidQueryException("INVALID_PRICE_RANGE");
        }
        return new ProductFilters(
            status, categoryId, minPriceCents, maxPriceCents);
    }
}
```

`InvalidQueryException` là exception nghiệp vụ minh họa cần được khai báo và ánh xạ thành `400`. Bài dùng enum/string có kiểm tra tường minh để tránh chấp nhận giá trị sort tùy ý. Không nối trực tiếp `sort` từ URL vào `ORDER BY` vì bind parameter SQL **không thể dùng để thay một identifier/keyword ORDER BY**.

### 7.3. SQL có cấu trúc, không ghép dữ liệu user vào SQL

```java
import java.sql.Timestamp;
import java.time.Instant;
import java.util.List;
import org.springframework.jdbc.core.namedparam.MapSqlParameterSource;
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate;

record ProductRow(
    long id, long categoryId, String status,
    long priceCents, String name, Instant createdAt
) {}

record Seek(
    Instant lastCreatedAt, Long lastPriceCents, long lastId
) {}

class ProductQueryRepository {
    private final NamedParameterJdbcTemplate jdbc;

    ProductQueryRepository(NamedParameterJdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    List<ProductRow> fetch(
            long tenantId, ProductFilters filters,
            ProductSort sort, Instant asOf,
            Seek seek, int fetchLimit) {

        StringBuilder sql = new StringBuilder("""
            SELECT id, category_id, status,
                   price_cents, name, created_at
            FROM product
            WHERE tenant_id = :tenantId
              AND created_at <= :asOf
            """);

        MapSqlParameterSource params =
            new MapSqlParameterSource("tenantId", tenantId)
                .addValue("asOf", Timestamp.from(asOf))
                .addValue("fetchLimit", fetchLimit);

        if (filters.status() != null) {
            sql.append(" AND status = :status");
            params.addValue("status", filters.status());
        }
        if (filters.categoryId() != null) {
            sql.append(" AND category_id = :categoryId");
            params.addValue("categoryId", filters.categoryId());
        }
        if (filters.minPriceCents() != null) {
            sql.append(" AND price_cents >= :minPrice");
            params.addValue("minPrice", filters.minPriceCents());
        }
        if (filters.maxPriceCents() != null) {
            sql.append(" AND price_cents <= :maxPrice");
            params.addValue("maxPrice", filters.maxPriceCents());
        }

        if (sort == ProductSort.CREATED_AT_DESC) {
            if (seek != null) {
                sql.append(
                    " AND (created_at, id) < (:lastCreatedAt, :lastId)");
                params.addValue(
                    "lastCreatedAt", Timestamp.from(seek.lastCreatedAt()));
                params.addValue("lastId", seek.lastId());
            }
            sql.append(" ORDER BY created_at DESC, id DESC");
        } else {
            if (seek != null) {
                sql.append(
                    " AND (price_cents, id) > (:lastPrice, :lastId)");
                params.addValue("lastPrice", seek.lastPriceCents());
                params.addValue("lastId", seek.lastId());
            }
            sql.append(" ORDER BY price_cents ASC, id ASC");
        }
        sql.append(" LIMIT :fetchLimit");

        return jdbc.query(sql.toString(), params, (rs, rowNum) ->
            new ProductRow(
                rs.getLong("id"),
                rs.getLong("category_id"),
                rs.getString("status"),
                rs.getLong("price_cents"),
                rs.getString("name"),
                rs.getTimestamp("created_at").toInstant()
            )
        );
    }
}
```

Trong code mẫu:

- **Mọi giá trị đầu vào** (`tenantId`, filter, cursor position, limit) đi qua named parameters.
- Chỉ **những mảnh SQL cố định** do server viết được append; `sort` đã chuyển thành enum từ allowlist. Đây là cách ghép SQL an toàn, khác việc nối raw input trực tiếp vào câu query.
- Predicate `tenant_id = :tenantId` có mặt **trong mọi nhánh**, kể cả khi cursor trỏ tới sản phẩm của tenant khác.
- `created_at <= :asOf` là một **upper watermark** để hạn chế thấy hàng mới có timestamp sau mốc bắt đầu; nó **không** đủ đảm bảo snapshot tuyệt đối.
- `fetchLimit` phải là `limit+1` đã kiểm tra ở service, không nhận giá trị tùy ý từ client.

Lưu ý khoảng trắng khi ghép SQL trong production: các mảnh `AND` và `ORDER BY` nối tiếp đều bắt đầu bằng khoảng trắng; nếu format code thay đổi, phải kiểm tra SQL đã render ra. Unit/integration test phải xác nhận truy vấn chạy thật.

### 7.4. Lấy mốc thời gian từ database

Khi client chưa có cursor, service có thể lấy `asOf` từ PostgreSQL rồi gắn vào cursor; ví dụ:

```java
Instant asOf = jdbcTemplate.queryForObject(
    "SELECT clock_timestamp()",
    Timestamp.class
).toInstant();
```

Mốc này là **rào giới hạn created_at**, không phải một MVCC snapshot export được giữ cho toàn bộ các HTTP request. `clock_timestamp()` phản ánh đồng hồ DB; một transaction bắt đầu trước mốc nhưng commit sau mốc vẫn có thể xuất hiện muộn với `created_at` cũ. Nếu cần snapshot nhất quán tuyệt đối, dùng chiến lược chuyên biệt ở phần 9.

Đối với ngày/giờ trên wire, dùng `Instant`/ISO-8601 UTC, không serialize theo timezone của máy người dùng. PostgreSQL `TIMESTAMPTZ` biểu diễn thời điểm; lưu và so sánh cùng precision của DB. Khi xây cursor từ `ProductRow`, dùng giá trị đọc ra từ DB thay vì ghép lại từ hiển thị đã bị cắt mili-giây.

## 8. Kết nối cursor codec với service

### 8.1. Record cursor và mẫu HMAC codec

Để tách đơn giản khỏi cấu hình Jackson Java Time, mẫu payload giữ timestamp ở dạng chuỗi ISO-8601 UTC. Khi đọc cursor, service phải parse timestamp và xác minh đúng loại khóa theo sort.

```java
record CursorState(
    int v,
    long tenantId,
    String sort,
    String filterHash,
    String asOf,
    String lastCreatedAt,
    Long lastPriceCents,
    Long lastId,
    long expiresAtEpochSeconds
) {}
```

Codec minh họa dùng HMAC-SHA256, Base64URL không padding và so sánh chữ ký bằng `MessageDigest.isEqual` thay vì `String.equals`:

```java
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.MessageDigest;
import java.util.Base64;
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;

final class SignedCursorCodec {
    private final ObjectMapper json = new ObjectMapper();
    private final byte[] secret;
    private final Base64.Encoder encoder =
        Base64.getUrlEncoder().withoutPadding();
    private final Base64.Decoder decoder = Base64.getUrlDecoder();

    SignedCursorCodec(byte[] secret) {
        if (secret == null || secret.length < 32) {
            throw new IllegalArgumentException(
                "Signing key must be at least 32 bytes");
        }
        this.secret = secret.clone();
    }

    String encode(CursorState state) {
        try {
            String body = encoder.encodeToString(
                json.writeValueAsBytes(state));
            return body + "." + encoder.encodeToString(sign(body));
        } catch (JsonProcessingException ex) {
            throw new IllegalStateException("Cursor serialization failed", ex);
        }
    }

    CursorState decode(String token) {
        if (token == null || token.isEmpty() || token.length() > 4096) {
            throw new InvalidCursorException();
        }
        String[] parts = token.split("\\.", -1);
        if (parts.length != 2 || parts[0].isEmpty()
                || parts[1].isEmpty()) {
            throw new InvalidCursorException();
        }
        try {
            byte[] actual = decoder.decode(parts[1]);
            byte[] expected = sign(parts[0]);
            if (!MessageDigest.isEqual(actual, expected)) {
                throw new InvalidCursorException();
            }
            return json.readValue(
                decoder.decode(parts[0]), CursorState.class);
        } catch (IllegalArgumentException | java.io.IOException ex) {
            throw new InvalidCursorException();
        }
    }

    private byte[] sign(String body) {
        try {
            Mac mac = Mac.getInstance("HmacSHA256");
            mac.init(new SecretKeySpec(secret, "HmacSHA256"));
            return mac.doFinal(
                body.getBytes(StandardCharsets.UTF_8));
        } catch (GeneralSecurityException ex) {
            throw new IllegalStateException("HMAC unavailable", ex);
        }
    }
}
```

`InvalidCursorException` trong ví dụ là exception ứng dụng cần khai báo và map thành `400 INVALID_CURSOR`. Decode trước khi dùng dữ liệu, nhưng **chữ ký đúng vẫn chưa chứng minh cursor có context hợp lệ**: service còn phải kiểm tra version, expiry, tenant, filter, sort và position. `ObjectMapper` trên snippet này dành riêng cho record cursor đơn giản; API JSON của domain có thể có cấu hình mapper riêng.

Trong hệ thống production cần bổ sung key ID/rotation, kiểm soát độ lớn payload sau decode, error metrics không lộ token, quản trị khóa bảo mật và thử nghiệm tương thích nhiều replica. Đừng dùng một literal `"secret"` trong mã nguồn hoặc log khóa HMAC. HMAC có thể xác nhận token do service phát ra; **nó không cấp quyền xem bất kỳ sản phẩm nào**.

### 8.2. Fingerprint bộ lọc

Một helper minh họa:

```java
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.Base64;

final class ProductFilterFingerprint {
    static String of(ProductFilters f) {
        String canonical =
            "filters-v1\n"
            + "status=" + stable(f.status()) + "\n"
            + "categoryId=" + stable(f.categoryId()) + "\n"
            + "minPriceCents=" + stable(f.minPriceCents()) + "\n"
            + "maxPriceCents=" + stable(f.maxPriceCents()) + "\n";
        try {
            byte[] digest = MessageDigest.getInstance("SHA-256").digest(
                canonical.getBytes(StandardCharsets.UTF_8));
            return Base64.getUrlEncoder()
                .withoutPadding().encodeToString(digest);
        } catch (NoSuchAlgorithmException ex) {
            throw new IllegalStateException(ex);
        }
    }

    private static String stable(Object value) {
        return value == null ? "<null>" : value.toString();
    }
}
```

Ở đây giá trị lọc đã bị giới hạn thành **enum cố định hoặc số nguyên** nên không chứa newline/chuỗi điều khiển; nếu bổ sung free-text filter, phải dùng canonical JSON/encoding có ranh giới rõ ràng (không nối chuỗi nhập tự do vào fingerprint theo cách dễ va chạm ngữ nghĩa). Cần phân biệt `status=null` với `status=""` theo quy tắc validation của API; không nên xem mọi input tùy ý là tương đương.

### 8.3. Page service: xác thực context, query limit+1, tạo cursor mới

Pseudocode Java (các dependency/exception được mô tả ở các phần trước):

```java
ProductPage list(
        long tenantId, String rawStatus, Long categoryId,
        Long minPrice, Long maxPrice,
        String rawSort, int limit, String cursorToken) {

    if (limit < 1 || limit > 100) {
        throw new InvalidQueryException("INVALID_LIMIT");
    }

    ProductFilters filters = ProductFilters.normalized(
        rawStatus, categoryId, minPrice, maxPrice);
    ProductSort sort = ProductSort.parse(rawSort);
    String fingerprint = ProductFilterFingerprint.of(filters);
    CursorState old = cursorToken == null
        ? null : cursorCodec.decode(cursorToken);

    Instant asOf;
    Seek seek = null;
    long expiresAt;

    if (old == null) {
        asOf = repository.currentDbTime();
        expiresAt = clock.instant()
            .plus(Duration.ofMinutes(15)).getEpochSecond();
    } else {
        if (old.v() != 1 || old.tenantId() != tenantId) {
            throw new InvalidCursorException();
        }
        if (clock.instant().getEpochSecond()
                >= old.expiresAtEpochSeconds()) {
            throw new InvalidQueryException("CURSOR_EXPIRED");
        }
        if (!sort.wireValue().equals(old.sort())
                || !fingerprint.equals(old.filterHash())) {
            throw new InvalidQueryException(
                "CURSOR_CONTEXT_MISMATCH");
        }
        if (old.lastId() == null || old.lastId() <= 0) {
            throw new InvalidCursorException();
        }

        try {
            asOf = Instant.parse(old.asOf());
            if (sort == ProductSort.CREATED_AT_DESC) {
                if (old.lastCreatedAt() == null
                        || old.lastPriceCents() != null) {
                    throw new InvalidCursorException();
                }
                seek = new Seek(
                    Instant.parse(old.lastCreatedAt()),
                    null, old.lastId());
            } else {
                if (old.lastPriceCents() == null
                        || old.lastCreatedAt() != null
                        || old.lastPriceCents() < 0) {
                    throw new InvalidCursorException();
                }
                seek = new Seek(
                    null, old.lastPriceCents(), old.lastId());
            }
        } catch (java.time.format.DateTimeParseException ex) {
            throw new InvalidCursorException();
        }
        expiresAt = old.expiresAtEpochSeconds();
    }

    List<ProductRow> fetched = repository.fetch(
        tenantId, filters, sort, asOf, seek, limit + 1);
    boolean hasMore = fetched.size() > limit;
    List<ProductRow> visible = fetched.subList(
        0, Math.min(limit, fetched.size()));

    String nextCursor = null;
    if (hasMore) {
        ProductRow last = visible.get(visible.size() - 1);
        CursorState next = new CursorState(
            1, tenantId, sort.wireValue(), fingerprint,
            asOf.toString(),
            sort == ProductSort.CREATED_AT_DESC
                ? last.createdAt().toString() : null,
            sort == ProductSort.PRICE_ASC
                ? last.priceCents() : null,
            last.id(), expiresAt
        );
        nextCursor = cursorCodec.encode(next);
    }

    List<ProductDto> items = visible.stream()
        .map(row -> new ProductDto(
            row.id(), row.categoryId(), row.status(),
            row.priceCents(), row.name(), row.createdAt()))
        .toList();
    return new ProductPage(items, nextCursor, hasMore);
}
```

Đoạn service là **khung thuật toán**: `repository.currentDbTime()` cần triển khai bằng SQL clock DB, `clock` được inject, `cursorCodec` và `repository` là dependency, `InvalidCursorException`/`InvalidQueryException` cần HTTP advice. Nếu dùng Java code thực tế, đưa method này vào `ProductPageService` có dependency injection, import đầy đủ và unit test từng branch. Không dùng một timestamp giả để thay thời gian DB trên nhiều replica trừ khi mô hình consistency được định nghĩa.

Các điểm quan trọng:

- Cursor mới dùng khóa **hàng cuối được trả** (`visible`), không phải hàng nhìn trước.
- `expiresAt` được giữ **cố định từ trang đầu**, không kéo dài mỗi lần lật trang để tránh traversal vô hạn dùng cùng một mốc cũ.
- Thay `limit` hợp lệ giữa các trang không làm sai khóa seek; thay filter/sort bị phát hiện qua context.
- Cursor có chữ ký vẫn cần check tenant theo identity hiện tại và SQL `tenant_id`; việc đổi tenant/principal giữa các request không được vượt qua ranh giới dữ liệu.
- API trả trang cuối với cursor `null`, không lặp lại cursor cũ. Một trang có thể rỗng ở lượt gọi sau dù trước đó `hasMore=true` vì dữ liệu đã thay đổi.

### 8.4. Problem Details và OpenAPI

Ví dụ cursor không khớp bộ lọc:

```http
HTTP/1.1 400 Bad Request
Content-Type: application/problem+json
Cache-Control: no-store

{
  "type": "https://api.example.com/problems/cursor-context-mismatch",
  "title": "Invalid pagination cursor",
  "status": 400,
  "detail": "Cursor không phù hợp với bộ lọc hoặc thứ tự hiện tại.",
  "code": "CURSOR_CONTEXT_MISMATCH"
}
```

Không trả nguyên cursor hay ký tự đã decode trong lỗi. Mã `CURSOR_EXPIRED` có thể hướng dẫn client bắt đầu lại từ trang đầu; `INVALID_SORT` giúp client sửa query. `@RestControllerAdvice` cần map riêng những exception đã biết sang `400`; không bắt tất cả `Exception` rồi ép thành `400` vì như vậy che lỗi server và authorization.

Fragment OpenAPI 3.1 (giản lược phần schema response):

```yaml
openapi: 3.1.0
info:
  title: Product Catalog API
  version: 1.0.0
paths:
  /api/v1/products:
    get:
      operationId: listProducts
      summary: Liệt kê sản phẩm bằng keyset pagination
      description: |
        Cursor phụ thuộc tenant, status, category, price range và sort.
        Kết quả theo best-effort traversal, không bảo đảm MVCC snapshot
        xuyên nhiều request. Các cột sort có thể đổi sẽ ảnh hưởng kết quả.
      parameters:
        - in: query
          name: status
          schema:
            type: string
            enum: [ACTIVE, DRAFT]
        - in: query
          name: categoryId
          schema: {type: integer, format: int64, minimum: 1}
        - in: query
          name: minPriceCents
          schema: {type: integer, format: int64, minimum: 0}
        - in: query
          name: maxPriceCents
          schema: {type: integer, format: int64, minimum: 0}
        - in: query
          name: sort
          schema:
            type: string
            enum: [createdAt_desc, price_asc]
            default: createdAt_desc
        - in: query
          name: limit
          schema: {type: integer, minimum: 1, maximum: 100, default: 25}
        - in: query
          name: cursor
          schema: {type: string}
          description: Opaque cursor do trang trước trả về.
      responses:
        '200':
          description: Một trang kết quả
          content:
            application/json:
              schema:
                type: object
                required: [items, nextCursor, hasMore]
                properties:
                  items:
                    type: array
                    items: {type: object}
                  nextCursor:
                    type: [string, 'null']
                  hasMore: {type: boolean}
        '400':
          description: Sai filter, sort, limit hoặc cursor
          content:
            application/problem+json:
              schema: {type: object}
        '401': {description: Chưa xác thực}
        '403': {description: Không được phép}
      security:
        - bearerAuth: []
components:
  securitySchemes:
    bearerAuth: {type: http, scheme: bearer}
```

Trong production, không để `items: {type: object}` và Problem Details chung chung: trỏ tới `ProductDto`, `ApiProblem` schemas chuẩn, thêm examples và bảo đảm query/response khớp controller. `type: [string, 'null']` là cú pháp JSON Schema trong OpenAPI 3.1; nếu dùng OpenAPI 3.0, biểu diễn nullability khác. Kiểm tra spec bằng OpenAPI validator và contract test.

## 9. Phần trọng tâm: dữ liệu thay đổi khi client đang lật trang

**Keyset bảo vệ vị trí seek theo khóa sort, không đóng băng toàn bộ database.** Hãy phân biệt ba cấp độ yêu cầu:

1. **Best-effort browsing:** người dùng lướt sản phẩm; thay đổi mới có thể xuất hiện hoặc không, danh sách không cần là một snapshot bất biến.
2. **Ổn định traversal theo khóa bất biến:** cursor dựa trên `created_at + id` không đổi, tránh dịch offset khi insert ở đầu và giữ thứ tự qua các trang; nhưng filter có thể thay đổi.
3. **Snapshot chính xác:** người dùng xuất danh sách đối soát/audit; cần cố định tập hàng và đôi khi cả giá trị của từng hàng tại một thời điểm hoặc version.

Chọn cấp độ ngay trong đặc tả yêu cầu. **Không gọi cấp độ 2 là “snapshot consistency”** khi chưa có snapshot thực sự.

### 9.1. Insert mới hơn cursor với createdAt_desc

Trang đầu của tenant 7/category 10/ACTIVE trả `[106,105]`; cursor có last key `(10:05,105)`. Ngay sau đó thêm sản phẩm 107 với `created_at = 10:09`.

```text
Trước insert: [106,105] | [104,103]
Sau insert:   [107,106,105,104,103]
Cursor:                      (10:05,105)
Trang tiếp:               [104,103]
```

Vì predicate seek chọn khóa **nhỏ hơn** `(10:05,105)`, 107 không làm lặp 105 hay 106. Nếu API dùng thêm `created_at <= :asOf` và 107 có timestamp sau mốc bắt đầu, nó cũng bị chặn bởi watermark.

**Giới hạn:** một insert mới có `created_at` cũ (backfill), hoặc một transaction commit muộn với timestamp đã được cấp trước `asOf`, có thể xuất hiện ở trang sau. Bởi vậy upper timestamp watermark chỉ là **giảm nhiễu**, không phải MVCC snapshot cứng.

### 9.2. Delete bản ghi ở giữa các trang

Trang đầu `[106,105]`, trước khi lấy trang sau có người xóa 104:

```text
Ban đầu:      [106,105] | [104,103]
Sau delete:   [106,105] | [103]
Cursor:                    (10:05,105)
Trang sau:                 [103]
```

Không có 104 vì nó đã bị xóa; keyset không thể trả về một row không còn tồn tại trong bảng truy vấn hiện tại. Với nhu cầu audit “tập sản phẩm đúng tại thời điểm bắt đầu”, đây là vi phạm snapshot, dù **không có lặp do offset**.

### 9.3. Filter status/category thay đổi

Client lọc `status=ACTIVE`. Trang đầu trả `[106,105]`. Nếu product 104 được đổi từ ACTIVE thành DRAFT trước trang sau, nó biến mất. Nếu một product cũ hơn cursor vừa chuyển DRAFT → ACTIVE, nó có thể xuất hiện trên trang sau dù không thuộc tập lúc bắt đầu.

Với `categoryId=10`, một sản phẩm chuyển category 20 → 10 cũng thay đổi membership. Cursor đã ký **không ngăn** mutation của bảng; nó chỉ ngăn client thay đổi filter/sort giữa các request mà không bắt đầu traversal mới.

Nếu nghiệp vụ cần dữ liệu chính xác ở `asOf`, phải có lịch sử phiên bản membership hoặc materialize danh sách ID theo snapshot. Việc áp dụng `created_at <= asOf` không giải quyết thay đổi status/category sau asOf.

### 9.4. Giá thay đổi khi đang sắp price_asc: lặp và bỏ sót

Ban đầu (tenant 7/category 10/ACTIVE):

```text
Vị trí 1        2         3         4
          (990,103) (1200,104) (1200,105) (2500,106)
Trang 1        [103,104]
Cursor = (1200,104)
```

**Kịch bản lặp:** sau khi client đã xem 103, giá của 103 tăng từ 990 lên 2000. Danh sách mới:

```text
          (1200,104) (1200,105) (2000,103) (2500,106)
Trang 2 sau (1200,104): [105,103]
```

`103` xuất hiện lần hai vì nó **di chuyển từ trước cursor ra sau cursor**. Query và HMAC đều đúng nhưng việc sort key có thể đổi làm traversal không còn ổn định.

**Kịch bản bỏ sót:** thay vì tăng giá 103, sau trang 1 giá sản phẩm **105 chưa xem** giảm từ 1200 xuống 800:

```text
          (800,105) (990,103) (1200,104) (2500,106)
Trang 2 sau (1200,104): [106]
```

`105` đã di chuyển về trước cursor nên sẽ không xuất hiện trong các trang tiếp theo. Client dùng `Set<id>` để dedupe có thể loại **lặp**, nhưng **không thể khôi phục** một row chưa từng nhận.

Đây là điểm phải trình bày trong phần giải thích nộp bài: keyset cho một bảng mutable không đồng nghĩa giao dịch snapshot xuyên các lần GET.

### 9.5. Thuộc tính created_at cũng không được tùy tiện cập nhật

Nếu ứng dụng cho phép sửa `created_at` hoặc dùng một cột sort mutable như `updated_at`, những rủi ro di chuyển khóa ở kịch bản price cũng có thể xuất hiện. Trong bài lab, quy ước `created_at` chỉ được đặt khi tạo và **bất biến** về sau; database/ứng dụng nên có cơ chế bảo vệ quy tắc này.

Ngay cả với khóa bất biến, thay đổi status, category, giá khi đang lọc hoặc xóa row vẫn ảnh hưởng tập dữ liệu. Một cách mô tả trung thực:

> “API dùng keyset theo khóa tạo bất biến để giảm lặp/bỏ sót do insert ở đầu. Kết quả là best-effort và có thể thay đổi khi record bị cập nhật hoặc xóa. Endpoint này không bảo đảm snapshot cố định giữa các trang.”

## 10. Nếu cần snapshot thật, thiết kế gì?

Đối với báo cáo tài chính, đối soát tồn kho hoặc xuất danh sách cần **đầy đủ đúng một phiên bản**, có một số chiến lược:

| Chiến lược | Cách làm | Đánh đổi |
| --- | --- | --- |
| **Materialized snapshot** | Tạo job ghi danh sách ID + sort key, hoặc cả dữ liệu xuất, ở một version/snapshot ID; phân trang theo snapshot đó | Tốn storage/TTL, cần xử lý quyền và cleanup |
| **Temporal/versioned read model** | Lưu lịch sử hiệu lực (`valid_from`/`valid_to` hoặc commit sequence), query `AS OF version` | Schema/truy vấn phức tạp; phải lưu đầy đủ biến động và thứ tự commit |
| **File export bất biến** | `POST` tạo export job, trả `202 + operation`; khi xong tải file cố định (có checksum/version) | Không phải trải nghiệm danh sách tương tác real-time |
| **Database snapshot giữ transaction** | Dùng một snapshot/transaction có cùng MVCC view cho các lần đọc liên quan | Giữ transaction dài qua nhiều HTTP request thường gây áp lực VACUUM/connection và khó vận hành |
| **Change feed / CDC** | Liệt kê snapshot cơ sở rồi áp dụng các event có sequence/watermark | Thích hợp đồng bộ liên tục, yêu cầu protocol/resume/deduplication khác pagination |

Với PostgreSQL, snapshot MVCC được áp dụng theo **transaction và isolation level**. Hai HTTP GET riêng biệt với transaction mới ở `READ COMMITTED` không cùng nhìn một snapshot. Việc gọi `REPEATABLE READ` riêng cho từng GET cũng không tự nối hai transaction thành một snapshot. Các cơ chế export snapshot của PostgreSQL yêu cầu quản lý transaction nguồn và vòng đời snapshot có giới hạn; thường **không thích hợp** cho nhiều phút người dùng lật trang qua Internet.

### Snapshot resource là một API riêng

Ví dụ một hợp đồng được thiết kế có chủ đích:

```http
POST /api/v1/product-exports HTTP/1.1
Content-Type: application/json
Idempotency-Key: 75fb8454-16b3-4a8e-ae25-e54b8db06975

{"status":"ACTIVE","categoryId":10,"sort":"price_asc"}

HTTP/1.1 202 Accepted
Location: /api/v1/operations/op-export-42
```

Sau khi job thành công, operation có thể trả `downloadUrl` hoặc `snapshotId` để đọc tập dữ liệu cố định. **Snapshot cần xác định là snapshot ID hay snapshot giá trị**: nếu chỉ lưu ID rồi join dữ liệu product hiện tại, một sản phẩm có thể đã đổi giá/tên sau thời điểm chụp. Nếu yêu cầu “giá đúng tại 10:08”, phải materialize cả giá hoặc dùng versioned storage.

Không trả `202` sau khi chỉ đẩy task vào queue RAM không bền vững. Lưu operation + outbox/job record trong một transaction trước khi phản hồi, theo hợp đồng xử lý bất đồng bộ; bảo vệ tài nguyên snapshot theo tenant và đặt TTL rõ ràng.

### Đồng bộ dữ liệu thay đổi là bài toán khác phân trang

Nếu client cần “tải toàn bộ dữ liệu hiện tại rồi tiếp tục nhận thay đổi”, hãy xem xét:

1. Snapshot/traversal lần đầu với một version/watermark xác định.
2. Nhận **change events** hoặc đọc endpoint `/changes?afterSequence=...` theo sequence đơn điệu được backend đảm bảo.
3. Áp dụng upsert/delete theo event ID/version, chống trùng và lưu checkpoint bền vững.
4. Đối soát định kỳ nếu retention event không đủ hoặc mất checkpoint.

Đừng dùng `updated_at DESC` kết hợp cursor thông thường như thể đó là change feed hoàn hảo; các bản ghi được update có thể nhảy qua cursor, timestamp có thể trùng và delete có thể không phát hiện nếu không có tombstone/event.

## 11. Bộ bài lab theo từng mốc

### Lab A — Trang đầu và trang sau

1. Tạo schema/index và seed dữ liệu của phần 5 trên database test.
2. Triển khai `GET /api/v1/products` trả `limit+1` để quyết định `hasMore`.
3. Gọi bằng tenant 7 với `status=ACTIVE&categoryId=10&sort=createdAt_desc&limit=2`.
4. Kiểm tra trang đầu `[106,105]`, trang hai `[104,103]`, sau đó cursor rỗng/null.
5. Đổi sang `sort=price_asc`: trang đầu `[103,104]`, trang hai `[105,106]`.

**Kết quả đạt:** mỗi request dùng seek predicate (không offset), các row cùng giá 1200 không bị mất, hai tenant không trộn dữ liệu, trang cuối có `hasMore=false`.

### Lab B — Bộ lọc và context của cursor

1. Lọc `minPriceCents=1200` và `maxPriceCents=2500` với `sort=price_asc`; trong tenant 7/category 10/ACTIVE, kết quả hợp lệ là `[104,105,106]`.
2. Lấy cursor trang đầu, đổi `status=ACTIVE` thành `status=DRAFT`; API phải trả `400 CURSOR_CONTEXT_MISMATCH`.
3. Dùng cursor `createdAt_desc` với `sort=price_asc`; cũng phải từ chối.
4. Gửi đúng filter nhưng đảo thứ tự query parameter; cursor phải tiếp tục hợp lệ.
5. Đổi `limit=2` thành `limit=1`; trong contract của bài này cursor vẫn hợp lệ.

**Kết quả đạt:** parse/normalize đúng, fingerprint ổn định, không dùng raw query string làm định danh bộ lọc.

### Lab C — Cursor có chữ ký và phân quyền

1. Thay một ký tự trong token; server trả `400 INVALID_CURSOR`, không thực thi query theo position giả.
2. Giả lập clock vượt TTL; server trả `400 CURSOR_EXPIRED`.
3. Dùng cursor tạo từ tenant 7 trong request xác thực là tenant 8; từ chối, không hiển thị bản ghi tenant 7.
4. Gửi token dài hơn giới hạn, Base64URL sai, JSON sai shape, version không hỗ trợ; tất cả đều thất bại an toàn.
5. Kiểm tra access log, trace và error response không chứa secret HMAC hoặc raw token.

**Kết quả đạt:** signed cursor không là giấy thông hành; quyền và predicate tenant vẫn bắt buộc trên mọi request.

### Lab D — Mutation và giới hạn consistency

1. Với `createdAt_desc`, lấy trang đầu `[106,105]` rồi insert 107 mới hơn. Đọc trang tiếp: không lặp 106/105; 107 thường không thuộc traversal cũ.
2. Reset dữ liệu; lấy trang đầu rồi xóa 104. Trang sau thiếu 104; giải thích vì sao điều này **không** phải snapshot.
3. Với `price_asc`, lấy trang đầu `[103,104]` rồi đổi giá 103 từ 990 → 2000; trang tiếp có thể chứa 103 lần hai.
4. Reset; sau trang đầu giảm giá 105 từ 1200 → 800; trang tiếp có thể **không còn thấy 105**.
5. Lặp thử nghiệm status/category thay đổi, sau đó đề xuất materialized snapshot nếu business requirement không cho phép bỏ sót.

**Kết quả đạt:** không “sửa” bài toán bằng cách gán HMAC/upper watermark thành snapshot, mà trình bày đúng mức bảo đảm và chọn kiến trúc phù hợp.

## 12. Kiểm thử tự động: điều cần chứng minh

### 12.1. Ma trận contract + integration tests

| Test | Input hoặc tình huống | Kết quả mong đợi |
| --- | --- | --- |
| Default sort | Tenant 7, ACTIVE, category 10, limit 2 | Trang 1 `[106,105]`; trang 2 `[104,103]` |
| Tie breaker | Hai sản phẩm cùng `created_at` | `id DESC` được áp dụng, không bỏ sót |
| Sort giá | Price asc, limit 2 | Trang 1 `[103,104]`; trang 2 `[105,106]` |
| Filter khoảng giá | 1200–2500, ACTIVE, category 10 | `[104,105,106]` theo price asc |
| Giá trị filter rỗng | Không truyền status/category | Truy vấn không tự bỏ tất cả row |
| Invalid range | `minPriceCents=3000&maxPriceCents=100` | `400 INVALID_PRICE_RANGE` |
| Invalid limit | `limit=0` hoặc `limit=101` | `400 INVALID_LIMIT` |
| Invalid type | `categoryId=abc` | `400` do binding/conversion |
| Invalid sort | `sort=created_at%3BDROP...` | `400 INVALID_SORT`, không dùng raw SQL |
| Cursor tampered | Sửa một byte payload/signature | `400 INVALID_CURSOR` |
| Cursor expired | Fake clock sau expiry | `400 CURSOR_EXPIRED` |
| Cursor context | Cùng cursor, khác status/category/sort | `400 CURSOR_CONTEXT_MISMATCH` |
| Cursor context order | Cùng filter nhưng query parameter đảo vị trí | Vẫn tiếp tục hợp lệ |
| Cursor page size | Đổi `limit=2` sang `limit=1` | Tiếp tục hợp lệ theo contract bài học |
| Tenant isolation | Cursor/request có tenant khác | Không trả hàng tenant ban đầu |
| Concurrent new head | Insert 107 mới sau trang 1 | Không lặp 106,105 trong traversal cũ |
| Delete unseen row | Xóa 104 trước trang 2 | 104 không còn; mô tả giới hạn snapshot |
| Price move forward | Tăng giá 103 sau trang 1 | 103 **có thể xuất hiện hai lần** |
| Price move backward | Giảm giá 105 sau trang 1 | 105 **có thể bị bỏ sót** |
| Empty result | Filter không khớp | `200`, items `[]`, cursor `null` |
| Multiple replicas | Cursor ký ở replica A, dùng tại B | Chữ ký xác minh nếu cùng key/version |
| SQL indexes | Seed lớn, plan theo filter phổ biến | Có số liệu về scan/sort, không chỉ đo một page |

### 12.2. JUnit integration test: insert mới ở đầu không làm lặp trang

Test minh họa dùng AssertJ, Spring Boot Test và một database PostgreSQL test đã được seed. Mỗi thao tác thay đổi dữ liệu phải **commit trước GET tiếp theo**, không được đặt cả kịch bản trong một transaction test rollback bao trùm rồi tuyên bố đã kiểm tra snapshot giữa các HTTP request:

```java
import static org.assertj.core.api.Assertions.assertThat;
import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;

@SpringBootTest
class ProductKeysetIntegrationTest {
    @Autowired ProductPageService pages;
    @Autowired JdbcTemplate jdbc;

    @Test
    void insertAtHeadDoesNotRepeatPreviousRows() {
        // Giả định @BeforeEach/fixture đã reset bảng và seed ID 101–106.
        ProductPage first = pages.list(
            7L, "ACTIVE", 10L, null, null,
            "createdAt_desc", 2, null);
        assertThat(first.items())
            .extracting(ProductDto::id)
            .containsExactly(106L, 105L);

        jdbc.update("""
            INSERT INTO product (
                id, tenant_id, category_id, status,
                price_cents, name, created_at
            ) VALUES (107, 7, 10, 'ACTIVE', 1100,
                      'New head', clock_timestamp())
            """);

        ProductPage second = pages.list(
            7L, "ACTIVE", 10L, null, null,
            "createdAt_desc", 2, first.nextCursor());

        assertThat(second.items())
            .extracting(ProductDto::id)
            .containsExactly(104L, 103L);
        assertThat(second.hasMore()).isFalse();
    }
}
```

Ví dụ giả định test data cô lập, đồng hồ/TTL ổn định, `ProductPageService` và dependency đã triển khai ở phần trước. Trong môi trường CI nên dùng **Testcontainers PostgreSQL hoặc DB test thật** với migration và index, vì H2/DB giả có thể không mô phỏng đúng row comparison, timestamp precision, transaction isolation hay query plan PostgreSQL. Test không kết luận snapshot mạnh; nó chỉ chứng minh không bị lệch offset khi một row mới xuất hiện ở đầu.

### 12.3. Test di chuyển khóa sort: cố ý chứng minh giới hạn

Sau khi reset seed:

```java
ProductPage first = pages.list(
    7L, "ACTIVE", 10L, null, null,
    "price_asc", 2, null);
assertThat(first.items())
    .extracting(ProductDto::id)
    .containsExactly(103L, 104L);

// Hàng 103 đã xem, giờ tăng giá và rơi ra phía sau cursor.
jdbc.update(
    "UPDATE product SET price_cents = 2000 WHERE id = 103");

ProductPage second = pages.list(
    7L, "ACTIVE", 10L, null, null,
    "price_asc", 2, first.nextCursor());
assertThat(second.items())
    .extracting(ProductDto::id)
    .containsExactly(105L, 103L);
```

Đây **không** phải một test phải sửa để “đạt yêu cầu không trùng”. Nó chứng minh rõ chính sách **best-effort** đã chọn. Nếu product API được yêu cầu không trùng/bỏ sót dưới update, cần thay thiết kế sort key hoặc snapshot, sau đó sửa acceptance criteria.

Test thiếu bản ghi tương tự: reset seed; lấy `[103,104]` với price asc, cập nhật product 105 từ 1200 xuống 800, rồi lấy trang sau. Nó có thể trả `[106]` và **không có 105**, vì 105 đã đi về trước cursor.

### 12.4. Test chữ ký và context

Trên một cursor hợp lệ:

1. Đổi một ký tự trong phần payload Base64URL nhưng giữ signature cũ → reject.
2. Đổi signature nhưng giữ payload → reject.
3. Gửi payload JSON đúng hình dạng nhưng signature do attacker tự tạo bằng khóa khác → reject.
4. Gửi token đúng HMAC nhưng user/tenant đã đổi → reject.
5. Gửi cursor đúng tenant nhưng đổi `status`, `categoryId`, `price range` hoặc `sort` → reject.
6. Fake clock đến sau `expiresAtEpochSeconds` → `CURSOR_EXPIRED`.
7. Gửi token có trường `lastCreatedAt` sai format hoặc `lastId <= 0` → reject.

Các test ở mức codec phải bổ sung test **tích hợp** qua controller/security để chắc chắn SQL luôn lọc tenant. Không dùng việc token khó đoán làm bằng chứng authorization. Không trả body khác nhau tiết lộ tenant của một cursor đến từ đâu.

### 12.5. Test hiệu năng và số liệu

Với dataset cỡ hàng chục/hàng trăm nghìn row **giả lập**:

- So sánh `OFFSET 50000` với keyset ở vị trí tương ứng, cùng filter và sort; ghi `EXPLAIN (ANALYZE, BUFFERS)`, execution time, rows scanned, sort và memory.
- Thử filter chỉ `tenant_id`, filter `tenant_id + status`, filter `tenant_id + category_id + status` và giá có range để thấy index nào hữu ích.
- Kiểm tra `limit=1` và `limit=100`, p50/p95/p99, concurrency và query timeout.
- Không giả định keyset luôn nhanh hơn trong mọi trường hợp; index không phù hợp hoặc filter kém chọn lọc có thể khiến PostgreSQL chọn plan khác.
- Không chạy benchmark ghi dữ liệu hoặc gây tải quá mức trên production; dùng dữ liệu thử tương tự phân bố thực tế.

Đừng thêm tổng số trang cố định `totalPages` nếu chưa có nhu cầu và định nghĩa tính nhất quán: một `COUNT(*)` riêng có thể rất tốn chi phí và trả số khác với tập kết quả đang lật trong hệ thống thay đổi liên tục. Trong bài này API chỉ trả `hasMore` và `nextCursor`.

## 13. Client tích hợp: retry, checkpoint và xử lý trùng

Một client đồng bộ cần biết xử lý thành công **cả trang** trước khi lưu cursor làm checkpoint. Mẫu pseudocode:

```text
cursor = loadCheckpointOrNull()
repeat:
    response = GET /products?filters=...&sort=...&limit=100&cursor=cursor
    if status == 429 or retryable 503:
        respect Retry-After, backoff+jitter, total retry/deadline budget
        retry SAME cursor
    if status == 400 CURSOR_EXPIRED:
        restart traversal according to documented recovery policy
    if non-2xx:
        stop and record safe error code / traceId

    for each product in response.items:
        upsert product by stable id (and version if provided)
    commit local upserts and nextCursor checkpoint atomically if possible

    if response.nextCursor == null:
        stop
    else:
        cursor = response.nextCursor
```

Nếu client lưu cursor **trước** khi lưu thành công các item, crash có thể làm bỏ sót trang đã đánh dấu là xử lý xong. Nếu lưu item xong nhưng chưa lưu cursor, crash khiến đọc lại trang; thiết kế upsert theo ID/version giúp lần đọc lặp an toàn. Với dataset có mutation, dedupe phía client chỉ giảm duplicate, **không thay thế snapshot**.

GET list phải có semantics đọc, không tạo side effect kinh doanh. Retrying GET cùng cursor thường hợp lý trong giới hạn, nhưng khi backend liên tục `503` hoặc `429`, client phải tôn trọng backoff/`Retry-After`. Không chạy đồng thời nhiều request trang **liên tiếp theo một cursor** khi chưa có khóa seek của trang trước, trừ khi API thiết kế partitioning riêng.

Về UX, “đổi bộ lọc” hoặc “đổi cách sắp” phải đặt `cursor=null` và bắt đầu từ đầu. Giao diện không nên cố chỉnh sửa cursor opaque hoặc dùng lại sau khi tenant/account thay đổi. Trang cuối có `nextCursor=null` nên dừng; đừng suy đoán số trang từ ID cuối hoặc từ số item đã nhận.

## 14. Vận hành và xử lý lỗi thường gặp

| Triệu chứng | Nguyên nhân thường gặp | Cách xác minh/khắc phục |
| --- | --- | --- |
| Bản ghi trùng giữa hai trang | Chỉ sort theo cột không unique; sort key mutable; dùng OFFSET | Kiểm tra `ORDER BY`, `id` tiebreaker, mutation test |
| Bỏ sót hàng cùng timestamp/price | Dùng `created_at < last` hoặc `price > last` mà thiếu `id` | Sử dụng tuple comparison đủ hai khóa |
| `400 CURSOR_CONTEXT_MISMATCH` dù filter có vẻ giống | Hash raw query string, không normalize null/default/ordering | Normalize theo typed values và schema version |
| Lỗi `400 INVALID_CURSOR` khi triển khai nhiều replica | Replica dùng secret/version khác nhau | Dùng key distribution và rotation nhất quán |
| Lật trang sâu vẫn chậm | Index không phục vụ filter/sort, query dùng function trên sort key | `EXPLAIN (ANALYZE, BUFFERS)`, đo workload thật |
| Cột sort null gây thứ tự khó lường | Không định nghĩa `NULLS FIRST/LAST` | Thiết kế NOT NULL hoặc predicate null riêng |
| Trang sau rỗng dù `hasMore=true` | Row bị xóa/đổi filter, hoặc traversal đã hết theo trạng thái mới | Giải thích best-effort, không lặp vô hạn |
| Sau khi đổi giá có trùng hoặc thiếu | `price_asc` dùng khóa có thể thay đổi | Dedupe chỉ giải quyết trùng; dùng snapshot cho yêu cầu mạnh |
| Cursor hết hạn khi job quá lâu | TTL ngắn hơn thời gian traversal | Bắt đầu lại/checkpoint riêng hoặc job export |
| Rò dữ liệu tenant | Tenant lấy từ user input hoặc query thiếu predicate | Tenant từ identity đã xác minh, test negative/authorization |
| Lỗi `400` quá nhiều sau release | OpenAPI, client query và server parser không đồng bộ | Contract test, thêm migration note, error code ổn định |

Metric nên có: `http.server.request.duration` theo **route template**, status và sort enum; `pagination.cursor_error_total` theo error code; `pagination.page_size` histogram; `db.query.duration` theo loại query đã chuẩn hóa; tỷ lệ `429/503`. Không gắn raw cursor, `tenantId`, token, email, product ID vào metric labels cardinality cao hoặc log phổ thông.

Một runbook xử lý sự cố:

1. Xác định request ở gateway hay service bằng status/error code/trace ID.
2. Kiểm tra filter/sort/limit và version của cursor, **không yêu cầu người dùng gửi token xác thực**.
3. Chạy lại bằng tenant/dữ liệu giả trong môi trường test.
4. Kiểm tra SQL được parameterize và `ORDER BY` khớp seek predicate.
5. Kiểm tra mutation và snapshot expectation thay vì chỉ sửa `LIMIT/OFFSET`.
6. Nếu lỗi sau deploy, so sánh OpenAPI, codec version/key rotation, migration/index và query plan.

## 15. Câu hỏi mở rộng và tiêu chí nghiệm thu

**Câu hỏi 1 — Một bản ghi có cùng timestamp.** Hai sản phẩm cùng `created_at = 10:05:00Z`, ID lần lượt 301 và 302. Nếu `createdAt_desc` và trang đầu kết thúc ở ID 302, predicate trang sau cần là gì để còn lấy 301? Vì sao chỉ dùng `created_at < lastCreatedAt` sẽ sai?

*Gợi ý:* `(created_at,id) < (:lastCreatedAt,:lastId)` khi `ORDER BY created_at DESC,id DESC`.

**Câu hỏi 2 — Phân trang qua cập nhật giá.** Một row đã xem có price thay đổi từ 900 lên 2000, còn một row chưa xem đổi từ 1200 xuống 800. Với `price_asc`, hãy mô tả chính xác trường hợp lặp và trường hợp thiếu. Có thể sửa hoàn toàn bằng `HashSet<id>` không?

**Câu hỏi 3 — Cursor bị sửa.** Attacker giải mã Base64URL, đổi `tenantId` và `lastId` rồi encode lại. Nếu API chỉ decode mà không HMAC, chuyện gì xảy ra? HMAC có đủ thay thế kiểm tra authorization ở SQL không?

**Câu hỏi 4 — Đối soát theo ngày.** Một khách hàng cần danh sách đầy đủ sản phẩm ACTIVE cùng giá ở thời điểm chốt ngày. Vì sao `created_at <= asOf` cộng keyset vẫn chưa đủ khi status/price có thể thay đổi? Hãy đề xuất một snapshot job có TTL, quyền truy cập và cơ chế lưu giá trị bất biến.

**Câu hỏi 5 — Thiết kế index.** Một hệ thống chủ yếu gọi `tenant_id + status`, sort `price_asc`, rất ít dùng `category_id`. Index nào phù hợp hơn cho workload đó? Tại sao index có `category_id` ở giữa không phải lựa chọn tối ưu mặc định? Bạn cần đo gì trước khi thêm index?

### Checklist nghiệm thu

- [ ] Endpoint phân trang dùng seek predicate theo tuple và tiebreaker `id`, không dựa vào `OFFSET`.
- [ ] Có 2 sort đã được cho phép với cùng thứ tự trên SQL, cursor và response.
- [ ] Filter được normalize và bind; không có raw SQL injection qua sort/filter.
- [ ] Có giới hạn `limit`, lấy `limit+1` và tạo cursor từ **hàng cuối được trả**.
- [ ] Cursor được ký, có version/expiry, ràng buộc tenant + filter + sort và không chứa secret/PII.
- [ ] Authorization theo tenant nằm trong mọi query, không chỉ trong payload cursor.
- [ ] Insert mới ở đầu không gây duplicate trong createdAt_desc; timestamp tie được xử lý.
- [ ] Có test chứng minh price/status mutation có thể làm duplicate/skip dù keyset đúng.
- [ ] Hợp đồng công bố rõ best-effort vs snapshot; có đề xuất kiến trúc khi yêu cầu mạnh hơn.
- [ ] Có test 400/401/403, giá trị limit/filter sai và cursor sai context.
- [ ] Có kết quả `EXPLAIN` hoặc benchmark trên PostgreSQL test phù hợp.
- [ ] OpenAPI, ví dụ HTTP, DTO, SQL và test thống nhất.

**Tiêu chí quan trọng nhất:** Một triển khai không được gọi là “keyset ổn định khi dữ liệu thay đổi” chỉ vì mọi test với dữ liệu bất biến đều xanh. Cần **chủ động tạo insert/update/delete giữa các lượt HTTP GET** và diễn giải đúng mức nhất quán mà hệ thống thực sự đảm bảo.

## Tài liệu tham khảo

- [PostgreSQL — Row and Array Comparisons](https://www.postgresql.org/docs/current/functions-comparisons.html)
- [PostgreSQL — Sorting Rows (ORDER BY)](https://www.postgresql.org/docs/current/queries-order.html)
- [PostgreSQL — Multicolumn Indexes](https://www.postgresql.org/docs/current/indexes-multicolumn.html)
- [PostgreSQL — Transaction Isolation](https://www.postgresql.org/docs/current/transaction-iso.html)
- [Spring Framework — JDBC and Named Parameters](https://docs.spring.io/spring-framework/reference/data-access/jdbc/core.html)
- [Spring Framework — Web MVC Annotated Controllers](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller.html)
- [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110)
- [RFC 9457 — Problem Details for HTTP APIs](https://www.rfc-editor.org/rfc/rfc9457)
- [OWASP API Security — Broken Object Level Authorization](https://owasp.org/API-Security/editions/2023/en/0xa1-broken-object-level-authorization/)
