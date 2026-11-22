# 404 do sai route, context path hoặc đường dẫn sau proxy

Một API trả `404 Not Found` không nhất thiết có nghĩa bản ghi cần tìm đã bị xóa. Client có thể gửi đúng ID nhưng sai tiền tố `/api`; ứng dụng Spring Boot có thể chạy dưới `server.servlet.context-path` mà gateway không biết; hoặc reverse proxy có thể âm thầm bỏ hay thêm một đoạn path khi chuyển tiếp. Cùng một request, gọi trực tiếp vào service thì thành công nhưng qua tên miền công khai lại 404.

Trong mô-đun **INTEGRATION_API_REST**, người học thiết kế REST API dựa trên resource, URI, HTTP method, status code và hợp đồng dữ liệu. Chương **Chẩn đoán sự cố** yêu cầu sử dụng chính hợp đồng ấy để khoanh vùng lỗi, thay vì sửa ngẫu nhiên annotation hoặc thêm redirect. Bài này xây quy trình điều tra **404 do sai route, context path hoặc đường dẫn sau proxy** với Java/Spring Boot 3, Spring MVC, Nginx và Kubernetes Ingress. Các ví dụ có thể điều chỉnh cho WebFlux hoặc gateway khác, nhưng cơ chế định tuyến của từng sản phẩm cần được đối chiếu riêng.

## 1. Mục tiêu học tập

Sau bài học, người học có thể:

1. Phân biệt 404 do **gateway/ingress không chọn được upstream**, 404 do **Spring không khớp handler**, và 404 do **resource nghiệp vụ không tồn tại hoặc bị che theo chính sách bảo mật**.
2. Tính được đường dẫn request thực tế từ **public path → proxy rewrite → servlet context path → controller mapping**.
3. Nhận diện lỗi của `server.servlet.context-path`, `spring.mvc.servlet.path`, `@RequestMapping`, prefix, version, dấu slash cuối và quy tắc encode URI.
4. Giải thích khác biệt giữa `proxy_pass` có và không có URI kết thúc bằng `/` trong Nginx, cũng như tác động của ingress rewrite.
5. Sử dụng `curl`, log, trace, Actuator mappings và kiểm thử MockMvc/HTTP integration để xác định **tầng đầu tiên** xuất hiện 404.
6. Khắc phục lỗi mà không vô tình thay đổi hợp đồng API, bỏ qua xác thực/phân quyền hoặc tạo redirect nguy hiểm cho request ghi.

**Nguyên tắc quan trọng:** đừng kết luận “database không có record” chỉ từ mã 404. Trước tiên phải trả lời **404 được tạo ở tầng nào và tầng đó đã nhìn thấy đường dẫn nào?**

## 2. Một URL đi qua nhiều ranh giới định tuyến

Giả sử client gọi:

~~~http
GET /api/v1/orders/8c9b4ca4-2211-4cd0-a949-d176bcb8e35f HTTP/1.1
Host: api.example.test
Authorization: Bearer <access-token>
Accept: application/json
~~~

Ứng dụng nội bộ được triển khai dưới context path `/orders-service`, nhưng hợp đồng public chỉ có prefix `/api`. Đường đi dự kiến:

~~~mermaid
flowchart LR
    C["Client<br/>/api/v1/orders/42"] --> G["Gateway<br/>rewrite /api/..."]
    G -->|"URI /orders-service/api/v1/orders/42"| S["Servlet container<br/>context /orders-service"]
    S -->|"Handler path /api/v1/orders/42"| M["Spring MVC<br/>@RequestMapping"]
    M --> D["Service / Database"]
~~~

Trong sơ đồ, ID `42` được rút gọn cho dễ đọc; API ví dụ thật dùng UUID. Có thể diễn tả đường đi thành bốn câu hỏi độc lập:

| Bước | Thành phần | Path cần thấy | Nếu sai |
| --- | --- | --- | --- |
| 1 | Client/gateway public | `/api/v1/orders/{id}` | Client ghép sai base URL, prefix hoặc phiên bản |
| 2 | Reverse proxy tới backend | `/orders-service/api/v1/orders/{id}` | Rewrite sai, strip/append prefix hai lần |
| 3 | Servlet container | Context path `/orders-service` | Request nằm ngoài context, chưa tới controller |
| 4 | Spring MVC handler | `/api/v1/orders/{id}` | Annotation/method/trailing slash không khớp |
| 5 | Nghiệp vụ | Đối tượng `id` thuộc phạm vi được xem | 404 nghiệp vụ hoặc 404 chủ ý để che tài nguyên |

Không có quy tắc rằng mọi proxy phải strip prefix hoặc mọi service phải có context path. **Chọn đúng một hợp đồng public và ghi rõ phép biến đổi sang internal path**. Sau đó kiểm tra phép biến đổi trên request thực thay vì đoán từ tên thư mục hoặc tên Kubernetes Service.

### 2.1. Phân biệt URL, URI path, context path, servlet path và handler mapping

Giả sử cấu hình:

~~~yaml
server:
  port: 8080
  servlet:
    context-path: /orders-service
~~~

Controller:

~~~java
@RestController
@RequestMapping("/api/v1/orders")
public class OrderController {
    private final OrderQueryService orders;

    public OrderController(OrderQueryService orders) {
        this.orders = orders;
    }

    @GetMapping("/{id}")
    public ResponseEntity<OrderView> findById(
            @PathVariable UUID id,
            Authentication authentication) {
        return ResponseEntity.ok(
            orders.findVisible(authentication.getName(), id));
    }
}
~~~

`OrderQueryService` và `OrderView` là thành phần ứng dụng giả định. Service phải xác minh chủ sở hữu/tenant và xử lý trạng thái resource không tồn tại. Trong cấu hình này, URL khi gọi **trực tiếp** vào cổng nội bộ là:

~~~text
http://orders-api:8080/orders-service/api/v1/orders/{id}
~~~

Phần `/orders-service` do servlet container nhận diện; Spring MVC đối chiếu `@RequestMapping("/api/v1/orders")` và `@GetMapping("/{id}")` trên path còn lại. Nếu gọi thẳng `http://orders-api:8080/api/v1/orders/{id}`, có thể nhận 404 **trước khi controller chạy**.

Một tiền tố khác là `spring.mvc.servlet.path`, ví dụ `/internal`, áp dụng cho dispatcher servlet của Spring MVC. Nếu dùng đồng thời context path, servlet path và mapping thì cần ghép chính xác từng phần; chúng không đồng nghĩa và có thể có tương tác với cấu hình path matching theo phiên bản Spring. **Đừng đổi cả ba để chữa một 404**. Bắt đầu bằng cấu hình thực tế đang chạy và danh sách mapping được framework đăng ký.

