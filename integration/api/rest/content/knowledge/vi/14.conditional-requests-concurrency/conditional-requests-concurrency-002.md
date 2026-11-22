# ETag mạnh, ETag yếu và ngữ nghĩa so sánh

## 1. Tình huống: một mã phiên bản phục vụ hai nhu cầu khác nhau

Trong REST API, client thường cần trả lời hai câu hỏi:

1. **“Dữ liệu tôi đã lưu hoặc đã hiển thị còn giống biểu diễn hiện tại không?”** Đây là bài toán **tái xác thực cache**: nếu chưa đổi, không cần tải lại toàn bộ response.
2. **“Tôi có thể sửa tài nguyên dựa trên phiên bản tôi đã đọc mà không ghi đè thay đổi của người khác không?”** Đây là bài toán **đồng thời lạc quan (optimistic concurrency control)**: nếu tài nguyên đã đổi, thao tác ghi cần được từ chối hoặc giải quyết xung đột.

HTTP có cơ chế **conditional requests** dùng các header như `ETag`, `If-None-Match` và `If-Match` để giải quyết hai bài toán này. Nhưng chúng **không dùng cùng một quy tắc so sánh**. HTTP phân biệt **strong entity-tag** (ETag mạnh) và **weak entity-tag** (ETag yếu), cùng hai phép so sánh **strong comparison** và **weak comparison**.

Ví dụ, Alice và Bình cùng đọc một đơn hàng:

~~~mermaid
sequenceDiagram
    participant A as Alice
    participant API as Order API
    participant DB as Database
    participant B as Bình
    A->>API: GET /v1/orders/o-42
    API->>DB: Đọc đơn version 7
    DB-->>API: total=100, version=7
    API-->>A: 200 + ETag "order-v7"
    B->>API: PATCH Order với If-Match "order-v7"
    API->>DB: Cập nhật thành version 8
    API-->>B: 200 + ETag "order-v8"
    A->>API: PATCH Order với If-Match "order-v7"
    API-->>A: 412 Precondition Failed
~~~

Nếu API chấp nhận cập nhật của Alice mà không kiểm tra phiên bản, thao tác của Bình có thể bị **ghi đè mất (lost update)**. Với nội dung công khai, ngược lại, client có thể chỉ muốn hỏi “bài viết đã thay đổi đáng kể chưa?” để nhận **304 Not Modified** và tái dùng bản lưu.

Bài học thuộc chương **Điều kiện và đồng thời** của module **INTEGRATION_API_REST**: thiết kế REST API trên resource, URI, phương thức, mã trạng thái và hợp đồng rõ ràng; kết nối cache, idempotency, phân quyền, xử lý lỗi, OpenAPI và kiểm thử bằng **Java/Spring** hoặc nền tảng tương đương.

**Mục tiêu sau bài học:** đọc/ghi ETag đúng cú pháp; phân biệt mạnh/yếu và thuật toán so sánh; dùng `If-Match` cho ghi có điều kiện và `If-None-Match` cho cache; xử lý `If-Range`, `304`/`412`/`428`; thiết kế validator theo representation và biến thể; kiểm chứng bằng test thực tế.

> **Ghi nhớ:** ETag không phải khóa bảo mật, không phải bằng chứng đã phân quyền và cũng không tự động là version database. Nó là **validator của biểu diễn được chọn**, được server phát theo hợp đồng HTTP.

## 2. ETag là gì? Cú pháp và phạm vi

### 2.1. Entity-tag trong response

Một response GET có thể chứa:

~~~http
GET /v1/articles/java-rest HTTP/1.1
Host: api.example.com
Accept: application/json

HTTP/1.1 200 OK
Content-Type: application/json
ETag: "article-rev-17"
Cache-Control: public, max-age=60

{"slug":"java-rest","title":"Thiết kế REST API"}
~~~

Header `ETag` mang một **opaque tag** do server chọn. Client **không được tự diễn giải** ý nghĩa của chuỗi bên trong dấu nháy. Nó có thể là mã phiên bản, hash, ID phát hành hoặc token khác, miễn tuân thủ các nghĩa vụ validator mà server công bố.

Cú pháp minh họa:

~~~http
ETag: "v7"
ETag: "sha256-8dd1f3"
ETag: W/"article-semantic-rev-3"
~~~

Trong cú pháp HTTP:

- **Strong ETag**: `"v7"`, tức **không có** tiền tố yếu.
- **Weak ETag**: `W/"v7"`, dùng **`W/` viết hoa** trước phần entity-tag.
- Phần nằm trong dấu nháy kép là **opaque tag**, và **chỉ chuỗi này** là giá trị được so khớp; tiền tố `W/` quy định **độ mạnh validator**.
- Dấu nháy kép là **một phần cú pháp bắt buộc**, không phải trang trí. `ETag: v7` không phải cú pháp entity-tag hợp lệ.
- `ETag` không đồng nghĩa với `Last-Modified`; cả hai đều là validator nhưng có mức độ chính xác/semantics khác nhau.

**Không đặt** thông tin mật như access token, password, email hoặc internal ID dễ nhận diện vào entity-tag. Client và proxy có thể ghi lại header trong log; ETag được xem là metadata có thể quan sát.

### 2.2. Validator của representation, không đơn thuần của một row

Một URI có thể có nhiều **representation variant** theo `Accept`, `Accept-Language`, `Content-Encoding`, phiên bản API hoặc phạm vi quyền. Chẳng hạn:

~~~http
GET /v1/help/articles/intro
Accept-Language: vi

HTTP/1.1 200 OK
Content-Language: vi
Vary: Accept-Language
ETag: "intro-vi-r9"
~~~

~~~http
GET /v1/help/articles/intro
Accept-Language: en

HTTP/1.1 200 OK
Content-Language: en
Vary: Accept-Language
ETag: "intro-en-r9"
~~~

Hai biểu diễn này khác ngôn ngữ và thường khác bytes, vì vậy **không được gán cùng một strong validator** nếu nội dung biểu diễn khác theo cách một strong validator phải phát hiện. `Vary` giúp cache biết trường request nào tham gia lựa chọn representation. Phạm vi resource và representation được chọn cũng quyết định cách đánh giá precondition.

Một trường `@Version` trong entity là **nguồn dữ liệu hữu ích** để tạo ETag, nhưng không tự đảm bảo strong validator nếu DTO còn thay đổi do dữ liệu bên ngoài, serialization, link theo quyền hoặc mã hóa nội dung. Bài sẽ quay lại vấn đề này ở phần thiết kế.

## 3. Strong và weak validator khác nhau ở đâu?

### 3.1. Strong ETag

**Strong validator** có yêu cầu đủ chặt để server phân biệt những thay đổi dữ liệu biểu diễn có thể quan sát khi chuyển toàn bộ representation; theo ngữ nghĩa HTTP, nó phù hợp với các trường hợp cần chính xác, như **kiểm tra precondition khi ghi** và **ghép partial responses**.

Ví dụ server phát:

~~~http
ETag: "article-17"
~~~

Khi representation thay đổi theo cách làm dữ liệu của biểu diễn GET khác đi, validator mạnh phải được cập nhật. Một ETag mạnh **không nhất thiết là hash nội dung**: server có thể dùng token phiên bản, miễn bảo đảm không vô tình tái dùng tag cho hai biểu diễn khác nhau trong phạm vi so sánh liên quan.

### 3.2. Weak ETag

**Weak validator** cho phép server coi hai biểu diễn là **tương đương về ngữ nghĩa** cho mục đích cache, dù bytes không giống nhau. Ví dụ:

- HTML cùng bài viết nhưng whitespace hoặc nội dung trang trí thay đổi.
- Một danh sách có metadata phụ không làm thay đổi nội dung cốt lõi theo chính sách ứng dụng.
- Server không thể bảo đảm mức chính xác đủ cho strong validator nhưng vẫn muốn hỗ trợ revalidation.

Ví dụ:

~~~http
ETag: W/"article-semantic-17"
~~~

**Weak ETag không có nghĩa “không đáng tin” hay “bị sai”.** Nó thể hiện sự **nới lỏng định nghĩa tương đương**: phù hợp để quyết định có thể tái sử dụng representation cho nhiều trường hợp đọc/cache, nhưng **không đủ** làm validator strong cho `If-Match` hoặc `If-Range` entity-tag.

### 3.3. So sánh

| Tiêu chí | Strong ETag | Weak ETag |
|---|---|---|
| Cú pháp | `"v7"` | `W/"v7"` |
| Cam kết về thay đổi representation | Phải thay đổi khi dữ liệu representation thay đổi theo yêu cầu strong validator | Có thể giữ nguyên với các thay đổi được coi là tương đương về ngữ nghĩa |
| Tái xác thực GET qua `If-None-Match` | Có | Có |
| Cập nhật có điều kiện qua `If-Match` | Có thể khớp theo strong comparison | **Không** khớp strong comparison |
| Dùng làm entity-tag của `If-Range` | Hợp lệ khi là strong validator phù hợp | **Không được** gửi weak entity-tag làm If-Range |
| Dùng khi ghép các phần của representation | Thích hợp nếu các điều kiện khác đều đúng | Không đủ để xác nhận các phần bytes thuộc cùng representation |
| Ví dụ tạo | Version chặt của representation hoặc hash bytes theo biến thể | Version ngữ nghĩa không đổi khi những thay đổi được chấp nhận xảy ra |

**Không suy ra** “hash = strong, version = weak”: khả năng mạnh/yếu dựa vào **tính đúng của lời cam kết validator**, không dựa vào thuật toán tạo token.

## 4. Hai phép so sánh entity-tag

Ngữ nghĩa chuẩn ở **RFC 9110** có **strong comparison** và **weak comparison**. Đây là trọng tâm của bài.

### 4.1. Strong comparison

Hai entity-tag **khớp mạnh** chỉ khi:

1. **Cả hai đều không có** tiền tố `W/`.
2. Phần **opaque tag giống hệt nhau**, so khớp như byte sequence theo cú pháp HTTP.

Nếu một bên yếu, **strong comparison trả false**, ngay cả khi chuỗi bên trong dấu nháy giống nhau.

### 4.2. Weak comparison

Hai entity-tag **khớp yếu** khi phần **opaque tag giống nhau**, **bất kể** có hay không tiền tố `W/`. Nếu opaque tag khác nhau, không khớp.

### 4.3. Bảng chân trị

| Entity-tag phía request | ETag hiện tại | Strong comparison | Weak comparison |
|---|---|---|---|
| `"v7"` | `"v7"` | **Khớp** | **Khớp** |
| `W/"v7"` | `"v7"` | **Không** | **Khớp** |
| `"v7"` | `W/"v7"` | **Không** | **Khớp** |
| `W/"v7"` | `W/"v7"` | **Không** | **Khớp** |
| `"v7"` | `"v8"` | **Không** | **Không** |
| `W/"v7"` | `W/"v8"` | **Không** | **Không** |

