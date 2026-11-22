# Thiết kế cú pháp lọc có giới hạn và kiểm soát trường được phép

> **Phạm vi:** Bài học thuộc **INTEGRATION_API_REST**, chương **Truy vấn tập hợp**. Người học thiết kế hợp đồng lọc cho REST API theo resource và URI, kiểm soát rõ trường và toán tử được phép, đặt giới hạn để truy vấn có chi phí dự đoán được, bảo vệ phân quyền dữ liệu, đồng thời kết hợp phân trang, sắp xếp, cache, lỗi HTTP, OpenAPI và kiểm thử. Ví dụ sử dụng Java/Spring và cơ sở dữ liệu quan hệ; nguyên tắc tương tự áp dụng với công nghệ khác.

## 1. Vấn đề: endpoint danh sách rất dễ trở thành một ngôn ngữ truy vấn không kiểm soát

Giả sử ứng dụng quản lý đơn hàng cần hiển thị danh sách. Ban đầu endpoint chỉ có:

~~~http
GET /v1/orders HTTP/1.1
Host: api.example.test
Authorization: Bearer <access-token>
~~~

Sau vài phiên bản, client muốn lọc theo trạng thái, khoảng ngày, tổng tiền và mã đơn. Một cách làm nhanh nhưng nguy hiểm là nhận các tham số như:

~~~text
GET /v1/orders?where=status='PAID' OR 1=1
GET /v1/orders?field=customer.email&operator=contains&value=@
GET /v1/orders?sql=SELECT * FROM orders
GET /v1/orders?sortBy=internal_cost&direction=desc
GET /v1/orders?filter=((((a OR b) OR c) OR d) ...)
~~~

Những URI trên minh họa **phản mẫu, không phải API nên triển khai**. Ngay cả khi code dùng prepared statement và ngăn được SQL injection, client vẫn có thể được phép tạo truy vấn quá đắt, lọc trên field bí mật, tham chiếu các bảng mà API không định công bố hoặc khiến cấu trúc database trở thành hợp đồng công khai. Thêm phân trang không tự giải quyết vấn đề: một truy vấn phải quét hàng triệu bản ghi trước khi lấy 20 kết quả vẫn có thể tốn rất nhiều tài nguyên.

**Câu hỏi kiến trúc:** làm sao cung cấp đủ khả năng lọc cho các hành trình thật của client, nhưng không trao cho client quyền điều khiển tùy ý kế hoạch truy vấn, phạm vi dữ liệu và chi phí của server?

Câu trả lời là một **ngôn ngữ lọc có giới hạn (bounded filter language)**: tập field hữu hạn, toán tử tương thích với từng field, ngữ nghĩa rõ ràng, giới hạn độ phức tạp, và lớp thực thi chỉ ánh xạ tới những truy vấn được server cho phép.

### 1.1. Kết quả học tập

Sau bài này, người học có thể:

- Phân biệt filter công khai với predicate nội bộ, cột SQL và quyền truy cập resource.
- Thiết kế cú pháp query parameter có thể đọc, encode, parse và tài liệu hóa nhất quán.
- Định nghĩa **allowlist field–operator**, kiểu dữ liệu, logic kết hợp điều kiện và quy tắc từ chối request.
- Áp dụng giới hạn cho số điều kiện, kích thước danh sách, độ dài chuỗi, khoảng ngày và số kết quả.
- Biên dịch filter thành truy vấn có **tham số hóa giá trị** nhưng không dùng field/operator do client tự ghép vào SQL.
- Kết hợp filter với sort, keyset pagination, cache, authorization và rate limit để bảo vệ tính ổn định.
- Viết ví dụ Java/Spring, OpenAPI và các bài test âm trước khi công bố endpoint.

## 2. Đừng bắt đầu bằng cú pháp: bắt đầu bằng câu hỏi nghiệp vụ

Một tính năng quản lý đơn hàng có thể có các nhu cầu:

1. Khách hàng muốn xem đơn gần đây của **chính mình**, lọc `PAID` hoặc `SHIPPED`.
2. Nhân viên hỗ trợ muốn tìm đơn theo **mã đơn** và thời gian tạo, nhưng chỉ trong phạm vi đơn được giao.
3. Nhân viên tài chính muốn xem đơn theo **khoảng tiền** trong một **loại tiền tệ** cụ thể.
4. Đội vận hành muốn phân tích gian lận, nhưng dữ liệu như `fraudScore` không được công khai qua endpoint khách hàng.

Từ các use case đó, thiết kế bộ lọc dành cho resource `orders` thay vì cấp quyền tùy ý đối với `OrderEntity`. Field như `createdAt` có thể là một thuộc tính công khai, mặc dù lưu trữ nội bộ dùng cột `created_on_utc` hoặc nhiều bảng. Người dùng không cần biết tên cột, cách join hay index.

### 2.1. Ba lớp trách nhiệm

~~~mermaid
flowchart LR
    Client["Client\nGET /v1/orders?filter..."] --> Contract["Hợp đồng lọc\nfield + operator + type + limits"]
    Contract --> Parser["Parser và validation\nQuerySpec có kiểu"]
    Parser --> Auth["Ràng buộc quyền\nprincipal + tenant + scope"]
    Auth --> Builder["Query builder\nmapping trường cố định"]
    Builder --> DB[("DB / search index")]
    DB --> Builder
    Builder --> Page["Projection + sort + cursor"]
    Page --> Client
    Internal["Tên cột, join, index\nchi tiết nội bộ"] -.-> Builder
~~~

**Lớp hợp đồng** định nghĩa client được hỏi gì. **Lớp phân quyền** giới hạn những bản ghi client được phép thấy. **Lớp thực thi** quyết định truy vấn hiệu quả và an toàn trên mô hình lưu trữ hiện tại. Không cho phép client bỏ qua lớp phân quyền bằng cách thêm filter mới.

### 2.2. Các câu hỏi phải trả lời trước khi viết parser

| Câu hỏi | Vì sao quan trọng? |
|---|---|
| Người dùng thực sự cần lọc theo field nào? | Tránh mở quá nhiều cột và tăng diện tấn công |
| Với mỗi field, cần `eq`, `in`, `gte`, `lt` hay `prefix`? | Toán tử quyết định ngữ nghĩa, index và chi phí |
| Có cần OR/NOT, nested groups hoặc join liên tài nguyên không? | Mức biểu đạt càng mạnh, parser và giới hạn chi phí càng khó |
| Kiểu dữ liệu và timezone là gì? | Tránh lệch thời gian, số tiền và so sánh chuỗi |
| Có mặc định nào khi không gửi điều kiện không? | Tránh vô tình quét toàn bộ dữ liệu |
| Cần giới hạn thời gian/độ dài/số điều kiện ra sao? | Chặn truy vấn quá rộng ngay từ API |
| Có phân quyền theo tenant và từng resource không? | Filter không phải cơ chế bảo mật |
| Danh sách thay đổi khi client phân trang thì sao? | Cần sort ổn định và cursor thích hợp |
| Đường dẫn query có thể cache không? | Cache phải tôn trọng quyền và key theo toàn bộ filter |

## 3. Hợp đồng mẫu: một ngôn ngữ lọc hữu hạn cho đơn hàng

Trong bài, ta chọn quy ước query parameter:

~~~text
GET /v1/orders
    ?filter[createdAt][gte]=2026-11-01T00:00:00Z
    &filter[createdAt][lt]=2026-12-01T00:00:00Z
    &filter[status][in]=PAID,SHIPPED
    &filter[currency][eq]=VND
    &sort=-createdAt
    &limit=20
~~~

Các dòng trên được ngắt để giải thích; một URI HTTP thực tế phải là một dòng, với các ký tự đặc biệt được percent-encode theo quy tắc URI. Cặp ngoặc vuông trong tên tham số nên được mã hóa khi gửi qua mạng, ví dụ `filter%5Bstatus%5D%5Bin%5D`; thư viện HTTP thường hỗ trợ encode tham số đúng cách.

### 3.1. Ngữ pháp công khai

Quy ước:

~~~text
filter-param = "filter[" field "][" operator "]=" value
field        = một tên field trong allowlist công khai
operator     = một toán tử được phép riêng cho field
value        = một giá trị theo kiểu dữ liệu của field/operator

GET /v1/orders?filter[field][operator]=value&...
~~~

Đây là **ngữ pháp ứng dụng** được định nghĩa cho endpoint; HTTP không áp đặt chuẩn chung rằng các query parameter bắt buộc có dạng `filter[...][...]`. Có hệ dùng `status=PAID`, `status.in=PAID,SHIPPED`, OData hoặc RSQL; lựa chọn nào cũng cần cùng nguyên tắc về giới hạn, allowlist, quyền truy cập và kiểm thử. Đừng chấp nhận nhiều cú pháp tương đương nếu không có nhu cầu, vì làm tăng số cách biểu đạt, khó canonicalize và khó cache.

Quy tắc cố ý **đơn giản**:

- Mọi cặp filter được kết hợp bằng **AND**.
- Riêng `in` có nghĩa **OR giữa các giá trị của cùng một field**.
- Không hỗ trợ nhóm `OR` lồng nhau, `NOT`, function, expression hoặc điều hướng quan hệ bằng dấu chấm.
- Một cặp field/operator chỉ được xuất hiện **một lần** trong request.
- Toán tử và field được định nghĩa cố định; không tự suy ra operator từ kiểu giá trị.

Ví dụ `status in (PAID, SHIPPED)` cùng `createdAt >= from` và `createdAt < to` tương đương về mặt logic với:

\[
(status = PAID \lor status = SHIPPED)
\land createdAt \ge from
\land createdAt < to
\]

Không diễn giải các filter khác nhau thành OR. Nếu client cần ngôn ngữ OR phức tạp, hãy đánh giá use case và chi phí riêng, không âm thầm mở một mini-SQL tổng quát qua query string.

### 3.2. Allowlist field–operator của phiên bản 1

| Field công khai | Kiểu | Toán tử cho phép | Giới hạn và ngữ nghĩa |
|---|---|---|---|
| `createdAt` | Date-time có offset | `gte`, `lt` | **Bắt buộc cả hai**; khoảng nửa mở `[from, to)`, tối đa 90 ngày |
| `status` | Enum | `in` | Tối đa 5 giá trị khác nhau, thuộc `PENDING_PAYMENT`, `PAID`, `SHIPPED`, `CANCELLED` |
| `currency` | Enum | `eq` | Chỉ `VND` hoặc `USD` trong ví dụ; bắt buộc nếu có filter tiền |
| `totalAmount` | Decimal | `gte`, `lt` | Không âm; tối đa 2 chữ số thập phân, giá trị nhỏ hơn 1 tỷ theo đơn vị tiền |
| `orderCode` | String có chuẩn riêng | `prefix` | Từ 2 đến 12 ký tự `A-Z`, `0-9`, dấu gạch nối; không nhận wildcard |

Những field sau **không nằm trong allowlist**: `customerId` do client tự gửi, `tenantId`, `paymentToken`, `fraudScore`, `internalCost`, `sqlExpression`, `deletedAt`, mọi quan hệ `customer.email` hoặc field không được liệt kê. Điều này không khẳng định chúng không tồn tại nội bộ; API chỉ quyết định rằng **không cho dùng chúng để lọc ở endpoint này**.

