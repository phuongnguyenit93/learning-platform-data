# RewriteRequestParameter và quy tắc thay query parameter trong Spring Cloud Gateway

Trong **SPRING_CLOUD_GATEWAY**, client thường gửi dữ liệu qua URL, ví dụ `GET /api/products?campaign=summer&sort=price`. Gateway có thể cần chuẩn hóa một query parameter trước khi chuyển tiếp sang microservice: thay `campaign=summer` bằng một mã chiến dịch được chấp nhận, ép tham số tương thích với API backend mới hoặc loại bỏ các giá trị lặp. **`RewriteRequestParameter`** là GatewayFilter Factory dành cho nhu cầu **thay thế giá trị của một query parameter đã có mặt**.

Điểm khác biệt dễ bỏ sót: filter này **không tự thêm parameter khi tên đó vắng mặt**, và khi một tên xuất hiện nhiều lần, nó **thay toàn bộ các giá trị bằng đúng một giá trị thay thế**. Bài học thuộc chương **Nội dung HTTP**, tập trung vào quy tắc chính xác đó, cú pháp cấu hình, tương tác với route predicates và các filter khác, URL encoding, kiểm thử downstream và các rủi ro bảo mật/vận hành.

> **Phạm vi:** Ví dụ sử dụng **Spring Cloud Gateway Server WebFlux 4.x** với namespace cấu hình `spring.cloud.gateway.routes`. Các dòng mới, chẳng hạn Gateway Server WebFlux 5.x, có thể sử dụng namespace `spring.cloud.gateway.server.webflux.routes`; Gateway Server MVC có biến thể cấu hình khác. Hãy kiểm tra phiên bản Gateway, Spring Cloud release train và web stack thực tế. Những URL, hostname, phiên bản chiến dịch trong bài đều là ví dụ minh họa, không phải cấu hình production có sẵn.

## 1. Query parameter nằm ở đâu trong HTTP request?

Xét request:

~~~http
GET /api/products/42?campaign=summer&sort=price HTTP/1.1
Host: api.example.test
Accept: application/json
~~~

Có thể tách các thành phần:

| Thành phần | Giá trị ví dụ | Vai trò |
|---|---|---|
| HTTP method | `GET` | Chỉ hành động mà client yêu cầu |
| Path | `/api/products/42` | Phần đường dẫn được route predicate và các path filter xử lý |
| Query string | `campaign=summer&sort=price` | Các cặp tên/giá trị phía sau dấu `?` |
| Query parameter | `campaign` → `summer` | Một tham số có tên và giá trị |
| Request header | `Accept: application/json` | Metadata của request |
| Request body | Không có trong ví dụ | Payload riêng với URL/query; có thể là JSON, form hoặc bytes |

**Query parameter không phải HTTP body.** Dù cùng liên quan “nội dung HTTP”, `RewriteRequestParameter` chỉ thay **query string trong request URI gửi xuống downstream**, không sửa JSON body, form body, request header hay path. Nếu cần sửa body thì dùng cơ chế như `ModifyRequestBody` theo đúng phiên bản; nếu cần sửa path thì xem `RewritePath`/`StripPrefix`; nếu cần sửa header thì dùng các filter header tương ứng.

Một query có thể chứa **nhiều giá trị cho cùng một tên**:

~~~text
/api/products?campaign=summer&campaign=winter&sort=price
~~~

Ở tầng WebFlux, `ServerHttpRequest.getQueryParams()` thường biểu diễn trường hợp này bằng cấu trúc đa giá trị, về mặt ý nghĩa:

~~~text
campaign -> [summer, winter]
sort     -> [price]
~~~

Vì thế, nói “thay query parameter” phải trả lời thêm: thay một giá trị hay thay **toàn bộ danh sách**? `RewriteRequestParameter` áp dụng quy tắc thứ hai.

## 2. Hợp đồng của `RewriteRequestParameter`

Filter nhận **hai tham số**:

- `name`: tên query parameter cần tìm, ví dụ `campaign`.
- `replacement`: giá trị mới dùng để thay thế, ví dụ `fall2027`.

Cú pháp rút gọn:

~~~text
RewriteRequestParameter=<name>,<replacement>
~~~

Với cấu hình:

~~~yaml
filters:
  - RewriteRequestParameter=campaign,fall2027
~~~

hành vi mong đợi là:

