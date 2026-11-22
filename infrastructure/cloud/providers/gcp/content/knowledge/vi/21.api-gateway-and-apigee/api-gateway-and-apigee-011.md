# Versioning, deprecation và quản trị danh mục API trên Google Cloud

> **Chương:** API Gateway và Apigee  
> **Mô-đun:** **CLOUD_PROVIDERS_GCP** — Khám phá Google Cloud từ tổ chức project, IAM và VPC đến Compute Engine, GKE, Cloud Run, dịch vụ lưu trữ và cơ sở dữ liệu. Qua các tình huống triển khai, người học biết lựa chọn dịch vụ, bảo vệ tài nguyên, tự động hóa phát hành và theo dõi độ tin cậy cùng chi phí.

Một API đã được nhiều ứng dụng sử dụng là **hợp đồng tích hợp** chứ không chỉ là một URL. Đổi tên trường JSON, loại bỏ một endpoint hoặc thay cách xác thực có thể khiến ứng dụng di động, đối tác và batch job cùng lỗi. Ngược lại, giữ mọi phiên bản cũ mãi mãi làm tăng chi phí bảo trì, lỗ hổng và độ phức tạp vận hành.

Bài học xây dựng quy trình quản trị vòng đời **thiết kế → phát hành → thay thế → thông báo ngừng hỗ trợ (deprecation) → ngừng phục vụ (sunset/retirement)** bằng các công cụ phù hợp: **API Gateway** quản lý API configs/gateways, **Apigee** quản lý API proxies/API products và **Apigee API hub** làm danh mục API. Ví dụ xuyên suốt là **Orders API** chuyển từ **/v1/orders** sang **/v2/orders**. Các mốc thời gian chỉ minh họa chính sách, không phải thời hạn mặc định của Google Cloud.

## Mục tiêu học tập

Sau bài, người học có thể:

1. Phân biệt **public API version**, **OpenAPI info.version**, **API Gateway API config**, **Apigee proxy revision**, **Apigee API product** và **API hub version**.
2. Phân loại thay đổi backward-compatible/breaking và chọn chính sách versioning thích hợp.
3. Mô tả **deprecation** khác **sunset**, thực hiện thông báo theo **RFC 9745** và **RFC 8594**.
4. Xây dựng OpenAPI contract cho v1/v2, migration guide và bộ kiểm thử contract.
5. Thiết kế rollout/rollback trên API Gateway hoặc Apigee mà không nhầm revision cấu hình với version bên ngoài.
6. Lập danh mục API có owner, consumer, dependency, deployment, SLA/SLO, security, lifecycle và ngày ngừng phục vụ.
7. Đo lượng người dùng còn gọi v1, đặt tiêu chí loại bỏ, phối hợp Security/SRE/FinOps và kiểm soát thay đổi.
8. Hoàn thành lab tài liệu, thao tác CLI chỉ đọc và bài tập tình huống.

## 1. Bốn tầng “phiên bản” không được nhầm lẫn

| Khái niệm | Ví dụ | Ai nhìn thấy? | Ý nghĩa |
|---|---|---|---|
| **Public API version** | **GET /v1/orders/{id}**, **/v2/orders/{id}** | Consumer | Hợp đồng request/response và behavior |
| **Specification version** | **OpenAPI info.version: 1.7.2** | Developer/CI/catalog | Phiên bản tài liệu contract; không tự đổi URL |
| **API Gateway API config** | **orders-config-20270301** | Platform operator | Snapshot cấu hình gateway khi upload API definition |
| **Apigee API proxy revision** | Proxy **orders**, revision **17** | Apigee operator | Số revision kỹ thuật của proxy bundle, không phải public version |
| **API hub API version** | Orders API → **v1**, **v2** | API catalog users | Đối tượng metadata liên kết spec, operations, deployments, lifecycle |
| **Apigee API product** | **orders-read-v1**, **orders-read-v2** | App/developer portal | Gói operation/path/method/quota/access dành cho client |
| **Backend release** | checkout-service image digest | SRE/CI | Bản code chạy ở Cloud Run/GKE/VM, không tự là public API version |

**Điểm mấu chốt:** đổi từ Apigee proxy revision **16** sang **17** không tự biến **/v1** thành **/v2**. Tương tự, tạo **orders-config-20270301** trong API Gateway không tự thay đổi URL public nếu spec và gateway route vẫn giữ như cũ. Public version thuộc về **hợp đồng mà client phụ thuộc**.

~~~mermaid
flowchart LR
    C["Clients: mobile, partner, batch"] --> V1["Public /v1/orders"]
    C --> V2["Public /v2/orders"]
    V1 --> G["API Gateway / Apigee"]
    V2 --> G
    G --> B["Cloud Run / GKE backend"]
    SPECS["OpenAPI v1, v2"] -. "Tài liệu contract" .-> G
    HUB["API hub catalog\nversion, owner, lifecycle"] -. "Mô tả" .-> SPECS
    CICD["CI/CD config/proxy revisions"] -. "Deploy" .-> G
~~~

### 1.1. Vai trò của ba sản phẩm Google Cloud

- **API Gateway:** giải pháp quản lý API gateway theo **OpenAPI/gRPC definitions**, có configs bất biến, gateway triển khai trong region và tính năng auth, quotas, monitoring theo khả năng hỗ trợ. Thích hợp đường quản lý tương đối gọn.
- **Apigee:** nền tảng API management với **API proxy**, policies, environments, API products, developer apps, analytics và khả năng quản trị người tiêu thụ/API ở mức sản phẩm.
- **Apigee API hub:** **danh mục và lớp governance** để đăng ký APIs từ nhiều nguồn, quản lý API versions/specs/deployments/dependencies/lifecycle và tìm kiếm. **API hub không tự cắt traffic, không tự enforce Sunset, không thay thế runtime gateway.**

Có thể dùng API hub để theo dõi APIs được expose qua API Gateway, Apigee hoặc nền tảng khác. Nếu đã kết nối API Gateway với API hub bằng integration được hỗ trợ, metadata API có thể được đồng bộ; vẫn cần kiểm tra **owner, chính sách vòng đời và độ mới dữ liệu**.

## 2. Chọn chiến lược versioning theo thay đổi hợp đồng

Một versioning policy phải nói được: **điều gì là breaking**, tên version được biểu diễn ở đâu, và client có bao lâu để migrate.

### 2.1. Phân loại tương thích

| Thay đổi | Thường tương thích? | Điều cần kiểm chứng |
|---|---|---|
| Thêm endpoint mới độc lập | Có | Không gây xung đột routing/security |
| Thêm **optional** response field | Thường có | Client không fail khi gặp unknown fields; schema chính xác |
| Thêm **optional** request field | Thường có | Default behavior không thay đổi |
| Thêm enum value | **Có thể breaking** | Client dùng exhaustive switch/deserialization nghiêm ngặt |
| Thay tên/xóa field JSON | **Breaking** | Client đang đọc/ghi field cũ |
| Đổi type **string → number** | **Breaking** | JSON schema và generated SDK |
| Đổi optional parameter thành required | **Breaking** | Request cũ không còn hợp lệ |
| Thay đơn vị tiền **VND → minor units** | **Breaking** nếu không đổi field/schema | Ý nghĩa dữ liệu thay đổi |
| Đổi status code/error shape | **Có thể breaking** | Retry/client error mapping |
| Chặn quyền trước đây được phép | Có thể breaking nhưng cần vì security | Migration/exception và risk review |
| Thu hẹp rate limit/quota | **Có thể breaking** | Consumer throughput và hợp đồng SLA |
| Đổi backend mà giữ output/semantics | Thường không | Performance, consistency, idempotency |

**Không suy “thêm trường luôn an toàn”.** Client Java generate từ một schema, client mobile có enum strict hoặc hệ thống chữ ký canonical JSON có thể hỏng ngay cả khi nhà cung cấp nghĩ đó là additive.

### 2.2. Cách mang version ra public contract

| Cách | Ví dụ | Ưu điểm | Điểm đánh đổi |
|---|---|---|---|
| URL path | **/v1/orders/{id}** | Dễ nhận diện, cache/log/gateway route rõ | URL của từng version khác nhau |
| Host | **v2.api.example.com** | Tách deployment/traffic rõ | DNS/cert và vận hành phức tạp hơn |
| Header | **API-Version: 2** | URL ổn định | Cần cache Vary, client observability, docs đầy đủ |
| Media type | **Accept: application/vnd.example.v2+json** | Gắn version với representation | Tooling/debug phức tạp |
| Query parameter | **?version=2** | Dễ thử | Cache/routing/documentation phải nhất quán |

Bài này chọn **path major version**: **/v1** và **/v2** cùng tồn tại. Dù cách nào, version public cần **nhất quán** ở OpenAPI, SDK, docs, gateway, telemetry và danh mục.

### 2.3. Major/minor/patch là một chính sách, không phải mặc định gateway

Ví dụ quy ước nội bộ:

- **Major** (v1 → v2): thay đổi không tương thích.
- **Minor** (1.7 → 1.8): thêm chức năng tương thích.
- **Patch** (1.8.1 → 1.8.2): sửa lỗi không đổi contract.