### 2.2. Hợp đồng public khác URL nội bộ là bình thường

Một tài liệu OpenAPI có thể công bố server `https://api.example.test`, resource path `/api/v1/orders/{id}` trong khi backend dùng thêm `/orders-service`. Client **không cần biết** context path riêng của dịch vụ nếu gateway đã ánh xạ đúng. Ngược lại, nếu spec/client generator lấy sai `servers.url` hoặc bị ghép hai lần `/api`, client có thể gửi `/api/api/v1/orders` và nhận 404 dù backend không lỗi.

Ví dụ cấu hình client thiếu nhất quán:

~~~text
base URL  = https://api.example.test/api
endpoint = /api/v1/orders
result   = https://api.example.test/api/api/v1/orders   (SAI)
~~~

Khi điều tra, ghi **URL cuối cùng thực sự được gửi**, không chỉ xem biến cấu hình `baseUrl` và annotation riêng lẻ. Một số HTTP client xử lý dấu `/` đầu tiên của relative path khác nhau; ví dụ trình giải quyết URI theo RFC có thể thay thế phần path của base URL khi relative reference bắt đầu bằng `/`. Kiểm tra request thực trên wire hoặc mock HTTP server.

## 3. 404 không phải lúc nào cũng có cùng nguyên nhân

| Nhóm | Ví dụ | Ai có thể tạo 404? | Tín hiệu phân biệt |
| --- | --- | --- | --- |
| Public host/path không có route | Ingress không có rule cho `api.example.test/api` | Gateway/default backend | Không có inbound request tương ứng ở application |
| Proxy rewrite sai | Public `/api/v1/orders` thành `/v1/orders` | Backend Spring hoặc proxy tiếp theo | Backend log thấy path khác dự kiến |
| Context path thiếu/thừa | Backend cần `/orders-service/...` nhưng proxy gửi `/api/...` | Servlet container | Controller không chạy, direct URL đúng context hoạt động |
| Controller mapping không có | Code chỉ map `/v2/orders` nhưng client gọi `/v1/orders` | Spring MVC | Actuator mappings không có handler tương ứng |
| Không khớp trailing slash/case/regex | `/orders/` khác `/orders`; ID bị encode sai | Spring/router/container | Một biến thể URL hoạt động, biến thể khác không |
| Resource nghiệp vụ không tồn tại | ID hợp lệ nhưng DB không có | Application service/advice | Handler đã match, có truy vấn tài nguyên |
| Resource bị ẩn vì quyền | ID thuộc tenant khác và API cố tình trả 404 | Security/domain layer | Handler có thể đã chạy; theo policy không tiết lộ tồn tại |
| Static asset/SPA fallback | `/api/...` bị rewrite tới trang frontend, hoặc static handler nhận request | Web server/static handler | Body HTML, asset path, status 200/404 lạ |
| Rollout không đồng nhất | Replica cũ chưa có route mới | Một phần backend replicas | Kết quả khác nhau tùy instance/version |
| Negative caching | CDN cache response 404 cũ | CDN/reverse proxy cache | `Age`/`Via`/cache metadata, direct backend đã có route |

**Mã HTTP là manh mối, không phải chứng cứ đủ.** `Server`, `Via`, `X-Cache` hoặc mẫu HTML error có thể gợi ý nguồn 404, nhưng proxy có thể sửa header và dùng chung error page. Bằng chứng đáng tin là **đối chiếu trace/log theo request ID tại từng hop và URI thực tế ứng dụng nhận**.

### 3.1. Phân biệt 404 với 400, 405, 406, 415 và 403

Không nên đổ mọi request thất bại vào “route sai”:

- **404 Not Found:** không tìm thấy target resource/route hoặc cố tình che sự tồn tại; phải xác định tầng tạo.
- **405 Method Not Allowed:** đường dẫn được nhận diện cho phương thức khác, ví dụ route chỉ `GET` nhưng client dùng `POST`. Framework có thể trả `Allow`; middleware có thể thay đổi hành vi.
- **400 Bad Request:** URI, path variable hoặc body sai định dạng (ví dụ string không parse thành UUID sau khi route đã match). Container cũng có thể trả 400 khi percent encoding không hợp lệ.
- **406 Not Acceptable:** route tồn tại nhưng không đáp ứng `Accept` theo content negotiation.
- **415 Unsupported Media Type:** content type request không được handler chấp nhận.
- **401/403:** chưa xác thực hoặc không đủ quyền. Security rule/exception handler riêng có thể **chủ đích trả 404** để không tiết lộ resource.

Nếu API `GET /api/v1/orders/{id}` yêu cầu UUID và client gửi `/api/v1/orders/abc`, Spring có thể match route nhưng trả `400` do chuyển kiểu thất bại; nó **không bắt buộc** phải trả 404. Đừng sửa mapping để biến lỗi input thành 404 nếu hợp đồng công khai không yêu cầu.

## 4. Quy trình điều tra 404: khoanh vùng trước, sửa sau

Một quy trình hiệu quả là xác minh đường đi từ ngoài vào trong:

~~~mermaid
flowchart TD
    A["Nhận 404 từ URL công khai"] --> B{"Request đến gateway đúng host/path?"}
    B -- "Không" --> C["Kiểm tra DNS, Host, route ingress, base URL"]
    B -- "Có" --> D{"Backend có nhận request?"}
    D -- "Không" --> E["Gateway path/rule, service endpoints, cache, route khác"]
    D -- "Có" --> F{"Backend thấy URI đúng?"}
    F -- "Không" --> G["Sửa prefix rewrite/context path/encoding"]
    F -- "Có" --> H{"Spring có mapping tương ứng?"}
    H -- "Không" --> I["Kiểm tra @RequestMapping, method, servlet path, version"]
    H -- "Có" --> J["Kiểm tra service, resource ID, tenant, auth policy"]
~~~

### Bước 1 — Thu thập request thật

Ghi thông tin tối thiểu:

~~~text
method: GET
scheme + host: https://api.example.test
path: /api/v1/orders/8c9b4ca4-2211-4cd0-a949-d176bcb8e35f
query: (nếu có)
status: 404
timestamp / region / deployment version
request-id / trace-id: giá trị lấy từ hệ thống
response content-type và một đoạn body đã loại dữ liệu nhạy cảm
~~~

