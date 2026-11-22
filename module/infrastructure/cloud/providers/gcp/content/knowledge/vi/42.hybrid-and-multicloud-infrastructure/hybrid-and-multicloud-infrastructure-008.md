# Quản lý chính sách và cấu hình Kubernetes xuyên cluster

Một tổ chức có thể vận hành nhiều Kubernetes cluster: GKE production ở các region khác nhau, GKE staging, Kubernetes tại trung tâm dữ liệu và cluster do một nhà cung cấp cloud khác quản lý. Nếu mỗi cluster được cấu hình thủ công, các chính sách về quyền truy cập, bảo mật pod, namespace, network và quota rất dễ bị lệch. Một cluster có thể chặn container đặc quyền trong khi cluster khác vẫn cho phép; cùng một ứng dụng có thể hoạt động ở staging nhưng bị từ chối khi triển khai production.

Quản lý cấu hình xuyên cluster là bài toán về **trạng thái mong muốn, quyền sở hữu, phân phối thay đổi và kiểm chứng tuân thủ**. Trên Google Cloud, GKE fleets và các công cụ như Config Sync, Policy Controller có thể giúp quản trị nhất quán trong phạm vi sản phẩm hỗ trợ. Với cluster ở môi trường khác, tổ chức cũng có thể sử dụng GitOps controllers, admission policies và hệ thống kiểm tra độc lập. Điều quan trọng là thiết kế hợp đồng chung và quy trình kiểm soát thay đổi, chứ không mặc định rằng đăng ký một cluster vào fleet sẽ tự động áp mọi chính sách lên cluster đó.

## 1. Phân biệt cấu hình, chính sách và trạng thái vận hành

Ba khái niệm liên quan nhưng không thay thế nhau:

| Khái niệm | Ví dụ | Mục tiêu |
| --- | --- | --- |
| Cấu hình mong muốn | Namespace, ResourceQuota, Deployment, ConfigMap, RBAC | Xác định resource cần tồn tại với giá trị nào |
| Chính sách | Chặn pod đặc quyền, yêu cầu labels, giới hạn registry image | Xác định cấu hình hoặc hành vi nào được chấp nhận |
| Trạng thái vận hành | Pod Ready, HPA đang scale, request latency, cảnh báo | Kiểm tra kết quả thực tế của hệ thống sau khi áp cấu hình |

GitOps controller có thể đồng bộ Deployment theo bản khai báo trong Git, nhưng Deployment vẫn có thể gặp lỗi image pull hoặc thiếu tài nguyên. Admission policy có thể từ chối manifest vi phạm quy tắc, nhưng không bảo đảm ứng dụng phục vụ traffic đúng SLO. Vì vậy, cần quan sát cả trạng thái đồng bộ, tuân thủ và sức khỏe workload.

Một mục tiêu quản trị có thể đo được: mọi cluster production phải có chính sách bảo mật pod tương đương, namespace sở hữu bởi đúng đội, không có thay đổi thủ công tồn tại lâu hơn thời hạn cho phép, và khi chính sách gây lỗi phải có cách rollback đã diễn tập.

## 2. Kiểm kê cluster và phân loại phạm vi quản trị

Trước khi triển khai công cụ, tạo inventory cho toàn bộ cluster:

| Thuộc tính | Ví dụ | Vì sao quan trọng |
| --- | --- | --- |
| Môi trường | dev, staging, production | Quyết định mức kiểm soát và nhịp phát hành |
| Nền tảng | GKE, on-prem Kubernetes, EKS, AKS | Khác biệt IAM, CNI, admission và tính năng quản lý |
| Phiên bản Kubernetes | Minor version và API được hỗ trợ | Tránh áp manifest không tương thích |
| Vị trí | Region, zone, datacenter | Độ trễ, residency, khả năng kết nối tới Git |
| Chủ sở hữu | Platform team, business team | Ai được thay đổi cấu hình và xử lý sự cố |
| Mức độ quan trọng | Tier 0/1/2 | Xác định kiểm tra và canary rollout |
| Nguồn cấu hình | Git repo, branch, revision, sync controller | Biết nguồn sự thật và tiến độ cập nhật |
| Baseline chính sách | Pod Security, RBAC, NetworkPolicy, quota | Phát hiện cluster chưa có kiểm soát cần thiết |

Không nên đưa mọi cluster vào một nhóm đồng nhất chỉ vì cùng dùng Kubernetes. Ví dụ, GKE Dataplane V2 và một CNI ở on-prem có thể có cách thực thi NetworkPolicy khác nhau; Pod Security Admission được hỗ trợ rộng trong Kubernetes nhưng cấu hình ngoại lệ và admission webhooks có thể khác. Cần kiểm tra từng chính sách trên mỗi loại nền tảng.

## 3. Phân định trách nhiệm giữa fleet, cluster và namespace

Trong Google Cloud, **fleet** cung cấp một mô hình nhóm và nhận diện các cluster dùng chung khả năng quản lý của GKE. Thành viên fleet có thể gồm các loại cluster được hỗ trợ, nhưng khả năng sử dụng Config Sync, Policy Controller hoặc tính năng fleet khác phụ thuộc loại cluster, phiên bản, vị trí và điều kiện cấp quyền.

