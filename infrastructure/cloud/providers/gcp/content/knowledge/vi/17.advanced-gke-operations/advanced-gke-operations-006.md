# Cloud Service Mesh và bảo mật giao tiếp giữa dịch vụ

Trong một hệ thống thương mại điện tử chạy trên Google Kubernetes Engine (GKE), `checkout` gọi `orders-api`, rồi `orders-api` gọi `payments`. Kubernetes Service giúp tìm địa chỉ đích, nhưng **có thể kết nối mạng** không đồng nghĩa **được quyền gọi API**. Nếu một Pod bị chiếm quyền, kẻ tấn công có thể cố gọi các dịch vụ nội bộ mà ứng dụng gốc không cần truy cập.

**Cloud Service Mesh (CSM)** bổ sung lớp kiểm soát giao tiếp *service-to-service*: nhận dạng workload, mã hóa kết nối bằng **mutual TLS (mTLS)**, cấp quyền chi tiết bằng **AuthorizationPolicy** và cung cấp telemetry tập trung. Bài thuộc chương **GKE nâng cao và vận hành** của mô-đun `CLOUD_PROVIDERS_GCP`, kết nối kỹ năng quản trị project/IAM/VPC với Compute Engine, GKE, Cloud Run, lưu trữ, cơ sở dữ liệu, tự động hóa phát hành, độ tin cậy và chi phí.

**Phạm vi ví dụ:** GKE dùng **managed Cloud Service Mesh với Istio APIs và Envoy sidecars**. Cloud Service Mesh còn hỗ trợ Google Cloud APIs, Envoy/proxyless gRPC và một số môi trường khác; cấu hình của những mô hình đó **không thể sao chép nguyên** từ tài nguyên `security.istio.io` trong bài.

## Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt **control plane** và **data plane**, Istio APIs và Google Cloud APIs.
2. Giải thích mTLS, workload identity, trust domain và cơ chế cấp/luân chuyển chứng chỉ.
3. Phân biệt `PeerAuthentication`, `AuthorizationPolicy`, `RequestAuthentication` với IAM, NetworkPolicy và gateway.
4. Thực hiện lộ trình **PERMISSIVE → STRICT mTLS → least-privilege authorization** có kiểm thử.
5. Viết chính sách chỉ cho `checkout-sa` gọi các endpoint cần thiết của `orders-api`.
6. Kiểm tra sidecar, lỗi `403`/`503`, traffic logs và khôi phục thay đổi chính sách.
7. Đánh giá giới hạn, độ tin cậy và chi phí của mesh trước khi đưa vào production.

## 1. Service mesh giải quyết vấn đề nào?

Giả sử có ba Kubernetes Services trong namespace `commerce`:

| Dịch vụ | Kubernetes ServiceAccount (KSA) | Luồng nghiệp vụ |
| --- | --- | --- |
| `checkout` | `checkout-sa` | Nhận đơn, gọi `orders-api` |
| `orders-api` | `orders-sa` | Xử lý đơn, gọi `payments` |
| `payments` | `payments-sa` | Xử lý thanh toán |

Yêu cầu bảo mật: **chỉ `checkout-sa` được gọi endpoint tạo/đọc đơn hàng**; một Pod `reporting` không được phép gọi `orders-api` chỉ vì đang ở cùng VPC/namespace.

~~~mermaid
flowchart LR
    C["checkout Pod<br/>KSA: checkout-sa"]
    CP["Envoy sidecar"]
    OP["Envoy sidecar"]
    O["orders-api Pod<br/>KSA: orders-sa"]
    P["payments"]
    U["Pod không được phép"]
    M["Managed control plane<br/>policy + identity + config"]
    C --> CP
    CP -->|"mTLS"| OP
    OP --> O --> P
    U -. "Chặn theo policy" .-> OP
    M -. "xDS/policy/chứng chỉ" .-> CP
    M -. "xDS/policy/chứng chỉ" .-> OP
~~~

Trong mô hình sidecar, **Envoy** đứng cạnh container ứng dụng và xử lý các kết nối được chuyển hướng qua proxy. Policy được áp dụng tại proxy đích; ứng dụng Java thường không cần tự quản lý chứng chỉ mTLS. Nhưng mesh **không tự biến ứng dụng sai phân quyền thành an toàn**: business authorization, IAM Google APIs, network isolation và quản trị secrets vẫn cần thiết.

## 2. Control plane, data plane và lựa chọn triển khai

