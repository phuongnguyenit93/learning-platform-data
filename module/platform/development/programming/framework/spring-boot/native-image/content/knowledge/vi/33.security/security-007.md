# Quyền tối thiểu cho builder, runner, runtime container và registry

Một pipeline Spring Boot Native Image có nhiều thành phần cùng tham gia tạo và chạy một ứng dụng: môi trường build, CI runner, registry lưu image, hệ thống triển khai và container đang phục vụ request. Nếu tất cả cùng dùng một tài khoản có quyền quản trị, một lỗi trong bước build hoặc một container bị xâm nhập có thể lan sang source code, registry, cluster và hạ tầng khác.

**Least privilege (quyền tối thiểu)** yêu cầu mỗi thành phần chỉ có quyền cần cho nhiệm vụ của nó, trong đúng phạm vi tài nguyên và khoảng thời gian cần thiết. Builder cần đọc source và dependency để tạo executable; job phát hành cần push image vào repository được chỉ định; node runtime cần pull image; ứng dụng đang chạy chỉ cần truy cập database, broker hoặc API nghiệp vụ theo quyền được cấp.

Bài học này thiết kế ranh giới quyền cho toàn bộ vòng đời container native: builder và compiler, CI runner, BuildKit/Docker daemon, credential lấy dependency, registry push/pull, deployment identity, runtime container và Kubernetes ServiceAccount. Các ví dụ tập trung vào Spring Boot Native Image, Docker, Kubernetes và GitHub Actions; nguyên tắc có thể áp dụng với CI/CD và registry khác.

## 1. Vì sao phải tách quyền theo từng giai đoạn?

Native Image thường cần một build job có nhiều tài nguyên CPU/RAM và quyền đọc dependency. Điều đó không có nghĩa process ứng dụng khi chạy cũng cần các quyền tương tự.

Ví dụ, một service có thể cần:

- Build job đọc repository source, tải Maven dependency và tạo executable.
- CI runner chạy native-image compiler, test và đóng gói OCI image.
- Publisher push image vào một repository cụ thể.
- Kubernetes node hoặc kubelet pull image để khởi động Pod.
- Runtime container gọi PostgreSQL và message broker.
- Deployment controller cập nhật workload trong namespace được giao.

Nếu dùng chung một credential có quyền đọc/ghi/xóa mọi repository và cluster, các nhiệm vụ độc lập trở thành một miền tin cậy lớn. Một script build bị chèn lệnh có thể lấy credential publish; một container runtime bị khai thác có thể lấy token của CI nếu token bị mount vào container.

Mục tiêu là chia nhỏ quyền, danh tính, thời gian sống và phạm vi mạng để giới hạn ảnh hưởng khi một thành phần gặp sự cố.

## 2. Các ranh giới tin cậy trong pipeline

Sơ đồ dưới đây mô tả các danh tính nên được tách:

~~~mermaid
flowchart TD
    A["Source repository<br/>read-only checkout"] --> B["Ephemeral CI runner"]
    B --> C["Native Image builder<br/>source + dependency read"]
    C --> D["Test artifact"]
    D --> E["Release publisher<br/>repository push only"]
    E --> F["Container registry"]
    F --> G["Node / kubelet<br/>image pull only"]
    G --> H["Runtime container<br/>non-root"]
    H --> I["Database / broker / API<br/>scoped application access"]
    B --> J["Deployment job<br/>namespace-scoped deploy"]
    J --> K["Kubernetes API"]
~~~

Các đường đi thể hiện quyền truy cập, không phải một tài khoản duy nhất được truyền qua toàn bộ pipeline. Artifact được chuyển giữa các bước; credential của builder không cần đi cùng artifact tới publisher hoặc runtime.

Một nguyên tắc hữu ích là: **artifact có thể đi tiếp qua pipeline, credential thì chỉ được cấp tại bước cần dùng**.

## 3. Ma trận quyền tối thiểu

| Thành phần | Quyền cần có | Quyền thường không cần |
|---|---|---|
| Source checkout | Đọc repository và submodule được phép | Push source, quản trị repository |
| Native builder | Đọc source, dependency registry, ghi build output | Production database, cluster-admin, registry delete |
| CI runner | Chạy job và truy cập artifact của job | Quyền quản trị host/daemon dùng chung |
| Test job | Đọc image/artifact và gọi dependency test | Push release image, deploy production |
| Image publisher | Push vào repository được phép | Xóa repository, quản trị organization |
| Registry pull identity | Pull image của workload | Push, delete hoặc sửa quyền repository |
| Deployment job | Cập nhật workload trong namespace/environment được giao | Cluster-admin, đọc mọi Secret |
| Runtime container | Gọi dependency nghiệp vụ cần thiết | Docker socket, registry push, Kubernetes API nếu không dùng |
| Runtime ServiceAccount | Quyền API tối thiểu nếu ứng dụng thật sự gọi Kubernetes API | Quyền mặc định rộng hoặc quyền ở namespace khác |
| Registry administrator | Quản lý repository và policy theo nhiệm vụ quản trị | Dùng credential này trong build/test/runtime |

