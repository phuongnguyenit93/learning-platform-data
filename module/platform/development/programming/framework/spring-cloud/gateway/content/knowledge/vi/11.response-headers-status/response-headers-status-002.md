# RemoveResponseHeader và loại bỏ thông tin triển khai trong Spring Cloud Gateway

Một API Gateway có thể vô tình trả về những HTTP response header tiết lộ tên framework, reverse proxy, runtime, phiên bản dịch vụ hoặc cấu trúc hạ tầng nội bộ. Ví dụ, downstream trả `X-Powered-By: Express` hoặc `X-Backend-Version: catalog-2027.06`; dù client chỉ cần kết quả JSON, những header đó vẫn có thể đi qua Gateway đến Internet.

Trong **SPRING_CLOUD_GATEWAY**, `RemoveResponseHeader` là một **GatewayFilter Factory** dùng để **xóa một tên header và tất cả giá trị của nó khỏi HTTP response** trên những route áp dụng filter. Bài học thuộc chương **Header và trạng thái**, hướng dẫn cách cấu hình đúng, phân biệt header request/response, xác định phạm vi xóa, xử lý tương tác giữa filter chain và commit response, kiểm thử các lớp proxy, cũng như tránh xóa nhầm những header quan trọng cho HTTP, xác thực, cache, CORS hoặc TLS.

> **Phạm vi ví dụ:** Các đoạn cấu hình bên dưới hướng đến **Spring Cloud Gateway Server WebFlux**, theo cú pháp `spring.cloud.gateway.routes` thường gặp ở một số dòng Gateway 4.x. Gateway Server MVC và các dòng phát hành mới có thể dùng namespace, starter hoặc API khác; trước khi áp dụng, đối chiếu phiên bản Gateway và Spring Cloud release train thực tế.

## 1. Vì sao response header có thể làm lộ thông tin triển khai?

HTTP response gồm **status line**, **headers** và (nếu có) **body**:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Server: catalog-api/2.8
X-Powered-By: ExampleFramework
X-Backend-Version: 2.8.7
X-Request-Id: 72bcf824

{"id":42,"name":"Notebook"}
~~~

Trong ví dụ giả định này, `Content-Type` cần cho client đọc JSON và `X-Request-Id` có thể hữu ích để báo lỗi. Ngược lại, `Server`, `X-Powered-By` hoặc `X-Backend-Version` có thể tiết lộ chi tiết triển khai mà hợp đồng API không cần công bố.

**Việc loại bỏ thông tin triển khai là một biện pháp giảm bề mặt tiết lộ thông tin**, không phải một giải pháp bảo mật toàn diện. Ngay cả khi các header bị xóa, client vẫn có thể suy đoán công nghệ từ hành vi giao thức, thông báo lỗi hoặc đặc điểm phản hồi. Vì vậy vẫn phải vá lỗ hổng, cập nhật dependency, cấu hình TLS, thực hiện xác thực/phân quyền và theo dõi hệ thống.

### Nhóm header cần đánh giá

| Header | Dữ liệu có thể lộ | Hành động cần cân nhắc |
|---|---|---|
| `Server` | Tên server, phần mềm hoặc phiên bản nếu được khai báo | Xóa/giảm chi tiết khi chính sách không cần công bố; kiểm tra cả server Gateway và proxy ngoài |
| `X-Powered-By` | Framework/runtime phía downstream | Thường có thể xóa nếu không thuộc hợp đồng API |
| `X-Backend-Version`, `X-App-Version` | Phiên bản triển khai backend, build ID | Ưu tiên giữ trong hệ thống quan sát nội bộ nếu cần, không tự động công khai |
| `X-Backend-Host`, `X-Node-Name` | Hostname hoặc topology nội bộ | Không để lộ nếu không có nhu cầu nghiệp vụ |
| `X-Generator` | Công cụ tạo nội dung hoặc framework | Đánh giá nhu cầu khách hàng trước khi công bố |
| `Via`, `X-Cache`, `X-Envoy-Upstream-Service-Time` | Một phần đường đi qua proxy/cache | Xét theo tiêu chuẩn, yêu cầu proxy, debugging và hợp đồng hạ tầng; **không xóa tùy tiện** |
| `X-Request-Id`, `traceparent` | Mã liên kết request/tracing | Có thể hữu ích cho hỗ trợ vận hành; cân nhắc định dạng và khả năng tiết lộ dữ liệu |
| `X-RateLimit-*`, `RateLimit-*` | Chính sách hoặc số liệu giới hạn lưu lượng | Có thể là một phần hợp đồng API; quyết định theo chính sách công khai |

