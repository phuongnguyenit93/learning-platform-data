# Container image, runtime và vòng đời container

## Mục tiêu bài học

Container là một cách đóng gói và chạy ứng dụng cùng các dependency cần thiết trong một môi trường cô lập ở mức hệ điều hành. Container giúp triển khai nhất quán giữa máy phát triển, máy ảo và cụm Kubernetes, đồng thời cho phép khởi động nhanh và sử dụng tài nguyên hiệu quả. Tuy nhiên, container không phải một máy ảo thu nhỏ: container thường chia sẻ kernel với host, còn image, runtime, process, network và storage đều có vòng đời riêng.

Để vận hành workload compute trên cloud, cần hiểu image được tạo và phân phối ra sao, runtime biến image thành process như thế nào, container chuyển qua các trạng thái nào và điều gì xảy ra khi process dừng hoặc bị thay thế.

Sau bài học này, bạn có thể:

- Phân biệt container, image, registry và runtime.
- Giải thích cấu trúc OCI image, manifest, config và layer.
- Viết Dockerfile có thể tái lập, tối ưu cache và giảm bề mặt tấn công.
- Phân biệt Docker Engine, containerd, CRI-O, CRI và OCI runtime.
- Mô tả các bước tạo, khởi động, dừng và xóa container.
- Thiết kế ứng dụng hỗ trợ signal, graceful shutdown và health check.
- Quản lý network, volume, log và giới hạn tài nguyên của container.
- Bảo vệ image và runtime trong môi trường VM, cloud và Kubernetes.

## 1. Container là gì?

Container là một môi trường thực thi cô lập cho một hoặc nhiều process. Trên Linux, container được xây dựng chủ yếu từ các cơ chế của kernel:

- **Namespaces** giới hạn góc nhìn của process về một số tài nguyên như process ID, network, mount, hostname, IPC và user.
- **Control groups (cgroups)** đo lường và giới hạn tài nguyên như CPU, memory, process count và I/O.
- **Filesystem isolation** cung cấp root filesystem riêng cho container, thường được ghép từ image layers và writable layer.
- **Capabilities, seccomp và LSM** giới hạn các thao tác kernel mà process có thể thực hiện.

Container thường chia sẻ kernel của host. Điều này giúp container nhẹ và khởi động nhanh hơn VM, nhưng cũng có nghĩa kernel là ranh giới bảo mật quan trọng. Một lỗ hổng kernel hoặc cấu hình đặc quyền sai có thể ảnh hưởng nhiều container cùng host.

VM ảo hóa phần cứng và thường chạy kernel riêng trong guest OS. Container cô lập process ở cấp hệ điều hành và thường dùng chung kernel. Hai mô hình có thể kết hợp: container chạy bên trong VM để tăng lớp cô lập và đơn giản hóa quản lý hạ tầng.

| Đặc điểm | Container | Virtual machine |
|---|---|---|
| Kernel | Thường dùng chung kernel host | Guest OS có kernel riêng |
| Đóng gói | Image gồm filesystem và metadata | Disk image gồm OS và phần mềm |
| Khởi động | Thường nhanh, tùy ứng dụng | Thường cần boot guest OS |
| Overhead | Thường thấp hơn | Thường cao hơn do guest OS |
| Cô lập | Namespaces, cgroups, security controls | Hypervisor và guest OS |
| Portability | Phụ thuộc kiến trúc, kernel interface và runtime | Phụ thuộc hypervisor, image và phần cứng ảo |
| Vận hành | Runtime, image, registry và orchestrator | Hypervisor, VM image và guest management |

Không nên kết luận container luôn an toàn hơn hoặc nhanh hơn VM. Hiệu năng và mức cô lập phụ thuộc workload, cấu hình kernel, runtime, storage, network và cách triển khai.

## 2. Image, container và registry

Ba khái niệm nền tảng:

- **Container image:** gói bất biến mô tả filesystem, metadata và cấu hình mặc định để tạo container.
- **Container:** một instance đang hoặc đã từng chạy từ image, có process, trạng thái runtime và thường có writable layer riêng.
- **Container registry:** dịch vụ lưu trữ, phân phối và quản lý image theo repository và tag/digest.

Có thể tạo nhiều container từ cùng một image. Image không thay đổi khi một container ghi dữ liệu vào writable layer; dữ liệu đó thuộc instance container hoặc volume được mount vào.

~~~mermaid
flowchart LR
    S["Source code"] --> B["Image build"]
    B --> I["OCI image"]
    I --> R["Container registry"]
    R --> P["Pull image"]
    P --> RT["Container runtime"]
    RT --> C1["Container A"]
    RT --> C2["Container B"]
    C1 --> V1["Writable layer / volume"]
    C2 --> V2["Writable layer / volume"]
~~~

### 2.1. Repository, tag và digest

Một image reference thường có dạng:

~~~text
registry.example.com/team/orders-api:2.4.1
~~~

Trong đó:

- registry.example.com là registry.
- team/orders-api là repository.
- 2.4.1 là tag.

Tag là tên dễ đọc, nhưng có thể được di chuyển để trỏ tới image khác. Vì vậy, tag latest hoặc tag version không tự bảo đảm nội dung bất biến nếu registry cho phép ghi đè.

Digest là định danh nội dung theo hash, thường có dạng:

~~~text
registry.example.com/team/orders-api@sha256:<digest>
~~~

Khi cần triển khai có thể tái lập, pin image theo digest giúp bảo đảm workload dùng đúng nội dung đã kiểm thử. Tag vẫn hữu ích cho con người và quy trình phát hành; digest phù hợp để xác định chính xác artifact.

### 2.2. Image registry

