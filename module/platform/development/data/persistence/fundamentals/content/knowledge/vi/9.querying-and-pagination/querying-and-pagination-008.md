# Phân trang theo khóa hoặc con trỏ

## Mục tiêu học tập

Sau bài học này, người học có thể:

1. Phân biệt **phân trang OFFSET/LIMIT**, **phân trang theo khóa (keyset/seek)** và **phân trang bằng con trỏ (cursor)**.
2. Xác định thứ tự sắp xếp **ổn định, có khóa giải quyết giá trị trùng** (*tie-breaker*) để không bỏ qua bản ghi.
3. Viết truy vấn PostgreSQL phân trang tiến/lùi theo khóa, sử dụng chỉ mục và điều kiện seek phù hợp.
4. Dùng Java 17/JDBC lấy `pageSize + 1` hàng để tính `hasNext` và tạo cursor từ hàng cuối thực sự trả về.
5. Thiết kế opaque cursor có HMAC, gắn tenant, bộ lọc, sort, version và expiry; không nhầm cursor với chứng nhận phân quyền.
6. Phân tích INSERT/DELETE/UPDATE, read replica và transaction isolation giữa các lần gọi API.
7. Kiểm thử NULL, timestamp trùng, mixed sorting, cursor lỗi, hiệu năng và các vấn đề multi-tenancy.

Bài thuộc chương **Truy vấn và phân trang** của module **DATA_PERSISTENCE_FUNDAMENTALS**. Phạm vi module bao gồm mô hình dữ liệu, lược đồ, truy vấn/chỉ mục, transaction, isolation, concurrency, persistence boundary cho Java, lỗi kết nối, tiến hóa schema, bảo mật, sao lưu và hiệu năng. Phân trang là một ví dụ liên kết các khái niệm đó: không chỉ chia nhỏ kết quả, mà còn bảo đảm **thứ tự, mức nhìn thấy dữ liệu, quyền truy cập và chi phí truy vấn**.

## 1. OFFSET/LIMIT: dễ hiểu nhưng có giới hạn

Với danh sách đơn hàng một tenant, truy vấn thường thấy:

~~~sql
SELECT order_id, created_at, status
FROM orders
WHERE tenant_id = 42
ORDER BY created_at DESC, order_id DESC
LIMIT 20 OFFSET 0;
~~~

Trang thứ hai:

~~~sql
SELECT order_id, created_at, status
FROM orders
WHERE tenant_id = 42
ORDER BY created_at DESC, order_id DESC
LIMIT 20 OFFSET 20;
~~~

`OFFSET n` yêu cầu bỏ qua `n` hàng đầu của **tập kết quả tại thời điểm query**. Cách này thích hợp bảng nhỏ hoặc UI cần nhảy thẳng đến trang N, nhưng có hai điểm yếu lớn:

- **Chi phí trang sâu:** dù có index, DB thường phải duyệt nhiều mục để bỏ qua các hàng trước offset lớn.
- **Dữ liệu thay đổi giữa request:** INSERT/DELETE trước offset làm vị trí các hàng dịch chuyển, gây trùng hoặc thiếu khi người dùng xem tuần tự.

### 1.1. Trùng hàng sau một INSERT

~~~text
Tại lúc đọc trang 1:
  [10, 9, 8, 7, 6, 5]

Trang 1: LIMIT 3 OFFSET 0
  [10, 9, 8]

Một transaction khác INSERT ID 11:
  [11, 10, 9, 8, 7, 6, 5]

Trang 2: LIMIT 3 OFFSET 3
  [8, 7, 6]

ID 8 xuất hiện hai lần.
~~~

### 1.2. Bỏ sót hàng sau một DELETE

~~~text
Ban đầu:
  [10, 9, 8, 7, 6, 5]

Trang 1: [10, 9, 8]

Xóa ID 10:
  [9, 8, 7, 6, 5]

Trang 2: OFFSET 3 LIMIT 3
  [6, 5]

ID 7 đã bị bỏ qua.
~~~

Không có bug trong SQL; đó là kết quả tất yếu khi dùng vị trí tuyệt đối trên tập dữ liệu luôn thay đổi. Index có thể làm query nhanh hơn nhưng không sửa được ngữ nghĩa offset dịch chuyển.

## 2. Keyset pagination: “đọc tiếp từ khóa cuối cùng”

Thay vì đếm bao nhiêu hàng đã bỏ qua, keyset dùng **khóa sort của hàng cuối trang trước**.

Với thứ tự đơn giản:

~~~sql
SELECT order_id
FROM orders
WHERE tenant_id = 42
ORDER BY order_id DESC
LIMIT 3;
~~~

Nếu trang đầu là `[110,109,108]`, trang sau là:

~~~sql
SELECT order_id
FROM orders
WHERE tenant_id = 42
  AND order_id < 108
ORDER BY order_id DESC
LIMIT 3;
~~~

Kết quả `[107,106,105]`. Một INSERT ID 111 ở đầu danh sách không làm hàng 108 dịch offset nên trang tiếp theo không tự lặp 108.

### 2.1. Keyset khác cursor như thế nào?

- **Keyset/seek pagination** là *kỹ thuật query*: điều kiện dựa trên khóa của hàng ở biên trang.
- **Cursor pagination** là *giao diện API*: client truyền token đại diện trạng thái đọc tiếp.
- Một cursor stateless thường mã hóa **keyset + thông tin query/tenant/sort/expiry**.
- Server-side cursor có thể duy trì trạng thái trên DB/server và có vòng đời/tài nguyên riêng; không đồng nghĩa với opaque token keyset.

Client nên xem cursor là **opaque**: chỉ lưu/gửi lại token, không sửa ID/timestamp bên trong để tự nhảy vị trí.

## 3. Điều kiện bắt buộc: thứ tự toàn phần và ổn định

Query này không xác định đủ thứ tự:

~~~sql
SELECT order_id, created_at
FROM orders
WHERE tenant_id = 42
ORDER BY created_at DESC
LIMIT 2;
~~~

Nếu nhiều đơn có cùng `created_at`, DB được phép trả chúng theo thứ tự phụ bất kỳ. Thêm khóa duy nhất:

~~~sql
ORDER BY created_at DESC, order_id DESC
~~~

Trong phạm vi một tenant, nếu `(tenant_id,order_id)` là primary key thì `(created_at,order_id)` là tuple đủ để phân định thứ tự.

### 3.1. Vì sao chỉ timestamp gây bỏ sót?

| order_id | created_at |
| ---: | --- |
| 105 | 09:30:00 |
| 104 | 09:30:00 |
| 103 | 09:30:00 |
| 102 | 09:29:00 |
| 101 | 09:28:00 |

Trang đầu size 2: `[105,104]`. Cursor chỉ chứa timestamp `09:30:00` và trang sau `WHERE created_at < '09:30:00'` sẽ **bỏ qua 103**. Nếu dùng `<=`, có thể đọc lặp `105/104`.

Phải dùng cả `(09:30:00,104)`:

~~~sql
SELECT order_id, created_at
FROM orders
WHERE tenant_id = 42
  AND (created_at, order_id)
      < (TIMESTAMPTZ '2026-11-22 09:30:00+07', 104)
ORDER BY created_at DESC, order_id DESC
LIMIT 2;
~~~

Khi cả hai sort key theo DESC, tuple nhỏ hơn là những hàng **đứng sau ranh giới**.

### 3.2. Chọn sort key nào?

Ưu tiên sort key:

