# Forwarded, X-Forwarded-* và thông tin proxy được tin cậy

## 1. Vì sao header chuyển tiếp quan trọng với API Gateway?

Trong kiến trúc microservices, client hiếm khi kết nối thẳng tới ứng dụng Spring Cloud Gateway. Request có thể đi qua CDN, WAF, load balancer, ingress và một hoặc nhiều reverse proxy trước khi đến gateway. Những thiết bị trung gian có thể thay đổi địa chỉ peer, scheme HTTPS/HTTP, `Host` và đường dẫn. Nếu không có thông tin về các chặng phía trước, dịch vụ đích khó biết URL bên ngoài mà client đã gọi.

**`Forwarded`** và họ header **`X-Forwarded-*`** được dùng để chuyển thông tin này giữa các proxy. Chúng thường tham gia vào việc tạo URL tuyệt đối, redirect, điều tra trace/log, xác định IP client và lựa chọn chính sách. Tuy nhiên, **header HTTP có thể do client tự gửi**. Gateway chỉ nên sử dụng thông tin proxy khi đã kiểm soát nguồn phát sinh và ranh giới tin cậy.

Bài này nằm trong chương **Header yêu cầu** của **SPRING_CLOUD_GATEWAY**. Kiến thức này bổ sung cho route predicate, filter chain, biến đổi path/header và khám phá dịch vụ; nó cũng ảnh hưởng trực tiếp đến xác thực, rate limiting theo IP, circuit breaker, retry, TLS và quan sát request khi vận hành cổng vào microservices an toàn.

Sau bài này, bạn có thể:

1. Phân biệt cấu trúc của `Forwarded` và các header `X-Forwarded-For/Host/Proto/Port/Prefix`.
2. Hiểu sự khác nhau giữa peer kết nối trực tiếp và IP client được **suy ra** qua proxy.
3. Thiết kế ranh giới tin cậy: xóa header đầu vào không đáng tin, thiết lập lại tại edge và chỉ nhận kết nối từ proxy được phép.
4. Cấu hình đúng **`trusted-proxies`** cùng các lựa chọn `x-forwarded.*` theo dòng Spring Cloud Gateway.
5. Phân biệt cơ chế của Spring WebFlux `ForwardedHeaderTransformer` với `HttpHeadersFilters` của Gateway.
6. Tự kiểm chứng trên backend và phát hiện hành vi giả mạo header trong môi trường thử nghiệm.

> **Phạm vi:** Ví dụ tập trung vào **Spring Cloud Gateway Server WebFlux**. Các phiên bản 4.2.x, 4.3.x và 5.x có khác biệt tên property. Gateway Server MVC dùng namespace và bộ lọc riêng, cần tham khảo tài liệu đúng biến thể.

## 2. Nhìn toàn bộ chuỗi proxy trước khi đọc header

Giả sử kiến trúc:

~~~mermaid
flowchart LR
    C["Client<br/>198.51.100.24"] -->|"HTTPS"| E["WAF / Edge<br/>10.0.1.10"]
    E -->|"HTTP hoặc HTTPS nội bộ"| I["Ingress<br/>10.0.1.20"]
    I --> G["Spring Cloud Gateway<br/>10.0.2.30"]
    G -->|"Route + filter + proxy"| B["orders-service"]
~~~

Trong ví dụ này, WAF là **điểm biên tin cậy đầu tiên**: nó nhận request từ Internet, xóa mọi giá trị `Forwarded` và `X-Forwarded-*` do client tự khai báo rồi tạo metadata mới từ kết nối thực tế. Ingress chỉ nhận traffic từ WAF và bổ sung metadata theo quy tắc đã thống nhất. Gateway chỉ nhận traffic từ ingress.

Khi đó, request đến gateway **có thể** mang:

~~~http
GET /api/orders/42 HTTP/1.1
Host: api.example.test
X-Forwarded-For: 198.51.100.24, 10.0.1.10
X-Forwarded-Proto: https
X-Forwarded-Host: api.example.test
X-Forwarded-Port: 443
~~~

Các địa chỉ trong ví dụ là địa chỉ minh họa. Một hệ thống thực có thể chọn chỉ truyền `Forwarded`, chỉ truyền `X-Forwarded-*`, hoặc cả hai nếu được cấu hình nhất quán.

| Khái niệm | Giá trị minh họa | Nguồn thông tin |
| --- | --- | --- |
| IP client thực | `198.51.100.24` | Kết nối mà WAF quan sát được; được tin **sau khi WAF làm sạch input** |
| Proxy thứ nhất | `10.0.1.10` | WAF, được ingress quan sát |
| Proxy kết nối trực tiếp tới gateway | `10.0.1.20` | Peer của kết nối đến gateway |
| Scheme client sử dụng | `https` | Kết nối client → WAF, nếu WAF xác nhận |
| Scheme giữa ingress và gateway | Có thể là `http` | Phụ thuộc TLS termination/re-encryption nội bộ |
| Host công khai | `api.example.test` | Được edge kiểm tra và chuyển theo quy tắc |

`198.51.100.0/24`, `192.0.2.0/24` và `203.0.113.0/24` là các dải IPv4 dành cho ví dụ tài liệu; `2001:db8::/32` là dải IPv6 minh họa. Không dùng chúng làm allowlist production.

