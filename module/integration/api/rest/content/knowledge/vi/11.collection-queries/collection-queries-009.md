# Metadata, liên kết trang kế tiếp và điều kiện kết thúc

## 1. Mục tiêu: client duyệt hết collection mà không bỏ sót hoặc lặp vô hạn

Một REST API có thể quản lý hàng triệu đơn hàng, sản phẩm hoặc sự kiện. Nếu **GET /api/orders** luôn trả toàn bộ dữ liệu, phản hồi trở nên lớn, gây tốn băng thông, bộ nhớ và thời gian chờ, đồng thời dễ làm quá tải database. Vì vậy API thường trả dữ liệu theo **trang (pagination)**.

Tuy nhiên, **chia thành nhiều trang chưa đủ để tạo ra một hợp đồng có thể dùng an toàn**. Client cần trả lời được ba câu hỏi:

1. **Trang hiện tại là gì?** Bao nhiêu phần tử thực sự được trả, giới hạn bao nhiêu, bộ lọc và thứ tự nào đã áp dụng?
2. **Đi tiếp bằng cách nào?** Có một URL trang kế tiếp, cursor hay số trang để client sử dụng mà không phải tự phỏng đoán?
3. **Khi nào phải dừng?** Trang cuối được nhận biết bằng tín hiệu nào, kể cả khi số phần tử đúng bằng kích thước trang?

Bài **“Metadata, liên kết trang kế tiếp và điều kiện kết thúc”** thuộc chương **Truy vấn tập hợp** của module **INTEGRATION_API_REST**. Người học sẽ thiết kế hợp đồng resource/URI, query parameters, JSON response và HTTP headers; thực hành kiểm thử với Java/Spring, phân tích trường hợp dữ liệu thay đổi, phân quyền, cache, OpenAPI và khả năng truy vết.

**Nguyên tắc xuyên suốt:** Server phải phát ra **tín hiệu điều hướng và kết thúc rõ ràng**; client không được coi “đã đủ `limit` phần tử” là bằng chứng chắc chắn còn trang tiếp theo.

## 2. Mô hình tư duy: collection, page và traversal

Giả sử collection gồm tất cả đơn hàng mà một tenant có quyền xem. Một truy vấn có thể trông như sau:

~~~http
GET /api/orders?status=PAID&limit=2 HTTP/1.1
Host: api.example.test
Accept: application/json
Authorization: Bearer <access-token>

~~~

Yêu cầu nói rằng client muốn các đơn hàng trạng thái **PAID**, tối đa **2 mục trên mỗi trang**. Server có thể phản hồi:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: private, no-store
Link: </api/orders?status=PAID&limit=2&after=c_v1_a91>; rel="next"

{
  "data": [
    {"id": 109, "status": "PAID", "createdAt": "2026-11-18T10:07:00Z"},
    {"id": 108, "status": "PAID", "createdAt": "2026-11-18T10:06:00Z"}
  ],
  "page": {
    "limit": 2,
    "returned": 2,
    "hasNext": true,
    "nextCursor": "c_v1_a91"
  },
  "links": {
    "self": "/api/orders?status=PAID&limit=2",
    "next": "/api/orders?status=PAID&limit=2&after=c_v1_a91"
  }
}
~~~

**Toàn bộ giá trị URI, cursor và đơn hàng ở đây là minh họa.** `c_v1_a91` chỉ là một chuỗi placeholder; client phải coi cursor thực là **opaque token** và không cố giải mã hoặc tự sửa nó.

Phân biệt ba lớp thông tin:

- **`data`**: các resource thực sự thuộc trang hiện tại.
- **`page`**: metadata giải thích giới hạn được áp dụng, số mục được trả, tín hiệu còn trang sau và cursor tiếp tục.
- **`links` hoặc HTTP `Link` header**: cách điều hướng đến trang kế tiếp mà client có thể dùng trực tiếp.

API có thể dùng body links, HTTP Link header hoặc cả hai. Khi cung cấp cả hai, **chúng phải mô tả cùng một trang kế tiếp**. Cần xác định một nguồn tạo URL chung thay vì tính hai phiên bản không đồng bộ.

### Các khái niệm không được trộn lẫn

| Khái niệm | Ý nghĩa | Chú ý |
|---|---|---|
| **Collection** | Tập resource theo quyền và bộ lọc | Không mặc định là tất cả dữ liệu trong database |
| **Page** | Phần kết quả của một truy vấn collection | Có giới hạn, thứ tự và ngữ cảnh |
| **Page size/limit** | Số mục tối đa trên một response | Có thể khác số mục thực trả |
| **Offset** | Bỏ qua một số mục trước khi lấy trang | Dễ dùng nhưng có vấn đề ở dữ liệu lớn/biến động |
| **Cursor** | Mốc tiếp tục do server cấp | Nên opaque, gắn với truy vấn và ngữ cảnh |
| **Next link** | URL lấy trang kế tiếp | Nên mang đủ tham số cần thiết |
| **End-of-collection** | Không còn trang tiếp theo theo snapshot/quy tắc truy vấn | Không đồng nghĩa collection không bao giờ có dữ liệu mới |

## 3. Những metadata nên có, nên cân nhắc và không nên hứa quá mức

Không có một schema phân trang JSON duy nhất bắt buộc cho mọi REST API. Tuy nhiên, hợp đồng ổn định thường có các trường:

| Trường | Ví dụ | Độ cần thiết | Lưu ý |
|---|---|---|---|
| `limit` | `20` | Nên có | **Giới hạn thực tế server áp dụng**, không chỉ giá trị client gửi |
| `returned` | `18` | Nên có | Phải bằng số phần tử trong `data` |
| `hasNext` | `true` | Rất hữu ích | Tín hiệu boolean do server quyết định |
| `nextCursor` | `"c_v1_..."` | Khi dùng cursor | `null` hoặc vắng mặt khi không còn trang sau theo contract |
| `links.self` | `"/api/orders?limit=20"` | Hữu ích | URL biểu diễn truy vấn hiện tại |
| `links.next` | `"/api/orders?limit=20&after=..."` | Rất hữu ích | URL hoàn chỉnh cho bước tiếp theo; `null` khi dừng |
| `page` / `offset` | `3` / `40` | Khi dùng offset | Phải công bố page đánh số từ 0 hay 1 |
| `totalItems` | `12840` | Tùy chọn | COUNT có thể đắt, thay đổi và cần nêu độ chính xác |
| `totalPages` | `643` | Tùy chọn | Chỉ ý nghĩa khi total và page size xác định |
| `snapshot` hoặc `asOf` | Mốc phiên bản dữ liệu | Tùy nhu cầu | Chỉ công bố nếu server thực sự bảo đảm ngữ nghĩa đã mô tả |
| `sort`, `filters` | `createdAt:desc,id:desc` | Hữu ích khi cần debug | Không được làm lộ điều kiện nội bộ hoặc dữ liệu ngoài quyền |

Metadata **phải phản ánh dữ liệu được trả thực tế**. Nếu client gửi `limit=1000` nhưng API chỉ cho tối đa 100, server cần chọn một chính sách rõ:

- **Từ chối 400 Bad Request** và nói giới hạn tối đa; hoặc
- **Giới hạn về 100** và trả `page.limit=100` cùng tài liệu cho biết cơ chế clamp.

Không để response vừa trả tối đa 100 mục vừa quảng bá `limit=1000`, vì client sẽ tính thời gian hoặc số trang sai.

### `totalItems` không phải điều kiện bắt buộc để phân trang