Không ghi bearer token, cookie session, URL chứa token, thông tin khách hàng hoặc full request body nhạy cảm vào ticket/log. Với path có ID, có thể dùng ID test riêng hoặc masking theo chính sách. Đối chiếu đúng **HTTP method**: gọi `GET` trong trình duyệt không tái hiện được một lỗi `POST`/`PATCH` mà client thật đang gặp.

### Bước 2 — Gọi lại public endpoint một cách kiểm soát

~~~bash
curl -i -sS \
  -H "Accept: application/json" \
  -H "X-Request-ID: diag-route-001" \
  -H "Authorization: Bearer <test-access-token>" \
  "https://api.example.test/api/v1/orders/8c9b4ca4-2211-4cd0-a949-d176bcb8e35f"
~~~

Sử dụng credential kiểm thử hợp lệ và không lưu command chứa secret vào lịch sử shell công khai. `-i` in response headers, `-sS` giảm progress nhưng vẫn hiển thị lỗi của curl. Nếu cần xem redirect/đường đi, dùng `-v` trong môi trường được kiểm soát, **không dump token/cookie ra log**. Không dùng `-k/--insecure` để “chữa 404”: nó bỏ xác minh TLS, không xác minh định tuyến đúng, và có thể che lỗi chứng chỉ.

Nếu nghi URL bị client chuẩn hóa sai, có thể dùng:

~~~bash
curl --path-as-is -i \
  "https://api.example.test/api/v1/orders/%2Fspecial"
~~~

Lệnh chỉ để **chẩn đoán cách path đi qua các tầng**, không khuyến nghị dùng slash đã encode làm ID. Các proxy/container có thể từ chối hoặc xử lý `%2F` khác nhau; không vội tắt bảo vệ encoded slash để một route lạ hoạt động.

### Bước 3 — So sánh direct backend và public proxy

Giả sử backend cần context `/orders-service`:

~~~bash
# Chạy từ môi trường test có quyền truy cập mạng nội bộ.
curl -i \
  -H "Authorization: Bearer <test-access-token>" \
  "http://orders-api:8080/orders-service/api/v1/orders/8c9b4ca4-2211-4cd0-a949-d176bcb8e35f"
~~~

Đọc kết quả:

| Public URL | Direct backend đúng context | Hướng điều tra |
| --- | --- | --- |
| 404 | 200 | Gateway/ingress rewrite, routing, cache hoặc auth khác đường đi |
| 404 | 404 | Kiểm tra context path, controller mapping, ID/tenant và response origin |
| 200 | 404 | Có thể public đi tới **backend khác**, proxy phục vụ cache hoặc direct URL chưa đúng |
| 404 ngẫu nhiên | 200 theo từng pod/instance | Deployment version, canary, routing, cấu hình từng replica |
| 403 public | 200 direct | Gateway auth/WAF policy hoặc khác credential; đây không phải cùng một 404 |

Không suy ra nguyên nhân chỉ từ bảng; phải bảo đảm hai thử nghiệm dùng cùng method, principal, tenant, path tương đương và dữ liệu đúng. Gọi trực tiếp backend có thể bỏ qua TLS termination, auth gateway hoặc header nhận dạng tenant; **không coi việc direct trả 200 là lý do bỏ lớp bảo vệ ở gateway**.

Với Kubernetes, có thể dùng `kubectl port-forward` trên môi trường được ủy quyền:

~~~bash
kubectl -n api port-forward svc/orders-service 18080:8080

# Ở terminal khác, giữ nguyên context path mà ứng dụng mong đợi:
curl -i \
  -H "Authorization: Bearer <test-access-token>" \
  "http://127.0.0.1:18080/orders-service/api/v1/orders/8c9b4ca4-2211-4cd0-a949-d176bcb8e35f"
~~~

`port-forward` chỉ giúp vượt qua một phần network ingress để khoanh vùng; nó không thay thế E2E qua gateway. Service port/namespace là ví dụ và cần đối chiếu manifest đang chạy.

### Bước 4 — Kiểm tra route đã đăng ký trong Spring

Một route dự kiến có thể **không được đăng ký** vì controller không nằm trong component scan, profile/condition không bật bean, chương trình khởi động bản build cũ, hoặc endpoint đã đổi version. Có thể kiểm tra startup logs hoặc dùng **Spring Boot Actuator mappings** trong môi trường được bảo vệ:

~~~text
GET /orders-service/actuator/mappings
~~~

Đường dẫn trên giả định Actuator dùng **cùng application port/context path** và base path mặc định `/actuator`. Nếu management server có port/base path/context riêng, URL sẽ khác. Endpoint `mappings` không luôn được web-expose mặc định; nếu cần mở cho chẩn đoán, hãy chỉ cho phép qua mạng quản trị và authentication/authorization phù hợp, sau đó đóng lại theo chính sách. Nó có thể tiết lộ danh sách endpoint nội bộ.

Một số logging tạm thời ở môi trường test:

~~~yaml
logging:
  level:
    org.springframework.web.servlet.DispatcherServlet: DEBUG
    org.springframework.web.servlet.mvc.method.annotation.RequestMappingHandlerMapping: TRACE
~~~

Các logger này mang tính minh họa, độ chi tiết và thông điệp thay đổi theo phiên bản Spring. Chỉ bật đủ lâu để chẩn đoán; tránh bật log request headers/body nhạy cảm trên production. **Không phải mọi 404 đều tạo `NoHandlerFoundException`**: cách Spring Boot/Spring MVC trả lỗi cho không tìm thấy handler hoặc static resource phụ thuộc phiên bản/cấu hình. Trong Spring Framework 6.1+, static resource handler cũng có thể sinh `NoResourceFoundException`; một lỗi này không có nghĩa controller bị gọi.

### Bước 5 — Xác minh nghiệp vụ sau khi route thực sự match

Nếu handler có mặt và service đã được gọi, `404` có thể là:

- ID hợp lệ nhưng không có row tương ứng.
- Row tồn tại nhưng đã soft-delete/archived và API không cho hiển thị.
- Principal không có quyền thấy object của tenant khác; API cố tình trả `404` thay vì `403`.
- Query có filter tenant/status vô tình quá chặt.
- Read replica chưa bắt kịp transaction mới commit; client đọc ngay sau ghi thấy dữ liệu cũ theo consistency model.
- Cache hoặc tầng data access giữ negative result cũ.

