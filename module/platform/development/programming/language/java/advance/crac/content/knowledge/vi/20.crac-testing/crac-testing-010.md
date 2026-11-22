# Kiểm thử ma trận JDK, kernel, CPU và container trong CI

Checkpoint image của CRaC (Coordinated Restore at Checkpoint) lưu trạng thái của một tiến trình Java đang chạy. Khả năng restore phụ thuộc vào runtime đã tạo image, checkpoint engine, hệ điều hành, kernel, CPU, native library và cách container được khởi chạy. Vì vậy, kiểm thử trên một máy CI duy nhất không đủ để kết luận image có thể restore trên mọi node production.

Một pipeline CRaC cần kiểm tra các tổ hợp môi trường có ý nghĩa, ghi lại chính xác cấu hình nguồn tạo checkpoint và cấu hình đích restore, rồi dùng kết quả đó làm điều kiện phát hành. Ma trận phải phản ánh môi trường thực tế mà workload sẽ chạy: JDK build nào, kernel nào, CPU architecture/features nào, container image/runtime nào và engine nào.

Bài này trình bày cách xây dựng ma trận CI có thể mở rộng, phân biệt những gì container kiểm soát với những gì phụ thuộc host, tổ chức kiểm thử theo source/target profile, thu thập bằng chứng và đặt release gate dựa trên kết quả restore thật.

## 1. Vì sao cần kiểm thử ma trận?

Một test CRaC thành công trên máy phát triển chỉ chứng minh rằng một tổ hợp cụ thể đã hoạt động. Nó không chứng minh các tổ hợp khác cũng tương thích.

Ví dụ, cùng một ứng dụng và container image có thể chạy trên:

- JDK CRaC build A và JDK CRaC build B.
- Kernel 6.x trên node pool A và kernel 6.y trên node pool B.
- CPU amd64 có AVX2 và CPU amd64 không có AVX2.
- CPU amd64 và arm64.
- Container runtime có phiên bản khác nhau.
- Filesystem ext4, XFS hoặc overlay filesystem.
- CRIU hoặc một checkpoint engine khác được vendor cung cấp.

Những khác biệt này có thể ảnh hưởng tới cách JVM lưu trạng thái, cách engine khôi phục process, native code, memory mapping, file descriptor, namespace và quyền truy cập. Một image có thể tạo thành công nhưng restore thất bại trên target. Cũng có thể process restore thành công nhưng callback afterRestore không kết nối lại được database hoặc ứng dụng chưa đạt readiness.

Kiểm thử ma trận giúp trả lời ba câu hỏi riêng:

1. **Build/runtime có tạo được checkpoint không?** JDK và engine nguồn có hỗ trợ workload và host nguồn không?
2. **Checkpoint có restore được trên target không?** Engine có khôi phục được process trong đúng tổ hợp JDK, kernel, CPU và container không?
3. **Ứng dụng có hoạt động đúng sau restore không?** Resource callback, external reconciliation và functional smoke test có thành công không?

Một phép thử chỉ kiểm tra callback không trả lời đầy đủ ba câu hỏi này. Cần kết hợp test nhanh trong pull request với restore integration test trên runner thực tế.

## 2. Ma trận phải mô tả source và target

Checkpoint được tạo ở một môi trường nguồn, sau đó được restore ở một môi trường đích. Khả năng tương thích là quan hệ **source → target**, không chỉ là thuộc tính của một host.

Ví dụ:

| Source profile | Target profile | Điều cần xác nhận |
|---|---|---|
| JDK A, kernel K1, CPU amd64, engine E1 | Cùng profile | Baseline restore |
| JDK A, kernel K1 | JDK A, kernel K2 | Khác kernel |
| JDK A, CPU amd64 | JDK A, CPU arm64 | Khác architecture; thường phải kiểm tra hỗ trợ riêng |
| JDK A, engine E1 | JDK B, engine E1 | Khác JDK build/vendor |
| Container digest X trên node pool A | Cùng digest X trên node pool B | Khác host kernel/CPU/runtime |
| Container digest X | Container digest Y | Khác userland, JDK hoặc native libraries |

Kết quả của A → B không tự chứng minh B → A. Một số vendor chỉ hỗ trợ một chiều hoặc yêu cầu source và target dùng đúng cùng build. Hãy ghi từng cặp theo hướng đã thử và đối chiếu với ma trận hỗ trợ của vendor.

~~~mermaid
flowchart LR
    S["Source profile<br/>JDK / kernel / CPU / container"] --> C["Create checkpoint<br/>artifact + manifest"]
    C --> T1["Target profile A"]
    C --> T2["Target profile B"]
    C --> T3["Target profile C"]
    T1 --> R1["Restore + app tests"]
    T2 --> R2["Restore + app tests"]
    T3 --> R3["Restore + app tests"]
    R1 --> E["Evidence and status"]
    R2 --> E
    R3 --> E
~~~

Nếu production chỉ tạo checkpoint trên một loại node nhưng restore trên nhiều node pool, cần thử source đó với tất cả target class bắt buộc. Nếu mỗi architecture hoặc runtime class tự tạo image riêng, cần kiểm tra từng source image với các target được phép sử dụng nó.

### 2.1 Không gộp vendor support với đã kiểm thử

Cần giữ riêng ba trạng thái:

- Vendor công bố hỗ trợ tổ hợp đó.
- Checkpoint engine đã restore thành công trong CI.
- Ứng dụng đã vượt qua kiểm tra sau restore.

Một tổ hợp có thể nằm trong tài liệu vendor nhưng chưa được kiểm thử với native library của ứng dụng. Ngược lại, một lần thử thành công không mở rộng phạm vi hỗ trợ chính thức của vendor.

Ma trận nên có cột riêng cho vendor support, process restore, application readiness và evidence.

## 3. Bốn chiều chính của ma trận

### 3.1 JDK vendor, version và build

Không chỉ ghi major version như Java 21. Hãy lưu đầy đủ:

- Vendor và distribution.
- Java version đầy đủ.
- Update/build identifier.
- CRaC runtime/API build.
- Architecture của JDK.
- JVM implementation và GC nếu có yêu cầu.
- JVM flags liên quan đến heap, GC, memory layout hoặc checkpoint.
- Các agent và native module được nạp.

Hai JDK cùng major version có thể có CRaC integration, patch, native library hoặc implementation khác nhau. Vì vậy, test matrix cần dùng đúng JDK build sẽ chạy production.

Trong CI, JDK có thể được cài sẵn trên runner hoặc được provision từ một artifact repository nội bộ. Với CRaC, không nên mặc định một action cài JDK phổ thông là đã cung cấp checkpoint engine thực. Cần xác minh runtime cụ thể có CRaC support theo tài liệu vendor.

Lưu metadata bằng:

~~~bash
java -version
~~~

Có thể thu thập thêm input arguments và system properties không nhạy cảm từ RuntimeMXBean. Không ghi environment variable chứa secret vào report.

### 3.2 Kernel và OS

Container chia sẻ kernel với host theo mô hình container thông thường. Việc dùng cùng container image trên hai node không làm kernel của hai node giống nhau.

Các trường cần ghi nhận:

- OS distribution và release.
- Kernel release/build.
- Kernel configuration hoặc sysctl quan trọng.
- cgroup version.
- Namespace mode.
- VMA và giới hạn process.
- File descriptor limits.
- Capability và security policy.
- SELinux/AppArmor hoặc seccomp profile.
- Các quyền mà checkpoint engine yêu cầu.

Ví dụ thu thập metadata trên Linux:

~~~bash
uname -a
cat /etc/os-release
cat /proc/sys/kernel/osrelease
cat /proc/sys/vm/max_map_count
ulimit -n
~~~

Các giá trị cụ thể cần so sánh tùy engine và workload. Không nên tạo một danh sách sysctl tùy ý rồi coi tất cả đều là điều kiện tương thích. Hãy lấy yêu cầu từ vendor, engine và các failure đã quan sát.

Kernel test cần chạy trên host hoặc VM có kernel thực sự tương ứng. Chạy container với một base image khác không thay kernel host.

### 3.3 CPU architecture và features

Ghi nhận:

- Architecture như amd64/x86_64 hoặc arm64/aarch64.
- CPU model hoặc CPU family khi có liên quan.
- Instruction set extensions và feature flags.
- Virtualization hoặc CPU feature masking nếu dùng VM.
- Native library ABI.
- Runtime CPU constraints của node pool.

Trên Linux có thể thu thập:

~~~bash
uname -m
lscpu
grep -m1 '^flags' /proc/cpuinfo
~~~

Không chỉ ghi architecture. Hai host amd64 có thể expose tập CPU features khác nhau. Native library hoặc JIT-generated code có thể phụ thuộc vào feature cụ thể.

Nếu production dùng node pool có CPU generation khác nhau, hãy test trên các profile đại diện. Nếu checkpoint image phụ thuộc CPU feature hoặc vendor quy định target phải có feature tương đương, CI cần enforce điều kiện đó trước restore.

QEMU hoặc emulation có thể hữu ích cho một số kiểm thử build và application logic, nhưng không nên coi một lần test emulation là bằng chứng đầy đủ cho process checkpoint/restore trên CPU vật lý hoặc VM target. Restore test quan trọng cần chạy trên architecture và CPU profile thực tế được hỗ trợ.

### 3.4 Container image và container runtime

Cần phân biệt hai lớp.

**Container image / userland**

- Base image và distribution.
- JDK build.
- Native libraries.
- CA certificates và timezone data.
- Application JAR và dependencies.
- User, entrypoint và filesystem layout.
- Container image digest.

**Container runtime / host integration**

- Docker/containerd/CRI-O version.
- OCI runtime như runc hoặc runtime class khác.
- Namespace, mount và cgroup behavior.
- Seccomp profile và capabilities.
- Volume/mount options.
- Host kernel và CPU.
- Kubernetes version, node pool và RuntimeClass nếu có.

Cùng một container image digest có thể chạy trên host có kernel hoặc CPU khác. Ngược lại, cùng kernel vẫn có thể gặp lỗi nếu userland hoặc native libraries khác.

Dùng digest bất biến thay cho tag mutable để liên kết checkpoint với container image đã tạo nó.

## 4. Không tạo Cartesian product một cách máy móc

Nếu có 3 JDK builds, 4 kernel profiles, 3 CPU profiles, 2 engines và 3 container profiles, một Cartesian product đầy đủ có thể tạo ra hàng trăm tổ hợp. Nhiều tổ hợp có thể không được vendor hỗ trợ hoặc không được dùng trong production.

Không cần test tất cả tổ hợp lý thuyết. Hãy xây ma trận từ target profiles thực tế và chọn các source-target pair có ý nghĩa.

### 4.1 Bắt đầu từ môi trường triển khai

Liệt kê node pool và runtime class đang dùng hoặc dự kiến dùng:

- Production amd64 node pool.
- Production arm64 node pool nếu có.
- Disaster recovery node pool.
- Staging.
- CI integration runner.
- Các node pool có kernel hoặc container runtime khác biệt.

Mỗi profile cần có ID ổn định và metadata chi tiết. Không tạo profile chỉ để bao phủ một tổ hợp không bao giờ triển khai.

### 4.2 Dùng include/exclude thay cho mọi tổ hợp

Có thể định nghĩa các cặp được phép:

| Source | Target | Lý do |
|---|---|---|
| src-amd64-jdkA-E1 | prod-amd64-poolA | Deployment bắt buộc |
| src-amd64-jdkA-E1 | prod-amd64-poolB | Kernel khác, cùng architecture |
| src-arm64-jdkA-E1 | prod-arm64-poolA | Architecture riêng |
| src-amd64-jdkB-E1 | prod-amd64-poolA | Đánh giá JDK upgrade |
| src-amd64-jdkA-E1 | staging-amd64 | Pre-release validation |

