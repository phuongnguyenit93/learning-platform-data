# Validation, CORS và xử lý lỗi API trên API Gateway và AppSync

## Mục tiêu học tập

Sau bài này, người học có thể:

- Phân biệt **validation ở tầng giao thức**, **validation đầu vào**, **quy tắc nghiệp vụ**, **authentication** và **authorization** trong API.
- Chọn đúng cách kiểm tra request cho **Amazon API Gateway REST API**, **API Gateway HTTP API** và **AWS AppSync GraphQL API**.
- Cấu hình và kiểm thử **CORS** gồm origin, preflight `OPTIONS`, allowed methods/headers, credentials, caching và response lỗi.
- Hiểu vì sao một request dùng `curl` có thể thành công nhưng trình duyệt vẫn báo **CORS error**, hoặc `OPTIONS` bị chặn bởi authorizer.
- Thiết kế hợp đồng lỗi HTTP nhất quán với **status code, error code, message, request ID**, không để lộ thông tin nội bộ.
- Phân biệt lỗi do **API Gateway tạo**, **Lambda/backend trả về**, **authorizer/WAF/throttling**, với lỗi **GraphQL schema/resolver**.
- Sử dụng `util.error` và `util.appendError` trong **AppSync APPSYNC_JS**, hiểu **partial data**, `errors.path` và **non-null propagation**.
- Kiểm thử bằng AWS Console, AWS CLI, `curl`, browser DevTools, CloudWatch, CloudTrail và các negative test.
- Thiết kế API an toàn với **IAM, Cognito/JWT, VPC, AWS Lambda, S3/DynamoDB/RDS**, logging, retry, monitoring và ngân sách.

**Bối cảnh:** Đây là bài của chương **API Gateway và AppSync**, thuộc module **CLOUD_PROVIDERS_AWS**. Trong hệ sinh thái AWS, người học sử dụng hạ tầng **Region/AZ**, IAM, VPC, compute, storage, database, tích hợp và serverless để triển khai ứng dụng có thể giám sát, phục hồi và kiểm soát chi phí. Một API đáng tin cậy không chỉ trả kết quả đúng khi dữ liệu hợp lệ: nó phải **từ chối đúng request sai**, **không rò rỉ dữ liệu**, **trả lỗi có thể chẩn đoán** và **chạy được từ trình duyệt ở origin đã được phê duyệt**.

> **Phạm vi:** Bài dùng API Gateway **REST API**, **HTTP API** và **AppSync GraphQL API**. Ba sản phẩm này có cơ chế validation/CORS/response khác nhau; không dùng một lệnh hoặc một policy chung cho tất cả. Các account ID, API ID, URL, domain và resource name là ví dụ, phải thay bằng tài nguyên lab thật trước khi thực thi.

## 1. Kiến trúc mẫu: request đi qua những lớp nào?

Giả sử ứng dụng bán hàng có hai cách cung cấp dữ liệu:

- **REST API:** `POST /orders` và `GET /orders/{id}` qua API Gateway → AWS Lambda Java hoặc HTTP backend.
- **GraphQL API:** `mutation createOrder` và `query getOrder` qua AppSync → DynamoDB/Lambda/HTTP data source.

