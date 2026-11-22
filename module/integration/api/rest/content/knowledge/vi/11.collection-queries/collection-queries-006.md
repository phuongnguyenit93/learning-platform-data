# Cursor mờ, phạm vi hiệu lực và bảo vệ khỏi sửa đổi

> **Module:** INTEGRATION_API_REST — học thiết kế REST API theo resource, URI, phương thức và mã trạng thái HTTP, với hợp đồng dữ liệu rõ ràng; thực hành phân trang, cache, idempotency, OpenAPI, xác thực, phân quyền, xử lý lỗi và kiểm thử API bằng Java/Spring hoặc công nghệ tương đương.  
> **Chương:** Truy vấn tập hợp.  
> **Trọng tâm:** Thiết kế **opaque cursor** cho phân trang tập hợp: thứ tự xác định, phạm vi hiệu lực theo bộ lọc và quyền truy cập, thời hạn sử dụng, chống chỉnh sửa token, cùng các đánh đổi về tính nhất quán, bảo mật và hiệu năng.

## 1. Bài toán: trang tiếp theo phải tiếp tục từ đâu?

Một API trả về danh sách đơn hàng cho cửa hàng:

```http
GET /api/orders?status=PAID&size=3 HTTP/1.1
Host: api.example.com
Authorization: Bearer <access-token>
Accept: application/json
```

Ban đầu có các đơn hàng sắp xếp từ mới đến cũ:

| Thứ tự | ID đơn | createdAt |
|---:|---:|---|
| 1 | 105 | 2026-11-18T09:05:00Z |
| 2 | 104 | 2026-11-18T09:04:00Z |
| 3 | 103 | 2026-11-18T09:03:00Z |
| 4 | 102 | 2026-11-18T09:02:00Z |
| 5 | 101 | 2026-11-18T09:01:00Z |

Client lấy trang đầu gồm `105, 104, 103`. Trước khi lấy trang hai, hệ thống có đơn mới `106` ở đầu danh sách. Nếu client dùng `offset=3`, cơ sở dữ liệu có thể trả `103, 102, 101`, khiến `103` xuất hiện hai lần. Nếu có bản ghi ở đầu bị xóa, cách dùng offset có thể **bỏ sót** một đơn.

**Cursor pagination** cho client một dấu mốc: “Tiếp tục sau đơn `103` theo đúng thứ tự và điều kiện truy vấn đã dùng”. Server không cần client biết chi tiết dấu mốc đó. Nó có thể phát hành một **cursor mờ** (*opaque cursor*) để client chỉ việc gửi lại.

Mục tiêu bài học:

1. Giải thích cách cursor khác `page/offset` và vai trò của **keyset/seek pagination**.
2. Thiết kế thứ tự ổn định, có khóa phụ phá hòa, và sinh `nextCursor` đúng vị trí.
3. Nêu rõ **phạm vi hiệu lực** của cursor theo tenant, principal/quyền, bộ lọc, sort, page size, API version và thời hạn.
4. Phân biệt **mờ đối với client**, **chống sửa đổi (integrity)** và **giữ bí mật (confidentiality)**.
5. Thiết kế HMAC hoặc cơ chế lưu trạng thái phía server để phát hiện cursor bị giả mạo; biết khi nào cần mã hóa.
6. Triển khai, tài liệu hóa và kiểm thử với REST API dùng Java/Spring, SQL và OpenAPI.

## 2. Offset pagination và cursor pagination khác gì?

**Offset pagination** thường dùng số trang hoặc vị trí trong danh sách:

```http
GET /api/orders?status=PAID&limit=20&offset=40
```

Server trả các dòng từ vị trí 41 theo thứ tự hiện tại. Dễ triển khai và thuận lợi khi người dùng muốn “đến trang 10”, nhưng có hai hạn chế phổ biến: chi phí bỏ qua nhiều dòng khi offset lớn, và vị trí dòng thay đổi nếu có insert/delete giữa các lần gọi.

**Cursor pagination** dùng một điểm tiếp tục do server phát hành:

```http
GET /api/orders?status=PAID&size=20&cursor=eyJ...
```

Server diễn giải cursor để trả các phần tử **nằm sau một khóa sắp xếp**, thay vì đếm lại từ đầu danh sách. Phương pháp điển hình là **keyset pagination** hay **seek pagination**.

| Tiêu chí | Offset/page number | Cursor/keyset |
|---|---|---|
| Định vị trang tiếp theo | Đếm vị trí từ đầu danh sách | Theo mốc khóa sắp xếp của trang trước |
| Truy vấn trang rất sâu | Có thể tốn chi phí quét/bỏ nhiều dòng | Thường hiệu quả với index và điều kiện seek phù hợp |
| Insert/delete phía trước | Dễ gây trùng/bỏ sót do vị trí dịch chuyển | Thường ổn định hơn khi khóa sắp xếp không đổi |
| Nhảy ngẫu nhiên đến trang N | Thuận lợi | Khó; thường duyệt tuần tự |
| Trả `totalPages` | Tự nhiên hơn nhưng COUNT có thể tốn kém | Không nhất thiết trả tổng số trang |
| Giữ “ảnh chụp” dữ liệu bất biến | Không tự đảm bảo | Cũng **không tự đảm bảo**; cần snapshot riêng nếu nghiệp vụ yêu cầu |
| Mức phụ thuộc vào thứ tự | Cần `ORDER BY` | Cần thứ tự **duy nhất, nhất quán** và điều kiện seek đúng |
| Độ phức tạp API | Nhỏ | Thêm cursor contract, bảo vệ và quản lý hiệu lực |

Không phải API nào cũng cần cursor. Với danh sách nhỏ, ít thay đổi, cần nhảy ngẫu nhiên theo trang, offset có thể phù hợp hơn. Cursor hữu ích với feed, lịch sử sự kiện, nhật ký giao dịch, catalog lớn hoặc danh sách được cập nhật thường xuyên.

## 3. Thứ tự ổn định là nền tảng của cursor

### 3.1. Không chỉ sắp xếp theo một trường có thể trùng

Giả sử nhiều đơn có cùng `created_at`. Nếu chỉ dùng:

```sql
ORDER BY created_at DESC
```

database có thể trả các bản ghi cùng thời điểm theo thứ tự không xác định. Cursor theo mỗi `created_at` có nguy cơ bỏ sót một số dòng cùng thời điểm.

Nên bổ sung một **tie-breaker duy nhất**:

```sql
ORDER BY created_at DESC, id DESC
```

Đối với ví dụ này, cặp khóa `(created_at, id)` tạo ra thứ tự xác định trong tập dữ liệu và phạm vi truy vấn. `id` có thể là UUID hoặc khóa khác có thứ tự so sánh được, nhưng phải xác định rõ cách so sánh tương ứng với index và SQL.

### 3.2. Điều kiện lấy những dòng sau mốc

Nếu trang trước kết thúc tại:

```text
lastCreatedAt = 2026-11-18T09:03:00Z
lastId = 103
```

thì với thứ tự **giảm dần cả hai trường**, câu truy vấn seek cho trang kế tiếp dùng:

```sql
SELECT id, created_at, status, total_amount
FROM orders
WHERE tenant_id = :tenantId
  AND status = :status
  AND (
       created_at < :lastCreatedAt
       OR (created_at = :lastCreatedAt AND id < :lastId)
  )
ORDER BY created_at DESC, id DESC
LIMIT :limitPlusOne;
```

Điều kiện trên chỉ đúng với bộ lọc và thứ tự đã nêu. Nếu đổi sang `ASC`, hoặc kết hợp `ASC/DESC`, phải điều chỉnh phép so sánh cho từng trường. Không thể dùng một predicate seek chung cho mọi sort mà không xét kiểu dữ liệu, `NULLS FIRST/LAST` và cách sắp xếp của database.

### 3.3. Trường sắp xếp nên ổn định

`created_at` và ID thường thích hợp hơn `updated_at`, `status` hoặc `price` nếu mục tiêu là duyệt lịch sử ổn định. Khi thuộc tính dùng để sắp xếp thay đổi giữa hai request, bản ghi có thể đi qua mốc cursor, gây trùng hoặc bị bỏ sót dù dùng keyset.

