# PATCH không mặc định có tính lũy đẳng

## 1. Vấn đề: cùng một PATCH được gửi hai lần thì điều gì xảy ra?

Giả sử ứng dụng quản lý kho có sản phẩm P-100 với số lượng tồn là 10. Một thiết bị gửi yêu cầu **PATCH tăng tồn kho thêm 3**; máy chủ xử lý thành công nhưng kết nối bị ngắt trước khi phản hồi đến thiết bị. Thiết bị không biết cập nhật đã được lưu hay chưa và gửi lại cùng yêu cầu.

- Nếu PATCH có nghĩa **“đặt tồn kho bằng 13”**, gửi hai lần thường vẫn cho kết quả 13.
- Nếu PATCH có nghĩa **“cộng thêm 3 vào tồn kho”**, gửi hai lần có thể đưa số lượng lên 16.

Đây là khác biệt giữa thao tác **đặt trạng thái** và thao tác **tăng trạng thái**. Trong thiết kế **INTEGRATION_API_REST**, khác biệt này ảnh hưởng trực tiếp đến hợp đồng API, cách HTTP client retry, độ đúng đắn dữ liệu, xử lý lỗi, kiểm thử và cách triển khai bằng Java/Spring.

**PATCH là phương thức dùng để yêu cầu chỉnh sửa một phần tài nguyên. Theo ngữ nghĩa HTTP, PATCH không mặc định là phương thức lũy đẳng (idempotent), dù từng yêu cầu PATCH cụ thể hoàn toàn có thể được thiết kế lũy đẳng.**

### Kết quả học tập

Sau bài học, bạn có thể:

1. Giải thích tính lũy đẳng của HTTP và phân biệt nó với safe method, cùng mã trạng thái hoặc cùng response.
2. Phân tích PATCH nào lũy đẳng, PATCH nào không, dựa trên **ý nghĩa phép cập nhật** thay vì chỉ nhìn tên phương thức.
3. So sánh JSON Patch, JSON Merge Patch và patch document tùy biến, đặc biệt ở thao tác **replace**, **add** và **increment**.
4. Sử dụng ETag và **If-Match** để tránh ghi đè cập nhật đồng thời; hiểu giới hạn của conditional request đối với retry.
5. Thiết kế idempotency key khi cần chống thực thi trùng một lệnh có tác dụng cộng dồn.
6. Định nghĩa mã lỗi, hợp đồng OpenAPI, chiến lược retry và kiểm thử cho PATCH trong API REST.

## 2. Lũy đẳng trong HTTP nghĩa là gì?

Một thao tác là **lũy đẳng** nếu thực hiện nó nhiều lần với cùng tham số có **tác động dự định lên trạng thái máy chủ tương đương việc thực hiện một lần**. Có thể diễn đạt đối với phép biến đổi trạng thái F:

\[
F(F(s)) = F(s)
\]

Đây là mô hình toán học hỗ trợ tư duy. Trong HTTP, cần xét **tác động dự định của phương thức và ngữ nghĩa yêu cầu**, không đòi hỏi byte của mọi phản hồi hoặc mọi dấu vết hệ thống hoàn toàn giống nhau.

Ví dụ:

- **Đặt trạng thái:** F(s) = 13. Làm một hoặc nhiều lần đều đặt giá trị là 13.
- **Tăng giá trị:** F(s) = s + 3. Làm một lần được 13, hai lần được 16: không lũy đẳng.
- **Xóa tài nguyên:** Xóa một lần hoặc yêu cầu xóa lại có thể khiến tài nguyên tiếp tục vắng mặt. Phản hồi đầu có thể là 204, lần sau 404; mã phản hồi khác nhau không phủ nhận tính lũy đẳng của **DELETE**.

### 2.1. Đừng nhầm lũy đẳng với an toàn

Phương thức **safe** là phương thức mà client không yêu cầu thay đổi trạng thái của tài nguyên theo ngữ nghĩa phương thức. Một phương thức **idempotent** vẫn có thể thay đổi tài nguyên, miễn là việc lặp lại không gây thêm tác động dự định so với một lần.

| Phương thức | Safe theo ngữ nghĩa HTTP? | Idempotent theo ngữ nghĩa HTTP? | Ghi chú |
|---|---|---|---|
| GET | Có | Có | Lấy biểu diễn tài nguyên; không dùng GET để kích hoạt cập nhật nghiệp vụ |
| HEAD | Có | Có | Như GET về mục đích, không trả response body |
| OPTIONS | Có | Có | Hỏi khả năng giao tiếp với tài nguyên |
| PUT | Không | Có | Thay thế hoặc tạo trạng thái tài nguyên theo nội dung yêu cầu |
| DELETE | Không | Có | Yêu cầu xóa liên kết tài nguyên; có thể trả mã khác khi lặp |
| POST | Không | Không mặc định | Có thể thiết kế idempotent cho từng API cụ thể |
| **PATCH** | **Không** | **Không mặc định** | Tùy ngữ nghĩa patch document và triển khai |

Đừng dùng tính idempotent để suy luận rằng **không có bất kỳ log hay audit nào được sinh thêm**. Server có thể ghi nhận từng lần nhận request. Cần phân biệt hiệu ứng phụ mang tính quan sát/vận hành với **tác động nghiệp vụ mà client yêu cầu**, chẳng hạn trừ tiền, tăng điểm, gửi lệnh tạo đơn hoặc phát sự kiện bên ngoài.

### 2.2. Vì sao idempotency quan trọng khi mạng không đáng tin cậy?

Trong hệ phân tán, client có thể gặp timeout mặc dù server đã ghi thành công:

~~~mermaid
sequenceDiagram
    participant C as HTTP Client
    participant S as REST API
    participant D as Database
    C->>S: PATCH tăng tồn +3
    S->>D: Cập nhật 10 thành 13
    D-->>S: Commit thành công
    Note over S,C: Kết nối mất trước khi response tới client
    C->>S: Retry cùng PATCH
    S->>D: Nếu tăng tiếp, 13 thành 16
    S-->>C: 200 OK
~~~

Client **không thể suy từ timeout** rằng server chưa thực hiện request. Vì PATCH không mặc định lũy đẳng, các HTTP client và thư viện retry **không nên tự động lặp lại một PATCH bất kỳ** khi không biết cơ chế bảo đảm an toàn. Retry có thể hợp lệ nếu hợp đồng PATCH cụ thể bảo đảm lũy đẳng hoặc có cơ chế chống xử lý trùng được thiết kế rõ.

