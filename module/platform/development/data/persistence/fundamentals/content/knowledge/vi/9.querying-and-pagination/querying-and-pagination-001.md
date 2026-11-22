# Xây dựng truy vấn từ nhu cầu đọc của ứng dụng

Một endpoint Java nhận yêu cầu “hiển thị 20 đơn hàng đã thanh toán gần nhất” không chỉ cần một câu `SELECT` chạy được. Nó còn phải trả đúng đơn thuộc người dùng có quyền xem, chỉ lấy những trường giao diện sử dụng, sắp xếp ổn định, phân trang không bỏ sót bản ghi và đáp ứng độ trễ phù hợp khi dữ liệu lớn lên. Nếu bắt đầu bằng cách chọn bảng rồi viết `SELECT *`, ta rất dễ đưa những quyết định về phân quyền, hiệu năng và tính nhất quán vào ứng dụng một cách ngẫu nhiên.

Trong chương **Truy vấn và phân trang** của **DATA_PERSISTENCE_FUNDAMENTALS**, bài này hướng dẫn quá trình đi **từ nhu cầu đọc của ứng dụng đến hợp đồng API, hình dạng truy vấn SQL, chỉ mục và triển khai Java/JDBC**. Nội dung liên hệ với các kiến thức nền tảng về mô hình dữ liệu, giao dịch, độ cô lập, quản lý kết nối, bảo mật và tối ưu hiệu năng trong lớp persistence.

**Nguyên tắc chính:** truy vấn tốt được thiết kế ngược từ thông tin mà người dùng cần xem, với ngữ nghĩa và ranh giới truy cập rõ ràng; sau đó mới chọn SQL và đo cách cơ sở dữ liệu thực thi.

## 1. Biến yêu cầu đọc thành hợp đồng có thể kiểm thử

Giả sử một ứng dụng quản lý đơn hàng nhiều tenant có ba nhu cầu:

| Nhu cầu | Người gọi cần thấy gì? | Điều kiện truy cập | Hình dạng kết quả |
| --- | --- | --- | --- |
| Danh sách đơn theo trạng thái | Mã đơn, trạng thái, thời gian tạo, tổng tiền | Chỉ đơn thuộc tenant đang được xác thực | Trang có giới hạn, sắp xếp mới nhất trước |
| Chi tiết một đơn | Thông tin đơn và các dòng sản phẩm | Tenant được phép xem đơn | Một đối tượng cha cùng danh sách dòng con |
| Báo cáo doanh thu | Tổng tiền và số đơn đã thanh toán theo ngày | Tenant/phạm vi thời gian được phép | Các hàng tổng hợp theo ngày, không phải toàn bộ đơn |

Trước khi viết SQL, cần trả lời ít nhất những câu hỏi sau:

1. **Đối tượng đọc:** danh sách, một bản ghi chi tiết, tổng hợp, tìm kiếm hay export hàng loạt?
2. **Ai được đọc:** tenant, chủ sở hữu đơn, vai trò, phạm vi dự án nào? ID tenant lấy từ nơi nào đáng tin?
3. **Trường cần thiết:** màn hình có cần email, địa chỉ giao hàng, dữ liệu thanh toán hay chỉ vài trường tóm tắt?
4. **Điều kiện lọc:** trạng thái bắt buộc hay tùy chọn, khoảng ngày, từ khóa, giới hạn số tiền, chỉ các đơn chưa xóa?
5. **Thứ tự:** mới nhất theo `created_at` hay cập nhật gần nhất theo `updated_at`? Hai bản ghi bằng thời gian được phân biệt thế nào?
6. **Khối lượng:** một request tối đa bao nhiêu hàng; có cần đi tới trang thứ 10.000 hoặc export không?
7. **Mức mới của dữ liệu:** đọc ngay sau ghi có cần thấy kết quả của chính mình không; có được phép đọc replica/cache có độ trễ?
8. **Ngữ nghĩa khi dữ liệu đổi:** khi có đơn mới giữa hai lần phân trang, API cần snapshot cố định hay chấp nhận danh sách đang thay đổi?
9. **Mục tiêu vận hành:** latency p95/p99, số truy vấn trên một request, giới hạn bộ nhớ và connection, tác động lên DB khi gọi nhiều lần?

Hợp đồng được định nghĩa trước giúp tránh tình trạng SQL trả ra “đúng kiểu dữ liệu” nhưng **sai ý nghĩa nghiệp vụ**. Ví dụ, “đơn gần nhất” theo `created_at` không tương đương “đơn thay đổi gần nhất” theo `updated_at`.

### Chọn câu hỏi đo được

Với endpoint danh sách, có thể viết yêu cầu dưới dạng:

> Trả tối đa 50 đơn có trạng thái được yêu cầu, chỉ thuộc tenant đã được xác thực, sắp xếp theo `created_at DESC, order_id DESC`. Client có thể yêu cầu trang tiếp theo bằng cursor; response không chứa thông tin khách hàng nhạy cảm và không cần tổng số đơn chính xác.

Đây là đặc tả đủ rõ để thiết kế query và các bài test. Số 50 là **giới hạn minh họa**; hệ thống thật phải chọn giá trị theo kích thước mỗi hàng, lưu lượng và SLO.

## 2. Mô hình dữ liệu mẫu: đơn hàng và dòng sản phẩm

Bài học dùng PostgreSQL làm ví dụ; các ý tưởng về projection, lọc, join và phân trang có thể áp dụng cho hệ quản trị khác, nhưng cú pháp index, cách tối ưu và isolation cần kiểm chứng theo engine thực tế.

```sql
CREATE TABLE orders (
    order_id      BIGINT PRIMARY KEY,
    tenant_id     BIGINT NOT NULL,
    customer_id   BIGINT NOT NULL,
    status        VARCHAR(20) NOT NULL
                  CHECK (status IN ('PENDING', 'PAID', 'CANCELLED')),
    total_amount  NUMERIC(18, 2) NOT NULL CHECK (total_amount >= 0),
    created_at    TIMESTAMPTZ NOT NULL,
    version       BIGINT NOT NULL DEFAULT 0 CHECK (version >= 0)
);

CREATE TABLE order_items (
    item_id       BIGINT PRIMARY KEY,
    order_id      BIGINT NOT NULL REFERENCES orders(order_id),
    product_sku   VARCHAR(80) NOT NULL,
    quantity      INTEGER NOT NULL CHECK (quantity > 0),
    unit_price    NUMERIC(18, 2) NOT NULL CHECK (unit_price >= 0)
);
```

