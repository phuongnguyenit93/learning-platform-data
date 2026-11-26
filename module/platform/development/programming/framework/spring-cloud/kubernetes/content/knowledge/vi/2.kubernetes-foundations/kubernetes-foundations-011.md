# Đọc manifest và quan sát tài nguyên bằng kubectl

## Mục tiêu bài học

Manifest Kubernetes là bản mô tả trạng thái mong muốn của tài nguyên. Lệnh kubectl là công cụ để gửi yêu cầu đến API Server, xem trạng thái đã được ghi nhận, đọc sự kiện và thu thập bằng chứng khi ứng dụng Spring gặp vấn đề. Đọc đúng cả manifest lẫn trạng thái thực tế giúp phân biệt “đã khai báo” với “đang hoạt động”.

Bài thuộc chương **Nền tảng Kubernetes** của module **SPRING_CLOUD_KUBERNETES**. Module học tích hợp ứng dụng Spring với Kubernetes qua DiscoveryClient, ConfigMap, Secret, Spring Cloud LoadBalancer và Configuration Watcher; đồng thời thực hành RBAC, cập nhật cấu hình, theo dõi sức khỏe Pod và lựa chọn tính năng Spring Cloud Kubernetes thực sự cần cho triển khai.

Sau bài này, bạn có thể:

- Đọc các trường chính của một manifest Kubernetes.
- Theo dõi quan hệ giữa Deployment, ReplicaSet, Pod và Service.
- Dùng kubectl để xem trạng thái, mô tả tài nguyên, đọc log và sự kiện.
- Kiểm tra label, selector, endpoint, probe và cấu hình của Pod.
- Tránh nhầm context, namespace hoặc trạng thái khai báo với trạng thái quan sát được.
- Thu thập một bộ bằng chứng có thứ tự khi ứng dụng Spring không nhận traffic hoặc không đọc được cấu hình.

## 1. Manifest và trạng thái thực tế

Một manifest thường có bốn nhóm trường chính:

    apiVersion
    kind
    metadata
    spec

Kubernetes lưu thêm trạng thái quan sát được trong trường status của object. Có thể hình dung:

    manifest
      → trạng thái mong muốn trong spec
      → controller và kubelet thực hiện
      → status, conditions, events và log

Ví dụ, Deployment có spec.replicas bằng ba nghĩa là mong muốn có ba replica. Nó chưa chứng minh đã có ba Pod Ready. Muốn biết kết quả, cần xem status của Deployment, ReplicaSet và Pod.

| Phần | Ý nghĩa | Ví dụ câu hỏi |
| --- | --- | --- |
| apiVersion | Nhóm API và phiên bản schema | Tài nguyên này thuộc API nào? |
| kind | Loại tài nguyên | Đây là Deployment, Service hay ConfigMap? |
| metadata | Tên, namespace, labels, annotations | Object có tên gì và thuộc namespace nào? |
| spec | Trạng thái mong muốn | Muốn chạy image nào, bao nhiêu replica, selector nào? |
| status | Trạng thái controller quan sát được | Bao nhiêu replica đã cập nhật và sẵn sàng? |

Manifest là đầu vào cho API Server, còn kubectl get, describe, logs và events cung cấp các góc nhìn khác nhau về kết quả. Không nên dùng một lệnh đơn lẻ để kết luận toàn bộ hệ thống.

## 2. Ngữ cảnh làm việc của kubectl

### 2.1. Context, cluster, user và namespace

kubectl dùng kubeconfig để chọn context. Context thường liên kết một cluster, một user và có thể có namespace mặc định. Một lệnh đúng cú pháp nhưng chạy nhầm context có thể trả về dữ liệu hợp lệ của cluster khác.

Trước khi quan sát tài nguyên, cần xác định:

- context hiện tại;
- cluster đang kết nối;
- user hoặc credential được dùng;
- namespace mặc định;
- namespace của workload;
- quyền của danh tính đang chạy kubectl.

Các lệnh kiểm tra thường dùng:

    kubectl config current-context
    kubectl config get-contexts
    kubectl config view --minify

Không nên đưa kubeconfig chứa credential vào log hoặc chia sẻ nguyên file. Khi làm việc production, phải tuân thủ cơ chế cấp quyền của tổ chức và xác nhận context trước lệnh có tác động.

### 2.2. Namespace phải được chỉ rõ khi cần

