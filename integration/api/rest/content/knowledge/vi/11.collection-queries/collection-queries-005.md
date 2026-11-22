# Phân trang cursor, keyset và khóa sắp xếp duy nhất

## 1. Bối cảnh: vì sao phân trang không chỉ là chia danh sách?

Giả sử REST API cung cấp danh sách đơn hàng:

~~~http
GET /orders?status=PAID&limit=20 HTTP/1.1
Host: api.example.com
Authorization: Bearer <access-token>
~~~

Khi hệ thống có vài chục bản ghi, trả toàn bộ danh sách có thể chấp nhận được. Khi dữ liệu lên tới hàng triệu đơn, client cần lấy từng phần để giảm thời gian phản hồi, bộ nhớ, băng thông và tải lên cơ sở dữ liệu. Tuy nhiên, phân trang còn phải giải quyết một vấn đề khó hơn: **dữ liệu liên tục được thêm, sửa, xóa giữa hai lần gọi**.

Ví dụ người dùng tải 20 đơn mới nhất, sau đó tải trang tiếp theo trong lúc có đơn mới được tạo. Nếu API dựa vào vị trí dòng trong một tập đang thay đổi, một đơn có thể xuất hiện hai lần hoặc bị bỏ qua. Đối với API giao dịch, việc lặp hoặc bỏ sót dữ liệu có thể dẫn tới thao tác sai ở client, báo cáo thiếu hoặc quá nhiều request.

Bài học thuộc chương **Truy vấn tập hợp** của module **INTEGRATION_API_REST**: thiết kế API từ resource, URI, phương thức HTTP và hợp đồng dữ liệu rõ ràng; thực hành phân trang, cache, idempotency, OpenAPI, xác thực, phân quyền, xử lý lỗi và kiểm thử với Java/Spring hoặc công nghệ tương đương.

Sau bài này, người học có thể:

- Phân biệt **offset pagination**, **keyset/seek pagination** và **cursor pagination**.
- Thiết kế thứ tự **toàn phần** bằng khóa sắp xếp có thành phần duy nhất để tránh kết quả bất định.
- Viết SQL cho trang đầu và trang kế tiếp với tổ hợp **created_at DESC, id DESC**.
- Tạo cursor có đủ bối cảnh lọc/sắp xếp, kiểm tra tính toàn vẹn và giới hạn phạm vi truy cập.
- Giải thích giới hạn nhất quán khi dữ liệu thay đổi, kể cả khi đã dùng keyset.
- Mô tả API trong OpenAPI, triển khai ví dụ Java/Spring và kiểm thử các trường hợp đồng thời.

## 2. Ba khái niệm dễ bị nhầm

| Khái niệm | Là gì? | Ví dụ | Điều cần nhớ |
| --- | --- | --- | --- |
| **Offset pagination** | Chọn một đoạn dựa trên vị trí dòng sau khi sắp xếp. | LIMIT 20 OFFSET 40 | Vị trí thay đổi khi dữ liệu bị thêm/xóa; offset lớn có thể tốn chi phí quét. |
| **Keyset/seek pagination** | Truy xuất các dòng nằm **sau giá trị khóa sắp xếp cuối cùng** đã nhận. | WHERE (created_at, id) < (:time, :id) | Cần thứ tự ổn định, khóa so sánh được và điều kiện seek đúng chiều. |
| **Cursor pagination** | Hợp đồng API dùng một **token** để tiếp tục truy vấn. | GET /orders?cursor=eyJ2... | Cursor có thể chứa khóa seek, bối cảnh và chữ ký; không bắt buộc phải là SQL cursor. |

**Keyset là kỹ thuật truy vấn dữ liệu; cursor là cách client giữ trạng thái tiếp tục truy vấn.** Một API cursor thường triển khai bằng keyset, nhưng cũng có thể dùng snapshot ID hoặc cơ chế nội bộ khác. Ngược lại, có thể xây keyset API với các tham số công khai như **afterCreatedAt** và **afterId** mà không đóng gói thành token.

**SQL cursor phía database** là một khái niệm riêng liên quan tới ngữ cảnh thực thi/truy xuất dòng, thường có vòng đời gắn với kết nối hoặc transaction. Không nên giả định token **cursor** trong URL là con trỏ SQL sống qua nhiều HTTP request.

## 3. Vì sao OFFSET có thể lặp hoặc bỏ sót bản ghi?

Danh sách ban đầu gồm 5 đơn hàng, sắp xếp **created_at DESC**, và giả sử timestamp của mỗi đơn khác nhau:

| Vị trí | ID | created_at (UTC) |
| ---: | ---: | --- |
| 1 | 105 | 2026-11-18 10:05:00 |
| 2 | 104 | 2026-11-18 10:04:00 |
| 3 | 103 | 2026-11-18 10:03:00 |
| 4 | 102 | 2026-11-18 10:02:00 |
| 5 | 101 | 2026-11-18 10:01:00 |

Client lấy trang đầu kích thước 2:

~~~sql
SELECT id, created_at
FROM orders
ORDER BY created_at DESC
LIMIT 2 OFFSET 0;
-- Trả: 105, 104
~~~

Trước lần gọi thứ hai, một đơn **106** mới được tạo với timestamp mới nhất. Danh sách trở thành **106, 105, 104, 103, 102, 101**. Client gọi:

~~~sql
SELECT id, created_at
FROM orders
ORDER BY created_at DESC
LIMIT 2 OFFSET 2;
-- Trả: 104, 103
~~~

**Đơn 104 bị lặp** vì một dòng mới chèn phía trước đã đẩy vị trí của nó từ 2 xuống 3. Trường hợp xóa dòng phía trước cũng có thể làm một dòng chưa đọc bị bỏ qua. Thêm vào đó, với offset lớn, database thường phải duyệt hoặc sắp xếp đủ số dòng để bỏ qua chúng, dù chỉ trả một trang nhỏ; chi phí thực tế tùy execution plan và index.

~~~mermaid
flowchart LR
    A["Trang 1: 105, 104"] --> B["Chèn đơn 106 ở đầu"]
    B --> C["OFFSET 2: 104, 103"]
    C --> D["104 xuất hiện lần thứ hai"]
~~~

Offset vẫn có chỗ dùng: tập dữ liệu nhỏ, dữ liệu gần như bất biến, giao diện cần nhảy thẳng đến trang số 30, hoặc hệ thống đã có snapshot ổn định theo yêu cầu. Tuy nhiên, đối với feed/collection lớn và liên tục thay đổi, **keyset + cursor** thường là phương án tốt để đi tuần tự qua các trang.

## 4. Điều kiện tiên quyết: thứ tự phải duy nhất và xác định

### 4.1. Chỉ ORDER BY created_at có gì sai?

Nhiều đơn có thể cùng thời điểm tạo, nhất là khi timestamp chỉ lưu tới giây hoặc mili giây. Khi truy vấn:

~~~sql
SELECT id, created_at
FROM orders
WHERE tenant_id = :tenant_id
ORDER BY created_at DESC
LIMIT 20;
~~~

Database **không bắt buộc** giữ thứ tự cố định giữa các dòng có cùng created_at. Nếu trang đầu kết thúc giữa một nhóm timestamp bằng nhau, dùng chỉ điều kiện **created_at < :last_time** sẽ bỏ sót những đơn cùng timestamp nhưng chưa được trả. Ngược lại dùng **created_at <= :last_time** có thể lặp lại những đơn đã đọc.