**Từ khóa quyết định không phải GET hay PUT, mà là header điều kiện nào được dùng.** `If-Match` dùng strong comparison; `If-None-Match` dùng weak comparison. `If-Range` với entity-tag cần strong validator và so sánh mạnh.

### 4.4. Ví dụ phản trực giác

Giả sử:

~~~http
ETag: "order-v7"
~~~

Client gửi:

~~~http
If-None-Match: W/"order-v7"
~~~

Điều kiện `If-None-Match` **khớp**, vì dùng **weak comparison**. Với GET hoặc HEAD phù hợp, server có thể trả **304 Not Modified**.

Nhưng nếu client gửi:

~~~http
If-Match: W/"order-v7"
~~~

Điều kiện `If-Match` **không khớp**, dù ETag hiện tại là `"order-v7"`. Với thao tác PATCH/PUT thông thường, server **không được xử lý cập nhật như thể điều kiện đạt**; thông thường phản hồi **412 Precondition Failed**, trừ những trường hợp ngoại lệ được chuẩn cho phép như server xác định thao tác yêu cầu đã được thực hiện.

### 4.5. Opaque tag và danh sách

Các trường `If-Match` và `If-None-Match` có thể chứa **danh sách entity-tag** hoặc giá trị đặc biệt `*`. Client không được tự cắt chuỗi theo ý nghĩa phiên bản, ví dụ so “v7 lớn hơn v6”; server cũng không được dùng `String.contains("v7")` để xác định khớp.

Ví dụ:

~~~http
If-None-Match: "v4", W/"v5", "v7"
If-Match: "v6", "v7"
If-None-Match: *
If-Match: *
~~~

Trong danh sách, điều kiện đạt nếu **ít nhất một thành viên phù hợp** theo phép so sánh của header đó. Dấu `*` không mang nghĩa “bất kỳ chuỗi version nào”; nó **kiểm tra có/không có representation hiện tại của resource đích** theo semantics riêng, sẽ trình bày ở phần tạo resource.

## 5. If-None-Match: tái xác thực cache và câu trả lời 304

`If-None-Match` nói: **“Chỉ xử lý như thường lệ nếu representation hiện tại không khớp với những tag tôi nêu.”** Server đánh giá điều kiện bằng **weak comparison**. Vì vậy strong và weak ETag có cùng opaque tag đều có thể giúp xác định nội dung trong cache **chưa cần tải lại**.

### 5.1. Conditional GET với strong ETag

Lần đầu, client tải tài liệu:

~~~http
GET /v1/help/articles/rest HTTP/1.1
Accept: application/json

HTTP/1.1 200 OK
Content-Type: application/json
ETag: "rest-article-v12"
Cache-Control: public, max-age=60

{"slug":"rest","title":"HTTP và REST","body":"..."}
~~~

Khi dữ liệu cache đã hết thời gian fresh hoặc client cần tái xác thực:

~~~http
GET /v1/help/articles/rest HTTP/1.1
If-None-Match: "rest-article-v12"

HTTP/1.1 304 Not Modified
ETag: "rest-article-v12"
Cache-Control: public, max-age=60
~~~

**304 không có response body** chứa JSON tài liệu. Client/cache tái sử dụng representation đã lưu và cập nhật metadata phù hợp từ response 304. Không viết body kiểu `{"status":"not_modified"}` dưới 304.

### 5.2. Conditional GET với weak ETag

Server phát:

~~~http
ETag: W/"rest-semantic-v12"
~~~

Client tái xác thực:

~~~http
GET /v1/help/articles/rest HTTP/1.1
If-None-Match: W/"rest-semantic-v12"
~~~

Nếu server đánh giá biểu diễn hiện tại vẫn tương đương theo validator yếu, nó trả **304**, ngay cả khi thay đổi không trọng yếu về bytes. Điều này hợp lý khi cache không cần tải lại representation chỉ vì biến đổi mà phía server đánh giá là tương đương về ngữ nghĩa.

**Cần cân nhắc tác động nghiệp vụ:** nếu UI phụ thuộc một trường mà server lại xem thay đổi của trường đó là “không đáng kể”, weak ETag có thể khiến người dùng giữ bản cũ không phù hợp. Mức độ yếu phải được xác định từ **cách client tiêu thụ representation**, không chỉ để giảm số lần phát ETag.

### 5.3. If-None-Match không khớp

Nếu current ETag đổi thành `"rest-article-v13"` mà client vẫn gửi `If-None-Match: "rest-article-v12"`, điều kiện **đạt** (không có match). Với GET thông thường server trả **200 OK** cùng representation và ETag mới:

~~~http
HTTP/1.1 200 OK
ETag: "rest-article-v13"
Content-Type: application/json

{"slug":"rest","title":"HTTP và REST","body":"Bản cập nhật"}
~~~

### 5.4. GET/HEAD và phương thức khác

Khi `If-None-Match` **khớp**:

- Với **GET hoặc HEAD**, kết quả điều kiện thường là **304 Not Modified**.
- Với **phương thức khác GET/HEAD** như PUT, POST hoặc PATCH, kết quả thông thường là **412 Precondition Failed** nếu một representation hiện tại khớp; điều kiện được sử dụng theo semantics của resource đích.

Khi không khớp, request có thể được xử lý **nếu các điều kiện khác** và quyền/trạng thái đều hợp lệ. Nói cách khác, `If-None-Match` không biến GET thành thao tác ghi hay bảo đảm response thành công; nó chỉ là một precondition.

### 5.5. Khi nào 304 thật sự tiết kiệm?

304 giúp giảm byte truyền representation và thường giảm công việc tuần tự hóa hoặc tạo body. Tuy nhiên server vẫn cần đủ thông tin để xác định **representation đã chọn, quyền truy cập và validator hiện tại**. Một truy vấn DB hoặc kiểm tra permission có thể vẫn cần thiết; ETag không khiến mọi conditional GET có chi phí bằng 0.

Nếu cache đã **fresh** theo `Cache-Control: max-age` và chính sách cache cho phép, client/cache có thể tái sử dụng mà không gửi request. Khi cần revalidation, nó gửi validator; **max-age** và ETag giải quyết **hai khía cạnh khác nhau** của caching: thời gian được dùng trực tiếp và cách xác minh sau đó.

## 6. If-Match: điều kiện ghi và kiểm soát lost update

`If-Match` nói: **“Chỉ thực hiện request nếu representation hiện tại khớp mạnh với ít nhất một validator tôi nêu.”** Nó dùng **strong comparison** vì thao tác ghi phải dựa trên trạng thái chính xác mà client kỳ vọng, không dựa vào tương đương ngữ nghĩa mơ hồ.

### 6.1. Cập nhật có điều kiện

Client đọc đơn:

~~~http
GET /v1/orders/o-42 HTTP/1.1
Authorization: Bearer <access-token>

HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: no-store
ETag: "order-o42-v7"

{
  "id": "o-42",
  "status": "DRAFT",
  "note": "Giao buổi sáng",
  "version": 7
}
~~~

Sau đó muốn sửa ghi chú:

~~~http
PATCH /v1/orders/o-42 HTTP/1.1
Authorization: Bearer <access-token>
Content-Type: application/merge-patch+json
If-Match: "order-o42-v7"

{"note":"Giao buổi chiều"}

HTTP/1.1 200 OK
Content-Type: application/json
ETag: "order-o42-v8"
Cache-Control: no-store

{
  "id":"o-42",
  "status":"DRAFT",
  "note":"Giao buổi chiều",
  "version":8
}
~~~

Điều kiện là **ETag hiện tại của chính URI /v1/orders/o-42** vẫn tương đương mạnh với tag client cung cấp. Nếu một người khác đã thay note hoặc trạng thái khiến ETag thành `"order-o42-v8"`, request với `If-Match: "order-o42-v7"` thông thường bị từ chối:

~~~http
HTTP/1.1 412 Precondition Failed
Content-Type: application/problem+json
Cache-Control: no-store

{
  "type":"https://api.example.com/problems/precondition-failed",
  "title":"Precondition Failed",
  "status":412,
  "detail":"Tài nguyên đã thay đổi; hãy tải lại trước khi cập nhật."
}
~~~

**Không được âm thầm ghi đè thay đổi mới** chỉ để trả 200. Client nên GET lại representation mới, xem khác biệt và quyết định có gửi PATCH với validator mới hay không.

### 6.2. Weak ETag không thay strong precondition

Nếu server trả `ETag: W/"order-o42-v7"`, client **không thể biến nó thành validator phù hợp cho `If-Match` chỉ bằng cách copy**. Khi dùng strong comparison, weak tag không khớp ngay cả với cùng opaque tag. API muốn hỗ trợ optimistic concurrency bằng `If-Match` phải phát **strong validator** đáp ứng tiêu chuẩn, thay vì bắt client tự bỏ tiền tố `W/`.

### 6.3. 412 khác 409 và 428

| Mã | Khi nào dùng | Ví dụ |
|---|---|---|
| **412 Precondition Failed** | Header điều kiện HTTP được gửi nhưng điều kiện không đạt | `If-Match` khác strong ETag hiện tại |
| **428 Precondition Required** | API yêu cầu client gửi điều kiện mà request không có | PATCH thiếu `If-Match` trong API có chính sách bắt buộc precondition |
| **409 Conflict** | Thao tác xung đột với trạng thái hoặc bất biến nghiệp vụ | Order đã PAID, không cho sửa note; hạ OWNER cuối cùng |
| **400 Bad Request** | Request/header sai cú pháp theo hợp đồng | Header If-Match bị malformed hoặc JSON sai cú pháp |
| **403 Forbidden** | Principal hiểu resource nhưng không có quyền thao tác | Người xem chỉ có quyền GET, không có quyền PATCH |
| **404 Not Found** | Resource không có hoặc không được phép tiết lộ | Order thuộc tenant khác theo chính sách ẩn |

**Có thể có nhiều điều kiện cùng thất bại**, chẳng hạn người gọi không có quyền, If-Match cũ và trạng thái Order đã PAID. API phải có **thứ tự kiểm tra an toàn**: không tiết lộ thông tin về tài nguyên bị cấm bằng 412/409; các HTTP precondition được đánh giá sau khi request đủ điều kiện xử lý theo ngữ nghĩa và chính sách máy chủ. Đối với resource đã được phép truy cập, trả 412 cho điều kiện HTTP thất bại thay vì âm thầm chạy phần ghi.

### 6.4. Cần khóa hoặc CAS ở thời điểm ghi, không chỉ kiểm tra ETag rồi ghi

