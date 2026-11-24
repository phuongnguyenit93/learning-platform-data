# Gateway dùng chung, gateway theo miền và Backend for Frontend

## 1. Vì sao cần phân biệt ba kiểu gateway?

Trong hệ thống microservices, một ứng dụng có thể có nhiều điểm tiêu thụ API: website, ứng dụng di động, hệ thống quản trị và đối tác. Các client cần một địa chỉ truy cập ổn định, trong khi các service phía sau được triển khai, mở rộng và thay đổi độc lập. **Spring Cloud Gateway** cung cấp khả năng định tuyến request dựa trên **route predicate**, xử lý qua **filter chain**, sửa đường dẫn/header, kết nối với service discovery và tích hợp các cơ chế như xác thực, rate limiting, circuit breaker, retry, TLS và quan sát request.

Tuy nhiên, dùng Spring Cloud Gateway không đồng nghĩa mọi hệ thống phải có một gateway duy nhất. Có ba cách phân chia trách nhiệm thường gặp:

- **Gateway dùng chung (shared/edge gateway):** một điểm vào chung cho nhiều API và nhiều nhóm client.
- **Gateway theo miền (domain gateway):** một cổng vào phụ trách API của một miền nghiệp vụ, chẳng hạn catalog, ordering hoặc payment.
- **Backend for Frontend (BFF):** một backend được thiết kế riêng cho nhu cầu của một loại giao diện/client, chẳng hạn web hoặc mobile.

Ba cách này mô tả **phạm vi trách nhiệm**, không nhất thiết mô tả ba công nghệ hay ba lớp triển khai luôn phải tồn tại. Một hệ thống có thể chỉ dùng shared gateway; hệ thống lớn hơn có thể kết hợp shared gateway, domain gateway và BFF.

### Kết quả cần nắm

Sau bài học, bạn cần có khả năng:

1. Giải thích trách nhiệm và ranh giới sở hữu của shared gateway, domain gateway và BFF.
2. Phân biệt thao tác định tuyến/filter với việc tổng hợp dữ liệu phục vụ giao diện.
3. Phác họa luồng request và cấu hình route cơ bản bằng Spring Cloud Gateway.
4. Chọn mô hình phù hợp dựa trên số client, số miền nghiệp vụ, quyền sở hữu API, bảo mật và chi phí vận hành.
5. Nhận diện các rủi ro như điểm nghẽn chung, logic nghiệp vụ đặt sai lớp, nhân đôi chính sách và tăng số chặng mạng.

## 2. Gateway dùng chung: một điểm vào tại biên hệ thống

**Shared gateway** thường là điểm vào đầu tiên của các API công khai hoặc API nội bộ dành cho client. Nó nhận request, kiểm tra route predicate để chọn route và chạy chuỗi filter tương ứng trước khi chuyển request đến backend.

~~~mermaid
flowchart LR
    W[Web client] --> E[Shared / Edge Gateway]
    M[Mobile client] --> E
    P[Partner client] --> E
    E -->|/api/catalog/**| C[Catalog service]
    E -->|/api/orders/**| O[Order service]
    E -->|/api/accounts/**| A[Account service]
~~~

Những việc hợp lý để thực hiện ở lớp này gồm:

- **Định tuyến:** chọn backend theo path, host, method, header hoặc điều kiện khác.
- **Bảo vệ biên:** kết thúc TLS (khi phù hợp với hạ tầng), xác thực ở lớp biên, kiểm tra một số chính sách truy cập và áp dụng giới hạn lưu lượng.
- **Thao tác giao thức:** chuẩn hóa đường dẫn, thêm/bỏ header tin cậy, xử lý CORS, gắn correlation ID, kiểm soát timeout.
- **Điều phối độ tin cậy tại biên:** retry có kiểm soát, circuit breaker và fallback khi có lý do rõ ràng.
- **Quan sát:** ghi nhận số request, thời gian xử lý, mã trạng thái, route ID và thông tin tracing.

Lợi thế lớn nhất là client có một địa chỉ truy cập thống nhất, còn các chính sách xuyên suốt có một nơi triển khai rõ ràng. Dù vậy, shared gateway cũng có thể thành **điểm lỗi có phạm vi ảnh hưởng lớn** nếu tất cả request phải đi qua nó. Điều này đòi hỏi nhiều instance, load balancing, cấu hình phù hợp và khả năng triển khai/rollback độc lập.

Shared gateway nên giữ logic đơn giản và ít phụ thuộc nghiệp vụ. Chẳng hạn, việc đổi đường dẫn từ **/api/catalog/products/42** thành **/products/42** là trách nhiệm hợp lý của gateway; tính tổng tiền đơn hàng hay xác định quyền hoàn tiền thuộc các thành phần nghiệp vụ phía sau.

