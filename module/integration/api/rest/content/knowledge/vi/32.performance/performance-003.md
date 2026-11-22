# Index, keyset pagination và giới hạn truy vấn tập hợp

Một REST API có thể hoạt động rất nhanh khi bảng `orders` chứa vài nghìn bản ghi nhưng chậm rõ rệt khi dữ liệu đạt hàng triệu dòng. Ví dụ, endpoint `GET /orders?page=10000&size=50` có thể buộc cơ sở dữ liệu đi qua hàng trăm nghìn dòng trước khi trả về 50 dòng; một yêu cầu `size=100000` có thể làm tăng sử dụng bộ nhớ, kết nối và độ trễ; truy vấn thiếu điều kiện `tenant_id` còn gây rò rỉ dữ liệu giữa các tenant.

Trong chương **Hiệu năng** của module **INTEGRATION_API_REST**, bài này kết hợp ba thành phần: **chỉ mục (index) phù hợp với truy vấn**, **phân trang keyset/cursor** và **giới hạn truy vấn tập hợp ở phía server**. Các ví dụ dùng HTTP, PostgreSQL và Java/Spring; nguyên tắc cũng áp dụng cho những cơ sở dữ liệu quan hệ và framework tương đương, sau khi điều chỉnh cú pháp và khả năng tối ưu của hệ quản trị.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Đọc một truy vấn list REST API, xác định điều kiện lọc, thứ tự sắp xếp và đề xuất composite index phù hợp.
2. Giải thích chi phí và sai lệch dữ liệu của `OFFSET/LIMIT` khi tập dữ liệu thay đổi hoặc trang rất sâu.
3. Viết keyset query có **thứ tự xác định hoàn toàn**, điều kiện seek đúng chiều và lấy thừa một dòng để tính `hasNext`.
4. Thiết kế cursor opaque, có chữ ký, hạn sử dụng và ràng buộc với tenant, filter, sort, page size.
5. Giới hạn truy vấn tập hợp: kích thước trang, phạm vi thời gian, bộ lọc, fan-out, N+1, count, batch và timeout.
6. Kiểm thử hiệu năng, tính đúng đắn, phân quyền tenant và hành vi khi có cập nhật đồng thời bằng Java/Spring cùng cơ sở dữ liệu thật.

## 2. Bài toán mẫu: API danh sách đơn hàng theo tenant

Giả sử nền tảng nhiều tenant có bảng `orders` với hàng triệu đơn hàng. Người dùng có quyền xem đơn của tenant A và muốn tìm các đơn đã thanh toán, mới nhất trước.

```http
GET /api/tenants/aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa/orders?status=PAID&size=20 HTTP/1.1
Authorization: Bearer <access-token>
Accept: application/json
```

Yêu cầu sản phẩm:

- Chỉ đọc dữ liệu thuộc tenant đã được xác thực và được cấp quyền.
- Sắp xếp theo `created_at DESC, id DESC`; nếu hai đơn cùng thời điểm tạo vẫn có thứ tự xác định.
- Mỗi trang tối đa 100 bản ghi, mặc định 20; không cho lấy không giới hạn.
- Hỗ trợ đi tiếp bằng `nextCursor`; API không cần trả số trang chính xác.
- Phản hồi nhanh và tránh quét sâu khi người dùng kéo danh sách nhiều lần.
- Có chính sách rõ khi đơn được tạo, xóa hoặc đổi trạng thái trong lúc người dùng phân trang.

Schema rút gọn với PostgreSQL:

```sql
CREATE TABLE orders (
    id            uuid PRIMARY KEY,
    tenant_id     uuid NOT NULL,
    customer_id   uuid NOT NULL,
    status        text NOT NULL,
    created_at    timestamptz NOT NULL DEFAULT now(),
    amount        numeric(19, 2) NOT NULL,
    currency      char(3) NOT NULL,
    version       bigint NOT NULL DEFAULT 0,
    CONSTRAINT ck_order_amount CHECK (amount >= 0),
    CONSTRAINT ck_order_status CHECK (
        status IN ('PENDING', 'PAID', 'CANCELLED')
    )
);
```

Trong bài học này, `created_at` và `id` được xem là **không thay đổi sau khi tạo**. Nếu nghiệp vụ cho phép sửa khóa sắp xếp, cần đánh giá lại tính ổn định của pagination. `id` duy nhất giúp phân biệt các bản ghi có cùng `created_at`; UUID có thể so sánh thứ tự trong PostgreSQL nhưng thứ tự đó không phản ánh trình tự phát hành đơn.

Endpoint đầu tiên trả:

```http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: private, no-store

{
  "items": [
    {
      "id": "11111111-1111-4111-8111-111111111111",
      "createdAt": "2026-11-18T08:10:00Z",
      "status": "PAID",
      "amount": 150000,
      "currency": "VND"
    }
  ],
  "pageSize": 20,
  "hasNext": true,
  "nextCursor": "<opaque-signed-cursor>"
}
```

Đây là **minh họa định dạng**, không phải một phản hồi logic hoàn chỉnh: mảng `items` được rút gọn chỉ còn một phần tử và `nextCursor` là placeholder. Trong thực tế, `hasNext` được tính từ số dòng đọc được; không tự trả `true` nếu database chưa chứng minh còn bản ghi. Cursor chỉ là một phần của hợp đồng truy vấn, không thay thế kiểm tra quyền trên từng request.

## 3. Vì sao OFFSET/LIMIT gặp vấn đề ở trang sâu?

Cách phân trang phổ biến:

```sql
SELECT id, created_at, status, amount, currency
FROM orders
WHERE tenant_id = :tenantId
  AND status = 'PAID'
ORDER BY created_at DESC, id DESC
LIMIT 20 OFFSET 200000;
```

Khi yêu cầu trang xa, PostgreSQL có thể phải duyệt qua số lượng lớn mục chỉ mục hoặc hàng đã sắp xếp để bỏ qua `OFFSET` rồi mới lấy `LIMIT`. Với nhiều kế hoạch thực thi, chi phí tăng theo độ sâu của trang. Có index tốt thì không nhất thiết phải sort toàn bảng, nhưng việc đi qua hàng bị bỏ vẫn tiêu tốn I/O hoặc CPU; `OFFSET` lớn không trở nên miễn phí chỉ vì có index.

Công thức gần đúng cho một kế hoạch quét tuần tự các mục trong thứ tự:

```text
rows examined ≈ offset + limit

OFFSET 0,     LIMIT 20  → khoảng 20 vị trí
OFFSET 200000, LIMIT 20 → khoảng 200020 vị trí
```

Đây là trực giác về chi phí, không phải dự báo chính xác số block đọc hay thời gian thực hiện. Planner có thể chọn phương án khác tùy bộ lọc, cache, phân bố dữ liệu và index.

### 3.1. Dữ liệu mới gây trùng hoặc bỏ sót với OFFSET

Giả sử danh sách được sắp mới nhất trước:

```text
Lần gọi thứ nhất, page size = 3:
Trang 1: [A, B, C]
Các dòng còn lại: [D, E, F]

Giữa hai request, một đơn X mới được thêm ở đầu:
Danh sách mới: [X, A, B, C, D, E, F]

Lần gọi thứ hai với OFFSET 3:
Trang 2: [C, D, E]   ← C xuất hiện lần thứ hai
```

Tương tự, việc xóa một dòng phía trước offset có thể làm một dòng chưa đọc bị bỏ qua. Các request REST thường chạy trong các database transaction độc lập, nên `OFFSET` không cung cấp một snapshot xuyên suốt nhiều HTTP requests.

### 3.2. Khi nào OFFSET vẫn hợp lý?

`OFFSET/LIMIT` không phải lúc nào cũng sai. Nó thuận tiện nếu bảng nhỏ, trang nông, dữ liệu ít thay đổi, giao diện thật sự cần chuyển thẳng tới trang N hoặc backend dùng một snapshot cố định. Vấn đề là sử dụng nó cho **trang vô hạn, tập dữ liệu lớn và thường xuyên ghi** mà không đo chi phí.

