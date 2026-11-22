# Xây dựng ma trận môi trường được kiểm chứng thay vì giả định ảnh chạy mọi nơi

Checkpoint image của CRaC (Coordinated Restore at Checkpoint) lưu trạng thái của một tiến trình Java tại một thời điểm. Image có thể chứa heap, thread state, native memory và các cấu trúc runtime mà checkpoint engine cần để khôi phục tiến trình. Vì trạng thái này gắn với JVM, hệ điều hành và tài nguyên của tiến trình, checkpoint image không có tính di động giống JAR ứng dụng.

Một JAR thường có thể chạy trên nhiều JDK tương thích. Một container image có thể chạy trên nhiều host đáp ứng yêu cầu của container runtime. Nhưng một checkpoint image chỉ nên được restore trên những môi trường mà vendor/runtime hỗ trợ và đội triển khai đã kiểm chứng.

Không thể kết luận rằng hai máy tương thích chỉ vì chúng cùng chạy Linux, cùng kiến trúc CPU hoặc cùng phiên bản Java chính. Tương thích phụ thuộc vào một tập hợp cụ thể gồm JDK build, CRaC integration, checkpoint engine, kernel, CPU features, native libraries, filesystem, container runtime, cấu hình JVM và trạng thái bên ngoài.

Cách quản lý đáng tin cậy là xây dựng **ma trận môi trường được kiểm chứng**. Ma trận ghi rõ image được tạo ở môi trường nào, đã restore thành công trên những môi trường nào, bằng chứng kiểm thử là gì và phạm vi nào chưa được thử. Mỗi kết luận phải gắn với một tổ hợp phiên bản và cấu hình cụ thể.

## 1. Vì sao không thể giả định checkpoint chạy ở mọi nơi?

Một checkpoint image không chỉ chứa bytecode. Nó lưu trạng thái của một tiến trình đang chạy. Khi restore, runtime phải khôi phục các vùng nhớ, thread và trạng thái hệ thống mà tiến trình phụ thuộc.

Các thành phần sau có thể làm thay đổi khả năng restore:

- **JDK vendor và build:** mỗi bản dựng có thể chứa implementation JVM, CRaC API và thay đổi nội bộ khác nhau.
- **Checkpoint engine:** engine quyết định cách chụp và khôi phục process state, memory pages, file descriptor và các tài nguyên được hỗ trợ.
- **Operating system và kernel:** system call, VMA, namespace, cgroup, signal và cấu trúc tiến trình phụ thuộc hệ điều hành.
- **CPU architecture và features:** register state, instruction set, native code và các extension của CPU có thể khác.
- **Native libraries:** JNI, thư viện C/C++, allocator, TLS library hoặc driver có thể phụ thuộc ABI và phiên bản.
- **Container runtime:** cách tạo namespace, mount, capability và cgroup có thể ảnh hưởng checkpoint/restore.
- **Filesystem và volume:** file backing, mount point, permission, overlay filesystem và shared volume có thể thay đổi.
- **JVM flags và runtime configuration:** heap, GC, memory layout, system properties và environment có thể ảnh hưởng trạng thái đã lưu.
- **External dependencies:** database, DNS, secret, certificate, service endpoint và lease có thể thay đổi trong thời gian image được giữ.

Một image có thể được tạo thành công nhưng restore thất bại trên host khác. Cũng có thể restore thành công nhưng callback afterRestore không mở lại được database pool hoặc cấu hình hiện tại không còn tương thích. Do đó, kiểm tra khả năng đọc file checkpoint hoặc thấy process được tạo chưa đủ để đánh dấu một môi trường là tương thích.

## 2. Tương thích là quan hệ giữa nguồn tạo ảnh và đích restore

Một lỗi thiết kế ma trận thường gặp là chỉ ghi một danh sách các môi trường “được hỗ trợ”. Nhưng checkpoint được tạo trên một môi trường nguồn rồi restore trên một môi trường đích. Khả năng tương thích là quan hệ giữa hai phía.

Ví dụ:

- Image A được tạo trên Linux distribution X, kernel build K1, JDK build J1 và engine E1.
- Host B có cùng CPU architecture nhưng kernel K2, JDK build J1 và engine E1.
- Host C có kernel K1 nhưng JDK build J2.
- Host D dùng cùng container image digest nhưng CPU features khác.

Không thể chỉ từ một chiều riêng lẻ kết luận B, C hoặc D có thể restore A. Cần thử tổ hợp thực tế theo hướng source → target và đối chiếu với ma trận hỗ trợ chính thức của vendor.

~~~mermaid
flowchart LR
    S["Source environment<br/>Tạo checkpoint"] --> I["Checkpoint artifact<br/>+ metadata"]
    I --> T1["Target A<br/>Restore test"]
    I --> T2["Target B<br/>Restore test"]
    I --> T3["Target C<br/>Restore test"]
    T1 --> R1["Verified / Failed"]
    T2 --> R2["Verified / Failed"]
    T3 --> R3["Verified / Failed"]
~~~

Kết quả A → B không tự chứng minh B → A. Một số khác biệt có thể ảnh hưởng theo hướng: image được tạo từ build mới có thể không restore được trên runtime cũ, trong khi hướng ngược lại có thể được vendor hỗ trợ. Hãy ghi rõ hướng kiểm thử.

