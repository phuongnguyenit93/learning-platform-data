# Namespace mặc định và cách xác định namespace của ứng dụng

## Mục tiêu bài học

Namespace là một phần quan trọng của identity trong Kubernetes. Cùng một tên Service, ConfigMap hoặc Secret có thể tồn tại ở nhiều namespace và đại diện cho những resource khác nhau. Một lệnh kubectl, một Pod và một Kubernetes client có thể có namespace mặc định khác nhau; nếu không xác định rõ phạm vi, ứng dụng dễ đọc nhầm cấu hình, gọi nhầm Service hoặc nhận lỗi NotFound và Forbidden khó giải thích.

Bài thuộc chương **Namespace và phạm vi** của module **SPRING_CLOUD_KUBERNETES**. Module học tích hợp ứng dụng Spring với Kubernetes qua DiscoveryClient, ConfigMap, Secret, Spring Cloud LoadBalancer và Configuration Watcher; đồng thời thực hành phân quyền RBAC, cập nhật cấu hình, theo dõi sức khỏe Pod và lựa chọn tính năng Spring Cloud Kubernetes thực sự cần cho triển khai.

Sau bài này, bạn có thể:

- Phân biệt namespace mặc định của kubectl, Pod và Kubernetes client.
- Xác định namespace của ứng dụng đang chạy từ Pod metadata hoặc file được mount.
- Hiểu phạm vi namespaced và cluster-scoped.
- Dùng namespace đúng khi gọi Service, ConfigMap, Secret và Kubernetes API.
- Tránh lỗi do context, namespace, ServiceAccount và RBAC không cùng phạm vi.
- Thiết kế cấu hình namespace rõ ràng cho Spring Cloud Kubernetes.

## 1. Namespace là gì?

Namespace là một phạm vi logic để nhóm và cô lập nhiều resource trong cùng cluster. Một resource namespaced được xác định bởi cặp:

    namespace + name

Ví dụ:

    team-a/order-service
    team-b/order-service

Hai Service trên có cùng name nhưng là hai object khác nhau. DNS, RBAC, quota và NetworkPolicy có thể làm hành vi của chúng khác nhau.

Namespace giúp:

- tách môi trường hoặc team;
- giới hạn quyền bằng Role và RoleBinding;
- áp quota và limit range;
- tổ chức Service, Deployment, ConfigMap và Secret;
- tách log, metric và quy trình vận hành.

Namespace không phải một cluster độc lập. Pod ở hai namespace vẫn có thể giao tiếp nếu DNS, NetworkPolicy và quyền ứng dụng cho phép. Namespace cũng không tự mã hóa hoặc bảo vệ Secret; bảo mật còn phụ thuộc RBAC, storage encryption, audit và quy trình credential.

## 2. Namespaced và cluster-scoped

### 2.1. Resource namespaced

Các resource thường namespaced:

- Pod;
- Deployment;
- ReplicaSet;
- Service;
- ConfigMap;
- Secret;
- ServiceAccount;
- Role;
- RoleBinding;
- Job;
- HPA.

Khi gọi API hoặc kubectl, các resource này thường cần namespace. Nếu không chỉ rõ, công cụ dùng namespace mặc định của context hoặc cấu hình client.

### 2.2. Resource cluster-scoped

Một số resource không thuộc namespace:

- Node;
- Namespace;
- ClusterRole;
- ClusterRoleBinding;
- PersistentVolume;
- CustomResourceDefinition.

Không thể sửa phạm vi của resource cluster-scoped bằng cách thêm namespace vào URL. RBAC cũng phân biệt Role trong namespace với ClusterRole có thể dùng cho phạm vi rộng hơn.

### 2.3. Scope của Custom Resource

CRD có thể khai báo scope Namespaced hoặc Cluster. Client phải đọc schema CRD hoặc tài liệu resource để biết có truyền namespace hay không. Không suy ra scope chỉ từ tên kind.

## 3. Có nhiều loại namespace mặc định

Từ mặc định cần được hiểu theo ngữ cảnh:

| Ngữ cảnh | Namespace được xác định ở đâu | Ảnh hưởng |
| --- | --- | --- |
| kubectl | kubeconfig context | Lệnh get, describe, logs và apply |
| Pod | metadata.namespace | Resource workload đang chạy |
| Service DNS | namespace của Service | Tên phân giải và điểm gọi |
| ServiceAccount | namespace của Pod và object | Authentication identity |
| Kubernetes client | in-cluster config, kubeconfig hoặc code | Request API đến namespace nào |
| Spring config | property hoặc nguồn cấu hình | Integration đọc resource ở đâu |

Không được thấy kubectl đang ở namespace team-a rồi kết luận Pod cũng thuộc team-a. Kubectl là công cụ bên ngoài; Pod metadata mới là identity của workload.

## 4. Namespace mặc định của kubectl

### 4.1. Context quyết định namespace

kubectl dùng context trong kubeconfig. Context thường chứa cluster, user và namespace mặc định. Kiểm tra trước khi đọc hoặc thay đổi resource:

    kubectl config current-context
    kubectl config get-contexts
    kubectl config view --minify

Nếu context không có namespace, kubectl thường dùng namespace mặc định theo behavior của lệnh. Vì vậy, runbook nên ghi rõ namespace bằng tùy chọn -n:

    kubectl get pods -n team-a
    kubectl get service inventory -n team-a

### 4.2. Vì sao lệnh không thấy resource?

Lệnh sau có thể không trả về Pod dù Pod tồn tại:

    kubectl get pods

Nguyên nhân có thể là:

- context đang ở namespace khác;
- resource thuộc namespace khác;
- user không có quyền list Pod ở namespace đó;
- Pod không tồn tại hoặc đã bị xóa.

Kiểm tra tất cả namespace chỉ khi user có quyền và phạm vi chẩn đoán cho phép:

    kubectl get pods --all-namespaces

Trong môi trường nhiều tenant, không nên mặc định yêu cầu quyền xem tất cả namespace chỉ để tiện thao tác.

### 4.3. Tùy chọn -n

Tùy chọn -n áp dụng cho command đang chạy. Nó không thay đổi namespace của Pod hoặc context lâu dài:

    kubectl get deployment order-service -n team-a

Đặt -n rõ ràng giúp lệnh có thể đọc lại và giảm rủi ro chạy nhầm context. Khi áp dụng manifest, namespace trong file và namespace trên command cần được kiểm tra cùng nhau.

## 5. Namespace của Pod

### 5.1. metadata.namespace

Pod namespaced có trường metadata.namespace:

    metadata:
      name: order-service-abcde
      namespace: team-a

Nếu manifest không ghi namespace, object có thể được tạo trong namespace mặc định của request hoặc namespace do công cụ triển khai chọn. Không nên bỏ qua field này trong manifest production nếu namespace là một phần của hợp đồng.

### 5.2. Downward API

Pod có thể nhận namespace của chính mình qua Downward API:

    env:
      - name: POD_NAMESPACE
        valueFrom:
          fieldRef:
            fieldPath: metadata.namespace

Ứng dụng Spring có thể dùng biến này để log context hoặc chọn scope của ConfigMap khi thiết kế cho phép:

    POD_NAMESPACE=team-a

Không ghi đè namespace bằng giá trị build-time nếu ứng dụng được triển khai ở nhiều namespace. Runtime metadata phản ánh nơi Pod thực sự đang chạy.

### 5.3. ServiceAccount namespace file

In-cluster client có thể đọc namespace được mount cùng ServiceAccount theo chính sách cluster. Đường dẫn và cơ chế mount có thể thay đổi theo token projection hoặc runtime, nên dùng helper chính thức hoặc kiểm tra path đã triển khai.

File namespace chỉ cho biết Pod namespace. Nó không cấp quyền và không chứng minh ConfigMap hoặc Service cần dùng nằm cùng namespace.

## 6. Namespace của Service và DNS

### 6.1. Tên ngắn trong cùng namespace

Nếu Service inventory nằm trong namespace team-a, Pod cùng namespace thường có thể gọi:

    http://inventory

DNS resolver của Pod bổ sung search domain theo namespace. Cùng tên ngắn có thể trỏ đến Service khác khi Pod ở namespace khác.

### 6.2. Gọi sang namespace khác

Có thể dùng:

    http://inventory.team-a

Hoặc tên đầy đủ theo cluster domain:

    http://inventory.team-a.svc.cluster.local

