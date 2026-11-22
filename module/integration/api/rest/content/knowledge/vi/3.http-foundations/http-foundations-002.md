# URI, origin, scheme, host, port, path và query

## Mục tiêu và phạm vi

Trong chương **Nền tảng HTTP** của module **INTEGRATION_API_REST**, bài học này giải thích cách đọc và xây dựng URI của một HTTP API: phần nào xác định origin, phần nào định danh tài nguyên, phần nào mang tham số và phần nào không được gửi đến server.

Module tập trung vào thiết kế REST API dựa trên resource, URI, phương thức và mã trạng thái HTTP, cùng hợp đồng dữ liệu rõ ràng. Hiểu URI giúp bạn đặt đích request đúng, thiết kế phân trang và bộ lọc nhất quán, chọn đúng cache key, mô tả OpenAPI và kiểm thử API bằng Java/Spring hoặc công nghệ tương đương. URI không thay thế xác thực, phân quyền hoặc hợp đồng về retry và idempotency.

Sau bài học, bạn có thể:

- Tách scheme, authority, host, port, path, query và fragment của một URI HTTP(S).
- Xác định hai địa chỉ có cùng origin hay không.
- Phân biệt biến trong path, tham số query và dữ liệu thuộc body hoặc header.
- Giải thích percent-encoding, dấu `+`, ký tự phân cách và nguy cơ decode nhiều lần.
- Dùng API URI của Java và builder của Spring mà không mã hóa lặp hoặc thay đổi cấu trúc ngoài ý muốn.

## 1. URI và URL trong phạm vi HTTP API

**URI**, Uniform Resource Identifier, là một định danh theo một cú pháp có cấu trúc. **URL** là cách gọi nhấn mạnh vai trò định vị và truy cập một tài nguyên. Trong bài này, các địa chỉ HTTP(S) là những URI mà ứng dụng dùng làm URL để gửi request.

Không phải mọi URI đều có host hoặc port. Ví dụ, một URI dùng scheme khác có thể có cấu trúc khác. Các quy tắc về origin và cổng mặc định được trình bày ở đây tập trung vào HTTP và HTTPS; không áp dụng máy móc cho mọi scheme.

Một URI không tự nói tài nguyên được lưu trong bảng nào, chạy trên máy vật lý nào hoặc dùng Java class nào. Một domain có thể dẫn qua gateway và nhiều instance, trong khi tài nguyên vẫn được định danh bằng URI công khai ổn định.

Ví dụ xuyên suốt:

```text
https://api.example.test:8443/v1/orders/ord-123?include=items&lang=vi#summary
```

| Thành phần | Giá trị | Vai trò |
| --- | --- | --- |
| Scheme | `https` | Xác định cơ chế truy cập và các quy tắc liên quan |
| Authority | `api.example.test:8443` | Phần authority trong ví dụ, gồm host và port |
| Host | `api.example.test` | Tên host đích |
| Port | `8443` | Cổng được chỉ định tường minh |
| Path | `/v1/orders/ord-123` | Đường dẫn của tài nguyên trong không gian URI đó |
| Query | `include=items&lang=vi` | Phần query theo hợp đồng API |
| Fragment | `summary` | Định danh phần hoặc trạng thái phía sử dụng URI; không gửi trong request target HTTP |

Dấu `?` mở đầu query, còn `#` mở đầu fragment; chúng không thuộc giá trị query và fragment trong bảng. Các dấu phân cách là một phần của cấu trúc URI, không phải ký tự có thể tùy ý thêm hoặc bỏ.

## 2. Scheme, host, port và authority

### 2.1. Scheme

Scheme đứng trước dấu hai chấm đầu tiên của URI có scheme:

```text
https://api.example.test/orders
^^^^^
```

Với HTTP API:

- `http` và `https` là hai scheme khác nhau.
- HTTPS sử dụng HTTP qua kênh được bảo vệ bằng TLS theo cơ chế của phiên bản giao thức liên quan.
- Chọn `https` không tự xác thực người dùng hoặc phân quyền cho một đơn hàng.
- Scheme không phải phiên bản HTTP. `https` không đồng nghĩa với HTTP/2, và URL thường không chứa phiên bản HTTP được thương lượng.

Tên scheme không phân biệt hoa thường. Tuy vậy, client và tài liệu thường dùng dạng chữ thường để giữ biểu diễn nhất quán.

### 2.2. Host không phải path và cũng không phải một IP cố định

Trong:

```text
https://api.example.test/orders
```

