# Lựa chọn API Gateway, Cloud Endpoints và Apigee

> **Chương:** API Gateway và Apigee  
> **Bài học:** Lựa chọn API Gateway, Cloud Endpoints và Apigee  
> **Mô-đun:** CLOUD_PROVIDERS_GCP

Trong mô-đun **CLOUD_PROVIDERS_GCP**, người học khám phá Google Cloud từ project, IAM và VPC tới Compute Engine, GKE, Cloud Run, lưu trữ, cơ sở dữ liệu, tự động hóa triển khai, độ tin cậy và chi phí. Khi ứng dụng Java cần cung cấp API cho mobile app, đối tác hoặc nhiều microservices, câu hỏi không chỉ là “mở một cổng HTTPS”, mà là **ai được gọi API, kiểm soát lưu lượng ra sao, theo dõi mức sử dụng thế nào và ai vận hành lớp trung gian**.

Google Cloud có ba hướng giải quyết với độ phức tạp khác nhau:

- **API Gateway:** gateway **được Google quản lý**, cấu hình API bằng OpenAPI hoặc cấu hình gRPC được hỗ trợ; phù hợp cách tiếp cận tương đối gọn cho API trên Google Cloud.
- **Cloud Endpoints:** quản lý API thông qua **ESP/ESPv2 proxy do nhóm triển khai và vận hành** cạnh hoặc trước backend; hữu ích khi cần điều khiển vị trí proxy, tích hợp một số môi trường GKE/Compute Engine hoặc gRPC.
- **Apigee:** nền tảng **quản lý API toàn vòng đời** có API proxies, policies, products, developer experience, analytics và các tùy chọn triển khai/quản trị lớn hơn; phù hợp chương trình API cho nhiều nhóm, đối tác và môi trường.

**Không có sản phẩm nào thay thế logic phân quyền nghiệp vụ của API Java.** API key không tương đương xác thực người dùng; proxy hợp lệ không có nghĩa caller được xem mọi hóa đơn. Lựa chọn tốt nhất phải cân bằng **bảo mật, khả năng vận hành, nhu cầu API product, độ trễ, chi phí và trách nhiệm của nhóm**.

Các tên project, image và endpoint là ví dụ; phần lab chỉ chạy trên sandbox được cấp quyền. Tính năng, giá, giới hạn region và editions thay đổi theo thời gian, nên đối chiếu tài liệu chính thức trước khi thiết kế production.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt **API gateway** (lớp xử lý request) với **API management** (vòng đời API và developer ecosystem).
2. Mô tả kiến trúc API Gateway, Cloud Endpoints ESPv2 và Apigee, cùng các thành phần nhóm phải tự vận hành.
3. So sánh authentication, authorization, quota, rate limiting, analytics, API products, portal và policy mediation.
4. Chọn giải pháp cho Java API trên Cloud Run, GKE, Compute Engine, API B2B và backend đa môi trường.
5. Thiết kế **API Gateway → Cloud Run private backend** với OpenAPI, backend service account và `roles/run.invoker`.
6. Giải thích mô hình **ESPv2 + Service Management/Service Control** của Cloud Endpoints.
7. Hiểu thành phần cơ bản của **Apigee API proxy** và quy trình publish API product cho đối tác.
8. Đánh giá bảo mật, vận hành, phiên bản API, SLO, quota, chi phí và rủi ro chuyển đổi.
9. Chẩn đoán các lỗi thường gặp và hoàn thành bài tập lựa chọn giải pháp.

## 2. Lớp API giải quyết vấn đề nào?

~~~mermaid
flowchart LR
    Client["Mobile / đối tác / frontend"] --> Edge["API entry point<br/>Gateway / ESPv2 / Apigee proxy"]
    Edge -->|"Xác thực, route, policy"| Java["Java Orders API<br/>Cloud Run / GKE / VM"]
    Java --> SQL["Cloud SQL"]
    Java --> Storage["Cloud Storage"]
    Ops["Logging / Monitoring<br/>IAM / Billing"] -. "Quan sát" .-> Edge
    Ops -. "Quan sát" .-> Java
~~~

Có ba tầng cần tách:

| Tầng | Câu hỏi chính | Ví dụ |
|---|---|---|
| **Transport / entry point** | Client gọi hostname nào qua HTTPS? | Gateway endpoint, proxy host, external HTTPS load balancer |
| **API enforcement** | Request có credential hợp lệ, đúng quota/policy và route không? | JWT validation, API key, traffic rules, policies |
| **Application authorization** | Người dùng A có quyền xem order B không? | Java service kiểm tra tenant, scope, owner và dữ liệu |

Một load balancer có thể giải quyết TLS, routing, health checks hoặc WAF khi tích hợp phù hợp, nhưng **không tự biến thành API product platform**. Ngược lại, Apigee có API management nhưng vẫn cần backend bảo vệ dữ liệu và SLO của chính nó.

**Câu hỏi đầu tiên khi chọn sản phẩm:** bạn thực sự cần **một điểm HTTPS an toàn cho vài API**, **proxy chạy cạnh backend**, hay **một chương trình API có đối tác, products, onboarding, analytics và policy xuyên nhiều team**?

## 3. So sánh nhanh ba sản phẩm

| Tiêu chí | API Gateway | Cloud Endpoints (ESPv2) | Apigee |
|---|---|---|---|
| Kiểu sản phẩm | Fully managed API gateway | API management + **self-deployed proxy** | Full-lifecycle API management |
| Đơn vị runtime | Google vận hành gateway | Nhóm chạy ESPv2 container/proxy | Apigee runtime/environment được quản trị theo mô hình chọn |
| API definition | OpenAPI 2.0/3.x và gRPC trong các cấu hình được hỗ trợ | OpenAPI, gRPC; một số framework-specific options | API proxy flows, policies, target endpoints, API products |
| Authentication | API key, JWT và các phương thức hỗ trợ | API key/JWT qua ESPv2/Service Control | API keys, OAuth 2.0, JWT, mTLS và các policies được hỗ trợ |
| Quota / traffic controls | Quota theo API/service consumer | Service Control quota/monitoring | Quota, SpikeArrest, policies và API-product-level rules |
| Biến đổi request/response phức tạp | Hạn chế; không thay integration middleware | Hạn chế so với Apigee | Bộ policy/flow phong phú |
| Developer portal / API products | Không phải trọng tâm | API console và chia sẻ API | Developer portal, API products, developer apps, analytics |
| Mức tự quản | Thấp | Quản ESPv2 lifecycle, sizing, patch, scale | Quản policies, environments, onboarding và governance |
| Kiến trúc thường gặp | Cloud Run/Google Cloud backend | GKE/VM/service cần co-located proxy | Nhiều APIs, đối tác, multi-environment, hybrid |
| Chi phí chính | Gateway usage và dịch vụ liên quan | ESPv2 compute + networking + service infrastructure usage | Apigee environment, traffic, add-ons và các hạng mục liên quan |

