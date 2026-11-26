# Quan sát log, event và trạng thái rollout

## 1. Ba nguồn bằng chứng trả lời ba câu hỏi khác nhau

Trong chương **Phát triển cục bộ** của module **SPRING_CLOUD_KUBERNETES**, quan sát giúp xác định lỗi nằm ở JVM, ở Kubernetes hay ở đường tích hợp giữa hai bên. Khi ứng dụng không đọc được ConfigMap, DiscoveryClient không tìm thấy instance hoặc bản triển khai mới chưa phục vụ, một dòng log riêng lẻ thường chưa đủ để kết luận.

Bài học này hướng dẫn một quy trình có thể áp dụng trên kind, minikube hoặc cụm phát triển tương đương: xác định đúng workload, đọc trạng thái, thu thập event và log, rồi kiểm chứng lại rollout cùng hành vi ứng dụng.

| Nguồn | Câu hỏi chính | Ví dụ bằng chứng |
| --- | --- | --- |
| Log container | Tiến trình đã làm gì, gặp lỗi nào? | Spring không tạo được bean, client nhận HTTP 403, request thất bại |
| Kubernetes Event | Thành phần Kubernetes đã quan sát hoặc thực hiện việc gì? | Không schedule được Pod, pull image thất bại, probe không đạt |
| Trạng thái tài nguyên và rollout | Trạng thái thực tế đã tiến tới cấu hình mong muốn đến đâu? | ReplicaSet mới chưa đủ Pod available, rollout chưa hoàn tất |

Một thông báo refresh bên trong Spring là sự kiện của ứng dụng; nó không tự trở thành Kubernetes Event. Tương tự, Kubernetes có thể báo container đã chạy nhưng không biết ứng dụng đang dùng sai giá trị cấu hình.

~~~mermaid
flowchart TD
    S["Triệu chứng: bản mới chưa phục vụ"] --> D["Xác định context, Deployment và revision"]
    D --> R["Đọc Deployment → ReplicaSet → Pod"]
    R --> E["Đọc Events của tài nguyên liên quan"]
    R --> L["Đọc log đúng Pod, container và lần chạy"]
    E --> T["Ghép timeline và kiểm tra giả thuyết"]
    L --> T
    T --> V["Sửa nguyên nhân và xác nhận rollout + hành vi"]
~~~

Mục tiêu không phải thu thập càng nhiều dữ liệu càng tốt. Mục tiêu là nối được **thay đổi nào → đối tượng nào → triệu chứng nào → bằng chứng nào**.

## 2. Chuẩn bị phạm vi quan sát

### 2.1. Hợp đồng của workload thực hành

Các lệnh dưới đây dùng một ứng dụng Spring đã triển khai trong cụm lab với các giá trị:

| Thông tin | Giá trị minh họa |
| --- | --- |
| Namespace | `sck-lab` |
| Deployment | `sck-demo` |
| Label trên Pod | `app=sck-demo` |
| Container ứng dụng | `app` |
| Cổng HTTP | 8080, có tên `http` |
| Endpoint readiness | `/actuator/health/readiness` |
| Service, nếu đã tạo | `sck-demo` |

Bạn có thể dùng ứng dụng của mình; hãy thay các giá trị theo manifest thực tế. Không cần một mã Java nghiệp vụ cụ thể để học cách quan sát.

Phần tạo lỗi ở cuối bài yêu cầu ứng dụng có Spring Boot Actuator, health probe được bật và đang hoạt động trên cổng 8080:

~~~properties
management.endpoints.web.exposure.include=health,info
management.endpoint.health.probes.enabled=true
~~~

Đường `/__lab_readiness_missing__` phải không được ứng dụng xử lý và trả HTTP 404. Cụm cần đủ tài nguyên cho hai Pod ổn định và một Pod tăng thêm khi rolling update. Chỉ thực hiện phần tạo lỗi trên workload lab riêng.

### 2.2. Đặt biến và xác nhận đúng cụm

Các ví dụ dùng PowerShell:

~~~powershell
$KubeContext = 'kind-sck-local'
$LabNamespace = 'sck-lab'
$DeploymentName = 'sck-demo'
$Selector = 'app=sck-demo'
$ContainerName = 'app'
~~~

Nếu dùng minikube, thay `$KubeContext` bằng tên context của profile, chẳng hạn `sck-local`. Mở terminal mới thì đặt lại các biến.

Kiểm tra:

~~~powershell
kubectl config get-contexts
kubectl --context $KubeContext -n $LabNamespace get deployment $DeploymentName
kubectl --context $KubeContext -n $LabNamespace get pods -l $Selector -o wide --show-labels
(Get-Date).ToUniversalTime().ToString('o')
~~~

Ghi giờ bắt đầu theo UTC để ghép với timestamp của log. Context và namespace cần xuất hiện trong ghi chép điều tra; một lỗi “không tìm thấy Pod” có thể chỉ do đang nhìn sai cụm.

### 2.3. Phân biệt quyền của người quan sát với quyền ứng dụng

Kiểm tra một số quyền của danh tính đang chạy kubectl:

~~~powershell
kubectl --context $KubeContext -n $LabNamespace auth can-i get deployments.apps
kubectl --context $KubeContext -n $LabNamespace auth can-i list pods
kubectl --context $KubeContext -n $LabNamespace auth can-i get pods --subresource=log
kubectl --context $KubeContext -n $LabNamespace auth can-i list events
~~~

Đọc log cần quyền trên subresource `pods/log`. Theo dõi tài nguyên có thể cần thêm `watch`; xem event còn phụ thuộc API event mà client sử dụng.

