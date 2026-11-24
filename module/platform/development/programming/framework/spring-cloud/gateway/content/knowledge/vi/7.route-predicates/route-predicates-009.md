# XForwardedRemoteAddr và giới hạn tin cậy proxy theo phiên bản hỗ trợ

## 1. Vấn đề cần giải quyết: gateway nhìn thấy IP nào?

Trong **SPRING_CLOUD_GATEWAY**, route predicate có thể quyết định chuyển một request đến microservice nào dựa vào đường dẫn, method, header hoặc địa chỉ nguồn. Bài thuộc chương **Điều kiện định tuyến** này tập trung vào hai câu hỏi dễ nhầm khi gateway nằm sau load balancer, ingress hoặc web application firewall (WAF):

1. **`XForwardedRemoteAddr` kiểm tra địa chỉ nào trong HTTP request?**
2. **Khi nào có thể tin vào `X-Forwarded-For`, và phải giới hạn số proxy đáng tin như thế nào?**

Đây là kiến thức cần có khi xây API Gateway với route predicate và filter chain, chuyển đổi header/path, khám phá dịch vụ, rồi bổ sung xác thực, rate limiting, circuit breaker, retry, TLS và quan sát request. Một IP được xác định sai có thể khiến route chạy nhầm, tạo sai khóa giới hạn lưu lượng hoặc khiến chính sách truy cập bị vượt qua.

**Nguyên tắc quan trọng:** `X-Forwarded-For` là **HTTP header có thể được người gửi tự tạo**. Việc một địa chỉ nằm trong dải CIDR cho phép **không chứng minh header đó được proxy đáng tin tạo ra**. Phải thiết kế ranh giới tin cậy ở cả lớp mạng và lớp xử lý header.

> **Phạm vi phiên bản:** Ví dụ chính dùng **Spring Cloud Gateway Server WebFlux**. Tài liệu chính thức cho các dòng **4.2, 4.3 và 5.x** đều mô tả route predicate `XForwardedRemoteAddr` và `RemoteAddr`. Tuy vậy, namespace cấu hình và các tính năng xử lý forwarded header có khác biệt giữa các dòng; cần đối chiếu đúng tài liệu phiên bản đang chạy. Server MVC có API và namespace riêng.

## 2. Phân biệt IP kết nối và chuỗi X-Forwarded-For

Giả sử một hệ thống có hai proxy tin cậy trước gateway:

~~~mermaid
flowchart LR
    C["Client<br/>198.51.100.24"] --> W["WAF<br/>10.0.1.10"]
    W --> I["Ingress<br/>10.0.1.20"]
    I --> G["Spring Cloud Gateway"]
    G --> B["orders-service"]
~~~

Nếu WAF **xóa giá trị `X-Forwarded-For` do client gửi** rồi tạo header mới, ingress sau đó nối thêm địa chỉ peer mà nó quan sát, gateway có thể nhận:

~~~http
GET /api/orders/42 HTTP/1.1
Host: api.example.test
X-Forwarded-For: 198.51.100.24, 10.0.1.10
~~~

Ở gateway, peer kết nối trực tiếp thường là ingress `10.0.1.20`, còn `X-Forwarded-For` mô tả các hop phía trước:

| Vị trí | IP minh họa | Vai trò |
| --- | --- | --- |
| Phần tử đầu của `X-Forwarded-For` | `198.51.100.24` | Client thật **chỉ khi** WAF đã làm sạch header đầu vào |
| Phần tử tiếp theo | `10.0.1.10` | WAF phía trước ingress |
| Peer kết nối đến gateway | `10.0.1.20` | Ingress trực tiếp kết nối với gateway |

Địa chỉ `198.51.100.0/24`, `192.0.2.0/24` và `203.0.113.0/24` là dải minh họa dùng trong tài liệu. Khi triển khai thực tế, thay bằng dải IP thật đã xác minh; đừng lấy các giá trị ví dụ làm allowlist production.