Nếu không dùng tùy chọn namespace, kubectl có thể dùng namespace mặc định của context. Tài nguyên ở namespace khác sẽ không xuất hiện trong kết quả, tạo cảm giác “không tồn tại”.

Ví dụ:

    kubectl get pods -n team-a
    kubectl get deployment order-service -n team-a
    kubectl get service inventory -n team-a

Để tránh lặp lại, có thể đặt namespace cho một context theo quy trình được kiểm soát. Dù vậy, khi viết runbook hoặc lệnh chẩn đoán, nên ghi rõ -n để người khác đọc được phạm vi.

## 3. Đọc manifest theo thứ tự

### 3.1. Xác định kind và apiVersion

apiVersion quyết định schema và nhóm API. kind quyết định controller hoặc API resource xử lý object. Cùng một tên field không có nghĩa mọi kind đều có hành vi giống nhau.

Ví dụ:

    apiVersion: apps/v1
    kind: Deployment

Deployment thuộc nhóm apps và được controller dùng để duy trì ReplicaSet. Một Service có API version và spec khác:

    apiVersion: v1
    kind: Service

Khi đọc một file nhiều document, dấu phân cách bằng ba dấu gạch ngang cho biết có nhiều object. Cần đọc từng object và quan hệ giữa chúng, không chỉ nhìn document đầu tiên.

### 3.2. Đọc metadata

Các trường quan trọng:

- name: tên object trong namespace;
- namespace: phạm vi tên của object;
- labels: cặp key-value để phân loại và chọn tài nguyên;
- annotations: metadata cho công cụ hoặc controller, không phải selector thông thường;
- ownerReferences: quan hệ sở hữu do controller thiết lập.

Label có thể được dùng bởi Service selector, Deployment selector hoặc công cụ quan sát. Một lỗi chính tả trong label có thể làm Service không có backend dù Pod vẫn Running.

### 3.3. Đọc spec và tìm điểm nối

Khi đọc spec, hãy tìm:

1. selector;
2. Pod template;
3. container image;
4. ports;
5. env, envFrom và volumeMounts;
6. resources;
7. startup, readiness và liveness probe;
8. serviceAccountName;
9. strategy;
10. policy hoặc affinity ảnh hưởng scheduling.

Một manifest có thể hợp lệ về YAML nhưng sai quan hệ. Ví dụ selector của Deployment không khớp label trong Pod template sẽ bị API validation từ chối hoặc tạo hành vi không như mong muốn tùy loại resource. Service selector không khớp Pod label thường khiến endpoint rỗng.

## 4. Deployment, ReplicaSet và Pod

### 4.1. Quan hệ controller

Luồng thường gặp:

    Deployment
        ↓ sở hữu
    ReplicaSet
        ↓ sở hữu
    Pod
        ↓ chạy
    container Spring Boot

Deployment mô tả rollout và số replica mong muốn. ReplicaSet duy trì số Pod tương ứng. Pod là object được scheduler gán node và kubelet tạo container.

Các lệnh quan sát:

    kubectl get deployment order-service -n team-a
    kubectl get replicaset -n team-a
    kubectl get pods -l app=order-service -n team-a
    kubectl get pods -o wide -l app=order-service -n team-a

Tùy chọn -o wide bổ sung node, IP và một số thông tin placement. Pod IP chỉ có giá trị trong vòng đời Pod; không dùng nó làm địa chỉ cấu hình bền vững cho client.

### 4.2. Đọc cột READY, STATUS và RESTARTS

Kết quả kubectl get pods thường có các cột dễ gây hiểu nhầm:

| Cột | Ý nghĩa khái quát | Giới hạn |
| --- | --- | --- |
| READY | Số container đã Ready trên tổng số container | Không mô tả nguyên nhân nếu chưa Ready |
| STATUS | Trạng thái hiển thị rút gọn | Cần xem container state và events để biết nguyên nhân |
| RESTARTS | Số lần container được restart | Không tự cho biết restart do OOM, probe hay process exit |
| AGE | Tuổi object | Không phải thời gian ứng dụng đã Ready |

Pod 1/1 Running có thể đang phục vụ, nhưng vẫn cần kiểm tra Ready condition, Service endpoint và log. Pod 0/1 Running thường là container chạy nhưng chưa đạt readiness hoặc có lỗi ở lớp health.

### 4.3. Đọc rollout

Các trường status của Deployment giúp so sánh:

- desired replicas;
- updated replicas;
- available replicas;
- ready replicas;
- điều kiện Progressing và Available.

Lệnh:

    kubectl rollout status deployment/order-service -n team-a
    kubectl rollout history deployment/order-service -n team-a

Rollout đang tiến triển không có nghĩa tất cả traffic đã đi vào phiên bản mới. Cần kiểm tra Pod Ready và backend của Service.

## 5. Service và endpoint

### 5.1. Đọc Service manifest

Service thường có:

    apiVersion: v1
    kind: Service
    metadata:
      name: inventory
      namespace: team-a
    spec:
      selector:
        app: inventory
      ports:
        - name: http
          port: 80
          targetPort: http

Ý nghĩa:

- port là cổng Service công bố;
- targetPort là cổng được chuyển đến Pod;
- selector xác định Pod backend;
- name của port giúp tham chiếu nhất quán trong một số cấu hình.

Nếu container lắng nghe 8080 nhưng targetPort trỏ 8081, DNS vẫn có thể phân giải và Service vẫn tồn tại, nhưng request có thể bị từ chối hoặc timeout.

### 5.2. Kiểm tra endpoint

Các lệnh quan sát:

    kubectl get service inventory -n team-a
    kubectl describe service inventory -n team-a
    kubectl get endpoints inventory -n team-a
    kubectl get endpointslice -l kubernetes.io/service-name=inventory -n team-a

Endpoint rỗng có thể do:

- selector không khớp label;
- Pod chưa Ready;
- Pod ở namespace khác;
- Service port hoặc targetPort sai;
- EndpointSlice chưa cập nhật;
- workload chưa tạo Pod thành công.

Vì vậy, khi service không nhận request, hãy kiểm tra selector và endpoint trước khi kết luận DNS lỗi.

### 5.3. Kiểm tra DNS và đường gọi

Một client trong cùng namespace thường có thể gọi tên Service ngắn:

    http://inventory

Khi gọi khác namespace, cần dùng tên có namespace hoặc tên DNS đầy đủ theo cấu hình cluster. Tên DNS không thay thế việc kiểm tra endpoint. DNS có thể trả địa chỉ Service trong khi Service không có backend Ready.

## 6. ConfigMap và Secret trong manifest

### 6.1. ConfigMap

ConfigMap chứa dữ liệu cấu hình không nhạy cảm. Nó có thể được đưa vào container qua environment hoặc volume:

    apiVersion: v1
    kind: ConfigMap
    metadata:
      name: order-service-config
      namespace: team-a
    data:
      application.yaml: |
        orders:
          max-items: 20

Khi đọc manifest, cần kiểm tra:

- tên và namespace của ConfigMap;
- key được tham chiếu có tồn tại không;
- ứng dụng đọc key như property hay file;
- Deployment có mount đúng path hoặc env đúng tên không;
- thay đổi ConfigMap có cần rollout hoặc refresh không.

ConfigMap tồn tại không chứng minh ứng dụng đang dùng nó. Phải nối từ resource đến Pod spec rồi đến property của Spring.

### 6.2. Secret

Secret dùng cho dữ liệu cần kiểm soát truy cập, chẳng hạn token hoặc mật khẩu. Không in toàn bộ nội dung Secret trong terminal, log hoặc tài liệu chẩn đoán.

Quan sát an toàn nên tập trung vào:

- Secret có tồn tại trong namespace không;
- key dự kiến có được khai báo không;
- Pod spec tham chiếu đúng tên Secret không;
- ServiceAccount có quyền cần thiết không;
- ứng dụng báo property đã được nạp mà không lộ giá trị không.

Các lệnh xem metadata:

    kubectl get secret order-service-secret -n team-a
    kubectl describe secret order-service-secret -n team-a

Kết quả describe cần được xử lý cẩn thận vì một số thông tin metadata vẫn có thể giúp suy ra cấu trúc credential. Không dùng tùy chọn xuất nội dung để đưa vào chat hoặc log chia sẻ.

### 6.3. Khi cấu hình thay đổi

Đọc manifest cần đi cùng việc đọc cơ chế cập nhật:

| Cách đưa vào Pod | Quan sát cần làm |
| --- | --- |
| Environment variable | Pod mới hoặc rollout đã nhận giá trị chưa |
| Volume file | File trong container có đổi chưa, ứng dụng có đọc lại không |
| Spring Cloud Kubernetes config client | Quyền API, source, refresh và bean có áp dụng không |
| Configuration Watcher | Tài nguyên nào được theo dõi, thông báo đến replica nào |