1. Không NULL hoặc có quy tắc NULL rõ ràng.
2. Ít thay đổi, tốt nhất bất biến trong vòng đời record.
3. Có tie-breaker duy nhất.
4. Có index phục vụ filter + order.
5. Có kiểu dữ liệu/precision/collation ổn định giữa các request.
6. Không tiết lộ thông tin nhạy cảm trong token.

`created_at` bất biến là ứng viên thường gặp; `updated_at` hoặc điểm popularity liên tục thay đổi dễ làm hàng nhảy qua ranh giới dẫn đến trùng/thiếu.

## 4. Schema PostgreSQL và index

Ví dụ SaaS nhiều tenant:

~~~sql
CREATE TABLE tenants (
    tenant_id BIGINT PRIMARY KEY,
    tenant_name TEXT NOT NULL
);

CREATE TABLE orders (
    tenant_id BIGINT NOT NULL REFERENCES tenants(tenant_id),
    order_id BIGINT GENERATED BY DEFAULT AS IDENTITY,
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    status TEXT NOT NULL
        CHECK (status IN ('NEW','PAID','CANCELLED')),
    total_amount NUMERIC(14, 2) NOT NULL
        CHECK (total_amount >= 0),
    PRIMARY KEY (tenant_id, order_id)
);
~~~

Trong ví dụ, `created_at` do DB cấp và **không được cập nhật**. Nếu muốn bảo đảm điều đó trước mọi writer, cần thực thi bằng quyền, trigger hoặc quy tắc DB; chỉ quy ước Java chưa đủ. `clock_timestamp()` không đồng nghĩa timestamp commit nên thứ tự theo nó không chắc bằng thứ tự commit khi transaction đồng thời.

Index cho feed toàn trạng thái:

~~~sql
CREATE INDEX idx_orders_tenant_recent
ON orders (tenant_id, created_at DESC, order_id DESC);
~~~

Index cho truy vấn lọc status thường xuyên:

~~~sql
CREATE INDEX idx_orders_tenant_status_recent
ON orders (tenant_id, status, created_at DESC, order_id DESC);
~~~

Hai index có mục đích khác nhau: khi status đứng trước created_at trong index, query không lọc status có thể không dùng được thứ tự tổng thể theo created_at một cách tối ưu. Đừng tạo index theo mọi tổ hợp mà không đo workload và chi phí ghi.

### 4.1. Query keyset với composite key

Trang đầu:

~~~sql
SELECT order_id, created_at, status, total_amount
FROM orders
WHERE tenant_id = ?
ORDER BY created_at DESC, order_id DESC
LIMIT ?;
~~~

Trang tiếp theo:

~~~sql
SELECT order_id, created_at, status, total_amount
FROM orders
WHERE tenant_id = ?
  AND (created_at, order_id) < (?, ?)
ORDER BY created_at DESC, order_id DESC
LIMIT ?;
~~~

JDBC bind tham số theo đúng thứ tự. Không cố ghép giá trị của client vào SQL literal.

## 5. Công thức so sánh theo hướng sort

Với `ORDER BY created_at DESC, order_id DESC`:

~~~sql
WHERE (created_at, order_id) < (:lastTime, :lastId)
~~~

Tương đương về ý nghĩa:

~~~sql
WHERE created_at < :lastTime
   OR (created_at = :lastTime AND order_id < :lastId)
~~~

Với `ORDER BY created_at ASC, order_id ASC`, điều kiện trang tiếp theo đổi thành `>`.

| ORDER BY | “Trang tiếp theo” |
| --- | --- |
| `a DESC, id DESC` | `(a,id) < (lastA,lastId)` |
| `a ASC, id ASC` | `(a,id) > (lastA,lastId)` |

**Khi thứ tự trộn ASC và DESC**, không dùng tuple `<` hoặc `>` một cách máy móc.

Ví dụ:

~~~sql
ORDER BY priority DESC, created_at ASC, order_id ASC
~~~

Điều kiện seek là:

~~~sql
WHERE priority < :priority
   OR (
       priority = :priority
       AND created_at > :created_at
   )
   OR (
       priority = :priority
       AND created_at = :created_at
       AND order_id > :order_id
   )
~~~

Các `:name` chỉ là ký hiệu minh họa. JDBC PreparedStatement dùng dấu `?` trừ khi framework cung cấp named parameter. Với nhiều sort option, dùng **allowlist** câu SQL, predicate/index và cursor format tương ứng.

## 6. Lấy `pageSize + 1` để xác định còn trang sau

Giả sử page size = 3. Query `LIMIT 4`.

~~~text
DB trả [A,B,C,D]
API items=[A,B,C]
hasNext=true
next cursor = key của C

DB trả [A,B]
API items=[A,B]
hasNext=false
next cursor=null
~~~

**Lỗi thường gặp:** dùng khóa D (hàng dư) làm cursor cho trang sau. Lúc đó lần tiếp theo bắt đầu sau D, khiến D **không được hiển thị lần nào**.

Trường hợp DB trả đúng 3 hàng và query đã lấy `LIMIT 4`: `hasNext=false` nếu không có hàng thứ tư. Nếu chỉ query `LIMIT 3`, không đủ thông tin để phân biệt “còn trang sau” với “đúng 3 hàng cuối”.

### 6.1. Giới hạn kích thước trang

- Từ chối page size nhỏ hơn 1.
- Giới hạn lớn nhất theo workload, ví dụ 100.
- Bảo đảm phép tính `limit+1` không overflow.
- Không cho client dùng limit lớn bất thường để tải hàng triệu hàng qua API tương tác.
- Dùng endpoint/export pipeline riêng cho tải dữ liệu lớn.

## 7. API contract với opaque cursor

Request đầu:

~~~text
GET /api/orders?status=PAID&limit=3
Authorization: Bearer <token>
~~~

Response minh họa:

~~~json
{
  "items": [
    {"orderId": 105, "createdAt": "2026-11-22T02:30:00Z", "status": "PAID"},
    {"orderId": 104, "createdAt": "2026-11-22T02:30:00Z", "status": "PAID"},
    {"orderId": 103, "createdAt": "2026-11-22T02:29:00Z", "status": "PAID"}
  ],
  "hasNext": true,
  "nextCursor": "<opaque-signed-cursor>"
}
~~~

Request sau:

~~~text
GET /api/orders?status=PAID&limit=3&cursor=<opaque-signed-cursor>
~~~

**Tenant phải được xác định từ principal đã xác thực/được ủy quyền**, không từ một trường client tùy ý. Cursor có thể mang tenant nhưng nó không phải chứng nhận quyền. Một user mất quyền tenant phải bị chặn dù còn token cursor cũ.

### 7.1. Trạng thái cần nằm trong cursor

| Trường | Lý do |
| --- | --- |
| Token version | Hỗ trợ đổi schema/cách decode |
| Tenant scope | Ngăn tái dùng cursor chéo tenant |
| Sort ID/direction | Ngăn dùng vị trí của sort khác |
| Filter hoặc fingerprint | Không đổi filter giữa các trang |
| Last sort key và tie-breaker | Tìm đúng ranh giới |
| Expiration | Giới hạn thời gian có hiệu lực |
| Optional anchor/snapshot ID | Hỗ trợ consistency contract đặc biệt |
| Optional key ID | Hỗ trợ xoay HMAC secret |

Base64url chỉ là **encoding**, không bảo mật nội dung. Không đặt password, access token, PII hoặc dữ liệu khách hàng trong cursor.