Phải giữ đúng policy bảo mật: **không thay `404` thành `200` hoặc bỏ tenant filter chỉ để hết lỗi**. Đối chiếu service/query bằng dữ liệu test đã được cấp quyền, kiểm tra trace/SQL parameters đã mask, sau đó phân biệt “resource chưa có” với “request không tới handler”.

## 5. Nginx: dấu slash trong proxy_pass là quyết định quan trọng

Nginx có quy tắc thay phần URI khớp `location` khi `proxy_pass` **chứa phần URI**. Với prefix location đơn giản và không có rewrite đặc biệt, hai cấu hình sau **không tương đương**.

### 5.1. Có dấu / ở cuối proxy_pass: strip và thay prefix

~~~nginx
location /api/ {
    proxy_pass http://orders-api:8080/;
}
~~~

Trong tình huống prefix location đơn giản:

~~~text
Client:    /api/v1/orders/42
Upstream:  /v1/orders/42
~~~

Phần `/api/` đã được thay bằng `/`. Nếu backend controller nhận `/api/v1/orders/{id}` ở context root, nó không match. Đây là nguyên nhân 404 rất phổ biến khi đội vận hành nghĩ rằng Nginx “chỉ chuyển nguyên path”.

### 5.2. Không có phần URI ở proxy_pass: thường giữ request URI

~~~nginx
location /api/ {
    proxy_pass http://orders-api:8080;
}
~~~

Với request thông thường không trải qua các rewrite đặc biệt:

~~~text
Client:    /api/v1/orders/42
Upstream:  /api/v1/orders/42
~~~

Hai ví dụ này khác nhau chính ở phần URI trong `proxy_pass`. Các quy tắc còn phụ thuộc `location` regex, biến trong `proxy_pass`, rewrite trước đó và URI đã normalize; **không áp dụng máy móc** cho mọi cấu hình Nginx.

### 5.3. Cấu hình phù hợp với context path của Spring Boot

Backend của bài chạy dưới `/orders-service`, nhưng public route vẫn là `/api/v1/orders/{id}`. Một mapping ví dụ:

~~~nginx
upstream orders_backend {
    server orders-api:8080;
}

server {
    listen 443 ssl;
    server_name api.example.test;
    # ssl_certificate / ssl_certificate_key được cấu hình an toàn.

    location /api/ {
        proxy_pass http://orders_backend/orders-service/api/;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-Host $host;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Request-ID $request_id;
    }
}
~~~

Với prefix location này:

~~~text
Public path:  /api/v1/orders/42
Rewritten:    /orders-service/api/v1/orders/42
Spring MVC:   /api/v1/orders/42 sau khi bỏ context path
~~~

Đây là cấu hình **minh họa**, chưa phải virtual host production hoàn chỉnh: cần TLS certificate thật, kiểm soát host, rate limit, body/timeouts, logging và chính sách network. Nếu môi trường đã có proxy ngoài thêm prefix, phải tính **toàn bộ chuỗi proxy**, không thêm một rewrite nữa cho chắc.

### 5.4. Kiểm tra đường dẫn trước và sau rewrite bằng log

Trong môi trường được phép, có thể cấu hình access log Nginx ghi route và upstream status bằng các trường hữu hạn, đã loại thông tin nhạy cảm:

~~~nginx
log_format api_route_diag
  'rid=$request_id host=$host '
  'request="$request" uri="$uri" '
  'status=$status upstream_status=$upstream_status '
  'upstream_addr=$upstream_addr';
~~~

`$request` chứa method và URI gốc, **có thể chứa query string hoặc dữ liệu nhạy cảm trong URL**. Không dùng format này trên production nếu chưa có redaction/retention/access policy. `$uri` là URI đã normalize trong ngữ cảnh xử lý Nginx, không phải lúc nào cũng là **URI cuối cùng gửi upstream**, đặc biệt khi có rewrite; xác minh upstream URI bằng log ứng dụng hoặc trace ở downstream. `$upstream_status` rỗng nếu Nginx không gọi upstream, giúp phân biệt lỗi tạo tại proxy với lỗi downstream, nhưng cũng cần xem cache, subrequest và retry.

Đừng sửa `proxy_pass` bằng thử-sai trên production. Hãy viết bảng expected mapping, thử trên staging/canary và so sánh nhiều URL biên như `/api`, `/api/`, `/api/v1/orders` và `/api/v1/orders/{id}`.

## 6. Kubernetes Ingress và API Gateway: rewrite có tính đặc thù

Kubernetes `Ingress` chọn backend theo host/path; việc viết lại path tùy **Ingress controller**, không phải mọi annotation đều do chuẩn Kubernetes định nghĩa. Dưới đây là ví dụ dành riêng cho **ingress-nginx** và backend có context `/orders-service`:

~~~yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: orders-api
  annotations:
    nginx.ingress.kubernetes.io/use-regex: "true"
    nginx.ingress.kubernetes.io/rewrite-target: /orders-service/api/$2
spec:
  ingressClassName: nginx
  rules:
    - host: api.example.test
      http:
        paths:
          - path: /api(/|$)(.*)
            pathType: ImplementationSpecific
            backend:
              service:
                name: orders-service
                port:
                  number: 8080
~~~

Với rule này, request `/api/v1/orders/42` khớp, capture `$2` là `v1/orders/42`; rewrite thành `/orders-service/api/v1/orders/42`. Đây là **ví dụ về quy tắc của ingress-nginx**, không được sao chép vào controller khác hoặc Gateway API và mặc định sẽ hoạt động. Việc dùng regex, thứ tự location, host chung với những Ingress khác và version controller có thể ảnh hưởng khớp route. TLS và các phần manifest khác được lược bớt.

### 6.1. Những sai lệch phổ biến trong ingress

| Cấu hình/hiện tượng | Hệ quả | Cách xác minh |
| --- | --- | --- |
| `host` không khớp request | Request vào default backend hoặc rule host khác | `curl` với hostname công khai đúng; kiểm tra host/SNI và Ingress rule |
| `path`/`pathType` sai | `/api` match nhưng `/api/v1` không match hoặc ngược lại | Đối chiếu Prefix/Exact/ImplementationSpecific |
| `rewrite-target` thiếu capture | Bỏ mất `/v1/orders` hoặc ghép sai prefix | Kiểm tra URI backend nhận và capture groups |
| Thêm prefix hai lần | Backend thấy `/api/api/v1/...` | Truy vết ingress → service → container |
| Dùng annotation controller khác | Rewrite không được áp dụng | Kiểm tra `ingressClassName` và controller đang quản lý |
| Service port/targetPort sai | Thường 502/503/timeout hơn là 404, nhưng có thể route sang app khác | Kiểm tra Service, EndpointSlice và upstream address |
| Cùng host có nhiều Ingress/rule | Một route bị rule khác ưu tiên | Kiểm tra cấu hình Nginx thực đã sinh và thứ tự match |
| Canary/rolling update | Một replica nhận path cũ, một replica nhận path mới | Gắn version/instance vào trace/log |