### 2.1 Phân biệt ba câu hỏi

Khi đánh giá một target, cần trả lời riêng:

1. **Vendor-supported:** tổ hợp này có nằm trong phạm vi hỗ trợ được công bố của vendor/runtime hay không?
2. **Technically-restored:** checkpoint engine có restore process thành công trong phép thử hay không?
3. **Application-ready:** ứng dụng có phục hồi resource, đối chiếu dependency và vượt qua health check nghiệp vụ hay không?

Một kết quả restore thành công trong một lần thử không tự mở rộng phạm vi hỗ trợ chính thức. Ngược lại, một tổ hợp nằm trong ma trận vendor hỗ trợ vẫn cần kiểm thử ứng dụng thực tế vì native library và external dependency của ứng dụng có thể có yêu cầu riêng.

## 3. Những chiều cần có trong ma trận môi trường

Ma trận không cần ghi mọi thông tin của máy, nhưng phải lưu đủ những yếu tố có thể ảnh hưởng checkpoint và restore. Nên phân chia thành nhóm runtime, host, container, ứng dụng và external state.

### 3.1 JDK và CRaC runtime

Ghi rõ:

- Vendor và tên bản phân phối JDK.
- Phiên bản Java đầy đủ, bao gồm update/build number.
- Kiến trúc JDK.
- CRaC API/runtime version hoặc build identifier.
- JVM implementation và GC nếu vendor yêu cầu.
- JVM flags có ảnh hưởng đến memory layout hoặc checkpoint.
- Các system properties và environment variables liên quan.
- Các module native hoặc agent được nạp.

Không chỉ ghi “Java 21”. Hai JDK cùng major version có thể khác vendor, patch level, CRaC integration hoặc cách đóng gói engine.

Lệnh sau hữu ích để lưu thông tin runtime cơ bản:

~~~bash
java -version
~~~

Có thể ghi thêm các system properties và command line thực tế của process. Không đưa giá trị secret vào báo cáo môi trường.

### 3.2 Checkpoint engine

Ghi rõ:

- Tên engine.
- Phiên bản và build.
- Engine configuration.
- Cách tạo image và cách restore.
- Các tùy chọn liên quan memory loading hoặc compression.
- Quyền và capability yêu cầu.
- Giới hạn đã biết theo tài liệu vendor.

CRIU và Warp là những ví dụ engine có cách triển khai khác nhau. Không suy luận kết quả của một engine sang engine khác. Simulation engine có thể hữu ích để chạy callback và kiểm tra lifecycle, nhưng không chứng minh process image thật có thể restore trên kernel production.

### 3.3 Hệ điều hành và kernel

Ghi nhận:

- OS distribution và release.
- Kernel release và build.
- CPU architecture.
- CPU model hoặc CPU feature flags có liên quan.
- Kernel configuration hoặc sysctl quan trọng.
- Namespace và cgroup mode.
- Các giới hạn process, memory map và file descriptor.
- SELinux/AppArmor hoặc chính sách bảo mật tương đương.
- Các capability hoặc quyền cần cho engine.

Ví dụ lệnh trên Linux:

~~~bash
uname -a
cat /etc/os-release
lscpu
~~~

Các lệnh này cung cấp thông tin nền tảng. Không phải mọi trường trong output đều cần so sánh; chọn các trường được vendor hoặc engine xác định là điều kiện tương thích.

### 3.4 Container và orchestration

Nếu chạy trong container, ghi rõ:

- Container image digest, không chỉ tag.
- Container runtime và phiên bản.
- OCI runtime nếu có.
- Base image và userland libraries.
- Mount namespace, volume và mount options.
- UID/GID, user và group.
- Linux capabilities và seccomp profile.
- cgroup version và resource limits.
- Kubernetes version, node pool và runtime class nếu triển khai trên Kubernetes.

Một image có cùng digest nhưng chạy trên host có kernel hoặc CPU khác vẫn cần được kiểm chứng. Container image không che giấu toàn bộ kernel và CPU của host.

### 3.5 Filesystem và tài nguyên bên ngoài

Ghi nhận các file và mount mà checkpoint hoặc ứng dụng cần sau restore:

- Filesystem type.
- Mount point và mount options.
- File backing cho memory mapping.
- Quyền truy cập và ownership.
- Volume có được mount ở target hay không.
- Network filesystem hoặc volume driver.
- DNS, route và endpoint.
- Database schema compatibility.
- Secret/certificate source và revision.
- Message broker, partition assignment hoặc lease service.

Không lưu secret nguyên bản trong ma trận. Chỉ lưu tên secret, version identifier hoặc fingerprint không nhạy cảm nếu cần đối chiếu.

### 3.6 Ứng dụng và dependency

Mỗi checkpoint cần liên kết với:

- Source commit hoặc release ID.
- Application JAR hash.
- Dependency lockfile hoặc SBOM.
- Native library versions.
- Agent và instrumentation.
- JVM arguments.
- Configuration revision.
- Schema compatibility range.
- Checkpoint ID và checksum.
- Thời điểm tạo ảnh.

Nếu ứng dụng dùng JNI hoặc thư viện native, ghi rõ phiên bản và ABI. Thay một native library có thể làm thay đổi khả năng restore dù JAR không đổi.

## 4. Thiết kế ma trận theo tổ hợp có ý nghĩa