## 8. Java 17/JDBC: truy vấn keyset theo tenant

Ví dụ repository dùng JDBC thật; nhận tenant ID đã được tầng service kiểm tra quyền. Filter được allowlist, limit bị chặn trước khi SQL chạy.

~~~java
import java.math.BigDecimal;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.time.Instant;
import java.time.OffsetDateTime;
import java.time.ZoneOffset;
import java.util.ArrayList;
import java.util.List;
import javax.sql.DataSource;

public final class OrdersKeysetRepository {
    public record Key(Instant createdAt, long orderId) {
        public Key {
            if (createdAt == null || orderId <= 0) {
                throw new IllegalArgumentException("Invalid seek key");
            }
        }
    }

    public record OrderRow(
            long orderId,
            Instant createdAt,
            String status,
            BigDecimal amount) {}

    public record Page(
            List<OrderRow> items, boolean hasNext, Key nextKey) {}

    private final DataSource source;

    public OrdersKeysetRepository(DataSource source) {
        this.source = source;
    }

    public Page list(long authorizedTenantId,
                     String statusFilter,
                     Key after,
                     int requestedLimit) throws SQLException {

        if (authorizedTenantId <= 0) {
            throw new IllegalArgumentException(
                    "Authorized tenant is required");
        }
        if (!"ALL".equals(statusFilter)
                && !"NEW".equals(statusFilter)
                && !"PAID".equals(statusFilter)
                && !"CANCELLED".equals(statusFilter)) {
            throw new IllegalArgumentException("Invalid status");
        }
        if (requestedLimit < 1 || requestedLimit > 100) {
            throw new IllegalArgumentException(
                    "Page limit out of range");
        }

        StringBuilder sql = new StringBuilder("""
            SELECT order_id, created_at, status, total_amount
            FROM orders
            WHERE tenant_id = ?
            """);

        boolean filtered = !"ALL".equals(statusFilter);
        if (filtered) {
            sql.append(" AND status = ?");
        }
        if (after != null) {
            sql.append(" AND (created_at, order_id) < (?, ?)");
        }
        sql.append("""
            ORDER BY created_at DESC, order_id DESC
            LIMIT ?
            """);

        List<OrderRow> fetched = new ArrayList<>();

        try (Connection c = source.getConnection();
             PreparedStatement p =
                     c.prepareStatement(sql.toString())) {

            int i = 1;
            p.setLong(i++, authorizedTenantId);
            if (filtered) {
                p.setString(i++, statusFilter);
            }
            if (after != null) {
                p.setObject(i++, OffsetDateTime.ofInstant(
                        after.createdAt(), ZoneOffset.UTC));
                p.setLong(i++, after.orderId());
            }
            p.setInt(i, requestedLimit + 1);

            try (ResultSet r = p.executeQuery()) {
                while (r.next()) {
                    OffsetDateTime at = r.getObject(
                            "created_at", OffsetDateTime.class);
                    fetched.add(new OrderRow(
                            r.getLong("order_id"),
                            at.toInstant(),
                            r.getString("status"),
                            r.getBigDecimal("total_amount")));
                }
            }
        }

        boolean hasNext = fetched.size() > requestedLimit;
        List<OrderRow> visible = hasNext
                ? new ArrayList<>(
                        fetched.subList(0, requestedLimit))
                : fetched;

        Key next = null;
        if (hasNext && !visible.isEmpty()) {
            OrderRow last = visible.get(visible.size() - 1);
            next = new Key(last.createdAt(), last.orderId());
        }
        return new Page(List.copyOf(visible), hasNext, next);
    }
}
~~~

### 8.1. Giới hạn của ví dụ Java

- `authorizedTenantId` phải được cấp bởi logic xác thực/ủy quyền; repository không tự xác thực.
- Dùng `OffsetDateTime` từ PostgreSQL `TIMESTAMPTZ` rồi chuyển sang `Instant`; không rút bớt microsecond trong cursor.
- `StringBuilder` chỉ ghép **đoạn SQL cố định**, không ghép chuỗi người dùng vào tên cột.
- Nếu ứng dụng dùng RLS dựa trên transaction-local tenant setting, cần đặt scope trước query trong **cùng transaction/connection** theo policy đã thiết kế.
- `Page.nextKey` là đối tượng Java nội bộ; tầng API cần mã hóa/ký trước khi phát cho client.
- Truy vấn lấy tất cả hàng kết quả của một trang rồi đóng ResultSet/PreparedStatement/Connection; không giữ connection qua nhiều request HTTP.
- Index phù hợp cần được xác minh bằng EXPLAIN thực, không mặc định PostgreSQL luôn chọn index mong muốn.

## 9. Cursor API cần được ký và kiểm tra quyền

Một cursor không nên là một chuỗi ID mà client có thể thay tùy ý. Với token dạng stateless, có thể mã hóa payload rồi ký bằng **HMAC-SHA256**.

Bộ thông tin mẫu:

~~~text
version          = v1
tenant_id        = 42
filter           = PAID
sort             = created_at_desc_order_id_desc
last_created_at  = 2026-11-22T02:29:00Z
last_order_id    = 103
expires_at       = 2026-11-22T03:00:00Z
~~~

Các bước xử lý đúng:

1. API xác thực user, xác định tenant được phép.
2. Validate status, limit và sort theo allowlist.
3. Decode cursor, verify HMAC bằng key từ secret manager.
4. Kiểm tra tenant, filter/sort, thời hạn và version khớp request.
5. Dùng last key đã verify để bind JDBC.
6. Ký next cursor từ khóa cuối **đã trả**.
7. Trả metadata nhất quán.

**HMAC không thay thế authentication hoặc authorization.** Nó chỉ phát hiện chỉnh sửa payload khi kẻ tấn công không biết khóa.

### 9.1. Các rủi ro khi thiếu chữ ký/ngữ cảnh

- Client đổi `last_order_id` để khám phá dữ liệu ngoài phạm vi UI.
- Cursor của tenant A bị gửi vào request B.
- Trang đầu dùng `status=PAID`, trang sau đổi `status=NEW` nhưng vẫn dùng khóa PAID.
- Cursor của kiểu sort khác được dùng lại và cho kết quả sai.
- Cursor rất dài gây tiêu thụ CPU/memory khi giải mã.
- Token cũ được dùng sau khi app thay schema/sort semantics.

Nếu không cần bảo mật vị trí (ví dụ API công khai hoàn toàn), vẫn cần kiểm soát quyền, input và tính nhất quán. **Cursor hợp lệ về chữ ký không tự có nghĩa người gọi hiện còn quyền xem hàng**.

## 10. Java 17: HMAC cursor codec tối giản

Ví dụ này dùng status allowlist, một sort cố định, version và expiry. Payload được Base64URL encode rồi HMAC-SHA256; không chứa secret hoặc PII.

~~~java
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.MessageDigest;
import java.time.Instant;
import java.util.Base64;
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;

public final class CursorCodec {
    private static final String SORT =
            "created_at_desc_order_id_desc";
    private static final Base64.Encoder ENC =
            Base64.getUrlEncoder().withoutPadding();
    private static final Base64.Decoder DEC =
            Base64.getUrlDecoder();

    public record Key(Instant createdAt, long orderId) {}

    private final byte[] hmacKey;

    public CursorCodec(byte[] hmacKey) {
        if (hmacKey == null || hmacKey.length < 32) {
            throw new IllegalArgumentException(
                    "At least 32 random secret bytes required");
        }
        this.hmacKey = hmacKey.clone();
    }