Một số dữ liệu dùng để suy nghĩ:

```text
orders
order_id | tenant_id | status | total_amount | created_at
---------+-----------+--------+--------------+----------------------
101      | 10        | PAID   | 125.50       | 2026-11-01 09:30 UTC
102      | 10        | PAID   |  42.00       | 2026-11-01 09:31 UTC
103      | 10        | PAID   |  70.00       | 2026-11-01 09:31 UTC
104      | 10        | PENDING|  15.00       | 2026-11-01 09:32 UTC
201      | 20        | PAID   | 890.00       | 2026-11-01 09:33 UTC
```

Ở đây `order_id` là khóa toàn cục và `tenant_id` là ranh giới truy cập. Trong một hệ thống khác, khóa có thể chỉ duy nhất **trong từng tenant**; khi đó schema, primary key, index và điều kiện truy vấn phải dùng cặp `(tenant_id, order_id)` tương ứng. Không suy cấu trúc khóa từ tên trường mà không xem hợp đồng dữ liệu.

**Dữ liệu mẫu không mặc định phản ánh production.** Thực tế cần xét phân bố tenant lớn/nhỏ, số items trên mỗi order, độ chọn lọc trạng thái, tỷ lệ các đơn mới/cũ, soft delete và lượng dữ liệu có thể nằm trong cache.

## 3. Từ câu hỏi giao diện đến SELECT, WHERE và projection

Giao diện danh sách cần mã đơn, trạng thái, tiền và thời điểm tạo. Hãy lấy đúng những trường ấy:

```sql
SELECT order_id, status, total_amount, created_at
FROM orders
WHERE tenant_id = ?
  AND status = ?
ORDER BY created_at DESC, order_id DESC
LIMIT ?;
```

Các điều kiện có lý do rõ ràng:

- `tenant_id = ?` là **điều kiện phân tách dữ liệu**; tenant ID phải đến từ thông tin xác thực/ủy quyền đã kiểm tra, không tin mù quáng vào query string do client gửi.
- `status = ?` phản ánh bộ lọc đang chọn. Backend cần giới hạn tập giá trị hợp lệ và quy tắc chuyển trạng thái ở tầng phù hợp.
- `SELECT` có danh sách cột cụ thể để tránh tải những trường không cần như email, địa chỉ, metadata nội bộ hoặc payload lớn.
- `ORDER BY created_at DESC, order_id DESC` mô tả thứ tự ổn định khi nhiều đơn có cùng timestamp.
- `LIMIT ?` giới hạn lượng dữ liệu mỗi request; vẫn cần cap ở tầng API để tránh người dùng yêu cầu hàng triệu bản ghi.

**Vì sao tránh `SELECT *` ở API danh sách?** Một bảng có thể bổ sung cột JSON lớn hoặc thông tin nhạy cảm về sau. `SELECT *` có thể tăng network, RAM, chi phí deserialize và gây rò rỉ dữ liệu qua DTO/log. Projection rõ ràng giúp hợp đồng API ổn định hơn trong quá trình tiến hóa schema.

### Chỉ lấy các trường cần thiết không có nghĩa bỏ qua tính đúng

Màn hình có thể hiển thị `total_amount` đã được lưu theo bất biến nghiệp vụ. Nếu tổng tiền cần tính từ chi tiết, phải chọn rõ **nguồn sự thật và cách tính**: đọc cột tổng đã được duy trì nhất quán, hoặc tổng hợp item theo quy tắc thuế/khuyến mãi. Không tùy ý đổi sang `SUM(quantity * unit_price)` rồi mặc định nó tương đương tổng thanh toán.

Khi giá trị hiển thị cần định dạng tiền tệ, nên giữ `NUMERIC` ở DB và `BigDecimal` ở Java; việc đặt dấu phẩy, đơn vị tiền và locale là trách nhiệm của tầng trình bày, không phải phép nối chuỗi trong SQL.

## 4. Mở rộng điều kiện lọc mà không biến query thành SQL injection

Giả sử API có thể lọc theo:

- Trạng thái đơn bắt buộc.
- Ngày bắt đầu tạo đơn (tùy chọn).
- Ngày kết thúc, **không gồm** mốc kết thúc (*half-open interval*).
- Người dùng tenant đã được xác thực.

Câu SQL khi có đầy đủ khoảng thời gian:

```sql
SELECT order_id, status, total_amount, created_at
FROM orders
WHERE tenant_id = ?
  AND status = ?
  AND created_at >= ?
  AND created_at < ?
ORDER BY created_at DESC, order_id DESC
LIMIT ?;
```

Điều kiện `[from, to)` làm ranh giới rõ ràng và dễ ghép các cửa sổ thời gian liền nhau; không cần đoán “cuối ngày 23:59:59.999...” với độ chính xác timestamp có thể khác nhau. Chuyển ngày do người dùng chọn trong một **múi giờ được xác định** thành hai mốc thời gian UTC trước khi bind.

Một cách xây query có kiểm soát là dùng **các query shape cố định** (có/không có filter), hoặc tạo động phần `WHERE` từ **danh sách cột/toán tử được whitelist**, trong khi **giá trị luôn bind bằng `PreparedStatement`**. Không ghép tên cột, hướng sort hoặc biểu thức SQL tùy ý từ input người dùng.

Ví dụ cần **tránh**:

```java
// Nguy hiểm: userInput có thể sửa cấu trúc SQL.
String sql = "SELECT * FROM orders WHERE status = '" + userInput + "'";
```

Nên dùng:

```java
String sql = """
    SELECT order_id, status, total_amount, created_at
    FROM orders WHERE tenant_id = ? AND status = ?
    ORDER BY created_at DESC, order_id DESC LIMIT ?
    """;
// ps.setLong(1, authorizedTenantId);
// ps.setString(2, status.name());
// ps.setInt(3, boundedPageSize);
```

**PreparedStatement bảo vệ giá trị bind**, không tự làm an toàn một mảnh SQL tùy ý đã được nối trước đó. Nếu cho chọn sort, map các lựa chọn như `NEWEST` hoặc `AMOUNT_DESC` sang chuỗi SQL **do server định nghĩa sẵn**. Luôn thêm khóa phụ duy nhất khi cần phân trang ổn định.

## 5. Truy vấn cho danh sách khác truy vấn chi tiết

Với endpoint `GET /orders/{orderId}`, giao diện cần cả header và các dòng sản phẩm. Có hai chiến lược phổ biến:

**Một JOIN trả nhiều hàng:**

```sql
SELECT o.order_id, o.status, o.total_amount,
       i.item_id, i.product_sku, i.quantity, i.unit_price
FROM orders o
LEFT JOIN order_items i ON i.order_id = o.order_id
WHERE o.tenant_id = ?
  AND o.order_id = ?
ORDER BY i.item_id;
```

Một order có ba items sẽ tạo ba hàng kết quả, lặp lại phần header. Java phải gom nhóm theo `order_id`, xử lý order không có item (các cột item là NULL) và không vô tình tạo ba order DTO riêng. JOIN phù hợp khi số item trên một order có giới hạn và số hàng được ước lượng hợp lý.

**Hai query có mục đích riêng:**

```sql
-- Query 1: lấy header; kiểm tra tenant trên nguồn có thẩm quyền.
SELECT order_id, status, total_amount, created_at, version
FROM orders
WHERE tenant_id = ? AND order_id = ?;

-- Query 2: lấy các item, vẫn ràng buộc tenant thông qua cha.
SELECT i.item_id, i.product_sku, i.quantity, i.unit_price
FROM order_items i
JOIN orders o ON o.order_id = i.order_id
WHERE o.tenant_id = ? AND o.order_id = ?
ORDER BY i.item_id;
```

Hai query tách biệt giúp tránh lặp nhiều lần phần header và thuận tiện map DTO, nhưng phải cân nhắc **mức nhất quán**: nếu writer thay đổi items giữa hai SELECT dưới `READ COMMITTED`, header và items có thể phản ánh hai snapshot khác nhau.

Nếu endpoint yêu cầu cả hai phần nhất quán tại cùng một mốc PostgreSQL, có thể đọc chúng **trong cùng transaction `REPEATABLE READ READ ONLY`**, dùng một connection và thời lượng ngắn. Nếu API chỉ cần dữ liệu gần đúng và chấp nhận thay đổi giữa hai thao tác, phải ghi rõ hợp đồng thay vì tùy tiện áp transaction dài để “an toàn”.

### Tránh nhân số dòng khi JOIN nhiều quan hệ một-nhiều

Giả sử một đơn có 5 items và 4 payment attempts. JOIN đồng thời hai bảng con có thể tạo **5 × 4 = 20 hàng** cho một đơn. Khi áp `SUM(i.quantity * i.unit_price)` trên tập JOIN đó, tổng item có thể bị nhân lên 4 lần.

Giải pháp tùy nhu cầu:

- Lấy hai collection riêng rồi lắp DTO.
- Tổng hợp items và payments trong các subquery/CTE **riêng trước khi JOIN**.
- Dùng `EXISTS` để lọc sự tồn tại, thay vì JOIN chỉ để kiểm tra có một dòng con.
- Không áp `LIMIT 20` lên JOIN một-nhiều rồi hiểu nó nghĩa là 20 đơn hàng; nó có thể là 20 **dòng đã nhân**.

Ví dụ lọc đơn có chứa một SKU nhưng không muốn lặp order:

```sql
SELECT o.order_id, o.status, o.total_amount, o.created_at
FROM orders o
WHERE o.tenant_id = ?
  AND o.status = 'PAID'
  AND EXISTS (
      SELECT 1
      FROM order_items i
      WHERE i.order_id = o.order_id
        AND i.product_sku = ?
  )
ORDER BY o.created_at DESC, o.order_id DESC
LIMIT ?;
```

`EXISTS` mô tả đúng câu hỏi “có ít nhất một dòng sản phẩm phù hợp hay không”; query planner có thể chuyển thành semi-join và dùng index tùy dữ liệu/thống kê.

## 6. Tổng hợp cho báo cáo: để DB làm đúng phép nhóm

Một trang dashboard có thể cần số đơn và tổng tiền đã thanh toán trong mỗi ngày, không cần tải tất cả đơn về JVM rồi tự đếm.

```sql
SELECT (created_at AT TIME ZONE 'UTC')::date AS order_day_utc,
       COUNT(*) AS paid_orders,
       SUM(total_amount) AS paid_amount
FROM orders
WHERE tenant_id = ?
  AND status = 'PAID'
  AND created_at >= ?
  AND created_at < ?
GROUP BY (created_at AT TIME ZONE 'UTC')::date
ORDER BY order_day_utc;
```

Ví dụ cố định **ngày theo UTC**; nếu báo cáo dùng ngày theo múi giờ tenant, phải áp múi giờ được xác thực và chuẩn hóa nhất quán. Không dùng `created_at::date` mà không biết session timezone có thể ảnh hưởng cách gán ngày cho `TIMESTAMPTZ`.

Điều kiện lọc thời gian nằm trên **cột gốc** `created_at`, giúp một số chỉ mục B-tree/range hoạt động hiệu quả hơn so với việc áp hàm lên cột trong `WHERE`. Dù vậy, bản thân việc nhóm theo ngày vẫn có chi phí và có thể cần aggregate table/read model cho workload rất lớn.

**Điều cần quyết định từ hợp đồng:** `PAID` là trạng thái *hiện tại* hay muốn tính doanh thu theo **thời điểm thanh toán**? Nếu cần dòng tiền theo ngày thanh toán, `orders.created_at` có thể là **sai trường dữ liệu**. Khi ấy phải dùng `paid_at` hoặc ledger/event có ngữ nghĩa đúng, không cố giải quyết bằng index cho cột không liên quan.