## 3. PATCH làm gì theo HTTP?

Theo **RFC 5789**, PATCH áp dụng một tập chỉ dẫn chỉnh sửa tới tài nguyên được xác định bởi request URI; nó khác PUT ở chỗ nội dung request thường là **tài liệu mô tả thay đổi**, không phải toàn bộ biểu diễn thay thế của tài nguyên.

Ví dụ có tài nguyên:

~~~json
{
  "id": "P-100",
  "name": "Bút bi",
  "price": 12000,
  "stock": 10,
  "tags": ["office"]
}
~~~

Một PATCH có thể yêu cầu đổi tên, đổi giá, bổ sung phần tử mảng hoặc tăng tồn kho. **Không thể biết PATCH có lũy đẳng hay không chỉ bằng URI /products/P-100.** Phải xem **Content-Type**, định dạng tài liệu cập nhật và quy tắc của API.

### 3.1. Những yêu cầu quan trọng của PATCH

- **Không safe:** PATCH dự định chỉnh sửa tài nguyên.
- **Không mặc định idempotent:** server chỉ có thể bảo đảm nếu tài liệu cập nhật và logic xử lý được thiết kế phù hợp.
- **Atomic ở mức áp dụng tài liệu patch:** theo RFC 5789, server phải áp dụng toàn bộ tập thay đổi atomically; nếu không áp dụng được toàn bộ, không để tài nguyên ở trạng thái đã sửa một phần.
- **Điều kiện và xung đột:** client có thể gửi **If-Match** với strong ETag để tránh áp dụng thay đổi trên phiên bản ngoài dự kiến.
- **Media type quyết định cách diễn giải:** JSON Patch, JSON Merge Patch và định dạng tùy biến có semantics khác nhau.
- **Khả năng hỗ trợ:** server có thể quảng bá định dạng patch trong header **Accept-Patch** (ví dụ ở phản hồi OPTIONS).

**Atomicity của một patch document không đồng nghĩa với idempotency.** Một yêu cầu tăng giá trị có thể được thực thi atomically nhưng vẫn làm tăng hai lần khi client gửi lại.

### 3.2. Các dạng patch document cần phân biệt

| Định dạng | Content-Type | Ý tưởng chính |
|---|---|---|
| JSON Patch | application/json-patch+json | Danh sách phép toán theo đường dẫn JSON Pointer: add, remove, replace, move, copy, test |
| JSON Merge Patch | application/merge-patch+json | Đưa object mô tả các trường cần thay đổi; null có nghĩa xóa trường theo định dạng này |
| Tùy biến theo API | Ví dụ application/json | API tự định nghĩa các lệnh như increment, append, activate; phải tài liệu hóa semantics |

**JSON Patch không có toán tử increment chuẩn.** Một payload chứa op = increment là định dạng riêng của ứng dụng, không phải JSON Patch chuẩn theo RFC 6902. Chọn Content-Type chính xác giúp client và server diễn giải payload thống nhất.

## 4. PATCH có thể lũy đẳng: cập nhật theo giá trị tuyệt đối

### 4.1. JSON Merge Patch đặt một giá trị cố định

~~~http
PATCH /products/P-100 HTTP/1.1
Host: api.example.test
Content-Type: application/merge-patch+json

{
  "price": 15000
}
~~~

Nếu server thực hiện đúng ngữ nghĩa Merge Patch đối với trường **price**, yêu cầu này có nghĩa **đặt giá bằng 15.000**. Với trạng thái ban đầu giá là 12.000:

| Số lần áp dụng | Price sau khi áp dụng |
|---|---:|
| Ban đầu | 12.000 |
| Lần 1 | 15.000 |
| Lần 2 | 15.000 |
| Lần 3 | 15.000 |

Đây là **yêu cầu PATCH lũy đẳng xét theo trạng thái price** nếu không có logic bổ sung làm thay đổi hiệu ứng dự định mỗi lần áp dụng.

Đối với Merge Patch, payload như sau:

~~~http
PATCH /profiles/u-7 HTTP/1.1
Content-Type: application/merge-patch+json

{"displayName": "Lan", "nickname": null}
~~~

Thường có nghĩa **đặt displayName = Lan, xóa trường nickname**; áp dụng lại cùng patch trên cùng trạng thái thường không thay đổi thêm gì. Nhưng **null không biểu thị “đặt giá trị JSON null”** trong cấu trúc object Merge Patch; nó yêu cầu xóa member. Nếu API cần phân biệt xóa trường với ghi giá trị null, cần chọn contract/định dạng phù hợp.

### 4.2. JSON Patch thay thế trường cố định

~~~http
PATCH /products/P-100 HTTP/1.1
Content-Type: application/json-patch+json

[
  {"op": "replace", "path": "/price", "value": 15000}
]
~~~

Khi path **/price** tồn tại và logic cập nhật không tạo tác động nghiệp vụ mới mỗi lần, lặp lại phép **replace** với cùng giá trị dẫn đến cùng trạng thái. Cần nhớ JSON Patch **replace** yêu cầu đường dẫn đích tồn tại; nếu bị người khác xóa hoặc schema thay đổi, thao tác có thể lỗi.

**Điều kiện quan trọng:** “Đặt giá trị cố định” không tự bảo đảm mọi tác động nghiệp vụ đều lũy đẳng. Ví dụ nếu mỗi lần PATCH cùng giá hệ thống vẫn **phát lệnh thu phí mới** hoặc **tăng một bộ đếm nghiệp vụ**, API đã có hiệu ứng cộng dồn. Các workflow liên quan phải được thiết kế để tránh trùng tác động ngoài ý muốn.

## 5. PATCH không lũy đẳng: tăng, append và những phép toán phụ thuộc trạng thái

### 5.1. Lệnh tăng số lượng

Giả sử API tự định nghĩa cách cập nhật lượng tồn:

~~~http
PATCH /products/P-100/stock HTTP/1.1
Content-Type: application/json

{
  "operation": "increment",
  "amount": 3
}
~~~

Giả sử trạng thái ban đầu là 10 và mỗi request đều được chấp nhận:

| Thời điểm | Stock |
|---|---:|
| Ban đầu | 10 |
| Sau PATCH đầu tiên | 13 |
| Sau retry y hệt | 16 |
| Sau retry lần nữa | 19 |

