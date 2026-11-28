# Container security: bảo vệ và kiểm chứng an toàn trong suốt vòng đời container

**Container security** là tập hợp các biện pháp bảo vệ mã nguồn, image, registry, nền tảng chạy container, cấu hình triển khai, tài nguyên, danh tính, mạng và dữ liệu trong suốt vòng đời của một workload được đóng gói bằng container. Container hỗ trợ nhất quán môi trường và triển khai nhanh, nhưng cùng lúc tạo thêm các đường tấn công qua image, dependency, quyền của tiến trình, container runtime, hệ thống điều phối và chuỗi cung ứng phần mềm.

Trong module **SECURITY_SECURITY_ASSURANCE**, nội dung này thuộc chương **Platform assurance**. Mục tiêu không dừng ở việc liệt kê best practice. Người học cần biết cách **đánh giá có bằng chứng** rằng các mục tiêu bảo mật đã được đáp ứng: xác định rủi ro, chuyển thành yêu cầu và control, kiểm tra hành vi thực tế, lưu bằng chứng cho audit, xử lý finding và liên tục đánh giá lại khi workload thay đổi.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích container, image, registry, container runtime và orchestrator; phân biệt ranh giới container với ranh giới máy ảo.
2. Nhận diện rủi ro trong các giai đoạn build, phân phối, triển khai và vận hành container.
3. Thiết kế baseline bảo mật cho image, danh tính, đặc quyền, hệ thống tệp, mạng, secret và Kubernetes workload.
4. Xác định bằng chứng kiểm toán phù hợp cho từng control, bao gồm cả phép kiểm cấu hình và kiểm thử hiệu lực.
5. Phân biệt lỗ hổng đã phát hiện với rủi ro có thể khai thác trong ngữ cảnh triển khai; thực hiện quy trình khắc phục và xác minh lại.
6. Xây dựng cơ chế assurance liên tục từ CI/CD đến production, bao gồm kiểm soát ngoại lệ và đo độ bao phủ.

## 2. Mô hình container và ranh giới bảo mật

Một **container image** là gói nội dung theo định dạng được runtime hiểu, thường gồm các lớp hệ thống tệp (layers), cấu hình khởi chạy và metadata. Khi chạy image, container runtime khởi tạo tiến trình trong các cơ chế cô lập được hệ điều hành hỗ trợ.

Trên Linux, những cơ chế quan trọng gồm:

- **Namespaces:** tách góc nhìn của tiến trình đối với PID, mạng, mount, IPC, hostname và user ID tùy cấu hình.
- **cgroups:** kiểm soát và đo mức sử dụng tài nguyên như CPU, bộ nhớ, số lượng tiến trình.
- **Capabilities:** phân chia một số đặc quyền của superuser thành các năng lực nhỏ hơn.
- **Seccomp và Linux Security Modules (LSM):** giới hạn syscall hoặc các thao tác nhạy cảm; ví dụ AppArmor và SELinux.
- **Container runtime:** thành phần tạo và quản lý tiến trình container, như containerd kết hợp với runtime OCI.
- **Orchestrator:** nền tảng điều phối, ví dụ Kubernetes, quản lý phân phối workload, policy, danh tính, network và trạng thái mong muốn.

Về bản chất, container thường **chia sẻ kernel của host**. Cơ chế cô lập của container khác với máy ảo dùng kernel riêng. Ranh giới container có thể bị ảnh hưởng bởi lỗi kernel/runtime, cấu hình quá đặc quyền hoặc mount tài nguyên host. Vì vậy, không nên xem container là một ranh giới bảo mật tuyệt đối.

~~~mermaid
flowchart TB
    DEV["Mã nguồn và dependency"] --> CI["CI/CD: build, test, scan"]
    CI --> IMG["Image + SBOM + provenance/signature"]
    IMG --> REG["Registry tin cậy"]
    REG --> ADM["Admission policy khi triển khai"]
    ADM --> POD["Pod / container workload"]
    POD --> CRI["Container runtime"]
    CRI --> NODE["Kernel + host OS + node"]
    POD --> NET["Service, NetworkPolicy, egress"]
    POD --> ID["Service account / workload identity"]
    POD --> OBS["Log, audit, runtime detection"]
    OBS --> EV["Bằng chứng và finding"]
~~~

**Phạm vi assurance** phải bao gồm các liên kết giữa những khối trên. Một image được scan sạch tại thời điểm build vẫn có thể trở nên không an toàn nếu pod chạy privileged, mount Docker socket, dùng token quá quyền hoặc không có kiểm soát luồng mạng.

### 2.1. Phân biệt những khái niệm dễ nhầm

| Khái niệm | Ý nghĩa | Câu hỏi assurance |
|---|---|---|
| **Image** | Artifact bất biến theo digest, có các layer và cấu hình khởi chạy | Có xác định được chính xác nội dung image đã triển khai và nguồn tạo ra không? |
| **Container** | Một instance chạy từ image với cấu hình runtime cụ thể | Tiến trình chạy dưới UID nào, có những quyền, mount và giới hạn nào? |
| **Registry** | Nơi lưu và phân phối image | Ai được push/pull, có kiểm tra tính xác thực và retention không? |
| **Node/host** | Máy chạy container runtime và kernel | Host được harden, cập nhật, giám sát và cô lập quyền ra sao? |
| **Pod** | Đơn vị triển khai Kubernetes, có thể gồm nhiều container dùng chung một số tài nguyên | Các container trong pod ảnh hưởng lẫn nhau thế nào? |
| **Namespace Kubernetes** | Phạm vi logic cho tài nguyên, RBAC và policy | Có phân quyền, quota và NetworkPolicy phù hợp không? |
| **Cluster** | Tập hợp control plane, node và các thành phần quản trị | Quản trị đặc quyền, admission, audit và isolation được bảo vệ thế nào? |

**Lưu ý:** Kubernetes namespace hỗ trợ tổ chức và áp policy; bản thân namespace không tạo ranh giới cô lập tương đương máy ảo hay cluster riêng. Với tenant có mức tin cậy khác nhau, cần đánh giá bổ sung ranh giới node, identity, network và có thể dùng cluster/VM riêng.

## 3. Threat model cho container

Threat modeling cần xác định tài sản, tác nhân, điểm vào, ranh giới tin cậy và hậu quả. Một vài tài sản có giá trị cao gồm: image dùng trong production, tài khoản registry, pipeline build, signing key, node, workload identity, secret, dữ liệu nhạy cảm và hệ thống quan sát bảo mật.

### 3.1. Các đường tấn công điển hình

| Điểm vào / nguồn rủi ro | Kịch bản | Tác động có thể xảy ra |
|---|---|---|
| Dependency, base image | Gói hoặc image độc hại được đưa vào quá trình build | Thực thi mã lạ, lấy secret, phát tán image độc hại |
| Registry / pipeline | Chiếm quyền token push hoặc đổi tag trỏ tới image khác | Đưa artifact không được phê duyệt vào production |
| Workload có lỗ hổng | API bị khai thác trong container có quyền cao | Đọc dữ liệu, chiếm workload identity, tiếp cận host hoặc dịch vụ khác |
| Privileged, hostPath, socket | Container truy cập thiết bị, hệ thống tệp host hoặc API runtime có đặc quyền | Mở rộng phạm vi xâm nhập đến host và các container khác |
| Service account quá quyền | Token của pod cho phép liệt kê secret hoặc sửa workload khác | Di chuyển ngang và kiểm soát tài nguyên cluster |
| Mạng quá mở | Pod bị xâm nhập truy cập tùy ý dịch vụ nội bộ hoặc Internet | Truy cập dữ liệu và chuyển dữ liệu ra ngoài |
| Secret và log | Credential được đưa vào image, environment, output build hoặc log | Lộ bí mật và tái sử dụng quyền |
| Runtime/host không được giám sát | Tiến trình lạ, shell hoặc kết nối bất thường không bị phát hiện | Duy trì xâm nhập lâu dài, khó điều tra |

