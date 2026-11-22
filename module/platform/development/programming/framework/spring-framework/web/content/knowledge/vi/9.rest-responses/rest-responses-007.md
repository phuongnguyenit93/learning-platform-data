# Thiết kế cập nhật PUT/PATCH và quy tắc xử lý yêu cầu lặp lại trong Spring MVC

## 1. Mục tiêu và tình huống mở đầu

Một client mở tài liệu tại `GET /api/documents/1`, sửa tiêu đề rồi nhấn Lưu. Server xử lý thay đổi thành công nhưng kết nối bị ngắt trước khi response quay về. Client **không biết** bản cập nhật đã được áp dụng hay chưa. Nếu gửi lại yêu cầu, liệu nội dung sẽ giữ nguyên, bị áp dụng hai lần, hay ghi đè cập nhật của người khác?

Để trả lời, phải thiết kế **ngữ nghĩa cập nhật**, **quy tắc yêu cầu lặp lại** và **bảo vệ khi nhiều client sửa đồng thời**. Bài học này giúp bạn:

- Phân biệt `PUT` với `PATCH` theo HTTP semantics, đặc biệt **thay thế toàn bộ** và **cập nhật một phần**.
- Hiểu **idempotency**: gọi nhiều lần cùng một yêu cầu có cùng hiệu ứng mong muốn lên tài nguyên như gọi một lần; phân biệt hiệu ứng cuối cùng với response, log và request ID.
- Nhận biết `PATCH` có thể idempotent hoặc không, tùy thao tác và cách server triển khai; hiểu JSON Merge Patch và JSON Patch.
- Dùng **ETag + If-Match** để tránh **lost update**; phân biệt `412 Precondition Failed`, `428 Precondition Required` và `409 Conflict`.
- Chọn response 200/204/201, phân biệt absent/null, xác định retry an toàn và tránh lặp side effect.
- Xây dựng Spring Boot 3.x / Java 17+ demo có endpoint `GET`, `PUT`, `PATCH`, kiểm tra điều kiện cập nhật và test `MockMvc`.

**Phạm vi:** thiết kế REST API và triển khai cơ bản trong **Spring MVC (Servlet stack)**. Các ví dụ tuân tinh thần RFC 9110 (HTTP Semantics), RFC 5789 (PATCH), RFC 7396 (JSON Merge Patch) và RFC 6902 (JSON Patch). Quy tắc idempotency là thuộc tính của **hiệu ứng HTTP request được định nghĩa**, không đồng nghĩa với việc server chỉ xử lý request một lần vật lý.

## 2. PUT và PATCH: khác nhau ở hợp đồng cập nhật

Ví dụ tài liệu hiện tại:

```json
{
  "title": "Hướng dẫn Spring",
  "description": "Bản nháp"
}
```

### 2.1. PUT: gửi biểu diễn mới cho tài nguyên đích

Client muốn thay toàn bộ biểu diễn có thể gửi:

```http
PUT /api/documents/1 HTTP/1.1
Content-Type: application/json

{"title":"Hướng dẫn Spring MVC","description":"Bản hoàn chỉnh"}
```

Ý nghĩa HTTP của `PUT`: yêu cầu server **tạo hoặc thay trạng thái của tài nguyên đích bằng biểu diễn đi kèm**. Nếu endpoint đã tồn tại và được cập nhật thành công, response thường là **200 OK** (có body) hoặc **204 No Content** (không body). Nếu tài nguyên **chưa tồn tại và PUT tạo mới thành công**, theo HTTP semantics server **phải trả 201 Created**.

**Không áp dụng “chỉ sửa các trường hiện diện” cho PUT** nếu API được mô tả là thay thế toàn bộ. Chẳng hạn:

```http
PUT /api/documents/1 HTTP/1.1
Content-Type: application/json

{"title":"Hướng dẫn Spring MVC"}
```

Với tài nguyên hai trường như trên, việc `description` bị bỏ qua **không có nghĩa ngầm giữ nguyên "Bản nháp"**. Hợp đồng PUT phải định nghĩa rõ: coi trường vắng mặt là giá trị mặc định/null, bỏ trường đó khỏi representation hoặc từ chối request thiếu field bắt buộc. Client cần gửi biểu diễn đầy đủ theo schema. Một số API thực tế gọi endpoint là PUT nhưng triển khai như partial update; đó là hợp đồng riêng dễ gây nhầm và nên được sửa hoặc công bố rõ.

**Điểm tinh tế:** HTTP PUT nói về **biểu diễn của tài nguyên**, không bắt server phải lưu byte-for-byte request body vào một dòng DB. Nhưng server cần duy trì ngữ nghĩa tài nguyên. Các thuộc tính do server sở hữu như `id`, `createdAt` thường không được client cho phép sửa; contract phải cho biết chúng có thuộc representation có thể PUT hay không.

### 2.2. PATCH: gửi tài liệu mô tả thay đổi

Để chỉ thay tiêu đề và giữ `description`, dùng `PATCH` với patch document có định dạng đã thống nhất:

```http
PATCH /api/documents/1 HTTP/1.1
Content-Type: application/merge-patch+json

{"title":"Hướng dẫn Spring MVC"}
```

Với **JSON Merge Patch** (RFC 7396), field không xuất hiện được giữ nguyên; field có mặt được thay/cập nhật theo quy tắc Merge Patch. Dữ liệu cũ:

```json
{"title":"Hướng dẫn Spring","description":"Bản nháp"}
```

Dữ liệu sau:

```json
{"title":"Hướng dẫn Spring MVC","description":"Bản nháp"}
```

Không phải mọi `PATCH` đều dùng cùng cú pháp. Server phải chọn/khai báo **patch media type**, ví dụ `application/merge-patch+json` hoặc `application/json-patch+json`; một endpoint tự đặt `PATCH` với `application/json` cần tự định nghĩa semantics. Không mặc định rằng mọi JSON object gửi với PATCH đều tự động có chức năng “chỉ cập nhật field được gửi”.

### 2.3. Bảng so sánh

| Câu hỏi | PUT | PATCH |
| --- | --- | --- |
| Request body biểu thị gì? | Biểu diễn mới cho toàn tài nguyên | Tập thay đổi/patch document |
| Trường không xuất hiện | Theo schema của biểu diễn thay thế; không mặc định giữ cũ | Theo định dạng patch; Merge Patch giữ nguyên |
| Có thể tạo tài nguyên? | Có, nếu server hỗ trợ PUT tại URI đó | Có thể trong một số hợp đồng PATCH/patch format, không phải nghĩa mặc định cần giả định |
| Có idempotent theo định nghĩa HTTP? | **Có** | **Không mặc định**, có thể được thiết kế idempotent |
| Có cần xử lý đồng thời? | Có | Có; một số patch đặc biệt nhạy cảm với thay đổi giữa chừng |
| Success status thường gặp | 200/204; 201 nếu tạo mới | 200/204 (hoặc khác nếu hợp đồng cần) |
| Body phù hợp | Biểu diễn tài nguyên | `application/merge-patch+json` hoặc `application/json-patch+json` |
| Mối nguy phổ biến | Thiếu field vô tình xóa giá trị, ghi đè thay đổi mới | Thiếu phân biệt absent/null, patch trên bản cũ, lặp thao tác cộng/dời |

## 3. Idempotency là gì?

Trong HTTP, một phương thức **idempotent** nếu hiệu ứng mong muốn lên trạng thái server của **nhiều request giống nhau** bằng hiệu ứng của **một request**. `GET`, `HEAD`, `OPTIONS`, `TRACE` là safe (và idempotent); `PUT` và `DELETE` là idempotent nhưng **không safe** vì có thể thay đổi trạng thái. `POST`, `PATCH` không được định nghĩa là idempotent mặc định.