Không kết luận “ConfigMap đã sửa nên ứng dụng đã đổi”. Hãy kiểm tra cả source, thời điểm nạp và giá trị hiệu lực theo một dấu hiệu an toàn.

## 7. ServiceAccount và RBAC

### 7.1. Đọc danh tính của Pod

Trong Pod template:

    spec:
      serviceAccountName: order-service

Nếu trường này không có, Pod có thể dùng ServiceAccount mặc định của namespace theo chính sách cluster. Đó có thể là nguyên nhân ứng dụng không đọc được Service, ConfigMap, Secret hoặc Endpoint.

Quan sát:

    kubectl get pod order-service-abcde -n team-a -o yaml
    kubectl get serviceaccount order-service -n team-a
    kubectl describe serviceaccount order-service -n team-a

Khi xem YAML Pod, tập trung vào serviceAccountName, không chia sẻ token hoặc dữ liệu nhạy cảm nếu object có liên quan.

### 7.2. Đọc Role và RoleBinding

Một Role mô tả resource và verb trong namespace. RoleBinding gán Role cho subject:

    apiVersion: rbac.authorization.k8s.io/v1
    kind: Role
    metadata:
      name: order-config-reader
      namespace: team-a
    rules:
      - apiGroups: [""]
        resources: ["configmaps"]
        verbs: ["get"]

Khi đọc, đối chiếu bốn điểm:

1. apiGroups;
2. resources;
3. verbs;
4. namespace và subject.

Discovery hoặc watcher có thể cần get, list hoặc watch trên những resource khác. Không suy rộng rằng quyền get ConfigMap đủ cho mọi tính năng Spring Cloud Kubernetes.

### 7.3. Kiểm tra quyền bằng auth can-i

Nếu được phép dùng lệnh kiểm tra quyền:

    kubectl auth can-i get configmaps \
      --as=system:serviceaccount:team-a:order-service \
      -n team-a

Có thể kiểm tra từng resource và verb cần thiết. Kết quả “yes” chứng minh danh tính có quyền theo câu hỏi đó, không chứng minh toàn bộ integration đã hoạt động.

Không dùng cluster-admin để bỏ qua lỗi Forbidden. Hãy ghi lại resource, verb, namespace và ServiceAccount gây lỗi rồi điều chỉnh rule tối thiểu.

## 8. kubectl get: xem danh sách và trạng thái

### 8.1. get cơ bản

Các lệnh cơ bản:

    kubectl get pods -n team-a
    kubectl get deployments -n team-a
    kubectl get services -n team-a
    kubectl get configmaps -n team-a

Thêm -o wide khi cần node hoặc IP:

    kubectl get pods -o wide -n team-a

Dùng label selector để giới hạn phạm vi:

    kubectl get pods -l app=order-service -n team-a

Dùng -o yaml hoặc -o json để xem object đầy đủ:

    kubectl get deployment order-service -o yaml -n team-a

Kết quả YAML chứa cả spec và status. Khi so sánh với file manifest, hãy tách phần được khai báo khỏi phần do server hoặc controller bổ sung.

### 8.2. custom-columns và jsonpath

Khi cần xem nhanh một số trường:

    kubectl get pods -n team-a \
      -o custom-columns=NAME:.metadata.name,READY:.status.containerStatuses[*].ready,NODE:.spec.nodeName

Ví dụ lấy tên Pod:

    kubectl get pods -n team-a -o jsonpath='{.items[*].metadata.name}'

Các biểu thức jsonpath có thể khó đọc khi lồng mảng hoặc có field trống. Dùng chúng cho báo cáo lặp lại sau khi đã kiểm tra kết quả bằng output dễ đọc. Không dùng một câu lệnh jsonpath phức tạp làm bằng chứng duy nhất nếu người khác không thể hiểu nó đang lấy field nào.

### 8.3. watch

Có thể theo dõi thay đổi:

    kubectl get pods -w -n team-a

Lệnh này giúp quan sát Pod chuyển từ Pending sang Running và Ready. Khi cần tìm nguyên nhân, dừng watch rồi dùng describe và logs để đọc chi tiết. Một dòng status thay đổi không cho biết event hoặc log bên trong.

## 9. kubectl describe: đọc điều kiện và sự kiện

