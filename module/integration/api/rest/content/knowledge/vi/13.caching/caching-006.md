# ETag, Last-Modified và yêu cầu đọc có điều kiện

## 1. Vấn đề: đọc lại tài nguyên nhưng dữ liệu chưa thay đổi

Trong REST API, ứng dụng thường gọi **GET** để đọc representation của một resource: chi tiết sản phẩm, thông tin đơn hàng, danh mục hoặc cấu hình. Nhiều lần đọc liên tiếp có thể trả cùng một nội dung. Nếu máy chủ gửi toàn bộ JSON mỗi lần, hệ thống tốn băng thông, thời gian truyền, tài nguyên serialize và đôi khi cả công sức dựng representation.

**HTTP conditional request** cho phép client diễn đạt: *“Tôi đã có một phiên bản của tài nguyên; chỉ gửi lại nội dung nếu representation cần dùng đã thay đổi.”* Hai loại validator thường gặp:

- **ETag (entity tag):** một nhãn phiên bản/định danh mờ do server phát hành cho representation.
- **Last-Modified:** thời điểm mà server tin rằng representation đã thay đổi lần cuối, dùng cú pháp ngày HTTP.

Client có thể gửi lại:

- **If-None-Match:** so sánh với ETag đang nắm giữ.
- **If-Modified-Since:** so sánh với Last-Modified đã nhận.

Nếu điều kiện revalidation của một request GET/HEAD hợp lệ cho thấy representation không đổi, server có thể trả **304 Not Modified** và **không gửi response body**. Nếu representation đã đổi, server trả **200 OK** cùng representation mới và validator mới.

Ví dụ một client gọi endpoint công khai:

~~~http
GET /api/products/prod-42 HTTP/1.1
Host: api.example.test
Accept: application/json

HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: public, max-age=60
ETag: "product-42-v7"
Last-Modified: Wed, 18 Nov 2026 10:00:00 GMT

{"id":"prod-42","name":"Sổ tay","price":45000}
~~~

Sau đó, khi cần kiểm tra lại phiên bản:

~~~http
GET /api/products/prod-42 HTTP/1.1
Host: api.example.test
If-None-Match: "product-42-v7"

HTTP/1.1 304 Not Modified
ETag: "product-42-v7"
Cache-Control: public, max-age=60
Last-Modified: Wed, 18 Nov 2026 10:00:00 GMT
~~~

Client có thể tiếp tục dùng representation phù hợp đã lưu nếu nó vẫn được phép sử dụng. **304 không có JSON body**; nó xác nhận điều kiện cache cho một representation đã biết, không phải response thành công mang một resource mới.

Trong module thiết kế REST API, cơ chế này cần được hiểu cùng **URI, GET/HEAD, HTTP status, cache policy, ETag theo representation, xác thực/phân quyền, OpenAPI và kiểm thử Java/Spring**.

> **Quy tắc ghi nhớ:** ETag/Last-Modified là **validator**; If-None-Match/If-Modified-Since là **điều kiện gửi từ client**; 304 là **kết quả revalidation khi representation chưa thay đổi**, không phải mã dùng cho mọi trường hợp thiếu body.

## 2. Ba khái niệm cần tách biệt

| Khái niệm | Trả lời câu hỏi | Ví dụ |
|---|---|---|
| **Representation** | Nội dung được trả cho một resource trong ngữ cảnh request | JSON của product, theo Accept/locale/quyền |
| **Validator** | Làm thế nào so sánh phiên bản representation? | ETag, Last-Modified |
| **Freshness/cache policy** | Bản đã lưu có thể dùng mà không cần hỏi server trong bao lâu? | Cache-Control: max-age=60, no-cache |

ETag **không tự có nghĩa response được phép lưu cache**. Ngược lại, Cache-Control: max-age=60 không buộc server phải có ETag. Chúng thường phối hợp để vừa tận dụng khoảng thời gian còn tươi, vừa revalidate khi cần.

### 2.1. Luồng tổng quát

~~~mermaid
sequenceDiagram
    participant C as HTTP Client / Cache
    participant A as REST API
    C->>A: GET /products/42
    A-->>C: 200 OK + body + ETag "v7"
    Note over C: Lưu representation khi chính sách cho phép
    C->>A: GET /products/42 + If-None-Match "v7"
    A->>A: Kiểm tra quyền, resource và validator
    alt Representation chưa đổi
      A-->>C: 304 Not Modified + headers, không body
      Note over C: Tái sử dụng body phù hợp đã lưu
    else Representation đã đổi
      A-->>C: 200 OK + body mới + ETag "v8"
      Note over C: Cập nhật bản đã lưu
    end
~~~

Sơ đồ đơn giản hóa luồng chính, chưa diễn đạt mọi trường hợp xác thực lỗi, tài nguyên bị xóa, request có nhiều precondition hoặc HTTP cache trung gian. **Không được so ETag rồi trả 304 trước khi xét quyền truy cập và trạng thái tài nguyên hiện hành**.

### 2.2. Phân biệt nguồn dữ liệu với representation

Một sản phẩm ở database có cột version = 7, nhưng representation công khai có thể thay đổi khi:

- Giá sản phẩm thay đổi.
- Tên danh mục liên quan thay đổi và được nhúng trong body.
- Client chọn ngôn ngữ khác qua Accept-Language.
- API thay đổi fields/expand hoặc content negotiation.
- Chính sách phân quyền làm ẩn/hiện một trường.

Vì vậy validator phải tương ứng với **representation có thể được trả trong bối cảnh request**, chứ không mặc định chỉ là version của một row DB bất kể body được dựng như thế nào.

## 3. ETag: nhãn phiên bản mờ của representation

### 3.1. Cú pháp và ý nghĩa

