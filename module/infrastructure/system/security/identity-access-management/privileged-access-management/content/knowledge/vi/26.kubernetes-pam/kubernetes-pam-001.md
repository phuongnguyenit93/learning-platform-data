# Cluster-admin role

Một kỹ sư cần xem log của một Pod nhưng được cấp một kubeconfig có quyền quản trị toàn cụm. Một pipeline chỉ triển khai vào một namespace nhưng ServiceAccount của nó lại được gắn với `cluster-admin`. Hai quyết định này giúp công việc ban đầu chạy nhanh, nhưng biến lỗi thao tác hoặc credential bị lộ thành sự cố có thể ảnh hưởng nhiều ứng dụng.

Trong Privileged Access Management (PAM), `cluster-admin` cần được coi là đặc quyền có phạm vi tác động lớn. Quản trị tốt không chỉ là biết ai có một role tên như vậy, mà còn phải xác định họ nhận quyền qua đường nào, được dùng khi nào, có thể tạo thêm quyền gì và làm sao thu hồi sau nhiệm vụ.

Bài học giải thích ý nghĩa của `cluster-admin` trong Kubernetes RBAC và cách quản trị quyền này theo least privilege, JIT/JEA, vòng đời credential và bằng chứng kiểm toán. Những ví dụ manifest và lệnh dưới đây dành cho việc học trên môi trường được phép; tên cluster, namespace và nhóm đều là minh họa.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

- Phân biệt ClusterRole, ClusterRoleBinding, RoleBinding và role có tên `cluster-admin`.
- Đánh giá quyền quản trị thực tế của người dùng, nhóm và ServiceAccount.
- Nhận diện những đường đạt đặc quyền tương đương dù không xuất hiện tên `cluster-admin`.
- Thiết kế quyền theo nhiệm vụ thay cho cấp quyền quản trị toàn cụm.
- Đưa cấp quyền tạm thời, bảo quản credential, audit và thu hồi vào cùng quy trình.
- Kiểm chứng quyền bằng kiểm tra có mục tiêu và yêu cầu thực tế, thay vì chỉ nhìn một manifest.

## 2. Hiểu đúng tên và đối tượng RBAC

`ClusterRole` là một loại đối tượng mô tả quyền. `cluster-admin` là tên một ClusterRole mặc định có quyền rất rộng. Không phải mọi ClusterRole đều là quyền quản trị; một ClusterRole tự định nghĩa có thể chỉ cho phép đọc một vài loại tài nguyên.

RoleBinding hoặc ClusterRoleBinding liên kết tập quyền với subject như User, Group hoặc ServiceAccount. Vì vậy, chỉ có định nghĩa role không cho biết ai được sử dụng role đó.