| Query string đầu vào | Query string logic chuyển tiếp | Giải thích |
|---|---|---|
| `?campaign=summer` | `?campaign=fall2027` | Đổi giá trị của tên đã có |
| `?campaign=summer&sort=price` | `?campaign=fall2027&sort=price` | Không làm mất tham số khác |
| `?campaign=summer&campaign=winter` | `?campaign=fall2027` | **Nhiều giá trị cùng tên thu gọn còn một** |
| `?sort=price` | `?sort=price` | **Không có `campaign` → không thêm mới** |
| Không có dấu `?` | Vẫn không có `campaign` | Không tự sinh query |
| `?campaign=` | `?campaign=fall2027` | Tên tồn tại với giá trị rỗng; có thể được thay |
| `?Campaign=summer` | `?Campaign=summer` | Tên query khác chữ hoa/thường, không khớp tên `campaign` |

**Bảng biểu diễn ý nghĩa của query parameter**, không bảo đảm thứ tự cặp tham số, chữ hoa/thường của phần đã percent-encode hay dấu `+`/`%20` trên dây mạng sẽ được giữ nguyên từng byte. Framework có thể xây dựng lại URI với encoding phù hợp.

Các tính chất quan trọng:

1. **Chỉ xử lý request đã chọn route áp dụng filter.** Không phải một phép biến đổi tất cả request đi qua cùng cổng.
2. **Thay toàn bộ giá trị của đúng một tên.** Nếu tên xuất hiện nhiều lần, kết quả cho tên đó là một giá trị mới.
3. **Không tạo tham số bị thiếu.** Muốn thêm khi thiếu phải chọn cách khác, chẳng hạn `AddRequestParameter` và kiểm soát điều kiện bổ sung.
4. **Không dùng regex để thay một phần chuỗi.** `replacement` là giá trị thay thế, không phải biểu thức tìm/thay bằng pattern tùy ý.
5. **Không tự thay HTTP method, path, header hoặc body.** Các thành phần khác của request được xử lý bởi chức năng riêng.

### So sánh với các bộ lọc gần tên

| Factory | Khi tên đã có | Khi tên chưa có | Phạm vi |
|---|---|---|---|
| `RewriteRequestParameter` | Thay toàn bộ giá trị của tên bằng **một** giá trị | Giữ nguyên, không thêm | Query của request |
| `AddRequestParameter` | Thêm giá trị mới, có thể tạo nhiều giá trị cùng tên | Thêm parameter mới | Query của request |
| `RemoveRequestParameter` | Xóa parameter theo tên khỏi query | Không có gì để xóa | Query của request |
| `RewritePath` | Biến đổi **path** bằng quy tắc/regex | Không phải thao tác query | Path của request |
| `SetRequestHeader` | Ghi đè giá trị header theo tên | Tạo header theo tên | Request header |
| `ModifyRequestBody` | Biến đổi payload theo cơ chế body | Tùy handler/body filter | Request body |

**Không thay `RewriteRequestParameter` bằng `AddRequestParameter` chỉ vì cả hai cùng nhận hai chuỗi.** Cái đầu có tính **ghi đè có điều kiện**, cái sau có tính **bổ sung**.

## 3. Ví dụ cấu hình route hoàn chỉnh

Giả sử Gateway lắng nghe cổng `8080`, một backend catalog lắng nghe `9090` và phục vụ `GET /products/42`. Client gọi `/api/products/42` với chiến dịch bất kỳ; Gateway muốn backend luôn nhận `campaign=fall2027` nếu client có truyền `campaign`.

