# Phân biệt lỗi mạng, lỗi xác thực và lỗi thiếu quyền

Khi ứng dụng Spring gọi Kubernetes API không thành công, việc nhìn thấy một exception chung như connection refused hoặc access denied chưa đủ để biết cần sửa ở đâu. Lỗi có thể xảy ra trước khi request tới API server, trong quá trình TLS handshake, khi API server xác minh danh tính, hoặc sau khi danh tính đã được xác minh nhưng RBAC từ chối thao tác.

Phân biệt đúng lớp lỗi giúp tránh các cách sửa sai: tăng quyền khi DNS đang hỏng, retry vô hạn khi token hết hạn, tắt TLS verification khi CA sai, hoặc mở network policy khi ServiceAccount chỉ thiếu verb get. Với Spring Cloud Kubernetes, cùng một ứng dụng có thể gặp các lớp lỗi khác nhau khi discovery, ConfigMap/Secret integration hoặc watcher dùng các đường gọi riêng.

Bài học thuộc chương **Kết nối Kubernetes API** của module **SPRING_CLOUD_KUBERNETES**. Mục tiêu là lần theo đường đi của request, nhận diện lỗi mạng, lỗi TLS, lỗi authentication, lỗi authorization và các lỗi API liên quan; sau đó chọn kiểm tra và cách khắc phục phù hợp.

## 1. Đường đi của một request tới Kubernetes API

Một request từ Pod tới Kubernetes API server thường đi qua các lớp:

~~~text
Ứng dụng Spring
      |
      v
Kubernetes client
      |
      v
DNS / hostname
      |
      v
Route, proxy, NetworkPolicy, TCP
      |
      v
TLS handshake và CA/hostname verification
      |
      v
HTTP request với credential
      |
      v
API server xác minh authentication
      |
      v
RBAC và admission kiểm tra authorization
      |
      v
API group/resource/version xử lý request
      |
      v
Response hoặc event trả về client
~~~

Mỗi lớp có dấu hiệu khác nhau:

| Lớp | Câu hỏi | Dấu hiệu thường gặp |
| --- | --- | --- |
| DNS | Hostname có phân giải được không? | UnknownHost, NXDOMAIN, resolver timeout |
| Route/TCP | Có mở được kết nối tới host/port không? | Connection refused, timeout, reset |
| TLS | Client có tin và xác minh server không? | Certificate unknown, hostname mismatch, handshake failure |
| Authentication | API server có nhận diện credential không? | HTTP 401 Unauthorized |
| Authorization | Danh tính có được phép thao tác không? | HTTP 403 Forbidden |
| API semantics | Resource/path/version/schema có đúng không? | 404, 405, 409, 410, 422 |
| Throttling/server | API server có giới hạn hoặc lỗi không? | 429, 5xx |

Không phải mọi exception đều giữ nguyên HTTP status. Nếu lỗi xảy ra trước khi có HTTP response, client thường chỉ trả về lỗi transport hoặc TLS. Khi có status code, hãy dùng nó cùng request path, resource, verb và danh tính để chẩn đoán.

## 2. Phân biệt không kết nối được và bị từ chối

Hai thông báo có chữ “connection” nhưng nguyên nhân khác nhau:

- Connection refused: host/port đã reachable ở mức TCP nhưng không có tiến trình chấp nhận kết nối hoặc kết nối bị từ chối trên đường đi.
- Connection timeout: không nhận được phản hồi TCP trong thời gian giới hạn; có thể do route, NetworkPolicy, firewall, proxy hoặc server quá tải.
- Connection reset: kết nối đã mở nhưng bị peer hoặc thiết bị trung gian đóng đột ngột.
- Unknown host: DNS không phân giải được hostname.
- HTTP 401/403: request đã đi đủ xa để nhận HTTP response từ API server hoặc proxy có thể trả response.

Một lỗi DNS không thể sửa bằng cách cấp Role. Một lỗi 403 không thể sửa bằng cách tăng connection pool. Hãy xác định request đã tới HTTP layer chưa trước khi thay đổi cấu hình quyền.

