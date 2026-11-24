# RouteDefinition, Route và quá trình chuyển đổi cấu hình trong Spring Cloud Gateway

Trong **SPRING_CLOUD_GATEWAY**, việc khai báo một route bằng YAML mới chỉ là bước mô tả ý định: request nào được nhận, chuyển đến đâu và áp dụng những filter nào. Để xử lý HTTP thật, Spring Cloud Gateway phải chuyển mô tả đó thành một **Route có thể thực thi**, chứa predicate dùng để so khớp request và các đối tượng filter dùng trong chuỗi xử lý.

Bài học thuộc chương **Kiến trúc xử lý**, giải thích đường đi **cấu hình → `RouteDefinition` → `Route` → lựa chọn route khi có request → filter chain → downstream**. Hiểu rõ các bước này giúp chẩn đoán các lỗi như “khai báo đã có nhưng route không xuất hiện”, “route được đăng ký nhưng không match”, “filter đặt trong YAML nhưng không chạy”, hoặc “route được cập nhật nhưng hệ thống vẫn dùng bản cũ”.

> **Phạm vi ví dụ:** Các tên lớp Java và cấu hình YAML chính minh họa **Spring Cloud Gateway Server WebFlux** thuộc các dòng có API/cấu trúc tương ứng, đặc biệt là Gateway 4.x. **Gateway Server MVC** có pipeline và cơ chế định tuyến riêng. Tên starter, thuộc tính và cách quản lý route có thể đổi theo phiên bản; luôn đối chiếu tài liệu đúng release train trước khi áp dụng.

## 1. Hai mô hình cần tách bạch

Ở cấp kiến trúc, Gateway thực hiện hai công việc khác nhau:

1. **Tạo mô hình định tuyến từ cấu hình**: tải các khai báo route từ file cấu hình, repository, discovery hoặc nguồn khác; chuyển chúng thành predicate và GatewayFilter có thể thực thi.
2. **Xử lý từng request HTTP**: tìm một Route phù hợp với request đến, chạy filter chain, chuyển tiếp request đến upstream/downstream tương ứng rồi trả response.

Hai công việc liên quan nhưng **không phải mỗi request đều đọc và phân tích lại YAML**. Gateway duy trì tập route đã được tạo hoặc cache; việc làm mới tập route có quy trình riêng.

~~~mermaid
flowchart TD
    subgraph BUILD["Giai đoạn xây dựng / làm mới routes"]
        A["application.yml, repository, discovery"] --> B["RouteDefinitionLocator"]
        B --> C["RouteDefinition"]
        C --> D["RouteDefinitionRouteLocator"]
        P["RoutePredicateFactory"] --> D
        F["GatewayFilterFactory"] --> D
        D --> E["Route (predicate + filters + URI + metadata)"]
        E --> L["RouteLocator / cache routes"]
    end
    subgraph REQUEST["Giai đoạn xử lý HTTP"]
        R["HTTP request"] --> H["RoutePredicateHandlerMapping"]
        L --> H
        H --> M{"Có route khớp?"}
        M -->|"Không"| N["Không chuyển tiếp theo route này; thường trả 404"]
        M -->|"Có"| W["FilteringWebHandler"]
        W --> G["GlobalFilter + GatewayFilter"]
        G --> U["Routing filter / downstream"]
        U --> V["Response về client"]
    end
~~~

Sơ đồ mô tả các thành phần cốt lõi. Trong vận hành thực tế, bộ lọc bảo mật, handler của Spring WebFlux, cache, load balancer và các bộ lọc xử lý response cũng tham gia theo cấu hình.

## 2. `RouteDefinition`: mô tả route ở mức cấu hình

`RouteDefinition` là **đối tượng dữ liệu mô tả** một tuyến đường. Trong Gateway Server WebFlux, nó thường được xây từ cấu hình đã bind hoặc do một `RouteDefinitionLocator` cung cấp. Nó có các thông tin chính:

| Thuộc tính | Vai trò | Ví dụ |
|---|---|---|
| `id` | Định danh route để quản lý và quan sát | `orders-read` |
| `uri` | Đích chuyển tiếp hoặc scheme cho bước routing | `http://localhost:9090`, `lb://order-service` |
| `predicates` | Danh sách khai báo điều kiện nhận request | `Path=/api/orders/**`, `Method=GET` |
| `filters` | Danh sách khai báo các filter riêng cho route | `StripPrefix=1`, `SetRequestHeader=...` |
| `order` | Độ ưu tiên **giữa các route** khi tìm route khớp | `-10` |
| `metadata` | Dữ liệu bổ sung để phân loại hoặc tích hợp xử lý | `owner: orders-team` |

Ví dụ YAML sau thể hiện một `RouteDefinition` ở dạng khai báo thường dùng cho Gateway Server WebFlux 4.x:

~~~yaml
spring:
  cloud:
    gateway:
      routes:
        - id: orders-read
          order: -10
          uri: http://localhost:9090
          predicates:
            - Path=/api/orders/**
            - Method=GET
          filters:
            - StripPrefix=1
            - SetRequestHeader=X-Gateway-Route,orders-read
          metadata:
            owner: orders-team
~~~

Ý nghĩa:

- Route có ID `orders-read`, ưu tiên `-10` khi so với route có `order` lớn hơn.
- Chỉ request có đường dẫn khớp `/api/orders/**` **và** phương thức `GET` mới qua được toàn bộ predicate của route.
- Sau khi route được chọn, `StripPrefix=1` loại phân đoạn đầu của path; `SetRequestHeader` đặt header trên request gửi tới backend.
- `uri` chỉ đích `http://localhost:9090`. Đây là địa chỉ **downstream nhìn từ môi trường đang chạy Gateway**, không nhất thiết là `localhost` của máy client.
- `metadata.owner` là dữ liệu ví dụ do người dùng đặt. Nó **không tự tạo hành vi** nào nếu không có thành phần đọc metadata đó.

**Quan trọng:** YAML trên không phải bản thân object `Route` đã chạy được. Các giá trị `Path`, `Method`, `StripPrefix`... vẫn là **khai báo tên và tham số** cần được Gateway giải mã thành các đối tượng xử lý.

### PredicateDefinition và FilterDefinition

Trong mô hình khai báo, mỗi phần tử `predicates` tương ứng một `PredicateDefinition`, còn mỗi phần tử `filters` tương ứng một `FilterDefinition`. Chúng lưu tên factory và tập tham số được phân tích từ cú pháp ngắn hoặc dạng cấu hình mở rộng.

Ví dụ:

~~~yaml
predicates:
  - Path=/api/orders/**
  - Method=GET
filters:
  - StripPrefix=1
~~~

Ở đây `Path` và `Method` là tên của **RoutePredicateFactory** tương ứng; `StripPrefix` là tên một **GatewayFilterFactory**. Các khai báo trên chưa trực tiếp là lambda nhận request hoặc filter có thể gọi `filter(exchange, chain)`.

Không phải mọi thuộc tính trong YAML đều là `RouteDefinition`: một số nhóm cấu hình như `default-filters`, global CORS, HTTP client hoặc discovery được quản lý ở cấp Gateway và áp dụng qua bước xây dựng hay runtime riêng.

## 3. `Route`: mô hình có thể đánh giá và thực thi

Trong Gateway Server WebFlux, một `Route` đã được tạo có những thành phần quan trọng như:

- **ID**, **URI**, **order** và **metadata** được mang theo từ mô tả hoặc được đặt qua DSL.
- **Predicate có thể thực thi**, thường ở dạng bất đồng bộ gắn với `ServerWebExchange`, dùng để kiểm tra request có thuộc route hay không.
- **Danh sách `GatewayFilter` đã được khởi tạo**, dùng để xử lý request/response nếu route được chọn.

Sự khác biệt có thể hình dung như sau:

| `RouteDefinition` | `Route` |
|---|---|
| Mô tả *muốn làm gì* bằng tên và tham số | Chứa thành phần *thực sự làm được* các bước đã mô tả |
| `Path=/api/orders/**` là cấu hình | Predicate đã xây để kiểm tra `ServerWebExchange` |
| `StripPrefix=1` là định nghĩa filter | `GatewayFilter` đã tạo với giá trị `parts=1` |
| Phù hợp để lưu, tải, thay đổi cấu hình | Phù hợp để Gateway so khớp và xử lý request |
| Được lấy qua `RouteDefinitionLocator` | Được cung cấp qua `RouteLocator` |

Đừng hiểu `Route` là một request đã được định tuyến. `Route` là đối tượng đại diện cho quy tắc có thể áp dụng cho **nhiều request**. Mỗi request có `ServerWebExchange` riêng và chỉ được gắn với route sau khi predicate khớp.

## 4. Các nguồn tạo `RouteDefinition`

Trong Gateway Server WebFlux, interface `RouteDefinitionLocator` đại diện cho **nguồn đọc các định nghĩa route**. Một hệ thống có thể có nhiều nguồn:

| Nguồn | Cách hoạt động thường gặp | Lưu ý |
|---|---|---|
| Cấu hình tĩnh | Binding danh sách routes từ application YAML/properties | Sửa file chưa chắc làm thay đổi route runtime nếu không reload/refresh phù hợp |
| Repository lưu route | Định nghĩa được lưu trong một `RouteDefinitionRepository` | Thao tác lưu/xóa và việc nạp lại cache phải được tổ chức nhất quán |
| Service discovery | Một thành phần định nghĩa route từ dữ liệu service discovery khi bật và cấu hình tương ứng | Discovery client/load balancer là phụ thuộc bổ sung; không tự có chỉ vì URI viết `lb://` |
| Nguồn tự triển khai | Ứng dụng cung cấp `RouteDefinitionLocator` tùy chỉnh | Cần kiểm soát ID trùng, lỗi dữ liệu và vòng đời làm mới |

Một số phiên bản có các lớp/bean cụ thể như `PropertiesRouteDefinitionLocator`, `DiscoveryClientRouteDefinitionLocator` hoặc cơ chế gộp nhiều locator. Cách đặt tên, tính năng và điều kiện kích hoạt phải đối chiếu theo phiên bản đang dùng.

### Vì sao cần phân biệt locator với repository?

- **Locator** trả về những định nghĩa có thể đọc để chuyển thành route.
- **Repository** là giao diện/một cơ chế hỗ trợ lưu, tìm, xóa định nghĩa; một repository thường đồng thời tham gia làm nguồn cung cấp definitions.
- **Refresh** quyết định khi nào tập `Route` đang được sử dụng được dựng/nạp lại. Một thao tác `save` thành công không chứng minh tất cả instance Gateway đã đồng thời dùng route mới.

Trong cụm nhiều Gateway instance, cần nghĩ đến **phân phối thay đổi và đồng bộ cache** giữa các instance; không suy ra mọi node tự cập nhật chỉ vì một node đã nhận route mới.

## 5. `RouteDefinitionRouteLocator` chuyển cấu hình thành Route như thế nào?

`RouteDefinitionRouteLocator` là một thành phần nối giữa **định nghĩa khai báo** và **route có thể chạy**. Trong mô hình WebFlux này, quá trình khái niệm gồm các bước:

1. **Lấy `RouteDefinition`** từ nguồn qua `RouteDefinitionLocator`.
2. **Tạo predicate**: với mỗi `PredicateDefinition`, tìm `RoutePredicateFactory` có tên tương ứng; bind/thẩm định tham số; tạo predicate.
3. **Kết hợp predicate**: các predicate được khai báo trong cùng một route thường kết hợp theo **AND**. Muốn route match, mọi điều kiện bắt buộc phải thỏa.
4. **Tạo `GatewayFilter`**: với mỗi `FilterDefinition`, tìm `GatewayFilterFactory` tương ứng và áp dụng tham số đã bind. Các `default-filters` nếu được cấu hình phù hợp cũng có thể được ghép vào route.
5. **Dựng `Route`** với predicate, filters, ID, URI, thứ tự và metadata.
6. **Đưa vào tập RouteLocator** để phần xử lý request sử dụng; có thể có lớp cache/sắp xếp route trong pipeline.

~~~mermaid
flowchart LR
    RD["RouteDefinition: orders-read"] --> RP["PathDefinition + MethodDefinition"]
    RD --> FD["StripPrefix + SetRequestHeader definitions"]
    RP --> RF["RoutePredicateFactory"]
    FD --> GF["GatewayFilterFactory"]
    RF --> P["Predicate thực thi (AND)"]
    GF --> FIL["GatewayFilter objects"]
    P --> R["Route: orders-read"]
    FIL --> R
    RD --> R
~~~

Nếu tên predicate/filter không tồn tại hoặc tham số không hợp lệ, bước chuyển đổi có thể thất bại, ghi log lỗi hoặc khiến route không khả dụng tùy phiên bản và thời điểm tập route được nạp. Vì vậy, trước khi sửa các filter ở request-time, phải xác định **route đã được tạo thành công chưa**.

### Các khái niệm cùng tên rất dễ nhầm

| Thành phần | Câu hỏi nó trả lời |
|---|---|
| `RouteDefinitionLocator` | Lấy khai báo route từ đâu? |
| `RouteDefinitionRouteLocator` | Biến khai báo thành route hoạt động như thế nào? |
| `RoutePredicateFactory` | Dùng tên/đối số này tạo điều kiện match bằng cách nào? |
| `GatewayFilterFactory` | Dùng tên/đối số này tạo filter cho route bằng cách nào? |
| `RouteLocator` | Những Route nào hiện có để Gateway lựa chọn? |
| `RoutePredicateHandlerMapping` | Với request này, Route nào match? |
| `FilteringWebHandler` | Khi đã chọn Route, thực thi filter chain ra sao? |

`RouteLocator` là giao diện cung cấp `Route`; không phải mọi implementation của nó đều chuyển từ `RouteDefinition`.

## 6. Từ `RouteLocator` đến request thật

Xét request:

~~~http
GET /api/orders/42 HTTP/1.1
Host: gateway.example.test
Authorization: Bearer <token>
~~~

Giả định Gateway chạy với YAML ở phần 2 và downstream phục vụ `GET /orders/42`. Khi có request:

1. **Spring WebFlux nhận request** và tạo `ServerWebExchange`. Những `WebFilter` bên ngoài handler định tuyến, ví dụ Spring Security WebFlux nếu được cấu hình, có thể xử lý request tại đây.
2. **`RoutePredicateHandlerMapping`** truy vấn tập `Route` từ `RouteLocator` và đánh giá predicate theo thứ tự route được cung cấp. Với ví dụ này, `Path` khớp `/api/orders/42` và `Method` khớp `GET`.
3. Khi match, Gateway **gắn Route đã chọn vào exchange** để các thành phần tiếp theo biết route nào đang hoạt động.
4. **`FilteringWebHandler`** kết hợp global filters và gateway filters thuộc Route, sắp xếp theo cơ chế order của filter, rồi thực hiện chuỗi xử lý.
5. `StripPrefix=1` đổi đường dẫn từ `/api/orders/42` thành `/orders/42`; `SetRequestHeader` đặt giá trị header `X-Gateway-Route` cho request chuyển tiếp.
6. **Routing filter** thích hợp chuyển tiếp đến URI đích; trường hợp HTTP(S) thông thường thường dùng các thành phần như Netty routing ở Gateway Server WebFlux. Khi downstream trả lời, các filter xử lý response hoàn tất và Gateway gửi kết quả về client.

Mô tả này là **luồng logic**. Thứ tự chính xác của một số filter phụ thuộc vào `Ordered` của global filters, gateway filters và phiên bản; không suy luận rằng mọi filter chạy đúng thứ tự xuất hiện trong YAML nếu có global/default filter hoặc filter có order riêng.

### Nếu request không match?

- `POST /api/orders/42` không thỏa `Method=GET`.
- `GET /public/orders/42` không thỏa `Path=/api/orders/**`.
- Nếu không có route nào khác khớp và cũng không có handler khác phục vụ path, Gateway thường trả **404**.

Route **có tồn tại** nhưng predicate **không khớp** là trạng thái khác với route không được dựng lên do cấu hình sai. Cách kiểm tra và hướng sửa của hai tình huống khác nhau.

## 7. Thứ tự route khác thứ tự filter

### Thứ tự giữa các route

Thuộc tính `order` của Route giúp ưu tiên khi **nhiều route cùng match một request**. Giá trị thấp hơn thường được xem xét trước trong tập routes đã sắp xếp.

Ví dụ:

~~~yaml
spring:
  cloud:
    gateway:
      routes:
        - id: orders-get
          order: -20
          uri: http://localhost:9091
          predicates:
            - Path=/api/orders/**
            - Method=GET

        - id: orders-fallback
          order: 10
          uri: http://localhost:9092
          predicates:
            - Path=/api/orders/**
~~~

Với `GET /api/orders/42`, cả hai route có thể match nhưng `orders-get` được ưu tiên do order nhỏ hơn. Với `POST /api/orders/42`, route đầu không thỏa Method nên route thứ hai có thể được chọn.

**Không dựa vào thứ tự xuất hiện trong YAML** để giải quyết xung đột khi hai route cùng nhận một request. Hãy đặt `order` rõ ràng, thiết kế predicates đủ phân biệt và tránh phụ thuộc vào hành vi khi `order` bằng nhau.

### Thứ tự bên trong filter chain

Ở giai đoạn xử lý request, Gateway hợp nhất các **`GlobalFilter`** và **`GatewayFilter` theo route** rồi sắp xếp theo thứ tự thích hợp. Trong một filter chain có kiểu trước/sau (`pre`/`post`):

- Phần **trước** khi gọi filter tiếp theo thường đi theo thứ tự order tăng dần.
- Phần **sau** khi filter tiếp theo hoàn tất thường chạy theo chiều ngược lại.

~~~text
Filter A — pre
  Filter B — pre
    Filter C — pre
      Routing / downstream
    Filter C — post
  Filter B — post
Filter A — post
~~~

Đây là hình dung tổng quát của chain khi các filter gọi chain tiếp tục. Một filter có thể từ chối request hoặc kết thúc sớm, chẳng hạn một rule bảo mật/rate limit, nên **không phải lúc nào request cũng đến downstream**. Order giữa các route **không** quyết định vị trí chạy của từng filter.

## 8. Vai trò của GlobalFilter, default filter và filter riêng của route

Khi thiết kế Gateway nhiều microservices, cần chọn đúng phạm vi xử lý:

| Loại | Phạm vi | Ví dụ sử dụng |
|---|---|---|
| `GlobalFilter` | Tham gia vào các request đã được Gateway route qua pipeline tương ứng | Gắn correlation ID, logging, đo latency, xử lý lỗi chung |
| `default-filters` | Các filter mặc định được áp dụng cho route được tạo từ cấu hình trong phạm vi cơ chế hỗ trợ | Xóa/đặt header dùng chung, chính sách cơ bản |
| `filters` của một `RouteDefinition` | Chỉ áp dụng khi route cụ thể được chọn | RewritePath, StripPrefix, retry riêng dịch vụ, rate limit theo API |

**GlobalFilter không đồng nghĩa WebFilter.** Trong WebFlux, `WebFilter` (ví dụ thành phần bảo mật HTTP của Spring Security) nằm trong pipeline web tổng thể và có thể xử lý request ngay cả trước khi Gateway chọn route. Còn `GlobalFilter` của Gateway thường được gọi trong chuỗi xử lý **sau khi Route đã được chọn**.

Nếu cần chặn cả request **không khớp bất kỳ route nào**, phải chọn điểm can thiệp phù hợp, chẳng hạn bảo mật ở tầng WebFlux hoặc hạ tầng phía trước; không mặc định `GlobalFilter` sẽ được gọi cho mọi request HTTP trên cổng.

Một ví dụ thay đổi header ở route:

~~~yaml
filters:
  - RemoveRequestHeader=Cookie
  - SetRequestHeader=X-Edge-Service,orders
~~~

Khi route match, các filter tạo từ khai báo trên sẽ chạy theo thứ tự cuối cùng của chain. Tuy nhiên, việc xóa Cookie hay đặt header không phải chính sách bảo mật hoàn chỉnh: cần kiểm tra tương tác với xác thực, ủy quyền, token relay và các proxy phía trước.

## 9. Route Java DSL có nhất thiết đi qua `RouteDefinition` không?

**Không.** Gateway Server WebFlux hỗ trợ tạo trực tiếp các object `Route` qua Java DSL như `RouteLocatorBuilder`, ví dụ ở dòng có API tương ứng:

~~~java
import org.springframework.cloud.gateway.route.RouteLocator;
import org.springframework.cloud.gateway.route.builder.RouteLocatorBuilder;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class GatewayRoutes {

    @Bean
    RouteLocator catalogRoutes(RouteLocatorBuilder builder) {
        return builder.routes()
            .route("catalog-java", r -> r
                .path("/api/catalog/**")
                .filters(f -> f.stripPrefix(1))
                .uri("http://localhost:9092"))
            .build();
    }
}
~~~

Đường này tạo **`RouteLocator` với Route có thể thực thi** mà không cần đi qua luồng cấu hình YAML → `RouteDefinition` → `RouteDefinitionRouteLocator` cho những route vừa khai báo bằng DSL. Tuy nhiên, khi có request, các Route đó vẫn được chọn và thực thi theo pipeline định tuyến/filter tương ứng của Gateway.

So sánh ngắn:

- **RouteDefinition từ YAML/repository**: thuận tiện cho khai báo dữ liệu, thay đổi ngoài mã nguồn và quản lý route theo cấu hình.
- **Route tạo qua Java DSL**: thuận tiện khi predicates/filters được biểu diễn bằng code, cấu trúc lập trình hoặc điều kiện tùy biến.
- **Đầu ra chung**: `Route` được Gateway sử dụng để kiểm tra predicate và thực thi filter chain.

Vì vậy, nói “mọi Route đều đi qua RouteDefinitionRouteLocator” là **không đúng**. Thành phần chuyển đổi này quan trọng cho **luồng định nghĩa route dạng dữ liệu**, không bắt buộc cho tất cả cách khai báo route.

## 10. Khi cấu hình thay đổi, route đang chạy cập nhật lúc nào?

Một route có thể thay đổi khi:

- Người vận hành sửa cấu hình tĩnh và **khởi động lại** Gateway hoặc áp dụng cơ chế reload được hỗ trợ.
- Ứng dụng lưu/xóa route thông qua repository hoặc một API quản trị.
- Service discovery cung cấp thông tin mới cho các route được sinh động.
- Có sự kiện/cơ chế **refresh routes** khiến các định nghĩa được đọc và chuyển đổi lại.

Đối với các dòng Gateway Server WebFlux có `CachingRouteLocator`, tập Route có thể được **cache** để tránh dựng lại mỗi lần có request. Một thao tác sửa dữ liệu nguồn không bảo đảm cache đã đổi tức thời. Cần xác nhận cơ chế phát sự kiện refresh, thao tác cache và trạng thái cuối cùng của route trên từng Gateway instance.

~~~mermaid
sequenceDiagram
    participant O as Operator / cấu hình
    participant S as Nguồn RouteDefinition
    participant C as RouteLocator / cache
    participant G as Gateway request handler
    O->>S: Thêm/sửa/xóa RouteDefinition
    Note over S,C: Thay dữ liệu nguồn chưa chắc thay cache ngay
    O->>C: Kích hoạt cơ chế refresh phù hợp
    C->>S: Đọc lại định nghĩa
    S-->>C: Danh sách RouteDefinition
    Note over C: Dựng lại Route, predicate và filter
    G->>C: Request mới tìm Route
    C-->>G: Tập Route đã cập nhật (sau khi refresh thành công)
~~~

**Lưu ý về điều khiển thay đổi:** Nếu dùng các endpoint quản trị route hoặc Actuator Gateway, hãy giới hạn truy cập bằng bảo mật và mạng nội bộ, chỉ mở những endpoint cần thiết. Không để người dùng Internet tự ghi/sửa route hoặc tự gọi refresh. Khả năng, endpoint path và cách exposure thay đổi theo phiên bản Spring Boot/Gateway.

### Cập nhật route và cập nhật service instance là hai việc khác nhau

Một URI như `lb://order-service` biểu thị việc định tuyến qua cơ chế load balancing/service discovery phù hợp. **Route có thể không thay đổi**, nhưng tập instance của `order-service` thay đổi khi scale hoặc rolling deploy. Mặt khác, thêm một service mới để **sinh một route mới** qua discovery locator lại liên quan đến việc cập nhật tập Route.

Cần phân biệt:

- `RouteDefinition` thay đổi: ID, predicates, filters hoặc URI của route được thay.
- Danh sách service instances thay đổi: URI `lb://...` có thể giữ nguyên nhưng downstream được chọn khác ở request-time.
- Route/cache refresh: cách Gateway thấy thay đổi trong tập Route, có thể độc lập với cập nhật danh sách instance ở load balancer.

## 11. Chẩn đoán lỗi theo đúng giai đoạn

Một phương pháp hiệu quả là phân loại lỗi theo **nơi xảy ra** trước khi sửa.

| Hiện tượng | Giai đoạn cần kiểm tra | Câu hỏi chẩn đoán |
|---|---|---|
| Route không xuất hiện trong danh sách | Nguồn định nghĩa / conversion / cache | YAML có bind đúng không? Locator có trả RouteDefinition không? Factory có được tìm thấy không? Đã refresh chưa? |
| Startup hoặc refresh lỗi khi tạo routes | Conversion | Predicate/filter có tên đúng và tham số hợp lệ theo phiên bản không? URI có parse được không? |
| Route có trong danh sách nhưng request 404 | Match predicate | Path, Method, Host hoặc Header có thật sự thỏa tất cả predicates không? Có route nào ưu tiên trước không? |
| Request đến backend sai đường dẫn | GatewayFilter chain | StripPrefix/RewritePath có chạy không? Có default/global filter hoặc proxy khác sửa path không? |
| Có route, filter chạy nhưng downstream báo lỗi | Routing / downstream | URI, DNS, load balancer, TLS, kết nối và trạng thái backend có đúng không? |
| Đổi cấu hình nhưng kết quả không đổi | Reload / refresh | Dữ liệu đã cập nhật ở nguồn nào? Cache route từng node đã nạp lại chưa? |
| Xác thực hoặc rate limit có hành vi bất ngờ | WebFilter / GatewayFilter | Rule nằm ở tầng nào? Có route match trước khi filter chạy không? Order và phạm vi áp dụng ra sao? |
| Metrics thiếu route ID hoặc request không có trace | Observability | Request đã chọn Route chưa? Tích hợp metric/tracing có bật đúng version không? |

### Công cụ quan sát phù hợp

Trong một số dòng Gateway, **Spring Boot Actuator + Gateway actuator endpoint** có thể cung cấp thông tin các route đã biết và việc refresh. URL thường được nhắc đến trong tài liệu là `/actuator/gateway/routes` hoặc `/actuator/gateway/refresh`, **nhưng không mặc định endpoint này luôn được bật, có cùng contract hoặc truy cập được ở mọi version**. Kiểm tra reference và chính sách bảo mật tương ứng.

Các nguồn kiểm tra nên kết hợp:

1. **Dependency và version**: bảo đảm artifact, WebFlux/MVC và namespace cấu hình đúng nhau.
2. **Startup log/refresh log**: tìm lỗi khi binding dữ liệu hoặc tạo predicate/filter.
3. **Danh sách Route được tạo**: kiểm tra ID, URI, thứ tự, predicates và filters đang có.
4. **Log của request và downstream**: đối chiếu URI/path/header thực tế, mã phản hồi và thời gian.
5. **Metrics/tracing**: kiểm tra route ID, latency, error rate nếu tính năng quan sát đã bật.

Đối với hệ thống có nhiều instance Gateway, ghi thêm **instance ID** khi so sánh cấu hình hoặc đường đi request; nếu không, cùng một URL có thể trả kết quả khác nhau qua load balancer vì cache ở các instance chưa đồng bộ.

## 12. Thực hành: chứng minh đường đi từ YAML đến Route

Giả sử có một backend đơn giản tại `http://localhost:9090` trả HTTP 200 khi nhận `GET /orders/42`. Cấu hình Gateway Server WebFlux theo ví dụ phần 2; giả định server Gateway ở `localhost:8080`.

### Bước 1 — Xác nhận route đã được nạp

Khởi động Gateway, kiểm tra log hoặc endpoint quản trị được cho phép để xác nhận route ID `orders-read` đã tồn tại, có URI `http://localhost:9090`, predicate `Path` và `Method`, cùng các filter tương ứng.

**Nếu không thấy route**, dừng tại bước chuyển đổi cấu hình để kiểm tra YAML, version và factory, thay vì thử sửa backend.

### Bước 2 — Gửi request khớp

~~~bash
curl -i http://localhost:8080/api/orders/42
~~~

Kỳ vọng: Gateway match `GET` và `/api/orders/42`, áp dụng `StripPrefix=1`, rồi backend nhận `GET /orders/42` cùng header `X-Gateway-Route: orders-read`. Điều kiện là không có filter khác ghi đè path/header hoặc thay đổi route đích.

### Bước 3 — Gửi request không khớp

~~~bash
curl -i -X POST http://localhost:8080/api/orders/42
curl -i http://localhost:8080/other/orders/42
~~~

Hai request không thỏa toàn bộ predicates của `orders-read`. Nếu ứng dụng không có route/handler khác nhận chúng, kết quả thường là **404**. Điều này không chứng minh `RouteDefinition` bị lỗi; nó chứng minh **route predicate không chọn route đó**.

### Bước 4 — Tạo tình huống downstream lỗi

Tắt backend cổng 9090 rồi gửi lại request GET hợp lệ. Lúc này **route vẫn có thể match** và GatewayFilter vẫn thực hiện, nhưng bước routing tới downstream thất bại, thường dẫn tới lỗi 5xx. Mã cụ thể tùy filter và cấu hình xử lý lỗi/retry/circuit breaker. Phân biệt rõ lỗi kết nối downstream với lỗi route không tồn tại.

### Bước 5 — Thay đổi và làm mới route có kiểm chứng

Nếu môi trường hỗ trợ thay đổi cấu hình động, tạo thay đổi hợp lệ (chẳng hạn sửa `Path`) tại **nguồn cấu hình thực tế**, kích hoạt quy trình refresh được hỗ trợ, rồi kiểm tra danh sách Route và hai request trước/sau. Nếu dùng file cấu hình tĩnh không có cơ chế reload, hãy **khởi động lại** ứng dụng trong môi trường thử nghiệm và kiểm tra lại.

Ghi kết quả dưới dạng bảng:

| Trường hợp | Dấu hiệu cần quan sát | Giai đoạn chứng minh |
|---|---|---|
| Route `orders-read` hiện diện | ID, URI, predicates và filters đã tạo | Conversion và RouteLocator |
| GET hợp lệ | Request đến đúng backend, path/header đã biến đổi | Match + filter + routing |
| POST sai Method | Route này không được chọn | Predicate |
| Backend không chạy | Route vẫn khớp nhưng kết nối downstream lỗi | Routing |
| Route được refresh | Tập Route mới hiển thị và hoạt động | Cache/refresh |

## 13. Liên hệ với bảo mật và khả năng vận hành

Hiểu đường đi `RouteDefinition` → `Route` giúp triển khai các năng lực Gateway có kiểm soát:

- **Xác thực và phân quyền**: quyết định chính sách cần chạy trước route matching (ví dụ WebFlux security) hay trong một route đã chọn; tránh để endpoint không match route vô tình nằm ngoài phạm vi kiểm tra cần thiết.
- **Giới hạn lưu lượng**: lựa chọn key resolver, phạm vi route và filter order; bảo đảm traffic vượt ngưỡng được xử lý trước khi gọi backend theo chính sách.
- **Circuit breaker và retry**: xác định filter nào bao quanh bước chuyển tiếp, tránh retry các operation không idempotent hoặc tạo số lần gọi vượt dự tính.
- **TLS**: kiểm tra TLS từ client đến Gateway và TLS từ Gateway đến downstream là hai đường kết nối có cấu hình riêng; chúng không được quyết định chỉ bởi việc Route được dựng thành công.
- **Khám phá dịch vụ**: phân biệt route discovery với chọn instance qua `lb://`; kiểm tra cả định nghĩa route và quá trình resolve instance.
- **Quan sát request**: gắn route ID và thông tin trace phù hợp khi route đã được chọn; vẫn thu thập được sự kiện cho request bị chặn trước routing bằng thành phần đúng tầng.

Không nên đánh đồng “có Route” với “hệ thống đã an toàn”. Predicate và filter của route chỉ là một phần của bảo mật tổng thể, cần kiểm tra thêm policy ở web server, Spring Security, downstream và hạ tầng mạng.

## 14. Các ngộ nhận thường gặp

| Ngộ nhận | Giải thích đúng |
|---|---|
| `RouteDefinition` và `Route` là cùng một object | Một bên là khai báo dữ liệu, bên kia mang predicate/filter đã được tạo để thực thi |
| Mỗi HTTP request đều đọc YAML rồi tạo lại Route | Gateway có `RouteLocator` và thường có cache; refresh là quy trình riêng |
| Mọi Route đều bắt buộc có RouteDefinition | Route từ Java DSL có thể được tạo trực tiếp |
| Một route có nhiều predicates là chỉ cần một điều kiện đúng | Trong khai báo phổ biến, các predicate của cùng route được kết hợp **AND** |
| Route theo thứ tự YAML nên filter cũng chạy theo thứ tự YAML | `order` chọn route khác với filter order; filter chain còn có global/default filters |
| `GlobalFilter` chạy cho mọi HTTP request dù không match route | Gateway GlobalFilter thường tham gia sau khi Route được chọn; WebFilter nằm ở tầng khác |
| Sửa repository thành công là mọi node đã dùng Route mới | Cần xét refresh/cache và đồng bộ các instance |
| `lb://service` nghĩa là RouteDefinition được viết lại khi scale instance | Route có thể giữ nguyên; load balancer có thể chọn service instance khi xử lý request |
| Gateway trả 404 chắc chắn do YAML sai | 404 còn có thể do predicate không match, route khác hoặc handler khác |
| Đã thấy route trong Actuator là đủ để chứng minh backend hoạt động | Cần request thật để kiểm chứng predicate, filter và kết nối downstream |

## 15. Checklist tự kiểm tra kiến trúc

- [ ] Tôi phân biệt được **`RouteDefinition` (dữ liệu)** và **`Route` (có thể thực thi)**.
- [ ] Tôi biết `RouteDefinitionLocator`, `RouteDefinitionRouteLocator` và `RouteLocator` làm việc ở đâu.
- [ ] Tôi biết `RoutePredicateFactory` và `GatewayFilterFactory` được dùng để tạo thành phần runtime.
- [ ] Tôi hiểu **AND** giữa các predicates trong một route và thứ tự ưu tiên giữa các routes.
- [ ] Tôi tách được **route order** khỏi **filter order**, **GlobalFilter** khỏi **WebFilter**.
- [ ] Tôi có thể giải thích hành vi của `Path`, `Method`, `StripPrefix`, `SetRequestHeader` trong một request thực tế.
- [ ] Tôi biết route tạo từ Java DSL có thể bỏ qua bước `RouteDefinition`.
- [ ] Tôi biết một thay đổi cấu hình cần quy trình cập nhật tập Route và cache phù hợp.
- [ ] Tôi có thể phân biệt lỗi **không nạp route**, **predicate không match** và **downstream không hoạt động**.
- [ ] Tôi đã kiểm tra phiên bản Gateway, biến thể WebFlux/MVC và bảo mật trước khi bật endpoint quản trị route.

## Tài liệu tham khảo chính thức

- [Spring Cloud Gateway Reference](https://docs.spring.io/spring-cloud-gateway/reference/) — tài liệu route, predicates, filters, GlobalFilter, routing và cơ chế quản lý routes; chọn đúng phiên bản.
- [Spring Cloud Gateway Project](https://spring.io/projects/spring-cloud-gateway) — thông tin dự án, các dòng phát hành và liên kết tài liệu.
- [Spring Framework WebFlux Reference](https://docs.spring.io/spring-framework/reference/web/webflux.html) — `DispatcherHandler`, handler mapping, `WebFilter` và `ServerWebExchange`.
- [Spring Boot Actuator Reference](https://docs.spring.io/spring-boot/reference/actuator/) — nguyên tắc cấu hình, bảo mật và exposure của management endpoints.

**Điểm cần nhớ:** `RouteDefinition` trả lời **“cấu hình nói phải định tuyến thế nào?”**; `Route` trả lời **“Gateway đang có quy tắc thực thi nào?”**; còn `RoutePredicateHandlerMapping` và `FilteringWebHandler` quyết định **“request cụ thể này đi qua quy tắc và chuỗi filter nào?”**. Tách ba câu hỏi này sẽ giúp bạn phát triển và vận hành API Gateway an toàn, dễ kiểm chứng khi mở rộng microservices.
