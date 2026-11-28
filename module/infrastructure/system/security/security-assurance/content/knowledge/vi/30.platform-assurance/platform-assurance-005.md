# Runtime isolation: Cô lập workload khi thực thi và kiểm chứng bằng chứng

## Mục tiêu học tập

Sau bài này, người học có thể:

1. Giải thích **runtime isolation** là gì, những ranh giới tin cậy nào cần được bảo vệ khi ứng dụng đang chạy và vì sao cách ly là một phần của **platform assurance**.
2. Phân biệt cô lập bằng tiến trình, Linux namespaces, cgroups, capabilities, seccomp, cơ chế kiểm soát truy cập bắt buộc (MAC), container, sandbox và máy ảo.
3. Thiết kế chính sách cô lập theo mô hình đe dọa của workload, đặc biệt trên nền tảng Kubernetes có nhiều nhóm hoặc nhiều tenant.
4. Xây dựng các phép kiểm chứng, bao gồm thử nghiệm hành vi bị từ chối, để chứng minh cấu hình mong muốn thực sự được thực thi.
5. Gắn kết **security claim → control → test → evidence → owner → thời hạn hiệu lực** thành hồ sơ assurance có thể rà soát và kiểm toán.

## 1. Runtime isolation trong security assurance

**Runtime isolation** là tập hợp các ranh giới và cơ chế kiểm soát nhằm giới hạn những gì một workload đang thực thi có thể **nhìn thấy, truy cập, thay đổi và tiêu thụ**, kể cả khi workload bị lỗi hoặc bị xâm nhập. Workload có thể là một tiến trình, container, pod, máy ảo, hàm serverless hoặc mã do người dùng cung cấp.

Câu hỏi trung tâm không chỉ là “ứng dụng có chạy trong container không?”, mà là:

> Nếu kẻ tấn công kiểm soát tiến trình này, họ có thể đi xa đến đâu, đụng tới dữ liệu nào, ảnh hưởng đến workload nào và liệu nền tảng có bằng chứng để khẳng định giới hạn đó đang được áp dụng không?

Trong mô-đun **SECURITY_SECURITY_ASSURANCE**, runtime isolation liên kết mục tiêu bảo mật và phân tích rủi ro với các security controls, kiểm thử, audit và khắc phục phát hiện. Một tuyên bố như “workload A bị cô lập với workload B” chỉ có giá trị assurance khi xác định được **ranh giới**, **đối tượng được bảo vệ**, **cơ chế thực thi**, **phép thử** và **bằng chứng có thời điểm**.

### 1.1. Những thuộc tính cần bảo vệ

| Thuộc tính | Mục tiêu cô lập tại runtime | Ví dụ thất bại |
|---|---|---|
| **Confidentiality** (bí mật) | Tiến trình chỉ đọc được dữ liệu, secrets, thông tin hệ thống đã được cấp phép. | Container A đọc token hoặc volume của tenant B. |
| **Integrity** (toàn vẹn) | Workload không thể sửa mã, cấu hình, bộ nhớ hoặc tài nguyên của workload khác hay host trái phép. | Pod bị xâm nhập ghi vào hệ thống tệp của node qua hostPath. |
| **Availability** (sẵn sàng) | Sự cố hoặc quá tải từ một workload không làm cạn kiệt tài nguyên chung ngoài mức chấp nhận. | Một tiến trình tạo quá nhiều tiến trình con làm node thiếu PID. |
| **Accountability** (truy vết) | Hành vi, thay đổi cấu hình và ngoại lệ có chủ sở hữu, được ghi nhận đủ để điều tra. | Workload chạy đặc quyền nhưng không có lịch sử phê duyệt hoặc sự kiện thay đổi. |

Không có một cơ chế đơn lẻ nào bảo đảm đồng thời mọi thuộc tính. Chẳng hạn, **cgroups** chủ yếu phân bổ/giới hạn tài nguyên; cgroups tự thân không tạo ranh giới bí mật dữ liệu. **NetworkPolicy** giới hạn lưu lượng mạng được hỗ trợ nhưng không bảo vệ tệp được mount chung.

### 1.2. Phạm vi assurance

Cần phân biệt ba loại câu hỏi:

- **Thiết kế:** Kiến trúc quy định workload được phép truy cập tài nguyên nào? Ranh giới có phù hợp với mức tin cậy của mã và dữ liệu không?
- **Cấu hình:** Deployment, image, runtime, kernel, chính sách mạng, quyền truy cập và admission policy có hiện thực hóa thiết kế không?
- **Hiệu lực thực tế:** Trong một workload đang chạy, các thao tác trái phép có bị chặn không? Nền tảng có phát hiện sai lệch và duy trì giới hạn khi thay đổi hoặc xảy ra sự cố không?

Một file YAML “đúng” là **bằng chứng cấu hình**, chưa phải bằng chứng hoàn chỉnh cho **kết quả cô lập**.

## 2. Bắt đầu từ ranh giới tin cậy và mô hình đe dọa

Trước khi lựa chọn container hay VM, hãy trả lời:

1. **Đối tượng cần bảo vệ:** dữ liệu khách hàng, secret, hệ điều hành host, control plane, workload lân cận, dung lượng CPU/RAM/I/O hay mạng nội bộ?
2. **Đối tượng có thể gây hại:** mã từ bên thứ ba, người dùng cuối, đối tác, nhân sự vận hành, tenant khác hoặc tiến trình ứng dụng đã bị xâm nhập?
3. **Điểm giao nhau:** cùng process, cùng pod, cùng kernel, cùng node, cùng cluster, cùng tài khoản đám mây hoặc cùng mạng?
4. **Khả năng tác động cần chặn:** đọc tệp, gọi API control plane, mở kết nối mạng, gọi syscall nguy hiểm, tăng đặc quyền, làm cạn tài nguyên hoặc thoát khỏi môi trường thực thi?
5. **Giới hạn tin cậy:** giả định kernel, hypervisor và thành phần quản trị nào vẫn đáng tin? Ai có quyền thay đổi cấu hình giới hạn đó?

Ví dụ: dịch vụ phân tích dữ liệu chạy mã Python do người dùng tải lên cần mức cô lập cao hơn một API nội bộ chỉ chạy mã đã ký và được kiểm thử. Với mã không đáng tin cậy, chia sẻ kernel giữa các tenant là một quyết định kiến trúc có rủi ro, dù mỗi tenant nằm trong container riêng.

### 2.1. Ví dụ ranh giới

~~~mermaid
flowchart LR
    Client["Người dùng"] --> Gateway["API Gateway"]
    Gateway --> App["Workload ứng dụng"]
    App --> Data["Kho dữ liệu được phép"]
    Other["Workload khác"] --> Policy["Chính sách mạng và danh tính"]
    Policy --> App
    App --> Runtime["Container runtime / Kernel"]
    Runtime --> Host["Node / Tài nguyên vật lý"]
    Control["Control plane"] --> Policy
~~~

Mỗi mũi tên trong sơ đồ biểu thị một quan hệ cần đánh giá quyền truy cập, không mặc nhiên nghĩa là được cho phép. Cần chỉ rõ ranh giới giữa **workload với workload**, **workload với host**, **data plane với control plane** và **tenant với tenant**.

### 2.2. Mô tả một “hợp đồng cô lập”

Một hợp đồng cô lập (isolation contract) nên có cấu trúc:

- **Chủ thể:** workload nào, danh tính dịch vụ nào, namespace/tenant nào.
- **Tài nguyên:** các đường dẫn tệp, volume, API, endpoint, node, CPU/RAM/PID hoặc secret cần bảo vệ.
- **Quyền được phép:** chỉ những thao tác thiết yếu, theo nguyên tắc đặc quyền tối thiểu.
- **Quyền phải bị chặn:** quyền cụ thể được chuyển thành phép thử âm tính (negative test).
- **Giả định và ngoại lệ:** ví dụ runtime chia sẻ kernel với node, CNI hỗ trợ NetworkPolicy, có dịch vụ DNS cần thiết, cần thư mục tạm có thể ghi.
- **Trách nhiệm và chứng cứ:** ai sở hữu policy, ai kiểm tra, thu thập log nào và khi nào phải kiểm tra lại.

Không thể kiểm chứng phát biểu mơ hồ “workload an toàn”. Có thể kiểm chứng phát biểu cụ thể “container của dịch vụ xử lý hóa đơn không có đặc quyền host, không nhận service-account token không cần thiết và không thể kết nối trực tiếp tới database của tenant khác trong phạm vi kịch bản kiểm thử”.

## 3. Các lớp cô lập và giới hạn thực tế

### 3.1. Cơ chế trên Linux

| Cơ chế | Kiểm soát chính | Giới hạn cần nhớ |
|---|---|---|
| **Process isolation, UID/GID và quyền tệp** | Tách không gian địa chỉ tiến trình, áp quyền truy cập người dùng và nhóm. | Quyền sai hoặc tiến trình có đặc quyền có thể phá vỡ dự kiến. |
| **Namespaces** (PID, mount, network, IPC, UTS, user, cgroup, time) | Tạo các góc nhìn hệ thống khác nhau: PID, mount, mạng, người dùng… | Vẫn dùng chung kernel; một số namespace được chia sẻ theo thiết kế; namespace không thay thế phân quyền. |
| **cgroups** | Giới hạn và phân bổ CPU, bộ nhớ, PIDs, I/O tùy cấu hình/nền tảng. | Chủ yếu bảo vệ tài nguyên; không tự chặn đọc secret hoặc syscall. |
| **Linux capabilities** | Chia nhỏ đặc quyền vốn thường gắn với root. | Giữ capability không cần thiết làm tăng tác động khi bị xâm nhập; bỏ capability không có nghĩa loại bỏ mọi đường tấn công. |
| **seccomp** | Lọc syscall của tiến trình bằng chính sách kernel. | Chỉ chặn các syscall được policy bao phủ; cấu hình mặc định phụ thuộc container runtime. |
| **SELinux/AppArmor** (MAC) | Áp chính sách bắt buộc lên thao tác với đối tượng/hành vi dù quyền UID/GID cho phép. | Hiệu lực phụ thuộc kernel, profile, chế độ enforcement và cấu hình node. |
| **User namespaces/rootless** | Ánh xạ UID/GID để giảm đặc quyền của tiến trình trong quan hệ với host. | Không đồng nghĩa có hypervisor; không tự bảo vệ toàn bộ tài nguyên mạng hay bí mật. |
| **Read-only root filesystem và mount policy** | Hạn chế ghi vào filesystem gốc và giới hạn vùng lưu trữ được mount. | Volume gắn vào có thể vẫn ghi được; cần đánh giá riêng các mount và secret. |
| **Network namespace, firewall, NetworkPolicy** | Giới hạn giao tiếp và sự hiển thị của các giao diện/luồng mạng. | Tùy cấu hình mạng, CNI, lưu lượng hệ thống và ngoại lệ; không thay thế IAM. |