### 4.2. Thêm khóa phá hòa (*tie-breaker*) duy nhất

Chọn thứ tự:

~~~sql
ORDER BY created_at DESC, id DESC
~~~

Với giả định **id duy nhất và không NULL**, cặp **(created_at, id)** xác định duy nhất vị trí mỗi bản ghi trong collection tại thời điểm truy vấn.

| created_at | id | Thứ tự DESC |
| --- | ---: | ---: |
| 2026-11-18 10:05:00 | 105 | 1 |
| 2026-11-18 10:04:00 | 104 | 2 |
| 2026-11-18 10:04:00 | 103 | 3 |
| 2026-11-18 10:04:00 | 102 | 4 |
| 2026-11-18 10:03:00 | 101 | 5 |

Nếu trang đầu là **105, 104**, cursor ghi lại **(10:04:00, 104)**; trang sau phải chọn những dòng có created_at nhỏ hơn 10:04 hoặc **cùng timestamp nhưng id nhỏ hơn 104**. Khi đó trang tiếp theo là **103, 102** và không bỏ sót các dòng trùng timestamp.

Lưu ý: “khóa duy nhất” ở đây là **tổ hợp toàn bộ các cột sắp xếp**, không yêu cầu từng cột tự nó duy nhất. Nếu ID chỉ duy nhất trong từng tenant, điều kiện **tenant_id = ...** phải cố định qua mọi trang; hoặc thêm tenant vào khóa khi thực sự cần thứ tự toàn cục.

### 4.3. Khóa sắp xếp tốt cần những tính chất nào?

- **Xác định và duy nhất:** kết hợp các trường cuối cùng phải phá hết trường hợp bằng nhau, thường kết thúc bằng ID duy nhất.
- **Kiểu và phép so sánh rõ ràng:** thời gian dùng timezone, precision, collation và quy tắc NULL nhất quán giữa DB và cursor.
- **Ổn định nếu có thể:** ưu tiên trường không thay đổi như created_at và ID để hạn chế dòng nhảy vị trí giữa các trang.
- **Được index phù hợp:** điều kiện tenant/filter, rồi các trường ORDER BY/seek để tránh quét và sort tốn kém.
- **Được bảo vệ:** client không được tùy tiện đưa tên cột hay biểu thức SQL vào ORDER BY; chỉ cho phép sort key theo danh sách được công bố.

**Khóa sắp xếp duy nhất không đồng nghĩa dữ liệu đã có snapshot nhất quán**; nó chỉ bảo đảm thứ tự trong kết quả của mỗi lần truy vấn được định nghĩa rõ ràng.

## 5. Viết truy vấn keyset chính xác

Giả sử bảng orders có **id BIGINT PRIMARY KEY**, **created_at TIMESTAMPTZ NOT NULL**, **tenant_id BIGINT NOT NULL**, **status VARCHAR NOT NULL**. API lọc theo tenant đã được xác thực và status đã chọn.

### 5.1. Trang đầu

~~~sql
SELECT id, tenant_id, status, created_at, total_minor_unit
FROM orders
WHERE tenant_id = :tenant_id
  AND status = :status
ORDER BY created_at DESC, id DESC
LIMIT :page_size_plus_one;
~~~

Nếu client muốn 20 dòng, truy vấn **21 dòng**. Dòng thứ 21 chỉ để kiểm tra còn dữ liệu phía sau; không trả nó trong items. Nếu có 21 dòng, **hasNext = true**. Cursor trang sau lấy từ **dòng thứ 20 (dòng cuối thực sự trả)**, không phải dòng thứ 21.

### 5.2. Trang tiếp theo

Với cursor chứa **last_created_at** và **last_id** từ dòng cuối của trang trước:

~~~sql
SELECT id, tenant_id, status, created_at, total_minor_unit
FROM orders
WHERE tenant_id = :tenant_id
  AND status = :status
  AND (
       created_at < :last_created_at
       OR (
            created_at = :last_created_at
            AND id < :last_id
          )
      )
ORDER BY created_at DESC, id DESC
LIMIT :page_size_plus_one;
~~~

Đây là **lexicographic comparison** (*so sánh theo thứ tự từ trái sang phải*). Khi hai trường đều giảm dần, những khóa “nằm sau” cursor có giá trị tuple nhỏ hơn. Với một số hệ cơ sở dữ liệu như PostgreSQL và dữ liệu NOT NULL, có thể viết gọn:

~~~sql
AND (created_at, id) < (:last_created_at, :last_id)
~~~

Điều kiện dạng tuple chỉ dùng khi semantics so sánh cột, chiều sort và NULL phù hợp; **không tự động áp dụng cho mọi ORDER BY trộn ASC/DESC**. Phiên bản OR rõ ràng hơn để hiểu và kiểm chứng.

### 5.3. Các chiều sắp xếp

| ORDER BY | Dòng sau cursor phải thỏa |
| --- | --- |
| created_at **DESC**, id **DESC** | created_at **<** t, hoặc cùng t và id **<** i |
| created_at **ASC**, id **ASC** | created_at **>** t, hoặc cùng t và id **>** i |
| score **DESC**, id **ASC** | score **<** s, hoặc cùng s và id **>** i |
| price **ASC**, id **DESC** | price **>** p, hoặc cùng p và id **<** i |

Không thay dấu theo cảm tính. Mỗi cột dùng toán tử “đi tiếp” ứng với chiều sắp xếp của nó; chỉ khi các cột trước bằng nhau mới so cột tiếp. Nếu có ba khóa, mở rộng biểu thức theo từng cấp.

### 5.4. Nếu giá trị sort có thể NULL?

Truy vấn như **ORDER BY score DESC NULLS LAST, id DESC** cần thứ tự rõ ràng và predicate tương ứng cho cả nhóm NULL. So sánh trực tiếp **score < :score** không chọn được dòng có score NULL; nếu cursor đã nằm trong nhóm NULL thì điều kiện đó cũng không hoạt động.

Một cách thiết kế là **không cho NULL trong khóa phân trang**, hoặc chuẩn hóa có chủ đích bằng cột sort phụ có giá trị không NULL và thứ tự xác định (ví dụ biểu thức/cột phát sinh mang **null_rank** và một giá trị score được chuẩn hóa), rồi định nghĩa seek tương ứng. Không dùng COALESCE với một sentinel có thể trùng giá trị thật mà chưa chứng minh miền dữ liệu. Với tìm kiếm phức tạp, hãy thử đầy đủ các chuyển tiếp **non-NULL → NULL → hết dữ liệu**.

## 6. Từ keyset tới cursor trên REST API

### 6.1. Hợp đồng endpoint đề xuất

Trang đầu:

~~~http
GET /orders?status=PAID&limit=2 HTTP/1.1
Authorization: Bearer <access-token>
Accept: application/json
~~~

Phản hồi:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: private, no-store

{
  "items": [
    {"id": 105, "createdAt": "2026-11-18T10:05:00Z", "status": "PAID"},
    {"id": 104, "createdAt": "2026-11-18T10:04:00Z", "status": "PAID"}
  ],
  "page": {
    "limit": 2,
    "hasNext": true,
    "nextCursor": "<opaque-signed-token>"
  }
}
~~~

Client lấy trang kế tiếp bằng token được trả:

~~~http
GET /orders?status=PAID&limit=2&cursor=<opaque-signed-token> HTTP/1.1
Authorization: Bearer <access-token>
~~~