**Điểm tinh tế:** `ServerHttpRequest.getRemoteAddress()` thể hiện địa chỉ remote của request trong ngữ cảnh WebFlux. Ở cấu hình mặc định, địa chỉ này thường là peer kết nối tới gateway, nhưng các cơ chế xử lý forwarded header sớm trong WebFlux (nếu bật) có thể biến đổi cách request biểu diễn remote address. Vì thế, không nên đồng nhất mọi giá trị `getRemoteAddress()` với “IP socket gốc” khi chưa kiểm tra cấu hình runtime.

### X-Forwarded-For được nối như thế nào?

Trong một chuỗi proxy thường gặp, danh sách XFF đi từ **client ở bên trái** đến các proxy trước gateway ở bên phải:

~~~text
X-Forwarded-For: client, proxy-1, proxy-2
                 trái nhất           phải nhất
~~~

Đây là quy ước phổ biến, không phải bằng chứng tin cậy. Một client độc hại có thể tự gửi:

~~~http
X-Forwarded-For: 203.0.113.9
~~~

Nếu edge proxy **chỉ append** địa chỉ client thực `198.51.100.24` mà không loại bỏ giá trị giả ban đầu, gateway có thể thấy:

~~~http
X-Forwarded-For: 203.0.113.9, 198.51.100.24
~~~

Lấy phần tử trái nhất theo kiểu “tin tất cả” sẽ nhầm `203.0.113.9` là địa chỉ client. Đây là rủi ro **IP spoofing qua header**; TLS bảo vệ kết nối truyền tải nhưng không làm nội dung header do client tự đặt trở nên đáng tin.

## 3. Ba cơ chế tên gần giống nhưng ý nghĩa khác nhau

| Cơ chế WebFlux Gateway | Đọc từ đâu? | Cấu hình/điểm dùng | Cảnh báo |
| --- | --- | --- | --- |
| **`RemoteAddr` predicate** | Địa chỉ remote của request, thông thường là peer trực tiếp hoặc giá trị đã được WebFlux xử lý | YAML `RemoteAddr=10.0.1.0/24` | Đứng sau proxy thì địa chỉ thường là proxy, không phải client |
| **`XForwardedRemoteAddr` predicate** | HTTP header `X-Forwarded-For` | YAML `XForwardedRemoteAddr=198.51.100.0/24` | Chỉ khớp theo dữ liệu header; bản thân predicate không xác minh nguồn gốc header |
| **`XForwardedRemoteAddressResolver.maxTrustedIndex(n)`** | Danh sách địa chỉ trong `X-Forwarded-For`, chọn vị trí tính từ phải sang trái | Java DSL với `remoteAddr(resolver, CIDR...)` | Phải biết chắc số hop tin cậy, kiểm soát đường vào và sanitization ở proxy |

Tài liệu Spring mô tả `XForwardedRemoteAddr` nhận **ít nhất một CIDR** trong tham số `sources`, hỗ trợ IPv4/IPv6, dùng `X-Forwarded-For` để đối chiếu. Tài liệu không biến nó thành một bộ kiểm chứng chuỗi proxy hay thay thế việc giới hạn trust boundary.

### Cú pháp CIDR

CIDR gồm địa chỉ mạng và prefix length:

~~~text
198.51.100.0/24   → ví dụ một mạng IPv4 có 256 địa chỉ
10.0.0.0/8        → một dải địa chỉ riêng rất rộng; không thích hợp làm
                    danh sách client tin cậy nếu không có lý do rõ ràng
2001:db8::/32     → dải IPv6 minh họa trong tài liệu
~~~

CIDR **không phải biểu thức chính quy**. Điều này quan trọng vì thuộc tính `trusted-proxies` ở phần sau nhận **Java regular expression**, không nhận CIDR.

## 4. Ví dụ cấu hình XForwardedRemoteAddr

Giả sử proxy đầu vào được quản lý chặt chẽ, luôn làm sạch header XFF, và bạn muốn định tuyến những yêu cầu có địa chỉ được proxy xác nhận thuộc `198.51.100.0/24` sang backend riêng.

Ví dụ dùng namespace của **Spring Cloud Gateway Server WebFlux 5.x**:

~~~yaml
server:
  port: 8080