**Container thông thường** kết hợp nhiều cơ chế trên nhưng vẫn **chia sẻ kernel của host**. Một tiến trình có thể là root trong container; điều đó không tự động khiến nó là root trên host, song rủi ro tùy user namespace, capabilities, mount và runtime thực tế. Vì thế không được coi việc có container là bằng chứng cô lập đủ mạnh cho mã không tin cậy.

### 3.2. Container, sandbox và VM

| Hình thức thực thi | Ranh giới chủ yếu | Trường hợp phù hợp | Cần đánh giá khi assurance |
|---|---|---|---|
| **Container chung kernel** | Namespace, quyền, LSM, seccomp và chính sách runtime trên một kernel. | Ứng dụng nội bộ đã kiểm soát mã, phân vùng dịch vụ thông thường. | Cấu hình đặc quyền, host mount, syscall, patch kernel, mức độ tin cậy các workload cùng node. |
| **Container sandbox với lớp trung gian** | Một lớp xử lý syscall hoặc cô lập bổ sung tùy runtime, ví dụ gVisor. | Workload có rủi ro cao cần thêm ranh giới. | Phạm vi syscall được trung gian hóa, tương thích ứng dụng, hiệu năng, cấu hình thực tế và giả định tin cậy. |
| **VM/microVM** | Kernel khách được cách ly bởi hypervisor. | Mã không đáng tin cậy, ranh giới tenant mạnh hơn, yêu cầu giảm chia sẻ kernel host. | Cô lập hypervisor, thiết bị ảo, đường quản trị, patching, quyền truy cập mạng/lưu trữ, rủi ro escape vẫn còn. |
| **Node/cluster riêng** | Phân tách hạ tầng và mặt quản trị theo kiến trúc. | Mức rủi ro cao hoặc yêu cầu phân vùng vận hành. | Control plane, IAM, mạng, bí mật, vị trí lưu trữ và quyền admin có thực sự tách hay không. |

Kết luận thiết kế phải dựa trên **mã có đáng tin cậy hay không, mức độ nhạy cảm của dữ liệu và hậu quả khi ranh giới bị vượt qua**. Sandbox/VM thường tăng mức cô lập nhưng không miễn trừ quản trị lỗ hổng, IAM và giám sát.

### 3.3. Ranh giới pod trong Kubernetes

Trong Kubernetes, các container thuộc **cùng một pod** thường chia sẻ **network namespace**, địa chỉ IP và cổng mạng; chúng cũng có thể chia sẻ các volume được cấu hình cho pod. Không nên dùng hai container trong cùng pod làm ranh giới tenant độc lập.

Pod trên cùng node thường chia sẻ kernel node nếu dùng container runtime thông thường. Việc tách bằng namespace Kubernetes là cơ chế phân nhóm tài nguyên và RBAC/policy; **namespace Kubernetes tự nó không tạo ranh giới bảo mật cấp VM**.

Một container có cấu hình tốt vẫn có thể bị ảnh hưởng bởi:

- Container đặc quyền trên cùng node, hostPath nhạy cảm hoặc socket của container runtime bị mount vào workload khác.
- Service account có quyền quá rộng, ví dụ đọc secret của nhiều namespace hoặc tạo pod đặc quyền.
- Chính sách mạng thiếu egress restriction hoặc được CNI thực thi không như giả định.
- Rủi ro kernel/container runtime/hypervisor, tài khoản node, hệ thống log và đường quản trị.

## 4. Các đường phá vỡ cô lập thường gặp

| Đường rủi ro | Ví dụ | Control cần đánh giá | Tín hiệu/bằng chứng |
|---|---|---|---|
| **Mở rộng đặc quyền lên host** | Container chạy privileged, giữ nhiều capability, bật hostPID hoặc mount thư mục hệ thống. | Chặn privileged và host namespace, loại capability dư, giới hạn hostPath, admission policy. | PodSpec hiện tại, kết quả admission, runtime metadata, kiểm tra mount/namespace. |
| **Di chuyển ngang giữa workload** | Ứng dụng bị chiếm quyền gọi trực tiếp endpoint nội bộ không cần thiết. | NetworkPolicy/segmentation, identity và authorization ở service đích. | Policy hiện hành, phép thử kết nối cho phép/từ chối, audit truy cập dịch vụ. |
| **Rò rỉ secret** | Token service account hoặc secret mount sẵn trong container không cần dùng. | Tắt tự động mount, cấp quyền tối thiểu, quản trị bí mật và vòng đời. | Manifest, service-account RBAC, kiểm tra mount và audit truy xuất. |
| **Ghi sửa trạng thái hệ thống** | Workload ghi vào filesystem gốc, hostPath hoặc volume của tenant khác. | Read-only rootfs, mount allowlist, quyền tệp, MAC. | Trạng thái mount, thử ghi trái phép có kiểm soát, hồ sơ volume. |
| **Cạn kiệt tài nguyên** | Fork bomb, memory spike, ghi quá nhiều dữ liệu tạm. | Giới hạn bộ nhớ/CPU/PID/I/O khi được hỗ trợ, quota và giám sát. | Runtime resource limits, metrics, sự kiện OOM/eviction, phép thử tải. |
| **Vượt ranh giới kernel/runtime** | Lỗ hổng ở thành phần hệ thống cho phép container escape. | Vá kernel/runtime, giảm syscall, sandbox/VM cho workload tin cậy thấp, phát hiện hành vi. | Inventory phiên bản, lịch vá, bản đánh giá lỗ hổng, runtime alerts. |
| **Sai lệch giữa ý định và runtime** | Manifest đã hardened nhưng workload đang chạy tạo từ template cũ. | Policy-as-code, admission enforcement, drift detection, thu thập bằng chứng runtime. | Desired-state commit và observed-state snapshot cùng định danh deployment. |