Không nên tạo một bảng khổng lồ liệt kê tất cả giá trị OS × JDK × engine × CPU × filesystem rồi giả định mọi tổ hợp đều phải được thử. Số lượng tổ hợp tăng rất nhanh.

Thay vào đó, bắt đầu từ các môi trường thực tế mà tổ chức dự định dùng, sau đó chọn các chiều có khả năng ảnh hưởng và các target đại diện.

Ví dụ ma trận rút gọn:

| Source checkpoint | Target restore | Vendor support | Restore test | App readiness | Kết luận |
|---|---|---|---|---|---|
| Linux x86_64, JDK build A, engine E1 | Cùng host class và build | Có | Pass | Pass | Verified |
| Linux x86_64, JDK build A, engine E1 | Kernel mới hơn, cùng JDK/engine | Cần xác nhận | Chưa chạy | Chưa chạy | Untested |
| Linux x86_64, JDK build A, engine E1 | JDK vendor khác | Không rõ | Fail | N/A | Not approved |
| Linux x86_64, engine E1 | Linux ARM64, engine E1 | Không hỗ trợ theo ma trận hiện tại | Không chạy | N/A | Unsupported |
| Container digest X, checkpoint C1 | Cùng digest, host node pool B | Có điều kiện | Pass | Dependency test pending | Partially verified |

Các dòng trên chỉ minh họa cấu trúc bảng, không phải kết luận hỗ trợ cho một vendor cụ thể.

### 4.1 Đặt tên environment profile

Mỗi môi trường kiểm thử nên có một ID ổn định, ví dụ:

- linux-amd64-jdkA-engineE1-kernelK1.
- linux-amd64-jdkA-engineE1-kernelK2.
- linux-arm64-jdkA-engineE1-kernelK3.
- linux-amd64-jdkB-engineE2-kernelK4.

ID không thay thế metadata chi tiết. Nó giúp đọc ma trận và liên kết log với cấu hình đã lưu.

### 4.2 Ma trận có hướng source → target

Có thể biểu diễn mỗi phép thử bằng một cặp:

| Checkpoint source | Restore target | Kết quả |
|---|---|---|
| profile-A | profile-A | Pass |
| profile-A | profile-B | Pass/Fail |
| profile-A | profile-C | Pass/Fail |
| profile-B | profile-A | Pass/Fail |
| profile-B | profile-B | Pass |

Nếu chỉ có một source image trong pipeline, ít nhất cần thử restore trên tất cả target class dự kiến. Nếu image được tạo trên nhiều loại source, phải ghi rõ source class nào đã được thử với target nào.

Không gộp hai chiều thành một ô “A và B tương thích” nếu chỉ thử A → B.

## 5. Phân loại kết quả kiểm chứng

Dùng các trạng thái có ý nghĩa rõ ràng. Không để ô trống bị hiểu nhầm là tương thích.

| Trạng thái | Ý nghĩa | Có được deploy? |
|---|---|---|
| VERIFIED | Đã thử đúng tổ hợp source/target và ứng dụng vượt qua kiểm tra cần thiết | Có, trong phạm vi đã thử |
| VENDOR_SUPPORTED | Vendor công bố hỗ trợ, nhưng phép thử ứng dụng nội bộ chưa hoàn tất | Chỉ theo policy của tổ chức; không gọi là verified |
| PARTIALLY_VERIFIED | Process restore thành công nhưng còn bước app/dependency hoặc workload chưa được xác nhận | Chưa mở rộng ngoài phạm vi đã kiểm |
| UNTESTED | Chưa có bằng chứng kiểm thử | Không giả định là tương thích |
| UNSUPPORTED | Vendor hoặc nền tảng không hỗ trợ tổ hợp đó | Không deploy checkpoint |
| FAILED | Đã thử và thất bại | Không deploy cho tới khi nguyên nhân được giải quyết |
| BLOCKED | Không thể chạy phép thử vì thiếu quyền, hạ tầng hoặc dependency | Không coi là pass |

Có thể tách hai cột vendor support và internal verification thay vì gộp thành một status. Ví dụ, vendor-supported nhưng chưa verified là thông tin hữu ích và cần được giữ riêng.

### 5.1 Bằng chứng phải đi cùng trạng thái

Một dòng VERIFIED cần có:

- Checkpoint ID.
- Source profile ID.
- Target profile ID.
- JAR hash và container digest.
- JDK/engine/kernel/architecture.
- Ngày giờ kiểm thử.
- Pipeline run hoặc test report ID.
- Kết quả process restore.
- Kết quả callback.
- Kết quả external reconciliation.
- Kết quả functional smoke test.
- Người hoặc hệ thống xác nhận.

Nếu thiếu bằng chứng, status nên là UNTESTED hoặc PARTIALLY_VERIFIED.

## 6. Quy trình kiểm thử một cặp môi trường

Một phép thử tương thích cần xác nhận cả khả năng khôi phục process và khả năng ứng dụng tiếp tục hoạt động.

### 6.1 Chuẩn bị source environment

1. Chọn đúng JAR và container image digest.
2. Ghi nhận JDK, CRaC runtime, engine, kernel, CPU và cấu hình container.
3. Khởi động ứng dụng trong source profile.
4. Chờ startup và warm-up hoàn tất.
5. Xác minh readiness và dependency.
6. Yêu cầu checkpoint.
7. Thu thập checkpoint files, checksum và metadata.
8. Ghi log của beforeCheckpoint và kết quả engine.