Lệnh quan sát định tuyến, chỉ chạy khi có quyền vào cluster:

~~~bash
kubectl -n api get ingress
kubectl -n api describe ingress orders-api
kubectl -n api get svc orders-service
kubectl -n api get endpointslices
kubectl -n api get pods -l app=orders-api
~~~

Kết quả mô tả trạng thái Kubernetes, **không tự chứng minh** cấu hình Nginx đang áp dụng đúng URI cho một request cụ thể. Kết hợp access log ingress/controller và inbound log ứng dụng có cùng request ID. Đừng chạy lệnh debug công khai làm lộ secret hoặc cấp quyền cluster-admin chỉ để điều tra 404.

### 6.2. Forwarded headers không đồng nghĩa rewrite route

Proxy thường gửi:

~~~http
X-Forwarded-Proto: https
X-Forwarded-Host: api.example.test
X-Forwarded-Prefix: /api
~~~

Chúng có thể giúp framework hiểu public scheme/host/prefix khi tạo absolute URL, redirect hoặc link, tùy cấu hình và implementation. **Không được mặc định rằng thêm `X-Forwarded-Prefix` sẽ khiến một `@GetMapping` sai tự match.** Ở ví dụ này, proxy vẫn cần gửi đúng URI mà Spring/container mong đợi.

Một cấu hình Spring Boot có thể sử dụng:

~~~yaml
server:
  forward-headers-strategy: framework
~~~

Cấu hình này yêu cầu **trust boundary đúng**: gateway phải loại bỏ hoặc ghi đè forwarded headers do client bên ngoài tự gửi, backend không được nhận trực tiếp header giả. Khi có nhiều proxy, kiểm tra chain và cấu hình theo môi trường. Header giả mạo có thể làm sinh link/redirect sai host, bypass một số quyết định dựa vào scheme hoặc tạo rủi ro bảo mật. Không bật forwarded header trust bừa để chữa route 404.

## 7. Spring MVC: những nguyên nhân mapping không khớp

### 7.1. Annotation ghép prefix nhưng code và client nhìn khác nhau

~~~java
@RestController
@RequestMapping("/api/v1/orders")
class OrderController {
    @GetMapping("/{id}")
    OrderView get(@PathVariable UUID id) {
        return orderService.get(id);
    }
}
~~~

Trong context root, ví dụ trên nhận `GET /api/v1/orders/{id}`, không nhận `GET /v1/orders/{id}`. Ở context `/orders-service`, đường HTTP trực tiếp lại là `/orders-service/api/v1/orders/{id}`. Nếu client dùng `POST` hoặc ID có dạng làm conversion thất bại, cần đọc `405`/`400` tương ứng, không tự kết luận mapping bị mất.

Đừng so route với **tên class/file**, vì Spring chỉ đăng ký những bean/controller được component scan hoặc cấu hình đưa vào context. Một controller nằm ngoài package scan, bị `@Profile`/`@Conditional` tắt hoặc class không được build/deploy có thể không tạo mapping. Kiểm tra version build và mappings thực tế của replica đang trả lỗi.

### 7.2. Trailing slash và case sensitivity

Trong cấu hình thường gặp của Spring Framework 6/Spring Boot 3, việc khớp dấu `/` cuối **không còn được nới lỏng mặc định như trước ở nhiều cấu hình cũ**. Vì thế:

~~~text
/api/v1/orders
/api/v1/orders/
~~~

có thể là hai path khác nhau. Tương tự, `/Orders` và `/orders` thường không thể hoán đổi nếu router phân biệt chữ hoa/chữ thường. Nên chọn URI chuẩn trong OpenAPI, frontend và test, sau đó áp dụng nhất quán. Nếu phải hỗ trợ alias cũ, khai báo mapping/redirect có chủ đích và kiểm thử.

**Cẩn trọng với redirect:** `301`/`302` có lịch sử hành vi đổi `POST` thành `GET` ở một số client; `307`/`308` giữ method/body theo chuẩn nhưng vẫn có hậu quả với authentication, retry, cache và client không hỗ trợ. Không tự động redirect request ghi chỉ để chữa dấu slash.

### 7.3. URL encoding và dấu phân tách

Với path variable, dấu `/` là separator path segment; một ID chứa slash cần thiết kế URI đặc biệt hoặc chuyển sang query/opaque identifier phù hợp. `%2F` có thể bị proxy, WAF hoặc servlet container chặn hay normalize khác nhau. `..`, dấu `//`, percent-encoding không chuẩn, Unicode normalization và dấu `;` (matrix parameter) cũng có thể dẫn tới URL khác kỳ vọng hoặc trả 400/404.

**Không nới lỏng bảo vệ path traversal/encoded slash** chỉ để một request mẫu chạy được. Trước tiên xác định kiểu ID hợp đồng cho phép; với UUID, ID hợp lệ vốn không cần ký tự slash. Test chính xác client encoding và backend path handling.

### 7.4. CORS/preflight và authentication có thể làm lẫn triệu chứng

Browser có thể gửi `OPTIONS` preflight trước request mang custom header hoặc content type nhất định. Nếu OPTIONS bị proxy route sai, frontend có thể báo “network/CORS error” thay vì hiển thị 404 từ API. Khi debug, kiểm tra **cả preflight OPTIONS và request thật**:

~~~http
OPTIONS /api/v1/orders HTTP/1.1
Host: api.example.test
Origin: https://app.example.test
Access-Control-Request-Method: POST
Access-Control-Request-Headers: content-type,authorization
~~~

Không chữa CORS bằng `Access-Control-Allow-Origin: *` cho request dùng credential. CORS không thay thế authentication, authorization hoặc CSRF protection khi API dùng cookie. Chỉ thay route/response policy sau khi xác định request nào thật sự bị 404.

## 8. Kiểm tra tự động bằng Java/Spring và HTTP integration

### 8.1. Controller test xác nhận handler path

Giả định Spring MVC có `OrderController` và service đọc đơn:

~~~java
public record OrderView(UUID id, String status) {}

