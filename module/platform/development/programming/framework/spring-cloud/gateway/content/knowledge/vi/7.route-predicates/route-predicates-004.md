# Header: kiểm tra header và biểu thức chính quy

## 1. Header predicate giải quyết vấn đề gì?

Trong **Spring Cloud Gateway**, mỗi route xác định **khi nào** một HTTP request được phép chọn route đó và **chuyển request tới đâu**. Điều kiện để chọn route gọi là **route predicate**. Bên cạnh điều kiện theo đường dẫn (`Path`), phương thức (`Method`) và hostname (`Host`), **Header Route Predicate Factory** cho phép quyết định route dựa trên sự hiện diện và giá trị của một HTTP request header, thường được kiểm tra bằng **biểu thức chính quy (regular expression/regex)**.

Ví dụ, hai client cùng gọi `GET /api/catalog/products`, nhưng request có `X-Client-Channel: mobile` được định tuyến tới một backend dành cho mobile, còn request khác đi tới backend mặc định.

~~~mermaid
flowchart LR
    C[Client request] --> G[Spring Cloud Gateway]
    G --> P{Path /api/catalog/**?}
    P -->|Không| N[Thử route khác]
    P -->|Có| H{X-Client-Channel khớp mobile?}
    H -->|Có| M[Mobile Catalog API]
    H -->|Không| D[Thử route mặc định]
~~~

Đây là cơ chế **chọn đích định tuyến**, hữu ích khi tổ chức phiên bản API, phân luồng theo loại client, phân tuyến thử nghiệm, hoặc cô lập một nhóm request theo hợp đồng HTTP. Nó **không tự xác thực danh tính** và **không thay thế phân quyền**: client có thể tự đặt hầu hết request header nếu hạ tầng không kiểm soát chúng.

Sau bài học, bạn cần có thể:

1. Giải thích cách `Header` kiểm tra tên header và giá trị bằng Java regex.
2. Viết route bằng cú pháp ngắn và cú pháp đầy đủ của Spring Cloud Gateway.
3. Phân biệt **tên header không phân biệt hoa/thường** với **giá trị header do regex quyết định**.
4. Kết hợp `Header` với `Path`, `Method` và route mặc định theo thứ tự ưu tiên.
5. Kiểm chứng request khớp/không khớp và tránh các lỗi về regex, YAML, header từ proxy và ranh giới bảo mật.

## 2. Cấu trúc và ý nghĩa của Header Route Predicate Factory

`Header` có hai đối số chính:

| Đối số | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| `header` | Tên HTTP request header cần kiểm tra | `X-Client-Channel` |
| `regexp` | Biểu thức chính quy dùng để so khớp giá trị header | `^(mobile|tablet)$` |

Biểu diễn ngắn trong danh sách `predicates`:

~~~yaml
predicates:
  - Header=X-Client-Channel, ^(mobile|tablet)$
~~~

Biểu diễn đầy đủ, thuận tiện khi regex dài hoặc cần phân tách rõ các đối số:

~~~yaml
predicates:
  - name: Header
    args:
      header: X-Client-Channel
      regexp: '^(mobile|tablet)$'
~~~

Trong cả hai cấu hình, một request có header `X-Client-Channel` mang giá trị `mobile` hoặc `tablet` thỏa điều kiện. Request thiếu header hoặc mang giá trị không phù hợp thì **predicate trả về false**; Gateway tiếp tục xét route có thể áp dụng, nếu có. Kết quả HTTP cuối cùng phụ thuộc các route khác và cấu hình xử lý lỗi, **không phải lúc nào cũng là 404**.

**Vị trí trong pipeline:** `Header` là điều kiện chọn route do `RoutePredicateHandlerMapping` đánh giá. Sau khi một route được chọn, Gateway mới chạy filter chain của route đó, ví dụ `StripPrefix`, `AddRequestHeader`, rate limiter hoặc circuit breaker. Vì vậy, một filter thuộc chính route **không thể bổ sung header rồi khiến predicate của route đó quay lại khớp**.

~~~mermaid
sequenceDiagram
    participant C as HTTP Client
    participant R as RoutePredicateHandlerMapping
    participant F as Gateway Filter Chain
    participant U as Upstream Service
    C->>R: GET /api/catalog/products (X-Client-Channel: mobile)
    R->>R: Path predicate = true
    R->>R: Header predicate = true
    R->>F: Selected route
    F->>F: Apply request/response filters
    F->>U: Forward HTTP request
    U-->>F: HTTP response
    F-->>C: HTTP response
~~~

## 3. Ví dụ route hoàn chỉnh trong Spring Cloud Gateway WebFlux

Một ứng dụng **Spring Cloud Gateway Server WebFlux** có thể khai báo:

~~~yaml
spring:
  cloud:
    gateway:
      server:
        webflux:
          routes:
            - id: catalog-mobile
              uri: http://localhost:9001
              predicates:
                - Path=/api/catalog/**
                - Method=GET
                - name: Header
                  args:
                    header: X-Client-Channel
                    regexp: '^(mobile|tablet)$'
              filters:
                - StripPrefix=2
~~~

Giải thích theo từng phần:

| Cấu hình | Tác dụng |
| --- | --- |
| `id: catalog-mobile` | Tên ổn định của route để quan sát, log và quản lý |
| `uri: http://localhost:9001` | Địa chỉ HTTP backend giả định của ví dụ |
| `Path=/api/catalog/**` | Chỉ xem xét request nằm dưới prefix `/api/catalog/` |
| `Method=GET` | Chỉ áp dụng cho phương thức GET |
| `Header=X-Client-Channel, ...` | Chỉ áp dụng khi header có giá trị thỏa regex |
| `StripPrefix=2` | Bỏ hai segment đầu trong path trước khi chuyển tới backend |

Với request:

~~~http
GET /api/catalog/products/42 HTTP/1.1
Host: localhost:8080
X-Client-Channel: mobile
~~~

Route được chọn khi **cả ba** điều kiện `Path`, `Method` và `Header` cùng đúng. Backend nhận request theo URL:

~~~text
GET http://localhost:9001/products/42
~~~

`StripPrefix=2` chỉ ảnh hưởng đường dẫn được chuyển tiếp; nó **không thay đổi cách Header predicate đã chọn route**. Địa chỉ `localhost:9001` ở đây chỉ minh họa; cần có backend đang chạy thì việc gọi thử mới trả response thành công.

**Tương thích phiên bản:** Namespace `spring.cloud.gateway.server.webflux.routes` áp dụng cho một số phiên bản Spring Cloud Gateway Server WebFlux mới. Ở các dòng trước, thuộc tính route thường có dạng `spring.cloud.gateway.routes`. Hãy dùng **đúng namespace của phiên bản** cùng starter Server WebFlux đang triển khai. **Server Web MVC** là biến thể khác, cần đối chiếu API và cách cấu hình riêng.

## 4. Biểu thức chính quy kiểm tra giá trị header như thế nào?

`Header` dùng **Java regular expression** để xác định giá trị phù hợp. Trong triển khai tiêu biểu của Spring Cloud Gateway, phép kiểm tra sử dụng ngữ nghĩa **khớp toàn bộ giá trị** (tương tự `String.matches(regexp)`), thay vì chỉ cần tìm được một đoạn con ở giữa chuỗi.

Ví dụ:

~~~yaml
predicates:
  - name: Header
    args:
      header: X-Api-Version
      regexp: '^v[12]$'
~~~

| Giá trị của X-Api-Version | Có khớp `^v[12]$`? | Lý do |
| --- | --- | --- |
| `v1` | Có | Bắt đầu bằng v và tiếp theo là 1 |
| `v2` | Có | Bắt đầu bằng v và tiếp theo là 2 |
| `v3` | Không | 3 không thuộc tập `[12]` |
| `V1` | Không | Regex mặc định phân biệt hoa/thường |
| `v1-beta` | Không | Giá trị không khớp toàn bộ |
| ` v1` | Không | Có ký tự khoảng trắng ở đầu |
| Không có header | Không | Không có giá trị nào để so khớp |

Các ký hiệu quan trọng:

| Ký hiệu regex | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| `^` và `$` | Ràng buộc đầu và cuối chuỗi | `^mobile$` |
| Phép chọn nhánh | Dùng dấu gạch đứng giữa các lựa chọn | Chấp nhận `mobile` hoặc `web` |
| `[0-9]` | Một chữ số | `^[0-9]+$` |
| `+` | Một hoặc nhiều lần | `^[a-z]+$` |
| `*` | Không hoặc nhiều lần | `^v[0-9]*$` |
| `?` | Thành phần trước tùy chọn | `^v2(?:-beta)?$` |
| `{m,n}` | Số lần lặp từ m đến n | `^[a-z]{2,8}$` |
| `(?i)` | Chế độ không phân biệt hoa/thường | `(?i)^mobile$` |
| `[.]` | Dấu chấm thật; không mang nghĩa wildcard | `^v2[.]1$` |

Trong regex, dấu gạch đứng (`|`) biểu thị phép chọn nhánh, ví dụ `^(mobile|web)$`. **Dấu chấm `.` đứng một mình trong regex thường đại diện cho ký tự bất kỳ** (trừ một số ký tự xuống dòng tùy chế độ). Muốn khớp dấu chấm thật, dùng `[.]` hoặc `\.`.

### Đặt cờ không phân biệt hoa/thường khi thực sự cần

~~~yaml
predicates:
  - name: Header
    args:
      header: X-Client-Channel
      regexp: '(?i)^(mobile|tablet)$'
~~~

Với `(?i)`, giá trị `mobile`, `MOBILE` và `Mobile` đều có thể khớp. **Không nên bật cờ này chỉ để “dễ khớp”** nếu hợp đồng header quy định giá trị phải đúng chữ thường; tính linh hoạt nên có chủ đích.

### Regex có dấu phẩy: ưu tiên cú pháp đầy đủ

Cú pháp ngắn phân tách tên predicate và các đối số bằng dấu phẩy, vì vậy pattern dài có **dấu phẩy**, ví dụ `^[a-z]{2,5}$`, có thể gây nhầm lẫn khi phân tích đối số.

~~~yaml
# Dễ hiểu và tránh mơ hồ khi regex có dấu phẩy:
predicates:
  - name: Header
    args:
      header: X-Region
      regexp: '^[a-z]{2,5}$'
~~~

Cú pháp đầy đủ cũng tránh việc phải nhớ các quy tắc escape riêng của shortcut. Nếu dùng cấu hình động qua Java DSL, hãy kiểm tra biểu thức regex sau cùng mà framework thật sự nhận, vì còn một tầng escape của chuỗi Java.

## 5. Quy tắc YAML và escaping regex

Một lỗi phổ biến là cho rằng chuỗi YAML, chuỗi Java và regex có cùng quy tắc escape. Chúng là những lớp khác nhau:

1. **YAML** đọc giá trị thuộc tính từ tệp cấu hình.
2. **Gateway** trích xuất hai tham số `header` và `regexp` rồi tạo predicate.
3. **Java regex** diễn giải biểu thức khi so khớp giá trị header.

Với pattern chứa dấu gạch chéo ngược, nên đặt regex trong **dấu nháy đơn YAML**:

~~~yaml
predicates:
  - name: Header
    args:
      header: X-Batch-Id
      regexp: '^\d{4}-[A-Z]{2}$'
~~~

Pattern trên chấp nhận các giá trị như `2026-AB`. Trong nháy đơn YAML, ký tự `\` được giữ nguyên để Java regex xử lý. Nếu viết `regexp: "^\d{4}-[A-Z]{2}$"` trong YAML nháy kép, sequence `\d` có thể bị YAML coi là escape không hợp lệ. Bạn có thể dùng nháy kép với backslash được escape đúng, nhưng nháy đơn thường dễ đọc hơn.

Ví dụ cách dùng `[0-9]` tránh vấn đề escape hoàn toàn:

~~~yaml
regexp: '^[0-9]{4}-[A-Z]{2}$'
~~~

**Không đánh giá regex chỉ bằng mắt.** Hãy lập bảng giá trị hợp lệ/không hợp lệ, kiểm tra cả dấu cách, chữ hoa/thường, giá trị rỗng, dấu phẩy và dữ liệu dài bất thường.

## 6. Header name, header value và header lặp

HTTP header bao gồm **tên** và **giá trị**. Chúng có quy tắc khác nhau:

**Tên header:** Tên HTTP field là **không phân biệt chữ hoa/chữ thường**. Vì vậy `X-Client-Channel`, `x-client-channel` và `X-CLIENT-CHANNEL` cùng chỉ một trường header về mặt giao thức. Dùng một cách viết nhất quán trong tài liệu để dễ bảo trì.

**Giá trị header:** Không có quy tắc chung cho mọi header rằng giá trị luôn không phân biệt hoa/thường. Khi Header predicate dùng regex, Java regex mặc định so khớp phân biệt hoa/thường; có thể bật `(?i)` nếu hợp đồng cho phép.

**Khoảng trắng:** Proxy/framework có thể chuẩn hóa khoảng trắng tùy bối cảnh. Không giả định request header được truyền nguyên từng byte từ client đến ứng dụng. Với contract do bạn quản lý, quy định giá trị canonical và kiểm thử cụ thể.

**Header lặp:** HTTP cho phép biểu diễn nhiều giá trị ở một số trường; việc truyền, gộp hoặc tách bằng dấu phẩy phụ thuộc loại header và hạ tầng. Khi ứng dụng nhận nhiều giá trị, cần xét cách Gateway đánh giá từng giá trị và cách proxy trước đó có thể đã gộp chúng. Đừng giả định chuỗi `X-Client-Channel: mobile,tablet` sẽ được tự tách thành hai giá trị `mobile` và `tablet` để khớp regex `^(mobile|tablet)$`.

Để hạn chế mơ hồ, nếu bạn thiết kế header cho định tuyến, hãy ưu tiên **một giá trị xác định duy nhất** theo contract, ví dụ `X-Client-Channel: mobile`, và xác định hành vi khi client gửi nhiều giá trị trái quy định.

### Một số giá trị đặc biệt

| Header trong request | Với regex `^mobile$` | Nhận xét |
| --- | --- | --- |
| `X-Client-Channel: mobile` | Khớp | Chuỗi đúng |
| `x-client-channel: mobile` | Khớp | Tên header khác kiểu chữ |
| `X-Client-Channel: MOBILE` | Không | Giá trị khác kiểu chữ |
| `X-Client-Channel: mobile-beta` | Không | Giá trị có hậu tố |
| `X-Client-Channel: mobile,tablet` | Không nếu ứng dụng nhận một chuỗi như vậy | Không tự suy ra việc tách danh sách |
| Header không xuất hiện | Không | Thiếu điều kiện cần |

Nếu cần route theo `Content-Type` hoặc `Accept`, lưu ý các header này có cú pháp riêng gồm media type, tham số, nhiều giá trị và mức ưu tiên. Một regex quá đơn giản có thể không phù hợp với nội dung hợp lệ như `application/json; charset=utf-8` hoặc nhiều media type trong `Accept`. Hãy cân nhắc những predicate/chính sách phù hợp hơn thay vì tự tái triển khai parser giao thức bằng regex.

## 7. Kết hợp Header với các predicate khác

Một route có nhiều predicate thường yêu cầu **tất cả predicate của route cùng đúng** (logic AND).

~~~yaml
spring:
  cloud:
    gateway:
      server:
        webflux:
          routes:
            - id: mobile-orders
              uri: lb://orders-service
              predicates:
                - Path=/api/orders/**
                - Method=GET
                - Header=X-Client-Channel, ^mobile$
                - Header=X-Api-Version, ^v2$
              filters:
                - StripPrefix=1
~~~

Điều kiện route là:

~~~text
Path khớp /api/orders/**
AND Method = GET
AND X-Client-Channel khớp ^mobile$
AND X-Api-Version khớp ^v2$
~~~

Ví dụ:

| Method/path | X-Client-Channel | X-Api-Version | Kết quả với route mobile-orders |
| --- | --- | --- | --- |
| GET /api/orders/17 | mobile | v2 | Khớp |
| GET /api/orders/17 | web | v2 | Không khớp |
| GET /api/orders/17 | mobile | v1 | Không khớp |
| POST /api/orders/17 | mobile | v2 | Không khớp |
| GET /api/catalog/17 | mobile | v2 | Không khớp |
| GET /api/orders/17 | *không có* | v2 | Không khớp |

Hai dòng `Header=` trong **cùng một route** là hai điều kiện bắt buộc. Nếu muốn **hoặc mobile hoặc web**, có thể viết một regex kết hợp `^(mobile|web)$` hoặc định nghĩa hai route rõ ràng nếu backend và filter khác nhau.

### Khi nào nên dùng Header thay vì predicate khác?

| Điều kiện | Predicate phù hợp | Ví dụ |
| --- | --- | --- |
| Đường dẫn API | `Path` | `/api/orders/**` |
| Phương thức HTTP | `Method` | `GET`, `POST` |
| Hostname | `Host` | `api.example.com` |
| Query parameter | `Query` | `?source=mobile` |
| HTTP request header | `Header` | `X-Client-Channel: mobile` |
| Cookie | `Cookie` | Cookie có tên/giá trị theo contract |

Tên route, predicate và filter không phải cơ chế phân quyền. Ví dụ, kiểm tra `X-Role: admin` bằng Header predicate **không chứng minh** người gửi thực sự là quản trị viên.

## 8. Chọn route chuyên biệt và route mặc định

Một tình huống rất thường gặp: một nhóm client có backend riêng, nhưng các client còn lại vẫn phải truy cập được API mặc định. Cần cấu hình **route cụ thể trước** và route mặc định có thứ tự ưu tiên thấp hơn.

~~~yaml
spring:
  cloud:
    gateway:
      server:
        webflux:
          routes:
            - id: catalog-mobile
              order: -10
              uri: lb://catalog-mobile-service
              predicates:
                - Path=/api/catalog/**
                - Method=GET
                - Header=X-Client-Channel, ^mobile$
              filters:
                - StripPrefix=2

            - id: catalog-default
              order: 0
              uri: lb://catalog-service
              predicates:
                - Path=/api/catalog/**
                - Method=GET
              filters:
                - StripPrefix=2
~~~

**Vì sao có `order`?** Request mobile cũng thỏa `Path` và `Method` của route mặc định. Trong Spring Cloud Gateway, route có **order nhỏ hơn** thường được ưu tiên khi nhiều route cùng khớp. Đặt `catalog-mobile` ở `-10` và route mặc định ở `0` giúp yêu cầu chuyên biệt được chọn trước. Thứ tự **route** và thứ tự **GatewayFilter** là hai cơ chế khác nhau.

~~~mermaid
flowchart TD
    A[GET /api/catalog/products] --> B{Header X-Client-Channel = mobile?}
    B -->|Có| C[Route catalog-mobile, order -10]
    B -->|Không hoặc thiếu| D[Route catalog-default, order 0]
    C --> E[Catalog mobile service]
    D --> F[Catalog service]
~~~

Với `lb://`, Gateway cần cấu hình Spring Cloud LoadBalancer và nguồn phân giải instance phù hợp (service discovery hoặc định nghĩa instance). Nếu chưa có discovery trong môi trường học tập, thay bằng URI `http://localhost:9001` và `http://localhost:9002` với hai backend thử nghiệm.

### Tránh dựa vào thứ tự khai báo trong YAML

Khi có nhiều route chồng lấn, hãy xác định rõ **order** thay vì chỉ hy vọng route viết trên sẽ thắng. Trong hệ thống có route động hoặc cấu hình ghép từ nhiều nguồn, thứ tự vật lý trong tệp không phải cách diễn tả ưu tiên dễ kiểm chứng.

Nếu một route khớp nhưng upstream trả 404 hoặc 503, Gateway **không tự động quay lại thử route có mức ưu tiên thấp hơn** như `catalog-default`; việc fallback sang backend khác phải được thiết kế tường minh theo nhu cầu nghiệp vụ và độ tin cậy.

## 9. Kiểm tra bằng curl và ma trận tình huống

Giả sử gateway đang chạy ở `localhost:8080` và có hai backend hoạt động theo cấu hình ở phần trước. Dùng cùng path, chỉ thay giá trị header:

~~~bash
# Route mobile:
curl -i -H 'X-Client-Channel: mobile' \
  http://localhost:8080/api/catalog/products/42

# Route mặc định (không có header):
curl -i http://localhost:8080/api/catalog/products/42

# Route mặc định (giá trị không khớp):
curl -i -H 'X-Client-Channel: web' \
  http://localhost:8080/api/catalog/products/42

# Route mặc định vì regex phân biệt chữ hoa/thường:
curl -i -H 'X-Client-Channel: MOBILE' \
  http://localhost:8080/api/catalog/products/42

# Vẫn khớp route mobile dù tên header viết chữ thường:
curl -i -H 'x-client-channel: mobile' \
  http://localhost:8080/api/catalog/products/42
~~~

**Kết quả route mong đợi** với ví dụ `^mobile$`:

| Request | Route được chọn | Lý do |
| --- | --- | --- |
| GET, `X-Client-Channel: mobile` | `catalog-mobile` | Header khớp và route có order cao hơn |
| GET, không có X-Client-Channel | `catalog-default` | Header predicate chuyên biệt không khớp |
| GET, `X-Client-Channel: web` | `catalog-default` | Không khớp `^mobile$` |
| GET, `X-Client-Channel: MOBILE` | `catalog-default` | Giá trị phân biệt hoa/thường |
| GET, `x-client-channel: mobile` | `catalog-mobile` | Tên header không phân biệt hoa/thường |
| POST /api/catalog/products/42 | Không thuộc hai route ví dụ | Cả hai route yêu cầu GET |

Các câu lệnh chỉ **thử cấu hình**, chưa được chạy trong bài. Mã HTTP thực tế do backend, security, filter và route khác quyết định. Nếu muốn chứng minh route nào đã được chọn, đặt response body/header nhận diện riêng ở **backend thử nghiệm** hoặc kiểm tra route ID qua telemetry của Gateway; đừng suy luận chỉ từ mã `200`.

### Kiểm tra riêng các trường hợp biên

1. Gửi header không có giá trị, ví dụ `X-Client-Channel:`, rồi xác định hành vi mong đợi.
2. Thử giá trị có khoảng trắng, dấu phẩy, chữ hoa và chuỗi rất dài.
3. Thử hai dòng header cùng tên nếu client/proxy cho phép và ghi nhận gateway thực sự nhận giá trị gì.
4. Thử request qua ingress/load balancer thật, không chỉ kết nối trực tiếp gateway tại localhost.
5. Thử request không có route nào khớp để phân biệt **predicate không khớp** với **upstream trả lỗi**.

## 10. Header predicate và vấn đề bảo mật

**Route predicate không phải một cơ chế xác thực hay phân quyền.** Nếu client tự chọn `X-Client-Channel: mobile`, client có thể chủ động đi vào route mobile. Điều này hợp lý khi header chỉ là thông tin chọn representation hoặc backend tương đương, nhưng có thể trở thành lỗ hổng nếu route mobile có quyền truy cập nhiều hơn.

Ví dụ cấu hình **không an toàn**:

~~~yaml
# Không dùng header do client tự đặt để chứng minh vai trò bảo mật:
predicates:
  - Header=X-User-Role, ^admin$
~~~

Bất cứ client nào có thể gửi giá trị `X-User-Role: admin` đều có thể làm điều kiện route trên khớp, trừ khi một tầng đáng tin cậy đã loại bỏ/kiểm soát giá trị. Dù vậy, tầng nghiệp vụ vẫn phải **kiểm tra quyền trên tài nguyên**. Không dùng điều kiện route để quyết định ai được xem đơn hàng, thay đổi thông tin thanh toán hay truy cập dữ liệu nhạy cảm.

Những biện pháp cần thiết:

- **Xác thực token/session bằng cơ chế phù hợp** (ví dụ Spring Security) trước khi cho phép thực hiện hành động bảo vệ; phân quyền chi tiết vẫn được thực thi ở service chịu trách nhiệm.
- **Xác định nguồn tin cậy của header.** Nếu header nội bộ được thêm bởi ingress/gateway phía trước, tầng đó phải loại bỏ giá trị cùng tên từ bên ngoài trước khi chèn giá trị đã xác minh; ranh giới mạng giữa các tầng phải được bảo vệ.
- **Không tin các header danh tính tự khai** như `X-User-Id`, `X-User-Role` hoặc `X-Authenticated` do client gửi.
- **Giới hạn kích thước header** ở hạ tầng HTTP/proxy phù hợp; regex không thay thế kiểm soát dung lượng request.
- **Không ghi thông tin nhạy cảm** như `Authorization`, token, cookie hoặc giá trị có dữ liệu cá nhân vào log, metrics, trace và thông báo lỗi.
- **Chọn regex có hiệu năng dự đoán được.** Tránh biểu thức quá phức tạp với lượng lặp lồng nhau dễ dẫn tới backtracking tốn CPU khi client gửi chuỗi do họ kiểm soát.

### Điểm dễ nhầm về AddRequestHeader

~~~yaml
predicates:
  - Header=X-Trusted-Group, ^gold$
filters:
  - AddRequestHeader=X-Trusted-Group, gold
~~~

Cấu hình này **không làm route khớp một request ban đầu thiếu `X-Trusted-Group`**. Predicate được đánh giá để **chọn route**, còn `AddRequestHeader` là filter **của route đã chọn** và chỉ chạy sau đó. Muốn định tuyến theo nhóm tin cậy, hãy xác thực và gắn nhãn ở tầng **trước route selection**, hoặc dùng predicate/cơ chế xác thực được thiết kế riêng, thay vì dựa vào việc thêm header trong chính route.

## 11. Quan sát, chẩn đoán và lỗi cấu hình phổ biến

Khi request không đi vào route như mong đợi, cần phân biệt ba vấn đề: **Gateway không tìm thấy route khớp**, **Gateway đã chọn route khác**, hoặc **route đúng nhưng backend/filter xử lý lỗi**.

| Hiện tượng | Nguyên nhân thường gặp | Cách kiểm tra |
| --- | --- | --- |
| Header hiển thị đúng nhưng route không khớp | Regex đòi khớp toàn bộ, khác kiểu chữ hoặc có khoảng trắng | Đối chiếu giá trị thực tế và thử mẫu regex rõ ràng |
| Header tên khác kiểu chữ | Tên header là không phân biệt hoa/thường; nguyên nhân có thể nằm ở giá trị hoặc tầng proxy | Kiểm tra request Gateway nhận được |
| Request mobile đi vào route mặc định | Route mặc định có order ưu tiên hơn hoặc regex mobile không khớp | Xem `order`, các predicate và route ID thực tế |
| Thêm header ở GatewayFilter nhưng predicate vẫn false | Filter chạy sau route selection | Kiểm tra chuỗi xử lý; chuyển logic đặt header đến đúng tầng |
| Regex hợp lệ trong Java nhưng ứng dụng không nạp YAML | Escape trong YAML nháy kép, dấu phẩy shortcut, indentation hoặc namespace sai | Ưu tiên nháy đơn, cú pháp đầy đủ và kiểm tra cấu hình đã nạp |
| Header có dấu phẩy hoặc nhiều giá trị nhưng regex không khớp | Giá trị do HTTP stack/proxy đưa tới khác giả định | Gửi request kiểm thử và quan sát các giá trị tại điểm vào |
| Route đã khớp nhưng trả 404/503 | Backend sai path, không có instance, lỗi upstream hoặc filter | Kiểm tra URI, `StripPrefix`, discovery và health backend |
| Regex chậm hoặc tốn CPU bất thường | Pattern có nguy cơ catastrophic backtracking hoặc giá trị header rất dài | Đơn giản hóa regex, giới hạn kích thước và đo với dữ liệu xấu |
| Header từ client chọn được tuyến đặc quyền | Dùng header không tin cậy như bằng chứng quyền hạn | Chuyển kiểm tra quyền sang Spring Security/service nghiệp vụ |

**Dữ liệu quan sát hữu ích** gồm route ID, method, public path, HTTP status, latency, số request theo route, và trạng thái filter như rate limit/circuit breaker. Nếu bật Spring Boot Actuator và khả năng quan sát của Gateway, có thể dùng các endpoint quản trị phù hợp để xem route đã nạp hoặc metrics, tùy phiên bản; **giới hạn truy cập các endpoint quản trị**. Tránh dùng raw header values làm nhãn metric vì có thể tăng cardinality và làm lộ dữ liệu.

Không nên bật logging toàn bộ request header trong môi trường production chỉ để tìm lỗi predicate. Hãy ghi nhận có chọn đúng route hay không và những giá trị **đã được phân loại/an toàn** thay vì log token và thông tin cá nhân.

## 12. Tình huống thực tế: phân luồng API theo phiên bản client

Giả sử hệ thống có API báo cáo và đang thay đổi cấu trúc response giữa `v1` và `v2`. Client gửi một header hợp đồng `X-Api-Version` để yêu cầu phiên bản:

~~~yaml
spring:
  cloud:
    gateway:
      server:
        webflux:
          routes:
            - id: reports-v2
              order: -10
              uri: lb://reports-v2-service
              predicates:
                - Path=/api/reports/**
                - Header=X-Api-Version, ^v2$
              filters:
                - StripPrefix=2

            - id: reports-v1
              order: 0
              uri: lb://reports-v1-service
              predicates:
                - Path=/api/reports/**
              filters:
                - StripPrefix=2
~~~

Một client gọi:

~~~bash
curl -i -H 'X-Api-Version: v2' \
  http://localhost:8080/api/reports/summary
~~~

Gateway sẽ chọn `reports-v2` nếu request và cấu hình đáp ứng đúng điều kiện, rồi gửi `/summary` cho backend v2. Không có header hoặc header khác `v2` sẽ chọn route mặc định v1 theo ví dụ.

**Câu hỏi thiết kế:** Nếu client gửi `X-Api-Version: v999`, có nên tự hạ xuống v1 hay trả lỗi “phiên bản không hỗ trợ”? Route mặc định trong cấu hình trên cho phép fallback về v1, nhưng đây là **quyết định hợp đồng API**, không phải hành vi bắt buộc của `Header`. Khi sự khác biệt phiên bản có thể tạo rủi ro tương thích, hãy xác định chính sách từ chối rõ ràng thay vì âm thầm chuyển sang phiên bản khác.

Tương tự, nếu dùng header để phân luồng canary, việc khách hàng tự chọn tuyến có thể ảnh hưởng tính ổn định hoặc an toàn. Nhóm canary nên được xác định bởi cơ chế có nguồn tin cậy, được đo lường và có đường quay lui rõ ràng.

## 13. Bài thực hành và tiêu chí kiểm chứng

**Bối cảnh:** API `/api/products/**` có một backend chung và một backend dành riêng cho client mobile. Route chỉ áp dụng cho request GET. Client mobile dùng header `X-Client-Channel: mobile`.

### Phần A — Cấu hình

1. Tạo route `products-mobile` có `Path`, `Method=GET` và `Header=X-Client-Channel, ^mobile$`, ưu tiên `order: -10`.
2. Tạo route `products-default` chỉ cần `Path` và `Method=GET`, với `order: 0`.
3. Chỉ định hai URI backend khác nhau. Nếu dùng `lb://`, chuẩn bị LoadBalancer/discovery; nếu dùng HTTP tĩnh, bảo đảm backend đang nghe đúng cổng.
4. Thống nhất path mà backend nhận được; chỉ dùng `StripPrefix` nếu hợp đồng path cần biến đổi.

### Phần B — Kiểm thử theo bảng

| Request | Dự kiến |
| --- | --- |
| GET, `X-Client-Channel: mobile` | Chọn `products-mobile` |
| GET, header viết `x-client-channel: mobile` | Chọn `products-mobile` |
| GET, `X-Client-Channel: MOBILE` | Chọn `products-default` |
| GET, không có header | Chọn `products-default` |
| GET, `X-Client-Channel: web` | Chọn `products-default` |
| POST, `X-Client-Channel: mobile` | Không khớp hai route GET |
| GET, path ngoài `/api/products/**` | Không khớp hai route ví dụ |

### Phần C — Mở rộng và phân tích

1. Đổi regex thành `(?i)^mobile$` và dự đoán route cho giá trị `MOBILE`.
2. Bổ sung điều kiện `X-Api-Version: v2` cho route mobile; giải thích tại sao phải thỏa cả hai header.
3. Thử regex có quantifier như `^[a-z]{2,5}$` bằng cú pháp đầy đủ, xác nhận YAML nạp đúng.
4. Thêm một trường hợp header rỗng, header có dấu phẩy hoặc giá trị quá dài và xác định hành vi mong muốn.
5. Giả lập một backend trả 503: kiểm tra Gateway **không tự động chuyển sang route mặc định** chỉ vì backend của route chuyên biệt lỗi.
6. Tự trả lời: Nếu client khai `X-User-Role: admin`, vì sao không được dùng nó như bằng chứng để cấp quyền?

**Tiêu chí đạt:** Bạn chứng minh được route thực tế qua log/telemetry hoặc backend kiểm thử; phân biệt được tên header và giá trị header; giải thích đúng logic AND, regex, thứ tự route và sự khác nhau giữa route predicate với bảo mật. Một phản hồi HTTP 200 duy nhất không đủ để kết luận cấu hình đã chính xác.

## 14. Ghi nhớ

- **Header Route Predicate Factory** của Spring Cloud Gateway so khớp **request header** theo tên và Java regex. Request thiếu header thường không thỏa điều kiện tương ứng.
- **Tên header không phân biệt hoa/thường**; **giá trị thường được so khớp phân biệt hoa/thường**, trừ khi regex quy định khác. Chú ý ngữ nghĩa khớp **toàn bộ giá trị**.
- Dùng **YAML nháy đơn** cho regex chứa backslash và cân nhắc cú pháp **`name: Header` / `args`** khi pattern phức tạp hoặc có dấu phẩy.
- Trong một route, các predicate như `Path`, `Method` và `Header` kết hợp theo **AND**. Với route chuyên biệt và route mặc định, thiết lập `order` rõ ràng và kiểm tra route nào được chọn.
- **GatewayFilter chạy sau khi route được chọn**; thêm header trong filter của route không khiến Header predicate của chính route đó được đánh giá lại.
- **Header do client gửi có thể bị giả mạo**. Định tuyến theo header không thay thế xác thực, phân quyền, kiểm soát header tin cậy, giới hạn tài nguyên hay khả năng quan sát.