| Thành phần | Trách nhiệm |
| --- | --- |
| **Control plane** | Phân phối cấu hình proxy, service discovery, routing, security policies và thông tin chứng chỉ |
| **Data plane** | Envoy sidecars xử lý luồng request thực; thực thi mTLS, policy, routing và ghi telemetry |
| **Certificate authority (CA)** | Cấp chứng chỉ workload ngắn hạn; có thể dùng Mesh CA hoặc CA Service theo cấu hình hỗ trợ |
| **Fleet** | Quản lý membership và managed mesh cho các GKE clusters trong phạm vi được hỗ trợ |
| **Istio APIs** | Các Kubernetes CRDs như `PeerAuthentication`, `AuthorizationPolicy`, `VirtualService` |
| **Google Cloud APIs** | Một đường cấu hình CSM khác; dùng các resources/API tương ứng, không thay bằng Istio CRDs tùy ý |

Đối với **GKE trên Google Cloud**, tài liệu hiện hành khuyến nghị **managed Cloud Service Mesh**: Google quản lý phần control plane và các thành phần data plane được hỗ trợ. Với người dùng mới trên GKE, managed control plane sử dụng triển khai dựa trên **Traffic Director** và hỗ trợ Istio APIs. Một số fleet cũ dùng control plane `ISTIOD` có lộ trình hiện đại hóa; **không mặc định mọi cluster có cùng bản điều khiển**.

**Điểm cần nhớ:** thuật ngữ “Traffic Director” trong `implementation` không có nghĩa bạn phải bỏ Istio APIs trong cấu hình GKE được hướng dẫn ở đây. Ngược lại, các ví dụ Google Cloud Service Routing/Network Security APIs hoặc proxyless gRPC thuộc đường cấu hình khác, cần tài liệu và feature matrix riêng.

## 3. Ba lớp danh tính và xác thực không được nhầm lẫn

| Lớp | Công nghệ | Trả lời |
| --- | --- | --- |
| **Peer authentication** | Chứng chỉ **mTLS** của workload | Dịch vụ đang gọi có danh tính nào? |
| **End-user/request authentication** | JWT/OIDC khi cấu hình `RequestAuthentication` | Request mang token của người dùng/client nào? |
| **Authorization** | `AuthorizationPolicy` | Danh tính đó được gọi workload/path/method nào? |
| **Google Cloud resource IAM** | IAM và Workload Identity Federation for GKE | Pod có quyền đọc Cloud Storage/Secret Manager/BigQuery không? |

Một KSA như `checkout-sa` có thể được ánh xạ tới danh tính workload để mesh nhận biết. Cloud Service Mesh sử dụng trust domain và chứng chỉ, thường có dạng SPIFFE:

~~~text
spiffe://PROJECT_ID.svc.id.goog/ns/commerce/sa/checkout-sa
~~~

Trong trường `source.principals` của Istio AuthorizationPolicy, dạng thông dụng **không có tiền tố `spiffe://`**:

~~~text
PROJECT_ID.svc.id.goog/ns/commerce/sa/checkout-sa
~~~

**Thay `PROJECT_ID` bằng trust domain thật** lấy từ cấu hình mesh; không tự giả định `cluster.local` hoặc Google IAM service account email là danh tính mTLS. In-cluster mesh dùng Citadel CA có thể dùng trust domain khác. Với multi-cluster, phải đối chiếu root of trust, trust domain và membership.

## 4. mTLS: mã hóa giao tiếp chưa đồng nghĩa có phân quyền

Với mTLS, **cả client và server** xuất trình chứng chỉ để xác thực lẫn nhau; kênh được mã hóa. Mesh quản lý cấp/luân chuyển chứng chỉ theo cơ chế CA đã chọn.

| Chế độ `PeerAuthentication.mtls.mode` | Hành vi |
| --- | --- |
| `PERMISSIVE` | Cho phép cả plaintext và mTLS; hữu ích trong giai đoạn di chuyển |
| `STRICT` | Chỉ chấp nhận mTLS ở workload/port áp dụng |
| `UNSET` | Kế thừa policy cấp trên |
| `DISABLE` | **Không được hỗ trợ** trong `PeerAuthentication` của managed Traffic Director; không dùng làm mẫu cho managed CSM |

**Auto mTLS** có thể được bật mặc định, nhưng client proxy có thể gửi **plaintext tới workload chưa có sidecar**, và server ở chế độ PERMISSIVE vẫn chấp nhận plaintext. Vì vậy “đã bật mesh” **không đồng nghĩa toàn bộ giao tiếp đã bắt buộc mTLS**.

### 4.1. Chỉ enforce STRICT cho orders-api trước

Khi các callers hợp lệ đã có sidecar và luồng health/probe/gateway đã được thử, áp dụng chính sách tại workload:

~~~yaml
apiVersion: security.istio.io/v1beta1
kind: PeerAuthentication
metadata:
  name: orders-strict
  namespace: commerce