Không phải mọi pipeline đều có tất cả vai trò thành process riêng. Một runner có thể thực hiện nhiều job, nhưng credential và quyền của từng job vẫn nên tách. Nếu builder và publisher chạy trong cùng workflow, hãy cấp quyền publish chỉ ở job phát hành sau khi kiểm thử đạt.

## 4. Quyền của native builder

Builder gồm GraalVM Native Image, JDK, compiler, linker, Spring AOT processing và các build tool như Maven/Gradle. Nhiệm vụ của nó là chuyển source cùng dependency thành native executable.

Builder thường chỉ cần:

- Đọc source code của repository đang build.
- Đọc Maven/Gradle dependency từ artifact registry được cho phép.
- Đọc base image hoặc builder image cần thiết.
- Ghi generated sources, cache và binary trong workspace.
- Truy cập CPU/RAM và process cần thiết cho compiler.

Builder không cần quyền đọc production database, truy cập Kubernetes API, sửa registry permission hoặc quản trị cloud account. Nếu build có bước tải schema/config từ hệ thống khác, hãy cấp quyền đọc đúng tài nguyên đó và xem xét đưa dữ liệu cần thiết vào source/artifact.

Native Image compilation không tự yêu cầu ứng dụng phải chạy bằng root. Nếu buildpack, Docker daemon hoặc toolchain cụ thể có yêu cầu quyền hệ thống, hãy xác định đúng thành phần yêu cầu và phạm vi quyền của nó; đừng mặc định cấp privileged cho toàn bộ builder container.

## 5. Builder image, Buildpacks và quyền của daemon

Cloud Native Buildpacks tách builder image khỏi run image. Builder chứa buildpacks và công cụ tạo artifact; run image chứa nền tảng cần để chạy ứng dụng. Runtime container không cần được cấp compiler chỉ vì builder sử dụng compiler.

Với Docker-based build, runner có thể gọi Docker daemon để tạo image. Cần đặc biệt chú ý quyền truy cập daemon: Docker daemon thường chạy với quyền root, và người có thể điều khiển daemon có thể yêu cầu mount filesystem host hoặc tạo container đặc quyền. Vì vậy, quyền truy cập Docker socket có thể tương đương quyền rất cao trên máy runner.

Không mount `/var/run/docker.sock` vào container ứng dụng hoặc container test không đáng tin cậy. Nếu job build cần daemon:

- Dùng runner riêng hoặc runner tạm thời cho job có quyền daemon.
- Không chạy source không tin cậy trên daemon có quyền truy cập host quan trọng.
- Cân nhắc Docker Rootless hoặc BuildKit rootless nếu workflow tương thích.
- Không chia sẻ daemon quản trị với job từ nhiều repository/tenant không cùng mức tin cậy.
- Xóa runner/workspace và credential sau job.

Docker Rootless chạy cả daemon và container dưới user thường trong user namespace, giúp giảm rủi ro khi daemon hoặc container bị khai thác. Rootless có yêu cầu kernel/subuid/subgid và giới hạn tương thích riêng; kiểm tra trước khi chuyển đổi.

## 6. Quyền của CI runner

CI runner là môi trường thực thi workflow, không phải identity của ứng dụng. Runner nên được cấp quyền tối thiểu để checkout, chạy compiler, lưu artifact và gọi đúng dịch vụ của job.

Với runner tự quản lý:

- Ưu tiên runner ephemeral, được tạo cho một job hoặc một nhóm job có cùng mức tin cậy.
- Không dùng chung workspace giữa job có source/credential khác mức tin cậy.
- Không chạy pull request từ fork trên runner có secret hoặc Docker daemon nhạy cảm.
- Hạn chế quyền truy cập mạng từ runner tới production network.
- Không giữ cloud credential, registry token hoặc kubeconfig sau khi job kết thúc.
- Giới hạn quyền điều khiển runner và quyền cài đặt extension/action.
- Cập nhật OS, Docker/BuildKit và runner agent.

Một runner chạy native compilation có thể cần nhiều RAM/CPU, nhưng resource quota không phải quyền bảo mật. Hãy cấu hình giới hạn tài nguyên riêng và tách quyền truy cập hệ thống khỏi mức tài nguyên được cấp.

## 7. Dùng credential ngắn hạn thay cho secret dài hạn

Credential nên có thời hạn ngắn, scope rõ và được cấp ngay trước thao tác cần dùng. Khi nền tảng hỗ trợ workload identity hoặc OIDC federation, CI có thể đổi identity token ngắn hạn lấy credential của registry/cloud thay vì lưu access key lâu dài trong secret store.