Cách nghĩ dễ nhớ:

```text
SET title = "Hoàn chỉnh"         → có thể idempotent
INCREMENT views BY 1            → không idempotent
APPEND "A" vào danh sách        → không idempotent (nếu không chống lặp)
DELETE tài nguyên ID=1          → idempotent về hiệu ứng đích
POST tạo một giao dịch mới     → có thể tạo thêm bản ghi khi retry
```

Ở đây `PUT` giống thao tác **đặt trạng thái mong muốn**. Gửi cùng body nhiều lần đến cùng tài nguyên, không có thao tác cạnh tranh hoặc ràng buộc phiên bản làm thay đổi kết quả, sẽ có trạng thái tài nguyên giống nhau sau mỗi lần áp dụng.

### 3.1. Idempotent không đồng nghĩa response giống hệt

Ví dụ:

1. `DELETE /api/documents/1` lần đầu: 204; tài nguyên bị xóa.
2. `DELETE /api/documents/1` lần hai: 404 vì tài nguyên đã không còn.
3. **Hiệu ứng cuối:** tài nguyên vẫn không tồn tại; `DELETE` vẫn là idempotent.

Tương tự, `PUT` có điều kiện `If-Match: "v1"` có thể thành công lần đầu, rồi trả 412 ở lần retry vì version đã đổi sang `"v2"`. **Điều này không làm PUT mất tính idempotent**: request lặp lại không ghi đè hoặc nhân đôi thay đổi. Response không nhất thiết giữ nguyên status/body/header.

Server có thể ghi access log mới, metric mới hoặc thực hiện một số side effect phục vụ quản trị sau mỗi request mà không làm thay đổi định nghĩa idempotent của phương thức. Tuy nhiên, **side effect thuộc nghiệp vụ** như gửi hai hóa đơn, trừ tiền hai lần hoặc bắn hai sự kiện giao hàng thì **cần cơ chế chống lặp rõ ràng**. Không dựa riêng vào nhãn PUT để suy ra exactly-once cho toàn bộ quy trình.

### 3.2. Bảng suy luận yêu cầu lặp

| Request | Lần đầu | Lặp lại nguyên request | Idempotent về hiệu ứng? |
| --- | --- | --- | --- |
| `PUT /docs/1` body cố định | Đặt tài liệu thành X | Vẫn X | Có |
| `PATCH` set `title="X"` | Đặt title thành X | Vẫn X | Có thể có |
| `PATCH` `increment count by 1` | count 5 → 6 | 6 → 7 | Không |
| `PATCH` JSON Patch `replace /title "X"` | title thành X | Vẫn X, nếu path tồn tại | Có thể có |
| `PATCH` JSON Patch `add /items/- "A"` | Append phần tử | Append thêm lần nữa | Không |
| `DELETE /docs/1` | Xóa tài liệu | Không có thêm tài liệu nào bị xóa | Có |
| `POST /payments` body cố định | Tạo giao dịch | Có thể tạo thêm giao dịch | Không mặc định |

**Giới hạn:** điều kiện tiền đề, side effect, tài nguyên liên quan và hợp đồng API quyết định tính idempotent thật sự. Không nên nói “PATCH luôn không idempotent”: RFC 5789 cho phép client thiết kế PATCH theo cách idempotent, và nên dùng điều kiện cập nhật để giảm xung đột.

### 3.3. Vì sao idempotency quan trọng cho retry?

Các sự cố có thể xảy ra sau khi request rời client:

- Kết nối đứt trước khi server nhận body.
- Server hoàn tất transaction nhưng response mất trên đường về.
- Gateway timeout rồi client hoặc proxy retry.
- Mobile app gửi lại do trạng thái mạng không chắc chắn.

Client khó phân biệt **“không thực thi”** với **“thực thi rồi nhưng mất phản hồi”**. Vì vậy, thiết kế PUT/PATCH cần quy tắc xác nhận kết quả; mọi thao tác không-idempotent cần nhận diện duplicate và kiểm tra hậu trạng thái trước khi chạy lại.

**Retry chỉ an toàn nếu thỏa hợp đồng.** Với PATCH thao tác cộng dồn, server phải có điều kiện/chốt chống lặp hoặc client không được tự động resend mù quáng.

## 4. Hai chuẩn phổ biến cho JSON PATCH document

### 4.1. JSON Merge Patch (RFC 7396)

Media type: `application/merge-patch+json`.

Cho tài nguyên:

```json
{
  "title": "Draft",
  "description": "Need review",
  "labels": ["java", "rest"],
  "settings": {"visible": false, "theme": "light"}
}
```

Gửi:

```http
PATCH /api/documents/1 HTTP/1.1
Content-Type: application/merge-patch+json

{
  "title": "Final",
  "description": null,
  "settings": {"visible": true}
}
```

Kết quả:

```json
{
  "title": "Final",
  "labels": ["java", "rest"],
  "settings": {"visible": true, "theme": "light"}
}
```

Quy tắc:

- **Vắng mặt:** giữ nguyên giá trị cũ.
- **Có giá trị khác null:** thêm/thay thế; với nested object, Merge Patch xử lý đệ quy.
- **Có giá trị null:** **xóa field** khỏi object đích, không phải “đặt field thành JSON null” theo nghĩa dữ liệu thông thường.
- **Array:** thường thay toàn bộ array; Merge Patch không hỗ trợ thay một phần tử theo chỉ số.
- **Patch không phải object:** thay toàn bộ target bằng giá trị patch. Một API có thể từ chối điều này theo schema tài nguyên, nhưng phải công bố rõ.
- **Áp dụng lại cùng Merge Patch thuần túy** lên trạng thái cuối thường không đổi dữ liệu nữa; tuy nhiên version/side effect của implementation cần được thiết kế đúng, và có thể gặp xung đột với cập nhật xen giữa.

Merge Patch phù hợp với resource có cấu trúc object và khi null không phải một giá trị cần lưu phân biệt với **xóa key**. Nếu domain cho phép field lưu JSON null hợp lệ, Merge Patch dễ mơ hồ; chọn JSON Patch hoặc hợp đồng chuyên biệt.

### 4.2. JSON Patch (RFC 6902)

Media type: `application/json-patch+json`. Body là **một mảng thao tác có thứ tự**:

```http
PATCH /api/documents/1 HTTP/1.1
Content-Type: application/json-patch+json

[
  {"op":"test","path":"/title","value":"Draft"},
  {"op":"replace","path":"/title","value":"Final"},
  {"op":"remove","path":"/description"}
]
```

Các operation trong RFC 6902:

| Operation | Tác dụng điển hình | Khi lặp lại |
| --- | --- | --- |
| `add` | Thêm/ghi vào object key hoặc chèn phần tử array | Thêm object key thường ổn; chèn array có thể lặp |
| `remove` | Xóa một vị trí tồn tại | Lần lặp có thể báo lỗi vì path không còn |
| `replace` | Thay giá trị ở path tồn tại | Thường giữ cùng giá trị khi lặp |
| `move` | Dời giá trị từ `from` sang `path` | Phụ thuộc cấu trúc sau lần đầu |
| `copy` | Sao chép từ `from` sang `path` | Phụ thuộc cấu trúc đích |
| `test` | Kiểm tra giá trị tại path; sai thì toàn patch thất bại | Hữu ích như tiền điều kiện trong patch |

Path sử dụng **JSON Pointer** (RFC 6901); ký tự `~` và `/` trong tên property phải escape thành `~0` và `~1`. Chỉ số array và `-` (vị trí append) có ngữ nghĩa riêng. Ví dụ:

```json
[
  {"op":"add","path":"/labels/-","value":"spring"}
]
```

Nếu không chống lặp, gửi lại request này sẽ append thêm `"spring"` một lần nữa. JSON Patch **không tự nhiên idempotent** chỉ vì HTTP method là PATCH.