spec:
  selector:
    matchLabels:
      app: orders-api
  mtls:
    mode: STRICT
~~~

Chỉ các Pods có label `app: orders-api` trong namespace này chịu policy trên. Khi rollout toàn bộ namespace, có thể tạo policy **không có selector**, nằm trong namespace `commerce`. Khi enforce **toàn mesh**, đặt policy không selector trong root namespace `istio-system` theo hướng dẫn CSM; không áp dụng toàn cluster ngay từ lần thử đầu.

**Cẩn trọng:** callers không đi qua sidecar, probes hoặc các gateway chưa được cấu hình tương thích có thể bị lỗi sau khi chuyển STRICT. Cần kiểm chứng tác động trước thay đổi production.

## 5. AuthorizationPolicy: ai được gọi endpoint nào?

`PeerAuthentication` bảo đảm danh tính peer và mã hóa; nó **không giới hạn** rằng chỉ checkout được gọi orders. `AuthorizationPolicy` mới quy định danh tính, HTTP method/path hoặc port nào được phép.

Ví dụ chỉ cho KSA `checkout-sa` gọi `GET` và `POST` tới API đơn hàng:

~~~yaml
apiVersion: security.istio.io/v1beta1
kind: AuthorizationPolicy
metadata:
  name: orders-from-checkout
  namespace: commerce
spec:
  selector:
    matchLabels:
      app: orders-api
  action: ALLOW
  rules:
    - from:
        - source:
            principals:
              - "PROJECT_ID.svc.id.goog/ns/commerce/sa/checkout-sa"
      to:
        - operation:
            methods: ["GET", "POST"]
            paths: ["/api/orders", "/api/orders/*"]
~~~

**Điều kiện để mẫu có tác dụng như mong đợi:**

- `PROJECT_ID.svc.id.goog` phải đúng trust domain của source workload.
- Callers cần dùng mTLS để proxy có thể xác định `source.principal`.
- Backend Pod có label `app: orders-api` và traffic đi qua proxy.
- API phải được nhận diện đúng giao thức HTTP; với TCP không thể dùng HTTP path/method như điều kiện chung.
- Không được có **ALLOW policy rộng khác** cũng match workload và cho phép nguồn không mong muốn.

Trong Istio authorization, **DENY được đánh giá ưu tiên trước ALLOW**; nếu có ALLOW policies áp dụng, request phải match ít nhất một ALLOW. Không có ALLOW policy nào thì hành vi mặc định thường là cho phép, trừ khi DENY policy hoặc cơ chế khác chặn.

### 5.1. Default deny có thể gây ngừng dịch vụ

Để chặn mặc định mọi request đến các workloads trong namespace `commerce`, có thể tạo policy `action: ALLOW` **không có rules**:

~~~yaml
apiVersion: security.istio.io/v1beta1
kind: AuthorizationPolicy
metadata:
  name: default-deny
  namespace: commerce
spec:
  action: ALLOW
~~~

Policy này **không tự ghi đè những ALLOW policies hẹp khác**. Nó khiến những request không được ALLOW bởi policy khác bị từ chối. **Không triển khai trước khi liệt kê đầy đủ** luồng đến checkout, orders, payments, gateway, health checks và service agents; nếu không, ứng dụng có thể dừng nhận request.

### 5.2. Vì sao không dùng `ALLOW rules: [{}]`?

Trong AuthorizationPolicy, `rules: [{}]` với `action: ALLOW` là rule **khớp mọi request**, có thể vô tình mở rộng truy cập. **`rules` vắng mặt/rỗng** lại có ý nghĩa *allow nothing*. Phân biệt hai trường hợp này khi review YAML hoặc Helm templates.

### 5.3. Quy tắc theo workload thay vì namespace

`selector.matchLabels` gắn chính sách với Pods được chọn. Một policy không có selector có thể áp dụng toàn namespace. Thiết kế nên dùng **KSA riêng từng dịch vụ**, nhãn ổn định, quy trình GitOps và kiểm tra đối tượng policy thực sự chọn; tránh phụ thuộc nhãn `app` chung cho nhiều workloads.

## 6. JWT người dùng khác chứng chỉ workload

Giả sử người dùng gọi API qua gateway và mang JWT. `RequestAuthentication` có thể xác minh **issuer, JWKS, audience** của token theo cấu hình được hỗ trợ:

~~~yaml
apiVersion: security.istio.io/v1beta1
kind: RequestAuthentication
metadata:
  name: orders-jwt
  namespace: commerce
spec:
  selector:
    matchLabels:
      app: orders-api
  jwtRules:
    - issuer: "https://issuer.example.com/"
      jwksUri: "https://issuer.example.com/.well-known/jwks.json"
      audiences: ["orders-api"]