Checkpoint phải được tạo bởi runtime/engine thật sẽ dùng trong triển khai. Chạy callback bằng simulation engine không thay thế bước này.

### 6.2 Chuẩn bị target environment

1. Tạo target host hoặc node thuộc profile cần thử.
2. Cài đặt hoặc pull đúng container image digest.
3. Cung cấp mount, volume, permission và runtime configuration.
4. Kiểm tra target đáp ứng yêu cầu vendor/engine.
5. Cấp external dependency test phù hợp.
6. Đưa checkpoint artifact tới target theo cách không thay đổi bytes.

Không sửa checkpoint files hoặc ghép một phần image từ nhiều lần tạo. Nếu engine tạo một bộ file, cần giữ đúng cấu trúc và quan hệ giữa các file.

### 6.3 Thực hiện restore

Khôi phục process theo hướng dẫn của đúng runtime/engine. Ghi nhận:

- Engine có mở và đọc được checkpoint artifact không.
- Process có được tạo thành công không.
- JVM có tiếp tục được không.
- Callback afterRestore có chạy đầy đủ không.
- Có suppressed exception hoặc native error nào không.
- Thời gian restore là bao lâu.
- Resource nào được reconnect hoặc recreate.

Một exit code thành công của lệnh restore chưa đủ để xác nhận application readiness.

### 6.4 Kiểm tra ứng dụng sau restore

Chạy các kiểm tra chức năng phù hợp:

- Readiness và liveness.
- Database query hoặc transaction test.
- Network client và TLS handshake.
- File read/write và memory mapping nếu có.
- Message consumer reconnect và offset correctness.
- Secret/certificate refresh.
- Lease/lock reacquisition.
- Cache revision và external state reconciliation.
- Một request nghiệp vụ đại diện.
- Kiểm tra không lặp side effect hoặc migration ngoài ý muốn.

Nếu process restore thành công nhưng database pool không kết nối được, kết quả là PARTIALLY_VERIFIED hoặc FAILED tùy tiêu chí, không phải VERIFIED.

### 6.5 Lặp lại và kiểm tra tải

Một lần restore thành công chỉ chứng minh một lần chạy. Với môi trường quan trọng, cần thử nhiều vòng:

- Tạo checkpoint mới và restore lặp lại.
- Restore đồng thời nhiều instance nếu production làm như vậy.
- Restore sau thời gian image được giữ lâu hơn.
- Thay đổi external dependency trong khoảng checkpoint/restore.
- Thử workload đại diện sau restore.
- Kiểm tra resource leak và thời gian readiness.

## 7. Tránh bùng nổ tổ hợp kiểm thử

Nếu có 4 JDK builds, 3 kernels, 2 architectures, 2 engines, 3 filesystem classes và 2 container runtimes, số tổ hợp đầy đủ là rất lớn. Không nhất thiết phải thử mọi tổ hợp nếu nhiều cấu hình không được triển khai hoặc vendor không hỗ trợ.

Có thể giảm phạm vi theo các bước:

1. Loại các tổ hợp vendor xác định không hỗ trợ.
2. Chọn các profile đang dùng hoặc dự kiến triển khai.
3. Ưu tiên thay đổi có thể ảnh hưởng process state: JDK, engine, kernel, architecture.
4. Tạo test riêng cho native library, file mapping, filesystem và container policy mà ứng dụng sử dụng.
5. Dùng pairwise hoặc representative combinations cho các chiều ít tương tác, nhưng giữ test end-to-end cho các tổ hợp production thực tế.
6. Bổ sung test khi một thành phần thay đổi hoặc có incident.

Pairwise testing giúp giảm số tổ hợp, nhưng không chứng minh mọi tương tác ba chiều hoặc bốn chiều. Ví dụ, một native library có thể chỉ lỗi khi đồng thời dùng architecture cụ thể và một JDK build cụ thể. Với những chiều có rủi ro cao, hãy thử đúng tổ hợp thực tế.

### 7.1 Chọn test theo rủi ro

| Thay đổi | Mức ưu tiên kiểm thử |
|---|---|
| JDK vendor/build thay đổi | Rất cao |
| Checkpoint engine/version thay đổi | Rất cao |
| CPU architecture thay đổi | Rất cao |
| Kernel hoặc OS family thay đổi | Cao |
| Native library hoặc JNI thay đổi | Cao |
| Container runtime/security policy thay đổi | Cao |
| Filesystem/mount thay đổi | Cao nếu có file mapping hoặc engine phụ thuộc |
| Chỉ thay đổi application config | Kiểm tra reconciliation và compatibility |
| Chỉ thay đổi dữ liệu bên ngoài | Kiểm tra external state và readiness |

Mức ưu tiên là gợi ý để lập kế hoạch, không thay thế ma trận hỗ trợ vendor.

## 8. Ví dụ cấu trúc dữ liệu cho ma trận

Có thể lưu ma trận trong YAML để review bằng Git. Ví dụ dưới đây minh họa một source profile và hai target profile:

~~~yaml
matrixVersion: 1

application:
  name: orders-service
  version: 2.8.1
  sourceCommit: abcdef123
  jarSha256: sha256:example-jar-digest

