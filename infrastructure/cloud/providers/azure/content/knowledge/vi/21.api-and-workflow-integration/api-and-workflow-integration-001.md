# Azure API Management và tổ chức API

Giả sử một công ty có các dịch vụ **đơn hàng**, **khách hàng** và **thanh toán**. Ứng dụng mobile cần tra cứu đơn hàng; website gọi API giỏ hàng; đối tác logistics chỉ được xem trạng thái giao hàng; nhóm nội bộ có thêm quyền quản trị. Nếu từng nhóm client gọi thẳng vào các backend, mỗi dịch vụ sẽ phải tự giải quyết nhiều vấn đề giống nhau: xác thực token, giới hạn lưu lượng, định tuyến, thay đổi phiên bản, cung cấp tài liệu, theo dõi lỗi và bảo vệ API khi backend gặp sự cố.

**Azure API Management (APIM)** cung cấp một lớp **API gateway và quản trị vòng đời API** giữa client và các backend. Nó giúp công bố API theo hợp đồng rõ ràng, gom những operations có liên quan, áp dụng policies chung hoặc riêng, cấp quyền truy cập theo sản phẩm/nhóm người dùng, theo dõi việc sử dụng và hỗ trợ thay đổi API mà không bắt mọi consumer hiểu chi tiết hạ tầng phía sau.

Bài thuộc chương **API và tích hợp quy trình** của module **CLOUD_PROVIDERS_AZURE**. Trong bức tranh Microsoft Azure từ subscription, resource group, Microsoft Entra ID đến mạng ảo, compute, storage và dữ liệu, APIM là một thành phần kết nối các ứng dụng với backend như **Azure App Service, Azure Functions, Azure Container Apps, AKS, Azure SQL** hoặc API bên ngoài. Việc tổ chức API phải đi đôi với bảo mật, giám sát, khả năng khôi phục và kiểm soát chi phí; chỉ “đưa một URL qua gateway” là chưa đủ.

Sau khi hoàn thành, bạn có thể:

- Mô tả vai trò và các thành phần của API Management: **instance, gateway, API, operation, product, group, subscription, backend, policy và developer portal**.
- Thiết kế API surface theo bounded context, route, OpenAPI contract, consumer, phiên bản và quyền.
- Phân biệt **API version** với **API revision**, lựa chọn versioning strategy và quy trình thay đổi tương thích.
- Áp dụng các APIM policies như `validate-jwt`, `rate-limit-by-key`, `quota-by-key`, `set-backend-service`, `rewrite-uri`, `set-header` và `cors` đúng mục đích.
- Phân biệt **APIM subscription key** với **Microsoft Entra access token**, managed identity và backend authorization.
- Import API từ OpenAPI bằng Azure CLI/Portal, cấu hình product và kiểm chứng đường đi gateway → backend.
- Thiết kế mạng riêng, bảo vệ backend, quan sát lỗi, tự động hóa CI/CD và quy trình rollback.
- Chọn SKU/cấp triển khai dựa trên tải, độ trễ, networking, tính năng, SLA và chi phí.

## 1. APIM là gì và giải quyết vấn đề nào?

**Azure API Management** là dịch vụ quản lý các API được công bố cho client nội bộ, đối tác hoặc công chúng. Một APIM instance bao gồm các mặt chức năng chính:

1. **API gateway:** nhận request, kiểm tra chính sách, định tuyến đến backend và trả response.
2. **Management plane:** cấu hình APIs, operations, products, groups, subscriptions, policies, backends, identities và các tài nguyên quản trị.
3. **Developer portal:** cung cấp catalog/tài liệu API và quy trình onboarding của developer theo cấu hình/tính năng của dịch vụ.
4. **Observability/integration:** theo dõi usage, diagnostics, traces/logs và kết nối Azure Monitor hoặc hệ thống quan sát được hỗ trợ.

APIM hoạt động như lớp **front door logic của API**, nhưng không nên nhầm nó với một ứng dụng backend. APIM có thể kiểm tra JWT, viết lại URI, đặt header, cache response hoặc giới hạn request; phần lớn **business logic và giao dịch dữ liệu** vẫn thuộc các backend.

### 1.1. Ví dụ luồng request

~~~mermaid
flowchart LR
    CLIENT[Mobile / web / partner] -->|HTTPS + token/key| GATEWAY[APIM Gateway]
    GATEWAY -->|Policies| POLICY[Validate / rate-limit / rewrite]
    POLICY -->|Forward| ORDERS[Orders API - App Service]
    POLICY -->|Forward| DELIVERY[Shipping API - Container Apps]
    POLICY -->|Forward| PAY[Payments API - AKS]
    ORDERS --> DB[(Azure SQL)]
    DELIVERY --> BUS[Azure Service Bus]
    PAY --> KV[Azure Key Vault]
    GATEWAY -. Request metrics/traces .-> MON[Azure Monitor]
    ADMIN[API platform team] -. Config/APIs/products .-> GATEWAY
~~~

Ví dụ consumer gọi:

~~~http
GET https://api.contoso.example/orders/v1/orders/INV-98421 HTTP/1.1
Authorization: Bearer <access-token>
Ocp-Apim-Subscription-Key: <subscription-key-if-required>
X-Correlation-ID: req-8f0a
~~~

Gateway có thể xác thực token, kiểm tra hạn mức, sau đó route request tới `https://orders-backend.internal/api/orders/INV-98421`. Consumer nhìn thấy đường dẫn và contract **công khai**, không cần biết hostname hay kiến trúc triển khai của backend.

### 1.2. Khi nào nên dùng APIM?

| Tình huống | APIM mang lại | Điều vẫn phải tự thiết kế |
|---|---|---|
| Nhiều backend cùng có public API | Gateway chung và hợp đồng API thống nhất | Ownership từng API, domain boundaries |
| Công bố API cho đối tác | Product, onboarding, subscriptions, developer portal | Quyền nghiệp vụ, legal agreements, SLA |
| Bảo vệ API | JWT validation, throttling, routing policies | AuthN/AuthZ cuối cùng ở backend, WAF/DoS defense theo kiến trúc |
| API thay đổi phiên bản | Version sets, revisions, quản lý công bố | Backward compatibility, deprecation/migration |
| Quan sát API | Metrics, diagnostics, correlation | Instrumentation backend, SLO và cảnh báo |
| Môi trường hybrid hoặc nhiều region | Các mô hình gateway/network được hỗ trợ | DNS, private routing, failover, DR |

APIM thường phù hợp khi có **nhiều consumer** hoặc khi chính sách API được dùng chung ở nhiều backend. Với một ứng dụng nhỏ chỉ có một endpoint private và chưa cần quản trị/API catalog, thêm APIM có thể tăng chi phí và độ phức tạp không cần thiết. Hãy chọn theo yêu cầu thực tế.

### 1.3. APIM không thay thế những gì?

- **Không thay Azure Application Gateway/Front Door với WAF:** APIM chủ yếu là gateway và API lifecycle; bảo vệ HTTP trước một số loại tấn công có thể cần WAF/edge riêng.
- **Không tự giải quyết authorization nghiệp vụ:** kiểm tra access token hợp lệ chưa đủ để biết user được xem **đơn hàng cụ thể nào**; backend phải kiểm tra ownership/permissions.
- **Không là service mesh/Kubernetes ingress controller tương đương:** các sản phẩm giải quyết các lớp vận hành khác nhau.
- **Không là queue, workflow engine hoặc database:** Service Bus/Event Grid/Logic Apps/SQL thực hiện vai trò tương ứng.
- **Không biến một backend lỗi thành khỏe:** retry, cache và circuit-breaker policy không thay khả năng phục hồi từ ứng dụng/dữ liệu.

## 2. Kiến trúc APIM trong hệ sinh thái Azure

APIM được đặt trong một **subscription và resource group** cùng các tài nguyên ứng dụng. APIM instance chạy trên một tier/SKU xác định, có hostname gateway, management và các thành phần/tính năng tương ứng.

~~~mermaid
flowchart TB
    USER[Consumer / partner] --> EDGE[Azure Front Door + WAF - nếu cần]
    EDGE --> G[APIM Gateway]
    DEVPORT[Developer Portal] -. API docs + onboarding .-> USER
    ADMIN[Platform team: Entra + Azure RBAC] -. Management plane .-> G
    G -->|HTTPS| WEB[App Service backend]
    G -->|HTTPS| FN[Functions backend]
    G -->|HTTPS via approved network| AKS[AKS backend]
    WEB --> SQL[(Azure SQL)]
    FN --> BLOB[(Blob Storage)]
    AKS --> SERVICEBUS[(Service Bus)]
    G -. Diagnostics .-> OBS[Azure Monitor / App Insights]
    KV[Key Vault] -. Certificates / secrets via identity .-> G
~~~

### 2.1. Ba đường đi cần kiểm chứng

1. **Client → APIM gateway (inbound):** hostname, public/private exposure, TLS, certificate, WAF/access restrictions và client authentication.
2. **APIM → backend (outbound):** backend URL, DNS, VNet connectivity/private endpoint, TLS và backend credentials/managed identity.
3. **Operator/CI → APIM management plane:** Azure RBAC, Azure Resource Manager hoặc management API, CI/CD và policy deployment.

Đường client truy cập được APIM **không chứng minh** APIM có thể gọi backend. Ngược lại, gateway truy cập backend private không có nghĩa public client được phép đi vào gateway. Một giải pháp cần kiểm thử từng đường riêng và xác định điểm thực hiện authorization.

### 2.2. Gateway và control plane khác nhau

| Mặt chức năng | Ví dụ hoạt động | Quyền/kiểm soát |
|---|---|---|
| **Data plane - gateway** | Gọi `GET /orders`, áp policies, forward đến backend | Authentication token, subscription key, quotas, network |
| **Management plane** | Tạo API, chỉnh product, sửa policy, tạo version | Microsoft Entra, Azure RBAC, deployment approval |
| **Developer plane** | Xem docs, đăng ký sản phẩm, thử API | Portal user/group, product visibility, subscription approval |
| **Backend data plane** | Lấy đơn hàng từ SQL hoặc publish Service Bus message | Workload identity, database row-level/business auth |

Không dùng role `Contributor` ở resource group như bằng chứng user đã có quyền **gọi API nghiệp vụ**. Một người có thể quản lý APIM mà không có JWT phù hợp để gọi `POST /payments`; ngược lại consumer có subscription nhưng không có quyền đổi policy.

## 3. Tổ chức tài nguyên: từ instance tới API operation

Một cách hình dung:

~~~text
APIM instance: apim-shared-prod
├── API: Orders API
│   ├── GET  /orders/{id}
│   ├── POST /orders
│   └── GET  /orders/{id}/status
├── API: Catalog API
│   ├── GET  /products
│   └── GET  /products/{id}
├── API: Shipping API
│   └── GET /shipments/{id}
├── Products
│   ├── Partner Basic → Orders read + Shipping read
│   └── Internal Pro → Orders + Catalog + Shipping
├── Groups / Subscriptions
├── Named values / Backends / Policies
└── Developer portal / Diagnostics
~~~

### 3.1. Các khái niệm cốt lõi

| Đối tượng | Là gì? | Ví dụ và mục đích |
|---|---|---|
| **APIM instance/service** | Tài nguyên gateway/quản trị ở Azure | `apim-shared-prod` |
| **API** | Tập hợp operations có chung contract và public URL suffix | `Orders API`, suffix `orders/v1` |
| **Operation** | Một HTTP method + URL template (hoặc mô hình API tương ứng) | `GET /orders/{id}` |
| **Product** | Gói công bố một hoặc nhiều APIs tới consumer với subscription/policy phù hợp | `Partner Basic` |
| **Group** | Nhóm người dùng/developer trong APIM để quản quyền nhìn/đăng ký product | `partners`, `internal` |
| **Subscription** | Quan hệ đăng ký/credential truy cập API/product theo subscription scope | Key do APIM cấp cho consumer |
| **Backend entity** | Cấu hình đích backend và một số phương án credential/circuit breaker theo tính năng | `orders-backend` |
| **Policy** | Quy tắc xử lý request/response ở một scope | `validate-jwt`, `rate-limit-by-key` |
| **Named value** | Giá trị cấu hình tái sử dụng trong policies, có khả năng liên kết Key Vault | `orders-backend-url` |
| **API version set** | Gom các API versions thuộc một API logic | `Orders v1` và `Orders v2` |
| **API revision** | Thay đổi không phá vỡ contract của một version/API | `Orders v1;rev=2` |

**API khác Product:** API mô tả contract và operations; Product mô tả **gói truy cập** dành cho đối tượng tiêu thụ. Một API có thể được đặt trong nhiều products khi mô hình APIM cho phép và phù hợp yêu cầu. Product không phải container runtime và không tạo bản sao backend.

### 3.2. Mô hình ownership theo domain

Nên chia APIs theo **năng lực nghiệp vụ** thay vì theo một màn hình giao diện hoặc theo đúng số microservices:

| API domain | Owner | Client chính | Backend hiện tại | Data classification |
|---|---|---|---|---|
| Orders | Order team | Web/mobile/partner | App Service | Dữ liệu đơn hàng |
| Catalog | Commerce team | Web/mobile | Container Apps | Danh mục công khai |
| Payments | Payment team | Internal/payment partner | AKS/private service | Tài chính nhạy cảm |
| Shipping | Logistics team | Partner/internal | Azure Functions | Trạng thái giao hàng |

Một API contract có thể được thực thi bởi nhiều backend trong tương lai; consumer không nên phải đổi endpoint chỉ vì nhóm vận hành chuyển backend từ VM sang App Service. Tránh tạo một “super API” trộn mọi domain với cùng auth/rate limit, gây khó kiểm soát version và ownership.

### 3.3. Phân loại APIs khi công bố

- **Public APIs:** dành cho consumer ngoài tổ chức, có hợp đồng/điều khoản rõ ràng.
- **Partner APIs:** chỉ cho đối tác có hợp đồng, cơ chế đăng ký và giám sát theo partner.
- **Internal APIs:** phục vụ hệ thống/nhân viên nội bộ, có thể cần private gateway và identity nội bộ.
- **Administrative APIs:** quyền mạnh, không nên công bố như một API product phổ thông.

