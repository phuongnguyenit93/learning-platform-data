# Bài toán mất cập nhật (lost update) khi nhiều client cùng sửa tài nguyên

> **Phạm vi:** Bài học thuộc module **INTEGRATION_API_REST**, chương **Điều kiện và đồng thời**. Người học tìm hiểu cách nhiều client đọc và sửa cùng một REST resource, vì sao xảy ra **lost update**, cách dùng conditional requests (`ETag`, `If-Match`), mã HTTP phù hợp và cơ chế cập nhật có kiểm soát bằng Java/Spring hoặc công nghệ tương đương. Bài liên hệ với URI, resource representation, PATCH/PUT, OpenAPI, bảo mật, idempotency, cache và kiểm thử API.

## 1. Tình huống mở đầu: hai người sửa cùng một bản nháp

Một nhân viên chăm sóc khách hàng (client A) và chủ đơn (client B) cùng truy cập bản nháp đơn hàng `ord_916`. Resource công khai tại `GET /v1/order-drafts/ord_916` có dữ liệu:

~~~json
{
  "id": "ord_916",
  "shippingAddress": "12 Nguyễn Trãi",
  "deliveryNote": "Giao giờ hành chính",
  "status": "DRAFT"
}
~~~

Tại thời điểm đầu, cả hai người đều đọc phiên bản hiện tại. Client A đổi `shippingAddress`. Client B dựa trên bản dữ liệu cũ, đổi `deliveryNote` nhưng gửi lại **toàn bộ object**. Nếu server chỉ ghi đè dữ liệu cuối cùng mà không kiểm tra phiên bản, thao tác của B có thể phục hồi địa chỉ cũ, làm mất thay đổi của A.

~~~mermaid
sequenceDiagram
    participant A as Client A
    participant S as REST API / DB
    participant B as Client B
    A->>S: GET /order-drafts/ord_916
    S-->>A: 200: address=12, note=giờ hành chính
    B->>S: GET /order-drafts/ord_916
    S-->>B: 200: address=12, note=giờ hành chính
    A->>S: PUT address=58, note=giờ hành chính
    S-->>A: 200: cập nhật thành công
    B->>S: PUT address=12, note=để trước cửa
    S-->>B: 200: cập nhật thành công
    Note over S: Giá trị address=58 của A đã bị ghi đè thành 12
~~~

**Lost update** là tình huống một cập nhật có ý nghĩa đã thành công trước đó bị một cập nhật khác dựa trên trạng thái lỗi thời ghi đè, mà hệ thống không phát hiện hoặc không xử lý xung đột phù hợp.

Trước khi đi vào kỹ thuật, hãy phân biệt:

- Hai người sửa cùng một tài nguyên **không nhất thiết** gây lost update. Nếu thay đổi được áp dụng nguyên tử và không xung đột, hệ thống có thể giữ cả hai.
- Lost update **không phải** chỉ là “một request nhận lỗi HTTP”. Nguy hiểm nhất là cả hai client đều được báo thành công, nhưng một thay đổi đã biến mất.
- `Last write wins` là một chính sách có thể chọn **nếu sản phẩm chấp nhận mất thay đổi trước**, chứ không nên là tác dụng phụ không được tài liệu hóa của persistence.

### 1.1. Mục tiêu học tập

Sau bài này, người học có thể:

1. Mô tả timeline của lost update trong REST, kể cả khi các request HTTP riêng lẻ đều hợp lệ.
2. Phân biệt optimistic concurrency control, pessimistic locking, last-write-wins và idempotency.
3. Đọc và gửi strong `ETag` cùng `If-Match` để cập nhật có điều kiện.
4. Chọn đúng `412 Precondition Failed`, `428 Precondition Required`, `409 Conflict`, `404`, `403` và các status thành công.
5. Bảo đảm precondition được kiểm tra **cùng với việc ghi** bằng version/CAS hoặc optimistic locking của database.
6. Thiết kế trải nghiệm client khi phát hiện dữ liệu đã đổi, tránh retry ghi đè vô thức.
7. Triển khai ví dụ Java/Spring, mô tả OpenAPI và kiểm thử hai request cạnh tranh một cách xác định.

## 2. Vì sao REST API dễ gặp lost update?

HTTP cho phép nhiều client gửi request đồng thời. Một resource có URI riêng không đồng nghĩa server tự bảo vệ sự kiện **“đọc ở phiên bản cũ rồi ghi ở phiên bản mới”**.

Một đường đi phổ biến:

~~~text
T0: DB có draft {address=A0, note=N0, version=7}
T1: Client A GET và nhớ representation version 7
T2: Client B GET và nhớ representation version 7
T3: Client A PUT {address=A1, note=N0}; DB trở thành version 8
T4: Client B PUT {address=A0, note=N1}; DB trở thành version 9
T5: Client A tưởng thay đổi A1 còn được giữ; thực tế address=A0
~~~

Lưu ý: transaction của một lần PUT **có thể hoàn toàn ACID** nhưng vẫn không giải quyết lỗi này. Mỗi request độc lập đều commit hợp lệ; vấn đề là thao tác thứ hai được xây dựng từ dữ liệu đọc **trước** thay đổi thứ nhất, nhưng hệ thống không kiểm tra phiên bản ban đầu của client.

### 2.1. Phạm vi của một HTTP request khác phạm vi phiên chỉnh sửa

Client có thể mở form trong vài phút; nhiều client khác vẫn chỉnh dữ liệu. Giữ transaction DB mở từ lúc GET cho đến khi người dùng bấm Save là phương án tốn kết nối, khóa và dễ timeout. Mô hình phổ biến hơn là:

1. GET tài nguyên, nhận **validator** đại diện cho phiên bản đã đọc.
2. Người dùng chỉnh sửa ở client, không giữ khóa DB suốt phiên.
3. Client gửi thay đổi **kèm điều kiện phiên bản**.
4. Server chỉ ghi khi trạng thái hiện tại còn thỏa điều kiện; nếu không, **từ chối cập nhật lỗi thời**.

Đây là **optimistic concurrency control (OCC)** ở giao diện HTTP, có thể thực thi bằng optimistic locking/version của database.

### 2.2. PUT, PATCH và POST có tự chống lost update không?

| Method | Ý nghĩa chính | Khả năng lost update nếu không có điều kiện |
|---|---|---|
| `PUT` | Thay thế trạng thái resource đích theo representation được định nghĩa | **Cao** khi client gửi dữ liệu đầy đủ từ một bản cũ |
| `PATCH` | Áp dụng một thay đổi theo patch document cụ thể | **Vẫn có** khi cùng field bị sửa hoặc patch phụ thuộc dữ liệu cũ |
| `POST` | Xử lý request theo ngữ nghĩa tài nguyên đích | Có thể có nếu command đổi dữ liệu cạnh tranh mà không kiểm tra trạng thái |
| `DELETE` | Yêu cầu xóa resource đích | Có thể xóa resource đã đổi kể từ lần client đọc |
| `GET` | Đọc tài nguyên; không chủ ý thay đổi trạng thái nghiệp vụ | Không tạo lost update, nhưng là nguồn representation có thể lỗi thời |

PUT có tính **idempotent theo ngữ nghĩa HTTP** khi cùng request được áp dụng lặp lại, nhưng **idempotent không có nghĩa an toàn trước cạnh tranh**. Cùng một PUT gửi hai lần có thể đưa resource về cùng một trạng thái mong muốn, còn một PUT của client khác ở giữa vẫn có thể bị ghi đè.

### 2.3. Lost update khác các vấn đề đồng thời khác

| Vấn đề | Ví dụ | Điểm phân biệt |
|---|---|---|
| **Lost update** | Hai người sửa một bản nháp; thay đổi của người trước biến mất | Ghi đè thay đổi được xây từ bản đọc cũ |
| **Dirty read** | Đọc dữ liệu từ transaction chưa commit | Vấn đề isolation của transaction DB |
| **Non-repeatable read** | Cùng transaction đọc một row hai lần ra giá trị khác | Thay đổi giữa các lần đọc |
| **Write skew** | Hai transaction cập nhật hai row khác nhau và cùng phá invariant liên row | Không nhất thiết cùng sửa một row |
| **Duplicate side effect** | Client retry tạo hai đơn hoặc thu tiền hai lần | Vấn đề lặp tác động/idempotency, có thể xảy ra dù không lost update |
| **Stale read** | Client nhìn thấy bản cũ từ cache/replica | Dữ liệu cũ có thể dẫn tới lost update nếu server không kiểm điều kiện |

Không dùng một biện pháp để tuyên bố giải quyết mọi vấn đề trên. `If-Match` rất thích hợp chống ghi đè từ representation lỗi thời; bất biến liên nhiều tài nguyên còn cần transaction, isolation, constraint hoặc phối hợp nghiệp vụ riêng.

## 3. Bốn chiến lược kiểm soát cập nhật

### 3.1. Last-write-wins (LWW)

Server cứ ghi request mới nhất theo thứ tự xử lý, không biết client dựa vào phiên bản nào.

**Ưu điểm:** đơn giản, ít lỗi conflict mà client phải xử lý.

**Nhược điểm:** mất thay đổi trong im lặng; khó điều tra; nếu thứ tự request phụ thuộc mạng/queue/replica, “mới nhất” không đồng nghĩa “đúng nhất”. Chỉ nên dùng khi nghiệp vụ chấp nhận mất cập nhật và thiết kế UI nói rõ.

### 3.2. Optimistic concurrency với version / ETag

Mỗi representation có validator. Client gửi lại validator khi thay đổi. Nếu resource đã đổi, server không ghi và trả **`412 Precondition Failed`** cho `If-Match` không thỏa. Client có thể tải bản mới, so sánh và quyết định.