Trong một API thực tế, có thể thiết kế allowlist khác theo vai trò hoặc tách endpoint quản trị. Ví dụ nhân viên hỗ trợ được phép lọc theo mã đơn và thời điểm, còn bộ phận thanh toán có endpoint truy vấn giao dịch riêng được bảo vệ. Không bật mọi field cho mọi principal chỉ để tái sử dụng một repository.

### 3.3. Ngưỡng bảo vệ của ví dụ

| Loại ngưỡng | Giá trị mẫu | Lý do |
|---|---:|---|
| Số điều kiện `filter[...][...]` | Tối đa 8 | Giới hạn số predicate và chi phí parser/query |
| Tổng số tham số query | Tối đa 12 | Tránh biến URI thành gói truy vấn không kiểm soát |
| Giá trị của `status in` | 1–5 | Tránh danh sách rất dài |
| Khoảng `createdAt` | `0 < duration <= 90 ngày` | Giới hạn lượng dữ liệu có thể quét |
| `orderCode prefix` | 2–12 ký tự | Bảo vệ index/selectivity |
| `limit` | 1–100, mặc định 20 | Chặn trả quá nhiều bản ghi |
| `sort` | `-createdAt` mặc định, hoặc `createdAt` | Chỉ hỗ trợ một trường có kế hoạch truy vấn rõ |
| `cursor` | Chuỗi opaque, có giới hạn độ dài/tuổi | Tránh offset sâu và ngăn sửa phạm vi |
| Kích thước URI và thời gian truy vấn | Theo gateway/app/DB budget được đo | Tránh payload và query execution quá lớn |

**Các con số là tham số minh họa**, không phải chuẩn REST toàn ngành. Chọn ngưỡng bằng số liệu thực tế: phân bố số đơn/tenant, độ chọn lọc của index, SLA, dung lượng DB, peak traffic và ngân sách truy vấn. Ghi lại giới hạn trong OpenAPI và thông báo lỗi để client có thể tự điều chỉnh.

Trong ví dụ này **bắt buộc gửi đủ hai mốc thời gian**; không có truy vấn mọi đơn của tất cả các năm qua endpoint danh sách. Để tìm lịch sử dài hơn 90 ngày, client chia thành các khoảng hợp lệ hoặc sử dụng endpoint xuất báo cáo bất đồng bộ được thiết kế riêng. Cách này minh họa ràng buộc phạm vi, không phải quy tắc mọi sản phẩm đều phải áp dụng.

## 4. Kiểu dữ liệu, đơn vị và giới hạn chính xác

### 4.1. Khoảng thời gian nửa mở

Dùng:

~~~text
filter[createdAt][gte]=2026-11-01T00:00:00Z
filter[createdAt][lt]=2026-12-01T00:00:00Z
~~~

Điều kiện đúng là `createdAt >= 2026-11-01T00:00:00Z` **và** `createdAt < 2026-12-01T00:00:00Z`. Khoảng `[from, to)` tránh phải tự tạo mốc “23:59:59.999” phụ thuộc độ chính xác của database. Hai khoảng liên tiếp `[A, B)` và `[B, C)` không chồng ranh giới tại B.

Yêu cầu date-time phải có offset, ví dụ `2026-11-01T07:00:00+07:00` hoặc `2026-11-01T00:00:00Z`; server đổi thành `Instant` trước khi truy vấn. Không suy đoán timezone từ địa chỉ IP hay timezone máy chủ. Nếu giao diện nhận ngày địa phương, client chuyển thành hai mốc theo timezone nghiệp vụ đã thống nhất; các vùng có DST cần đặc biệt lưu ý.

Ràng buộc:

- Không thiếu một trong hai mốc.
- `from < to`.
- Khoảng thời gian không quá 90 ngày theo ngưỡng đã công bố.
- Timestamp phải parse được theo ISO 8601 có offset và nằm trong miền thời gian hỗ trợ.
- Không chấp nhận số epoch tùy ý ở cùng một field nếu API chỉ hỗ trợ dạng chuỗi ISO.

### 4.2. Enum, giá trị nhiều phần và dấu phẩy

Giá trị:

~~~text
filter[status][in]=PAID,SHIPPED
~~~

Được định nghĩa là **danh sách enum phân cách bằng dấu phẩy**, tối đa năm token khác nhau. Vì các token enum được quy định không chứa dấu phẩy, parser không cần hỗ trợ escaping phức tạp. Nếu một API phải lọc theo dữ liệu chuỗi có thể chứa dấu phẩy, không nên tái sử dụng quy tắc này một cách tùy tiện; hãy chọn một cách biểu diễn khác có escape/repeated parameters rõ ràng.

Các trường hợp bị từ chối: `PAID,`, `,PAID`, `PAID,,SHIPPED`, `PAID,PAID`, `PAID,UNKNOWN` và quá năm mục. So sánh enum **phân biệt chữ hoa/chữ thường** trong phiên bản này; không tự cắt khoảng trắng hoặc sửa lỗi chính tả trừ khi hợp đồng có quy tắc chuẩn hóa riêng.

### 4.3. Tiền phải đi cùng đơn vị

`totalAmount` chỉ so sánh có ý nghĩa trong một currency. Vì thế nếu có `filter[totalAmount][gte]` hoặc `filter[totalAmount][lt]`, API yêu cầu `filter[currency][eq]`.

~~~text
filter[currency][eq]=VND
filter[totalAmount][gte]=100000
filter[totalAmount][lt]=500000
~~~

Không so sánh giá trị 100.000 VND với 100.000 USD chỉ vì đều là một cột decimal. Parser nhận giá trị decimal hữu hạn, không âm, tối đa hai chữ số sau dấu thập phân; không dùng `double` để tính tiền. Khi sản phẩm sử dụng đơn vị nhỏ nhất (minor units) dạng số nguyên, hợp đồng và cách parse sẽ khác. Nếu có cả hai mốc tiền, phải kiểm tra `gte < lt`.

### 4.4. Prefix trên mã đơn, không phải tìm kiếm tùy ý

`filter[orderCode][prefix]=ORD-2026` có ngữ nghĩa “bắt đầu bằng chuỗi đã cho”, phân biệt với `contains` hay full-text search. Cho phép wildcard `%`, `_` hoặc pattern regex từ client có thể dẫn tới hành vi khác và query tốn tài nguyên.

Giới hạn ký tự, độ dài tối thiểu và mapping tới index có thể sử dụng prefix scan. Nếu hệ thống cần tìm kiếm nội dung tự do, hãy thiết kế một chức năng search có giới hạn và chỉ số phù hợp, thay vì mở `LIKE '%anything%'` trên bảng lớn.

## 5. URI và encoding: cú pháp hợp đồng không phải chuỗi ghép tùy tiện

URI mẫu dễ đọc:

~~~text
/v1/orders?filter[createdAt][gte]=2026-11-01T00:00:00Z&filter[createdAt][lt]=2026-12-01T00:00:00Z&filter[status][in]=PAID,SHIPPED&sort=-createdAt&limit=20
~~~

Khi truyền qua HTTP, client dùng công cụ encode các tên/giá trị query. Ví dụ có thể trở thành:

~~~http
GET /v1/orders?filter%5BcreatedAt%5D%5Bgte%5D=2026-11-01T00%3A00%3A00Z&filter%5BcreatedAt%5D%5Blt%5D=2026-12-01T00%3A00%3A00Z&filter%5Bstatus%5D%5Bin%5D=PAID%2CSHIPPED&sort=-createdAt&limit=20 HTTP/1.1
Host: api.example.test
Authorization: Bearer <access-token>
~~~

Ví dụ `curl` dễ kiểm soát encoding hơn:

~~~bash
curl --get "https://api.example.test/v1/orders" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN" \
  --data-urlencode "filter[createdAt][gte]=2026-11-01T00:00:00Z" \
  --data-urlencode "filter[createdAt][lt]=2026-12-01T00:00:00Z" \
  --data-urlencode "filter[status][in]=PAID,SHIPPED" \
  --data-urlencode "sort=-createdAt" \
  --data-urlencode "limit=20"
~~~

HTTP server/framework thường decode query parameter trước khi controller nhận chúng. Parser nên xử lý **tên sau khi decode một lần theo cơ chế chuẩn**; không tự decode lặp đi lặp lại, vì `%255B` có thể trở thành `%5B` rồi `[` và tạo đường vòng qua validation.

### 5.1. Chính sách với tham số lặp hoặc lạ

Các request sau cần có cách xử lý xác định:

~~~text
?filter[status][in]=PAID&filter[status][in]=CANCELLED
?filter[createdAt][gt]=2026-11-01T00:00:00Z
?filter[customer.email][contains]=@example.test
?filter[status][in]=PAID&unusedParam=anything
?sort=-createdAt&sort=createdAt
~~~

Trong hợp đồng ví dụ, **tất cả bị từ chối với lỗi 400** vì duplicate, operator không hỗ trợ, field ngoài allowlist hoặc query parameter không được công bố. Không dùng `getFirst()` để âm thầm bỏ những giá trị trùng, vì proxy, framework hoặc tầng cache có thể diễn giải chúng khác nhau, tạo lỗi khó dự đoán.

Một số API chọn bỏ qua unknown parameter để tương thích ngược; đó là quyết định có thể chấp nhận nếu rủi ro được đánh giá, nhưng **không** nên vô tình bỏ qua filter mà client tưởng đã được áp dụng. Với endpoint có giới hạn bảo mật và dữ liệu nhạy cảm, fail-fast thường rõ ràng hơn.

### 5.2. Canonicalization và tính ổn định

Hai URI có thứ tự tham số khác nhau có thể có ngữ nghĩa logic giống nhau, nhưng cache HTTP thông thường coi chúng là các key URL khác nhau nếu không có cơ chế chuẩn hóa. Có thể chuẩn hóa query theo thứ tự field/operator, giá trị enum và format timestamp **ở phía server**, rồi dùng biểu diễn chuẩn cho fingerprint, phân tích và cursor. Không làm mất ý nghĩa giá trị do client gửi và không tự động chuẩn hóa những dạng không được hợp đồng chấp nhận.

Đừng coi normalization là cơ chế chống injection. Dù đầu vào đúng grammar, vẫn cần allowlist và parameterization khi biên dịch truy vấn.

## 6. Allowlist phải kiểm soát tổ hợp field–operator, không chỉ tên field

Cho phép `createdAt` không có nghĩa cho phép mọi toán tử trên nó. So sánh prefix với timestamp hay `contains` trên tiền không có ý nghĩa. Thiết kế một registry cố định:

~~~text
createdAt  -> gte, lt
status     -> in
currency   -> eq
totalAmount-> gte, lt
orderCode  -> prefix
~~~

Mọi cặp ngoài registry bị từ chối trước khi truy vấn. Không cần xây dựng hệ thống thực thi biểu thức chung với toán tử do client tự khai báo.

### 6.1. Hạn chế độ phức tạp từ nhiều chiều

Một request có đúng field và operator vẫn có thể nguy hiểm nếu:

- Kết hợp rất nhiều điều kiện, gây query plan phức tạp hoặc quá nhiều bind parameter.
- Danh sách `IN` có hàng chục nghìn giá trị.
- Khoảng ngày trải qua nhiều năm, buộc quét lượng dữ liệu lớn.
- Filter prefix chỉ có một ký tự hoặc bắt đầu bằng wildcard.
- Sort trên cột không có index rồi yêu cầu `offset=10000000`.
- Dùng join qua nhiều collection làm nổ số row và khiến phân trang không ổn định.
- Client tạo hàng nghìn request lọc khác nhau mỗi phút, vượt khả năng cache.

Vì vậy **giới hạn cú pháp, giới hạn giá trị và giới hạn tài nguyên thực thi** phải đi cùng nhau. `limit=20` không giới hạn chi phí của phần `WHERE`/`ORDER BY`.

### 6.2. Khi thật sự cần truy vấn nâng cao

Nếu nhóm nghiệp vụ cần nhóm OR lồng nhau, aggregation, regex, tự do chọn field, search toàn văn hoặc join liên resource, hãy xem xét:

- Định nghĩa các **mẫu truy vấn có tên** như `/orders/search-by-code` hoặc endpoint báo cáo riêng, với request schema có giới hạn.
- Dùng resource tìm kiếm/báo cáo có thể xử lý bất đồng bộ: `POST /report-jobs`, `202 Accepted`, `Location` trỏ đến monitor, giới hạn quota.
- Dùng search engine riêng khi yêu cầu full-text thật sự, đồng thời kiểm soát quyền tài liệu và consistency.
- Cho phép filter nâng cao cho nhóm quản trị qua API và quota riêng, với **AST parser**, giới hạn độ sâu/số nút, cấm function không cần thiết và query cost budget.

Đừng mở rộng grammar của endpoint danh sách phổ thông chỉ vì một use case quản trị đặc biệt. Quyền truy cập và đặc tính tải của hai nhóm có thể rất khác nhau.

## 7. Phân quyền dữ liệu không được đến từ filter của client

Một lỗi nghiêm trọng:

~~~text
GET /v1/orders?filter[customerId][eq]=user_123
~~~

Nếu server coi `customerId` từ query là điều kiện duy nhất để chọn đơn, người gọi có thể thay thành `user_456` và đọc dữ liệu ngoài quyền. Đây là dạng lỗi **Broken Object Level Authorization (BOLA)** hoặc lộ dữ liệu liên tenant. Người dùng **không** được chọn tenant/owner mà server tin dùng để giới hạn quyền.

### 7.1. Ghép predicate phân quyền từ danh tính đáng tin cậy

Giả sử request xác thực thành công cho principal `user_123` thuộc tenant `t_7`. Server áp dụng predicate bắt buộc **ngoài query filter**:

~~~sql
SELECT o.public_id, o.status, o.currency, o.total_amount, o.created_at
FROM orders o
WHERE o.tenant_id = :tenant_from_auth
  AND o.owner_id = :user_from_auth
  AND o.created_at >= :from
  AND o.created_at < :to
  AND o.status IN (:allowed_statuses)
ORDER BY o.created_at DESC, o.public_id DESC
LIMIT :page_size_plus_one;
~~~

Đây là SQL **minh họa**, không phải query hoàn chỉnh cho mọi trường hợp. Predicate status chỉ được thêm khi client thật sự gửi filter status; syntax `IN (:allowed_statuses)` cần bind collection theo cơ chế ORM/driver phù hợp. Với các role khác, policy scope có thể phức tạp hơn, nhưng luôn bắt nguồn từ **quyền đã xác minh**, không phải từ tham số `tenantId` do client tự khai.

### 7.2. Phân quyền theo field và theo row là hai việc khác nhau

- **Field allowlist** kiểm soát trường nào được dùng để truy vấn. Ví dụ không được lọc theo `fraudScore`, dù response cũng không trả field đó.
- **Row-level scope** kiểm soát tập bản ghi nhìn thấy. Ví dụ người dùng chỉ được thấy đơn của mình.
- **Projection allowlist** kiểm soát field nào được trả trong JSON.

Một client có thể lọc theo một field mà họ **không được đọc giá trị** nhưng vẫn suy ra thông tin bằng “có/không có kết quả”. Vì thế việc chỉ ẩn field khỏi response **chưa đủ**; quyền lọc cũng cần được xem là quyền truy cập thông tin. Ví dụ cấm filter theo `internalRiskScore` ngay cả khi JSON không chứa điểm rủi ro.

Nếu filter registry thay đổi theo vai trò, nên áp dụng quyền trước khi tiết lộ danh sách field được phép. Với cặp field/operator không được hỗ trợ cho principal, có thể trả lỗi tổng quát `400 INVALID_FILTER` thay vì xác nhận sự tồn tại của field nội bộ. Nếu caller không có quyền truy cập collection, trả `403` hoặc chính sách thích hợp trước khi chạy truy vấn.

### 7.3. Đừng để filter hoặc sort ghi đè chính sách mặc định

Các predicate bắt buộc như `tenant_id`, `owner_id`, `soft_deleted = false`, vùng dữ liệu/địa bàn được phép hoặc chính sách phân loại dữ liệu phải được gắn từ server vào **mọi truy vấn**, kể cả truy vấn có cursor và truy vấn count.

Không cho query string gửi:

~~~text
?includeDeleted=true
?allTenants=true
?bypassPermission=true
?filter[ownerId][eq]=another_user
~~~

Trừ khi đây là chức năng được thiết kế riêng, kiểm tra quyền mạnh và mô tả hợp đồng. Việc nối chuỗi predicate động có nhiều nhánh OR dễ vô tình làm mất ràng buộc tenant; dùng nhóm logic rõ ràng khi build query.

## 8. Sắp xếp và phân trang cũng cần allowlist

Filter có giới hạn nhưng `sort=internalCost` hoặc `sort=customer.passwordHash` vẫn là lỗi kiến trúc. Trong ví dụ, chỉ công bố:

~~~text
sort=-createdAt  # mới nhất trước, mặc định
sort=createdAt   # cũ nhất trước
~~~

Server tự thêm **khóa phụ ổn định** (ví dụ `publicId`) để tạo thứ tự toàn phần:

~~~sql
ORDER BY created_at DESC, public_id DESC
~~~

Khi hai đơn có cùng `created_at`, `public_id` phân định thứ tự. Nếu client chỉ sắp xếp theo timestamp không duy nhất, kết quả có thể bị lặp hoặc thiếu khi phân trang.

### 8.1. Offset và cursor

| Cơ chế | Ví dụ | Ưu điểm | Giới hạn |
|---|---|---|---|
| Offset/limit | `?offset=1000&limit=20` | Đơn giản khi dữ liệu nhỏ | Trang sâu có thể đắt; thêm/xóa dữ liệu có thể làm bỏ sót/lặp |
| Keyset/cursor | `?cursor=opaque...&limit=20` | Tốt hơn cho tập lớn theo sort ổn định | Cursor phải mang ngữ cảnh filter/sort và có thời hạn |

Với sort giảm dần theo `createdAt` và `publicId`, trang tiếp theo có thể được xác định bởi:

~~~sql
AND (
  o.created_at < :last_created_at
  OR (o.created_at = :last_created_at AND o.public_id < :last_public_id)
)
ORDER BY o.created_at DESC, o.public_id DESC
LIMIT :limit_plus_one;
~~~

Mẫu này giả định `createdAt` và `publicId` không đổi sau khi tạo, và phép so sánh ID trong database có thứ tự ổn định. Nếu sort tăng dần, dấu so sánh đổi theo. Nếu sort theo trường có thể sửa, tính ổn định của cursor cần được phân tích thêm.

### 8.2. Cursor phải bị ràng buộc với filter

Cursor là một phần của hợp đồng tìm kiếm; không phải chuỗi tùy ý do client sửa. Một payload logic có thể chứa:

~~~json
{
  "version": 1,
  "lastCreatedAt": "2026-11-15T12:30:00Z",
  "lastPublicId": "ord_916",
  "sort": "-createdAt",
  "normalizedFilterHash": "sha256-of-canonical-filter",
  "scopeHash": "hash-of-authorized-tenant-and-principal",
  "expiresAt": "2026-11-18T10:00:00Z"
}
~~~

Đây là **mô hình logic trước khi tạo cursor**, không phải lời khuyên trả trực tiếp payload trên cho client. Cursor công khai nên opaque, được ký/MAC hoặc bảo vệ chống giả mạo theo thiết kế và kiểm tra phiên bản, thời hạn, sort, filter, phạm vi truy cập trước khi dùng. Đừng coi Base64 là mã hóa hay chữ ký. Không đưa token bí mật hoặc thông tin cá nhân vào cursor không mã hóa.

Khi client đổi filter trong lúc tiếp tục cursor cũ, API **từ chối** thay vì tự chèn kết quả của truy vấn khác. Hãy trả mã lỗi hợp đồng như `400 INVALID_CURSOR` để client bắt đầu lại truy vấn.

**Lưu ý về dữ liệu thay đổi:** Keyset giúp giảm vấn đề offset sâu, nhưng không bảo đảm snapshot nhất quán tuyệt đối khi row có thể được thêm, xóa hoặc cập nhật trong quá trình duyệt. Nếu cần xuất toàn bộ tập tại một thời điểm, hãy dùng snapshot/transaction hoặc tác vụ export được thiết kế riêng.

### 8.3. Phản hồi collection có nextCursor

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: private, no-store

{
  "data": [
    {
      "id": "ord_916",
      "status": "PAID",
      "currency": "VND",
      "totalAmount": "250000",
      "createdAt": "2026-11-15T12:30:00Z"
    }
  ],
  "page": {
    "limit": 20,
    "nextCursor": "eyJ2Ijo...opaque...",
    "hasMore": true
  }
}
~~~

`hasMore` có thể được xác định bằng cách truy vấn tối đa `limit + 1` bản ghi. Đừng lấy toàn bộ dữ liệu rồi cắt ở bộ nhớ để làm pagination. Không tính `totalCount` một cách mặc định nếu count trên tập lớn rất đắt hoặc dễ lộ số lượng bản ghi ngoài phạm vi quyền; cung cấp count nếu có nhu cầu và chi phí chấp nhận được.

## 9. Chống SQL injection chưa đủ: phải chặn query injection về năng lực

Phân biệt hai vấn đề:

1. **SQL injection:** giá trị đầu vào bị ghép vào chuỗi SQL và thay đổi cú pháp truy vấn.
2. **Query capability abuse:** client chỉ dùng cú pháp hợp lệ nhưng được cấp khả năng lọc/sort/join/scan quá mạnh, gây lộ thông tin hoặc làm quá tải DB.

Dùng prepared statement, bind parameters và ORM là cần thiết để bảo vệ **giá trị**. Nhưng danh sách field, toán tử, tên cột sắp xếp và hướng sort thường **không thể bind như một giá trị SQL**; chúng phải đi qua mapping cố định do server chọn.

### 9.1. Ví dụ SQL nguy hiểm

~~~java
// PHẢN MẪU: không sử dụng trong production.
String sql = "SELECT * FROM orders WHERE " +
             request.getParameter("where") +
             " ORDER BY " + request.getParameter("sort");
~~~

Ngay cả nếu chỉ tham số hóa `value` nhưng lấy `field` và `operator` trực tiếp để nối, client vẫn có thể chạm vào cột không được duyệt. Không coi `replace("'", "")` hoặc blacklist vài chuỗi SQL là đủ.

### 9.2. Biên dịch từ registry cố định