Một ETag hợp lệ về mặt cú pháp có dạng chuỗi trong dấu ngoặc kép; ETag yếu có tiền tố **W/**:

~~~http
ETag: "product-42-v7"
ETag: W/"product-42-v7"
~~~

Client phải coi giá trị ETag là **opaque**: không dựa vào nội dung chuỗi để suy ra phiên bản DB, thời gian, hash, tính bảo mật hoặc thứ tự bản cập nhật. Server có thể dùng version, hash hoặc một nhãn khác, miễn tuân thủ ngữ nghĩa so sánh mà nó công bố.

Không nhầm ETag với:

- URI hoặc primary key của resource.
- Access token hoặc chữ ký ủy quyền.
- Mã kiểm tra tính toàn vẹn có chứng thực mật mã; ETag không mặc nhiên là checksum an toàn.
- Last-Modified; một bên là nhãn, một bên là thời điểm.

### 3.2. Strong ETag và weak ETag

| Kiểu | Ví dụ | Cam kết so sánh | Dùng trong revalidation GET |
|---|---|---|---|
| **Strong entity tag** | "p42-v7" | Phân biệt representation khi dữ liệu representation thay đổi ở mức quan trọng với strong comparison | Có |
| **Weak entity tag** | W/"p42-v7" | Hai representation có thể khác byte nhưng được xem là tương đương theo ngữ nghĩa mà server chọn | Có |

HTTP dùng hai phép so sánh:

- **Strong comparison:** chỉ khớp khi *cả hai tag đều strong* và opaque tag giống nhau.
- **Weak comparison:** khớp nếu opaque tag giống nhau, bất kể có tiền tố W/ hay không.

**If-None-Match dùng weak comparison**; đây là một điểm rất quan trọng khi tối ưu GET/HEAD. Còn **If-Match**, thường dùng với thao tác cập nhật có điều kiện, dùng strong comparison để bảo vệ thay đổi đồng thời.

Ví dụ:

| Validator hiện tại | Header từ client | Kết quả so sánh cho If-None-Match |
|---|---|---|
| "abc" | If-None-Match: "abc" | Khớp |
| W/"abc" | If-None-Match: "abc" | Khớp theo weak comparison |
| "abc" | If-None-Match: W/"abc" | Khớp theo weak comparison |
| "abc" | If-None-Match: "xyz" | Không khớp |

Không tự thêm/bỏ W/ trong client để “đổi” độ mạnh của tag; server chịu trách nhiệm phát hành validator với ngữ nghĩa chính xác.

### 3.3. ETag được tạo thế nào?

| Chiến lược | Điểm mạnh | Rủi ro/cần kiểm tra |
|---|---|---|
| **Hash của bytes representation** | Liên hệ trực tiếp nội dung đã tạo | Có thể cần serialize/body trước khi tính; Content-Encoding và biến thể phải được xét |
| **Version của resource** | Rẻ nếu DB đã có version tăng đúng | Bỏ sót thay đổi từ bảng liên quan, locale hoặc projection |
| **Version tổng hợp** | Bao gồm dữ liệu quan hệ và phiên bản rendering | Cần bảo đảm mọi thay đổi ảnh hưởng representation đều làm thay tag |
| **ETag do gateway/storage quản lý** | Thuận lợi nếu hạ tầng cung cấp đúng | Không giả định ETag của object store luôn là hash nội dung theo cách client nghĩ |

Nếu body của /products/42 chứa name và price, một ETag dựa trên version phù hợp khi **mọi thay đổi liên quan đến body đều tăng version**. Nếu body mở rộng categories.name mà category đổi không tăng product version, ETag đó có thể trở thành **validator sai**.

### 3.4. Strong tag và Content-Encoding

Khi cùng một resource có thể trả representation được nén gzip và representation không nén, nội dung bytes của hai dạng khác nhau. Một **strong ETag** không nên được dùng như cùng một strong validator cho các content coding khác nhau nếu byte của representation khác nhau. Server có thể tạo tag mạnh khác nhau theo content coding hoặc sử dụng weak validator khi phù hợp.

Ví dụ minh họa:

~~~http
Vary: Accept-Encoding
ETag: "p42-v7-gzip"
Content-Encoding: gzip
~~~

so với:

~~~http
Vary: Accept-Encoding
ETag: "p42-v7-identity"
~~~

Đây chỉ là ví dụ nhãn do ứng dụng chọn, không phải định dạng bắt buộc. **Vary** giúp cache nhận diện sự khác biệt do request header ảnh hưởng representation, còn ETag phải phản ánh tính tương đương đúng của representation được chọn.

### 3.5. Vì sao hash không nhất thiết luôn tốt hơn version?

Nếu server phải query toàn bộ aggregate, dựng JSON, nén rồi tính hash **trước khi biết có thể trả 304**, chi phí DB/CPU có thể gần như request 200. Conditional GET lúc đó chủ yếu tiết kiệm network.

Một version đã duy trì chính xác tại nguồn có thể giúp kiểm tra nhanh, nhưng chỉ an toàn nếu nó bao quát **mọi dữ liệu ảnh hưởng response**. Chọn cách tạo validator dựa trên trade-off giữa tính đúng, chi phí tính toán, độ phức tạp và phạm vi cache.

## 4. Last-Modified: validator theo thời điểm

Last-Modified cho biết thời điểm mà origin server tin rằng representation được sửa đổi lần cuối, dùng cú pháp **HTTP-date**:

~~~http
Last-Modified: Wed, 18 Nov 2026 10:00:00 GMT
~~~

Ví dụ client lưu header và gửi:

~~~http
If-Modified-Since: Wed, 18 Nov 2026 10:00:00 GMT
~~~

Nếu server xác định representation chưa thay đổi kể từ thời điểm được cung cấp và các điều kiện áp dụng, response GET/HEAD có thể là 304.

### 4.1. Last-Modified khác thời gian tạo dữ liệu

- **createdAt:** thời điểm tạo resource.
- **updatedAt:** thời điểm cập nhật bản ghi.
- **Last-Modified:** thời điểm dùng làm validator cho **representation hiện tại**.

Nếu API nhúng thông tin category và category đổi, Last-Modified chỉ dựa trên product.updatedAt có thể không đủ. Cần tính từ các thành phần liên quan hoặc chọn không cung cấp Last-Modified nếu không bảo đảm chính xác.

### 4.2. Giới hạn độ chính xác theo giây

HTTP-date có độ phân giải **một giây**. Nếu representation thay đổi hai lần trong cùng giây, Last-Modified có thể trùng dù nội dung đã khác.

~~~text
10:00:00.100  product giá 45.000
10:00:00.800  product giá 49.000
Last-Modified cùng hiển thị: 10:00:00 GMT
~~~

Một client chỉ dùng If-Modified-Since có thể không phát hiện sự thay đổi khi server đánh giá thời gian với độ chính xác không đủ. Vì vậy, đối với tài nguyên thay đổi nhanh, **ưu tiên cung cấp ETag chính xác**; Last-Modified có thể bổ sung khi đáng tin cậy.

**Không tùy tiện coi timestamp mili giây trong DB là HTTP Last-Modified có cùng độ chính xác**. Phải hiểu cách chuyển sang HTTP-date, cập nhật và so sánh để tránh sai điều kiện.

### 4.3. Clock skew và timestamp không đáng tin

Nếu nhiều node có đồng hồ lệch nhau hoặc dữ liệu được đồng bộ bất đồng bộ, updatedAt có thể đi lùi hoặc phản ánh thời điểm chưa nhìn thấy phiên bản mới. Cần dùng nguồn thời gian và cơ chế version phù hợp, kiểm tra tính nhất quán khi replica chuyển vai trò.

Nếu client gửi một ngày không hợp lệ, header đó không nên khiến API trả 500. Nếu client gửi thời điểm tương lai hoặc giá trị không có ý nghĩa với phiên bản, server phải áp dụng quy tắc HTTP và kiểm tra implementation; không được coi header của client là quyền truy cập hay bằng chứng dữ liệu đã cập nhật.

## 5. If-None-Match: điều kiện theo ETag

### 5.1. Một ETag

Client đã nhận:

~~~http
ETag: "product-42-v7"
~~~

Nó yêu cầu:

~~~http
GET /api/products/prod-42 HTTP/1.1
If-None-Match: "product-42-v7"
~~~

Nếu representation hiện tại vẫn có tag phù hợp theo weak comparison và các điều kiện khác cho phép, **304** là phản hồi thích hợp. Nếu tag hiện tại là "product-42-v8", response là **200** cùng body và validator v8.

### 5.2. Danh sách các ETag

Header có thể chứa nhiều tag:

~~~http
If-None-Match: "product-42-v5", "product-42-v7", W/"product-42-v6"
~~~

Điều kiện khớp nếu **bất kỳ** tag nào trong danh sách khớp với ETag hiện tại theo quy tắc của If-None-Match.

Không viết parser bằng cách tách dấu phẩy tùy tiện nếu chưa xử lý đúng cú pháp entity-tag, dấu ngoặc kép và giá trị hợp lệ. Trong Java/Spring nên dùng cơ chế xử lý HTTP condition của framework thay vì tự so raw string.

### 5.3. Dấu sao trong If-None-Match

~~~http
If-None-Match: *
~~~

Giá trị dấu sao khớp khi có **representation hiện tại cho resource đích** theo quy tắc HTTP. Với GET/HEAD, điều kiện này có thể dẫn đến 304 nếu resource hiện tồn tại và request được phép. Nếu resource không tồn tại, đây **không phải lý do để trả 304**: server xử lý theo trạng thái tài nguyên, ví dụ 404.

Với **PUT tạo mới**, If-None-Match: * cũng thường được dùng để yêu cầu *chỉ tạo khi resource chưa tồn tại*; nếu điều kiện không đạt, response cho thao tác không phải GET/HEAD thường là **412 Precondition Failed**, không phải 304. Chủ đề cập nhật có điều kiện được phân biệt thêm ở phần sau.

### 5.4. ETag không phải token xác thực

Một client có thể đoán hoặc biết một ETag cũ. Nếu resource đã thuộc tenant khác hoặc quyền đọc bị thu hồi, server không được trả 304 chỉ vì header If-None-Match khớp. **Authentication/authorization và trạng thái tài nguyên hiện hành phải được đánh giá trước khi dùng validator để rút ngắn response**.

## 6. If-Modified-Since: điều kiện theo Last-Modified

Client đã đọc:

~~~http
HTTP/1.1 200 OK
Last-Modified: Wed, 18 Nov 2026 10:00:00 GMT
ETag: "product-42-v7"
Content-Type: application/json

{"id":"prod-42","price":45000}
~~~

Một client không dùng ETag có thể gửi:

~~~http
GET /api/products/prod-42 HTTP/1.1
If-Modified-Since: Wed, 18 Nov 2026 10:00:00 GMT
~~~

Nếu Last-Modified hiện tại **không muộn hơn** thời điểm trong header, server có thể trả 304 theo các điều kiện chuẩn HTTP. Nếu có thay đổi muộn hơn mốc đó, server trả 200 với representation mới.

Lưu ý:

- If-Modified-Since chủ yếu được định nghĩa cho **GET và HEAD**; với method khác, server không dùng nó theo cùng cơ chế revalidation.
- Giá trị header phải là **ngày HTTP hợp lệ**. Với giá trị không hợp lệ, server bỏ qua điều kiện đó thay vì suy luận tùy tiện.
- Last-Modified không được tính chỉ từ đồng hồ của máy phát request; phải phản ánh trạng thái representation phía origin.
- Nếu không thể xác định chính xác mốc thời gian, có thể không dùng Last-Modified và dựa vào ETag.

### 6.1. Khi cả hai header được gửi

~~~http
GET /api/products/prod-42 HTTP/1.1
If-None-Match: "product-42-v6"
If-Modified-Since: Wed, 18 Nov 2026 10:00:00 GMT
~~~

Khi **If-None-Match hiện diện**, server **phải bỏ qua If-Modified-Since** khi đánh giá điều kiện đọc này. Đây không phải bài toán “chọn header nào khớp thì trả 304” hay ghép hai điều kiện bằng AND.

Giả sử ETag hiện tại là "product-42-v7" nhưng Last-Modified vẫn hiển thị 10:00:00 GMT vì hai lần sửa trong cùng giây:

- If-None-Match: "product-42-v6" **không khớp**.
- Server không dùng kết quả If-Modified-Since để lật kết luận.
- Với request GET hợp lệ, trả **200** chứa representation mới.

Đây là một lợi ích quan trọng của ETag khi Last-Modified có độ phân giải thời gian thấp.

## 7. Mã 304 Not Modified: điều gì được và không được gửi?

**304** áp dụng cho conditional GET/HEAD khi các điều kiện cho biết có thể dùng bản representation đã lưu; nó không phải body rỗng của 200 và cũng không phải 204 No Content.

Ví dụ:

~~~http
HTTP/1.1 304 Not Modified
Date: Wed, 18 Nov 2026 10:05:00 GMT
ETag: "product-42-v7"
Last-Modified: Wed, 18 Nov 2026 10:00:00 GMT
Cache-Control: public, max-age=60
Vary: Accept-Language
~~~

### 7.1. Những thuộc tính chính của 304

- **Không có message body**. Không gửi JSON rỗng, Problem Details hay một bản resource mới sau status 304.
- Header phù hợp giúp cache **cập nhật metadata của response đã lưu** để tiếp tục sử dụng representation tương ứng.
- 304 **không có nghĩa resource bị xóa, body là null hoặc user không có quyền**.
- Khi server trả 304, vẫn có thể phải thực hiện truy vấn/kiểm tra metadata và authorization; “không gửi body” không đồng nghĩa “không tốn CPU/DB”.
- API có thể trả 304 với HEAD phù hợp dù HEAD vốn không mang response body.

Theo ngữ nghĩa HTTP, origin server tạo 304 cần gửi những header cần thiết từ response 200 tương ứng như **ETag, Vary, Cache-Control, Expires, Content-Location, Date** khi chúng đáng lẽ được gửi theo quy tắc. Last-Modified thường cũng nên được duy trì nhất quán khi đã có. Tránh gửi các header mô tả payload mới mà client có thể hiểu là một body đang được truyền.

### 7.2. Khi nào không được trả 304?

| Tình huống | Phản hồi phù hợp | Vì sao |
|---|---|---|
| ETag cũ không khớp representation hiện tại | 200 (nếu có quyền đọc) | Client cần body mới |
| Không có điều kiện đọc và resource hiện hữu | 200 | Client chưa yêu cầu revalidation |
| Resource không tồn tại hoặc đã bị ẩn | 404/410 theo hợp đồng và quyền | Không có representation hiện tại được phép dùng |
| Client chưa xác thực với API private | 401 và challenge thích hợp | Không để validator bỏ qua authentication |
| Client thiếu quyền đọc | 403 hoặc 404 theo chính sách che giấu | Không để 304 tiết lộ quyền/tồn tại |
| Server không truy cập được DB và không có cơ chế fallback hợp lệ | Lỗi 5xx thích hợp | Không bịa “không đổi” khi không thể kiểm tra |
| Client gửi PUT với If-Match không khớp | 412 | Đây là điều kiện ghi, không phải GET revalidation |
| Server muốn báo tạo/xóa thành công nhưng không có body | 201/204/202 tùy nghiệp vụ | 304 không diễn đạt kết quả của lệnh ghi |

### 7.3. Một client không có bản cache sẽ làm gì với 304?

Nếu client tự gửi If-None-Match nhưng **không giữ một representation phù hợp**, nó có thể nhận 304 và không có body để hiển thị. Đó không phải cách thích hợp để lấy dữ liệu lần đầu.

Client nên gửi conditional headers khi có bản hợp lệ để so sánh; nếu không thể dùng body đã lưu hoặc các metadata của cache không còn tương ứng, **gửi GET không có điều kiện** để lấy 200 và representation. Một 304 không phải API tiện dụng để chỉ hỏi “resource có tồn tại không?” trong mọi bối cảnh.

## 8. Thứ tự đánh giá các điều kiện HTTP

Với GET/HEAD thường gặp, có thể nhớ thứ tự thực tế:

1. Kiểm tra **authentication, authorization, URI và representation**; các lỗi ban đầu cần xử lý theo ngữ nghĩa HTTP.
2. Nếu request có những **precondition khác** như If-Match hoặc If-Unmodified-Since, chúng có thứ tự ưu tiên riêng trong chuẩn và có thể ngăn xử lý tiếp.
3. Nếu có **If-None-Match**, đánh giá so sánh ETag với validator hiện tại theo weak comparison.
4. Nếu **không có If-None-Match** và có If-Modified-Since cho GET/HEAD, xét thời gian Last-Modified.
5. Nếu điều kiện revalidation cho thấy không đổi, trả 304; nếu đã đổi, trả 200 với representation hiện hành.

Nhìn dưới dạng luồng đơn giản:

~~~mermaid
flowchart TD
    A[GET hoặc HEAD tới resource] --> B{Xác thực và quyền đọc hợp lệ?}
    B -->|Không| C[401 / 403 / 404 theo chính sách]
    B -->|Có| D{Resource và representation tồn tại?}
    D -->|Không| E[404 / 410]
    D -->|Có| P[Đánh giá các precondition khác nếu có]
    P --> F{Có If-None-Match?}
    F -->|Có| G{ETag hiện tại khớp?}
    G -->|Có| H[304 không có body]
    G -->|Không| I[200 có body với GET]
    F -->|Không| J{Có If-Modified-Since hợp lệ?}
    J -->|Không| I
    J -->|Có| K{Có thay đổi sau mốc thời gian?}
    K -->|Không| H
    K -->|Có| I
~~~

Sơ đồ cố ý tập trung hai header của **yêu cầu đọc có điều kiện**; việc xử lý đầy đủ mọi precondition phải tuân theo RFC và framework. Không dùng sơ đồ này để tự triển khai thuật toán điều kiện cho mọi HTTP method.

### 8.1. Tại sao If-Match khác If-None-Match?

- **If-None-Match** với GET/HEAD giúp **không tải lại** representation khi validator còn khớp.
- **If-Match** thường giúp **tránh ghi đè phiên bản mới hơn** khi client cập nhật resource. Nó dùng strong comparison; mismatch thường dẫn đến **412 Precondition Failed**.
- **If-Unmodified-Since** là điều kiện ghi dựa trên thời gian, có độ chính xác hạn chế.
- **428 Precondition Required** có thể được server dùng khi bắt buộc request phải có precondition để tránh lost update.

Ví dụ cập nhật có điều kiện:

~~~http
PUT /api/products/prod-42 HTTP/1.1
If-Match: "product-42-v7"
Content-Type: application/json

{"name":"Sổ tay mới","price":49000}
~~~

Nếu phiên bản hiện hành đã khác, có thể trả 412 thay vì ghi đè. Đây là **hành vi điều kiện cập nhật**, không phải trường hợp dùng 304; cần kiểm tra cả tính nguyên tử của việc so khớp version và thao tác ghi.

## 9. Kết hợp validator với Cache-Control

Validator giúp server và cache xác định representation **đã thay đổi hay chưa**. Cache-Control hướng dẫn **khi nào cache được dùng nội dung đã lưu** và có cần liên hệ server không.

| Chỉ dẫn | Ý nghĩa chính | Tác động đến conditional GET |
|---|---|---|
| **public** | Cho phép shared cache lưu nếu các quy tắc khác cho phép | Hữu ích cho catalog công khai |
| **private** | Response dành cho private cache, không dành cho shared cache | Phù hợp với dữ liệu phụ thuộc người dùng |
| **max-age=60** | Freshness lifetime 60 giây theo quy tắc cache | Trong thời gian còn fresh, cache thường không cần revalidate |
| **s-maxage=60** | Freshness dành cho shared cache | Có thể khác max-age của private cache |
| **no-cache** | Cache có thể lưu nhưng **phải revalidate trước khi dùng lại** theo yêu cầu | Có thể tạo If-None-Match / If-Modified-Since |
| **no-store** | Cache không được lưu response theo chính sách | Không có bản lưu để tự revalidate theo mô hình cache thông thường |
| **must-revalidate** | Khi response đã stale, không được sử dụng lại mà chưa revalidate thành công | Giới hạn phục vụ dữ liệu stale |

### 9.1. no-cache không đồng nghĩa no-store

Hai phản hồi:

~~~http
Cache-Control: private, no-cache
ETag: "my-order-v7"
~~~

và:

~~~http
Cache-Control: no-store
ETag: "my-order-v7"
~~~

**không giống nhau**.

- Với **private, no-cache**, một private cache có thể lưu response nhưng phải xác nhận với origin hoặc cơ chế revalidation hợp lệ trước khi tái sử dụng. ETag có thể giúp nhận 304 thay vì tải lại JSON.
- Với **no-store**, một HTTP cache tuân thủ không lưu response để tái sử dụng; tự động tận dụng 304 từ một bản HTTP-cache đã lưu sẽ không phải hành vi mong đợi.

Một ứng dụng có thể chủ động quản lý dữ liệu và validator ngoài HTTP cache, nhưng phải bảo đảm việc đó phù hợp chính sách bảo mật, yêu cầu dữ liệu và hợp đồng. **Đừng thêm ETag rồi mặc định no-store vẫn tiết kiệm băng thông cho browser cache**.

### 9.2. max-age và thời điểm revalidation

Ví dụ:

~~~http
Cache-Control: public, max-age=60
ETag: "catalog-v12"
~~~

Trong khoảng freshness, cache có thể dùng response đã lưu mà **không gửi request tới origin**. Sau khi stale (hoặc khi client yêu cầu revalidation phù hợp), cache có thể gửi If-None-Match. Nếu được trả 304, metadata của bản lưu được cập nhật và body được tái sử dụng theo quy tắc cache.

**304 vẫn có một network round trip** giữa cache/client và phía xác minh. Nếu mục tiêu là giảm độ trễ cho tài nguyên công khai ít thay đổi, freshness hợp lý có thể hiệu quả hơn revalidation bắt buộc ở mọi request. Ngược lại, dữ liệu thay đổi nhanh có thể cần max-age thấp hoặc no-cache để giữ độ mới.

### 9.3. Cache tại nhiều tầng

Một hành trình đọc có thể đi qua:

~~~mermaid
flowchart LR
    U[Ứng dụng hoặc browser] --> B[Private HTTP cache]
    B --> G[Gateway / CDN / Shared cache]
    G --> A[Origin REST API]
    A --> D[(Database / Read model)]
~~~

Mỗi tầng có thể kiểm tra freshness hoặc gửi conditional request xuống tầng sau. Một 304 từ origin giúp CDN dùng lại body đã lưu; CDN có thể trả **200 kèm body từ cache** cho client cuối hoặc tự trả 304 cho một client có điều kiện, tùy request và trạng thái cache.

Vì vậy **không mặc định client cuối sẽ luôn nhìn thấy 304** chỉ vì origin đã tạo 304. Quan sát log/metric cần phân biệt response tại edge và response tại origin.

### 9.4. Negative caching cho 404/410

HTTP cache cũng có thể lưu một số phản hồi lỗi như 404/410 theo quy tắc phù hợp. Nếu tài nguyên chưa tồn tại rồi được tạo, một bản 404 cũ ở cache có thể kéo dài tình trạng “không tìm thấy”.

Với tài nguyên có thể xuất hiện/phục hồi nhanh, phải cân nhắc TTL và invalidation cho **negative cache**. Đừng giải quyết trường hợp 404 stale bằng cách trả 304 giả: một response “không tìm thấy” và một representation hiện hữu là hai trạng thái khác nhau.

## 10. Validators phải đúng với từng representation và quyền

### 10.1. Content negotiation và Vary

Cùng URI /api/products/prod-42 có thể trả:

- JSON bằng tiếng Việt khi Accept-Language: vi.
- JSON bằng tiếng Anh khi Accept-Language: en.
- Một representation với Content-Encoding: gzip khi client chấp nhận nén.
- Một trường hợp response theo media type khác, ví dụ application/vnd.example.product+json.

Nếu nội dung thay đổi theo request header, cần **Vary** thích hợp để cache chọn đúng variant. Ví dụ:

~~~http
HTTP/1.1 200 OK
Vary: Accept-Language, Accept-Encoding
ETag: "p42-v7-vi-gzip"
Content-Encoding: gzip
~~~

ETag phải xác nhận đúng representation được chọn. Không nên dùng một strong ETag giống hệt cho hai representation có bytes khác nhau và mong cache tự hiểu ngữ cảnh. Nếu một weak ETag được chia sẻ giữa các biến thể tương đương về ngữ nghĩa, cần đảm bảo điều đó đúng với chuẩn và cách sử dụng của API.

### 10.2. Fields, expand và query parameters

Các request:

~~~http
GET /api/orders/42?fields=id,status
GET /api/orders/42?fields=id,status,totalAmount&expand=customer
~~~

có thể trả body khác nhau. Query string là một phần của URI dùng để xác định cache key theo cách thông thường, nhưng gateway/CDN có thể được cấu hình bỏ qua hoặc chuẩn hóa một số query parameter. **Không để cache key gộp hai URI có representation khác nhau**.

Nếu ETag được sinh từ order.version nhưng expanded customer thay đổi, validator có thể sai. Cần ETag cho **shape và dữ liệu liên quan** hoặc không hỗ trợ validator cho tổ hợp expansion chưa thể tạo đúng.

### 10.3. Dữ liệu cá nhân và nhiều tenant

Ví dụ user A và user B cùng gọi GET /api/orders/42. Một trong hai người có thể không có quyền xem đơn, hoặc mỗi người chỉ được thấy một tập field khác nhau. Do đó:

1. **Authentication/authorization** phải được thực thi ở mỗi lần request, kể cả conditional request.
2. Nếu user B không có quyền, không được trả 304 chỉ vì user A từng nhận ETag trùng.
3. Không dùng shared cache chứa dữ liệu riêng tư nếu không có thiết kế phân tách/ủy quyền đáng tin cậy.
4. ETag không được sử dụng làm chứng từ sở hữu resource; nó chỉ là validator.
5. Nếu quyền bị thu hồi, GET với ETag cũ phải phản ánh chính sách quyền **hiện hành**, không tái xác nhận bản bị cấm.

Ví dụ response cho tài nguyên cá nhân:

~~~http
HTTP/1.1 200 OK
Cache-Control: private, no-cache
ETag: "order-42-view-v5"
Content-Type: application/json
~~~

Chính sách trên chỉ là phương án nếu việc lưu ở private cache được chấp nhận. Với dữ liệu nhạy cảm cần ngăn lưu, ưu tiên **no-store**; khi đó lợi ích cache tự động của conditional GET sẽ hạn chế hơn.

**Cảnh báo:** Chỉ thêm Vary: Authorization không tự biến một shared cache thành nơi an toàn để lưu dữ liệu nhiều người dùng. Cần tuân thủ Cache-Control, thiết kế key/permission và quy tắc cache của tầng trung gian; khi không chắc, dùng private hoặc no-store theo phân loại dữ liệu.

### 10.4. Tài nguyên xóa, ẩn hoặc đổi quyền

Một sản phẩm công khai có thể bị gỡ; một đơn hàng có thể soft-delete; người gọi có thể mất quyền. Khi đó request có điều kiện:

~~~http
GET /api/orders/42 HTTP/1.1
If-None-Match: "order-42-v5"
~~~

không mặc nhiên được 304. Server phải xác định:

- Resource còn representation hiện tại được phép truy cập không?
- Trạng thái xóa có được công khai bằng 410 hay che giấu bằng 404?
- Người gọi có đủ quyền đọc không (401/403/404 theo mô hình bảo mật)?
- Nếu được phép và có representation, validator hiện tại có khớp không?

**Trả 304 cho một ETag cũ khi tài nguyên bị xóa hoặc cấm là sai**; có thể khiến client giữ dữ liệu không được phép hoặc làm lộ sự tồn tại.

## 11. Những tình huống nghiệp vụ và quyết định cache

| Tài nguyên | Khả năng thay đổi | Cách dùng validator tham khảo | Cache policy tham khảo |
|---|---|---|---|
| Catalog công khai | Đổi giá/tên theo đợt | Strong ETag từ version đúng hoặc hash; Last-Modified nếu đáng tin | public, max-age ngắn có chủ đích |
| Tài liệu phiên bản hóa | Hầu như bất biến | ETag ổn định cho từng representation, Last-Modified | TTL dài nếu URI mang version và không đổi |
| Đơn hàng cá nhân | Trạng thái thay đổi và nhạy cảm | ETag theo trạng thái và quyền; không dùng nếu khó xác minh đúng | private, no-cache hoặc no-store tùy phân loại |
| Danh sách đơn phân trang | Dễ đổi do insert/delete/sort | Validator theo query shape, trang và data version nếu khả thi | Thường thận trọng với freshness/cache |
| File nhị phân tĩnh | Thay đổi theo phiên bản | Strong ETag chính xác cho selected representation | Có thể cache dài khi tên file/version bất biến |
| Dashboard tổng hợp | Thường đọc nhiều nguồn | Validator tổng hợp nếu được duy trì đúng; có thể chỉ dùng TTL | Theo mức độ chấp nhận stale và chi phí |

Không có một bộ header phù hợp cho mọi endpoint. Để chọn, hãy xét **mức độ công khai, độ mới bắt buộc, tần suất thay đổi, kích thước payload, chi phí tính validator, độ trễ mạng, cách quản lý quyền và khả năng invalidation**.

### 11.1. Ví dụ dữ liệu thay đổi nhanh

Endpoint GET /api/stock/{sku} có số lượng hàng biến động hàng chục lần mỗi giây. Một Last-Modified chỉ đến giây rất dễ không phân biệt hai bản cập nhật. Nên xem xét ETag/sequence version chính xác và mức độ chấp nhận dữ liệu cũ của nghiệp vụ. **Cache không được là nguồn sự thật để xác nhận giữ hàng** trong một giao dịch checkout; thao tác ghi cần kiểm tra tồn kho authoritative.

### 11.2. Ví dụ dữ liệu bất biến theo URI

Một file /assets/manual-v3.pdf không thay đổi sau khi phát hành, có thể dùng cache freshness dài và ETag ổn định. Khi cập nhật tài liệu, hệ thống tạo URI /assets/manual-v4.pdf. Đây là cách giảm lượng conditional requests; không phải file nào cũng cần revalidate ở mỗi lần sử dụng.

### 11.3. Ví dụ collection và phân trang

ETag của GET /api/products?category=books&sort=name&page=2 cần phản ánh **trang kết quả cụ thể**, không chỉ version của một product bất kỳ. Nếu product được thêm trước trang 2, tập phần tử của trang 2 có thể đổi dù các product hiện trên trang chưa sửa. Vì vậy validator của collection thường khó duy trì hơn resource đơn lẻ; cần chiến lược query version/snapshot hoặc chọn không cung cấp ETag cho endpoint chưa bảo đảm độ đúng.

## 12. Triển khai conditional GET bằng Java/Spring MVC

### 12.1. Vì sao nên dùng hỗ trợ của framework?

So sánh thủ công bằng các phép như:

~~~java
if (clientHeader.equals(currentEtag)) {
    return ResponseEntity.status(304).build();
}
~~~

không bao quát đầy đủ cú pháp ETag, danh sách tag, weak comparison, dấu sao, precedence của If-None-Match so với If-Modified-Since, HEAD hoặc các HTTP precondition khác. Nó còn dễ bỏ qua authorization, Vary và header cần thiết trong response 304.

**Ưu tiên dùng cơ chế điều kiện HTTP đã được kiểm chứng của framework**, kết hợp validator được ứng dụng tạo đúng với representation.

### 12.2. Ví dụ ProductSnapshot và controller

Mã dưới đây minh họa Spring MVC thuộc Spring Framework 6 / Spring Boot 3. Những kiểu dữ liệu được định nghĩa để ví dụ tự mô tả; cơ chế tra cứu thật cần tích hợp với repository, security và cách quản lý version của ứng dụng.

~~~java
import java.time.Instant;
import java.time.temporal.ChronoUnit;
import jakarta.servlet.http.HttpServletResponse;

import org.springframework.http.CacheControl;
import org.springframework.http.HttpHeaders;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.context.request.WebRequest;

record ProductView(String id, String name, long price) {}

record ProductSnapshot(
        String id,
        long representationVersion,
        Instant modifiedAt,
        ProductView view) {}

interface ProductReader {
    // Phải kiểm tra danh tính, quyền, trạng thái và tenant trước khi trả snapshot.
    ProductSnapshot readVisible(
            String id, Authentication authentication);
}

@RestController
class ProductReadController {
    private final ProductReader reader;

    ProductReadController(ProductReader reader) {
        this.reader = reader;
    }

    @GetMapping("/api/products/{id}")
    ResponseEntity<ProductView> get(
            @PathVariable String id,
            Authentication authentication,
            WebRequest webRequest,
            HttpServletResponse servletResponse) {

        // Thực hiện authorization và kiểm tra resource trước revalidation.
        ProductSnapshot current = reader.readVisible(id, authentication);

        // Ví dụ chỉ có một JSON representation cho mỗi ID trong phạm vi quyền.
        // Version phải thay đổi khi bất kỳ trường nào trong ProductView thay đổi.
        String etag = "\"product-" + current.id()
                + "-v" + current.representationVersion() + "\"";
        long lastModified = current.modifiedAt()
                .truncatedTo(ChronoUnit.SECONDS)
                .toEpochMilli();

        // Giữ cache policy kể cả khi checkNotModified trả về 304.
        servletResponse.setHeader(
                HttpHeaders.CACHE_CONTROL, "private, no-cache");

        // Spring xử lý các điều kiện GET/HEAD theo quy tắc HTTP.
        // Nếu true, framework đã tạo response revalidation thích hợp.
        if (webRequest.checkNotModified(etag, lastModified)) {
            return null;
        }

        return ResponseEntity.ok()
                .eTag(etag)
                .lastModified(lastModified)
                .cacheControl(CacheControl.noCache().cachePrivate())
                .body(current.view());
    }
}
~~~

**Giải thích thiết kế:**

1. **readVisible** phải xử lý authentication, authorization và trạng thái resource trước khi lấy validator. Nếu không tìm thấy hoặc không được phép xem, trả 404/403/401 theo hợp đồng; không cho request chuyển thành 304.
2. **representationVersion** là version của **ProductView trong hợp đồng minh họa**, không mặc định là version DB nếu body phụ thuộc quan hệ hoặc locale.
3. **Last-Modified** được chuyển thành thời điểm theo giây khi phát header. ETag đảm nhiệm việc phân biệt các thay đổi trong cùng giây nếu version được duy trì đúng.
4. **WebRequest.checkNotModified** giúp xử lý điều kiện đọc, bao gồm ưu tiên If-None-Match so với If-Modified-Since, thay vì so raw string.
5. **ResponseEntity** cho nhánh 200 trả body và các header liên quan. Với nhánh 304, Spring đã cấu hình status/validator; return null chỉ là cách kết thúc handler sau khi kiểm tra điều kiện thành công.
6. **private, no-cache** cho phép private cache lưu nhưng phải revalidate trước khi dùng; đây chỉ là ví dụ chính sách. Với dữ liệu nhạy cảm bắt buộc không lưu, thay bằng no-store theo phân loại.

Đoạn ví dụ giả định một representation cố định và snapshot nhất quán: **view, version và modifiedAt** phải đến từ cùng trạng thái logic của resource. Nếu đọc version trước rồi dữ liệu sau qua hai transaction độc lập, response 200 có thể mang body không tương ứng ETag.

### 12.3. Điều kiện áp dụng và điểm cần chỉnh khi triển khai thật

- **Bảo mật:** cần một SecurityFilterChain thích hợp, xác thực token và kiểm tra quyền; không dựa vào việc client gửi một authentication object tùy ý.
- **Vary và content negotiation:** nếu response phụ thuộc Accept-Language, Accept-Encoding hoặc scope/fields, phải tạo validator đúng biến thể, thêm Vary phù hợp và kiểm thử.
- **Cache-Control:** public,max-age cho tài nguyên công khai có thể hiệu quả hơn private,no-cache; không copy cấu hình cache của sản phẩm sang API đơn hàng cá nhân.
- **HEAD:** Spring MVC thường hỗ trợ HEAD theo GET mapping; phải kiểm tra response không có body, status và header tương ứng.
- **Error handling:** 404, 403, 401 và lỗi server không được chuyển nhầm thành 304.
- **Hash/ETag format:** ví dụ dùng version và ID để dễ học. Nếu ID/version có thể làm lộ thông tin nhạy cảm, sử dụng token mờ phù hợp thay vì xuất trực tiếp metadata đó.
- **Lỗi lưu trữ:** nếu không kiểm chứng được version hiện hành và không có fallback đáng tin cậy, không trả 304 do đoán rằng dữ liệu “chắc chưa đổi”.

### 12.4. Shallow ETag Filter và giới hạn

Một số ứng dụng Spring dùng **ShallowEtagHeaderFilter** để sinh ETag từ response đã tạo. Nó có thể giúp client/cache tiết kiệm băng thông khi revalidate, nhưng việc sinh ETag kiểu này có thể đòi hỏi ứng dụng **xử lý, serialize và buffer response** trước, nên không nhất thiết giảm chi phí database hoặc CPU.

Nếu bottleneck là query nặng, việc thêm shallow ETag không đủ. Cần đo số query, thời gian dựng representation, băng thông và p95/p99 trước–sau. Cẩn trọng với response lớn hoặc streaming; một filter cần buffer body có thể ảnh hưởng bộ nhớ và không phù hợp cho mọi loại endpoint.

## 13. Hợp đồng OpenAPI cho yêu cầu đọc có điều kiện

OpenAPI nên mô tả các header request được hỗ trợ, header response và mã 304 **không có body**. Ví dụ rút gọn:

~~~yaml
paths:
  /api/products/{id}:
    get:
      summary: Read product with conditional HTTP caching
      parameters:
        - name: id
          in: path
          required: true
          schema:
            type: string
        - name: If-None-Match
          in: header
          required: false
          description: >
            One or more entity-tags from an earlier representation.
            For GET, a matching current validator yields 304.
          schema:
            type: string
          example: '"product-42-v7"'
        - name: If-Modified-Since
          in: header
          required: false
          description: >
            HTTP-date of a previously seen Last-Modified.
            Ignored when If-None-Match is present.
          schema:
            type: string
          example: "Wed, 18 Nov 2026 10:00:00 GMT"
      responses:
        '200':
          description: Current product representation
          headers:
            ETag:
              schema:
                type: string
            Last-Modified:
              schema:
                type: string
            Cache-Control:
              schema:
                type: string
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/Product'
        '304':
          description: >
            Representation has not changed according to the
            applicable conditional request. No response body.
          headers:
            ETag:
              schema:
                type: string
            Last-Modified:
              schema:
                type: string
            Cache-Control:
              schema:
                type: string
        '401':
          description: Authentication required or invalid
        '403':
          description: Insufficient permission
        '404':
          description: Product not found or deliberately hidden
components:
  schemas:
    Product:
      type: object
      required: [id, name, price]
      properties:
        id:
          type: string
        name:
          type: string
        price:
          type: integer
          format: int64
~~~

Đây là **một đoạn OpenAPI minh họa**, không bao gồm toàn bộ securitySchemes, error schemas, Vary/Content-Encoding, phạm vi cache hoặc policy đối với nhiều biến thể. Ở endpoint thật, phải ghi rõ mức tin cậy validator và quyền.

**Điểm quan trọng khi sinh SDK:** định nghĩa response 304 trong OpenAPI không làm HTTP client tự động lưu body, phát conditional request hoặc kết hợp 304 với bản cache. Cơ chế này phụ thuộc HTTP library, cấu hình cache và logic client. Một SDK không có bộ nhớ đệm tích hợp có thể nhận 304 dưới dạng status không có body và phải xử lý rõ.

## 14. Kiểm thử GET/HEAD có điều kiện

### 14.1. Kiểm tra qua curl

Lần đầu lấy representation và header:

~~~bash
curl -i \
  -H 'Accept: application/json' \
  https://api.example.test/api/products/prod-42
~~~

Giả sử ETag nhận được là "product-42-v7", kiểm tra revalidation:

~~~bash
curl -i \
  -H 'If-None-Match: "product-42-v7"' \
  https://api.example.test/api/products/prod-42
~~~

Khi resource chưa đổi và caller có quyền, kỳ vọng 304 với **không có JSON body**. Gửi một tag cũ:

~~~bash
curl -i \
  -H 'If-None-Match: "product-42-v6"' \
  https://api.example.test/api/products/prod-42
~~~

Kỳ vọng 200 với representation hiện tại và ETag mới.

Kiểm tra Last-Modified:

~~~bash
curl -i \
  -H 'If-Modified-Since: Wed, 18 Nov 2026 10:00:00 GMT' \
  https://api.example.test/api/products/prod-42
~~~

Kiểm tra HEAD:

~~~bash
curl -I \
  -H 'If-None-Match: "product-42-v7"' \
  https://api.example.test/api/products/prod-42
~~~

Lưu ý **curl -I gửi HEAD**, nên không phải bằng chứng GET trả đúng body. Khi test cần cả GET và HEAD. Chỉ dùng môi trường được cho phép, không ghi token thật hay dữ liệu nhạy cảm vào log chia sẻ.

### 14.2. Ma trận kiểm thử hợp đồng

| # | Request và trạng thái server | Kết quả mong đợi | Điểm cần xác minh |
|---:|---|---|---|
| 1 | GET không có điều kiện, resource hiện hữu | 200 | Có body, ETag/Last-Modified nếu đã công bố |
| 2 | GET với If-None-Match khớp | 304 | Không có body, header validator/cache phù hợp |
| 3 | GET với If-None-Match không khớp | 200 | Có body mới và ETag hiện tại |
| 4 | GET với danh sách ETag, một tag khớp | 304 | Parser list và weak comparison đúng |
| 5 | GET có weak tag W/"abc", server có strong "abc" | 304 nếu khớp theo điều kiện | If-None-Match dùng weak comparison |
| 6 | GET với If-None-Match: * và có representation hiện hành | 304 nếu request hợp lệ | Dấu sao được xử lý đúng |
| 7 | GET với If-Modified-Since bằng Last-Modified | 304 nếu không đổi | Ngày HTTP được parse đúng |
| 8 | GET với Last-Modified mới hơn giá trị If-Modified-Since | 200 | Client nhận representation cập nhật |
| 9 | GET có cả If-None-Match **không khớp** và If-Modified-Since trùng | 200 | If-None-Match ưu tiên |
| 10 | GET có If-Modified-Since sai cú pháp | Xử lý như không có điều kiện đó | Không báo 500 hay trả 304 tùy tiện |
| 11 | GET có token thiếu/hết hạn dù tag khớp | 401 | Có challenge phù hợp, không bị 304 bỏ qua |
| 12 | GET resource ngoài tenant dù tag khớp | 403/404 theo policy | Không lộ tồn tại hoặc dữ liệu |
| 13 | GET resource đã xóa dù tag cũ khớp | 404/410 theo policy | Không dùng 304 cho representation đã mất |
| 14 | HEAD có If-None-Match khớp | 304 | Không response body |
| 15 | HEAD không có điều kiện và resource hiện hữu | 200 | Metadata tương ứng GET, không body |
| 16 | GET với biến thể locale/fields khác | 200 hoặc 304 đúng biến thể | Không dùng validator sai shape |
| 17 | GET qua gateway/CDN và cache stale | 200/304 theo chuỗi cache | Không trộn người dùng/variant |
| 18 | PUT với If-Match không khớp | 412 | Không nhầm với 304, dữ liệu không bị ghi đè |
| 19 | DB không thể xác minh representation hiện tại | Lỗi thích hợp theo hợp đồng | Không bịa 304 |

Ma trận cần được chạy qua **các HTTP client thực tế được hỗ trợ**. Proxy, CDN và SDK có thể tự xử lý 304 hoặc điều chỉnh header, vì vậy kết quả tại origin và kết quả mà ứng dụng nhận được không nhất thiết giống hệt.

### 14.3. Fragment MockMvc cho Spring

Giả sử đã có một lớp test với MockMvc, cấu hình authentication hợp lệ và ProductReader trả ProductSnapshot có version 7:

~~~java
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.head;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.http.HttpHeaders;

// Fragment trong class test đã inject mockMvc và cấu hình security:
@Test
void matchingEtagReturns304WithoutBody() throws Exception {
    mockMvc.perform(get("/api/products/prod-42")
            .header(HttpHeaders.IF_NONE_MATCH, "\"product-prod-42-v7\""))
        .andExpect(status().isNotModified())
        .andExpect(header().string(
                HttpHeaders.ETAG, "\"product-prod-42-v7\""))
        .andExpect(content().string(""));
}

@Test
void oldEtagReturns200WithBody() throws Exception {
    mockMvc.perform(get("/api/products/prod-42")
            .header(HttpHeaders.IF_NONE_MATCH, "\"product-prod-42-v6\""))
        .andExpect(status().isOk())
        .andExpect(header().string(
                HttpHeaders.ETAG, "\"product-prod-42-v7\""))
        .andExpect(content().json("""
            {"id":"prod-42","name":"Sổ tay","price":45000}
            """));
}

@Test
void conditionalHeadHasNoBody() throws Exception {
    mockMvc.perform(head("/api/products/prod-42")
            .header(HttpHeaders.IF_NONE_MATCH, "\"product-prod-42-v7\""))
        .andExpect(status().isNotModified())
        .andExpect(content().string(""));
}
~~~

**Đây là test fragment**, không phải toàn bộ lớp có thể chạy độc lập. Để chạy, cần tạo WebMvc/Spring Boot test context, inject mockMvc, stub ProductReader và cấp principal/token có quyền đọc. Nếu security filter chặn request trước khi tới controller, kết quả có thể là 401; không nên tắt bảo mật ở production chỉ để test 304.

### 14.4. Kiểm thử tình huống thay đổi nhanh

Một lỗi khó phát hiện:

1. Ghi giá 45.000 lúc 10:00:00.100 và trả ETag v7, Last-Modified 10:00:00 GMT.
2. Ghi giá 49.000 lúc 10:00:00.800, ETag đổi v8 nhưng Last-Modified vẫn 10:00:00 GMT.
3. Client gửi cả If-None-Match: "v7" và If-Modified-Since: 10:00:00 GMT.

**Kỳ vọng:** 200 với giá mới vì If-None-Match không khớp và được ưu tiên. Nếu code so sánh ngày trước, nó có thể trả 304 sai.

Test nên xác định snapshot/clock thay vì dùng Thread.sleep phụ thuộc thời gian thực; sử dụng dữ liệu/clock được kiểm soát để tạo hai phiên bản trong cùng một giây.

### 14.5. Kiểm thử bảo mật và biến thể

- Cùng ETag nhưng caller không còn quyền → không nhận 304.
- Tenant A và B không trộn bản cache dù URI/path tương tự hoặc proxy normalize query.
- Accept-Language và Content-Encoding khác nhau → body/ETag/Vary tương ứng.
- Query fields/expand khác nhau → ETag phản ánh nội dung đúng.
- Sau xóa/ẩn resource, request If-None-Match cũ → phản hồi trạng thái truy cập hiện tại.
- Khi CDN trả từ cache, Vary và Cache-Control vẫn được thực hiện đúng.

Đây là các trường hợp cần **integration test qua hạ tầng tương đương production**, không chỉ MockMvc gọi controller.

## 15. Đo lợi ích và chi phí của conditional GET

Không nên đưa ETag vào mọi endpoint mà không có mục tiêu. Với một API danh mục có response trung bình 50 KB:

- 10.000 lần tải lại body 50 KB tạo khoảng **500 MB dữ liệu body** (theo đơn vị thập phân, chưa tính header/giao thức).
- Nếu 80% số lần revalidation thực sự không đổi và client/cache đã có body phù hợp, server có thể tránh gửi body cho khoảng 8.000 request.
- Mức tiết kiệm lý thuyết riêng phần body là khoảng **400 MB** trong ví dụ này, nhưng thực tế còn phụ thuộc số request có cache, compression, proxy, mức thay đổi và chi phí truyền khác.

Đây là **ví dụ tính toán**, không phải số đo production. Cần đo các chỉ số sau:

| Metric | Dùng để trả lời câu hỏi |
|---|---|
| **304 / conditional GET count** | Có bao nhiêu request được revalidate thành công? |
| **200 sau conditional GET** | Có bao nhiêu representation thực sự thay đổi hoặc validator không khớp? |
| **Cache hit / miss / revalidation tại edge** | CDN có phục vụ từ cache hay luôn tới origin? |
| **Response bytes / egress** | Lượng dữ liệu có thực sự giảm? |
| **Origin CPU, DB queries, serialization time** | Kiểm tra validator có tránh được xử lý tốn kém? |
| **p50/p95/p99 end-to-end latency** | Client có nhanh hơn hay vẫn chờ round trip như cũ? |
| **Validator computation latency** | Tính hash/version có tạo bottleneck mới? |
| **4xx/5xx theo query và authorization** | Có trả nhầm 304, lộ dữ liệu hoặc tạo vòng retry? |

### 15.1. Tỷ lệ 304 cao không tự chứng minh tối ưu

Một hệ thống có tỷ lệ 304 cao nhưng vẫn chạy query 200 ms và hash JSON lớn cho mỗi request có thể tiết kiệm băng thông nhưng không tiết kiệm nhiều CPU/DB. Một CDN có freshness phù hợp có thể trả 200 từ edge mà **không chạm origin**, hữu ích hơn việc origin phải phục vụ mọi lần conditional GET.

Do đó đánh giá **tổng chi phí mỗi lần đọc thành công, độ trễ và tính đúng của dữ liệu**, không tối đa hóa riêng tỷ lệ 304.

### 15.2. Mức độ nhất quán của validator

Với nhiều app instance sau load balancer, mọi instance phải sinh validator nhất quán cho **cùng một representation**. Không dùng biến ngẫu nhiên, local deployment timestamp hoặc thứ tự serialize không ổn định để tạo strong ETag nếu các instance có thể trả bytes khác nhau.

Nếu một node đọc từ replica chậm và phát ETag của bản cũ sau khi client đã thấy bản mới, người dùng có thể nhận dữ liệu lùi phiên bản. Cần đánh giá consistency của read model/cache, định tuyến và cách tính version, nhất là khi API dùng Last-Modified hoặc ETag để đưa ra quyết định 304.

## 16. Những sai lầm thường gặp

| Sai lầm | Hậu quả | Cách xử lý |
|---|---|---|
| Coi ETag là cache TTL | Dùng bản stale hoặc revalidate sai | Tách validator và Cache-Control |
| Dùng no-cache như đồng nghĩa no-store | Hiểu sai private cache có thể lưu response | Chọn directive theo chính sách lưu và độ mới |
| Tự so chuỗi If-None-Match bằng equals | Bỏ sót weak tag, list, dấu sao | Dùng xử lý điều kiện của HTTP framework |
| Ưu tiên If-Modified-Since khi cả hai có mặt | Có thể trả 304 sai sau cập nhật trong cùng giây | If-None-Match có ưu tiên |
| Sinh Last-Modified chỉ từ createdAt | Không phát hiện update | Dùng mốc sửa representation hoặc không gửi |
| Coi timestamp mili giây giống HTTP-date | Không nhận ra nhiều update trong cùng giây | ETag chính xác, làm tròn và test |
| Dùng một strong ETag cho nội dung gzip và identity khác bytes | Sai ngữ nghĩa strong validator | Tạo đúng validator theo selected representation |
| Tạo ETag chỉ từ version row dù expand đổi | Client dùng body cũ | Version/hash phải bao quát representation |
| Trả 304 trước khi kiểm tra quyền | Lộ tồn tại, dùng lại dữ liệu bị cấm | Kiểm tra auth/tenant/ACL trước |
| Trả 304 cho resource đã xóa | Client giữ representation không còn đúng | Đánh giá lifecycle, 404/410 theo hợp đồng |
| Trả JSON body với status 304 | Sai ngữ nghĩa giao thức | 304 chỉ có các header phù hợp |
| Trả 304 cho PUT thất bại precondition | Lẫn yêu cầu đọc với ghi | Dùng 412 và kiểm tra version nguyên tử |
| Bật cache public cho đơn hàng riêng tư | Nguy cơ rò rỉ dữ liệu qua shared cache | private/no-store theo phân loại |
| Không xét Vary hoặc query shape | Cache trả sai ngôn ngữ/fields/expand | Thiết kế key/validator theo variant |
| Dùng shallow ETag và cho rằng DB không còn query | Không giảm tải gốc, có thể buffer lớn | Đo DB/CPU và tối ưu version/query |
| Mọi client tự gửi If-None-Match dù không có body cũ | Nhận 304 mà không thể hiển thị gì | Chỉ revalidate khi có bản được phép tái sử dụng |
| Không thử qua CDN/proxy thực | Kết quả khác production | Integration test các cache layer |

## 17. Bài tập thực hành và đáp án gợi ý

### Bài 1 — Chọn 200 hay 304

Server có ETag hiện tại "article-v8". Client gửi:

~~~http
GET /api/articles/42 HTTP/1.1
If-None-Match: "article-v7"
~~~

**Câu hỏi:** Trả status nào nếu tài nguyên tồn tại và caller có quyền? Nếu tag client là "article-v8" thì sao?

**Gợi ý:** Với v7 không khớp → 200 và body v8. Với v8 khớp → 304, không có body, gửi header revalidation phù hợp.

### Bài 2 — Strong và weak comparison

Server phát:

~~~http
ETag: W/"product-v9"
~~~

Client đọc gửi:

~~~http
If-None-Match: "product-v9"
~~~

**Câu hỏi:** Có khớp không? Nếu client dùng If-Match: "product-v9" cho một thao tác ghi thì sao?

**Gợi ý:** If-None-Match dùng **weak comparison** nên khớp nếu opaque tag giống nhau. If-Match dùng **strong comparison**, một ETag hiện tại weak không thể khớp strong theo quy tắc đó; điều kiện ghi không đạt.

### Bài 3 — Hai điều kiện cùng xuất hiện

Server có ETag "v12" và Last-Modified bằng Wed, 18 Nov 2026 10:00:00 GMT. Client gửi:

~~~http
GET /api/products/42 HTTP/1.1
If-None-Match: "v11"
If-Modified-Since: Wed, 18 Nov 2026 10:00:00 GMT
~~~

**Câu hỏi:** Trả 304 hay 200?

**Đáp án:** 200 nếu resource hợp lệ và được phép đọc. If-None-Match có mặt và **không khớp**, nên server bỏ qua If-Modified-Since; không dùng timestamp trùng để trả 304.

### Bài 4 — Dữ liệu thay đổi trong cùng giây

Một API cập nhật giá từ 45.000 thành 49.000 trong cùng giây. Last-Modified theo HTTP-date không đổi, nhưng database version tăng từ 10 lên 11.

**Câu hỏi:** Nên phát validator nào để phân biệt hai representation? Cần kiểm tra gì?

**Gợi ý:** ETag chính xác dựa trên version 10/11 hoặc nội dung, bảo đảm mỗi thay đổi body quan trọng làm đổi ETag. Kiểm tra body và version được lấy từ cùng trạng thái; nếu giá được tính từ nguồn khác, version cần bao phủ nguồn đó.

### Bài 5 — no-cache và no-store

Hai endpoint:

1. Danh mục công khai, thay đổi theo giờ.
2. Hồ sơ thanh toán nhạy cảm, không được phép lưu trên client/cache.

**Câu hỏi:** Nên chọn chính sách nào? ETag có luôn tạo lợi ích?

**Gợi ý:** Danh mục có thể dùng public,max-age ngắn và ETag để revalidate khi stale. Hồ sơ nhạy cảm có thể dùng no-store, khiến HTTP cache không lưu body để tận dụng 304; ETag không tự đem lại lợi ích cache cho trường hợp này.

### Bài 6 — Bỏ sót quyền với conditional GET

Người dùng A từng xem đơn 42 và có ETag "order-v5". Hôm sau quyền bị thu hồi, nhưng client vẫn gửi If-None-Match: "order-v5".

**Câu hỏi:** Trả 304 được không?

**Đáp án:** Không. Authorization phải xét quyền hiện tại; trả 403 hoặc 404 che giấu theo chính sách, không xác nhận lại representation bị cấm chỉ vì ETag khớp.

### Bài 7 — Variant theo ngôn ngữ

Hai client cùng GET /api/articles/42 nhưng một client yêu cầu tiếng Việt, client còn lại tiếng Anh. Nội dung khác nhau nhưng server dùng cùng strong ETag "v8" và cache không có Vary.

**Câu hỏi:** Rủi ro là gì và cách sửa?

**Gợi ý:** Cache có thể nhận nhầm representation, còn strong ETag không phân biệt body khác nhau. Thêm Vary: Accept-Language và xây validator đúng variant hoặc một chiến lược representation/URL rõ ràng; kiểm thử hai ngôn ngữ qua cache thật.

### Bài 8 — Đánh giá hiệu năng

Sau khi bật ShallowEtagHeaderFilter, tỷ lệ 304 tăng 70% nhưng SQL count và p95 ở origin gần như không đổi.

**Câu hỏi:** Đây có phải thất bại hoàn toàn không? Cần đo thêm gì?

**Gợi ý:** Không hẳn. Có thể tiết kiệm body bytes/băng thông nhưng vẫn thực thi DB/serialization. Đo egress, response bytes, client latency, CPU, memory/buffering và giá trị tài nguyên; cân nhắc validator rẻ từ version/read model hoặc TTL cache thích hợp.

## 18. Checklist trước khi triển khai caching có điều kiện

- [ ] Có xác định tài nguyên và **selected representation** mà ETag/Last-Modified xác nhận?
- [ ] ETag hợp lệ, được coi là opaque và có chính sách strong/weak rõ ràng?
- [ ] Mọi thay đổi ảnh hưởng body đều làm thay validator hoặc làm điều kiện revalidation không khớp?
- [ ] Last-Modified phản ánh representation, không mặc định là createdAt hoặc timestamp của một row không liên quan?
- [ ] Có xét độ phân giải theo giây, cập nhật liên tiếp, clock skew và read replica?
- [ ] If-None-Match được đánh giá theo weak comparison và hỗ trợ danh sách/tag sao?
- [ ] If-None-Match được ưu tiên hơn If-Modified-Since khi cả hai tồn tại?
- [ ] 304 chỉ được trả cho GET/HEAD phù hợp, không có body và giữ header cache cần thiết?
- [ ] 200 trả representation đúng với ETag/Last-Modified của cùng một trạng thái dữ liệu?
- [ ] Không trả 304 trước khi kiểm tra authentication, authorization, tenant và trạng thái resource?
- [ ] Resource bị ẩn/xóa và lỗi DB có status phù hợp, không tự biến thành 304?
- [ ] Có phân biệt no-cache, no-store, private, public, max-age, s-maxage và must-revalidate?
- [ ] Cache keys, Vary và validator đúng với Accept, Accept-Language, Content-Encoding, query fields/expand?
- [ ] Không chia sẻ nhầm representation riêng tư giữa các tenant/người dùng?
- [ ] Spring dùng cơ chế điều kiện HTTP có kiểm thử, không chỉ so ETag bằng chuỗi thô?
- [ ] Có hợp đồng OpenAPI cho 200/304, các conditional request headers và lỗi 401/403/404?
- [ ] Đã thử GET, HEAD, weak tag, tag list, wildcard, Last-Modified, hai điều kiện cùng lúc và update trong cùng giây?
- [ ] Đã thử trên client/SDK, gateway/CDN và nhiều node thực tế?
- [ ] Đo băng thông, cache hit, origin CPU/DB, serialization, memory và p95/p99 thay vì chỉ tỷ lệ 304?

## 19. Kết luận

**ETag** và **Last-Modified** là validator để xác định representation đã thay đổi hay chưa. Client dùng **If-None-Match** hoặc **If-Modified-Since** trong GET/HEAD để revalidate; server trả **304 Not Modified không có body** khi điều kiện phù hợp, hoặc **200 OK với representation mới** khi cần tải lại.

Trong thiết kế REST API, phần khó không nằm ở việc thêm hai header. Đó là bảo đảm validator **đúng với representation, quyền, biến thể nội dung và vòng đời tài nguyên**, hiểu **thứ tự ưu tiên điều kiện**, phối hợp chính xác với **Cache-Control/Vary**, và kiểm thử cả Java/Spring lẫn cache trung gian. Chỉ khi kết hợp được tính đúng, bảo mật và phép đo hiệu năng, conditional GET mới thực sự giúp giảm tải và cải thiện trải nghiệm đọc tài nguyên.