**Phù hợp:** API CRUD và tài nguyên được chỉnh không quá thường xuyên, form người dùng, mobile client hoạt động nhiều phiên, đa instance API.

**Đánh đổi:** client phải giữ validator và xử lý conflict; DB/backend phải hỗ trợ thao tác so sánh và ghi nguyên tử. Không chỉ so sánh ETag trong controller rồi save tùy ý.

### 3.3. Pessimistic locking

Server khóa row hoặc tài nguyên trong một transaction ngắn để thao tác không chồng nhau. Cách này phù hợp phần xử lý DB có tính tranh chấp cao, nhưng **không nên giữ DB lock suốt thời gian người dùng chỉnh form**. Khóa đúng phạm vi có thể kết hợp với version check khi ghi.

### 3.4. Gộp thay đổi có ngữ nghĩa (merge/commutative operations)

Nếu hai thay đổi **thực sự độc lập**, hệ thống có thể áp dụng cả hai theo quy tắc rõ ràng. Ví dụ một PATCH chỉ cập nhật `deliveryNote` và một PATCH khác chỉ cập nhật `shippingAddress`, với update từng cột nguyên tử. Tuy nhiên, hai request sửa **cùng một field** vẫn xung đột; ngay cả field khác nhau cũng có thể phá invariant liên quan (địa chỉ và phí vận chuyển).

Không tự khẳng định mọi PATCH đều “tránh lost update”. Việc chọn merge hay từ chối cần dựa trên **ngữ nghĩa domain**, không chỉ khác tên property.

## 4. HTTP validator: `ETag` là dấu hiệu phiên bản của representation

`ETag` (entity tag) là một validator do server phát hành để client nhận diện một representation cụ thể. Nó là một giá trị **opaque** đối với client: không parse ra version, không tính toán thêm và không suy ra định danh tài nguyên từ nó.

~~~http
GET /v1/order-drafts/ord_916 HTTP/1.1
Host: api.example.test
Authorization: Bearer <access-token>
Accept: application/json
~~~

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
ETag: "draft-916-v7"
Cache-Control: private, no-store

{
  "id": "ord_916",
  "shippingAddress": "12 Nguyễn Trãi",
  "deliveryNote": "Giao giờ hành chính",
  "status": "DRAFT"
}
~~~

Client phải lưu chính xác chuỗi validator có dấu nháy như `"draft-916-v7"` để gửi lại trong `If-Match`. Giá trị `draft-916-v7` chỉ mang tính ví dụ; thực tế server có thể dùng hash, token phiên bản hoặc giá trị khác. **Không buộc client biết cơ chế tạo ETag.**

### 4.1. Strong ETag và weak ETag

| Validator | Cú pháp | Ý nghĩa và cách dùng |
|---|---|---|
| **Strong ETag** | `ETag: "draft-916-v7"` | Đại diện cho một validator mạnh, dùng được để so khớp bằng `If-Match` |
| **Weak ETag** | `ETag: W/"draft-916-v7"` | Cho biết tính tương đương yếu theo ngữ nghĩa ứng dụng, không đáp ứng so khớp mạnh của `If-Match` |

HTTP định nghĩa `If-Match` dùng **strong comparison**. Vì vậy:

~~~http
If-Match: "draft-916-v7"
~~~

có thể khớp current strong ETag cùng giá trị, còn:

~~~http
If-Match: W/"draft-916-v7"
~~~

**không được** coi là khớp mạnh với strong ETag tương tự. Một API hỗ trợ optimistic locking thông qua `If-Match` nên phát strong validator cho representation có thể sửa.

### 4.2. Khi nào version database đủ để tạo strong ETag?

Sử dụng `@Version` trong JPA là một cách tốt để kiểm soát ghi cạnh tranh, nhưng **một version cột không mặc nhiên là strong ETag hợp lệ trong mọi thiết kế**. Hãy xem:

- Response có chỉ chứa field của một entity được cập nhật version khi mọi field đó đổi không?
- Có projection từ bảng/đối tác khác, dữ liệu phụ thuộc locale, định dạng hoặc quyền caller không?
- Nội dung JSON có thể thay đổi mà version entity **không đổi** không?
- Các representation khác nhau (ngôn ngữ, encoding, media type) có cùng ETag dù khác dữ liệu không?

Để phát một **strong validator** đúng nghĩa, server phải đảm bảo validator thay đổi khi representation cần so sánh mạnh thay đổi. Có thể dùng hash của representation thực tế hoặc một token phiên bản phản ánh **tất cả phụ thuộc** của representation. Nếu chưa thể bảo đảm, không gắn nhãn strong chỉ vì có số version; cân nhắc điều chỉnh representation hoặc chiến lược validator.

**Ví dụ code ở các mục sau** giả định một JSON representation đơn nhất của draft, mọi thay đổi liên quan đến representation đều làm tăng version trong cùng transaction và ETag được xây ổn định từ version. Nếu response còn kết hợp dữ liệu ngoài, phải sửa cách tạo validator/thiết kế resource.

### 4.3. ETag không phải token phân quyền

ETag có thể xuất hiện ở cache, log hoặc request. Nó không nên chứa secret, dữ liệu cá nhân hay thông tin nội bộ có thể gây hại khi lộ. Client có ETag hợp lệ **không có nghĩa** có quyền sửa resource: server vẫn phải xác thực và kiểm tra tenant/owner, trạng thái nghiệp vụ và quyền cập nhật.

## 5. `If-Match`: gửi thay đổi chỉ nếu resource còn khớp

Sau khi GET với ETag `"draft-916-v7"`, client A gửi:

~~~http
PATCH /v1/order-drafts/ord_916 HTTP/1.1
Host: api.example.test
Authorization: Bearer <access-token>
Content-Type: application/merge-patch+json
If-Match: "draft-916-v7"

{"shippingAddress":"58 Lê Lợi"}
~~~

Server xác minh validator còn khớp với representation hiện hành. Nếu khớp và update thành công:

~~~http
HTTP/1.1 204 No Content
ETag: "draft-916-v8"
Cache-Control: no-store
~~~

Ở đây `204` hợp lệ vì PATCH đã xử lý thành công và response không có body; ETag mới cho client biết validator của representation sau cập nhật, **theo giả định server phát đúng validator**. Server cũng có thể trả `200 OK` cùng representation mới và ETag.

Client B đang giữ `"draft-916-v7"`, gửi:

~~~http
PATCH /v1/order-drafts/ord_916 HTTP/1.1
Host: api.example.test
Authorization: Bearer <access-token>
Content-Type: application/merge-patch+json
If-Match: "draft-916-v7"

{"deliveryNote":"Để trước cửa"}
~~~

Current ETag đã là `"draft-916-v8"` nên điều kiện sai:

~~~http
HTTP/1.1 412 Precondition Failed
Content-Type: application/problem+json
Cache-Control: no-store

{
  "type": "https://api.example.test/problems/stale-resource",
  "title": "Resource has changed",
  "status": 412,
  "code": "STALE_EDIT",
  "detail": "Bản nháp đã thay đổi. Hãy tải phiên bản mới trước khi lưu."
}
~~~

**Kết quả đúng:** yêu cầu của B **không ghi đè** address mới của A. Client B có thể GET lại draft, hiển thị khác biệt hoặc áp dụng lại thay đổi của mình lên bản mới nếu người dùng xác nhận.

### 5.1. Timeline chống lost update

~~~mermaid
sequenceDiagram
    participant A as Client A
    participant S as API
    participant DB as Database
    participant B as Client B
    A->>S: GET /drafts/ord_916
    S-->>A: 200 + ETag "v7"
    B->>S: GET /drafts/ord_916
    S-->>B: 200 + ETag "v7"
    A->>S: PATCH If-Match "v7"
    S->>DB: UPDATE ... WHERE version=7
    DB-->>S: affected rows = 1, version=8
    S-->>A: 204 + ETag "v8"
    B->>S: PATCH If-Match "v7"
    S->>DB: UPDATE ... WHERE version=7
    DB-->>S: affected rows = 0
    S-->>B: 412 Precondition Failed
    B->>S: GET /drafts/ord_916
    S-->>B: 200 + ETag "v8" + dữ liệu mới
~~~

Trong sơ đồ `"v7"`/`"v8"` chỉ là nhãn rút gọn. Điểm bảo đảm không nằm ở sơ đồ client, mà ở **UPDATE có điều kiện nguyên tử hoặc optimistic locking tương đương**.

### 5.2. Điều kiện `If-Match` được kiểm tra ra sao?

Nếu request có `If-Match`, server đánh giá validator so với **representation được chọn cho tài nguyên đích** theo ngữ nghĩa HTTP; với entity tags, dùng strong comparison. Điều kiện là đúng khi ít nhất một strong tag trong danh sách khớp current tag; wildcard `*` có nghĩa có representation hiện tại của resource, **không phải** “phiên bản tôi vừa đọc vẫn còn”.

~~~http
If-Match: "v7", "v8"
If-Match: *
~~~

Đây là cú pháp HTTP hợp lệ trong các trường hợp thích hợp, nhưng một API dành cho chỉnh sửa không mất dữ liệu có thể **quy định chỉ nhận một strong ETag cụ thể** trong giao diện lưu form. `If-Match: *` không đủ để ngăn lost update, vì nó chỉ đòi resource hiện tồn tại. Nếu giới hạn cú pháp như vậy, hãy tài liệu hóa và trả lỗi request phù hợp cho giá trị không được hỗ trợ; không diễn giải `*` thành phiên bản mới nhất.

### 5.3. Phân biệt `If-Match` và `If-None-Match`