Các quyền này thuộc người quan sát. Quyền ứng dụng đọc ConfigMap, Secret, Service hoặc EndpointSlice thuộc ServiceAccount của Pod và phải được kiểm tra riêng. Không cấp quyền quản trị cụm cho ứng dụng chỉ để việc chẩn đoán dễ hơn.

## 3. Chụp trạng thái trước khi thay đổi hệ thống

### 3.1. Đi từ Deployment xuống đúng Pod

Bắt đầu bằng ảnh chụp tổng thể:

~~~powershell
kubectl --context $KubeContext -n $LabNamespace get deployment $DeploymentName -o wide
kubectl --context $KubeContext -n $LabNamespace get replicasets -l $Selector -o wide
kubectl --context $KubeContext -n $LabNamespace get pods -l $Selector -o wide
kubectl --context $KubeContext -n $LabNamespace describe deployment $DeploymentName
~~~

Deployment quản lý ReplicaSet; ReplicaSet quản lý Pod. Trong một rolling update, Pod của bản cũ và bản mới có thể tồn tại đồng thời. Label ứng dụng thường chọn cả hai nhóm, còn `pod-template-hash` giúp phân biệt template.

Từ danh sách Pod, chọn chính xác Pod cần điều tra:

~~~powershell
$PodName = 'sck-demo-<replicaset-hash>-<pod-suffix>'
kubectl --context $KubeContext -n $LabNamespace get pod $PodName -o jsonpath='{.spec.containers[*].name}'
kubectl --context $KubeContext -n $LabNamespace describe pod $PodName
~~~

Thay chuỗi minh họa bằng tên thực tế. Không lấy tùy tiện phần tử đầu tiên của danh sách vì nó có thể là một Pod cũ đang khỏe.

Kiểm tra danh tính và image mà không xuất toàn bộ manifest:

~~~powershell
$PodState = kubectl --context $KubeContext -n $LabNamespace get pod $PodName -o json | ConvertFrom-Json
$PodState.metadata | Select-Object name, uid, creationTimestamp
$PodState.metadata.ownerReferences | Select-Object kind, name, uid
$PodState.spec.containers | Select-Object name, image
$PodState.status.containerStatuses | Select-Object name, imageID, ready, restartCount
~~~

`image` là cấu hình mong muốn; `imageID` cho biết định danh image mà runtime ghi nhận. Tag có thể được dùng lại, vì vậy chỉ thấy cùng tag chưa chứng minh hai Pod chạy cùng nội dung.

### 3.2. Đọc trạng thái container thay vì chỉ nhìn cột STATUS

~~~powershell
$PodState.status.containerStatuses | Select-Object name, state, lastState, restartCount | ConvertTo-Json -Depth 8
~~~

| Dấu hiệu | Điều có thể kết luận | Điều chưa thể kết luận |
| --- | --- | --- |
| Pod phase `Running` | Pod đã được gán node và có container đang chạy hoặc trong quá trình khởi động/restart | Ứng dụng sẵn sàng phục vụ |
| `Ready=false` | Điều kiện sẵn sàng chưa đạt | JVM chắc chắn đã chết |
| `CrashLoopBackOff` | Một container đang bị lùi thời gian thử chạy lại sau lỗi lặp lại | Nguyên nhân gốc là gì |
| `restartCount` tăng | Container trong Pod đó đã restart | Đây là một đợt rollout mới |
| `lastState.terminated.reason=OOMKilled` | Runtime ghi nhận lần kết thúc trước liên quan OOM | Cách sửa chỉ là tăng heap |
| `exitCode=137` | Tiến trình đã kết thúc theo mã đó | Chắc chắn OOM nếu chưa có bằng chứng khác |

