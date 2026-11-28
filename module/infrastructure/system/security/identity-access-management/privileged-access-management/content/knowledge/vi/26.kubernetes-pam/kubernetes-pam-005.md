# Kubernetes exec session

Kubernetes exec session là một lần thực thi lệnh trong container đang chạy thông qua API Kubernetes. Phiên có thể chỉ chạy một lệnh rồi kết thúc, hoặc mở kết nối tương tác để người vận hành làm việc trong shell.

Trong Privileged Access Management (PAM), quyền exec cần được xem là quyền tiếp cận môi trường thực thi của ứng dụng. Người có quyền này có thể chạm tới tệp, kết nối mạng, dữ liệu và credential mà tiến trình trong container được phép sử dụng. Vì vậy, “không có quyền đọc Secret qua Kubernetes API” không đủ để kết luận người đó không thể tiếp cận bí mật đã được đưa vào container.

Bài học tập trung vào cấp quyền đúng phạm vi, mở phiên có điều kiện, giám sát, ghi bằng chứng và kết thúc phiên. Các tên cluster, Pod, principal và grant trong ví dụ là giả định. Manifest chỉ minh họa thiết kế; không áp dụng trực tiếp vào production nếu chưa đối chiếu phiên bản, cơ chế xác thực và quy trình vận hành thực tế.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

- Phân biệt exec với đọc log, attach, port-forward và debug container.
- Giải thích ranh giới giữa danh tính Kubernetes và danh tính tiến trình trong container.
- Thiết kế quyền pods/exec theo namespace và Pod cần thiết.
- Nhận biết những giới hạn mà RBAC không tự cung cấp.
- Kết hợp grant PAM, credential có hạn và kiểm soát đường kết nối.
- Phân biệt API audit, bản ghi luồng phiên và telemetry runtime.
- Kiểm thử việc chặn phiên mới, ngắt phiên đang mở và xử lý tác động còn lại.

## 2. Exec thực sự làm gì?

### 2.1. Lệnh một lần và shell tương tác

