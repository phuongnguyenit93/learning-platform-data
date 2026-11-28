# Namespace admin role

## Mục tiêu bài học

Sau bài học này, bạn có thể:

- Phân biệt Role, ClusterRole, RoleBinding và ClusterRoleBinding khi cấp quyền trong namespace.
- Giải thích quyền quản trị namespace và những giới hạn không thể suy ra chỉ từ tên role.
- Nhận diện rủi ro từ quyền sửa workload, đọc Secret, dùng ServiceAccount và phân quyền tiếp.
- Lựa chọn giữa role admin và role phục vụ một nhiệm vụ cụ thể.
- Thiết kế cấp quyền tạm thời, kiểm tra quyền hiệu lực, thu hồi và lưu bằng chứng.

## 1. Namespace admin là một phạm vi quản trị

**Namespace admin role** là tập quyền cho phép một danh tính quản lý tài nguyên trong một namespace. Trong Kubernetes có ClusterRole mặc định tên **admin**, nhưng tổ chức cũng có thể xây dựng role tùy chỉnh cho nhu cầu quản trị riêng.

Cần phân biệt tên gọi nghiệp vụ “quản trị namespace” với một đối tượng RBAC cụ thể. Một role tự đặt tên namespace-admin không tự có quyền nào ngoài các rule được khai báo và những quyền khác mà danh tính đã được cấp.

Ví dụ, đội Payments quản lý workload trong namespace payments-prod. Họ cần triển khai, kiểm tra tình trạng và xử lý sự cố ứng dụng. Điều đó không tự tạo nhu cầu quản trị node, cấp quyền toàn cluster hoặc truy cập namespace của đội khác.

### 1.1. Namespace không phải ranh giới tuyệt đối

Namespace giúp tổ chức và giới hạn phạm vi nhiều tài nguyên API. Nó không tự tạo đầy đủ cách ly mạng, runtime, dữ liệu hoặc danh tính bên ngoài cluster.

Một thiết kế PAM phải đánh giá cả:

- Quyền trực tiếp trên Kubernetes API.
- Khả năng thay đổi workload để dùng quyền hoặc dữ liệu khác.
- Những ServiceAccount có thể được workload sử dụng.
- Credential cloud hoặc dịch vụ ngoài cluster mà workload có thể nhận.
- Các kiểm soát admission, runtime và mạng được áp dụng.

Tên “namespace admin” chỉ mô tả điểm bắt đầu của phân tích quyền; hậu quả có thể vượt quá các thao tác API ban đầu.

### 1.2. Phân biệt phạm vi với mức độ tin cậy

Một người có quyền rộng trong namespace chứa ứng dụng nhạy cảm cần được tin cậy tương ứng với dữ liệu và danh tính ở đó. Không nên đặt thành phần có mức tin cậy rất khác nhau vào cùng namespace rồi dựa riêng vào role nhỏ hơn để khẳng định chúng được cách ly hoàn toàn.

## 2. Bốn đối tượng RBAC cần hiểu

| Đối tượng | Vai trò trong thiết kế |
|---|---|
| Role | Chứa rule quyền trong một namespace |
| ClusterRole | Chứa rule có thể được tái sử dụng hoặc áp dụng ở phạm vi cluster tùy cách binding |
| RoleBinding | Gắn subject với Role cùng namespace hoặc ClusterRole, cho quyền trong namespace của binding |
| ClusterRoleBinding | Gắn subject với ClusterRole ở phạm vi toàn cluster |

**ClusterRole không đồng nghĩa mọi lần sử dụng đều cấp quyền toàn cluster.** Cách binding quyết định phạm vi cấp quyền tương ứng.

Ví dụ, một RoleBinding ở payments-prod tham chiếu ClusterRole admin cấp quyền trong payments-prod. Nếu dùng ClusterRoleBinding cho cùng ClusterRole, phạm vi sẽ rộng hơn nhiều.