~~~

**Đây là mẫu minh họa:** các URL không đại diện identity provider thật. Quan trọng hơn, **RequestAuthentication một mình không bắt buộc mọi request phải có JWT**: request không mang token có thể vẫn đi tiếp. Muốn yêu cầu JWT, thêm AuthorizationPolicy giới hạn `requestPrincipals: ["*"]` và các đường được phép; kết hợp với mTLS principal nếu cần cả **danh tính dịch vụ lẫn danh tính người dùng**.

Đừng dùng JWT do client tự cung cấp để thay cho workload mTLS trong giao tiếp nội bộ, hoặc coi mTLS giữa services là bằng chứng người dùng cuối được phép thực hiện nghiệp vụ.

## 7. Chuẩn bị GKE cluster và namespace an toàn

Phần sau giả định **managed Cloud Service Mesh đã được cấp phát**, GKE cluster có phiên bản được hỗ trợ, tham gia **fleet**, Workload Identity Federation for GKE được cấu hình theo yêu cầu và tài khoản có quyền xem mesh/Kubernetes resources. **Không dùng các lệnh đổi policy trên production trước khi được phê duyệt.**

### 7.1. Kiểm tra read-only

~~~bash
gcloud container fleet memberships list \
  --project=FLEET_PROJECT_ID

gcloud container fleet mesh describe \
  --project=FLEET_PROJECT_ID

kubectl config current-context
kubectl get namespace commerce --show-labels
kubectl get pods -n commerce
kubectl get peerauthentication,authorizationpolicy,requestauthentication -n commerce
~~~

Trong output của fleet mesh, xem **`controlPlaneManagement.state`**, **`dataPlaneManagement.state`** và **`implementation`**. `ACTIVE` cho biết trạng thái managed components, **không đủ để khẳng định từng Pod đã có sidecar**.

### 7.2. Bật sidecar injection theo control plane

Với managed Cloud Service Mesh **Traffic Director implementation** dùng Istio APIs, tài liệu GKE hướng dẫn nhãn mặc định:

~~~bash
kubectl label namespace commerce \
  istio.io/rev- istio-injection=enabled --overwrite
~~~

Lệnh trên **thay đổi namespace**; cần kiểm tra control plane, migration plan và labels hiện có trước. Với những control plane/release channel khác, revision label có thể khác; không gán bừa `istio.io/rev=asm-managed` cho mọi cluster.

Injection chỉ xảy ra khi **Pod mới được tạo**. Với ứng dụng đã tồn tại, thực hiện rollout có kiểm soát (ví dụ trên Deployment cụ thể):

~~~bash
kubectl rollout restart deployment/orders-api -n commerce
kubectl rollout status deployment/orders-api -n commerce
~~~

Kiểm tra container sidecar:

~~~bash
kubectl get pods -n commerce \
  -o jsonpath='{range .items[*]}{.metadata.name}{"\t"}{.spec.containers[*].name}{"\n"}{end}'
~~~

Pod của `orders-api` phải có container ứng dụng và `istio-proxy` trong mô hình Envoy sidecar. Nếu chưa có, dừng bước mTLS STRICT và xem injection webhook, namespace labels, Pod annotations, policy, phiên bản control plane.

**Đừng áp dụng `rollout restart` lên tất cả deployments** khi chưa kiểm soát PodDisruptionBudget, readiness và capacity.

## 8. Lab: thử allow và deny giữa hai service accounts

**Giả định:** namespace `commerce` thuộc managed CSM, sidecars hoạt động; `orders-api.commerce.svc.cluster.local:8080` là Kubernetes Service có endpoint HTTP `GET /api/orders` trả `200` khi không bị policy chặn. Đường dẫn/port cần thay theo app thực.

### 8.1. Hai client identities

Dùng hai ServiceAccounts **trong namespace lab**; nếu tên đã được ứng dụng sử dụng, không tạo trùng ở production:

~~~yaml
apiVersion: v1
kind: ServiceAccount
metadata:
  name: checkout-sa
  namespace: commerce
---
apiVersion: v1
kind: ServiceAccount
metadata:
  name: untrusted-sa
  namespace: commerce
---
apiVersion: v1
kind: Pod
metadata:
  name: test-allowed
  namespace: commerce
spec:
  serviceAccountName: checkout-sa
  containers:
    - name: curl
      image: curlimages/curl:8.12.1
      command: ["sleep", "3600"]
---
apiVersion: v1
kind: Pod
metadata:
  name: test-denied
  namespace: commerce
spec:
  serviceAccountName: untrusted-sa
  containers:
    - name: curl
      image: curlimages/curl:8.12.1
      command: ["sleep", "3600"]
