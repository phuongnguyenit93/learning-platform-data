# Cấu hình client từ môi trường, file cấu hình và thông tin trong Pod

## 1. Client cần những thông tin nào?

Một Kubernetes client không thể gọi API server chỉ bằng tên namespace. Nó cần ghép nhiều mảnh cấu hình:

- Địa chỉ API server và cổng kết nối.
- Cơ chế xác thực, thường là token hoặc thông tin từ kubeconfig.
- CA hoặc trust configuration để xác minh máy chủ TLS.
- Namespace mặc định khi thư viện cần phạm vi namespaced.
- Chính sách timeout, proxy, retry và watch.
- Cách đọc lại token hoặc chứng thư khi chúng được thay mới.

Trong ứng dụng Spring Cloud Kubernetes, các mảnh này thường được client Java và lớp auto-configuration thu thập từ một trong ba nguồn:

1. **Kubeconfig hoặc file cấu hình bên ngoài**, thường dùng khi chạy local hoặc ngoài cluster.
2. **Biến môi trường và property của ứng dụng**, dùng để truyền endpoint, namespace hoặc tùy chọn client.
3. **Thông tin được cấp trong Pod**, gồm địa chỉ API server, CA, token ServiceAccount và namespace hiện tại.

Luồng khái quát:

```text
Spring Cloud Kubernetes
        |
        v
Kubernetes client configuration
        |
        +-- property/environment
        +-- kubeconfig
        '-- in-cluster service account
        |
        v
API server qua TLS
```

Mục tiêu không phải là ép mọi môi trường dùng cùng một file. Mục tiêu là xác định nguồn cấu hình được phép, thứ tự ưu tiên của thư viện đang dùng và cách bảo vệ dữ liệu xác thực.

## 2. Chạy ngoài cluster: kubeconfig và property

Khi chạy ứng dụng trên máy lập trình viên, container local hoặc một máy CI, tiến trình thường không có volume ServiceAccount của Pod. Client có thể dùng kubeconfig do người dùng chỉ định hoặc kubeconfig ở vị trí mặc định của công cụ Kubernetes.

Một kubeconfig thường mô tả:

- Một hoặc nhiều cluster với server URL và CA.
- User hoặc credential để xác thực.
- Context ghép cluster, user và namespace.
- Context hiện tại.

Cấu trúc khái quát:

```yaml
apiVersion: v1
kind: Config
clusters:
  - name: dev-cluster
    cluster:
      server: https://api.dev.example
      certificate-authority-data: <base64-ca>
contexts:
  - name: dev-context
    context:
      cluster: dev-cluster
      user: dev-user
      namespace: shop
current-context: dev-context
users:
  - name: dev-user
    user:
      token: <credential>
```

Không commit kubeconfig chứa token hoặc certificate nhạy cảm vào repository. Không đưa kubeconfig quản trị vào image. Trong CI, dùng credential ngắn hạn và quyền tối thiểu; dọn file tạm sau job theo chính sách của hệ thống.

Các biến môi trường phổ biến trong hệ sinh thái client có thể chỉ đường dẫn kubeconfig hoặc chọn context, nhưng tên và precedence cụ thể phụ thuộc thư viện. Một số client cũng hỗ trợ property của Spring hoặc system property. Không giả định rằng mọi client đều đọc cùng một biến.

Ví dụ nguyên tắc cấu hình theo profile:

```yaml
spring:
  config:
    activate:
      on-profile: local
  cloud:
    kubernetes:
      discovery:
        enabled: false
```

Ví dụ này chỉ minh họa việc tắt discovery khi local; property chính xác và tên profile phải khớp release train của dự án. Nếu local cần thử discovery, hãy dùng kubeconfig có quyền tương đương production thay vì tài khoản quản trị cá nhân.

## 3. Chạy trong cluster: in-cluster configuration

Khi Pod chạy trong Kubernetes, client thường có thể dùng thông tin ServiceAccount được gắn cho Pod. Nền tảng cung cấp:

- Địa chỉ API server hoặc thông tin để client suy ra địa chỉ đó.
- CA của cluster qua volume được mount.
- Token của ServiceAccount.
- Namespace hiện tại qua file namespace được mount hoặc cấu hình tương ứng.