Mô hình an toàn hơn:

~~~text
HTTP decoded parameter
    -> strict parser
    -> allowlisted field/operator
    -> typed value + bounded QuerySpec
    -> authorized scope from principal
    -> static mapping to expression/predicate
    -> parameterized values
    -> bounded result page
~~~

Ví dụ mapping:

~~~text
Public field       Internal query mapping
------------------------------------------
createdAt           orders.created_at_utc
status              orders.lifecycle_status
currency            orders.currency_code
totalAmount         orders.gross_amount
orderCode           orders.public_order_code
~~~

Mapping này thuộc backend và có thể đổi khi database refactor. Nó không được hình thành bằng quy tắc “field query == tên thuộc tính entity” cho mọi field.

### 9.3. Prefix search và ký tự đặc biệt

Nếu dùng SQL `LIKE` cho prefix, tham số chứa `%` hoặc `_` có thể hoạt động như wildcard theo SQL. Trong hợp đồng mẫu, `orderCode` chỉ chấp nhận `A-Z`, `0-9` và `-`, nên hai ký tự đó không đi qua validation. Nếu về sau cho phép ký tự khác, phải escape đúng wildcard và ký tự escape theo DB dialect:

~~~sql
WHERE o.order_code LIKE :escaped_prefix_pattern ESCAPE '\'
~~~

Trong mẫu SQL, cơ chế escape cần được kiểm chứng với dialect cụ thể. Parameterization chống thay đổi **cú pháp SQL**, còn escaping ở đây kiểm soát **ngữ nghĩa LIKE**. Prefix scan chỉ có lợi nếu index/collation phù hợp; không khẳng định mọi DB sẽ sử dụng index khi có `LIKE 'ABC%'`.

## 10. Thiết kế lớp parsing/validation trong Java/Spring

Spring MVC có thể nhận query string sau khi decode dưới dạng `MultiValueMap<String, String>`. Không chỉ dùng `@RequestParam Map<String,String>` nếu muốn phát hiện duplicate, vì map một giá trị có thể làm mất thông tin client đã gửi tham số hai lần.

### 10.1. Kiểu dữ liệu nội bộ sau khi parse

~~~java
import java.math.BigDecimal;
import java.time.Instant;
import java.util.Set;

enum OrderStatus {
    PENDING_PAYMENT, PAID, SHIPPED, CANCELLED
}

enum SupportedCurrency {
    VND, USD
}

record OrderFilters(
    Instant createdFrom,
    Instant createdBefore,
    Set<OrderStatus> statuses,
    SupportedCurrency currency,
    BigDecimal minAmount,
    BigDecimal beforeAmount,
    String orderCodePrefix
) {}

record OrderQuerySpec(
    OrderFilters filters,
    boolean newestFirst,
    int limit,
    String cursor
) {}
~~~

`OrderQuerySpec` là hợp đồng giữa API layer và query service; nó có **kiểu mạnh**, không giữ một chuỗi SQL do client đưa vào. Dùng `BigDecimal` cho tiền, `Instant` cho thời điểm, enum cho trạng thái và currency. Phải lưu ý `Set` bỏ thứ tự và có thể bỏ trùng; hãy **phát hiện giá trị trùng trước khi tạo Set**.

### 10.2. Registry và tên query parameter

~~~java
import java.util.Set;
import java.util.regex.Pattern;

final class OrderFilterContract {
    static final Set<String> FILTER_KEYS = Set.of(
        "filter[createdAt][gte]",
        "filter[createdAt][lt]",
        "filter[status][in]",
        "filter[currency][eq]",
        "filter[totalAmount][gte]",
        "filter[totalAmount][lt]",
        "filter[orderCode][prefix]"
    );
    static final Set<String> CONTROL_KEYS =
        Set.of("sort", "limit", "cursor");

    static final Pattern PREFIX =
        Pattern.compile("[A-Z0-9-]{2,12}");

    private OrderFilterContract() {}

    static boolean isKnown(String key) {
        return FILTER_KEYS.contains(key) || CONTROL_KEYS.contains(key);
    }
}
~~~

Ở hệ thống có nhiều collection, registry nên là cấu trúc rõ theo endpoint/role; không tạo một `FilterRegistry` toàn ứng dụng cho phép mọi resource chia sẻ toàn bộ field chỉ vì trùng tên. Mapping nội bộ có thể tái sử dụng an toàn nhưng allowlist công khai phải do resource chịu trách nhiệm.

### 10.3. Parse chặt và trả lỗi rõ

Ví dụ parser trọng tâm, dùng `MultiValueMap` để từ chối unknown/duplicate và kiểm tra giới hạn. Các helper được tách để nhìn rõ ý nghĩa; phần lỗi được ánh xạ sang `400 Bad Request` ở tầng HTTP.

~~~java
import java.math.BigDecimal;
import java.time.Duration;
import java.time.Instant;
import java.time.OffsetDateTime;
import java.time.format.DateTimeParseException;
import java.util.Arrays;
import java.util.HashSet;
import java.util.List;
import java.util.Set;
import org.springframework.util.MultiValueMap;

final class OrderQueryParser {
    OrderQuerySpec parse(MultiValueMap<String, String> params) {
        if (params.size() > 12) {
            throw bad("TOO_MANY_PARAMETERS");
        }
        long filterCount = params.keySet().stream()
            .filter(k -> k.startsWith("filter["))
            .count();
        if (filterCount > 8) {
            throw bad("TOO_MANY_FILTERS");
        }

        for (var entry : params.entrySet()) {
            String key = entry.getKey();
            List<String> values = entry.getValue();
            if (!OrderFilterContract.isKnown(key)) {
                throw bad("UNKNOWN_QUERY_PARAMETER");
            }
            if (values == null || values.size() != 1
                    || values.get(0) == null
                    || values.get(0).isBlank()) {
                throw bad("DUPLICATE_OR_EMPTY_PARAMETER");
            }
        }

        Instant from = instant(required(params, "filter[createdAt][gte]"));
        Instant before = instant(required(params, "filter[createdAt][lt]"));
        Duration range = Duration.between(from, before);
        if (range.isZero() || range.isNegative()
                || range.compareTo(Duration.ofDays(90)) > 0) {
            throw bad("DATE_RANGE_OUT_OF_BOUNDS");
        }

        Set<OrderStatus> statuses = parseStatuses(
            optional(params, "filter[status][in]"));
        SupportedCurrency currency = parseCurrency(
            optional(params, "filter[currency][eq]"));
        BigDecimal minAmount = decimal(
            optional(params, "filter[totalAmount][gte]"));
        BigDecimal beforeAmount = decimal(
            optional(params, "filter[totalAmount][lt]"));
        if ((minAmount != null || beforeAmount != null)
                && currency == null) {
            throw bad("CURRENCY_REQUIRED_FOR_AMOUNT");
        }
        if (minAmount != null && beforeAmount != null
                && minAmount.compareTo(beforeAmount) >= 0) {
            throw bad("INVALID_AMOUNT_RANGE");
        }

        String prefix = optional(params, "filter[orderCode][prefix]");
        if (prefix != null
                && !OrderFilterContract.PREFIX.matcher(prefix).matches()) {
            throw bad("INVALID_ORDER_CODE_PREFIX");
        }

        String sort = optional(params, "sort");
        if (sort == null) sort = "-createdAt";
        if (!sort.equals("-createdAt") && !sort.equals("createdAt")) {
            throw bad("UNSUPPORTED_SORT");
        }

        String pageSize = optional(params, "limit");
        int limit = parseLimit(pageSize == null ? "20" : pageSize);
        String cursor = optional(params, "cursor");
        if (cursor != null && cursor.length() > 2048) {
            throw bad("CURSOR_TOO_LONG");
        }
        // Query service phải kiểm chứng chữ ký, expiry, filter hash,
        // sort và phạm vi quyền của cursor trước khi truy vấn.
        return new OrderQuerySpec(
            new OrderFilters(from, before, statuses, currency,
                             minAmount, beforeAmount, prefix),
            sort.equals("-createdAt"), limit, cursor);
    }

    private static String required(
            MultiValueMap<String, String> p, String key) {
        String v = p.getFirst(key);
        if (v == null) throw bad("MISSING_REQUIRED_FILTER");
        return v;
    }

    private static String optional(
            MultiValueMap<String, String> p, String key) {
        return p.getFirst(key);
    }

    private static Instant instant(String v) {
        try {
            return OffsetDateTime.parse(v).toInstant();
        } catch (DateTimeParseException ex) {
            throw bad("INVALID_DATETIME");
        }
    }

    private static Set<OrderStatus> parseStatuses(String v) {
        if (v == null) return Set.of();
        String[] parts = v.split(",", -1);
        if (parts.length == 0 || parts.length > 5) {
            throw bad("INVALID_STATUS_LIST");
        }
        Set<OrderStatus> result = new HashSet<>();
        try {
            for (String part : parts) {
                if (!part.equals(part.strip()) || part.isEmpty()
                        || !result.add(OrderStatus.valueOf(part))) {
                    throw bad("INVALID_OR_DUPLICATE_STATUS");
                }
            }
        } catch (IllegalArgumentException ex) {
            throw bad("INVALID_OR_DUPLICATE_STATUS");
        }
        return Set.copyOf(result);
    }

    private static SupportedCurrency parseCurrency(String v) {
        if (v == null) return null;
        try {
            return SupportedCurrency.valueOf(v);
        } catch (IllegalArgumentException ex) {
            throw bad("UNSUPPORTED_CURRENCY");
        }
    }

    private static BigDecimal decimal(String v) {
        if (v == null) return null;
        // Chỉ nhận cú pháp thập phân đã công bố: không exponent,
        // dấu âm, khoảng trắng hoặc phần nguyên có số 0 dẫn đầu.
        if (!v.matches("(0|[1-9][0-9]{0,8})(\\.[0-9]{1,2})?")) {
            throw bad("INVALID_DECIMAL");
        }
        try {
            BigDecimal n = new BigDecimal(v);
            if (n.signum() < 0 || n.scale() > 2
                    || n.compareTo(new BigDecimal("1000000000")) >= 0) {
                throw bad("AMOUNT_OUT_OF_BOUNDS");
            }
            return n;
        } catch (NumberFormatException ex) {
            throw bad("INVALID_DECIMAL");
        }
    }

    private static int parseLimit(String v) {
        try {
            // Chỉ nhận chữ số decimal, không nhận dấu +, -, khoảng trắng.
            if (!v.matches("[0-9]{1,3}")) throw bad("INVALID_LIMIT");
            int n = Integer.parseInt(v);
            if (n < 1 || n > 100) throw bad("LIMIT_OUT_OF_BOUNDS");
            return n;
        } catch (NumberFormatException ex) {
            throw bad("INVALID_LIMIT");
        }
    }

    private static IllegalArgumentException bad(String code) {
        return new IllegalArgumentException(code);
    }
}
~~~

Đoạn code là **mẫu parser trọng tâm**, chưa phải thư viện production hoàn chỉnh. Cần bổ sung giới hạn kích thước URL ở gateway/container, logging an toàn, error mapping, giới hạn thời gian/cost query và test sâu. Danh sách enum được parse rồi đưa vào `Set` để loại bỏ phụ thuộc thứ tự khi build query; parser đã từ chối phần tử lặp trước khi đưa vào set.