checkpoint:
  id: orders-2.8.1-amd64-001
  artifactSha256: sha256:example-checkpoint-digest
  createdAt: "2026-11-13T06:00:00Z"
  sourceProfile: linux-amd64-jdkA-engineE1

profiles:
  linux-amd64-jdkA-engineE1:
    os: linux
    distribution: example-linux
    kernel: "6.x.y"
    architecture: amd64
    cpuFeatures:
      - sse4_2
      - avx2
    jdkVendor: example-vendor
    jdkBuild: example-crac-build
    cracRuntime: example-crac-version
    engine:
      name: example-engine
      version: example-engine-version
    containerRuntime: example-runtime
    containerDigest: sha256:example-container-digest
    filesystem: ext4

  linux-amd64-jdkA-engineE1-target:
    os: linux
    distribution: example-linux
    kernel: "6.x.z"
    architecture: amd64
    cpuFeatures:
      - sse4_2
      - avx2
    jdkVendor: example-vendor
    jdkBuild: example-crac-build
    cracRuntime: example-crac-version
    engine:
      name: example-engine
      version: example-engine-version
    containerRuntime: example-runtime
    containerDigest: sha256:example-container-digest
    filesystem: ext4

tests:
  - source: linux-amd64-jdkA-engineE1
    target: linux-amd64-jdkA-engineE1
    vendorSupport: supported
    restoreResult: passed
    applicationResult: passed
    status: VERIFIED
    evidence:
      pipelineRun: "run-12345"
      report: "artifacts/restore-report.json"
      testedAt: "2026-11-13T07:00:00Z"

  - source: linux-amd64-jdkA-engineE1
    target: linux-amd64-jdkA-engineE1-target
    vendorSupport: pending
    restoreResult: not_run
    applicationResult: not_run
    status: UNTESTED
~~~

Các giá trị ví dụ không phải cấu hình CRaC thực tế. Schema này do đội triển khai tự định nghĩa. Có thể lưu các trường chi tiết hơn như kernel config, cgroup mode, seccomp profile, mount options, CPU model, native library hashes và JVM flags.

### 8.1 Giữ test evidence riêng

Không nhất thiết phải nhúng toàn bộ log vào YAML. Manifest có thể trỏ tới:

- Test report.
- Engine log.
- JVM log.
- Runtime metadata.
- Checkpoint checksum.
- Restore timing.
- Functional test result.

Bằng chứng nên được lưu bất biến theo pipeline run hoặc release ID. Nếu report bị ghi đè, ma trận mất khả năng truy vết.

## 9. Tự động thu thập metadata môi trường

Để tránh nhập tay sai version, pipeline nên thu thập metadata từ chính host/process đã tạo checkpoint và target đang restore.

Ví dụ các lệnh Linux:

~~~bash
java -version
uname -a
cat /etc/os-release
lscpu
cat /proc/self/status
~~~

Nếu chạy trong container, bổ sung metadata từ container runtime và orchestration platform. Một số thông tin có thể cần quyền đọc đặc biệt; nếu không thu thập được, ghi UNKNOWN thay vì tự suy đoán.

### 9.1 Không lưu secret trong manifest

Manifest có thể được lưu lâu và chia sẻ rộng trong pipeline. Chỉ ghi version hoặc reference:

- Secret name và version ID.
- Certificate fingerprint.
- Configuration revision.
- Workload identity provider.
- Environment name.

Không ghi password, token, private key hoặc nội dung secret.

### 9.2 Chuẩn hóa metadata

Dùng định dạng thống nhất:

- Version đầy đủ thay vì chỉ major version.
- Architecture theo tên chuẩn như amd64 hoặc arm64.
- Kernel release đầy đủ.
- Image digest thay cho tag mutable.
- UTC timestamp.
- Checkpoint ID duy nhất.
- Source và target profile ID.
- Kết quả test có enum cố định.

Chuẩn hóa giúp so sánh profile tự động và phát hiện thay đổi ngoài dự kiến.

## 10. Ma trận tương thích cần gắn với release pipeline

Ma trận chỉ có giá trị nếu pipeline sử dụng nó để quyết định phát hành. Nếu chỉ lưu một spreadsheet mà không có release gate, người triển khai vẫn có thể chọn nhầm image.

Một pipeline có thể có các giai đoạn:

~~~mermaid
flowchart TD
    A["Build JAR and container image"] --> B["Collect source environment metadata"]
    B --> C["Start and warm up application"]
    C --> D["Create checkpoint"]
    D --> E["Store immutable checkpoint + manifest"]
    E --> F["Select target profiles"]
    F --> G["Run restore matrix"]
    G --> H{"Required profiles verified?"}
    H -->|Yes| I["Publish checkpoint release"]
    H -->|No| J["Block release or use fresh startup"]
    I --> K["Deploy by approved profile"]
    J --> L["Record failure and investigate"]
~~~

### 10.1 Định nghĩa required profiles

Không phải mọi môi trường có trong inventory đều cần hỗ trợ mọi release. Hãy xác định required profiles theo deployment target:

- Production node pool A.
- Production node pool B.
- Disaster recovery region.
- Staging.
- Development hoặc CI runner.

Một release chỉ được đánh dấu đủ điều kiện nếu các profile bắt buộc đã được kiểm chứng hoặc có ngoại lệ được phê duyệt theo policy.

