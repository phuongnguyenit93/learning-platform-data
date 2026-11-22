# Import OpenAPI, version và revision trong API Management

Khi một hệ thống ứng dụng bắt đầu có nhiều khách hàng, ứng dụng di động, đối tác và dịch vụ nội bộ sử dụng chung API, việc thay đổi một endpoint không còn đơn giản là deploy code mới. Một thay đổi tưởng như nhỏ — đổi tên trường JSON, bỏ một operation, cập nhật đường dẫn hoặc chính sách xác thực — có thể khiến những client chưa nâng cấp bị lỗi ngay lập tức.

**Azure API Management (APIM)** cung cấp một lớp gateway để công bố và quản lý API có kiểm soát. Từ một bản mô tả **OpenAPI**, nhóm phát triển có thể import các operations và schema vào APIM. Sau đó có thể quản lý **API versions** để duy trì những hợp đồng khác nhau cho các nhóm client, và **API revisions** để thử nghiệm, phát hành hoặc quay lại những thay đổi của một API mà không bắt mọi client đổi URL ngay.

Trong chương **API và tích hợp quy trình** của mô-đun **CLOUD_PROVIDERS_AZURE**, bài học này kết nối APIM với Azure subscription, resource group, Microsoft Entra ID, mạng ảo, backend App Service/Azure Functions/AKS, monitoring, bảo mật và kiểm soát chi phí. Trọng tâm không chỉ là bấm nút import mà là **quản trị vòng đời hợp đồng API** từ thiết kế, phát hành, tương thích đến ngừng phiên bản.

## 1. Mục tiêu học tập

Sau khi hoàn thành bài, bạn có thể:

1. Giải thích các thành phần APIM: gateway, backend, API, operation, product, subscription, policy và developer portal.
2. Đọc một tài liệu OpenAPI cơ bản và nhận ra những phần APIM dùng khi import.
3. Import OpenAPI bằng Azure Portal hoặc Azure CLI vào một API mới, kiểm tra operations và backend URL.
4. Phân biệt **OpenAPI info.version**, **API version set**, **API version identifier** và **API revision**.
5. Chọn versioning scheme theo URL path, HTTP header hoặc query string tùy client và yêu cầu API.
6. Thiết kế thay đổi tương thích ngược và thay đổi phá vỡ hợp đồng; chọn tạo revision hay version mới.
7. Tạo revision không phải current, thử nghiệm qua địa chỉ revision riêng, rồi đưa nó thành current có kiểm soát.
8. Áp dụng nguyên tắc import an toàn: không ghi đè production, xác minh policies, schema, products và authorization.
9. Lập chiến lược rollback/release notes, theo dõi version adoption và ngừng hỗ trợ version cũ.
10. Chẩn đoán lỗi import, trùng route, sai backend URL, lỗi 401/403/404/429/5xx và sai version routing.
11. Xây dựng checklist production, quy trình CI/CD và quản trị APIM bằng Infrastructure as Code.

Các ví dụ CLI, YAML và HTTP là **minh họa**, không tự chạy. Tên service, URL backend, version và subscription key phải được thay bằng giá trị hợp lệ đã được phê duyệt khi áp dụng trên subscription thật.

## 2. Azure API Management đứng ở đâu trong kiến trúc?

### 2.1. Một cổng API, nhiều backend

~~~mermaid
flowchart LR
    C1["Web / Mobile"] --> G["Azure API Management Gateway"]
    C2["Partner"] --> G
    C3["Internal Client"] --> G
    G --> P["Products / Subscriptions / Policies"]
    P --> A1["Orders API"]
    P --> A2["Payments API"]
    P --> A3["Reporting API"]
    A1 --> B1["App Service"]
    A2 --> B2["Azure Functions"]
    A3 --> B3["AKS / Container Apps"]
    G --> M["Azure Monitor / App Insights"]
~~~

Client gọi **gateway endpoint** của APIM. APIM áp dụng các policies và định tuyến request tới **backend API** đã cấu hình. Backend vẫn phải hoạt động và được bảo vệ theo chính sách riêng; APIM không tự tạo business logic từ OpenAPI.

Ví dụ:

~~~text
Client gọi:
  https://api.contoso.example/orders/42

APIM Gateway:
  xác định API/operation từ path và method
  kiểm tra subscription/identity theo cấu hình
  áp policies: validate-jwt, rate-limit, transform...
  chuyển request tới backend URL

Backend:
  https://orders-backend.example.internal/orders/42
~~~

Tên miền ở đây là ví dụ. Trong thực tế, APIM có thể dùng domain mặc định hoặc custom domain, và backend URL có thể khác gateway path. Nếu APIM được triển khai với private networking, cần kiểm tra DNS, routing, firewall và phương án gateway exposure tương ứng.

### 2.2. Các khái niệm cần phân biệt

| Khái niệm | Vai trò | Không nên hiểu thành |
|---|---|---|
| APIM service | Resource quản lý gateway và cấu hình API | Một backend app |
| API | Tập operations, metadata, policies và backend configuration | Một bản container/source code |
| Operation | Một method + URL template và thuộc tính liên quan | Một Function/App Service nhất thiết phải có riêng |
| API URL suffix/path | Phần đường dẫn APIM dùng phân biệt API | Backend URL |
| Backend | Dịch vụ thật xử lý request | API version set |
| Product | Nhóm các APIs để công bố/kiểm soát truy cập | Bản phát hành code |
| Subscription | Cơ chế cấp khóa và scope sử dụng APIM theo cấu hình | Microsoft Entra authentication mặc định |
| Policy | Quy tắc gateway: auth, rewrite, transform, quota, logging... | OpenAPI description thuần túy |
| API version | Một hợp đồng API với version identifier riêng | Revision số 2 |
| API revision | Bản thay đổi của một API, có revision number | Một API major version độc lập |
| Release | Thông tin ghi nhận revision được đưa thành current và release notes | Deploy backend code |
| OpenAPI | Hợp đồng mô tả HTTP operations/schemas/security metadata | Cơ chế thực thi toàn bộ auth/policy tự động |

### 2.3. Hai mặt phẳng vận hành

- **Management plane:** Azure Portal, Azure Resource Manager, Azure CLI/REST/IaC dùng tạo API, import spec, quản trị version/revision, products và policies.
- **Gateway/data plane:** client gửi HTTP/HTTPS tới APIM gateway, hệ thống thực hiện route, kiểm tra auth/rate limit/policy, gọi backend và trả response.

Người được Azure RBAC cấp quyền sửa APIM service ở management plane **không đồng nghĩa** là client được gọi mọi gateway operation. Ngược lại, có APIM subscription key không cho phép chỉnh API definition trong Azure Portal.

## 3. OpenAPI là gì và APIM import được những gì?

### 3.1. OpenAPI là bản hợp đồng HTTP API

OpenAPI Specification (OAS) thường được viết bằng YAML hoặc JSON và mô tả:

- **openapi:** phiên bản cú pháp OpenAPI, ví dụ 3.0.3.
- **info:** tên, mô tả, contact, license và version của bản mô tả.
- **servers:** địa chỉ server hoặc môi trường được tài liệu hóa.
- **paths:** danh sách URL paths và HTTP methods.
- **parameters:** path/query/header parameters.
- **requestBody:** kiểu dữ liệu yêu cầu, schema và ví dụ.
- **responses:** HTTP status, response body và error schemas.
- **components.schemas:** những model dùng lại.
- **components.securitySchemes:** cách xác thực được mô tả trong hợp đồng.
- **security:** yêu cầu security được tài liệu hóa ở API/operation scope.

Không phải mọi thuộc tính OpenAPI đều được APIM import hoặc xử lý với semantics giống công cụ thiết kế ban đầu. APIM hỗ trợ những **phiên bản OpenAPI và tập tính năng cụ thể**; cần kiểm tra tài liệu import restrictions cho SKU/API type và thời điểm triển khai.

### 3.2. Import không tự tạo backend

OpenAPI mô tả một HTTP API. Import vào APIM có thể tạo hoặc cập nhật cấu hình API/operations ở gateway, nhưng **không** tự:

- Tạo bảng database hoặc implement CRUD.
- Deploy Azure Function/App Service/AKS.
- Tạo source code Java/Python.
- Chuyển dữ liệu giữa schema cũ và mới.
- Cấp managed identity quyền gọi backend.
- Bảo đảm JWT có chữ ký hợp lệ chỉ vì OpenAPI có securitySchemes.
- Tự tạo đầy đủ các policies như validate-jwt, rate-limit, CORS hoặc rewrite.
- Kiểm thử mọi request/response có đúng schema không.

Sau import, phải cấu hình và thử **backend service URL**, networking, authentication, operation templates, products, subscriptions và policies.

### 3.3. Hai định nghĩa version rất dễ nhầm

Ví dụ OpenAPI:

~~~yaml
openapi: 3.0.3
info:
  title: Orders API
  version: "1.4.0"
~~~

Giá trị **info.version = 1.4.0** là metadata của bản mô tả API. Nó **không tự động** có nghĩa APIM đã tạo version identifier **v1** hoặc revision **4**. API version và revision của APIM được quản lý qua những thuộc tính/lifecycle riêng.

| Giá trị | Nằm ở đâu? | Chức năng |
|---|---|---|
| openapi: 3.0.3 | Đầu OpenAPI document | Cú pháp/phiên bản OAS |
| info.version: 1.4.0 | OpenAPI info | Metadata của API contract |
| API version identifier: v1 | APIM API version set | Routing/identification của contract version |
| API revision: 2 | APIM revision lifecycle | Một bản thay đổi đang thử nghiệm hoặc phát hành |
| Backend artifact: build-417 | CI/CD hoặc runtime | Code đang được backend triển khai |

Không nên dùng một số duy nhất cho tất cả mục đích này. Release record cần ghi rõ từng loại.

## 4. Tài liệu OpenAPI mẫu cho Orders API

Để học import, dùng OpenAPI 3.0.3 với hai operations: lấy đơn hàng và tạo đơn hàng. Tài liệu này không chứa credential thật.