**Đây là ma trận định hướng**, không phải cam kết mọi tính năng có sẵn ở mọi region, edition, version hoặc protocol. Ví dụ **Apigee portal/API products/monetization và advanced security** có thể chịu giới hạn edition/add-on; **API Gateway streaming** cũng có trạng thái hỗ trợ riêng. Không quyết định chỉ bằng một dấu tích tính năng.

## 4. Khi nào chọn API Gateway?

API Gateway là cách tiếp cận gọn khi muốn Google Cloud **vận hành lớp gateway** và bạn cần một OpenAPI/gRPC contract có chính sách cơ bản.

~~~mermaid
flowchart LR
    Users["Client app"] -->|"HTTPS + key/JWT"| GW["API Gateway<br/>managed runtime"]
    GW -->|"ID token của backend identity"| Run["Cloud Run Java service<br/>private"]
    Run --> DB["Database / Storage"]
    Config["OpenAPI / API config"] -. "Triển khai" .-> GW
~~~

### 4.1. Điểm mạnh

- Không phải duy trì deployment/container proxy cho gateway.
- Dùng OpenAPI contract với `x-google-backend` để map route đến backend.
- Hỗ trợ các cơ chế API keys, authentication JWT và quota theo cấu hình dịch vụ.
- Tích hợp Cloud Logging/Monitoring và giao diện quản lý API Gateway.
- Có thể dùng **backend authentication service account** để gọi Cloud Run private.
- Phù hợp nhóm Java nhỏ muốn tách bảo vệ/routing API khỏi code business.

### 4.2. Giới hạn cần đánh giá

- Không phải **full-lifecycle API management** với API products/developer portal như Apigee.
- Hệ thống policies/mediation không linh hoạt bằng Apigee cho các quy trình B2B phức tạp.
- Cần xem giới hạn **gateway locations, payload sizes, streaming, quota và timeout** theo tài liệu hiện hành.
- API Gateway có hostname public do dịch vụ cấp; custom domain/TLS và ingress cần thiết kế frontend phù hợp nếu yêu cầu.
- Quota cấu hình ở API level có tác động giữa các API configs/gateways cùng API; quản lý version cần xét tương thích metrics.
- Không thay database-level access control, logic tenant isolation hoặc kiểm tra authorization trong Java.

### 4.3. Ví dụ phù hợp

Nhóm có **Orders API** chạy Cloud Run: `GET /v1/orders`, `POST /v1/orders`, cần xác thực khách hàng, quota cơ bản và theo dõi lỗi. Không cần 100 API products, portal onboarding hay biến đổi XML/SOAP phức tạp. **API Gateway là ứng viên mặc định hợp lý**, nếu khu vực triển khai/limits đáp ứng.

## 5. Khi nào chọn Cloud Endpoints?

Cloud Endpoints cung cấp API management nhờ **Extensible Service Proxy (ESP)** hoặc **ESPv2** kết hợp Google Service Management và Service Control.

~~~mermaid
flowchart LR
    Caller["Client"] --> ESP["ESPv2<br/>Envoy-based proxy"]
    ESP --> Java["Java API<br/>GKE / VM / Cloud Run"]
    SM["Service Management<br/>API config"] -. "Cấu hình" .-> ESP
    SC["Service Control<br/>quota/telemetry"] <-.-> ESP
    Team["Platform team"] -. "Build, patch, scale proxy" .-> ESP
~~~

**ESPv2** dựa trên Envoy, hỗ trợ OpenAPI và gRPC trong các phạm vi được công bố. **ESP thế hệ cũ** là proxy NGINX-based, chủ yếu duy trì cho người dùng hiện hữu; với triển khai mới, **ưu tiên ESPv2** theo hướng dẫn của Google Cloud. Cloud Endpoints vẫn là một sản phẩm có tài liệu và hỗ trợ, **không đồng nghĩa bị ngừng dịch vụ chỉ vì có API Gateway**.

### 5.1. Những bước nhóm tự làm

1. Định nghĩa API (OpenAPI hoặc gRPC).
2. Deploy service config lên **Service Management**.
3. Đóng gói/triển khai **ESPv2** trước hoặc cùng backend ở môi trường hỗ trợ.
4. Cấu hình service name, backend routing, auth và quota.
5. Quản lý container image proxy, liveness/readiness, scaling, logging và cập nhật bảo mật.
6. Đo hiệu năng cả proxy lẫn Java backend.

Trong GKE, ESPv2 có thể chạy thành sidecar hoặc proxy deployment theo kiến trúc; lựa chọn làm thay đổi **điểm failure, resource requests/limits và traffic path**. Với Compute Engine, cũng cần vận hành runtime ESPv2. Cloud Run có hướng dẫn triển khai ESPv2 riêng, nhưng không được giả định toàn bộ gói tính năng của API Gateway và Endpoints tương đương.

### 5.2. Điểm mạnh và đánh đổi

| Khi phù hợp | Khi nên cân nhắc giải pháp khác |
|---|---|
| Đã có GKE/VM platform team biết vận hành Envoy/proxy | Không muốn chịu công patch/scale/rollout proxy |
| Backend gRPC hoặc đặc thù hạ tầng cần co-located proxy | Chỉ cần vài HTTP endpoints trên Cloud Run |
| Cần kiểm soát vị trí runtime và đường kết nối private | Cần developer portal, products, approval flow, analytics chuyên sâu |
| Muốn tích hợp Service Management/Service Control | Nhóm thiếu SRE capacity để giám sát proxy |