    public String encode(long tenantId,
                         String status,
                         Key last,
                         Instant expiresAt) {
        validateStatus(status);
        if (tenantId <= 0 || last == null
                || last.createdAt() == null
                || last.orderId() <= 0
                || expiresAt == null) {
            throw new IllegalArgumentException("Invalid cursor data");
        }

        String payload = String.join("|",
                "v1",
                Long.toString(tenantId),
                status,
                SORT,
                last.createdAt().toString(),
                Long.toString(last.orderId()),
                Long.toString(expiresAt.getEpochSecond()));

        byte[] data = payload.getBytes(StandardCharsets.UTF_8);
        return ENC.encodeToString(data) + "."
                + ENC.encodeToString(sign(data));
    }

    public Key decode(String token,
                      long authorizedTenant,
                      String requestedStatus,
                      Instant now) {
        validateStatus(requestedStatus);
        if (token == null || token.isBlank()
                || token.length() > 2048 || now == null) {
            throw new IllegalArgumentException("Invalid cursor");
        }

        String[] parts = token.split("\\.", -1);
        if (parts.length != 2) {
            throw new IllegalArgumentException("Invalid cursor");
        }

        final byte[] data;
        final byte[] signature;
        try {
            data = DEC.decode(parts[0]);
            signature = DEC.decode(parts[1]);
        } catch (IllegalArgumentException badEncoding) {
            throw new IllegalArgumentException("Invalid cursor");
        }

        if (!MessageDigest.isEqual(sign(data), signature)) {
            throw new IllegalArgumentException("Invalid cursor");
        }

        String payload = new String(
                data, StandardCharsets.UTF_8);
        String[] fields = payload.split("\\|", -1);
        if (fields.length != 7
                || !"v1".equals(fields[0])
                || !SORT.equals(fields[3])) {
            throw new IllegalArgumentException("Invalid cursor");
        }

        try {
            long tenant = Long.parseLong(fields[1]);
            long orderId = Long.parseLong(fields[5]);
            Instant createdAt = Instant.parse(fields[4]);
            long expiry = Long.parseLong(fields[6]);

            if (tenant != authorizedTenant
                    || !requestedStatus.equals(fields[2])
                    || orderId <= 0
                    || now.getEpochSecond() >= expiry) {
                throw new IllegalArgumentException("Invalid cursor");
            }
            return new Key(createdAt, orderId);
        } catch (NumberFormatException
                 | java.time.format.DateTimeParseException badData) {
            throw new IllegalArgumentException("Invalid cursor");
        }
    }

    private static void validateStatus(String value) {
        if (!"ALL".equals(value)
                && !"NEW".equals(value)
                && !"PAID".equals(value)
                && !"CANCELLED".equals(value)) {
            throw new IllegalArgumentException("Invalid filter");
        }
    }

    private byte[] sign(byte[] payload) {
        try {
            Mac mac = Mac.getInstance("HmacSHA256");
            mac.init(new SecretKeySpec(hmacKey, "HmacSHA256"));
            return mac.doFinal(payload);
        } catch (GeneralSecurityException error) {
            throw new IllegalStateException(
                    "HMAC not available", error);
        }
    }
}
~~~

### 10.1. Giới hạn của mã mẫu

- Đây là **ví dụ giáo dục**; cần thêm key rotation/`keyId` và chính sách tương thích token qua nhiều release.
- **Base64 không mã hóa dữ liệu**; token có thể được giải mã để xem last ID và timestamp.
- Không lưu HMAC key vào source hoặc log; load từ secret manager, phân quyền/rotation theo quy trình.
- `MessageDigest.isEqual` giúp so chữ ký không phụ thuộc trực tiếp vào vị trí byte sai theo cách `Arrays.equals` đơn giản; vẫn cần tránh lộ chi tiết lỗi qua các nhánh không liên quan.
- Token có expiry nhưng không ngăn việc **replay** trong thời hạn. Với cursor đọc, replay thường được phép theo hợp đồng.
- Nếu có nhiều filter, cần canonical hóa và ký **mọi filter có ảnh hưởng query**; đoạn mẫu chỉ gắn status.
- Giới hạn độ dài token trước giải mã để giảm rủi ro từ input lớn.
- Mọi request vẫn phải xác thực principal và kiểm tra quyền tenant độc lập.
- Token không chứa pageSize; thay page size giữa hai request trong ví dụ là hợp lệ nếu API chọn chính sách đó. Nếu muốn khóa pageSize, phải đưa nó vào payload đã ký.
- Timestamp phải được round-trip từ DB không mất precision; không dùng timestamp do client tự gửi làm seek key.

## 11. Kết hợp repository và cursor trong tầng API

Ví dụ giả mã cho một request đã xác thực:

~~~text
function listOrders(principal, request):
    tenant = authorizeTenant(principal, request.workspace)
    status = normalizeAndAllowlist(request.status)
    pageSize = validateLimit(request.limit, 1, 100)

    if request.cursor exists:
        seekKey = codec.decode(
            request.cursor, tenant.id, status, now())
    else:
        seekKey = null

    page = repository.list(
        tenant.id, status, seekKey, pageSize)

    if page.hasNext:
        nextCursor = codec.encode(
            tenant.id, status, page.nextKey,
            now() + permittedCursorTTL)
    else:
        nextCursor = null

    return {
      items: page.items,
      hasNext: page.hasNext,
      nextCursor: nextCursor
    }
~~~

Các bước cần giữ đúng thứ tự:

1. **Xác thực/ủy quyền** tenant trước khi dùng cursor.
2. **Chuẩn hóa bộ lọc** theo một hợp đồng cố định.
3. **Verify chữ ký cursor** trước khi lấy vị trí dùng cho SQL.
4. **Bind** điều kiện tenant, status và keyset qua PreparedStatement.
5. Tạo cursor từ **hàng cuối thực sự gửi cho client**, không từ hàng dư.

### 11.1. Đổi filter giữa các trang

Nếu trang đầu dùng `status=PAID` nhưng trang sau dùng `status=NEW`, cursor chứa khóa của tập PAID không còn là vị trí hợp lệ trong tập NEW. API nên từ chối token không khớp, thay vì tự dùng key đó với một filter mới rồi để client gặp kết quả kỳ lạ.

Với nhiều filter như `createdFrom`, `createdTo`, `searchText`, `region` hay `minAmount`, phải:

- Chuẩn hóa giá trị mặc định.
- Chuẩn hóa timezone/giá trị thời điểm.
- Xác định ngữ nghĩa rỗng, NULL và dấu cách.
- Dùng fingerprint hoặc payload chuẩn tắc khi ký.
- Áp cùng cách chuẩn hóa ở bước query và bước xác minh token.

Nếu bộ lọc không được gắn vào chữ ký, việc đổi nó giữa các trang có thể tạo ra **hành trình không nhất quán** dù chữ ký cursor vẫn hợp lệ.

## 12. Phân trang ngược: quay lại trang phía trước

Giả sử thứ tự chuẩn `ORDER BY created_at DESC, order_id DESC`. Trang hiện tại bắt đầu ở khóa `firstKey`; muốn tìm những hàng **ngay phía trước** nó, cần điều kiện `>` và truy vấn theo thứ tự **ASC để lấy các hàng gần nhất**:

~~~sql
SELECT order_id, created_at, status
FROM orders
WHERE tenant_id = ?
  AND (created_at, order_id) > (?, ?)