Cluster domain có thể khác giữa môi trường. Không ghi cứng cluster.local nếu hạ tầng không cam kết giá trị đó.

### 6.3. Namespace không thay thế NetworkPolicy

DNS phân giải được tên không có nghĩa request được phép đi qua. Cross-namespace call còn phụ thuộc NetworkPolicy, firewall, service mesh, port, protocol và readiness của backend.

## 7. Namespace của ConfigMap và Secret

ConfigMap và Secret thường namespaced. Pod ở team-a không tự đọc được resource cùng tên ở team-b:

    team-a/order-service-config
    team-b/order-service-config

Nếu ứng dụng cần cấu hình ở namespace khác, cần thiết kế client namespace, ServiceAccount, RoleBinding, NetworkPolicy và phạm vi bảo mật rõ ràng. Đổi tên resource không tạo quyền cross-namespace.

Reference trong Pod spec thường được resolve trong namespace của Pod:

    volumes:
      - name: application-config
        configMap:
          name: order-service-config

Resource được tham chiếu ở đây được tìm trong namespace của Pod. Volume reference không tự cross-namespace.

## 8. Namespace và ServiceAccount

ServiceAccount cũng namespaced:

    serviceAccountName: order-service

Identity đầy đủ thường được biểu diễn như:

    system:serviceaccount:team-a:order-service

RoleBinding ở team-a có thể gán Role cho ServiceAccount team-a. Nếu cần đọc resource team-b, phải xem xét RoleBinding ở team-b hoặc cơ chế quyền rộng hơn theo chính sách. ServiceAccount cùng tên ở team-b không cấp quyền cho identity team-a.

Khi nhận 403, kiểm tra:

1. Pod đang ở namespace nào?
2. Pod dùng ServiceAccount nào?
3. RoleBinding gán đúng subject namespace chưa?
4. Resource đích nằm ở namespace nào?
5. Rule có resource và verb phù hợp không?

Không cấp cluster-admin chỉ vì client cần đọc một ConfigMap khác namespace.

## 9. Namespace trong Kubernetes client

Client chạy trong Pod thường lấy API host, CA và ServiceAccount credential từ môi trường hoặc filesystem được mount. Namespace có thể lấy từ metadata của Pod, file namespace hoặc cấu hình explicit.

Ứng dụng cần quyết định:

- chỉ đọc resource trong namespace hiện tại;
- đọc một namespace cấu hình cố định;
- đọc nhiều namespace;
- đọc resource cluster-scoped.

Không để client tự suy đoán namespace từ tên Service. Namespace là field riêng và cần được truyền rõ trong API call.

Client chạy ngoài cluster thường dùng kubeconfig context. Namespace mặc định của kubeconfig có thể khác namespace Deployment. Một job CI có thể apply manifest vào namespace được truyền bởi pipeline, còn kubeconfig vẫn có default namespace khác.

Spring Cloud Kubernetes có thể lấy namespace từ in-cluster metadata, property, client context hoặc implementation mặc định. Tên property và behavior phụ thuộc module và release. Khi cấu hình discovery hoặc config, phải xác định namespace hiệu lực bằng log, metric hoặc request an toàn.

## 10. Namespace của DiscoveryClient và LoadBalancer

Discovery có thể được giới hạn trong namespace hiện tại hoặc mở rộng theo thiết kế:

| Phạm vi | Lợi ích | Chi phí và rủi ro |
| --- | --- | --- |
| Namespace hiện tại | Quyền hẹp, tên service dễ hiểu | Không thấy service ở namespace khác |
| Một namespace cố định | Hợp đồng rõ cho dependency | Cần cross-namespace RBAC |
| Nhiều namespace | Hỗ trợ shared platform | Cache, quyền và tên service dễ nhầm |
| Cluster-wide | Quan sát rộng | Quyền lớn và rủi ro lộ metadata |

Nếu hai namespace cùng có Service inventory, discovery multi-namespace cần metadata namespace để không trộn instance. Chỉ service ID inventory là chưa đủ nếu name không unique trên toàn cluster.

Chuỗi:

    http://inventory

có thể là DNS Service trong namespace hiện tại hoặc service ID do DiscoveryClient trả về. Khi đổi namespace của dependency, kiểm tra URL, discovery scope, DNS search domain, NetworkPolicy, RBAC và cache instance cũ.

