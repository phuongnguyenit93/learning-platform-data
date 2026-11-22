# Policy xác thực JWT và bảo vệ backend API

Trong module **CLOUD_PROVIDERS_AZURE**, chúng ta tìm hiểu hệ sinh thái Microsoft Azure từ subscription, resource group và Microsoft Entra ID đến mạng ảo, dịch vụ tính toán, lưu trữ và dữ liệu. Mục tiêu không chỉ là triển khai ứng dụng lên Azure mà còn biết **giám sát, bảo vệ và kiểm soát chi phí** của một kiến trúc thực tế. Ở chương **API và tích hợp quy trình**, bài học này tập trung vào cách dùng **Azure API Management (APIM)** để kiểm tra JSON Web Token (JWT), áp dụng policy kiểm soát truy cập và bảo vệ **backend API**, kết hợp xác thực/phân quyền của ứng dụng và các lớp bảo mật mạng.

Giả sử hệ thống đặt hàng có một **Java REST API** chạy trên Azure App Service hoặc Azure Kubernetes Service. Ứng dụng web gọi `GET /orders` để đọc đơn và `POST /orders` để tạo đơn. Một worker nội bộ gọi `POST /orders/reconcile` để đối soát. Ba kiểu caller có quyền khác nhau, nhưng tất cả đều đi qua API Management. Nếu gateway chỉ kiểm tra token có chữ ký hợp lệ mà **không kiểm tra audience, issuer, quyền truy cập và nguồn caller**, API có thể bị sử dụng bằng token không dành cho nó. Nếu backend lại mở trực tiếp cho Internet và bỏ qua xác thực, kẻ tấn công có thể bỏ qua toàn bộ policy ở gateway.

Sau bài học, bạn có thể:

- Phân biệt **JWT**, **OAuth 2.0 access token**, **OpenID Connect ID token**, authentication và authorization.
- Giải thích vì sao phải xác minh **chữ ký, issuer, audience, expiration, not-before** cùng **scope/role**.
- Thiết lập policy **`validate-jwt`** của APIM dùng OpenID Connect discovery/JWKS với Microsoft Entra ID.
- Thiết kế policy theo **API/operation**, **delegated scopes (scp)** và **application roles (roles)** mà không cấp quyền quá rộng.
- Hiểu inheritance của policy ở **global, product, API và operation scope**, tránh vô tình cho phép một operation bỏ qua kiểm tra.
- Phối hợp gateway với **authentication ở backend**, managed identity/mTLS và network isolation.
- Áp dụng rate limiting, request validation, hạn chế CORS, quản trị secrets, TLS và diagnostic logging.
- Kiểm thử các tình huống token sai/hết hạn/không đủ quyền, backend bypass và thiết kế runbook production.

## 1. Bức tranh tổng thể: API Management đứng ở đâu?

**Azure API Management** cung cấp gateway, mặt phẳng quản lý API và trải nghiệm developer-facing theo tier/cấu hình. Ở đây, gateway nhận request của client rồi áp dụng **policy** trước khi chuyển tiếp đến backend đã được cấu hình.

```text
Browser / mobile app                Background job
      |                                   |
      | OAuth2 Authorization Code + PKCE  | Client Credentials
      v                                   v
  Microsoft Entra ID                 Microsoft Entra ID
      |                                   |
      +----------- JWT access token ------+
                       |
                       | Authorization: Bearer <access-token>
                       v
                Azure API Management
                +----------------------+
                | validate-jwt         |
                | validate claims      |
                | rate limit / quota   |
                | request validation   |
                | route to backend     |
                +----------------------+
                       |
                       | Backend authentication + private networking
                       v
              Orders Java API / backend
                       |
                 Azure SQL / Storage
```

Luồng này có **ít nhất ba ranh giới bảo mật**:

1. **Client → Identity Provider:** người dùng hay ứng dụng được Microsoft Entra ID xác thực và nhận access token có quyền phù hợp.
2. **Client → APIM:** gateway kiểm tra token và policy của từng API/operation, từ chối request không hợp lệ trước khi gửi tới backend.
3. **APIM → backend:** backend chỉ nhận traffic được phép, xác minh danh tính/ủy quyền của caller theo thiết kế, không phụ thuộc tuyệt đối vào việc client luôn đi qua APIM.

**APIM không tự làm backend thành private hoặc an toàn.** Policy ở gateway không bảo vệ request đi thẳng tới URL của backend nếu backend có đường public không được hạn chế.

### 1.1. API Management là gateway, không phải Identity Provider

APIM **không** thay thế Microsoft Entra ID hoặc hệ thống phát hành token. Trong kiến trúc phổ biến, Entra ID là **issuer** của JWT; APIM là bên **xác minh** và áp policy; Java API là **resource server** phục vụ nghiệp vụ. API có thể tiếp tục kiểm tra token và business authorization ở tầng ứng dụng.

### 1.2. Khi nào cần mô hình này?

| Tình huống | Giá trị của APIM | Lớp bổ sung cần lưu ý |
|---|---|---|
| Nhiều ứng dụng dùng cùng một backend API | Policy nhất quán, routing, versioning, quota và diagnostics | Backend RBAC và object-level authorization |
| Mobile/web app gọi API | Kiểm tra bearer access token, scope theo operation | OAuth2 code + PKCE, CORS đúng origin |
| Daemon gọi API | Kiểm tra app roles và caller app identity | Client credentials, credential/federation và least privilege |
| Public API cần hạn chế abuse | Rate limit, request validation, WAF ở edge khi phù hợp | DDoS/edge, bot defense, security monitoring |
| Backend chỉ nên nhận từ gateway | Kiểm soát mạng và service-to-service identity | Private endpoint, VNet routing, mTLS/managed identity |

Không phải hệ thống nào cũng cần APIM: API nhỏ nội bộ có thể đủ với các lớp xác thực ứng dụng và networking trực tiếp. Khi số API/caller/policy tăng, gateway giúp tập trung quản trị nhưng cũng làm phát sinh **chi phí, độ trễ, phụ thuộc hạ tầng và rủi ro cấu hình chung**.

## 2. JWT là gì và có những gì bên trong?

**JSON Web Token (JWT)** theo định dạng compact phổ biến gồm ba phần được mã hóa Base64URL, ngăn cách bởi dấu chấm:

```text
BASE64URL(header).BASE64URL(payload).BASE64URL(signature)
```

Ví dụ payload **giả lập** của một access token:

```json
{
  "iss": "https://login.microsoftonline.com/<tenant-id>/v2.0",
  "aud": "api://<orders-api-app-id>",
  "sub": "<subject>",
  "tid": "<tenant-id>",
  "scp": "orders.read orders.write",
  "iat": 1795150000,
  "nbf": 1795150000,
  "exp": 1795153600
}
```

**Đây không phải JWT thật**: phần payload trên không chứa chữ ký. Không sao chép vào test rồi kỳ vọng APIM chấp nhận. Trong token thực, các claim tùy token version, tenant, grant type và cấu hình API; không phải lúc nào cũng có cả `scp` và `roles`.

### 2.1. Header, payload, signature

| Thành phần | Ví dụ | Ý nghĩa |
|---|---|---|
| JWT header | `alg`, `kid`, `typ` | Thuật toán chữ ký, khóa dùng để ký, thông tin loại token |
| JWT payload | `iss`, `aud`, `exp`, `nbf`, `scp`, `roles` | Claims bên phát hành công bố về token/caller |
| JWT signature | Giá trị chữ ký số | Bên xác minh kiểm tra token không bị sửa và được ký bằng khóa tin cậy |

**Base64URL không phải mã hóa nội dung.** Người có token có thể giải mã payload nếu đó là signed JWT thông thường; tuyệt đối không đặt password, key hoặc dữ liệu bí mật vào custom claims chỉ vì token có chữ ký.

### 2.2. Những claim cơ bản phải xem xét

| Claim | Ý nghĩa | Kiểm tra cần có |
|---|---|---|
| `iss` | Issuer phát hành token | Khớp issuer được tin cậy, gồm tenant/token version phù hợp |
| `aud` | Audience – tài nguyên nhận token | Khớp **đúng API backend** chứ không phải SPA hoặc API khác |
| `exp` | Hết hạn | Từ chối khi token hết hạn, ngoại trừ clock skew nhỏ có chủ đích |
| `nbf` | Không hợp lệ trước thời điểm | Từ chối token trước thời điểm hiệu lực |
| `iat` | Thời điểm phát hành | Có ích cho auditing/kiểm tra thời gian, không thay `exp` |
| `tid` | Tenant identifier trong token Microsoft Entra | Có thể dùng để khóa tenant trong mô hình phù hợp |
| `sub` | Subject | Một định danh trong ngữ cảnh token; không mặc định là khóa người dùng toàn cầu |
| `oid` | Object ID của principal trong Entra theo loại token | Dùng khi cần nhận diện principal kết hợp tenant, không thay phân quyền |
| `azp` hoặc `appid` | ID ứng dụng client tùy token version | Dùng allowlist caller được phê duyệt khi threat model yêu cầu |
| `scp` | Delegated scopes | Kiểm tra quyền thay mặt người dùng cho operation cụ thể |
| `roles` | App roles | Kiểm tra application permissions hoặc vai trò được khai báo |

**Không dựa chỉ vào `sub`, `oid`, `email` hoặc `preferred_username` để cấp quyền gọi mọi API.** Chữ ký hợp lệ chỉ chứng minh các claims thuộc token đã được issuer ký; authorization vẫn phải kiểm tra **quyền và phạm vi nghiệp vụ**.

### 2.3. JWT hợp lệ về chữ ký chưa đủ

Một JWT do Microsoft Entra ID ký có thể:

- Dành cho **Microsoft Graph** thay vì Orders API (`aud` sai).
- Được phát hành từ **tenant khác** mà Orders API không tin cậy (`iss`/tenant sai).
- Đã hết hạn hoặc chưa tới thời điểm hiệu lực.
- Không có `orders.write` nhưng caller cố gọi `POST /orders`.
- Có role chỉ dành cho một backend khác hoặc app không được phê duyệt.

Do đó, **xác thực token** và **kiểm tra quyền** là hai lớp riêng, dù có thể cấu hình cùng một `validate-jwt` policy.

## 3. OAuth 2.0 access token khác OIDC ID token thế nào?

Client có thể nhận nhiều loại token, nhưng **backend API phải kiểm tra access token dành cho API đó**.

| Loại | Audience chính | Cách dùng |
|---|---|---|
| **ID token** | Ứng dụng client dùng để đăng nhập, chẳng hạn SPA | Chứng minh authentication của người dùng với client; không phải bằng chứng quyền gọi Orders API |
| **Access token** | Resource/API mà client được phép gọi | Gửi ở `Authorization: Bearer`; API kiểm tra chữ ký, claims và quyền |
| **Refresh token** | Dùng trong OAuth token lifecycle tại client hợp lệ | Không gửi tới Orders API để truy cập tài nguyên |

Trong ứng dụng web/mobile public client, hướng tiếp cận tiêu chuẩn là **OAuth 2.0 Authorization Code + PKCE** với thư viện nhận diện phù hợp. **Không** khuyến khích Resource Owner Password Credentials hay nhúng client secret vào JavaScript của browser.

Với job/daemon không có người dùng, **Client Credentials** dùng application identity và permissions/app roles phù hợp. Đừng gán giả một delegated `scp` của người dùng cho một token app-only.

### 3.1. Delegated scopes và application roles

Ví dụ Orders API công bố:

- Delegated scope: `orders.read`, `orders.write`.
- Application role: `Orders.Reconcile` cho daemon đối soát.

Quy tắc nghiệp vụ:

| Operation | Caller | Claim cần kiểm tra |
|---|---|---|
| `GET /orders` | Người dùng qua web/mobile | `scp` chứa `orders.read` hoặc quyền khác được chính sách chấp nhận |
| `POST /orders` | Người dùng qua web/mobile | `scp` chứa `orders.write` |
| `POST /orders/reconcile` | Daemon nội bộ | `roles` chứa `Orders.Reconcile`, và cân nhắc allowlist caller app |

Đây là **một mô hình thiết kế cụ thể**; hệ thống khác có thể dùng app roles cho người dùng hoặc kết hợp các cơ chế, nhưng phải tài liệu hóa cách phân biệt user-delegated và app-only. Không dùng một câu điều kiện mơ hồ “có `scp` **hoặc** `roles` bất kỳ” cho mọi operation.