describe là góc nhìn tổng hợp cho người vận hành:

    kubectl describe pod order-service-abcde -n team-a
    kubectl describe deployment order-service -n team-a
    kubectl describe service inventory -n team-a

Với Pod, chú ý:

- Node;
- Labels;
- Service Account;
- Containers;
- Image;
- Ports;
- Environment;
- Mounts;
- Requests và limits;
- Liveness, readiness, startup;
- Conditions;
- State và Last State;
- Exit Code;
- Events.

Events thường cho biết các bước như FailedScheduling, Pulling, Pulled, Created, Started, Unhealthy, BackOff hoặc lỗi mount. Events có thời gian tồn tại giới hạn và có thể bị thay thế, nên khi sự cố xảy ra cần thu thập sớm.

describe có thể hiển thị nhiều thông tin hơn log ứng dụng, nhưng không thay thế log. Nó nói hệ thống đã quan sát Pod thế nào; log nói process đã ghi gì.

## 10. kubectl logs: đọc process bên trong container

### 10.1. Log cơ bản

    kubectl logs pod/order-service-abcde -n team-a

Với Deployment:

    kubectl logs deployment/order-service -n team-a

Nếu Pod có nhiều container, cần chỉ rõ container:

    kubectl logs pod/order-service-abcde -c app -n team-a

Theo dõi log mới:

    kubectl logs pod/order-service-abcde -c app -f -n team-a

Giới hạn log theo thời gian hoặc số dòng để giảm output:

    kubectl logs pod/order-service-abcde -c app --since=10m -n team-a
    kubectl logs pod/order-service-abcde -c app --tail=200 -n team-a

### 10.2. Log của lần chạy trước

Nếu container đã restart:

    kubectl logs pod/order-service-abcde -c app --previous -n team-a

Log hiện tại có thể chỉ nói process mới đang khởi động. Log previous thường chứa stack trace hoặc lỗi khiến lần chạy trước kết thúc.

### 10.3. Đọc log an toàn

Log có thể chứa request data, header hoặc property nhạy cảm. Khi chia sẻ bằng chứng:

- lọc token, mật khẩu và Secret;
- giới hạn khoảng thời gian;
- giữ timestamp, error type và correlation ID;
- ghi tên Pod, container và namespace;
- không gửi toàn bộ log nếu vài dòng đủ chứng minh lỗi.

Với ứng dụng Spring, tìm các nhóm tín hiệu:

- lỗi bind property;
- lỗi không kết nối được ConfigMap hoặc Secret;
- lỗi 401 hoặc 403 đến API Server;
- lỗi discovery không có instance;
- lỗi timeout đến downstream;
- lỗi startup hoặc health indicator;
- OutOfMemoryError hoặc shutdown bất thường.

## 11. kubectl get events: đọc lịch sử ngắn hạn

Lệnh:

    kubectl get events -n team-a --sort-by=.lastTimestamp

Có thể lọc theo field selector nếu cần, nhưng cú pháp và field hỗ trợ phụ thuộc resource API. Khi output nhiều, ưu tiên event gắn với Pod, ReplicaSet, Deployment hoặc node liên quan.

Events trả lời những câu hỏi như:

- scheduler không đặt Pod vì lý do gì;
- image pull thất bại ở đâu;
- volume mount lỗi gì;
- probe fail vào thời điểm nào;
- controller tạo hoặc xóa Pod ra sao.

Events không phải hệ thống audit lâu dài. Với sự cố quan trọng, lưu lại timestamp, resource name, namespace và trích đoạn event theo quy trình của tổ chức.

## 12. Kiểm tra probe và conditions

### 12.1. Conditions

Pod có thể có các condition như PodScheduled, Initialized, ContainersReady và Ready. Mỗi condition có status, reason, message và thời điểm.

Điều cần quan sát:

- Pod đã được scheduler gán chưa;
- init container đã hoàn tất chưa;
- mọi container cần thiết đã Ready chưa;
- Ready fail vì probe hay điều kiện khác;
- thời điểm chuyển trạng thái có trùng với rollout hoặc thay đổi config không.

### 12.2. Probe thất bại

Khi thấy Unhealthy trong events:

1. Xác định probe nào thất bại.
2. Kiểm tra path, port, scheme và HTTP headers nếu có.
3. Kiểm tra ứng dụng thực sự lắng nghe trên cổng đó.
4. Đọc log cùng khoảng thời gian.
5. Xem startup, readiness và liveness có bắt đầu đúng lúc không.
6. Kiểm tra dependency mà health indicator đang bao gồm.