## 11. Namespace và Configuration Watcher

Configuration Watcher cần biết resource nào được theo dõi. Nếu watcher quan sát namespace team-a còn ConfigMap nằm team-b, event sẽ không đến trừ khi scope và quyền phù hợp.

Thiết kế cần nêu:

- watcher chạy ở namespace nào;
- theo dõi ConfigMap và Secret nào;
- ứng dụng nhận thông báo thuộc namespace nào;
- Role hoặc ClusterRole cấp list/watch ở đâu;
- cross-namespace event có được phép về bảo mật không;
- mỗi replica nhận update bằng cách nào.

Tài nguyên cùng tên ở hai namespace có thể phát event khác nhau. Log watcher nên ghi namespace và resource name, nhưng không ghi Secret data.

## 12. Namespace, RBAC và phạm vi quyền

Role chỉ mô tả quyền trong một namespace:

    apiVersion: rbac.authorization.k8s.io/v1
    kind: Role
    metadata:
      name: order-config-reader
      namespace: team-a
    rules:
      - apiGroups: [""]
        resources: ["configmaps"]
        verbs: ["get"]

Role trên không cấp quyền đọc ConfigMap team-b. RoleBinding cũng namespaced và cần gán đúng subject. ClusterRoleBinding có phạm vi rộng hơn và chỉ nên dùng khi có yêu cầu rõ.

Kiểm tra quyền theo đúng identity:

    kubectl auth can-i get configmaps \
      --as=system:serviceaccount:team-a:order-service \
      -n team-a

Và kiểm tra namespace khác nếu use case có cross-namespace:

    kubectl auth can-i get configmaps \
      --as=system:serviceaccount:team-a:order-service \
      -n team-b

Hai câu hỏi có thể cho kết quả khác. Không cấp cluster-admin chỉ vì client cần đọc một ConfigMap khác namespace.

## 13. Namespace, quota và manifest

Namespace còn liên quan đến quota và limit range. Pod có thể Pending vì namespace hết quota CPU, memory hoặc số lượng object. Khi điều tra, phân biệt quota namespace với capacity node.

Manifest production nên làm rõ namespace:

    apiVersion: apps/v1
    kind: Deployment
    metadata:
      name: order-service
      namespace: team-a

Nếu manifest được render theo môi trường, pipeline phải bảo đảm namespace không rỗng và không trỏ nhầm production. Tùy chọn -n của kubectl chỉ áp dụng cho command; nó không thay đổi metadata của Pod hoặc context lâu dài.

Không dùng namespace name như một cơ chế bảo mật duy nhất. Credential và policy cần được bảo vệ độc lập.

## 14. Quy trình xác định namespace của ứng dụng

Khi nhận một Pod hoặc service Spring, làm theo thứ tự:

1. Xác định cluster và context đang quan sát.
2. Đọc metadata.namespace của Deployment hoặc Pod.
3. Đọc serviceAccountName và identity đầy đủ.
4. Đọc Service, ConfigMap và Secret reference.
5. Kiểm tra selector và Service endpoint trong đúng namespace.
6. Kiểm tra discovery hoặc config integration được cấu hình scope nào.
7. Kiểm tra RoleBinding và resource namespace.
8. Thực hiện smoke test bằng DNS hoặc service ID đúng phạm vi.

Các lệnh read-only thường dùng:

    kubectl get deployment order-service -n team-a -o yaml
    kubectl get pod -l app=order-service -n team-a -o wide
    kubectl get service order-service -n team-a
    kubectl get configmap order-service-config -n team-a
    kubectl get serviceaccount order-service -n team-a
    kubectl get rolebinding -n team-a

Không kết luận từ kubectl context duy nhất. Hãy kiểm tra namespace thực trên object.

## 15. Tình huống chẩn đoán

### ConfigMap NotFound

Kiểm tra Pod ở namespace nào, ConfigMap tồn tại ở đâu, client lấy namespace từ đâu, tên key có chính xác không và config integration có scope mặc định khác không. Copy tên resource sang cấu hình không tạo quyền cross-namespace.

### Discovery không thấy inventory