Nên chia cấu hình thành ba lớp:

1. **Baseline tổ chức/fleet:** quy tắc bắt buộc về labels, Pod Security, audit, nguyên tắc registry và quyền quản trị.
2. **Cấu hình cluster:** ingress, storage class, cấu hình network, namespace hệ thống và những ngoại lệ hợp lệ của từng cluster.
3. **Cấu hình ứng dụng/namespace:** Deployment, Service, ConfigMap, HPA, quota và RoleBinding theo workload.

Nhóm platform thường sở hữu các đối tượng cluster-scoped và chính sách bảo mật. Nhóm ứng dụng chỉ sở hữu các tài nguyên trong namespace đã được ủy quyền. Tách quyền ở ranh giới này ngăn một pull request của ứng dụng vô tình sửa ClusterRole, webhook hoặc policy áp dụng toàn cluster.

Trên một cluster, resource cluster-scoped không chịu namespace isolation. Vì thế, không nên để mọi nhóm tự tạo ClusterRole, CustomResourceDefinition hoặc ConstraintTemplate qua cùng luồng GitOps không có phê duyệt đặc biệt.

## 4. Kiến trúc tham chiếu: Git là nguồn sự thật

Một mô hình triển khai phổ biến là lưu cấu hình và policy trong repository được bảo vệ, kiểm tra qua CI, sau đó controller của từng cluster kéo đúng phiên bản và đối chiếu trạng thái thực tế với mong muốn.

~~~mermaid
flowchart TB
  Dev["Platform / Security / App teams"] --> PR["Pull request + review"]
  PR --> CI["Schema, policy, security và dry-run tests"]
  CI --> Git["Git config repositories"]
  Git --> DevSync["GitOps controller - staging"]
  DevSync --> Staging["GKE staging"]
  Git --> ProdSync["GitOps controller - production"]
  ProdSync --> Prod["GKE production"]
  Git --> HybridSync["GitOps controller - external cluster"]
  HybridSync --> Hybrid["On-prem / cloud khác"]
  Staging --> Observe["Sync status + policy compliance + workload health"]
  Prod --> Observe
  Hybrid --> Observe
  Observe --> Feedback["Alert, rollback, remediation"]
  Feedback --> PR
~~~

Các controller chạy bên trong hoặc gần cluster, kéo cấu hình từ nguồn được tin cậy và áp dụng với danh tính có quyền phù hợp. Mô hình **pull** thường giảm nhu cầu lưu kubeconfig có quyền cluster-admin cho tất cả cluster trong một máy CI trung tâm.

Một thay đổi chỉ được coi là hoàn tất khi đã được commit/phê duyệt, đồng bộ đến đúng cluster, admission không từ chối và tín hiệu vận hành ổn định. Việc merge pull request không đồng nghĩa mọi cluster đã nhận thành công cấu hình.

## 5. Thiết kế repository đa cluster

Có thể tách repository quản trị nền tảng và repository ứng dụng, hoặc tổ chức monorepo có quy tắc CODEOWNERS chặt chẽ. Ví dụ một repository platform:

~~~text
platform-kubernetes-config/
├── base/
│   ├── namespaces/
│   ├── rbac/
│   ├── network-policies/
│   ├── quotas/
│   └── policy-constraints/
├── overlays/
│   ├── staging/
│   ├── prod-asia/
│   ├── prod-europe/
│   └── onprem/
├── rendered/
│   ├── staging/
│   ├── prod-asia/
│   ├── prod-europe/
│   └── onprem/
├── tests/
└── README.md
~~~

Thư mục **base** thể hiện những quy tắc và cấu hình có thể chia sẻ; **overlays** chứa khác biệt được phê duyệt theo môi trường; **rendered** là YAML đầu ra nếu pipeline chọn cách dựng Kustomize/Helm trong CI trước khi GitOps controller đồng bộ. Đây là một lựa chọn tổ chức, không phải cấu trúc bắt buộc của Config Sync.

Tránh tạo bản sao đầy đủ của toàn bộ manifest cho mỗi cluster. Sao chép làm việc sửa một lỗi bảo mật phải lặp trên nhiều thư mục và dễ bỏ sót. Tuy nhiên cũng không nên ép mọi cluster dùng một file không có khác biệt khi CNI, Kubernetes version hoặc yêu cầu lưu trú dữ liệu khác nhau.

Một chiến lược rõ ràng là dùng một baseline chung, thay đổi có giới hạn ở overlay và ghi nhận lý do cho mọi exception. Ví dụ, production có quota và namespace policy chặt hơn staging, còn on-prem sử dụng storage class riêng nhưng cùng tiêu chuẩn labels và non-root containers.

## 6. Kustomize và Helm trong quy trình phân phối

**Kustomize** hữu ích khi nhiều môi trường dùng cùng Kubernetes resources nhưng khác replicas, tên namespace, image hoặc một số trường cấu hình. **Helm** hữu ích khi ứng dụng được đóng gói thành chart có giao diện values và vòng đời release rõ ràng. Cả hai cần được kiểm tra đầu ra trước khi deploy.