Registry có thể là dịch vụ cloud, registry riêng của tổ chức hoặc dịch vụ tích hợp với nền tảng phát triển. Registry thường hỗ trợ:

- Push và pull image.
- Quản lý repository, tag và digest.
- Xác thực và phân quyền.
- Lưu manifest và layer.
- Quét lỗ hổng hoặc tích hợp policy.
- Retention, replication và audit log.

Trong môi trường cloud, đặt registry gần workload có thể giảm thời gian pull và chi phí truyền dữ liệu. Tuy nhiên, cần có quyền truy cập theo workload identity hoặc cơ chế credential ngắn hạn; không nhúng registry password vào image.

## 3. Cấu trúc OCI image

Open Container Initiative (OCI) chuẩn hóa một số định dạng và giao diện để hệ sinh thái container có thể tương tác với nhau.

OCI image thường có các thành phần:

- **Image manifest:** mô tả config và danh sách layer của một image cho một platform.
- **Image config:** chứa metadata như command mặc định, environment, user, working directory và history.
- **Layers:** các phần filesystem được đóng gói thành blob bất biến.
- **Image index/manifest list:** có thể trỏ tới nhiều manifest cho các platform khác nhau, ví dụ linux/amd64 và linux/arm64.

~~~mermaid
flowchart TD
    IDX["OCI image index"] --> M1["Manifest: linux/amd64"]
    IDX --> M2["Manifest: linux/arm64"]
    M1 --> CFG1["Image config"]
    M1 --> L1["Layer 1"]
    M1 --> L2["Layer 2"]
    M1 --> L3["Layer 3"]
    M2 --> CFG2["Image config"]
    M2 --> L4["Layer 1"]
    M2 --> L5["Layer 2"]
~~~

Khi pull image đa kiến trúc, client/runtime chọn manifest phù hợp với platform hiện tại. Nếu image không có manifest cho kiến trúc của node, container có thể không khởi động hoặc không chạy được binary bên trong.

### 3.1. Layer và copy-on-write

Mỗi lệnh filesystem trong quá trình build có thể tạo một layer. Các layer được chia sẻ giữa nhiều image hoặc container nếu nội dung trùng nhau và runtime hỗ trợ cơ chế lưu trữ tương ứng.

Khi tạo container, runtime ghép các layer read-only thành root filesystem và thêm một writable layer cho instance. Đây là mô hình copy-on-write thường gặp với storage driver như OverlayFS trên Linux.

Hệ quả vận hành:

- Image layer bất biến và có thể được cache.
- Nhiều container có thể dùng chung các layer image.
- Thay đổi trong writable layer không sửa image gốc.
- Ghi nhiều dữ liệu vào writable layer có thể làm tăng I/O và dung lượng.
- Xóa container thường làm mất writable layer nếu dữ liệu chưa được lưu vào volume hoặc hệ thống ngoài.

Không dùng writable layer làm nơi lưu dữ liệu nghiệp vụ cần tồn tại qua lần recreate container.

### 3.2. Pull và unpack image

Khi runtime cần chạy image chưa có trên host, thường phải:

1. Xác thực với registry.
2. Lấy manifest hoặc image index.
3. Chọn manifest phù hợp với platform.
4. Tải các layer chưa có trong local content store.
5. Xác minh digest và tính toàn vẹn.
6. Giải nén/unpack layer thành snapshot filesystem.
7. Tạo container root filesystem từ snapshot và writable layer.

Layer đã có trên host có thể được tái sử dụng, vì vậy pull không nhất thiết tải toàn bộ image mỗi lần. Tuy nhiên, image quá lớn hoặc có nhiều layer không hiệu quả có thể kéo dài scale-out và tăng chi phí network/storage.

## 4. Thiết kế Dockerfile và build image

Dockerfile mô tả cách tạo image. Một Dockerfile tốt cần rõ ràng, có thể tái lập, tận dụng build cache và giảm thành phần không cần thiết trong runtime image.

Ví dụ Java với multi-stage build:

~~~dockerfile
# Stage build: dùng JDK và Maven để biên dịch ứng dụng
FROM maven:3.9-eclipse-temurin-21 AS build
WORKDIR /workspace

# Sao chép manifest dependency trước để tận dụng build cache
COPY pom.xml .
RUN mvn -B -q dependency:go-offline

COPY src ./src
RUN mvn -B -DskipTests package

# Stage runtime: chỉ giữ JRE và artifact đã build
FROM eclipse-temurin:21-jre
WORKDIR /app

RUN groupadd --system app \
    && useradd --system --uid 10001 --gid app app

COPY --from=build --chown=10001:10001 \
    /workspace/target/app.jar /app/app.jar

USER 10001:10001
EXPOSE 8080

ENTRYPOINT ["java", "-jar", "/app/app.jar"]
~~~

Ví dụ giả định dự án có pom.xml, source Maven và tạo ra target/app.jar. Tên artifact, JDK/JRE version và lệnh build phải điều chỉnh theo dự án. Với image production, nên pin base image theo digest hoặc quản lý version đã kiểm thử.

### 4.1. Multi-stage build

Multi-stage build dùng một stage để biên dịch/test/package và stage khác làm runtime. Chỉ artifact cần thiết được sao chép sang image cuối.

Lợi ích:

- Không mang compiler, build tool và source code vào runtime image nếu không cần.
- Giảm kích thước image và số package.
- Giảm bề mặt tấn công.
- Tách dependency build khỏi dependency chạy.
- Có thể dùng cache riêng cho dependency.

Một runtime image nhỏ vẫn cần chứng thư CA, timezone data, native library hoặc công cụ chẩn đoán nếu ứng dụng yêu cầu. Không xóa package theo kích thước mà chưa kiểm tra runtime dependency.

