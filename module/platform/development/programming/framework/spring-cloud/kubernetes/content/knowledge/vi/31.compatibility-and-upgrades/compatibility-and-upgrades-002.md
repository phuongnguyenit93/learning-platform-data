# Kiểm tra khả năng tương thích với phiên bản Kubernetes API

## Mục tiêu và tình huống thực tế

Một ứng dụng Spring Boot vẫn khởi động sau khi cluster Kubernetes được nâng cấp, nhưng `DiscoveryClient` trả danh sách rỗng, Configuration Watcher không còn nhận thay đổi hoặc client liên tục mở lại watch. Để kết luận có vấn đề tương thích, cần biết **ứng dụng gọi API nào, bằng client nào, với danh tính nào và hành vi mong đợi là gì**.

Trong module **SPRING_CLOUD_KUBERNETES**, phạm vi kiểm tra gồm discovery, đọc ConfigMap/Secret, Spring Cloud LoadBalancer, Configuration Watcher và các thao tác quan sát Pod mà ứng dụng thực sự bật. Không cần cấp quyền hoặc kiểm thử mọi resource Kubernetes cho một ứng dụng chỉ sử dụng một phần các tính năng này.

Sau bài học, bạn có thể:

- Phân biệt phiên bản cluster, phiên bản API resource và phiên bản Java client.
- Kiểm kê API mà cấu hình Spring Cloud Kubernetes đang sử dụng.
- Kiểm tra discovery của API server, quyền ServiceAccount và request thực tế.
- Phân biệt API bị loại bỏ với lỗi xác thực, RBAC, schema hoặc watch.
- Thiết lập bằng chứng đủ để quyết định triển khai lên cluster mục tiêu.

Các ví dụ lệnh dùng PowerShell và kubectl. Namespace `compat-lab`, ứng dụng gọi `catalog-client` và Service đích `catalog-api` là tên minh họa; thay chúng theo môi trường kiểm thử của bạn.

## 1. Phân biệt các lớp phiên bản

### 1.1. Phiên bản cluster không phải apiVersion của resource

`Kubernetes 1.x.y` là phiên bản phát hành của cluster. Trong khi đó, `v1`, `apps/v1` hoặc `discovery.k8s.io/v1` xác định phiên bản API của từng nhóm tài nguyên.

Ví dụ:

| Đối tượng | Giá trị cần hiểu |
| --- | --- |
| Cluster Kubernetes | Một bản phát hành có major/minor/patch cụ thể |
| `Service` | Core API group, version `v1` |
| `EndpointSlice` | Group `discovery.k8s.io`, version `v1` |
| `Deployment` | Group `apps`, version `v1` |
| `Role` | Group `rbac.authorization.k8s.io`, version `v1` |