Mức độ ưu tiên phải xét **khả năng khai thác thực tế và tác động**, gồm: dịch vụ có public exposure hay không; mức đặc quyền; loại dữ liệu; tính sẵn có của biện pháp giảm thiểu; exploit công khai; khả năng truy cập thành phần; và phạm vi bị ảnh hưởng. Không nên quyết định xử lý chỉ dựa vào một điểm CVSS.

### 3.2. Ranh giới tin cậy quan trọng

1. **Developer → build system:** mã, dependency và secret dùng cho build đi vào pipeline.
2. **Build system → registry:** artifact được công bố kèm metadata, digest và chứng thực nguồn gốc.
3. **Registry → cluster:** image được cho phép hoặc bị chặn theo policy triển khai.
4. **Workload → node:** tiến trình truy cập syscall, filesystem, socket, device và tài nguyên host.
5. **Workload → workload/API:** danh tính và chính sách mạng giới hạn giao tiếp.
6. **Platform → evidence store:** log và bằng chứng được chuyển đến khu vực có phân quyền, thời hạn lưu giữ và tính toàn vẹn thích hợp.

Một control thường không bảo vệ mọi ranh giới. Ví dụ, chữ ký image giúp xác minh artifact theo chính sách tin cậy, nhưng không chứng minh image không chứa lỗ hổng hay container đang chạy với đặc quyền tối thiểu.

## 4. Bảo vệ chuỗi cung ứng image

### 4.1. Chọn base image

Nên dùng base image từ nguồn được phê duyệt, phù hợp mục đích và có cơ chế duy trì bản vá. Giảm các công cụ không cần thiết trong runtime image để hạn chế bề mặt tấn công, nhưng **image nhỏ không tự động an toàn**: lỗ hổng vẫn có thể tồn tại trong thư viện, runtime hoặc ứng dụng.

Các điểm cần kiểm tra:

- Nguồn image, publisher, kênh phát hành và chính sách cập nhật có rõ ràng.
- Phiên bản hệ điều hành/runtime còn được hỗ trợ.
- Có quản lý dependency trực tiếp và bắc cầu, kể cả dependency dùng tại build.
- Có lịch rebuild image khi base image hoặc thư viện nhận bản vá.
- Có khả năng chứng minh production dùng artifact cụ thể nào.

### 4.2. Digest, tag và tính bất biến

**Tag** như phiên bản ứng dụng hoặc latest là tên tham chiếu có thể được gán lại, tùy cấu hình registry. **Digest** xác định nội dung của một manifest artifact cụ thể. Deploy bằng digest giúp xác định chính xác image được yêu cầu, nhưng cần kiểm tra **ai xây image đó, nguồn gốc nào và image có được phép triển khai không**.

Với môi trường production, có thể yêu cầu:

1. CI sinh image và lưu digest.
2. Scanner kiểm tra vulnerability, secret và cấu hình build.
3. Pipeline sinh SBOM, provenance/attestation; nếu dùng signing, ký artifact bằng danh tính đã xác minh.
4. Policy tại admission hoặc cơ chế tương đương chỉ chấp nhận artifact đáp ứng yêu cầu tổ chức.
5. Hệ thống lưu lịch sử digest → commit → build run → deploy → môi trường.

**Giới hạn quan trọng:** chỉ có digest không chứng minh người tạo đáng tin cậy; chỉ có chữ ký không chứng minh mã an toàn; chỉ có một bản scan thành công cũng không phản ánh lỗ hổng được phát hiện về sau.

### 4.3. SBOM, vulnerability và triage

**Software Bill of Materials (SBOM)** mô tả các thành phần phần mềm có trong artifact theo khả năng công cụ quan sát. Nó giúp điều tra ảnh hưởng khi một dependency phát sinh lỗ hổng. Tuy vậy, SBOM có thể thiếu thành phần, đặc biệt với binary đóng gói đặc biệt hoặc phần mềm tải lúc runtime. Cần đánh giá chất lượng dữ liệu và phạm vi nguồn sinh SBOM.

Một quy trình quản lý vulnerability phù hợp:

- Scan tại build, lúc đưa image vào registry và định kỳ đối với image đang chạy.
- Phân biệt **finding trên image** với **khả năng khai thác trong workload**; đánh giá khả năng tiếp cận và cấu hình giảm thiểu.
- Quy định thời hạn xử lý theo rủi ro, chủ sở hữu và đường khắc phục: cập nhật dependency, base image hoặc đổi kiến trúc.
- Xây lại, ký và redeploy artifact mới; tránh trông chờ vào việc sửa container đang chạy.
- Xác nhận production đã chuyển sang digest mới và không còn replica dùng digest cũ trong phạm vi cần xử lý.

### 4.4. Secret trong quá trình build

Không nhúng password, private key, token hoặc file cấu hình chứa secret vào Dockerfile, lệnh build, image layer hay artifact trung gian. Xóa secret trong một layer sau khi đã COPY ở layer trước thường **không xóa được** secret khỏi lịch sử image.

Nếu build cần truy cập hệ thống riêng, dùng cơ chế cấp secret tạm thời của build system, thu hồi sau sử dụng và hạn chế log. Bên cạnh scan image, nên quét repository và pipeline output để tìm rò rỉ credential.

### 4.5. Ví dụ Dockerfile cho dịch vụ Java

~~~dockerfile
# Ví dụ minh họa: cấu hình base image phải được pin/kiểm chứng
# bằng digest trong pipeline production.
FROM eclipse-temurin:21-jdk AS builder
WORKDIR /source

COPY gradlew settings.gradle build.gradle ./
COPY gradle ./gradle
RUN chmod +x ./gradlew
COPY src ./src
RUN ./gradlew --no-daemon clean bootJar

FROM eclipse-temurin:21-jre
WORKDIR /app