Phân loại này không tự tạo bảo mật. **Cần kết hợp network exposure, token audience/scopes, chính sách APIM, backend authorization và audit**.

## 4. API contract và chuẩn hóa operations

Trước khi import vào APIM, hãy thiết kế contract của API: URL, method, schema, error codes, authentication, pagination, idempotency, versioning và backward compatibility. **OpenAPI** là một cách phổ biến để mô tả HTTP REST API và tạo tài liệu/SDK/tests.

### 4.1. Quy tắc đường dẫn và HTTP method

Ví dụ:

~~~text
GET    /orders/v1/orders                List/search orders
POST   /orders/v1/orders                Create order
GET    /orders/v1/orders/{orderId}      Get order by ID
GET    /orders/v1/orders/{orderId}/status
PATCH  /orders/v1/orders/{orderId}      Update selected fields
~~~

Ở đây `orders/v1` là **API suffix trên APIM gateway** và `/orders/{orderId}` là đường dẫn operation nằm trong API. Khi import một OpenAPI spec có servers/path, cần kiểm tra mapping cuối cùng để tránh route bị lặp kiểu `/orders/v1/orders/v1/orders`.

| Quy tắc | Lý do |
|---|---|
| Sử dụng HTTP methods đúng semantics | GET không làm thay đổi nghiệp vụ; POST có thể tạo resource |
| Dùng resource names rõ ràng | Dễ khám phá và bảo trì API |
| Xác định error model thống nhất | Client phân biệt 400/401/403/404/409/429/500/503 |
| Pagination và filtering | Không trả hàng triệu records trong một response |
| Idempotency key khi cần | Retry POST sau network timeout không tạo đơn trùng |
| Correlation/request ID | Debug xuyên APIM và backend |
| Xác định response schema và content type | Tránh client phụ thuộc trường không cam kết |
| Document deprecation | Consumer có thời gian chuyển version |

### 4.2. Ví dụ OpenAPI tối giản

~~~yaml
openapi: 3.0.3
info:
  title: Orders API
  version: 1.0.0
  description: API quản lý đơn hàng, ví dụ dùng cho bài học.
servers:
  - url: https://api.contoso.example/orders/v1
paths:
  /orders/{orderId}:
    get:
      operationId: getOrderById
      summary: Lấy thông tin đơn hàng
      parameters:
        - in: path
          name: orderId
          required: true
          schema:
            type: string
      responses:
        "200":
          description: Đơn hàng tồn tại
          content:
            application/json:
              schema:
                type: object
                required: [id, status]
                properties:
                  id: {type: string}
                  status: {type: string}
        "401":
          description: Thiếu hoặc không hợp lệ thông tin xác thực
        "403":
          description: Không đủ quyền xem đơn hàng
        "404":
          description: Không tìm thấy đơn hàng
  /orders:
    post:
      operationId: createOrder
      summary: Tạo đơn hàng
      requestBody:
        required: true
        content:
          application/json:
            schema:
              type: object
              required: [customerId]
              properties:
                customerId: {type: string}
      responses:
        "201": {description: Tạo đơn hàng thành công}
        "400": {description: Dữ liệu không hợp lệ}
        "409": {description: Xung đột nghiệp vụ}
~~~

**Đây là contract học tập**, không phải endpoint hiện hữu. `api.contoso.example`, mã đơn hàng và backend cần được thay bằng tên thực theo hệ thống đã được cấp phép. Khi import, phải kiểm tra OpenAPI validator, quyền operation path, request-body validation và cách APIM trích server base URL.

### 4.3. Contract ≠ implementation

Import OpenAPI tạo mô hình API/operations/tài liệu ở APIM; **không tự triển khai backend**, tạo database hay xác minh logic nghiệp vụ đúng. APIM có thể chuyển request theo contract nhưng backend vẫn phải bảo đảm dữ liệu trả ra, authentication, authorization theo từng resource và transaction integrity.

Một hợp đồng OpenAPI không khai báo security scheme không có nghĩa API thực tế được phép công khai. Thiết lập security requirement trong OpenAPI và policies/rules tương ứng, rồi **kiểm thử negative cases** (không token, sai token, sai scope, sai consumer key, sai order owner).

## 5. API versions và revisions: hai cơ chế khác nhau

API có thể thay đổi theo hướng tương thích hoặc phá vỡ hợp đồng. APIM có **API versions** và **API revisions** để tổ chức những thay đổi này.

### 5.1. Khi nào tạo version mới?

Tạo **API version mới** khi client cũ không còn tương thích với hợp đồng API mới. Ví dụ:

- Đổi một field bắt buộc từ `amount` (decimal) sang `amountMinorUnits` (integer) mà client cũ không hiểu.
- Xóa operation đang được consumer sử dụng.
- Thay cách xác thực hoặc semantics của operation theo cách phá vỡ client.
- Thay đổi response schema/HTTP behavior theo cách khiến client cũ không thể xử lý.

Với API version set, APIM có thể tổ chức nhiều versions của cùng API logic. Có các **versioning schemes** như **path**, **query string** hoặc **header**, tùy cấu hình/tính năng:

| Chiến lược | Ví dụ | Ưu / nhược điểm |
|---|---|---|
| **Path-based** | `/orders/v1/orders/123` | Dễ nhìn, test và cache; version lộ trong URL |
| **Query-based** | `/orders/orders/123?api-version=1` | Giữ path ổn định, dễ gọi; cần nhất quán query/clients |
| **Header-based** | `Api-Version: v1` | URL gọn; khó quan sát hơn nếu tools/cache/proxies không giữ header |

Không có chiến lược nào tự động bảo đảm compatibility. Nên chọn một cách phù hợp cho cả hệ thống, ghi tài liệu, chuẩn hóa error model và tránh đổi cách đánh version mỗi khi có team mới.

### 5.2. Khi nào dùng revision?

**API revision** phù hợp với thay đổi **không phá vỡ contract** của một API/version: thêm một optional response field, cập nhật description, tối ưu policies hoặc thay backend route mà consumer không cần thay request.

APIM giữ khái niệm **current revision** và các non-current revisions để kiểm thử/đưa ra bản mới theo quy trình tương ứng. Trong một số mô hình REST API, non-current revision có thể truy cập qua URL có dạng `;rev=2` để kiểm thử khi điều kiện gateway/tier/authorization cho phép. **Đây không phải cơ chế canary theo phần trăm traffic tự động**; việc đưa một revision thành current cần thao tác phát hành rõ ràng.

| Câu hỏi | API version | API revision |
|---|---|---|
| Mục đích | Quản lý hợp đồng không tương thích | Điều chỉnh cùng hợp đồng mà không đổi version |
| Client cần chọn khác đi? | Thường có, qua path/header/query | Thường không với current revision |
| Ví dụ | v1 và v2 cùng tồn tại | v1;rev=1 và v1;rev=2 |
| Phục vụ migration dài hạn? | Phù hợp để hỗ trợ v1/v2 song song | Chủ yếu cho chỉnh sửa/test trước khi công bố current |
| Thay đổi DB schema phá tương thích? | Vẫn cần migration/contract plan | Revision không tự rollback dữ liệu |

### 5.3. Release một revision an toàn

1. Ghi nhận revision hiện hành, policies, backend và các client quan trọng.
2. Tạo revision mới từ API hiện hữu theo khả năng APIM.
3. Thay operation/policy/backend ở **revision thử nghiệm**.
4. Kiểm thử auth, 2xx, 4xx, 5xx, quota và dữ liệu qua URL revision hoặc test setup được hỗ trợ.
5. Phê duyệt, chuyển revision thành **current** theo quy trình phát hành.
6. Quan sát request/error/latency và hỗ trợ rollback về revision cũ nếu còn hợp lệ.

**Rollback APIM revision không rollback application deployment hoặc database**. Nếu backend code mới đã xóa cột SQL mà bản cũ cần, chuyển policy/revision cũ không tự phục hồi schema. Phải thiết kế thay đổi dữ liệu và ứng dụng tương thích, ví dụ expand–migrate–contract.

## 6. Products, groups và subscriptions: công bố API theo consumer

Nếu API là “những gì hệ thống có thể làm”, **product** là “gói API mà một nhóm consumer được phép khám phá/đăng ký với các quy tắc tương ứng”. Product có thể gom nhiều APIs, cấu hình publish/approval/subscription requirements và áp policies ở cấp product theo tính năng APIM.

### 6.1. Ví dụ thiết kế products

| Product | APIs đưa vào | Đối tượng | Giới hạn minh họa | Quy trình onboarding |
|---|---|---|---|---|
| **Partner Basic** | GET Orders, GET Shipping (cần cân nhắc phạm vi API/operations) | Đối tác logistics | 60 requests/phút theo subscription | Review hồ sơ đối tác |
| **Internal Business** | Orders + Catalog + Shipping | Ứng dụng nhân viên | Theo quota nội bộ | Entra group / approval |
| **Premium Partner** | Orders + Shipping + API nâng cao | Đối tác có hợp đồng trả phí | Theo hợp đồng/SLO | Contract + approval |
| **Sandbox** | API test với dữ liệu giả | Developer thử nghiệm | Hạn mức thấp | Self-service có điều kiện |

**Chú ý granularity:** trong APIM, product phổ biến liên kết ở **cấp API**, không nhất thiết hỗ trợ chọn chỉ một HTTP operation cho từng product bằng thao tác thêm API. Nếu product chỉ được gọi `GET` mà cùng API cũng có `POST`, phải thiết kế **API tách phù hợp hoặc chính sách authorization/operation restrictions**. Đừng cho rằng đưa Orders API vào Partner Basic tự động chỉ cấp GET vì bảng mô tả ghi “GET Orders”.

### 6.2. Group không tương đương Azure RBAC

Một group trong APIM có thể được dùng để quản lý khả năng xem/đăng ký một product qua developer portal. Nó **không** thay thế:

- Microsoft Entra group và **Azure RBAC** trên tài nguyên APIM management plane;
- OAuth scopes/app roles trong **access token** của client;
- Quyền nghiệp vụ ở backend đối với order/customer cụ thể.

Một người thuộc `partners` group được nhìn product trên portal không mặc nhiên được gọi `DELETE /orders`. Muốn bảo vệ thao tác xóa, cần kiểm tra token, product/subscription context và quyền cuối cùng tại backend.

### 6.3. Product publication và subscription approval

Một product có thể được cấu hình **published/unpublished** và yêu cầu subscription/approval theo tính năng. Consumer đăng ký subscription để lấy credentials truy cập khi API/product yêu cầu. Có thể có **product-scoped** subscriptions hoặc subscriptions ở phạm vi khác như API/all-APIs tùy cấu hình APIM; vì vậy policy ở product scope **không nên được giả định luôn áp dụng với mọi đường gọi tới một API** nếu consumer có subscription scope khác.

Những quyết định cần ghi rõ:

1. Consumer nào được xem product và tài liệu?
2. Ai được đăng ký/tạo subscription và có cần phê duyệt không?
3. Subscription key gắn với product hay API? Có quy tắc bypass product không?
4. Khi thay đổi người dùng, hợp đồng hoặc điều khoản, ai revoke/rotate key?
5. API có yêu cầu **JWT hợp lệ** bên cạnh subscription key không?
6. Product policy có thực thi ở mọi call path được phép theo scope hiện tại không?

**Không để một product “internal” published cho mọi developer rồi tin rằng tên sản phẩm đã ngăn truy cập.** Phải kiểm tra settings và thử trực tiếp gateway endpoint bằng các credential không đủ quyền.

### 6.4. Subscription keys không chứng minh danh tính người dùng

APIM thường hỗ trợ hai keys của một subscription để luân chuyển. Key được client gửi, điển hình qua header:

~~~http
Ocp-Apim-Subscription-Key: <apim-subscription-key>
~~~

Key có thể giúp định danh một **subscription/calling application**, áp quotas và thực hiện một số kiểm soát tiêu thụ, nhưng nó là **shared bearer secret**, không phải cơ chế người dùng đăng nhập hay token chuẩn OAuth 2.0. Nếu key bị lộ, người có key có thể gọi API trong phạm vi cho phép đến khi key bị rotate/revoke.

Với API xử lý dữ liệu khách hàng hoặc thanh toán, thông thường cần **Entra/OAuth2/JWT hoặc cơ chế authentication phù hợp**, rồi **authorization nghiệp vụ**, bên cạnh subscription key nếu tổ chức quyết định dùng.

## 7. Policies: pipeline xử lý request/response của APIM

Policies là các cấu hình XML khai báo **cách gateway xử lý request/response**. Đây là năng lực rất quan trọng của APIM, nhưng cũng là nguồn rủi ro khi policy có scope quá rộng, đặt sai thứ tự hoặc làm lộ thông tin.

### 7.1. Bốn section thường dùng

~~~xml
<policies>
  <inbound>
    <base />
    <!-- xác thực, giới hạn, sửa request trước khi gọi backend -->
  </inbound>
  <backend>
    <base />
    <!-- điều phối forward hoặc cấu hình backend -->
  </backend>
  <outbound>
    <base />
    <!-- xử lý response trả về client -->
  </outbound>
  <on-error>
    <base />
    <!-- xử lý lỗi phát sinh trong policy pipeline -->
  </on-error>
</policies>
~~~

| Section | Trách nhiệm chính | Ví dụ |
|---|---|---|
| **inbound** | Áp chính sách vào request trước backend | Validate JWT, rate limit, rewrite, set headers |
| **backend** | Quyết định xử lý request tới backend | Forward-request, cấu hình retry theo kiểm soát |
| **outbound** | Điều chỉnh response trước client | Ẩn internal headers, set header, cache-store |
| **on-error** | Xử lý lỗi từ policy pipeline khi lỗi phát sinh | Ghi log có kiểm soát, trả error response phù hợp |

**Cần phân biệt HTTP 4xx/5xx trả về bình thường từ backend với lỗi policy pipeline.** `on-error` không phải cơ chế bắt mọi HTTP 500 để tự động biến thành 200. Nếu cần xử lý response theo status code, dùng điều kiện trong outbound hoặc thiết kế chính sách lỗi đúng semantics và bảo toàn khả năng điều tra.

### 7.2. Policy scope và kế thừa

Các scope phổ biến gồm:

1. **Global (all APIs)**: logging, security headers, một số policy bảo vệ mặc định.
2. **Workspace** nếu mô hình/tier hỗ trợ: boundary vận hành của một nhóm API.
3. **Product**: policies áp với những lời gọi thuộc product theo scope của subscription và routing.
4. **API**: quy tắc dùng chung cho mọi operations của API.
5. **Operation**: ngoại lệ riêng cho một HTTP method/path.

`<base />` là điểm quan trọng để áp các policies từ scope cao hơn theo quy tắc kế thừa APIM. **Bỏ `<base />` có thể làm một policy ở scope thấp không áp dụng policies ở scope cha như mong đợi**, dẫn đến bỏ lọt authentication/throttling hoặc hành vi khác. Với production, cần review **effective policy** của operation sau khi ghép scopes, không chỉ xem một file XML.

### 7.3. Những policy thường gặp

| Policy | Vai trò | Điểm cẩn thận |
|---|---|---|
| `validate-jwt` | Xác thực JWT từ client | Issuer, audience, expiration, required claims |
| `rate-limit` / `rate-limit-by-key` | Giới hạn số request trong cửa sổ ngắn | Chọn counter key theo consumer, hiểu tính xấp xỉ ở nhiều gateways |
| `quota` / `quota-by-key` | Giới hạn usage trên khoảng dài hơn | Billing/quota không bằng transaction accounting tuyệt đối |
| `set-backend-service` | Chọn backend URL/entity | Tránh backend URL từ dữ liệu client không đáng tin |
| `rewrite-uri` | Ánh xạ public route sang backend route | Đảm bảo path/query parameter được chuyển đúng |
| `set-header` | Thêm/xóa/ghi đè HTTP headers | Không forward client-supplied identity header đáng tin cậy một cách mù quáng |
| `set-query-parameter` | Thay đổi query phục vụ backend | Tránh ghi secret vào URL/log |
| `cors` | Cấu hình Cross-Origin Resource Sharing | CORS không phải authentication/authorization |
| `cache-lookup` / `cache-store` | Caching theo khả năng gateway | Không cache response cá nhân hóa hoặc dữ liệu nhạy cảm sai key |
| `choose` / `when` | Rẽ nhánh điều kiện theo context | Complex logic cần tests |
| `return-response` | Trả response từ gateway mà không gọi backend | Chỉ dùng đúng mục đích và status |
| `authentication-managed-identity` | Lấy token để APIM gọi backend bằng managed identity | Token audience đúng và backend phải chấp nhận Entra token |

Các policy có thể có hạn chế theo gateway/tier và phiên bản. Trước khi triển khai production, cần kiểm tra **policy reference** theo APIM tier/gateway đang dùng và test cả positive/negative cases.

## 8. Thực hành policy: JWT, rate limit và backend routing

Các ví dụ sau là **mẫu để học cách đọc XML policy**, không phải file cấu hình sẵn cho production. Người thực hành phải thay tenant ID, App ID URI/audience, backend URL, counter keys và chọn đúng scope sau khi review.

### 8.1. Validate JWT từ Microsoft Entra ID

Ví dụ API có **access token** do một tenant Entra cấp, audience là API của bạn. Policy có thể đặt ở API scope:

~~~xml
<policies>
  <inbound>
    <base />
    <validate-jwt
      header-name="Authorization"
      require-scheme="Bearer"
      failed-validation-httpcode="401"
      failed-validation-error-message="Unauthorized">
      <openid-config
        url="https://login.microsoftonline.com/11111111-2222-3333-4444-555555555555/v2.0/.well-known/openid-configuration" />
      <audiences>
        <audience>api://orders-api-app-id</audience>
      </audiences>
      <required-claims>
        <claim name="roles" match="any">
          <value>Orders.Read</value>
        </claim>
      </required-claims>
    </validate-jwt>
  </inbound>
  <backend>
    <base />
  </backend>
  <outbound>
    <base />
  </outbound>
  <on-error>
    <base />
  </on-error>
</policies>
~~~

**Ý nghĩa từng bước:**

1. Gateway đọc `Authorization: Bearer <token>` từ client.
2. Token được kiểm tra theo OpenID configuration/JWKS của **tenant được tin cậy**, audience được chấp nhận và các điều kiện xác thực khác.
3. Policy ví dụ yêu cầu app role `Orders.Read` trong claim `roles`.
4. Nếu không đạt, APIM trả 401 theo policy, **không forward request** đến backend.

**Nuance quan trọng:**

- `api://orders-api-app-id` là **placeholder**, phải thay bằng audience thực do API app registration định nghĩa. Ở production, enforce đúng token issuer/tenant, audience, expiry và claims/scope phù hợp.
- Delegated access tokens thường dùng `scp`, trong khi application permissions thường dùng `roles`. Không dùng mẫu `roles=Orders.Read` để kết luận mọi delegated flow đúng; thiết kế policy theo loại client thực tế.
- Nếu API cần biết **ai được truy cập order cụ thể**, backend vẫn phải kiểm tra customer ownership, tenant ID, resource permission và row-level authorization.
- Không dùng **ID token** thay access token cho API. ID token dùng để xác minh phiên đăng nhập của client, không mặc nhiên có audience/permissions phù hợp để gọi API.
- Khi áp policy ở operation scope, nếu muốn operation này chấp nhận `Orders.Write` thay vì `Orders.Read`, phải xem **chính sách kế thừa** để không tự yêu cầu hai role mâu thuẫn.

### 8.2. Rate limiting theo một định danh đã kiểm chứng

Một ví dụ đơn giản giới hạn theo subscription; với API mà subscription có thể rỗng/không bắt buộc, cần thiết kế counter key riêng:

~~~xml
<policies>
  <inbound>
    <base />
    <rate-limit-by-key
      calls="60"
      renewal-period="60"
      counter-key="@(context.Subscription != null
        ? context.Subscription.Id
        : context.Request.IpAddress)" />
  </inbound>
  <backend>
    <base />
  </backend>
  <outbound><base /></outbound>
  <on-error><base /></on-error>
</policies>
~~~

Ví dụ trên **không phải policy chống abuse hoàn hảo**. Nếu không có subscription, giới hạn theo IP có thể gom nhiều user sau NAT vào một counter hoặc có thể bị phân tán khi caller đổi IP. Với JWT-protected API, có thể cân nhắc dùng một **claim đã được validate** (tenant/application/client ID) làm key, tránh dùng header không xác thực do client tự đặt.

Ở hệ thống multi-region/multiple gateway, bộ đếm rate limit và độ chính xác có thể phụ thuộc cơ chế phân tán/tier. Đừng dùng nó thay billing chính xác, chống gian lận hay transaction quota cần đảm bảo tuyệt đối. Khi vượt hạn mức, client nên xử lý HTTP **429**, backoff và tuân thủ `Retry-After` nếu có.

### 8.3. Quy tắc kết hợp authentication và throttling

Thứ tự policies có ý nghĩa. Một cấu hình có thể chọn chặn traffic không hợp lệ sớm để giảm tải backend; tuy nhiên việc xác thực JWT có overhead và nếu rate limit được đặt sau authentication, request vô danh có thể không bị counter theo mong đợi. Chọn chiến lược phù hợp với threat model.

Một pipeline điển hình:

~~~text
Client HTTPS request
    ↓
Edge/WAF/network admission nếu có
    ↓
APIM inbound
    → validate token / subscription theo policy
    → limit caller/tenant/operation
    → validate required headers / transform URI
    → set backend and identity
    ↓
APIM backend: forward request
    ↓
Backend: business authorization + transaction
    ↓
APIM outbound: response headers / cache/log nếu phù hợp
    ↓
Client response
~~~

Không tin client-supplied `X-User-ID` hoặc `X-Tenant-ID` như danh tính đã xác thực nếu không xác minh token và xóa/ghi đè header giả mạo trước khi chuyển cho backend.

### 8.4. Chọn backend theo URL đã cấu hình

~~~xml
<policies>
  <inbound>
    <base />
    <set-backend-service
      base-url="https://orders-api.internal.example" />
    <rewrite-uri template="/api/orders/{orderId}" />
  </inbound>
  <backend><base /></backend>
  <outbound><base /></outbound>
  <on-error><base /></on-error>
</policies>
~~~

**Giới hạn của ví dụ:** `{orderId}` phải là parameter hợp lệ được định nghĩa trên operation mà policy này áp dụng; nếu đặt ở API scope cho operations không có `orderId`, policy có thể không hợp lệ hoặc route sai. Nên gắn ví dụ ở operation `GET /orders/{orderId}` và test path/query. `orders-api.internal.example` là hostname minh họa; APIM gateway phải có DNS/route đến backend, không chỉ là URL viết trong policy.

### 8.5. Sử dụng backend entity và named values

Với hệ thống nhiều môi trường, không nên sao chép backend hostname/secret vào hàng chục XML policies. APIM có thể quản lý **backend entities** và **named values**, sau đó tham chiếu trong policy ở nơi hỗ trợ.

Ví dụ khái niệm:

~~~xml
<set-backend-service backend-id="orders-backend" />
~~~

Hoặc các policy values có thể tham chiếu named value theo cú pháp `{{orders-backend-url}}` ở các thuộc tính/hướng dẫn được hỗ trợ. Với giá trị nhạy cảm, dùng **Key Vault-backed named values** và managed identity/role thích hợp, tránh đưa secret plaintext vào Git hoặc log.

Named value giúp tái sử dụng cấu hình nhưng **không là authorization rule**. Nếu backend URL lấy từ một input không được xác thực, nguy cơ SSRF/routing sai vẫn tồn tại. Chỉ dùng danh sách backend hợp lệ và bảo vệ người có quyền sửa policies/named values.

## 9. CORS, caching, transformations và bảo vệ backend

APIM policies có thể giải quyết một số nhu cầu nằm giữa HTTP client và backend, nhưng cần đặt ra giới hạn để tránh biến gateway thành nơi chứa business logic khó kiểm thử.

### 9.1. CORS không phải kiểm soát quyền API

**Cross-Origin Resource Sharing (CORS)** là cơ chế trình duyệt quyết định có cho JavaScript từ một origin gọi và đọc response của một origin khác không. Ví dụ website `https://portal.contoso.example` muốn gọi `https://api.contoso.example`.

~~~xml
<policies>
  <inbound>
    <base />
    <cors allow-credentials="false">
      <allowed-origins>
        <origin>https://portal.contoso.example</origin>
      </allowed-origins>
      <allowed-methods>
        <method>GET</method>
        <method>POST</method>
      </allowed-methods>
      <allowed-headers>
        <header>Authorization</header>
        <header>Content-Type</header>
      </allowed-headers>
    </cors>
  </inbound>
  <backend><base /></backend>
  <outbound><base /></outbound>
  <on-error><base /></on-error>
</policies>
~~~

Đây là ví dụ cho **browser client**, cần điều chỉnh khi preflight request có các custom headers hoặc yêu cầu credentials. **CORS không ngăn curl, mobile app hay server-side callers** truy cập gateway; bảo vệ API bằng JWT, keys, network, permissions và backend authorization. Đừng đặt `*` tùy tiện cho origin/headers trong API nhạy cảm.

### 9.2. Caching để giảm tải nhưng tránh lộ dữ liệu

APIM có các policies phục vụ caching trên gateway hoặc external cache theo tính năng/tier/gateway phù hợp. Cache có thể hữu ích cho dữ liệu công khai hoặc ít thay đổi:

~~~text
GET /catalog/v1/products?page=1
    → Response có thể cache trong thời gian ngắn

GET /orders/v1/orders/INV-98421
    → Chứa dữ liệu của customer cụ thể, rất nhạy cảm
    → Không cache chỉ theo path công khai nếu nhiều user dùng chung
~~~

Khi muốn cache:

1. Xác định nội dung có được chia sẻ giữa tất cả callers hay không.
2. Thiết kế cache key tính đến query, vary headers, authorization/tenant khi phù hợp.
3. Chọn TTL và invalidation dựa trên freshness/SLA.
4. Kiểm tra behavior khi backend dữ liệu thay đổi hoặc trả lỗi.
5. Đánh giá cache support/limits theo APIM tier và topology multi-region.

**Không cache đơn hàng theo URL đơn thuần** nếu response phụ thuộc danh tính; nguy cơ user A nhận dữ liệu của user B. Với API nhiều tenants, cần tách cache theo context đã được xác thực hoặc tắt cache cho endpoints nhạy cảm.

### 9.3. Header transformation và correlation ID

Một policy có thể thêm correlation ID/tracing headers trước khi forward backend, hoặc xóa các headers nội bộ khỏi response. Ví dụ:

~~~xml
<policies>
  <inbound>
    <base />
    <set-header name="X-API-Gateway" exists-action="override">
      <value>azure-apim</value>
    </set-header>
  </inbound>
  <backend><base /></backend>
  <outbound>
    <base />
    <set-header name="X-Internal-Backend-Node"
                exists-action="delete" />
  </outbound>
  <on-error><base /></on-error>
</policies>
~~~

Không chuyển mọi header `Authorization` nguyên trạng tới backend khi backend không cần, hoặc để APIM viết đè các identity headers mà backend coi là đã được xác thực một cách không kiểm soát. Nếu backend nhận **JWT từ client**, phải quyết định rõ kiểm tra lại token hay chấp nhận chỉ APIM verify theo threat model; một backend có thể bị gọi trực tiếp qua đường khác nếu không được bảo vệ.

### 9.4. Response transformation có giới hạn

Gateway có thể thay status/header/body, chuyển XML ↔ JSON hoặc validate content theo policy/tính năng được hỗ trợ. Nhưng transformation phức tạp gây:

- Tăng latency và CPU ở gateway.
- Khó debug khi contract và backend payload khác nhau.
- Khó giữ compatibility khi schema phát triển.
- Rủi ro lộ dữ liệu nếu policy log/trả quá nhiều chi tiết.

Nếu transformation có nhiều quy tắc nghiệp vụ, cân nhắc một **adapter/backend-for-frontend** hoặc service tích hợp riêng. APIM phù hợp với policies có chủ đích, không nên biến thành nơi xử lý transaction SQL.

### 9.5. Throttling vs quota