## 7. ORDER BY phải tạo ra thứ tự xác định

Giả sử hai order `102` và `103` cùng `created_at = 2026-11-01T09:31:00Z`. Query:

```sql
SELECT order_id, created_at
FROM orders
WHERE tenant_id = 10 AND status = 'PAID'
ORDER BY created_at DESC;
```

**Không xác định** order `102` hay `103` đứng trước khi timestamp bằng nhau. Database có thể thay đổi thứ tự do index scan, parallel execution, VACUUM hoặc thay đổi plan.

Thêm khóa phụ duy nhất:

```sql
ORDER BY created_at DESC, order_id DESC
```

Trong dữ liệu minh họa, thứ tự là **103 → 102 → 101**. Đây là nền tảng quan trọng của phân trang, nhất là keyset/cursor pagination.

**Không dựa vào thứ tự ngẫu nhiên của PRIMARY KEY hay heap.** SQL không bảo đảm thứ tự khi không có `ORDER BY`. Nếu API cho phép sort theo trường có thể NULL, phải quy định cả `NULLS FIRST/LAST` và khóa phụ để bảo đảm cursor có semantics đúng.

## 8. OFFSET/LIMIT: đơn giản nhưng cần hiểu giới hạn

Với trang kích thước 20:

```sql
SELECT order_id, status, total_amount, created_at
FROM orders
WHERE tenant_id = ?
  AND status = ?
ORDER BY created_at DESC, order_id DESC
LIMIT 20 OFFSET 40;
```

Query này lấy trang thứ ba nếu đánh số trang bắt đầu từ 1, trong **trạng thái dữ liệu hiện tại**. Nó thuận tiện cho màn hình có số trang hoặc danh sách nhỏ.

Nhưng có hai vấn đề:

1. **Trang sâu:** database thường vẫn phải tìm/đi qua nhiều hàng trước `OFFSET` để bỏ qua. Một index phù hợp có thể giúp nhưng không khiến chi phí bỏ qua N hàng biến mất.
2. **Dữ liệu thay đổi giữa request:** nếu một order mới được chèn vào đầu danh sách sau khi client lấy trang một, `OFFSET 20` cho trang hai có thể **lặp** một order đã thấy. Nếu có bản ghi bị xóa, client cũng có thể **bỏ sót** order.

Ví dụ với trang 2 bản ghi:

```text
Ban đầu:            [105, 104] [103, 102] [101]
Client lấy trang 1:  105, 104
Chèn order 106:     [106, 105] [104, 103] [102, 101]
Client OFFSET 2:     104, 103  -> 104 xuất hiện lần hai
```

OFFSET/LIMIT **không sai** nếu hợp đồng chấp nhận danh sách biến động hoặc phải đi tới một trang số cụ thể. Nhưng không nên dùng nó làm mặc định cho *infinite scroll* trên bảng rất lớn hoặc cho quá trình export cần không mất/không trùng bản ghi.

## 9. Keyset/cursor pagination: tiếp tục sau khóa của hàng cuối

Với thứ tự `created_at DESC, order_id DESC`, thay vì đếm “bỏ qua 20 hàng”, trang kế tiếp hỏi: **“Cho tôi các hàng đứng sau cặp khóa của hàng cuối trang trước.”**

Trang đầu:

```sql
SELECT order_id, status, total_amount, created_at
FROM orders
WHERE tenant_id = ?
  AND status = ?
ORDER BY created_at DESC, order_id DESC
LIMIT ?;
```

Trang tiếp theo dùng cursor `(last_created_at, last_order_id)`:

```sql
SELECT order_id, status, total_amount, created_at
FROM orders
WHERE tenant_id = ?
  AND status = ?
  AND (created_at, order_id) < (?, ?)
ORDER BY created_at DESC, order_id DESC
LIMIT ?;
```

PostgreSQL hỗ trợ so sánh hai tuple kiểu này. Với cả hai cột được sắp xếp **DESC**, toán tử `<` chọn các khóa đứng sau cursor. Viết tường minh tương đương:

```sql
AND (
    created_at < ?
    OR (created_at = ? AND order_id < ?)
)
```

Lợi ích: database có thể tiếp tục từ vị trí khóa phù hợp bằng index thay vì duyệt rất nhiều hàng bị bỏ qua, và các order mới có khóa lớn hơn cursor **không đẩy lùi ranh giới trang đã lấy**.

### Cursor phải chứa đủ khóa sắp xếp

Chỉ dùng `created_at` làm cursor có thể **bỏ sót** order cùng timestamp. Với dữ liệu:

```text
Thứ tự:  (09:31,103), (09:31,102), (09:30,101)
Trang 1 gồm: (09:31,103)

Nếu cursor chỉ là thời gian 09:31 và trang 2 lọc created_at < 09:31:
  -> bỏ mất order 102.

Nếu cursor gồm (09:31,103):
  -> trang 2 lấy (09:31,102), rồi (09:30,101).
```

Trong API thật, cursor nên là **token opaque** có version/định dạng xác định, mang đầy đủ khóa và phạm vi bộ lọc. Có thể mã hóa rồi ký HMAC để phát hiện sửa đổi; **Base64 không phải chữ ký hay mã hóa bảo mật**. Phải ràng buộc cursor với tenant và những filter/sort được chấp nhận, hoặc kiểm tra các trường ấy riêng khi xử lý request; nếu không client có thể dùng cursor từ một query khác và nhận trang sai.

### Keyset không tự tạo snapshot bất biến qua nhiều HTTP request

Nếu `created_at` là immutable và không có xóa/update làm thay đổi membership, keyset thường tránh kiểu lặp do đơn mới chèn ở đầu. Tuy nhiên, nếu order đổi status giữa các trang, bị xóa, hoặc cột sort bị cập nhật, một kết quả có thể biến mất/chuyển vị trí. Keyset **không bảo đảm export đầy đủ từ một snapshot cố định** dưới mọi thay đổi đồng thời.