ORDER BY created_at ASC, order_id ASC
LIMIT ?;
~~~

Sau khi lấy đủ tối đa `pageSize + 1`, bỏ hàng dư nếu có rồi **đảo danh sách ở Java** để trả về thứ tự chuẩn DESC.

### 12.1. Vì sao không dùng ORDER BY DESC?

~~~text
Thứ tự gốc:
  [12, 11, 10, 9, 8, 7, 6, 5]

Trang hiện tại: [9, 8, 7]
Khóa đầu = 9

Những hàng ngay trước 9: [12, 11, 10]

Query không đúng khi dữ liệu nhiều:
  WHERE id > 9 ORDER BY id DESC LIMIT 3
  có thể chọn các id rất lớn và xa vị trí 9.

Query đúng:
  WHERE id > 9 ORDER BY id ASC LIMIT 3
  -> [10, 11, 12]
  đảo ở Java -> [12, 11, 10]
~~~

Với query ngược, dấu `>` tìm phần trước ranh giới còn `ORDER BY ASC` chọn những hàng **sát ranh giới**, không phải hàng đầu toàn danh sách.

### 12.2. Metadata khi hỗ trợ previous

Một API có thể trả:

~~~json
{
  "items": ["..."],
  "nextCursor": "<cursor-based-on-last-row>",
  "previousCursor": "<cursor-based-on-first-row>"
}
~~~

Token phải chứa `direction=AFTER` hoặc `BEFORE` **đã ký** nếu hai kiểu dùng chung endpoint. `hasPrevious` phải được tính đúng theo truy vấn ngược, không suy từ việc `nextCursor` có hay không.

Keyset phù hợp hành trình “trước/sau”, nhưng không dễ nhảy thẳng đến “trang số 100”. Nếu UI bắt buộc có số trang, cần đánh giá các thiết kế khác thay vì giả vờ cursor là offset.

## 13. NULL và kiểu sắp xếp đặc biệt

Trong PostgreSQL, một tuple comparison với NULL có thể trả kết quả UNKNOWN. Vì vậy:

~~~sql
WHERE (optional_score, order_id) < (?, ?)
~~~

không tự xử lý đúng những hàng có `optional_score IS NULL`.

### 13.1. Ví dụ: score DESC NULLS LAST

Thứ tự:

~~~sql
ORDER BY score DESC NULLS LAST, order_id DESC
~~~

Khi khóa cuối của trang trước có **score khác NULL**, phần tiếp theo gồm những score nhỏ hơn, cùng score nhưng ID nhỏ hơn, rồi đến bucket NULL:

~~~sql
WHERE
    score < :lastScore
    OR (score = :lastScore AND order_id < :lastId)
    OR score IS NULL
ORDER BY score DESC NULLS LAST, order_id DESC;
~~~

Khi khóa cuối **score là NULL**, phần tiếp theo chỉ còn bucket NULL với ID nhỏ hơn:

~~~sql
WHERE score IS NULL
  AND order_id < :lastId
ORDER BY score DESC NULLS LAST, order_id DESC;
~~~

Những query này chỉ minh họa điều kiện seek; một ứng dụng multi-tenant vẫn phải bổ sung `tenant_id = ?` và bind đúng. Với production cần test đầy đủ **chuyển từ bucket có giá trị sang bucket NULL**.

### 13.2. COALESCE có thể nguy hiểm

Không mặc định dùng:

~~~sql
ORDER BY COALESCE(score, 0) DESC
~~~

nếu `score=0` là giá trị thật cần phân biệt với NULL. COALESCE có thể làm mất semantics hoặc tạo tie mới. Nếu dùng sentinel, phải chứng minh sentinel không thể là giá trị thật và index expression tương ứng tồn tại.

### 13.3. Văn bản, collation, Unicode

Khi sort theo tên:

- Collation ảnh hưởng thứ tự các chữ có dấu, hoa/thường và ký tự Unicode.
- Nhiều giá trị có thể so sánh như tương đương tùy collation.
- Tie-breaker duy nhất vẫn cần thiết.
- Cần kiểm tra query và index dùng cùng collation.
- Thay đổi collation/version hoặc sort rules có thể khiến cursor cũ không còn hợp lệ; token version/TTL giúp quản lý.

Không dùng sort key có tính ngẫu nhiên hoặc phụ thuộc locale client mà không cố định ngữ nghĩa trong SQL.

## 14. Tác động của INSERT, DELETE và UPDATE giữa các request

**Keyset không tự tạo snapshot bất biến.** Ở PostgreSQL `READ COMMITTED`, trang 1 và trang 2 thường được truy vấn bằng hai statement/transaction khác nhau và có thể thấy những commit khác nhau.

### 14.1. INSERT mới đứng trước ranh giới

Với sort key bất biến:

~~~text
Trang 1: [10, 9, 8] -> cursor 8

INSERT mới ID 11 vào đầu:
  [11, 10, 9, 8, 7, 6]

Trang 2: WHERE id < 8
  [7, 6, ...]
~~~

Khác OFFSET, cursor không bị dịch bởi INSERT trước ranh giới. Đây là lợi ích lớn cho feed mới→cũ.

### 14.2. INSERT có sort key cũ hơn

Một job backfill có thể tạo hàng sau trang 1 nhưng gán `created_at` cũ hơn cursor. Hàng này có thể xuất hiện ở trang 2 dù **không tồn tại tại thời điểm trang 1**.

Do đó, keyset **không đảm bảo mọi hàng thuộc cùng một snapshot thời gian** nếu có backdated INSERT.

### 14.3. DELETE một hàng chưa được đọc

Hàng bị xóa khỏi DB thì không thể xuất hiện ở trang sau. Với keyset, việc xóa một hàng trước cursor không tự làm điểm bắt đầu dịch đi, nhưng không có bảo đảm rằng **tất cả hàng từng tồn tại khi bắt đầu** sẽ đều được trả trong một feed live.

### 14.4. UPDATE sort key gây bỏ sót/lặp

Sắp xếp theo `updated_at DESC`:

~~~text
Ban đầu:
  [A(10), B(9), C(8), D(7)]

Trang 1:
  [A(10), B(9)] -> cursor=9

UPDATE C: 8 -> 11
Thứ tự mới:
  [C(11), A(10), B(9), D(7)]

Trang 2 WHERE score < 9:
  [D(7)]
C bị bỏ sót.
~~~

Ngược lại, nếu A đã trả rồi được cập nhật khiến khóa nhỏ hơn cursor, A có thể xuất hiện lần nữa. Nếu sản phẩm cần hành trình ổn định, nên chọn sort key bất biến hoặc thiết kế snapshot/watermark rõ ràng.

### 14.5. created_at và thứ tự COMMIT không nhất thiết đồng nhất

Hai transaction có thể gán `created_at` theo thứ tự A rồi B nhưng commit theo thứ tự B rồi A. Một hàng commit muộn có thể có timestamp “cũ hơn” những hàng đang hiển thị.

Vì vậy, ngay cả khi `created_at` bất biến, nó chưa phải một **commit-order snapshot marker**. Đừng quảng bá “không thể bỏ sót bất kỳ transaction nào vừa commit” nếu thứ tự tạo khác thứ tự commit.

## 15. Anchor và snapshot: phân biệt bảo đảm

Một API có thể lưu **anchor key** là vị trí đầu của trang đầu để hạn chế hàng mới đứng phía trước:

~~~text
anchor = (created_at đầu tiên, order_id đầu tiên)
lastKey = (created_at cuối trang trước, order_id cuối trang trước)
~~~

Trong các lần sau:

~~~sql
WHERE tenant_id = ?
  AND (created_at, order_id) <= (?, ?)  -- anchor
  AND (created_at, order_id) <  (?, ?)  -- lastKey
ORDER BY created_at DESC, order_id DESC
LIMIT ?;
~~~

Anchor giúp giới hạn “cửa sổ top” theo sort, nhưng **không tương đương MVCC snapshot**: backdated inserts, update hoặc delete vẫn thay đổi membership.

### 15.1. Khi cần export đúng một tập dữ liệu cố định

Có những lựa chọn mạnh hơn:

1. **Materialized snapshot IDs:** tạo một danh sách ID/phiên export ở thời điểm bắt đầu, sau đó page qua snapshot này.
2. **Temporal/versioned data:** hỗ trợ truy vấn “as of” theo version/transaction sequence có ý nghĩa và cơ chế bảo đảm rõ.
3. **Batch job có watermark, checkpoint và dedup:** chấp nhận xử lý lặp để bảo đảm kết quả nghiệp vụ cuối đúng.
4. **Transaction snapshot duy trì qua một job ngắn được kiểm soát:** phù hợp một số tác vụ batch, nhưng cần quản lý connection và MVCC.

Không giữ một PostgreSQL `REPEATABLE READ` transaction mở qua hàng chục lần cuộn trang HTTP kéo dài hàng giờ nếu chưa đánh giá vacuum/connection pinning, tuổi transaction và khả năng cleanup.

PostgreSQL `pg_export_snapshot` có điều kiện về vòng đời transaction xuất snapshot; **một snapshot identifier không tự là cursor HTTP tồn tại mãi**.

## 16. Isolation, replica và read-your-writes

- **READ COMMITTED:** mỗi statement thấy tập dữ liệu theo snapshot riêng; trang 1 và 2 có thể khác.
- **REPEATABLE READ trong cùng transaction:** snapshot ổn định hơn, nhưng giữ transaction giữa nhiều HTTP requests thường không phù hợp.
- **SERIALIZABLE:** có thể phát sinh `40001`; không mặc định dùng để “sửa” cursor stateless.
- **Read replica:** có thể trễ primary; một trang đọc từ primary, trang sau ở standby chậm có thể không thấy những hàng vừa commit.
- **Failover async:** nếu standby không có commit đã ACK, cursor không tái tạo được lịch sử thiếu; phải xét RPO.

Nếu API cam kết **read-your-writes** cho đơn mới tạo, cần đọc primary hoặc một cơ chế đảm bảo replica bắt kịp trạng thái yêu cầu. Một HMAC cursor chỉ bảo vệ vị trí, không tự đảm bảo độ mới dữ liệu.

### 16.1. Transaction không thay thế authorization

Dù đọc trong một transaction snapshot ổn định, nếu query thiếu `WHERE tenant_id=?` hoặc role có quyền quá rộng, vẫn có nguy cơ truy xuất dữ liệu tenant khác. Isolation và authorization là hai thuộc tính khác nhau.

## 17. Hiệu năng: vì sao keyset thường tốt ở trang sâu?

Với chỉ mục phù hợp `(tenant_id, created_at DESC, order_id DESC)`, DB có thể đi tới ranh giới rồi đọc một lượng nhỏ hàng kế tiếp. `OFFSET` có thể phải đi qua nhiều hàng để bỏ qua chúng.

Tuy vậy, **không khẳng định keyset luôn O(1)**:

- Filter không chọn lọc hoặc không được index có thể quét nhiều hàng.
- JOIN/aggregate/ORDER BY expression có thể yêu cầu sort hoặc thao tác tốn kém.
- Index-only scan phụ thuộc visibility map và cột cần lấy.
- Dữ liệu đã nằm trong cache hay phải đọc từ disk ảnh hưởng latency.
- Số hàng được quét có thể vượt pageSize nếu nhiều hàng bị filter sau index.
- DB planner lựa chọn plan theo thống kê và chi phí, không theo mong muốn trong code.

### 17.1. Benchmark với EXPLAIN

Ví dụ OFFSET sâu:

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT order_id, created_at
FROM orders
WHERE tenant_id = 42
ORDER BY created_at DESC, order_id DESC
LIMIT 20 OFFSET 100000;
~~~

Ví dụ seek:

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT order_id, created_at
FROM orders
WHERE tenant_id = 42
  AND (created_at, order_id)
      < (TIMESTAMPTZ '2026-01-01 00:00:00+00', 50000)
ORDER BY created_at DESC, order_id DESC
LIMIT 20;
~~~

Các giá trị chỉ minh họa. Benchmark công bằng phải chọn keyset boundary **tương ứng với vị trí offset trên cùng dataset/snapshot**. Không so hai mốc khác nhau rồi kết luận chỉ từ latency.

Theo dõi actual rows, loops, index scan, buffers hit/read, heap fetches, sort và execution time. `EXPLAIN ANALYZE` thực thi truy vấn; với SQL ghi phải dùng quy trình an toàn, không chạy trên dữ liệu production tùy tiện.

### 17.2. Count(*) và số trang

Keyset không cung cấp miễn phí tổng số trang. Một query `COUNT(*)` chính xác trên filter phức tạp có thể tốn kém.

Các lựa chọn:

- Không trả totalCount cho infinite scroll.
- Trả approximate count có nhãn “ước lượng”.
- Cache count với stale policy rõ.
- Chạy count ở luồng analytics riêng.
- Dùng OFFSET cho bảng nhỏ khi cần nhảy trang ngẫu nhiên.

Không làm một feed nhanh trở nên chậm chỉ vì mỗi trang lại chạy `COUNT(*)` toàn bảng mà UI không cần.

## 18. Bảo mật đa tenant và giới hạn tài nguyên

Một query keyset đúng về sort nhưng thiếu tenant filter vẫn có thể lộ dữ liệu:

~~~sql
-- Sai trong hệ multi-tenant:
SELECT order_id, created_at
FROM orders
WHERE (created_at, order_id) < (?, ?)
ORDER BY created_at DESC, order_id DESC
LIMIT ?;
~~~

Phiên bản đúng về **scope query**:

~~~sql
SELECT order_id, created_at
FROM orders
WHERE tenant_id = ?
  AND (created_at, order_id) < (?, ?)
ORDER BY created_at DESC, order_id DESC
LIMIT ?;
~~~

Ngoài ra cần:

1. Xác thực người dùng và kiểm tra quyền ở tenant được yêu cầu.
2. Verify token HMAC, filter/sort/version/expiry.
3. Nếu có PostgreSQL RLS, đặt tenant context đúng trong transaction và dùng role runtime không `BYPASSRLS`.
4. Chặn limit rất lớn, cursor quá dài hoặc filter/query cost vượt budget.
5. Cache key bao gồm tenant/filter/cursor hoặc một cache policy tương đương được chứng minh an toàn.
6. Rate-limit/abuse protection đối với API có thể quét dữ liệu lớn.
7. Không log raw cursor, request/token hay SQL chứa PII.
8. Tôn trọng quyền bị thu hồi ngay cả khi user còn cursor chưa hết hạn.

**HMAC không cấp quyền.** Một token không bị sửa vẫn có thể không còn được phép sử dụng khi membership của user thay đổi.

## 19. Khi nào cursor cần bị từ chối?

