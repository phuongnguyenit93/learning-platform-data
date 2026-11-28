# Audit Kubernetes privileged verb

## Mục tiêu bài học

Sau bài học này, bạn có thể:

- Nhận diện thao tác Kubernetes cần audit theo verb, resource, subresource và phạm vi.
- Phân biệt verb của yêu cầu API với những quyền đặc biệt như bind, escalate và impersonate.
- Chọn mức audit phù hợp để có bằng chứng mà không làm lộ Secret hoặc token.
- Liên kết sự kiện Kubernetes với danh tính, yêu cầu PAM, cửa sổ JIT và thay đổi quyền.
- Thiết kế cảnh báo, kiểm thử và đối soát kết quả có tính đến giới hạn của audit.

## 1. Audit privileged verb nhằm trả lời điều gì?

Trong Kubernetes PAM, **audit privileged verb** là giám sát và lưu bằng chứng về những thao tác API có thể làm thay đổi đặc quyền, tiếp cận tài sản nhạy cảm hoặc ảnh hưởng lớn đến hệ thống.

Mục tiêu không chỉ là tìm lệnh đáng ngờ. Cần trả lời được:

1. Ai xác thực tới API server?
2. Yêu cầu được thực hiện dưới danh tính nào?
3. Hành động tác động vào cluster, namespace và tài nguyên nào?
4. Có thuộc một yêu cầu được phê duyệt không?
5. API đã nhận, từ chối hay chấp nhận yêu cầu?
6. Quyền hoặc trạng thái cuối cùng thay đổi ra sao?
7. Còn đường truy cập nào phát sinh sau thao tác không?

Một bản ghi “có người chạy kubectl” không đủ. Người dùng có thể gửi cùng yêu cầu qua client khác, automation hoặc giao diện quản trị.

### 1.1. Không có một danh sách verb đủ cho mọi rủi ro

Một verb chỉ có ý nghĩa khi kết hợp với tài nguyên và ngữ cảnh:

- get trên một cấu hình công khai khác với get trên Secret.
- create một đối tượng theo dõi khác với create trên serviceaccounts/token.
- patch một nhãn thông thường khác với patch chính sách phân quyền.
- delete một tài nguyên thử nghiệm khác với xóa thành phần bảo vệ sản xuất.

Vì vậy, mô hình phát hiện nên dựa trên một bộ thông tin:

~~~text
Danh tính + verb + API group + resource + subresource
+ cluster + namespace + đối tượng + kết quả + ngữ cảnh cấp quyền
~~~

### 1.2. Audit không thay authorization hoặc admission

Audit hỗ trợ phát hiện, điều tra và kiểm toán. Nó không tự chặn yêu cầu.