## 3. Gateway theo miền: một cổng vào cho một nhóm năng lực nghiệp vụ

Khi hệ thống có nhiều miền nghiệp vụ và các nhóm phát triển sở hữu API độc lập, một gateway chung có thể chứa ngày càng nhiều route và quy tắc riêng. **Domain gateway** gom các API của một miền, cung cấp hợp đồng truy cập ổn định và phân phối request tới các service thuộc miền đó.

Ví dụ một miền **Catalog** có nhiều service: sản phẩm, tồn kho và giá. Gateway theo miền Catalog có thể quản lý các route của miền thay vì buộc shared gateway hiểu tất cả service con:

~~~mermaid
flowchart LR
    Client[Client] --> Edge[Shared Gateway]
    Edge -->|/api/catalog/**| CG[Catalog Domain Gateway]
    Edge -->|/api/orders/**| OG[Ordering Domain Gateway]
    CG --> PS[Product service]
    CG --> IS[Inventory service]
    CG --> PR[Pricing service]
    OG --> OS[Order service]
    OG --> FS[Fulfillment service]
~~~

Một domain gateway thường chịu trách nhiệm:

- Đưa ra **API contract của miền**: các đường dẫn, phiên bản API, quy tắc chuyển tiếp và chính sách phù hợp cho nhóm API đó.
- Điều phối route đến các service trong cùng miền mà không lộ chi tiết bố trí service cho client.
- Thực hiện các chính sách mức miền, ví dụ giới hạn truy cập cho một nhóm API có chi phí cao.
- Giúp nhóm sở hữu miền triển khai và thay đổi cấu hình độc lập trong giới hạn hợp đồng với gateway biên.

Điểm phân biệt quan trọng: **domain gateway không tự động đồng nghĩa với một lớp nghiệp vụ mới**. Nó có thể chỉ làm routing/filter. Nếu miền cần một API tổng hợp hoặc nghiệp vụ phức tạp, hãy cân nhắc một application service/facade rõ trách nhiệm, thay vì nhồi logic vào một filter của gateway.

Domain gateway mang lại quyền tự chủ, nhưng đổi lại có thêm hop mạng, thêm dịch vụ cần quan sát, cập nhật, bảo mật và vận hành. Trong một hệ thống nhỏ chỉ có vài backend và một nhóm quản lý, tách domain gateway có thể chưa đem lại lợi ích tương xứng.

## 4. Backend for Frontend: backend chuyên biệt cho từng trải nghiệm

**Backend for Frontend (BFF)** tổ chức API theo nhu cầu của **client**, không theo ranh giới của một miền nghiệp vụ. Chẳng hạn, màn hình trang chủ mobile chỉ cần ảnh thu nhỏ, giá hiện tại, tình trạng tồn kho ngắn gọn và tối đa năm sản phẩm gợi ý; website desktop lại cần nhiều bộ lọc, bảng so sánh và dữ liệu phong phú hơn.

Thay vì bắt client gọi nhiều service và tự ghép kết quả, **mobile BFF** có thể trả về một payload đúng cấu trúc màn hình:

~~~mermaid
flowchart LR
    Mobile[Mobile app] --> MG[Mobile BFF]
    Web[Web app] --> WG[Web BFF]
    MG --> C[Catalog service]
    MG --> I[Inventory service]
    MG --> R[Recommendation service]
    WG --> C
    WG --> I
    WG --> S[Search service]
~~~

BFF thường phụ trách:

- **API composition:** gọi nhiều backend và tổng hợp dữ liệu thành response phù hợp một màn hình hoặc luồng giao diện.
- **Chuyển đổi representation:** đổi tên trường, rút gọn thông tin, phân trang hoặc định dạng theo nhu cầu web/mobile.
- **Giảm số lần gọi từ client:** tổ chức nhiều lệnh gọi backend từ phía server, cân nhắc song song hóa và timeout.
- **Thích ứng nhịp thay đổi UI:** cập nhật response contract cho từng client mà không ép mọi client thay đổi đồng thời.

BFF **không nên sở hữu quy tắc nghiệp vụ cốt lõi** như tính thuế, chính sách hoàn tiền hay quyết định trạng thái đơn hàng. Những quy tắc này phải nằm tại service nghiệp vụ phù hợp để web, mobile và đối tác nhận kết quả nhất quán.

BFF có thể được xây bằng Spring Boot WebFlux, Spring MVC hoặc công nghệ backend khác. **Spring Cloud Gateway phù hợp cho việc định tuyến tới BFF và xử lý filter**, nhưng các bước ghép dữ liệu phức tạp thường dễ kiểm thử, bảo trì và quan sát hơn khi triển khai trong controller/service của ứng dụng BFF. Vì vậy, **BFF là một mẫu kiến trúc**, không phải tên của một filter có sẵn trong Spring Cloud Gateway.

## 5. So sánh nhanh theo mục tiêu thiết kế

| Tiêu chí | Shared gateway | Domain gateway | BFF |
| --- | --- | --- | --- |
| Phục vụ ai? | Nhiều client và nhiều miền | Người dùng API của một miền | Một loại client hoặc một trải nghiệm |
| Trục phân chia | Biên hệ thống | Miền nghiệp vụ / bounded context | Giao diện, thiết bị hoặc nhóm client |
| Trách nhiệm chính | Điểm vào, route, chính sách xuyên suốt | API contract và định tuyến trong miền | Tổng hợp, chọn lọc, biến đổi dữ liệu cho UI |
| Đội sở hữu điển hình | Platform / infrastructure | Nhóm phát triển miền | Nhóm sản phẩm / frontend và backend liên quan |
| Thay đổi thường gặp | Chính sách biên, route public | Cấu trúc API nội bộ miền | Yêu cầu màn hình, payload, trải nghiệm |
| Lợi ích nổi bật | Truy cập nhất quán, quản lý tập trung | Tự chủ theo miền, giảm cấu hình tập trung | Giảm round trip, đơn giản hóa client |
| Rủi ro nổi bật | Điểm nghẽn/ảnh hưởng diện rộng | Tăng hop và trùng chính sách | Tăng số backend, dễ sao chép nghiệp vụ |

**Cùng là một request nhưng phân loại theo lý do thay đổi:** Nếu có một tuyến mới để chuyển request tới Order service, đó là routing. Nếu Catalog cần một hợp đồng API ổn định cho nhiều nhóm client, cân nhắc domain gateway. Nếu mobile cần một response chỉ gồm các trường hiển thị trên màn hình, đó là nhu cầu BFF.

## 6. Kết hợp cả ba trong hệ thống bán hàng

Giả sử nền tảng bán hàng có **web**, **mobile**, **API đối tác** và các miền Catalog, Ordering. Một lựa chọn có thể là:

~~~mermaid
flowchart TB
    WEB[Web app] --> EDGE[Shared Gateway]
    MOB[Mobile app] --> EDGE
    PARTNER[Partner] --> EDGE

    EDGE -->|/web/**| WBFF[Web BFF]
    EDGE -->|/mobile/**| MBFF[Mobile BFF]
    EDGE -->|/api/catalog/**| CAT[Catalog Domain Gateway]
    EDGE -->|/api/orders/**| ORD[Ordering Domain Gateway]

    WBFF --> CATALOG[Catalog API]
    WBFF --> ORDER[Order API]
    MBFF --> CATALOG
    MBFF --> ORDER

    CAT --> CATALOG
    CAT --> INVENTORY[Inventory API]
    ORD --> ORDER
    ORD --> FULFILLMENT[Fulfillment API]
~~~

Ở thiết kế này:

1. Client gửi request qua shared gateway để được kiểm tra chính sách chung và chọn điểm đến.
2. Request khớp **Path=/api/catalog/\*\*** chuyển đến Catalog domain gateway, nơi quyết định service nào xử lý API thuộc Catalog.
3. Request khớp **Path=/mobile/\*\*** chuyển đến mobile BFF; BFF lấy dữ liệu từ các API phía sau và trả response phù hợp mobile.
4. Request khớp **Path=/web/\*\*** chuyển đến web BFF nếu web cần payload hoặc luồng tổng hợp khác mobile.
5. Backend nghiệp vụ tiếp tục chịu trách nhiệm xác thực quyền trên tài nguyên, tính toán và kiểm tra bất biến nghiệp vụ.

Đường gọi từ BFF tới backend có thể trực tiếp qua service discovery hoặc qua domain API/domain gateway tùy hợp đồng và chính sách kết nối. Cần **xác định một đường gọi nội bộ nhất quán**, tránh vô tình cho BFF vòng trở lại shared gateway rồi quay về chính nó. Tránh mặc định đẩy mọi hop vào nhau nếu không cần thiết.

### Minh họa một request

Mobile gửi **GET /mobile/home** tới shared gateway. Gateway bỏ prefix **/mobile** và chuyển **GET /home** tới mobile BFF. BFF có thể gọi Catalog và Recommendation song song, chuẩn hóa dữ liệu, sau đó trả một response như:

~~~json
{
  "featuredProducts": [
    {
      "id": "P-42",
      "name": "Bình nước",
      "thumbnail": "/images/P-42-small.webp",
      "displayPrice": "199.000 ₫",
      "available": true
    }
  ],
  "recommendations": [
    { "id": "P-81", "name": "Túi thể thao" }
  ]
}
~~~

Trong ví dụ này, BFF quyết định **cách trình bày dữ liệu** cho mobile; Catalog/Pricing/Inventory vẫn quyết định dữ liệu sản phẩm, giá và tồn kho có hợp lệ hay không.

## 7. Cấu hình route minh họa bằng Spring Cloud Gateway

Một shared gateway dùng Spring Cloud Gateway Server WebFlux có thể định tuyến dựa trên **Path predicate** và **StripPrefix filter**:

~~~yaml
spring:
  cloud:
    gateway:
      routes:
        - id: catalog-domain
          uri: lb://catalog-gateway
          predicates:
            - Path=/api/catalog/**
          filters:
            - StripPrefix=2

        - id: ordering-domain
          uri: lb://ordering-gateway
          predicates:
            - Path=/api/orders/**
          filters:
            - StripPrefix=2

        - id: mobile-bff
          uri: lb://mobile-bff
          predicates:
            - Path=/mobile/**
          filters:
            - StripPrefix=1

        - id: web-bff
          uri: lb://web-bff
          predicates:
            - Path=/web/**
          filters:
            - StripPrefix=1
~~~

Ý nghĩa của ví dụ:

| Request ban đầu | Route được chọn | Path chuyển đến đích |
| --- | --- | --- |
| GET /api/catalog/products/42 | catalog-domain | /products/42 |
| GET /api/orders/123 | ordering-domain | /123 |
| GET /mobile/home | mobile-bff | /home |
| GET /web/dashboard | web-bff | /dashboard |

**Lưu ý về hợp đồng đường dẫn:** Nếu Ordering API nội bộ mong đợi **/orders/123**, chỉ bỏ một phần prefix hoặc dùng rewrite phù hợp; cấu hình ví dụ chủ ý bỏ cả **/api/orders** để minh họa hoạt động của **StripPrefix=2**. Path nội bộ phải khớp với controller/backend thực tế. Tương tự, không áp dụng StripPrefix một cách máy móc cho mọi route.