~~~

Ví dụ sử dụng image công khai để thử curl; trong môi trường hạn chế egress, dùng **digest/image từ Artifact Registry được tổ chức phê duyệt**. Khởi tạo các Pod thử sau khi injection đã bật. Xác nhận cả hai đều có `istio-proxy`, Ready và nhận được chứng chỉ/identity.

### 8.2. Áp dụng policy ở phạm vi hẹp

1. Xác minh `PeerAuthentication` ở mục 4 chỉ áp dụng cho `orders-api`.
2. Xác minh không có ALLOW policy rộng khác cho backend.
3. Thay `PROJECT_ID` trong `orders-from-checkout` bằng **trust domain thật**.
4. Apply YAML ở môi trường lab theo quyền được phép; chờ proxy nhận cập nhật.
5. Chạy từ **cả hai client Pods**:

~~~bash
kubectl exec -n commerce test-allowed -c curl -- \
  curl -sS -o /dev/null -w '%{http_code}\n' \
  http://orders-api.commerce.svc.cluster.local:8080/api/orders

kubectl exec -n commerce test-denied -c curl -- \
  curl -sS -o /dev/null -w '%{http_code}\n' \
  http://orders-api.commerce.svc.cluster.local:8080/api/orders
~~~

**Kết quả kỳ vọng:** client `checkout-sa` được policy ALLOW và thấy HTTP `200` nếu ứng dụng trả 200; `untrusted-sa` bị từ chối, thường `403` ở proxy. Nếu request được phép trả `404` hoặc `500`, cần tách lỗi ứng dụng khỏi mesh authorization. Một Pod không sidecar có thể không hoàn tất mTLS handshake (lỗi kết nối) chứ không nhất thiết nhận HTTP 403.

### 8.3. Kiểm tra thêm luồng âm tính

| Thử nghiệm | Kỳ vọng khi policy ở mục 5 đúng |
| --- | --- |
| `checkout-sa` gọi `GET /api/orders` | Cho phép nếu application hợp lệ |
| `untrusted-sa` gọi endpoint trên | Từ chối |
| `checkout-sa` gọi `DELETE /api/orders/123` | Từ chối vì method không được ALLOW |
| Pod không có sidecar gọi `orders-api` có STRICT mTLS | Không tạo được kết nối plaintext hợp lệ |
| Client hợp lệ nhưng app xử lý lỗi | Có thể trả 4xx/5xx từ app; không đồng nghĩa lỗi mTLS |

Trong production, đừng dùng `200` duy nhất làm bằng chứng bảo mật. Xác minh **mTLS peer identity**, policy match và logs; sau đó thử cả luồng không được phép.

### 8.4. Dọn lab có chủ đích

Xóa hai **Pod thử** và KSA `untrusted-sa` khi không còn sử dụng. **Không xóa `checkout-sa`** nếu là identity của ứng dụng đang chạy. Với policies, chỉ rollback những tài nguyên vừa được tạo cho lab khi đã hiểu tác động tới luồng bảo mật còn lại.

## 9. Gateway, egress và những luồng không tự được mesh bảo vệ

| Luồng | Cần kiểm soát |
| --- | --- |
| Client Internet → ứng dụng | HTTPS/TLS tại load balancer/ingress gateway, Cloud Armor khi phù hợp, authentication và authorization của API |
| Gateway → backend trong mesh | mTLS/identity và AuthorizationPolicy cho **danh tính gateway** nếu được phép |
| Service A → Service B trong mesh | PeerAuthentication STRICT + AuthorizationPolicy least privilege |
| Pod → Google APIs | IAM/Workload Identity Federation, VPC egress và VPC Service Controls nếu cần |
| Pod → hệ thống ngoài | Egress gateway/proxy, DNS, firewall, NetworkPolicy và controls theo đích |
| Cloud Run ↔ GKE mesh | Tích hợp/route theo tính năng CSM được hỗ trợ; không tự coi Cloud Run là Pod có sidecar |

**Một ingress gateway không tự bảo vệ toàn bộ Internet ingress**. Ngoài mTLS trong mesh, phải xử lý TLS từ client, xác thực người dùng, WAF/rate limiting, policy gateway và rủi ro request không qua gateway.

Cần xem **port exceptions, hostNetwork Pods, bypass từ traffic không được sidecar intercept, endpoints ngoài mesh** và các giới hạn của managed CSM. Service mesh không thay thế **Kubernetes NetworkPolicy**, GKE Dataplane V2 hoặc VPC firewall; dùng network segmentation để ngăn đường bypass không mong muốn.

## 10. Quan sát mTLS, policy denies và độ tin cậy