Sử dụng **info.version** của OpenAPI để đánh dấu bản spec đã phát hành. Bản thân API Gateway không tự dùng quy tắc SemVer để chặn breaking changes; CI và quy trình review phải kiểm tra.

## 3. Thiết kế Orders API v1 và v2 trước khi đổi runtime

**Hợp đồng giả định:**

- **v1:** GET /v1/orders/{orderId}, response gồm **id**, **totalAmount** (đơn vị VND), **status**.
- **v2:** GET /v2/orders/{orderId}, response gồm **id**, **amount: { value, currency }**, **status**.

Nếu v1 sử dụng **totalAmount** còn v2 thay bằng object **amount**, đó là breaking change. Không đổi trả response v1 sang v2 ngầm vì sẽ làm client cũ hỏng.

### 3.1. OpenAPI 3.0 contract cho v1 (tài liệu, chưa là gateway deploy spec hoàn chỉnh)

~~~yaml
openapi: 3.0.3
info:
  title: Orders API
  version: 1.4.0
  description: Version v1 - deprecated theo chính sách tổ chức
servers:
  - url: https://api.example.com
paths:
  /v1/orders/{orderId}:
    get:
      operationId: getOrderV1
      deprecated: true
      summary: Đọc đơn hàng, v1
      parameters:
        - name: orderId
          in: path
          required: true
          schema:
            type: string
      responses:
        '200':
          description: Thành công
          content:
            application/json:
              schema:
                type: object
                required: [id, totalAmount, status]
                properties:
                  id: {type: string}
                  totalAmount:
                    type: integer
                    format: int64
                    description: Tổng tiền, đơn vị VND
                  status: {type: string}
        '404':
          description: Không tìm thấy đơn hàng
~~~

### 3.2. Contract v2

~~~yaml
openapi: 3.0.3
info:
  title: Orders API
  version: 2.0.0
servers:
  - url: https://api.example.com
paths:
  /v2/orders/{orderId}:
    get:
      operationId: getOrderV2
      summary: Đọc đơn hàng, v2
      parameters:
        - name: orderId
          in: path
          required: true
          schema:
            type: string
      responses:
        '200':
          description: Thành công
          content:
            application/json:
              schema:
                type: object
                required: [id, amount, status]
                properties:
                  id: {type: string}
                  amount:
                    type: object
                    required: [value, currency]
                    properties:
                      value: {type: integer, format: int64}
                      currency: {type: string, example: VND}
                  status: {type: string}
        '404':
          description: Không tìm thấy đơn hàng
~~~

Ví dụ response:

~~~json
{
  "id": "ord-1001",
  "amount": {"value": 150000, "currency": "VND"},
  "status": "PAID"
}
~~~

**Phân biệt:** thuộc tính **deprecated: true** trên OpenAPI operation thể hiện trạng thái tài liệu cho người dùng/tooling; nó **không tự chặn request, không gửi header Sunset và không xóa endpoint**. Cần triển khai headers/policy/tắt routing ở backend/gateway khi đến mốc phù hợp.

**Ghi chú bảo mật:** hai OpenAPI snippets cố ý tập trung vào contract và **chưa có security schemes, backend mapping, authentication, error schema đầy đủ**. Không deploy chúng như API công khai production chỉ vì schema hợp lệ. Ví dụ triển khai API Gateway ở phần sau sẽ yêu cầu spec phù hợp và backend/auth riêng.

### 3.3. Bản đồ chuyển đổi dữ liệu

| v1 | v2 | Cách migrate |
|---|---|---|
| totalAmount: 150000 | amount.value: 150000 | Đổi nơi đọc field |
| Ngầm định VND | amount.currency: "VND" | Xử lý rõ đơn vị |
| /v1/orders/{id} | /v2/orders/{id} | Đổi URL và SDK client |
| getOrderV1 | getOrderV2 | Regenerate SDK hoặc adapter |
| OpenAPI deprecated | OpenAPI active | Update docs, changelog và runbook |

Chuyển đổi v1 → v2 có thể do **backend hỗ trợ song song** hoặc Apigee proxy làm transformation, tùy kiến trúc. Không cố dùng gateway transformation để che mọi khác biệt behavior dài hạn: đó có thể làm tăng độ phức tạp và chi phí latency.

## 4. Deprecation khác sunset như thế nào?

| Trạng thái | Ý nghĩa đối với client | Hành động của provider |
|---|---|---|
| **Design** | Chưa dùng production | Review contract, security, owner |
| **Preview/Beta** | Có thể thay đổi theo điều khoản preview | Gắn nhãn rõ, giới hạn consumers |
| **Active/GA** | Được khuyến nghị dùng, có SLO/support policy | Quản lý versions, monitoring |
| **Deprecated** | Còn hoạt động nhưng **không nên tích hợp mới**; phải chuẩn bị migrate | Thông báo, hỗ trợ v2, đo v1 |
| **Sunset reached** | Ngày dự kiến ngừng phục vụ đã tới | Thực hiện quyết định cutoff có phê duyệt, hướng dẫn lỗi |
| **Retired** | Không còn phục vụ contract v1 | Gỡ route/keys/docs live, lưu hồ sơ kiểm toán |

**Deprecated không phải disabled.** Một endpoint đang deprecated có thể tiếp tục trả HTTP 200 bình thường. **Sunset là mốc thông báo dự kiến ngừng hoạt động**, nhưng bản thân header HTTP không đóng một endpoint; người vận hành phải thực hiện thay đổi routing/proxy/backend và kiểm chứng. **Retired** là trạng thái governance xác nhận dịch vụ v1 đã dừng.

### 4.1. Mốc thời gian minh họa cho Orders API

| Thời điểm (UTC) | Sự kiện | Kỳ vọng |
|---|---|---|
| **01/02/2027** | Công bố v2, migration guide và kế hoạch v1 | Consumer owner xác nhận đã nhận thông báo |
| **01/03/2027** | v1 bước vào **Deprecated** | Responses v1 có Deprecation + Link; mở dashboard |
| **01/06/2027** | Đợt kiểm tra giữa kỳ | Top v1 consumers còn lại có kế hoạch |
| **01/09/2027** | **Sunset dự kiến** | Hội đồng thay đổi quyết định cutoff/extension dựa trên số liệu |
| **Sau cutoff được xác nhận** | Retired | API hub và docs cập nhật; rollback plan đóng |

Các ngày này là **ví dụ chính sách của một tổ chức**, không phải SLA/thời hạn mà API Gateway hay Apigee tự áp dụng. Khoảng thông báo thực tế phải dựa trên hợp đồng với đối tác, vòng đời phiên bản ứng dụng di động, ngành nghề, pháp lý, data retention và mức rủi ro.

### 4.2. HTTP Deprecation, Sunset và Link

**RFC 9745** định nghĩa header **Deprecation** dưới dạng *Structured Field Date*, dùng epoch giây với ký tự **@**. **RFC 8594** định nghĩa **Sunset** theo định dạng **HTTP-date**, khác với Deprecation.

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Deprecation: @1803859200
Sunset: Wed, 01 Sep 2027 00:00:00 GMT
Link: <https://developer.example.com/orders/migrate-v2>; rel="deprecation"; type="text/html"

{"id":"ord-1001","totalAmount":150000,"status":"PAID"}
~~~

- **Deprecation: @1803859200** là **01/03/2027 00:00:00 UTC**.
- **Sunset** là **01/09/2027 00:00:00 UTC** theo HTTP-date.
- **Link** trỏ đến hướng dẫn migration có changelog, ví dụ request/response, SDK và lịch hỗ trợ; URL chỉ minh họa.
- **Sunset không được đặt trước mốc Deprecation** trong thông báo cùng resource; cần thống nhất giữa docs/header/catalog.
- Thêm header **không tự chuyển request sang v2**, không thay đổi response schema và không tự từ chối traffic.

Trước ngày 01/03/2027, provider có thể gửi header Deprecation với ngày trong tương lai để thông báo sớm, miễn là tài liệu thống nhất. Khi một resource cụ thể chỉ ra Deprecation/Sunset, phạm vi mặc định là resource đó; nếu thông báo dành cho toàn bộ **/v1**, hãy công bố rõ phạm vi trong docs và cung cấp header nhất quán ở những operation liên quan.

### 4.3. Ví dụ Java/Spring Boot trả header deprecation

Giả sử ứng dụng Spring Boot đã có service đọc đơn hàng:

~~~java
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;
import java.util.Map;

@RestController
public class OrdersV1Controller {

    @GetMapping("/v1/orders/{orderId}")
    public ResponseEntity<Map<String, Object>> getOrder(
            @PathVariable String orderId) {

        // Ví dụ dữ liệu giả lập, không phải repository/database thật.
        Map<String, Object> body = Map.of(
                "id", orderId,
                "totalAmount", 150000,
                "status", "PAID"
        );

        return ResponseEntity.ok()
                .contentType(MediaType.APPLICATION_JSON)
                .header("Deprecation", "@1803859200")
                .header("Sunset", "Wed, 01 Sep 2027 00:00:00 GMT")
                .header(
                        HttpHeaders.LINK,
                        "<https://developer.example.com/orders/migrate-v2>"
                        + "; rel=\"deprecation\""
                )
                .body(body);
    }
}
~~~