RFC 5789 yêu cầu **áp dụng patch atomically**: nếu một operation thất bại giữa danh sách, server không được công khai một representation cập nhật dở và không được giữ một phần thay đổi. Triển khai production cần transaction/rollback hoặc cơ chế tương đương cho mọi cập nhật liên quan.

### 4.3. PATCH với body JSON tự định nghĩa

Nhiều API chọn:

```http
PATCH /api/orders/42 HTTP/1.1
Content-Type: application/json

{"status":"SHIPPED"}
```

Cách này có thể hợp lệ nếu API **định nghĩa rõ** body là “các field được phép thay đổi, field vắng mặt giữ nguyên, null nghĩa X”. Nhưng không tự gọi nó là RFC 7396 nếu không tuân đầy đủ Merge Patch (ví dụ null được lưu thành null, hoặc array được merge theo index). Nên cân nhắc vendor media type và tài liệu OpenAPI/contract.

Khi cần thay đổi quan hệ nghiệp vụ như “thu tiền”, “xác nhận”, “thêm đơn vị hàng”, một **command endpoint POST** với idempotency key đôi khi biểu đạt hành vi rõ hơn việc dùng PATCH mơ hồ. Chọn method theo ngữ nghĩa tài nguyên, không theo độ dễ của controller annotation.

## 5. Vấn đề khó: cập nhật đồng thời và lost update

Giả sử trạng thái ban đầu:

```json
{"title":"Draft","description":"Original"}
```

Hai client cùng GET lúc 10:00:

1. Client A đổi `title` thành `"Published"` rồi PUT full object.
2. Client B vẫn giữ bản cũ, đổi `description` thành `"Revised"` rồi PUT full object.
3. Nếu server nhận B sau A mà **không kiểm tra phiên bản**, body B có thể chứa `title="Draft"`, vô tình ghi đè `"Published"` của A.

Đây là **lost update**, có thể xảy ra dù PUT hoàn toàn idempotent. Idempotency giải quyết rủi ro **lặp cùng yêu cầu**, không tự giải quyết việc **hai yêu cầu hợp lệ khác nhau cạnh tranh**.

PATCH giảm nguy cơ ghi đè field không liên quan nếu nó chỉ thay field gửi lên, nhưng vẫn có thể xung đột logic; hai client cùng sửa `description`, một người dựa vào version cũ, hoặc một JSON Patch thao tác chỉ số array bị thay đổi sẽ có vấn đề. Vì vậy cả PUT lẫn PATCH cần cơ chế concurrency control.

### 5.1. ETag + If-Match (optimistic concurrency)

Một cách HTTP chuẩn là trả **strong ETag** khi GET tài nguyên:

```http
GET /api/documents/1 HTTP/1.1

HTTP/1.1 200 OK
ETag: "v7"
Content-Type: application/json

{"title":"Draft","description":"Original"}
```

Client gửi phiên bản mà mình vừa đọc:

```http
PUT /api/documents/1 HTTP/1.1
If-Match: "v7"
Content-Type: application/json

{"title":"Published","description":"Original"}
```

Server thực hiện một bước **kiểm tra và cập nhật nguyên tử**:

```text
Tài nguyên có current ETag "v7"?
  ├── Có → xác thực input, ghi bản cập nhật, chuyển version mới
  └── Không → KHÔNG ghi đè, trả 412 Precondition Failed
```

Nếu A đã cập nhật thành `"v8"` thì PUT cũ của B với `If-Match: "v7"` bị từ chối bằng **412**, thay vì tự động đè A. B cần GET trạng thái mới và quyết định merge/edit lại.

**Điều quan trọng:**

- `If-Match` dùng **strong comparison**. Weak ETag như `W/"v7"` không đủ điều kiện so khớp strong với `"v7"`.
- `If-Match: *` yêu cầu tài nguyên có representation hiện tại, **không** có nghĩa kiểm tra phiên bản cụ thể; nó không ngăn lost update từ bản cũ.
- `If-Match` có thể chứa danh sách entity tags hợp lệ. Ví dụ chạy ở mục 8 **cố ý chỉ hỗ trợ một tag mạnh đúng nguyên dạng** để code tập trung; production phải tuân toàn bộ cú pháp/preconditions theo HTTP spec.
- Nếu client không gửi điều kiện và chính sách API bắt buộc optimistic concurrency, trả **428 Precondition Required**. Nếu đã gửi nhưng tag sai, trả **412 Precondition Failed**.
- Không dùng `If-None-Match` thay cho `If-Match` khi bảo vệ một cập nhật đang tồn tại; `If-None-Match: *` chủ yếu hữu ích để **tạo mới nếu chưa tồn tại**.
- Một entity tag không nhất thiết là số version hiển thị; có thể là hash representation hoặc opaque token, miễn chính sách strong validator đúng. Không so sánh ETag như số bằng dấu lớn hơn/nhỏ hơn.

### 5.2. ETag có khác @Version trong JPA?

`@Version` của Jakarta Persistence là optimistic locking ở **lớp lưu trữ**; ETag/If-Match là hợp đồng **HTTP**. Chúng có thể phối hợp:

```text
HTTP GET  → đọc hàng (id=1, version=7) → tạo ETag "v7"
HTTP PUT  → nhận If-Match "v7"
          → transaction kiểm tra DB version=7
          → UPDATE ... WHERE id=1 AND version=7
          → cập nhật version=8
          → commit
HTTP GET  → ETag "v8"
```

Không chỉ làm:

```java
if (incomingTag.equals(currentTag)) {
    // đọc xong, một transaction khác có thể xen vào ở đây
    repository.save(entity);
}
```

Check-then-write không có transaction/locking/CAS là **race condition**. Với nhiều instance ứng dụng, `synchronized` trên một JVM cũng không đủ vì mỗi instance có lock riêng. Hãy dùng DB transaction, optimistic locking/version, compare-and-swap hoặc atomic operation của storage.

### 5.3. Retry sau khi request đã thành công nhưng response mất

Ví dụ:

```text
Trạng thái trước: ETag "v7"
Client gửi: PUT body X + If-Match "v7"
Server: commit X, tăng tag thành "v8"; response bị mất
Client retry NGUYÊN request: PUT body X + If-Match "v7"
Server: thấy tag "v8" → 412, KHÔNG ghi lần hai
Client: GET mới, đối chiếu nội dung và quyết định kết quả
```

Đây là phản hồi an toàn. Không gọi HTTP 412 là “chắc chắn thất bại toàn bộ thao tác từ đầu”; có thể request trước đó **đã thành công**. Client nên GET/đối chiếu trạng thái hoặc dùng cơ chế idempotency result tracking nếu cần biết chắc kết quả của một hành động nghiệp vụ.

HTTP cho phép một số trường hợp server trả 2xx nếu xác định trạng thái đã giống yêu cầu cũ, nhưng **không được tùy tiện ghi đè trạng thái mới** và không nên trả ETag mới sai ngữ nghĩa. Để dễ giải thích, demo sử dụng 412 nghiêm ngặt nếu tag không còn khớp.

## 6. Quy tắc thiết kế response/status cho cập nhật