**Cloud Endpoints không “miễn vận hành”** chỉ vì phần control plane thuộc Google Cloud. Chi phí và rủi ro ở đây gồm tài nguyên **ESPv2, network, logs và công bảo trì**.

## 6. Khi nào chọn Apigee?

**Apigee** là nền tảng quản lý API có **API proxies, policies, environments, products, developer apps, developer portals và analytics**. Nhu cầu không còn chỉ “route một request tới Orders API” mà là **quản lý hàng chục API cho nhiều đội và đối tác**.

~~~mermaid
flowchart LR
    Partners["Đối tác A/B<br/>developer apps"] --> Portal["Developer portal<br/>docs + onboarding"]
    Portal --> Product["API products<br/>operations + quotas"]
    Partners --> Proxy["Apigee API proxy<br/>Auth + policy + analytics"]
    Proxy --> Java["Java Orders/Billing APIs"]
    Product -. "Quyền/plan" .-> Proxy
    Analytics["API analytics & governance"] -. "Theo dõi" .-> Proxy
~~~

### 6.1. Khái niệm của Apigee

- **API proxy:** endpoint do Apigee cung cấp, định nghĩa flows để nhận request, áp chính sách và gửi tới target service.
- **Policy:** thành phần xử lý request/response như VerifyAPIKey, OAuthV2/JWT, SpikeArrest, Quota, AssignMessage, transformations hoặc threat protection tùy tính năng.
- **Environment:** vùng triển khai logical cho proxies và quy tắc runtime.
- **API product:** nhóm operations được phép cho developer app; có thể gắn quota/access rules.
- **Developer app / developer portal:** client/đối tác đăng ký ứng dụng, nhận credentials, đọc docs và sử dụng APIs theo sản phẩm.
- **Analytics:** phân tích usage, errors, latency, behavior của consumers, hoạt động vận hành/kinh doanh.
- **Apigee hybrid:** control plane và runtime có mô hình triển khai riêng; có thể chạy runtime tại Kubernetes do tổ chức vận hành, phù hợp yêu cầu placement dữ liệu/traffic.

### 6.2. Ví dụ API product cho đối tác logistics

| Yếu tố | Thiết kế |
|---|---|
| Product | `Orders Partner API` |
| Operations | `GET /v1/orders/{id}`; `POST /v1/shipments` |
| Consumer | Ứng dụng của partner, được onboarding/phê duyệt |
| Identity | Developer app credentials, OAuth/JWT và chính sách xác thực |
| Traffic | Quota theo product, spike protection ở proxy |
| Backend | Orders Java API, Billing API, logistics service |
| Analytics | Traffic theo partner, error rate, p95 latency |
| Governance | Versioning, SLA, deprecation notice, audit, chargeback |

Apigee có thể giảm logic cross-cutting trong Java APIs, nhưng **ứng dụng vẫn kiểm tra quyền trên từng resource**: một partner được gọi `GET /v1/orders/{id}` không có nghĩa được đọc order của partner khác.

### 6.3. Đánh đổi

Apigee yêu cầu thiết kế organization/environments, API proxies, policies, routing, identities, developer onboarding và quy trình vận hành. Chi phí gồm **active environments, API calls, add-ons, network, analytics và SLA/edition**, không chỉ chi phí “một gateway đứng trước app”. Một hệ thống demo hai endpoints có thể không cần quy mô đó.

Không giả định **mọi edition** đều có sẵn monetization, advanced security, developer portal hoặc mọi loại proxy. Trước khi chọn, cần kiểm tra **Pay-as-you-go vs subscription tier**, giới hạn triển khai, vùng hỗ trợ và điều khoản thanh toán/SLA.

## 7. Ma trận chọn sản phẩm theo bài toán

| Nhu cầu | Phương án khởi đầu | Lý do |
|---|---|---|
| Một vài REST API Java trên Cloud Run | **API Gateway** | Dễ quản lý, không vận hành proxy |
| GKE service gRPC, platform team có Envoy | **Cloud Endpoints/ESPv2** hoặc API Gateway nếu tính năng phù hợp | Quyết định bằng protocol, topology và trách nhiệm vận hành |
| Hàng trăm API cho nhiều đối tác B2B | **Apigee** | Products, onboarding, policy, analytics |
| Backend nhiều clouds/on-prem, policies phức tạp | **Apigee / Apigee hybrid** | Governance và mediation đa môi trường |
| API nội bộ đơn giản chỉ cho một service gọi một service | Có thể **không cần cả ba** | Cloud Run IAM, service-to-service auth, HTTPS/LB nếu đủ |
| Đã đầu tư vào ESPv2 trên GKE, muốn giữ private proxy | **Cloud Endpoints** | Không phải đổi sang managed gateway chỉ vì có sản phẩm mới |
| Cần chỉ API key + JWT + quota cơ bản | **API Gateway** hoặc **Endpoints** | Chọn mức vận hành và hạ tầng |
| Cần hợp đồng sản phẩm API, developer self-service, analytics theo đối tác | **Apigee** | API management thay vì chỉ request routing |
| HTTP traffic cần WAF mạnh, cache/CDN, L7 DDoS | Thiết kế **Application Load Balancer + Cloud Armor/CDN** theo phù hợp | Đây là lớp network/security bổ sung, không phải đặc tính thay thế tất cả sản phẩm API |

**Thứ tự ra quyết định:** (1) chức năng bắt buộc, (2) môi trường/protocol, (3) identity/security, (4) lưu lượng và SLO, (5) vận hành, (6) tổng chi phí. Đừng khởi đầu bằng “Apigee nhiều tính năng nhất nên luôn tốt nhất”.

## 8. Thực hành: API Gateway bảo vệ Java API trên Cloud Run

Bài lab giả định Java Orders API đã chạy trên **Cloud Run private backend** có URI HTTPS và nhận `GET /v1/orders`. Để đơn giản, dùng **API Gateway ở `us-central1`**, một location được tài liệu hướng dẫn hỗ trợ; kiểm tra lại danh sách locations khi triển khai thật. Backend Cloud Run ví dụ cũng ở `us-central1`, dù gateway và backend có thể là các location khác nếu thiết kế được hỗ trợ.

