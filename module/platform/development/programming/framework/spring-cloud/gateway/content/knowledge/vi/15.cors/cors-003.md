# Cấu hình CORS toàn cục cho Gateway Server WebFlux trong Spring Cloud Gateway

Một SPA chạy tại `https://app.example.test` thường gọi API tại `https://api.example.test`. Dù cả hai cùng thuộc một hệ thống, **trình duyệt coi chúng là hai origin khác nhau**. Nếu API Gateway không trả các header Cross-Origin Resource Sharing (**CORS**) phù hợp, trình duyệt có thể chặn JavaScript đọc response hoặc không gửi request thực tế sau khi kiểm tra preflight.

Trong **SPRING_CLOUD_GATEWAY**, bạn có thể đặt chính sách CORS **toàn cục** cho Gateway Server WebFlux thay vì lặp lại cấu hình ở từng route. Bài học thuộc chương **CORS**, giải thích cách dùng `spring.cloud.gateway.globalcors.cors-configurations`, xử lý preflight không match route bằng `add-to-simple-url-handler-mapping`, chọn origin/method/header an toàn, phối hợp Spring Security và kiểm chứng bằng HTTP request thực tế.

Gateway vẫn đảm nhiệm route predicate, filter chain, biến đổi path/header, service discovery và routing tới microservices. CORS là **chính sách cho trình duyệt**, không thay thế xác thực, phân quyền, giới hạn lưu lượng, circuit breaker, retry, TLS hoặc quan sát request.

> **Phạm vi phiên bản:** Cấu hình YAML dưới đây minh họa những dòng **Spring Cloud Gateway Server WebFlux** dùng namespace `spring.cloud.gateway.globalcors`, phổ biến ở Gateway 4.x. Các dòng phát hành hoặc biến thể **Server MVC** khác có thể dùng namespace và cách tích hợp khác. Hãy kiểm tra tài liệu chính thức cho đúng phiên bản Spring Boot, Spring Cloud và Gateway đang triển khai.

## 1. Hiểu đúng same-origin và CORS

**Origin** được xác định bởi bộ ba **scheme + hostname + port**. Path không tham gia xác định origin.

| Trang web gọi API | API được gọi | Cùng origin? |
|---|---|---|
| `https://app.example.test` | `https://app.example.test/api/orders` | Có |
| `https://app.example.test` | `https://api.example.test/orders` | Không — khác hostname |
| `http://localhost:3000` | `http://localhost:8080/api/orders` | Không — khác port |
| `http://app.example.test` | `https://app.example.test/api/orders` | Không — khác scheme |
| `https://app.example.test` | `https://app.example.test:8443/api/orders` | Không — khác port |

**Same-Origin Policy** hạn chế JavaScript trong trình duyệt truy cập một số response cross-origin, trừ khi server cho phép theo cơ chế CORS. Trình duyệt gửi header `Origin` để thông báo origin của trang đang yêu cầu.

~~~http
GET /api/orders/42 HTTP/1.1
Host: api.example.test
Origin: https://app.example.test
Accept: application/json
~~~

Nếu origin được cho phép, Gateway có thể trả:

~~~http
HTTP/1.1 200 OK
Access-Control-Allow-Origin: https://app.example.test
Vary: Origin
Content-Type: application/json
~~~

Khi có một origin hợp lệ và response được xử lý đúng, JavaScript ở `https://app.example.test` có thể đọc response theo các quy tắc CORS còn lại. Header `Vary` và các giá trị thực tế khác phụ thuộc xử lý framework/proxy; ví dụ chỉ minh họa.

**CORS không phải cơ chế chặn mọi client.** cURL, CLI, ứng dụng server-to-server hay client độc hại có thể gửi HTTP mà không tuân theo chính sách CORS của trình duyệt. Do đó **không dùng CORS như danh sách phân quyền API**, cũng không thay thế OAuth2/JWT, session security, IP policy hoặc kiểm soát dữ liệu nhạy cảm.

## 2. Request thường và preflight khác nhau ở đâu?

Trình duyệt có thể gửi một request cross-origin trực tiếp rồi kiểm tra header trong response, hoặc thực hiện **preflight** bằng HTTP `OPTIONS` trước khi gửi request thật. Việc có preflight hay không được quyết định bởi các quy tắc của Fetch/CORS: phương thức, request headers và content type, không phải đơn thuần cứ có cross-origin là sẽ có `OPTIONS`.

Ví dụ SPA muốn gửi JSON bằng `POST` có header `Authorization`:

~~~http
OPTIONS /api/orders HTTP/1.1
Host: api.example.test
Origin: https://app.example.test
Access-Control-Request-Method: POST
Access-Control-Request-Headers: authorization,content-type
~~~

Một response preflight hợp lệ có thể như sau:

~~~http
HTTP/1.1 200 OK
Access-Control-Allow-Origin: https://app.example.test
Access-Control-Allow-Methods: GET,POST,OPTIONS
Access-Control-Allow-Headers: Authorization,Content-Type,X-Request-Id
Access-Control-Max-Age: 1800
~~~