Một số môi trường cũng đưa các biến như `KUBERNETES_SERVICE_HOST` và `KUBERNETES_SERVICE_PORT` vào Pod. Đây là tín hiệu môi trường thường được client Kubernetes sử dụng để nhận biết API server nội bộ, nhưng không nên viết logic ứng dụng phụ thuộc cứng vào tên biến nếu thư viện đã có cơ chế in-cluster riêng.

Cấu hình Pod khái quát:

```yaml
apiVersion: v1
kind: Pod
metadata:
  name: order-service
  namespace: shop
spec:
  serviceAccountName: order-runtime
  containers:
    - name: app
      image: example/order-service:1.0
```

Việc có `serviceAccountName` chỉ thiết lập danh tính gắn với Pod. Nó không tự cấp quyền đọc Service, EndpointSlice, ConfigMap hoặc Secret. RBAC quyết định request nào được phép.

Client cần tin cậy CA khi kết nối TLS tới API server. Không tắt xác minh TLS để vượt qua lỗi chứng thư. Nếu ứng dụng không cần Kubernetes API, cân nhắc tắt tự gắn token cho Pod sau khi kiểm tra chắc chắn rằng không có thành phần nào trong Pod cần token.

## 4. Ba lớp: endpoint, xác thực và phạm vi

Khi lỗi client, tách ba lớp trước khi thay đổi cấu hình:

| Lớp | Câu hỏi | Dấu hiệu lỗi thường gặp |
|---|---|---|
| Endpoint/mạng | Có kết nối được tới API server không? | DNS, timeout, connection refused |
| TLS/xác thực | Client có xác minh server và trình bày credential hợp lệ không? | Chứng thư, `401 Unauthorized` |
| Phạm vi/RBAC | Danh tính có được phép thao tác không? | `403 Forbidden` |

Ví dụ:

- API URL sai thường không được sửa bằng cách thêm Role.
- Token hợp lệ nhưng thiếu RoleBinding vẫn nhận `403`.
- CA sai có thể làm TLS fail trước khi RBAC được đánh giá.
- Kết nối thành công không chứng minh tài nguyên yêu cầu tồn tại trong namespace đúng.

Sơ đồ điều tra:

```text
Không gọi được Kubernetes API
    |
    +-- Không mở được kết nối? -> URL, DNS, mạng, proxy, timeout
    +-- TLS fail?              -> server URL, CA, hostname verification
    +-- 401?                  -> token/credential và thời hạn
    +-- 403?                  -> ServiceAccount, Role, RoleBinding, namespace
    '-- Gọi được nhưng dữ liệu sai? -> resource, selector, cache, filter
```

Cách tách lớp này đặc biệt quan trọng khi Spring Cloud Kubernetes khởi động trong Pod. Một bean được tạo thành công chỉ chứng minh cấu hình ứng dụng đủ để tạo bean; request đầu tiên mới cho biết endpoint, TLS và quyền có hoạt động.

## 5. Namespace được xác định như thế nào?

Nhiều tài nguyên Kubernetes có phạm vi namespace. Client có thể nhận namespace từ:

- Property hoặc biến môi trường của ứng dụng.
- Context trong kubeconfig khi chạy ngoài cluster.
- File namespace được mount vào Pod.
- Giá trị mặc định của thư viện hoặc namespace được cấu hình trong integration.

Không nên giả định namespace của process Windows/Linux hay thư mục làm việc là namespace Kubernetes. Cũng không nên dựa vào namespace mặc định nếu ứng dụng cần đọc dữ liệu ở namespace cụ thể.

Một thiết kế rõ ràng khai báo namespace theo profile hoặc manifest:

```yaml
spring:
  cloud:
    kubernetes:
      discovery:
        namespace: shop
```

Tên property chỉ là ví dụ theo cách đặt cấu hình của từng dòng. Hãy kiểm tra property metadata và tài liệu đúng phiên bản. Nếu integration hỗ trợ nhiều namespace, cần đánh giá lại RBAC: Role trong một namespace không tự cho phép đọc namespace khác.

Bảng tình huống:

| Môi trường | Nguồn namespace nên kiểm tra | Rủi ro |
|---|---|---|
| Local | kubeconfig context hoặc property profile | Context cá nhân có thể trỏ nhầm cluster |
| CI | property/secret của job và kubeconfig tạm | Credential có thể quá rộng |
| Pod trong `shop` | file namespace, manifest và property | Client đọc nhầm namespace mặc định |
| Nhiều namespace | cấu hình integration và binding tương ứng | Vô tình cấp ClusterRoleBinding |