Ví dụ này chỉ chứng minh HTTP headers/schema của **v1**; production phải dùng **cấu hình ngày/version tập trung**, có contract tests và không hardcode data/order IDs. Đảm bảo cả responses lỗi quan trọng (4xx/5xx) cũng thể hiện thông tin phù hợp khi policy yêu cầu; tránh trả deprecation headers trên **/v2** nếu chỉ v1 bị deprecated.

**Không dùng 301/302 redirect từ v1 sang v2 làm giải pháp mặc định**: client POST, authentication, idempotency, response schema và cache semantics có thể khác, làm redirect gây mất dữ liệu hoặc lỗi không lường trước.

### 4.4. Khi đến ngày cutoff, API trả gì?

Không có một HTTP status code duy nhất bắt buộc cho mọi retired API. Một lựa chọn chính sách:

- Sau khi ngắt route, trả **410 Gone** và liên kết đến migration guide nếu platform/backend hỗ trợ và không tiết lộ dữ liệu không được phép.
- Với request thiếu quyền, **401/403** vẫn phải theo auth policy; không bỏ authentication chỉ để hiển thị hướng dẫn.
- Với API Gateway/Apigee, cách trả status/body tùy backend hoặc proxy policy; **không phải tính năng tự động từ API hub lifecycle**.
- Tiếp tục giám sát requests đến v1 để phát hiện client chưa migrate; có quy trình re-enable khẩn cấp được phê duyệt trong thời gian rollback.

## 5. API Gateway: cập nhật API configs theo chu kỳ release

**API Gateway có hai lớp chính:**

- **API config:** được tạo bằng cách upload OpenAPI/gRPC definition; cấu hình logic hầu như **bất biến** (chỉ có thể đổi display name/labels).
- **Gateway:** một resource triển khai trong region, phục vụ **một API config tại một thời điểm**; có thể update gateway để trỏ sang config mới.

~~~mermaid
flowchart LR
    SPECA["openapi-v1.yaml"] --> CA["API config: orders-config-001"]
    SPECB["openapi-v1-updated.yaml"] --> CB["API config: orders-config-002"]
    CA --> GW["Gateway: orders-gw\nregion X"]
    CB -. "Deploy config mới" .-> GW
    GW --> CLIENT["Consumers /v1, /v2\nnếu cùng config có cả hai"]
~~~

### 5.1. Phân biệt config rollout và versioning

- **orders-config-001 → 002** có thể chỉ là thêm monitoring hoặc sửa backend target **mà vẫn giữ v1**.
- Nếu muốn một gateway phục vụ cả **/v1 và /v2**, API definition **được triển khai trong cùng config** phải định nghĩa cả hai paths, hoặc thiết kế thêm gateway/domain/routing ở lớp trên. Không thể gắn **hai API configs** đồng thời vào **một gateway**.
- Khi gateway update, platform hỗ trợ đường chuyển cấu hình không gián đoạn theo mô hình sản phẩm, nhưng **một khoảng thời gian có thể vẫn có requests đi theo config cũ**. Thiết kế cả hai cấu hình và backend tương thích trong quá trình chuyển.
- Nếu cùng API có gateways ở nhiều regions, cập nhật **từng gateway riêng** và theo dõi deployment drift.

### 5.2. Đọc trước khi thay đổi (chỉ đọc)

~~~bash
PROJECT_ID="YOUR_PROJECT_ID"
API_ID="orders-api"
GATEWAY_REGION="YOUR_SUPPORTED_GATEWAY_REGION"
GATEWAY_ID="orders-gw"

gcloud auth list
gcloud config list project

gcloud api-gateway apis list \
  --project="$PROJECT_ID"

gcloud api-gateway api-configs list \
  --api="$API_ID" --project="$PROJECT_ID"

gcloud api-gateway gateways list \
  --location="$GATEWAY_REGION" --project="$PROJECT_ID"

gcloud api-gateway gateways describe "$GATEWAY_ID" \
  --location="$GATEWAY_REGION" \
  --project="$PROJECT_ID" \
  --format=yaml
~~~

Chỉ thực hiện khi có API đã tồn tại và người học được cấp quyền. **Region phải thuộc danh sách API Gateway hỗ trợ**; không suy từ region Cloud Run/GKE rằng Gateway cũng chắc chắn hỗ trợ. Đọc gateway đang dùng **apiConfig**, thời điểm update, traffic và managed service trước khi can thiệp.

### 5.3. Ví dụ pipeline tạo config mới và cập nhật gateway

Giả sử tài liệu **openapi-orders.yaml** đã khai báo đầy đủ API Gateway backend/security, đã qua linter và được owner duyệt. **Không dùng trực tiếp hai OpenAPI snippets học khái niệm ở mục 3 để tạo API public** vì còn thiếu backend/auth.

~~~bash
# THAY ĐỔI THẬT — chỉ trong project/gateway lab được phê duyệt.
CONFIG_ID="orders-config-20270301"
BACKEND_SA="gateway-backend@$PROJECT_ID.iam.gserviceaccount.com"

gcloud api-gateway api-configs create "$CONFIG_ID" \
  --api="$API_ID" \
  --openapi-spec="openapi-orders.yaml" \
  --backend-auth-service-account="$BACKEND_SA" \
  --project="$PROJECT_ID"

# CHỈ ĐỌC — chờ config ACTIVE và xác minh contract metadata.
gcloud api-gateway api-configs describe "$CONFIG_ID" \
  --api="$API_ID" --project="$PROJECT_ID"

# THAY ĐỔI GATEWAY — cần change window/rollback plan.
gcloud api-gateway gateways update "$GATEWAY_ID" \
  --api="$API_ID" \
  --api-config="$CONFIG_ID" \
  --location="$GATEWAY_REGION" \
  --project="$PROJECT_ID"

# CHỈ ĐỌC — xác minh gateway đang dùng config mới.
gcloud api-gateway gateways describe "$GATEWAY_ID" \
  --location="$GATEWAY_REGION" --project="$PROJECT_ID" \
  --format="yaml(apiConfig,state,defaultHostname)"
~~~

**Điều kiện:** deployer có IAM thích hợp để tạo API config/update gateway và service account được cấu hình quyền truy cập backend. Một config **đang được gateway sử dụng** thường không thể xóa cho tới khi gateway chuyển config khác hoặc bị xóa. Không thao tác xóa API configs vội vì cần rollback.

### 5.4. Quota và API config cũ

API Gateway có **các quota metric/limit áp dụng ở mức toàn API**, không chỉ ở từng API config. Khi thay đổi quota declaration ở config mới, các gateway còn đang chạy config cũ có thể bị ảnh hưởng; đổi tên/xóa metric chưa được đồng bộ có thể gây lỗi quota cho những operations cũ. Trước khi cập nhật, kiểm tra **metrics/limits nhất quán giữa các configs đang active**, especially multi-region.

Đừng dùng việc đổi config nhằm deprecate v1 như cách “tắt v1 ngay”: consumer contract/lịch thông báo phải được xử lý riêng. Xác minh gateway metrics theo **api_config, gateway_id, location, response_code_class** và logs để phát hiện rollout không đồng bộ.

## 6. Apigee: proxy revisions, environments và API products

Apigee thêm một lớp **API management** giàu policy và quản lý consumers. Ba đối tượng cần phân biệt:

- **API proxy** định nghĩa **ProxyEndpoint** (client-facing URL/base path/policies) và **TargetEndpoint** (backend routing/policies).
- **Proxy revision** là bản cấu hình kỹ thuật được đánh số tuần tự, deploy vào environment như **test** hay **prod**. Revision **không phải** public v1/v2.
- **API product** gom operations theo API proxy, resource paths, HTTP methods, quota/scopes/access; các developer apps đăng ký và nhận API credentials/quyền truy cập theo sản phẩm.

### 6.1. Hai public versions và revision triển khai

Ví dụ công ty chọn hai proxies riêng:

~~~text
Apigee environment: prod
  API proxy: orders-v1
    BasePath: /v1/orders
    Deployed proxy revision: 12

  API proxy: orders-v2
    BasePath: /v2/orders
    Deployed proxy revision: 4

API products:
  orders-read-v1 -> proxy orders-v1, GET /{orderId}
  orders-read-v2 -> proxy orders-v2, GET /{orderId}
~~~

Đây là **một phương án thiết kế**, không bắt buộc mọi Apigee organization phải tạo proxy riêng cho từng major version. Có thể route nhiều versions trong một proxy nếu cấu hình rõ ràng; điều quan trọng là public contract, basepath và ownership dễ quan sát. Không deploy hai proxies/versions với **base path xung đột trong cùng environment group** mà chưa kiểm tra báo cáo deployment change.

### 6.2. Deploy proxy revision, không đổi public path bừa bãi