Ví dụ với GitHub Actions, job cần yêu cầu OIDC token phải có:

~~~yaml
permissions:
  id-token: write
  contents: read
~~~

`id-token: write` cho phép job yêu cầu JWT từ GitHub OIDC provider; nó **không tự cấp quyền ghi vào cloud resource**. Cloud provider vẫn phải cấu hình trust relationship và IAM role/policy để xác định repository, branch, tag, environment, audience và subject nào được đổi token.

Nên giới hạn trust policy vào repository và ref/environment phát hành cụ thể. Không cho mọi branch hoặc mọi workflow trong organization assume cùng một role production.

Nếu registry/cloud không hỗ trợ OIDC, dùng token riêng cho automation, giới hạn scope, đặt expiration và rotation. Không dùng password tài khoản cá nhân làm credential lâu dài cho pipeline.

## 8. Phân quyền GitHub Actions theo job

Không cấp `write-all` ở cấp workflow nếu chỉ một job cần publish. Đặt mặc định không có quyền, rồi mở đúng scope cho từng job:

~~~yaml
name: native-image-ci

on:
  pull_request:
  push:
    tags:
      - "v*"

permissions: {}

jobs:
  verify:
    runs-on: ubuntu-latest
    permissions:
      contents: read
    steps:
      - uses: actions/checkout@v4
      - name: Build and test native executable
        run: ./mvnw -Pnative verify

  publish:
    if: github.event_name == 'push'
    needs: verify
    runs-on: ubuntu-latest
    permissions:
      contents: read
      packages: write
    steps:
      - uses: actions/checkout@v4
      - name: Build and publish image
        run: ./ci/publish-native-image.sh
~~~

Ví dụ minh họa tách verify và publish. Script publish cần đăng nhập registry bằng token do job cấp và chỉ push vào package/repository được phép. Với GitHub Container Registry, `packages: write` là quyền workflow thường cần để publish package; cấu hình quyền package và repository liên kết cũng phải cho phép.

Trong production, pin action bên thứ ba bằng full commit SHA đã kiểm tra, thay vì chỉ dùng tag có thể thay đổi. Nếu job tạo provenance/attestation hoặc dùng OIDC để ký/phát hành, thêm đúng permission như `attestations: write` hoặc `id-token: write` ở job cần nó. Không thêm quyền này cho job verify chỉ vì job publish cần.

## 9. Tách job kiểm thử và job phát hành

Pull request từ fork hoặc source chưa được review phải được xem là không tin cậy. Một script build có thể chạy mã tùy ý thông qua plugin Maven/Gradle, annotation processor, test hoặc build script.

Thiết kế pipeline:

- **Verify job:** checkout read-only, build/test, không có registry push token, không có production credential.
- **Package job:** đóng gói image sau khi source đã được kiểm tra; quyền chỉ ở registry target.
- **Publish job:** chạy trên protected branch/tag hoặc environment được duyệt, có quyền push image.
- **Deploy job:** dùng identity riêng có quyền cập nhật đúng namespace/environment.
- **Runtime:** không kế thừa token của bất kỳ job CI nào.

Không truyền secret vào job chạy code từ pull request không tin cậy. Với GitHub Actions, tránh dùng `pull_request_target` để checkout và thực thi code của pull request với token có quyền ghi; event này có ngữ cảnh quyền khác và cần được thiết kế cẩn thận.

## 10. Secret cho Maven và Gradle khi build native

Native builder có thể cần credential đọc private Maven repository, plugin repository hoặc Git repository. Credential này chỉ nên có quyền đọc artifact cần thiết.

Với Docker BuildKit, dùng secret mount thay vì Dockerfile `ARG` hoặc `ENV`:

~~~dockerfile
# syntax=docker/dockerfile:1

FROM ghcr.io/graalvm/native-image-community:25 AS native-build

WORKDIR /workspace
COPY . .

RUN --mount=type=secret,id=maven_settings,target=/run/secrets/settings.xml \
    ./mvnw -s /run/secrets/settings.xml -Pnative package
~~~

Truyền file credential cho đúng build step:

~~~bash
docker buildx build \
  --secret id=maven_settings,src=./settings-ci.xml \
  -t orders-service:native .
~~~

Secret mount được đưa vào môi trường thực thi của lệnh build khi cần và không được đóng gói thành layer image theo cách `ARG`/`ENV` có thể làm. Không `COPY` file settings chứa password vào build context hoặc ghi token ra log. Dùng `.dockerignore` để loại credential file, `.env`, private key và kubeconfig khỏi context.

Với Gradle, dùng credential provider hoặc secret mount cho repository credential; không commit password vào `gradle.properties` hay build script. Nếu cache build được chia sẻ giữa tenant/job khác nhau, kiểm tra quyền đọc cache và nội dung cache trước khi dùng chung.