**Điều kiện:** project sandbox có billing và các APIs `apigateway.googleapis.com`, `servicemanagement.googleapis.com` và `servicecontrol.googleapis.com` được bật; người thực hiện có IAM tạo API/Gateway, gắn service account và IAM Cloud Run phù hợp.

### 8.1. Sơ đồ bảo mật của mẫu

~~~mermaid
flowchart LR
    C["Client HTTPS"] -->|"Gateway public URL"| G["API Gateway: orders-gw"]
    G -->|"Google-signed ID token<br/>backend SA"| R["Cloud Run private<br/>orders-backend"]
    SA["apigw-backend SA<br/>roles/run.invoker"] -. "Được Gateway dùng" .-> G
    R --> DB["Cloud SQL / dữ liệu"]
~~~

- **Client → Gateway:** cần chính sách API key/JWT nếu muốn giới hạn caller. Mẫu cơ bản bên dưới **chưa bật client authentication**, vì thế endpoint Gateway có thể bị gọi công khai.
- **Gateway → Cloud Run:** dùng **backend authentication service account**, phải có **`roles/run.invoker` trên Cloud Run service**.
- **Cloud Run → database:** dùng runtime service account của Java và database authentication riêng; không dùng Gateway backend SA làm runtime SA.

### 8.2. Chuẩn bị backend và kiểm tra

Lệnh chỉ đọc:

~~~bash
gcloud run services describe orders-backend \
  --project=PROJECT_ID \
  --region=us-central1 \
  --format="value(status.url)"

gcloud run services get-iam-policy orders-backend \
  --project=PROJECT_ID \
  --region=us-central1
~~~

Giả sử URL backend có dạng `https://orders-backend-EXAMPLE-uc.a.run.app`. URI thực tế do Cloud Run trả về; **không sao chép tên ví dụ thành địa chỉ thật**.

Nếu Java API dùng Spring Boot, một controller tối giản:

~~~java
package com.example.orders;

import java.util.List;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class OrdersController {
    @GetMapping("/v1/orders")
    public List<String> listOrders() {
        return List.of("OD-1001", "OD-1002");
    }
}
~~~

Controller là phần nhỏ của ứng dụng Spring Boot đã có; **không phải chương trình Java hoàn chỉnh chỉ cần một file**. Khi chạy trên Cloud Run, container phải lắng nghe `0.0.0.0` tại cổng do `PORT` cung cấp hoặc theo cấu hình Cloud Run cho container. Đảm bảo image và health checks đã được thử độc lập.

### 8.3. Tạo backend service account

**Các lệnh từ đây làm thay đổi IAM/tài nguyên thật**, chỉ chạy trong sandbox:

~~~bash
gcloud iam service-accounts create apigw-backend \
  --project=PROJECT_ID \
  --display-name="API Gateway backend caller"

gcloud run services add-iam-policy-binding orders-backend \
  --project=PROJECT_ID \
  --region=us-central1 \
  --member="serviceAccount:apigw-backend@PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/run.invoker"
~~~

Gắn `roles/run.invoker` tại **service đích** thay vì toàn project để hạn chế phạm vi. Người tạo API config cần quyền sử dụng service account theo cơ chế Cloud IAM (`iam.serviceAccounts.actAs` khi yêu cầu), nhưng không nên cấp Owner cho publisher. Runtime SA của Cloud Run **không** được nhầm với backend-auth SA của API Gateway.

### 8.4. Định nghĩa API bằng OpenAPI 2.0

Tạo tệp `openapi-orders.yaml` **trong thư mục lab cục bộ** (không phải bài knowledge đang viết). Thay `BACKEND_URL` bằng URL Cloud Run thực tế, không kết thúc bằng slash ngoài ý muốn:

~~~yaml
swagger: "2.0"
info:
  title: orders-api
  version: "1.0.0"
  description: Orders API fronted by API Gateway
schemes:
- https
produces:
- application/json
x-google-backend:
  address: https://orders-backend-EXAMPLE-uc.a.run.app
  jwt_audience: https://orders-backend-EXAMPLE-uc.a.run.app
  path_translation: APPEND_PATH_TO_ADDRESS
paths:
  /v1/orders:
    get:
      operationId: listOrders
      summary: List orders (lab)
      responses:
        "200":
          description: Orders returned
          schema:
            type: array
            items:
              type: string
~~~

**Giải thích quan trọng:**

- `swagger: "2.0"` là OpenAPI 2.0; API Gateway hiện còn hỗ trợ OpenAPI 3.x nhưng các extensions có **cú pháp khác**. Đừng copy nguyên `x-google-backend` dạng OpenAPI 2 sang schema 3.x.
- `x-google-backend.address` là URL server backend; `path_translation: APPEND_PATH_TO_ADDRESS` giữ route `/v1/orders` theo thiết kế mẫu.
- `jwt_audience` chỉ định audience của ID token **Gateway gửi đến Cloud Run**. Nếu dùng revision-tag/custom path URL, không mặc định audience sẽ đúng; đặt rõ giá trị theo Cloud Run service.
- Mẫu **chưa cấu hình `securityDefinitions`/`security` cho caller**; không áp thẳng vào API production chứa dữ liệu nhạy cảm.
- Không đưa API secret hoặc JSON key vào OpenAPI spec.

### 8.5. Tạo API config và gateway

~~~bash
gcloud api-gateway api-configs create orders-config-v1 \
  --project=PROJECT_ID \
  --api=orders-api \
  --openapi-spec=openapi-orders.yaml \
  --backend-auth-service-account=apigw-backend@PROJECT_ID.iam.gserviceaccount.com

gcloud api-gateway gateways create orders-gw \
  --project=PROJECT_ID \
  --api=orders-api \
  --api-config=orders-config-v1 \
  --location=us-central1
~~~

Tạo API config có thể cần vài phút để propagate; **không vội tạo config thứ hai cho cùng API khi config đầu chưa hoàn tất**. Việc deploy gateway tạo endpoint public. Xem trạng thái:

~~~bash
gcloud api-gateway api-configs describe orders-config-v1 \
  --project=PROJECT_ID \
  --api=orders-api

gcloud api-gateway gateways describe orders-gw \
  --project=PROJECT_ID \
  --location=us-central1

gcloud api-gateway gateways list \
  --project=PROJECT_ID \
  --location=us-central1
~~~