Một lỗi triển khai hay gặp:

~~~text
SELECT version FROM orders WHERE id = :id;   # thấy v7
if request If-Match == "v7":
    UPDATE orders SET note = :newNote;        # không kiểm tra version!
~~~

Giữa SELECT và UPDATE, một transaction khác có thể sửa version thành v8. Vì thế, phải kết hợp **conditional HTTP** với **kiểm soát ghi nguyên tử ở database**, chẳng hạn:

~~~sql
UPDATE orders
SET note = :note,
    version = version + 1
WHERE id = :id
  AND tenant_id = :authenticatedTenantId
  AND version = :expectedVersion
  AND status = 'DRAFT';
~~~

Nếu số hàng cập nhật là **1**, thao tác CAS (*compare-and-swap*) thành công. Nếu **0**, cần tra cứu trong cùng phạm vi quyền để phân biệt resource không nhìn thấy, precondition sai và trạng thái nghiệp vụ không cho phép. Với bất biến liên quan **nhiều hàng**, chẳng hạn tổng đơn hàng hoặc OWNER cuối cùng, kiểm tra riêng version một row có thể chưa đủ; cần transaction/lock đúng **ranh giới aggregate**.

### 6.5. Nếu dữ liệu thay đổi mà version không đổi?

Một field trong response được tính từ bảng khác hoặc từ chính sách quyền có thể thay đổi mà version của `orders` không tăng. Khi đó ETag `"order-o42-v7"` không còn đại diện mạnh cho **toàn bộ representation**. Để giữ validator đúng, hãy thiết kế token phản ánh đủ mọi thay đổi có thể quan sát, hoặc tách subresource/representation có vòng đời riêng, hoặc tính hash trên representation đúng biến thể.

Không được tuyên bố một ETag là strong chỉ vì có ký tự `v7` không có `W/`; **server phải thực sự duy trì invariant của strong validator**.

## 7. If-None-Match: * và If-Match: *

Dấu sao `*` là trường hợp đặc biệt, không phải một entity-tag được trích dẫn.

### 7.1. Tạo resource chỉ khi chưa tồn tại

Một client muốn tạo resource tại URI xác định mà **không ghi đè** resource đang có:

~~~http
PUT /v1/users/u-123/preferences HTTP/1.1
Authorization: Bearer <access-token>
Content-Type: application/json
If-None-Match: *

{"theme":"dark"}
~~~

Nếu chưa có representation hiện tại ở target URI, điều kiện đạt; nếu PUT được phép tạo resource thì server có thể trả:

~~~http
HTTP/1.1 201 Created
Location: /v1/users/u-123/preferences
ETag: "preferences-v1"
~~~

Nếu đã có representation hiện tại, `If-None-Match: *` không đạt, nên với PUT thông thường server trả **412 Precondition Failed**. Cơ chế này là một cách biểu diễn **create-if-absent** theo semantics HTTP.

**Lưu ý:** “không có representation hiện tại” không nhất thiết đồng nghĩa “không có row trong DB” — resource có thể bị ẩn, đã xóa mềm hoặc URL bị giữ lại theo chính sách. Vẫn phải kiểm tra quyền tạo resource và quy tắc tái sử dụng URI. Để bảo đảm hai yêu cầu tạo đồng thời không cùng thành công, cần **unique constraint/transaction** ở backend.

### 7.2. If-Match: * yêu cầu resource đang tồn tại

~~~http
DELETE /v1/users/u-123/preferences HTTP/1.1
If-Match: *
Authorization: Bearer <access-token>
~~~

Điều kiện `If-Match: *` đạt nếu server có biểu diễn hiện tại của resource đích. Nó hữu ích cho thao tác **chỉ khi tồn tại**; tuy nhiên **không phát hiện ai đã thay đổi nội dung kể từ lần đọc**. Vì vậy `If-Match: *` **không thay thế** một strong ETag cụ thể như `If-Match: "preferences-v4"` khi cần chống lost update.

Một API đặt yêu cầu “phải có **validator phiên bản cụ thể**” cần mô tả rõ rằng wildcard không đáp ứng chính sách chống lost update của sản phẩm, dù wildcard vẫn là cú pháp HTTP hợp lệ. Không diễn giải `*` thành strong entity-tag thông thường.

### 7.3. So sánh hai wildcard

| Header | Khi resource hiện có representation | Khi không có representation |
|---|---|---|
| `If-Match: *` | Điều kiện đạt | Điều kiện không đạt |
| `If-None-Match: *` | Điều kiện không đạt | Điều kiện đạt |

Ví dụ với GET, `If-None-Match: *` khi representation tồn tại thường dẫn tới **304**, còn với PUT sẽ dẫn tới **412** khi điều kiện không đạt. Cùng một header nhưng mã phản hồi phụ thuộc phương thức HTTP theo quy tắc chuẩn.

## 8. If-Range và tải từng phần: vì sao weak ETag không đủ?

Một client tải file lớn có thể ngừng giữa chừng rồi yêu cầu **Range** để lấy tiếp phần còn thiếu. Nếu file đã thay đổi, ghép phần cũ và phần mới sẽ tạo nội dung bị hỏng. Header `If-Range` giúp server quyết định chỉ gửi một phần khi representation vẫn phù hợp.

### 8.1. Khi ETag mạnh vẫn khớp

Client đã tải 1.000 byte đầu của một file có ETag `"file-a-v8"` và muốn tải từ byte 1000 trở đi:

~~~http
GET /v1/files/f-9/content HTTP/1.1
Range: bytes=1000-
If-Range: "file-a-v8"
~~~

Nếu validator mạnh vẫn phù hợp và Range có thể thỏa, server có thể trả:

~~~http
HTTP/1.1 206 Partial Content
ETag: "file-a-v8"
Content-Range: bytes 1000-4999/5000
Content-Length: 4000
Content-Type: application/octet-stream

<4000 byte dữ liệu>
~~~

Nếu file đã đổi ETag, `If-Range` không đạt và server **bỏ qua Range**, gửi lại representation toàn phần với **200 OK** (giả định GET đủ điều kiện và tài nguyên hiện có). Không dùng 412 cho thất bại `If-Range` thông thường. Nếu Range được áp dụng nhưng không thể thỏa, **416 Range Not Satisfiable** có thể phù hợp theo ngữ nghĩa Range.

### 8.2. Weak ETag không được dùng làm If-Range

`If-Range` với entity-tag cần **strong validator**. Client **không được gửi** `If-Range: W/"file-a-v8"`. Lý do: hai biểu diễn “tương đương ngữ nghĩa” có thể khác bytes; ghép nhiều phần byte đòi sự nhất quán mạnh hơn revalidation thông thường.

Nếu server không có strong validator cho file, client có thể tải lại toàn phần hoặc dùng một cơ chế hợp lệ khác được đặc tả HTTP hỗ trợ. `If-Range` cũng có dạng **HTTP-date**, nhưng điều kiện date cần đáp ứng yêu cầu strong validator; không dùng tùy tiện mốc `Last-Modified` độ phân giải một giây nếu nó không đủ mạnh cho trường hợp đó.

### 8.3. Ranh giới resource quan trọng

Tải `/v1/files/f-9/content` khác với GET metadata tại `/v1/files/f-9`. ETag của **metadata JSON** không mặc định là ETag mạnh của **byte stream file**. Nếu hai resource có cách thay đổi khác nhau, hãy phát validator riêng và chỉ dùng `If-Range` từ representation **đúng content URI** đã được đọc trước đó.

## 9. Thứ tự đánh giá điều kiện HTTP và mối quan hệ với Last-Modified

Một request có thể chứa nhiều header điều kiện. Server không được kiểm tra tùy hứng khiến cùng request cho kết quả trái semantics. **RFC 9110, mục 13.2** định nghĩa thứ tự đánh giá trong những trường hợp cần thiết.

| Header | Phép so sánh/chỉ tiêu | Mục đích chủ yếu |
|---|---|---|
| `If-Match` | **Strong** entity-tag comparison, hoặc wildcard | Chỉ ghi khi representation kỳ vọng còn phù hợp |
| `If-Unmodified-Since` | So thời điểm sửa đổi theo ngữ nghĩa HTTP-date | Ghi có điều kiện dựa trên thời gian khi không có If-Match |
| `If-None-Match` | **Weak** entity-tag comparison, hoặc wildcard | Revalidation cache, create-if-absent |
| `If-Modified-Since` | So HTTP-date cho GET/HEAD | Revalidation theo thời điểm khi không có If-None-Match |
| `If-Range` | Strong validator hoặc date đủ điều kiện | Gửi Range nếu representation chưa đổi phù hợp |

### 9.1. Quan hệ ưu tiên cơ bản

- Nếu request đã có **`If-Match`**, `If-Unmodified-Since` không được dùng để thay thế điều kiện entity-tag của nó.
- Nếu request đã có **`If-None-Match`**, `If-Modified-Since` được bỏ qua theo quy tắc của HTTP; ETag thường là validator chính xác hơn thời điểm sửa đổi.
- `If-Range` liên quan đến **Range** và xử lý sau các điều kiện thích hợp khác; nó không phải bản sao của `If-Match`.
- Việc một precondition khớp **không tự cấp quyền** hoặc biến một method không hợp lệ thành hợp lệ.

### 9.2. Vì sao thời gian sửa đổi có thể yếu hơn ETag?

`Last-Modified` thường có độ phân giải theo **giây** trong HTTP-date. Nếu resource bị sửa **hai lần trong cùng giây**, chỉ dựa vào thời gian có thể không phát hiện bản ghi mới. Với optimistic concurrency cần độ chính xác cao, strong ETag dựa trên version/representation đáng tin thường phù hợp hơn.

Một thời điểm sửa đổi có thể là strong validator trong một số điều kiện được chuẩn cho phép, nhưng **không được mặc định** rằng mọi timestamp đều mạnh. Quy tắc về khoảng thời gian và độ chính xác có thể khác theo nguồn đồng hồ, server, nguồn dữ liệu và yêu cầu sử dụng.

### 9.3. HEAD và các response không có body

`HEAD` mang cùng tinh thần lấy metadata của GET nhưng **không có response body**. Client có thể dùng `If-None-Match` trong HEAD; khi điều kiện phù hợp có thể nhận 304. HTTP API vẫn phải kiểm tra quyền đọc của resource trước khi để ETag hoặc trạng thái trở thành đường vòng tiết lộ sự tồn tại.

## 10. Sinh và duy trì validator đúng ở server

### 10.1. Phương án strong ETag từ version nghiệp vụ

Nếu response JSON chỉ phụ thuộc **Order entity và các field có version**, server có thể tạo tag:

~~~text
Order(id=o-42, version=7)
   -> ETag: "order-o42-json-v7"

Sau transaction thay note/quantity/status:
Order(id=o-42, version=8)
   -> ETag: "order-o42-json-v8"
~~~

Điều kiện để tag này **thật sự mạnh**:

- Mọi cập nhật làm thay đổi dữ liệu representation có thể quan sát đều dẫn đến token mới.
- Không có đường cập nhật bỏ qua tăng version, kể cả migration, batch SQL hoặc tác vụ worker.
- Những dữ liệu từ quan hệ khác, giá tính toán, link theo quyền hoặc schema/serializer thay đổi phải được phản ánh trong chiến lược validator.
- Các representation variant không bị dùng chung strong tag sai khi bytes/dữ liệu representation khác nhau.
- Không tạo vòng quay version có thể tái sử dụng cùng tag cho trạng thái khác trong phạm vi liên quan.

Đối với response có link hypermedia phụ thuộc quyền, một Order version đơn thuần **có thể không đủ**: manager và owner cùng thấy Order version 7 nhưng action khác. Cần tính validator cho **representation thực tế** hoặc chọn chiến lược không dùng conditional cache cho variant động ấy.

### 10.2. Phương án strong ETag từ nội dung

Một cách khác là hash representation đã được tạo ổn định, ví dụ:

~~~text
strongTag = SHA-256(bytes-of-selected-representation)
ETag = quote(encode(strongTag))
~~~

Hash mạnh có thể thuận tiện cho object bất biến hoặc nội dung được cache. Tuy nhiên:

- **Chi phí:** phải đọc/render nội dung hoặc dùng hash đã lưu; với file lớn có thể tốn I/O/CPU.
- **Biến thể:** dữ liệu được mã hóa gzip và identity là các representation khác, cần xử lý strong validators tương ứng.
- **Serialization:** thứ tự field, whitespace, timestamp được format, schema, locale, permission links có thể làm bytes đổi.
- **Collision/security:** dùng thuật toán đủ mạnh, và không coi hash là authorization hoặc chữ ký số.

Không bắt buộc mọi strong ETag phải là SHA-256; thuật toán hash là **lựa chọn triển khai**, còn nghĩa vụ strong validator là **hợp đồng HTTP**.

### 10.3. Khi nào weak ETag là lựa chọn đúng?

Với trang công khai có nội dung chính không đổi nhưng phần trình bày thay đổi, server có thể phát:

~~~http
ETag: W/"help-article-semantic-v5"
~~~

Nếu ứng dụng chủ động coi whitespace hoặc vài chi tiết trình bày là tương đương, nó có thể không đổi weak tag. Nhưng phải kiểm tra **người tiêu dùng representation** thực sự chấp nhận tương đương đó. API trả biểu đồ, số tiền, điều khoản pháp lý hay thông báo bảo mật có thể không thể coi những thay đổi tưởng “nhỏ” là không có ý nghĩa.

### 10.4. Content-Encoding tạo ra biến thể quan trọng

Ví dụ cùng một tài liệu được phục vụ bằng **identity** và **gzip**:

~~~http
HTTP/1.1 200 OK
Content-Encoding: gzip
Vary: Accept-Encoding
ETag: "article-gzip-v9"
~~~

~~~http
HTTP/1.1 200 OK
Vary: Accept-Encoding
ETag: "article-identity-v9"
~~~

**Không dùng cùng strong ETag cho hai dạng dữ liệu biểu diễn khác bytes** khi strong validator phải phân biệt chúng để bảo vệ tính toàn vẹn Range/cache. Nếu chính sách coi hai dạng là tương đương về ngữ nghĩa, weak validators có thể chia sẻ opaque tag phù hợp. Cần tính đến proxy/CDN có thể nén hoặc biến đổi response, làm thay đổi dữ liệu trên đường đi.

Tương tự, các biến thể `Accept-Language`, `Accept`, serializer version và các field theo principal cần được xem xét khi phát validator. `Vary` nói cho cache biết những header nào tham gia chọn representation; nó **không tự sửa ETag sinh sai**.

### 10.5. Những lỗi phát ETag cần tránh

| Sai lầm | Vì sao không ổn | Hướng xử lý |
|---|---|---|
| Phát `ETag: W/"v7"` nhưng dùng `If-Match` để chống lost update | Weak không khớp trong strong comparison | Phát strong validator đúng hoặc chọn cơ chế khác |
| Chỉ hash ID resource | Nội dung có thể đổi mà ETag không đổi | Phản ánh version/dữ liệu representation |
| Tính tag từ `updatedAt` làm tròn đến giây | Hai cập nhật trong một giây có thể nhận cùng tag | Version nguyên tử hoặc strong representation hash |
| Bỏ qua relation/permission field trong token | Representation đổi nhưng strong ETag không đổi | Tính theo variant và những dữ liệu được hiển thị |
| Dùng ETag metadata cho bytes file | Ghép Range có thể không nhất quán | Validator riêng của content representation |
| Cấp cùng strong ETag cho gzip và identity khác bytes | Không bảo đảm byte identity | Variant-specific strong tag hoặc weak khi phù hợp |
| Đưa giá trị bí mật/PII vào opaque tag | Metadata bị lộ qua response/log | Token mờ không chứa dữ liệu nhạy cảm |
| Nghĩ `@Version` tự xử lý mọi race | Aggregate có thể gồm nhiều row và side effect | CAS/transaction đúng phạm vi, kiểm soát invariant |
| Nghĩ ETag thay thế unique constraint | Hai client có thể tạo cùng resource mới | Unique constraint và transaction cho create-if-absent |

## 11. Cache, bảo mật và phạm vi tenant

### 11.1. Conditional GET không bỏ qua authorization

Một client có thể gửi ETag lấy từ tài khoản khác. Server không được trả **304** để xác nhận tài nguyên ngoài phạm vi người gọi. Phải xác thực, xác định resource/representation **được phép xem**, rồi mới xét precondition phù hợp.

Ví dụ:

~~~text
GET /v1/orders/o-42
Authorization: Bearer <token-cua-tenant-b>
If-None-Match: "order-o42-v7"
~~~

Nếu Order chỉ thuộc tenant-a và bị ẩn đối với tenant-b, API theo chính sách của bài trả **404 Not Found** trung tính. Không được tiết lộ “tag của bạn đã đúng” qua 304 hoặc ETag response.

### 11.2. Cache-Control phải khớp loại dữ liệu

| Resource | Chính sách gợi ý | Ghi chú |
|---|---|---|
| Bài viết công khai, có ETag | `Cache-Control: public, max-age=60` (ví dụ) | Dùng cache khi fresh, revalidate qua If-None-Match |
| Dữ liệu cá nhân nhạy cảm | `Cache-Control: no-store` | Tránh lưu thông tin vào cache; ETag vẫn có thể dùng như token precondition cho thao tác ghi |
| Dữ liệu riêng tư chấp nhận client-side cache | `Cache-Control: private, no-cache` | Cache riêng có thể lưu nhưng phải revalidate trước khi dùng |
| Trang thay đổi theo ngôn ngữ | `Vary: Accept-Language` và validator theo representation | Tránh tái dùng bản tiếng Anh cho client tiếng Việt |
| Nội dung có gzip/identity | `Vary: Accept-Encoding` và validator phù hợp | Tránh trộn các variant hoặc ghép Range sai |

**no-cache không có nghĩa không được lưu**: nó yêu cầu tái xác thực thành công trước khi dùng bản lưu. **no-store** là chỉ thị không lưu response theo chính sách cache. Với dữ liệu cần bảo vệ cao, no-store thường dễ dự đoán hơn.

### 11.3. ETag và quyền có thể thay đổi độc lập

Nếu representation trả về theo role, một thay đổi quyền có thể thay đổi link/action trong body dù Order không bị sửa. Strong ETag phải phản ánh representation mới; khi principal khác nhau, shared cache không được dùng nhầm biến thể.

`Vary: Authorization` một mình không thể thay thế thiết kế cache riêng tư: hệ thống CDN có cách cấu hình cache key và credential khác nhau. Trước khi bật shared caching cho dữ liệu phụ thuộc principal, phải xác minh đầy đủ cách tách user/tenant/quyền, invalidate khi role đổi và bảo vệ metadata.

### 11.4. ETag có phải token theo dõi người dùng?

Vì ETag có thể tồn tại lâu trong cache, triển khai không cẩn thận có thể biến nó thành **định danh theo dõi** giữa các request. Tránh sinh ETag riêng bền vững theo người dùng cho nội dung công khai chung khi không cần; không dùng ETag làm session ID. Đặt chính sách cache, TTL và privacy phù hợp, nhất là khi phục vụ qua miền hoặc ứng dụng nhạy cảm.

## 12. Java/Spring: triển khai GET có điều kiện

Ví dụ sử dụng **Java 17+, Spring Boot 3, Spring MVC**. Các đoạn mã minh họa ranh giới trách nhiệm; cần bổ sung import, entity/repository, lớp service, cấu hình bảo mật và các exception ứng dụng để chạy thành dự án hoàn chỉnh.

### 12.1. Hàm so sánh ETag theo đúng ngữ nghĩa

Đầu tiên hãy tách **giải mã header** khỏi **quy tắc so sánh**:

~~~java
record EntityTag(boolean weak, String opaque) {}

final class EntityTagComparison {
    private EntityTagComparison() {}

    static boolean strongEquals(EntityTag a, EntityTag b) {
        return !a.weak() && !b.weak()
            && a.opaque().equals(b.opaque());
    }

    static boolean weakEquals(EntityTag a, EntityTag b) {
        return a.opaque().equals(b.opaque());
    }
}
~~~

Hai hàm trên thể hiện **thuật toán so sánh sau khi đã parse thành công**. Không đưa nguyên header `W/"v7"` hay danh sách `"v5", "v7"` vào `opaque()`; parser phải tách phần `W/`, dấu nháy và thành viên danh sách theo cú pháp HTTP.

Một dịch vụ có thể cung cấp:

~~~java
interface HttpEntityTagConditions {
    // Đúng semantics If-None-Match: danh sách + wildcard + weak comparison.
    boolean ifNoneMatchMatches(
        String rawHeader,
        String currentEntityTag,
        boolean representationExists
    );

    // Đúng semantics If-Match: danh sách + wildcard + strong comparison.
    boolean ifMatchMatches(
        String rawHeader,
        String currentEntityTag,
        boolean representationExists
    );
}
~~~