`api.example.test` là host; `/orders` là path. DNS và hạ tầng có thể ánh xạ host đến các địa chỉ khác nhau theo thời điểm hoặc vị trí mạng. Đổi một bản ghi DNS không tự đổi origin của URL đang dùng, vì origin dựa vào tên host trong URL, không dựa vào việc hai host có cùng IP hay không.

Host có thể là tên miền hoặc một địa chỉ IP theo cú pháp áp dụng. Với IPv6 trong authority, địa chỉ được đặt trong dấu ngoặc vuông để phân biệt các dấu hai chấm của địa chỉ với dấu phân cách port:

```text
https://[2001:db8::10]:8443/orders
```

Trong ví dụ này, `8443` là port; không được tách authority bằng cách lấy mọi dấu hai chấm như thể đó là các trường độc lập.

Với tên miền ASCII thông thường, so sánh host không phân biệt hoa thường. Quy tắc đó không cho phép tự chuyển cả path và query thành chữ thường.

### 2.3. Port và cổng mặc định

Port là cổng của dịch vụ được truy cập tại authority đó. Các cổng mặc định trong phạm vi bài học:

| Scheme | Cổng mặc định |
| --- | --- |
| `http` | `80` |
| `https` | `443` |

Vì thế:

```text
https://api.example.test/orders
https://api.example.test:443/orders
```

có cùng scheme, host và cổng hiệu lực. Ngược lại, `https://api.example.test:8443/orders` dùng một cổng khác.

Bỏ port nghĩa là áp dụng mặc định của scheme, không phải “dùng bất kỳ cổng nào server đang chạy”. Nếu ứng dụng chỉ được mở ở cổng `8080`, URI không có port với scheme `http` vẫn nhắm tới cổng `80`, trừ khi có hạ tầng chuyển tiếp phù hợp.

### 2.4. Authority và thông tin người dùng

Trong cú pháp URI tổng quát, authority có thể chứa các thành phần ngoài host và port, chẳng hạn userinfo. Tuy nhiên, không nên đưa mật khẩu hoặc access token vào authority của URL API. Hợp đồng HTTP cần sử dụng cơ chế xác thực phù hợp, thường qua các header hoặc cơ chế đã công bố.

Các ví dụ trong bài chỉ dùng authority dạng host và port tùy chọn. Đừng coi authority luôn là một chuỗi có thể tách an toàn bằng một thao tác `split(":")`.

## 3. Origin: bộ ba scheme, host và cổng hiệu lực

### 3.1. Origin không bao gồm path và query

Với các URL HTTP(S) thông thường trong bài, origin được xác định bằng:

```text
(scheme, host, effective port)
```

Origin của URL xuyên suốt là:

```text
https://api.example.test:8443
```

Path `/v1/orders/ord-123`, query và fragment không tham gia bộ ba này. Hai tài nguyên khác nhau vẫn có thể thuộc cùng origin.

Ví dụ, lấy `https://api.example.test/orders` làm mốc:

| URL so sánh | Cùng origin? | Giải thích |
| --- | --- | --- |
| `https://api.example.test/products` | Có | Chỉ thay path |
| `https://api.example.test/orders?page=2` | Có | Chỉ thay query |
| `https://API.EXAMPLE.TEST:443/orders` | Có | Host ASCII tương đương và cổng hiệu lực đều là 443 |
| `http://api.example.test/orders` | Không | Scheme khác |
| `https://api.example.test:8443/orders` | Không | Cổng hiệu lực khác |
| `https://admin.example.test/orders` | Không | Host khác |
| `https://example.test/orders` | Không | Host khác, dù có phần tên miền liên quan |

`http://localhost:8080` và `http://127.0.0.1:8080` cũng khác origin. Việc chúng có thể dẫn tới cùng máy không làm chuỗi host trở thành giống nhau.

### 3.2. Origin trong chính sách trình duyệt

Trình duyệt dùng origin trong các cơ chế như same-origin policy và CORS. Một trang tại `https://shop.example.test` gọi API tại `https://api.example.test` là tương tác khác origin, dù hai host có chung phần `example.test`.

Các điểm cần phân biệt:

- Cùng origin không có nghĩa người dùng được phép đọc mọi tài nguyên của origin đó.
- Khác origin không có nghĩa một Java HTTP client không thể gửi request.
- CORS chủ yếu quy định hành vi truy cập từ môi trường trình duyệt; nó không thay thế xác thực hoặc phân quyền tại server.
- Cùng site và cùng origin là các khái niệm khác nhau; không suy ra origin chỉ từ tên miền gốc.

Bài này dùng origin để hiểu ranh giới địa chỉ. Cấu hình CORS và các chính sách trình duyệt chi tiết là một vấn đề riêng.