~~~yaml
openapi: 3.0.3
info:
  title: Orders API
  version: "1.0.0"
  description: API quản lý đơn hàng của hệ thống thương mại.
servers:
  - url: https://orders-backend.example.internal
paths:
  /orders/{orderId}:
    get:
      operationId: getOrderById
      summary: Lấy đơn hàng theo ID
      parameters:
        - name: orderId
          in: path
          required: true
          description: Mã đơn hàng.
          schema:
            type: string
      responses:
        "200":
          description: Tìm thấy đơn hàng.
          content:
            application/json:
              schema:
                $ref: "#/components/schemas/Order"
        "404":
          description: Không tìm thấy đơn hàng.
          content:
            application/json:
              schema:
                $ref: "#/components/schemas/Error"
  /orders:
    post:
      operationId: createOrder
      summary: Tạo đơn hàng
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: "#/components/schemas/CreateOrderRequest"
      responses:
        "201":
          description: Tạo thành công.
          content:
            application/json:
              schema:
                $ref: "#/components/schemas/Order"
        "400":
          description: Yêu cầu không hợp lệ.
          content:
            application/json:
              schema:
                $ref: "#/components/schemas/Error"
components:
  schemas:
    CreateOrderRequest:
      type: object
      required: [customerId, amount]
      properties:
        customerId:
          type: string
        amount:
          type: number
          format: double
          minimum: 0
    Order:
      type: object
      required: [id, status, customerId, amount]
      properties:
        id:
          type: string
        status:
          type: string
          enum: [pending, paid, canceled]
        customerId:
          type: string
        amount:
          type: number
          format: double
    Error:
      type: object
      required: [code, message]
      properties:
        code:
          type: string
        message:
          type: string
~~~

Ở đây:

- API gateway có thể dùng một **API URL suffix** như orders.
- Operation template lấy đơn hàng là **GET /orders/{orderId}** tính theo phần operation path của API.
- Nếu API suffix cũng là orders, URL gateway hiệu dụng có thể chứa **/orders/orders/{orderId}**. Muốn thiết kế đường dẫn gọn cần tính cả suffix và operation path ngay từ lúc thiết kế, không tự assume APIM bỏ một đoạn trùng.
- **servers.url** là metadata trong OpenAPI; sau import phải xác minh rõ backend URL do APIM sử dụng, đặc biệt khi import từ nhiều môi trường.
- OpenAPI example trên chưa khai báo security scheme. Khi dùng production, cần bổ sung tài liệu bảo mật và policies thực thi tương ứng.

### 4.1. Kiểm tra contract trước import

Một quá trình contract review nên kiểm tra:

1. YAML/JSON hợp lệ, không trùng key.
2. OAS version được APIM hỗ trợ.
3. operationId rõ ràng, ổn định và không trùng.
4. Paths/methods không tạo ambiguity.
5. Path parameters có đúng khai báo required và schema không.
6. Request body/response status phù hợp backend thực tế.
7. Schemas, nullable/required và enum được dùng nhất quán.
8. Không đưa token, URL chứa credential hay dữ liệu khách hàng thật vào examples.
9. Cấu hình security được tài liệu hóa đúng, không hứa APIM tự enforce.
10. Các OpenAPI constructs không được APIM import hỗ trợ đã được phát hiện qua quá trình validate/import thử.

Việc YAML đúng cú pháp chỉ là điều kiện ban đầu. Một contract có thể hợp lệ nhưng **không tương thích** với những client đã triển khai.

## 5. Chuẩn bị Azure API Management

### 5.1. Những resource cần có

Giả sử kiến trúc lab:

~~~text
Subscription: sub-commerce-lab
Resource group: rg-api-lab
Region: southeastasia
APIM service: apim-commerce-lab
Backend: https://orders-backend.example.internal
API id: orders-api
API URL suffix: orders
OpenAPI file: orders-openapi.yaml
~~~

Tên resource và domain hoàn toàn minh họa; APIM service phải tồn tại, đã được provision và có gateway hoạt động. Không tự tạo APIM production khi chỉ làm bài thực hành; APIM có tier và mô hình giá/khả năng network/developer portal khác nhau.

### 5.2. Các câu hỏi trước khi import

- APIM resource ở subscription/resource group đúng chưa?
- Có Azure RBAC permission đủ để sửa API definitions không?
- API URL suffix có trùng API khác không?
- Backend đã tồn tại và có đường network từ APIM tới backend không?
- Backend cần OAuth token, mTLS, managed identity, header/API key hay cách khác?
- Product/subscription configuration có được xác định chưa?
- API đang có khách hàng gọi không, hay là API hoàn toàn mới?
- Có policy ở global/product/API/operation scope mà import có thể tương tác?
- Có monitoring/trace để quan sát request trước và sau thay đổi không?
- Có version/revision strategy và rollback owner chưa?

### 5.3. Xác minh Azure context

~~~bash
az account show --output table
az account set --subscription "<SUBSCRIPTION_ID>"

az apim show \
  --resource-group rg-api-lab \
  --name apim-commerce-lab \
  --query "{name:name,location:location,sku:sku.name,gatewayUrl:gatewayUrl}" \
  --output json
~~~

Đây là lệnh đọc metadata. Những giá trị query có thể khác theo API/CLI response; kiểm tra tài nguyên thực tế. Không tự suy ra tên APIM gateway host từ tên service nếu đang dùng custom domain.

## 6. Import OpenAPI bằng Azure Portal

### 6.1. Luồng thao tác

Trong Azure Portal:

1. Mở đúng Azure API Management instance.
2. Vào **APIs**.
3. Chọn tạo API từ **OpenAPI** hoặc mục Import tương ứng trong giao diện phiên bản đang dùng.
4. Cung cấp file OpenAPI hoặc URL theo tùy chọn được hỗ trợ.
5. Kiểm tra **Display name**, **Name/API identifier**, **API URL suffix**, protocols và backend Web service URL.
6. Nếu đang tạo API mới, chọn chiến lược version phù hợp hoặc tạo API trước rồi quản lý version set có chủ đích.
7. Import.
8. Mở danh sách operations, schemas và settings của API để xác nhận.
9. Thử từ gateway test console hoặc HTTP client có quyền.
10. Chỉ công bố API vào product và developer portal theo quy trình phê duyệt.

Không mặc định UI có cùng nút hoặc trường ở mọi APIM tier/giao diện. Quan trọng là kết quả cuối: API ID, path, backend, operations, chính sách và trạng thái công bố đúng như thiết kế.

### 6.2. Những field cần hiểu rõ

| Field | Tác dụng | Rủi ro nếu sai |
|---|---|---|
| Display name | Tên hiển thị trong Portal/developer portal | Client tìm nhầm API |
| Name/API identifier | Định danh quản trị APIM của API | Import trùng có thể cập nhật API đã tồn tại |
| API URL suffix | Phân vùng gateway route | Trùng đường dẫn hoặc URL không như contract |
| Web service URL | Địa chỉ backend APIM chuyển request tới | 404/502/timeout sai môi trường |
| Protocols | HTTP/HTTPS theo khả năng cấu hình | Mở protocol không mong muốn |
| Subscription required | Yêu cầu key theo product/API/subscription | API vô tình công khai hoặc test nhận 401 |
| API version | Identifier hợp đồng version theo version set | Client không biết gọi version nào |
| API revision | Bản cấu hình thay đổi của API | Ghi đè current thay vì tạo non-current |
| API products | Nhóm phân phối API | Partner không thấy API hoặc có quyền quá rộng |

### 6.3. Import từ file hay URL?

- **File trong pipeline:** xác định được commit và checksum; dễ review/rollback.
- **URL OpenAPI public/private:** tiện khi nguồn luôn cung cấp spec mới, nhưng cần kiểm soát availability, quyền truy cập, network, trust và nội dung có thay đổi giữa các lần import hay không.
- **Artifact trong CI/CD:** thường nên dùng versioned, immutable OpenAPI spec tạo từ build đã kiểm tra.

Không nên để production tự import "latest spec" từ một URL mutable mỗi lần deploy mà không kiểm tra diff và approval. Cùng URL có thể trả contract mới và làm thay đổi API ngoài kế hoạch.

## 7. Import OpenAPI bằng Azure CLI

### 7.1. Import một API mới

Giả sử đã lưu OpenAPI mẫu thành **orders-openapi.yaml** ở thư mục làm việc được phép. Lệnh minh họa:

~~~bash
az apim api import \
  --resource-group rg-api-lab \
  --service-name apim-commerce-lab \
  --api-id orders-api \
  --path orders \
  --specification-format OpenApi \
  --specification-path "./orders-openapi.yaml" \
  --service-url "https://orders-backend.example.internal"
~~~

Ý nghĩa:

- **--resource-group, --service-name:** xác định APIM resource.
- **--api-id:** ID quản trị API, không phải URL.
- **--path:** phần API URL suffix tại gateway.
- **--specification-format:** chỉ cách hiểu tài liệu OpenAPI.
- **--specification-path:** file mô tả API.
- **--service-url:** backend URL APIM sử dụng theo cấu hình.

Các giá trị **--specification-format** và flags hỗ trợ khác có thể thay đổi theo phiên bản Azure CLI, loại file OpenAPI (YAML/JSON) và tính năng được phát hành. Trước khi chạy thật, đối chiếu:

~~~bash
az apim api import --help
~~~

Nếu dự án dùng OpenAPI JSON, chọn đúng định dạng import mà CLI hiện tại hỗ trợ; không đổi tên đuôi file để thay cho chuyển đổi dữ liệu.

**Cảnh báo ghi đè:** nếu API ID đã tồn tại, import có thể cập nhật cấu hình API đó. Không chạy lệnh trên current production API để thử nghiệm một spec mới. Dùng API/instance lab hoặc tạo revision non-current trước.

### 7.2. Kiểm tra API sau import

