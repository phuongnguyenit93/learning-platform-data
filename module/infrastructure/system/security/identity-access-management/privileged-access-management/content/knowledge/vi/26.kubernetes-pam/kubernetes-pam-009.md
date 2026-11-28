# Pod security context

## 1. Security context kiểm soát lớp quyền nào?

Pod security context là phần cấu hình các thuộc tính bảo mật cho Pod và container, chẳng hạn danh tính hệ điều hành của tiến trình, quyền tăng đặc quyền, Linux capabilities, quyền trên volume và một số cơ chế kiểm soát của kernel.

Trong Kubernetes PAM, cần phân biệt ít nhất ba lớp:

| Lớp | Câu hỏi chính | Ví dụ |
|---|---|---|
| Quyền Kubernetes API | Ai được tạo, sửa hoặc tương tác với workload? | RBAC cho phép tạo Pod hoặc mở exec |
| Danh tính workload | Workload dùng principal nào khi gọi hệ thống khác? | ServiceAccount, danh tính cloud, credential ứng dụng |
| Quyền tiến trình | Mã trong container có thể làm gì ở hệ điều hành? | UID, GID, capabilities, seccomp, quyền file |

Một container chạy bằng UID khác 0 vẫn có thể dùng token có quyền quản trị cluster nếu token đó có sẵn và được hệ thống đích chấp nhận. Ngược lại, container chạy bằng UID 0 không tự nhận quyền cluster-admin từ Kubernetes.

Vì vậy, security context cần phối hợp với quản lý danh tính và quyền truy cập. Nó không thay thế RBAC, vault hoặc quy trình cấp quyền JIT.

### Mục tiêu học tập

Sau bài này, người học có thể:

1. Phân biệt cấu hình ở cấp Pod và cấp container.
2. Chọn UID, GID và quyền filesystem phù hợp.
3. Kết hợp non-root, hạn chế tăng quyền, capabilities và seccomp.
4. Thiết kế volume ghi được mà không mở rộng quyền toàn bộ container.
5. Kiểm chứng trạng thái runtime và quản lý ngoại lệ đặc quyền có thời hạn.

## 2. Cấp Pod và cấp container

### 2.1. Hai vị trí cấu hình

Ở cấp Pod:

```yaml
spec:
  securityContext:
    runAsNonRoot: true
    runAsUser: 10001
    runAsGroup: 10001
```

Ở cấp container:

```yaml
spec:
  containers:
    - name: application
      securityContext:
        allowPrivilegeEscalation: false
        readOnlyRootFilesystem: true
```

Không phải trường nào cũng dùng được ở cả hai cấp. Cần đặt đúng vị trí theo schema của phiên bản cluster.

### 2.2. Khi hai cấp cùng đặt một thuộc tính

Với những thuộc tính có ở cả hai cấp, giá trị container có thể ghi đè giá trị Pod cho container đó. Không nên hiểu cấu hình Pod là một điều kiện bắt buộc không thể bị container thay đổi.

Ví dụ, Pod đặt `runAsUser: 10001`, còn một container đặt `runAsUser: 20001`; container đó dùng giá trị riêng của nó. Nếu một container yêu cầu UID 0 trong khi vẫn có yêu cầu non-root hiệu lực, cấu hình có thể bị chặn ở admission hoặc không khởi chạy được, tùy kiểm soát liên quan.