### 3.3. Origin, Host và header Origin khác vai trò

Giả sử trang web ở `https://shop.example.test` gửi request đến API:

```http
GET /orders/ord-123 HTTP/1.1
Host: api.example.test
Origin: https://shop.example.test
```

Trong ví dụ:

- `Host` là authority đích của request HTTP/1.1.
- `Origin` mô tả origin của phía khởi tạo theo cơ chế có liên quan của client.
- Hai header không bắt buộc có cùng giá trị.
- Không phải mọi request đều có header `Origin`.

Header `Origin` không chứa path hay query trong dạng thông thường này. Nó cũng không phải chứng nhận danh tính: một client ngoài trình duyệt có thể tự tạo header, nên server không dựa riêng vào đó để cấp quyền nghiệp vụ.

## 4. Path: đường dẫn trong không gian tài nguyên

### 4.1. Segment không phải thư mục trên ổ đĩa

```text
/v1/orders/ord-123/items
```

Path trên có các segment như `v1`, `orders`, `ord-123` và `items`, phân cách bởi dấu `/`. Các segment này là một phần của hợp đồng định danh; chúng không buộc server có thư mục `orders` hoặc bảng database tên tương ứng.

Trong thiết kế tài nguyên:

- `/orders` có thể định danh tập đơn hàng.
- `/orders/ord-123` có thể định danh một đơn hàng.
- `/orders/ord-123/items` có thể định danh tập mục hàng của đơn đó.

Đây là các lựa chọn mô hình hóa API, không phải ý nghĩa tự động của mọi chuỗi path giống nhau. HTTP method và hợp đồng mới cho biết request thực hiện tương tác nào với đích đó.

### 4.2. Biến path là ký hiệu của tài liệu và framework

```text
/v1/orders/{orderId}
```

là một mẫu trong tài liệu hoặc router. Request thực tế thường là:

```text
/v1/orders/ord-123
```

Tên `orderId` không được gửi như metadata riêng trên wire. Framework khớp mẫu rồi cung cấp giá trị tương ứng, chẳng hạn qua `@PathVariable("orderId")` trong Spring.

### 4.3. Hoa thường, dấu slash cuối và chuẩn hóa

Không mặc định các URI sau là tương đương:

```text
/orders/ord-123
/Orders/ord-123
/orders/ord-123/
/orders//ord-123
```

Path nói chung được xử lý có phân biệt hoa thường, trừ khi ứng dụng công bố quy tắc khác. Dấu slash cuối hoặc slash lặp cũng có thể làm thay đổi đường dẫn. Server có thể thiết kế redirect hoặc alias, nhưng đó là hành vi cần được thống nhất giữa router, proxy, client và cache.

Không tự chuyển toàn bộ URL sang chữ thường, xóa slash hoặc sửa path vì cho rằng đó chỉ là định dạng. Việc chuẩn hóa cú pháp không đồng nghĩa với việc biết hai tài nguyên có cùng ý nghĩa nghiệp vụ.

## 5. Query: cấu trúc do hợp đồng API diễn giải

### 5.1. Query bắt đầu sau dấu hỏi

```text
/v1/orders?status=PENDING&page=0&size=20
```

Trong cách biểu diễn tham số thường gặp, query gồm các cặp tên–giá trị phân cách bằng `&`:

| Tên | Giá trị văn bản | Ý nghĩa theo hợp đồng ví dụ |
| --- | --- | --- |
| `status` | `PENDING` | Lọc đơn theo trạng thái |
| `page` | `0` | Lấy trang đầu, vì API này quy định bắt đầu từ 0 |
| `size` | `20` | Kích thước trang yêu cầu |

HTTP và cú pháp URI không tự quy định API phải phân trang theo số trang, bắt đầu từ 0, hoặc dùng một tên parameter cụ thể. Một API khác có thể dùng cursor và các tên khác.

Query là một phần của URI, không phải phần metadata có thể bỏ qua tùy ý. Hai URI có query khác nhau có thể dẫn tới tập dữ liệu, thứ tự hoặc biểu diễn khác nhau và thường cần được phân biệt khi lưu cache.

### 5.2. Query không luôn là một map đơn giản

Hợp đồng cần quy định các trường hợp sau:

| Dạng query | Câu hỏi cần trả lời |
| --- | --- |
| `tag=java&tag=spring` | Lặp key tạo danh sách, lấy giá trị đầu, lấy giá trị cuối hay bị từ chối? |
| `sort=createdAt&sort=id` | Thứ tự các giá trị có xác định ưu tiên sắp xếp không? |
| `q=` | Chuỗi rỗng có hợp lệ không? |
| Không có `q` | Thiếu parameter khác chuỗi rỗng thế nào? |
| `active=false` | Chấp nhận những dạng boolean nào? |
| `size=-1` | Lỗi kiểu dữ liệu hay giá trị nằm ngoài phạm vi cho phép? |