Đối với mỗi hàng, nhóm assurance cần xác định **failure mode có thể kiểm chứng**, thay vì chỉ đánh dấu một control là “đã bật”.

## 5. Thiết kế cấu hình tối thiểu đặc quyền

Xét dịch vụ nội bộ **risk-api** trong namespace **platform-prod**: ứng dụng chỉ cần nhận HTTP trên cổng 8080 từ gateway cùng namespace, truy vấn DNS và ghi tệp tạm trong thư mục **/tmp**. Dịch vụ không cần Kubernetes API, không cần quyền root và không cần tương tác với host.

Một Deployment minh họa:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: risk-api
  namespace: platform-prod
spec:
  replicas: 2
  selector:
    matchLabels:
      app: risk-api
  template:
    metadata:
      labels:
        app: risk-api
    spec:
      automountServiceAccountToken: false
      hostNetwork: false
      hostPID: false
      hostIPC: false
      securityContext:
        runAsNonRoot: true
        seccompProfile:
          type: RuntimeDefault
      containers:
        - name: api
          image: registry.example.com/risk-api:1.4.2
          ports:
            - containerPort: 8080
          securityContext:
            runAsUser: 10001
            runAsGroup: 10001
            allowPrivilegeEscalation: false
            privileged: false
            readOnlyRootFilesystem: true
            capabilities:
              drop: ["ALL"]
          resources:
            requests:
              cpu: "100m"
              memory: "128Mi"
            limits:
              cpu: "500m"
              memory: "256Mi"
              ephemeral-storage: "256Mi"
          volumeMounts:
            - name: tmp
              mountPath: /tmp
      volumes:
        - name: tmp
          emptyDir:
            sizeLimit: 64Mi
~~~

Các thuộc tính này thể hiện **ý định cấu hình**:

- **runAsNonRoot** và UID/GID xác định hạn chế danh tính tiến trình; khả năng hoạt động phải phù hợp permission của image và volume.
- **allowPrivilegeEscalation: false** hạn chế tiến trình thu được đặc quyền mới qua các đường mà cơ chế no_new_privs kiểm soát; không phải cam kết rằng mọi lỗ hổng nâng quyền đều bất khả thi.
- **capabilities.drop: ["ALL"]** loại các Linux capabilities mặc định ở container; nếu workload cần một capability, phải có lý do và phạm vi ngoại lệ.
- **seccompProfile: RuntimeDefault** yêu cầu profile seccomp mặc định của runtime. Nội dung profile có thể khác nhau giữa runtime và phiên bản; cần xác minh trên node.
- **readOnlyRootFilesystem** khóa ghi trên filesystem gốc của container; **/tmp** là ngoại lệ có chủ đích, vẫn cần kiểm soát quyền và mức tiêu thụ.
- **automountServiceAccountToken: false** giảm nguy cơ lộ token tự động mount; một token vẫn có thể xuất hiện nếu ứng dụng hoặc thành phần khác cố ý mount/cấp nó.
- **resources.limits** giúp kiểm soát tài nguyên, nhưng không nên coi CPU/memory/ephemeral-storage limit là ranh giới bảo mật tuyệt đối cho mọi dạng DoS.

Image, phiên bản, cấu hình, quyền đọc secrets, volume khác, ingress và phiên bản node phải được quản trị riêng. Trong triển khai thực tế nên **ghim image bằng digest đã xác minh** để giảm khả năng thay đổi nội dung dù giữ nguyên tag; tên registry/image ở ví dụ là giả định.

### 5.1. Chính sách mạng cho workload

~~~yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: risk-api-isolation
  namespace: platform-prod
spec:
  podSelector:
    matchLabels:
      app: risk-api
  policyTypes:
    - Ingress
    - Egress
  ingress:
    - from:
        - podSelector:
            matchLabels:
              app: edge-gateway
      ports:
        - protocol: TCP
          port: 8080
  egress:
    - to:
        - namespaceSelector:
            matchLabels:
              kubernetes.io/metadata.name: kube-system
          podSelector:
            matchLabels:
              k8s-app: kube-dns
      ports:
        - protocol: UDP
          port: 53
        - protocol: TCP
          port: 53
~~~

NetworkPolicy này chọn những pod có nhãn **app: risk-api**. Chính sách cho ingress từ pod gateway cùng namespace đến TCP 8080 và cho egress DNS theo nhãn minh họa. Vì policy đã chọn cả **Ingress** và **Egress**, các kết nối khác thuộc phạm vi thực thi của chính sách sẽ bị từ chối, trừ khi có **NetworkPolicy khác cũng cho phép** chúng: tập các policy Kubernetes được kết hợp theo hướng **cộng quyền cho phép**.