Cloud Service Mesh tích hợp Cloud Logging, Cloud Monitoring và Cloud Trace theo khả năng tính năng/cấu hình. Trên GKE managed mesh, **traffic logs** thường được bật mặc định; **Envoy access logs** là loại riêng và không nhất thiết được bật.

Các tín hiệu cần xem:

| Tín hiệu | Giúp trả lời |
| --- | --- |
| Request rate, p95/p99 latency, 4xx/5xx | Mesh policy có gây lỗi hoặc tăng trễ không? |
| mTLS authentication policy và source principal | Đúng workload đang gọi đúng endpoint không? |
| Authorization denials | Deny hợp lệ hay lỡ chặn traffic nghiệp vụ? |
| Envoy proxy readiness/config sync | Sidecar có nhận cấu hình và chứng chỉ không? |
| Pod CPU/memory, restart | Proxy overhead ảnh hưởng autoscaling/capacity thế nào? |
| Cloud Trace request spans | Call chain nào phát sinh độ trễ? |
| Cloud Billing logs/metrics | Telemetry có tăng chi phí không? |

Ví dụ xem policy và logs bằng quyền chỉ đọc:

~~~bash
kubectl get peerauthentication,authorizationpolicy,requestauthentication -A

# Log container Envoy (chỉ có request access logs nếu cấu hình bật)
kubectl logs -n commerce deployment/orders-api \
  -c istio-proxy --tail=100
~~~

Trong **Logs Explorer**, tìm **server/client traffic logs** của Cloud Service Mesh theo cluster/service; log names và resource labels cần xác minh với cấu hình đang dùng. Ví dụ khởi đầu:

~~~text
logName="projects/PROJECT_ID/logs/server-accesslog-stackdriver"
resource.labels.namespace_name="commerce"
~~~

Không in JWT, authorization headers hoặc dữ liệu cá nhân trong access logs. Log volume, sampling traces và metrics retention có thể phát sinh chi phí.

## 11. Triển khai policy không gây outage

1. **Inventory** luồng service-to-service: caller KSA, namespace, service/port, HTTP method/path, gateway, job định kỳ, health probes và external endpoints.
2. **Kiểm tra mesh readiness** trên từng cluster/namespace; Pod phải có sidecar và workload identity đúng.
3. **Di chuyển mTLS**: giữ PERMISSIVE trong giai đoạn chuyển đổi; áp STRICT ở workload thử, rồi namespace/toàn mesh khi đủ coverage.
4. **Thử authorization** bằng `AuthorizationPolicy` phạm vi hẹp; xác nhận allow và deny bằng client danh tính thật. Có thể dùng dry-run annotation khi phiên bản CSM hỗ trợ và đã kiểm tra telemetry.
5. **Thu hẹp quyền** theo KSA + operation; tránh ALLOW mọi principal/path để chữa lỗi.
6. **Duyệt thay đổi qua GitOps/IaC**, đo latency, 403/503, mesh telemetry, health của Java apps và impact lên rollout.
7. **Chuẩn bị rollback**: lưu manifest cũ, danh sách policy vừa thêm, chủ sở hữu và tiêu chí hoàn nguyên.
8. **Mở rộng theo namespace/cluster** khi các SLO đạt và chưa có luồng hợp lệ bị chặn.

Một thay đổi `PeerAuthentication` hoặc `AuthorizationPolicy` có thể **ảnh hưởng ngay traffic production** khi control plane phân phối cấu hình; không coi YAML là bước không có rủi ro.

### 11.1. Thứ tự rollback khi phát sinh lỗi

- Xác định request bị chặn ở **TLS handshake**, **AuthorizationPolicy** hay **ứng dụng**.
- Chỉ hoàn nguyên policy/canary vừa thay đổi, không xóa toàn bộ bảo vệ mesh.
- Giữ lại các chính sách đã xác minh cho luồng nghiệp vụ khác.
- Sau rollback, xác nhận lại các negative tests để không vô tình mở quyền rộng.

## 12. Troubleshooting: 403, 503, TLS và không có sidecar