Một parser biến query thành map một giá trị có thể làm mất dữ liệu khi key lặp. Ngược lại, tự sắp xếp toàn bộ query để “chuẩn hóa” có thể thay đổi ý nghĩa nếu thứ tự quan trọng theo hợp đồng.

Với query chỉ có các bộ lọc độc lập, ứng dụng có thể quy định thứ tự các cặp không ảnh hưởng kết quả. Nhưng đó không phải quy tắc suy ra được cho mọi URI hoặc mọi cơ chế ký request.

### 5.3. Path, query, header và body không hoán đổi tùy ý

| Nhu cầu trong ví dụ | Vị trí phù hợp theo hợp đồng |
| --- | --- |
| Chọn đơn hàng `ord-123` | Path `/orders/ord-123` |
| Lọc tập đơn hàng hoặc phân trang | Query như `status`, `page`, `size` |
| Gửi danh sách mặt hàng để tạo đơn | Request body theo schema |
| Gửi media type mong muốn | Header `Accept` |
| Gửi thông tin xác thực theo cơ chế Bearer | Header `Authorization` |

Đây là lựa chọn cho một hợp đồng cụ thể, không phải khẳng định mọi định danh bắt buộc nằm trong path. Điều quan trọng là client và server thống nhất nguồn dữ liệu và ý nghĩa của nó.

Không dùng query như nơi mặc định để đặt mật khẩu hoặc token. URI thường xuất hiện trong log và các công cụ chẩn đoán; cơ chế xác thực cần được thiết kế ở đúng ranh giới của hợp đồng. Đưa giá trị vào header cũng không tự thay thế các biện pháp bảo vệ và quản lý log phù hợp.

## 6. Fragment: phần không được gửi trong request target

Trong:

```text
https://api.example.test/orders/ord-123?include=items#summary
```

fragment là `summary`. Khi gửi request HTTP trực tiếp theo dạng thông thường của HTTP/1.1, client gửi:

```http
GET /orders/ord-123?include=items HTTP/1.1
Host: api.example.test
```

Không có `#summary` trong request target. Server không thể dùng fragment làm bộ lọc chỉ bằng cách chờ router đọc nó.

Trình duyệt hoặc ứng dụng có thể dùng fragment để điều hướng trong tài liệu, biểu đạt trạng thái giao diện hoặc thực hiện hành vi phù hợp với kiểu tài nguyên. Nếu mã client chủ động lấy fragment rồi đưa vào query, body hoặc một request khác, server mới nhận dữ liệu qua phần được gửi đó.

Vì vậy:

```text
/products?q=C#
/products?q=C%23
```

không có cùng cấu trúc. Ở dòng đầu, `#` mở đầu fragment và query chỉ chứa `q=C`. Ở dòng sau, `%23` biểu diễn ký tự `#` bên trong giá trị query, chẳng hạn khi tìm ngôn ngữ C#.

## 7. Percent-encoding: mã hóa dữ liệu bên trong cấu trúc

### 7.1. Mã hóa byte, không xóa ý nghĩa dấu phân cách

Percent-encoding dùng dạng `%HH` để biểu diễn một byte. Với ký tự ngoài ASCII, thường cần chuyển ký tự thành các byte UTF-8 rồi percent-encode theo vị trí và quy tắc được sử dụng.

Ví dụ dữ liệu tìm kiếm:

```text
Bàn phím
```

có thể được biểu diễn trong giá trị query bằng:

```text
B%C3%A0n%20ph%C3%ADm
```

Các chuỗi `%C3%A0` và `%C3%AD` biểu diễn các byte UTF-8 của ký tự có dấu; `%20` biểu diễn dấu cách.

Một số ký tự cần chú ý:

| Ký tự dữ liệu | Dạng percent-encoded | Ý nghĩa cần giữ |
| --- | --- | --- |
| Dấu cách | `%20` | Một dấu cách trong dữ liệu |
| `+` | `%2B` | Dấu cộng thực sự |
| `&` | `%26` | Dữ liệu, không phải dấu tách cặp query |
| `=` | `%3D` | Dữ liệu, không phải dấu tách tên và giá trị theo quy ước tham số |
| `#` | `%23` | Dữ liệu, không phải bắt đầu fragment |
| `%` | `%25` | Dấu phần trăm thực sự |
| `/` | `%2F` | Slash được mã hóa; cách chấp nhận và xử lý trong path cần hợp đồng rõ |