Trong ví dụ, tiền tố URI **lb://** yêu cầu cơ chế phân giải tên service và cân bằng tải phù hợp, chẳng hạn Spring Cloud LoadBalancer kết hợp discovery client được cấu hình. Nếu chưa sử dụng service discovery, có thể định tuyến tới địa chỉ HTTP cố định cho môi trường thử nghiệm:

~~~yaml
uri: http://localhost:8081
~~~

**Khác biệt phiên bản:** Namespace cấu hình Gateway Server WebFlux có thể thay đổi theo phiên bản Spring Cloud Gateway; một số dòng mới dùng cấu trúc **spring.cloud.gateway.server.webflux.routes** thay cho **spring.cloud.gateway.routes**. Khi triển khai, đối chiếu tài liệu của đúng phiên bản Spring Cloud và phân biệt **Server WebFlux** với **Server Web MVC**; ví dụ trên minh họa cú pháp phổ biến của Gateway WebFlux.

Domain gateway Catalog có thể tiếp tục định tuyến từ hợp đồng miền đến service cụ thể:

~~~yaml
spring:
  cloud:
    gateway:
      routes:
        - id: catalog-products
          uri: lb://product-service
          predicates:
            - Path=/products/**

        - id: catalog-stock
          uri: lb://inventory-service
          predicates:
            - Path=/stock/**
~~~

Điều này phân tách trách nhiệm: shared gateway biết **đi tới miền nào**; Catalog domain gateway biết **service nào trong miền**. Nếu chưa cần lớp trung gian, route ở shared gateway hoàn toàn có thể trỏ thẳng tới Product service.

### Khi nào cần logic BFF thay vì thêm filter?

Ví dụ, mobile cần đồng thời sản phẩm nổi bật và gợi ý. Ứng dụng BFF sử dụng reactive client có thể thể hiện ý tưởng tổng hợp theo dạng pseudocode Java:

~~~java
// Minh họa bên trong service của Mobile BFF;
// productClient và recommendationClient là các adapter gọi backend.
Mono<MobileHomeResponse> loadHome() {
    Mono<List<ProductCard>> products = productClient.featured(5);
    Mono<List<RecommendationCard>> suggestions =
            recommendationClient.forHome();

    return Mono.zip(products, suggestions)
            .map(data -> new MobileHomeResponse(
                    data.getT1(),
                    data.getT2()
            ));
}
~~~

Đây là **đoạn mã minh họa**, không phải một class hoàn chỉnh để chạy trực tiếp. Trong ứng dụng thật cần bổ sung hợp đồng DTO, truyền thông tin danh tính đúng cách, timeout, giới hạn đồng thời, xử lý lỗi và kiểm thử. **Mono.zip** đợi cả hai kết quả; nếu một nguồn lỗi, toàn bộ phép ghép mặc định lỗi theo. Nếu UI chấp nhận thiếu phần gợi ý, fallback phải được thiết kế **có chủ đích** cho riêng phần đó.

## 8. Phân định xác thực, phân quyền và bảo mật

Chia nhiều gateway không làm thay đổi nguyên tắc quan trọng: mỗi request phải đi qua các kiểm soát thích hợp, và service xử lý tài nguyên vẫn phải bảo vệ tài nguyên đó.

| Lớp | Trách nhiệm bảo mật thường phù hợp |
| --- | --- |
| Shared gateway | TLS tại biên theo thiết kế triển khai, xác thực token, kiểm soát lưu lượng chung, CORS, loại bỏ header giả mạo từ bên ngoài |
| Domain gateway | Quy tắc truy cập theo nhóm API/miền, giới hạn riêng cho API nhạy cảm hoặc tốn tài nguyên |
| BFF | Quản lý phiên hoặc token phù hợp với kiểu client, giới hạn dữ liệu phản hồi, chống lộ thông tin không cần cho UI |
| Service nghiệp vụ | Kiểm tra quyền trên từng đối tượng/tài nguyên, ràng buộc nghiệp vụ, kiểm soát truy cập dữ liệu |

Một số quy tắc thực hành:

- **Xác thực ở gateway không thay thế phân quyền tại service.** Có token hợp lệ không đồng nghĩa người dùng được xem đơn hàng của người khác.
- **Không tin header danh tính do client tự gửi** như **X-User-Id**. Nếu kiến trúc dùng header nội bộ, lớp biên cần bỏ giá trị bên ngoài và chỉ thiết lập thông tin đã xác minh; kết nối nội bộ phải có ranh giới tin cậy rõ ràng.
- **Token/session cần chính sách nhất quán.** BFF có thể làm thành phần giữ phiên cho browser và thay mặt client gọi backend, nhưng phải bảo vệ cookie/token, chống CSRF khi dùng cơ chế xác thực dựa trên cookie và chỉ cấp quyền cần thiết.
- **TLS và định danh nội bộ** phải phù hợp với hạ tầng. Kết thúc TLS tại proxy ngoài không có nghĩa kết nối phía sau mặc nhiên an toàn.
- **Không log access token, cookie, mật khẩu hay dữ liệu nhạy cảm** vào access log hoặc trace.

Nếu cùng một quy tắc được cấu hình ở nhiều gateway, cần chỉ rõ lớp nào là nguồn chính sách và lớp nào thực hiện bảo vệ bổ sung. Ví dụ, có thể giới hạn tổng request ở edge và giới hạn riêng endpoint tìm kiếm tốn kém tại domain gateway; hai giới hạn có mục đích khác nhau.

## 9. Độ tin cậy, hiệu năng và khả năng quan sát

Mỗi gateway bổ sung một lần xử lý, một chặng mạng và thêm một nơi có thể xảy ra timeout. Tách nhiều tầng vì vậy cần dựa trên lợi ích quản trị và hợp đồng API, đồng thời đo được tác động thực tế.

**Timeout và retry:** Phân bổ ngân sách timeout cho toàn request; nếu shared gateway, domain gateway và BFF đều tự retry nhiều lần, số yêu cầu đổ về backend có thể tăng mạnh khi sự cố xảy ra. Chỉ retry lỗi có khả năng hồi phục và thao tác an toàn/idempotent hoặc có cơ chế chống xử lý trùng như idempotency key. Với thao tác tạo thanh toán/đơn hàng, không tự bật retry POST một cách tùy tiện.

**Circuit breaker và fallback:** Circuit breaker giúp giới hạn tác động của backend lỗi. Fallback phải giữ đúng ngữ nghĩa: trang chủ có thể bỏ phần gợi ý khi Recommendation không sẵn sàng, nhưng không được trả giá hay số dư giả để che lỗi dịch vụ quan trọng. Quyết định fallback thường cần hiểu ngữ cảnh nghiệp vụ nên có thể thích hợp ở BFF/application service hơn là một fallback chung cho mọi route.

**Rate limiting:** Edge thường bảo vệ tài nguyên toàn hệ thống; domain gateway có thể đặt quota riêng cho một nhóm API. Khi có nhiều instance, cần cơ chế chia sẻ trạng thái nếu muốn kiểm soát quota toàn cụm. Cân nhắc khóa rate limit theo người dùng, client hoặc định danh được xác thực, tránh phụ thuộc hoàn toàn vào IP trong môi trường NAT.

**Quan sát xuyên suốt:** Tracing nên liên kết request qua edge, domain gateway, BFF và backend bằng trace context. Các chỉ số cần quan sát gồm:

- Số lượng request, tỷ lệ lỗi **4xx/5xx** và độ trễ **p50/p95/p99** theo route.
- Số request bị từ chối bởi rate limiter, timeout, circuit breaker, retry và fallback.
- Lưu lượng vào/ra, mức sử dụng connection pool, tài nguyên CPU/bộ nhớ theo từng gateway.
- Độ trễ và tỷ lệ lỗi của từng lời gọi backend trong BFF, kể cả khi response tổng hợp vẫn trả mã **200**.

Tránh đưa user ID, token hoặc path chứa định danh tùy ý thành nhãn metric có độ phân mảnh cao; dùng tên route ổn định và thông tin truy vết phù hợp.

## 10. Chọn kiến trúc theo nhu cầu thực tế

Có thể bắt đầu từ một shared gateway nếu nhóm phát triển còn nhỏ, các backend ít và API chưa cần nhiều hợp đồng độc lập. Chỉ thêm tầng mới khi đã xác định rõ **ai sở hữu nó**, **vấn đề nó giải quyết** và **cách đo lợi ích**.

| Dấu hiệu trong hệ thống | Hướng cân nhắc |
| --- | --- |
| Một số service, ít nhóm phát triển, chủ yếu cần routing/TLS/auth | Shared gateway với route rõ ràng |
| Nhiều miền có API contract và vòng phát hành độc lập | Shared gateway kết hợp domain gateway ở những miền cần tự chủ |
| Web và mobile cần payload/lịch phát hành khác nhau, client gọi quá nhiều API | BFF cho trải nghiệm có nhu cầu khác biệt |
| Web/mobile gần như dùng chung cùng API và dữ liệu | Chưa cần tách BFF chỉ vì có hai loại client |
| Chính sách nghiệp vụ phức tạp phải nhất quán cho mọi client | Đưa về domain/application service; gateway chủ yếu xử lý chính sách giao thức |
| Nhiều hop nhưng chưa thấy lợi ích rõ rệt | Đo latency, độ phức tạp vận hành và xem xét gộp bớt tầng |

Một chuỗi quyết định thực dụng:

1. **Cần một điểm vào ổn định và chính sách biên?** Dùng shared gateway.
2. **Một miền có nhiều service và đội sở hữu cần thay đổi API độc lập?** Xem xét domain gateway cho miền đó.
3. **Một loại giao diện cần dữ liệu tổng hợp/biến đổi riêng?** Xem xét BFF cho trải nghiệm đó.
4. **Logic vừa được thêm có phải quy tắc nghiệp vụ cốt lõi?** Chuyển về service miền và kiểm tra lại ranh giới sở hữu.
5. **Lợi ích có lớn hơn chi phí của một lớp triển khai mới?** Đánh giá bằng tốc độ phát hành, độ trễ, lượng request, lỗi và công vận hành.

### Những phản mẫu cần tránh

**God gateway:** Một gateway duy nhất chứa mọi quy tắc nghiệp vụ, kết hợp dữ liệu, phân quyền tài nguyên và xử lý lỗi cho mọi miền; nó tạo nút phụ thuộc cho tất cả nhóm phát triển.

**Gateway theo miền chỉ để tạo thêm hop:** Thêm một service trung gian nhưng không có hợp đồng, chính sách hoặc quyền sở hữu độc lập rõ ràng.

**BFF nhân bản nghiệp vụ:** Web BFF và mobile BFF tự tính giá/thuế/khuyến mại khác nhau, dẫn đến kết quả không nhất quán.

**Chuỗi gateway tự gọi vòng:** BFF gọi shared gateway bằng đường public route trỏ ngược BFF, dẫn tới vòng lặp hoặc tăng số hop không kiểm soát.

**Retry khuếch đại tải:** Nhiều tầng đều retry, làm backend đang quá tải nhận nhiều request hơn; thiếu timeout tổng và giám sát retry.

## 11. Bài thực hành thiết kế và kiểm chứng

**Bối cảnh:** Bạn có Product service, Inventory service, Order service, website và mobile app. Mobile cần một endpoint trả sản phẩm nổi bật cùng trạng thái còn hàng; đối tác cần API truy cập đơn hàng. Hệ thống dùng Spring Cloud Gateway để bảo vệ điểm vào và định tuyến.

### Phần A — Thiết kế tối thiểu

1. Bắt đầu bằng shared gateway. Khai báo hai route **Path=/api/products/\*\*** và **Path=/api/orders/\*\*** đến backend tương ứng, xác định rõ path phía service nhận được.
2. Thiết kế một **/mobile/home** chuyển tới mobile BFF. BFF gọi Product và Inventory, tổng hợp response chỉ chứa các trường mobile cần.
3. Bảo đảm quy tắc quyết định sản phẩm có được bán hay không vẫn nằm trong service có trách nhiệm nghiệp vụ, không trong BFF.