| Tiêu chí | OFFSET pagination | Keyset pagination |
|---|---|---|
| Truy cập trang N trực tiếp | Thuận tiện | Không trực tiếp; cần cursor từ trang trước hoặc cách định vị khác |
| Trang sâu | Có thể phải bỏ qua lượng lớn bản ghi | Có thể bắt đầu seek tại khóa cuối trang trước |
| Dữ liệu thêm phía trước | Dễ làm trùng/thiếu dòng giữa các trang | Ít chịu ảnh hưởng của insert phía trước cursor |
| Cần sort ổn định | Có | **Bắt buộc** có thứ tự toàn phần |
| Tính tổng số trang | Thường đi kèm count | Không bắt buộc; có thể dùng `hasNext` |
| Filter/sort thay đổi | Tính lại offset | Phải phát cursor mới cho truy vấn mới |
| Thay đổi giá trị khóa sắp xếp | Vẫn có sai lệch | Cũng có thể trùng/bỏ sót, cần thiết kế thêm |

## 4. Thiết kế composite index bám theo truy vấn

Index nên xuất phát từ **query thực tế**, không phải quy tắc "cột nào lọc thì tạo một index riêng".

Query chính:

```sql
SELECT id, created_at, status, amount, currency
FROM orders
WHERE tenant_id = :tenantId
  AND status = 'PAID'
ORDER BY created_at DESC, id DESC
LIMIT 21;
```

Một composite index phù hợp:

```sql
-- PostgreSQL: chạy ngoài transaction block.
CREATE INDEX CONCURRENTLY idx_orders_tenant_status_seek
    ON orders (tenant_id, status, created_at DESC, id DESC);
```

Mục đích từng phần:

| Thành phần index | Tác dụng |
|---|---|
| `tenant_id` | Khoanh đúng tenant trước khi tìm |
| `status` | Thu hẹp tới một trạng thái cụ thể trong tenant |
| `created_at DESC` | Hỗ trợ sắp mới nhất trước |
| `id DESC` | Tie-breaker để sort có thứ tự toàn phần, đồng thời hỗ trợ seek |

Với `tenant_id` và `status` là điều kiện bằng, phần phía sau của index thuận lợi cho việc duyệt theo `created_at DESC, id DESC` mà không phải sort toàn bộ phần dữ liệu phù hợp, nếu planner chọn index scan. **Không có bảo đảm planner luôn chọn index**: ở bảng nhỏ hoặc điều kiện kém chọn lọc, sequential scan có thể rẻ hơn.

`CREATE INDEX CONCURRENTLY` là cú pháp PostgreSQL cho xây chỉ mục với mức chặn ghi nhỏ hơn cách thông thường, nhưng có chi phí tài nguyên, xử lý đặc biệt khi thất bại và **không được chạy trong transaction block**. Không đưa dòng này nguyên xi vào migration framework mặc định wrap toàn bộ migration trong một transaction.

### 4.1. Thứ tự cột không tùy ý

Index:

```sql
CREATE INDEX idx_orders_seek_wrong_shape
    ON orders (created_at DESC, tenant_id, status);
```

không tối ưu tương đương với index bắt đầu bằng `tenant_id, status` cho query `WHERE tenant_id = ? AND status = ?` ở ví dụ. Nó được tổ chức theo thời gian trước, làm cơ sở dữ liệu có thể phải đi qua nhiều tenant khác khi lấy 20 dòng của tenant A. Hiệu quả thực tế tùy phân bố dữ liệu và planner.

Một quy tắc khởi đầu hữu ích: với B-tree và dạng query này, đặt cột so sánh bằng dùng thường xuyên ở đầu, rồi đến cột hỗ trợ `ORDER BY` và khóa phân biệt duy nhất. Quy tắc này cần được xác minh bằng `EXPLAIN` chứ không được dùng máy móc cho mọi `OR`, range, join hay nhiều dạng truy vấn.

### 4.2. Các query khác nhau cần xem lại index

Giả sử API cho phép bỏ `status`:

```sql
SELECT id, created_at, status, amount, currency
FROM orders
WHERE tenant_id = :tenantId
ORDER BY created_at DESC, id DESC
LIMIT 21;
```

Index `(tenant_id, status, created_at DESC, id DESC)` nhóm dữ liệu theo status trước; nó **không đảm bảo** thứ tự tạo toàn cục của tenant khi status không cố định. Có thể cân nhắc thêm:

```sql
CREATE INDEX CONCURRENTLY idx_orders_tenant_seek
    ON orders (tenant_id, created_at DESC, id DESC);
```

Đừng tạo mọi biến thể index theo mọi query parameter. Chỉ thêm index dựa trên lưu lượng thực tế, query plans và ngân sách ghi/đĩa. Mỗi index làm tăng chi phí `INSERT/UPDATE/DELETE`, WAL, chiếm dung lượng và công việc bảo trì. Nếu bảng được ghi rất nhiều, một index phục vụ endpoint ít sử dụng có thể không xứng chi phí.

### 4.3. Partial và covering index

Nếu hầu hết truy vấn quan trọng chỉ xem đơn đã thanh toán, có thể đánh giá partial index:

```sql
CREATE INDEX CONCURRENTLY idx_paid_orders_tenant_seek
    ON orders (tenant_id, created_at DESC, id DESC)
    WHERE status = 'PAID';
```

Index chỉ chứa các dòng phù hợp predicate, có thể nhỏ hơn. Nhưng query planner chỉ dùng nó khi chứng minh được điều kiện truy vấn hàm ý `status = 'PAID'`; câu lệnh prepared có `status = :status` và generic plan có thể không sử dụng partial index vì giá trị parameter chưa được biết khi lập kế hoạch. Nên đo trên đúng SQL/driver/cách bind parameter đang vận hành.

Một lựa chọn khác:

```sql
CREATE INDEX CONCURRENTLY idx_orders_tenant_status_cover
    ON orders (tenant_id, status, created_at DESC, id DESC)
    INCLUDE (amount, currency);
```

PostgreSQL có thể thực hiện `index-only scan` nếu các cột cần trả nằm trong index **và** điều kiện MVCC/visibility map cho phép tránh truy cập heap. `INCLUDE` làm index lớn hơn, có thể gây chi phí ghi cao; không mặc định dùng `INCLUDE` cho mọi cột response. Các field nhạy cảm không nên được copy vào index nếu không có nhu cầu truy vấn rõ ràng.

### 4.4. Tránh làm mất khả năng dùng index

Một số truy vấn khó tối ưu:

```sql
-- Hàm trên cột có thể ngăn sử dụng index thời gian thông thường.
WHERE date(created_at) = :localDate

-- Gồm OR động khiến planner khó dùng một index chọn lọc.
WHERE tenant_id = :tenantId
  AND (:status IS NULL OR status = :status)

-- Search chứa wildcard đầu không được B-tree thường hỗ trợ hiệu quả.
WHERE customer_name LIKE '%an%'
```

Với ngày, chuyển khoảng ngày theo timezone nghiệp vụ thành hai mốc thời gian UTC để so trực tiếp:

```sql
WHERE created_at >= :startInstant
  AND created_at <  :endInstant
```

Đối với `status` tùy chọn, có thể tạo **hai SQL template an toàn với bind parameters**: có status và không status. Không nối thẳng giá trị người dùng vào SQL. Với search toàn văn hoặc substring, xem full-text search/trigram index nếu loại query và tải thực tế phù hợp.

## 5. Keyset pagination: tìm tiếp từ khóa cuối trang

Thay vì nhớ "bỏ qua 200.000 dòng", cursor nhớ **khóa sắp xếp cuối cùng đã trả**. Với `ORDER BY created_at DESC, id DESC`, trang kế tiếp cần các dòng có cặp khóa **nhỏ hơn** khóa cuối của trang trước.

### 5.1. Lần gọi đầu

```sql
SELECT id, created_at, status, amount, currency
FROM orders
WHERE tenant_id = :tenantId
  AND status = :status
ORDER BY created_at DESC, id DESC
LIMIT :limitPlusOne;
```