Không encode nguyên URL như thể mọi ký tự đều là dữ liệu. Nếu dấu `:`, `/`, `?` và `&` đang làm nhiệm vụ cấu trúc, việc mã hóa cả chuỗi có thể phá cấu trúc đích muốn gọi.

### 7.2. Dấu cộng không phải lúc nào cũng là dấu cách

Trong mã hóa form `application/x-www-form-urlencoded`, dấu `+` thường biểu diễn dấu cách. Nhiều thư viện query parameter cũng sử dụng quy ước này.

Tuy nhiên, `+` không có nghĩa dấu cách một cách phổ quát trong mọi thành phần URI. Nếu giá trị tìm kiếm là:

```text
C++
```

một cách biểu diễn rõ ràng khi truyền dấu cộng trong query là:

```text
q=C%2B%2B
```

Nếu gửi `q=C++` vào một parser áp dụng quy tắc form, giá trị nhận được có thể là chữ `C` theo sau bởi hai dấu cách. Client và server phải dùng cùng hợp đồng mã hóa.

`java.net.URLEncoder` tạo dữ liệu theo quy tắc form, không phải công cụ mã hóa nguyên URI hoặc mọi path segment. Nó có thể phù hợp với một giá trị query theo quy ước form, nhưng không được sử dụng cho toàn bộ URL rồi mong mọi phần vẫn giữ đúng cấu trúc.

### 7.3. Không decode toàn query trước khi tìm ranh giới tham số

Xét raw query:

```text
q=A%26B&sort=name
```

Theo hợp đồng tên–giá trị thông thường, có hai parameter:

```text
q    = A&B
sort = name
```

Nếu decode toàn query trước thành `q=A&B&sort=name` rồi mới chia theo `&`, một dấu `&` thuộc dữ liệu đã bị biến thành dấu phân cách. Cách đúng là dùng parser hiểu cấu trúc và decode từng thành phần theo quy tắc tương ứng.

Tương tự, decode nhiều lần có thể thay đổi cấu trúc:

```text
%252F  -- decode một lần -->  %2F
%2F    -- decode lần nữa -->  /
```

Đây không phải những trạng thái có thể coi là tương đương tùy ý. Tránh việc client, proxy và ứng dụng cùng decode lặp mà không có quy ước rõ.

### 7.4. Slash mã hóa trong path cần được xem xét riêng

Một ID chứa slash không tự trở thành một segment an toàn chỉ vì client thay `/` bằng `%2F`. Server, proxy hoặc router có thể từ chối, giữ nguyên hoặc xử lý encoded slash theo các quy tắc khác nhau.

Hợp đồng nên xác định miền ký tự của ID và cách truyền chúng. Nếu ID được giới hạn ở chữ, số và một số ký tự rõ ràng như dấu gạch ngang, nhiều vấn đề định tuyến sẽ đơn giản hơn. Không mở rộng miền ID tùy ý chỉ dựa vào việc một URI builder chấp nhận chuỗi đầu vào.

## 8. URI reference và cách phân giải địa chỉ tương đối

### 8.1. Có scheme và không có scheme

Một URI reference có thể là URI có scheme:

```text
https://api.example.test/v1/orders/ord-123
```

hoặc một tham chiếu tương đối cần base URI:

```text
ord-123
../products/prd-10
/v1/orders/ord-123
```

Một tham chiếu bắt đầu bằng `//` cung cấp authority mới và kế thừa scheme từ base. Nó không phải cùng trường hợp với một path bắt đầu bằng một dấu `/`.

### 8.2. Base URI quyết định kết quả

Với base:

```text
https://api.example.test/v1/orders/
```

các tham chiếu có kết quả như sau:

| Reference | Kết quả sau phân giải |
| --- | --- |
| `ord-123` | `https://api.example.test/v1/orders/ord-123` |
| `../products/prd-10` | `https://api.example.test/v1/products/prd-10` |
| `/health` | `https://api.example.test/health` |
| `//files.example.test/report.pdf` | `https://files.example.test/report.pdf` |
| `https://partner.example.test/orders` | `https://partner.example.test/orders` |

Dấu slash cuối của base rất quan trọng:

```text
Base: https://api.example.test/v1/orders/
Ref:  ord-123
Kết quả: https://api.example.test/v1/orders/ord-123

Base: https://api.example.test/v1/orders
Ref:  ord-123
Kết quả: https://api.example.test/v1/ord-123
```

Ở trường hợp thứ hai, segment cuối của path base được thay khi phân giải relative path. Không thể thay thuật toán phân giải bằng việc nối thêm dấu `/` vào mọi chuỗi.