Một truy vấn đếm toàn bộ bảng với bộ lọc phức tạp đôi khi tốn hơn chính truy vấn lấy trang. Trên dữ liệu lớn hoặc thay đổi liên tục, `totalItems` còn có thể trở nên lỗi thời ngay sau khi tính.

Các lựa chọn hợp lý:

1. **Không trả total**; client dùng `hasNext`/`next` để duyệt.
2. Trả **total chính xác theo một snapshot** nếu nghiệp vụ thực sự cần và hệ thống có khả năng bảo đảm.
3. Trả **total ước lượng** nhưng ghi rõ `estimatedTotal` hoặc `totalIsEstimate`, tuyệt đối không gắn nhãn chính xác giả.

Đừng yêu cầu một hệ thống event log hàng tỷ bản ghi chạy **COUNT(*)** trên từng page request chỉ để hiển thị “trang 1 / 1.283.916”.

## 4. Biểu diễn liên kết trang kế tiếp: body và HTTP Link

### Liên kết trong JSON

Một cách phổ biến:

~~~json
{
  "data": [{"id": 109}, {"id": 108}],
  "page": {
    "limit": 2,
    "returned": 2,
    "hasNext": true
  },
  "links": {
    "self": "/api/orders?limit=2",
    "next": "/api/orders?limit=2&after=c_v1_a91"
  }
}
~~~

Điểm mạnh của body links là SDK JavaScript/Java có thể đọc trực tiếp từ JSON. Nếu dùng framework hypermedia như HAL hoặc một profile JSON khác, tên trường có thể khác; cần thống nhất **media type và schema** thay vì trộn nhiều quy ước.

### HTTP Link header theo Web Linking

HTTP có header **Link** để mang các liên kết quan hệ. Theo cách dùng của RFC 8288, relation type **`next`** cho biết liên kết tới resource kế tiếp trong chuỗi điều hướng:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Link: </api/orders?limit=2&after=c_v1_a91>; rel="next"
Link: </api/orders?limit=2>; rel="first"

{"data":[{"id":109},{"id":108}]}
~~~

**Relative URI** trong Link được phân giải theo ngữ cảnh URL của response. Có thể dùng **absolute URI**, nhưng phải chú ý reverse proxy, host đáng tin cậy và nhất quán HTTPS. Không sao chép Host hoặc `X-Forwarded-Host` không được tin cậy để tạo URL, vì có nguy cơ trả liên kết dẫn sang tên miền của bên tấn công.

Những relation thường được API cân nhắc:

- **`self`**: resource/biểu diễn hiện tại.
- **`next`**: trang kế tiếp trong chuỗi điều hướng.
- **`prev`**: trang trước khi có thể xác định.
- **`first`**: trang đầu.
- **`last`**: trang cuối khi thực sự biết cách định danh nó.

Không bắt buộc tạo `last` hoặc `totalPages` trong mô hình cursor nếu không thể biết trang cuối mà không quét hết collection. `prev` với keyset cũng cần chiến lược riêng; không đơn giản đảo cursor hiện tại.

### Browser và CORS

Với frontend ở origin khác, response chứa Link header phải tuân thủ CORS. Nếu JavaScript cần đọc header **Link**, server có thể cần:

~~~http
Access-Control-Allow-Origin: https://app.example.test
Access-Control-Expose-Headers: Link
Vary: Origin
~~~

Nếu API chỉ cung cấp `links.next` trong JSON, JavaScript có thể đọc qua body khi response CORS hợp lệ. **CORS không phải authorization**; mọi trang tiếp theo vẫn phải kiểm tra quyền độc lập.

### Nên chọn một hay cả hai?

| Lựa chọn | Ưu điểm | Đánh đổi |
|---|---|---|
| Chỉ `links.next` trong body | SDK/SPA xử lý JSON thuận tiện | Client chỉ dùng header không thấy link |
| Chỉ HTTP `Link` | Tương thích Web Linking, giảm cấu trúc body | Một số client cần parser header; browser có yêu cầu expose |
| Cả body và Link | Phù hợp nhiều kiểu client | Phải tạo từ cùng một nguồn và kiểm thử không mâu thuẫn |

Trong bài thực hành này, ta chọn **body `links.next` là giao diện chính**, còn **Link header là tín hiệu bổ sung** cùng giá trị.

## 5. Điều kiện kết thúc: hợp đồng phải dứt khoát

Một client đọc tuần tự có thể mắc lỗi khi quyết định còn dữ liệu hay không. Hãy thống nhất hợp đồng:

> **Nếu `links.next` khác `null`, còn một trang tiếp theo có thể yêu cầu. Nếu `links.next` bằng `null` và `page.hasNext=false`, traversal đã tới cuối của tập kết quả theo ngữ nghĩa truy vấn hiện tại.**

Hợp đồng nên yêu cầu `page.hasNext` và `links.next` **luôn đồng nhất**. Với Link header, chỉ gửi `rel="next"` khi có next link; trang cuối **không quảng bá next**.

### Bốn trường hợp cần kiểm tra

| Tình huống | `data` | `hasNext` | `links.next` |
|---|---|---|---|
| Collection rỗng | `[]` | `false` | `null` |
| Có ít hơn limit mục và không còn kết quả | `[...]` | `false` | `null` |
| Trang đầy nhưng vẫn có mục tiếp theo | Đúng `limit` mục | `true` | URL kế tiếp |
| Trang đầy và **đúng là trang cuối** | Đúng `limit` mục | `false` | `null` |

**Trường hợp cuối là chỗ dễ sai nhất.** Nếu một collection có đúng 40 mục, `limit=20`, trang thứ hai có 20 mục nhưng **không còn trang thứ ba**. Client không được giả định `data.length === limit` đồng nghĩa còn trang tiếp theo.

### Vì sao `data.length < limit` chưa đủ?

Khi dữ liệu ổn định và server luôn lấp đầy trang, trang có ít mục hơn limit thường là dấu hiệu đã hết. Nhưng đây là **suy đoán phụ thuộc implementation**, không phải hợp đồng đáng tin cậy:

- Server có thể **lọc quyền** hoặc loại dữ liệu không hợp lệ ở bước sau truy vấn, tạo trang ngắn dù còn kết quả.
- Page size có thể bị giới hạn động hoặc áp chính sách khác.
- Backend có thể phân trang từ nhiều nguồn, mỗi nguồn cung cấp kết quả theo từng đợt.
- Một vài API cố ý trả trang ngắn để giới hạn thời gian xử lý.

Tốt nhất là client dựa vào **next link/hasNext do server công bố**, không tự suy ra dựa trên độ dài array. Nếu API lựa chọn hợp đồng khác, phải mô tả cụ thể và test các cạnh.

### Có cần trả 404 hoặc 204 khi hết trang?

Với truy vấn collection hợp lệ, **200 OK** và `data: []`, `hasNext: false`, `next: null` là lựa chọn thông dụng, dễ xử lý. **404 Not Found** thường phù hợp khi resource hoặc đường dẫn không tồn tại, không phải cách mặc định biểu thị một danh sách rỗng. **204 No Content** không phù hợp nếu hợp đồng yêu cầu body metadata để nói rõ kết thúc.

**206 Partial Content** không phải status mặc định cho response được chia trang bằng `limit`/`cursor`; 206 gắn với cơ chế HTTP Range. Trang dữ liệu thông thường vẫn có thể trả **200 OK** dù chưa chứa toàn bộ collection.

## 6. Server xác định `hasNext` thế nào mà không COUNT toàn bộ?

Với dữ liệu truy vấn theo thứ tự ổn định, một kỹ thuật phổ biến là **lấy thêm một phần tử**:

1. Client gửi `limit=N`.
2. Server thực hiện truy vấn trả tối đa **N+1** mục trong phạm vi lọc, quyền và thứ tự tương ứng.
3. Nếu nhận được **N+1** mục, chỉ trả **N** mục đầu và đặt `hasNext=true`.
4. Nếu nhận được **tối đa N** mục, trả tất cả và đặt `hasNext=false`.
5. Cursor kế tiếp, nếu có, được tạo từ **mục cuối cùng thật sự trả cho client**, không phải mục thứ N+1.

~~~text
queryLimit = requestedLimit + 1
rows = loadInStableOrder(queryLimit, filters, authorizedScope, cursor)
hasNext = (rows.size > requestedLimit)
visibleRows = rows.take(requestedLimit)

nextCursor = null
if hasNext:
    lastVisible = visibleRows.last
    nextCursor = encodeOpaqueCursor(
        sortKey = (lastVisible.createdAt, lastVisible.id),
        filters = filters,
        scope = authorizedScope,
        version = cursorVersion
    )

return {
    data: visibleRows,
    page: {
        limit: requestedLimit,
        returned: visibleRows.size,
        hasNext: hasNext,
        nextCursor: nextCursor
    },
    links: {
        next: nextCursor == null ? null : buildNextUrl(nextCursor, filters)
    }
}
~~~

Đây là **giả mã**, không phải thư viện có thể chạy ngay. Điều kiện `rows.size > N` chỉ chính xác khi truy vấn **đã áp đầy đủ scope, filter và điều kiện visibility** trước khi overfetch. Nếu kiểm tra quyền sau khi lấy N+1 phần tử, server có thể trả sai `hasNext` và trang ngắn gây mất dữ liệu hiển thị.

### Ví dụ đúng bội số page size

Nếu tập kết quả chỉ có 4 bản ghi và `limit=2`:

- Trang 1: lấy thử tối đa 3 bản ghi, nhận 3 → trả 2, `hasNext=true`.
- Trang 2: lấy thử tối đa 3 bản ghi kể từ cursor, chỉ nhận 2 → trả 2, `hasNext=false`.

Client dừng sau **hai trang**, không cần gửi request thứ ba để lấy mảng rỗng.

### Tính đúng khi backend đặc thù

Nếu backend chỉ cung cấp API trang tiếp theo, một continuation token hoặc cơ chế lọc khác, server có thể dùng chính token/flag của backend thay cho N+1. **Không cố áp N+1 bằng mọi giá**: mục tiêu là tạo điều kiện kết thúc rõ ràng, không phải bắt buộc dùng một thuật toán truy vấn cụ thể.

## 7. Offset pagination: metadata dễ hiểu nhưng có giới hạn

Với `page` và `size`:

~~~http
GET /api/orders?status=PAID&page=2&size=20 HTTP/1.1
Host: api.example.test

~~~

Giả sử **page đánh số từ 0**, server có thể truy vấn:

~~~sql
SELECT id, status, created_at
FROM orders
WHERE tenant_id = :tenant_id
  AND status = 'PAID'
ORDER BY created_at DESC, id DESC
LIMIT :size_plus_one OFFSET :page_times_size;
~~~

Ở đây lấy `size+1` để xác định `hasNext` mà không bắt buộc đếm tổng. URL trang kế tiếp có thể là `?page=3&size=20&status=PAID`.

### Khi nào offset phù hợp?

- Dữ liệu tương đối nhỏ hoặc ít biến động trong quá trình duyệt.
- Giao diện cần chọn trang số 1/2/3, nhảy tới số trang bất kỳ.
- Có nhu cầu công bố `totalItems` hoặc `totalPages` đã được đánh giá chi phí.

### Hạn chế của offset

Giả sử trang đầu trả IDs `[109,108]` theo thứ tự mới nhất → cũ nhất. Trước khi client gọi `OFFSET 2`, một đơn mới `110` được thêm vào đầu danh sách. Thứ tự trở thành `[110,109,108,...]`; trang tiếp theo `OFFSET 2` có thể trả `108` lần nữa. **Duplicate giữa các trang** xuất hiện dù SQL của từng trang đúng.

Ngược lại, khi dữ liệu ở đầu danh sách bị xóa hoặc thay đổi thứ tự, offset có thể **bỏ qua** bản ghi chưa được đọc. OFFSET rất sâu cũng có thể tốn chi phí quét/bỏ qua nhiều hàng trên một số database.

Không có nghĩa offset luôn sai: nó hợp lý cho nhiều màn hình quản trị nhỏ. Nhưng với **feed lớn và cập nhật liên tục**, nên cân nhắc keyset/cursor.

## 8. Keyset/cursor pagination: tiếp tục từ một mốc sắp xếp

**Keyset pagination** lấy trang tiếp theo dựa trên **giá trị khóa sắp xếp của phần tử cuối trang trước**, thay vì đếm số hàng đã bỏ qua. Với đơn hàng sắp theo:

~~~sql
ORDER BY created_at DESC, id DESC
~~~

Ta dùng cặp **`(created_at, id)`** làm khóa đầy đủ. `created_at` có thể trùng, nên `id` đóng vai trò **tie-breaker duy nhất** để bảo đảm thứ tự xác định. `id` phải có kiểu và quy tắc so sánh phù hợp với database; ví dụ ở đây là số nguyên.

### Truy vấn trang đầu

~~~sql
SELECT id, status, created_at
FROM orders
WHERE tenant_id = :tenant_id
  AND status = :status
ORDER BY created_at DESC, id DESC
LIMIT :limit_plus_one;
~~~

### Truy vấn trang tiếp

~~~sql
SELECT id, status, created_at
FROM orders
WHERE tenant_id = :tenant_id
  AND status = :status
  AND (
       created_at < :cursor_created_at
       OR (created_at = :cursor_created_at AND id < :cursor_id)
  )
ORDER BY created_at DESC, id DESC
LIMIT :limit_plus_one;
~~~

Điều kiện **nhỏ hơn** phù hợp với thứ tự **DESC** đang dùng. Khi đổi sang ASC, đổi khóa hoặc thêm quy tắc NULL, điều kiện cursor phải đổi tương ứng. Nếu sort động cho phép nhiều cột hoặc hướng khác nhau, cần **allowlist các kiểu sắp xếp** và dựng điều kiện keyset đúng cho từng kiểu; không ghép tên cột không đáng tin từ query string vào SQL.

### Minh họa traversal

Giả sử các bản ghi PAID có thứ tự:

| Vị trí | `created_at` (UTC) | `id` |
|---:|---|---:|
| 1 | 10:07 | 109 |
| 2 | 10:06 | 108 |
| 3 | 10:06 | 107 |
| 4 | 10:05 | 106 |
| 5 | 10:04 | 105 |
| 6 | 10:04 | 104 |
| 7 | 10:03 | 103 |

Với `limit=3`:

1. **Trang 1:** `[109,108,107]`; `hasNext=true`; cursor mang mốc `(10:06,107)`.
2. **Trang 2:** `[106,105,104]`; `hasNext=true`; cursor mang mốc `(10:04,104)`.
3. **Trang 3:** `[103]`; `hasNext=false`; `next=null`.

Không mất bản ghi 107/104 do timestamp trùng vì cặp `(created_at,id)` tạo thứ tự toàn phần trong tập dữ liệu đã giả định.

### Cursor nên được thiết kế thế nào?

Một cursor logic có thể chứa:

~~~json
{
  "v": 1,
  "lastCreatedAt": "2026-11-18T10:04:00Z",
  "lastId": 104,
  "sort": "createdAt:desc,id:desc",
  "filterHash": "sha256-of-canonical-filters",
  "scopeId": "tenant-27",
  "expiresAt": "2026-11-18T11:04:00Z"
}
~~~