### Phần B — Mở rộng khi số service tăng

Khi miền Catalog xuất hiện Product, Inventory, Pricing và Search service do một đội riêng quản lý, đánh giá việc thêm Catalog domain gateway. Nếu quyết định tách, hãy xác định public contract, route nội bộ, chủ sở hữu cấu hình, chuẩn bảo mật, timeout và dashboard riêng. Giữ nguyên contract client nếu có thể.

### Phần C — Kiểm chứng hành vi

| Trường hợp | Kết quả mong đợi |
| --- | --- |
| Gọi **GET /mobile/home** | Edge chọn mobile BFF; response phản ánh contract mobile |
| Gọi **GET /api/products/42** | Route tới backend đúng, path rewrite/strip đúng |
| Token thiếu hoặc không hợp lệ | Request bị từ chối theo chính sách xác thực |
| User A đọc đơn hàng của User B | Service nghiệp vụ từ chối do thiếu quyền trên tài nguyên |
| Recommendation/Inventory chậm | Timeout và fallback theo đúng ý nghĩa dữ liệu; có trace để điều tra |
| Gửi nhiều request vượt quota | Rate limiter phản hồi theo cấu hình, không làm backend quá tải |
| Một instance gateway ngừng hoạt động | Hạ tầng vẫn chuyển được request qua instance khỏe, nếu đã cấu hình HA |