### 4.2. Tối ưu build cache

Docker build cache dựa trên nội dung instruction và các file liên quan. Khi một bước thay đổi, các bước sau có thể cần chạy lại.

Một số nguyên tắc:

- Sao chép file dependency manifest trước source code nếu dependency ít thay đổi hơn source.
- Gom các lệnh cài package hợp lý để giảm layer dư thừa.
- Không đưa file build output hoặc thư mục local không cần thiết vào build context.
- Dùng .dockerignore để loại target, .git, log, secret và file tạm.
- Giữ các bước build có kết quả xác định.
- Dùng BuildKit cache mount nếu pipeline hỗ trợ và có chính sách cache phù hợp.

Ví dụ .dockerignore:

~~~text
.git
.gitignore
target/
build/
.gradle/
.idea/
*.log
.env
.env.*
secrets/
~~~

Danh sách cần điều chỉnh theo dự án. Không loại file mà build cần, và không đưa secret vào build context.

### 4.3. Build argument và secret

Build argument (ARG) có thể xuất hiện trong metadata hoặc lịch sử build tùy cách sử dụng và builder. Không dùng ARG hoặc ENV để truyền password, token hay private key.

Với BuildKit, dùng secret mount để cấp secret tạm thời cho một bước build. Secret mount không được ghi tự động vào layer nếu lệnh không sao chép nó sang filesystem, nhưng script build vẫn có thể làm lộ secret trong log hoặc artifact. Chỉ cấp secret cho bước cần thiết và thu hồi sau build.

### 4.4. ENTRYPOINT, CMD và exec form

ENTRYPOINT xác định executable chính; CMD thường cung cấp tham số mặc định hoặc command mặc định. Exec form dùng mảng JSON:

~~~dockerfile
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
~~~

Exec form giúp process chính nhận signal trực tiếp hơn so với shell form. Với shell form, shell có thể trở thành process cha và không chuyển tiếp signal như mong muốn nếu không dùng exec đúng cách.

Trong container, process chính thường chạy với PID 1 trong PID namespace. PID 1 có một số hành vi signal và reaping process khác với process thông thường. Nếu ứng dụng tạo child process, cần bảo đảm child được thu hồi đúng cách; có thể dùng init nhỏ như tini khi cần.

## 5. Build, tag, push và chạy image

Một luồng phát hành cơ bản:

~~~bash
# Build image
docker build -t orders-api:2.4.1 .

# Tag theo registry
docker tag orders-api:2.4.1 registry.example.com/team/orders-api:2.4.1

# Đăng nhập registry bằng credential được cấp an toàn
docker login registry.example.com

# Push image
docker push registry.example.com/team/orders-api:2.4.1

# Chạy thử container
docker run --name orders-api-test \
  --publish 8080:8080 \
  --memory 1g \
  --cpus 1.5 \
  registry.example.com/team/orders-api:2.4.1
~~~

Không ghi credential trực tiếp trong script hoặc lịch sử shell. Trong CI/CD, ưu tiên workload identity hoặc secret store và credential ngắn hạn.

Các lệnh kiểm tra thường dùng:

~~~bash
docker image ls
docker image inspect orders-api:2.4.1
docker container ls -a
docker logs orders-api-test
docker inspect orders-api-test
docker stats orders-api-test
docker stop orders-api-test
docker rm orders-api-test
~~~

Docker CLI là công cụ phổ biến để build và quản lý container. Trong Kubernetes, node runtime thường được quản lý qua CRI; không nhất thiết phải có Docker Engine trên node.

## 6. Container runtime và các lớp giao tiếp

Runtime chịu trách nhiệm biến image thành môi trường thực thi và quản lý process/container trên host. Hệ sinh thái có nhiều lớp, mỗi lớp có nhiệm vụ khác nhau.

| Thành phần | Vai trò |
|---|---|
| Container engine | Cung cấp API/CLI và điều phối thao tác image/container |
| CRI (Container Runtime Interface) | Giao diện để kubelet giao tiếp với container runtime |
| High-level runtime | Quản lý image, metadata, snapshot và vòng đời container |
| Low-level OCI runtime | Tạo process/container theo OCI Runtime Specification |
| Kernel | Cung cấp namespaces, cgroups, filesystem, network và syscall |

### 6.1. Docker Engine

Docker Engine là nền tảng quản lý container có API và Docker CLI. Kiến trúc triển khai truyền thống gồm Docker client, daemon và các thành phần runtime bên dưới. Docker có thể dùng containerd và OCI runtime để tạo container.

Docker rất hữu ích trong môi trường phát triển và build pipeline. Kubernetes hiện đại không yêu cầu Docker Engine trên node; kubelet giao tiếp với runtime qua CRI.

### 6.2. containerd và CRI-O

**containerd** là container runtime cấp cao, quản lý image, snapshot và container lifecycle. Nó có thể dùng OCI runtime như runc để tạo process container. Kubernetes thường tích hợp containerd qua CRI plugin.

**CRI-O** là runtime được thiết kế cho Kubernetes, triển khai CRI và dùng OCI runtime để tạo container.

Hai lựa chọn này đều có thể chạy workload Kubernetes. Chọn theo nền tảng, hỗ trợ của nhà cung cấp, hệ sinh thái tooling, chính sách bảo mật và yêu cầu vận hành.

### 6.3. runc và OCI runtime

runc là một triển khai OCI runtime phổ biến. Nó đọc bundle cấu hình container và yêu cầu kernel tạo môi trường process với namespace, cgroup, mount và các thiết lập cần thiết.