### 3.2. Audience phải lấy từ token thật và cấu hình App Registration

Khi đăng ký API với Entra ID, ứng dụng có **Application (client) ID** và có thể có **Application ID URI** như `api://<orders-api-app-id>`. Giá trị `aud` thực tế của access token có thể là **client ID dạng GUID** hoặc **URI** tùy token/API configuration.

Vì thế hãy đối chiếu access token được cấp **đúng cho API** với App Registration và policy APIM; không tự đoán rằng mọi token hợp lệ đều có `aud = api://...`.

### 3.3. Tenant và token version

Microsoft Entra ID có thể phát hành access token với issuer khác nhau giữa **v1 và v2**, phụ thuộc cấu hình resource token version. Ví dụ issuer có thể có dạng:

```text
https://login.microsoftonline.com/<tenant-id>/v2.0
https://sts.windows.net/<tenant-id>/
```

Không dùng endpoint `/common` làm ranh giới tin cậy mơ hồ cho API **single-tenant** nếu không có lý do. Với **multi-tenant**, cần thiết kế xác minh issuer/tenant cho từng tổ chức đã được onboard, kiểm tra tenant allowlist và tách dữ liệu theo tenant. Cho phép token từ mọi tenant chỉ vì chữ ký của Microsoft hợp lệ có thể gây lỗ hổng truy cập chéo tenant.

## 4. Chuỗi xử lý request qua Azure API Management

Policy APIM được tổ chức theo các phần **inbound, backend, outbound và on-error**:

```text
Client request
     |
     v
Inbound policies
  - kiểm tra JWT
  - kiểm tra scopes/roles
  - rate limit và validate request
  - rewrite/set headers
     |
     v
Backend policies
  - forward request
  - route/backend authentication
     |
     v
Backend response
     |
     v
Outbound policies
  - response shaping / safe headers theo thiết kế
     |
     v
Client response

Nếu lỗi policy/transport: on-error xử lý theo cấu hình.
```

### 4.1. Vì sao xác thực nằm trong inbound?

JWT validation và kiểm tra quyền nên diễn ra **trước `forward-request`**, tránh request không hợp lệ sử dụng tài nguyên compute/database của backend. Sau khi token hợp lệ, vẫn cần kiểm soát request content/size, quotas, routing và identity đến backend.

### 4.2. Phân biệt policy scope

Các scope thường dùng:

- **Global:** chính sách chung của gateway (khi được hỗ trợ).
- **Product:** hành vi với API được công bố trong product tương ứng.
- **API:** quy tắc áp cho một API.
- **Operation:** phân quyền/validation riêng cho một đường dẫn/phương thức.

Khả năng hỗ trợ và quy tắc hiệu lực có thể khác theo tier/gateway/workspace/feature. Quy tắc **`<base />`** điều khiển vị trí kế thừa policy từ scope cha. Nếu xóa `<base />` hoặc đặt ở vị trí không phù hợp, operation có thể **không thừa hưởng** validation từ API/global như người vận hành tưởng.

**Nguyên tắc:** sau mỗi thay đổi, kiểm tra **effective policy** trên chính operation được công bố, không chỉ mở policy của API ở cấp cao rồi kết luận mọi request được bảo vệ.

### 4.3. Subscription key không thay access token

APIM có thể yêu cầu **subscription key** để quản lý developer/product, quota và tracing. Đây không mặc nhiên là cơ chế xác thực danh tính người dùng hoặc phân quyền truy cập dữ liệu nghiệp vụ. Không dùng “có `Ocp-Apim-Subscription-Key`” để thay kiểm tra JWT, scope/role và object-level permissions.

Với API public đa tenant, một subscription key bị chia sẻ/rò rỉ có thể được dùng từ client khác; vai trò của nó trong bảo mật cần được mô tả riêng và giữ ở mức tối thiểu.

## 5. Chuẩn bị Microsoft Entra ID cho Orders API

Ví dụ thực hành dùng một tenant Entra ID mà đội kỹ thuật kiểm soát. Các giá trị `<tenant-id>` và `<orders-api-app-id>` là **placeholders**; thay bằng giá trị thực được bảo vệ trong môi trường lab.

### 5.1. Đăng ký API resource

Trong Microsoft Entra admin center:

1. Tạo hoặc chọn **App Registration** đại diện **Orders API**.
2. Ghi nhận **Application (client) ID**, **Directory (tenant) ID** và App ID URI nếu cấu hình.
3. Ở **Expose an API**, công bố các delegated scopes như `orders.read` và `orders.write` theo thiết kế.
4. Tạo **app role `Orders.Reconcile`** dành cho workload automation theo cấu hình permitted member types phù hợp.
5. Phân quyền/consent scopes hoặc application roles cho đúng client applications.
6. Kiểm tra access token thực tế để xác nhận `iss`, `aud`, `scp`, `roles` và token version.

### 5.2. Đăng ký client

- Web/mobile public client phải dùng luồng OAuth phù hợp, redirect URI được kiểm soát, **PKCE** và không nhúng client secret.
- Backend daemon có thể dùng service principal/managed identity hoặc workload federation và app role được cấp với consent phù hợp.
- Không cấp `orders.write` cho mọi app chỉ để chúng đọc đơn; và không cấp `Orders.Reconcile` cho browser SPA.

### 5.3. Ba định danh dễ nhầm

| Giá trị | Ví dụ | Mục đích |
|---|---|---|
| Tenant ID | `<tenant-id>` | Khóa issuer/tenant tin cậy |
| API Application ID / App ID URI | `<orders-api-app-id>` hoặc `api://...` | Audience của access token mà API nhận |
| Client application ID | `<web-client-id>` hoặc `<daemon-client-id>` | Xác định ứng dụng đang xin token, có thể được allowlist |

**Không lấy `client_id` của SPA làm `aud` cho Orders API.** Điều đó có thể dẫn tới việc gateway chấp nhận ID token của client thay vì access token dành cho API.

## 6. Policy APIM `validate-jwt`: xác minh access token

**`validate-jwt`** là policy dùng để kiểm tra JWT nhận từ request hoặc nguồn token cấu hình. Với API OAuth 2.0 thông thường, JWT nằm trong:

```http
GET /orders HTTP/1.1
Host: api.example.com
Authorization: Bearer <access-token>
```

Policy nên kiểm tra **chữ ký, issuer, audience, lifetime** và những claims phù hợp với threat model. Nếu dùng Microsoft Entra ID, APIM có thể lấy khóa công khai qua **OpenID Connect configuration/JWKS** thay vì hard-code một khóa signing duy nhất trong policy.

### 6.1. Ví dụ API-level policy kiểm tra token

Đoạn XML dưới đây minh họa policy cho một API nhận **access token v2 của single tenant**, phát hành cho Orders API. Hãy thay toàn bộ các chuỗi `TENANT_ID` và `ORDERS_API_AUDIENCE` bằng giá trị thực đã xác minh:

```xml
<policies>
  <inbound>
    <base />
    <validate-jwt
        header-name="Authorization"
        require-scheme="Bearer"
        require-signed-tokens="true"
        require-expiration-time="true"
        clock-skew="60"
        failed-validation-httpcode="401"
        failed-validation-error-message="Unauthorized"
        output-token-variable-name="validatedJwt">
      <openid-config
          url="https://login.microsoftonline.com/TENANT_ID/v2.0/.well-known/openid-configuration" />
      <audiences>
        <audience>ORDERS_API_AUDIENCE</audience>
      </audiences>
      <issuers>
        <issuer>https://login.microsoftonline.com/TENANT_ID/v2.0</issuer>
      </issuers>
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
```

Ví dụ với API App ID URI thật là `api://11111111-2222-3333-4444-555555555555` thì `ORDERS_API_AUDIENCE` phải được thay bằng chuỗi đó **nếu access token thực sự dùng chuỗi ấy trong `aud`**. Nếu `aud` là GUID, cấu hình audience bằng GUID phù hợp. Không chấp nhận cả một danh sách audience tùy tiện “cho dễ chạy”.

### 6.2. Ý nghĩa của những thuộc tính chính

| Thuộc tính/phần tử | Ý nghĩa |
|---|---|
| `header-name="Authorization"` | Đọc JWT từ HTTP header |
| `require-scheme="Bearer"` | Yêu cầu đúng authorization scheme |
| `require-signed-tokens="true"` | Không chấp nhận token unsigned theo cấu hình policy |
| `require-expiration-time="true"` | Yêu cầu có expiration claim hợp lệ |
| `clock-skew="60"` | Cho phép sai lệch đồng hồ nhỏ tính bằng giây theo chính sách |
| `failed-validation-httpcode="401"` | Từ chối request khi token không hợp lệ |
| `failed-validation-error-message` | Thông báo chung, không tiết lộ lý do/khóa nội bộ |
| `openid-config` | Địa chỉ OpenID discovery phục vụ xác minh issuer/signing keys |
| `audiences` | Token phải dành cho API được bảo vệ |
| `issuers` | Chỉ tin issuer được cấu hình |
| `output-token-variable-name` | Lưu đối tượng JWT đã xác minh để policy phía sau dùng khi cần |

**Đừng vô hiệu hóa kiểm tra signature/lifetime để xử lý lỗi clock, issuer hoặc JWKS.** Tìm nguyên nhân mismatch và sửa cấu hình hoặc đồng bộ thời gian hợp lệ.

### 6.3. OpenID Connect discovery và key rotation

Metadata OpenID Connect của issuer cung cấp thông tin để verifier biết nơi lấy **public signing keys**. Khi Entra ID xoay signing keys, APIM cần lấy metadata/keys cập nhật theo cơ chế cache/refetch của nền tảng.

Điểm cần lưu ý:

1. `kid` trong JWT header giúp định vị khóa ký phù hợp từ JWKS, nhưng **không tự chứng minh khóa đáng tin** nếu JWKS đến từ một URL không tin cậy.
2. URL `openid-config` phải là của issuer/tenant được phê duyệt; **không** xây URL đó trực tiếp từ claim/token do client gửi.
3. Các thuật toán chữ ký được chấp nhận phải theo policy của issuer và validator; không cho phép `alg=none` hoặc kiểu confusion giữa symmetric/asymmetric.
4. Khi issuer xoay khóa, một token mới có thể dùng `kid` mới. Quy trình cần hỗ trợ refresh metadata, theo dõi lỗi và tránh pin khóa công khai thủ công không cần thiết.
5. Xác thực token phải xử lý `exp`, `nbf` theo đồng hồ của gateway và sai lệch nhỏ đã cho phép, không chấp nhận token quá hạn dài vì “để client khỏi lỗi”.

**Không lấy khóa signing từ URL đặt trong chính JWT** nếu hệ thống không xác minh URL đó là nguồn được tin cậy. Policy của issuer phải cố định hoặc được lựa chọn từ danh sách tenant đã được onboard và thẩm định.

### 6.4. Khi APIM nhận token v1 và v2

Nếu access token thực tế là **v1** với issuer và claims tương ứng, đoạn policy chỉ cho v2 ở trên sẽ từ chối, ngay cả khi client đã đăng nhập Entra ID hợp lệ. Đây là điều đúng nếu API chủ động chỉ hỗ trợ v2. Nếu cần hỗ trợ cả hai:

- Xác định rõ lý do tương thích.
- Xác minh **mỗi** issuer, audience, claim shape và cách lấy metadata tương ứng.
- Thiết lập policy theo các điều kiện tin cậy có chủ đích.
- Viết kiểm thử cho token từ version không được phép.

Không đơn giản bỏ `issuers` hoặc `audiences` để “hỗ trợ mọi token”.

## 7. Kiểm tra delegated scope trên từng operation

Sau khi xác minh token từ issuer và audience đúng, cần xác định client có quyền gọi **operation cụ thể** không. Ví dụ `GET /orders` yêu cầu delegated scope `orders.read`.

### 7.1. Policy cho GET /orders

Ví dụ dùng `validate-jwt` với `required-claims`; đặt tại **operation GET /orders** hoặc nơi có hiệu lực đúng theo cấu trúc API của bạn:

```xml
<policies>
  <inbound>
    <base />
    <validate-jwt
        header-name="Authorization"
        require-scheme="Bearer"
        require-signed-tokens="true"
        require-expiration-time="true"
        failed-validation-httpcode="403"
        failed-validation-error-message="Forbidden">
      <openid-config
          url="https://login.microsoftonline.com/TENANT_ID/v2.0/.well-known/openid-configuration" />
      <audiences>
        <audience>ORDERS_API_AUDIENCE</audience>
      </audiences>
      <issuers>
        <issuer>https://login.microsoftonline.com/TENANT_ID/v2.0</issuer>
      </issuers>
      <required-claims>
        <claim name="scp" match="any" separator=" ">
          <value>orders.read</value>
        </claim>
      </required-claims>
    </validate-jwt>
  </inbound>
  <backend><base /></backend>
  <outbound><base /></outbound>
  <on-error><base /></on-error>
</policies>
```

Đoạn ví dụ **cố tình tái xác minh JWT tại operation** để việc kiểm tra `scp` không phụ thuộc vào một biểu thức parser tự viết. Nếu đã có `validate-jwt` ở API-level và `<base />` được kế thừa, yêu cầu này có thể dẫn tới **xác minh lại token** ở cùng request; trong production, cân nhắc policy fragments hoặc biểu thức authorization đọc **JWT đã được validate** với kiểm thử rõ ràng để giảm lặp. Dù tối ưu cách nào, **không bỏ kiểm tra signature/issuer/audience trước khi tin claims**.

Lưu ý response code: policy này được cấu hình trả **403** khi bất kỳ phần nào của validation tại scope này thất bại, kể cả token không hợp lệ nếu request không bị chặn trước đó. Theo ngữ nghĩa thông thường, token thiếu/invalid nên nhận **401**, còn authenticated-but-insufficient-permission thường nhận **403**. Có thể cấu hình một policy riêng để phân biệt, nhưng phải test effective policy và giữ thông điệp lỗi an toàn.

### 7.2. Scope nhiều giá trị và dấu cách

Microsoft Entra delegated token thường biểu diễn `scp` là một chuỗi các scope **phân tách bằng dấu cách**:

```text
"scp": "orders.read orders.write"
```

Trong `required-claims`, thuộc tính `separator=" "` giúp so khớp từng giá trị theo cơ chế policy. Không dùng so sánh chuỗi con kiểu:

```text
Nếu scp chứa ký tự "orders.read" thì cho phép.
```

Vì so khớp chuỗi con có thể chấp nhận nhầm các scope tương tự như `orders.read.all` hoặc một tên quyền do phía khác định nghĩa. Authorization cần kiểm tra **tên scope trọn vẹn**.

### 7.3. POST /orders cần quyền khác

Với operation `POST /orders`, thay quyền `orders.read` bằng:

```xml
<required-claims>
  <claim name="scp" match="any" separator=" ">
    <value>orders.write</value>
  </claim>
</required-claims>
```

Đây là fragment dùng **bên trong** một `validate-jwt` đang kiểm tra đầy đủ signature, issuer, audience và lifetime, **không phải policy hoàn chỉnh** để dán độc lập. Nếu API có operation `DELETE /orders/{id}`, không mặc nhiên cho phép chỉ vì caller có `orders.write`; hãy xác định một quyền xóa phù hợp và business authorization ở backend.

## 8. Kiểm tra application role cho daemon

Ứng dụng automation/daemon thường lấy access token bằng **client credentials**, không có người dùng hiện diện. Trong mô hình app-only điển hình, token có **`roles`** thay vì delegated `scp`.

Ví dụ `POST /orders/reconcile` cần `Orders.Reconcile` và chỉ một daemon được phê duyệt được gọi.

### 8.1. Policy kiểm tra role

```xml
<policies>
  <inbound>
    <base />
    <validate-jwt
        header-name="Authorization"
        require-scheme="Bearer"
        require-signed-tokens="true"
        require-expiration-time="true"
        failed-validation-httpcode="403"
        failed-validation-error-message="Forbidden">
      <openid-config
          url="https://login.microsoftonline.com/TENANT_ID/v2.0/.well-known/openid-configuration" />
      <audiences>
        <audience>ORDERS_API_AUDIENCE</audience>
      </audiences>
      <issuers>
        <issuer>https://login.microsoftonline.com/TENANT_ID/v2.0</issuer>
      </issuers>
      <required-claims>
        <claim name="roles" match="any">
          <value>Orders.Reconcile</value>
        </claim>
      </required-claims>
    </validate-jwt>
  </inbound>
  <backend><base /></backend>
  <outbound><base /></outbound>
  <on-error><base /></on-error>
</policies>
```

Như ví dụ `scp`, đoạn này có thể xác minh token lần nữa nếu `<base />` đã thừa hưởng validation chung. Trong production có thể tối ưu, **nhưng phải giữ đầy đủ kiểm soát authorization**.

### 8.2. Thêm allowlist ứng dụng khi cần

Role nói rằng client được cấp một application permission. Trong những operation đặc biệt nhạy cảm, đội bảo mật có thể cần kiểm tra **ứng dụng gọi** qua `azp` (token v2) hoặc `appid` (token v1), cùng tenant và điều kiện khác. Ví dụ policy fragment:

```xml
<required-claims>
  <claim name="roles" match="any">
    <value>Orders.Reconcile</value>
  </claim>
  <claim name="azp" match="any">
    <value>APPROVED_DAEMON_CLIENT_ID</value>
  </claim>
</required-claims>
```

Fragment này **chỉ áp dụng cho token shape có `azp`**, không tự dùng được cho mọi v1/v2 token. Phải kiểm tra token thật, protected operation và điều kiện đối với managed identities/service principals trước khi triển khai. Không dùng một client ID lấy từ header do người dùng tự gửi thay cho `azp` đã được chữ ký xác minh.

### 8.3. Tại sao không dùng chung policy `scp` và `roles` vô điều kiện?

Nếu `POST /orders/reconcile` cho phép bất kỳ token có `orders.write` **hoặc** `Orders.Reconcile` thì một người dùng web có scope write cũng có thể chạy đối soát, mặc dù nghiệp vụ chỉ định daemon. Tách **user-delegated** và **app-only** authorization theo operation giúp tránh mở rộng đặc quyền ngoài ý muốn.

Trong các hệ thống đa tenant hoặc có impersonation/delegation phức tạp, cần phân biệt thêm loại principal, allowed clients, tenant boundary và ownership của dữ liệu; không coi một claim duy nhất là đủ chứng minh toàn bộ yêu cầu bảo mật.

## 9. Policy inheritance và thứ tự áp dụng

Một lỗi vận hành nguy hiểm là **tưởng APIM đã validate JWT ở cấp API**, nhưng operation override vô tình không kế thừa policy đó.

### 9.1. `<base />` không chỉ là trang trí XML

Ví dụ API-level inbound:

```xml
<inbound>
  <base />
  <validate-jwt ...>
    <!-- Kiểm tra issuer, audience, signature, lifetime -->
  </validate-jwt>
</inbound>
```

Ở operation level, nếu dùng:

```xml
<inbound>
  <base />
  <!-- Policy kiểm tra quyền riêng của operation -->
</inbound>
```

thì policy kế thừa được chèn tại vị trí `<base />` theo mô hình APIM. Nếu operation **không** chứa `<base />`, hoặc một scope khác ghi đè policy theo cách không mong đợi, validation ở scope cha có thể không còn áp dụng đúng như kỳ vọng.

### 9.2. Quy tắc an toàn khi tổ chức policy

1. Chọn **một chỗ có trách nhiệm rõ** cho baseline token validation theo API.
2. Đặt kiểm tra **quyền operation** sau khi đã có token được xác minh.
3. Không cho phép operation sensitive không có auth vì copy một policy public endpoint.
4. Rà soát effective policies ở **global/product/API/operation** trước và sau deploy.
5. Dùng **policy fragments** hoặc IaC khi logic chung lớn, nhưng version và review như code.
6. Test mọi operation quan trọng bằng **missing/invalid/wrong-audience/insufficient-scope token**, không chỉ test một API root.

### 9.3. Public endpoint có ngoại lệ thì làm thế nào?

Một API có thể có `GET /health` hoặc một OpenAPI document public. Nếu cần miễn yêu cầu JWT, tạo **operation riêng**, đánh giá dữ liệu mà nó lộ ra và kiểm soát route tương ứng. Không đặt policy toàn API thành “không cần JWT” chỉ vì có một đường public.

Health endpoint công khai nên trả tín hiệu **tối thiểu**; đừng trả connection strings, backend hostname nhạy cảm, stack trace hoặc danh sách secrets.

## 10. Phân quyền API không thay phân quyền theo đối tượng

JWT có `orders.read` chứng minh caller được thực hiện **loại thao tác** đọc đơn, không chứng minh caller được đọc **mọi** đơn trong database.

Ví dụ:

```http
GET /orders/ORD-1042
Authorization: Bearer <valid-token-with-orders.read>
```

Backend vẫn phải kiểm tra người dùng/tenant của đơn:

```text
Token hợp lệ?
     |
     v
Có scope orders.read?
     |
     v
Đơn ORD-1042 thuộc tenant/user mà caller được phép?
     |
     +-- Có -> trả dữ liệu theo quyền
     |
     +-- Không -> 403 hoặc 404 theo chính sách tránh enumeration
```

**Broken Object Level Authorization (BOLA)** có thể xảy ra nếu backend chỉ tin claim `scp` và không kiểm tra quan hệ `tenantId`/owner của record. Gateway thông thường không có đủ dữ liệu nghiệp vụ hoặc transaction context để thực hiện kiểm tra object ownership chính xác, vì vậy trách nhiệm này thuộc backend.

### 10.1. Không tin tenant ID từ query hoặc header tự do

Nếu client gửi `X-Tenant-Id: tenant-b` hoặc `?tenantId=tenant-b`, backend không được coi đó là bằng chứng user có quyền truy cập tenant-b. Phải ánh xạ tenant được cấp quyền dựa trên **danh tính đã xác thực** và dữ liệu cấp quyền trong hệ thống.

Với ứng dụng SaaS multi-tenant, cần tổ chức bảng phân quyền, isolation của dữ liệu, tenant allowlist và chính sách truy cập xuyên tenant độc lập với việc ký JWT.

### 10.2. Không đưa quá nhiều authorization vào JWT

Token có thể sống trong nhiều phút/giờ theo chính sách. Nếu quyền người dùng thay đổi trong thời gian token còn hiệu lực, các claims cũ có thể tiếp tục được chấp nhận cho tới khi token hết hạn hoặc cơ chế thu hồi/bổ sung có hiệu lực.

Đối với quyền nhạy cảm thay đổi thường xuyên, backend có thể cần **kiểm tra quyền hiện tại trong database/authorization service**, dùng short-lived token hoặc chiến lược session/revocation phù hợp. Tránh kỳ vọng mọi thay đổi quyền trên portal có hiệu lực tức thời với các access tokens đã phát hành.

## 11. Ngăn truy cập trực tiếp bỏ qua API Management

Giả sử khách hàng bình thường gọi:

```text
https://api.orders.example.com/orders
        |
        v
     Azure APIM
        |
        v
https://orders-api-prod.azurewebsites.net
```

Nếu backend có public hostname và **không bắt xác thực**, một người biết URL backend có thể gọi:

```text
https://orders-api-prod.azurewebsites.net/orders
```

thay vì đi qua APIM. Khi đó mọi `validate-jwt`, rate limit, request validation ở gateway **không được thực hiện**. Đây là lỗi thiết kế nghiêm trọng, dù policy APIM hoàn toàn đúng.

### 11.1. Ba lớp bảo vệ nên phối hợp

| Lớp | Mục tiêu | Ví dụ |
|---|---|---|
| **Mạng** | Chỉ nguồn hợp lệ kết nối tới backend | Private endpoint, VNet topology, access restrictions, internal ingress, NSG/firewall |
| **Service-to-service identity** | Backend xác minh bên gọi là thành phần được ủy quyền | APIM managed identity, Microsoft Entra token, mTLS khi phù hợp |
| **Application authorization** | Chỉ cho phép thao tác và dữ liệu thuộc quyền caller | JWT validation, scope/role, tenant membership, object ownership |

Không có lớp nào nên được dùng để biện minh bỏ qua hai lớp còn lại. Một private endpoint không tự xác minh user scopes. Một JWT đúng không tự hạn chế inbound network. Một mTLS certificate chỉ cho biết danh tính peer theo trust configuration, không chứng minh user được đọc đơn hàng nào.

### 11.2. Các lựa chọn backend trên Azure

**Azure App Service:** cân nhắc **private endpoint** và tắt/giới hạn public network access theo khả năng tier, hoặc access restrictions với địa chỉ nguồn được kiểm soát. Có thể dùng **App Service Authentication/Authorization (Easy Auth)** để xác minh Entra tokens; kiểm tra audience và allowed client applications phù hợp với kiến trúc.