Các cặp không được hỗ trợ nên được loại khỏi matrix với lý do rõ ràng. Đừng dùng exclude để che một test đang thất bại; chỉ loại tổ hợp đã được xác định là không áp dụng hoặc không hỗ trợ theo policy.

### 4.3 Pairwise và risk-based selection

Pairwise testing có thể giảm số tổ hợp cho các chiều ít tương tác. Tuy nhiên, nó không đảm bảo mọi tương tác nhiều chiều đều được phát hiện.

Ví dụ, lỗi chỉ xuất hiện khi JDK build B kết hợp với kernel K2 và native library N3 sẽ không nhất thiết xuất hiện trong các cặp riêng lẻ.

Ưu tiên test end-to-end chính xác cho:

- JDK/CRaC build thay đổi.
- Engine thay đổi.
- CPU architecture hoặc feature baseline thay đổi.
- Kernel thay đổi ngoài phạm vi đã kiểm chứng.
- Native library hoặc JNI thay đổi.
- Container runtime/security profile thay đổi.
- Filesystem hoặc mount thay đổi có ảnh hưởng mapping.
- Target node pool production mới.

Pairwise phù hợp để mở rộng coverage cho các chiều rủi ro thấp hơn, không thay thế test cho production profiles bắt buộc.

## 5. Các tầng kiểm thử trong CI

Một pipeline tốt không cần chạy restore matrix đầy đủ ở mọi commit. Có thể chia thành các tầng với thời gian và mức độ tin cậy khác nhau.

| Tầng | Khi chạy | Nội dung | Điều nó chứng minh |
|---|---|---|---|
| Unit tests | Mỗi pull request | Deadline, state machine, config và Resource logic | Logic ứng dụng |
| Callback/simulation tests | Mỗi pull request | beforeCheckpoint/afterRestore với simulation hoặc test harness | Hành vi callback |
| JDK build tests | Pull request hoặc nightly | Compile và chạy smoke test trên các JDK được hỗ trợ | Tương thích Java/runtime ở mức cơ bản |
| Real checkpoint/restore | Nightly hoặc release | Tạo image và restore bằng engine thật | Process checkpoint/restore trên profile cụ thể |
| Source-target matrix | Nightly/release | Restore cùng artifact trên các target profiles | Tương thích theo hướng source → target |
| Application integration | Release gate | DB, TLS, broker, filesystem, readiness và workload | Ứng dụng hoạt động sau restore |
| Performance/capacity | Nightly/release | Restore time, RSS/PSS, first-request latency | Mục tiêu vận hành |

Simulation engine có thể chạy callback trong cùng tiến trình và hữu ích để kiểm tra logic cleanup/reopen. Nó không chứng minh kernel đã lưu và khôi phục process state, native memory, VMA hoặc file descriptor đúng cách.

Real checkpoint test phải dùng đúng JDK/engine và host class được dự định triển khai.

### 5.1 Pull request tier

Ở mỗi pull request, nên chạy nhanh:

- Compile và unit tests trên JDK chính.
- Unit tests trên các JDK major versions cần hỗ trợ.
- Test callback logic.
- Kiểm tra resource registration.
- Kiểm tra timeout và failure handling.
- Kiểm tra manifest/profile schema.
- Kiểm tra build container image.

Nếu runner không có checkpoint engine thực hoặc không đủ quyền, không nên gọi kết quả đó là checkpoint restore pass. Ghi rõ đây là simulation hoặc compile test.

### 5.2 Nightly tier

Nightly có thể tạo checkpoint từ một source profile chuẩn, sau đó restore trên các target profiles đại diện. Chạy cả trường hợp restore lặp và nhiều instance nếu production dùng cùng một image để scale.

Nightly phù hợp để phát hiện drift của runner, kernel update, container runtime update hoặc thay đổi external dependency mà pull request không bao phủ.

### 5.3 Release tier

Trước khi publish checkpoint artifact:

- Chạy tất cả source-target pair bắt buộc cho production.
- Chạy callback và application integration.
- Xác minh external state sau restore.
- Kiểm tra readiness.
- Thu thập performance metrics.
- Lưu artifact checksum và environment metadata.
- Chỉ phát hành nếu các profile bắt buộc đạt release policy.

Không đánh dấu một release VERIFIED chỉ vì lệnh restore trả exit code 0. Ứng dụng phải vượt qua các kiểm tra đã định nghĩa.

## 6. CI runner phải đại diện cho môi trường thật

JDK có thể cài đặt trong job, nhưng kernel và CPU thuộc host runner. Vì vậy, ma trận JDK/kernel/CPU/container thường cần nhiều runner class.

### 6.1 Hosted runner và self-hosted runner

Hosted runner tiện cho compile, unit test và container build. Tuy nhiên, phiên bản kernel, CPU model, virtualization và quyền hệ thống có thể do nhà cung cấp CI quản lý và thay đổi theo thời gian.

Self-hosted runner phù hợp khi cần:

- Kernel cụ thể.
- CPU architecture hoặc feature baseline cụ thể.
- Quyền/capability mà checkpoint engine yêu cầu.
- Container runtime cụ thể.
- Filesystem/mount profile cụ thể.
- Cấu hình host ổn định và có thể audit.

Runner labels nên phản ánh profile đã chuẩn hóa, ví dụ:

~~~text
self-hosted
linux
amd64
kernel-6-8
cpu-avx2
crac-engine-e1
~~~

Tên label là ví dụ. Cần đồng bộ label với metadata thật của runner. Một label kernel-6-8 sẽ mất ý nghĩa nếu host được nâng kernel nhưng label không được cập nhật.

### 6.2 Runner cần được quản lý như một phần của matrix

Đối với self-hosted runner:

- Dùng runner pool riêng cho checkpoint tests.
- Không chạy job không tin cậy trên runner có quyền checkpoint.
- Dọn workspace và checkpoint files sau job.
- Hạn chế quyền truy cập daemon/container runtime.
- Ghi nhận runner image và host fingerprint.
- Cập nhật label khi kernel, CPU hoặc runtime thay đổi.
- Có lịch bảo trì và kiểm tra drift.
- Tránh dùng một host đồng thời cho nhiều test có thể xung đột process state.