Giả sử `size=20`, server đặt `limitPlusOne=21`. Nếu đọc được 21 dòng, trả 20 dòng đầu, giữ lại dòng thứ 21 chỉ làm tín hiệu `hasNext=true`. Nếu đọc không quá 20 dòng, `hasNext=false`. Không đưa dòng nhìn trước vào trang trả về; cursor được tạo từ **dòng thứ 20**, không phải dòng thứ 21.

### 5.2. Lần gọi tiếp theo

Giả sử dòng cuối trang trước là:

```json
{
  "id": "30000000-0000-4000-8000-000000000003",
  "createdAt": "2026-11-18T08:00:00Z"
}
```

Query trang sau:

```sql
SELECT id, created_at, status, amount, currency
FROM orders
WHERE tenant_id = :tenantId
  AND status = :status
  AND (created_at, id) < (:lastCreatedAt, :lastId)
ORDER BY created_at DESC, id DESC
LIMIT :limitPlusOne;
```

Trong PostgreSQL, so sánh tuple `(created_at, id) < (...)` áp dụng theo thứ tự từ trái qua phải: trước hết so `created_at`, khi bằng mới so `id`. Đó là cách viết gọn của:

```sql
AND (
    created_at < :lastCreatedAt
    OR (created_at = :lastCreatedAt AND id < :lastId)
)
```

Dấu `<` đúng vì đang sắp **giảm dần ở cả hai cột**. Nếu sắp tăng dần ở cả hai cột, dùng `>`. Nếu direction trộn (ví dụ `priority DESC, created_at ASC`), không dùng tuple comparator đơn giản mà cần xây các nhánh điều kiện đúng chiều theo từng khóa.

### 5.3. Vì sao phải có tie-breaker duy nhất?

Nếu chỉ `ORDER BY created_at DESC`, nhiều đơn có thể cùng timestamp (đặc biệt khi tạo theo batch). Cursor chỉ lưu timestamp sẽ gặp hai lỗi:

- `created_at < :lastCreatedAt` bỏ qua các đơn còn lại có timestamp bằng khóa cuối.
- `created_at <= :lastCreatedAt` có thể trả lại các đơn vừa xuất hiện ở trang trước.

Thêm `id` duy nhất tạo một **total order** ổn định cho những dòng có cùng thời điểm. Với bảng có ID dạng số tăng dần, có thể dùng ID đó; với UUID vẫn dùng được như khóa phụ duy nhất, miễn thứ tự so sánh và cách bind trong database nhất quán.

Một ví dụ minh họa:

```text
Sắp DESC theo (created_at, id), size = 2:

(10:00, id=900)   ← Trang 1, dòng 1
(10:00, id=700)   ← Trang 1, dòng 2, cursor=(10:00, 700)
(10:00, id=500)   ← Trang 2, dòng 1
(09:59, id=990)   ← Trang 2, dòng 2
```

Nếu chỉ dùng `created_at < '10:00'`, dòng `id=500` bị bỏ sót. Nếu sort field có thể `NULL`, row comparison có thể cho kết quả unknown; cần quy định `NULLS FIRST/LAST`, chuẩn hóa thành non-null key hoặc viết predicate riêng. Ví dụ bài này cố ý để `created_at NOT NULL` và `id NOT NULL`.

### 5.4. Đi ngược về trang trước

Keyset thường thuận tiện cho `next`. Nếu cần `previous`, lưu khóa đầu của trang hiện tại; với sort giảm dần:

```sql
-- Lấy những dòng đứng TRƯỚC khóa đầu trang hiện tại.
SELECT id, created_at, status, amount, currency
FROM orders
WHERE tenant_id = :tenantId
  AND status = :status
  AND (created_at, id) > (:firstCreatedAt, :firstId)
ORDER BY created_at ASC, id ASC
LIMIT :limitPlusOne;
```

Đảo ngược thứ tự kết quả trong ứng dụng trước khi trả cho client. Phải tính `hasPrevious` đúng theo số dòng thực tế, và thử dữ liệu ở biên trang 1/trang cuối. Không tùy tiện đổi dấu comparator mà giữ nguyên `ORDER BY DESC`, vì có thể lấy sai nhóm dòng liền kề.

## 6. Hợp đồng HTTP với cursor opaque

Gợi ý giao diện REST:

```http
GET /api/tenants/{tenantId}/orders?status=PAID&size=20
GET /api/tenants/{tenantId}/orders?status=PAID&size=20&cursor=<opaque>
```

Response mẫu:

```json
{
  "items": [
    {
      "id": "11111111-1111-4111-8111-111111111111",
      "createdAt": "2026-11-18T08:10:00Z",
      "status": "PAID",
      "amount": 150000,
      "currency": "VND"
    }
  ],
  "pageSize": 20,
  "hasNext": false,
  "nextCursor": null
}
```

Khi `hasNext=false`, `nextCursor=null` hoặc bỏ trường cursor theo hợp đồng. Một số API dùng `links.next` hoặc HTTP `Link`; quan trọng là client không phải tự xây cursor bằng cách sửa ID. Chỉ dùng cursor được server trả.

### 6.1. Cursor nên chứa gì?

Một payload nội bộ có thể gồm:

```json
{
  "v": 1,
  "tenantId": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
  "status": "PAID",
  "sort": "createdAt:desc,id:desc",
  "size": 20,
  "lastCreatedAt": "2026-11-18T08:00:00Z",
  "lastId": "30000000-0000-4000-8000-000000000003",
  "expiresAt": "2026-11-18T08:30:00Z"
}
```

Các khóa và timestamp trong ví dụ chỉ minh họa. Trong hợp đồng thật, cursor nên được **mã hóa dạng chuỗi opaque** bằng Base64URL của payload và chữ ký HMAC, hoặc dùng ID token để tra cứu state ở server. Không cho client truyền trực tiếp `lastCreatedAt`/`lastId` như nguồn quyền hoặc tin vào trường tenant bên trong token mà chưa xác thực.

Yêu cầu bảo vệ:

1. **Toàn vẹn:** ký payload bằng HMAC-SHA256 hoặc cơ chế tương đương. Trước khi sử dụng phải xác minh chữ ký bằng so sánh constant-time và từ chối token sai.
2. **Ràng buộc truy vấn:** tenant, filter (hoặc fingerprint chuẩn hóa của bộ lọc), sort, phiên bản cursor và page size phải khớp request hiện tại. Khi user đổi filter/sort, bắt đầu truy vấn mới.
3. **Hạn sử dụng và giới hạn kích thước:** tránh token vô thời hạn và payload khổng lồ; xử lý lỗi cú pháp an toàn.
4. **Quyền độc lập:** ở **mỗi** request, server xác minh membership, scope và quyền đọc dữ liệu; cursor hợp lệ **không cấp quyền**.
5. **Bí mật:** ký HMAC **không mã hóa payload**. Không chứa access token, PII hoặc bí mật; nếu cần giữ bí mật hoàn toàn, dùng token ngẫu nhiên có state server-side hoặc mã hóa xác thực.
6. **Vòng đời khóa:** giữ HMAC secret ở secret manager/cấu hình bảo mật, hỗ trợ key ID/rotation nếu cursor còn hạn trong lúc triển khai khóa mới.

Phải chuẩn hóa sort/filter trước khi ký. Ví dụ `status=PAID` và `status=paid` chỉ là cùng filter nếu API công khai chấp nhận dạng chữ thường; khi đó chuẩn hóa trước khi tính fingerprint. Filter động cũng phải có allowlist cột và toán tử, giới hạn độ dài.

Lỗi cursor sai hoặc hết hạn thường là `400 Bad Request`, có thể dùng mã lỗi ứng dụng như `INVALID_CURSOR` / `CURSOR_EXPIRED`; chỉ dùng `410 Gone` nếu hợp đồng API định nghĩa như vậy và client có hướng phục hồi. Không tiết lộ chữ ký, secret hoặc cấu trúc nội bộ trong body lỗi.

### 6.2. Cursor, dữ liệu thay đổi và snapshot

Keyset giải quyết tốt việc **insert mới ở phía trước cursor**: request trang sau không phải bỏ qua một số dòng cố định nên ít bị lặp lại do insert mới nhất. Nhưng keyset **không mặc nhiên tạo một snapshot bất biến giữa các HTTP requests**:

- Nếu xóa bản ghi trước khi đọc trang sau, bản ghi đó đơn giản không xuất hiện.
- Nếu một đơn đang `PAID` chuyển trạng thái, nó có thể rời khỏi filter; số phần tử/trang thay đổi.
- Nếu `created_at` hoặc trường sort bị sửa, một dòng có thể di chuyển qua cursor, tạo trùng hoặc bỏ sót.
- Nếu insert bản ghi mới với timestamp **cũ hơn cursor** (backfill) thì nó có thể xuất hiện ở trang tiếp theo dù được tạo sau request đầu.

Có thể ghi một **mốc trên** `(anchorCreatedAt, anchorId)` từ lần đọc đầu và thêm điều kiện giới hạn key để tránh chèn các bản ghi có khóa *mới hơn* mốc. Tuy nhiên, mốc này **không phải database snapshot**: cập nhật status hoặc insert backdated vẫn làm tập kết quả thay đổi.

Nếu cần xuất báo cáo nhất quán chính xác hàng triệu dòng, cân nhắc tạo **export job bất đồng bộ**, snapshot/materialized result có phiên bản hoặc cơ chế point-in-time phù hợp với database/search engine. Không giữ một transaction/connection DB mở qua nhiều HTTP requests chỉ để giả lập snapshot, vì điều đó làm tăng áp lực MVCC, lock/tài nguyên và gây rủi ro phục hồi.

### 6.3. Timestamp precision và các khóa sắp xếp khác

Giá trị cursor phải giữ **đúng độ chính xác** như trong database. Nếu `timestamptz` lưu microsecond mà API làm tròn xuống millisecond trước khi tạo cursor, dòng có cùng giây nhưng phần microsecond khác có thể bị bỏ sót. Cursor nên serialize timestamp gốc từ JDBC/driver và parse bằng kiểu tương ứng, không dùng chuỗi display đã được làm tròn.

Với sort theo `amount` hoặc `name`, cần chỉ mục và quy tắc collation/null nhất quán; với price có thể thay đổi nhiều, keyset ít ổn định hơn created-at. Với sort tùy chọn, chỉ chấp nhận danh sách cấu hình trước, không ghép `ORDER BY` từ chuỗi do client nhập trực tiếp để tránh SQL injection.

## 7. Cài đặt với Java/Spring JDBC

Ví dụ triển khai client-facing API dùng Spring MVC, `NamedParameterJdbcTemplate` và PostgreSQL. Các class minh họa dùng Java record; import và cấu hình security/JDBC phụ thuộc phiên bản dự án.

### 7.1. DTO và controller có giới hạn kích thước

```java
public enum OrderStatus {
    PENDING, PAID, CANCELLED
}

public record OrderSummary(
        UUID id,
        Instant createdAt,
        OrderStatus status,
        BigDecimal amount,
        String currency) {}

public record OrderSlice(
        List<OrderSummary> items,
        int pageSize,
        boolean hasNext,
        String nextCursor) {}

@RestController
@RequestMapping("/api/tenants/{tenantId}/orders")
@Validated
public class OrderQueryController {
    private final OrderQueryService service;

    public OrderQueryController(OrderQueryService service) {
        this.service = service;
    }

    @GetMapping
    public OrderSlice list(
            @PathVariable UUID tenantId,
            @RequestParam(defaultValue = "PAID") OrderStatus status,
            @RequestParam(defaultValue = "20")
            @Min(1) @Max(100) int size,
            @RequestParam(required = false) String cursor,
            Authentication authentication) {
        return service.list(tenantId, status, size, cursor, authentication);
    }
}
```

`@Min/@Max` cần hỗ trợ method validation (Bean Validation và cấu hình Spring tương ứng). Nếu framework không tự bắt lỗi binding/validation thành `400`, cần cấu hình exception handler. Không dựa riêng vào annotation controller: service cũng phải có giới hạn cuối cùng vì nó có thể được gọi từ service khác, batch hoặc test.

REST API nên document rõ:

| Parameter | Giới hạn | Hành vi |
|---|---|---|
| `size` | Integer 1–100; mặc định 20 | Ngoài khoảng trả `400` theo hợp đồng |
| `status` | Enum đã cho phép | Không nhận chuỗi tùy ý rồi đưa vào SQL |
| `cursor` | Chuỗi ngắn, opaque, có chữ ký | Không hợp lệ/hết hạn/khác filter trả lỗi rõ |
| `tenantId` | UUID trong đường dẫn | Cần xác minh quyền tenant từ danh tính thật |
| `sort` nếu hỗ trợ | Allowlist như `createdAtDesc` | Cursor và index phải khớp kiểu sort |
| `from/to` nếu hỗ trợ | Khoảng hợp lý, giới hạn độ rộng | Tránh quét toàn bộ lịch sử qua mỗi request |

### 7.2. Query service dùng seek và lookahead

```java
@Service
public class OrderQueryService {
    private final NamedParameterJdbcTemplate jdbc;
    private final OrderReadPolicy policy;
    private final OrderCursorCodec cursors;

    public OrderQueryService(NamedParameterJdbcTemplate jdbc,
                             OrderReadPolicy policy,
                             OrderCursorCodec cursors) {
        this.jdbc = jdbc;
        this.policy = policy;
        this.cursors = cursors;
    }

    @Transactional(readOnly = true)
    public OrderSlice list(UUID tenantId,
                           OrderStatus status,
                           int size,
                           String opaqueCursor,
                           Authentication actor) {

        if (size < 1 || size > 100) {
            throw new ResponseStatusException(
                HttpStatus.BAD_REQUEST, "size must be from 1 to 100");
        }

        // Phải đối chiếu JWT/session đã xác thực với membership tenant.
        policy.requireCanReadOrders(actor, tenantId);

        SeekCursor after = opaqueCursor == null
                ? null
                : cursors.decodeAndValidate(
                        opaqueCursor, tenantId, status, size);

        String sql = """
            SELECT id, created_at, status, amount, currency
            FROM orders
            WHERE tenant_id = :tenantId
              AND status = :status
            """;

        MapSqlParameterSource bind = new MapSqlParameterSource()
                .addValue("tenantId", tenantId)
                .addValue("status", status.name())
                .addValue("limit", size + 1);

        if (after != null) {
            sql += """
                  AND (created_at, id) < (:lastCreatedAt, :lastId)
                """;
            bind.addValue("lastCreatedAt",
                          OffsetDateTime.ofInstant(
                              after.lastCreatedAt(), ZoneOffset.UTC));
            bind.addValue("lastId", after.lastId());
        }

        sql += """
            ORDER BY created_at DESC, id DESC
            LIMIT :limit
            """;

        List<OrderSummary> found = jdbc.query(
                sql,
                bind,
                (rs, rowNum) -> new OrderSummary(
                        rs.getObject("id", UUID.class),
                        rs.getObject("created_at",
                                OffsetDateTime.class).toInstant(),
                        OrderStatus.valueOf(rs.getString("status")),
                        rs.getBigDecimal("amount"),
                        rs.getString("currency").trim()));

        boolean hasNext = found.size() > size;
        List<OrderSummary> visible = hasNext
                ? found.subList(0, size)
                : found;

        String nextCursor = null;
        if (hasNext) {
            OrderSummary last = visible.get(visible.size() - 1);
            nextCursor = cursors.encode(
                new SeekCursor(
                    1, tenantId, status, size,
                    last.createdAt(), last.id(),
                    Instant.now().plus(Duration.ofMinutes(30))));
        }

        return new OrderSlice(
                List.copyOf(visible), size, hasNext, nextCursor);
    }
}
```

`OrderReadPolicy` là thành phần nghiệp vụ cần triển khai, không phải class tích hợp sẵn trong Spring. Trong ví dụ, `SeekCursor` được dùng với `version`, tenant, status, size, lastCreatedAt, lastId và expiry; codec ở mục tiếp theo minh họa cấu trúc. Điều kiện an toàn quan trọng gồm:

- `tenant_id` nằm trong **SQL query**, không chỉ trong policy; policy lại phải xác minh membership/role. Không được chỉ lấy tenant từ query param rồi cho đọc tất cả.
- SQL giữ nguyên cấu trúc cố định, các giá trị được bind; không ghép raw `sort` hay `status` từ input.
- Lấy `size + 1` để biết có trang tiếp; không chạy `COUNT(*)` mỗi lần.
- Cursor lấy khóa của dòng cuối **đã trả**, không phải dòng nhìn trước.
- Method `@Transactional(readOnly = true)` kết thúc trong một HTTP request ngắn; nó không cung cấp snapshot xuyên nhiều lần gọi trang và không phải cơ chế phân quyền.
- Controller/service trả DTO công khai, không serialize entity chứa dữ liệu thanh toán/PII ngoài quyền.

Ví dụ cố ý dùng `Instant.now()` để dễ đọc. Hệ thống cần kiểm thử đồng hồ có thể inject `Clock`, thống nhất TTL và xử lý token hết hạn nhất quán. Timestamp đọc bằng `OffsetDateTime` dựa vào PostgreSQL JDBC driver hỗ trợ `TIMESTAMP WITH TIME ZONE`; nếu driver khác, điều chỉnh mapper và giữ precision.

### 7.3. Codec cursor ký bằng HMAC, không tin dữ liệu client

Đây là skeleton Java tập trung vào các bước an toàn của cursor. `secretKey` phải được cấp từ secret manager/cấu hình server, có entropy đủ mạnh (ví dụ ít nhất 256 bit cho HMAC-SHA256); không hard-code trong mã nguồn.

```java
public record SeekCursor(
        int version,
        UUID tenantId,
        OrderStatus status,
        int pageSize,
        Instant lastCreatedAt,
        UUID lastId,
        Instant expiresAt) {}

@Component
public class OrderCursorCodec {
    private final ObjectMapper json;
    private final byte[] secretKey;
    private final Clock clock;

    public OrderCursorCodec(
            ObjectMapper json,
            Clock clock,
            CursorSigningKeyProvider keys) {
        this.json = json; // Cấu hình JavaTimeModule cho Instant.
        this.clock = clock;
        this.secretKey = keys.currentHmacKey();
    }

    public String encode(SeekCursor payload) {
        try {
            byte[] bytes = json.writeValueAsBytes(payload);
            return url64(bytes) + "." + url64(hmac(bytes));
        } catch (JsonProcessingException ex) {
            throw new IllegalStateException("Cannot encode cursor", ex);
        }
    }

    public SeekCursor decodeAndValidate(
            String token,
            UUID expectedTenant,
            OrderStatus expectedStatus,
            int expectedSize) {
        try {
            if (token.length() > 4096) {
                throw invalid();
            }

            String[] parts = token.split("\\.", -1);
            if (parts.length != 2) {
                throw invalid();
            }

            byte[] body = Base64.getUrlDecoder().decode(parts[0]);
            byte[] receivedTag =
                    Base64.getUrlDecoder().decode(parts[1]);

            if (body.length > 2048
                    || !MessageDigest.isEqual(
                        receivedTag, hmac(body))) {
                throw invalid();
            }

            SeekCursor c = json.readValue(body, SeekCursor.class);
            if (c.version() != 1
                    || !expectedTenant.equals(c.tenantId())
                    || c.status() != expectedStatus
                    || c.pageSize() != expectedSize
                    || c.lastId() == null
                    || c.lastCreatedAt() == null
                    || c.expiresAt() == null
                    || !c.expiresAt().isAfter(clock.instant())) {
                throw invalid();
            }

            return c;
        } catch (IllegalArgumentException
                 | JsonProcessingException ex) {
            throw invalid();
        }
    }

    private byte[] hmac(byte[] payload) {
        try {
            Mac mac = Mac.getInstance("HmacSHA256");
            mac.init(new SecretKeySpec(secretKey, "HmacSHA256"));
            return mac.doFinal(payload);
        } catch (GeneralSecurityException ex) {
            throw new IllegalStateException("HMAC unavailable", ex);
        }
    }

    private static String url64(byte[] bytes) {
        return Base64.getUrlEncoder()
                .withoutPadding()
                .encodeToString(bytes);
    }

    private static ResponseStatusException invalid() {
        return new ResponseStatusException(
                HttpStatus.BAD_REQUEST, "Invalid or expired cursor");
    }
}
```

`CursorSigningKeyProvider` là interface ứng dụng tự xây; import các class Java/Spring/Jackson/JCE tương ứng. Với cấu hình thực tế, cần key rotation theo `keyId`, kiểm soát key length và tuân thủ chính sách thời gian token. Ví dụ trên dùng một khóa hiện hành, nên cursor cũ sẽ hết hiệu lực ngay khi thay khóa; có thể chấp nhận nếu hợp đồng quy định như vậy hoặc triển khai hỗ trợ nhiều khóa trong thời gian chuyển tiếp.

HMAC ngăn client sửa `tenantId`, `status` hay khóa seek mà không bị phát hiện. Nhưng **cursor hợp lệ không chứng minh người gọi có quyền**: `policy.requireCanReadOrders` phải chạy ở mọi lần request, và SQL luôn có `WHERE tenant_id = :tenantId`. Nếu người dùng mất quyền giữa hai trang, request kế tiếp phải bị chặn theo chính sách revoke.

Các bộ lọc bổ sung `from`, `to`, `customerId` hoặc sort tùy chọn phải được đưa vào payload hoặc fingerprint đã ký; nếu không, client có thể reuse cursor của query khác và nhận kết quả sai.

## 8. Giới hạn truy vấn tập hợp ở nhiều lớp

Keyset giúp trang sâu ít tốn công hơn, nhưng **không ngăn** client gửi hàng nghìn request hoặc dùng một query cực rộng. Tập hợp dữ liệu của một API phải có giới hạn ở cả HTTP, service, SQL và cơ chế bảo vệ tài nguyên.

### 8.1. Giới hạn `size` ở server

Ví dụ chính sách:

```text
GET /orders?size=20       → mặc định/cho phép
GET /orders?size=100      → mức tối đa
GET /orders?size=1000000  → 400 Bad Request
GET /orders?size=0        → 400 Bad Request
```

Đây là **con số minh họa**, cần chọn theo kích thước DTO, tải, SLA và yêu cầu sản phẩm. Không chỉ chặn ở UI vì client có thể gọi trực tiếp; cũng không chỉ dùng `Pageable` mà quên cấu hình mức tối đa.

Một số API thay vì trả `400` sẽ ép `size=1000000` về 100. Cách nào cũng được nếu hợp đồng quy định rõ, nhưng **không âm thầm thay đổi kích thước trang** khi cursor đã ký với page size cũ.

### 8.2. Giới hạn độ rộng filter và số lượng điều kiện

Endpoint dễ gặp vấn đề:

```http
GET /orders?from=2000-01-01&to=2100-01-01&status=PAID&size=100
```

Dù `size` chỉ 100, cơ sở dữ liệu vẫn có thể quét và lọc lượng dữ liệu lớn để tìm đủ 100 dòng nếu index/filter không phù hợp. Giới hạn hợp lý:

- `from/to` có khoảng thời gian tối đa cho truy vấn tương tác (ví dụ 90 ngày theo nhu cầu).
- `status`, `sort`, field filter theo allowlist; giới hạn số tham số và độ phức tạp của bộ lọc.
- `ids` nhận danh sách phải giới hạn số phần tử và độ dài request, ví dụ tối đa 100 hoặc 500 IDs tùy tác vụ.
- `search` giới hạn độ dài chuỗi, ký tự điều khiển, wildcard, và dùng kỹ thuật index đúng loại.
- Với export nhiều tháng/nhiều triệu dòng, chuyển sang **asynchronous export job** và theo dõi qua `202 Accepted`/status endpoint.

Giới hạn độ rộng ngày chỉ có ý nghĩa nếu nghiệp vụ không cần truy vấn toàn lịch sử. Nên phân biệt quyền và SLA của người dùng thông thường với endpoint quản trị/báo cáo và cho phép truy vấn lớn theo luồng xử lý riêng được quản lý capacity.

### 8.3. Tránh N+1 khi trả collection có quan hệ con