| Header | Mục đích thường gặp | Loại so khớp cho ETag |
|---|---|---|
| `If-Match` | Chỉ thay đổi nếu validator hiện tại khớp; tránh lost update | **Strong comparison** |
| `If-None-Match` | Conditional GET để không tải lại body khi cache còn hợp lệ; `*` có thể dùng tạo resource chỉ nếu chưa tồn tại | **Weak comparison** |

Ví dụ conditional GET:

~~~http
GET /v1/order-drafts/ord_916 HTTP/1.1
Host: api.example.test
If-None-Match: "draft-916-v8"
Authorization: Bearer <access-token>
~~~

Nếu representation phù hợp chưa đổi và các điều kiện khác đúng, server có thể trả:

~~~http
HTTP/1.1 304 Not Modified
ETag: "draft-916-v8"
Cache-Control: private, max-age=10
~~~

`304` nói về xác thực cache cho request GET/HEAD, **không phải kết quả khi `If-Match` thất bại trên PATCH**. Với thay đổi không qua precondition, `If-None-Match: *` có thể bảo vệ một PUT mang nghĩa create-if-absent, nhưng logic đó khác với “tôi đang sửa version nào”.

### 5.4. `Last-Modified` và `If-Unmodified-Since`

Một lựa chọn khác là dùng:

~~~http
Last-Modified: Wed, 18 Nov 2026 09:00:00 GMT
~~~

Client gửi `If-Unmodified-Since` để chỉ sửa nếu resource chưa đổi kể từ thời điểm cho trước. Cách này dễ gặp vấn đề về **độ phân giải thời gian**, đồng hồ và nhiều cập nhật trong cùng một giây; nên ưu tiên strong ETag/If-Match cho form dễ tranh chấp. Theo thứ tự đánh giá điều kiện HTTP, nếu `If-Match` có mặt thì `If-Unmodified-Since` bị bỏ qua cho mục đích đánh giá precondition tương ứng; không nên tự kết hợp tùy tiện rồi đổi nghĩa chuẩn.

## 6. Mã trạng thái HTTP: lỗi nào tương ứng tình huống nào?

| Tình huống | Status thường phù hợp | Ghi chú |
|---|---|---|
| GET hiện tại thành công | `200 OK` + representation, ETag | Client lưu validator |
| GET conditional khớp cache | `304 Not Modified` | Chỉ áp dụng đúng điều kiện GET/HEAD |
| Tạo resource thành công | `201 Created` + Location | Nếu tạo tài nguyên mới theo hợp đồng |
| PATCH/PUT thành công và có body | `200 OK` | Có thể trả ETag/representation mới |
| PATCH/PUT thành công không body | `204 No Content` | Không gửi body trong 204 |
| `If-Match` đã gửi nhưng không khớp | **`412 Precondition Failed`** | Phải không ghi đè khi điều kiện sai; có ngoại lệ chuẩn cho yêu cầu đã thực hiện trước đó như ghi chú bên dưới |
| API yêu cầu conditional write, request không gửi precondition | **`428 Precondition Required`** | Chính sách API bắt buộc kiểm tra phiên bản |
| Không thể cập nhật do **trạng thái nghiệp vụ** | `409 Conflict` | Ví dụ draft đã xác nhận, không được đổi địa chỉ dù validator mới |
| Request body/cú pháp không hợp lệ | `400 Bad Request` hoặc `422 Unprocessable Content` theo quy ước | Phân biệt với xung đột phiên bản |
| Không được xác thực hoặc không có quyền | `401` / `403` | Precondition không thay thế authorization |
| Không tìm thấy hoặc không công bố resource | `404 Not Found` | Có thể che sự tồn tại theo chính sách |
| Quá nhiều request | `429 Too Many Requests` | Client backoff; không coi 429 là version conflict |
| Backend tạm thời không đáp ứng | `503 Service Unavailable` | Không tự retry ghi vô điều kiện |

**Lưu ý chính xác:** HTTP cho phép ngoại lệ khi điều kiện `If-Match` hiện không đúng nhưng server xác định request thay đổi trạng thái **đã thành công trước đó** (ví dụ request trùng sau khi response bị mất) và trả status thành công theo các ràng buộc của giao thức. Đừng biến ngoại lệ này thành lối tắt “nếu không khớp cứ ghi lại”. Hợp đồng bài học chọn cách đơn giản: một stale edit mới nhận `412`; retry một request cũ phải được thiết kế riêng bằng idempotency/dedupe nếu cần.

### 6.1. Khi nào `428 Precondition Required`?

Nếu endpoint bảo vệ việc chỉnh sửa bằng phiên bản, request không có `If-Match`:

~~~http
PATCH /v1/order-drafts/ord_916 HTTP/1.1
Host: api.example.test
Content-Type: application/merge-patch+json
Authorization: Bearer <access-token>

{"deliveryNote":"Để trước cửa"}
~~~

Phản hồi:

~~~http
HTTP/1.1 428 Precondition Required
Content-Type: application/problem+json
Cache-Control: no-store

{
  "type": "https://api.example.test/problems/precondition-required",
  "title": "Precondition required",
  "status": 428,
  "code": "IF_MATCH_REQUIRED",
  "detail": "Hãy GET tài nguyên và gửi strong ETag bằng If-Match."
}
~~~

`428` cho biết **server yêu cầu request có điều kiện**. `412` cho biết **điều kiện đã gửi không thỏa**. Không tráo đổi hai status để client có thể hiển thị đúng cách sửa.

### 6.2. Khi nào `409 Conflict`?

Ngay cả khi client gửi current ETag, nghiệp vụ vẫn có thể chặn chỉnh sửa. Ví dụ bản nháp đã được xác nhận thành đơn:

~~~http
HTTP/1.1 409 Conflict
Content-Type: application/problem+json

{
  "type": "https://api.example.test/problems/draft-not-editable",
  "title": "Draft is no longer editable",
  "status": 409,
  "code": "DRAFT_NOT_EDITABLE",
  "detail": "Đơn đã được xác nhận nên không thể đổi địa chỉ theo thao tác này."
}
~~~

Nếu `If-Match` đã không khớp ngay từ đầu, kết quả HTTP về precondition thông thường là `412` theo thứ tự đánh giá điều kiện; sau khi điều kiện khớp, server vẫn phải đánh giá luật nghiệp vụ có thể dẫn tới `409`. Đừng lộ trạng thái hoặc thông tin của resource ngoài quyền chỉ để giải thích conflict.

## 7. Bảo đảm quan trọng: kiểm tra phiên bản phải nguyên tử với việc ghi

Một controller làm như sau **vẫn sai** nếu không có cơ chế đồng bộ:

~~~java
// PHẢN MẪU: kiểm tra rồi ghi rời rạc, có cửa sổ race.
OrderDraft draft = repository.findById(id).orElseThrow();
if (!ifMatch.equals(makeEtag(draft.getVersion()))) {
    throw new StaleEditException();
}
// Client khác có thể ghi giữa dòng kiểm tra và dòng save.
draft.setDeliveryNote(request.note());
repository.save(draft);
~~~

Hai request đồng thời có thể cùng đọc version 7, cùng vượt qua câu `if`, rồi ghi đè nhau. **Check-then-act** không nguyên tử là lỗi TOCTOU (time-of-check to time-of-use).

### 7.1. Cập nhật có điều kiện kiểu compare-and-swap

Một cách minh họa bằng SQL:

~~~sql
UPDATE order_drafts
SET delivery_note = :new_note,
    version = version + 1
WHERE public_id = :public_id
  AND tenant_id = :tenant_from_auth
  AND owner_id = :owner_from_auth
  AND version = :expected_version
  AND status = 'DRAFT';
~~~

Server kiểm tra số row cập nhật:

- **1 row:** precondition/version và điều kiện nghiệp vụ trong `WHERE` thỏa; transaction cập nhật thành công.
- **0 row:** có thể resource đã thay đổi, bị xóa, ngoài phạm vi quyền hoặc không còn `DRAFT`. Server cần chính sách phân loại lỗi phù hợp mà **không làm lộ dữ liệu ngoài quyền**; không tự kết luận mọi trường hợp đều là stale update.

Điểm mấu chốt: DB thực hiện việc so sánh version và cập nhật trong **một thao tác nguyên tử**. Tùy DB/transaction, cần bảo đảm việc đọc kết quả sau ghi, commit, trigger, outbox và các thay đổi phụ cũng được tổ chức nhất quán.

### 7.2. Optimistic locking của JPA

JPA có thể dùng:

~~~java
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Version;

@Entity
public class OrderDraftEntity {
    @Id
    private Long id;

    private String publicId;
    private String tenantId;
    private String ownerId;
    private String status;
    private String shippingAddress;
    private String deliveryNote;

    @Version
    private long version;

    // Getter/setter và mapping được lược bỏ cho ngắn gọn.
}
~~~

Trong transaction, JPA dùng version để phát hiện việc row đã đổi giữa lúc đọc và flush/commit. Một trong hai thao tác cạnh tranh có thể nhận `OptimisticLockException` (hoặc exception tương ứng đã được Spring dịch sang loại khác). Server ánh xạ **version conflict của conditional write** sang `412`, không trả stack trace hoặc lỗi `500` cho client.

**Điều kiện:** các thành phần ghi khác cũng phải tôn trọng version discipline; một câu native SQL update bỏ qua version hoặc một batch job cập nhật cột nằm trong representation mà không tăng version có thể phá bảo đảm. Đừng tin rằng chỉ thêm `@Version` vào entity là tự động bảo vệ mọi đường ghi khác của hệ thống.

### 7.3. Phân biệt validator công khai và khóa DB

Client chỉ biết strong ETag như `"draft-916-v7"`. Server có thể ánh xạ nó đến version 7 hoặc kiểm tra với fingerprint representation, nhưng client không cần và không nên biết cách làm này. Trong backend:

~~~text
HTTP If-Match (opaque ETag)
       -> nhận diện validator mạnh
       -> kiểm tra representation phiên bản client đã đọc
       -> optimistic lock/CAS trên dữ liệu thực
       -> commit + tạo ETag mới
       -> trả 200/204 hoặc 412 nếu xung đột
~~~

Nếu có nhiều nguồn dữ liệu cùng tạo nên representation, việc kiểm tra một row DB là chưa đủ: hãy thiết kế ranh giới phiên bản đúng với resource công khai hoặc chọn resource/representation nhỏ hơn có thể khóa/validate một cách nhất quán.

## 8. PATCH và PUT: chọn mức thay đổi theo nghiệp vụ

### 8.1. PUT thay thế representation có thể vô tình phục hồi field cũ

Một PUT thay thế đầy đủ thường mang theo các field client đã đọc trước khi chỉnh:

~~~http
PUT /v1/order-drafts/ord_916 HTTP/1.1
Content-Type: application/json
If-Match: "draft-916-v7"

{
  "shippingAddress": "12 Nguyễn Trãi",
  "deliveryNote": "Để trước cửa"
}
~~~

Nếu version 8 đã chứa địa chỉ `58 Lê Lợi`, server phải từ chối `412` thay vì phục hồi `12 Nguyễn Trãi`. Ngoài ra, API phải xác định những field nào thuộc **trạng thái có thể thay thế bằng PUT**; không cho client gán trạng thái thanh toán, owner hoặc thời gian tạo chỉ vì chúng có trong JSON GET.

### 8.2. PATCH giảm payload nhưng không tự giải quyết cạnh tranh

Ví dụ JSON Merge Patch:

~~~http
PATCH /v1/order-drafts/ord_916 HTTP/1.1
Content-Type: application/merge-patch+json
If-Match: "draft-916-v7"

{"deliveryNote":"Để trước cửa"}
~~~

Chỉ `deliveryNote` được yêu cầu đổi. Nếu client A sửa `shippingAddress`, một patch tối thiểu theo field có thể giữ cả hai thay đổi **nếu domain cho phép và backend xử lý nguyên tử**. Nhưng:

- Hai client sửa chính `deliveryNote` vẫn có thể ghi đè.
- Địa chỉ và ghi chú giao hàng có thể có invariant liên quan; áp dụng riêng từng field không luôn an toàn.
- JSON Merge Patch có quy tắc `null` mang ý nghĩa xóa trường trong object; mảng thường bị thay thế, không merge theo từng phần tử.
- JSON Patch (`application/json-patch+json`) có dạng operation list khác và có thể sử dụng `test` để thể hiện precondition ở payload. Điều đó không mặc nhiên thay thế chiến lược conditional request/version của cả resource.

Đối với bài toán chỉnh form, dùng `If-Match` dù là PUT hay PATCH giúp server chặn các thay đổi dựa trên representation đã cũ. Nếu muốn tự động gộp field khác nhau, hãy xây quy tắc merge có chủ đích và chứng minh invariant nghiệp vụ vẫn đúng.

### 8.3. Một số thao tác nên là command riêng

Ví dụ “xác nhận thanh toán” hoặc “hủy đơn đã tạo” không phải chỉ cập nhật `status` thông qua PATCH. Các lệnh nghiệp vụ có xác thực và bất biến riêng, có thể có idempotency và xử lý bất đồng bộ. Trong trường hợp đó vẫn cần giải quyết tranh chấp tài nguyên, nhưng không nên để client tự set mọi state.

## 9. Java/Spring: kiến trúc mẫu bảo vệ thao tác sửa

Ví dụ tập trung vào một resource draft có **một representation JSON được hỗ trợ**, có trường người dùng được phép sửa là `shippingAddress` và `deliveryNote`. Để dễ thấy ngữ nghĩa replace, endpoint dùng `PUT` với **DTO chỉnh sửa đầy đủ**, không dùng trực tiếp JPA entity. Các class được minh họa từng phần; để chạy như một ứng dụng thật phải cấu hình Spring MVC, Validation, Security, database, repository, transaction và exception handler.

### 9.1. Định nghĩa DTO riêng với persistence

~~~java
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

public record ReplaceDraftRequest(
    @NotBlank @Size(max = 200) String shippingAddress,
    @Size(max = 500) String deliveryNote
) {}

public record DraftResponse(
    String id,
    String shippingAddress,
    String deliveryNote,
    String status
) {}

// DTO trả về từ application service kèm validator.
// ETag là opaque ở HTTP layer; không cần public field "version".
public record VersionedDraft(
    DraftResponse response,
    String strongEtag
) {}
~~~

Các field `id`, `status`, `ownerId`, `tenantId`, `version` và `internalNote` **không** nằm trong request DTO. Client không được điều khiển chúng bằng thao tác PUT. Nếu API chọn PUT thay thế toàn resource với representation khác, hợp đồng phải công bố đầy đủ trường nào client có quyền thay đổi và giá trị nào server kiểm soát.

Với DTO này, `deliveryNote == null` được định nghĩa là không có ghi chú trong **replacement request**; không phải “giữ nguyên” như một số người nhầm khi dùng PATCH. Khi cần thay đổi một field độc lập, có thể thiết kế PATCH rõ media type, nhưng vẫn áp dụng precondition.

### 9.2. HTTP controller: GET phát ETag, PUT yêu cầu If-Match

~~~java
import java.security.Principal;
import jakarta.validation.Valid;
import org.springframework.http.CacheControl;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/v1/order-drafts")
public class OrderDraftController {
    private final OrderDraftService drafts;

    public OrderDraftController(OrderDraftService drafts) {
        this.drafts = drafts;
    }

    @GetMapping("/{id}")
    public ResponseEntity<DraftResponse> read(
            @PathVariable String id, Principal principal) {
        VersionedDraft current =
            drafts.readAuthorized(principal.getName(), id);
        return ResponseEntity.ok()
            .eTag(current.strongEtag())
            .cacheControl(CacheControl.noStore())
            .body(current.response());
    }

    @PutMapping(path = "/{id}", consumes = "application/json")
    public ResponseEntity<DraftResponse> replace(
            @PathVariable String id,
            @RequestHeader(value = "If-Match", required = false)
                String ifMatch,
            @Valid @RequestBody ReplaceDraftRequest request,
            Principal principal) {
        if (ifMatch == null || ifMatch.isBlank()) {
            throw new MissingPreconditionException();
        }

        VersionedDraft updated = drafts.replaceAuthorized(
            principal.getName(), id, ifMatch, request);
        return ResponseEntity.ok()
            .eTag(updated.strongEtag())
            .cacheControl(CacheControl.noStore())
            .body(updated.response());
    }
}
~~~

Controller trả `200` + representation mới sau PUT, trong khi ví dụ PATCH mục 5 dùng `204` không body. Cả hai là lựa chọn hợp lệ tùy hợp đồng; ETag mới phải khớp representation mà response thực sự công bố.

`Principal` chỉ đáng tin sau khi Spring Security đã xác thực yêu cầu và bind danh tính đúng. Nếu principal vắng mặt, cần trả `401` hoặc ứng xử tương ứng; đừng chỉ dựa vào tên parameter. Không dùng ID do người dùng gửi như bằng chứng quyền sở hữu.

### 9.3. Application service kiểm tra version và commit

Đoạn code sau mô tả **hai lớp bảo vệ**: so ETag trước khi áp dụng thay đổi và optimistic lock của JPA khi flush/commit. Việc thực hiện các bước phải nằm trong transaction phù hợp.

~~~java
import jakarta.persistence.EntityManager;
import jakarta.transaction.Transactional;

public class OrderDraftService {
    private final OrderDraftRepository repository;
    private final DraftMapper mapper;
    private final EntityManager entityManager;

    public OrderDraftService(
            OrderDraftRepository repository,
            DraftMapper mapper,
            EntityManager entityManager) {
        this.repository = repository;
        this.mapper = mapper;
        this.entityManager = entityManager;
    }

    @Transactional
    public VersionedDraft replaceAuthorized(
            String authenticatedUser,
            String publicId,
            String ifMatch,
            ReplaceDraftRequest request) {
        // Lookup đã scope theo user/tenant; method thật phải áp
        // đúng policy và tránh tiết lộ resource ngoài quyền.
        OrderDraftEntity entity = repository
            .findVisibleForWrite(authenticatedUser, publicId)
            .orElseThrow(ResourceNotFoundException::new);

        // Điều kiện HTTP được so với strong validator hiện hành.
        // Một API đầy đủ nên parse If-Match theo HTTP grammar.
        String currentTag = mapper.strongEtag(entity);
        if (!isSingleSupportedStrongTag(ifMatch)) {
            throw new InvalidPreconditionSyntaxException();
        }
        if (!currentTag.equals(ifMatch)) {
            throw new StaleDraftException();
        }
        if (!"DRAFT".equals(entity.getStatus())) {
            throw new DraftStateConflictException();
        }

        entity.setShippingAddress(request.shippingAddress());
        entity.setDeliveryNote(request.deliveryNote());

        // @Version giúp phát hiện một transaction khác đã ghi
        // cùng entity kể từ khi row được đọc.
        entityManager.flush();

        return new VersionedDraft(
            mapper.toResponse(entity),
            mapper.strongEtag(entity));
    }

    private static boolean isSingleSupportedStrongTag(String tag) {
        // Contract minh họa chỉ hỗ trợ một strong tag cụ thể.
        // Không chấp nhận wildcard, weak tag hoặc danh sách nhiều tag.
        return tag != null
            && tag.matches("\"draft-[A-Za-z0-9_-]+-v[0-9]+\"");
    }