Phản hồi trang thứ hai:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

{
  "items": [
    {"id": 103, "createdAt": "2026-11-18T10:04:00Z", "status": "PAID"},
    {"id": 102, "createdAt": "2026-11-18T10:04:00Z", "status": "PAID"}
  ],
  "page": {
    "limit": 2,
    "hasNext": true,
    "nextCursor": "<opaque-signed-token-2>"
  }
}
~~~

Trang cuối sẽ là:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

{
  "items": [
    {"id": 101, "createdAt": "2026-11-18T10:03:00Z", "status": "PAID"}
  ],
  "page": {
    "limit": 2,
    "hasNext": false,
    "nextCursor": null
  }
}
~~~

Các ID, thời gian và token chỉ để minh họa. Với đúng năm bản ghi ở ví dụ và limit = 2, trang 1 và 2 có hasNext = true, trang 3 không còn trang sau. Nếu dữ liệu thực vẫn còn nhiều dòng, hasNext phải phản ánh kết quả **LIMIT + 1** chứ không được đoán từ số lượng dòng của trang.

**HTTP 200 OK** phù hợp với GET collection dù trả về tập rỗng. Không dùng 404 cho trang cuối rỗng nếu resource collection vẫn tồn tại; cũng không cần trả 206 Partial Content chỉ vì API tự phân trang theo cursor. **206** gắn với semantics của HTTP Range request.

### 6.2. Next link, URL và cursor

Có thể đưa URI trang kế tiếp vào JSON:

~~~json
{
  "page": {
    "hasNext": true,
    "nextCursor": "<opaque-signed-token>",
    "next": "/orders?status=PAID&limit=2&cursor=<opaque-signed-token>"
  }
}
~~~

Hoặc dùng HTTP **Link** với quan hệ **next** nếu hợp đồng API quy định. Client nên xem cursor như một token **opaque**: không tự phân tích rồi tự sửa timestamp, ID hoặc filter. Token phải được URL-encode khi gắn vào query string; tránh đưa thông tin nhạy cảm trực tiếp vào URL vì URL có thể xuất hiện trong log, lịch sử và hệ thống phân tích.

### 6.3. Có nên trả totalCount và totalPages?

Keyset được thiết kế tối ưu cho **đi tuần tự**, không tự hỗ trợ “nhảy đến trang 500”. Truy vấn **COUNT(*)** trên collection lớn và có filter phức tạp có thể đắt, hoặc số lượng thay đổi trong khi client đang đọc. API có thể:

- Không trả totalCount, chỉ trả **hasNext/nextCursor**.
- Trả **estimatedCount** với nhãn rõ ràng và chính sách độ mới.
- Trả count qua một endpoint hoặc truy vấn riêng khi thật sự cần, kèm giới hạn hiệu năng.

Không suy ra **totalPages** từ số bản ghi đang biến động rồi hứa thứ tự nhất quán qua nhiều request.

## 7. Cursor nên chứa thông tin gì?

Với keyset dựa trên **(created_at DESC, id DESC)**, cursor cần giữ đủ bối cảnh để server tiếp tục đúng cùng một truy vấn:

~~~json
{
  "v": 1,
  "sort": "createdAt_desc_id_desc",
  "lastCreatedAt": "2026-11-18T10:04:00Z",
  "lastId": 104,
  "filterHash": "sha256-of-canonical-filter",
  "tenant": "tenant-7",
  "subject": "user-19",
  "limit": 2,
  "issuedAt": 1794996300,
  "expiresAt": 1794999900
}
~~~

Đây là **payload minh họa trước khi đóng gói thành token**; thời điểm issuedAt/expiresAt phải được sinh thực tế từ hệ thống, không sao chép các giá trị trên. Có thể thay trường tenant/subject bằng định danh phạm vi hoặc băm/opaque reference, để tránh tiết lộ thông tin. Những thông tin thường cần thiết:

| Trường | Vì sao có ích? |
| --- | --- |
| **v** | Quản lý phiên bản định dạng cursor khi triển khai thay đổi. |
| **lastCreatedAt**, **lastId** | Mốc keyset để truy vấn dòng sau. |
| **sort** | Buộc tất cả các trang dùng cùng một định nghĩa thứ tự. |
| **filterHash** | Phát hiện client đổi filter giữa chừng hoặc dùng cursor sang collection khác. |
| **tenant/subject/scope** | Ràng buộc token với phạm vi truy cập; vẫn phải kiểm tra authorization mỗi request. |
| **limit** | Giữ kích thước trang đồng nhất nếu hợp đồng yêu cầu. |
| **issuedAt/expiresAt** | Hạn chế vòng đời token; hỗ trợ đổi chiến lược hoặc khóa ký. |
| **snapshot/watermark** (nếu có) | Duy trì chính sách nhất quán có xác định, cần định nghĩa ý nghĩa thật. |

Không nhất thiết phải mang mọi trường trong mọi token. Có thể phát token ngẫu nhiên tham chiếu tới một bản ghi trạng thái trên server; đổi lại cần kho lưu, TTL và vận hành dọn state. Với API stateless, đóng gói payload và ký là lựa chọn phổ biến.

### 7.1. Token phải được kiểm tra tính toàn vẹn

Chỉ **Base64URL-encode JSON** không phải biện pháp bảo mật: client có thể giải mã và sửa các trường. Một cách phát token:

~~~text
payloadBytes = UTF8(canonicalJSON(cursorPayload))
body = base64url(payloadBytes)
mac = HMAC_SHA256(serverSecret, body)
token = body + "." + base64url(mac)
~~~

Khi nhận token, server:

1. Giới hạn độ dài, định dạng, số phần và phiên bản cho phép.
2. Xác minh HMAC bằng khóa server quản lý, so sánh chữ ký theo cách chống rò rỉ thời gian.
3. Kiểm tra hết hạn, định dạng khóa seek và sort được hỗ trợ.
4. So khớp filter đã chuẩn hóa và page size theo hợp đồng.
5. Ràng buộc với danh tính/tenant/scope hiện tại và **kiểm tra quyền từ đầu mỗi request**.
6. Chỉ dùng những trường đã qua kiểm tra để xây câu SQL có tham số.

**Chữ ký không mã hóa nội dung token.** Người nhận vẫn có thể đọc phần Base64URL; không đưa token, dữ liệu cá nhân hoặc bí mật khác vào cursor nếu không có kiểm soát phù hợp. Nếu phải che cả nội dung, dùng token opaque ngẫu nhiên ánh xạ server-side, hoặc thiết kế mã hóa có xác thực và quản lý khóa đúng cách.

Không tự đưa tên cột, điều kiện WHERE hoặc chuỗi ORDER BY từ cursor vào SQL. Token được ký chỉ chứng minh server từng phát payload đó; chính sách truy cập và phiên bản hợp đồng vẫn cần được kiểm tra.

### 7.2. Khóa ký và vòng đời cursor

- Lưu khóa ký trong hệ thống quản lý secret; không hard-code vào source code hoặc ghi log.
- Dùng **key ID/phiên bản** khi cần xoay vòng; tiếp tục chấp nhận khóa cũ trong thời gian token còn hiệu lực theo chính sách.
- Chọn TTL dựa vào hành vi người dùng, chi phí duy trì tương thích và rủi ro lộ token.
- Định nghĩa mã lỗi và hướng bắt đầu lại khi token quá hạn hoặc phiên bản không còn hỗ trợ.
- Không gửi token sang bên thứ ba qua query, referrer hoặc log không cần thiết.