| HTTP status | Dùng khi nào | Gợi ý response |
| --- | --- | --- |
| **200 OK** | PUT/PATCH thành công và trả representation hoặc metadata | JSON body phản ánh trạng thái mới |
| **204 No Content** | PUT/PATCH thành công, client không cần body | **Không có body**; có thể trả metadata phù hợp |
| **201 Created** | PUT tạo mới resource tại URI | `Location` khi hữu ích; trả representation nếu cần |
| **400 Bad Request** | Body sai cú pháp, thiếu field bắt buộc, input contract không hợp lệ | Mã lỗi/chi tiết an toàn |
| **404 Not Found** | Tài nguyên đích không có, API không cho PUT create | Thông báo resource không tồn tại |
| **409 Conflict** | Xung đột trạng thái nghiệp vụ hoặc patch conflict không được biểu diễn bằng precondition HTTP | Mã lỗi và hướng fetch/reconcile |
| **412 Precondition Failed** | `If-Match`/điều kiện HTTP được gửi nhưng thất bại | Yêu cầu client đọc lại trạng thái |
| **415 Unsupported Media Type** | Không hỗ trợ patch content type | Có thể quảng bá patch format cho client |
| **422 Unprocessable Content** | Hiểu content type/cú pháp nhưng không xử lý được chỉ dẫn về nghĩa, nếu hợp đồng chọn status này | Mô tả lỗi semantic phù hợp |
| **428 Precondition Required** | API đòi gửi điều kiện cập nhật để tránh lost update | Hướng dẫn client dùng If-Match |

Không gán tất cả lỗi PATCH là 409. Nếu header `If-Match` được đánh giá và không khớp, **412** biểu đạt rõ hơn. Nếu API chủ động yêu cầu header nhưng thiếu, **428** là lựa chọn đúng. Với validation thông thường, Spring MVC thường trả **400**, còn sử dụng **422** là quyết định contract chứ không mặc định Spring tự áp dụng.

**ETag trong response PUT:** HTTP đặt điều kiện nghiêm về gửi validator sau PUT thành công: không trả `ETag`/`Last-Modified` nếu request representation đã bị server biến đổi khi lưu và validator không phản ánh chính xác biểu diễn được lưu. Demo bên dưới **không gửi ETag trong response PUT**; client gọi GET để nhận validator mới. Trong GET, ETag được trả cho representation hiện tại. Với PATCH, server cũng có thể trả thông tin version sau cập nhật nếu được tính đúng.

### 6.1. Công bố patch formats

RFC 5789 định nghĩa header `Accept-Patch`, thường có thể quảng bá trong response `OPTIONS`:

```http
OPTIONS /api/documents/1 HTTP/1.1

HTTP/1.1 204 No Content
Allow: GET, PUT, PATCH, OPTIONS
Accept-Patch: application/merge-patch+json, application/json-patch+json
```

Đây là **ví dụ HTTP do server giả định hỗ trợ cả hai chuẩn**; đừng trả danh sách format chưa triển khai. Trong Spring MVC, chỉ khai báo `@PatchMapping(consumes = ...)` chưa chắc tự sinh header `Accept-Patch` như ví dụ. Nếu muốn quảng bá, cấu hình endpoint/response phù hợp và kiểm thử.

## 7. Thiết kế DTO, absent/null và bảo mật khi cập nhật

Với PUT thay thế tài nguyên, một DTO đủ điều kiện thường có field rõ ràng. Với PATCH partial, cần phân biệt ít nhất **ba trạng thái**:

1. Field **vắng mặt** → không chạm tới.
2. Field **hiện diện với giá trị** → thay thành giá trị đó.
3. Field **hiện diện với null** → tùy định dạng: JSON Merge Patch **xóa key**, còn DTO partial tự định nghĩa có thể xem như “đặt null”, “xóa dữ liệu” hoặc “không cho phép”.

Nếu bind PATCH trực tiếp vào:

```java
record PatchProfile(String nickname, String phone) {}
```

thì cả JSON `{}` và `{"phone":null}` thường cùng tạo `phone == null`, làm mất thông tin “client không gửi” và “client yêu cầu xóa”. Nếu cần phân biệt, dùng `JsonNode`/`Map` có kiểm tra key hiện diện, hoặc wrapper ba trạng thái chuyên dụng được ánh xạ rõ ràng.

**Validation khác PUT/PATCH:** PUT thường dùng constraint cho toàn representation mới. PATCH thường validate **patch document**, áp dụng patch lên object tạm, rồi validate **trạng thái kết quả toàn tài nguyên** trước commit. Không chỉ validate từng field đơn lẻ, vì thay một field có thể phá bất biến liên trường.

**Bảo mật:**

- Chỉ cho phép sửa những field đã được công bố; từ chối `role`, `isAdmin`, `balance`, `createdAt` nếu client không có quyền. Không bind thẳng request vào persistence entity có setters rộng.
- Kiểm tra authorization với **resource ID** và từng field/hành động; ETag không thay xác thực/phân quyền.
- Giới hạn kích thước patch document, số operation, độ sâu JSON, đường dẫn JSON Pointer/array indices.
- Áp dụng patch atomically trong transaction; kiểm tra quy tắc nghiệp vụ và concurrency trước commit.
- Tránh phản hồi lại dữ liệu nhạy cảm hoặc stack trace từ Jackson/JPA.

## 8. Demo Spring Boot 3 + Java 17: PUT/PATCH + ETag/If-Match

Ứng dụng này quản lý đúng **một tài liệu** tại `/api/documents/1`, lưu **trong bộ nhớ một JVM** để minh họa ngữ nghĩa và request flow. Không có database, authentication, multi-node synchronization. Code dùng `synchronized` để kiểm tra version và cập nhật nguyên tử trên **một instance controller**; phần 10 giải thích cách chuyển sang storage thật.

Demo hỗ trợ:

- `GET /api/documents/1` trả representation và strong ETag `"v1"`, `"v2"`...
- `PUT /api/documents/1` với toàn bộ representation và `If-Match`, cùng trạng thái thì không tăng version.
- `PATCH /api/documents/1` chỉ nhận `application/merge-patch+json` cho hai field phẳng `title` và `description`. Bỏ field nghĩa giữ nguyên; `description:null` nghĩa xóa khỏi representation. `title` phải là chuỗi không trắng và không được xóa.
- Từ chối unknown field/kiểu JSON sai, đảm bảo **không update một phần khi request lỗi**.
- Trả 404 khi ID khác 1, 428 nếu thiếu `If-Match`, 412 nếu stale tag, 400 nếu input không hợp lệ.

Đây là **subset có schema tài liệu cố định** của JSON Merge Patch: body phải là object và chỉ được chứa hai field được phép. Nó không phải implementation JSON Merge Patch tổng quát cho mọi cấu trúc JSON/array hoặc mọi resource.

### 8.1. Cấu trúc project

```text
document-update-demo/
├── pom.xml
└── src/
    ├── main/java/example/DocumentUpdateApplication.java
    └── test/java/example/DocumentControllerTest.java
```

### 8.2. pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>document-update-demo</artifactId>
    <version>1.0.0</version>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-validation</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

### 8.3. DocumentUpdateApplication.java (chương trình chạy được)

Toàn bộ class/record nằm trong file `src/main/java/example/DocumentUpdateApplication.java`. Java cho phép một `public` top-level class trùng tên file và các class package-private khác.