Khi kiểm thử, đối chiếu **request URL ban đầu**, **route ID được chọn**, **URL chuyển tiếp**, **header đáng tin cậy**, **mã trạng thái** và **trace**. Đó là bằng chứng trực tiếp rằng các ranh giới gateway/BFF hoạt động như thiết kế.

## 12. Ghi nhớ

- **Shared gateway** tổ chức điểm vào chung và những chính sách xuyên suốt; thường là nơi client truy cập đầu tiên.
- **Domain gateway** tổ chức API theo miền nghiệp vụ và quyền sở hữu; chỉ hữu ích khi có nhu cầu tách hợp đồng/chính sách/triển khai tương ứng.
- **BFF** tổ chức API theo trải nghiệm client; tập trung tổng hợp, điều chỉnh dữ liệu, giảm số lần gọi từ giao diện.
- **Spring Cloud Gateway** thực hiện routing, predicate, filter và các tính năng ở lớp gateway; ứng dụng BFF có thể dùng các thành phần Spring khác để triển khai logic tổng hợp.
- Hệ thống có thể kết hợp cả ba, nhưng cần thiết kế rõ luồng request, ranh giới tin cậy, timeout, retry, phân quyền và khả năng quan sát. Thêm một tầng kiến trúc chỉ hợp lý khi giải quyết nhu cầu thật và đo được chi phí của nó.