| Cơ chế | Câu hỏi trả lời | Ví dụ |
|---|---|---|
| **Rate limiting** | Một consumer được gọi nhanh đến đâu? | 60 requests / 60 giây |
| **Quota** | Một consumer được dùng tổng cộng bao nhiêu trong kỳ? | 100.000 requests / tháng |
| **Backend concurrency limit** | Backend có thể xử lý cùng lúc bao nhiêu? | 50 requests chạy đồng thời |
| **Client retry budget** | Khi bị 429/503 được retry thế nào? | Exponential backoff + jitter |

Rate limit/quota của APIM không đồng nghĩa **capacity của backend được bảo đảm**. Một request nặng có thể chiếm tài nguyên hơn hàng trăm request nhẹ. Phải đo per-operation usage và kiểm soát concurrency/timeouts ở application/edge phù hợp.

## 10. Authentication, authorization và managed identity theo từng chặng

Một trong những lỗi thiết kế lớn nhất là cho rằng “API yêu cầu subscription key” đồng nghĩa “người gọi đã được xác thực đầy đủ”. Hãy tách các lớp:

### 10.1. Ba danh tính trong một request

~~~mermaid
flowchart LR
    APP[Client app] -->|Entra access token + optional subscription key| APIM[APIM Gateway]
    APIM -->|Managed identity token hoặc validated client token| BACKEND[Orders backend]
    BACKEND -->|Workload identity| SQL[(Azure SQL)]
~~~

| Chặng | Credential | Mục đích |
|---|---|---|
| **Client → APIM** | OAuth2/OIDC access token, mTLS/client cert hoặc phương án được phê duyệt; có thể thêm APIM subscription key | Xác minh application/user, quyền gọi API và quản lý usage |
| **APIM → backend** | Managed identity token, client token đã xác minh hoặc backend key/credential được bảo vệ | Chỉ gateway/identity hợp lệ được gọi backend |
| **Backend → database** | Workload identity và data-plane permission, hoặc secret quản lý an toàn | Chỉ API backend được truy cập dữ liệu cần thiết |

APIM subscription key **không** là một Microsoft Entra access token. Managed identity của APIM gọi backend **không đại diện tự động cho người dùng cuối**. Nếu backend cần biết user/tenant để authorize dữ liệu, phải truyền bối cảnh danh tính đã được xác thực theo giao thức an toàn và kiểm tra chính sách nghiệp vụ phù hợp.

### 10.2. Managed identity khi APIM gọi backend

Nếu backend là một API được bảo vệ bởi Microsoft Entra và chấp nhận token có audience phù hợp, APIM có thể dùng **managed identity** để lấy token:

~~~xml
<policies>
  <inbound>
    <base />
    <authentication-managed-identity
      resource="api://orders-backend-app-id" />
    <set-backend-service backend-id="orders-backend" />
  </inbound>
  <backend><base /></backend>
  <outbound><base /></outbound>
  <on-error><base /></on-error>
</policies>
~~~

**Điều kiện bắt buộc:**

- APIM instance có system-assigned hoặc user-assigned managed identity hợp lệ theo tính năng/cấu hình được hỗ trợ.
- Backend có app registration / audience đúng và cơ chế validate token từ Entra.
- APIM identity được cấp quyền **gọi backend** bằng app role/application permission/ủy quyền thích hợp ở Entra, không chỉ được gán Azure RBAC Contributor trên APIM resource.
- Đường mạng APIM → backend hoạt động và HTTPS/TLS được xác minh.
- Nếu cần danh tính **người dùng cuối**, backend vẫn phải có nguồn danh tính user được xác minh riêng; token từ APIM managed identity thường cho biết **APIM là caller**, không phải người dùng cuối.

### 10.3. API authorization theo operation

Ví dụ:

| Operation | Client role/scope minh họa | Backend business rule |
|---|---|---|
| `GET /orders/{id}` | `Orders.Read` | Người dùng có quyền xem đúng order ID |
| `POST /orders` | `Orders.Write` | User/tenant được tạo đơn, giá/stock hợp lệ |
| `POST /payments` | `Payments.Submit` | Kiểm tra tenant, idempotency, limit và chống gian lận |
| `GET /catalog/products` | Public hoặc `Catalog.Read` | Bỏ thông tin chưa công bố nếu cần |

Đặt `validate-jwt` ở API/operation scope phù hợp, nhưng **không** để APIM quyết định toàn bộ quyền row-level vì nó thường không có bối cảnh database. Backend vẫn là nơi enforce chính sách theo resource.

### 10.4. Key rotation và developer lifecycle

Một subscription key có thể bị lộ qua log, browser source, code repo hoặc partner integration. Quy trình quản trị nên:

1. Cấp key cho đúng consumer/application và scope; không dùng một key chung cho mọi đối tác.
2. Giới hạn access tới nơi hiển thị key; tránh gửi qua chat/email không bảo vệ.
3. Dùng primary/secondary key để luân chuyển không gián đoạn khi áp dụng được.
4. Theo dõi usage bất thường theo subscription/product/API.
5. Thu hồi key/consumer khi hợp đồng kết thúc hoặc credential bị lộ.
6. Đánh giá có nên dùng subscription key **cùng** OAuth token hay chỉ OAuth, theo threat model và APIM config.

## 11. API gateway và mạng riêng trên Azure

Một APIM instance có thể nằm trong nhiều kiến trúc mạng khác nhau, tùy SKU/cấp dịch vụ và tính năng. Cần phân biệt **gateway được client truy cập từ đâu** với **gateway được phép đi tới backend nào**.

### 11.1. Các kiến trúc điển hình

| Mô hình | Khi phù hợp | Điều cần kiểm tra |
|---|---|---|
| **Public APIM gateway → public backend có auth** | API public đơn giản/lab | TLS, backend auth, không để backend bị bypass |
| **Public gateway → private backend** | Consumer ngoài Internet nhưng backend chỉ trong VNet | APIM outbound VNet routing, DNS, NSG/firewall và SKU |
| **Private/internal gateway → private backend** | API nội bộ/doanh nghiệp | VNet, DNS private, client connectivity, VPN/ExpressRoute |
| **Front Door + WAF → APIM → backend** | Cần edge bảo vệ/đa vùng | Origin restrictions, hostname, TLS, WAF rules, routing |
| **Hybrid/self-hosted gateway** | Backend hoặc consumer on-premises/edge theo mô hình được hỗ trợ | Gateway deployment, control plane connectivity, policy feature parity |

**Không giả định mọi APIM SKU đều hỗ trợ cùng tính năng networking.** Classic tiers, v2 tiers và workspace gateways có khác biệt về VNet integration/injection, private endpoints, availability và regional behavior. Trước khi chọn SKU, cần kiểm tra tính năng đang được hỗ trợ ở region và loại gateway cụ thể.

### 11.2. Private DNS và kết nối backend

Nếu backend App Service chỉ được truy cập qua Private Endpoint, APIM phải có đường **outbound** đến private IP tương ứng và DNS resolve đúng:

~~~text
Partner/employee
      |
      v
APIM gateway
      |
      | HTTPS, authenticated backend access
      v
VNet connectivity + private DNS
      |
      v
Private Endpoint to App Service / Functions / SQL service
~~~

Một private endpoint inbound cho APIM **không tự cấp** đường APIM outbound tới private backend. Nếu gateway khác network/subscription, cần thiết kế VNet peering, routing, private DNS links, NSG/firewall và kiểm tra DNS từ runtime của gateway.

Đối với public gateway, phải bảo vệ **origin backend** để client không bỏ qua gateway khi backend URL cũng còn public. Có thể dùng private endpoint/network restrictions, backend authentication với APIM managed identity, certificate, allowlists theo kiến trúc; không tin rằng việc “không công bố URL backend” đủ bảo mật.

### 11.3. Custom domain và TLS

APIM gateway thường có hostname mặc định và có thể được cấu hình custom domain phù hợp, ví dụ `api.contoso.example`. Cần:

- Chứng chỉ TLS còn hiệu lực, được quản lý và rotate theo quy trình.
- DNS/CNAME/A record phù hợp mô hình gateway/edge.
- Chính sách TLS/HTTPS, SNI, hostname validation và backend TLS phù hợp.
- Tài liệu consumer chỉ dùng URL công khai ổn định, không lộ internal hostname.
- Quy trình thay domain/cert có rollback và cảnh báo trước ngày hết hạn.

Khi dùng Key Vault certificate, APIM identity phải được phép truy cập secret/cert material theo cơ chế được hỗ trợ; network Key Vault và lifecycle rotation cần kiểm tra. APIM không tự miễn trách nhiệm theo dõi chain/certificate expiration của tổ chức.

### 11.4. Workspace và self-hosted gateway

Ở những SKU/mô hình APIM hỗ trợ, **workspaces** giúp đội API quản lý tài nguyên trong phạm vi được ủy quyền; **self-hosted gateway** cho phép chạy gateway ở môi trường khác như Kubernetes/on-premises theo điều kiện của dịch vụ. Hai khả năng này có quyền, network, feature support và billing riêng.

Không đưa vào kiến trúc production chỉ vì tên tính năng có trên Portal: phải kiểm tra gateway policy compatibility, connectivity đến management plane, logs/diagnostics, region/tier, SLA, lifecycle upgrade, secret distribution và giới hạn hiện hành.

## 12. Developer portal, tài liệu và onboarding API consumer

Một API được triển khai nhưng không ai biết operation, schema, auth và error handling thì rất khó sử dụng. **Developer portal** của APIM có thể giúp developer khám phá các API/products được công bố, xem tài liệu và đăng ký subscriptions theo cấu hình instance/tier.

### 12.1. Thông tin cần có cho một API công bố

| Nội dung | Ví dụ cần mô tả |
|---|---|
| **Business purpose** | API cho biết đơn hàng, không cho phép thanh toán |
| **Base URL** | `https://api.contoso.example/orders/v1` |
| **Operations** | Methods, URL params, headers, request/response schemas |
| **Authentication** | Entra issuer/audience, scopes/app roles, subscription requirement |
| **Authorization** | Quyền nào được đọc order theo tenant/customer |
| **Limits** | Rate limit, quota, payload size, timeout, retry/backoff |
| **Errors** | 400, 401, 403, 404, 409, 429, 500, 503; error response contract |
| **Version lifecycle** | Current version, deprecation, sunset date và migration guide |
| **Support** | Owner, support channel, status page, incident escalation |
| **Examples** | Curl/SDK sample với placeholder, không chia sẻ token/key thật |

Một product published trên portal có thể hiển thị APIs theo chính sách visibility/authorization; phải thử **tài khoản consumer ít quyền** để xác nhận đúng danh mục và thông tin nhạy cảm không bị lộ. Portal tùy biến nội dung không thay thế policy runtime của gateway.

### 12.2. Quy trình onboarding đối tác

~~~mermaid
flowchart LR
    PARTNER[Partner developer] --> PORTAL[Developer portal / onboarding]
    PORTAL --> PRODUCT[Select API product]
    PRODUCT --> APPROVE[Contract + approval]
    APPROVE --> CREDS[Subscription credential + OAuth client setup]
    CREDS --> TEST[Sandbox tests]
    TEST --> PROD[Production access]
    PROD --> USE[Usage monitoring + rotation]
~~~

Điều kiện phát hành cho đối tác nên gồm:

1. Đã có hợp đồng và data-access agreement thích hợp.
2. Product/operations tương ứng với quyền thực sự cần.
3. Subscription approval/credential rotation theo chính sách.
4. Entra/oauth tenant/client configuration hoặc phương án identity phù hợp.
5. Sandbox không chứa PII/financial production data.
6. Rate limits, escalation và error-handling được kiểm thử.
7. Có monitoring theo consumer, audit và phương án revoke khi có sự cố.

**Không dùng một subscription key duy nhất cho tất cả partner clients** nếu cần truy vết/gỡ quyền độc lập. Và không công bố toàn bộ admin API chỉ vì một đối tác cần một endpoint đọc trạng thái.

## 13. Lab Azure CLI: tạo APIM instance và import Orders API

Lab sử dụng **Azure CLI trong Bash/Cloud Shell** và một OpenAPI document như ở phần 4.2. **Các lệnh trong bài chỉ dành cho subscription lab được phép**, không phải lệnh đã chạy trong lúc biên soạn. APIM instance có thể phát sinh chi phí đáng kể ngay khi được cấp phát; cần chọn SKU đúng mục đích và xóa đúng tài nguyên sau khi thực hành.

### 13.1. Điều kiện đầu vào

- Azure subscription có quyền tạo resource group và Azure API Management.
- Azure CLI đã đăng nhập và đúng tenant/subscription.
- Một địa chỉ email của nhóm sở hữu được cấp phép làm publisher contact.
- Một file OpenAPI hợp lệ, lưu ở thư mục lab, ví dụ `orders-openapi.yaml` chứa mẫu đã giới thiệu và được chỉnh cho backend test.
- Một backend HTTP/API thử nghiệm **thực sự tồn tại**, có thể trả GET order, không chứa dữ liệu production.
- Quyền được phép truy cập backend và cấu hình authentication/network; không dùng production secret.
- Quota/tier/region phù hợp và có ngân sách lab.

### 13.2. Đặt biến và xác nhận subscription

~~~bash
az login

SUBSCRIPTION_ID="<lab-subscription-id>"
RESOURCE_GROUP="rg-apim-lab"
LOCATION="southeastasia"
APIM_NAME="<globally-unique-apim-name>"
PUBLISHER_NAME="API Lab Team"
PUBLISHER_EMAIL="<approved-owner-email>"
API_ID="orders-v1"
API_PATH="orders/v1"
OPENAPI_PATH="./orders-openapi.yaml"

az account set --subscription "$SUBSCRIPTION_ID"
az account show \
  --query "{id:id,name:name,tenantId:tenantId}" \
  --output table
~~~

Các giá trị trong dấu `<...>` phải được thay bằng dữ liệu hợp lệ. `APIM_NAME` cần đáp ứng quy tắc tên/uniqueness và khả dụng tại region. Kiểm tra resource group/subscription có đúng là môi trường lab; đừng đưa chính sách mới vào APIM instance production dùng chung.

### 13.3. Tạo resource group và APIM instance

~~~bash
az group create \
  --name "$RESOURCE_GROUP" \
  --location "$LOCATION"