**Chi tiết quan trọng:** Trong mẫu này, `params.size()` đếm **số tên tham số phân biệt**. Vì mỗi tên chỉ được phép có đúng một giá trị, con số đó cũng giới hạn tổng số tham số có giá trị. Nếu framework hoặc proxy có cách gom query khác, cần kiểm thử request lặp và giới hạn raw URL trước khi đi vào controller.

### 10.4. Controller dùng query spec, không đưa SQL vào request

~~~java
import java.security.Principal;
import org.springframework.http.CacheControl;
import org.springframework.http.ResponseEntity;
import org.springframework.util.MultiValueMap;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/v1/orders")
class OrderListController {
    private final OrderQueryParser parser = new OrderQueryParser();
    private final OrderQueryService service;

    OrderListController(OrderQueryService service) {
        this.service = service;
    }

    @GetMapping
    ResponseEntity<OrderPageResponse> list(
            @RequestParam MultiValueMap<String, String> params,
            Principal principal) {
        // Principal chỉ đáng tin khi hệ thống authentication đã cấu hình.
        OrderQuerySpec spec = parser.parse(params);
        OrderPageResponse page = service.findVisibleOrders(
            principal.getName(), spec);
        return ResponseEntity.ok()
            .cacheControl(CacheControl.noStore())
            .body(page);
    }
}

interface OrderQueryService {
    OrderPageResponse findVisibleOrders(
        String authenticatedPrincipal, OrderQuerySpec query);
}

record OrderSummary(
    String id, String status, String currency,
    String totalAmount, java.time.Instant createdAt
) {}

record PageInfo(int limit, String nextCursor, boolean hasMore) {}
record OrderPageResponse(
    java.util.List<OrderSummary> data, PageInfo page
) {}
~~~

Controller không nhận `ownerId` hoặc `tenantId` từ query. `OrderQueryService` phải tra scope theo danh tính đã xác thực, có thể kết hợp policy theo role và từng bản ghi. Không tin `principal.getName()` có ý nghĩa tenant đầy đủ nếu mô hình quyền phức tạp: service phải lấy đúng tenant/claims đã kiểm chứng từ security context. Có thể tách parser thành Spring bean để dễ test.

### 10.5. Biên dịch truy vấn bằng mapping cố định

Ví dụ nguyên tắc với JPA Criteria API. Các field trong `root.get(...)` là **literal backend kiểm soát**, không được lấy từ raw query parameter:

~~~java
// Ví dụ xây dựng các predicate chính, không phải repository hoàn chỉnh.
CriteriaBuilder cb = entityManager.getCriteriaBuilder();
CriteriaQuery<OrderEntity> cq =
    cb.createQuery(OrderEntity.class);
Root<OrderEntity> root = cq.from(OrderEntity.class);

OrderFilters f = spec.filters();
List<Predicate> predicates = new ArrayList<>();

// Scope bắt buộc từ security layer, không lấy từ filter client.
predicates.add(cb.equal(root.get("tenantId"), scope.tenantId()));
predicates.add(cb.equal(root.get("ownerId"), scope.ownerId()));
predicates.add(cb.isFalse(root.get("deleted")));

predicates.add(cb.greaterThanOrEqualTo(
    root.<Instant>get("createdAtUtc"), f.createdFrom()));
predicates.add(cb.lessThan(
    root.<Instant>get("createdAtUtc"), f.createdBefore()));

if (!f.statuses().isEmpty()) {
    predicates.add(root.get("lifecycleStatus").in(f.statuses()));
}
if (f.currency() != null) {
    predicates.add(cb.equal(root.get("currencyCode"), f.currency()));
}
if (f.minAmount() != null) {
    predicates.add(cb.greaterThanOrEqualTo(
        root.<BigDecimal>get("grossAmount"), f.minAmount()));
}
if (f.beforeAmount() != null) {
    predicates.add(cb.lessThan(
        root.<BigDecimal>get("grossAmount"), f.beforeAmount()));
}
if (f.orderCodePrefix() != null) {
    predicates.add(cb.like(
        root.get("publicOrderCode"),
        f.orderCodePrefix() + "%"));
}

// Giải mã/xác minh cursor rồi bổ sung keyset predicate.
// Dùng mapping cố định và direction tương ứng, không raw SQL.
cq.where(cb.and(predicates.toArray(Predicate[]::new)));
cq.orderBy(spec.newestFirst()
    ? List.of(cb.desc(root.get("createdAtUtc")),
              cb.desc(root.get("publicId")))
    : List.of(cb.asc(root.get("createdAtUtc")),
              cb.asc(root.get("publicId"))));
~~~

Ở đây `root.get("...")` là **tên thuộc tính Java persistence đã được lập trình viên lựa chọn**, không phải tên field client gửi. Một triển khai thật cần xử lý cursor, chọn projection thay vì đọc entity rộng, giới hạn số row `limit+1`, truy vấn tenant-scope chính xác và bảo vệ kiểu dữ liệu. Enum `OrderStatus`/`SupportedCurrency` phải được mapper chuyển sang kiểu persistence nếu khác. Với API quản trị đa tenant, điều kiện scope có thể là tập quyền phức tạp hơn hai điều kiện bằng nhau nhưng tuyệt đối không được bỏ qua.

Nếu chuyển sang JdbcTemplate, jOOQ, Querydsl hoặc native SQL, nguyên tắc không đổi: **tên trường/toán tử/ORDER BY đến từ registry tĩnh; giá trị đến từ bind parameter**. SQL escaping thủ công không thay thế việc tách hai nguồn này.

## 11. Kiểm soát chi phí thực thi: parser hợp lệ chưa có nghĩa query rẻ

Một bộ lọc đã qua validation vẫn có thể chậm vì dữ liệu phân bố không đều, index không đúng, thống kê DB cũ, tài khoản quá nhiều đơn hoặc query tranh chấp tài nguyên với workload khác. **Giới hạn cú pháp** là lớp bảo vệ đầu tiên; **giới hạn vận hành** là lớp tiếp theo.

### 11.1. Cần đo các loại chi phí nào?

| Nguồn chi phí | Ví dụ | Kiểm soát khả dĩ |
|---|---|---|
| Quét dữ liệu | Khoảng ngày 90 ngày với tenant có nhiều triệu đơn | Index theo tenant/scope/time; giới hạn ngày, dữ liệu lưu trữ lạnh |
| Sort | Sắp theo trường không có index, nhiều row cần sort | Allowlist sort; thứ tự gắn index, limit phù hợp |
| Join | Lọc theo quan hệ nhiều-nhiều | Không cho điều hướng quan hệ tùy ý; dùng truy vấn chuyên biệt |
| Băng thông/serialization | Response chứa mọi chi tiết dòng hàng | Projection tối thiểu, phân trang, endpoint chi tiết riêng |
| Count | `COUNT(*)` trên tập lớn theo nhiều predicate | Bỏ count mặc định; chỉ hỗ trợ khi có bằng chứng đủ rẻ |
| Connection/CPU DB | Nhiều filter khác nhau từ bot hoặc script | Quota, pool riêng, concurrency limit, timeout |
| Cache fragmentation | Hàng nghìn URI filter khác nhau | Canonicalize, TTL phù hợp, không cache shared dữ liệu nhạy cảm |
| Deep pagination | Offset quá lớn | Cursor/keyset, token có thời hạn |

### 11.2. Index phải phục vụ query thực

Trong ví dụ, truy vấn phổ biến gồm:

~~~sql
WHERE tenant_id = :tenant
  AND owner_id = :user
  AND created_at >= :from
  AND created_at < :to
ORDER BY created_at DESC, public_id DESC
LIMIT :limit_plus_one
~~~

Một index ứng viên tùy hệ quản trị:

~~~sql
CREATE INDEX idx_orders_owner_time_id
ON orders (tenant_id, owner_id, created_at DESC, public_id DESC);
~~~

Không kết luận index này tối ưu cho mọi truy vấn. Khi thêm filter `status`/`currency` hoặc range `totalAmount`, kế hoạch thực tế có thể khác tùy độ chọn lọc, cardinality, điều kiện scope và khả năng sử dụng index. Hãy dùng công cụ phân tích query plan của DB trên dữ liệu đại diện; đo scanned rows, latency p95/p99, memory, I/O và mức ảnh hưởng đến truy vấn khác. Tránh tạo hàng chục index cho mọi tổ hợp filter vì index cũng tốn dung lượng và chi phí ghi.

### 11.3. Query timeout và cơ chế chống lạm dụng

Một số lớp bảo vệ hữu ích:

1. **Gateway:** giới hạn độ dài URI, số connection và tần suất request; chặn request quá lớn trước ứng dụng.
2. **Parser:** từ chối field, operator, số điều kiện, kiểu dữ liệu hoặc khoảng ngày ngoài hợp đồng.
3. **Authorization:** áp dụng tenant/owner scope và giới hạn các field nhạy cảm.
4. **Query execution:** giới hạn số row, thời gian chạy và resource budget theo khả năng DB/driver; có phương án hủy query khi vượt ngưỡng.
5. **Observability:** phân nhóm query theo **template/canonical shape**, không ghi thẳng dữ liệu cá nhân trong chuỗi filter vào log.
6. **Product decision:** truy vấn quá nặng chuyển sang export/report job chạy nền có quota, không âm thầm nâng giới hạn collection endpoint.

Time limit cần được phối hợp giữa HTTP request timeout, DB statement timeout, connection timeout và hệ thống retry. Nếu HTTP client timeout nhưng query vẫn tiếp tục chạy phía DB, tải có thể chồng lên nhau. Hãy kiểm tra khả năng cancel query và circuit breaker khi backend quá tải.

### 11.4. Đánh đổi giữa linh hoạt và kiểm soát

Một API cho phép mọi biểu thức SQL sẽ “linh hoạt” với người dùng đầu tiên nhưng có chi phí bảo mật và vận hành rất cao. Ngược lại, quá ít filter có thể khiến client tải hàng trăm trang rồi lọc ở frontend — tăng băng thông, độ trễ và thậm chí tạo rủi ro khi trả dữ liệu không cần thiết. Mục tiêu là **tập filter nhỏ nhưng đủ phục vụ hành trình thực**, có chỉ số sử dụng và đường mở rộng có kiểm soát.

## 12. OpenAPI: công bố từng tham số đã được phép

OpenAPI giúp client và SDK biết endpoint hỗ trợ gì, thay vì đoán từ tên cột DB hoặc thử nhiều kiểu query. Với cú pháp ngoặc vuông, cách đơn giản là khai báo **từng parameter với tên đầy đủ**, không dùng một object tùy ý gồm mọi field chưa biết.

Ví dụ OpenAPI 3.1 rút gọn:

~~~yaml
openapi: 3.1.0
info:
  title: Orders Collection API
  version: 1.0.0