~~~bash
az apim api show \
  --resource-group rg-api-lab \
  --service-name apim-commerce-lab \
  --api-id orders-api \
  --output json
~~~

Xem các APIs hiện có:

~~~bash
az apim api list \
  --resource-group rg-api-lab \
  --service-name apim-commerce-lab \
  --output table
~~~

Một số phiên bản Azure CLI có nhóm lệnh riêng để liệt kê operations và policies. Dùng Portal hoặc CLI help để xác nhận subcommands/parameters trước khi đưa vào pipeline production. Đừng chỉ kiểm tra API resource tồn tại; cần so sánh **tất cả operations/methods/templates** với OpenAPI input.

### 7.3. Kiểm tra bằng gateway HTTP

Giả sử gateway domain là **api.contoso.example**, APIM suffix là orders và spec operation path là /orders/{orderId}:

~~~bash
curl -i \
  "https://api.contoso.example/orders/orders/42" \
  -H "Accept: application/json" \
  -H "Ocp-Apim-Subscription-Key: <APIM_SUBSCRIPTION_KEY>"
~~~

Đường dẫn lặp orders trong ví dụ là chủ đích để nhấn mạnh quan hệ **API URL suffix + operation path**. Nếu chọn suffix khác, gateway URL sẽ khác. Tùy cấu hình subscription, authentication và policies, request có thể cần Bearer token thay thế hoặc bổ sung subscription key.

**Không lưu subscription key thật trong shell history, HTTP trace công khai hay tài liệu.** Tốt hơn là sử dụng secret store/terminal environment phù hợp rồi kiểm soát command logging.

### 7.4. Xác minh backend URL độc lập

APIM gateway URL và backend URL không giống nhau. Nếu gateway trả 404, kiểm tra:

1. APIM có API suffix đúng không?
2. Operation template có khớp URL không?
3. Request đang vào đúng version/revision không?
4. Policies có rewrite-uri hoặc set-backend-service không?
5. Backend có nhận path mong đợi không?

Nếu backend trả 404 còn gateway match operation thành công, lỗi có thể ở mapping path giữa APIM và backend. Không vội sửa OpenAPI contract trước khi xác định request nào thật sự đến backend.

### 7.5. So sánh trước và sau import

Một quá trình an toàn lưu các bằng chứng:

~~~text
Source commit:      <COMMIT_SHA>
OpenAPI checksum:   <SHA256>
APIM service:       apim-commerce-lab
API ID:             orders-api
Target revision:    <REVISION>
Imported at UTC:    <TIMESTAMP>
Operations before:  <COUNT / LIST>
Operations after:   <COUNT / LIST>
Policy diff:        <REVIEW_LINK>
Backend URL:        <EXPECTED_URL>
Approver:           <IDENTITY>
~~~

Thông tin trên là mẫu release record, không phải kết quả import đã thực hiện.

## 8. API version trong API Management

### 8.1. Khi nào cần version mới?

API version giúp chạy song song những hợp đồng mà client có thể không tương thích nhau.

Ví dụ:

~~~text
v1:
  GET /orders/{id}
  Response: {"id":"42","totalPrice":150}

v2:
  GET /orders/{id}
  Response: {"id":"42","total":{"amount":150,"currency":"USD"}}
~~~

Client v1 đọc totalPrice sẽ lỗi hoặc lấy sai dữ liệu nếu bị đổi thẳng sang v2. Khi thay đổi phá vỡ hợp đồng, nên xuất bản API version mới và giữ v1 trong giai đoạn migration đã được thỏa thuận.

### 8.2. Version set

Trong APIM, những API versions của cùng một hợp đồng logic có thể được tổ chức qua **API version set**. Version set mô tả cách client chọn version, ví dụ path, header hoặc query string. Mỗi version thường là một API resource có **API version identifier** và cấu hình tương ứng.

~~~mermaid
flowchart TD
    V["API Version Set: Orders"] --> V1["Version v1"]
    V --> V2["Version v2"]
    V1 --> R11["Revision 1"]
    V1 --> R12["Revision 2"]
    V2 --> R21["Revision 1"]
    V2 --> R22["Revision 2"]
    R11 -.-> C1["V1 current revision"]
    R21 -.-> C2["V2 current revision"]
~~~

Sơ đồ mang tính khái niệm: current revision tại một thời điểm là một revision của từng API version; trong thực tế dòng nối current sẽ thay đổi khi phát hành. Một version có thể tạo nhiều revisions độc lập mà không bắt client dùng version khác.

### 8.3. Phân biệt hai kiểu thay đổi

| Thay đổi | Ví dụ | Cách xem xét |
|---|---|---|
| Sửa mô tả operation | Cập nhật summary, ví dụ response | Revision thường phù hợp |
| Bổ sung response field tùy chọn | Thêm trackingCode optional | Có thể revision nếu mọi client vẫn tương thích |
| Bổ sung optional query parameter | Thêm sortBy optional | Có thể revision |
| Thêm operation mới | GET /orders/{id}/events | Có thể revision nếu không phá contract |
| Bỏ response field đang được dùng | Xóa totalPrice | Version mới |
| Đổi kiểu dữ liệu | totalPrice từ number thành object | Version mới |
| Đổi HTTP method hoặc URL bắt buộc | GET chuyển thành POST | Version mới |
| Siết required request field | Bắt buộc gửi customerSegment | Version mới nếu client cũ không gửi |
| Thay schema lỗi hoặc auth bắt buộc | Client cũ không đáp ứng | Phải đánh giá breaking change, thường version mới |
| Chuyển backend nội bộ nhưng giữ contract | App Service sang AKS | Có thể revision/rollout, thử tương thích |
| Đổi rate limit | 1000 req/phút xuống 100 | Có thể phá nhu cầu client dù schema không đổi; cần thông báo/kế hoạch |

**Tương thích không chỉ ở OpenAPI.** Authentication, status codes, error behavior, rate limit, latency, ordering, pagination và các side effects cũng thuộc hợp đồng thực tế.

### 8.4. Version identifier và semantic versioning

Một API public có thể công bố **v1**, **v2**; còn OpenAPI info.version hoặc backend release là 1.4.7, 2.1.0.

Không cần tạo API version mới cho mọi patch release của backend. Khi một phiên bản contract không đổi, các release code hoặc APIM revisions có thể tiếp tục dùng cùng version.

Cũng không nên gọi version mới là v2 chỉ vì đã tạo revision 2. Số revision và API version identifier có ý nghĩa khác nhau.

## 9. Ba cách xác định API version

### 9.1. Path (URL segment)

Client truyền version trong URL path:

~~~http
GET /v1/orders/42 HTTP/1.1
Host: api.contoso.example
Accept: application/json
~~~

Version v2:

~~~http
GET /v2/orders/42 HTTP/1.1
Host: api.contoso.example
Accept: application/json
~~~

**Ưu điểm:** dễ quan sát trong URL, cache key và log; người dùng dễ xem version.

**Nhược điểm:** thay version đổi URL; nếu client, proxy, reverse proxy hoặc SDK có routing cứng phải cập nhật.

Ví dụ trên mô tả một cách tổ chức path mong muốn. APIM kết hợp version segment với API URL suffix/operation path theo cấu hình version set; cần **kiểm tra URL thực tế mà Portal hiển thị**, không áp nguyên chuỗi ví dụ nếu đã đặt suffix khác.

### 9.2. Header

Version nằm trong HTTP header, ví dụ tên header tùy version set:

~~~http
GET /orders/42 HTTP/1.1
Host: api.contoso.example
api-version: v1
Accept: application/json
~~~

**Ưu điểm:** URL nhất quán giữa versions, thích hợp client có khả năng thêm header.

**Nhược điểm:** một số proxy/cache/log/SDK không giữ hoặc phân biệt header theo mặc định. Nếu cache response phải xét version header trong cache key và Vary/thiết kế gateway tương ứng.

Không tự chọn tên header là api-version nếu APIM version set được cấu hình tên khác.

### 9.3. Query string

Version trong query parameter:

~~~http
GET /orders/42?api-version=v1 HTTP/1.1
Host: api.contoso.example
Accept: application/json
~~~

**Ưu điểm:** dễ thử từ browser hoặc HTTP client, URL hiển thị version.

**Nhược điểm:** client phải giữ query parameter; cache/proxy/SDK phải phân biệt các variants. Nên tránh đưa secrets vào URL query vì query strings dễ lọt log; riêng version identifier không phải secret.

### 9.4. So sánh để quyết định

| Tiêu chí | Path | Header | Query |
|---|---|---|---|
| Client nhìn version trong URL | Có | Không | Có |
| SDK phải thêm header | Không | Có | Không |
| Ảnh hưởng URL khi nâng version | Có | Không | Có |
| Cache key cần cân nhắc | Theo path | Theo header | Theo query |
| Dễ thử thủ công | Cao | Vừa | Cao |
| Dễ chia sẻ URL có version | Cao | Thấp | Cao |
| Rủi ro proxy bỏ metadata | Thấp hơn với path | Có thể cao hơn | Cần kiểm tra query forwarding |

Chọn scheme dựa trên **cách client được phát triển**, cache/CDN/front door, API gateway routing và chính sách vận hành. Khi đã nhiều client dùng production, đổi scheme có thể là breaking change và cần kế hoạch migration riêng.

## 10. Tạo API version set và quản lý versions

### 10.1. Qua Azure Portal

Một quy trình điển hình:

1. Mở APIM → APIs.
2. Chọn API Orders hiện tại hoặc tạo version set phù hợp.
3. Chọn thao tác quản lý **Versions**.
4. Tạo/đặt **version set display name** và **versioning scheme** (Path/Header/Query).
5. Nhập identifier ví dụ **v1** cho API hiện tại hoặc tạo API version mới **v2**.
6. Xác minh API ID của v1/v2 không trùng và URL hiển thị đúng.
7. Import/tạo operations cho phiên bản mới theo hợp đồng của version đó.
8. Cấu hình backend URL, products, policies và test cho từng version.
9. Công bố version theo kênh và kế hoạch đã được phê duyệt.