OCI Runtime Specification mô tả cấu hình và lifecycle ở mức thấp. Runtime khác có thể cung cấp thêm lớp cô lập hoặc cơ chế bảo mật riêng; không phải mọi runtime đều có cùng threat model.

### 6.4. CRI trong Kubernetes

Kubelet dùng CRI để yêu cầu runtime thực hiện các thao tác như:

- Pull image.
- Tạo Pod sandbox.
- Tạo, khởi động và dừng container.
- Kiểm tra trạng thái container.
- Thu thập một số thông tin runtime và log.

Pod sandbox thường tạo môi trường dùng chung một số namespace/network cho các container trong cùng Pod, tùy cấu hình runtime. Các container trong một Pod có thể chia sẻ network namespace và giao tiếp qua localhost, nhưng vẫn có thể có filesystem và resource limit riêng.

~~~mermaid
flowchart TD
    K["Kubelet"] --> CRI["CRI API"]
    CRI --> R["containerd hoặc CRI-O"]
    R --> IMG["Image / snapshot service"]
    R --> OCI["OCI runtime"]
    OCI --> L["Linux kernel"]
    L --> NS["Namespaces"]
    L --> CG["cgroups"]
    L --> FS["Mount / root filesystem"]
    L --> PR["Container processes"]
~~~

## 7. Vòng đời container

Ở mức tổng quát, container đi qua các giai đoạn:

1. Image được pull hoặc lấy từ local content store.
2. Runtime chuẩn bị root filesystem và metadata.
3. Runtime tạo container và cấu hình namespace/cgroup/mount.
4. Runtime khởi chạy process chính.
5. Process chạy, nhận traffic và ghi log.
6. Process kết thúc, bị dừng hoặc bị runtime terminate.
7. Runtime lưu trạng thái kết thúc và giải phóng tài nguyên.
8. Container có thể bị xóa; writable layer có thể bị loại bỏ.

Tên trạng thái hiển thị phụ thuộc công cụ. Docker thường có các trạng thái như created, running, paused, restarting, exited và dead. Kubernetes hiển thị trạng thái Pod như Pending, Running, Succeeded, Failed hoặc Unknown; trạng thái container trong Pod có thể là Waiting, Running hoặc Terminated.

Không đồng nhất trạng thái Pod với trạng thái một container. Một Pod có thể Running trong khi một container đang restart hoặc sidecar chưa sẵn sàng.

### 7.1. Created và running

- **Created:** metadata và cấu hình container đã được tạo, nhưng process chính chưa chạy.
- **Running:** process chính đang thực thi.
- **Paused:** process bị đóng băng bởi runtime nếu tính năng được hỗ trợ.
- **Exited/Terminated:** process chính đã kết thúc; runtime giữ thông tin exit code và trạng thái.
- **Removing/Deleted:** container được xóa và tài nguyên runtime được giải phóng.

Container không tự động trở lại trạng thái running sau khi process thoát. Restart policy hoặc orchestrator quyết định có tạo lại hoặc khởi động lại container hay không.

### 7.2. Restart policy

Trong Docker, restart policy có thể gồm no, on-failure, always và unless-stopped. Chính sách cụ thể quyết định container được restart trong trường hợp nào và có phụ thuộc trạng thái daemon hay thao tác người dùng hay không.

Trong Kubernetes, restartPolicy của Pod thường là Always, OnFailure hoặc Never. Với Deployment, Pod thường dùng Always; controller tạo Pod thay thế khi Pod không còn đáp ứng trạng thái mong muốn. Job thường dùng OnFailure hoặc Never tùy thiết kế.

Restart không giải quyết nguyên nhân lỗi. Nếu process crash vì cấu hình sai hoặc dependency không sẵn sàng, restart liên tục có thể tạo crash loop và tăng tải lên hệ thống phụ thuộc.

## 8. Dừng container và graceful shutdown

Khi container được dừng có kiểm soát, runtime thường gửi tín hiệu tới process chính, chờ một khoảng thời gian rồi mới gửi tín hiệu buộc dừng nếu process chưa thoát. Với Docker, tín hiệu mặc định thường là SIGTERM và sau timeout là SIGKILL; thời gian chờ có thể cấu hình. Kubernetes cũng có termination grace period và quy trình gửi tín hiệu dừng tới container.

Một ứng dụng cần xử lý shutdown để:

- Ngừng nhận request hoặc message mới.
- Hoàn tất request/job đang xử lý trong giới hạn.
- Commit transaction và checkpoint.
- Flush log hoặc buffer quan trọng.
- Đóng connection pool, consumer và thread pool.
- Kết thúc process trước khi hết grace period.

Nếu process không xử lý SIGTERM hoặc không thoát kịp, runtime có thể gửi SIGKILL. SIGKILL không thể được bắt hoặc xử lý bởi ứng dụng.

### 8.1. Graceful shutdown trong Java

Java shutdown hook có thể giúp đóng tài nguyên khi JVM nhận tín hiệu kết thúc có thể xử lý:

~~~java
public final class Application {
    public static void main(String[] args) {
        WorkerService worker = new WorkerService();
        worker.start();

        Runtime.getRuntime().addShutdownHook(
            new Thread(() -> {
                worker.stopAcceptingNewWork();
                worker.awaitInFlightTasks();
                worker.closeResources();
            }, "shutdown-hook")
        );
    }
}
~~~

Đây là mã minh họa. Các phương thức cần có timeout và xử lý exception phù hợp. Không chờ vô hạn trong shutdown hook; orchestrator chỉ dành một khoảng thời gian hữu hạn trước khi buộc dừng.