Một lỗi thường gặp trong ORM:

```java
List<Order> orders = orderRepository.findFirst20ByTenantId(...);
for (Order order : orders) {
    // Có thể kích hoạt một SELECT cho từng order.
    var count = order.getItems().size();
}
```

Nếu có 20 order và mỗi lần `getItems()` tải lazy collection, backend có thể chạy 1 query lấy order + 20 query lấy items, thậm chí nhiều hơn với quan hệ lồng nhau. Giới hạn `size` vẫn không sửa được N+1.

Với collection one-to-many, **đừng tùy tiện `JOIN FETCH` collection vào query paginated**: một order có nhiều item làm nhân số row; ORM có thể phải phân trang trong bộ nhớ hoặc xử lý sai tập parent. Một chiến lược rõ ràng:

1. Query **chính** lấy tối đa `size + 1` order IDs theo keyset, kèm các cột header cần thiết.
2. Chỉ với **size order IDs thực sự trả**, query thêm items có giới hạn theo quan hệ; hoặc dùng projection/aggregate đã được đo.
3. Ghép DTO trong ứng dụng, giữ đúng thứ tự order từ query đầu.
4. Nếu mỗi order có rất nhiều items, **phân trang endpoint con** `GET /orders/{id}/items` riêng và giới hạn `expand`.

Ví dụ truy vấn batch:

```sql
SELECT order_id, id, sku, quantity
FROM order_items
WHERE order_id = ANY(:orderIds)
ORDER BY order_id, id
LIMIT :maxRows;
```

Chỉ sử dụng `LIMIT` toàn cục trong ví dụ này nếu hợp đồng chấp nhận lấy một phần items **của cả batch**; nó **không** bảo đảm mỗi order có đủ items. Khi cần giới hạn tối đa N items **cho mỗi order**, dùng window function `ROW_NUMBER() OVER (PARTITION BY order_id ORDER BY id)` với điều kiện `row_number <= :maxPerOrder` hoặc gọi endpoint riêng cho items. Với DTO khai báo là "đầy đủ items", không được âm thầm cắt.

`orderIds` cũng phải được giới hạn và lấy từ trang đã được authorization; nếu client gửi IDs cho batch, phải kiểm tra tenant/quyền trên từng ID trước khi trả dữ liệu.

### 8.4. `COUNT(*)` và tổng số trang không miễn phí

Một API có thể trả:

```json
{
  "items": [],
  "totalElements": 2871934,
  "totalPages": 143597,
  "page": 1
}
```

Để tính `totalElements` chính xác với filter và MVCC, database có thể phải duyệt nhiều dòng/index entries; không phải vì có index mà mọi `COUNT(*)` đều là O(1). Với keyset, ưu tiên `hasNext` từ `size + 1`, không buộc query count trên mọi trang.

Nếu sản phẩm cần total:

- Chạy `COUNT(*)` riêng chỉ khi client yêu cầu hoặc ở trang đầu, đo tải và consistency.
- Có thể sử dụng số đếm cache/materialized hay gần đúng, nhưng phản hồi phải phân biệt **exact** và **approximate**.
- Không trả total/facets tính trên toàn hệ thống cho user chỉ có quyền tenant; cả count và aggregation cũng phải giới hạn quyền.
- Khi dữ liệu thay đổi liên tục, total giữa các request là giá trị tại thời điểm đo, không phải invariant của toàn chuỗi trang.

### 8.5. Giới hạn đồng thời, timeout và ngân sách tài nguyên

Giới hạn response size và page size phải phối hợp với:

| Lớp | Mục tiêu | Ví dụ cơ chế |
|---|---|---|
| HTTP ingress | Không cho body/header/URL quá lớn | Request size cap, validation, rate limiter |
| Controller/service | Chặn query quá rộng/trái hợp đồng | Max page size, date range, allowlist sort/filter |
| Database | Không giữ query quá lâu | Query timeout/statement timeout, index, connection pool |
| Concurrency | Không cho một tenant chiếm mọi worker | Bulkhead, per-tenant concurrency limit, quota |
| Response | Không serialize vô hạn hoặc dữ liệu bí mật | DTO projection, streaming chỉ khi có hợp đồng phù hợp |
| Export | Tách việc lớn khỏi request đồng bộ | Job queue, chunk size, backpressure và status API |

Với PostgreSQL, `statement_timeout` có thể giới hạn thời gian thực thi statement, nhưng cần cấu hình ở session/role hoặc `SET LOCAL` trong transaction được quản lý đúng cách. `@Transactional(timeout = ...)` của Spring có ngữ nghĩa phụ thuộc transaction manager và driver; không được mặc định nó chắc chắn hủy mọi truy vấn/HTTP call ngay lập tức. Nếu query có tính chất nặng, đo thực tế và cấu hình timeouts ở các lớp tương ứng.

Rate limiting API gốc không đủ nếu một request kích hoạt hàng trăm SQL queries do N+1, retry hoặc fan-out. Bảo vệ capacity dựa cả trên số request lẫn **chi phí công việc** mà mỗi request có thể phát sinh.

## 9. Đo và tối ưu bằng EXPLAIN thay vì phỏng đoán

Trước khi thêm index, thu thập **SQL thực sự** do Spring/ORM gửi, tham số điển hình và phân bố tenant (tenant nhỏ/lớn, status phổ biến/hiếm, trang đầu/trang sâu). Trên môi trường staging với dữ liệu đủ đại diện, chạy:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT id, created_at, status, amount, currency
FROM orders
WHERE tenant_id = 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa'
  AND status = 'PAID'
  AND (created_at, id) < (
      '2026-11-18T08:00:00Z'::timestamptz,
      '30000000-0000-4000-8000-000000000003'::uuid
  )