Đọc trường **defaultHostname** hoặc gateway URL tương ứng từ resource thực tế; gửi thử request bằng HTTPS. Nếu endpoint chưa sẵn sàng, kiểm tra gateway state/config propagation thay vì lặp tạo resource.

### 8.6. Kiểm thử và thêm xác thực caller

~~~bash
# Chỉ minh họa sau khi lấy HOSTNAME thực tế từ gateway describe.
curl -i "https://GATEWAY_HOSTNAME/v1/orders"
~~~

Mẫu minh họa không giới hạn caller, nên **dùng dữ liệu thử không nhạy cảm**. Để bảo vệ production:

- **JWT authentication:** cấu hình security scheme/issuer/JWKS/audience theo nhà cung cấp danh tính; API Gateway xác minh JWT ở ingress.
- **API key:** dùng để định danh consumer project, quota/monitoring và áp giới hạn; **không đủ để xác thực người dùng với dữ liệu nhạy cảm**.
- **Backend IAM:** giữ Cloud Run private, chỉ Gateway backend SA có Invoker; không mở `allUsers` để “sửa” lỗi 403.
- **Business authorization:** Java backend kiểm tra `tenantId`/`orderId` và vai trò người dùng sau khi trust boundary đã rõ.
- **Quota:** chọn theo rủi ro abuse và năng lực backend; quota không thay WAF, load testing hoặc HPA/max-instances.

**Hai đường xác thực khác nhau:** Client phải đáp ứng **Gateway policy**; Gateway dùng **backend SA + ID token** để gọi private Cloud Run. Không lấy token của client làm IAM token để Gateway tự có quyền backend.

## 9. Nếu chọn Cloud Endpoints: bài triển khai đổi thế nào?

Cùng Java Orders API nhưng backend nằm trong GKE và team muốn dùng ESPv2:

1. Định nghĩa OpenAPI/gRPC service và authentication/quota rules.
2. Deploy config lên **Service Management** bằng lệnh/tài liệu Endpoints phù hợp.
3. Triển khai **ESPv2 image** cùng hoặc trước Java backend ở GKE.
4. Cấu hình proxy biết Service Management service name và backend URI.
5. Cấp cho proxy runtime identity các quyền cần tương tác với Google service infrastructure.
6. Gắn Service/Ingress/Load Balancer theo mạng truy cập thực tế; chú ý auth, TLS và private/public entry.
7. Theo dõi CPU/memory/latency/restarts của **cả ESPv2 lẫn Java container**.
8. Rolling update proxy riêng với backend, giữ compatibility.

### 9.1. Vì sao resource sizing khác API Gateway?

Với API Gateway, Google vận hành gateway capacity ở cấp dịch vụ. Với ESPv2 sidecar trên GKE, giả sử mỗi Pod gồm:

~~~yaml
containers:
- name: java-orders
  resources:
    requests:
      cpu: "500m"
      memory: "768Mi"
- name: espv2-proxy
  resources:
    requests:
      cpu: "100m"
      memory: "128Mi"
~~~

Scheduler phải tính requests của **cả hai containers**; ví dụ mỗi Pod request tổng **600m CPU, 896Mi RAM**, chưa tính init containers/overhead. Đây là **minh họa phần resources**, không phải manifest ESPv2 có thể triển khai ngay: còn cần image, args, ports, probes, certificates và service configuration.

### 9.2. Khi nào rời Endpoints?

Nếu đội khó duy trì ESPv2, không cần proxy co-located và workload chủ yếu là Cloud Run, có thể **thử API Gateway**. Nếu API product/partner governance mở rộng, cân nhắc **Apigee**. Migration phải kiểm tra lại **OpenAPI extensions, backend auth, quota semantics, headers, routing, gateway latency và logging**, không mặc định một file cấu hình thay thế hoàn toàn cho proxy.

## 10. Nếu chọn Apigee: khác biệt trong cách tổ chức API

Với cùng Orders API, Apigee workflow đi xa hơn:

1. Provision Apigee organization và environments theo mô hình/tier được chọn.
2. Thiết kế **API proxy** public-facing, base path `/orders/v1` và target endpoint Java API.
3. Gắn security policies ở flow phù hợp: verify credential, JWT/OAuth, quota/spike protection, mediation.
4. Đóng gói operations vào **API product** cho đối tác.
5. Tạo developer app/credentials, cấu hình approval/portal theo chính sách.
6. Deploy proxy revision vào môi trường thử, kiểm tra traffic, policy errors, analytics.
7. Promote sang môi trường production có audit/change process.
8. Monitor API traffic theo developer/app/product và backend SLO.

### 10.1. Ví dụ policy minh họa

Mẫu Apigee VerifyAPIKey (chỉ là **một policy fragment**, không phải proxy bundle đầy đủ):

~~~xml
<VerifyAPIKey name="VerifyPartnerKey">
  <DisplayName>Verify Partner API Key</DisplayName>
  <APIKey ref="request.header.x-api-key"/>
</VerifyAPIKey>
~~~

Mẫu SpikeArrest:

~~~xml
<SpikeArrest name="LimitSpikes">
  <Rate>30ps</Rate>
</SpikeArrest>
~~~

Để policies hoạt động, phải **attach vào flow**, triển khai proxy, cấu hình API product/developer app và chọn version/edition hỗ trợ. `30ps` là ví dụ, không phải rate “an toàn” cho mọi workload. **SpikeArrest** giảm spikes ngắn hạn; **Quota** dùng để quản hạn mức trong chu kỳ. Cả hai khác với **HPA** tăng replicas của backend.

### 10.2. Vì sao không nhét mọi logic vào proxy?

Apigee có thể xử lý auth, validation, header/URL transformation và policy chung. Nhưng domain logic như tính tiền, xác nhận tồn kho, quyền xem đơn hàng theo tenant, giao dịch database và audit nghiệp vụ vẫn nên ở Java backend hoặc dịch vụ chuyên trách. **Tránh proxy quá phức tạp khiến thay đổi API trở thành thay đổi business logic khó kiểm thử.**

## 11. Xác thực, quota và IAM: không được đánh đồng