Trong Apigee, khi muốn sửa policy/target của một proxy đang chạy, tạo **revision mới** và deploy thay revision cũ. Một revision đã deploy là bản read-only theo cơ chế sản phẩm; không sửa file XML tại runtime rồi kỳ vọng revision đang phục vụ tự đổi.

~~~bash
# CHỈ MINH HỌA — yêu cầu Apigee organization đã provision,
# deployer đủ IAM và quy trình change approval.
ORG="YOUR_APIGEE_ORG"
ENV="test"
API="orders-v1"
REV="13"

# CHỈ ĐỌC trước khi thao tác.
gcloud apigee apis list --organization="$ORG"
gcloud apigee apis describe "$API" --organization="$ORG"

# THAY ĐỔI THẬT — chỉ dùng khi revision 13 đã được review.
gcloud apigee apis deploy "$REV" \
  --api="$API" \
  --environment="$ENV" \
  --organization="$ORG" \
  --override
~~~

**Lưu ý:** với CLI version khác nhau, kiểm tra **gcloud apigee apis deploy --help**, và bảo đảm revision **13** có thật trong organization. Flag **--override** dùng khi cần thay một revision đang deployed, cần được review trước khi deploy. Sau thay đổi, kiểm tra deployment status, health và analytics ở environment cụ thể.

**Zero-downtime deployment không thay cho rollback.** Nếu revision mới có lỗi policy/backend, phải có khả năng redeploy revision trước và xác minh consumer SLO. API proxy deploy và API contract version là hai quyết định riêng.

### 6.3. API product phục vụ version migration

Với Apigee, một **API product** có thể giới hạn operation/path/method và quản lý app access. Ví dụ:

| Product | Operations | Consumer policy |
|---|---|---|
| **orders-read-v1** | GET /v1/orders/{id} | Không nhận đăng ký mới khi v1 Deprecated |
| **orders-read-v2** | GET /v2/orders/{id} | Khuyến nghị cho mọi tích hợp mới |
| **orders-partner-premium** | GET/POST đã được phê duyệt trên v2 | Quota và scopes theo hợp đồng |

Để hiện thực hóa:

1. Tạo **v2 proxy** với basepath không xung đột và deploy vào test.
2. Tạo **v2 API product** bao gồm đúng proxy/operations và authorization policy.
3. Đưa v2 product vào portal/docs, đăng ký developer apps hoặc cấp quyền cho apps hiện có theo quy trình.
4. Theo dõi **traffic theo app/product/version** và contact consumers.
5. Chặn **cấp quyền mới vào v1** nếu policy yêu cầu; tiếp tục tôn trọng quyền đã cấp trong migration window.
6. Khi đạt điều kiện sunset, thu hồi quyền/undeploy v1 **theo change approval**, không gỡ nhầm v2.

**Quan trọng:** khai báo quota trên API product **không tự đảm bảo quota được enforce**; Apigee proxy cần policy Quota/VerifyAPIKey/OAuth tương ứng trong flow và cấu hình đúng. Cũng không coi API key là xác thực danh tính người dùng cuối; API key thường xác định ứng dụng/consumer và cần kết hợp authn/authz phù hợp.

### 6.4. Hành vi sunset không tự xuất hiện

Để v1 trả header **Deprecation** và **Sunset**, có thể:

- Trả trực tiếp từ backend như ví dụ Spring Boot.
- Dùng Apigee **AssignMessage policy** hoặc response flow được cấu hình/kiểm thử để thêm headers.
- Ghi lịch và link migration trong developer portal/docs.

Đến thời điểm retired, có thể deploy policy trả **410 Gone** có kiểm soát hoặc undeploy/không route endpoint, tùy chính sách. Phải duy trì **auth, logging, request metrics và rollback**; API product hay API hub đổi lifecycle thành Deprecated không tự chặn đường truyền.

## 7. API hub: danh mục tập trung để quản trị nhiều API

Vấn đề lớn của một tổ chức thường không phải “có bao nhiêu routes”, mà là **không biết owner, consumer, contract đang deploy và ngày hết hỗ trợ**. API hub cung cấp đối tượng mô tả **API → versions → specifications/operations → deployments/dependencies**, cho phép tra cứu trong một danh mục.

~~~mermaid
flowchart TD
    A["API: Orders"] --> V1["Version v1\nLifecycle: Deprecated"]
    A --> V2["Version v2\nLifecycle: Active"]
    V1 --> S1["OpenAPI v1\noperations"]
    V2 --> S2["OpenAPI v2\noperations"]
    V1 --> D1["Deployment: API Gateway/Apigee prod"]
    V2 --> D2["Deployment: API Gateway/Apigee prod"]
    V1 --> OWNER["Owner / contact / migration guide"]
    V2 --> OWNER
    C["Consumer & dependency records"] -. "Theo dõi rủi ro" .-> A
~~~

### 7.1. Metadata tối thiểu cho từng API/version

| Trường | Ví dụ Orders API | Vì sao bắt buộc cho governance? |
|---|---|---|
| API ID / Display name | orders | Định danh danh mục |
| API owner / technical contact | commerce-platform/on-call | Có người chịu trách nhiệm |
| Business domain / classification | Checkout / internal partner | Phân quyền, compliance |
| Public version | v1, v2 | Phân biệt contract |
| Lifecycle | Deprecated / Active | Hiển thị trạng thái hiện hành |
| Spec URL, checksum/version | OpenAPI v1.4.0 / v2.0.0 | Nguồn sự thật để so breaking changes |
| Operations | GET order; POST order... | Tìm kiếm và impact analysis |
| Deployment environment/endpoint | test/prod URL, region, gateway/proxy | Biết version nào chạy ở đâu |
| Consumer owners/dependencies | mobile, partner-A, batch-B | Xác định ảnh hưởng khi ngừng v1 |
| Authentication/authorization | OAuth/OIDC, API key policy | Không phát hành API không rõ bảo vệ |
| SLO/SLA và support tier | p95 latency, availability | Kiểm soát rủi ro phát hành |
| Deprecation/sunset dates | 01/03 và 01/09/2027 UTC | Lịch và thông báo thống nhất |
| Migration guide/replacement | /v2/orders; link docs | Client có đường chuyển |
| Data sensitivity/retention | order metadata, PII classification | Bảo vệ dữ liệu và audit |
| Cost center / business value | commerce | Phân bổ chi phí duy trì |
| Approval/change record | CAB-XXXX | Chứng cứ cho lifecycle changes |

**Phân biệt nguồn dữ liệu:** API hub hỗ trợ thuộc tính Lifecycle/version/deployment/spec/dependency, nhưng không phải mọi trường trong bảng được tích hợp mặc định hoặc tự đồng bộ. Consumer owner, SLO, sunset date, risk score, approval có thể cần **custom attributes/links/quy trình quản trị ngoài API hub**. Tránh giả định tạo API hub version đồng nghĩa đã cấu hình Gateway/Apigee runtime.

### 7.2. Thao tác trong API hub (thực hành đọc và quản trị có quyền)

Trong **Google Cloud Console → Apigee → API hub** với một API hub instance đã provision:

1. Tìm **Orders API** hoặc đăng ký API mới theo quyền catalog editor.
2. Thêm **v1** và **v2** dưới cùng API resource.
3. Gắn OpenAPI specs tương ứng; kiểm tra API hub parse operations.
4. Gắn deployments (endpoint, môi trường, platform) cho mỗi version.
5. Chọn lifecycle attribute **Deprecated** cho v1 và **Active** cho v2; bổ sung migration URL/date bằng attributes/tài liệu theo governance của tổ chức.
6. Liên kết dependencies/owners và sử dụng search/filter để lập danh sách versions sắp sunset.
7. Kiểm chứng catalog trùng khớp runtime: v1/v2 hiện đang có endpoint nào, proxy/gateway nào.

**API hub có thể tự đăng ký Apigee proxies và tích hợp API Gateway** theo cơ chế hỗ trợ, nhưng metadata không đồng nghĩa có đầy đủ owner, policy hoặc thông tin client migration. Những trường đó cần review của đội API và có độ trễ đồng bộ; luôn kiểm tra trạng thái runtime trước khi ngắt traffic.

### 7.3. Một bản ghi danh mục mẫu (quy ước nội bộ, không phải API hub import schema)

~~~yaml
apiId: orders
version: v1
owner: commerce-platform
lifecycle: deprecated
specRef: docs/orders/openapi-v1.yaml
deployments:
  - environment: production
    gateway: orders-gw
    basePath: /v1/orders
deprecationAt: "2027-03-01T00:00:00Z"
sunsetAt: "2027-09-01T00:00:00Z"
replacement: /v2/orders
migrationGuide: https://developer.example.com/orders/migrate-v2
consumers:
  - mobile-checkout
  - partner-a
approval: CAB-EXAMPLE
~~~

Bản ghi này dùng để thảo luận **schema governance của tổ chức**; không dùng **gcloud** hoặc API hub REST để import trực tiếp như một payload chuẩn. Khi triển khai tự động hóa, phải map từng trường sang API hub resource/attributes và lưu các liên kết ngoài khi sản phẩm chưa có trường tương ứng.