RBAC là mô hình cộng dồn quyền, không có rule deny để trừ quyền được cấp bởi binding khác. [Tài liệu Kubernetes về RBAC](https://kubernetes.io/docs/reference/access-authn-authz/rbac/).

### 2.1. Namespace của binding khác namespace của subject

Một ServiceAccount có namespace định danh riêng. Trường namespace trong subject xác định ServiceAccount nào, không phải giới hạn phạm vi quyền của binding.

Vì vậy, một ServiceAccount ở namespace công cụ vận hành có thể được cấp quyền trong payments-prod bằng RoleBinding ở payments-prod. Nếu cấp qua ClusterRoleBinding, việc ServiceAccount thuộc một namespace không làm quyền tự thu hẹp về namespace đó.

Khi duyệt manifest, cần đọc cả loại binding, metadata.namespace, roleRef và subjects.

### 2.2. Một danh tính có thể nhận quyền qua nhiều đường

Các nguồn cần kiểm kê gồm binding trực tiếp, nhóm danh tính, ServiceAccount, quyền quản lý từ nền tảng cluster và các cơ chế authorization khác đang được cấu hình.

Xóa một RoleBinding chỉ loại bỏ một đường cấp. Không chứng minh danh tính đã mất quyền nếu còn binding khác hoặc còn quyền thông qua một nhóm.

## 3. ClusterRole mặc định admin có ý nghĩa gì?

ClusterRole admin được thiết kế để cấp quản trị namespace qua RoleBinding. Theo tài liệu mặc định, nó cho đọc/ghi phần lớn tài nguyên namespaced và quản lý Role, RoleBinding; không bao gồm quyền ghi ResourceQuota hoặc chính Namespace như một quyền quản trị toàn diện. Các role mặc định cũng có thể nhận thêm rule qua aggregation. [Mô tả các user-facing role](https://kubernetes.io/docs/reference/access-authn-authz/rbac/#user-facing-roles).

Không nên học thuộc một danh sách tài nguyên rồi coi nó đúng cho mọi cluster. Cần xem phiên bản Kubernetes, rule thực tế, extension, aggregation và thay đổi do tổ chức áp dụng.

### 3.1. admin khác cluster-admin

Hai tên đều có chữ admin nhưng có mục đích khác nhau. Không dùng cluster-admin để thay cho việc thiết kế phạm vi namespace chỉ vì dễ cấu hình.

Một quyết định cấp quyền phải nêu rõ:

- Loại role và tên role.
- Rule thực tế tại thời điểm phê duyệt.
- Loại binding.
- Namespace và cluster đích.
- Các quyền khác của subject.
- Những kiểm soát ngoài RBAC.

### 3.2. Không có quyền cluster trực tiếp vẫn có thể gây hậu quả lớn

Quyền sửa workload sản xuất có thể thay đổi mã chạy và cách workload dùng dữ liệu. Do đó, “không quản trị node” không có nghĩa “không nguy hiểm”.

PAM cần đánh giá hậu quả trên tài nguyên, không chỉ đánh giá số lượng quyền cluster-scoped.

## 4. Ví dụ cấp admin trong một namespace

Manifest sau minh họa một quyết định cấp quyền rộng cho một nhóm trong namespace đã xác định. Chỉ dùng khi nhóm được phép quản trị phạm vi này và các điều kiện bảo vệ liên quan đã được xem xét.

~~~yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  name: payments-namespace-administrators
  namespace: payments-prod
subjects:
  - kind: Group
    name: team-payments-namespace-admins
    apiGroup: rbac.authorization.k8s.io
roleRef:
  kind: ClusterRole
  name: admin
  apiGroup: rbac.authorization.k8s.io
~~~

Tên nhóm chỉ là ví dụ. Hệ thống xác thực phải thực sự cung cấp định danh nhóm đó; tạo RoleBinding không tạo ra nhóm hoặc thành viên nhóm.

Phân tích manifest:

1. RoleBinding là đối tượng namespaced.
2. payments-prod là nơi quyền được cấp.
3. Subject là nhóm đã được hệ thống xác thực nhận diện.
4. roleRef tham chiếu ClusterRole admin hiện có.
5. Các rule thực tế được lấy từ role, không phải từ tên RoleBinding.

Schema RoleBinding có subjects và roleRef; roleRef không thể được thay sang role khác bằng cập nhật thông thường. Khi cần đổi role tham chiếu, phải có kế hoạch thay binding phù hợp. [API RoleBinding](https://kubernetes.io/docs/reference/kubernetes-api/rbac/role-binding-v1/).

Manifest này không tự có hạn dùng và không thể hiện quy trình phê duyệt. Đó là những trách nhiệm bổ sung của lớp PAM hoặc hệ thống quản lý quyền.

## 5. Khi nào nên dùng role hẹp hơn?

Nếu nhu cầu chỉ là cập nhật một Deployment và xem tình trạng Pod, cấp admin có thể rộng hơn cần thiết.

Một role phục vụ nhiệm vụ cụ thể có thể tách:

- Quyền xem tình trạng.
- Quyền sửa một nhóm workload.
- Quyền đọc log.
- Quyền tương tác vào container.
- Quyền truy cập Secret.
- Quyền phân quyền cho người khác.

### 5.1. Ví dụ role cập nhật một Deployment

~~~yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: payments-api-config-updater
  namespace: payments-prod
rules:
  - apiGroups: ["apps"]
    resources: ["deployments"]
    resourceNames: ["payments-api"]
    verbs: ["get", "patch", "update"]
  - apiGroups: [""]
    resources: ["pods"]
    verbs: ["get", "list", "watch"]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  name: payments-api-change-operators
  namespace: payments-prod
subjects:
  - kind: Group
    name: team-payments-change-operators
    apiGroup: rbac.authorization.k8s.io
roleRef:
  kind: Role
  name: payments-api-config-updater
  apiGroup: rbac.authorization.k8s.io
~~~

Đây là ví dụ do bài học xây dựng để minh họa phạm vi theo resource và tên đối tượng. Không phải chính sách an toàn hoàn chỉnh cho mọi ứng dụng.

Các rule dùng API group, resources, verbs và resourceNames; schema của Role mô tả các thành phần đó. [API Role](https://kubernetes.io/docs/reference/kubernetes-api/rbac/role-v1/).

### 5.2. Quyền sửa Deployment vẫn rất nhạy cảm

Role trên không giới hạn việc sửa vào một trường cấu hình cụ thể. Người có quyền cập nhật Deployment có thể thay đổi nhiều phần của đối tượng mà API và admission cho phép, bao gồm Pod template.

Vì vậy, hạn chế tên Deployment không tương đương chỉ cho đổi một biến cấu hình đã duyệt. Nếu nhiệm vụ chỉ được sửa một số trường, cần một cơ chế kiểm tra phù hợp, chẳng hạn workflow chuyên biệt hoặc admission policy được quản lý độc lập.

Đây là lý do không thể chỉ đếm số resource trong role để đo mức rủi ro.

### 5.3. Không thêm wildcard để chữa mọi lỗi Forbidden

Khi thiếu quyền, cần xác định chính xác resource, subresource, API group và verb của yêu cầu. Sau đó quyết định quyền đó có cần thiết không.

Thêm dấu sao cho toàn bộ resource và verb có thể giải quyết một lỗi trước mắt nhưng mở rộng cả quyền hiện tại lẫn khả năng truy cập tài nguyên được bổ sung về sau.

## 6. Các đường mở rộng đặc quyền cần đánh giá

### 6.1. Quyền tạo hoặc sửa workload

Người sửa workload có thể ảnh hưởng dữ liệu, cấu hình và danh tính được workload sử dụng. Nếu được tạo Pod tùy ý, họ có thể tiếp cận nhiều tài nguyên cùng namespace hoặc quyền của ServiceAccount mà Pod được phép dùng.

Kubernetes cảnh báo namespace không tạo ranh giới tin cậy mạnh giữa các đối tượng khi một principal có thể tạo workload rộng rãi. [RBAC good practices](https://kubernetes.io/docs/concepts/security/rbac-good-practices/).

Hệ quả thiết kế PAM là phải rà soát cả quyền gián tiếp, không chỉ yêu cầu API trực tiếp của người vận hành.

### 6.2. Secret không chỉ bị lộ qua lệnh get

Quyền đọc Secret cần được đánh giá cùng khả năng list, watch và khả năng làm workload sử dụng Secret. Một người không có quyền đọc trực tiếp vẫn có thể tiếp cận giá trị qua workload nếu họ được kiểm soát cách workload dùng bí mật.

Tài liệu Kubernetes nhấn mạnh nguy cơ của quyền tạo Pod dùng Secret. [Good practices for Kubernetes Secrets](https://kubernetes.io/docs/concepts/security/secrets-good-practices/).

Không đưa credential quản trị toàn hệ thống vào namespace mà đội chỉ được phép quản trị ứng dụng hẹp. Nếu họ có thể khiến workload dùng credential đó, ranh giới mong muốn có thể bị phá vỡ.

### 6.3. ServiceAccount mạnh trong cùng namespace

ServiceAccount là danh tính dành cho workload hoặc tự động hóa. Nó có thể có quyền Kubernetes và, trong một số kiến trúc tích hợp, quyền tới hệ thống ngoài cluster. [Tài liệu về ServiceAccount](https://kubernetes.io/docs/concepts/security/service-accounts/).

Khi xét namespace admin, hãy hỏi:

- Namespace có những ServiceAccount nào?
- Từng ServiceAccount được cấp quyền ở đâu?
- Ai có thể chọn hoặc thay danh tính cho workload?
- Có liên kết tới credential hoặc danh tính cloud không?
- Hệ thống nào kiểm soát các quan hệ này?

Đừng để một ServiceAccount mạnh trở thành đường đi vòng mà bản kiểm kê người dùng không nhận ra.

### 6.4. Role và RoleBinding có thể tạo quyền tồn dư

Người đang có admin tạm thời có thể có khả năng cấp lại những quyền họ được phép phân quyền cho một danh tính khác trong namespace.

Kubernetes có kiểm tra chống nâng quyền khi tạo hoặc sửa role và binding, nhưng các kiểm tra đó không đồng nghĩa cấm mọi việc ủy quyền các quyền đã có. Quyền đặc biệt bind và escalate cũng cần được quản lý riêng. [Kiểm soát privilege escalation trong RBAC](https://kubernetes.io/docs/reference/access-authn-authz/rbac/#privilege-escalation-prevention-and-bootstrapping).

Do đó, cấp admin qua JIT rồi chỉ xóa binding ban đầu chưa đủ nếu người dùng đã tạo thêm đường cấp hợp lệ khác.

### 6.5. Controller và tài nguyên mở rộng

Một namespace có thể chứa custom resource mà controller xử lý bằng quyền mạnh. Cần đánh giá tác động của việc tạo hoặc sửa custom resource, không chỉ nhìn tên API có vẻ vô hại.

Ví dụ về câu hỏi thiết kế: controller có chấp nhận một tham chiếu tài nguyên ngoài namespace không? Ai được sửa template hoặc đích triển khai? Những điều kiện nào được kiểm tra ở backend?

Không mặc định mọi controller đều có lỗ hổng. Mục tiêu là nhận diện nơi quyền của namespace admin có thể tác động tới một thành phần được ủy quyền rộng hơn.

## 7. RBAC cần phối hợp với admission và kiểm soát nền tảng

RBAC chủ yếu quyết định principal có được thực hiện verb trên resource trong phạm vi hay không. Nó không thay thế mọi kiểm tra về nội dung một Pod hoặc hậu quả của cấu hình.

### 7.1. Pod Security Admission

Pod Security Admission có các chế độ enforce, audit và warn. Enforce có thể từ chối Pod vi phạm; audit và warn không tự ngăn Pod đó chỉ vì có cảnh báo hoặc ghi chú audit. [Tài liệu Pod Security Admission](https://kubernetes.io/docs/concepts/security/pod-security-admission/).

Cần xác định chính sách và ngoại lệ thực tế. Không gọi một namespace là đã được bảo vệ chỉ vì có nhãn cảnh báo.

### 7.2. Bảo vệ cấu hình của chính hàng rào

Nếu người cần bị giới hạn có thể thay đổi cấu hình admission, ngoại lệ hoặc controller bảo vệ, hàng rào có thể không đáp ứng mục tiêu.

Cần phân tách người vận hành ứng dụng với người quản lý các kiểm soát nền tảng phù hợp mức rủi ro. Kiểm tra quyền sửa Namespace từ tất cả nguồn, không chỉ từ một RoleBinding.

### 7.3. Mạng, tài nguyên và runtime là các lớp khác

Kiểm soát lưu lượng, giới hạn tài nguyên, lưu trữ và cách ly runtime giải quyết các nhóm rủi ro khác nhau. Chúng không làm một credential đặc quyền bị lộ tự mất tác dụng.

Khi đánh giá namespace admin, nên ghi rõ lớp nào đang thực thi từng giới hạn và ai có thể thay đổi nó. Điều đó hữu ích hơn một câu mô tả chung như “namespace đã được cách ly”.

## 8. Kiểm tra quyền hiệu lực trước và sau khi cấp

Các lệnh dưới đây là ví dụ kiểm tra trong môi trường được phép. Không thực hiện thay đổi cluster chỉ để minh họa bài học.

### 8.1. Kiểm tra bằng danh tính thực

~~~sh
kubectl --context=training-cluster auth can-i patch deployments.apps/payments-api -n payments-prod
kubectl --context=training-cluster auth can-i list secrets -n payments-prod
kubectl --context=training-cluster auth can-i get nodes
kubectl --context=training-cluster auth can-i list pods -n another-team
~~~

Thay context và namespace bằng đích kiểm thử đã được phê duyệt. Kết quả phụ thuộc toàn bộ quyền hiện có, không chỉ các manifest trong bài.

Với role hẹp ở phần 5, mong muốn là chỉ cho phép tác vụ đã thiết kế. Nếu kiểm tra quyền rộng vẫn trả về yes, cần tìm nguồn cấp thêm.

### 8.2. Kiểm tra subresource và giới hạn công cụ

Có thể kiểm tra subresource khi phiên bản công cụ hỗ trợ cú pháp tương ứng:

~~~sh
kubectl --context=training-cluster auth can-i get pods --subresource=log -n payments-prod
kubectl --context=training-cluster auth can-i create pods --subresource=exec -n payments-prod
~~~

Một phép kiểm tra chỉ đánh giá yêu cầu được mô tả, không chứng minh mọi luồng client đều dùng cùng verb. Cần đối chiếu yêu cầu thực tế nếu đang chẩn đoán một thao tác cụ thể.

kubectl auth can-i hỗ trợ kiểm tra quyền và các tùy chọn impersonation. Dùng impersonation cần thẩm quyền tương ứng; phải cung cấp đúng danh tính và nhóm khi muốn mô phỏng ngữ cảnh. [Tham chiếu kubectl auth can-i](https://kubernetes.io/docs/reference/kubectl/generated/kubectl_auth/kubectl_auth_can-i/).

Không cấp quyền impersonate rộng cho cả đội chỉ để tiện kiểm tra.

### 8.3. Kết quả yes chưa chứng minh thao tác sẽ hoàn tất

Authorization được phép chưa bảo đảm đối tượng tồn tại, đầu vào hợp lệ, admission chấp nhận, quota đủ hoặc controller thực hiện thành công.

Nên tách bằng chứng thành:

- Được phép gọi API.
- API chấp nhận thay đổi theo các kiểm tra liên quan.
- Hệ thống đạt trạng thái nghiệp vụ mong muốn.

Không dùng can-i làm bằng chứng duy nhất cho cả ba.

## 9. Thiết kế JIT cho namespace admin

### 9.1. RoleBinding không tự có đồng hồ hết hạn

RoleBinding tiêu chuẩn không cung cấp trường thời hạn để tự thu hồi theo lịch nghiệp vụ. Nếu tổ chức gắn annotation như expires-at, annotation chỉ có ý nghĩa vận hành khi có thành phần đáng tin cậy thực thi nó.

Không nhầm thời hạn token với thời hạn quyền. Token còn hiệu lực có thể nhận quyền khác; token hết hạn có thể được làm mới nếu đường cấp vẫn mở.

### 9.2. Chọn mô hình phù hợp nhiệm vụ

Có thể thiết kế:

- Cấp role tác vụ hẹp trong cửa sổ thay đổi.
- Kích hoạt nhóm hoặc khả năng truy cập tạm thời qua hệ thống danh tính.
- Tạo binding riêng cho một yêu cầu bằng controller quản lý quyền.
- Cấp quyền qua broker với danh tính và giới hạn được kiểm tra.

Đây là các lựa chọn kiến trúc, không phải tính năng JIT mặc định của RBAC. Mỗi mô hình phải chứng minh được khi nào cấp, gia hạn và thu hồi có hiệu lực.

### 9.3. Bảo vệ người cấp quyền

Controller cấp quyền là tài sản đặc quyền. Cần giới hạn cluster, namespace, role đích và khả năng thay đổi cấu hình của nó.

Nếu người nhận quyền có thể sửa yêu cầu, đổi thời hạn hoặc vô hiệu hóa cleanup, một nhãn “temporary” không còn giá trị kiểm soát.

### 9.4. Quyền tạm thời cần điểm kết thúc thực tế

Runbook phải xác định:

1. Điều kiện ngăn cấp hoặc gia hạn mới.
2. Cách xử lý binding hoặc nhóm cấp quyền.
3. Cách kiểm tra API request mới.
4. Các phiên tương tác cần xử lý.
5. Credential, workload và quyền được tạo trong cửa sổ.
6. Những ngoại lệ còn cần theo dõi.

Nếu cấp role admin, phải có phương án đối soát những binding hoặc đường truy cập phát sinh. Với tác vụ không cần phân quyền, role không có khả năng quản lý RBAC thường dễ kiểm soát hơn.

## 10. Quy trình tham chiếu cho một lần cấp quyền

### Bước 1: Chốt danh tính và đích

Ghi danh tính cá nhân, cluster ID hoặc định danh đích ổn định, namespace và môi trường. Không dùng riêng tên context cục bộ làm định danh hệ thống kiểm toán.

### Bước 2: Xác định nhu cầu

Lập danh sách hành động và tài nguyên. Kiểm tra có thực sự cần admin hay role nhỏ hơn đã đủ.

Đối với sửa workload, đánh giá cả Secret, ServiceAccount, volume và các tích hợp mà workload có thể sử dụng.

### Bước 3: Phê duyệt

Người duyệt đánh giá phạm vi và thời hạn. Công việc hậu quả cao có thể cần kế hoạch thay đổi riêng, không chỉ phê duyệt quyền truy cập.

### Bước 4: Ghi trạng thái ban đầu

Lưu metadata của role, binding, membership liên quan và kết quả kiểm tra quyền. Không xuất nội dung Secret hoặc credential để làm bằng chứng.

### Bước 5: Cấp và xác minh

Tạo thay đổi theo hệ thống quản lý được phép. Kiểm tra tác vụ cần thiết được cho phép, tác vụ ngoài phạm vi vẫn bị từ chối và đúng danh tính đang dùng quyền.

### Bước 6: Theo dõi

Quan sát hành động nhạy cảm, thay đổi RBAC, credential và workload. Khi phạm vi công việc thay đổi, đánh giá lại thay vì tự mở rộng quyền.

### Bước 7: Thu hồi và đối soát

Thu hồi đúng nguồn cấp, kiểm tra quyền từ ngữ cảnh thực tế, so sánh thay đổi với kế hoạch và xử lý truy cập tồn dư.

### Bước 8: Đóng hồ sơ

Chỉ kết luận hoàn tất khi quyền và hậu quả liên quan đã có trạng thái rõ ràng. Nếu còn phần chưa xác minh, ghi owner và hạn xử lý.

## 11. Thu hồi không chỉ là xóa một binding

### 11.1. Kiểm tra mọi nguồn cấp còn lại

Danh tính có thể tiếp tục có quyền qua nhóm hoặc binding khác. Vì RBAC cộng dồn, một role hẹp mới không làm mất quyền rộng cũ.

Cần kiểm tra bằng chính ngữ cảnh danh tính dự kiến sử dụng. Nếu nhóm nằm trong credential đã phát hành, thay membership ở nguồn danh tính có thể không lập tức đổi nội dung credential cũ; cách xử lý phụ thuộc cơ chế xác thực.

### 11.2. Phiên đang chạy và request mới khác nhau

Xóa đường cấp quyền nhằm ảnh hưởng quyết định cho yêu cầu tiếp theo theo cơ chế authorization. Không mặc định việc đó ngắt ngay mọi kết nối exec, port-forward, watch hoặc tác vụ đã được khởi tạo.

Runbook cần kiểm tra các phiên đang hoạt động và có biện pháp xử lý tương ứng nếu mức rủi ro yêu cầu. Không dùng một kết quả can-i là no để kết luận mọi kênh tương tác đã đóng.

### 11.3. Quyền và dữ liệu phát sinh cần được xử lý riêng

Những thứ có thể tồn tại sau cửa sổ gồm:

- RoleBinding hoặc thay đổi subjects khác.
- Credential đã được cấp hoặc sao chép.
- Workload mới, Job hoặc thay đổi Pod template.
- Dữ liệu đã đọc hoặc bản xuất đã tạo.
- Thay đổi ở hệ thống bên ngoài do workload thực hiện.

Không tự xóa toàn bộ namespace để thu hồi người dùng. Phải đối soát đúng đối tượng và hậu quả theo kế hoạch.

### 11.4. Chống việc công cụ quản lý tạo lại quyền

Nếu GitOps hoặc automation vẫn khai báo binding, xóa thủ công có thể chỉ là tạm thời. Nguồn trạng thái mong muốn và quy trình thu hồi phải thống nhất.

Tương tự, cleanup phải xác định đúng binding do yêu cầu sở hữu. Một đối tượng đã bị xóa rồi tạo lại không nên bị xử lý mù quáng chỉ vì trùng tên; cần kiểm tra metadata và điều kiện phù hợp với thiết kế.

## 12. Tình huống: admin tạm thời nhưng quyền vẫn còn

Đội Payments được cấp admin trong payments-prod để xử lý sự cố. Trong thời gian đó, một thành viên tạo thêm RoleBinding cho tài khoản tự động hóa nhằm tiếp tục công việc.

Hệ thống JIT xóa binding ban đầu khi hết hạn và báo thành công. Tài khoản tự động hóa vẫn được cấp quyền qua binding mới.

### 12.1. Vì sao kiểm soát ban đầu chưa đủ?

Hệ thống chỉ theo dõi đường cấp đầu tiên. Nó không tính tới khả năng namespace admin phân quyền tiếp trong phạm vi được phép.

Một cơ chế chống nâng quyền không tự cấm cấp lại những quyền mà người tạo đã có. Đây là vấn đề về phạm vi ủy quyền và quản lý vòng đời.

### 12.2. Thiết kế lại

Có thể kết hợp:

1. Dùng role tác vụ không quản lý RBAC nếu sự cố không cần phân quyền.
2. Kiểm soát thay đổi binding bằng workflow và admission phù hợp.
3. Bảo vệ chính sách để người nhận quyền không tự sửa được.
4. Liên kết mọi thay đổi quyền trong cửa sổ với yêu cầu.
5. Đối soát quyền cuối cùng, không chỉ sự tồn tại của binding đầu tiên.
6. Kiểm tra automation hoặc GitOps không tạo lại quyền đã thu hồi.

Không coi quét tên annotation là đủ nếu người có quyền có thể tạo đối tượng khác mà không mang annotation đó.

### 12.3. Báo cáo phù hợp

> Binding JIT ban đầu đã được thu hồi. Phát hiện một binding mới được tạo trong cửa sổ thay đổi. Hồ sơ chưa đóng cho tới khi xác minh mục đích, xử lý quyền của tài khoản tự động hóa và kiểm tra các đường cấp còn lại.

Báo cáo phản ánh quyền thực tế thay vì chỉ phản ánh một thao tác cleanup thành công.

## 13. Audit và bảo vệ bằng chứng

Kubernetes audit có thể ghi metadata của yêu cầu hoặc thêm body tùy policy. Metadata gồm các thông tin như người gọi, thời điểm, resource và verb; ghi body có thể làm lộ dữ liệu nhạy cảm. [Tài liệu Kubernetes Auditing](https://kubernetes.io/docs/tasks/debug/debug-cluster/audit/).

### 13.1. Các hành động đáng chú ý

Theo mức rủi ro, cần quan sát:

- Tạo, sửa hoặc xóa Role và RoleBinding.
- Thay đổi subjects hoặc nguồn membership.
- Tạo và sửa workload nhạy cảm.
- Truy cập Secret hoặc tạo credential.
- Exec, phiên tương tác và hoạt động liên quan.
- Thay đổi admission hoặc cơ chế bảo vệ.
- Các lần bị từ chối ngoài phạm vi dự kiến.

Audit API không tự là bản ghi nội dung mọi lệnh chạy bên trong container. Nếu cần bằng chứng phiên tương tác, phải có cơ chế phù hợp và kiểm tra giới hạn.

### 13.2. Liên kết bằng chứng

| Thông tin | Mục đích |
|---|---|
| Người và nguồn danh tính | Quy trách nhiệm cho cá nhân |
| Cluster và namespace | Xác định đích thực tế |
| Role và phiên bản rule | Hiểu quyền đã cấp |
| Binding hoặc nguồn nhóm | Xác định đường cấp |
| Yêu cầu, phê duyệt và thời hạn | Chứng minh mục đích hợp lệ |
| Hành động và kết quả | Đối chiếu thực thi |
| Kiểm tra sau thu hồi | Chứng minh quyền cuối cùng |
| Ngoại lệ và owner | Tránh bỏ quên phần còn mở |

### 13.3. Không biến audit thành nguồn lộ bí mật

Tránh đưa Secret, token, khóa riêng hoặc kubeconfig chứa credential vào ticket và log thông thường. Nếu cần lưu manifest để đối soát, phải đánh giá trường nhạy cảm và quyền truy cập bản lưu.

Bảo vệ audit ở nơi namespace admin không thể tự xóa hoặc sửa mọi bằng chứng về mình. Đồng thời kiểm tra ai có quyền đổi cấu hình và thời hạn lưu của nơi nhận.

## 14. Ma trận kiểm thử

| Mục tiêu | Kiểm tra cần thiết |
|---|---|
| Đúng namespace | Tác vụ ở namespace đích được phép, namespace khác không được phép ngoài chính sách |
| Không có quyền cluster ngoài nhu cầu | Kiểm tra node, cluster-scoped RBAC và các nguồn cấp bổ sung |
| Đúng tác vụ | Phân biệt resource, subresource, verb và tên đối tượng |
| Không có đường dùng danh tính mạnh ngoài dự kiến | Rà soát workload, ServiceAccount và tích hợp |
| Có hạn thực tế | Hết cửa sổ thì request mới không còn quyền đặc biệt theo thiết kế |
| Không có quyền tồn dư | Đối soát binding, nhóm, credential và thay đổi được tạo |
| Hàng rào còn hiệu lực | Kiểm tra admission và quyền thay đổi chính sách |
| Bằng chứng đầy đủ | Liên kết yêu cầu với hành động và kết quả thu hồi |

Cần có kiểm tra từ chối, không chỉ kiểm tra công việc được phép. Các ca gây hậu quả nên được thử bằng tài nguyên và dữ liệu mô phỏng trong môi trường phù hợp.

## 15. Những lỗi thường gặp

| Lỗi | Hệ quả | Cách cải thiện |
|---|---|---|
| Nghĩ ClusterRole luôn cấp toàn cluster | Chọn sai hoặc hiểu sai binding | Đọc cả loại binding và namespace |
| Nghĩ namespace của ServiceAccount giới hạn mọi quyền | Bỏ sót quyền qua ClusterRoleBinding | Kiểm tra phạm vi cấp thực tế |
| Dùng admin cho mọi sự cố | Có thêm quyền sửa workload và phân quyền | Thiết kế role tác vụ |
| Cho rằng không đọc Secret là không thể lấy bí mật | Bỏ sót đường qua workload | Đánh giá quyền gián tiếp |
| Đặt ServiceAccount mạnh cùng namespace với người không đủ tin cậy | Có thể mở đường tới đặc quyền cao hơn | Phân tách và kiểm soát cách dùng danh tính |
| Cấp role hẹp rồi quên binding rộng cũ | Quyền rộng vẫn còn do cộng dồn | Kiểm kê mọi nguồn cấp |
| Gắn annotation hết hạn nhưng không có cơ chế thực thi | Quyền không tự thu hồi | Dùng vòng đời được quản lý và kiểm thử |
| Chỉ xóa binding JIT ban đầu | Bỏ sót quyền được tạo trong cửa sổ | Đối soát thay đổi và quyền cuối cùng |
| Nghĩ can-i kiểm tra mọi admission | Kết luận sai khả năng hoàn tất | Tách authorization và kết quả hệ thống |
| Nghĩ xóa binding sẽ ngắt mọi phiên | Có thể còn kênh tương tác | Kiểm tra và xử lý phiên riêng |
| Chỉ có warn hoặc audit cho Pod policy | Vi phạm có thể vẫn được chấp nhận | Xác minh chế độ thực thi phù hợp |
| Log toàn bộ Secret để làm bằng chứng | Tạo thêm nguồn lộ | Lưu metadata và dữ liệu đã được xử lý phù hợp |

## 16. Thực hành

### Bài tập 1: Đọc phạm vi binding

Một RoleBinding ở payments-prod tham chiếu ClusterRole admin và gắn cho ServiceAccount thuộc ops-tools.

Hãy chỉ ra namespace của đối tượng được cấp quyền và namespace định danh của ServiceAccount. Giải thích điều gì thay đổi nếu dùng ClusterRoleBinding.

### Bài tập 2: Thay admin bằng role tác vụ

Một người chỉ cần xem Pod và cập nhật Deployment payments-api trong một cửa sổ bảo trì.

Hãy thiết kế role hẹp, liệt kê quyền cố ý không cấp và phân tích phần rủi ro vẫn còn vì có thể sửa Pod template. Nêu cơ chế bổ sung nếu chỉ cho phép sửa một trường cụ thể.

### Bài tập 3: Phân tích quyền tồn dư

Trong cửa sổ JIT, người dùng tạo thêm binding cho một ServiceAccount. Cleanup chỉ xóa binding ban đầu.

Hãy xác định bằng chứng cần xem, điều kiện xử lý binding mới và cách tránh automation tạo lại quyền. Không dùng xóa namespace làm giải pháp mặc định.

### Bài tập 4: Kiểm tra thu hồi

Sau khi hết quyền, can-i trả về no nhưng một phiên exec mở trước đó vẫn cần được đánh giá.

Hãy phân biệt quyền gọi API mới với kênh tương tác đã mở. Viết runbook xác minh và báo cáo phần chưa thể chứng minh.

### Bài tập 5: Đánh giá ranh giới tin cậy

Một namespace chứa cả ứng dụng thông thường và workload có quyền rộng tới hệ thống ngoài cluster.

Hãy đánh giá hậu quả khi đội ứng dụng được cấp admin namespace. Đề xuất cách phân tách workload, danh tính và quyền quản lý để ranh giới phù hợp hơn với mức tin cậy.

## 17. Điểm cần ghi nhớ

Namespace admin giới hạn một phạm vi quản trị API, nhưng vẫn là đặc quyền mạnh đối với workload, dữ liệu và danh tính trong phạm vi đó. Quyền gián tiếp và quyền được phân phối tiếp phải nằm trong bản kiểm kê PAM.

Một thiết kế tốt chọn đúng loại binding, dùng role tác vụ khi đủ, bảo vệ admission và kiểm soát vòng đời quyền. Hoàn tất thu hồi cần bằng chứng về quyền hiệu lực cuối cùng và những đường truy cập phát sinh, không chỉ một thông báo đã xóa binding.
