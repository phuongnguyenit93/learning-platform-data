# Chính sách bảo mật Pod và filesystem chỉ đọc

## 1. Mục tiêu và phạm vi

Trong chương **Bảo mật tích hợp** của module **SPRING_CLOUD_KUBERNETES**, bài này hướng dẫn chạy ứng dụng Spring trên Kubernetes với quyền hạn chế, root filesystem chỉ đọc và những vùng ghi được khai báo rõ ràng.

Sau bài học, bạn có thể:

- Phân biệt Pod Security Standards, Pod Security Admission, security context và RBAC.
- Chạy container bằng người dùng không phải root, không cho tăng đặc quyền và không giữ capability không cần thiết.
- Bật `readOnlyRootFilesystem` mà vẫn đáp ứng nhu cầu tạo tệp tạm của JVM.
- Đọc ConfigMap, Secret và credential Kubernetes mà không mở quyền ghi vào toàn bộ container.
- Kiểm chứng cả chính sách admission lẫn hành vi thực tế khi ứng dụng chạy.

Các ví dụ áp dụng cho **Linux container**. UID/GID, đường dẫn, dung lượng và tài nguyên là lựa chọn minh họa, phải phù hợp với image và workload thực tế. Không suy từ một cấu hình Linux sang Windows container.

Tình huống xuyên suốt: `orders-api` chạy Spring Boot, có thể dùng DiscoveryClient và Spring Cloud LoadBalancer, đọc ConfigMap/Secret và nhận refresh từ Configuration Watcher. Nhóm triển khai muốn giảm khả năng thay đổi tệp ứng dụng sau khi container đã chạy.

## 2. Phân biệt các lớp kiểm soát

| Lớp | Câu hỏi được giải quyết | Ví dụ |
| --- | --- | --- |
| Pod Security Standards, viết tắt PSS | Pod được phép có những đặc điểm bảo mật nào? | Các mức `privileged`, `baseline`, `restricted` |
| Pod Security Admission, viết tắt PSA | Khi Pod vi phạm chuẩn thì cảnh báo, ghi nhận hay từ chối? | Nhãn namespace `enforce: restricted` |
| Security context | Container thực sự được cấu hình chạy như thế nào? | UID, seccomp, capabilities, root filesystem chỉ đọc |
| Quyền tệp và volume | Tiến trình nào được đọc/ghi đường dẫn nào? | Secret chỉ đọc, vùng tạm ghi được |
| RBAC | Danh tính được làm thao tác nào trên Kubernetes API? | Đọc Service nhưng không đọc Secret qua API |
| Chính sách mạng và xác thực HTTP | Kết nối nào được phép và caller là ai? | Giới hạn caller của `/actuator/refresh` |

Một Pod có RBAC rất hẹp vẫn có thể chạy bằng root nếu security context và admission cho phép. Ngược lại, container không phải root vẫn có thể dùng token được cấp quá nhiều quyền để gọi Kubernetes API.

### 2.1. “Chính sách bảo mật Pod” không phải API PodSecurityPolicy cũ