Bảng tóm tắt:

| Quan sát | Request đã tới API server chưa? | Hướng kiểm tra đầu tiên |
| --- | --- | --- |
| Unknown host | Chưa | DNS, hostname, search domain |
| TCP timeout | Chưa chắc | Route, NetworkPolicy, firewall, proxy |
| TLS handshake failure | Đã tới endpoint nhưng chưa có HTTP request hoàn chỉnh | CA, hostname, SNI, thời gian hệ thống |
| 401 Unauthorized | Có HTTP response | Token, credential provider, thời hạn |
| 403 Forbidden | Có HTTP response và đã nhận diện danh tính | Role, RoleBinding, resource, verb, namespace |
| 404 Not Found | Có HTTP response | API path, group/version, resource, namespace |
| 429 Too Many Requests | Có HTTP response | Throttling, retry-after, request rate |
| 5xx | Có HTTP response hoặc proxy response | API server, proxy, outage, load |

## 3. Lỗi DNS và hostname

Kubernetes client cần biết hostname hoặc địa chỉ API server. Trong môi trường in-cluster, client có thể dùng địa chỉ được cung cấp qua environment hoặc cấu hình của thư viện. Nếu hostname sai, request chưa thể tới TLS hoặc authentication.

Nguyên nhân thường gặp:

- Dùng tên Service sai namespace.
- Dùng hậu tố cluster domain không đúng môi trường.
- Cấu hình proxy thay đổi DNS path.
- Pod dùng DNS policy khác mặc định.
- CoreDNS hoặc resolver đang lỗi.
- Hostname API server chỉ có thể phân giải từ một network segment.
- Giá trị environment bị override bởi profile hoặc command line.

DNS và Service discovery nghiệp vụ cũng cần phân biệt. Hostname catalog-api dùng để gọi Service ứng dụng không phải hostname Kubernetes API server. Một ứng dụng có thể gọi catalog-api được nhưng không gọi được API server, hoặc ngược lại.

Khi chẩn đoán từ Pod, hãy dùng một công cụ có sẵn trong image hoặc ephemeral diagnostic container theo policy của platform. Kiểm tra hostname và port trước; không cần gửi Secret để kiểm tra DNS.

Kết quả cần diễn giải:

- Hostname phân giải thành địa chỉ: chỉ xác nhận DNS.
- TCP mở được: chỉ xác nhận route/port ở mức transport.
- TLS thành công: chỉ xác nhận endpoint và trust chain.
- HTTP 401/403: đã đi tới lớp API access.

Không nên kết luận “DNS hoạt động” chỉ vì một hostname khác trong cluster phân giải được. API server, Service nghiệp vụ và external endpoint có thể dùng resolver path hoặc policy khác.

## 4. Lỗi TCP, route và NetworkPolicy

Sau DNS là kết nối tới host và port. Lỗi ở lớp này thường không có HTTP status:

~~~text
DNS thành công
    |
    v
TCP SYN không có phản hồi -> timeout
TCP RST ngay lập tức -> refused/reset
TCP handshake thành công
    |
    v
TLS hoặc HTTP mới bắt đầu
~~~

Nguyên nhân có thể gồm:

- NetworkPolicy chặn egress từ namespace hoặc Pod.
- Egress gateway hoặc proxy yêu cầu cấu hình riêng.
- Firewall chặn port API server.
- Route từ node tới control plane bị lỗi.
- API server endpoint không lắng nghe trên địa chỉ được cấu hình.
- Proxy đóng connection idle hoặc giới hạn request.
- API server quá tải và không accept nhanh.

NetworkPolicy không cấp quyền Kubernetes API. Nó chỉ quyết định traffic có được đi qua network path hay không. Có egress tới API server vẫn chưa có nghĩa ServiceAccount được phép get ConfigMap.

Khi network policy được áp dụng theo label, hãy kiểm tra label của Pod thực tế và namespace selector. Không mở rộng egress toàn cluster nếu chỉ cần tới một API endpoint. Nếu cluster dùng private endpoint hoặc proxy, ghi rõ route mong đợi trong deployment contract.