Không mặc định mọi trường version set có thể đổi dễ dàng sau khi công bố. Nếu đổi versioning scheme, client có thể phải đổi URL/header/query và hệ thống cache/integration.

### 10.2. Tùy chọn Azure CLI

Azure CLI có nhóm lệnh quản lý APIM API version sets. Ví dụ cú pháp minh họa:

~~~bash
az apim api versionset create \
  --resource-group rg-api-lab \
  --service-name apim-commerce-lab \
  --version-set-id orders-versions \
  --display-name "Orders API versions" \
  --versioning-scheme Segment
~~~

Trong các phiên bản CLI, giá trị **Segment** có thể tương ứng với path/URL segment; những lựa chọn cho header/query có các thuộc tính tên header/query riêng. Trước khi chạy production cần xác minh:

~~~bash
az apim api versionset create --help
~~~

Không tự suy ra chỉ vì version set tồn tại là v1/v2 API objects cũng đã được tạo. Phải tạo hoặc liên kết từng API version với đúng version set theo công cụ hỗ trợ.

### 10.3. Liên kết một API version

Mỗi API version thuộc version set phải có:

- API ID riêng trong management plane.
- Version identifier, ví dụ v1 hoặc v2.
- Reference tới API version set.
- Operations và policies của version đó.
- Backend config và test cases.
- Products/subscriptions được công bố phù hợp.

Khi dùng CLI hoặc IaC, có thể cần truyền **API version set resource ID** thay cho display name. Lấy ID từ tài nguyên version set thực tế, không tự ghép bằng chuỗi nếu chưa xác minh subscription/resource group.

### 10.4. Tạo version mới không phải ghi đè version cũ

Một chiến lược phát hành v2:

~~~mermaid
flowchart TD
    C["Orders v1 đang phục vụ"] --> N["Thiết kế OpenAPI v2"]
    N --> D["Contract diff + breaking-change review"]
    D --> V["Tạo API v2 trong version set"]
    V --> I["Import OpenAPI v2 vào API v2"]
    I --> T["Test policy, backend, auth, responses"]
    T --> P["Công bố v2 cho nhóm client"]
    P --> M["Theo dõi adoption v1/v2"]
    M --> E["Deprecate/sunset v1 theo kế hoạch"]
~~~

**Không sửa OpenAPI info.version từ 1.0.0 sang 2.0.0 rồi giả định APIM tự tạo một API v2.** Version set và API version identifier phải được cấu hình rõ.

### 10.5. Giữ v1 trong giai đoạn chuyển đổi

Nếu client v1 vẫn đang hoạt động:

- Tiếp tục hỗ trợ v1 tới ngày sunset đã thông báo.
- Chỉ sửa lỗi bảo mật/tính ổn định cần thiết.
- Cung cấp migration guide và sample requests v2.
- Giám sát version traffic và những subscription/client đang gọi v1.
- Tránh thay backend response v1 theo schema v2 nếu không có adapter tương thích.
- Có rollback v2 độc lập mà không ảnh hưởng v1.

APIM có thể định tuyến v1/v2 tới cùng backend code với routes/policies khác nhau, nhưng việc đó chỉ an toàn khi backend hiểu cả hai hợp đồng và được kiểm thử.

## 11. API revision: thay đổi trong một version

### 11.1. Revision khác version

**Revision** cho phép tạo một bản thay đổi của **cùng API contract/version** để thử trước khi áp vào URL chính thức. Revision đặc biệt phù hợp cho:

- Thêm operation tương thích.
- Sửa documentation/examples.
- Cập nhật mapping/rewrite policy.
- Thay backend/service URL mà vẫn giữ contract.
- Bổ sung validation hoặc telemetry không phá client.
- Chuẩn bị policy thay đổi và kiểm thử trước khi công bố.

~~~mermaid
flowchart TD
    V["Orders v1"] --> R1["Revision 1: current"]
    V --> R2["Revision 2: non-current"]
    V --> R3["Revision 3: non-current"]
    R2 --> T["Test qua revision URL"]
    T --> G{"Release gate đạt?"}
    G -->|Có| C["Make revision 2 current"]
    G -->|Không| H["Giữ current revision 1"]
~~~

Với v2, có thể có revision 1, revision 2 riêng. Không xem revision 2 của v1 là API version v2.

### 11.2. Current và non-current

- **Current revision:** phiên bản cấu hình hiện tại phục vụ khách hàng qua gateway URL thông thường của API version.
- **Non-current revision:** bản thay đổi chưa được chuyển thành current, có thể được truy cập qua revision-specific gateway URL theo tính năng và chính sách.
- **Make current:** thao tác đưa một revision đã thử thành current, thay đổi cấu hình mà URL thông thường sử dụng.
- **Release notes:** ghi lý do và nội dung thay đổi phục vụ người dùng/internal audit.
- **Rollback:** có thể chọn một revision trước làm current lại nếu tình trạng và policy cho phép, nhưng phải xét backend/data side effects.

Tạo revision **không** đồng nghĩa tự động đưa nó thành current; đây chính là chỗ hữu ích cho việc test không làm ảnh hưởng ngay người gọi production.

### 11.3. Đường dẫn truy cập revision

APIM sử dụng cơ chế URL có suffix revision, thường thể hiện bằng **;rev={revisionNumber}** trong phần đường dẫn API. Ví dụ minh họa cho API suffix orders:

~~~text
Current:
  https://api.contoso.example/orders/orders/42

Non-current revision 2:
  https://api.contoso.example/orders;rev=2/orders/42
~~~

Đây là ví dụ trực quan; nếu APIM API versioning theo path/header/query thì URL hiệu dụng sẽ còn phụ thuộc **versioning scheme, API URL suffix và operation template**. Luôn lấy URL do Portal/gateway config cung cấp.

Một số client/proxy/router có thể xử lý dấu chấm phẩy trong path khác nhau. Kiểm tra WAF, Application Gateway/Front Door, reverse proxy và SDK thật trước khi dùng revision URL để test.

Non-current revision vẫn cần quyền gọi API theo cấu hình sản phẩm/subscription/policy tương ứng; **;rev=2 không phải một cơ chế xác thực**.

### 11.4. Tạo revision bằng Portal

1. Mở đúng API hoặc đúng **API version v1** trong APIM.
2. Vào **Revisions**.
3. Chọn **Add revision**.
4. Đặt revision number mới và mô tả thay đổi.
5. Giữ current revision hiện hành phục vụ traffic production.
6. Mở revision mới để import/update OpenAPI và policies cần thử.
7. Cấu hình/kiểm tra backend URL, operation templates, schemas.
8. Gọi revision-specific URL với auth, subscription key và test cases phù hợp.
9. Sau acceptance và approval mới chọn **Make current**.
10. Ghi release notes, thời gian, người phê duyệt, cấu hình/commit SHA và kết quả kiểm thử.

**Không sửa thẳng current revision khi đang chuẩn bị thay đổi chưa thử**. Việc import với cùng API ID nhưng không trỏ đúng revision mục tiêu có thể làm production thay đổi ngoài ý muốn.

### 11.5. Cấu hình import vào revision

Khi tự động hóa, phải xác định rõ **API revision target**, không chỉ API display name.

Một số công cụ APIM biểu diễn revision trong management API ID bằng hậu tố dạng **;rev=2**. Trong CLI/shell, dấu chấm phẩy phải được quote/escape đúng, ví dụ một API identifier có revision được giữ trong một string:

~~~text
orders-api;rev=2
~~~

Không giả định tất cả lệnh CLI/API đều nhận định danh này ở cùng tham số. Trước khi viết pipeline, kiểm tra công cụ đang dùng có yêu cầu API ID có revision suffix hay tham số revision riêng, và thử ở APIM lab. Chỉ thực hiện import khi chắc chắn nhắm **non-current revision**.

### 11.6. Make current và API release

Một workflow thường:

~~~mermaid
sequenceDiagram
    participant D as Developer / CI
    participant A as APIM Non-current Revision
    participant Q as QA / Security
    participant G as APIM Gateway Current
    participant M as Monitoring
    D->>A: Import OpenAPI + policies
    Q->>A: Test revision URL
    A-->>Q: Responses và trace
    Q->>D: Approval / sign-off
    D->>G: Make revision current
    G->>M: Traffic production theo cấu hình mới
    M-->>D: Error rate, latency, business checks
~~~

**Make current không tự deploy backend code.** Nếu revision tham chiếu backend mới, phải bảo đảm backend version đã sẵn sàng và tương thích. Một API release có thể ghi chú revision được đưa thành current; thông báo client và tài liệu hóa release cần được quản lý theo vòng đời riêng.

### 11.7. Rollback revision có giới hạn

Quay lại revision trước có thể khôi phục một phần cấu hình APIM như operations hoặc API-level policies theo semantics của revision. Nhưng không tự hoàn tác:

- Database schema migration đã chạy trong backend.
- Dữ liệu bị thay đổi bởi API mới.
- Secret rotation, Key Vault permissions, mạng/VNet/Private Endpoint ngoài API resource.
- Policies ở global/product scope đã được chỉnh riêng.
- Backend artifact đã được deploy/rollback độc lập.
- Cache, subscriptions, client state hay các service khác.

Vì vậy cần giữ bản backend tương thích hoặc có rollback/feature-flag plan; chỉ "Make old revision current" không phải một transaction phục hồi toàn hệ thống.

## 12. Chọn version hay revision: ma trận quyết định