## 8. Quy trình thông báo và di chuyển consumers

Một kế hoạch deprecation thành công phải trả lời: **ai đang dùng v1, ai là người quyết định đổi, phiên bản nào thay thế, lịch cắt và chứng cứ hoàn tất**.

### 8.1. Playbook từng giai đoạn

| Giai đoạn | Điều cần làm | Bằng chứng |
|---|---|---|
| **Inventory** | Tìm mọi client v1, app ID, key/token owner, job định kỳ | Traffic dashboard + danh sách dependencies |
| **Design v2** | Contract diff, migration examples, SDK, changelog | Review và spec version |
| **Announce** | Portal, email/partner notice, OpenAPI deprecated, HTTP headers | Thông báo và người nhận |
| **Migration** | Client canary, contract tests, compatibility window | % v1 usage giảm; client sign-off |
| **Final warning** | Liên hệ consumer chưa chuyển, kiểm tra các ngoại lệ | Waiver/extension được duyệt |
| **Sunset decision** | Kiểm tra SLO, traffic, compliance, business approval | Change record và rollback window |
| **Retire** | Tắt route/access đúng phạm vi, quan sát lỗi/traffic cũ | Runtime đã đổi, API hub + docs đồng bộ |

**Không ngừng v1 chỉ vì đến ngày** nếu contract với consumer quan trọng chưa cho phép: cần cơ chế exception/extension có owner và expiry, nhưng không biến ngoại lệ thành việc hỗ trợ vô thời hạn không có kế hoạch.

### 8.2. Tình huống consumer không có identity rõ

Có request logs nhưng không biết ai gọi v1 vì API dùng chung một API key hoặc không có client identifier. Đây là **lỗ hổng governance cần sửa trước sunset**:

- Chuyển sang credentials phân biệt developer app/service account theo policy.
- Gắn consumer identity vào logs/analytics sau khi đã đáp ứng privacy policy.
- Thu thập SDK version/User-Agent ở mức phù hợp, nhưng không coi User-Agent là danh tính đáng tin.
- Phối hợp owner của mobile app/partner và inventory các batch jobs ít chạy.
- Không log raw Authorization header, API key, PII hoặc full request body chỉ để tìm người dùng.

Trong Apigee, thông tin developer app/API product có thể giúp phân tích consumer nếu proxy đã áp policy xác minh tương ứng. Trên API Gateway, metrics và log có các chiều gateway/config/response, nhưng cần kết hợp identity bên ứng dụng hoặc API key/consumer metadata khi được cấu hình; không giả định một cột log duy nhất luôn chỉ rõ người tiêu thụ.

### 8.3. Mẫu thông báo gửi consumer

~~~text
Subject: Orders API v1 - deprecation và kế hoạch chuyển sang v2

Orders API v1 (/v1/orders) sẽ chuyển sang Deprecated từ
01/03/2027 00:00 UTC. Ngày ngừng hỗ trợ dự kiến: 01/09/2027 00:00 UTC.

Phiên bản thay thế: /v2/orders
Khác biệt chính: totalAmount -> amount.value + amount.currency
Tài liệu hợp đồng và migration: [URL thật của tổ chức]
Các bước:
1. Đăng ký quyền/credentials v2 nếu cần.
2. Cập nhật SDK, URL, model JSON và test ở staging.
3. Báo ngày hoàn tất migration cho API owner trước hạn.
4. Liên hệ support: [kênh chính thức]

Nếu không thể chuyển trước hạn, gửi yêu cầu ngoại lệ kèm
consumer ID, khối lượng traffic, lý do và ngày dự kiến hoàn tất.
~~~

Mẫu này **không phải thay thế thông báo theo hợp đồng**. Một API public có SLA/terms cần nội dung, thời hạn và kênh truyền thông được Legal/Support/Partner Management xác nhận.

## 9. Đo việc sử dụng v1 và đặt “exit criteria” trước sunset

Quyết định ngừng API phải dựa trên **số liệu theo public version**, không chỉ xem một gateway hay proxy có traffic hay không. Một gateway config có thể phục vụ **cả v1 lẫn v2**; tổng requests theo API config không đủ để kết luận v1 đã hết người dùng.

### 9.1. Các chỉ số cần giám sát

| Chỉ số | Ý nghĩa khi quyết định retire |
|---|---|
| **Requests theo /v1 và /v2** | Mức dùng thực của mỗi public version |
| **Active consumers per version** | Bao nhiêu app/partner/job vẫn sử dụng v1 |
| **Last-seen time** | Consumer ít gọi nhưng có thể quan trọng, ví dụ batch hàng tháng |
| **Error rate / p95 latency** | Tránh migration làm xấu SLO |
| **401/403/429/5xx** | Phân biệt lỗi credential, rate limit, backend |
| **Deprecated operations** | Một API có thể chỉ sunset một endpoint, không cả version |
| **Top consumers và SLA tier** | Ưu tiên hỗ trợ/ngoại lệ |
| **Traffic v1 sau thông báo** | Xác minh hiệu quả truyền thông |
| **Cloud Billing theo SKU** | Chi phí giữ song song hai versions |

Trong **API Gateway**, Cloud Monitoring có metric **API Gateway → Proxy → Request Count**, có thể phân theo **gateway_id, api_config, location, response_code_class**. Để có usage **/v1 vs /v2**, cần kết hợp request logs/route information hoặc metrics cấp backend đã được instrument phù hợp.

Trong **Apigee**, analytics có thể cung cấp proxy/product/developer app insights theo policies và cấu hình; nếu thiếu xác minh API key/app identity, không được khẳng định đã có danh sách đầy đủ consumer owners. Log/analytics và dữ liệu catalog phải có chính sách bảo vệ PII/keys.

### 9.2. Một truy vấn Cloud Logging tham khảo

Đây là **filter chỉ đọc cho Logs Explorer**, không phải lệnh gcloud. Thay project/location/gateway và điều chỉnh theo schema request log thực tế:

~~~text
resource.type="apigateway.googleapis.com/Gateway"
resource.labels.gateway_id="orders-gw"
resource.labels.location="YOUR_SUPPORTED_GATEWAY_REGION"
log_name="projects/YOUR_PROJECT_ID/logs/apigateway.googleapis.com%2Frequests"
~~~

Sau khi lọc, xác minh **trường nào trong log thể hiện path/operation/consumer**, rồi xây dashboard/metric cho /v1 và /v2. Đừng đoán tên JSON field từ tutorial của phiên bản sản phẩm khác rồi âm thầm bỏ các requests không match. Nếu logs không đủ attribution, bổ sung **structured logging ở backend** hoặc policy analytics của Apigee theo nguyên tắc privacy.

### 9.3. Điều kiện ngừng v1 (policy minh họa)

Một hội đồng thay đổi có thể đặt các điều kiện cùng lúc:

1. **100% các consumer có hợp đồng/đối tác quan trọng** xác nhận đã migrate, hoặc có ngoại lệ hợp lệ.
2. **Không còn client v1 được biết đang hoạt động** trong ít nhất 30 ngày bao gồm cả lịch batch hàng tháng.
3. Lượng request v1 nhỏ hơn **0,1% tổng request Orders API** trong 14 ngày, nhưng **không dùng tỷ lệ này thay điều kiện 1**.
4. v2 đáp ứng SLO, security review và compatibility tests.
5. Đã xuất bản docs, headers, migration guide; thông báo cuối đã được xác nhận.
6. Có rollback plan, feature flags/routing và dashboard cảnh báo sau cutoff.
7. Product, proxy/gateway, API hub metadata và support team cùng một trạng thái cuối.

**Các ngưỡng trên là lựa chọn ví dụ**, không phải quy định của API Gateway/Apigee. Một partner gửi 1 request/tháng có thể có giá trị lớn hơn hàng triệu requests từ hệ thống nội bộ; cần đánh giá **mức độ tác động**, không chỉ % traffic.

### 9.4. Đừng quên long-tail consumers

Các loại client thường bị bỏ sót: mobile app chưa cập nhật, browser extension, batch cuối tháng, webhook receiver, SDK được nhúng trong phần mềm bên thứ ba, môi trường DR dự phòng, hệ thống cron chỉ chạy khi có incident. Với các consumer không thể xác định, cần quyết định **risk acceptance** có người phê duyệt.

## 10. Tích hợp contract governance vào Git và CI/CD

Một danh mục có metadata đẹp nhưng code có thể deploy phá vỡ contract bất cứ lúc nào nếu thiếu **change gate**. Nguồn kiểm soát tốt thường là OpenAPI specs trong Git, tự động kiểm tra trước khi tạo gateway config hay Apigee proxy revision.

### 10.1. Pipeline khuyến nghị