    @Transactional
    public VersionedDraft readAuthorized(
            String authenticatedUser, String publicId) {
        OrderDraftEntity entity = repository
            .findVisibleForRead(authenticatedUser, publicId)
            .orElseThrow(ResourceNotFoundException::new);
        return new VersionedDraft(
            mapper.toResponse(entity),
            mapper.strongEtag(entity));
    }
}
~~~

Trong mẫu này, `OrderDraftRepository`, `DraftMapper` và các exception là interface/class ứng dụng cần hiện thực. Giả định entity ở mục 7 có getter/setter cần thiết và `@Version`. Nếu dùng `jakarta.transaction.Transactional` cho read, có thể thay bằng `org.springframework.transaction.annotation.Transactional(readOnly = true)` để tối ưu khi dự án dùng Spring transaction management.

**Cẩn thận về tính nguyên tử:** `currentTag.equals(ifMatch)` chỉ phát hiện client đã cũ **tại thời điểm service đọc row**. Hai transaction có thể đọc cùng phiên bản và đều vượt qua câu so sánh. Lúc `flush()` hoặc commit, `@Version` phải làm **một transaction thất bại**; nếu mọi đường ghi đều tuân thủ version discipline, không có “hai PUT cùng thắng”. Nếu bỏ `@Version` hoặc cập nhật qua native SQL không điều kiện, chỉ kiểm tra ETag ở application layer sẽ không đủ.

### 9.4. Một mapper ETag minh họa

~~~java
public final class DraftMapper {
    public DraftResponse toResponse(OrderDraftEntity e) {
        return new DraftResponse(
            e.getPublicId(),
            e.getShippingAddress(),
            e.getDeliveryNote(),
            e.getStatus());
    }

    public String strongEtag(OrderDraftEntity e) {
        // Chỉ phù hợp theo GIẢ ĐỊNH: mọi thay đổi representation
        // JSON đều tăng version, không có biến thể nội dung khác.
        return "\"draft-" + e.getPublicId()
            + "-v" + e.getVersion() + "\"";
    }
}
~~~

Tag ở snippet có thêm public ID (ví dụ `"draft-ord_916-v7"`), còn các chuỗi như `"draft-916-v7"` ở ví dụ HTTP là nhãn minh họa độc lập. Trong một API thật, hãy chọn **một cách sinh ETag nhất quán** giữa GET, PUT và PATCH. Không dùng string concatenation với ID tùy ý trong production; giới hạn/encode giá trị hoặc dùng HMAC/hash phù hợp để bảo đảm cú pháp entity-tag hợp lệ và tránh đưa dữ liệu nhạy cảm vào header.

Đừng copy snippet rồi khẳng định strong ETag cho response kết hợp từ service khác. Khi có các phần representation không theo `@Version`, cần một validator phản ánh toàn bộ response hoặc một mô hình resource khác, như đã phân tích ở mục 4.2.

### 9.5. Ánh xạ exception sang 412, 428 và 409

~~~java
import java.net.URI;
import org.springframework.http.HttpStatus;
import org.springframework.http.ProblemDetail;
import org.springframework.orm.ObjectOptimisticLockingFailureException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class DraftProblemHandler {
    @ExceptionHandler(InvalidPreconditionSyntaxException.class)
    ProblemDetail invalidPrecondition() {
        return problem(
            HttpStatus.BAD_REQUEST,
            "INVALID_IF_MATCH", "Unsupported If-Match format");
    }

    @ExceptionHandler(MissingPreconditionException.class)
    ProblemDetail missingPrecondition() {
        return problem(
            HttpStatus.PRECONDITION_REQUIRED,
            "IF_MATCH_REQUIRED", "A strong If-Match is required");
    }

    @ExceptionHandler({
        StaleDraftException.class,
        ObjectOptimisticLockingFailureException.class
    })
    ProblemDetail staleEdit() {
        return problem(
            HttpStatus.PRECONDITION_FAILED,
            "STALE_EDIT", "Read the newest draft before saving");
    }

    @ExceptionHandler(DraftStateConflictException.class)
    ProblemDetail stateConflict() {
        return problem(
            HttpStatus.CONFLICT,
            "DRAFT_NOT_EDITABLE", "Draft state does not allow editing");
    }

    private ProblemDetail problem(
            HttpStatus status, String code, String detail) {
        ProblemDetail p = ProblemDetail.forStatus(status);
        p.setType(URI.create(
            "https://api.example.test/problems/" + code));
        p.setDetail(detail);
        p.setProperty("code", code);
        return p;
    }
}
~~~

Đoạn trên chỉ minh họa. Khi dùng Hibernate/JPA, optimistic conflict có thể hiện thành exception Jakarta hoặc biến thể khác; phải kiểm tra thực tế translation ở tầng Spring/repository. Chỉ biến **optimistic conflict của endpoint conditional write** thành `412`; đừng bắt mọi `ObjectOptimisticLockingFailureException` trong mọi use case rồi tuyên bố tất cả đều là điều kiện HTTP sai. Một ứng dụng có thể định nghĩa exception chuyên biệt và ánh xạ tại boundary rõ ràng.

Nếu mapper trả entity sau `flush()` nhưng transaction commit hoặc hành vi phụ thuộc ngoại hệ thống vẫn có thể lỗi, không được gửi status thành công trước khi ranh giới commit tương ứng hoàn tất. Với `@Transactional` trên service, proxy thường hoàn tất transaction trước khi controller xây response, nhưng cần test các failure mode thực tế của ứng dụng.

### 9.6. Xác thực, tenant scope và lỗi không lộ thông tin

Các phương thức `findVisibleForRead`/`findVisibleForWrite` phải áp dụng policy người dùng và tenant. Không cho một client truy cập ID của tenant khác rồi suy ra từ `412` rằng resource đang ở phiên bản nào. Thứ tự auth, kiểm tra quyền và conditional write cần thiết kế để không tiết lộ nội dung resource ngoài quyền.

Nếu user không có quyền, có thể dùng `403` hoặc `404` theo chính sách che sự tồn tại. Không trả current ETag và representation cho người chưa đủ quyền chỉ để giúp họ giải quyết xung đột. Khi nhận `If-Match` mạnh, server vẫn phải kiểm tra **trạng thái nghiệp vụ** (`DRAFT` hay không) và validation đầu vào.

## 10. Đường đi khác: dùng một câu UPDATE nguyên tử

Với một số endpoint rất đơn giản, không nhất thiết phải load toàn bộ entity và flush qua ORM. Có thể dùng SQL condition:

~~~sql
UPDATE order_drafts
SET shipping_address = :new_address,
    delivery_note = :new_note,
    version = version + 1,
    updated_at = CURRENT_TIMESTAMP
WHERE public_id = :id
  AND tenant_id = :authorized_tenant
  AND owner_id = :authorized_user
  AND status = 'DRAFT'
  AND version = :expected_version;
~~~

Lấy số hàng ảnh hưởng và xử lý:

~~~text
affectedRows = executeConditionalUpdate(...)
if affectedRows == 1:
    COMMIT
    return 200/204 + validator mới được xác định đúng
else:
    kiểm tra resource/quyền/trạng thái theo chính sách
    trả 404/403/409/412 thích hợp, không ghi đè
~~~

**Không tạo ETag mới bằng cách giả định version luôn đúng nếu commit chưa thành công.** Với database có `RETURNING`, có thể lấy version mới từ câu UPDATE; cách khác là đọc lại đúng transaction hoặc query sau commit theo quy tắc consistency phù hợp.

Phải phân biệt:

- **Expected version** được xác định từ strong ETag của client.
- **Actual version** hiện tại chỉ nên được tiết lộ nếu caller được phép.
- **Business predicate** có thể chặn cập nhật dù version khớp.
- **Lỗi hạ tầng** khi query/commit phải là lỗi HTTP phù hợp, không đánh đồng với `412`.

Nếu một request vừa tạo row và vừa cập nhật nhiều bảng/ghi outbox, thao tác compare-and-swap phải nằm trong giao dịch bảo đảm mọi thay đổi nghiệp vụ liên quan commit cùng nhau. HTTP precondition không tự thay thế giao dịch đó.

## 11. Hành vi client khi nhận 412: đừng tự động ghi lại

Client B nhận `412` không nên ngay lập tức GET latest ETag rồi gửi lại **cùng payload cũ**. Như vậy đã **vô hiệu hóa** bảo vệ mất cập nhật: client chỉ xin validator mới để ghi đè dữ liệu vừa thay đổi của người khác.

### 11.1. Flow xử lý có ý thức

~~~mermaid
flowchart TD
    A["GET resource + ETag"] --> B["Người dùng chỉnh form"]
    B --> C["PUT/PATCH + If-Match"]
    C --> D{"HTTP status?"}
    D -- "200/204" --> E["Lưu thành công; giữ ETag mới"]
    D -- "412" --> F["GET representation mới nhất"]
    F --> G["So sánh bản gốc, thay đổi local, bản mới"]
    G --> H{"Có thể gộp an toàn?"}
    H -- "Không" --> I["Hiển thị xung đột; người dùng quyết định"]
    H -- "Có, theo domain rule" --> J["Tạo payload mới từ bản mới"]
    I --> J
    J --> K["Gửi lại với ETag mới sau xác nhận"]
    K --> D
    D -- "428" --> L["Đọc ETag và gửi request có điều kiện"]
    D -- "409" --> M["Giải thích state conflict; không ép ghi"]
    D -- "401/403/404" --> N["Xử lý quyền/tài nguyên"]
    D -- "429/503" --> O["Backoff theo hợp đồng"]
~~~

Flow này không đề nghị client tự động retry vô hạn. Khi request có side effect ngoài việc cập nhật row, cần cân nhắc idempotency, timeout và điều kiện retry riêng.