paths:
  /v1/orders:
    get:
      summary: Liệt kê các đơn được phép xem với filter có giới hạn
      description: |
        Các filter kết hợp bằng AND.
        status[in] có nghĩa OR giữa các giá trị enum.
        createdAt[gte] và createdAt[lt] cùng bắt buộc,
        khoảng nửa mở tối đa 90 ngày.
        Không chấp nhận unknown hoặc duplicated query parameters.
      security:
        - bearerAuth: []
      parameters:
        - name: filter[createdAt][gte]
          in: query
          required: true
          description: Mốc bắt đầu, tính cả mốc, có timezone offset
          schema:
            type: string
            format: date-time
        - name: filter[createdAt][lt]
          in: query
          required: true
          description: Mốc kết thúc, không tính mốc, tối đa 90 ngày
          schema:
            type: string
            format: date-time
        - name: filter[status][in]
          in: query
          required: false
          description: |
            Một chuỗi enum cách nhau bằng dấu phẩy, tối đa 5
            giá trị không trùng; ví dụ PAID,SHIPPED.
            Không dùng mảng nhiều lần cùng tên query key.
          schema:
            type: string
        - name: filter[currency][eq]
          in: query
          required: false
          schema:
            type: string
            enum: [VND, USD]
        - name: filter[totalAmount][gte]
          in: query
          required: false
          description: Decimal không âm, tối đa hai chữ số thập phân
          schema:
            type: string
        - name: filter[totalAmount][lt]
          in: query
          required: false
          schema:
            type: string
        - name: filter[orderCode][prefix]
          in: query
          required: false
          schema:
            type: string
            pattern: '^[A-Z0-9-]{2,12}$'
        - name: sort
          in: query
          schema:
            type: string
            enum: ['-createdAt', 'createdAt']
            default: '-createdAt'
        - name: limit
          in: query
          schema:
            type: integer
            minimum: 1
            maximum: 100
            default: 20
        - name: cursor
          in: query
          description: Opaque cursor từ response trước, cùng filter/sort
          schema:
            type: string
            maxLength: 2048
      responses:
        '200':
          description: Danh sách đơn đã lọc trong phạm vi được phân quyền
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/OrderPage'
        '400':
          description: Filter, sort, limit hoặc cursor không hợp lệ
          content:
            application/problem+json:
              schema:
                $ref: '#/components/schemas/Problem'
        '401':
          description: Thiếu hoặc sai thông tin xác thực
        '403':
          description: Không có quyền sử dụng collection
        '414':
          description: URI dài hơn giới hạn chấp nhận
        '429':
          description: Vượt tần suất truy vấn cho phép
        '503':
          description: Dịch vụ tạm thời không sẵn sàng
components:
  securitySchemes:
    bearerAuth:
      type: http
      scheme: bearer
  schemas:
    OrderPage:
      type: object
      required: [data, page]
      properties:
        data:
          type: array
          items:
            $ref: '#/components/schemas/OrderSummary'
        page:
          type: object
          required: [limit, hasMore]
          properties:
            limit: {type: integer}
            hasMore: {type: boolean}
            nextCursor:
              type: [string, 'null']
    OrderSummary:
      type: object
      required: [id, status, currency, totalAmount, createdAt]
      properties:
        id: {type: string}
        status: {type: string}
        currency: {type: string}
        totalAmount: {type: string}
        createdAt: {type: string, format: date-time}
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

Các giá trị URI, giới hạn và enum ở đây thuộc hợp đồng ví dụ. **OpenAPI tự thân không thực thi** chính sách từ chối unknown query parameter, duplicate hoặc ràng buộc “có amount thì phải có currency”. Parser runtime và contract tests phải bảo đảm chúng thực sự được thực hiện. OpenAPI 3.1 hỗ trợ JSON Schema ở phần schema nhưng ràng buộc liên tham số query cần mô tả và kiểm thử riêng.

Với `filter[status][in]`, schema được mô tả là **một string** cố ý, thay vì khai báo array khiến generator có thể serialize thành nhiều tham số cùng tên hoặc cách khác. Nếu muốn thiết kế array chuẩn, cần chọn một quy tắc serialization nhất quán (`style`, `explode`) và cập nhật parser, ví dụ và kiểm thử theo quy tắc đó.

## 13. HTTP status và lỗi khi từ chối truy vấn

Để API có thể tích hợp dễ, **không chỉ trả 200 kèm danh sách rỗng** cho filter sai. Danh sách rỗng nghĩa là không có bản ghi khớp với **truy vấn hợp lệ**. Filter không hợp lệ phải có mã lỗi rõ để client biết cần sửa request.

| Tình huống | Status đề xuất | Lý do |
|---|---|---|
| Field/operator không thuộc allowlist | `400 Bad Request` | Không phù hợp hợp đồng query |
| Thiếu một trong hai mốc ngày | `400 Bad Request` | Thiếu điều kiện bắt buộc |
| Ngày sai định dạng, từ ≥ đến, range > 90 ngày | `400 Bad Request` | Giá trị vượt ràng buộc |
| Trùng tham số hoặc giá trị enum trùng | `400 Bad Request` | Cú pháp không rõ ràng |
| Currency thiếu khi có amount | `400 Bad Request` | Ràng buộc ngữ nghĩa theo hợp đồng ví dụ |
| Sort/cursor không hỗ trợ hoặc cursor sai filter | `400 Bad Request` | Không thể thực hiện đúng truy vấn đã yêu cầu |
| Người gọi chưa xác thực | `401 Unauthorized` | Yêu cầu danh tính hợp lệ |
| Người gọi không có quyền xem collection | `403 Forbidden` | Phân quyền, không phải lỗi cú pháp |
| URI quá dài theo server/gateway | `414 URI Too Long` | Giới hạn request target |
| Vượt quota/tần suất | `429 Too Many Requests` | Cần giảm request; có thể kèm `Retry-After` |
| Query backend đang lỗi hoặc tạm quá tải | `503 Service Unavailable` nếu phù hợp | Sự cố tạm thời phía dịch vụ |

API khác có thể dùng `422 Unprocessable Content` cho một số ràng buộc ngữ nghĩa, nhưng ở đây chủ động chọn **400 cho mọi lỗi filter/validation của query string**. Điều quan trọng là quy tắc nhất quán và được tài liệu hóa, tránh tự đổi mã lỗi theo từng branch.

### 13.1. Problem Details khi filter không hợp lệ

~~~http
HTTP/1.1 400 Bad Request
Content-Type: application/problem+json
Cache-Control: no-store

{
  "type": "https://api.example.test/problems/invalid-filter",
  "title": "Invalid collection filter",
  "status": 400,
  "code": "UNSUPPORTED_FILTER",
  "detail": "Truy vấn chứa một filter không được hỗ trợ.",
  "invalidParams": [
    {
      "name": "filter[customer.email][contains]",
      "reason": "Unsupported filter"
    }
  ]
}
~~~

`invalidParams` và `code` là các **extension member do API định nghĩa** bên cạnh cấu trúc Problem Details chuẩn. URI trong `type` chỉ là ví dụ; khi công bố thật cần định nghĩa và duy trì loại lỗi ổn định. Với field nhạy cảm, có thể dùng thông báo ít chi tiết hơn để tránh xác nhận sự tồn tại của thuộc tính nội bộ.

Không lặp toàn bộ raw query string vào log/error response nếu nó có thể chứa email, ID nhạy cảm, token hoặc chuỗi dài. Với input quá mức, log mã lỗi, endpoint và thông tin đo lường an toàn; chỉ lưu giá trị đầu vào cần thiết theo chính sách bảo mật và retention.

### 13.2. Ánh xạ lỗi parser trong Spring

~~~java
import java.net.URI;
import org.springframework.http.HttpStatus;
import org.springframework.http.ProblemDetail;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
class ApiProblemHandler {
    @ExceptionHandler(IllegalArgumentException.class)
    ProblemDetail invalidQuery(IllegalArgumentException ex) {
        ProblemDetail p = ProblemDetail.forStatus(
            HttpStatus.BAD_REQUEST);
        p.setTitle("Invalid collection filter");
        p.setType(URI.create(
            "https://api.example.test/problems/invalid-filter"));
        // Trong production, bắt exception chuyên biệt thay vì
        // mọi IllegalArgumentException của toàn ứng dụng.
        p.setProperty("code", ex.getMessage());
        return p;
    }
}
~~~

Ví dụ này cố ý **rút gọn**, nhằm cho thấy mapping sang Problem Details. Trong production nên tạo `InvalidOrderQueryException` hoặc loại exception có code rõ và chỉ handler cho loại đó; nếu bắt mọi `IllegalArgumentException` toàn ứng dụng sẽ vô tình biến lỗi lập trình trong service thành lỗi 400. Không đưa stack trace hoặc raw values nguy hiểm vào `detail`.

## 14. Cache, nhất quán dữ liệu và canonical query

HTTP GET có thể cache trong những điều kiện phù hợp, nhưng kết quả collection thường bị ảnh hưởng bởi:

- Quyền và tenant của người gọi.
- Bộ filter, sort, limit và cursor.
- Trạng thái dữ liệu thay đổi theo thời gian.
- Phiên bản contract, representation và các tùy chọn locale nếu có.

Nếu cache dựa trên `/v1/orders` mà **bỏ qua query string**, client có thể nhận nhầm trang hoặc kết quả của filter khác. Nếu cache được chia sẻ giữa nhiều user mà không phân vùng quyền, nguy cơ lộ dữ liệu rất nghiêm trọng.

### 14.1. Chính sách cache cho collection riêng tư

Với đơn hàng chứa dữ liệu người dùng, lựa chọn bảo thủ:

~~~http
Cache-Control: no-store
~~~

Hoặc nếu ứng dụng có yêu cầu cache cục bộ được kiểm soát:

~~~http
Cache-Control: private, max-age=15
~~~

Chọn lựa phụ thuộc vào yêu cầu riêng tư, tính mới và nơi client lưu dữ liệu. `private` không cho phép shared cache lưu response theo ngữ nghĩa HTTP, nhưng không thay thế phân quyền ở API; `no-store` ngăn cache lưu phản hồi theo chỉ thị. Đừng tự động cho cache chung chỉ vì GET là phương thức safe.

Một `ETag` cho collection (nếu cung cấp) phải phản ánh representation cụ thể của **filter, sort, phạm vi quyền và phiên bản dữ liệu**; ETag của danh sách đơn thuộc user A không được dùng để xác nhận cache của user B. `304 Not Modified` giảm payload, không mặc nhiên làm giảm số request hoặc chi phí tính toán nếu server vẫn phải chạy query để xác định tính mới.

### 14.2. URI/cursor khác nhau có thể biểu diễn cùng điều kiện

Nếu server canonicalize để tạo cache/fingerprint, cần thống nhất:

1. Tên field/operator theo allowlist cố định.
2. Thứ tự query parameter không ảnh hưởng logic AND.
3. Giá trị enum `in` có thể được sắp xếp khi tạo hash **sau** khi xác nhận không trùng, nếu hợp đồng coi thứ tự không có nghĩa.
4. Timestamp có thể chuẩn về UTC `Instant` theo độ chính xác đã công bố.
5. Khoảng ngày, currency, sort và tenant scope phải nằm trong fingerprint.

Đừng lấy chuỗi query thô do client gửi làm **SQL fragment** hoặc làm nguồn phân quyền. Hai URL có thứ tự parameter khác nhau không có nghĩa hai bộ quyền khác nhau.

## 15. Kiểm thử hợp đồng: đặc biệt chú trọng trường hợp bị từ chối

Một bộ test chỉ chạy happy path như `status=PAID` là chưa đủ. Rủi ro thường nằm ở field lạ, operator lạ, nhiều giá trị, request lớn, tenant bị thay và query sau khi dữ liệu thay đổi.