### 10.2 Kiểm tra drift trước deploy

Ngay cả khi một profile từng VERIFIED, host có thể được nâng kernel, đổi CPU generation hoặc cập nhật container runtime.

Trước khi deploy:

1. Thu thập target metadata hiện tại.
2. So sánh với profile đã kiểm chứng.
3. Xác định các trường đã thay đổi.
4. Kiểm tra thay đổi có nằm trong phạm vi vendor support và test evidence không.
5. Nếu thay đổi quan trọng, yêu cầu restore test mới.
6. Nếu không có bằng chứng, chọn fresh startup hoặc target đã được xác nhận.

Không nên tự động coi một profile mới là tương thích chỉ vì khác biệt có vẻ nhỏ.

### 10.3 Fresh startup là fallback rõ ràng

Nếu target không nằm trong ma trận VERIFIED hoặc không còn đáp ứng profile, pipeline có thể:

- Chặn triển khai checkpoint.
- Chọn node pool đã được kiểm chứng.
- Tạo checkpoint mới trên target class phù hợp.
- Khởi động JVM mới từ JAR trong container image.

Fresh startup không cần checkpoint compatibility, nhưng vẫn cần application/runtime compatibility bình thường. Nó cũng phải tuân theo chính sách migration, initialization và readiness của ứng dụng.

## 11. Kiểm tra tương thích ở mức ứng dụng

Process restore chỉ là tầng đầu tiên. Một ma trận tốt phải bao gồm kiểm tra các tính năng ứng dụng thực sự sử dụng.

### 11.1 Resource lifecycle

Xác nhận:

- beforeCheckpoint hoàn tất.
- Tài nguyên cần đóng đã được giải phóng.
- afterRestore mở lại được file, socket và pool.
- Callback lỗi được báo đúng.
- Thứ tự callback không gây phụ thuộc sai.
- Nhiều lần checkpoint/restore không làm rò rỉ resource.

### 11.2 Native code và memory

Nếu ứng dụng có native code:

- Xác minh thư viện có cùng ABI và version.
- Kiểm tra native thread và TLS state.
- Kiểm tra direct buffer và mapped memory.
- Kiểm tra file backing và mount.
- Chạy một thao tác native đại diện sau restore.
- Kiểm tra memory usage và lỗi segmentation/native crash.

### 11.3 External state

Kiểm tra:

- Database connection và schema compatibility.
- DNS và service discovery.
- Secret/certificate rotation.
- Session và token expiration.
- Lease và fencing token.
- Message broker assignment và cursor.
- Feature flag/config revision.
- Cache invalidation hoặc replay event.

Những kiểm tra này giúp phát hiện trường hợp process restore thành công nhưng ứng dụng vẫn mang trạng thái cũ.

### 11.4 Hiệu năng sau restore

Đo:

- Thời gian từ restore command tới process available.
- Thời gian callback afterRestore.
- Thời gian external reconciliation.
- Thời gian tới readiness.
- Latency của request đầu tiên.
- Throughput và error rate sau restore.
- Memory RSS/PSS và số lượng file descriptor.
- Kích thước checkpoint artifact.

Một image có thể restore thành công nhưng không đạt mục tiêu latency hoặc tiêu thụ bộ nhớ quá cao. Kết quả hiệu năng cần được ghi riêng với kết quả tương thích chức năng.

## 12. Quản lý thay đổi và tái kiểm chứng

Ma trận không phải tài liệu viết một lần rồi giữ nguyên mãi. Mỗi thay đổi runtime hoặc nền tảng có thể làm một kết luận cũ hết hiệu lực.

### 12.1 Những thay đổi cần đánh giá lại

| Thay đổi | Phần cần kiểm chứng lại |
|---|---|
| JDK vendor/build | Checkpoint/restore và application tests |
| CRaC runtime/API | Callback behavior, image format và restore |
| Checkpoint engine | Toàn bộ process restore trên target profiles |
| Kernel | Process state, VMA, syscall và engine requirements |
| CPU architecture/model/features | Native code và process compatibility |
| Container runtime/OCI runtime | Namespace, mount, cgroup và permission |
| Native library | ABI, memory, thread và callback |
| Filesystem/volume | File mapping, permission và backing data |
| JVM flags | Runtime layout, heap và restore configuration |
| Application JAR | Functional tests và checkpoint recreation |
| External dependency version | Reconciliation và application readiness |

### 12.2 Không tái sử dụng status VERIFIED một cách mù quáng

Nếu source profile thay đổi JDK build hoặc target profile thay kernel, status cũ có thể không còn áp dụng.

Có thể lưu testedProfileFingerprint hoặc hash metadata đã chuẩn hóa. Khi fingerprint hiện tại khác fingerprint đã thử ở trường quan trọng, pipeline đánh dấu NEEDS_RETEST.

Không nhất thiết mọi thay đổi đều buộc phải tạo checkpoint mới. Quyết định dựa trên tài liệu vendor và ảnh hưởng thực tế. Nhưng phải có quy tắc rõ ràng để status VERIFIED không tồn tại vô thời hạn sau khi môi trường đã đổi.

## 13. Kiểm soát phạm vi hỗ trợ