Timeout nên có giới hạn. Timeout quá ngắn làm retry tăng; timeout quá dài giữ connection và thread khi API server không reachable. Cần phối hợp connect timeout, read timeout, retry budget và termination grace period.

## 5. Lỗi TLS và chứng thư

Nếu TCP thành công nhưng TLS handshake thất bại, HTTP request chưa được gửi hoặc chưa được API server xử lý. Các lỗi thường gặp:

- Client không trust CA của API server.
- CA file không được mount hoặc path sai.
- Hostname trong certificate không khớp hostname client dùng.
- Proxy thay certificate nhưng CA proxy chưa được trust.
- SNI không đúng do endpoint hoặc proxy configuration.
- Đồng hồ hệ thống sai làm certificate chưa valid hoặc đã hết hạn.
- TLS protocol/cipher không tương thích policy của server.
- Client giữ SSL context cũ sau CA rotation.

Không nên đặt trust-all hoặc tắt hostname verification để làm lỗi biến mất. Cách đó có thể biến lỗi kết nối thành lỗ hổng giả mạo API server. Hãy kiểm tra CA chain, hostname, proxy, thời gian hệ thống và cấu hình client.

Kubernetes client có thể lấy CA từ projected volume, kubeconfig hoặc cấu hình application. Khi file CA được cập nhật, process có thể không tự reload. Khả năng reload phụ thuộc thư viện và transport. Nếu không hỗ trợ reload, cần restart hoặc recreate client theo lifecycle an toàn.

Dấu hiệu phân biệt:

| Dấu hiệu | Có thể chỉ ra |
| --- | --- |
| Unknown CA | Truststore/CA bundle thiếu |
| Certificate expired | Chứng thư hoặc đồng hồ hệ thống |
| Hostname mismatch | Dùng endpoint không nằm trong SAN |
| Connection closed during handshake | Proxy, TLS policy hoặc server |
| HTTP 401/403 | TLS đã đủ để gửi HTTP request |

## 6. Authentication: API server nhận diện ai?

Authentication trả lời câu hỏi “request đến từ danh tính nào?”. Credential có thể là ServiceAccount token, kubeconfig credential, client certificate, OIDC hoặc provider khác tùy cluster.

Nếu credential không hợp lệ hoặc không được gửi, API server thường trả 401 Unauthorized. Nguyên nhân gồm:

- Token không có, sai path hoặc không được đọc.
- Token hết hạn.
- Client không reload projected token sau rotation.
- Kubeconfig dùng context sai.
- Certificate client hết hạn.
- OIDC provider không chấp nhận token.
- Proxy loại bỏ Authorization header.
- Clock skew làm token bị coi là chưa valid hoặc hết hạn.
- Application dùng nhầm credential của môi trường khác.

401 khác 403:

- 401: API server chưa nhận diện được danh tính hợp lệ.
- 403: danh tính đã được nhận diện nhưng không được phép thực hiện thao tác.

Không nên giải quyết 401 bằng cách thêm RoleBinding. RoleBinding chỉ có tác dụng sau khi authentication thành công. Ngược lại, thay token khi lỗi là 403 sẽ không sửa được quyền nếu token vẫn là cùng ServiceAccount.

Khi log lỗi authentication, chỉ ghi status, resource an toàn, namespace và request id. Không ghi token, Authorization header, nội dung kubeconfig hoặc private key.

## 7. Authorization và RBAC: danh tính được phép làm gì?

Authorization trả lời “danh tính đã xác thực được phép làm thao tác nào trên resource nào trong phạm vi nào?”. Kubernetes RBAC thường xét:

- Subject: ServiceAccount, user hoặc group.
- Verb: get, list, watch, create, update, patch, delete.
- Resource: configmaps, secrets, services, endpointslices và resource khác.
- API group.
- Namespace.
- Resource name trong một số rule.

Ví dụ, một ứng dụng đọc ConfigMap đã biết tên:

~~~yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: order-config-reader
  namespace: shop