Đây là **PATCH không lũy đẳng**. Một lần và ba lần thực hiện có tác động nghiệp vụ khác nhau.

Phép toán tăng tồn kho không sai về mặt nghiệp vụ, nhưng API phải công bố rõ nó **là lệnh tăng chứ không phải đặt giá trị**. Cần hợp đồng chống xử lý trùng nếu client có khả năng retry sau timeout.

### 5.2. JSON Patch append vào mảng

~~~http
PATCH /products/P-100 HTTP/1.1
Content-Type: application/json-patch+json

[
  {"op": "add", "path": "/tags/-", "value": "sale"}
]
~~~

Trong JSON Patch, dấu **-** ở cuối JSON Pointer trên một mảng biểu thị **thêm vào cuối mảng**. Nếu tags ban đầu là:

~~~json
["office"]
~~~

Sau lần đầu:

~~~json
["office", "sale"]
~~~

Sau lần hai:

~~~json
["office", "sale", "sale"]
~~~

Vì mảng JSON cho phép phần tử trùng, append vào cuối mảng có thể không lũy đẳng. Ngược lại, thao tác JSON Patch **add** vào một member object đã có khóa thường thay thế giá trị ở khóa đó; **không thể kết luận mọi op = add đều không lũy đẳng** nếu không xét loại đích và vị trí.

### 5.3. Các phép toán khác cần chú ý

| Chỉ dẫn / cách xử lý | Lặp lại có thể xảy ra gì? | Kết luận khi chưa biết contract |
|---|---|---|
| replace /price thành 15000 | Cùng giá trị nếu path còn tồn tại | Thường lũy đẳng theo trạng thái tài nguyên |
| add /tags/- “sale” | Thêm phần tử lần nữa | Thường không lũy đẳng |
| add /metadata/owner “team-a” | Ghi/ghi đè cùng thuộc tính | Có thể lũy đẳng |
| remove /nickname | Lần đầu xóa, lần sau có thể lỗi vì path không còn | Phản hồi có thể khác; cần xét tác động dự định |
| move /tasks/0 sang /tasks/2 | Thứ tự mảng sau lần đầu khác; lần hai tác động lên vị trí mới | Không được mặc định lũy đẳng |
| test /version rồi replace | Nếu version đã đổi, lần sau có thể thất bại | Có thể tránh cập nhật trùng, nhưng phụ thuộc trạng thái |
| Custom increment +3 | Cộng thêm mỗi lần | Không lũy đẳng khi được áp dụng nhiều lần |
| Custom set stock = 13 | Đặt cùng giá trị | Thường lũy đẳng nếu không có side effect cộng dồn |

**Lũy đẳng không đồng nghĩa lần retry luôn thành công với cùng HTTP status.** Nếu lần thứ hai bị từ chối do precondition hoặc đường dẫn không còn tồn tại, phải đánh giá **tác động lên tài nguyên** và ngữ nghĩa thao tác, thay vì so sánh mã 200/204/404/412 đơn thuần.

## 6. Cập nhật đồng thời: If-Match và strong ETag

Tính lũy đẳng và **tránh ghi đè cập nhật của người khác (lost update)** là hai vấn đề liên quan nhưng khác nhau.

Giả sử cả hai client đọc sản phẩm lúc giá = 12.000 và nhận ETag **"product-v7"**. Client A muốn đặt giá 15.000, client B muốn đặt giá 14.000. Nếu cả hai gửi PATCH mà không có điều kiện, request đến sau có thể ghi đè request trước mà không nhận biết.

### 6.1. Chuỗi cập nhật có điều kiện

~~~mermaid
sequenceDiagram
    participant A as Client A
    participant B as Client B
    participant S as API / Database
    A->>S: GET /products/P-100
    S-->>A: 200 OK, ETag "product-v7"
    B->>S: GET /products/P-100
    S-->>B: 200 OK, ETag "product-v7"
    A->>S: PATCH price=15000, If-Match "product-v7"
    S-->>A: 200 OK, ETag "product-v8"
    B->>S: PATCH price=14000, If-Match "product-v7"
    S-->>B: 412 Precondition Failed
~~~

Yêu cầu của A:

~~~http
PATCH /products/P-100 HTTP/1.1
Content-Type: application/merge-patch+json
If-Match: "product-v7"

{"price": 15000}
~~~

Máy chủ chỉ áp dụng nếu **strong validator** hiện tại khớp **If-Match**. Sau khi cập nhật, representation có ETag mới, ví dụ **"product-v8"**. B tiếp tục gửi ETag cũ nên server trả **412 Precondition Failed**, không áp dụng PATCH của B.

Hệ thống phải thực hiện kiểm tra phiên bản và ghi dữ liệu **một cách nguyên tử** hoặc dùng optimistic concurrency control (ví dụ version column + compare-and-swap/transaction). Chỉ đọc ETag trước rồi cập nhật ở bước khác không có khóa/điều kiện đồng thời vẫn có race condition.

### 6.2. If-Match có làm PATCH “idempotent” không?

**If-Match có thể ngăn cùng thay đổi áp dụng nhiều lần trên một phiên bản**:

- Lần 1: ETag v7 khớp, PATCH được áp dụng, tài nguyên sang v8.
- Retry cùng yêu cầu chứa If-Match v7: ETag không còn khớp, server trả 412, không thay đổi thêm.

Tuy nhiên, **412 không chứng minh lần PATCH trước của chính client đã thành công**. Một client khác cũng có thể đã sửa tài nguyên giữa hai lần gửi. Khi nhận 412 sau timeout, client cần lấy lại tài nguyên, kiểm tra trạng thái nghiệp vụ hoặc dùng cơ chế idempotency key nếu muốn truy xuất kết quả thực hiện trước đó.

**If-Match giải quyết điều kiện trên phiên bản tài nguyên. Idempotency key giải quyết nhận diện một yêu cầu nghiệp vụ bị gửi lại.** Hai cơ chế có thể kết hợp khi cần.

### 6.3. Những chú ý với ETag

- **ETag** là opaque validator: client không tự suy diễn cách tính, không sửa chuỗi trong dấu ngoặc kép.
- **If-Match** sử dụng phép so sánh strong ETag; weak ETag như **W/"product-v7"** không phù hợp để bảo vệ PATCH đòi hỏi so khớp mạnh.
- Strong ETag phải đại diện nhất quán cho phiên bản biểu diễn đã chọn; version column chỉ phù hợp nếu mọi thay đổi liên quan đến biểu diễn khiến validator được đổi đúng.
- Nếu API **bắt buộc** client gửi precondition, có thể trả **428 Precondition Required** khi thiếu.
- Không dùng header **If-None-Match** như thay thế trực tiếp cho kiểm tra cập nhật đồng thời bằng **If-Match**.