## 11. Phân biệt build secret và runtime secret

Hai loại secret có mục đích và vòng đời khác nhau:

| Secret | Ai sử dụng | Quyền cần có | Khi nào tồn tại |
|---|---|---|---|
| Maven repository token | Builder | Đọc artifact/private plugin | Trong bước tải dependency |
| Git SSH key | Builder | Đọc repository được chỉ định | Trong bước fetch source |
| Registry push token | Publisher | Push vào image repository cụ thể | Trong bước publish |
| Registry pull credential | Kubelet/node hoặc credential provider | Pull image | Khi node khởi chạy container |
| Database password | Ứng dụng runtime | Đúng database/schema/role | Trong thời gian ứng dụng cần kết nối |
| Cloud workload credential | Ứng dụng hoặc deploy job | API và resource được chỉ định | Token ngắn hạn theo workload/job |
| Kubernetes API token | Ứng dụng thực sự gọi API hoặc deploy job | Role/ClusterRole phù hợp | Khi thao tác Kubernetes |

Không dùng database password làm build argument. Không dùng registry push token làm image pull credential. Không copy `kubeconfig` của deploy job vào image. Không để runtime container đọc toàn bộ secret store chỉ vì một bean cần một credential.

## 12. Phân quyền registry: pull, push và admin

Registry nên có danh tính riêng cho từng thao tác:

- **Pull identity:** chỉ đọc image của repository/workload cần chạy.
- **Push identity:** chỉ ghi image vào repository của service được phát hành.
- **Delete/admin identity:** quản trị tag, retention, repository và permission; chỉ cấp cho người hoặc automation quản trị cần thiết.

Ví dụ, job build cần pull base image và dependency image có thể chỉ cần read permission ở các repository đó. Job publish được cấp write cho `orders-service`. Node chạy ứng dụng chỉ cần pull `orders-service`; không cần push hoặc xóa image.

Nếu dùng Docker Hub, chọn token có mức repository permission thấp nhất đáp ứng tác vụ. Token chỉ pull private base image có thể dùng Repo Read-only; automation publish cần quyền ghi ở phạm vi được quản lý. Organization access token có thể giới hạn repository và operation theo cấu hình hỗ trợ.

Không dùng một token cá nhân toàn quyền cho mọi workflow. Credential push cần expiration/rotation và khả năng revoke độc lập.

## 13. Bảo vệ image và tag trong registry

Registry là nơi lưu artifact phát hành; quyền ghi registry vì vậy có ảnh hưởng trực tiếp tới production.

Nên áp dụng:

- Tách repository theo service hoặc trust boundary.
- Bật tag immutability nếu registry hỗ trợ.
- Không cho job thông thường xóa image/tag.
- Chỉ publisher đã kiểm tra mới được tạo tag release.
- Dùng digest bất biến để deploy, không chỉ dùng tag `latest`.
- Bật scan image và lưu SBOM.
- Bật audit log cho login, pull, push, delete và thay đổi permission.
- Giới hạn retention/deletion policy để tránh xóa nhầm image đang chạy.
- Kiểm tra chữ ký/provenance trước khi triển khai nếu tổ chức có admission policy.

Tag giúp con người nhận diện version; digest xác định nội dung image chính xác. Deploy theo digest giúp cluster chạy đúng artifact đã được kiểm thử.

## 14. Quyền runtime container và nguyên tắc non-root

Native executable không cần chạy bằng root chỉ vì được tạo bởi GraalVM. Chọn UID/GID không phải 0, cấp quyền đọc binary và config, chỉ cho ghi vào các thư mục cần thiết.

Ví dụ Dockerfile:

~~~dockerfile
FROM debian:bookworm-slim

WORKDIR /app
COPY --chown=10001:10001 application /app/application

USER 10001:10001
EXPOSE 8080
ENTRYPOINT ["/app/application"]
~~~

Trong runtime, ứng dụng chỉ cần:

- Đọc executable, resource, CA certificate và cấu hình được mount.
- Ghi vào thư mục tạm hoặc volume được cấp quyền.
- Bind cổng ứng dụng.
- Kết nối tới dependency qua network policy.
- Đọc đúng runtime secret cần thiết.

Nếu service chỉ lắng nghe port 8080, thường không cần Linux capability `NET_BIND_SERVICE`. Ưu tiên port lớn hơn 1024 để có thể drop toàn bộ capabilities.

## 15. Docker runtime security options

Ví dụ chạy container với các giới hạn phổ biến:

~~~bash
docker run --rm \
  --user 10001:10001 \
  --read-only \
  --tmpfs /tmp:rw,noexec,nosuid,size=64m \
  --cap-drop=ALL \
  --security-opt=no-new-privileges \
  --memory=512m \
  --cpus=1 \
  --pids-limit=128 \
  --publish 8080:8080 \
  orders-service@sha256:REPLACE_WITH_VERIFIED_DIGEST