## 8. Filter, sort và quyền truy cập phải giữ ổn định

Giả sử trang đầu dùng:

~~~http
GET /orders?status=PAID&sort=-createdAt&limit=20
~~~

Sau đó client đổi status thành CANCELLED nhưng giữ cursor cũ. Nếu server chỉ sử dụng lastCreatedAt/lastId, truy vấn tiếp theo không còn là “trang sau” của cùng collection đã lọc; kết quả có thể bị trùng hoặc bỏ sót so với kỳ vọng.

**Cần chuẩn hóa truy vấn** trước khi so filterHash:

- Chuẩn hóa giá trị mặc định: không truyền sort và truyền sort mặc định phải mang cùng nghĩa.
- Chuẩn hóa dạng biểu diễn: danh sách filter, thứ tự phần tử nếu không quan trọng, timezone và kiểu dữ liệu.
- Gắn phiên bản quy tắc sort/filter để khi server thay mặc định, cursor cũ không âm thầm đổi nghĩa.
- Tính cả phạm vi dữ liệu được phép xem (tenant, organization, data scope).
- Giới hạn kích thước trang, ví dụ **1–100**, và chỉ cho phép sort key trong allowlist.

**Quyền có thể thay đổi giữa các trang.** Cursor được cấp khi user có quyền không được biến thành quyền vĩnh viễn. Server luôn kiểm tra quyền hiện tại, ràng buộc tenant từ token xác thực và áp đặt filter phân quyền trong SQL. Cần từ chối token của tenant khác mà không tiết lộ sự tồn tại của dữ liệu.

### 8.1. Trạng thái lỗi của cursor

| Trường hợp | Phản hồi có thể chọn | Nội dung client cần biết |
| --- | --- | --- |
| Token sai định dạng, chữ ký sai hoặc payload không hợp lệ | **400 Bad Request** | Cursor không hợp lệ; không thử sửa thủ công. |
| Token hết hạn | **400** với problem type riêng, hoặc **410 Gone** nếu API chủ đích coi cursor như resource đã hết vòng đời | Bắt đầu lại từ trang đầu. |
| Đổi filter/sort/limit trái hợp đồng | **400 Bad Request** | Tiếp tục với truy vấn cũ hoặc xin trang đầu của truy vấn mới. |
| Không đủ quyền xem collection | **403 Forbidden**, hoặc **404** nếu chính sách che resource | Không sử dụng cursor để vượt phạm vi quyền. |
| Rate limit | **429 Too Many Requests** | Backoff, tuân thủ Retry-After nếu có. |
| Backend tạm không sẵn sàng | **503 Service Unavailable** hoặc mã 5xx đúng nguyên nhân | Retry có giới hạn theo tính an toàn của GET. |

Không có một status bắt buộc riêng cho mọi lỗi cursor ở chuẩn HTTP; điều quan trọng là hợp đồng API công bố loại lỗi ổn định, status đúng và cách client phục hồi. Problem Details theo **RFC 9457** hữu ích để chuẩn hóa lỗi này.

~~~http
HTTP/1.1 400 Bad Request
Content-Type: application/problem+json
Cache-Control: no-store

{
  "type": "https://api.example.com/problems/invalid-cursor",
  "title": "Invalid cursor",
  "status": 400,
  "detail": "Cursor không phù hợp với truy vấn hiện tại.",
  "code": "CURSOR_QUERY_MISMATCH"
}
~~~

Không đưa chi tiết chữ ký, khóa HMAC hoặc ID của tenant khác vào body lỗi.

## 9. Keyset có bảo đảm snapshot nhất quán không?

**Không.** Keyset giúp đi theo một thứ tự rõ ràng mà không phụ thuộc offset. Nó không tự đảm bảo mọi trang cùng quan sát một snapshot cơ sở dữ liệu.

### 9.1. Insert mới

Với **created_at DESC, id DESC**, một bản ghi mới hơn cursor ở phía đầu danh sách thường **không xuất hiện** trong các trang tiếp theo. Đây là ưu điểm khi người dùng đang cuộn xuống danh sách đơn cũ. Tuy nhiên, nếu có insert với timestamp **backdated** hoặc sort key được thiết lập nằm *sau cursor*, bản ghi đó có thể xuất hiện trong trang sau dù không tồn tại lúc trang đầu.

### 9.2. Delete và cập nhật khóa sort

Nếu một đơn ở trang sau bị xóa trước khi client tới đó, nó có thể không còn xuất hiện. Nếu **created_at hoặc khóa sort khác bị sửa**, bản ghi có thể chuyển từ phía chưa đọc sang phía đã đọc, hoặc ngược lại, gây thiếu/lặp ngay cả với keyset. Nếu filter dựa trên **status** và status đổi từ PAID sang CANCELLED, tập kết quả cũng thay đổi.

Tóm tắt:

| Thay đổi giữa các request | OFFSET | KEYSET với khóa bất biến |
| --- | --- | --- |
| Insert mới ở đầu | Có thể làm lặp một dòng cũ. | Thường không làm dịch ranh giới đã đọc. |
| Delete ở trước vị trí tiếp tục | Có thể bỏ qua một dòng chưa đọc. | Ranh giới khóa thường vẫn chính xác. |
| Insert được backdate xuống sau cursor | Có thể xuất hiện tùy vị trí. | Có thể xuất hiện dù không có trong trang đầu. |
| Update một trường dùng để sort | Có thể gây lặp hoặc thiếu. | **Vẫn có thể** gây lặp hoặc thiếu. |
| Thay đổi quyền/filter membership | Kết quả thay đổi. | Kết quả cũng thay đổi; phải áp lại quyền. |

### 9.3. Watermark và snapshot

Nếu nghiệp vụ cần danh sách ổn định hơn, có thể thêm **watermark** khi lấy trang đầu, chẳng hạn chỉ lấy đơn có **created_at <= :cutoff** và dùng cùng cutoff ở mọi trang. Cách này loại được phần lớn insert có timestamp tạo mới sau cutoff trong giả định timestamp được server gán chính xác. Nhưng **không ngăn insert backdated, update, delete hoặc thay đổi quyền** và không phải bằng chứng snapshot database nghiêm ngặt.

Khi cần **đúng một tập cố định** để xuất báo cáo, đối soát hoặc xử lý mỗi bản ghi đúng một lần, cân nhắc:

1. Database snapshot có cơ chế giữ/khôi phục snapshot qua nhiều lần đọc phù hợp công nghệ và vòng đời request.
2. Materialize một tập ID tại thời điểm bắt đầu, có TTL và phân quyền chặt.
3. Dùng một job xuất dữ liệu bất đồng bộ với mốc chốt và kết quả bất biến.
4. Thiết kế event stream có offset/checkpoint rõ ràng nếu nghiệp vụ thực sự muốn “đọc tất cả thay đổi” thay vì phân trang representation hiện tại.

Không giữ transaction database mở lâu qua nhiều lần HTTP request chỉ để giả lập snapshot mà chưa đánh giá lock, VACUUM/retention, tài nguyên và tính khả thi. “Keyset không lặp” phải luôn gắn điều kiện **dữ liệu và khóa sort không thay đổi theo cách làm dịch vị trí**.

## 10. Thiết kế index và đánh giá hiệu năng