spring:
  application:
    name: gateway-routing-lab
  cloud:
    gateway:
      server:
        webflux:
          routes:
            - id: trusted-source-demo
              order: -10
              uri: http://localhost:9001
              predicates:
                - Path=/demo/**
                - Method=GET
                - XForwardedRemoteAddr=198.51.100.0/24
              filters:
                - AddResponseHeader=X-Lab-Route, trusted-source-demo
~~~

Điều kiện để route được chọn là **đồng thời** khớp `Path`, `Method` và `XForwardedRemoteAddr`. `AddResponseHeader` chỉ đánh dấu route được chọn trong bài lab; nó không thực hiện kiểm tra proxy hay xác thực.

Ví dụ tài liệu chính thức cũng dùng cú pháp ngắn gọn như:

~~~yaml
predicates:
  - XForwardedRemoteAddr=192.168.1.1/24
~~~

Địa chỉ `192.168.1.10` nằm trong dải được ví dụ này cho phép. Có thể cấu hình nhiều CIDR theo cú pháp tham số `sources` của phiên bản, nhưng cần xác định chính xác tập địa chỉ đáng tin và kiểm tra hành vi khi header có **nhiều hop** trước khi sử dụng để bảo vệ tài nguyên.

### Nếu dự án đang dùng Spring Cloud Gateway 4.3.x trở về trước

Theo tài liệu WebFlux **4.3.x, 4.2.x và các dòng cũ phù hợp**, chuyển nguyên phần danh sách route thành:

~~~yaml
spring:
  cloud:
    gateway:
      routes:
        - id: trusted-source-demo
          order: -10
          uri: http://localhost:9001
          predicates:
            - Path=/demo/**
            - Method=GET
            - XForwardedRemoteAddr=198.51.100.0/24
          filters:
            - AddResponseHeader=X-Lab-Route, trusted-source-demo
~~~

**Đừng để cả hai namespace `spring.cloud.gateway.routes` và `spring.cloud.gateway.server.webflux.routes` cùng định nghĩa các route trùng ID.** Khi thấy `404` cho mọi URL dù YAML trông đúng, hãy xác minh trước tiên rằng phiên bản gateway đã nạp các route từ đúng namespace.

### Predicate khớp không đồng nghĩa với 403 khi không khớp

Nếu request không thỏa `XForwardedRemoteAddr`, route trên **không được chọn**. Gateway tiếp tục tìm route khác; nếu không có handler nào khác, kết quả thường là **404**, không tự sinh 403. Một route tổng quát khác có thể nhận cùng request, nên **không dùng một route predicate đơn lẻ làm toàn bộ cơ chế phân quyền**.

Để trả `403 Forbidden` hoặc `401 Unauthorized` theo chính sách bảo mật, cấu hình Spring Security hay một lớp kiểm soát truy cập phù hợp, độc lập với việc route nào được chọn. Dịch vụ đích vẫn cần kiểm tra quyền nghiệp vụ cho tài nguyên mà nó sở hữu.

## 5. Giới hạn độ tin cậy bằng XForwardedRemoteAddressResolver

Khi thực sự cần chọn **địa chỉ client theo một số proxy tin cậy đã biết**, tài liệu WebFlux Gateway cung cấp `XForwardedRemoteAddressResolver` với hai cách:

- `trustAll()`: lấy IP đầu tiên trong `X-Forwarded-For`; **dễ bị spoofing** khi client có thể gửi header giả.
- `maxTrustedIndex(n)`: chọn IP theo số hop đáng tin phía trước gateway; `n` phải là số nguyên dương, được xác định từ **topology thật** và ràng buộc truy cập mạng.

Ví dụ tài liệu:

~~~http
X-Forwarded-For: 0.0.0.1, 0.0.0.2, 0.0.0.3
~~~

| `maxTrustedIndex(n)` | Địa chỉ được chọn |
| ---: | --- |
| `1` | `0.0.0.3` (phải nhất) |
| `2` | `0.0.0.2` |
| `3` | `0.0.0.1` (trái nhất) |
| `4` trở lên | `0.0.0.1` khi chuỗi chỉ có 3 địa chỉ |
| `0` hoặc âm | Không hợp lệ; báo lỗi khi khởi tạo resolver |

Với topology ở mục 2, header đã được WAF làm sạch là:

~~~http
X-Forwarded-For: 198.51.100.24, 10.0.1.10
~~~

`maxTrustedIndex(1)` cho `10.0.1.10`; `maxTrustedIndex(2)` cho `198.51.100.24`. Con số `2` chỉ hợp lý **khi gateway thực sự luôn được truy cập qua đúng hai hop proxy đã kiểm soát, các hop thêm header theo quy tắc mong đợi và không có đường bypass**.

Nếu thực tế chỉ có một proxy nhưng đặt `maxTrustedIndex(2)`, một phần tử giả ở bên trái có thể lại được chọn. Ngược lại, cấu hình quá thấp có thể lấy IP proxy thay vì client và làm các phép đo/rate limit hoặc route theo IP sai.

### 5.1. Ví dụ Java DSL với RemoteAddr và resolver

Khi cần kiểm soát vị trí XFF theo số hop thay vì dùng trực tiếp predicate `XForwardedRemoteAddr` trong YAML, có thể cấu hình route bằng Java DSL. Ví dụ sau **giả định hai proxy đầu vào tin cậy** và backend nghe tại `localhost:9001`:

~~~java
package demo.gateway;

import org.springframework.cloud.gateway.route.RouteLocator;
import org.springframework.cloud.gateway.route.builder.RouteLocatorBuilder;
import org.springframework.cloud.gateway.support.ipresolver.RemoteAddressResolver;
import org.springframework.cloud.gateway.support.ipresolver.XForwardedRemoteAddressResolver;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class GatewayRoutes {

    @Bean
    RouteLocator trustedClientRoutes(RouteLocatorBuilder builder) {
        RemoteAddressResolver resolver =
                XForwardedRemoteAddressResolver.maxTrustedIndex(2);

        return builder.routes()
                .route("partner-api", r -> r
                        .path("/partner/**")
                        .and()
                        .remoteAddr(resolver, "198.51.100.0/24")
                        .uri("http://localhost:9001"))
                .build();
    }
}
~~~

Ở đây `remoteAddr(resolver, ...)` lấy địa chỉ qua **resolver đã truyền vào**, rồi đối chiếu CIDR. Đó là route predicate `RemoteAddr` được điều chỉnh bằng resolver; không phải cách gán `maxTrustedIndex` vào cấu hình ngắn `XForwardedRemoteAddr=...`. Cấu hình Java cần được dùng trong dự án Spring Cloud Gateway **Server WebFlux** tương ứng, cùng dependency và BOM Spring Cloud tương thích.

> **Quan trọng về an toàn:** `maxTrustedIndex` chỉ chọn một **vị trí** trong danh sách XFF; nó không tự kiểm tra chứng chỉ của proxy, không khóa người ngoài kết nối trực tiếp vào gateway và không xác minh từng hop trong danh sách. Kiểm soát nguồn kết nối, làm sạch header đầu vào và giới hạn truy cập qua mạng vẫn là yêu cầu bắt buộc.

### 5.2. Đừng cố “đếm hop” từ chuỗi header tùy tiện

Số proxy đáng tin phải đến từ thiết kế triển khai (load balancer, CDN, WAF, ingress) và cách chúng thực tế ghi XFF. Những tình huống làm giả định sai gồm:

- Client có thể gọi trực tiếp gateway, bỏ qua ingress.
- Có request đi qua một WAF, request khác đi qua hai WAF hoặc CDN.
- Proxy đầu tiên nối thêm header mà không loại bỏ chuỗi từ Internet.
- Một lớp reverse proxy thay đổi cách đặt header hoặc gộp nhiều trường XFF.
- WebFlux `ForwardedHeaderTransformer` hay hạ tầng phía trước đã chuẩn hóa forwarded headers trước khi route predicate kiểm tra.

Nếu topology không cố định, nên chuẩn hóa địa chỉ client tại một boundary proxy đáng tin và truyền metadata đã kiểm chứng theo cơ chế rõ ràng, thay vì chọn một chỉ số cố định rồi xem kết quả là danh tính đáng tin.

## 6. Cấu hình trusted-proxies thay đổi theo phiên bản

Spring Cloud Gateway có khái niệm **`trusted-proxies`** liên quan đến các **`HttpHeadersFilters`** xử lý header `Forwarded` và `X-Forwarded-*` trước khi gửi request tới downstream. Nó dễ bị nhầm với `XForwardedRemoteAddr` hoặc `maxTrustedIndex`, nhưng vai trò **khác nhau**.

| Dòng WebFlux Gateway (theo tài liệu Spring) | Namespace khai báo route thường gặp | Thuộc tính cấu hình proxy tin cậy cho forwarded header filters |
| --- | --- | --- |
| **4.2.x** | `spring.cloud.gateway.routes` | `spring.cloud.gateway.trusted-proxies` |
| **4.3.x** | `spring.cloud.gateway.routes` | `spring.cloud.gateway.server.webflux.trusted-proxies` |
| **5.0.x / 5.1.x** | `spring.cloud.gateway.server.webflux.routes` | `spring.cloud.gateway.server.webflux.trusted-proxies` |

Giá trị của `trusted-proxies` là **Java regular expression** mô tả proxy tin cậy khi chúng xuất hiện trong header `Forwarded`/`X-Forwarded-*`, **không phải danh sách CIDR**. Ví dụ minh họa cho proxy mang địa chỉ `10.0.1.10` hoặc `10.0.1.20` trong các phiên bản dùng namespace mới:

~~~yaml
spring:
  cloud:
    gateway:
      server:
        webflux:
          trusted-proxies: '10\.0\.1\.(?:10|20)'
~~~

Đối với dòng 4.2, vị trí property theo tài liệu là:

~~~yaml
spring:
  cloud:
    gateway:
      trusted-proxies: '10\.0\.1\.(?:10|20)'
~~~

Đây là mẫu regex **minh họa**; hãy kiểm tra cách matching thực tế và các IP proxy thật trước khi triển khai. Tránh sử dụng biểu thức `.*` như một cấu hình “tin mọi proxy” trong môi trường công khai. Về phía mạng, vẫn phải khóa đường trực tiếp đến gateway và cấu hình proxy chuẩn hóa header.

### 6.1. Tham số này có tự bảo vệ XForwardedRemoteAddr không?

**Không nên giả định như vậy.** Tài liệu Spring trình bày `trusted-proxies` trong phần **HttpHeadersFilters**, còn `XForwardedRemoteAddr` nằm ở phần **Route Predicate Factories**. Việc bật `trusted-proxies` cho forwarded header filters không thay thế:

1. Xác minh kết nối vào gateway đi từ proxy được phép.
2. Làm sạch `X-Forwarded-For` do client tự gửi ở edge.
3. Chọn đúng địa chỉ trong chuỗi theo cơ chế được hỗ trợ.
4. Kiểm thử hành vi ở **đúng phiên bản** gateway, WebFlux và reverse proxy đang chạy.

Cũng phải phân biệt `XForwarded Headers Filter` của gateway, vốn xây dựng/cập nhật header chuyển **xuống backend**, với việc kiểm tra nguồn đáng tin của header **đi vào** gateway. Hai hướng xử lý có liên hệ nhưng không đồng nhất.

### 6.2. Một số tham số X-Forwarded khác

Các bản WebFlux mới có các property như `spring.cloud.gateway.server.webflux.x-forwarded.for-enabled` và `...for-append` để điều khiển việc tạo/nối thêm XFF trên **request chuyển tiếp**. Chúng hữu ích để thiết kế chuỗi trace/proxy nhưng **không tự biến giá trị XFF đầu vào thành đáng tin**.

Khi cần forwarded header chính xác để backend biết scheme HTTPS, original host hoặc đường dẫn gốc, hãy kiểm tra riêng cấu hình TLS termination và forwarding của ingress. Không nên lấy `X-Forwarded-Proto: https` do client tự gửi làm bằng chứng request đã đi qua HTTPS.

## 7. Mô hình bảo vệ thực tế theo ranh giới tin cậy

Một thiết kế vững chắc cần nhiều lớp, nhất là nếu IP tham gia vào route đặc quyền, allowlist đối tác, giới hạn lưu lượng hoặc nhận diện vị trí địa lý.

~~~mermaid
flowchart TD
    C["Client từ Internet"] --> E["Edge WAF / ingress<br/>xóa XFF do client cấp"]
    E --> A["Thiết lập / nối XFF<br/>theo IP peer đã quan sát"]
    A --> N{"Kết nối đến gateway<br/>được network policy cho phép?"}
    N -->|"Không"| D["Chặn ở lớp mạng"]
    N -->|"Có"| G["Gateway kiểm tra route<br/>và resolver theo topology"]
    G --> S["Spring Security / policy<br/>và phân quyền ở backend"]
    S --> B["Microservice"]
~~~

Các lớp kiểm soát nên được áp dụng:

1. **Khóa đường vào gateway:** security group, firewall, NetworkPolicy hoặc private listener chỉ cho load balancer/ingress được quản lý kết nối. Với cấu hình phát triển, `localhost` chỉ là mô hình đơn giản, không nói lên policy production.
2. **Sanitize tại proxy đầu tiên tin cậy:** loại header `X-Forwarded-For`/`Forwarded` do Internet gửi rồi tái tạo bằng IP peer quan sát được; các proxy nội bộ tiếp theo append theo quy tắc thống nhất. Trong một số hạ tầng, có chế độ proxy-protocol hay client-IP forwarding riêng, cần xác minh ngữ nghĩa.
3. **Cố định hoặc ghi nhận rõ topology:** biết có mấy hop trước gateway; chỉ dùng `maxTrustedIndex(n)` khi chuỗi thực sự phù hợp, và kiểm tra các lối vào ngoài ý định.
4. **Xác thực/phân quyền độc lập:** route predicate theo IP chỉ là điều kiện định tuyến. Các API nhạy cảm vẫn cần xác thực token/API key và phân quyền ở gateway/backend theo trách nhiệm.
5. **Quan sát mà không lộ dữ liệu:** có thể log route ID, địa chỉ peer đã kiểm chứng, client IP suy ra, số hop, quyết định route và trace ID; hạn chế log toàn bộ các forwarded header từ client và dữ liệu cá nhân. Tuân thủ chính sách lưu giữ log.

## 8. Thực hành kiểm tra và kiểm chứng rủi ro giả mạo

Thử nghiệm chỉ nên thực hiện trong **môi trường local/lab**. Dùng ứng dụng gateway cấu hình `trusted-source-demo` ở mục 4 (cổng `8080`) và một HTTP backend bất kỳ ở `localhost:9001` có endpoint xử lý `GET /demo/check`. Nếu backend trả 200, response qua route phù hợp có thêm `X-Lab-Route: trusted-source-demo`.

### 8.1. Gửi một giá trị XFF đơn

~~~bash
# Địa chỉ minh họa nằm trong 198.51.100.0/24:
curl -i "http://localhost:8080/demo/check" \
  -H "X-Forwarded-For: 198.51.100.24"

# Địa chỉ nằm ngoài dải được phép:
curl -i "http://localhost:8080/demo/check" \
  -H "X-Forwarded-For: 203.0.113.77"

# Không có X-Forwarded-For:
curl -i "http://localhost:8080/demo/check"
~~~

Với ví dụ chỉ có một route và không có handler khác, request đầu **có thể khớp route** và được chuyển backend, còn hai request sau thường không khớp và trả `404`. Chỉ coi đây là kết quả kỳ vọng khi phiên bản gateway và cấu hình proxy tương ứng xử lý các header đúng như bài lab.

**Nếu bạn gửi `X-Forwarded-For` tùy ý trực tiếp vào gateway và vẫn điều khiển được route thắng, đó là bằng chứng vì sao không thể lấy header này làm cơ sở bảo mật khi không có trusted ingress.** Kết quả thử nghiệm không chứng minh client được xác thực.

### 8.2. Tạo tình huống có hai hop

Sử dụng reverse proxy thật hoặc môi trường test tích hợp để kiểm chứng:

~~~http
X-Forwarded-For: 198.51.100.24, 10.0.1.10
~~~

Với Java DSL `maxTrustedIndex(2)` ở mục 5, giá trị được dùng để đối chiếu `198.51.100.0/24` phải là `198.51.100.24`, **nếu** chuỗi đã được proxy đầu vào kiểm soát như giả định. Kiểm thử thêm các trường hợp:

| Tình huống | Hành vi cần xác minh |
| --- | --- |
| Chuỗi hợp lệ hai proxy | Resolver chọn đúng IP client theo `n=2` |
| Client gửi XFF giả trước edge | Edge loại bỏ spoofed prefix, gateway không tin giá trị giả |
| Một proxy bị bypass | Cổng mạng không cho request đi tắt vào gateway |
| XFF thiếu hoặc sai định dạng | Route không được chấp nhận sai lệch; quan sát lỗi theo version |
| Số hop thay đổi | Kiểm tra lại giả định `maxTrustedIndex`, không giữ cứng cấu hình sai |
| IPv4/IPv6 hỗn hợp | Xác minh cách proxy định dạng và cách Gateway parse theo bản sử dụng |

### 8.3. Phân biệt 404, 403 và lỗi backend

- **404 do route không khớp:** nếu request không thỏa XFF predicate và không có route/handler khác. Backend không thấy request.
- **403 do chính sách truy cập:** khi Security/filter chủ động từ chối; không phải mặc định của predicate.
- **404/5xx từ backend:** route có thể đã khớp, gateway đã forward nhưng backend trả lỗi; phải kiểm tra log/trace cả hai phía.
- **503 khi discovery không tìm được instance:** nếu route dùng `lb://service-id` và không có instance, Gateway WebFlux LoadBalancer thường trả 503 mặc định. Lỗi này khác với predicate không khớp.

Khi gỡ lỗi nên theo thứ tự: **kết nối vào gateway → nội dung header sau trusted proxy → route predicate → chọn URL/instance → filter chain → backend → response**.

## 9. Câu hỏi thường gặp

### Có nên dùng XForwardedRemoteAddr để bảo vệ API nội bộ?

Có thể dùng nó như **một điều kiện định tuyến bổ trợ** khi toàn bộ đường đi của header đã được kiểm soát. Không dùng riêng nó thay thế firewall/NetworkPolicy, xác thực hay phân quyền. Nếu có route dự phòng `Path=/**` có thể chuyển cùng API sang backend khác, cần kiểm tra route order và bảo mật để tránh đường vòng ngoài ý muốn.

### CIDR của XForwardedRemoteAddr nên chứa IP client hay IP proxy?

Phụ thuộc mục tiêu chính sách và giá trị header được gateway đánh giá. Dải địa chỉ trong predicate áp dụng cho **địa chỉ được chọn từ XFF**, còn IP peer trực tiếp thuộc phạm vi kiểm soát kết nối mạng và `RemoteAddr`. Đừng đưa dải IP WAF vào allowlist client chỉ vì WAF đứng ngay trước gateway, hoặc coi địa chỉ XFF do người dùng cung cấp là “IP client tin cậy”.

### maxTrustedIndex có phải một thuộc tính trong YAML XForwardedRemoteAddr không?

Không. `maxTrustedIndex(n)` là phương thức tạo **`XForwardedRemoteAddressResolver`**, dùng qua API nhận `RemoteAddressResolver` (ví dụ Java DSL `remoteAddr(resolver, ...)`). Không tự thêm `maxTrustedIndex` vào cú pháp `XForwardedRemoteAddr=...` rồi giả định framework sẽ xử lý.

### Có nên bật trustAll để lấy IP trái nhất?

Tránh dùng `trustAll()` làm nguồn cho kiểm soát truy cập hoặc rate limit theo IP trong môi trường có thể nhận header từ Internet. Phương thức đó cố tình tin phần tử đầu XFF và được tài liệu Spring cảnh báo về spoofing.

### trusted-proxies có áp dụng giống nhau cho WebFlux và Server MVC không?

Không. Các dòng mới có property riêng như `spring.cloud.gateway.server.webflux.trusted-proxies` và `spring.cloud.gateway.server.webmvc.trusted-proxies`; các framework và filter thực thi khác nhau. Bài này chỉ trình bày ví dụ **WebFlux**. Khi chuyển sang MVC, phải đọc tài liệu tương ứng, không sao chép nguyên Java DSL/namespace của WebFlux.

## 10. Checklist trước khi dùng IP để ra quyết định

- [ ] Xác định chính xác phiên bản Spring Cloud Gateway, Spring Boot và mode WebFlux/MVC; dùng namespace cấu hình tương ứng.
- [ ] Vẽ topology client → CDN/WAF → ingress → gateway; biết điểm nào kết thúc TLS và điểm nào xử lý forwarded headers.
- [ ] Đảm bảo gateway không mở cổng bypass cho client bên ngoài đi thẳng vào.
- [ ] Proxy tin cậy đầu tiên đã xóa hoặc chuẩn hóa các forwarded headers từ nguồn không tin cậy.
- [ ] Biết rõ chính sách đang dùng `RemoteAddr`, `XForwardedRemoteAddr` hay `RemoteAddr` với `maxTrustedIndex`; không nhập nhằng.
- [ ] Khi dùng `maxTrustedIndex`, số hop và hướng append đã được xác minh trong môi trường chạy thật.
- [ ] `trusted-proxies` là **regex** theo đúng namespace/version, đã được kiểm thử; không coi đó là cơ chế xác thực đầu vào hoàn chỉnh.
- [ ] Có bài thử header spoofing, proxy bypass, header thiếu/sai, route fallback và status code.
- [ ] Authorization ở gateway/backend vẫn được áp dụng; rate limiting theo IP dựa trên địa chỉ đáng tin đã xác nhận.
- [ ] Log/trace cho thấy route ID, nguồn địa chỉ và kết quả xử lý mà không lộ token hoặc thông tin nhạy cảm.

## Tài liệu tham khảo và đối chiếu phiên bản

Các liên kết sau đến **tài liệu chính thức của Spring**; nên chọn đúng nhánh version khi nâng cấp:

1. [Route Predicate Factories — Spring Cloud Gateway Server WebFlux 5.1](https://docs.spring.io/spring-cloud-gateway/reference/spring-cloud-gateway-server-webflux/request-predicates-factories.html): mục `RemoteAddr`, `XForwardedRemoteAddressResolver` và `XForwardedRemoteAddr`.
2. [Route Predicate Factories — Spring Cloud Gateway 4.2](https://docs.spring.io/spring-cloud-gateway/reference/4.2/spring-cloud-gateway/request-predicates-factories.html): ví dụ namespace `spring.cloud.gateway.routes`.
3. [HttpHeadersFilters — Spring Cloud Gateway 4.2](https://docs.spring.io/spring-cloud-gateway/reference/4.2/spring-cloud-gateway/httpheadersfilters.html): `spring.cloud.gateway.trusted-proxies`.
4. [HttpHeadersFilters — Spring Cloud Gateway 4.3](https://docs.spring.io/spring-cloud-gateway/reference/4.3/spring-cloud-gateway-server-webflux/httpheadersfilters.html): `spring.cloud.gateway.server.webflux.trusted-proxies`.
5. [HttpHeadersFilters — Spring Cloud Gateway 5.1](https://docs.spring.io/spring-cloud-gateway/reference/spring-cloud-gateway-server-webflux/httpheadersfilters.html): các header chuyển tiếp và tham số `x-forwarded.*`.

**Ghi nhớ:** `XForwardedRemoteAddr` so khớp địa chỉ từ `X-Forwarded-For`; `RemoteAddr` mặc định dùng địa chỉ remote của request; `maxTrustedIndex(n)` cho phép chọn vị trí địa chỉ theo số hop giả định trong chuỗi XFF. Không cơ chế nào tự chứng minh proxy đáng tin. Hãy khóa đường truy cập gateway, chuẩn hóa header tại edge, áp dụng đúng property theo phiên bản và giữ xác thực/phân quyền độc lập với quyết định định tuyến.