### 8.3. Liên kết trong API

Header `Location` sau khi tạo tài nguyên hoặc các liên kết trong body có thể chứa URI reference. Client phải hiểu base nào được dùng và có cho phép đi sang origin khác hay không theo hợp đồng.

Một liên kết bắt đầu bằng `/` giữ scheme và authority khi phân giải theo base thông thường, nhưng đi từ gốc path. Nếu API được công bố dưới prefix `/api`, một `Location: /orders/ord-123` có thể bỏ mất prefix đó. Cần tạo liên kết phù hợp với địa chỉ công khai, không chỉ với route nội bộ của ứng dụng.

## 9. Làm việc với URI trong Java

### 9.1. Đọc từng thành phần bằng java.net.URI

```java
URI target = URI.create(
        "https://api.example.test:8443/v1/orders/ord-123"
        + "?include=items&lang=vi#summary");

System.out.println(target.getScheme());
System.out.println(target.getHost());
System.out.println(target.getPort());
System.out.println(target.getRawPath());
System.out.println(target.getRawQuery());
System.out.println(target.getRawFragment());
```

`URI` thuộc `java.net`. Kết quả tương ứng:

```text
https
api.example.test
8443
/v1/orders/ord-123
include=items&lang=vi
summary
```

Điểm quan trọng là `URI` giúp phân tích cú pháp, không tự chứng minh server tồn tại hoặc tài nguyên có thể truy cập. Một URI reference còn có thể là tương đối; khi đó các thành phần như scheme và host có thể không có giá trị.

### 9.2. Port bị bỏ trống không được tự điền trong getPort

```java
URI target = URI.create("https://api.example.test/orders");
System.out.println(target.getPort());
```

Kết quả là `-1`, biểu thị không có port tường minh. Khi tính origin HTTP(S), ứng dụng phải xét cổng hiệu lực `443` cho `https` hoặc `80` cho `http`, thay vì coi `-1` là một cổng mạng thực tế.

`URI.equals()` cũng không phải một hàm kiểm tra same-origin. So sánh URI và xác định origin là hai bài toán khác nhau; origin chỉ xét scheme, host và cổng hiệu lực theo quy tắc phù hợp.

### 9.3. Raw component khác decoded component

```java
URI target = URI.create(
        "https://api.example.test/products?q=A%26B");

System.out.println(target.getRawQuery());
System.out.println(target.getQuery());
```

Kết quả:

```text
q=A%26B
q=A&B
```

`getQuery()` không trả một map parameter. Nó trả thành phần query đã được decode theo cơ chế của `URI`. Nếu lấy kết quả này rồi tách theo `&`, bạn có thể làm mất ranh giới dữ liệu như đã phân tích ở trên.

Hãy dùng parser parameter của framework hoặc thư viện phù hợp với hợp đồng query. Tương tự, không tự decode tiếp một giá trị mà router hoặc request parser đã decode.

### 9.4. Phân giải reference bằng resolve

```java
URI base = URI.create("https://api.example.test/v1/orders/");
URI detail = base.resolve("ord-123");

System.out.println(detail);
```

Kết quả:

```text
https://api.example.test/v1/orders/ord-123
```

`resolve` xử lý reference theo base; nó không có nghĩa mọi đầu vào đều giữ nguyên origin. Một reference cung cấp scheme hoặc authority mới có thể đổi đích như các ví dụ trước.

`normalize()` có thể chuẩn hóa những thành phần cú pháp được API đó hỗ trợ, chẳng hạn xử lý dot segment trong path. Nó không biết quy tắc nghiệp vụ, không xác định tài nguyên tương đương và không thay thế việc kiểm tra đích có phù hợp hợp đồng hay không.

Các parser URI và URL trong những môi trường khác nhau cũng không nhất thiết có mọi quy tắc xử lý đầu vào giống nhau. Không dùng hành vi một trình duyệt chấp nhận một chuỗi để kết luận `java.net.URI` sẽ phân tích chuỗi đó giống hệt, hoặc ngược lại.

## 10. Xây dựng URI và nhận parameter trong Spring

### 10.1. Truyền dữ liệu thô vào builder theo đúng chế độ

Ví dụ dùng Spring Web và `Map.of` của JDK 9 trở lên. Các biến template được encode sau khi mở rộng theo cách builder đã cấu hình:

```java
URI target = UriComponentsBuilder
        .fromUriString("https://api.example.test")
        .pathSegment("v1", "products")
        .queryParam("q", "{q}")
        .queryParam("page", 0)
        .queryParam("size", 20)
        .encode()
        .buildAndExpand(Map.of("q", "C++ & Java"))
        .toUri();

System.out.println(target);
```