~~~mermaid
flowchart TB
    Browser[Web app ở https://shop.example.com] --> CORS{Browser CORS policy}
    CORS --> REST[API Gateway REST / HTTP API]
    CORS --> GQL[AWS AppSync GraphQL]
    REST --> Auth[AuthN/AuthZ, throttling, routing]
    Auth --> Validate[Gateway validation nếu loại API hỗ trợ]
    Validate --> Lambda[Lambda / HTTP integration]
    Lambda --> Data[(DynamoDB / RDS / S3)]
    GQL --> Schema[GraphQL parsing + schema validation]
    Schema --> Resolver[Resolver / pipeline logic]
    Resolver --> Data
    REST --> Logs[CloudWatch / access logs]
    GQL --> Logs
~~~

**CORS không phải một gateway đứng trước tất cả traffic.** Đây là chính sách do **trình duyệt** áp dụng với cross-origin JavaScript requests, sử dụng headers mà server trả về. AWS backend vẫn có thể nhận request từ `curl`, SDK hoặc server-to-server dù browser không cho trang đọc response.

### Bốn câu hỏi khi một API request không thành công

1. **Browser có gửi request thật hay mới dừng ở preflight?** Kiểm tra DevTools Network.
2. **Gateway có nhận request và chấp nhận authentication/authorization không?** Xem HTTP status, gateway logs.
3. **Request có hợp lệ về cấu trúc/schema không?** Xem request validator, GraphQL schema, mapping.
4. **Backend có thực hiện được nghiệp vụ không?** Xem Lambda/resolver/data source logs, DB và downstream.

Nếu không tách bốn câu hỏi này, kỹ sư dễ “sửa CORS” khi lỗi thật là 401/403/500, hoặc mở toàn bộ quyền IAM khi chỉ thiếu một header `Access-Control-Allow-Origin`.

## 2. So sánh nhanh ba kiểu API trước khi cấu hình

| Tiêu chí | API Gateway **REST API** | API Gateway **HTTP API** | **AppSync GraphQL** |
| --- | --- | --- | --- |
| Mô hình endpoint | Resources, methods, stages, integration | Routes, integrations, stages | Một GraphQL endpoint/schema gồm Query/Mutation/Subscription |
| Validation tích hợp | **Request validators + Models** cho body/required params | **Không có cùng cơ chế REST request validators/models**; thường xử lý tại backend/authorizer | **GraphQL parser và schema type system** kiểm tra query/variables trước resolver |
| Business validation | Lambda/HTTP integration, service layer | Lambda/HTTP integration, service layer | Resolver, pipeline functions, Lambda/data source |
| CORS | Tùy integration: preflight `OPTIONS`, headers method/integration, gateway responses | **CORS configuration cấp API** có thể tự trả preflight/thêm headers | AppSync quản lý GraphQL endpoint/response; custom CORS không cấu hình qua resolver như REST |
| Auth | IAM, Cognito, Lambda authorizers và API key/usage plan theo tính năng | IAM, JWT/Lambda authorizers | API key, AWS IAM, Cognito User Pools, OIDC, Lambda authorizer theo config |
| Lỗi thông thường | HTTP status + body; có **Gateway Responses** cho lỗi do gateway tạo | HTTP status + body; không có cùng tính năng REST Gateway Responses | GraphQL envelope `data`, `errors`; không suy status chỉ từ HTTP 200 |
| Logging | Access + execution logs theo khả năng REST | Access logs/metrics | AppSync field logs, CloudWatch/X-Ray theo cấu hình |
| Chọn khi | Cần nhiều tính năng REST truyền thống, model/request validator/gateway responses | HTTP API đơn giản, latency/chi phí/tính năng phù hợp | Client cần GraphQL query fields, schema và resolvers |

**Không suy luận rằng HTTP API hỗ trợ tất cả tính năng của REST API.** Trước khi thiết kế dựa vào request validators, usage plans, mapping templates hoặc gateway responses, hãy kiểm tra **API type** cụ thể.

## 3. Validation không chỉ là JSON hợp lệ

Validation nên được chia theo **loại điều kiện** và **lớp chịu trách nhiệm**.

| Lớp | Ví dụ | Nơi phù hợp |
| --- | --- | --- |
| HTTP protocol/size/content type | Sai method, Content-Type, payload quá lớn | Gateway và backend |
| Required path/query/header | Thiếu `orderId`, thiếu header bắt buộc | REST method validator hoặc backend |
| JSON/schema/type | `quantity` không phải số, thiếu `customerId` | REST model validator, GraphQL schema, backend |
| Business invariant | Số lượng 1–20, hàng còn tồn, ngày giao không trong quá khứ | **Backend/domain service** hoặc AppSync resolver/pipeline |
| Authentication | Không có token, token hết hạn, chữ ký sai | API authorizer/Cognito/IAM |
| Authorization | Caller có được xem đơn hàng của tenant khác? | API auth + backend row/resource-level policy |
| Replay/idempotency | Cùng `Idempotency-Key` được gửi lại | Backend và dữ liệu bền vững |
| Rate/abuse control | Quá nhiều requests hoặc query quá sâu | Gateway throttling/WAF/AppSync query controls |

**Validation != authorization.** Request `{"orderId":"O-1"}` có thể hợp schema nhưng caller vẫn không được đọc đơn hàng của người khác. **CORS != authorization**: origin được cho phép không thể thay kiểm tra token/tenant.

### Nguyên tắc “fail early, but verify again”

- Từ chối dữ liệu **sai rõ ràng** càng sớm càng tốt để không gọi backend vô ích.
- Validate **nghiệp vụ và quyền** tại lớp chịu trách nhiệm dữ liệu, vì API còn có thể được gọi từ SDK, event source, nội bộ hoặc hệ thống khác.
- Trả thông báo lỗi giúp client sửa request nhưng không tiết lộ stack trace, SQL, ARN/secret, user tồn tại hay không khi thông tin này nhạy cảm.
- Luôn đặt giới hạn về kích thước/độ sâu/số lượng, tránh regex tốn CPU hoặc object chứa hàng trăm nghìn items làm kiệt tài nguyên.

## 4. REST API Gateway request validator làm được gì?

**API Gateway REST API** có **request validators** cấu hình trên **method**. Khi request không hợp lệ, gateway có thể từ chối với **HTTP 400** trước khi gửi vào integration.

Các kiểu phổ biến:

- **Validate body:** kiểm tra body theo **Model JSON Schema** được gán cho Content-Type.
- **Validate query string parameters and headers:** kiểm tra các tham số được đánh dấu required.
- **Validate body, query string parameters, and headers:** kết hợp hai nhóm.

**Giới hạn cần nhớ:**

1. Với path/query/header required, gateway chủ yếu kiểm tra **tham số có tồn tại và không rỗng**; **không tự kiểm tra format, range hoặc semantic value** của các tham số này.
2. Với body, gateway dùng model theo **content type** của request. Nếu **không có model phù hợp**, validation body có thể **không chạy**; cần thiết kế content-type mapping/default model phù hợp.
3. API Gateway model dựa trên **một subset JSON Schema Draft 4**, không thể giả định mọi từ khóa Draft mới hoặc mọi hành vi validator thư viện Java đều được hỗ trợ.
4. Validation tại gateway không tự kiểm tra nghiệp vụ như stock, ownership, giá đơn hàng, quota tenant.
5. Khi sửa model/validator của REST API, cần **deploy/redeploy stage** để client nhận cấu hình mới theo mô hình deployment.

### Ví dụ request sai cấu trúc

~~~http
POST /orders HTTP/1.1
Host: abc123.execute-api.ap-southeast-1.amazonaws.com
Content-Type: application/json

{"customerId":"C-100", "quantity":"five"}
~~~

Nếu model yêu cầu `quantity` là integer và validation body được bật đúng, gateway có thể từ chối `400 Bad Request` **trước khi invoke Lambda**.

## 5. Ví dụ REST Model: đơn hàng hợp lệ

Giả sử `POST /orders` cần:

- `customerId`: string không rỗng.
- `quantity`: integer, tối thiểu 1.
- `sku`: string bắt buộc.
- `note`: optional string.

Tệp `order-request-model.json`:

~~~json
{
  "$schema": "http://json-schema.org/draft-04/schema#",
  "title": "CreateOrderRequest",
  "type": "object",
  "required": ["customerId", "sku", "quantity"],
  "properties": {
    "customerId": {
      "type": "string",
      "minLength": 1
    },
    "sku": {
      "type": "string",
      "minLength": 1
    },
    "quantity": {
      "type": "integer",
      "minimum": 1
    },
    "note": {
      "type": "string"
    }
  }
}
~~~

**Tại sao vẫn phải validate backend?** API Gateway kiểm tra JSON schema trước integration theo khả năng hỗ trợ; nhưng “`sku` có tồn tại trong inventory?”, “quantity có vượt stock?” và “caller có quyền đặt hàng cho customerId này?” phải được xử lý ở domain service.

### Quy trình cấu hình REST API bằng Console

1. **API Gateway → REST API** đã có method `POST /orders`.
2. Trong **Models**, tạo model `CreateOrderRequest` với schema ở trên, content type `application/json`.
3. Tạo một **Request Validator** với `Validate request body` (có thể thêm required headers/params khi cần).
4. Trong **Method Request** của `POST`, gán request model vào `application/json` và chọn validator.
5. Bảo đảm model/body không bị bỏ qua do content type không khớp. Nếu cần default model, xem cách dùng `$default` theo tài liệu.
6. **Deploy API** tới stage lab.
7. Gửi valid/invalid requests, kiểm tra Lambda Invocations và gateway response; dữ liệu sai phải không tới backend khi validator đã từ chối.

### CLI tham khảo

~~~bash
aws apigateway create-model \
  --rest-api-id a1b2c3d4e5 \
  --name CreateOrderRequest \
  --content-type application/json \
  --schema file://order-request-model.json \
  --region ap-southeast-1 \
  --profile lab

aws apigateway create-request-validator \
  --rest-api-id a1b2c3d4e5 \
  --name validate-orders-body \
  --validate-request-body \
  --no-validate-request-parameters \
  --region ap-southeast-1 \
  --profile lab
~~~

Hai lệnh này tạo resources **nhưng chưa tự gắn validator/model vào method**. Cần đặt `requestValidatorId` và `requestModels` cho đúng REST method (qua Console, IaC hoặc REST API update-method), rồi deploy stage. Không chạy command tạo lại resource lặp vô hạn khi thấy validation chưa có hiệu lực.

## 6. JSON Schema cần gắn đúng content type

Lỗi dễ bỏ sót:

~~~text
Request Content-Type: application/json
Method Request Model: application/json → CreateOrderRequest
Result: body được kiểm tra theo model nếu validator bật.

Request Content-Type: text/plain
Method Request Model: chỉ application/json
Result: validation body có thể bị bỏ qua theo config.
~~~

**`$default` model** có thể được dùng khi muốn chọn model ngay cả khi client gửi Content-Type khác. Nhưng nếu API chỉ chấp nhận JSON, nên có quy tắc **415 Unsupported Media Type** theo gateway/backend policy thay vì đơn thuần parse body sai.

Hãy phân biệt:

- **Validation body:** kiểm tra shape/constraint theo model.
- **Passthrough behavior/mapping template:** quy định request body nào được chuyển tiếp khi integration không có mapping tương ứng.
- **Content negotiation:** `Content-Type` mô tả request; `Accept` mô tả loại response client mong muốn.

Một body `{"quantity":1}` là JSON hợp lệ về cú pháp nhưng không hợp schema vì thiếu `customerId` và `sku`. Một body `{quantity: 1}` không phải JSON hợp lệ. Hai trường hợp cần có test riêng.

## 7. HTTP API Gateway: validate ở backend, không giả định có REST Model

**HTTP API** tối ưu hóa cho nhiều workload HTTP thông thường nhưng không cung cấp **REST API Request Validators/Models** với cùng cách cấu hình method. Vì vậy:

- Parse/validate request body trong **Lambda**, ECS/HTTP backend hoặc lớp ứng dụng.
- Có thể dùng **JWT/Lambda authorizer**, IAM auth theo route và WAF/throttling theo khả năng dịch vụ để từ chối traffic không hợp lệ về quyền/tần suất.
- Dùng OpenAPI/JSON Schema/Bean Validation như **contract của ứng dụng** và test CI, thay vì cho rằng import OpenAPI vào HTTP API sẽ tự bật mọi kiểu JSON body validation.
- Trả `400` hoặc `422` theo tiêu chuẩn đội ngũ, giữ response nhất quán và thông tin lỗi tối thiểu.

**Ví dụ:** HTTP API `POST /orders` → Lambda Java. Lambda phải parse JSON, kiểm tra `quantity`, validate `sku` và quyền của caller; gateway có thể xử lý authentication/routing nhưng không tự thực hiện schema validation kiểu REST.

### Không đẩy business validation vào authorizer

Authorizer xác định danh tính và phạm vi truy cập, không nên truy vấn stock hoặc validate chi tiết mọi order item. Nếu nhét business validation vào authorizer:

- Khó trả lỗi trường dữ liệu chính xác.
- Khó kiểm soát caching và stale decisions.
- Dễ tăng chi phí và latency.
- Trộn hai trách nhiệm validation và authorization.

AuthN/AuthZ phải diễn ra ở lớp hợp lý, còn business invariant ở backend service/resolver có quyền truy cập dữ liệu nhất quán.

## 8. Java Lambda: trả HTTP 400 có cấu trúc cho dữ liệu sai

Với API Gateway **Lambda proxy integration**, Lambda có thể trả một response dạng:

~~~json
{
  "statusCode": 400,
  "headers": {
    "Content-Type": "application/problem+json",
    "Access-Control-Allow-Origin": "https://shop.example.com"
  },
  "body": "{\"type\":\"https://api.example.com/problems/validation\",\"title\":\"Invalid request\",\"status\":400,\"code\":\"VALIDATION_FAILED\"}"
}
~~~

**Quan trọng:** `body` trong proxy response là **JSON string**, không phải object Java có thể trả lồng trực tiếp tùy tiện. Với HTTP API payload format `2.0`, Lambda có thêm những response inference rules trong một số trường hợp; để tương thích, dễ hiểu và kiểm soát status/headers, nên **trả cấu trúc rõ ràng**.

### Ví dụ handler Java có kiểm tra input

Ví dụ giả định project có `aws-lambda-java-core` và Jackson ObjectMapper trong artifact Java. Contract dùng event dạng API Gateway proxy có trường `body`.

~~~java
package com.example.api;

import com.amazonaws.services.lambda.runtime.Context;
import com.amazonaws.services.lambda.runtime.RequestHandler;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;

import java.util.LinkedHashMap;
import java.util.Map;

public final class CreateOrderHandler
    implements RequestHandler<Map<String, Object>, Map<String, Object>> {

    private static final ObjectMapper JSON = new ObjectMapper();
    private static final String ORIGIN = "https://shop.example.com";

    @Override
    public Map<String, Object> handleRequest(
        Map<String, Object> event, Context context) {

        String requestId = context.getAwsRequestId();

        try {
            String body = (String) event.getOrDefault("body", "");
            JsonNode input = JSON.readTree(body);

            if (input == null || !input.isObject()) {
                return problem(400, "INVALID_JSON",
                    "Request body must be a JSON object", requestId);
            }

            JsonNode customerId = input.path("customerId");
            JsonNode quantity = input.path("quantity");
            JsonNode sku = input.path("sku");

            if (!customerId.isTextual() || customerId.asText().isBlank()
                || !sku.isTextual() || sku.asText().isBlank()
                || !quantity.isIntegralNumber() || quantity.asInt() < 1) {
                return problem(400, "VALIDATION_FAILED",
                    "customerId, sku and positive quantity are required",
                    requestId);
            }

            // Production: kiểm tra auth/tenant, inventory, idempotency,
            // lưu đơn bằng transaction rồi trả mã định danh.
            Map<String, Object> result = Map.of(
                "orderId", "ORD-LAB-1",
                "status", "ACCEPTED"
            );

            return reply(201, result, requestId, "application/json");
        } catch (com.fasterxml.jackson.core.JsonProcessingException ex) {
            return problem(400, "INVALID_JSON",
                "Request body is not valid JSON", requestId);
        } catch (Exception ex) {
            context.getLogger().log(
                "Unexpected error; requestId=" + requestId);
            // Không gửi stack trace hoặc secret về client.
            return problem(500, "INTERNAL_ERROR",
                "Internal server error", requestId);
        }
    }

    private Map<String, Object> problem(
        int status, String code, String detail, String requestId) {

        Map<String, Object> fields = new LinkedHashMap<>();
        fields.put("type", "https://api.example.com/problems/" + code);
        fields.put("title", "Request failed");
        fields.put("status", status);
        fields.put("code", code);
        fields.put("detail", detail);
        fields.put("requestId", requestId);

        return reply(status, fields, requestId, "application/problem+json");
    }

    private Map<String, Object> reply(
        int status, Object data, String requestId, String contentType) {
        try {
            return Map.of(
                "statusCode", status,
                "headers", Map.of(
                    "Content-Type", contentType,
                    "Access-Control-Allow-Origin", ORIGIN,
                    "Vary", "Origin",
                    "X-Request-Id", requestId
                ),
                "isBase64Encoded", false,
                "body", JSON.writeValueAsString(data)
            );
        } catch (Exception ex) {
            throw new IllegalStateException("Cannot serialize response", ex);
        }
    }
}
~~~

**Hạn chế có chủ đích của ví dụ:**

- Đây là **handler minh họa**, không phải API production: chưa có authentication/authorization, transaction, idempotency, schema đầy đủ hoặc logic đặt hàng.
- Handler trả CORS header cố định cho origin được phê duyệt; **không tự động tin giá trị `Origin`**. Với nhiều origins, phải match exact allowlist và set `Vary: Origin` khi phản hồi động.
- Với **HTTP API có CORS configuration** tại gateway, API Gateway **bỏ qua CORS headers từ backend integration**; không cần xử lý hai nơi chồng lấn.
- `JsonNode.asInt()` có thể tràn/ép không như mong muốn nếu số vượt phạm vi; production cần validate range/size bằng cách rõ ràng hơn.
- Lambda source phải được build kèm Jackson, handler name và dependency tương ứng. Runtime exception do lỗi serialization vẫn cần được báo qua logs/alerts và chuẩn hóa bởi lớp lỗi thích hợp.

## 9. GraphQL AppSync: schema kiểm tra gì trước resolver?

**AWS AppSync GraphQL API** dựa vào schema gồm **types, fields, arguments, input types, enums và nullability**. GraphQL engine parse/validate request trước khi gọi field resolvers.

Ví dụ schema:

~~~graphql
schema {
  query: Query
  mutation: Mutation
}

enum OrderStatus {
  CREATED
  PAID
  CANCELLED
}

input CreateOrderInput {
  customerId: ID!
  sku: String!
  quantity: Int!
  note: String
}

type Order {
  id: ID!
  customerId: ID!
  sku: String!
  quantity: Int!
  status: OrderStatus!
}

type Query {
  getOrder(id: ID!): Order
}

type Mutation {
  createOrder(input: CreateOrderInput!): Order!
}
~~~

Các điều kiện GraphQL engine có thể từ chối trước resolver:

- Query gọi một field **không có** trong schema.
- Argument bắt buộc kiểu `ID!` bị bỏ qua hoặc null.
- Input có type không hợp lệ với field hoặc enum value không được định nghĩa.
- Query viết sai syntax hoặc selection set không hợp lý.
- Request vượt một số query complexity/depth/resolver limits được cấu hình.

**Nhưng GraphQL schema không tự biết `quantity` phải từ 1 đến 20**, `sku` có còn hàng hay customer thuộc tenant nào. Những điều kiện đó phải kiểm tra trong resolver/pipeline/backend.

### Non-null có ý nghĩa cả ở input lẫn output

- `quantity: Int!`: client cần cung cấp một số nguyên không null; **không đồng nghĩa số đó > 0**.
- `status: OrderStatus!`: resolver phải trả enum hợp lệ, không null. Nếu data source trả null không hợp contract, GraphQL có thể tạo lỗi và **lan truyền null lên field cha** theo quy tắc GraphQL.

Cần chủ động thiết kế nullable fields và error strategy, tránh một field quá chặt làm `data` của cả operation trở thành null khi có một lỗi con.

## 10. AppSync business validation trong APPSYNC_JS resolver

AWS AppSync hỗ trợ resolver bằng **APPSYNC_JS** và VTL. Với APPSYNC_JS, dùng các utility tích hợp:

- `util.error(message, errorType, ...)`: tạo field error và **ngừng evaluation** tại điểm gọi.
- `util.appendError(message, errorType, ...)`: ghi lỗi nhưng **không ngừng execution**, có thể trả partial data.
- `ctx.args`: arguments của GraphQL field.
- `ctx.identity`: identity claims/context khi có authentication.
- `ctx.result`, `ctx.error`: kết quả hoặc lỗi của data source theo ngữ cảnh resolver.

### Ví dụ NONE data source để minh họa validation

Gắn **unit resolver `Mutation.createOrder`** với một **NONE data source**, runtime **APPSYNC_JS**. Không ghi database thật trong ví dụ này.

~~~javascript
import { util } from '@aws-appsync/utils';

export function request(ctx) {
  const input = ctx.args.input;

  if (input.quantity < 1 || input.quantity > 20) {
    util.error(
      'quantity must be between 1 and 20',
      'VALIDATION_FAILED'
    );
  }

  if (input.sku.trim().length === 0) {
    util.error('sku must not be blank', 'VALIDATION_FAILED');
  }

  // NONE data source: payload sẽ có tại ctx.result trong response().
  return {
    payload: {
      id: 'ORD-LAB-1',
      customerId: input.customerId,
      sku: input.sku,
      quantity: input.quantity,
      status: 'CREATED'
    }
  };
}

export function response(ctx) {
  if (ctx.error) {
    util.error('Unable to process order', 'INTERNAL_ERROR');
  }
  return ctx.result;
}
~~~

**Đây chỉ là ví dụ học**, cần kiểm thử các phép toán/string helpers với runtime `APPSYNC_JS` và schema thực. Không dùng NONE data source để tuyên bố đã tạo đơn hàng. Production cần kiểm tra quyền người dùng/tenant, tồn kho, idempotency và ghi dữ liệu qua DynamoDB/Lambda/HTTP data source theo semantics phù hợp.

**Không dùng `throw new Error(...)` như JavaScript chạy trong Node.js**: APPSYNC_JS là runtime giới hạn, có utility `util.error` cho lỗi field và không hỗ trợ tất cả Web/Node APIs. Nó không tự mở HTTP socket hoặc filesystem; I/O được AppSync thực hiện qua data sources đã cấu hình.

### VTL tương đương

Nếu hệ thống legacy dùng VTL, có thể dùng:

~~~vtl
#if($ctx.args.input.quantity < 1)
  $util.error("quantity must be positive", "VALIDATION_FAILED")
#end
$util.toJson($ctx.args.input)
~~~

Đây là **đoạn minh họa validation**, không phải mapping template hoàn chỉnh cho mọi data source. Không copy VTL request mapping này cho DynamoDB rồi kỳ vọng có `operation`/key đầy đủ.

## 11. AppSync pipeline resolver và lỗi một bước

Với pipeline resolver, có thể tách:

~~~mermaid
flowchart LR
    Query[GraphQL createOrder] --> Schema[Schema validation]
    Schema --> Auth[AuthN/AuthZ]
    Auth --> R[Pipeline resolver]
    R --> V[Function 1: validate input / tenant]
    V --> I[Function 2: inventory check]
    I --> D[Function 3: DynamoDB conditional write]
    D --> Out[GraphQL response data/errors]
~~~

**Vì sao pipeline hữu ích?**

- Validation business không bị lặp ở nhiều field resolvers.
- Có thể tách validate → authorize → data operation, quản lý `ctx.stash` và `ctx.prev.result` theo cơ chế AppSync.
- `util.error` có thể dừng pipeline ngay để không ghi dữ liệu khi input invalid.
- `util.appendError` có thể để pipeline tiếp tục và trả partial data **nếu điều đó an toàn về nghiệp vụ**.

**Cẩn thận:** Cho pipeline tiếp tục sau khi phát hiện lỗi tạo đơn hàng có thể gây side effect không mong đợi. Với mutation quan trọng, thường nên **fail-fast** và đảm bảo transaction/idempotency ở database. `appendError` phù hợp hơn cho trường hợp partial read hoặc lỗi optional field được thiết kế trước.

### GraphQL resolver error không phải luôn HTTP 500

GraphQL response có thể trả HTTP 200 **kèm `errors`** khi operation được xử lý ở tầng GraphQL nhưng một field resolver lỗi. Một lỗi parse/validation, authentication hoặc transport có thể dùng status HTTP khác. **Client phải đọc cả HTTP status, `data` và `errors`**, không chỉ kiểm tra `response.ok`.

## 12. CORS là gì, browser quyết định ra sao?

**Cross-Origin Resource Sharing (CORS)** là cơ chế mà server dùng **response headers** để nói với browser một trang ở origin nào được phép truy cập response cross-origin bằng JavaScript.

Một **origin** được xác định bởi:

~~~text
scheme + host + port
~~~

Ví dụ:

- `https://shop.example.com`
- `http://shop.example.com`
- `https://api.example.com`
- `https://shop.example.com:8443`

Bốn origin này **khác nhau** theo scheme/host/port.

**CORS không bảo đảm request nguy hiểm không đến server.** Browser có thể gửi một số loại request trước khi kiểm tra response; non-browser clients không bị browser CORS áp dụng. **Không coi CORS là tường lửa, CSRF prevention hay chính sách IAM.**

### Simple request và request cần preflight

Một số request thỏa điều kiện *CORS-safelisted/simple* có thể được browser gửi trực tiếp. Ví dụ GET với headers đơn giản thường không preflight.

Các request thường dẫn tới **preflight OPTIONS**:

- `POST` với `Content-Type: application/json`;
- Request gửi `Authorization` header;
- Sử dụng method như `PUT`, `DELETE`;
- Gửi custom headers như `X-Idempotency-Key`.

Các chi tiết phụ thuộc chuẩn Fetch/CORS của browser, nên cần kiểm tra request thực qua DevTools; đừng đoán chỉ từ method.

## 13. Luồng preflight OPTIONS và response thật

Giả sử frontend `https://shop.example.com` gọi:

~~~javascript
fetch('https://api.example.com/orders', {
  method: 'POST',
  headers: {
    'Content-Type': 'application/json',
    'Authorization': 'Bearer <access-token>'
  },
  body: JSON.stringify({ customerId: 'C-100', sku: 'SKU-1', quantity: 2 })
});
~~~

Browser thường gửi **preflight** trước:

~~~http
OPTIONS /orders HTTP/1.1
Host: api.example.com
Origin: https://shop.example.com
Access-Control-Request-Method: POST
Access-Control-Request-Headers: authorization,content-type
~~~

Server/gateway trả ví dụ:

~~~http
HTTP/1.1 204 No Content
Access-Control-Allow-Origin: https://shop.example.com
Access-Control-Allow-Methods: GET,POST,OPTIONS
Access-Control-Allow-Headers: authorization,content-type
Access-Control-Max-Age: 300
Vary: Origin
~~~

Nếu preflight được browser chấp nhận, browser mới gửi `POST` thật. Response cho `POST` cũng phải có CORS headers hợp lệ, ví dụ:

~~~http
HTTP/1.1 201 Created
Content-Type: application/json
Access-Control-Allow-Origin: https://shop.example.com
Vary: Origin

{"orderId":"ORD-1001","status":"CREATED"}
~~~

**Chỉ cấu hình `OPTIONS` không đủ.** Nếu backend trả `201` mà thiếu `Access-Control-Allow-Origin`, browser vẫn không cho JavaScript đọc response. Tương tự, nếu backend trả `400/401/403/500` nhưng thiếu CORS headers, client chỉ thấy “CORS error” thay vì error message thật.

~~~mermaid
sequenceDiagram
    participant Browser as Browser frontend
    participant API as API Gateway / AppSync endpoint
    participant Backend as Backend / Resolver
    Browser->>API: OPTIONS + Origin + requested method/headers
    API-->>Browser: CORS preflight response
    alt Allowed
      Browser->>API: POST /orders + token + JSON
      API->>Backend: Invoke khi auth/validation cho phép
      Backend-->>API: 201 hoặc 4xx/5xx
      API-->>Browser: Response + CORS headers
    else Rejected
      Note over Browser: Không gửi actual request từ fetch
    end
~~~

## 14. REST API Gateway CORS: proxy và non-proxy khác nhau

### 14.1. Non-proxy integration

Với REST API **non-proxy integration** (ví dụ mapping templates), cấu hình thường bao gồm:

1. Tạo `OPTIONS` method không yêu cầu authentication cho preflight thông thường.
2. Dùng **MOCK integration** hoặc một integration phù hợp trả response với:
   - `Access-Control-Allow-Origin`
   - `Access-Control-Allow-Methods`
   - `Access-Control-Allow-Headers`
3. Đảm bảo **method response/integration response mapping** đưa CORS headers vào **actual responses**, gồm các status cần hỗ trợ.
4. Đánh giá trường hợp binary media types `*/*` và `contentHandling=CONVERT_TO_TEXT` cho preflight nếu cần.
5. **Deploy lại REST API stage** để thay đổi có hiệu lực.

Console có tính năng **Enable CORS**, nhưng không tự đảm bảo mọi integration/error response đã cấu hình chuẩn. Sau khi bật, vẫn cần **test preflight và mọi actual response**.

### 14.2. Lambda proxy integration

Với REST API **Lambda proxy**, backend phải trả CORS headers cho actual responses. Gateway **không có integration response mapping thường dùng** để tự thêm CORS headers vào mọi response proxy.

Ví dụ (Node.js, chỉ minh họa response shape):

~~~javascript
export const handler = async (event) => ({
  statusCode: 400,
  headers: {
    'Content-Type': 'application/problem+json',
    'Access-Control-Allow-Origin': 'https://shop.example.com',
    'Vary': 'Origin'
  },
  body: JSON.stringify({
    code: 'VALIDATION_FAILED',
    message: 'quantity must be positive'
  })
});
~~~

Phần `OPTIONS` có thể do MOCK `OPTIONS` method hoặc backend route được cấu hình xử lý, tùy thiết kế. **Không để JWT/Lambda authorizer bắt token cho một preflight thông thường vốn không mang bearer token như actual request**.

### 14.3. Lỗi do gateway tạo: Gateway Responses

Ngay cả khi Lambda đã trả CORS headers đầy đủ, API Gateway vẫn có thể tự tạo lỗi:

- `UNAUTHORIZED`, `ACCESS_DENIED`;
- `BAD_REQUEST_BODY`, `BAD_REQUEST_PARAMETERS`;
- `MISSING_AUTHENTICATION_TOKEN`;
- `THROTTLED`, `DEFAULT_4XX`, `DEFAULT_5XX`;
- Lỗi configuration/integration.

Với **REST API**, tính năng **Gateway Responses** cho phép tùy chỉnh một số response types, gồm body, status và headers theo khả năng dịch vụ. Bạn có thể thêm `Access-Control-Allow-Origin` cho những lỗi này để browser thấy 4xx/5xx thật thay vì thông báo CORS giả.

**Cẩn thận:** Gateway Responses không phải là response Lambda. Nếu backend tự trả `400` hoặc `409`, phải bảo đảm **backend/integration response** đã chứa CORS headers tương ứng. Với REST API có **WAF custom response**, kiểm tra tính ưu tiên so với gateway response.

## 15. HTTP API Gateway CORS: cấu hình ở cấp API

Với **HTTP API**, CORS configuration có các trường:

- `allowOrigins`
- `allowMethods`
- `allowHeaders`
- `allowCredentials`
- `exposeHeaders`
- `maxAge`

Khi bật CORS cho HTTP API, **API Gateway tự có thể phản hồi preflight OPTIONS** và thêm configured CORS headers vào responses của integration. **Nếu đã bật CORS config, API Gateway bỏ qua CORS headers do backend trả về** đối với CORS processing. Đây là khác biệt quan trọng so với REST Lambda proxy.

### Ví dụ CORS configuration cho HTTP API

Tệp `http-api-cors.json`:

~~~json
{
  "AllowOrigins": ["https://shop.example.com"],
  "AllowMethods": ["GET", "POST", "OPTIONS"],
  "AllowHeaders": [
    "content-type",
    "authorization",
    "x-idempotency-key"
  ],
  "AllowCredentials": false,
  "ExposeHeaders": ["x-request-id"],
  "MaxAge": 300
}
~~~

Áp dụng cho API lab đã tồn tại:

~~~bash
aws apigatewayv2 update-api \
  --api-id a1b2c3d4 \
  --cors-configuration file://http-api-cors.json \
  --region ap-southeast-1 \
  --profile lab
~~~

Đây là **AWS CLI API Gateway v2** dành cho HTTP API, không phải `aws apigateway` REST API v1. Kiểm tra stage/deploy behavior của API đang dùng; các thay đổi có thể cần deployment nếu auto-deploy đã tắt.

### Trường hợp `$default` route có authorizer

`$default` bắt nhiều đường/method không có route riêng, bao gồm `OPTIONS`. Khi `$default` có authorizer và preflight không mang token, request có thể bị `401`.

Theo hướng dẫn AWS cho HTTP API, hãy cân nhắc tạo **`OPTIONS /{proxy+}`** route **không yêu cầu authorization** với integration phù hợp, có routing priority cao hơn `$default`. Chỉ miễn auth cho preflight route; **actual POST/GET vẫn phải được xác thực và phân quyền**.

**Không mở tất cả methods cho public** để sửa riêng lỗi OPTIONS.

## 16. AppSync GraphQL và CORS: không cấu hình như REST

AWS AppSync cung cấp **GraphQL HTTPS endpoint** quản lý request/response GraphQL; client browser thường POST JSON chứa query, variables và header authorization/API key.

CORS trong AppSync có các điểm phải phân biệt:

- AppSync xử lý giao thức/headers của **GraphQL endpoint được quản lý**. Không có REST API `OPTIONS` MOCK method để bật như API Gateway REST.
- APPSYNC_JS/VTL có helper thêm **một số custom response headers**, nhưng **không được tự đặt nhiều headers CORS chuẩn** như `Access-Control-Allow-Origin`, `Access-Control-Allow-Methods`, `Access-Control-Allow-Headers` bằng `util.http.addResponseHeader` vì chúng thuộc danh sách **restricted response headers**.
- Nếu cần **giới hạn frontend origins** theo chính sách riêng, có thể đánh giá **CloudFront** hoặc proxy bảo mật ở phía trước AppSync, dùng **response headers policy + origin request/cache policy** đúng với GraphQL, theo phương án AWS hỗ trợ.
- Tránh dùng custom proxy làm sai **authorization header, API key/host, WebSocket subscription handshake**, caching hoặc response content type.
- Không coi CORS là cách giới hạn **ai được gọi GraphQL API**; AppSync authentication modes và field-level authorization mới là cơ chế access control.

**Thực tế cần làm:** Dùng DevTools để kiểm tra request đến AppSync endpoint; nếu có CloudFront/custom domain ở giữa, xác định **lớp nào đang trả CORS headers**. Một lỗi CORS có thể do proxy cache header cho sai origin, preflight bị chặn bởi WAF/CloudFront hoặc response 403 thiếu headers; không nên sửa resolver business validation để chữa lỗi browser policy.

## 17. CORS, cookies, credentials và vấn đề bảo mật

### 17.1. Không dùng wildcard cho credentialed CORS response

Khi browser gửi cross-origin request với **credentials mode include** (ví dụ cookies hoặc HTTP auth theo trường hợp), response cần origin **cụ thể**, không phải:

~~~http
Access-Control-Allow-Origin: *
Access-Control-Allow-Credentials: true
~~~

Cấu hình trên **không hợp lệ cho credentialed CORS** trong browser. Cách thiết kế:

~~~http
Access-Control-Allow-Origin: https://shop.example.com
Access-Control-Allow-Credentials: true
Vary: Origin
~~~

Phải match origin chính xác theo allowlist đã phê duyệt. **Không phản chiếu `Origin` bất kỳ** rồi trả `Allow-Credentials: true`, vì một trang độc hại có thể đọc dữ liệu user nếu các điều kiện cookie/auth cho phép.

### 17.2. Cookie, SameSite và CSRF

CORS chỉ kiểm soát **script đọc cross-origin response**, không phải cơ chế đầy đủ chống **Cross-Site Request Forgery (CSRF)**. Với cookie-based sessions:

- Dùng **Secure, HttpOnly, SameSite** theo threat model;
- có cơ chế CSRF token/origin checks cho state-changing endpoints khi cần;
- không cho phép origins không được tin cậy kèm credentials;
- kiểm soát domain/path/expiry và session invalidation.

Với bearer tokens trong `Authorization` header, cần bảo vệ token trong frontend khỏi XSS; CORS cấu hình chính xác không tự giảm rủi ro XSS hay token theft.

### 17.3. Cache preflight và headers theo origin

`Access-Control-Max-Age` có thể giúp browser cache preflight theo giới hạn browser. Nếu server chọn `Access-Control-Allow-Origin` động theo request `Origin`, đặt **`Vary: Origin`** để HTTP caches không dùng response CORS của origin A cho origin B.

Nếu có **CloudFront/CDN**, kiểm tra cache key và origin forwarding, nhất là với credentialed requests hoặc dữ liệu per-user. **Không cache GraphQL/REST auth responses ở tầng CDN chung** nếu thiếu cache partitioning/authorization strategy.

### 17.4. CORS không thể ngăn non-browser clients

Một attacker dùng script/server/CLI không bị browser CORS giới hạn. Muốn bảo vệ API cần:

- Authentication (JWT/Cognito/IAM/OIDC/Lambda authorizer);
- Authorization theo resource/tenant;
- Rate limiting/WAF, input validation;
- Network policies trong VPC khi thích hợp;
- Logging, monitoring và cơ chế ngăn abuse.

**Đừng dùng danh sách allowed origins như cơ chế bảo mật duy nhất của API**.

## 18. Hợp đồng lỗi REST/HTTP nhất quán

API nên có một **error contract** được document và test. Ví dụ dùng **RFC 9457 Problem Details for HTTP APIs** làm cơ sở:

~~~http
HTTP/1.1 400 Bad Request
Content-Type: application/problem+json
Access-Control-Allow-Origin: https://shop.example.com
X-Request-Id: req-7ac21
~~~

~~~json
{
  "type": "https://api.example.com/problems/validation",
  "title": "Invalid request",
  "status": 400,
  "detail": "One or more fields are invalid",
  "instance": "/orders",
  "code": "VALIDATION_FAILED",
  "requestId": "req-7ac21",
  "invalidParams": [
    {
      "name": "quantity",
      "reason": "must be between 1 and 20"
    }
  ]
}
~~~

**`code`, `requestId`, `invalidParams` là extension fields** do ứng dụng thiết kế, không phải tất cả trường đều bắt buộc trong RFC. `title` và `detail` hướng tới client, không dùng để đổ log stack trace ra public.

### Lựa chọn status code

| Tình huống | HTTP status thường phù hợp | Gợi ý error code |
| --- | --- | --- |
| JSON parse/schema invalid | **400 Bad Request** | `INVALID_JSON` / `VALIDATION_FAILED` |
| Content type không hỗ trợ | **415 Unsupported Media Type** | `UNSUPPORTED_MEDIA_TYPE` |
| Không có/không hợp lệ credentials | **401 Unauthorized** | `UNAUTHENTICATED` |
| Đã biết danh tính nhưng thiếu quyền | **403 Forbidden** | `ACCESS_DENIED` |
| Resource không tồn tại | **404 Not Found** | `ORDER_NOT_FOUND` |
| Trạng thái dữ liệu xung đột | **409 Conflict** | `ORDER_ALREADY_EXISTS` |
| Đầu vào hợp cú pháp nhưng sai business rule | **400** hoặc **422 Unprocessable Content** theo contract | `INVALID_QUANTITY` |
| Quá nhiều request | **429 Too Many Requests** | `RATE_LIMITED` |
| Lỗi bất ngờ của service | **500 Internal Server Error** | `INTERNAL_ERROR` |
| Gateway/đường tích hợp lỗi | **502 Bad Gateway** | `UPSTREAM_ERROR` |
| Backend tạm thời không sẵn sàng | **503 Service Unavailable** | `SERVICE_UNAVAILABLE` |
| Integration timeout | **504 Gateway Timeout** | `UPSTREAM_TIMEOUT` |

**Không máy móc dùng 422 cho mọi business error.** Nếu API đã chọn 400 cho input/business validation, hãy giữ nhất quán; dùng 409 cho trạng thái tài nguyên conflict, 403 cho quyền thật sự bị từ chối.

### Correlation ID và retry hints

- Sinh hoặc truyền **request ID/correlation ID** để nối gateway logs → Lambda → RDS/SQS.
- Với **429/503**, cân nhắc header `Retry-After` khi biết thời điểm retry hữu ích.
- Với lỗi timeout/transient, client dùng **exponential backoff + jitter** và **idempotency key** để tránh duplicate side effects.
- Không trả `Retry-After` cố định nếu backend không biết lúc phục hồi.

## 19. Phân biệt gateway error, integration error và application error

### 19.1. Gateway tự từ chối trước backend

Ví dụ REST request model validation fail. Lambda **không được gọi**, API Gateway trả lỗi 400 theo cơ chế gateway. Muốn thống nhất body/CORS cho các lỗi này, dùng **REST Gateway Responses** đúng response type.

### 19.2. Lambda trả lỗi nghiệp vụ chủ động

Lambda xử lý và trả:

~~~json
{
  "statusCode": 409,
  "headers": {
    "Content-Type": "application/problem+json",
    "Access-Control-Allow-Origin": "https://shop.example.com"
  },
  "body": "{\"code\":\"ORDER_ALREADY_EXISTS\",\"detail\":\"Order already exists\"}"
}
~~~

Đây là **application-level response**. Nếu Lambda dùng Lambda proxy và trả body/status hợp lệ, API Gateway chuyển theo integration mode, không tự chuyển mọi `409` thành `500`.

### 19.3. Lambda ném exception hoặc response sai định dạng

Nếu Lambda throw exception, timeout hoặc trả format proxy không hợp lệ, API Gateway có thể trả **5xx như 502** tùy integration. **Lỗi runtime không tương đương response `{"statusCode":400}`**.

Với REST **non-proxy**, response mapping và integration response selection logic có thể biến lỗi backend thành status cụ thể; nếu cấu hình sai, gateway có thể tạo 5xx hoặc kết quả không mong đợi. Đọc integration logs và status codes thay vì sửa nhầm business logic.

### 19.4. Authentication và throttling

Authorizer, IAM, WAF hoặc throttling có thể từ chối **trước khi Lambda chạy**. Kiểm tra:

- `401`: token không có/sai/hết hạn;
- `403`: bị deny, scope thiếu, resource/method policy, WAF hoặc thiếu quyền;
- `429`: bị throttled do API/usage limits hay backend theo response thực;
- `5xx`: integration/config failure hoặc backend lỗi.

**Phân loại 401/403 theo response thực của API type/authorizer**, vì một số AWS response names/status có các trường hợp đặc thù. Không chỉ nhìn string `Missing Authentication Token` rồi kết luận chắc chắn người dùng không có token: ở REST API nó cũng có thể xuất hiện khi route/method/stage không đúng.

## 20. GraphQL error contract khác HTTP status code như thế nào?

Một response AppSync/GraphQL điển hình:

~~~json
{
  "data": {
    "getOrder": null
  },
  "errors": [
    {
      "path": ["getOrder"],
      "locations": [
        {"line": 2, "column": 3}
      ],
      "message": "Order not found",
      "errorType": "NOT_FOUND"
    }
  ]
}
~~~

**Đặc điểm:**

- `data` có thể chứa **một phần thành công** và một số field null.
- `errors` là danh sách lỗi GraphQL; với AppSync có thể có `errorType` và những field AWS cụ thể.
- `path` giúp client biết field nào lỗi, hữu ích khi một query trả nhiều nhánh dữ liệu.
- Nếu field lỗi có kiểu **non-null**, GraphQL có thể **bubbling null** lên cha nullable gần nhất, thậm chí `data: null`.
- **HTTP 200 vẫn có thể chứa `errors`**; nhưng authentication/validation/transport errors có thể có HTTP status khác. Client phải kiểm tra cả hai.

### Ví dụ partial data

Giả sử query:

~~~graphql
query HomePage {
  getOrder(id: "ORD-1001") {
    id
    status
  }
  listProducts {
    id
    name
  }
}
~~~

Nếu `getOrder` lỗi nhưng `listProducts` thành công, response có thể chứa data cho sản phẩm và error riêng cho order. Điều này là **tính năng có chủ đích của GraphQL**, không phải lúc nào HTTP 500 cũng đúng.

### `util.error` và `util.appendError`

- **`util.error`:** thích hợp khi field không thể xử lý tiếp, validation/auth failure hoặc lỗi dữ liệu bắt buộc.
- **`util.appendError`:** phù hợp khi muốn trả phần dữ liệu có ích và ghi lỗi cho client; phải bảo đảm không vi phạm schema non-null và không thực hiện side effect không đáng có.

**Không gửi `ctx.error.message` hoặc toàn bộ AWS SDK exception ra client vô điều kiện**: response có thể lộ table ARN, khóa, dữ liệu nội bộ hoặc chi tiết permission.

## 21. AppSync authorization không thay schema validation

AppSync có các authorization modes theo cấu hình: **API_KEY**, **AWS_IAM**, **AMAZON_COGNITO_USER_POOLS**, **OPENID_CONNECT** và **AWS_LAMBDA** theo khả năng dịch vụ. Có thể áp dụng các directive hỗ trợ ở schema để giới hạn quyền theo field.

Khác biệt:

- **Authentication:** Caller là ai? Dùng JWT, IAM SigV4, API key hoặc Lambda authorizer theo API configuration.
- **Authorization:** Caller có quyền gọi `Mutation.createOrder` hay xem `Order.customerId` không?
- **Schema validation:** Operation có đúng kiểu/field/argument không?
- **Business validation:** quantity hợp lệ, order có thể tạo, tenant sở hữu resource không?

**API key không phải chứng thực danh tính người dùng đáng tin cậy cho dữ liệu nhạy cảm.** API key có thể được dùng trong lab/public use cases phù hợp, nhưng production cần chọn authn/authz mode đúng và bảo vệ API key/thời gian sống.

### Query complexity và abuse protection

GraphQL client có thể gửi nhiều nested fields, aliases, query fragments và yêu cầu resolver tốn kém. Ngoài schema validation, nên:

- Cấu hình **query depth limit** và **resolver count limit** theo tính năng AppSync;
- xác thực và phân quyền từng loại operation/field;
- dùng pagination và giới hạn kích thước danh sách;
- tối ưu DynamoDB/RDS queries, tránh N+1 backend calls;
- logging/metrics và WAF theo kiến trúc hỗ trợ.

**Một query hợp schema vẫn có thể gây tải quá mức** nếu không giới hạn resource cost.

## 22. CORS và GraphQL Subscriptions qua WebSocket

GraphQL subscriptions dùng cơ chế **WebSocket/real-time endpoint** và authorization handshake khác HTTP POST thông thường. Với AppSync:

- Không coi **CORS preflight của fetch** là toàn bộ chính sách WebSocket.
- Khi đặt **CloudFront/custom domain/proxy** trước AppSync, phải tính đúng origin/host headers, connection upgrade, WebSocket handshake và cơ chế auth tương ứng.
- Browser có thể có cách áp dụng Origin headers khác đối với WebSockets; server/proxy vẫn cần kiểm soát nguồn truy cập và authentication.
- Việc mutation/query hoạt động không chứng minh **subscriptions** hoạt động; phải test kết nối, reconnect, token expiry và error handling riêng.

**Security takeaway:** CORS response headers không thay cơ chế authentication/authorization của WebSocket subscription.

## 23. Bài thực hành REST API: validate body và xem error

> **Điều kiện lab:** Một REST API có `POST /orders` và Lambda/HTTP integration đơn giản; IAM role đã được cấp quyền tương ứng. Thực hành cần giới hạn chi phí/log retention và không dùng dữ liệu thật. Tất cả ID/URL dưới đây phải thay bằng tài nguyên của lab.

### Bước 1 — Bật validator

Tạo model ở mục 5, tạo request validator, gắn vào `POST /orders`, deploy stage `lab`.

### Bước 2 — Request hợp lệ

~~~bash
curl -i -X POST \
  "https://a1b2c3d4e5.execute-api.ap-southeast-1.amazonaws.com/lab/orders" \
  -H "Content-Type: application/json" \
  -d '{"customerId":"C-100","sku":"SKU-1","quantity":2}'
~~~

Dự kiến method tới backend nếu authentication và integration hợp lệ. Nếu method có authorizer, cần cung cấp token/lab identity trước; **401 do auth không chứng minh validator đã hoạt động**.

### Bước 3 — Request thiếu required field

~~~bash
curl -i -X POST \
  "https://a1b2c3d4e5.execute-api.ap-southeast-1.amazonaws.com/lab/orders" \
  -H "Content-Type: application/json" \
  -d '{"customerId":"C-100","quantity":2}'
~~~

Quan sát **HTTP 400** ở gateway khi model validator đã được cấu hình và request đi qua auth phù hợp. So sánh CloudWatch Logs/Integration Requests để xác nhận **Lambda không được invoke** vì lỗi schema.

### Bước 4 — Request đúng cú pháp nhưng sai nghiệp vụ

~~~bash
curl -i -X POST \
  "https://a1b2c3d4e5.execute-api.ap-southeast-1.amazonaws.com/lab/orders" \
  -H "Content-Type: application/json" \
  -d '{"customerId":"C-100","sku":"SKU-1","quantity":1000}'
~~~

Nếu JSON Schema chỉ yêu cầu quantity ≥ 1, request có thể **qua validator**. Backend cần từ chối theo giới hạn nghiệp vụ, ví dụ `quantity <= 20`. Quan sát khác biệt status/body/request ID và tầng chịu trách nhiệm.

### Bước 5 — Kiểm tra response lỗi có CORS

Gửi lại request sai với `Origin`:

~~~bash
curl -i -X POST \
  "https://a1b2c3d4e5.execute-api.ap-southeast-1.amazonaws.com/lab/orders" \
  -H "Origin: https://shop.example.com" \
  -H "Content-Type: application/json" \
  -d '{"sku":"SKU-1"}'
~~~

Nếu gateway trả 400 nhưng thiếu `Access-Control-Allow-Origin`, cấu hình **REST Gateway Responses** phù hợp. Nếu backend trả 400 nhưng thiếu header này, sửa backend/integration response theo loại integration.

## 24. Bài thực hành CORS với OPTIONS, curl và DevTools

### 24.1. Gửi preflight thủ công

~~~bash
curl -i -X OPTIONS \
  "https://api.example.com/orders" \
  -H "Origin: https://shop.example.com" \
  -H "Access-Control-Request-Method: POST" \
  -H "Access-Control-Request-Headers: content-type,authorization"
~~~

Đối chiếu response:

- HTTP status preflight thành công theo cấu hình;
- `Access-Control-Allow-Origin` khớp origin;
- `Access-Control-Allow-Methods` có `POST`;
- `Access-Control-Allow-Headers` cho phép `content-type,authorization`;
- `Access-Control-Allow-Credentials` nếu frontend dùng credentials và không có wildcard bất hợp lệ.

**`curl` không thực thi chính sách CORS như browser.** Nó chỉ cho biết HTTP response; để chứng minh browser chấp nhận response, mở DevTools và thử `fetch` thật.

### 24.2. Thử origin không cho phép

~~~bash
curl -i -X OPTIONS \
  "https://api.example.com/orders" \
  -H "Origin: https://evil.invalid" \
  -H "Access-Control-Request-Method: POST" \
  -H "Access-Control-Request-Headers: content-type"
~~~

Không nên nhận CORS allowance cho origin này nếu API chỉ chấp nhận `https://shop.example.com`.

### 24.3. Thử actual 401/400/500

Trong browser DevTools Network:

1. Xem preflight `OPTIONS` có thành công không.
2. Nếu có, xem actual `POST` response status và CORS headers.
3. Thử token thiếu/hết hạn để có **401/403**; lỗi dữ liệu để có **400**; mock backend lỗi để có **500** trên lab.
4. Xác nhận client **đọc được body lỗi** ở origin được phép, không chỉ response 2xx.
5. Xem `Vary: Origin` và behavior CloudFront khi nhiều origins.

**Một `curl -i` trả 200 không phải test CORS đã pass** nếu bạn chưa gửi `Origin` và chưa kiểm tra actual response trong browser.

## 25. Bài thực hành AppSync: GraphQL validation và resolver error

> **Điều kiện lab:** AppSync GraphQL API có schema của mục 9, và `createOrder` dùng NONE data source với APPSYNC_JS resolver của mục 10. Chỉ dùng API key nếu lab đã cho phép public-like testing; với ứng dụng thật ưu tiên IAM/Cognito/OIDC phù hợp.

### 25.1. Query/mutation hợp lệ

~~~graphql
mutation CreateOrder {
  createOrder(input: {
    customerId: "C-100"
    sku: "SKU-1"
    quantity: 2
  }) {
    id
    status
    quantity
  }
}
~~~

Dự kiến data tương ứng payload của NONE data source. **Không có đơn hàng thật trong database** vì resolver ở bài chỉ trả object mô phỏng.

### 25.2. Thiếu field non-null

~~~graphql
mutation InvalidOrder {
  createOrder(input: {
    customerId: "C-100"
    quantity: 2
  }) {
    id
  }
}
~~~

Do thiếu `sku: String!`, GraphQL engine từ chối ở tầng **schema validation**, chưa chạy resolver.

### 25.3. Sai business range

~~~graphql
mutation InvalidBusinessRule {
  createOrder(input: {
    customerId: "C-100"
    sku: "SKU-1"
    quantity: -3
  }) {
    id
    quantity
  }
}
~~~

`-3` vẫn là **Int** và có thể hợp schema, nhưng `util.error` trong resolver từ chối **business rule**.

### 25.4. Gọi HTTPS endpoint bằng curl

Với AppSync API key lab và endpoint thật:

~~~bash
curl -i -X POST \
  "https://example.appsync-api.ap-southeast-1.amazonaws.com/graphql" \
  -H "Content-Type: application/json" \
  -H "x-api-key: <appsync-lab-api-key>" \
  --data '{"query":"mutation { createOrder(input:{customerId:\"C-100\",sku:\"SKU-1\",quantity:2}) { id status } }"}'
~~~

Đây là ví dụ **API_KEY auth mode**, phải thay endpoint và token thật; không commit key vào repository. Với Cognito/JWT hoặc IAM SigV4, header/auth mechanism khác. So **HTTP status + JSON `data` + `errors`**, kiểm tra GraphQL errors không bị bỏ qua chỉ vì HTTP response thành công.

## 26. Observability: tìm đúng lỗi trước khi sửa

### API Gateway

Theo dõi:

- `4XXError`, `5XXError` theo API/stage;
- **Latency** và **IntegrationLatency** để tách overhead gateway và backend;
- số requests, throttling và cache metrics khi có tính năng tương ứng;
- **access logs** có request ID, route/method, status, integration status và latency;
- **REST execution logs** khi đã bật phù hợp, tránh ghi payload nhạy cảm.

**Không tự động bật full request/response data tracing trên production** nếu có khả năng log token, PII hoặc secret. Tối ưu logging theo chính sách bảo mật và chi phí.

### AppSync

Theo dõi:

- request/latency/error metrics được AppSync phát ra theo cấu hình;
- resolver errors, field-level logs khi bật mức độ phù hợp;
- DynamoDB throttling/conditional check, Lambda errors, RDS/data source latency;
- schema changes, query depth/complexity violations và auth failures;
- tracing/X-Ray khi tích hợp hỗ trợ.

### Lambda/backend

Theo dõi:

- **Invocations, Errors, Duration, Throttles**;
- logs/structured error và correlation ID;
- DB connection pool, transaction failures, `ConditionalCheckFailed`, rate limits và retries;
- cost/cuộc gọi downstream và hiệu quả cache.

### Correlation ID xuyên nhiều lớp

~~~mermaid
flowchart LR
    Client[Client request] --> Gateway[Gateway request ID]
    Gateway --> Handler[Lambda trace/correlation ID]
    Handler --> DB[Database operation ID]
    Handler --> Q[SQS event correlation ID]
    Gateway --> Logs[Centralized logs/metrics]
    Handler --> Logs
~~~

Ví dụ một log entry an toàn:

~~~json
{
  "service": "orders-api",
  "requestId": "req-lab-7ac21",
  "operation": "createOrder",
  "result": "VALIDATION_FAILED",
  "errorCode": "INVALID_QUANTITY",
  "latencyMs": 18
}
~~~

Đừng log bearer token, cookie, password, raw payment card, toàn bộ GraphQL variables chứa PII, SQL query có bí mật, KMS plaintext key hoặc backend stack trace không cần thiết.

## 27. Troubleshooting: bản đồ triệu chứng → nguyên nhân

| Triệu chứng | Khả năng cao | Cách kiểm tra |
| --- | --- | --- |
| Browser báo CORS, `curl` vẫn trả body | `OPTIONS`/actual response thiếu hoặc sai CORS headers | DevTools, `curl` có Origin, response của 2xx và 4xx |
| Preflight trả 401 | Authorizer áp dụng lên `OPTIONS`, `$default` route bắt request | Miễn auth đúng OPTIONS route, vẫn giữ auth actual methods |
| Preflight 204 nhưng POST vẫn CORS blocked | Actual POST response thiếu `Access-Control-Allow-Origin` | Kiểm tra backend proxy/Gateway Responses/CDN |
| `Access-Control-Allow-Origin: *` với credentials | Wildcard không hợp lệ cho credentialed request | Match exact origin, Allow-Credentials, cookies/SameSite |
| Origin A được phép, origin B nhận sai header | CDN/cache không phân biệt Origin, thiếu Vary | Cache key/policy, `Vary: Origin`, edge layer |
| REST validator không chạy | Chưa gắn method validator/model, Content-Type khác, chưa deploy stage | Method Request, Model content type, deployment/stage |
| REST trả 400 trước Lambda | Required params/body không hợp model | Gateway execution logs, request validator settings |
| HTTP API không có tùy chọn validator REST | API type khác | Validate tại Lambda/backend; không tìm REST Model |
| API Gateway REST trả `Missing Authentication Token` | Sai route/method/stage hoặc authentication issue | URL, base path mapping, method/route, authorizer |
| HTTP API báo 404/403 qua `$default` | Route/authorizer/default priority | Routes, JWT config, OPTIONS precedence |
| Lambda proxy trả 502 | Handler crash hoặc response format sai, body không phải string | Lambda logs, proxy integration event/response contract |
| API Gateway 504 | Integration timeout/downstream chậm | IntegrationLatency, Lambda/DB/network logs, timeout |
| Backend 400 không có CORS | App chỉ set headers ở successful response | Error middleware/response mapping ở 4xx/5xx |
| AppSync field trả null và errors | Resolver/data source/GraphQL non-null propagation | GraphQL errors path/errorType, resolver logs |
| AppSync query sai field bị từ chối | Schema parsing/validation | Query + variables vs schema, console schema |
| GraphQL 200 nhưng client coi là thành công | Client chỉ kiểm tra HTTP code, bỏ qua `errors` | Parse envelope data/errors, test partial data |
| AppSync `MappingTemplate` lỗi | VTL/JS request/response mapping sai | Resolver runtime, code, evaluate/test, logs |
| AppSync bị Unauthorized | Auth mode/API key/JWT/IAM/field directive không khớp | Headers, token claims, IAM action, schema auth directives |
| Tăng timeout/5xx khi load | Backend DB locks, throttling, Lambda concurrency, query quá sâu | Logs/traces, DB metrics, AppSync limits, retries |
| Lambda retry tạo đơn trùng | Thiếu idempotency, client retry request `POST` | Idempotency key, conditional write/transaction và logs |

### Quy trình điều tra 9 bước

~~~text
1. Xác định loại API: Gateway REST / HTTP / AppSync GraphQL.
2. Xác định client: browser hay curl/server; URL, method, origin, auth mode.
3. Với browser: nhìn OPTIONS và actual request riêng trong DevTools.
4. Kiểm tra HTTP status, CORS headers, request ID và response body.
5. Với REST: kiểm tra Model/Validator, method/stage, Gateway Responses.
6. Với HTTP API: kiểm tra Routes/$default, authorizer, CORS config.
7. Với AppSync: kiểm tra schema/variables/auth, data/errors/path/errorType.
8. Xem backend/resolver logs, data source và network/IAM/KMS khi cần.
9. Sửa một nguyên nhân, thử lại happy path + negative tests, theo dõi metrics.
~~~

**Không sửa lỗi bằng cách** mở mọi origin kèm credentials, tắt authorizer cho toàn API, cấp `AdministratorAccess`, tăng timeout vô hạn hoặc trả HTTP 200 cho mọi lỗi nghiệp vụ.

## 28. Bảo mật API: validation và CORS không thể đứng riêng

Một API trên AWS cần nhiều lớp bảo vệ:

1. **IAM/Cognito/OIDC/Lambda authorizers:** xác minh caller theo loại API, phân quyền method/field/resource.
2. **Backend authorization:** đảm bảo tenant/user không truy cập dữ liệu của người khác, ngay cả khi schema hợp lệ.
3. **Input validation:** type/range/required fields, normalize/encode, kiểm soát payload size, query depth và batch size.
4. **CORS allowlist:** origin cụ thể cho frontend, không phản chiếu origin tùy ý, cẩn thận với cookies.
5. **Throttling/WAF:** giới hạn tần suất, bảo vệ API khỏi abuse và tăng chi phí bất thường.
6. **TLS:** HTTPS ở endpoint, chứng chỉ custom domain/ACM; backend/private link/VPC theo yêu cầu.
7. **IAM/KMS/data:** Lambda execution role least privilege, Secrets Manager, S3 SSE-KMS, DynamoDB/RDS authorization và audit.
8. **Logging/trace:** request ID, status, error code không chứa secret/PII; retention phù hợp.
9. **Recovery:** retry/backoff/idempotency, DLQ/queue khi xử lý async, backup và Multi-AZ dữ liệu.
10. **CI/CD:** IaC cho request models/validators/CORS/gateway responses/AppSync schema và resolvers, test trước production.

### Ví dụ tenant isolation

Một client GraphQL gửi:

~~~graphql
query {
  getOrder(id: "ORDER-OF-OTHER-TENANT") {
    id
    customerId
  }
}
~~~

Query này **hợp schema**, nhưng resolver/backend phải so tenant/user identity với owner của order. Nếu không kiểm tra, CORS đúng, JWT hợp lệ và schema validation pass cũng **không ngăn truy cập trái phép (BOLA/IDOR)**.

**Không chỉ dựa vào frontend** ẩn nút hoặc gửi `tenantId` do client tự khai; backend phải lấy subject/tenant từ claims xác thực và kiểm tra quyền với resource thật.

## 29. Reliability, availability và kiểm soát chi phí

### Kiến trúc minh họa bán hàng qua REST và GraphQL

~~~mermaid
flowchart TB
    Web[Frontend HTTPS / CloudFront] --> Rest[API Gateway /orders]
    Web --> Gql[AppSync GraphQL]
    Rest --> Validation[REST validator / backend validation]
    Validation --> Lambda[Lambda Orders API]
    Gql --> Resolver[AppSync schema + resolvers]
    Resolver --> DDB[(DynamoDB)]
    Lambda --> DDB
    Lambda --> Queue[(SQS: OrderCreated)]
    Queue --> Worker[Lambda invoice worker]
    Worker --> S3[(S3 hóa đơn / SSE-KMS)]
    Rest --> CW[CloudWatch / alarms]
    Gql --> CW
    Lambda --> CW
    Resolver --> CW
~~~

**Các điểm cần thiết kế:**

- REST hoặc GraphQL có **validation contract** riêng; auth và business rules phải được giữ nhất quán nếu cùng phục vụ một dữ liệu.
- **Throttling**, API limits và AppSync query depth bảo vệ backend khỏi traffic không hợp lý; một lỗi resolver không tự làm toàn bộ hệ thống HA.
- Lambda scale nhưng **RDS/DB/SQS/KMS có quota và chi phí**; cần backpressure/retry/idempotency.
- DynamoDB có đặc tính dịch vụ/Region riêng; S3 backup/versioning, dữ liệu RDS Multi-AZ hoặc replication cần thiết kế theo RTO/RPO.
- Nếu frontend nhiều Region/origin, CORS allowlist, custom domains, DNS và disaster recovery cần được xem theo môi trường thật.
- CloudWatch logs/traces giúp nối request lỗi từ client đến gateway/resolver/data.
- AWS Budgets/Cost Explorer/CloudWatch alarms phát hiện request burst, lỗi retry loop và logging tăng chi phí.

### Những khoản chi phí cần ước lượng

| Khoản | Khi nào tăng |
| --- | --- |
| **API Gateway API requests** | Số request, loại API, cache/data transfer theo tính năng |
| **AppSync operations và real-time** | GraphQL query/mutation/subscription, connection/messages theo biểu giá |
| **Lambda** | Invocations, memory-duration, provisioned concurrency, logs |
| **DynamoDB/RDS** | Reads/writes, throughput/capacity, connections và storage |
| **CloudWatch/X-Ray** | Access/execution logs, field logs, metrics/traces |
| **WAF/CloudFront** | Rules/requests, caching, internet data transfer |
| **KMS/S3/SQS** | Data/API calls, encryption key requests, retries/DLQ |

**Validation hợp lý có thể giảm invocations backend không cần thiết**, nhưng gateway/resolver requests và logs vẫn có chi phí. Không bật field-level verbose logging dài hạn trên toàn production chỉ để chẩn đoán một lỗi nhỏ. Dùng sampling, masking và retention có kiểm soát.

## 30. Bài tập áp dụng

### Bài tập 1 — REST validator không chặn request

**Đề bài:** REST API có `POST /orders`, Model `CreateOrderRequest` cho `application/json`. Client gửi `Content-Type: text/plain` với JSON thiếu `sku`; request vẫn tới Lambda.

**Yêu cầu:** Giải thích vì sao body validator có thể bỏ qua; đề xuất `$default` model, content-type enforcement và test cases; phân biệt với lỗi parser trong backend. Xác minh stage đã redeploy.

### Bài tập 2 — CORS giả che mất 401

Frontend `https://shop.example.com` gọi API với Bearer token hết hạn. Browser báo CORS blocked, trong CloudWatch API Gateway có 401.

Hãy kiểm tra preflight `OPTIONS`, actual response `401`, authorizer và Gateway Responses/HTTP API CORS configuration. Mục tiêu là **trả 401 với CORS headers đúng** chứ không bỏ auth.

### Bài tập 3 — `$default` route chặn OPTIONS

HTTP API dùng JWT authorizer trên `$default` route. Browser POST JSON từ origin hợp lệ nhưng preflight OPTIONS bị 401.

**Yêu cầu:** Giải thích route matching, tạo `OPTIONS /{proxy+}` không yêu cầu auth theo tài liệu, kiểm chứng actual POST vẫn đòi JWT.

### Bài tập 4 — GraphQL schema pass nhưng sai nghiệp vụ

Mutation gửi `quantity: -10` cho input `Int!`. GraphQL chấp nhận kiểu, resolver tạo dữ liệu âm.

**Yêu cầu:** Thêm validation `quantity >= 1`, phân biệt với schema validation, dùng `util.error` và test `data/errors`. Nếu hai API REST/GraphQL cùng tạo đơn, đề xuất chia sẻ domain invariant ở tầng service/transaction.

### Bài tập 5 — GraphQL HTTP 200 có errors

Một GraphQL query lấy `getOrder` và `listProducts`. `getOrder` lỗi, `listProducts` thành công, HTTP status trả 200.

**Yêu cầu:** Viết một response có `data` partial và `errors.path`, cập nhật client để không coi `response.ok` là “mọi field thành công”, giải thích null bubbling khi schema đặt `Order!`.

### Bài tập 6 — CORS và cookies

Frontend dùng `credentials: 'include'`, server trả `Access-Control-Allow-Origin: *` và `Access-Control-Allow-Credentials: true`.

**Yêu cầu:** Tìm lỗi theo Fetch/CORS, sửa exact origin + credentials + Vary, đánh giá CSRF/SameSite/HttpOnly/Secure và không phản chiếu origin tùy ý.

### Bài tập 7 — Lambda proxy trả 502

Lambda Java trong HTTP API trả `body` là một Map thay vì JSON string với cấu trúc proxy response tùy handler/version; production bắt đầu có lỗi 502.

**Yêu cầu:** Kiểm tra payload format `1.0/2.0`, raw Lambda result, CloudWatch logs, response shape/status/headers, test một phản hồi `400` và một `201` có CORS.

### Bài tập 8 — Chi phí và abuse

AppSync được gọi bằng GraphQL query sâu, mỗi resolver đọc nhiều items DynamoDB. Gateway/DB request volume tăng nhanh.

**Yêu cầu:** Đề xuất query depth/resolver count limits, pagination, auth, WAF, metrics, caching phù hợp, budgets và load testing; giải thích vì sao “query hợp schema” không đồng nghĩa “chi phí an toàn”.

## 31. Checklist trước khi triển khai production

- [ ] Đã xác định đúng **REST API, HTTP API hay AppSync GraphQL** và tính năng thực sự có ở loại đó.
- [ ] Có contract request/response và chính sách validation rõ: schema, required, type, range, business invariant.
- [ ] REST API có Model và request validator gắn đúng method/content type; đã redeploy stage và kiểm thử.
- [ ] HTTP API validate dữ liệu tại backend, không giả định có REST Request Validator.
- [ ] AppSync schema kiểm tra query/variables, resolver/pipeline kiểm tra business rule/authorization.
- [ ] Không trộn CORS với authentication/authorization; có kiểm tra resource/tenant ở backend.
- [ ] Allowed origins là danh sách được phê duyệt; không dùng wildcard với credentialed CORS.
- [ ] Preflight OPTIONS hoạt động không có auth không cần thiết; actual request vẫn bắt buộc auth khi phù hợp.
- [ ] CORS headers hiện diện trên **2xx và 4xx/5xx** theo loại API/integration, được browser chấp nhận.
- [ ] Với REST proxy, backend trả headers; với HTTP API CORS bật, gateway quản lý headers; AppSync không tự sửa CORS trong resolver.
- [ ] Với nhiều origins/cache, có `Vary: Origin` và CloudFront cache policy hợp lý.
- [ ] Error contract có HTTP status/GraphQL errors, code/message/request ID; không lộ stack trace/PII.
- [ ] Client GraphQL đọc `errors` ngay cả khi HTTP 200; xử lý partial data và non-null behavior.
- [ ] Lambda proxy response body là JSON string theo contract; integration mapping đã test.
- [ ] Có 401/403/404/409/429/500/502/504 tests và quy tắc retry/backoff/idempotency.
- [ ] AppSync có auth modes/field policies, query depth/resolver limits và data source permissions đúng.
- [ ] CloudWatch access/field logs, metrics/traces và alarms được cấu hình, dữ liệu nhạy cảm được mask.
- [ ] VPC, IAM, KMS, RDS/S3/DynamoDB và quota được đánh giá cùng với API; không chỉ sửa gateway.
- [ ] Có IaC, code review, deployment version/rollback, negative tests trong CI/CD.
- [ ] Có ngân sách giám sát API requests, resolver/DB calls, Lambda, CloudWatch và WAF/CloudFront.

## 32. Tổng kết

**Validation**, **CORS** và **xử lý lỗi** là ba trách nhiệm khác nhau nhưng liên quan trực tiếp đến trải nghiệm và bảo mật API:

- **Validation**: API Gateway REST có thể chặn body/required params qua **Model và Request Validator**; HTTP API thường để backend đảm nhiệm; AppSync dùng **GraphQL schema** và **resolver/pipeline** cho các kiểm tra phù hợp.
- **CORS**: browser kiểm tra origin/preflight/response headers; **REST proxy**, **HTTP API CORS configuration** và **AppSync GraphQL** có cách xử lý riêng. CORS **không cấp quyền và không ngăn non-browser clients**.
- **Xử lý lỗi**: HTTP API cần status/contract rõ ràng; **REST Gateway Responses** quản lý một số lỗi gateway; **GraphQL AppSync** có `data` và `errors`, đôi khi HTTP 200 vẫn có field errors.

Một API đáng tin cậy cần **từ chối dữ liệu sai càng sớm càng hợp lý, kiểm tra quyền ở backend, trả lỗi nhất quán trên cả luồng thành công và thất bại, có khả năng chẩn đoán bằng request ID/logs/traces và bảo vệ dữ liệu/chi phí**. Khi kết hợp AWS Lambda, IAM, VPC, RDS/DynamoDB/S3, CloudWatch và AWS Budgets, các nguyên tắc này giúp ứng dụng **an toàn, quan sát được và phục hồi được**.

### Tài liệu tham khảo chính thức

- [AWS API Gateway REST API request validation](https://docs.aws.amazon.com/apigateway/latest/developerguide/api-gateway-method-request-validation.html)
- [Set up request validation for REST API](https://docs.aws.amazon.com/apigateway/latest/developerguide/api-gateway-request-validation-set-up.html)
- [CORS for API Gateway REST APIs](https://docs.aws.amazon.com/apigateway/latest/developerguide/how-to-cors.html)
- [CORS for API Gateway HTTP APIs](https://docs.aws.amazon.com/apigateway/latest/developerguide/http-api-cors.html)
- [API Gateway REST Gateway Responses](https://docs.aws.amazon.com/apigateway/latest/developerguide/api-gateway-gatewayResponse-definition.html)
- [API Gateway Gateway Response Types](https://docs.aws.amazon.com/apigateway/latest/developerguide/supported-gateway-response-types.html)
- [AWS Lambda proxy integration](https://docs.aws.amazon.com/apigateway/latest/developerguide/set-up-lambda-proxy-integrations.html)
- [AWS AppSync GraphQL schema design](https://docs.aws.amazon.com/appsync/latest/devguide/designing-your-schema.html)
- [AWS AppSync resolvers](https://docs.aws.amazon.com/appsync/latest/devguide/resolver-components.html)
- [AWS AppSync JavaScript resolver runtime](https://docs.aws.amazon.com/appsync/latest/devguide/resolver-reference-overview-js.html)
- [AppSync NONE data source JavaScript resolver](https://docs.aws.amazon.com/appsync/latest/devguide/resolver-reference-none-js.html)
- [AppSync util.error/util.appendError](https://docs.aws.amazon.com/appsync/latest/devguide/built-in-util-js.html)
- [AppSync troubleshooting](https://docs.aws.amazon.com/appsync/latest/devguide/troubleshooting-and-common-mistakes.html)
- [AppSync authorization and authentication](https://docs.aws.amazon.com/appsync/latest/devguide/security-authz.html)
- [AppSync query depth and resolver count limits](https://docs.aws.amazon.com/appsync/latest/devguide/configuration-limits.html)
- [AppSync custom response header limits](https://docs.aws.amazon.com/appsync/latest/devguide/http-helpers-in-utils-http-js.html)
- [Amazon CloudFront CORS response headers policies](https://docs.aws.amazon.com/AmazonCloudFront/latest/DeveloperGuide/understanding-response-headers-policies.html)
- [RFC 9457 Problem Details for HTTP APIs](https://www.rfc-editor.org/rfc/rfc9457.html)
- [AWS API Gateway pricing](https://aws.amazon.com/api-gateway/pricing/) và [AWS AppSync pricing](https://aws.amazon.com/appsync/pricing/)

**Lưu ý khi áp dụng:** Tính năng, giới hạn, lỗi do dịch vụ tạo, pricing và Console/API behavior có thể thay đổi theo loại API, Region và thời điểm. Luôn kiểm tra tài liệu mới nhất và kiểm thử tại **stage/account thực** trước khi triển khai production.