**AKS:** cân nhắc internal ingress/load balancer hoặc gateway kết nối qua VNet, Kubernetes NetworkPolicy, identity và authentication ở ingress/API. Pod không nên được công bố ra Internet ngoài ý muốn chỉ vì có một Service loại LoadBalancer public.

**Azure Container Apps:** chọn ingress internal/private theo môi trường, cấu hình networking, authentication và route đúng chiều. Không mặc định một endpoint là private chỉ vì Container Apps environment có VNet.

Khả năng kết nối APIM qua VNet, private endpoint/private link, internal gateway và các cấu hình APIM phụ thuộc **tier, thế hệ dịch vụ và region**. Trước khi chốt sơ đồ, xác minh các chức năng đang được hỗ trợ cho gateway cụ thể; không copy cấu hình của một APIM tier khác.

### 11.3. IP allowlist có đủ không?

Chặn mọi traffic trừ IP egress của APIM có thể hữu ích trong một số kiến trúc, nhưng:

- IP egress có thể phụ thuộc kiểu triển khai, NAT, region và cấu hình; chỉ dùng khi địa chỉ nguồn **ổn định và được xác minh**.
- IP có thể được chia sẻ hoặc thay đổi theo vòng đời infrastructure.
- IP không chứng minh caller được cấp token hợp lệ.
- Nếu backend có nhiều đường đi, một allowlist ở chỗ sai sẽ không chặn đường khác.

Khi yêu cầu cách ly mạnh, cân nhắc **private networking + identity xác thực service-to-service + xác thực/ủy quyền backend**.

## 12. Hai mô hình xác thực giữa APIM và backend

Có **hai** mô hình phổ biến; hãy chọn có chủ đích, không trộn chúng rồi vô tình làm mất identity của người dùng.

### 12.1. Mô hình A: end-to-end access token của người dùng

```text
Client --(User JWT for Orders API)--> APIM
  APIM: validate JWT, tenant, scope, rate limit
                           |
                           v
Backend Java API: xác minh lại JWT,
  kiểm tra scope/role + owner/tenant của từng đơn hàng
                           |
                           v
Database
```

Ưu điểm: backend nhìn thấy user token dành cho API và có thể quyết định object-level authorization trực tiếp. Nó cũng chống bypass tốt hơn nếu URL backend lộ ra, vì backend không cho phép request không có token/quyền hợp lệ.

Vẫn cần network controls vì có token hợp lệ không có nghĩa client được phép **bỏ qua quota, logging và các policy gateway**. Nếu backend public, người dùng hợp lệ nhưng độc hại có thể vượt qua rate limit APIM khi gọi trực tiếp.

### 12.2. Mô hình B: APIM dùng managed identity gọi backend

APIM có thể dùng **managed identity** để lấy access token cho resource/backend được bảo vệ, thông qua policy `authentication-managed-identity` khi tier/tính năng hỗ trợ.

```xml
<policies>
  <inbound>
    <base />
    <!-- Đặt sau khi đã kiểm tra JWT/scopes ở inbound. -->
    <authentication-managed-identity resource="api://BACKEND_APP_ID" />
  </inbound>
  <backend><base /></backend>
  <outbound><base /></outbound>
  <on-error><base /></on-error>
</policies>
```

**Chỉ là mảnh ghép của kiến trúc**: policy trên giả định có validation và authorization đầy đủ ở scope cha, `<base />` kế thừa đúng, APIM managed identity đã bật, backend đã đăng ký Entra resource `api://BACKEND_APP_ID` và chấp nhận token của đúng APIM principal. **Không tự coi đoạn XML này là policy bảo vệ hoàn chỉnh.**

Trong luồng này, gateway lấy token **đại diện cho managed identity của APIM** để xác thực với backend; nó có thể **thay Authorization header** mà client đã gửi. Vì vậy backend sẽ thấy **service identity**, không tự thấy đầy đủ người dùng cuối. Nếu backend còn phải kiểm tra quyền của từng người dùng hoặc đơn hàng, cần thiết kế **đường truyền user context có thể xác minh** và cơ chế authorization tương ứng, hoặc ưu tiên mô hình A.

### 12.3. Không tin header `X-User-Id` do client tự khai báo

Ví dụ backend chỉ đọc:

```http
X-User-Id: alice
X-Tenant-Id: tenant-a
```

rồi cho phép truy cập dữ liệu là **không an toàn** nếu client có thể tự thêm/sửa những header này. Ngay cả khi APIM chèn header, phải:

1. Xóa/ghi đè header cùng tên từ request client **trước khi truyền**.
2. Bảo đảm backend **chỉ có thể truy cập qua kênh xác thực** và backend xác minh service identity.
3. Đảm bảo danh tính/ngữ cảnh người dùng được kiểm tra bằng một **bằng chứng có thể xác minh** (ví dụ token được backend validate, signed assertion có trust rõ, hoặc backend authorization service).
4. Không lấy header làm nguồn sự thật duy nhất cho các quyết định tài chính hoặc đối tượng nhạy cảm.

APIM managed identity là **danh tính của gateway**, không phải quyền truy cập dữ liệu của mọi người dùng cuối. Không tự biến “APIM gọi được backend” thành “người dùng nào cũng được phép”.

### 12.4. Khi backend gọi tiếp dịch vụ khác

Nếu Orders API gọi Microsoft Graph, Azure SQL hoặc một API khác, token đã cấp **cho Orders API** không nhất thiết có audience phù hợp với dịch vụ mới. Không chuyển thẳng access token bất kỳ sang downstream và mong nó được chấp nhận. Cân nhắc:

- **On-Behalf-Of (OBO)** khi thật sự cần gọi downstream với quyền delegated của người dùng và luồng ứng dụng hỗ trợ.
- **Managed identity** khi backend thực hiện công việc bằng quyền của chính workload.
- **Client credentials** hoặc federation theo yêu cầu service-to-service.

Mỗi downstream API cần access token với **audience và scopes/roles riêng**, cùng chính sách tenant, data access và least privilege.

## 13. Java Spring Security: backend tự xác minh JWT

Một backend Java dùng **Spring Boot/Spring Security OAuth2 Resource Server** có thể xác minh token do Microsoft Entra ID phát hành để tạo lớp bảo vệ độc lập với APIM.

### 13.1. Dependencies

Với Spring Boot có cấu hình dependency management phù hợp:

```xml
<dependencies>
  <dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-web</artifactId>
  </dependency>
  <dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-security</artifactId>
  </dependency>
  <dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-oauth2-resource-server</artifactId>
  </dependency>
</dependencies>
```

Ví dụ giả định dùng thế hệ Spring Boot/Spring Security hỗ trợ cấu hình này; version thực phải được quản lý bằng BOM/plugin phù hợp và kiểm tra trước deploy.

### 13.2. Cấu hình issuer và audience

Ví dụ `application.yml`:

```yaml
security:
  orders-api:
    audience: "api://ORDERS_API_APP_ID"

spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: "https://login.microsoftonline.com/TENANT_ID/v2.0"
          audiences:
            - "api://ORDERS_API_APP_ID"
```

Thuộc tính `audiences` được hỗ trợ trong những phiên bản Spring Boot phù hợp; nếu dự án dùng version khác, cần tạo **audience validator** tường minh trong `JwtDecoder` và kiểm thử. Không chỉ đặt `issuer-uri` rồi mặc định backend đã kiểm tra đúng audience cho API. Có thể loại bỏ `security.orders-api.audience` trong bản triển khai thật nếu không dùng nó để tránh hai nguồn cấu hình.

### 13.3. Áp scope và app role theo endpoint

Spring Security thường ánh xạ delegated `scope`/`scp` thành authorities có tiền tố `SCOPE_`. Với `roles` của Entra application, có thể thêm một converter tường minh; không mặc định Spring tự hiểu app role theo prefix mà code dùng.

```java
import java.util.ArrayList;
import java.util.Collection;
import java.util.List;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationConverter;
import org.springframework.security.oauth2.server.resource.authentication.JwtGrantedAuthoritiesConverter;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class OrdersApiSecurity {

    @Bean
    SecurityFilterChain filterChain(HttpSecurity http) throws Exception {
        http.authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.POST, "/orders/reconcile")
                    .hasAuthority("APPROLE_Orders.Reconcile")
                .requestMatchers(HttpMethod.GET, "/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .requestMatchers(HttpMethod.POST, "/orders")
                    .hasAuthority("SCOPE_orders.write")
                .anyRequest().denyAll()
        ).oauth2ResourceServer(oauth -> oauth.jwt(jwt ->
                jwt.jwtAuthenticationConverter(jwtAuthenticationConverter())
        ));

        return http.build();
    }

    @Bean
    JwtAuthenticationConverter jwtAuthenticationConverter() {
        JwtGrantedAuthoritiesConverter scopeConverter =
                new JwtGrantedAuthoritiesConverter();

        JwtAuthenticationConverter converter =
                new JwtAuthenticationConverter();
        converter.setJwtGrantedAuthoritiesConverter(jwt -> {
            Collection<GrantedAuthority> scopeAuthorities =
                    scopeConverter.convert(jwt);
            List<GrantedAuthority> authorities = new ArrayList<>();
            if (scopeAuthorities != null) {
                authorities.addAll(scopeAuthorities);
            }

            List<String> roles = jwt.getClaimAsStringList("roles");
            if (roles != null) {
                roles.forEach(role -> authorities.add(
                        new SimpleGrantedAuthority("APPROLE_" + role)));
            }
            return authorities;
        });
        return converter;
    }
}
```

Ví dụ trên:

- Mặc định **deny all** những endpoints chưa có quy tắc rõ (cần mở thêm đúng các health endpoints nếu có).
- Kiểm tra `SCOPE_orders.read`/`SCOPE_orders.write` cho delegated API.
- Chuyển `roles` thành `APPROLE_...` để endpoint daemon có thể kiểm tra `Orders.Reconcile`.
- Dựa vào resource-server JWT validation để kiểm tra chữ ký, issuer, lifetime và audience **khi đã cấu hình đủ**.

**Không coi ví dụ là production security configuration hoàn chỉnh.** Cần kiểm tra CSRF theo loại ứng dụng (bearer-token stateless API khác cookie/session browser), CORS, exception handling, session management, method security, authentication entry points và những endpoints thực tế. Nếu token role có ý nghĩa khác với quyền daemon, phải thêm kiểm tra **client application ID, tenant và loại principal** phù hợp, không chỉ so role.

### 13.4. Authorization theo đơn hàng trong Java

Controller chỉ kiểm tra scope; service nghiệp vụ phải kiểm tra **object ownership**:

```java
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class OrdersController {
    private final OrdersService service;

    public OrdersController(OrdersService service) {
        this.service = service;
    }

    @GetMapping("/orders/{orderId}")
    public OrderDto readOrder(
            @PathVariable String orderId,
            @AuthenticationPrincipal Jwt jwt) {

        String issuerTenantId = jwt.getClaimAsString("tid");
        String principalObjectId = jwt.getClaimAsString("oid");

        // Pseudocode dịch vụ: ánh xạ principal/tenant thành quyền nghiệp vụ,
        // kiểm tra order ownership trước khi đọc hoặc trả dữ liệu.
        return service.findOrderAuthorized(
                orderId, issuerTenantId, principalObjectId);
    }
}
```

`OrdersService` và `OrderDto` là các type nghiệp vụ minh họa, không phải classes của Spring Security. Backend phải kiểm tra đúng claims của loại token đang dùng; `tid` và `oid` chỉ là danh tính đầu vào cho **authorization lookup**, không tự suy rằng tenant Entra luôn bằng tenant dữ liệu trong SaaS.

### 13.5. Cần thống nhất policy APIM và Java backend

Nếu APIM yêu cầu `orders.write` nhưng Java backend vô tình chỉ kiểm tra `authenticated()` thì backend vẫn yếu hơn khi có đường truy cập trực tiếp. Ngược lại, nếu Java yêu cầu một audience khác với APIM, request hợp lệ tại gateway có thể bị backend từ chối.

Một **security contract** giữa hai tầng nên thống nhất:

- Allowed issuer/tenant và token versions.
- Allowed audiences của API.
- Định nghĩa `scp`/`roles` cho từng operation.
- Cách ánh xạ principal đến tenant/user/business authorization.
- Cách xử lý 401/403, auditing và token/key rotation.
- Cơ chế service-to-service authentication nếu gateway dùng managed identity.