Đây chỉ là **payload logic minh họa**, không phải token nên trả nguyên văn cho client. Trên thực tế, server nên phát token **opaque, chống sửa đổi** (ví dụ mã hóa ký tự URL-safe kèm chữ ký/HMAC hoặc token được lưu ở server); nếu có dữ liệu nhạy cảm, cân nhắc **mã hóa**, bởi Base64URL và chữ ký **không che giấu nội dung**.

Các trường quan trọng:

- **Phiên bản format** để có thể nâng cấp cursor.
- **Khóa sort cuối** để lấy trang tiếp đúng thứ tự.
- **Dấu vết query** (lọc, sắp xếp và các tham số ảnh hưởng tập kết quả) để phát hiện client dùng cursor với truy vấn khác.
- **Scope/tenant** và kiểm tra quyền **tại từng request**, không tin token như giấy phép truy cập.
- **Hạn dùng** nếu cần kiểm soát TTL, session hoặc snapshot.
- **Snapshot marker** nếu hệ thống thực sự bảo đảm duyệt trên một phiên bản dữ liệu nhất quán.

Một cursor hợp lệ với filter `status=PAID` không được âm thầm áp dụng cho `status=CANCELLED`. Server có thể trả **400 Bad Request** với problem type `invalid-cursor` hoặc `cursor-query-mismatch`; cursor hết hạn có thể dùng **400** hoặc **410 Gone** theo hợp đồng đã công bố. Không có một HTTP status bắt buộc riêng cho mọi loại lỗi cursor.

## 9. Dữ liệu thay đổi trong khi duyệt: “hết trang” có nghĩa chính xác gì?

Đây là phần dễ bị bỏ qua khi thiết kế collection API.

### Duyệt trên tập dữ liệu động

Tại thời điểm lấy trang đầu, có 100 đơn. Trong lúc client đang đọc các trang:

- Một đơn mới được thêm.
- Một đơn chuyển từ PAID sang CANCELLED.
- Một đơn cũ bị xóa.
- Một tác vụ nhập liệu bổ sung đơn có timestamp cũ.

Khi ấy **tập kết quả đã thay đổi**, nên `hasNext=false` nghĩa là **theo phép truy vấn và mốc mà server đang áp dụng, không còn trang tiếp theo tại thời điểm đó**; nó **không tuyên bố collection vĩnh viễn không có đơn mới**.

Keyset làm giảm một số lỗi dịch chuyển trang của offset, nhưng **không tạo snapshot nhất quán một cách tự động**. Ví dụ bản ghi có khóa sắp xếp cũ được thêm sau khi client lấy trang đầu vẫn có thể xuất hiện ở trang sau; bản ghi bị xóa có thể biến mất khỏi traversal.

### Ba mức cam kết nhất quán

| Mô hình | Hợp đồng | Trường hợp dùng |
|---|---|---|
| **Live traversal / best effort** | Mỗi trang phản ánh dữ liệu đang thấy; không bảo đảm snapshot xuyên nhiều request | Feed, UI danh sách, dữ liệu cập nhật thường xuyên |
| **High-water mark** | Giới hạn kết quả theo mốc như `createdAt <= asOf` | Giảm ảnh hưởng của mục mới có timestamp tăng dần; không ngăn backfill/sửa/xóa |
| **Snapshot/version cố định** | Các trang cùng truy vấn một tập đã đóng băng hoặc phiên bản dữ liệu cụ thể | Export, đối soát, báo cáo cần đầy đủ/tái lập |

**High-water mark không phải bằng chứng snapshot.** Nếu hệ thống cho phép backdate, update hoặc delete, thêm `createdAt <= asOf` không đủ để bảo đảm client nhận đúng một tập bản ghi bất biến.

Muốn export chính xác, có thể tạo một **job export** trên snapshot vật lý, dùng MVCC snapshot có vòng đời và giới hạn phù hợp, hoặc lưu danh sách ID/manifest cố định. Cần tính chi phí giữ snapshot và timeout; không nên giữ transaction database dài hàng giờ qua nhiều request HTTP mà không đánh giá tác động.

### Total count và snapshot

Nếu `totalItems=100` được tính ở trang đầu, các trang sau có thể không cộng thành đúng 100 khi tập dữ liệu thay đổi. Nếu nghiệp vụ cần báo cáo “đã export đúng 100/100”, hãy dùng **snapshot và đối soát**; không suy tính đúng từ một total count được tính riêng.

## 10. Thiết kế next link giữ nguyên ý nghĩa truy vấn

Giả sử client yêu cầu:

~~~http
GET /api/orders?status=PAID&sort=createdAt:desc&limit=20 HTTP/1.1
Host: api.example.test

~~~

Trang sau phải tiếp tục **cùng tập lọc, cùng thứ tự và cùng phạm vi phân quyền**:

~~~text
/api/orders?status=PAID&sort=createdAt%3Adesc&limit=20&after=c_v1_next
~~~

Nếu server chỉ trả `?after=c_v1_next` mà quên `status=PAID`, client có thể duyệt lẫn đơn khác trạng thái. Nếu client đổi `sort` giữa hai trang, cursor cũ có thể không còn ý nghĩa.

### Các nguyên tắc tạo link

1. **Không bắt client tự ghép cursor vào URI.** Ưu tiên next URL có thể gọi trực tiếp.
2. **Giữ các filter và sort ảnh hưởng kết quả**, chuẩn hóa encoding của các query parameter.
3. **Không đưa access token hoặc secret vào URL.** Client gửi credentials theo cơ chế xác thực ban đầu.
4. **Không thay quyền truy cập bằng cursor.** Mọi request trang sau vẫn phải kiểm tra tenant, resource và authorization.
5. **Không tạo URL từ host header chưa xác thực.** Nếu cần absolute links, dùng base URL đáng tin cậy theo cấu hình hoặc proxy tin cậy.
6. **Giới hạn kích thước cursor/link** để tránh URL quá dài, log tràn hoặc vượt giới hạn gateway.
7. **Không tạo vòng lặp:** next cursor phải tiến theo thứ tự hoặc biểu thị một trạng thái tiếp tục rõ ràng của backend.

### Nếu người dùng đổi filter giữa chừng?

Người dùng có thể thay `status=PAID` thành `status=SHIPPED` trên UI. Cách an toàn là **bỏ cursor cũ và bắt đầu trang đầu của truy vấn mới**. Server cũng phải từ chối một cursor không khớp điều kiện truy vấn thay vì âm thầm trộn dữ liệu.

### Giới hạn bảo mật của next links

Với một SDK hoặc backend tự động đi theo URL từ response, cần xác định **base origin được phép**; không tự chuyển **Authorization** header sang một host bất kỳ được đưa vào `next`, vì có thể làm rò token. Các liên kết API được coi là dữ liệu đầu vào cần kiểm tra, đặc biệt khi có reverse proxy hoặc dữ liệu metadata do bên thứ ba tạo.

## 11. HTTP status, cache, ETag và quyền xem collection

### Trạng thái HTTP phù hợp