### 11.2. So sánh ba phiên bản khi giải quyết xung đột

Một UI có thể giữ:

- **Base:** representation mà người dùng bắt đầu chỉnh (version 7).
- **Local:** dữ liệu người dùng thay đổi dựa trên base.
- **Remote:** representation mới nhất trên server (version 8).

Ví dụ:

| Field | Base v7 | Local của B | Remote v8 của A | Gợi ý |
|---|---|---|---|---|
| `shippingAddress` | 12 Nguyễn Trãi | 12 Nguyễn Trãi | 58 Lê Lợi | Giữ remote, vì B không sửa field này |
| `deliveryNote` | Giao giờ hành chính | Để trước cửa | Giao giờ hành chính | Có thể giữ local nếu domain cho phép |

Nếu domain coi hai trường độc lập, có thể gộp thành địa chỉ mới + ghi chú mới rồi gửi request với version 8. Nhưng nếu cả hai người cùng thay `shippingAddress`, hoặc ghi chú phụ thuộc địa chỉ, client cần quyết định rõ; không tự động coi update B “mới hơn” là đúng.

### 11.3. Chỉnh sửa offline

Ứng dụng mobile có thể giữ bản nháp khi mất mạng. Một giờ sau, validator cũ không còn khớp. `If-Match` vẫn có giá trị: nó **phát hiện** xung đột, không bảo đảm tự giải quyết. Thiết kế offline cần lưu base ETag/representation, thời điểm chỉnh, các local changes và chính sách gộp. Với hệ thống cộng tác tài liệu thời gian thực, có thể cần mô hình chuyên biệt như operation transformation hoặc CRDT, không kỳ vọng một ETag giải quyết toàn bộ merge.

## 12. Idempotency khác concurrency control

Hai khái niệm thường bị trộn:

| Cơ chế | Câu hỏi được trả lời | Ví dụ |
|---|---|---|
| **`If-Match` / OCC** | “Tôi đang sửa đúng phiên bản mình đã đọc chứ?” | Không cho client B ghi đè thay đổi A |
| **`Idempotency-Key`** | “Tôi đã gửi chính yêu cầu này rồi; retry có tạo tác động thứ hai không?” | Client mất response POST tạo đơn nhưng retry không tạo đơn thứ hai |
| **Business constraint** | “Dù request không bị trùng và version đúng, thao tác có hợp lệ không?” | Đơn đã giao thì không được hủy trực tiếp |

### 12.1. Khi response PUT/PATCH bị mất

Client gửi `PUT` kèm `If-Match: "v7"`, server đã commit version 8 nhưng response bị mất. Client retry **y nguyên request** với `"v7"` có thể nhận `412` vì precondition giờ không khớp. Điều này **không nhất thiết có nghĩa lần đầu thất bại**.

Cách xử lý:

1. Client GET latest và so sánh resource có phản ánh ý định đã gửi không; chú ý có thể có tác động từ client khác sau đó.
2. Nếu endpoint có cơ chế idempotency được thiết kế cho thay đổi có tác động, dùng khóa request và dữ liệu đối soát thích hợp.
3. Không tự bỏ `If-Match` khi retry chỉ để “đảm bảo lần này thành công”.
4. Không khẳng định status của hai lần gọi sẽ giống hệt nhau: idempotent theo HTTP không yêu cầu response giống nhau.

### 12.2. Khi POST command chạy cạnh tranh

Hai client cùng yêu cầu `POST /orders/{id}/confirmations` có thể đều gửi đúng ETag cũ. Nếu nghiệp vụ chỉ cho xác nhận một lần, backend vẫn cần transaction, unique constraint, domain state và/hoặc idempotency. Không thay các biện pháp nghiệp vụ bằng việc “có ETag rồi” vì quy trình có thể chạm nhiều tài nguyên và dịch vụ.

## 13. Cache, conditional GET và tính nhất quán

### 13.1. Cached representation vẫn có thể là phiên bản cũ

Client có thể nhận representation từ cache với ETag `v7` trong khi origin đã có `v8`. Điều này không tự gây mất dữ liệu nếu server **luôn kiểm tra `If-Match` trên origin/cơ chế bảo đảm đúng** trước khi ghi. Response `412` báo client refresh và gộp.

Một proxy không được tự quyết định rằng một PUT/PATCH có điều kiện thành công chỉ vì có bản cache v7. Với API có cache phân quyền hoặc nhiều bản sao đọc, hãy đảm bảo conditional write kiểm soát được **current committed state**, không chỉ so với bản replica trễ.

### 13.2. ETag dùng cho đọc và ghi có liên quan nhưng mục tiêu khác

| Tình huống | Header request | Response thường gặp | Mục tiêu |
|---|---|---|---|
| GET lần đầu | Không có điều kiện | `200` + ETag | Lấy representation và validator |
| GET kiểm tra cache | `If-None-Match` | `304` hoặc `200` | Giảm tải nội dung khi representation chưa đổi |
| PUT/PATCH chỉnh sửa | `If-Match` | `200/204` hoặc `412` | Ngăn ghi từ phiên bản lỗi thời |
| PUT tạo nếu chưa tồn tại | `If-None-Match: *` | `201` hoặc `412` | Tránh ghi đè resource đã có |

Một resource có thể chọn `Cache-Control: no-store` vì chứa dữ liệu nhạy cảm nhưng **vẫn phát `ETag` phục vụ conditional write**. ETag không bắt buộc response phải được cache. Nếu API sử dụng `private, max-age=...`, phải xét yêu cầu quyền riêng tư, khả năng stale và cập nhật affordance phù hợp.

### 13.3. ETag và representation variants

Nếu cùng URI có JSON và XML, hoặc JSON theo các ngôn ngữ/quyền khác nhau, những representation có nội dung khác có thể cần validator khác. Đừng dùng một strong ETag cho mọi biến thể chỉ vì cùng row version nếu chúng không đáp ứng điều kiện so khớp mạnh.

Trong thiết kế bảo vệ PUT/PATCH, chọn **một representation cập nhật rõ ràng** và một quy tắc validator ổn định để client biết ETag nào gửi lại. Nếu không thể đối chiếu điều kiện với resource logic một cách chính xác, xem xét resource con riêng, version cho aggregate hoặc precondition ở command-specific contract.

## 14. OpenAPI: phải công bố precondition như một phần hợp đồng

Một API chỉ viết “PUT cập nhật draft” mà không ghi yêu cầu `If-Match` khiến client không biết tại sao nhận `428`. OpenAPI cần mô tả:

- Resource URI và request schema.
- Header `If-Match` bắt buộc, cách lấy strong ETag từ GET.
- Response `200`/`204` kèm ETag mới.
- `412` khi current validator không khớp, `428` khi thiếu điều kiện.
- `409` khi xung đột domain, `401/403/404` khi không được phép/không có.
- Problem Details và quy tắc retry/refresh.

Ví dụ OpenAPI 3.1 rút gọn:

~~~yaml
openapi: 3.1.0
info:
  title: Order Draft API
  version: 1.0.0
paths:
  /v1/order-drafts/{id}:
    parameters:
      - name: id
        in: path
        required: true
        schema: {type: string}
    get:
      summary: Đọc draft và strong ETag hiện tại
      security:
        - bearerAuth: []
      responses:
        '200':
          description: Draft được phép đọc
          headers:
            ETag:
              required: true
              description: Strong validator của representation draft
              schema: {type: string}
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/Draft'
        '304':
          description: Representation chưa đổi khi GET có If-None-Match
        '401':
          description: Cần xác thực
        '404':
          description: Không tìm thấy hoặc không công bố draft
    put:
      summary: Thay thế phần có thể chỉnh của draft có điều kiện
      security:
        - bearerAuth: []
      parameters:
        - name: If-Match
          in: header
          required: true
          description: |
            Strong ETag lấy từ GET draft.
            Contract này yêu cầu một validator mạnh cụ thể,
            không nhận wildcard hoặc danh sách nhiều ETag.
          schema: {type: string}
          example: '"draft-ord_916-v7"'
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/ReplaceDraftRequest'
      responses:
        '200':
          description: Draft đã cập nhật, trả representation và ETag mới
          headers:
            ETag:
              required: true
              schema: {type: string}
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/Draft'
        '400':
          description: Request hoặc cú pháp điều kiện không được hỗ trợ
        '401':
          description: Cần xác thực
        '403':
          description: Không có quyền
        '404':
          description: Không tìm thấy hoặc không công bố draft
        '409':
          description: Domain state không cho phép cập nhật
          content:
            application/problem+json:
              schema:
                $ref: '#/components/schemas/Problem'
        '412':
          description: Validator lỗi thời hoặc không khớp
          content:
            application/problem+json:
              schema:
                $ref: '#/components/schemas/Problem'
        '428':
          description: Thiếu precondition theo chính sách API
          content:
            application/problem+json:
              schema:
                $ref: '#/components/schemas/Problem'
components:
  securitySchemes:
    bearerAuth:
      type: http
      scheme: bearer
  schemas:
    Draft:
      type: object
      required: [id, shippingAddress, status]
      properties:
        id: {type: string}
        shippingAddress: {type: string}
        deliveryNote:
          type: [string, 'null']
        status:
          type: string
          enum: [DRAFT, CONFIRMED]
    ReplaceDraftRequest:
      type: object
      required: [shippingAddress]
      additionalProperties: false
      properties:
        shippingAddress:
          type: string
          minLength: 1
          maxLength: 200
        deliveryNote:
          type: [string, 'null']
          maxLength: 500
    Problem:
      type: object
      required: [type, title, status]
      properties:
        type: {type: string, format: uri-reference}
        title: {type: string}
        status: {type: integer}
        detail: {type: string}
        code: {type: string}