Đây là **interface minh họa cho bộ xử lý header tuân thủ RFC**, không phải một class sẵn có trong Spring. Khi triển khai, ưu tiên dùng cơ chế HTTP conditional request do framework hỗ trợ và đã kiểm thử; nếu tự viết, phải parse đúng cú pháp dấu nháy, danh sách, wildcard và strong/weak. **Không dùng `split(",")` thô** vì opaque tag hợp lệ có thể chứa dấu phẩy bên trong chuỗi trích dẫn, và không dùng `String.contains` để so khớp validator.

### 12.2. Public GET với weak ETag

Giả sử một bài viết công khai có `semanticRevision`; backend chủ động coi những thay đổi trình bày không đáng kể là tương đương:

~~~java
@RestController
@RequestMapping("/v1/help/articles")
class PublicArticleController {
    private final ArticleService articles;
    private final HttpEntityTagConditions conditions;

    PublicArticleController(
            ArticleService articles,
            HttpEntityTagConditions conditions) {
        this.articles = articles;
        this.conditions = conditions;
    }

    @GetMapping("/{slug}")
    ResponseEntity<ArticleDto> get(
            @PathVariable String slug,
            @RequestHeader(
                value = HttpHeaders.IF_NONE_MATCH,
                required = false
            ) String ifNoneMatch) {

        ArticleDto article = articles.findPublished(slug);
        String weakTag = "W/\"article-semantic-v"
            + article.semanticRevision() + "\"";
        CacheControl cache = CacheControl
            .maxAge(Duration.ofSeconds(60)).cachePublic();

        if (ifNoneMatch != null
                && conditions.ifNoneMatchMatches(
                    ifNoneMatch, weakTag, true
                )) {
            return ResponseEntity
                .status(HttpStatus.NOT_MODIFIED)
                .header(HttpHeaders.ETAG, weakTag)
                .cacheControl(cache)
                .build();
        }

        return ResponseEntity.ok()
            .header(HttpHeaders.ETAG, weakTag)
            .cacheControl(cache)
            .body(article);
    }
}
~~~

**`ArticleService.findPublished`** phải xác nhận tài liệu được phép công khai trước khi phát ETag. Ví dụ **không hỗ trợ** `Accept-Language` hoặc variant khác; nếu có, phải thêm `Vary` và validator tương ứng. Nếu server hỗ trợ `If-Modified-Since` và các precondition khác, dùng bộ xử lý conditional requests chuẩn để tránh thực hiện thứ tự đánh giá sai.

Spring MVC có các cơ chế hỗ trợ conditional request, chẳng hạn `WebRequest.checkNotModified(...)` trong ngữ cảnh phù hợp. Cần kiểm chứng chính xác behavior của framework/phiên bản triển khai, nhất là với response có content negotiation và cache header. Đoạn mã tự viết trên cố ý chỉ minh họa **If-None-Match**, không tuyên bố là HTTP precondition processor hoàn chỉnh.

### 12.3. Response 304 cần có những header nào?

Khi trả 304, server nên đưa những metadata cần thiết như `Date`, `ETag`, `Cache-Control`, `Expires`, `Vary` hoặc `Content-Location` **nếu chúng thuộc những header tương ứng cần xuất hiện theo quy tắc 304 và 200**. Không gửi body của representation; không đặt `Content-Length` một cách tùy ý gây mâu thuẫn với nội dung không được truyền.

Ví dụ với phiên bản tiếng Việt:

~~~http
HTTP/1.1 304 Not Modified
ETag: "help-vi-v9"
Cache-Control: public, max-age=60
Vary: Accept-Language
~~~

Cache sẽ dùng cả thông tin `Vary` và khóa cache của request tương ứng để tái sử dụng đúng biến thể. Nếu resource phụ thuộc quyền, việc xác thực và chọn representation theo principal phải hoàn tất **trước** khi cân nhắc trả 304.

## 13. Java/Spring: PATCH có If-Match và CAS trong transaction

Ví dụ tiếp theo dùng **Order** có `@Version` và endpoint PATCH chỉ sửa field `note`. Để minh họa logic chính, giả định response Order chỉ chứa các field được bao phủ bởi version và cùng một representation JSON ổn định. Với biểu diễn phụ thuộc ngôn ngữ, quyền hoặc nguồn dữ liệu khác, phải thiết kế validator mở rộng.

### 13.1. Entity và repository

~~~java
@Entity
@Table(name = "orders")
class OrderEntity {
    @Id
    private UUID id;

    @Column(nullable = false)
    private UUID tenantId;

    @Column(nullable = false)
    private String status;

    private String note;

    @Version
    private long version;

    // Getters/setters cần bổ sung theo dự án.
}
~~~

~~~java
interface OrderRepository extends JpaRepository<OrderEntity, UUID> {
    @Lock(LockModeType.PESSIMISTIC_WRITE)
    @Query("""
        select o from OrderEntity o
        where o.id = :id and o.tenantId = :tenantId
        """)
    Optional<OrderEntity> findForUpdate(
        @Param("id") UUID id,
        @Param("tenantId") UUID tenantId
    );
}
~~~

Ví dụ dùng **pessimistic lock** khi thực hiện PATCH, cùng `@Version` để quản lý revision. Một phương án khác là optimistic-only `@Version` và xử lý xung đột lúc flush hoặc `UPDATE ... WHERE version = expected`. **Không nhất thiết vừa dùng cả hai cơ chế** trong mọi ứng dụng; chọn theo tải, mức tranh chấp và ranh giới consistency.

### 13.2. Service kiểm tra quyền, trạng thái và validator

~~~java
record OrderUpdate(
    OrderDto value,
    String strongEtag
) {}

@Service
class OrderCommandService {
    private final OrderRepository repository;
    private final HttpEntityTagConditions conditions;
    private final EntityManager em;

    OrderCommandService(
            OrderRepository repository,
            HttpEntityTagConditions conditions,
            EntityManager em) {
        this.repository = repository;
        this.conditions = conditions;
        this.em = em;
    }

    @Transactional
    OrderUpdate changeNote(
            UUID orderId,
            Actor actor,
            String ifMatch,
            String newNote) {

        UUID tenantId = actor.validatedTenantId();
        OrderEntity order = repository
            .findForUpdate(orderId, tenantId)
            .orElseThrow(HiddenNotFoundException::new);

        requireCanUpdate(actor, order); // 403 nếu thiếu quyền

        if (ifMatch == null) {
            throw new PreconditionRequiredException(); // 428
        }
        String currentTag = strongOrderTag(order);
        if (!conditions.ifMatchMatches(ifMatch, currentTag, true)) {
            throw new PreconditionFailedException(); // 412
        }
        if (!"DRAFT".equals(order.getStatus())) {
            throw new OrderStateConflictException(); // 409
        }

        order.setNote(newNote);
        em.flush(); // Đảm bảo @Version đã được cập nhật ở DB.

        return new OrderUpdate(
            toDto(order),
            strongOrderTag(order)
        );
    }

    private String strongOrderTag(OrderEntity order) {
        return "\"order-" + order.getId()
            + "-json-v" + order.getVersion() + "\"";
    }
}
~~~

Các thành phần `Actor`, `requireCanUpdate`, `toDto` và exception là thành phần giả định. `validatedTenantId` phải lấy từ identity đã được kiểm chứng; không được tin tenant do client tự đặt. Dùng `flush()` để cập nhật version trước khi tạo ETag; transaction vẫn cần commit thành công trước khi HTTP response được coi là kết quả cuối.

**Giới hạn của ví dụ:** nếu một thao tác khác sửa representation mà không làm tăng `@Version` của Order, validator trên không còn mạnh. Ngoài ra nếu policy yêu cầu **strong validator cụ thể**, wildcard `If-Match: *` không đủ chống lost update dù nó hợp lệ theo HTTP; phải công bố chính sách riêng và xử lý rõ. `HttpEntityTagConditions` là tầng xử lý RFC chưa được hiện thực trong code này; triển khai production cần library/logic đã kiểm thử toàn bộ grammar.

### 13.3. Controller giữ đúng HTTP status và header

~~~java
@RestController
@RequestMapping("/v1/orders")
class OrderCommandController {
    private final OrderCommandService commands;
    private final ActorFactory actors;

    OrderCommandController(
            OrderCommandService commands,
            ActorFactory actors) {
        this.commands = commands;
        this.actors = actors;
    }

    @PatchMapping(
        path = "/{id}",
        consumes = MediaType.APPLICATION_JSON_VALUE
    )
    ResponseEntity<OrderDto> changeNote(
            @PathVariable UUID id,
            @RequestHeader(
                value = HttpHeaders.IF_MATCH,
                required = false
            ) String ifMatch,
            @Valid @RequestBody ChangeOrderNoteRequest request,
            @AuthenticationPrincipal Jwt jwt) {

        Actor actor = actors.fromVerifiedJwt(jwt);
        OrderUpdate result = commands.changeNote(
            id, actor, ifMatch, request.note()
        );

        return ResponseEntity.ok()
            .header(HttpHeaders.ETAG, result.strongEtag())
            .cacheControl(CacheControl.noStore())
            .body(result.value());
    }
}
~~~

Ở đây PATCH sử dụng **`application/json` với DTO riêng** (`ChangeOrderNoteRequest`), không tự tuyên bố hỗ trợ JSON Merge Patch. Nếu dùng `application/merge-patch+json`, phải áp dụng đúng semantics null/xóa field của RFC 7396. API có thể trả **204 No Content** nếu không trả representation, nhưng khi đó vẫn có thể kèm ETag mới và không có body.

### 13.4. Map lỗi sang Problem Details

~~~java
@RestControllerAdvice
class ConditionalRequestProblemHandler {
    @ExceptionHandler(PreconditionRequiredException.class)
    ResponseEntity<ProblemDetail> missingPrecondition() {
        return problem(
            HttpStatus.PRECONDITION_REQUIRED,
            "Cần gửi If-Match hợp lệ."
        );
    }

    @ExceptionHandler(PreconditionFailedException.class)
    ResponseEntity<ProblemDetail> stalePrecondition() {
        return problem(
            HttpStatus.PRECONDITION_FAILED,
            "Phiên bản tài nguyên đã thay đổi."
        );
    }

    @ExceptionHandler(OrderStateConflictException.class)
    ResponseEntity<ProblemDetail> conflict() {
        return problem(
            HttpStatus.CONFLICT,
            "Trạng thái đơn không cho phép cập nhật."
        );
    }

    private ResponseEntity<ProblemDetail> problem(
            HttpStatus status, String message) {
        ProblemDetail detail =
            ProblemDetail.forStatusAndDetail(status, message);
        return ResponseEntity.status(status)
            .cacheControl(CacheControl.noStore())
            .body(detail);
    }
}
~~~