Khi cần một bản xuất đúng tại cùng một thời điểm, cần một thiết kế khác: snapshot nhất quán với tuổi transaction được kiểm soát, watermark/snapshot version phù hợp, hoặc dữ liệu bất biến kèm cơ chế snapshot/export riêng. Không giữ transaction database mở hàng giờ giữa các HTTP request chỉ để duy trì cursor.

## 10. Triển khai Java/JDBC: từ request tới Page DTO

Ví dụ Java 17+ sau triển khai hợp đồng danh sách đơn theo trạng thái. Nó dùng PostgreSQL, `DataSource` do ứng dụng quản lý, hai query shape cố định (trang đầu và trang tiếp theo), `PreparedStatement` và kỹ thuật **fetch `pageSize + 1`** để biết còn trang sau mà không cần `COUNT(*)`.

```java
import javax.sql.DataSource;
import java.math.BigDecimal;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.time.OffsetDateTime;
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

public final class OrderListReader {
    public enum Status { PENDING, PAID, CANCELLED }

    public record OrderSummary(
            long orderId, Status status,
            BigDecimal totalAmount, OffsetDateTime createdAt) {}

    public record Cursor(OffsetDateTime createdAt, long orderId) {
        public Cursor {
            Objects.requireNonNull(createdAt, "createdAt");
            if (orderId <= 0) {
                throw new IllegalArgumentException("orderId không hợp lệ");
            }
        }
    }

    public record Page(List<OrderSummary> items, Cursor nextCursor) {
        public Page {
            items = List.copyOf(items);
        }
    }

    private static final String FIRST_PAGE_SQL = """
        SELECT order_id, status, total_amount, created_at
        FROM orders
        WHERE tenant_id = ? AND status = ?
        ORDER BY created_at DESC, order_id DESC
        LIMIT ?
        """;

    private static final String NEXT_PAGE_SQL = """
        SELECT order_id, status, total_amount, created_at
        FROM orders
        WHERE tenant_id = ? AND status = ?
          AND (created_at, order_id) < (?, ?)
        ORDER BY created_at DESC, order_id DESC
        LIMIT ?
        """;

    private final DataSource dataSource;

    public OrderListReader(DataSource dataSource) {
        this.dataSource = Objects.requireNonNull(dataSource);
    }

    public Page listByStatus(
            long authorizedTenantId, Status status,
            Cursor cursor, int pageSize) throws SQLException {
        if (authorizedTenantId <= 0 || pageSize < 1 || pageSize > 100) {
            throw new IllegalArgumentException(
                    "tenant hoặc pageSize không hợp lệ");
        }
        Objects.requireNonNull(status, "status");

        String sql = cursor == null ? FIRST_PAGE_SQL : NEXT_PAGE_SQL;
        List<OrderSummary> fetched = new ArrayList<>();

        try (Connection c = dataSource.getConnection();
             PreparedStatement ps = c.prepareStatement(sql)) {
            ps.setLong(1, authorizedTenantId);
            ps.setString(2, status.name());
            int nextParameter = 3;
            if (cursor != null) {
                ps.setObject(nextParameter++, cursor.createdAt());
                ps.setLong(nextParameter++, cursor.orderId());
            }
            ps.setInt(nextParameter, pageSize + 1);
            ps.setQueryTimeout(5); // giây; tùy driver/DB

            try (ResultSet rs = ps.executeQuery()) {
                while (rs.next()) {
                    fetched.add(new OrderSummary(
                            rs.getLong("order_id"),
                            Status.valueOf(rs.getString("status")),
                            rs.getBigDecimal("total_amount"),
                            rs.getObject(
                                    "created_at", OffsetDateTime.class)));
                }
            }
        }

        boolean hasNext = fetched.size() > pageSize;
        List<OrderSummary> visible = fetched.subList(
                0, Math.min(pageSize, fetched.size()));
        Cursor nextCursor = null;
        if (hasNext) {
            OrderSummary lastVisible = visible.get(visible.size() - 1);
            nextCursor = new Cursor(
                    lastVisible.createdAt(), lastVisible.orderId());
        }
        return new Page(visible, nextCursor);
    }
}
```

Ví dụ gọi từ tầng dịch vụ sau khi **ủy quyền tenant**:

```java
// authorizedTenantId lấy từ security context đã kiểm tra.
var page1 = reader.listByStatus(
        authorizedTenantId, OrderListReader.Status.PAID, null, 2);

if (page1.nextCursor() != null) {
    var page2 = reader.listByStatus(
            authorizedTenantId, OrderListReader.Status.PAID,
            page1.nextCursor(), 2);
}
```

Các quyết định thiết kế có ý nghĩa:

- **Không tạo pool trên mỗi request.** `DataSource` sống cùng application, còn `Connection` được mượn và trả trong `try-with-resources`.
- **Không nhận tenantId tùy ý làm quyền.** Method đặt tên `authorizedTenantId` để nhắc rằng tầng authentication/authorization phải xác định phạm vi này. Method tự nó **không thay thế kiểm tra quyền**.
- **Không ghép SQL từ user input.** Status là enum và giá trị được bind. Việc cung cấp sort/filter động cần whitelist query shapes riêng.
- **Không giữ mọi hàng trong RAM.** Mỗi request chỉ nhận tối đa `pageSize + 1` hàng, rồi trả tối đa `pageSize`.
- **Không chạy COUNT toàn bảng để biết có trang sau.** Hàng thêm vào ở cuối chính là tín hiệu còn trang.
- **Không coi timeout 5 giây là bảo đảm latency 5 giây.** Thời gian đợi connection pool, mạng hoặc HTTP có timeout riêng; driver/DB có thể có cách thực thi hủy statement khác nhau.
- **Không giả định token cursor an toàn chỉ vì là record Java.** Controller phải mã hóa/xác minh token và bảo vệ ranh giới tenant, filter, sort trước khi gọi repository.

Đoạn code dùng `OffsetDateTime` cho `TIMESTAMPTZ` vì PostgreSQL JDBC hỗ trợ kiểu này. Cursor phải giữ **đúng độ chính xác timestamp** mà database trả về; nếu controller cắt về milliseconds khi DB giữ microseconds, trang tiếp theo có thể bỏ sót hoặc lặp bản ghi.