rules:
  - apiGroups: [""]
    resources: ["configmaps"]
    resourceNames: ["order-settings"]
    verbs: ["get"]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  name: order-config-reader
  namespace: shop
subjects:
  - kind: ServiceAccount
    name: order-api
    namespace: shop
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: Role
  name: order-config-reader
~~~

Pod phải dùng đúng ServiceAccount:

~~~yaml
spec:
  serviceAccountName: order-api
~~~

Nếu Pod không khai báo serviceAccountName, nó có thể dùng ServiceAccount mặc định của namespace. RoleBinding cho order-api sẽ không áp dụng cho Pod đang dùng default.

Một ứng dụng discovery hoặc informer có thể cần list/watch thay vì chỉ get. Một client đọc Secret cần resource secrets, không phải configmaps. Một client đọc EndpointSlice cần đúng API group/resource của EndpointSlice. Quyền phải được suy ra từ request thực tế.

## 8. Namespace sai cũng có thể tạo 403 hoặc 404

Namespace là một phần của request path và RBAC scope. Các tình huống có thể xảy ra:

- Resource tồn tại ở namespace shop nhưng client gọi namespace default.
- ServiceAccount ở namespace A không tự có Role ở namespace B.
- RoleBinding ở namespace B trỏ tới subject sai namespace.
- ClusterRoleBinding cấp quyền rộng nhưng client vẫn gọi sai resource name.
- ConfigMap được tạo ở staging nhưng Pod đang chạy production namespace.
- Profile đặt namespace khác với Downward API.

Lỗi có thể là 404 nếu resource không tồn tại trong namespace được gọi, hoặc 403 nếu danh tính không được phép list/get tại namespace đó. Hãy ghi cả namespace thực tế trong log an toàn và kiểm tra nó từ Pod metadata hoặc configuration đã chọn.

Không nên cho phép namespace đến từ input HTTP của người dùng rồi dùng thẳng trong Kubernetes client. Nếu platform cần nhiều namespace, dùng allowlist và RBAC được review.

## 9. API path, group/version và resource not found

Sau authentication và authorization, request có thể thất bại vì API path hoặc version:

- Dùng core API path cho resource thuộc API group.
- Client gọi version không được serve.
- Resource bị disable hoặc chưa cài.
- CRD/operator chưa tồn tại.
- Subresource như status hoặc scale không được gọi đúng path.
- Client dùng tên plural/singular sai.
- Resource tồn tại nhưng không ở namespace đó.

404 không luôn có nghĩa “object không tồn tại”. Có thể API group/version không được serve. Cần xem response body, path và API discovery.

Một preflight tối thiểu nên kiểm tra group/version/resource cần dùng thay vì list toàn bộ cluster:

~~~text
API server version
API group/version
Resource discovery
Namespace scope
Resource name nếu cần
~~~

Nếu client đọc Service và EndpointSlice, kiểm tra cả hai resource. Nếu client chỉ gọi Service DNS, không cần đọc EndpointSlice chỉ để xác nhận HTTP path nghiệp vụ.

## 10. 401, 403 và 404 trong một bảng chẩn đoán

| Status | Ý nghĩa chính | Kiểm tra | Không nên làm |
| --- | --- | --- | --- |
| 401 | Credential không được chấp nhận | Token, cert, provider, expiry, proxy header | Thêm RoleBinding |
| 403 | Danh tính hợp lệ nhưng thiếu quyền | ServiceAccount, Role, RoleBinding, verb/resource/namespace | Cấp cluster-admin ngay |
| 404 | Path/resource/version không tồn tại trong ngữ cảnh gọi | API discovery, group/version, namespace, name | Đổi token ngẫu nhiên |
| 405 | Method không được hỗ trợ ở path | Verb và endpoint đúng | Retry cùng request |
| 409 | Conflict hoặc object state thay đổi | resourceVersion, optimistic concurrency | Ghi đè mù |
| 410 | ResourceVersion/watch quá cũ | List lại và watch từ version mới | Retry cùng watch vô hạn |
| 422 | Schema/validation không chấp nhận | Body, CRD schema, admission | Bỏ validation |
| 429 | Bị throttling | Request rate, Retry-After, quota | Tăng retry tức thời |
| 5xx | Lỗi server/proxy hoặc quá tải | API server, proxy, platform status | Retry vô hạn |