**Danh sách trên là các ví dụ cần đánh giá**, không phải danh sách phải xóa hết. Tính hữu ích và yêu cầu giữ lại từng header phụ thuộc môi trường, tiêu chuẩn HTTP, proxy/CDN và hợp đồng của API.

## 2. `RemoveResponseHeader` làm chính xác điều gì?

Filter nhận **một tên HTTP header** cần xóa khỏi response. Nếu header đó xuất hiện với nhiều giá trị, thao tác xóa theo tên sẽ loại **toàn bộ danh sách giá trị** của tên đó, thay vì chỉ một giá trị cụ thể.

~~~text
Response từ backend:
  X-Powered-By -> ["Framework-A", "Plugin-B"]
  Content-Type -> ["application/json"]

Sau RemoveResponseHeader=X-Powered-By:
  X-Powered-By -> (không còn)
  Content-Type -> ["application/json"]
~~~

Đặc tính cần nhớ:

- Tên header HTTP **không phân biệt chữ hoa/chữ thường**: `Server`, `server`, `SERVER` chỉ cùng một tên về mặt ngữ nghĩa.
- Filter **xóa** header được chỉ định; nó không đổi tên, che một phần giá trị hoặc mặc định thay bằng chuỗi rỗng.
- Filter thao tác **response trả về client**, không phải request gửi đến downstream.
- Filter **không đổi HTTP status** hay body. `200`, `404`, `503` vẫn là status theo pipeline hiện tại, trừ khi thành phần khác chỉnh.
- Một filter `RemoveResponseHeader` được cấu hình cho **một tên header**; muốn xóa nhiều tên khác nhau thì khai báo nhiều phần tử filter.
- Nếu header không tồn tại, việc xóa theo tên không cần tạo header mới hoặc thay đổi các header còn lại.

So sánh với các factory liên quan:

| Factory | Phần HTTP bị tác động | Hiệu ứng |
|---|---|---|
| `RemoveRequestHeader` | Request Gateway → backend | Xóa header trước khi forward |
| `RemoveResponseHeader` | Response backend/Gateway → client, trong phạm vi route áp dụng | Xóa toàn bộ giá trị của tên header |
| `SetResponseHeader` | Response | Đặt/thay giá trị của tên header |
| `AddResponseHeader` | Response | Bổ sung một giá trị, có thể tạo nhiều giá trị |
| `DedupeResponseHeader` | Response | Giảm giá trị trùng theo chiến lược được factory hỗ trợ |
| `SetStatus` | Response status | Chỉnh mã trạng thái theo cấu hình riêng, **khác** xóa header |

## 3. Cấu hình cú pháp rút gọn

Giả định dịch vụ catalog đang chạy tại `http://localhost:9090`; Gateway nhận request `/api/catalog/**`, bỏ phân đoạn `api` rồi forward về catalog.