~~~mermaid
flowchart TD
    PR["Pull request: OpenAPI + implementation"] --> LINT["Lint OpenAPI và policies"]
    LINT --> DIFF["Diff với bản public gần nhất"]
    DIFF --> BREAK{"Breaking change?"}
    BREAK -- "Có" --> NEW["Yêu cầu major version mới hoặc waiver"]
    BREAK -- "Không" --> TEST["Contract & security tests"]
    NEW --> REVIEW["Owner + security/consumer review"]
    REVIEW --> TEST
    TEST --> STAGE["Deploy stage: gateway config/proxy revision"]
    STAGE --> SMOKE["Smoke & canary; đo lỗi/latency"]
    SMOKE --> PROD["Promote tới prod theo change approval"]
    PROD --> CATALOG["Cập nhật API hub/docs/deprecation"]
~~~

**Bước kiểm tra bắt buộc nên có:**

- YAML/OpenAPI parse/lint thành công.
- So sánh request/response schemas, parameters, status/error codes và security requirements với version đang public.
- Chặn thay đổi breaking trong **v1** trừ khi được cấp ngoại lệ có thời hạn và kế hoạch consumer migration.
- Kiểm tra implementation tuân theo spec: contract tests, smoke tests cả v1 và v2.
- Kiểm tra authn/authz, rate limits, input validation, payload max và lỗi backend.
- Kiểm tra metadata: owner, public version, release note, spec checksum, deployment URL.
- Đảm bảo v1 vẫn chạy trong migration window khi deploy v2.
- Đối chiếu gateway/Apigee deploy status, version và API hub/catalog sau promotion.

### 10.2. Cách hiểu một OpenAPI diff

Ví dụ diff báo:

~~~text
GET /v1/orders/{orderId}
- response.totalAmount: integer, required
+ response.amount: object, required

Classification: BREAKING for consumers of v1
Decision:
  Reject change on /v1
  Introduce /v2/orders/{orderId}
  Keep v1 response schema until approved sunset
~~~

Công cụ diff tự động có thể không hiểu **business semantics**: thay đơn vị tiền từ VND sang cents nhưng type vẫn integer có thể **không bị tool phát hiện**. Phải kết hợp review của API owner và consumer contract tests.

### 10.3. Ví dụ checklist review pull request

~~~text
API_ID / PUBLIC_VERSION:
SPEC_COMMIT / SPEC_CHECKSUM:
CHANGE_TYPE: additive / breaking / security / behavioral
AFFECTED_OPERATIONS:
BREAKING_DIFF_REVIEW:
OWNER_APPROVAL:
SECURITY_REVIEW:
CONSUMER_IMPACT / NOTIFICATION:
GATEWAY_CONFIG_ID / APIGEE_PROXY_REVISION:
STAGING_URL / CONTRACT_TEST_RESULT:
PROD_ROLLOUT_WINDOW:
DEPRECATION_DATE / SUNSET_DATE (IF ANY):
API_HUB_METADATA_UPDATED:
MONITORING / ROLLBACK:
~~~

Không thay thế một approval bằng việc CI báo “green” khi chưa có consumer contract hoặc compliance yêu cầu con người phê duyệt.

## 11. Bảo mật, quyền và chi phí trong vòng đời API

### 11.1. Ranh giới trách nhiệm

| Thành phần | Quyền và giới hạn |
|---|---|
| **API Gateway** | Ai tạo config/update gateway, service account để gọi backend, IAM và API key/JWT theo spec |
| **Apigee** | Ai sửa/deploy proxy revisions, policies, products, developer apps, analytics |
| **API hub** | Ai xem/chỉnh catalog/versions/lifecycle/spec/deployments |
| **Cloud Run/GKE backend** | Runtime identity, IAM, database authorization, VPC access |
| **Consumer** | API keys/OAuth credentials, quota/scopes và quyền theo hợp đồng |

**Không cấp quyền deploy platform cho người chỉ cần sửa metadata catalog.** Cũng không cấp quyền API hub Editor để thay đổi production runtime rồi nghĩ IAM sẽ “tự lan sang gateway”: các hệ thống có ranh giới riêng.

### 11.2. Khi deprecate một API có dữ liệu nhạy cảm

- Không log raw API keys, JWTs, Authorization header, account IDs hay payload đơn hàng.
- Nếu cần biết consumer, dùng **app identity** hoặc principal đã được bảo vệ; gắn pseudonymous identifier khi có thể.
- Tôn trọng retention/privacy policy đối với API logs, telemetry và consumer registry.
- Một v1 cũ có lỗ hổng nghiêm trọng có thể cần **security emergency change** sớm hơn lịch sunset; phải có risk review, thông báo và mitigation.
- Không redirect request có credentials hoặc request body sang endpoint mới khi chưa đánh giá auth/HTTPS/redirect semantics.
- Đảm bảo HTTP Deprecation/Link headers không tiết lộ thông tin nội bộ ở endpoint public.

### 11.3. Tối ưu chi phí nhưng không cắt tùy tiện

Giữ đồng thời v1/v2 có thể tăng phí:

- API Gateway requests và các gateways triển khai ở nhiều regions.
- Apigee capacity/proxy deployment units, policies, analytics theo mô hình giá/entitlements.
- Compute/backend Cloud Run/GKE/DB, cache và traffic network.
- Logging, trace retention, dashboard và API hub/governance.
- Nhân sự support, security patches và tests cho hai contracts.

Không kết luận xóa một **API Gateway config** sẽ giảm chi phí chạy gateway tương ứng: config và gateway là hai resource khác vai trò, phí thực nằm theo SKU/tài nguyên đã provision và request. Trên Apigee, giữ một v1 proxy deployed có thể ảnh hưởng **proxy deployment units** theo environment/instance. Phải đo phí bằng **Cloud Billing** và entitlement thật, không chỉ đếm versions trong API hub.

Tại mốc sunset, chỉ thu hồi **gateway/proxy/SDK/spec deployment không còn consumers** sau khi đã đối chiếu owner, SLO, compliance và khả năng rollback. Không xóa log/contract archives còn trong thời gian retention quy định.

## 12. Lab: quản lý v1/v2 bằng spec, gateway config và catalog

Lab gồm hai mức: **A. Thực hành tài liệu không tạo tài nguyên**, và **B. Triển khai tùy chọn trên project đã được phê duyệt**. Trong production, API Gateway/Apigee và API hub có chi phí, IAM, quota và điều kiện provision; không tạo resources chỉ để chạy một phép thử nếu tổ chức chưa cho phép.

### 12.1. Lab A — Contract-only, có thể làm offline

Chuẩn bị hai tệp OpenAPI v1/v2 như mục 3 ở một **thư mục thực hành riêng** của người học. Sau đó lập bảng:

| Kiểm thử | v1 | v2 | PASS khi |
|---|---|---|---|
| GET order 200 | Có totalAmount | Có amount.value/currency | Schema khớp spec |
| ID không tồn tại | 404 | 404 | Error handling nhất quán |
| Auth thiếu | 401/403 theo policy | 401/403 | Không mở dữ liệu |
| Tổng tiền | 150000 VND | value=150000, currency=VND | Không đổi đơn vị |
| Deprecated marker | true | false/không khai báo | Docs rõ |
| Deprecation response header | Có trên v1 theo ngày policy | Không áp dụng | RFC 9745 đúng định dạng |
| Sunset header | Ngày UTC theo policy | Không áp dụng | RFC 8594 đúng định dạng |

Thảo luận: nếu v1 response xóa **totalAmount** mà không đổi public path, contract test nào fail? Nếu v2 có response mới nhưng database đã thay schema, kiểm tra nào giúp bảo đảm v1 vẫn hoạt động?

### 12.2. Lab B — OpenAPI 2.0 cho API Gateway (chỉ trong môi trường lab được phép)

Ví dụ dưới đây là **cấu hình minh họa đầy đủ cấu trúc cơ bản** để một gateway gọi một backend Cloud Run đã tồn tại. Backend **phải tự implement cả /v1 và /v2**, yêu cầu IAM phù hợp, và thông tin API key phải được quản lý đúng. Thay URL thật; không dùng URL placeholder để deploy.

~~~yaml
swagger: "2.0"
info:
  title: Orders API Lab
  description: API Gateway demo, v1 deprecated và v2 active
  version: "2.0.0"
schemes:
  - https
produces:
  - application/json
x-google-allow: configured
x-google-backend:
  address: https://REPLACE_WITH_CLOUD_RUN_SERVICE_URL
  path_translation: APPEND_PATH_TO_ADDRESS
securityDefinitions:
  api_key:
    type: apiKey
    name: key
    in: query
paths:
  /v1/orders/{orderId}:
    get:
      operationId: getOrderV1
      deprecated: true
      security:
        - api_key: []
      parameters:
        - name: orderId
          in: path
          required: true
          type: string
      responses:
        "200":
          description: Order v1
          schema:
            type: object
            required: [id, totalAmount, status]
            properties:
              id: {type: string}
              totalAmount: {type: integer, format: int64}
              status: {type: string}
        "404":
          description: Not found
  /v2/orders/{orderId}:
    get:
      operationId: getOrderV2
      security:
        - api_key: []
      parameters:
        - name: orderId
          in: path
          required: true
          type: string
      responses:
        "200":
          description: Order v2
          schema:
            type: object
            required: [id, amount, status]
            properties:
              id: {type: string}
              amount:
                type: object
                required: [value, currency]
                properties:
                  value: {type: integer, format: int64}
                  currency: {type: string}
              status: {type: string}
        "404":
          description: Not found
