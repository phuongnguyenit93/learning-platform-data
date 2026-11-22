# Thiết kế hợp đồng OpenAPI cho API trên GCP

Một hệ thống bán lẻ có `orders-api` chạy trên **Cloud Run**, worker trên **GKE** và dữ liệu đơn hàng tại **Cloud SQL**. Website, ứng dụng di động và đối tác đều cần tạo hoặc tra cứu đơn hàng. Nếu mỗi đội tự hiểu cấu trúc JSON, mã lỗi và cơ chế xác thực, những thay đổi nhỏ ở backend có thể phá vỡ nhiều client. **Thiết kế API-first bằng OpenAPI** giải quyết vấn đề bằng một hợp đồng có phiên bản, có thể review và kiểm thử **trước khi** triển khai.

Bài này thuộc chương **API Gateway và Apigee** trong mô-đun **CLOUD_PROVIDERS_GCP**. Trọng tâm là thiết kế hợp đồng OpenAPI cho các API trên Google Cloud, sử dụng được với **API Gateway** hoặc **Apigee**, đồng thời phân biệt rõ *tài liệu mô tả giao diện API* với *những kiểm soát thật sự được thực thi* ở gateway, proxy và ứng dụng.

## 1. Mục tiêu và bức tranh kiến trúc

Sau bài học, bạn có thể:

1. Thiết kế tài nguyên, path, method, request/response, lỗi, pagination và versioning theo OpenAPI.
2. Viết một **OpenAPI 3.0.x** đủ dùng, có ví dụ request/response, schema dùng lại và mô tả bảo mật.
3. Tích hợp **API Gateway** với backend Cloud Run bằng các `x-google-*` extensions phù hợp phiên bản OpenAPI.
4. Phân biệt **JWT của client**, **danh tính gateway gọi backend** và **quyền nghiệp vụ của người dùng**.
5. Hiểu khi nào cần **Apigee API proxy**, policy validation, quota, authentication và analytics.
6. Đưa lint, contract tests, compatibility checks và phát hành API config vào CI/CD.
7. Nhận diện lỗi hợp đồng, lỗi routing, auth và các chỉ số cần giám sát.

~~~mermaid
flowchart LR
    C["Web / mobile / partner"] --> GW["API Gateway hoặc Apigee proxy"]
    GW --> API["Cloud Run: orders-api"]
    API --> DB["Cloud SQL"]
    API --> PUB["Pub/Sub"]
    OAS["OpenAPI contract: paths, schemas, errors"] -. "Định nghĩa hành vi kỳ vọng" .-> C
    OAS -. "Cấu hình gateway / proxy" .-> GW
    OAS -. "Contract tests" .-> API
    IAM["IAM + JWT + backend auth"] -. "Bảo vệ từng ranh giới" .-> GW
~~~

**Điểm quan trọng:** OpenAPI mô tả cách client và server phải giao tiếp. Nó **không tự** tạo database, thực thi authorization theo từng đơn hàng, đảm bảo schema validation hoặc bật rate limit trên mọi gateway.

## 2. Hợp đồng API phải xác định những gì?

### 2.1. Các lớp của API-first

| Lớp | Nội dung cần thống nhất | Ví dụ |
| --- | --- | --- |
| **Resource** | Tên, path, HTTP method, semantics. | `POST /v1/orders`, `GET /v1/orders/{orderId}`. |
| **Representation** | JSON schema, field required/optional, kiểu, ví dụ. | `quantity` là integer lớn hơn hoặc bằng 1. |
| **HTTP behavior** | Mã trạng thái, headers, retry, idempotency. | Tạo đơn trả `201` và `Location`. |
| **Security** | Cơ chế credential, phạm vi quyền, danh tính. | Bearer JWT; backend kiểm tra chủ đơn hàng. |
| **Reliability** | Timeout, xử lý lỗi, pagination, giới hạn tải. | `429` có `Retry-After` khi phù hợp. |
| **Evolution** | Version, thay đổi tương thích, deprecation. | Giữ `/v1`, không đổi nghĩa một field. |
| **Operations** | `operationId`, tag, trace/correlation ID, monitoring. | `createOrder`, `getOrder`. |

Một bản YAML chỉ khai báo path và trả `200` cho mọi trường hợp **chưa đủ** làm hợp đồng dùng cho client production. Bắt đầu từ **ý nghĩa nghiệp vụ**, sau đó mới chọn field và cách mã hóa.

### 2.2. Không nhầm schema với quy tắc nghiệp vụ

Schema có thể yêu cầu `quantity >= 1`, nhưng không thể tự chứng minh người dùng được mua sản phẩm đó hoặc được xem đơn của người khác. Tương tự, JWT hợp lệ không có nghĩa caller được sửa mọi đơn hàng.

~~~text
1. Client đưa credential và request.
2. Gateway/proxy kiểm tra những policy đã cấu hình.
3. Backend xác thực ngữ cảnh tin cậy, phân quyền nghiệp vụ.
4. Backend xác thực payload, cập nhật dữ liệu và trả response đúng contract.
~~~

Phải phân biệt **authentication (ai gọi)**, **authorization (được làm gì)** và **validation (dữ liệu có hợp lệ không)**.

## 3. Chọn OpenAPI version và dịch vụ GCP

### 3.1. Tình trạng hỗ trợ cần biết