| Tình huống | Khuyến nghị sơ bộ | Lý do |
|---|---|---|
| Sửa lỗi chính tả mô tả operation | Revision | Không làm thay đổi hợp đồng client |
| Thêm optional response field | Revision nếu kiểm thử tương thích | Client cũ thường bỏ qua field lạ, nhưng không phải tất cả |
| Thêm GET endpoint mới | Revision | Các operation cũ giữ nguyên |
| Thay mock bằng backend production, giữ contract | Revision | Chuyển implementation sau test |
| Đổi auth policy làm client cũ bị chặn | Version mới hoặc migration được quản trị | Đây là breaking operational behavior |
| Bỏ một required response field | Version mới | Client cũ có thể lỗi |
| Đổi property từ string sang number | Version mới | Schema breaking |
| Đổi path bắt buộc | Version mới | Client phải thay request |
| Đổi pagination semantics | Version mới nếu không tương thích | Client logic có thể sai |
| Đổi timeout/429 quota mạnh | Release change có thông báo, cân nhắc version | Không chỉ là schema |
| Phát hành bugfix backend không đổi contract | Release/revision theo quản trị | Không cần nhân API versions |
| Mở beta API cho nhóm client độc lập | Version/preview API theo chiến lược | Không nhầm revision URL thành public beta lâu dài |
| Muốn thử policy mới trước khi áp production | Non-current revision | Có test endpoint và promotion gate |

**Không dùng số version như cách tránh phải kiểm thử.** API v2 vẫn cần contract tests, security tests và backend observability.

### 12.1. Một quy tắc thực dụng

- Thay đổi phá client → tạo **version mới**.
- Thay đổi tương thích, cần thử trước khi công bố → tạo **revision mới**.
- Chỉ thay đổi backend deploy và không tác động APIM configuration → quản lý qua CI/CD backend; có thể không cần revision nếu không có yêu cầu audit/promotion APIM.
- Thay đổi security, routing, quota hoặc lỗi nghiệp vụ không hiển thị trong schema → đánh giá tác động như breaking change, không quyết định chỉ từ OpenAPI diff.

## 13. Quy trình chuẩn từ contract đến release

### 13.1. Contract-first workflow

~~~mermaid
flowchart TD
    R["Requirement / change request"] --> O["Sửa OpenAPI trong Git"]
    O --> D["OpenAPI lint + diff"]
    D --> B{"Có breaking change?"}
    B -->|Có| V["Tạo API version mới"]
    B -->|Không| N["Tạo non-current revision"]
    V --> I["Import đúng API target"]
    N --> I
    I --> T["Validate operations, policies, backend"]
    T --> S["Security + contract tests"]
    S --> A{"Approval"}
    A -->|Không| F["Giữ phiên đang phục vụ"]
    A -->|Có| P["Make revision current / Publish version"]
    P --> M["Monitor errors, latency, adoption"]
    M --> K["Release notes + rollback readiness"]
~~~

Không phải mọi CI pipeline đều có khả năng tự tạo revision giống nhau; dùng API Management REST/ARM/Bicep/CLI được hỗ trợ và đã kiểm thử, không coi thao tác Portal thủ công là toàn bộ nguồn sự thật nếu muốn vận hành có thể tái lập.

### 13.2. Trước khi import vào APIM

1. Review OpenAPI diff từ commit so với version/revision current.
2. Chạy linter/schema validation bằng công cụ được nhóm chọn.
3. Phân loại breaking/non-breaking.
4. Có rollback/compatibility plan cho backend, database và messaging.
5. Xác định APIM service, version set, API ID và revision target.
6. Chốt backend URL, identity, networking và policies cần áp.
7. Ghi artifact SHA/commit SHA và approver.
8. Sao lưu/export metadata cần cho rollback nếu quá trình quản lý yêu cầu.
9. Không để pipeline import thẳng current production nếu change chưa được QA.

### 13.3. Sau khi import

Đối chiếu OpenAPI gốc với APIM API:

| Kiểm tra | Cần xác minh |
|---|---|
| API ID và URL suffix | Đúng tên, không trùng route |
| API version/version set | Identifier và scheme đúng |
| Target revision | Non-current hay current như kế hoạch |
| Operations | Số lượng, method, path templates |
| Parameters | Required/path/query/header chính xác |
| Request/response schemas | Không bị bỏ qua phần quan trọng |
| Backend URL | Đúng dev/staging/prod |
| Policies | Auth, CORS, transformation, throttling vẫn hoạt động |
| Products/subscriptions | Đúng nhóm người dùng được phép |
| Developer portal | Tài liệu/try-it/links hợp lệ khi công bố |
| Gateway connectivity | HTTP 2xx/4xx/5xx và TLS/network đúng |
| Monitoring | Diagnostics/logs có dữ liệu |
| Contract tests | Client v1/v2 hoạt động tương thích |
| Rollback | Có current/previous revision và thao tác phục hồi |

Nếu import cảnh báo unsupported OpenAPI constructs, không bỏ qua chỉ vì HTTP GET thử trả 200. Cần ghi nhận phần nào không được nhập và liệu nó có ảnh hưởng validation/client documentation hay không.

## 14. Kiểm thử gateway, version và revision

### 14.1. Ma trận test tối thiểu

| Test | Current v1 | Revision v1 non-current | Version v2 |
|---|---|---|---|
| GET /orders/{id} hợp lệ | 200 theo v1 schema | 200 theo schema revision dự kiến | 200 theo v2 schema |
| ID không tồn tại | 404 có error contract v1 | 404 có format được thử | 404 theo v2 contract |
| Payload POST sai | 400/422 theo hợp đồng | Còn tương thích với v1 | Theo v2 |
| Thiếu subscription/token | Từ chối theo policy | Từ chối tương tự, trừ khi test riêng | Từ chối theo v2 policy |
| Không đủ quyền | 403 theo policy | 403 | 403 |
| Rate limit | Chính sách hiện hành | Chính sách mới nếu đang thử | Policy đã định |
| Backend timeout | Error mapping/observability | Kiểm tra no regressions | Kiểm tra riêng |
| OpenAPI contract | v1 | Non-breaking v1 | v2 |
| Metrics/tracing | Baseline | So sánh trong test | Theo version adoption |

HTTP status cụ thể phụ thuộc contract và policies thật; không phải mọi lỗi validation đều bắt buộc trả 422. Mục tiêu là kiểm tra đúng **những gì API đã cam kết**.

### 14.2. Test auth và subscription

APIM subscription key thường được truyền qua header được cấu hình, ví dụ:

~~~http
GET /orders/orders/42 HTTP/1.1
Host: api.contoso.example
Ocp-Apim-Subscription-Key: <SUBSCRIPTION_KEY>
Authorization: Bearer <ACCESS_TOKEN>
Accept: application/json
~~~

Có thể API chỉ yêu cầu một trong hai hoặc cả hai, tùy product/subscription và validate-jwt/validate-azure-ad-token policy đã cấu hình. **OpenAPI securitySchemes không làm gateway tự yêu cầu và kiểm tra JWT** nếu chưa có policy hoặc cơ chế xác thực phù hợp.

### 14.3. Những lỗi phổ biến cần phân biệt

- **401:** subscription key thiếu/sai, bearer token không hợp lệ hoặc policy authentication từ chối theo cấu hình.
- **403:** caller đã xác định nhưng thiếu quyền, bị chặn IP/policy/product, hoặc backend từ chối.
- **404:** APIM không tìm thấy API/operation/version/revision route hoặc backend trả 404 sau routing.
- **405:** method không được phép hoặc operation không được import/định tuyến như mong đợi.
- **429:** rate-limit/quota hoặc backend throttling; xác định lỗi phát sinh ở gateway hay backend.
- **500:** policy expression hoặc backend/internal error; cần logs/trace.
- **502/503/504:** backend connectivity, DNS/TLS, timeout, upstream availability hoặc gateway issue.

Không tự kết luận 404 là do OpenAPI sai path. Cần trace request thực tế qua gateway và backend để xác định lớp lỗi.

### 14.4. Kiểm tra version routing đúng scheme

Nếu path versioning:

~~~text
Call current v1 via v1 URL.
Call new v2 via v2 URL.
Do not omit version segment if required.
~~~

Nếu header versioning:

~~~http
GET /orders/orders/42 HTTP/1.1
Host: api.contoso.example
api-version: v2
~~~

Nếu query versioning:

~~~http
GET /orders/orders/42?api-version=v2 HTTP/1.1
Host: api.contoso.example
~~~

Các URL chỉ minh họa; path và tên header/query thực tế phụ thuộc version set. Đặc biệt cần test proxy/CDN/cache để tránh response v2 bị phục vụ cho request v1.

### 14.5. Test revision URL

Sau khi tạo revision 2:

~~~text
Current v1:
  https://api.contoso.example/orders/orders/42

Non-current revision 2:
  https://api.contoso.example/orders;rev=2/orders/42
~~~

Đối với API đã có version scheme, lấy URL cụ thể từ APIM và thêm revision theo routing được hỗ trợ. Khi test, giữ nguyên subscription/auth chính sách. Đừng cho phép endpoint revision lộ dữ liệu chưa công bố chỉ vì client phải biết cú pháp ;rev=2.

## 15. Backend, policies và OpenAPI contract cần nhất quán

### 15.1. APIM không làm backend tự tương thích

Giả sử revision 2 thêm field discountCode trong request body. Backend code v1 có thể bỏ qua field hoặc trả 400. Import vào APIM không tự deploy backend hiểu field đó.

Một release cần bảo đảm:

- Backend đã hỗ trợ contract mới hoặc có adapter.
- APIM mapping/rewrite policies đúng.
- Các field/headers bị policy xóa hoặc đổi được ghi nhận.
- Error codes/messages đúng hợp đồng.
- Backend version không làm API v1 bị phá khi cùng chia sẻ dịch vụ.
- Data migration/DB schema tương thích với các phiên đang hoạt động.
- Có rollback đường API và backend.

### 15.2. Các policy scopes

APIM policies có thể được áp ở nhiều scope, ví dụ:

- Global.
- Product.
- API.
- Operation.

Hiệu lực thực tế liên quan thứ tự/chính sách kế thừa và cách dùng **base**. Khi thử revision mới, không được giả định policies ở product/global sẽ tự được version hóa cùng API revision. Thay đổi một policy global có thể ảnh hưởng cả v1 và v2 dù chỉ sửa một đoạn XML.

Các nhóm policy thường dùng:

| Policy | Mục tiêu | Điều cần kiểm tra |
|---|---|---|
| validate-jwt / Entra token validation | Xác thực JWT | Issuer/audience, keys, claims, expiry |
| rate-limit / quota | Bảo vệ backend, phân bổ quyền sử dụng | Scope counter, client key, 429 |
| set-backend-service | Chọn backend | Môi trường, TLS, DNS, failover |
| rewrite-uri | Ánh xạ gateway path tới backend path | Path params, method, query |
| set-header | Thêm/bỏ/đổi headers | Không làm rò token hoặc phá signature |
| CORS | Quy định browser origins/headers | Không thay thế authentication |
| validate-content / validate-parameters | Kiểm tra request/response theo cấu hình được hỗ trợ | Runtime cost, schema support và error behavior |
| cache | Giảm backend requests | Cache key phải tách version/auth/tenant đúng |
| trace/logging | Chẩn đoán request | Không log secrets/PII |

Không mặc định OpenAPI import sẽ tự tạo tất cả policy validation. Việc documentation và runtime enforcement là hai phần có thể khác nhau.

### 15.3. OpenAPI securitySchemes là lời mô tả, không phải quyền

Ví dụ tài liệu có:

~~~yaml
components:
  securitySchemes:
    bearerAuth:
      type: http
      scheme: bearer
      bearerFormat: JWT
security:
  - bearerAuth: []
~~~

Đoạn này nói client cần Bearer token theo hợp đồng. Để APIM thực sự kiểm tra JWT claims và issuer, cần policy/tích hợp authentication phù hợp; backend cũng cần được bảo vệ theo kiến trúc. Không coi securitySchemes là cơ chế chặn truy cập tự động.

### 15.4. Managed identity tới backend

Nếu backend hỗ trợ Microsoft Entra ID, APIM có thể sử dụng managed identity và policy phù hợp để lấy token gọi backend theo khả năng sản phẩm. Cần:

1. Bật identity cho APIM resource theo kịch bản hỗ trợ.
2. Cấp APIM identity quyền ở backend/resource.
3. Cấu hình token resource/audience đúng.
4. Đảm bảo network DNS/routing và TLS.
5. Kiểm tra policy đúng scope/version/revision.
6. Không log bearer token hoặc backend credentials.

Nếu backend là Azure Function có function key, dùng named values/Key Vault integration và chính sách bảo vệ phù hợp; đừng ghi key thẳng vào OpenAPI examples hay source pipeline.

## 16. Versioning và revisions trong CI/CD

### 16.1. Một nguồn sự thật

Quản trị API production nên có nguồn cấu hình có thể review:

~~~text
Repository
  ├─ openapi/orders-v1.yaml
  ├─ openapi/orders-v2.yaml
  ├─ apim/api-definitions/
  ├─ apim/policies/
  ├─ apim/version-sets/
  ├─ tests/contract/
  └─ release-metadata/
~~~

Cấu trúc trên chỉ để minh họa kiến trúc thư mục **trong dự án của nhóm**, không phải yêu cầu tạo file khi thực hiện bài học. Không tạo những file này chỉ từ ví dụ.

Có thể sử dụng Bicep, Terraform, ARM templates, APIM DevOps tooling hoặc REST/CLI theo công cụ được tổ chức chọn. Quan trọng là version set, API metadata, policies và import source đều được đưa vào change control.

### 16.2. Pipeline release an toàn

~~~mermaid
flowchart TD
    S["OpenAPI commit"] --> L["Lint / validate OAS"]
    L --> D["Diff với current contract"]
    D --> C{"Breaking change?"}
    C -->|Có| V["New API version"]
    C -->|Không| R["New non-current revision"]
    V --> I["Import into target"]
    R --> I
    I --> Q["Contract + gateway security tests"]
    Q --> G{"Approval"}
    G -->|Fail| H["Giữ production current"]
    G -->|Pass| P["Publish version / Make current"]
    P --> O["Monitor + release notes"]
~~~

Tách vai trò:

- CI identity đọc source, xây OpenAPI artifact và chạy linter.
- CD identity được phép import vào APIM staging hoặc non-current revision.
- Release approver quyết định thay current/publish version.
- APIM runtime identity truy cập backend theo least privilege.
- API clients dùng subscription/Entra credentials ở data plane.

Không cấp Owner toàn subscription cho pipeline chỉ để import một API.

### 16.3. Kiểm soát drift khi sửa Portal thủ công

Nếu nhóm quản lý APIM bằng IaC nhưng người khác chỉnh operation/policy trực tiếp trong Portal:

- Lần deploy tiếp theo có thể ghi đè sửa đổi.
- Bản OpenAPI không còn phản ánh runtime.
- Audit trail khó xác định nguồn thay đổi.
- Một revision có thể không có bản xuất/release record tương ứng.

Cần quy định thay đổi production qua PR/change ticket; nếu sửa khẩn cấp trong Portal, phải cập nhật lại IaC/source và ghi reconciliation.

### 16.4. Release metadata

~~~yaml
releaseId: "orders-api-v1-rev3-2026-11-20"
apimService: "apim-commerce-lab"
apiId: "orders-v1"
apiVersionSet: "orders-versions"
apiVersion: "v1"
revision: "3"
previousCurrentRevision: "2"
sourceCommit: "<COMMIT_SHA>"
openapiChecksum: "<SHA256>"
backendVersion: "<BUILD_SHA>"
approval: "<APPROVER_ID>"
changeType: "non-breaking"
tests:
  contract: "passed"
  gatewayAuth: "passed"
  backendConnectivity: "passed"
  regression: "passed"
rollback:
  previousRevisionAvailable: true
  backendCompatible: true
~~~

Đây là metadata minh họa, **không phải schema bắt buộc của Azure CLI/APIM**. Trạng thái "passed" cần có log/artifact kiểm chứng thực tế; không viết vào production release record nếu chưa chạy.

## 17. Chiến lược rollback và quản trị client migration

### 17.1. Rollback API revision

Nếu vừa đưa revision 3 thành current và phát hiện lỗi policy:

1. Xác định tác động: 401, 403, 429, 5xx, response schema, affected clients.
2. Kiểm tra backend/data có thay đổi không.
3. Nếu phù hợp, đưa revision 2 đã biết tốt thành current theo quy trình APIM.
4. Đối chiếu gateway responses với baseline.
5. Theo dõi rate/latency và các transactions.
6. Ghi incident/release note và hành động phòng ngừa.

**Quay lại current revision** có thể phục hồi route/policy thuộc revision nhưng không tự rollback một database migration hoặc policy global đã bị sửa.

### 17.2. Rollback API version

Nếu v2 gặp lỗi, client đang gọi v2 thường cần:

- Điều chỉnh client routing/feature flag nếu có thể.
- Hoặc triển khai bugfix cho v2.
- Hoặc giữ v1 còn hoạt động để client chuyển về.
- Kiểm tra dữ liệu v2 đã ghi có còn đọc được từ v1 không.

Không thể buộc client v2 quay lại v1 chỉ bằng cách đổi current revision của API v1; **version v1 và version v2 là hai tuyến hợp đồng riêng**.

### 17.3. Deprecation và sunset

Một kế hoạch v1 → v2:

1. Công bố v2 cùng docs, OpenAPI contract và migration guide.
2. Cho client thử staging/sandbox nếu có.
3. Theo dõi traffic, version identifier, response errors và subscription/client adoption.
4. Gửi thông báo deprecation có mốc ngày cụ thể.
5. Hỗ trợ giai đoạn chuyển tiếp theo SLA.
6. Có thể cung cấp response headers deprecation/sunset phù hợp chính sách nếu muốn; phải tự cấu hình và kiểm tra.
7. Chỉ gỡ v1 khi yêu cầu pháp lý/hợp đồng và quan sát cho phép.
8. Giữ release records, audit và rollback strategy trong giai đoạn dừng.

Không xóa một version đã công bố chỉ vì số lượng request thấp trong một ngày. Có thể còn client chạy theo lịch tháng hoặc batch jobs.

### 17.4. Version adoption metrics

Theo dõi:

- Request count theo version, product và subscription/client identifier (đã xử lý privacy).
- Error rates và latency p95/p99 theo version.
- Các operations v1 còn được sử dụng.
- Tỷ lệ success ở client v2 mới.
- Các integration tests của đối tác.
- Ngày yêu cầu ngừng hỗ trợ theo hợp đồng.

Cần bảo vệ thông tin danh tính khách hàng và không đưa subscription keys hoặc bearer tokens vào log analytics.

## 18. Bảo mật khi import, test và công bố API

### 18.1. Quyền quản lý APIM

Dùng Azure RBAC và PIM theo nguyên tắc tối thiểu:

- Người thiết kế có thể review OpenAPI mà không cần quyền chỉnh production APIM.
- CI/CD automation có quyền import trong scope được kiểm soát.
- Người phê duyệt có quyền chuyển revision current theo quy trình.
- Người vận hành có quyền đọc diagnostics và xử lý sự cố.
- Không cấp quyền xóa APIM service cho người chỉ cần cập nhật một API.

### 18.2. Bảo vệ dữ liệu và credentials

- Không lưu APIM subscription key trong OpenAPI/examples.
- Không nhúng backend API key vào spec hoặc CLI logs.
- Dùng Key Vault/named values theo tính năng APIM hỗ trợ.
- Khi import qua URL, kiểm soát nguồn và checksum artifact.
- Chỉ gọi revision test bằng tài khoản/subscription phù hợp.
- Cấu hình validate-jwt, IP restrictions, mTLS, CORS và rate limit theo threat model.
- Không tin rằng một endpoint revision "khó đoán" là đã được bảo vệ.
- Che PII trong trace và response bodies khi cần.
- Bảo vệ developer portal và chỉ hiển thị APIs cho đúng products/audience.

### 18.3. Networking

APIM có thể gọi backend qua public/private network tùy tier/mạng:

- Kiểm tra backend DNS.
- Kiểm tra VNet/Private Endpoint/VNet integration khi cần.
- Kiểm tra outbound TLS và certificate trust.
- Kiểm tra WAF/Front Door, proxy và path/header forwarding.
- Kiểm tra application-level auth tới backend.
- Không mở firewall cho toàn Internet để sửa nhanh một lỗi APIM 502.

Gateway request 502 do không kết nối được backend không tự động là lỗi OpenAPI import; phải xem network, DNS, TLS và backend logs.

## 19. Monitoring và chi phí API Management

### 19.1. Dữ liệu cần quan sát

| Tín hiệu | Câu hỏi vận hành |
|---|---|
| Gateway request count | Version nào đang được gọi? |
| 4xx theo API/version | Client/auth/version routing sai hay thay đổi contract? |
| 429 | APIM rate limit hay backend throttling? |
| 5xx | Policy/gateway/backend lỗi? |
| Gateway response duration | APIM có tăng độ trễ không? |
| Backend response duration | Backend có chậm hơn sau release? |
| Policy errors | Expression/JWT/rewrite có lỗi? |
| Product/subscription usage | Nhóm client nào bị ảnh hưởng? |
| APIM capacity/scale | Tier có đủ tải? |
| Backend availability | Dịch vụ đích có sẵn sàng không? |
| Cost by resource/tag | APIM tier, logs, networking và backend tốn bao nhiêu? |

### 19.2. Log và trace có thể phụ thuộc cấu hình

Sử dụng Azure Monitor metrics, APIM diagnostics, Log Analytics và Application Insights integration theo tính năng được bật. Đối với troubleshooting, ghi:

- Timestamp UTC.
- APIM service/API ID.
- Version identifier/revision.
- Operation và request ID/correlation ID.
- Gateway status, backend status.
- Durations/latency.
- Policy/error code đã được chuẩn hóa.
- Backend version/build ID nếu ứng dụng cung cấp.
- Client identity/subscription identifier ở mức cần thiết, không ghi keys/tokens.

Không mặc định mọi request/response body được lưu: logging có sampling, privacy và retention. **Không bật full body logging trên dữ liệu nhạy cảm** chỉ để so sánh revision.

### 19.3. Alert sau Make current

Trong cửa sổ theo dõi (ngưỡng là ví dụ, phải theo baseline thật):

- 5xx vượt ngưỡng đã thống nhất trong 5 phút.
- 401/403 tăng đột ngột sau thay đổi auth policy.
- 404/405 tăng ở operations mới import.
- 429 tăng khi sửa rate-limit policy.
- p95 latency tăng bất thường.
- Backend dependency/health thất bại.
- Không có telemetry từ gateway sau thay đổi diagnostics.
- Version adoption hoặc client regression khác kỳ vọng.

Không tự rollback khi chỉ thấy một metric trừ khi đã có quy tắc quyết định và người chịu trách nhiệm. Một số lỗi có thể đến từ backend hoặc data migration mà APIM rollback không giải quyết.

### 19.4. Chi phí cần xem

Azure API Management có các service tiers/mô hình tính phí, khả năng capacity và network khác nhau. Khi thiết kế nhiều versions/revisions:

- Bản thân version/revision là cấu hình gateway, không đồng nghĩa tạo một APIM instance khác; nhưng mọi phiên cùng dùng khả năng/tải của APIM service.
- APIM capacity/tier/scale quyết định phần lớn chi phí gateway theo mô hình được chọn.
- Mỗi API version có thể làm tăng số request, policies và chi phí backend.
- Application Insights/Log Analytics có phí ingestion và retention.
- Custom domains/certificates, networking, WAF/Front Door và private networking có thể có chi phí phụ.
- Cache hoặc policy nặng có thể tác động độ trễ/compute.
- Giữ nhiều API versions cũ làm tăng chi phí vận hành và hỗ trợ đối tác.

Không chọn Premium/isolated tiers chỉ vì cần một ví dụ version mới; phải kiểm tra tính năng và giá theo nhu cầu thực tế, region, VNet và SLA.

## 20. Tình huống thực tế: Orders API từ v1 sang v2

### 20.1. Bối cảnh

Một doanh nghiệp có:

- Mobile app v1 gọi Orders API và đọc totalPrice.
- Partner integrations dùng subscription keys riêng.
- Backend chạy App Service với database đơn hàng.
- APIM gateway bảo vệ API bằng Entra auth policy cho nhóm internal và subscription/product phù hợp cho partner.
- Nhóm phát triển muốn thêm cấu trúc money mới **total.amount + total.currency**.

Thay totalPrice bằng object là breaking change. Kế hoạch an toàn:

1. Giữ Orders v1 hoạt động.
2. Tạo Orders v2 trong version set.
3. Import OpenAPI v2 tương thích backend mới.
4. Backend hỗ trợ cả v1/v2 hoặc có adapter/route riêng.
5. Test security và response schemas của hai version.
6. Công bố v2 cho nhóm client thử nghiệm.
7. Theo dõi migration theo product/subscription.
8. Trong v2, dùng revision để thử thêm optional field hoặc chỉnh policy.
9. Chỉ sunset v1 sau thời hạn thông báo và xác nhận client đã nâng cấp.

### 20.2. Mô hình phát hành

~~~mermaid
flowchart TD
    VS["Orders Version Set"] --> V1["API v1"]
    VS --> V2["API v2"]
    V1 --> B1["Backend adapter v1"]
    V2 --> B2["Backend adapter v2"]
    V2 --> R1["Revision 1 current"]
    V2 --> R2["Revision 2 non-current"]
    R2 --> T["Test policy/operation"]
    T --> C["Make revision 2 current"]
    B1 --> DB["Orders database"]
    B2 --> DB
~~~

Nếu database schema phải thay, dùng migration tương thích ngược (ví dụ expand–migrate–contract) để cả v1 và v2 hoạt động trong giai đoạn chuyển tiếp. APIM versioning không tự điều phối database migration.

### 20.3. Release runbook

~~~yaml
release:
  service: "apim-commerce-lab"
  resourceGroup: "rg-api-prod"
  versionSet: "orders"
  apiId: "orders-v2"
  version: "v2"
  targetRevision: "2"
  previousCurrentRevision: "1"
  openapiArtifact: "orders-v2.yaml"
preflight:
  - "Confirm API version set and routing scheme"
  - "Confirm revision 2 is non-current"
  - "Check OpenAPI diff and unsupported constructs"
  - "Validate backend URL and Entra/Key Vault permissions"
  - "Test gateway revision URL and policy inheritance"
  - "Contract regression for both v1 and v2"
approval:
  required: true
promotion:
  action: "Make revision 2 current"
postRelease:
  - "Verify normal v2 URL serves revision 2"
  - "Check 4xx/5xx/429/p95 latency"
  - "Confirm v1 contract remains valid"
  - "Record release notes and source SHA"
rollback:
  - "Evaluate backend/data compatibility"
  - "If safe, make revision 1 current again"
  - "Run gateway and business smoke tests"
~~~

Runbook YAML này là **mẫu nghiệp vụ**, không phải cấu hình để chạy trực tiếp trên Azure CLI hoặc DevOps. Các giá trị như "Confirm..." là bước phải có bằng chứng thực hiện.

### 20.4. Tiêu chí hoàn thành release

- OpenAPI v1 và v2 có artifact/checksum xác định.
- API versions chọn đúng qua path/header/query.
- Mỗi version có API ID rõ và thuộc đúng version set.
- Revision mới đã được kiểm thử mà không sửa current trước approval.
- Authentication, subscription policies và product visibility đúng.
- Backend nhận đúng đường dẫn, token và schema.
- v1 client không bị ảnh hưởng bởi release v2.
- Gateway logs thể hiện đúng API version/operation và request status.
- Có migration guide và ngày sunset v1.
- Có khả năng quay lại revision cũ và tương thích dữ liệu.

## 21. Xử lý sự cố thường gặp

| Triệu chứng | Nguyên nhân khả dĩ | Hướng xử lý |
|---|---|---|
| Import báo invalid OpenAPI | YAML/JSON lỗi, OAS version unsupported, schema construct không hỗ trợ | Validate OAS, xem warnings, chỉnh format |
| Import thành công nhưng thiếu operation | Operation template không được hỗ trợ, lỗi path/parameter | So sánh operations sau import với source |
| API ID đã tồn tại | Import nhắm API production thay vì API mới | Dừng, xác nhận target, tạo revision/API ID đúng |
| Gateway trả 404 | API suffix + operation path sai, version identifier thiếu | Kiểm tra URL thật, method và scheme |
| Backend trả 404 | APIM rewrite/set-backend-service chuyển path sai | Xem APIM/backend trace, kiểm tra URL |
| Header version không có hiệu lực | Header name sai hoặc proxy bỏ header | Kiểm tra version set và forwarding |
| Query version không có hiệu lực | Query parameter name/value sai | So sánh với version set settings |
| Revision URL không truy cập | ;rev suffix đặt sai, proxy xử lý dấu chấm phẩy, auth | Lấy URL thật và thử direct gateway |
| Non-current revision làm production đổi | Import nhầm current API | Khôi phục config/revision, sửa CD targets |
| Cả v1 và v2 cùng lỗi sau policy change | Policy global/product thay đổi | Kiểm tra policy inheritance và rollback scope đúng |
| 401/403 sau import | Subscription/product/auth policy sai hoặc thiếu quyền backend | Phân biệt gateway auth với backend auth |
| 429 sau Make current | Rate-limit/quota policy thay đổi hoặc backend throttling | So sánh counter/quotas/logs |
| 500 sau sửa policy | Policy expression lỗi hoặc mapping mới không hợp lệ | Trace policy và test rollback |
| 502/503/504 | Backend DNS, TLS, network, service unavailable | Kiểm tra APIM→backend connectivity |
| OpenAPI securitySchemas có nhưng client vẫn gọi được | Chưa có policy auth thực thi | Cấu hình validate-jwt/authorization |
| Custom domain hoạt động nhưng revision thất bại | WAF/proxy path rewrite làm mất ;rev | Kiểm tra end-to-end routing |
| Client v1 hỏng sau import v2 | Backend shared schema/policy phá v1 | Contract regression, backend compatibility |
| Revision rollback vẫn lỗi | Database/backend/global policy thay đổi ngoài revision | Recovery ở layer liên quan |
| Developer portal không thấy v2 | Chưa publish vào đúng product hoặc portal config | Kiểm tra product/visibility/publishing |
| APIM logs không có request | Diagnostic/sampling chưa bật hoặc sai workspace | Kiểm tra telemetry pipeline |