Ví dụ overlay Kustomize thay số replicas:

~~~yaml
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization
resources:
  - ../../base/orders-api
patches:
  - target:
      kind: Deployment
      name: orders-api
    patch: |-
      - op: replace
        path: /spec/replicas
        value: 3
~~~

Đây là tệp **kustomization.yaml** ở overlay production. Resource Deployment trong base phải có tên và đường dẫn đúng như ví dụ. Có thể xem YAML đầu ra trước khi đưa vào nguồn đồng bộ:

~~~bash
kubectl kustomize overlays/prod-asia
~~~

Với Helm, tương tự có thể chạy **helm template** với chart và values tương ứng để tạo manifest và kiểm tra policy. Không nên cho pipeline ghi trực tiếp output chưa được review vào nhiều cluster production.

Config Sync và các GitOps controllers không có cấu hình xử lý Kustomize/Helm hoàn toàn giống nhau ở mọi phiên bản. Một cách giảm phụ thuộc là render trong CI và lưu/đưa YAML đã kiểm định vào thư mục mà controller thực sự theo dõi. Nếu muốn controller render trực tiếp, cần kiểm tra capability và cấu hình của sản phẩm đang dùng, rồi quyết định nơi bảo đảm tính tái lập của đầu ra.

## 7. Config Sync trên GKE: vai trò và cơ chế đồng bộ

**Config Sync** hỗ trợ đưa cấu hình khai báo vào cluster và phát hiện/sửa drift theo phạm vi quản lý. Các kiểu đối tượng chính:

| Đối tượng | Phạm vi | Vai trò |
| --- | --- | --- |
| RootSync | Đồng bộ cấu hình có thể bao gồm cluster-scoped và namespace-scoped objects theo quyền | Thường do platform team sở hữu |
| RepoSync | Đồng bộ cấu hình giới hạn ở một namespace theo cơ chế phân quyền phù hợp | Hữu ích để giao nhóm ứng dụng tự quản lý tài nguyên trong namespace |
| Nguồn Git hoặc nguồn được hỗ trợ | Chứa trạng thái mong muốn | Cần xác thực, kiểm tra commit và giám sát thay đổi |
| Sync/reconciler status | Cho biết trạng thái kéo, render và áp dụng | Dùng để phát hiện lỗi hoặc cluster bị chậm phiên bản |

RootSync và RepoSync là các Custom Resources của Config Sync, không phải tính năng có sẵn trên một cluster Kubernetes chưa cài Config Sync. Khi hoạt động theo mô hình GitOps, controller định kỳ đối chiếu resource với trạng thái mong muốn và có thể đưa resource bị chỉnh trực tiếp trở về giá trị từ nguồn.

Tính năng tự sửa drift có giá trị, nhưng cũng có rủi ro: nếu source commit sai, controller có thể áp dụng sai cho nhiều cluster. Vì thế cần phê duyệt, thử nghiệm theo vòng và cơ chế dừng đồng bộ trong tình huống khẩn cấp.

## 8. Ví dụ RootSync cho một cluster

Ví dụ RootSync đồng bộ những manifest đã render của cluster production tại một thư mục riêng:

~~~yaml
apiVersion: configsync.gke.io/v1beta1
kind: RootSync
metadata:
  name: root-sync
  namespace: config-management-system
spec:
  sourceType: git
  git:
    repo: https://git.example.com/platform/kubernetes-config.git
    branch: main
    dir: rendered/prod-asia
    auth: none
    period: 60s
~~~

Ví dụ giả định repository công khai chỉ-đọc để minh họa cú pháp. **auth: none không phù hợp cho Git repository private**; môi trường thật cần chọn phương án xác thực được Config Sync hỗ trợ (chẳng hạn SSH token/credential hoặc workload identity trong môi trường hỗ trợ) và giới hạn quyền chỉ đọc. Không đưa private key, access token hay kubeconfig vào manifest commit.

Thư mục rendered/prod-asia cần chứa những object hợp lệ cho cluster đích. Không dùng cùng đường dẫn chung cho cả staging và production nếu hai môi trường có policy khác nhau. Cấu hình nguồn cùng nhánh main có thể phù hợp nếu quá trình promotion kiểm soát nội dung của các thư mục; nếu cần cố định revision cho từng môi trường, hãy thiết kế chiến lược version hoặc promotion thích hợp với các trường được phiên bản Config Sync hỗ trợ.

Sau khi Config Sync được cài đặt và cấp quyền, có thể quan sát:

~~~bash
kubectl --context=GKE_PROD_CONTEXT \
  -n config-management-system get rootsync

kubectl --context=GKE_PROD_CONTEXT \
  -n config-management-system describe rootsync root-sync
~~~

Đừng xem một lệnh **kubectl apply** thành công là bằng chứng đã đồng bộ. Cần xem trạng thái sync/reconcile, các lỗi fetch, authorization, render hoặc admission; xác minh resource mục tiêu có phiên bản và nội dung đúng.

## 9. RepoSync và quyền sở hữu theo namespace