| Cơ chế | Nó trả lời điều gì? | Không thay thế điều gì? |
|---|---|---|
| **API key** | Ứng dụng/project nào đang gọi để quota/billing/monitoring? | Danh tính người dùng hoặc phân quyền order |
| **JWT/OIDC** | Token do issuer tin cậy phát, hợp lệ về signature/audience/time? | Quyền thao tác với từng object |
| **OAuth 2.0** | Client/user được cấp scope/token theo authorization flow? | Domain-level authorization trong Java |
| **`roles/run.invoker`** | Gateway backend SA có thể gọi Cloud Run private không? | Caller JWT, rate limiting, database auth |
| **Quota** | Consumer được dùng bao nhiêu request trong chu kỳ? | Bảo vệ tức thời trước spikes hoặc DDoS |
| **Rate limit / SpikeArrest** | Có giảm bớt bursts vượt ngưỡng không? | Quota dài hạn, autoscaling, hard backend capacity |
| **Cloud Armor / WAF** | Có lọc một số traffic độc hại ở lớp edge hỗ trợ? | API identity/consent/business authorization |
| **mTLS** | Hai đầu có xác thực bằng certificate theo thiết kế? | Ủy quyền tenant hay role nghiệp vụ |

**Mẫu an toàn cho Java API B2B:** xác minh credential ở edge, truyền identity/claims theo hợp đồng tin cậy, backend xác minh context và thực thi tenant checks; mọi thay đổi IAM có audit. Không nhận một header `X-User-Id` do client tự gắn làm bằng chứng danh tính trừ khi có trust boundary và cơ chế xác thực/ghi đè rõ ràng.

### 11.1. Lưu ý về headers và gateway

Một gateway/proxy có thể thay hoặc bổ sung `Authorization` header khi xác thực backend. Nếu Java backend cần token người dùng gốc, thiết kế cách truyền/kiểm tra identity theo tài liệu của sản phẩm; không mặc định request sẽ giữ nguyên mọi header auth. Với API Gateway, xem cơ chế `X-Forwarded-Authorization`/backend auth và kiểm tra end-to-end. Không log raw access token, API key hoặc dữ liệu cá nhân.

## 12. Chẩn đoán và vận hành

| Triệu chứng | Khả năng nguyên nhân | Kiểm tra trước |
|---|---|---|
| API Gateway trả 401 khi client gọi | JWT issuer/audience/signature/header sai | API security config và client token |
| API Gateway trả 403 khi gọi Cloud Run | Backend SA thiếu `roles/run.invoker` | Cloud Run IAM, backend SA, ID token audience |
| Gateway 404 | Sai base path, operation hoặc route config | OpenAPI paths, path translation và gateway config |
| Gateway 5xx hoặc timeout | Backend chưa khỏe, deadline, network hoặc quota infrastructure | Gateway/Cloud Run logs, latency, Service Control |
| API key bị từ chối | Key chưa được phép dùng API, restrictions sai | API key restrictions, service enablement và config |
| ESPv2 503, Java vẫn khỏe | Proxy chưa config/service name/route hoặc overloaded | ESPv2 logs, Service Management config, Pod metrics |
| Endpoints thiếu telemetry/quota | Proxy service identity hoặc Service Control config sai | Service Control IAM/logs, service config |
| Apigee trả policy fault 401/429 | VerifyAPIKey/OAuth/Quota/SpikeArrest từ chối | Proxy trace/debug, product/app/flow và policy |
| Apigee 502/504 | Target endpoint/TLS/private networking hoặc backend timeout | Target health, certs, network, timeouts |
| p95 latency tăng sau thêm gateway | Thêm hop, policy cost, cold start/scale hoặc backend | Phân tách proxy latency và backend latency |
| Có hai configs quota khác nhau | Quota metrics thay đổi khi triển khai config mới cho cùng API | Kiểm tra quota ở API scope và tất cả gateways |
| Chi phí vượt dự toán | Traffic, gateway usage, ESPv2 nodes hoặc Apigee environments | Billing Reports, request count, active resources |

### 12.1. Bộ lệnh quan sát API Gateway

~~~bash
gcloud api-gateway apis list --project=PROJECT_ID

gcloud api-gateway api-configs list \
  --project=PROJECT_ID \
  --api=orders-api

gcloud api-gateway gateways describe orders-gw \
  --project=PROJECT_ID \
  --location=us-central1

gcloud run services logs read orders-backend \
  --project=PROJECT_ID \
  --region=us-central1 \
  --limit=50
~~~

Khi chẩn đoán, luôn xác định **lỗi tại client → gateway** hay **gateway → backend**:

- Chỉ lỗi ở gateway nhưng backend không thấy request: kiểm tra client authentication/API key/quota/route.
- Gateway gọi backend và nhận 403: kiểm tra backend auth service account + Cloud Run IAM/`aud`.
- Backend nhận request rồi 500: kiểm tra Java logs, DB/Secret Manager permissions, lỗi nghiệp vụ.
- ESPv2 hoặc Apigee có proxy riêng: cần xem runtime logs/trace và health ở cả proxy lẫn backend.

### 12.2. Rollout và rollback

**API Gateway:** tạo **API config mới** khi đổi OpenAPI, thử với gateway/canary được kiểm soát; chuyển gateway dùng config đã được kiểm tra theo hướng dẫn hiện hành. Quota metrics chung cho cùng API có thể ảnh hưởng các gateway đang chạy config cũ, nên phải đối chiếu version semantics.

**Cloud Endpoints:** cập nhật Service Management config và rollout ESPv2 có kiểm soát; cần version compatibility của proxy và backend. Trong GKE, đảm bảo requests/limits/PDB và autoscaling.

**Apigee:** quản lý API proxy revisions, shared flows và environment deployment; canary/rollback theo chính sách platform. Kiểm tra API products/developer apps để không bất ngờ thu hồi quyền đối tác.

**Không xóa API config, ESPv2 deployment hoặc Apigee proxy revision đang được consumer sử dụng** chỉ vì đã có phiên bản mới.

## 13. Chi phí và cách đánh giá TCO