Theo tài liệu Google Cloud được đối chiếu tháng **11/2026**, API Gateway hỗ trợ **OpenAPI 2.0, 3.0.x và 3.1.x**. Các ví dụ cũ chỉ nhắc Swagger 2.0 không còn mô tả đầy đủ khả năng hiện hành. API Gateway có **giới hạn riêng** đối với một số tính năng OpenAPI 3.x, vì thế khả năng *upload thành công* không có nghĩa mọi keyword được thực thi. [Tài liệu API Gateway](https://cloud.google.com/api-gateway/docs/openapi-overview).

| Tiêu chí | API Gateway | Apigee |
| --- | --- | --- |
| Vai trò | Gateway được quản lý cho API/backend trên Google Cloud. | Nền tảng quản trị API với API proxies, policies và analytics. |
| OpenAPI | Có thể dùng OAS 2.0/3.0.x/3.1.x theo hỗ trợ hiện hành. | Có thể import OAS để tạo proxy; **OASValidation policy** tài liệu hỗ trợ OAS 3.0. |
| Routing | Backend được khai báo bằng `x-google-*` extensions. | Proxy endpoint/target endpoint và flow/policies. |
| Bảo mật | API key/JWT theo API config; backend auth riêng. | VerifyAPIKey, VerifyJWT/OAuthV2, policies khác nếu cấu hình. |
| Validation | Không tự validate toàn bộ request body chỉ vì có schema. | Có thể thêm **OASValidation policy**; phải attach policy và hiểu những phần được kiểm tra. |
| Vận hành | API configs, gateway deployments, metrics/quota. | API proxy revisions, environments, API products, analytics và policies. |

Lựa chọn dịch vụ phải theo tính năng, mức quản trị, yêu cầu bảo mật, độ phức tạp triển khai và **chi phí**. Đừng chọn Apigee chỉ vì muốn hiển thị Swagger UI, cũng đừng giả định API Gateway có mọi policy tùy chỉnh giống Apigee.

### 3.2. Vì sao ví dụ dùng OpenAPI 3.0.3?

OpenAPI 3.0.3 có `components.schemas`, `requestBody`, `content` và các security schemes rõ ràng. Đây là cơ sở tốt để chia sẻ giữa client/backend và thử với Apigee OASValidation 3.0. Khi dùng **OAS 3.1**, cần kiểm tra thêm khả năng xử lý JSON Schema của từng công cụ, SDK generator, gateway và proxy policy.

Trong OAS 2.0, các trường như `swagger`, `definitions`, `securityDefinitions`, `consumes`, `produces` và cách khai báo `x-google-backend` **khác** OAS 3.x. Không chép nguyên extensions của OAS 2.0 vào OAS 3.x rồi kỳ vọng gateway nhận đúng.

## 4. Thiết kế tài nguyên đơn hàng

### 4.1. Path và HTTP semantics

Giả sử `orders-api` phục vụ:

| Operation | URL | Thành công | Lưu ý |
| --- | --- | --- | --- |
| Tạo đơn | `POST /v1/orders` | `201 Created` | `Idempotency-Key` giúp chống tạo trùng khi retry. |
| Xem đơn | `GET /v1/orders/{orderId}` | `200 OK` | Chỉ trả đơn mà caller có quyền xem. |
| Không tìm thấy | `GET /v1/orders/{orderId}` | `404 Not Found` | Có thể dùng để tránh tiết lộ tồn tại của đơn khác. |
| Request sai | Tùy operation | `400` hoặc `422` theo quy ước được thống nhất. | Thống nhất error shape, không trả thông điệp nội bộ. |
| Rate limiting | Tùy operation | `429 Too Many Requests` | Khi có policy giới hạn, cân nhắc `Retry-After`. |

`GET` không làm thay đổi trạng thái nghiệp vụ. `POST` có thể tạo side effects; retry chỉ an toàn khi backend hỗ trợ idempotency. `Idempotency-Key` là **quy ước ứng dụng được khai báo trong contract**, không phải tính năng mặc nhiên của OpenAPI hay API Gateway.

### 4.2. Field, tính tiền và dữ liệu nhạy cảm

Ví dụ request:

~~~json
{
  "items": [
    {"sku": "SKU-1001", "quantity": 2}
  ],
  "currency": "VND"
}
~~~

Không để client tự quyết định `totalPrice` phải thanh toán: backend cần tra giá hợp lệ, tính tổng và tạo đơn trong transaction. Khi biểu diễn tiền, ưu tiên **số nguyên ở đơn vị nhỏ nhất theo tiền tệ**, tránh sai số số thực và làm rõ cách làm tròn (VND hiện không có phần thập phân trong đơn vị tiêu chuẩn).

Một response có thể cung cấp `orderId`, `status`, `totalMinor` và `createdAt`, nhưng **không** nên công khai token thanh toán, mật khẩu, thông tin xác thực Cloud SQL hoặc dữ liệu cá nhân không cần thiết.

## 5. Ví dụ OpenAPI 3.0.3 có thể tích hợp API Gateway

Tài liệu dưới đây được viết như một file ví dụ `openapi-orders.yaml`. Các URL `example.invalid` và `REPLACE_WITH_CLOUD_RUN_URL` là **placeholder có chủ đích**, bắt buộc thay bằng nhà cung cấp JWT và Cloud Run service thật trước khi tạo API config. Mã nguồn ở phần bài học này **không tạo file ngoài** Markdown được giao.

~~~yaml
openapi: 3.0.3
info:
  title: Retail Orders API
  version: 1.0.0
  description: Contract tao va truy van don hang.

# Cau hinh rieng cua Google API Gateway cho OpenAPI 3.x.
x-google-api-management:
  backends:
    orders-backend:
      address: https://REPLACE_WITH_CLOUD_RUN_URL
      jwtAudience: https://REPLACE_WITH_CLOUD_RUN_URL
      pathTranslation: APPEND_PATH_TO_ADDRESS
      deadline: 30.0
x-google-backend: orders-backend

# Bao ve mac dinh; khong mo public mot operation do vo y.
security:
  - CustomerJwt: []

paths:
  /v1/orders:
    post:
      tags: [Orders]
      summary: Tao don hang
      operationId: createOrder
      parameters:
        - name: Idempotency-Key
          in: header
          required: true
          description: Khoa on dinh qua cac lan retry cung mot thao tac.
          schema:
            type: string
            minLength: 8
            maxLength: 128
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/CreateOrderRequest'
      responses:
        '201':
          description: Don hang da duoc tao.
          headers:
            Location:
              description: URL cua don hang vua tao.
              schema:
                type: string
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/Order'
        '400':
          $ref: '#/components/responses/BadRequest'
        '401':
          $ref: '#/components/responses/Unauthorized'
        '409':
          description: Idempotency key xung dot voi payload khac.
          content:
            application/problem+json:
              schema:
                $ref: '#/components/schemas/Problem'
        '429':
          $ref: '#/components/responses/TooManyRequests'

  /v1/orders/{orderId}:
    get:
      tags: [Orders]
      summary: Lay mot don hang
      operationId: getOrder
      parameters:
        - name: orderId
          in: path
          required: true
          schema:
            type: string
            pattern: '^[A-Za-z0-9_-]{8,64}$'
      responses:
        '200':
          description: Don hang duoc phep xem.
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/Order'
        '401':
          $ref: '#/components/responses/Unauthorized'
        '404':
          description: Khong tim thay hoac khong duoc tiet lo.
          content:
            application/problem+json:
              schema:
                $ref: '#/components/schemas/Problem'

components:
  securitySchemes:
    CustomerJwt:
      type: oauth2
      flows:
        implicit:
          authorizationUrl: https://idp.example.invalid/authorize
          scopes: {}
      x-google-auth:
        issuer: https://idp.example.invalid/
        jwksUri: https://idp.example.invalid/.well-known/jwks.json
        audiences: [retail-orders-client]
        jwtLocations:
          - header: Authorization
            valuePrefix: 'Bearer '

  schemas:
    OrderItem:
      type: object
      additionalProperties: false
      required: [sku, quantity]
      properties:
        sku:
          type: string
          minLength: 1
          maxLength: 64
        quantity:
          type: integer
          minimum: 1
          maximum: 100
    CreateOrderRequest:
      type: object
      additionalProperties: false
      required: [items, currency]
      properties:
        items:
          type: array
          minItems: 1
          maxItems: 50
          items:
            $ref: '#/components/schemas/OrderItem'
        currency:
          type: string
          enum: [VND]
    Order:
      type: object
      required: [orderId, status, currency, totalMinor, createdAt]
      properties:
        orderId:
          type: string
        status:
          type: string
          enum: [PENDING, CONFIRMED, CANCELLED]
        currency:
          type: string
          example: VND
        totalMinor:
          type: integer
          format: int64
          minimum: 0
        createdAt:
          type: string
          format: date-time
    Problem:
      type: object
      required: [type, title, status]
      properties:
        type:
          type: string
          format: uri-reference
        title:
          type: string
        status:
          type: integer
        detail:
          type: string
        requestId:
          type: string

  responses:
    BadRequest:
      description: Request khong hop le.
      content:
        application/problem+json:
          schema:
            $ref: '#/components/schemas/Problem'
    Unauthorized:
      description: Credential khong hop le hoac khong co.
      content:
        application/problem+json:
          schema:
            $ref: '#/components/schemas/Problem'
    TooManyRequests:
      description: Qua gioi han request.
      headers:
        Retry-After:
          description: Thoi gian goi lai neu duoc cung cap.
          schema:
            type: string
      content:
        application/problem+json:
          schema:
            $ref: '#/components/schemas/Problem'
~~~

**Cần hiểu đúng tính chất ví dụ:**

- `components.schemas` mô tả payload theo OpenAPI 3.0, còn **backend vẫn phải validate request**. API Gateway nhận schema nhưng không thực thi toàn bộ điều kiện như `minLength`, `pattern`, `required` hoặc JSON body validation. 
- Các response được liệt kê là **hợp đồng mà backend nên thực hiện**. Lỗi do gateway/proxy sinh ra có thể có body/header **khác** `Problem`; cần kiểm thử và chuẩn hóa qua lớp phù hợp nếu API public đòi cùng error envelope.
- `CustomerJwt` là ví dụ dùng provider JWT được cấu hình theo **Google `x-google-auth`**. Giá trị issuer, JWKS và audience phải lấy từ IdP thực; `example.invalid` **không phải endpoint hoạt động**.
- `flows.implicit` ở mẫu security scheme phản ánh **cách khai báo JWT trong tài liệu API Gateway**, **không phải khuyến nghị dùng OAuth implicit grant cho ứng dụng mới**. Với browser/mobile, xem xét Authorization Code + PKCE theo IdP; API Gateway kiểm tra JWT nhận được bằng issuer/JWKS/audience đã cấu hình.
- `x-google-api-management` và `x-google-backend` **không phải keywords chuẩn của OpenAPI**. Chúng là adapter cho API Gateway; phần contract như `paths`/`schemas` vẫn có thể dùng với tool khác.
- Tên `orders-backend` phải khớp giữa map backend và `x-google-backend`. Khi dùng OpenAPI 3.x, không điền URL backend trực tiếp vào `x-google-backend` như trong những ví dụ OAS 2.0.

## 6. Giải thích các phần dễ sai của hợp đồng

### 6.1. `operationId`, schema dùng lại và ví dụ

`operationId` nên duy nhất, ổn định và đọc được như `createOrder`, `getOrder`, vì SDK generators và contract tests có thể dựa vào nó. `$ref` giúp dùng lại schema/response, tránh mỗi endpoint tự khai báo `Order` theo kiểu khác nhau.

Trong CI, nên kiểm tra:

- Mọi path parameter `{orderId}` đều khai báo `in: path`, `required: true`.
- `201`, `400`, `401`, `404`, `409`, `429` khớp logic nghiệp vụ; không mô tả `200` rồi backend thường xuyên trả `201`.
- `application/json` và `application/problem+json` được dùng nhất quán.
- Không có field nhạy cảm trong response; optional/required phản ánh **dữ liệu thực**.
- `example`/`examples` không chứa API keys, JWT, email hoặc đơn hàng thật.

Một OpenAPI document đúng YAML nhưng định nghĩa sai business semantics vẫn là hợp đồng kém. Review sản phẩm và API consumer quan trọng như schema lint.

### 6.2. Idempotency và HTTP retries

Với `POST /v1/orders`, lưu `Idempotency-Key` cùng dấu vết payload và kết quả trong kho bền vững, trong thời gian giữ được công bố:

~~~text
Client POST key=A, body=X
  → backend tạo order #100, lưu kết quả, trả 201.

Client retry key=A, body=X
  → backend trả lại cùng kết quả theo chính sách.

Client POST key=A, body=Y
  → backend trả 409 nếu key đã gắn với body khác.
~~~

Chỉ **khai báo header trong OpenAPI không làm retry an toàn**. Cần transaction/unique constraint/locking phù hợp; nếu Cloud Run scale nhiều instances, bộ nhớ instance không phải nơi lưu idempotency key đáng tin cậy.

### 6.3. Phân trang và lọc dữ liệu khi API mở rộng

Nếu sau này thêm `GET /v1/orders`, nên quy định `pageSize`, `pageToken`, sort order, giới hạn tối đa và response `nextPageToken`. Mã hóa page token như dữ liệu opaque, không cho client dựa vào cấu trúc token nội bộ. Đừng thêm pagination rồi trả một mảng không giới hạn, dễ tăng latency/Cloud SQL load.

## 7. Hai ranh giới bảo mật trong API Gateway

### 7.1. Client → gateway: JWT không phải quyền xem đơn hàng

`components.securitySchemes.CustomerJwt` với `x-google-auth` chỉ dẫn API Gateway kiểm tra **issuer, JWKS/signature, audience và thời hạn token** khi cấu hình phù hợp. Sau đó backend vẫn cần kiểm tra người dùng có quyền xem `orderId` cụ thể. 

**API Gateway không thực thi OAuth scopes trong OpenAPI** theo tài liệu hạn chế hiện hành. Không coi `scopes: {read: ...}` trong contract là đủ để khóa nghiệp vụ. Vai trò/permissions thực tế phải được ứng dụng hoặc policy được hỗ trợ thực thi.

Về mặt OpenAPI:

~~~yaml
# AND: hai scheme trong cùng một security requirement object.
security:
  - CustomerJwt: []
    ClientApiKey: []

# OR: nhiều security requirement objects (cần xem giới hạn sản phẩm).
# security:
#   - CustomerJwt: []
#   - ClientApiKey: []
~~~

**API Gateway có giới hạn tổ hợp scheme**: có thể yêu cầu JWT **và** API key, nhưng không hỗ trợ tất cả cách OR giữa API key với scheme khác; với OAuth schemes cũng có giới hạn. API key hữu ích để nhận diện project/consumer, theo dõi hoặc áp quota, **không phải thay thế xác thực người dùng**. Khi dùng `ClientApiKey`, phải định nghĩa `components.securitySchemes.ClientApiKey` và kiểm thử trước khi deploy; đoạn trên chỉ giải thích logic AND/OR, **không phải file YAML độc lập**.

### 7.2. Gateway → Cloud Run: danh tính backend khác JWT người dùng

Khi API Gateway gọi một Cloud Run service có **authentication bắt buộc**, gateway cần một **backend-auth service account** được cấp `roles/run.invoker` trên dịch vụ Cloud Run. API config chỉ định SA này khi tạo; gateway tạo ID token phù hợp với backend audience (`jwtAudience`).

~~~mermaid
sequenceDiagram
    participant C as Client
    participant G as API Gateway
    participant R as Cloud Run backend
    participant D as Cloud SQL
    C->>G: Bearer JWT cua nguoi dung
    G->>G: Kiem tra issuer / signature / audience
    G->>R: Authorization: ID token cua gateway SA
    Note over G,R: Thong tin claim client qua header gateway theo tai lieu
    R->>R: Kiem tra quyen xem / tao don
    R->>D: Truy van bang runtime identity / DB auth
    D-->>R: Du lieu
    R-->>C: Response qua gateway
~~~

API Gateway có thể **thay header `Authorization` trước khi gửi tới backend** khi dùng backend authentication. Thông tin xác thực client đã được gateway xác minh được chuyển qua header **`X-Apigateway-Api-Userinfo`** theo cơ chế dịch vụ. Không giả định backend luôn nhận nguyên JWT của người dùng trong `Authorization`.

**Không tin header do bất kỳ client trực tiếp tự gửi.** Để tin ngữ cảnh danh tính từ gateway, phải bảo vệ đường tới backend (Cloud Run Invoker chỉ cho đúng gateway SA, kiểm soát ingress và các đường bypass), xác minh audience/issuer theo mô hình phù hợp và giới hạn quyền ứng dụng.

### 7.3. Danh tính runtime thứ ba

Cloud Run runtime service account truy cập **Cloud SQL, Cloud Storage, Pub/Sub hoặc Secret Manager** là danh tính **khác** backend-auth SA dùng gọi Cloud Run. Cấp `roles/run.invoker` cho gateway SA **không** tự cho code backend quyền đọc dữ liệu hay ngược lại.

## 8. Những phần riêng của Google API Gateway

### 8.1. Backend routing và path translation

Trong OAS 3.x, khai báo:

~~~yaml
x-google-api-management:
  backends:
    orders-backend:
      address: https://REPLACE_WITH_CLOUD_RUN_URL
      jwtAudience: https://REPLACE_WITH_CLOUD_RUN_URL
      pathTranslation: APPEND_PATH_TO_ADDRESS
x-google-backend: orders-backend
~~~

Ở đây:

- `address` là endpoint backend HTTPS.
- `jwtAudience` dùng khi gateway cần ID token để gọi backend; với Cloud Run thường là URL service gốc được backend chấp nhận.
- `pathTranslation: APPEND_PATH_TO_ADDRESS` giữ đường request tương ứng khi chuyển tiếp, nếu cấu hình backend path phù hợp.
- Nếu đặt backend tại **operation** thay vì root và bỏ `pathTranslation`, hành vi mặc định có thể khác (`CONSTANT_ADDRESS`); phải kiểm tra để tránh làm sai `/v1/orders/{orderId}`.

OpenAPI 3.x sử dụng `x-google-api-management.backends` và **`x-google-backend` tham chiếu tên backend**, khác cú pháp OAS 2.0. Tài liệu còn có các extensions khác về quota, auth và endpoint; chỉ thêm khi đã hiểu tính tương thích và tác động.

### 8.2. API config là artifact có phiên bản

Với API Gateway, **không sửa nội dung OpenAPI của API config hiện hữu tại chỗ**. Mỗi lần publish phiên bản contract/config mới cần tạo **API config mới**, rồi cập nhật gateway trỏ tới config đó. Nếu thay nhiều gateway/regions, phải rollout và kiểm chứng từng gateway; có thời điểm config cũ và mới cùng phục vụ traffic.

Đối với OAS 3.x, các tùy chọn `servers` có giới hạn: API Gateway xem một server có `x-google-endpoint` làm server được cấu hình; không tự sử dụng mọi server URL như những mock/API client tools. Đặc biệt, **`x-google-allow` của OAS 2.0 không được hỗ trợ trong OAS 3.x**. Những keyword path/parameter được chấp nhận cũng có giới hạn; kiểm tra thông báo khi create API config.

### 8.3. Schema mô tả khác với enforcement

API Gateway có thể **chấp nhận** điều kiện `required`, `minimum`, `pattern` và JSON request body schema nhưng **không tự enforce toàn bộ các ràng buộc đó**. Vì thế:

- Backend Cloud Run phải validate payload và trả lỗi theo contract.
- Việc cấu hình `security`/JWT tại gateway là một cơ chế enforcement **riêng**, không đồng nghĩa validate dữ liệu ứng dụng.
- `429` trong `responses` **không tự tạo quota/rate-limit policy**.
- CORS và request options cần cấu hình phù hợp ở gateway/backend; `servers` hay `responses` không tự mở CORS cho mọi trình duyệt.

## 9. Quy trình triển khai minh họa trên API Gateway

Ví dụ sau giả định **Cloud Run service `orders-api` đã triển khai**, chạy ở vùng được chọn và yêu cầu authentication; backend SA đã tồn tại. Các lệnh có `create`, `add-iam-policy-binding`, `update`, `enable` là **thao tác ghi có thể phát sinh phí**. Chỉ chạy trong project lab được phép. Bài tập không tự tạo file OpenAPI trên workspace này; khi thực hành, lưu nội dung phần 5 thành `openapi-orders.yaml` trong thư mục thử nghiệm riêng và **thay các placeholder**.

### 9.1. Chọn region hợp lệ

~~~bash
PROJECT_ID="retail-lab"
API_ID="retail-orders"
CONFIG_ID="orders-config-v1"
GATEWAY_ID="retail-orders-gw"
GATEWAY_REGION="us-central1"
BACKEND_SA="api-gateway-invoker@retail-lab.iam.gserviceaccount.com"
BACKEND_REGION="us-central1"
~~~

Vùng của API Gateway **không đồng nhất với mọi region Cloud Run**. Ví dụ dùng `us-central1` là một **gateway location được liệt kê trong hướng dẫn Google Cloud**; không giả định có gateway ở mọi region như `asia-southeast1`. Chọn vị trí hỗ trợ, độ trễ, data residency và network transfer phù hợp trước khi đưa vào production.

### 9.2. Cấp quyền gọi backend

~~~bash
# WRITE: gateway SA chỉ được gọi service backend được chỉ định.
gcloud run services add-iam-policy-binding orders-api \
  --project="$PROJECT_ID" \
  --region="$BACKEND_REGION" \
  --member="serviceAccount:$BACKEND_SA" \
  --role="roles/run.invoker"

# READ-ONLY: kiểm tra IAM backend.
gcloud run services get-iam-policy orders-api \
  --project="$PROJECT_ID" \
  --region="$BACKEND_REGION"
~~~

Deployer tạo API config có thể cần `roles/iam.serviceAccountUser` hoặc quyền `iam.serviceAccounts.actAs` đối với gateway SA, ngoài quyền tạo API/config/gateway. Đừng cấp Owner cho cả nhóm chỉ để tạo một config.

### 9.3. Tạo API config

~~~bash
# READ-ONLY: kiểm tra project và CLI.
gcloud config get-value project
gcloud --version

# WRITE: API ID có thể được tạo cùng config nếu chưa tồn tại.
gcloud api-gateway api-configs create "$CONFIG_ID" \
  --api="$API_ID" \
  --openapi-spec=openapi-orders.yaml \
  --project="$PROJECT_ID" \
  --backend-auth-service-account="$BACKEND_SA"

# READ-ONLY: xác minh config và trạng thái.
gcloud api-gateway api-configs describe "$CONFIG_ID" \
  --api="$API_ID" \
  --project="$PROJECT_ID"
~~~

Trước bước này cần bật các **Google Cloud APIs được API Gateway yêu cầu**, chuẩn bị quyền IAM/service agents, cập nhật `gcloud` để hỗ trợ OAS 3.x và làm đúng bước **enable managed service** tương ứng theo hướng dẫn API Gateway. Tạo config thành công chưa đủ chứng minh client đã gọi được API: còn gateway deployment và quyền backend.

### 9.4. Tạo gateway và đọc hostname

~~~bash
# WRITE: có phí gateway theo sản phẩm; thực hiện sau khi review config.
gcloud api-gateway gateways create "$GATEWAY_ID" \
  --api="$API_ID" \
  --api-config="$CONFIG_ID" \
  --location="$GATEWAY_REGION" \
  --project="$PROJECT_ID"

# READ-ONLY: xem hostname do gateway cấp.
gcloud api-gateway gateways describe "$GATEWAY_ID" \
  --location="$GATEWAY_REGION" \
  --project="$PROJECT_ID" \
  --format="yaml(defaultHostname,state,apiConfig)"
~~~

Gateway được cấp hostname (thường thuộc miền `gateway.dev` ở các triển khai mới). URL client là `https://<defaultHostname>/v1/orders/...`, **không dùng URL Cloud Run backend** nếu muốn yêu cầu đi qua gateway. Nếu muốn custom domain, cân nhắc tài nguyên load balancing/DNS/TLS và mô hình hỗ trợ.

### 9.5. Thử bằng JWT hợp lệ

~~~bash
# READ/REQUEST: các giá trị này phải do hệ thống thật cung cấp.
GATEWAY_URL="https://REPLACE_WITH_GATEWAY_HOSTNAME"
JWT="REPLACE_WITH_VALID_JWT_FROM_IDP"

# Kiểm tra HTTP status và response.
curl -i \
  -H "Authorization: Bearer $JWT" \
  "$GATEWAY_URL/v1/orders/ORDER1234"
~~~

Token ví dụ **không dùng được**: phải lấy JWT từ đúng IdP với `iss`, `aud`, chữ ký và thời hạn hợp lệ. Đừng ghi token vào shell history, logs hay issue tracker; trong script thực dùng quy trình lấy token an toàn. Kiểm tra thêm token thiếu, token hết hạn, `orderId` không hợp lệ và người dùng không có quyền xem đơn.

## 10. Sử dụng cùng hợp đồng trong Apigee

### 10.1. Import OpenAPI chưa phải bật policy

Apigee cho phép tạo **API proxy từ OpenAPI Specification** rồi bổ sung flow, target và policies. Để kiểm tra request/response dựa trên OAS 3.0, có **`OASValidation` policy**; spec được lưu như resource trong API proxy bundle, ví dụ `apiproxy/resources/oas/orders.yaml`, rồi policy phải được **gắn vào flow** thích hợp.

~~~mermaid
flowchart LR
    C["Client"] --> P["Apigee API proxy"]
    P --> V["VerifyJWT / VerifyAPIKey / OAuthV2"]
    V --> Q["Quota / SpikeArrest"]
    Q --> O["OASValidation (nếu gắn vào flow)"]
    O --> T["TargetEndpoint → Cloud Run / GKE"]
    T --> R["Response + analytics"]
~~~

Sơ đồ minh họa **những policy có thể sử dụng**, không khẳng định thứ tự như vậy phù hợp mọi proxy. Apigee OASValidation có phạm vi và giới hạn kiểm tra các thành phần request/response; nếu chưa attach, một OpenAPI schema **không tự chặn payload sai**. Phải kiểm thử policy flow, lỗi, tác động latency và quy tắc mapping path/basepath trước production.

### 10.2. Bỏ phần nào khi dùng Apigee?

Các trường chuẩn `openapi`, `info`, `paths`, `components` và security descriptions là phần hợp đồng có thể tái sử dụng. Với Apigee:

- Không sao chép `x-google-api-management`/`x-google-backend` của API Gateway như thể chúng tự tạo Apigee TargetEndpoint.
- Cấu hình proxy basepath, target, virtual host/environment group và deployment theo Apigee.
- Gắn policies **VerifyJWT/VerifyAPIKey/OAuthV2**, quota và OASValidation theo kế hoạch.
- Định nghĩa API products/developer apps nếu mô hình phân phối API cần.
- Kiểm tra upstream identity tới Cloud Run và bảo vệ backend để không bị gọi vòng qua proxy.

Có thể duy trì một **canonical OpenAPI contract** và một lớp **deployment overlays** cho Gateway/Apigee. Cách này giảm sao chép paths/schemas nhưng vẫn tách rõ các kiểm soát hạ tầng có tính đặc thù.

### 10.3. Khi nào dùng API Gateway, khi nào dùng Apigee?

Nếu chỉ cần vài REST endpoints, routing/auth cơ bản trên Google Cloud và khả năng triển khai đơn giản, API Gateway thường đáng xem trước. Nếu tổ chức cần nhiều API products, chính sách phong phú, analytics, developer onboarding hoặc quản trị API xuyên đội, hãy đánh giá Apigee. Quyết định dựa trên **yêu cầu thực, giới hạn sản phẩm, vị trí triển khai, SLO và tổng chi phí**, không chỉ số lượng endpoint.

## 11. Kiểm thử hợp đồng và tự động hóa CI/CD

### 11.1. Bốn tầng kiểm thử

1. **Syntax/lint:** YAML parse được, `$ref` hợp lệ, `operationId` duy nhất, path parameters đúng và không có nội dung nhạy cảm.
2. **Semantic review:** HTTP status, optional/required, money units, pagination, versioning và error semantics hợp lý.
3. **Contract tests:** request/response thực của Cloud Run có khớp schema? Thử payload hợp lệ, sai, boundary values và authorization.
4. **Gateway/proxy integration:** JWT/API key policy, backend IAM, path translation, timeout, header propagation, quota/rate limit và analytics đúng như thiết kế.

Ví dụ lệnh lint trong **thư mục thực hành có OpenAPI file**, yêu cầu Node.js và CLI phù hợp đã được kiểm soát phiên bản:

~~~bash
# READ/LOCAL VALIDATION: lint spec, không thay đổi tài nguyên GCP.
npx @redocly/cli lint openapi-orders.yaml
~~~

Không coi lệnh lint là bằng chứng API Gateway/Apigee **sẽ thực thi đầy đủ schema**. Ngoài ra, khi phát hành API config, phải thực hiện bước validation của sản phẩm vì extensions và khả năng hỗ trợ có giới hạn riêng.

### 11.2. Contract tests tối thiểu

| Tình huống | Request | Kỳ vọng |
| --- | --- | --- |
| Tra cứu hợp lệ | `GET /v1/orders/ORDER1234` với JWT đúng quyền | `200`, JSON đúng schema `Order`. |
| Không xác thực | Không gửi `Authorization` | `401` hoặc lỗi authentication theo gateway đã cấu hình. |
| Không có quyền xem | JWT hợp lệ nhưng đơn thuộc người khác | Không rò dữ liệu; `403`/`404` theo chính sách đã thống nhất. |
| Tạo hợp lệ | `POST /v1/orders` + body hợp lệ + `Idempotency-Key` | `201`, `Location`, order JSON đúng contract. |
| Sai số lượng | `quantity: 0` | Validation error theo hợp đồng, backend không ghi đơn. |
| Retry cùng key | Hai lần POST cùng key/payload | Một đơn, kết quả theo chính sách idempotency. |
| Xung đột key | Cùng key nhưng payload khác | `409`; không tạo đơn thứ hai. |
| Bị giới hạn | Vượt quota thực sự cấu hình | `429` nếu sản phẩm/policy áp dụng, quan sát `Retry-After` nếu có. |

Mỗi test phải xác minh **HTTP code + headers + JSON shape + side effects**, không chỉ text trả về. Với authorization, cần kiểm tra trường hợp IDOR: người dùng A đoán ID đơn của B nhưng backend vẫn từ chối.

### 11.3. Pipeline tham khảo

~~~mermaid
flowchart LR
    G["PR: sửa OpenAPI"] --> L["Lint + semantic review"]
    L --> D["Breaking-change diff"]
    D --> M["Mock / client SDK test"]
    M --> B["Backend contract tests"]
    B --> S["Staging API Gateway/Apigee"]
    S --> E["JWT/IAM/routing/SLO tests"]
    E --> A["Approval"]
    A --> P["Publish config/proxy revision"]
    P --> O["Monitoring + rollback"]
~~~

Để rollback, giữ **OpenAPI artifact đã build, API config ID/proxy revision, image digest Cloud Run, IAM và dữ liệu migration**. Một gateway cập nhật config có thể phục vụ config cũ và mới trong một khoảng thời gian; không giả định thay đổi có hiệu lực cùng một thời điểm ở mọi nơi.

## 12. Versioning và quản lý breaking changes

| Thay đổi | Khả năng tương thích | Chiến lược |
| --- | --- | --- |
| Thêm trường response optional | Thường tương thích với client linh hoạt. | Test client cũ, document field. |
| Thêm một operation mới | Thường không phá consumer cũ. | Kiểm tra route, auth và policies. |
| Biến field optional thành required | **Breaking** cho client gửi request cũ. | Version mới hoặc migration có giai đoạn chuyển tiếp. |
| Đổi kiểu `orderId` từ string sang integer | **Breaking** cho SDK/client. | Giữ contract cũ, tạo v2 nếu cần. |
| Xóa enum value đang dùng | Có thể phá server/client xử lý trạng thái. | Deprecation, compatibility tests, timeline. |
| Đổi HTTP 200 thành 201 ở operation cũ | Có thể phá logic client. | Đánh giá tác động và phát hành có phiên bản. |
| Đổi JWT issuer/audience | Thay đổi security contract, có thể chặn client. | Chuyển tiếp IdP/token, kiểm thử staging. |

Nên quản lý cả:

- **`info.version`**: phiên bản tài liệu/contract, ví dụ `1.1.0`.
- **Path major version**: ví dụ `/v1` và `/v2` khi thay đổi không tương thích.
- **API config/proxy revision**: artifact triển khai hạ tầng, có thể cập nhật dù không đổi public API version.
- **Backend release**: image digest/revision, độc lập với tên API config.

Không phải mỗi lần sửa tài liệu đều cần `/v2`; nhưng **không thay đổi nghĩa endpoint v1** mà không có migration và thông báo cho consumer.

## 13. Bảo mật, SLO và chi phí

### 13.1. Bảo mật theo từng ranh giới

| Ranh giới | Kiểm soát |
| --- | --- |
| Client → gateway | HTTPS, JWT/API key theo chính sách, quota, WAF/Cloud Armor nếu topology hỗ trợ. |
| Gateway → Cloud Run | Backend-auth SA có `roles/run.invoker`, audience đúng, không mở backend để bypass. |
| Cloud Run → Cloud SQL/Storage | Runtime SA, database authentication, VPC/private connectivity, Secrets. |
| Contract → CI | Review, lint, chống lộ PII, security diff và audit. |

Đừng dùng API key để chứng minh danh tính người dùng hoặc xem có quyền đọc đơn nào. Đừng chỉ dựa vào thông tin claim ở header nếu backend vẫn có đường gọi trực tiếp không được kiểm soát.

### 13.2. Các chỉ số cần đo

- **Client SLIs:** tỷ lệ 2xx/4xx/5xx, p50/p95/p99 latency, checkout success rate.
- **Gateway/proxy:** auth failure, quota rejection, upstream status, request count, lỗi routing/config.
- **Backend:** Cloud Run startup/instance metrics, error/timeout, SQL connection pool và query latency.
- **Cost:** requests xử lý qua gateway/Apigee, Cloud Run CPU/memory, database load, Cloud Logging/Monitoring, data transfer và load balancing.

Một contract chuẩn **không bảo đảm SLO**: còn phụ thuộc capacity, timeout, retry, transaction, database và chính sách phát hành. `429` có thể là biểu hiện một bảo vệ đang hoạt động, không nhất thiết là lỗi application.

## 14. Troubleshooting

| Triệu chứng | Nguyên nhân khả dĩ | Kiểm tra đầu tiên |
| --- | --- | --- |
| Tạo API config bị từ chối | OAS sai schema, sai `x-google-*`, CLI cũ hoặc reference không hỗ trợ. | Lint, tài liệu OAS version/extensions, lỗi API config. |
| `404` từ gateway | Path/method không khai báo, basepath/path translation sai. | `paths`, `servers`, gateway config và backend routes. |
| `401` trước backend | JWT sai issuer/audience/chữ ký, hết hạn hoặc thiếu header. | `security`, `x-google-auth`, IdP JWKS và token claims. |
| `403` khi gateway gọi Cloud Run | Backend-auth SA không có `roles/run.invoker` hoặc audience không khớp. | Backend IAM, `jwtAudience`, gateway API config SA. |
| `403` từ ứng dụng | Caller đã xác thực nhưng không có quyền với đơn hàng. | Authorization/ownership logic và audit ứng dụng. |
| `400` không theo format hợp đồng | Gateway/backend trả lỗi riêng; chưa chuẩn hóa response. | Xác định lớp sinh lỗi và hợp đồng error envelope. |
| `POST` tạo trùng đơn | Không thực thi `Idempotency-Key` tại backend. | Transaction/idempotency store, retry traces. |
| `422` không xảy ra với payload sai | Gateway chỉ nhận schema, không validate mọi field. | Backend validators/Apigee OASValidation policy tests. |
| `429` không xuất hiện dù đã khai báo | `responses` là mô tả, chưa có quota/rate policy. | API Gateway quota hoặc Apigee SpikeArrest/Quota. |
| p95 tăng sau triển khai | Backend cold start, Cloud SQL chậm, proxy policy nặng hoặc timeout. | Trace xuyên gateway/backend và Cloud Monitoring. |
| CI sửa contract nhưng gateway vẫn dùng bản cũ | Chưa tạo API config mới/chưa cập nhật gateway. | API config ID và gateway `apiConfig` đang ACTIVE. |

**Phương pháp nhanh:** xác định request ID → gateway/proxy log → xác thực/authz → route/backend SA → Cloud Run log → Cloud SQL/dependency. Phân biệt lỗi ở **gateway** và **backend** trước khi sửa schema hoặc IAM.

## 15. Bài tập

### Bài 1 — Thiết kế contract

Thiết kế `GET /v1/products/{productId}` và `POST /v1/products` cho hệ thống bán lẻ. Nêu `operationId`, path parameter, body schema, các response `200/201/400/404` và ví dụ JSON. Giải thích field nào backend phải validate dù OpenAPI đã khai báo.

### Bài 2 — Tìm lỗi security

Một nhóm đặt trong OpenAPI:

~~~yaml
security:
  - CustomerJwt: []
~~~

Nhưng không có security scheme, JWT issuer/JWKS hoặc IAM backend phù hợp. Liệt kê các lớp còn thiếu nếu dùng API Gateway OpenAPI 3.x, và phân biệt lỗi client 401 với lỗi gateway→Cloud Run 403.

### Bài 3 — OAS 2.0 và OAS 3.x

Một tài liệu cũ dùng `swagger: "2.0"` và `x-google-backend: {address: ...}`. Bạn chuyển sang OAS 3.0.3. Phải thay cách khai báo request body, schema definitions, JWT extensions và backend mapping như thế nào? Vì sao không copy nguyên extension cũ?

### Bài 4 — Idempotency

Client `POST /v1/orders` thành công nhưng mất kết nối trước khi nhận response. Nó retry ba lần cùng `Idempotency-Key`. Nêu quy tắc backend cần thực hiện, response kỳ vọng và cách bảo vệ transaction trên Cloud SQL.

### Bài 5 — Breaking change

Version v1 trả `totalMinor` là integer. Nhóm backend muốn đổi thành `total` dạng decimal string, bỏ trường cũ. Thay đổi này có breaking không? Hãy đề xuất một chiến lược chuyển tiếp cho mobile clients chưa cập nhật.

### Bài 6 — Apigee policy

Đội phát triển import OAS 3.0 vào Apigee nhưng client vẫn gửi `quantity: 0` mà proxy chuyển tới backend. Hãy giải thích vì sao và nêu cách kiểm tra `OASValidation` policy, proxy flow, schema cùng backend validation.

### Bài 7 — Debug 404 và 403

`GET /v1/orders/ORDER1234` ở gateway trả 404, trong khi gọi backend trực tiếp trả 200. Sau khi sửa path lại nhận 403. Hãy lập checklist lần lượt về `paths`, `x-google-backend`, `pathTranslation`, backend SA, `roles/run.invoker` và JWT audience.

### Bài 8 — Contract test và phát hành

Đề xuất pipeline kiểm tra OpenAPI cho Cloud Run backend phục vụ cả GKE/mobile clients: lint, diff breaking changes, mock/SDK, staging gateway, JWT/authz, SLO, phê duyệt và rollback. Nêu ít nhất **một phép thử phủ định** (client không được phép).

## 16. Checklist triển khai và tài liệu tham khảo

| Hạng mục | Điều kiện đạt |
| --- | --- |
| **API-first** | Resource, HTTP semantics, error model, security, pagination/version có owner và được review. |
| **Schema** | Types, required/optional, examples, `$ref`, `operationId` nhất quán; không lộ secret/PII. |
| **OAS version** | OpenAPI 3.0.x/3.1.x hay 2.0 phù hợp với gateway và tooling. |
| **Google extensions** | Dùng đúng cú pháp theo phiên bản, backend URL/audience/path translation hợp lệ. |
| **Authentication** | JWT/API key requirements được thực thi, không tin scopes chưa được enforce. |
| **Backend IAM** | Gateway SA có `run.invoker`; runtime identity tách riêng; không bypass backend. |
| **Validation** | Backend validate; Apigee OASValidation chỉ có tác dụng khi gắn policy và thử nghiệm. |
| **Reliability** | Idempotency, timeout, error mapping, quota và retry được định nghĩa/thực thi. |
| **CI/CD** | Lint, contract tests, compatibility diff, config/proxy revision và rollback. |
| **Observability/cost** | Theo dõi latency, errors, quota, logs, Cloud Run/SQL và Billing theo workload. |

Nguồn chính thức cần đối chiếu trước khi triển khai, vì hỗ trợ OpenAPI và các extensions có thể thay đổi:

- [OpenAPI Specification](https://spec.openapis.org/oas/v3.0.3)
- [API Gateway — OpenAPI overview](https://cloud.google.com/api-gateway/docs/openapi-overview)
- [API Gateway — OpenAPI 3.x extensions](https://cloud.google.com/api-gateway/docs/oasv3-extensions)
- [API Gateway — OpenAPI 3.x limitations](https://cloud.google.com/api-gateway/docs/openapi-v3-limitations)
- [API Gateway — Authenticate users with JWT](https://cloud.google.com/api-gateway/docs/authenticating-users-jwt)
- [API Gateway — Create an API config](https://cloud.google.com/api-gateway/docs/creating-api-config)
- [API Gateway — Deploy an API](https://cloud.google.com/api-gateway/docs/deploying-api)
- [API Gateway — Cloud Run backend](https://cloud.google.com/api-gateway/docs/get-started-cloud-run)
- [Apigee — Create proxy from OpenAPI](https://cloud.google.com/apigee/docs/api-platform/tutorials/create-api-proxy-openapi-spec)
- [Apigee — OASValidation policy](https://cloud.google.com/apigee/docs/api-platform/reference/policies/oas-validation-policy)
- [Cloud Run — Authentication](https://cloud.google.com/run/docs/authenticating/overview)

**Ghi nhớ:** một hợp đồng OpenAPI tốt nói rõ **client gửi gì, nhận gì, lỗi gì và xác thực ra sao**; API Gateway/Apigee chỉ thực thi những cơ chế **thật sự được cấu hình và hỗ trợ**. Hãy thiết kế theo API-first, dùng extensions đúng OAS version, bảo vệ riêng client→gateway và gateway→backend, giữ validation/authorization ở lớp phù hợp, và kiểm thử tính tương thích trước khi phát hành.