Điều kiện bắt buộc khi đưa ví dụ vào hệ thống thật:

1. **CNI phải hỗ trợ và thực thi NetworkPolicy**; chỉ tạo object NetworkPolicy trong API không bảo đảm lọc lưu lượng.
2. Kiểm tra chính xác nhãn của DNS pod, vị trí dịch vụ DNS và cơ chế DNS node-local; các nhãn trong ví dụ không phổ quát.
3. Bổ sung endpoint mà ứng dụng thật sự cần (ví dụ database) với đích/port tối thiểu; giả định của ví dụ chỉ có DNS và gateway.
4. Xác nhận hành vi với các loại lưu lượng đặc biệt (hostNetwork, lưu lượng qua node, đường CNI/plugin) dựa trên tài liệu và phép thử của cụm.
5. Giữ authorization tại ứng dụng và dịch vụ đích; chỉ có thể kết nối không đồng nghĩa đã được quyền đọc dữ liệu.

Nếu trong namespace còn workload khác cần được bảo vệ, áp dụng baseline mặc định chặn ingress/egress cho những pod liên quan và bổ sung policy cấp phép theo nhu cầu. Không suy luận toàn bộ namespace đã “default deny” từ một policy chỉ chọn nhãn **app: risk-api**.

### 5.2. Những cơ chế phải được quản trị ở cấp nền tảng

Ngoài manifest của ứng dụng, nhóm platform cần xác minh:

- **Pod Security Admission** hoặc policy engine được cấu hình chế độ **enforce** theo mức phù hợp (thường là Restricted cho workload thông thường); chế độ audit/warn chỉ phát tín hiệu, không tự chặn yêu cầu.
- RBAC không cấp cho principal không phù hợp quyền tạo hoặc sửa workload đặc quyền, sửa policy, xem secrets hay chiếm quyền service account.
- RuntimeClass, node pool, kernel, container runtime và sandbox được lựa chọn phù hợp với mức độ tin cậy của workload.
- HostPath, thiết bị host, socket runtime, Linux capabilities, host namespaces, sysctls và các ngoại lệ được quản lý tập trung.
- Chính sách phân bổ tài nguyên, quota, node isolation và giám sát phù hợp với nguy cơ lạm dụng CPU/RAM/PID/I/O.
- Tài khoản quản trị, cơ chế truy cập node, control plane, secret store, audit log và agent quan sát không trở thành đường vòng quanh ranh giới workload.

Trong môi trường nhiều tenant hoặc chạy mã không đáng tin cậy, cân nhắc **sandbox/VM hoặc phân tách node/cluster** và ghi nhận rõ giả định tin cậy của từng lớp. Không coi admission policy là lá chắn trước lỗi kernel hoặc quyền quản trị cấp host.

## 6. Chuyển kiểm soát thành bằng chứng assurance

Cách làm phù hợp là thiết lập chuỗi truy vết:

~~~mermaid
flowchart LR
    Threat["Threat / Risk"] --> Claim["Security claim"]
    Claim --> Control["Control được áp dụng"]
    Control --> Test["Phép thử / Quan sát"]
    Test --> Evidence["Bằng chứng có thời điểm"]
    Evidence --> Review["Kết luận và ngoại lệ"]
    Review --> Recheck["Theo dõi thay đổi / Kiểm tra lại"]
    Recheck --> Claim
~~~

Mỗi **security claim** nên cụ thể, giới hạn phạm vi và có điều kiện chấp nhận rõ ràng.

| Claim kiểm chứng | Kiểm soát chính | Bài kiểm tra và tiêu chí chấp nhận | Bằng chứng cần giữ |
|---|---|---|---|
| **C1 — Không có đặc quyền host** | Admission enforce, cấm privileged/host namespace, hạn chế capabilities, hostPath. | Không pod nào thuộc phạm vi có trường đặc quyền bị cấm; yêu cầu tạo pod vi phạm bị admission từ chối. | Bản policy và phiên bản, kết quả thử admission, snapshot PodSpec đang chạy. |
| **C2 — Giới hạn thao tác tiến trình** | UID/GID không root, seccomp, LSM, read-only rootfs. | Thao tác ghi vào đường dẫn hệ thống ngoài vùng được phép thất bại; trạng thái runtime cho thấy profile áp dụng. | Cấu hình và metadata runtime, log thử nghiệm, phiên bản image/node/runtime. |
| **C3 — Không truy cập mạng ngoài allowlist** | NetworkPolicy được CNI thực thi, quyền tại dịch vụ đích. | Kết nối từ nguồn được phép thành công; từ nguồn/đích ngoài chính sách thất bại trong thời hạn timeout đã quy định. | Policy đã áp dụng, nhãn pod/namespace, kết quả flow test và flow logs phù hợp. |
| **C4 — Không lộ token dư thừa** | Không auto-mount token, RBAC theo đặc quyền tối thiểu. | Workload không có token mount không cần thiết; danh tính dịch vụ không thể gọi API bị cấm. | Manifest/mount snapshot, role binding, kết quả API authorization test. |
| **C5 — Có giới hạn tác động tài nguyên** | Request/limit/quota, chính sách PID/I/O của node/runtime theo khả năng nền tảng. | Thử tải được kiểm soát không làm workload khác vượt ngưỡng SLO đã định; cảnh báo tài nguyên hoạt động. | Cấu hình giới hạn, dashboard metrics, kết quả thử tải và sự kiện OOM/eviction. |
| **C6 — Phát hiện thay đổi làm yếu cô lập** | Policy-as-code, admission, drift monitoring, audit. | Thay đổi vi phạm bị chặn hoặc phát hiện trong SLA theo định nghĩa; ngoại lệ có owner/ngày hết hạn. | Báo cáo CI, audit event, snapshot desired/observed state, hồ sơ ngoại lệ. |

