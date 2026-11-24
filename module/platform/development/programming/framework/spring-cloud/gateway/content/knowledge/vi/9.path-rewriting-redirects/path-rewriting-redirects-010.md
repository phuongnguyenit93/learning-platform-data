# Giữ query string, dấu gạch chéo và ký tự mã hóa khi đổi đường dẫn

## 1. Vì sao đổi đường dẫn dễ làm hỏng request?

Trong hệ thống microservices, client thường truy cập một đường dẫn công khai như `/api/v1/catalog/products/42`, trong khi service phía sau chỉ xử lý `/products/42`. **Spring Cloud Gateway** hỗ trợ `RewritePath`, `StripPrefix`, `SetPath` và `PrefixPath` để chuyển đổi đường dẫn trước khi proxy request. Chúng giúp giữ API công khai ổn định ngay cả khi cấu trúc service nội bộ thay đổi.

Tuy nhiên, URL còn chứa query string và các ký tự được percent-encode. Xét request:

~~~http
GET /api/v1/items/blue%20shirt?tag=a%2Fb&tag=c&sort=desc HTTP/1.1
Host: api.example.test
~~~

Nếu chỉ muốn bỏ tiền tố `/api/v1`, backend nên nhận **raw path** `/items/blue%20shirt` và **raw query** `tag=a%2Fb&tag=c&sort=desc`. Một cách viết lại URL không phù hợp có thể:

- Xóa toàn bộ `?tag=...` khi thay path.
- Đổi `a%2Fb` thành `a/b`, làm thay đổi cách hiểu giá trị.
- Đổi `blue%20shirt` thành `blue%2520shirt` do mã hóa ký tự `%` thêm một lần.
- Làm mất dấu `/` cuối path, hoặc tạo `//items` ngoài ý muốn.
- Gom tham số query lặp thành một giá trị duy nhất khi parse rồi dựng lại URL.

Bài học thuộc chương **Đường dẫn và chuyển hướng** của **Spring Cloud Gateway** này tập trung vào cách **đổi riêng path và giữ nguyên phần còn lại theo hợp đồng API**. Các ví dụ dùng **Gateway Server WebFlux**; với Server Web MVC hoặc các dòng phiên bản khác cần đối chiếu API và namespace cấu hình tương ứng.

Sau bài học, bạn có thể:

1. Phân biệt raw path, decoded path, query string và percent-encoding.
2. Cấu hình `RewritePath`, `StripPrefix`, `SetPath` mà không chủ động làm mất query.
3. Giải thích sự khác nhau giữa slash thật `/` và encoded slash `%2F`.
4. Xử lý rõ root path, trailing slash, slash trùng và query parameter lặp.
5. Phân biệt path rewrite nội bộ với redirect 3xx.
6. Kiểm tra request backend thực nhận và phòng tránh sai lệch giải mã giữa Gateway, proxy và service.

## 2. Path, query và fragment là các thành phần khác nhau

Một URI truy cập HTTP có thể được phân tích như sau:

~~~text
https://api.example.test:8443/api/v1/items/blue%20shirt?tag=a%2Fb&tag=c#section
|scheme|------ authority -------|-------- raw path ------|--- raw query ---|
~~~

| Thành phần | Giá trị minh họa | Công dụng |
| --- | --- | --- |
| Scheme | `https` | Giao thức |
| Authority | `api.example.test:8443` | Host và cổng |
| Raw path | `/api/v1/items/blue%20shirt` | Đường dẫn có thể còn percent escape |
| Raw query | `tag=a%2Fb&tag=c` | Phần sau dấu `?` |
| Fragment | `section` | Phần sau `#`, xử lý phía client; không có trong HTTP request-target thông thường |

**Path** thường được dùng để định tuyến đến tài nguyên hoặc handler. **Query** là thành phần độc lập, thường biểu diễn điều kiện lọc, tìm kiếm, phân trang hoặc tùy chọn trả dữ liệu. Quy tắc thay path không cần hiểu ý nghĩa của query nếu không có yêu cầu thay query.

~~~text
/api/v1/items/42
/api/v1/items/42?lang=vi
/api/v1/items/42?lang=en&tag=hot&tag=new
~~~