@RestController
@RequestMapping("/api/v1/orders")
class OrderController {
    private final OrderQueryService query;

    OrderController(OrderQueryService query) {
        this.query = query;
    }

    @GetMapping("/{id}")
    OrderView one(@PathVariable UUID id) {
        return query.findById(id);
    }
}
~~~

Unit/slice test không cần proxy:

~~~java
@WebMvcTest(OrderController.class)
@AutoConfigureMockMvc(addFilters = false)
class OrderRouteTest {
    @Autowired MockMvc mvc;
    @MockitoBean OrderQueryService query;

    private static final UUID ID =
        UUID.fromString("8c9b4ca4-2211-4cd0-a949-d176bcb8e35f");

    @Test
    void registeredGetRouteWorks() throws Exception {
        when(query.findById(ID))
            .thenReturn(new OrderView(ID, "PENDING"));

        mvc.perform(get("/api/v1/orders/" + ID))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.status").value("PENDING"));
    }

    @Test
    void nonExistingRouteDoesNotMatch() throws Exception {
        mvc.perform(get("/v1/orders/" + ID))
            .andExpect(status().isNotFound());
        verifyNoInteractions(query);
    }
}
~~~

Ví dụ dùng Spring Boot 3, JUnit, Mockito, MockMvc và `@MockitoBean` (Spring Framework 6.2/Spring Boot 3.4+); bản Boot 3 cũ hơn thường dùng `@MockBean`. `addFilters=false` chỉ nhằm cô lập routing ở **bài test này**; nó **không kiểm tra Spring Security** và không được dùng làm bằng chứng auth hoạt động. Viết security test riêng với filter chain thật, đồng thời dùng controller/service thực để xác minh logic 404 vì không đủ quyền theo thiết kế.

### 8.2. MockMvc và context path: phải dựng request cho đúng

MockMvc không tạo một HTTP socket qua Nginx, và đường dẫn trong mock request có thể cần đặt context path tường minh. Với ví dụ backend có context `/orders-service`:

~~~java
mvc.perform(get("/orders-service/api/v1/orders/" + ID)
        .contextPath("/orders-service"))
    .andExpect(status().isOk());
~~~

`contextPath("/orders-service")` khiến handler path tương ứng là `/api/v1/orders/{id}` khi servlet path mặc định phù hợp. Test này kiểm tra Spring MVC request mapping **trong mô hình mock**, không chứng minh Boot embedded server thực sự lắng nghe với context đó hoặc Ingress rewrite đúng. Nếu muốn kiểm tra property `server.servlet.context-path` và network stack thật, sử dụng `@SpringBootTest(webEnvironment = RANDOM_PORT)` với HTTP client.

Một controller test vẫn có thể pass khi gateway rewrite sai. Đây là lý do test contract qua **public ingress URL** nên nằm trong pipeline deploy/smoke test, không chỉ trong PR unit tests.

### 8.3. Test backend socket thật

Phác thảo integration test chạy embedded server:

~~~java
@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT,
    properties = "server.servlet.context-path=/orders-service")
class OrderContextPathIT {
    @LocalServerPort int port;
    @Autowired TestRestTemplate http;

    @Test
    void internalRequestMustIncludeContextPath() {
        String root = "http://localhost:" + port;
        ResponseEntity<String> missingPrefix = http.getForEntity(
            root + "/api/v1/orders", String.class);

        // Có thể là 404 nếu không có mapping khác ngoài context;
        // kết quả path đúng cần thêm fixture/credential hợp lệ.
        assertThat(missingPrefix.getStatusCode().value()).isEqualTo(404);
    }
}
~~~

Mã khung không thực hiện xác thực/fixture đầy đủ và không kết luận đường `/orders-service/api/v1/orders` sẽ 200 nếu ứng dụng không có handler GET collection. Cần bổ sung test với ID hợp lệ, principal test hoặc endpoint public chuyên dụng, và kiểm tra status/body mong đợi. Với Boot 3, `@LocalServerPort` thuộc package `org.springframework.boot.test.web.server`; import/phụ thuộc theo project thực tế.

Để chứng minh routing public cuối cùng, hãy chạy test ngoài ứng dụng, qua **gateway với host/TLS thật của staging**, assert HTTP status, media type, version và resource. Không cho phép test vượt auth ở production.

### 8.4. Contract test ma trận đường dẫn

| URL/method | Đường dẫn giả định qua proxy | Kết quả mong đợi |
| --- | --- | --- |
| `GET /api/v1/orders/{validId}` | `/orders-service/api/v1/orders/{id}` | `200` nếu resource nhìn thấy được |
| `GET /api/v1/orders/{missingId}` | Cùng route, ID không có | `404` nghiệp vụ |
| `GET /v1/orders/{id}` | Không có rule public | `404` tại ingress/proxy |
| `GET /api/api/v1/orders/{id}` | Prefix nhân đôi | `404`; test phát hiện lỗi client |
| `GET /api/v1/orders/{badUuid}` | Route khớp nhưng conversion sai | Thường `400` khi path variable UUID |
| `POST /api/v1/orders/{id}` | Route chỉ GET | Thường `405` nếu security cho phép và route tồn tại |
| `GET /api/v1/orders/` | Tùy controller mapping/route | Có thể `404` theo trailing slash policy |
| `OPTIONS /api/v1/orders` | Preflight nếu cần | Theo CORS policy, không bị rewrite nhầm |
| `GET /api/v2/orders/{id}` | Chưa hỗ trợ v2 | `404` hoặc version policy đã công bố |

Các status “thường” có thể thay đổi nếu auth middleware chạy trước, resource bị che, CORS filter, fallback route hoặc custom handler. Test thực phải cố định **hợp đồng mong muốn** và khởi tạo cùng điều kiện xác thực, tránh hardcode kỳ vọng mà chính sách API không xác nhận.

## 9. Các trường hợp dễ bỏ sót khi 404 chỉ xuất hiện ngoài production

### 9.1. Tài liệu OpenAPI, Swagger UI và client generator

Kiểm tra `servers` trong OpenAPI:

~~~yaml
openapi: 3.0.3
info:
  title: Orders API
  version: "1.0"
servers:
  - url: https://api.example.test
paths:
  /api/v1/orders/{id}:
    get:
      operationId: getOrder
      parameters:
        - name: id
          in: path
          required: true
          schema:
            type: string
            format: uuid
      responses:
        "200":
          description: Tìm thấy đơn hàng
        "404":
          description: Không tìm thấy hoặc không được phép xem
