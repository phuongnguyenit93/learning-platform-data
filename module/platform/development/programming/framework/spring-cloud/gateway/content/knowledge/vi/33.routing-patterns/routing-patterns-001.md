# Định tuyến theo phiên bản API bằng path hoặc header

## 1. Bối cảnh: một API, nhiều hợp đồng phải cùng tồn tại

Khi một hệ thống microservices phát triển, API thường có nhiều thế hệ client: ứng dụng mobile chưa cập nhật, frontend web đang chạy bản mới, hệ thống tích hợp của đối tác hoặc ứng dụng nội bộ. Nếu một thay đổi làm **không tương thích ngược**, triển khai backend mới mà không định tuyến phiên bản có thể khiến các client cũ nhận JSON sai cấu trúc, thiếu trường bắt buộc hoặc xử lý nghiệp vụ khác kỳ vọng.

Trong **Spring Cloud Gateway (SCG)**, một mẫu phổ biến là **định tuyến theo phiên bản API**: gateway đọc thông tin phiên bản trong **đường dẫn (path)** hoặc **HTTP request header**, chọn đúng route và chuyển yêu cầu tới backend triển khai hợp đồng phù hợp.

Hai request dưới đây có thể biểu diễn cùng một ý định:

~~~http
GET /api/v1/catalog/items/42 HTTP/1.1
Host: api.example.test
~~~

~~~http
GET /api/catalog/items/42 HTTP/1.1
Host: api.example.test
X-API-Version: 1
~~~

Điểm khác là **phiên bản được mang trong thành phần nào của request**. Gateway cần quy tắc rõ về cách đọc, kiểm tra và chuyển tiếp phiên bản ấy; backend cần hiểu hợp đồng `v1` hay `v2` mà request đã chọn.

Trong module **SPRING_CLOUD_GATEWAY**, chúng ta đã có những mảnh ghép như **route predicate, filter chain, chuyển đổi path/header, service discovery, Spring Security, rate limiting, circuit breaker, retry, TLS và observability**. Bài **“Định tuyến theo phiên bản API bằng path hoặc header”**, thuộc chương **Mẫu định tuyến**, kết hợp các mảnh ghép này thành kiến trúc triển khai nhiều phiên bản an toàn, dễ kiểm thử và có thể dừng hỗ trợ phiên bản cũ theo kế hoạch.

### Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt **phiên bản hợp đồng API** với **phiên bản deployment**, **phiên bản schema database** và **canary traffic splitting**.
2. Cấu hình hai tuyến `/api/v1/catalog/**` và `/api/v2/catalog/**` bằng Spring Cloud Gateway `Path` predicate.
3. Cấu hình hai tuyến cùng path `/api/catalog/**` nhưng khác `Header=X-API-Version` và hiểu regex matching.
4. Dùng `Method`, `StripPrefix`, `RemoveRequestHeader`, `SetRequestHeader` và `SetResponseHeader` đúng chiều.
5. Xử lý **missing/invalid/unsupported/duplicate/conflicting version** theo một hợp đồng có thể dự đoán.
6. Giải thích **route order, catch-all routes, filter order** và tránh định tuyến nhầm phiên bản.
7. Thiết kế **Vary: X-API-Version**, ETag và cache behavior đúng khi dùng phiên bản trong header.
8. Tách API versioning khỏi authentication/authorization, không tin header client như chứng minh danh tính.
9. Kiểm thử thực tế bằng **backend stub**, so sánh request backend nhận với response client nhận, gồm lỗi 400/404/503 và rollout.
10. Lập kế hoạch migration, deprecation, Sunset và quan sát mức sử dụng từng API version để dừng phiên bản cũ có kiểm soát.

> **Phạm vi ví dụ:** Cấu hình chính sử dụng **Spring Cloud Gateway Server WebFlux**, với namespace `spring.cloud.gateway.server.webflux.routes` ở những dòng hỗ trợ. Các dòng cũ có thể dùng `spring.cloud.gateway.routes`; **Gateway Server Web MVC** có dependency, namespace và filter chain riêng. Hãy khóa Spring Boot/Spring Cloud BOM và đọc configuration metadata theo phiên bản trước khi triển khai. Các hostname và số liệu trong bài đều là **ví dụ lab**, không phải endpoints thật.

## 2. “Phiên bản API” không đồng nghĩa “phiên bản ứng dụng”

Trước khi viết YAML, hãy quyết định chính xác **đối tượng cần versioning**.

| Khái niệm | Ví dụ | Có phải khóa chọn contract phía client? |
| --- | --- | --- |
| **API contract version** | `/api/v1/catalog` hoặc `X-API-Version: 2` | **Có**, nếu những hợp đồng khác nhau không tương thích |
| **Backend build/release version** | `catalog:2026.11.24-rc3` | Không; nhiều builds có thể cùng phục vụ API v1 |
| **Kubernetes Deployment revision** | `catalog-v2-7d9c...` | Không; đây là rollout artifact |
| **Database schema version** | Migration V37 của Flyway | Không trực tiếp; schema có thể được chia sẻ bởi nhiều API contracts |
| **Canary rollout** | 10% traffic v2 code rồi 90% v1 code | Không tự tạo API v2; chỉ phân phối traffic |
| **Content/media-type representation** | `application/vnd.example.catalog.v2+json` | Có thể là cách negotiate representation, nhưng là hợp đồng khác với custom header |
| **SemVer của SDK** | `catalog-client 3.2.1` | Không nhất thiết tương ứng API server major version |

### Khi nào cần API v2?

Một số thay đổi có khả năng phá hợp đồng của v1:

- Đổi kiểu trường `price` từ số integer sang object chứa `amount`/`currency`.
- Đổi tên hoặc bỏ trường mà client cũ bắt buộc đọc.
- Đổi phương thức `GET` thành `POST` hoặc thay semantics của resource ID.
- Thay đổi ý nghĩa pagination, error codes hoặc authorization requirements.
- Chuyển giữa các representation không tương thích, kể cả khi URL backend không đổi.

Ngược lại, thêm trường JSON *có thể* tương thích ngược nếu client được thiết kế bỏ qua unknown fields; nhưng không được mặc định mọi client/SDK đều chấp nhận. Quyết định versioning dựa trên **contract tests**, không chỉ dựa vào số lần release.

### Phiên bản hợp đồng có thể cùng tồn tại trên một backend

~~~mermaid
flowchart LR
    C["Clients"] --> G["Spring Cloud Gateway"]
    G -->|"v1 contract"| V1["catalog-v1 adapter"]
    G -->|"v2 contract"| V2["catalog-v2 adapter"]
    V1 --> Domain["Shared domain service / database"]
    V2 --> Domain
~~~

SCG có thể route đến hai backend deployments khác nhau, **hoặc** cả hai phiên bản được phục vụ trong cùng một application backend với các handlers/adapters riêng. Đường đi runtime là một lựa chọn thiết kế; **API version không buộc database hoặc infrastructure phải nhân đôi**.

## 3. Path versioning và header versioning: so sánh có chủ đích

| Tiêu chí | Phiên bản bằng path | Phiên bản bằng header |
| --- | --- | --- |
| Request mẫu | `GET /api/v1/catalog/items/42` | `GET /api/catalog/items/42` + `X-API-Version: 1` |
| Khả năng nhìn thấy trong URL/log route | Rõ ràng ở path | Không thấy nếu chỉ nhìn URL |
| Dễ dùng với browser/curl/link | Thường thuận tiện hơn | Client phải đặt request header |
| Bookmark và share URL | URL xác định phiên bản | Cùng URL có thể trả nhiều representations |
| CDN/cache | Phiên bản thường tách theo URI | Cần cache key/Vary đúng theo header |
| Reverse proxy/load balancer support | Path match phổ biến | Cần forward header và xử lý cache/header policy |
| API docs và examples | Dễ tách `/v1`, `/v2` | Phải ghi rõ header bắt buộc trong OpenAPI/docs |
| Nguy cơ client gửi dữ liệu phiên bản sai | Path `/v3` hoặc route match nhầm | Header thiếu, nhiều giá trị, malformed, proxy strip |
| OpenAPI/server URL | Thường phân biệt bằng base path | Dùng parameter/header contract phù hợp |
| Tiến hóa nhiều clients | Có thể duy trì hai paths song song | Có thể giữ endpoint path ổn định với header negotiation |
| Khi phù hợp | Public REST APIs, linkable resources, observability đơn giản | Internal APIs, clients có SDK kiểm soát headers, nhu cầu cùng URL |

**Không có lựa chọn nào mặc định tốt hơn trong mọi môi trường.** Với public API nhiều client không đồng bộ, path thường dễ khám phá. Với clients SDK có kiểm soát chặt và cần giữ URL ổn định, header có thể hợp lý. Có thể hỗ trợ **cả hai trong giai đoạn chuyển đổi**, nhưng phải có quy tắc xử lý **khi path nói v1 còn header nói v2**.

### Khuyến nghị chọn một khóa chuẩn trong nội bộ

Ngay cả khi public API hỗ trợ hai cơ chế, backend nên nhận một **version context nội bộ được Gateway xác định** (ví dụ `X-Resolved-Api-Version: 1`), chứ không tự tin cả path và raw header của client. Header nội bộ này **phải được set lại bởi Gateway** và **không phải bằng chứng danh tính**; backend vẫn xác thực người gọi và permissions.

## 4. Luồng định tuyến và ba ranh giới tin cậy

~~~mermaid
flowchart TD
    C["Client: URL hoặc X-API-Version"] --> E["Ingress / edge reverse proxy"]
    E --> S["Spring Security / request validation"]
    S --> R{"SCG Route predicates"}
    R -->|"Path /api/v1/catalog"| V1["Route catalog-v1"]
    R -->|"Path /api/v2/catalog"| V2["Route catalog-v2"]
    R -->|"Header X-API-Version: 1"| H1["Route catalog-header-v1"]
    R -->|"Header X-API-Version: 2"| H2["Route catalog-header-v2"]
    V1 --> F["Rewrite path + normalize upstream headers"]
    V2 --> F
    H1 --> F
    H2 --> F
    F --> U["Approved Catalog upstream"]
    U --> O["Response status/headers/body"]
    O --> C
~~~

Các route trên là **bốn nhánh mẫu**, không phải bốn backends bắt buộc. Khi route được chọn:

1. **Inbound boundary:** Client kiểm soát URL và request headers. Không coi `X-API-Version` là dữ liệu đáng tin về quyền truy cập.
2. **Gateway boundary:** Route predicate quyết định **hợp đồng**; filter sửa path và thay header do Gateway sở hữu; Spring Security quyết định quyền.
3. **Outbound boundary:** SCG HTTP client gọi một upstream URI/service đã được cho phép. Backend nhận request đã normalize, kiểm tra identity và resource authorization của chính nó.

Một request **không match route** có thể dừng ở Gateway (ví dụ 404), không có cuộc gọi tới backend. Một request bị Spring Security chặn (401/403) cũng không nên có outbound HTTP attempt. Đây là các tình huống cần đo riêng trong kiểm thử, không gom tất cả lỗi thành “backend 404”.

## 5. Thiết kế contract và bảng tuyến trước khi viết YAML

Giả định Catalog cung cấp:

- **v1:** `{"id":"42","price":1000}`.
- **v2:** `{"id":"42","price":{"amount":1000,"currency":"VND"}}`.

Backend của mỗi phiên bản cùng nhận path nội bộ:

~~~text
GET /items/42?lang=vi
~~~

Kế hoạch định tuyến:

| Client request | Version | Gateway route ID | Backend URI | Backend path |
| --- | --- | --- | --- | --- |
| `GET /api/v1/catalog/items/42` | 1 | `catalog-path-v1` | `http://catalog-v1.internal:8080` | `/items/42` |
| `GET /api/v2/catalog/items/42` | 2 | `catalog-path-v2` | `http://catalog-v2.internal:8080` | `/items/42` |
| `GET /api/catalog/items/42` + `X-API-Version: 1` | 1 | `catalog-header-v1` | `http://catalog-v1.internal:8080` | `/items/42` |
| `GET /api/catalog/items/42` + `X-API-Version: 2` | 2 | `catalog-header-v2` | `http://catalog-v2.internal:8080` | `/items/42` |

Trong lab, hai URI cần được thay bằng địa chỉ của **backend stubs**. Trong production, hostname phải được kiểm soát qua configuration/discovery, không lấy từ query hoặc header do client tự chọn. Nếu cần TLS nội bộ, dùng `https://...` và cấu hình hostname/certificate verification; các URI HTTP trong ví dụ chỉ để minh họa route.

### Những quyết định phải có trước

1. Chỉ hỗ trợ **v1 và v2** hay có default version?
2. Vắng header có phải là lỗi 400, hay dùng một default được tài liệu hóa?
3. Path có hỗ trợ header bổ sung không? Nếu có, conflict được xử lý thế nào?
4. Với unknown version `v3`, trả 400/404/406/410 theo contract nào?
5. Backend version có cùng authentication/scope/tenant model không?
6. CDN và browser cache có phân biệt hai versions bằng cache key không?
7. Khi retire v1, response và Sunset/deprecation timeline được thông báo thế nào?

Mỗi câu trả lời nên thể hiện trong **test matrix**, không chỉ trong wiki.

## 6. Cấu hình Spring Cloud Gateway: route theo path

Trong Gateway Server WebFlux, `Path` route predicate quyết định route dựa trên đường dẫn HTTP. Mỗi route có `id`, `uri`, `predicates` và có thể thêm `filters`.

### 6.1. Hai tuyến v1/v2 được tách tường minh