Cả ba request đều có thể chuyển path tới `/items/42` và giữ nguyên query của từng request. Quan trọng là không ghép lại toàn URL từ một map tham số, vì map đơn giản có thể làm mất giá trị `tag` thứ hai.

### Raw path khác decoded path

| Raw path | Sau một lần giải mã phù hợp | Lưu ý |
| --- | --- | --- |
| `/items/blue%20shirt` | `/items/blue shirt` | Dấu cách cần mã hóa khi đi trong URI |
| `/items/a%2Fb` | `/items/a/b` | Slash được mã hóa có thể đổi ranh giới segment |
| `/items/a%252Fb` | `/items/a%2Fb` | Giải mã thêm lần nữa có thể tạo slash |
| `/items/price%2Btax` | `/items/price+tax` | Dấu cộng trong path không tự động là dấu cách |
| `/items/%C3%A1o` | `/items/áo` với UTF-8 | Chữ có dấu được mã hóa thành nhiều byte |

**Không phải mọi HTTP stack đều chấp nhận encoded slash `%2F`.** Proxy, container hoặc ứng dụng có thể từ chối, giữ nguyên hoặc giải mã nó theo chính sách riêng. Khi thiết kế route và phân quyền, cần thống nhất cách xử lý ở toàn hệ thống; không thể chỉ dựa vào cách một lớp nhìn raw path.

## 3. Path rewrite nằm ở đâu trong pipeline của Gateway?

Spring Cloud Gateway xác định route bằng **route predicate**, ví dụ `Path`, `Method`, `Host` hoặc `Header`. Sau khi route phù hợp được chọn, `FilteringWebHandler` chạy các gateway filter có liên quan, bao gồm filter biến đổi path và filter dùng để định tuyến đến upstream.

~~~mermaid
flowchart TD
    A[Client: /api/v1/items/42?lang=vi] --> B[RoutePredicateHandlerMapping]
    B -->|Route phù hợp| C[FilteringWebHandler]
    C --> D[RewritePath hoặc StripPrefix]
    D --> E[Raw path mới: /items/42]
    E --> F[HTTP routing tới upstream]
    F --> G[Backend: /items/42?lang=vi]
    G --> H[Response về client]
~~~

Một filter chuyên dụng như `RewritePath` thay đổi phần path của request và cập nhật dữ liệu cần thiết cho định tuyến. Các routing filter phía sau sử dụng thông tin trong `ServerWebExchange`, bao gồm URL đích được chuẩn bị qua các exchange attribute, chẳng hạn `GATEWAY_REQUEST_URL_ATTR`.

Ba nguyên tắc:

1. **Predicate chọn route trước filter của chính route đó.** Nếu `Path` không khớp request đầu vào, `RewritePath` của route đó không chạy.
2. **Chỉ thay đổi thành phần cần thiết.** Khi bài toán chỉ là bỏ prefix của path, hãy thay path thay vì nối lại toàn bộ scheme, authority và query.
3. **Kiểm tra ở backend.** Gateway có thể biến đổi path đúng nhưng proxy ở phía trước/sau hoặc framework backend vẫn có thể chuẩn hóa đường dẫn khác nhau.

## 4. RewritePath với query string được giữ nguyên

`RewritePath` nhận một regex và một replacement. Ví dụ route trên **Spring Cloud Gateway Server WebFlux**:

~~~yaml
spring:
  cloud:
    gateway:
      server:
        webflux:
          routes:
            - id: catalog-v1
              uri: http://localhost:9001
              predicates:
                - Path=/api/v1/**
              filters:
                - RewritePath=^/api/v1(?<suffix>/.*)$, $\{suffix}
~~~

Ý nghĩa:

- `Path=/api/v1/**` lọc các request thuộc nhánh công khai.
- Regex `^/api/v1(?<suffix>/.*)$` lấy suffix có **dấu slash đầu tiên** sau tiền tố `/api/v1`.
- Replacement `$\{suffix}` dùng nhóm bắt làm path mới. Khi dùng YAML với Gateway, dấu backslash trước ngoặc nhọn giúp xử lý cú pháp placeholder của Spring; cần kiểm tra với phiên bản đang chạy.
- `uri` là địa chỉ backend thử nghiệm. Cần chạy backend ở `localhost:9001` mới có thể quan sát response.

Giả sử request đã đi qua Gateway và không có thành phần nào khác chủ động viết lại URL, kết quả mong đợi là:

| Request tới Gateway | Raw path backend | Raw query dự kiến |
| --- | --- | --- |
| `/api/v1/items/42` | `/items/42` | Không có |
| `/api/v1/items/42?lang=vi` | `/items/42` | `lang=vi` |
| `/api/v1/items/42?tag=a&tag=b` | `/items/42` | `tag=a&tag=b` |
| `/api/v1/items/blue%20shirt?q=a%2Bb` | `/items/blue%20shirt` | `q=a%2Bb` |
| `/api/v1/?page=2` | `/` | `page=2` |
| `/api/v1/items/a%2Fb?x=1` | Phụ thuộc cách HTTP stack xử lý encoded slash | `x=1` nếu request được chấp nhận |

**Vì sao query thường không đổi?** Khi filter chỉ mutate path, phần query của URI không cần được parse hoặc tái tạo. Query có thể tiếp tục đi cùng request tới upstream. Đây vẫn là **hành vi cần kiểm chứng trong toàn stack** khi có ingress, proxy, custom filter hoặc filter thêm query parameter.

### Phân tích named capture group

~~~text
Regex:       ^/api/v1(?<suffix>/.*)$
Raw path:    /api/v1/items/42
suffix:      /items/42
Kết quả:     /items/42
~~~

Regex này **không khớp `/api/v1` nếu không có slash ở cuối**. Nếu API cần hỗ trợ cả `/api/v1` và `/api/v1/`, hãy thiết kế thêm trường hợp root thay vì giả định framework tự nối slash.

**Lưu ý phiên bản:** Cấu trúc `spring.cloud.gateway.server.webflux.routes` dùng ở một số dòng Spring Cloud Gateway Server WebFlux mới; những phiên bản khác sử dụng `spring.cloud.gateway.routes`. Hãy dùng đúng namespace và starter tương thích với ứng dụng, đồng thời phân biệt Gateway Server WebFlux với Server Web MVC.

## 5. StripPrefix, SetPath và PrefixPath có gì khác?

Không phải thao tác đổi đường dẫn nào cũng cần regex. Chọn filter đơn giản nhất thể hiện hợp đồng API:

| Filter | Mục tiêu | Ví dụ |
| --- | --- | --- |
| `StripPrefix=2` | Bỏ hai segment đầu | `/api/v1/items/42` → `/items/42` |
| `PrefixPath=/internal` | Thêm tiền tố path | `/items/42` → `/internal/items/42` |
| `SetPath=/products/{id}` | Dựng path từ template đã match | `/api/v1/items/42` → `/products/42` |
| `RewritePath` | Áp dụng regex và replacement | `/api/v1/items/42` → `/items/42` |

### Dùng StripPrefix khi prefix cố định

~~~yaml
predicates:
  - Path=/api/v1/**
filters:
  - StripPrefix=2
~~~

`StripPrefix=2` bỏ `api` và `v1` trước khi chuyển tiếp. Cách này ngắn và dễ đọc; nhưng vẫn phải kiểm tra số segment với đường dẫn gốc, slash thừa và dạng path được mã hóa, vì đường đi qua các URI parser có thể ảnh hưởng cách đếm segment.

### Dùng SetPath khi predicate cung cấp biến URI

~~~yaml
predicates:
  - Path=/api/v1/items/{id}
filters:
  - SetPath=/products/{id}
~~~

`Path` thu thập biến `id` rồi `SetPath` đặt biến vào path đích. Cách này phù hợp với một template rõ ràng. Nếu `id` có percent-encoding hoặc slash mã hóa, hãy kiểm tra cách route pattern và template expansion xử lý giá trị; không mặc định rằng kết quả giữ nguyên mọi byte như thao tác trên raw path.

### Dùng PrefixPath cho backend có context path khác

~~~yaml
predicates:
  - Path=/assets/**
filters:
  - PrefixPath=/internal
~~~

`/assets/logo.svg` được chuyển thành `/internal/assets/logo.svg`. Khi phối hợp nhiều filter, thứ tự xử lý ảnh hưởng path cuối. Không đặt nhiều `StripPrefix` hoặc `RewritePath` nếu không rõ mỗi bước được áp vào path nào.

## 6. Giữ query parameter lặp và biểu diễn raw query

Khi chỉ thay path, không nên vô tình sửa query:

~~~text
Input : /api/v1/items/42?tag=a&tag=b&search=a%2Bb&empty=&flag
Output: /items/42?tag=a&tag=b&search=a%2Bb&empty=&flag
~~~

Những chi tiết có thể quan trọng:

- **Tên lặp:** `tag=a&tag=b` không tương đương map chỉ còn `tag=b`.
- **Giá trị trống:** `empty=` và `flag` có cách biểu diễn khác; không nên tự ý chuẩn hóa khi không được yêu cầu.
- **Thứ tự:** nhiều API coi thứ tự query parameter không quan trọng, nhưng hệ thống ký URL hoặc cache có thể dựa trên dạng canonical.
- **Mã hóa:** `search=a%2Bb` và `search=a+b` có thể không mang cùng ý nghĩa với mọi parser. Dấu `+` thường được hiểu là khoảng trắng trong ngữ cảnh form URL-encoded, trong khi `%2B` biểu diễn dấu cộng.
- **Dấu hỏi trống:** một URI có `?` ở cuối và một URI không có query có thể khác nhau về biểu diễn; tránh sửa nếu không cần.

### Kiểm tra raw query trong WebFlux

Ở nơi có biến `ServerHttpRequest request`:

~~~java
import java.net.URI;
import org.springframework.http.server.reactive.ServerHttpRequest;

URI uri = request.getURI();
String rawPath = uri.getRawPath();
String rawQuery = uri.getRawQuery();
// rawQuery có thể null nếu URI không có query.
~~~

`getRawQuery()` trả biểu diễn chưa giải mã **mà ứng dụng nhận được**. Nó không chứng minh từng byte đã đi nguyên vẹn từ browser qua CDN/ingress. Khi cần đọc giá trị logic, có thể dùng `request.getQueryParams()`; nhưng nếu mục tiêu chỉ là giữ raw query, không cần parse rồi dựng lại.

Một filter như `AddRequestParameter`, custom filter mutate URI, hoặc rule viết lại query của reverse proxy có thể chủ động sửa tham số. Do đó cần phân biệt **hành vi path-only của RewritePath** với **hành vi toàn bộ chuỗi xử lý**.

## 7. Slash đầu, slash cuối, root path và slash trùng

Dấu `/` phân tách các path segment; có hoặc không có slash có thể tạo khác biệt về route, tài nguyên và kiểm soát truy cập.

| Input path | Câu hỏi cần quyết định | Rủi ro |
| --- | --- | --- |
| `/api/v1` | Có chuyển tới `/` hay dùng route riêng? | Regex yêu cầu slash cuối sẽ không khớp |
| `/api/v1/` | Backend nhận root `/` hay path khác? | Sai controller khi rewrite |
| `/api/v1/items` | Có chuyển tới `/items` không? | Trường hợp thông thường |
| `/api/v1/items/` | Có giữ slash cuối không? | Framework backend có thể phân biệt với `/items` |
| `/api/v1//items` | Slash trùng có hợp lệ không? | Proxy có thể gộp hoặc từ chối |
| `/api/v1/items/a%2Fb` | Encoded slash được chấp nhận ra sao? | Các tầng có thể phân đoạn path khác nhau |

### Route tường minh cho base path

Nếu `/api/v1` phải map tới root backend, có thể thêm route riêng:

~~~yaml
spring:
  cloud:
    gateway:
      server:
        webflux:
          routes:
            - id: catalog-root
              order: -10
              uri: http://localhost:9001
              predicates:
                - Path=/api/v1
              filters:
                - SetPath=/

            - id: catalog-child
              order: 0
              uri: http://localhost:9001
              predicates:
                - Path=/api/v1/**
              filters:
                - RewritePath=^/api/v1(?<suffix>/.*)$, $\{suffix}
~~~

Khi đó `/api/v1` có contract tường minh thay vì phụ thuộc regex con. Với `/api/v1/`, kết quả còn phụ thuộc route matcher và cấu hình trailing slash của phiên bản; hãy kiểm tra bằng test. Đừng mặc định `//` tương đương `/` ở mọi tầng.

Nếu áp dụng canonical URL, cần quyết định **giữ nguyên, từ chối hoặc redirect** các dạng slash không chuẩn. Tuyệt đối không sửa `//` trên **toàn URL** bằng thay chuỗi đơn giản, vì có thể làm hỏng cả `https://`.

## 8. Percent-encoding và lỗi decode/encode lặp

Percent-encoding dùng ký tự `%` và hai chữ số hex để biểu diễn byte. Nhiều ký tự cần mã hóa vì chúng có ý nghĩa ngữ pháp trong URI.

| Ký tự | Biểu diễn | Điều cần nhớ |
| --- | --- | --- |
| Dấu cách | `%20` | Không đặt dấu cách thô vào request-target |
| Slash nằm trong dữ liệu segment | `%2F` | Có thể bị hiểu thành dấu phân cách path khi decode |
| Dấu hỏi trong path | `%3F` | Decode/ghép sai có thể biến thành dấu mở query |
| Dấu thăng | `%23` | Không làm phát sinh fragment ở sai tầng |
| Dấu phần trăm | `%25` | Decode nhiều lần có thể sinh chuỗi escape mới |
| Dấu cộng | `%2B` | Không nhầm với dấu cách ở query form-urlencoded |
| Chữ “á” | `%C3%A1` (UTF-8) | Ký tự Unicode có thể chiếm nhiều byte |

**Lỗi 1 — Decode path trước khi định tuyến:** Nếu `/items/a%2Fb` biến thành `/items/a/b`, một segment có thể bị hiểu thành hai. Kiểm tra security theo cách này rồi xử lý backend theo cách khác là rủi ro.

**Lỗi 2 — Encode lặp:** Nếu `%20` bị encode thêm một lần, `%` thành `%25`, khiến `/blue%20shirt` biến thành `/blue%2520shirt`.

**Lỗi 3 — Decode hai lần:** `/a%252Fb` sau một lần decode thành `/a%2Fb`, sau lần tiếp theo thành `/a/b`. Các chính sách trên Gateway và service có thể không còn nhất quán.

Khi chỉ bỏ prefix, nên dùng filter built-in thay vì `URLDecoder.decode(rawPath, ...)` hoặc `URLEncoder.encode(entireUrl, ...)`. Hai API này có ngữ nghĩa form encoding và không phù hợp để áp tùy ý lên toàn URI.

### Các dạng path phải kiểm tra trong bảo mật

Kiểm tra `%2F`, `%5C`, `%2E`, `%252F`, dấu `..` và slash trùng qua ingress, Gateway, Spring Security và backend. Nếu một tầng chuẩn hóa hoặc từ chối khác tầng còn lại, kẻ tấn công có thể tìm cách vượt qua route predicate hoặc kiểm soát truy cập. **Chính sách an toàn là thống nhất cách hiểu hoặc từ chối dạng mơ hồ**, không cố vượt rào để nhận encoded slash trong mọi trường hợp.

## 9. Regex và cách escape replacement trong YAML

`RewritePath` dùng Java regex. Named capture group `(?<suffix>...)` được tham chiếu bằng cú pháp `${suffix}` ở cấp regex replacement. Trong YAML cấu hình Gateway, thường dùng dạng escape `$\{suffix}` để tránh Spring coi replacement là property placeholder.

~~~yaml
filters:
  - RewritePath=^/api/v1(?<suffix>/.*)$, $\{suffix}
~~~

Một cách trình bày đầy đủ để người đọc dễ phân biệt các đối số:

~~~yaml
filters:
  - name: RewritePath
    args:
      regexp: '^/api/v1(?<suffix>/.*)$'
      replacement: '$\{suffix}'
~~~

**Chỉ YAML parse thành công chưa đủ**: cần kiểm tra route đã được binder nạp và đường dẫn thực nhận. Dấu `$` có ý nghĩa trong regex replacement lẫn Spring property placeholder, nên cấu hình dễ sai khi thiếu escape.

Viết regex đủ chặt, ví dụ `^/api/v1(?<suffix>/.*)$` có anchor đầu/cuối, thay vì chỉ tìm chuỗi `/api/v1` ở bất kỳ vị trí nào. Một pattern không có ràng buộc dễ sửa nhầm `/legacy/api/v1/items` hoặc `/api/v12/items`.

Khi path chứa dữ liệu do client điều khiển, tránh regex quá phức tạp với các nhóm lặp lồng nhau có nguy cơ backtracking tốn CPU. `SetPath` dùng URI template variables từ route predicate; `RewritePath` dùng regex trên path. Chọn công cụ theo hợp đồng và kiểm tra riêng những giá trị percent-encoded.

## 10. Rewrite nội bộ khác HTTP redirect

**Rewrite** xảy ra bên trong Gateway khi chuyển request tới upstream: client vẫn gọi URL ban đầu. **Redirect** trả HTTP 3xx và header `Location`; client có thể phát request mới tới URL khác.

~~~mermaid
sequenceDiagram
    participant C as Client
    participant G as Spring Cloud Gateway
    participant S as Backend
    Note over C,S: Rewrite nội bộ
    C->>G: GET /api/v1/items/42?lang=vi
    G->>S: GET /items/42?lang=vi
    S-->>G: 200 OK
    G-->>C: 200 OK
    Note over C,S: Redirect HTTP
    C->>G: GET /old-page?lang=vi
    G-->>C: 302 Location: /new-page
    C->>G: GET /new-page (nếu theo redirect)
~~~

Ví dụ chuyển hướng cố định:

~~~yaml
predicates:
  - Path=/old-docs
filters:
  - RedirectTo=302, https://docs.example.test/guide
~~~

`Location` là URL đã cấu hình. **Không mặc định query ban đầu tự được mang sang URL redirect**. Nếu hợp đồng cần giữ query, phải định nghĩa cách dựng Location rõ ràng, dùng tính năng phù hợp với đúng phiên bản hoặc handler kiểm soát được URL. Không dùng host do client tự chọn để dựng Location, tránh **open redirect**.

| Status | Ý nghĩa liên quan tới method |
| --- | --- |
| 301 | Redirect vĩnh viễn; một số client lịch sử chuyển POST thành GET |
| 302 | Redirect tạm thời; một số client chuyển POST thành GET |
| 307 | Redirect tạm thời, client theo redirect cần giữ method và body |
| 308 | Redirect vĩnh viễn, client theo redirect cần giữ method và body |

307/308 có ngữ nghĩa giữ method nhưng **không bảo đảm client sẽ theo redirect hoặc có thể phát lại request body streaming**. Với API có thao tác ghi, cần thận trọng trước khi yêu cầu client redirect.

## 11. Proxy, TLS và forwarded headers có thể ảnh hưởng URL

Trong production, client có thể đi qua CDN, WAF, ingress hoặc load balancer trước Gateway:

~~~mermaid
flowchart LR
    A[Client] --> B[CDN / WAF]
    B --> C[Ingress / reverse proxy]
    C --> D[Spring Cloud Gateway]
    D --> E[Microservice]
~~~

Cần tách bốn góc nhìn:

- **Public URL client thấy:** có thể chứa prefix khác với path vào Gateway nếu ingress đã rewrite.
- **Raw path Gateway nhận:** sau các tầng proxy phía trước.
- **Path sau GatewayFilter:** đã đi qua `RewritePath`, `StripPrefix` hoặc các filter liên quan.
- **Request target backend nhận:** có thể qua sidecar/proxy nội bộ, tiếp tục chịu chính sách HTTP stack.

Các header `Forwarded`, `X-Forwarded-Proto`, `X-Forwarded-Host` hoặc `X-Forwarded-Prefix` có thể cung cấp thông tin URL gốc **khi được đặt bởi proxy đáng tin cậy**. Nếu client được phép tự đưa chúng vào và ứng dụng dùng để tạo redirect, có thể tạo sai URL, chuyển hướng sang host khác hoặc lộ dữ liệu. Cần xóa/ghi đè header không tin cậy ở biên, cấu hình trust proxy đúng và kiểm thử.

**TLS termination** cũng quan trọng: request ngoài là HTTPS nhưng kết nối nội bộ tới Gateway có thể là HTTP. Khi dựng Location tuyệt đối, cần xác định đúng scheme/host/port công khai từ nguồn tin cậy; không đoán từ header do người dùng tự gửi.

## 12. Đo đường dẫn và raw query ở backend WebFlux

Để biết kết quả cuối, tạo backend thử nghiệm chạy ở cổng `9001`:

~~~java
import java.net.URI;

import org.springframework.http.server.reactive.ServerHttpRequest;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
class RequestTargetDebugController {
    record RequestTarget(String rawPath, String rawQuery) {}

    @GetMapping("/items/**")
    Mono<RequestTarget> show(ServerHttpRequest request) {
        URI uri = request.getURI();
        return Mono.just(new RequestTarget(
                uri.getRawPath(),
                uri.getRawQuery()
        ));
    }
}
~~~

Đây là controller minh họa, cần đặt trong ứng dụng WebFlux thực tế và bật HTTP server để chạy. Nó cho thấy URI **backend nhận**, không tự chứng minh URL nguyên bản phía client. Không đưa debug endpoint này ra internet nếu query có token hoặc dữ liệu nhạy cảm.

Sử dụng route `catalog-v1` từ phần 4:

~~~bash
# Query có tham số lặp:
curl -i --path-as-is --globoff \
  'http://localhost:8080/api/v1/items/42?tag=a&tag=b&sort=desc'

# Mã hóa dấu cách và dấu cộng:
curl -i --path-as-is --globoff \
  'http://localhost:8080/api/v1/items/blue%20shirt?search=a%2Bb'

# Slash cuối:
curl -i --path-as-is --globoff \
  'http://localhost:8080/api/v1/items/?page=2'

# Encoded slash: có thể bị một tầng từ chối:
curl -i --path-as-is --globoff \
  'http://localhost:8080/api/v1/items/a%2Fb?source=test'
~~~

`--path-as-is` ngăn curl tự loại bỏ một số dấu chấm và segment trong path trước khi gửi; `--globoff` tắt xử lý glob trong URL. Hai tùy chọn này **không tắt chính sách chuẩn hóa và bảo mật của proxy, Gateway hay backend**.

| Input ở Gateway | Raw path mong đợi ở backend nếu được chấp nhận | Raw query mong đợi |
| --- | --- | --- |
| `/api/v1/items/42?tag=a&tag=b&sort=desc` | `/items/42` | `tag=a&tag=b&sort=desc` |
| `/api/v1/items/blue%20shirt?search=a%2Bb` | `/items/blue%20shirt` | `search=a%2Bb` |
| `/api/v1/items/?page=2` | `/items/` | `page=2` |
| `/api/v1/items/a%2Fb?source=test` | Không mặc định: có thể bị chặn hoặc diễn giải khác | `source=test` nếu request được chấp nhận |

Các giá trị trên là **mục tiêu kiểm thử**, không phải output đã chạy thử trong bài. Nếu kết quả khác, lần lượt gọi trực tiếp backend, qua Gateway, rồi qua ingress để xác định tầng đã thay đổi path/query.

## 13. Lỗi thường gặp và cách chẩn đoán

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| Query mất sau rewrite | Custom filter dựng URI mới chỉ có path; proxy sửa query | Dùng path-only filter, xem `getRawQuery()` ở các tầng |
| `%20` thành `%2520` | Encode percent escape lần hai | Bỏ bước encode lặp, chọn đúng URI component |
| Encoded slash bị từ chối | HTTP stack có chính sách bảo mật | Xác định contract, từ chối nhất quán hoặc chọn định danh khác |
| `/api/v1` không khớp regex | Regex đòi suffix bắt đầu bằng slash | Viết route root riêng hoặc đổi regex có chủ đích |
| Backend trả 404 khi có slash cuối | Controller phân biệt `/items/` với `/items` | Thống nhất contract và kiểm thử |
| Path có `//` đi sai route | Proxy hoặc framework gộp/từ chối slash trùng | Chọn canonical path và xác minh từng tầng |
| `tag=a&tag=b` chỉ còn một tham số | Parse thành map chỉ giữ một giá trị | Giữ raw query hoặc dùng cấu trúc multi-value |
| Dấu `+` thành khoảng trắng | Form decoding ở sai vị trí | Phân biệt path/query; kiểm tra `%2B` |
| YAML replacement có `$` nhưng không chạy | Escape placeholder hoặc regex sai | Xem cách viết `$\{suffix}`, kiểm tra config thực nạp |
| Redirect mất query | Location không chứa query theo yêu cầu | Định nghĩa URL đích rõ ràng |
| Redirect sang host giả | Tin forwarded headers từ client | Xác thực nguồn proxy và host được phép |
| Phân quyền khác nhau giữa Gateway và backend | Decode/normalize URL không nhất quán | Test encoded path, từ chối input mơ hồ |

Không thể chỉ dùng HTTP status `200` để kết luận rewrite đúng. Backend có thể trả 200 nhưng nhận thiếu query; một 404 cũng có thể xuất phát từ backend sau khi route đã được chọn chính xác.

## 14. Bài thực hành tổng hợp

**Bối cảnh:** API công khai của hệ thống bán hàng dùng `/api/v2/products/**`. Product service chỉ nhận `/products/**` và hỗ trợ lọc bằng nhiều giá trị query `tag`. Gateway còn áp dụng xác thực, rate limiting, tracing và TLS theo thiết kế.

### Phần A — Thiết kế route

1. Khai báo route `product-v2` với `Path=/api/v2/**` tới Product service.
2. Chọn `StripPrefix=2` hoặc `RewritePath` để bỏ tiền tố; giải thích vì sao chọn filter đó.
3. Xác định hợp đồng cho `/api/v2`, `/api/v2/` và `/api/v2/products/`; không dựa vào trailing slash normalization không được kiểm soát.

### Phần B — Kiểm thử

| Request | Kiểm chứng |
| --- | --- |
| `GET /api/v2/products/42?lang=vi` | Backend nhận `/products/42` cùng query `lang=vi` |
| `GET /api/v2/products?tag=a&tag=b` | Không mất tham số `tag` thứ hai |
| `GET /api/v2/products/blue%20shirt?search=a%2Bb` | Không double-encode path hoặc thay query vô ý |
| `GET /api/v2/products/` | Slash cuối được xử lý theo contract |
| `GET /api/v2/products/a%2Fb` | Được chấp nhận/từ chối theo chính sách rõ ràng |
| `GET /api/v2/products?empty=&flag` | Không tự xóa hay gộp dạng query đặc biệt |

### Phần C — Kiểm tra tính đúng đắn và an toàn

1. Trong môi trường kiểm thử, giả lập một custom filter dựng URI mới nhưng bỏ query; quan sát lỗi rồi trả về cách đổi riêng path.
2. So sánh gọi trực tiếp Gateway và đi qua ingress để tìm chỗ bị thay đổi slash/encoding.
3. Xác minh định tuyến và phân quyền không bị vượt qua bằng `%2F`, `%252F` hoặc các path mơ hồ.
4. Với redirect từ URL cũ, thử GET và POST cùng các status 302/307 để hiểu Location và cách client xử lý method.
5. Ghi nhận route ID, latency, status và trace mà không ghi token hay raw query nhạy cảm.

**Tiêu chí đạt:** Prefix được đổi đúng, query lặp được giữ, encoding không bị xử lý thêm ngoài ý muốn, root/trailing slash có chính sách, encoded slash được xử lý nhất quán, và kết quả đã kiểm chứng ở backend thực nhận.

## 15. Ghi nhớ

- **Đổi path là đổi một thành phần của URI.** Dùng `StripPrefix`, `RewritePath`, `SetPath` hoặc `PrefixPath` thay vì tự ghép lại toàn URL.
- **Query string** có thể có tham số lặp, giá trị rỗng, thứ tự và percent-encoding. Tránh parse rồi serialize khi chỉ muốn giữ nguyên.
- **Slash thật và encoded slash không đồng nhất.** Root, slash cuối, slash trùng và `%2F` cần hợp đồng và kiểm thử qua mọi tầng.
- **Raw path khác decoded path.** Decode/encode thêm có thể làm `%2F` thành `/` hoặc `%20` thành `%2520`.
- **RewritePath** dùng regex và replacement; trong YAML cần chú ý escape nhóm như `$\{suffix}` và đúng namespace phiên bản Gateway.
- **Rewrite nội bộ khác redirect.** Redirect có Location, có thể tạo request mới và không tự đảm bảo giữ query/method.
- Khi vận hành Gateway, kiểm chứng **URL backend thực nhận**, dùng forwarded headers từ nguồn tin cậy và bảo vệ đồng nhất trước các biến thể path được mã hóa.