RepoSync hỗ trợ mô hình phân quyền khi team được phép quản lý resource trong namespace của mình, trong khi platform giữ quyền đối với những thành phần cấp cluster.

Một quy trình hợp lý:

1. Platform team tạo namespace, quota, RBAC và baseline security trước.
2. Platform phê duyệt danh tính dùng để đồng bộ RepoSync trong namespace đó.
3. Team ứng dụng quản lý Deployment, Service, ConfigMap và HPA theo quyền được cấp.
4. Admission policies ngăn resource vượt ranh giới bảo mật.
5. Controller đồng bộ và báo lỗi khi quyền không đủ hoặc cấu hình bị từ chối.

Không cấp cluster-admin cho RepoSync chỉ để tránh lỗi thiếu quyền. Nếu một ứng dụng thật sự cần ClusterRole, CRD hoặc webhook, chuyển thay đổi đó sang quy trình quản lý platform với review riêng. Thêm quyền vào service account của controller cũng là thay đổi bảo mật, cần được kiểm soát như thay đổi code production.

## 10. Policy Controller và admission policies

**Policy Controller** trong hệ sinh thái GKE dùng các cơ chế dựa trên OPA/Gatekeeper để kiểm tra resource theo các chính sách được khai báo. Điều này khác với Config Sync:

- Config Sync cố gắng làm cho các resource được quản lý khớp với Git.
- Policy Controller đánh giá resource có tuân thủ constraint hay không; các chế độ phù hợp có thể kiểm tra lúc admission, audit resource đang tồn tại hoặc triển khai theo mức độ enforcement.

Một rule có thể yêu cầu namespace mang nhãn owner, chặn image từ registry không được phép, hoặc ngăn workload dùng thiết lập đặc quyền. Một thư viện constraint template có thể cung cấp các loại policy sẵn có; các chính sách tùy biến phải được thử nghiệm kỹ vì webhook lỗi có thể ảnh hưởng khả năng triển khai trên cluster.

Nên phân biệt ba giai đoạn:

| Giai đoạn | Cách thực hiện | Mục tiêu |
| --- | --- | --- |
| CI check | Kiểm tra manifest đã render trước merge | Trả lỗi sớm cho người phát triển |
| Audit / dry-run | Quan sát những resource hiện có vi phạm policy | Ước lượng tác động, tránh chặn đột ngột |
| Enforce | Chặn create/update không tuân thủ theo cấu hình admission | Bảo vệ cluster sau khi đã xử lý ngoại lệ |

Đừng kích hoạt deny toàn fleet ngay khi vừa viết một constraint. Hãy thử với workload và API version thực tế, đánh giá các hệ thống controller và namespace thiết yếu, rồi mới nâng mức enforcement.

## 11. Ví dụ policy yêu cầu nhãn sở hữu namespace

Policy Controller/Gatekeeper có thể dùng loại constraint **K8sRequiredLabels** nếu ConstraintTemplate tương ứng đã được cài đặt từ thư viện chính sách tương thích.

~~~yaml
apiVersion: constraints.gatekeeper.sh/v1beta1
kind: K8sRequiredLabels
metadata:
  name: namespaces-require-owner
spec:
  enforcementAction: dryrun
  match:
    kinds:
      - apiGroups: [""]
        kinds: ["Namespace"]
  parameters:
    labels:
      - key: owner
~~~

Ví dụ đang dùng chế độ **dryrun** để kiểm kê vi phạm thay vì chặn ngay các request. Khi đã kiểm tra compatibility, xử lý resource hiện có và quy trình ngoại lệ, nhóm có thể cân nhắc enforcementAction tương ứng để chặn những thay đổi vi phạm.

Lưu ý rằng constraint không tự định nghĩa K8sRequiredLabels. Cluster phải có ConstraintTemplate/constraint type hợp lệ; nếu chưa có, manifest sẽ bị Kubernetes API từ chối vì không nhận diện loại resource. Tên và schema của constraint template phải được kiểm tra theo phiên bản thư viện đang chạy.

Một namespace có nhãn owner hợp lệ:

~~~yaml
apiVersion: v1
kind: Namespace
metadata:
  name: orders
  labels:
    owner: commerce-platform
    environment: production
~~~

Nhãn owner giúp truy vết đội chịu trách nhiệm; nó không phải cơ chế xác thực và không được dùng làm ranh giới quyền thay cho RBAC/IAM. Nếu cần kiểm tra danh sách owner được phép, chính sách phải quy định rõ điều kiện bổ sung.

## 12. Các lớp chính sách Kubernetes cần thống nhất

Không nên kỳ vọng một công cụ bao phủ mọi loại kiểm soát. Một baseline tốt có nhiều lớp:

| Kiểm soát | Công cụ hoặc cơ chế | Điều cần xác minh |
| --- | --- | --- |
| Pod Security | Pod Security Admission, policies hoặc Gatekeeper tùy thiết kế | Chặn workload đặc quyền và thiết lập nguy hiểm |
| RBAC | Role, RoleBinding, ClusterRole có kiểm soát | Ai có thể đọc, sửa hoặc tạo resource |
| Network segmentation | NetworkPolicy với data plane hỗ trợ | Namespace nào được nói chuyện với namespace nào |
| Resource isolation | ResourceQuota, LimitRange | Ngăn một đội chiếm hết tài nguyên cluster |
| Image controls | Admission checks, ký artifact, policy registry | Workload có dùng image được tin cậy không |
| Secrets | Secret Manager, CSI driver hoặc cơ chế phù hợp | Ai có quyền đọc bí mật và key nằm ở đâu |
| Audit | Kubernetes audit logs và Cloud Audit Logs theo nền tảng | Ai đã đổi policy, RBAC hoặc workload |
| GitOps integrity | Protected branch, review, provenance và sync status | Cấu hình triển khai có đúng revision đã phê duyệt không |

Ví dụ NetworkPolicy chặn ingress mặc định trong namespace orders:

~~~yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: default-deny-ingress
  namespace: orders
spec:
  podSelector: {}
  policyTypes:
    - Ingress
~~~

Policy này không mặc định chặn egress và cũng không tự tạo các allow rules cần cho ứng dụng. Sau khi áp dụng, phải bổ sung chính sách cho phép ingress cụ thể. Khả năng thực thi NetworkPolicy phụ thuộc vào CNI và cấu hình cluster; kiểm tra data plane thực tế trước khi coi file YAML là hàng rào bảo mật đã hoạt động.

Với Pod Security Admission, các mức như privileged, baseline và restricted có ý nghĩa trong Kubernetes, nhưng namespace exemptions và khả năng tương thích của workload hệ thống cần được thiết kế có chủ đích. Chặn nhầm admission của controller hoặc CNI có thể ảnh hưởng vận hành toàn cluster.

## 13. Tách IAM cloud và Kubernetes RBAC

Khi quản lý nhiều cluster, ít nhất có hai mặt phẳng danh tính: quyền gọi API quản lý hạ tầng cloud và quyền gọi Kubernetes API bên trong cluster. Một người có quyền xem GKE cluster không mặc nhiên có đầy đủ quyền quản trị resource trong Kubernetes.

Trên GKE, cần xem xét Google Cloud IAM, danh tính xác thực với control plane, Kubernetes RBAC và cơ chế Workload Identity Federation for GKE để workload truy cập Google Cloud APIs. Với EKS/AKS/on-prem, ánh xạ danh tính, OIDC và quyền cloud tương ứng có khác biệt.

Nguyên tắc:

- Người quản lý cấu hình Git không nhất thiết có quyền kubectl cluster-admin trực tiếp.
- Danh tính của GitOps controller chỉ có quyền trên resource và namespace nó phụ trách.
- CI cần quyền đọc và kiểm tra manifest; quyền ghi trực tiếp vào production API phải được hạn chế nếu đang dùng GitOps pull model.
- Workload identity của ứng dụng tách khỏi danh tính của controller đồng bộ.
- Quyền tạo admission webhook, CRD, ClusterRole và cấp quyền đặc biệt phải có review riêng.

Không lưu kubeconfig lâu dài với credential quyền cao trong repository hay môi trường CI chung. Dùng credential ngắn hạn và xác thực theo danh tính được kiểm toán khi môi trường hỗ trợ.

## 14. Secrets, ConfigMaps và dữ liệu nhạy cảm

ConfigMap phù hợp cho cấu hình không nhạy cảm; Kubernetes Secret không nên được xem là két chứa bí mật tuyệt đối chỉ vì giá trị được mã hóa base64. Secret vẫn phụ thuộc vào RBAC, encryption at rest, cách truyền, controller và cơ chế đọc tại node.

Với ứng dụng GCP, có thể tích hợp Secret Manager hoặc cơ chế đồng bộ/CSI được hỗ trợ để cung cấp bí mật cho workload. Đối với hybrid/multicloud, cần phân biệt kho bí mật nguồn, cơ chế cấp phát ngắn hạn, quyền truy cập từ mỗi cluster và yêu cầu residency.

Không commit plaintext token, mật khẩu hoặc service account key vào GitOps repo. Nếu cần cấu hình có tham chiếu secret, tài liệu hóa rõ trách nhiệm của External Secrets operator/CSI driver hoặc công cụ được chọn, cùng quyền truy cập và cách xoay vòng. Một manifest Kubernetes tham chiếu đến Secret chưa tồn tại có thể đồng bộ thành công nhưng workload vẫn không chạy được; phải quan sát cả hai lớp.

## 15. Promotion theo vòng và triển khai thay đổi có kiểm soát

Thay đổi policy cluster-scoped có phạm vi ảnh hưởng lớn hơn thay đổi một Deployment. Một rollout an toàn nên có thứ tự:

1. **Review thiết kế:** xác định resource và cluster chịu tác động, policy mới, ngoại lệ và điều kiện rollback.
2. **Kiểm tra tĩnh:** kiểm tra YAML/schema, output Kustomize/Helm, version API và các quy tắc bảo mật.
3. **Cluster thử nghiệm:** áp dụng trong môi trường có các workload đại diện.
4. **Audit/dry-run:** thu thập danh sách vi phạm và ước lượng tác động trước khi bật deny.
5. **Canary cluster:** chọn một cụm production có phạm vi rủi ro chấp nhận được, theo dõi sync và deployment.
6. **Mở rộng có kiểm soát:** rollout theo region, environment hoặc nhóm cluster, dừng khi có cảnh báo.
7. **Xác nhận hoàn tất:** kiểm tra commit được đồng bộ, số vi phạm mới và tình trạng workload.

