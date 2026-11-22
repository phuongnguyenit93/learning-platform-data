# API Gateway, API deployments và backend integrations

## 1. Mục tiêu và bối cảnh

Trong chương **API, sự kiện và tích hợp** của module **CLOUD_PROVIDERS_ORACLE**, OCI API Gateway cung cấp điểm vào API để ứng dụng gọi các dịch vụ phía sau theo một hợp đồng rõ ràng. Việc triển khai cần gắn với tenancy, compartment, IAM, VCN, giám sát và kiểm soát tài nguyên tiêu thụ.

Ví dụ xuyên suốt bài học là một API orders có ba loại route:

| API phía client | Mục đích | Backend |
| --- | --- | --- |
| `GET /v1/health` | Kiểm tra đường tới gateway và deployment | Stock response |
| `GET /v1/orders/{orderId}` | Đọc thông tin đơn hàng | HTTP/HTTPS service |
| `POST /v1/order-summary` | Tạo bản tóm tắt đơn hàng | OCI Functions |

Sau bài học, người học có thể:

- Phân biệt gateway, API resource, deployment, specification, route và backend.
- Tạo deployment có path prefix và route nhất quán.
- Tích hợp HTTP backend và Functions backend với quyền, mạng và hợp đồng dữ liệu phù hợp.
- Phân biệt IAM quản trị, xác thực client và xác thực giữa gateway với backend.
- Kiểm tra cấu hình bằng một lab nhỏ, đọc log, theo dõi metrics và xác định hướng xử lý lỗi.

## 2. API Gateway làm gì trong kiến trúc?