# Giả định build chỉ sinh ra một file JAR phù hợp.
COPY --from=builder --chown=10001:10001 \
    /source/build/libs/*.jar /app/app.jar

USER 10001:10001
EXPOSE 8080
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
~~~

Ví dụ cho thấy **multi-stage build** để hạn chế công cụ build có mặt trong runtime image và **USER 10001** để tiến trình chạy dưới UID không phải root. Đây là mẫu minh họa; cần kiểm tra Gradle project, tag/digest, permission thư mục ghi, Java runtime và hành vi thực tế của ứng dụng trước khi dùng production.

Cần thêm cấu hình deployment để đặt read-only root filesystem, hạn chế Linux capabilities, seccomp, resource và mạng. Một Dockerfile không thể tự đảm bảo tất cả các control tại runtime.

## 5. Bảo vệ registry và kênh phân phối

Registry là thành phần quan trọng của supply chain. Nếu kẻ tấn công push hoặc thay thế artifact, các bước kiểm soát sau build có thể bị vượt qua nếu admission không xác minh lại.

Các yêu cầu quản trị phổ biến:

- Phân tách quyền push và pull; CI dùng danh tính chuyên biệt với scope hẹp, token ngắn hạn khi có thể.
- Bảo vệ tài khoản quản trị registry bằng xác thực mạnh, audit log và quy trình phê duyệt.
- Áp cơ chế bất biến cho artifact/tag ở những repository cần kiểm soát; quản lý retention và garbage collection an toàn.
- Tách registry/repository production khỏi khu thử nghiệm theo mức rủi ro.
- Không lưu secret dưới dạng image hoặc build artifact; quét image và metadata trước khi công bố.
- Kiểm tra image provenance và chính sách signer/issuer/danh tính được phép tại khâu triển khai.
- Đảm bảo có bản ghi image nào được pull/triển khai ở đâu, đồng thời giữ bằng chứng theo kỳ kiểm toán.

Đối với container chạy tại node, cần xem cách cấp **image pull credential**. Không nên phát tán một token registry quyền ghi cho mọi node hoặc workload. Network và TLS cần bảo vệ đường vận chuyển; trust store phải được quản lý.

## 6. Hardening container tại runtime

**Principle of least privilege** nghĩa là mỗi tiến trình chỉ có những quyền và tài nguyên cần thiết để thực hiện chức năng đã được phê duyệt. Với container, nguyên tắc này được cụ thể hóa ở nhiều tầng.

### 6.1. Danh tính tiến trình

- Chạy ứng dụng bằng UID/GID không phải root khi có thể.
- Không chạy privileged nếu workload không có yêu cầu đặc biệt đã được phê duyệt.
- Hạn chế cơ chế nâng quyền tiến trình, chẳng hạn thiết lập cho Kubernetes **allowPrivilegeEscalation: false** khi tương thích.
- Cân nhắc user namespace/rootless container ở những nền tảng hỗ trợ; đánh giá quyền host và giới hạn vận hành thực tế.
- Không đánh đồng **USER khác 0 bên trong container** với **runtime/daemon rootless trên host**; đây là hai lớp bảo vệ khác nhau.

### 6.2. Capability, syscall và MAC

- Loại bỏ các Linux capability không cần thiết; với nhiều dịch vụ web, có thể bắt đầu bằng drop toàn bộ rồi cho phép bổ sung khi đã xác minh nhu cầu.
- Dùng seccomp profile phù hợp để giảm bề mặt syscall; cấu hình **RuntimeDefault** trong Kubernetes thường là điểm khởi đầu tốt nếu workload tương thích.
- Khi nền tảng hỗ trợ, bổ sung AppArmor hoặc SELinux policy và kiểm tra chúng thật sự được bật/enforce ở node.
- Tránh dùng hostPID, hostIPC, hostNetwork, hostPath, quyền truy cập device hoặc runtime socket nếu không có lý do đã kiểm soát.

**Không có một cờ bảo mật đơn lẻ đủ sức tạo ranh giới an toàn.** Một workload chạy UID khác 0 vẫn có thể đọc secret trái phép nếu ServiceAccount quá quyền; seccomp không thay thế RBAC hay network isolation.

### 6.3. Hệ thống tệp và mount

Dùng **read-only root filesystem** khi ứng dụng cho phép; chỉ mount writable volume vào những vị trí thực sự cần ghi. Tách dữ liệu nghiệp vụ khỏi image và quản lý lifecycle của persistent volume theo yêu cầu bảo mật dữ liệu.

Hạn chế các mount nguy hiểm:

| Kiểu mount / tài nguyên | Rủi ro | Hướng kiểm soát |
|---|---|---|
| Host filesystem / hostPath | Container đọc hoặc sửa dữ liệu host, truy cập socket hoặc file cấu hình | Mặc định từ chối; chỉ cho phép đường dẫn/capability rõ ràng qua policy và review |
| Docker/container runtime socket | Có thể điều khiển runtime để tạo container với quyền rộng trên host | Không mount vào workload thông thường; dùng build service tách biệt, ít quyền |
| Shared writable volume | Container khác có thể đọc/ghi dữ liệu ngoài nhu cầu | Phân quyền, tách volume và kiểm tra identity/permission |
| Secret volume | Lộ credential nếu mount quá rộng hoặc ghi log | Mount đúng workload, giới hạn quyền đọc, xoay vòng và theo dõi sử dụng |
| Writable root filesystem | Dễ ghi file không mong muốn hoặc lưu dấu mã độc trong tầng ghi | Chuyển sang read-only và cấp volume riêng cho thư mục cần ghi |

### 6.4. Giới hạn tài nguyên

CPU/memory requests và limits, giới hạn PID, ephemeral storage, quota namespace và cơ chế ưu tiên pod giúp giảm tác động của workload sử dụng quá nhiều tài nguyên.

Các giới hạn này **giảm rủi ro cạn tài nguyên** nhưng không tự bảo đảm chống được mọi hình thức từ chối dịch vụ. Cần kiểm thử với traffic, tải thực tế và tình huống thiếu bộ nhớ; xác định mức retry, restart và eviction phù hợp.

## 7. Bảo mật Kubernetes workload

Kubernetes phân phối quyền và policy trên nhiều lớp: API server, admission, RBAC, ServiceAccount, namespace, pod, node, network và các controller. Đánh giá assurance phải phân biệt cấu hình **được khai báo** với cấu hình **đang có hiệu lực** trên workload.

### 7.1. Pod Security Standards và admission

Kubernetes định nghĩa các mức **Privileged**, **Baseline** và **Restricted** trong Pod Security Standards (PSS). Pod Security Admission có thể đánh giá theo các chế độ enforce, audit và warn gắn với namespace. Mức **Restricted** thích hợp làm nền tảng cho nhiều workload ứng dụng thông thường, với điều kiện cần được kiểm thử tương thích và quản lý ngoại lệ.

Giới hạn:

- PSS/P.S. Admission tập trung vào các trường bảo mật của pod, không thay thế scan image, signature verification, NetworkPolicy, RBAC hay secret governance.
- Namespace label thể hiện ý định chính sách, nhưng assurance vẫn phải kiểm tra admission có hoạt động, workload có ngoại lệ và việc policy có thực sự được enforce không.
- Một số thành phần hệ thống cần quyền đặc biệt; cần phê duyệt phạm vi, cách cô lập và giám sát thay vì tắt toàn bộ kiểm soát.

### 7.2. Ví dụ manifest workload đã harden

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: payments-api
  namespace: payments-prod
spec:
  replicas: 2
  selector:
    matchLabels:
      app: payments-api
  template:
    metadata:
      labels:
        app: payments-api
    spec:
      automountServiceAccountToken: false
      securityContext:
        runAsNonRoot: true
        runAsUser: 10001
        runAsGroup: 10001
        fsGroup: 10001
        seccompProfile:
          type: RuntimeDefault
      containers:
        - name: api
          # Placeholder minh họa: thay bằng image digest SHA-256 thực.
          image: registry.example.com/payments/api@sha256:REPLACE_WITH_REAL_DIGEST
          ports:
            - containerPort: 8080
          securityContext:
            allowPrivilegeEscalation: false
            readOnlyRootFilesystem: true
            capabilities:
              drop: ["ALL"]
          resources:
            requests:
              cpu: "100m"
              memory: "128Mi"
            limits:
              cpu: "500m"
              memory: "512Mi"
          volumeMounts:
            - name: tmp
              mountPath: /tmp
      volumes:
        - name: tmp
          emptyDir:
            medium: Memory
            sizeLimit: "64Mi"
~~~

Manifest là ví dụ **minh họa kiểm soát**, chưa phải cấu hình triển khai hoàn chỉnh. Cần thay digest bằng digest thật, xác nhận namespace, image, đường ghi file, port, probes, nhu cầu network, secret và ServiceAccount theo ứng dụng. Nếu workload thực sự cần gọi Kubernetes API, không thể chỉ tắt token rồi xem như hoàn thành: phải thiết kế ServiceAccount riêng với quyền phù hợp và chứng minh lý do cần quyền.

**Phân tích các trường quan trọng:**

| Trường | Mục đích | Điều cần kiểm chứng |
|---|---|---|
| runAsNonRoot, runAsUser | Không dùng UID root cho tiến trình chính | Container thực tế chạy UID/GID dự kiến; init container và sidecar cũng phù hợp |
| allowPrivilegeEscalation: false | Giảm khả năng nâng quyền qua một số cơ chế ở runtime | Giá trị có hiệu lực trên tất cả container thuộc phạm vi; không có đường privileged |
| capabilities.drop: ALL | Gỡ các Linux capability mặc định | Ứng dụng vẫn chạy và chỉ bổ sung capability đã phê duyệt nếu cần |
| seccompProfile: RuntimeDefault | Sử dụng profile seccomp mặc định của runtime | Node/runtime hỗ trợ và workload không có ngoại lệ trái chính sách |
| readOnlyRootFilesystem | Hạn chế ghi trên root filesystem của container | Ứng dụng dùng writable volume được cho phép; không có mount host rủi ro |
| automountServiceAccountToken: false | Tránh tự động mount token nếu workload không cần Kubernetes API | Không có token/API credential khác được cấp thừa hoặc nạp từ đường khác |
| resources | Giới hạn sử dụng CPU và bộ nhớ | Mức giới hạn phù hợp tải thực tế; hiệu lực cgroup/khả năng OOM được hiểu đúng |
| image theo digest | Triển khai đúng artifact đã xét duyệt | Digest thực khớp kết quả build và điều kiện signature/provenance |

### 7.3. RBAC, ServiceAccount và workload identity

Không nên cấp cluster-admin cho ứng dụng thông thường. Nguyên tắc thiết kế:

1. Mỗi workload hoặc nhóm có cùng nhu cầu quyền dùng ServiceAccount riêng.
2. Chỉ cấp verb và resource Kubernetes API cần thiết; tránh wildcard khi có thể.
3. Ưu tiên Role và RoleBinding giới hạn namespace khi đủ nhu cầu; ClusterRoleBinding cần được đánh giá kỹ vì phạm vi rộng.
4. Dùng workload identity/federation để truy cập dịch vụ cloud khi nền tảng hỗ trợ; tránh nhúng khóa tĩnh trong image hoặc cấu hình.
5. Theo dõi việc tạo token, binding quyền và thay đổi danh tính; kiểm thử quyền theo cả kịch bản được phép và bị từ chối.

Một pod bị xâm nhập có thể sử dụng quyền API gắn với danh tính của nó, bất kể container đang chạy UID nào. Do đó, **bảo vệ runtime phải đi cùng bảo vệ identity**.

### 7.4. Mạng và egress

Kubernetes NetworkPolicy cho phép mô tả chính sách ở tầng pod/network, tùy vào khả năng hiện thực của plugin CNI. **NetworkPolicy chỉ có tác dụng nếu hệ thống mạng thực sự hỗ trợ/enforce**. Nó cũng không thay thế firewall ngoài cluster, gateway, chính sách truy cập dịch vụ hay bảo vệ ứng dụng.

Ví dụ policy egress có phạm vi hẹp, minh họa ý tưởng chỉ cho pod ứng dụng kết nối một nhóm pod backend trong cùng namespace:

~~~yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: payments-api-egress
  namespace: payments-prod
spec:
  podSelector:
    matchLabels:
      app: payments-api
  policyTypes:
    - Egress
  egress:
    - to:
        - podSelector:
            matchLabels:
              app: payments-db-proxy
      ports:
        - protocol: TCP
          port: 5432
~~~

Policy trên chỉ nêu **egress** và là ví dụ minh họa; cần bổ sung policy ingress, DNS, health check hoặc luồng phụ trợ nếu thực tế yêu cầu. Đánh giá phải xét tất cả policy cùng chọn một pod và tính cộng gộp quyền cho phép, đồng thời xem CNI enforce như thế nào. Một rule riêng lẻ chưa đủ để kết luận toàn bộ lưu lượng đã được giới hạn.

Đối với workload có egress Internet, xác định chính xác domain/IP/port cần truy cập, phương thức bảo vệ giao tiếp và khả năng logging. Hạn chế exfiltration cần kết hợp identity, chính sách egress, DNS/proxy và các biện pháp dữ liệu phù hợp.

### 7.5. Node, cluster và control plane

Assurance cấp workload chưa đầy đủ nếu nền tảng host bị cấu hình sai. Cần xác minh:

- Node OS và container runtime còn được hỗ trợ, cập nhật bản vá theo rủi ro.
- Kubelet/API access, certificate và credential được quản lý; đặc quyền node bị giới hạn.
- Audit log Kubernetes được cấu hình và chuyển tới nơi bảo vệ phù hợp, với thời hạn lưu giữ đã xác định.
- Admission policy cho workload mới và workload cập nhật được áp dụng tại phạm vi dự kiến.
- Node pool/taint/toleration và topology cô lập workload rủi ro cao hoặc tenant nhạy cảm nếu kiến trúc yêu cầu.
- Các add-on như CNI, CSI, ingress controller, service mesh được kiểm soát image, quyền và thay đổi.
- Recovery và quy trình nâng cấp/rollback có khả năng xử lý sự cố bảo mật mà vẫn duy trì bằng chứng.

**Đặc biệt:** bảo vệ container không thay thế yêu cầu quản trị control plane và host; quyền kubelet, quyền đọc secret và quyền quản trị cluster có thể vượt qua nhiều ranh giới pod.

## 8. Bảo vệ secret và dữ liệu container

### 8.1. Secret

Secret có thể là credential database, API token, private key hoặc khóa ký. Một số rủi ro phổ biến:

- Secret xuất hiện trong source code, image layer, cache, output build hoặc log.
- Token được cấp quá rộng, không có thời hạn hoặc được dùng chung nhiều workload.
- ServiceAccount có quyền đọc Kubernetes Secret của workload khác.
- Secret trong environment variable vô tình lộ qua debug, dump hoặc hệ thống quan sát.
- Backup và snapshot chứa secret nhưng không có chính sách phân quyền tương ứng.

Các biện pháp thường dùng:

- Cấp secret vào đúng workload theo cơ chế do nền tảng hỗ trợ; không đưa secret vào image.
- Xác định nguồn phát hành, owner, hạn sử dụng, cơ chế rotation và revoke.
- Mã hóa dữ liệu nhạy cảm khi lưu và truyền theo yêu cầu; phân quyền truy cập kho secret và quản lý khóa.
- Hạn chế secret trong log, thông báo lỗi, ảnh chụp debug và báo cáo scan.
- Kiểm chứng rằng một workload không thể truy cập secret ngoài phạm vi được phê duyệt.

**Lưu ý Kubernetes:** đối tượng Secret không tự mặc định bảo đảm bí mật trước mọi principal có quyền đọc; cần kiểm soát RBAC, cấu hình mã hóa dữ liệu lưu trữ và phạm vi truy cập, cùng kiểm tra log/audit.

### 8.2. Dữ liệu và storage

Persistent volume, object storage và database là những phạm vi riêng trong threat model. Container có read-only root filesystem vẫn có thể sửa dữ liệu trong volume được mount. Cần đánh giá quyền truy cập dữ liệu, mã hóa, network, backup, retention, quy trình hủy dữ liệu và sự kiện audit theo từng loại kho lưu trữ.

Với dữ liệu nhạy cảm, kết luận assurance cần trả lời **workload nào được phép đọc/ghi**, bằng danh tính nào, trong hoàn cảnh nào và có bằng chứng nào cho phép kiểm chứng.

## 9. Logging, runtime detection và phản ứng sự cố

Runtime detection tập trung vào những sự kiện có thể chỉ xuất hiện khi container đang chạy: tiến trình lạ, thực thi shell, thay đổi file bất thường, truy cập file nhạy cảm, kết nối ra ngoài không hợp lệ, thao tác API đáng ngờ và dấu hiệu tấn công vào host.

Phân biệt ba nguồn:

| Nguồn | Ví dụ | Giới hạn |
|---|---|---|
| **Application log** | Truy cập endpoint, lỗi nghiệp vụ, sự kiện xác thực | Có thể thiếu thông tin syscall, đặc quyền hoặc hành vi kernel |
| **Kubernetes audit/event** | Tạo pod, thay đổi role, cập nhật deployment, admission deny | Không ghi mọi hành vi của tiến trình bên trong container; event Kubernetes có retention giới hạn |
| **Host/runtime telemetry** | Process execution, syscall/event, thay đổi file, network connection | Phụ thuộc agent, kernel, khả năng quan sát, overhead và chất lượng rule |

Một chương trình assurance tốt kiểm tra cả **khả năng phát hiện** lẫn **khả năng phản ứng**. Ví dụ:

1. Sinh một sự kiện thử được phép trong môi trường kiểm soát (như tiến trình bất thường trong namespace thử nghiệm).
2. Kiểm tra telemetry có ghi nhận đúng nguồn, thời gian, pod UID, container ID và node hay không.
3. Kiểm tra rule có tạo cảnh báo và cảnh báo được chuyển đến đúng đội xử lý.
4. Xem hành động điều tra: thu log, truy dấu image digest, phân tích identity, xác định phạm vi ảnh hưởng.
5. Xác minh việc cô lập workload, thu hồi credential và triển khai bản vá không làm mất dấu vết điều tra.

**Không dựa vào log tại local container làm bằng chứng duy nhất.** Container có thể bị tạo lại, node có thể mất hoặc đối tượng bị xóa. Bằng chứng điều tra quan trọng cần chuyển đến nơi lưu trữ với quyền, tính toàn vẹn và retention phù hợp.

### 9.1. Quy trình phản ứng khi container nghi bị xâm nhập

Khi có dấu hiệu xâm nhập, cần cân bằng giữa khống chế rủi ro và bảo toàn chứng cứ:

- Xác nhận signal và phân loại mức độ khẩn cấp.
- Ghi workload/pod/container ID, node, image digest, namespace, ServiceAccount, mốc thời gian và các kết nối quan sát được.
- Giới hạn quyền hoặc network theo playbook đã phê duyệt; cân nhắc ảnh hưởng dịch vụ.
- Thu hồi credential có thể đã bị lộ, đánh giá các quyền liên quan và truy vết lateral movement.
- Khắc phục nguồn gốc: image, cấu hình, policy, dependency hoặc hạ tầng.
- Redeploy artifact sạch và kiểm thử lại; không xem việc restart container là đã giải quyết nguyên nhân.
- Cập nhật rule phát hiện và baseline nếu phát hiện lỗ hổng trong kiểm soát.

## 10. Baseline security control và bằng chứng assurance

Baseline nên được viết dưới dạng **điều kiện có thể kiểm tra**, thay vì mệnh đề chung như "image an toàn" hoặc "pod được bảo vệ".

| ID | Control | Điều kiện kỳ vọng | Bằng chứng / phép kiểm |
|---|---|---|---|
| CS-01 | Inventory và owner | Mọi workload trong phạm vi có owner, môi trường, namespace, service và digest nhận diện được | Inventory từ API cluster/registry đối chiếu service catalog |
| CS-02 | Image provenance | Image production được sinh từ pipeline và nguồn được phép; có metadata khớp digest | Build run, commit, digest, attestation/signature, admission decision |
| CS-03 | Vulnerability management | Image được quét và finding xử lý theo risk policy; có quy trình tái scan | Scan result có timestamp, SBOM, risk decision, bản ghi sửa và redeploy |
| CS-04 | Registry access | Quyền push/pull giới hạn theo vai trò; audit và cơ chế giữ artifact phù hợp | Access policy, identity mapping, log push, retention |
| CS-05 | Non-root và privilege | Workload tuân baseline về UID, privilege escalation và capability | PodSpec thực tế, admission result, runtime UID/capability khi cần |
| CS-06 | Filesystem và mount | Không mount host/runtime socket ngoài ngoại lệ; root FS read-only theo yêu cầu | Export pod spec, policy, thử nghiệm ghi bị từ chối có kiểm soát |
| CS-07 | Seccomp/LSM | Profile được áp cho workload thuộc phạm vi và node hỗ trợ | PodSpec, node/runtime config, audit deny hoặc kết quả kiểm thử tương thích |
| CS-08 | Workload identity | ServiceAccount/RBAC tối thiểu; token tự mount chỉ khi cần | Binding, Role/ClusterRole, token mount, phép kiểm quyền được phép/bị từ chối |
| CS-09 | Network segmentation | Luồng ingress/egress được định nghĩa và kiểm soát | NetworkPolicy, cấu hình CNI, test connectivity allow/deny |
| CS-10 | Secret governance | Secret được cấp đúng phạm vi, không nhúng trong image, có rotation | Secret scan, IAM/RBAC, policy kho secret, log truy cập và rotation |
| CS-11 | Resource control | Workload có giới hạn phù hợp mức rủi ro và nhu cầu tải | Requests/limits, quota, telemetry và kiểm thử tải phù hợp |
| CS-12 | Platform hardening | Node/runtime/control plane và add-on được quản trị bản vá, cấu hình, audit | Inventory version, kết quả cấu hình, change record, audit log |
| CS-13 | Detection và response | Có telemetry, cảnh báo và khả năng xử lý hành vi bất thường | Sự kiện thử, alert/ticket, playbook, kết quả diễn tập |
| CS-14 | Change/drift | Thay đổi image, quyền, policy, cấu hình có thể phát hiện và truy trách nhiệm | GitOps diff, audit trail, drift result, approval, remediation record |

Một control có thể cần nhiều loại bằng chứng. Ví dụ, CS-09 đòi hỏi policy đúng trên giấy **và** một phép kiểm network thực tế cho thấy luồng bị cấm không đi qua được. Nếu plugin CNI không enforce policy, việc có file YAML hợp lệ vẫn không chứng minh đạt.

### 10.1. Cách chuyển control thành một assertion kiểm chứng được

Ví dụ với CS-05:

> Trong mọi namespace production thuộc phạm vi, các container ứng dụng phải chạy không phải root, không có privilege escalation, không chạy privileged và không giữ Linux capability ngoài danh sách đã phê duyệt.

Tách assertion thành tiêu chí:

1. Xác định đủ namespace và workload production.
2. Lấy danh sách **pod đang chạy**, gồm container ứng dụng, init container và sidecar.
3. Đánh giá securityContext có hiệu lực của từng container và các ngoại lệ.
4. Đối chiếu policy admission với các cấu hình thực tế; kiểm tra đường tạo workload ngoài pipeline.
5. Chọn mẫu để xác minh UID/capability runtime nếu control đòi hỏi bằng chứng hành vi.
6. Ghi finding nếu không đạt, nêu exact resource, điều kiện thiếu, nguyên nhân, owner và hạn xử lý.
7. Kiểm tra lại sau sửa; lưu kết quả có dấu thời gian.

Một assertion có phạm vi rõ ràng giúp tránh kết luận mơ hồ như "Kubernetes hardening: PASS" dựa vào chỉ một manifest.

## 11. Thực hành kiểm tra read-only trên Kubernetes

Các lệnh sau minh họa một số nguồn bằng chứng. Chỉ chạy trong cluster mà người thực hiện có quyền đọc phù hợp. Kết quả phải được bảo vệ khi lưu vì có thể chứa tên tài nguyên, metadata hoặc cấu hình nhạy cảm.

### Bước 1 — Xác định cluster và quyền người kiểm tra

~~~bash
kubectl config current-context
kubectl auth can-i list pods --all-namespaces
kubectl auth can-i list networkpolicies --all-namespaces
~~~

Cần ghi cụ thể cluster context và thời điểm kiểm tra, tránh lấy bằng chứng từ nhầm môi trường. Lệnh **can-i** phản ánh câu trả lời về quyền của danh tính hiện tại cho câu hỏi cụ thể; không suy ra toàn bộ RBAC của các workload khác từ kết quả này.

### Bước 2 — Thu inventory pod và cấu hình thực tế

~~~bash
kubectl get namespaces -o json > namespaces.json
kubectl get pods --all-namespaces -o json > pods.json
kubectl get deployments --all-namespaces -o json > deployments.json
~~~

Từ dữ liệu trên có thể trích namespace, tên workload, image, digest được khai báo, ServiceAccount, securityContext, volumes và resource limits. Pod đang chạy có thể khác deployment template sau rollout, nên nên đối chiếu cả hai. Khi cần xác định **digest thực tế container runtime đã pull**, kiểm tra trường trạng thái imageID/containerID và đối chiếu theo ngữ nghĩa runtime; không suy luận từ tên tag.

### Bước 3 — Kiểm tra policy mạng và RBAC

~~~bash
kubectl get networkpolicies --all-namespaces -o json > networkpolicies.json
kubectl get roles,rolebindings --all-namespaces -o json > rbac-namespaced.json
kubectl get clusterroles,clusterrolebindings -o json > rbac-cluster.json
kubectl get serviceaccounts --all-namespaces -o json > serviceaccounts.json
~~~

Đọc dữ liệu cấu hình cho biết **ý định cấu hình**; cần kiểm chứng cả hiệu lực network ở CNI, các binding liên quan và identity cloud liên kết. Nếu muốn kiểm tra quyền một ServiceAccount cụ thể bằng impersonation, người đánh giá cần có quyền impersonate hợp lệ và phải lưu kết quả cùng ngữ cảnh.

### Bước 4 — Kiểm thử policy, telemetry và admission

Một chu trình kiểm thử an toàn có thể thực hiện trong namespace thử nghiệm được phê duyệt:

1. Thử tạo workload cấu hình trái baseline và quan sát admission có từ chối hay không.
2. Triển khai workload hợp lệ và xác minh runtime identity, secret access và connectivity được phép.
3. Thử kết nối mạng bị policy cấm, xác nhận bị chặn tại môi trường thực thi có CNI enforce.
4. Phát sinh một sự kiện audit/monitoring đã được cho phép; theo dõi đến kho lưu tập trung.
5. Lưu policy version, thời gian, identity thực thi, đối tượng, kết quả, dấu vết log và thông tin môi trường.

Không nên dùng test "bị chặn" bằng cách chủ động cố chiếm quyền hoặc phá hoại môi trường production. Các tình huống bất thường có thể kiểm tra trên môi trường được phép và các thao tác mô phỏng có kiểm soát.

### 11.1. Giới hạn khi dùng lệnh kiểm tra

Một số giá trị từ Kubernetes API không phản ánh hoàn toàn cấu hình runtime cuối cùng; một số kiểm soát được áp bởi admission, runtime, node hoặc CNI. Ngoài ra, dữ liệu có thể thay đổi trong khi đang thu thập. Vì vậy, ghi rõ **thời gian snapshot**, cluster version, chính sách và độ bao phủ. Khi phép kiểm chưa quan sát đủ, nên dùng kết quả **INCONCLUSIVE / cần kiểm tra thêm** thay vì mặc định PASS.

## 12. Bản ghi bằng chứng và logic kết luận

Bộ hồ sơ sau minh họa kiểm tra CS-05 cho một workload cụ thể. Mọi ID, đường dẫn và thời gian đều là **ví dụ giả định**.

~~~yaml
assessment_id: "PA-CS-2026-11-028"
control_id: "CS-05"
assessed_at: "2026-11-28T08:30:00Z"
environment: "production"
target:
  cluster: "cluster-prod-a"
  namespace: "payments-prod"
  workload: "deployment/payments-api"
  container: "api"
  image_digest: "sha256:REPLACE_WITH_REAL_DIGEST"
baseline_version: "container-security-v3"
criteria:
  run_as_non_root: true
  privileged: false
  allow_privilege_escalation: false
  drop_all_capabilities: true
evidence:
  - kind: "kubernetes-api-export"
    location: "evidence/CS-05/pod-snapshot.json"
  - kind: "admission-decision"
    location: "evidence/CS-05/admission-audit.json"
  - kind: "runtime-check"
    location: "evidence/CS-05/runtime-identity.json"
result: "PASS_WITH_SCOPE"
limitations:
  - "Phạm vi: workload và container được nêu ở trên"
  - "Không kết luận về các workload khác của cluster"
assessor: "platform-assurance-team"
~~~

Trạng thái **PASS_WITH_SCOPE** chỉ là quy ước ví dụ để nhấn mạnh giới hạn kết luận. Hệ thống thực tế nên định nghĩa rõ các trạng thái như PASS, FAIL, NOT_APPLICABLE và INCONCLUSIVE, tiêu chí chuyển trạng thái và trách nhiệm phê duyệt.

### 12.1. Yêu cầu đối với bằng chứng tốt

- **Nguồn truy xuất:** API, CI/CD system, registry, audit hoặc runtime telemetry có nguồn rõ ràng.
- **Đối tượng và phạm vi:** cluster, namespace, workload UID, container ID, image digest, chính sách và thời điểm.
- **Dấu vết liên kết:** yêu cầu → control → phép kiểm → kết quả → finding → remediation → retest.
- **Khả năng tái lập:** nêu công cụ/phiên bản, input, scope và điều kiện đo.
- **Tính toàn vẹn:** kiểm soát ai có quyền sửa/xóa; lưu evidence theo retention và kiểm tra integrity nếu cần.
- **An toàn thông tin:** không đưa credential hay dữ liệu khách hàng vào artifact kiểm toán; che nội dung nhạy cảm nhưng vẫn giữ đủ dữ liệu xác minh.

Một dashboard báo "all pods compliant" có thể là tín hiệu hữu ích, nhưng cần biết dashboard quét những namespace nào, kiểm tra phiên bản policy nào, đã bỏ qua init container/sidecar hay chưa, và kết quả có còn đúng với pod vừa được tạo gần đây hay không.

## 13. Tình huống tổng hợp: triển khai image hợp lệ nhưng container vẫn quá quyền

Một dịch vụ **payments-api** được xây trong pipeline chuẩn. Image đã được scan, có SBOM và chữ ký hợp lệ. Sau đợt thay đổi cấu hình, một kỹ sư thêm mount tới runtime socket để "debug nhanh"; deployment dùng ServiceAccount có quyền đọc secret ở nhiều namespace. Ứng dụng có public endpoint.

Đội assurance nhận thấy:

1. CS-02 về nguồn gốc image có thể vẫn **PASS**, vì artifact vẫn được tạo từ pipeline được phép.
2. CS-06 về mount rủi ro **FAIL**, vì runtime socket tạo đường truy cập nguy hiểm tới host/runtime.
3. CS-08 về workload identity **FAIL**, vì quyền đọc secret quá rộng.
4. CS-13 cần được kiểm tra: có alert khi cấu hình mới triển khai hoặc khi pod dùng quyền bất thường không?
5. Kết luận chung về workload không thể là "an toàn" chỉ vì image scan và signature hợp lệ.

### Quy trình xử lý

**Bước 1 — Xác nhận bằng chứng:** lưu deployment/pod spec, admission event, owner, image digest, ServiceAccount binding, phạm vi secret có thể truy cập và thời điểm thay đổi. Loại bỏ credential thật khỏi báo cáo.

**Bước 2 — Đánh giá rủi ro:** xét khả năng bị khai thác từ public endpoint, quyền đọc dữ liệu nhạy cảm, quyền runtime socket và phạm vi di chuyển ngang. Xác định mức ưu tiên dựa trên rủi ro thực tế, không dùng số CVE như thước đo duy nhất.

**Bước 3 — Khắc phục:** bỏ runtime socket mount, thu hẹp Role/RoleBinding và thay ServiceAccount nếu cần, kiểm tra lại Pod Security Admission, thu hồi credential có nguy cơ lộ và redeploy manifest được phê duyệt.

**Bước 4 — Kiểm chứng:** xác minh mount không còn trên pod mới, quyền API ngoài phạm vi bị từ chối, sự kiện policy phù hợp được log và cảnh báo xuất hiện theo kịch bản thử.

**Bước 5 — Ngăn tái diễn:** đưa guardrail vào admission, policy-as-code và review thay đổi; ghi finding với owner, hạn xử lý, lý do gốc và kết quả retest.

Tình huống này cho thấy **assurance là chuỗi bằng chứng đa lớp**. Kết quả tốt ở một lớp không loại bỏ lỗi của lớp khác.

## 14. Continuous assurance và quản lý ngoại lệ

Số lượng container thay đổi nhanh; đánh giá thủ công mỗi quý có thể bỏ sót nhiều cấu hình chỉ xuất hiện trong thời gian ngắn. Các điểm kiểm tra nên được tự động hóa theo vòng đời:

~~~mermaid
flowchart LR
    A["Commit / dependency update"] --> B["Build + scan + SBOM"]
    B --> C["Ký / chứng thực artifact"]
    C --> D["Registry + admission policy"]
    D --> E["Deploy và kiểm tra baseline"]
    E --> F["Telemetry + drift + re-scan"]
    F --> G{"Phát hiện sai lệch?"}
    G -- "Không" --> F
    G -- "Có" --> H["Finding + owner + SLA"]
    H --> I["Sửa, redeploy, retest"]
    I --> E
~~~

### 14.1. Phân loại kiểm soát theo thời điểm

| Thời điểm | Cơ chế điển hình | Cần giữ gì làm bằng chứng? |
|---|---|---|
| Source/PR | Review, kiểm tra dependency, secret scan, policy-as-code | Commit, kết quả check, approval và ngoại lệ |
| Build | SBOM, vulnerability scan, attestations, image digest | Build run, tool/policy version, scan result, digest |
| Publish | Kiểm tra registry permission, signature, metadata và retention | Registry audit, artifact metadata, quyết định publish |
| Deploy | Admission, RBAC, image verification, baseline policy | Admission decision, manifest, deploy actor và thời gian |
| Runtime | Drift detection, process/network telemetry, runtime scan | Alert, snapshot, log, imageID, owner và ticket |
| Retire | Thu hồi credential, xóa workload, bảo toàn log cần giữ | Change record, xác nhận thu hồi/xóa, hồ sơ retention |

**Drift** là chênh lệch giữa trạng thái thực tế và trạng thái mong muốn/được phê duyệt. Drift có thể xảy ra khi ai đó sửa trực tiếp manifest, thay RBAC, tắt policy hoặc cập nhật image ngoài quy trình. GitOps giúp làm rõ trạng thái khai báo và lịch sử thay đổi nhưng vẫn cần kiểm chứng runtime có tuân thủ và các thao tác ngoài Git có bị phát hiện không.

### 14.2. Ngoại lệ có kiểm soát

Một số hệ thống như CNI, storage driver, tracing agent hoặc công cụ quản trị node có thể cần thêm capability, mount hoặc quyền. Ngoại lệ cần nêu rõ:

- Control nào bị lệch; workload/namespace/node pool nào bị ảnh hưởng.
- Mục đích kỹ thuật, rủi ro, phạm vi dữ liệu và tác động có thể xảy ra.
- Biện pháp bù trừ: cô lập node, giảm quyền khác, allowlist image/digest, monitoring tăng cường.
- Người đề xuất, người phê duyệt, owner, hạn hết hiệu lực và thời điểm rà soát.
- Bằng chứng chứng minh ngoại lệ chỉ áp cho đối tượng cần thiết và có thể thu hồi.

Ngoại lệ không có thời hạn và không có bằng chứng kiểm soát bù trừ dễ trở thành lỗ hổng quản trị kéo dài.

### 14.3. Chỉ số đánh giá

Các chỉ số nên phản ánh **chất lượng kiểm soát và độ bao phủ**, không chỉ số lượng công cụ đã mua hay số lần scan.

| Chỉ số | Gợi ý cách đo | Giới hạn cần hiểu |
|---|---|---|
| Độ bao phủ inventory | Workload production có owner và image digest hợp lệ / workload production được phát hiện | Phải xem nguồn phát hiện có bao phủ tất cả cluster/namespace không |
| Độ bao phủ admission | Số workload thuộc phạm vi chịu policy enforce / tổng workload thuộc phạm vi | Không tính namespace chỉ gắn chế độ audit/warn như enforce |
| Độ bao phủ runtime hardening | Container thực tế đạt các assertion CS-05, CS-06, CS-07 / container đã kiểm tra trong phạm vi | Tính cả init container/sidecar và ngoại lệ hợp lệ |
| Độ bao phủ provenance | Digest đang chạy có metadata/signature được xác minh / tất cả digest thuộc phạm vi | Không suy ra an toàn mã nguồn từ chữ ký |
| Tồn đọng vulnerability | Finding chưa xử lý theo mức rủi ro và thời gian tồn tại | Cần tránh đếm trùng cùng artifact hoặc bỏ sót image đang chạy |
| Thời gian khắc phục | Từ phát hiện tới khi retest chứng minh rollout đã đạt | Ticket chuyển "Done" không đồng nghĩa các replica đã cập nhật |
| Độ bao phủ detection | Tỷ lệ kịch bản thử có cảnh báo đúng và phản ứng được thực hiện | Chỉ có ý nghĩa trong tập kịch bản đã công bố và được phép kiểm thử |
| Ngoại lệ quá hạn | Ngoại lệ hết hạn chưa được giải quyết / tổng ngoại lệ đã hết hạn | Ngoại lệ phải có owner, mục đích và hạn xử lý |

Một hệ thống có 100% image đã scan nhưng 30% pod chạy privileged hoặc có quyền Kubernetes quá rộng không thể được đánh giá mức assurance cao chỉ dựa trên KPI scanning.

## 15. Sai lầm thường gặp

| Nhận định sai | Cách hiểu đúng |
|---|---|
| "Container giống VM nên đã cô lập hoàn toàn khỏi host." | Container thường chia sẻ kernel; cần host hardening, runtime security và isolation bổ sung. |
| "Image không có CVE critical nghĩa là an toàn." | Có thể tồn tại lỗi ứng dụng, secret, lỗ hổng chưa công bố, sai cấu hình và đường tấn công runtime. |
| "Đã pin digest nên không cần provenance/signature." | Digest định danh artifact, không chứng minh ai đã tạo, từ mã nào và đã qua quy trình tin cậy. |
| "USER non-root đủ để ngăn chiếm quyền." | Vẫn có nguy cơ từ ServiceAccount, network, volume, capability, kernel và quyền dữ liệu. |
| "Kubernetes namespace là ranh giới tenant hoàn chỉnh." | Cần RBAC, network, node, admission, identity và cân nhắc cluster/VM riêng khi rủi ro yêu cầu. |
| "Có NetworkPolicy là network đã bị cô lập." | Phải xác minh CNI hỗ trợ/enforce, tổng hợp policy áp dụng và test luồng thực tế. |
| "Pod đang healthy nên control bảo mật đạt." | Health check và security assertion đo những điều khác nhau. |
| "Đã đóng finding sau khi sửa file YAML." | Cần kiểm chứng trạng thái thực tế của pod/replica và kết quả retest. |
| "Vulnerability scan lúc build đủ cho suốt đời image." | Cần tái scan, theo dõi image đang chạy, rebuild và redeploy khi rủi ro thay đổi. |
| "Runtime alert nghĩa là phát hiện đã hiệu quả." | Phải xác nhận log đủ ngữ cảnh, cảnh báo chuyển đúng người và hành động response có thể thực thi. |

## 16. Bài tập tự kiểm tra

**Câu 1.** Một container đã chạy bằng UID 10001 và đặt read-only root filesystem. Pod được bind với ClusterRole cho phép đọc tất cả Secret. Có thể kết luận workload có quyền tối thiểu không?

**Gợi ý:** Không. Cấu hình process/filesystem chỉ là một phần; quyền Kubernetes API qua ServiceAccount vẫn quá rộng. Cần kiểm tra RBAC và thu hẹp tài nguyên, verb, namespace.

**Câu 2.** Image production được chỉ định bằng digest và đã ký. Vì sao vẫn cần vulnerability scan và admission policy?

**Gợi ý:** Digest xác định artifact, chữ ký xác minh theo mô hình tin cậy đã cấu hình; hai yếu tố đó không chứng minh không có lỗ hổng hoặc runtime configuration đạt baseline. Admission cần kiểm tra điều kiện được phép triển khai.

**Câu 3.** Một NetworkPolicy chỉ cho kết nối từ payment API đến proxy database. Vì sao cần thêm kiểm thử kết nối?

**Gợi ý:** Policy có thể không được CNI enforce, các policy khác có thể mở thêm đường, hoặc luồng mạng thực tế đi qua thành phần không nằm trong giả định ban đầu. Kiểm thử allow/deny xác nhận hiệu lực theo phạm vi.

**Câu 4.** Scanner phát hiện CVE mức cao trên một image đang chạy. Những dữ liệu nào giúp đội assurance ưu tiên xử lý?

**Gợi ý:** Digest và workload sử dụng image, thư viện bị ảnh hưởng, khả năng khai thác, mức tiếp xúc, dữ liệu liên quan, đặc quyền runtime, biện pháp giảm thiểu, khả năng có bản vá và hạn xử lý theo chính sách rủi ro.

**Câu 5.** Một finding được đánh dấu "đã sửa" sau khi pipeline phát hành image mới. Bằng chứng tối thiểu để đóng finding là gì?

**Gợi ý:** Kiểm tra rollout cho thấy các replica thuộc phạm vi đang chạy digest đã sửa, scan/retest cho thấy assertion ban đầu đã đạt, không còn workload cũ ngoài ngoại lệ và có dấu vết phê duyệt/đánh giá lại.

## 17. Checklist triển khai một chương trình container assurance

Có thể dùng checklist dưới đây làm khung thảo luận khi xây dựng baseline, sau đó chuyển từng mục thành assertion cụ thể và phép kiểm đo được:

- [ ] Có inventory đầy đủ cluster, namespace, workload, image digest và owner.
- [ ] Image được build từ pipeline được phép, giữ provenance, SBOM, scan result và quyết định phát hành.
- [ ] Registry phân quyền push/pull hợp lý, ghi audit và bảo vệ artifact.
- [ ] Workload production chịu admission policy; ngoại lệ có phạm vi, owner và hạn hiệu lực.
- [ ] Privileged, hostPath, runtime socket, host namespaces và capability được kiểm soát theo rủi ro.
- [ ] Runtime identity, seccomp/LSM, filesystem và resource limits được kiểm tra theo tiêu chí rõ ràng.
- [ ] ServiceAccount, RBAC, workload identity và secret được giới hạn và có khả năng thu hồi.
- [ ] Luồng ingress/egress được thiết kế và kiểm thử trên hạ tầng network thực tế.
- [ ] Node/runtime/control plane, add-on và audit logging nằm trong chu kỳ bảo trì và đánh giá.
- [ ] Có runtime telemetry, alert, playbook sự cố và diễn tập kiểm tra hiệu lực.
- [ ] Finding được theo dõi đến lúc khắc phục và **retest**; bằng chứng có nguồn, phạm vi và thời điểm.
- [ ] Dashboard assurance chỉ tổng hợp các assertion đã được định nghĩa, công bố giới hạn và độ bao phủ.

## Kết luận

Container security bao phủ toàn bộ vòng đời từ **source và image** đến **registry, admission, runtime, host, identity, network và dữ liệu**. Trong phạm vi **Platform assurance**, tổ chức phải chứng minh bằng bằng chứng đủ tin cậy rằng các biện pháp bảo mật này đang có hiệu lực trên đúng workload, đúng môi trường và đúng thời điểm. Một chương trình security assurance liên tục gắn từng rủi ro với yêu cầu, control, phép kiểm, finding, remediation và retest sẽ giúp kết luận bảo mật có thể giải thích, kiểm chứng và cải thiện theo thời gian.