~~~

Lưu tên **openapi-orders.yaml** trong **thư mục lab của người học**, không phải file knowledge Markdown/YAML do worker đang xử lý. Những điều cần xác nhận trước triển khai:

- Backend Cloud Run chạy thật, xử lý cả hai routes/response schemas và yêu cầu IAM đúng.
- **x-google-backend.address** là URL HTTPS thật, không có trailing path ngoài dự kiến; **APPEND_PATH_TO_ADDRESS** giữ public request path khi proxy đến backend.
- **backend authentication** được cấu hình bằng service account của API Gateway và Cloud Run backend cho phép principal tương ứng gọi.
- API key requirement có nghĩa gateway nhận dạng consumer project/quota; **API key không thay thế xác thực người dùng cuối** nếu endpoint chứa dữ liệu đơn hàng. Bổ sung OAuth/JWT/application authorization theo yêu cầu.
- Managed service của API Gateway đã được enable cho project consumer/keys theo quy trình; chưa đủ chỉ có securityDefinitions.
- OpenAPI2 document là ví dụ theo mục tiêu lab; người dùng phải xác nhận giới hạn OpenAPI extensions và tài liệu Google Cloud tại thời điểm chạy.

Sau khi đã tạo config mới ở mục 5 (nếu được phép), xác minh:

~~~bash
# CHỈ ĐỌC.
gcloud api-gateway api-configs describe "$CONFIG_ID" \
  --api="$API_ID" --project="$PROJECT_ID"

gcloud api-gateway gateways describe "$GATEWAY_ID" \
  --location="$GATEWAY_REGION" --project="$PROJECT_ID"

# URL backend/gateway và API key phải lấy từ tài nguyên thật.
# Không in token/key vào logs hoặc file báo cáo.
~~~

Kiểm tra HTTP từ client **đã có quyền**:

~~~bash
# CHỈ GỬI REQUEST; không tự tạo/xóa cloud resources.
# Đổi URL và xác thực theo security policy thực tế.
curl -i "https://REAL_GATEWAY_HOST/v1/orders/ord-1001"
curl -i "https://REAL_GATEWAY_HOST/v2/orders/ord-1001"
~~~

Nếu spec yêu cầu API key, requests thiếu key sẽ bị từ chối; đó có thể là hành vi đúng. Không dùng log đầy đủ chứa query parameter **key** trong biên bản học tập. Kiểm tra **/v1** có headers Deprecation/Sunset từ backend/proxy nếu đã triển khai, vì OpenAPI **deprecated: true** không tự thêm các headers đó.

### 12.3. Lab C — Kiểm kê một API hiện có trong API hub

Nếu tổ chức đã có API hub được provision và có quyền xem:

1. Tìm một API thuộc nhóm đang quản lý.
2. Xác định owner và những versions đã đăng ký.
3. Mở spec của từng version, so sánh operations.
4. Kiểm tra deployments test/prod, platform, endpoint và lifecycle.
5. Ghi consumer/dependency thông qua catalog/analytics/chủ sở hữu khi có.
6. Đối chiếu một version đang **Deprecated** với logs/traffic thực; nếu còn dùng, mở migration ticket.
7. Không thay lifecycle/cắt traffic khi chỉ được giao kiểm kê.

Đầu ra là **bảng portfolio** 3–5 APIs với owner, version, lifecycle, last deployment, deprecation/sunset dates, consumers và gaps. Nếu trường không có, ghi **UNKNOWN** thay vì suy đoán.

## 13. Runbook sunset/rollback trong production

### 13.1. Ngày trước cutoff

- Đóng băng thay đổi breaking trên v1, chỉ nhận security fixes được review.
- Kiểm kê traffic/người dùng qua một chu kỳ đủ dài; xác nhận batch định kỳ.
- Xác nhận v2 đã đạt SLO và client contract tests; không còn migration blockers.
- Xác nhận API product credentials, developer apps và backend IAM của v2.
- Lấy snapshot cấu hình deploy: **API Gateway config ID** hoặc **Apigee proxy revision**, cùng backend release/digest và policy.
- Công bố “final reminder” kèm date/time UTC, kênh hỗ trợ và ngoại lệ được duyệt.
- Tạo change record với **go/no-go criteria**, rollback owner và thời hạn khôi phục.

### 13.2. Khi thực hiện cutoff

~~~mermaid
flowchart TD
    READY["Go/no-go được duyệt"] --> BASE["Snapshot logs, traffic, configs"]
    BASE --> CHANGE["Ngừng /v1 đúng phạm vi"]
    CHANGE --> TEST["Smoke /v2 + auth + 404/410 /v1"]
    TEST --> OK{"SLO / lỗi / consumer impact đạt?"}
    OK -- "Không" --> ROLL["Rollback config/revision/route"]
    OK -- "Có" --> WATCH["Observe 4xx, 5xx, support tickets"]
    WATCH --> UPDATE["Cập nhật API hub, docs và records"]
~~~

**Thứ tự thao tác tùy nền tảng:**

- **API Gateway:** tạo config mới chứa routes/policies sau cutoff, cập nhật **gateway(s)** và theo dõi. Giữ config trước để rollback nếu còn hợp lệ. Không xóa config cũ khi gateway chưa rời khỏi nó.
- **Apigee:** deploy proxy revision mới hoặc thay API product/policy theo kế hoạch. Tránh xóa credentials chung đang được v2 dùng. Nếu cần 410 Gone, thực hiện policy/backend behavior có kiểm chứng.
- **API hub:** cập nhật lifecycle **Retired** và deployment metadata **sau khi runtime thực sự đổi**; API hub không thực thi cutoff.

### 13.3. Sau cutoff

Theo dõi tỷ lệ request v1, nguồn 4xx/5xx, client complaints, tác động batch, on-call và khả năng khôi phục. Ghi rõ **đã tắt version nào, path nào, tại region nào**; một gateway ở region khác còn config cũ nghĩa là retired chưa hoàn toàn.

Không xóa toàn bộ v1 logs/docs ngay: cần audit, troubleshooting và tuân thủ retention. Có thể giữ **spec v1 và migration guide ở trạng thái archive** trong danh mục ngay cả khi endpoint đã ngừng.

## 14. Case study: Orders API của hệ thống thương mại điện tử

### 14.1. Bối cảnh

Orders API được phục vụ qua **API Gateway** tới Java service trên Cloud Run. Ứng dụng mobile và ba đối tác đang gọi **/v1/orders**. Một đối tác chỉ thực hiện đối soát vào ngày cuối tháng. Công ty muốn chuẩn hóa cách biểu diễn tiền bằng object có currency trong **v2** và cần API catalog cho hơn 100 APIs.

**Kế hoạch:**

1. Giữ v1 hoạt động, phát hành v2 với contract riêng.
2. Đăng ký cả hai vào API hub, gắn owner, spec và deployment.
3. Công bố mốc Deprecation/Sunset qua docs, portal và headers v1.
4. Cấp v2 credentials/product nếu dùng Apigee API products.
5. Thu số liệu từng client, **không chỉ tổng traffic**.
6. Thử cutoff trong staging, sau đó production theo change window.
7. Chỉ chuyển v1 sang Retired khi runtime đã ngừng và không còn exceptions được phê duyệt.

### 14.2. Sự cố giả định

Tháng 08/2027, dashboard báo chỉ còn 0,05% traffic v1 nên nhóm định gỡ ngay. Tuy nhiên một đối tác bảo hiểm gọi API một lần cuối tháng để đối soát thanh toán, chiếm ít requests nhưng tác động lớn. API hub có owner nhưng không lưu consumer dependency đó.

**Sai lầm:** dùng ngưỡng % request để thay kết quả phân tích rủi ro. **Khắc phục:** liên hệ đối tác, hoàn tất v2 integration test, thêm dependency/owner vào danh mục, cấp ngoại lệ có hạn đến khi đối tác chuyển. Sau đó mới sunset.

### 14.3. Tiêu chí thành công

- Cả v1 và v2 trả đúng schemas, v1 không bị phá trong migration window.
- Các consumer critical có bằng chứng chuyển sang v2.
- API hub thể hiện đúng version, deployment, owner và lifecycle.
- Không có API product/key của v2 bị thu hồi nhầm khi đóng v1.
- p95, 5xx, auth errors và partner support tickets ổn định.
- Chi phí/phí hỗ trợ v1 giảm sau retire mà vẫn tuân thủ audit/retention.

## 15. Bài tập vận dụng và đáp án

### 15.1. Bài tập A — Đánh giá breaking changes

Cho v1:

~~~json
{"id":"ord-1001","totalAmount":150000,"status":"PAID"}
~~~

Nhóm Java đề xuất bốn thay đổi:

1. Thêm response field **createdAt** (optional).
2. Đổi **totalAmount** thành **amount: {value, currency}**.
3. Thay **status="PAID"** thành **status="SETTLED"** dù schema vẫn string.
4. Yêu cầu tham số query **locale** mới cho mọi request.