Theo tài liệu Kubernetes, binding ở cấp cụm tới `cluster-admin` trao khả năng quản trị tài nguyên trên toàn cụm; RoleBinding áp dụng quyền theo phạm vi namespace của binding. RBAC cộng các quyền được cấp và không có rule từ chối để trừ quyền đã nhận. [Tài liệu RBAC Kubernetes](https://kubernetes.io/docs/reference/access-authn-authz/rbac/).

Có thể đọc quan hệ theo hướng:

```text
Credential được xác thực
         |
         v
Username, groups hoặc ServiceAccount
         |
         v
Các binding áp dụng cho subject
         |
         v
Các role được tham chiếu
         |
         v
Quyền RBAC trên tài nguyên và phạm vi cụ thể
```

### 2.1. Tại sao phải kiểm tra binding?

Giả sử hai nhóm cùng tham chiếu một ClusterRole đọc Pod:

- Nhóm A nhận qua RoleBinding ở namespace `billing-prod`.
- Nhóm B nhận qua ClusterRoleBinding.

Định nghĩa quyền giống nhau nhưng phạm vi áp dụng khác nhau. Do đó, câu “nhóm này có một ClusterRole” chưa đủ để kết luận quyền rộng hay hẹp.

RoleBinding không làm tài nguyên cấp cụm trở thành tài nguyên namespace. Khi phân tích quyền trên Node, ClusterRole hoặc đối tượng cấp cụm khác, phải xem đúng đường cấp quyền cho loại tài nguyên đó.

### 2.2. Tên có thể gây hiểu nhầm

Một role tên `support-reader` vẫn có thể chứa quyền rộng. Một role tùy chỉnh không tên `cluster-admin` cũng có thể cấp wildcard đối với nhiều API.

Ngược lại, một principal không xuất hiện trực tiếp trong binding vẫn có thể nhận quyền qua nhóm mà hệ thống xác thực cung cấp.

Cần kiểm tra nội dung, subject, nguồn nhóm và phạm vi. Không phân loại chỉ từ tên role, tên người dùng hoặc nhãn “read-only” trong tài liệu nội bộ.

## 3. Phạm vi tác động của quyền quản trị toàn cụm

Một người có quyền quản trị API rộng có thể tác động nhiều lớp:

| Lớp | Ví dụ tác động cần xem xét |
| --- | --- |
| Workload | Thay image, lệnh chạy, cấu hình Pod hoặc đối tượng tạo Pod |
| Dữ liệu cấu hình | Đọc hoặc sửa Secret, ConfigMap theo quyền hiệu lực |
| Phân quyền | Thay role, binding, ServiceAccount hoặc đường ủy quyền |
| Vận hành cụm | Tác động tài nguyên cấp cụm và nhiều namespace |
| Cơ chế kiểm soát | Thay cấu hình admission hoặc controller nếu có quyền tương ứng |
| Chuỗi cung ứng | Thay các thành phần tự động triển khai và duy trì tài nguyên |
| Bằng chứng | Tác động những thành phần thu thập log nằm trong phạm vi kiểm soát |

Không phải mọi hành động đều chắc chắn thành công trong mọi cụm. Cấu hình admission, quyền ở hệ thống bên ngoài và đặc điểm dịch vụ Kubernetes được quản lý có thể đặt thêm giới hạn.

Điều cần hiểu là một quyền rộng tạo nhiều lựa chọn tác động và nhiều cơ hội tạo quyền tồn dư. Vì vậy, rủi ro không chỉ là “có thể xóa một Deployment”.

### 3.1. Quyền Kubernetes và quyền cloud là hai lớp khác nhau

Quản trị API Kubernetes không tự động có nghĩa sở hữu tài khoản cloud. Ngược lại, một principal cloud có quyền quản lý cụm hoặc ánh xạ truy cập có thể tạo đường vào Kubernetes.

Khi đánh giá một cụm trên cloud, cần xem cả:

- Danh tính và quyền truy cập control plane Kubernetes.
- Cơ chế cloud ánh xạ principal vào cụm.
- Quyền sửa cấu hình cluster hoặc phục hồi đường quản trị.
- Danh tính workload liên kết với hệ thống cloud.
- Quyền đối với node, lưu trữ, backup và khóa mã hóa.

Một nhóm không có ClusterRoleBinding trực tiếp chưa chứng minh họ không thể đạt quyền quản trị nếu còn kiểm soát một đường cấp quyền khác.

### 3.2. Quyền trong container không phải cùng một khái niệm

User `root` bên trong container không phải tên gọi khác của `cluster-admin`.

Rủi ro phụ thuộc cấu hình Pod, mount, danh tính workload, quyền truy cập node và những kiểm soát khác. Một Pod không chạy root vẫn có thể rất nhạy cảm nếu cầm token ServiceAccount quyền cao. Một tài khoản quản trị cụm cũng không nên được đánh giá chỉ bằng user ID của container mà nó tạo.

Phân tích PAM cần nối danh tính API với khả năng thực thi và dữ liệu có thể tiếp cận, thay vì đồng nhất mọi khái niệm “admin”.

## 4. Xác thực, phân quyền và admission

Ba câu hỏi cần được tách rõ:

1. **Xác thực:** request thuộc principal nào?
2. **Phân quyền:** principal đó có được yêu cầu hành động trên tài nguyên tương ứng không?
3. **Admission và kiểm tra liên quan:** nội dung thao tác có đáp ứng các điều kiện áp dụng không?

Trong Kubernetes, admission diễn ra sau khi request đã được cho phép ở bước authorization. Vì vậy, một quyết định authorization cho phép không bảo đảm mọi nội dung thay đổi đều được chấp nhận. [Mô hình authorization Kubernetes](https://kubernetes.io/docs/reference/access-authn-authz/authorization/).

### 4.1. Không dùng admission để hợp thức hóa quyền quá rộng

Một tổ chức có thể có policy chặn một số cấu hình Pod rủi ro. Điều đó không phải lý do để cấp `cluster-admin` cho mọi pipeline.

Cần xem ai có thể sửa policy, binding, controller hoặc cấu hình áp dụng của chính kiểm soát đó. Một biện pháp bảo vệ mà principal được bảo vệ có thể tự vô hiệu hóa có giới hạn rõ ràng.

### 4.2. Một lỗi Forbidden cần được phân tích đúng lớp

Khi người dùng gặp lỗi, hãy xác định:

- Credential có được xác thực không?
- Username và groups thực tế là gì?
- Cluster và namespace đích có đúng không?
- Hành động và subresource nào đang bị kiểm tra?
- Quyền nào còn thiếu cho nhiệm vụ hợp lệ?
- Có policy hoặc cơ chế khác gây từ chối không?

Không phản ứng với mọi lỗi bằng cách thêm `cluster-admin`. Một lỗi đọc log có thể chỉ cần quyền thích hợp cho subresource log; quyền quản trị toàn cụm làm mất cơ hội xác định yêu cầu thật.

## 5. Vì sao PAM phải quản trị cả đường tương đương?

Tìm kiếm binding tham chiếu `cluster-admin` là bước kiểm kê hữu ích, nhưng chưa đủ.

Một principal có thể có khả năng rất mạnh thông qua:

- Role tùy chỉnh chứa nhiều wildcard.
- Khả năng gán hoặc sửa quyền ngoài phạm vi dự kiến.
- Quyền giả danh principal có quyền cao.
- Khả năng tạo workload sử dụng một ServiceAccount nhạy cảm.
- Quyền sửa một controller chạy bằng danh tính quyền cao.
- Quyền ghi vào nguồn cấu hình mà GitOps controller có đặc quyền sẽ áp dụng.
- Quyền cấp credential hoặc điều khiển thành phần xác thực theo một đường khác.

Đây là các đường cần phân tích theo cấu hình thực tế, không phải khẳng định mỗi quyền trong danh sách luôn dẫn tới quản trị toàn cụm.

### 5.1. Quyền quản lý RBAC có cơ chế chống tự nâng quyền, nhưng vẫn nhạy cảm

Kubernetes có các kiểm tra khi tạo hoặc sửa role và binding. Các verb như `escalate` và `bind` liên quan tới việc cho phép vượt những kiểm tra tương ứng. Vì vậy, phải xem cả quyền thao tác đối tượng RBAC lẫn quyền đặc biệt được cấp; không kết luận rằng chỉ cần tạo RoleBinding là luôn có thể tự gắn mọi quyền. [Các giới hạn tạo role và binding](https://kubernetes.io/docs/reference/access-authn-authz/rbac/#privilege-escalation-prevention-and-bootstrapping).

Đối với PAM, quyền ủy quyền là một loại đặc quyền. Khi cấp cho hệ thống tự động, cần xác định nó được gán role nào, cho subject nào, ở phạm vi nào và theo bằng chứng phê duyệt nào.

### 5.2. Nhóm system:masters cần đánh giá riêng

Kubernetes cảnh báo rằng thành viên `system:masters` có thể vượt kiểm tra RBAC; gỡ RoleBinding hoặc ClusterRoleBinding không thu hồi được khả năng đó. Không coi nhóm này chỉ là một nhóm thông thường đang được gắn role rộng. [Thực hành RBAC an toàn](https://kubernetes.io/docs/concepts/security/rbac-good-practices/).

Vì vậy, không đưa người dùng hoặc credential vận hành thông thường vào nhóm này để thuận tiện. Nếu tồn tại trong đường bootstrap hoặc phục hồi, phải bảo vệ credential và hiểu cơ chế chấm dứt khả năng sử dụng của nó.

### 5.3. Controller và GitOps

Nếu controller có quyền rất rộng, người được sửa cấu hình mà controller tin cậy có thể khiến controller thực hiện thay đổi thay mình.

Cần kiểm tra nguồn repository, nhánh được áp dụng, người được sửa manifest, cơ chế review và phạm vi controller. Quyền merge vào một thư mục quản trị có thể quan trọng không kém một binding trực tiếp.

Khi thu hồi một grant, cũng phải kiểm tra nguồn khai báo. Một binding bị xóa bằng tay có thể được controller tạo lại nếu cấu hình mong muốn vẫn chứa nó.

## 6. Kiểm kê quyền hiệu lực

Một danh mục đặc quyền nên nối được từ người hoặc workload tới mọi đường cấp quyền liên quan.

### 6.1. Thông tin cần lưu

| Thành phần | Nội dung cần xác định |
| --- | --- |
| Cluster | Định danh ổn định, môi trường, chủ sở hữu |
| Principal | Người dùng, nhóm, ServiceAccount hoặc danh tính quản trị khác |
| Nguồn xác thực | IdP, credential workload, chứng thư hoặc cơ chế được cấu hình |
| Binding | Tên, loại, namespace nếu có và subject |
| Role | Nội dung quyền và nguồn quản lý cấu hình |
| Mục đích | Nhiệm vụ cần quyền, người chịu trách nhiệm |
| Vòng đời | Thường trực hay tạm thời, cơ chế hết hạn và thu hồi |
| Bằng chứng | Hồ sơ cấp quyền, kiểm tra, audit sử dụng |

Không lưu token, private key hoặc kubeconfig chứa credential vào bảng kiểm kê chỉ để liên kết danh tính.

### 6.2. Một số lệnh đọc phục vụ kiểm tra

Các lệnh sau là ví dụ cho người có quyền kiểm kê trên môi trường học tập `lab-pam`:

```bash
kubectl --context=lab-pam get clusterrole cluster-admin -o yaml
kubectl --context=lab-pam get clusterrolebindings -o yaml
kubectl --context=lab-pam get rolebindings --all-namespaces -o yaml
```

Chúng giúp đọc cấu hình RBAC đang hiện diện. Kết quả vẫn cần được liên kết với nhóm thực tế, role tùy chỉnh, nguồn GitOps và cơ chế xác thực.

Không đưa mọi kết quả kiểm kê vào kênh công khai. Tên nhóm, principal và cấu trúc quyền cũng có thể là thông tin nội bộ nhạy cảm.

### 6.3. Đừng sửa role mặc định để xử lý một grant

Nếu vấn đề là một nhóm đang được cấp quá rộng, cần xem đúng binding hoặc nguồn cấp quyền của nhóm đó. Sửa định nghĩa `cluster-admin` có thể tác động nhiều principal và không phải cách thông thường để giới hạn một người.

Những đối tượng mặc định còn có hành vi quản lý riêng của Kubernetes. Thay đổi cần được đánh giá cùng cấu hình cụm, thay vì coi chúng là một policy nội bộ có thể chỉnh tùy ý.

## 7. Thiết kế quyền theo công việc

Trước khi chọn role, viết nhiệm vụ thành câu cụ thể:

> Người trực cần xem trạng thái Pod và log của ứng dụng billing trong namespace billing-prod để xử lý một incident.

Câu đó không yêu cầu quản lý Node, Secret của ứng dụng khác, admission hoặc RBAC toàn cụm.

Một cách phân tách:

| Nhiệm vụ | Phạm vi quyền để bắt đầu thiết kế |
| --- | --- |
| Quan sát tình trạng ứng dụng | Đọc đối tượng và log cần thiết trong namespace được giao |
| Thay đổi bản triển khai | Sửa những workload được phân công với các ràng buộc triển khai tương ứng |
| Điều chỉnh số replica | Quyền phù hợp với thao tác scale, không mặc định toàn bộ quyền sửa Pod |
| Xử lý mạng ứng dụng | Tài nguyên mạng cần thiết trong phạm vi ứng dụng |
| Quản trị thành phần cụm | Quyền cấp cụm cho nhóm platform theo nhiệm vụ được duyệt |
| Phục hồi cấu hình phân quyền | Đường quản trị nhạy cảm, có kiểm soát và bằng chứng riêng |

Bảng chỉ là điểm xuất phát. Ví dụ, quyền thay workload có thể cho phép lựa chọn image, danh tính hoặc mount; cần đánh giá khả năng tiếp cận dữ liệu và quyền của workload sau thay đổi.

JEA trong bối cảnh này nghĩa là cung cấp chức năng quản trị vừa đủ. Không chỉ giảm số dòng policy mà phải giảm những hành động và phạm vi có thể tác động thực tế.

### 7.1. Ví dụ quyền quan sát trong một namespace

Manifest dưới đây mô tả role riêng cho mục đích học tập, với nhóm `team:billing:observe` đã được hệ thống xác thực ánh xạ đúng:

```yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: billing-observer
  namespace: billing-prod
rules:
  - apiGroups: [""]
    resources: ["pods"]
    verbs: ["get", "list", "watch"]
  - apiGroups: [""]
    resources: ["pods/log"]
    verbs: ["get"]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  name: billing-observer-team
  namespace: billing-prod
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: Role
  name: billing-observer
subjects:
  - apiGroup: rbac.authorization.k8s.io
    kind: Group
    name: team:billing:observe
```

Ví dụ này không cấp thêm quyền đọc Secret, mở shell trong Pod hoặc sửa binding. Điều đó không có nghĩa một subject đã có quyền rộng từ nơi khác sẽ bị giới hạn lại bởi role này.

Log và thông tin Pod vẫn có thể chứa dữ liệu nhạy cảm. Khi cấp quyền đọc, cần phân loại nội dung và giới hạn người nhận phù hợp, không đánh đồng “chỉ đọc” với “không có rủi ro”.

### 7.2. Namespace không thay thế toàn bộ mô hình cách ly

Một namespace là phạm vi quản lý quan trọng, nhưng phải xem các đường tiếp cận qua ServiceAccount, workload, controller, tài nguyên dùng chung và quyền cấp cụm.

Nếu nhiều tenant không tin cậy lẫn nhau, cần đánh giá yêu cầu cách ly rộng hơn. Không dùng một RoleBinding hẹp làm bằng chứng duy nhất rằng mọi dữ liệu và đường thực thi giữa tenant đã được tách.

## 8. Tách quyền của người và workload

### 8.1. Người dùng cần danh tính có thể quy trách nhiệm

Tránh phát một kubeconfig quản trị chung cho toàn đội. Khi nhiều người cùng sử dụng một principal, audit của API khó phân biệt người thực hiện nếu không có cơ chế liên kết bổ sung đáng tin cậy.

Ưu tiên danh tính cá nhân qua cơ chế xác thực được quản trị. PAM cần nối được người yêu cầu, phê duyệt, thời hạn và hoạt động thực tế.

Kubeconfig là cấu hình truy cập có thể chứa hoặc tham chiếu credential. Tên file `read-only.yaml` không chứng minh quyền bên trong; cũng không được coi file đó là tài liệu vô hại có thể gửi tùy ý.

### 8.2. ServiceAccount theo mục đích

Một pipeline triển khai billing không cần dùng danh tính khẩn cấp của quản trị viên cụm. Dùng principal riêng để có thể giới hạn và thu hồi theo công việc.

Kubernetes hỗ trợ token ServiceAccount có thời hạn và cơ chế token được chiếu vào Pod; token dài hạn có rủi ro khi bị lộ. Chọn cơ chế phù hợp với workload thay vì sao chép một token quản trị tồn tại lâu vào CI. [Danh tính ServiceAccount](https://kubernetes.io/docs/concepts/security/service-accounts/).

Credential ngắn hạn không làm một quyền quá rộng trở thành least privilege. Trong thời gian còn hiệu lực, token vẫn có thể thực hiện những hành động được cấp cho principal.

### 8.3. Vai trò của vault

Vault hoặc kho bí mật có thể bảo vệ credential, kiểm soát checkout và hỗ trợ vòng đời. Nhưng cất một credential `cluster-admin` trong vault không tự thu hẹp quyền của nó.

Cần biết ai có thể lấy credential, ai có thể thay policy vault, secret được đưa tới đâu và người nhận có thể tạo credential hoặc binding khác trong phiên hay không. Phải quản trị cả nơi bảo quản lẫn quyền thực thi trên cluster.

## 9. Khi nào thực sự cần cluster-admin?

Có những nhiệm vụ quản trị cụm không thể hoàn thành bằng quyền vận hành namespace. Ví dụ, phục hồi một cấu hình RBAC cấp cụm hoặc xử lý thành phần platform có phạm vi rộng có thể cần quyền quản trị cao.

Quyết định cấp quyền nên trả lời:

1. Hành động cụ thể là gì?
2. Vì sao quyền hiện tại không đủ?
3. Một role chức năng hẹp hơn có đáp ứng được không?
4. Những cluster và tài nguyên nào bị tác động?
5. Ai thực hiện, ai duyệt và thời hạn bao lâu?
6. Cách kiểm tra và kết thúc quyền là gì?

Không cần biến mọi nhiệm vụ thành một role mới nếu chi phí quản trị vượt lợi ích. Nhưng việc chọn quyền rộng phải có căn cứ từ nhiệm vụ và phạm vi tác động, không từ sự tiện lợi của một kubeconfig có sẵn.

### 9.1. Tách công việc hằng ngày khỏi công việc quản trị cụm

Người thuộc đội platform vẫn có thể sử dụng danh tính quyền thấp cho quan sát thường ngày và nâng quyền khi thực hiện nhiệm vụ cụm.

Cách này giảm nguy cơ một lệnh sai ngữ cảnh hoặc một script không được xem xét chạy ngay với toàn bộ đặc quyền. Người quản trị không nên phải giữ mọi terminal ở trạng thái quyền cao để làm việc bình thường.

### 9.2. Công cụ thực hiện tác vụ hẹp

Một tác vụ thường xuyên có thể được cung cấp qua công cụ quản trị hẹp, chẳng hạn yêu cầu điều chỉnh một tham số đã được kiểm tra hoặc khởi động một quy trình phục hồi được định nghĩa.

Khi đó, backend của công cụ vẫn là principal đặc quyền. Cần xác thực người yêu cầu, kiểm tra phạm vi phía server và không cho client truyền manifest hoặc lệnh tùy ý để biến chức năng hẹp thành quyền quản trị tổng quát.

Công cụ cũng cần audit liên kết người yêu cầu với principal thực thi. Chỉ ghi “controller đã sửa tài nguyên” chưa đủ để biết ai đã khởi phát.

## 10. Cấp quyền JIT với vòng đời rõ ràng

Một luồng tham khảo:

```text
Người yêu cầu
     |
     v
Xác minh nhiệm vụ, cluster và phạm vi
     |
     v
Phê duyệt theo mức tác động
     |
     v
Cấp grant hoặc binding phù hợp
     |
     v
Theo dõi sử dụng trong thời hạn
     |
     v
Thu hồi và kiểm tra quyền còn lại
```

Các thông tin cần gắn với một yêu cầu gồm chủ thể nhận quyền, cluster, tập quyền, lý do, hồ sơ thay đổi hoặc sự cố, thời điểm bắt đầu và hết hạn.

Một mã ticket chỉ là tham chiếu. Server hoặc người có thẩm quyền phải xác minh tình trạng và phạm vi phê duyệt, không tin một trường `approved: true` do client gửi.

### 10.1. Binding chuẩn không tự có TTL chỉ vì ghi annotation

Schema ClusterRoleBinding chuẩn có thông tin metadata, roleRef và subjects; một annotation tự đặt về thời hạn không tự tạo cơ chế thu hồi. Muốn quyền hết hạn cần có thành phần thực thi vòng đời và kiểm tra việc thu hồi thực tế. [API ClusterRoleBinding](https://kubernetes.io/docs/reference/kubernetes-api/rbac/cluster-role-binding-v1/).

Ví dụ sau chỉ là **metadata minh họa**, không phải grant hoàn chỉnh:

```yaml
metadata:
  annotations:
    access.example.org/request-id: "INC-example-318"
    access.example.org/expires-at: "2026-01-12T04:00:00Z"
```

Nếu không có controller hoặc cơ chế quản lý tương ứng, thời điểm này chỉ là dữ liệu. Không báo cáo rằng quyền tự hết hạn khi chưa kiểm chứng hành vi đó.

### 10.2. Thành phần cấp quyền cũng là đặc quyền

Một broker được phép cấp quyền cao có thể trở thành điểm ảnh hưởng lớn. Cần bảo vệ danh tính của broker, đầu vào, nguồn phê duyệt và quyền sửa cấu hình.

Không giả định policy RBAC đơn giản có thể giới hạn mọi trường bên trong một binding, chẳng hạn chính xác subject nào được thêm. Nếu thiết kế cần ràng buộc nội dung yêu cầu, phải có lớp thực thi phù hợp và được kiểm tra.

Cần giám sát grant đã hết hạn mà chưa thu hồi, lỗi controller và cấu hình khai báo có thể tạo lại grant. Một job chạy định kỳ không đủ nếu không ai phát hiện khi nó ngừng chạy.

### 10.3. Thời hạn credential và thời hạn quyền khác nhau

Credential xác thực principal và binding cấp quyền cho principal là hai phần khác nhau.

Token còn hạn có thể không còn quyền cũ nếu đường cấp quyền đã được gỡ đúng cách. Ngược lại, một binding còn tồn tại có thể lại trao quyền khi chủ thể có credential mới hoặc quay lại nhóm tương ứng.

Thiết kế JIT cần quản lý cả hai vòng đời, cộng thêm những phiên hoặc credential được tạo trong lúc có quyền cao.

## 11. Kiểm tra quyền bằng can-i và yêu cầu thực tế

`kubectl auth can-i` giúp kiểm tra một hành động theo ngữ cảnh yêu cầu. Tùy chọn giả danh yêu cầu quyền impersonation tương ứng; kiểm tra dưới một tên khác không tự chứng minh chuỗi đăng nhập của người đó hoạt động đúng. [Tham chiếu kubectl auth can-i](https://kubernetes.io/docs/reference/kubectl/generated/kubectl_auth/kubectl_auth_can-i/).

Ví dụ kiểm tra chủ thể hiện tại trên môi trường học tập:

```bash
kubectl --context=lab-pam auth can-i list pods --namespace=billing-prod
kubectl --context=lab-pam auth can-i get pods --subresource=log --namespace=billing-prod
kubectl --context=lab-pam auth can-i get secrets --namespace=billing-prod
kubectl --context=lab-pam auth can-i create clusterrolebindings.rbac.authorization.k8s.io
```

Trong thiết kế observer ở phần trước, hai kiểm tra đầu dự kiến được cho phép; hai kiểm tra sau dự kiến không được cho phép **nếu principal không có quyền bổ sung từ đường khác**.

### 11.1. Kiểm tra từng hành động quan trọng

Không chỉ hỏi một câu quá rộng rồi coi như đã hiểu mọi quyền.

Nên xây dựng danh sách theo nhiệm vụ:

- Có đọc được nguồn cần thiết không?
- Có vượt sang namespace khác không?
- Có đọc được Secret không?
- Có quyền trên subresource nhạy cảm không?
- Có thể sửa role, binding hoặc đối tượng cấp cụm không?
- Có thể tạo hoặc sửa workload dùng danh tính mạnh hơn không?

Kết quả kiểm tra authorization không thay thế việc thử hành vi phù hợp ở môi trường được phép. Một request có thể còn bị admission từ chối; một thao tác nhiều bước có thể cần nhiều API hơn dự kiến.

### 11.2. Kiểm tra cả xác thực

Giả danh subject trong phép thử có thể hữu ích cho quản trị viên, nhưng cần mô tả đúng groups và ngữ cảnh áp dụng.

Một phép thử dùng tên người nhưng thiếu nhóm mà token thật cung cấp có thể cho kết quả khác hoạt động thực tế. Ngược lại, tự đưa thêm một nhóm đặc quyền vào phép thử không chứng minh người đó thực sự thuộc nhóm.

Cần có kiểm tra bằng đường đăng nhập thật cho những trường hợp quan trọng. Không cấp thêm quyền impersonation cho người dùng chỉ để họ tự chạy một bài kiểm tra được viết cho quản trị viên.

### 11.3. Giữ đúng cluster và ngữ cảnh

Chỉ định context trong bài thử giúp giảm nhầm lẫn, nhưng tên context vẫn là cấu hình phía client. Người vận hành cần biết nó trỏ tới đích nào và dùng principal nào.

Không xác minh bằng cách in credential thô. Không sao chép kết quả cấu hình có token hoặc private key vào hồ sơ kiểm thử.

## 12. Thu hồi quyền: phải xét những gì?

Một phiên có quyền cao có thể tạo những thứ tồn tại sau khi binding ban đầu bị gỡ.

### 12.1. Quyền cấp trực tiếp và quyền gián tiếp

Khi kết thúc nhiệm vụ:

- Gỡ hoặc kết thúc grant tạm thời đúng nguồn quản lý.
- Đối chiếu các binding khác của principal và nhóm.
- Kiểm tra thay đổi role hoặc nhóm liên quan.
- Xem xét principal, credential và đường ủy quyền mới được tạo.
- Kiểm tra cấu hình GitOps không khôi phục grant ngoài ý muốn.
- Thử lại các hành động quan trọng theo danh tính và ngữ cảnh phù hợp.

Một role quyền thấp mới không trừ quyền từ role cao còn tồn tại. Nếu một người vẫn thuộc nhóm đặc quyền, xóa binding mang tên cá nhân của họ có thể chưa có tác dụng mong muốn.

### 12.2. Credential và phiên đang tồn tại

Các cơ chế xác thực có hành vi hết hạn và thu hồi khác nhau. Vô hiệu hóa tài khoản ở IdP không nên được coi là bằng chứng rằng mọi credential đã cấp đều không thể dùng ngay.

Cần biết credential nào đang được dùng, nơi nào xác minh, thời hạn và các bước xử lý khi lộ. Với private key hoặc credential có khả năng truy cập đặc biệt, phải có kế hoạch ứng phó theo cơ chế cụm thực tế.

Không mặc định Kubernetes có một đối tượng User để xóa là giải quyết mọi cơ chế xác thực.

### 12.3. Kết nối và công việc đã bắt đầu

Một request authorization mới bị từ chối không chứng minh mọi kết nối đang mở hoặc tác vụ đã tạo đều bị dừng.

Cần xét phiên tương tác, luồng theo dõi, tiến trình trong workload và job được khởi phát trong thời gian có quyền. Việc chấm dứt những hoạt động này phải được thiết kế và xác minh theo cơ chế thực tế, không suy ra chỉ từ việc gỡ binding.

### 12.4. Tồn dư trên cluster và hệ thống bên ngoài

Quyền cao có thể tạo bản sao Secret, thay image, thay controller hoặc cấp credential cho hệ thống khác. Thu hồi quyền Kubernetes không kéo lại một secret đã được đọc hay tự hoàn nguyên một thay đổi đã thực hiện.

Nếu nghi bị lạm dụng, xử lý cả dữ liệu, workload, danh tính liên quan và bằng chứng. Không kết thúc điều tra chỉ vì principal ban đầu không còn `cluster-admin`.

## 13. Audit và bằng chứng sử dụng

Một chuỗi bằng chứng cần nối được:

```text
Người / workload yêu cầu
  → phê duyệt và grant
  → danh tính API
  → thao tác trên đối tượng
  → kết quả
  → thu hồi và hậu kiểm
```

Audit Kubernetes có các mức ghi khác nhau; metadata của request khác với việc ghi cả request hoặc response body. Cần chọn phạm vi phù hợp, nhất là khi thao tác có thể chứa Secret hoặc dữ liệu nhạy cảm. [Audit Kubernetes](https://kubernetes.io/docs/tasks/debug/debug-cluster/audit/).

### 13.1. Những hoạt động nên chú ý

Các tín hiệu quan trọng có thể gồm:

- Tạo hoặc sửa binding tới quyền quản trị rộng.
- Sửa nội dung role quyền cao.
- Cấp quyền cho nhóm hoặc ServiceAccount ngoài mục đích.
- Tạo credential hoặc principal trong một phiên quản trị.
- Sử dụng impersonation ngoài quy trình được duyệt.
- Đọc dữ liệu nhạy cảm hoặc tác động nhiều namespace bất thường.
- Sửa controller, admission hoặc thành phần thu thập bằng chứng.
- Sử dụng credential phục hồi ngoài một sự cố đã xác nhận.

Tín hiệu cần được đối chiếu với công việc hợp lệ. Một quản trị viên xử lý sự cố có thể thực hiện nhiều thao tác; nhiệm vụ là xác minh phạm vi và trách nhiệm, không chỉ đếm số request.

### 13.2. Bảo vệ bằng chứng

Một collector chạy trong cluster có thể chịu tác động từ người quản trị cluster. Cần đánh giá đường đưa audit ra nơi lưu, quyền tại đích và khả năng thay đổi cấu hình thu thập.

Tách miền quản trị hoặc nơi bảo quản bằng chứng có thể giúp giảm khả năng một principal che giấu toàn bộ hoạt động. Mức tách biệt cần xét cả quyền cloud, kho lưu, khóa mã hóa và tài khoản cấp cao.

Không mô tả audit API là bản ghi đầy đủ của mọi lệnh chạy bên trong container. Muốn quan sát hoạt động thực thi cần các lớp phù hợp với mục tiêu, đồng thời kiểm soát dữ liệu nhạy cảm có thể xuất hiện trong bản ghi.

### 13.3. Liên kết với PAM

Hồ sơ PAM nên ghi cluster, principal nhận quyền, role hoặc grant, người duyệt, thời hạn và bằng chứng thu hồi.

Nếu broker thực hiện thay đổi bằng ServiceAccount của nó, cần lưu liên kết tới người khởi phát. Audit chỉ thấy danh tính broker mà không có bằng chứng liên kết sẽ làm giảm khả năng quy trách nhiệm.

## 14. Quyền phục hồi và break-glass

Đường phục hồi có thể cần quyền quản trị cao khi chính RBAC hoặc cổng truy cập bình thường gặp sự cố.

Thiết kế cần trả lời:

- Tình huống nào được kích hoạt?
- Danh tính và credential nằm ở đâu?
- Có phụ thuộc vào hệ thống đang hỏng không?
- Ai nhận quyền và ai giám sát?
- Thao tác phục hồi nào được phép?
- Làm sao ghi bằng chứng và khôi phục trạng thái bảo quản?

Không dùng credential phục hồi cho triển khai hằng ngày. Nếu một credential có khả năng đặc biệt, chẳng hạn đi qua đường không thể thu hồi chỉ bằng binding, phải ghi rõ giới hạn đó trong phương án bảo quản và ứng phó.

Định kỳ kiểm tra khả năng phục hồi bằng kịch bản được phép. Đăng nhập được chưa đủ; cần xác nhận có thể thực hiện nhiệm vụ phục hồi đại diện và có thể kết thúc quyền theo thiết kế.

## 15. Tình huống thực hành: pipeline triển khai có quyền toàn cụm

Một doanh nghiệp có ba namespace: billing, inventory và platform. Pipeline billing dùng ServiceAccount được gắn với `cluster-admin` vì trước đây manifest triển khai từng gặp lỗi Forbidden.

### 15.1. Phân tích yêu cầu thật

Nhiệm vụ của pipeline là cập nhật workload billing theo cấu hình đã review. Cần liệt kê chính xác loại tài nguyên, hành động và namespace mà quy trình sử dụng.

Phân biệt:

- Triển khai ứng dụng thông thường.
- Cài đặt hoặc thay đổi thành phần cấp cụm.
- Tạo danh tính và cấp quyền cho workload.
- Quản trị namespace hoặc chính sách dùng chung.

Nếu một đợt triển khai ứng dụng đồng thời sửa RBAC cấp cụm, cần đánh giá việc tách trách nhiệm. Không giữ quyền toàn cụm cho pipeline chỉ vì một file quản trị từng được đặt chung thư mục.

### 15.2. Thiết kế thay thế

Có thể dùng principal triển khai riêng cho billing, cấp những quyền thực sự cần trong phạm vi tương ứng và kiểm soát nội dung workload.

Các tài nguyên platform được quản trị bởi đường thay đổi riêng. Quyền sửa repository, secret của CI và cấu hình runner cũng phải được xem xét vì chúng ảnh hưởng tới principal triển khai.

Khi thay manifest, kiểm tra khả năng sử dụng ServiceAccount khác, mount dữ liệu và tác động của image. Một role chỉ sửa Deployment vẫn cần được đánh giá theo những gì Deployment đó có thể tạo ra.

### 15.3. Chuyển đổi có kiểm chứng

1. Ghi lại đường quyền và credential hiện tại.
2. Tạo thiết kế quyền mới dựa trên nhiệm vụ đã xác định.
3. Thử triển khai trên môi trường và tài nguyên được phép.
4. Kiểm tra các hành động ngoài phạm vi bị từ chối.
5. Cập nhật cấu hình nguồn để không tái tạo quyền cũ.
6. Thu hồi binding rộng và xử lý credential theo nhu cầu.
7. Theo dõi các lần từ chối, nhiệm vụ thất bại và dấu hiệu quyền còn sót.

Không cần sao chép credential `cluster-admin` sang runner mới để thử role hẹp. Giữ riêng ngữ cảnh kiểm tra và ngữ cảnh quản trị thay đổi để kết quả có ý nghĩa.

## 16. Bộ kiểm tra nghiệm thu

| Tình huống | Điều cần chứng minh |
| --- | --- |
| Observer đọc Pod và log đúng namespace | Hoàn thành nhiệm vụ hợp lệ |
| Observer đọc Secret hoặc mở shell | Không có quyền ngoài thiết kế |
| Người dùng đổi namespace hoặc cluster đích | Không mang quyền vượt sang phạm vi chưa được cấp |
| Subject nhận thêm một binding qua nhóm | Kiểm kê phát hiện quyền cộng thêm |
| Role tùy chỉnh được thêm wildcard | Thay đổi được nhận diện và đánh giá |
| Người quản lý RBAC thử vượt phạm vi ủy quyền | Cơ chế kiểm soát hoạt động đúng |
| Pipeline chọn ServiceAccount nhạy cảm | Ràng buộc thiết kế ngăn hoặc kiểm soát được hành vi |
| Người sửa nguồn GitOps của controller mạnh | Quyền đối với nguồn cấu hình được quản trị tương ứng |
| Grant JIT hết hạn | Cơ chế thu hồi thực sự chạy và có bằng chứng |
| Controller thu hồi gặp lỗi | Có phát hiện, xử lý và giới hạn rủi ro đã biết |
| Binding bị gỡ nhưng nguồn khai báo còn grant | Không để quyền được tạo lại ngoài ý muốn |
| Phiên hoặc tác vụ đã mở trước thu hồi | Được xử lý theo cơ chế kết thúc đã thiết kế |
| Người giữ credential phục hồi dùng ngoài sự cố | Có tín hiệu và quy trình điều tra |
| Người quản trị sửa đường audit | Có kiểm soát và bằng chứng phù hợp |
| Hậu kiểm sau dùng quyền cao | Phát hiện binding, credential hoặc workload tồn dư |

Các phép thử phải phù hợp quyền được giao. Dùng môi trường học tập hoặc tài nguyên thử nghiệm cho những hành động có tác động. Không cần xóa đối tượng thật hay đọc Secret thật để chứng minh thiết kế phân quyền.

## 17. Bài tập tự áp dụng

Bạn nhận một cụm có các tình trạng sau:

- Nhóm hỗ trợ được gắn `cluster-admin` để xem log.
- Pipeline billing dùng chung kubeconfig với quản trị viên.
- Một controller GitOps có quyền cao, nhưng nhiều người được sửa repository của nó.
- Grant tạm thời được ghi annotation hết hạn mà chưa có thành phần thu hồi.
- Đội vận hành chỉ kiểm tra quyền bằng tên người giả định, chưa thử đường đăng nhập thật.

Hãy lập phương án xử lý:

1. Vẽ các đường từ người và workload tới quyền hiệu lực.
2. Chỉ ra nhiệm vụ nào cần quyền namespace và nhiệm vụ nào cần cấp cụm.
3. Tách danh tính, credential và quyền theo mục đích.
4. Thiết kế cấp quyền tạm thời có cơ chế thu hồi kiểm chứng được.
5. Nêu các phép thử tích cực và các yêu cầu phải bị từ chối.
6. Xác định bằng chứng để nối người khởi phát với API thực thi.
7. Chỉ ra những tồn dư cần kiểm tra sau phiên quyền cao.

Một đáp án tốt phải giải thích quyền đến từ đâu và được thực thi ở đâu. Chỉ đổi tên role hoặc cất kubeconfig vào vault chưa giải quyết trọn vẹn bài toán.

## 18. Tiêu chí hoàn thành

Việc quản trị `cluster-admin` đạt mục tiêu khi có thể chứng minh:

- Hiểu role, binding, subject và phạm vi thay vì chỉ tìm tên quyền.
- Kiểm kê cả quyền trực tiếp lẫn nhóm, controller, GitOps và đường quản trị bên ngoài.
- Quyền thường ngày được thiết kế theo nhiệm vụ và dữ liệu cần tiếp cận.
- Người và workload sử dụng danh tính, credential có chủ sở hữu rõ ràng.
- Quyền quản trị cao chỉ được cấp với căn cứ, phạm vi và vòng đời phù hợp.
- JIT có cơ chế thực thi thời hạn, phát hiện lỗi và kiểm chứng thu hồi.
- Audit liên kết được yêu cầu, principal, thao tác, kết quả và việc đóng quyền.
- Đường phục hồi được bảo quản, diễn tập và tách khỏi vận hành thông thường.
- Kiểm tra cuối phiên bao phủ quyền, credential, kết nối và thay đổi tồn dư.

`cluster-admin` là một năng lực quản trị lớn của Kubernetes. Đưa nó vào PAM nghĩa là làm rõ ai có thể sử dụng năng lực đó, vì nhiệm vụ gì, trong phạm vi nào và bằng chứng nào cho thấy quyền đã được kết thúc. Đó là cơ sở để vừa giữ khả năng vận hành cụm, vừa giảm tác động khi con người, workload hoặc credential gặp sự cố.