**Không được đánh đồng ba thứ:** IP peer của TCP connection, địa chỉ ghi trong header XFF và địa chỉ client *đã được proxy xác minh*. Chỉ giá trị cuối cùng mới thích hợp cho các quyết định nhạy cảm, và nó phụ thuộc toàn bộ chuỗi trust.

## 3. Forwarded: định dạng chuẩn theo RFC 7239

RFC 7239 định nghĩa header chuẩn `Forwarded` để mô tả thông tin proxy theo các tham số:

| Tham số | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| `for` | Bên đã gửi request đến proxy tại hop tương ứng | `for=198.51.100.24` |
| `by` | Giao diện phía nhận của proxy | `by=10.0.1.10` |
| `host` | Host mà proxy nhìn thấy ở request đầu vào | `host=api.example.test` |
| `proto` | Scheme/protocol mà proxy nhận request | `proto=https` |

Ví dụ một hop:

~~~http
Forwarded: for=198.51.100.24;proto=https;host=api.example.test
~~~

Với nhiều proxy, các **forwarded element** được ngăn bởi **dấu phẩy**. Bên trong mỗi element, các cặp thuộc tính được ngăn bởi **dấu chấm phẩy**:

~~~http
Forwarded: for=198.51.100.24;proto=https;host=api.example.test, for=10.0.1.10;proto=https;host=api.example.test
~~~

Header có thể được biểu diễn bằng nhiều dòng header cùng tên tùy proxy và tầng HTTP. Khi parse, phải tôn trọng dấu ngoặc kép/escaping của RFC, không được tách chuỗi bằng `split(",")` và `split(";")` một cách mù quáng rồi coi là dữ liệu bảo mật đáng tin.

IPv6 thường cần quoted-string và ngoặc vuông:

~~~http
Forwarded: for="[2001:db8::1234]";proto=https;host=api.example.test
~~~

Theo RFC, `for` hoặc `by` cũng có thể mang tên ẩn danh hoặc giá trị `unknown`; vì vậy không phải mọi giá trị đều là IP có thể đem so CIDR. Header `Forwarded` mô tả metadata từ proxy, **không phải chữ ký số hoặc bằng chứng xác thực**.

### Khi nào Forwarded có ích?

Ví dụ client truy cập `https://api.example.test/account`, nhưng gateway nhận request nội bộ từ ingress bằng `http://gateway:8080/account`. Nếu ứng dụng backend tạo link tuyệt đối hoặc trả HTTP `Location` dựa vào URL nội bộ, nó có thể sinh sai scheme/host và dẫn đến redirect về hostname private. Header proxy được xác nhận giúp ứng dụng tái dựng URL bên ngoài, ví dụ `https://api.example.test/account`.

Ngược lại, nếu tin mù quáng giá trị `host=attacker.example` do client tự gửi, backend có thể phát sinh redirect/link sai miền hoặc sai cookie policy. Do đó cần **kiểm tra Host được cho phép và làm sạch header tại edge** trước khi dùng metadata để tạo URL.

## 4. X-Forwarded-*: họ header phổ biến trong thực tế

Khác với header chuẩn `Forwarded`, nhiều reverse proxy dùng các header `X-Forwarded-*` theo quy ước lịch sử. Chúng không nhất thiết chứa cùng nội dung hoặc định dạng với RFC 7239.

| Header | Ý nghĩa thường gặp | Ví dụ | Lưu ý |
| --- | --- | --- | --- |
| `X-Forwarded-For` | Chuỗi IP client và các proxy trước đó | `198.51.100.24, 10.0.1.10` | Phần tử trái nhất **không tự động** đáng tin |
| `X-Forwarded-Proto` | Scheme client dùng khi vào proxy | `https` | Có thể khác scheme nội bộ tới gateway |
| `X-Forwarded-Host` | Host công khai mà client gọi | `api.example.test` | Cần kiểm soát host header injection |
| `X-Forwarded-Port` | Cổng phía client/proxy | `443` | Không phải lúc nào cũng bằng port của gateway |
| `X-Forwarded-Prefix` | Prefix công khai bị proxy thay đổi trước khi forward | `/api` | Cần nhất quán với rewrite path; không phải mọi stack hỗ trợ giống nhau |
| `X-Forwarded-Ssl` | Một quy ước cũ mô tả kết nối SSL/TLS phía trước | `on` | Chỉ dùng khi cơ sở hạ tầng và framework hỗ trợ rõ ràng |

### 4.1. X-Forwarded-For khi có nhiều hop

Chuỗi thường được ghi theo hướng từ trái sang phải:

~~~text
X-Forwarded-For: client, proxy-trước, proxy-tiếp-theo
                 trái nhất              phải nhất
~~~

Thông thường proxy cuối ngay trước gateway **không nằm trong chuỗi XFF mà nó nhận/gửi** nếu địa chỉ của chính nó chưa được một hop tiếp theo append. Gateway vẫn có thể biết peer ngay trước qua thông tin kết nối.

Giả sử client xấu cố tình gửi:

~~~http
X-Forwarded-For: 203.0.113.99
~~~

Nếu WAF chỉ sử dụng thao tác append, chuỗi gateway nhận có thể thành:

~~~http
X-Forwarded-For: 203.0.113.99, 198.51.100.24, 10.0.1.10
~~~