~~~yaml
spring:
  cloud:
    gateway:
      routes:
        - id: catalog-campaign
          uri: http://localhost:9090
          predicates:
            - Path=/api/products/**
            - Method=GET
          filters:
            - StripPrefix=1
            - RewriteRequestParameter=campaign,fall2027
~~~

Giải thích:

1. `Path=/api/products/**` kiểm tra **đường dẫn** của request; `Method=GET` giới hạn method.
2. Chỉ khi các predicates khớp, Gateway mới chọn `catalog-campaign` và chạy filters của route.
3. `StripPrefix=1` bỏ phân đoạn `api` khỏi path, nên `/api/products/42` trở thành `/products/42`.
4. `RewriteRequestParameter` kiểm tra **query**. Nếu có `campaign`, thay mọi giá trị bằng `fall2027`.
5. Routing filter gửi request đã biến đổi đến `http://localhost:9090`; trong môi trường Docker/Kubernetes, `localhost` phải được thay bằng địa chỉ downstream thực sự có thể truy cập từ tiến trình Gateway.

Luồng ví dụ:

~~~mermaid
flowchart LR
    C["GET /api/products/42?campaign=summer&sort=price"] --> P["Path + Method match"]
    P --> F1["StripPrefix=1"]
    F1 --> F2["RewriteRequestParameter campaign → fall2027"]
    F2 --> D["Backend: /products/42?campaign=fall2027&sort=price"]
    D --> R["Response về client"]
~~~

**Quan sát quan trọng:** URI mà client dùng để gọi Gateway **không thay đổi trên máy client**. Filter tạo request chuyển tiếp với URI được điều chỉnh cho downstream. Khi backend phản hồi, Gateway trả response theo chuỗi xử lý; filter này không có chức năng đổi giá trị query trong đường dẫn hiển thị của trình duyệt bằng redirect.

### Cú pháp đầy đủ: `name` và `args`

Cũng có thể khai báo như sau:

~~~yaml
spring:
  cloud:
    gateway:
      routes:
        - id: catalog-campaign
          uri: http://localhost:9090
          predicates:
            - Path=/api/products/**
            - Method=GET
          filters:
            - StripPrefix=1
            - name: RewriteRequestParameter
              args:
                name: campaign
                replacement: fall2027
~~~

Hai chữ `name` ở đây **khác ý nghĩa**:

- `filters[1].name`: chọn **factory** tên `RewriteRequestParameter`.
- `filters[1].args.name`: tên **query parameter** cần thay, tức `campaign`.
- `filters[1].args.replacement`: giá trị mới, tức `fall2027`.

Không đổi `args.replacement` thành `args.value` theo thói quen từ `AddRequestParameter`; các factory có tên trường và hợp đồng riêng.

### Chọn shortcut hay khai báo đầy đủ?

| Tình huống | Gợi ý |
|---|---|
| Tên và giá trị ngắn, không có dấu phẩy | Shortcut dễ đọc: `RewriteRequestParameter=campaign,fall2027` |
| Cần code review rõ các tham số | Expanded: `name` + `args.name` + `args.replacement` |
| Replacement chứa dấu phẩy hoặc ký tự YAML nhạy cảm | Expanded và quote chuỗi thích hợp |
| Dự án có nhiều filter với tham số phức tạp | Ưu tiên expanded để giảm nhầm thứ tự và field |
| Nâng cấp release train | Đối chiếu **tài liệu đúng phiên bản**, không đổi cú pháp theo ví dụ của phiên bản khác |

## 4. Quy tắc với tham số trùng tên, tham số thiếu và tham số rỗng

### 4.1. Có nhiều giá trị cùng tên

Request:

~~~http
GET /api/products/42?campaign=summer&campaign=winter&sort=price HTTP/1.1
Host: gateway.example.test
~~~

Gateway dùng `RewriteRequestParameter=campaign,fall2027`. Backend được kỳ vọng nhận **một** giá trị `fall2027` cho `campaign`, còn `sort=price` được giữ về mặt ý nghĩa.

~~~text
Trước filter:
  campaign -> ["summer", "winter"]
  sort     -> ["price"]

Sau filter:
  campaign -> ["fall2027"]
  sort     -> ["price"]
~~~

Điều này giúp tránh tình huống backend đọc **giá trị đầu tiên** nhưng lớp middleware khác lại đọc **giá trị cuối cùng** của tham số trùng tên. Tuy nhiên, đây **không phải biện pháp xác thực**: những parameter khác hoặc route khác vẫn có thể gây mơ hồ nếu hệ thống không kiểm soát.

### 4.2. Không có tên tham số

Request:

~~~http
GET /api/products/42?sort=price HTTP/1.1
Host: gateway.example.test
~~~

Vì `campaign` **không tồn tại**, filter không làm xuất hiện `campaign=fall2027`. Nếu backend đòi bắt buộc phải có tham số này, **chỉ cấu hình `RewriteRequestParameter` là chưa đủ**.

Các hướng thiết kế khác nhau:

- **Bắt buộc client cung cấp:** dùng `Query` route predicate hoặc validation ở backend; phản hồi lỗi rõ ràng nếu thiếu.
- **Luôn bổ sung giá trị:** dùng `AddRequestParameter` theo chính sách và hiểu rõ trường hợp trùng tên.
- **Bổ sung chỉ khi thiếu:** cần logic điều kiện phù hợp (có thể là custom filter hoặc xử lý ở backend); không giả định một factory `RewriteRequestParameter` tự làm điều đó.

### 4.3. Có tên nhưng giá trị rỗng

Với `?campaign=` hoặc `?campaign`, cần phân biệt **tên hiện diện** và **tên không có**. Tại lớp phân tích query của framework, những trường hợp có tên với giá trị rỗng thường vẫn biểu diễn việc parameter tồn tại; `RewriteRequestParameter` sẽ thay giá trị đó.

Nên đưa cả `?campaign=` và `?campaign` vào integration test vì cách parse/encode query qua các proxy và framework có thể khác nhau, đặc biệt với dữ liệu đến từ client không chuẩn.

### 4.4. Tên query phân biệt hoa/chữ thường

Trong query string, `campaign` và `Campaign` thường được xử lý là **hai tên khác nhau**. Không áp dụng quy tắc HTTP header (tên header không phân biệt hoa/thường) cho query parameter.

~~~text
Đầu vào: ?campaign=summer&Campaign=winter
Filter:   RewriteRequestParameter=campaign,fall2027
Dự kiến: campaign=fall2027, Campaign=winter
~~~

Nếu API cần chuẩn hóa tên tham số, định nghĩa quy ước công khai và xử lý tại backend hoặc bằng một filter chuyên dụng; không suy đoán factory này thực hiện lowercase toàn bộ query.

## 5. Quan hệ giữa `Query` Route Predicate và `RewriteRequestParameter`

Một **`Query` Route Predicate** kiểm tra tham số trong request **khi Gateway đang chọn route**. `RewriteRequestParameter` là **GatewayFilter chạy sau khi route đã được chọn**.

~~~mermaid
sequenceDiagram
    participant C as Client
    participant M as RoutePredicateHandlerMapping
    participant F as GatewayFilterChain
    participant B as Backend
    C->>M: GET /products?campaign=summer
    M->>M: Kiểm tra Path / Query / Method trên request gốc
    alt Route khớp
        M->>F: Giao route đã chọn
        F->>F: RewriteRequestParameter campaign = fall2027
        F->>B: GET /products?campaign=fall2027
        B-->>C: Response qua Gateway
    else Route không khớp
        M-->>C: Xét route khác hoặc handler khác
    end
~~~

Ví dụ:

~~~yaml
spring:
  cloud:
    gateway:
      routes:
        - id: selected-by-query
          uri: http://localhost:9090
          predicates:
            - Path=/products/**
            - Query=campaign,summer
          filters:
            - RewriteRequestParameter=campaign,fall2027
~~~

- Request `GET /products/42?campaign=summer`: predicate `Query` **khớp giá trị gốc**; route được chọn rồi filter thay giá trị gửi xuống backend.
- Request `GET /products/42?campaign=fall2027`: không khớp biểu thức `summer` của predicate route này, dù `fall2027` là giá trị mà filter muốn tạo nếu route được chọn.
- Request không có `campaign`: predicate không khớp; filter của route này không chạy.

**Kết luận:** Không thiết kế một route yêu cầu giá trị query đã được filter của chính route đó tạo ra, trừ khi predicate vốn cũng khớp request gốc. Thứ tự logic là **route matching → GatewayFilter → routing**, không phải chiều ngược lại.

## 6. Kết hợp `AddRequestParameter` và `RemoveRequestParameter`

### Add trước, Rewrite sau

~~~yaml
filters:
  - AddRequestParameter=campaign,from-gateway
  - RewriteRequestParameter=campaign,fall2027
~~~

Ở một chuỗi xử lý thông thường với các filter thực thi phép biến đổi request theo thứ tự này:

- Nếu client **chưa có `campaign`**, `AddRequestParameter` thêm `campaign=from-gateway`, rồi `RewriteRequestParameter` biến thành `campaign=fall2027`.
- Nếu client đã có `campaign=summer`, Add có thể tạo danh sách `[summer, from-gateway]`, rồi Rewrite thu gọn còn `[fall2027]`.

Như vậy, cấu hình **Add rồi Rewrite** có thể tạo hiệu ứng “luôn có một giá trị cuối”. Tuy nhiên cần **kiểm tra filter order thực tế**, nhất là khi có default/global filter hoặc filter có order tùy chỉnh.

### Rewrite trước, Add sau

~~~yaml
filters:
  - RewriteRequestParameter=campaign,fall2027
  - AddRequestParameter=campaign,from-gateway
~~~

Nếu request ban đầu có `campaign`, bước Rewrite đặt `fall2027`, sau đó Add có thể thêm `from-gateway`. Backend có thể nhận **hai giá trị**, khác mục tiêu một giá trị của `RewriteRequestParameter` khi chạy đơn lẻ.

Nếu request ban đầu **không có `campaign`**, bước Rewrite không làm gì, rồi Add tạo `campaign=from-gateway`. Hai thứ tự cấu hình vì thế **không tương đương**.

### Remove trước hoặc sau Rewrite

~~~yaml
filters:
  - RemoveRequestParameter=campaign
  - RewriteRequestParameter=campaign,fall2027
~~~

Sau Remove, tên `campaign` không còn, vì vậy Rewrite **không có gì để thay**. Đảo chiều:

~~~yaml
filters:
  - RewriteRequestParameter=campaign,fall2027
  - RemoveRequestParameter=campaign
~~~

thì giá trị vừa được thay cuối cùng cũng bị xóa. Đặt cả hai trong cùng route chỉ hợp lý khi bạn hiểu đầy đủ logic và filter order.

| Thứ tự trên một route đơn giản | Đầu vào `?campaign=old` | Kết quả logic |
|---|---|---|
| Chỉ Rewrite | `old` | `fall2027` |
| Add rồi Rewrite | `old` | `fall2027` |
| Rewrite rồi Add | `old` | `fall2027` và `from-gateway` |
| Remove rồi Rewrite | `old` | Không còn `campaign` |
| Rewrite rồi Remove | `old` | Không còn `campaign` |

**Đừng nhầm `Route.order` với filter order.** `Route.order` quyết định ưu tiên các route có khả năng match; filter order liên quan thứ tự trong chuỗi xử lý khi route đã được chọn. Các `GlobalFilter` hoặc filter nội bộ có thể tham gia chuỗi, do đó cần kiểm tra request downstream thực tế khi có cấu hình phức tạp.

## 7. URL encoding và ký tự đặc biệt

Query parameter trên HTTP URI có thể chứa khoảng trắng, dấu `&`, `=`, `#`, ký tự Unicode và các ký tự cần percent-encoding. Ví dụ giá trị logic `blue & green` không thể được nối thẳng vào URL dưới dạng ký tự `&` chưa encode, vì dấu `&` có vai trò phân tách parameters.

**Nên viết dạng expanded** khi giá trị khó đọc trong shortcut:

~~~yaml
filters:
  - name: RewriteRequestParameter
    args:
      name: label
      replacement: 'blue & green'
~~~

Trong thực thi, giá trị cần được biểu diễn thành URI hợp lệ theo cơ chế encode/build URI của Spring Framework và phiên bản Gateway đang dùng. **Không tự giả định** rằng output trên dây mạng sẽ là `blue%20%26%20green` hay `blue+%26+green`: cách biểu diễn khoảng trắng và việc parse theo loại query còn phụ thuộc lớp HTTP/framework. Hãy kiểm tra **giá trị đã decode ở downstream** lẫn **raw query** nếu hợp đồng API quan tâm đến từng byte.

Những điểm cần lưu ý:

- Dấu `&` phân tách cặp query; dấu `=` phân tách tên và giá trị theo quy ước phổ biến. Nếu chúng là dữ liệu, phải encode phù hợp.
- Dấu `#` là phần bắt đầu fragment trong URI của client; fragment thông thường **không được gửi trong HTTP request tới server**. Không trông đợi Gateway xử lý fragment như query.
- Dấu `+` có thể được diễn giải là khoảng trắng theo quy tắc form URL encoding của một số thành phần; không suy ra semantics giống nhau ở mọi backend.
- Unicode được thể hiện bằng UTF-8 và percent-encoding trong URI khi cần; kiểm tra end-to-end với ký tự tiếng Việt.
- Không ghép query bằng nối chuỗi thủ công như `oldUri + "&campaign=" + userInput`. Nếu viết filter riêng, sử dụng builder/API URI đúng cách, giữ các tham số khác và xử lý encoding an toàn.

### Dấu phẩy trong shortcut

Shortcut dùng dấu phẩy để phân tách `name` và `replacement`. Nếu replacement chứa dấu phẩy, ví dụ `east,west`, hãy dùng expanded:

~~~yaml
filters:
  - name: RewriteRequestParameter
    args:
      name: region
      replacement: 'east,west'
~~~

Điều này diễn đạt **một chuỗi giá trị `east,west`**. Đừng viết `RewriteRequestParameter=region,east,west` rồi mặc định factory hiểu ba token theo cách bạn muốn.

### Query đã ký (signed URL)

Một số hệ thống ký HMAC hoặc tạo chữ ký presigned URL trên **query string** hoặc biểu diễn chuẩn hóa của URI. Dù việc thay `campaign` là hợp lệ về mặt kỹ thuật, nó có thể làm **chữ ký sai** nếu tham số là một phần dữ liệu được ký. Với URL đã ký:

1. Xác định thành phần nào kiểm tra signature: Gateway, backend hay hệ thống lưu trữ.
2. Không đổi query sau khi chữ ký được tạo nếu điều đó làm sai hợp đồng ký.
3. Nếu cần chuẩn hóa, thực hiện trước bước ký hoặc cập nhật thiết kế ký/ủy quyền theo một trình tự đã được kiểm chứng.
4. Kiểm tra raw query, encoding và tên parameter trùng lặp trong integration test bảo mật.

## 8. Tương tác với header, body và response

`RewriteRequestParameter` sửa **request URI** nhưng không đổi nội dung JSON body. Ví dụ client gửi:

~~~http
POST /api/orders?campaign=summer HTTP/1.1
Host: gateway.example.test
Content-Type: application/json

{"campaign":"summer","quantity":2}
~~~

Nếu route cho phép POST và áp dụng `RewriteRequestParameter=campaign,fall2027`, thì backend có thể nhận URI `/api/orders?campaign=fall2027` (hoặc path đã được một filter khác viết lại), nhưng body vẫn chứa `"campaign":"summer"` nếu không có body filter khác can thiệp.

**Đừng dựa vào hai nơi có dữ liệu trùng tên mà tự giả định chúng nhất quán.** Backend phải xác định nguồn dữ liệu chính: query, body hay token/claims. Nếu hợp đồng API yêu cầu chúng giống nhau, cần validation rõ ràng hoặc thiết kế request khác.

Tương tự:

- `AddRequestHeader` và `SetRequestHeader` sửa **request headers**, không tác động query.
- `RewritePath`, `StripPrefix` sửa **path**, không biến giá trị `campaign` trong query.
- `RemoveResponseHeader`, `SetResponseHeader`, `SetStatus` tác động **response**, không quyết định giá trị query gửi xuống backend.
- `ModifyRequestBody` xử lý payload, có thể liên quan buffering/serialization, không phải chức năng của `RewriteRequestParameter`.

Điều này giúp phân loại lỗi: backend nhận đúng path nhưng sai campaign thì kiểm tra query filter; backend nhận đúng query nhưng body sai thì kiểm tra body/contract; response status sai thì xem downstream, error handling, retry, circuit breaker và response filters.

## 9. Bảo mật và tác động vận hành

Việc rewrite query parameter có thể đơn giản nhưng ảnh hưởng đến các lớp khác:

| Chủ đề | Tác động có thể xảy ra | Cách kiểm soát |
|---|---|---|
| **Xác thực/ủy quyền** | Query bị thay sau bước xác thực hoặc khác dữ liệu trong token | Không dùng rewrite làm cơ chế phân quyền; backend cần validate claims/quyền |
| **Rate limiting** | Nhiều giá trị client khác nhau bị gộp thành một giá trị downstream; limiter ở tầng khác có thể nhìn dữ liệu khác | Chọn key resolver đáng tin và xác định vị trí áp dụng limiter trong chain |
| **Cache/CDN** | Cache key có thể bao gồm raw URI/query; client và backend nhìn tên/giá trị khác nhau | Xác định chuẩn hóa query trước khi cache và thống nhất chiến lược cache key |
| **Circuit breaker/retry** | Mỗi lần retry có thể dùng request đã chỉnh; nhiều lần gửi gây tải phía backend | Chỉ retry operation hợp lệ, có timeout/backoff/idempotency rõ ràng |
| **Service discovery** | Query được giữ trên URI chuyển tiếp, còn instance do `lb://`/load balancer quyết định | Đảm bảo URI và chọn service instance đúng, không nhầm query với service ID |
| **TLS và URL signing** | Query có thể thuộc dữ liệu ký, nhưng TLS chỉ mã hóa đường truyền | Duy trì TLS cả hai chặng và kiểm tra chữ ký sau rewrite |
| **Quan sát request** | Log Gateway có thể ghi URI gốc, backend ghi URI đã rewrite | Gắn route ID/correlation ID, ghi nhận thay đổi mà không lộ dữ liệu nhạy cảm |
| **Dữ liệu cá nhân** | Query thường được ghi vào logs, browser history, analytics hoặc proxy | Tránh token/PII trong URL; redact query nhạy cảm ở mọi điểm logging |

### Không dùng rewrite để “lọc sạch” input

Thay `campaign=anything` thành `fall2027` không làm các phần còn lại của request an toàn. Client có thể đưa thêm những parameter chưa được xử lý, giá trị dài bất thường, Unicode khó chuẩn hóa hoặc dữ liệu độc hại trong body/header. Backend vẫn phải validate dữ liệu theo hợp đồng API, giới hạn kích thước request và kiểm soát truy cập.

Nếu ứng dụng có **nhiều instance Gateway**, xác nhận tất cả đã nạp cùng route/filter configuration; nếu một node chưa cập nhật, backend có thể thấy hai dạng `campaign` khác nhau tùy instance mà load balancer chọn.

## 10. Thực hành: kiểm chứng query từ downstream

### Chuẩn bị backend echo

Giả định một backend tại `http://localhost:9090` có endpoint `GET /products/42` trả JSON hoặc log các query parameters nhận được. Nếu đang dùng Spring WebFlux, controller minh họa trong **ứng dụng backend riêng** có thể như sau:

~~~java
import java.util.LinkedHashMap;
import java.util.Map;
import org.springframework.http.server.reactive.ServerHttpRequest;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
public class ProductEchoController {

    @GetMapping("/products/{id}")
    public Mono<Map<String, Object>> echo(@PathVariable String id,
                                           ServerHttpRequest request) {
        Map<String, Object> data = new LinkedHashMap<>();
        data.put("productId", id);
        data.put("rawQuery", request.getURI().getRawQuery());
        data.put("queryParams", request.getQueryParams());
        return Mono.just(data);
    }
}
~~~

Đây là controller dành cho **backend demo WebFlux** có đủ starter/web server, không phải code để đặt trực tiếp trong Gateway nếu mục tiêu là giữ kiến trúc gateway chỉ làm định tuyến. Trong production, tránh echo dữ liệu query nhạy cảm.

### Cấu hình Gateway thử nghiệm

~~~yaml
spring:
  cloud:
    gateway:
      routes:
        - id: rewrite-query-demo
          uri: http://localhost:9090
          predicates:
            - Path=/api/products/**
            - Method=GET
          filters:
            - StripPrefix=1
            - RewriteRequestParameter=campaign,fall2027
~~~

Gateway giả định chạy tại `http://localhost:8080`. Đảm bảo cấu hình được nạp sau restart hoặc cơ chế refresh route phù hợp phiên bản. Sau đó gọi:

~~~bash
# 1. Có giá trị ban đầu
curl -i "http://localhost:8080/api/products/42?campaign=summer&sort=price"

# 2. Hai giá trị cùng tên
curl -i "http://localhost:8080/api/products/42?campaign=summer&campaign=winter"

# 3. Thiếu tham số campaign
curl -i "http://localhost:8080/api/products/42?sort=price"

# 4. Giá trị rỗng
curl -i "http://localhost:8080/api/products/42?campaign="

# 5. Tên khác chữ hoa/thường
curl -i "http://localhost:8080/api/products/42?Campaign=summer"
~~~

Kết quả kỳ vọng ở `queryParams` mà backend nhận:

| Test | Giá trị `campaign` tại backend | Ghi chú |
|---|---|---|
| 1 | `[fall2027]` | `sort=price` vẫn tồn tại |
| 2 | `[fall2027]` | Hai giá trị được thu gọn |
| 3 | Không có key `campaign` | Không thêm mới |
| 4 | `[fall2027]` | Tên có mặt dù giá trị rỗng |
| 5 | Không có key `campaign`; `Campaign=[summer]` | Tên query khác chữ hoa/thường |

Nếu kết quả khác kỳ vọng, kiểm tra response backend **trực tiếp** để biết controller có parse đúng query hay không; xem URI thực nhận tại downstream, danh sách routes, filter order, log của Gateway và proxy ở giữa. Không kết luận filter sai chỉ bằng response `404` hoặc `5xx`: `404` có thể do route không match; `5xx` có thể do backend không chạy.

### So sánh với `AddRequestParameter`

Thay riêng dòng filter thành:

~~~yaml
filters:
  - StripPrefix=1
  - AddRequestParameter=campaign,fall2027
~~~

Chạy lại test 2 và 3:

- Test 2: có thể thấy **giá trị cũ cùng giá trị mới**, thay vì chỉ `fall2027`.
- Test 3: backend thấy `campaign=fall2027` dù client không gửi tham số này.

Khôi phục `RewriteRequestParameter` sau thử nghiệm nếu chính sách chỉ cho phép thay tham số **đã có**.

### Thử path/method không khớp

~~~bash
curl -i -X POST "http://localhost:8080/api/products/42?campaign=summer"
curl -i "http://localhost:8080/other/products/42?campaign=summer"
~~~

Hai request không thỏa predicates của route ví dụ. Nếu ứng dụng không có route/handler khác, chúng thường không được forward tới backend bởi route `rewrite-query-demo`; việc `RewriteRequestParameter` không chạy là đúng kiến trúc.

## 11. Những sai lầm thường gặp

| Triệu chứng/hiểu nhầm | Giải thích | Hướng xử lý |
|---|---|---|
| `RewriteRequestParameter` không thêm key còn thiếu | Đây là hành vi thiết kế, không phải lỗi | Dùng `AddRequestParameter`/validation/logic có điều kiện phù hợp |
| Có `campaign=old&campaign=new` nhưng backend chỉ thấy một giá trị mới | Factory thay **toàn bộ giá trị cùng tên** bằng một giá trị | Nếu muốn giữ lịch sử nhiều giá trị, không dùng Rewrite theo cách này |
| Không đổi `Campaign` viết hoa | Query parameter name phân biệt chữ hoa/thường | Chuẩn hóa hợp đồng API hoặc dùng logic riêng |
| YAML parse được nhưng filter không chạy | Route không match, sai version/namespace, sai tên factory, chưa refresh | Kiểm tra RouteDefinition, runtime version, route ID, log |
| Nhập `args.value` ở expanded config | Rewrite dùng tên field `replacement` | Đổi thành `args.replacement` |
| Query bị thêm dấu `+` hoặc `%20` khác trước | URL encoding/normalization hoặc proxy có thể thay biểu diễn thô | Đối chiếu decoded value và raw query theo hợp đồng |
| Backend kiểm tra chữ ký URL thất bại | Query đã bị sửa sau khi ký | Thiết kế lại thứ tự ký/validation; không sửa URL đã ký tùy tiện |
| Backend vẫn thấy JSON body cũ | Factory chỉ sửa query, không sửa body | Dùng body transformation/validation phù hợp |
| Query predicate không match dù filter muốn tạo giá trị ấy | Route matching xảy ra **trước** GatewayFilter | Chọn predicate theo request gốc hoặc dùng route khác |
| Hai Gateway node trả kết quả khác nhau | Khác cấu hình, route cache hoặc version | Kiểm tra rollout và refresh trên mọi instance |
| Request 429/401/403 không đi qua filter rewrite | Có thể bị chặn bởi security/rate limiter trước bước rewrite hoặc trước khi chọn route | Kiểm tra thứ tự và phạm vi các filter thực tế |
| Response body đổi khác dù query đúng | Downstream xử lý tham số mới theo business logic | Kiểm tra contract backend, cache/fallback và response status |

## 12. Checklist khi triển khai

- [ ] Tôi biết query string nằm trong **request URI**, khác với path/header/body.
- [ ] Tôi hiểu `RewriteRequestParameter(name, replacement)` chỉ thay **parameter có mặt**.
- [ ] Tôi biết nhiều giá trị cùng tên sẽ được thay bằng **một** giá trị.
- [ ] Tôi không kỳ vọng filter tạo parameter mới khi tên vắng mặt.
- [ ] Tôi đã phân biệt với `AddRequestParameter`, `RemoveRequestParameter`, `RewritePath` và `ModifyRequestBody`.
- [ ] Tôi dùng đúng cú pháp shortcut hoặc `name` + `args.name` + `args.replacement`.
- [ ] Tôi đã kiểm tra trường hợp parameter rỗng, lặp, viết hoa khác nhau và giá trị chứa ký tự cần encode.
- [ ] Tôi biết các route predicates được đánh giá **trước** khi filter rewrite chạy.
- [ ] Tôi kiểm tra filter order khi kết hợp Add/Remove/default/global filters.
- [ ] Tôi đã thử request với backend echo và kiểm tra cả **raw query** lẫn **decoded query params**.
- [ ] Tôi đã rà soát query đã ký, cache key, auth, rate limiting, retry/circuit breaker, TLS và service discovery nếu có.
- [ ] Tôi không đưa token hoặc dữ liệu cá nhân vào query/log và vẫn thực hiện validation ở backend.
- [ ] Tôi đã đối chiếu phiên bản Gateway/WebFlux/MVC và cách làm mới routes trong môi trường triển khai.

## Tài liệu tham khảo chính thức

- [RewriteRequestParameter GatewayFilter Factory — Spring Cloud Gateway Server WebFlux 4.3](https://docs.spring.io/spring-cloud-gateway/reference/4.3/spring-cloud-gateway-server-webflux/gatewayfilter-factories/rewriterequestparameter-factory.html) — mô tả hai tham số `name`, `replacement` và quy tắc ghi đè nhiều giá trị.
- [Spring Cloud Gateway Reference](https://docs.spring.io/spring-cloud-gateway/reference/) — chọn đúng phiên bản và biến thể, xem thêm `AddRequestParameter`, `RemoveRequestParameter` và các route predicate.
- [Spring Framework — ServerHttpRequest](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/http/server/reactive/ServerHttpRequest.html) — URI và query parameters ở request WebFlux.
- [Spring Framework — UriComponentsBuilder](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/util/UriComponentsBuilder.html) — làm việc với URI, query và encoding khi cần triển khai filter tùy biến.
- [RFC 3986: Uniform Resource Identifier](https://www.rfc-editor.org/rfc/rfc3986) — cú pháp URI và percent-encoding.

**Ghi nhớ:** `RewriteRequestParameter=campaign,fall2027` **chỉ thay khi `campaign` hiện diện**, **thu gọn mọi giá trị `campaign` về một giá trị mới**, và **không tự thêm `campaign` nếu thiếu**. Hãy thử các trường hợp một giá trị, nhiều giá trị, rỗng, không có và URL đã ký; đây là cách chắc chắn để Gateway chuẩn hóa query mà không phá vỡ hợp đồng giữa client và microservice.