Ví dụ cursor dựa vào `updated_at DESC`; cập nhật một đơn cũ khiến nó nhảy lên đầu trước khi client lấy trang tiếp theo. Client sẽ không thấy bản ghi mới được sửa trong phần sau mốc. Nếu yêu cầu là **xem tất cả bản ghi đúng một lần theo một ảnh chụp**, cursor thông thường chưa đáp ứng và phải thiết kế snapshot/cơ chế đọc nhất quán riêng.

## 4. Hợp đồng REST API cho cursor mờ

Một API có thể công bố:

```http
GET /api/orders?status=PAID&size=3 HTTP/1.1
Host: api.example.com
Authorization: Bearer <access-token>
Accept: application/json
```

Phản hồi minh họa (token bị rút gọn để dễ đọc):

```http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: private, no-store

{
  "data": [
    {"id": 105, "createdAt": "2026-11-18T09:05:00Z", "status": "PAID"},
    {"id": 104, "createdAt": "2026-11-18T09:04:00Z", "status": "PAID"},
    {"id": 103, "createdAt": "2026-11-18T09:03:00Z", "status": "PAID"}
  ],
  "page": {
    "size": 3,
    "hasMore": true,
    "nextCursor": "v1.eyJ...tQ.K8...oA"
  },
  "links": {
    "next": "/api/orders?status=PAID&size=3&cursor=v1.eyJ...tQ.K8...oA"
  }
}
```

Client lấy trang tiếp:

```http
GET /api/orders?status=PAID&size=3&cursor=v1.eyJ...tQ.K8...oA HTTP/1.1
Host: api.example.com
Authorization: Bearer <access-token>
```

Server giải mã, xác minh và áp dụng cursor. Phản hồi kế tiếp có thể trả `102` và `101`; `hasMore=false`, `nextCursor=null` nếu không còn dữ liệu:

```json
{
  "data": [
    {"id": 102, "createdAt": "2026-11-18T09:02:00Z", "status": "PAID"},
    {"id": 101, "createdAt": "2026-11-18T09:01:00Z", "status": "PAID"}
  ],
  "page": {
    "size": 3,
    "hasMore": false,
    "nextCursor": null
  }
}
```

**Hợp đồng cần nói rõ:**

- `cursor` là chuỗi **mờ**: client không phân tích, sửa, dự đoán hoặc tự sinh token.
- Khi gọi trang tiếp theo, client phải giữ nguyên các tham số có ảnh hưởng đến tập kết quả, hoặc dùng link `next` do server cung cấp.
- `size` có giá trị mặc định và ngưỡng tối đa, chẳng hạn mặc định 20, giới hạn 1–100. Các số là chính sách minh họa.
- `nextCursor=null` nghĩa là **tại thời điểm truy vấn đó** server không thấy trang kế tiếp trong phạm vi mà cursor định nghĩa; không phải lời hứa dữ liệu không bao giờ có thêm.
- Không cam kết số lượng dòng chính xác bằng `size` nếu dữ liệu ít hơn, quyền hiển thị thay đổi hoặc có lọc hậu xử lý.
- `totalCount`/`totalPages` là lựa chọn riêng, có thể tốn truy vấn và không nhất quán với danh sách đang thay đổi. Không nên mặc định phải cung cấp.
- `links.next` nếu có cần được URL-encode đúng, không làm lộ token ngoài nơi dự kiến.

## 5. Cursor “mờ” nghĩa là gì?

**Opaque cursor** là token mà **client không được phụ thuộc vào cấu trúc bên trong**. Server có thể đổi định dạng, thứ tự khóa, thuật toán hoặc chế độ lưu trữ mà vẫn giữ contract bên ngoài.

“Mờ đối với client” **không đồng nghĩa** với “được mã hóa và giữ bí mật”. Ví dụ server có thể mã hóa một JSON thành Base64URL và ký bằng HMAC:

```text
v1.<base64url(JSON-payload)>.<base64url(HMAC-signature)>
```

Client được yêu cầu chỉ truyền nguyên token, nhưng bất kỳ ai nhận được token vẫn có thể **giải mã Base64URL để đọc payload**. Base64URL chỉ mã hóa định dạng văn bản an toàn trong URL, **không phải mã hóa bảo mật**.

Ví dụ payload nội bộ **minh họa**, không phải dữ liệu được công bố cho client:

```json
{
  "v": 1,
  "tenant": "tenant-17",
  "scopeHash": "b1a4...",
  "sort": "createdAt:desc,id:desc",
  "size": 3,
  "after": {
    "createdAt": "2026-11-18T09:03:00Z",
    "id": 103
  },
  "asOf": "2026-11-18T09:06:00Z",
  "exp": "2026-11-18T09:21:00Z"
}
```

Payload đại diện cho **vị trí tiếp tục** và các điều kiện mà vị trí đó còn có ý nghĩa. Có thể giữ một số field dưới dạng hash để giảm lộ thông tin và đơn giản hóa so sánh; việc hash không tự tạo tính bí mật nếu dữ liệu đầu vào dễ đoán. Nếu payload chứa thông tin thực sự nhạy cảm, cần mã hóa có xác thực hoặc lưu cursor phía server.

## 6. Phạm vi hiệu lực: cursor phải gắn với truy vấn nào?

Một cursor sinh từ truy vấn **`status=PAID` của tenant A** không được tự ý dùng cho **`status=CANCELLED`**, tenant B hoặc thứ tự khác. Nếu không ràng buộc, client có thể nhận trang sai, bỏ qua bản ghi, thậm chí làm lộ dữ liệu khi code truy vấn dùng nhầm phạm vi.

### 6.1. Ma trận phạm vi

| Yếu tố | Tại sao cần ràng buộc? | Cách làm |
|---|---|---|
| **Tenant hoặc account** | Ngăn token của tenant A bị hiểu như vị trí của B | Lấy tenant từ danh tính đã xác thực, so với tenant trong token, luôn áp `WHERE tenant_id = ...` |
| **Bộ lọc** | Mốc trang của `PAID` không có ý nghĩa với `CANCELLED` | Chuẩn hóa bộ lọc và so sánh hash/fingerprint đã ký |
| **Thứ tự sắp xếp** | Dấu `<`/`>` tùy sort, tie-breaker | Bind sort vào token; whitelist sort được hỗ trợ |
| **Page size** | Tránh thay đổi semantics/giới hạn tài nguyên giữa các trang | Bind size vào token hoặc chủ động quy định cách đổi size |
| **Phạm vi thời gian/snapshot** | Một mốc có thể thuộc cửa sổ dữ liệu khác | Bind `asOf`/snapshot ID khi có |
| **API/schema version** | Thay đổi ý nghĩa field hoặc encoding khiến token cũ không diễn giải được | Có version của cursor, migration hoặc thời hạn để chuyển đổi |
| **Quyền truy cập** | Quyền có thể bị thu hồi sau trang đầu | **Kiểm tra lại quyền mỗi request**; có thể bind thêm identity/scope tùy hợp đồng |
| **Thời hạn** | Token cũ dễ trở nên sai khi dữ liệu/khóa thay đổi | `exp`/TTL và chính sách lỗi rõ ràng |

Không nhất thiết phải lưu mọi thông tin như tên người dùng, role hay danh sách filter ở dạng plaintext trong token. Có thể dùng fingerprint của cấu hình truy vấn đã chuẩn hóa. **Bảo mật vẫn dựa vào xác thực và phân quyền trên từng request**; cursor không phải vé cho phép truy cập.

### 6.2. Canonicalization trước khi tính fingerprint

Hai truy vấn tương đương về ngữ nghĩa có thể khác cách viết:

```text
?status=PAID&sort=createdAt:desc&size=20
?size=20&sort=createdAt:desc&status=PAID
```

Nếu chỉ hash nguyên query string, hai request này có fingerprint khác dù cùng ý nghĩa. Server nên **chuẩn hóa** trước:

1. Parse query theo schema, kiểm tra field và giá trị hợp lệ.
2. Gán giá trị mặc định rõ ràng, ví dụ `size=20` khi client không gửi.
3. Chuẩn hóa dạng ngày giờ, Unicode, enum, khoảng giá, giá trị boolean theo quy ước.
4. Sắp xếp các filter theo thứ tự khóa cố định; xác định khi nào danh sách giá trị có thứ tự hay không.
5. Gắn sort tường minh, tie-breaker và version vào chuỗi canonical.
6. Tính fingerprint ổn định, ví dụ SHA-256 trên chuỗi canonical đã xác định.

Ví dụ **dạng nội bộ do server tự quy định**:

```text
v=1|resource=orders|status=PAID|sort=createdAt:desc,id:desc|size=20
```

Dùng chuỗi này để kiểm tra scope của các trang. Khi filter/query chuẩn hóa thay đổi, token cũ phải bị từ chối hoặc client bắt đầu lại từ trang đầu theo hành vi đã công bố.

**Lưu ý:** nếu API có khoảng lọc thời gian, tìm kiếm văn bản, quyền theo tài nguyên hoặc nhiều sort, canonicalization phải đi kèm quy tắc chính xác. Không ghép chuỗi tùy ý với delimiter có thể xuất hiện trong input mà không escape; sản phẩm thực tế có thể dùng JSON canonical/typed encoding thay cho chuỗi thủ công.

### 6.3. Đổi size giữa các trang

Có hai phương án hợp lệ:

- **Khóa page size:** token bind `size=20`; request tiếp theo đổi sang `size=100` bị từ chối. Cách này dễ dự đoán và bảo vệ tải.
- **Cho đổi page size có kiểm soát:** server dùng mốc seek cũ nhưng cho phép size mới trong giới hạn, không bind size vào scope hoặc có quy tắc riêng. Phải tài liệu hóa và test.

Trong bài này chọn **khóa page size**. Client nên lấy trang kế tiếp từ `links.next` để giữ tham số đồng nhất.

## 7. Bảo vệ khỏi sửa đổi: ký token, mã hóa hay lưu trạng thái?

### 7.1. Vì sao chỉ Base64 là không đủ?

Nếu token chỉ là:

```text
base64url({"tenant":"tenant-A","afterId":103,"size":20})
```

người nhận token có thể giải mã, sửa `afterId`, `tenant` hoặc `size`, mã hóa lại rồi gửi lên. Dù API vẫn phải phân quyền đúng, việc tin dữ liệu chưa được bảo vệ có thể dẫn tới đọc sai phạm vi, bypass limit hoặc tấn công tiêu tốn tài nguyên.

Phải coi **mọi cursor do client gửi lại là input không đáng tin cậy**.

### 7.2. HMAC: bảo đảm tính toàn vẹn và nguồn phát hành

Với cursor không có dữ liệu bí mật, một cách phổ biến là dùng **HMAC-SHA-256** bằng khóa bí mật chỉ server giữ:

```text
payloadBytes = UTF8(JSON xác định vị trí + scope + exp)
payloadB64   = base64url(payloadBytes)
message      = UTF8("v1." + payloadB64)
signature    = HMAC_SHA256(secretKey, message)
cursor       = "v1." + payloadB64 + "." + base64url(signature)
```

Khi nhận:

1. Kiểm tra độ dài và định dạng cursor, từ chối input bất thường.
2. Xác định phiên bản/khóa được hỗ trợ.
3. Tính lại chữ ký trên **đúng bytes của token được ký**.
4. So sánh chữ ký bằng hàm so sánh byte có đặc tính thời gian phù hợp, ví dụ `MessageDigest.isEqual`.
5. **Chỉ sau khi chữ ký hợp lệ**, parse payload thành kiểu dữ liệu có schema.
6. Kiểm tra `exp`, tenant, fingerprint, sort, page size và quyền truy cập hiện hành.
7. Thực thi câu truy vấn seek với tham số được bind, không ghép SQL trực tiếp từ token.

**HMAC không mã hóa payload.** Ai có cursor có thể đọc phần JSON nếu payload chỉ Base64URL. HMAC giúp phát hiện sửa nội dung khi người gửi không có khóa bí mật.

### 7.3. Khi nào cần mã hóa?

Nếu cursor chứa dữ liệu cần giữ bí mật, như tham số truy vấn nhạy cảm hoặc khóa nội bộ không được lộ, hãy cân nhắc:

- **Authenticated encryption (AEAD)**, ví dụ AES-GCM, với nonce/IV đúng quy tắc và key rotation; bảo vệ cả bí mật lẫn tính toàn vẹn.
- **Cursor lưu phía server:** token là định danh ngẫu nhiên đủ mạnh; vị trí, scope và expiry được lưu trong Redis/database theo TTL. Cách này không để payload ở client, dễ thu hồi riêng lẻ, nhưng tăng phụ thuộc storage, vận hành và chi phí.
- **Thiết kế lại payload:** giảm dữ liệu nhạy cảm, chỉ giữ khóa không nhạy và fingerprint. Nhiều trường hợp đơn giản không cần mã hóa khi tránh đưa thông tin cần bí mật vào token.

Không tự tạo thuật toán mã hóa; dùng thư viện được kiểm chứng và key management của nền tảng. Nếu chỉ cần chống sửa, HMAC có thể đơn giản hơn AEAD.

### 7.4. So sánh ba cách triển khai

| Phương án | Integrity | Confidentiality | Thu hồi/expiry | Đánh đổi |
|---|---|---|---|---|
| Base64URL JSON không ký | **Không** | **Không** | Client có thể tự sửa `exp` | Không nên dùng để tin dữ liệu scope hoặc limit |
| JSON + HMAC | Có khi khóa được bảo vệ | Không | TTL trong token; thu hồi một token riêng lẻ khó nếu stateless | Không cần session store, scale dễ |
| JSON + AEAD | Có | Có | TTL tương tự stateless nếu không có revoke list | Quản lý nonce, key, version phức tạp hơn |
| Random token + server-side store | Theo tính không đoán được của token và kiểm tra store | Payload chỉ ở server | Có thể xóa record và TTL | Tăng storage, lookup, cache/cluster consistency |

**Cursor ký không phải access token.** Bất kể chữ ký đúng, server vẫn phải xác thực người gọi và áp dụng quyền đọc mới nhất. Nếu user mất quyền giữa hai lần request, token cũ không được giữ cho họ khả năng truy cập.

### 7.5. Không dùng chữ ký làm quyền truy cập

Xét một cursor hợp lệ do tenant A phát hành. Nếu tenant B có được token, server phải:

- Xác thực B theo cơ chế API.
- Xác định tenant/principal từ danh tính tin cậy, **không từ payload cursor**.
- Kiểm tra cursor khớp scope hiện tại; nếu không, từ chối cursor.
- Luôn truy vấn `WHERE tenant_id = :authenticatedTenantId` và mọi policy phân quyền áp dụng.

Ngay cả khi logic kiểm tra token có lỗi, **điều kiện phân quyền ở truy vấn** vẫn là lớp bảo vệ quan trọng. Tránh lấy `tenantId` trong cursor làm nguồn quyền duy nhất.

## 8. Thời hạn, vòng đời và phiên bản cursor

### 8.1. TTL và `exp`

Cursor có thể hết hiệu lực vì dữ liệu thay đổi, cấu trúc API đổi hoặc khóa ký được thay mới. Một chính sách ví dụ:

```text
issuedAt = 2026-11-18T09:06:00Z
expiresAt = 2026-11-18T09:21:00Z
TTL = 15 phút
```

Các con số chỉ minh họa, không phải chuẩn REST. TTL nên cân bằng:

- **Trải nghiệm người dùng:** một session duyệt có thể kéo dài hơn vài phút.
- **Mức thay đổi dữ liệu:** tập hợp biến động nhanh có thể khiến cursor cũ khó còn ý nghĩa.
- **Khả năng thay đổi server:** deploy/đổi schema hoặc rotation key phải xét token còn sống.
- **Rủi ro bị lộ/replay:** TTL ngắn giảm thời gian một token đã lộ còn được chấp nhận.
- **Khả năng hỗ trợ client:** khi hết hạn, client cần cách **bắt đầu lại từ trang đầu** và giữ trạng thái UI hợp lý.