Giá trị `203.0.113.99` **do client tự khai báo**. Một thành phần lấy IP trái nhất và tin nó sẽ sai. Edge WAF phải xóa giá trị từ Internet rồi tạo XFF từ địa chỉ peer đã quan sát, hoặc sử dụng cơ chế chuẩn hóa tương đương đã được kiểm chứng.

### 4.2. Prefix và URL bên ngoài

Ví dụ ingress cung cấp URL `https://api.example.test/edge/orders/42` nhưng strip `/edge` trước khi chuyển tiếp tới gateway, nên gateway nhận `/orders/42`. Nếu proxy tin cậy đặt `X-Forwarded-Prefix: /edge`, các thành phần hỗ trợ có thể dùng prefix đó khi tái dựng URL/link.

Điều này **không đồng nghĩa** với filter `StripPrefix`/`SetPath` của Gateway: các filter đó thay đổi **request path chuyển tới backend**, còn X-Forwarded-Prefix diễn đạt **ngữ cảnh đường dẫn công khai**. Nếu cấu hình cả hai sai thứ tự hoặc trùng prefix, kết quả có thể là link sai hoặc đường dẫn nhân đôi.

## 5. Hai chiều xử lý header trong Spring Cloud Gateway

Trong **Gateway Server WebFlux**, có hai lớp xử lý dễ nhầm:

1. **Header đến gateway:** các header do client/proxy gửi vào được WebFlux HTTP server tiếp nhận. Nếu được cấu hình, tầng WebFlux hoặc server có thể đọc thông tin forwarded để điều chỉnh URI/remote address của request hiện hành.
2. **Header từ gateway xuống backend:** các **`HttpHeadersFilters`** như `Forwarded Headers Filter` và `XForwarded Headers Filter` được áp dụng khi chuẩn bị HTTP request gửi đi, ví dụ trong `NettyRoutingFilter`.

~~~mermaid
flowchart TD
    C["Client / proxy"] --> I["HTTP request đến Gateway<br/>Forwarded, X-Forwarded-*"]
    I --> T["WebFlux / server xử lý<br/>forwarded input nếu đã cấu hình"]
    T --> M["Route predicate và<br/>gateway filter chain"]
    M --> H["HttpHeadersFilters:<br/>Forwarded, XForwarded,<br/>RemoveHopByHop"]
    H --> R["HTTP client của Gateway<br/>gửi đến service"]
    R --> B["Backend"]
~~~

**Không nên hiểu `trusted-proxies` là một tường lửa tự động chặn mọi kết nối từ IP khác.** Thuộc tính này tham gia cơ chế tin cậy/forward header của Gateway theo phiên bản. Việc kiểm soát **ai có thể kết nối gateway** vẫn cần firewall, ingress policy, network ACL hoặc tương đương; còn header đầu vào không đáng tin cần được xử lý tại proxy biên.

### 5.1. Forwarded Headers Filter

Theo tài liệu WebFlux Gateway, filter này tạo header `Forwarded` gửi tới downstream, dùng thông tin `Host`, scheme và port của request hiện tại và có thể bổ sung vào header hiện hữu theo chính sách tin cậy. Với các phiên bản hiện hành, để kích hoạt chức năng này cần cấu hình `trusted-proxies` bằng **Java regular expression**.

Trong dòng 4.3+/5.x, property `spring.cloud.gateway.server.webflux.forwarded.by.enabled=true` cho phép thêm phần `by`; giá trị mặc định tài liệu nêu là `false`.

### 5.2. XForwarded Headers Filter

Filter này tạo các trường `X-Forwarded-*` trên request gửi xuống backend, dựa vào host, scheme, port và path hiện hành. Các option có hậu tố:

- `for-enabled`, `host-enabled`, `port-enabled`, `proto-enabled`, `prefix-enabled` để bật/tắt tạo từng trường.
- `for-append`, `host-append`, `port-append`, `proto-append`, `prefix-append` để điều khiển append giá trị cũ hay không.

Theo tài liệu Spring Gateway 4.2/4.3/5.1, các tùy chọn trên **mặc định true** khi filter tương ứng được kích hoạt. Trong hệ thống có nhiều proxy, append cần được kiểm tra cẩn thận: append một danh sách chứa dữ liệu giả mạo từ Internet là sai, dù cú pháp HTTP có thể hợp lệ.

### 5.3. RemoveHopByHop Headers Filter

Các header chỉ có ý nghĩa trên **một kết nối HTTP** (hop-by-hop) không nên được chuyển qua proxy như header end-to-end. Gateway có filter loại bỏ theo danh sách mặc định được tài liệu nêu, gồm `Connection`, `Keep-Alive`, `Proxy-Authenticate`, `Proxy-Authorization`, `TE`, `Trailer`, `Transfer-Encoding` và `Upgrade`.

`Forwarded` và `X-Forwarded-*` **không phải** là cùng nhóm với hop-by-hop headers; việc xác minh chúng cần cơ chế tin cậy riêng. Khi dùng HTTP Upgrade/WebSocket hoặc một giao thức đặc biệt, phải xem filter/protocol handler tương ứng của Gateway thay vì vô hiệu hóa các biện pháp bảo vệ header một cách tùy tiện.