~~~

Nếu `servers.url` đã có `/api` **và** `paths` lại bắt đầu `/api/v1/...` thì client generator có thể gọi `/api/api/v1/...`. OpenAPI path bắt đầu bằng `/` và được ghép theo quy tắc của spec, không thể bỏ qua việc kiểm tra URL sinh ra thực tế. API documentation endpoint cũng có thể bị sai context path; việc Swagger UI mở được không có nghĩa “Try it out” đang trỏ đúng domain/prefix.

### 9.2. SPA catch-all và reverse proxy phục vụ static content

Một cấu hình frontend có thể có catch-all trả `index.html` cho mọi path. Nếu rule `location /` ưu tiên sai hoặc backend route bị loại bỏ, request `/api/v1/orders` có thể nhận **`200 text/html`** thay vì 404 JSON. Client sẽ báo JSON parse error, dù nguyên nhân ban đầu vẫn là route API không được chuyển tới backend. Kiểm tra `Content-Type` và đầu body; đừng chỉ theo status.

Ngược lại, request `/api` có thể đi sang static server và trả trang HTML 404 mang branding của frontend. Khi cần, tách route `/api/` và fallback SPA rõ ràng, test cả link deep route frontend và API resource.

### 9.3. CDN cache 404 hoặc redirect cũ

Một số CDN/reverse proxy có cơ chế **negative caching** cho 404 hoặc cache error/redirect theo cấu hình. Sau khi deploy route mới, request vẫn có thể bị trả 404 từ edge cho đến khi TTL hết hoặc cache được invalidate. Kiểm tra `Age`, `Via`, `X-Cache`/header nhà cung cấp nếu có, HTTP cache policy và khác biệt giữa các PoP/region.

Không thêm query ngẫu nhiên làm workaround lâu dài: nó có thể tăng cache cardinality, bỏ kiểm soát cache hoặc che bug origin. Xác minh với cache-bypass có kiểm soát và điều chỉnh cache policy/invalidation theo hợp đồng.

### 9.4. Canary/rolling deployment và version skew

Nếu route chỉ có ở bản N+1 nhưng 30% traffic vẫn vào N, sẽ có lỗi 404 **không ổn định**. Phân loại theo `deployment.version` và replica trong trace/log; so sánh mapping đã đăng ký ở cả N và N+1. Chỉ route qua nhóm backend đã triển khai feature hoặc thực hiện rollout tương thích. Đừng bật retry vô hạn trên 404: client có thể liên tục gửi đến phiên bản cũ và che lỗi phát hành.

### 9.5. Host, SNI, HTTPS và nhiều virtual host

Với TLS, tên host dùng khi chọn virtual host/certificate có thể phụ thuộc SNI; HTTP routing dùng `Host`/`:authority` và path. Để điều tra IP cụ thể mà vẫn giữ hostname/TLS validation, `curl --resolve` có thể hữu ích:

~~~bash
curl --resolve api.example.test:443:203.0.113.10 -i \
  "https://api.example.test/api/v1/orders/8c9b4ca4-2211-4cd0-a949-d176bcb8e35f"
~~~

`203.0.113.10` là địa chỉ mẫu dành cho tài liệu, **không phải IP thật để gọi**. `--resolve` giúp kết nối tới IP chọn trước trong khi URL vẫn chứa hostname phục vụ SNI/Host; khác với `-H 'Host: ...'` trên HTTPS IP literal. Chỉ dùng với hệ thống và quyền kiểm thử được cho phép. Nếu kết quả khác theo edge IP, hãy điều tra config rollout/DNS/virtual host, không bỏ kiểm tra chứng chỉ.

## 10. Chẩn đoán 404 mà không phá bảo mật

Khắc phục route cần tôn trọng các ranh giới sẵn có:

1. Không sửa `authorizeHttpRequests(...).anyRequest().permitAll()` để một URL thôi trả 404. 404 có thể do security policy cố tình che resource.
2. Không trả ID hoặc trạng thái tồn tại của record cross-tenant để “điều tra” qua public API.
3. Không bật Actuator mappings hoặc debug log header/body chứa token trên Internet.
4. Không tin tùy ý `X-Forwarded-Host`, `X-Forwarded-Proto` hay `X-Forwarded-Prefix` từ client ngoài; proxy phải làm sạch.
5. Không bật unsafe path normalization hoặc encoded slash trên servlet container nếu chưa đánh giá traversal/WAF/auth.
6. Không redirect `POST` sang path mới mà không kiểm tra method/body, idempotency và khả năng client retry.
7. Không cho SPA static handler hoặc fallback proxy trả nội dung thành công giả cho API bị lỗi.
8. Giữ request-id/trace-id nhất quán giữa proxy và app nhưng không dùng ID nhạy cảm làm metric label.

Với domain resource, trả 404 hay 403 là **quyết định bảo mật**: một số API chủ ý trả 404 khi principal không được phép biết tài nguyên có tồn tại. Test phải kiểm tra không có data leakage và không có side effect sai, thay vì tự động biến tất cả thành 403.

## 11. Runbook xử lý 404 trong sự cố thực tế

| Giai đoạn | Việc cần làm | Kết quả |
| --- | --- | --- |
| **Triage** | Thu method, full public URL (đã mask), status, trace ID, thời điểm, version | Tái hiện được lỗi |
| **Provenance** | Đối chiếu ingress/proxy log và app log cùng request ID | Biết tầng tạo 404 |
| **Path mapping** | Viết bảng public → rewritten URI → context → handler path | Xác định đoạn prefix sai/mất/thừa |
| **Application route** | Kiểm tra Spring mappings, annotation, scan, method, trailing slash | Biết route có được đăng ký không |
| **Business/resource** | Nếu handler match: ID, tenant, quyền, DB/read replica/cache | Phân biệt 404 nghiệp vụ |
| **Mitigation** | Điều chỉnh một nơi: client base URL, proxy rewrite hoặc app mapping | Khôi phục mà không nhân đôi prefix |
| **Validation** | Test direct + public, GET/POST/OPTIONS, resource tồn tại/vắng, auth | Không làm hỏng contract hoặc security |
| **Follow-up** | Thêm contract/smoke test, dashboard/log path, rollback plan | Ngăn lỗi tái diễn |

Một cách ghi incident ngắn gọn:

~~~text
Triệu chứng:
  GET https://api.example.test/api/v1/orders/{id} -> 404 (từ ingress)

