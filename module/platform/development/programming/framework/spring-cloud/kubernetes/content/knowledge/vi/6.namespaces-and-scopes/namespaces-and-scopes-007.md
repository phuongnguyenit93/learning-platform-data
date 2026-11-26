# Phân biệt phạm vi theo namespace và phạm vi toàn cluster

## Mục tiêu bài học

Kubernetes có resource thuộc một namespace và resource thuộc toàn cluster. Phân biệt hai phạm vi này là điều kiện để viết đúng API request, manifest, RBAC rule, discovery scope và runbook. Nếu nhầm phạm vi, client có thể gửi namespace vào resource cluster-scoped, cấp ClusterRoleBinding quá rộng hoặc tưởng rằng một Service ở namespace này có thể được đọc như Service ở namespace khác.

Bài thuộc chương **Namespace và phạm vi** của module **SPRING_CLOUD_KUBERNETES**. Module học tích hợp ứng dụng Spring với Kubernetes qua DiscoveryClient, ConfigMap, Secret, Spring Cloud LoadBalancer và Configuration Watcher; đồng thời thực hành phân quyền RBAC, cập nhật cấu hình, theo dõi sức khỏe Pod và lựa chọn tính năng Spring Cloud Kubernetes thực sự cần cho triển khai.

Sau bài này, bạn có thể:

- Phân biệt namespaced resource và cluster-scoped resource.
- Xác định scope từ kind, API discovery hoặc CRD schema.
- Đọc đúng API path và cách dùng kubectl cho mỗi phạm vi.
- Thiết kế Role, RoleBinding, ClusterRole và ClusterRoleBinding theo quyền tối thiểu.
- Hiểu tác động của scope đến Spring Cloud Kubernetes, discovery, ConfigMap và Secret.
- Chẩn đoán lỗi NotFound, Forbidden và request sai namespace.

## 1. Scope là một phần của hợp đồng API

Một resource Kubernetes có thể được định danh theo:

    group + version + resource + namespace + name

Với resource namespaced, namespace là một phần identity. Với resource cluster-scoped, namespace không tồn tại trong identity.

Ví dụ:

    team-a/order-service
    team-b/order-service

Hai object trên có thể cùng tên nhưng khác namespace. Ngược lại, một Node tên worker-01 là object ở cấp cluster; không có team-a/worker-01.

| Phạm vi | Identity | Ví dụ |
| --- | --- | --- |
| Namespaced | namespace + name | Pod, Service, ConfigMap, Secret, Deployment |
| Cluster-scoped | name trên toàn cluster | Node, Namespace, PersistentVolume, CRD |

Scope không chỉ ảnh hưởng nơi lưu object. Nó ảnh hưởng API URL, RBAC, kubectl, discovery, cleanup, quota và blast radius của thao tác.

## 2. Resource namespaced

Các resource thường namespaced:

- Deployment;
- Pod;
- Service;
- ConfigMap;
- Secret;
- ServiceAccount;
- Role;
- RoleBinding;
- Endpoint hoặc EndpointSlice;
- Job;
- HorizontalPodAutoscaler.

Ví dụ manifest:

    apiVersion: v1
    kind: Service
    metadata:
      name: inventory
      namespace: team-a

Service inventory ở team-a khác Service inventory ở team-b. Client cần truyền đúng namespace hoặc dùng DNS có namespace.

API path khái quát của resource namespaced:

    /apis/<group>/<version>/namespaces/<namespace>/<resource>

Resource lõi thường có dạng:

    /api/v1/namespaces/<namespace>/pods

Người dùng không nên tự nối URL nếu thư viện đã cung cấp typed API, nhưng cần hiểu namespace nằm trong path.

## 3. Resource cluster-scoped

Một số resource không thuộc namespace:

- Namespace;
- Node;
- PersistentVolume;
- ClusterRole;
- ClusterRoleBinding;
- CustomResourceDefinition;
- StorageClass;
- PriorityClass;
- APIService.

Một resource cluster-scoped có tên duy nhất trong cluster:

    worker-01
    team-a
    order-service.example.io

API path khái quát:

    /apis/<group>/<version>/<resource>

Không có đoạn namespaces/<namespace>. Thêm namespace vào resource cluster-scoped không biến nó thành namespaced.