Một claim có thể **đạt trong phạm vi thử nghiệm**, nhưng vẫn có **rủi ro tồn dư**. Ví dụ, thử kết nối mạng thất bại không chứng minh kernel không có lỗ hổng; một kết quả chạy lệnh thành công cũng không bảo đảm policy còn nguyên sau lần deploy tiếp theo.

### 6.1. Quy trình kiểm chứng ba lớp

**Lớp A — Kiểm tra cấu hình trước triển khai**

- Phân tích manifest/Helm/Kustomize sau render, cùng policy áp dụng cho namespace.
- Kiểm tra tất cả container, init container và ephemeral container theo chính sách tương ứng.
- Kiểm tra securityContext, service account, RBAC, host namespace, volume, capability, seccomp, RuntimeClass, network policy và tài nguyên.
- Thử một manifest vi phạm trong môi trường kiểm thử để xác nhận **admission enforce** thực sự từ chối; một chính sách chỉ ở chế độ audit chưa đáp ứng claim chặn.
- Ghi lại commit, digest image, phiên bản rule/policy, kết quả và thời điểm.

**Lớp B — Kiểm tra trạng thái đã triển khai**

- Lấy snapshot pod hiện tại và đối chiếu với manifest mong muốn; phân biệt template của Deployment với PodSpec thực đang chạy.
- Kiểm tra node/runtime, phiên bản kernel, cấu hình sandbox, seccomp/LSM enforcement và các ngoại lệ phù hợp.
- Kiểm tra service account thực tế, volume, nhãn pod/namespace, NetworkPolicy và CNI.
- Chú ý workload đang chạy có thể được tạo trước một thay đổi admission policy; enforce policy khi tạo pod không tự chỉnh lại pod cũ.

Ví dụ lệnh quan sát trong cluster được ủy quyền:

~~~bash
kubectl -n platform-prod get deploy risk-api -o yaml
kubectl -n platform-prod get pods -l app=risk-api -o wide
kubectl -n platform-prod get networkpolicy risk-api-isolation -o yaml
kubectl get namespace platform-prod --show-labels
kubectl -n platform-prod describe pod <ten-pod-thuc-te>
~~~

Nếu image có shell và công cụ cần thiết, có thể kiểm tra thêm:

~~~bash
kubectl -n platform-prod exec <ten-pod-thuc-te> -c api -- id
kubectl -n platform-prod exec <ten-pod-thuc-te> -c api -- cat /proc/self/status
~~~

Trường **Seccomp** trong **/proc/self/status** có thể cho biết seccomp đang lọc (giá trị 2); cần kết hợp thêm policy/profile và runtime metadata để biết tập syscall nào thực sự bị giới hạn. **CapEff** là một dấu hiệu về effective capabilities tại thời điểm quan sát. Container image dạng distroless có thể không chứa shell, **id** hoặc **cat**; khi đó sử dụng công cụ quan sát phù hợp từ node/runtime hoặc một test workload được cấu hình cùng profile. Không thêm công cụ debug vào production image chỉ để đáp ứng ví dụ này.

**Lớp C — Kiểm tra hành vi**

Chỉ thử trong phạm vi môi trường, tài khoản và workload đã cho phép; với phép thử gây tải hoặc ảnh hưởng dịch vụ, dùng môi trường cô lập và ngưỡng dừng rõ ràng.

| Phép thử | Kết quả kỳ vọng | Vì sao cần cả phép thử dương tính |
|---|---|---|
| Gửi HTTP từ gateway hợp lệ tới cổng 8080 của risk-api. | **Cho phép** và có phản hồi ứng dụng hợp lệ. | Tránh đánh giá “an toàn” vì policy chặn nhầm toàn bộ traffic. |
| Kết nối từ một pod không được phép trong cùng namespace đến risk-api. | **Bị chặn** tại ranh giới mạng theo chính sách. | Chứng minh quy tắc ingress có tác dụng. |
| Kết nối từ risk-api đến endpoint bất kỳ ngoài allowlist. | **Bị chặn** theo chính sách egress, trong môi trường CNI hỗ trợ. | Phân biệt lọc mạng thực tế với việc chỉ có object policy. |
| Truy vấn DNS tới dịch vụ DNS hợp lệ. | **Cho phép**. | Xác nhận ngoại lệ DNS vẫn phục vụ chức năng ứng dụng. |
| Từ tiến trình ứng dụng thử ghi vào đường dẫn hệ thống ngoài vùng được phép. | **Thất bại**; ghi vào /tmp được phép nếu ứng dụng cần. | Phân biệt rootfs read-only và volume được phép ghi. |
| Kiểm tra token và gọi API Kubernetes bị cấm bằng danh tính workload nếu có. | Không có token dư thừa; yêu cầu không được cấp quyền bị **từ chối**. | Chứng minh IAM và mount policy có hiệu lực thay vì chỉ xét cờ cấu hình. |
| Tạo pod kiểm thử vi phạm policy admission bằng tài khoản đại diện nhà phát triển. | API từ chối với lý do policy cụ thể. | Chứng minh ranh giới quản trị không thể bị bỏ qua qua quy trình triển khai thông thường. |