# Developer chỉ dành cho học tập/phát triển, không dùng cho production.
az apim create \
  --resource-group "$RESOURCE_GROUP" \
  --name "$APIM_NAME" \
  --location "$LOCATION" \
  --publisher-name "$PUBLISHER_NAME" \
  --publisher-email "$PUBLISHER_EMAIL" \
  --sku-name Developer
~~~

Việc provision APIM có thể mất một khoảng thời gian và có thể cần quota/cấu hình subscription cụ thể. **Developer SKU không dành cho workload production và không mang cùng cam kết SLA/tính năng như các production tiers.** Có nhiều dòng SKU như classic/v2 với feature availability khác nhau; phải kiểm tra tier cụ thể trước khi dùng networking/workspaces/availability zones.

Đọc lại resource:

~~~bash
az apim show \
  --resource-group "$RESOURCE_GROUP" \
  --name "$APIM_NAME" \
  --query "{name:name,location:location,provisioningState:provisioningState,sku:sku.name}" \
  --output json
~~~

Nếu lệnh `az apim show` hoặc `create` có khác biệt về options theo phiên bản CLI đang sử dụng, xem `az apim --help` và `az apim create --help`; không tự đổi sang SKU production đắt hơn chỉ để bỏ qua một lỗi cấu hình.

### 13.4. Chuẩn bị OpenAPI spec

Lưu nội dung OpenAPI mẫu ở phần 4.2 vào `orders-openapi.yaml` trong **repo lab do người học sở hữu**. Kiểm tra trước khi import:

- `openapi` version và YAML syntax đúng.
- Methods/paths/operation IDs không trùng.
- URL server và APIM public suffix được chọn **không gây route lặp**.
- `200/201/400/401/403/404/409` có schema/error documentation thích hợp.
- Không chứa credential, production hostname private hoặc thông tin dữ liệu cá nhân nhạy cảm.
- Backend test đã tồn tại và đáp ứng contract; import không tự tạo backend.

### 13.5. Import một API vào APIM

~~~bash
az apim api import \
  --resource-group "$RESOURCE_GROUP" \
  --service-name "$APIM_NAME" \
  --api-id "$API_ID" \
  --path "$API_PATH" \
  --specification-format OpenApi \
  --specification-path "$OPENAPI_PATH"
~~~

Cú pháp `--specification-format` và các formats/cách import từ file/URL phụ thuộc phiên bản CLI/API. Hãy kiểm tra `az apim api import --help` trong môi trường thật, và test spec trước. Sau import:

~~~bash
az apim api list \
  --resource-group "$RESOURCE_GROUP" \
  --service-name "$APIM_NAME" \
  --output table

az apim api show \
  --resource-group "$RESOURCE_GROUP" \
  --service-name "$APIM_NAME" \
  --api-id "$API_ID" \
  --output json

az apim api operation list \
  --resource-group "$RESOURCE_GROUP" \
  --service-name "$APIM_NAME" \
  --api-id "$API_ID" \
  --output table
~~~

Kiểm tra các operation có đúng method/path và không có path duplication. Nếu spec mô tả `/orders/{orderId}` còn APIM suffix là `orders/v1`, expected public route là `/orders/v1/orders/{orderId}`, không phải một URL chỉ được đoán theo tên API.

### 13.6. Cấu hình backend thực sự

Trong **Azure Portal → API Management → APIs → Orders API → Settings / Design**, chọn **Web service URL** tương ứng với backend test. Ví dụ một backend test có các endpoints:

~~~text
Public gateway:
  https://<apim-name>.azure-api.net/orders/v1/orders/INV-98421

Backend test:
  https://<orders-test-backend-domain>/api/orders/INV-98421
~~~

Nếu backend path khác public path, dùng rewrite-uri hoặc API settings phù hợp để chuyển chính xác URL. **Đừng đặt backend production URL vào một APIM Developer instance** chỉ để test: có thể tạo traffic thật hoặc truy cập dữ liệu thật.

APIM resource creation/import **không tự bảo đảm** một backend được kết nối và sẵn sàng. Trước khi nói “lab thành công”, kiểm tra DNS, HTTPS certificate, network access, backend response và auth cả hai phía.

### 13.7. Tạo product và quản lý subscriptions trên Portal

Trong Portal:

1. Vào APIM instance → **Products** và tạo một product thử nghiệm, ví dụ `sandbox-orders`.
2. Đặt display name, description, visibility/published state và yêu cầu subscription theo nhu cầu.
3. Thêm **Orders API** vào product.
4. Cấu hình nhóm users/developers có thể truy cập/đăng ký nếu cần.
5. Tạo/duyệt subscription test theo phương án được phép; lưu key trong secret store, không dán vào source code.
6. Kiểm tra gateway/API có yêu cầu key, JWT hoặc cả hai; thử cả requests có/không đủ credential.

Trên một APIM dùng chung, thêm API vào product hoặc đổi product visibility có thể thay đổi quyền truy cập của consumer khác. Vì vậy phải thử ở lab instance tách biệt và có người phê duyệt.

### 13.8. Gọi thử API

Nếu API yêu cầu subscription key:

~~~bash
GATEWAY_HOST="<apim-name>.azure-api.net"
ORDER_ID="INV-98421"
SUBSCRIPTION_KEY="<lab-subscription-key>"

curl -i \
  "https://$GATEWAY_HOST/orders/v1/orders/$ORDER_ID" \
  -H "Ocp-Apim-Subscription-Key: $SUBSCRIPTION_KEY"
~~~

Khi đã áp JWT validation, còn cần bearer **access token hợp lệ** dành cho API:

~~~bash
ACCESS_TOKEN="<valid-access-token-for-orders-api>"

curl -i \
  "https://$GATEWAY_HOST/orders/v1/orders/$ORDER_ID" \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -H "Ocp-Apim-Subscription-Key: $SUBSCRIPTION_KEY"
~~~

**Không copy các lệnh có token/key thật vào shared terminal history, CI logs hoặc ticket**. Sử dụng secret injection an toàn theo môi trường, redact kết quả trước khi chia sẻ. Đừng sử dụng bất kỳ token mẫu nào trong bài như credential thật.

Kết quả mong đợi tùy cấu hình:

| Kiểm thử | Kết quả dự kiến |
|---|---|
| URL đúng, token/key đúng và backend khỏe | Response 2xx theo contract |
| Thiếu subscription key khi yêu cầu | 401/403 hoặc thông báo tương ứng từ APIM |
| Token không hợp lệ/không đúng audience | 401 theo validate-jwt |
| Token hợp lệ nhưng không có role/permission | 401/403 theo policy và backend |
| Resource không tồn tại | 404 theo business contract |
| Rate limit vượt ngưỡng | 429 |
| Backend không thể kết nối | Lỗi gateway/backend như 502/503/504 tùy nguyên nhân |

**Không hardcode một HTTP status duy nhất cho mọi lỗi platform**. APIM, backend và các policies có thể trả status/error body khác nhau; quan trọng là client nhận đúng contract và logs đủ để xác định lỗi nằm ở đâu.

## 14. Tổ chức APIs ở quy mô nhiều nhóm, nhiều môi trường

Một APIM instance có thể chứa nhiều APIs, products, backends và policies. Khi tổ chức tăng quy mô, câu hỏi không chỉ là tạo bao nhiêu API mà còn là **ai được phép thay đổi cái gì**, làm sao giữ tiêu chuẩn bảo mật và tránh tác động chéo.

### 14.1. Mô hình phân chia quản trị

| Nhóm | Sở hữu | Không nên được phép |
|---|---|---|
| **Platform/API team** | APIM instance, gateway, base policies, networking, shared backend conventions | Đổi business logic/permissions nghiệp vụ tùy tiện |
| **Domain API team** | OpenAPI contract, operations, API-specific policies, backend version | Ghi đè global JWT/WAF/network policy không được duyệt |
| **Security team** | Auth standards, JWT/claims, certificate/secret policies, vulnerability review | Tự xóa API hay thay production route không qua change |
| **Partner enablement** | Products, onboarding docs, subscriptions và support | Cấp quyền admin backend hoặc mở API tài chính ngoài phạm vi |
| **SRE/On-call** | SLO, diagnostics, incident, rollback/runbook | Thay đổi permanent ngoài IaC/source of truth mà không reconciled |

Ở mô hình APIM workspaces có hỗ trợ, có thể ủy quyền phạm vi quản lý theo workspace; nếu không, cần Azure RBAC/custom roles, code ownership, pipeline gates và phân tách instance/resource groups hợp lý. **Workspace không tự biến mọi API thành một ranh giới network/security hoàn toàn riêng**; vẫn phải đánh giá gateway, identity, connectivity và hạn chế tier.

### 14.2. Tách environments

Một cách tổ chức:

~~~text
Subscription: app-dev
  APIM: apim-dev
    API: orders-v1 (dev backend)
    Product: sandbox (fake data)

Subscription: app-staging
  APIM: apim-staging
    API: orders-v1 (staging backend)
    Product: partner-uat

Subscription: app-prod
  APIM: apim-prod
    API: orders-v1, orders-v2
    Products: partner-basic, partner-premium, internal
~~~

Không phải tổ chức nào cũng cần ba APIM instances đầy đủ; chi phí, SLA, blast radius và feature availability quyết định. **Không dùng chung production credentials và database với sandbox** chỉ để tiết kiệm công cấu hình.

### 14.3. Taxonomy và metadata API

Mỗi API nên có metadata:

~~~yaml
# Ví dụ metadata quản trị trong repo, không phải một APIM resource schema
apiId: orders-v1
businessDomain: commerce.orders
ownerTeam: orders-platform
consumerTypes: [web, mobile, partner]
dataClassification: confidential
publicPath: orders/v1
backendService: orders-api
authMode: [entra-jwt, apim-subscription]
supportedVersions: [v1]
slo:
  availabilityTarget: "99.9% (mục tiêu nội bộ giả định)"
  latencyP95Ms: 500
onCall: orders-oncall
deprecationPolicy: "90-day notice (ví dụ)"
~~~

Metadata đó phục vụ catalog/audit, không thay thế APIM configuration. Các giá trị SLO/deprecation là **ví dụ giả định** cần thỏa thuận với chủ hệ thống và hợp đồng.

### 14.4. Product design theo mục tiêu và quyền

Thay vì product `Everything` gộp tất cả APIs, thiết kế từ **use cases**:

- `Shipping Tracking` chỉ những chức năng theo dõi giao hàng cần thiết, với scope/operation auth giới hạn.
- `Order Fulfillment` dành cho đối tác thực hiện đơn, có scopes mạnh hơn và quota riêng.
- `Catalog Public` cho dữ liệu công khai ít nhạy cảm, có cache/rate limit thích hợp.
- `Payments Internal` cho API tài chính, yêu cầu identity/network/audit chặt.

Nếu API operations có phạm vi quyền rất khác nhau, **tách APIs theo ranh giới bảo mật hoặc dùng authorization policy phù hợp** để product không vô tình cấp rộng. Hãy thử token/keys của từng consumer trên các endpoints không được phép.

### 14.5. Quản lý API lifecycle

Các giai đoạn nên có:

1. **Design:** chủ API, OpenAPI, threat model, error model, rate/quota.
2. **Develop/Test:** backend test, negative tests, policy tests, performance.
3. **Publish:** product và onboarding, auth credentials, docs.
4. **Operate:** SLO, monitoring, subscription usage, credential rotation.
5. **Evolve:** revisions, versions, backward compatibility, migration guides.
6. **Deprecate/Retire:** thông báo, đo traffic version cũ, khóa/xóa theo approval.

Không xóa API version cũ khi một số consumer vẫn gọi nó mà không có lộ trình migration. Với đối tác, cần có **deprecation window và liên lạc chính thức** theo hợp đồng.

## 15. CI/CD và Infrastructure as Code cho APIM

Khi số lượng APIs và policies tăng, sửa cấu hình bằng tay trong Portal dễ gây **configuration drift** giữa dev/staging/prod. Nên quản lý APIM definitions dưới dạng code và có một pipeline đảm bảo mọi thay đổi được kiểm thử, phê duyệt và có thể khôi phục.

### 15.1. Source of truth

Một cấu trúc repository ví dụ:

~~~text
api-platform/
├── apis/
│   ├── orders/
│   │   ├── openapi.yaml
│   │   ├── api-policy.xml
│   │   ├── operations/
│   │   │   └── get-order-policy.xml
│   │   └── versions/
│   │       └── v2-openapi.yaml
│   └── shipping/
│       ├── openapi.yaml
│       └── api-policy.xml
├── products/
│   ├── partner-basic.yaml
│   └── internal.yaml
├── infrastructure/
│   ├── main.bicep
│   └── parameters/
│       ├── dev.json
│       └── prod.json
├── tests/
│   ├── contract/
│   ├── policies/
│   └── security/
└── README.md
~~~

Đây là **mẫu cấu trúc học tập**, không phải yêu cầu tạo thêm files trong dự án bài học. Khi triển khai thực tế, có thể dùng Bicep/ARM/Terraform, APIM DevOps tooling được tổ chức duy trì hoặc Azure Resource Manager API, nhưng phải chọn **một nguồn điều khiển rõ ràng** cho từng cấu hình để tránh Portal và CI ghi đè qua lại.

### 15.2. Những gì cần nằm trong version control

- API contract (OpenAPI/GraphQL/SOAP metadata theo mô hình).
- API suffix, operations, policies (global/product/API/operation) và backend references.
- Products, associations, groups/visibility và subscription requirements **không chứa keys**.
- Named values **không nhạy cảm**; với secret dùng references vào Key Vault.
- Custom domain/network/identity/tier configs trong IaC theo phạm vi khả thi.
- Diagnostics, alerts, policy tests và release metadata.
- API versions/revisions cùng lịch deprecation.

**Không commit** APIM subscription keys, client secrets, certificate private keys hoặc thực token. Đối với secrets, lưu reference/identity binding có thể triển khai, còn secret value thuộc secret store được bảo vệ.

### 15.3. Pipeline thay đổi có kiểm soát

~~~mermaid
flowchart LR
    PR[Pull Request] --> LINT[OpenAPI / XML / IaC validate]
    LINT --> SEC[Security + API contract checks]
    SEC --> DIFF[What will change?]
    DIFF --> APPROVE[CODEOWNERS / approval]
    APPROVE --> DEV[Deploy to dev APIM]
    DEV --> TEST[Auth / contract / load tests]
    TEST --> PROD[Promote same config to prod]
    PROD --> OBS[Observe / rollback if needed]