| Thành phần | API Gateway | Cloud Endpoints | Apigee |
|---|---|---|---|
| Gateway/proxy runtime | Usage pricing | Compute/memory của ESPv2 nơi bạn chạy | Active environments/traffic theo plan |
| Lưu lượng/egress | Có thể phát sinh | Có thể phát sinh | Có thể phát sinh |
| Logging/Monitoring | Theo dữ liệu/logging | Theo dữ liệu + proxy logs | Analytics/logging theo tier/khả năng |
| Tự quản trị | Ít | Patch/scale/proxy rollout | Provisioning, products, policies, portal |
| Bảo mật | IAM/JWT/key + backend | IAM/JWT/key + proxy lifecycle | Policies, products và tùy chọn add-ons |
| Chi phí tổ chức | Nhỏ khi use case đơn giản | Có SRE/DevOps overhead | Có API program/platform governance |

**Dùng Tổng chi phí sở hữu (TCO), không chỉ đơn giá request:**

~~~text
TCO ≈ Phí dịch vụ gateway/proxy
    + tài nguyên compute/network/observability
    + quản lý identities, certs, security
    + thời gian phát triển & vận hành
    + chi phí incident/không đạt SLO
    + chi phí onboarding và governance đối tác
~~~

Đối với Apigee, các tiers **Pay-as-you-go** và **Subscription** có mô hình tính phí khác nhau. Với Endpoints, “dùng proxy miễn phí” là nhận định thiếu: vẫn có phí compute, network và hoạt động hệ thống liên quan. API Gateway đơn giản hơn không có nghĩa tự động rẻ nhất ở mọi traffic pattern hoặc phù hợp API có governance phức tạp.

**Checklist FinOps:** region/tier, số requests và payload, latency, active environments, proxy compute, egress, Cloud Armor/LB (nếu có), logging retention, CI/CD và on-call. Giá cần xác minh từ pricing pages khi lập dự toán.

## 14. Case study: RetailOne mở API cho đối tác

### 14.1. Bối cảnh

`RetailOne` có ba Java services: `orders-api` trên Cloud Run, `billing-api` trên GKE và `shipping-api` trên Compute Engine. Ban đầu chỉ có ứng dụng web nội bộ; sau sáu tháng có 30 đối tác logistics cần API contract, quotas, onboarding, khả năng tạm khóa một partner, analytics theo partner và một số policy chuyển đổi dữ liệu.

### 14.2. Quyết định theo giai đoạn

| Giai đoạn | Nhu cầu thật | Lựa chọn |
|---|---|---|
| **Giai đoạn A:** 1 REST API nội bộ, traffic thấp | HTTPS, JWT, IAM, cơ bản | API Gateway hoặc chỉ Cloud Run IAM nếu đủ |
| **Giai đoạn B:** backend GKE cần ESPv2 gần app | gRPC/co-located proxy, operator skills | Cloud Endpoints khi cần kiểm soát runtime |
| **Giai đoạn C:** 30 đối tác và 3 backend | API products, onboarding, quotas theo partner, analytics | Đánh giá Apigee theo TCO/edition |
| **Giai đoạn D:** multi-cloud / dữ liệu có yêu cầu placement | Policy chung và môi trường vận hành phân tán | Apigee hybrid khi đáp ứng điều kiện |

**Không cần migration chỉ vì số endpoints tăng**. Hãy có **ngưỡng quyết định**: số API products, developer onboarding hours, số chính sách riêng, báo cáo usage, cost incident và SLO. Với 30 đối tác nhưng luồng rất đơn giản, vẫn phải đo ROI Apigee.

### 14.3. Kế hoạch kiểm chứng trước khi chọn

1. Xác định OpenAPI contracts, auth mechanism, token issuer, quotas và hiện trạng data classification.
2. Ước tính RPS trung bình/đỉnh, payload sizes, p95 latency và tỷ lệ 4xx/5xx.
3. Proof-of-concept một luồng end-to-end với **backend private** và negative tests.
4. So sánh khả năng hỗ trợ protocol, policies, IP/private connectivity và vùng triển khai.
5. Kiểm tra developer onboarding, API product model, analytics/usage export, audit.
6. Đo gateway-added latency, retry behavior, backend overload và outage blast radius.
7. Dự toán TCO và đội vận hành 12 tháng, không chỉ phí lab.
8. Lập migration/rollback, ownership và bảo vệ API versions cũ.

## 15. Bài tập thực hành và tự đánh giá

### Bài 1 — API Gateway hay Apigee?

Một công ty có một Java API trên Cloud Run, ba endpoints, 20.000 requests/ngày, chỉ cần JWT và metrics cơ bản. Không có đối tác bên ngoài hay portal.

**Hỏi:** nên thử giải pháp nào trước? Vì sao Apigee có thể dư thừa?

**Gợi ý:** API Gateway, hoặc Cloud Run IAM trực tiếp nếu đủ; Apigee tạo thêm platform/chi phí không tương xứng.

### Bài 2 — Endpoints trên GKE

Một nhóm có backend gRPC trên GKE, muốn proxy cùng Pod để kiểm soát đường traffic và có SRE chăm sóc Envoy.

**Hỏi:** chọn sản phẩm nào làm ứng viên và những chi phí vận hành nào phải tính?

**Gợi ý:** Cloud Endpoints ESPv2; proxy resources, rollout, patch, network, logs và quotas.

### Bài 3 — Chương trình API partner

Doanh nghiệp có 50 đối tác, mỗi đối tác gói API operations và quota khác nhau, cần portal, onboarding, usage analytics và deprecation policy.

**Hỏi:** giải pháp nào đáp ứng ở cấp product? Cần kiểm tra điều kiện gì về edition/giá?

### Bài 4 — Backend Cloud Run 403

API Gateway có hostname hoạt động nhưng gọi `GET /v1/orders` trả 403; Cloud Run private. Người dùng đề xuất `--allow-unauthenticated`.

**Hỏi:** tại sao không nên mở backend? Cần kiểm tra service account nào và role gì?

**Gợi ý:** API config backend-auth SA cần `roles/run.invoker` trên đúng Cloud Run service, kèm `jwt_audience` đúng.

### Bài 5 — API key không đủ

Một API nhạy cảm dùng key để giới hạn 100 requests/phút. Bất kỳ người có key đều xem được order của mọi khách hàng.

**Hỏi:** thiết kế sai ở lớp nào? Hãy bổ sung caller auth và business authorization.

### Bài 6 — Quota và rate limiting

Orders API có 3 partners, mỗi partner hạn mức hàng tháng, còn backend chỉ chịu được 500 RPS ở đỉnh.