## 6. Cấu hình trusted-proxies theo phiên bản

Tài liệu chính thức có thay đổi namespace quan trọng:

| Spring Cloud Gateway Server WebFlux | Thuộc tính proxy tin cậy | Tùy chọn tạo XFF |
| --- | --- | --- |
| **4.2.x** | `spring.cloud.gateway.trusted-proxies` | `spring.cloud.gateway.x-forwarded.for-enabled` |
| **4.3.x** | `spring.cloud.gateway.server.webflux.trusted-proxies` | `spring.cloud.gateway.server.webflux.x-forwarded.for-enabled` |
| **5.0.x / 5.1.x** | `spring.cloud.gateway.server.webflux.trusted-proxies` | `spring.cloud.gateway.server.webflux.x-forwarded.for-enabled` |

Đặc biệt, dòng 4.3.x thường vẫn khai báo **routes** ở `spring.cloud.gateway.routes`, nhưng các property `trusted-proxies` / `x-forwarded.*` đã dùng tiền tố **`server.webflux`**. Dòng 5.x dùng `spring.cloud.gateway.server.webflux.routes`. Không suy ra namespace của mọi property chỉ bằng vị trí đặt route.

### 6.1. Ví dụ cho 4.3.x và 5.x

Giả sử chỉ có WAF `10.0.1.10` và ingress `10.0.1.20` là các proxy đã được quản lý, được ghi đúng trong forwarded chain. Cấu hình WebFlux để chọn chính sách tin cậy và kiểm soát các header chuyển tiếp:

~~~yaml
spring:
  cloud:
    gateway:
      server:
        webflux:
          trusted-proxies: '^(?:10\.0\.1\.10|10\.0\.1\.20)$'
          x-forwarded:
            for-enabled: true
            for-append: true
            host-enabled: true
            host-append: true
            proto-enabled: true
            proto-append: true
            port-enabled: true
            prefix-enabled: true
~~~

**Giá trị `trusted-proxies` là Java regex, không phải CIDR.** Các dấu chấm trong IP cần escape, như `10\.0\.1\.10`. YAML single quotes giúp giữ nguyên dấu gạch chéo ngược. Regex trên chỉ để **minh họa cú pháp**; cấu hình production phải đối chiếu cơ chế matching thực tế của đúng phiên bản, định dạng header mà proxy gửi và danh sách IP proxy thật. Không dùng `.*` để “tin tất cả” trong hệ thống mở ra Internet.

Lưu ý `for-append: true` có thể có ý nghĩa giữ lịch sử proxy **chỉ khi các header đầu vào đã được làm sạch**. Bật property không đồng nghĩa gateway đã nhận diện chính xác IP client; quan sát request xuống backend để chắc chắn chuỗi XFF không chứa giá trị giả mạo.

### 6.2. Ví dụ cho dòng 4.2.x

Ở Gateway WebFlux 4.2.x, namespace trong tài liệu là:

~~~yaml
spring:
  cloud:
    gateway:
      trusted-proxies: '^(?:10\.0\.1\.10|10\.0\.1\.20)$'
      x-forwarded:
        for-enabled: true
        for-append: true
        proto-enabled: true
        host-enabled: true
~~~

Các option filter ngoài phần khác biệt namespace nên được kiểm tra trong reference tương ứng với **phiên bản patch** đang chạy. Nếu sau nâng cấp mà backend đột nhiên không còn nhận `Forwarded` hoặc `X-Forwarded-*`, hãy kiểm tra thay đổi bảo mật của gateway và trạng thái `trusted-proxies` trước khi tăng độ rộng của regex.

### 6.3. Cảnh báo bảo mật đã được Spring công bố

Spring từng công bố **CVE-2025-41235** về việc Gateway Server chuyển tiếp `Forwarded`/`X-Forwarded-For` từ nguồn proxy không đáng tin. Theo advisory, các phiên bản bị ảnh hưởng gồm **4.2.0–4.2.2** và **4.1.0–4.1.7**; các bản sửa tương ứng gồm **4.2.3** và **4.1.8**. Những nhánh cũ khác cũng được advisory liệt kê.

Từ các bản sửa, hành vi forwarded header trở nên chặt chẽ hơn: khả năng forward của các header này bị vô hiệu hóa mặc định cho đến khi cấu hình proxy tin cậy phù hợp. **Không nên hạ cấp hoặc vô hiệu hóa kiểm tra chỉ để làm cho XFF xuất hiện lại**. Cần chọn phiên bản đã vá và kiểm tra cấu hình reverse proxy cùng property tương ứng.