Body mặc định của `ProblemDetail` theo **RFC 9457** sử dụng `application/problem+json` khi được Spring MVC cấu hình hỗ trợ phù hợp. Nên bổ sung `type` và `code` ổn định để client phân biệt các loại lỗi mà không parse chuỗi tiếng Việt. Không trả SQL, version của tenant khác hoặc thông tin tài nguyên bị ẩn trong response công khai.

## 14. Tương quan với idempotency, retry và phương thức HTTP

ETag giải quyết **điều kiện trên representation hiện tại**, còn **Idempotency-Key** thường giải quyết câu hỏi **“đây có phải chính ý định nghiệp vụ tôi đã gửi trước đó không?”**. Chúng liên quan nhưng **không thay thế nhau**.

### 14.1. Khi response PATCH bị mất

Giả sử client gửi:

~~~http
PATCH /v1/orders/o-42
If-Match: "order-o42-v7"
{"note":"Giao chiều"}
~~~

Server áp dụng thành công, tăng version lên v8, nhưng response bị mất. Client retry cùng PATCH với `If-Match: "order-o42-v7"`. Điều kiện hiện tại **không khớp**, và client có thể nhận **412**. Đây **không nhất thiết là lỗi nghiệp vụ**: thao tác đầu tiên có thể đã thành công.

Client cần **GET lại trạng thái**, kiểm tra note đã thay đổi đúng chưa, hoặc dựa vào operation ID/idempotency key nếu hợp đồng hỗ trợ để truy vấn kết quả cũ. Không tự bỏ `If-Match` rồi gửi lại PATCH vì như vậy có thể ghi đè thay đổi của người khác.

### 14.2. POST có side effect

POST tạo thanh toán, phê duyệt hoặc đơn mới không tự có khả năng retry an toàn chỉ nhờ ETag của resource liên quan. Nếu cần chống lặp, dùng **Idempotency-Key** theo scope principal/tenant/operation, lưu fingerprint request và kết quả bền vững. Kết hợp transactional outbox, unique constraint và đối soát khi có phụ thuộc bên ngoài.

### 14.3. PUT và DELETE idempotent vẫn có thể trả 412

PUT và DELETE là các phương thức **idempotent theo hiệu ứng dự kiến**, nhưng một request có precondition cũ vẫn có thể thất bại với 412 sau khi resource đổi. **Idempotence không hứa mỗi lần gọi sẽ có cùng response status**. Với DELETE, nếu request đầu đã xóa resource và response mất, retry với `If-Match` cũ thường không đạt; client có thể tra cứu kết quả và đối chiếu hợp đồng xóa.

### 14.4. 304 không dùng để báo ghi thành công

**304** dùng cho conditional GET/HEAD khi representation không cần truyền lại. Với PUT/PATCH/DELETE, precondition thất bại thường phản hồi **412**, không phải 304. Không trả HTTP 200 cùng JSON `{"status":304}` thay cho trạng thái HTTP thật.

## 15. Mô tả hợp đồng trong OpenAPI 3.1

OpenAPI giúp client biết **header nào cần gửi, loại representation nào có validator và các mã lỗi có thể xảy ra**. Nó không tự thực thi điều kiện tại database; phần server vẫn phải tuân thủ semantics HTTP.

### 15.1. Ví dụ OpenAPI rút gọn

~~~yaml
openapi: 3.1.0
info:
  title: Conditional Orders API
  version: 1.0.0
paths:
  /v1/orders/{orderId}:
    parameters:
      - name: orderId
        in: path
        required: true
        schema:
          type: string
          format: uuid
    get:
      operationId: getOrder
      summary: Đọc đơn và strong ETag của representation
      security:
        - bearerAuth: []
      parameters:
        - name: If-None-Match
          in: header
          required: false
          description: >
            Danh sách entity-tag để revalidation bằng weak comparison.
            Khi có match trên GET, có thể trả 304 không body.
          schema:
            type: string
      responses:
        "200":
          description: Order representation hiện tại
          headers:
            ETag:
              description: Strong validator cho representation được chọn
              schema:
                type: string
                example: '"order-o42-json-v7"'
            Cache-Control:
              schema:
                type: string
                example: no-store
          content:
            application/json:
              schema:
                $ref: "#/components/schemas/Order"
        "304":
          description: Biểu diễn chưa đổi theo If-None-Match, không có body
          headers:
            ETag:
              schema:
                type: string
        "401":
          description: Thiếu hoặc không có xác thực hợp lệ
          headers:
            WWW-Authenticate:
              schema:
                type: string
        "404":
          description: Order không tồn tại hoặc không được phép tiết lộ
          content:
            application/problem+json:
              schema:
                $ref: "#/components/schemas/Problem"
    patch:
      operationId: changeOrderNote
      summary: Đổi ghi chú dựa trên strong ETag đã đọc
      security:
        - bearerAuth: []
      parameters:
        - name: If-Match
          in: header
          required: true
          description: >
            Strong entity-tag cụ thể của representation Order.
            API yêu cầu version token cụ thể để chống lost update.
          schema:
            type: string
            example: '"order-o42-json-v7"'
      requestBody:
        required: true
        content:
          application/json:
            schema:
              type: object
              additionalProperties: false
              required: [note]
              properties:
                note:
                  type: string
                  maxLength: 500
      responses:
        "200":
          description: Đã cập nhật; trả ETag mới
          headers:
            ETag:
              schema:
                type: string
          content:
            application/json:
              schema:
                $ref: "#/components/schemas/Order"
        "400":
          description: Payload/header sai cú pháp
          content:
            application/problem+json:
              schema:
                $ref: "#/components/schemas/Problem"
        "401":
          description: Xác thực không hợp lệ
        "403":
          description: Không có quyền cập nhật đơn
        "404":
          description: Order không có hoặc không được phép tiết lộ
        "409":
          description: Trạng thái Order không cho phép chỉnh sửa
        "412":
          description: If-Match không khớp strong validator hiện tại
          content:
            application/problem+json:
              schema:
                $ref: "#/components/schemas/Problem"
        "428":
          description: Thiếu precondition If-Match bắt buộc
components:
  securitySchemes:
    bearerAuth:
      type: http
      scheme: bearer
      bearerFormat: JWT
  schemas:
    Order:
      type: object
      required: [id, status, version]
      properties:
        id:
          type: string
          format: uuid
        status:
          type: string
          enum: [DRAFT, PAID, CANCELLED]
        note:
          type:
            - string
            - "null"
        version:
          type: integer
          format: int64
    Problem:
      type: object
      required: [type, title, status]
      properties:
        type:
          type: string
          format: uri-reference
        title:
          type: string
        status:
          type: integer
        detail:
          type: string
        code:
          type: string
~~~

Trong ví dụ, `orderId` theo UUID để minh họa triển khai thật; `o-42` ở phần giải thích là ID ngắn giả lập và **không phải UUID hợp lệ**. Khi dùng mã nguồn demo, cần seed dữ liệu với UUID thật hoặc đổi schema/DTO cho khớp ID được chọn.

### 15.2. Những điều OpenAPI cần nói thêm bằng prose

- **ETag trả về là strong hay weak**, phạm vi biến thể representation nào.
- Khi nào GET có thể trả 304 và những header liên quan cache, `Vary`.
- PATCH có yêu cầu `If-Match` không; **wildcard** có đáp ứng chính sách chống lost update của sản phẩm hay không.
- Phân biệt **412 khi precondition sai**, **428 khi thiếu điều kiện**, **409 khi trạng thái nghiệp vụ xung đột**.
- Chính sách bảo mật: người khác tenant có thể nhận 404 trung tính dù gửi ETag đúng.
- Quy tắc xử lý **timeout sau commit**: client đọc lại trạng thái hoặc dùng idempotency key/operation resource theo hợp đồng.
- Những điều kiện tạo resource với `If-None-Match: *` nếu API còn hỗ trợ PUT create-only.

**OpenAPI khai báo `required: true` cho If-Match** không tự khiến Spring hoặc database thực thi precondition. Cần code xử lý header, so khớp strong và cập nhật nguyên tử; test cả trường hợp thiếu và sai.

## 16. Kiểm thử HTTP và đồng thời

### 16.1. Ma trận test ETag

| Test | ETag hiện tại / input | Kỳ vọng |
|---|---|---|
| E01 | GET lần đầu, resource có dữ liệu | **200**, ETag đúng cú pháp |
| E02 | GET `If-None-Match: "v7"`, current `"v7"` | **304**, không body |
| E03 | GET `If-None-Match: W/"v7"`, current `"v7"` | **304**, vì weak comparison khớp |
| E04 | GET `If-None-Match: "v7"`, current `W/"v7"` | **304**, vì weak comparison khớp |
| E05 | GET `If-None-Match: "v6"`, current `"v7"` | **200** và representation hiện tại |
| E06 | HEAD `If-None-Match` phù hợp | **304** hoặc status theo precondition, **không body** |
| E07 | PATCH `If-Match: "v7"`, current `"v7"`, đủ quyền | Cập nhật thành công, ETag mới |
| E08 | PATCH `If-Match: W/"v7"`, current `"v7"` | **412**, weak tag không khớp mạnh |
| E09 | PATCH `If-Match: "v6"`, current `"v7"` | **412**, DB không đổi |
| E10 | PATCH không gửi If-Match, API yêu cầu header | **428** |
| E11 | PUT `If-None-Match: *` khi URI chưa tồn tại | **201** nếu tạo thành công |
| E12 | PUT `If-None-Match: *` khi resource hiện có | **412**, không ghi đè |
| E13 | DELETE `If-Match: *` khi resource hiện có | Điều kiện đạt; method và quyền quyết định kết quả |
| E14 | DELETE `If-Match: *` khi resource không có | Điều kiện không đạt theo semantics HTTP phù hợp |
| E15 | GET Range + If-Range strong tag khớp | **206** nếu Range hợp lệ và server hỗ trợ |
| E16 | GET Range + If-Range strong tag khác | **200 toàn phần** thông thường |
| E17 | Không gửi If-Range weak tag | Client tuân thủ quy tắc; server được kiểm tra nếu nhận header không hợp lệ |
| E18 | Hai ETag có cùng opaque, một yếu, một mạnh | Strong **không**, weak **có** |
| E19 | ETag list chứa một match | Header có kết quả theo đúng strong/weak algorithm |
| E20 | ETag list có dấu phẩy bên trong opaque tag | Parser không cắt nhầm |
| E21 | Strong tag của gzip và identity cho bytes khác nhau | Không dùng nhầm validator; `Vary` thích hợp |
| E22 | Principal thay đổi, Order version không đổi nhưng body/action đổi | Không trả nhầm 304 hoặc phục vụ cache của người khác |
| E23 | Tenant B gửi validator của tenant A | Không lộ Order A qua 304/ETag |
| E24 | Two writers cùng dùng v7 | Tối đa một cập nhật đạt điều kiện; kết quả DB nhất quán |
| E25 | PATCH đã commit nhưng response mất, client retry v7 | Client xử lý 412/đọc lại; không ghi đè để “thành công giả” |