Thao tác cluster-scoped thường có blast radius lớn. Sửa StorageClass có thể ảnh hưởng nhiều workload, xóa CRD có thể ảnh hưởng tất cả custom object, còn sửa ClusterRoleBinding có thể thay đổi quyền toàn cluster.

## 4. Xác định scope từ API discovery và CRD

API discovery cung cấp group, version, resource name, kind, namespaced true hoặc false và verbs hỗ trợ. Khi code hỗ trợ resource động, nên kiểm tra discovery hoặc catalog được quản lý thay vì hard-code mọi scope.

Với CRD, đọc schema:

    spec:
      scope: Namespaced

hoặc:

    spec:
      scope: Cluster

Cần phân biệt hai lớp:

1. CRD definition là resource cluster-scoped.
2. Instance của custom resource có thể namespaced hoặc cluster-scoped theo spec.scope.

Không suy ra scope chỉ từ tên kind hoặc tên file manifest.

## 5. kubectl và scope

Ví dụ lệnh namespaced:

    kubectl get pods -n team-a
    kubectl get service inventory -n team-a
    kubectl get configmap order-service-config -n team-a
    kubectl get deployment order-service -n team-a

Ví dụ lệnh cluster-scoped:

    kubectl get nodes
    kubectl get namespaces
    kubectl get persistentvolumes
    kubectl get storageclasses
    kubectl get customresourcedefinitions

Tùy chọn -n chỉ xác định phạm vi request của kubectl. Nó không biến resource cluster-scoped thành namespaced và không thay đổi scope của object.

Trước khi kết luận NotFound:

1. Xác định kind và API group.
2. Xác định namespaced hay cluster-scoped.
3. Kiểm tra context và quyền.
4. Gọi đúng lệnh có hoặc không có namespace.

## 6. RBAC theo scope

Role là namespaced object, mô tả quyền trong một namespace:

    apiVersion: rbac.authorization.k8s.io/v1
    kind: Role
    metadata:
      name: order-config-reader
      namespace: team-a
    rules:
      - apiGroups: [""]
        resources: ["configmaps"]
        verbs: ["get"]

Role trên không cấp quyền đọc ConfigMap team-b và không cấp quyền resource cluster-scoped.

ClusterRole là cluster-scoped object. Nó có thể mô tả quyền cho resource cluster-scoped hoặc được bind vào một namespace bằng RoleBinding:

    apiVersion: rbac.authorization.k8s.io/v1
    kind: ClusterRole
    metadata:
      name: inventory-reader
    rules:
      - apiGroups: [""]
        resources: ["services"]
        verbs: ["get", "list"]

ClusterRole không tự cấp quyền cho ai. Quyền có hiệu lực thông qua RoleBinding hoặc ClusterRoleBinding.

RoleBinding là namespaced và có thể tham chiếu ClusterRole để giới hạn quyền vào namespace của binding:

    kind: RoleBinding
    metadata:
      name: inventory-reader-binding
      namespace: team-a
    roleRef:
      kind: ClusterRole
      name: inventory-reader

ClusterRoleBinding gán ClusterRole ở phạm vi cluster. Chỉ dùng khi có yêu cầu rõ và được review.

| Object | Scope của object | Quyền có thể áp dụng |
| --- | --- | --- |
| Role | Namespace | Resource trong namespace đó |
| ClusterRole | Cluster | Resource cluster-scoped hoặc được bind hẹp |
| RoleBinding | Namespace | Gán Role hoặc ClusterRole trong namespace binding |
| ClusterRoleBinding | Cluster | Gán ClusterRole trên toàn cluster |

## 7. Spring Cloud Kubernetes và scope

Discovery có thể đọc Service, Endpoint hoặc EndpointSlice trong namespace hiện tại, một namespace cố định, nhiều namespace hoặc toàn cluster. Phạm vi càng rộng, yêu cầu RBAC và cache càng lớn.

Nếu hai namespace cùng có Service inventory, discovery multi-namespace cần metadata namespace để không trộn instance. Chỉ service ID inventory là chưa đủ nếu name không unique trên toàn cluster.