Checkpoint test có thể cần quyền đặc biệt. Không cấp quyền privileged cho mọi job CI nếu chỉ một job cần nó.

### 6.3 Job isolation

Dùng ephemeral VM hoặc runner được tái tạo theo job nếu có thể. Nếu dùng runner lâu dài, phải đảm bảo một test không để lại:

- Process cũ.
- Mount hoặc namespace.
- Checkpoint files.
- Network listener.
- File descriptor hoặc shared resource.
- Container cũ.
- Secret hoặc credential.
- Sysctl tạm đã thay đổi.

Một test restore thất bại không nên làm bẩn môi trường cho test kế tiếp.

## 7. Container không thay thế host matrix

Container image có thể pin JDK và native libraries, nhưng không pin được toàn bộ kernel và CPU host.

### 7.1 Cùng image, nhiều host

Đây là một phép thử hữu ích: tạo checkpoint từ container image digest cố định rồi restore trên các node pool khác nhau.

Như vậy, có thể kiểm tra ảnh hưởng của:

- Kernel release.
- CPU features.
- Container runtime.
- cgroup mode.
- Seccomp/capability.
- Filesystem và mount.

Nếu chỉ chạy nhiều container trên cùng một host, test không bao phủ khác biệt kernel/CPU giữa các node.

### 7.2 Khác container image

Nếu thay base image hoặc native libraries, cần xem đây là một dimension riêng. Checkpoint được tạo trong container image A không nên tự động restore trong image B chỉ vì JAR giống nhau.

Ghi lại:

- OCI image digest.
- Base distribution.
- JDK build.
- Native library versions.
- Runtime user và permission.
- Entrypoint và JVM arguments.
- Mount layout.

Nếu vendor cho phép một số khác biệt userland, hãy ghi đúng phạm vi đó và thử restore trên target tương ứng.

### 7.3 Container runtime và OCI runtime

Docker, containerd, CRI-O hoặc OCI runtime có thể có phiên bản và cấu hình khác nhau. Namespace, mount, cgroup và security profile có thể ảnh hưởng tới process checkpoint.

Đừng chỉ ghi Dockerfile hoặc image digest rồi coi container environment đã được mô tả đầy đủ. Host runtime cần được thu thập riêng.

## 8. Cấu trúc workflow CI tham khảo

Ví dụ dưới đây là pseudocode trung lập về CI provider. Nó minh họa cách chia source job và target job; tên runner labels, JDK provisioning, lệnh checkpoint/restore và artifact transfer phải được thay bằng tooling thật của tổ chức và vendor.

### 8.1 Định nghĩa source profiles

Source profile mô tả runner sẽ khởi động ứng dụng và tạo checkpoint.

~~~yaml
sourceProfiles:
  - id: linux-amd64-jdkA-engineE1
    runner: crac-linux-amd64-kernel-k1-cpu-avx2
    jdkProfile: jdkA
    containerDigest: sha256:source-image-digest

  - id: linux-arm64-jdkA-engineE1
    runner: crac-linux-arm64-kernel-k2
    jdkProfile: jdkA-arm64
    containerDigest: sha256:arm64-image-digest
~~~

Pipeline đọc từng profile, chọn runner tương ứng, cài hoặc xác minh JDK, khởi động container đúng digest, warm-up ứng dụng và tạo checkpoint. Mỗi source job lưu artifact riêng cùng source fingerprint.

### 8.2 Định nghĩa restore pairs

Không tạo mọi tổ hợp tự động nếu chỉ một số cặp được phép.

~~~yaml
restorePairs:
  - source: linux-amd64-jdkA-engineE1
    target: prod-amd64-poolA
    required: true

  - source: linux-amd64-jdkA-engineE1
    target: prod-amd64-poolB
    required: true

  - source: linux-arm64-jdkA-engineE1
    target: prod-arm64-poolA
    required: true
~~~

Mỗi target profile trỏ tới runner pool thật. Target job tải đúng artifact theo source ID, kiểm tra checksum và metadata, rồi chạy restore trên target runner.

### 8.3 Ví dụ các bước trong job

~~~yaml
steps:
  - name: Provision CRaC JDK
    run: ./ci/install-crac-jdk.sh PROFILE_ID

  - name: Record source or target profile
    run: ./ci/collect-environment.sh > environment-profile.json

  - name: Verify runner fingerprint
    run: ./ci/verify-runner-profile.sh environment-profile.json PROFILE_ID

  - name: Start and warm up application
    run: ./ci/start-and-warmup.sh

  - name: Create checkpoint
    run: ./ci/create-checkpoint.sh

  - name: Verify artifact
    run: ./ci/verify-checkpoint-artifact.sh

  - name: Restore checkpoint
    run: ./ci/restore-checkpoint.sh

  - name: Run application smoke tests
    run: ./ci/post-restore-smoke.sh

  - name: Publish evidence
    run: ./ci/write-matrix-result.sh
~~~

Các script là thành phần do repository cung cấp, không phải lệnh chuẩn của CRaC. Lệnh thực tế phụ thuộc JDK vendor và checkpoint engine. Bước publish evidence nên chạy cả khi job thất bại để lưu log, nhưng không được biến test fail thành pass.

### 8.4 Giới hạn concurrency

Nếu checkpoint engine hoặc runner không hỗ trợ nhiều restore đồng thời trên cùng host, hãy giới hạn concurrency theo runner hoặc profile.

Không dùng chung một checkpoint directory cho nhiều job. Mỗi job cần workspace, process ID, output directory và checkpoint ID riêng.

## 9. Tách lệnh kiểm thử khỏi policy matrix

Không nên hard-code toàn bộ logic trong YAML workflow. Tách thành script hoặc tool nhỏ có interface ổn định:

~~~text
ci/
  collect-environment.sh
  install-crac-jdk.sh
  start-and-warmup.sh
  create-checkpoint.sh
  package-checkpoint.sh
  verify-checkpoint-manifest.sh
  restore-checkpoint.sh
  post-restore-smoke.sh
  write-matrix-result.sh
  profiles/
    source-profiles.yml
    restore-pairs.yml
~~~

Workflow điều phối profile. Script thực hiện thao tác. Manifest ghi bằng chứng.

Lợi ích:

- Có thể chạy local hoặc trên runner riêng.
- Dễ thay engine command mà không sửa toàn bộ matrix.
- Có thể test parser và policy độc lập.
- Kết quả dễ chuẩn hóa.
- Profile được review bằng Git.
- Có thể dùng cùng script trong nightly và release pipeline.

Không để script tự chọn target từ thông tin thiếu hoặc đoán profile. Nếu metadata không khớp runner label, fail fast và ghi BLOCKED.

## 10. Thu thập fingerprint nguồn và đích

Mỗi lần tạo và restore cần thu thập metadata từ host/process thực tế, không lấy metadata từ một file cấu hình tĩnh rồi giả định host đang đúng.

Một profile nên có các nhóm:

~~~json
{
  "profileId": "linux-amd64-jdkA-kernelK1-engineE1",
  "os": {
    "name": "linux",
    "distribution": "example-linux",
    "kernel": "6.x.y"
  },
  "cpu": {
    "architecture": "amd64",
    "model": "example-cpu",
    "features": ["sse4_2", "avx2"]
  },
  "jdk": {
    "vendor": "example-vendor",
    "version": "21.x",
    "build": "example-crac-build"
  },
  "engine": {
    "name": "example-engine",
    "version": "example-engine-version"
  },
  "container": {
    "imageDigest": "sha256:example-image-digest",
    "runtime": "example-runtime",
    "runtimeVersion": "example-runtime-version"
  }
}
~~~

Các giá trị chỉ minh họa cấu trúc. Manifest thật cần dùng dữ liệu thu thập từ runner và runtime.

### 10.1 Fingerprint không thay thế metadata đầy đủ

Có thể tạo hash từ các trường đã chuẩn hóa để so sánh nhanh profile. Nhưng cần lưu cả metadata gốc để điều tra khi fingerprint khác.

Không đưa secret, token, private key hoặc nội dung environment nhạy cảm vào fingerprint report. Chỉ thu thập biến môi trường được allowlist.

### 10.2 So sánh source-target có chính sách

Không phải mọi trường phải giống tuyệt đối. Có thể có những khác biệt được vendor hỗ trợ, ví dụ một số patch kernel hoặc host CPU trong cùng phạm vi. Policy cần chỉ rõ:

- Trường nào phải trùng khớp.
- Trường nào được phép khác trong range.
- Trường nào chỉ cần ghi nhận.
- Trường nào bắt buộc test lại khi thay đổi.
- Trường nào khiến target unsupported.

Không dùng một phép so sánh chuỗi đơn giản để quyết định tương thích nếu vendor có quy tắc phức tạp hơn.

## 11. Quản lý trạng thái test và release gate

Mỗi source-target pair nên có kết quả độc lập.

| Status | Ý nghĩa | Hành động |
|---|---|---|
| VERIFIED | Process restore và application checks đều đạt trên đúng pair | Cho phép theo policy |
| PROCESS_RESTORED | Engine restore thành công nhưng application checks chưa hoàn tất | Chưa publish nếu yêu cầu app readiness |
| VENDOR_SUPPORTED | Nằm trong vendor matrix nhưng chưa có test nội bộ | Chưa coi là verified |
| UNTESTED | Chưa có phép thử | Không suy luận là pass |
| UNSUPPORTED | Nằm ngoài phạm vi hỗ trợ | Không dùng checkpoint |
| FAILED | Đã thử và có lỗi | Chặn pair cho tới khi xử lý |
| BLOCKED | Không chạy được do runner/quyền/dependency | Không coi là pass |
| FLAKY | Kết quả không ổn định giữa các lần chạy | Điều tra, không phát hành như VERIFIED |

Release gate nên kiểm tra các target profiles bắt buộc. Nếu một target optional thất bại, policy có thể cho phép release giới hạn phạm vi. Nếu production node pool bắt buộc chưa được test, không nên publish checkpoint cho node pool đó.

### 11.1 Không dùng green build chung chung

Một workflow có thể xanh dù một matrix row bị skipped hoặc excluded. Hãy kiểm tra danh sách required pairs và xác nhận mỗi pair có evidence hợp lệ.

Nếu một test bị skip do runner không có sẵn, status phải là BLOCKED hoặc UNTESTED, không phải PASS.

### 11.2 Fresh startup fallback

Nếu target chưa được kiểm chứng hoặc checkpoint restore thất bại, deployment có thể dùng fresh JVM startup từ cùng container image/JAR theo fallback policy.

Fallback cần kiểm soát side effect. Migration, seed và initialization phải có chính sách idempotent; application readiness chỉ bật sau khi dependency sẵn sàng.

## 12. Test matrix phải kiểm tra application state sau restore

Một process restore thành công không đảm bảo ứng dụng có thể phục vụ. Mỗi target pair cần chạy các kiểm tra phù hợp với ứng dụng.

### 12.1 Resource callbacks

Xác nhận:

- beforeCheckpoint đã dừng nhận công việc và giải phóng tài nguyên.
- afterRestore đã mở lại file, socket và connection pool.
- Callback lỗi được truyền ra ngoài.
- Resource phụ thuộc nhau được phục hồi đúng thứ tự.
- Nhiều vòng checkpoint/restore không gây rò rỉ.
- Không có thread nền tiếp tục dùng handle cũ.

### 12.2 Database và external services

Kiểm tra:

- Database connection mới hoạt động.
- Schema nằm trong compatibility range.
- TLS handshake thành công.
- Secret và certificate được lấy đúng version.
- Service discovery trả endpoint hiện tại.
- Message broker cấp assignment phù hợp.
- Lease được acquire lại hoặc xác minh.
- Cache revision và external state được reconcile.