**Hỏi:** quota dài hạn giải quyết bài toán nào, rate limiting/SpikeArrest giải quyết bài toán nào? HPA có thay quota không?

### Bài 7 — Hiệu năng và sự cố

Sau khi thêm ESPv2 sidecar, Pod Java cứ `Pending` vì `Insufficient cpu`, trong khi trước đó không bị.

**Hỏi:** tính lại tổng resource requests và hành động nào khác cần kiểm tra ngoài việc tăng node count?

### Bài 8 — Migration kiểm soát rủi ro

Nhóm đang dùng Endpoints/ESPv2 và muốn chuyển sang API Gateway vì giảm gánh nặng vận hành.

**Hỏi:** hãy liệt kê những thứ phải so trước khi cutover: API spec/extensions, auth/JWT, backend identity, URL, quotas, headers, telemetry, error codes, traffic splitting và rollback.

### Bài 9 — Chọn sản phẩm theo ràng buộc

Một Java API chạy nội bộ trên Cloud Run, không có khách hàng ngoài, được gọi bởi một Cloud Run service khác bằng ID token, không yêu cầu quota/portal/analytics đặc biệt.

**Hỏi:** liệu cần mua/gắn API Gateway/Endpoints/Apigee không? Giải thích phương án đơn giản hơn.

### Bài 10 — Phương án kiến trúc tổng thể

Hãy lập bảng quyết định cho ba workload:

- Java REST Orders API chạy Cloud Run, cần auth/quota cơ bản.
- Java gRPC risk engine trên GKE, cần proxy gần ứng dụng.
- Hệ API logistics B2B nhiều backend, onboarding và analytics.

Với mỗi workload, nêu **lựa chọn**, **đối tượng quản trị**, **chính sách auth**, **dự toán**, **phương án quan sát và rollback**.

## 16. Checklist trước khi đưa API platform lên production

- [ ] Xác định API consumers, auth mode, data sensitivity, protocol và network topology.
- [ ] Phân biệt gateway ingress, backend invocation và application-level authorization.
- [ ] Đã chọn tối thiểu tính năng đủ đáp ứng nhu cầu; tránh mua thừa API management.
- [ ] Kiểm tra product availability, location, API specification support và request/streaming limits.
- [ ] Với API Gateway, OpenAPI config có `x-google-backend`, auth policy và backend SA phù hợp.
- [ ] Backend Cloud Run giữ private khi cần; Gateway backend SA có `roles/run.invoker` đúng scope.
- [ ] API keys được restriction, không coi là credential cho dữ liệu nhạy cảm.
- [ ] JWT/OIDC issuer/audience/claims và cách truyền identity tới backend đã kiểm thử.
- [ ] Với Endpoints, ESPv2 được cập nhật, có probes, resource sizing, telemetry và rollout riêng.
- [ ] Với Apigee, proxy policies, API products, developer apps và analytics phù hợp edition/tier.
- [ ] Đã phân biệt quota dài hạn, spike control, WAF và autoscaling backend.
- [ ] Đã kiểm thử 401/403/404/429/5xx, TLS, timeouts, header forwarding và rate limits.
- [ ] Có Cloud Logging/Monitoring, latency p95/p99, quota/usage metrics và alert.
- [ ] Có canary/rollout, version compatibility và rollback path đã thử.
- [ ] Đã có threat model, IAM least privilege, audit, policy review và data privacy.
- [ ] Đã dự toán gateway/ESPv2/Apigee tier, backend, network, monitoring và chi phí vận hành.
- [ ] Cleanup sandbox theo dependency; không xóa API configs/proxies đang có consumers.

## 17. Tài liệu Google Cloud chính thức

Đối chiếu phiên bản, giá, regions, SLA và policy support khi thực hiện:

- [API Gateway — About API Gateway](https://docs.cloud.google.com/api-gateway/docs/about-api-gateway)
- [API Gateway — Get started with Cloud Run](https://docs.cloud.google.com/api-gateway/docs/get-started-cloud-run)
- [API Gateway — Authentication methods](https://docs.cloud.google.com/api-gateway/docs/authentication-method)
- [API Gateway — Securing backend services](https://docs.cloud.google.com/api-gateway/docs/securing-backend-services)
- [API Gateway — API keys](https://docs.cloud.google.com/api-gateway/docs/authenticate-api-keys)
- [API Gateway — Quotas and limits](https://docs.cloud.google.com/api-gateway/docs/quotas)
- [API Gateway — API configs](https://docs.cloud.google.com/api-gateway/docs/creating-api-config)
- [Cloud Endpoints — About Endpoints](https://docs.cloud.google.com/endpoints/docs/openapi/about-cloud-endpoints)
- [Cloud Endpoints — ESPv2 architecture](https://docs.cloud.google.com/endpoints/docs/openapi/architecture-overview)
- [Cloud Endpoints — Choose an Endpoints option](https://docs.cloud.google.com/endpoints/docs/choose-endpoints-option)
- [Apigee — What is Apigee?](https://docs.cloud.google.com/apigee/docs/api-platform/get-started/what-apigee)
- [Apigee — API products](https://docs.cloud.google.com/apigee/docs/api-platform/publish/what-api-product)
- [Apigee — API Analytics](https://docs.cloud.google.com/apigee/docs/api-platform/analytics/analytics-services-overview)
- [API Gateway pricing](https://cloud.google.com/api-gateway/pricing)
- [Apigee pricing](https://cloud.google.com/apigee/pricing)

**Điểm cần nhớ:** **API Gateway** hợp với việc đưa API của Cloud Run/Google Cloud ra một endpoint được quản lý với chính sách cơ bản. **Cloud Endpoints/ESPv2** phù hợp khi cần vận hành proxy cạnh backend và kiểm soát runtime. **Apigee** phù hợp quản trị API như một sản phẩm cho nhiều consumer/đối tác với policies, onboarding và analytics. Chọn dựa trên **yêu cầu thực tế, đội vận hành, bảo mật, độ trễ, SLA và tổng chi phí**; dù dùng sản phẩm nào, Java backend vẫn phải kiểm tra **quyền dữ liệu theo người dùng/tenant** và có quy trình quan sát, phát hành, rollback.