~~~

**Lưu ý:** OpenAPI `required: true` chỉ mô tả yêu cầu header cho client/tooling, không tự ép server trả `428`. Runtime phải kiểm tra, và contract tests phải xác nhận. `additionalProperties: false` trong schema cũng không tự khiến Jackson từ chối field lạ nếu runtime chưa cấu hình tương ứng.

OpenAPI cho phép mô tả nhiều mã thành công như `200` hoặc `204`, nhưng nên chọn **một hành vi chính** cho từng endpoint để client đỡ nhầm. Ví dụ ở đây chọn `200` + body + ETag khi PUT thành công; response PATCH ở mục 5 minh họa tùy chọn `204`.

## 15. Kiểm thử: phải tái hiện race condition, không chỉ gửi request nối tiếp

Nếu chỉ test:

~~~text
GET version 7
PUT If-Match version 7 => 200
PUT If-Match version 7 => 412
~~~

ta mới kiểm tra việc server phát hiện **stale request theo thứ tự**. Chưa chứng minh hai request thực sự đồng thời không cùng thắng tại khe hở giữa check và save. Cần cả hai loại test.

### 15.1. Ma trận kiểm thử hợp đồng

| Kịch bản | Kỳ vọng |
|---|---|
| GET draft thuộc quyền | `200` và strong ETag, schema đúng |
| GET với If-None-Match khớp | `304` khi điều kiện hợp lệ, không có body |
| PUT đúng strong ETag | `200` + body mới, strong ETag thay đổi |
| PATCH đúng strong ETag | `200/204` theo contract, không mất field ngoài phạm vi |
| PUT không có `If-Match` | `428`, DB không đổi |
| PUT với stale `If-Match` | `412`, DB không đổi |
| PUT với weak ETag | Không được coi là strong match; lỗi theo contract |
| PUT với `If-Match: *` | Không được bypass yêu cầu version cụ thể của API |
| PUT với nhiều ETag khi API chỉ cho phép một | Từ chối theo contract; không âm thầm chọn tag đầu |
| PUT với ETag sai resource | Không cho phép ghi, không lộ resource ngoài quyền |
| GET sau PATCH thành công | Trả representation và ETag mới nhất |
| Hai PUT cạnh tranh cùng ETag | Đúng một thay đổi thắng, yêu cầu còn lại bị chặn |
| Request đúng ETag nhưng draft đã xác nhận | `409` nếu domain không cho sửa và precondition đã thỏa |
| User khác tenant biết ID/ETag | `403` hoặc `404`, không ghi hoặc đọc dữ liệu |
| Token bị thu hồi sau GET | Không được PUT bằng ETag cũ nếu quyền không còn |
| Client retry sau mất response | Không tự tạo tác động trùng; quy tắc retry được công bố |
| Update native SQL bỏ version | Test phát hiện validator không đổi hoặc lost update |
| Hai service instance khác nhau | OCC vẫn hoạt động nhờ DB, không dựa vào lock trong memory |
| Cache/replica trả ETag cũ | Conditional write tại origin/nguồn đúng vẫn chặn stale edit |
| Field không cho sửa trong JSON | Không có mass assignment, thông báo validation đúng |

### 15.2. Test định kỳ với curl

Lấy representation và ETag:

~~~bash
curl -i "https://api.example.test/v1/order-drafts/ord_916" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN" \
  -H "Accept: application/json"
~~~

Gửi thay đổi có điều kiện (thay đúng ETag đã nhận từ server):

~~~bash
curl -i -X PUT "https://api.example.test/v1/order-drafts/ord_916" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -H 'If-Match: "draft-ord_916-v7"' \
  -d '{"shippingAddress":"58 Lê Lợi","deliveryNote":"Giao giờ hành chính"}'
~~~

Gửi lại ETag cũ với nội dung khác để thấy `412`:

~~~bash
curl -i -X PUT "https://api.example.test/v1/order-drafts/ord_916" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -H 'If-Match: "draft-ord_916-v7"' \
  -d '{"shippingAddress":"12 Nguyễn Trãi","deliveryNote":"Để trước cửa"}'
~~~

Các URL, token và ETag là **giá trị minh họa**, không phải endpoint thực. Nếu test chạy trên Windows PowerShell, cách quote/escape shell có thể khác ví dụ bash. Với một resource vừa được chỉnh bởi người khác trong lúc test, kết quả cũng phải được đánh giá theo phiên bản thực tế.

### 15.3. MockMvc minh họa điều kiện HTTP

~~~java
// Assertions minh họa; cần @WebMvcTest, mock service, principal,
// exception handler và dữ liệu test đúng. Không phải class độc lập.

mockMvc.perform(get("/v1/order-drafts/ord_916"))
    .andExpect(status().isOk())
    .andExpect(header().exists("ETag"));

mockMvc.perform(put("/v1/order-drafts/ord_916")
        .contentType(MediaType.APPLICATION_JSON)
        .content("""
            {"shippingAddress":"58 Lê Lợi","deliveryNote":"Giao giờ hành chính"}
            """))
    .andExpect(status().isPreconditionRequired());

mockMvc.perform(put("/v1/order-drafts/ord_916")
        .header("If-Match", "\"draft-ord_916-v7\"")
        .contentType(MediaType.APPLICATION_JSON)
        .content("""
            {"shippingAddress":"12 Nguyễn Trãi","deliveryNote":"Để trước cửa"}
            """))
    .andExpect(status().isPreconditionFailed());
~~~

Mock service phải được cấu hình trả exception phù hợp cho stale request. Kiểm tra controller không tự chứng minh DB CAS hoạt động; cần integration test qua persistence thực. Test phải xác nhận **DB không đổi** khi `412`, không chỉ nhìn status.

### 15.4. Test cạnh tranh với hàng rào đồng bộ

Ý tưởng integration test:

~~~text
1. Chuẩn bị DB: draft ord_916 version 7, address=A0, note=N0.
2. Cả client A và B GET cùng strong ETag version 7.
3. Tạo hai luồng A/B; dùng barrier cho chúng gửi PUT cùng lúc.
4. A muốn {address=A1, note=N0}; B muốn {address=A0, note=N1}.
5. Thu cả hai response và trạng thái DB cuối.
6. Kỳ vọng đúng một request thành công (200), một request nhận 412.
7. DB phải phản ánh đúng toàn bộ payload của request thắng.
8. Không được xuất hiện trạng thái pha trộn sai hoặc mất version increment.
~~~

Một mẫu Java concurrency test tối giản (phần `sendPut` và fixture phải được hiện thực trong test tích hợp thật):

~~~java
import java.util.Set;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import static org.junit.jupiter.api.Assertions.assertEquals;

CountDownLatch ready = new CountDownLatch(2);
CountDownLatch fire = new CountDownLatch(1);

ExecutorService pool = Executors.newFixedThreadPool(2);
try {
    Future<Integer> a = pool.submit(() -> {
        ready.countDown();
        fire.await();
        return sendPut("A1", "N0", sharedEtag);
    });
    Future<Integer> b = pool.submit(() -> {
        ready.countDown();
        fire.await();
        return sendPut("A0", "N1", sharedEtag);
    });
    if (!ready.await(5, TimeUnit.SECONDS)) {
        throw new AssertionError("Workers not ready");
    }
    fire.countDown();
    Set<Integer> outcomes = Set.of(a.get(), b.get());
    assertEquals(Set.of(200, 412), outcomes);
} finally {
    pool.shutdownNow();
}
~~~

Đoạn code minh họa logic đồng bộ test, không chạy độc lập: `sendPut`, `sharedEtag`, database fixture và imports/test class phải được tạo. **Một lần chạy đồng thời chưa bảo đảm hai transaction đọc cùng version trước khi ghi**; để tái hiện lỗi check-then-act, integration test nên có hook/barrier ở chính tầng service/repository sau khi đọc version nhưng trước khi ghi (trong môi trường test có kiểm soát), hoặc chạy stress test nhiều lần trên hạ tầng có khả năng concurrency thật.

Đồng thời cần test “hai sửa không chồng field” theo chính sách merge đã chọn. Với endpoint PUT replacement + `If-Match` trong bài, vẫn chỉ một request trên shared ETag được phép thắng; nếu muốn merge thành công cả hai, đó phải là hành vi mới được thiết kế và kiểm thử.

### 15.5. Tiêm lỗi và test trên nhiều instance

- API A và API B cùng dùng một DB: cùng nhận `If-Match` version 7, không được cùng trả thành công sau hai bản ghi cạnh tranh.
- Transaction A đọc version 7, transaction B commit version 8 trước khi A flush: A phải thất bại bằng optimistic conflict và không commit.
- Native/batch update từ hệ khác thay dữ liệu công khai: ETag/version phải đổi hoặc nguồn cập nhật phải bị chặn để không phá OCC.
- Connection mất sau commit: client phải có cách phát hiện kết quả thực, không tự bỏ precondition để retry.
- Replica đọc chậm: client có thể nhận validator cũ, nhưng origin không được ghi dựa trên validator stale đó.
- Resource bị xóa/thu hồi quyền giữa GET và PUT: không được ghi, lỗi theo policy và không lộ dữ liệu ngoài quyền.
- Validation và domain checks phải chạy trong transaction/quy tắc cạnh tranh hợp lý, không chỉ ở UI.

## 16. Bài tập tổng hợp: hai người chỉnh thông tin giao hàng

**Bối cảnh:** API có resource `/v1/order-drafts/{id}` gồm địa chỉ nhận, ghi chú giao hàng, lựa chọn khung giờ, trạng thái và phiên bản nội bộ. Khách hàng và nhân viên hỗ trợ có thể cùng mở form. Địa chỉ nhận quyết định vùng giao và phí vận chuyển; một số trạng thái không cho sửa.

