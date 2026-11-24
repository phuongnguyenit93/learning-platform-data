# AddRequestHeader và SetRequestHeader: thêm hoặc thay thế giá trị trong Spring Cloud Gateway

Trong **SPRING_CLOUD_GATEWAY**, API Gateway không chỉ chọn backend bằng route predicate mà còn có thể thay đổi HTTP request trước khi chuyển tiếp. Hai **GatewayFilter Factory** dễ nhầm nhất là `AddRequestHeader` và `SetRequestHeader`: cả hai đều tác động đến **header của request đi xuống dịch vụ**, nhưng khác nhau ở cách xử lý giá trị đã tồn tại.

Bài học thuộc chương **Header yêu cầu** và giải thích chính xác khi nào nên thêm, khi nào nên thay thế, cú pháp YAML rút gọn/đầy đủ, ý nghĩa header đa giá trị, tác động của filter order và cách xác minh từ downstream. Những quyết định này liên quan trực tiếp đến truyền correlation ID, nhận diện route, khám phá dịch vụ, xác thực, rate limiting, circuit breaker, retry, TLS và khả năng quan sát request của hệ thống microservices.

> **Phạm vi:** Ví dụ sử dụng cú pháp phổ biến của **Spring Cloud Gateway Server WebFlux 4.x** với `spring.cloud.gateway.routes`. Tên starter, namespace cấu hình và API có thể khác ở dòng phát hành mới hơn hoặc ở **Gateway Server MVC**. Hãy đối chiếu phiên bản Spring Boot, Spring Cloud và biến thể Gateway thực tế trước khi áp dụng.

## 1. So sánh ngắn gọn: Add và Set

Giả sử client gửi đến Gateway:

~~~http
GET /api/orders/42 HTTP/1.1
Host: gateway.example.test
X-Edge-Source: mobile-client
~~~

Một route có filter `AddRequestHeader=X-Edge-Source,edge-gateway` sẽ yêu cầu thêm giá trị `edge-gateway` cho header có tên `X-Edge-Source`. Nếu route dùng `SetRequestHeader=X-Edge-Source,edge-gateway`, Gateway sẽ thay tập giá trị header đó bằng giá trị mới.

| Trạng thái trước filter | `AddRequestHeader=X-Edge-Source,edge-gateway` | `SetRequestHeader=X-Edge-Source,edge-gateway` |
|---|---|---|
| Header chưa tồn tại | Có một giá trị: `edge-gateway` | Có một giá trị: `edge-gateway` |
| Header có `mobile-client` | Có hai giá trị: `mobile-client` và `edge-gateway` | Chỉ còn `edge-gateway` |
| Header có `a` và `b` | Giữ `a`, `b` và thêm `edge-gateway` | Thay toàn bộ bằng `edge-gateway` |
| Header tên viết khác kiểu hoa/thường | Vẫn xử lý cùng một tên header | Vẫn xử lý cùng một tên header |

**Add = thêm một giá trị vào danh sách hiện có. Set = thay toàn bộ danh sách giá trị của tên header đó.** Cả hai đều chỉ là xử lý cấu hình của filter; không tự xác thực nội dung header, và không tự tạo chính sách bảo mật.

Ở tầng API của Spring WebFlux, có thể hình dung hiệu ứng gần với hai thao tác trên `HttpHeaders`:

~~~java
headers.add("X-Edge-Source", "edge-gateway"); // Thêm giá trị
headers.set("X-Edge-Source", "edge-gateway"); // Thay các giá trị hiện có
~~~

Đây là **minh họa hành vi**, không phải mã nguồn nguyên văn của hai factory. Đối tượng request thật trong WebFlux có đặc điểm bất biến về mặt mô hình; các filter tạo/mutate request phù hợp để đưa header đã chỉnh vào chuỗi xử lý.

## 2. Header được thay ở giai đoạn nào?

Khi một request đến Gateway Server WebFlux, hệ thống thường thực hiện các bước:

1. Thành phần HTTP/WebFlux nhận request, có thể áp dụng `WebFilter` hoặc Spring Security.
2. Gateway đánh giá route predicates như `Path`, `Method`, `Host` và `Header` để chọn route.
3. `FilteringWebHandler` thực thi chuỗi `GlobalFilter` và `GatewayFilter` tương ứng với route đã chọn.
4. `AddRequestHeader` hoặc `SetRequestHeader` tạo request chuyển tiếp mang header mới.
5. Routing filter gửi request sang downstream qua URI tĩnh hoặc cơ chế như `lb://` với load balancer/service discovery phù hợp.
6. Response của downstream đi ngược lại qua chuỗi xử lý và được trả về client.