## 7. Idempotency key cho PATCH có hiệu ứng cộng dồn

Khi API buộc phải hỗ trợ lệnh như tăng stock, cộng credit hoặc gửi lại giao dịch nghiệp vụ, một giải pháp là cho client gửi **một khóa nhận diện thao tác logic**. Ví dụ header **Idempotency-Key**, nếu được API hỗ trợ và được tài liệu hóa:

~~~http
PATCH /products/P-100/stock HTTP/1.1
Content-Type: application/json
Idempotency-Key: 7794f08e-2b2a-438b-a2e7-90ac0f1889a4

{"operation": "increment", "amount": 3}
~~~

Client dùng **cùng key cho retry của cùng thao tác**, dùng key mới nếu người dùng thực sự muốn cộng thêm 3 lần thứ hai.

### 7.1. Thiết kế server-side deduplication

Một triển khai cần tính đến:

1. **Phạm vi key:** thường gắn với tenant hoặc principal, phương thức, URI/ngữ nghĩa thao tác; tránh cho hai người dùng vô tình dùng chung một key và chặn lẫn nhau.
2. **Fingerprint request:** lưu hash payload được chuẩn hóa phù hợp cùng tham số có ảnh hưởng đến nghiệp vụ; nếu cùng key nhưng payload khác, trả lỗi theo hợp đồng.
3. **Trạng thái xử lý:** phân biệt request chưa có, đang xử lý, đã hoàn thành và đã thất bại; xử lý trường hợp hai request cùng key đến đồng thời.
4. **Nguyên tử:** ghi nhận key và hiệu ứng dữ liệu trong một transaction nếu cùng database; dùng outbox/transactional workflow nếu cần phát sự kiện hoặc gọi hệ thống ngoài.
5. **Kết quả:** có thể lưu HTTP status và response/body để trả lại nhất quán cho retry, hoặc cung cấp endpoint truy vấn kết quả.
6. **Thời hạn giữ key:** công bố TTL, phạm vi lưu, giới hạn và cách xử lý retry sau TTL.
7. **Bảo mật:** khóa là mã nhận diện request, không phải chứng thực; vẫn phải xác thực, phân quyền và chống đoán/chiếm key xuyên tenant.

Luồng giả mã:

~~~text
scope = (authenticatedTenant, HTTPMethod, canonicalResource)
fingerprint = hash(meaningfulRequestParameters)

begin transaction
    try insert (scope, idempotencyKey, fingerprint, state=IN_PROGRESS)

    if key already exists:
        if existing.fingerprint differs: reject as key reuse
        if existing.state == COMPLETED: return saved result
        else: return or wait per documented concurrency policy

    update product stock atomically (+3)
    save response and mark key COMPLETED
commit transaction

return saved response
~~~

Pseudocode chỉ mô tả logic; một triển khai thật phải bảo đảm thao tác tranh chấp cùng key không cùng đi qua nhánh cập nhật, transaction rollback nếu lỗi và lưu kết quả phù hợp. Với lệnh liên quan thanh toán hoặc đối tác ngoài, **không thể tuyên bố exactly-once end-to-end** chỉ vì đã tạo bảng key. Cần kết hợp idempotency tại hệ thống đích, outbox, correlation ID và đối soát.

### 7.2. Nếu vừa có If-Match vừa có Idempotency-Key

- **If-Match:** bảo đảm patch chỉ áp dụng trên phiên bản dữ liệu được client chấp nhận.
- **Idempotency-Key:** nhận diện request logic, giúp tránh thực hiện lệnh có tác dụng cộng dồn thêm lần nữa khi retry.
- **Authorization:** quyết định client có quyền thay đổi tài nguyên hay không.
- **Transaction/outbox:** giúp hiệu ứng dữ liệu và thông điệp sự kiện không rơi vào trạng thái nửa vời.

Trong thực tế thứ tự kiểm tra cần được thiết kế cẩn thận: một retry có key đã hoàn thành có thể cần **trả lại kết quả đã lưu** ngay cả khi ETag hiện tại đã đổi; đồng thời vẫn phải xác minh principal/tenant hợp lệ. Nếu xử lý precondition trước deduplication, server có thể trả 412 thay vì kết quả ban đầu. Cần **ghi rõ contract** và kiểm thử quyết định này.

## 8. Hợp đồng HTTP cho PATCH: status, header và retry

Một REST API tốt phải thể hiện rõ **resource URI, Content-Type, precondition, kết quả và lỗi**. Đừng để client đoán một PATCH có phải thao tác gán giá trị, phép cộng hay lệnh kích hoạt workflow.

### 8.1. Thành công và lỗi thường gặp

| Mã HTTP | Khi nào dùng | Điều client nên làm |
|---|---|---|
| **200 OK** | PATCH thành công và trả representation hoặc kết quả trong body | Dùng trạng thái mới và ETag nếu được trả |
| **204 No Content** | PATCH thành công nhưng không trả body | Cập nhật cache theo ETag nếu có; GET lại khi cần |
| **400 Bad Request** | Cú pháp request/patch document không hợp lệ | Sửa payload; không retry y hệt |
| **401 Unauthorized** | Chưa có hoặc sai thông tin xác thực | Xác thực lại theo giao thức |
| **403 Forbidden** | Đã xác thực nhưng không có quyền sửa trường/tài nguyên | Không retry khi quyền chưa thay đổi |
| **404 Not Found** | Không tìm thấy tài nguyên theo hợp đồng API | Xác minh resource URI, không giả định PATCH tự tạo mới |
| **409 Conflict** | Xung đột trạng thái nghiệp vụ/tài nguyên không được giải quyết bằng precondition cụ thể | Đọc trạng thái hiện tại, xử lý xung đột |
| **412 Precondition Failed** | If-Match không khớp validator hiện tại | GET lại, cân nhắc merge/reconcile thay đổi |
| **415 Unsupported Media Type** | API không hỗ trợ loại patch document được gửi | Sử dụng Content-Type được API công bố |
| **422 Unprocessable Content** | Cú pháp hiểu được nhưng patch vi phạm ngữ nghĩa/validation | Sửa nội dung patch, ví dụ giá âm hay path không hợp lệ |
| **428 Precondition Required** | Server yêu cầu If-Match hoặc precondition khác nhưng client chưa gửi | GET lấy ETag rồi gửi yêu cầu có điều kiện |
| **429 Too Many Requests** | Vượt rate limit | Chờ theo Retry-After/backoff, chỉ retry khi an toàn ngữ nghĩa |
| **503 Service Unavailable** | Dịch vụ tạm thời không phục vụ | Chỉ retry an toàn, tránh tạo tải đồng thời |