```java
package example;

import java.util.Iterator;
import java.util.Map;
import java.util.Objects;

import com.fasterxml.jackson.annotation.JsonInclude;
import com.fasterxml.jackson.databind.JsonNode;

import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PatchMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class DocumentUpdateApplication {
    public static void main(String[] args) {
        SpringApplication.run(DocumentUpdateApplication.class, args);
    }
}

// Null description được bỏ qua khi serialize response JSON.
// Với PUT, đây là representation mới; bỏ description sẽ làm nó thành null.
@JsonInclude(JsonInclude.Include.NON_NULL)
record Document(@NotBlank String title, String description) {}

// Body lỗi đơn giản, chỉ chứa mã do demo định nghĩa.
record ApiProblem(String code) {}

@RestController
@RequestMapping("/api/documents")
class DocumentController {

    private Document current = new Document("Draft", "Initial description");
    private long version = 1L;

    private String currentTag() {
        return "\"v" + version + "\"";
    }

    private ResponseEntity<?> guard(long id, String ifMatch) {
        if (id != 1L) {
            return ResponseEntity.status(HttpStatus.NOT_FOUND)
                    .body(new ApiProblem("NOT_FOUND"));
        }
        if (ifMatch == null || ifMatch.isBlank()) {
            return ResponseEntity.status(HttpStatus.PRECONDITION_REQUIRED)
                    .body(new ApiProblem("PRECONDITION_REQUIRED"));
        }
        // Demo chỉ nhận một strong ETag dạng "vN".
        // Sản phẩm thực cần xử lý danh sách tags và các precondition
        // đầy đủ theo RFC 9110.
        if (!ifMatch.equals(currentTag())) {
            return ResponseEntity.status(HttpStatus.PRECONDITION_FAILED)
                    .body(new ApiProblem("STALE_VERSION"));
        }
        return null;
    }

    @GetMapping("/{id}")
    public synchronized ResponseEntity<?> get(@PathVariable long id) {
        if (id != 1L) {
            return ResponseEntity.status(HttpStatus.NOT_FOUND)
                    .body(new ApiProblem("NOT_FOUND"));
        }
        return ResponseEntity.ok()
                .eTag(currentTag())
                .body(current);
    }

    @PutMapping(path = "/{id}",
                consumes = MediaType.APPLICATION_JSON_VALUE)
    public synchronized ResponseEntity<?> put(
            @PathVariable long id,
            @RequestHeader(value = "If-Match", required = false)
            String ifMatch,
            @Valid @RequestBody Document replacement) {

        ResponseEntity<?> precondition = guard(id, ifMatch);
        if (precondition != null) {
            return precondition;
        }

        // PUT gửi representation thay thế. Nếu body giống trạng thái
        // hiện tại thì không tạo thêm một phiên bản chỉ vì retry.
        if (!Objects.equals(current, replacement)) {
            current = replacement;
            version++;
        }

        // GET tiếp theo cung cấp ETag mới. Không tự động đưa
        // validator vào response PUT khi server có thể biến đổi dữ liệu.
        return ResponseEntity.ok(current);
    }

    @PatchMapping(path = "/{id}",
                  consumes = "application/merge-patch+json")
    public synchronized ResponseEntity<?> patch(
            @PathVariable long id,
            @RequestHeader(value = "If-Match", required = false)
            String ifMatch,
            @RequestBody JsonNode patchDocument) {

        ResponseEntity<?> precondition = guard(id, ifMatch);
        if (precondition != null) {
            return precondition;
        }

        if (!patchDocument.isObject()) {
            return ResponseEntity.badRequest()
                    .body(new ApiProblem("INVALID_PATCH_DOCUMENT"));
        }

        // Xây dựng candidate trước, không sửa current giữa chừng.
        String newTitle = current.title();
        String newDescription = current.description();

        Iterator<Map.Entry<String, JsonNode>> entries =
                patchDocument.fields();

        while (entries.hasNext()) {
            Map.Entry<String, JsonNode> entry = entries.next();
            String field = entry.getKey();
            JsonNode value = entry.getValue();

            if (field.equals("title")) {
                if (!value.isTextual() || value.asText().isBlank()) {
                    return ResponseEntity.badRequest()
                            .body(new ApiProblem("INVALID_TITLE"));
                }
                newTitle = value.asText();
            } else if (field.equals("description")) {
                if (!value.isNull() && !value.isTextual()) {
                    return ResponseEntity.badRequest()
                            .body(new ApiProblem("INVALID_DESCRIPTION"));
                }
                // Merge Patch: null nghĩa xóa property khỏi representation.
                newDescription = value.isNull() ? null : value.asText();
            } else {
                return ResponseEntity.badRequest()
                        .body(new ApiProblem("UNKNOWN_PATCH_FIELD"));
            }
        }

        Document candidate = new Document(newTitle, newDescription);

        // Commit duy nhất khi toàn bộ patch đã qua kiểm tra.
        if (!candidate.equals(current)) {
            current = candidate;
            version++;
        }

        return ResponseEntity.ok(current);
    }
}
```

**Cơ chế quan trọng:**

- `currentTag()` là token mạnh được bao trong dấu `"..."`. Đây là implementation minh họa: version đổi khi representation thay đổi; các instance khác sẽ không dùng chung bộ đếm nếu chuyển thành multi-node.
- `guard()` dùng tag đọc được khi GET, yêu cầu header trước PUT/PATCH và ngăn request stale. `If-Match` trong demo dùng **so sánh chuỗi đơn**; production cần parser/so sánh HTTP precondition đầy đủ.
- PUT nhận `Document` có `@NotBlank title`; body đủ điều kiện cập nhật toàn representation. `description` bị thiếu trở thành `null` và không được giữ ngầm. `@JsonInclude(NON_NULL)` giúp biểu diễn GET bỏ field description khi nó đã bị xóa.
- PATCH nhận `JsonNode` để phân biệt **field vắng mặt** với **field có null**. Title không được xóa vì ràng buộc domain; description null xóa field khỏi JSON output.
- Cả PUT và PATCH chỉ tăng version nếu `Document` cuối khác bản hiện tại. Patch lỗi trả 400 trước khi gán `current`, thỏa atomicity cho tài nguyên trong-memory này.
- `synchronized` làm check và mutation có cùng lock trong một JVM. Đây không phải phương án multi-instance production.
- API chọn chính sách **update-only** cho ID=1, không hỗ trợ PUT-create; ID khác được trả 404 theo hợp đồng demo.

### 8.4. Chạy và thử với curl

Cần JDK 17+ và Maven; tại thư mục chứa `pom.xml`:

```bash
mvn test
mvn spring-boot:run
```

Đầu tiên đọc tài nguyên và ETag:

```bash
curl -i http://localhost:8080/api/documents/1
```

Response minh họa (có thể kèm các header khác do HTTP server):

```http
HTTP/1.1 200 OK
ETag: "v1"
Content-Type: application/json

{"title":"Draft","description":"Initial description"}
```

**PUT thay thế**:

```bash
curl -i -X PUT http://localhost:8080/api/documents/1 \
  -H 'Content-Type: application/json' \
  -H 'If-Match: "v1"' \
  -d '{"title":"Published","description":"Final description"}'
```

Server trả **200** với body:

```json
{"title":"Published","description":"Final description"}
```

GET lại:

```bash
curl -i http://localhost:8080/api/documents/1
```

Kỳ vọng ETag `"v2"` vì representation đã thay đổi. Nếu retry đúng nguyên PUT cùng `If-Match: "v1"`, server trả **412**:

```json
{"code":"STALE_VERSION"}
```

Tài nguyên vẫn là `{"title":"Published","description":"Final description"}`; không có thao tác ghi lần thứ hai.

**PATCH chỉ xóa description**:

```bash
curl -i -X PATCH http://localhost:8080/api/documents/1 \
  -H 'Content-Type: application/merge-patch+json' \
  -H 'If-Match: "v2"' \
  -d '{"description":null}'
```

Body thành công:

```json
{"title":"Published"}
```

GET lại có ETag `"v3"` và body không có `description`. Trường vắng mặt trong PATCH (ví dụ `{"title":"Final"}`) sẽ giữ description, trong khi `"description":null` chủ ý loại bỏ nó.

**Thiếu điều kiện cập nhật**:

```bash
curl -i -X PATCH http://localhost:8080/api/documents/1 \
  -H 'Content-Type: application/merge-patch+json' \
  -d '{"title":"Danger"}'
```

Kỳ vọng **428** với:

```json
{"code":"PRECONDITION_REQUIRED"}
```

Lưu ý: đoạn `curl` trên dùng dấu nối dòng của shell POSIX; PowerShell có thể dùng `curl.exe` và gõ một dòng, hoặc thay cú pháp multiline tương ứng.