~~~mermaid
flowchart TD
    C["Client gửi request + headers"] --> S["WebFlux / Spring Security"]
    S --> P{"Route predicates match?"}
    P -->|Không| N["Không chạy GatewayFilter của route này"]
    P -->|Có| G["Gateway filter chain"]
    G --> A{"Filter header"}
    A -->|AddRequestHeader| AD["Giữ giá trị cũ + thêm giá trị mới"]
    A -->|SetRequestHeader| ST["Thay tất cả giá trị của tên header"]
    AD --> R["Routing tới downstream"]
    ST --> R
    R --> D["Backend nhận request đã biến đổi"]
    D --> B["Response về Gateway và client"]
~~~

**Điểm dễ sai:** `Header` **route predicate** kiểm tra header của request khi Gateway đang chọn route. Còn `AddRequestHeader`/`SetRequestHeader` là **filter chạy sau bước chọn route**. Nếu bạn thêm header bằng GatewayFilter trên cùng route, header mới đó **không thể khiến predicate Header của chính route bỗng khớp trở lại**.

Ví dụ một route yêu cầu `Header=X-Client-Tier,premium` sẽ không được chọn cho request thiếu `X-Client-Tier`, kể cả khi bên dưới route có `SetRequestHeader=X-Client-Tier,premium`.

## 3. Cú pháp rút gọn trong YAML

Với route `orders`, muốn **thêm** header `X-Edge-Source: edge-gateway` trước khi gọi backend:

~~~yaml
spring:
  cloud:
    gateway:
      routes:
        - id: orders
          uri: http://localhost:9090
          predicates:
            - Path=/api/orders/**
          filters:
            - StripPrefix=1
            - AddRequestHeader=X-Edge-Source,edge-gateway
~~~

Nếu muốn **ghi đè mọi giá trị** của cùng header, chỉ thay tên factory:

~~~yaml
spring:
  cloud:
    gateway:
      routes:
        - id: orders
          uri: http://localhost:9090
          predicates:
            - Path=/api/orders/**
          filters:
            - StripPrefix=1
            - SetRequestHeader=X-Edge-Source,edge-gateway
~~~

Mỗi ví dụ là **một cấu hình thay thế**. Với request `GET /api/orders/42`, `StripPrefix=1` bỏ phân đoạn `api`, nên downstream nhận đường dẫn `/orders/42` nếu các thành phần khác không sửa path.

Ở shortcut, mẫu là:

~~~text
AddRequestHeader=<header-name>,<header-value>
SetRequestHeader=<header-name>,<header-value>
~~~

Giá trị **thứ nhất là tên header**, giá trị **thứ hai là nội dung header**. Đảo hai vị trí sẽ khiến Gateway dùng nhầm giá trị làm tên header.

Không nhầm lẫn dấu phẩy phân tách hai tham số của shortcut với một HTTP header **có nội dung chứa dấu phẩy**. Khi nội dung phức tạp, ưu tiên dạng đầy đủ trong phần tiếp theo.

## 4. Cú pháp đầy đủ với `name` và `args`

Dùng dạng expanded khi cần đọc rõ tên và giá trị, đặc biệt trong code review:

**Thêm giá trị:**

~~~yaml
spring:
  cloud:
    gateway:
      routes:
        - id: orders
          uri: http://localhost:9090
          predicates:
            - name: Path
              args:
                patterns:
                  - /api/orders/**
          filters:
            - name: AddRequestHeader
              args:
                name: X-Edge-Source
                value: edge-gateway
~~~

**Thay thế giá trị:**

~~~yaml
spring:
  cloud:
    gateway:
      routes:
        - id: orders
          uri: http://localhost:9090
          predicates:
            - Path=/api/orders/**
          filters:
            - name: SetRequestHeader
              args:
                name: X-Edge-Source
                value: edge-gateway
~~~

Ở đây có **hai ý nghĩa khác nhau của từ `name`**:

- `filters[0].name` là tên factory: `AddRequestHeader` hoặc `SetRequestHeader`.
- `filters[0].args.name` là tên HTTP header: `X-Edge-Source`.
- `filters[0].args.value` là giá trị HTTP header: `edge-gateway`.

Cả shortcut và expanded đều được chuyển thành cấu hình filter phù hợp khi Gateway tạo route. Với cùng factory và cùng tham số, chúng hướng đến cùng hành vi khi xử lý request.

| Mục tiêu | Shortcut | Expanded (`filters` chứa phần tử map) |
|---|---|---|
| Thêm một giá trị | `AddRequestHeader=X-Edge-Source,edge-gateway` | `name: AddRequestHeader`, `args.name: X-Edge-Source`, `args.value: edge-gateway` |
| Thay mọi giá trị | `SetRequestHeader=X-Edge-Source,edge-gateway` | `name: SetRequestHeader`, `args.name: X-Edge-Source`, `args.value: edge-gateway` |

## 5. HTTP header có thể có nhiều giá trị

Một điểm quan trọng là **tên header không nhất thiết chỉ có một giá trị**. Trong Spring, `HttpHeaders` có mô hình `MultiValueMap<String, String>`; một tên header có thể ánh xạ tới **danh sách nhiều chuỗi**.

Ví dụ request từ client chứa hai dòng có cùng tên header:

~~~http
GET /api/orders/42 HTTP/1.1
Host: gateway.example.test
X-Feature-Flag: alpha
X-Feature-Flag: beta
~~~

Kết quả khái niệm:

~~~text
Ban đầu:
  X-Feature-Flag -> ["alpha", "beta"]

Sau AddRequestHeader=X-Feature-Flag,gamma:
  X-Feature-Flag -> ["alpha", "beta", "gamma"]

Sau SetRequestHeader=X-Feature-Flag,gamma:
  X-Feature-Flag -> ["gamma"]
~~~

**Đừng dùng số dòng header nhìn thấy trên dây mạng làm bằng chứng duy nhất.** HTTP client, proxy hoặc server có thể biểu diễn một số header đa giá trị thành nhiều dòng hoặc gộp giá trị trong một dòng, tùy semantics của từng header và phiên bản HTTP. Kiểm chứng **danh sách giá trị được backend nhận**, chứ không chỉ kiểm tra cách một công cụ in chúng ra.

Dấu phẩy trong một chuỗi như `X-Feature-Flag: alpha,beta` **không tự đồng nghĩa** với hai giá trị `alpha`, `beta` trong `HttpHeaders`. Với các header có cú pháp danh sách, backend có thể tự tách theo quy tắc HTTP tương ứng. Một số header, đặc biệt `Set-Cookie` ở phía response, có quy tắc riêng; không áp dụng máy móc cách ghép dấu phẩy cho tất cả tên header.

### Tên header không phân biệt hoa/thường

Trong HTTP, `X-Edge-Source`, `x-edge-source` và `X-EDGE-SOURCE` chỉ cùng một tên header về mặt ngữ nghĩa. Vì vậy, `SetRequestHeader` phải được hiểu là thay giá trị của **header theo tên**, không tạo ra header mới chỉ vì kiểu chữ khác.

Hãy chọn một cách viết thống nhất cho tài liệu/log, nhưng đừng dùng chữ hoa/thường làm cơ chế phân quyền hoặc kiểm tra tin cậy.

## 6. Add rồi Set, hoặc Set rồi Add: filter order đổi kết quả

Khi nhiều filter chạm vào **cùng tên header**, thứ tự chạy quyết định trạng thái cuối:

~~~yaml
filters:
  - AddRequestHeader=X-Flow,first
  - SetRequestHeader=X-Flow,final
~~~

Trong một route đơn giản, nếu hai filter thực thi phần sửa request theo thứ tự này, trạng thái cuối sẽ là **`X-Flow: final`**: `SetRequestHeader` loại giá trị trước đó.

Đảo lại:

~~~yaml
filters:
  - SetRequestHeader=X-Flow,final
  - AddRequestHeader=X-Flow,extra
~~~

Kết quả cuối được kỳ vọng là **hai giá trị** `final` và `extra` ở request đến downstream.

~~~mermaid
flowchart LR
    I["Request ban đầu: X-Flow=client"] --> A["Add first"]
    A --> S["Set final"]
    S --> O["Downstream: [final]"]
    I --> S2["Set final"]
    S2 --> A2["Add extra"]
    A2 --> O2["Downstream: [final, extra]"]
~~~

Đây là ví dụ dùng các **GatewayFilters trên cùng route**, với thứ tự thực thi tương ứng. Trong hệ thống thật, `default-filters`, `GlobalFilter`, filter có `Ordered` riêng và thành phần outbound HTTP khác có thể tác động trước/sau. Khi debug, hãy quan sát **request downstream thực nhận**, không suy ra chỉ từ vị trí các dòng YAML.

### Kết hợp với RemoveRequestHeader

Nếu muốn đặt một giá trị thống nhất, `SetRequestHeader` thường đã đủ vì nó thay tất cả giá trị của tên header tương ứng:

~~~yaml
filters:
  - SetRequestHeader=X-Edge-Source,edge-gateway
~~~

Một số nhóm dùng `RemoveRequestHeader` trước để thể hiện chính sách xóa header đầu vào không tin cậy:

~~~yaml
filters:
  - RemoveRequestHeader=X-Internal-User
  # Chỉ gắn lại danh tính bằng logic đáng tin cậy nếu nghiệp vụ thực sự yêu cầu.
~~~

Không nên tự bổ sung `X-Internal-User` từ một chuỗi cố định rồi coi request đã được xác thực. Việc lấy danh tính phải đến từ security context đáng tin cậy, kết hợp chính sách mạng/ngăn client truy cập trực tiếp backend.

## 7. Khi nào nên dùng Add, khi nào nên dùng Set?

| Tình huống | Lựa chọn thường phù hợp | Lý do |
|---|---|---|
| Thêm một nhãn chẩn đoán vào header đa giá trị do các proxy hợp lệ cùng góp phần xây dựng | `AddRequestHeader` sau khi xác nhận semantics của header | Giữ các giá trị đã có |
| Đặt tên route hoặc tên edge service đáng tin cậy, không muốn nhận giá trị giả mạo từ client | `SetRequestHeader` | Ghi đè giá trị đến từ client |
| Chuẩn hóa một header do gateway quản lý | `SetRequestHeader` | Tránh nhiều giá trị mâu thuẫn |
| Thêm một tag bên cạnh các tag đã có | `AddRequestHeader` nếu downstream thật sự hỗ trợ nhiều giá trị | Giữ ngữ nghĩa danh sách |
| Xóa toàn bộ header nhạy cảm không cần gửi xuống | `RemoveRequestHeader` | Không phải vấn đề thêm hay thay |
| Đưa danh tính người dùng đã xác thực đến downstream | Filter tích hợp security hoặc custom filter tin cậy | Giá trị phải lấy từ kết quả xác thực, không phải hằng số YAML |
| Chuyển tiếp access token OAuth2 theo chính sách | Cơ chế như Token Relay phù hợp, Spring Security | `Add`/`Set` không thay được OAuth2 token handling |
| Đặt correlation ID động cho từng request | Tích hợp tracing hoặc custom filter có kiểm tra/khởi tạo ID | Một chuỗi cấu hình cố định không tạo ID duy nhất |
| Sửa response header trả về client | `AddResponseHeader` hoặc `SetResponseHeader` | Hai factory đang học chỉ tác động request |

**Nguyên tắc chọn:** nếu header thuộc quyền quản lý của Gateway và downstream phải nhận **đúng một giá trị**, `SetRequestHeader` là lựa chọn rõ ràng hơn. Nếu header có ngữ nghĩa hỗ trợ **nhiều giá trị độc lập** và cần giữ giá trị cũ, mới cân nhắc `AddRequestHeader`.

## 8. Truyền giá trị lấy từ biến URI của route

Trong các dòng Gateway Server WebFlux hỗ trợ cơ chế mở rộng biến URI, `AddRequestHeader` và `SetRequestHeader` có thể dùng biến được route predicate trích xuất.

Ví dụ match Host theo subdomain:

~~~yaml
spring:
  cloud:
    gateway:
      routes:
        - id: tenant-catalog
          uri: http://localhost:9091
          predicates:
            - Host={tenant}.example.test
            - Path=/api/catalog/**
          filters:
            - StripPrefix=1
            - SetRequestHeader=X-Route-Tenant,{tenant}
~~~

Giả sử Gateway nhận request với Host `shop-a.example.test` và path `/api/catalog/42`. Khi predicate Host và Path khớp, giá trị `{tenant}` có thể được thay bằng `shop-a`, và backend nhận `X-Route-Tenant: shop-a` nếu route/filter/phiên bản hỗ trợ như mô tả.

Ví dụ tương đương dùng `AddRequestHeader`:

~~~yaml
filters:
  - AddRequestHeader=X-Route-Tenant,{tenant}
~~~

Khác biệt vẫn là **add giữ giá trị ban đầu** nếu client đã cung cấp `X-Route-Tenant`, còn **set thay nó**. Với header nội bộ phân luồng tenant, bạn thường muốn **ghi đè giá trị client tự nhập** và chỉ tin tưởng kết quả predicate đã được kiểm chứng ở tầng proxy.

**Cảnh báo về ranh giới tin cậy:** Host và các header forwarded vẫn có thể bị thao túng tùy mạng/proxy/TLS. Dữ liệu `tenant` trích từ URL **không chứng minh** người dùng thuộc tenant đó. Backend cần đối chiếu tenant với danh tính/claims và quyền truy cập; chỉ đọc `X-Route-Tenant` như thông tin hỗ trợ định tuyến hoặc logging khi có hợp đồng tin cậy rõ ràng.

Không sử dụng `{tenant}` như một cú pháp template có thể lấy được mọi thứ trong request. Nó chỉ mở rộng khi có biến tương ứng do predicate hoặc cơ chế được phiên bản Gateway hỗ trợ cung cấp.

## 9. Hạn chế của shortcut với giá trị có dấu phẩy

Shortcut thường tách tên factory và các giá trị theo vị trí bằng dấu `=` và dấu phẩy. Ví dụ:

~~~yaml
filters:
  - AddRequestHeader=X-Region,ap-southeast
~~~

Nếu cần một **chuỗi giá trị có dấu phẩy**, ví dụ `east,west`, dạng expanded giúp thể hiện ý định rõ:

~~~yaml
filters:
  - name: AddRequestHeader
    args:
      name: X-Regions
      value: 'east,west'
~~~

Ở đây `east,west` là **một giá trị dạng chuỗi**. Nếu muốn hai giá trị độc lập, và downstream hỗ trợ nhiều giá trị, có thể áp dụng hai filter để thêm từng giá trị:

~~~yaml
filters:
  - AddRequestHeader=X-Regions,east
  - AddRequestHeader=X-Regions,west
~~~

Kết quả mục tiêu là `X-Regions` có hai giá trị `east` và `west` ở request downstream. Nếu có proxy hoặc một filter khác sửa cùng header, phải kiểm chứng lại thực tế.

**Đừng dùng shortcut `AddRequestHeader=X-Regions,east,west` rồi mặc định Gateway sẽ hiểu là hai giá trị cần thêm.** Cú pháp shortcut của factory này mô tả tên header và một tham số giá trị; số lượng, escaping và cách xử lý tham số thừa phụ thuộc chi tiết triển khai/phiên bản.

### Ký tự đặc biệt trong YAML

Khi giá trị chứa `:`, `#`, `{`, dấu phẩy, khoảng trắng đầu/cuối hoặc ký tự có thể bị parser hiểu là kiểu khác, dùng quote phù hợp. Ví dụ giá trị chữ `true` nên ghi rõ:

~~~yaml
filters:
  - name: SetRequestHeader
    args:
      name: X-Feature-Enabled
      value: 'true'
~~~

Với khai báo dạng expanded, `args.value` là phần giá trị chứ không phải tên factory. Nếu sử dụng placeholder từ cấu hình Spring Boot, phải cân nhắc việc giá trị thay đổi theo profile/environment và kiểm tra phiên bản runtime thật.

## 10. Cấu hình `default-filters` và phạm vi áp dụng

Khi nhiều route cần cùng một header, một số dòng Gateway Server WebFlux hỗ trợ `default-filters` để áp dụng filter mặc định lên các route do cơ chế cấu hình liên quan tạo ra:

~~~yaml
spring:
  cloud:
    gateway:
      default-filters:
        - SetRequestHeader=X-Edge-Environment,staging
      routes:
        - id: orders
          uri: http://localhost:9090
          predicates:
            - Path=/api/orders/**
        - id: catalog
          uri: http://localhost:9091
          predicates:
            - Path=/api/catalog/**
~~~

Trong môi trường `staging`, các route này được kỳ vọng gửi `X-Edge-Environment: staging` tới downstream khi filter mặc định được áp dụng. Với production, đặt giá trị theo cấu hình thực tế của môi trường, **không hardcode nhầm staging**.

Cần phân biệt:

- **Filter riêng route:** chỉ tham gia khi route đó được chọn.
- **Default filter:** được ghép vào các route theo cơ chế được phiên bản Gateway hỗ trợ.
- **GlobalFilter:** logic chung ở tầng chuỗi Gateway, không phải phần tử `filters` khai báo trực tiếp trong từng route.
- **WebFilter/Spring Security:** có thể chạy trước route matching, với phạm vi khác GatewayFilter.

Khi default filter và route filter cùng sửa tên header, hãy xác minh **thứ tự thực thi cuối cùng**. Không cho rằng một filter “riêng route” luôn chạy sau mọi filter mặc định, hoặc một filter “global” luôn chạy trước; kiểm tra order và trace/request downstream thực nhận.

## 11. Bài thực hành: quan sát giá trị ở backend

Để phân biệt Add và Set chính xác, cần đo **header request tại downstream**, không chỉ nhìn `curl` gửi vào Gateway.

### Chuẩn bị

Giả sử:

- Gateway Server WebFlux lắng nghe tại `http://localhost:8080`.
- Backend echo chạy tại `http://localhost:9090`, cung cấp endpoint `GET /echo` và trả lại **các giá trị header đã nhận** dưới dạng JSON hoặc log.
- Các filter bảo mật, retry, proxy bổ sung đã được ghi rõ để hiểu kết quả. Ví dụ có thể chạy trên môi trường test độc lập.

Khai báo hai route như sau:

~~~yaml
spring:
  cloud:
    gateway:
      routes:
        - id: demo-add
          uri: http://localhost:9090
          predicates:
            - Path=/demo/add/**
          filters:
            - StripPrefix=2
            - AddRequestHeader=X-Workshop,from-gateway

        - id: demo-set
          uri: http://localhost:9090
          predicates:
            - Path=/demo/set/**
          filters:
            - StripPrefix=2
            - SetRequestHeader=X-Workshop,from-gateway
~~~

`StripPrefix=2` bỏ `demo` và `add` hoặc `set`, biến `/demo/add/echo` và `/demo/set/echo` đều thành `/echo` trước khi gọi backend.

### Bước 1 — Gửi header từ client

~~~bash
curl -i -H "X-Workshop: from-client" http://localhost:8080/demo/add/echo
curl -i -H "X-Workshop: from-client" http://localhost:8080/demo/set/echo
~~~

Trên Windows PowerShell, nếu `curl` là alias khác công cụ dòng lệnh chuẩn, sử dụng `curl.exe`.

Quan sát nội dung echo/log từ backend:

| Route | Header client gửi | Giá trị backend cần thấy |
|---|---|---|
| `demo-add` | `from-client` | `from-client` **và** `from-gateway` |
| `demo-set` | `from-client` | Chỉ `from-gateway` |

Nếu backend trả JSON có dạng mảng hoặc chuỗi gộp dấu phẩy, hãy kiểm tra contract của ứng dụng echo trước khi kết luận. Mục tiêu là xác minh **giá trị**, không phải hình thức hiển thị HTTP cụ thể.

### Bước 2 — Bỏ header ở client

~~~bash
curl -i http://localhost:8080/demo/add/echo
curl -i http://localhost:8080/demo/set/echo
~~~

Khi không có `X-Workshop` ban đầu, cả hai cách phải hướng đến cùng kết quả là **`from-gateway`**. Từ thử nghiệm này, dễ thấy khác biệt của Add và Set chỉ biểu hiện rõ khi **header đã có giá trị trước filter**.

### Bước 3 — Thử nhiều giá trị đầu vào

~~~bash
curl -i -H "X-Workshop: alpha" -H "X-Workshop: beta" http://localhost:8080/demo/add/echo
curl -i -H "X-Workshop: alpha" -H "X-Workshop: beta" http://localhost:8080/demo/set/echo
~~~

Với Add, backend được kỳ vọng thấy `alpha`, `beta`, `from-gateway`. Với Set, backend được kỳ vọng thấy **chỉ** `from-gateway`. Cần bảo đảm HTTP client, proxy và ứng dụng echo thực sự giữ/hiển thị được header đa giá trị để phép thử có ý nghĩa.

### Bước 4 — Đảo thứ tự filter và dự đoán

Trong một route test riêng, thêm:

~~~yaml
filters:
  - SetRequestHeader=X-Workshop,first
  - AddRequestHeader=X-Workshop,second
~~~

Dự đoán backend nhận hai giá trị `first` và `second`. Đổi thứ tự thành Add rồi Set và kiểm tra backend còn giá trị nào. Đây là cách học thực tế về filter order, đặc biệt hữu ích trước khi thêm default/global filters.

### Bước 5 — Thử route không match

~~~bash
curl -i -H "X-Workshop: from-client" http://localhost:8080/unknown/path
~~~

Nếu không có route/handler khác, Gateway có thể trả HTTP 404. Không nên trông đợi `AddRequestHeader` hay `SetRequestHeader` của `demo-add`/`demo-set` chạy trên request đó.

### Ghi kết quả

| Kiểm tra | Dấu hiệu đạt | Nhóm lỗi nếu không đạt |
|---|---|---|
| Route Add nhận request | Backend thấy cả giá trị client và Gateway | Predicate, cấu hình factory, filter order |
| Route Set nhận request | Backend chỉ thấy giá trị Gateway | Nhầm Add/Set, ghi đè sau filter |
| Request không có header đầu vào | Hai route đều thêm giá trị Gateway | Sai route hoặc tên header |
| Request có nhiều giá trị | Add giữ rồi thêm; Set thay tất cả | Proxy/echo gộp header, cấu hình sai |
| Path sau StripPrefix | Backend nhận `/echo` | Route/filter path |
| Route không khớp | Không chuyển tới backend theo hai route test | Predicate/handler khác |

## 12. An toàn và ranh giới tin cậy của request header

Header mang dữ liệu do client gửi **không mặc định đáng tin**. Một số tên đặc biệt cần xử lý theo chính sách rõ ràng:

| Header / nhóm header | Rủi ro khi Add/Set không kiểm soát | Cách tiếp cận |
|---|---|---|
| `Authorization` | Ghi đè token thật, thêm nhiều token hoặc chuyển sai credentials | Dùng cơ chế xác thực, phân quyền và Token Relay phù hợp; không hardcode token trong YAML |
| `Cookie` | Trộn session/cookie hoặc rò rỉ thông tin không cần thiết | Chỉ chuyển tiếp cookie có mục đích, giữ đúng giới hạn miền và chính sách session |
| `X-Forwarded-For`, `Forwarded` | Client giả mạo địa chỉ IP hoặc chuỗi proxy | Cấu hình trusted proxies và cơ chế forwarded headers đúng phiên bản |
| `Host` | Sai virtual host, sai chữ ký hoặc sai đích routing | Dùng cơ chế PreserveHostHeader/host routing phù hợp khi thật sự cần |
| `X-Internal-User`, `X-User-Role` | Client tự nhận danh tính/quyền | Xóa giá trị không tin cậy và chỉ gắn lại từ security context hợp lệ |
| Correlation ID / trace headers | Mất khả năng ghép trace hoặc cho phép ID giả mạo | Dùng chuẩn propagation/tracing và validate/sanitize giá trị đầu vào |
| `Content-Length`, `Transfer-Encoding` | Sai framing request, lỗi proxy hoặc nguy cơ request smuggling | Để HTTP server/client và bộ lọc chuyên dụng quản lý; không sửa thủ công bằng generic Add/Set |
| Hop-by-hop headers như `Connection` | Sai nghĩa khi đi qua proxy và có thể làm hỏng kết nối | Dùng cơ chế lọc header của Gateway/HTTP stack theo chuẩn, không tùy tiện chuyển tiếp |

Không dùng `SetRequestHeader` với một hằng số như `X-Authenticated: true` để thay thế kiểm tra quyền. **Xác thực** cần đến từ Spring Security hoặc thành phần có thẩm quyền. **Giới hạn lưu lượng** cần chính sách riêng và một key đáng tin cậy; nếu rate limiter đọc một header do client tự đặt, kẻ tấn công có thể xoay giá trị để vượt giới hạn.

Với `lb://order-service`, các filter header vẫn tác động lên **request đến instance được chọn**, nhưng URI `lb://` còn cần discovery/load balancer hoạt động. `CircuitBreaker`/`Retry` có thể tạo nhiều lần gửi request đến downstream; header bất biến như `X-Edge-Source` có thể được dùng trên các lần gọi, trong khi correlation ID hoặc trạng thái idempotency cần quản lý theo chính sách. TLS trên hai chặng client → Gateway và Gateway → downstream cũng được cấu hình riêng; việc thêm header không thay thế TLS.

## 13. Chẩn đoán lỗi thường gặp

| Triệu chứng | Kiểm tra trước | Cách xử lý |
|---|---|---|
| Backend không nhận header mới | Route có match không? Filter có được bind không? Đúng WebFlux/MVC/version không? | Kiểm tra danh sách route, log và request backend |
| Header xuất hiện hai giá trị ngoài ý muốn | Dùng `AddRequestHeader` khi header đầu vào đã tồn tại | Dùng `SetRequestHeader` nếu downstream cần một giá trị |
| Header chỉ còn giá trị Gateway nhưng muốn giữ giá trị client | Dùng `SetRequestHeader` | Đổi sang `AddRequestHeader` khi có hợp đồng đa giá trị hợp lệ |
| Header bị ghi đè dù route đã cấu hình đúng | Default filter, GlobalFilter hoặc proxy khác sửa cùng tên | Lần theo filter order và từng chặng HTTP |
| Dùng `AddRequestHeader=X-A,a,b` nhưng backend nhận sai | Shortcut có dấu phẩy bị tách thành tham số | Dùng expanded `name`/`args.value` |
| `{tenant}` không được thay | Predicate không trích xuất biến, sai placeholder hoặc version | Đối chiếu Host/Path predicate và khả năng hỗ trợ URI variables |
| Header không xuất hiện trong response client | Đang dùng **RequestHeader** filter thay vì **ResponseHeader** filter | Kiểm tra header ở downstream hoặc chọn response filter |
| Client gửi header khác kiểu hoa/thường rồi Set không như dự kiến | Nhiều filter/proxy tác động, không phải tên HTTP phân biệt hoa/thường | Kiểm tra toàn bộ pipeline và danh sách giá trị thực |
| Response 401/403 trước routing nhưng filter route không chạy | Spring Security từ chối trước bước chọn route | Kiểm tra security `WebFilter`, không kỳ vọng route filter chạy |
| Header thay đổi sau deploy nhưng chỉ ở vài request | Các Gateway instance đang dùng config hoặc phiên bản khác nhau | Kiểm tra từng instance, reload/cache/rollout và metrics |

Khi kiểm tra header mang token, session, IP hoặc dữ liệu cá nhân, **không ghi toàn bộ giá trị vào log**. Ưu tiên tên header, số lượng giá trị, giá trị test giả lập hoặc hash đã được xử lý thích hợp, kết hợp correlation ID có kiểm soát.

## 14. Checklist trước khi đưa cấu hình vào production

- [ ] Tôi phân biệt **`AddRequestHeader` thêm** với **`SetRequestHeader` thay toàn bộ giá trị**.
- [ ] Tôi biết header được chỉnh trong **request tới downstream**, không phải response trả client.
- [ ] Tôi xác nhận route đã match; không trông đợi route filter tác động trước route predicate.
- [ ] Tôi khai báo đúng tên factory và các tham số `name`/`value`, hoặc shortcut theo đúng vị trí.
- [ ] Tôi hiểu một header có thể chứa nhiều giá trị, và tên header không phân biệt hoa/thường.
- [ ] Tôi biết khi nào cần giữ nhiều giá trị và khi nào cần đảm bảo **một giá trị cuối cùng**.
- [ ] Tôi đã kiểm tra filter order, default filters và các thành phần khác có thể sửa cùng header.
- [ ] Tôi dùng dạng đầy đủ khi giá trị chứa dấu phẩy hoặc ký tự YAML đặc biệt.
- [ ] Tôi chỉ dùng URI variables khi predicate thực sự cung cấp biến tương ứng.
- [ ] Tôi kiểm thử bằng backend echo hoặc log nhận header tại downstream, bao gồm khi client không có/có một/có nhiều giá trị.
- [ ] Tôi tránh sửa trực tiếp hop-by-hop headers, framing headers và credentials bằng filter tĩnh.
- [ ] Tôi không dùng header do client điều khiển làm bằng chứng xác thực, phân quyền hoặc khóa rate limit đáng tin cậy.
- [ ] Tôi đã kiểm tra tương thích phiên bản Gateway, service discovery, retry/circuit breaker và đường truyền TLS khi các tính năng đó được bật.

## Tài liệu tham khảo chính thức

- [Spring Cloud Gateway Reference](https://docs.spring.io/spring-cloud-gateway/reference/) — tìm các mục **AddRequestHeader GatewayFilter Factory**, **SetRequestHeader GatewayFilter Factory**, **RemoveRequestHeader** và **Global Filters** theo **đúng phiên bản Gateway**.
- [Spring Cloud Gateway project](https://spring.io/projects/spring-cloud-gateway) — phiên bản dự án và liên kết tài liệu.
- [Spring Framework — HttpHeaders](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/http/HttpHeaders.html) — mô hình header đa giá trị và các thao tác `add`/`set`.
- [Spring Framework WebFlux Reference](https://docs.spring.io/spring-framework/reference/web/webflux.html) — `ServerWebExchange`, request mutation và pipeline HTTP.
- [RFC 9110: HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110) — quy tắc chung về tên, giá trị và semantics của HTTP fields.

**Ghi nhớ:** `AddRequestHeader` **bổ sung giá trị** và có thể để lại nhiều giá trị cho cùng một tên header; `SetRequestHeader` **ghi đè toàn bộ giá trị** để downstream nhận giá trị mà Gateway đã đặt. Lựa chọn đúng cần dựa trên hợp đồng HTTP của backend, thứ tự filter và ranh giới tin cậy của dữ liệu do client gửi.