ORDER BY created_at DESC, id DESC
LIMIT 21;
```

`EXPLAIN ANALYZE` **thực thi câu lệnh**; với truy vấn đắt hoặc có side effect, chỉ chạy trên môi trường kiểm thử/thích hợp và dùng transaction rollback nếu phù hợp. Không giả định output của database khác nhau sẽ giống nhau.

Những dấu hiệu cần nhìn:

- Có `Index Scan` / `Index Only Scan` phù hợp hay vẫn `Seq Scan` và `Sort` trên lượng lớn dữ liệu?
- `Index Cond` có thực sự chứa `tenant_id`, `status` và điều kiện seek không, hay bị đẩy thành `Filter` rồi đọc quá nhiều dòng?
- `actual rows`, `Rows Removed by Filter`, `Buffers: shared hit/read`, thời gian thực thi và sự thay đổi theo trang.
- Nếu `Sort` xảy ra, đó có phải một top-N sort nhỏ hay sort lớn phải spill ra disk?
- Có sự khác biệt lớn giữa `estimated rows` và `actual rows`, đặc biệt ở tenant có phân bố dữ liệu rất khác?
- Kế hoạch với prepared statement/generic plan và parameter status thực tế có khác kế hoạch dùng literal không?

Khi tối ưu, kiểm tra một biến mỗi lần: chỉ mục mới, đổi query shape, thay offset bằng seek, giới hạn `size`, bỏ N+1… Sau khi chỉnh, đo lại cả **p50/p95/p99 latency**, database CPU/IO, active connections, query timeout, số SQL/query và ảnh hưởng tới throughput ghi.

### 9.1. Ví dụ mục tiêu SLO

Giả sử yêu cầu thử nghiệm (chỉ để minh họa):

```text
P95 latency của GET /orders trang đầu: < 150 ms
P95 latency của GET /orders trang sâu:  < 200 ms
Số order tối đa trong một response:      100
Tối đa số SQL truy vấn list/header:       1
Số SQL phụ để tải items theo batch:       1
Tỷ lệ 5xx và timeout:                     dưới ngưỡng vận hành định nghĩa
```

SLO không phải con số mặc định của mọi REST API. Cần đo ở lưu lượng/khối lượng dữ liệu gần production, có nhiều tenant và request đồng thời, kiểm tra những trường hợp dữ liệu bất lợi. Cùng một index có thể tốt cho một tenant nhỏ nhưng kém ở tenant quá lớn; tuning phải dựa workload thực.

## 10. Kiểm thử độ đúng của keyset và giới hạn truy vấn

### 10.1. Fixture cố tình tạo khóa trùng

Hãy tạo:

- Tenant A có ít nhất bảy orders `PAID`, trong đó bốn order cùng `created_at` nhưng `id` khác nhau.
- Tenant A có một số order `PENDING` xen giữa các thời điểm.
- Tenant B có orders cùng timestamp hoặc cùng mẫu ID nhưng không thuộc A.
- Một user được quyền xem A, một user chỉ được quyền xem B, một user không có membership.
- Một số order có 0 items, một số có hàng trăm items để bắt lỗi N+1 và dữ liệu quan hệ con quá lớn.

Đọc trang với `size=2` liên tục đến `hasNext=false`; ghép danh sách IDs và so với câu query tham chiếu có cùng filter/sort trên một bộ dữ liệu cố định.

Các bất biến cần assert:

```text
Mỗi trang chứa không quá 2 items.
Các ID không trùng giữa các trang khi fixture không thay đổi.
Tất cả ID đều thuộc tenant A và status PAID.
Danh sách ghép đúng thứ tự (created_at DESC, id DESC).
Không bỏ sót ID do cùng timestamp.
nextCursor chỉ có khi có trang tiếp.
Các trang không tăng chi phí theo offset/depth như OFFSET sâu.
```

Bất biến "không trùng/không thiếu" được kiểm tra trên dữ liệu **không thay đổi**. Khi có concurrent write, kết quả phải được đánh giá theo consistency contract đã công bố chứ không đòi một snapshot mà API không cung cấp.

### 10.2. Ma trận test âm tính và bảo mật

| Kịch bản | Kỳ vọng |
|---|---|
| `size=0`, `size=-1`, `size=100000` | `400` theo chính sách max size |
| `status` không thuộc enum | `400`, không đưa chuỗi lạ vào SQL |
| Cursor bị sửa một ký tự | `400 INVALID_CURSOR`, không trả dữ liệu |
| Cursor hết hạn hoặc sai version | Lỗi rõ theo hợp đồng; không truy vấn như trang đầu |
| Dùng cursor tenant A trên URL tenant B | `400` hoặc `403/404` theo thứ tự kiểm tra quyền; không lộ dữ liệu A |
| Dùng cursor của `PAID` với `status=PENDING` | `400`, buộc tạo cursor mới |
| Dùng cursor `size=20` với `size=100` | `400` nếu page size đã ký |
| User B gọi URL tenant A dù có cursor đúng | Bị chặn authorization; cursor không cấp quyền |
| Dùng cursor cũ sau khi membership bị revoke | Request mới bị chặn theo chính sách revoke |
| Hai dòng cùng `created_at` nằm qua ranh giới trang | Không trùng và không bỏ sót trên dataset cố định |
| Trang cuối và dataset rỗng | `hasNext=false`, `nextCursor=null`, không lỗi |
| Query quá rộng hoặc quá nhiều IDs | Bị từ chối/đẩy sang export flow đúng hợp đồng |
| Dữ liệu có quan hệ con lớn | Không xuất vô hạn, không tạo N+1, không cắt sai âm thầm |

Các test này nên chạy trên PostgreSQL thật hoặc Testcontainers PostgreSQL khi cần xác minh tuple comparisons, index, SQL/locking và precision của `timestamptz`. Test với H2 có thể bỏ qua khác biệt về comparator, planner và driver.

### 10.3. Spring MockMvc integration test minh họa

Đoạn test sau giả định fixture, chính sách tenant và Spring Security được cấu hình. `jwt()` ở đây mô phỏng principal đã xác thực để test authorization; nó **không** kiểm tra chữ ký, issuer, audience hay expiry của JWT thật. Những phần đó cần test riêng với JWT decoder/issuer trong môi trường phù hợp.

```java
@SpringBootTest
@AutoConfigureMockMvc
class OrderListPaginationIT {
    private static final String TENANT_A =
        "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa";

    @Autowired MockMvc mvc;
    @Autowired ObjectMapper json;

    private RequestPostProcessor alice() {
        return jwt()
            .jwt(token -> token.subject("alice"))
            .authorities(new SimpleGrantedAuthority(
                "SCOPE_orders:read"));
    }

    @Test
    void paginatesUsingOpaqueCursorWithoutRepeatingRows()
            throws Exception {
        String firstJson = mvc.perform(
                get("/api/tenants/{tenantId}/orders", TENANT_A)
                    .param("status", "PAID")
                    .param("size", "2")
                    .with(alice()))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.items.length()").value(2))
            .andExpect(jsonPath("$.hasNext").value(true))
            .andReturn().getResponse().getContentAsString();

        JsonNode first = json.readTree(firstJson);
        String cursor = first.path("nextCursor").asText();
        String id1 = first.path("items").get(0).path("id").asText();
        String id2 = first.path("items").get(1).path("id").asText();

        String secondJson = mvc.perform(
                get("/api/tenants/{tenantId}/orders", TENANT_A)
                    .param("status", "PAID")
                    .param("size", "2")
                    .param("cursor", cursor)
                    .with(alice()))
            .andExpect(status().isOk())
            .andReturn().getResponse().getContentAsString();

        JsonNode second = json.readTree(secondJson).path("items");
        for (JsonNode item : second) {
            assertThat(item.path("id").asText())
                .isNotIn(id1, id2);
        }
    }

    @Test
    void rejectsOutOfRangeSize() throws Exception {
        mvc.perform(get("/api/tenants/{tenantId}/orders", TENANT_A)
                .param("size", "10000")
                .with(alice()))
            .andExpect(status().isBadRequest());
    }
}
```

Imports thông thường từ JUnit 5, Spring Test, Spring Security Test, Jackson và AssertJ được IDE thêm. Đây là **ví dụ tích hợp cần fixture xác định**: nếu fixture không có ít nhất ba order PAID, `hasNext=true` ở test đầu là kỳ vọng không hợp lệ. Để kiểm thử toàn bộ danh sách, tiếp tục lặp đến trang cuối và so sánh IDs với query tham chiếu trên dataset không đổi; test minh họa mới kiểm tra hai trang đầu.

Test với `@Transactional` bọc toàn bộ test có thể khiến fixture chưa commit không nhìn thấy từ thread/connection khác; cần tạo dữ liệu rõ ràng và tránh giả định behavior của transaction test là giống production. Test performance cần chạy warmup, dữ liệu đủ lớn và môi trường có độ ổn định hợp lý; không dùng thời gian từ vài hàng trong unit test làm kết luận về index.

### 10.4. Kiểm thử concurrent inserts và updates

Hai kịch bản nên phân biệt:

**Insert mới ở đầu danh sách:**

```text
1. GET trang đầu, ghi lại nextCursor.
2. Insert một order mới với created_at mới hơn tất cả.
3. GET trang tiếp bằng cursor cũ.
4. Xác nhận không lặp bản ghi trang đầu chỉ vì insert ở đầu.
5. Chấp nhận order mới không xuất hiện trong chuỗi trang hiện tại.
```

**Update/xóa một order phía sau cursor:**

```text
1. GET trang đầu.
2. Đổi status của một order chưa đọc từ PAID sang CANCELLED.
3. GET trang tiếp.
4. Đánh giá theo chính sách "tập kết quả hiện tại" hoặc snapshot đã công bố.
5. Không yêu cầu trả order đã rời filter nếu API không bảo đảm snapshot.
```

Nếu muốn bản xuất hoàn chỉnh đúng một thời điểm, xây flow export/snapshot riêng, có kiểm thử data version và trạng thái job; không sửa keyset query bằng một loạt transaction dài sống qua HTTP.

## 11. Lỗi thường gặp khi tối ưu list API

| Sai lầm | Hậu quả | Cách khắc phục |
|---|---|---|
| Chỉ tạo index trên `created_at` | Trộn dữ liệu nhiều tenant/status trước khi tìm đủ dòng | Đo và tạo composite index theo `WHERE` + `ORDER BY` |
| Tạo index riêng cho mọi cột filter | Planner không nhất thiết ghép thành plan tốt; tăng chi phí ghi | Ưu tiên index theo workload query |
| `OFFSET` lớn và không đặt giới hạn trang | Request chậm do bỏ qua nhiều dòng | Keyset cho luồng next/scroll; giới hạn size |
| `ORDER BY created_at` không có tie-breaker | Các dòng cùng timestamp trùng/bỏ sót giữa trang | Thêm khóa unique như `id` |
| Sắp DESC nhưng dùng `>` cho next | Nhận sai phía của cursor | Với mọi cột DESC, next dùng `<` |
| Cursor chỉ mã hóa Base64 không ký | Client có thể sửa khóa/filter/tenant | HMAC hoặc token stateful, kiểm tra quyền lại |
| Tin cursor đã ký là quyền đọc | User hết quyền vẫn có thể truy cập tenant | Policy kiểm tra mỗi request + tenant predicate trong SQL |
| Dùng cursor của filter khác | Không liên tục, bỏ sót hoặc trả sai dữ liệu | Ràng buộc filter/sort/size và version với cursor |
| Dùng timestamp đã làm tròn | Mất record ở ranh giới precision | Giữ precision DB trong cursor |
| Dùng `JOIN FETCH` collection kèm `LIMIT` tùy tiện | Nhân row, N+1 hoặc pagination trong memory | Keyset parent IDs rồi batch child/projection |
| Luôn trả `totalElements` chính xác | Count tốn công với filter lớn | `size+1` để tính `hasNext`; count tùy nhu cầu |
| Tăng `size` để bớt HTTP calls | Mỗi response rất lớn, tăng heap/p95 latency | Tìm mức cân bằng theo SLO; giới hạn max |
| Đưa ID user, tenant, cursor vào metric label | Cardinality nổ, dashboard tốn bộ nhớ | Dùng route template/status, IDs ở trace/log có kiểm soát |
| Tối ưu chỉ theo query planner trên bảng nhỏ | Không thấy tác động I/O, skew tenant và writes | Staging dữ liệu đại diện, đo p95 và throughput |
| Ngầm coi keyset là snapshot | Hiểu sai kết quả khi status/sort thay đổi | Nêu rõ consistency contract hoặc dùng snapshot/export |

## 12. Bài tập thực hành

### Bài tập 1 — Chọn index cho ba truy vấn

Một hệ thống có ba query:

```sql
-- Q1: Danh sách PAID của tenant theo thời gian tạo mới nhất
WHERE tenant_id = :tenant AND status = 'PAID'
ORDER BY created_at DESC, id DESC