Kubernetes phân biệt phase của Pod, state của container và các condition; cột `STATUS` của kubectl là phần hiển thị tiện dụng, không phải một field duy nhất có thể thay thế tất cả các thông tin trên. Xem [vòng đời Pod](https://kubernetes.io/docs/concepts/workloads/pods/pod-lifecycle/).

Đừng restart hoặc xóa Pod ngay khi thấy lỗi. Những thao tác đó có thể thay đối tượng đang điều tra và làm mất log chưa được lưu ở hệ thống tập trung.

## 4. Đọc log đúng nguồn, đúng khoảng thời gian

### 4.1. Một Pod và một container

~~~powershell
kubectl --context $KubeContext -n $LabNamespace logs $PodName -c $ContainerName --tail=200 --since=15m --timestamps=true
~~~

Đặt rõ container khi Pod có sidecar. Một container proxy khỏe không chứng minh JVM khỏe, và log của init container không nằm trong log container ứng dụng.

Theo dõi tiếp:

~~~powershell
kubectl --context $KubeContext -n $LabNamespace logs $PodName -c $ContainerName --follow --tail=100 --timestamps=true
~~~

Dừng bằng `Ctrl+C`. Thao tác này dừng việc đọc log của terminal, không dừng ứng dụng.

Nếu container vừa restart:

~~~powershell
kubectl --context $KubeContext -n $LabNamespace logs $PodName -c $ContainerName --previous --tail=200 --timestamps=true
~~~

`--previous` đọc log instance container đã kết thúc trước đó trong **cùng Pod**, nếu còn. Nó không tìm log của Pod thuộc revision cũ đã bị xóa. Nếu chưa từng có instance trước hoặc log không còn, lỗi trả về là thông tin cần ghi nhận.

### 4.2. Nhiều replica và nhiều revision

~~~powershell
kubectl --context $KubeContext -n $LabNamespace logs -l $Selector -c $ContainerName --since=10m --tail=200 --timestamps=true --prefix=true --max-log-requests=10
~~~

Prefix giúp nhận diện Pod/container ở từng dòng. Đặt `--tail` tường minh vì truy vấn bằng selector có mặc định số dòng khác truy vấn một Pod.

Để theo dõi các Pod được chọn tại lúc bắt đầu:

~~~powershell
kubectl --context $KubeContext -n $LabNamespace logs -l $Selector -c $ContainerName --follow --tail=100 --timestamps=true --prefix=true --max-log-requests=10
~~~

Không giả định một phiên follow sẽ tự gắn vào mọi Pod mới sinh trong toàn bộ rollout. Kiểm tra lại danh sách Pod và chạy lại lệnh khi đối tượng thay đổi. Kết quả gộp từ nhiều luồng cũng không phải một timeline được sắp xếp toàn cục.

Tham số và hành vi đọc log được mô tả tại [kubectl logs](https://kubernetes.io/docs/reference/kubectl/generated/kubectl_logs/).

### 4.3. Init container, sidecar và khoảng trống log

Liệt kê các init container nếu có:

~~~powershell
$PodState.spec.initContainers | Select-Object name, image
$PodState.status.initContainerStatuses | ConvertTo-Json -Depth 8
~~~

Sau đó dùng tên chính xác với `kubectl logs <tên-pod> -c <tên-init-container>`, kèm context và namespace như các lệnh trước.

Không có log ứng dụng có thể là kết quả đúng: image chưa pull được, volume chưa mount được hoặc init container chưa hoàn tất nên JVM chưa chạy. Khi đó, chuyển sang trạng thái và event trước khi sửa cấu hình logging.

Log chuẩn của container thường đi qua stdout/stderr. Tệp log riêng bên trong container không tự xuất hiện trong `kubectl logs`. Log cục bộ còn chịu cơ chế rotation và vòng đời node/Pod; nếu cần lưu bền vững hoặc tra cứu lịch sử dài, dùng hệ thống thu thập log phù hợp. Xem [kiến trúc logging của Kubernetes](https://kubernetes.io/docs/concepts/cluster-administration/logging/).

## 5. Đọc Event để biết Kubernetes đang làm gì

### 5.1. Quan sát cả namespace rồi thu hẹp

~~~powershell
kubectl --context $KubeContext -n $LabNamespace get events --sort-by=.metadata.creationTimestamp
kubectl --context $KubeContext -n $LabNamespace events --types=Warning
kubectl --context $KubeContext -n $LabNamespace events --for "pod/$PodName"
~~~

Để theo dõi trong lúc tái hiện:

~~~powershell
kubectl --context $KubeContext -n $LabNamespace events --for "pod/$PodName" --watch
~~~

Nếu phiên bản kubectl không có subcommand `events`, dùng `get events` và `describe`. Xác nhận tùy chọn của client bằng `kubectl events --help`.

Lọc theo Deployment chỉ cho event gắn trực tiếp với Deployment đó; nó không tự thu thập đệ quy mọi event của ReplicaSet và Pod. Vì vậy cần đi theo quan hệ sở hữu đã xác định ở phần trước. Tham khảo [kubectl events](https://kubernetes.io/docs/reference/kubectl/generated/kubectl_events/).

Khi cần gắn chặt với một đời Pod, lọc UID:

~~~powershell
$PodUid = $PodState.metadata.uid
kubectl --context $KubeContext -n $LabNamespace get events --field-selector "involvedObject.uid=$PodUid" --sort-by=.metadata.creationTimestamp
~~~

Lệnh này dùng các field của tài nguyên Event mà `kubectl get events` truy vấn theo cách thông thường. UID giúp phân biệt đối tượng đã bị xóa rồi được tạo lại với cùng tên.

### 5.2. Diễn giải reason cùng message và đối tượng

| Event reason thường gặp | Hướng kiểm tra |
| --- | --- |
| `FailedScheduling` | Requests, tài nguyên node, taint, affinity và giới hạn scheduling |
| `FailedCreate` trên ReplicaSet | Quota, policy hoặc quyền khiến Pod chưa được tạo |
| `FailedMount` | Volume, tên ConfigMap/Secret, nguồn lưu trữ và message chi tiết |
| `Failed` hoặc `BackOff` liên quan pull image | Image/tag, registry, xác thực và kết nối từ node |
| `Unhealthy` | Loại probe, URL, cổng và nội dung lỗi probe |
| `BackOff` khi restart container | Last State và log `--previous` |
| `ScalingReplicaSet` | Controller đang thay đổi số replica ở ReplicaSet nào |

Reason không đủ để định danh lỗi. Hai event có reason `BackOff` có thể nói về pull image hoặc restart container, tùy message. Một event `Warning` đã xảy ra trước đó cũng có thể đã được khắc phục; hãy đối chiếu trạng thái hiện tại.

`Normal` không có nghĩa là vô ích. Chuỗi schedule → pull → create → start giúp chỉ ra Kubernetes đã đi được tới đâu trước khi lỗi ứng dụng xuất hiện.

### 5.3. Event không phải nhật ký đầy đủ của hệ thống

Một record event có thể được gộp qua nhiều lần lặp. Hãy đọc số lần, thời điểm đầu/cuối hoặc thông tin series khi API cung cấp chúng. Sắp xếp theo `metadata.creationTimestamp` chỉ sắp xếp thời điểm tạo record, không biến các lần lặp thành những dòng độc lập.

Event được giữ trong một khoảng thời gian hữu hạn do cụm quyết định. Không có event không chứng minh rằng không từng có lỗi, và Event không thay thế audit log hoặc log nghiệp vụ.

Khi ghép timeline, phân biệt ba mốc: thời điểm ứng dụng ghi log, thời điểm thành phần Kubernetes quan sát lỗi và thời điểm bạn lấy dữ liệu. Với log nhiều Pod, giữ cả timestamp và nguồn để tránh suy diễn thứ tự từ vị trí dòng trên màn hình.

## 6. Hiểu trạng thái rollout trước khi kết luận thành công

### 6.1. Đọc các bộ đếm và condition

~~~powershell
$DeploymentState = kubectl --context $KubeContext -n $LabNamespace get deployment $DeploymentName -o json | ConvertFrom-Json
$DeploymentState.metadata | Select-Object name, generation
$DeploymentState.spec | Select-Object replicas, minReadySeconds, progressDeadlineSeconds
$DeploymentState.status | Select-Object observedGeneration, replicas, updatedReplicas, readyReplicas, availableReplicas, unavailableReplicas
$DeploymentState.status.conditions | Format-Table type, status, reason, message -Wrap
~~~

| Field | Cách đọc |
| --- | --- |
| `spec.replicas` | Số replica mong muốn |
| `status.updatedReplicas` | Số replica dùng Pod template hiện tại |
| `status.readyReplicas` | Số replica đang Ready, có thể gồm bản cũ |
| `status.availableReplicas` | Số replica đã đáp ứng điều kiện available, xét `minReadySeconds` |
| `metadata.generation` | Thế hệ cấu hình mong muốn của Deployment |
| `status.observedGeneration` | Thế hệ mà controller đã quan sát để cập nhật trạng thái |

Nếu `observedGeneration` còn thấp hơn `generation`, đừng dùng status cũ để kết luận cho cấu hình vừa gửi. Revision, generation và image tag là ba khái niệm khác nhau; scale số replica có thể đổi generation mà không tạo một revision Pod template mới.

Một Deployment có `Available=True` có thể vẫn đang phục vụ bằng Pod cũ trong lúc Pod mới lỗi. `Progressing=True` cũng cần đọc kèm reason để phân biệt đang tiến triển với đã hoàn tất.

Ví dụ condition rút gọn:

~~~text
TYPE          STATUS   REASON
Available     True     MinimumReplicasAvailable
Progressing   False    ProgressDeadlineExceeded
~~~

Diễn giải: workload vẫn đạt mức available tối thiểu, nhưng rollout không tiến triển đúng hạn. Không thể kết luận bản mới đã được triển khai thành công. Xem [trạng thái và condition của Deployment](https://kubernetes.io/docs/concepts/workloads/controllers/deployment/).

### 6.2. Chờ rollout với thời hạn rõ ràng

~~~powershell
kubectl --context $KubeContext -n $LabNamespace rollout status "deployment/$DeploymentName" --timeout=180s
$RolloutExitCode = $LASTEXITCODE
$RolloutExitCode
~~~

Ghi nhận exit code ngay sau lệnh. Nếu khác 0, quay lại describe, Pod, event và log; không tiếp tục quy trình như thể rollout đã thành công.

Phân biệt:

| Giới hạn | Ai sử dụng? | Ý nghĩa |
| --- | --- | --- |
| `--timeout=180s` | Tiến trình kubectl | Sau khoảng chờ này, client dừng đợi nếu chưa đạt kết quả |
| `spec.progressDeadlineSeconds` | Deployment controller | Khoảng thời gian không tiến triển trước khi báo rollout bị đình trệ |
| `spec.minReadySeconds` | Deployment controller | Thời gian Pod cần giữ Ready để được tính là available |

Client timeout không hủy rollout. Vượt progress deadline không tự động rollback; controller vẫn có thể tiếp tục điều hòa và rollout có thể phục hồi khi nguyên nhân được giải quyết. Deadline theo dõi tiến triển, không nên hiểu thành giới hạn tổng thời gian tuyệt đối cho mọi rollout. Xem [API Deployment](https://kubernetes.io/docs/reference/kubernetes-api/apps/deployment-v1/).

### 6.3. Gắn kết quả với đúng revision

~~~powershell
kubectl --context $KubeContext -n $LabNamespace rollout history "deployment/$DeploymentName"
~~~

Lấy revision từ Deployment đã được controller xử lý:

~~~powershell
$DeploymentState = kubectl --context $KubeContext -n $LabNamespace get deployment $DeploymentName -o json | ConvertFrom-Json
$DeploymentState.metadata.annotations.'deployment.kubernetes.io/revision'
~~~

Nếu cần theo dõi một revision đã xác định, ví dụ revision 3:

~~~powershell
$Revision = 3
kubectl --context $KubeContext -n $LabNamespace rollout status "deployment/$DeploymentName" --revision=$Revision --timeout=180s
~~~

Thay 3 bằng revision thực tế. Mặc định, `rollout status` theo rollout mới nhất và có thể chuyển sang revision mới nếu một thay đổi khác xảy ra. `--revision` giúp phát hiện việc revision đang theo dõi bị thay thế. Tham khảo [kubectl rollout status](https://kubernetes.io/docs/reference/kubectl/generated/kubectl_rollout/kubectl_rollout_status/).

Sau một thay đổi, annotation revision có thể chưa kịp cập nhật. Đối chiếu generation, observedGeneration và ReplicaSet thay vì đọc ngay giá trị annotation cũ rồi gán nó cho rollout mới.

## 7. Quan sát các lỗi tích hợp Spring Cloud Kubernetes

### 7.1. Không đọc được ConfigMap hoặc Secret

Một chuỗi bằng chứng có thể là:

~~~text
Event: container đã được tạo và bắt đầu chạy
Log ứng dụng: yêu cầu đọc ConfigMap trả HTTP 403
Log ứng dụng: khởi tạo Spring context thất bại
Pod: restartCount tăng
Deployment: updated replica chưa available
~~~

Đây là tình huống minh họa, không phải chuỗi log bắt buộc của mọi phiên bản.

Kiểm tra danh tính và tài nguyên được yêu cầu:

~~~powershell
$PodState.spec.serviceAccountName
kubectl --context $KubeContext -n $LabNamespace get rolebindings
~~~

Nếu được phép impersonate, có thể kiểm tra quyền của ServiceAccount đã xác nhận:

~~~powershell
$ServiceAccountName = $PodState.spec.serviceAccountName
kubectl --context $KubeContext -n $LabNamespace auth can-i get configmaps --as="system:serviceaccount:$($LabNamespace):$($ServiceAccountName)"
kubectl --context $KubeContext -n $LabNamespace auth can-i list configmaps --as="system:serviceaccount:$($LabNamespace):$($ServiceAccountName)"
~~~

Chọn verb theo request lỗi; quyền `get` không bảo đảm quyền `list` hoặc `watch`. Nếu danh tính quan sát không được impersonate, lỗi của lệnh này chưa kết luận được quyền của ứng dụng. Đối chiếu [quyền ServiceAccount trong Spring Cloud Kubernetes](https://docs.spring.io/spring-cloud-kubernetes/reference/security-service-accounts.html).

Một số chế độ đọc cấu hình có thể cho phép ứng dụng tiếp tục với nguồn khác khi không tải được ConfigMap. Khi đó, rollout thành công vẫn chưa chứng minh cấu hình Kubernetes đã được dùng. Kiểm tra tên nguồn, namespace, chính sách fail-fast và một dấu hiệu cấu hình không nhạy cảm theo [ConfigMap PropertySource](https://docs.spring.io/spring-cloud-kubernetes/reference/property-source-config/configmap-propertysource.html).

Không dump Secret, token ServiceAccount hoặc toàn bộ Environment để chứng minh cấu hình đã vào. Hãy quan sát sự tồn tại hoặc mã phiên bản cấu hình không nhạy cảm do ứng dụng chủ động công bố.

### 7.2. DiscoveryClient không trả instance hoặc lời gọi bị lỗi

Trước hết xác định caller nằm trong IDE hay trong Pod. Truy cập API server thành công không chứng minh caller có route tới địa chỉ Pod nhận từ discovery.

Kiểm tra lớp Kubernetes:

~~~powershell
kubectl --context $KubeContext -n $LabNamespace get service sck-demo
kubectl --context $KubeContext -n $LabNamespace get pods -l $Selector --show-labels
kubectl --context $KubeContext -n $LabNamespace get endpointslices -l kubernetes.io/service-name=sck-demo -o yaml
~~~

Đối chiếu selector, cổng, địa chỉ backend và condition `ready` trong EndpointSlice; xem [EndpointSlices](https://kubernetes.io/docs/concepts/services-networking/endpoint-slices/).

Sau đó mới kiểm tra namespace, bộ lọc service, quyền đọc tài nguyên và cơ chế endpoint mà DiscoveryClient đang dùng. Một client dùng Endpoints và một client bật EndpointSlice có yêu cầu API/RBAC khác nhau; xem [DiscoveryClient](https://docs.spring.io/spring-cloud-kubernetes/reference/discovery-client.html).

Nếu Spring Cloud LoadBalancer thông báo không có instance, xem đó là triệu chứng phía client: cần chứng minh dữ liệu discovery đầu vào và cách chọn service ID trước khi thay thuật toán cân bằng tải. Không suy từ log load balancer rằng Deployment backend chắc chắn đã hỏng.

### 7.3. Configuration Watcher có log nhưng ứng dụng chưa đổi cấu hình

Quan sát theo chuỗi:

1. ConfigMap/Secret đúng nguồn đã thay đổi.
2. Watcher quan sát đúng namespace và chọn nguồn đó.
3. Watcher tìm đúng các instance cần thông báo.
4. Thông báo refresh đến được từng instance.
5. Ứng dụng đọc lại nguồn phù hợp và hành vi thay đổi như kỳ vọng.

Nếu đã triển khai watcher, lấy đúng tên Deployment và selector từ manifest của nó rồi đọc log theo cùng quy trình nhiều replica ở phần 4. So sánh timestamp log watcher với log của **từng** instance ứng dụng.

Cơ chế HTTP của Configuration Watcher sử dụng discovery để gửi yêu cầu refresh tới các instance phù hợp. Quy tắc chọn nguồn và cách cấu hình cần đối chiếu đúng phiên bản ở [Configuration Watcher](https://docs.spring.io/spring-cloud-kubernetes/reference/spring-cloud-kubernetes-configuration-watcher.html).

Thay đổi dữ liệu ConfigMap thường không làm Pod template thay đổi, nên không nhất thiết có revision Deployment mới. ResourceVersion mới chỉ chứng minh đối tượng Kubernetes đổi, chưa chứng minh bean đã nhận cấu hình.

Nếu ứng dụng lấy cấu hình từ biến môi trường của container, thay ConfigMap không cập nhật environment của tiến trình đang chạy. Cần tạo lại container bằng quy trình phù hợp; xem [các cách sử dụng ConfigMap](https://kubernetes.io/docs/concepts/configuration/configmap/). Đừng dùng một rollout không đổi làm bằng chứng rằng refresh đã thành công.

## 8. Thực hành: rollout kẹt trong khi ứng dụng vẫn có Pod khỏe

Bài thực hành tạo lỗi readiness để quan sát một tình huống dễ bị bỏ sót: JVM mới vẫn chạy, log khởi động có vẻ bình thường, nhưng Kubernetes chưa đưa Pod mới vào trạng thái sẵn sàng.

### 8.1. Thiết lập baseline trên workload lab

Trước khi thay đổi, ghi lại số replica, strategy, deadline và readiness hiện tại. Nếu workload do GitOps hoặc công cụ khác điều hòa, thực hiện bài tập trong bản sao lab để các thay đổi không bị ghi đè giữa chừng.

Tạo `observation-policy-patch.yaml`:

~~~yaml
spec:
  replicas: 2
  minReadySeconds: 5
  progressDeadlineSeconds: 120
  revisionHistoryLimit: 5
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxSurge: 1
      maxUnavailable: 0
~~~

Áp dụng:

~~~powershell
kubectl --context $KubeContext -n $LabNamespace patch deployment $DeploymentName --type=merge --patch-file=observation-policy-patch.yaml
kubectl --context $KubeContext -n $LabNamespace rollout status "deployment/$DeploymentName" --timeout=180s
~~~

Chỉ tiếp tục khi baseline khỏe, hai replica đạt available và readiness đang trỏ đúng endpoint. Nếu thao tác này thất bại, điều tra baseline trước.

Ghi revision có Pod template khỏe:

~~~powershell
$BaselineDeployment = kubectl --context $KubeContext -n $LabNamespace get deployment $DeploymentName -o json | ConvertFrom-Json
$HealthyRevision = [int]($BaselineDeployment.metadata.annotations.'deployment.kubernetes.io/revision')
$HealthyRevision
kubectl --context $KubeContext -n $LabNamespace rollout history "deployment/$DeploymentName" --revision=$HealthyRevision
~~~

Revision này được dùng làm đích phục hồi. Không để một người hoặc một automation khác cập nhật Deployment trong lúc thực hiện.

### 8.2. Mở các cửa sổ quan sát

Trong terminal thứ nhất:

~~~powershell
kubectl --context $KubeContext -n $LabNamespace get pods -l $Selector -w -o wide
~~~

Trong terminal thứ hai:

~~~powershell
kubectl --context $KubeContext -n $LabNamespace events --watch
~~~

Đặt lại các biến trong từng terminal. Terminal thứ ba dùng để tạo thay đổi và lấy ảnh chụp trạng thái. Phiên theo dõi không thay thế ảnh chụp cuối cùng khi kết luận.

### 8.3. Làm readiness trỏ vào đường dẫn không tồn tại

Tạo `bad-readiness-patch.yaml`:

~~~yaml
spec:
  template:
    spec:
      containers:
        - name: app
          readinessProbe:
            httpGet:
              path: /__lab_readiness_missing__
              port: http
            periodSeconds: 5
            timeoutSeconds: 2
            failureThreshold: 3
~~~

Trong baseline của bài, readiness dùng HTTP GET và container tên `app`. Nếu workload của bạn có cấu hình probe khác, dùng bản sao phù hợp trước khi áp dụng patch.

~~~powershell
kubectl --context $KubeContext -n $LabNamespace patch deployment $DeploymentName --type=strategic --patch-file=bad-readiness-patch.yaml
kubectl --context $KubeContext -n $LabNamespace rollout status "deployment/$DeploymentName" --timeout=30s
~~~

Strategic merge ghép danh sách container theo `name` nên patch này sửa container `app` và giữ các container khác. Dùng tệp patch cũng tránh lỗi escape chuỗi JSON giữa các shell; xem [kubectl patch](https://kubernetes.io/docs/reference/kubectl/generated/kubectl_patch/).

Khoảng chờ 30 giây chỉ dành cho client; chưa đủ để mặc định kết luận đã vượt deadline 120 giây ở controller.

### 8.4. Ghép các nguồn bằng chứng

Lấy trạng thái mới:

~~~powershell
kubectl --context $KubeContext -n $LabNamespace get replicasets -l $Selector -o wide
kubectl --context $KubeContext -n $LabNamespace get pods -l $Selector -o wide
kubectl --context $KubeContext -n $LabNamespace describe deployment $DeploymentName
~~~

Chọn Pod của ReplicaSet mới, cập nhật `$PodName`, rồi đọc:

~~~powershell
kubectl --context $KubeContext -n $LabNamespace describe pod $PodName
kubectl --context $KubeContext -n $LabNamespace logs $PodName -c $ContainerName --tail=100 --timestamps=true
kubectl --context $KubeContext -n $LabNamespace events --for "pod/$PodName"
~~~

Trong điều kiện baseline không có lỗi khác, có thể thấy:

| Nguồn | Bằng chứng kỳ vọng |
| --- | --- |
| Pod cũ | Hai Pod vẫn Ready |
| Pod mới | Container chạy nhưng readiness không đạt |
| Log Spring của Pod mới | Ứng dụng khởi động được, không nhất thiết có stack trace |
| Event của Pod mới | Readiness probe nhận HTTP 404 |
| ReplicaSet | Có nhóm cũ và nhóm mới |
| Rollout | Chờ Pod mới available, chưa hoàn tất |

Với hai replica mong muốn, `maxSurge=1` và `maxUnavailable=0`, ảnh chụp có thể có ba Pod: hai cũ available và một mới chưa Ready. Các giá trị minh họa:

~~~text
spec.replicas:             2
status.replicas:           3
status.updatedReplicas:    1
status.readyReplicas:      2
status.availableReplicas:  2
~~~

Đây là ảnh chụp một thời điểm, không phải mọi lần chạy đều phải hiện đúng cùng số ở mọi giây. Nó cho thấy vì sao “vẫn có hai Pod Ready” chưa đủ để chứng minh rollout bản mới hoàn tất.

Readiness thất bại tự nó không yêu cầu kubelet restart container. Nếu liveness và startup vẫn khỏe, restartCount có thể giữ nguyên. Startup/liveness thất bại có hệ quả khác; xem [các loại probe](https://kubernetes.io/docs/tasks/configure-pod-container/configure-liveness-readiness-startup-probes/).

Sau khi không có tiến triển đủ lâu, kiểm tra lại condition:

~~~powershell
kubectl --context $KubeContext -n $LabNamespace rollout status "deployment/$DeploymentName" --timeout=180s
kubectl --context $KubeContext -n $LabNamespace describe deployment $DeploymentName
~~~

Có thể thấy `Progressing=False`, reason `ProgressDeadlineExceeded` trong khi `Available=True` vẫn tồn tại nhờ Pod cũ. Đừng xóa các Pod cũ để “ép” bản mới nhận traffic; hãy sửa readiness.

### 8.5. Phục hồi và xác nhận

Sau khi đã thu thập bằng chứng, phục hồi Pod template đã ghi nhận:

~~~powershell
kubectl --context $KubeContext -n $LabNamespace rollout undo "deployment/$DeploymentName" --to-revision=$HealthyRevision
kubectl --context $KubeContext -n $LabNamespace rollout status "deployment/$DeploymentName" --timeout=180s
kubectl --context $KubeContext -n $LabNamespace get pods -l $Selector -o wide
~~~

`rollout undo` phụ thuộc lịch sử revision còn được giữ; xem [kubectl rollout undo](https://kubernetes.io/docs/reference/kubectl/generated/kubectl_rollout/kubectl_rollout_undo/).

Undo phục hồi Pod template, không hoàn tác mọi thay đổi của Deployment và không phục hồi nội dung ConfigMap/Secret bên ngoài. Số replica, policy quan sát hoặc dữ liệu cấu hình được đổi riêng phải được khôi phục riêng nếu cần. Không mặc định revision hiện tại sau phục hồi sẽ mang số cũ.

Kiểm tra readiness đã đúng và thử một endpoint nghiệp vụ của ứng dụng. Nếu Service chỉ phục vụ Pod cũ trước đó, chỉ kiểm tra HTTP thành công trong lúc rollout kẹt sẽ bỏ sót lỗi; sau phục hồi cần xác nhận cả revision/template đang chạy.

Cuối bài, dừng các terminal watch bằng `Ctrl+C`, đưa cấu hình workload về trạng thái mong muốn đã ghi ở baseline và bỏ các patch gây lỗi khỏi quy trình apply thường ngày.

## 9. Ghi log Spring đủ để liên kết các bằng chứng

### 9.1. Ghi thông tin nhận dạng có chủ đích

Một dòng log tốt phục vụ điều tra nên cho biết:

- Tên ứng dụng và build đang chạy.
- Pod, namespace hoặc thông tin đủ để nối với metadata Kubernetes.
- Thành phần đang xử lý: config, discovery, refresh hoặc nghiệp vụ.
- Kết quả và mã tương quan khi có.
- Thông báo lỗi đủ chẩn đoán, đã loại dữ liệu nhạy cảm.

Có thể đưa metadata vào Pod bằng Downward API:

~~~yaml
env:
  - name: POD_NAME
    valueFrom:
      fieldRef:
        fieldPath: metadata.name
  - name: POD_NAMESPACE
    valueFrom:
      fieldRef:
        fieldPath: metadata.namespace
  - name: APP_BUILD
    value: "dev-002"
~~~

Đây là đoạn đặt dưới container trong manifest, không phải một tài nguyên độc lập. `APP_BUILD` cần được quy trình build/deploy gán đúng; một giá trị tự khai báo không thay thế image digest.

Ví dụ lớp Java bổ sung vào package của ứng dụng Spring Boot:

~~~java
package com.example.sckdemo;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.ApplicationRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.env.Environment;

@Configuration
public class ObservationConfiguration {

    private static final Logger log =
        LoggerFactory.getLogger(ObservationConfiguration.class);

    @Bean
    ApplicationRunner logRuntimeIdentity(Environment environment) {
        return args -> log.info(
            "runtime_identity app={} build={} pod={} namespace={}",
            environment.getProperty("spring.application.name", "unknown"),
            environment.getProperty("APP_BUILD", "unknown"),
            environment.getProperty("POD_NAME", "local"),
            environment.getProperty("POD_NAMESPACE", "local")
        );
    }
}
~~~

Dòng này hỗ trợ liên kết lần chạy JVM với workload. Nó không chứng minh nguồn cấu hình Kubernetes đã được đọc hoặc ứng dụng đã sẵn sàng phục vụ; các phép kiểm tra đó cần bằng chứng riêng.

### 9.2. Bật mức log có giới hạn

Cấu hình khởi đầu:

~~~properties
logging.level.root=INFO
logging.level.org.springframework.cloud.kubernetes=DEBUG
~~~

Chỉ bật DEBUG của package liên quan trong thời gian tái hiện lỗi. Xác nhận tên logger ở phiên bản đang dùng và đưa lại mức bình thường khi đã đủ bằng chứng. Việc thêm cấu hình log vào Pod template có thể tự tạo rollout mới; ghi nhận thay đổi này trong timeline.

Spring Boot hỗ trợ cấu hình mức log theo logger và mặc định có console logging; xem [logging của Spring Boot](https://docs.spring.io/spring-boot/reference/features/logging.html).

Không bật TRACE toàn bộ HTTP client hoặc in request header để tìm lỗi 403; cách đó có thể đưa token, cookie hoặc Secret vào log. Thường thông tin method, resource, namespace, status code và danh tính workload đã đủ để bắt đầu kiểm tra quyền.

## 10. Quy trình chẩn đoán dùng trong vòng lặp phát triển

### 10.1. Thứ tự kiểm tra khi bản mới chưa phục vụ

1. **Chốt phạm vi:** context, namespace, Deployment, thời điểm và thay đổi gần nhất.
2. **Chốt đối tượng:** revision/template, ReplicaSet, Pod UID, container và imageID.
3. **Đọc trạng thái:** scheduling, container state, restartCount, readiness và condition Deployment.
4. **Đọc event:** bắt đầu với đối tượng lỗi, mở rộng lên ReplicaSet/Deployment khi cần.
5. **Đọc log:** container hiện tại; thêm `--previous` nếu container đã restart.
6. **Đặt giả thuyết:** tài nguyên nào, request nào hoặc probe nào đang thất bại.
7. **Thay đổi có mục đích:** sửa một nguyên nhân đã có bằng chứng, ghi lại thời điểm.
8. **Kiểm chứng:** rollout đúng revision, Pod khỏe, hành vi nghiệp vụ và tích hợp đúng.

Nếu Pod chưa được tạo, ưu tiên Deployment/ReplicaSet và event; không tiếp tục chạy logs trên một tên Pod không tồn tại. Nếu JVM chưa chạy, event về image/volume/init container thường hữu ích hơn việc đổi log level Spring.

### 10.2. Bảng định hướng nhanh

| Triệu chứng | Bằng chứng đầu tiên | Bước kiểm tra tiếp |
| --- | --- | --- |
| Chưa có Pod mới | Condition Deployment và describe ReplicaSet | Quota, policy, trạng thái controller |
| Pod Pending | Describe Pod và FailedScheduling | Requests, node, affinity/taint |
| Image không chạy | Waiting reason và event pull | Tag, registry, quyền pull, image đã load vào node |
| Container restart | Last State và log previous | Lỗi khởi động, OOM, probe hoặc kết thúc tiến trình |
| JVM chạy, Pod chưa Ready | Event probe và cấu hình readiness | Cổng, URL, bảo vệ endpoint và tình trạng ứng dụng |
| Client nhận 403 khi đọc API | Log có verb/resource/namespace | ServiceAccount và quyền tương ứng |
| Discovery trả rỗng | Log caller và trạng thái backend | Service selector, namespace, bộ lọc và quyền API |
| Refresh chỉ tác động một replica | Log watcher cùng từng Pod | Danh sách instance, kết nối và nguồn cấu hình |
| Rollout báo thành công, giá trị vẫn sai | Marker cấu hình và hành vi ứng dụng | Nguồn cấu hình, ưu tiên và cơ chế cập nhật |
| Watch/log không có dữ liệu | Lệnh, selector và quyền quan sát | Đúng context, đúng Pod/container, lịch sử còn được giữ |

Nếu nghi thiếu CPU hoặc memory, `kubectl top pods` chỉ hữu ích khi cụm đã có metrics API hoạt động. Không có metrics không làm mất giá trị của Events, Last State và các giới hạn tài nguyên trong manifest.

### 10.3. Mẫu ghi nhận kết quả điều tra

~~~text
Context / namespace:
Deployment / revision / generation:
Thay đổi gần nhất và thời điểm UTC:
Pod name / UID / container:
Image / imageID:

Triệu chứng:
Event liên quan, số lần và thời điểm:
Trạng thái container hiện tại / lần trước:
Log liên quan, nguồn và timestamp:

Giả thuyết:
Bằng chứng ủng hộ:
Bằng chứng còn thiếu:
Thay đổi đã thực hiện:

Kết quả rollout và revision đã xác nhận:
Kết quả health:
Kết quả hành vi nghiệp vụ / config / discovery / refresh:
Giới hạn của kết luận:
~~~

Mẫu này giúp người khác kiểm tra lại lập luận mà không cần đọc toàn bộ terminal. Chỉ đính kèm đoạn log liên quan, đã loại dữ liệu nhạy cảm; nếu chia sẻ bản xuất manifest, rà soát cả giá trị environment được khai báo trực tiếp.

## 11. Tiêu chí hoàn thành

Bạn hoàn thành bài học khi thực hiện được những việc sau trên workload lab:

- [ ] Chỉ đúng context, namespace, Deployment và Pod cần quan sát.
- [ ] Phân biệt được revision, ReplicaSet, Pod UID và lần chạy container.
- [ ] Đọc log có timestamp và nhận diện nguồn khi có nhiều replica.
- [ ] Dùng được `--previous` và giải thích trường hợp không có log trước.
- [ ] Tìm được event của Pod lỗi và biết khi nào phải xem thêm ReplicaSet.
- [ ] Phân biệt được `Running`, `Ready`, `Available` và rollout hoàn tất.
- [ ] Giải thích được client timeout khác progress deadline như thế nào.
- [ ] Tái hiện lỗi readiness, chứng minh bản cũ vẫn khỏe nhưng bản mới chưa available.
- [ ] Phục hồi Pod template khỏe và kiểm chứng lại rollout cùng hành vi ứng dụng.
- [ ] Phân biệt được lỗi RBAC của workload với lỗi quyền quan sát của người chạy kubectl.
- [ ] Biết rằng log watcher hoặc rollout thành công chưa đủ chứng minh refresh cấu hình.
- [ ] Giữ log và bằng chứng đủ dùng mà không để lộ Secret.

Một kết luận tốt có thể viết: “Revision mới tạo được JVM nhưng chưa available vì readiness nhận HTTP 404; hai Pod cũ vẫn phục vụ. Sau khi phục hồi probe đúng, rollout hoàn tất và endpoint nghiệp vụ hoạt động.” Kết luận đó nêu rõ đối tượng, nguyên nhân, bằng chứng và kết quả kiểm chứng.