### 8.5. MockMvc: chứng minh thay thế, partial update, retry và precondition

File `src/test/java/example/DocumentControllerTest.java`:

```java
package example;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.annotation.DirtiesContext;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.patch;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.put;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
@DirtiesContext(classMode = DirtiesContext.ClassMode.BEFORE_EACH_TEST_METHOD)
class DocumentControllerTest {

    @Autowired
    MockMvc mvc;

    @Test
    void getExposesInitialStrongEtag() throws Exception {
        mvc.perform(get("/api/documents/1"))
            .andExpect(status().isOk())
            .andExpect(header().string("ETag", "\"v1\""))
            .andExpect(jsonPath("$.title").value("Draft"));
    }

    @Test
    void putReplacesAndRetryWithStaleEtagDoesNotOverwrite() throws Exception {
        String body =
                "{\"title\":\"Published\","
              + "\"description\":\"Final description\"}";

        mvc.perform(put("/api/documents/1")
                    .contentType(MediaType.APPLICATION_JSON)
                    .header("If-Match", "\"v1\"")
                    .content(body))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.title").value("Published"));

        mvc.perform(get("/api/documents/1"))
            .andExpect(header().string("ETag", "\"v2\""));

        mvc.perform(put("/api/documents/1")
                    .contentType(MediaType.APPLICATION_JSON)
                    .header("If-Match", "\"v1\"")
                    .content(body))
            .andExpect(status().isPreconditionFailed())
            .andExpect(jsonPath("$.code").value("STALE_VERSION"));

        mvc.perform(get("/api/documents/1"))
            .andExpect(status().isOk())
            .andExpect(header().string("ETag", "\"v2\""))
            .andExpect(jsonPath("$.description")
                    .value("Final description"));
    }

    @Test
    void putWithSameRepresentationHasNoAdditionalEffect() throws Exception {
        String same =
                "{\"title\":\"Draft\","
              + "\"description\":\"Initial description\"}";

        for (int n = 0; n < 2; n++) {
            mvc.perform(put("/api/documents/1")
                        .contentType(MediaType.APPLICATION_JSON)
                        .header("If-Match", "\"v1\"")
                        .content(same))
                .andExpect(status().isOk());
        }

        mvc.perform(get("/api/documents/1"))
            .andExpect(header().string("ETag", "\"v1\""));
    }

    @Test
    void patchDistinguishesOmittedFieldAndExplicitNull() throws Exception {
        mvc.perform(patch("/api/documents/1")
                    .contentType("application/merge-patch+json")
                    .header("If-Match", "\"v1\"")
                    .content("{\"title\":\"Published\"}"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.title").value("Published"))
            .andExpect(jsonPath("$.description")
                    .value("Initial description"));

        mvc.perform(get("/api/documents/1"))
            .andExpect(header().string("ETag", "\"v2\""));

        mvc.perform(patch("/api/documents/1")
                    .contentType("application/merge-patch+json")
                    .header("If-Match", "\"v2\"")
                    .content("{\"description\":null}"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.description").doesNotExist());

        mvc.perform(get("/api/documents/1"))
            .andExpect(header().string("ETag", "\"v3\""))
            .andExpect(jsonPath("$.description").doesNotExist());
    }

    @Test
    void patchWithNoStateChangeCanRepeatWithSameEtag() throws Exception {
        for (int n = 0; n < 2; n++) {
            mvc.perform(patch("/api/documents/1")
                        .contentType("application/merge-patch+json")
                        .header("If-Match", "\"v1\"")
                        .content("{\"title\":\"Draft\"}"))
                .andExpect(status().isOk());
        }

        mvc.perform(get("/api/documents/1"))
            .andExpect(header().string("ETag", "\"v1\""));
    }

    @Test
    void incompletePutReplacesAbsentOptionalField() throws Exception {
        mvc.perform(put("/api/documents/1")
                    .contentType(MediaType.APPLICATION_JSON)
                    .header("If-Match", "\"v1\"")
                    .content("{\"title\":\"Only title\"}"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.title").value("Only title"))
            .andExpect(jsonPath("$.description").doesNotExist());
    }

    @Test
    void missingConditionIs428AndLeavesStateIntact() throws Exception {
        mvc.perform(put("/api/documents/1")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content(
                        "{\"title\":\"Other\", \"description\":\"Text\"}"))
            .andExpect(status().is(428))
            .andExpect(jsonPath("$.code")
                    .value("PRECONDITION_REQUIRED"));

        mvc.perform(get("/api/documents/1"))
            .andExpect(header().string("ETag", "\"v1\""));
    }

    @Test
    void invalidPatchFailsAtomically() throws Exception {
        mvc.perform(patch("/api/documents/1")
                    .contentType("application/merge-patch+json")
                    .header("If-Match", "\"v1\"")
                    .content(
                        "{\"title\":\"Changed\", \"privileged\":true}"))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.code")
                    .value("UNKNOWN_PATCH_FIELD"));

        mvc.perform(get("/api/documents/1"))
            .andExpect(header().string("ETag", "\"v1\""))
            .andExpect(jsonPath("$.title").value("Draft"));
    }

    @Test
    void invalidPutDataCannotReplaceResource() throws Exception {
        mvc.perform(put("/api/documents/1")
                    .contentType(MediaType.APPLICATION_JSON)
                    .header("If-Match", "\"v1\"")
                    .content(
                        "{\"title\":\"\", \"description\":\"Ignored\"}"))
            .andExpect(status().isBadRequest());

        mvc.perform(get("/api/documents/1"))
            .andExpect(header().string("ETag", "\"v1\""));
    }

    @Test
    void unsupportedPatchMediaTypeIs415() throws Exception {
        mvc.perform(patch("/api/documents/1")
                    .contentType(MediaType.TEXT_PLAIN)
                    .header("If-Match", "\"v1\"")
                    .content("title=Changed"))
            .andExpect(status().isUnsupportedMediaType());
    }
}
```

Chạy `mvn test`. Mỗi test có Spring context mới nhờ `@DirtiesContext(BEFORE_EACH_TEST_METHOD)` để reset bộ nhớ ban đầu về `"v1"`; cách này đơn giản cho ví dụ nhỏ nhưng tương đối tốn chi phí khi test nhiều. Với project thực tế, thay bằng test fixture reset dữ liệu một cách có kiểm soát và kiểm thử cả luồng transaction/concurrency ở persistence layer.

Các test xác nhận **trạng thái cuối cùng** sau update/retry. Chỉ assert status 200 không đủ để chứng minh idempotency hoặc không có lost update.

## 9. Thiết kế retry khi không chắc lần trước đã thành công

### 9.1. Retry PUT

Nếu PUT được thiết kế đúng ngữ nghĩa thay thế, request lặp cùng body thường đưa trạng thái về cùng biểu diễn mong muốn. Với If-Match:

1. Gửi PUT có `If-Match: "vN"`.
2. Nếu nhận **200/204**, cập nhật local cache hoặc GET lại nếu cần token phiên bản mới.
3. Nếu timeout và retry request, có thể nhận **412** vì lần đầu đã commit. Không coi 412 là bằng chứng “chưa lần nào thành công”; GET và đối chiếu.
4. Nếu trạng thái mới trùng mục tiêu, xử lý như “đã đạt trạng thái mong muốn” khi workflow cho phép. Nếu khác, hiển thị conflict/đề nghị merge.
5. Không tự động bỏ `If-Match` khi gặp 412 để “ép ghi cho thành công”; làm vậy có thể ghi đè người khác.

### 9.2. Retry PATCH

Phân loại patch:

- **Patch theo giá trị mục tiêu:** `{"title":"Final"}` với Merge Patch có thể chạy nhiều lần mà trạng thái nội dung không đổi sau lần đầu; vẫn dùng If-Match để tránh cập nhật trên phiên bản cũ.
- **Patch phụ thuộc trạng thái:** JSON Patch có `test` hoặc `remove`; retry có thể trả lỗi vì base đã đổi; cần GET rồi tính lại.
- **Patch cộng dồn:** `{"increment":1}` là hợp đồng command riêng không phải RFC Merge Patch thuần túy; retry mù sẽ nhân đôi.
- **Patch append:** JSON Patch thêm vào `/items/-` có thể lặp phần tử; cần token chống lặp hoặc chính sách về item identity.

Nếu PATCH không idempotent, hãy dùng **idempotency key** nếu server hỗ trợ, hoặc thay thiết kế thành “set trạng thái mong muốn” / item resource có URI ổn định, hoặc dùng precondition kèm logic reconcile. Đừng suy ra chỉ gửi `If-Match` là sẽ tự trả lại response giống hệt khi retry: If-Match chỉ bảo vệ **version trước khi áp dụng**, không lưu kết quả của request cũ.

### 9.3. Idempotency-Key cho thao tác không-idempotent

Ví dụ nghiệp vụ thêm một khoản thanh toán:

```http
POST /api/payments HTTP/1.1
Idempotency-Key: 58f147f6-6b4d-4f8b-9b2e-1a1c4ef9a53a
Content-Type: application/json

{"orderId":42,"amount":150000}
```

Đây là **một hợp đồng do API triển khai**. Header không tự tạo idempotency khi server không có cơ chế xử lý. Backend cần:

1. Chuẩn hóa phạm vi khóa (user/tenant + operation + key) và request fingerprint; cùng key với payload khác → lỗi phù hợp.
2. Dành chỗ cho key một cách **nguyên tử** với giao dịch, tránh hai request đồng thời cùng thực hiện.
3. Lưu trạng thái in-progress/succeeded/failed và kết quả có thể replay theo chính sách; không thực hiện side effect lần hai khi key đã hoàn tất.
4. Thiết lập thời hạn lưu, cơ chế khôi phục khi process crash, timeout và retry.
5. Với external event/payment, kết hợp transaction/outbox, provider idempotency key hoặc deduplication ở consumer. Không chỉ lưu key trong một `HashMap` của process nếu cần bảo đảm đa instance.

Có thể áp dụng cùng nguyên tắc cho PATCH có thao tác append/increment nếu hợp đồng nghiệp vụ cần exactly-once-effect. Điều này không biến toàn bộ phương thức PATCH thành idempotent theo HTTP một cách tự động; nó làm **một operation cụ thể** an toàn hơn khi lặp.

## 10. Từ demo một JVM sang Spring MVC production

Demo dùng `synchronized` để minh họa cập nhật nguyên tử; triển khai production phải phối hợp storage, validation, authorization và event.

### 10.1. Cách dùng JPA @Version

Entity minh họa:

```java
@Entity
class DocumentEntity {
    @Id
    private Long id;

    @Version
    private long version;

    private String title;
    private String description;

    // Constructors, getters và setters được lược bỏ;
    // đây là đoạn minh họa không độc lập.
}
```

Trên GET, đọc version gắn với representation và tạo ETag. Trên PUT/PATCH, verify client If-Match khớp version và thực hiện thay đổi trong transaction. Hibernate/JPA optimistic locking sẽ kiểm tra version khi flush/commit; khi có `OptimisticLockException` hoặc `ObjectOptimisticLockingFailureException`, cần phản hồi phù hợp với hợp đồng (ví dụ 412 nếu điều kiện If-Match không còn hợp lệ, hoặc 409 trong xung đột khác). Việc map exception vào status cần dựa trên **nguyên nhân và ngữ nghĩa điều kiện**, không tự động xem mọi DB exception là 412.

### 10.2. Đồng nhất kiểm tra version và tác động phụ

Một quy trình production nên là:

```text
Authentication/Authorization
   → Xác định tài nguyên & permission
   → Parse và validate representation / patch document
   → Bắt đầu transaction
       → Đọc và khóa/CAS theo version
       → Đánh giá If-Match
       → Tạo trạng thái dự kiến
       → Validate bất biến toàn tài nguyên
       → Lưu state + version mới nếu thay đổi
       → Ghi outbox event trong cùng transaction nếu cần
   → Commit
   → Trả response / ETag (nếu thỏa HTTP spec)
   → Outbox publisher gửi event, consumer có deduplication
```

Với storage hỗ trợ compare-and-swap, có thể dùng ý tưởng:

```sql
UPDATE documents
SET title = :new_title,
    description = :new_description,
    version = version + 1
WHERE id = :id AND version = :expected_version;
```

Nếu số hàng cập nhật bằng 0, kiểm tra xem tài nguyên không còn tồn tại hay đã đổi version rồi trả 404/412 phù hợp. Đoạn SQL chỉ minh họa conditional update; để giữ **không tạo version mới nếu PUT cùng dữ liệu**, phải bổ sung bước so sánh trạng thái mong muốn với hiện tại dưới cùng cơ chế lock/CAS hoặc chọn chính sách version phù hợp và chứng minh retry không tạo nghiệp vụ lặp ngoài ý muốn.

### 10.3. Validation sau khi áp dụng patch

Đừng sửa entity đang được persistence context quản lý, flush sớm rồi mới kiểm tra một field khác trong patch. Một mẫu an toàn:

1. Phân tích patch vào cấu trúc **tạm**, kiểm tra field nào được phép và type/null rules.
2. Tạo **candidate copy** của trạng thái resource dựa trên phiên bản đã xác thực.
3. Áp dụng **toàn bộ** patch vào candidate.
4. Chạy Bean Validation + bất biến domain trên **candidate cuối cùng**.
5. Nếu hợp lệ, ghi toàn bộ thay đổi cùng transaction; nếu bất kỳ bước nào thất bại, rollback tất cả.
6. Không phát event hoặc thay trạng thái phụ khi transaction chưa commit thành công.

Với PATCH JSON Patch gồm nhiều operation, atomicity đặc biệt quan trọng: nếu operation thứ ba thất bại thì hai operation đầu **không** được tồn tại dưới dạng một phần cập nhật.

### 10.4. ETag phải mô tả representation nào?

ETag là validator của **representation**, không phải trường ngẫu nhiên trong DB. Nếu cùng resource có nhiều representation theo media type, ngôn ngữ hoặc encoding, cần cẩn thận về validators/variant handling. ETag không nên chỉ chứa số version DB nếu representation có thể thay đổi mà version ấy không tăng hoặc nếu cùng tag được gán cho các representation khác byte khác nhau và được coi là strong.

Trong demo, representation là hai field JSON trong một JVM, version tăng khi dữ liệu thay đổi; vì vậy ETag mô phỏng strong validator trong phạm vi cố định. Sản phẩm thực cần đảm bảo validator thực sự đúng với response GET, cập nhật khi có thay đổi ảnh hưởng representation và tuân HTTP preconditions.

## 11. Lỗi thiết kế thường gặp