### 21.1. Thứ tự điều tra

1. **Azure resource:** đúng subscription, service và API ID?
2. **Route:** đúng suffix, version set scheme, version identifier và revision?
3. **Operation:** method/path template có trong APIM?
4. **Product/subscription:** key và quyền đã hợp lệ?
5. **Policies:** auth, rewrite, backend routing, rate limit có thay đổi?
6. **Backend:** DNS/TLS/network/service URL và runtime có sẵn sàng?
7. **Contract:** request/response có khớp OpenAPI đã import?
8. **Metrics:** error rate, latency, client version distribution thế nào?
9. **Release metadata:** commit, revision, backend artifact và thời gian nào?
10. **Rollback:** có bản config trước và data compatibility không?

Không giải quyết lỗi 404 bằng cách công khai backend trực tiếp lên Internet hoặc xóa hết policies. Mục tiêu là xác định lỗi ở gateway routing, authorization hay backend.

## 22. Checklist production

### Hợp đồng OpenAPI

- [ ] OpenAPI version và file YAML/JSON được APIM hỗ trợ.
- [ ] operations, parameters, requestBody và response schemas đầy đủ.
- [ ] operationId duy nhất và ổn định.
- [ ] Không có secret/tài khoản thật trong spec/examples.
- [ ] OpenAPI diff đã phân loại breaking/non-breaking.
- [ ] Tài liệu info.version không bị nhầm với APIM API version.
- [ ] Import warnings và unsupported fields đã được xem xét.
- [ ] Có artifact checksum và source commit.

### Version và revision

- [ ] Version set đã chọn scheme Path/Header/Query phù hợp client.
- [ ] v1/v2 có API IDs riêng, thuộc đúng version set.
- [ ] Version identifier xuất hiện đúng trong gateway requests.
- [ ] Change tương thích được thử ở non-current revision.
- [ ] Current revision chưa đổi trước khi được phê duyệt.
- [ ] Revision URL đã được test qua cả gateway và proxy thực tế.
- [ ] Make current đi kèm release note, approver và timestamp.
- [ ] Revision rollback và backend rollback đã được đánh giá.
- [ ] v1 client vẫn được hỗ trợ trong migration window.

### Bảo mật và mạng

- [ ] Backend URL, TLS/DNS và private networking đúng.
- [ ] APIM identity/Key Vault/named values được cấp quyền tối thiểu.
- [ ] Subscription products và scopes không công khai nhầm API.
- [ ] JWT/auth policies thực thi đúng; không chỉ dựa trên OpenAPI security metadata.
- [ ] CORS, rate limits, cache keys và rewrite policies đã kiểm tra.
- [ ] Không log subscription keys, Bearer tokens hoặc PII.
- [ ] CI/CD identity không có quyền rộng hơn mức cần import/phát hành.

### Giám sát và vận hành

- [ ] Có smoke tests cho gateway current/revision/version.
- [ ] 4xx/5xx/429 và p95 latency có baseline/alert.
- [ ] Có client adoption metrics theo version.
- [ ] Có backend health và dependency logs.
- [ ] Có incident runbook khi import/current promotion gây lỗi.
- [ ] Có migration guide và kế hoạch deprecation/sunset.
- [ ] APIM, Monitor, networking và backend cost được theo dõi.
- [ ] IaC/repository metadata phản ánh cấu hình runtime, tránh drift.

## 23. Câu hỏi tự kiểm tra

1. **Azure API Management có tự chạy business code sau import OpenAPI không?** Không; APIM quản lý gateway/operations/policies, còn backend xử lý nghiệp vụ.
2. **OpenAPI info.version là API version identifier của APIM không?** Không mặc nhiên.
3. **API URL suffix khác operation path thế nào?** Suffix xác định API ở gateway; operation path là tuyến bên trong API.
4. **Vì sao import thành công vẫn có thể trả 502?** APIM có thể không kết nối được backend do DNS/TLS/network.
5. **API version dùng khi nào?** Khi cần nhiều hợp đồng API khác nhau chạy song song, thường do breaking change.
6. **API revision dùng khi nào?** Khi cần thử/thay đổi một API version mà chưa áp ngay cho current gateway URL.
7. **Revision 2 có đồng nghĩa version v2 không?** Không.
8. **Current revision là gì?** Revision phục vụ qua URL thông thường của API version.
9. **Non-current revision có thể được thử thế nào?** Thông qua revision-specific URL theo tính năng APIM, với auth và policy phù hợp.
10. **Cú pháp ;rev=2 có phải một mật khẩu không?** Không; chỉ là định tuyến revision.
11. **Có thể dùng path/header/query để chọn API version không?** Có, theo scheme của version set.
12. **Ưu nhược điểm version bằng header là gì?** Giữ URL nhưng phải xử lý header forwarding/cache key.
13. **Khi thay đổi response field bắt buộc, nên nghĩ đến gì?** Breaking change; cân nhắc version mới.
14. **Thêm optional query parameter có luôn không phá client không?** Không chắc; cần contract/regression tests.
15. **Import OpenAPI có tự tạo validate-jwt policy không?** Không nên giả định; phải cấu hình và test.
16. **Tại sao phải kiểm tra product/subscription sau import?** Để API chỉ hiện/cấp quyền cho đúng nhóm client.
17. **Vì sao không import thẳng current API từ branch chưa review?** Có nguy cơ ghi đè production operations/policies.
18. **Release notes gắn với sự kiện nào của revision?** Thường khi một revision được phát hành/make current theo lifecycle APIM.
19. **Rollback revision có rollback database không?** Không.
20. **Version v2 mới có tự làm v1 ngừng hoạt động không?** Không; cần quản trị cả hai versions và backend compatibility.
21. **Cần test gì sau import?** Operations, schemas, backend, auth, policies, gateway errors và client contract.
22. **Cách phân biệt 404 APIM với 404 backend?** Dựa vào gateway/backend traces, operation match và logs.
23. **Tại sao rate limit giảm có thể là breaking change?** Client cũ có thể vượt quota và nhận 429.
24. **Versioning scheme đổi sau khi client dùng có rủi ro gì?** URL/header/query contract thay đổi, proxy/cache có thể không khớp.
25. **Có thể dùng cùng backend cho v1 và v2 không?** Có khi backend hỗ trợ cả hai contracts/adapter đúng.
26. **Vì sao cần release artifact/checksum?** Để xác minh spec nào đã import và phục hồi/tái hiện.
27. **Có cần quản trị OpenAPI/policies trong Git/IaC không?** Nên có để review, audit và giảm drift.
28. **Non-current revision có tự bảo vệ khỏi người ngoài không?** Không; cần auth, subscription, network controls.
29. **Khi nào nên sunset v1?** Sau thông báo, giai đoạn migration, kiểm tra client adoption và nghĩa vụ hỗ trợ.
30. **Một APIM release thành công cần gì ngoài make current?** Contract tests, security, backend connectivity, metrics, rollback và client compatibility.

## 24. Tài liệu tham khảo

- [Azure API Management documentation](https://learn.microsoft.com/azure/api-management/) — service, gateway, products, policies và quản lý vòng đời API.
- [Import and publish an API](https://learn.microsoft.com/azure/api-management/import-and-publish) — thao tác import và kiểm tra API.
- [Import restrictions and known issues](https://learn.microsoft.com/azure/api-management/api-management-api-import-restrictions) — giới hạn định dạng/spec khi import.
- [Versions in Azure API Management](https://learn.microsoft.com/azure/api-management/api-management-versions) — version sets và path/header/query versioning.
- [Revisions in Azure API Management](https://learn.microsoft.com/azure/api-management/api-management-revisions) — revisions, current revision và release lifecycle.
- [API Management policies](https://learn.microsoft.com/azure/api-management/api-management-howto-policies) — policy scopes, inheritance và cấu hình gateway.
- [Authentication and authorization in APIM](https://learn.microsoft.com/azure/api-management/authentication-authorization-overview) — gateway/backend/client authentication.
- [API Management REST API reference](https://learn.microsoft.com/rest/api/apimanagement/) — automation quản lý APIs, versions, revisions và releases.
- [Azure CLI az apim api reference](https://learn.microsoft.com/cli/azure/apim/api) — import, list, show và những operations hỗ trợ.
- [Azure CLI az apim api versionset reference](https://learn.microsoft.com/cli/azure/apim/api/versionset) — quản lý API version sets.
- [Azure Monitor for API Management](https://learn.microsoft.com/azure/api-management/api-management-howto-use-azure-monitor) — metrics, logs và diagnostics.
- [OpenAPI Specification](https://spec.openapis.org/oas/latest.html) — chuẩn tài liệu hợp đồng HTTP APIs.
- [Azure Cost Management](https://learn.microsoft.com/azure/cost-management-billing/costs/) — giám sát giá và chi phí theo resource.

**Kết luận:** OpenAPI giúp mô tả hợp đồng; Azure API Management import hợp đồng thành các API/operations được quản trị qua gateway; **API version** giúp nhiều hợp đồng client cùng tồn tại, còn **API revision** giúp thay đổi và kiểm thử từng version trước khi đưa thành current. Muốn phát hành an toàn, phải **nhập đúng API ID/revision target**, kiểm tra backend và policies, xác nhận version routing, kiểm thử security/contract, đo tác động client và có rollback cho cả APIM lẫn backend/dữ liệu. Không xem thông báo import succeeded hoặc thao tác make current là bằng chứng một API release đã hoàn tất.