Khi discovery không trả dữ liệu, namespace sai là một nguyên nhân phổ biến bên cạnh selector, endpoint và RBAC.

## 6. Biến môi trường và property Spring

Biến môi trường phù hợp để truyền giá trị triển khai không nhạy cảm hoặc credential được quản lý bởi nền tảng. Spring Boot có thể ánh xạ nhiều biến sang property theo quy tắc relaxed binding, nhưng property cụ thể của Spring Cloud Kubernetes vẫn phụ thuộc phiên bản.

Ví dụ khái quát:

```yaml
env:
  - name: SPRING_CLOUD_KUBERNETES_DISCOVERY_ENABLED
    value: "true"
  - name: SPRING_CLOUD_KUBERNETES_DISCOVERY_NAMESPACE
    value: "shop"
```

Các nguyên tắc:

- Ghi rõ biến nào là của Spring Boot, biến nào là của Kubernetes client.
- Không giả định biến `KUBERNETES_...` và `SPRING_CLOUD_...` có cùng ý nghĩa.
- Kiểm tra giá trị sau khi binding mà không log Secret.
- Dùng profile cho khác biệt local/cluster, tránh sửa image.
- Không đưa token trực tiếp vào `Deployment` dạng plaintext nếu có cơ chế Secret hoặc ServiceAccount phù hợp.

Property có thể override file cấu hình, environment hoặc command-line tùy thứ tự PropertySource của Spring Boot. Với các property nhạy cảm, điều quan trọng là biết nguồn nào có precedence cao nhất trong ứng dụng cụ thể. Không đặt cùng một endpoint ở nhiều nguồn mà không ghi lại quy tắc ưu tiên.

Ví dụ kiểm tra an toàn:

```text
Log:
  kubernetes.client.endpoint.configured=true
  kubernetes.namespace=shop
  kubernetes.token.present=true

Không log:
  token đầy đủ
  certificate key
  nội dung Secret
  toàn bộ Environment
```

## 7. Token, CA và vòng đời credential trong Pod

ServiceAccount token là credential. Client phải dùng nó theo cách không làm lộ dữ liệu và có thể thích ứng với vòng đời token.

Cần quan tâm:

- Token được mount ở đâu và client đọc từ đâu?
- Token có được thay mới trong quá trình Pod chạy không?
- Client mở file một lần hay đọc lại khi request mới?
- CA có được thay đổi khi cluster thay chứng thư không?
- Log exception có in header Authorization hoặc đường dẫn nhạy cảm không?
- Khi token hết hạn, ứng dụng retry, refresh hay cần restart?

Không tự copy token từ một Pod vào image hoặc ConfigMap. Không lưu token trong repository. Không đưa token vào query string.

Khi client hỗ trợ token rotation, giữ cấu hình mặc định phù hợp và kiểm thử việc thay token trong môi trường an toàn. Nếu thư viện cũ chỉ đọc token một lần, đây là giới hạn vận hành cần biết trước khi triển khai dài ngày. Không kết luận client có hỗ trợ rotation chỉ vì token được mount dưới dạng file.

CA và token phục vụ hai mục đích khác:

```text
CA
  -> xác minh API server là máy chủ tin cậy

Token/credential
  -> xác định client là ai
  -> RBAC quyết định được làm gì
```

Có CA đúng nhưng token không hợp lệ vẫn nhận lỗi xác thực. Có token đúng nhưng CA sai vẫn không thiết lập được TLS.

## 8. Kubeconfig không phải cấu hình in-cluster

Kubeconfig và in-cluster configuration phục vụ hai bối cảnh khác nhau:

| Đặc điểm | Kubeconfig | In-cluster |
|---|---|---|
| Môi trường chính | Local, CI, ngoài cluster | Pod đang chạy trong cluster |
| Endpoint | Trường `server` trong cluster entry | Service/API endpoint được cluster cung cấp |
| Credential | User, exec plugin, certificate hoặc token | ServiceAccount token |
| Namespace | Context hoặc property | File namespace/property/giá trị integration |
| Rủi ro | Dùng nhầm context hoặc quyền quá rộng | Binding sai hoặc token bị lộ |
| Kiểm tra | Context hiện tại và file credential | serviceAccountName, volume, RBAC |