| Triệu chứng | Nguyên nhân thường gặp | Cách kiểm tra |
| --- | --- | --- |
| HTTP `403` từ Envoy | Không match ALLOW, match DENY, JWT hoặc principal sai | AuthorizationPolicy, traffic logs, trust domain, labels |
| Kết nối bị reset/SSL error sau STRICT | Caller chưa có sidecar hoặc TLS mode không tương thích | Pod injection, PeerAuthentication, DestinationRule |
| HTTP `503`, `no healthy upstream` | Endpoint thiếu, Envoy chưa sync, pod readiness fail | Service/endpoints, proxy readiness, health checks |
| Một Pod không có `istio-proxy` | Namespace label sai, injection bị tắt hoặc pod cũ | `kubectl get ns --show-labels`, rollout status |
| Policy không có tác dụng | Selector không match, traffic bypass proxy, config chưa phân phối | Pod labels, CRD status, logs/xDS |
| HTTP method/path bị deny ngoài ý muốn | Policy không cho phép health, gRPC path khác hoặc route rewrite | Route thực tế, logs, policy operations |
| Mesh TLS hoạt động nhưng Google API `403` | IAM/Workload Identity thiếu quyền | GKE KSA-to-IAM, policy resource, audit logs |
| JWT được xác minh nhưng request anonymous vẫn qua | Chỉ tạo RequestAuthentication, chưa yêu cầu JWT bằng AuthorizationPolicy | `requestPrincipals`, hiệu lực các ALLOW |
| Proxy CPU/memory tăng, Pod restart | Sidecar overhead, resource limits thấp | Per-container metrics, node pressure |
| External call không chịu mesh policy | Bypass sidecar, egress gateway chưa cấu hình | VPC routes, NetworkPolicy, ServiceEntry/gateway |

**Không chẩn đoán mọi `403` là lỗi IAM**: mesh authorization, API application, gateway và Google IAM đều có thể trả từ chối. Đối chiếu response headers, caller, proxy/access logs và thời điểm đổi policy.

## 13. Bài toán chi phí và giới hạn

Mesh thêm **Envoy sidecars** (CPU/memory), tài nguyên mạng, hoạt động quản lý chứng chỉ, telemetry và có thể là phí dịch vụ theo gói/edition. Trong GKE có autoscaling, sidecar requests/limits ảnh hưởng đến số Pods mà node chứa được; điều này có thể tăng node count và bill.

Tối ưu theo ba nguyên tắc:

- Đưa vào mesh **những workload cần kiểm soát service-to-service rõ ràng**, tránh tự ép mọi Pod utility vào mesh nếu không phù hợp.
- Đo overhead **latency, CPU, memory và log volume** trước/sau; cân bằng log retention với nhu cầu điều tra.
- Kiểm tra **giá Cloud Service Mesh/GKE/Observability** và hạn chế tính năng theo managed control plane đang dùng. Không suy ra mọi Istio feature từ upstream đều hỗ trợ đầy đủ.

**Mesh không phải phương án thay thế kiến trúc HA**: cần readiness/liveness, PodDisruptionBudget, multi-zone capacity, load balancing, backup, IAM và SLO riêng cho ứng dụng.

## 14. Tình huống tổng hợp: bảo vệ checkout → orders → payments

**Yêu cầu:** `checkout` được tạo đơn; `orders-api` được gọi `payments`; `reporting` chỉ đọc dữ liệu tổng hợp từ một API riêng; mọi luồng nội bộ bắt buộc mTLS và mặc định từ chối những caller ngoài danh sách.

Thiết kế:

| Cặp giao tiếp | Kiểm soát |
| --- | --- |
| `checkout-sa` → `orders-api` | mTLS STRICT + ALLOW theo principal/method/path |
| `orders-sa` → `payments` | Một ALLOW policy riêng ở payments cho orders-sa |
| `reporting-sa` → `orders-api` | Không có ALLOW phù hợp, bị từ chối |
| Ingress gateway → `checkout` | Gateway TLS, xác thực client và policy cấp ingress phù hợp |
| `orders-api` → Cloud SQL/Storage | IAM/Workload Identity và đường mạng an toàn, **không** dùng AuthorizationPolicy thay IAM |

Triển khai theo **một workload/namespace canary**, kiểm thử positive/negative, sau đó mới áp dụng default-deny và STRICT rộng hơn. Ghi nhận metrics `403/503`, latency và resource overhead trước/sau để chứng minh vừa bảo mật vừa đáp ứng SLO.

## 15. Bài tập tự kiểm tra

**Câu 1.** Một client có network access đến `orders-api` nghĩa là được quyền gọi API không?

*Đáp án:* Không. Network access và service authorization khác nhau; dùng AuthorizationPolicy theo danh tính và operation.

**Câu 2.** Đã bật auto mTLS thì có thể khẳng định mọi request nội bộ đều mã hóa không?

*Đáp án:* Không. PERMISSIVE và callers không sidecar có thể dùng plaintext; cần kế hoạch chuyển STRICT.

**Câu 3.** mTLS xác thực `checkout-sa` có tự chứng minh người dùng cuối được phép đặt hàng?

*Đáp án:* Không. Peer identity khác end-user JWT và business authorization.

**Câu 4.** Tại sao RequestAuthentication chưa bắt buộc JWT?