`PodSecurityPolicy` là API đã bị loại bỏ từ Kubernetes 1.25. Với cluster hiện đại, dùng PSA/PSS và cơ chế admission bổ sung phù hợp thay vì tạo manifest `kind: PodSecurityPolicy`. Xem [Pod Security Policies](https://kubernetes.io/docs/concepts/security/pod-security-policy/).

### 2.2. Restricted không tự bắt buộc root filesystem chỉ đọc

PSS `restricted` đặt yêu cầu chặt hơn về người dùng không phải root, tăng đặc quyền, seccomp và capabilities. Tuy nhiên, `readOnlyRootFilesystem` không phải yêu cầu bắt buộc của chuẩn này. Bảng ánh xạ chính thức thể hiện chuẩn không đặt điều kiện cho trường đó. Xem [ánh xạ PSS](https://kubernetes.io/docs/reference/access-authn-authz/psp-to-pod-security-standards/).

Vì thế cần tách hai quyết định:

~~~text
Pod đáp ứng restricted
        +
Mỗi container phải bật readOnlyRootFilesystem
        +
Chỉ mở vùng ghi thực sự cần
~~~

PSA không tự điền tất cả trường còn thiếu để làm Pod an toàn. Muốn bắt buộc root filesystem chỉ đọc trên toàn bộ workload thuộc một phạm vi, cần thêm chính sách kiểm tra trường đó.

## 3. Thiết kế security context

### 3.1. Các trường cần hiểu đúng

| Trường | Vị trí trong ví dụ | Mục đích |
| --- | --- | --- |
| `runAsNonRoot: true` | Security context của Pod | Yêu cầu tiến trình không chạy bằng UID 0 |
| `runAsUser: 10001` | Security context của Pod | Chọn UID số đã kiểm chứng với image |
| `runAsGroup: 10001` | Security context của Pod | Chọn nhóm chính |
| `fsGroup: 10001` | Security context của Pod | Hỗ trợ quyền nhóm trên volume phù hợp |
| `seccompProfile.type: RuntimeDefault` | Security context của Pod | Dùng hồ sơ seccomp mặc định của runtime |
| `allowPrivilegeEscalation: false` | Security context của từng container | Không cho tiến trình tăng đặc quyền theo cơ chế tương ứng |
| `capabilities.drop: [ALL]` | Security context của từng container | Bỏ các Linux capability mặc định |
| `readOnlyRootFilesystem: true` | Security context của từng container | Mount root filesystem của container ở chế độ chỉ đọc |

Security context của Pod và container có phạm vi khác nhau. Những trường như `readOnlyRootFilesystem`, `allowPrivilegeEscalation` và `capabilities` phải được đặt ở container, không đưa nhầm vào `spec.securityContext`. Xem [Security Context](https://kubernetes.io/docs/tasks/configure-pod-container/security-context/).

Ví dụ phần chung:

~~~yaml
spec:
  securityContext:
    runAsNonRoot: true
    runAsUser: 10001
    runAsGroup: 10001
    fsGroup: 10001
    seccompProfile:
      type: RuntimeDefault
  containers:
    - name: orders-api
      securityContext:
        privileged: false
        allowPrivilegeEscalation: false
        readOnlyRootFilesystem: true
        capabilities:
          drop: ["ALL"]
~~~

Đây là đoạn cấu hình cần ghép vào PodSpec có image và các trường khác.

Với các kiểm soát Linux của PSS restricted, từng container phải đáp ứng yêu cầu tương ứng; container thường, init container và ephemeral container đều cần được xét. Các capability được phép thêm lại rất hạn chế. Xem [Pod Security Standards](https://kubernetes.io/docs/concepts/security/pod-security-standards/).

### 3.2. Non-root không thay thế readonly

Người dùng không phải root vẫn có thể ghi vào tệp hoặc thư mục do mình sở hữu nếu mount cho phép ghi. Nếu ứng dụng sở hữu toàn bộ `/app`, chỉ đặt `runAsNonRoot` chưa ngăn sửa tệp ở đó.

Ngược lại, root filesystem chỉ đọc không tự loại bỏ quyền mạng, quyền đọc bí mật hoặc capability. Các kiểm soát phải kết hợp theo tác dụng riêng.

Image phải hỗ trợ UID đã chọn:

- JRE, JAR và thư viện cần đọc được bằng UID/GID tương ứng.
- Entrypoint không được phụ thuộc vào việc cài gói, sửa `/etc` hoặc `chown` tệp image lúc khởi động.
- Không bắt buộc tiến trình phải sở hữu tệp JAR; chỉ cần quyền đọc phù hợp.
- Nếu image hỗ trợ UID tùy chọn theo quy ước của nền tảng, dùng quy ước đó thay vì áp UID 10001 một cách máy móc.

`fsGroup` không sửa quyền toàn bộ filesystem của image. Nó phục vụ volume hỗ trợ cơ chế quyền nhóm; cần kiểm chứng loại volume/driver thực tế.

## 4. Root filesystem chỉ đọc và các vùng ghi ngoại lệ

### 4.1. Phạm vi của readOnlyRootFilesystem

`readOnlyRootFilesystem: true` tác động tới root filesystem của container. Volume mount có cơ chế và quyền truy cập riêng.

~~~mermaid
flowchart TD
    P["Tiến trình Spring/JVM, UID không phải root"]
    ROOT["Root filesystem: /app, JRE, thư viện — chỉ đọc"]
    TMP["emptyDir tại /tmp — được ghi"]
    CFG["ConfigMap tại /etc/orders/config — chỉ đọc"]
    SEC["Secret tại /etc/orders/secret — chỉ đọc"]
    TOK["Projected token nếu cần API — ứng dụng chỉ đọc"]
    P --> ROOT
    P --> TMP
    P --> CFG
    P --> SEC
    P --> TOK
~~~

Một volume ghi được không tự trở thành chỉ đọc vì root filesystem đã khóa. Cần đánh giá riêng từng mount và đặt `volumeMounts[].readOnly` khi không cần ghi. Xem [Volumes](https://kubernetes.io/docs/concepts/storage/volumes/).

### 4.2. Lập bản đồ đường dẫn

| Đường dẫn/nhu cầu | Chính sách đề xuất cho ví dụ | Lý do |
| --- | --- | --- |
| `/app`, JAR, JRE, thư viện đóng gói | Chỉ đọc | Không sửa mã và runtime khi khởi động |
| `/tmp` | `emptyDir` ghi được, có ngân sách | Tệp tạm được phép tạo/xóa |
| `/etc/orders/config` | ConfigMap, chỉ đọc từ container | Ứng dụng tiêu thụ cấu hình |
| `/etc/orders/secret` | Secret, chỉ đọc, giới hạn quyền tệp | Không cho ứng dụng sửa nguồn bí mật |
| ServiceAccount token/CA nếu cần | Mount do Kubernetes quản lý, chỉ đọc từ ứng dụng | Không sao chép token sang root filesystem |
| Log ứng dụng | stdout/stderr | Không cần một thư mục log ghi được trong image |
| Heap dump/JFR nếu có yêu cầu | Volume riêng với dung lượng và quyền rõ ràng | Dữ liệu lớn và có thể chứa bí mật |
| Dữ liệu nghiệp vụ cần tồn tại lâu | Kho bền vững được thiết kế riêng | Không dùng vùng tạm như cơ sở dữ liệu |

Không mount `emptyDir` lên cả `/app` để giải quyết một lỗi tạo tệp tạm. Mount như vậy có thể che mất JAR trong image và mở quá rộng vùng ghi.

Không mount volume trên toàn bộ `/etc` hoặc cây chứa credential chỉ để cho phép một thư viện tạo cache. Hãy đổi đúng vị trí cache hoặc chuẩn bị tệp cần thiết từ giai đoạn build.

### 4.3. Vùng tạm cũng cần giới hạn tài nguyên

`emptyDir` phù hợp với dữ liệu tạm theo vòng đời Pod. Container restart trong cùng Pod và Pod bị thay thế là hai tình huống khác nhau; không dùng `emptyDir` để cam kết giữ dữ liệu qua việc thay Pod.

Có hai lựa chọn cần cân nhắc:

| Loại vùng tạm | Điều cần tính |
| --- | --- |
| `emptyDir` dùng lưu trữ node | Ngân sách ephemeral storage, dung lượng node và cơ chế theo dõi/eviction |
| `emptyDir.medium: Memory` | Dữ liệu tmpfs dùng bộ nhớ; cần tính chung với nhu cầu JVM và giới hạn memory |

Kubernetes theo dõi tmpfs như memory thay vì local ephemeral storage. Vì vậy, chuyển `/tmp` sang RAM không làm mất chi phí tài nguyên. Xem [Resource Management](https://kubernetes.io/docs/concepts/configuration/manage-resources-containers/).

`sizeLimit` không biến mọi loại `emptyDir` thành một phân vùng được dành sẵn với cơ chế quota tức thời giống nhau. Cần kiểm tra hành vi loại volume, kế toán tài nguyên của node và chính sách eviction. Đặc biệt, không chọn vùng tạm nhỏ rồi kỳ vọng chứa được heap dump lớn.

## 5. Ví dụ triển khai: cấu hình và Secret qua volume

Ví dụ này chọn hồ sơ đơn giản: `orders-api` gọi Service qua DNS đã biết, đọc cấu hình/Secret từ tệp, không bật tính năng cần Kubernetes API trong tiến trình. Phần sau sẽ trình bày biến thể khi cần DiscoveryClient trực tiếp.

Các manifest là mẫu để thực hành trong namespace riêng. Image `registry.example.com/training/orders-api:readonly-lab` là **địa chỉ minh họa**, cần thay bằng image của bạn đã kiểm chứng chạy với UID/GID 10001, cổng 8080 và Actuator probes. Nội dung Secret là dữ liệu giả cho lab.

### 5.1. Namespace có policy được ghim phiên bản

Ví dụ ghim PSS ở `v1.35`, giả định cluster hỗ trợ phiên bản chính sách này. Đây là phiên bản minh họa để bài thực hành có quy tắc xác định, không phải khẳng định phiên bản cluster của bạn.

~~~yaml
apiVersion: v1
kind: Namespace
metadata:
  name: pod-security-lab
  labels:
    pod-security.kubernetes.io/enforce: restricted
    pod-security.kubernetes.io/enforce-version: v1.35
    pod-security.kubernetes.io/audit: restricted
    pod-security.kubernetes.io/audit-version: v1.35
    pod-security.kubernetes.io/warn: restricted
    pod-security.kubernetes.io/warn-version: v1.35
    security.example.com/rootfs-profile: readonly
~~~

Trong PSA, `enforce` từ chối Pod vi phạm; `warn` phát cảnh báo và `audit` thêm thông tin audit. Enforce kiểm tra Pod thực sự được tạo, không áp dụng trực tiếp như một phép kiểm tra đầy đủ cho Deployment. Xem [Pod Security Admission](https://kubernetes.io/docs/concepts/security/pod-security-admission/).

Nhãn `security.example.com/rootfs-profile` là nhãn do ví dụ tự đặt để chọn phạm vi cho policy bổ sung ở phần 8. Nếu chưa cài policy và binding đó, nhãn này **không tự bắt buộc readonly**.

Người tạo/cập nhật nhãn namespace và chính sách admission là chủ thể quản trị được phân quyền, không phải ServiceAccount runtime của ứng dụng.

### 5.2. Nguồn cấu hình và ServiceAccount

~~~yaml
apiVersion: v1
kind: ServiceAccount
metadata:
  name: orders-runtime
  namespace: pod-security-lab
automountServiceAccountToken: false
---
apiVersion: v1
kind: ConfigMap
metadata:
  name: orders-settings
  namespace: pod-security-lab
data:
  app.message: "Cấu hình phiên bản 1"
---
apiVersion: v1
kind: Secret
metadata:
  name: orders-db
  namespace: pod-security-lab
type: Opaque
stringData:
  db.username: "lab-user"
  db.password: "lab-only-not-a-real-password"
~~~

Ứng dụng đọc các nguồn đã mount không cần quyền GET Secret chỉ để đọc tệp trong container. Nếu có tính năng khác gọi API thì phải đánh giá riêng, không suy từ ví dụ này rằng mọi ứng dụng Spring Cloud Kubernetes đều không cần token.

### 5.3. Deployment với root filesystem chỉ đọc

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: orders-api
  namespace: pod-security-lab
spec:
  replicas: 1
  selector:
    matchLabels:
      app: orders-api
  template:
    metadata:
      labels:
        app: orders-api
    spec:
      os:
        name: linux
      serviceAccountName: orders-runtime
      automountServiceAccountToken: false
      securityContext:
        runAsNonRoot: true
        runAsUser: 10001
        runAsGroup: 10001
        fsGroup: 10001
        seccompProfile:
          type: RuntimeDefault
      containers:
        - name: orders-api
          image: registry.example.com/training/orders-api:readonly-lab
          ports:
            - name: http
              containerPort: 8080
          env:
            - name: JAVA_TOOL_OPTIONS
              value: "-Djava.io.tmpdir=/tmp"
            - name: TMPDIR
              value: "/tmp"
            - name: SPRING_CONFIG_IMPORT
              value: "configtree:/etc/orders/config/,configtree:/etc/orders/secret/"
            - name: SPRING_CLOUD_KUBERNETES_DISCOVERY_ENABLED
              value: "false"
            - name: SPRING_CLOUD_KUBERNETES_CONFIG_ENABLED
              value: "false"
            - name: SPRING_CLOUD_KUBERNETES_SECRETS_ENABLED
              value: "false"
            - name: MANAGEMENT_HEALTH_KUBERNETES_ENABLED
              value: "false"
            - name: MANAGEMENT_INFO_KUBERNETES_ENABLED
              value: "false"
            - name: MANAGEMENT_ENDPOINT_HEALTH_PROBES_ENABLED
              value: "true"
          securityContext:
            privileged: false
            allowPrivilegeEscalation: false
            readOnlyRootFilesystem: true
            capabilities:
              drop: ["ALL"]
          resources:
            requests:
              cpu: "100m"
              memory: "256Mi"
              ephemeral-storage: "128Mi"
            limits:
              cpu: "1"
              memory: "512Mi"
              ephemeral-storage: "512Mi"
          volumeMounts:
            - name: tmp
              mountPath: /tmp
            - name: config
              mountPath: /etc/orders/config
              readOnly: true
            - name: secret
              mountPath: /etc/orders/secret
              readOnly: true
          startupProbe:
            httpGet:
              path: /actuator/health/liveness
              port: http
            periodSeconds: 10
            failureThreshold: 30
          livenessProbe:
            httpGet:
              path: /actuator/health/liveness
              port: http
            periodSeconds: 10
            timeoutSeconds: 2
          readinessProbe:
            httpGet:
              path: /actuator/health/readiness
              port: http
            periodSeconds: 5
            timeoutSeconds: 2
      volumes:
        - name: tmp
          emptyDir:
            sizeLimit: "64Mi"
        - name: config
          configMap:
            name: orders-settings
            defaultMode: 0444
        - name: secret
          secret:
            secretName: orders-db
            defaultMode: 0440
~~~

Điểm cần đọc kỹ:

- `readOnlyRootFilesystem` nằm ở container; `fsGroup` và seccomp chung nằm ở Pod.
- `/tmp` là vùng ghi ngoại lệ, dùng lưu trữ mặc định của node trong mẫu này; không có `medium: Memory`.
- `JAVA_TOOL_OPTIONS` chọn thư mục tạm cho JVM; `TMPDIR` phục vụ những công cụ tôn trọng biến này. Chúng không buộc mọi thư viện dùng cùng vị trí.
- Cấu hình Spring Cloud Kubernetes qua API đã được tắt trong hồ sơ này; `configtree:` vẫn là cơ chế đọc tệp của Spring Boot.
- `0440` là dạng bát phân trong YAML. Nếu viết JSON, giá trị tương đương là 288.
- Quyền nhóm của Secret phải được kiểm tra với UID/GID và cơ chế volume thực tế. Không chữa lỗi đọc bằng `chmod 777`.
- Health endpoint và chính sách xác thực của image phải cho phép kubelet thực hiện probe như dự định. Các ngưỡng probe và resource là giá trị lab, chưa phải kết quả sizing sản xuất.

Spring Boot hỗ trợ nhập configuration tree, trong đó tên tệp trở thành khóa cấu hình. Vì vậy hai tệp `db.username`, `db.password` được đọc dưới các khóa tương ứng. Xem [Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html#features.external-config.files.configtree).

Không dùng `optional:` trong mẫu vì các nguồn này được coi là bắt buộc. Nếu chuyển chúng thành tùy chọn, phải có chính sách mặc định phù hợp với ý nghĩa nghiệp vụ.

## 6. Giữ đúng hành vi Spring Cloud Kubernetes

### 6.1. ConfigMap/Secret chỉ đọc vẫn có thể được Kubernetes cập nhật

“Chỉ đọc từ container” không có nghĩa kubelet bị cấm thay nội dung nguồn được chiếu vào volume. Đây là hai bên thực hiện khác nhau.

ConfigMap volume thông thường có thể được cập nhật sau một độ trễ; mount qua `subPath` không nhận cập nhật tự động và biến môi trường không tự đổi theo ConfigMap. Xem [ConfigMaps](https://kubernetes.io/docs/concepts/configuration/configmap/#mounted-configmaps-are-updated-automatically).

Secret volume cũng có cơ chế cập nhật nhất quán cuối cùng. Khi chẩn đoán, phân biệt quyền đọc tệp với đường cập nhật từ Kubernetes. Xem [Secrets](https://kubernetes.io/docs/concepts/configuration/secret/#using-secrets-as-files-from-a-pod).

Luồng cần quan sát:

~~~text
Nguồn trong API thay đổi
  -> kubelet chiếu nội dung mới vào volume
  -> tiến trình đọc lại nguồn
  -> Spring áp dụng vào các đối tượng phù hợp
~~~

Tệp đã đổi chưa đồng nghĩa mọi bean đã đổi. Trong ví dụ `configtree:`, nội dung được nạp vào Spring khi đọc nguồn cấu hình; không coi volume update là một cơ chế tự refresh toàn bộ ứng dụng.

Không sao chép tệp từ mount sang `/app/application.yaml` để tránh chuyện này. Cách sao chép vừa đòi ghi vào image filesystem vừa có thể làm mất quan hệ cập nhật với nguồn mount.

### 6.2. Khi cần DiscoveryClient trực tiếp

Nếu chuyển ví dụ sang Fabric8 hoặc Kubernetes Java Client để discovery, cần thay đổi hồ sơ danh tính:

1. Dùng ServiceAccount riêng đã được cấp quyền đọc tài nguyên discovery trong phạm vi cần thiết.
2. Cho phép cung cấp credential phù hợp, chẳng hạn projected token tự mount.
3. Bật lại DiscoveryClient và cấu hình namespace cần tìm.
4. Giữ nguyên các giới hạn root filesystem, capability và người dùng.
5. Kiểm tra client đọc token/CA và tiếp tục hoạt động sau token rotation.

Phần PodSpec định hướng:

~~~yaml
serviceAccountName: orders-api-reader
automountServiceAccountToken: true
~~~

`orders-api-reader` phải được tạo và bind Role tương ứng trước. Không chỉ thay tên ServiceAccount rồi cho rằng quyền đã tồn tại.

Các phần tử env thay cho cấu hình discovery bị tắt ở ví dụ trước:

~~~yaml
- name: SPRING_CLOUD_KUBERNETES_DISCOVERY_ENABLED
  value: "true"
- name: SPRING_CLOUD_KUBERNETES_DISCOVERY_NAMESPACES_0
  valueFrom:
    fieldRef:
      fieldPath: metadata.namespace
~~~

Không thêm phần tử env trùng tên với giá trị false cũ; phải thay thế đúng phần tử. ConfigMap/Secret vẫn có thể tiếp tục dùng volume như trước, nên không cần bật đường API của hai tính năng đó chỉ vì đã bật discovery.

Quyền tài nguyên phụ thuộc loại client, tính năng metadata và việc dùng Endpoints hay EndpointSlice. Xem [DiscoveryClient](https://docs.spring.io/spring-cloud-kubernetes/reference/discovery-client.html) và [cấu hình ServiceAccount cho Spring Cloud Kubernetes](https://docs.spring.io/spring-cloud-kubernetes/reference/security-service-accounts.html).

DiscoveryClient và LoadBalancer không cần được cho phép sửa JAR để tìm hoặc chọn một instance. Nếu image hoặc thư viện tùy biến có cache ghi đĩa, đánh giá đường dẫn cache đó riêng; không mặc định mọi client đều có cùng nhu cầu filesystem.

### 6.3. Token rotation không cần ứng dụng ghi vào tệp token

Kubelet quản lý projected token và xoay token; ứng dụng/client có trách nhiệm nạp lại credential khi thay đổi. Xem [ServiceAccount token projection](https://kubernetes.io/docs/tasks/configure-pod-container/configure-service-account/#serviceaccount-token-volume-projection).

Root filesystem chỉ đọc không tự chặn cơ chế cập nhật volume do kubelet quản lý. Điều cần xác minh là:

- Tiến trình đọc được token và CA với UID/GID đã chọn.
- Không mount đè lên cây đường dẫn credential.
- Không copy token sang một tệp khác rồi dùng mãi bản cũ.
- Client đúng phiên bản có cơ chế nạp lại token phù hợp.
- Token không bị in vào log hoặc response chẩn đoán.

Với token không đọc được, sửa quyền hoặc cách cung cấp credential. Với token đọc được nhưng API trả 403, điều tra authorization; không mở root filesystem để chữa RBAC.

### 6.4. Configuration Watcher và DiscoveryServer cũng là workload cần làm cứng

Nếu triển khai Watcher hoặc DiscoveryServer thành Pod riêng, kiểm tra security context cho chính các container của chúng. Cấu hình của `orders-api` không tự áp dụng sang controller hỗ trợ.

Watcher có thể phát thông báo refresh qua HTTP hoặc Bus. Cơ chế đó không đòi ứng dụng ghi đè JAR hay bật root filesystem ghi được. Xem [Configuration Watcher](https://docs.spring.io/spring-cloud-kubernetes/reference/spring-cloud-kubernetes-configuration-watcher.html).

Tuy vậy, không áp UID hoặc thư mục tạm của ví dụ lên image đóng gói sẵn mà chưa kiểm tra entrypoint và quyền tệp. Một image dùng script chuẩn bị truststore có nhu cầu khác image đã chứa truststore hoàn chỉnh.

Quyền RBAC để Watcher đọc cấu hình và quyền HTTP gọi `/actuator/refresh` vẫn là hai lớp riêng. Root filesystem chỉ đọc không xác thực người gọi refresh.

## 7. Những nơi JVM và thư viện có thể cần ghi

Một ứng dụng chỉ ghi log ra stdout vẫn có thể tạo tệp tạm.

| Nguồn ghi tiềm năng | Ví dụ | Cách thiết kế |
| --- | --- | --- |
| Java temporary files | Tệp được tạo qua API tệp tạm | Chọn `java.io.tmpdir` trên volume cho phép ghi |
| Web server hoặc multipart | Dữ liệu upload, thư mục làm việc | Giới hạn kích thước và trỏ đúng vùng tạm |
| Thư viện native/agent | Giải nén thư viện hoặc cache | Đóng gói sẵn hoặc dùng vùng riêng đã xác minh |
| Cache của thư viện | Ghi dưới user home | Cấu hình đúng đường dẫn cache; không mở cả cây home nếu không cần |
| Entrypoint | Ghi cấu hình/truststore lúc chạy | Chuẩn bị ở build hoặc đưa đầu ra vào volume hẹp |
| Chẩn đoán JVM | Heap dump, lỗi fatal, JFR | Chọn nơi ghi, ngân sách, thời hạn lưu và quyền đọc |
| Công cụ build | Cache Maven/Gradle | Hoàn tất build trước khi chạy runtime |

Java dùng thuộc tính `java.io.tmpdir` cho thư mục tạm mặc định của các API tương ứng. Đây không phải cam kết rằng mọi thư viện đều tuân theo thuộc tính này. Xem [Java File API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/io/File.html#createTempFile(java.lang.String,java.lang.String)).

### 7.1. Log và chẩn đoán

Ưu tiên stdout/stderr cho log vận hành. Nếu cấu hình `logging.file.name` hoặc appender ghi tệp, phải cung cấp volume cho đúng đường dẫn và quản lý dung lượng; chỉ có root filesystem chỉ đọc không tự chuyển log tệp thành log console.

Nếu có nhu cầu dump, có thể cấu hình vị trí bằng các tùy chọn JVM như:

~~~text
-XX:ErrorFile=/diagnostics/hs_err_pid%p.log
-XX:HeapDumpPath=/diagnostics
~~~

Các đường dẫn này chỉ hữu ích khi `/diagnostics` thực sự tồn tại, ghi được và đủ dung lượng. `HeapDumpPath` tự nó không bật việc tạo heap dump; phải chọn cơ chế kích hoạt phù hợp. Xem [java command](https://docs.oracle.com/en/java/javase/21/docs/specs/man/java.html).

Không dùng dung lượng 64Mi của `/tmp` trong mẫu làm cam kết chứa heap dump của JVM 512Mi. Không lưu dump chứa mật khẩu/token vào volume dùng chung không kiểm soát.

### 7.2. Đừng giải quyết lỗi bằng quyền quá rộng

| Cách xử lý dễ gặp | Vấn đề | Cách sửa đúng phạm vi |
| --- | --- | --- |
| Tắt readonly vì lỗi tạo tệp tạm | Mở lại toàn bộ root filesystem | Mount vùng tạm và đổi đường dẫn tạo tệp |
| Chạy root vì Secret không đọc được | Tăng quyền tiến trình không cần thiết | Kiểm tra mode, UID/GID và volume |
| Dùng `chmod 777` cho cả volume | Mở quyền rộng hơn nhu cầu | Chọn nhóm và mode phù hợp |
| Thêm `SYS_ADMIN` để thư viện hoạt động | Thay đổi đáng kể quyền container | Kiểm tra thư viện, runtime và thiết kế mount |
| Thêm init container root chỉ để sửa image | Mâu thuẫn mục tiêu restricted | Sửa quyền ở giai đoạn build hoặc thiết kế volume hỗ trợ |
| Tải dependency khi Pod khởi động | Thêm mạng, cache và nguồn thay đổi | Đóng gói dependency vào image runtime |

Làm cứng container thường đòi chỉnh cách đóng gói và cấu hình đường dẫn. Không chỉ thêm vài trường YAML vào một image còn phụ thuộc thao tác ghi khắp filesystem.

## 8. Bắt buộc readonly bằng admission policy bổ sung

Nếu tổ chức yêu cầu mọi container trong namespace phải bật readonly, có thể dùng ValidatingAdmissionPolicy hoặc cơ chế admission phù hợp khác. ValidatingAdmissionPolicy với API v1 ổn định từ Kubernetes 1.30; cần xác minh cluster cung cấp tính năng này. Xem [Validating Admission Policy](https://kubernetes.io/docs/reference/access-authn-authz/validating-admission-policy/).

Mẫu sau dành cho namespace lab Linux đã gắn nhãn `security.example.com/rootfs-profile: readonly`. Policy kiểm tra Pod thường và request thêm ephemeral container, không thay thế toàn bộ PSS.

~~~yaml
apiVersion: admissionregistration.k8s.io/v1
kind: ValidatingAdmissionPolicy
metadata:
  name: require-readonly-rootfs.example.com
spec:
  failurePolicy: Fail
  matchConstraints:
    resourceRules:
      - apiGroups: [""]
        apiVersions: ["v1"]
        operations: ["CREATE", "UPDATE"]
        resources: ["pods", "pods/ephemeralcontainers"]
  validations:
    - expression: >-
        object.spec.containers.all(c,
          has(c.securityContext) &&
          has(c.securityContext.readOnlyRootFilesystem) &&
          c.securityContext.readOnlyRootFilesystem)
        &&
        (!has(object.spec.initContainers) ||
          object.spec.initContainers.all(c,
            has(c.securityContext) &&
            has(c.securityContext.readOnlyRootFilesystem) &&
            c.securityContext.readOnlyRootFilesystem))
        &&
        (!has(object.spec.ephemeralContainers) ||
          object.spec.ephemeralContainers.all(c,
            has(c.securityContext) &&
            has(c.securityContext.readOnlyRootFilesystem) &&
            c.securityContext.readOnlyRootFilesystem))
      message: "Every container must set readOnlyRootFilesystem to true."
---
apiVersion: admissionregistration.k8s.io/v1
kind: ValidatingAdmissionPolicyBinding
metadata:
  name: require-readonly-rootfs-lab.example.com
spec:
  policyName: require-readonly-rootfs.example.com
  validationActions: ["Deny"]
  matchResources:
    namespaceSelector:
      matchLabels:
        security.example.com/rootfs-profile: readonly
~~~

Các điểm cần hiểu trước khi dùng:

- Policy và binding là tài nguyên quản trị cluster; không cấp quyền quản lý chúng cho ServiceAccount ứng dụng.
- Binding chọn namespace bằng nhãn do ví dụ đặt, không áp dụng tùy tiện cho mọi namespace.
- Biểu thức yêu cầu khai báo true ở **từng container**, kể cả init/ephemeral container.
- Mẫu không kiểm tra mount ghi được có đúng nhu cầu hay không. Pod vẫn có thể dùng volume ghi được.
- Mẫu không xác minh image có khởi động thành công hay có giữ bí mật đúng cách.
- Nếu workload có sidecar được inject, sidecar sau mutation cũng phải đáp ứng điều kiện.
- Policy nhắm vào Pod; Deployment có thể được lưu nhưng controller không tạo được Pod vi phạm. Cần đọc Event của ReplicaSet.
- Khi bổ sung policy vào môi trường đã có Pod không phù hợp, phải đánh giá cả tác động lên các request UPDATE được match.

Ở giai đoạn đánh giá có thể dùng `validationActions: ["Warn", "Audit"]` rồi chuyển sang `Deny` khi đã kiểm chứng. Không ghép `Deny` và `Warn` trong cùng binding.

Việc bổ sung policy là quyết định quản trị có phạm vi rộng hơn sửa Deployment. Ví dụ chỉ mô tả cơ chế; bài viết không tự cài chính sách lên cluster của bạn.

## 9. Thực hành: kiểm tra admission và hành vi runtime

Các bước dưới đây dành cho môi trường lab riêng. Chúng là hướng dẫn kiểm thử, không phải thông báo rằng bài viết đã chạy các lệnh trên một cluster thực.

### 9.1. Chuẩn bị

1. Kiểm tra phiên bản Kubernetes và khả năng dùng PSA, policy version cùng admission policy bổ sung.
2. Dùng image Spring của bạn đã xác định UID/GID, entrypoint, cổng HTTP và các endpoint probe.
3. Chuẩn bị namespace, nguồn cấu hình và ServiceAccount như ví dụ.
4. Áp dụng Deployment bằng kênh triển khai được phân quyền.
5. Nếu kiểm tra policy readonly, cài policy/binding bằng kênh quản trị riêng.
6. Ghi lại các đường dẫn ứng dụng phải đọc, phải ghi và không được ghi.

Không gắn `enforce` mới lên namespace dùng chung mà chưa đánh giá các workload bên trong. Có thể kiểm tra dự kiến thay đổi nhãn bằng server dry run trong namespace lab:

~~~powershell
kubectl label namespace pod-security-lab --dry-run=server --overwrite pod-security.kubernetes.io/enforce=restricted pod-security.kubernetes.io/enforce-version=v1.35
~~~

Cách dùng dry run để đánh giá nhãn policy được Kubernetes hướng dẫn tại [Enforce Standards with Namespace Labels](https://kubernetes.io/docs/tasks/configure-pod-container/enforce-standards-namespace-labels/).

### 9.2. Quan sát rollout và lỗi tạo Pod

~~~powershell
kubectl -n pod-security-lab rollout status deployment/orders-api --timeout=180s
kubectl -n pod-security-lab get pods -l app=orders-api
kubectl -n pod-security-lab get replicasets
kubectl -n pod-security-lab get events --sort-by=.metadata.creationTimestamp
kubectl -n pod-security-lab logs deployment/orders-api --since=5m
~~~

Nếu Deployment tồn tại mà chưa có Pod, đọc Event của ReplicaSet/controller. Không suy ra “Deployment apply thành công” là PSA và policy readonly đã cho Pod đi qua.

Nếu Pod có nhưng không tạo được container, xem chi tiết Pod, image user, quyền tệp và runtime. Nếu Java đã chạy rồi thoát, xem log ứng dụng và lỗi filesystem tương ứng.

### 9.3. Kiểm tra Pod admission bằng request trực tiếp

Có thể tạo một đối tượng Pod **chỉ trong bộ nhớ PowerShell**, lấy từ template Deployment lab để server dry run. Cách này kiểm tra Pod admission thay vì chỉ kiểm tra đối tượng Deployment:

~~~powershell
$labDeployment = kubectl -n pod-security-lab get deployment orders-api -o json | ConvertFrom-Json

$podCandidate = [ordered]@{
  apiVersion = 'v1'
  kind = 'Pod'
  metadata = @{
    name = 'orders-api-admission-check'
    namespace = 'pod-security-lab'
  }
  spec = $labDeployment.spec.template.spec
}

$podCandidate | ConvertTo-Json -Depth 100 | kubectl create --dry-run=server -f -
~~~

Với template đúng và admission được cấu hình như dự định, request này phải được chấp nhận ở giai đoạn admission; nó chưa kéo image, schedule hoặc khởi động JVM.

Tiếp theo thử một ứng viên không readonly:

~~~powershell
$podCandidate.spec.containers[0].securityContext.readOnlyRootFilesystem = $false

$podCandidate | ConvertTo-Json -Depth 100 | kubectl create --dry-run=server -f -
~~~

Kết quả cần phân biệt:

| Chính sách đang có | Kỳ vọng với readonly false, các trường khác vẫn đúng |
| --- | --- |
| Chỉ PSS restricted | Không bị từ chối chỉ vì trường readonly false |
| Có policy/binding readonly ở chế độ Deny và namespace được chọn | Bị từ chối bởi policy bổ sung |
| Policy ở chế độ Warn/Audit | Có thể được chấp nhận nhưng có tín hiệu đánh giá tương ứng |

Các lệnh trên không tạo Pod do dùng server dry run và không cập nhật Deployment nguồn. Nếu có admission khác, phải đọc lý do phản hồi để xác định policy nào quyết định kết quả.

Có thể tạo các ứng viên riêng để thử thiếu `allowPrivilegeEscalation: false`, chạy UID 0 hoặc bỏ `drop: [ALL]`. Giữ từng phép thử độc lập để biết điều kiện nào bị từ chối; không sửa nhiều trường rồi đoán nguyên nhân.

### 9.4. Kiểm tra vùng ghi và quyền người dùng

Với image lab có sẵn các công cụ tương ứng, người vận hành được cấp quyền chẩn đoán có thể chạy:

~~~powershell
kubectl -n pod-security-lab exec deployment/orders-api -- id
kubectl -n pod-security-lab exec deployment/orders-api -- cat /proc/self/mountinfo
kubectl -n pod-security-lab exec deployment/orders-api -- touch /tmp/rootfs-lab-probe
kubectl -n pod-security-lab exec deployment/orders-api -- rm /tmp/rootfs-lab-probe
kubectl -n pod-security-lab exec deployment/orders-api -- touch /app/rootfs-lab-probe
~~~

Kỳ vọng:

- UID không phải 0.
- Thông tin mount cho thấy root filesystem chỉ đọc.
- Tạo/xóa tệp nhỏ trong `/tmp` thành công.
- Ghi vào đường dẫn thuộc root filesystem bị từ chối.

Nếu thử cuối cùng bất ngờ tạo được tệp, dọn đúng tệp probe trong lab và điều tra mount/cấu hình thực tế. Không thử bằng cách ghi đè JAR, tệp hệ thống hoặc Secret.

Lỗi `Permission denied` có thể do mode hoặc ownership. Chỉ thấy một lần ghi thất bại chưa đủ chứng minh mount readonly; đối chiếu cấu hình runtime và mount flags. Lỗi `Read-only file system` chỉ ra một nguyên nhân khác với thiếu quyền Unix.

Image tối giản có thể không có `id`, `cat`, `touch` hay shell. Khi đó dùng công cụ quan sát đã chuẩn bị hoặc một chế độ chẩn đoán Java trong image lab. Không cài gói vào container đang chạy, không bật privileged và không tắt chính sách chỉ để có shell.

Quyền exec phục vụ phép thử là quyền của kênh vận hành. Không cấp `pods/exec` cho ServiceAccount runtime của ứng dụng vì bài thực hành có lệnh exec.

### 9.5. Kiểm tra chức năng Spring thay vì chỉ kiểm tra container sống

| Luồng | Điều cần xác nhận |
| --- | --- |
| Khởi động | Không có lỗi tạo tệp trong đường dẫn bị khóa |
| ConfigMap/Secret | Đọc được nguồn bắt buộc bằng UID thực tế, không in giá trị bí mật |
| Cập nhật ConfigMap | Tệp được chiếu mới và cấu hình có hiệu lực được xác minh riêng |
| Discovery nếu bật | Hoàn tất khởi tạo, tìm đúng namespace và phục hồi watch |
| Token rotation nếu dùng API | Client tiếp tục xác thực sau khi token thay đổi |
| LoadBalancer | Request tới dịch vụ đích vẫn đúng với nguồn discovery đã chọn |
| Watcher nếu dùng | Thông báo tới đúng đích, refresh thành công theo cơ chế cấu hình |
| Probe | Endpoint trả trạng thái phù hợp; không lặp restart do một lỗi phụ thuộc bên ngoài |
| Resource | Vùng tạm không đầy, không phát sinh OOM hoặc eviction ngoài dự kiến |

Trong hồ sơ cơ bản phần 5, không có Watcher/refresh tự động được cài chỉ bởi các manifest đã nêu. Muốn kiểm tra refresh phải bổ sung cơ chế đó và cấu hình ứng dụng theo đúng phiên bản.

Không đưa việc mất kết nối API server vào liveness chỉ để kiểm tra tích hợp. Spring Boot khuyến cáo liveness không phụ thuộc hệ thống bên ngoài; readiness cần được chọn theo khả năng phục vụ thực tế. Xem [Kubernetes Probes](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html#actuator.endpoints.kubernetes-probes).

## 10. Chẩn đoán theo triệu chứng

| Triệu chứng | Nguyên nhân cần xét | Hướng xử lý |
| --- | --- | --- |
| ReplicaSet báo vi phạm restricted | Thiếu trường bảo mật, capability hoặc container phụ vi phạm | Sửa đúng Pod template hoặc cấu hình injection |
| Bị policy readonly từ chối | Một container chưa đặt true | Kiểm tra container thường, init và ephemeral container |
| Container không chạy vì image user | UID không phù hợp hoặc không xác định được non-root | Sửa image/chọn UID số được hỗ trợ |
| Java không tạo được tệp tạm | Thư mục tạm nằm trên rootfs hoặc thiếu quyền ghi | Mount vùng tạm, kiểm tra `java.io.tmpdir` và đường dẫn thực |
| Đọc Secret bị Permission denied | Mode, group hoặc cách mount không phù hợp | Kiểm tra quyền tệp với UID/GID thực tế |
| Entrypoint lỗi khi sửa cấu hình | Script dùng `sed`, copy hoặc chown trên image | Chuyển thao tác sang build hoặc volume đầu ra hẹp |
| API trả 401 | Credential thiếu, hết hạn, sai audience hoặc không được nạp lại | Kiểm tra cơ chế credential; không mở rootfs |
| API trả 403 | Danh tính thiếu quyền cho request | Kiểm tra RBAC và request thực tế |
| ConfigMap đổi nhưng bean không đổi | Chưa có đường refresh phù hợp | Kiểm tra chuỗi đọc tệp, refresh và bean được cập nhật |
| OOM sau khi dùng tmpfs | JVM và tệp trên RAM vượt ngân sách | Tính lại memory và chọn loại vùng tạm |
| Pod bị eviction hoặc vùng tạm đầy | Dung lượng, log hoặc ephemeral storage vượt ngân sách | Giới hạn đầu vào, dọn tệp tạm và điều chỉnh sizing |
| Tệp biến mất sau khi thay Pod | Dùng dữ liệu tạm như dữ liệu bền vững | Chuyển dữ liệu cần giữ sang kho phù hợp |

Không chữa lỗi thuộc cột credential/RBAC bằng cách tăng quyền Linux. Không chữa lỗi mount/quyền tệp bằng cách cấp quyền Secret toàn namespace.

## 11. Triển khai dần và quản lý ngoại lệ

Một trình tự phù hợp với workload đang có:

1. Lập danh sách đường ghi ở startup và các luồng ít gặp như upload, lỗi JVM, refresh hoặc agent khởi tạo.
2. Chuẩn bị image hỗ trợ non-root và tệp cần thiết từ lúc build.
3. Khai báo đúng những vùng ghi riêng, quyền nhóm và ngân sách tài nguyên.
4. Bật security context trong môi trường kiểm thử.
5. Quan sát PSS và policy readonly ở chế độ cảnh báo/audit khi phù hợp.
6. Kiểm tra các luồng khởi tạo, cập nhật cấu hình, token rotation, phục hồi và chẩn đoán cần thiết.
7. Chuyển sang enforce/Deny trong phạm vi đã xác nhận.
8. Rollout theo quy trình triển khai và theo dõi lỗi tạo Pod, restart, OOM cùng dung lượng tạm.

Ghim phiên bản PSS giúp đánh giá thay đổi có kiểm soát; khi nâng cluster hoặc đổi mức policy cần đánh giá lại. Chọn `latest` có nghĩa chấp nhận quy tắc thay đổi theo phiên bản mà cluster áp dụng.

Nếu image chưa đáp ứng, ghi rõ phần còn thiếu và kế hoạch sửa. Ngoại lệ phải nhắm đúng workload/nhu cầu được quản lý, không hạ policy cho mọi ứng dụng chỉ vì một thành phần phụ đang ghi sai đường dẫn.

Khi có sidecar hoặc init container, đánh giá image và vùng ghi của từng thành phần. Một init container cần ghi vào volume dùng chung không có nghĩa cần root filesystem ghi được; hai vùng filesystem đó có thể được thiết kế riêng.

## 12. Những giới hạn còn lại và kết quả cần bàn giao

Root filesystem chỉ đọc giúp hạn chế thay đổi phần filesystem được khóa. Nó không bảo đảm ứng dụng không bị khai thác:

- Tiến trình vẫn có thể thay đổi dữ liệu trong RAM.
- Vùng ghi được vẫn có thể chứa tệp ngoài dự định nếu ứng dụng bị chiếm quyền.
- Bí mật tiến trình đọc được vẫn có thể bị lộ.
- Quyền API và khả năng kết nối mạng vẫn phụ thuộc những chính sách riêng.
- Cấu hình không tự cập nhật hoặc rollback đúng chỉ vì volume chỉ đọc.
- Một mount ghi được quá rộng có thể làm giảm đáng kể lợi ích mong muốn.

Do đó, kết quả triển khai cần bàn giao gồm:

| Bằng chứng | Nội dung cần rõ |
| --- | --- |
| Chính sách Pod | Mức PSS, phiên bản ghim, phạm vi namespace và ngoại lệ nếu có |
| Chính sách readonly | Cơ chế bắt buộc, phạm vi chọn và các loại container được kiểm tra |
| Danh tính runtime | UID/GID, ServiceAccount và lý do có/không mount token |
| Bản đồ filesystem | Cây chỉ đọc, từng vùng ghi ngoại lệ và mục đích |
| Quyền nguồn cấu hình | Cách đọc ConfigMap/Secret, mode tệp, đường cập nhật |
| Ngân sách tài nguyên | Dung lượng tạm, memory/ephemeral storage và cách xử lý khi đầy |
| Kiểm chứng | Admission cho phép/từ chối, startup, chức năng Spring và các giai đoạn cập nhật |
| Vận hành | Log, probe, chẩn đoán và cách thu thập dữ liệu nhạy cảm có kiểm soát |

Thiết kế đạt mục tiêu khi ứng dụng Spring vẫn thực hiện đúng những tích hợp cần thiết, đồng thời không cần ghi vào cây mã/runtime và không được cấp thêm quyền chỉ để che một lỗi đường dẫn hoặc quyền tệp.