**Câu hỏi:** thay đổi nào có khả năng breaking và cần version mới? Có tình huống nào công cụ OpenAPI diff không phát hiện?

**Đáp án định hướng:** (2) breaking vì đổi schema; (4) breaking vì thêm required param; (3) có thể breaking về semantics/client enum dù type không đổi; (1) thường tương thích nhưng cần kiểm tra strict clients. Với trường hợp (3), chỉ schema type string có thể khiến static diff không biết semantics thay đổi.

### 15.2. Bài tập B — Đọc đúng ba tầng phiên bản

Hệ thống đang có:

~~~text
Public API: /v1/orders
OpenAPI info.version: 1.4.2
API Gateway API config: orders-config-202702
Apigee proxy: orders-v1, revision 19
API hub: Orders API, version v1, Lifecycle Deprecated
Backend: checkout-api revision 20270212
~~~

**Câu hỏi:**

1. Tạo API Gateway config **orders-config-202703** có bắt buộc client chuyển sang **/v2** không?
2. Apigee proxy revision 20 có nghĩa public API version 20 không?
3. Đổi API hub lifecycle v1 thành Retired có tự ngắt request không?
4. Backend rollout từ revision 20270212 sang 20270301 có cần thay public version không?

**Đáp án:** cả bốn câu đều **không tự động**. Public contract thay đổi hay không phụ thuộc spec, behavior, routing và chính sách tương thích; runtime version/revision/catalog metadata là những lớp khác.

### 15.3. Bài tập C — Tính tỷ lệ traffic và quyết định sunset

Giả sử trong 14 ngày:

| Consumer | Requests v1 | Thuộc nhóm critical? |
|---|---:|---|
| Mobile cũ | 3.000 | Không |
| Partner đối soát | 20 | **Có** |
| Batch nội bộ | 500 | Không |
| Tổng API v1 + v2 | 5.000.000 | — |

**Tính toán:** v1 có **3.520 / 5.000.000 = 0,0704%** traffic.

**Câu hỏi:** Đã dưới ngưỡng 0,1%; có nên sunset v1 ngay không?

**Đáp án:** **chưa đủ điều kiện**, vì partner critical vẫn gọi v1; cần migration/sign-off hoặc ngoại lệ có hạn. Phần trăm requests là chỉ báo, không thay đánh giá tác động và hợp đồng.

### 15.4. Bài tập D — Chẩn đoán sau API Gateway rollout

Một gateway mới chuyển từ config A sang config B. Trong vài phút, một phần requests vẫn đi theo config A. Một số request báo quota errors.

**Hãy phân tích:**

- Hiện tượng có thể phù hợp mô hình update nào?
- Tại sao thay đổi quota metric definition ở config B gây rủi ro cho config A?
- Cần theo dõi metrics/logs với chiều dữ liệu gì?
- Nếu vượt SLO, rollback thế nào và cần xác minh gì?

**Đáp án định hướng:** gateway có thể phục vụ old/new configs trong giai đoạn chuyển; quota declarations áp dụng ở cấp API, nên config cũ có thể ảnh hưởng nếu metric đổi tên/xóa. Xem gateway ID, region, api_config, response code/error, backend logs, sau đó update gateway về config trước đã kiểm chứng; đảm bảo quota policy vẫn tương thích và chạy smoke tests.

### 15.5. Bài tập E — Viết kế hoạch deprecation 90 ngày

Chọn một API giả định có ba consumers, một trong số đó là batch chạy 1 lần/tháng. Soạn tài liệu không quá một trang gồm:

- Contract v1/v2 và breaking diff.
- Ngày thông báo, deprecation, sunset (UTC), consumer owner, migrations.
- Headers RFC 9745/8594, migration guide URL và danh mục API hub.
- SLO/traffic dashboard; cách tìm consumer ít gọi.
- Tiêu chí go/no-go, ngoại lệ/extension và rollback.
- Bằng chứng cho trạng thái Retired.

**Tiêu chí chấm:** mốc thời gian không mâu thuẫn, không nhầm spec version/proxy revision/public version, không giả định API hub tự tắt endpoint, có consumer critical sign-off, không lộ credentials/PII và có kế hoạch giám sát sau cutoff.

### 15.6. Mẫu checklist kiểm kê và nghiệm thu

~~~text
API_ID / BUSINESS_OWNER / TECHNICAL_OWNER:
PUBLIC_VERSION(S) / OPENAPI_SPEC_VERSION(S):
BREAKING_CHANGE_REVIEW:
API_GATEWAY_API_CONFIG(S) / REGION / GATEWAY(S):
APIGEE_PROXY / REVISION / ENVIRONMENT / API_PRODUCT:
API_HUB_API / VERSION / LIFECYCLE / DEPLOYMENT:
AUTH / QUOTA / BACKEND_IDENTITY:
DEPRECATION_AT / SUNSET_AT / TIMEZONE:
HEADER_DEPRECATION / HEADER_SUNSET / LINK:
MIGRATION_GUIDE / SDK / CHANGELOG:
KNOWN_CONSUMERS / LAST_SEEN / CRITICAL_SIGN_OFF:
V1_REQUESTS / V2_REQUESTS / 4XX / 5XX / P95:
SLO_AND_COST_IMPACT:
GO_NO_GO / EXCEPTIONS / ROLLBACK:
ACTUAL_RETIREMENT_DATE / REGION_COVERAGE:
DOCS_CATALOG_UPDATED / CHANGE_TICKET / OWNER:
OPEN_ISSUES:
~~~

Không ghi **PASS** khi chỉ có thiết kế hoặc không có quyền xem production. Ghi **UNKNOWN**, owner và bước xác minh tiếp theo. Không đưa access tokens, API keys hay thông tin đơn hàng vào báo cáo.

## 16. Tài liệu tham khảo và ghi nhớ

**Google Cloud — API Gateway:**

- [Deployment model và API configs](https://docs.cloud.google.com/api-gateway/docs/deployment-model)
- [Create/update API config](https://docs.cloud.google.com/api-gateway/docs/creating-api-config)
- [Deploy/update gateway](https://docs.cloud.google.com/api-gateway/docs/deploying-api)
- [OpenAPI versions supported](https://docs.cloud.google.com/api-gateway/docs/openapi-overview)
- [OpenAPI 2.0 extensions và backend routing](https://docs.cloud.google.com/api-gateway/docs/oasv2-extensions)
- [Use API keys](https://docs.cloud.google.com/api-gateway/docs/authenticate-api-keys)
- [Monitor API Gateway metrics/logs](https://docs.cloud.google.com/api-gateway/docs/monitoring)
- [Connect API Gateway with API hub](https://docs.cloud.google.com/api-gateway/docs/api-hub-overview)

**Google Cloud — Apigee và API hub:**

- [Understanding API proxies, revisions and policies](https://docs.cloud.google.com/apigee/docs/api-platform/fundamentals/understanding-apis-and-api-proxies)
- [Deploy API proxy revisions](https://docs.cloud.google.com/apigee/docs/api-platform/deploy/ui-deploy-new)
- [API products](https://docs.cloud.google.com/apigee/docs/api-platform/publish/what-api-product)
- [Managing API products](https://docs.cloud.google.com/apigee/docs/api-platform/publish/create-api-products)
- [What is Apigee API hub?](https://docs.cloud.google.com/apigee/docs/apihub/what-is-api-hub/)
- [API hub versions overview](https://docs.cloud.google.com/apigee/docs/apihub/versions-intro)
- [Manage API hub versions](https://docs.cloud.google.com/apigee/docs/apihub/manage-versions)
- [Manage API hub lifecycle attributes](https://docs.cloud.google.com/apigee/docs/apihub/manage-attributes)

**Chuẩn HTTP và OpenAPI:**

- [RFC 9745 — Deprecation HTTP Response Header](https://www.rfc-editor.org/rfc/rfc9745)
- [RFC 8594 — Sunset HTTP Header](https://www.rfc-editor.org/rfc/rfc8594)
- [OpenAPI Specification](https://spec.openapis.org/oas/latest.html)

**Ghi nhớ:** **Versioning** bảo vệ hợp đồng với client; **deprecation** thông báo cần chuyển đổi nhưng không tự ngừng phục vụ; **sunset/retirement** cần change approval, telemetry và hành động runtime thực. API Gateway API configs và Apigee proxy revisions là **bản cấu hình triển khai**, không phải public API versions. **API hub** giúp biết API nào đang ở trạng thái nào, thuộc về ai, chạy ở đâu và consumer nào bị ảnh hưởng — nhưng không thay quản lý traffic.

**Kết nối với lộ trình CLOUD_PROVIDERS_GCP:** quản trị API version cần phối hợp **IAM/authentication**, **Cloud Run/GKE backend deployments**, **VPC/network**, **Cloud Monitoring/Logging**, **Cloud Billing** và quy trình CI/CD. Một API thành công không chỉ “deploy chạy được”; nó phải **có contract rõ, owner rõ, đổi phiên bản có kiểm chứng, thông báo minh bạch và khả năng dừng phiên bản cũ mà không phá người dùng**.