ConfigMap và Secret là namespaced. Spring Cloud Kubernetes config integration cần biết resource nằm ở đâu. Tên order-service-config trong team-a khác tên cùng loại ở team-b.

Configuration Watcher cũng cần watch đúng namespace và resource. Watch ConfigMap team-a không tự nhận event ConfigMap team-b.

LoadBalancer nhận service ID từ discovery hoặc dùng DNS Service. Scope nằm ở nguồn instance hoặc DNS, không tự phát sinh từ LoadBalancer. Khi đổi discovery scope, kiểm tra cache, namespace metadata và NetworkPolicy.

## 8. Cross-namespace request

Cross-namespace không chỉ là thêm namespace vào tên. Cần kiểm tra:

- resource đích có namespaced không;
- client dùng API method đúng không;
- ServiceAccount có quyền tại namespace đích không;
- NetworkPolicy cho phép đường nghiệp vụ;
- DNS hoặc API endpoint đúng;
- dữ liệu có được phép vượt boundary không;
- retry và cache có phân biệt namespace không.

Ví dụ, ứng dụng team-a đọc ConfigMap team-b qua API cần RoleBinding ở team-b cho identity của team-a. Role ở team-a không đủ.

Nếu chỉ gọi Service team-b bằng DNS, RBAC đọc API có thể không cần, nhưng NetworkPolicy và authentication của service đích vẫn cần.

## 9. Custom Resource Definition

CRD là cluster-scoped vì nó định nghĩa loại resource trong toàn cluster:

    kind: CustomResourceDefinition
    metadata:
      name: widgets.example.io

Custom object do CRD tạo có thể Namespaced hoặc Cluster tùy schema. Client cần dùng đúng API path và RBAC cho cả discovery CRD lẫn instance.

Không cấp quyền sửa CRD cho ứng dụng chỉ cần đọc custom object. Xóa CRD có thể ảnh hưởng tất cả instance và controller liên quan.

## 10. Namespace và cleanup

Namespace deletion có thể kích hoạt cleanup resource namespaced. Đây là khác biệt lớn so với xóa một Pod hoặc ConfigMap.

OwnerReference cũng có scope rule. Object owner và dependent phải tuân theo quan hệ scope được Kubernetes cho phép. Khi client tạo resource phụ, cần xác định owner, dùng UID thật, hiểu propagation policy và đánh giá blast radius.

Thao tác cluster-scoped cần quy trình review nghiêm hơn thay đổi hẹp trong namespace.

## 11. Chẩn đoán lỗi theo scope

### NotFound

Kiểm tra kind, API version, plural resource name, namespace, resource scope và việc object đã bị xóa hay chưa. NotFound do gọi sai scope khác với NotFound vì object thật sự không tồn tại.

### Forbidden

Kiểm tra identity đầy đủ, Role hoặc ClusterRole, RoleBinding hay ClusterRoleBinding, binding namespace, resource scope, verb và apiGroup.

### Discovery rỗng

Kiểm tra namespace discovery, Service selector, endpoint Ready và quyền list/watch. Discovery rỗng không phải lúc nào là lỗi client; có thể không có backend trong scope đã chọn.

### ConfigMap hoặc Secret không được đọc

Kiểm tra resource namespace, reference của Pod, config integration scope, ServiceAccount và quyền get/list/watch.

## 12. Capability matrix theo phạm vi

| Use case | Scope thường gặp | Quyền cần cân nhắc |
| --- | --- | --- |
| Gọi Service trong namespace hiện tại | Namespaced | Không nhất thiết cần API read nếu dùng DNS |
| Discovery Service nhiều namespace | Namespaced ở nhiều nơi | get/list/watch theo namespace |
| Đọc ConfigMap của ứng dụng | Namespaced | get hoặc list/watch tại namespace đích |
| Đọc Node để phân tích placement | Cluster-scoped | get/list Node |
| Đọc CRD definition | Cluster-scoped | get CRD |
| Đọc custom object namespaced | Theo scope CRD | Quyền tại namespace instance |
| Quản lý Namespace | Cluster-scoped | create/update/delete Namespace |

Chọn capability nhỏ nhất. Ứng dụng nghiệp vụ thường không cần quyền cluster-scoped.

## 13. Những hiểu nhầm thường gặp