**Không chỉ test response code.** Cần kiểm tra **ETag mới, body/absence-of-body, trạng thái database, số lần side effect, quyền tenant và điều kiện không bị ghi đè**.

### 16.2. MockMvc kiểm tra GET có điều kiện

Ví dụ giả định fixture có bài viết công khai ở `semanticRevision=7` và controller xử lý đúng `If-None-Match`:

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class ArticleConditionalGetTest {
    @Autowired MockMvc mvc;

    @Test
    void weakIfNoneMatchCanMatchWeakCurrentTag() throws Exception {
        mvc.perform(get("/v1/help/articles/{slug}", "etag-guide")
                .header(HttpHeaders.IF_NONE_MATCH,
                    "W/\"article-semantic-v7\""))
            .andExpect(status().isNotModified())
            .andExpect(header().string(
                HttpHeaders.ETAG,
                "W/\"article-semantic-v7\""))
            .andExpect(content().string(""));
    }

    @Test
    void strongRequestTagAlsoWeakMatchesWeakCurrentTag()
            throws Exception {
        mvc.perform(get("/v1/help/articles/{slug}", "etag-guide")
                .header(HttpHeaders.IF_NONE_MATCH,
                    "\"article-semantic-v7\""))
            .andExpect(status().isNotModified())
            .andExpect(content().string(""));
    }

    @Test
    void differentIfNoneMatchReturnsNewRepresentation()
            throws Exception {
        mvc.perform(get("/v1/help/articles/{slug}", "etag-guide")
                .header(HttpHeaders.IF_NONE_MATCH,
                    "\"article-semantic-v6\""))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.semanticRevision").value(7));
    }
}
~~~

Đoạn test cần import JUnit, Spring Test/MockMvc, header matcher và fixture, và giả định DTO công khai trả `semanticRevision` như đã test. Trong môi trường production, server có thể không công khai revision đó trong body; khi ấy test nên kiểm tra ETag và dữ liệu đại diện phù hợp.

### 16.3. MockMvc kiểm tra ghi có điều kiện

Giả sử test fixture tạo Order có UUID thật, owner đúng tenant và version 7:

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class OrderConditionalWriteTest {
    @Autowired MockMvc mvc;

    UUID orderId;
    String currentStrongTag;

    @Test
    void weakIfMatchDoesNotAllowUpdate() throws Exception {
        String weak = "W/" + currentStrongTag;
        mvc.perform(
                patch("/v1/orders/{id}", orderId)
                    .with(jwt().jwt(
                        j -> j.claim("tenant_id", "tenant-a")
                    ))
                    .header(HttpHeaders.IF_MATCH, weak)
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("{\"note\":\"Giao trưa\"}")
            )
            .andExpect(status().isPreconditionFailed());

        // Sau test, xác minh DB vẫn giữ phiên bản và note cũ.
    }

    @Test
    void missingIfMatchIsRejected() throws Exception {
        mvc.perform(
                patch("/v1/orders/{id}", orderId)
                    .with(jwt().jwt(
                        j -> j.claim("tenant_id", "tenant-a")
                    ))
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("{\"note\":\"Giao trưa\"}")
            )
            .andExpect(status().isPreconditionRequired());
    }

    @Test
    void staleStrongIfMatchIsRejected() throws Exception {
        mvc.perform(
                patch("/v1/orders/{id}", orderId)
                    .with(jwt().jwt(
                        j -> j.claim("tenant_id", "tenant-a")
                    ))
                    .header(HttpHeaders.IF_MATCH,
                        "\"order-" + orderId + "-json-v6\"")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("{\"note\":\"Giao trưa\"}")
            )
            .andExpect(status().isPreconditionFailed());
    }
}
~~~

`jwt()` của `spring-security-test` có thể dựng principal giả lập **không xác minh chữ ký/issuer/audience token thật**. Fixture phải cấp quyền sửa Order cho actor; nếu actor không có quyền thì 403 có thể xuất hiện **trước khi kiểm tra If-Match**, làm test 412/428 không đo được điều cần kiểm. Cần test bảo mật tích hợp riêng cho credential không hợp lệ, tenant khác và token hết hạn.

### 16.4. Test concurrency trên database thực

Một test tuần tự “PATCH v7 xong, PATCH v7 tiếp nhận 412” chỉ chứng minh kiểm tra phiên bản sau khi một transaction kết thúc. Để phát hiện **lost update race**, cần:

1. Seed Order v7 và hai actor có quyền sửa.
2. Khởi chạy **hai request/transaction gần đồng thời** cùng `If-Match: "order-v7"`, dùng barrier hoặc transaction harness để tăng khả năng đụng nhau.
3. Xác nhận không có cả hai cập nhật được commit như thể đều nhìn v7; transaction CAS/lock/`@Version` phải giải quyết cạnh tranh.
4. Kiểm tra phiên bản cuối, dữ liệu ghi, rollback và audit/outbox không bị lặp sai.
5. Lặp test trên **database engine giống production**; in-memory database có isolation/locking khác.

Nếu server dùng JDBC, hãy test affected row count của `UPDATE ... WHERE version=:expected`. Nếu dùng JPA, hãy test behavior tại `flush/commit` và cách map stale update thành lỗi thích hợp **khi client có precondition**.

### 16.5. Test thuộc tính so sánh

Với các giá trị opaque ngẫu nhiên và hai cờ weak/strong, kiểm tra các bất biến:

~~~text
strongEquals(a, b) chỉ true khi:
  !a.weak && !b.weak && a.opaque == b.opaque

weakEquals(a, b) true khi:
  a.opaque == b.opaque

strongEquals(a, b) => weakEquals(a, b)
weakEquals(a, b) KHÔNG suy ra strongEquals(a, b)
~~~

Thêm test parser cho danh sách entity-tag, dấu nháy, wildcard, header sai cú pháp và opaque tag chứa dấu phẩy. Đừng viết test dựa trên việc tách header bằng dấu phẩy đơn giản rồi vô tình xác nhận chính một lỗi parser.

## 17. Bài tập thực hành và đáp án tham khảo

### Bài tập A — Strong hay weak comparison?

Cho entity-tag hiện tại của resource là `"order-v9"`. Hãy xác định những request sau có **match** hay không, và HTTP status dự kiến nếu các điều kiện khác (quyền, body, method) đều hợp lệ:

| Yêu cầu | Kết quả mong đợi? |
|---|---|
| GET với `If-None-Match: "order-v9"` | ? |
| GET với `If-None-Match: W/"order-v9"` | ? |
| GET với `If-None-Match: "order-v8"` | ? |
| PATCH với `If-Match: "order-v9"` | ? |
| PATCH với `If-Match: W/"order-v9"` | ? |
| PATCH với `If-Match: "order-v8"` | ? |
| PATCH với `If-Match: *` | ? |
| PUT với `If-None-Match: *` | ? |

**Đáp án:**

| Yêu cầu | So khớp | Kết quả dự kiến |
|---|---|---|
| GET + `If-None-Match: "order-v9"` | Weak comparison **match** | **304**, không body |
| GET + `If-None-Match: W/"order-v9"` | Weak comparison **match** | **304**, không body |
| GET + `If-None-Match: "order-v8"` | **Không match** | **200** với representation hiện tại |
| PATCH + `If-Match: "order-v9"` | Strong comparison **match** | Có thể cập nhật, trả **200/204** theo hợp đồng |
| PATCH + `If-Match: W/"order-v9"` | Strong comparison **không match** | **412** thông thường |
| PATCH + `If-Match: "order-v8"` | **Không match** | **412** thông thường |
| PATCH + `If-Match: *` | Resource tồn tại, **điều kiện đạt** | Có thể cập nhật theo HTTP; **không chống lost update** bằng version cụ thể |
| PUT + `If-None-Match: *` | Resource tồn tại, **điều kiện không đạt** | **412** thông thường |

**Giải thích:** `If-None-Match` dùng weak comparison nên weak và strong tag cùng opaque đều khớp. `If-Match` dùng strong comparison nên weak tag không bao giờ khớp. Wildcard kiểm tra tình trạng tồn tại, không so phiên bản. Khi dùng trong API có chính sách cụ thể về strong version, cần xử lý/ghi rõ trường hợp wildcard riêng.

### Bài tập B — Giao dịch đồng thời và response bị mất

Giả sử Order v12 có `note="Giao sáng"`. Hai client A và B cùng GET:

~~~text
T1: A GET -> 200, ETag "order-v12", note="Giao sáng"
T2: B GET -> 200, ETag "order-v12", note="Giao sáng"
T3: A PATCH If-Match "order-v12" -> thay note="Giao chiều"
T4: A commit thành version 13, nhưng response bị mất
T5: B PATCH If-Match "order-v12" -> muốn note="Giao tối"
T6: A retry request cũ với If-Match "order-v12"
~~~

Hỏi:

1. Tại T5 và T6, server nên làm gì?
2. A có thể kết luận PATCH T3 thất bại chỉ vì retry T6 nhận 412 không?
3. Nếu `note` là một phần của dữ liệu được dùng trong xuất hóa đơn, có nên tự động retry không precondition?

**Lời giải:** T5 và T6 thường bị **412** vì current strong ETag đã là v13. A **không thể** suy ra T3 thất bại; thao tác có thể đã commit trước khi mất response. A cần GET lại, xác nhận trạng thái hoặc dùng operation/idempotency key nếu hợp đồng có; B cũng cần GET lại và giải quyết xung đột. Không bỏ If-Match chỉ để retry “cho thành công”: nó có thể ghi đè một thay đổi hợp lệ, đặc biệt nguy hiểm với dữ liệu ảnh hưởng hóa đơn.

### Bài tập C — Validator của một JSON theo quyền

Một API trả:

~~~text
GET /v1/orders/o-7 của owner:
  body: {"status":"SUBMITTED","availableActions":["cancel"]}
  ETag: "order-v3"

GET /v1/orders/o-7 của manager:
  body: {"status":"SUBMITTED","availableActions":["approve"]}
  ETag: "order-v3"
~~~

**Câu hỏi:** nếu ETag được quảng bá là strong, thiết kế này ổn chưa? Cache cần làm gì?

**Lời giải:** hai representation **khác nội dung** nhưng dùng cùng strong validator chỉ từ version Order là không phù hợp nếu hệ thống dựa vào validator đó để phân biệt representation. Nên tạo validator phù hợp cho biến thể theo quyền và các thành phần ảnh hưởng body, hoặc không dùng shared/conditional caching cho dạng representation này. Phải tách quyền/tenant, cache key và `Cache-Control`; 304 không được tái dùng action cũ của principal khác. Phân quyền tại endpoint command vẫn bắt buộc.