Một probe HTTP có thể nhận 404 vì context path sai, 401 vì endpoint bị bảo vệ hoặc timeout vì ứng dụng chưa hoàn tất startup. Mỗi nguyên nhân cần xử lý khác nhau.

### 12.3. Không sửa probe bằng cách làm nó vô nghĩa

Probe quá rộng hoặc trả luôn thành công làm mất giá trị của controller. Probe quá chặt hoặc phụ thuộc quá nhiều hệ thống bên ngoài làm rollout và traffic không ổn định. Mục tiêu là tín hiệu đủ nhỏ để đo đúng quyết định cần đưa ra.

## 13. So sánh manifest với resource đang chạy

### 13.1. get -o yaml không phải file manifest gốc

Kết quả:

    kubectl get deployment order-service -n team-a -o yaml

thường chứa metadata server-side, status, UID, resourceVersion và các field do controller thêm. Không copy nguyên output này thành manifest triển khai mới mà không hiểu từng trường.

Khi so sánh, tập trung vào:

- image;
- replicas;
- selector;
- labels;
- env và envFrom;
- volume;
- resources;
- probe;
- serviceAccount;
- strategy.

### 13.2. diff trước khi apply

Nếu có quyền và file manifest local hợp lệ, có thể xem thay đổi dự kiến:

    kubectl diff -f deployment.yaml -n team-a

diff giúp phát hiện image, port, selector, probe hoặc nguồn cấu hình đổi ngoài ý muốn. Cần xác định đúng context và namespace trước khi đọc diff.

### 13.3. apply và quan sát sau thay đổi

Sau khi một manifest được áp dụng theo quy trình được ủy quyền:

    kubectl apply -f deployment.yaml -n team-a
    kubectl rollout status deployment/order-service -n team-a
    kubectl get pods -l app=order-service -n team-a

Quan sát sau apply phải kiểm tra cả desired state lẫn observed state. “Apply configured” chỉ cho biết API Server nhận yêu cầu; không có nghĩa Pod mới đã Ready hoặc request đã thành công.

Trong bài này, các lệnh apply chỉ là ví dụ học tập. Khi làm production, phải tuân thủ quy trình review, approval và change management của hệ thống.

## 14. Quy trình chẩn đoán theo tầng

Khi client không gọi được order-service hoặc Spring không đọc được cấu hình, dùng thứ tự từ ngoài vào trong:

### Tầng 1: context và namespace

    kubectl config current-context
    kubectl get namespace team-a

Xác nhận lệnh đang đi đến cluster đúng và object nằm ở namespace đúng.

### Tầng 2: Deployment và replica

    kubectl get deployment order-service -n team-a
    kubectl get replicaset -n team-a
    kubectl get pods -l app=order-service -n team-a

Xác định desired, ready, updated và available replica.

### Tầng 3: Pod và container

    kubectl describe pod order-service-abcde -n team-a
    kubectl logs pod/order-service-abcde -c app -n team-a

Đọc state, probe, event, exit code và log ứng dụng.

### Tầng 4: Service và endpoint

    kubectl get service order-service -n team-a
    kubectl get endpointslice -l kubernetes.io/service-name=order-service -n team-a

Kiểm tra selector, port và backend Ready.

### Tầng 5: Cấu hình và quyền

    kubectl get configmap order-service-config -n team-a
    kubectl get serviceaccount order-service -n team-a
    kubectl auth can-i get configmaps --as=system:serviceaccount:team-a:order-service -n team-a

Không in Secret value; chỉ xác nhận object, key, tham chiếu và quyền cần thiết.

### Tầng 6: request an toàn

Sau khi các tầng trên hợp lý, thực hiện smoke test không gây tác dụng phụ hoặc dùng dữ liệu test. Ghi timestamp, URL logic, response status, Pod version và correlation ID để liên kết với log.

## 15. Ví dụ đọc một bộ manifest