Với container, dùng exec form cho ENTRYPOINT để Java process nhận tín hiệu trực tiếp. Nếu cần shell wrapper, dùng exec java ... để thay shell bằng process Java.

### 8.2. PID 1 và process reaping

Process đầu tiên trong PID namespace thường có PID 1. Nếu ứng dụng spawn child process nhưng không thu hồi process đã kết thúc, zombie process có thể tích tụ. Một init nhỏ như tini có thể forward signal và reap orphaned child process.

Không cần thêm init process nếu ứng dụng chỉ chạy một process và xử lý child process đúng cách. Hãy chọn theo cấu trúc process thực tế.

## 9. Health check: health, readiness và startup

Health check giúp runtime hoặc orchestrator biết process có hoạt động và có thể nhận traffic hay không. Cần phân biệt ba câu hỏi:

- **Startup:** ứng dụng đã hoàn tất giai đoạn khởi động chưa?
- **Readiness:** ứng dụng có thể phục vụ request ngay lúc này không?
- **Liveness:** process có còn hoạt động và có thể tự phục hồi không?

Trong Docker, HEALTHCHECK có thể chạy một lệnh định kỳ và đánh dấu container healthy/unhealthy. Docker health status không tự động đồng nghĩa load balancer sẽ loại target hoặc Docker sẽ restart container khi unhealthy; hành vi đó cần cơ chế điều phối riêng.

Trong Kubernetes, startup, readiness và liveness probe có semantics riêng:

- Startup probe cho phép ứng dụng khởi động lâu mà chưa bị liveness probe kết luận thất bại.
- Readiness probe quyết định Pod có đủ điều kiện nhận traffic qua Service.
- Liveness probe có thể khiến kubelet restart container khi phát hiện process không thể phục hồi theo điều kiện probe.

Không dùng liveness để kiểm tra mọi external dependency như database hoặc API bên ngoài. Một dependency tạm thời lỗi có thể khiến tất cả container restart liên tục.

### 9.1. Ví dụ Docker HEALTHCHECK

~~~dockerfile
HEALTHCHECK --interval=30s --timeout=3s --start-period=20s --retries=3 \
  CMD curl --fail --silent http://127.0.0.1:8080/health/live || exit 1
~~~

Ví dụ giả định image có curl và ứng dụng cung cấp endpoint liveness tại đường dẫn này. Health check chỉ nên kiểm tra process có thể tiếp tục hoạt động; readiness và dependency checks cần được thiết kế riêng. Nếu image không có curl/wget, có thể dùng probe nhỏ đã được kiểm soát hoặc cơ chế health check của orchestrator, thay vì thêm công cụ vào runtime image mà chưa cân nhắc kích thước và bề mặt tấn công.

### 9.2. Ví dụ Kubernetes probes

~~~yaml
startupProbe:
  httpGet:
    path: /health/startup
    port: 8080
  periodSeconds: 5
  failureThreshold: 36

readinessProbe:
  httpGet:
    path: /health/ready
    port: 8080
  periodSeconds: 5
  timeoutSeconds: 2
  failureThreshold: 3

livenessProbe:
  httpGet:
    path: /health/live
    port: 8080
  periodSeconds: 10
  timeoutSeconds: 2
  failureThreshold: 3
~~~

Các endpoint phải được triển khai đúng semantics. Readiness có thể trả lỗi khi ứng dụng đang drain; liveness chỉ nên thất bại khi process thực sự cần restart.

## 10. Network của container

Container có thể có network namespace riêng và giao diện mạng ảo. Runtime hoặc nền tảng điều phối thiết lập địa chỉ IP, route, DNS và kết nối giữa container với host hoặc mạng bên ngoài.

Các khái niệm thường gặp:

- **Bridge network:** các container kết nối qua bridge ảo trên host.
- **Host network:** container dùng network namespace của host, giảm một lớp network isolation nhưng làm thay đổi cách quản lý port.
- **Overlay network:** tạo mạng logic qua nhiều host.
- **CNI:** giao diện plugin mạng thường dùng trong Kubernetes để cấu hình network cho Pod.
- **Port publishing:** ánh xạ port của container ra host hoặc endpoint bên ngoài.
- **Service discovery/DNS:** tìm container hoặc service bằng tên thay vì IP cố định.

Ví dụ Docker:

~~~bash
# Tạo network riêng
docker network create app-net

# Chạy database chỉ trong network nội bộ của ứng dụng
docker run -d --name db --network app-net postgres:16

# Chạy API và publish HTTP port ra host
docker run -d --name api \
  --network app-net \
  --publish 8080:8080 \
  orders-api:2.4.1
~~~

Ví dụ chỉ minh họa network kết nối. Trong production, cần cấu hình password, volume, TLS, firewall và image digest phù hợp. Không publish port database ra Internet nếu không có yêu cầu và kiểm soát mạng rõ ràng.

### 10.1. DNS và địa chỉ IP

IP của container có thể thay đổi khi container được tạo lại. Ứng dụng nên dùng service discovery hoặc DNS name ổn định thay vì lưu địa chỉ IP container lâu dài.

Trong Kubernetes, Pod IP có thể thay đổi khi Pod được thay thế; Service cung cấp endpoint ổn định cho workload. Network policy có thể giới hạn luồng traffic giữa namespace, Pod hoặc workload theo plugin hỗ trợ.

## 11. Storage và dữ liệu của container

Writable layer của container thường phù hợp cho file tạm và dữ liệu có thể tạo lại. Dữ liệu cần tồn tại qua lần recreate phải nằm trên volume hoặc dịch vụ lưu trữ độc lập.

Các dạng lưu trữ thường gặp:

| Loại | Vòng đời | Trường hợp sử dụng |
|---|---|---|
| Writable container layer | Gắn với container instance | File tạm, cache có thể tạo lại |
| Bind mount | Ánh xạ path host vào container | Development hoặc truy cập path host có kiểm soát |
| Named volume | Được runtime quản lý, tồn tại độc lập với container | Dữ liệu cần giữ trên host |
| Ephemeral volume | Thường tồn tại theo Pod hoặc workload lifecycle | Scratch data, cache tạm |
| Persistent volume | Storage được quản lý độc lập theo policy | Database, stateful workload |
| Object storage | Dữ liệu truy cập qua API | Artifact, backup, checkpoint và dữ liệu chia sẻ |

Không phải named volume nào cũng tự động replicate hoặc tồn tại khi host mất. Độ bền phụ thuộc driver, backend và chính sách storage.

### 11.1. Ví dụ Docker volume

~~~bash
docker volume create orders-data

docker run -d --name orders-db \
  --mount source=orders-data,target=/var/lib/postgresql/data \
  postgres:16
~~~

Ví dụ chỉ minh họa cách gắn volume; cấu hình database production cần secret, backup, network, version pinning và chính sách storage riêng.

### 11.2. Ephemeral storage trong Kubernetes

Container writable layer, log và emptyDir có thể sử dụng ephemeral storage của node. Nếu workload ghi quá nhiều dữ liệu tạm hoặc log, node có thể gặp disk pressure và kubelet có thể evict Pod.

Với workload có ghi nhiều dữ liệu, cần đặt ephemeral-storage requests/limits khi nền tảng hỗ trợ, theo dõi node filesystem và chuyển dữ liệu cần giữ sang persistent storage.

## 12. Giới hạn tài nguyên bằng cgroups

Container không tự động có một lượng CPU và RAM cố định. Runtime và orchestrator cấu hình cgroups để đo lường và áp dụng giới hạn.

### 12.1. CPU

CPU có thể được điều khiển qua:

- CPU shares/weight: mức ưu tiên tương đối khi tranh chấp.
- CPU quota/period: giới hạn lượng CPU time trong một chu kỳ.
- CPU set: giới hạn tập CPU mà process có thể chạy.

Trong Docker, --cpus, --cpu-shares và --cpuset-cpus có thể cấu hình các cơ chế liên quan. Trong Kubernetes, CPU request ảnh hưởng scheduling và shares/weight; CPU limit thường được áp dụng như quota.

CPU limit quá thấp có thể làm ứng dụng bị throttling và tăng latency. Không chỉ nhìn CPU usage trung bình; cần xem throttling và tail latency.

### 12.2. Memory

Memory limit đặt giới hạn cgroup cho container. Nếu container vượt giới hạn, kernel có thể kích hoạt OOM handling và kết thúc một hoặc nhiều process trong cgroup.

Với Java, heap không nên chiếm toàn bộ memory limit. Cần chừa chỗ cho metaspace, code cache, thread stack, direct buffer, native library và agent.

Trong Kubernetes:

- requests.memory ảnh hưởng scheduling và QoS.
- limits.memory giới hạn memory của container.
- Container có thể bị OOMKilled nếu vượt giới hạn hoặc node gặp memory pressure theo chính sách.
- Pod có thể bị evict khi node thiếu tài nguyên, ngay cả khi container chưa vượt limit riêng.

### 12.3. PID và I/O

Cgroup có thể giới hạn số process/thread và theo dõi I/O. PID limit quá thấp có thể khiến JVM hoặc ứng dụng không tạo được thread. Disk I/O policy có thể ảnh hưởng workload đọc/ghi nặng, nhưng mức hỗ trợ phụ thuộc kernel và runtime.

Theo dõi cả container lẫn node: CPU throttling, memory working set, OOM events, PID usage, filesystem usage và block I/O.

## 13. Bảo mật image và container runtime

Container chia sẻ kernel nên cấu hình bảo mật có ý nghĩa trực tiếp tới ranh giới host.

Các nguyên tắc:

- Chạy process bằng user không phải root khi có thể.
- Không dùng --privileged trừ khi có yêu cầu rõ và được kiểm soát.
- Giảm Linux capabilities xuống mức cần thiết.
- Dùng seccomp profile phù hợp để hạn chế syscall.
- Dùng AppArmor hoặc SELinux khi nền tảng hỗ trợ.
- Mount filesystem read-only nếu ứng dụng cho phép.
- Giới hạn quyền ghi và mount host path.
- Không mount Docker socket hoặc runtime socket vào container ứng dụng.
- Dùng user namespace hoặc rootless container khi phù hợp.
- Giới hạn network ingress/egress.
- Cập nhật host kernel, runtime và image base.

### 13.1. Chạy non-root và read-only

Dockerfile có thể đặt user không phải root:

~~~dockerfile
USER 10001:10001
~~~

Docker run có thể áp dụng một số giới hạn:

~~~bash
docker run --read-only \
  --cap-drop ALL \
  --security-opt no-new-privileges \
  --tmpfs /tmp:rw,noexec,nosuid,size=64m \
  orders-api:2.4.1
~~~

Cấu hình chỉ phù hợp nếu ứng dụng không cần ghi vào root filesystem và không cần capability đặc biệt. Nếu ứng dụng cần thư mục tạm, mount tmpfs hoặc volume riêng với quyền tối thiểu.

### 13.2. Image supply chain

Image là artifact cần được bảo vệ từ source tới production:

1. Build từ base image được phê duyệt.
2. Pin dependency và base image theo version/digest.
3. Quét lỗ hổng ở OS package và application dependency.
4. Tạo Software Bill of Materials (SBOM).
5. Ký image hoặc artifact theo quy trình tổ chức.
6. Verify chữ ký và provenance trước deploy.
7. Quản lý quyền push/pull theo repository.
8. Retention và xóa image lỗi thời theo policy.
9. Theo dõi base image patch và rebuild định kỳ.

Quét image không bảo đảm không có lỗ hổng; scanner chỉ phát hiện những vấn đề có trong dữ liệu và rule hiện có. Cần kết hợp patch management, runtime controls và giám sát.

### 13.3. Secret trong container

Không đưa secret vào Dockerfile, image layer, source control hoặc environment được lưu lâu dài nếu có lựa chọn an toàn hơn. Ưu tiên secret manager và workload identity để cấp credential ngắn hạn. Giới hạn quyền đọc secret theo service account và thu hồi khi workload bị xóa.

Environment variable tiện sử dụng nhưng có thể bị lộ qua process inspection, crash dump hoặc log. Cần hiểu threat model và cơ chế secret injection của nền tảng.

## 14. Logging và quan sát container

Container thường được thiết kế để ghi log ứng dụng ra stdout/stderr. Runtime hoặc nền tảng có thể thu thập các stream này và chuyển tới log backend.

Cần theo dõi:

- Container state và restart count.
- Exit code và termination reason.
- CPU, memory, throttling và OOM event.
- Network traffic, errors và connection.
- Writable layer và ephemeral storage.
- Image digest, runtime version và node.
- Startup/readiness duration.
- Application logs và metrics.

Trong Docker, các lệnh như docker logs, docker inspect và docker stats giúp kiểm tra một số thông tin tại host. Trong Kubernetes, dùng kubectl describe pod, kubectl logs, kubectl get events và metrics backend phù hợp.

Không chỉ quan sát Pod state. Một Pod có thể Running nhưng ứng dụng không ready; một container có thể restart nhiều lần; node có thể thiếu disk hoặc memory. Liên kết event runtime với metric ứng dụng giúp tìm nguyên nhân nhanh hơn.

### 14.1. Log rotation và dung lượng

Nếu log không được rotate hoặc giới hạn, container có thể làm đầy disk node. Cấu hình log driver/runtime và log collector để có giới hạn dung lượng, retention và backpressure phù hợp.

Ứng dụng nên tránh ghi log lặp tốc độ cao khi lỗi dependency kéo dài. Dùng rate limiting, sampling hoặc giảm mức log khi phù hợp; vẫn giữ đủ thông tin để điều tra.

## 15. Container trong VM, Kubernetes và serverless

### 15.1. Container trên VM

Một VM có thể chạy Docker Engine hoặc containerd để chạy nhiều container. Người vận hành chịu trách nhiệm quản lý OS, kernel, runtime, image pull, network, volume và restart policy.

Mô hình này phù hợp khi cần kiểm soát host hoặc chạy một số lượng workload vừa phải. Khi quy mô lớn, việc tự quản lý scheduling, service discovery và capacity trở nên phức tạp.

### 15.2. Container trên Kubernetes

Kubernetes điều phối container thông qua Pod và các controller. Pod là đơn vị scheduling; container trong cùng Pod chia sẻ một số tài nguyên và network context. Deployment, StatefulSet, DaemonSet và Job mô tả các kiểu workload khác nhau.

Kubernetes quản lý desired state: nếu Pod bị mất hoặc container cần restart theo policy, controller/kubelet cố gắng đưa hệ thống về trạng thái mong muốn. Tuy nhiên, ứng dụng vẫn cần readiness, graceful shutdown, persistent storage và thiết kế chịu lỗi.

### 15.3. Container trong serverless

Một số nền tảng serverless nhận container image hoặc đóng gói ứng dụng theo image-compatible format, sau đó quản lý host và runtime thay người dùng. Người dùng vẫn cần quan tâm image size, startup time, memory/CPU request, concurrency, health và graceful shutdown theo contract của dịch vụ.

Không phải serverless nào cũng chạy một OCI image không giới hạn. Nền tảng có thể yêu cầu port, entrypoint, architecture, image registry hoặc filesystem layout cụ thể.

## 16. Debug container lifecycle

Một số lệnh chẩn đoán Docker:

~~~bash
# Liệt kê container và trạng thái
docker ps -a

# Xem cấu hình và trạng thái chi tiết
docker inspect orders-api-test

# Xem log
docker logs --tail 200 orders-api-test

# Xem tài nguyên đang dùng
docker stats orders-api-test

# Xem process trong container
docker top orders-api-test

# Xem image và digest
docker image inspect orders-api:2.4.1
~~~

Trong Kubernetes:

~~~bash
# Trạng thái Pod và node
kubectl get pods -o wide
kubectl get nodes

# Chi tiết Pod, event và probe
kubectl describe pod <pod-name>

# Log container hiện tại
kubectl logs <pod-name> -c <container-name>

# Log lần chạy trước nếu container đã restart
kubectl logs <pod-name> -c <container-name> --previous

# Kiểm tra event gần đây
kubectl get events --sort-by=.lastTimestamp
~~~

Một số nguyên nhân container không khởi động:

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra |
|---|---|---|
| ImagePullBackOff | Registry auth, tag/digest sai hoặc network | Kiểm tra image reference, quyền pull và registry |
| Exec format error | Binary hoặc image sai kiến trúc | Kiểm tra platform và manifest list |
| CrashLoopBackOff | Process thoát liên tục hoặc probe cấu hình sai | Xem exit code, logs, startup và liveness |
| OOMKilled | Vượt memory limit hoặc node pressure | So sánh RSS, heap, cgroup và memory events |
| Container running nhưng không nhận traffic | Readiness, port, network policy hoặc service routing | Kiểm tra probe, listener, endpoint và route |
| Filesystem đầy | Log hoặc writable layer tăng | Kiểm tra ephemeral storage, log rotation và volume |
| Dừng không sạch | PID 1 không forward signal hoặc app shutdown quá lâu | Kiểm tra ENTRYPOINT, signal và grace period |