## 11. Chọn index từ mẫu WHERE và ORDER BY, không từ tên endpoint

Với query danh sách:

```sql
WHERE tenant_id = ?
  AND status = ?
ORDER BY created_at DESC, order_id DESC
```

Một **index ứng viên** trên PostgreSQL:

```sql
CREATE INDEX idx_orders_tenant_status_recent
ON orders (tenant_id, status, created_at DESC, order_id DESC)
INCLUDE (total_amount);
```

Lập luận chọn thứ tự:

1. `tenant_id` và `status` là điều kiện bằng, giúp thu hẹp nhóm hàng.
2. `created_at DESC` và `order_id DESC` phù hợp với thứ tự đọc và cursor.
3. `total_amount` trong `INCLUDE` có thể giúp index bao phủ projection của danh sách ở một số tình huống; cột INCLUDE **không** là khóa dùng tìm kiếm.

Nhưng index này không mặc định là tốt nhất:

- Với bảng nhỏ hoặc điều kiện ít chọn lọc, planner có thể chọn sequential scan.
- Index tăng chi phí INSERT/UPDATE/DELETE, bộ nhớ đệm và dung lượng.
- `INCLUDE` làm index rộng; *index-only scan* còn phụ thuộc visibility map, dữ liệu và plan.
- Nếu workload chủ yếu lọc theo `created_at` mà không có `status`, thứ tự khóa khác có thể phù hợp hơn.
- Với `EXISTS` theo SKU, có thể cần index trên `order_items(order_id, product_sku)` hoặc phương án khác tùy độ chọn lọc; không kết luận bằng trực giác.
- Index trên bảng được ghi nhiều phải được triển khai bằng migration phù hợp, tránh tạo khóa dài/gián đoạn không được dự trù.

Ứng viên cho phép đọc items theo cha:

```sql
CREATE INDEX idx_order_items_by_order
ON order_items (order_id, item_id);
```

Đây là ví dụ **index bổ sung**, không phải quy tắc “mọi foreign key phải có đúng index này”. Xem các index đã có, tỷ lệ query và chi phí duy trì trước khi tạo.

### Đo query plan thay vì đoán

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT order_id, status, total_amount, created_at
FROM orders
WHERE tenant_id = 10 AND status = 'PAID'
ORDER BY created_at DESC, order_id DESC
LIMIT 50;
```

Đọc `actual rows`, estimates, loại scan, sort, `Buffers: shared hit/read` và thời gian. Test nhiều tenant lớn/nhỏ và phân bố dữ liệu giống production. Một lần query nhanh sau khi cache nóng chưa chứng minh truy vấn đạt p99 dưới tải thật.

**Lưu ý:** `EXPLAIN ANALYZE` **thực thi câu lệnh**; ví dụ SELECT này thích hợp để đo trong môi trường có kiểm soát. Không chạy vô tư trên câu UPDATE/DELETE production để “xem plan”, vì chúng có thể làm thay đổi dữ liệu.

## 12. Tính mới của dữ liệu và ranh giới transaction đọc

SQL đúng chưa bảo đảm **ngữ nghĩa đọc đúng** khi có transaction đang ghi.

### Đọc ngay sau ghi

Sau khi ghi đơn và commit trên primary, một SELECT từ read replica bất đồng bộ có thể chưa thấy đơn do replication lag. Với màn hình xác nhận thanh toán, đọc từ nguồn đủ nhất quán (thường primary hoặc cơ chế read-after-write được hệ thống bảo đảm) thay vì kết luận “đơn biến mất” từ replica chậm.

### Đọc nhiều query cho một view

Nếu trang chi tiết đọc header rồi items bằng hai query, PostgreSQL `READ COMMITTED` thường cho snapshot mới tại **mỗi statement**. Writer commit giữa chúng có thể khiến header và items khác thời điểm. Đối với view yêu cầu một ảnh nhất quán, dùng một transaction đọc ngắn ở `REPEATABLE READ`; đây là quyết định theo use case, không phải lý do mở transaction cho toàn phiên người dùng.

### Đếm tổng và danh sách cũng có thể lệch

Hai query:

```sql
SELECT COUNT(*) FROM orders WHERE tenant_id=? AND status=?;
SELECT ... FROM orders
WHERE tenant_id=? AND status=?
ORDER BY created_at DESC, order_id DESC LIMIT ?;
```

nếu chạy tại hai thời điểm có thể trả `total=100` nhưng trang đầu đã có 101 bản ghi trong phạm vi lọc. Nếu UI không thực sự cần số trang chính xác, không nên ép một phép COUNT đắt đỏ vào mỗi request. Nếu cần số đếm chính xác cùng snapshot, thiết kế transaction/isolation hoặc mô hình báo cáo thích hợp và chấp nhận chi phí.

### Cache không phải nguồn sự thật cho bất biến

Cache có thể phục vụ trang đọc cho phép stale data, nhưng không nên dùng giá trị cached stock/order status để quyết định đặt chỗ hoặc thu tiền mà bỏ qua điều kiện transaction ở DB. Cần hợp đồng freshness/TTL/invalidation và fallback; cache miss trên một trang lớn có thể gây thác truy vấn đến DB.

## 13. Kiểm thử theo use case: đúng dữ liệu trước, hiệu năng sau

Một bộ integration test tốt cần có **fixtures chứa ca biên**:

| Ca kiểm thử | Dữ liệu giả lập | Điều cần chứng minh |
| --- | --- | --- |
| Tenant isolation | Tenant 10 và 20 cùng có đơn PAID | Query của tenant 10 không trả order của tenant 20 |
| Tie-breaking | Nhiều đơn cùng `created_at` | Phân trang không mất/lặp do cùng timestamp |
| Trang cuối | Số bản ghi không chia hết cho page size | `nextCursor=null` khi không còn dữ liệu |
| Filter | PAID/PENDING/CANCELLED lẫn nhau | Chỉ các hàng đúng status được trả |
| Missing order | Không có order ID hoặc nằm tenant khác | Không lộ chi tiết qua truy vấn không được phép |
| JOIN một-nhiều | Order có nhiều items, order không có items | Không nhân đối tượng cha/không tạo item NULL |
| Đồng thời | Chèn order mới giữa hai lần đọc trang | Phân biệt giới hạn keyset với snapshot bất biến |
| Timestamp precision | Hai bản ghi cách nhau microsecond | Cursor không bị làm tròn làm sai ranh giới |
| Dữ liệu lớn | Nhiều tenant, phân bố hot/cold | Query plan/latency phù hợp SLO dưới tải |

Ví dụ dữ liệu test để chứng minh thứ tự:

```sql
-- Chỉ chạy trên database test đã tạo schema riêng.
INSERT INTO orders (
    order_id, tenant_id, customer_id, status,
    total_amount, created_at, version)