Đây là **một** tệp cấu hình hoàn chỉnh cho lab, gồm cả phương án path và header để có thể kiểm thử chung. Bốn routes **không trùng nhau** vì hai nhóm sử dụng hai kiểu đường dẫn khác nhau.

~~~yaml
server:
  port: 8080

spring:
  cloud:
    gateway:
      server:
        webflux:
          routes:
            # PHƯƠNG ÁN A: version nằm trong path.
            - id: catalog-path-v1
              order: 0
              uri: ${catalog.v1-base-url}
              predicates:
                - Path=/api/v1/catalog/**
                - Method=GET
              filters:
                - StripPrefix=3
                - RemoveRequestHeader=X-API-Version
                - SetRequestHeader=X-Resolved-Api-Version,1
                - SetResponseHeader=X-Resolved-Api-Version,1

            - id: catalog-path-v2
              order: 0
              uri: ${catalog.v2-base-url}
              predicates:
                - Path=/api/v2/catalog/**
                - Method=GET
              filters:
                - StripPrefix=3
                - RemoveRequestHeader=X-API-Version
                - SetRequestHeader=X-Resolved-Api-Version,2
                - SetResponseHeader=X-Resolved-Api-Version,2

            # PHƯƠNG ÁN B: version nằm trong X-API-Version.
            - id: catalog-header-v1
              order: 0
              uri: ${catalog.v1-base-url}
              predicates:
                - Path=/api/catalog/**
                - Method=GET
                - Header=X-API-Version, ^1$
              filters:
                - StripPrefix=2
                - RemoveRequestHeader=X-API-Version
                - SetRequestHeader=X-Resolved-Api-Version,1
                - SetResponseHeader=X-Resolved-Api-Version,1

            - id: catalog-header-v2
              order: 0
              uri: ${catalog.v2-base-url}
              predicates:
                - Path=/api/catalog/**
                - Method=GET
                - Header=X-API-Version, ^2$
              filters:
                - StripPrefix=2
                - RemoveRequestHeader=X-API-Version
                - SetRequestHeader=X-Resolved-Api-Version,2
                - SetResponseHeader=X-Resolved-Api-Version,2

catalog:
  v1-base-url: http://127.0.0.1:9001
  v2-base-url: http://127.0.0.1:9002
~~~

**Hai cổng 9001/9002 chỉ là ví dụ local.** Trong test thực, nên dùng backend stubs có port động và cấu hình qua `@DynamicPropertySource`. Trong production, khai báo URI từ nguồn cấu hình được kiểm soát hoặc `lb://` với discovery integration đã được kiểm chứng. Không lấy URI upstream từ một header như `X-Backend-Url` do client gửi.

### 6.2. Vì sao StripPrefix=3 cho path version?

Với request:

~~~text
/api/v1/catalog/items/42?lang=vi
  1   2      3      4    5
~~~

Ba path segments đầu là `api`, `v1`, `catalog`. `StripPrefix=3` bỏ chúng để backend nhận:

~~~http
GET /items/42?lang=vi HTTP/1.1
X-Resolved-Api-Version: 1
~~~

Query string `lang=vi` không tự trở thành path segment; filter dự kiến giữ nó. Dẫu vậy, **đường dẫn có phần mã hóa đặc biệt, encoded slash, plus hoặc double slash** có thể chịu tác động của URI parser, proxy phía trước và Spring Cloud Gateway version; phải kiểm thử raw URI trên runtime thật.

Nếu backend v1 đòi `/v1/items/42` thay vì `/items/42`, không dùng nguyên cấu hình `StripPrefix=3`: cần đổi phép rewrite hoặc backend contract. Đừng “sửa lỗi” bằng cách vừa rewrite ở ingress vừa strip ở SCG mà không có sơ đồ đường dẫn.

### 6.3. Hai chiều SetRequestHeader và SetResponseHeader

| Filter | Phía nhận | Mục đích |
| --- | --- | --- |
| `RemoveRequestHeader=X-API-Version` | **Upstream request** | Loại header thô của client sau khi Gateway đã chọn version |
| `SetRequestHeader=X-Resolved-Api-Version,1` | **Upstream request** | Ghi đè header canonical do Gateway quản lý |
| `SetResponseHeader=X-Resolved-Api-Version,1` | **Client response** | Thông báo phiên bản hợp đồng thực sự được route |
| `StripPrefix=3` | **Upstream request path** | Bỏ prefix version trước khi gọi backend |

Đặc biệt, `SetRequestHeader` **thay giá trị**; `AddRequestHeader` thường **thêm giá trị**, có thể khiến backend nhận hai phiên bản khác nhau nếu client gửi header giả trước. Header `X-Resolved-Api-Version` vẫn chỉ là metadata nội bộ và **không phải bằng chứng client được phép gọi API**.

### 6.4. Prefix root và trailing slash

`Path=/api/v1/catalog/**` được dùng để match các tài nguyên phía dưới. Hành vi ở `/api/v1/catalog`, `/api/v1/catalog/` hoặc request có encoded slash phụ thuộc path matcher/version và cấu hình trailing slash. Nếu contract cho phép gọi collection root, **viết test riêng** và cân nhắc bổ sung pattern rõ ràng; không suy rằng mọi biến thể tự match như nhau.

## 7. Cấu hình theo header: cùng URL, khác route

Trong hai route `catalog-header-v1` và `catalog-header-v2` ở phần 6, request path đều là:

~~~text
/api/catalog/items/42
~~~

Gateway phân biệt bằng **Header route predicate**:

~~~yaml
# Trích hai predicates trong cùng một route:
predicates:
  - Path=/api/catalog/**
  - Method=GET
  - Header=X-API-Version, ^1$
~~~

Header value `1` sẽ chọn v1; `2` chọn v2, khi request phù hợp tất cả predicates của route tương ứng.

### 7.1. Regex có neo đầu/cuối

`Header=X-API-Version, ^1$` dùng regex cho **giá trị header**. Neo `^` và `$` giúp biểu diễn yêu cầu **giá trị đúng chính xác** `1`, tránh cố ý match những giá trị như `10`, `v1` hoặc `preview-1`.

| Header do client gửi | Route v1 nên match? | Route v2 nên match? |
| --- | --- | --- |
| `X-API-Version: 1` | Có | Không |
| `X-API-Version: 2` | Không | Có |
| `X-API-Version: 10` | Không | Không |
| `X-API-Version: v1` | Không | Không |
| `X-API-Version: 1,2` | Không theo regex exact | Không theo regex exact |
| Không có header | Không | Không |
| Hai header fields `1` và `2` | **Có nguy cơ** mỗi route match một value | **Có nguy cơ** mỗi route match một value |

Điểm cuối cùng rất quan trọng: một số implementations của Header predicate có thể xét **từng giá trị trong nhiều HTTP header values**. Nếu client gửi lặp `X-API-Version` một lần `1` và một lần `2`, một route có thể thấy value `1`, route khác thấy `2`. Vì vậy **regex chính xác không thay kiểm tra header trùng lặp**. Khi version có nhiều giá trị, nên trả lỗi theo contract **trước khi chọn route** (xem phần 9).

### 7.2. StripPrefix=2 cho header version

~~~text
/api/catalog/items/42?lang=vi
  1      2     3    4
~~~

Ở đây chỉ có hai prefix segments `api` và `catalog`; `StripPrefix=2` đưa path về `/items/42`. Nếu vô tình dùng `StripPrefix=3` giống path version, request có thể thành `/42` và backend trả 404.

### 7.3. Header version nên được normalize trước backend

Trong cấu hình phần 6:

~~~text
Client:   X-API-Version: 1
            |
SCG:      Header predicate chọn catalog-header-v1
            |
SCG:      RemoveRequestHeader: X-API-Version
            |
SCG:      SetRequestHeader: X-Resolved-Api-Version: 1
            |
Backend:  X-Resolved-Api-Version: 1
~~~

Nhờ đó backend không phải tự diễn giải một tập các cách ghi version khác nhau. Nhưng **backend nên tin version từ route/config đã xác thực chứ không phải bất kỳ client nào có thể tự gọi trực tiếp tới backend**. Nếu backend dựa trên header canonical để chọn hợp đồng mà vẫn public trực tiếp, client có thể giả header này; cần network policy, mTLS/service identity hoặc backend validation thích hợp.

### 7.4. Header path và browser behavior

Một HTTP browser fetch gửi custom `X-API-Version` cross-origin có thể kích hoạt **CORS preflight OPTIONS**. Route chỉ nhận `Method=GET`, trong khi preflight là OPTIONS và thường **không chứa `X-API-Version` với cùng hình thức như GET thực**. Vì vậy phải cấu hình CORS ở ingress/Gateway/Spring Security để xử lý OPTIONS đúng cách, **không ép preflight phải match Header predicate của GET**.

## 8. Route matching là phép AND, ưu tiên route không phải fallback business

Trong SCG, các predicates của một route thông thường được kết hợp theo **AND**. Với route:

~~~yaml
predicates:
  - Path=/api/catalog/**
  - Method=GET
  - Header=X-API-Version, ^2$
~~~

request phải đồng thời có path hợp lệ, method GET và header version value hợp lệ để match **route đó**. Đây không phải “Path OR Method OR Header”.

### 8.1. Tránh route catch-all nuốt yêu cầu thiếu version

Ví dụ nguy hiểm:

~~~yaml
# CHỐNG MẪU khi không có default version được phê duyệt.
- id: catalog-catch-all
  uri: http://catalog-v2.internal:8080
  predicates:
    - Path=/api/catalog/**
~~~

Request thiếu `X-API-Version` có thể bị route catch-all đưa tới v2, khiến client vốn không khai version nhận hợp đồng mới không mong đợi. Trong API versioning, **không match thường an toàn hơn âm thầm đổi hợp đồng**, trừ khi đã công bố một default.

### 8.2. order không thay chính sách kiểm tra version

Routes có trường `order`; trong cơ chế chọn route phổ biến, giá trị thấp hơn có độ ưu tiên cao hơn. Tuy vậy:

- Những routes được thiết kế **không chồng lấn** sẽ dễ bảo trì hơn các routes phải phụ thuộc thứ tự.
- Nếu hai routes cùng match, một thứ tự có thể quyết định route được dùng; đây không phải bằng chứng client thật sự khai đúng một version.
- Nếu nhiều routes cùng `order`, không nên phụ thuộc vào thứ tự khai báo hoặc chi tiết RouteDefinitionLocator không được cam kết làm hợp đồng nghiệp vụ.
- Một global route `Path=/**` có thể làm route version bị che nếu cấu hình priority sai.
- Spring Security/WebFilter và route predicates chạy ở **những lớp khác nhau**; route order không thay quyền truy cập.

**Thiết kế ưu tiên:** Một tập các predicates rõ và loại trừ nhau, validator cho ambiguous/missing versions, và regression tests về route ID/backends. `order` là công cụ quản lý route priority, không phải cơ chế “phiên bản nào mới hơn thì được chọn”.

### 8.3. Một route match không chứng minh backend sẽ trả đúng

Sau khi route match, Gateway còn phải resolve URI/`lb://` service instance, lấy outbound connection, truyền headers/body và nhận response. Backend có thể:

- Không sẵn sàng → 502/503 theo transport policy.
- Trả 404 vì `StripPrefix` sai hoặc item không tồn tại.
- Trả 503/429 hợp lệ theo nghiệp vụ/vận hành.
- Trả JSON của phiên bản khác vì service deployment/config chưa đồng bộ.

**Test phải quan sát backend thực sự nhận gì**, không chỉ assert route match hoặc response 200.

## 9. Xử lý header thiếu, sai định dạng và xung đột bằng WebFilter

Các route predicates **chọn route**, chứ không phải API validator trả một thông báo lỗi theo hợp đồng. Nếu header không match route, Gateway thường tiếp tục tìm tuyến khác; nếu không có tuyến, response có thể là 404. Khi muốn trả **400 Bad Request** cho phiên bản thiếu, không hợp lệ hoặc xung đột, cần triển khai **một bước validation riêng**, có tests và được đặt đúng vị trí trong pipeline.

### 9.1. Hợp đồng của lab

| Tình huống | Hành vi chủ đích |
| --- | --- |
| `GET /api/v1/catalog/items/42` không có version header | Cho qua, chọn path v1 |
| `GET /api/v1/catalog/items/42` + header `1` | Cho qua, chọn path v1; bỏ raw header trước backend |
| `GET /api/v1/catalog/items/42` + header `2` | Trả **400**, không gọi backend |
| `GET /api/catalog/items/42` không có header | Trả **400**, không âm thầm chọn v1 hoặc v2 |
| `GET /api/catalog/items/42` + header `3` | Trả **400** theo hợp đồng custom-header của lab |
| `GET /api/catalog/items/42` + hai giá trị `1` và `2` | Trả **400** vì ambiguous |
| `GET /api/v3/catalog/items/42` | **404** vì không có path route v3, nếu không có catch-all |
| `OPTIONS /api/catalog/items/42` (CORS preflight) | Chuyển tiếp tới CORS/security handling, không bắt buộc version header |

### 9.2. Ví dụ WebFlux WebFilter kiểm tra version contract

~~~java
import java.util.List;

import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Component;
import org.springframework.web.server.ServerWebExchange;
import org.springframework.web.server.WebFilter;
import org.springframework.web.server.WebFilterChain;
import reactor.core.publisher.Mono;

@Component
public final class ApiVersionValidationWebFilter implements WebFilter {

    private static final String HEADER = "X-API-Version";

    @Override
    public Mono<Void> filter(
            ServerWebExchange exchange,
            WebFilterChain chain
    ) {
        // Đừng ép preflight OPTIONS hoặc method khác vào hợp đồng GET này.
        if (!HttpMethod.GET.equals(exchange.getRequest().getMethod())) {
            return chain.filter(exchange);
        }

        String path = exchange.getRequest().getURI().getRawPath();
        List<String> versions =
                exchange.getRequest().getHeaders().get(HEADER);
        String fromPath = versionInPath(path);

        if (fromPath != null) {
            // Path đã chỉ rõ v1/v2; header nếu có phải nhất quán.
            if (versions != null &&
                    (versions.size() != 1
                    || !fromPath.equals(versions.get(0)))) {
                return badRequest(exchange);
            }
        } else if (isHeaderVersionedCatalogPath(path)) {
            // Với /api/catalog/**, yêu cầu đúng một giá trị 1 hoặc 2.
            if (versions == null || versions.size() != 1
                    || (!"1".equals(versions.get(0))
                    && !"2".equals(versions.get(0)))) {
                return badRequest(exchange);
            }
        }

        return chain.filter(exchange);
    }

    private static String versionInPath(String path) {
        if (path.equals("/api/v1/catalog")
                || path.startsWith("/api/v1/catalog/")) {
            return "1";
        }
        if (path.equals("/api/v2/catalog")
                || path.startsWith("/api/v2/catalog/")) {
            return "2";
        }
        return null;
    }

    private static boolean isHeaderVersionedCatalogPath(String path) {
        return path.equals("/api/catalog")
                || path.startsWith("/api/catalog/");
    }

    private static Mono<Void> badRequest(ServerWebExchange exchange) {
        exchange.getResponse().setStatusCode(HttpStatus.BAD_REQUEST);
        return exchange.getResponse().setComplete();
    }
}
~~~

Ví dụ này **không trả body lỗi**, chỉ minh họa một validator dễ kiểm thử cho hai phiên bản và một nhóm path. Nếu API cần JSON `application/problem+json` theo RFC 9457, dùng error handling phù hợp, trả body/status/header đúng, không ghi raw token vào response/log.

**Giới hạn cần hiểu:**

1. `WebFilter` là thành phần **WebFlux**, chạy ở tầng web chứ không phải một `GatewayFilter` chỉ áp cho route đã chọn. Chỉ áp nó trên đúng những paths/methods muốn kiểm soát.
2. Nó không tự thay Spring Security: thứ tự security filters và validator ảnh hưởng việc client thấy 400 hay 401/403 nếu cùng request vừa sai authentication vừa sai version.
3. Không sử dụng raw path matching trong ví dụ làm quy tắc authorization. Servlet/Netty/ingress có thể xử lý encoded slash, double slash, percent encoding khác nhau; kiểm thử và normalize đường dẫn ở ranh giới đúng.
4. Các version khác `v1`/`v2` trong **path** không bị validator này bắt; chúng chỉ không match routes. Muốn trả 410/400 cho version cũ, xây tombstone/error route rõ.
5. Một HTTP header field `X-API-Version: 1,2` là **một chuỗi** và cũng bị từ chối. Hai HTTP header fields riêng cũng bị từ chối vì `versions.size() != 1`.
6. Nếu tổ chức dùng custom filters khác để rewrite path trước khi validation, phải chỉ rõ stage path đang kiểm tra; không mặc định raw URI tương ứng mọi route representation.

### 9.3. Tại sao không dùng một catch-all route để trả 400?

Có thể tạo một route `Path=/api/catalog/**` với thứ tự thấp hơn và xử lý lỗi trong `forward:` handler, nhưng phải bảo đảm **không che route hợp lệ**, không tạo outbound call và không xung đột security. Với bài toán chỉ kiểm tra một header, WebFilter/validation component rõ ràng thường dễ audit hơn. Trong hệ thống nhiều API versions, có thể dùng shared version-negotiation policy nhưng cần có ma trận route conflict đầy đủ.

## 10. Chọn HTTP status cho phiên bản lỗi hoặc đã ngừng hỗ trợ

Không có một HTTP status duy nhất bắt buộc cho mọi API versioning scheme. Quan trọng là **tài liệu công khai, mã hóa nhất quán, phân biệt lỗi input với lỗi backend và migration behavior**.

| Trường hợp | Status có thể chọn | Diễn giải |
| --- | --- | --- |
| Thiếu `X-API-Version` khi bắt buộc | **400** | Client thiếu tham số/header theo contract |
| Header phiên bản sai format hoặc nhiều giá trị | **400** | Request không hợp lệ/ambiguous |
| Header phiên bản không được hỗ trợ | **400** hoặc status chính sách riêng | Không tự âm thầm nâng/hạ phiên bản |
| Path `/api/v3/...` không tồn tại | **404** thường gặp | Không có route cho version trong URL |
| Version đã nghỉ hưu, chủ động công bố endpoint không còn | **410 Gone** nếu có tombstone route | Chỉ gửi khi cố ý thông báo resource/route đã dừng |
| Content negotiation qua `Accept` không có representation đáp ứng | **406 Not Acceptable** khi đúng semantics HTTP | Phù hợp content negotiation, không tự phát sinh từ Header predicate |
| Client không có quyền gọi phiên bản | **401/403** theo security contract | Version hợp lệ không cấp quyền |
| Backend không sẵn sàng | **502/503/504** tùy lỗi và policy | Không nói “version sai” khi thực tế là transport/backend failure |

### Không để mặc định chọn “latest” mà không có hợp đồng

Một số nhóm muốn header trống tự chọn **phiên bản mới nhất**. Điều này có vẻ thân thiện nhưng tạo rủi ro khi:

- v2 thay đổi semantics có thể làm client cũ hỏng mà không đổi request.
- Cache của cùng URL có thể lưu representation mới không phù hợp client khác.
- Deployment rolling update có thể khiến default version khác nhau giữa các Gateway replicas.
- Error rate chỉ tăng ở một số clients và khó phát hiện nguồn.

Nếu thật sự muốn default, **cố định một phiên bản công khai** (ví dụ v1 cho đến một mốc migration), tài liệu hóa thời hạn và viết tests cho transition. Không dùng `latest` làm alias tự đổi theo từng deployment.

### Error response nên giúp client sửa request

Với custom-header versioning, một error payload có thể có dạng:

~~~json
{
  "type": "https://api.example.test/problems/invalid-api-version",
  "title": "Invalid API version",
  "status": 400,
  "detail": "Use one X-API-Version header with value 1 or 2."
}
~~~

Đây là **hợp đồng minh họa**, không phải body tự sinh ra từ `WebFilter` phần 9. Nếu muốn hỗ trợ `application/problem+json`, thực hiện đúng content type/serialization và kiểm soát không đưa URL backend, security exception hoặc credentials vào error.

## 11. Path rewriting, query preservation và URI encoding

Trong Gateway có thể có nhiều điểm thay đổi URI: ingress, Spring Cloud Gateway `StripPrefix`/`RewritePath`, HTTP client và backend router. Versioned routing dễ hỏng nếu hai lớp cùng đổi một segment.

### 11.1. So sánh path trước/sau filter

| Client path | Route | StripPrefix | Backend path kỳ vọng |
| --- | --- | --- | --- |
| `/api/v1/catalog/items/42` | `catalog-path-v1` | 3 | `/items/42` |
| `/api/v2/catalog/items/42` | `catalog-path-v2` | 3 | `/items/42` |
| `/api/catalog/items/42` + header `1` | `catalog-header-v1` | 2 | `/items/42` |
| `/api/catalog/items/42` + header `2` | `catalog-header-v2` | 2 | `/items/42` |

### 11.2. Query string và percent encoding là một phần của contract

~~~http
GET /api/v2/catalog/items/42?lang=vi&tag=a%2Bb HTTP/1.1
X-API-Version: 2
~~~

Backend có thể cần nhìn `tag=a%2Bb` (literal plus sau decode) khác với `tag=a+b` (thường biểu diễn space trong form-style query parsing). Nếu một custom rewrite decode rồi encode lại không đúng, chữ ký request, cache key hoặc search semantics có thể thay đổi.

Vì vậy kiểm thử cả:

- Query rỗng, nhiều tham số và tham số lặp.
- `+`, `%2B`, `%20` và Unicode UTF-8 percent encoding.
- Encoded slash `%2F`, double slash, trailing slash và semicolon nếu contract liên quan.
- Path variables có ký tự đặc biệt và một số ingress/Servlet/Netty versions có thể từ chối trước Gateway route.
- Raw query/backend URI được ghi bằng stub, **không chỉ so sánh decoded `getParameter()`**.

Không dùng string replace kiểu `path.replace("/v1", "")` trên raw URL không kiểm soát: nó có thể xóa nhầm một segment có chữ `v1` ở giữa hoặc thay đổi dấu slash. Dùng filters/path rules rõ ràng và test cả encoded edge cases.

### 11.3. Lỗi double rewrite từ ingress

~~~text
Client:         /api/v1/catalog/items/42
Ingress:        strip /api  -> /v1/catalog/items/42
SCG Path:       /api/v1/catalog/**   <-- KHÔNG MATCH
Backend HITS:   0
~~~

Để tránh lỗi, chọn **một owner** cho rewrite:

1. Ingress/Gateway API chỉ match host/path và chuyển nguyên prefix đến SCG; SCG strip path như YAML.
2. Hoặc ingress rewrite theo contract rõ, và SCG route predicates/filters được thiết kế cho path đã rewrite.

**Không suy rằng Path predicate tự cắt prefix.** Nó chọn route; `StripPrefix`/`RewritePath` mới thay đổi request path.

### 11.4. Trường hợp RewritePath thực sự cần

Khi backend path khác về cấu trúc chứ không chỉ cần bỏ một số segments, dùng `RewritePath` với regex và capture groups phù hợp. Ví dụ v2 `/api/v2/catalog/items/42` cần `/inventory/items/42`:

~~~yaml
# Trích filter riêng để minh họa; KHÔNG dùng cùng StripPrefix của route đó.
filters:
  - RewritePath=/api/v2/catalog/(?<segment>.*), /inventory/$\{segment}
~~~

Trong YAML/Spring property binding, replacement dạng `$\{segment}` (dấu `$` được escape bằng ký tự backslash theo ví dụ SCG documentation) giúp tránh nhầm với Spring property placeholder. Quy tắc escape chính xác phụ thuộc cách YAML/string được parse, vì vậy phải **test URI thực gửi tới backend**, không chỉ nhìn cấu hình. Đừng kết hợp một `RewritePath` giả định path gốc với `StripPrefix` đã làm biến mất prefix.

## 12. Cache, Vary và ETag: điểm khó nhất của header versioning

Với path versioning, hai hợp đồng thường có **hai URIs khác nhau**:

~~~text
/api/v1/catalog/items/42
/api/v2/catalog/items/42
~~~

Với header versioning, URI **giống hệt nhau**, nhưng response body khác:

~~~http
GET /api/catalog/items/42 HTTP/1.1
X-API-Version: 1
~~~

~~~json
{"id":"42","price":1000}
~~~

~~~http
GET /api/catalog/items/42 HTTP/1.1
X-API-Version: 2
~~~

~~~json
{"id":"42","price":{"amount":1000,"currency":"VND"}}
~~~

Nếu một shared cache/CDN dùng **chỉ URL** làm cache key, client v2 có thể nhận JSON v1 và ngược lại. Đối với cache dùng HTTP semantics, response cần thông báo rằng representation thay đổi theo header `X-API-Version`:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Vary: X-API-Version
ETag: "catalog-v2-item-42-r7"
~~~

### 12.1. Vary là một phần của response contract

- `Vary: X-API-Version` cho biết cached response cần được chọn theo giá trị request header đó.
- Nếu response còn thay đổi theo `Accept-Encoding`, `Accept-Language` hoặc `Origin` do CORS, phải giữ những dimensions hợp lệ, **không ghi đè toàn bộ Vary bằng một giá trị mới**.
- `Vary: *` có semantics đặc biệt; đừng thêm thủ công các values khác một cách vô nghĩa.
- Một số CDN có cache policy riêng hoặc không đưa custom headers vào cache key như bạn kỳ vọng; cần **cấu hình CDN và test HTTP cache thực**.
- `Vary` không thay authentication hoặc cache privacy. Personalized/secret-bearing response có thể cần `Cache-Control: private, no-store`.

### 12.2. Không dùng SetResponseHeader=Vary một cách mù quáng

Một cấu hình kiểu:

~~~yaml
# CHỐNG MẪU nếu upstream đã gửi Vary: Accept-Encoding, Origin.
filters:
  - SetResponseHeader=Vary,X-API-Version
~~~

có thể **thay mất** những giá trị `Vary` đã có từ backend/Spring Security/CORS. Trong hệ thống có header versioning, dùng response policy có khả năng **merge Vary token** (ví dụ response decorator/custom filter được kiểm thử) hoặc thiết lập ở nguồn backend cho đúng representation.

### 12.3. Một ví dụ GlobalFilter bổ sung Vary mà không xóa giá trị cũ

~~~java
import java.util.Arrays;
import java.util.List;

import org.springframework.cloud.gateway.filter.GatewayFilterChain;
import org.springframework.cloud.gateway.filter.GlobalFilter;
import org.springframework.cloud.gateway.route.Route;
import org.springframework.cloud.gateway.support.ServerWebExchangeUtils;
import org.springframework.core.Ordered;
import org.springframework.http.HttpHeaders;
import org.springframework.stereotype.Component;
import org.springframework.web.server.ServerWebExchange;
import reactor.core.publisher.Mono;

@Component
public final class ApiVersionVaryGlobalFilter
        implements GlobalFilter, Ordered {

    @Override
    public int getOrder() {
        return -100;
    }

    @Override
    public Mono<Void> filter(
            ServerWebExchange exchange,
            GatewayFilterChain chain
    ) {
        Route route = exchange.getAttribute(
                ServerWebExchangeUtils.GATEWAY_ROUTE_ATTR);

        if (route == null ||
                !route.getId().startsWith("catalog-header-v")) {
            return chain.filter(exchange);
        }

        exchange.getResponse().beforeCommit(() -> {
            HttpHeaders responseHeaders =
                    exchange.getResponse().getHeaders();
            List<String> fields =
                    responseHeaders.get(HttpHeaders.VARY);

            boolean alreadyCovered = fields != null
                    && fields.stream()
                    .flatMap(field ->
                            Arrays.stream(field.split(",")))
                    .map(String::trim)
                    .anyMatch(token -> token.equals("*")
                            || token.equalsIgnoreCase("X-API-Version"));

            if (!alreadyCovered) {
                responseHeaders.add(
                        HttpHeaders.VARY, "X-API-Version");
            }

            return Mono.empty();
        });

        return chain.filter(exchange);
    }
}
~~~

**Mục đích:** Khi response đi qua một route `catalog-header-v*`, thêm một trường Vary hợp lệ nếu chưa có `X-API-Version` hoặc `*`. Điều này **không kiểm tra cache policy của CDN**, không bảo đảm upstream tự xây đúng ETag, và không thay xử lý `Cache-Control` cho dữ liệu nhạy cảm. GlobalFilter chỉ chạy khi request match Gateway route; request bị Security chặn sớm hoặc route miss sẽ không nhất thiết đi qua filter.

### 12.4. ETag phải đại diện cho đúng versioned representation

Nếu v1 body là số `1000` còn v2 body là object, hai bytes representations khác nhau. Một backend không nên tùy tiện tái sử dụng **cùng strong ETag** cho chúng. Nếu Gateway có filter biến đổi JSON, ETag/Content-Length/Content-Encoding và Content-Type phải tương ứng body **thực** gửi client.

### 12.5. Conditional GET và status 304

Khi client gửi `If-None-Match`, backend/cache cần so sánh validator cho **đúng API version**. Một 304 có `Vary` hoặc `ETag` bị bỏ có thể làm cache chọn nhầm representation. Test v1→v2 với cùng URL, các validators khác nhau và request lặp; đừng chỉ test GET 200.

## 13. Header version so với Accept/media-type versioning

Ngoài custom header `X-API-Version`, HTTP còn có cơ chế **content negotiation** qua `Accept` và `Content-Type`. Ví dụ:

~~~http
GET /api/catalog/items/42 HTTP/1.1
Accept: application/vnd.example.catalog.v2+json
~~~

Một backend có thể chọn representation v2 khi thấy media type đó; khi không có representation phù hợp, **406 Not Acceptable** có thể là status phù hợp. Nhưng đây là **một giao thức phiên bản khác**, không mặc nhiên tương đương với `X-API-Version: 2`.

### 13.1. Vì sao không dùng regex Accept đơn giản như parser đầy đủ?

~~~yaml
# CHỈ minh họa ý tưởng route, KHÔNG phải HTTP content negotiation đầy đủ.
predicates:
  - Header=Accept, .*application/vnd\.example\.catalog\.v2\+json.*
~~~

Giá trị `Accept` có thể chứa **nhiều media ranges**, tham số, mức ưu tiên `q=`, wildcard và thứ tự khác nhau. Một regex chỉ tìm substring `v2` có thể nhận v2 ngay cả khi client đã đặt `q=0` (không chấp nhận) hoặc ưu tiên media type khác cao hơn. Nó cũng có thể match trong những chuỗi không đúng format.

Nếu sản phẩm quyết định dùng versioning qua `Accept`, nên sử dụng **parser/negotiation strategy tôn trọng HTTP semantics**, có test với nhiều Accept values và quality factors, hoặc đặt chính sách negotiation ở backend/app phù hợp. Spring Cloud Gateway `Header` predicate thích hợp cho **header version có format đơn giản, exact/regex đã xác định**, không thay toàn bộ content negotiation của HTTP.

### 13.2. Request Content-Type khác response Accept

- `Accept` cho biết representation response mà client muốn nhận.
- `Content-Type` của request cho biết định dạng body client đang gửi.
- Một route API v2 có thể nhận `Content-Type: application/json` và trả `application/vnd.example.catalog.v2+json` nếu contract quy định.
- Không coi `Content-Type` của request là version selector nếu hợp đồng của bạn đã chọn `X-API-Version` hoặc path.

### 13.3. Tránh nhiều khóa nguồn sự thật

Ví dụ request:

~~~http
GET /api/v1/catalog/items/42 HTTP/1.1
X-API-Version: 2
Accept: application/vnd.example.catalog.v2+json
~~~

Đây là **ba tín hiệu mâu thuẫn**. Nếu hệ thống hỗ trợ nhiều cách negotiate trong giai đoạn migration, phải xác định **cái nào được ưu tiên, trường hợp nào bị từ chối** và test thật. Chính sách dễ kiểm soát nhất thường là **một nguồn quyết định hợp đồng**, còn những hints khác phải tương thích với nguồn đó.

## 14. Security: phiên bản là lựa chọn contract, không phải chứng cứ quyền truy cập

Client kiểm soát `/api/v2/...` và `X-API-Version: 2`. Vì vậy việc chọn một API version **không tự xác thực user**, không chứng minh tenant, không cấp `ROLE_ADMIN` và không thay quyền đọc tài nguyên.

### 14.1. Spring Security phải bao phủ mọi phiên bản

Ví dụ yêu cầu:

- Catalog GET v1/v2 là public.
- Orders GET v1/v2 yêu cầu scope `orders.read`.
- Mọi request khác bị deny-by-default.

Với **Server WebFlux** và ứng dụng Resource Server Bearer-only:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
@EnableWebFluxSecurity
public class ApiSecurityConfiguration {

    @Bean
    SecurityWebFilterChain security(ServerHttpSecurity http) {
        return http
                .authorizeExchange(auth -> auth
                        .pathMatchers(HttpMethod.GET,
                                "/api/v1/catalog/**",
                                "/api/v2/catalog/**",
                                "/api/catalog/**")
                            .permitAll()
                        .pathMatchers(HttpMethod.GET,
                                "/api/v1/orders/**",
                                "/api/v2/orders/**")
                            .hasAuthority("SCOPE_orders.read")
                        .anyExchange().denyAll()
                )
                .oauth2ResourceServer(resourceServer ->
                        resourceServer.jwt(Customizer.withDefaults()))
                // Chỉ hợp lý với API stateless chỉ dùng Bearer token.
                .csrf(ServerHttpSecurity.CsrfSpec::disable)
                .build();
    }
}
~~~

**Chú ý:** Đây là minh họa security rules cho những routes đã nêu; không bao gồm mọi CORS/preflight, Actuator/health, error handler hoặc authorization rules của một hệ thống thật. Nếu Kubernetes probes gọi health endpoints, cần chính sách probe riêng ở management network. Nếu browser dùng cookie/session auth, **không tắt CSRF vô điều kiện**. Cần cấu hình resource-server JWT issuer/JWKS/signature, `aud` (audience theo API), expiration và authority mapping đúng; validator có thể cần tùy chỉnh audience theo release.

Nếu URL được gateway route qua `/api/v2/orders/**` nhưng Spring Security chỉ bảo vệ `/api/v1/orders/**`, phiên bản v2 có thể thành **lối vòng qua authorization**. Các matcher phải được cập nhật cùng route definitions. Dùng tests cho mọi version, methods khác GET, đường dẫn encoded/trailing slash và default/catch-all routes.

### 14.2. Backend vẫn phải kiểm tra quyền nghiệp vụ

Backend Orders cần kiểm tra quyền theo **principal/tenant/resource ownership**; một user có scope `orders.read` không đương nhiên được đọc đơn hàng của bất kỳ user khác. Nếu backend được gọi trực tiếp ngoài Gateway hoặc qua route khác, nó không thể chỉ tin header `X-Resolved-Api-Version` và bỏ authentication.

### 14.3. Token forwarding không được quyết định bởi version

Một số backend v1/v2 có thể yêu cầu token có **audience khác nhau** hoặc các service credentials riêng. Không tự forward bearer token của client tới mọi upstream chỉ vì route đổi từ v1 sang v2:

- Chỉ truyền **access token** đến resource server được phép nhận nó theo issuer, audience và scopes phù hợp.
- Cân nhắc token exchange/service credentials cho đường gọi khác trust boundary.
- Không gửi refresh token/ID token, session cookie tới những backend không cần.
- Dùng TLS/mTLS và hostname verification cho các hops nhạy cảm.
- Không ghi raw Authorization/Cookie vào logs, traces hoặc metrics.
- Khi ứng dụng public Catalog không cần user identity, loại credentials trước outbound nếu policy cho phép.

### 14.4. X-API-Version là header do client gửi

Nó không được dùng làm:

- Principal identity, tenant ID hoặc role.
- Chữ ký/secret chứng minh người gọi là mobile app chính thức.
- Tín hiệu cấp quyền truy cập API admin.
- Nguồn tính rate limit key đáng tin duy nhất.
- URL/hostname động để chọn backend tùy ý.

Ngay cả header do Gateway đặt như `X-Resolved-Api-Version` cũng **chỉ đáng tin nếu backend chỉ nhận nó từ Gateway đã được chứng thực và không có đường bypass trực tiếp**.

## 15. Rate limiting, retry, circuit breaker và version isolation

API version routing có thể kết hợp với những tính năng resilience của Spring Cloud Gateway, nhưng **phiên bản không được biến thành cơ chế phân phối ngẫu nhiên hoặc cách né hạn mức**.

### 15.1. Rate limiting phải tính cả người dùng đổi version

Nếu quota là 100 requests/phút/user trên toàn API Catalog, một client không được vượt quota bằng cách gửi đồng thời:

~~~text
50 req/min -> /api/v1/catalog
50 req/min -> /api/v2/catalog
50 req/min -> /api/catalog, X-API-Version: 1
~~~

Hệ thống phải xác định quota áp ở **operation/principal/tenant** hay **principal + version**. Nếu version là một phần key mà client tự chọn, người dùng có thể khuếch đại quota bằng cách chuyển version. Với rate limiter phân tán, kiểm tra key resolver và store dùng chung giữa Gateway replicas.

### 15.2. Retry không được đổi phiên bản sau lỗi

Một request v1 bị Catalog v1 trả 503 **không nên tự động chuyển tới Catalog v2** chỉ để có response 200: cấu trúc JSON v2 có thể làm client v1 hỏng. Retry, load balancing hoặc circuit breaker fallback phải giữ **đúng API contract**.

| Sự cố | Hành động an toàn theo hợp đồng |
| --- | --- |
| v1 instance A timeout | Retry có giới hạn sang **instance v1 tương thích** nếu method/idempotency cho phép |
| v1 backend 503 | Giữ 503 hoặc fallback v1 đã được thiết kế |
| v2 circuit OPEN | Trả lỗi/fallback v2, **không trả body v1 mạo danh v2** |
| v1 đã sunset | Trả response retirement đã công bố, không âm thầm route sang v2 |
| POST tạo đơn bị reset sau khi backend có thể commit | Không tự retry nếu thiếu idempotency key/deduplication |

### 15.3. Công thức khuếch đại retries nhiều tầng

Nếu client retry tổng cộng 3 attempts, Gateway retry tối đa 2 attempts cho mỗi client call và SDK backend lại retry 2 attempts, một logical operation có thể tạo tối đa:

\[
3 \times 2 \times 2 = 12\ \text{outbound attempts}
\]

Đây là ví dụ cận trên cho các tầng retry tuần tự, chưa tính fan-out/hedging. Cần quan sát **attempt count, status, latency và tổng deadline**; không chỉ nhìn final HTTP 200.

### 15.4. Circuit breaker và fallback theo contract

Mỗi API version có thể có SLO, error classification và fallback behavior riêng. Một breaker v2 mở không nhất thiết yêu cầu v1 breaker mở; nhưng dùng chung dependency, shared pool hoặc database có thể khiến sự cố lan qua cả hai. Không tạo hai tên breaker rồi suy rằng tài nguyên vật lý đã tách biệt. Backend cross-version fallback cần **adapter biến đổi hợp đồng đã được kiểm thử**, không chỉ thay upstream URI.

## 16. API versioning khác canary/blue-green rollout

Hai mô hình dễ nhầm:

~~~mermaid
flowchart TD
    C["Client đã chọn API v1"] --> G["Gateway route v1"]
    G --> W{"Canary trong cùng hợp đồng v1"}
    W -->|"90%"| OLD["Backend build A: trả JSON v1"]
    W -->|"10%"| NEW["Backend build B: vẫn trả JSON v1"]
    V2["Client chọn API v2"] --> G2["Gateway route v2"]
    G2 --> NEW2["Backend hỗ trợ JSON v2"]
~~~

**API versioning** chọn **hợp đồng**. **Canary** chọn một **build/implementation** mà vẫn giữ đúng hợp đồng đã cam kết. Nếu v1 request được cân 10% sang build mới nhưng build đó chỉ biết JSON v2, kết quả là rollout vi phạm compatibility chứ không phải chiến lược version routing hợp lệ.

### Một số chiến lược

| Chiến lược | Mục tiêu | Điều bắt buộc |
| --- | --- | --- |
| Path/header version routes | Chọn contract v1 hoặc v2 theo client | Route predicates không mơ hồ |
| Canary v1 build B | Thử implementation mới nhưng giữ v1 contract | Contract tests và traffic/metrics riêng |
| Blue-green backend v2 | Thay instances v2 theo rollout | Cả blue và green đều đáp ứng v2 contract |
| Shadow/mirror | Đo backend mới mà không dùng response của nó | Không gây side effects hoặc lộ PII |
| Client migration v1→v2 | Người dùng đổi contract theo lộ trình | SDK/docs, observability, deprecation |

Nếu muốn dùng `Weight` route predicate hoặc weighted backends, tính năng và cấu hình cần được kiểm tra theo SCG version; không dùng `Weight` để chọn v1/v2 **khi client đã chỉ rõ version**. Traffic weighting còn chịu cỡ mẫu và thuật toán; 90/10 không bảo đảm đúng 9/1 trong mọi 10 requests.

## 17. Service discovery và môi trường Kubernetes

Các URI trong YAML phần 6 là static:

~~~yaml
catalog:
  v1-base-url: http://127.0.0.1:9001
  v2-base-url: http://127.0.0.1:9002
~~~

Trong Kubernetes, có thể dùng **Service DNS** riêng cho hai contract implementations:

~~~yaml
catalog:
  v1-base-url: http://catalog-v1.apps.svc.cluster.local:8080
  v2-base-url: http://catalog-v2.apps.svc.cluster.local:8080
~~~

Hoặc route trỏ tới SCG service discovery:

~~~yaml
# Trích một RouteDefinition, chỉ khi đã có LoadBalancer/ServiceInstances.
- id: catalog-path-v2
  uri: lb://catalog-v2
  predicates:
    - Path=/api/v2/catalog/**
    - Method=GET
  filters:
    - StripPrefix=3
    - SetRequestHeader=X-Resolved-Api-Version,2
~~~

`lb://catalog-v2` **không tự tương đương Kubernetes DNS**: cần Spring Cloud LoadBalancer và một `ServiceInstance` supplier/discovery integration phù hợp. Mặt khác, nếu route dùng FQDN của Kubernetes Service, HTTP client gọi qua cluster DNS/network routing; có thể không cần client-side `lb://`.

### Nếu hai versions dùng một Service?

Có thể có `catalog-service` duy nhất mà bên trong hỗ trợ v1/v2. Khi đó hai routes có thể trỏ cùng URI, nhưng backend cần đảm bảo đọc **canonical version context** và phân tách hợp đồng. Đó không phải lỗi kiến trúc; nó có thể giúp chia sẻ domain logic và giảm overhead. Rủi ro là một rollout build mới ảnh hưởng cả hai versions, nên cần regression tests cho **cả v1 và v2**.

### TLS, Host và forwarded headers

- Với backend HTTPS, hostname/SNI/CA trust phải đúng; không tắt hostname verification để qua test.
- Không lấy `Host` hoặc `X-Forwarded-Host` do client gửi làm target URI/version backend.
- Ingress có thể rewrite path hoặc normalize forwarded metadata; SCG phải nhận đúng prefix để match.
- Pooled connections đến instances v1/v2 cần được quản lý theo backend/connection lifetime; không suy rằng đổi DNS record lập tức chuyển mọi pooled connection.
- Với cross-namespace K8s Services, Kubernetes RBAC/NetworkPolicy và application authorization là những lớp độc lập.

## 18. Gateway Server Web MVC và Proxy Exchange có áp dụng cùng ý tưởng?

**Có ở mức kiến trúc**, nhưng không dùng nguyên code/configuration của WebFlux:

| Khía cạnh | Server WebFlux | Server Web MVC | Proxy Exchange |
| --- | --- | --- | --- |
| Web runtime | Reactor/WebFlux | Servlet/Spring MVC/WebMvc.fn | MVC hoặc WebFlux controller utility |
| Route declarations | RouteDefinition YAML/Java DSL | WebMvc.fn route definitions/filters | `ProxyExchange<T>` trong controller |
| API version match | `Path`, `Header`, `Method` predicates | Predicates tương ứng mà release hỗ trợ | `@GetMapping` + handler header/path validation |
| Request path/header transform | Gateway WebFlux filters | Gateway Server MVC before/after filters | Controller/ProxyExchange URI, request headers |
| Security | `SecurityWebFilterChain` | Servlet `SecurityFilterChain` | Security của stack controller |
| Backend HTTP client | Reactor Netty trong nhiều cấu hình | HTTP client/request factory của MVC stack | HTTP client tùy Proxy Exchange MVC/WebFlux |

Trong các dòng mới, namespace Gateway Server MVC có thể là `spring.cloud.gateway.server.webmvc.routes`, trong các dòng cũ là `spring.cloud.gateway.mvc.routes`. **Không dùng `org.springframework.cloud.gateway.filter.GlobalFilter` của WebFlux trực tiếp trong Gateway Server MVC**. Thay vì dịch API theo tên, hãy chọn một runtime và xác nhận starter/BOM/predicate/filter signatures bằng integration tests.

Với Proxy Exchange, route version thường được diễn tả bằng `@GetMapping` hoặc handler logic rồi `ProxyExchange.header(...)`/URI mapping; không phải RouteDefinition YAML giống Gateway Server. Thay đổi sang Proxy Exchange chỉ vì muốn if/else version header sẽ tăng mã application cần duy trì, nên cần cân nhắc.

## 19. Deprecation, Sunset và vòng đời một API version

Versioning chỉ có ích lâu dài nếu có **quy trình tiến hóa và nghỉ hưu phiên bản**. Nếu v1 vẫn phải sống mãi vì không có dữ liệu migration, mọi route/backend/filter/security policy sẽ phình ra và làm tăng diện tích rủi ro.

### 19.1. Trạng thái vòng đời

~~~mermaid
flowchart LR
    D["Design + contract tests"] --> P["Preview / limited clients"]
    P --> S["Supported"]
    S --> DE["Deprecated: có lịch chuyển"]
    DE --> SU["Sunset: mốc ngừng hỗ trợ"]
    SU --> R["Retired: 404/410 theo policy"]
~~~

| Trạng thái | Hành động chính | Chỉ số theo dõi |
| --- | --- | --- |
| Preview | Nhóm client được phép, API contract chưa cam kết rộng | Error rate, feedback |
| Supported | Docs/SDK/tests đầy đủ, capacity và auth ổn | Requests/status/latency theo version |
| Deprecated | Công bố v2, hướng dẫn migration, không mở thêm breaking features v1 | Số clients v1 còn hoạt động |
| Sunset pending | Ấn định cutoff và xử lý exception cho đối tác quan trọng | `v1` traffic giảm, clients đã liên hệ |
| Retired | Ngừng route hoặc dùng tombstone handler 410 có chủ đích | Request v1 còn sót, support incidents |

**Deprecation không phải ngay lập tức trả lỗi.** Trong một giai đoạn, v1 tiếp tục hoạt động nhưng được khuyến nghị chuyển. Không gỡ backend v1 chỉ vì metrics tổng có vẻ thấp; phải xem traffic theo đối tác, region, SDK, method và chu kỳ sử dụng theo ngày/tuần/tháng.

### 19.2. Dùng HTTP response headers một cách có hợp đồng

HTTP đã có các cơ chế truyền thông báo ngừng hỗ trợ như **Deprecation** (RFC 9745) và **Sunset** (RFC 8594). Tuy nhiên cú pháp, thời điểm và phần mềm client/CDN hỗ trợ có khác nhau; ứng dụng phải triển khai đúng chuẩn và docs công khai, không tự phát header “deprecated: yes” rồi cho rằng client tự hiểu.

Ví dụ **Sunset** mang HTTP-date có thể dùng trong chính sách đã công bố:

~~~http
Sunset: Fri, 31 Dec 2027 23:59:59 GMT
Link: <https://docs.example.test/migration/catalog-v2>; rel="deprecation"
~~~

Ngày trên chỉ là **minh họa**, không phải thời hạn thật. Cần xác định phiên bản nào nhận header, ngày UTC chính xác và thông tin hỗ trợ. Với `Deprecation`, sử dụng syntax phù hợp chuẩn và version framework đang dùng; không phát một Unix timestamp tùy tiện mà không kiểm chứng.

### 19.3. Thu hồi route v1 an toàn

Một phương án:

1. **Thông báo và đo:** đo `catalog-path-v1`/`catalog-header-v1` qua metrics, phân nhóm khách hàng.
2. **Cập nhật SDK và docs:** v2 phản ánh JSON/schema/errors mới; các clients có test chứng minh.
3. **Canary client migration:** một số clients có chủ đích chuyển sang `X-API-Version: 2` hoặc path v2, không force hàng loạt.
4. **Sunset review:** API owners, Security, SRE và khách hàng xác nhận thời hạn.
5. **Retirement:** có thể giữ handler 410 để chỉ đến docs trong một khoảng ngắn hoặc để không có route → 404, tùy contract.
6. **Rollback:** nếu phát hiện client quan trọng chưa cập nhật, xác định có thể bật lại v1 trong phạm vi nào, có còn dữ liệu/hợp đồng tương thích không.

Đừng giữ một route `catalog-path-v1` rồi đổi URI sang v2 chỉ để giải quyết thiếu backend v1; điều đó tạo **silent breaking change** và làm mất khả năng phát hiện clients chưa migration.

## 20. OpenAPI, SDK và quan sát mức sử dụng theo version

### 20.1. Tài liệu cho path version

Có thể có hai OpenAPI documents độc lập:

~~~text
catalog-v1-openapi.yaml:
  servers: [{url: https://api.example.test/api/v1}]
  /catalog/items/{id} -> price: integer

catalog-v2-openapi.yaml:
  servers: [{url: https://api.example.test/api/v2}]
  /catalog/items/{id} -> price: {amount, currency}
~~~

Đây là **mô hình rút gọn**, không phải một OpenAPI file hoàn chỉnh. Điểm chính là docs/SDK phải thể hiện **hai response schemas khác nhau**, không chỉ thêm `/v2` vào URL mà vẫn mô tả schema v1.

### 20.2. Tài liệu cho header version

Một OpenAPI parameter có thể mô tả yêu cầu client đặt header:

~~~yaml
# Trích trong operation.parameters, không phải một tài liệu đầy đủ.
parameters:
  - name: X-API-Version
    in: header
    required: true
    description: API contract version. Supported values are "1" and "2".
    schema:
      type: string
      enum: ["1", "2"]
~~~

Nếu hai versions có **hai response JSON schemas khác nhau trên cùng path/method**, cần thiết kế OpenAPI để docs và SDK thực sự phân biệt chúng (ví dụ tài liệu/version-specific API definitions hoặc điều kiện do tooling hỗ trợ). Một parameter `enum: ["1","2"]` riêng lẻ **không tự bảo đảm code generator chọn DTO v1/v2**.

### 20.3. Nhận diện client migration bằng telemetry

| Metric / dimension | Tác dụng | Cardinality/Privacy |
| --- | --- | --- |
| **route ID** (`catalog-header-v1`) | Đếm lượt gọi từng version | Hữu hạn |
| **final status** | Phát hiện 400/404/503 khi migration | Hữu hạn |
| **upstream service** | Phân biệt Catalog v1/v2 backends | Hữu hạn theo inventory |
| **client SDK version** từ identity/metadata đã kiểm soát | Xác định clients cần migration | Chỉ đưa taxonomy hữu hạn, không raw user agent vô hạn |
| **business owner/tenant** | Liên hệ khách hàng chưa chuyển | Tránh nhãn metrics lộ PII/high-cardinality; phân tích ở hệ thống có quyền riêng |
| **response schema validation** | Phát hiện v2 trả nhầm shape v1 | Không log raw user payload |
| **outbound attempts** | Phát hiện retry storm ở version cụ thể | Nhãn version/route hữu hạn |

Với Spring Cloud Gateway, `gateway.requests` và các meters Micrometer/Actuator (khi enabled) có thể cung cấp route-level telemetry, **nhưng tên meter/tags/exposure phụ thuộc release**. Phải kiểm tra thực tế trên environment đang chạy, không đoán rằng `gateway.requests` luôn bật.

**Không lưu raw `Authorization`, `Cookie`, query chứa PII hoặc body của user vào logs/traces** chỉ để đo adoption phiên bản. Nếu cần tra phiên bản của một đối tác, dùng hệ thống analytics có kiểm soát truy cập và retention phù hợp thay vì nhét tenant/user ID vào metrics labels.

### 20.4. Phân biệt response provenance

Một request v1 trả HTTP 404 có thể do:

~~~text
Security/cors/filter: bị chặn trước Gateway routing
Gateway: không có route phù hợp
Gateway: có route nhưng backend URI/instance không khả dụng
Backend v1: item 42 thật sự không tồn tại
~~~

Một status giống nhau có thể có ý nghĩa khác. Khi debug, dùng **backend request counter, route ID, trace context, upstream status và final status** để xác định nguồn. Đừng chuyển mọi lỗi versioning thành 404 rồi làm mất dữ liệu migration.

## 21. Backend stub: xác minh backend thật đã nhận phiên bản nào

Để kiểm thử Gateway route, một mock controller không đủ. Ta cần **HTTP backend stub** thực sự lắng nghe trên loopback port động và ghi các request nhận được. Dưới đây là fixture dùng JDK `com.sun.net.httpserver.HttpServer` (Java 17+), được dùng riêng cho lab/CI.

~~~java
import java.io.IOException;
import java.io.OutputStream;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicReference;

import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;

final class CatalogVersionStub implements AutoCloseable {

    private final HttpServer server;
    private final String version;

    final AtomicInteger calls = new AtomicInteger();
    final AtomicReference<String> lastMethod = new AtomicReference<>();
    final AtomicReference<String> lastRawPath = new AtomicReference<>();
    final AtomicReference<String> lastRawQuery = new AtomicReference<>();
    final AtomicReference<String> lastResolved = new AtomicReference<>();
    final AtomicReference<String> lastClientHeader = new AtomicReference<>();

    CatalogVersionStub(String version) throws IOException {
        this.version = version;
        server = HttpServer.create(
                new InetSocketAddress("127.0.0.1", 0), 0);
        server.createContext("/", this::handle);
        server.start();
    }

    String baseUrl() {
        return "http://127.0.0.1:" + server.getAddress().getPort();
    }

    void reset() {
        calls.set(0);
        lastMethod.set(null);
        lastRawPath.set(null);
        lastRawQuery.set(null);
        lastResolved.set(null);
        lastClientHeader.set(null);
    }

    private void handle(HttpExchange exchange) throws IOException {
        calls.incrementAndGet();
        String path = exchange.getRequestURI().getRawPath();
        lastMethod.set(exchange.getRequestMethod());
        lastRawPath.set(path);
        lastRawQuery.set(exchange.getRequestURI().getRawQuery());
        lastResolved.set(exchange.getRequestHeaders()
                .getFirst("X-Resolved-Api-Version"));
        lastClientHeader.set(exchange.getRequestHeaders()
                .getFirst("X-API-Version"));

        int status = path.endsWith("/missing") ? 404
                : path.endsWith("/busy") ? 503 : 200;

        String body;
        if (status == 404) {
            body = "{\"error\":\"NOT_FOUND\",\"version\":\""
                    + version + "\"}";
        } else if (status == 503) {
            body = "{\"error\":\"UPSTREAM_BUSY\",\"version\":\""
                    + version + "\"}";
        } else if ("1".equals(version)) {
            body = "{\"id\":\"42\",\"price\":1000"
                    + ",\"version\":\"1\"}";
        } else {
            body = "{\"id\":\"42\",\"price\":{"
                    + "\"amount\":1000,\"currency\":\"VND\"}"
                    + ",\"version\":\"2\"}";
        }

        byte[] bytes = body.getBytes(StandardCharsets.UTF_8);
        exchange.getResponseHeaders().set(
                "Content-Type", "application/json; charset=UTF-8");
        exchange.getResponseHeaders().set(
                "ETag", "\"catalog-v" + version + "-r1\"");
        exchange.getResponseHeaders().set(
                "Cache-Control", "public, max-age=30");
        exchange.sendResponseHeaders(status, bytes.length);
        try (OutputStream stream = exchange.getResponseBody()) {
            stream.write(bytes);
        }
    }

    @Override
    public void close() {
        server.stop(0);
    }
}
~~~

**Đây là test fixture**, không phải HTTP server production. Nó chỉ nhận GET trên test path theo contract đơn giản; các mã lỗi được tạo có chủ đích. Đừng để stub có quyền truy cập secrets hoặc kết nối production backend. Với Java modules, `HttpServer` nằm trong module `jdk.httpserver`.

### Những gì backend journal phải chứng minh

| Request đến Gateway | Stub được gọi | `lastRawPath` | `lastResolved` | JSON schema |
| --- | --- | --- | --- | --- |
| Path v1 | v1 | `/items/42` | `1` | `price` là số |
| Path v2 | v2 | `/items/42` | `2` | `price` là object |
| Header v1 | v1 | `/items/42` | `1` | `price` là số |
| Header v2 | v2 | `/items/42` | `2` | `price` là object |
| Missing/ambiguous header | **Không stub nào** | Không có | Không có | Không có outbound call |

**Lưu ý:** `lastRawPath` và `lastResolved` là trạng thái request cuối cùng, đủ cho test tuần tự đơn giản. Với retries/concurrent requests, dùng **request journal thread-safe gắn correlation ID**, không suy luận mọi attempts chỉ từ một `AtomicReference`. Có thể thay fixture bằng WireMock/MockWebServer để test delay, reset, headers và multi-attempt assertions kỹ hơn.

## 22. HTTP integration test: một Gateway, hai phiên bản, hai cách chọn route

Kiểm thử unit riêng cho predicate/filter có ích, nhưng **không thay** bài test đi qua HTTP socket thật. Ví dụ dưới đây dùng **Spring Boot `RANDOM_PORT`** cho Gateway Server WebFlux, JDK `HttpClient` gửi inbound request và hai `CatalogVersionStub` riêng cho backend v1/v2.

### 22.1. Test app setup

Đặt YAML bốn routes phần 6 trong test profile `application-versioning-test.yml` hoặc một test configuration tương đương, sao cho các property `catalog.v1-base-url` và `catalog.v2-base-url` có thể được ghi đè bằng port động của backend stubs.

~~~java
import java.io.IOException;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;

import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.parallel.Execution;
import org.junit.jupiter.api.parallel.ExecutionMode;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@ActiveProfiles("versioning-test")
@Execution(ExecutionMode.SAME_THREAD)
class VersionedCatalogGatewayIntegrationTest {

    static final CatalogVersionStub V1 = startStub("1");
    static final CatalogVersionStub V2 = startStub("2");

    @DynamicPropertySource
    static void targetUris(DynamicPropertyRegistry registry) {
        registry.add("catalog.v1-base-url", V1::baseUrl);
        registry.add("catalog.v2-base-url", V2::baseUrl);
    }

    @LocalServerPort
    int gatewayPort;

    final HttpClient client = HttpClient.newBuilder()
            .connectTimeout(Duration.ofSeconds(2))
            .followRedirects(HttpClient.Redirect.NEVER)
            .build();

    private static CatalogVersionStub startStub(String version) {
        try {
            return new CatalogVersionStub(version);
        } catch (IOException error) {
            throw new ExceptionInInitializerError(error);
        }
    }

    @BeforeEach
    void reset() {
        V1.reset();
        V2.reset();
    }

    @AfterAll
    static void stopStubs() {
        V1.close();
        V2.close();
    }

    private HttpResponse<String> get(
            String path,
            String... versionHeaderValues
    ) throws Exception {
        HttpRequest.Builder builder = HttpRequest.newBuilder(
                        URI.create("http://127.0.0.1:"
                                + gatewayPort + path))
                .timeout(Duration.ofSeconds(5))
                .GET();

        for (String value : versionHeaderValues) {
            builder.header("X-API-Version", value);
        }
        return client.send(
                builder.build(), HttpResponse.BodyHandlers.ofString());
    }

    @Test
    void pathV1SelectsV1AndPreservesQuery() throws Exception {
        HttpResponse<String> response =
                get("/api/v1/catalog/items/42?lang=vi");

        assertEquals(200, response.statusCode());
        assertTrue(response.body().contains("\"price\":1000"));
        assertEquals("1", response.headers()
                .firstValue("X-Resolved-Api-Version").orElse(""));
        assertEquals(1, V1.calls.get());
        assertEquals(0, V2.calls.get());
        assertEquals("GET", V1.lastMethod.get());
        assertEquals("/items/42", V1.lastRawPath.get());
        assertEquals("lang=vi", V1.lastRawQuery.get());
        assertEquals("1", V1.lastResolved.get());
        assertNull(V1.lastClientHeader.get());
    }

    @Test
    void pathV2KeepsDifferentContract() throws Exception {
        HttpResponse<String> response =
                get("/api/v2/catalog/items/42");

        assertEquals(200, response.statusCode());
        assertTrue(response.body()
                .contains("\"price\":{\"amount\":1000"));
        assertEquals(0, V1.calls.get());
        assertEquals(1, V2.calls.get());
        assertEquals("2", V2.lastResolved.get());
    }

    @Test
    void headerV2SelectsV2AndReturnsVary() throws Exception {
        HttpResponse<String> response =
                get("/api/catalog/items/42", "2");

        assertEquals(200, response.statusCode());
        assertEquals(0, V1.calls.get());
        assertEquals(1, V2.calls.get());
        assertEquals("/items/42", V2.lastRawPath.get());
        assertEquals("2", V2.lastResolved.get());
        assertNull(V2.lastClientHeader.get());
        assertTrue(response.headers().allValues("Vary")
                .stream().anyMatch(
                        field -> field.toLowerCase()
                                .contains("x-api-version")));
        assertEquals("\"catalog-v2-r1\"", response.headers()
                .firstValue("ETag").orElse(""));
    }

    @Test
    void missingHeaderDoesNotSilentlyChooseLatest() throws Exception {
        HttpResponse<String> response =
                get("/api/catalog/items/42");

        assertEquals(400, response.statusCode());
        assertEquals(0, V1.calls.get());
        assertEquals(0, V2.calls.get());
    }

    @Test
    void repeatedHeaderOrConflictIsRejected() throws Exception {
        assertEquals(400,
                get("/api/catalog/items/42", "1", "2")
                        .statusCode());
        assertEquals(400,
                get("/api/v1/catalog/items/42", "2")
                        .statusCode());
        assertEquals(0, V1.calls.get());
        assertEquals(0, V2.calls.get());
    }

    @Test
    void backend404Remains404WithoutCrossVersionFallback()
            throws Exception {
        HttpResponse<String> response =
                get("/api/catalog/items/missing", "1");

        assertEquals(404, response.statusCode());
        assertTrue(response.body().contains("NOT_FOUND"));
        assertEquals(1, V1.calls.get());
        assertEquals(0, V2.calls.get());
    }

    @Test
    void backend503IsNotAutomaticallyHidden() throws Exception {
        HttpResponse<String> response =
                get("/api/catalog/items/busy", "2");

        assertEquals(503, response.statusCode());
        assertEquals(0, V1.calls.get());
        assertEquals(1, V2.calls.get());
    }
}
~~~

**Đây là mã test minh họa, chưa được thực thi trong bài.** Cần dự án thật có Gateway Server WebFlux starter/BOM tương thích, Spring Boot Test + JUnit 5, YAML bốn routes đã nạp và `ApiVersionValidationWebFilter` + `ApiVersionVaryGlobalFilter` trong component scan. Không cấu hình security test chặn Catalog requests vô tình; security integration tests cần được viết **riêng** và phải chứng minh 401/403 không có backend attempt.

**Giới hạn cấu hình và lifecycle:**

- `CatalogVersionStub` sử dụng port `0` cho hai backends; `@DynamicPropertySource` inject URI trước khi context dựng routes.
- `@Execution(SAME_THREAD)` giới hạn test methods trong class này không chạy song song; với nhiều test classes/context caching, còn cần fixture ownership phù hợp.
- HTTP client dùng `Redirect.NEVER` để không che HTTP 3xx nếu backend/route có redirect.
- Response 404/503 là **backend-generated HTTP responses**, không phải DNS/TCP/TLS exceptions; test riêng transport failures.
- Hành vi exact status/body/headers còn phụ thuộc filter chain và Spring Cloud Gateway version; nếu thay route filters hoặc security policies, chỉnh test theo **contract**, không chỉ để test xanh.
- Test chưa có load, CORS OPTIONS, signed JWT, TLS, large body hoặc retry injection. Chúng là các lớp khác, không được suy ra từ bảy phương thức test ở trên.

### 22.2. Kiểm tra header do client cố tình giả mạo

Ngoài `X-API-Version`, client có thể gửi `X-Resolved-Api-Version: attacker`. Filter `SetRequestHeader` ở Gateway phải **thay** giá trị này trước backend. Thêm một test:

~~~java
@Test
void clientCannotOverrideCanonicalVersionHeader() throws Exception {
    HttpRequest request = HttpRequest.newBuilder(
                    URI.create("http://127.0.0.1:"
                            + gatewayPort
                            + "/api/catalog/items/42"))
            .header("X-API-Version", "1")
            .header("X-Resolved-Api-Version", "attacker")
            .GET()
            .build();

    HttpResponse<String> response = client.send(
            request, HttpResponse.BodyHandlers.ofString());

    assertEquals(200, response.statusCode());
    assertEquals("1", V1.lastResolved.get());
}
~~~

Đoạn này là **một phương thức đặt bên trong class `VersionedCatalogGatewayIntegrationTest`**, không phải file độc lập. Nó chứng minh version header được normalize tại đúng HTTP hop; không chứng minh backend đã xác thực danh tính Gateway bằng mTLS/token.

### 22.3. Test ETag và response schema thật

Với cùng item `42`:

1. Gọi header v1, ghi `ETag` và JSON v1.
2. Gọi header v2, ghi `ETag` và JSON v2.
3. Kiểm tra `Vary: X-API-Version` ở cả hai responses.
4. Không dùng response v1 từ một cache giả khi client yêu cầu v2.
5. Thử `If-None-Match` của v1 khi yêu cầu v2; không được trả 304 sai representation.
6. Nếu contract yêu cầu CORS, kiểm tra OPTIONS preflight và actual GET với `X-API-Version`.

Backend stub ở phần 21 chưa triển khai conditional GET/304, nên **các tests 304/cache revalidation cần fixture nâng cao hơn**. Đừng đánh dấu chúng PASS khi chưa có backend/cache có hành vi đó.

## 23. Ma trận kiểm thử đầy đủ trước khi triển khai API version routing

| ID | Kịch bản | Công cụ thích hợp | Bằng chứng cần có |
| --- | --- | --- | --- |
| V01 | Path v1 tới backend v1 | HTTP client + stub v1 | V1 HITS=1, v2 HITS=0 |
| V02 | Path v2 tới backend v2 | HTTP client + stub v2 | V2 HITS=1, v1 HITS=0 |
| V03 | Header `1` tới backend v1 | HTTP client + stub | Backend thấy canonical version 1 |
| V04 | Header `2` tới backend v2 | HTTP client + stub | Backend thấy canonical version 2 |
| V05 | Path v1 với header `2` | HTTP client | 400, không gọi backend |
| V06 | Path v2 với header `1` | HTTP client | 400, không gọi backend |
| V07 | Header version thiếu | HTTP client | 400, không có fallback bí mật |
| V08 | Header version `3` | HTTP client | Lỗi đúng contract, không route v1/v2 |
| V09 | Hai header values `1`/`2` | HTTP client | 400, không route mơ hồ |
| V10 | Một header `1,2` | HTTP client | 400 |
| V11 | Client gửi `X-Resolved-Api-Version: attacker` | Stub journal | Gateway thay bằng 1/2 |
| V12 | Backend nhận request path | Stub raw-path journal | `/items/42`, không double strip |
| V13 | Query `lang=vi` | Stub raw-query journal | Không mất query |
| V14 | Query `tag=a%2Bb` | HTTP client + stub | Không biến thành space ngoài contract |
| V15 | Encoded slash/double slash | HTTP client thật | Hành vi normalize/reject theo spec/container |
| V16 | Header name khác chữ hoa/thường | HTTP client | `x-api-version` được hiểu đúng như `X-API-Version` |
| V17 | GET-only route nhận POST | HTTP client | Không có outbound attempt |
| V18 | Unknown path `/api/v3/...` | HTTP client | 404 hoặc status explicit theo policy |
| V19 | Catch-all route cùng prefix | Route test + stub | Không nuốt version thiếu/sai |
| V20 | Header v1/v2 response JSON | HTTP client + JSON schema | V1/v2 schemas khác đúng contract |
| V21 | Header v1/v2 cache isolation | CDN/cache integration | `Vary` và cache key đúng |
| V22 | ETag và If-None-Match | HTTP client/cache fixture | Không trả 304 sai version |
| V23 | Backend 404 v1 | Stub journal | Client 404 từ đúng backend |
| V24 | Backend 503 v2 | Stub journal | Không fallback sang v1 |
| V25 | Backend connect timeout | Fault injection | 502/503/504 theo contract, finite deadline |
| V26 | Retry v1 instance A→B | Stub với counter | Mọi attempts vẫn v1 và có giới hạn |
| V27 | Circuit breaker v2 OPEN | Fault injection | Backend không bị gọi, fallback v2 |
| V28 | Rate limit qua cả path/header aliases | Security/rate limiter test | Không nhân quota bằng cách đổi alias |
| V29 | Anonymous gọi versioned private API | Spring Security test | Bị từ chối trước backend |
| V30 | JWT thiếu scope/sai audience | Signed test token | Bị từ chối không gọi backend |
| V31 | Public Catalog và credential forwarding | Stub header-name journal | Không leak token/cookie trái policy |
| V32 | CORS preflight OPTIONS | Browser/HTTP test | `Access-Control-Allow-Headers` và policy đúng |
| V33 | Proxy strip `X-API-Version` | Ingress/SCG e2e | Lỗi rõ, không mặc định sai version |
| V34 | Deployment v2 build rollback | Canary integration | v1/v2 API contracts vẫn ổn |
| V35 | Deprecation/Sunset v1 | HTTP tests | Chỉ đúng routes và mốc đã công bố |
| V36 | Multi-replica route config drift | E2E per Pod | Không chọn version khác nhau giữa replicas |

### Cách ưu tiên test

- **Mỗi commit:** V01–V13, V17–V20, V23–V24, V29 (với context phù hợp).
- **Trước release/migration:** V14–V16, V21–V22, V25–V28, V30–V33, V35.
- **Canary/chaos được phê duyệt:** V34, V36 và load/connection failure tests.

Không cần chạy mọi test dưới dạng destructive e2e trong production. Các fault scenarios (timeout, circuit OPEN, rate limiter store outage, backend swap) nên ở **sandbox/test namespace** với dữ liệu giả, giới hạn số request và rollback rõ ràng.

## 24. Chẩn đoán lỗi định tuyến sai phiên bản

Khi nhận khiếu nại “gọi v1 nhưng nhận JSON v2”, hãy quan sát đường đi thật thay vì sửa `order` hoặc đổi URI backend ngay.

| Triệu chứng | Nguyên nhân có thể | Bằng chứng/cách xử lý |
| --- | --- | --- |
| `/api/v1/...` trả schema v2 | Route URI trỏ nhầm service, backend build vi phạm v1 contract | Route ID, outbound target và JSON schema test |
| Header `1` đôi khi vào v2 | Client/proxy gửi nhiều header values, route predicate overlap | Request header count, validator 400, không chỉ regex |
| Header thiếu nhưng vẫn vào v2 | Catch-all/default route chọn latest | Bỏ catch-all hoặc công bố/đóng băng default |
| Header đúng nhưng Gateway trả 404 | Namespace config sai, Header predicate không match, Method sai | Actuator route definitions đã được bảo vệ; test route ID |
| Path v1 trả 404 ở backend | `StripPrefix` sai hoặc double rewrite ở ingress | Backend raw path/HITS, kiểm tra cả hai layers |
| V1 trả 404 tại Gateway, backend HITS=0 | Không match route/method/path hoặc bị filter khác chặn | Spring WebFlux route predicates/security status |
| `/api/v3` trả v2 | Generic route hoặc fallback không phù hợp | Loại path catch-all hoặc thêm explicit unsupported policy |
| POST vào route GET nhưng backend vẫn được gọi | Route khác/catch-all match POST, security rules thiếu | Route ID và backend method journal |
| Cùng URL, client v2 nhận cache JSON v1 | `Vary` thiếu, cache key không tính version | CDN cache test, response headers, ETag distinct |
| `Vary: Accept-Encoding` bị mất | `SetResponseHeader=Vary` ghi đè toàn bộ | Merge Vary và test compression/cache |
| 304 trả sai schema | Dùng chung ETag giữa v1/v2 | Revalidation test theo exact version |
| Browser báo CORS error, curl vẫn 200 | Preflight OPTIONS không được xử lý hoặc X-API-Version không được allow | Browser preflight headers, Security/CORS policy |
| Client gửi header nhưng backend không thấy | Gateway cố ý RemoveRequestHeader hoặc ingress strip | Kiểm tra canonical X-Resolved-Api-Version ở backend |
| Backend thấy `X-API-Version` lạ | Header stripping chưa chạy/route match sai | Backend journal, filter order, version config |
| Client spoof `X-Resolved-Api-Version` được backend tin | Dùng AddRequestHeader hoặc backend reachable trực tiếp | SetRequestHeader + network identity/auth |
| V2 endpoint bypass JWT requirement | Security matcher chỉ bao phủ v1 | Test anonymous/wrong scope trên **mọi** version |
| Rate limiter quota tăng khi dùng cả hai aliases | Key resolver tính raw path/version do client chọn | Stable principal/operation budget, shared store |
| Retry v1 sang v2 rồi trả 200 | Fallback/LoadBalancer trộn service contract | Version-bound upstream sets và adapter rõ |
| v1 outage nhưng dashboard chỉ thấy 200 | Fallback che upstream failure | Upstream outcome và final status tách riêng |
| Một Gateway replica trả khác | Route config/BOM/filter versions không đồng bộ | Per-replica config revision và smoke tests |
| Header regex không match đúng | Chữ hoa thường của **value**, whitespace, pattern, q values | Test exact raw values và regex contract |
| Encoded plus/slash đổi path | Ingress/URI decoder/RewritePath normalize sai | Real HTTP raw query/path journal |
| v1 có header Sunset nhưng v2 cũng có | Response filter/global policy gắn quá rộng | Route ID scope và response tests |
| Backend 503 chỉ trên header version | URI riêng của header route sai, thiếu endpoints | Backend target/ServiceInstance và exception type |
| Route có nhưng outbound connect/TLS fail | DNS/port/cert/truststore hoặc pool | Phân biệt routing success với transport failures |

### Runbook theo một request

1. **Ghi nhận contract:** Client gọi path version hay header version? Method, URL template và expected version nào?
2. **Xác minh inbound boundary:** Ingress có sửa path, Host, `X-API-Version` hoặc chuyển HTTP method không?
3. **Xác minh validation:** Request có đúng một header không? Path/header có mâu thuẫn không? Security có chặn trước khi route được chọn không?
4. **Xác minh route selection:** Route ID nào match, giá trị `order` và predicates là gì?
5. **Xác minh filter chain:** `StripPrefix` và `SetRequestHeader` đã tạo đúng upstream path/header chưa?
6. **Xác minh upstream:** Backend v1/v2 nào được chọn? ServiceInstance, DNS/TCP/TLS và HTTP client pool có lỗi không?
7. **Xác minh response:** Backend status/schema/ETag là gì? Gateway có rewrite response headers/body không?
8. **Xác minh cache/CDN:** Có `Vary`, Cache-Control, ETag phân biệt version không? CDN có honor custom header?
9. **Xác minh retries/fallback:** Một client request phát bao nhiêu outbound attempts, có lần nào đổi contract không?
10. **Tái hiện trong lab:** Dùng stubs v1/v2 và test profile, không dùng production token hoặc thay đổi trực tiếp các route đang phục vụ traffic thật.

Không bật toàn bộ Reactor Netty wiretap hoặc HTTP header dump để điều tra versioning nếu request chứa JWT, Cookie hoặc PII. Dùng **route IDs, số outbound attempts, backend stub có dữ liệu giả và tracing với metadata hữu hạn**.

### Một vài lệnh curl kiểm tra contract ở môi trường test

~~~bash
# Giả sử Gateway test chạy trên cổng 8080, KHÔNG phải production.
GATEWAY_URL='http://127.0.0.1:8080'

# Chọn v1 bằng path; response kỳ vọng price dạng số.
curl --silent --show-error -i \
  "$GATEWAY_URL/api/v1/catalog/items/42?lang=vi"

# Chọn v2 bằng path; response kỳ vọng price là object.
curl --silent --show-error -i \
  "$GATEWAY_URL/api/v2/catalog/items/42?lang=vi"

# Chọn v1 bằng header.
curl --silent --show-error -i \
  -H 'X-API-Version: 1' \
  "$GATEWAY_URL/api/catalog/items/42"

# Chọn v2 bằng header; kiểm tra Vary và ETag.
curl --silent --show-error -i \
  -H 'X-API-Version: 2' \
  "$GATEWAY_URL/api/catalog/items/42"

# Không có version header: lab policy trả 400.
curl --silent --show-error -i \
  "$GATEWAY_URL/api/catalog/items/42"

# Mâu thuẫn path v1 / header v2: lab policy trả 400.
curl --silent --show-error -i \
  -H 'X-API-Version: 2' \
  "$GATEWAY_URL/api/v1/catalog/items/42"

# Hai giá trị phiên bản: lab policy trả 400.
curl --silent --show-error -i \
  -H 'X-API-Version: 1' -H 'X-API-Version: 2' \
  "$GATEWAY_URL/api/catalog/items/42"
~~~

Đây là **các lệnh cần chạy trong lab**, không phải kết quả đã chạy. Nếu bạn thực hiện với route có Spring Security, cần dùng identity/token test hợp lệ hoặc cách test authentication được phê duyệt; một HTTP 401/403 có thể xuất hiện trước validator. Không đưa token thật vào shell history; tránh chạy lệnh verbose có dump credentials.

### CORS preflight riêng cho header version

~~~bash
curl --silent --show-error -i -X OPTIONS \
  -H 'Origin: https://frontend.example.test' \
  -H 'Access-Control-Request-Method: GET' \
  -H 'Access-Control-Request-Headers: x-api-version' \
  "$GATEWAY_URL/api/catalog/items/42"
~~~

Nếu frontend cross-origin được phép, response preflight cần phù hợp CORS policy của origin đó. Header `X-API-Version` có thể cần nằm trong danh sách `Access-Control-Allow-Headers`. **Một CORS preflight thành công không cấp quyền đọc dữ liệu**, và wildcard origin kết hợp credentials phải được thiết kế đúng semantics; không mở mọi origin chỉ để test qua.

## 25. Bài thực hành tổng hợp: từ route YAML đến migration

**Bối cảnh:** Catalog v1 vẫn phục vụ ứng dụng mobile cũ; Catalog v2 trả trường `price` có cấu trúc mới. Nhóm xây một Spring Cloud Gateway Server WebFlux đứng trước hai backends và hỗ trợ đồng thời **path-based** lẫn **header-based** API versioning trong giai đoạn migration.

### Phần A — Chốt kiến trúc và hợp đồng

1. Ghi lại **Spring Boot, Spring Cloud BOM, Gateway Server WebFlux và Java versions** đang dùng.
2. Khóa contract v1/v2 bằng hai JSON schemas hoặc DTO tests độc lập, nhất là trường `price`.
3. Vẽ đường đi client → ingress (nếu có) → SCG → Catalog v1/v2.
4. Chọn rule: path `/api/v1|v2/catalog/**` không bắt header; nếu có header thì phải cùng version.
5. Chọn rule: header path `/api/catalog/**` bắt **đúng một** `X-API-Version: 1` hoặc `2`.
6. Chọn policy: vắng/sai/trùng/xung đột header trả 400; unknown `/api/v3/...` không có route nên 404.
7. Chỉ định owner của rewrite, cache Vary, auth và version deprecation headers.

### Phần B — Cấu hình Gateway

1. Dùng bốn routes ở phần 6, thay `catalog.v1-base-url` và `catalog.v2-base-url` bằng test stub endpoints.
2. Kiểm tra `Path`, `Method` và `Header` chính xác, header values được neo regex.
3. Test `StripPrefix=3` cho path scheme và `StripPrefix=2` cho header scheme.
4. Loại raw `X-API-Version` trước backend và thay `X-Resolved-Api-Version` do Gateway sở hữu.
5. Dùng `SetResponseHeader` cho header thông tin phiên bản đã chọn.
6. Thêm `ApiVersionValidationWebFilter` để trả 400 cho các input conflict/malformed.
7. Thêm `ApiVersionVaryGlobalFilter` cho header scheme, nhưng không phá `Vary` vốn đã có từ backend.
8. Đảm bảo API auth, CORS OPTIONS và health/management routes không bị vô tình chặn bởi validator.

### Phần C — Kiểm thử qua HTTP

1. Chạy hai `CatalogVersionStub` v1/v2 bằng cổng ngẫu nhiên.
2. Gọi cả bốn request forms, kiểm tra **status, body schema, response version header**.
3. Tại backend, assert **request count, raw path/query, X-Resolved-Api-Version**.
4. Gửi request với hai version header values và path/header conflict: 400, backend HITS=0.
5. Kiểm tra query `lang=vi&tag=a%2Bb` qua cổng HTTP thực.
6. Cho stub v1 trả 404, v2 trả 503; client nhận đúng status, không chuyển sang phiên bản khác.
7. Gửi `X-Resolved-Api-Version: attacker`; backend phải nhận canonical version đúng.
8. Bổ sung test ETag/Vary/cache và browser preflight; fixture cơ bản chưa kiểm tra đầy đủ điều kiện 304.

### Phần D — Bảo mật và vận hành

1. Bật Spring Security trên API private cho **cả v1 và v2**, kiểm tra anonymous và wrong-scope responses.
2. Dùng signed test JWT để kiểm tra issuer/audience/signature, không chỉ `.with(jwt())` của mock authorization tests.
3. Xác minh backend Orders vẫn kiểm tra quyền sở hữu tài nguyên; version header không cấp quyền.
4. Kiểm tra Service DNS hoặc `lb://` discovery, readiness và no-instance behavior theo topology thật.
5. Đo route ID, upstream status, final status và outbound attempts; không log raw tokens/queries chứa PII.
6. Áp rate limit key/quotas để hai version aliases không vô tình nhân quota.
7. Thử canary một build v1 mới nhưng vẫn giữ schema v1; **không** dùng canary để trả v2 JSON cho v1 client.

### Phần E — Giả lập migration v1→v2

1. Tạo client SDK test v1 chỉ hiểu `price: integer`.
2. Tạo client SDK test v2 chỉ hiểu `price.amount` và `price.currency`.
3. Đo traffic v1/v2 theo route IDs, không dựa vào parsing raw user ID.
4. Công bố v1 deprecated ở docs và response metadata theo policy; giữ v1 chạy trong giai đoạn chuyển.
5. Nâng client v1 test lên v2 và chứng minh JSON/schema/handling đúng.
6. Trong sandbox, ngừng v1 theo mốc Sunset giả định: trả 410 bằng tombstone handler hoặc không có route → 404 theo hợp đồng.
7. Thử rollback v1 sau migration nếu dữ liệu/backend còn hỗ trợ, không đổi route v1 sang JSON v2 một cách im lặng.

### Phiếu nghiệm thu

| Hạng mục | Bằng chứng phải nộp |
| --- | --- |
| Architecture | Sơ đồ routes v1/v2, hai version schemes và security boundary |
| Routing | Hai Paths, hai Header predicates, route IDs và backend URIs |
| Request transform | Stub chứng minh `StripPrefix` và canonical request header |
| Response contract | JSON v1/v2 khác nhau, status và response version header |
| Cache safety | `Vary: X-API-Version`, ETag đúng representation, không cache leak |
| Version validation | Missing/unsupported/duplicate/conflict tests |
| Security | Anonymous/wrong-scope, token audience/ownership, no credential leak |
| Resilience | Retry/circuit không tự đổi version, upstream attempts giới hạn |
| Observability | Route ID/version counters, lỗi có provenance |
| Migration | Docs/SDK v1→v2, Sunset policy và rollback plan |

**Tiêu chí đạt:** Người học chứng minh bằng HTTP và backend journal rằng một request **chọn đúng hợp đồng API, đúng backend, đúng path/header, đúng response schema**, đồng thời version lỗi không bị âm thầm route sang “latest” và cache/authorization không bị bypass.

## 26. Những phản mẫu cần tránh và checklist trước merge

| Phản mẫu | Hậu quả | Cách thay thế |
| --- | --- | --- |
| Dùng `Path=/api/{version}/...` rồi route chung tới v2 mà không validate | Unknown v3 hoặc v1 bị đưa đến hợp đồng sai | Hai routes explicit hoặc validator có bảng ánh xạ rõ |
| Dùng `Header=X-API-Version, 1` với regex mơ hồ | Có thể match dữ liệu không chủ đích tùy pattern | `^1$`, `^2$` và reject duplicates |
| Header route thiếu version tự về latest | Silent breaking change | Default cố định đã công bố hoặc 400 |
| Hai header values v1/v2 vẫn cho qua | Route match mơ hồ | WebFilter reject size khác 1 |
| Path v1 + header v2 cho phép đi tiếp | Backend nhận thông tin bất nhất | 400 hoặc precedence contract có tests |
| Dùng `AddRequestHeader` cho canonical version | Client spoof có thể tạo nhiều giá trị | `SetRequestHeader` overwrite |
| Copy header version như principal | Authorization bypass | Spring Security và backend resource authorization |
| Quên bảo vệ endpoint v2 trong security matcher | V2 bypass quyền | Test security cho mọi version/method |
| Cấu hình `StripPrefix=3` cho cả hai schemes | Header path mất nhầm `items` segment | Path=3, Header=2 theo ví dụ |
| Ingress và SCG đều strip /api | Route không match hoặc đi backend sai | Chỉ định một owner rewrite |
| Dùng dynamic target từ header client | SSRF, token egress | Static config/approved service discovery |
| Header v2 cùng URL nhưng thiếu Vary | Shared cache trả nhầm JSON v1 | `Vary` và cache key policy |
| Ghi đè `Vary` khi thêm version | Hỏng compression/CORS cache semantics | Merge field tokens, kiểm thử |
| Dùng cùng strong ETag cho body v1/v2 khác nhau | 304/cache sai | Validator theo representation |
| Retry v1 sang v2 khi v1 lỗi | Trả sai contract | Fallback cùng version hoặc explicit adapter |
| Canary v1 request sang build chỉ trả v2 | Hỏng client cũ | Canary chỉ trong cùng API contract |
| Rate limit key = raw version header | Client dễ đổi header để tăng quota | Key theo identity/operation policy |
| Actuator/Gateway route admin public | Người lạ xem/sửa route | Management security/network isolation |
| Log raw Authorization và URL query | Rò secrets/PII | Metadata allowlist, bounded telemetry |
| Chỉ assert HTTP 200 | Không biết backend/route version nào xử lý | Backend journal + response schema |
| Chỉ dùng MockMvc/WebTestClient mock | Không chứng minh outbound TCP/HTTP | Integration test RANDOM_PORT + stub |
| Thay WebFlux GlobalFilter vào Gateway MVC | Sai runtime/filter chain | Sử dụng đúng MVC APIs và starter |
| Xóa v1 ngay khi v2 deploy | Clients cũ hỏng hàng loạt | Deprecation, telemetry, migration, Sunset |

### Checklist kỹ thuật

~~~text
[ ] Version là API contract, không nhầm với build/canary.
[ ] Chọn path hoặc header scheme, hoặc có quy tắc kết hợp rõ ràng.
[ ] Route predicates Path/Method/Header match chính xác, không overlap.
[ ] Header version regex exact và duplicate/malformed handling được test.
[ ] Unknown/missing/conflicting versions có HTTP status theo contract.
[ ] StripPrefix/RewritePath giữ raw URI/query và xử lý encoded path đúng.
[ ] SetRequestHeader thay header canonical từ client, không dùng Add tùy tiện.
[ ] Upstream URI/service IDs thuộc allowlist, không do client điều khiển.
[ ] Security matcher bảo vệ đầy đủ v1/v2, methods và path aliases.
[ ] Backend kiểm tra identity/tenant/resource ownership độc lập.
[ ] Token/Cookie chỉ forward khi audience/permission/trust boundary đúng.
[ ] Header version có Vary/cache key chính xác, ETag theo representation.
[ ] CORS preflight OPTIONS có policy riêng, không bị Header predicate GET chặn.
[ ] Rate limiting/retries/circuit breakers không nhân quota hoặc đổi contract.
[ ] Backend stubs kiểm chứng path/method/headers/outbound attempts.
[ ] HTTP tests kiểm chứng status, response schema, 4xx/5xx và cache safety.
[ ] Metrics theo route ID/version hữu hạn, logs/traces không chứa secrets.
[ ] Có rollout/canary/rollback, deprecation và Sunset plan cho v1.
[ ] BOM/starter/property namespace chính xác với Gateway runtime thật.
~~~

## 27. Tổng kết

- **Định tuyến theo phiên bản API** chọn một **hợp đồng request/response** cho client, không phải tự động chọn build mới nhất hay một canary. Phân biệt API v1/v2 với deployment revision và database schema.
- Với **path versioning**, các tuyến `/api/v1/catalog/**` và `/api/v2/catalog/**` dùng `Path` và `Method` predicates. Ví dụ của bài dùng `StripPrefix=3` để backend nhận `/items/42`.
- Với **header versioning**, một URL `/api/catalog/**` kết hợp `Header=X-API-Version, ^1$` hoặc `^2$`. Ví dụ dùng `StripPrefix=2`; phải có **một** giá trị header rõ ràng, không để multiple values làm route chọn mơ hồ.
- **Route predicate chỉ match**, không tự validate request và không tự chọn status 400. Một `WebFilter` hoặc validation layer riêng có thể từ chối missing/malformed/conflicting versions, còn không match route thường dẫn đến 404 nếu không có route khác.
- **Chuẩn hóa upstream metadata:** dùng `RemoveRequestHeader` và `SetRequestHeader` để backend nhận `X-Resolved-Api-Version` do Gateway xác định; `SetResponseHeader` thông báo version cho client. Đây **không phải cơ chế authentication**.
- **Header-based versioning cần cache isolation.** Cùng URI có hai JSON representations nên phải thiết kế `Vary: X-API-Version`, ETag/Content-Type/Cache-Control và chính sách CDN đúng; không ghi đè mất những giá trị Vary khác.
- **Security bảo vệ mọi version và alias:** Spring Security/JWT, backend tenant/resource authorization, token audience, rate limiting và trusted proxy policy phải bao phủ cả path lẫn header routes. Không nhận raw header client làm principal/role/backend URI.
- **Resilience giữ nguyên contract:** Retry/circuit breaker/load balancing cho v1 phải tới backend còn phục vụ v1; không tự fallback sang v2 khi lỗi. Canary build mới trong một route không được âm thầm đổi JSON schema của route đó.
- **HTTP integration tests có hai phía:** Client nhận đúng status/schema/headers; backend stub chứng minh đúng route URI, raw path/query, canonical header và số outbound attempts. Test cả 400, 404, 503, duplicate headers, CORS, cache và security.
- **Vòng đời phiên bản có kế hoạch:** duy trì docs/SDK, theo dõi adoption từng route ID, thông báo deprecation/Sunset, sunset v1 theo cam kết và có rollback strategy. Không để `latest` thay đổi theo deployment khi client chưa chọn version.

Tóm lại, một hệ thống **SPRING_CLOUD_GATEWAY** version-aware tốt không chỉ “nhìn path hoặc header để chọn URL”. Nó phải **chọn đúng hợp đồng, giữ nguyên semantics của HTTP, bảo vệ mọi lối truy cập, không làm cache hoặc retry trả nhầm phiên bản, và cung cấp đủ telemetry/tests để chuyển đổi client an toàn**.

### Tài liệu tham khảo và hướng đối chiếu theo phiên bản

- **Spring Cloud Gateway Reference — Route Predicate Factories:** https://docs.spring.io/spring-cloud-gateway/reference/
- **Spring Cloud Gateway — GatewayFilter Factories** (Path, Header, Method, StripPrefix, RewritePath, SetRequestHeader, SetResponseHeader): https://docs.spring.io/spring-cloud-gateway/reference/
- **Spring Security Reactive Resource Server JWT:** https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/jwt.html
- **HTTP Semantics, RFC 9110** (Accept, Vary, conditional requests, status codes): https://www.rfc-editor.org/rfc/rfc9110
- **Deprecation HTTP Response Header Field, RFC 9745:** https://www.rfc-editor.org/rfc/rfc9745
- **Sunset HTTP Header Field, RFC 8594:** https://www.rfc-editor.org/rfc/rfc8594
- **OpenAPI Specification:** https://spec.openapis.org/oas/latest.html

**Lưu ý sử dụng ví dụ:** Các mã Java/YAML trong bài mô tả một cấu hình **Gateway Server WebFlux** với hai routes theo path và hai routes theo header, nhằm học/kiểm thử trên môi trường có dữ liệu giả. Tên property, starter, API filter và meter có thể thay đổi theo phiên bản Spring Cloud Gateway; ví dụ không tự thay cho test chạy thực, security review hoặc vòng QA học thuật STEP 6.