Có thể dùng tag/branch hoặc các thư mục promotion khác nhau để giữ cấu hình production ở revision ổn định. Dù chọn mô hình nào, phải tránh nhánh production tự nhận thay đổi chưa được kiểm thử chỉ vì tất cả cluster đều theo dõi main. Những điều kiện quan trọng cần gate trước khi một revision đến được cluster production.

Nếu chính sách mới chặn một ứng dụng hợp lệ, rollback revision policy hoặc chuyển enforcement về mức audit theo quy trình đã thống nhất. Không khôi phục bằng cách tắt toàn bộ admission controls nếu chỉ một constraint có vấn đề.

## 16. Phát hiện drift và thay đổi khẩn cấp

**Configuration drift** xảy ra khi resource thực tế không còn khớp trạng thái trong nguồn khai báo. Nguyên nhân có thể là thao tác kubectl trực tiếp, controller khác sửa chung field, defaulting của API server hoặc một admission webhook thay đổi object.

Drift không phải lúc nào cũng là hành vi độc hại. Ví dụ HPA điều chỉnh replicas trong khi GitOps tiếp tục ép Deployment về một số replicas cố định sẽ tạo xung đột điều khiển. Cần xác định field ownership: HPA quản lý số replica khi autoscaling được bật; GitOps quản lý HPA spec và những trường khác, không cố chống lại hoạt động hợp lệ.

Khi phát hiện drift:

1. Xác định resource, cluster, field và timestamp bị thay.
2. Kiểm tra audit logs, actor, admission và controller có liên quan.
3. Xác định Git hay một controller khác phải là nguồn sự thật cho field đó.
4. Nếu drift ngoài kế hoạch, phục hồi bằng commit hoặc reconciliation có kiểm soát.
5. Nếu do sự cố production, ghi nhận **break-glass** có người chịu trách nhiệm và thời hạn kết thúc.
6. Sau khi khắc phục, đưa trạng thái khẩn cấp trở lại nguồn khai báo để tránh controller ghi đè bất ngờ.

Không sửa trực tiếp một resource đang được GitOps quản lý rồi quên đồng bộ Git. Controller có thể hoàn nguyên thay đổi chỉ sau một chu kỳ. Với break-glass, cần hướng dẫn rõ cách tạm dừng hoặc giới hạn sync theo sản phẩm, quyền truy cập tối thiểu và cách bật lại để tránh mất kiểm soát.

## 17. Tránh xung đột giữa nhiều controllers

Một cluster có thể cùng chạy Config Sync, Flux/Argo CD, Helm release controllers, HPA và operator của ứng dụng. Nếu hai controller quản lý cùng object hoặc cùng field với mục tiêu khác nhau, vòng reconciliation có thể thay đổi resource qua lại liên tục.

Hãy công bố ma trận sở hữu:

| Resource hoặc nhóm field | Chủ sở hữu đề xuất |
| --- | --- |
| ClusterRole, ConstraintTemplate, policy baseline | Platform GitOps |
| Namespace và quota | Platform, hoặc team được ủy quyền theo policy |
| Deployment image và container config | Application GitOps/CI |
| HPA target và min/max replicas | Application GitOps |
| Deployment replicas khi HPA hoạt động | HPA, theo cách tích hợp được hỗ trợ |
| Secret data | Secret management controller hoặc hệ thống được chỉ định |
| Status fields của Kubernetes resources | Kubernetes controllers, không dùng Git làm trạng thái mong muốn |

Một manifest có thể được API server thay đổi bởi defaulting hoặc mutation webhook. Đặt quy tắc ignore differences/ownership của công cụ GitOps theo đúng semantics và kiểm tra tác động bảo mật; tránh bỏ qua toàn bộ resource chỉ để dập cảnh báo drift.

## 18. Hybrid/multicloud: khả năng tương thích và kết nối

Quản lý xuyên cluster không đồng nghĩa mọi cluster có cùng môi trường runtime. Hãy xác định những phần portable và những phần cần adapter riêng:

| Chủ đề | Phần có thể chia sẻ | Phần cần đánh giá theo nền tảng |
| --- | --- | --- |
| Namespace labels, RBAC cơ bản | Nhiều manifest chuẩn Kubernetes | Identity provider và nhóm người dùng |
| Pod security | Ý định chặn quyền nguy hiểm | Phiên bản admission, ngoại lệ, pod/system add-ons |
| NetworkPolicy | Ý định phân đoạn | CNI và data plane có hỗ trợ đầy đủ không |
| Storage | PVC và StorageClass references | CSI driver, class name, topology, snapshot |
| Ingress/Gateway | API theo phiên bản được hỗ trợ | Controller, load balancer, TLS và DNS |
| Workload identity | Không dùng key tĩnh, cấp quyền tối thiểu | IAM/OIDC mapping của GCP, AWS, Azure, on-prem |
| Container registry | Pin digest, ký và xác minh image | Quyền pull, region và mạng/private endpoint |