Một sản phẩm có thể tuyên bố hỗ trợ nhiều loại host, nhưng checkpoint compatibility cần một phạm vi cụ thể hơn.

Ví dụ, thay vì tuyên bố:

> Checkpoint chạy trên Linux.

Hãy mô tả phạm vi:

- Linux distribution và kernel range đã được kiểm tra.
- JDK vendor/build được hỗ trợ.
- Checkpoint engine và version.
- CPU architecture/features.
- Container runtime và cấu hình.
- Filesystem và mount profile.
- Các native library được kiểm chứng.
- Target profiles đã restore thành công.

Phạm vi này có thể được cập nhật theo release. Nếu có một host nằm ngoài ma trận, hãy xem nó là UNTESTED cho tới khi có bằng chứng.

### 13.1 Phân biệt vendor matrix và application matrix

Vendor có thể công bố một ma trận hỗ trợ engine/runtime/platform. Đó là nền tảng để chọn tổ hợp hợp lệ.

Ứng dụng cần một ma trận riêng vì nó có thêm:

- Framework.
- JNI/native libraries.
- Database driver.
- HTTP/TLS stack.
- Filesystem mapping.
- External dependencies.
- Callback và readiness logic.

Một tổ hợp vendor-supported có thể vẫn không phù hợp với ứng dụng nếu ứng dụng giữ native state hoặc resource không được xử lý đúng.

## 14. Ví dụ báo cáo kiểm thử

Một báo cáo restore nên mô tả source và target cụ thể:

~~~text
Checkpoint compatibility test

Checkpoint ID: orders-2.8.1-amd64-001
Source profile: linux-amd64-jdkA-engineE1
Target profile: linux-amd64-jdkA-engineE1-nodepoolB

Source:
  JDK build: <exact-build>
  Engine: <name-and-version>
  Kernel: <release>
  Architecture: amd64
  Container digest: sha256:<digest>

Target:
  JDK build: <exact-build>
  Engine: <name-and-version>
  Kernel: <release>
  Architecture: amd64
  Container digest: sha256:<digest>

Results:
  Artifact integrity: PASS
  Process restore: PASS
  afterRestore callbacks: PASS
  Database reconnect: PASS
  Secret validation: PASS
  Service discovery: PASS
  Functional smoke test: PASS
  Readiness: PASS

Restore duration: <measured-duration>
Evidence: <pipeline-run-or-report-id>
Status: VERIFIED
~~~

Các giá trị trong dấu ngoặc nhọn là placeholder. Báo cáo phải được sinh từ dữ liệu thật của pipeline, không copy một báo cáo cũ rồi thay tên profile.

## 15. Xử lý khi một target thất bại

Khi restore thất bại, không nên lập tức kết luận toàn bộ source image không dùng được. Hãy xác định lớp gây lỗi.

| Lớp | Ví dụ dấu hiệu | Hướng xử lý |
|---|---|---|
| Artifact integrity | Checksum sai, file thiếu | Tải lại artifact, xác minh quá trình publish |
| JDK/CRaC | Runtime từ chối image hoặc callback/API khác | So sánh exact build và vendor support |
| Engine | Không tái tạo được process state | Kiểm tra engine version, log và quyền |
| Kernel/platform | System call, namespace hoặc VMA failure | Kiểm tra kernel, sysctl, capability và host profile |
| CPU | Native instruction hoặc architecture mismatch | Kiểm tra architecture/features và tạo image riêng |
| Container | Mount, seccomp hoặc cgroup khác | So sánh container runtime và security policy |
| Native library | Linker error, crash hoặc native handle invalid | Kiểm tra ABI, library version và native lifecycle |
| Application | Callback hoặc readiness thất bại | Đọc exception tree và external dependency state |

Ghi lại lỗi theo source-target pair. Một target failure không nên làm mất kết quả pass của các target khác, nhưng phải làm target lỗi chuyển sang FAILED hoặc BLOCKED.

Nếu target nằm ngoài phạm vi hỗ trợ vendor, không nên tiếp tục thử bằng các thay đổi tùy tiện trong production. Dùng môi trường test cô lập hoặc chọn fresh startup.

## 16. Quản lý image theo architecture và environment

Nếu cluster có nhiều kiến trúc CPU hoặc nhiều environment, có thể cần nhiều checkpoint artifact.

~~~text
checkpoint-artifacts/
  orders-service/
    2.8.1/
      linux-amd64/
        checkpoint-001/
        manifest.json
      linux-arm64/
        checkpoint-001/
        manifest.json
    2.8.2/
      linux-amd64/
        checkpoint-001/
        manifest.json
~~~

Nếu staging và production có credential, endpoint hoặc config khác nhau, không nên dùng chung image nếu heap đã chứa trạng thái riêng của environment.

Một checkpoint có thể được tạo theo application build nhưng cần phân tách theo:

- Architecture.
- JDK/engine build.
- Runtime profile.
- Environment/config revision.
- External dependency compatibility.

Không nhất thiết mỗi tổ hợp phải có artifact riêng nếu vendor và kiểm thử xác nhận cùng một image có thể restore trên nhiều target. Nhưng kết luận đó phải được ghi bằng các source-target pair đã thử.

## 17. Bảo mật và quyền truy cập vào bằng chứng

Ma trận chứa thông tin hạ tầng có thể nhạy cảm: kernel build, CPU model, runtime version, network profile và container digest. Checkpoint artifact còn có thể chứa secret trong heap.