Với truy vấn:

~~~sql
SELECT id, created_at, status, total_minor_unit
FROM orders
WHERE tenant_id = :tenant_id
  AND status = :status
  AND (
    created_at < :last_created_at
    OR (created_at = :last_created_at AND id < :last_id)
  )
ORDER BY created_at DESC, id DESC
LIMIT 21;
~~~

Một index thường đáng cân nhắc trên PostgreSQL:

~~~sql
CREATE INDEX idx_orders_tenant_status_created_id
ON orders (tenant_id, status, created_at DESC, id DESC);
~~~

Đặt các cột lọc bằng trước các cột dùng để seek/sắp xếp thường giúp database tận dụng index. Tuy nhiên, thứ tự index cần dựa trên **toàn bộ tập truy vấn phổ biến, phân bố dữ liệu và kế hoạch thực thi**. Nếu status thay đổi thường xuyên, index sẽ có chi phí cập nhật. Nếu API còn truy vấn không có filter status, một index khác có thể phù hợp.

Hãy dùng:

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT id, created_at, status, total_minor_unit
FROM orders
WHERE tenant_id = 7
  AND status = 'PAID'
  AND (created_at, id)
        < (TIMESTAMPTZ '2026-11-18 10:04:00+00', 104)
ORDER BY created_at DESC, id DESC
LIMIT 21;
~~~

Đây là phép đo dành cho môi trường thử nghiệm có dữ liệu đại diện. Quan sát **Index Scan/Index Only Scan**, số rows đọc/bỏ, sort, buffer read, độ trễ và thay đổi khi cursor đi sâu. Tránh lấy một execution plan trên bảng nhỏ làm căn cứ chắc chắn cho dữ liệu production.

Các điểm thực tế khác:

- Bảo đảm time precision trong cursor khớp giá trị DB. Ví dụ timestamp microsecond từ PostgreSQL không nên bị làm tròn thành giây rồi đưa vào điều kiện equality.
- Nếu ORDER BY theo chuỗi, phải thống nhất collation giữa truy vấn, index và cách so sánh; thay locale/collation có thể khiến cursor cũ không còn hợp lệ.
- Nếu ORDER BY theo điểm xếp hạng tính động, keyset có thể bị thay đổi vị trí; cân nhắc giữ phiên bản điểm hoặc chỉ cam kết tính nhất quán yếu.
- Với dữ liệu multi-tenant, index và mọi điều kiện seek luôn phải áp dụng bộ lọc tenant ở server.
- Có giới hạn page size và thời gian truy vấn; cursor không được trở thành phương tiện đọc toàn bộ dữ liệu vượt hạn mức.

## 11. Ví dụ triển khai với Java/Spring

### 11.1. DTO và hợp đồng truy vấn

Giả định API dùng **Spring Boot/Spring JDBC**, cơ sở dữ liệu PostgreSQL và dữ liệu đơn hàng được phân quyền theo **tenantId** lấy từ danh tính người dùng. Các đoạn mã dưới minh họa cơ chế seek; các lớp xác thực, tạo chữ ký cursor và xử lý lỗi được trình bày thành interface để nêu rõ trách nhiệm.

~~~java
import java.time.Instant;
import java.util.List;

record OrderRow(
        long id,
        Instant createdAt,
        String status,
        long totalMinorUnit
) {}

record SeekKey(Instant createdAt, long id) {}

record OrderPage(
        List<OrderRow> items,
        boolean hasNext,
        SeekKey lastReturnedKey
) {}

record CursorPayload(
        int version,
        SeekKey after,
        String sort,
        String filterHash,
        long tenantId,
        int limit,
        Instant expiresAt
) {}
~~~

**lastReturnedKey** là trạng thái nội bộ; API nên chỉ trả **nextCursor** đã được đóng gói và kiểm tra, không nhất thiết lộ các trường seek cho client.

### 11.2. Repository dùng NamedParameterJdbcTemplate

~~~java
import java.sql.Timestamp;
import java.util.List;
import org.springframework.jdbc.core.namedparam.MapSqlParameterSource;
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate;
import org.springframework.stereotype.Repository;

@Repository
public class OrderReadRepository {
    private final NamedParameterJdbcTemplate jdbc;

    public OrderReadRepository(NamedParameterJdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public OrderPage list(
            long tenantId, String status, int pageSize, SeekKey after) {
        // Giả định pageSize đã được service kiểm tra: 1..100.
        String seek = (after == null) ? "" : """
                AND (
                    created_at < :afterCreatedAt
                    OR (created_at = :afterCreatedAt AND id < :afterId)
                )
                """;

        String sql = """
                SELECT id, created_at, status, total_minor_unit
                FROM orders
                WHERE tenant_id = :tenantId
                  AND status = :status
                """ + seek + """
                ORDER BY created_at DESC, id DESC
                LIMIT :fetchSize
                """;

        var params = new MapSqlParameterSource()
                .addValue("tenantId", tenantId)
                .addValue("status", status)
                .addValue("fetchSize", pageSize + 1);

        if (after != null) {
            params.addValue("afterCreatedAt",
                    Timestamp.from(after.createdAt()));
            params.addValue("afterId", after.id());
        }

        List<OrderRow> found = jdbc.query(sql, params,
                (rs, rowNum) -> new OrderRow(
                        rs.getLong("id"),
                        rs.getTimestamp("created_at").toInstant(),
                        rs.getString("status"),
                        rs.getLong("total_minor_unit")));

        boolean hasNext = found.size() > pageSize;
        List<OrderRow> items = List.copyOf(
                found.subList(0, Math.min(pageSize, found.size())));

        SeekKey lastKey = (hasNext && !items.isEmpty())
                ? new SeekKey(
                        items.get(items.size() - 1).createdAt(),
                        items.get(items.size() - 1).id())
                : null;

        return new OrderPage(items, hasNext, lastKey);
    }
}
~~~

Điểm quan trọng:

- SQL chỉ có **hai dạng cố định** (trang đầu và trang tiếp), biến dữ liệu được truyền bằng parameter binding.
- Không dùng OFFSET; trang tiếp lấy điều kiện keyset.
- Đọc tối đa **pageSize + 1**, nhưng chỉ trả tối đa **pageSize**.
- Cursor được tạo từ **dòng cuối thực sự gửi cho client**, không phải dòng dư dùng kiểm tra hasNext.
- Giới hạn pageSize trước khi vào repository để tránh overflow/hạn mức không phù hợp. Trong code thật, cần kiểm tra giới hạn timeout truy vấn và status filter được cho phép.

### 11.3. Codec và service kiểm tra cursor

Thay vì nối trực tiếp query params thành SQL, service giải mã và kiểm tra:

~~~java
interface CursorCodec {
    // encode phải ký payload hoặc dùng token opaque tham chiếu state.
    String encode(CursorPayload payload);