## 14. Rate limiting, quota và chống abuse

JWT validation chỉ xác định ai có quyền gọi operation; nó không tự giới hạn số request. Một client hợp lệ có thể vô tình hoặc cố ý tạo tải lớn khiến backend quá tải.

### 14.1. Rate limit theo principal

Ví dụ bên dưới giả định policy `validate-jwt` đã chạy, đã xác minh token và lưu đối tượng JWT vào biến `validatedJwt`. Khi đó có thể giới hạn số calls trong một cửa sổ cho `Subject`:

```xml
<rate-limit-by-key
    calls="60"
    renewal-period="60"
    counter-key="@(((Jwt)context.Variables[&quot;validatedJwt&quot;]).Subject)" />
```

Đây là **policy fragment**, phải được đặt **sau `validate-jwt`** trong inbound và trong môi trường APIM hỗ trợ biểu thức/policy tương ứng. Ví dụ dùng một tenant tin cậy và `sub` có sẵn; trong môi trường multi-tenant hoặc có user và app-only, cần tạo **khóa phân biệt tenant + principal/client** để tránh nhầm lẫn/cùng quota.

Rate limiting ở gateway có thể mang tính xấp xỉ hoặc có giới hạn nhất quán giữa các gateway units/regions tùy tính năng, topology và policy. Không dùng nó như **quota giao dịch tài chính chính xác**; cần lưu quy tắc nghiệp vụ quan trọng tại backend/database.

### 14.2. Đừng dùng IP làm định danh người dùng mặc định

Nếu nhiều người sau cùng NAT/proxy chia sẻ một IP, rate limit theo IP có thể chặn nhầm cả nhóm. Ngược lại, một attacker dùng nhiều IP có thể tránh giới hạn đơn giản. Với API đã có JWT hợp lệ, việc giới hạn theo **tenant, client application hoặc principal được xác minh** thường có ý nghĩa hơn, tùy khả năng quản lý fairness và nguy cơ abuse.

### 14.3. Quota và backend throttling

**Rate limit** bảo vệ tốc độ request ngắn hạn. **Quota** có thể giới hạn tổng lượng tiêu thụ trong kỳ theo chính sách/tính năng. Ngoài ra:

- Backend nên có giới hạn concurrency, timeout và circuit breaker phù hợp.
- Các downstream như database, Service Bus và Key Vault có quota riêng.
- Request HTTP lớn cần giới hạn body size và validate schema.
- Với 429, client nên dùng retry có backoff/jitter theo header/hướng dẫn và tránh retry storm.
- Autoscale backend không thay thế việc chặn request không hợp lệ hoặc abusive traffic ở edge.

### 14.4. Chặn request quá lớn và dữ liệu không đúng schema

Ngoài JWT, nên dùng các khả năng APIM **request/content validation** khi phù hợp với API definition và SKU:

1. Giới hạn `Content-Type` và body size của endpoints nhận JSON.
2. Validate OpenAPI schema hoặc JSON schema theo cơ chế được hỗ trợ.
3. Không cho client điều khiển dynamic backend URL/route không được phê duyệt.
4. Giới hạn các phương thức/paths được công bố; không forward mọi method đến backend vô điều kiện.
5. Tiếp tục validate input ở backend, vì gateway không biết mọi invariant nghiệp vụ.

Request validation tại APIM **không thay** parameterized SQL, output encoding, kiểm soát file uploads hay authorization theo đối tượng ở Java API.

## 15. CORS, TLS, headers và an toàn ở lớp HTTP

Một API production còn cần bảo vệ ở tầng HTTP và browser. Những cơ chế này bổ sung cho OAuth/JWT, nhưng **không được dùng thay authentication**.

### 15.1. CORS là chính sách browser, không phải API authorization

**Cross-Origin Resource Sharing (CORS)** cho phép browser quyết định JavaScript của origin nào được đọc response từ origin khác. Một policy APIM có thể quy định các origins, methods và headers được phép:

```xml
<cors allow-credentials="false">
  <allowed-origins>
    <origin>https://app.orders.example.com</origin>
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
```

Đây là fragment đặt trong inbound theo thứ tự phù hợp với **CORS preflight** và JWT policy. Preflight `OPTIONS` thường không mang bearer token; cần tổ chức CORS policy và API operation handling sao cho browser preflight an toàn mà request nghiệp vụ vẫn được bảo vệ.

CORS **không cấm** curl, mobile app hoặc server khác gọi API. Request không qua browser vẫn có thể gửi bearer token. Do đó CORS không chứng minh danh tính và không thay kiểm tra `aud`/`scp`/`roles`.

Không dùng wildcard origin cùng browser credentials theo cách vi phạm CORS. Nếu có cookie/session authentication, còn phải thiết kế CSRF protections; việc dùng bearer token trong `Authorization` khác cookie tự động gửi bởi browser.

### 15.2. HTTPS/TLS

- Mọi access token nên truyền qua **HTTPS/TLS**; không chấp nhận bearer token qua HTTP plaintext.
- Domain APIM và backend cần certificate hợp lệ, chain tin cậy và kế hoạch gia hạn.
- Với backend private, **mạng private không đồng nghĩa TLS tùy chọn**.
- Nếu dùng **mTLS**, quản lý cả certificate trust, rotation và revocation; không chỉ kiểm tra certificate tồn tại.
- Khi APIM gọi backend, kiểm tra certificate validation, DNS và routing; không vô hiệu hóa certificate checks để sửa nhanh lỗi handshake.

### 15.3. Headers không phải nguồn quyền

APIM có thể dùng `set-header` để chuyển trace/correlation ID, loại header không mong muốn hoặc chèn metadata. Tuy nhiên:

- `X-User-Id`, `X-Roles` hay `X-Tenant-Id` do caller tự gửi phải được coi là **untrusted** trừ khi có một chuỗi trust xác minh được.
- Không forward `Authorization` của client tới backend không phải audience của token.
- Không log `Authorization`, cookies, API keys hoặc secret header values.
- Có thể dùng `X-Request-Id` cho correlation, nhưng phải chuẩn hóa/giới hạn độ dài và không xem nó là bằng chứng xác thực.

### 15.4. Caching nhạy cảm với danh tính

Gateway caching giảm tải nhưng cache key **chỉ dựa URL** có thể nguy hiểm với response phụ thuộc user/tenant:

```text
GET /orders/ORD-1042
  Alice -> response của Alice được cache theo URL
  Bob   -> gọi cùng URL, có thể nhận nhầm dữ liệu nếu thiếu phân ranh giới
```

Đối với dữ liệu cá nhân/đơn hàng, mặc định **không cache công khai** khi chưa thiết kế `Cache-Control`, tenant/principal-aware cache key và invalidation. Cache không thay object-level authorization.

## 16. Kiểm thử policy: ma trận token và quyền

Policy chỉ đạt yêu cầu khi đã thử **cả trường hợp cho phép lẫn từ chối**. JWT đặc biệt cần negative tests: chỉ cần audience quá rộng hoặc operation thiếu `<base />` là có thể mở truy cập ngoài ý muốn.

### 16.1. Ma trận thử nghiệm GET/POST

Giả sử:

- `GET /orders`: delegated `scp` chứa `orders.read`.
- `POST /orders`: delegated `scp` chứa `orders.write`.
- `POST /orders/reconcile`: app-only `roles` chứa `Orders.Reconcile` và approved caller.

| Trường hợp | GET /orders | POST /orders | POST /orders/reconcile |
|---|---|---|---|
| Không có Authorization header | Từ chối | Từ chối | Từ chối |
| Bearer token bị sửa chữ ký | Từ chối | Từ chối | Từ chối |
| Access token đã hết hạn | Từ chối | Từ chối | Từ chối |
| Token chưa tới `nbf` | Từ chối | Từ chối | Từ chối |
| Token của tenant không được tin | Từ chối | Từ chối | Từ chối |
| Token `aud` là Microsoft Graph | Từ chối | Từ chối | Từ chối |
| ID token `aud` là web client | Từ chối | Từ chối | Từ chối |
| Delegated `scp=orders.read` | Cho phép ở gateway | Từ chối | Từ chối |
| Delegated `scp=orders.write`, không có read | Từ chối theo ví dụ | Cho phép ở gateway | Từ chối |
| Delegated `scp=orders.read orders.write` | Cho phép | Cho phép | Từ chối |
| App-only `roles=Orders.Reconcile` từ client hợp lệ | Từ chối | Từ chối | Cho phép |
| App-only không có role phù hợp | Từ chối | Từ chối | Từ chối |

“Cho phép ở gateway” **không đồng nghĩa** backend trả 200: Java API có thể từ chối theo quyền đối tượng/tenant hoặc dữ liệu nghiệp vụ. Tùy cách tách validation/authorization, status thực tế có thể là **401**, **403** hoặc mã cố ý do policy trả về; phải kiểm tra theo contract.

### 16.2. Test object-level authorization

Với JWT có `orders.read`:

1. Alice gọi `GET /orders/ORD-A` thuộc Alice: kết quả hợp lệ.
2. Alice gọi `GET /orders/ORD-B` thuộc Bob: **bị từ chối** (403 hoặc 404 theo chính sách).
3. Alice tự thêm `X-Tenant-Id: tenant-b`: không được mở quyền.
4. Daemon chỉ có `Orders.Reconcile` gọi `GET /orders/ORD-A`: bị từ chối trừ khi có policy riêng.
5. User đổi quyền trong hệ thống: backend phản ánh membership hiện tại theo thiết kế, không chỉ tin claims đã cũ cho dữ liệu cực kỳ nhạy cảm.

Đây là phép thử **ở backend** và data authorization, không thể thay bằng việc APIM trả 401 cho token invalid.

### 16.3. Test backend bypass

Trong môi trường được phép:

- Gọi qua APIM với access token hợp lệ: kiểm tra kết quả như mong đợi.
- Gọi trực tiếp backend hostname từ **nguồn không được phê duyệt**: phải bị network restriction và/hoặc backend authentication từ chối.
- Gọi backend với token dành cho API khác: bị từ chối.
- Gọi backend với token hợp lệ nhưng thiếu scope: backend từ chối.
- Kiểm tra endpoints quản trị, health, debug/Swagger/OpenAPI, actuator và deployment/SCM riêng, không chỉ `/orders`.

**Không chạy penetration test lên tài nguyên ngoài quyền sở hữu.** Test trên lab/staging hoặc production theo quy trình security/change.

### 16.4. Test key rotation và clock skew

Trong môi trường test được kiểm soát:

- Kiểm tra JWKS/OpenID metadata có thể cập nhật signing keys.
- Test JWT hết hạn, chưa tới `nbf`, thiếu `exp` và sai lệch thời gian nhỏ.
- Test token version/issuer đúng và sai.
- Test metadata endpoint outage theo hành vi cache/refetch của APIM.
- Xác minh policy không fallback sang “allow all” khi metadata không tải được.

### 16.5. Gọi thử bằng curl

Giả sử `ACCESS_TOKEN` đã nhận từ OAuth client được phép và **dành cho Orders API**:

```bash
API_BASE="https://api.orders.example.com"

# Không echo token hoặc bật shell tracing ghi Authorization header.
curl -i \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -H "Accept: application/json" \
  "$API_BASE/orders"

# Không token: kỳ vọng từ chối nếu endpoint yêu cầu authentication.
curl -i "$API_BASE/orders"
```

`curl -i` in response headers/body chứ không cần in request Authorization header; tuy nhiên **không** dùng `curl -v` hoặc `set -x` trên máy có log chia sẻ khi có token thật.

**Không lấy token bất kỳ từ `az account get-access-token` rồi suy rằng nó có `scp=orders.read`.** Azure CLI token tùy resource và delegated grants; kiểm tra audience/claims thật hoặc dùng MSAL/OAuth client được đăng ký đúng scopes.

## 17. Triển khai policy APIM theo cách có thể kiểm soát

### 17.1. Quản lý policy như mã nguồn

Trong quy trình nhiều API, policy XML nên được quản lý bằng **Git + pull request + IaC** (ví dụ Bicep/ARM/Terraform theo Azure API Management resource provider), thay vì chỉ chỉnh thủ công trên Portal.