~~~

Các lựa chọn có ý nghĩa:

- `--user`: chạy process bằng UID/GID không đặc quyền.
- `--read-only`: không cho ghi lên root filesystem.
- `--tmpfs`: cấp vùng tạm có giới hạn cho file cần tạo lúc chạy.
- `--cap-drop=ALL`: loại bỏ Linux capabilities nếu ứng dụng không cần.
- `no-new-privileges`: ngăn process có thêm privilege qua setuid/setgid.
- `--memory`, `--cpus`, `--pids-limit`: giới hạn tài nguyên và số process/thread.

Docker mặc định áp dụng seccomp profile của daemon; nếu dùng custom profile, cần test trên native runtime và các thư viện JNI thực tế. Không bật `--privileged`, host PID/network namespace hoặc mount host path rộng nếu không có yêu cầu rõ ràng. Đặc biệt không mount Docker socket vào runtime container.

Các giới hạn tài nguyên cần được đo theo workload. Native Image có thể cần vùng nhớ cho heap, thread stack, direct buffer và thư viện native; đặt memory limit quá thấp có thể khiến process bị OOM kill.

## 16. Kubernetes SecurityContext theo nguyên tắc Restricted

Kubernetes cho phép thiết lập user, group, capabilities, seccomp và quyền filesystem ở Pod/container level.

Ví dụ ServiceAccount và Deployment:

~~~yaml
apiVersion: v1
kind: ServiceAccount
metadata:
  name: orders-runtime
  namespace: production
automountServiceAccountToken: false
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: orders-native
  namespace: production
spec:
  replicas: 3
  selector:
    matchLabels:
      app: orders-native
  template:
    metadata:
      labels:
        app: orders-native
    spec:
      serviceAccountName: orders-runtime
      automountServiceAccountToken: false
      imagePullSecrets:
        - name: orders-registry-pull
      securityContext:
        runAsNonRoot: true
        runAsUser: 10001
        runAsGroup: 10001
        seccompProfile:
          type: RuntimeDefault
      containers:
        - name: orders
          image: registry.example.com/orders/orders-service@sha256:REPLACE_WITH_VERIFIED_DIGEST
          ports:
            - name: http
              containerPort: 8080
          securityContext:
            allowPrivilegeEscalation: false
            readOnlyRootFilesystem: true
            capabilities:
              drop:
                - ALL
          volumeMounts:
            - name: tmp
              mountPath: /tmp
      volumes:
        - name: tmp
          emptyDir:
            medium: Memory
            sizeLimit: 64Mi
~~~

Đây là cấu hình nền để bắt đầu, không phải manifest áp dụng nguyên trạng cho mọi ứng dụng. Nếu ứng dụng cần ghi file, mount volume cụ thể với quyền phù hợp. Nếu cần supplementary group để truy cập volume, chỉ thêm group được yêu cầu.

Các trường `runAsNonRoot`, `allowPrivilegeEscalation: false`, `capabilities.drop: ["ALL"]` và `seccompProfile: RuntimeDefault` phù hợp với các yêu cầu chính của Kubernetes Restricted Pod Security Standard trên Linux. Namespace có thể áp dụng Pod Security Admission để thực thi policy này.

## 17. ServiceAccount của ứng dụng và imagePullSecret là hai việc khác nhau

Kubernetes ServiceAccount cung cấp identity cho process trong Pod khi nó gọi Kubernetes API. `imagePullSecrets` được kubelet dùng để xác thực với registry khi kéo image. Hai credential phục vụ hai mục đích khác nhau.

Nếu Spring Boot service không gọi Kubernetes API, đặt:

~~~yaml
automountServiceAccountToken: false
~~~

Khi đó Pod không tự động mount API token vào filesystem container. Việc này không ngăn kubelet sử dụng `imagePullSecrets` để pull image.

Nếu ứng dụng thật sự cần gọi Kubernetes API:

1. Tạo ServiceAccount riêng cho service.
2. Tạo Role chỉ cho phép verb/resource cần thiết trong namespace.
3. Bind Role vào ServiceAccount đó bằng RoleBinding.
4. Dùng token projection/TokenRequest ngắn hạn nếu có thể.
5. Không cấp ClusterRoleBinding rộng nếu chỉ thao tác trong một namespace.
6. Không dùng ServiceAccount của deployment controller cho ứng dụng runtime.

Không dựa vào quyền mặc định của ServiceAccount `default`. Hãy khai báo identity rõ ràng để review và audit.

## 18. Credential pull image ở node runtime

Container process không cần biết password registry để tự kéo image. Trong Kubernetes, kubelet/container runtime thực hiện pull trước khi khởi chạy container.

Các lựa chọn:

- `imagePullSecrets` trong cùng namespace với Pod.
- Credential provider plugin của kubelet.
- Identity của node hoặc workload federation theo khả năng của nền tảng.
- Registry private endpoint với policy cho node pool/workload cụ thể.

Secret dùng cho pull chỉ cần read permission đối với image cần chạy. Không đưa credential pull vào environment variable của Spring Boot. Không mount file `.dockerconfigjson` vào container ứng dụng.

Nếu dùng credential provider hoặc workload identity theo nền tảng, xác minh version Kubernetes, node configuration và cơ chế token exchange được hỗ trợ. Đừng giả định ServiceAccount token trong Pod luôn được kubelet dùng để pull image trên mọi cluster.

## 19. Quyền cloud của runtime workload

Một Spring Boot service có thể gọi object storage, queue, KMS hoặc secret manager. Hãy cấp quyền cho workload theo resource và operation cụ thể.

Ví dụ:

| Nhu cầu | Quyền nên cấp |
|---|---|
| Đọc file cấu hình từ object storage | Read đúng bucket/prefix |
| Ghi báo cáo | Write đúng bucket/prefix |
| Gửi message | Publish đúng topic/queue |
| Nhận message | Consume đúng queue/subscription |
| Giải mã dữ liệu | KMS decrypt đúng key |
| Đọc secret | Get đúng secret name/version |
| Gọi API nội bộ | Identity có audience/scope phù hợp |

Dùng Kubernetes Workload Identity, cloud workload federation hoặc credential ngắn hạn nếu nền tảng hỗ trợ. Tránh lưu cloud access key lâu dài trong Docker image, ConfigMap hoặc manifest. Nếu cần secret mount, chỉ mount vào container và path cần sử dụng.

Tách identity của runtime khỏi identity deploy. Ứng dụng không cần quyền tạo Pod, sửa Deployment hoặc đọc Secret toàn namespace chỉ vì CI cần triển khai nó.

## 20. Network policy và quyền kết nối

Quyền network cũng là một phần của least privilege. Runtime container chỉ nên kết nối tới dependency cần thiết, ví dụ database, broker, DNS và API nội bộ.

Một chính sách tốt xác định:

- Ingress từ ingress controller/service cần thiết.
- Egress tới database port và broker port cần dùng.
- Egress DNS tới resolver của cluster.
- Egress HTTPS tới API/identity provider cần thiết.
- Không cho kết nối tùy ý tới metadata endpoint, node management port hoặc service nhạy cảm khác.

Kubernetes NetworkPolicy cần CNI hỗ trợ enforcement. Chỉ tạo resource NetworkPolicy mà cluster không enforce thì không tạo ra ranh giới network thực tế. Hãy kiểm tra bằng test kết nối được phép và bị từ chối.

Không dùng host network để giải quyết lỗi kết nối thông thường. Chọn Service, DNS và policy đúng thay vì mở toàn bộ network namespace của node.

## 21. Native Image không thay thế các lớp bảo mật container

Native Image loại bỏ nhu cầu JRE khi chạy executable, nhưng process vẫn chạy với quyền của Linux user và có thể truy cập filesystem, network, syscall cùng shared library được cấp.

Một số điểm cần nhớ:

- JNI/native library chạy trong cùng process và có thể thực hiện thao tác native với quyền của process.
- Shared library dễ bị thay thế hoặc thiếu kiểm soát có thể tạo đường thực thi mã.
- Dynamic loader và libc cần được cập nhật như package runtime khác.
- Resource/config được đóng gói vào image vẫn có thể chứa dữ liệu nhạy cảm nếu build sai.
- Native binary không có shell không đồng nghĩa không thể bị khai thác.
- Reflection/AOT metadata là cấu hình tương thích runtime, không phải access control của OS.
- JFR, heap dump và diagnostic endpoint có thể làm lộ dữ liệu nếu mở không đúng quyền.

Giữ nguyên các lớp bảo vệ của container: user namespace, seccomp, capabilities, read-only filesystem, network policy, secret isolation và image provenance.

## 22. Kiểm soát filesystem và file tạm

Native executable có thể cần file tạm, certificate, timezone data, resource ngoài classpath hoặc thư mục chẩn đoán. Chạy read-only root filesystem buộc ứng dụng chỉ ghi vào các vùng được cấp rõ ràng.

Nên:

- Dùng `/tmp` dạng tmpfs hoặc emptyDir với size limit.
- Mount thư mục upload/cache vào đúng path và quota.
- Đặt owner/group theo UID/GID của process.
- Mount secret ở chế độ read-only và quyền đọc tối thiểu.
- Không mount host root, home directory hoặc Docker socket.
- Không copy `application.yml` chứa password vào image.
- Không ghi heap dump hoặc diagnostic file vào volume dùng chung nếu chưa kiểm soát access/retention.