### 15.1. Ma trận kiểm thử parser

| Kịch bản | Input mẫu | Kỳ vọng |
|---|---|---|
| Điều kiện cơ bản | Hai mốc createdAt hợp lệ | Parse thành `Instant` và khoảng nửa mở |
| Enum nhiều giá trị | `status[in]=PAID,SHIPPED` | Hai giá trị, logic OR bên trong điều kiện |
| Kết hợp field | Date + status + currency | Logic AND giữa field, không lẫn OR |
| Thiếu createdAt lt | Chỉ `createdAt[gte]` | 400, không chạy query |
| Khoảng bằng 0/âm | `from >= to` | 400 |
| Khoảng vượt 90 ngày | 91 ngày | 400, không quét DB |
| Timezone không rõ | `2026-11-01T00:00:00` | 400, không đoán timezone |
| Giá trị thời gian sai | `next-friday` | 400 |
| Enum sai | `PAID,UNKNOWN` | 400 |
| Enum trùng | `PAID,PAID` | 400 |
| Danh sách trống | `PAID,` | 400 |
| Có khoảng tiền, thiếu currency | `totalAmount[gte]=100` | 400 |
| Tiền âm hoặc quá lớn | `-1` hoặc vượt cap | 400 |
| Tiền không đúng format | `NaN`, exponent nếu không hỗ trợ, >2 số thập phân | 400 |
| Prefix ngắn/wildcard | `A`, `ORD%`, `ORD_` | 400 |
| Field ngoài allowlist | `fraudScore[gte]` | 400 |
| Đường dẫn quan hệ | `customer.email[contains]` | 400 |
| Operator không hỗ trợ | `createdAt[regex]` | 400 |
| Duplicate query key | Hai `filter[status][in]` | 400, không getFirst im lặng |
| Query parameter lạ | `includeDeleted=true` | 400 |
| Sort không hỗ trợ | `sort=-internalCost` | 400 |
| Limit vượt max | `limit=10000` | 400 |
| Cursor không hợp lệ | Bị sửa, hết hạn, khác filter | 400 hoặc mã lỗi hợp đồng riêng |
| URI quá dài | Vượt gateway limit | Bị chặn trước query, thường 414 |

### 15.2. Test bảo mật và quyền truy cập

| Kịch bản | Kỳ vọng |
|---|---|
| Người dùng A truy vấn đơn của mình | Chỉ đơn thuộc A và tenant của A |
| Người dùng A gửi `tenantId=t_other` | Bị từ chối, không đổi scope |
| Người dùng A đoán ID hoặc field nội bộ | Không thấy dữ liệu ngoài quyền hoặc suy ra giá trị nhạy cảm |
| Cursor từ user A dùng bởi user B | Từ chối, không truy vấn phạm vi của A |
| Cursor trước khi quyền bị thu hồi | Bị kiểm tra lại với quyền hiện tại, không được dùng quyền cũ |
| Nhân viên support khác tenant dùng cùng filter | Chỉ kết quả trong quyền hiện tại |
| API cache có nhiều principal | Không trả response/ETag của người này cho người khác |
| Filter giá trị độc hại `' OR 1=1 --` | Bị reject theo type/allowlist, không thay đổi SQL |

Với bộ lọc chỉ cho phép enum, timestamp, decimal và prefix chuẩn, nhiều chuỗi injection sẽ bị từ chối ngay ở parser. Tuy vậy vẫn cần sử dụng parameterized queries trong persistence layer: validation không thay thế an toàn ở DB.

### 15.3. Test hiệu năng và phân trang

- Tạo dữ liệu đại diện với tenant lớn và nhỏ; đo p95/p99 và DB scanned rows cho các query shape quan trọng.
- Lấy trang 1, trang 2 theo cursor: không lặp/bỏ sót trong trường hợp tập dữ liệu không thay đổi.
- Tạo hai đơn cùng thời điểm `createdAt` để xác minh thứ tự phụ `publicId`.
- Thử thêm/xóa đơn giữa hai trang; mô tả mức nhất quán thực tế, không giả định snapshot.
- Thử sort tăng dần và giảm dần, giới hạn 1 và 100, rỗng kết quả, cursor ở trang cuối.
- Tăng đồng thời số request tới quota; xác minh `429` không khiến database quá tải.
- Thử query vượt timeout; đảm bảo cancel/giải phóng connection và không có retry storm.
- Xác nhận count không bị gọi mặc định nếu contract không cung cấp tổng số dòng.

### 15.4. MockMvc minh họa

~~~java
// Cần thiết lập @WebMvcTest hoặc context phù hợp, mock service,
// principal được xác thực và error handler.

mockMvc.perform(get("/v1/orders")
        .param("filter[createdAt][gte]", "2026-11-01T00:00:00Z")
        .param("filter[createdAt][lt]", "2026-12-01T00:00:00Z")
        .param("filter[status][in]", "PAID,SHIPPED")
        .param("limit", "20"))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$.data").isArray());

mockMvc.perform(get("/v1/orders")
        .param("filter[createdAt][gte]", "2026-11-01T00:00:00Z")
        .param("filter[createdAt][lt]", "2026-12-01T00:00:00Z")
        .param("filter[fraudScore][gte]", "10"))
    .andExpect(status().isBadRequest());

mockMvc.perform(get("/v1/orders")
        .param("filter[createdAt][gte]", "2026-11-01T00:00:00Z")
        .param("filter[createdAt][lt]", "2026-12-01T00:00:00Z")
        .param("filter[status][in]", "PAID", "SHIPPED"))
    .andExpect(status().isBadRequest());
~~~

Các đoạn là **assertion minh họa**, không phải test class chạy độc lập. Cần cấu hình response của mock service, security filter, principal và exception handler để xác nhận chính xác hành vi. Spring MVC tự gom nhiều giá trị `.param(...)` thành MultiValueMap; đây là lý do parser ví dụ từ chối size khác 1 trước khi gọi `getFirst()`.

### 15.5. Property-based và fuzz testing

Đối với parser phức tạp, có thể sinh ngẫu nhiên các chuỗi query nhỏ và kiểm tra bất biến:

- Parser **không** tạo SQL từ giá trị chưa được validate.
- Không tồn tại đường đầu vào nào khiến điều kiện tenant/owner bị bỏ khỏi query.
- Mọi query spec hợp lệ tuân thủ giới hạn ngày, số token, page size và allowlist.
- Cùng query logic chuẩn hóa và cùng scope cho cùng fingerprint.
- Cursor giả mạo, sai phiên bản, hết hạn hoặc thuộc principal khác không được chấp nhận.
- Parser không tiêu tốn tài nguyên tăng bất thường khi nhận chuỗi dài hoặc lặp nhiều lần.

Fuzz test giúp tìm lỗi parser, nhưng không thay cho kiểm thử tích hợp với DB, security và gateway vì các tầng có thể decode và canonicalize khác nhau.

## 16. Tình huống thực tế mô phỏng: từ filter tùy ý sang hợp đồng có giới hạn

### 16.1. Thiết kế cũ

Một hệ thống thương mại điện tử ban đầu công bố:

~~~text
GET /orders?field=<field>&op=<op>&value=<value>
           &sortBy=<column>&page=<offset>
~~~

Server dùng tên field để tạo predicate trên ORM, cho phép `contains` ở mọi string và tùy ý đi qua quan hệ như `customer.email`. Có endpoint khác chấp nhận `includeAllTenants` phục vụ việc debug. Sự cố và vấn đề phát hiện:

- Client cũ đang phụ thuộc tên cột `order_state_cd`.
- Search theo `customer.email` có thể giúp suy ra khách đã đặt hàng hay chưa, dù response không trả email.
- Một số request dùng `contains` trên chuỗi dài và `offset=500000` khiến DB chậm.
- Bộ lọc `includeAllTenants` được nhiều thành phần copy lại mà thiếu policy kiểm tra.
- Không có quy ước xử lý tham số lặp; một proxy chọn giá trị đầu, service chọn giá trị cuối.

### 16.2. Thiết kế mới

Nhóm product/engineering chọn ba use case có ưu tiên: khách xem lịch sử đơn của mình, support tra theo mã đơn, tài chính xem giao dịch theo khoảng tiền. Họ công bố contract mới với field–operator allowlist; một phiên bản được mô tả ở mục 3.

Các thay đổi:

1. Tách endpoint khách hàng khỏi nhu cầu truy vấn đặc quyền. Scope tenant/owner được áp từ security layer, không phải filter công khai.
2. Giữ tên public `status`, `createdAt`, `totalAmount` mặc dù persistence mapping thay đổi.
3. Bỏ free-text SQL/ORM field traversal; thêm prefix trên mã đơn với ký tự/độ dài được kiểm soát.
4. Bắt buộc khoảng thời gian tối đa 90 ngày, sort có index, page size 1–100, cursor gắn filter/scope.
5. Có Problem Details ổn định khi client gửi field/operator sai.
6. Thêm quota theo tenant và đo p95 query theo shape, thông tin scanned rows, DB time và số `400/429`.
7. Viết migration guide cho client cũ, có thời hạn ngừng hỗ trợ cú pháp cũ; không âm thầm đổi contract ở cùng một version nếu đang có client sử dụng.

### 16.3. Chứng minh cải thiện

| Tiêu chí | Trước | Bằng chứng cần có sau thay đổi |
|---|---|---|
| Trường được phép | Mọi ORM property khả dụng | Schema/OpenAPI và test từ chối unknown field |
| Quyền dữ liệu | Có nhánh filter theo tenant từ client | Scope bắt buộc từ principal, test cross-tenant |
| Chi phí | Sort/contains/offset tùy ý | Query plan, p95/p99 ở tải đại diện, max limit và 429 |
| Cú pháp | Duplicate/escaping không rõ | Parser test, URI encoding và error contract |
| Tương thích | Client biết tên cột nội bộ | Mapping field public, migration test khi schema đổi |
| Vận hành | Log raw query khó kiểm soát | Metric query shape, error code và tracing an toàn |

**Không nên tuyên bố “nhanh hơn X%” hoặc “an toàn tuyệt đối” nếu chưa đo thực tế.** Bounded filtering làm giảm bề mặt rủi ro và giúp khả năng kiểm soát/kiểm thử tốt hơn, nhưng phải đánh giá trên dữ liệu thật và các luồng nghiệp vụ.

## 17. Bài thực hành: thiết kế API lọc cho kho sản phẩm

**Đề bài:** Bạn xây dựng REST API danh sách sản phẩm cho nền tảng bán hàng. Nhu cầu gồm lọc theo trạng thái hiển thị, danh mục, khoảng giá, ngày cập nhật và tên sản phẩm bắt đầu bằng tiền tố. Hệ thống có bảng nội bộ `products`, `supplier_contracts`, `stock_reservations`, `internal_margins`. Khách mua hàng **không được** lọc hoặc suy ra biên lợi nhuận nội bộ, thông tin hợp đồng nhà cung cấp hay hàng bị ẩn của merchant khác.

### 17.1. Các yêu cầu chức năng