Không đưa kubeconfig local vào Pod như cách “sửa nhanh” lỗi in-cluster. Làm vậy có thể bỏ qua ServiceAccount, tạo credential quá rộng và khiến hành vi Pod khác production. Hãy sửa cơ chế in-cluster hoặc cấp property cần thiết qua secret/configuration được quản lý đúng.

Ngược lại, khi local dùng kubeconfig quản trị, việc discovery thành công chưa chứng minh Pod production có quyền tương ứng. Phải kiểm thử bằng ServiceAccount và Role thực tế hoặc một danh tính có phạm vi tương đương.

## 9. Cấu hình client trong Spring Cloud Kubernetes

Các integration Spring Cloud Kubernetes thường nhận cấu hình qua Spring Environment. Một số nhóm property có thể liên quan:

```yaml
spring:
  cloud:
    kubernetes:
      client:
        namespace: shop
      discovery:
        enabled: true
      config:
        enabled: true
```

Tên nhóm, property và cơ chế phát hiện in-cluster có thể thay đổi giữa các release. Hãy xem property metadata của dependency đã chọn, Condition Evaluation Report và log startup để biết property nào thực sự được bind.

Khi cấu hình discovery và config cùng lúc, đừng giả định chúng dùng đúng cùng một namespace hoặc cùng một client bean. Kiểm tra:

- Discovery đang đọc Service/EndpointSlice nào?
- Config đang đọc ConfigMap/Secret nào?
- Hai capability có dùng cùng ServiceAccount không?
- Quyền cần thiết có bị gộp rộng hơn mức cần thiết không?
- Có property nào bị profile cluster override bởi environment không?

Một ứng dụng có thể dùng DNS cho discovery nghiệp vụ nhưng vẫn dùng ConfigMap qua API. Khi đó không cần cấp quyền discovery chỉ vì đã bật config integration.

## 10. Proxy, timeout và retry

API server có thể nằm sau proxy hoặc mạng private. Client cần cấu hình proxy, connect timeout, read timeout và backoff theo môi trường. Không dùng timeout cực dài cho request khởi động nếu điều đó làm readiness treo vô hạn.

Nguyên tắc:

- Connect timeout giới hạn thời gian mở kết nối.
- Read timeout giới hạn thời gian chờ phản hồi.
- Backoff giảm retry dồn dập khi API server hoặc mạng gặp sự cố.
- Jitter giúp nhiều Pod không retry cùng một thời điểm.
- Retry request đọc thường an toàn hơn retry thao tác ghi, nhưng vẫn cần giới hạn.
- Watch cần cơ chế nối lại và đồng bộ lại cache khi phiên bản resource không còn phù hợp.

Không dùng retry để che URL sai, CA sai hoặc `403`. Retry liên tục trong các lỗi cấu hình cố định chỉ làm log và tải tăng.

Khi Spring Cloud Kubernetes dùng client để discovery hoặc watch, đánh giá tải tổng thể:

```text
Số Pod
  x số watch/list
  x tần suất reconnect
  x retry khi lỗi
  -> tải lên API server và mạng
```

Cache và watch có thể giảm polling, nhưng không xóa nhu cầu timeout, backoff và quan sát.

## 11. Luồng cấu hình theo môi trường

Một cách tổ chức rõ ràng:

```text
Profile local
  -> kubeconfig/context được chỉ định
  -> namespace dev
  -> quyền giới hạn cho developer/test

Profile cluster
  -> in-cluster ServiceAccount
  -> namespace từ manifest hoặc property đã kiểm soát
  -> Role/RoleBinding production
```

Không nhúng credential vào image. Không dùng cùng một file cấu hình chứa token cho local, CI và production. Đặt các giá trị môi trường-specific ở lớp triển khai, Secret manager hoặc cơ chế credential phù hợp.

Ví dụ manifest truyền một property không nhạy cảm:

```yaml
env:
  - name: SPRING_CLOUD_KUBERNETES_DISCOVERY_NAMESPACE
    valueFrom:
      fieldRef:
        fieldPath: metadata.namespace
```

Cách dùng Downward API có thể giúp Pod lấy namespace của chính mình mà không cần hard-code. Tuy nhiên, property mapping phải khớp với integration đang dùng. Không suy luận rằng mọi client tự đọc biến này nếu chưa kiểm tra binding.

## 12. Kiểm tra khi client không khởi động