Nếu ứng dụng cần ghi file bền vững, dùng volume/service lưu trữ được thiết kế cho dữ liệu đó. Không dùng container writable layer làm nơi lưu dữ liệu lâu dài.

## 23. SBOM, scan và xác minh artifact

Least privilege giảm tác động của credential bị lộ; supply-chain verification giúp bảo đảm image được tạo từ source và toolchain được tin cậy.

Với mỗi image phát hành, lưu:

- Image digest và source commit.
- GraalVM/JDK, Spring Boot, Native Build Tools version.
- Builder image và run image digest.
- Build arguments và target OS/architecture.
- SBOM cho application dependency và OS package.
- Vulnerability scan result.
- Provenance/attestation và chữ ký nếu pipeline hỗ trợ.

Scan final image, bao gồm shared libraries và CA package, không chỉ scan Maven dependency. Image native không có JRE nhưng vẫn có libc, zlib, JNI library và package hệ điều hành cần patch.

Deploy theo digest đã scan và ký. Admission policy có thể yêu cầu chữ ký/provenance từ identity được phép phát hành. Credential ký nên nằm ở publisher/signing job, không có trong runtime container.

## 24. Audit, rotation và thu hồi quyền

Quyền tối thiểu cần được duy trì sau khi pipeline hoạt động. Mỗi credential nên có owner, purpose, scope, expiration và cách revoke.

Nên định kỳ kiểm tra:

- Credential nào chưa được dùng trong khoảng thời gian dài?
- Token nào có quyền write/delete nhưng job chỉ cần read?
- Repository nào cho phép push từ branch không được bảo vệ?
- Pod nào còn mount ServiceAccount token nhưng không gọi Kubernetes API?
- Workload nào chạy root, privileged hoặc có capability dư?
- Container nào mount host path hoặc Docker socket?
- Role nào có quyền trên namespace/resource rộng hơn nhu cầu?
- Image nào chưa có SBOM, scan hoặc provenance?
- Runner nào tồn tại lâu và giữ workspace/cache/secret cũ?

Khi nghi ngờ credential bị lộ: revoke token, dừng job/runner liên quan, kiểm tra audit log registry/cloud/cluster, xác định digest bị thay đổi, rebuild image từ source tin cậy và redeploy digest đã xác minh. Không chỉ xóa secret khỏi workflow rồi coi sự cố đã kết thúc.

## 25. Tình huống sự cố và cách giới hạn ảnh hưởng

| Sự cố | Nếu quyền bị gom chung | Khi đã tách quyền |
|---|---|---|
| Pull request độc hại chạy build script | Có thể lấy registry push token hoặc cloud key | Verify job không có secret/publish permission |
| Builder bị chiếm quyền | Có thể truy cập production và cluster | Chỉ đọc source/dependency, ghi workspace |
| Registry pull token bị lộ | Có thể push/xóa image | Token chỉ pull repository được giao |
| Runtime container bị khai thác | Có thể đọc Docker socket hoặc host filesystem | Non-root, read-only, no capabilities, không mount host |
| Deployment job bị lộ | Có thể quản trị toàn cluster | Role chỉ cập nhật namespace/environment được giao |
| Ứng dụng cần gọi cloud API | Có thể dùng static key của toàn account | Workload identity với scope resource và token ngắn hạn |
| Image tag bị ghi đè | Node có thể tải artifact khác cùng tag | Tag immutability và deploy theo digest |

Mục tiêu không phải giả định mọi sự cố đều ngăn được. Mục tiêu là khi một thành phần bị xâm nhập, attacker không tự động có được quyền của tất cả thành phần còn lại.

## 26. Bài thực hành: tách quyền build, push và runtime pull

Giả sử service tên `orders-service` được build bằng GraalVM Native Image, lưu ở private registry và chạy trong Kubernetes.

### Bước 1 — Xác định ba danh tính

- Builder: đọc repository và Maven dependency, tạo native executable.
- Publisher: push image vào `registry.example.com/orders/orders-service`.
- Runtime: kubelet pull image; process chạy bằng UID 10001 và không cần registry credential.

Không dùng cùng token cho cả ba.

### Bước 2 — Cấu hình secret build

Dùng BuildKit secret mount để cung cấp Maven settings chỉ trong bước build. Không copy file vào image và không truyền password qua Dockerfile `ARG`/`ENV`.

### Bước 3 — Cấu hình registry

- Builder được pull builder/base image.
- Publisher được push đúng repository.
- Runtime pull credential chỉ đọc image.
- Không cấp quyền delete/admin cho hai identity tự động.

### Bước 4 — Hardening runtime

Chạy container bằng non-root, read-only root filesystem, drop toàn bộ capabilities và mount `/tmp` có giới hạn. Không mount Docker socket hoặc host path.

### Bước 5 — Hardening Kubernetes identity