`URI` thuộc `java.net`, `Map` thuộc `java.util`, còn `UriComponentsBuilder` thuộc `org.springframework.web.util`.

Kết quả:

```text
https://api.example.test/v1/products?q=C%2B%2B%20%26%20Java&page=0&size=20
```

Ở đây, `q` được khai báo là URI variable. Việc gọi `encode()` trước khi mở rộng variable giúp giá trị dữ liệu được mã hóa chặt, bao gồm những ký tự có thể mang nghĩa cấu trúc như dấu cộng hoặc `&` trong ngữ cảnh này.

Đầu vào là chuỗi thô `C++ & Java`, không phải chuỗi đã encode. Nếu đưa sẵn `%2B` vào một quy trình tiếp tục encode dấu `%`, kết quả có thể thành `%252B`: đó là dữ liệu khác sau một lần decode.

Không suy ra mọi chuỗi gọi builder theo mọi thứ tự đều có cùng hành vi. Cần phân biệt dữ liệu thô, URI đã encode và template variable, rồi sử dụng API đúng với trạng thái đầu vào.

### 10.2. Nhận query trong controller

Giả sử controller đã được cấu hình và có service `catalog`:

```java
@GetMapping("/v1/products")
public ProductPage searchProducts(
        @RequestParam("q") String query,
        @RequestParam(name = "page", defaultValue = "0") int page,
        @RequestParam(name = "size", defaultValue = "20") int size) {
    return catalog.search(query, page, size);
}
```

DTO `ProductPage`, cấu hình controller, import và triển khai service được lược bỏ. Annotation thuộc Spring MVC. Trong ví dụ này, parameter của request `GET` được lấy từ query theo hợp đồng đã định nghĩa.

Với URI được tạo ở trên, service phải nhận từ khóa `C++ & Java`, không phải chuỗi còn chứa `%2B`, và cũng không phải `C` kèm hai dấu cách.

Framework chuyển kiểu `page` và `size` không có nghĩa mọi giá trị đều hợp lệ. Hợp đồng vẫn cần quy định trang đầu, kích thước tối thiểu và tối đa, cùng cách phản hồi lỗi. Không tự gọi thêm `URLDecoder` lên `query` chỉ vì thấy dữ liệu từng có percent-encoding trên wire.

Nếu API hỗ trợ key lặp để tạo danh sách, kiểu parameter và quy tắc binding cũng cần thể hiện điều đó; không dùng một `String` rồi âm thầm bỏ các giá trị còn lại.

### 10.3. Biến path theo cùng hợp đồng

Một ánh xạ như:

```java
@GetMapping("/v1/orders/{orderId}")
public OrderView getOrder(
        @PathVariable("orderId") String orderId) {
    return orders.getRequired(orderId);
}
```

lấy định danh từ path, không lấy từ một parameter query cũng có tên `orderId`. Các ví dụ giả định service thực hiện validation và kiểm tra quyền phù hợp. Biết URI của đơn hàng không tự cấp quyền truy cập đơn đó.

## 11. Địa chỉ công khai và địa chỉ phía sau proxy

Một request công khai có thể dùng:

```text
https://api.example.test/api/v1/orders
```

nhưng gateway chuyển tiếp đến ứng dụng bằng:

```text
http://orders-service:8080/v1/orders
```

Đây là hai địa chỉ ở hai chặng khác nhau. Origin và prefix mà người dùng nhìn thấy khác với địa chỉ kết nối nội bộ của ứng dụng.

Khi tạo `Location`, liên kết phân trang, URI trong OpenAPI hoặc redirect, API cần dùng thông tin địa chỉ công khai phù hợp. Nếu lấy trực tiếp mọi giá trị từ kết nối nội bộ, response có thể trỏ tới host nội bộ hoặc bỏ mất prefix `/api`.

Các hạ tầng có thể chuyển thông tin qua `Forwarded` hoặc các header theo quy ước như `X-Forwarded-*`. Ứng dụng chỉ nên diễn giải chúng theo cấu hình proxy được tin cậy và quy tắc triển khai; không coi mọi giá trị header do một request bất kỳ gửi vào là địa chỉ công khai có thẩm quyền.

Cần kiểm tra liên kết qua đường truy cập thực tế, gồm gateway và path rewrite, thay vì chỉ kiểm tra controller khi gọi thẳng vào cổng nội bộ.

## 12. URI liên quan thế nào đến các phần khác của REST API?