Mã 404, 409 hoặc 422 cho từng lỗi phụ thuộc vào **điều kiện cụ thể và hợp đồng API**. Chẳng hạn một JSON Patch có path không tồn tại có thể được từ chối vì không xử lý được chỉ dẫn; cách ánh xạ sang status cần nhất quán và được tài liệu hóa.

**428** là mã được định nghĩa cho trường hợp server yêu cầu request có điều kiện; **412** là kết quả khi precondition đã gửi nhưng đánh giá không đúng. Không dùng 409 thay thế tùy tiện cho 412 nếu nguyên nhân thực sự là **If-Match sai**.

### 8.2. Ví dụ phản hồi có ETag

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
ETag: "product-v8"

{
  "id": "P-100",
  "price": 15000,
  "stock": 10
}
~~~

Nếu trả **204 No Content**, response không có representation body; client có thể dùng header ETag nếu API trả và validator phù hợp với tài nguyên. Nếu server hỗ trợ nhiều loại patch document, có thể công bố:

~~~http
OPTIONS /products/P-100 HTTP/1.1
Host: api.example.test

HTTP/1.1 204 No Content
Allow: GET, HEAD, OPTIONS, PATCH
Accept-Patch: application/json-patch+json, application/merge-patch+json
~~~

**Accept-Patch** cho biết các media type được phép dùng làm tài liệu patch. Đây là header ở response cho discovery; client vẫn phải gửi **Content-Type** đúng trong PATCH. Đừng nhầm Accept-Patch với header **Accept** yêu cầu định dạng response.

### 8.3. Quy tắc retry cho HTTP client

| Tình huống | Nguy cơ | Hành vi khuyến nghị |
|---|---|---|
| Response thành công đã nhận đủ | Thấp | Không gửi lại cùng thao tác chỉ vì muốn “chắc chắn” |
| Timeout hoặc mất kết nối sau khi gửi PATCH | Không biết server đã commit chưa | Kiểm tra trạng thái hoặc chỉ retry nếu patch lũy đẳng hay có idempotency key |
| 502/503 hoặc lỗi mạng tạm thời | Server/downstream có thể đã xử lý một phần | Retry có giới hạn, backoff + jitter, kiểm tra idempotency trước |
| 429 kèm Retry-After | Có thể làm hệ thống quá tải nếu retry ngay | Tôn trọng khoảng chờ và điều kiện an toàn của thao tác |
| 412 khi dùng If-Match | Phiên bản client đã cũ hoặc một request trước đã thay đổi tài nguyên | GET lại, phân tích thay đổi; không lặp vô hạn cùng ETag |
| 409 | Trạng thái nghiệp vụ đang xung đột | Giải quyết xung đột hoặc hiển thị để người dùng quyết định |
| 400/415/422 | Payload hoặc media type không hợp lệ | Sửa request; retry nguyên trạng không có ích |

Khi gửi lệnh cộng dồn, **backoff chỉ giảm tải, không loại bỏ nguy cơ trùng nghiệp vụ**. Đồng thời cần có deadline, giới hạn số lần thử và khả năng quan sát correlation ID. Không tự khởi động retry với mọi PATCH chỉ vì thư viện hỗ trợ auto-retry.

### 8.4. Lưu ý về cache

PATCH thường làm các representation đã cache trở nên cũ. Theo yêu cầu và cấu hình HTTP caching, client/gateway cần xử lý invalidation phù hợp cho tài nguyên được sửa. Không dựa vào tính lũy đẳng để kết luận PATCH có thể cache tự động; **tính lũy đẳng** và **khả năng cache** là hai thuộc tính khác nhau.

## 9. Thực hành với Java/Spring: PATCH có điều kiện

Ví dụ sau thiết kế endpoint đổi **price** theo phép gán giá trị tuyệt đối. Resource là sản phẩm, URI giữ vai trò định danh, request chỉ chứa trường được phép sửa. API bắt buộc **If-Match** để chống lost update.

### 9.1. Định nghĩa request và controller

~~~java
@RestController
@RequestMapping("/products")
class ProductController {
    private final ProductService service;

    ProductController(ProductService service) {
        this.service = service;
    }

    @PatchMapping(
        path = "/{id}",
        consumes = "application/merge-patch+json"
    )
    ResponseEntity<ProductView> patchPrice(
            @PathVariable String id,
            @RequestHeader(name = "If-Match", required = false)
            String ifMatch,
            @RequestBody JsonNode patch) {

        if (ifMatch == null || ifMatch.isBlank()) {
            throw new ResponseStatusException(
                HttpStatus.PRECONDITION_REQUIRED,
                "If-Match is required"
            );
        }

        // Định dạng Merge Patch được hỗ trợ ở endpoint này
        // chỉ cho phép đặt price; không cho xóa trường price.
        if (!patch.isObject()
                || patch.size() != 1
                || !patch.hasNonNull("price")
                || !patch.get("price").isNumber()) {
            throw new ResponseStatusException(
                HttpStatus.UNPROCESSABLE_ENTITY,
                "Only a numeric price update is allowed"
            );
        }

        BigDecimal newPrice = patch.get("price").decimalValue();
        if (newPrice.signum() < 0) {
            throw new ResponseStatusException(
                HttpStatus.UNPROCESSABLE_ENTITY,
                "Price must be non-negative"
            );
        }

        UpdatedProduct updated =
            service.setPriceIfMatch(id, ifMatch, newPrice);

        return ResponseEntity.ok()
            .eTag(updated.strongEtag())
            .body(updated.view());
    }
}
~~~

Đây là **mẫu minh họa cách ghép các thành phần Spring MVC/Jackson**, giả định có các lớp ProductService, UpdatedProduct, ProductView và xử lý lỗi tương ứng. Cần khai báo import, cơ chế xác thực/phân quyền, kiểm tra kích thước payload, log và giới hạn nghiệp vụ trước khi dùng production.