- Giữ **baseline validation policy** có owner, tests và version.
- Sử dụng **policy fragments** cho logic chung khi được hỗ trợ, không copy nhiều phiên bản lệch nhau.
- Tham số hóa `TENANT_ID`, `AUDIENCE` và backend IDs theo môi trường; không lưu access token/secret/private key trong repository.
- Review `<base />` inheritance và **effective policy** sau deploy.
- Tách dev/test/prod và kiểm thử positive/negative theo từng operation.
- Dùng **what-if/plan** và kiểm tra cấu hình trước production khi công cụ hỗ trợ.

### 17.2. Một gateway có nhiều APIs

Một APIM instance có thể có nhiều APIs với audiences khác nhau. Nếu global policy chỉ kiểm tra Microsoft Entra issuer mà **không kiểm tra đúng audience theo API**, token của API-A có thể được chấp nhận ở API-B.

Baseline toàn gateway có thể kiểm tra những yếu tố chung nhưng **không thay audience-specific checks**. Policy tại API/operation cần xác minh đúng audience. Dù chọn cách tổ chức nào, **test token cross-audience** là bắt buộc.

### 17.3. Deploy qua pipeline

```text
Developer thay APIM policy XML
       |
       v
Pull request + security review
       |
       v
Lint/validate policy syntax + cấu hình môi trường
       |
       v
Deploy DEV APIM
       |
       v
Positive/negative JWT tests + backend bypass tests
       |
       v
Deploy STAGING + canary/controlled traffic
       |
       v
Approval
       |
       v
Deploy PROD + verify effective policies, logs, alerts
       |
       v
Rollback theo phiên bản policy đã kiểm tra nếu cần
```

**XML parse thành công không chứng minh bảo mật**: policy có thể đúng cú pháp nhưng sai audience, sai order, thiếu `<base />` hoặc condition quá rộng.

### 17.4. Tách quyền giữa các nhóm

- **Identity team** quản lý Entra App Registrations, scopes, app roles và consent.
- **API/platform team** quản lý APIM, policies, backend routing và mạng.
- **Backend team** quản lý Java code, business authorization và dữ liệu.
- **Security/SRE** review least privilege, logs/alerts và incident response.

Một CI identity không cần mặc nhiên có **Owner** cả subscription, quyền sửa App Registration lẫn quyền đổi APIM policy production.

## 18. Xử lý lỗi và phản hồi an toàn cho client

Một API cần trả lỗi có ý nghĩa nhưng không để lộ thông tin nội bộ.

| Tình huống | Mã thường dùng | Nguyên tắc |
|---|---|---|
| Không có bearer token | 401 | Không forward tới backend, trả lỗi gọn |
| Token sai chữ ký/hết hạn/sai audience | 401 | Không tiết lộ token hoặc nội dung khóa |
| Token hợp lệ nhưng thiếu scope/role | 403 | Không cung cấp dữ liệu về quyền user khác |
| User hợp lệ đọc record người khác | 403 hoặc 404 theo thiết kế | Ngăn object enumeration |
| Rate limit vượt ngưỡng | 429 | Hỗ trợ retry/backoff hợp lý |
| Body sai schema | 400 hoặc mã do contract quy định | Trả validation error được kiểm soát |
| Backend tạm unavailable | 502/503/504 theo nguyên nhân | Không trả stack trace hoặc infrastructure secrets |

Ví dụ response an toàn:

```json
{
  "error": {
    "code": "ACCESS_DENIED",
    "message": "You do not have permission to perform this operation.",
    "correlationId": "req-7f95c2"
  }
}
```

Không đưa raw JWT, signing key, URL private của database hoặc policy expression exception vào response. Trace/correlation ID giúp SRE tìm logs mà không lộ chi tiết bảo mật.

### 18.1. Kết hợp `on-error` với audit

APIM có khu vực `on-error` để xử lý các lỗi phát sinh trong policy/gateway theo khả năng. Có thể dùng để chuẩn hóa thông điệp lỗi, ghi telemetry an toàn hoặc thêm correlation ID, nhưng **không dùng on-error để trả 200 cho một JWT validation thất bại**.

Nếu dùng policy `return-response` để trả thông báo chung, phải giữ nguyên trạng thái chặn request, không in exception nội bộ và không làm mất audit logs. Lỗi downstream không được giả dạng “user chưa đăng nhập” nếu thực chất backend outage.

### 18.2. 401 và 403 trong diagnostics

Trong ví dụ policy scope/role ở trên, `failed-validation-httpcode="403"` có thể trả 403 cho cả token sai tại lần validate đó. Vì vậy **chỉ nhìn HTTP status** không đủ kết luận “token hợp lệ nhưng thiếu quyền”. Trong sản phẩm thật, nên tách **authentication (401)** và **authorization (403)** rõ ràng bằng policy đã test; giữ logs nội bộ đủ chi tiết để phân biệt nguyên nhân.

Không ghi raw token, full `kid` cùng nội dung JWT hoặc cấu hình issuer/private keys ra response public. Logs nội bộ phải có RBAC và retention phù hợp.

## 19. Logging, Azure Monitor và điều tra sự cố

Azure API Management có thể tích hợp **Azure Monitor**, **diagnostic settings**, **Log Analytics** và **Application Insights** theo khả năng. Mục tiêu là biết request bị chặn ở gateway hay đã tới backend, **không cần ghi full payload/token**.

### 19.1. Những tín hiệu quan trọng

| Nguồn | Tín hiệu | Tác dụng |
|---|---|---|
| APIM gateway diagnostics | Status, API/operation, duration, backend status, correlation ID | Xác định lỗi policy/gateway/backend |
| Entra sign-in/workload identity telemetry | Token acquisition/consent/trust errors theo quyền và dữ liệu hiện có | Kiểm tra caller có lấy được token không |
| Java backend logs | Authorization denied, request ID, principal/tenant đã lọc, business decision | Điều tra quyền theo từng đơn |
| Application Insights/tracing | Request/dependency latency, exceptions, distributed trace | Phân biệt code/database/downstream issues |
| Azure Activity Log | Thay đổi APIM policy, networking và IAM resources | Tìm cấu hình vừa thay gây lỗi |
| WAF/edge logs nếu có | Rate, bot/attack patterns, blocked rules | Phân biệt security abuse và client bugs |

Không có APIM gateway log cho request bị chặn **trước gateway** bởi WAF/DNS/network; mỗi tầng chỉ quan sát traffic thực sự đến được mình.

### 19.2. Ví dụ KQL cho APIM gateway logs

Nếu APIM diagnostic settings gửi gateway logs tới Log Analytics dưới dạng bảng **`ApiManagementGatewayLogs`**:

```kusto
ApiManagementGatewayLogs
| where TimeGenerated > ago(1h)
| summarize Requests=count()
    by bin(TimeGenerated, 5m), ResponseCode
| order by TimeGenerated asc
```

Để xem request bị từ chối:

```kusto
ApiManagementGatewayLogs
| where TimeGenerated > ago(1h)
| where ResponseCode in (401, 403, 429)
| summarize Rejections=count()
    by bin(TimeGenerated, 5m), ResponseCode, ApiId
| order by TimeGenerated asc
```

Bảng/cột có thể khác theo **diagnostic category, resource-specific table mode, APIM tier và cấu hình hiện tại**. Một số môi trường legacy dùng `AzureDiagnostics`. Nếu query báo không có bảng, kiểm tra diagnostic settings, **workspace đích** và schema thực tế trước khi tự sửa tên cột theo phỏng đoán.

**Không kết luận tất cả 401/403 là tấn công**: có thể client token hết hạn, sai audience, consent chưa cấp, policy vừa cập nhật hoặc identity nhầm môi trường.

### 19.3. Những câu hỏi khi có spike 401

1. Spike xảy ra với **API/operation nào**, tenant hoặc loại caller nào?
2. Phát sinh ngay sau thay Entra App Registration, audience, scopes hoặc APIM policy không?
3. JWT token version/issuer có thay không? Signing key xoay trong thời gian gần đây?
4. Token được lấy cho **đúng resource** và dùng scheme Bearer?
5. Lỗi ở APIM hay backend Java? Có backend response không?
6. Một client đơn lẻ hay toàn bộ clients bị ảnh hưởng?
7. Có dấu hiệu request không token, token bị sửa hoặc replay bất thường không?

Khi debug, chỉ log **metadata đã làm sạch** và correlation IDs. Không đính kèm raw access token vào support ticket hoặc các kênh trao đổi không được bảo vệ.

### 19.4. Dashboard và alert

Gợi ý dashboard:

- Request volume theo API/operation và environment.
- 401/403/429 rate theo thời gian, tenant/client đã phân loại an toàn nếu có.
- 5xx và latency p50/p95/p99 ở gateway và backend.
- Backend availability/timeout rate.
- Tần suất policy deploy và Azure Activity Log changes.
- APIM capacity/usage, rate-limited requests và chi phí theo tier.

Alert hữu ích: 401 tăng bất thường sau policy deploy; 403 nhiều ở operation nhạy cảm; 429 tăng kéo dài; backend 5xx vượt SLO; hoặc backend public endpoint được bật ngoài quy trình.

**Alert cần owner, threshold, evaluation window, action group và runbook.** Một cảnh báo “401 > 0” cho API public có thể tạo nhiễu và không có giá trị vận hành.

## 20. Troubleshooting: token sai, policy sai hay backend sai?

Một request trả 401/403/502 có thể do nhiều tầng. Quy trình điều tra có thứ tự:

```text
Client có lấy access token?
      |
      +-- Không -> kiểm tra OAuth grant, redirect/PKCE,
      |             consent, client/federated credential
      v
Header Authorization đúng scheme?
      |
      +-- Không -> sửa client, không nới APIM validation
      v
APIM kiểm tra signature/issuer/audience/lifetime?
      |
      +-- Sai -> đối chiếu App Registration, token version,
      |          metadata/JWKS, clock và scope
      v
APIM kiểm tra scp/roles đúng operation?
      |
      +-- Không -> xác định principal, grant, consent,
      |              effective policy, <base />
      v
Gateway có route tới backend?
      |
      +-- Không -> VNet/DNS/NSG/firewall, backend TLS,
      |             managed identity/mTLS, policy routing
      v
Backend xác thực/ủy quyền request?
      |
      +-- Không -> issuer/audience ở Java, object ownership,
      |              backend roles, user/tenant mapping
      v
Business logic và dependencies hoạt động?
      |
      +-- Không -> database, downstream, timeout, application logs
      v
Request thành công theo contract
```

### 20.1. Bảng triệu chứng – nguyên nhân – cách kiểm tra

| Dấu hiệu | Nguyên nhân khả dĩ | Kiểm tra |
|---|---|---|
| 401 ngay tại APIM | Thiếu token, sai scheme, token invalid/hết hạn | Authorization header, validation logs, access token metadata |
| 401 sau một thay đổi login | API audience/issuer hoặc token version thay | `aud`/`iss`/`ver`, App Registration, APIM policy |
| 401 sau key rotation | JWKS metadata chưa refresh hoặc issuer URL sai | Trusted discovery URL, `kid` an toàn, cache/refetch behavior |
| 403 trên một operation | Thiếu delegated scope/app role hoặc allowlist client | `scp`, `roles`, `azp`/`appid`, effective policy |
| GET được nhưng POST 403 | Có `orders.read` nhưng không `orders.write` | Permission model/consent, operation required-claims |
| Daemon 403 nhưng user GET được | App-only token không có `Orders.Reconcile` | App role assignment, client credentials token, approved caller |
| 401 từ Java sau khi qua gateway | Backend issuer/audience khác, token bị thay | Auth model A/B, request headers, Spring Resource Server |
| 403 Java nhưng gateway cho qua | Object-level authorization hoặc backend role thiếu | Order owner/tenant membership, service permission lookup |
| 502/504 tới backend | DNS, TLS, network hoặc backend outage | APIM backend diagnostics, private endpoint, App Service/AKS health |
| Backend gọi trực tiếp vẫn thành công không token | Backend chưa được bảo vệ | Private networking, Easy Auth/Spring auth, route restrictions |
| CORS preflight thất bại | `OPTIONS` không được xử lý đúng, origin/method/header bị chặn | Policy order, allowed origins, browser console |
| 429 tăng | Rate-limit/quota hoặc downstream throttling | Counter key, scopes, SLO, client retries |
| Token đúng nhưng một tenant nhìn dữ liệu tenant khác | Broken object-level authorization | Backend membership/data isolation, không tin user headers |

### 20.2. Không sửa bằng cách tắt validation

Những “cách sửa” nguy hiểm:

- Bỏ `<audiences>` để nhận token của mọi API.
- Dùng issuer `/common` rồi chấp nhận tenant chưa onboard.
- Bật `require-signed-tokens="false"`.
- Cho phép token `exp` quá hạn dài hoặc bỏ kiểm tra expiration.
- Cấp mọi user `orders.write`/`Orders.Reconcile`.
- Mở public backend và bỏ Easy Auth/Spring Security.
- Trust `X-User-Id` của client hoặc chỉ kiểm tra subscription key.
- Bật verbose logging chứa raw bearer token.

Giải pháp đúng là **xác định tầng lỗi**, so sánh token/resource/policy với contract và sửa tối thiểu có kiểm chứng.

### 20.3. Trường hợp local hoạt động, production thất bại

Local có thể dùng **một client application, token audience hoặc Entra tenant khác** so với production. Với daemon, local dùng developer `az login` có thể có delegated scopes, còn production managed identity nhận **app-only role**. Không giả định hai token có claims giống nhau dù đều phát hành từ Entra ID.

Hãy lưu một bảng so sánh **không chứa token thô**: tenant, issuer, audience, grant type, client ID, scopes/roles, API operation, timestamp, policy version, error code. So sánh metadata ở môi trường dev/test để xác định nguyên nhân.

## 21. Tình huống kiến trúc: Orders API cho web và daemon

### 21.1. Yêu cầu nghiệp vụ

Một doanh nghiệp muốn công bố API:

```text
GET    /orders                  Người dùng xem danh sách đơn của mình
GET    /orders/{orderId}        Người dùng xem chi tiết đơn có quyền
POST   /orders                  Người dùng tạo đơn
POST   /orders/reconcile        Daemon nội bộ đối soát đơn
GET    /health                  Endpoint health tối thiểu theo chính sách
```

Ứng dụng web dùng Microsoft Entra ID sign-in. Daemon có service principal/managed identity riêng, không đăng nhập như người dùng. Backend Java chạy trên Azure App Service với dữ liệu ở Azure SQL. APIM là gateway public duy nhất được phép chuyển traffic tới backend theo topology đã thiết kế.

**Yêu cầu bảo mật:** bearer JWT phải có đúng issuer và audience; web chỉ có quyền `orders.read`/`orders.write` được cấp; daemon chỉ được đối soát khi có `Orders.Reconcile` và caller application nằm trong danh sách phê duyệt; Java API kiểm tra quyền sở hữu từng đơn; backend không mở truy cập trực tiếp bypass APIM.

### 21.2. Thiết kế được đề xuất

```text
                          Microsoft Entra ID
                          /                \
               web user access token   daemon app token
                       |                     |
                       v                     v
                 Azure API Management
                 -----------------------------
                 Inbound:
                 - verify signature via trusted JWKS
                 - verify iss, aud, exp, nbf
                 - GET: orders.read
                 - POST: orders.write
                 - reconcile: Orders.Reconcile
                 - limit requests and validate input
                 -----------------------------
                               |
                               | private network / allowed path
                               v
                       Orders Java API
                       - validate JWT again
                       - check scope/role
                       - check tenant/order ownership
                               |
                               v
                            Azure SQL
```

Trong sơ đồ này, lựa chọn là **mô hình A**: giữ user access token có audience là Orders API để backend xác minh lại. APIM có thể ở vùng mạng phù hợp để kết nối tới backend bằng đường được phép. Các tham số DNS, TLS, private endpoint và network support cần được xác nhận theo APIM/App Service tier thực tế.

### 21.3. Ma trận quyền thiết kế

| Role/Scope | GET /orders | POST /orders | POST /orders/reconcile |
|---|---|---|---|
| `orders.read` | Có, theo ownership | Không | Không |
| `orders.write` | Không, nếu không được cấp read | Có, theo business rules | Không |
| `Orders.Reconcile` từ app-only được phê duyệt | Không | Không | Có |
| Không có claim quyền phù hợp | Không | Không | Không |

Ma trận nêu **authorization ở mức API operation**. Một user có `orders.read` vẫn chỉ xem những đơn mà backend xác nhận thuộc phạm vi được phép. App role `Orders.Reconcile` không tự cho daemon quyền sửa mọi bảng dữ liệu; backend phải giới hạn transaction, database permissions và audit.

### 21.4. Các bước triển khai

1. Đăng ký Orders API resource và clients trong Entra ID; công bố delegated scopes/app role.
2. Cấp permissions/consent theo chính sách, kiểm tra access token thực tế của web và daemon.
3. Tạo hoặc chọn APIM gateway, công bố API definition và backend route.
4. Thiết lập policy validate JWT bắt buộc, kiểm tra đúng issuer và audience.
5. Áp per-operation `scp`/`roles`, allowlist daemon và rate limits.
6. Cấu hình Java Resource Server cùng audience/issuer, endpoint authorization và ownership check.
7. Thiết kế private route/ingress hạn chế bypass backend.
8. Bật diagnostics an toàn, alert, dashboard và correlation IDs.
9. Chạy test matrix (positive/negative/cross-tenant/bypass).
10. Triển khai staging/canary, review effective policies rồi rollout production.

### 21.5. Tiêu chí nghiệm thu

- Token thiếu/sai/hết hạn/sai audience không đến được backend nghiệp vụ.
- Scope/role theo operation được thực thi và không bị lỗi kế thừa policy.
- Không thể đọc đơn hàng của tenant/user khác dù có token hợp lệ.
- URL backend trực tiếp không cho client không được phê duyệt bỏ qua gateway.
- App-only daemon không được gọi endpoints chỉ dành cho user nếu chưa có policy riêng.
- Logs/audit đủ phục vụ incident mà không lưu bearer token, secrets hoặc dữ liệu nhạy cảm không cần thiết.
- Rate limit/quota không làm hỏng client hợp lệ do sử dụng key không phù hợp.

## 22. Threat modeling: những cách thiết kế có thể thất bại

Trước khi đưa API lên production, nên kiểm tra không chỉ happy path mà còn các tình huống caller cố sử dụng token/cấu hình ngoài mục đích.

### 22.1. Cross-audience token reuse

Một user có token dành cho Microsoft Graph. Nếu APIM chỉ kiểm tra issuer mà không kiểm tra `aud`, token có thể được dùng nhầm để truy cập Orders API.

**Biện pháp:** `aud` phải bằng đúng resource được phê duyệt, theo token version và API registration; test token từ resource khác bị từ chối.

### 22.2. Multi-tenant issuer confusion

Một ứng dụng multi-tenant cho phép tokens từ tenant chưa được onboard. Nếu backend dựa vào `oid` nhưng không kết hợp `tid` hoặc tenant mapping, có thể xảy ra lẫn danh tính.

**Biện pháp:** xác thực issuer/tenant, allowlist tenant đã onboard, key principal đúng ngữ cảnh và kiểm tra tenant membership khi truy cập dữ liệu.

### 22.3. Delegated scope vs app role confusion

Một daemon có app role `Orders.Reconcile`, nhưng operation dành cho người dùng có logic “bất kỳ token hợp lệ nào cũng được phép”; hoặc user có `orders.write` lại gọi được reconcile.

**Biện pháp:** chỉ định grant/claim/caller type được chấp nhận trên mỗi operation; kiểm tra role **cùng** issuer, audience, tenant, client ID khi phù hợp.

### 22.4. Privilege escalation qua policy override

Một operation thiếu `<base />` khiến token validation ở parent không còn được kế thừa.

**Biện pháp:** kiểm tra effective policy, lint/scan policy changes, negative tests trên mọi operation; chỉ nhóm được phê duyệt có quyền thay security policies.

### 22.5. Gateway bypass

Backend public URL không có authentication, nên caller đi thẳng tới backend và bỏ qua validation/rate limit.

**Biện pháp:** private networking hoặc access restrictions phù hợp, backend JWT/service authentication và kiểm thử truy cập trực tiếp từ nguồn ngoài.

### 22.6. Object-level authorization bypass

Alice có `orders.read` và chỉnh URL sang đơn của Bob; Java API chỉ kiểm tra scope nên trả dữ liệu Bob.

**Biện pháp:** kiểm tra ownership/tenant authorization trong repository/service layer, sử dụng least-privilege database access và các tests dữ liệu chéo user/tenant.

### 22.7. Stolen bearer token

Kẻ tấn công có bearer token còn hạn và có thể dùng ở nơi khác trong phạm vi token.

**Biện pháp:** bảo vệ transport/storage, tránh logs/chia sẻ token, ngắn hạn theo chính sách, identity provider risk controls và sender-constrained tokens khi hệ sinh thái hỗ trợ. Không giả định JWT signature tự ngăn **replay**; chữ ký không xác minh token đang được dùng bởi đúng thiết bị ban đầu.

### 22.8. Header spoofing và forwarded identity

Backend tin `X-User-Id` do client tự khai báo hoặc một gateway khác không được phê duyệt có thể đặt header.

**Biện pháp:** loại header untrusted, xác thực APIM-to-backend, dùng bằng chứng danh tính có thể verify, backend không chỉ tin header rời rạc.

### 22.9. Denial of service bởi client hợp lệ

Một client có token hợp lệ gửi quá nhiều requests và khiến SQL connection pool cạn.

**Biện pháp:** rate limits theo verified principal/tenant, resource/request size limits, backend concurrency control, autoscale, circuit breaker và monitoring.

## 23. Chi phí, tính sẵn sàng và quản trị vòng đời

JWT validation là thao tác cần thiết cho bảo mật, nhưng triển khai gateway và quan sát cũng có chi phí/độ trễ. Tối ưu không phải bỏ security checks mà là chọn kiến trúc phù hợp và giảm thao tác lặp không cần thiết.

### 23.1. Những yếu tố chi phí

| Hạng mục | Điều ảnh hưởng |
|---|---|
| **API Management tier/capacity** | Loại APIM, số gateway units/địa điểm, thời gian chạy và giới hạn features |
| **Traffic** | Request volume, outbound bandwidth, networking và khả năng tích hợp WAF/Front Door |
| **Backend** | App Service Plan/AKS compute, database, storage, dependent APIs |
| **Observability** | Log Analytics ingestion/retention, Application Insights, alerts |
| **Identity** | Những tính năng Entra ID/Conditional Access hoặc license liên quan theo yêu cầu |
| **Networking/security** | Private endpoints, NAT, Firewall, VNet gateways, certificates |
| **Vận hành** | Policy reviews, incident response, schema/contract tests và bảo trì quyền |

Không đưa một đơn giá cố định cho mọi region/tier. Khi lập ngân sách, sử dụng **Azure Pricing Calculator** và **Cost Management** sau triển khai, kiểm tra nguồn chi phí thực tế.

### 23.2. Cache OpenID keys và độ trễ xác minh

APIM có cơ chế sử dụng/cập nhật metadata và public keys để xác minh token; **không** cần gọi Microsoft Entra ID trên mỗi request để introspect mọi JWT theo mô hình validate-jwt thông thường. Tuy nhiên:

- Signing key rotation và cache refresh vẫn là sự kiện vận hành cần chuẩn bị.
- Thêm quá nhiều lần validate-jwt giống nhau trong nhiều scope có thể gây overhead không cần thiết.
- Không giảm overhead bằng cách **bỏ signature/issuer/audience/lifetime checks**.
- Các biểu thức policy có tính toán phức tạp nên được review, đặc biệt với traffic lớn.

### 23.3. APIM là một điểm phụ thuộc trong đường request

Đặt APIM làm gateway tập trung mang lợi ích quản trị nhưng cũng đòi hỏi:

- SLO của gateway và backend.
- Kiểm thử khi APIM không sẵn sàng hoặc kết nối backend bị lỗi.
- Capacity planning cho rate limit, gateway units/regions và network.
- Quy trình rollback policy mà không vô tình mở API.
- Chính sách DNS, certificate rotation và disaster recovery phù hợp với tier.

**Không tạo đường bypass public “dự phòng”** tới backend mà không có xác thực/giám sát tương đương. Giải pháp failover phải giữ đúng security boundary.

### 23.4. Secrets và chứng chỉ

Nếu phải dùng backend client certificate hoặc credential không thể thay thế bằng managed identity:

1. Lưu secrets trong nguồn được quản lý an toàn (ví dụ Azure Key Vault theo hỗ trợ).
2. Gán quyền tối thiểu cho APIM/backends cần truy cập.
3. Có owner, rotation/expiry alert, dual-key/certificate rollover khi phù hợp.
4. Không đưa secret vào policy XML, Git, logs hoặc support ticket.
5. Kiểm tra đường truy cập Key Vault, identity và network trước khi rotation production.

