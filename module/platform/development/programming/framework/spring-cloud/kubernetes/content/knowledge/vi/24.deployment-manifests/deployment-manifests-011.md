# Kiểm tra manifest và tài nguyên đã được áp dụng

## Mục tiêu và phạm vi

Trong chương **Manifest triển khai** của module **SPRING_CLOUD_KUBERNETES**, kiểm tra sau triển khai có nghĩa là nối được ba bằng chứng: manifest dự định áp dụng, tài nguyên hiện có trong Kubernetes và hành vi của ứng dụng Spring. Thông báo `configured` chỉ xác nhận một thao tác với API; nó chưa chứng minh ứng dụng phục vụ đúng phiên bản, đọc đúng ConfigMap hoặc gọi được dịch vụ khác.

Sau bài học, bạn có thể:

- Kiểm tra manifest với schema và API server trước khi triển khai.
- Đối chiếu tài nguyên thực tế với bản manifest đã render cho đúng môi trường.
- Theo dõi Deployment, ReplicaSet, Pod, probe, Service và EndpointSlice.
- Kiểm tra ServiceAccount, RBAC, ConfigMap và Secret theo tính năng Spring Cloud Kubernetes được sử dụng.
- Thu thập bằng chứng cho DiscoveryClient, Spring Cloud LoadBalancer và Configuration Watcher khi chúng thuộc thiết kế triển khai.

Các lệnh bên dưới dùng **PowerShell** và `kubectl`. Đây là hướng dẫn thực hành; kết quả minh họa không phải kết quả đo từ một cluster cụ thể.

## 1. Xác định điều cần chứng minh

Có thể chia công việc thành năm lớp. Một lớp đạt không thay thế bằng chứng của lớp tiếp theo.

| Lớp kiểm tra | Câu hỏi cần trả lời | Bằng chứng điển hình |
| --- | --- | --- |
| Manifest | Cấu trúc, API version và trường dữ liệu có hợp lệ không? | Dry-run, thông báo validation |
| API server | Đúng tài nguyên đã tồn tại ở đúng namespace chưa? | `get -f`, UID, spec, diff |
| Controller | Controller đã xử lý thay đổi và hoàn tất rollout chưa? | Generation, rollout status, số replica |
| Mạng và quyền | Service tìm đúng Pod; ứng dụng có quyền API cần thiết không? | Selector, EndpointSlice, RBAC, log |
| Ứng dụng | Phiên bản, cấu hình và lời gọi nghiệp vụ có đúng không? | HTTP, log, quan sát từng replica |

Ví dụ, hai Pod có thể đều `Running` nhưng chưa `Ready`. Một Service có thể tồn tại nhưng chọn sai label. Một ConfigMap có thể đã mang nội dung mới trong khi tiến trình Java vẫn giữ giá trị cũ. Không dùng một lệnh duy nhất làm tiêu chí chấp nhận toàn bộ triển khai.

## 2. Chuẩn bị tình huống thực hành

Giả sử pipeline đã triển khai ứng dụng `orders-api` vào namespace `sck-lab`. Bản manifest cuối cùng nằm trong artifact `.\rendered\orders-api.yaml`. Nếu dùng Helm hoặc Kustomize, hãy lấy kết quả render của đúng release và môi trường; không đưa biểu thức template Helm chưa render vào `kubectl apply -f`.

Bài học dùng các quy ước sau; thay chúng bằng thông tin của hệ thống đang kiểm tra:

| Thành phần | Quy ước trong ví dụ |
| --- | --- |
| Context | `kind-sck-lab` |
| Namespace | `sck-lab`, đã được tạo trước |
| Deployment | `orders-api`, mong muốn 2 replica, không dùng HPA trong ví dụ |
| Container ứng dụng | `orders-api`, lắng nghe cổng 8080 |
| Label chọn Pod | `app.kubernetes.io/name=orders-api` |
| Service | `orders-api`, cổng 80 chuyển đến named port `http` |
| ServiceAccount | `orders-api` |
| ConfigMap | `orders-api` |
| Secret tùy chọn | `orders-api-db` |
| Dịch vụ phụ thuộc tùy chọn | `inventory-api` |
| Watcher tùy chọn | Deployment `configuration-watcher` |

Image phải chứa ứng dụng Spring Boot và các dependency cần thiết. Cơ chế nạp cấu hình, discovery, profile và các endpoint quản trị phải được thiết lập theo release Spring Boot/Spring Cloud mà dự án đã khóa. Khai báo ConfigMap hoặc biến môi trường không tự thêm starter vào image.

Các đoạn YAML dưới đây thể hiện **quan hệ cần kiểm tra**, không phải bộ manifest hoàn chỉnh để sao chép triển khai:

```yaml
# Phần liên quan trong Deployment orders-api
spec:
  replicas: 2
  selector:
    matchLabels:
      app.kubernetes.io/name: orders-api
  template:
    metadata:
      labels:
        app.kubernetes.io/name: orders-api
    spec:
      serviceAccountName: orders-api
      containers:
        - name: orders-api
          # image được lấy từ artifact của release thực tế
          ports:
            - name: http
              containerPort: 8080
          readinessProbe:
            httpGet:
              path: /actuator/health/readiness
              port: http
          livenessProbe:
            httpGet:
              path: /actuator/health/liveness
              port: http
---
# Phần liên quan trong Service orders-api
spec:
  selector:
    app.kubernetes.io/name: orders-api
  ports:
    - name: http
      port: 80
      targetPort: http
```

Nếu Actuator dùng management port riêng, phải đối chiếu probe với cổng đó. Named port `http` trong ví dụ trỏ vào cổng ứng dụng 8080, không mặc nhiên trỏ vào mọi cổng quản trị.

Thiết lập biến cho phiên kiểm tra:

```powershell
$clusterContext = 'kind-sck-lab'
$namespace = 'sck-lab'
$manifestPath = '.\rendered\orders-api.yaml'
$deploymentName = 'orders-api'
$serviceName = 'orders-api'
$selector = 'app.kubernetes.io/name=orders-api'
```

Chạy các khối lệnh trong cùng phiên PowerShell. Mọi tên đường dẫn, context và tài nguyên phải được thay trước khi chạy.

## 3. Xác nhận cluster và namespace

Bắt đầu bằng việc xác nhận đích đến:

```powershell
kubectl config current-context
kubectl config get-contexts $clusterContext
kubectl --context $clusterContext cluster-info
kubectl --context $clusterContext get namespace $namespace
kubectl --context $clusterContext -n $namespace get deployment $deploymentName
```

Trong các bước tiếp theo, `--context` và `-n` luôn được truyền rõ ràng. Không cần đổi context hoặc namespace mặc định của người vận hành.

Đọc từng lỗi theo đúng lớp:

- Không kết nối được API server: xử lý kết nối hoặc kubeconfig trước.
- `Unauthorized`: kiểm tra thông tin xác thực của người chạy lệnh.
- `Forbidden`: danh tính hiện tại không được phép thực hiện thao tác đó.
- `NotFound`: kiểm tra context, namespace, tên và việc tài nguyên đã được tạo hay chưa.

`-n` không ghi đè một `metadata.namespace` đã được khai báo khác trong manifest. Kiểm tra namespace trong bản render; các tài nguyên như Namespace hoặc ClusterRole vốn không thuộc namespace.

## 4. Kiểm tra manifest trước khi áp dụng

### 4.1. Dry-run phía client

```powershell
kubectl --context $clusterContext -n $namespace apply `
  --dry-run=client --validate=strict -f $manifestPath
if ($LASTEXITCODE -ne 0) {
    throw 'Manifest chưa vượt qua kiểm tra phía client.'
}
```

Bước này giúp phát hiện lỗi cú pháp, kiểu dữ liệu và nhiều lỗi schema trước thao tác ghi. Nó không tạo tài nguyên. Tuy nhiên, `kubectl` vẫn có thể cần liên hệ cluster để lấy thông tin API/schema; `client` không có nghĩa là luôn hoạt động ngoại tuyến.

### 4.2. Dry-run phía server theo đúng cách triển khai

Giả sử pipeline sử dụng server-side apply với field manager `sck-release`:

```powershell
kubectl --context $clusterContext -n $namespace apply `
  --server-side --field-manager=sck-release `
  --dry-run=server --validate=strict -f $manifestPath
if ($LASTEXITCODE -ne 0) {
    throw 'API server chưa chấp nhận manifest trong dry-run.'
}
```

Server dry-run đưa yêu cầu qua xử lý của API server nhưng không lưu tài nguyên. `--validate=strict` yêu cầu validation nghiêm ngặt; khả năng kiểm tra phía server còn phụ thuộc cluster. Xem [tài liệu kubectl apply](https://kubernetes.io/docs/reference/kubectl/generated/kubectl_apply/) và [cơ chế dry-run của Kubernetes API](https://kubernetes.io/docs/reference/using-api/api-concepts/#dry-run).

Cách apply và field manager cần khớp với pipeline thực tế. Không tự chuyển phương thức quản lý trường chỉ để vượt qua bước kiểm tra.

| Thông báo hoặc dấu hiệu | Hướng kiểm tra |
| --- | --- |
| `no matches for kind` | API version, tài nguyên được hỗ trợ, CRD đã cài chưa |
| Trường không được nhận diện | Sai tên trường, sai cấp thụt lề hoặc sai schema |
| `field is immutable` | Đang sửa trường không thể cập nhật tại chỗ |
| Admission từ chối | Policy, quota, yêu cầu bảo mật hoặc webhook |
| Xung đột field manager | Ai sở hữu trường đó; có controller cùng quản lý không |
| Thiếu Namespace hoặc CRD | Chuẩn bị dependency theo đúng thứ tự trước |

Server dry-run không kéo image, không schedule Pod, không chạy Spring và không kiểm tra mật khẩu có kết nối được cơ sở dữ liệu. Nó cũng không phải giao dịch tạo tạm mọi dependency: một Namespace hoặc CRD được dry-run ở đầu file không xuất hiện thật để phục vụ tài nguyên phía sau.

Không dùng `--validate=false` hoặc `--force-conflicts` như phản xạ đầu tiên khi gặp lỗi.

## 5. So sánh bản dự kiến với trạng thái hiện tại

### 5.1. Đọc diff

```powershell
kubectl --context $clusterContext -n $namespace diff `
  --server-side --field-manager=sck-release -f $manifestPath
$diffExitCode = $LASTEXITCODE

switch ($diffExitCode) {
    0 { 'Không có khác biệt theo phép so sánh của kubectl diff.' }
    1 { 'Có khác biệt: cần đọc từng thay đổi trước khi tiếp tục.' }
    default { throw "Không tạo được diff. Exit code: $diffExitCode" }
}
```