**Mọi resource đều có namespace.** Node, Namespace, CRD, PersistentVolume và nhiều resource khác cluster-scoped.

**ClusterRole luôn mở toàn cluster.** ClusterRole là object cluster-scoped, nhưng có thể được RoleBinding bind trong một namespace.

**Role ở team-a đọc được team-b nếu ServiceAccount cùng tên.** ServiceAccount là namespaced; cùng tên không cùng identity.

**CRD và custom object có cùng scope.** CRD definition cluster-scoped; instance phụ thuộc spec.scope.

**Thêm -n vào lệnh là resource chuyển sang namespace đó.** -n chỉ xác định phạm vi request của kubectl.

**Discovery toàn cluster chỉ cần bật một property.** Còn cần API scope, cache, RBAC, dữ liệu metadata và đánh giá blast radius.

**Gọi Service cross-namespace cần ClusterRole.** Gọi qua DNS và đọc API là hai việc khác nhau. NetworkPolicy và service authentication có thể đủ cho đường gọi, còn API read mới cần RBAC tương ứng.

## 14. Checklist phân biệt scope

- [ ] Đã xác định group, version, kind và resource plural.
- [ ] Đã biết resource namespaced hay cluster-scoped.
- [ ] API path có hoặc không có namespace đúng theo scope.
- [ ] kubectl command dùng -n đúng chỗ.
- [ ] Role và RoleBinding dùng cho quyền hẹp.
- [ ] ClusterRoleBinding chỉ dùng khi có lý do rõ.
- [ ] CRD definition và custom instance được đánh giá riêng.
- [ ] Discovery scope được ghi rõ.
- [ ] ConfigMap và Secret được đọc đúng namespace.
- [ ] Cross-namespace request có RBAC và NetworkPolicy phù hợp.
- [ ] Runbook ghi rõ blast radius của thao tác cluster-scoped.

## 15. Tự kiểm tra mức độ hiểu

**Câu 1: Điểm khác nhau cốt lõi giữa namespaced và cluster-scoped là gì?**

Resource namespaced có identity gồm namespace và name. Resource cluster-scoped có name duy nhất trên toàn cluster và không nhận namespace trong API path.

**Câu 2: Role và ClusterRole khác nhau thế nào?**

Role là resource trong namespace và mô tả quyền theo phạm vi namespace. ClusterRole là resource cluster-scoped và có thể mô tả quyền cluster hoặc được bind hẹp bằng RoleBinding.

**Câu 3: RoleBinding có thể tham chiếu ClusterRole không?**

Có. Khi RoleBinding nằm trong một namespace, ClusterRole được áp dụng theo phạm vi binding đó, không tự biến thành ClusterRoleBinding toàn cluster.

**Câu 4: Vì sao ứng dụng discovery nhiều namespace cần cẩn thận hơn?**

Nó cần quyền và cache rộng hơn, đồng thời cùng service name có thể xuất hiện ở nhiều namespace. Nếu thiếu metadata namespace, client có thể chọn nhầm instance.

**Câu 5: CRD có phải luôn namespaced không?**

Không. CRD definition là cluster-scoped, còn instance có thể Namespaced hoặc Cluster theo schema CRD.

**Câu 6: 403 khi đọc resource team-b dù Pod ở team-a cần kiểm tra gì?**

Kiểm tra identity ServiceAccount team-a, Role hoặc ClusterRole, binding tại team-b, resource scope và verb get/list/watch. Role chỉ ở team-a thường không đủ.

## Kết luận

Namespaced và cluster-scoped là hai hợp đồng khác nhau về identity, API path, RBAC và blast radius. Pod, Service, ConfigMap, Secret và Deployment thường thuộc namespace; Node, Namespace, CRD definition và PersistentVolume thường thuộc toàn cluster. Custom resource cần đọc schema để xác định instance scope.

Trong Spring Cloud Kubernetes, scope ảnh hưởng trực tiếp đến discovery, ConfigMap, Secret, watcher và load balancing. Hãy xác định scope trước khi viết client hoặc cấp quyền, dùng RoleBinding khi có thể, giữ discovery trong namespace cần thiết và chỉ mở rộng cluster-wide khi có yêu cầu được chứng minh.