### 12.3 Filesystem và native memory

Nếu ứng dụng dùng file mapping hoặc native code:

- File backing tồn tại và có quyền.
- Mount layout phù hợp.
- Mapping có thể đọc/ghi theo yêu cầu.
- Native library load đúng ABI.
- Direct/mapped memory được quản lý đúng.
- Không có lỗi native crash hoặc invalid handle.

### 12.4 Functional smoke test

Gửi một số request đại diện sau restore:

- Đọc dữ liệu.
- Ghi dữ liệu test có idempotency key.
- Gọi một dependency nội bộ.
- Thực hiện một đường xử lý có TLS.
- Kiểm tra authentication bằng runtime identity.
- Xác nhận readiness chỉ bật sau reconcile.

Dùng sandbox data và dependency test trong CI. Không để matrix test phát sinh payment, email hoặc side effect production.

## 13. Kiểm tra thời gian và hiệu năng

Ngoài pass/fail, ghi các số đo để biết thay đổi môi trường có làm hiệu năng suy giảm.

Các metric hữu ích:

- Thời gian tạo checkpoint.
- Kích thước checkpoint artifact.
- Thời gian từ lệnh restore tới process alive.
- Thời gian callback afterRestore.
- Thời gian external reconciliation.
- Thời gian tới readiness.
- Latency request đầu tiên.
- Throughput sau restore.
- Error rate sau restore.
- RSS/PSS và native memory.
- Số file descriptor và memory mapping.
- Thời gian tải artifact.

So sánh cùng workload và cùng cách đo. Không kết luận một kernel nhanh hơn chỉ từ một lần chạy; có thể cần nhiều lần lặp và phân tích phân vị.

### 13.1 Phân biệt process restore time và time-to-ready

Một engine có thể khôi phục process nhanh nhưng ứng dụng mất nhiều thời gian reconnect database hoặc lấy credential. Hãy đo riêng:

~~~text
T0: restore command started
T1: process restored
T2: afterRestore callbacks completed
T3: external state reconciled
T4: readiness true
~~~

- Restore duration = T1 - T0.
- Callback duration = T2 - T1.
- Reconcile duration = T3 - T2.
- Time-to-ready = T4 - T0.

Time-to-ready mới là chỉ số gần với trải nghiệm triển khai. Nếu chỉ đo thời gian engine restore, pipeline có thể bỏ qua bottleneck thực tế.

## 14. Khi nào cần chạy lại matrix?

Ma trận cần được cập nhật khi môi trường thay đổi. Không cần chạy lại toàn bộ suite sau mọi commit, nhưng cần policy trigger rõ ràng.

| Thay đổi | Kiểm thử nên kích hoạt |
|---|---|
| JDK vendor/build | Compile, callback và real restore matrix liên quan JDK |
| CRaC runtime/API | Real checkpoint/restore trên mọi target bắt buộc |
| Checkpoint engine/version | Real restore matrix |
| Kernel/node image | Restore trên node pool đã cập nhật |
| CPU architecture | Checkpoint riêng và restore trên architecture tương ứng |
| CPU feature baseline | Restore/native smoke test trên feature profile mới |
| Container image/base image | Tạo checkpoint mới và restore bằng digest mới |
| Container runtime/OCI runtime | Restore trên runner dùng runtime mới |
| Native library/JNI | Native smoke và real restore |
| Filesystem/mount | File mapping và restore test |
| JVM flags | Tạo image mới và restore theo cấu hình mới |
| External dependency/config | Reconciliation, readiness và integration test |

Có thể dùng dependency fingerprint để xác định profile nào bị ảnh hưởng. Nếu chỉ một node pool đổi kernel, chạy lại các pair dùng node pool đó và source image liên quan. Nhưng nếu thay JDK hoặc engine dùng chung, phạm vi retest có thể rộng hơn.

### 14.1 Nightly drift detection

Nightly job có thể thu thập metadata runner và so với profile đã được kiểm chứng. Nếu kernel hoặc runtime đã đổi, job đánh dấu NEEDS_RETEST và chạy restore test.

Điều này đặc biệt hữu ích với hosted runner hoặc node pool được cập nhật tự động. Nếu CI không thể bảo đảm host cố định, metadata thực tế cần được lưu cho mỗi lần chạy.

## 15. Xử lý lỗi trong matrix

Một matrix job thất bại cần chỉ ra layer gây lỗi thay vì chỉ trả “restore failed”.

| Lớp | Ví dụ | Hướng điều tra |
|---|---|---|
| Provisioning | Không lấy được JDK hoặc image | Registry, artifact source và runner setup |
| Source startup | Ứng dụng không warm-up hoặc readiness false | App log, dependency và fixture |
| Checkpoint | beforeCheckpoint hoặc engine thất bại | Callback exception tree, engine log, quyền host |
| Artifact handoff | Thiếu file hoặc checksum sai | Upload/download, storage và path |
| Target provisioning | Runner sai kernel/CPU/runtime | Host fingerprint và runner labels |
| Process restore | Engine không tái tạo được process | JDK/engine/kernel/CPU compatibility |
| Callback recovery | afterRestore ném exception | Resource lifecycle và dependency |
| External reconciliation | Secret/DB/DNS/lease không hợp lệ | External service và identity |
| Functional test | Request lỗi sau restore | App state, stale cache và business flow |

Lưu exit code, stdout/stderr, engine logs và JVM logs theo source-target pair. Tránh ghi secret hoặc token trong log.

### 15.1 Retry có kiểm soát

Có thể retry một lỗi hạ tầng tạm thời như runner bị mất kết nối hoặc artifact download timeout. Nhưng không retry vô hạn một lỗi deterministic như:

- JDK build không tương thích.
- CPU architecture sai.
- Thiếu capability.
- Native library không load được.
- File backing không tồn tại.
- Callback luôn ném exception.

Một test flaky cần status riêng và điều tra nguyên nhân. Không chuyển FLAKY thành VERIFIED chỉ vì lần retry cuối cùng pass.

### 15.2 Giữ evidence kể cả khi job thất bại