Theo [tài liệu kubectl diff](https://kubernetes.io/docs/reference/kubectl/generated/kubectl_diff/), mã `0` nghĩa là không có khác biệt, `1` nghĩa là có khác biệt, lớn hơn `1` là lỗi. Cấu hình CI/PowerShell xử lý native command cần chấp nhận quy ước này; không đánh đồng mọi mã khác 0 với lỗi công cụ. Lệnh còn phụ thuộc chương trình diff có sẵn hoặc được cấu hình phù hợp trên máy.

Trước apply, khác biệt về image hoặc cấu hình có thể là thay đổi dự kiến. Sau apply, phải giải thích được khác biệt còn lại. HPA quản lý replica hoặc admission webhook thêm sidecar là những yếu tố cần đối chiếu với thiết kế.

Diff có thể hiển thị dữ liệu Secret nếu đầu vào chứa Secret. Chỉ xem đầu ra tại nơi được phép; không đưa nguyên diff chứa bí mật vào log CI hoặc báo cáo.

### 5.2. Phân biệt apply với xác minh sau apply

Nếu đang thực hành triển khai trong lab và đã duyệt khác biệt, thao tác thực sự thay đổi cluster là:

```powershell
kubectl --context $clusterContext -n $namespace apply `
  --server-side --field-manager=sck-release -f $manifestPath
if ($LASTEXITCODE -ne 0) {
    throw 'Apply thất bại hoặc chỉ áp dụng được một phần tài nguyên.'
}
```

Nếu pipeline đã apply, bắt đầu kiểm tra từ trạng thái hiện tại; không chạy lại lệnh ghi chỉ để xem tài nguyên.

Một file nhiều đối tượng không được apply theo kiểu tất cả thành công hoặc tất cả hoàn tác. Nếu Service đã cập nhật nhưng Deployment lỗi, cluster có thể đang được cập nhật một phần. Đọc kết quả của từng đối tượng.

## 6. Kiểm kê tài nguyên đã được tạo

```powershell
kubectl --context $clusterContext -n $namespace get -f $manifestPath

kubectl --context $clusterContext -n $namespace get `
  deployments,replicasets,pods,services,configmaps,serviceaccounts,roles,rolebindings `
  -l $selector

kubectl --context $clusterContext -n $namespace get deployment $deploymentName -o yaml
kubectl --context $clusterContext -n $namespace get service $serviceName -o yaml
```

`get -f` tra cứu những đối tượng được định danh trong manifest. Lệnh theo label chỉ tìm những tài nguyên thật sự có label đó; nếu RoleBinding không được gắn label thì nó không xuất hiện trong truy vấn này.

`kubectl get all` cũng không phải danh sách mọi loại tài nguyên. Truy vấn trực tiếp ConfigMap, Secret, RBAC, Ingress hoặc NetworkPolicy nếu chúng thuộc phạm vi release.

Khi đọc YAML thực tế, chú ý:

- `metadata.namespace` và `metadata.name`: xác nhận đúng đích.
- `metadata.uid`: phân biệt đối tượng hiện tại với đối tượng cùng tên đã bị xóa và tạo lại.
- `spec`: kiểm tra image, selector, ServiceAccount, cổng và tham chiếu cấu hình.
- `status`: trạng thái do controller báo cáo.
- `ownerReferences`: truy vết Pod về ReplicaSet và ReplicaSet về Deployment.

Đối tượng từ API có thể có giá trị mặc định, `resourceVersion`, `status` hoặc trường do controller bổ sung. So sánh toàn bộ YAML bằng chuỗi văn bản thường tạo nhiều nhiễu. Đối chiếu trường liên quan và dùng diff đúng chế độ apply.

Không dùng `resourceVersion` như số phiên bản nghiệp vụ hoặc thời điểm chắc chắn ứng dụng đã nạp cấu hình.

## 7. Xác minh Deployment đã hoàn tất rollout

### 7.1. Chờ rollout với thời hạn rõ ràng

```powershell
kubectl --context $clusterContext -n $namespace rollout status `
  "deployment/$deploymentName" --timeout=180s
if ($LASTEXITCODE -ne 0) {
    throw 'Rollout chưa hoàn tất; cần đọc Deployment, Pod và Events.'
}

kubectl --context $clusterContext -n $namespace get deployment $deploymentName
kubectl --context $clusterContext -n $namespace describe deployment $deploymentName
kubectl --context $clusterContext -n $namespace get replicasets -l $selector
```

`--timeout=180s` là thời gian công cụ chờ, không thay đổi `progressDeadlineSeconds` của Deployment. Chọn thời hạn theo thời gian khởi động và đặc điểm rollout của ứng dụng.

Một rollout hoàn chỉnh cần các replica mới sẵn sàng phục vụ và replica cũ đã được thay thế. Riêng `Available=True` có thể vẫn đúng trong lúc replica cũ đang phục vụ. Đối chiếu trạng thái cập nhật thay vì chỉ nhìn một condition. Xem [trạng thái Deployment](https://kubernetes.io/docs/concepts/workloads/controllers/deployment/#deployment-status).

### 7.2. Đọc generation và số replica

```powershell
$deploymentJson = kubectl --context $clusterContext -n $namespace get `
  deployment $deploymentName -o json
if ($LASTEXITCODE -ne 0) {
    throw 'Không đọc được Deployment.'
}
$deployment = ($deploymentJson -join [Environment]::NewLine) | ConvertFrom-Json

[pscustomobject]@{
    Generation         = $deployment.metadata.generation
    ObservedGeneration = $deployment.status.observedGeneration
    Desired            = $deployment.spec.replicas
    Updated            = $deployment.status.updatedReplicas
    Ready              = $deployment.status.readyReplicas
    Available          = $deployment.status.availableReplicas
    Total              = $deployment.status.replicas
}
$deployment.status.conditions | Format-Table type, status, reason
```

Trong ví dụ 2 replica, trạng thái ổn định mong đợi là controller đã quan sát generation hiện tại, các số Updated/Ready/Available/Total đều là 2 và rollout status thành công. Trường đếm có thể chưa xuất hiện khi chưa có replica tương ứng; không diễn giải giá trị rỗng thành “đã đạt”.

Đây là ví dụ cho ứng dụng không dùng HPA. Khi có autoscaler, số replica mong muốn phải đối chiếu với controller đang quản lý nó. Nếu release khác xuất hiện trong lúc kiểm tra, cần xác định lại revision và image của release đang đánh giá.

### 7.3. Xác nhận image ở Pod thực tế

```powershell
kubectl --context $clusterContext -n $namespace get pods -l $selector -o wide

kubectl --context $clusterContext -n $namespace get pods -l $selector `
  -o 'jsonpath={range .items[*]}{.metadata.name}{"\n"}{range .status.containerStatuses[*]}{.name}{" image="}{.image}{" imageID="}{.imageID}{"\n"}{end}{end}'
```

Đối chiếu image trong Deployment với container thực tế và imageID mà runtime báo cáo. Với tag có thể bị ghi đè, chỉ nhìn tag chưa đủ chứng minh cùng nội dung. Với image đa kiến trúc, manifest-list digest và digest theo nền tảng có thể khác nhau; đối chiếu qua artifact/registry theo quy trình dự án.

Kiểm tra container ứng dụng và sidecar riêng biệt. Một sidecar khỏe không chứng minh tiến trình Spring hoạt động.

## 8. Đọc trạng thái Pod, probe và Events

Chọn một tên Pod thật từ kết quả ở trên:

```powershell
$podName = '<ten-pod-thuc-te>'

kubectl --context $clusterContext -n $namespace describe pod $podName
kubectl --context $clusterContext -n $namespace logs $podName `
  -c orders-api --tail=150
kubectl --context $clusterContext -n $namespace get events `
  --field-selector "involvedObject.name=$podName" `
  --sort-by=.metadata.creationTimestamp
```

Nếu container đã restart và còn log của lần chạy trước:

```powershell
kubectl --context $clusterContext -n $namespace logs $podName `
  -c orders-api --previous --tail=150
```

`--previous` chỉ hữu ích khi có lần chạy trước được giữ lại. Không có log trước không tự chứng minh container chưa từng gặp vấn đề.

| Dấu hiệu | Điều cần kiểm tra tiếp |
| --- | --- |
| `Pending` | Scheduling, requests/limits, quota, node affinity, volume |
| `ImagePullBackOff` | Tên image, tag/digest, registry và imagePullSecret |
| `CreateContainerConfigError` | ConfigMap/Secret/key được tham chiếu có tồn tại không |
| `CrashLoopBackOff` | Log trước, lỗi khởi động Spring, exit code, bộ nhớ |
| `Running` nhưng chưa `Ready` | Probe, cổng, đường dẫn, thời gian khởi động, readiness gate |
| Restart tăng | Liveness, OOMKilled hoặc lỗi tiến trình; đối chiếu Last State |

Events có thời gian lưu hữu hạn. Không thấy Event lỗi không đủ kết luận chưa từng có lỗi.

Spring Boot cung cấp health group readiness/liveness cho Kubernetes. Kiểm tra đúng đường dẫn, cổng và chính sách truy cập. Nếu management port tách riêng, endpoint quản trị có thể vẫn trả lời khi cổng nghiệp vụ gặp vấn đề; cần thêm kiểm tra nghiệp vụ. Với ứng dụng khởi động lâu, đánh giá `startupProbe` để tránh restart quá sớm. Không gắn lỗi của mọi hệ thống bên ngoài vào liveness. Xem [Kubernetes Probes trong Spring Boot](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html#actuator.endpoints.kubernetes-probes).

## 9. Kiểm tra Service, EndpointSlice và đường đi HTTP

### 9.1. Đối chiếu selector và cổng

```powershell
kubectl --context $clusterContext -n $namespace describe service $serviceName
kubectl --context $clusterContext -n $namespace get pods -l $selector --show-labels

kubectl --context $clusterContext -n $namespace get endpointslices.discovery.k8s.io `
  -l "kubernetes.io/service-name=$serviceName" -o yaml
```

Với Service có selector của bài này, cần nối được chuỗi:

```text
Service orders-api:80
  -> selector app.kubernetes.io/name=orders-api
  -> Pod được chọn
  -> targetPort http
  -> containerPort 8080
  -> tiến trình thực sự lắng nghe cổng 8080
```

Đọc địa chỉ, cổng, `targetRef` và conditions của endpoint. Có Pod mang label chưa đủ nếu endpoint chưa sẵn sàng. Xét thêm thiết kế như `publishNotReadyAddresses` hoặc Service không có selector khi chúng được sử dụng. Xem [hướng dẫn chẩn đoán Service](https://kubernetes.io/docs/tasks/debug/debug-application/debug-service/).

Nếu client Spring của dự án vẫn đọc API `Endpoints`, kiểm tra thêm:

```powershell
kubectl --context $clusterContext -n $namespace get endpoints $serviceName -o yaml
```

Quan sát EndpointSlice là kiểm tra tài nguyên Kubernetes; nó không tự chuyển DiscoveryClient sang API EndpointSlice.

### 9.2. Tách kiểm tra một Pod khỏi kiểm tra Service

Để kiểm tra một Pod cụ thể, chạy ở terminal thứ nhất:

```powershell
kubectl --context $clusterContext -n $namespace port-forward `
  "pod/$podName" 18080:8080
```

Ở terminal khác:

```powershell
Invoke-RestMethod -Uri 'http://127.0.0.1:18080/actuator/health/readiness'
```

Sau đó gọi một API nghiệp vụ thật qua cùng kết nối và đối chiếu kết quả mong đợi. Đường dẫn API nghiệp vụ thuộc ứng dụng của bạn; Spring Boot không tự cung cấp endpoint kiểm tra release hoặc DiscoveryClient.

Port-forward tới Pod kiểm tra tiến trình trên Pod đó, nhưng không xác minh DNS hay đường truyền qua ClusterIP. Kể cả port-forward tới Service cũng không chứng minh đầy đủ đường truyền mạng của Service trong cluster.

Để kiểm tra Service, dùng một Pod chẩn đoán đã được cấp phép, có `curl` và nằm trong vị trí mạng tương đương caller:

```powershell
$diagnosticPod = '<ten-pod-chan-doan-co-curl>'
$serviceUrl = 'http://orders-api.' + $namespace +
    '.svc.cluster.local:80/actuator/health/readiness'

kubectl --context $clusterContext -n $namespace exec $diagnosticPod -- `
  curl --fail --show-error --silent --connect-timeout 3 --max-time 10 $serviceUrl
```

Ví dụ dùng cluster domain `cluster.local`; thay nếu cluster dùng domain khác. Một phản hồi thành công chứng minh một lời gọi tới được backend, chưa chứng minh mọi replica phục vụ đúng cấu hình. Phân biệt HTTP 401/403 với lỗi DNS, timeout hoặc connection refused.

Nếu NetworkPolicy phụ thuộc label/namespace caller, Pod chẩn đoán có quyền khác có thể cho kết quả khác ứng dụng thực tế. Đối chiếu đường đi từ caller thật trước khi kết luận.

## 10. Kiểm tra ConfigMap và Secret theo cách ứng dụng tiêu thụ

### 10.1. Kiểm tra đối tượng và tham chiếu

```powershell
kubectl --context $clusterContext -n $namespace get configmap orders-api -o yaml
kubectl --context $clusterContext -n $namespace describe secret orders-api-db
kubectl --context $clusterContext -n $namespace get deployment $deploymentName -o yaml
```

Chỉ truy vấn Secret khi thành phần đó được sử dụng. `describe secret` cho xem metadata và tên key/kích thước mà không in giá trị như `get secret -o yaml`. Tên key và metadata vẫn cần được xử lý theo quy định của hệ thống.

Đối chiếu tên, namespace, key, volume mount, `envFrom` hoặc `valueFrom`. Một Secret tồn tại không chứng minh username/password hợp lệ với dịch vụ đích. Thiếu key bắt buộc và lỗi xác thực nghiệp vụ là hai vấn đề khác nhau.

Với Spring Cloud Kubernetes đọc ConfigMap qua API, đối chiếu `spring.application.name`, tên nguồn cấu hình, namespace và danh sách source/profile. Tên ConfigMap đúng theo quy ước mặc định không có nghĩa mọi override đều đúng. Xem [ConfigMap PropertySource](https://docs.spring.io/spring-cloud-kubernetes/reference/property-source-config/configmap-propertysource.html).

### 10.2. Phân biệt cập nhật Kubernetes với cập nhật Spring

| Cách sử dụng cấu hình | Khi đối tượng Kubernetes đổi | Bằng chứng cần bổ sung |
| --- | --- | --- |
| Biến môi trường từ ConfigMap/Secret | Tiến trình đang chạy giữ giá trị cũ | Pod mới khởi động với cấu hình mới |
| Volume chiếu thông thường | Nội dung có thể cập nhật sau độ trễ đồng bộ | File đổi và ứng dụng đã nạp lại |
| Mount qua `subPath` | Không tự nhận cập nhật nội dung nguồn | Quy trình tạo lại Pod hoặc cơ chế thay thế đã thiết kế |
| Spring Cloud Kubernetes đọc API | Phụ thuộc cấu hình đọc và refresh | Đúng source, quyền đúng, bean dùng giá trị mới |
| Configuration Watcher | Có thể phát thông báo theo thiết kế | Đúng instance nhận thông báo, hành vi sau refresh đúng |

Cơ chế đồng bộ được mô tả trong [tài liệu ConfigMap](https://kubernetes.io/docs/concepts/configuration/configmap/#mounted-configmaps-are-updated-automatically) và [cập nhật Secret được mount](https://kubernetes.io/docs/concepts/configuration/secret/#using-secrets-as-files-from-a-pod).

Để quan sát cấu hình không nhạy cảm, bài lab có thể dành một key như `demo.config-version`:

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: orders-api
  namespace: sck-lab
data:
  application.yaml: |-
    demo:
      config-version: "cfg-2026-11-24-01"
```

Đây là key do ứng dụng ví dụ quy ước, không phải thuộc tính có sẵn của Spring. Ứng dụng phải có cách quan sát an toàn, chẳng hạn ghi phiên bản cấu hình không bí mật vào log hoặc trả về qua endpoint nội bộ đã thiết kế. Không công khai toàn bộ Environment hoặc giá trị Secret để kiểm tra.

Thay ConfigMap độc lập không mặc nhiên tạo rollout. Xác định cơ chế dự án sử dụng: tạo Pod mới theo quy trình release, checksum trong Pod template hoặc refresh được hỗ trợ. Với refresh, cần chứng minh bean xử lý yêu cầu đã nhận giá trị mới; phản hồi thành công của endpoint refresh chưa đủ.

Nếu có hai replica, kiểm tra cấu hình ở cả hai. Gọi lặp qua Service không bảo đảm đã chạm đến từng Pod.

## 11. Kiểm tra ServiceAccount và RBAC bằng danh tính ứng dụng

Tài khoản người vận hành và tài khoản Pod có thể có quyền khác nhau. Bạn đọc được ConfigMap bằng `kubectl` không chứng minh ứng dụng đọc được.

Xem `serviceAccountName` trên Pod thực tế và các liên kết:

```powershell
kubectl --context $clusterContext -n $namespace get pod $podName `
  -o 'jsonpath={.spec.serviceAccountName}{"\n"}'

kubectl --context $clusterContext -n $namespace get serviceaccount orders-api
kubectl --context $clusterContext -n $namespace get role <ten-role> -o yaml
kubectl --context $clusterContext -n $namespace get rolebinding <ten-rolebinding> -o yaml
```

Thay `<ten-role>` và `<ten-rolebinding>` bằng tên trong manifest. Kiểm tra `roleRef`, tên ServiceAccount và namespace ở `subjects`; đừng chỉ kiểm tra RoleBinding tồn tại.

Sau đó kiểm tra quyền cần thiết:

```powershell
$serviceAccountIdentity = 'system:serviceaccount:' + $namespace + ':orders-api'

kubectl --context $clusterContext -n $namespace auth can-i `
  get configmaps/orders-api --as $serviceAccountIdentity

kubectl --context $clusterContext -n $namespace auth can-i `
  list services --as $serviceAccountIdentity

kubectl --context $clusterContext -n $namespace auth can-i `
  watch endpointslices.discovery.k8s.io --as $serviceAccountIdentity
```

`--as` yêu cầu người kiểm tra có quyền impersonation. Nếu yêu cầu impersonation bị từ chối, đó không phải bằng chứng ServiceAccount thiếu quyền đọc ConfigMap. Xem [kubectl auth can-i](https://kubernetes.io/docs/reference/kubectl/generated/kubectl_auth/kubectl_auth_can-i/).

Chọn phép kiểm tra theo implementation và tính năng thực tế:

| Tính năng | Tài nguyên/quyền cần xác minh theo release |
| --- | --- |
| Đọc ConfigMap qua API | ConfigMap, phạm vi namespace; `get/list` tùy cách đọc |
| Discovery trực tiếp qua Kubernetes API | Service, Endpoints hoặc EndpointSlice; Pod nếu implementation/tính năng cần |
| Theo dõi thay đổi | Thêm `watch` và quyền khởi tạo danh sách cần thiết |
| Đọc Secret qua API | Chỉ quyền Secret thật sự được sử dụng |
| Watcher chạy riêng | ServiceAccount và RBAC của chính Watcher |
| Chỉ dùng biến môi trường/volume | Không tự suy ra Pod phải có quyền đọc API ConfigMap/Secret |

Với EndpointSlice, API group của rule là `discovery.k8s.io`, không phải core group rỗng. Ví dụ một rule khi client thực sự dùng EndpointSlice:

```yaml
rules:
  - apiGroups: ["discovery.k8s.io"]
    resources: ["endpointslices"]
    verbs: ["get", "list", "watch"]
```

Đây là một rule minh họa, không phải toàn bộ Role cho mọi ứng dụng. Đối chiếu [DiscoveryClient for Kubernetes](https://docs.spring.io/spring-cloud-kubernetes/reference/discovery-client.html) và release đang dùng trước khi quyết định API/permissions.

Với discovery nhiều namespace, kiểm tra quyền tại từng namespace mục tiêu. Đừng mở rộng thành `cluster-admin` để chữa nhanh lỗi `Forbidden`. Ngoài RBAC, truy cập API còn có thể lỗi do token, CA, namespace resolution hoặc kết nối mạng.

## 12. Xác minh tính năng Spring Cloud Kubernetes đã chọn

### 12.1. DiscoveryClient và Spring Cloud LoadBalancer

Khi ứng dụng gọi `inventory-api` qua DiscoveryClient, kiểm tra Service và endpoint của **inventory-api**, namespace tìm kiếm, bộ lọc và cổng được chọn. Nếu Kubernetes có endpoint nhưng client trả danh sách rỗng, đối chiếu cấu hình discovery và log API thay vì chỉ restart caller.

Với Spring Cloud LoadBalancer, xác định chế độ `POD` hay `SERVICE` rồi theo dõi địa chỉ thực tế được chọn. Hai chế độ có đường chọn đích khác nhau; xem [LoadBalancer for Kubernetes](https://docs.spring.io/spring-cloud-kubernetes/reference/load-balancer.html).

Thực hiện một lời gọi nghiệp vụ từ `orders-api` đến dịch vụ phụ thuộc và ghi nhận kết quả/trace theo khả năng quan sát của hệ thống. Gọi thành công DNS bằng `curl` chưa chứng minh đường gọi qua client Spring hoạt động. Nếu ứng dụng chỉ cần DNS Service và không dùng DiscoveryClient, đánh dấu bước discovery là không áp dụng.

### 12.2. Configuration Watcher khi có trong thiết kế

Kiểm tra Watcher theo chuỗi: rollout controller, namespace theo dõi, ServiceAccount/RBAC, bộ lọc tài nguyên, ứng dụng đích và việc nhận refresh. Với cấu hình lọc tương ứng, ConfigMap có thể dùng label `spring.cloud.kubernetes.config: "true"`. HTTP refresh thường gửi đến `/actuator/refresh`; đối chiếu cổng, đường dẫn và quyền truy cập. Xem [Configuration Watcher](https://docs.spring.io/spring-cloud-kubernetes/reference/spring-cloud-kubernetes-configuration-watcher.html).

```powershell
kubectl --context $clusterContext -n $namespace rollout status `
  deployment/configuration-watcher --timeout=180s

kubectl --context $clusterContext -n $namespace logs `
  deployment/configuration-watcher --tail=150
```

Trong lab, thay một giá trị không nhạy cảm qua quy trình cấu hình rồi kiểm tra nó trên từng instance. Đối chiếu thời điểm thay đổi, thông báo của Watcher và giá trị yêu cầu nghiệp vụ sử dụng. Nếu refresh xảy ra trước khi file chiếu đồng bộ, đánh giá độ trễ và cách tải lại.

Nếu thiết kế dùng rollout để cập nhật cấu hình, Watcher có thể không cần thiết. Chỉ triển khai và cấp quyền cho tính năng thực sự cần.

## 13. Xử lý một tình huống lỗi xuyên suốt

Giả sử pipeline báo apply thành công, Deployment đủ 2 replica và ConfigMap đã có `cfg-2026-11-24-02`, nhưng một số yêu cầu vẫn dùng cấu hình cũ.

Đi theo bằng chứng:

1. Xác nhận context/namespace và image của release đang kiểm tra.
2. Xem từng Pod, ReplicaSet và thời điểm tạo để biết có Pod cũ hoặc rollout khác không.
3. Xác định cấu hình được truyền qua biến môi trường, file hay API.
4. Nếu là biến môi trường, kiểm tra quy trình tạo Pod mới; refresh không thay đổi môi trường của tiến trình đã chạy.
5. Nếu là file, kiểm tra nội dung được chiếu, `subPath` và việc ứng dụng đọc lại.
6. Nếu là API/Watcher, kiểm tra source, quyền, instance nhận sự kiện và khả năng refresh của bean.
7. Kiểm tra từng Pod qua phiên bản cấu hình không bí mật.
8. Kiểm tra lại lời gọi nghiệp vụ qua đường mạng thật của caller.

Một kết luận hữu ích phải chỉ ra lớp lỗi và bằng chứng. Ví dụ: “Pod A và B có cùng image; ConfigMap đã đổi; cả hai đọc giá trị qua biến môi trường và chưa có Pod mới, nên tiến trình vẫn dùng cấu hình khi khởi động.”

Kết luận đó dẫn đến hành động phù hợp trong quy trình release. “Kubernetes chưa cập nhật” là nhận xét quá rộng để quyết định cách sửa.

## 14. Ghi bằng chứng và tiêu chí chấp nhận

Báo cáo xác minh cần gắn với context, namespace, release/image và thời điểm đo. Đây là **mẫu trống**, không phải xác nhận một triển khai đã đạt:

```text
Context: <context-da-kiem-tra>
Namespace: <namespace>
Release/Image: <release-va-digest>
Thoi diem: <thoi-diem-kem-mui-gio>

Manifest validation: NOT_RUN
API inventory/diff: NOT_RUN
Deployment rollout: NOT_RUN
Pod/probes/restarts: NOT_RUN
Service/EndpointSlice: NOT_RUN
ConfigMap/Secret references: NOT_RUN
RBAC theo tinh nang: NOT_RUN
HTTP nghiep vu: NOT_RUN
Discovery/LoadBalancer: NOT_RUN hoac NOT_APPLICABLE + ly do
Configuration Watcher: NOT_RUN hoac NOT_APPLICABLE + ly do

Bang chung: <lenh/ket-qua-da-loc-du-lieu-nhay-cam>
Sai lech con lai: <mo-ta>
Ket luan: <PASS/FAIL/INCONCLUSIVE>
```

Chỉ dùng `PASS` khi có bằng chứng cho tiêu chí tương ứng. `NOT_APPLICABLE` phải có lý do thiết kế; không dùng để che một bước chưa chạy. `INCONCLUSIVE` phù hợp khi thiếu quyền quan sát hoặc đang có release khác làm thay đổi trạng thái.

Trước khi chấp nhận triển khai, đối chiếu:

- Đúng cluster, namespace, artifact render và release.
- Validation thành công; diff còn lại được giải thích.
- Đủ tài nguyên thuộc phạm vi release; tham chiếu tên/key đúng.
- Rollout hoàn tất, Pod dùng đúng image và probe đạt.
- Service chọn đúng backend; đường HTTP nghiệp vụ hoạt động.
- Cấu hình không nhạy cảm quan sát được trên từng instance cần kiểm tra.
- Quyền API khớp tính năng; không còn lỗi quyền chưa xử lý.
- DiscoveryClient, LoadBalancer hoặc Watcher được kiểm tra khi thiết kế yêu cầu.

## 15. Bài tập thực hành

Thực hiện các tình huống sau trên lab được phép thay đổi và khôi phục theo quy trình dự án sau khi ghi nhận kết quả:

1. Làm selector Service không khớp label Pod. So sánh Deployment rollout, EndpointSlice và lời gọi qua Service. Giải thích vì sao rollout vẫn có thể đạt.
2. Tạo sai một key ConfigMap được container tham chiếu bắt buộc. Dự đoán khác biệt giữa dry-run thành công và lỗi khi kubelet chuẩn bị container, rồi kiểm tra Events.
3. Cập nhật `demo.config-version` khi cấu hình được cấp qua biến môi trường. Đối chiếu ConfigMap trên API với giá trị ứng dụng trước và sau khi quy trình release tạo Pod mới.
4. Với ứng dụng discovery trực tiếp, dùng phép kiểm tra quyền phù hợp để xác định API thực tế cần đọc. Giải thích vì sao quyền của người vận hành không thay thế quyền ServiceAccount.

Mỗi tình huống cần ghi: biểu hiện, lệnh quan sát, lớp lỗi, nguyên nhân và bằng chứng phục hồi. Mục tiêu là chứng minh trạng thái triển khai từ manifest đến hành vi Spring, thay vì chỉ thu thập thông báo thành công của từng lệnh.