Một cluster tại datacenter có thể không kết nối liên tục đến repository trung tâm. Thiết kế cần quy định khoảng mất kết nối chấp nhận được, cơ chế mirror Git/registry nếu cần, chứng chỉ, proxy và quy trình phân phối bản vá khẩn cấp khi offline. Không mặc định controller sẽ áp chính sách mới trong vài phút nếu đường mạng hoặc quyền truy cập nguồn đã hỏng.

Để quản lý fleet có cluster thuộc cloud khác, phải kiểm tra chính xác điều kiện hỗ trợ attached/registered cluster và các policy products theo phiên bản sử dụng. Một membership hiển thị trên console không bảo đảm admission webhook hoặc đồng bộ manifests đã được cài và hoạt động.

## 19. Quan sát tình trạng đồng bộ và tuân thủ

Một dashboard đa cluster nên hiển thị:

- Danh sách cluster dự kiến và cluster đang nhận cấu hình.
- Revision hoặc commit cấu hình mong muốn và revision đã áp dụng ở từng cluster.
- Thời điểm sync gần nhất, thời gian stale, số lỗi fetch, auth, render, apply và retry.
- Số resource bị drift, cluster có drift kéo dài và nguyên nhân.
- Số constraint vi phạm ở audit mode, số admission denials theo loại policy.
- Tỷ lệ Pod Ready, deployment availability, error rate và latency ở workload chịu thay đổi.
- Trạng thái cert/webhook, admission latency và áp lực lên Kubernetes API server.

Đặt SLO thực tế cho management plane, ví dụ phần lớn cluster production áp dụng revision được phê duyệt trong một khoảng thời gian sau promotion, không có cluster báo lỗi sync kéo dài quá ngưỡng; con số cụ thể phải dựa trên connectivity và tần suất thay đổi.

Nếu GitOps báo Synced nhưng ứng dụng không Ready, đó là sự cố workload hoặc dependency, không nhất thiết là lỗi đồng bộ. Ngược lại, nếu workload còn chạy tốt nhưng cluster bị mất sync nhiều ngày, rủi ro drift và chậm bản vá vẫn cần xử lý.

## 20. Runbook khi cấu hình hoặc policy gây sự cố

**Tình huống:** sau một pull request cập nhật policy, nhiều Deployment tại production bị từ chối khi tạo Pod mới.

Quy trình:

1. Xác định cluster và namespace bị ảnh hưởng; so sánh commit đã áp dụng với commit gần nhất hoạt động tốt.
2. Kiểm tra sync status của RootSync/RepoSync hoặc controller tương đương; tìm lỗi áp dụng manifest.
3. Kiểm tra admission denial từ policy engine, tên constraint và đối tượng bị từ chối.
4. Đánh giá đây là manifest không tuân thủ thật hay policy mới quá nghiêm ngặt/không tương thích.
5. Nếu sự cố do policy mới, revert commit hoặc đổi mức enforcement theo quy trình đã định; ưu tiên sửa đúng constraint gây ảnh hưởng.
6. Quan sát rollout của workload sau khi policy được sửa; xác nhận Pod Ready, error rate và SLO trở lại bình thường.
7. Ghi lại nguyên nhân, phạm vi ảnh hưởng, thông tin người phê duyệt và bổ sung regression test trong CI.

Tránh dùng kubectl apply thủ công để sửa hàng loạt tài nguyên đang do GitOps sở hữu khi chưa có kế hoạch reconciliation. Khi API server hoặc admission webhook gặp lỗi, phải xác định loại failurePolicy và tác động đến bảo mật trước khi thay đổi chế độ fail-open/fail-closed. Một quyết định cho phép mọi resource đi qua chỉ để hết lỗi triển khai có thể tạo lỗ hổng lớn hơn.

## 21. Bài thực hành: duy trì ba cluster với hai mức chính sách

**Bối cảnh:** tổ chức có GKE staging, GKE production và Kubernetes on-premises. Nhóm muốn yêu cầu mọi namespace ứng dụng có nhãn owner, chặn workload đặc quyền ở production và cho nhóm ứng dụng tự quản lý Deployment trong namespace của mình.

Các nhiệm vụ:

1. Lập inventory cluster: nền tảng, phiên bản Kubernetes, cluster context, chủ sở hữu và khả năng áp policy.
2. Thiết kế repository base/overlays/rendered với baseline chung và những ngoại lệ có tài liệu.
3. Tạo Namespace mẫu có owner và environment labels; cấu hình quota và RBAC theo namespace.
4. Cấu hình một RootSync thử nghiệm trên GKE staging với repo chỉ đọc và đường dẫn riêng.
5. Cài đặt/kiểm tra ConstraintTemplate cần thiết, áp constraint yêu cầu owner ở chế độ dry-run.
6. Tạo hai namespace thử nghiệm: một có nhãn owner, một thiếu nhãn; ghi nhận vi phạm trong báo cáo audit.
7. Sau khi xác minh, thử enforcement trên namespace thử nghiệm trước khi xem xét production.
8. Tạo thay đổi thủ công trong một resource được GitOps quản lý và kiểm tra drift/reconciliation.
9. Ngắt quyền đọc repository trong môi trường thử nghiệm, quan sát lỗi sync và khả năng cảnh báo.
10. Trình bày kế hoạch promotion sang GKE production và cluster on-prem, bao gồm đường rollback.