~~~

Một pipeline nên phân biệt **deploy API contract** với **deploy backend application**. Thay OpenAPI hoặc policy `set-backend-service` không tự build code mới hoặc nâng cấp Azure SQL. Nếu backend/contract cần thay đồng thời, phải thiết kế thứ tự compatible: backend chấp nhận cũ và mới → thêm API version/revision → chuyển consumer → bỏ behavior cũ.

### 15.4. Policy tests và negative tests

Trước khi apply:

| Kiểm thử | Vì sao cần |
|---|---|
| XML policy well-formed/validate syntax | Tránh deployment fail do malformed XML |
| Có `<base />` phù hợp | Bảo toàn security policy kế thừa |
| Missing/wrong JWT | Bảo đảm policy chặn 401 đúng |
| Token đúng issuer nhưng sai audience | Bảo đảm không dùng token của API khác |
| Token không đủ role/scope | Bảo vệ operation nhạy cảm |
| Missing/invalid subscription key | Đúng product/API requirements |
| Rate limit và quota | Trả 429 khi đạt ngưỡng, không làm hỏng caller khác |
| Public/backend path mapping | Không rewrite sai path, query, HTTP method |
| PII/log redaction | Không log bearer token, account key, payment details |
| Cross-tenant/isolation | Consumer A không xem được order của consumer B |
| Backend outage | Client nhận lỗi phù hợp, alert có correlation |

**Đừng chỉ test happy path 200 OK.** Một API public quan trọng phải chứng minh hành vi 401, 403, 429, timeout, backend 5xx và version không còn hỗ trợ.

### 15.5. Rollback cấu hình

Khi policy mới gây 401 cho mọi client hoặc rewrite route sai:

1. Xác định commit/config thay đổi, scope và các operations bị ảnh hưởng.
2. Tạm dừng các lần promotion tiếp theo.
3. Revert policy/config bằng Git/IaC theo pipeline khẩn cấp hoặc chuyển về API revision cũ nếu cơ chế đó phù hợp.
4. Kiểm tra **effective policy**, backend URL và health ở gateway.
5. Gọi synthetic tests từ đúng loại client, quan sát 401/403/5xx/429 và business SLO.
6. Ghi incident và đồng bộ trạng thái cuối với source of truth.

Chỉnh trực tiếp Portal trong lúc khẩn cấp có thể cần thiết theo **break-glass** nhưng phải ghi lại và reconcile về Git sau đó; nếu không, IaC apply tiếp theo có thể ghi đè bản sửa khẩn cấp.

## 16. Quan sát API: metrics, logs, tracing và SLO

Một APIM instance có thể trả 200 ở gateway nhưng business transaction vẫn sai; ngược lại backend khỏe nhưng gateway policy có thể trả 401 do sai audience. Cần tách **gateway health, backend health và business correctness**.

### 16.1. Các lớp telemetry

| Lớp | Dữ liệu cần quan sát | Ví dụ tín hiệu |
|---|---|---|
| **Ingress/gateway** | Request count, latency, status by API/operation/product/region | 429 tăng chỉ với Partner Basic |
| **Policy/auth** | JWT validation failures, subscription key failures, transformation errors | 401 tăng sau rotate certificate/config |
| **Backend forwarding** | Backend latency, timeouts, TLS/DNS/network errors | APIM nhận 502/504 dù backend Pod Running |
| **Backend app** | Request traces, exception, dependency performance | SQL query p95 tăng |
| **Business** | Order success rate, payment completion, customer-facing SLO | POST thành công HTTP nhưng hóa đơn không được tạo |
| **Control plane** | Activity Log, policy deployments, role changes | Ai đổi rate limit hoặc public ingress |
| **Cost/capacity** | Gateway load, network egress, logs ingestion, tier capacity | Dư tải giờ cao điểm / overprovision |

### 16.2. Correlation và distributed tracing

API requests đi qua nhiều services nên cần correlation:

~~~text
Client request ID
    ↓
APIM gateway request ID / trace context
    ↓
Orders backend trace ID
    ↓
SQL query / Service Bus message correlation ID
    ↓
Application Insights / OpenTelemetry distributed trace
~~~

Ưu tiên dùng **W3C Trace Context** (`traceparent`/`tracestate`) trong hệ thống có instrumentation hỗ trợ, hoặc correlation ID thống nhất. Không tạo một header ID do client tự cung cấp rồi xem nó là bằng chứng danh tính/authorization. Với troubleshooting, nên giữ cả ID của client và ID được hệ thống kiểm soát tạo ra.

### 16.3. Diagnostics và sampling

APIM có khả năng xuất diagnostics/telemetry tới Application Insights và Azure Monitor theo cấu hình/tier hỗ trợ. Để vận hành an toàn:

1. Bật nguồn telemetry phù hợp (gateway logs, metrics, backend traces).
2. Xác định sampling theo traffic, yêu cầu audit và chi phí.
3. Redact/không thu `Authorization`, `Ocp-Apim-Subscription-Key`, cookies, request body nhạy cảm.
4. Chọn retention, access controls và dữ liệu khu vực theo chính sách.
5. Test thực sự có log với API, operation, response code, backend duration và correlation.
6. Tạo cảnh báo/owner; không giả định có Log Analytics workspace thì logs tự động xuất hiện.

Một request trả 401 do `validate-jwt` có thể không chạm backend; nếu chỉ nhìn Application Insights của backend sẽ bỏ sót. Ngược lại backend có thể lỗi sau khi APIM forward thành công; cần logs của cả hai phía.

### 16.4. SLO ví dụ

Giả định một API đọc đơn hàng có mục tiêu:

~~~text
Availability (user-facing): >= 99.9% theo thỏa thuận nội bộ
Latency p95: dưới 500 ms trong giờ hoạt động đã xác định
Error budget: do SLO owner quản lý
Contract errors 4xx hợp lệ: theo semantics, không tự tính thành outage
Payment/data errors: có business checks riêng
~~~

Các con số chỉ để minh họa, không phải SLA do Azure cam kết. Phải định nghĩa **request nào hợp lệ**, cách tính availability, vùng/route và maintenance window. Ví dụ 401 đối với token giả mạo thường là **hành vi đúng**, không nên tính như một availability failure của API.

### 16.5. Dashboard nên tách theo chiều nào?

- **API/operation:** GET read và POST write có latency/risks khác nhau.
- **Version:** v1 có thể tăng lỗi sau khi backend thay đổi dù v2 khỏe.
- **Product/subscription:** phát hiện đối tác nào vượt quota hoặc có traffic bất thường.
- **Backend:** lỗi 502/504 do một backend riêng.
- **Region/gateway:** sự cố mạng hoặc region-specific capacity.
- **Auth error category:** thiếu key khác token signature invalid khác thiếu role.
- **Business tenant/correlation (ẩn PII):** điều tra tác động mà không lộ dữ liệu.

Nếu một metric không cung cấp dimension mong muốn ở tier/kênh telemetry đang dùng, có thể bổ sung structured logs từ policy/backend theo cách hỗ trợ; **không tự giả định mọi metric đều có mọi dimension**.

## 17. Độ tin cậy, latency, retries và failover

Đặt APIM giữa client và backend tạo thêm một hop HTTP. Mục tiêu là kiểm soát tốt API mà không biến gateway thành single point of failure hoặc nguồn retry storm.

### 17.1. Timeout theo nhiều lớp

Một request có thể chịu các timeout khác nhau:

~~~text
Client HTTP timeout
    ↕
Edge/WAF/Front Door timeout (nếu có)
    ↕
APIM gateway backend forwarding timeout
    ↕
Backend application timeout
    ↕
SQL/external dependency timeout
~~~

Nếu backend mất 120 giây nhưng client chỉ chờ 15 giây, tăng timeout ở APIM lên 180 giây **không** giúp trải nghiệm client. Với tác vụ dài, cân nhắc API trả **202 Accepted**, ghi Queue Storage/Service Bus message, rồi cung cấp job-status endpoint hoặc webhook.

### 17.2. Retry cần idempotency và budget

Retry ở APIM/edge/client/backend có thể chồng lên nhau:

~~~text
Client retries 3 times
  × Gateway retries 3 times
    × Backend retries SQL 3 times
  = có thể khuếch đại nhiều nỗ lực xử lý
~~~

Không tự bật retry cho mọi `POST /payments`. Nếu request đã tạo thanh toán nhưng response bị mất, retry có thể tạo thanh toán trùng. Dùng **idempotency key**, database uniqueness, outbox/transactional handling và giới hạn retry/backoff/jitter. Với 429 cần tôn trọng `Retry-After` khi thích hợp.

### 17.3. Circuit breaker và backend pools

APIM có những khả năng quản lý **backend entities/pools** và chính sách/circuit breaker theo tier/tính năng được hỗ trợ. Một số kiến trúc có thể chuyển traffic giữa backend primary/secondary để giảm lỗi.

Điều kiện để failover có ý nghĩa:

1. Secondary backend thực sự khỏe và có đủ capacity.
2. Dữ liệu/database replication và semantics hoạt động theo RPO/RTO.
3. DNS/route/identity/certificate được kiểm tra ở đường failover.
4. Backend response contract tương thích.
5. Không mở flood traffic gây hỏng cả secondary.
6. Có quy trình failback và monitoring, không chỉ thay URL.

**Không coi set-backend-service giữa hai hostname là disaster recovery hoàn chỉnh.** Nếu cả hai backend dùng cùng một database đang outage, chuyển hostname không cứu được hệ thống.

### 17.4. Multi-region và high availability

APIM có các tùy chọn regional/availability khác nhau tùy SKU và tier. Một số production tiers hỗ trợ các khả năng vùng/zone; không suy rộng mọi tier đều có region replicas hoặc cùng SLA. Hãy kiểm tra:

- Gateway availability, zone redundancy và regional deployment thực tế.
- Azure Front Door/DNS failover, backend locality và latency.
- Dữ liệu đồng bộ, certificate/identity và network rules ở từng region.
- Diagnostic settings và secrets khi region/gateway thay đổi.
- RPO/RTO và runbook phục hồi nếu APIM control plane hoặc gateway gặp sự cố.

Một developer instance dùng để test **không là chiến lược dự phòng** cho production. Đối với API tài chính, cần mô hình DR đã được thử nghiệm định kỳ, không chỉ screenshot kiến trúc hai vùng.

## 18. Chọn APIM tier/SKU và chi phí

APIM có các dòng **classic** và **v2** (và các lựa chọn gateway/workspace liên quan) với khả năng khác nhau về SLA, scaling, network integration, workspaces, availability và chi phí. Mức giá, tên/tính năng SKU có thể thay đổi theo vùng và thời điểm. Không có một SKU mặc định đúng cho mọi mục tiêu.

### 18.1. Checklist chọn tier

| Tiêu chí | Câu hỏi cần đặt |
|---|---|
| **Môi trường** | Lab/dev hay production? Có SLA bắt buộc không? |
| **Lưu lượng** | Requests/giây, peak, payload size, policy complexity, latency budget? |
| **Network** | Gateway public/internal? Private backend? VNet integration/injection? |
| **Security** | Managed identity, Key Vault, mTLS, JWT policy, custom domains? |
| **Topology** | Một region hay nhiều regions/zones? DR RPO/RTO? |
| **Governance** | Có cần workspaces, self-hosted gateways, nhiều API teams? |
| **Operations** | Logging/diagnostics, tracing và capacity scale? |
| **Chi phí** | Fixed gateway/units, scaling, bandwidth, private networking, monitoring? |

**Developer tier** thường dành cho môi trường phát triển và thử nghiệm, không dùng cho production. Các tiers production có feature availability khác nhau, nhất là khi xét classic/v2. Cần xác minh **đúng SKU và region** hỗ trợ mọi yêu cầu trước khi thiết kế mạng hoặc triển khai IaC.

### 18.2. Các nguồn chi phí

| Khoản mục | Điều gì tạo chi phí |
|---|---|
| **APIM instance/tier/units** | Hạ tầng gateway theo pricing model/SKU, scaling |
| **Request processing** | Một số tiers/pricing models có thành phần request/capacity theo điều kiện |
| **Network** | NAT, Firewall, Private Endpoints, egress, liên vùng và edge WAF/Front Door |
| **Observability** | Application Insights/Log Analytics ingestion, retention, sampling |
| **Key Vault** | Secret operations, certificate lifecycle theo dịch vụ |
| **Backend compute/data** | App Service/Functions/AKS/SQL/Storage vẫn được tính phí |
| **CI/CD và testing** | Pipeline runners, scans, staging instance, load testing |
| **DR** | Region phụ, capacity dự phòng, backup và monitoring |

**APIM không làm backend hết tốn phí.** Một policy cache tốt có thể giảm request xuống backend; ngược lại logging body quá nhiều, retry không kiểm soát hoặc giữ nhiều environment/tier cao có thể tăng đáng kể chi phí.

### 18.3. Cách tối ưu

- Chọn SKU theo feature/SLO thực tế, không chọn tier cao nhất khi chưa có nhu cầu.
- Đặt APIM gần backend/region phù hợp để giảm latency và network transfer.
- Giới hạn diagnostics payload và retention; dùng sampling/tracing có mục đích.
- Tách môi trường phù hợp nhưng không nhân bản quá nhiều instances khi team nhỏ.
- Cache **chỉ** những dữ liệu có contract cho phép và không chứa PII.
- Dùng throttling/quota theo consumer để giảm abuse và bảo vệ backend.
- Dọn sandbox/test resources đúng owner và kiểm tra tài nguyên mạng/logs còn lại.
- Gắn tags owner/environment/application/costCenter; review ngân sách với Azure Cost Management.

**Budget alerts không phải hard spending cap**. Xóa API object mà giữ APIM instance có thể không làm biến mất phí gateway; phải xem toàn bộ resource billing và cách tính tier.

## 19. Troubleshooting APIM: 401, 403, 404, 429, 502 và 504

Khi consumer gọi API thất bại, không nên ngay lập tức sửa backend hoặc tắt `validate-jwt`. Hãy xác định lỗi nằm ở **client → gateway policy → backend network/auth → application → data service**.