~~~yaml
spring:
  cloud:
    gateway:
      routes:
        - id: catalog-api
          uri: http://localhost:9090
          predicates:
            - Path=/api/catalog/**
          filters:
            - StripPrefix=1
            - RemoveResponseHeader=X-Powered-By
            - RemoveResponseHeader=X-Backend-Version
~~~

Cú pháp tổng quát:

~~~text
- RemoveResponseHeader=<header-name>
~~~

Ví dụ, backend trả:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
X-Powered-By: CatalogFramework
X-Backend-Version: 2.8.7
X-Request-Id: 72bcf824
~~~

Sau khi request đã match route và filter chạy thành công **trước khi response commit**, client dự kiến nhận:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
X-Request-Id: 72bcf824
~~~

Đây là **phần header minh họa**, không phải toàn bộ response thực tế. Gateway, Netty, reverse proxy hoặc CDN có thể thêm header khác; kết quả phải xác minh tại điểm truy cập của client.

### Khi nào nên dùng `Server`?

Bạn có thể thêm:

~~~yaml
filters:
  - RemoveResponseHeader=Server
  - RemoveResponseHeader=X-Powered-By
~~~

Trong route tương ứng, cấu hình nhằm xóa `Server` và `X-Powered-By` nếu chúng đã xuất hiện trong response ở giai đoạn filter can thiệp. **Không cam kết rằng header `Server` sẽ biến mất khỏi response cuối trên Internet**: chính HTTP server của Gateway, reverse proxy, ingress hoặc CDN có thể tự chèn `Server` tại một tầng sau đó. Cần kiểm tra cả các tầng ngoài Gateway và cấu hình giảm header quảng bá phiên bản ở từng tầng.

## 4. Cú pháp đầy đủ với `name` và `args`

Cùng một ý định được viết tường minh:

~~~yaml
spring:
  cloud:
    gateway:
      routes:
        - id: catalog-api
          uri: http://localhost:9090
          predicates:
            - Path=/api/catalog/**
          filters:
            - name: RemoveResponseHeader
              args:
                name: X-Powered-By
            - name: RemoveResponseHeader
              args:
                name: X-Backend-Version
~~~

Ở đây:

- `filters[0].name` chọn **GatewayFilter Factory** tên `RemoveResponseHeader`.
- `filters[0].args.name` là **tên HTTP header** cần xóa, ví dụ `X-Powered-By`.
- `filters[1]` là một khai báo filter độc lập xóa tên `X-Backend-Version`.

Hai cách **shortcut** và **expanded** có thể tạo ra hành vi tương đương nếu dùng đúng tên factory và tham số trong cùng phiên bản.

| Kiểu | Ví dụ | Khi nên chọn |
|---|---|---|
| Rút gọn | `RemoveResponseHeader=X-Powered-By` | Tên header ngắn, cấu hình đơn giản |
| Đầy đủ | `name: RemoveResponseHeader` + `args.name: X-Powered-By` | Cần công khai cấu trúc, code review hoặc thống nhất quy ước YAML |

**Lỗi dễ gặp:** Không đặt `args.header` hoặc `args.value` theo suy đoán từ những factory khác. Ở các phiên bản dùng cấu hình minh họa, trường tên header của `RemoveResponseHeader` là **`name`**.

## 5. Đặt filter trên từng route hay cấu hình `default-filters`?

### Filter riêng cho một route

Một số dịch vụ cần công khai phiên bản để hỗ trợ client, dịch vụ khác cần giấu hoàn toàn. Khi chính sách khác nhau theo tuyến, cấu hình `RemoveResponseHeader` **trên chính route** phù hợp hơn:

~~~yaml
spring:
  cloud:
    gateway:
      routes:
        - id: catalog-private-metadata
          uri: http://localhost:9090
          predicates:
            - Path=/api/catalog/**
          filters:
            - StripPrefix=1
            - RemoveResponseHeader=X-Backend-Version

        - id: public-status
          uri: http://localhost:9091
          predicates:
            - Path=/api/status/**
          filters:
            - StripPrefix=1
~~~

Trong ví dụ, chỉ route `catalog-private-metadata` có filter xóa `X-Backend-Version`. Route `public-status` không bị xóa bởi **filter cụ thể đó**, nhưng vẫn có thể chịu tác động của các filter chung hoặc proxy bên ngoài.

### Filter mặc định cho các route

Nếu muốn áp dụng cùng chính sách cho nhiều route được Gateway cấu hình, ở những dòng WebFlux hỗ trợ thuộc tính này có thể dùng `default-filters`:

~~~yaml
spring:
  cloud:
    gateway:
      default-filters:
        - RemoveResponseHeader=X-Powered-By
        - RemoveResponseHeader=X-Backend-Version
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

`default-filters` được ghép vào các route theo cơ chế của phiên bản Gateway tương ứng. Đây là cách giảm lặp nếu các dịch vụ có cùng yêu cầu, nhưng **không nên hiểu nó bao phủ tất cả HTTP response do web server tạo ra**. Nếu request không match bất kỳ Gateway route nào, hoặc bị Spring Security từ chối ở lớp WebFlux trước bước lựa chọn route, filter route/default này có thể **không chạy**.

**Phân biệt phạm vi:**

| Vị trí | Phạm vi tác dụng thông thường | Có bao phủ 404 không match route? |
|---|---|---|
| `filters` trong route | Request đã chọn route ấy | Không |
| `default-filters` | Các route được áp dụng default filters | Không bảo đảm |
| `GlobalFilter` Gateway | Chuỗi xử lý của route Gateway đã chọn | Không bảo đảm |
| `WebFilter` phù hợp trong WebFlux | Tầng HTTP của ứng dụng, theo thứ tự web filters | Có thể, nếu chạy trước thành phần sinh response đó |
| Reverse proxy/ingress/CDN | Các response đi qua tầng proxy, theo cấu hình | Tùy nơi có chặn/gửi response và chính sách proxy |

Chọn tầng cấu hình theo **phạm vi mà chính sách đòi hỏi**, không chỉ theo số dòng YAML ngắn nhất.

## 6. Thời điểm xóa header và response commit

Header phải được xóa **trước khi HTTP response được commit** để ảnh hưởng đến dữ liệu client thực nhận. Sau khi status và headers được gửi đi, thay đổi chúng thường không còn tác dụng.

Một luồng khái niệm Gateway Server WebFlux:

~~~mermaid
sequenceDiagram
    participant C as Client
    participant G as Gateway
    participant S as Catalog service
    participant P as Reverse proxy / CDN
    C->>G: GET /api/catalog/42
    G->>S: Forward GET /catalog/42
    S-->>G: 200 + Server / X-Powered-By / Content-Type
    Note over G: GatewayFilter response xóa tên header trước commit
    G-->>P: 200 + Content-Type, không còn header bị xóa ở tầng Gateway
    Note over P: Proxy có thể thêm header của chính nó
    P-->>C: Response cuối cùng
~~~

Trong ứng dụng thực tế, response của downstream được Gateway đọc, các bước post-filter và routing response phối hợp quyết định khi nào headers được ghi. **Không nên suy ra chỉ từ vị trí các dòng YAML rằng filter đã can thiệp đúng lúc** nếu có filter tùy biến, body streaming hoặc response được commit sớm. Hãy kiểm chứng bằng request thật và log khi cần.

### Nếu có filter khác thêm lại cùng header

Ví dụ minh họa:

~~~yaml
filters:
  - AddResponseHeader=X-Backend-Version,unknown
  - RemoveResponseHeader=X-Backend-Version
~~~

Ý định là thêm rồi xóa cùng một header. Tuy nhiên, thứ tự thực thi cuối cùng phụ thuộc filter order, default/global filters và thời điểm post-processing; **không nên dùng cặp cấu hình tự mâu thuẫn này trong production**. Nếu mục tiêu là giấu version, bỏ nguồn tạo header hoặc áp dụng chính sách xóa tại một tầng có quyền kiểm soát response trước khi commit.

Trường hợp ngược lại cũng có thể xảy ra: một GatewayFilter đã xóa header do backend đưa về, nhưng reverse proxy **sau Gateway** lại đặt `Server` của chính proxy. Không có thay đổi nào trong route filter có thể chặn header được tạo **sau khi response rời Gateway**.

### Streaming và response lỗi

Khi downstream gửi file lớn hoặc **Server-Sent Events (SSE)**, response headers có thể commit ngay trước chunk đầu tiên dù stream tiếp tục nhiều phút. Filter cần được áp dụng vào đúng chu kỳ xử lý response **trước commit**. Việc đợi stream hoàn tất để xóa header chắc chắn quá muộn.

Khi fallback/circuit breaker hoặc error handler tạo response thay thế, header có thể đến từ **Gateway hoặc fallback service**, thay vì backend gốc. Kiểm tra nhánh phát sinh response thật, nhất là với `401`, `403`, `429`, `503`, redirect và lỗi TLS/downstream.

## 7. Xóa thông tin triển khai khác với xóa header bảo mật

Không nên dùng `RemoveResponseHeader` như một danh sách chặn tất cả header “có vẻ kỹ thuật”. Nhiều header quyết định giao thức, an toàn và chức năng phía client.

| Header hoặc nhóm | Vì sao cần cân nhắc giữ lại |
|---|---|
| `Content-Type` | Client cần biết kiểu dữ liệu (JSON, HTML, file, SSE) |
| `Content-Length`, `Transfer-Encoding`, `Content-Encoding` | Liên quan framing/compression; chỉnh sai có thể làm client đọc hỏng response |
| `Cache-Control`, `ETag`, `Last-Modified`, `Vary` | Điều khiển cache, revalidation và cách cache phân biệt response |
| `Location` | Cần cho redirect `3xx` và một số response tạo tài nguyên |
| `WWW-Authenticate` | Có ý nghĩa trong các tình huống xác thực, đặc biệt response `401` |
| `Access-Control-Allow-Origin`, các header CORS khác | Browser cần chúng để thực hiện chính sách CORS |
| `Strict-Transport-Security` | HSTS giúp client ưu tiên HTTPS theo chính sách đã triển khai |
| `Content-Security-Policy`, `X-Content-Type-Options` | Bảo vệ trình duyệt trước một số loại rủi ro |
| `Set-Cookie` | Có thể phục vụ session; xóa sẽ thay đổi cách client duy trì trạng thái |
| `Retry-After`, `RateLimit-*` | Có thể cần cho retry, backoff và hành vi rate limiting của client |

**Nguyên tắc:** chỉ loại bỏ header **đã được phân loại** là không cần thiết hoặc nhạy cảm và có chủ sở hữu chính sách rõ ràng. Xóa `Server`/`X-Powered-By` thường dễ giải thích hơn việc xóa `Cache-Control`, CORS hoặc header bảo mật.

Đặc biệt, khi làm việc với response `401`, `403` và `429`, một số header có thể là phần cần thiết của hợp đồng giao tiếp. Nếu xóa `WWW-Authenticate` hoặc `Retry-After` thiếu chủ đích, client sẽ khó xác định cơ chế xác thực hoặc thời gian chờ trước khi retry.

## 8. CORS, cookies và các phản hồi do Gateway tự tạo

### CORS preflight

Một browser có thể gửi `OPTIONS` trước request thật. Tùy cấu hình CORS ở Gateway và tầng WebFlux, preflight có thể được xử lý **trước khi một route thông thường được chọn**. Nếu filter `RemoveResponseHeader` chỉ đặt trên route, nó có thể không chạy cho preflight.

Không dùng `RemoveResponseHeader=Access-Control-Allow-Origin` như một cách cấu hình bảo mật CORS. Hãy xác định chính sách CORS từ nguồn đáng tin cậy, giới hạn origin/method/headers hợp lệ, rồi kiểm tra response preflight và request thật.

### Response do Spring Security tạo

Spring Security có thể trả `401` hoặc `403` **trước khi Gateway chọn route**. Route filter không nhất thiết được thực thi. Nếu chính sách yêu cầu xóa `Server`/`X-Powered-By` khỏi **mọi response**, cần xem xét tầng bao trùm như web server/proxy hoặc `WebFilter` đăng ký đủ sớm.

### Cookie và session

Không xóa `Set-Cookie` chỉ vì header chứa một số thông tin triển khai. Nếu cookie thực sự không cần thiết, nên **loại bỏ tại nguồn tạo cookie** hoặc cấu hình session phù hợp. Với cookie cần thiết, kiểm tra `Secure`, `HttpOnly`, `SameSite`, domain/path và TLS. Xóa header mù quáng có thể gây lỗi đăng nhập khó chẩn đoán.

### HTTP error body

Ngay cả khi xóa header version, response body có thể chứa stack trace, tên class, hostname hoặc URI nội bộ:

~~~json
{
  "error": "Downstream exception",
  "detail": "com.example.catalog.internal.CatalogServiceException"
}
~~~

`RemoveResponseHeader` **không sửa JSON body**. Muốn giảm lộ thông tin triển khai trong body, cần xử lý exception và cấu trúc lỗi ở backend hoặc Gateway bằng cơ chế thích hợp; luôn giữ mã lỗi/correlation ID có ích cho điều tra nội bộ.

## 9. Nếu phải bao phủ cả response không đi qua Gateway route

Với Spring Cloud Gateway Server WebFlux, có thể triển khai một `WebFilter` bao trùm hơn để xử lý response của ứng dụng WebFlux, bao gồm một số response không match Gateway route. Ví dụ minh họa:

~~~java
package example.gateway;

import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;
import org.springframework.http.server.reactive.ServerHttpResponse;
import org.springframework.stereotype.Component;
import org.springframework.web.server.ServerWebExchange;
import org.springframework.web.server.WebFilter;
import org.springframework.web.server.WebFilterChain;
import reactor.core.publisher.Mono;

@Component
@Order(Ordered.HIGHEST_PRECEDENCE)
public class ResponseImplementationHeaderFilter implements WebFilter {

    @Override
    public Mono<Void> filter(ServerWebExchange exchange, WebFilterChain chain) {
        ServerHttpResponse response = exchange.getResponse();

        response.beforeCommit(() -> Mono.defer(() -> {
            response.getHeaders().remove("X-Powered-By");
            response.getHeaders().remove("X-Backend-Version");
            return Mono.empty();
        }));

        return chain.filter(exchange);
    }
}
~~~

Đoạn code có các đặc điểm:

- Đây là **`WebFilter` của Spring WebFlux**, khác với `GatewayFilter` và `GlobalFilter` của Spring Cloud Gateway.
- Callback `beforeCommit` được đăng ký **trước `chain.filter(exchange)`**, để xử lý khi response đang chuẩn bị commit.
- `Mono.defer` trì hoãn side effect đến thời điểm publisher được thực thi.
- Không thực hiện I/O chặn luồng hoặc gọi dịch vụ khác trong callback.
- `@Order(Ordered.HIGHEST_PRECEDENCE)` thể hiện chủ đích đăng ký sớm; cần kiểm tra thứ tự filter thật và thành phần security/error handler trong ứng dụng.

Đây là **một phương án mở rộng khi cần**, không bắt buộc nếu chỉ cần xóa header trên vài route. Nó cũng không thể xóa header do reverse proxy/CDN thêm **sau Gateway**, hoặc header do tầng transport thêm sau khi các callback đã chạy. Với production, nên so sánh phương án loại bỏ header **ngay tại nguồn** hoặc áp dụng chính sách ở **tầng edge cuối cùng**.

## 10. Tương tác với gateway filters, routing và hạ tầng

Trong gateway thực tế, response có thể đi qua nhiều tầng. Khi một header biến mất ở môi trường local nhưng xuất hiện lại ở production, hãy xác định **ai tạo nó** và **tầng nào chạy sau bước xóa**.

~~~mermaid
flowchart LR
    A["Service backend"] --> B["Spring Cloud Gateway route"]
    B --> C["Web server Gateway"]
    C --> D["Ingress / Reverse proxy"]
    D --> E["CDN / Edge"]
    E --> F["Client"]
    B -.->|RemoveResponseHeader tại Gateway| C
    D -.->|Proxy có thể thêm headers| E
~~~

Sơ đồ chỉ minh họa các tầng có thể có; request thật không nhất thiết sử dụng đủ tất cả. Ngoài ra, Gateway có thể đứng **sau** ingress ở chiều request, nhưng response vẫn đi **từ Gateway trở lại qua ingress** trước khi tới client.

| Thành phần | Điều cần xem xét khi xóa header |
|---|---|
| Route predicates | Filter chỉ áp dụng nếu route được chọn; `Path`/`Host`/`Method` không khớp thì route filter không chạy |
| Path rewrite và request headers | Thực hiện ở chiều request; không đồng nghĩa với xóa response header |
| Service discovery / `lb://` | Downstream instance khác nhau có thể sinh bộ headers khác nhau |
| Default/Global filters | Có thể cùng sửa response headers và ảnh hưởng thứ tự/giá trị cuối |
| Circuit breaker, retry, fallback | Response có thể được sinh bởi backend khác hoặc Gateway sau nhiều lần thử |
| Rate limiting | Response `429` có thể được tạo sớm, trước khi gọi downstream |
| Authentication/authorization | Response `401`/`403` có thể phát sinh trước khi Gateway chọn route |
| TLS | Bảo vệ đường truyền trên từng chặng; xóa header không thay được HTTPS hay certificate validation |
| Tracing/observability | Cân nhắc giữ correlation ID hữu ích, nhưng tránh lộ hostname, PII và token |
| Ingress/CDN | Có thể bổ sung header sau khi Gateway đã xóa |

**Không nên che giấu các header mà hệ thống quan sát hoặc API client đang phụ thuộc** mà chưa có phương án thay thế. Ví dụ, nếu client cần `Retry-After` sau rate limiting, xóa toàn bộ nhóm header “liên quan hạ tầng” có thể khiến client retry liên tục.

## 11. Thực hành: chứng minh filter đã xóa đúng header

### Chuẩn bị môi trường

Giả định có:

- **Gateway Server WebFlux** lắng nghe `http://localhost:8080`.
- **Backend giả lập** lắng nghe `http://localhost:9090` với endpoint `GET /catalog/items`.
- Backend trả các header test `X-Powered-By: DemoFramework`, `X-Backend-Version: 2.8.7`, `X-Request-Id: test-42`, `Content-Type: application/json`.

Cấu hình Gateway ở phần 3 sẽ map `GET /api/catalog/items` thành `GET /catalog/items` ở backend. Có thể dùng backend echo hoặc mock HTTP server tùy môi trường; endpoint này là **giả định cho thực hành**, không phải endpoint có sẵn của Gateway.

### Bước 1 — Đọc response trực tiếp từ backend

~~~bash
curl -i http://localhost:9090/catalog/items
~~~

Xác nhận backend thực sự gửi `X-Powered-By` và `X-Backend-Version`. Nếu backend chưa gửi hai header này, việc Gateway không trả chúng **chưa chứng minh filter đã xóa đúng**.

### Bước 2 — Gọi qua Gateway

~~~bash
curl -i http://localhost:8080/api/catalog/items
~~~

Ở PowerShell nơi `curl` là alias của lệnh khác, dùng `curl.exe -i` để nhận đúng hành vi cURL.

Kỳ vọng:

| Header/mã | Backend trực tiếp | Qua Gateway | Diễn giải |
|---|---|---|---|
| `X-Powered-By` | Có | Không còn do filter | Đã loại tên header |
| `X-Backend-Version` | Có | Không còn do filter | Đã loại thông tin version |
| `Content-Type` | `application/json` | Vẫn phù hợp response | Không ảnh hưởng việc parse body |
| `X-Request-Id` | `test-42` | Còn nếu không bị thành phần khác sửa | Hỗ trợ chẩn đoán |
| Status `200` | `200` | `200` nếu không có thành phần khác đổi | Filter không sửa status |

Sau đó thử backend trả `404` có cùng hai header. Với request đã match **Gateway route**, filter vẫn có thể xóa các header đó trên response lỗi do downstream tạo. Đừng nhầm HTTP `404` **từ downstream** với HTTP `404` **do Gateway không tìm thấy route**; chỉ trường hợp đầu chắc chắn đã đi qua route này theo giả định.

### Bước 3 — Kiểm thử response nhiều giá trị

Cho backend trả `X-Powered-By` với hai giá trị (nếu server test cho phép) và gọi qua Gateway. Xác nhận **không còn bất kỳ giá trị nào** cho tên `X-Powered-By`. Đây là khác biệt giữa xóa cả header và chỉnh một giá trị.

### Bước 4 — Thử request không khớp

~~~bash
curl -i http://localhost:8080/does-not-exist
~~~

Nếu ứng dụng không có handler/route cho path này, thường nhận `404`. **Không giả định** các filter trên route `catalog-api` đã được thực thi. Để kiểm tra chính sách xóa trên mọi response, cần thực hiện phép thử này với tầng bao trùm hơn như `WebFilter`/web server/edge proxy.

### Bước 5 — Kiểm tra qua ingress và domain thật

Sau khi thử ở cổng Gateway, kiểm tra đường truy cập thực tế qua proxy/CDN hoặc ingress:

~~~bash
curl -i https://api.example.test/api/catalog/items
~~~

Tên miền trên chỉ để minh họa, hãy thay bằng domain kiểm thử hợp lệ do nhóm quản lý. So sánh tập header **trực tiếp Gateway** và **từ Internet/điểm truy cập client**. Nếu `Server` vẫn có mặt ở lớp ngoài, cần xác minh proxy/CDN đã thêm nó hay không; không kết luận `RemoveResponseHeader` thất bại chỉ từ một kết quả cuối.

### Bước 6 — Kiểm tra nhánh lỗi và streaming

Thực hiện thêm các trường hợp có ý nghĩa với dự án:

- Backend trả `401`, `403`, `429` hoặc `503`; kiểm tra header nhạy cảm bị xóa mà header hợp đồng API cần thiết vẫn tồn tại.
- Circuit breaker/fallback trả response từ backend khác hoặc Gateway; so sánh bộ header tương ứng.
- Endpoint streaming/SSE nếu có; header phải bị xóa **trước khi chunk đầu đến client**.
- Service discovery trả các instance khác nhau; mỗi instance backend có thể sinh header khác nhau.

Ghi **route ID, status, bộ header trước/sau và instance Gateway** khi thử trong cụm nhiều node. Không ghi token, cookie hoặc dữ liệu cá nhân nguyên văn vào log.

## 12. Debug khi header vẫn còn xuất hiện

| Triệu chứng | Khả năng cần kiểm tra | Cách xử lý |
|---|---|---|
| Header vẫn tồn tại qua route Gateway | Sai tên factory/field, route không match, filter không được nạp | Kiểm tra `RouteDefinition`, startup log, version và đường đi request |
| Header còn trên một số route | Chỉ cấu hình `filters` ở một route | Áp dụng cho các route còn lại hoặc `default-filters` nếu chính sách thống nhất |
| `Server` vẫn còn ở public domain | Server Gateway/ingress/CDN chèn sau điểm xóa | So sánh từng hop, cấu hình tầng thêm header |
| 404 không match vẫn có header | Route filter không chạy khi không có route | Xử lý bằng tầng HTTP/edge bao trùm |
| 401/403 do Spring Security vẫn có header | Security chặn request trước Gateway filter | Kiểm tra thứ tự `WebFilter` và chính sách tại web server/proxy |
| Header biến mất trên 200 nhưng xuất hiện trên fallback | Response từ nhánh khác hoặc filter bị bỏ qua/ghi đè | Kiểm tra circuit breaker, fallback URI và filter chain |
| Header mới lại xuất hiện sau deploy | Bản cũ trên một số instance; default/global filter hoặc proxy thêm lại | Kiểm tra rollout, cache, config và các gateway node |
| CORS bị lỗi sau khi xóa header | Xóa nhầm `Access-Control-Allow-*` hoặc `Vary` | Phục hồi header hợp đồng, sửa chính sách CORS tại nguồn |
| Client không đăng nhập được | Xóa `Set-Cookie` hoặc `WWW-Authenticate` | Phục hồi cơ chế session/auth phù hợp |
| Response nén hoặc tải file lỗi | Xóa header giao thức như `Content-Encoding`/`Content-Length` | Tránh generic remove với framing header; để HTTP stack quản lý |

**Quy trình khoanh vùng:** xác nhận backend **có phát header** → Gateway **đã chọn đúng route** → filter **được nạp và chạy trước commit** → header **không bị thêm lại sau Gateway**. Đồng thời so sánh HTTP status/body để phát hiện request thực ra đang đi sang nhánh fallback khác.

## 13. Checklist trước khi áp dụng chính sách xóa header

- [ ] Tôi xác định được header nào thật sự không cần công khai và ai là nguồn tạo ra nó.
- [ ] Tôi phân biệt `RemoveResponseHeader` với `RemoveRequestHeader`, `SetResponseHeader` và `SetStatus`.
- [ ] Tôi đã chọn đúng phiên bản và biến thể Gateway, namespace YAML và tên factory.
- [ ] Tôi biết mỗi `RemoveResponseHeader` xóa một tên header cùng **mọi giá trị** của nó.
- [ ] Tôi kiểm tra sự khác nhau giữa filter riêng route, `default-filters`, `GlobalFilter` và `WebFilter`.
- [ ] Tôi đã xét response `404` không match route và `401/403` do Spring Security tạo sớm.
- [ ] Tôi hiểu vì sao chỉnh response headers phải diễn ra trước lúc commit, đặc biệt với streaming.
- [ ] Tôi không xóa những header bảo mật, CORS, cache, xác thực hoặc framing mà client đang cần.
- [ ] Tôi đã kiểm thử backend trực tiếp, Gateway trực tiếp và đường truy cập qua ingress/CDN.
- [ ] Tôi đã thử response 2xx và các lỗi có liên quan, kể cả fallback/retry/rate limiting nếu được bật.
- [ ] Tôi đã kiểm tra `Server` có được thêm lại ở tầng proxy ngoài Gateway hay không.
- [ ] Tôi vẫn quản lý TLS, xác thực, cập nhật dependency, giới hạn lưu lượng và observability như các chính sách độc lập.
- [ ] Tôi có ghi nhận cấu hình và kết quả kiểm thử để lần nâng cấp Gateway tiếp theo có thể kiểm tra lại.

## Tài liệu tham khảo chính thức

- [Spring Cloud Gateway Reference](https://docs.spring.io/spring-cloud-gateway/reference/) — tìm mục **RemoveResponseHeader GatewayFilter Factory** và các mục về default filters, global filters, response handling đúng **phiên bản Gateway**.
- [Spring Cloud Gateway project](https://spring.io/projects/spring-cloud-gateway) — thông tin release train liên quan và điểm vào tài liệu dự án.
- [Spring Framework — HttpHeaders](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/http/HttpHeaders.html) — API quản lý header và thao tác `remove` theo tên.
- [Spring Framework — ServerHttpResponse](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/http/server/reactive/ServerHttpResponse.html) — vòng đời commit response và `beforeCommit`.
- [RFC 9110: HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110) — ý nghĩa trường HTTP, trạng thái phản hồi và những ràng buộc giao thức.

**Ghi nhớ:** `RemoveResponseHeader` giúp Gateway **xóa một tên response header và mọi giá trị của nó trên những route áp dụng**, thích hợp để hạn chế lộ `X-Powered-By`, phiên bản hoặc hostname backend không cần công khai. Để chính sách thực sự hiệu lực, phải xác nhận phạm vi filter, thời điểm commit, phản hồi lỗi và những tầng proxy có thể bổ sung header sau Gateway; đồng thời bảo toàn các header mà HTTP client và hệ thống bảo mật đang cần.