Status code phải được đọc cùng request. Một proxy có thể trả 401/403 trước khi API server nhận request, nên khi chẩn đoán OIDC hoặc gateway hãy xác định response đến từ đâu.

## 11. Spring Cloud Kubernetes và các đường gọi khác nhau

Một ứng dụng Spring có thể dùng nhiều đường kết nối:

| Tính năng | Đường gọi | Lỗi cần phân biệt |
| --- | --- | --- |
| Gọi Service nội bộ | DNS/Service tới application Pod | DNS, TCP, readiness, HTTP nghiệp vụ |
| Discovery trực tiếp | Kubernetes client tới API server | DNS/TLS/401/403/API discovery |
| ConfigMap/Secret qua API | Kubernetes client tới API server | Auth, RBAC, namespace, resource |
| ConfigMap/Secret qua env/volume | Kubelet inject vào Pod | Key/resource/Pod creation/reload |
| Configuration Watcher | Watcher tới API + signal tới app | Watcher RBAC, network, callback, refresh |
| Spring Cloud LoadBalancer | Client chọn endpoint rồi gọi | Discovery source, timeout, endpoint health |

Không nên sửa Kubernetes API RBAC khi lỗi thực tế là catalog-api HTTP 500. Không nên sửa Service selector khi DiscoveryClient nhận 403 từ API server. Tách các đường gọi giúp chọn đúng dữ liệu chẩn đoán.

Nếu một starter tạo client lúc startup, lỗi có thể xuất hiện trước khi Actuator readiness mở. Nếu integration là optional, ứng dụng có thể startup nhưng tính năng discovery/config không hoạt động. Hãy biết behavior được chọn trong profile và release train.

## 12. Quy trình chẩn đoán từ trong Pod

Khi Pod không truy cập được Kubernetes API, đi theo thứ tự từ lớp thấp đến lớp cao:

1. Xác định application profile và hostname API server đang dùng.
2. Kiểm tra DNS của hostname đó.
3. Kiểm tra route/TCP tới port API server.
4. Kiểm tra CA, hostname và TLS handshake.
5. Kiểm tra credential có tồn tại và còn hiệu lực, không in giá trị.
6. Gửi một request read tối thiểu với đúng identity của Pod.
7. Phân tích 401/403/404/429/5xx.
8. Kiểm tra API group/version/resource.
9. Kiểm tra cache/watch/retry nếu request cơ bản đã thành công.
10. Kiểm tra readiness và shutdown sau khi sửa.

Sơ đồ quyết định:

~~~text
Có HTTP response không?
  |
  +-- Không --> DNS -> TCP -> TLS
  |
  +-- Có
       |
       +-- 401 --> authentication
       +-- 403 --> RBAC/authorization
       +-- 404 --> path/version/namespace/resource
       +-- 429 --> throttling/backoff
       +-- 5xx --> API server/proxy/platform
       +-- 2xx --> kiểm tra response/schema/cache/watch
~~~

Thử nghiệm phải dùng đúng ServiceAccount, namespace, network policy và image của workload. Một lệnh chạy từ laptop với quyền admin chỉ kiểm tra cluster ở một góc nhìn khác.

## 13. Log và metric an toàn

Một log chẩn đoán hữu ích có thể chứa:

- Tên application.
- Pod name và namespace.
- API server host đã che hoặc hostname không nhạy cảm.
- API group/resource/verb.
- HTTP status.
- Request duration.
- Retry attempt và lý do backoff.
- Client library version.
- Request correlation id.

Không nên chứa:

- Token hoặc Authorization header.
- Private key, client certificate content.
- Secret value.
- Toàn bộ kubeconfig.
- URL có credential trong query.
- Body ConfigMap/Secret nếu chứa dữ liệu nhạy cảm.