*Đáp án:* Nó xác minh JWT được gửi đến, nhưng cần AuthorizationPolicy như `requestPrincipals: ["*"]` để từ chối request không mang JWT.

**Câu 5.** `principals` cần là email Google IAM SA hay SPIFFE-based trust domain?

*Đáp án:* Dùng principal của mesh, ví dụ `PROJECT_ID.svc.id.goog/ns/commerce/sa/checkout-sa` theo CA/trust domain cấu hình; không mặc định dùng email IAM.

**Câu 6.** Một namespace default-deny ALLOW policy không có rules khác gì ALLOW policy với `rules: [{}]`?

*Đáp án:* Không rules → không match request; rule trống `{}` → match tất cả request.

**Câu 7.** Chỉ bật STRICT cho orders rồi thấy client không sidecar lỗi. Vì sao?

*Đáp án:* Backend chỉ chấp nhận mTLS, client ngoài mesh đang gửi plaintext; cần onboarding/thiết kế gateway phù hợp.

**Câu 8.** `403` khi gọi BigQuery từ Pod đang có mesh có nhất thiết do AuthorizationPolicy?

*Đáp án:* Không. Có thể do IAM, Workload Identity, VPC SC hoặc API; kiểm tra logs theo lớp.

**Câu 9.** Tại sao `kubectl label namespace ... istio-injection=enabled` chưa làm tất cả Pod hiện hữu có sidecar ngay?

*Đáp án:* Injection áp dụng khi Pod được tạo; cần rollout từng Deployment và kiểm tra Pod mới.

**Câu 10.** Mesh có thay thế VPC firewall/NetworkPolicy và Cloud Armor không?

*Đáp án:* Không. Mesh kiểm soát luồng đã đi qua data plane; network/edge controls chặn đường bypass và bảo vệ Internet ingress.

## 16. Checklist trước production

- [ ] Chọn đúng managed control plane, Istio/Google Cloud API model và feature support.
- [ ] Fleet/cluster/namespace ở trạng thái phù hợp; workload Pod có sidecar và đúng KSA.
- [ ] Biết trust domain và CA; không giả định principal là IAM email.
- [ ] Đã kiểm thử mTLS STRICT ở workload canary, bao gồm health/gateway/legacy callers.
- [ ] AuthorizationPolicy scoped theo workload, principal, method/path/port và tránh allow-all.
- [ ] Có policy riêng cho gateway, jobs, service agents và luồng ngoài mesh.
- [ ] JWT khi cần end-user auth; RequestAuthentication đi cùng chính sách yêu cầu token.
- [ ] IAM, VPC, NetworkPolicy, Cloud Armor/ingress bảo vệ các lớp còn lại.
- [ ] Đã thử client được phép/bị chặn và đo logs/latency/CPU/memory.
- [ ] Có GitOps review, rollback manifest, SLO alerts và người xử lý sự cố.
- [ ] Đã dự báo chi phí data plane, telemetry và GKE capacity.
- [ ] Rà soát policy sau mỗi thay đổi KSA, service label, gateway hoặc topology.

## 17. Kết luận

**Cloud Service Mesh bảo vệ giao tiếp dịch vụ bằng ba trụ cột: nhận diện workload, mTLS và ủy quyền theo policy.** Auto mTLS giúp chuyển đổi, nhưng **STRICT + AuthorizationPolicy ít quyền** mới thể hiện rõ biên bảo mật nội bộ. Các ví dụ dùng Istio APIs dành cho mô hình GKE managed mesh tương thích; khi triển khai thật phải xác minh control plane, trust domain, feature support và các luồng đặc biệt trước khi enforce.

## Tài liệu tham khảo chính thức

- [Cloud Service Mesh overview](https://cloud.google.com/service-mesh/docs/overview)
- [Provision managed control plane on GKE](https://cloud.google.com/service-mesh/docs/onboarding/provision-control-plane)
- [Cloud Service Mesh security overview](https://cloud.google.com/service-mesh/docs/security/security-overview)
- [Configure transport security and STRICT mTLS](https://cloud.google.com/service-mesh/docs/security/configuring-mtls)
- [AuthorizationPolicy overview](https://cloud.google.com/service-mesh/docs/security/authorization-policy-overview)
- [Supported Istio APIs for managed Cloud Service Mesh](https://cloud.google.com/service-mesh/docs/onboarding/api-support)
- [Cloud Service Mesh security best practices](https://cloud.google.com/service-mesh/docs/security/anthos-service-mesh-security-best-practices)
- [Request proxy traffic logs](https://cloud.google.com/service-mesh/docs/observability/access-logs)
- [Cloud Service Mesh pricing](https://cloud.google.com/service-mesh/pricing)