| Tình huống | Phản hồi đề xuất |
|---|---|
| Trang hợp lệ có dữ liệu | **200 OK** với body data/metadata/links |
| Collection hợp lệ nhưng rỗng | **200 OK** với `data: []`, `next: null` |
| `limit=0`, vượt giới hạn hoặc sort không hợp lệ | **400 Bad Request** nếu API chọn từ chối |
| Cursor sai định dạng hoặc không đúng query | **400 Bad Request** và lỗi có cấu trúc |
| Cursor hết hạn | **400** hoặc **410 Gone** theo hợp đồng, kèm hướng dẫn bắt đầu lại |
| Chưa xác thực | **401 Unauthorized** theo cơ chế HTTP authentication |
| Không có quyền collection | **403 Forbidden** hoặc **404** theo chính sách không tiết lộ |
| Bị giới hạn tốc độ đọc nhiều trang | **429 Too Many Requests**, có thể kèm `Retry-After` |
| Hệ thống tạm quá tải | **503 Service Unavailable** theo phạm vi lỗi |

Đừng dùng **416 Range Not Satisfiable** để diễn đạt “đã hết trang offset/cursor” trừ khi API thực sự triển khai HTTP Range với ngữ nghĩa phù hợp. Đừng dùng **204** cho trang rỗng nếu hợp đồng client cần biết metadata kết thúc.

### Cache khi kết quả phụ thuộc người dùng

URL cùng `/api/orders?limit=20` có thể trả tập đơn hoàn toàn khác theo tenant/authorization. Vì vậy:

- Với dữ liệu nhạy cảm hoặc thay đổi nhanh, **Cache-Control: private, no-store** là lựa chọn bảo thủ để tránh lưu bản sao; chỉ cần **no-store** đã truyền đạt việc không được lưu.
- Nếu muốn caching có kiểm soát, cần thiết kế **cache key**, phân vùng theo người dùng/tenant, `Vary` thích hợp, thời hạn hợp lệ và chính sách vô hiệu hóa. Không để shared cache phát tán dữ liệu giữa tenant.
- **ETag** có thể dùng để kiểm tra lại một biểu diễn trang, nhưng chỉ hợp lệ cho **đúng URI, filter, sort, scope và phiên bản dữ liệu**. ETag của một trang không mặc nhiên bảo đảm traversal nhiều trang có snapshot nhất quán.

**Pagination và HTTP caching là hai bài toán khác nhau.** Một `next` link không thay thế `ETag/If-None-Match`, và một response 304 của trang hiện tại không có nghĩa collection không còn thay đổi ở những trang khác.

## 12. Thiết kế Java/Spring: response envelope và Link header

Ví dụ sau áp dụng cho **Spring Framework 6 / Spring Boot 3** hoặc công nghệ tương đương. Nó tập trung vào **hợp đồng trang** và **cách sinh next link**; lớp truy vấn phải chịu trách nhiệm tenant isolation, kiểm tra cursor và lấy `limit+1` bản ghi đúng thứ tự.

### Các kiểu dữ liệu phản hồi

~~~java
import java.time.Instant;
import java.util.List;

record OrderView(long id, String status, Instant createdAt) {}

record PageInfo(
        int limit,
        int returned,
        boolean hasNext,
        String nextCursor) {}

record PageLinks(String self, String next) {}

record OrderPage(
        List<OrderView> data,
        PageInfo page,
        PageLinks links) {}

// Bộ đọc chịu trách nhiệm phân quyền theo Principal,
// xác thực scope của cursor, sort ổn định và truy vấn limit+1.
record PageSlice(List<OrderView> items, String nextCursor) {}
~~~

**Quy ước:** `nextCursor == null` biểu thị không có trang sau; đây là kết quả của kiểm tra N+1 hoặc continuation của nguồn dữ liệu, không phải suy luận từ việc `items.size() < limit` ngay tại controller.

### Controller minh họa

~~~java
import java.security.Principal;
import org.springframework.http.CacheControl;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;
import org.springframework.web.servlet.support.ServletUriComponentsBuilder;

@RestController
class OrdersController {
    private final OrderQueryService service;

    OrdersController(OrderQueryService service) {
        this.service = service;
    }

    @GetMapping("/api/orders")
    ResponseEntity<OrderPage> list(
            Principal principal,
            @RequestParam(defaultValue = "20") int limit,
            @RequestParam(required = false) String status,
            @RequestParam(required = false) String after) {

        if (limit < 1 || limit > 100) {
            throw new ResponseStatusException(
                    HttpStatus.BAD_REQUEST,
                    "limit phải trong khoảng 1..100");
        }

        PageSlice slice = service.findPage(
                principal, status, after, limit);
        boolean hasNext = slice.nextCursor() != null;

        var base = ServletUriComponentsBuilder.fromCurrentRequest()
                .replaceQueryParam("limit", limit);
        String self = base.build().encode().toUriString();
        String next = null;

        if (hasNext) {
            next = base.replaceQueryParam("after", slice.nextCursor())
                    .build().encode().toUriString();
        }

        OrderPage body = new OrderPage(
                slice.items(),
                new PageInfo(
                        limit, slice.items().size(),
                        hasNext, slice.nextCursor()),
                new PageLinks(self, next));

        var response = ResponseEntity.ok()
                .cacheControl(CacheControl.noStore());
        if (next != null) {
            response.header(
                    HttpHeaders.LINK, "<" + next + ">; rel=\"next\"");
        }
        return response.body(body);
    }
}
~~~

`OrderQueryService` trong snippet là **dependency nghiệp vụ** của ứng dụng, không phải class Spring có sẵn; nó trả `PageSlice` và phải xác thực `Principal`, bộ lọc và cursor theo chính sách. Ví dụ tập trung vào controller, nên chưa có các class database, security và cursor codec đủ để chạy độc lập.

**Lưu ý triển khai thực tế:**

- Chỉ dùng thông tin proxy khi có cấu hình **trusted forwarded headers**; nếu không, xây absolute URI bằng base URL đáng tin cậy của ứng dụng để tránh host poisoning.
- Cần kiểm tra encoding thực tế của query khi có ký tự Unicode, dấu `+`, `%` hoặc URL đã được encode; việc xây URL nên được kiểm thử qua gateway.
- Nên có lớp xử lý lỗi cursor trả **Problem Details** thay vì exception 500.
- Controller không tự ghép SQL từ `sort` hoặc query string không tin cậy.
- `Principal` phải được ánh xạ tới tenant/scope có quyền thật; **không dùng tenantId do client tự khai để thay thế authorization**.
- Khi có `next=null`, không thêm Link `rel="next"` và giữ `hasNext=false`.

### Bộ đọc dùng keyset và N+1

Lớp service có thể làm theo quy tắc:

~~~text
findPage(principal, statusFilter, rawCursor, limit):
    tenant = resolveAuthorizedTenant(principal)
    filter = validateAndNormalize(statusFilter)
    cursor = decodeValidateAndBind(
        rawCursor, tenant, filter, fixedSort, currentUserScope)

    rows = database.query(
        tenant = tenant,
        status = filter,
        olderThan = cursor.lastKeyOrNull,
        orderBy = createdAt DESC, id DESC,
        limit = limit + 1)

    hasNext = rows.size > limit
    visible = rows.take(limit)
    next = hasNext
        ? signCursor(visible.last.key, tenant, filter, fixedSort)
        : null
    return PageSlice(visible, next)
~~~

Để truy vấn hiệu quả, cân nhắc chỉ mục phù hợp với `tenant_id, status, created_at DESC, id DESC`, nhưng phải đo trên loại database thực tế và tập filter được hỗ trợ. Không thêm index theo mọi kết hợp một cách mù quáng vì index có chi phí ghi và dung lượng.

## 13. Đặc tả OpenAPI 3.1 cho metadata và next links

~~~yaml
openapi: 3.1.0
info:
  title: Orders API
  version: 1.0.0