Mã status có thể là `200` hoặc một mã thành công khác tùy stack; **không lấy con số trong minh họa làm yêu cầu bắt buộc**. Sau khi preflight đạt, trình duyệt mới gửi POST thực tế theo quy tắc riêng của nó.

~~~mermaid
sequenceDiagram
    participant B as Browser tại app.example.test
    participant G as Gateway api.example.test
    participant S as Downstream orders
    B->>G: OPTIONS /api/orders + Origin + Access-Control-Request-Method
    G-->>B: Preflight CORS headers (nếu được phép)
    Note over B: Browser kiểm tra origin, method và request headers
    B->>G: POST /api/orders + Origin + Authorization + JSON
    G->>S: Route + GatewayFilter + downstream request
    S-->>G: Response
    G-->>B: Actual response + CORS headers
    Note over B: Browser kiểm tra CORS của actual response trước khi JS đọc
~~~

**Cần tách hai lượt:** preflight là một request HTTP `OPTIONS` độc lập, không phải body của POST. Trong nhiều cấu hình, Gateway xử lý preflight ở tầng CORS handler mà không forward nó xuống backend; còn POST thực tế đi qua route và filter chain bình thường.

Một request đơn giản như GET cross-origin vẫn cần `Access-Control-Allow-Origin` trên **response thật** để JavaScript đọc được dữ liệu. Chỉ làm preflight thành công là **chưa đủ**.

## 3. Cấu hình CORS toàn cục tối thiểu, có giới hạn rõ ràng

Giả định chỉ hai frontend sau được phép gọi Gateway:

- `https://app.example.test` — ứng dụng người dùng.
- `https://admin.example.test` — ứng dụng quản trị.

Một cấu hình minh họa cho Server WebFlux:

~~~yaml
spring:
  cloud:
    gateway:
      globalcors:
        cors-configurations:
          '[/**]':
            allowedOrigins:
              - https://app.example.test
              - https://admin.example.test
            allowedMethods:
              - GET
              - POST
              - PUT
              - DELETE
              - OPTIONS
            allowedHeaders:
              - Authorization
              - Content-Type
              - X-Request-Id
            exposedHeaders:
              - X-Request-Id
            allowCredentials: true
            maxAge: 1800
~~~

**Đọc các phần quan trọng:**

1. `globalcors` là nhóm cấu hình CORS áp dụng ở phạm vi Gateway handler mapping, không phải một phần tử `filters` của từng `RouteDefinition`.
2. `cors-configurations` ánh xạ **path pattern** đến chính sách `CorsConfiguration`. Khóa `'[/**]'` nghĩa là áp dụng cho các path phù hợp ở Gateway. Dấu ngoặc vuông phục vụ cơ chế binding map key của Spring Boot; cần giữ đúng cách biểu diễn được tài liệu phiên bản hướng dẫn.
3. `allowedOrigins` là **danh sách origin cụ thể**, gồm scheme và hostname (và port khi không mặc định). Không thêm path `/login` hoặc `/api` vào origin.
4. `allowedMethods` là những method mà frontend được phép dùng trong CORS; danh sách này **không tạo route** và **không cấp quyền truy cập business API**.
5. `allowedHeaders` là những request header mà preflight có thể đề nghị gửi.
6. `exposedHeaders` là những **response header** mà JavaScript được phép đọc ngoài các CORS-safelisted response headers.
7. `allowCredentials: true` cho phép phản hồi CORS biểu thị hỗ trợ credentialed requests theo quy tắc trình duyệt; chỉ nên dùng với các origin đã xác định và policy xác thực phù hợp.
8. `maxAge` được dùng để đưa thời gian cache kết quả preflight tính bằng **giây**, theo sự kiểm soát và giới hạn của trình duyệt.

Các giá trị `app.example.test`, `admin.example.test` chỉ để minh họa; cần thay bằng domain do tổ chức kiểm soát. Không được hiểu rằng đưa domain vào allowlist tự bảo đảm domain đó an toàn hoặc tất cả người dùng của nó được phép truy cập API.

### Tại sao khóa `'[/**]'` lại có dấu ngoặc vuông?

Trong cấu hình Gateway thường gặp:

~~~yaml
globalcors:
  cors-configurations:
    '[/**]':
      allowedOrigins:
        - https://app.example.test
~~~

Map key trên tương ứng với pattern `/**`. Cú pháp `[...]` giúp Spring Boot giữ nguyên ký tự đặc biệt của key khi bind sang map cấu hình. **Không nhầm `[/**]` với một đường dẫn HTTP thật** mà browser cần gọi.

Có thể dùng pattern phạm vi hẹp hơn khi phiên bản và yêu cầu cho phép, ví dụ chỉ một nhóm URL API; tuy nhiên chính sách “toàn cục” thường cần kiểm chứng cả các response lỗi, route không match và request preflight trước khi quyết định phạm vi.