Kiểm tra Service namespace, DNS hay service ID, discovery scope, endpoint Ready, quyền list/watch và NetworkPolicy. Service tồn tại ở namespace khác chưa đủ để request hoạt động.

### 403 khi đọc Secret

Xác định identity theo dạng:

    system:serviceaccount:<pod-namespace>:<service-account>

Sau đó kiểm tra RoleBinding tại namespace chứa Secret. Không sửa bằng quyền đọc mọi Secret trong cluster.

### kubectl thấy Pod nhưng ứng dụng không thấy resource

kubectl user và Pod ServiceAccount là hai danh tính khác nhau. Quyền của kubectl không đại diện cho ServiceAccount của ứng dụng.

## 16. Những hiểu nhầm thường gặp

**Namespace của kubectl là namespace của ứng dụng.** Context chỉ là phạm vi mặc định của lệnh; Pod metadata mới xác định namespace workload.

**Cùng tên Service nghĩa là cùng endpoint.** Service identity gồm namespace và name.

**Biết tên ConfigMap là mount được resource khác namespace.** Reference trong Pod spec thường được resolve trong namespace của Pod.

**DNS thông suốt namespace thì RBAC cũng thông.** DNS và RBAC là hai lớp khác nhau.

**ServiceAccount cùng tên ở namespace khác là cùng identity.** ServiceAccount namespaced.

**ClusterRole luôn cần ClusterRoleBinding.** ClusterRole có thể được bind trong phạm vi namespace bằng RoleBinding tùy thiết kế.

## 17. Checklist xác định namespace

- [ ] Cluster và kubectl context đã xác nhận.
- [ ] Namespace trên Deployment hoặc Pod đã đọc trực tiếp.
- [ ] ServiceAccount và identity đầy đủ đã xác định.
- [ ] Service name đi cùng namespace.
- [ ] ConfigMap và Secret nằm ở namespace dự kiến.
- [ ] Discovery và watcher có scope rõ.
- [ ] Role và RoleBinding nằm đúng namespace.
- [ ] Quyền cross-namespace được cấp có chủ ý.
- [ ] NetworkPolicy cho phép đúng đường kết nối.
- [ ] Runbook ghi namespace explicit.

## 18. Tự kiểm tra mức độ hiểu

**Câu 1: Resource namespaced được định danh thế nào?**

Bằng cặp namespace và name. Cùng name ở hai namespace là hai object khác nhau.

**Câu 2: Làm sao biết Pod đang chạy ở namespace nào?**

Đọc metadata.namespace của Pod hoặc Deployment, hoặc truyền namespace qua Downward API. Không suy ra chỉ từ namespace mặc định của kubectl.

**Câu 3: Service inventory trong team-a được gọi bằng tên ngắn từ Pod team-b có chắc đúng không?**

Không. Tên ngắn dùng search domain của namespace hiện tại. Nên dùng tên có namespace hoặc DNS đầy đủ theo thiết kế, rồi kiểm tra NetworkPolicy và endpoint.

**Câu 4: Vì sao kubectl đọc được ConfigMap nhưng Pod nhận 403?**

Kubectl và Pod dùng hai danh tính khác nhau. Quyền của kubectl không đại diện cho ServiceAccount của ứng dụng.

**Câu 5: Namespace file của Pod có cấp quyền API không?**

Không. Nó chỉ cung cấp thông tin namespace. Authentication đến từ token hoặc credential, còn quyền do RBAC quyết định.

## Kết luận

Namespace là một phần của phạm vi và identity, không phải một giá trị trang trí trong manifest. Để xác định ứng dụng đang chạy ở đâu, hãy đọc metadata của Pod, ServiceAccount, Service, ConfigMap và Secret; đồng thời phân biệt namespace của kubectl với namespace runtime.

Spring Cloud Kubernetes, DiscoveryClient và Kubernetes client chỉ hoạt động đúng khi scope được thiết kế rõ: service ID phân giải trong namespace nào, ConfigMap và Secret được đọc ở đâu, watcher theo dõi resource nào, và ServiceAccount có quyền gì. Ghi namespace explicit, kiểm tra cross-namespace có chủ ý và dùng quyền tối thiểu sẽ làm hệ thống dễ vận hành hơn và tránh nhiều lỗi NotFound, 403, DNS cùng discovery rỗng.