Endpoint chọn hỗ trợ một **subset hẹp** của Merge Patch: chỉ cho đặt giá và từ chối xóa. Cách giới hạn này phải được mô tả trong OpenAPI; nếu API hứa hỗ trợ Merge Patch tổng quát, cần xử lý đầy đủ semantics tương ứng thay vì chỉ bind vào DTO bất kỳ và suy diễn trường thiếu/null.

### 9.2. Trách nhiệm bắt buộc ở service/repository

Controller ở trên **chưa đủ bảo đảm an toàn đồng thời**. Service cần thực hiện các bước sau trong một transaction:

~~~text
setPriceIfMatch(productId, ifMatch, newPrice):
    authenticate / authorize caller for product and field
    load product with its current version
    compute the current strong ETag for the representation

    if If-Match does not match:
        reject with 412 Precondition Failed

    if current price differs from newPrice:
        update price and increment resource version
    else:
        preserve the no-op result according to documented semantics

    atomically commit with optimistic version check
    if another transaction changed the version:
        reject appropriately (for this precondition, 412)

    return product representation and its new strong ETag
~~~

Trong ứng dụng dùng JPA, **@Version** hỗ trợ kiểm soát optimistic locking. Khi commit gặp xung đột, cần ánh xạ lỗi phù hợp và đảm bảo transaction rollback. Ở SQL có thể dùng compare-and-swap với điều kiện cập nhật:

~~~sql
UPDATE products
SET price = :new_price,
    version = version + 1
WHERE id = :product_id
  AND version = :expected_version;
~~~

Kiểm tra **số hàng cập nhật**: nếu bằng 0, tài nguyên có thể không tồn tại hoặc phiên bản không còn khớp; xác định nguyên nhân theo hợp đồng để trả 404/412. Ví dụ này dùng version làm optimistic concurrency token; nếu ETag cho representation không thể ánh xạ đơn giản sang một version column, logic kiểm tra validator phải xử lý đúng biểu diễn.

**Không so sánh If-Match như một chuỗi tùy tiện trong sản phẩm thật.** Header này có cú pháp HTTP cho ETag được trích dẫn, danh sách validator và trường hợp dấu sao. Phải dùng parser/phép so khớp strong validator phù hợp hoặc công cụ được kiểm tra; nếu hợp đồng chỉ chấp nhận một strong ETag phiên bản, hãy từ chối dạng không hỗ trợ một cách rõ ràng.

### 9.3. Tránh event hoặc update timestamp không cần thiết

Với một PATCH đặt giá 15.000 lặp lại khi giá đã là 15.000, logic nghiệp vụ thường nên nhận ra **no-op**. Nếu mỗi lần ghi lại cùng giá đều tăng version, thay đổi updatedAt hoặc phát event “giá đã đổi”, request có thể tạo hiệu ứng mới ngoài ý định. Những tác động này cần được định nghĩa và kiểm thử thay vì mặc định rằng câu lệnh gán giá luôn bảo đảm toàn bộ API lũy đẳng.

Với cập nhật có điều kiện If-Match, lần retry mang ETag cũ thường bị 412 nên không làm thay đổi thêm. Điều đó không loại bỏ yêu cầu no-op và phân biệt thay đổi thật ở những endpoint có phép gán không dùng precondition.

## 10. Hợp đồng OpenAPI phải ghi rõ PATCH làm gì

Một OpenAPI tốt cần thể hiện **định dạng patch, trường cho phép, ràng buộc, If-Match và lỗi**. Ví dụ OpenAPI 3.0/3.1 rút gọn cho endpoint ở phần 9:

~~~yaml
paths:
  /products/{id}:
    patch:
      summary: Đặt giá sản phẩm nếu phiên bản còn khớp
      description: >
        Chỉ hỗ trợ Merge Patch cập nhật price bằng số tuyệt đối.
        Không cho phép xóa price hoặc sửa trường khác.
        Client phải gửi strong ETag qua If-Match.
      parameters:
        - in: path
          name: id
          required: true
          schema:
            type: string
        - in: header
          name: If-Match
          required: true
          description: Strong ETag của representation hiện tại
          schema:
            type: string
      requestBody:
        required: true
        content:
          application/merge-patch+json:
            schema:
              type: object
              additionalProperties: false
              required: [price]
              properties:
                price:
                  type: number
                  minimum: 0
            example:
              price: 15000
      responses:
        "200":
          description: Cập nhật thành công
          headers:
            ETag:
              description: Strong ETag mới
              schema:
                type: string
          content:
            application/json:
              schema:
                type: object
                properties:
                  id:
                    type: string
                  price:
                    type: number
        "404":
          description: Không tìm thấy sản phẩm
        "412":
          description: If-Match không còn khớp
        "422":
          description: Patch document không hợp lệ về ngữ nghĩa
        "428":
          description: Thiếu If-Match bắt buộc
        "415":
          description: Content-Type không được hỗ trợ
~~~

Nếu endpoint khác hỗ trợ **increment**, OpenAPI phải có mô tả riêng rằng thao tác là **không lũy đẳng khi áp dụng lặp**, yêu cầu **Idempotency-Key** nếu cơ chế đó là bắt buộc, nêu TTL key, hành vi khi key trùng/khác payload và các response có thể trả.

**OpenAPI không tự kiểm tra tính lũy đẳng.** Đó là đặc tính của implementation và hợp đồng hành vi, phải được xác minh bằng thử nghiệm tích hợp.

## 11. Bảo mật và tính toàn vẹn dữ liệu khi PATCH

PATCH có thể tạo bề mặt tấn công lớn nếu client được gửi tự do tên trường, JSON Pointer hoặc thao tác trong một object graph. Các nguyên tắc quan trọng:

1. **Authorization trên tài nguyên và trường:** người dùng được sửa tên sản phẩm chưa chắc được sửa price, ownerId, role hay trạng thái thanh toán.
2. **Không mass assignment:** danh sách trường/path được PATCH phải được whitelist; không bind JSON tùy ý thẳng vào entity có trường đặc quyền.
3. **Object-level access:** kiểm tra người dùng/tenant có quyền trên resource URI và các tài nguyên được tham chiếu trong patch.
4. **Giới hạn payload và độ phức tạp:** số phép toán JSON Patch, kích thước body, độ sâu JSON, số phần tử mảng và phạm vi đường dẫn.
5. **Validation trước commit:** kiểm tra giá trị hợp lệ, quan hệ dữ liệu, invariant và quyền; nếu một phép toán thất bại, không để các phép trước đó commit.
6. **Chống race condition:** transaction, optimistic locking và unique/foreign key constraint ở database.
7. **Không lộ dữ liệu qua lỗi:** trả mã lỗi có cấu trúc, có correlation ID nhưng không đưa secret, stack trace hoặc dữ liệu tenant khác vào response.
8. **Phát sự kiện nhất quán:** với event/outbox, chỉ phát thay đổi nghiệp vụ đã commit; worker phải chịu được duplicate delivery.