### 16.1. Yêu cầu

1. **Vẽ timeline lost update** khi khách đổi địa chỉ, support đổi ghi chú nhưng gửi PUT toàn bộ dữ liệu từ bản cũ.
2. **Thiết kế GET response** có strong ETag và JSON không lộ trường nội bộ. Trình bày tại sao `@Version` của JPA chỉ là một thành phần của validator.
3. **Viết PUT hoặc PATCH contract** với `If-Match`, request DTO allowlist và response `200`/`204` phù hợp.
4. **Định nghĩa cách xử lý** khi thiếu `If-Match` (`428`), ETag stale (`412`), draft đã xác nhận (`409`), user ngoài tenant (`403/404`) và request sai (`400/422`).
5. **Thiết kế cơ chế ghi nguyên tử** dùng `@Version` hoặc câu `UPDATE ... WHERE version = expected`; chứng minh không có race giữa kiểm tra và ghi.
6. **Đánh giá merge:** Nếu địa chỉ và ghi chú thay đổi độc lập thì có gộp được không? Nếu khung giờ giao phụ thuộc địa chỉ thì phải xử lý ra sao?
7. **Thiết kế UI xử lý 412** dùng base/local/remote, có lựa chọn refresh/merge, không tự động ghi đè.
8. **Viết OpenAPI** nêu `ETag` trong GET, `If-Match` bắt buộc trên write, Problem Details, mã lỗi và security scheme.
9. **Viết ít nhất 12 test** gồm request tuần tự, thực sự cạnh tranh, ngoài quyền, lỗi domain, lost response, ETag weak, wildcard, cache stale và native SQL.
10. **Đề xuất observability:** metric conflict rate, latency, retry, tỉ lệ lưu thành công sau khi gộp và cảnh báo khi xuất hiện hai request cạnh tranh cùng thành công.

### 16.2. Ví dụ đầu ra cần trình bày

**GET ban đầu:**

~~~http
HTTP/1.1 200 OK
ETag: "draft-ord_916-v7"
Content-Type: application/json

{
  "id": "ord_916",
  "shippingAddress": "12 Nguyễn Trãi",
  "deliveryNote": "Giao giờ hành chính",
  "deliverySlot": "MORNING",
  "status": "DRAFT"
}
~~~

**Client A đổi địa chỉ, gửi điều kiện đúng:**

~~~http
PUT /v1/order-drafts/ord_916 HTTP/1.1
Content-Type: application/json
If-Match: "draft-ord_916-v7"

{
  "shippingAddress": "58 Lê Lợi",
  "deliveryNote": "Giao giờ hành chính",
  "deliverySlot": "MORNING"
}
~~~

**Server lưu thành version 8 và phản hồi:**

~~~http
HTTP/1.1 200 OK
ETag: "draft-ord_916-v8"
Content-Type: application/json

{
  "id": "ord_916",
  "shippingAddress": "58 Lê Lợi",
  "deliveryNote": "Giao giờ hành chính",
  "deliverySlot": "MORNING",
  "status": "DRAFT"
}
~~~

**Client B dùng ETag version 7 phải bị từ chối:**

~~~http
HTTP/1.1 412 Precondition Failed
Content-Type: application/problem+json

{
  "type": "https://api.example.test/problems/stale-resource",
  "title": "Draft has changed",
  "status": 412,
  "code": "STALE_EDIT"
}
~~~

Sau `412`, client B tải bản mới, xác định địa chỉ A đã thay và ghi chú B muốn đổi; không gửi PUT chứa địa chỉ cũ mà không xin người dùng xác nhận. Nếu đổi địa chỉ làm khung giờ sáng không còn hợp lệ, server phải tái kiểm tra bất biến khi nhận payload gộp — **merge không đồng nghĩa tự động hợp lệ**.

### 16.3. Gợi ý thang chấm

| Tiêu chí | Điểm |
|---|---:|
| Giải thích lost update và timeline chính xác | 15 |
| ETag/If-Match/HTTP status hợp lý | 20 |
| Atomic write và version discipline ở DB | 20 |
| DTO, validation, phân quyền, bất biến nghiệp vụ | 15 |
| UI xử lý 412, merge và retry/idempotency | 10 |
| OpenAPI và test cạnh tranh có khả năng phát hiện lỗi | 15 |
| Observability và lưu ý vận hành | 5 |
| **Tổng** | **100** |

## 17. Phản mẫu thường gặp

| Phản mẫu | Hệ quả | Thiết kế thay thế |
|---|---|---|
| Client PUT toàn bộ object từ form cũ, không có precondition | Ghi đè thay đổi người khác | GET ETag, PUT/PATCH với If-Match |
| Controller so ETag rồi repository save không khóa/version | Hai request cùng qua check trước khi ghi | CAS hoặc JPA optimistic lock tới commit |
| Dùng weak ETag cho `If-Match` | Không thỏa strong comparison | Phát strong validator đúng nghĩa |
| Coi `If-Match: *` là version bất biến | Chỉ kiểm tra resource tồn tại | Yêu cầu strong ETag cụ thể cho chỉnh sửa |
| Dùng DB timestamp có độ phân giải giây làm version tuyệt đối | Có thể bỏ sót cập nhật liên tiếp | Validator/version monotonic hoặc fingerprint phù hợp |
| Phát ETag từ một row trong khi JSON còn lấy từ bảng khác | Representation đổi nhưng validator giữ nguyên | Validator phản ánh toàn bộ representation |
| Catch mọi optimistic exception thành 500 | Client không biết refresh và giải quyết conflict | Ánh xạ đúng 412 ở conditional write |
| Dùng 409 cho mọi If-Match stale | Không phân biệt HTTP precondition và domain conflict | 412 cho điều kiện, 409 cho bất biến nghiệp vụ |
| Chỉ khóa trong memory của một API instance | Không bảo vệ cạnh tranh giữa các instance | DB CAS/transaction dùng chung |
| Native SQL thay field nhưng không tăng version | ETag stale trông như còn hợp lệ | Đồng bộ mọi đường ghi với version discipline |
| Client thấy 412 rồi tự lấy ETag mới và ghi lại payload cũ | Bỏ qua cơ chế chống lost update | Refresh, so sánh, gộp có ý thức |
| Client đổi field không cho phép vì DTO trùng JPA entity | Mass assignment, cập nhật trái quyền | DTO chỉ chứa trường được sửa và kiểm tra domain |
| ETag coi như quyền sửa | Lộ dữ liệu, BOLA/IDOR | Authn/authz theo resource và tenant |
| Chỉ có test tuần tự, không test race | Không bắt được TOCTOU khi hai request cùng check | Test barrier, load/stress và kiểm tra DB |
| Cache/replica quyết định precondition khi ghi | Ghi đè dựa trên dữ liệu không mới nhất | Conditional write trên nguồn có consistency đúng |

## 18. Checklist trước khi công bố endpoint chỉnh sửa

### HTTP contract và representation

- [ ] Có URI resource ổn định, phương thức và request DTO phù hợp.
- [ ] GET trả representation hiện hành với strong ETag đúng nghĩa nếu API dùng If-Match.
- [ ] PUT/PATCH công bố rõ trường được sửa và semantics của null/field vắng mặt.
- [ ] Write yêu cầu `If-Match` theo hợp đồng; thiếu trả 428, stale trả 412.
- [ ] `409` dành cho xung đột domain sau khi điều kiện HTTP phù hợp.
- [ ] Response thành công trả ETag mới đúng representation hoặc chỉ dẫn GET lại.

### Tính nguyên tử và bảo mật

- [ ] ETag/version check gắn với update nguyên tử, không chỉ if-check ở controller.
- [ ] JPA `@Version` hoặc CAS hoạt động trên mọi đường ghi có liên quan.
- [ ] Transaction/commit, khóa và outbox khi cần không làm lộ partial result.
- [ ] Tenant/owner được xác minh từ identity đáng tin, không lấy từ JSON.
- [ ] Kiểm tra authorization và business invariants tại thời điểm write.
- [ ] ETag không chứa secret; không lộ current version/resource ngoài quyền.

### Client, test và vận hành

- [ ] Client lưu base representation + ETag, có UX cho 412 và merge an toàn.
- [ ] Không tự bỏ If-Match để retry; xử lý response bị mất có đối soát.
- [ ] OpenAPI định nghĩa ETag, If-Match, 412, 428, 409 và Problem Details.
- [ ] Có test thiếu/stale/weak ETag, wildcard, auth và validation.
- [ ] Có test hai request thực sự cạnh tranh, multi-instance và native/batch write.
- [ ] Có metric conflict rate, retry, optimistic lock failure và tình trạng stale.
- [ ] Cache/replica không bypass conditional write ở nguồn dữ liệu đúng.

## 19. Kết luận

**Lost update không phải lỗi của riêng PUT, PATCH hay JPA**; đó là việc nhiều client cập nhật dựa trên các phiên bản khác nhau nhưng server không nhận biết hoặc không xử lý xung đột. Giải pháp thực tế thường là **optimistic concurrency**: server phát strong `ETag` khi GET, client gửi `If-Match` khi ghi, và backend thực hiện **so sánh phiên bản gắn nguyên tử với cập nhật**.

Khi precondition không đúng, server trả `412 Precondition Failed` và **không ghi đè**. Khi API bắt buộc precondition nhưng client không gửi, dùng `428 Precondition Required`; khi trạng thái nghiệp vụ không cho phép hành động dù version phù hợp, dùng `409 Conflict`. Đặt các quy tắc này trong OpenAPI, kết hợp xác thực, phân quyền, validation, xử lý retry và kiểm thử đồng thời thật để API bảo toàn thay đổi giữa nhiều người dùng.