| Sai lầm | Rủi ro | Cách xử lý |
| --- | --- | --- |
| Dùng PUT để merge những field có trong body mà không công bố | Client tưởng thay toàn bộ nhưng dữ liệu cũ vẫn tồn tại | Tách rõ full replacement và partial patch |
| Dùng PATCH nhưng không định nghĩa media type/semantics | Không biết null/omitted/array nghĩa gì | Chọn JSON Merge Patch, JSON Patch hoặc contract riêng |
| Cho rằng mọi PATCH không-idempotent | Bỏ lỡ cách update theo trạng thái mong muốn | Phân loại operation và bảo đảm hiệu ứng khi retry |
| Cho rằng mọi PATCH đều idempotent | Append/increment bị nhân đôi | Dùng precondition/idempotency key hoặc đổi mô hình |
| Chỉ thêm `synchronized` rồi deploy nhiều instance | Hai instance vẫn ghi đè lẫn nhau | DB transaction/version/CAS |
| Chỉ kiểm tra If-Match trước transaction | Race giữa kiểm tra và ghi | Conditional write nguyên tử |
| Trả 409 khi ETag đã sai | Client khó phân biệt HTTP precondition | Trả 412 khi If-Match thất bại |
| Bỏ If-Match khi retry bị 412 | Ghi đè thay đổi của người khác | GET, reconcile, gửi request mới có tag mới |
| Trả 428 khi tag có nhưng sai | Nhầm thiếu điều kiện với điều kiện thất bại | 428 thiếu, 412 mismatch |
| Dùng `If-Match: *` để chống lost update | Chỉ kiểm tra tài nguyên tồn tại | Sử dụng tag phiên bản mạnh cụ thể |
| PUT thiếu field vẫn giữ giá trị cũ mà không khai báo | Không thật sự full replacement | DTO PUT rõ contract và validate đầy đủ |
| JSON Merge Patch `null` nghĩa “lưu null” | Sai RFC 7396, có thể xóa ngoài ý muốn | Null là xóa field; nếu cần JSON null, chọn định dạng khác |
| JSON Patch `add /items/-` được retry mù | Append trùng phần tử | Dùng chống lặp hoặc element identity |
| PATCH áp dụng từng operation rồi return lỗi | Tài nguyên bị cập nhật dở | Transaction/rollback toàn bộ |
| Chỉ validate mỗi field trong patch | Bỏ lọt bất biến liên trường | Validate candidate sau merge |
| Đưa entity có `role`/`balance` vào binder | Mass assignment/escalation | DTO, allowlist, authorization |
| Trả ETag sau PUT mà request data bị biến đổi | Vi phạm điều kiện về validator trong HTTP | Chỉ phát validator khi đủ điều kiện, hoặc cho client GET lại |
| Retry tạo thêm event/email/payment | Trùng side effect nghiệp vụ | Outbox + dedup/idempotency key |
| Coi response 412 sau timeout là “chắc chắn chưa commit” | Người dùng thao tác lặp hoặc xung đột sai | GET trạng thái thực tế và reconcile |

## 12. Bài tập tự kiểm tra

1. **PUT** `{"title":"A","description":"B"}` hai lần vào cùng URL, không có cập nhật cạnh tranh. State cuối khác nhau không? **Không**; mục tiêu đều là A/B. Nếu dùng If-Match cũ lần hai có thể trả 412, nhưng không ghi đè.
2. **PUT** chỉ `{"title":"A"}` mà endpoint khai báo thay toàn bộ. Server có nên tự giữ `description` không? **Không mặc định**. Bỏ field nghĩa theo schema toàn representation hoặc lỗi nếu bắt buộc.
3. **PATCH Merge Patch** gửi `{"description":null}`. Có phải đặt description thành JSON null? **Không theo RFC 7396**; đó là yêu cầu xóa member.
4. **PATCH Merge Patch** gửi `{}`. Điều gì xảy ra? **Không yêu cầu thay đổi field nào**; state kết quả bằng trước (nếu input hợp lệ và server không thêm side effect nghiệp vụ).
5. **PATCH JSON Patch** `add` vào `/items/-` bị retry. Vấn đề? **Có thể append lần hai**, nên không được xem idempotent khi thiếu chống lặp.
6. Nếu Client A và B đều GET ETag `"v7"`, A cập nhật trước lên `"v8"`, B PUT cùng `If-Match: "v7"` thì sao? **412**, không ghi đè A.
7. Nếu API yêu cầu If-Match nhưng request PUT không có thì status? **428 Precondition Required** theo chính sách API.
8. Nếu request có If-Match nhưng không còn khớp thì status? **412 Precondition Failed**.
9. Gửi `If-Match: *` có chống được lost update không? **Không đủ**, vì chỉ kiểm tra tài nguyên tồn tại.
10. HTTP 204 có body JSON không? **Không**; nếu muốn gửi representation hãy dùng 200.
11. PUT tạo tài nguyên chưa tồn tại thành công cần status nào theo HTTP? **201 Created**.
12. Tại sao `PATCH` không bảo đảm an toàn đồng thời dù chỉ gửi một field? **Vì có thể đụng đúng field người khác sửa hoặc phụ thuộc base-state cũ**, nên vẫn cần concurrency control.
13. Một service gửi email mỗi khi xử lý PUT dù state không đổi. Có vấn đề gì? **Có**, về hiệu ứng nghiệp vụ khi retry; cần giới hạn email theo transition thực và dedup/outbox.
14. Có thể triển khai `synchronized` trên controller để tránh lost update trên 5 instance Spring Boot không? **Không**; lock đó chỉ nằm trong từng JVM.
15. Khi PATCH có 5 operation, operation cuối sai, 4 operation đầu đã commit có đúng RFC 5789 không? **Không**, patch phải atomic.
16. Nếu body PATCH là `application/json` nhưng server chỉ hỗ trợ `application/merge-patch+json`, status phù hợp? **415 Unsupported Media Type**.
17. Sau timeout, retry PUT bị 412. Có thể khẳng định lần đầu thất bại? **Không**; GET kiểm tra trạng thái hiện tại trước khi quyết định thao tác kế.
18. Nếu database lưu version=8 nhưng GET representation thay đổi từ nguồn phụ ngoài DB, strong ETag `"v8"` có còn đúng không? **Chưa chắc**; validator phải thay đổi theo representation thực tế.

## 13. Nguồn chính thức và tài liệu tham khảo

- [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110): ngữ nghĩa PUT, idempotency, status codes, ETag và điều kiện `If-Match`.
- [RFC 5789 — PATCH Method for HTTP](https://www.rfc-editor.org/rfc/rfc5789): ngữ nghĩa PATCH, atomicity, idempotency tùy thiết kế, `Accept-Patch`.
- [RFC 7396 — JSON Merge Patch](https://www.rfc-editor.org/rfc/rfc7396): cấu trúc JSON Merge Patch, absent/null, xử lý object và array.
- [RFC 6902 — JSON Patch](https://www.rfc-editor.org/rfc/rfc6902): `add`, `remove`, `replace`, `move`, `copy`, `test`.
- [RFC 6901 — JSON Pointer](https://www.rfc-editor.org/rfc/rfc6901): cú pháp path trong JSON Patch.
- [RFC 6585 — Additional HTTP Status Codes](https://www.rfc-editor.org/rfc/rfc6585): status 428 Precondition Required.
- [Spring Framework — Annotated Controllers](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods.html): `@PutMapping`, `@PatchMapping`, request mapping.
- [Spring Framework — HTTP Message Converters](https://docs.spring.io/spring-framework/reference/web/webmvc/message-converters.html): chọn converter theo `Content-Type`, binding JSON vào DTO.
- [Spring Data JPA — Locking](https://docs.spring.io/spring-data/jpa/reference/jpa/locking.html): cơ chế khóa ở persistence layer; kết hợp với version/transaction phù hợp.

**Ghi nhớ:** `PUT` diễn tả **trạng thái tài nguyên cần có sau cập nhật** và mang tính idempotent theo HTTP; `PATCH` diễn tả **thay đổi cần áp dụng**, có idempotent hay không phụ thuộc format và operation. **ETag/If-Match** ngăn ghi đè khi dùng dữ liệu cũ; **idempotency key/dedup** bảo vệ những hiệu ứng nghiệp vụ không được lặp. Kiểm chứng bằng trạng thái sau request và sau retry, không chỉ bằng một mã HTTP trả về.