- Khách chỉ xem sản phẩm `PUBLISHED` trong kênh/tenant được phép.
- Nhân viên merchant có thể xem cả `DRAFT` của chính merchant, nhưng không xem merchant khác.
- Người dùng lọc theo category ID công khai và khoảng giá theo currency.
- Tìm tên theo prefix nếu dữ liệu sản phẩm/locale hỗ trợ; không cần regex hay arbitrary contains.
- Client phân trang bằng cursor và sắp theo `-updatedAt` mặc định.
- API có ngưỡng cho range, IN list, page size, độ dài URI và tần suất.

### 17.2. Nhiệm vụ của người học

1. Viết danh sách resource/role/scope và xác định **field bắt buộc đến từ server**, không cho client chọn như `merchantId` của người khác.
2. Thiết kế cú pháp filter theo `filter[field][op]`; ghi rõ những operator hỗ trợ cho `category`, `price`, `currency`, `updatedAt` và `namePrefix`.
3. Viết bảng allowlist và chọn **năm giới hạn** cụ thể (có lý do và cách đo lại sau).
4. Giải thích cách kết hợp AND và OR. Nếu yêu cầu “category A hoặc B, giá từ 100 đến 500”, viết biểu thức và URL đã encode.
5. Viết `OrderQueryParser` tương tự cho sản phẩm: kiểm tra duplicate, unknown field, enum, prefix, khoảng ngày, amount/currency.
6. Đề xuất mapping từ field công khai sang query builder, nêu cách truyền giá trị an toàn và kiểm soát index.
7. Thiết kế phân quyền: khách xem `PUBLISHED`, merchant xem sản phẩm của mình. Chỉ rõ tại sao `filter[merchantId][eq]=...` không được tin.
8. Chọn sort, tie-breaker và keyset cursor; xử lý khi client đổi filter với cursor cũ.
9. Viết OpenAPI rút gọn cho ít nhất bốn filter, `sort`, `limit` và `cursor`; có response `200`, `400`, `401`, `403` và `429`.
10. Thiết kế ít nhất **mười hai test**, gồm input hợp lệ, unknown field, operator sai, quá ngưỡng, phân quyền chéo tenant và giá trị chứa payload injection.

### 17.3. Gợi ý lời giải

Một phương án ban đầu:

| Field công khai | Operator | Điều kiện |
|---|---|---|
| `category` | `in` | Tối đa 10 category IDs công khai |
| `price` | `gte`, `lt` | Không âm, hợp lệ theo currency |
| `currency` | `eq` | Bắt buộc nếu có price filter |
| `updatedAt` | `gte`, `lt` | Khoảng tối đa 30 hoặc 90 ngày tùy dữ liệu |
| `namePrefix` | `prefix` | Giới hạn 2–30 ký tự và normalization theo locale |

Nếu muốn client lọc theo category A hoặc B và giá trong khoảng 100 đến 500, ngữ nghĩa là:

\[
(category=A \lor category=B)
\land price \ge 100
\land price < 500
\land currency=VND
\]

Các filter nghiệp vụ được **AND**, riêng danh sách category bên trong `in` là OR. Giá trị currency ở đây chỉ minh họa đơn vị; yêu cầu nghiệp vụ về VND có thể không cho phép số tiền nhỏ như vậy, nhưng điều đó không ảnh hưởng đến cấu trúc logic của bài.

Một URL dạng đã encode:

~~~http
GET /v1/products?filter%5Bcategory%5D%5Bin%5D=A%2CB&filter%5Bprice%5D%5Bgte%5D=100&filter%5Bprice%5D%5Blt%5D=500&filter%5Bcurrency%5D%5Beq%5D=VND&sort=-updatedAt&limit=20 HTTP/1.1
Host: api.example.test
Authorization: Bearer <access-token>
~~~

Nếu category/names chứa ký tự đặc biệt, cần chọn cách serialize rõ và thêm test encoding; đừng dùng quy tắc dấu phẩy cho chuỗi bất kỳ có thể chứa dấu phẩy. Quyền nhìn thấy `PUBLISHED` hay `DRAFT` phải đến từ server-side policy, không dựa vào client chọn filter. Với tìm kiếm tên, Unicode normalization, phân biệt chữ hoa, ngôn ngữ và collation có thể ảnh hưởng index và kết quả; không tự hứa prefix search hoạt động giống nhau trên mọi ngôn ngữ/DB.

### 17.4. Bài tập nâng cao: bảo vệ endpoint khỏi filter hợp lệ nhưng nặng

Giả sử sau triển khai, user có quyền hợp lệ gửi hàng nghìn request với các category filter khác nhau, mỗi request chỉ 20 kết quả nhưng p95 DB tăng cao. Hãy đề xuất:

- Bộ metric gắn với query template và principal/tenant mà không log dữ liệu nhạy cảm.
- Rate limit theo principal/tenant và budget cho các query nặng.
- Kiểm tra index, selectivity, execution plan và chi phí count/sort.
- Cách trả `429` và hướng client backoff; trường hợp cần `503` do hạ tầng tạm quá tải.
- Khi nào nên giới hạn thêm use case hoặc chuyển sang export/search job bất đồng bộ.

## 18. Bộ câu hỏi tự kiểm tra

**1. Prepared statement đã đủ an toàn cho API lọc tự do chưa?** Chưa. Nó bảo vệ giá trị khỏi thay đổi cú pháp SQL nhưng không tự giới hạn field, operator, mối quan hệ, độ phức tạp, quyền dữ liệu hoặc tài nguyên DB mà client có thể sử dụng.

**2. Cho phép `filter[fraudScore][gte]` có nguy hiểm nếu không trả `fraudScore` trong JSON không?** Có. Client có thể suy ra thông tin nhạy cảm từ số lượng hoặc sự tồn tại bản ghi khớp; quyền lọc theo field cũng là một dạng khả năng quan sát.

**3. Tại sao cần kiểm tra duplicate parameters?** Các tầng proxy, framework và cache có thể lấy giá trị đầu/cuối hoặc gom thành danh sách theo các cách khác nhau. Fail-fast theo một quy tắc thống nhất tránh sai khác và bypass filter.

**4. Tại sao `limit=20` không bảo đảm truy vấn rẻ?** Database vẫn có thể phải quét và sort hàng triệu row trước khi chọn 20 row. Cần giới hạn predicate, range, index, timeout và quota.

**5. Truy vấn không có kết quả nên trả 400 hay 200?** Nếu filter hợp lệ và không có bản ghi phù hợp, trả `200 OK` với `data: []` và metadata trang thích hợp. Nếu filter sai kiểu/trường/operator hoặc vượt ngưỡng, trả `400` theo hợp đồng.

**6. Có nên dùng `offset=10000000` để cho khách đi đến trang cuối?** Thường không với collection lớn: truy vấn sâu tốn tài nguyên và có thể không ổn định khi dữ liệu thay đổi. Dùng cursor/keyset hoặc luồng export phù hợp với nhu cầu.

**7. Cursor có thể chỉ là Base64 của offset hoặc primary key không?** Base64 không chống sửa; cursor nên kiểm chứng integrity, phiên bản, hạn, filter, sort và scope. Tránh lộ dữ liệu nhạy cảm trong token.

**8. Nếu đổi tên cột DB, có cần đổi field công khai không?** Không nhất thiết. Field contract có thể giữ nguyên và mapper/query builder chuyển sang cột mới. Chỉ thay API khi semantics đối với client thay đổi có chủ đích.

**9. Có cần hỗ trợ tất cả toán tử cho mỗi field?** Không. Toán tử phải phù hợp kiểu dữ liệu, use case, quyền và kế hoạch truy vấn được kiểm chứng. Cấm điều hướng quan hệ hoặc regex tùy ý nếu không có yêu cầu.

**10. Có thể dựa vào filter `tenantId=t_7` để phân quyền không?** Không. Scope phải đến từ danh tính và policy đáng tin, được áp bắt buộc vào truy vấn. Client không thể tự cấp quyền qua query string.

## 19. Checklist trước khi phát hành collection filter API

### Hợp đồng và cú pháp

- [ ] Đã xác định use case, hành trình khách hàng, field/operator thật sự cần.
- [ ] Cú pháp query được công bố nhất quán, có ví dụ encoding và xử lý giá trị đặc biệt.
- [ ] Các điều kiện AND/OR, khoảng nửa mở và kiểu dữ liệu có định nghĩa rõ.
- [ ] Field và operator có allowlist riêng cho resource và role khi cần.
- [ ] Unknown/duplicate parameter, field lạ và operator sai có quy tắc từ chối.
- [ ] Mọi giá trị có validation: enum, ngày, decimal, tiền tệ, prefix, ký tự, độ dài.

### Bảo vệ chi phí và phân trang

- [ ] Có giới hạn số điều kiện, IN list, range, độ dài URI, page size và query timeout.
- [ ] Sort chỉ dùng field được phép và có tie-breaker ổn định.
- [ ] Cursor chứa/bảo vệ filter, sort, phạm vi quyền, phiên bản và thời hạn.
- [ ] Query có phân trang tại DB và không lấy toàn bộ rồi cắt trong ứng dụng.
- [ ] Đã đo query plan, index, p95/p99 và scanned rows ở dữ liệu/tải đại diện.
- [ ] Có quota/rate limit và phương án cho truy vấn quá nặng (báo cáo nền hoặc search riêng).

### Bảo mật và dữ liệu

- [ ] Xác thực và row-level scope không lấy từ filter của client.
- [ ] Lọc theo field nhạy cảm bị kiểm soát ngay cả khi không có field đó trong JSON.
- [ ] Field/operator/sort map tới biểu thức backend cố định; giá trị được bind an toàn.
- [ ] Có test cross-tenant, cursor giả mạo, query injection và không lộ dữ liệu qua cache/log.
- [ ] Chính sách cache phản ánh quyền riêng tư và canonical query; không có shared cache chéo tenant.

### Hợp đồng tích hợp và vận hành

- [ ] OpenAPI có từng parameter, ví dụ, mã lỗi và schema `200`.
- [ ] Problem Details có mã ổn định, không lộ SQL/internal schema/raw input nhạy cảm.
- [ ] Client biết phân trang, reset cursor khi đổi filter và xử lý `400/429/503` phù hợp.
- [ ] Có metric theo query shape, cảnh báo quá tải và kế hoạch review giới hạn.
- [ ] Đã chạy parser tests, integration tests, security tests và load tests.
- [ ] Có kế hoạch thay đổi contract nếu cần thêm field/operator, không chỉ mở trực tiếp cột DB mới.

## 20. Ghi nhớ

**Một REST collection query tốt không phải là một cổng SQL thu nhỏ.** Nó là hợp đồng để client hỏi những câu hỏi nghiệp vụ đã được server chấp nhận. Mỗi field công khai, mỗi toán tử, mỗi dạng giá trị và mỗi quyền truy cập đều là một quyết định kiến trúc cần có lý do.

Hãy bắt đầu từ allowlist **field–operator** và ngữ nghĩa AND/IN rõ ràng, dùng giới hạn giá trị và chi phí để ngăn truy vấn vô hạn, tách quyền tenant/owner khỏi query string, rồi mới biên dịch qua mapper/query builder có tham số hóa. Khi kết hợp với sort ổn định, cursor gắn phạm vi, OpenAPI, lỗi HTTP nhất quán và kiểm thử âm, API vừa đủ linh hoạt cho người dùng, vừa giữ được **bảo mật, hiệu năng và khả năng tiến hóa** khi mô hình dữ liệu nội bộ thay đổi.