Giả sử có ba object:

    apiVersion: apps/v1
    kind: Deployment
    metadata:
      name: order-service
      namespace: team-a
    spec:
      replicas: 2
      selector:
        matchLabels:
          app: order-service
      template:
        metadata:
          labels:
            app: order-service
        spec:
          serviceAccountName: order-service
          containers:
            - name: app
              image: registry.example/order-service:1.4.0
              ports:
                - name: http
                  containerPort: 8080

    ---

    apiVersion: v1
    kind: Service
    metadata:
      name: order-service
      namespace: team-a
    spec:
      selector:
        app: order-service
      ports:
        - name: http
          port: 80
          targetPort: http

    ---

    apiVersion: v1
    kind: ConfigMap
    metadata:
      name: order-service-config
      namespace: team-a
    data:
      application.yaml: |
        orders:
          max-items: 20

Cách đọc:

1. Deployment mong muốn hai Pod.
2. Pod template có label app=order-service.
3. Service selector khớp label nên có thể chọn các Pod.
4. Service port 80 chuyển đến port có tên http của container.
5. ServiceAccount được chỉ rõ để đối chiếu RBAC.
6. ConfigMap tồn tại nhưng chưa thể kết luận Pod đã mount hoặc Spring đã đọc nó, vì template chưa thể hiện volume hoặc source config.

Kết luận đúng ở đây là “manifest tạo quan hệ tiềm năng giữa các resource”, không phải “ứng dụng chắc chắn đang nhận traffic và dùng ConfigMap”.

## 16. Quan sát Spring Cloud Kubernetes qua kubectl

Các tính năng Spring Cloud Kubernetes có thể tạo ra dấu hiệu ở nhiều resource:

| Tính năng | Resource hoặc tín hiệu cần quan sát |
| --- | --- |
| DiscoveryClient | Pod log, quyền đọc Service/Endpoint, danh sách instance hiệu lực |
| ConfigMap integration | ConfigMap, Pod spec, log nạp property, quyền API |
| Secret integration | Secret metadata, RBAC, log trạng thái nạp an toàn |
| Spring Cloud LoadBalancer | Log chọn instance, timeout và lỗi downstream |
| Configuration Watcher | watcher Pod, events, log thông báo, refresh outcome |
| Health và probe | Pod conditions, events, Actuator endpoint và restart count |

kubectl không thể trực tiếp chứng minh mọi bean trong JVM đang dùng property nào. Nó cung cấp context Kubernetes và log. Để xác nhận giá trị hiệu lực, ứng dụng cần có metric, version identifier hoặc endpoint chẩn đoán an toàn được thiết kế trước.

## 17. Các lệnh quan sát nên có trong runbook

Một runbook tối thiểu cho workload Spring có thể ghi:

    kubectl config current-context
    kubectl get deployment order-service -n team-a
    kubectl rollout status deployment/order-service -n team-a
    kubectl get pods -l app=order-service -o wide -n team-a
    kubectl describe pod <pod-name> -n team-a
    kubectl logs pod/<pod-name> -c app --since=10m -n team-a
    kubectl get service order-service -n team-a
    kubectl get endpointslice -l kubernetes.io/service-name=order-service -n team-a
    kubectl get events -n team-a --sort-by=.lastTimestamp

Trong tài liệu thực tế, thay placeholder bằng tên đã được xác định và ghi rõ lệnh nào chỉ đọc, lệnh nào có thể thay đổi resource. Không đặt lệnh xóa hoặc restart vào phần kiểm tra cơ bản nếu chưa có bước phê duyệt.

## 18. Các thao tác cần thận trọng

### Xóa Pod

Xóa Pod có thể kích hoạt controller tạo bản sao mới. Dù hữu ích trong một số kiểm tra, đây vẫn là thay đổi trạng thái. Không dùng xóa như bước chẩn đoán mặc định.

### Rollout restart

Rollout restart tạo Pod mới và có thể làm tăng tải, mất cache hoặc tạo gián đoạn nếu workload không đủ replica. Chỉ dùng khi đã hiểu nguyên nhân và có quyền.

### Exec vào container

kubectl exec có thể giúp kiểm tra filesystem, DNS hoặc process bên trong container:

    kubectl exec -it pod/order-service-abcde -c app -n team-a -- sh

Exec là một hành động tương tác, có thể lộ dữ liệu và làm thay đổi trạng thái nếu chạy nhầm lệnh. Ưu tiên các lệnh read-only, không nhập Secret vào shell history và ghi lại lý do truy cập.

### Port-forward

Port-forward giúp kiểm tra endpoint trong phạm vi chẩn đoán:

    kubectl port-forward pod/order-service-abcde 18080:8080 -n team-a