paths:
  /api/orders:
    get:
      summary: Liệt kê đơn hàng theo trang
      parameters:
        - name: status
          in: query
          required: false
          schema:
            type: string
            enum: [PAID, SHIPPED, CANCELLED]
        - name: limit
          in: query
          required: false
          schema:
            type: integer
            minimum: 1
            maximum: 100
            default: 20
        - name: after
          in: query
          required: false
          description: Opaque cursor từ liên kết next của trang trước
          schema:
            type: string
      responses:
        '200':
          description: Trang kết quả, kể cả trang rỗng
          headers:
            Link:
              description: Liên kết rel=next khi còn trang sau
              schema:
                type: string
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/OrderPage'
        '400':
          description: limit, filter hoặc cursor không hợp lệ
          content:
            application/problem+json:
              schema:
                type: object
        '401':
          description: Chưa xác thực
        '403':
          description: Không có quyền truy cập collection
        '429':
          description: Vượt hạn mức gọi API
components:
  schemas:
    OrderPage:
      type: object
      required: [data, page, links]
      properties:
        data:
          type: array
          items:
            type: object
            required: [id, status, createdAt]
            properties:
              id:
                type: integer
                format: int64
              status:
                type: string
              createdAt:
                type: string
                format: date-time
        page:
          type: object
          required: [limit, returned, hasNext, nextCursor]
          properties:
            limit:
              type: integer
              minimum: 1
            returned:
              type: integer
              minimum: 0
            hasNext:
              type: boolean
            nextCursor:
              type: [string, 'null']
        links:
          type: object
          required: [self, next]
          properties:
            self:
              type: string
              description: URI reference của trang hiện tại
            next:
              type: [string, 'null']
              description: URI reference của trang kế tiếp hoặc null
~~~

Đây là **profile hợp đồng minh họa**, không phải định dạng bắt buộc cho REST API. Nếu API quyết định dùng `cursor` thay `after`, hoặc trả `totalItems`, cần sửa tài liệu và test cùng lúc. Không khai báo `last`, `totalPages` khi backend không bảo đảm có thể cung cấp chính xác.

### Tài liệu còn cần giải thích

- Thứ tự mặc định **`createdAt DESC, id DESC`** và quy tắc tie-breaker.
- `limit` bị **từ chối hay clamp** khi vượt giới hạn.
- Cursor là **opaque**, có thể hết hạn, ràng buộc filter/scope và cần bắt đầu lại khi sai.
- `links.next=null` **cùng `hasNext=false`** là điều kiện kết thúc.
- Mức **nhất quán** khi dữ liệu bị thêm/xóa/cập nhật trong lúc duyệt.
- Có hay không **snapshot/total chính xác**, và quy tắc dữ liệu đến muộn.
- Rate limit, cache, quyền đọc collection và các header cần thiết.

OpenAPI mô tả hình dạng response, nhưng không tự thay cho **mô tả ngữ nghĩa traversal** ở trên.

## 14. Client duyệt nhiều trang an toàn

### Luồng tổng quát

~~~mermaid
flowchart TD
    A["Bắt đầu với URL collection + filter + limit"] --> B["GET và xác thực response"]
    B --> C{"HTTP success, schema hợp lệ?"}
    C -- "Không" --> E["Xử lý 401/403/429/5xx/cursor error theo contract"]
    C -- "Có" --> D["Xử lý data của trang hiện tại"]
    D --> F{"links.next != null?"}
    F -- "Không" --> G["Kết thúc traversal"]
    F -- "Có" --> H["Kiểm tra next URL, vòng lặp và ngân sách"]
    H --> B
~~~

### Thuật toán tham khảo cho SDK

~~~text
url = "/api/orders?status=PAID&limit=100"
seenUrls = Set()
maxPages = 10_000
pagesRead = 0

while url != null:
    if pagesRead >= maxPages or url in seenUrls:
        fail("Pagination loop/budget exceeded")

    assertAllowedApiOrigin(url)
    seenUrls.add(url)

    response = authenticatedGET(url)
    if response.status == 429:
        obeyRetryAfterWithBackoffAndRetryBudget()
        continueWithSameUrl()
    if response.status is not 200:
        failOrRecoverAccordingToContract(response)

    page = parseAndValidateSchema(response.body)
    assert(page.page.returned == page.data.size)
    assert(page.page.hasNext == (page.links.next != null))

    for item in page.data:
        consume(item)

    pagesRead += 1
    url = page.links.next
~~~

**Đây là giả mã**, không phải SDK hoàn chỉnh. Nếu `consume(item)` có side effect, cần idempotency hoặc lưu checkpoint để một lần chạy lại không xử lý trùng. Trước khi dùng next URL, backend client cần kiểm tra **scheme/host được phép** và không gửi token cho origin lạ. Nếu API dùng relative URI, client phải phân giải an toàn dựa trên base URL đã cấu hình.

### Vì sao cần bảo vệ vòng lặp?

Một bug ở server có thể phát lại chính cùng một next URL hoặc cursor không tiến. Một SDK không giới hạn số trang có thể:

- Gửi request vô hạn, gây chi phí và rate limiting.
- Lặp dữ liệu trong file export hoặc báo cáo.
- Chặn thread và tiêu thụ bộ nhớ.

Client nên có **seen cursor/URL, max pages, max items, thời hạn tổng, retry budget** và khả năng dừng có thông báo rõ. Server vẫn chịu trách nhiệm xuất next link đúng; các giới hạn client là **phòng vệ bổ sung**, không bào chữa cho bug của server.

### Nếu cursor hết hạn giữa chừng?

API nên trả problem type rõ như `cursor-expired`, cùng cách bắt đầu lại. Client không nên tự thay một vài byte của cursor để cố tiếp tục. Với màn hình danh sách, có thể khởi động traversal mới và hiển thị cảnh báo dữ liệu đã đổi. Với export cần tính đúng, phải tạo **snapshot hoặc một export job có checkpoint**, không tự nối nửa đầu traversal cũ với nửa sau traversal mới rồi tuyên bố hoàn tất.

## 15. Kiểm thử bằng curl, Spring MockMvc và dữ liệu biến động

### Kiểm thử trang đầu và Link header

~~~bash
curl -i \
  -H 'Authorization: Bearer <test-token>' \
  'https://api.example.test/api/orders?status=PAID&limit=2'
~~~

Khi response có `next`, hãy dùng đúng URL đó cho lần gọi tiếp theo; không tự suy ra `after` bằng cách đếm số mục. Trên môi trường thử nghiệm, cố định dataset để xác minh `hasNext`, cursor và thứ tự.

### Ma trận contract test thiết yếu

| Kịch bản | Kết quả cần kiểm tra |
|---|---|
| Collection không có phần tử | 200, `data=[]`, `returned=0`, `hasNext=false`, `next=null` |
| Ít hơn limit mục | Không phát next link; metadata đúng |
| Đúng bằng limit mục, **không còn dữ liệu** | **Không** phát next link dù trang đầy |
| Có limit+1 mục | Trang đầu đúng limit và có next |
| Nhiều trang, timestamp trùng | Duyệt đủ mỗi ID đúng một lần trên dataset cố định |
| Filter + sort + limit | Next link giữ nguyên điều kiện |
| Client đổi filter khi giữ cursor cũ | Lỗi cursor mismatch, không trộn dữ liệu |
| `limit=0` hoặc quá max | 400 hoặc clamp đúng contract |
| Cursor giả mạo/sai chữ ký | Từ chối, không 500 hoặc lộ dữ liệu |
| Cursor hết hạn | Error được tài liệu hóa; có hướng dẫn bắt đầu lại |
| Tenant A dùng cursor của tenant B | Không đọc được dữ liệu B |
| Không có quyền đọc một phần dữ liệu | HasNext tính trên tập đã được phép xem |
| Thêm item vào đầu danh sách giữa hai trang | Hành vi phù hợp cam kết live/snapshot |
| Xóa item giữa hai trang | Không tuyên bố snapshot nếu không có |
| Proxy xây URL khác host/scheme | Next không rò sang host lạ, HTTPS đúng |
| CORS đọc HTTP Link | Header expose đúng nếu frontend cần |
| Client theo next hết dataset | Dừng hữu hạn, không request vòng lặp |
| 429 giữa các trang | Client retry đúng URL, có backoff, không nhân đôi side effect |