Khi ứng dụng fail startup, thu thập theo lớp:

1. Dependency và auto-configuration có đúng họ client không?
2. Property đã bind đúng tên và profile chưa?
3. Ứng dụng có đang nhận nhầm kubeconfig hoặc context không?
4. Trong Pod, `serviceAccountName` là gì?
5. API endpoint có phân giải và kết nối được không?
6. CA có được đọc đúng và TLS hostname có khớp không?
7. Token có hiện diện, hợp lệ và không hết hạn không?
8. Role/RoleBinding có cho phép request đầu tiên không?
9. Namespace và resource có đúng không?
10. Timeout hoặc retry có làm startup kéo dài không?

Bảng chẩn đoán:

| Biểu hiện | Nên kiểm tra |
|---|---|
| Không tìm thấy kubeconfig khi local | Đường dẫn, context, profile và quyền đọc file |
| Trong Pod nhưng client dùng local config | Cấu hình override, biến môi trường, classpath resource |
| Connection refused/timeout | Endpoint, DNS, network policy, proxy, API server |
| TLS handshake fail | CA, server URL, hostname verification |
| `401 Unauthorized` | Token, credential source, thời hạn |
| `403 Forbidden` | ServiceAccount, RoleBinding, resource, verb, namespace |
| Discovery rỗng | Service, EndpointSlice, filter, namespace, cache |
| Config không thấy | ConfigMap/Secret name, label, namespace, RBAC |
| Startup treo lâu | Timeout, retry, phụ thuộc từ xa trong startup |

Không xóa TLS verification hoặc cấp `cluster-admin` để làm lỗi biến mất. Cần sửa đúng lớp gây lỗi và giữ nguyên ranh giới bảo mật.

## 13. Cấu hình không nên bị ghi đè ngoài ý muốn

Spring có nhiều nguồn property: file, profile, environment, command-line và nguồn động. Khi Kubernetes client không kết nối được, đôi khi nguyên nhân không phải API server mà là property bị override.

Một checklist nhỏ:

- In tên profile đang hoạt động.
- Kiểm tra endpoint đã được chọn nhưng che credential.
- Kiểm tra namespace sau binding.
- Kiểm tra cờ discovery/config đã bật chưa.
- Ghi nguồn property nếu framework hỗ trợ mà không in giá trị Secret.
- Tránh đặt cùng property ở ConfigMap, biến môi trường và command-line nếu không có lý do.
- Đọc Condition Evaluation Report để biết auto-configuration nhìn thấy điều gì.

Nếu dùng ConfigMap để cấu hình chính Kubernetes client, cần nghĩ về vòng đời: client phải kết nối để đọc ConfigMap, nhưng cấu hình kết nối ban đầu lại phụ thuộc ConfigMap. Những giá trị bootstrap như API server, CA hoặc credential không nên tạo vòng phụ thuộc mà ứng dụng không thể phá vỡ khi khởi động.

## 14. Checklist triển khai

Trước khi đưa Spring Cloud Kubernetes lên cluster:

- Đã xác định chạy local bằng kubeconfig hay chạy Pod bằng in-cluster config?
- Kubeconfig local/CI có context và quyền tối thiểu không?
- Pod có `serviceAccountName` riêng không?
- CA và token được cấp qua cơ chế an toàn không?
- Client có hỗ trợ cách token/CA được thay mới trong môi trường không?
- Endpoint, namespace và property có cùng một nguồn rõ ràng không?
- Có phân biệt `401`, `403`, TLS và timeout không?
- Role có đúng resource/verb của discovery hoặc config integration không?
- Secret có bị log hoặc đưa vào biến plaintext ngoài ý muốn không?
- Timeout, backoff và watch reconnect có giới hạn không?
- Liveness/readiness có tránh phụ thuộc quá chặt vào API server không?
- Local test có đang dùng quyền rộng hơn production không?
- Có log/metric đủ để biết nguồn cấu hình mà không lộ credential không?

Cấu hình Kubernetes client là bài toán về nguồn dữ liệu và vòng đời, không chỉ là điền một URL. Khi tách rõ kubeconfig, property, thông tin in-cluster, TLS, token và RBAC, ứng dụng Spring Cloud Kubernetes sẽ dễ khởi động đúng trong từng môi trường, dễ chẩn đoán khi lỗi và tránh mang credential hoặc quyền thừa từ local vào production.