### 8.2. Cursor không nhất thiết dùng một lần

Token stateless có chữ ký và TTL thường có thể **gửi lại nhiều lần** trong thời hạn. HMAC không ngăn replay. Với phân trang **GET**, replay thông thường chấp nhận được và có thể hữu ích khi mạng lỗi.

Nếu nghiệp vụ đòi một token chỉ dùng một lần, cần **trạng thái phía server** để ghi nhận token đã tiêu thụ hoặc cơ chế tương đương. Điều này thường không cần cho việc đọc tập hợp và làm tăng độ phức tạp.

### 8.3. Key rotation và nhiều instance

Một dịch vụ có nhiều pod/instance cần cùng logic, cùng hệ khóa hợp lệ và cách parse token tương thích. Nếu mỗi instance tạo khóa ngẫu nhiên lúc khởi động, cursor phát ở node A có thể bị node B từ chối.

Một kế hoạch rotation hợp lý:

1. Token mang **version** và có thể mang **key ID (kid)** đã được công bố, không chứa khóa thật.
2. Server chỉ nhận `kid` từ danh sách key đã cấu hình, không tải key từ URI bất kỳ do client đưa.
3. Dùng key mới để ký token mới, tiếp tục verify token cũ bằng key trước đó trong khoảng tối thiểu đủ TTL cộng dự phòng.
4. Theo dõi tỷ lệ lỗi token phiên bản cũ, sau đó loại key hết hạn.
5. Nếu khóa bị lộ, vô hiệu hóa ngay theo quy trình ứng phó và chấp nhận yêu cầu client bắt đầu lại phân trang.

**Version của cursor** là version định dạng/semantics; **kid** là phiên bản khóa hoặc tên khóa dùng xác thực. Hai thứ có thể phát triển độc lập.

### 8.4. Phân loại lỗi hết hiệu lực

| Tình huống | Cách xử lý HTTP thường dùng | Client làm gì? |
|---|---|---|
| Token sai cú pháp/Base64 lỗi | `400 Bad Request` | Bỏ token, bắt đầu lại |
| Token đã bị sửa/chữ ký không hợp lệ | `400 Bad Request` với mô tả chung | Không retry cùng token liên tục |
| Token hết hạn | `400` hoặc `410 Gone` nếu API định nghĩa ý nghĩa này rõ | Bắt đầu lại ở trang đầu |
| Scope/filter/sort/tenant không khớp | `400` cho cursor không hợp lệ; authz riêng có thể 403 | Dùng token tương ứng hoặc bắt đầu lại |
| API không hỗ trợ cursor version | `400` theo hợp đồng | Bắt đầu lại, cập nhật SDK nếu cần |
| Chưa đăng nhập hoặc token auth hết hạn | `401 Unauthorized` | Xác thực lại; cursor không thay quyền |
| Người gọi thiếu quyền resource | `403 Forbidden` hoặc `404` theo chính sách | Không được dùng cursor để vượt quyền |
| Lỗi server/DB thật sự | `5xx` theo nguyên nhân | Retry có giới hạn theo chính sách |

**Không có một HTTP status chuẩn riêng bắt buộc cho “cursor expired”.** Phải chọn và công bố một contract ổn định. Có thể dùng Problem Details `application/problem+json` với `type` như `.../invalid-cursor` hoặc `.../expired-cursor`, nhưng không nên để nội dung phản hồi tiết lộ dữ liệu tenant hay khóa nội bộ.

## 9. Dữ liệu thay đổi giữa các trang: cursor đảm bảo tới đâu?

Cursor keyset giảm lỗi do **thay đổi vị trí offset**, nhưng không tự đóng băng dữ liệu.

### 9.1. Insert mới phía trước

Giả sử trang đầu kết thúc ở `103`. Một đơn mới `106` có `created_at` lớn hơn `103` được thêm vào. Trang sau dùng điều kiện `created_at < mốc của 103`, vì vậy không lấy `106` và không khiến `103` lặp lại.

Điều này thường đúng mong muốn: client đang **tiếp tục hành trình duyệt danh sách tại thời điểm trước**, còn đơn mới sẽ xuất hiện khi làm mới từ đầu. Tuy nhiên, nếu người dùng cần liên tục cập nhật đơn mới, có thể dùng polling/SSE/WebSocket hoặc một endpoint lấy thay đổi kể từ watermark, không cố ép cursor của feed cũ làm cơ chế đồng bộ realtime.

### 9.2. Xóa dữ liệu

Nếu đơn `102` bị xóa trước khi lấy trang hai, trang sau có thể trả `101` và kết thúc. Cursor không tự làm sống lại phần tử đã xóa. Nếu nghiệp vụ cần liệt kê mọi giao dịch lịch sử, cân nhắc **soft delete**, audit log bất biến hoặc snapshot phù hợp.

### 9.3. Update bộ lọc hoặc sort

Nếu `status` chuyển từ `PENDING` sang `PAID` giữa hai trang, bản ghi có thể đi vào hoặc rời khỏi tập kết quả. Nếu `updated_at` làm sort key, bản ghi có thể di chuyển qua mốc seek. **Không thể tuyên bố cursor mặc nhiên cho danh sách “không lặp, không thiếu” trong mọi thay đổi đồng thời.**

Nên dùng trường sắp xếp có tính bất biến trong vòng đời liên quan và mô tả mức nhất quán client có thể mong đợi.

### 9.4. Watermark `asOf` khác snapshot thật

Một giải pháp đơn giản là lưu thời điểm cắt `asOf` trong cursor và thêm:

```sql
AND created_at <= :asOf
```

để loại những bản ghi có `created_at` mới hơn mốc ban đầu. Điều này hữu ích khi `created_at` đáng tin cậy và lấy từ cùng cơ sở thời gian (tốt nhất từ DB). Nhưng nó **không ngăn** một bản ghi cũ bị cập nhật status, xóa hoặc thay đổi sort key; cũng không ngăn late-arriving records được gắn timestamp cũ.

Để có **ảnh chụp nhất quán**, cần cơ chế phù hợp hệ quản trị dữ liệu, ví dụ:

- Snapshot/database transaction có thời hạn và đặc tính nhất quán phù hợp; giữ transaction dài qua nhiều request HTTP thường có chi phí/rủi ro cao.
- Snapshot ID hoặc phiên bản dữ liệu có thể truy vấn lại, nếu storage hỗ trợ và có retention.
- Materialized result set/ID list được lưu tạm phía server và gắn với cursor, chịu chi phí lưu trữ.
- Event log bất biến có sequence/watermark, nếu bài toán là duyệt sự kiện theo thứ tự.

Phải nêu rõ **độ nhất quán và thời gian tồn tại snapshot**, giá vận hành và trường hợp snapshot không còn.

## 10. Câu truy vấn seek trong cơ sở dữ liệu

### 10.1. Trang đầu và trang tiếp theo

Với danh sách đơn theo `tenant_id`, `status` và thứ tự `created_at DESC, id DESC`, truy vấn trang đầu (watermark là thời điểm chốt phạm vi nếu có):

```sql
SELECT id, created_at, status, total_amount
FROM orders
WHERE tenant_id = :tenantId
  AND status = :status
  AND created_at <= :asOf
ORDER BY created_at DESC, id DESC
LIMIT :limitPlusOne;
```

Trang tiếp:

```sql
SELECT id, created_at, status, total_amount
FROM orders
WHERE tenant_id = :tenantId
  AND status = :status
  AND created_at <= :asOf
  AND (
      created_at < :afterCreatedAt
      OR (created_at = :afterCreatedAt AND id < :afterId)
  )
ORDER BY created_at DESC, id DESC
LIMIT :limitPlusOne;
```