VALUES
    (101, 10, 501, 'PAID', 125.50, '2026-11-01T09:30:00Z', 0),
    (102, 10, 502, 'PAID',  42.00, '2026-11-01T09:31:00Z', 0),
    (103, 10, 501, 'PAID',  70.00, '2026-11-01T09:31:00Z', 0),
    (104, 10, 501, 'PENDING', 15.00, '2026-11-01T09:32:00Z', 0),
    (201, 20, 601, 'PAID', 890.00, '2026-11-01T09:33:00Z', 0);
```

Đoạn JUnit 5 minh họa dưới đây giả định có một `DataSource` đã kết nối database test với fixture vừa seed và tạo `reader` từ `OrderListReader`:

```java
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;
import java.util.List;

class OrderListReaderIT {
    // DataSource và migration/fixture được chuẩn bị
    // trong @BeforeEach hoặc test container của project.
    private final OrderListReader reader = createReaderFromTestDataSource();

    @Test
    void pagesPaidOrdersWithoutCrossTenantLeakOrTies() throws Exception {
        var first = reader.listByStatus(
                10L, OrderListReader.Status.PAID, null, 2);
        assertEquals(
                List.of(103L, 102L),
                first.items().stream()
                     .map(OrderListReader.OrderSummary::orderId)
                     .toList());
        assertNotNull(first.nextCursor());

        var second = reader.listByStatus(
                10L, OrderListReader.Status.PAID,
                first.nextCursor(), 2);
        assertEquals(
                List.of(101L),
                second.items().stream()
                      .map(OrderListReader.OrderSummary::orderId)
                      .toList());
        assertNull(second.nextCursor());
    }