### Ví dụ MockMvc kiểm tra trang cuối

Đoạn test sau là **khung minh họa**: cần có controller và bộ dữ liệu test/fixture giả định.

~~~java
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class OrdersPaginationContractTest {
    @Autowired MockMvc mvc;

    @Test
    void lastFullPageHasNoNextLink() throws Exception {
        // Fixture: dataset có đúng 4 bản ghi được phép, limit=2,
        // và cursor hợp lệ trỏ tới đầu trang thứ hai.
        String validSecondPageCursor = "fixture-cursor-page-2";

        mvc.perform(get("/api/orders")
                .param("limit", "2")
                .param("after", validSecondPageCursor))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.data.length()").value(2))
            .andExpect(jsonPath("$.page.returned").value(2))
            .andExpect(jsonPath("$.page.hasNext").value(false))
            .andExpect(jsonPath("$.links.next").value(
                    org.hamcrest.Matchers.nullValue()))
            .andExpect(header().doesNotExist("Link"));
    }
}
~~~

**Chú ý:** `fixture-cursor-page-2` là dữ liệu test, không phải cursor production tự giải mã được. Test thật cần **seed dữ liệu, cấp token/scope hợp lệ và tạo cursor bằng cùng codec với server**. Khi dùng Spring Security, phải cấu hình authentication/mock principal để không dừng ở 401 trước controller.

### Test tính nhất quán

Với dataset cố định, kiểm tra **union các trang bằng đúng tập được lọc**, không trùng ID và đúng thứ tự. Với dataset có ghi đồng thời, test theo **cam kết cụ thể**:

- Nếu là **live traversal**, kiểm tra không trả 500, không vòng lặp, không tiết lộ dữ liệu ngoài quyền; ghi nhận những thay đổi có thể khiến tập kết quả khác.
- Nếu cam kết **snapshot**, kiểm tra output đúng danh sách/phiên bản đã đóng băng, kể cả khi thêm, sửa hoặc xóa bản ghi trong database nguồn.

Không viết test mặc định “keyset luôn không mất/không trùng dù có update đồng thời” khi hệ thống chưa có snapshot hoặc quy tắc xử lý version tương ứng.

## 16. Tình huống thiết kế: lịch sử giao dịch ví điện tử

### Bối cảnh giả định

Một ứng dụng ví điện tử cho người dùng xem lịch sử giao dịch qua:

~~~http
GET /api/transactions?from=2026-11-01&to=2026-11-18&limit=50 HTTP/1.1
Host: api.example.test

~~~

Dữ liệu có thể rất lớn; khách hàng truy cập từ điện thoại; hệ thống có thêm giao dịch mới khi người dùng đang cuộn danh sách. Người dùng muốn xem các giao dịch gần đây trước, còn bộ phận đối soát cần export chính xác toàn bộ giao dịch trong một kỳ.

### Tách hai nhu cầu khác nhau

**Danh sách trong ứng dụng:** dùng cursor/keyset, sắp theo `occurredAt DESC, id DESC`, tối đa 50 phần tử/trang, phản hồi `hasNext` và `links.next`, quyền theo tài khoản đã xác thực. Có thể chấp nhận **live traversal** nếu tài liệu giải thích dữ liệu có thể đổi và UI hỗ trợ refresh.

**Export phục vụ đối soát:** không nên chỉ gọi live list API hết mọi trang rồi giả định đó là snapshot. Tạo một **export job bất đồng bộ** trên tập nguồn đã chốt, có `jobId`, snapshot/watermark/manifest, kiểm tra số bản ghi và checksum khi cần; cho tải file khi trạng thái hoàn tất. Dữ liệu đã xuất phải có phạm vi và phiên bản có thể chứng minh.

### Lựa chọn metadata

| Trường | Danh sách điện thoại | Export đối soát |
|---|---|---|
| `limit` | 50, giới hạn tối đa theo chính sách | Batch size nội bộ, không nhất thiết lộ cho UI |
| `hasNext` / `next` | Bắt buộc trong contract đang chọn | Có thể dùng token/checkpoint xử lý job |
| `totalItems` | Có thể bỏ | Chỉ công bố sau đối soát trên snapshot |
| `asOf` | Tùy chọn, cần nói rõ giới hạn | Có snapshot/manifest thực sự |
| `status` | Trạng thái giao dịch/hiển thị | Trạng thái job: PENDING/RUNNING/COMPLETED/FAILED |
| Authorization | Kiểm tra mỗi request | Kiểm tra lúc tạo và tải kết quả, hạn chế URL tải |
| Audit | Ghi truy cập phù hợp | Theo dõi job, người yêu cầu, kết quả, retention |

**Kết luận tình huống:** cùng một collection có thể cần **hai hợp đồng truy vấn**: một cho tương tác có tính cập nhật và một cho kết quả tái lập chính xác. Dùng một loại next cursor cho mọi mục đích dễ tạo ra cam kết sai về tính nhất quán.

## 17. Bài tập thực hành và gợi ý đối chiếu

Một API quản lý sản phẩm công bố:

- **GET /api/products?category=BOOK&limit=3**.
- Sắp theo **`createdAt DESC, id DESC`**, id là số nguyên duy nhất.
- Cursor là opaque, gắn với `category`, sort và tenant.
- Server dùng chiến lược **LIMIT N+1** để tính `hasNext`.
- Trong một test, tập BOOK cố định có bảy ID theo thứ tự: **109, 108, 107, 106, 105, 104, 103**; các ID 108/107 có cùng timestamp, ID 105/104 có cùng timestamp.

### Câu hỏi

1. Trang thứ nhất, thứ hai và thứ ba có `data`, `hasNext` và `next` như thế nào?
2. Nếu collection còn **đúng 6 mục** thay vì 7, trang thứ hai có đủ 3 mục thì có nên tạo trang thứ ba không?
3. Viết response JSON cho **trang cuối** theo hợp đồng của bài, gồm `page` và `links`.
4. Viết truy vấn SQL keyset cho trang kế tiếp khi cursor mang mốc `createdAt=10:04`, `id=104` và thứ tự là DESC/DESC.
5. Client có được lấy cursor của **category=BOOK** rồi gửi với **category=TOY**? Server nên phản hồi thế nào?
6. Khi thêm một sản phẩm có timestamp mới hơn mọi sản phẩm hiện tại giữa trang đầu và trang sau, **offset** và **keyset** có thể khác nhau ra sao?
7. Nếu cần xuất toàn bộ sản phẩm đúng tại thời điểm kiểm kê, **keyset đơn thuần** đã đủ chưa? Cần thêm ràng buộc hoặc cơ chế gì?
8. Đề xuất ít nhất **sáu contract test** và **bốn metric** cho API này.

### Gợi ý lời giải

**Câu 1:** Trang 1 có `[109,108,107]`, `hasNext=true`, cursor từ bản ghi 107; trang 2 `[106,105,104]`, `hasNext=true`, cursor từ 104; trang 3 `[103]`, `hasNext=false`, `next=null`. Server phát link có đủ `category=BOOK&limit=3` và cursor mới ở hai trang đầu.