Khi một phép thử âm tính thất bại, phải phân biệt **bị chặn thật sự** với lỗi DNS, lỗi dịch vụ, lỗi kết nối ngẫu nhiên hoặc lỗi công cụ kiểm thử. Ghi rõ nguồn, đích, route, thời điểm, timeout, mã lỗi và flow log để tránh kết luận sai.

### 6.2. Bằng chứng cần có tính tái lập

Một bộ bằng chứng mẫu cho từng lần phát hành có thể gồm:

~~~text
assurance/runtime-isolation/
  release-id.txt                 # workload, namespace, commit, image digest
  isolation-contract.md          # ranh giới, tài nguyên, quyền và giả định
  risk-assessment.md             # threat, mức rủi ro, chấp nhận rủi ro
  desired-manifests.yaml         # cấu hình sau render
  observed-pod-spec.yaml         # trạng thái runtime tại thời điểm kiểm tra
  policy-admission-result.json   # tên policy, mode, quyết định, timestamp
  network-test-results.json      # nguồn, đích, kết quả allow/deny
  runtime-check-results.json     # UID, capability, seccomp, rootfs, mount
  cluster-versions.txt           # CNI, Kubernetes, runtime, kernel
  exceptions.csv                 # ngoại lệ, lý do, owner, thời hạn
  review-decision.md             # quyết định, người duyệt, rủi ro còn lại
~~~

Đây là **cấu trúc minh họa**, không phải một định dạng bắt buộc. Chỉ lưu dữ liệu cần thiết; không đưa token, khóa bí mật hoặc thông tin nhạy cảm vào báo cáo thử nghiệm. Dùng nơi lưu có kiểm soát quyền, thời hạn lưu và khả năng truy vết chỉnh sửa.

Một bản ghi kiểm chứng phải cho phép người đánh giá khác trả lời: **đã kiểm tra workload nào, trên cluster/node/runtime nào, bằng chính sách phiên bản nào, thử điều gì, quan sát kết quả gì và kết luận áp dụng đến khi nào**.

## 7. Duy trì cô lập khi runtime thay đổi

Runtime isolation không phải cấu hình làm một lần rồi kết thúc. Ranh giới có thể yếu đi khi:

- Một nhóm bật privileged để khắc phục sự cố rồi quên gỡ ngoại lệ.
- Nâng cấp Kubernetes, container runtime, CNI hoặc kernel khiến hành vi enforcement thay đổi.
- Deployment đổi nhãn khiến NetworkPolicy không còn chọn đúng pod.
- Thay service account hoặc thêm volume làm workload có quyền mới.
- Thêm container phụ, ephemeral container để debug hoặc thay đổi RuntimeClass.
- Workload chuyển sang node pool mới với cấu hình seccomp/LSM khác.
- Một policy NetworkPolicy khác cấp thêm luồng vào/ra ngoài allowlist ban đầu.

### 7.1. Vòng kiểm soát liên tục

1. **Define:** Chốt isolation contract, mức rủi ro và owner cho từng loại workload.
2. **Prevent:** Enforce policy tại pipeline, admission, RBAC và cấu hình node/runtime.
3. **Verify:** Kết hợp kiểm tra desired state, observed state và thử hành vi cho ranh giới quan trọng.
4. **Detect:** Theo dõi policy drift, privileged container, cấu hình mount, bất thường syscall, hành vi mạng và tài nguyên.
5. **Respond:** Khoanh vùng workload, thu thập chứng cứ, khắc phục nguyên nhân, kiểm tra tác động lên các workload cùng ranh giới tin cậy.
6. **Reassess:** Chạy lại thử nghiệm sau thay đổi chính sách, phiên bản runtime, kiến trúc, phân loại dữ liệu hoặc kết quả phát hiện mới.

Nên phân công rõ: **platform team** sở hữu baseline runtime/node/CNI, **application team** sở hữu quyền và nhu cầu kết nối của workload, **security/assurance team** sở hữu tiêu chí và phương pháp kiểm chứng, **risk owner** phê duyệt rủi ro tồn dư. Các vai trò thực tế có thể gộp, nhưng trách nhiệm không nên bị bỏ trống.

### 7.2. Quản lý ngoại lệ

Một ngoại lệ, ví dụ ứng dụng cần ghi vào đường dẫn tạm hoặc giữ một capability, phải ghi rõ:

- Workload và môi trường áp dụng; quyền đặc biệt cụ thể.
- Lý do kinh doanh/kỹ thuật và phương án thay thế đã đánh giá.
- Threat và tài nguyên bị ảnh hưởng; control bù trừ.
- Người phê duyệt, người chịu trách nhiệm, ngày hết hạn và sự kiện kích hoạt kiểm tra lại.
- Kiểm thử xác minh ngoại lệ không mở rộng vượt phạm vi đã được chấp thuận.

Không dùng “ứng dụng vẫn chạy tốt” làm lý do duy nhất để giữ đặc quyền.