    private static OrderListReader createReaderFromTestDataSource() {
        // Thay bằng DataSource fixture của project đang học.
        throw new UnsupportedOperationException(
                "Cần cung cấp database test/fixture");
    }
}
```

Đoạn test mô tả **assertion cần triển khai**, không phải một test có thể chạy độc lập ngay (method dựng DataSource là placeholder). Khi tích hợp CI, dùng PostgreSQL thực/Testcontainers, reset fixture giữa các test, cấu hình connection pool và kiểm tra version driver. Không dùng một DB nhúng khác rồi suy ra index plan/isolation PostgreSQL chắc chắn giống.

Một test hiệu năng cũng nên xác nhận **số SQL trên một request**: ORM lazy loading có thể gây N+1 (1 SELECT lấy 50 đơn rồi 50 SELECT lấy items), khiến truy vấn riêng lẻ đều nhanh nhưng API chậm dưới tải.

## 14. Những lỗi thường gặp khi thiết kế từ nhu cầu đọc

| Lỗi | Hậu quả | Hướng sửa |
| --- | --- | --- |
| Bắt đầu từ `SELECT *` rồi trả entity ra API | Đọc thừa cột, lộ dữ liệu, hợp đồng phụ thuộc schema | Projection/DTO được định nghĩa từ màn hình |
| Dùng `tenant_id` do client tự khai mà không ủy quyền | Truy cập xuyên tenant | Lấy phạm vi từ security context, áp điều kiện DB và test |
| Chỉ sort theo thời gian không duy nhất | Trang tiếp theo lặp/mất khi nhiều giá trị bằng nhau | Thêm khóa duy nhất, cursor chứa đủ khóa |
| OFFSET sâu cho infinite scroll | Bỏ qua nhiều hàng; trang biến động khi insert/delete | Keyset khi use case cho phép |
| JOIN nhiều collection rồi `LIMIT` | Nhân số dòng; LIMIT đếm item thay vì đơn | Phân trang cha trước, EXISTS, query con riêng |
| `COUNT(*)` trên mỗi lần kéo trang | Tăng tải đọc khi chỉ cần biết còn trang | Fetch pageSize + 1 hoặc summary riêng |
| Build SQL từ tên sort do người dùng gửi | SQL injection/sort không kiểm soát | Whitelist query shapes, bind values |
| Dùng replica cho read-after-write nghiêm ngặt | Không thấy commit vừa ghi do replication lag | Đọc nguồn đủ nhất quán hoặc cơ chế consistency token |
| Tính tổng tiền sai ngữ nghĩa | Dashboard “đúng SQL” nhưng sai nghiệp vụ | Xác định nguồn/timestamp/quy tắc tính |
| Chỉ kiểm tra chạy được trên vài hàng | Plan khác production, không thấy N+1/hot tenant | Đo workload đại diện và các ca biên |

## 15. Bài tập thực hành

### Bài tập 1: bắt đầu từ UI

Màn hình chỉ hiển thị mã đơn, trạng thái và ngày tạo. Developer viết `SELECT * FROM orders` rồi serialize toàn bộ entity, gồm địa chỉ và dữ liệu thanh toán.

**Câu hỏi:** nên thay đổi hợp đồng và truy vấn như thế nào?

**Gợi ý đáp án:** định nghĩa DTO ba trường, thêm điều kiện phạm vi tenant/ủy quyền và danh sách cột cụ thể; phân trang có giới hạn và `ORDER BY` xác định. Không trả dữ liệu nhạy cảm chỉ vì entity có trường ấy.

### Bài tập 2: thiếu order có cùng timestamp

Ba đơn được sắp theo `(created_at DESC, order_id DESC)`:

```text
(09:31,103), (09:31,102), (09:30,101)
```

Client lấy page size 1 rồi gửi cursor chỉ gồm `09:31`. Vì sao đơn 102 có thể mất? Hãy viết điều kiện cursor đúng.

**Đáp án:** nếu dùng `created_at < '09:31'`, hàng 102 cùng timestamp bị loại. Cursor phải chứa cả `created_at` và `order_id`: `(created_at, order_id) < (?, ?)` đối với thứ tự DESC/DESC.

### Bài tập 3: JOIN làm sai phân trang

Mỗi order có 6 items. Query JOIN orders với items rồi `LIMIT 12`. Có chắc kết quả gồm 12 order không?

**Đáp án:** không. Có thể chỉ gồm 2 order và 12 item rows. Nếu cần 12 order, phân trang bảng cha theo khóa trước rồi lấy items cho các order thuộc trang; hoặc thiết kế truy vấn hai bước/CTE phù hợp.

### Bài tập 4: tổng hợp đúng ngày

Dashboard yêu cầu doanh thu theo **ngày thanh toán của tenant**. Developer nhóm theo `orders.created_at::date` trên database có session timezone ngẫu nhiên. Có vấn đề gì?

**Đáp án:** cần trường có đúng ngữ nghĩa **thanh toán** (chẳng hạn `paid_at` hoặc ledger event), quy định timezone của tenant và dùng ranh giới thời gian ổn định. Ngày tạo đơn không mặc nhiên là ngày thu tiền.

### Bài tập 5: chọn cách phân trang

Một báo cáo nội bộ cần nhảy ngay tới trang 7 trên danh sách nhỏ, còn feed đơn hàng lớn cần “Tải thêm” liên tục với dữ liệu mới thường xuyên xuất hiện.

**Đáp án:** OFFSET/LIMIT có thể phù hợp báo cáo nhỏ cần số trang; keyset/cursor thường phù hợp feed lớn đi theo thứ tự. Cả hai phải có ORDER BY xác định. Nếu cần snapshot cố định, keyset riêng chưa đủ.

### Bài tập 6: index theo use case

Query quan trọng có `WHERE tenant_id=? AND status=? ORDER BY created_at DESC, order_id DESC LIMIT 50`. Một developer đề xuất tạo bốn index độc lập trên bốn cột.

**Đáp án:** đánh giá index ghép `(tenant_id, status, created_at DESC, order_id DESC)` vì phản ánh cả filter lẫn sort, rồi đo `EXPLAIN (ANALYZE, BUFFERS)` và chi phí ghi. Không mặc định càng nhiều index càng nhanh.

### Bài tập 7: dữ liệu sau ghi không xuất hiện

API vừa `COMMIT` tạo đơn trên primary, sau đó truy vấn read replica và thấy trang danh sách thiếu đơn ấy. Có thể kết luận INSERT thất bại không?

**Đáp án:** không. Replica bất đồng bộ có thể lag. Với read-after-write bắt buộc, đọc từ nguồn có bảo đảm phù hợp và đối soát commit/receipt; không retry tạo đơn bằng ID mới chỉ vì replica chưa thấy.

### Bài tập 8: cùng câu SQL nhưng sai quyền

API cho phép gửi `tenant_id=20` qua query parameter, backend lấy trực tiếp giá trị đó trong WHERE dù người dùng thuộc tenant 10. SQL vẫn dùng `PreparedStatement`. Có an toàn không?

**Đáp án:** không. Parameter binding chống chèn cấu trúc SQL nhưng **không cấp quyền truy cập**. Backend phải xác định tenant từ identity/security context, kiểm tra chính sách ủy quyền, áp predicate và kiểm thử truy cập chéo.

### Checklist thiết kế truy vấn từ nhu cầu đọc

- Đã định nghĩa **use case, hình dạng DTO, quyền truy cập, điều kiện lọc, sort và số hàng tối đa** chưa?
- Mỗi `WHERE` có xuất phát từ hợp đồng nghiệp vụ, đặc biệt ranh giới tenant/owner chưa?
- Projection có lấy đúng cột cần thiết, không vô tình đưa PII hay entity nội bộ ra response chưa?
- Câu JOIN/EXISTS/aggregate có đúng **đơn vị dữ liệu** (đơn hàng, dòng hàng, thanh toán), không nhân bản hoặc đếm sai chưa?
- Thứ tự có xác định với tie-breaker duy nhất; cursor có chứa đủ khóa, giữ đúng độ chính xác timestamp không?
- Đã chọn OFFSET hay keyset theo cách người dùng điều hướng, quy mô và thay đổi đồng thời chưa?
- Query Java có bind giá trị an toàn, giới hạn page size, dùng `try-with-resources` và không tạo N+1/pool leak chưa?
- Chỉ mục được đề xuất từ filter/sort thực tế và được kiểm tra bằng `EXPLAIN` trên dữ liệu đại diện chưa?
- Mức nhất quán đọc từ primary/replica/cache và giữa nhiều statement có phù hợp yêu cầu chưa?
- Integration test có trường hợp chéo tenant, timestamp bằng nhau, filter, trang cuối, concurrent insert và dữ liệu lớn chưa?

**Kết luận:** Xây dựng truy vấn từ nhu cầu đọc là quá trình **chuyển một yêu cầu giao diện thành hợp đồng dữ liệu có thể kiểm chứng**: ai được xem, xem trường nào, lọc/sắp xếp ra sao, đọc bao nhiêu và cần nhất quán đến mức nào. Từ hợp đồng đó mới thiết kế `SELECT`/`WHERE`/`JOIN`/`ORDER BY`/phân trang, triển khai JDBC và đánh giá chỉ mục, query plan, transaction. Khi giữ ranh giới quyền, thứ tự xác định và dữ liệu đại diện trong kiểm thử, lớp persistence Java mới trả **đúng dữ liệu, đúng thời điểm và với chi phí phù hợp**, thay vì chỉ chạy một câu SQL có vẻ hợp lệ.