**Kết quả cần nộp:** sơ đồ ownership, cấu trúc repository, hai manifest ví dụ, kết quả kiểm tra policy, tình trạng sync trước/sau thay đổi, ma trận quyền của controller và runbook khôi phục.

Không dùng cluster production thật cho thử nghiệm denial, mất kết nối Git hoặc thao tác phá cấu hình nếu chưa có quy trình phê duyệt và môi trường thử nghiệm an toàn.

## 22. Những lỗi thiết kế thường gặp

| Lỗi | Hậu quả | Cách khắc phục |
| --- | --- | --- |
| Coi đăng ký fleet là đủ để áp chính sách | Một số cluster thực tế không được quản lý | Kiểm tra installation, eligibility, sync và policy status từng cluster |
| Một repository trộn mọi quyền platform/app | Pull request ứng dụng có thể đổi policy cấp cluster | Tách nguồn, CODEOWNERS và controller permissions |
| Áp deny toàn fleet ngay từ đầu | Hỏng rollout hoặc thành phần hệ thống | Audit/dry-run, staging, canary rồi mới enforce |
| Sao chép toàn bộ manifest cho từng cluster | Security fix dễ bị bỏ sót | Base chung, overlay tối thiểu và review drift |
| Cấp cluster-admin cho tất cả GitOps controllers | Tăng phạm vi ảnh hưởng khi repo/credential bị xâm phạm | Quyền tối thiểu theo đối tượng và namespace |
| Để HPA và GitOps cùng ép replicas | Reconciliation lặp hoặc autoscaling lỗi | Xác định field ownership và ignore rules có kiểm soát |
| Đưa plaintext Secret vào Git | Lộ credential qua Git history | Dùng kho bí mật và identity/secret injection phù hợp |
| Chỉ đo trạng thái Git Sync | Bỏ sót vi phạm policy hoặc workload không Ready | Quan sát sync, compliance và runtime health riêng |
| Quên khác biệt CNI/API giữa cluster | Manifest hợp lệ nhưng chính sách không có hiệu lực | Thử compatibility theo từng loại cluster |
| Sửa trực tiếp production nhưng không cập nhật Git | Controller hoàn nguyên thay đổi bất ngờ | Break-glass có audit, expiry và reconciliation rõ |
| Rollback source nhưng không xác minh trạng thái | Cluster có thể chưa nhận revision cũ hoặc đang lỗi | Kiểm tra applied revision và workload health sau rollback |

## 23. Checklist trước khi quản lý Kubernetes xuyên cluster

- Đã lập inventory tất cả cluster và các tính năng quản trị thực sự được hỗ trợ.
- Có nguồn sự thật và người sở hữu rõ cho cluster-scoped, namespace-scoped resources và policy.
- Repo có branch protection, review, quy trình promotion và metadata commit/release.
- Config Sync hoặc GitOps controller chạy đúng cluster, dùng danh tính chỉ có quyền cần thiết.
- RootSync/RepoSync được phân vai hợp lý; không tự cấp quyền cluster-admin cho namespace teams.
- Cấu hình được render, validate và kiểm tra security trước khi đồng bộ.
- Policy được thử ở audit/dry-run và staging trước khi mở rộng enforcement.
- Các quy tắc Pod Security, RBAC, NetworkPolicy, quotas và image trust được đánh giá theo nền tảng.
- GitOps, HPA, operators và secret controllers có field ownership không xung đột.
- Không có secret hoặc credential dài hạn trong Git và image.
- Có cơ chế quan sát revision/sync latency/drift, admission violation và workload health.
- Có cảnh báo cluster mất đồng bộ, policy webhook lỗi hoặc workload suy giảm sau rollout.
- Có cách rollback, break-glass, quay lại Git và diễn tập phục hồi.
- Những ngoại lệ theo cluster có lý do, người phê duyệt và lịch rà soát.
- Đã cân nhắc trạng thái cluster offline, route đến repository, registry và DNS trong môi trường hybrid/multicloud.

Quản lý chính sách và cấu hình Kubernetes xuyên cluster hiệu quả cần kết hợp GitOps với admission control và phân quyền. GKE fleets giúp tổ chức nhóm các cluster được hỗ trợ; Config Sync đưa trạng thái khai báo đến cluster; Policy Controller kiểm tra các quy tắc phù hợp. Tuy nhiên, độ tin cậy thực sự đến từ việc phân định rõ nguồn sự thật, kiểm thử theo vòng, giới hạn quyền, giám sát drift và có phương án khôi phục khi cấu hình sai. Cách tiếp cận này tạo nền tảng nhất quán cho Kubernetes trên Google Cloud, tại trung tâm dữ liệu và trong những môi trường cloud khác mà không che giấu khác biệt kỹ thuật giữa chúng.