Bằng chứng:
  Gọi trực tiếp backend /orders-service/api/v1/orders/{id} -> 200
  Ingress ghi không có upstream cho request đó
  Rule hiện tại chỉ match /order/ (thiếu s)

Nguyên nhân:
  Path rule ingress không khớp hợp đồng công khai /api/...

Khắc phục:
  Sửa path rule và kiểm chứng rewrite theo bảng mapping

Kiểm thử hồi quy:
  Cùng request qua gateway -> 200
  Resource không tồn tại -> 404 nghiệp vụ
  Token sai -> 401/403 theo policy; không lộ dữ liệu
~~~

Đây là ví dụ báo cáo giả định. Nếu access log ingress cho thấy `upstream_status=404`, request có thể đã tới backend; cần đối chiếu đường dẫn backend nhận trước khi kết luận lỗi nằm tại ingress.

## 12. Bài tập thực hành

**Bài tập 1 — Tính path qua Nginx.** Backend map `GET /api/v1/orders/{id}` và chạy context root. Cho hai cấu hình `proxy_pass http://backend:8080;` và `proxy_pass http://backend:8080/;` bên trong `location /api/`. Hãy viết upstream URI khi client gọi `/api/v1/orders/42`, xác định cấu hình nào phù hợp, giải thích vì sao sự khác nhau nằm ở **phần URI** của `proxy_pass` chứ không chỉ cổng upstream.

**Bài tập 2 — Context path và annotation.** Spring Boot cấu hình `server.servlet.context-path=/orders-service`, controller có `@RequestMapping("/api/v1/orders")`, method `@GetMapping("/{id}")`. Gọi backend trực tiếp bằng hai URL `/api/v1/orders/42` và `/orders-service/api/v1/orders/42`. Giải thích tầng nào có thể trả 404; viết test MockMvc có `contextPath` và HTTP integration test trên port thật.

**Bài tập 3 — Ingress rewrite.** Public URL là `/api/v1/orders/42`, backend cần `/orders-service/api/v1/orders/42`. Viết hoặc chỉnh annotation/rule của ingress-nginx để URI chuyển đúng. Thử thêm `/api`, `/api/`, `/api/v1/orders` và ID có ký tự encode; kiểm tra không tạo `/api/api` hoặc mất `/v1`. Nêu lý do không bê annotation này sang controller khác mà chưa xác minh.

**Bài tập 4 — Nhận diện nguồn 404.** Nhận bốn response: (a) HTML 404 ở gateway, app không có trace; (b) app log thấy `/v1/orders/42` nhưng mapping là `/api/v1/orders/{id}`; (c) handler chạy, repository không tìm thấy UUID; (d) handler tìm thấy record tenant B nhưng người gọi tenant A. Hãy xác định nguyên nhân, cách phản hồi HTTP phù hợp và dữ liệu nào không được tiết lộ.

**Bài tập 5 — OpenAPI và client URL.** OpenAPI `servers.url` là `https://api.example.test/api`, trong khi `paths` có `/api/v1/orders/{id}`. Client generator gửi `/api/api/v1/orders/42`. Chọn một cách sửa hợp đồng để không nhân đôi tiền tố, tạo controller/contract test và smoke test từ public URL. Kiểm tra thêm phiên bản `/v2` chưa triển khai.

**Bài tập 6 — 404 không ổn định sau deploy.** Bản N chưa có `GET /api/v1/orders/{id}` nhưng N+1 đã có; load balancer gửi traffic đến cả hai. Đề xuất cách chứng minh bằng version/trace ID, chiến lược rollout/compatibility và test hồi quy. Phân biệt với CDN negative cache hoặc read replica lag.

**Bài tập 7 — Runbook và bảo mật.** Viết quy trình điều tra 404 cho một API có Spring Security và CORS. Dùng request GET, POST và OPTIONS hợp lệ; mô tả cách kiểm tra forwarded headers, Actuator mappings, ingress log mà không lộ token/PII. Chứng minh sửa route không vô hiệu hóa object-level authorization hoặc CSRF cho cookie authentication.

### Tiêu chí đánh giá

Lời giải đạt yêu cầu khi (1) chỉ được tầng tạo 404 bằng bằng chứng; (2) tính chính xác public URI → upstream URI → context/servlet path → handler mapping; (3) phân biệt 404 với 400/405/403 và 404 nghiệp vụ; (4) đưa ra thay đổi nhỏ nhất ở đúng tầng; (5) chứng minh bằng direct/backend và public/gateway test; (6) giữ nguyên contract, security và tính đúng đắn khi rollout.

## 13. Checklist trước khi kết luận đã sửa xong 404

- [ ] Method, Host, scheme, port, public path và query của request thực đã được xác minh.
- [ ] Đã xác định proxy/gateway có forward request tới backend hay tạo 404 tại edge.
- [ ] Có bảng mapping path từ client qua từng proxy tới servlet context và Spring handler.
- [ ] Cấu hình Nginx `location`/`proxy_pass` (có/không URI `/`) hoặc Ingress rewrite đã được kiểm tra theo đúng controller/version.
- [ ] `server.servlet.context-path`, servlet path và `@RequestMapping` được đối chiếu với route đăng ký thực tế.
- [ ] Dấu slash cuối, case, percent encoding và base URL/`servers` OpenAPI không tạo URI khác hợp đồng.
- [ ] Nếu route match, đã kiểm tra ID, tenant, auth, soft delete, read replica/cache trước khi gọi đó là “lỗi routing”.
- [ ] Không dùng `-k`, mở Actuator công khai, tắt filter/auth hoặc cho phép encoded slash tùy tiện để che lỗi.
- [ ] Đã kiểm thử public và direct URL trong cùng điều kiện quyền, bao gồm response `200`/`404`/`401`/`403` theo policy.
- [ ] Đã có test cho method `POST`/`OPTIONS`, path version, N/N+1 deployment và đường đi qua gateway.
- [ ] Dashboard/log/trace phân biệt status gateway và backend, cùng request ID nhưng không ghi credential/PII.

**Kết luận:** 404 ở REST API là **kết quả của một đường định tuyến và một quyết định nghiệp vụ**, không chỉ là “không có record”. Điều tra hiệu quả nhất là đi từ URL client vào từng hop, ghi nhận path đã biến đổi và xác nhận nơi tạo response. Khi đã biết sai ở proxy, context path, controller hay business query, hãy sửa đúng ranh giới, kiểm thử qua public endpoint và giữ nguyên bảo mật cùng hợp đồng HTTP.