Hai resource cùng có phần version là `v1` chưa chắc cùng API group. Với core group, trường `apiVersion` chỉ ghi `v1`; URL thường bắt đầu bằng `/api/v1`. Với named group, URL bắt đầu bằng `/apis/<group>/<version>`. Xem [tổng quan Kubernetes API](https://kubernetes.io/docs/reference/using-api/).

Do đó, đổi một thuộc tính cấu hình client thành `v1` không thể tự chuyển mọi lời gọi nội bộ sang API phù hợp. Cần kiểm tra group, version, resource và thao tác thật.

### 1.2. Phiên bản Java client là một lớp độc lập

Ứng dụng còn có các lớp:

~~~text
JDK + Spring Boot
        ↓
Spring Cloud release train / BOM
        ↓
Spring Cloud Kubernetes và các starter được chọn
        ↓
Fabric8 client hoặc Kubernetes Java Client
        ↓
HTTP request đến API group/version/resource cụ thể
        ↓
Kubernetes API server và chính sách của cluster
~~~

Build thành công chứng minh được một phần tương thích thư viện trong JVM. Nó chưa chứng minh API server còn phục vụ đường dẫn mà client sử dụng.

Ngược lại, `kubectl get services` thành công chưa chứng minh Java client đọc được EndpointSlice, giải mã response được và duy trì watch được.

### 1.3. Không áp dụng quy tắc version skew của kubectl cho mọi Java client

Kubernetes hỗ trợ kubectl trong phạm vi một minor version trước hoặc sau kube-apiserver, với giới hạn bổ sung khi các API server trong cluster HA khác phiên bản. Đây là quy tắc dành cho kubectl, không phải ma trận hỗ trợ chung cho thư viện Java. Xem [Version Skew Policy](https://kubernetes.io/releases/version-skew-policy/#kubectl).

Kubernetes Java Client có [ma trận Versioning and Compatibility riêng](https://github.com/kubernetes-client/java/wiki/2.-Versioning-and-Compatibility). Ma trận phân biệt tập API trùng khớp, phần API chỉ một phía có và tổ hợp không được bảo đảm. Khi nâng major client, cần đọc cả thay đổi API Java được sinh ra.

Fabric8 công bố chính sách tương thích trong [tài liệu của Kubernetes Client](https://github.com/fabric8io/kubernetes-client#compatibility). Đọc tài liệu phù hợp với phiên bản artifact đang dùng; tuyên bố của nhánh hiện tại không thay thế bằng chứng cho một artifact cũ.

## 2. Lập danh mục API theo tính năng thực sự bật

Trước tiên, ghi rõ implementation là Fabric8, Kubernetes Java Client hay HTTP DiscoveryClient đi qua DiscoveryServer. Nếu có DiscoveryServer hoặc Configuration Watcher triển khai riêng, chúng là những client Kubernetes cần kiểm tra độc lập.

Danh mục ban đầu có thể như sau:

| Tính năng | API/resource cần đối chiếu | Thao tác thường phải kiểm tra | Điều kiện phạm vi |
| --- | --- | --- | --- |
| Đọc ConfigMap qua API | Core `v1` / `configmaps` | get; có thể list tùy cách chọn nguồn | Tên nguồn, label, namespace |
| Đọc Secret qua API | Core `v1` / `secrets` | get; có thể list tùy cách chọn nguồn | Chỉ khi cơ chế đọc API được bật |
| Discovery dùng Endpoints | Core `v1` / `services`, `endpoints` | get/list/watch tùy implementation | Kiểm tra cấu hình hiệu lực |
| Discovery dùng EndpointSlice | `discovery.k8s.io/v1` / `endpointslices` và Service | get/list/watch tùy implementation | Cluster và client cùng hỗ trợ |
| Metadata hoặc sức khỏe Pod | Core `v1` / `pods` | get/list/watch theo tính năng | Không mặc định mọi ứng dụng đều cần |
| Configuration Watcher | ConfigMap/Secret và các resource phục vụ tìm ứng dụng đích | list/watch và đọc resource liên quan | Danh tính của watcher riêng |
| Leader election nếu có | ConfigMap hoặc Lease theo implementation | Đọc/cập nhật, có thể tạo hoặc watch | Không suy từ tên starter khác |
| Triển khai workload/RBAC | `apps/v1`, `rbac.authorization.k8s.io/v1`... | Thao tác của công cụ triển khai | Tách khỏi quyền runtime của ứng dụng |

Bảng là điểm bắt đầu để đối chiếu request, không phải manifest RBAC dùng chung. Ghi rõ scope namespace và selector bên cạnh từng hàng.

Các trường hợp cần tách biệt:

- **Mount ConfigMap/Secret vào volume:** ứng dụng có thể chỉ đọc file; khi đó request API để đồng bộ volume thuộc thành phần Kubernetes, không tự động thuộc Java process.
- **Đọc ConfigMap/Secret bằng Spring Cloud Kubernetes client:** chính danh tính của Pod cần quyền đọc API tương ứng.
- **Configuration Watcher:** nhận được sự kiện Kubernetes và gửi được yêu cầu refresh đến ứng dụng là hai chặng khác nhau.
- **LoadBalancer:** đường gọi phụ thuộc mode. Tài liệu nhánh 3.3 mô tả mode `POD` dựa vào DiscoveryClient và mode `SERVICE` dựa vào Service. Xem [LoadBalancer for Kubernetes](https://docs.spring.io/spring-cloud-kubernetes/reference/3.3/load-balancer.html).

Nếu ứng dụng dùng HTTP DiscoveryClient, lỗi API Kubernetes có thể nằm ở DiscoveryServer trong khi log phía ứng dụng chỉ ghi lỗi HTTP đến server đó.

## 3. Chụp cấu hình runtime trước khi đánh giá tương thích

Lập một hồ sơ kiểm tra thay vì ghi nhận chung chung “dùng Spring Cloud Kubernetes”:

| Thông tin | Nội dung cần ghi |
| --- | --- |
| Artifact triển khai | Image tag và digest thực tế |
| Nền tảng JVM | JDK, Spring Boot, Spring Cloud BOM |
| Tích hợp Kubernetes | Phiên bản Spring Cloud Kubernetes và starter |
| Client | Fabric8 hoặc Kubernetes Java Client, phiên bản đã resolve |
| API server | Phiên bản và bản phân phối/nhà cung cấp cluster |
| Tính năng | Discovery, nguồn config, watcher, load-balancer mode |
| Danh tính | Namespace và ServiceAccount từng component |
| Nhóm API | Group/version/resource/verb đang sử dụng |
| Mốc kiểm thử | Cluster hiện tại, cluster mục tiêu, thời điểm |

Trong dự án Maven cần kiểm tra, có thể xem dependency tree:

~~~powershell
mvn dependency:tree "-Dincludes=org.springframework.cloud:*,io.fabric8:*,io.kubernetes:*"
~~~

Đây là lệnh thực hiện trong dự án ứng dụng cần đánh giá. Kết quả cần đọc là phiên bản **được chọn cuối cùng**, gồm dependency bắc cầu. Đối chiếu thêm artifact đã đóng gói hoặc SBOM của đúng image; POM trên một nhánh khác không phải bằng chứng của runtime.

Không tự override một Java client mới vào ứng dụng cũ chỉ vì client đó có model của Kubernetes mới. Spring Cloud Kubernetes có thể đang gọi method hoặc dùng kiểu dữ liệu chỉ phù hợp với client do bộ dependency hiện tại quản lý.

Khi có nhiều replica, kiểm tra image và cấu hình hiệu lực trên từng nhóm phiên bản. Một rollout chưa hoàn tất có thể khiến chỉ một phần request sử dụng API cũ.

## 4. Kiểm tra API server thực sự phục vụ gì

### 4.1. Chọn rõ context và đọc phiên bản

Các lệnh sau dùng context được chỉ định, không đổi context hiện tại của kubectl:

~~~powershell
$contextName = "TEN_CONTEXT_CAN_KIEM_TRA"
$ns = "compat-lab"
$serviceName = "catalog-api"

kubectl --context=$contextName version -o json
kubectl --context=$contextName get --raw /version
~~~

Đọc riêng `clientVersion` và `serverVersion`. Trong cluster HA đang nâng cấp, một response qua load balancer không mô tả đầy đủ mọi API server; cần thông tin rollout từ bên vận hành cluster.

Nếu kubectl không kết nối hoặc không được phép đọc discovery, giữ nguyên kết luận là **chưa có bằng chứng**, không ghi rằng cluster không hỗ trợ resource.

### 4.2. Liệt kê group/version và resource

~~~powershell
kubectl --context=$contextName api-versions
kubectl --context=$contextName api-resources --cached=false -o wide
kubectl --context=$contextName api-resources --api-group=discovery.k8s.io --cached=false -o wide
~~~

Trong kết quả, kiểm tra `APIVERSION`, `NAME`, `KIND`, `NAMESPACED` và `VERBS`. `VERBS` ở đây là những thao tác resource hỗ trợ theo discovery, không phải quyền của ServiceAccount.

`--cached=false` giúp tránh chủ động dùng danh sách resource đã cache. Các lỗi discovery phải được xử lý trước khi kết luận từ phần output còn lại. Xem [tham chiếu kubectl api-resources](https://kubernetes.io/docs/reference/kubectl/generated/kubectl_api-resources/).

Danh sách API ưu tiên không nhất thiết trình bày tất cả phiên bản được phục vụ của cùng resource. Khi cần xác minh một version cụ thể, truy vấn đúng đường dẫn discovery.

### 4.3. Kiểm tra đúng group/version

~~~powershell
$rawDiscovery = kubectl --context=$contextName get --raw /apis/discovery.k8s.io/v1 --request-timeout=10s
if ($LASTEXITCODE -ne 0) {
    throw "Chua xac minh duoc discovery.k8s.io/v1"
}

$discovery = $rawDiscovery | ConvertFrom-Json
$discovery.resources |
    Where-Object { $_.name -eq "endpointslices" } |
    Select-Object name, kind, namespaced, verbs
~~~

Resource `endpointslices` phải có mặt trong tài liệu trả về nếu đó là API mà ứng dụng cần. Với core API, thực hiện tương tự trên `/api/v1` rồi tìm `services`, `configmaps` hoặc resource liên quan.

Nếu group có nhiều version, có thể đọc:

~~~powershell
kubectl --context=$contextName get --raw /apis/discovery.k8s.io
~~~

Phân biệt `versions` với `preferredVersion`. Client cũ có thể gọi một version khác phiên bản ưu tiên mà kubectl đang chọn. API discovery cho biết bề mặt API server công bố; xem [Discovery API của Kubernetes](https://kubernetes.io/docs/concepts/overview/kubernetes-api/#discovery-api).

Không dùng việc đổi `apiVersion` trong Deployment của ứng dụng để sửa đường HTTP do Java client sinh ra. Hai vị trí này thuộc hai luồng gọi API khác nhau.

## 5. Ví dụ quan trọng: Endpoints và EndpointSlice

### 5.1. Phân biệt deprecated với removed

Kubernetes đã deprecated Endpoints API từ **1.33**. Điều này không có nghĩa `/api/v1/endpoints` đã ngừng được phục vụ từ phiên bản đó. Cảnh báo deprecated cần được ghi nhận và có kế hoạch chuyển đổi. Xem [thông báo chuyển từ Endpoints sang EndpointSlices](https://kubernetes.io/blog/2025/04/24/endpoints-deprecation/).

Một ví dụ khác có kết quả rõ hơn: `discovery.k8s.io/v1beta1` của EndpointSlice **không còn được phục vụ từ Kubernetes 1.25**; phiên bản `discovery.k8s.io/v1` có từ 1.21. Khi chuyển API còn có thay đổi biểu diễn trường topology, nên không chỉ sửa chuỗi version rồi bỏ qua cách đọc dữ liệu. Xem [Deprecated API Migration Guide](https://kubernetes.io/docs/reference/using-api/deprecation-guide/#endpointslice).

| Trạng thái | Ý nghĩa vận hành |
| --- | --- |
| API được phục vụ và chưa có vấn đề đã biết | Tiếp tục kiểm tra quyền, client và hành vi |
| API vẫn được phục vụ nhưng deprecated | Có thể chạy, cần kế hoạch xử lý và kiểm tra mục tiêu nâng cấp |
| API không còn được phục vụ | Client gọi đường đó phải được thay đổi |
| API tồn tại nhưng không có quyền | Sửa quyền/phạm vi theo request, không kết luận API bị loại |
| API gọi được nhưng không có backend | Kiểm tra dữ liệu, selector và readiness |

Kubernetes có thể trả Warning header, thông tin audit và metric liên quan request tới API deprecated. Tận dụng dữ liệu này để tìm workload còn dùng API cũ; không chỉ tìm chuỗi `apiVersion` trong manifest. Xem [Kubernetes Deprecation Policy](https://kubernetes.io/docs/reference/deprecation-policy/).

### 5.2. Bật EndpointSlice khi nhánh Spring Cloud Kubernetes hỗ trợ

Ví dụ sau đối chiếu với tài liệu **Spring Cloud Kubernetes 3.3**; đây là mốc tham chiếu cho thuộc tính, không phải chỉ định phiên bản triển khai:

~~~yaml
spring:
  cloud:
    kubernetes:
      discovery:
        enabled: true
        all-namespaces: false
        namespaces:
          - compat-lab
        use-endpoint-slices: true
~~~

Nhánh tài liệu này mô tả thuộc tính `spring.cloud.kubernetes.discovery.use-endpoint-slices`; cluster cũng phải hỗ trợ API tương ứng và có RBAC cho EndpointSlice. Với phiên bản khác, đối chiếu tài liệu và cấu hình hiệu lực trước khi áp dụng. Xem [DiscoveryClient for Kubernetes](https://docs.spring.io/spring-cloud-kubernetes/reference/3.3/discovery-client.html).

Không suy luận rằng thuộc tính đã có tác dụng chỉ vì ứng dụng chấp nhận file YAML. Cần thấy request hoặc log của implementation đang chạy, rồi xác minh backend mà DiscoveryClient trả về.

### 5.3. Cấp quyền ở đúng API group

Ví dụ Role/RoleBinding dưới đây dành cho namespace lab đã tồn tại, với ServiceAccount `catalog-client` đã được tạo và gắn vào Pod:

~~~yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: catalog-client-discovery
  namespace: compat-lab
rules:
  - apiGroups: [""]
    resources: ["services", "pods"]
    verbs: ["get", "list", "watch"]
  - apiGroups: ["discovery.k8s.io"]
    resources: ["endpointslices"]
    verbs: ["get", "list", "watch"]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  name: catalog-client-discovery
  namespace: compat-lab
subjects:
  - kind: ServiceAccount
    name: catalog-client
    namespace: compat-lab
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: Role
  name: catalog-client-discovery
~~~

Đây là bộ quyền minh họa cho discovery có đọc Pod trong lab. Điều chỉnh theo request thật của implementation, không xem mọi rule đều là yêu cầu tối thiểu bắt buộc cho mọi ứng dụng.

Điểm cần nhớ là `apiGroups: ["discovery.k8s.io"]`, không phải `apiGroups: ["discovery.k8s.io/v1"]`. RBAC rule chỉ rõ group; version thuộc URL API. Quyền đọc `endpoints` trong core group không tự bao gồm `endpointslices` trong group khác. Xem [Using RBAC Authorization](https://kubernetes.io/docs/reference/access-authn-authz/rbac/).

Bộ quyền trên không cấp đọc ConfigMap/Secret. Nếu ứng dụng cần các tính năng đó, bổ sung theo nguồn và phạm vi thực sự sử dụng. Cũng không cấp quyền toàn cluster chỉ để tránh xác định namespace.

## 6. Kiểm tra bằng danh tính của ứng dụng

### 6.1. Xác định đúng ServiceAccount

Lấy Pod thật đang chạy và đọc danh tính đã gắn vào Pod:

~~~powershell
$podName = "TEN_POD_CATALOG_CLIENT"
kubectl --context=$contextName get pod $podName -n $ns -o jsonpath='{.spec.serviceAccountName}'
~~~

Nếu ứng dụng, DiscoveryServer và Configuration Watcher dùng ba ServiceAccount khác nhau, cần kiểm tra cả ba theo phần việc của chúng.

### 6.2. Kiểm tra quyền tách biệt với sự tồn tại API

~~~powershell
$saName = "catalog-client"
$saSubject = "system:serviceaccount:$($ns):$saName"

kubectl --context=$contextName auth can-i list services -n $ns --as=$saSubject
kubectl --context=$contextName auth can-i get endpointslices.discovery.k8s.io -n $ns --as=$saSubject
kubectl --context=$contextName auth can-i list endpointslices.discovery.k8s.io -n $ns --as=$saSubject
kubectl --context=$contextName auth can-i watch endpointslices.discovery.k8s.io -n $ns --as=$saSubject
~~~

Operator cần có quyền impersonate để dùng `--as`. Nếu bị từ chối impersonation, đó chưa phải kết quả kiểm quyền của ServiceAccount. Với quyền được gán qua group, cần mô phỏng cả group phù hợp hoặc kiểm thử bằng danh tính thật trong Pod.

`auth can-i` trả lời câu hỏi phân quyền; nó không thay thế request đọc resource, giải mã response hoặc duy trì watch. Xem [tham chiếu kubectl auth can-i](https://kubernetes.io/docs/reference/kubectl/generated/kubectl_auth/kubectl_auth_can-i/).

### 6.3. Gọi đúng URL collection

Ví dụ đọc EndpointSlice của Service `catalog-api` bằng API version chính xác:

~~~powershell
$selector = [uri]::EscapeDataString("kubernetes.io/service-name=$serviceName")
$collectionPath = "/apis/discovery.k8s.io/v1/namespaces/$ns/endpointslices"
$listUrl = "$($collectionPath)?labelSelector=$selector"

$rawList = kubectl --context=$contextName --as=$saSubject get --raw $listUrl --request-timeout=10s
if ($LASTEXITCODE -ne 0) {
    throw "Request list EndpointSlice chua thanh cong"
}

$sliceList = $rawList | ConvertFrom-Json
[pscustomobject]@{
    ApiVersion = $sliceList.apiVersion
    Kind = $sliceList.kind
    SliceCount = @($sliceList.items).Count
}
~~~

Một response thành công với `items: []` chứng minh request được xử lý, nhưng chưa chứng minh discovery trả được backend cần thiết.

Nếu danh sách rỗng, kiểm tra:

- Namespace có đúng với Service đích không?
- Label `kubernetes.io/service-name` có khớp không?
- Service có selector và backend đúng thiết kế không?
- Backend Pod đã Ready chưa?
- Workload có dùng Service không selector hoặc resource do controller khác quản lý không?

Một Service có thể có nhiều EndpointSlice. Không chỉ đọc Slice đầu tiên rồi kết luận tập instance đầy đủ. Xem [EndpointSlices](https://kubernetes.io/docs/concepts/services-networking/endpoint-slices/).

### 6.4. Kiểm tra watch bằng đúng version

~~~powershell
$watchUrl = "$($collectionPath)?watch=true&timeoutSeconds=20&labelSelector=$selector"

kubectl --context=$contextName --as=$saSubject get --raw $watchUrl --request-timeout=25s
~~~

Mở terminal khác và tạo thay đổi có kiểm soát trên backend lab, chẳng hạn thêm một replica đã được phép chạy. Ghi nhận sự kiện và đối chiếu thay đổi mà ứng dụng nhìn thấy.

Đoạn raw watch này phục vụ kiểm tra endpoint và luồng sự kiện; nó không hiện thực đầy đủ quy trình list-then-watch, quản lý resourceVersion và reconnect của Java client. Watch kết thúc sau `timeoutSeconds` là hành vi cần phân biệt với lỗi không tương thích.

Không thấy sự kiện khi không có thay đổi không đủ để kết luận watch lỗi. Cũng không coi một lần mở watch thành công là bằng chứng informer sẽ phục hồi sau gián đoạn.

## 7. Kiểm tra chính Java client trong Pod

kubectl impersonation vẫn dùng network path, TLS stack và cơ chế nhận credential của kubectl. Vì vậy bước tiếp theo phải dùng đúng image ứng dụng, client runtime và ServiceAccount ở cluster mục tiêu.

### 7.1. Phép thử đọc bằng Fabric8 client do Spring quản lý

Mẫu sau dành cho ứng dụng đang sử dụng Fabric8 và đã có bean `KubernetesClient`. Nó chỉ chạy khi profile `k8s-api-smoke` được bật và chỉ đọc Service/EndpointSlice:

~~~java
package example.compatibility;

import io.fabric8.kubernetes.client.KubernetesClient;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.ApplicationRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Profile;

@Configuration(proxyBeanMethods = false)
@Profile("k8s-api-smoke")
public class KubernetesApiSmokeConfiguration {

    private static final Logger log =
            LoggerFactory.getLogger(KubernetesApiSmokeConfiguration.class);

    @Bean
    ApplicationRunner verifyKubernetesApi(KubernetesClient client) {
        return args -> {
            String namespace = client.getNamespace();
            if (namespace == null || namespace.isBlank()) {
                throw new IllegalStateException("Missing client namespace");
            }

            var services = client.services()
                    .inNamespace(namespace)
                    .list();

            var slices = client.discovery().v1().endpointSlices()
                    .inNamespace(namespace)
                    .withLabel("kubernetes.io/service-name", "catalog-api")
                    .list();

            boolean servicePresent = services.getItems().stream()
                    .anyMatch(service ->
                            "catalog-api".equals(service.getMetadata().getName()));

            if (!servicePresent || slices.getItems().isEmpty()) {
                throw new IllegalStateException(
                        "Lab fixture catalog-api or its EndpointSlices is missing");
            }

            log.info("k8s_api_smoke_pass namespace={} services={} slices={}",
                    namespace,
                    services.getItems().size(),
                    slices.getItems().size());
        };
    }
}
~~~

Chuẩn bị Service `catalog-api` và backend lab trước khi chạy. Mẫu cố ý coi thiếu fixture là thất bại để tránh ghi nhận PASS từ một collection rỗng.

Mẫu tái sử dụng client bean hiện có, không tự tạo client mới có thể lấy kubeconfig hoặc credential khác. Tên DSL phải được đối chiếu với phiên bản Fabric8 đã resolve. Với Kubernetes Java Client, viết phép thử tương đương bằng API của client đó; không thêm Fabric8 chỉ để chạy ví dụ.

Thêm profile kiểm thử vào tập profile lab cần dùng, giữ các profile nghiệp vụ cần thiết. Vì lỗi trong ApplicationRunner có thể làm lần khởi động kiểm thử thất bại, chỉ bật profile này cho lượt xác minh được chuẩn bị.

Phép thử xác nhận được kết nối, quyền đọc và khả năng giải mã các model được gọi. Nó chưa kiểm tra:

- Watch/informer và phục hồi sau ngắt kết nối.
- Cách Spring Cloud DiscoveryClient lọc hoặc chuyển EndpointSlice thành instance.
- Việc chọn port và xử lý trạng thái backend.
- Spring Cloud LoadBalancer thực sự gọi được service đích.
- ConfigMap/Secret được nạp vào Environment hoặc được refresh.

### 7.2. Kiểm tra hành vi của tính năng Spring

Dùng ứng dụng kiểm thử hoặc endpoint quản trị nội bộ để gọi `DiscoveryClient.getInstances("catalog-api")` và quan sát các instance đủ điều kiện. Không mở endpoint chẩn đoán ra công khai.

Thực hiện hai lượt quan sát:

1. **Trạng thái ban đầu:** instance có host/port phù hợp, lời gọi tới backend thành công.
2. **Sau thay đổi backend:** thêm/bớt replica hoặc làm một backend không còn sẵn sàng trong lab, rồi đo thời gian tập instance cập nhật.

Nếu ứng dụng dùng LoadBalancer mode `POD`, kiểm tra nhánh dựa trên DiscoveryClient. Nếu dùng mode `SERVICE`, xác minh lựa chọn Service/port và đường gọi tương ứng. Chỉ kiểm tra DNS hoặc curl Service không đủ để bao phủ cả hai mode.

Quan sát tình huống khởi động lạnh và khi Pod đã chạy ổn định. Một client chỉ lỗi trong bước tạo informer hoặc đồng bộ cache ban đầu có thể không lộ ra qua request nghiệp vụ được phục vụ từ cache cũ.

## 8. Kiểm tra ConfigMap, Secret và Configuration Watcher

### 8.1. Tách API đọc cấu hình khỏi hiệu lực cấu hình

Với ConfigMap đọc qua API, cần kiểm tra cả request đọc nguồn và thuộc tính đã vào ứng dụng. Việc API trả ConfigMap không tự chứng minh Spring đã chọn đúng tên nguồn, profile hoặc thứ tự ưu tiên.

Spring Cloud Kubernetes cho phép chọn ConfigMap theo tên và namespace cấu hình; xem [ConfigMap PropertySource](https://docs.spring.io/spring-cloud-kubernetes/reference/3.3/property-source-config/configmap-propertysource.html).

Trong lab, dùng một thuộc tính không nhạy cảm, chẳng hạn:

~~~yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: catalog-client-config
  namespace: compat-lab
data:
  demo.message: before-upgrade
~~~

Nếu ứng dụng được cấu hình đọc đúng nguồn này, xác minh giá trị hiệu lực là `before-upgrade` qua một cơ chế quan sát nội bộ đã chuẩn bị.

Đối với Secret, kiểm tra bằng một Secret lab chuyên dụng và chỉ ghi nhận có đọc/nạp thành công hay không. Không in token, mật khẩu hoặc toàn bộ response Secret để làm bằng chứng.

### 8.2. Kiểm tra watcher như một workload độc lập

Với Configuration Watcher, xác minh lần lượt:

| Chặng | Bằng chứng cần có |
| --- | --- |
| Đọc/list nguồn ban đầu | Watcher truy cập được ConfigMap/Secret trong namespace cấu hình |
| Nhận sự kiện thay đổi | Có log/sự kiện tương ứng với lần cập nhật nguồn lab |
| Chọn nguồn hợp lệ | Label và điều kiện lọc khớp cấu hình watcher |
| Xác định ứng dụng đích | Namespace, Service và metadata đúng thiết kế |
| Gửi refresh hoặc sự kiện Bus | Kênh truyền thành công |
| Ứng dụng áp dụng thay đổi | Giá trị hiệu lực hoặc bean liên quan đổi như kỳ vọng |

Tài liệu watcher mô tả yêu cầu label của nguồn và cơ chế gửi yêu cầu refresh; việc chỉ sửa nội dung ConfigMap chưa đủ để mọi ứng dụng tự cập nhật. Xem [Spring Cloud Kubernetes Configuration Watcher](https://docs.spring.io/spring-cloud-kubernetes/reference/3.3/spring-cloud-kubernetes-configuration-watcher.html).

Trong lab, đổi `demo.message` thành `after-upgrade` bằng quy trình cập nhật đang dùng. Đo từ lúc resource thay đổi đến khi ứng dụng nhìn thấy giá trị mới. Nếu API watch vẫn chạy nhưng refresh trả HTTP 403, hãy kiểm tra security của ứng dụng đích; đó không phải bằng chứng API Kubernetes đã đổi phiên bản.

Nếu ứng dụng chỉ đọc file mount lúc khởi động và không có cơ chế refresh, kết quả “file đổi nhưng bean chưa đổi” cần được đánh giá theo thiết kế đó.

## 9. Đọc lỗi theo đúng lớp

| Triệu chứng | Nhóm nguyên nhân cần kiểm tra | Bằng chứng tiếp theo |
| --- | --- | --- |
| `404` ở collection của một group/version | API version không được phục vụ hoặc URL sai | Discovery đúng group/version và URL client gọi |
| `404` khi đọc một object | Sai tên/namespace hoặc object chưa có | List collection bằng cùng danh tính |
| `403 Forbidden` | RBAC, scope hoặc danh tính | Resource/verb/namespace/user trong lỗi |
| `401 Unauthorized` | Credential không hợp lệ hoặc không được gửi đúng | Cơ chế xác thực của Pod/client |
| `410 Gone` trên watch | ResourceVersion quá cũ theo lịch sử server giữ | Khả năng relist/reconnect của informer |
| `400/422` | Query, schema, trường hoặc giá trị không phù hợp | Response Status và schema của đúng version |
| Lỗi deserialize JSON/model | Client không xử lý được response hoặc dependency model lệch | Body đã loại dữ liệu nhạy cảm và phiên bản runtime |
| `NoSuchMethodError` / `ClassNotFoundException` | Xung đột thư viện trong JVM | Dependency tree và artifact đã đóng gói |
| Lỗi CA, TLS, DNS hoặc timeout | Đường kết nối, trust store, proxy hoặc tải | Network path và cấu hình client |
| List thành công nhưng không có instance | Dữ liệu, selector, readiness, port hoặc cách map instance | API response và kết quả DiscoveryClient |

HTTP 410 trên watch không có cùng ý nghĩa với API đã bị loại bỏ. Kubernetes cho phép server không giữ vô hạn lịch sử resourceVersion; client phải xử lý việc đồng bộ lại phù hợp. Xem [Kubernetes API Concepts](https://kubernetes.io/docs/reference/using-api/api-concepts/#efficient-detection-of-changes).

Khi thu thập HTTP trace, chỉ lưu phương thức, đường dẫn, status, thời gian và trường cần thiết. Tránh bật log request/response body toàn cục cho Secret hoặc Authorization header.

Có thể sử dụng cây quyết định sau:

~~~mermaid
flowchart TD
    A[Tính năng không hoạt động trên cluster mục tiêu] --> B{Đúng group/version/resource có được phục vụ?}
    B -->|Chưa xác minh| C[Đọc discovery và request thật]
    B -->|Không| D[Chọn API/client/implementation phù hợp]
    B -->|Có| E{Danh tính runtime có quyền và kết nối được?}
    E -->|Không| F[Sửa credential, RBAC hoặc đường kết nối]
    E -->|Có| G{Java client giải mã và theo dõi thay đổi được?}
    G -->|Không| H[Đối chiếu dependency và hành vi client]
    G -->|Có| I[Kiểm tra cấu hình Spring và hành vi nghiệp vụ]
~~~

Không dùng một log chung như “failed to load cache” làm kết luận cuối cùng. Tìm lỗi gốc và request gây ra lỗi trước khi thay phiên bản.

## 10. Kiểm tra manifest và chuẩn bị nâng cấp

### 10.1. Server-side dry-run có phạm vi riêng

Manifest triển khai cũng có thể dùng API cũ. Ví dụ kiểm tra một Service lab trên API server mục tiêu mà không lưu resource:

~~~powershell
@'
apiVersion: v1
kind: Service
metadata:
  name: catalog-api-compat-check
  namespace: compat-lab
spec:
  selector:
    app: catalog-api
  ports:
    - name: http
      port: 80
      targetPort: 8080
'@ | kubectl --context=$contextName apply --dry-run=server -f -
~~~

Namespace cần tồn tại và tài khoản triển khai cần quyền phù hợp. Server-side dry-run giúp kiểm tra request, validation và admission của manifest; xem [Server-Side Apply](https://kubernetes.io/docs/reference/using-api/server-side-apply/#dry-run).

Dry-run của Service không kiểm tra được Java client list/watch EndpointSlice. Tương tự, manifest qua kiểm tra schema không chứng minh backend Ready hoặc refresh hoạt động.

Với manifest thực tế, kiểm tra cả bản đã render từ Helm/Kustomize, RBAC và các controller phụ trợ. Chỉ tìm API cũ trong mã nguồn ứng dụng có thể bỏ sót artifact triển khai.

### 10.2. Dùng ma trận hai phía khi thay ứng dụng và cluster

Gọi `A0` là image hiện tại, `A1` là image dự kiến, `K0` là cluster hiện tại và `K1` là cluster mục tiêu:

| Tổ hợp | Mục đích kiểm thử |
| --- | --- |
| `A0 × K0` | Lấy đường cơ sở của hành vi hiện tại |
| `A1 × K0` | Xác minh image mới chạy được trước khi đổi cluster |
| `A1 × K1` | Xác minh trạng thái đích |
| `A0 × K1` | Xác minh khả năng quay lại image cũ nếu kế hoạch phụ thuộc nó |

Không tự ghi PASS cho ô chưa chạy. Nếu `A0 × K1` không phù hợp vì image cũ dùng API đã bị loại, kế hoạch rollback phải có phương án khác đã kiểm chứng. `kubectl rollout undo` chỉ quay lại workload revision, không khôi phục API server hoặc API đã ngừng phục vụ.

Một trình tự thường dễ kiểm soát là chuẩn bị image hỗ trợ API chung của cả hai cluster, xác minh trên `K0` rồi xác minh trên staging `K1`. Lựa chọn cuối cùng còn phụ thuộc ràng buộc nhà cung cấp và chính sách nâng cấp cluster.

### 10.3. Kiểm tra hành vi sau gián đoạn

Ngoài lần khởi động đầu, thử trong lab:

- Restart Pod ứng dụng với cùng ServiceAccount.
- Thêm/bớt backend và quan sát cập nhật discovery.
- Làm gián đoạn kết nối client có kiểm soát rồi quan sát informer phục hồi.
- Cập nhật nguồn cấu hình đã được chọn và đo hiệu lực refresh.
- Quan sát trong thời gian có credential rotation và qua các chu kỳ reconnect cần thiết.
- Kiểm tra readiness cùng kết quả nghiệp vụ, không chỉ HTTP liveness.

Liveness thành công chỉ cho biết điều kiện probe hiện tại đạt. Không gộp mọi kiểm tra tương thích vào liveness, vì lỗi dependency hoặc API ngoài có thể gây vòng restart thay vì cung cấp bằng chứng hữu ích.

## 11. Hồ sơ kết quả và tiêu chí ra quyết định

Dùng một bảng kết quả gắn với **đúng image, cluster, danh tính và cấu hình**:

| Hạng mục | Kết quả | Bằng chứng nên giữ |
| --- | --- | --- |
| Inventory dependency | PASS/FAIL/CHƯA KIỂM TRA | Phiên bản client đã resolve và digest image |
| API discovery | PASS/FAIL/CHƯA KIỂM TRA | Group/version/resource trên cluster mục tiêu |
| RBAC/runtime identity | PASS/FAIL/CHƯA KIỂM TRA | ServiceAccount, scope, verb đã kiểm tra |
| Request của Java client | PASS/FAIL/CHƯA KIỂM TRA | URL/status, đọc và giải mã thành công |
| Discovery/LoadBalancer | PASS/FAIL/CHƯA KIỂM TRA | Instance và lời gọi backend trước/sau thay đổi |
| ConfigMap/Secret | PASS/FAIL/CHƯA KIỂM TRA/KHÔNG ÁP DỤNG | Nguồn được chọn và thuộc tính có hiệu lực |
| Configuration Watcher | PASS/FAIL/CHƯA KIỂM TRA/KHÔNG ÁP DỤNG | Chặng nhận sự kiện đến refresh ứng dụng |
| Reconnect/khởi động lại | PASS/FAIL/CHƯA KIỂM TRA | Hành vi phục hồi và độ trễ |
| API deprecated | Có/Không/CHƯA XÁC MINH | Workload còn gọi, API thay thế và kế hoạch |
| Phương án quay lại | ĐÃ KIỂM CHỨNG/CHƯA KIỂM CHỨNG | Tổ hợp image/cluster đã chạy thực tế |

Chỉ dùng `KHÔNG ÁP DỤNG` khi tính năng không được sử dụng và cấu hình/dependency không vô tình kích hoạt request liên quan. Điều này giúp giới hạn quyền và phạm vi kiểm tra theo nhu cầu triển khai.

Có thể xác nhận đạt cho phạm vi đã kiểm thử khi:

1. Mọi API cần dùng đều được cluster mục tiêu phục vụ, hoặc đã có thay thế được kiểm chứng.
2. Runtime dùng đúng client/dependency và đúng ServiceAccount.
3. Các thao tác cần thiết thành công, bao gồm list/watch hoặc cập nhật nếu tính năng yêu cầu.
4. Hành vi Spring tương ứng đúng sau khởi động, thay đổi dữ liệu và reconnect.
5. Cảnh báo deprecated, giới hạn còn lại và phương án nâng cấp/quay lại đã được ghi rõ.

Một kết luận có giá trị là: “Image này, với cấu hình và danh tính đã ghi nhận, đã vượt qua các phép thử discovery bằng EndpointSlice và cập nhật ConfigMap trên cluster mục tiêu.” Tránh mở rộng thành bảo đảm cho mọi tính năng Spring Cloud Kubernetes hoặc mọi phiên bản Kubernetes khi chưa có bằng chứng tương ứng.