| Chủ đề | Liên hệ với URI |
| --- | --- |
| Resource | URI định danh đích tương tác; path không bắt buộc phản chiếu database |
| HTTP method | Cùng URI có thể được tương tác bằng các phương thức khác nhau theo hợp đồng |
| Phân trang và lọc | Query hoặc reference tới trang tiếp theo phải có quy tắc rõ |
| Cache | Query và các thành phần đích có thể làm thay đổi cache key; cùng path chưa đủ xác định cùng response |
| Content negotiation | Cùng URI có thể có nhiều biểu diễn được chọn bằng header; cần metadata như `Vary` khi phù hợp |
| Idempotency | Một URI ổn định không tự làm thao tác `POST` trở thành idempotent |
| Xác thực, phân quyền | URI biết được không phải thông tin cấp quyền; origin cũng không phải danh tính người dùng |
| OpenAPI | Cần mô tả server URL, path template và parameter theo đúng địa chỉ công khai |
| Kiểm thử | Cần kiểm tra cả parsing, encoding, binding, liên kết và hành vi qua proxy |

Một ví dụ quan trọng: `/orders?page=0` và `/orders?page=1` có thể có cùng origin nhưng là hai URI khác nhau phục vụ hai phần dữ liệu. Cùng origin không đồng nghĩa cùng tài nguyên hoặc cùng cache entry.

Ngược lại, hai URL khác origin có thể cùng dẫn tới một dữ liệu nghiệp vụ phía trong. Điều đó không tự xóa ranh giới origin của trình duyệt hoặc biến chúng thành một địa chỉ công khai duy nhất.

## 13. Các trường hợp nên kiểm tra khi triển khai

| Trường hợp | Kỳ vọng cần xác minh |
| --- | --- |
| HTTPS không ghi port và HTTPS ghi `443` | Xác định cùng origin theo cổng hiệu lực, dù biểu diễn URI khác nhau |
| HTTPS đổi sang `8443` | Nhận biết khác origin |
| Đổi `/orders` sang `/orders/` | Có hành vi đã công bố, không phụ thuộc alias ngẫu nhiên ở một lớp |
| Query chứa `C++`, `A&B` hoặc tiếng Việt | Giá trị đến service giữ nguyên ý nghĩa sau parsing và decoding |
| Key query lặp | Không mất dữ liệu hoặc đổi thứ tự ngoài hợp đồng |
| ID chứa slash mã hóa | Hành vi phù hợp miền ID và các lớp định tuyến đã hỗ trợ |
| URI có fragment | Server không nhận fragment như một parameter HTTP tự động |
| Base có và không có slash cuối | Relative reference được phân giải thành đích dự kiến |
| API chạy sau prefix của gateway | `Location` và các liên kết giữ đúng origin và path công khai |
| Hai tài khoản gọi cùng URI | Phân quyền vẫn được áp dụng, không dựa vào việc biết ID |

Các kiểm tra này là kiểm tra hợp đồng URI, không chỉ kiểm tra xem một chuỗi có parse được hay không. Một URI đúng cú pháp vẫn có thể trỏ sai origin, chọn sai trang hoặc mang sai giá trị dữ liệu.

## 14. Tự đọc một URI trước khi gửi request

Khi gặp một địa chỉ API mới, hãy lần lượt trả lời:

1. **Scheme nào được dùng?** Cơ chế truy cập và cổng mặc định là gì?
2. **Authority là gì?** Host và port tường minh nằm ở đâu; có thành phần nào cần parser xử lý riêng không?
3. **Origin là gì?** So sánh bộ ba scheme, host và cổng hiệu lực với origin liên quan.
4. **Path định danh gì?** Segment nào là phần cố định, segment nào là dữ liệu theo hợp đồng?
5. **Query có cấu trúc nào?** Kiểu dữ liệu, key lặp, giá trị rỗng và thứ tự được định nghĩa ra sao?
6. **Có fragment không?** Dữ liệu nào thực sự được gửi tới server?
7. **Giá trị đã encode chưa?** Có nguy cơ mã hóa lặp hoặc decode nhiều lần không?
8. **Nếu là reference tương đối, base là gì?** Kết quả có giữ đúng origin và prefix dự kiến không?

Với `https://api.example.test:8443/v1/orders/ord-123?include=items&lang=vi#summary`, kết luận phù hợp là request nhắm tới origin HTTPS trên cổng 8443, path xác định đơn hàng theo hợp đồng, query yêu cầu thêm dữ liệu và ngôn ngữ, còn fragment không đi vào request target. Phương thức HTTP, header, quyền truy cập và schema response vẫn cần được đọc tiếp để hiểu đầy đủ tương tác với tài nguyên.