Port-forward không mô phỏng toàn bộ đường đi qua Service, NetworkPolicy hoặc load balancer. Dùng nó để kiểm tra process và endpoint, không kết luận rằng client trong cluster cũng có cùng kết quả.

## 19. Những hiểu nhầm thường gặp

**“kubectl apply thành công nghĩa là ứng dụng đã chạy.”** Apply chỉ cho biết API Server nhận object. Cần xem rollout, Pod, readiness, endpoint và request.

**“Pod không xuất hiện vì nó không tồn tại.”** Có thể đang xem nhầm context hoặc namespace. Xác nhận phạm vi trước.

**“Pod Running là Service sẽ tự có endpoint.”** Service cần selector khớp và Pod thường phải Ready để được dùng làm backend.

**“get yaml là manifest sạch để apply lại.”** Output có status, UID, resourceVersion và metadata server-side. Cần lọc và hiểu từng field trước khi tái sử dụng.

**“describe không có lỗi nghĩa là ứng dụng không lỗi.”** describe phản ánh resource và event; lỗi nghiệp vụ hoặc lỗi trong JVM có thể chỉ xuất hiện ở log và metric.

**“Có ConfigMap là Spring đã đọc cấu hình.”** Cần kiểm tra đường nối từ ConfigMap đến Pod và source configuration của ứng dụng.

**“Xem Secret để debug nghĩa là phải decode nội dung.”** Thường chỉ cần kiểm tra tồn tại, key, reference và quyền. Không đưa giá trị nhạy cảm vào bằng chứng.

**“Port-forward chứng minh Service hoạt động.”** Port-forward có thể bỏ qua Service selector và đường mạng thực tế. Nó chỉ kiểm tra trực tiếp một Pod.

## 20. Tự kiểm tra mức độ hiểu

**Câu 1: Vì sao phải kiểm tra context trước khi chạy kubectl get pods?**

Vì context quyết định cluster và credential mà kubectl dùng. Chạy đúng cú pháp trên cluster hoặc namespace sai có thể trả về kết quả hợp lệ nhưng không liên quan workload đang điều tra.

**Câu 2: Deployment có replicas bằng hai nhưng chỉ có một Pod Ready. Cần xem gì?**

Xem Deployment status, ReplicaSet, Pod còn lại, describe, events, log, resource scheduling và readiness. Spec chỉ là số lượng mong muốn; status mới cho biết số bản sao hiện có.

**Câu 3: Service tồn tại nhưng endpoint rỗng. Nguyên nhân thường gặp là gì?**

Selector không khớp label, Pod chưa Ready, namespace sai hoặc workload chưa tạo Pod thành công. Cần đọc cả Service và Pod thay vì chỉ kiểm tra DNS.

**Câu 4: Khi nào dùng kubectl logs --previous?**

Khi container đã restart và cần đọc log của lần chạy trước, thường để tìm stack trace, exit reason hoặc lỗi khởi động đã khiến process kết thúc.

**Câu 5: kubectl describe và kubectl logs bổ sung cho nhau thế nào?**

describe cho biết resource, conditions, event, probe và trạng thái container theo quan sát của Kubernetes. logs cho biết process ứng dụng ghi gì. Cả hai cần được đối chiếu theo timestamp.

**Câu 6: Làm sao kiểm tra ứng dụng có quyền đọc ConfigMap mà không lộ Secret?**

Dùng đúng ServiceAccount để chạy câu hỏi auth can-i với resource và verb cần thiết, kiểm tra reference và metadata của ConfigMap. Không cần in Secret value.

## Kết luận

Đọc manifest là đọc trạng thái mong muốn và các quan hệ giữa resource. Quan sát bằng kubectl là đọc trạng thái đã xảy ra qua status, conditions, events, log và endpoint. Hai góc nhìn phải được ghép lại mới cho biết ứng dụng Spring đã thật sự khởi động, Ready, nhận traffic và dùng đúng cấu hình hay chưa.

Quy trình an toàn bắt đầu bằng context và namespace, tiếp tục qua Deployment, ReplicaSet, Pod, Service, endpoint, cấu hình và RBAC, rồi kết thúc bằng log và smoke test có kiểm soát. Khi đã có thói quen kiểm tra theo tầng, các lỗi discovery, ConfigMap, Secret, LoadBalancer, watcher và probe sẽ được khoanh vùng bằng bằng chứng cụ thể thay vì suy đoán từ một dòng trạng thái.