Ví dụ JSON Patch gồm hai thao tác:

~~~http
PATCH /products/P-100 HTTP/1.1
Content-Type: application/json-patch+json

[
  {"op": "replace", "path": "/price", "value": 15000},
  {"op": "remove", "path": "/field-does-not-exist"}
]
~~~

Vì thao tác remove không hợp lệ, **toàn bộ patch phải thất bại mà không để price đã đổi thành 15.000**. Đó là yêu cầu atomicity đối với áp dụng patch document, khác với chuyện idempotency khi gửi cùng request nhiều lần.

## 12. Kiểm thử PATCH đúng trọng tâm

Kiểm thử không chỉ xem status 200. Phải kiểm tra **trạng thái tài nguyên sau mỗi lần gọi**, điều kiện đồng thời và hành vi sau timeout.

### 12.1. Ma trận kiểm thử đề xuất

| Kiểm thử | Cách thực hiện | Kết quả mong đợi |
|---|---|---|
| Đặt giá lặp lại | Gửi cùng patch set price hai lần trong điều kiện phù hợp | Price cuối bằng giá được đặt, không tăng cộng dồn |
| Increment lặp lại khi không có dedup | Gửi custom increment hai lần trên môi trường thử nghiệm | Số tăng hai lần, chứng minh đây là thao tác không lũy đẳng |
| Append JSON Patch | Gửi add vào /tags/- hai lần | Có thể có hai phần tử giống nhau theo semantics mảng |
| Lỗi giữa patch document | Phép 1 hợp lệ, phép 2 lỗi | Không commit một phần; dữ liệu giữ nguyên |
| Hai người dùng cùng ETag | Đọc cùng phiên bản rồi PATCH song song | Một cập nhật được chấp nhận; cập nhật stale bị 412 |
| Retry sau commit mất response | Giả lập server commit rồi client timeout | Không tạo thay đổi cộng dồn nếu API bảo đảm replay-safe |
| Lặp Idempotency-Key | Hai request giống key/payload gửi đồng thời | Không thực hiện hiệu ứng nghiệp vụ hai lần |
| Trùng key khác payload | Cùng key nhưng amount khác | Bị từ chối theo hợp đồng, không dùng kết quả sai |
| Không có If-Match | Endpoint bắt buộc precondition | 428, dữ liệu không đổi |
| Weak/stale ETag | Gửi validator không phù hợp | Không cập nhật trái điều kiện |
| Sai Content-Type | Gửi JSON Patch tới endpoint chỉ hỗ trợ Merge Patch | 415 hoặc lỗi được hợp đồng định nghĩa đúng |
| Trường không được sửa | PATCH role/owner/field nội bộ | 403 hoặc 422 theo contract; không thay đổi dữ liệu |
| Cross-tenant | Tenant A sửa tài nguyên tenant B | Bị từ chối, không rò dữ liệu hoặc tồn tại resource |
| Event/downstream retry | Giao trùng event sau commit | Không phát sinh nghiệp vụ trùng |

### 12.2. Ví dụ kiểm tra Spring MockMvc

Ví dụ test tích hợp dùng fixture một sản phẩm tồn tại, GET có ETag và endpoint bắt buộc If-Match. Sau khi patch thành công, retry **cùng ETag cũ** phải thất bại:

~~~java
String id = "P-100";
String etag = mockMvc.perform(get("/products/{id}", id))
    .andExpect(status().isOk())
    .andExpect(header().exists("ETag"))
    .andReturn()
    .getResponse()
    .getHeader("ETag");

String patchBody = "{\"price\":15000}";

mockMvc.perform(patch("/products/{id}", id)
        .contentType("application/merge-patch+json")
        .header("If-Match", etag)
        .content(patchBody))
    .andExpect(status().isOk())
    .andExpect(header().exists("ETag"));

mockMvc.perform(patch("/products/{id}", id)
        .contentType("application/merge-patch+json")
        .header("If-Match", etag)
        .content(patchBody))
    .andExpect(status().isPreconditionFailed());
~~~

Ở mức tích hợp, nên **assert lại GET và dữ liệu DB** để xác minh trạng thái chính xác, không chỉ kiểm tra 412. Test đồng thời và idempotency key cần môi trường lưu trữ/transaction thật hoặc phương án kiểm thử đủ gần production để phát hiện race condition.

## 13. Bài thực hành: thiết kế PATCH có thể retry an toàn

### Bối cảnh

Một REST API quản lý giỏ hàng cung cấp:

- **GET /carts/C-01** trả một giỏ hàng có số lượng sản phẩm và ETag.
- **PATCH /carts/C-01/items/SKU-9** nhận yêu cầu tăng số lượng sản phẩm.
- Mobile client có cơ chế retry khi mạng di động không ổn định.

Trạng thái ban đầu là **quantity = 2**. Client muốn **tăng thêm 1** và có thể gửi lại khi timeout. Đội phát triển đề xuất hai contract:

**Phương án A — gán số lượng tuyệt đối**

~~~http
PATCH /carts/C-01/items/SKU-9 HTTP/1.1
Content-Type: application/merge-patch+json
If-Match: "cart-item-v4"

{"quantity": 3}
~~~

**Phương án B — tăng số lượng tương đối**

~~~http
PATCH /carts/C-01/items/SKU-9 HTTP/1.1
Content-Type: application/json
Idempotency-Key: cart-increment-8d7f-4a2c

{"operation": "increment", "amount": 1}
~~~

### Yêu cầu