Metric có thể tách theo status code, group, resource và verb với cardinality được kiểm soát. Không dùng resource name người dùng nhập làm label không giới hạn. Với 403, metric giúp biết lỗi tăng sau rollout; log an toàn giúp xác định namespace/verb; audit log platform giúp xác nhận request thực tế.

## 14. Retry đúng lớp lỗi

Retry chỉ phù hợp với lỗi tạm thời hoặc thao tác có thể lặp an toàn:

| Lỗi | Retry mặc định |
| --- | --- |
| DNS timeout tạm thời | Có backoff và giới hạn |
| Connection reset | Có thể, tùy request idempotent |
| TLS certificate error | Không; sửa cấu hình |
| 401 | Không lặp vô hạn; refresh credential nếu hỗ trợ |
| 403 | Không; sửa authorization |
| 404 API path sai | Không; sửa group/version/resource |
| 404 object tạm bị xóa | Tùy nghiệp vụ |
| 409 conflict | Đọc lại và xử lý concurrency |
| 410 watch cũ | List lại rồi watch mới |
| 429 | Retry theo backoff/Retry-After |
| 5xx | Có backoff, budget và circuit behavior |

Retry 403 làm tăng log và tải mà không thay đổi quyền. Retry TLS làm chậm failure và che certificate issue. Retry 404 API path không có ích. Retry 401 vô hạn có thể tạo vòng lặp khi token bị thu hồi.

Một client discovery nên có retry budget chung, tránh mỗi layer tự retry khiến một request thành nhiều chục request. Ghi rõ timeout của request, số retry, backoff và tổng thời gian cho phép.

## 15. Preflight kiểm tra kết nối

Một preflight cho workload có thể kiểm tra tối thiểu:

~~~text
1. DNS API server
2. TCP/TLS endpoint
3. Authentication bằng ServiceAccount thật
4. Authorization cho get resource cần thiết
5. API group/version/resource discovery
6. ConfigMap/Service/EndpointSlice cần dùng
7. Watch nếu tính năng production cần watch
~~~

Kết quả nên phân loại theo mã lỗi và dừng với thông báo có hành động cụ thể:

- NETWORK_UNREACHABLE
- TLS_UNTRUSTED
- AUTHENTICATION_FAILED
- AUTHORIZATION_DENIED
- API_RESOURCE_UNAVAILABLE
- API_THROTTLED
- API_SERVER_ERROR

Không nên cho preflight đọc toàn bộ Secret hoặc list toàn cluster chỉ để chứng minh kết nối. Chọn resource không nhạy cảm và verb nhỏ nhất. Nếu kiểm tra Secret là bắt buộc, chỉ xác nhận quyền và key metadata, không in giá trị.

Preflight có thể chạy trong startup nhưng phải cân nhắc readiness. Nếu API server tạm thời chậm, startup fail có thể tạo rollout storm. Dùng timeout, backoff và giới hạn replica khởi động đồng thời.

## 16. Ví dụ phân tích một lỗi 403

Giả sử ứng dụng nhận:

~~~text
HTTP 403 Forbidden
resource: configmaps
namespace: shop
verb: get
name: order-settings
~~~

Trình tự kiểm tra:

1. Pod đang dùng ServiceAccount nào?
2. ServiceAccount đó có RoleBinding trong namespace shop không?
3. Role có apiGroups core, resource configmaps, verb get không?
4. Nếu có resourceNames, tên có đúng order-settings không?
5. Ứng dụng có thực sự gọi namespace shop hay namespace khác không?
6. Có admission/proxy thay đổi request không?
7. Thành phần gọi API có phải ứng dụng hay watcher riêng không?

Không cần bắt đầu bằng ClusterRole. Nếu thiếu RoleBinding, sửa RoleBinding; nếu sai ServiceAccount trong Pod, sửa Deployment; nếu client gọi list/watch, cập nhật quyền theo thao tác thật và đánh giá phạm vi.

## 17. Ví dụ phân tích một lỗi TLS

Giả sử log có:

~~~text
SSLHandshakeException:
unable to find valid certification path
~~~

Trình tự kiểm tra:

1. Hostname API server thực tế.
2. Certificate chain server gửi.
3. CA file hoặc truststore client đang đọc.
4. Path mount và quyền đọc file.
5. Proxy có thay certificate không.
6. Thời gian hệ thống của node/container.
7. Client có giữ SSL context cũ sau CA rotation không.
8. Có cấu hình trust-all hoặc hostname verification bị tắt không.

Nếu CA file mount đúng nhưng process đã khởi tạo SSL context trước khi file được cập nhật, restart/reload lifecycle có thể cần thiết. Không nên sửa bằng cách chuyển sang HTTP hoặc bỏ verify.

## 18. Version và lỗi kết nối

Dependency mismatch có thể tạo lỗi giống lỗi kết nối. Ví dụ:

- Client mặc định dùng endpoint hoặc auth provider khác sau upgrade.
- Property cũ bị bỏ qua, dẫn tới hostname rỗng hoặc sai.
- HTTP transport đổi default proxy/timeout.
- Watch implementation đổi path hoặc resourceVersion.
- Model resource không hiểu field response.
- Spring auto-configuration bật client ngoài ý muốn.

Vì vậy, khi lỗi xuất hiện sau nâng dependency, so sánh:

- Active profile.
- Effective properties.
- API server host/port.
- Client library version.
- Request path/group/version.
- TLS settings.
- ServiceAccount.
- HTTP status hoặc exception ở lớp thấp nhất.

Không nên quy mọi lỗi sau upgrade cho RBAC. Một property bị đổi tên có thể làm client dùng endpoint sai, dẫn tới DNS/TLS lỗi trước khi RBAC được kiểm tra.

## 19. Checklist phân biệt lỗi

Trước khi sửa, hãy trả lời:

- Request có nhận HTTP response không?
- Hostname có phân giải được từ đúng Pod không?
- TCP có kết nối được tới đúng port không?
- TLS có verify được CA và hostname không?
- Credential nào đang được dùng?
- API server trả 401 hay 403?
- Request dùng ServiceAccount nào?
- Verb/resource/group/version/namespace là gì?
- Resource có được API discovery serve không?
- Lỗi có xuất hiện ở application, watcher hay discovery server?
- Retry có làm tải tăng không?
- Log/metric có lộ credential không?
- Sau khi sửa, bằng chứng nào xác nhận đúng lớp đã được khắc phục?

## 20. Tự kiểm tra

1. Vì sao lỗi 403 không được sửa bằng cách tăng connection pool?
2. Khác biệt giữa 401 Unauthorized và 403 Forbidden là gì?
3. Khi nào lỗi 404 là sai namespace và khi nào là API group/version không được serve?
4. Vì sao TCP kết nối thành công chưa chứng minh Kubernetes client hoạt động?
5. Những nguyên nhân nào gây TLS handshake failure?
6. Tại sao NetworkPolicy và RBAC giải quyết hai lớp khác nhau?
7. Nếu Pod dùng ServiceAccount mặc định, RoleBinding cho ServiceAccount riêng có tác dụng không?
8. Vì sao retry TLS hoặc 403 vô hạn là thiết kế nguy hiểm?
9. Preflight nên dùng quyền và identity nào để có giá trị đại diện?
10. Khi Spring Cloud Kubernetes discovery nhận 403, cần kiểm tra thành phần nào thực sự gọi API?
11. Làm thế nào kiểm tra Secret access mà không log Secret value?
12. Bằng chứng nào cho thấy lỗi đã được sửa ở đúng lớp thay vì chỉ hết tạm thời?

Một request Kubernetes API cần đi qua network, TLS, authentication, authorization và API semantics theo đúng thứ tự. Hãy phân loại lỗi từ lớp thấp đến lớp cao, dùng status code và request context để xác nhận, rồi sửa đúng DNS/route, CA, credential, RBAC hoặc API version. Với Spring Cloud Kubernetes, hiểu rõ đường gọi của discovery, config và watcher giúp chẩn đoán nhanh hơn mà không mở quyền hoặc retry vượt quá nhu cầu.