## 4. `add-to-simple-url-handler-mapping`: preflight không match route

Một tình huống kinh điển:

~~~yaml
spring:
  cloud:
    gateway:
      routes:
        - id: orders
          uri: http://localhost:9090
          predicates:
            - Path=/api/orders/**
            - Method=POST
~~~

Browser gửi `OPTIONS /api/orders/42` để hỏi có được phép POST hay không. Route này có `Method=POST` nên **OPTIONS không khớp predicate**, khiến request có thể không được xử lý qua route handler mapping thông thường.

Ở các dòng Gateway Server WebFlux hỗ trợ, có thể thêm:

~~~yaml
spring:
  cloud:
    gateway:
      globalcors:
        add-to-simple-url-handler-mapping: true
        cors-configurations:
          '[/**]':
            allowedOrigins:
              - https://app.example.test
            allowedMethods:
              - POST
              - OPTIONS
            allowedHeaders:
              - Content-Type
              - Authorization
~~~

`add-to-simple-url-handler-mapping: true` cho phép cấu hình global CORS được gắn thêm vào **simple URL handler mapping** để xử lý các CORS request phù hợp **ngay cả khi request không match một Gateway route predicate**. Nó đặc biệt hữu ích với preflight `OPTIONS` khi route chỉ nhận `GET`, `POST` hoặc các method khác.

~~~mermaid
flowchart TD
    O["OPTIONS /api/orders/42 + Origin + preflight headers"] --> M{"Method=POST của Gateway route có khớp?"}
    M -->|Không| H{"Global CORS có được gắn với simple URL handler mapping?"}
    H -->|Không| N["Có thể bị xử lý bởi handler khác / 404 / lỗi CORS"]
    H -->|Có| C{"Origin, requested method, headers được phép?"}
    C -->|Có| A["Trả CORS preflight response"]
    C -->|Không| D["Không cấp phép CORS / có thể từ chối"]
    A --> B["Browser quyết định gửi POST thật"]
    B --> P["POST match route và đi downstream"]
~~~

**Thuộc tính trên không biến `OPTIONS` thành `POST`**, không tự tạo route cho API chưa tồn tại và không nới quyền của Spring Security. Một preflight có thể được trả lời ở tầng global CORS dù backend URL đích chưa sẵn sàng; request thật vẫn cần match route, được xác thực và kết nối downstream thành công.

### Các phản hồi không qua route

Một route-specific `GatewayFilter` có thể không chạy nếu một request không match route hoặc bị security layer từ chối sớm. Cấu hình global CORS và simple mapping giúp bao phủ thêm nhánh preflight liên quan, **không phải lời hứa rằng mọi response 401/403/404/5xx trong ứng dụng đều tự động có cùng tập CORS headers**. Phải kiểm thử từng loại response và kiểm tra thứ tự filter/handler mapping trong phiên bản đang sử dụng.

## 5. Hiểu từng thuộc tính CORS và nguy cơ cấu hình sai

| Thuộc tính | Mục đích | Lỗi hay gặp |
|---|---|---|
| `allowedOrigins` | Cho phép origin chính xác | Quên scheme/port; đưa cả path vào origin; cấp phép quá rộng |
| `allowedOriginPatterns` | Cho phép origin theo mẫu được hỗ trợ | Mẫu quá rộng, cho phép subdomain không được kiểm soát |
| `allowedMethods` | Khai báo method được phép trong CORS | Nhầm với routing predicate hoặc authorization |
| `allowedHeaders` | Những header client được đề nghị gửi ở preflight | Thiếu `Authorization` hoặc `Content-Type` khi frontend dùng JSON/JWT |
| `exposedHeaders` | Response headers JS có thể đọc | Nhầm với request headers được phép gửi |
| `allowCredentials` | Chính sách gửi credentials qua CORS | Bật credentials với wildcard origin không phù hợp |
| `maxAge` | Thời lượng cache preflight | Nhầm giây với mili giây, kỳ vọng mọi browser cache chính xác |
| `add-to-simple-url-handler-mapping` | Hỗ trợ global CORS ở simple URL mapping | Quên bật khi `OPTIONS` không match route predicate |

### `allowedHeaders` và `exposedHeaders` không giống nhau

Giả sử frontend gửi:

~~~http
Authorization: Bearer token-example
Content-Type: application/json
~~~

thì preflight hỏi browser có được gửi hai **request headers** này không. Chúng thuộc `allowedHeaders`. Ngược lại, nếu backend trả:

~~~http
X-Request-Id: request-42
~~~

và JavaScript cần đọc `response.headers.get("X-Request-Id")`, tên `X-Request-Id` phải nằm trong `exposedHeaders` (trừ khi header thuộc danh sách safelisted).

**Không dùng `exposedHeaders` để cho phép gửi `Authorization`**. Đó là hai chiều truyền khác nhau.

### Chính sách origin khác chính sách path

Cấu hình `cors-configurations.'[/**]'` áp dụng theo **path mà Gateway thấy**, không phải wildcard origin. `allowedOrigins` kiểm tra **Origin** như `https://app.example.test`. Muốn chỉ cho phép một API, cần thiết kế path pattern thích hợp và đồng thời kiểm tra các route đã cấu hình.

## 6. `allowCredentials`, wildcard và ranh giới tin cậy

Với những API sử dụng cookie/session hoặc các yêu cầu browser có credentials, `allowCredentials: true` khiến cấu hình CORS cần được đánh giá chặt chẽ.

**Không dùng cấu hình kiểu này:**

~~~yaml
globalcors:
  cors-configurations:
    '[/**]':
      allowedOrigins:
        - '*'
      allowCredentials: true
~~~

Trong Spring Framework, **wildcard `*` trong `allowedOrigins` không tương thích với `allowCredentials=true`**; việc validate cấu hình có thể gây lỗi. Đồng thời, xét về bảo mật, cấp phép credentials cho mọi origin là một chính sách nguy hiểm.

Cách rõ ràng nhất là allowlist origin cụ thể:

~~~yaml
globalcors:
  cors-configurations:
    '[/**]':
      allowedOrigins:
        - https://app.example.test
      allowCredentials: true
~~~

### Nếu thực sự cần origin patterns

Một số phiên bản Spring hỗ trợ `allowedOriginPatterns` để match origin theo mẫu, ví dụ:

~~~yaml
globalcors:
  cors-configurations:
    '[/**]':
      allowedOriginPatterns:
        - https://*.apps.example.test
      allowCredentials: true
~~~

Cách này có thể cho phép đáp ứng CORS bằng **origin cụ thể đã match** thay vì trả literal `*`. Nhưng wildcard subdomain làm tăng đáng kể phạm vi tin cậy: nếu một subdomain bị chiếm quyền, trình duyệt của người dùng có thể gửi yêu cầu cross-origin đến API dưới mẫu được phép.

Chỉ dùng patterns khi bạn **kiểm soát tất cả subdomain được match**, có chính sách cấp phát/thu hồi và đã xác minh behavior chính xác của phiên bản Spring Framework. Với API chứa thông tin nhạy cảm, allowlist domain cụ thể thường dễ kiểm soát hơn.

### CORS không thay thế CSRF protection

Nếu xác thực dựa trên **cookie**, việc cho phép cross-origin có credentials và việc chống **Cross-Site Request Forgery (CSRF)** là hai vấn đề riêng. Một request có thể vẫn được trình duyệt gửi đi trong các điều kiện nhất định dù JavaScript không đọc được response vì CORS. Cần xem xét `SameSite`, `Secure`, CSRF token, phân quyền và chính sách session tương ứng.

Không tắt CSRF một cách máy móc chỉ để “sửa lỗi CORS”. Với API stateless sử dụng Bearer token, cấu hình CSRF có thể khác API dùng cookie, nhưng quyết định phải dựa trên threat model, không dựa đơn thuần vào lỗi preflight.

## 7. CORS và Spring Security WebFlux

Trong Gateway tích hợp Spring Security, một lỗi phổ biến là **preflight nhận 401/403**. Browser gửi `OPTIONS` để kiểm tra quyền cross-origin, nhưng request preflight thường **không mang thông tin xác thực giống request thật**. Nếu security filter xử lý nó như POST/GET nghiệp vụ cần JWT trước khi CORS được giải quyết, browser có thể dừng ngay.

Một thứ tự logic cần đạt:

~~~mermaid
flowchart TD
    REQ["Browser preflight OPTIONS"] --> SEC["WebFlux / Spring Security filter chain"]
    SEC --> CO["CORS được kiểm tra bởi thành phần cấu hình phù hợp"]
    CO --> OK{"Origin, method, headers được chấp nhận?"}
    OK -->|Không| REJ["Không cấp phép CORS"]
    OK -->|Có| PREF["Hoàn tất preflight theo chính sách"]
    PREF --> REAL["Browser gửi request thật"]
    REAL --> AUTH["Xác thực và phân quyền request thật"]
    AUTH --> RT["Route predicates + GatewayFilters"]
    RT --> DOWN["Downstream microservice"]
~~~

Sơ đồ chỉ thể hiện **yêu cầu logic**; thứ tự triển khai chi tiết phụ thuộc cách cấu hình `SecurityWebFilterChain`, handler mappings và CORS processing trong runtime.

**Cách tiếp cận:**

1. Xác nhận Gateway đã bind đúng `globalcors` và policy khớp origin/method/headers.
2. Kiểm tra security có chặn `OPTIONS` trước khi CORS handler xử lý hay không.
3. Phối hợp cấu hình CORS với **Spring Security reactive** theo tài liệu đúng phiên bản; nếu chọn cho phép preflight đi qua authorization, phải giữ xác thực/phân quyền đầy đủ cho **request thật**.
4. Không mở toàn bộ `/**` thành `permitAll` chỉ để preflight thành công.
5. Test đủ request có và không có credentials, expired token, unauthorized resource và các response lỗi.

Không nên có **hai chính sách CORS khác nhau** cùng xử lý một request (ví dụ một policy ở SecurityWebFilterChain, một policy ở Gateway, một policy ở backend) mà thiếu quy ước ưu tiên. Những sự khác biệt có thể tạo response CORS mâu thuẫn, header lặp hoặc một số nhánh lỗi không mang header cần thiết.

## 8. Global CORS khác route metadata CORS và response header filters thế nào?

Spring Cloud Gateway có thể áp dụng CORS toàn cục hoặc, ở các dòng hỗ trợ, chính sách **CORS theo route** thông qua metadata/cấu hình. Lựa chọn nào phù hợp tùy có nhiều frontend với chính sách khác nhau không.

| Cách tiếp cận | Phạm vi | Tình huống thích hợp |
|---|---|---|
| **`globalcors`** | Chính sách theo path pattern ở handler mapping của Gateway | Phần lớn API cùng allowlist origin |
| **Route-specific CORS metadata** | Chính sách gắn một route theo khả năng phiên bản | Một nhóm API cần origin/method khác |
| **`SetResponseHeader` / `AddResponseHeader`** | Thay header sau khi route được chọn | Những response header bình thường, không thay thế quy trình CORS preflight |
| **`DedupeResponseHeader`** | Giảm header lặp theo chiến lược cấu hình | Gateway và downstream cùng sinh header CORS |
| **`CorsWebFilter` / security integration** | Tầng WebFlux bao trùm theo điều kiện cấu hình | Cần xử lý CORS ở tầng web/security ngoài phạm vi route |

**Tránh tự lắp CORS chỉ bằng `SetResponseHeader=Access-Control-Allow-Origin,*`.** CORS phải xét origin, preflight, requested method/headers, credentials, các request lỗi và response thật. Set một header tĩnh không thực hiện đầy đủ những kiểm tra này.

### Khi Gateway và downstream cùng trả CORS headers

Giả sử downstream tự trả `Access-Control-Allow-Origin`, trong khi global CORS của Gateway cũng tạo header ấy. Khi browser nhận **nhiều header Allow-Origin** hoặc một giá trị bị gộp không hợp lệ, browser có thể từ chối response dù cả hai tầng đều “cho phép”.

Giải pháp ưu tiên là **chỉ định một nơi sở hữu chính sách CORS**:

- Gateway quyết định CORS cho public browser API, còn downstream không đặt header CORS cho luồng đi qua Gateway; hoặc
- Hệ thống có phân quyền chính sách rõ ràng khác, nhưng phải kiểm tra response cuối.

Ở những phiên bản có `DedupeResponseHeader`, có thể dùng nó để giảm header lặp, ví dụ:

~~~yaml
spring:
  cloud:
    gateway:
      default-filters:
        - DedupeResponseHeader=Access-Control-Allow-Credentials Access-Control-Allow-Origin
~~~

Bộ lọc trên **chỉ xử lý trùng lặp**, không xác minh một origin có được phép hay không. Không dùng dedupe để che giấu hai cấu hình CORS đang xung đột. Cũng cần rà soát order thực tế, vì có trường hợp header được thêm ở tầng ngoài Gateway sau khi response rời filter chain.

## 9. CORS với route predicates, rewrite path và service discovery

Một route thực tế:

~~~yaml
spring:
  cloud:
    gateway:
      routes:
        - id: orders
          uri: lb://order-service
          predicates:
            - Path=/api/orders/**
            - Method=POST
          filters:
            - StripPrefix=1
            - SetRequestHeader=X-Edge-Service,orders
~~~

Với chính sách global CORS:

- Browser gửi preflight `OPTIONS /api/orders/42`, hỏi phép `POST` và header `Authorization`.
- Vì route có predicate `Method=POST`, preflight không nhất thiết match route. `add-to-simple-url-handler-mapping: true` có thể xử lý tình huống này ở tầng global CORS.
- Browser gửi POST thật; sau khi security policy chấp nhận, request match route `orders`, chạy `StripPrefix` và `SetRequestHeader` rồi chọn instance `order-service` bằng load balancer.
- Downstream nhận `POST /orders/42` nếu `StripPrefix=1` và không có filter khác đổi path; nó không cần biết origin browser để xác thực nghiệp vụ nếu Gateway/security contract đã xử lý.
- Response thực tế phải mang CORS headers thích hợp để browser được đọc.

**CORS không tự bảo đảm `lb://order-service` có instance, URI downstream an toàn, chứng chỉ TLS hợp lệ hoặc rate limiting hoạt động.** Nếu backend trả 503, chính sách CORS vẫn cần được kiểm tra để frontend đọc được error response khi phù hợp; nếu API không có route match, phải xử lý lỗi routing độc lập.

### URL nào được dùng để xét CORS path pattern?

Hãy phân biệt **path request đến Gateway** với path downstream sau `StripPrefix` hoặc `RewritePath`. Cấu hình `globalcors.cors-configurations` được áp dụng ở tầng xử lý **request đến Gateway**, vì vậy pattern cần khớp **public URL** theo handler mapping, không phải path sau filter.

Ví dụ frontend gọi `/api/orders/42`; nếu CORS pattern chỉ nhận `/orders/**`, đừng giả định nó được match nhờ `StripPrefix` chạy sau đó. Thực hiện phép thử preflight qua URL public để xác nhận.

## 10. Thiết kế cấu hình CORS theo môi trường

Một lỗi vận hành thường gặp là mang cấu hình phát triển kiểu `allowedOrigins: ['*']` vào production. Hãy quản lý các origin được phép như một phần chính sách triển khai, rà soát khi đổi frontend domain, port, CDN hoặc môi trường staging.

Ví dụ minh họa cho **development**, khi frontend chạy ở một địa chỉ cụ thể:

~~~yaml
spring:
  cloud:
    gateway:
      globalcors:
        add-to-simple-url-handler-mapping: true
        cors-configurations:
          '[/**]':
            allowedOrigins:
              - http://localhost:3000
            allowedMethods:
              - GET
              - POST
              - OPTIONS
            allowedHeaders:
              - Authorization
              - Content-Type
            maxAge: 600
~~~

Với production, thay origin bằng tên miền HTTPS do tổ chức kiểm soát; dùng `allowCredentials` nếu nghiệp vụ thực sự cần và đã xây dựng CSRF/session policy tương ứng. Một số frontend từ port 5173/4200 hoặc preview domain sẽ là **origin khác**; không mở wildcard toàn bộ chỉ vì muốn tiện kiểm thử.

Khi dùng externalized configuration của Spring Boot, các profile/environment overrides có thể thay thuộc tính CORS. Hãy xác nhận **cấu hình có hiệu lực ở instance thật**. Không tự suy rằng một tệp YAML đúng nghĩa là mọi Gateway node đã nạp cùng chính sách.

## 11. Thực hành: kiểm tra CORS bằng cURL và trình duyệt

Giả sử Gateway lắng nghe `http://localhost:8080`, frontend thử nghiệm có origin `http://localhost:3000`, backend test ở `http://localhost:9090`. Đặt cấu hình development ở mục 10 và route minh họa:

~~~yaml
spring:
  cloud:
    gateway:
      routes:
        - id: demo-orders
          uri: http://localhost:9090
          predicates:
            - Path=/api/orders/**
            - Method=POST
          filters:
            - StripPrefix=1
~~~

Backend giả định nhận `POST /orders/42`. Đây là môi trường demo; không tự hiểu endpoint đã tồn tại nếu chưa tạo mock/service thật.

### Bước 1 — Preflight được phép

~~~bash
curl -i -X OPTIONS "http://localhost:8080/api/orders/42" \
  -H "Origin: http://localhost:3000" \
  -H "Access-Control-Request-Method: POST" \
  -H "Access-Control-Request-Headers: authorization,content-type"
~~~

Trong môi trường dùng PowerShell nơi `curl` là alias, sử dụng `curl.exe` với cú pháp xuống dòng phù hợp shell. Trên Bash, dấu `\` ở cuối dòng như ví dụ nối lệnh.

Kết quả cần kiểm tra:

- Response là một **preflight response thành công** theo chính sách runtime.
- `Access-Control-Allow-Origin` cho phép `http://localhost:3000`.
- `Access-Control-Allow-Methods` và `Access-Control-Allow-Headers` chấp nhận POST và các header yêu cầu.
- Header khác như `Access-Control-Max-Age` hoặc `Vary` phù hợp cấu hình và hành vi framework.
- Không nhất thiết có request nào được gửi tới backend chỉ để trả preflight.

### Bước 2 — Origin không được phép

~~~bash
curl -i -X OPTIONS "http://localhost:8080/api/orders/42" \
  -H "Origin: http://localhost:9999" \
  -H "Access-Control-Request-Method: POST"
~~~

Không kỳ vọng response cấp phép `Access-Control-Allow-Origin: http://localhost:9999`. Server có thể trả `403` hoặc phản hồi khác theo handler mapping/CORS processing; **đánh giá chính sách qua header và hành vi browser**, không chỉ mã status.

### Bước 3 — Method hoặc request header không được phép

~~~bash
curl -i -X OPTIONS "http://localhost:8080/api/orders/42" \
  -H "Origin: http://localhost:3000" \
  -H "Access-Control-Request-Method: DELETE"

curl -i -X OPTIONS "http://localhost:8080/api/orders/42" \
  -H "Origin: http://localhost:3000" \
  -H "Access-Control-Request-Method: POST" \
  -H "Access-Control-Request-Headers: x-unapproved-header"
~~~

Theo cấu hình mục 10, `DELETE` và `X-Unapproved-Header` không được cấp phép. Kiểm tra việc Gateway không cho phép preflight tương ứng. **Lưu ý:** policy CORS từ chối DELETE không thay thế authorization nếu một HTTP client ngoài trình duyệt vẫn gửi DELETE trực tiếp.

### Bước 4 — Request thật

~~~bash
curl -i -X POST "http://localhost:8080/api/orders/42" \
  -H "Origin: http://localhost:3000" \
  -H "Content-Type: application/json" \
  -d '{"quantity":2}'
~~~

Nếu backend test nhận POST và trả response, response thực cần có CORS headers hợp lệ. Test thêm trạng thái backend 4xx/5xx để xem frontend có đọc được body lỗi hay không. Đừng dùng kết quả preflight thành công để suy đoán request thật sẽ trả 2xx.

### Bước 5 — Browser Fetch

Trong trang chạy ở `http://localhost:3000`, gọi:

~~~javascript
const response = await fetch("http://localhost:8080/api/orders/42", {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({ quantity: 2 }),
});
console.log(response.status, await response.text());
~~~

Mở Developer Tools, xem **Network** để đối chiếu request OPTIONS (nếu trình duyệt gửi), request POST thật, Origin và các `Access-Control-*` trong response. Nếu JavaScript báo “CORS error”, phải xem cả network request: lỗi có thể đến từ preflight, từ response thật thiếu CORS header, hoặc từ security/proxy xử lý trước route.

### Bước 6 — Test credentials khi chính sách cần

Chỉ khi đã cấu hình đúng allowlist origin, session/token model và `allowCredentials`, thử request theo chính sách credentials của frontend. Ví dụ với cookie session:

~~~javascript
const response = await fetch("https://api.example.test/api/profile", {
  credentials: "include",
});
console.log(response.status);
~~~

Ví dụ trên chỉ là cách gọi từ browser. Để chạy thực tế còn cần endpoint/profile, cookie được cấu hình hợp lệ (bao gồm `SameSite`/`Secure` khi cần), HTTPS và chính sách CSRF/session thích hợp. Không dùng cookie production trong môi trường demo.

### Bảng kết quả thực hành

| Test | Điều kiện | Dấu hiệu đúng |
|---|---|---|
| Preflight origin hợp lệ | `localhost:3000`, POST, headers được phép | CORS preflight chấp nhận |
| Preflight origin lạ | `localhost:9999` | Không cấp phép origin đó |
| Preflight method lạ | DELETE ngoài `allowedMethods` | Không cấp phép method đó |
| Preflight header lạ | `X-Unapproved-Header` | Không cấp phép header đó |
| POST thật | Origin hợp lệ, route POST tồn tại | Route/filter/backend hoạt động; response có CORS headers hợp lệ |
| Backend lỗi | Route match nhưng backend trả 5xx | Browser có thể đọc error response nếu chính sách CORS cho phép |
| Security từ chối | Token thiếu/hết hạn | HTTP 401/403 theo auth; kiểm tra CORS headers trên chính nhánh này |
| Không match route | Public URL khác pattern route | Có thể 404; phân biệt với lỗi chính sách CORS |

**Giới hạn của cURL:** nó không thực thi Same-Origin Policy và không tự chặn response nếu CORS sai. cURL hữu ích để xem HTTP headers, còn **trình duyệt mới kiểm chứng kết quả trải nghiệm người dùng web**.

## 12. Chẩn đoán sự cố CORS có hệ thống

| Hiện tượng | Nguyên nhân cần kiểm tra | Hướng xử lý |
|---|---|---|
| OPTIONS trả 404 khi route chỉ nhận POST | Predicate `Method=POST` không match OPTIONS | Cân nhắc `add-to-simple-url-handler-mapping: true` và test preflight |
| OPTIONS trả 401/403 | Security xử lý trước CORS hoặc chính sách từ chối request | Kiểm tra `SecurityWebFilterChain`, thứ tự CORS, origin/method/headers |
| GET trả 200 trong cURL nhưng browser báo CORS | Response thật thiếu header CORS phù hợp | Gửi kèm Origin khi test và xem browser Network |
| Frontend origin có port khác | Origin là scheme + host + port | Thêm đúng origin cần thiết; tránh wildcard production |
| Có `Access-Control-Allow-Origin` hai lần | Gateway và backend/proxy cùng tạo CORS header | Chỉ định owner, loại trùng có kiểm soát |
| `allowCredentials=true` kết hợp `allowedOrigins=*` | Cấu hình không hợp lệ/nguy hiểm | Dùng allowlist origin cụ thể hoặc pattern được kiểm soát |
| Đọc response header `X-Request-Id` bị `null` | Header không có hoặc chưa được expose | Kiểm tra response thật và `exposedHeaders` |
| Header `Authorization` bị chặn ở preflight | Thiếu trong `allowedHeaders` | Bổ sung header cần thiết sau khi rà soát policy |
| Browser vẫn không gửi cookie | Cookie `SameSite`/`Secure`, policy credentials hoặc HTTPS chưa phù hợp | Kiểm tra session/cookie, CSRF và browser DevTools |
| 404/503 từ downstream bị báo CORS chung chung | Nhánh lỗi thiếu CORS headers, route không match hoặc proxy override | So sánh status, route ID, handler mapping và headers cuối |
| Khác nhau giữa Gateway instances | Profile/cấu hình/restart/refresh khác nhau | Kiểm tra cấu hình thực tế, logs và rollout từng instance |
| CORS chạy local nhưng lỗi qua CDN/ingress | Proxy cache sai theo `Origin` hoặc ghi đè header | Kiểm tra `Vary`, cache key, response qua từng hop |

### Quy trình khoanh vùng năm câu hỏi

1. **Origin nào** thực sự xuất hiện trong request browser (scheme, host, port)?
2. **Browser gửi OPTIONS hay request trực tiếp**, và `Access-Control-Request-Method/Headers` là gì?
3. **Gateway handler nào xử lý**, request có match route không, security có chặn trước không?
4. **Response cuối** ở browser có đúng `Access-Control-Allow-Origin`, Allow-Methods/Headers/Credentials/Expose-Headers hay không?
5. **Proxy, CDN, default filters hoặc downstream** có thêm/xóa/gộp header CORS sau đó không?

Dùng log và tracing vừa đủ: ghi origin được yêu cầu, route ID, trạng thái preflight/request thật và nguyên nhân policy từ chối; **không ghi access token/cookie nguyên văn** để debug.

## 13. Checklist triển khai an toàn

- [ ] Tôi phân biệt **origin** với domain/path và hiểu scheme/host/port đều quan trọng.
- [ ] Tôi biết preflight `OPTIONS` khác request thật và không phải mọi request cross-origin đều có preflight.
- [ ] Tôi đã cấu hình `spring.cloud.gateway.globalcors.cors-configurations` đúng namespace của Gateway Server WebFlux.
- [ ] Tôi hiểu map key `'[/**]'` biểu diễn path pattern public được kiểm tra.
- [ ] Tôi dùng `allowedOrigins` cụ thể cho production và đã xem xét `allowedOriginPatterns` nếu cần.
- [ ] Tôi không kết hợp `allowCredentials: true` với `allowedOrigins: ['*']`.
- [ ] Tôi phân biệt `allowedHeaders` (request) với `exposedHeaders` (response).
- [ ] Tôi đã quyết định `maxAge` theo nhu cầu và kiểm thử thay đổi policy trên browser thật.
- [ ] Tôi đã kiểm tra `add-to-simple-url-handler-mapping` khi OPTIONS không match Method predicate.
- [ ] Tôi đã phối hợp CORS với Spring Security WebFlux mà không nới quyền request nghiệp vụ.
- [ ] Tôi không xem CORS như authentication, authorization hoặc CSRF protection.
- [ ] Tôi đã thống nhất chủ sở hữu CORS giữa Gateway, downstream, ingress và CDN.
- [ ] Tôi đã thử origin hợp lệ/bị từ chối, method/header hợp lệ/bị từ chối, preflight và request thật.
- [ ] Tôi đã thử 401/403/404/429/503 khi chúng có thể phát sinh trong kiến trúc.
- [ ] Tôi đã kiểm tra cookie, `credentials`, `SameSite`, `Secure` và TLS nếu API dùng session.
- [ ] Tôi vẫn kiểm soát route predicates, rate limiting, retry/circuit breaker, TLS và metrics/tracing như những chính sách độc lập.
- [ ] Tôi đã xác nhận tất cả Gateway instance dùng cùng policy khi triển khai nhiều node.

## Tài liệu tham khảo chính thức

- [Spring Cloud Gateway Reference](https://docs.spring.io/spring-cloud-gateway/reference/) — tìm mục **CORS Configuration** của đúng **Gateway Server WebFlux** và phiên bản, gồm `globalcors` và `add-to-simple-url-handler-mapping`.
- [Spring Framework — CORS](https://docs.spring.io/spring-framework/reference/web/webflux-cors.html) — cách WebFlux xử lý CORS, `CorsConfiguration` và các trường policy.
- [Spring Security — CORS](https://docs.spring.io/spring-security/reference/reactive/integrations/cors.html) — tích hợp CORS với bảo mật reactive, đặc biệt preflight.
- [MDN — Cross-Origin Resource Sharing](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/CORS) — request/response CORS, preflight, credentials và lỗi ở trình duyệt.
- [Spring Boot Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html) — binding YAML, profile và cấu hình theo môi trường.

**Ghi nhớ:** Cấu hình CORS toàn cục trong Gateway Server WebFlux cần **chỉ rõ origin, method, request headers, credentials và phạm vi path**, đồng thời xử lý đúng **preflight OPTIONS không match route** khi cần. Một chính sách đúng chỉ được xác nhận khi **browser đọc được response thật** và các request không được phép vẫn bị từ chối đúng quy tắc; CORS không thay thế xác thực, phân quyền hoặc bảo vệ dữ liệu tại microservices.