### 19.1. Bảng triệu chứng

| Triệu chứng | Nguyên nhân có thể | Điều tra/cách xử lý |
|---|---|---|
| `401 Access denied due to missing subscription key` | Product/API/subscription yêu cầu key | Kiểm tra product association, subscription scope/key, header và renewal |
| `401 Unauthorized` từ `validate-jwt` | Token hết hạn, sai issuer/audience, signature/claims | Đối chiếu app registration, token type, OpenID metadata, scopes/roles |
| `403 Forbidden` | Token hợp lệ nhưng không đủ quyền, backend authorization hoặc network policy | Phân biệt APIM policy error và backend 403; kiểm tra resource permission |
| `404 Resource not found` | Sai API suffix, operation template, version hoặc backend route | Xem `api.path`, method/path, rewrite URI và backend URL |
| `429 Too Many Requests` | Rate limit/quota ở APIM hoặc backend | Xem counter key, limit window, product usage; backoff theo policy |
| `500` từ backend | Bug application, database exception, dependency | Backend logs/traces, request correlation, recent release |
| `502 Bad Gateway` | Gateway không nhận response hợp lệ từ backend, TLS hoặc backend connection lỗi | APIM gateway diagnostics, backend DNS/TLS, route và health |
| `503 Service Unavailable` | Backend/gateway quá tải hoặc không sẵn sàng | Gateway metrics, backend replicas, capacity, health |
| `504 Gateway Timeout` | Backend chậm, route không thông hoặc timeout policy | APIM/backend latency, DNS/network, timeout chain |
| `CORS error` trên browser | Allowed origin/header/method không khớp hoặc preflight/auth | Browser devtools, OPTIONS behavior, APIM CORS policy |
| Portal không hiển thị API/product | Chưa publish, group access, portal cache/config | Portal user permissions, products, visibility/approval |
| Subscription key đúng nhưng backend 401 | APIM key không được backend tin; backend cần JWT/managed identity | Kiểm tra APIM→backend auth riêng |
| APIM route gọi nhầm môi trường | Backend entity/named value/slot config sai | Azure activity/config diff, backend URL và environment |
| Policy thay ở operation không có tác dụng | Scope, kế thừa `<base />` hoặc policy order sai | Review effective policy/route, policy tester |
| Data leak qua cache | Cache key thiếu tenant/user hoặc nhầm cacheable response | Tắt cache, purge theo khả năng, incident security và sửa key |
| Certificate mới gây lỗi | TLS trust/SNI/hostname không khớp, Key Vault permissions | Certificate chain/expiry, DNS, backend hostname, MI |
| v2 API chạy nhưng v1 lỗi | Contract/backend schema không tương thích hoặc version mapping sai | Test từng version, migration status và deprecation rules |

**Không thay thế mã lỗi một cách tùy tiện** như biến mọi 401/403/429 thành 200 để “app chạy”. Điều này che giấu lỗi bảo mật và phá API contract cho client.

### 19.2. Runbook điều tra 8 bước

**Bước 1 — Xác nhận scope.** Đúng subscription, resource group, APIM instance, environment, API ID, version/revision, operation, hostname và timestamp chưa?

~~~bash
az account show --query "{id:id,name:name}" -o table

az apim show \
  --resource-group "$RESOURCE_GROUP" \
  --name "$APIM_NAME" \
  --query "{name:name,provisioningState:provisioningState}" \
  -o json

az apim api list \
  --resource-group "$RESOURCE_GROUP" \
  --service-name "$APIM_NAME" \
  --output table
~~~

**Bước 2 — Xác định client request.** HTTP method/path, query/headers có đúng contract? Có token/key không? Không đưa credential thật vào incident ticket.

**Bước 3 — Xem response gốc.** Status 401/403/404/429/5xx đến từ APIM policy hay backend? Đối chiếu gateway logs/correlation và thử endpoint tương ứng bằng client được phép.

**Bước 4 — Kiểm tra authentication/authorization.** Với 401 từ JWT, xem issuer/audience/expiration/scope/roles và policy kế thừa. Với key error, kiểm tra product/subscription scope, key status/rotation. Với 403 từ backend, kiểm tra quyền nghiệp vụ và backend identity.

**Bước 5 — Kiểm tra route/network.** APIM API suffix và operation mapping, backend URL, private DNS, VNet, firewall, TLS và backend readiness.

**Bước 6 — Kiểm tra policy changes.** Có ai vừa thay global/product/API/operation policy, named values hoặc backend entity? Có bỏ `<base />` gây mất kế thừa? Ghi nhận commit/config diff.

**Bước 7 — Đo mức ảnh hưởng.** Request error rate theo API/version/product/region, backend latency, lượng partner bị ảnh hưởng, business transactions thất bại.

**Bước 8 — Khôi phục bền vững.** Rollback policy/revision/route theo nguồn cấu hình, xác minh 2xx và negative auth tests, theo dõi business SLO rồi đóng incident.

### 19.3. Tình huống cụ thể: key hợp lệ nhưng 403

Một đối tác gửi `Ocp-Apim-Subscription-Key` đúng và nhận 403 khi đọc đơn hàng:

~~~text
Client holds an APIM product subscription
    ↓
Gateway accepts subscription key
    ↓
JWT check succeeds
    ↓
Backend checks order.customerId / token tenant
    ↓
Backend returns 403 (user not owner)
~~~

**Đây có thể là hành vi đúng.** Không cấp thêm APIM Contributor hoặc tắt backend authorization để xóa 403. Hãy xác nhận caller được phép truy cập **order ID đó** hay không.

### 19.4. Tình huống: v2 import tạo đường dẫn lặp

OpenAPI `servers.url` đã chứa `/orders/v2`, nhưng khi import, admin đặt API suffix `orders/v2` và đồng thời import paths `/orders/v2/orders`. Kết quả gateway kỳ vọng `/orders/v2/orders/v2/orders`, khiến client gọi theo tài liệu nhận 404.

Khắc phục: kiểm tra **public suffix + operation path + backend path**, chuẩn hóa contract một lần, test operations và cập nhật tài liệu. Đừng sửa cả APIM path và backend router một cách thiếu kiểm soát khiến client cũ bị phá.

### 19.5. Tình huống: rate limit chặn sai nhiều khách hàng

Một policy dùng `context.Request.IpAddress` làm counter key. Hàng trăm nhân viên ở cùng văn phòng đi qua NAT nên chia sẻ public IP và cùng bị 429.

Khắc phục: sau khi đã xác thực caller, chọn **client/application/tenant/subscription identifier đã kiểm chứng** làm counter key nếu phù hợp. Đừng tin một header `X-Customer-ID` do client tùy ý tự gửi để tính quota. Sau thay đổi, kiểm thử công bằng giữa nhiều consumers và xem hạn mức backend thực tế.

## 20. Case study: nền tảng API cho thương mại điện tử và đối tác logistics

**Bối cảnh giả định:** Một doanh nghiệp có API Orders trên App Service, API Catalog trên Azure Container Apps và API Payments trên AKS. Backend Azure SQL và Azure Service Bus nằm trong mạng riêng. Doanh nghiệp chuẩn bị công bố một phần API cho ba đối tác logistics, cho phép mỗi partner xem trạng thái vận chuyển nhưng không được xem lịch sử thanh toán hoặc dữ liệu của partner khác.

Các yêu cầu:

- Một hostname API công khai có HTTPS/TLS và WAF theo kiến trúc.
- Consumer phải có Entra/OAuth credential hoặc authentication phù hợp; đối tác có subscription riêng để quản usage.
- API v1 tiếp tục hoạt động trong khi v2 được thử nghiệm và chuyển đổi.
- Hạn chế 60 requests/phút theo từng partner cho endpoint đọc trạng thái, không dùng chung một IP counter.
- Payment API chỉ accessible cho những clients có scopes/roles đặc biệt và backend kiểm tra quyền nghiệp vụ.
- Không để partner bypass APIM gọi trực tiếp backend.
- Theo dõi 401/403/429/5xx, p95 latency và usage theo consumer.
- Có rollback policy/revision và kế hoạch dữ liệu tương thích.

### 20.1. Kiến trúc gợi ý

~~~mermaid
flowchart TB
    PARTNER[Partner apps] -->|HTTPS access token + subscription key| EDGE[Front Door / WAF]
    EMPLOYEE[Internal apps] -->|HTTPS access token| EDGE
    EDGE --> APIM[Azure API Management gateway]
    APIM --> POLICY[JWT + rate-limit-by-key + route]
    POLICY --> ORDERS[Orders API - App Service]
    POLICY --> SHIP[Shipping API - Azure Functions]
    POLICY --> CAT[Catalog API - Container Apps]
    POLICY --> PAY[Payments API - AKS private]
    ORDERS --> SQL[(Azure SQL)]
    SHIP --> BUS[(Azure Service Bus)]
    PAY --> SQL
    APIM -. Metrics / logs .-> MON[Azure Monitor / App Insights]
    KV[Key Vault] -. Secret/cert references .-> APIM
    ADMIN[Platform / API owners / Security] -. CI/CD + approval .-> APIM
~~~

**Sơ đồ là logic.** Private networking chỉ hoạt động khi APIM SKU hỗ trợ cấu hình mong muốn, VNet/private DNS/route và backend identities được cấp quyền. Front Door/WAF không mặc nhiên được bật khi tạo APIM; đó là một thiết kế tùy nhu cầu và chi phí.

### 20.2. Phân chia APIs và products

| API ID logic | Owner | API surface | Product |
|---|---|---|---|
| `shipping-v1` | Logistics | `GET /shipments/{id}` | Partner Tracking, Internal |
| `orders-read-v1` | Orders | `GET /orders/{id}/status` với dữ liệu tối thiểu | Partner Tracking |
| `orders-admin-v1` | Orders | `POST/PATCH /orders` | Internal Business |
| `catalog-v1` | Commerce | `GET /products` | Catalog Public, Internal |
| `payments-v1` | Payments | `POST /payments` | Internal Secure Payments |

**Vì sao tách Orders Read và Admin?** Để hạn chế exposure và bảo vệ operations nhạy cảm. Nếu giữ chung API với cả GET/POST, việc thêm API vào Partner Tracking product cần policies operation-level rất cẩn trọng; tách API surface thường giúp tránh cấp rộng khi gateway/product subscriptions có phạm vi khác nhau.

### 20.3. Authentication và authorization theo luồng

1. Partner application xin **access token** với audience/scope đúng cho API.
2. Partner gửi request và subscription key riêng; gateway validate JWT và key theo policy.
3. Rate limit counter dựa trên subscription ID/định danh caller đã kiểm chứng, không dùng IP chung.
4. APIM forward qua mạng phù hợp, sử dụng managed identity khi backend yêu cầu.
5. Shipping/Orders backend xác minh partner được xem **shipment/order đó**, tránh cross-tenant data leak.
6. Response chỉ trả fields cần thiết; không bao gồm payment details hoặc data classification không phù hợp.
7. Logs ghi request ID/partner ID đã được giảm nhạy cảm, API/operation/status, không ghi token/key.

### 20.4. Version v1/v2 và rollback

Giả sử v2 của Shipping API thay đổi cách biểu diễn trạng thái:

~~~json
{
  "shipmentId": "SHP-2026-101",
  "status": "in_transit",
  "estimatedDelivery": "2026-11-25"
}
~~~

Nếu v1 chỉ dùng `status: "on_the_way"` và client cũ không nhận `in_transit`, đây có thể là **breaking semantic change**. Hãy tổ chức v1/v2 trong API version set; giữ v1 đủ thời gian theo hợp đồng và phát migration guide. Nếu chỉ sửa mô tả hoặc thêm optional field, có thể dùng revision thay vì version.

Khi v2 gây lỗi, chuyển consumer về v1 **không** khôi phục dữ liệu nếu backend đã áp migration không tương thích. Cần kiểm tra response schema và dữ liệu trước khi cho phép rollback.

### 20.5. Quy trình go-live

1. Chủ API và security review OpenAPI, policies, versioning, partner use cases.
2. CI validate OpenAPI, policy XML, Bicep/Terraform, security negative tests.
3. Deploy dev/staging APIM, backend test và thông số mạng tương đương production.
4. Cấp sandbox subscriptions và token test cho từng partner; chạy contract tests.
5. Kiểm thử rate limit đúng từng subscription và role/operation restrictions.
6. Test failover/timeout và xác nhận backend không có public bypass path.
7. Phê duyệt promotion; triển khai API products và docs tới production.
8. Quan sát 401/403/429/5xx, latency, quotas và business success trong giai đoạn đầu.
9. Duy trì rollback plan, key rotation và hỗ trợ đối tác theo SLA hợp đồng.

### 20.6. Nếu gặp lỗi 401 diện rộng sau deploy policy

Giả sử một policy update đổi audience từ `api://orders-v1` sang `api://orders-v2` nhưng partner clients vẫn gọi v1. Mọi request hợp lệ trước đó bắt đầu trả 401.

Runbook:

1. Đóng băng promotion/config thay đổi thêm.
2. Xác định API scope/revision nào áp sai audience và các consumers ảnh hưởng.
3. Revert policy về audience hợp lệ đã phê duyệt qua Git/IaC hoặc restore revision phù hợp.
4. Không tắt JWT validation chỉ để có 200; đây là cổng bảo mật.
5. Test **valid v1 token**, invalid token, wrong tenant token và partner không được phép.
6. Theo dõi 401 drop, 5xx/latency và business API results; ghi sự cố và cập nhật tests ngăn tái diễn.

## 21. Bài thực hành tổng hợp: công bố API bằng APIM

**Đề bài:** Một công ty có hai backend thử nghiệm: `orders-api` với `GET /orders/{id}` và `POST /orders`, `shipping-api` với `GET /shipments/{id}`. Backend chạy trên App Service/Functions và có dữ liệu test. Công ty muốn công bố API cho đội nội bộ và một đối tác logistics, đồng thời cần JWT authentication, subscription usage tracking, versioning và khả năng rollback policy.

Chỉ thực hiện trên **subscription/resource group/APIM lab** đã được cấp phép. Không chạy các lệnh quản trị trên production hoặc sử dụng thông tin khách hàng/thanh toán thật trong bài thực hành.