    // decode phải xác thực chữ ký/định dạng, giới hạn kích thước,
    // version và expiry, nếu sai thì báo InvalidCursorException.
    CursorPayload decode(String token);
}

record PageMeta(int limit, boolean hasNext, String nextCursor) {}
record PageResponse(List<OrderRow> items, PageMeta page) {}

// Pseudocode cho luồng application service:
//
// int size = validateLimit(requestedLimit, 1, 100);
// long tenant = authenticatedPrincipal.tenantId();
// String filter = canonicalizeFilter(requestedStatus);
// String hash = sha256OfCanonicalFilter(filter, "createdAt_desc_id_desc");
// SeekKey after = null;
//
// if (cursorToken != null) {
//     CursorPayload current = cursorCodec.decode(cursorToken);
//     require(current.tenantId() == tenant);
//     require(current.limit() == size);
//     require(current.sort().equals("createdAt_desc_id_desc"));
//     require(current.filterHash().equals(hash));
//     after = current.after();
// }
//
// authorizeCanListOrders(tenant, authenticatedPrincipal);
// OrderPage slice = repository.list(tenant, filter, size, after);
// String nextCursor = slice.hasNext()
//      ? cursorCodec.encode(new CursorPayload(
//            1, slice.lastReturnedKey(),
//            "createdAt_desc_id_desc", hash, tenant, size,
//            Instant.now().plusSeconds(3600)))
//      : null;
// return new PageResponse(slice.items(),
//      new PageMeta(size, slice.hasNext(), nextCursor));
~~~

Đây là mã giả ở service để minh họa trách nhiệm, không phải một triển khai security/cursor hoàn chỉnh có thể copy nguyên vào production. **Codec.encode/decode phải được hiện thực an toàn** bằng token được ký/xác thực hoặc opaque server-side; kiểm tra chữ ký và quyền không được thay bằng kiểm tra format. Nếu quyền người dùng có thể khác nhau trong cùng tenant, cursor còn phải ràng buộc với **subject/scope** và SQL phải áp đúng điều kiện phân quyền từng bản ghi.

**Điểm đồng bộ thời gian:** repository lấy created_at từ database; encode cursor phải giữ chính xác độ phân giải này. Nếu làm tròn timestamp ở bước serialize/deserialize, điều kiện equal created_at không còn chính xác và có thể tạo lỗ hổng phân trang.

### 11.4. Controller và mã lỗi

~~~java
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/orders")
class OrderQueryController {
    private final OrderQueryService service;

    OrderQueryController(OrderQueryService service) {
        this.service = service;
    }