Một cursor có thể không hợp lệ khi:

- HMAC sai, token bị cắt hoặc encoding lỗi.
- TTL đã hết hoặc token quá dài.
- Tenant, status/filter hoặc sort không khớp request.
- Schema/token version không còn hỗ trợ.
- HMAC key bị xoay và không còn key xác minh tương ứng.
- Principal mất quyền truy cập tenant.
- Dữ liệu chuyển shard/database làm authority/semantics thay đổi.
- Server-side snapshot/batch resource đã hết hạn nếu kiến trúc có dùng.

API nên trả **invalid/expired cursor** rõ ràng và hướng dẫn bắt đầu hành trình mới. Đừng âm thầm quay về trang đầu rồi trả response như trang 2; client có thể nhận nhiều bản ghi trùng mà không nhận ra.

### 19.1. Xoay khóa HMAC

Khi rotation:

- Đặt `keyId` trong token hoặc có cấu hình hỗ trợ hai key trong cửa sổ chuyển tiếp.
- Chỉ chấp nhận key đã được phê duyệt; không suy key từ dữ liệu client tùy ý.
- Không log hay export key.
- Bảo đảm TTL cursor không vượt chính sách lưu key cũ nếu không có hành vi hết hạn được công bố.
- Có kiểm thử nhiều instance đang chạy hai revision khác nhau.

Cursor version trong rollout cũng cần tương thích hoặc có fallback có kiểm soát; không đổi sort từ DESC thành ASC mà vẫn dùng key của token cũ.

## 20. Kiểm thử tích hợp PostgreSQL

Test bằng PostgreSQL cùng họ/version tương thích production sẽ xác nhận được semantics tuple comparison, NULL/collation và chỉ mục; mock repository không chứng minh SQL thực chạy đúng.

### 20.1. Fixture cố tình có nhiều khóa hòa

~~~text
Tenant A, created_at 09:30: id 105, 104, 103
Tenant A, created_at 09:29: id 102
Tenant A, created_at 09:28: id 101

Tenant B, created_at 09:30: id 105, 104
~~~

Tenant A, page size 2:

~~~text
Trang 1: [105,104] ; cursor = (09:30,104)
Trang 2: [103,102] ; cursor = (09:29,102)
Trang 3: [101]     ; hasNext=false
~~~

Nếu fixture không có các `created_at` trùng nhau, test có thể không phát hiện thiếu tie-breaker.

### 20.2. Ma trận kiểm thử bắt buộc

| Trường hợp | Kỳ vọng |
| --- | --- |
| Không cursor, có dữ liệu | Trang đầu đúng thứ tự |
| Tie-breaker trùng timestamp | Không bỏ sót ID cùng timestamp |
| Kết thúc đúng bằng pageSize | `hasNext=false` nhờ lấy N+1 |
| Trang cuối không đủ pageSize | `nextCursor=null` |
| Không có dữ liệu | Items rỗng, cursor null |
| Page size 0/âm/vượt max | Từ chối trước DB |
| Token HMAC bị sửa một byte | Verify thất bại |
| Token hết hạn | Bị từ chối theo contract |
| Cursor tenant A dùng cho B | Bị từ chối |
| Cursor PAID dùng với NEW | Bị từ chối |
| INSERT đứng trước cursor | Không lặp ranh giới như OFFSET |
| INSERT backdated | Theo live semantics có thể xuất hiện |
| DELETE hàng ở trang trước | Không làm cursor dịch |
| UPDATE sort key | Test minh họa có thể lặp/bỏ sót |
| Reverse pagination | Trả hàng gần ranh giới và đảo đúng thứ tự |
| Mixed ASC/DESC | Điều kiện seek OR đúng |
| NULL sort key | Qua được bucket NULLS FIRST/LAST |
| Unicode/collation | Có tie-breaker không mơ hồ |
| Timestamp microseconds | Encode/decode không mất precision |
| Replica lag | Không giả định đọc dữ liệu mới nhất |
| Auth revoked | Token cũ không cho đọc tenant |
| Token/schema version đổi | Có quy tắc lỗi/compatibility rõ |

### 20.3. Assertion trên dataset không thay đổi

Với dữ liệu tĩnh, một bất biến hữu ích:

~~~text
concat(page1.items, page2.items, ..., pageN.items)
  == SELECT tất cả hàng cùng filter và ORDER BY
~~~

Đồng thời kiểm tra:

- Mỗi hàng xuất hiện đúng một lần trong chuỗi trang.
- Thứ tự tuple `(created_at,id)` giảm dần.
- Không trang nào vượt pageSize.
- Cursor trỏ tới hàng cuối **được trả**, không phải hàng dư.
- Mọi hàng thuộc tenant đã được cấp quyền.
- Filter không đổi trong toàn hành trình.

Với dữ liệu biến động, không dùng assertion “không bao giờ lặp/bỏ sót” mà không kèm giả định về immutable key/snapshot. Hãy kiểm thử tường minh những mutation sản phẩm cho phép.

## 21. Quan sát pagination trong production

Các tín hiệu hữu ích:

| Metric | Mục đích |
| --- | --- |
| page_size requested/served | Kiểm soát tải và client misuse |
| cursor_invalid/expired rate | Lỗi token version/filter/rotation |
| API latency p50/p95/p99 theo sort/filter | Phát hiện truy vấn trang sâu chậm |
| DB actual rows/buffers/sort spill | Đánh giá hiệu quả index |
| connection acquisition wait | Giám sát áp lực pool |
| transaction age | Không giữ transaction lâu qua nhiều trang |
| returned row count vs scanned rows | Phát hiện filter/index mismatch |
| tenant authorization deny/RLS failures | An toàn dữ liệu |
| duplicated/gap incident reports | Mutation sort-key hoặc token mismatch |
| config/query/token version | Phát hiện lỗi sau rollout |

Không đặt raw cursor, email, user ID hoặc giá trị truy vấn chứa PII thành label metric. Nếu cần điều tra, lưu correlation ID/fingerprint dưới quyền và retention phù hợp.

### 21.1. Không giữ connection qua HTTP pages

Opaque keyset cursor cho phép **đóng ResultSet và JDBC connection sau từng page**. Người dùng có thể xem trang trong vài phút mà không giữ transaction mở.

Nếu chọn server-side SQL cursor, cần quản lý connection pinning, timeout, cleanup và ảnh hưởng MVCC/vacuum. Đây là một quyết định kiến trúc khác, không tự nên áp dụng chỉ để có “Next”.

## 22. Khi nào OFFSET vẫn hợp lý?

OFFSET có thể phù hợp nếu:

- Tập dữ liệu nhỏ, số trang ít.
- UI cần nhảy tới trang N trực tiếp.
- Dữ liệu tương đối tĩnh hoặc thay đổi giữa trang là chấp nhận được.
- Chi phí query đo bằng EXPLAIN vẫn trong SLO.
- Cần tổng số trang chính xác và hệ thống có ngân sách cho COUNT.

Keyset thường phù hợp khi:

- Tập dữ liệu rất lớn, cuộn tuần tự từ mới tới cũ.
- Muốn giảm chi phí bỏ qua hàng ở trang sâu.
- Có sort key/index phù hợp.
- Muốn giảm trùng/thiếu do offset dịch chuyển khi INSERT/DELETE ở đầu.
- API có thể dùng next/previous cursor thay vì nhảy tùy ý tới trang số 100.