Cần rà soát cả container chính, init container và ephemeral container, không chỉ container đầu tiên. [Kubernetes — Configure a Security Context](https://kubernetes.io/docs/tasks/configure-pod-container/security-context/).

### 2.3. Những trường thường gặp

| Trường | Vị trí thông dụng | Mục đích |
|---|---|---|
| runAsUser | Pod hoặc container | UID chạy tiến trình |
| runAsGroup | Pod hoặc container | GID chính chạy tiến trình |
| runAsNonRoot | Pod hoặc container | Yêu cầu tiến trình không chạy bằng UID 0 |
| fsGroup | Pod | Nhóm bổ sung và xử lý quyền volume theo cơ chế hỗ trợ |
| supplementalGroups | Pod | Những nhóm bổ sung được khai báo |
| allowPrivilegeEscalation | Container | Hạn chế nhận thêm đặc quyền qua cơ chế thực thi chương trình |
| capabilities | Container | Cấu hình Linux capabilities |
| privileged | Container | Yêu cầu chế độ đặc quyền |
| readOnlyRootFilesystem | Container | Mount root filesystem của container ở chế độ chỉ đọc |
| seccompProfile | Pod hoặc container | Chọn chính sách lọc syscall |

Bảng là định hướng cho các ví dụ Linux. Không sao chép toàn bộ sang Windows; khả năng hỗ trợ và những trường được phép khác nhau.

## 3. runAsUser, runAsGroup và runAsNonRoot

### 3.1. UID và GID là danh tính hệ điều hành

`runAsUser` chọn UID cho tiến trình khởi chạy trong container. `runAsGroup` chọn GID chính.

Các số này không tạo user hoặc group mới trong image, không tự sửa `/etc/passwd` và không tự đổi ownership của mọi file.

Một tiến trình có UID 10001 vẫn cần quyền đọc executable, thư viện và cấu hình; nó cũng cần quyền ghi đúng những thư mục mà ứng dụng sử dụng.

### 3.2. runAsNonRoot không tự chọn UID an toàn

`runAsNonRoot: true` là yêu cầu xác minh không chạy bằng UID 0. Nó không tự chuyển một image cần root thành ứng dụng tương thích non-root.

Nếu image mặc định chạy root mà không có cấu hình phù hợp, container có thể không khởi chạy. Nếu danh tính trong image không cho runtime xác minh được yêu cầu, cần xử lý metadata hoặc cấu hình UID phù hợp thay vì bỏ kiểm soát.

Khi không chỉ định UID hoặc GID, phải xem metadata image và hành vi runtime; không giả định mọi image có cùng mặc định. [Kubernetes API — Pod and SecurityContext](https://kubernetes.io/docs/reference/kubernetes-api/core/pod-v1/).

### 3.3. Vì sao thường kết hợp cả ba trường?

Một cấu hình minh họa:

```yaml
securityContext:
  runAsNonRoot: true
  runAsUser: 10001
  runAsGroup: 10001
```

UID và GID giúp xác định danh tính mong muốn; yêu cầu non-root thể hiện một ràng buộc cần duy trì.

Các số 10001 chỉ là lựa chọn của ví dụ. Một nền tảng có thể cấp dải UID riêng hoặc yêu cầu image hỗ trợ UID bất kỳ. Cần tuân thủ mô hình đó, không áp một UID cố định cho mọi ứng dụng.

### 3.4. Non-root không phải toàn bộ least privilege

Một tiến trình non-root vẫn có thể:

- Đọc file được cấp quyền cho UID hoặc group của nó.
- Dùng credential đã mount hoặc được cấp từ nguồn khác.
- Gọi API mạng nếu đường truy cập được phép.
- Thao tác trên volume ghi được.
- Nhận các capabilities hoặc quyền khác nếu cấu hình cho phép.

Mục tiêu PAM là giới hạn từng khả năng theo nhiệm vụ, không chỉ đạt một nhãn “non-root”.

## 4. Hạn chế tăng đặc quyền

### 4.1. allowPrivilegeEscalation

Với container Linux, `allowPrivilegeEscalation: false` liên quan tới cơ chế `no_new_privs`, giúp hạn chế tiến trình nhận thêm đặc quyền khi thực thi chương trình, chẳng hạn qua các cơ chế set-user-ID hoặc file capabilities.

Ở mức kernel, no_new_privs giải quyết việc nhận thêm quyền qua exec; nó không thu hồi các quyền mà tiến trình đã có. [Linux kernel — No New Privileges Flag](https://docs.kernel.org/userspace-api/no_new_privs.html).

### 4.2. Những kết luận không được suy ra

Thiết lập này không tự:

- Đổi UID hiện tại thành non-root.
- Xóa mọi Linux capability.
- Vô hiệu hóa token Kubernetes.
- Chặn mọi khai thác lỗi kernel hoặc ứng dụng.
- Làm filesystem chỉ đọc.
- Giới hạn quyền truy cập mạng.

Cần kết hợp với những kiểm soát riêng cho các khả năng đó.

### 4.3. Không ghép với privileged rồi coi như đã an toàn

Chế độ privileged và các capability rất mạnh có thể làm mất ý nghĩa của những hạn chế khác; API và runtime còn có ràng buộc đối với các tổ hợp cấu hình.

Không thiết kế một ngoại lệ bằng cách bật privileged rồi giữ `allowPrivilegeEscalation: false` để tuyên bố container vẫn bị hạn chế đầy đủ.

Nếu ứng dụng thất bại vì một thao tác cần quyền, phải xác định chính xác thao tác và lý do trước khi tăng quyền.

## 5. Linux capabilities và privileged container

### 5.1. Capabilities chia nhỏ một số đặc quyền

Linux capabilities cho phép phân chia các khả năng đặc biệt của tiến trình thành những quyền riêng, thay vì chỉ dựa vào một nhãn root.

Một hướng thiết kế là bắt đầu bằng:

```yaml
securityContext:
  capabilities:
    drop:
      - ALL
```

Sau đó chỉ cân nhắc bổ sung một capability khi có nhu cầu đã được xác định và kiểm chứng. Không thêm một danh sách rộng để giải quyết mọi lỗi khởi động.

### 5.2. Không suy luận từ UID

UID khác 0 không tự chứng minh không có capabilities. UID 0 cũng không mô tả đầy đủ capabilities, namespace và những hạn chế runtime đang có.

Khi cần kết luận quyền thực tế, phải xem trạng thái tiến trình và cấu hình runtime phù hợp, không chỉ nhìn một trường trong manifest.

### 5.3. privileged mở phạm vi lớn hơn một lỗi cụ thể

Privileged container được cấp những khả năng mạnh và có thể bỏ qua hoặc làm mất hiệu lực nhiều hạn chế kernel của container. Vì thế, bật privileged để khắc phục một lỗi ghi file là cách mở rộng quyền không tương xứng.

Những workload thực sự cần khả năng quản trị hệ điều hành, thiết bị hoặc mạng cần một thiết kế và quy trình ngoại lệ riêng. [Kubernetes — Linux kernel security constraints](https://kubernetes.io/docs/concepts/security/linux-kernel-security-constraints/).

### 5.4. Bắt đầu từ chức năng cần thiết

Ví dụ, ứng dụng web có thể được thiết kế nghe trên một cổng không cần đặc quyền thay vì yêu cầu quyền bổ sung để bind cổng đặc biệt.

Việc thay đổi cổng phải phù hợp cấu hình Service và ứng dụng. Khai báo `containerPort` trong manifest không tự cấu hình tiến trình nghe trên cổng đó.

Không dùng một thay đổi security context để che một lỗi cấu hình ứng dụng chưa được hiểu.

## 6. Seccomp và các cơ chế kiểm soát kernel khác

### 6.1. Seccomp lọc syscall

Seccomp giới hạn những system call mà tiến trình được thực hiện theo profile.

Một cấu hình thường được dùng làm điểm khởi đầu:

```yaml
securityContext:
  seccompProfile:
    type: RuntimeDefault
```

`RuntimeDefault` dùng profile mặc định của container runtime. Profile có thể khác giữa runtime hoặc phiên bản.

`Localhost` tham chiếu profile được chuẩn bị trên node. `Unconfined` không áp giới hạn seccomp tương ứng. Privileged container không được coi là vẫn được bảo vệ bởi profile seccomp khai báo. [Kubernetes — Seccomp and Kubernetes](https://kubernetes.io/docs/reference/node/seccomp/).

### 6.2. RuntimeDefault không phải cam kết chặn mọi tấn công

Một chương trình độc hại vẫn có thể gây tác động bằng các syscall được phép và những quyền khác đã được cấp.

Cần kiểm thử ứng dụng với runtime, kernel và profile dự kiến. Nếu có lỗi, thu thập bằng chứng về syscall hoặc hành vi liên quan trước khi đổi sang Unconfined.

Một profile tùy chỉnh cũng có vòng đời: phải được phân phối tới node phù hợp, quản lý phiên bản và kiểm tra khi ứng dụng thay đổi. [Kubernetes — Restrict a Container's Syscalls](https://kubernetes.io/docs/tutorials/security/seccomp/).

### 6.3. AppArmor và SELinux

AppArmor và SELinux là những cơ chế kiểm soát bổ sung với mô hình chính sách riêng. Hiệu lực phụ thuộc node, kernel, runtime, cấu hình và profile hoặc label được sử dụng.

Không tự chọn một SELinux label hoặc profile AppArmor từ một ví dụ trên mạng rồi áp rộng lên mọi node.

Nếu dùng các trường API cho những cơ chế này, cần xác minh phiên bản và khả năng hỗ trợ của cluster. Việc chỉ có tên profile trong manifest không chứng minh profile đó tồn tại và được thực thi đúng.

### 6.4. Nhiều lớp bảo vệ không đồng nghĩa cùng một chức năng

| Cơ chế | Trọng tâm |
|---|---|
| UID/GID và quyền file | Quyền truy cập theo danh tính hệ điều hành |
| Capabilities | Những khả năng đặc biệt của tiến trình |
| no_new_privs | Hạn chế nhận thêm quyền qua thực thi chương trình |
| Seccomp | Giới hạn syscall |
| AppArmor hoặc SELinux | Chính sách kiểm soát truy cập theo cơ chế tương ứng |
| RBAC | Quyền thực hiện yêu cầu Kubernetes API |

Khi một thao tác thất bại, cần tìm đúng lớp đã từ chối. Không tắt tất cả các lớp chỉ để ứng dụng chạy.

## 7. Root filesystem chỉ đọc và vùng ghi riêng

### 7.1. readOnlyRootFilesystem

`readOnlyRootFilesystem: true` đặt root filesystem của container thành chỉ đọc.

Nó giúp giảm khả năng sửa các file trong lớp filesystem đó. Tuy nhiên, volume được mount riêng có thể vẫn ghi được theo cấu hình và quyền của volume.

Nó cũng không tự ngăn đọc dữ liệu, dùng token hoặc truy cập dịch vụ mạng.

### 7.2. Ứng dụng vẫn có thể cần ghi

Những vị trí thường cần được phân tích:

- Thư mục tạm.
- Cache ứng dụng.
- File PID hoặc socket.
- Dữ liệu làm việc.
- Kết quả xử lý.
- Dữ liệu nghiệp vụ bền vững.

Cần xác định nơi nào thực sự cần ghi, thời hạn lưu và quyền truy cập. Sau đó mount vùng phù hợp thay vì mở lại root filesystem toàn bộ.

### 7.3. Không sửa lỗi bằng chmod rộng

Nếu UID mới không ghi được một thư mục, cần kiểm tra ownership, mode, ACL, nhóm, mount và cơ chế storage.

Việc mở quyền cho mọi user trên toàn bộ thư mục có thể giải quyết triệu chứng nhưng làm mất ranh giới giữa tiến trình và dữ liệu.

Có thể cần sửa image lúc build, chuẩn bị volume hoặc cấu hình ứng dụng ghi vào đúng đường dẫn được cấp.

### 7.4. Vùng tạm cũng cần giới hạn

Một emptyDir ghi được vẫn là nơi ứng dụng có thể tạo file. Root filesystem chỉ đọc không ngăn mã độc chạy từ một vùng ghi được nếu những điều kiện khác cho phép.

Cần đánh giá dữ liệu, dung lượng và quyền trên vùng đó. Một giới hạn dung lượng minh họa không phải cơ chế phân quyền hay cách ly dữ liệu giữa mọi workload.

Tài liệu checklist ứng dụng khuyến nghị phối hợp non-root, hạn chế tăng quyền và root filesystem chỉ đọc, nhưng hiệu quả vẫn cần được kiểm chứng theo ứng dụng. [Kubernetes — Application Security Checklist](https://kubernetes.io/docs/concepts/security/application-security-checklist/).

## 8. fsGroup, supplementalGroups và quyền volume

### 8.1. runAsGroup khác fsGroup

`runAsGroup` là GID chính của tiến trình. `fsGroup` tham gia mô hình nhóm bổ sung và quyền volume theo cơ chế được hỗ trợ.

Không coi fsGroup là UID, cũng không coi nó là cách đổi ownership của toàn bộ filesystem trong image.

Một container có thể đọc file nhờ quyền group dù UID không trùng owner. Vì vậy, kiểm tra quyền cần xem đầy đủ UID, GID và các group hiệu lực.

### 8.2. Không phải mọi volume có cùng hành vi

Hiệu lực thay đổi quyền theo fsGroup phụ thuộc loại volume và driver.

Với CSI, driver có thể tham gia hoặc đảm nhận xử lý nhóm và quyền mount theo khả năng hỗ trợ. Cần xem hành vi của driver và storage thật, không chỉ nhìn manifest. [Kubernetes CSI — FSGroup Support](https://kubernetes-csi.github.io/docs/support-fsgroup.html).

### 8.3. fsGroupChangePolicy

Đối với những volume hỗ trợ cơ chế tương ứng, `fsGroupChangePolicy` có thể thay đổi cách kiểm tra hoặc sửa ownership và permissions.

`OnRootMismatch` có thể tránh một số công việc lặp khi thư mục gốc volume đã khớp. Nó không phải phép kiểm tra toàn bộ mọi file luôn có quyền đúng.

Không áp dụng giả định này cho mọi volume. Tài liệu Kubernetes lưu ý trường này không có tác dụng với các loại volume như Secret, ConfigMap và emptyDir; khi CSI đảm nhận xử lý nhóm, cũng cần hiểu trách nhiệm của driver. [Kubernetes — Volume permission and ownership change](https://kubernetes.io/docs/tasks/configure-pod-container/security-context/#configure-volume-permission-and-ownership-change-policy-for-pods).

### 8.4. Nhóm bổ sung có thể đến từ image

Tùy chính sách và khả năng hỗ trợ, thông tin nhóm trong image có thể được kết hợp với nhóm khai báo.

Do đó, nhìn một danh sách supplementalGroups trong manifest chưa đủ để kết luận tiến trình chỉ có đúng những group đó.

Một số phiên bản và runtime hỗ trợ `supplementalGroupsPolicy: Strict`. Nếu cần dùng, phải xác minh cluster và node có hỗ trợ, rồi đọc trạng thái thực tế; không đưa vào mọi manifest mà bỏ qua tính tương thích.

### 8.5. Volume chỉ đọc vẫn có thể chứa dữ liệu nhạy cảm

Mount chỉ đọc ngăn một số thao tác ghi, nhưng không ngăn đọc và gửi dữ liệu ra nơi khác.

Nếu không cần một secret hoặc credential, cách giảm quyền phù hợp thường là không cung cấp nó cho container đó, thay vì chỉ mount ở chế độ read-only.

## 9. Manifest minh họa cho workload Linux có quyền hạn chế

Giả sử namespace `workload-lab` đã được chuẩn bị. Image của ứng dụng được xây để:

- Chạy được với UID/GID 10001.
- Không cần capability bổ sung.
- Đọc cấu hình từ image mà không sửa file hệ thống.
- Chỉ ghi dữ liệu tạm vào `/tmp`.
- Không cần gọi Kubernetes API.
- Nếu phục vụ HTTP, ứng dụng tự được cấu hình nghe trên cổng 8080.

Tên image dưới đây là placeholder. Cần thay bằng image đã được phê duyệt và kiểm chứng; manifest không hứa rằng một image bất kỳ sẽ chạy với các điều kiện này.

```yaml
apiVersion: v1
kind: Pod
metadata:
  name: context-demo
  namespace: workload-lab
  labels:
    app: context-demo
spec:
  os:
    name: linux

  automountServiceAccountToken: false
  hostNetwork: false
  hostPID: false
  hostIPC: false

  securityContext:
    runAsNonRoot: true
    runAsUser: 10001
    runAsGroup: 10001
    fsGroup: 20001
    seccompProfile:
      type: RuntimeDefault

  containers:
    - name: application
      image: registry.example.net/pam/context-demo:approved

      securityContext:
        privileged: false
        allowPrivilegeEscalation: false
        readOnlyRootFilesystem: true
        capabilities:
          drop:
            - ALL

      ports:
        - name: http
          containerPort: 8080

      volumeMounts:
        - name: scratch
          mountPath: /tmp

      resources:
        requests:
          cpu: 100m
          memory: 64Mi
        limits:
          cpu: 250m
          memory: 128Mi

  volumes:
    - name: scratch
      emptyDir:
        sizeLimit: 64Mi
```

### 9.1. Những quyết định chính

Pod xác định danh tính mặc định và seccomp cho các container không ghi đè những trường tương ứng.

Container chính thể hiện rõ không privileged, không nhận thêm quyền qua cơ chế escalation đã nêu, không giữ capabilities trong cấu hình minh họa và không ghi vào root filesystem.

Volume scratch tạo một vùng ghi riêng. fsGroup là một phần của cấu hình quyền volume cần được kiểm chứng, không phải lý do bỏ kiểm tra ownership và mode thực tế.

Các giá trị tài nguyên chỉ để minh họa; phải được điều chỉnh theo nhu cầu workload.

### 9.2. Những điều manifest chưa giải quyết

Manifest không tự cấu hình:

- NetworkPolicy hoặc giới hạn egress.
- RoleBinding cho con người hoặc workload.
- Quyền cloud và credential ứng dụng.
- Độ tin cậy của image hoặc chuỗi cung ứng.
- Chính sách admission của cluster.
- Hệ thống ghi phiên và audit.
- Giới hạn thời gian cho một ngoại lệ PAM.
- Toàn bộ yêu cầu vận hành của ứng dụng production.

Không dùng một manifest “hardened” làm bằng chứng đã hoàn tất mọi lớp bảo mật.

### 9.3. Tắt automount token không phải tắt mọi API access

`automountServiceAccountToken: false` kiểm soát việc tự động mount theo cơ chế đó. Nó không tự chặn kết nối mạng tới API server hoặc vô hiệu hóa credential được cung cấp bằng đường khác.

Nếu container vẫn có token chiếu vào volume riêng, key trong file hoặc danh tính khác có thể nhận credential, cần quản lý những đường đó độc lập.

## 10. Rà soát tất cả container và những trường ngoài securityContext

### 10.1. Init container

Một init container có thể hoàn tất trước khi container chính chạy nhưng vẫn tác động tới volume hoặc môi trường dùng chung.

Nếu nó được cấp root hay privileged để chuẩn bị dữ liệu, các thay đổi tạo ra vẫn có thể tồn tại sau khi init container kết thúc.

Cần xác định công việc có thể được giải quyết ở build hoặc bằng cơ chế quyền volume phù hợp hay không, thay vì mặc định thêm init container đặc quyền.

### 10.2. Sidecar

Sidecar có thể có cấu hình, volume và credential khác container chính. Một proxy, agent hoặc collector cũng cần tập quyền riêng theo nhiệm vụ.

Không kết luận Pod non-root hoặc không có quyền nhạy cảm chỉ vì container ứng dụng đã được giới hạn.

### 10.3. Ephemeral container và luồng debug

Thêm một container debug là một thay đổi cần thẩm quyền. Khả năng truy cập dữ liệu, namespace tiến trình hoặc công cụ phụ thuộc cấu hình và đường debug thực tế.

Quy trình hỗ trợ cần xác định ai được thêm, image nào được dùng, quyền nào được nhận và làm thế nào kết thúc hoạt động debug.

Không coi nó là một ngoại lệ nằm ngoài phạm vi PAM.

### 10.4. Host namespaces, hostPath và thiết bị

Những trường như hostNetwork, hostPID, hostIPC và các mount từ host không chỉ được quyết định bởi một trường securityContext.

Một manifest có non-root và seccomp vẫn cần được xem xét nếu yêu cầu các khả năng tiếp cận host.

Tương tự, việc đưa socket quản trị hoặc credential của một dịch vụ mạnh vào container có thể tạo đường đặc quyền không được mô tả đầy đủ bằng UID.

## 11. Pod Security Standards và admission

### 11.1. Cấu hình đề nghị khác với điều kiện bắt buộc

Security context trong manifest mô tả điều workload yêu cầu. Nếu người được sửa workload có thể bỏ các trường hạn chế, cần một kiểm soát ở nơi chấp nhận đối tượng để giữ baseline.

Pod Security Standards định nghĩa các mức Privileged, Baseline và Restricted. Những yêu cầu cụ thể phụ thuộc phiên bản và có phân biệt hệ điều hành.

Restricted không phải một cam kết rằng ứng dụng hoàn toàn an toàn. Ví dụ, không được suy luận rằng đạt mức này tự chứng minh root filesystem chỉ đọc hoặc workload không có quyền dữ liệu nhạy cảm. [Kubernetes — Pod Security Standards](https://kubernetes.io/docs/concepts/security/pod-security-standards/).

### 11.2. Enforce, audit và warn

Trong Pod Security Admission:

- Enforce có thể từ chối Pod vi phạm chính sách được chọn.
- Audit ghi nhận vi phạm theo cơ chế audit.
- Warn đưa ra cảnh báo nhưng không tương đương việc từ chối.

Cần xem đúng chế độ và phiên bản chính sách đang áp dụng. Không mô tả một namespace chỉ bật warn là đã chặn Pod vi phạm. [Kubernetes — Pod Security Admission](https://kubernetes.io/docs/concepts/security/pod-security-admission/).

### 11.3. Workload template và Pod thực tế

Một Deployment chứa Pod template. Deployment được API chấp nhận chưa tự chứng minh các Pod mà controller tạo ra sẽ khởi chạy.

Cần kiểm tra rollout, sự kiện và trạng thái Pod thực tế. Đặc biệt, một điều kiện admission hoặc runtime có thể khiến workload không đạt trạng thái hoạt động dù đối tượng quản lý đã tồn tại.

### 11.4. Bảo vệ người có quyền thay baseline

Người sửa namespace label, cấu hình admission hoặc ngoại lệ có thể ảnh hưởng tới việc thực thi chính sách.

PAM cần kiểm kê và giới hạn những quyền đó, không chỉ quyền sửa Deployment. Nếu cùng một người vừa yêu cầu ngoại lệ vừa tự tắt lớp enforce, ranh giới phê duyệt có thể không còn hiệu lực.

## 12. Kiểm chứng từ manifest tới runtime

Cần phân biệt bốn trạng thái:

1. Cấu hình nguồn đã được phê duyệt.
2. PodSpec được API chấp nhận sau các xử lý liên quan.
3. Container thực sự được runtime khởi chạy.
4. Tiến trình và ứng dụng có quyền, hành vi đúng kỳ vọng.

### 12.1. Đọc lại PodSpec

Ví dụ lệnh đọc trong lab:

```bash
kubectl --context=pam-lab get pod context-demo   --namespace=workload-lab -o yaml

kubectl --context=pam-lab describe pod context-demo   --namespace=workload-lab
```

Các lệnh trong bài là ví dụ cho người học; chúng chưa được chạy vào cluster trong quá trình soạn tài liệu.

Cần kiểm tra image, security context, mount, trạng thái và sự kiện. Nội dung đọc lại cũng có thể chứa thông tin nhạy cảm; chỉ lưu phần cần thiết trong bằng chứng.

### 12.2. Kiểm tra danh tính và thuộc tính tiến trình

Nếu image lab có công cụ cần thiết và người học có quyền exec được phê duyệt:

```bash
kubectl --context=pam-lab exec context-demo   --namespace=workload-lab --container=application -- id

kubectl --context=pam-lab exec context-demo   --namespace=workload-lab --container=application -- cat /proc/1/status
```

Có thể xem UID, GID, các group, capabilities và những trường như NoNewPrivs hoặc Seccomp.

Những giá trị cần được diễn giải đúng:

- NoNewPrivs cho biết trạng thái cơ chế tương ứng của tiến trình được quan sát.
- Seccomp ở chế độ lọc không tự cho biết toàn bộ nội dung profile.
- Capabilities cần được đánh giá theo các tập và cơ chế Linux thích hợp.
- Danh tính của tiến trình đầu tiên không tự mô tả mọi tiến trình vào mọi thời điểm.

Nếu image không có shell hoặc công cụ đọc trạng thái, không tự thêm một image debug quyền rộng vào production. Chọn một cách quan sát đã được phê duyệt hoặc kiểm chứng trong lab đại diện.

### 12.3. Thử quyền ghi có kiểm soát

Trong lab, xác định trước một đường dẫn thử dưới root filesystem và một đường dẫn trong volume scratch.

Kỳ vọng là không ghi được vào vùng root filesystem chỉ đọc, nhưng ghi được đúng vùng scratch nếu quyền volume phù hợp.

Không dùng file hệ thống hoặc dữ liệu nghiệp vụ thật làm mục tiêu thử. Cũng không suy ra root filesystem chỉ đọc từ việc một file thất bại vì thiếu quyền DAC; cần phân biệt nguyên nhân.

### 12.4. Thử chức năng nghiệp vụ

Ứng dụng cần khởi chạy, xử lý tác vụ đại diện, ghi đúng vùng được cấp và dừng bình thường.

Một container Running chưa chứng minh mọi đường code đều tương thích với non-root, root filesystem chỉ đọc hoặc seccomp.

Cần kiểm tra những tác vụ ít xảy ra như rotation file, tạo cache, cập nhật thư viện hoặc xử lý một loại dữ liệu đặc biệt theo phạm vi ứng dụng.

## 13. Chẩn đoán lỗi mà không mở rộng quyền tùy tiện

| Triệu chứng | Hướng kiểm tra trước | Điều không nên mặc định |
|---|---|---|
| Container không chạy với yêu cầu non-root | UID hiệu lực, metadata image, đường executable | Tắt runAsNonRoot cho mọi workload |
| Permission denied khi ghi file | Đường dẫn, UID/GID, mode, ACL, volume | Bật privileged hoặc mở quyền mọi user |
| Read-only filesystem | Ứng dụng đang ghi vào đâu? | Mở lại toàn bộ root filesystem |
| Lỗi thao tác hệ thống | Syscall, capabilities, profile và runtime | Chuyển ngay sang Unconfined |
| Mount hoặc ghi volume thất bại | Driver, fsGroup, quyền storage, cơ chế MAC | Cho init container root chạy chown tùy ý |
| Ứng dụng gọi API bị từ chối | Credential, ServiceAccount, RBAC hoặc quyền đích | Đổi UID thành 0 để sửa lỗi API |
| Chỉ lỗi trên một nhóm node | Kernel, runtime, profile, cấu hình node | Coi manifest giống nhau là runtime giống nhau |

### 13.1. Phân biệt lỗi khởi tạo và lỗi runtime

Một container chưa được tạo có thể cần xem events và trạng thái từ kubelet, không có application log để đọc.

Một container khởi chạy rồi lỗi sau một tác vụ cần xem hành vi thực tế, đường file hoặc profile liên quan.

Giữ rõ điều đã quan sát và suy luận. Không ghi “seccomp gây lỗi” chỉ vì ứng dụng bị từ chối mà chưa có bằng chứng phù hợp.

### 13.2. Lỗi volume không phải lúc nào cũng giải quyết bằng root

Storage có thể có ACL, chính sách export, cơ chế MAC hoặc hành vi driver riêng. Root trong container không tự có quyền vượt mọi kiểm soát đó.

Cần sửa đúng lớp. Một thay đổi đệ quy ownership trên volume dùng chung còn có thể ảnh hưởng workload khác.

### 13.3. Mọi tăng quyền đều cần phạm vi

Nếu xác nhận ứng dụng cần một quyền bổ sung, ghi rõ:

- Thao tác cần quyền.
- Container và phiên bản image liên quan.
- Phạm vi dữ liệu hoặc host có thể bị tác động.
- Kiểm soát bổ sung.
- Cách kiểm thử.
- Người phê duyệt và thời hạn rà soát.

Không để một thay đổi tạm khi xử lý lỗi trở thành baseline thường trực mà không được đánh giá.

## 14. PAM cho ngoại lệ security context

### 14.1. Ngoại lệ là một grant cần được quản lý

Một ngoại lệ có thể liên quan chạy UID 0, bổ sung capability, dùng profile khác hoặc tiếp cận tài nguyên host.

Cần xác định nó thuộc workload, container và phiên bản nào. Không cấp ngoại lệ cho toàn namespace nếu nhu cầu chỉ thuộc một tác vụ hẹp mà hệ thống có thể phân biệt.

Ví dụ hồ sơ nội bộ:

```yaml
exception_reference: EXCEPTION-DEMO-036

target:
  cluster_reference: cluster-demo-a
  namespace: platform-maintenance
  workload_reference: maintenance-job-demo
  container_reference: worker
  image_reference: approved-image-record-demo

requested_change:
  control_reference: one-specific-runtime-capability
  purpose_reference: approved-maintenance-task
  expected_resource_scope: resource-set-demo

approval:
  owner_reference: platform-owner
  reviewer_reference: security-reviewer
  change_reference: CHANGE-DEMO-611

validity:
  expires_at: "2030-07-21T03:00:00Z"

closure:
  source_configuration_reference: baseline-config-demo
  runtime_verification_reference: pending
```

Đây là dữ liệu quản trị minh họa, không phải một Kubernetes resource tự thực thi hết hạn.

### 14.2. JIT không tự làm biến mất quyền tiến trình

Hết hạn phê duyệt hoặc thu hồi quyền sửa workload không tự biến container đang privileged thành container bị hạn chế.

Cần có kế hoạch chấm dứt hoặc thay thế workload theo cơ chế hỗ trợ, rồi xác minh tiến trình mới thực sự dùng baseline.

Nhiều trường security context không phải cấu hình có thể tùy ý sửa nóng trên Pod đang chạy. Khi vận hành cần dùng quy trình rollout hoặc tái tạo phù hợp, giữ rõ tác động tới dịch vụ.

### 14.3. Phải sửa cả nguồn desired state

Nếu chỉ thay Pod hiện tại nhưng Deployment hoặc hệ thống GitOps vẫn chứa ngoại lệ, workload có thể được tạo lại với quyền cũ.

Kết thúc ngoại lệ cần cập nhật nguồn được quản lý, kiểm tra những Pod thực tế và đối soát các đối tượng còn tồn tại.

### 14.4. Đánh giá tác động còn lại

Một tiến trình từng có quyền mạnh có thể đã sửa dữ liệu volume hoặc tạo thay đổi ở hệ thống bên ngoài.

Khôi phục security context không tự hoàn tác mọi tác động đó. Nếu có nghi ngờ lạm dụng, cần điều tra dữ liệu, credential và những hành động liên quan.

## 15. Audit và bằng chứng cần lưu

### 15.1. Bằng chứng cấu hình

Có thể cần:

- Bản thay đổi đã được phê duyệt.
- Workload template và PodSpec thực tế.
- Định danh image cùng phiên bản hoặc digest được quản lý.
- Những container và volume liên quan.
- Chính sách admission và ngoại lệ áp dụng.
- Node hoặc nhóm node thực thi nếu ảnh hưởng khả năng hỗ trợ.

Không cần sao chép toàn bộ dữ liệu volume để chứng minh security context.

### 15.2. Bằng chứng runtime

Ghi nhận những thuộc tính đã kiểm tra và cách thu thập: UID, GID, group, profile, mount và kết quả chức năng đại diện.

Phải phân biệt:

- Đã khai báo.
- Đã được API chấp nhận.
- Đã được runtime áp dụng theo quan sát.
- Đã kiểm thử hành vi.
- Chưa đủ bằng chứng.

Một nhãn “compliant” chung không mô tả được những mức này.

### 15.3. Bảo vệ nội dung bằng chứng

Không đưa token, nội dung Secret hoặc dữ liệu nghiệp vụ vào báo cáo chẩn đoán.

Ngay cả log ứng dụng và PodSpec cũng có thể chứa thông tin nhạy cảm do cách ứng dụng cấu hình. Chọn phạm vi lưu phù hợp và giới hạn người đọc.

### 15.4. Theo dõi thay đổi làm rộng quyền

Có thể theo dõi các thay đổi như:

- Chuyển sang privileged.
- Đổi UID về 0 hoặc bỏ yêu cầu non-root.
- Bổ sung capability.
- Chuyển seccomp sang Unconfined.
- Mở lại root filesystem khi baseline yêu cầu chỉ đọc.
- Thêm host mount hoặc quyền tiếp cận host.
- Bổ sung container debug hoặc init có quyền mạnh.
- Thay chính sách admission hoặc ngoại lệ liên quan.

Tín hiệu cần được gắn với change và phiên bản workload. Một thay đổi có phê duyệt vẫn cần được kiểm chứng đúng phạm vi, không chỉ tìm thấy mã ticket là đóng cảnh báo.

## 16. Tình huống: ứng dụng ghi cache bị lỗi sau hardening

Ứng dụng xử lý báo cáo trước đây chạy bằng UID 0. Sau khi chuyển non-root và root filesystem chỉ đọc, ứng dụng lỗi khi tạo cache ở một đường dẫn dưới thư mục cài đặt.

Nhóm đề xuất bật privileged để tránh lỗi quyền.

### 16.1. Phân tích nguyên nhân

Cần xác định:

- Ứng dụng có thật sự cần sửa thư mục cài đặt hay chỉ đang dùng đường dẫn cache mặc định?
- Có cấu hình chuyển cache sang vùng ghi riêng không?
- UID/GID nào đang chạy?
- Directory cần ghi thuộc volume hay root filesystem?
- Có driver hoặc MAC policy nào tham gia không?
- Lỗi xảy ra ở container chính hay init container?

### 16.2. Hướng xử lý phù hợp nhiệm vụ

Nếu cache không cần nằm trong thư mục cài đặt, có thể chuyển sang một đường dẫn riêng và mount vùng tạm hoặc storage phù hợp.

Image cần có quyền đọc executable và cấu hình cho UID được chọn. Volume ghi cần đúng ownership và quyền, không mở rộng toàn bộ filesystem.

Privileged không phải yêu cầu nghiệp vụ của việc tạo cache. Bật nó làm tăng phạm vi tác động mà chưa giải quyết thiết kế quyền file một cách rõ ràng.

### 16.3. Điều cần kiểm chứng sau thay đổi

- Ứng dụng chạy bằng UID/GID mong muốn.
- Root filesystem vẫn chỉ đọc.
- Chỉ vùng cache được ghi theo phạm vi dự kiến.
- Tác vụ báo cáo đại diện hoạt động.
- Không đưa credential vào cache hoặc log ngoài ý định.
- Những container khác không nhận thêm quyền.
- Desired state và Pod runtime khớp phương án được duyệt.

## 17. Ma trận kiểm chứng

Những kiểm chứng sau dành cho môi trường và công việc được phép.

| Nội dung | Thử nghiệm đại diện | Kết quả cần chứng minh |
|---|---|---|
| Non-root | Xem danh tính tiến trình | UID hiệu lực đúng và khác 0 theo thiết kế |
| Group | Xem group và quyền volume | Không có quyền nhóm ngoài kỳ vọng chưa được giải thích |
| Root filesystem | Thử ghi tại đường dẫn lab định sẵn | Không ghi được vì cơ chế chỉ đọc mong muốn |
| Vùng scratch | Ghi dữ liệu thử không nhạy cảm | Chỉ ghi được trong phạm vi đã cấp |
| Capabilities | Quan sát trạng thái runtime | Phù hợp cấu hình và nhu cầu |
| no_new_privs | Quan sát thuộc tính tiến trình | Cơ chế tương ứng được áp dụng |
| Seccomp | Kiểm tra profile và hành vi đại diện | Đúng profile, ứng dụng vẫn hoạt động |
| Toàn bộ container | Rà soát init, sidecar và debug | Không có đường quyền mạnh bị bỏ sót |
| Admission | Gửi cấu hình vi phạm trong lab theo kế hoạch | Bị xử lý đúng chế độ enforce, audit hoặc warn |
| Ngoại lệ | Kết thúc cửa sổ bảo trì | Nguồn cấu hình và workload thực tế trở lại baseline |
| Danh tính API | Kiểm tra đường credential | UID hạn chế không che giấu quyền API rộng |
| Tái tạo workload | Kiểm tra rollout hoặc controller | Không tạo lại Pod với ngoại lệ đã hết hạn |

Không chỉ kiểm tra một container đang Running rồi đánh dấu tất cả PASS. Cần chọn bằng chứng phù hợp từng mục.

## 18. Bài tập phân tích

Một Pod có container chính chạy UID 10001, `runAsNonRoot: true` và `readOnlyRootFilesystem: true`.

Trong cùng Pod:

- Một init container chạy đặc quyền để sửa quyền volume.
- Một volume chứa credential được mount chỉ đọc vào container chính.
- ServiceAccount của workload có quyền Kubernetes rộng.
- Không khai báo rõ profile seccomp.
- Namespace chỉ bật chế độ cảnh báo cho Pod security.
- Ngoại lệ init container có ngày hết hạn trong ticket nhưng chưa có kế hoạch rollout.

Nhóm kết luận Pod đã đạt least privilege vì container chính không chạy root và không ghi được root filesystem.

Hãy trả lời:

1. Những lớp quyền nào đang bị trộn lẫn trong kết luận?
2. Mount credential chỉ đọc có ngăn container sử dụng credential không?
3. Init container đặc quyền có thể để lại tác động nào?
4. Chế độ cảnh báo có giữ baseline bắt buộc không?
5. Hết hạn ticket có thay đổi Pod đang chạy không?
6. Cần những bằng chứng nào để kết luận ngoại lệ đã kết thúc?

### Hướng phân tích

Kết luận chỉ xem một phần quyền tiến trình của container chính. Nó chưa bao phủ API identity, volume, init container, profile kernel và admission.

Credential mount chỉ đọc vẫn có thể được đọc và dùng theo quyền của tiến trình cùng cơ chế xác thực ở đích. Cần giảm hoặc loại bỏ credential không cần thiết và giới hạn quyền của principal.

Init container có thể đã thay ownership hoặc dữ liệu trên volume; việc nó hoàn tất không tự khôi phục các thay đổi.

Warn không tương đương enforce. Cần kiểm chứng chính sách thực sự chặn những cấu hình ngoài baseline khi yêu cầu tổ chức là bắt buộc.

Ticket hết hạn chỉ thay đổi trạng thái quản trị nếu không có hành động thực thi. Cần cập nhật desired state, thay thế workload theo kế hoạch, đọc lại Pod và kiểm chứng runtime mới.

Nếu từng có quyền mạnh, còn phải đối soát tác động còn lại theo phạm vi công việc hoặc sự cố, không chỉ kiểm tra trường privileged đã trở về false.

## 19. Những điểm cần nhớ

Pod security context quản lý một phần quyền hệ điều hành và runtime của workload. Nó cần phối hợp với RBAC, danh tính workload, credential, mạng và admission.

Non-root, hạn chế tăng quyền, capabilities tối thiểu, seccomp và root filesystem chỉ đọc giải quyết các khía cạnh khác nhau. Không một trường riêng lẻ nào chứng minh workload đã đạt least privilege.

Quyền volume cần được kiểm chứng cùng UID, GID, group, loại storage và driver. Volume chỉ đọc vẫn có thể làm lộ dữ liệu hoặc credential cho tiến trình có quyền đọc.

Trong PAM, ngoại lệ security context phải có phạm vi, phê duyệt, bằng chứng và cách kết thúc thực tế. Hết hạn một grant hoặc ticket không tự làm thay đổi quyền của tiến trình đang chạy.