Cú pháp kubectl exec cho phép chọn Pod, container và lệnh. Tùy chọn stdin và TTY phục vụ tương tác; container có thể được chọn mặc định nếu người dùng không chỉ rõ. Trong một quy trình PAM, nên chỉ rõ container để tránh thao tác nhầm. [Tham chiếu kubectl exec](https://kubernetes.io/docs/reference/kubectl/generated/kubectl_exec/).

Ví dụ trong một cluster lab đã được cấp quyền:

~~~sh
kubectl --context lab-pam -n billing-lab exec billing-api-7c89d6f4b5-k9m2q -c app -- id
~~~

Đây là yêu cầu chạy chương trình id trong container app. Nó không cần mở shell tương tác.

Nếu container có shell phù hợp và nhiệm vụ cho phép:

~~~sh
kubectl --context lab-pam -n billing-lab exec -it billing-api-7c89d6f4b5-k9m2q -c app -- sh
~~~

Sau khi mở shell, những gì người dùng gõ tiếp nằm trong luồng tương tác của phiên. Không nên coi mỗi lệnh gõ trong shell là một yêu cầu pods/exec mới.

### 2.2. Không phải SSH vào node

Exec đi qua đường API và thành phần thực thi của Kubernetes để tạo tiến trình trong container. Nó không đồng nghĩa đăng nhập SSH vào máy chủ.

Tuy nhiên, mức tác động phụ thuộc cấu hình container. Một container có quyền mạnh, volume nhạy cảm hoặc khả năng tiếp cận tài nguyên host có ranh giới khác container đã được hạn chế.

Không dùng từ “chỉ ở trong container” làm căn cứ cho phép quyền mà chưa đánh giá môi trường thực thi.

### 2.3. Hai danh tính khác nhau

Có ít nhất hai lớp danh tính:

| Lớp | Ý nghĩa |
| --- | --- |
| Danh tính gọi API | Người hoặc ServiceAccount được Kubernetes xác thực và cấp quyền exec |
| Danh tính tiến trình | UID, GID hoặc tài khoản hệ điều hành dùng để chạy tiến trình trong container |

Security context của Pod hoặc container chi phối các thuộc tính như user và group của tiến trình. Nó không tự chuyển username Kubernetes của người vận hành thành một tài khoản hệ điều hành riêng trong container. [Security context cho Pod và container](https://kubernetes.io/docs/tasks/configure-pod-container/security-context/).

Nếu nhiều người exec vào cùng container dưới cùng UID, một log ứng dụng chỉ ghi UID có thể không phân biệt được họ. Cần chuỗi liên kết tới phiên và danh tính API.

### 2.4. Một phiên exec có thể dùng quyền của workload

Trong container có thể tồn tại:

- Secret được mount hoặc đưa vào môi trường.
- Credential cơ sở dữ liệu.
- Token ServiceAccount khi được cấp cho workload.
- Cơ chế nhận credential cloud.
- Chứng thư ứng dụng.
- Dữ liệu trên volume.
- Kết nối tới dịch vụ nội bộ.

Khả năng tiếp cận thực tế còn phụ thuộc quyền hệ điều hành và cách ứng dụng được triển khai. Nhưng khi lập inventory PAM, phải đánh giá các đường này thay vì chỉ nhìn quyền Kubernetes API của người gọi.

## 3. Khi nào nên dùng exec?

### 3.1. Bắt đầu từ câu hỏi cần chẩn đoán

Trước khi mở phiên, xác định:

- Cần biết điều gì?
- Có thể lấy từ metric, trace, log hoặc API chẩn đoán sẵn có không?
- Có cần chạy mã trong chính container không?
- Có cần tương tác hay chỉ cần một lệnh đã định?
- Có dữ liệu nhạy cảm nào có thể xuất ra?
- Công việc có thể làm trên bản sao hoặc môi trường thử nghiệm không?

Ví dụ, kiểm tra phiên bản triển khai thường có thể dựa vào metadata hoặc endpoint được thiết kế sẵn. Không cần cấp shell chỉ để đọc một thông tin có thể quan sát qua đường hẹp hơn.

### 3.2. Phân biệt các khả năng vận hành

| Khả năng | Điều thực hiện | Điểm cần quản lý riêng |
| --- | --- | --- |
| Đọc log | Lấy log container | Dữ liệu nhạy cảm có thể nằm trong log |
| Exec | Tạo tiến trình trong container | Thực thi mã với khả năng của môi trường đích |
| Attach | Nối vào tiến trình đã chạy | Tương tác với luồng của tiến trình đó |
| Port-forward | Mở đường kết nối tới cổng | Có thể tiếp cận dịch vụ quản trị hoặc dữ liệu |
| Ephemeral debug container | Thêm môi trường chẩn đoán theo cơ chế được phép | Quyền, image và mức tiếp cận cần được đánh giá |
| Debug node | Chẩn đoán ở cấp node | Phạm vi tác động cao hơn công việc trong một container |

Quyền cho một khả năng không nên tự kéo theo mọi khả năng khác. Đặc biệt, không bổ sung quyền debug node hoặc sửa workload chỉ để xử lý lỗi thiếu shell trong image.

### 3.3. Image tối giản có thể không có công cụ chẩn đoán

Không phải container nào cũng có sh, bash, id, tar hoặc công cụ mạng. Một lệnh thất bại vì thiếu chương trình không chứng minh quyền RBAC sai.

Nếu cần công cụ bổ sung, dùng phương án chẩn đoán đã được quản lý và phê duyệt. Không mặc định cho phép cài package, sửa image đang chạy hoặc đưa bất kỳ debug image nào vào production.

## 4. Phạm vi quyền Kubernetes cho exec

### 4.1. Subresource pods/exec

Quyền vào exec là quyền trên subresource pods/exec, khác với quyền đọc Pod thông thường. Kubernetes RBAC dùng tên resource/subresource để biểu diễn các quyền này. RBAC cấp quyền theo hướng cộng thêm; một Role hẹp không loại bỏ quyền rộng đã được cấp qua binding khác. [Sử dụng Kubernetes RBAC](https://kubernetes.io/docs/reference/access-authn-authz/rbac/).

Khi đánh giá một principal, cần xem toàn bộ quyền hiệu lực, bao gồm nhóm mà principal thuộc về và các binding liên quan.

### 4.2. Chú ý khác biệt giao thức và phiên bản

Không nên rút gọn thành quy tắc “exec luôn chỉ cần một verb giống nhau trên mọi cluster”.

Đường streaming có thể dùng WebSocket hoặc giao thức khác tùy client và server. Feature gate AuthorizePodWebsocketUpgradeCreatePermission, khi được bật, yêu cầu quyền create cho việc nâng cấp WebSocket vào các subresource như pods/exec. Do đó, HTTP GET cho handshake không có nghĩa chỉ cần quyền đọc là đủ trong mọi cấu hình. [Feature gate của Kubernetes](https://kubernetes.io/docs/reference/command-line-tools-reference/feature-gates/).

Thiết kế phải:

- Ghi phiên bản client và API server.
- Xác minh feature gate hoặc hành vi mà nhà cung cấp quản lý hỗ trợ.
- Kiểm thử đường streaming thực tế.
- Chỉ thêm verb cần thiết đã được xác nhận.
- Theo dõi audit theo subresource, không chỉ dựa vào một verb cố định.

Không cấp wildcard để tránh phải hiểu vì sao client hiện tại bị từ chối.

### 4.3. RoleBinding và phạm vi namespace

RoleBinding gắn role với các subject trong namespace của nó; role được tham chiếu có thể là Role trong namespace hoặc ClusterRole. Điều đó không tự biến một RoleBinding thành quyền trên mọi namespace. [API RoleBinding](https://kubernetes.io/docs/reference/kubernetes-api/rbac/role-binding-v1/).

Với nhiệm vụ trong một namespace, ưu tiên ranh giới namespace rõ ràng thay vì cấp ClusterRoleBinding rộng rồi mong người vận hành tự chọn đúng đích.

### 4.4. Giới hạn theo tên Pod

Kubernetes hỗ trợ resourceNames cho pods/exec; hạn chế của top-level create theo tên không áp dụng giống vậy cho subresource này. [Giới hạn resource theo tên trong RBAC](https://kubernetes.io/docs/reference/access-authn-authz/rbac/).

Tuy nhiên, tên Pod không phải UID. Trong thiết kế PAM, cần xem xét việc Pod bị thay thế hoặc tên được dùng lại, đặc biệt khi grant kéo dài hơn vòng đời workload.

RBAC theo tên cũng không tự giới hạn:

- Container nào trong Pod.
- Lệnh và đối số.
- Có TTY hay không.
- Thời gian phiên.
- Dữ liệu được đọc trong container.
- Kết nối mạng từ tiến trình.

Những ranh giới đó cần cơ chế khác nếu là yêu cầu bắt buộc.

## 5. Ví dụ RBAC hẹp cho một Pod lab

### 5.1. Role minh họa

~~~yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: pam-exec-billing-session-019
  namespace: billing-lab
rules:
  - apiGroups: [""]
    resources: ["pods"]
    resourceNames: ["billing-api-7c89d6f4b5-k9m2q"]
    verbs: ["get"]
  - apiGroups: [""]
    resources: ["pods/exec"]
    resourceNames: ["billing-api-7c89d6f4b5-k9m2q"]
    verbs: ["create"]
~~~

Role cho phép đọc metadata của Pod được chỉ định và quyền create trên subresource exec theo giả định đường client đã được kiểm thử. Nếu stack thực tế cần kiểm tra thêm verb, phải xác minh và bổ sung đúng phạm vi, không mặc định cấp mọi verb.

Manifest không cấp list Pod, đọc Secret, đọc log, sửa workload hoặc quyền quản trị RBAC. Dù vậy, exec vẫn có thể tiếp cận dữ liệu mà container được phép dùng.

### 5.2. Binding tới danh tính phiên

~~~yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  name: pam-exec-billing-session-019
  namespace: billing-lab
  annotations:
    pam.example.com/grant-id: "GRANT-2841"
    pam.example.com/expires-at: "2026-11-26T14:30:00+07:00"
subjects:
  - kind: User
    name: "pam:session:session-019"
    apiGroup: rbac.authorization.k8s.io
roleRef:
  kind: Role
  name: pam-exec-billing-session-019
  apiGroup: rbac.authorization.k8s.io
~~~

Tên User phải khớp danh tính do cơ chế xác thực thật tạo ra. Manifest này không tạo tài khoản người dùng hoặc tự cấp credential cho principal đó.

Các annotation ở ví dụ chỉ là metadata do hệ thống PAM quy ước. Chúng không khiến RoleBinding tự hết hạn. Nếu dùng annotation để điều phối thu hồi, cần controller hoặc quy trình có khả năng thực thi, giám sát và xác minh cleanup.

### 5.3. Những điều ví dụ chưa bảo đảm

Ví dụ RBAC chưa tạo ra một sản phẩm PAM hoàn chỉnh. Nó chưa:

- Kiểm tra yêu cầu nghiệp vụ.
- Xác thực tăng cường.
- Phê duyệt.
- Giới hạn container app trong Pod.
- Giới hạn đúng UID Pod đã duyệt.
- Ghi lại luồng phiên.
- Ngắt kết nối khi hết hạn.
- Thu hồi các binding khác.
- Ngăn sử dụng credential ngoài đường được giám sát.

Các yêu cầu ấy phải được phân công cho thành phần thực thi cụ thể.

## 6. Workflow PAM cho một phiên exec

### 6.1. Chuỗi trạng thái đề xuất

~~~text
REQUESTED
    -> APPROVED
    -> GRANT_ACTIVE
    -> SESSION_OPEN
    -> SESSION_CLOSING
    -> SESSION_CLOSED
    -> ACCESS_CLEANUP_VERIFIED
~~~

Cũng cần các trạng thái từ chối, hết hạn trước khi mở, lỗi kết nối, mất recorder và cleanup thất bại.

Đừng dùng một trạng thái completed để che lấp mọi sự khác biệt giữa “người dùng đóng terminal”, “stream đã đóng” và “quyền đã được thu hồi”.

### 6.2. Nội dung yêu cầu

Một yêu cầu nên xác định:

- Danh tính người hoặc workload.
- Lý do và mã công việc.
- Cluster được định danh rõ.
- Namespace.
- Pod name, UID và container đích.
- Chế độ một lệnh hay shell.
- Năng lực dự kiến cần sử dụng.
- Thời gian và thời hạn tối đa.
- Owner và người phê duyệt nếu policy yêu cầu.
- Điều kiện giám sát, recording và xử lý khi gián đoạn.

Chỉ ghi tên Deployment có thể chưa đủ nếu hệ thống tự chọn một replica bất kỳ. Khi mở phiên, cần resolve đích theo quy tắc rồi kiểm tra lại phạm vi được duyệt.

### 6.3. Ví dụ grant nghiệp vụ

~~~yaml
grantId: GRANT-2841
requester: operator-017
purpose: Chan doan ket noi cua Billing API
target:
  clusterId: cluster-lab-01
  namespace: billing-lab
  podName: billing-api-7c89d6f4b5-k9m2q
  podUid: pod-uid-example-019
  containerName: app
session:
  mode: interactive
  maximumDurationSeconds: 900
  recordingRequired: true
approval:
  reference: CHG-2841
  state: approved
~~~

Đây là schema minh họa của PAM, không phải đối tượng Kubernetes có sẵn. Mỗi thuộc tính bắt buộc phải được ánh xạ tới cơ chế kiểm tra hoặc thực thi thực tế.

Nếu gateway không thể xác nhận container hoặc UID như thiết kế yêu cầu, nó không nên báo rằng đã giới hạn đúng các thuộc tính ấy.

### 6.4. Kiểm tra lại ngay trước khi mở stream

Giữa lúc duyệt và lúc kết nối, Pod có thể đã:

- Bị xóa và tạo lại.
- Đổi owner hoặc được thay bằng bản triển khai khác.
- Restart container.
- Không còn ở trạng thái có thể thực thi.
- Thay môi trường mà nhiệm vụ đang nhắm tới.

Cần đối chiếu đích hiện tại với grant theo policy. Nếu có khoảng thời gian giữa kiểm tra và kết nối, phải đánh giá nguy cơ thay thế đích và cách giảm khoảng trống đó.

Không coi một lần đọc UID ở giao diện là ràng buộc nguyên tử cho request exec theo tên về sau.

### 6.5. Cấp quyền và credential theo phiên

Có thể kết hợp credential có hạn, binding tạm thời và proxy kiểm soát. Cần quản lý cả:

- Quyền được mở phiên mới.
- Thời hạn credential.
- Khả năng refresh.
- Binding đang tồn tại.
- Stream đang mở.
- Quyền hiệu lực được cấp từ nơi khác.

Một credential ngắn hạn nhưng được refresh tự động không giới hạn sau khi nhiệm vụ kết thúc chưa đáp ứng vòng đời JIT mong muốn.

## 7. Chọn đường kết nối phù hợp

### 7.1. Truy cập trực tiếp với quyền tạm thời

Người dùng nhận credential có hạn và gọi API server trực tiếp.

Ưu điểm có thể là phù hợp công cụ hiện có và ít thành phần trên đường truyền. Tuy nhiên, cần hiểu khả năng ghi lại phiên, giới hạn thời gian và ngắt stream đang mở.

Không hứa có recording hoặc kiểm soát lệnh nếu kiến trúc chỉ cấp RoleBinding rồi trả kubeconfig.

### 7.2. Qua gateway hoặc broker PAM

~~~text
Người dùng
    |
    v
Gateway PAM: xác thực + grant + kiểm tra đích
    |
    v
Kiểm soát phiên / recorder
    |
    v
API server: xác thực và cấp quyền Kubernetes
    |
    v
Kubelet / runtime
    |
    v
Container đích
~~~

Gateway có thể phục vụ kiểm tra theo nhiệm vụ, quản lý thời gian và ghi luồng nếu sản phẩm thực sự hỗ trợ. Những khả năng này phải được kiểm thử trên cả đường tương tác và không tương tác.

Một gateway chỉ cấp credential rồi để client kết nối trực tiếp không tự nhìn thấy nội dung stream.

### 7.3. Tránh đường bỏ qua gateway

Nếu mục tiêu yêu cầu mọi exec qua recorder, cần kiểm tra:

- Người dùng có credential khác cho phép exec trực tiếp không?
- API endpoint có thể được gọi ngoài đường quản lý không?
- Một nhóm rộng vẫn có quyền tương đương không?
- Có kubeconfig cũ hoặc ServiceAccount dùng chung không?
- Có đường truy cập node, kubelet hoặc runtime riêng không?
- Công cụ khác có mở cùng subresource mà không qua gateway không?

Không cần áp một kiến trúc mạng duy nhất cho mọi cluster. Nhưng phải chứng minh đường ngoài quy trình không phá vỡ bảo đảm đang tuyên bố.

### 7.4. Broker là tài sản có đặc quyền

Broker cần quyền đủ để cấp hoặc thực hiện phiên được duyệt, nhưng không nên có quyền tự do trên mọi cluster chỉ vì thuận tiện.

Nếu dùng impersonation hoặc cơ chế đại diện, cần giới hạn principal và phạm vi mà broker được đại diện. Không coi header danh tính do client gửi là bằng chứng.

Audit cần giữ được người yêu cầu, principal broker và danh tính hiệu lực, thay vì chỉ ghi một ServiceAccount chung cho mọi người.

## 8. JEA và giới hạn lệnh

### 8.1. RBAC không phải bộ lọc lệnh shell

Kubernetes RBAC có thể cho phép pods/exec, nhưng không quyết định danh sách lệnh được gõ bên trong shell. Quyền API và policy lệnh là hai lớp khác nhau. [Bảo vệ hoạt động debugging production](https://kubernetes.io/blog/2026/03/18/securing-production-debugging-in-kubernetes/).

Nếu yêu cầu chỉ cho phép một chẩn đoán cụ thể, cân nhắc:

- Công cụ chẩn đoán có API hẹp.
- Một thao tác một lần với executable và đối số được xác minh.
- Job vận hành được quản lý riêng.
- Gateway hiểu và kiểm soát hành động theo khả năng thực tế.
- Môi trường chẩn đoán tách khỏi dữ liệu production khi phù hợp.

Không ghi “read-only exec” chỉ vì người dùng hứa không sửa gì.

### 8.2. Allowlist chuỗi lệnh dễ sai

Chỉ cho phép tên một chương trình chưa đủ nếu chương trình đó có thể:

- Chạy shell hoặc chương trình con.
- Đọc tệp bất kỳ.
- Ghi tệp hoặc mở kết nối mạng.
- Nạp script, plugin hoặc cấu hình do người dùng kiểm soát.
- Diễn giải biểu thức có khả năng thực thi.

Nếu đưa shell vào danh sách cho phép, việc chỉ kiểm tra lệnh khởi tạo thường không giới hạn được mọi hành động tiếp theo.

Policy nên mô tả năng lực cần cho công việc và điểm thực thi phù hợp. Kiểm tra đối số phải theo ngữ nghĩa chương trình, không chỉ ghép chuỗi hoặc chặn một vài ký tự.

### 8.3. Quyền đọc vẫn có tác động

Một lệnh đọc có thể xuất credential, dữ liệu khách hàng hoặc thông tin nội bộ ra terminal. Bản recording sau đó trở thành bản sao nhạy cảm.

Không để người dùng chạy lệnh in toàn bộ môi trường hoặc toàn bộ filesystem chỉ để kiểm tra một tham số. Ưu tiên chẩn đoán có đầu ra tối thiểu cần thiết.

### 8.4. Hardening container hỗ trợ giảm tác động

Cần đánh giá danh tính tiến trình, capabilities, privilege escalation, mount, hệ thống tệp và các ranh giới runtime phù hợp. Pod Security Standards mô tả các mức kiểm soát đối với cấu hình Pod; chúng không thay thế kiểm soát ai được mở phiên và phiên được dùng vì mục đích gì. [Pod Security Standards](https://kubernetes.io/docs/concepts/security/pod-security-standards/).

Một container không chạy root vẫn có thể đọc dữ liệu hoặc dùng credential mà tài khoản ứng dụng được phép tiếp cận. Không coi non-root là cơ chế bảo đảm mọi thao tác exec đều vô hại.

## 9. Audit API và recording phiên

### 9.1. Ba nguồn bằng chứng khác nhau

| Nguồn | Có thể giúp biết | Không nên mặc định có |
| --- | --- | --- |
| API audit | Principal, đích, subresource, ngữ cảnh và kết quả request theo cấu hình | Toàn bộ nội dung gõ trong shell |
| Stream recording | Dữ liệu vào/ra mà recorder quan sát được | Mọi tiến trình nền và tác động ngoài luồng |
| Runtime telemetry | Process, syscall hoặc hoạt động được sensor hỗ trợ | Danh tính người khởi tạo nếu chưa có chuỗi tương quan |

Một log API ghi lệnh khởi tạo sh chưa phải lịch sử mọi lệnh tiếp theo. Một video terminal cũng chưa chứng minh mọi tác động của tiến trình trong container.

### 9.2. Giới hạn của API audit

Kubernetes audit có các mức Metadata, Request và RequestResponse cùng các stage của request. Metadata không ghi request hoặc response body; policy được đánh giá theo quy tắc khớp đầu tiên. Việc chọn mức cao hơn không nên được hiểu là tự có một terminal recorder. [Kubernetes Auditing](https://kubernetes.io/docs/tasks/debug/debug-cluster/audit/).

Cần kiểm thử các trường thực tế thu được cho phiên exec trên cluster mục tiêu. Đừng suy ra độ bao phủ chỉ từ tên audit level.

### 9.3. Fragment policy minh họa

~~~yaml
- level: Metadata
  resources:
    - group: ""
      resources:
        - "pods/exec"
~~~

Đây chỉ là một phần tử rules cần tích hợp vào policy đang quản lý, không phải policy đầy đủ để thay thế cấu hình toàn cluster.

Không giới hạn rule vào một verb duy nhất nếu mục tiêu là thu mọi đường exec đã được cluster hỗ trợ. Cần xét thứ tự rule để một rule trước đó không loại bỏ sự kiện quan trọng.

Metadata không đồng nghĩa dữ liệu hoàn toàn không nhạy cảm. URI, tên tài nguyên hoặc đối số ban đầu có thể mang thông tin không nên công khai. Tránh đưa secret trực tiếp vào đối số của lệnh.

### 9.4. Nối audit với nội dung trong container

Để nối hành vi runtime với người gọi, cần cơ chế tương quan thật. Gần nhau về thời gian và cùng tên Pod chưa đủ khi nhiều phiên cùng tồn tại.

Các thiết kế Kubernetes về truyền audit ID cho exec cũng nhấn mạnh khoảng trống giữa danh tính tại API server và telemetry runtime. Khả năng hỗ trợ phải được xác minh theo phiên bản và thành phần đã triển khai, không mặc định mọi cluster đều có. [Thiết kế exec session identity propagation](https://www.k8s.dev/resources/keps/6035/).

Trong vận hành, nên ghi nhận mức tin cậy của phép nối: trực tiếp theo định danh, theo quy tắc có giả định, hoặc chưa liên kết được.

### 9.5. Recording phải bao phủ các chế độ cần quản lý

Kiểm thử riêng:

- TTY và không TTY.
- Có stdin và không stdin.
- Lệnh một lần và shell.
- Kết nối lại.
- Client khác nhau.
- Giao thức streaming được hỗ trợ.
- Luồng có dữ liệu nhị phân.
- Phiên có nhiều kênh đầu ra.

Không coi một demo ghi shell trên trình duyệt là bằng chứng mọi request exec đều được ghi đầy đủ.

Nếu yêu cầu recording là bắt buộc, cần định nghĩa hành vi khi recorder không khởi tạo được hoặc ngừng hoạt động giữa phiên.

## 10. Bằng chứng tối thiểu cho một phiên

### 10.1. Trước khi mở

- Danh tính đã xác thực.
- Mã công việc và grant.
- Quyết định policy hoặc phê duyệt.
- Cluster, namespace, Pod và container.
- UID Pod và thông tin đích tại thời điểm kiểm tra.
- Quyền hiệu lực và phương thức cấp.
- Thời hạn và yêu cầu recording.

### 10.2. Trong phiên

- Session ID.
- Principal hiệu lực.
- Thời điểm mở.
- Các audit ID có thể liên kết.
- Trạng thái recorder.
- Thay đổi đích hoặc lỗi kết nối.
- Hành động quan trọng mà nguồn quan sát được.
- Quyết định gia hạn hoặc thu hồi.

### 10.3. Khi kết thúc

- Thời điểm và lý do kết thúc.
- Stream đã đóng hay chỉ mất kết nối client.
- Trạng thái quyền mở phiên mới.
- Cleanup binding và credential.
- Vị trí bản ghi cùng kiểm tra toàn vẹn phù hợp.
- Tác động còn tồn tại cần xử lý.
- Kết quả hậu kiểm và ngoại lệ.

Ví dụ sự kiện PAM chuẩn hóa:

~~~json
{
  "event": "kubernetes_exec_session_closed",
  "sessionId": "session-019",
  "grantId": "GRANT-2841",
  "requester": "operator-017",
  "clusterId": "cluster-lab-01",
  "namespace": "billing-lab",
  "podName": "billing-api-7c89d6f4b5-k9m2q",
  "podUid": "pod-uid-example-019",
  "containerName": "app",
  "closeReason": "grant_expired",
  "streamState": "closed",
  "newExecAccess": "denied_verified",
  "recordingState": "stored",
  "cleanupState": "verified"
}
~~~

Đây là sự kiện nghiệp vụ đề xuất của PAM, không phải record Kubernetes nguyên bản. Chỉ điền các trạng thái verified khi đã có kiểm tra tương ứng.

## 11. Thu hồi và ngắt phiên đang mở

### 11.1. Những việc khác nhau cần được quản lý riêng

~~~text
Ngăn mở phiên mới
    khác với
Đóng stream đang tồn tại
    khác với
Dừng tiến trình và xử lý tác động đã tạo
~~~

Xóa binding hoặc hết hạn credential không nên được coi là bảo đảm stream đã thiết lập sẽ lập tức bị ngắt. Cần kiểm thử hành vi của stack và có thành phần quản lý kết nối nếu chính sách yêu cầu ngắt theo thời gian.

### 11.2. Giới hạn thời gian ở đúng điểm

Có thể cần:

- Hạn grant tại hệ thống PAM.
- Hạn credential.
- Hạn thời gian phiên tại gateway.
- Idle timeout phù hợp.
- Cơ chế chặn refresh.
- Controller dọn binding.
- Cảnh báo cleanup thất bại.

Một annotation expires-at chỉ mô tả ý định nếu không có thành phần thực thi. Một token hết hạn chỉ giải quyết một phần vòng đời truy cập.

### 11.3. Đóng stream không tự hoàn tác mọi hành động

Trong phiên, người dùng có thể đã:

- Thay đổi tệp trên volume.
- Khởi động tác vụ.
- Gửi dữ liệu ra ngoài.
- Tạo kết nối tới hệ thống khác.
- Sử dụng credential của workload.
- Làm thay đổi dữ liệu ứng dụng.

Không mặc định mất terminal sẽ dừng mọi process hoặc hoàn tác tác động. Cần kiểm tra và xử lý theo phạm vi sự cố.

Việc restart hoặc thay Pod cũng không tự sửa dữ liệu đã ghi vào persistent volume hoặc credential đã bị sao chép. Quyết định phục hồi phải dựa trên tác động thực tế.

### 11.4. Không coi xóa Pod là nút logout mặc định

Xóa Pod production có thể gây gián đoạn và không giải quyết mọi tác động ngoài Pod.

Thiết kế cần có đường ngắt phù hợp với hệ thống quản lý phiên. Nếu biện pháp ứng phó cần thay hoặc dừng workload, phải thực hiện theo runbook có đánh giá tác động và quyền tương ứng.

### 11.5. Kiểm tra quyền còn lại

Sau thu hồi, kiểm tra:

- Principal có nhận credential mới được không?
- Có mở exec mới tới cùng hoặc Pod khác không?
- Binding tạm đã được dọn đúng đối tượng chưa?
- Có quyền rộng từ nhóm hoặc binding khác không?
- Gateway có tự mở lại stream không?
- Phiên hoặc tiến trình cũ còn hoạt động không?

Thu hồi một binding không đủ nếu principal vẫn có khả năng tương đương từ nơi khác.

## 12. Các đường quyền tương đương cần kiểm kê

### 12.1. Sửa hoặc tạo workload

Quyền tạo hay sửa workload có thể tạo đường tiếp cận tài nguyên và danh tính khác trong namespace. Tài liệu thực hành RBAC của Kubernetes nhấn mạnh rủi ro từ workload dùng ServiceAccount, mount Secret và các tài nguyên liên quan. [Thực hành tốt cho Kubernetes RBAC](https://kubernetes.io/docs/concepts/security/rbac-good-practices/).

Vì vậy, một người bị cấm exec nhưng vẫn sửa được image, command hoặc workload có đặc quyền có thể còn khả năng gây tác động tương đương hoặc rộng hơn.

### 12.2. Đường ngoài API exec đang quản lý

Cần xem xét riêng quyền:

- Truy cập node.
- Truy cập kubelet hoặc runtime.
- Dùng debug container.
- Attach.
- Port-forward.
- Tạo job có khả năng đọc cùng volume.
- Sửa công cụ quản trị hoặc gateway.
- Quản trị RBAC và cơ chế xác thực.

Không phải mọi môi trường đều có mọi đường. Inventory phải dựa vào cấu hình thật, không suy ra từ một danh sách lệnh chuẩn.

### 12.3. Break-glass

Nếu cần quyền exec khẩn cấp khi PAM chính bị lỗi:

- Dùng danh tính riêng, không dùng tài khoản chung không truy vết.
- Xác định điều kiện kích hoạt.
- Giới hạn cluster và thời gian theo khả năng.
- Lưu bằng chứng ở đường độc lập phù hợp.
- Thu hồi và đối soát sau sử dụng.
- Kiểm thử định kỳ.

Break-glass không nên trở thành đường thường trực để tránh phê duyệt hoặc recording.

## 13. Kiểm tra quyền và hành vi trong lab

### 13.1. Xác nhận context và Pod

Trước khi thử, kiểm tra kubeconfig đang nhắm đúng cluster và namespace. Có thể xem UID Pod lab bằng lệnh chỉ đọc:

~~~sh
kubectl --context lab-pam -n billing-lab get pod billing-api-7c89d6f4b5-k9m2q -o jsonpath='{.metadata.uid}'
~~~

Đối chiếu kết quả với đích đã được duyệt. Đây là kiểm tra trước thao tác, không tự khóa UID cho request tiếp theo.

### 13.2. Kiểm tra authorization

kubectl auth can-i hỗ trợ kiểm tra hành động, resource và subresource. Nó giúp kiểm tra quyền API, nhưng không thay thế thử kết nối thật và kiểm tra các lớp PAM khác. [Tham chiếu kubectl auth can-i](https://kubernetes.io/docs/reference/kubectl/generated/kubectl_auth/kubectl_auth_can-i/).

Ví dụ:

~~~sh
kubectl --context lab-pam -n billing-lab auth can-i create pods/billing-api-7c89d6f4b5-k9m2q --subresource=exec
~~~

Thử thêm Pod khác để xác nhận ranh giới theo tên nếu đó là thiết kế được chọn.

Không dùng tài khoản quản trị rộng để kiểm thử rồi suy ra người dùng bị giới hạn cũng có hành vi như vậy. Nếu dùng impersonation trong kiểm thử của quản trị viên, phải hiểu quyền impersonate và bảo đảm ngữ cảnh phản ánh đúng subject cần thử.

### 13.3. Kiểm thử end-to-end

Sau kiểm tra quyền, thử lệnh lành tính trên container lab có công cụ tương ứng. Xác minh:

- Quyết định cấp quyền.
- Đúng Pod và container.
- Stream hoạt động.
- Audit được thu.
- Recording đúng chế độ nếu bắt buộc.
- Kết thúc và cleanup.

Một kết quả yes từ can-i không chứng minh recorder hoạt động hoặc không có đường bypass.

## 14. Ma trận kiểm thử nghiệm thu

| Tình huống | Kết quả mong đợi |
| --- | --- |
| Grant hợp lệ, đúng đích, đủ điều kiện | Mở phiên trong phạm vi thiết kế |
| Không có grant nhưng gọi gateway | Từ chối |
| Principal gọi API trực tiếp ngoài đường bắt buộc | Bị chặn theo mô hình truy cập |
| Đổi namespace | Không mở phiên ngoài phạm vi |
| Đổi Pod name | Bị giới hạn theo RBAC hoặc policy thực thi |
| Pod cùng tên nhưng UID đã đổi | Xử lý theo policy đích, không tự coi vẫn là đối tượng cũ |
| Chọn container khác trong cùng Pod | Bị kiểm soát tại lớp được thiết kế, không quy cho RBAC theo Pod |
| Dùng client hoặc giao thức streaming khác | Vẫn đáp ứng authorization và recording đã yêu cầu |
| Grant hết hạn trước khi mở | Không cấp hoặc mở phiên mới |
| Grant hết hạn khi đang có stream | Gateway thực thi hành vi kết thúc đã công bố |
| Xóa binding trong khi phiên đang mở | Kiểm tra riêng phiên mới và stream cũ |
| Recorder không khởi tạo được | Thực hiện đúng policy bắt buộc hoặc ngoại lệ đã định |
| Mất recorder giữa phiên | Có hành vi xử lý và bằng chứng trạng thái rõ |
| Chạy lệnh không TTY | Không bỏ sót chỉ vì không phải terminal tương tác |
| Hai người cùng vào một Pod | Không nối nhầm audit và recording |
| Pod hoặc container restart | Không tự nối sang đích mới ngoài điều kiện |
| Principal có binding rộng khác | Phát hiện quyền hiệu lực vượt thiết kế |
| Người dùng ngắt mạng | Phân biệt client mất kết nối với cleanup đã hoàn tất |

Lỗi do thiếu executable, container chưa chạy hoặc kết nối mạng không chứng minh authorization đã từ chối đúng yêu cầu. Mỗi phép thử âm tính cần xác định nguyên nhân thất bại mong đợi.

## 15. Bài thực hành: phiên chẩn đoán Billing

### 15.1. Bối cảnh

Billing API gặp lỗi kết nối nội bộ. Nhóm trực ca hiện dùng một kubeconfig chung có quyền exec trong nhiều namespace.

Yêu cầu thay đổi:

- Mỗi phiên truy được tới người cụ thể.
- Chỉ được truy cập container app của Pod đã được duyệt.
- Phiên có thời hạn.
- Không cấp quyền đọc Secret trực tiếp hoặc sửa workload cho nhiệm vụ này.
- Có API audit và recording theo yêu cầu.
- Có cơ chế ngắt stream và xác minh thu hồi.
- Có kế hoạch xử lý khi Pod bị thay thế.

### 15.2. Thiết kế cần nộp

1. Sơ đồ danh tính, gateway và đường API.
2. Schema grant với cluster, namespace, Pod, UID và container.
3. Role và binding phù hợp, kèm giới hạn còn lại.
4. Cơ chế thực thi container và thời hạn phiên.
5. Cách ngăn đường trực tiếp bỏ qua recording.
6. Kế hoạch bảo vệ credential và kubeconfig.
7. Chuỗi audit, recording và tương quan.
8. Runbook thu hồi, ngắt stream và cleanup.
9. Ma trận kiểm thử với kết quả mong đợi.
10. Quy trình break-glass nếu hệ thống chính không dùng được.

### 15.3. Những câu hỏi phải trả lời

- Nếu người dùng đổi tùy chọn container, thành phần nào chặn?
- Nếu Pod bị tạo lại cùng tên, grant xử lý ra sao?
- Nếu người dùng mở hai phiên, hạn và recording áp dụng thế nào?
- Nếu xóa binding nhưng stream vẫn chạy, ai đóng stream?
- Nếu tiến trình trong container còn chạy sau khi stream đóng, cách phát hiện là gì?
- Nếu credential workload có thể đã bị lộ, cần đánh giá và thu hồi ở đâu?
- Nếu kubeconfig chung cũ vẫn tồn tại, quy trình mới có còn bảo đảm gì?

Bài đạt khi mỗi bảo đảm có một điểm thực thi và một phép thử chứng minh. Không được dùng một annotation, tên role hoặc lời hứa của người vận hành thay cho cơ chế kiểm soát.

## 16. Sai lầm thường gặp và cách điều chỉnh

| Sai lầm | Hệ quả | Điều chỉnh |
| --- | --- | --- |
| Cấp cluster-admin để tiện chẩn đoán | Phạm vi vượt xa nhu cầu exec | Dùng quyền hẹp theo nhiệm vụ và kiểm tra quyền hiệu lực |
| Coi exec là quyền chỉ đọc | Có thể thực thi mã và dùng tài nguyên workload | Đánh giá khả năng trong container |
| Chỉ xóa pods/exec khỏi một Role | Quyền có thể còn từ binding khác | Rà soát toàn bộ principal và nhóm |
| Chỉ ghi audit API rồi báo có full session recording | Không có bằng chứng nội dung toàn phiên | Thiết kế recorder và nêu giới hạn |
| Dùng tên Pod làm định danh bền vững | Có thể truy cập đối tượng thay thế | Kiểm tra UID và policy khi đích thay đổi |
| Đặt annotation hết hạn nhưng không có controller | Quyền tạm trở thành quyền tồn đọng | Thực thi cleanup và giám sát lỗi |
| Dùng regex chặn vài lệnh nguy hiểm | Không giới hạn được năng lực shell đầy đủ | Chọn thao tác hẹp và điểm thực thi phù hợp |
| Hết hạn token là báo phiên đã đóng | Stream có thể chưa kết thúc | Quản lý và kiểm thử kết nối hiện hữu |
| Xóa Pod để logout mặc định | Gây gián đoạn và không hoàn tác tác động bên ngoài | Dùng cơ chế ngắt phù hợp và runbook ứng phó |
| Lưu output chứa secret vào recording rộng quyền | Tạo thêm nguồn lộ dữ liệu | Hạn chế đầu ra và bảo vệ bản ghi |

## 17. Chỉ số vận hành

Các chỉ số có ích:

- Số principal còn quyền exec thường trực.
- Tỷ lệ phiên nối được với người hoặc workload và grant.
- Tỷ lệ phiên có đích cụ thể được xác minh.
- Số lần mở ngoài đường bắt buộc.
- Tỷ lệ recording thành công theo chế độ phiên.
- Số phiên không rõ trạng thái sau gián đoạn.
- Thời gian từ quyết định thu hồi tới khi không mở được phiên mới.
- Thời gian ngắt stream theo policy.
- Số binding tạm chưa được cleanup đúng hạn.
- Tỷ lệ hậu kiểm break-glass hoàn tất.
- Số trường hợp Pod thay thế làm thay đổi đích truy cập.
- Tỷ lệ kiểm thử lại sau thay client, API server hoặc gateway.

Mẫu số và phạm vi cần rõ. “100% exec được ghi” chỉ có ý nghĩa nếu bao gồm cả client, giao thức, chế độ không TTY và các đường kết nối nằm trong bảo đảm.

## 18. Câu hỏi tự kiểm tra

**Không có quyền get Secret thì có thể yên tâm cấp exec không?**

Không. Container có thể đã có dữ liệu hoặc credential mà tiến trình trong đó được phép dùng.

**RBAC theo tên Pod có giới hạn được container và lệnh không?**

Không. Các yêu cầu này cần lớp thực thi khác nếu là ranh giới bắt buộc.

**Có thể luôn dùng một verb cho exec trên mọi cluster không?**

Không nên giả định. Cần đối chiếu client, server, giao thức và feature gate thực tế.

**RequestResponse có phải terminal recorder không?**

Không nên coi như vậy. Phải xác minh dữ liệu thực sự được thu và thiết kế recording riêng cho luồng phiên.

**Annotation thời hạn có làm RoleBinding tự hết hạn không?**

Không. Annotation trong ví dụ chỉ là metadata, cần thành phần thực thi và kiểm tra cleanup.

**Thu hồi quyền mở exec mới có chứng minh stream cũ đã đóng không?**

Không. Phải kiểm tra riêng quyền mới và kết nối đang tồn tại.

**Đóng stream có hoàn tác tệp đã sửa hoặc credential đã sao chép không?**

Không. Tác động cần được điều tra và xử lý riêng.

**Vì sao cần xem cả quyền tạo và sửa workload?**

Chúng có thể tạo đường tiếp cận danh tính, dữ liệu và môi trường thực thi dù đường exec trực tiếp đã bị giới hạn.

Một Kubernetes exec session được quản lý tốt cần có đích rõ ràng, danh tính riêng, quyền vừa đủ, vòng đời phiên được thực thi và bằng chứng đúng với khả năng quan sát. Trong PAM, RBAC là một phần của ranh giới đó; kiểm soát stream, credential, dữ liệu trong container và đường truy cập tương đương quyết định phần còn lại.