### Bài tập D — Gzip và tải tiếp file

Server phục vụ cùng tài liệu dưới hai dạng:

~~~text
identity bytes: 5000 byte
gzip bytes:     1700 byte
ETag cho cả hai: "doc-v4"
~~~

Client đã tải phần đầu identity và muốn dùng `Range` + `If-Range`. Vấn đề có thể xảy ra là gì?

**Lời giải:** cùng strong tag cho hai biểu diễn có bytes khác nhau gây nguy cơ dùng sai phần dữ liệu khi xử lý byte-range/caching, không phù hợp với tính chính xác của strong validator theo representation. Cần strong ETag riêng cho identity/gzip và `Vary: Accept-Encoding`, hoặc chính sách variant hợp lệ khác; `If-Range` phải dùng strong validator của **representation đang được tải**. Weak ETag chỉ phù hợp với những tình huống revalidation tương đương ngữ nghĩa, **không dùng cho If-Range entity-tag**.

### Bài tập E — Tạo tài nguyên chỉ khi chưa tồn tại

Thiết kế PUT `/v1/users/u-77/preferences` chỉ để **tạo lần đầu**, không ghi đè preference hiện tại. Hai client gửi cùng lúc:

~~~http
PUT /v1/users/u-77/preferences
If-None-Match: *
Content-Type: application/json

{"theme":"dark"}
~~~

Hỏi:

1. Điều kiện `If-None-Match: *` có ý nghĩa gì?
2. Chỉ kiểm tra tồn tại trước INSERT bằng một SELECT rời rạc đã đủ chưa?
3. Nếu đã có preference, mã nào phù hợp?

**Lời giải:** precondition cho phép thao tác khi URI **chưa có representation hiện tại**. Hai request đồng thời có thể cùng thấy “chưa có” trước khi ghi, nên cần **unique constraint + transaction** hoặc cơ chế tạo nguyên tử trong storage. Nếu representation đã tồn tại, PUT với điều kiện không đạt thông thường trả **412 Precondition Failed**, không tự sửa dữ liệu cũ. Vẫn phải kiểm tra chủ sở hữu/tenant và chính sách tạo.

### Bài tập F — Cài đặt thuật toán so sánh

Hãy viết hai hàm `strongEquals(a,b)` và `weakEquals(a,b)` sau khi parse một entity-tag thành cặp `(isWeak, opaqueTag)`. Cần chứng minh:

1. Nếu hai tag **khớp mạnh** thì nhất định **khớp yếu**.
2. Hai tag **khớp yếu** chưa chắc **khớp mạnh**.
3. `W/"x"` và `"x"` khớp yếu nhưng không khớp mạnh.

**Lời giải:** tham khảo `EntityTagComparison` ở Mục 12. Strong yêu cầu cả hai không yếu và opaque bằng nhau; weak chỉ yêu cầu opaque bằng nhau. Không được làm sạch tiền tố `W/` một cách vô điều kiện **trước mọi phép so sánh** vì như vậy sẽ đánh mất thông tin strength.

## 18. Phản mẫu cần tránh và checklist triển khai

### 18.1. Các phản mẫu phổ biến

| Phản mẫu | Hậu quả | Biện pháp |
|---|---|---|
| Gọi mọi ETag là “version” mà không phân biệt mạnh/yếu | Client dùng weak tag cho If-Match và luôn gặp lỗi | Document strength và dùng đúng conditional header |
| Coi `W/"v7"` và `"v7"` khớp nhau trong `If-Match` | Phá semantics strong comparison | Weak tag luôn không khớp `If-Match` |
| Coi `W/"v7"` và `"v7"` khác nhau trong `If-None-Match` | Không tận dụng 304 khi representation tương đương | Weak comparison trên opaque tag |
| Dùng `If-Match: *` để “chống mất cập nhật” | Chỉ kiểm tra resource tồn tại, không kiểm tra phiên bản | Yêu cầu strong entity-tag cụ thể khi cần OCC |
| Dùng weak ETag cho `If-Range` | Có thể ghép bytes khác phiên bản | Strong validator đúng content representation |
| Parse tag bằng so chuỗi thô hoặc split dấu phẩy | Sai danh sách/opaque tag hợp lệ | Parser theo grammar HTTP |
| Tạo strong ETag bằng timestamp độ phân giải thấp | Hai update có thể tái dùng cùng tag | Version CAS hoặc hash representation đúng |
| Hash ID thay vì body/version | Tag không đổi dù nội dung đổi | Validator phản ánh dữ liệu biểu diễn thực |
| Kiểm tra If-Match ở controller rồi UPDATE không điều kiện | Race vẫn gây lost update | CAS/`@Version`/lock trong transaction |
| Dùng một strong ETag cho nhiều representation khác bytes | 304/cache/Range có thể sai | Variant-specific validator và `Vary` |
| Dùng ETag JSON metadata để tải tiếp byte file | Range không được bảo vệ đúng | Validator theo content URI |
| Cho GET của tenant khác trả 304 nếu tag khớp | Rò rỉ sự tồn tại và metadata | Authn/authz trước khi đánh giá validator |
| Dùng `Cache-Control: public` cho response phụ thuộc principal | Có thể phục vụ dữ liệu hoặc action của user khác | no-store/private và cache key được kiểm chứng |
| Hiểu `no-cache` là không lưu | Cache vẫn có thể lưu và revalidate | Dùng no-store khi cần không lưu |
| Trả body JSON với 304 hoặc 204 | Vi phạm semantics response không có body | Chỉ metadata hợp lệ, không có body |
| Dùng 409 cho mọi If-Match stale | Client khó phân biệt conflict HTTP với nghiệp vụ | 412 khi điều kiện HTTP không đạt |
| Dùng 412 cho mọi lỗi nghiệp vụ | Lẫn lộn version và trạng thái domain | 409/422 khi business invariant không đạt |
| Retry PATCH bỏ If-Match sau 412 | Ghi đè bản cập nhật của người khác | GET lại và giải quyết conflict |
| Nghĩ ETag tự ngăn tạo trùng POST hoặc thanh toán | Side effect có thể lặp | Idempotency key và lưu kết quả bền vững |
| Chỉ test tuần tự, không test database concurrent | Không bắt được race trong transaction | Test song song và kiểm tra version/side effect |

### 18.2. Checklist trước khi công bố API

- [ ] Resource có URI và **representation** được xác định rõ, bao gồm content negotiation và scope.
- [ ] ETag phát ra có **cú pháp hợp lệ**, được phân loại **strong** hoặc **weak**.
- [ ] Strong validator thay đổi đúng khi representation thay đổi theo nghĩa vụ của RFC.
- [ ] Weak validator chỉ bỏ qua những thay đổi mà client có thể chấp nhận là tương đương về ngữ nghĩa.
- [ ] `If-Match` dùng **strong comparison**, `If-None-Match` dùng **weak comparison**.
- [ ] Parser hỗ trợ danh sách entity-tag, dấu nháy, opaque tag, `W/` và `*` đúng chuẩn.
- [ ] GET/HEAD có điều kiện trả **304** không body khi thích hợp; khác tag thì trả representation hiện tại.
- [ ] PUT/PATCH/DELETE có precondition được xử lý trước side effect; **412** khi điều kiện không đạt.
- [ ] API yêu cầu `If-Match` có **428** khi thiếu; phân biệt rõ 409/403/404 và validation errors.
- [ ] `If-None-Match: *` cho create-if-absent có unique constraint/transaction chống race.
- [ ] `If-Match: *` không bị nhầm với kiểm tra version cụ thể.
- [ ] `If-Range` với entity-tag chỉ dùng strong validator của đúng byte representation.
- [ ] `@Version` hoặc CAS/lock được dùng **ở điểm ghi**, không chỉ so tag trong memory.
- [ ] Aggregate có nhiều hàng hoặc side effect có phương án transaction/đồng bộ riêng.
- [ ] Response theo quyền/tenant, gzip, ngôn ngữ, media type và link động có validator/cache strategy đúng.
- [ ] `Vary` và `Cache-Control` được cấu hình chính xác, không lộ dữ liệu khi thay principal.
- [ ] ETag không chứa token, thông tin bí mật hoặc định danh theo dõi không cần thiết.
- [ ] Timeout sau commit được xử lý bằng GET lại trạng thái hoặc idempotency/operation resource.
- [ ] Hợp đồng OpenAPI document ETag, `If-Match`, `If-None-Match`, 304/412/428 và mã lỗi.
- [ ] Test có strong/weak cross-compare, wildcard, stale write, lost response, Range, variants và cross-tenant.
- [ ] Có metrics 304 ratio, 412/428 count, cache hit/revalidation, stale-write conflict và latency DB.

### 18.3. Tài liệu kỹ thuật tham khảo

- **RFC 9110 — HTTP Semantics:** `8.8` validator fields, `13` conditional requests, `15` status code. [RFC 9110](https://www.rfc-editor.org/rfc/rfc9110)
- **RFC 9111 — HTTP Caching:** cache freshness, revalidation và xử lý cache. [RFC 9111](https://www.rfc-editor.org/rfc/rfc9111)
- **RFC 6585 — Additional HTTP Status Codes:** `428 Precondition Required`. [RFC 6585](https://www.rfc-editor.org/rfc/rfc6585)
- **RFC 9457 — Problem Details for HTTP APIs:** `application/problem+json` cho lỗi điều kiện. [RFC 9457](https://www.rfc-editor.org/rfc/rfc9457)
- **RFC 5789 — PATCH Method for HTTP:** semantics cập nhật một phần. [RFC 5789](https://www.rfc-editor.org/rfc/rfc5789)
- **OpenAPI Specification 3.1:** header parameters, response metadata, security và schema. [OpenAPI 3.1](https://spec.openapis.org/oas/v3.1.0)
- **Spring Framework / Spring Data JPA:** kiểm chứng `WebRequest.checkNotModified`, `ResponseEntity`, `@Version` và behavior theo phiên bản ứng dụng.

**Kết luận:** cả strong và weak ETag đều hữu ích, nhưng chúng có **những lời cam kết và cách so sánh khác nhau**. `If-None-Match` dùng **weak comparison** để tái xác thực GET/cache; `If-Match` dùng **strong comparison** để bảo vệ ghi có điều kiện; `If-Range` cần validator đủ mạnh cho từng phần dữ liệu. Thiết kế đúng phải gắn validator với **representation thực tế**, kiểm tra quyền trước khi tiết lộ trạng thái và bảo vệ thay đổi bằng **CAS/transaction** ở điểm ghi, không chỉ so chuỗi header.