Hãy áp dụng các nguyên tắc:

- Không lưu secret nguyên bản trong profile hoặc report.
- Phân quyền truy cập checkpoint artifact riêng với container image.
- Mã hóa checkpoint khi lưu và truyền.
- Audit ai tải hoặc restore image.
- Không đưa internal hostname hoặc IP nhạy cảm vào report được chia sẻ công khai.
- Giữ test report theo retention policy.
- Thu hồi artifact khi release hoặc credential đã bị thu hồi.
- Dùng immutable digest để phát hiện thay đổi artifact.

Ma trận có thể được chia thành phần công khai cho đội phát triển và phần hạ tầng chi tiết chỉ dành cho vận hành.

## 18. Quy trình xây dựng và duy trì ma trận

Có thể áp dụng quy trình sau cho mỗi release:

**Bước 1 — Chọn source profile.** Xác định môi trường sẽ khởi động ứng dụng, warm-up và tạo checkpoint. Ghi đầy đủ JDK, engine, kernel, architecture và container digest.

**Bước 2 — Thu thập metadata.** Tự động ghi nhận OS, kernel, CPU features, container runtime, filesystem, JVM flags và native libraries.

**Bước 3 — Xác định target profiles.** Liệt kê node pool, region, architecture và runtime class thực sự cần restore.

**Bước 4 — Đối chiếu vendor support.** Loại các tổ hợp không được hỗ trợ và ghi rõ phần chưa rõ.

**Bước 5 — Tạo checkpoint artifact bất biến.** Lưu checksum và metadata liên kết với JAR, container image digest và source profile.

**Bước 6 — Chạy restore matrix.** Thử từng source-target pair bắt buộc bằng checkpoint thật trên môi trường tương ứng.

**Bước 7 — Kiểm tra ứng dụng.** Xác nhận callback, external reconciliation, functional smoke test, readiness và hiệu năng.

**Bước 8 — Ghi kết quả và bằng chứng.** Phân loại VERIFIED, PARTIALLY_VERIFIED, UNTESTED, UNSUPPORTED, FAILED hoặc BLOCKED.

**Bước 9 — Áp dụng release gate.** Chỉ publish checkpoint cho target profiles đã đạt policy. Nếu target chưa được kiểm chứng, dùng fresh startup hoặc chặn deploy.

**Bước 10 — Theo dõi drift.** Khi JDK, engine, kernel, CPU, container runtime hoặc native library thay đổi, so sánh fingerprint và lên lịch retest.

**Bước 11 — Quản lý retention.** Giữ checkpoint, container image và report tương ứng trong thời gian rollback cần thiết; xóa artifact cũ theo policy.

## 19. Tiêu chí hoàn thành một môi trường VERIFIED

Một environment pair chỉ nên được đánh dấu VERIFIED khi tất cả điều kiện bắt buộc đã có bằng chứng:

- Vendor support không bị vi phạm.
- Checkpoint artifact toàn vẹn.
- Source và target profile được ghi đầy đủ.
- Restore process thành công trên target.
- Resource callback hoàn tất.
- External dependency được reconnect và reconcile.
- Functional smoke test đạt.
- Readiness chỉ bật sau khi validation xong.
- Không phát hiện side effect lặp hoặc state drift không xử lý.
- Thời gian restore và resource usage nằm trong giới hạn vận hành.
- Test report được lưu với checkpoint ID và pipeline run.

Nếu process restore thành công nhưng một kiểm tra nghiệp vụ chưa chạy, hãy giữ trạng thái PARTIALLY_VERIFIED. Nếu chưa có phép thử trên target, giữ UNTESTED. Trạng thái chính xác giúp đội triển khai biết mức độ rủi ro thay vì hiểu nhầm rằng image “chắc chắn chạy được”.

## Tài liệu tham khảo

- [CRaC — What CRaC is](https://crac.org/about/about-crac/): mô hình checkpoint/restore và giới hạn phụ thuộc môi trường.
- [CRaC — Running an Application With CRaC](https://docs.azul.com/crac/usage/running-crac): chuẩn bị runtime và chạy ứng dụng CRaC.
- [CRaC — CRaC Engines](https://docs.azul.com/crac/usage/crac-engines): các engine và sự khác biệt theo bản dựng.
- [CRaC — Debugging](https://crac.org/reference/debugging/): điều tra lỗi checkpoint/restore.
- [CRIU Documentation](https://criu.org/): yêu cầu và giới hạn checkpoint/restore process trên Linux.
- [Open Container Initiative — Image Format Specification](https://github.com/opencontainers/image-spec): metadata và định dạng container image.
- [Kubernetes — Container Runtimes](https://kubernetes.io/docs/setup/production-environment/container-runtimes/): runtime và tích hợp container trên node.
- [Linux man-pages — proc](https://man7.org/linux/man-pages/man5/proc.5.html): thông tin process và các interface trong procfs.
- [Linux man-pages — uname](https://man7.org/linux/man-pages/man2/uname.2.html): truy vấn thông tin kernel.
- [Java API — RuntimeMXBean](https://docs.oracle.com/en/java/javase/24/docs/api/java.management/java/lang/management/RuntimeMXBean.html): thông tin runtime và input arguments của JVM.