    @GetMapping
    ResponseEntity<PageResponse> list(
            @RequestParam(defaultValue = "PAID") String status,
            @RequestParam(defaultValue = "20") int limit,
            @RequestParam(required = false) String cursor) {
        return ResponseEntity.ok(
                service.list(status, limit, cursor));
    }
}
~~~

**OrderQueryService** là lớp application giả định theo hợp đồng ở phần trên. Cần xử lý ngoại lệ **InvalidCursorException**, giới hạn filter, quyền của principal và lỗi backend bằng Problem Details hợp lý. Nếu cursor chứa dữ liệu riêng của tenant, response nên có Cache-Control phù hợp (ví dụ private, no-store) và không bị CDN chia sẻ sang client khác.

## 12. Mô tả hợp đồng bằng OpenAPI 3.1

~~~yaml
openapi: 3.1.0
info:
  title: Orders API
  version: 1.0.0
paths:
  /orders:
    get:
      summary: Liệt kê đơn hàng bằng cursor
      description: >
        Sắp xếp ổn định theo createdAt DESC, id DESC.
        Cursor phụ thuộc filter, limit và phạm vi người dùng.
        Không hỗ trợ nhảy tùy ý tới trang số N.
      parameters:
        - in: query
          name: status
          required: false
          schema:
            type: string
            enum: [PAID, PENDING, CANCELLED]
            default: PAID
        - in: query
          name: limit
          required: false
          schema:
            type: integer
            minimum: 1
            maximum: 100
            default: 20
        - in: query
          name: cursor
          required: false
          description: Token opaque do server phát từ lần truy vấn trước.
          schema:
            type: string
      responses:
        '200':
          description: Trang dữ liệu theo thứ tự xác định
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/OrdersPage'
        '400':
          description: Filter/limit/cursor không hợp lệ hoặc không khớp
          content:
            application/problem+json:
              schema:
                $ref: '#/components/schemas/Problem'
        '401':
          description: Chưa xác thực hợp lệ
        '403':
          description: Không có quyền truy vấn collection
        '429':
          description: Vượt giới hạn truy vấn
        '503':
          description: Tạm thời không phục vụ
components:
  schemas:
    OrdersPage:
      type: object
      required: [items, page]
      properties:
        items:
          type: array
          items:
            $ref: '#/components/schemas/Order'
        page:
          type: object
          required: [limit, hasNext, nextCursor]
          properties:
            limit:
              type: integer
            hasNext:
              type: boolean
            nextCursor:
              type: [string, 'null']
    Order:
      type: object
      required: [id, createdAt, status]
      properties:
        id:
          type: integer
          format: int64
        createdAt:
          type: string
          format: date-time
        status:
          type: string
    Problem:
      type: object
      properties:
        type: {type: string, format: uri-reference}
        title: {type: string}
        status: {type: integer}
        detail: {type: string}
~~~

Trích đoạn này minh họa hợp đồng phân trang và status, chưa bao gồm securitySchemes, giới hạn permission theo tenant, mọi trường Order, ETag hoặc chi tiết OAuth2. Trong OpenAPI 3.1, **type: [string, 'null']** thể hiện nextCursor có thể null; không tự biến nó thành chuỗi chữ “null”.

## 13. Phân trang ngược và tải trang trước

Trang kế tiếp trong thứ tự **created_at DESC, id DESC** lấy những dòng có khóa nhỏ hơn cursor cuối. Muốn quay về phần ngay trước trang hiện tại, có thể lấy **khóa của dòng đầu tiên** làm mốc và truy vấn những dòng có khóa lớn hơn, nhưng phải **đảo chiều ORDER BY khi giới hạn kết quả**, rồi đảo thứ tự hiển thị:

~~~sql
-- :first_created_at, :first_id là khóa của dòng đầu ở trang hiện tại.
SELECT id, created_at
FROM orders
WHERE tenant_id = :tenant_id
  AND status = :status
  AND (
       created_at > :first_created_at
       OR (created_at = :first_created_at AND id > :first_id)
      )
ORDER BY created_at ASC, id ASC
LIMIT :page_size_plus_one;
~~~

Kết quả từ DB ở chiều ASC chọn **những dòng gần mốc nhất**, sau đó reverse về DESC để trả client. Nếu lấy ASC rồi không reverse, UI sẽ hiển thị sai thứ tự. Nếu chỉ trả nextCursor, API có thể không hỗ trợ trang trước; điều này đơn giản hơn và thường phù hợp luồng “infinite scroll”.

**Lưu ý:** khi dùng limit + 1 cho trang trước, dòng dư là dấu hiệu còn các trang trước nữa; vẫn phải cắt đúng pageSize và đảo mảng đúng vị trí. API cần phân biệt **nextCursor** và **previousCursor** với payload/cách giải mã rõ ràng, không tái dùng một token cho hai chiều mà không kiểm tra.

Một kỹ thuật khác là **giữ lịch sử cursor trong client** để quay lại các trang đã truy vấn; cách này dễ dùng nhưng dữ liệu có thể thay đổi giữa các lần gọi, nên không tương đương snapshot.

## 14. Kiểm thử đúng thứ tự, đúng biên và đúng quyền

### 14.1. Ma trận kiểm thử

| ID | Kịch bản | Điều kiện kỳ vọng |
| --- | --- | --- |
| K01 | Collection rỗng | HTTP 200; items = []; hasNext = false; nextCursor = null. |
| K02 | Số dòng nhỏ hơn limit | Trả hết dòng, không phát nextCursor. |
| K03 | Số dòng đúng bằng limit | Không tự khẳng định còn trang; hasNext = false khi truy vấn limit+1 không có dòng dư. |
| K04 | Nhiều dòng có cùng created_at | Không mất/lặp do timestamp trùng; tie-breaker ID xác định thứ tự. |
| K05 | Ba trang trở lên, dữ liệu tĩnh | Ghép kết quả đúng thứ tự và đúng tập bản ghi; không trùng ID. |
| K06 | Insert mới ở đầu giữa hai trang | Với khóa bất biến, không lặp dòng đã đọc do dịch offset. |
| K07 | Delete dòng phía trước cursor | Tiếp tục lấy đúng những dòng còn tồn tại sau khóa cursor. |
| K08 | Update khóa sort hoặc đổi status giữa trang | Hành vi được ghi nhận như giới hạn nhất quán; không đưa ra cam kết snapshot giả. |
| K09 | Cursor bị sửa một byte / chữ ký sai | Từ chối 400, không truy vấn dữ liệu ngoài quyền. |
| K10 | Cursor hết hạn / phiên bản không hỗ trợ | Lỗi có type/code ổn định, hướng bắt đầu lại từ trang đầu. |
| K11 | Đổi status, sort hoặc limit khi dùng cursor cũ | Bị từ chối theo hợp đồng, không dùng mốc seek cho filter khác. |
| K12 | Dùng cursor tenant/user khác | Không tiết lộ dữ liệu; quyền được kiểm tra lại. |
| K13 | Limit bằng 0, âm hoặc quá lớn | 400 hoặc xử lý giới hạn được công bố, không chạy truy vấn vô hạn. |
| K14 | Tới trang cuối và tiếp tục gọi | Không trả thêm ID trùng; kết quả phù hợp hợp đồng kết thúc. |
| K15 | Thử sort ASC, DESC và các hướng kết hợp | Predicate seek khớp ORDER BY; không lặp/mất với dữ liệu tĩnh. |
| K16 | Giá trị NULL, timezone, precision và collation | Tuân thủ thứ tự đã công bố hoặc từ chối sort không hỗ trợ. |
| K17 | Khi có rate limit hoặc backend lỗi | 429/5xx đúng mã; client retry GET có giới hạn và bảo mật. |

### 14.2. Bộ dữ liệu biên tối thiểu

Để phát hiện lỗi tie-breaker, tạo ít nhất các dòng sau cho **cùng một tenant/status**:

~~~text
id  created_at
105 2026-11-18T10:05:00Z
104 2026-11-18T10:04:00Z
103 2026-11-18T10:04:00Z
102 2026-11-18T10:04:00Z
101 2026-11-18T10:03:00Z
~~~

Với limit = 2, ba lần gọi phải cho:

~~~text
page 1: [105, 104], hasNext=true, cursor from (10:04:00, 104)
page 2: [103, 102], hasNext=true, cursor from (10:04:00, 102)
page 3: [101],      hasNext=false, nextCursor=null
~~~

Đây là bài thử rất quan trọng: nếu dùng mỗi điều kiện **created_at < last_created_at**, trang 2 sẽ bắt đầu từ 101, bỏ qua 103 và 102. Nếu dùng **created_at <=** mà không có tie-breaker, trang 2 có thể lặp lại 104.

### 14.3. Kiểm thử Spring/JDBC

Với các lớp ở phần 11, một integration test dùng database thật (ví dụ PostgreSQL trong môi trường thử nghiệm) có thể:

~~~java
OrderPage first = repository.list(7L, "PAID", 2, null);
assertThat(first.items()).extracting(OrderRow::id)
        .containsExactly(105L, 104L);
assertThat(first.hasNext()).isTrue();

OrderPage second = repository.list(
        7L, "PAID", 2, first.lastReturnedKey());
assertThat(second.items()).extracting(OrderRow::id)
        .containsExactly(103L, 102L);
assertThat(second.hasNext()).isTrue();

OrderPage third = repository.list(
        7L, "PAID", 2, second.lastReturnedKey());
assertThat(third.items()).extracting(OrderRow::id)
        .containsExactly(101L);
assertThat(third.hasNext()).isFalse();
~~~

Đoạn test dùng **AssertJ** và giả định dữ liệu đã được seed như bảng mẫu. Tách thêm test API để kiểm tra **token ký, status, header, lỗi và quyền**, vì repository test không bao phủ toàn bộ hợp đồng REST. Không cần viết test chỉ lặp lại lời gọi repository: quan trọng nhất là các trường hợp tie-breaker, đồng thời, filter thay đổi và token bị giả mạo.

### 14.4. Kiểm thử hiệu năng

Đo:

- p50/p95/p99 latency của trang đầu và các trang sâu.
- Số rows/index entries đọc so với số dòng trả.
- CPU, buffer hit/miss và thời gian sort khi dữ liệu tăng.
- Tốc độ ký/giải mã token, kích thước URI và tỷ lệ cursor invalid.
- Tỷ lệ 400/403/429/5xx theo route, tenant và nhóm client ở mức được phép.

Chạy thử trên bộ dữ liệu đủ lớn và phản ánh phân bố tenant/status thực tế. Thử thay đổi kích thước trang và index để đánh giá đánh đổi giữa số request, thời gian mỗi request và tải DB.

## 15. Những phản mẫu phổ biến

| Phản mẫu | Vì sao sai? | Cách sửa |
| --- | --- | --- |
| **ORDER BY created_at DESC** rồi seek bằng thời gian duy nhất | Các dòng trùng timestamp có thể bị bỏ sót hoặc lặp. | Thêm ID duy nhất và predicate theo cặp. |
| Dùng **OFFSET** cho feed đang thay đổi | Insert/delete phía trước làm vị trí bị dịch. | Keyset với sort ổn định khi cần duyệt tuần tự. |
| Cursor chứa chỉ số trang số N | Vẫn phụ thuộc offset, không giải quyết chi phí/độ dịch. | Cursor chứa khóa seek hoặc tham chiếu snapshot thực. |
| Lấy cursor từ dòng **LIMIT + 1** | Bỏ qua dòng dư đáng lẽ thuộc trang tiếp. | Lấy khóa của **dòng cuối trả client**. |
| Dùng dấu so sánh sai với DESC/ASC | Trả dữ liệu phía trước hoặc bỏ qua. | Kiểm tra lexicographic predicate theo từng chiều sort. |
| Cho client sửa JSON Base64 của cursor | Có thể thay filter, tenant, giới hạn truy vấn. | Token ký/MAC hoặc opaque có state; kiểm quyền mỗi request. |
| Chỉ tin cursor cũ đã có quyền | Quyền có thể bị thu hồi; token có thể bị chuyển cho người khác. | Ràng buộc scope và xác thực/phân quyền lại. |
| Đổi filter khi giữ cursor | Một mốc seek bị áp vào tập dữ liệu khác. | Ràng buộc filter/sort/limit với cursor và validate. |
| Hứa **snapshot tuyệt đối** khi chỉ dùng keyset | Insert backdated, update/delete vẫn ảnh hưởng. | Công bố tính nhất quán thực hoặc dùng snapshot/job export. |
| Trả totalCount chính xác cho mọi request mà không đo chi phí | COUNT trên tập lớn có thể đắt và không đồng bộ với trang. | Count riêng, ước tính hoặc chỉ dùng hasNext. |
| Đưa tên cột sort từ query vào SQL trực tiếp | Có thể gây injection hoặc truy vấn quá nặng. | Allowlist sort và câu SQL/biểu thức cố định. |
| Dùng timestamp đã làm tròn trong cursor | Equality có thể lệch dữ liệu thật. | Serialize đúng precision từ DB. |

## 16. Bài tập thiết kế: lịch sử giao dịch của nhiều tenant

### Đề bài

Một hệ thống thanh toán có **8 triệu giao dịch**, liên tục nhận thêm dữ liệu. API cần hiển thị lịch sử theo **created_at DESC**. Nhiều giao dịch có timestamp trùng vì xử lý theo lô. Mỗi người dùng chỉ được xem giao dịch trong tenant được cấp quyền. Giao diện di động tải 25 giao dịch mỗi lần và hỗ trợ cuộn vô hạn. Đội sản phẩm muốn thêm filter **status=SUCCESS**, sau này có thể hỗ trợ sort theo số tiền.

Yêu cầu:

1. Lựa chọn offset hay keyset và giải thích.
2. Xác định thứ tự sắp xếp đầy đủ và SQL cho trang sau.
3. Đề xuất payload cursor và cách kiểm tra an toàn.
4. Nêu hành vi khi client đổi filter hoặc người dùng bị thu hồi quyền.
5. Giải thích xem có thể cam kết “mọi giao dịch tồn tại lúc bắt đầu đều xuất hiện đúng một lần” không.
6. Phác thảo index, response và ít nhất năm bài kiểm thử quan trọng.

### Phương án tham khảo

**Lựa chọn:** dùng **keyset** với cursor opaque vì client duyệt tuần tự, khối lượng lớn và dữ liệu liên tục được bổ sung. Đặt thứ tự **created_at DESC, id DESC**, với ID duy nhất. Nếu timestamp là cột không NULL, predicate của trang sau là:

~~~sql
WHERE tenant_id = :tenant_id
  AND status = 'SUCCESS'
  AND (
       created_at < :last_created_at
       OR (created_at = :last_created_at AND id < :last_id)
      )
ORDER BY created_at DESC, id DESC
LIMIT 26;
~~~

**Cursor:** lưu phiên bản định dạng, last_created_at, last_id, định nghĩa sort, filterHash, tenant/subject hoặc scope, page size, expiry; ký xác thực hoặc cấp mã opaque server-side. **Không** đưa số thẻ, token thanh toán, khóa bí mật vào cursor. Mọi request vẫn phải được xác thực và áp đặt filter tenant tại server.

**Khi đổi filter:** yêu cầu client bỏ cursor và lấy trang đầu của bộ lọc mới; nếu cố tái dùng token thì trả 400 có loại lỗi ổn định. **Khi bị thu hồi quyền:** từ chối theo chính sách; cursor cũ không được vượt quyền hiện tại.

**Về nhất quán:** nếu created_at và id bất biến, keyset giúp tránh dịch vị trí do insert ở đầu; nhưng update status, delete hoặc insert có timestamp backdated vẫn có thể thay đổi tập kết quả. Để cam kết đúng tập giao dịch tại một mốc, cần snapshot/materialized ID set hoặc cơ chế xuất dữ liệu có watermark và bằng chứng nhất quán.

**Index gợi ý:** **(tenant_id, status, created_at DESC, id DESC)**, cần kiểm tra bằng EXPLAIN trên dữ liệu đại diện; có thể có index riêng nếu nhiều endpoint bỏ filter status.

**Kiểm thử:** trùng timestamp; insert mới giữa trang; cursor bị sửa; cursor tenant khác; đổi filter; trang cuối; limit vượt ngưỡng; rollback giao dịch và thay đổi status; xác minh p95 latency ở trang sâu.

### Câu hỏi nâng cao

- Nếu muốn sort theo **amount DESC**, có thể thay **created_at** bằng **amount** rồi giữ id tie-breaker không? Nếu amount thay đổi sau khi tạo, điều gì xảy ra?
- Nếu user chuyển giữa tenant A và tenant B nhưng giữ cursor A, server phải xử lý thế nào?
- Nếu cần nhảy tới trang 100 của bảng kết quả tổng hợp bất biến, offset có thể là lựa chọn hợp lý hơn không?
- Nếu API muốn “tiếp tục từ đúng vị trí” trong khi một số transaction bị xóa, chỉ giữ ID có đủ không?

**Gợi ý:** (1) có thể dùng amount + id nếu nhất quán semantics và có index, nhưng amount thay đổi làm dịch vị trí; (2) phải từ chối và kiểm quyền; (3) có thể, nếu dữ liệu/snapshot và chi phí cho phép; (4) cần giữ toàn bộ sort tuple, không chỉ ID, trừ khi ID chính là khóa sort được dùng.

## 17. Checklist trước khi phát hành cursor pagination

- [ ] Đã chọn đúng trường hợp sử dụng: cuộn tuần tự hay cần truy cập trang ngẫu nhiên.
- [ ] ORDER BY có thứ tự xác định, kết thúc bằng khóa phá hòa duy nhất.
- [ ] Các cột sort có quy tắc NULL, timezone, precision và collation rõ ràng.
- [ ] Predicate seek đúng cho mọi chiều ASC/DESC được hỗ trợ.
- [ ] Trang đầu và trang sau lọc, phân quyền và sắp xếp nhất quán.
- [ ] Truy vấn lấy **limit + 1** và tạo cursor từ **dòng cuối trả client**.
- [ ] API có limit mặc định, giá trị tối đa và xử lý collection rỗng/trang cuối bằng HTTP 200.
- [ ] Cursor là opaque với client, có phiên bản, expiry và kiểm tra tính toàn vẹn.
- [ ] Cursor ràng buộc filter, sort, limit và phạm vi dữ liệu; quyền được kiểm tra lại.
- [ ] Không lộ PII trong cursor/URL/log; khóa ký có quy trình quản lý và xoay vòng.
- [ ] SQL sử dụng tham số và allowlist sort; không ghép tên cột từ đầu vào không tin cậy.
- [ ] Đã đánh giá index và kế hoạch thực thi trên dữ liệu lớn, kể cả trang sâu.
- [ ] Tính nhất quán khi insert/update/delete được công bố đúng, không hứa snapshot khi không có cơ chế bảo đảm.
- [ ] OpenAPI mô tả items, page, nextCursor và các lỗi như invalid/expired cursor.
- [ ] Đã kiểm thử timestamp trùng, trang cuối, filter đổi, quyền bị thu hồi, cursor giả mạo và dữ liệu thay đổi.
- [ ] Client có cách bắt đầu lại khi cursor hết hạn, và không coi token là giá trị có thể tự chỉnh sửa.

**Điểm cần nhớ:** phân trang keyset đi tiếp từ **giá trị khóa sắp xếp**, không đi tiếp từ **vị trí dòng**. Muốn làm đúng phải xây một thứ tự **duy nhất và ổn định** như **(created_at DESC, id DESC)**, dùng điều kiện seek tương ứng, và đóng gói mốc này trong cursor được kiểm tra an toàn. Cursor làm API dễ sử dụng; keyset làm truy vấn hiệu quả và ít bị dịch bởi thay đổi ở đầu danh sách; cả hai vẫn cần hợp đồng rõ về filter, phân quyền và mức nhất quán khi dữ liệu thay đổi.