## 8. Tình huống phân tích: chạy mã của khách hàng

Một nền tảng cho khách hàng gửi mã phân tích dữ liệu; mỗi job chạy trong container và xử lý dữ liệu của chính khách hàng. Kỹ sư đề xuất “mỗi tenant một namespace Kubernetes và bật default deny ingress” rồi tuyên bố đạt runtime isolation.

**Đánh giá:**

- **Tài sản/rủi ro:** mã người dùng là không đáng tin cậy; rò rỉ dữ liệu chéo tenant, truy cập host, khai thác kernel, lấy secret, làm cạn tài nguyên và lạm dụng egress đều đáng xét.
- **Khoảng trống kiến trúc:** namespace Kubernetes và network policy không cô lập kernel hoặc quyền truy cập node; default deny ingress chưa kiểm soát egress, secrets, volume hay tài nguyên.
- **Thiết kế mạnh hơn:** cân nhắc sandbox/VM hoặc node pool tách biệt phù hợp mức rủi ro; service account tối thiểu; giới hạn network/volume/syscall; timeout và resource quota; mã và đầu ra được kiểm soát; control plane và IAM phân tách theo phạm vi cần thiết.
- **Bằng chứng cần thu:** policy enforce, cấu hình runtime/VM, kết quả thử đọc chéo tenant, thử egress/ingress, thử quyền API, thử resource abuse có kiểm soát, theo dõi kernel/runtime patching, logs và ngoại lệ.
- **Quyết định:** chỉ có thể tuyên bố một ranh giới được assurance khi các phép thử và giả định tương ứng đạt yêu cầu. Nếu chưa xác thực sandbox hoặc node isolation, ghi nhận rủi ro tồn dư thay vì đánh dấu “đã cô lập hoàn toàn”.

Câu hỏi thực hành: nếu attacker kiểm soát toàn bộ user code trong job, đâu là lớp ngăn attacker đọc secret của tenant khác? Đâu là lớp ngăn đọc host filesystem? Đâu là lớp hạn chế ảnh hưởng DoS? Với mỗi lớp, hãy chỉ ra **một bằng chứng cấu hình** và **một kết quả thử hành vi**.

## 9. Sai lầm thường gặp

1. **“Container là ranh giới bảo mật tuyệt đối.”** Container thường chia sẻ kernel; chất lượng ranh giới phụ thuộc nhiều cơ chế và việc cập nhật runtime/host.
2. **“Đặt workload vào namespace Kubernetes riêng là đủ.”** Namespace tổ chức tài nguyên và hỗ trợ chính sách, không thay thế tách kernel, IAM hoặc bảo vệ control plane.
3. **“Có cgroups nghĩa là dữ liệu đã được cô lập.”** cgroups chủ yếu hạn chế tài nguyên; bảo mật dữ liệu cần quyền, mount, network và identity tương ứng.
4. **“NetworkPolicy đang tồn tại nên chắc chắn có hiệu lực.”** CNI phải thực thi; selector, policy cộng quyền, DNS và ngoại lệ node cần được kiểm tra thực tế.
5. **“root filesystem read-only nghĩa là không ghi được bất cứ đâu.”** Một volume được mount vẫn có thể ghi, và host mount phải kiểm tra riêng.
6. **“seccomp RuntimeDefault có nội dung giống nhau trên mọi cluster.”** Profile phụ thuộc runtime và phiên bản; cần ghi nhận môi trường kiểm tra.
7. **“Đã vượt bài kiểm tra cấu hình thì không cần test hành vi.”** Admission policy có thể chỉ audit; pod đang chạy có thể khác template hoặc được tạo trước khi policy cập nhật.
8. **“Một lần pass có giá trị mãi mãi.”** Rủi ro đổi theo image, policy, runtime, node, CNI và quyền của principal.

## 10. Checklist trước khi kết luận đạt assurance

- [ ] Xác định rõ workload, tenant, tài nguyên, ranh giới tin cậy, giả định và tác động khi thất bại.
- [ ] Chọn mức cô lập tương ứng với độ tin cậy của mã và mức nhạy cảm của dữ liệu.
- [ ] Có baseline cho đặc quyền, host namespaces, capabilities, seccomp/MAC, quyền tệp và mount.
- [ ] Kiểm soát service account, RBAC, secrets, quyền admin và khả năng sửa policy.
- [ ] Xác nhận giới hạn mạng, bao gồm egress, được hạ tầng mạng thực thi đúng.
- [ ] Có giới hạn và giám sát tài nguyên thích hợp; nêu rõ các trường hợp không được bảo vệ.
- [ ] Kiểm tra cả cấu hình mong muốn, trạng thái đang chạy và hành vi cho phép/từ chối.
- [ ] Thu thập bằng chứng có thời điểm, phiên bản, phạm vi, tiêu chí chấp nhận và người đánh giá.
- [ ] Ghi nhận ngoại lệ, rủi ro tồn dư và thời điểm phải kiểm chứng lại.

**Điểm cốt lõi:** runtime isolation là một tập hợp ranh giới có điều kiện, không phải một nhãn công nghệ. Trong platform assurance, chất lượng của tuyên bố cô lập được quyết định bởi tính rõ ràng của threat model, mức phù hợp của các control và **bằng chứng rằng những thao tác vượt quyền thực sự bị ngăn chặn trong môi trường đang vận hành**.