Tham khảo [Spring Security Advisory — CVE-2025-41235](https://spring.io/security/cve-2025-41235/).

## 7. ForwardedHeaderTransformer của WebFlux khác gì HttpHeadersFilters?

Spring Framework WebFlux cung cấp `ForwardedHeaderTransformer` để **đọc các forwarded header trên request đi vào**, dùng chúng tái dựng một số thông tin URL/remote address của request và loại bỏ header đã xử lý; nó có thể được kích hoạt qua bean mang tên `forwardedHeaderTransformer` hoặc qua cấu hình Spring Boot phù hợp.

Trong các dòng Spring Boot 3.x, một cách cấu hình được tài liệu Boot mô tả là:

~~~yaml
server:
  forward-headers-strategy: framework
~~~

Chế độ này có thể khiến WebFlux xử lý forwarded input ở tầng framework. Chế độ `native` giao việc xử lý cho web server tương ứng; `none` không tự kích hoạt cơ chế này. **Tên property và hành vi chi tiết có thể thay đổi ở các dòng Spring Boot mới**, nên phải đọc tài liệu của đúng phiên bản. Không nên bật cả cơ chế native và framework một cách mù quáng.

Khác biệt:

| Thành phần | Vị trí | Mục tiêu chính |
| --- | --- | --- |
| `ForwardedHeaderTransformer` của Spring WebFlux | **Phía nhận** request, trước khi ứng dụng xử lý exchange | Tái dựng URI/remote theo forwarded input nếu được phép; loại bỏ headers sau xử lý |
| `Forwarded Headers Filter` của Gateway | **Phía gửi** request đến downstream | Tạo/bổ sung header chuẩn `Forwarded` |
| `XForwarded Headers Filter` của Gateway | **Phía gửi** request đến downstream | Tạo/bổ sung bộ `X-Forwarded-*` |
| Reverse proxy/ingress ở trust boundary | **Trước Gateway** | Xóa metadata do client tự khai và ghi metadata đã xác minh |

### 7.1. Chế độ removeOnly

Khi ứng dụng không muốn sử dụng bất cứ metadata forwarded nào do caller truyền, WebFlux có thể đăng ký transformer với chế độ **`removeOnly`**:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.server.adapter.ForwardedHeaderTransformer;

@Configuration
class ForwardedHeaderPolicy {

    @Bean(name = "forwardedHeaderTransformer")
    ForwardedHeaderTransformer forwardedHeaderTransformer() {
        ForwardedHeaderTransformer transformer =
                new ForwardedHeaderTransformer();
        transformer.setRemoveOnly(true);
        return transformer;
    }
}
~~~

Ví dụ này hướng đến **lớp WebFlux nhận request**: nó loại forwarded headers mà không dùng để sửa metadata request. Cần chọn một cách cấu hình thống nhất; không sao chép bean này cùng cấu hình `server.forward-headers-strategy=framework` khi chưa xem auto-configuration của phiên bản đang chạy.

Nếu gateway cần nhận metadata từ ingress đáng tin và đồng thời tái tạo forwarded headers xuống backend, chọn chế độ `removeOnly` có thể làm mất thông tin cần truyền. Việc có dùng transformer hay không phải là quyết định **theo ranh giới tin cậy và mục đích**, không phải một mẹo bật/tắt để sửa status HTTP.

### 7.2. Điều gì xảy ra với remote address?

Trước khi xử lý forwarded input, `exchange.getRequest().getRemoteAddress()` thường phản ánh **peer kết nối trực tiếp** (ingress). Sau khi một thành phần xử lý forwarded header ở tầng WebFlux hoặc web server, giá trị remote request có thể đã được tái dựng thành IP suy ra từ header.

Vì thế, khi dùng `RemoteAddr` predicate, `XForwardedRemoteAddr` predicate hoặc triển khai rate limiter theo IP, phải xác định **bạn đang so khớp giá trị nào**, nó có được chuẩn hóa đáng tin hay chưa, và các lớp trước đó đã xử lý header ra sao. `trusted-proxies` của HttpHeadersFilters và resolver phục vụ route predicate không mặc nhiên thay thế nhau.

## 8. Thiết kế ranh giới tin cậy ở proxy biên

Một kiến trúc an toàn phải kết hợp **quy tắc mạng** với **quy tắc header**:

~~~mermaid
flowchart TD
    C["Internet: request có thể chứa<br/>Forwarded giả"] --> E["Edge WAF / ingress"]
    E --> X["Xóa Forwarded và X-Forwarded-*<br/>do client tự khai"]
    X --> V["Tạo metadata từ TLS, peer IP,<br/>host đã kiểm tra"]
    V --> N{"Chỉ proxy được phép<br/>kết nối Gateway?"}
    N -->|"Không"| D["Chặn tại network boundary"]
    N -->|"Có"| G["Gateway xử lý theo<br/>version + trusted-proxies"]
    G --> B["Backend xác thực / phân quyền<br/>và quan sát request"]
~~~

Một số nguyên tắc triển khai:

1. **Không mở cổng bypass:** gateway chỉ được nhận traffic từ proxy được quản lý. Nếu client có thể gọi thẳng gateway và tự cung cấp forwarded headers, mô hình tin cậy đã bị phá vỡ.
2. **Xóa cả hai họ header ở biên:** ngay cả khi chỉ dùng `X-Forwarded-*`, cần loại giá trị `Forwarded` không đáng tin; một dịch vụ phía sau có thể ưu tiên header chuẩn.
3. **Ghi lại metadata từ kết nối thực:** IP client lấy từ peer mà edge nhìn thấy; `proto=https` chỉ được ghi khi edge thực sự nhận HTTPS. Kiểm tra Host với allowlist để tránh sinh redirect/link theo host do attacker chỉ định.
4. **Proxy nội bộ thống nhất quy tắc append:** các hop sau chỉ chấp nhận kết nối từ hop trước, rồi append IP đã quan sát theo một định dạng được kiểm thử. Không để topology biến động mà vẫn suy luận IP client từ một vị trí cố định.
5. **Bảo vệ từng chặng:** TLS đến edge không mã hóa mặc định kết nối edge → ingress → gateway → service. Cân nhắc HTTPS/mTLS nội bộ, policy mạng và bảo vệ secrets/token.
6. **Xác thực độc lập với IP:** forwarding header chủ yếu phục vụ định tuyến, URL reconstruction và quan sát. Phân quyền nghiệp vụ và token validation vẫn cần được thực thi ở các tầng phù hợp.

### 8.1. Minh họa cách edge Nginx tái tạo header

Ví dụ **chỉ minh họa phần cấu hình trong `location`** khi Nginx chính là proxy public đầu tiên, đã terminate TLS và kiểm soát `server_name`/Host. Nó không bao gồm chứng chỉ, upstream và cấu hình mạng:

~~~nginx
location / {
    proxy_pass http://gateway_upstream;

    # Không chuyển tiếp Forwarded do client tự khai.
    proxy_set_header Forwarded "";

    # Tạo lại metadata từ kết nối/host đã được edge kiểm tra.
    proxy_set_header X-Forwarded-For $remote_addr;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_set_header X-Forwarded-Host $host;
    proxy_set_header X-Forwarded-Port $server_port;
    proxy_set_header Host $host;
}
~~~

Ở **edge đầu tiên**, `$remote_addr` chính là peer mà Nginx quan sát, nên ví dụ **không** dùng `$proxy_add_x_forwarded_for` để vô tình giữ XFF giả do Internet cung cấp. Với một proxy **nội bộ phía sau edge đã được làm sạch**, việc append địa chỉ peer có thể hợp lý, nhưng cần giới hạn inbound chỉ từ edge và kiểm tra kết quả trên toàn chuỗi.

Trong hạ tầng CDN/managed load balancer, `$remote_addr` có thể là IP CDN chứ chưa phải client thật. Khi đó phải dùng cơ chế nhận diện upstream *đã xác minh* của nhà cung cấp và cấu hình allowlist phù hợp; không thay `$remote_addr` bằng `$http_x_forwarded_for` một cách tùy tiện.

## 9. Thực hành quan sát header tại backend

Hãy triển khai thử nghiệm trong môi trường **local/lab**, trước khi áp dụng policy production. Mục tiêu là thấy header **thực sự được gửi tới backend**, không chỉ thấy header client gửi vào gateway.

### 9.1. Echo backend WebFlux

Tạo một ứng dụng Spring Boot có dependency `spring-boot-starter-webflux`, lắng nghe `localhost:9091`:

~~~yaml
# src/main/resources/application.yml của backend
server:
  port: 9091
~~~

Đặt class khởi chạy và controller vào cùng package `demo.echo`:

~~~java
package demo.echo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class EchoApplication {
    public static void main(String[] args) {
        SpringApplication.run(EchoApplication.class, args);
    }
}
~~~

~~~java
package demo.echo;

import java.util.LinkedHashMap;
import java.util.Map;

import org.springframework.http.server.reactive.ServerHttpRequest;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class EchoController {

    @GetMapping("/echo/{id}")
    public Map<String, Object> inspect(@PathVariable String id,
                                       ServerHttpRequest request) {
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("id", id);
        result.put("uri", request.getURI().toString());
        result.put("path", request.getPath().value());
        result.put("remoteAddress",
                String.valueOf(request.getRemoteAddress()));
        result.put("forwarded",
                request.getHeaders().getFirst("Forwarded"));
        result.put("xff",
                request.getHeaders().getFirst("X-Forwarded-For"));
        result.put("xfProto",
                request.getHeaders().getFirst("X-Forwarded-Proto"));
        result.put("xfHost",
                request.getHeaders().getFirst("X-Forwarded-Host"));
        result.put("xfPrefix",
                request.getHeaders().getFirst("X-Forwarded-Prefix"));
        return result;
    }
}
~~~

Đây là endpoint **chẩn đoán**: không công khai các forwarded headers và remote address của người dùng thật trên Internet. Chỉ dùng trong môi trường test cô lập và xóa hoặc bảo vệ endpoint trước khi deploy production.

### 9.2. Route Gateway tới backend

Ví dụ route dùng namespace của **Gateway Server WebFlux 5.x**:

~~~yaml
server:
  port: 8080

spring:
  cloud:
    gateway:
      server:
        webflux:
          routes:
            - id: echo-headers
              uri: http://localhost:9091
              predicates:
                - Path=/api/echo/**
              filters:
                - StripPrefix=1
                - AddResponseHeader=X-Lab-Route, echo-headers
~~~

Ở WebFlux 4.2/4.3, đặt nguyên danh sách `routes` dưới `spring.cloud.gateway.routes`. Kết hợp với **một cấu hình `trusted-proxies` tương ứng** nếu hệ thống thật có reverse proxy tin cậy phía trước, như mục 6.

Khi client gọi `/api/echo/42`, backend nhận path `/echo/42`. Header `X-Lab-Route` chỉ đánh dấu response đã đi qua route của lab; nó không chứng minh các header forwarding đã được tin cậy.

Khởi động backend và gateway trong hai terminal ở đúng thư mục dự án (ví dụ Maven Wrapper):

~~~bash
./mvnw spring-boot:run
~~~

Trong Windows PowerShell có thể dùng `mvnw.cmd spring-boot:run`. Đây là hướng dẫn thực hành; bài viết không khẳng định đã chạy ứng dụng.

### 9.3. So sánh request trực tiếp và request qua edge tin cậy

Gọi backend trực tiếp:

~~~bash
curl -i "http://localhost:9091/echo/42"
~~~

Gọi qua gateway trong lab:

~~~bash
curl -i "http://localhost:8080/api/echo/42"
~~~

Nếu có ingress/WAF riêng, test qua **địa chỉ công khai của proxy đó** (đã triển khai và cấp TLS hợp lệ):

~~~bash
curl -i "https://api.example.test/api/echo/42"
~~~

Khi đi qua đúng edge đã cấu hình, backend **có thể** thấy `X-Forwarded-For` là chuỗi IP đã xác minh và `X-Forwarded-Proto: https`; kết quả thực tế phụ thuộc chính sách của proxy, phiên bản gateway, trust regex và việc backend có tự tiêu thụ forwarded headers hay không. Không suy đoán giá trị cụ thể chỉ từ việc `curl` trả 200.

### 9.4. Kiểm thử header do client giả mạo

Chỉ thực hiện trên gateway test của bạn:

~~~bash
curl -i "http://localhost:8080/api/echo/42" \
  -H "Forwarded: for=203.0.113.99;proto=https;host=attacker.example" \
  -H "X-Forwarded-For: 203.0.113.99" \
  -H "X-Forwarded-Proto: https" \
  -H "X-Forwarded-Host: attacker.example"
~~~

**Kỳ vọng về bảo mật:** các giá trị tự khai không được biến thành IP/scheme/host đáng tin cho chính sách truy cập hoặc URL sinh ra phía backend. Hành vi header có thể khác theo version/cấu hình; hãy kiểm tra request echo và log của proxy/gateway. Nếu backend thấy giá trị giả như thông tin đáng tin, cần sửa edge sanitization, đường bypass, cấu hình forwarded input hoặc trusted proxies.

**Không nên “sửa” bằng cách đặt `trusted-proxies: '.*'`**. Regex rộng có thể mở lại rủi ro mà các bản vá bảo mật đã cố ngăn.

### 9.5. Bảng kiểm tra hai chiều

| Tình huống | Quan sát cần có | Lỗi thường gặp |
| --- | --- | --- |
| Client → edge qua HTTPS | Edge biết scheme client thật và Host đã được allowlist | Backend tạo link `http://...` do tin scheme nội bộ |
| Client cố gửi `Forwarded`/XFF giả | Edge xóa các giá trị tự khai | Client kiểm soát IP hoặc Host xuất hiện trên backend |
| Edge → gateway | Gateway chỉ nhận từ nguồn proxy được phép | Có cổng public bypass ingress |
| Gateway → backend | Header mà backend nhận phù hợp chính sách `HttpHeadersFilters` | Header bị mất sau nâng cấp bản vá hoặc append sai |
| Path rewrite tại ingress/gateway | `X-Forwarded-Prefix` và path cuối không mâu thuẫn | Redirect nhân đôi prefix |
| Sinh 301/302 hoặc absolute URL | `Location` có scheme/host công khai hợp lệ | Open redirect/host header injection |
| Dùng IP cho rate limit hoặc route | IP đã được chuẩn hóa, nguồn rõ ràng | Nhiều client bị gộp thành IP proxy hoặc attacker đổi khóa |
| Backend trả 4xx/5xx | Phân biệt Gateway từ chối với lỗi backend | Nhầm lỗi xác thực/rate limiter thành lỗi XFF |

## 10. Những lỗi thiết kế thường gặp

### 10.1. Tin IP trái nhất trong X-Forwarded-For

Giá trị trái nhất thường được gọi là “client IP” trong tài liệu proxy, nhưng kẻ tấn công có thể tự thêm phần tử ở đầu chuỗi. Chỉ lấy địa chỉ sau khi kiểm soát tất cả proxy tham gia và áp dụng mô hình trust đúng. Với các route predicate `XForwardedRemoteAddr` hoặc resolver `XForwardedRemoteAddressResolver.maxTrustedIndex(n)`, hãy hiểu rõ chúng chọn địa chỉ nào và **không** tự chứng minh địa chỉ đó đã được xác thực.

### 10.2. Lẫn route predicate với cơ chế trust header

`Path`, `Host`, `RemoteAddr` hoặc `XForwardedRemoteAddr` quyết định route có khớp không. `trusted-proxies` thuộc xử lý forwarded header của Gateway. Các cơ chế này không tự thay thế authorization, NetworkPolicy hay cấu hình WAF. Một route fallback rộng có thể tiếp nhận request không khớp route IP allowlist; hãy kiểm tra tất cả các tuyến và chính sách bảo mật.

### 10.3. Cấu hình nhiều tầng xử lý forwarded cùng lúc

Ví dụ edge đã tái tạo `Forwarded`, Gateway bật `ForwardedHeaderTransformer` và `HttpHeadersFilters` tiếp tục append header xuống backend. Nếu không kiểm tra vòng đời header, thông tin có thể bị ghi trùng, mất hoặc khác nhau giữa hai dạng chuẩn và XFF. Phải xác định **thành phần nào ghi giá trị nguồn**, thành phần nào đọc, thành phần nào chuyển tiếp và thành phần nào xóa.

### 10.4. Coi X-Forwarded-Proto là bằng chứng TLS

Một header `X-Forwarded-Proto: https` do client tự gửi **không chứng minh** client đã kết nối HTTPS. TLS phải được xác nhận tại điểm kết thúc TLS; kết nối Gateway → backend cần HTTPS/mTLS riêng nếu có yêu cầu bảo vệ. Khi tạo URL redirect hoặc secure cookie, hãy dùng metadata đã qua trust boundary.

### 10.5. Log mọi header để chẩn đoán

Access token, cookie và nội dung định danh nhạy cảm có thể lọt vào log. Chỉ ghi các trường cần thiết như route ID, trace ID, status, latency, IP đã xác minh (theo chính sách bảo vệ dữ liệu), số hop proxy và kết quả kiểm tra nguồn. Không công khai endpoint echo nội bộ ở production.

## 11. Checklist trước khi đưa vào production

- [ ] Xác nhận đúng **Spring Cloud Gateway Server WebFlux** và version, đặc biệt namespace `trusted-proxies` và `x-forwarded.*`.
- [ ] Dùng nhánh Spring Cloud Gateway đã vá các advisory liên quan đến forwarded headers.
- [ ] Vẽ rõ đường client → CDN/WAF → load balancer → ingress → gateway → microservice.
- [ ] Không có đường trực tiếp từ Internet tới gateway bỏ qua trust boundary.
- [ ] Proxy public đầu tiên xóa **cả** `Forwarded` và `X-Forwarded-*` do client gửi.
- [ ] Edge tạo header từ IP peer và TLS/Host thật; Host được kiểm tra bằng danh sách cho phép.
- [ ] Các proxy nội bộ chỉ nhận traffic từ hop tin cậy trước đó và append theo quy ước thống nhất.
- [ ] `trusted-proxies` dùng Java regex đúng namespace, không tin mọi địa chỉ và được thử bằng request thực.
- [ ] Xác định rõ có cần Spring Boot/WebFlux `ForwardedHeaderTransformer` hay không; kiểm thử nếu bật `framework`, `native` hoặc `removeOnly`.
- [ ] Kiểm thử cả `Forwarded` và các header XFF, gồm header giả mạo, thiếu, lặp, đa hop và IPv6.
- [ ] Xác minh route predicate, rate limiter, redirect, link tuyệt đối và log dựa trên **dữ liệu đã được xác minh**, không dựa vào header bất kỳ.
- [ ] Giữ xác thực/phân quyền ở Gateway và backend theo trách nhiệm; IP chỉ là tín hiệu bổ trợ.
- [ ] Quan sát request tại gateway **và** backend, nhưng không ghi token, cookie hay dữ liệu nhạy cảm.

## 12. Tài liệu tham khảo theo phiên bản

Các nguồn chính thức để kiểm tra cú pháp và giới hạn:

1. [RFC 7239 — Forwarded HTTP Extension](https://www.rfc-editor.org/rfc/rfc7239.html): cấu trúc `for`, `by`, `host`, `proto`, multi-hop và escaping.
2. [Spring Cloud Gateway Server WebFlux 5.x — HttpHeadersFilters](https://docs.spring.io/spring-cloud-gateway/reference/spring-cloud-gateway-server-webflux/httpheadersfilters.html): `Forwarded`, `XForwarded`, `RemoveHopByHop` và namespace mới.
3. [Spring Cloud Gateway Server WebFlux 4.3.x — HttpHeadersFilters](https://docs.spring.io/spring-cloud-gateway/reference/4.3/spring-cloud-gateway-server-webflux/httpheadersfilters.html): `server.webflux.trusted-proxies` và lựa chọn X-Forwarded.
4. [Spring Cloud Gateway 4.2.x — HttpHeadersFilters](https://docs.spring.io/spring-cloud-gateway/reference/4.2/spring-cloud-gateway/httpheadersfilters.html): `spring.cloud.gateway.trusted-proxies` và prefix cũ.
5. [Spring Framework WebFlux — ForwardedHeaderTransformer](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/reactive-spring.html): forwarded input, remove-only và ranh giới bảo mật.
6. [Spring Boot — Running Behind a Front-end Proxy](https://docs.spring.io/spring-boot/3.5/how-to/webserver.html): forwarding strategy trong Boot 3.x.
7. [Spring Security Advisory CVE-2025-41235](https://spring.io/security/cve-2025-41235/): các phiên bản bị ảnh hưởng và yêu cầu cấu hình proxy tin cậy ở bản vá.

**Ghi nhớ:** `Forwarded` và `X-Forwarded-*` giúp các service hiểu ngữ cảnh request trước proxy, nhưng **chúng chỉ đáng tin khi được tạo hoặc chuẩn hóa tại một proxy thuộc trust boundary đã kiểm soát**. Trong Spring Cloud Gateway, phân biệt việc xử lý header **đi vào** của WebFlux với `HttpHeadersFilters` **gửi xuống backend**, dùng đúng property theo phiên bản, kiểm tra spoofing trên toàn chuỗi và không dùng các header này thay thế xác thực hay phân quyền.