Không tuyên bố “OFFSET luôn sai” hoặc “keyset luôn nhanh”. Lựa chọn theo **UX, consistency contract, workload và index**.

## 23. Những sai lầm thường gặp

**“Chỉ cần ORDER BY created_at DESC.”** Timestamp trùng cần tie-breaker duy nhất.

**“Cursor chỉ cần timestamp.”** Nhiều hàng cùng giây sẽ bị bỏ sót hoặc lặp.

**“Cứ có keyset là có snapshot cố định.”** INSERT/DELETE/UPDATE vẫn thay đổi tập kết quả.

**“Keyset không bao giờ lặp/bỏ sót.”** UPDATE sort key có thể di chuyển hàng qua ranh giới.

**“created_at chắc chắn sắp đúng thứ tự commit.”** Giá trị thời điểm tạo không nhất thiết là commit order.

**“Anchor bằng snapshot PostgreSQL.”** Anchor không chặn backdated inserts hoặc mutation.

**“Tuple < dùng được cả mixed ASC/DESC.”** Phải viết predicate riêng theo từng cột.

**“Có index là query O(1).”** JOIN/filter/sort/heap fetch còn có chi phí.

**“Trả đủ N hàng nghĩa là còn trang tiếp.”** Nên lấy N+1 hoặc có cách kiểm chứng khác.

**“Cursor lấy từ hàng dư thứ N+1.”** Phải dùng hàng cuối thực sự trả.

**“Base64 mã hóa an toàn.”** Base64 chỉ encoding; nội dung đọc được.

**“HMAC ký token nên khỏi cần phân quyền.”** HMAC không bảo đảm user có quyền vào tenant.

**“Cursor PAID dùng được cho filter NEW.”** Bộ lọc đổi phá ngữ nghĩa vị trí.

**“Giữ một JDBC transaction suốt nhiều lần scroll luôn tốt.”** Có rủi ro pool pinning/MVCC/vacuum.

**“Một replica luôn đọc được đơn vừa ghi.”** Replication có thể trễ.

**“COUNT(*) luôn rẻ.”** Count chính xác trên tập lớn có thể nặng.

## 24. Bài tập vận dụng

**Bài 1 — OFFSET shift.** Với `[10,9,8,7,6,5]` và page size 3, minh họa INSERT 11 trước trang 2 và DELETE 10 trong một thử nghiệm khác. Tìm hàng lặp/bỏ sót.

**Bài 2 — timestamp trùng.** Tạo ba hàng cùng `created_at`, page size 2. So sánh cursor chỉ timestamp với cursor tuple `(created_at,order_id)`.

**Bài 3 — ASC/DESC.** Viết điều kiện trang sau cho `ORDER BY created_at ASC, order_id ASC` và DESC; chứng minh bằng dữ liệu.

**Bài 4 — mixed sort.** Với `priority DESC, created_at ASC, id ASC`, viết seek predicate và index ứng viên; tạo ca khi priority và thời gian hòa.

**Bài 5 — limit+1.** Với pageSize 3, DB trả 4 hàng. Xác định items, hasNext, nextCursor đúng.

**Bài 6 — Java/JDBC.** Mở rộng `OrdersKeysetRepository` với query cho status PAID; test first/last page và precision timestamp.

**Bài 7 — HMAC.** Tạo cursor tenant A, sửa signature một byte, đổi filter và tenant; giải thích vì sao các nhánh bị chặn.

**Bài 8 — key rotation.** Cursor TTL 30 phút nhưng HMAC key rotate mỗi 10 phút. Thiết kế `keyId` và cửa sổ chấp nhận key cũ.

**Bài 9 — NULL.** Với `score DESC NULLS LAST, order_id DESC`, viết hai query seek cho boundary score khác NULL và score NULL.

**Bài 10 — previous.** Danh sách DESC `[12,11,10,9,8,7,6,5]`, trang hiện tại `[9,8,7]`. Viết query lấy ba hàng trước và đảo lại.

**Bài 11 — concurrent updates.** Sort theo `updated_at DESC`; tạo hai trường hợp row nhảy trước/sau cursor gây bỏ sót/lặp.

**Bài 12 — snapshot export.** Tập ID phải cố định lúc job bắt đầu. So sánh materialized IDs, snapshot transaction và cursor stateless.

**Bài 13 — benchmark.** Với một triệu đơn, so OFFSET sâu và keyset tương ứng bằng `EXPLAIN (ANALYZE, BUFFERS)`; ghi actual rows, buffers và time.

**Bài 14 — multi-tenant.** Token của A được gửi khi request đang ở tenant B. Xác định cả bước authorization, token verification và DB filter/RLS.

**Bài 15 — filter changes.** Client đổi từ PAID sang NEW giữa hai trang. Định nghĩa response lỗi và cách bắt đầu lại.

**Bài 16 — runbook.** Sau deployment, cursor expired tăng và p99 trang sâu chậm. Liệt kê token versions, schema/config, query plans, key rotation và metrics cần xem.

## 25. Checklist nghiệm thu

- [ ] Sort có thứ tự xác định với unique tie-breaker.
- [ ] Cursor mang đủ mọi sort key.
- [ ] Predicate seek đúng theo chiều ASC/DESC.
- [ ] Có index ứng viên phù hợp tenant/filter/order và đã đo bằng EXPLAIN.
- [ ] `limit + 1` dùng đúng; cursor là hàng cuối đã trả.
- [ ] SQL chỉ ghép các đoạn cấu trúc allowlist, tham số bind bằng PreparedStatement.
- [ ] Page size và token length có giới hạn.
- [ ] Cursor version, tenant, filter, sort và expiry được ký/kiểm tra.
- [ ] Authorization độc lập với cursor HMAC.
- [ ] Fixture có timestamp trùng và hai tenant có cùng ID.
- [ ] Test đủ first/last/empty page và backdated INSERT.
- [ ] Đã xác định semantics UPDATE/DELETE giữa request.
- [ ] NULL/collation/timestamp precision có quy tắc rõ.
- [ ] Previous page có predicate và đảo thứ tự đúng nếu hỗ trợ.
- [ ] Không giữ JDBC connection/transaction giữa nhiều request HTTP.
- [ ] Nếu đọc replica, đã định nghĩa read-your-writes và failover behavior.
- [ ] Telemetry không đưa raw token hoặc dữ liệu nhạy cảm vào metrics.
- [ ] Đã đánh giá khi nào OFFSET vẫn phù hợp.

## Ghi nhớ

**Keyset pagination** dùng ranh giới của **hàng cuối đã trả** trong một thứ tự xác định để lấy các hàng đứng sau nó. So với OFFSET, nó thường có lợi thế ở các trang sâu và giảm trùng/bỏ sót do dịch chuyển offset khi có INSERT/DELETE ở đầu. Muốn đúng cần **sort key đầy đủ, tie-breaker duy nhất, predicate theo chiều sort và index phù hợp**.

**Cursor** là cách API đóng gói trạng thái đọc tiếp. Với Java và PostgreSQL, hãy dùng JDBC PreparedStatement, `limit+1`, token HMAC có version/expiry, ràng buộc tenant/filter/sort, đồng thời **kiểm tra quyền ở mỗi request**. Keyset không tự tạo snapshot cố định: cập nhật sort key, backdated inserts, replica lag và failover vẫn cần consistency contract rõ ràng. Một cơ chế phân trang tốt phải **đọc đúng dữ liệu, có thể đo hiệu năng và không vượt ranh giới bảo mật**.