**Câu 2:** Không. Nếu chỉ có 6 bản ghi, khi lấy thử trang 2 với `LIMIT 4`, server nhận 3 bản ghi và xác định **`hasNext=false`**, dù trang có đúng ba mục.

**Câu 3:** Ví dụ body trang cuối:

~~~json
{
  "data": [{"id": 103, "category": "BOOK"}],
  "page": {
    "limit": 3,
    "returned": 1,
    "hasNext": false,
    "nextCursor": null
  },
  "links": {
    "self": "/api/products?category=BOOK&limit=3&after=c_v1_last",
    "next": null
  }
}
~~~

Không có **Link rel=next** trong header của trang này. Giá trị cursor ở URL self chỉ là minh họa; không liên quan tới token production thật.

**Câu 4:** Điều kiện keyset:

~~~sql
SELECT id, category, created_at
FROM products
WHERE tenant_id = :tenant_id
  AND category = 'BOOK'
  AND (
    created_at < :cursor_created_at
    OR (created_at = :cursor_created_at AND id < 104)
  )
ORDER BY created_at DESC, id DESC
LIMIT 4; -- limit=3, lấy thêm 1
~~~

**Câu 5:** Không nên chấp nhận. Cursor chỉ có nghĩa trong ngữ cảnh category và scope đã ký/ràng buộc. Server có thể trả **400** với problem type **invalid-cursor** hoặc **cursor-query-mismatch**, không trả sản phẩm TOY lẫn BOOK.

**Câu 6:** Offset có thể **trả lặp** một mục vì vị trí đếm bị đẩy xuống. Keyset thường tiếp tục sau khóa cuối đã thấy nên hạn chế loại duplicate do chèn mới ở đầu; tuy nhiên nó **không tự bảo đảm snapshot** khi có update/delete/backfill.

**Câu 7:** Chưa đủ. Cần một **snapshot dữ liệu, versioned export, manifest cố định hoặc cơ chế tương đương** để bảo đảm tập được export không thay đổi. Có thể thêm đối soát số lượng/checksum và audit khi nghiệp vụ yêu cầu.

**Câu 8:** Contract test nên có: collection rỗng, ít hơn limit, đúng bội số limit, N+1, timestamp trùng, filter đổi giữa trang, cursor sai chữ ký/hết hạn, tenant khác, proxy host và client loop detection. Metric nên theo dõi **p95/p99 query latency**, **number of pages/items returned**, **invalid/expired cursor rate**, **429 rate**, **database rows examined/index usage** và tỷ lệ **traversal bất thường**.

## 18. Các lỗi phổ biến và checklist trước khi công bố API

| Phản mẫu | Hậu quả | Cách sửa |
|---|---|---|
| Chỉ trả `data`, không có next/hasNext | Client đoán bằng độ dài trang và có thể gọi vô hạn | Công bố tín hiệu kết thúc chính thức |
| Luôn tạo next nếu `returned == limit` | Trang cuối đầy vẫn sinh link thừa | Overfetch N+1 hoặc dùng continuation token đúng |
| Cursor lấy từ bản ghi N+1 | Bỏ mất bản ghi bị ẩn sau trang trước | Cursor lấy từ **mục cuối đã trả** |
| Chỉ sort `createdAt` khi có timestamp trùng | Đọc lặp hoặc mất bản ghi | Bổ sung tie-breaker duy nhất |
| Trang sau làm mất filter/sort | Kết quả lẫn dữ liệu hoặc sai thứ tự | Sinh URL từ cùng query context |
| Cursor không gắn với tenant/scope | Có nguy cơ đọc dữ liệu ngoài quyền | Ký/ràng buộc cursor và kiểm tra authorization từng trang |
| Giải mã Base64 rồi cho là bảo mật | Lộ metadata và dễ sửa token nếu không ký | Dùng token opaque có integrity; mã hóa nếu nhạy cảm |
| Công bố total luôn chính xác trên dữ liệu live | UI/export hiểu sai số lượng | Bỏ total, đánh dấu ước lượng hoặc dùng snapshot |
| Dùng 206 cho mọi trang bình thường | Trộn với HTTP Range | Dùng 200 cho trang collection thông thường |
| Dùng 404 cho collection rỗng | Client nhầm lỗi endpoint với hết dữ liệu | Dùng 200 và body rỗng có metadata |
| Quên CORS expose Link | Browser không đọc được HTTP Link | Cấu hình expose khi frontend cần |
| Xây absolute next URL từ Host không tin cậy | Host poisoning, rò thông tin | Base URL tin cậy hoặc relative link |
| Caching public cho collection riêng tư | Rò dữ liệu xuyên tenant | Cache-Control và cache key theo scope |
| Client tự gửi token qua mọi URL next | Nguy cơ chuyển credentials sang origin lạ | Kiểm tra origin/scheme trước khi follow |

### Checklist kỹ thuật

- [ ] Có **thứ tự sắp xếp toàn phần và ổn định**, gồm tie-breaker duy nhất.
- [ ] `limit` có giá trị mặc định, min/max, cách từ chối/clamp và phản hồi metadata chính xác.
- [ ] `data`, `returned`, `hasNext`, `nextCursor` và `links.next` không mâu thuẫn.
- [ ] Trang **rỗng**, **ngắn**, **đầy còn tiếp** và **đầy nhưng kết thúc** đều được kiểm thử.
- [ ] Next link bảo toàn **filter/sort/limit** và không yêu cầu client tự sửa cursor.
- [ ] `rel="next"` trong HTTP Link chỉ xuất hiện khi có trang tiếp theo; body và header khớp nhau.
- [ ] Cursor **opaque, chống sửa đổi, gắn quyền và query**, có quy tắc TTL và lỗi rõ ràng.
- [ ] Client hiểu khi nào **dừng**, có bảo vệ lặp URL/cursor và giới hạn tổng lượt gọi.
- [ ] Quyết định **offset hay keyset** dựa trên tính biến động, nhu cầu nhảy trang và hiệu năng.
- [ ] Không hứa snapshot/total chính xác nếu không có cơ chế bảo đảm.
- [ ] Mỗi request trang tiếp theo đều xác thực, phân quyền; cache và URL không làm lộ dữ liệu.
- [ ] Spring/gateway/CORS và OpenAPI mô tả đúng hành vi trên môi trường thực tế.
- [ ] Có contract test với **N+1**, timestamp trùng, filter thay đổi, cursor hết hạn, tenant khác và ghi đồng thời.
- [ ] Theo dõi latency, database load, cursor errors, 429, số trang/traversal và bất thường trong next links.

**Điểm cần nhớ:** Một collection API hoàn chỉnh không chỉ trả một mảng và một giới hạn. Nó còn phải nói **đã trả gì, đi tiếp ra sao và dừng khi nào**. Tín hiệu `next` đáng tin, thứ tự ổn định, cursor được ràng buộc với truy vấn/quyền và cam kết nhất quán trung thực giúp client duyệt dữ liệu mà không phỏng đoán hoặc vô tình truy cập sai phạm vi.

### Tài liệu nền để tham khảo

- **RFC 8288 — Web Linking:** HTTP `Link` header và relation `next`, `prev`.
- **RFC 9110 — HTTP Semantics:** GET, status, nội dung phản hồi và các header HTTP.
- **RFC 9111 — HTTP Caching:** cache key, kiểm soát cache và phản hồi theo ngữ cảnh.
- **OpenAPI Specification 3.1:** query parameters, response schema và response headers.
- **Spring Framework / Spring MVC:** controller mapping, URI builders và kiểm thử MockMvc.