Dùng bước always hoặc cơ chế tương đương để thu thập report, nhưng không để bước publish evidence biến một test fail thành success.

Mỗi report cần có:

- Workflow run ID.
- Commit/release ID.
- Checkpoint ID.
- Source và target profile.
- Artifact checksum.
- JDK/engine/kernel/CPU/container metadata.
- Restore result.
- Callback result.
- Application test result.
- Failure reason.
- Thời điểm và duration.

## 16. Bảo vệ CI runner và artifact

Checkpoint image có thể chứa heap data, token, session hoặc secret đã giải mã. Do đó, checkpoint artifact và runner cần được bảo vệ như một môi trường có dữ liệu nhạy cảm.

Áp dụng các nguyên tắc:

- Dùng sandbox data và credential giới hạn.
- Không đưa production secret vào CI runner.
- Giới hạn quyền tạo, tải và restore checkpoint.
- Mã hóa artifact khi lưu và truyền.
- Dùng artifact retention ngắn phù hợp với mục đích test.
- Xóa checkpoint files và workspace sau job.
- Không chạy pull request không tin cậy trên runner có quyền privileged.
- Không ghi token hoặc environment secret vào metadata.
- Audit việc tải và restore artifact.
- Không upload checkpoint vào public artifact storage.

Nếu runner dùng self-hosted, hãy phân vùng runner pool. Job build thông thường không nên có quyền truy cập checkpoint storage hoặc host capability mà restore test cần.

## 17. Ví dụ policy cho release gate

Một policy có thể định nghĩa target profiles bắt buộc trong YAML:

~~~yaml
matrixPolicyVersion: 1

requiredTargets:
  - prod-amd64-poolA
  - prod-amd64-poolB
  - prod-arm64-poolA

requiredChecks:
  artifactIntegrity: true
  processRestore: true
  resourceCallbacks: true
  externalReconciliation: true
  functionalSmoke: true
  readiness: true

allowedStatuses:
  - VERIFIED

fallback:
  enabled: true
  mode: fresh-jvm-startup

evidence:
  requireCheckpointId: true
  requireSourceProfile: true
  requireTargetProfile: true
  requireArtifactChecksum: true
  requirePipelineRun: true
~~~

Đây là policy schema minh họa do pipeline định nghĩa. Release gate cần xác minh mỗi required target có kết quả VERIFIED cho đúng checkpoint ID và source-target pair. Không chấp nhận một kết quả pass của checkpoint cũ hoặc một profile có fingerprint khác.

Nếu production chỉ dùng amd64, không cần đưa arm64 thành required target. Nếu có disaster recovery region dùng kernel/runtime khác, profile đó cần được đưa vào required list.

## 18. Quản lý artifact và metadata giữa các job

Source job và target job cần trao đổi checkpoint artifact bất biến.

Nên lưu:

- Checkpoint files theo cấu trúc engine yêu cầu.
- Checkpoint ID.
- Artifact checksum.
- Source environment profile.
- JAR checksum.
- Container image digest.
- JDK vendor/version/build.
- Engine name/version.
- JVM flags cần thiết.
- Thời điểm tạo checkpoint.
- Application build và config compatibility metadata.

Target job cần xác minh checksum trước restore. Không sửa hoặc ghép file từ nhiều checkpoint. Không dùng artifact name có thể bị ghi đè mà không có version.

Nếu CI artifact storage có retention ngắn, bảo đảm artifact tồn tại cho tất cả target jobs. Với matrix lớn, có thể dùng object storage hoặc artifact store riêng với quyền truy cập giới hạn.

## 19. Ma trận ví dụ cho một release

Một release có thể định nghĩa các profile như sau:

| Profile | JDK | Kernel | CPU | Container | Vai trò |
|---|---|---|---|---|---|
| SRC-A | Vendor A CRaC build 21.x | K1 | amd64 + AVX2 | Digest X / runtime R1 | Tạo checkpoint amd64 |
| DST-A | Vendor A CRaC build 21.x | K1 | amd64 + AVX2 | Digest X / runtime R1 | Production pool A |
| DST-B | Vendor A CRaC build 21.x | K2 | amd64 + AVX2 | Digest X / runtime R2 | Production pool B |
| SRC-C | Vendor A CRaC build 21.x arm64 | K3 | arm64 profile | Digest Y / runtime R1 | Tạo checkpoint arm64 |
| DST-C | Vendor A CRaC build 21.x arm64 | K3 | arm64 profile | Digest Y / runtime R1 | Production arm64 |

Các profile trên chỉ là ví dụ. Cần thay bằng exact build và cấu hình được vendor hỗ trợ.

Matrix pair có thể là:

| Source | Target | Required | Kết quả cần có |
|---|---|---:|---|
| SRC-A | DST-A | Có | VERIFIED |
| SRC-A | DST-B | Có | VERIFIED |
| SRC-C | DST-C | Có | VERIFIED |
| SRC-A | DST-C | Không | UNSUPPORTED hoặc NOT_APPLICABLE theo vendor policy |

Không restore image amd64 trên arm64 chỉ để tạo một dòng test nếu vendor xác định tổ hợp đó không được hỗ trợ. Hãy ghi rõ lý do loại trừ.

## 20. Quy trình triển khai trong CI

Có thể áp dụng quy trình sau cho mỗi thay đổi ảnh hưởng runtime hoặc trước release:

**Bước 1 — Xác định target profiles.** Lấy danh sách node pool và runtime class thực sự triển khai. Ghi JDK, kernel, CPU, container runtime và architecture.

**Bước 2 — Đối chiếu vendor support.** Loại các source-target pair không được hỗ trợ. Ghi rõ những trường bắt buộc trùng hoặc được phép khác.

**Bước 3 — Provision source runner.** Chọn runner có kernel, CPU và engine phù hợp. Cài đúng JDK build và pull container digest.

**Bước 4 — Thu thập source fingerprint.** Ghi OS, kernel, CPU features, JDK, engine, container runtime, image digest và JVM flags.