## 17. Quy trình phát hành image an toàn

Một pipeline phát hành image nên có các bước:

1. Checkout source từ revision đã xác định.
2. Cài dependency từ nguồn đáng tin cậy.
3. Chạy test và build artifact.
4. Build image theo Dockerfile đã review.
5. Quét dependency và image.
6. Tạo SBOM và provenance nếu pipeline hỗ trợ.
7. Gắn tag phát hành và lấy digest.
8. Push image lên registry.
9. Ký image và kiểm tra chữ ký theo policy.
10. Deploy bằng digest hoặc artifact đã xác minh.
11. Theo dõi startup, readiness, error và resource.
12. Rollback về digest trước nếu release không đạt SLO.

Tag giúp nhận diện release, còn digest xác định nội dung. Lưu digest trong deployment record để có thể tái lập và điều tra chính xác image nào đã chạy.

### 17.1. Rollout và rollback

Với Kubernetes Deployment, rolling update có thể thay Pod theo từng đợt. Cần cấu hình maxSurge, maxUnavailable, readiness và PodDisruptionBudget phù hợp để tránh mất quá nhiều capacity cùng lúc.

Rollback cần image digest trước đó vẫn còn trong registry và tương thích với dữ liệu/schema hiện tại. Nếu release có migration không tương thích ngược, rollback image có thể chưa đủ; cần quy trình migration an toàn.

## 18. Lỗi thường gặp và cách tránh

**Nhầm image với container:** image là artifact bất biến, container là instance runtime. Dữ liệu ghi trong container không tự cập nhật image.

**Dùng tag mutable trong production:** tag có thể trỏ sang nội dung khác. Ghi nhận và pin digest đã kiểm thử.

**Đưa compiler và build tool vào runtime image:** tăng kích thước và bề mặt tấn công. Dùng multi-stage build khi phù hợp.

**Chạy container bằng root và privileged:** tăng khả năng tác động tới host. Dùng non-root, drop capabilities và security profile tối thiểu.

**Lưu state trong writable layer:** dữ liệu có thể mất khi container bị recreate. Dùng volume hoặc dịch vụ lưu trữ bền vững.

**Dùng shell form không xử lý signal:** ứng dụng có thể không nhận SIGTERM đúng cách. Dùng exec form hoặc wrapper có exec.

**Không tính PID 1:** child process có thể không được thu hồi. Dùng process model đúng hoặc init nhỏ khi cần.

**Dùng liveness để kiểm tra database:** dependency tạm thời lỗi có thể làm toàn bộ container restart. Tách readiness và liveness.

**Không giới hạn CPU/memory:** một container có thể ảnh hưởng workload khác trên cùng host. Đặt request/limit và quan sát throttling/OOM.

**Image quá lớn:** tăng pull time và scale-out latency. Tối ưu layer, multi-stage và base image.

**Không quản lý log rotation:** log có thể làm đầy disk node. Cấu hình driver và retention.

**Để secret trong image hoặc build log:** secret có thể tồn tại trong layer và artifact. Dùng secret manager hoặc BuildKit secret mount.

**Coi PDB hoặc restart policy là bảo đảm không gián đoạn:** orchestrator chỉ hỗ trợ khôi phục theo semantics của nó. Ứng dụng vẫn cần graceful shutdown, retry và state bền vững.

## 19. Checklist container image, runtime và lifecycle

- [ ] Image được build từ base image đã phê duyệt và có version/digest rõ ràng.
- [ ] Dockerfile dùng multi-stage khi phù hợp và chỉ giữ runtime dependency cần thiết.
- [ ] Build context được lọc bằng .dockerignore.
- [ ] Không đưa credential hoặc secret vào image, ARG, ENV hay log build.
- [ ] Image có manifest cho kiến trúc node được phép chạy.
- [ ] Registry có xác thực, phân quyền và retention.
- [ ] Image được scan, có SBOM/provenance khi quy trình yêu cầu và được verify trước deploy.
- [ ] Container chạy non-root và không dùng privileged không cần thiết.
- [ ] Capabilities, seccomp, AppArmor/SELinux và filesystem được giới hạn phù hợp.
- [ ] Runtime và kernel được cập nhật, quản lý phiên bản.
- [ ] Process chính nhận signal đúng; graceful shutdown có timeout.
- [ ] Readiness, liveness và startup probe có semantics riêng.
- [ ] Dữ liệu cần giữ được lưu trên volume hoặc dịch vụ bền vững.
- [ ] CPU, memory, PID và ephemeral storage có giới hạn phù hợp.
- [ ] Network, DNS, port và policy được kiểm soát.
- [ ] Log rotation, metrics và container events được thu thập.
- [ ] Deployment dùng digest và có phương án rollback.
- [ ] Đã kiểm thử pull failure, crash, OOM, restart và termination.

Container image mô tả artifact cần chạy; registry phân phối artifact; runtime tạo và quản lý process trong môi trường cô lập. Khi hiểu rõ layer, digest, CRI/OCI runtime và lifecycle, đội ngũ có thể xây dựng image nhỏ, tái lập và an toàn hơn. Ứng dụng cần xử lý signal, health check, storage và giới hạn tài nguyên đúng cách để hoạt động ổn định khi container bị restart, thay thế hoặc di chuyển giữa các node cloud.