Tạo ServiceAccount riêng. Nếu service không gọi Kubernetes API, tắt automount token. Khai báo `imagePullSecrets` riêng cho kubelet và chỉ dùng secret có pull permission.

### Bước 6 — Kiểm tra âm tính

Thực hiện các kiểm tra sau trong môi trường test:

- Builder không thể truy cập production database.
- Verify job không thể push image release.
- Pull identity không thể push hoặc delete image.
- Runtime process không đọc được ServiceAccount token khi automount đã tắt.
- Runtime container không ghi được root filesystem.
- Runtime container không có capability ngoài nhu cầu.
- Runtime identity không thể đọc secret của service khác.
- Deployment identity không thể sửa resource ngoài namespace được giao.

Một kiểm tra bảo mật có giá trị phải xác nhận cả quyền được phép và hành động bị từ chối.

## 27. Checklist trước khi phát hành

- [ ] Builder chỉ đọc source/dependency cần thiết và ghi vào workspace riêng.
- [ ] Runner được cô lập, ưu tiên ephemeral và không dùng chung daemon với job không tin cậy.
- [ ] Không cấp Docker socket cho application/test container.
- [ ] Pull request không nhận secret, registry push token hoặc production credential.
- [ ] Build secret dùng secret mount/secret store, không dùng Dockerfile ARG/ENV.
- [ ] CI credential ngắn hạn qua OIDC/federation nếu nền tảng hỗ trợ.
- [ ] Publisher chỉ push repository được giao; không có quyền delete/admin.
- [ ] Runtime pull identity chỉ đọc image cần triển khai.
- [ ] Image được pin bằng digest, scan và lưu SBOM/provenance.
- [ ] Container chạy non-root, không privileged và không cho privilege escalation.
- [ ] Root filesystem read-only; thư mục ghi được mount riêng có quota.
- [ ] Drop toàn bộ Linux capabilities nếu service không cần capability đặc biệt.
- [ ] Seccomp profile phù hợp được bật.
- [ ] Kubernetes ServiceAccount riêng và RBAC tối thiểu.
- [ ] Tắt automount ServiceAccount token nếu ứng dụng không gọi Kubernetes API.
- [ ] Registry pull secret tách khỏi credential của ứng dụng.
- [ ] Cloud workload identity chỉ có quyền resource/operation cần thiết.
- [ ] NetworkPolicy được CNI thực thi và chỉ mở luồng cần thiết.
- [ ] Credential có owner, expiration, rotation và quy trình revoke.
- [ ] Đã kiểm thử các hành động phải bị từ chối.

## 28. Ghi nhớ

Quyền tối thiểu cho Native Image container phải được áp dụng ở mọi giai đoạn: builder, CI runner, publisher, registry, deployment và runtime. Builder cần đọc source/dependency; publisher cần push vào repository được giao; kubelet cần pull image; ứng dụng chỉ cần quyền truy cập dependency nghiệp vụ của nó.

Tách credential, dùng OIDC/token ngắn hạn, BuildKit secret mount, registry read/write riêng, runner cô lập và image digest bất biến. Trong runtime, chạy non-root, read-only, drop capabilities, seccomp, network policy và ServiceAccount/RBAC tối thiểu. Nếu ứng dụng không gọi Kubernetes API, không cần mount ServiceAccount token.

Native Image không tự tạo sandbox. JNI, shared libraries và executable vẫn có quyền của process/container. **Một pipeline an toàn cần bảo vệ cả artifact lẫn danh tính có quyền tạo, phát hành, triển khai và chạy artifact đó.**

### Tài liệu tham khảo

- Docker Engine — Security: https://docs.docker.com/engine/security/
- Docker Engine — Rootless mode: https://docs.docker.com/engine/security/rootless/
- Docker Build — Build secrets: https://docs.docker.com/build/building/secrets/
- Docker Build — SecretsUsedInArgOrEnv check: https://docs.docker.com/reference/build-checks/secrets-used-in-arg-or-env/
- Docker Hub — Access token permissions: https://docs.docker.com/security/access-tokens/reference/
- GitHub Actions — OpenID Connect: https://docs.github.com/en/actions/reference/security/oidc
- GitHub Actions — Workflow permissions: https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax
- Kubernetes — Configure a Security Context: https://kubernetes.io/docs/tasks/configure-pod-container/security-context/
- Kubernetes — Pod Security Standards: https://kubernetes.io/docs/concepts/security/pod-security-standards/
- Kubernetes — Service Accounts: https://kubernetes.io/docs/concepts/security/service-accounts/
- Kubernetes — Application Security Checklist: https://kubernetes.io/docs/concepts/security/application-security-checklist/

Chi tiết quyền, token exchange, registry scope và Pod Security Admission phụ thuộc phiên bản CI, registry, Kubernetes và cloud provider. Hãy xác minh policy đang có hiệu lực trên môi trường triển khai, không chỉ dựa vào YAML đã commit.