**Bước 5 — Tạo checkpoint thật.** Khởi động ứng dụng, warm-up, kiểm tra readiness, chạy beforeCheckpoint và lưu artifact cùng manifest.

**Bước 6 — Fan out target jobs.** Mỗi job nhận đúng checkpoint artifact và chạy trên target runner được chỉ định.

**Bước 7 — Thu thập target fingerprint.** Xác minh runner thực tế khớp profile yêu cầu trước khi restore.

**Bước 8 — Restore và kiểm tra ứng dụng.** Chạy engine restore, kiểm tra callback, external reconciliation, functional smoke test và readiness.

**Bước 9 — Lưu evidence.** Ghi kết quả theo source-target pair, bao gồm log, checksum và duration.

**Bước 10 — Áp dụng release gate.** Chỉ publish checkpoint nếu các target bắt buộc đạt policy. Giữ fresh startup fallback cho target chưa được kiểm chứng.

**Bước 11 — Theo dõi drift.** Khi JDK, kernel, CPU, engine hoặc container runtime thay đổi, kích hoạt retest cho các profile bị ảnh hưởng.

**Bước 12 — Dọn runner và artifact tạm.** Đóng process, gỡ mount, revoke test credential và xóa workspace theo retention.

## 21. Tiêu chí hoàn thành một matrix run

Một matrix run có thể được coi là hoàn tất khi:

- Tất cả source profile bắt buộc đã tạo checkpoint hoặc báo lỗi rõ ràng.
- Mỗi artifact có ID và checksum.
- Target job dùng đúng artifact từ source đã khai báo.
- Metadata target được thu thập từ runner thật.
- Runner khớp profile được yêu cầu.
- Restore test dùng checkpoint engine thật.
- Callback sau restore hoàn tất.
- External dependency và readiness được kiểm tra.
- Functional smoke test đạt.
- Mọi required pair có status và evidence.
- Job bị skip hoặc blocked không bị tính là pass.
- Artifact và workspace tạm được xử lý theo retention policy.

Nếu một target không chạy được vì runner offline, kết quả là BLOCKED. Nếu chưa có target profile, là UNTESTED. Nếu process restore thành công nhưng app test chưa chạy, là PROCESS_RESTORED hoặc PARTIALLY_VERIFIED theo policy. Chỉ dùng VERIFIED khi tất cả kiểm tra bắt buộc đã đạt.

## 22. Những sai lầm thường gặp

### Chỉ test một JDK major version

Major version không xác định đầy đủ vendor, patch, build và CRaC integration. Lưu exact JDK build.

### Chạy nhiều container trên cùng một kernel rồi gọi đó là kernel matrix

Container chia sẻ kernel host. Cần runner hoặc VM có kernel thực sự khác nhau.

### Dùng container image để giả lập CPU

Container không giả lập architecture hoặc CPU feature của host. Chạy target trên host/VM có CPU profile tương ứng.

### Chỉ kiểm tra java -version

Lệnh này không cho biết engine, kernel, CPU features, container runtime hoặc mount profile. Thu thập metadata từ host và process.

### Dùng simulation test thay real restore test

Simulation hữu ích cho callback logic, nhưng không chứng minh process image được khôi phục bởi engine thật.

### Tạo Cartesian product quá lớn

Nhiều tổ hợp không áp dụng hoặc không được hỗ trợ. Xây matrix từ production profiles và source-target pair cần thiết.

### Không ghi hướng source → target

Một lần A → B không chứng minh B → A. Ghi từng cặp theo hướng thực tế.

### Dùng runner label mà không kiểm tra metadata

Host có thể đã được nâng kernel hoặc thay CPU. Đọc fingerprint thực tế và fail fast khi lệch profile.

### Chỉ coi exit code restore là thành công

Process có thể sống nhưng database, TLS, secret hoặc broker chưa phục hồi. Chạy application checks và readiness.

### Bỏ qua matrix row bị skip

Một workflow xanh có thể che giấu target chưa được test. Release gate cần kiểm tra danh sách required pairs và evidence.

### Retry vô hạn lỗi deterministic

Lỗi tương thích cần được điều tra và chặn. Retry không sửa được sai architecture, JDK build hoặc native ABI.

## Tài liệu tham khảo

- [CRaC — What CRaC is](https://crac.org/about/about-crac/): mô hình checkpoint/restore và sự phối hợp với ứng dụng.
- [CRaC — Running an Application With CRaC](https://docs.azul.com/crac/usage/running-crac): chuẩn bị JDK/runtime và chạy ứng dụng CRaC.
- [CRaC — CRaC Engines](https://docs.azul.com/crac/usage/crac-engines): các checkpoint engine và khác biệt theo bản dựng.
- [CRaC — Debugging](https://crac.org/reference/debugging/): chẩn đoán lỗi checkpoint và restore.
- [GitHub Actions — Using a matrix for your jobs](https://docs.github.com/actions/using-jobs/using-a-matrix-for-your-jobs): tổ chức job matrix và include/exclude.
- [GitHub Actions — Choosing the runner for a job](https://docs.github.com/actions/using-jobs/choosing-the-runner-for-a-job): runner labels và self-hosted runners.
- [GitHub Actions — Workflow artifacts](https://docs.github.com/actions/using-workflows/storing-workflow-data-as-artifacts): truyền checkpoint artifact và test evidence giữa jobs.
- [Kubernetes — Container Runtimes](https://kubernetes.io/docs/setup/production-environment/container-runtimes/): container runtime trên node.
- [Kubernetes — Nodes](https://kubernetes.io/docs/concepts/architecture/nodes/): node và tài nguyên host trong cluster.
- [Linux man-pages — uname](https://man7.org/linux/man-pages/man2/uname.2.html): truy vấn kernel/system identity.
- [Linux man-pages — proc](https://man7.org/linux/man-pages/man5/proc.5.html): thông tin process và CPU/system data qua procfs.
- [CRIU Documentation](https://criu.org/): checkpoint/restore process trên Linux và các yêu cầu hệ thống.