Managed identity giảm nhu cầu giữ client secret lâu dài nhưng **không** thay chính sách cấp quyền và audit.

## 24. Bài tập thực hành

### Bài tập A: policy audience và issuer

**Bối cảnh:** APIM đang chấp nhận một JWT Microsoft Entra ID nhưng `aud` là Microsoft Graph, trong khi resource cần truy cập là Orders API.

**Yêu cầu:**

1. Giải thích vì sao signature hợp lệ chưa đủ.
2. Viết phần `<audiences>`, `<issuers>` cho Orders API.
3. Giải thích cần thay gì khi API nhận token v1 thay vì v2.
4. Nêu một negative test xác nhận token dành cho Graph không thể gọi Orders API.

**Hướng giải:** khóa issuer đúng tenant/version và audience đúng resource Orders API; không loại bỏ validation vì token vẫn được Entra ký. Dùng access token thực sự được phát hành cho Orders API khi kiểm thử.

### Bài tập B: phân quyền delegated và daemon

API có ba operations: `GET /orders`, `POST /orders` và `POST /orders/reconcile`.

**Nhiệm vụ:** thiết kế `required-claims` để GET cần `scp=orders.read`, POST cần `scp=orders.write` và reconcile cần `roles=Orders.Reconcile` cùng approved client ID. Đánh giá vì sao daemon không nên mang `scp` giả để vượt policy.

**Hướng giải:** từng operation có quyền riêng; delegated token và app-only token có kiểu claims khác. Chỉ dùng những claims đã được kiểm tra chữ ký/issuer/audience; không tin header “clientId” do client tự đặt.

### Bài tập C: phát hiện bypass backend

Một Java API chạy trên App Service có URL `https://orders-api-prod.azurewebsites.net`. Client không có JWT vẫn có thể gọi trực tiếp, mặc dù qua APIM bị 401.

**Nhiệm vụ:** trình bày hai lớp sửa độc lập: hạn chế đường mạng và xác thực ở backend. Viết test xác minh direct request từ nguồn không được phê duyệt bị từ chối.

**Hướng giải:** dùng private endpoint/access restrictions phù hợp với APIM tier/topology, cùng Spring Security/Easy Auth hoặc trusted service identity. Không chỉ ẩn hostname hoặc đổi tên DNS.

### Bài tập D: object authorization

User Alice có scope `orders.read` và gọi `GET /orders/ORD-B` thuộc Bob.

**Nhiệm vụ:** giải thích vì sao APIM có thể cho qua nhưng Java API phải từ chối; đề xuất cách ánh xạ `tid`/`oid` sang quyền dữ liệu, không tin `X-Tenant-Id`.

**Hướng giải:** `orders.read` cấp quyền loại thao tác, không cấp quyền dữ liệu của tất cả users. Backend phải kiểm tra membership và ownership từ authorization store đáng tin cậy.

### Bài tập E: operational incident

Sau một thay đổi policy, tất cả clients trả 401. APIM logs tăng `ResponseCode=401`, backend không nhận request.

**Nhiệm vụ:** trình tự điều tra policy version, issuer, audience, `<base />`, OpenID metadata/JWKS, request token type và rollback an toàn.

**Hướng giải:** xác nhận thay đổi gần nhất, lấy metadata không nhạy cảm của access token, so sánh issuer/audience/version, kiểm tra effective policy và triển khai rollback **về policy hợp lệ trước đó**, không tắt validation.

### Bài tập F: tối ưu rate limiting

Một trăm nhân viên dùng chung NAT IP. Policy rate limit theo IP gây 429 hàng loạt dù mỗi người gửi ít requests.

**Nhiệm vụ:** đề xuất rate limit theo verified principal hoặc tenant phù hợp, nêu điều kiện khi caller là daemon app-only và khi có nhiều tenant. Kiểm tra khả năng gateway scale khiến counter không hoàn toàn chính xác.

**Hướng giải:** identity-based key sau JWT validation, ghép tenant/principal để tránh collisions; giữ backend quota kinh doanh chính xác trong data store riêng.

## 25. Câu hỏi tự kiểm tra

**1. JWT có chữ ký hợp lệ đã đủ cho backend API chưa?** Chưa. Phải kiểm tra issuer, audience, lifetime và quyền theo operation, cùng object-level authorization.

**2. `aud` của access token nên là gì?** Tài nguyên/API mà caller muốn gọi, không phải mặc nhiên client SPA hoặc Microsoft Graph.

**3. ID token có nên dùng thay access token gọi REST API không?** Không. ID token có audience là client đăng nhập, không phải bằng chứng quyền gọi resource API.

**4. `scp` và `roles` khác nhau ở đâu?** `scp` thường biểu diễn delegated scopes, `roles` thường biểu diễn app roles theo token/grant; policy phải phân biệt kiểu caller.

**5. `iss` quan trọng thế nào?** Nó xác định nguồn phát hành token; API phải chỉ tin issuer/tenant/version đã được phê duyệt.

**6. `openid-config` giúp điều gì?** Cho validator truy cập metadata/khóa public từ issuer tin cậy để kiểm tra chữ ký và hỗ trợ key rotation.

**7. Vì sao `alg=none` không được chấp nhận?** Token không có chữ ký không chứng minh claims đã được issuer tin cậy phát hành.

**8. Tại sao claim `scp=orders.read` không có nghĩa đọc được đơn của mọi user?** Scope chỉ cấp quyền loại thao tác; backend phải kiểm tra ownership/tenant membership của từng record.

**9. `<base />` trong APIM policy dùng làm gì?** Xác định vị trí kế thừa policy từ scope cha; thiếu nó có thể vô tình bỏ validation chung.

**10. APIM subscription key có thể thay JWT access token không?** Không. Nó phục vụ quản lý API subscription/quota theo mô hình sản phẩm, không thay xác thực và ủy quyền người dùng.

**11. CORS có chặn curl gọi API không?** Không. CORS là ràng buộc do browser thực thi.

**12. Backend chỉ có private endpoint có cần authentication không?** Vẫn cần theo threat model; private network chỉ kiểm soát đường kết nối, không chứng minh quyền dữ liệu người dùng.

**13. APIM managed identity đại diện cho ai?** Cho gateway/service principal của APIM, không tự đại diện cho mọi người dùng cuối.

**14. Vì sao cần kiểm tra JWT ở Java backend dù APIM đã validate?** Để tăng defense-in-depth, chống truy cập trực tiếp và thực thi authorization của dữ liệu/operation đúng phạm vi.

**15. Rate limit theo IP có thể gây vấn đề gì?** Nhiều users dùng chung NAT bị chặn nhầm, và client độc hại có thể thay IP để tránh giới hạn.

**16. 401 khác 403 theo ngữ nghĩa thông thường thế nào?** 401 thường là chưa xác thực/token không hợp lệ; 403 là đã xác thực nhưng không đủ quyền. Policy cấu hình có thể cần tinh chỉnh để phản ánh đúng phân biệt.

**17. Vì sao không log bearer token?** Đó là credential có thể bị replay trong thời gian hợp lệ; logs thường được lưu và truy cập rộng hơn bộ nhớ ứng dụng.

**18. Khi JWKS key rotation xảy ra, có nên tắt signature verification không?** Không. Phải kiểm tra trusted metadata source, cache/refetch và signing key policy.

**19. Khi có 401 sau deploy, bước đầu nên làm gì?** Xác định operation, policy version, JWT issuer/audience và nơi lỗi, không tự mở quyền hoặc bỏ validation.

**20. Vì sao cần kiểm tra effective policy theo operation?** Một operation có thể kế thừa/override khác với API-level policy mà đội vận hành đang nhìn.

## 26. Checklist đưa API lên production

### 26.1. Identity và token

- [ ] Orders API có App Registration và **audience được xác định từ access token thực tế**.
- [ ] Trusted issuer/tenant và token version được kiểm soát, không tin mọi tenant theo mặc định.
- [ ] API từ chối unsigned, invalid-signature, expired, not-yet-valid tokens.
- [ ] OpenID discovery/JWKS đến từ issuer được phê duyệt; có kế hoạch key rotation.
- [ ] Browser/mobile dùng OAuth2 Authorization Code + PKCE khi phù hợp, không nhúng client secret.
- [ ] Daemon dùng app-only identity và role được cấp tối thiểu, có allowlist caller khi cần.
- [ ] `scp`/`roles` và các claims khác được kiểm tra từ **token đã xác minh**, không từ header do client tự khai báo.
- [ ] Đã thử token thiếu, hết hạn, sai tenant, sai audience, wrong grant type và bị sửa signature.

### 26.2. API Management policy

- [ ] Có `validate-jwt` trước khi request tới backend, đúng issuer/audience/lifetime.
- [ ] Các operation sensitive có scope/role đúng, không áp một quyền chung quá rộng.
- [ ] Đã kiểm tra `<base />` và **effective policy** trên global/product/API/operation.
- [ ] Không biến subscription key thành cơ chế authentication duy nhất.
- [ ] Rate limit, quota và input validation phù hợp với SLO và threat model.
- [ ] CORS cho đúng origins/methods/headers, preflight được xử lý mà không mở business request.
- [ ] Không cache response cá nhân theo URL chung thiếu principal/tenant boundary.
- [ ] Phản hồi lỗi không lộ JWT, signing keys, internal paths hoặc stack traces.
- [ ] APIM policy được version, review, test và có rollback rõ.

### 26.3. Backend và mạng

- [ ] Backend không thể bị gọi thẳng từ nguồn không được phê duyệt để bỏ qua gateway controls.
- [ ] Đã chọn end-to-end JWT hoặc gateway managed identity một cách có chủ đích.
- [ ] Nếu APIM dùng managed identity, backend xác minh đúng APIM principal/audience và có phương án user authorization riêng khi cần.
- [ ] Java Resource Server xác minh issuer/audience/expiration/roles/scopes theo security contract.
- [ ] Java service kiểm tra tenant membership và object ownership cho từng record.
- [ ] Backend không tin `X-User-Id`/`X-Tenant-Id` tự khai báo.
- [ ] HTTPS/TLS, certificate lifecycle, private DNS/routing, firewall và endpoint exposure đã được review.
- [ ] Secrets/certificates được quản lý trong nguồn phù hợp, không hard-code vào policy/code/log.

### 26.4. Quan sát và vận hành

- [ ] APIM diagnostic settings/Log Analytics/Application Insights được bật theo nhu cầu và quyền.
- [ ] Logs có correlation ID, API/operation, status và latency nhưng **không có raw token**.
- [ ] Dashboard theo dõi 401/403/429, backend 5xx, latency và policy rollout.
- [ ] Alert có ngưỡng, owner, action group và runbook.
- [ ] Đã thử gọi trực tiếp backend, cross-tenant access và cross-audience token.
- [ ] Đã kiểm tra khi metadata/JWKS refresh hoặc issuer đổi theo quy trình.
- [ ] Có kiểm soát truy cập IAM đối với policy, App Registration, backend và diagnostic data.
- [ ] Đã ước lượng chi phí APIM, monitoring, networking, backend và kế hoạch capacity.
- [ ] Có canary/staging rollout và rollback **không làm yếu bảo mật**.

## 27. Kết luận

**Azure API Management** giúp kiểm tra và điều phối truy cập API thông qua các policy như **`validate-jwt`**, nhưng bảo vệ đúng không chỉ là “có bearer token”. API phải xác minh **chữ ký, issuer, audience, thời hạn** và **delegated scopes hoặc application roles** theo từng operation. Với Microsoft Entra ID, OpenID Connect discovery/JWKS giúp xây chuỗi trust rõ ràng và hỗ trợ signing-key rotation; APIM policy inheritance phải được kiểm tra để không vô tình bỏ qua validation ở một endpoint.

Phần quan trọng không kém nằm **sau gateway**: hạn chế truy cập trực tiếp backend, xác thực đúng danh tính service-to-service hoặc end-user, thực thi **object-level authorization** trong Java, kiểm soát request rate, CORS, TLS, secrets và dữ liệu telemetry. Khi kết hợp **security policy as code, negative tests, monitoring và runbook**, đội phát triển có thể vận hành API trên Azure an toàn, có thể kiểm toán và dễ mở rộng mà không đánh đổi bảo mật để đổi lấy sự tiện lợi.