-- Q2: Mọi đơn của tenant theo thời gian tạo mới nhất
WHERE tenant_id = :tenant
ORDER BY created_at DESC, id DESC

-- Q3: Danh sách đơn theo customer trong tenant
WHERE tenant_id = :tenant AND customer_id = :customer
ORDER BY created_at DESC, id DESC
```

Hãy đề xuất composite indexes, giải thích thứ tự các cột, xác định index nào dùng lại được và liệu cả ba đều cần index riêng hay không. Kiểm tra bằng `EXPLAIN (ANALYZE, BUFFERS)` trên dữ liệu đại diện và ghi chi phí ghi thêm do index.

*Gợi ý:* Q1 có thể cần `(tenant_id,status,created_at DESC,id DESC)`; Q2 cần xem `(tenant_id,created_at DESC,id DESC)`; Q3 có dạng khác với `customer_id`. Đừng tạo index chỉ vì tên query, hãy đo tần suất sử dụng và planner thực tế.

### Bài tập 2 — Viết keyset cho chiều DESC và ASC

Cho `created_at` và `id` là non-null, hai cột sắp DESC. Viết SQL trang đầu, trang tiếp và trang trước với `size=25`. Giải thích vì sao `LIMIT 26` để tính `hasNext`, vì sao cursor lấy từ dòng cuối đã trả và vì sao phải đảo kết quả của query "previous".

Sau đó đổi sort thành `priority DESC, created_at ASC, id ASC`. Viết đầy đủ biểu thức OR để tìm dòng kế tiếp; kiểm tra các trường hợp hai dòng bằng priority và timestamp.

*Gợi ý biểu thức cho sort trộn:* bước đầu `priority < :lastPriority`; khi priority bằng, `created_at > :lastCreatedAt`; khi tiếp tục bằng, `id > :lastId`. Chú ý null và collation theo dữ liệu thực tế.

### Bài tập 3 — Kiểm thử cursor bị sửa và tenant khác

Tạo hai tenant A/B, user A/B, dữ liệu có cùng timestamp. Gửi trang đầu của A, sửa một ký tự trong cursor, sau đó dùng cursor hợp lệ của A ở URL B. Viết test HTTP status và assert không có bản ghi của A xuất hiện trong kết quả B. Thu hồi membership của user A trước trang tiếp và kiểm thử API từ chối request mới.

### Bài tập 4 — Khắc phục N+1 và collection quá lớn

Một endpoint `GET /orders?expand=items` đang tải 50 orders, mỗi order 200 items và chạy 51 SQL queries. Hãy thiết kế hai bước: lấy 50 parent theo keyset, rồi batch items có giới hạn và hợp đồng expansion rõ. Đề xuất cách xử lý nếu product không cần đủ 200 items mỗi order, có thể thay bằng `itemCount` hoặc URI endpoint con.

### Bài tập 5 — Đo latency khi tăng độ sâu

Chuẩn bị ít nhất vài trăm nghìn dòng với hai tenant kích thước khác nhau, chạy `OFFSET 0`, `OFFSET 100000` và keyset sau cursor tương ứng. Ghi actual rows, buffer reads, execution time và p95 request latency dưới tải đồng thời. Giải thích sự khác biệt; đánh giá ảnh hưởng của index mới đến insert throughput và WAL. Kết quả cần dựa trên số đo, không tự giả định keyset luôn nhanh ở mọi tập dữ liệu.

## 13. Checklist trước khi triển khai production

- [ ] Có truy vấn list thực tế, bộ lọc, thứ tự sort và index được kiểm chứng bằng `EXPLAIN` trên dữ liệu đại diện.
- [ ] Mọi collection query có điều kiện tenant/authorization trước khi truy cập dữ liệu.
- [ ] Phân trang có thứ tự xác định hoàn toàn; tie-breaker unique, non-null và precision chính xác.
- [ ] Query trang sau dùng comparator đúng hướng, index hỗ trợ seek và `size+1` để tính `hasNext`.
- [ ] Cursor có xác thực toàn vẹn, version, expiry, filter/sort/size/tenant binding; không chứa bí mật.
- [ ] Quyền được kiểm tra lại ở từng trang; cursor không được dùng như bearer credential.
- [ ] Có max page size, giới hạn filter/date range/batch IDs, allowlist sort và response DTO.
- [ ] Có chiến lược cho list quan hệ con, tránh N+1 và phân trang sai khi join collection.
- [ ] `COUNT(*)` là lựa chọn có chủ đích, không chạy mặc định cho mọi next page nếu không cần.
- [ ] Hợp đồng nêu rõ tính nhất quán khi insert/update/delete giữa các request.
- [ ] Query timeouts, concurrency limit, rate limiting và flow export riêng bảo vệ tài nguyên.
- [ ] Test same-timestamp, trang đầu/trang cuối, cursor sai/hết hạn, cross-tenant, revoke và concurrent writes.
- [ ] Theo dõi p95/p99 latency, DB I/O, pool pressure, SQL count/request và write amplification do index.

**Nguyên tắc cần nhớ:** Một API danh sách hiệu quả không hình thành chỉ bằng cách thêm `LIMIT`. Phải **lọc đúng dữ liệu theo quyền**, **sắp xếp ổn định**, **seek trên composite index phù hợp**, **giới hạn công việc do mỗi request tạo ra** và **đo plan thực tế**. Keyset giúp tránh chi phí và sai lệch của deep offset trong nhiều tình huống, nhưng không thay thế kiểm tra quyền, quản lý capacity hay một hợp đồng snapshot rõ ràng khi nghiệp vụ cần dữ liệu nhất quán tuyệt đối.