**OCI API Gateway** là dịch vụ quản lý điểm vào API, định tuyến request tới backend và áp dụng các policy được hỗ trợ như xác thực, CORS, giới hạn request hoặc biến đổi dữ liệu. Backend có thể là HTTP API hoặc OCI Functions. Xem [Overview of API Gateway](https://docs.oracle.com/en-us/iaas/Content/APIGateway/Concepts/apigatewayoverview.htm).

~~~mermaid
flowchart LR
    CLIENT["API client"] -->|HTTPS request| GW["OCI API Gateway"]
    GW --> DEP["Deployment /v1"]
    DEP --> ROUTE["Chọn route theo path và method"]
    ROUTE --> STOCK["Stock response"]
    ROUTE --> HTTP["HTTP/HTTPS backend"]
    ROUTE --> FN["OCI Functions"]
    HTTP --> DATA["Dữ liệu nghiệp vụ"]
    FN --> DATA
    GW --> OBS["Access logs, execution logs, metrics"]
~~~

Sơ đồ biểu diễn luồng logic. Chính sách của deployment và route tác động tới cách request được xử lý; thứ tự chi tiết phụ thuộc loại policy và cấu hình.

Gateway giúp tách địa chỉ API mà client sử dụng khỏi vị trí backend. Ví dụ, client vẫn gọi `/v1/orders/ORD-1001` khi nhóm vận hành chuyển dịch vụ orders sang backend mới tương thích.

Tuy nhiên, việc đổi backend không tự bảo đảm tính tương thích. Nhóm sở hữu API vẫn cần giữ đúng status code, schema dữ liệu, cách xác thực và ý nghĩa nghiệp vụ mà client đang phụ thuộc.

## 3. Các tài nguyên và khái niệm

### 3.1. Gateway, deployment và API resource

| Khái niệm | Vai trò |
| --- | --- |
| API gateway | Điểm vào mạng nhận API request |
| API deployment | Bản cấu hình API được triển khai trên một gateway |
| Deployment specification | Mô tả routes, backend và các policy |
| Route | Ghép path, HTTP method và backend |
| Backend | Nơi xử lý hoặc tạo phản hồi |
| API resource | Biểu diễn API ở giai đoạn thiết kế |
| API description | Mô tả hợp đồng API, chẳng hạn bằng OpenAPI |

API resource là tùy chọn. Có thể tạo deployment trực tiếp mà không tạo API resource trước. Nếu dùng API resource và API description, một số thông tin có thể được dùng để khởi tạo cấu hình deployment. Xem [API Gateway Concepts](https://docs.oracle.com/en-us/iaas/Content/APIGateway/Concepts/apigatewayconcepts.htm).

Một file OpenAPI mô tả hợp đồng API không thay thế mọi quyết định triển khai: vẫn cần xác định gateway, backend thực tế, mạng và policy phù hợp.

### 3.2. Một gateway có thể phục vụ nhiều deployment

Có thể tạo nhiều route trong một deployment, hoặc nhiều deployment trên cùng gateway. Deployment có path prefix riêng, ví dụ `/v1` và `/v2`. Xem [Deploying an API by Creating an API Deployment](https://docs.oracle.com/en-us/iaas/Content/APIGateway/Tasks/apigatewaycreatingdeployment.htm).

Ví dụ thiết kế:

~~~text
Gateway orders-gateway
├── Deployment orders-v1: prefix /v1
│   ├── GET  /health
│   ├── GET  /orders/{orderId}
│   └── POST /order-summary
└── Deployment orders-v2: prefix /v2
    └── GET /orders/{orderId}
~~~

Đây là cách tổ chức minh họa, không phải yêu cầu phải có hai phiên bản. Nên chọn ranh giới deployment theo nhu cầu phát hành, cấu hình và quản trị.

## 4. URL phía client, path prefix và route

### 4.1. Ghép đúng URL

Một lời gọi có dạng:

~~~text
https://<gateway-hostname><deployment-path-prefix><route-path>
~~~

Với prefix `/v1` và route `/health`:

~~~text
https://<gateway-hostname>/v1/health
~~~

`<gateway-hostname>` phải lấy từ gateway thực tế trên Console hoặc API. Nó không phải tên hiển thị như `orders-gateway` và cũng không phải gateway OCID.

Route được khai báo tương đối với path prefix. Không viết route `/v1/health` nếu deployment đã có prefix `/v1`, trừ khi chủ đích muốn URL chứa prefix lặp. Cách gọi được mô tả trong [Calling an API Deployed on an API Gateway](https://docs.oracle.com/en-us/iaas/Content/APIGateway/Tasks/apigatewayinvokingdeployedapi.htm).

| Cấu hình | Kết quả phía client |
| --- | --- |
| Prefix `/v1`, route `/health` | `/v1/health` |
| Prefix `/v1`, route `/orders/{orderId}` | Ví dụ `/v1/orders/ORD-1001` |
| Prefix `/v1`, route `/v1/health` | `/v1/v1/health` |

Prefix không nhận path parameter hoặc wildcard. Nếu chọn prefix `/`, gateway chỉ được có deployment đó; cần xét điều này trước khi chọn root cho một API muốn mở rộng. Xem [Creating an API Deployment](https://docs.oracle.com/en-us/iaas/Content/APIGateway/Tasks/apigatewaycreatingdeployment.htm).

### 4.2. Phân biệt URL client và URL backend

Giả sử client gọi:

~~~text
GET https://<gateway-hostname>/v1/orders/ORD-1001
~~~

Backend có thể nhận:

~~~text
GET https://orders.internal.example/internal/orders/ORD-1001
~~~

Hai URL có thể khác host và khác cấu trúc path. Specification phải mô tả việc ánh xạ cần thiết. Không giả định mọi phần đường dẫn client đều tự xuất hiện trong URL backend.

Tên miền `orders.internal.example` chỉ là ví dụ; phải thay bằng backend thật và cấu hình phân giải DNS phù hợp.

## 5. Mạng: điểm vào gateway và đường tới backend

### 5.1. Public hoặc private là quyết định về điểm vào

| Gateway | Đường truy cập dự kiến |
| --- | --- |
| Public | Client trên Internet khi route và quy tắc mạng cho phép |
| Private | Client trong VCN hoặc mạng riêng kết nối tới VCN |

Public gateway cần public regional subnet và cấu hình truy cập phù hợp. Gateway nhận HTTPS trên cổng `443`; cần quy tắc ingress tương ứng. Private gateway cần client có đường tới địa chỉ private của nó. Xem [Creating an API Gateway](https://docs.oracle.com/en-us/iaas/Content/APIGateway/Tasks/apigatewaycreatinggateway.htm).

Việc tra được DNS chưa chứng minh kết nối được. Một hostname có thể phân giải thành private IP nhưng máy đang thử không có route tới địa chỉ đó.

### 5.2. Gateway public vẫn có thể gọi backend private

Điểm vào public và backend private giải quyết hai nhu cầu khác nhau. Ví dụ, client bên ngoài gọi gateway public, còn dịch vụ orders nằm sau private load balancer và chỉ nhận traffic phù hợp từ phía gateway.

Cần kiểm tra hai chặng:

~~~text
Client → Gateway:
    DNS, route, HTTPS 443, certificate và policy client.

Gateway → Backend:
    DNS của backend, route, egress, ingress phía backend,
    cổng dịch vụ, TLS và xác thực backend.
~~~

Một phép thử curl trên laptop không chứng minh subnet của gateway phân giải được cùng hostname hoặc có cùng đường mạng. Khi thiết kế HTTP integration, hãy kiểm tra vị trí và quyền truy cập từ phía gateway. Tài liệu [Adding an HTTP or HTTPS URL as a Back End](https://docs.oracle.com/en-us/iaas/Content/APIGateway/Tasks/apigatewayusinghttpbackend.htm) mô tả cả yêu cầu phân giải hostname backend.

Lab trong bài chọn gateway **private** và client thử trong mạng có kết nối tới VCN. Cách này giúp quan sát cấu hình API trước khi quyết định điểm vào công khai.

## 6. Ba loại backend phổ biến

Các ví dụ sau tập trung vào ba backend thông dụng: `STOCK_RESPONSE_BACKEND`, `HTTP_BACKEND` và `ORACLE_FUNCTIONS_BACKEND`. Dịch vụ còn có các backend chuyên biệt cho luồng xác thực; danh sách và hướng dẫn nằm trong [Adding API Gateway Back Ends](https://docs.oracle.com/en-us/iaas/Content/APIGateway/Tasks/apigatewayaddingbackendstoapigateways.htm).

### 6.1. Stock response: gateway tạo phản hồi

Stock response trả status, headers và body đã khai báo, không gọi một dịch vụ nghiệp vụ bên ngoài. Nó phù hợp cho một route kiểm tra cấu hình hoặc phản hồi cố định. Xem [Adding Stock Responses as a Back End](https://docs.oracle.com/en-us/iaas/Content/APIGateway/Tasks/apigatewayaddingstockresponses.htm).

Specification tối thiểu:

~~~json
{
  "routes": [
    {
      "path": "/health",
      "methods": ["GET"],
      "backend": {
        "type": "STOCK_RESPONSE_BACKEND",
        "status": 200,
        "headers": [
          {
            "name": "Content-Type",
            "value": "application/json"
          }
        ],
        "body": "{\"gateway\":\"ok\",\"release\":\"lab-001\"}"
      }
    }
  ]
}
~~~

`body` là một chuỗi trong specification. Vì chuỗi đó chứa JSON, dấu nháy bên trong được escape.

Kết quả `200` từ route này chỉ xác nhận đường vào, deployment và cấu hình stock response đã hoạt động. Nó chưa chứng minh dịch vụ orders hoặc cơ sở dữ liệu còn sẵn sàng.

### 6.2. HTTP backend: gọi một HTTP/HTTPS service

Backend HTTP phù hợp khi nghiệp vụ đã có API, chẳng hạn service trên Compute, OKE, sau load balancer hoặc một endpoint REST của hệ thống tích hợp.

Ví dụ một **route** để thêm vào mảng `routes`:

~~~json
{
  "path": "/orders/{orderId}",
  "methods": ["GET"],
  "backend": {
    "type": "HTTP_BACKEND",
    "url": "https://orders.internal.example/internal/orders/${request.path[orderId]}",
    "connectTimeoutInSeconds": 3,
    "readTimeoutInSeconds": 10,
    "sendTimeoutInSeconds": 10,
    "isSSLVerifyDisabled": false
  }
}
~~~

`url` là địa chỉ backend; ba timeout kiểm soát các giai đoạn kết nối, đọc phản hồi và gửi request. `isSSLVerifyDisabled: false` giữ kiểm tra certificate của backend. Với CA riêng, cần cấu hình trust phù hợp thay vì tắt kiểm tra để che lỗi. Xem [Adding an HTTP or HTTPS URL as a Back End](https://docs.oracle.com/en-us/iaas/Content/APIGateway/Tasks/apigatewayusinghttpbackend.htm).

Đối với ví dụ trên:

~~~text
Client:   /v1/orders/ORD-1001
Route:    /orders/{orderId}
Context:  request.path[orderId] = ORD-1001
Backend:  /internal/orders/ORD-1001
~~~

Cú pháp `${request.path[orderId]}` là biến ngữ cảnh được gateway xử lý, không phải một giá trị cần shell thay thế.

Nếu ghi specification bằng Bash heredoc, dùng delimiter được quote để giữ nguyên biến này:

~~~bash
cat > deployment.json <<'JSON'
{
  "routes": [
    {
      "path": "/orders/{orderId}",
      "methods": ["GET"],
      "backend": {
        "type": "HTTP_BACKEND",
        "url": "https://orders.internal.example/internal/orders/${request.path[orderId]}"
      }
    }
  ]
}
JSON
~~~

Đây là ví dụ thay file cấu hình trong thư mục lab của người học. Khi đang giữ nhiều route trong cùng specification, hãy sửa mảng `routes` thay vì ghi đè file bằng đoạn ví dụ một route.

Context variables còn có thể được dùng trong policy được hỗ trợ. Với giá trị động ở query string, Oracle hướng dẫn dùng query parameter transformation policy, không ghép biểu thức query động trực tiếp vào `url`. Xem [Adding Context Variables](https://docs.oracle.com/en-us/iaas/Content/APIGateway/Tasks/apigatewaycontextvariables.htm).

### 6.3. Functions backend: gọi function đã triển khai

Ví dụ một route gửi request tới OCI Functions:

~~~json
{
  "path": "/order-summary",
  "methods": ["POST"],
  "backend": {
    "type": "ORACLE_FUNCTIONS_BACKEND",
    "functionId": "REPLACE_WITH_REAL_FUNCTION_OCID"
  }
}
~~~

Cần thay placeholder bằng function OCID thật. Function phải được triển khai, gateway có đường tới Functions và có quyền gọi thích hợp. Quyền của người tạo deployment cũng cần được chuẩn bị. Xem [Adding a Function as an API Gateway Back End](https://docs.oracle.com/en-us/iaas/Content/APIGateway/Tasks/apigatewayusingfunctionsbackend.htm).

Ví dụ hợp đồng request do nhóm ứng dụng lựa chọn:

~~~http
POST /v1/order-summary HTTP/1.1
Content-Type: application/json

{"orderId":"ORD-1001"}
~~~

Function phải đọc và kiểm tra dữ liệu theo hợp đồng này, đồng thời trả status, headers và body phù hợp với cơ chế tích hợp và FDK sử dụng. Không mặc định rằng mọi function có sẵn đều hiểu đúng cùng một cấu trúc request.

Ví dụ, function cần biết phải trả gì khi `orderId` thiếu, khi đơn hàng không tồn tại và khi dịch vụ dữ liệu gặp lỗi. Những hành vi đó thuộc hợp đồng API và logic backend.

### 6.4. Tích hợp với dịch vụ khác qua đúng lớp

| Hệ thống phía sau | Cách tiếp cận |
| --- | --- |
| HTTP microservice | HTTP backend |
| Logic ngắn đã triển khai trên OCI Functions | Functions backend |
| Oracle Integration có endpoint phù hợp | Tích hợp HTTP với xác thực tương ứng |
| Dữ liệu Oracle Database | Service hoặc lớp REST phù hợp truy cập DB |
| API OCI yêu cầu request được ký | Thành phần gọi API có cơ chế ký hợp lệ |

Gateway làm việc với API; kết nối TCP trực tiếp tới listener của database không trở thành một REST API chỉ vì được đặt phía sau gateway.

Đặc biệt, chuyển tiếp nguyên header `Authorization` của một OCI-signed request chưa bảo đảm chữ ký còn đúng khi host hoặc path thay đổi. Oracle khuyến nghị ký request cuối cùng gửi tới dịch vụ đích, có thể qua một Functions backend dùng cơ chế xác thực OCI phù hợp. Xem [OCI service API calls fail after being proxied through API Gateway](https://docs.oracle.com/en-us/iaas/Content/APIGateway/Tasks/apigatewaytroubleshooting_topic-service_api_calls_fail_after_proxied.htm).

## 7. IAM quản trị và quyền gateway gọi Functions

### 7.1. Tách các chủ thể

| Chủ thể | Phạm vi cần xét |
| --- | --- |
| Developer hoặc CI | Tạo/cập nhật gateway, deployment và cấu hình liên quan |
| API client | Được gọi route theo policy xác thực/ủy quyền API |
| Gateway | Được truy cập backend cần IAM hoặc credential |
| Function hoặc service backend | Được truy cập dữ liệu nghiệp vụ |

Quyền developer deploy không tự làm cho client được gọi API nghiệp vụ, cũng không tự cấp cho function quyền đọc bucket hoặc database.

Ví dụ cấp quyền quản lý tài nguyên gateway trong compartment `ApiDev`:

~~~text
Allow group 'Default'/'ApiDevelopers' to manage api-gateway-family in compartment ApiDev
~~~

Nhóm triển khai còn cần quyền mạng và các tài nguyên liên quan theo thiết kế. Không coi dòng policy này là toàn bộ cấu hình cần thiết cho mọi backend.

### 7.2. Ví dụ gateway gọi Functions

Mẫu policy theo compartment:

~~~text
Allow any-user to use functions-family in compartment AppFunctions where all { request.principal.type = 'ApiGateway', request.resource.compartment.id = '<GATEWAY_COMPARTMENT_OCID>' }
~~~

Thay compartment và OCID bằng giá trị thật. Điều kiện giới hạn chủ thể là API Gateway trong compartment được chỉ định. `any-user` ở đây không có nghĩa cho mọi API client ẩn danh quyền gọi function trực tiếp.

Mẫu này cấp phạm vi cho các gateway thuộc compartment đó; cần chọn cách tổ chức và điều kiện phù hợp với ranh giới quản trị. Các mẫu IAM được Oracle mô tả trong [Create Policies to Control Access](https://docs.oracle.com/en-us/iaas/Content/APIGateway/Tasks/apigatewaycreatingpolicies.htm).

Nếu function tiếp tục đọc Object Storage hoặc secret, cần thiết kế thêm quyền runtime của function. Đó là một chặng truy cập riêng trong chuỗi.

## 8. Xác thực và ủy quyền cho người gọi API

### 8.1. Kiểm tra danh tính và quyền thao tác

**Authentication** xác định ai đang gọi. **Authorization** xác định danh tính đó được phép làm gì.

OCI API Gateway hỗ trợ các phương án như xác thực token hoặc gọi authorizer function. Xem [Adding Authentication and Authorization](https://docs.oracle.com/en-us/iaas/Content/APIGateway/Tasks/apigatewayaddingauthzauthn.htm).

Với token, cấu hình phải khớp nhà phát hành và đối tượng sử dụng của API. Thiết kế cần xác định token được lấy từ đâu, kiểm tra bằng cơ chế nào và route yêu cầu scope hoặc quyền gì. Tham khảo [Validating Tokens](https://docs.oracle.com/en-us/iaas/Content/APIGateway/Tasks/apigatewayusingjwttokens.htm).

Ví dụ hợp đồng bảo vệ API orders:

| Route | Quyền đề xuất |
| --- | --- |
| `GET /orders/{orderId}` | Có quyền đọc orders và được truy cập đơn hàng đó |
| `POST /order-summary` | Có quyền tạo summary |
| Route quản trị | Chỉ dành cho vai trò quản trị tương ứng |

Quyền ở mức đối tượng, chẳng hạn “người dùng chỉ xem đơn hàng của mình”, cần được kiểm tra tại lớp có đủ dữ liệu nghiệp vụ. Một token hợp lệ không tự chứng minh quyền sở hữu mọi order ID.

### 8.2. Authorizer và backend nghiệp vụ có vai trò khác nhau

Authorizer function quyết định yêu cầu có được phép tiếp tục hay không; function backend xử lý nghiệp vụ của route. Dùng cùng một nền tảng Functions không làm hai vai trò này trở thành một bước.

Authorizer cũng có thể ảnh hưởng độ trễ, tải và khả năng sẵn sàng. Cần xác định đầu vào, kết quả và cách xử lý lỗi theo giao thức authorizer được hỗ trợ. Xem [Passing Tokens to Authorizer Functions](https://docs.oracle.com/en-us/iaas/Content/APIGateway/Tasks/apigatewayusingauthorizerfunction.htm).

## 9. Policy: áp dụng đúng phạm vi

### 9.1. Policy của API không phải IAM policy

IAM policy kiểm soát quyền trên tài nguyên OCI. Request/response policy trong deployment kiểm soát cách API xử lý request và response.

Ví dụ:

| Cấu hình | Tác động |
| --- | --- |
| IAM `manage api-gateway-family` | Cho phép thao tác quản lý tài nguyên |
| Authentication policy | Kiểm tra danh tính client khi gọi API |
| Rate limiting policy | Giới hạn tốc độ request theo cấu hình |
| CORS policy | Điều khiển chia sẻ tài nguyên giữa các origin trong trình duyệt |
| Transformation policy | Điều chỉnh dữ liệu request/response được hỗ trợ |

Không phải loại policy nào cũng hỗ trợ cùng một phạm vi. Cần kiểm tra chính sách ở cấp deployment hay route thay vì suy rằng mọi cấu hình đều có thể đặt tùy ý ở cả hai cấp.

### 9.2. Rate limit ở cấp deployment

OCI API Gateway hỗ trợ rate limit cho toàn bộ routes của một deployment, theo tổng request hoặc theo client IP. Policy này không được đặt riêng cho từng route trong deployment. Xem [Limiting the Number of Requests to Back Ends](https://docs.oracle.com/en-us/iaas/Content/APIGateway/Tasks/apigatewaylimitingbackendaccess.htm).

Ví dụ phần cấu hình ở top-level của specification:

~~~json
{
  "requestPolicies": {
    "rateLimiting": {
      "rateKey": "TOTAL",
      "rateInRequestsPerSecond": 20
    }
  },
  "routes": [
    {
      "path": "/health",
      "methods": ["GET"],
      "backend": {
        "type": "STOCK_RESPONSE_BACKEND",
        "status": 200,
        "body": "ok"
      }
    }
  ]
}
~~~

`20` là giá trị minh họa cho lab. Trong hệ thống thật, chọn mức giới hạn theo khả năng xử lý backend và nhu cầu sử dụng.

Theo IP không đồng nghĩa theo tài khoản: nhiều người dùng có thể chung địa chỉ NAT. Nếu cần quản lý mức sử dụng theo khách hàng hoặc gói dịch vụ, cần đánh giá cơ chế usage plan và nhận diện client phù hợp.

Rate limit giúp kiểm soát số request đi vào. Nó không thay thế timeout, giới hạn connection hoặc thiết kế chịu lỗi ở backend.

### 9.3. CORS dành cho client trong trình duyệt

CORS cho phép trình duyệt quyết định có chia sẻ response cho mã chạy từ origin khác hay không. Có thể cấu hình policy ở deployment hoặc route. Xem [Adding CORS support to API Deployments](https://docs.oracle.com/en-us/iaas/Content/APIGateway/Tasks/apigatewayaddingcorssupport.htm).

Ví dụ cấu hình dành cho một frontend xác định:

~~~json
{
  "cors": {
    "allowedOrigins": ["https://app.example.com"],
    "allowedMethods": ["GET", "POST"],
    "allowedHeaders": ["Authorization", "Content-Type"],
    "exposedHeaders": ["opc-request-id"],
    "isAllowCredentialsEnabled": false,
    "maxAgeInSeconds": 300
  }
}
~~~

Đây là nội dung để ghép vào `requestPolicies` ở phạm vi được chọn. Thay origin ví dụ bằng origin thật.

Nếu browser lỗi nhưng curl thành công, cần xem request preflight, method, headers và CORS response. Curl không thực thi chính sách same-origin như trình duyệt. Đồng thời, CORS không cấp quyền nghiệp vụ cho client; API vẫn cần cơ chế xác thực/ủy quyền riêng.

## 10. Lab: tạo một deployment có thể kiểm tra độc lập

### 10.1. Chuẩn bị

Các lệnh dưới đây là hướng dẫn Bash để người học chạy trong môi trường của mình. Lab chưa yêu cầu triển khai service orders hoặc function; bắt đầu bằng stock response để kiểm tra đường vào.

Cần có:

- Region và compartment dành cho API lab.
- OCI CLI được cấu hình đúng profile, tenancy và region.
- VCN và private regional subnet đã chuẩn bị.
- Client kiểm thử có đường mạng tới VCN.
- Quyền tạo gateway/deployment và sử dụng tài nguyên mạng liên quan.
- Ingress HTTPS `443` tới gateway từ nguồn kiểm thử phù hợp.

Trong Console, mở **API Gateway**, tạo gateway tên `orders-gateway-lab`, loại **Private**, chọn VCN và subnet lab. Chờ tài nguyên sẵn sàng, ghi gateway OCID và hostname từ Console.

Không cần đặt backend thật lên Internet để hoàn thành phép thử này.

### 10.2. Lưu specification của lab

Tạo file `deployment.json` trong thư mục lab với nội dung đầy đủ ở mục 6.1, gồm route stock response `/health`.

Specification này không khai báo xác thực client và chỉ trả dữ liệu cố định của lab. Khi bổ sung route nghiệp vụ, phải cấu hình bảo vệ theo hợp đồng đã xác định.

Khai báo các giá trị thực tế:

~~~bash
export OCI_REGION='us-ashburn-1'
export API_COMPARTMENT_OCID='REPLACE_WITH_API_COMPARTMENT_OCID'
export GATEWAY_OCID='REPLACE_WITH_GATEWAY_OCID'
export GATEWAY_HOSTNAME='REPLACE_WITH_GATEWAY_HOSTNAME'
~~~

`GATEWAY_HOSTNAME` chỉ chứa hostname, không chứa `https://` hoặc `/v1`. Nếu chọn region khác, thay `OCI_REGION` cho đúng tài nguyên đã tạo.

### 10.3. Tạo deployment

Chạy từ thư mục chứa `deployment.json`:

~~~bash
oci api-gateway deployment create \
  --region "$OCI_REGION" \
  --compartment-id "$API_COMPARTMENT_OCID" \
  --gateway-id "$GATEWAY_OCID" \
  --display-name orders-v1-lab \
  --path-prefix /v1 \
  --specification file://deployment.json
~~~

`--specification` nhận nội dung specification, không phải toàn bộ một tài liệu có thêm gateway OCID và compartment ở lớp ngoài. Những giá trị đó đã được truyền bằng tham số CLI. Cấu trúc specification được mô tả trong [Creating an API Deployment Specification](https://docs.oracle.com/en-us/iaas/Content/APIGateway/Tasks/apigatewaycreatingspecification.htm).

Ghi deployment OCID từ kết quả. Theo dõi work request và trạng thái deployment trên Console; chỉ kiểm thử khi thao tác tạo thành công và deployment đã `ACTIVE`.

Có thể xem lại tài nguyên bằng CLI:

~~~bash
export DEPLOYMENT_OCID='REPLACE_WITH_DEPLOYMENT_OCID'

oci api-gateway deployment get \
  --region "$OCI_REGION" \
  --deployment-id "$DEPLOYMENT_OCID"
~~~

Lệnh tạo tài nguyên trả thành công chưa chứng minh một HTTP backend sẽ truy cập được. Với stock response, chưa có chặng gọi ra backend nghiệp vụ để kiểm tra.

### 10.4. Gọi API từ client có kết nối tới private gateway

~~~bash
curl --include \
  "https://$GATEWAY_HOSTNAME/v1/health"
~~~

Kết quả mong đợi:

~~~http
HTTP/1.1 200
Content-Type: application/json

{"gateway":"ok","release":"lab-001"}
~~~

Phiên bản HTTP hoặc một số header có thể khác tùy kết nối; cần xác minh status `200` và body đã cấu hình.

Các phép thử bổ sung:

| Phép thử | Điều cần quan sát |
| --- | --- |
| Gọi `/v1/health` bằng GET | Nhận stock response |
| Gọi `/health` thiếu prefix | Không khớp đường API đã cấu hình |
| Gọi một path chưa khai báo | Không tự đi vào backend khác |
| Gọi method chưa khai báo | Không thực hiện hành vi của method được cho phép |
| Kiểm tra log | Tìm được request vào deployment |

Không dùng `curl -k` làm mặc định. Nếu TLS lỗi, cần kiểm tra hostname và certificate thay vì bỏ qua xác minh rồi kết luận cấu hình hoàn chỉnh.

## 11. Mở rộng lab sang backend thật

### 11.1. Thêm HTTP backend

Chuẩn bị service orders và endpoint kiểm thử có hợp đồng rõ ràng. Trước khi cập nhật deployment, xác nhận:

1. Hostname backend phân giải được theo DNS mà gateway sử dụng.
2. Có route và quy tắc mạng cho phép gateway kết nối tới cổng backend.
3. Backend có certificate và chuỗi tin cậy phù hợp nếu dùng HTTPS.
4. Backend chấp nhận method, path, headers và cách xác thực dự định.
5. Có dữ liệu đơn hàng thử để phân biệt lỗi routing với lỗi nghiệp vụ.

Thêm object route ở mục 6.2 vào mảng `routes` của `deployment.json`, giữ route `/health`. Thay hostname ví dụ bằng đích thật.

Cập nhật:

~~~bash
oci api-gateway deployment update \
  --region "$OCI_REGION" \
  --deployment-id "$DEPLOYMENT_OCID" \
  --specification file://deployment.json
~~~

Cập nhật specification cần giữ các route và policy muốn tiếp tục sử dụng; không xem đoạn một route là một bản vá tự động gộp vào cấu hình hiện tại. Khi dùng CI, có thể bổ sung `--if-match` với ETag từ lần đọc tài nguyên để kiểm soát cập nhật đồng thời. Xem [deployment update](https://docs.oracle.com/en-us/iaas/tools/oci-cli/latest/oci_cli_docs/cmdref/api-gateway/deployment/update.html).

Sau khi cập nhật thành công:

~~~bash
curl --include \
  "https://$GATEWAY_HOSTNAME/v1/orders/ORD-1001"
~~~

Đối chiếu response với dữ liệu thử và log backend. Stock response vẫn thành công trong khi route orders lỗi là dấu hiệu cần tập trung vào chặng tích hợp mới.

### 11.2. Thêm Functions backend

Chuẩn bị function đã triển khai và xử lý được request JSON của lab. Xác nhận quyền gateway gọi function, quyền của người triển khai và đường kết nối tới Functions.

Thêm route ở mục 6.3 vào specification, thay `functionId` bằng OCID thật rồi cập nhật deployment.

Gọi:

~~~bash
curl --include \
  --request POST \
  --header 'Content-Type: application/json' \
  --data '{"orderId":"ORD-1001"}' \
  "https://$GATEWAY_HOSTNAME/v1/order-summary"
~~~

Nếu deployment đã được bảo vệ bằng bearer token, bổ sung token hợp lệ theo cấu hình API. Credential của backend hoặc function runtime không nên được client gửi thay cho token API.

Kết quả cần đối chiếu ở cả hai nơi: gateway đã định tuyến được và function đã thực thi đúng nghiệp vụ. Nếu function tiếp tục truy cập cơ sở dữ liệu, cần kiểm tra cả chặng dữ liệu đó.

### 11.3. Phân biệt đúng mức độ xác minh

| Phép thử thành công | Đã có bằng chứng | Vẫn cần xác minh |
| --- | --- | --- |
| Stock response | Điểm vào và route cơ bản | Backend nghiệp vụ |
| HTTP GET đơn hàng thử | Một đường tới HTTP backend | Quyền theo người dùng và tải đồng thời |
| Functions response | Gateway gọi được function | Phụ thuộc dữ liệu và tình huống lỗi |
| Token hợp lệ | Một cấu hình xác thực hoạt động | Token sai, thiếu scope, hết hạn |
| Thử tải nhỏ | Hành vi ở mức tải đã đo | Burst, giới hạn tài nguyên và phục hồi |

Các bước này là quy trình thực hành của người học; việc có specification trong tài liệu không đồng nghĩa tài nguyên cloud đã được tạo hoặc các phép thử đã được chạy.

## 12. Độ trễ, timeout và gọi lặp

### 12.1. Timeout cần khớp toàn bộ chuỗi

Một request có thể đi qua client, gateway, function hoặc service, rồi tới database. Mỗi tầng có thể có timeout riêng.

Ví dụ thiết kế:

~~~text
Client chờ tối đa theo hợp đồng
    → gateway có giới hạn kết nối và I/O backend
    → backend đặt deadline xử lý
    → truy vấn DB có thời hạn ngắn hơn phần ngân sách còn lại
~~~

Các tham số connect/read/send timeout của HTTP backend kiểm soát từng giai đoạn; không nên coi chúng là một đồng hồ tổng có thể cộng đơn giản trong mọi tình huống.

Nếu caller ngừng chờ, tác động ở backend có thể đã xảy ra. Ví dụ, đơn hàng được ghi thành công nhưng response bị mất; retry thiếu kiểm soát có thể ghi lần nữa.

Do đó, API tạo tài nguyên hoặc kích hoạt nghiệp vụ cần xác định khóa idempotency, cách phát hiện yêu cầu lặp và kết quả trả cho lần gọi lại.

### 12.2. Chọn đúng hợp đồng đồng bộ hoặc bất đồng bộ

Một API xử lý ngắn có thể trả kết quả trực tiếp. Nếu công việc dài hơn ngân sách HTTP đã thống nhất, có thể thiết kế nhận yêu cầu, tạo job và cung cấp endpoint đọc trạng thái.

Ví dụ hợp đồng do ứng dụng thiết kế:

~~~http
HTTP/1.1 202 Accepted
Content-Type: application/json

{"jobId":"JOB-1001","status":"accepted"}
~~~

Gateway định tuyến API này; backend phải thật sự lưu hoặc chuyển giao công việc trước khi công bố đã nhận. Việc chọn trả `202` không tự tạo queue, worker hay bảo đảm hoàn tất công việc.

### 12.3. Nhiều backend cho cùng một route

API Gateway hỗ trợ chọn backend động theo phần tử request được cấu hình, chẳng hạn context của path, header hoặc danh tính đã xác thực. Xem [Dynamically Selecting API Gateway Back Ends](https://docs.oracle.com/en-us/iaas/Content/APIGateway/Tasks/apigatewaydynamicroutingbasedonrequest_topic.htm).

Có thể dùng để hướng các nhóm request tới backend tương thích khác nhau. Tuy nhiên:

- Quy tắc định tuyến không thay thế kiểm tra quyền.
- Header do client tự đặt chưa chứng minh client thuộc một nhóm được tin cậy.
- Cần quy tắc mặc định và hợp đồng nhất quán giữa các backend.
- Chọn backend theo request không tự tạo cơ chế failover khi một đích gặp lỗi.

Với bài thực hành cơ bản, một backend xác định cho mỗi route thường dễ quan sát hơn.

## 13. Logs và metrics phục vụ vận hành

### 13.1. Access logs và execution logs

API deployments có hai loại log chính:

| Log | Nội dung sử dụng |
| --- | --- |
| Access log | Tóm tắt request và response đi qua deployment |
| Execution log | Các bước xử lý trong gateway và thông tin lỗi |

Cần cấu hình mức execution log phù hợp và bật category log trong OCI Logging cho deployment, với log group và thời hạn lưu. Chọn log level trong specification chưa thay thế việc chuẩn bị nơi thu thập log. Xem [Adding Logging to API Deployments](https://docs.oracle.com/en-us/iaas/Content/APIGateway/Tasks/apigatewayaddinglogpolicies.htm).

Khi điều tra một request, nên lưu thời điểm, method, path, deployment, mã tương quan và bản phát hành backend. Nếu ứng dụng hỗ trợ correlation ID, thống nhất cách truyền và ghi nhận giữa gateway, service và function.

Log đủ để điều tra nhưng tránh ghi token, mật khẩu và toàn bộ dữ liệu nhạy cảm của đơn hàng.

### 13.2. Metrics của gateway và backend

Namespace metrics là `oci_apigateway`. Các metric đáng chú ý gồm `HttpRequests`, `HttpResponses`, `BackendHttpResponses`, `Latency`, `IntegrationLatency` và `InternalLatency`. Xem [API Gateway Metrics](https://docs.oracle.com/en-us/iaas/Content/APIGateway/Reference/apigatewaymetrics.htm).

| Quan sát | Hướng phân tích |
| --- | --- |
| Gateway trả nhiều 4xx | Kiểm tra route, method, token và policy |
| Backend trả nhiều 5xx | Đối chiếu log và tình trạng backend |
| `IntegrationLatency` tăng | Kiểm tra các tích hợp ngoài gateway, bao gồm DNS hoặc xác thực |
| Tổng latency tăng | Tách xử lý nội bộ và các lần gọi tích hợp |
| Request tăng mạnh | Phân biệt người dùng thật, retry và traffic bất thường |

Không coi IntegrationLatency là thời gian của riêng code nghiệp vụ. Metric này còn phản ánh các tích hợp ngoài gateway mà request đi qua.

### 13.3. Kiểm tra endpoint từ đúng vị trí

Stock response giúp kiểm tra khả năng tới một path cụ thể; muốn đo cả phụ thuộc cần thêm một phép kiểm tra phù hợp với nghiệp vụ.

Với gateway private, probe phải có đường tới mạng riêng. Với điểm vào public, có thể dùng cơ chế kiểm tra ngoài hệ thống phù hợp. Không suy rằng “không có lỗi trong metrics” đồng nghĩa endpoint đang truy cập được. Oracle phân biệt khả năng truy cập và metrics trong [Monitoring endpoint reachability](https://docs.oracle.com/en-us/iaas/Content/APIGateway/Tasks/apigatewaytroubleshooting_topic-monitor_endpoint_reachability.htm).

## 14. Chẩn đoán sự cố theo từng chặng

| Triệu chứng | Cần kiểm tra trước | Bằng chứng hữu ích |
| --- | --- | --- |
| Không kết nối được gateway | DNS, route, ingress 443 và vị trí client | Hostname, IP phân giải, lỗi kết nối |
| TLS handshake lỗi | Hostname, certificate và chuỗi tin cậy | Chi tiết lỗi TLS, certificate được trình bày |
| Không khớp API dự kiến | Prefix, route, method và deployment đang dùng | URL đầy đủ và specification hiệu lực |
| Lỗi xác thực/ủy quyền | Token, policy và quyền nghiệp vụ | Execution log và cấu hình xác thực |
| Stock response được nhưng HTTP route lỗi | Đường tới HTTP backend | DNS, route, TLS và access log backend |
| Functions integration lỗi | Function OCID, quyền gateway và kết nối | Gateway log, function log và mã yêu cầu |
| Response chậm hoặc timeout | Các thời hạn và hệ thống phụ thuộc | Latency, integration latency và backend log |
| Browser lỗi nhưng curl được | CORS và preflight | Request OPTIONS và response headers |
| OCI service từ chối chữ ký | Chữ ký của request cuối cùng tới dịch vụ | Host, path và cơ chế ký ở lớp gọi dịch vụ |

Status code là một dấu hiệu, không đủ xác định nguồn lỗi. Cùng một lỗi `5xx` có thể xuất phát từ backend, kết nối hoặc bước xử lý trong gateway.

Ví dụ điều tra:

~~~text
GET /v1/orders/ORD-1001 lỗi
    → /v1/health vẫn trả 200
    → kiểm tra route orders đang trỏ đúng backend chưa
    → xem gateway log có lỗi DNS/TLS/kết nối không
    → nếu request đã tới backend: đối chiếu backend log và dữ liệu
~~~

Cách đi từng chặng giúp tránh đổi policy xác thực khi nguyên nhân thật là backend không phân giải được DNS.

## 15. Phát hành, quay lui và kiểm soát chi phí

### 15.1. Quản lý specification cùng bản phát hành

Nên giữ specification trong quy trình quản lý phiên bản, gắn với cấu hình môi trường và backend tương ứng. Khi cập nhật, xem lại thay đổi của routes, policy, URL backend và function OCID.

Lưu ý các ranh giới:

- Đổi prefix hoặc bỏ route có thể làm client hiện tại không gọi được.
- Đổi backend có thể giữ nguyên URL nhưng làm thay đổi schema hoặc hành vi.
- Đổi policy có thể chặn client hợp lệ hoặc mở quyền ngoài dự định.
- Rollback deployment không tự rollback dữ liệu đã được backend ghi.

Một phương án dùng `/v2` song song `/v1` chỉ có ý nghĩa khi có hợp đồng, kế hoạch chuyển client và thời điểm ngừng phiên bản cũ. Không cần tạo phiên bản mới cho mọi thay đổi nội bộ tương thích.

### 15.2. Sẵn sàng của toàn chuỗi

Cần xét gateway, mạng, dịch vụ xác thực, backend và dữ liệu. Gateway hoạt động tốt nhưng backend hoặc cơ sở dữ liệu lỗi vẫn làm API thất bại.

Nếu có yêu cầu dự phòng region, chuẩn bị cả gateway, deployment, certificate, quyền, artifact backend và dữ liệu tại đích. Việc có hai deployment trên cùng gateway không phải một phương án dự phòng region.

Với backend trên nhiều instance, nên dùng lớp phân phối và cơ chế kiểm tra tình trạng phù hợp thay vì mặc định một URL backend riêng lẻ tự có tính sẵn sàng cao.

### 15.3. Ngân sách gắn với traffic thực tế

Đánh giá chi phí từ lượng API request, các backend bị kích hoạt, mạng, logs và dịch vụ liên quan. Tra bảng giá và điều kiện tenancy tại thời điểm triển khai; bài này không giả định một đơn giá cố định.

Các điểm cần đo:

| Yếu tố | Cách kiểm soát |
| --- | --- |
| Lượng request và retry | Rate limit, theo dõi client và chính sách thử lại |
| Backend Functions | Đo số lần gọi, thời gian chạy và tài nguyên |
| Backend database/API ngoài | Giới hạn đồng thời và truy cập không cần thiết |
| Logs | Chọn mức log, phạm vi dữ liệu và thời hạn lưu |
| Bản phát hành lab | Dọn tài nguyên thử khi không còn sử dụng |

Sau lab, chỉ xóa deployment và gateway được tạo riêng cho bài nếu không còn phụ thuộc. Không xóa VCN, policy hoặc function dùng chung chỉ vì bài thực hành đã kết thúc.

## 16. Các quyết định cần chốt cho một API

Một cấu hình đủ để tiếp tục triển khai cần trả lời được:

1. Client gọi hostname, prefix, path và method nào?
2. Mỗi route đi tới backend nào, dùng hợp đồng request/response gì?
3. Client đến gateway bằng mạng nào; gateway đến backend bằng mạng nào?
4. Ai được quản lý tài nguyên, ai được gọi API và gateway dùng quyền nào để gọi backend?
5. Timeout, rate limit, CORS và quyền nghiệp vụ được đặt ở đâu?
6. Có đủ log, metrics và bản cấu hình đã duyệt để điều tra hoặc quay lui không?

Với API orders, stock response xác minh điểm vào; HTTP integration xác minh service hiện có; Functions integration nối API với logic serverless. Tính đúng và tính sẵn sàng của API đến từ việc các chặng đó có cấu hình, quyền và hợp đồng dữ liệu nhất quán.