**`limitPlusOne = size + 1`** để biết có dòng tiếp hay không mà không cần `COUNT(*)`. Nếu yêu cầu 20 dòng, server có thể lấy tối đa 21. Trả 20 dòng đầu tiên; nếu có dòng thứ 21 thì `hasMore=true`.

**Cực kỳ quan trọng:** tạo `nextCursor` từ **dòng cuối cùng thực sự trả cho client**, không phải dòng phụ thứ 21 dùng để kiểm tra `hasMore`. Nếu lấy mốc từ dòng thứ 21, dòng đó sẽ bị bỏ qua ở trang sau.

### 10.2. Chỉ mục hỗ trợ

Ví dụ PostgreSQL hoặc database có khả năng B-tree tương tự:

```sql
CREATE INDEX idx_orders_tenant_status_created_id
ON orders (tenant_id, status, created_at DESC, id DESC);
```

Index cần tương ứng với predicate, thứ tự sort, mật độ dữ liệu và workload. `EXPLAIN ANALYZE` giúp xem database có dùng index, còn bao nhiêu dòng phải scan, có sort lớn không và latency ra sao. Một index có thể tăng chi phí ghi và storage; không tạo mọi kết hợp filter/sort chỉ vì frontend hỗ trợ.

Khi thêm bộ lọc `minTotal` hoặc thứ tự `totalAmount ASC`, query và index có thể cần thay đổi. Không cho client gửi một trường sort tùy ý rồi ghép thẳng vào `ORDER BY`; **whitelist** các lựa chọn được hỗ trợ.

### 10.3. Số tiền, NULL và collation

- Nếu sắp xếp bằng giá/tiền, dùng kiểu dữ liệu chính xác như decimal hoặc đơn vị nhỏ nhất, không dùng float cho tiền.
- Với trường có `NULL`, phải xác định vị trí NULL, cách so sánh cursor và thứ tự trong database.
- Với sort theo text, collation/language và cập nhật index có thể làm thứ tự thay đổi; cursor version có thể phải đổi.
- Với timestamp độ chính xác cao, serialize/parse phải giữ đủ độ chính xác của DB để không tạo khoảng trống ở tie-break.
- Với UUID, cần xác định DB có ordering phù hợp và không dựa vào thứ tự ngẫu nhiên để phản ánh thời điểm nghiệp vụ.

## 11. Mẫu triển khai với Java/Spring

Phần này minh họa hợp đồng và một **codec cursor HMAC** có kiểm tra phạm vi. Đây là code hướng dẫn; cần ghép với Spring Security, repository, cấu hình Jackson, quản lý khóa và error handler thực tế.

### 11.1. Model của cursor và trang kết quả

```java
import java.time.Instant;
import java.util.List;

public record CursorState(
        int version,
        String tenantId,
        String scopeHash,
        int size,
        Instant asOf,
        Instant lastCreatedAt,
        long lastId,
        Instant expiresAt
) {}

public record PageInfo(
        int size,
        boolean hasMore,
        String nextCursor
) {}

public record OrderPage(
        List<OrderDto> data,
        PageInfo page
) {}
```

Đây là **state nội bộ server**, không phải JSON schema cho `cursor` công khai. Client chỉ thấy token dạng string, không thấy các field này trong hợp đồng.

### 11.2. Codec HMAC có kiểm tra chữ ký trước khi parse JSON

```java
import com.fasterxml.jackson.databind.ObjectMapper;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.MessageDigest;
import java.time.Instant;
import java.util.Base64;
import java.util.Objects;
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;

public final class SignedCursorCodec {
    private static final String FORMAT = "v1";
    private static final int MAX_LENGTH = 4096;

    private final ObjectMapper mapper;
    private final byte[] secretKey;

    public SignedCursorCodec(ObjectMapper mapper, byte[] secretKey) {
        if (secretKey == null || secretKey.length < 32) {
            throw new IllegalArgumentException("HMAC key must be >= 32 bytes");
        }
        this.mapper = Objects.requireNonNull(mapper);
        this.secretKey = secretKey.clone();
    }

    public String encode(CursorState state) {
        try {
            byte[] json = mapper.writeValueAsBytes(state);
            String payload = Base64.getUrlEncoder().withoutPadding()
                    .encodeToString(json);
            String signed = FORMAT + "." + payload;
            String tag = Base64.getUrlEncoder().withoutPadding()
                    .encodeToString(hmac(signed.getBytes(StandardCharsets.UTF_8)));
            return signed + "." + tag;
        } catch (IOException ex) {
            throw new IllegalStateException("Cannot serialize cursor", ex);
        }
    }

    public CursorState decode(
            String token,
            String authenticatedTenant,
            String expectedScopeHash,
            int requestedSize,
            Instant now) {

        if (token == null || token.isBlank() || token.length() > MAX_LENGTH) {
            throw new InvalidCursorException();
        }

        String[] parts = token.split("\\.", -1);
        if (parts.length != 3 || !FORMAT.equals(parts[0])
                || parts[1].isEmpty() || parts[2].isEmpty()) {
            throw new InvalidCursorException();
        }

        try {
            byte[] providedTag = Base64.getUrlDecoder().decode(parts[2]);
            String signed = parts[0] + "." + parts[1];
            byte[] expectedTag =
                    hmac(signed.getBytes(StandardCharsets.UTF_8));

            // Kiểm tra integrity trước khi deserialize payload.
            if (!MessageDigest.isEqual(providedTag, expectedTag)) {
                throw new InvalidCursorException();
            }

            byte[] json = Base64.getUrlDecoder().decode(parts[1]);
            CursorState state = mapper.readValue(json, CursorState.class);

            if (state.version() != 1
                    || !Objects.equals(state.tenantId(), authenticatedTenant)
                    || !Objects.equals(state.scopeHash(), expectedScopeHash)
                    || state.size() != requestedSize
                    || state.size() < 1 || state.size() > 100
                    || state.lastId() <= 0
                    || state.lastCreatedAt() == null
                    || state.asOf() == null
                    || state.expiresAt() == null
                    || !now.isBefore(state.expiresAt())
                    || state.lastCreatedAt().isAfter(state.asOf())) {
                throw new InvalidCursorException();
            }
            return state;
        } catch (IllegalArgumentException | IOException ex) {
            throw new InvalidCursorException();
        }
    }

    private byte[] hmac(byte[] message) {
        try {
            Mac mac = Mac.getInstance("HmacSHA256");
            mac.init(new SecretKeySpec(secretKey, "HmacSHA256"));
            return mac.doFinal(message);
        } catch (GeneralSecurityException ex) {
            throw new IllegalStateException("HMAC unavailable", ex);
        }
    }
}

class InvalidCursorException extends RuntimeException {}
```

Đoạn code minh họa một **khóa đang hoạt động**. Trong hệ thống có key rotation, cần thêm `kid`, key ring verify và quy trình loại key cũ. Secret phải đến từ secret manager hoặc cơ chế cấu hình an toàn; không viết trực tiếp giá trị khóa vào repository.

**Những điểm phải làm trước production:**

- `ObjectMapper` cần hỗ trợ `Instant` bằng module thời gian Java, chẳng hạn cấu hình Jackson của Spring Boot.
- Đảm bảo các instance dùng cùng khóa và cùng schema/logic codec.
- Kiểm tra cả kích thước **payload đã decode** và giới hạn JSON/nesting khi mở rộng schema.
- HMAC xác thực bytes của phần header/version và payload đúng như token; không parse payload hoặc truy vấn DB trước khi verify.
- Có thể kiểm tra `expiresAt` không vượt chính sách TTL tối đa so với thời điểm phát hành; giới hạn version, `asOf` và các giá trị vô lý.
- Giá trị `tenantId` đến từ principal đã xác thực, không tin tham số do client tự cung cấp. Truy vấn DB cũng phải ràng tenant.
- Cần mapping `InvalidCursorException` thành Problem Details 400/loại lỗi ổn định; không ghi raw cursor vào log.
- Trong Java, công việc giữ nhiều phiên bản key, chống replay đặc biệt hoặc mã hóa nên dùng thư viện phù hợp, không phát minh giao thức mật mã riêng ngoài thiết kế đã review.