1. Cho biết A và B có tính lũy đẳng mặc định hay không, và kết quả nếu mỗi request thực sự được áp dụng hai lần.
2. Giải thích trong A tại sao retry với If-Match cũ có thể trả 412 dù quantity đã đúng bằng 3.
3. Trong B, thiết kế khóa chống thực thi trùng: phạm vi key, fingerprint, TTL, transaction và xử lý hai request đồng thời.
4. Nếu có hai thiết bị cùng tăng 1 từ quantity = 2, làm sao phân biệt **hai thao tác hợp lệ** với **retry của cùng một thao tác**?
5. Chọn status phù hợp cho trường hợp thiếu If-Match, ETag sai, payload có amount âm ngoài chính sách, Content-Type không được hỗ trợ và vượt rate limit.
6. Đề xuất năm bài kiểm thử tính đúng đắn của dữ liệu và tính an toàn khi retry.

### Hướng dẫn đánh giá

**Phương án A:** yêu cầu gán quantity = 3 thuộc dạng lũy đẳng theo trạng thái số lượng. Nếu không có điều kiện và được áp dụng hai lần, quantity vẫn là 3. Với **If-Match v4**, lần đầu làm phiên bản đổi sang v5, retry mang ETag v4 thường bị 412 và không áp dụng lần nữa. Nếu thiết bị khác sửa giỏ hàng, không được coi mọi 412 là “lần trước chắc chắn thành công”.

**Phương án B:** increment +1 không lũy đẳng nếu áp dụng hai lần, nên cần dedup dựa trên key. Cùng key/payload của **một thao tác logic** chỉ thay đổi quantity một lần; hai thao tác riêng biệt phải dùng **hai key khác nhau** và nếu đều hợp lệ, quantity tăng 2. Key không thay thế xác thực/phân quyền và phải xử lý cạnh tranh trong database transaction.

Các status tham khảo: **428** cho thiếu precondition ở A; **412** cho If-Match sai; **422** cho lượng cập nhật trái quy tắc nghiệp vụ; **415** cho sai media type; **429** khi vượt giới hạn tốc độ. Với B, cùng key nhưng payload khác cần trả lỗi phù hợp hợp đồng, và không áp dụng thao tác thứ hai.

Bộ kiểm thử mạnh gồm: gửi request trùng; hai thiết bị cập nhật đồng thời; timeout sau commit; gửi lại cùng key từ nhiều instance; gửi cùng key với body khác; thử thiếu precondition; thử lỗi transaction; kiểm tra event/đối soát sau retry.

## 14. Những nhầm lẫn thường gặp

| Nhầm lẫn | Cách hiểu đúng |
|---|---|
| “PATCH lúc nào cũng không lũy đẳng” | PATCH **không được bảo đảm mặc định**; một PATCH đặt giá trị tuyệt đối có thể lũy đẳng |
| “PATCH luôn lũy đẳng vì chỉ sửa một trường” | Số lượng trường không quyết định; increment một trường vẫn không lũy đẳng |
| “JSON Patch là idempotent” | JSON Patch là **định dạng chỉ dẫn**; mỗi op và path có semantics khác nhau |
| “JSON Merge Patch luôn an toàn để retry trong mọi hệ thống” | Phép merge thường lũy đẳng về tài liệu nhưng side effect, đồng thời và nghiệp vụ vẫn phải xét |
| “If-Match và Idempotency-Key là một” | If-Match quản lý điều kiện phiên bản; key nhận diện một thao tác logic gửi lại |
| “412 nghĩa là PATCH của tôi đã thành công trước đó” | 412 chỉ nói precondition hiện tại không đúng; nguyên nhân thay đổi có thể do client khác |
| “Atomic PATCH nghĩa là gửi hai lần cũng chỉ áp dụng một lần” | Atomicity áp dụng **một patch document**; lặp request là vấn đề riêng |
| “Retry có exponential backoff là an toàn” | Backoff không ngăn tăng tồn/trừ tiền lặp |
| “Cùng status 200 nghĩa là lũy đẳng” | Phải so sánh tác động dự định lên trạng thái, không chỉ status |
| “PUT idempotent, nên dùng PUT thay mọi PATCH” | PUT có nghĩa thay thế trạng thái tài nguyên; chọn theo hợp đồng resource, không đổi phương thức tùy tiện |

## 15. Checklist khi thiết kế endpoint PATCH

- [ ] Xác định rõ resource URI và quyền cập nhật các field hoặc path.
- [ ] Công bố loại patch document và semantics của từng phép toán.
- [ ] Biết thao tác là gán trạng thái hay cộng dồn; không dựa vào tên PATCH để kết luận idempotency.
- [ ] Nếu có retry sau timeout, có chiến lược bảo đảm an toàn: lũy đẳng, If-Match và/hoặc idempotency key tùy nhu cầu.
- [ ] Với If-Match: có strong ETag đúng và kiểm tra/ghi phiên bản nguyên tử.
- [ ] Với key: có scope, fingerprint, TTL, trạng thái xử lý, transaction và kiểm tra request đồng thời.
- [ ] Hỗ trợ patch document atomically, không để thay đổi một phần khi lỗi.
- [ ] Các status 200/204, 400/409/412/415/422/428/429 và 5xx được tài liệu hóa phù hợp.
- [ ] OpenAPI mô tả Content-Type, request schema, precondition, response, lỗi và ví dụ.
- [ ] Kiểm thử double submit, lost response, stale version, concurrent writes, invalid path, cross-tenant và side effect bất đồng bộ.

## 16. Ghi nhớ và tài liệu chuẩn

**PATCH không mặc định lũy đẳng.** Tính lũy đẳng phụ thuộc **phép biến đổi trạng thái mà patch document và ứng dụng thực thi**: đặt một giá trị cố định có thể lũy đẳng, còn cộng dồn hoặc append thường không. **Atomicity** bảo đảm một patch document không áp dụng dở dang; **If-Match/ETag** bảo vệ cập nhật theo phiên bản; **Idempotency-Key** giúp nhận diện retry của cùng một thao tác logic. Client và server phải thống nhất contract, đặc biệt trong tình huống mất kết nối sau khi server đã commit.

Tài liệu tham khảo chính thức:

- [RFC 9110 — HTTP Semantics, Idempotent Methods và Conditional Requests](https://www.rfc-editor.org/rfc/rfc9110).
- [RFC 5789 — PATCH Method for HTTP](https://www.rfc-editor.org/rfc/rfc5789).
- [RFC 6902 — JavaScript Object Notation (JSON) Patch](https://www.rfc-editor.org/rfc/rfc6902).
- [RFC 7386 — JSON Merge Patch](https://www.rfc-editor.org/rfc/rfc7386).
- [RFC 6585 — Additional HTTP Status Codes (bao gồm 428)](https://www.rfc-editor.org/rfc/rfc6585).