### 21.1. Các yêu cầu

1. **Kiến trúc:** vẽ đường client → edge/WAF (nếu cần) → APIM → backend → Azure SQL/Service Bus. Phân biệt control plane/data plane.
2. **Tổ chức API:** chọn API IDs, public suffix, operations và người sở hữu cho Orders/Shipping.
3. **OpenAPI:** tạo tối thiểu ba operations có request/response/error schemas và operationId không trùng.
4. **Versioning:** chọn path/query/header cho v1/v2 và giải thích khi nào dùng revision.
5. **Product:** thiết kế `Partner Tracking` chỉ có quyền đọc trạng thái, `Internal Business` được tạo đơn. Nếu Orders API có cả GET/POST, mô tả cách tránh product cấp quá rộng.
6. **Subscription:** mô tả workflow đăng ký/duyệt, cấp key, hai keys để rotate và cách thu hồi khi partner rời hệ thống.
7. **Azure CLI:** tạo APIM Developer instance trong RG lab, import OpenAPI, liệt kê API/operations và kiểm chứng backend.
8. **JWT:** thêm policy validate issuer/audience và quyền `Orders.Read` cho đúng operation. Test thiếu token, expired token, wrong audience, valid token và thiếu role.
9. **Throttling:** đặt giới hạn minh họa `60 calls/60s` theo subscription, lý giải vì sao không dùng IP nguồn khi nhiều partner dùng chung NAT.
10. **Backend routing:** thiết kế set-backend-service/rewrite-uri nếu public path khác backend path; test query/path parameters không bị mất.
11. **CORS:** chỉ cho phép origin thử nghiệm cụ thể; giải thích vì sao curl vẫn có thể gọi khi browser bị chặn CORS.
12. **Mạng riêng:** nếu backend chỉ có Private Endpoint, liệt kê VNet, DNS, route, SKU feature và backend auth cần có.
13. **Managed identity:** thiết kế APIM gọi backend với token audience đúng, phân biệt với access token user.
14. **Developer portal:** mô tả product discovery, docs, subscription approval, authentication và sandbox data.
15. **Observability:** định nghĩa dashboard phân tách 401/403/429/5xx, p95, backend latency, version và subscription.
16. **Rollback:** một policy mới làm mọi request trả 401. Viết runbook revert config/revision, validate negative tests và giám sát.
17. **FinOps:** liệt kê gateway SKU/units, network, monitoring, backend compute và tài nguyên lab cần xóa sau bài.
18. **Governance:** xác định API owner/platform/security/partner enablement responsibilities và CODEOWNERS/review gates.

### 21.2. Ma trận quyền tham khảo

| Consumer | `GET /shipping` | `GET /orders/{id}` | `POST /orders` | `POST /payments` |
|---|---|---|---|---|
| **Partner logistics** | Cho phép với đúng shipment | Chỉ order được ủy quyền | Từ chối | Từ chối |
| **Internal order app** | Theo role được cấp | Theo quyền nội bộ | Cho phép theo `Orders.Write` | Từ chối nếu thiếu Payments role |
| **Payment service** | Không mặc định | Khi cần theo least privilege | Không mặc định | Cho phép theo chính sách riêng |
| **Unknown caller** | Từ chối | Từ chối | Từ chối | Từ chối |

*Lưu ý:* `GET /shipping` trong bảng là cách viết gọn; API thực tế dùng contract rõ như `GET /shipments/{id}`. Từng ô “Cho phép” còn phụ thuộc valid token, subscription và **resource-level authorization ở backend**. Không chỉ kiểm tra role chung rồi cho partner đọc bất kỳ order của khách hàng khác.

### 21.3. Kết quả kiểm tra dự kiến

~~~text
Case A: missing required key
    → request bị chặn ở gateway

Case B: key valid, JWT missing
    → validate-jwt chặn request

Case C: JWT valid, audience wrong
    → token không được chấp nhận

Case D: JWT valid, role Orders.Read, wrong order owner
    → backend trả 403

Case E: token/key valid, resource permitted, backend healthy
    → trả response thành công theo OpenAPI contract

Case F: consumer vượt rate limit
    → HTTP 429, client phải retry có backoff

Case G: APIM không kết nối được private backend
    → lỗi network/gateway, kiểm tra DNS và tuyến outbound

Case H: đổi policy sai audience
    → revert bằng Git/approved revision, kiểm chứng token hợp lệ vẫn được phép
~~~

### 21.4. Câu hỏi suy luận

**Câu 1.** Product Partner Tracking đã thêm `Orders API` có operations đọc và tạo đơn. Đối tác có product subscription key. Có chắc đối tác không gọi được `POST /orders`?

*Gợi ý:* Không. Việc thêm API vào product không mặc nhiên lọc operation theo tên product. Cần thiết kế API tách ranh giới quyền hoặc policy kiểm soát JWT scopes/roles/operation, và test trực tiếp.

**Câu 2.** Token từ một tenant Entra hợp lệ nhưng audience là Graph API. Nó có nên được dùng để gọi Orders API?

*Gợi ý:* Không. API cần access token có audience dành cho **Orders API**, issuer/claims và chính sách quyền phù hợp; một token hợp lệ về chữ ký không tự hợp lệ cho mọi API.

**Câu 3.** APIM Developer instance đã kết nối backend qua hostname public. Chuyển backend sang Private Endpoint nhưng không thay networking của gateway. Điều gì có thể xảy ra?

*Gợi ý:* APIM có thể không phân giải hoặc route đến private IP, gây 502/503/504 tùy tình huống. Phải chọn APIM tier/topology có hỗ trợ outbound private connectivity, cấu hình VNet/private DNS/route và kiểm tra TLS/identity.

**Câu 4.** CI cập nhật backend v2 và tự xóa cột DB mà v1 còn đọc. API v2 bị lỗi, bạn revert APIM revision về v1. Đã rollback thành công chưa?

*Gợi ý:* Chưa. API route/policy cũ không làm cột database xuất hiện lại; cần migration tương thích hoặc khôi phục dữ liệu với runbook đã đánh giá RPO/RTO.

**Câu 5.** Gateway log có 30.000 request 401 trong một phút. Tất cả có nghĩa API outage?

*Gợi ý:* Không. Một đợt request không có token/hacker scan có thể bị chặn đúng policy. Cần xem lỗi trên traffic **hợp lệ**, business SLO, auth error category và sự kiện deploy mới.

### 21.5. Tiêu chí hoàn thành

Bài đạt khi người học:

- Xác định được **API contract và public route** nhất quán với backend.
- Mô tả đúng khác biệt **API, operation, product, group, subscription, version, revision và policy scopes**.
- Chứng minh request có key/JWT đúng thì vào backend và không có quyền thì bị chặn.
- Nêu cách tránh product cấp quá rộng cho operation nhạy cảm.
- Kiểm chứng kết nối private backend, identity và diagnostics mà không lộ secrets.
- Có quy trình CI/CD và rollback **cả policy lẫn business/data dependencies**.
- Đưa ra một dự toán chi phí theo SKU/topology và phương án cleanup an toàn.

## 22. Checklist triển khai APIM theo môi trường

### 22.1. Trước khi tạo API hoặc product

- [ ] Xác nhận đúng subscription, resource group, APIM instance/SKU, environment và owner.
- [ ] Phân loại API public/partner/internal/admin theo dữ liệu và consumer.
- [ ] Có OpenAPI contract, path, method, status/error model, versioning và SLO.
- [ ] Xác định backend thật, health endpoint, auth, network và cách triển khai rollback.
- [ ] Kiểm tra SKU hỗ trợ private networking, workspaces, certificates, region/availability theo yêu cầu.
- [ ] Đã tạo threat model cho OAuth scopes/roles, subscription keys và backend resource authorization.
- [ ] Có chính sách secrets/certificates dùng Key Vault/managed identity khi thích hợp.
- [ ] Cấu hình APIM instance/tài nguyên bằng IaC hoặc source of truth rõ ràng.

### 22.2. Trước khi publish

- [ ] Validate OpenAPI và mapping public suffix + operation path + backend route.
- [ ] Policies XML hợp lệ; effective policies kế thừa `<base />` đúng.
- [ ] Test missing/invalid JWT, issuer/audience, wrong role/scope và subscription key.
- [ ] Test từng operation sensitive, không cho product vô tình cấp quyền rộng.
- [ ] CORS và caching được kiểm chứng, không lộ dữ liệu giữa tenants.
- [ ] Product visibility, group access, approval/subscription scope đúng.
- [ ] Developer portal docs có auth/limits/error/deprecation/support rõ.
- [ ] Backend private endpoint/DNS/route/TLS/identity được kiểm thử từ gateway.
- [ ] Rate limits/quotas theo identity đã xác thực, không chỉ IP NAT.
- [ ] Log redaction, alert owner, tracing và SLO monitoring đã hoạt động.
- [ ] Có production approval, rollback path và data migration compatible.

### 22.3. Sau khi publish

- [ ] Xác minh request 2xx từ consumer hợp lệ ở gateway và backend.
- [ ] Negative tests 401/403/429 và resource-level authorization vẫn đạt.
- [ ] Error rate, p95/p99, backend latency và quota theo API/product/version ổn định.
- [ ] Subscriptions/keys được cấp theo từng consumer, có rotation và revoke process.
- [ ] Không có backend public bypass path hoặc origin policy sai.
- [ ] Theo dõi certificate/secret expiration, JWT discovery/issuer settings và logs.
- [ ] Ghi deployment commit, API revision/version và change record.
- [ ] Review usage/cost, API deprecation và subscriptions không còn dùng.

### 22.4. Khi xảy ra sự cố

- [ ] Đóng băng promotion, ghi API/operation/version, timestamp và correlation ID.
- [ ] Phân biệt 401/403/404/429/5xx từ APIM hay backend; không tắt security tùy tiện.
- [ ] So effective policy, backend route, Azure Activity Log và CI diff gần nhất.
- [ ] Nếu là lỗi config, revert approved policy/revision và cập nhật source of truth.
- [ ] Nếu là lỗi backend/DB, kích hoạt runbook ứng dụng/dữ liệu, không chỉ đổi gateway.
- [ ] Test lại token hợp lệ, token sai audience, consumer thiếu scope và business cases.
- [ ] Ghi incident, ảnh hưởng consumer, recovery time và hành động phòng ngừa.

## 23. Dọn dẹp lab an toàn

APIM instance và các tài nguyên network/logging có thể tiếp tục tính phí dù không có requests. Trước khi xóa:

1. Xác nhận đúng subscription/resource group.
2. Liệt kê APIM instance, custom domains, identities, Key Vault, private endpoints, Log Analytics và các backends liên quan.
3. Kiểm tra resource group có chứa ứng dụng/tài nguyên dùng chung của team khác không.
4. Xác định products/subscriptions test có đang được consumer nào dùng thực tế không.
5. Lưu logs/bằng chứng cần giữ theo chính sách; không lưu keys/token.
6. Chỉ xóa **resource group hoàn toàn dành cho lab** và đã được người sở hữu phê duyệt.

~~~bash
az account show --query "{id:id,name:name}" --output table

az resource list \
  --resource-group "$RESOURCE_GROUP" \
  --output table

# Ví dụ xóa chỉ để tham khảo, KHÔNG tự chạy.
# Chỉ dùng nếu 100% RG là của lab và đã được phê duyệt:
# az group delete --name "$RESOURCE_GROUP" --yes
~~~

Nếu APIM lab nằm trong RG dùng chung, cần **chọn đúng resource** để dọn thay vì xóa nguyên RG. Việc xóa instance sẽ ảnh hưởng tất cả APIs, products, developer portal, subscriptions và gateway endpoints trong instance đó. Trước khi xóa, xác nhận không có client đang sử dụng và tuân thủ retention/audit requirements.

**Không xóa một Key Vault, storage account hoặc network resource chỉ vì nó được tạo cùng ngày với APIM.** Phải dựa trên ownership và resource dependencies thực tế.

## 24. Ghi nhớ

**Azure API Management** là lớp quản trị và công bố APIs, gồm **gateway, management, developer portal, policies và observability**. Thiết kế tốt bắt đầu từ API contract và consumer needs, rồi mới cấu hình URL và sản phẩm trên Portal.

Những điểm cốt lõi:

1. **Tổ chức API theo domain:** API → operations; products gom API offerings, groups/subscriptions quản onboarding và usage; quyền product không mặc nhiên giới hạn từng HTTP operation.
2. **Version và revision khác nhau:** version dùng cho hợp đồng không tương thích; revision phù hợp thay đổi không phá vỡ contract trong cùng API/version.
3. **Policies có scope và thứ tự:** inbound/backend/outbound/on-error; `<base />` quyết định kế thừa policies từ scope cao hơn, cần review effective policy.
4. **Keys khác token:** APIM subscription key phục vụ quản lý subscription/usage, không thay OAuth/JWT user identity hoặc backend resource authorization.
5. **Managed identity cho backend:** APIM có thể lấy token để gọi backend an toàn, nhưng không tự nhân danh user cuối.
6. **Mạng có nhiều chặng:** client → gateway và gateway → backend là hai luồng riêng; private DNS/VNet/networking cần phù hợp APIM SKU/tier.
7. **Tài liệu và onboarding:** OpenAPI, developer portal, products, subscription approval, rate limits và error model phải thống nhất.
8. **Vận hành theo source of truth:** IaC/CI/CD, negative tests, diagnostics, correlation, SLO và rollback policy/revision có kiểm soát.
9. **APIM không thay business logic/DR:** vẫn phải bảo vệ backend, database, credentials, dữ liệu và kiến trúc phục hồi.
10. **FinOps:** chi phí phụ thuộc gateway tier/capacity, mạng, monitoring và backends; chọn theo yêu cầu thực tế, tránh giữ APIM lab không dùng.

Đừng chỉ hỏi **“API đã xuất hiện trong APIM chưa?”**. Một API chỉ thực sự sẵn sàng khi consumer tìm thấy contract đúng, gọi được qua hostname an toàn, được xác thực và phân quyền chính xác, backend đáp ứng SLO, phiên bản có lộ trình thay đổi và đội vận hành có bằng chứng để chẩn đoán/khôi phục khi lỗi.