### 11.3. Ghép controller với service phân trang

```java
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class OrderQueryController {
    private final OrderQueryService service;

    public OrderQueryController(OrderQueryService service) {
        this.service = service;
    }

    @GetMapping("/api/orders")
    public OrderPage list(
            @RequestParam(defaultValue = "PAID") String status,
            @RequestParam(defaultValue = "20") int size,
            @RequestParam(required = false) String cursor) {

        // Trong ứng dụng thực tế, lấy tenant từ security context
        // sau khi authentication đã thành công.
        String tenant = CurrentTenant.required();
        return service.list(tenant, status, size, cursor);
    }
}
```

`OrderQueryService` cần tổ chức đường đi như sau:

```text
1. Xác thực quyền đọc orders của tenant hiện tại.
2. Validate status, size, sort và quy tắc normalize các filter.
3. Xây scopeHash từ canonical query + resource/version.
4. Nếu cursor == null:
     asOf = thời điểm từ nguồn đồng hồ DB phù hợp
     after = null
   Ngược lại:
     state = codec.decode(cursor, tenant, scopeHash, size, now)
     asOf = state.asOf
     after = (state.lastCreatedAt, state.lastId)
5. Query DB với tenant + status + asOf + after
   ORDER BY created_at DESC, id DESC
   LIMIT size + 1
6. hasMore = số dòng query > size
   visible = tối đa size dòng đầu
7. Nếu hasMore && visible không rỗng:
     nextCursor = ký state mới với after = dòng cuối visible
   Ngược lại:
     nextCursor = null
8. Trả data + page; không trả CursorState hoặc key cho client.
```

Sử dụng prepared statements hoặc query builder an toàn; **không** ghép `status`, `sort`, `tenantId` hoặc `after` vào chuỗi SQL trực tiếp. Cần giữ `asOf` và `expiresAt` của hành trình đã bắt đầu (hoặc quy tắc hạn mới có kiểm soát), tránh trường hợp cứ lấy trang tiếp là vô hạn kéo dài hiệu lực token cũ.

Nếu client cần sắp xếp khác, khai báo các giá trị sort được hỗ trợ (ví dụ `createdAtDesc`), thêm vào fingerprint và xây predicate tương ứng. Không nhận mọi field arbitrary và tạo ORDER BY từ input không được whitelist.

## 12. Hợp đồng lỗi bằng HTTP Problem Details

Ví dụ client đổi `status=PAID` sang `CANCELLED` nhưng giữ cursor cũ:

```http
GET /api/orders?status=CANCELLED&size=3&cursor=v1.eyJ... HTTP/1.1
Authorization: Bearer <access-token>
```

Server trả lỗi hợp đồng, **không tự ý dùng dấu mốc cũ cho tập khác**:

```http
HTTP/1.1 400 Bad Request
Content-Type: application/problem+json
Cache-Control: no-store

{
  "type": "https://api.example.com/problems/invalid-cursor",
  "title": "Cursor không hợp lệ",
  "status": 400,
  "detail": "Cursor không phù hợp với truy vấn hiện tại. Hãy tải lại trang đầu.",
  "instance": "/problems/occurrences/req-734a"
}
```

Nếu cursor hết hạn, API có thể chọn Problem Type riêng `expired-cursor` để SDK hiển thị “Làm mới danh sách”. Việc tách loại có ích cho UX nhưng cần cân nhắc không tiết lộ trạng thái nội bộ hoặc dữ liệu ngoài quyền. Mã 400 là lựa chọn đơn giản, ổn định; `410 Gone` chỉ nên dùng nếu hợp đồng chủ động chọn semantics đó.

**Đừng dùng HTTP 200 với danh sách rỗng cho cursor sai chữ ký.** Điều này che lỗi client, gây mất trang và khiến monitoring tưởng dữ liệu hết. Tách rõ “cursor hợp lệ nhưng không còn item” (200, `data=[]`) với “cursor không hợp lệ” (4xx phù hợp).

### 12.1. Thứ tự kiểm tra bảo mật

Trong triển khai thực tế:

1. Kiểm tra authentication và giới hạn request như các endpoint khác.
2. Parse/validate các query parameter trong schema cho phép.
3. Khi có cursor, kiểm tra format/size/chữ ký/scope mà không tiết lộ thông tin về tenant khác.
4. Áp dụng authorization từ principal hiện tại đối với resource và bộ lọc.
5. Truy vấn DB với tenant và row-level policy tương ứng.

Chi tiết thứ tự có thể thay đổi theo framework và security filter, nhưng không một nhánh nào được bỏ qua quyền truy cập chỉ vì cursor có chữ ký hợp lệ.

## 13. OpenAPI cho phân trang cursor

Ví dụ OpenAPI 3.0.3 minh họa endpoint chỉ hỗ trợ thứ tự mới nhất trước:

```yaml
openapi: 3.0.3
info:
  title: Order API
  version: 1.0.0
paths:
  /api/orders:
    get:
      summary: Lấy danh sách đơn hàng bằng cursor
      description: >
        Cursor là token mờ, chỉ được gửi nguyên vẹn cho các trang kế tiếp.
        Khi thay bộ lọc hoặc size, bắt đầu từ trang đầu.
        Cursor có thời hạn và không cấp quyền truy cập.
      parameters:
        - name: status
          in: query
          required: false
          schema:
            type: string
            enum: [PAID, PENDING, CANCELLED]
            default: PAID
        - name: size
          in: query
          required: false
          schema:
            type: integer
            minimum: 1
            maximum: 100
            default: 20
        - name: cursor
          in: query
          required: false
          description: >
            Opaque token từ page.nextCursor hoặc links.next.
            Không tự phân tích hoặc thay đổi; chỉ sử dụng trong phạm vi truy vấn.
          schema:
            type: string
      responses:
        '200':
          description: Trang dữ liệu, có nextCursor khi còn trang sau
          content:
            application/json:
              schema:
                type: object
                required: [data, page]
                properties:
                  data:
                    type: array
                    items:
                      type: object
                      properties:
                        id: {type: integer, format: int64}
                        status: {type: string}
                        createdAt: {type: string, format: date-time}
                  page:
                    type: object
                    required: [size, hasMore]
                    properties:
                      size: {type: integer}
                      hasMore: {type: boolean}
                      nextCursor:
                        type: string
                        nullable: true
        '400':
          description: Query hoặc cursor không hợp lệ/hết hạn
          content:
            application/problem+json:
              schema:
                type: object
                properties:
                  type: {type: string}
                  title: {type: string}
                  status: {type: integer}
                  detail: {type: string}
                  instance: {type: string}
        '401':
          description: Chưa xác thực
        '403':
          description: Không đủ quyền
```

Bản production cần khai báo `securitySchemes`, lỗi 429/5xx, trường bắt buộc của `OrderDto` và thỏa thuận cache/link đầy đủ. Nếu SDK tự nối URL, phải URL-encode token (đặc biệt nếu định dạng thay đổi). Đừng yêu cầu client giải mã cursor để hiện “trang số 5” vì hợp đồng chủ động để token mờ.

## 14. Kiểm thử: đúng dữ liệu, đúng phạm vi, không giả mạo

### 14.1. Ma trận kiểm thử