Authorization quyết định quyền thực hiện yêu cầu. Admission và các kiểm tra khác có thể đánh giá nội dung hoặc điều kiện tiếp theo. Cần xác định lớp nào đang ngăn hành động, lớp nào chỉ ghi nhận và cảnh báo. [Tài liệu Kubernetes về authorization](https://kubernetes.io/docs/reference/access-authn-authz/authorization/).

## 2. Phân biệt ba loại hành động

### 2.1. Verb của yêu cầu tài nguyên

Các verb thường gặp gồm get, list, watch, create, update, patch, delete và deletecollection. Chúng diễn đạt cách API được truy cập, không trực tiếp diễn đạt mức rủi ro nghiệp vụ.

Một lệnh kubectl có thể tạo nhiều request. Ngược lại, hai lệnh khác tên có thể tác động đến cùng loại resource.

Không xây dựng rule chỉ từ tên lệnh mà người dùng gõ.

### 2.2. Subresource làm thay đổi ý nghĩa quyền

Một Pod và các subresource của Pod không phải cùng một mục tiêu kiểm soát:

| Mục tiêu | Ý nghĩa cần xem xét |
|---|---|
| pods | Đối tượng Pod |
| pods/log | Truy cập log |
| pods/exec | Khởi tạo thực thi lệnh qua API tương ứng |
| pods/attach | Kết nối vào tiến trình/container |
| pods/portforward | Mở đường chuyển tiếp tới workload |
| pods/ephemeralcontainers | Thay đổi container phục vụ debug theo API được hỗ trợ |

Phải kiểm tra request thực tế và phiên bản client. Không mặc định mọi thao tác tương tác luôn xuất hiện dưới cùng một verb hoặc cùng một kiểu kết nối.

### 2.3. Quyền đặc biệt trong authorization

bind, escalate và impersonate là các quyền có vai trò đặc biệt trong kiểm soát quyền. Chúng không nhất thiết xuất hiện thành các audit event độc lập có trường verb đúng bằng tên đó.

Ví dụ:

- Tạo RoleBinding thường được quan sát như create trên rolebindings.
- Thay rule của Role có thể xuất hiện dưới update hoặc patch.
- Dùng impersonation cần xem thông tin danh tính trong event của hành động thực tế.

RBAC có các điều kiện riêng khi tạo/sửa role và binding; kiểm tra bind hoặc escalate có thể tham gia trong quá trình xử lý đó. [Kiểm soát nâng quyền trong RBAC](https://kubernetes.io/docs/reference/access-authn-authz/rbac/#privilege-escalation-prevention-and-bootstrapping).

Một rule chỉ tìm verb bằng bind có thể bỏ sót thay đổi cấp quyền quan trọng.

## 3. Lập danh mục thao tác cần theo dõi

Một danh mục khởi đầu cho PAM có thể gồm:

| Nhóm | Dấu hiệu API cần quan tâm | Hậu quả cần đánh giá |
|---|---|---|
| Thay đổi RBAC | create/update/patch/delete trên role, binding | Tăng quyền, thay người nhận hoặc xóa hàng rào |
| Truy cập bí mật | get/list/watch trên secrets | Tiếp cận credential hoặc dữ liệu nhạy cảm |
| Cấp token | create trên serviceaccounts/token | Tạo khả năng xác thực dưới ServiceAccount |
| Phiên tương tác | pods/exec, attach, portforward | Tiếp cận runtime hoặc dịch vụ nội bộ |
| Sửa workload | Tạo/sửa Pod hoặc controller workload | Thay mã chạy, danh tính, volume hoặc cấu hình |
| Cấp chứng chỉ | CSR, approval và kết quả ký | Tạo đường xác thực mới |
| Thay kiểm soát | Webhook, chính sách hoặc cấu hình bảo vệ | Làm yếu kiểm tra đối với thao tác sau |
| Tác động diện rộng | deletecollection hoặc thao tác nhiều namespace | Gián đoạn hoặc mất trạng thái |
| Truy cập proxy nhạy cảm | nodes/proxy và đường tương ứng | Truy cập khả năng của kubelet ngoài luồng thông thường |

Đây là danh mục phân tích, không phải khẳng định mọi request trong bảng đều là sự cố. Controller hợp lệ cũng có thể thực hiện các hành động đó.

Kubernetes nêu các rủi ro như workload creation, token request, bind/escalate và node proxy trong hướng dẫn RBAC. Đặc biệt, get trên nodes/proxy không nên được hiểu đơn giản là quyền chỉ đọc. [RBAC good practices](https://kubernetes.io/docs/concepts/security/rbac-good-practices/).

### 3.1. Bổ sung phạm vi riêng của cluster

Mỗi cluster cần thêm:

- Custom resource và controller có quyền mạnh.
- Namespace đặc biệt.
- Tài nguyên chứa credential hoặc tham chiếu bí mật.
- Workload có liên kết tới danh tính cloud.
- Công cụ GitOps, CI/CD và hệ thống cấp quyền.
- Cơ chế authorization hoặc admission ngoài mặc định.

Danh mục phải được cập nhật khi cài extension hoặc thay đổi mô hình vận hành. Một danh sách tĩnh chỉ gồm tài nguyên built-in có thể không còn đủ.

## 4. Hiểu vòng đời một audit request

Một yêu cầu có thể sinh sự kiện ở các giai đoạn như RequestReceived, ResponseStarted, ResponseComplete hoặc Panic. Một số giai đoạn chỉ áp dụng cho loại request nhất định.

Các mức audit gồm None, Metadata, Request và RequestResponse; mức sau có thể ghi thêm body. Policy xét các rule theo thứ tự và lấy rule khớp đầu tiên. [Tài liệu Kubernetes Auditing](https://kubernetes.io/docs/tasks/debug/debug-cluster/audit/).

### 4.1. Không đếm mỗi stage thành một hành động mới

Cùng một auditID có thể xuất hiện nhiều lần qua các stage. Pipeline nên giữ thông tin giai đoạn, đồng thời liên kết chúng thành một request.

Một mô hình dữ liệu nội bộ có thể tách:

- Sự kiện đầu vào nguyên bản.
- Bản tổng hợp request theo cluster và auditID.
- Kết quả phân loại rủi ro.
- Hồ sơ cảnh báo hoặc điều tra liên quan.

Không xóa mọi stage trùng auditID một cách mù quáng; stage sau có thể bổ sung kết quả mà stage trước chưa có.

### 4.2. Received chưa phải thành công

RequestReceived chỉ chứng minh yêu cầu đi tới điểm audit tương ứng. Nó không chứng minh authorization đã cho phép hoặc tài nguyên đã thay đổi.

ResponseStarted cho một kết nối dài cũng chưa chứng minh mọi hoạt động bên trong đã hoàn tất.

### 4.3. Kết quả API chưa phải kết quả nghiệp vụ

Một request được chấp nhận có thể tạo ra công việc cho controller xử lý sau. Một yêu cầu xóa có thể còn chờ finalizer. Một thay đổi workload có thể chưa rollout thành công.

Bằng chứng cần phân biệt:

1. Có yêu cầu.
2. Có phản hồi API.
3. Có thay đổi đối tượng.
4. Hệ thống đạt hoặc chưa đạt trạng thái mong muốn.

### 4.4. Không quy mọi mã lỗi thành một nguyên nhân

Một mã 403 có thể liên quan authorization hoặc kiểm tra khác. Cần xem nguồn phản hồi, các trường và annotation tin cậy có sẵn, cùng cấu hình thực tế.

Một request trả lỗi vẫn có giá trị phát hiện: thử truy cập nhiều Secret hoặc thử tạo binding ngoài cửa sổ được phép đều có thể cần điều tra.

## 5. Những trường bằng chứng quan trọng

Schema audit có các trường như auditID, stage, verb, user, impersonatedUser, objectRef, requestURI và responseStatus. userAgent là thông tin client cung cấp; sourceIPs cần được hiểu cùng đường proxy tin cậy. [Schema audit.k8s.io/v1](https://kubernetes.io/docs/reference/config-api/apiserver-audit.v1/).

| Trường hoặc thông tin | Dùng để làm gì | Điểm cần thận trọng |
|---|---|---|
| Cluster ID | Phân biệt nguồn sự kiện | Không chỉ dùng tên context trên máy cá nhân |
| auditID và stage | Ghép vòng đời request | Không đồng nhất với phiên người dùng |
| user | Danh tính đã xác thực | Tài khoản dịch vụ không tự chỉ ra người yêu cầu |
| impersonatedUser | Danh tính được impersonate nếu có | Cần giữ cả người gọi gốc và danh tính hiệu lực |
| verb | Loại thao tác API | Chưa đủ để đánh giá rủi ro |
| objectRef | Resource, namespace, name, subresource khi có | Có thể thiếu thông tin tùy loại request hoặc stage |
| requestURI | Đường và tham số yêu cầu | Có thể chứa dữ liệu nhạy cảm trong query |
| responseStatus | Phản hồi ở stage tương ứng | Không phải bằng chứng mọi hậu quả đã hoàn tất |
| Timestamp | Đặt trong cửa sổ phê duyệt | Cần tính đến đồng hồ và độ trễ ingest |
| requestObject | Nội dung gửi khi policy cho ghi | Chưa chắc là trạng thái cuối sau xử lý |
| Nguồn cấp quyền | Liên kết yêu cầu PAM và JIT | Thường cần lấy từ hệ thống khác |

### 5.1. Bản ghi minh họa

Ví dụ sau chỉ minh họa một phần cấu trúc, không phải log thật:

~~~json
{
  "apiVersion": "audit.k8s.io/v1",
  "kind": "Event",
  "level": "Metadata",
  "auditID": "d5628ad1-2e91-4a4b-a4fb-1c2f4d233e19",
  "stage": "ResponseComplete",
  "requestURI": "/apis/rbac.authorization.k8s.io/v1/namespaces/payments-prod/rolebindings",
  "verb": "create",
  "user": {
    "username": "example-operator",
    "groups": ["example-payments-operators"]
  },
  "objectRef": {
    "apiGroup": "rbac.authorization.k8s.io",
    "resource": "rolebindings",
    "namespace": "payments-prod",
    "name": "example-maintenance-binding"
  },
  "responseStatus": {
    "code": 201
  }
}
~~~

Bản ghi cho thấy một request tạo RoleBinding đã nhận phản hồi 201. Nó chưa cho biết roleRef và danh sách subjects vì ví dụ chỉ ghi Metadata.

Muốn kết luận ai được cấp quyền gì, cần thêm bằng chứng nội dung thay đổi hoặc trạng thái đối tượng có liên kết đáng tin cậy. Đọc đối tượng hiện tại sau nhiều lần thay đổi có thể không tái hiện chính xác nội dung tại thời điểm event.

### 5.2. Phân biệt bằng chứng quan sát và suy luận

Nếu có đầy đủ manifest đã được quản lý, phiên bản đối tượng và lịch sử thay đổi, có thể đối chiếu quyền mới với yêu cầu được duyệt.

Nếu chỉ có metadata, hãy ghi “phát hiện thay đổi binding, cần xác minh nội dung”, thay vì khẳng định đã cấp cluster-admin khi chưa thấy roleRef.

## 6. Audit bind và escalate đúng cách

### 6.1. Theo dõi thay đổi đối tượng RBAC

Các thao tác cần xét gồm:

- Tạo Role hoặc ClusterRole.
- Thêm hoặc thay rule.
- Tạo binding.
- Thay subjects của binding.
- Thay nguồn quyền được aggregation vào role.
- Xóa hoặc thay đối tượng nhằm làm thay đổi quyền cuối cùng.

Cần phân tích cả phạm vi namespaced và cluster-scoped. Một thay đổi nhỏ về subject có thể cấp quyền lớn mà không sửa nội dung role.

### 6.2. Tách cấp quyền đặc biệt khỏi sử dụng quyền

Hai câu hỏi khác nhau:

1. Ai vừa được cấp bind hoặc escalate?
2. Sau đó, người đó đã dùng khả năng ấy để thay đổi role hoặc binding nào?

Câu hỏi đầu đòi hỏi hiểu rule được cấp. Câu hỏi sau cần audit của hành động thực tế và kết quả.

Không yêu cầu phải có hai event tương ứng một-một. Cách kiểm tra authorization nội bộ không mặc nhiên tạo một audit request riêng.

### 6.3. Role name không đủ để đo hậu quả

Một role tên viewer có thể bị sửa để chứa quyền mạnh. Một role tùy chỉnh có thể được aggregation vào role khác.

Hệ thống phát hiện cần biết phiên bản rule hoặc có bản chụp đáng tin cậy. Không chỉ cảnh báo khi roleRef.name bằng cluster-admin rồi bỏ qua các role có quyền tương đương hoặc đường gián tiếp.

### 6.4. Nội dung patch cần được hiểu theo loại patch

Một patch có thể chỉ chứa các thao tác thay đổi, không phải toàn bộ đối tượng. Không phân tích mọi requestObject như một manifest hoàn chỉnh.

Khi cần tính chênh lệch quyền, dùng trạng thái trước, nội dung patch phù hợp và trạng thái sau có liên kết phiên bản. Nếu thiếu đầu vào, đánh dấu kết quả chưa xác định thay vì suy ra sai.

## 7. Audit impersonation

Impersonation cho phép một người được ủy quyền yêu cầu API xử lý dưới danh tính khác. Kubernetes có cơ chế riêng kiểm tra quyền cho việc này. [Tài liệu User Impersonation](https://kubernetes.io/docs/reference/access-authn-authz/user-impersonation/).

Đối với PAM, cần giữ hai lớp:

- Người hoặc hệ thống đã xác thực ban đầu.
- Danh tính được dùng để thực hiện hành động sau impersonation.

### 7.1. Vì sao cần giữ cả hai?

Một broker có thể hợp lệ khi thay mặt người dùng. Nếu chỉ giữ danh tính hiệu lực, mất bằng chứng broker nào đã khởi tạo. Nếu chỉ giữ broker, không biết thao tác thuộc yêu cầu của cá nhân nào.

Thông tin ở hệ thống PAM cũng cần được bảo vệ. Không coi một chuỗi tên người do client tự khai là bằng chứng tương đương danh tính đã được xác thực.

### 7.2. Cảnh báo theo quan hệ được phép

Ví dụ điều kiện cần xem xét:

- Người gọi sử dụng một danh tính không nằm trong tập được ủy quyền.
- Danh tính hiệu lực có quyền nhạy cảm hơn phạm vi yêu cầu.
- Có impersonation ngoài cửa sổ hoặc ngoài namespace dự kiến.
- Một broker bắt đầu dùng danh tính mới chưa được kiểm kê.

Không cảnh báo mọi impersonation ở cùng mức độ nếu tổ chức dùng nó hợp lệ trên diện rộng. Nhưng ngoại lệ cần có phạm vi rõ và có kiểm thử.

## 8. Audit Secret, TokenRequest và chứng chỉ

### 8.1. Đọc Secret có thể là hành động đặc quyền

Không chỉ theo dõi thao tác ghi. Các yêu cầu get, list và watch có thể tiếp cận dữ liệu nhạy cảm tùy resource và quyền.

Ngữ cảnh cần biết gồm danh tính, namespace, loại Secret theo metadata được phép thu thập, thời điểm, tần suất và sự khác biệt với nhiệm vụ thông thường.

Không đọc hoặc sao chép giá trị Secret chỉ để tăng độ tin cậy cho cảnh báo. Bằng chứng truy cập không cần chứa bí mật đã được truy cập.

### 8.2. TokenRequest cần được ghi mà không lưu token

Một request tạo token cho ServiceAccount có thể tạo một khả năng xác thực mới. Cần liên kết người yêu cầu, ServiceAccount đích, kết quả và điều kiện cấp theo những thông tin an toàn có thể thu thập.

Không ghi response body chứa token vào kho log thông thường. Không dùng chính token làm khóa liên kết giữa các hệ thống.

Nếu token đã bị ghi ra log, cần coi đó là một nguồn lộ credential và xử lý phạm vi truy cập log, bản sao và hiệu lực token.

### 8.3. Phê duyệt CSR chưa đồng nghĩa chứng chỉ đã được cấp

Trong luồng CSR, việc yêu cầu, phê duyệt, ký và nhận chứng chỉ là các bước khác nhau. Tài liệu Kubernetes mô tả phê duyệt qua subresource approval cùng quyền theo signer. [Certificates and Certificate Signing Requests](https://kubernetes.io/docs/reference/access-authn-authz/certificate-signing-requests/).

Do đó, cần phân biệt:

- Ai tạo yêu cầu.
- Ai phê duyệt và cho signer nào.
- Yêu cầu có thực sự được ký không.
- Danh tính và mục đích của chứng chỉ phát hành.
- Credential đó có thể tạo truy cập nào tiếp theo.

Không tìm duy nhất audit verb approve rồi coi đã bao phủ toàn bộ luồng.

## 9. Chọn policy audit theo rủi ro dữ liệu

### 9.1. Metadata là điểm khởi đầu, không phải cam kết không có dữ liệu nhạy cảm

Metadata không ghi request/response body theo mức audit, nhưng các trường như URI, tên tài nguyên, lỗi hoặc thông tin danh tính vẫn có thể nhạy cảm.

Đặc biệt, lệnh hoặc tham số có thể nằm trong query của một request tương tác. Người vận hành không nên truyền secret qua dòng lệnh hoặc URL rồi kỳ vọng mức Metadata tự che nó.

Policy audit tiêu chuẩn chọn mức và tập request; không nên giả định nó tự xóa mọi trường nhạy cảm tùy ý. Nếu làm sạch ở downstream, dữ liệu thô phía trước vẫn cần được bảo vệ.

### 9.2. Request giúp hiểu nội dung nhưng cần giới hạn

Đối với thay đổi RBAC, nội dung request có thể giúp xác định subjects hoặc rule. Tuy nhiên, annotation và các trường do người dùng nhập vẫn có thể chứa thông tin không nên công khai.

Việc ghi Request phải có phạm vi, quyền truy cập, thời hạn lưu và quy trình xử lý dữ liệu phù hợp.

### 9.3. Tránh RequestResponse mặc định cho mọi tài nguyên

Ghi toàn bộ body phản hồi có thể làm lộ Secret, token hoặc dữ liệu khác. Nó cũng làm tăng lưu lượng và chi phí lưu trữ.

Quyết định thêm body cần xuất phát từ câu hỏi điều tra cụ thể, không phải từ nguyên tắc “càng nhiều log càng tốt”.

## 10. Policy minh họa

Policy sau minh họa cách ưu tiên metadata cho các đường có thể chứa bí mật và ghi request body cho thay đổi RBAC được lựa chọn:

~~~yaml
apiVersion: audit.k8s.io/v1
kind: Policy
rules:
  - level: Metadata
    resources:
      - group: ""
        resources:
          - secrets
          - serviceaccounts/token
          - pods/exec
          - pods/attach
          - pods/portforward
          - nodes/proxy

  - level: Request
    verbs:
      - create
      - update
      - patch
      - delete
      - deletecollection
    resources:
      - group: rbac.authorization.k8s.io
        resources:
          - roles
          - rolebindings
          - clusterroles
          - clusterrolebindings

  - level: Metadata
    resources:
      - group: certificates.k8s.io
        resources:
          - certificatesigningrequests
          - certificatesigningrequests/approval
          - certificatesigningrequests/status

  - level: Metadata
~~~

Đây là policy học tập, chưa phải cấu hình được khuyến nghị áp dụng nguyên trạng cho mọi cluster. Bài học không triển khai policy này lên hệ thống thật.

### 10.1. Điều cần hiểu trong ví dụ

- Các rule có thứ tự; catch-all nằm cuối.
- Tài nguyên và subresource cần được xét đúng.
- Rule RBAC chỉ tăng mức cho những verb được liệt kê.
- Catch-all giữ metadata cho phần còn lại, nên cần đánh giá dung lượng.
- Không có rule nào ở đây tự tạo cảnh báo hoặc chặn hành động.
- Không có cơ chế tự che dữ liệu nhạy cảm nằm trong URI.
- Không bỏ stage nào trong ví dụ; pipeline phải liên kết nhiều stage của cùng request.

### 10.2. Policy chưa phải toàn bộ đường audit

Cần cấu hình nguồn ghi, nơi nhận, quyền lưu trữ, giám sát mất sự kiện và quy trình vận hành. Với cluster được quản lý bởi nhà cung cấp, cách bật hoặc xuất audit có thể khác việc cấu hình trực tiếp API server.

Đừng xác nhận audit hoạt động chỉ vì có một YAML hợp lệ. Phải kiểm tra sự kiện thực tế đi hết đường đến nơi phân tích.

## 11. Xây dựng pipeline phát hiện

Một mô hình tham chiếu:

~~~text
Kubernetes audit
      ↓
Thu thập và lưu nguồn có bảo vệ
      ↓
Chuẩn hóa / liên kết stage theo request
      ↓
Bổ sung danh tính, quyền, yêu cầu PAM và trạng thái tài nguyên
      ↓
Phân loại rủi ro
      ↓
Cảnh báo → người xử lý → đối soát kết quả
~~~

### 11.1. Chuẩn hóa mà không mất bằng chứng

Bản chuẩn hóa nên giữ tham chiếu tới dữ liệu nguồn có kiểm soát. Không thay toàn bộ event bằng một nhãn như privileged=true rồi bỏ các trường cần điều tra.

Khi một trường thiếu, ghi rõ chưa có dữ liệu. Không tự gán tên namespace hoặc danh tính từ suy đoán không đáng tin cậy.

### 11.2. Tách attempt, accepted và verified

Một hệ thống có thể dùng các trạng thái nội bộ:

- ATTEMPT_OBSERVED: thấy yêu cầu.
- RESPONSE_OBSERVED: có phản hồi và phân loại kết quả theo API.
- CHANGE_CONFIRMED: đã đối chiếu thay đổi.
- IMPACT_VERIFIED: đã kiểm tra hậu quả liên quan.
- NEEDS_RECONCILIATION: thiếu dữ kiện để kết luận.

Tên chỉ mang tính minh họa. Giá trị nằm ở việc không gộp tất cả thành “thành công” hoặc “thất bại”.

### 11.3. Mã giả phát hiện thay đổi phân quyền

~~~text
on_audit_event(event):
    request = correlate_by_cluster_and_audit_id(event)

    if targets_rbac_resource(request):
        if is_change_verb(request):
            finding = open_or_update_finding(request)

            finding.actor = authenticated_identity(request)
            finding.effective_identity = impersonated_or_original_identity(request)
            finding.scope = observed_resource_scope(request)
            finding.outcome = classify_observed_response(request)

            evidence = load_authorized_change_evidence(request)

            if evidence.is_sufficient:
                finding.permission_change = calculate_change(evidence)
            else:
                finding.permission_change = UNKNOWN

            approval = match_trusted_pam_approval(request, evidence)
            finding.approval_match = approval.result

            route_by_risk_and_uncertainty(finding)
~~~

Đây là mã giả, không phải query hay script có thể chạy trực tiếp. Hệ thống thực tế cần xử lý patch, stage thiếu, sự kiện đến trễ và nhiều lần thay đổi cùng đối tượng.

## 12. Liên kết audit với PAM và JIT

Một sự kiện thực hiện trong khoảng thời gian được duyệt chưa đủ để chứng minh nó được duyệt. Cần đối chiếu cả danh tính, cluster, namespace, hành động và phạm vi.

| Dữ liệu PAM | Dữ liệu Kubernetes cần đối chiếu |
|---|---|
| Người được cấp quyền | user và danh tính hiệu lực có liên kết đáng tin cậy |
| Cluster đích | Nguồn event và định danh cluster |
| Namespace | Phạm vi yêu cầu thực tế |
| Role hoặc hành động | Rule, resource và nội dung thay đổi liên quan |
| Cửa sổ thực hiện | Timestamp nguồn, thời điểm cấp và thu hồi |
| Kế hoạch | Đối tượng, tham số và thay đổi được cho phép |
| Kết thúc | Bằng chứng request mới và quyền cuối cùng |

### 12.1. Controller thực hiện thay người dùng

Nếu controller tạo RoleBinding, audit Kubernetes có thể ghi danh tính controller. Cần nối với yêu cầu nào đã khiến controller thực hiện thay đổi.

Mã liên kết cần được bảo vệ khỏi giả mạo hoặc sửa tùy tiện. Một annotation do người bất kỳ có thể ghi không tự trở thành bằng chứng phê duyệt.

### 12.2. Theo dõi quyền phát sinh trong cửa sổ

Một người được cấp quyền tạm thời có thể tạo binding, credential hoặc workload khác. Những đối tượng đó có thể còn sau khi binding JIT ban đầu bị xóa.

PAM nên đối soát toàn bộ thay đổi liên quan với trạng thái mong muốn cuối cùng, không chỉ đếm sự kiện cleanup.

### 12.3. Phân biệt giờ nguồn và giờ nhận

Một event đến SIEM sau cửa sổ không có nghĩa thao tác xảy ra sau cửa sổ. Cần dùng thời điểm nguồn và ghi nhận độ trễ ingest.

Ngược lại, đồng hồ nguồn sai có thể làm việc đối chiếu không đáng tin cậy. Pipeline phải có cách theo dõi chất lượng thời gian.

## 13. Tình huống: thay đổi binding sau đó đọc Secret

Một kỹ sư được cấp quyền chẩn đoán ứng dụng. Trong cửa sổ đó xuất hiện:

1. Một request tạo RoleBinding.
2. Một lần đọc Secret bởi danh tính vừa được cấp quyền.
3. Một request mở phiên tương tác vào Pod.
4. Binding ban đầu của yêu cầu JIT bị cleanup khi hết hạn.

### 13.1. Những gì chưa được phép kết luận ngay

Không thể chỉ từ trình tự thời gian khẳng định đã có xâm nhập. Có thể có thay đổi hợp lệ chưa được đối chiếu.

Cũng không thể kết luận an toàn vì mọi hành động nằm trong cửa sổ JIT. Phê duyệt chẩn đoán không mặc nhiên cho phép cấp quyền mới hoặc đọc mọi Secret.

### 13.2. Quy trình điều tra

- Xác định cluster, namespace và danh tính thực ở từng request.
- Lấy nội dung binding từ nguồn bằng chứng được phép.
- Kiểm tra roleRef, subjects và rule hiệu lực tại thời điểm đó.
- Liên kết với kế hoạch được duyệt.
- Xác định Secret nào bị truy cập mà không sao chép giá trị vào hồ sơ thông thường.
- Kiểm tra phạm vi phiên tương tác và giới hạn bằng chứng sẵn có.
- Đánh giá credential, workload hoặc đường quyền mới.
- Xác minh cleanup đã xử lý quyền phát sinh hay chỉ binding đầu tiên.

### 13.3. Báo cáo có mức chắc chắn rõ

Ví dụ:

> Đã xác nhận tạo binding cho một ServiceAccount ngoài phạm vi phê duyệt ban đầu. Có phản hồi API thành công cho truy cập Secret. Audit hiện có không chứng minh nội dung mọi lệnh trong phiên tương tác. Binding phát sinh và credential liên quan đang được xử lý; chưa đóng hồ sơ.

Báo cáo phân biệt điều quan sát được với phần chưa có bằng chứng.

## 14. Giới hạn của audit và điểm mù

### 14.1. Audit API không phải terminal transcript

Sự kiện mở exec có thể giúp xác định ai mở kết nối tới Pod. Nó không tự ghi toàn bộ lệnh tương tác, output hay hoạt động bên trong container.

Nếu cần bằng chứng mức đó, phải có cơ chế bổ sung và kiểm tra phạm vi thu thập. Không biến yêu cầu ghi phiên thành việc vô tình ghi lại bí mật.

### 14.2. Không phải mọi hoạt động đều đi qua cùng API server

Truy cập node, kubelet, ứng dụng hoặc hệ thống ngoài cluster có thể cần nguồn log khác. Đặc biệt, proxy hoặc đường quản trị khác cần được đánh giá để tránh giả định audit trung tâm bao phủ toàn bộ hoạt động phía sau.

### 14.3. Controller tạo một chuỗi nhân quả

Một người tạo Deployment; sau đó controller tạo ReplicaSet và Pod bằng danh tính của controller. Cần nối theo owner reference, phiên bản và thời gian khi đủ dữ kiện.

Không gán mọi request của controller cho con người gần nhất theo thời gian. Nhiều công việc đồng thời có thể tạo kết luận sai.

### 14.4. Mất sự kiện là một trạng thái cần giám sát

Không có event có thể do không có hành động, policy không ghi, đường thu thập lỗi hoặc dữ liệu đã quá hạn lưu.

Cần giám sát số lượng, độ trễ, lỗi gửi, dung lượng và tính liên tục của nguồn. Một dashboard trống không tự chứng minh cluster yên ổn.

## 15. Kiểm thử trước khi tin cậy cảnh báo

Các ca kiểm thử cần được thực hiện trong môi trường được phép, dùng danh tính và dữ liệu mô phỏng.

| Ca kiểm thử | Bằng chứng mong muốn |
|---|---|
| Tạo binding hợp lệ | Có actor, scope, kết quả và đối chiếu phê duyệt |
| Tạo binding bị từ chối | Có attempt và phân loại kết quả đúng |
| Patch subjects | Không bị parser hiểu sai như manifest đầy đủ |
| Thay rule chứa quyền đặc biệt | Phát hiện quyền mới và đối tượng bị ảnh hưởng |
| Impersonation được phép | Giữ cả danh tính gốc và danh tính hiệu lực |
| Đọc Secret giả lập | Ghi nhận truy cập, không lộ giá trị giả lập trong nơi không được phép |
| Tạo token thử nghiệm | Có dấu vết cấp, response token không bị ghi vào kho log thường |
| Mở phiên tương tác | Xác định verb, subresource và stage của luồng thực tế |
| Phê duyệt CSR thử nghiệm | Phân biệt phê duyệt với ký và sử dụng |
| Event đến trễ hoặc lặp | Không nhân đôi hành động và không đối chiếu sai cửa sổ |
| Nguồn log gián đoạn | Có cảnh báo về độ bao phủ |
| Cleanup JIT nhưng còn binding phát sinh | Phát hiện và giữ hồ sơ chưa hoàn tất |

Nếu có dữ liệu giả lập nhạy cảm trong kiểm thử, dùng dấu hiệu nhận diện riêng để kiểm tra đường lộ mà không đưa credential thật vào log.

Không chạy hành vi nâng quyền thực sự chỉ để tạo cảnh báo trong production.

## 16. Vận hành cảnh báo và bảo vệ bằng chứng

### 16.1. Cảnh báo phải có người xử lý

Một cảnh báo hữu ích nêu được cluster, đối tượng, actor, danh tính hiệu lực, hành động, kết quả quan sát và lý do cần xem xét.

Đính kèm tham chiếu bằng chứng theo quyền; không gửi body chứa token hoặc Secret vào kênh thông báo rộng.

### 16.2. Giảm nhiễu bằng phạm vi, không bằng ngoại lệ vô hạn

Có thể nhận diện controller hợp lệ, nhưng ngoại lệ nên có resource, phạm vi và hành động rõ. Nếu controller bị chiếm, việc bỏ qua toàn bộ hoạt động của nó sẽ tạo điểm mù lớn.

Khi thay đổi baseline, cần giữ owner và bằng chứng kiểm thử.

### 16.3. Những chỉ số nên theo dõi

- Tỷ lệ nguồn cluster được kiểm thử gần đây.
- Độ trễ từ nguồn tới cảnh báo.
- Số request rủi ro không liên kết được với danh tính hoặc yêu cầu.
- Số thay đổi quyền chưa đối soát.
- Số lỗi parser và event thiếu stage.
- Thời gian từ phát hiện tới xử lý quyền tồn dư.
- Số lần phát hiện dữ liệu nhạy cảm đi vào nơi lưu không phù hợp.

Không chỉ đo số lượng log hoặc số alert. Cần đo khả năng kết luận và xử lý.

## 17. Những lỗi thường gặp

| Lỗi | Hệ quả | Cách cải thiện |
|---|---|---|
| Chỉ tìm verb bind/escalate | Bỏ sót request thay đổi RBAC thực tế | Phân tích resource, verb và nội dung quyền |
| Chỉ theo dõi create/update/delete | Bỏ sót đọc Secret và đường proxy nhạy cảm | Phân loại theo hậu quả |
| Bỏ qua subresource | Nhầm đọc Pod với exec hoặc token request | Chuẩn hóa resource và subresource |
| Đếm mỗi stage là một lần thao tác | Phóng đại số hành động | Liên kết theo cluster và auditID |
| Coi RequestReceived là thành công | Kết luận sai kết quả | Theo dõi phản hồi và trạng thái cuối |
| Coi mọi 403 là RBAC từ chối | Chẩn đoán sai lớp kiểm soát | Dùng ngữ cảnh và bằng chứng nguồn |
| Ghi RequestResponse cho mọi thứ | Có thể lộ Secret hoặc token | Chọn mức theo câu hỏi cần trả lời |
| Nghĩ Metadata luôn vô hại | Bỏ sót URI và thông tin nhạy cảm | Đánh giá dữ liệu thực tế và bảo vệ log |
| Chỉ giữ danh tính được impersonate | Mất người khởi tạo | Giữ cả hai lớp danh tính |
| Coi audit exec là bản ghi mọi lệnh | Đánh giá sai bằng chứng phiên | Nêu rõ giới hạn và nguồn bổ sung |
| Đóng hồ sơ sau cleanup đầu tiên | Bỏ sót quyền phát sinh | Đối soát quyền hiệu lực cuối cùng |
| Loại toàn bộ controller khỏi giám sát | Tạo vùng mù khi controller bị chiếm | Ngoại lệ có phạm vi và kiểm thử |

## 18. Thực hành

### Bài tập 1: Sửa rule phát hiện

Một rule chỉ tìm event.verb thuộc tập bind, escalate, impersonate.

Hãy giải thích những hành động nào có thể bị bỏ sót. Thiết kế lại bằng nhóm resource, thay đổi role/binding và thông tin danh tính.

### Bài tập 2: Chọn mức audit

Bạn cần theo dõi tạo token cho ServiceAccount, cập nhật RoleBinding và đọc Secret.

Hãy chọn thông tin tối thiểu cho từng loại. Nêu cách biết subjects hoặc rule được đổi mà vẫn tránh ghi token và dữ liệu Secret vào kho log thông thường.

### Bài tập 3: Đọc vòng đời request

Một request có RequestReceived rồi ResponseStarted nhưng chưa thấy ResponseComplete. Một request khác có ResponseComplete với lỗi.

Hãy liệt kê điều đã biết, điều chưa biết và cách trình bày kết quả mà không gọi tất cả là thành công hoặc thất bại giống nhau.

### Bài tập 4: Đối chiếu JIT

Một binding mới được tạo trong cửa sổ được duyệt, nhưng role và ServiceAccount đích khác kế hoạch.

Hãy thiết kế dữ liệu cần đối chiếu, cảnh báo và quy trình xử lý quyền phát sinh. Giải thích vì sao chỉ kiểm tra thời gian chưa đủ.

### Bài tập 5: Viết báo cáo với điểm mù

Bạn thấy mở exec vào Pod nhưng không có terminal transcript và không đủ log về hệ thống bên ngoài.

Hãy viết báo cáo phân biệt hành động API đã xác nhận, phạm vi chưa quan sát được và bước điều tra tiếp theo. Không suy diễn nội dung lệnh từ việc chỉ thấy một phiên mở.

## 19. Điểm cần ghi nhớ

Audit thao tác đặc quyền trong Kubernetes phải dựa trên danh tính, verb, resource, subresource, phạm vi và kết quả. Tên lệnh hoặc một danh sách verb đặc biệt không đủ để tái hiện thay đổi quyền.

Một triển khai PAM hiệu quả bảo vệ dữ liệu audit, liên kết yêu cầu với thực thi và phân biệt quan sát với suy luận. Bằng chứng cần tiếp tục tới quyền và trạng thái cuối cùng, đồng thời nêu rõ những hoạt động nằm ngoài độ bao phủ của audit API.