| Test ID | Trường hợp | Kỳ vọng |
|---|---|---|
| CUR-01 | Lấy trang đầu với `size=3` | 200, 3 item, `hasMore` đúng, cursor sinh từ item cuối trả về |
| CUR-02 | Có 4 item, `size=3` | Trang 1 có 3; trang 2 có item thứ 4, không bỏ qua |
| CUR-03 | Nhiều item cùng `createdAt` | Tie-breaker ID bảo đảm thứ tự ổn định |
| CUR-04 | Insert item mới lên đầu giữa trang | Không làm trùng item cuối trang trước |
| CUR-05 | Xóa item giữa hai lần gọi | Trả tập hiện còn theo contract; không hứa snapshot |
| CUR-06 | Update field sort/filter giữa trang | Ghi nhận giới hạn nhất quán đã công bố |
| CUR-07 | Đổi `status` nhưng giữ cursor | 400 + Problem Type invalid cursor |
| CUR-08 | Đổi `size` khi contract khóa size | 400, yêu cầu bắt đầu lại |
| CUR-09 | Đổi tenant hoặc principal | Không truy cập được dữ liệu tenant khác |
| CUR-10 | Đổi một ký tự trong payload/tag | Chữ ký không hợp lệ, 400 |
| CUR-11 | Token quá dài, Base64 hỏng, thiếu phần | 400, không 500, không log raw token |
| CUR-12 | Token hết hạn | 4xx theo hợp đồng; client được hướng dẫn khởi động lại |
| CUR-13 | Token format version không hỗ trợ | Lỗi rõ, không tự diễn giải theo version cũ |
| CUR-14 | Replay cursor hợp lệ trong TTL | GET có hành vi theo contract, không coi cursor là one-time |
| CUR-15 | Nhiều instance cùng key ring | Cursor do A ký được B verify khi còn hiệu lực |
| CUR-16 | Rotate key trong TTL | Token cũ còn được xử lý theo key ring trong cửa sổ cho phép |
| CUR-17 | Trang cuối không còn item khác | `hasMore=false`, `nextCursor=null` |
| CUR-18 | Tài khoản bị thu hồi quyền | AuthZ hiện hành có hiệu lực dù cursor còn chữ ký đúng |
| CUR-19 | Query chứa filter không hợp lệ | 400 validation, không xây SQL nguy hiểm |
| CUR-20 | `totalCount` được thêm vào response | Kiểm tra hiệu năng và semantics số đếm trong tập biến động |

### 14.2. MockMvc test ở tầng hợp đồng

Đoạn test là **mẫu**; giả định Spring Boot đã có `OrderQueryController`, `OrderQueryService`, xác thực tenant và fixture đơn hàng. Không thể coi đây là kết quả test đã chạy.

```java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@SpringBootTest
@AutoConfigureMockMvc
class OrderCursorContractTest {
    @Autowired
    MockMvc mvc;

    @Test
    void firstPageReturnsCursorForNextPage() throws Exception {
        mvc.perform(get("/api/orders")
                .param("status", "PAID")
                .param("size", "3"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.data").isArray())
            .andExpect(jsonPath("$.page.hasMore").isBoolean());
    }

    @Test
    void malformedCursorIsRejected() throws Exception {
        mvc.perform(get("/api/orders")
                .param("status", "PAID")
                .param("size", "3")
                .param("cursor", "v1.tampered.not-valid"))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.type").value(
                "https://api.example.com/problems/invalid-cursor"));
    }
}
```

Với test thực tế, cấu hình mock authentication đúng tenant và tạo fixture riêng cho từng case; dùng clock có thể kiểm soát khi test expiry. Để chứng minh tính đúng của phân trang, integration test cần đọc nhiều trang rồi kiểm tra tập ID không trùng, không thiếu **trong điều kiện giả định đã chỉ rõ**. Test về tenant phải đồng thời kiểm tra response và truy vấn/policy bên dưới, không chỉ dựa vào mã 400.

### 14.3. Unit test cho cursor codec

Những kiểm tra nên chạy riêng:

```text
encode(state) -> token
decode(token, đúng tenant/scope/size/thời gian) -> đúng state

decode(token đã sửa một byte) -> InvalidCursorException
decode(token khác tenant) -> InvalidCursorException
decode(token khác filter fingerprint) -> InvalidCursorException
decode(token đã hết hạn) -> InvalidCursorException
decode(token Base64URL lỗi) -> InvalidCursorException
decode(token từ khóa không được nhận) -> InvalidCursorException
decode(token không hợp schema/version) -> InvalidCursorException
```

Với signed cursor, việc giả mạo payload rồi tự tính HMAC bằng khóa test *đúng* không phải test “tampering without secret”; cần có test sửa token **không ký lại** để chứng minh bộ kiểm tra signature hoạt động.

## 15. Những lỗi triển khai thường gặp

### 15.1. Base64URL được xem như chữ ký

Chỉ Base64-encode JSON không chống sửa đổi. Người dùng có thể giải mã và tăng `size`, đổi `tenant`, đổi last ID. Ký bằng HMAC hoặc dùng kho server-side nếu dữ liệu ảnh hưởng đến logic truy vấn.

### 15.2. Cursor chứa quyền truy cập

Backend đọc `tenantId`/`role` từ cursor rồi truy vấn không xác thực lại. Một cursor có chữ ký chỉ cho biết server đã phát token trước đây, **không chứng minh người gửi hiện tại còn được phép truy cập**.

### 15.3. Quên bind filter/sort

Token sinh từ `status=PAID` nhưng client gửi lại với `status=PENDING`. Nếu server chỉ dùng last ID, nó có thể tạo trang sai. Bind scope vào token và kiểm tra trên mỗi request.

### 15.4. Chỉ sort theo timestamp không duy nhất

Các dòng cùng `createdAt` có thể bị bỏ sót. Sử dụng tie-breaker duy nhất và predicate seek phù hợp.

### 15.5. Sinh next cursor từ dòng thừa

Server lấy 21 dòng cho `size=20` rồi ký cursor từ dòng thứ 21. Dòng thứ 21 không được trả ở trang đầu và bị bỏ qua ở trang hai. Phải ký từ **dòng thứ 20**.

### 15.6. Dùng HMAC rồi tuyên bố payload được giữ bí mật

HMAC chỉ cung cấp integrity/authenticity theo khóa bí mật, không mã hóa JSON. Đừng đưa PII/secret vào payload; nếu cần, dùng AEAD hoặc stateful token.

### 15.7. Không hỗ trợ rotation

Mỗi lần restart dịch vụ lại tạo khóa khác hoặc deploy thay khóa ký mà không có verify key cũ. Cursor còn TTL bỗng bị từ chối ngẫu nhiên; client thấy lỗi phân trang. Cần phân phối khóa nhất quán và kế hoạch rotation.

### 15.8. Coi cursor là snapshot tuyệt đối

Insert phía trước ít gây trùng hơn offset, nhưng update filter, delete, dữ liệu đến muộn và trường sort mutable vẫn có thể gây khác biệt. Nếu sản phẩm cần danh sách bất biến, phải thiết kế snapshot có retention và chi phí phù hợp.

### 15.9. Trả HTTP 200 với danh sách rỗng cho cursor lỗi

Client tưởng đã đến trang cuối và giấu lỗi phân trang. Trả 4xx theo contract và hướng client bắt đầu lại từ đầu.

### 15.10. Log nguyên cursor và URL chứa token

Cursor nằm trong query string có thể lọt vào access log, browser history, referrer hoặc công cụ giám sát; các hệ thống này có thể được nhiều người đọc. Dùng HTTPS, redaction query trong log, `Referrer-Policy` phù hợp khi cần và tránh đưa dữ liệu riêng vào token. Với use case đòi bí mật cao, có thể cân nhắc POST search endpoint với body theo hợp đồng hoặc cơ chế token lưu server-side; vẫn phải xét logging body và caching semantics.

### 15.11. Không giới hạn kích thước và độ phức tạp token

Input khổng lồ hoặc JSON sâu gây tốn CPU/memory trước khi đến DB. Giới hạn chiều dài token, định dạng, kích thước payload, schema và tần suất request; verify chữ ký trước parse payload.

### 15.12. Query keyset nhưng thiếu index

Cursor không tự biến mọi query thành nhanh. Nếu database phải sort toàn bảng hoặc scan không phù hợp với filter, trang vẫn chậm. Đo query plan với dữ liệu đại diện, cân nhắc index và chi phí ghi.

## 16. Quan sát, vận hành và giới hạn hiệu năng

Nên theo dõi:

| Chỉ số/tín hiệu | Câu hỏi |
|---|---|
| p50/p95/p99 của `GET /orders` theo loại filter | Trang đầu và trang sâu có chậm hơn nhau? |
| Số hàng scan so với số trả về | Keyset/index hoạt động hiệu quả không? |
| Tỷ lệ cursor invalid/expired/scope mismatch | Client có lỗi tích hợp, token TTL quá ngắn hay có request bất thường? |
| Tỷ lệ 401/403 khi dùng cursor | Quyền được kiểm tra lại đúng không? |
| `hasMore` và số item mỗi trang | Logic `size+1`, lọc và cursor có bỏ sót không? |
| Chi phí query, index, DB CPU/IO | Đánh đổi băng thông/CPU/storage thế nào? |
| Số version/key cũ đang được dùng | Có thể rotate và loại key an toàn không? |
| Thời gian duyệt toàn bộ tập | TTL có đủ cho hành trình sử dụng thực tế không? |

Không ghi raw cursor, khóa ký, token truy cập hoặc dữ liệu cá nhân vào log chỉ để debug. Có thể log **version**, kết quả validation, loại lỗi, correlation ID và hash một chiều của token khi có lý do rõ ràng, với chính sách bảo vệ dữ liệu phù hợp.

Nếu dùng CDN hoặc HTTP cache, lưu ý kết quả phân trang thường phụ thuộc vào tenant/quyền và có token trong URL. Đừng cache chung theo mỗi path mà bỏ query/auth scope. Với dữ liệu đơn hàng riêng tư, `Cache-Control: private, no-store` là lựa chọn thận trọng trong ví dụ; việc dùng cache khác cần đánh giá bảo mật và ngữ nghĩa dữ liệu.

## 17. Bài thực hành có hướng dẫn

### Bài A — Tìm lỗi bỏ sót dữ liệu

Database có các đơn theo thứ tự `created_at DESC, id DESC`:

```text
(09:05, 105), (09:04, 104), (09:03, 103),
(09:02, 102), (09:01, 101)
```

Client lấy trang 3 item đầu, sau đó một dòng mới `(09:06, 106)` được insert.

1. Offset pagination `offset=3` trả gì và vì sao có thể lặp?
2. Keyset pagination với mốc `(09:03,103)` trả gì?
3. Nếu `(09:02,102)` bị xóa trước trang hai, kết quả thay đổi ra sao?
4. Trường hợp nào cần snapshot thật thay vì cursor dựa vào keyset?

### Bài B — Phạm vi hiệu lực

Token được ký từ truy vấn `tenant=A, status=PAID, size=20, sort=createdAtDesc`. Client gửi lại trong các tình huống:

- Vẫn tenant A, cùng filter và size.
- Tenant B nhưng giữ token A.
- Tenant A, đổi status sang CANCELLED.
- Tenant A, đổi size lên 100.
- Tenant A, token hết hạn.
- Tenant A, quyền xem đơn bị thu hồi.

Hãy xác định tình huống nào được phép và HTTP response phù hợp với hợp đồng đã chọn. Giải thích **vì sao token có HMAC hợp lệ vẫn không thay authorization**.

### Bài C — Chữ ký và tính bí mật

Một hệ thống đang dùng `base64url(JSON)` làm cursor. Hãy:

1. Mô tả cách user có thể thay lastId hoặc size mà server khó phát hiện.
2. Thiết kế payload có version, scope, position và expiry.
3. Mô tả quy trình ký/verify bằng HMAC và kiểm tra thời gian.
4. Giải thích vì sao HMAC không che giấu tenant ID trong payload.
5. So sánh chuyển sang AEAD với lưu state phía server theo chi phí, khả năng thu hồi và quyền riêng tư.

### Bài D — Thiết kế Spring API có test

Thiết kế `GET /api/orders?status=PAID&size=20&cursor=...`:

- Order thuộc tenant; lấy tenant từ principal đã xác thực.
- Sort cố định: `created_at DESC, id DESC`.
- `size` được phép từ 1 đến 100.
- Cursor HMAC có expiry 15 phút, bind tenant, normalized filter, size, sort.
- Lỗi cursor trả 400 Problem Details; lỗi authentication/authorization theo status tương ứng.
- Tạo `nextCursor` từ bản ghi cuối trong số được trả, `hasMore` bằng truy vấn `size+1`.
- Tối thiểu 6 test về thứ tự trùng timestamp, tampering, expiry, đổi filter, tenant khác và insert mới.

Viết SQL có tham số, DTO response, OpenAPI và mô tả cách quản lý key trong nhiều instance. Nêu giả định về snapshot/watermark và giới hạn khi cập nhật status giữa các trang.

### Bài E — Đánh giá thiết kế theo rủi ro

Một API phân trang theo `updated_at DESC`, cursor chứa nguyên email người dùng và khóa ký được hard-code trong repository. Khi deploy, tất cả cursor cũ bị lỗi; một vài response dữ liệu tenant B xuất hiện ở tenant A.

Hãy phân loại vấn đề thành: **tính đúng phân trang, tính bí mật, quản lý khóa và phân quyền**. Đề xuất các bước sửa, thứ tự ưu tiên và bằng chứng kiểm thử. Vì sao chỉ tăng thời hạn cursor hoặc mã hóa token không thể sửa lỗi lộ dữ liệu nếu query thiếu tenant predicate?

## 18. Checklist review trước production

- [ ] Endpoint công bố cursor là token mờ; client không phụ thuộc vào payload.
- [ ] Thứ tự sắp xếp xác định, có tie-breaker duy nhất và predicate seek đúng chiều sort.
- [ ] Trường sort được chọn phù hợp mức nhất quán và hạn chế cập nhật giữa các trang.
- [ ] Cursor gắn với tenant/principal scope, normalized filter, sort, size và thời hạn.
- [ ] Mọi request đều xác thực và phân quyền; tenant được ràng buộc ở truy vấn DB.
- [ ] Cursor được ký HMAC hoặc bảo vệ tương đương; kiểm tra trước khi parse dữ liệu.
- [ ] Nếu payload nhạy cảm, có mã hóa có xác thực hoặc token lưu trạng thái phía server.
- [ ] Key không hard-code; nhiều instance dùng key ring nhất quán và có rotation.
- [ ] Client đổi filter/sort/size dùng lại token được xử lý theo hợp đồng rõ ràng.
- [ ] Cursor sai chữ ký, quá dài, hết hạn hoặc version không hỗ trợ có lỗi 4xx phù hợp.
- [ ] Trang cuối trả `hasMore=false` và `nextCursor=null`.
- [ ] Truy vấn lấy `size+1` nhưng next cursor sinh từ **dòng cuối đã trả**, không từ dòng thừa.
- [ ] Có index hỗ trợ filter và ORDER BY; đã đo hiệu năng với dữ liệu đại diện.
- [ ] Snapshot/watermark và giới hạn consistency được nêu rõ, không hứa “không lặp/không thiếu” tuyệt đối.
- [ ] Không ghi raw cursor/secret hoặc PII vào log và cache chia sẻ trái chính sách.
- [ ] OpenAPI mô tả request/response, lifetime, cách bắt đầu lại và Problem Details.
- [ ] Đã test thay đổi dữ liệu, concurrent writes, scope mismatch, tenant isolation, HMAC tampering và key rotation.

## 19. Ghi nhớ

**Cursor mờ** là dấu mốc phân trang do server phát hành mà client chỉ gửi lại nguyên vẹn. Tính đúng bắt đầu từ **thứ tự ổn định và điều kiện keyset/seek**, không bắt đầu từ Base64. **Phạm vi hiệu lực** phải gắn cursor với truy vấn và bối cảnh truy cập tương ứng, đồng thời xác định thời hạn/version để server có thể bảo trì hệ thống.

**HMAC** giúp phát hiện token bị sửa, nhưng không giữ bí mật payload và không cấp quyền truy cập; **authorization phải được kiểm tra lại ở mỗi request và ràng buộc ở truy vấn dữ liệu**. Cursor giảm lỗi do dịch chuyển offset nhưng không tự tạo snapshot bất biến. Một REST API tốt phải công bố rõ những giới hạn đó, xử lý lỗi có hợp đồng, quản lý khóa an toàn và có test chứng minh thứ tự, phạm vi, tính toàn vẹn và quyền truy cập.
