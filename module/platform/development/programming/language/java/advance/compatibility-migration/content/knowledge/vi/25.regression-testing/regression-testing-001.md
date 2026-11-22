# Lập ma trận JDK, nhà cung cấp, hệ điều hành và kiến trúc cần hỗ trợ

## 1. Vì sao kiểm thử hồi quy khi nâng JDK cần một ma trận?

Một ứng dụng Java có thể chạy tốt trên JDK 17 tại máy phát triển nhưng gặp lỗi khi triển khai trên JDK 21 ở production. Khác biệt không chỉ nằm ở hai con số 17 và 21. JDK có **bản phân phối/nhà cung cấp**, bản cập nhật vá lỗi, hệ điều hành, kiến trúc CPU, cấu hình container, bộ thư viện native và tham số JVM đi kèm.

Ví dụ:

- CI chạy Eclipse Temurin trên Linux `x86_64`, nhưng production chạy một bản phân phối JDK khác trên Linux `aarch64`.
- Unit tests chạy JDK 21 trên Windows, nhưng ứng dụng deploy trên Linux Alpine với `musl` thay vì `glibc`.
- Driver JNI cung cấp bản native cho Linux x64 nhưng thiếu Linux ARM64.
- Ứng dụng dùng mã hóa TLS và truststore; một JDK distribution/OS image khác có root certificates hoặc security configuration khác.
- Tracing agent hoạt động ở JDK 17 nhưng chưa được vendor công bố hỗ trợ JDK mục tiêu.
- Class Java tương thích nhưng một thư viện sinh bytecode không hiểu class-file major version mới.
- Test xanh trên macOS Apple Silicon vì Java chạy qua Rosetta/x64; production ARM64 thuần lại có hành vi native khác.

Vì vậy, câu hỏi “đã test Java 21 chưa?” quá chung chung. Cần hỏi chính xác hơn:

> Đã chạy **artifact nào**, với **JDK vendor/build nào**, trên **OS/architecture nào**, bằng **runtime image và dependency set nào**, theo **bộ kiểm thử nào**, và **kết quả có thuộc phạm vi hỗ trợ chính thức không**?

Một **ma trận tương thích** trả lời những câu hỏi đó. Nó giúp phân biệt giữa **tổ hợp được sản phẩm cam kết hỗ trợ** và **tổ hợp chỉ được kiểm tra tham khảo**, đồng thời biến tuyên bố “Java compatible” thành bằng chứng có thể tái lập.

## 2. Mục tiêu của ma trận không phải kiểm thử mọi thứ bằng mọi cách

Nếu lấy 3 JDK releases × 3 vendors × 3 OS × 2 architectures, đã có 54 tổ hợp lý thuyết, chưa tính patch versions, libc, JVM flags, application server, driver, agents và database.

Không phải tổ hợp nào cũng tồn tại dưới dạng binary được nhà cung cấp hỗ trợ. Cũng không phải mọi tổ hợp đều cần chạy toàn bộ end-to-end suite.

**Mục tiêu đúng** là:

1. Xác định những platform thực sự được sản phẩm **hứa hỗ trợ**.
2. Loại trừ có lý do những tổ hợp không có distribution hoặc nằm ngoài support policy.
3. Chọn các thử nghiệm có khả năng phát hiện lỗi hồi quy quan trọng.
4. Đảm bảo mọi **tổ hợp production hoặc release-blocking** được kiểm tra đủ sâu.
5. Chạy những kiểm thử bổ sung để phát hiện tương tác giữa JDK, vendor, OS và architecture.
6. Lưu bằng chứng gồm phiên bản, binary, image, test report và timestamp.
7. Đặt tiêu chí chặn release rõ ràng; không coi “test đã chạy” là đồng nghĩa “được hỗ trợ”.

Ma trận là **hợp đồng về phạm vi hỗ trợ và quy trình kiểm chứng**, không phải bảng trang trí với các ô xanh.

## 3. Những chiều chính của ma trận

| Chiều | Ví dụ | Rủi ro mà chiều này giúp phát hiện |
| --- | --- | --- |
| JDK feature release | Java 8, 11, 17, 21 | API removal, class-file version, GC/JIT, module encapsulation |
| JDK update/build | 17.0.x, 21.0.x, build cụ thể | Bản vá, regression, thay đổi security defaults |
| JDK distribution/vendor | Temurin, Corretto, Zulu, Oracle JDK, Microsoft, Semeru, Liberica... | Packaging, JVM implementation, truststore/provider, support policy |
| JVM implementation | HotSpot-family, OpenJ9 hoặc runtime được hỗ trợ khác | JIT/GC/JVM options, attach, diagnostics, native integration |
| Operating system | Linux, Windows, macOS | Native loader, file paths, encoding, process model |
| OS release/image | Ubuntu/RHEL/Alpine/Windows build/macOS release | libc, certificates, system packages, permissions |
| CPU architecture | x86_64/amd64, aarch64/arm64 | JNI binaries, calling convention, CPU intrinsics |
| Runtime environment | Bare metal, VM, container, Kubernetes | cgroup limits, PID namespaces, startup flags, native libraries |
| Packaging/loading mode | Classpath, module path, fat JAR, jlink image | Class loading, modules, resource/service lookup |
| Dependencies/agents | JDBC, JNI/JNA, HTTP client, APM, coverage | Bytecode/native/runtime compatibility |
| Application workload | Request APIs, batch, messaging, encryption, persistence | Chức năng thực sự và non-functional regression |

Chiều **JDK feature release** và **JDK update version** phải được tách. Ghi “Java 21” không đủ để tái hiện một lỗi do bản vá hoặc vendor build.

## 4. Phân biệt bốn loại “hỗ trợ”

Một tổ hợp có thể chạy được nhưng chưa được cam kết cho khách hàng. Cần gắn nhãn rõ:

| Loại | Ý nghĩa | Hệ quả đối với release |
| --- | --- | --- |
| **Supported** | Nằm trong policy chính thức của sản phẩm, có owner và kế hoạch kiểm thử | Có thể chặn release nếu không đạt |
| **Validated** | Đã kiểm thử thành công với build và suite cụ thể | Là bằng chứng tại thời điểm test, không tự thành cam kết dài hạn |
| **Experimental** | Thử để phát hiện rủi ro hoặc chuẩn bị mở rộng hỗ trợ | Thường không chặn release trừ khi được quy định |
| **Unsupported** | Ngoài policy, EOL, không có binary được hỗ trợ hoặc tổ hợp không hợp lệ | Không được trình bày như đã xác nhận |

Có thể thêm **Untested** cho tổ hợp nằm trong phạm vi hỗ trợ nhưng chưa có bằng chứng. Đó là khoảng trống cần giải quyết, không phải trạng thái pass.

### 4.1. Tách vendor support và application support

Nhà cung cấp JDK công bố một distribution chạy trên OS/CPU nào đó không có nghĩa **ứng dụng của bạn** tự động hỗ trợ tổ hợp ấy. Ngược lại, việc ứng dụng vượt qua một số tests trên distribution không được nhà cung cấp bảo trì cũng không thay thế chính sách support/EOL.

Tổ hợp đưa vào production nên đáp ứng **cả hai phía**: binary/runtime được hỗ trợ theo chính sách đã duyệt và ứng dụng có bằng chứng kiểm thử.

## 5. Xác định phạm vi hỗ trợ từ sản phẩm trước khi thiết kế CI

Không nên bắt đầu bằng danh sách runner mà GitHub Actions hoặc một CI provider đang có. Hãy bắt đầu từ **người dùng và deployment thực tế**:

- Ứng dụng chỉ chạy trên container do tổ chức phát hành hay khách hàng tự cung cấp JDK?
- Đó là ứng dụng server, desktop application, SDK/library hay công cụ CLI?
- Khách hàng còn sử dụng JDK 11/17 hay đã cam kết tối thiểu Java 21?
- Có khách hàng chạy Windows Server, Linux ARM64 hoặc macOS không?
- Có phân phối native binaries theo OS/CPU không?
- Có cam kết cho nhiều JDK vendors hoặc chỉ một distribution đã duyệt?
- Có yêu cầu FIPS, custom truststore, proxy, LDAP/Kerberos hoặc smart card không?
- Có cần hỗ trợ rolling deployment giữa các JVM versions khác nhau không?
- Có thể rollback sau khi producer mới đã ghi dữ liệu hay thay protocol không?

Một backend hoàn toàn chạy trong Kubernetes Linux AMD64 do nhóm kiểm soát có ma trận khác một SDK thương mại phát hành cho Windows/macOS/Linux đa kiến trúc.

### 5.1. Ba nhóm phạm vi nên ghi rõ

**Production baseline:** Những tổ hợp thực tế đang chạy và phải tiếp tục đúng trong migration.

**Target supported:** Những tổ hợp được hứa hỗ trợ sau cutover; là cổng release chính.

**Exploratory/forward-looking:** Những tổ hợp dùng để phát hiện rủi ro trước, ví dụ một JDK feature release mới hoặc architecture mà thị trường có thể cần.

Không trộn test exploratory chưa pass vào báo cáo “tất cả platform được hỗ trợ đã pass”.

## 6. Xây support policy với lifecycle rõ ràng

Ví dụ một chính sách minh họa cho server Java:

~~~text
Application: orders-service
Current supported runtime: JDK 17 on approved Linux image
Target supported runtime: JDK 21 on approved Linux images
Allowed vendors: Temurin and Corretto, subject to validated binaries
Architectures: linux/amd64; linux/arm64 after native dependency validation
Unsupported: JDK 8/11, desktop OS and unapproved runtime images
JDK patch policy: approved security update baseline
Test policy: production combinations are release-blocking
Review cadence: each JDK security-update cycle and OS-image change
Owner: runtime-platform and service team
~~~

Đây chỉ là **ví dụ**, không phải đề xuất vendor hay mức JDK áp dụng cho mọi tổ chức.

### 6.1. Feature release và update release

Mức 21 là một feature release. Các bản 21.0.x có thể khác nhau về security fixes, certificate handling, performance hoặc bug fixes. Ma trận cần có:

~~~text
jdk_feature: 21
jdk_full_version: 21.0.x+build
vendor_distribution: ...
jvm_implementation: ...
image_digest: sha256:...
~~~

Khi pin một baseline patch, cần cập nhật chính sách security patches hợp lý thay vì giữ mãi một bản cũ. Việc chọn patch mới phải kích hoạt lại bộ kiểm thử phù hợp.

### 6.2. Không ghi “LTS = hỗ trợ mãi mãi”

Các JDK LTS có chính sách update và support khác nhau theo nhà cung cấp, license và thời hạn. Một feature release được gọi là LTS không tự đảm bảo artifact có thể nhận bản vá vô hạn. Cần xem lifecycle/support contract của đúng distribution và phiên bản.

## 7. JDK vendor: vì sao “Java giống nhau” nhưng vẫn cần test?

Những bản phân phối JDK cùng feature release thường tuân thủ Java SE platform compatibility, nhưng các chi tiết triển khai/vận hành vẫn có thể khác:

- JVM implementation và cách tối ưu JIT/GC.
- Cấu hình mặc định, build flags hoặc patch set.
- Certificates/truststore, CA list và security provider setup theo distribution/image.
- Packaging, filesystem layout, bộ công cụ `jcmd`/`jfr`/`jlink` có mặt.
- License, update cadence và support window.
- Hỗ trợ OS/CPU architecture.
- Diagnostic flags, JVM crash signatures và native integration.
- Có hay không những tính năng/value-add của vendor.

Ví dụ những distribution thường được gặp:

| Distribution | Điều cần xác minh |
| --- | --- |
| Eclipse Temurin | Release/build, supported OS/arch, HotSpot packaging, update policy |
| Amazon Corretto | Build cụ thể, OS/architecture support, update policy |
| Azul Zulu | Phiên bản, JVM variant/configuration, supported platforms |
| Oracle JDK | Distribution/build/license/support terms, supported platforms |
| Microsoft Build of OpenJDK | Release/build, supported OS/CPU, support commitments |
| IBM Semeru | Runtime implementation variant, features/flags, OS/CPU support |
| BellSoft Liberica | Distribution variant, package contents, supported platforms |
| GraalVM-based runtime | JDK compatibility, runtime mode, native image khác JVM execution |

Bảng trên không khẳng định mọi distribution luôn phát hành mọi JDK/OS/architecture. **Chỉ đưa một ô vào ma trận khi binary tương ứng tồn tại và được vendor công bố/được tổ chức duyệt**.

### 7.1. Không đánh đồng vendor với JVM implementation

“Vendor khác” chưa chắc đồng nghĩa JIT/GC implementation khác; nhiều distribution dựa trên HotSpot. Ngược lại, một distribution có lựa chọn JVM khác như OpenJ9 có thể thay đổi options, diagnostics và behavior vận hành.

Vì vậy cần ghi **distribution + JVM implementation** thay vì một cột “vendor” rồi suy ra hết.

### 7.2. Quy tắc chọn vendors đại diện

Nếu production chỉ dùng một distribution được duyệt, tổ hợp đó phải được test sâu. Nếu library/SDK tuyên bố vendor-neutral, nên có một nhóm representative vendors có tính khác biệt thực, và xác định giới hạn của lời cam kết.

Không test mọi vendor hàng ngày chỉ để tạo cảm giác đầy đủ, nhưng cũng không tuyên bố “chạy trên mọi JDK vendor” khi chỉ có bằng chứng từ một build duy nhất.

## 8. Operating system: không chỉ là tên Linux, Windows, macOS

Một ma trận ghi `Linux` là chưa đủ, nhất là khi ứng dụng có JNI/JNA, native agents hoặc tương tác filesystem.

Những khác biệt quan trọng:

- OS distribution và release.
- Bộ thư viện C (`glibc` hay `musl` trên Linux).
- Kernel version và container runtime.
- Filesystem case sensitivity, path separators và permissions.
- Default charset/locale/timezone, khi cách vận hành/configuration khác.
- Named pipes, sockets, file locks và process signals.
- TLS certificate stores, native crypto providers, keystores.
- Quy tắc native dynamic linker và shared library dependencies.
- Scheduler, threads, memory allocation và resource limits.
- Quyền attach/debug/profiling.

### 8.1. Linux `glibc` và `musl`

Một native library được build cho Linux `glibc` không mặc nhiên chạy trên Alpine Linux `musl`. Khi đổi Docker base image để nâng JDK, có thể đồng thời thay ABI nền tảng.

Ví dụ một lỗi:

~~~text
java.lang.UnsatisfiedLinkError:
  /app/native/libcodec.so: error loading shared library ...
~~~

Đừng quy ngay lỗi cho JDK 21 nếu JDK upgrade cũng chuyển image từ Debian sang Alpine.

### 8.2. Windows

Kiểm thử nên xét:

- Windows edition/build thực tế.
- DLL search behavior và Microsoft runtime dependencies.
- File path với dấu cách, drive letters, separator.
- File locking và khả năng xóa/đổi tên khi file đang mở.
- Process creation, service account privileges, charset.
- Native binaries đúng `x64` hoặc `arm64`.

Không dùng kết quả Linux để suy ra behavior của một SDK có cam kết Windows.

### 8.3. macOS

Phân biệt Apple Silicon `arm64` và Intel `x86_64`, architecture thực tế của JVM/CLI, các binary slices, code signing và native dependencies.

Một máy Apple Silicon có thể chạy JDK x64 dưới Rosetta. Khi đó test đã sử dụng binary x64 emulation, **chưa phải** bằng chứng arm64-native support.

## 9. Kiến trúc CPU: x64 và ARM64 là hai tổ hợp riêng

Java bytecode có tính portable, nhưng toàn ứng dụng có thể không:

- JNI/JNA/native libraries phải có binary đúng CPU.
- APM, profiler, native transport và compression libraries có thể sử dụng binary riêng.
- Calling conventions, alignment, word size và endian assumptions ảnh hưởng native code.
- CPU instruction sets và vectorization có thể thay JIT behavior/performance.
- Atomic operations, memory fences và concurrency timing có thể khác.
- Docker image phải có manifest/platform tương ứng.
- JVM flags liên quan CPU architecture có thể không tồn tại hoặc không có cùng ý nghĩa.

### 9.1. Ví dụ biểu diễn architecture

~~~text
Linux x86_64    ~ linux/amd64
Linux aarch64   ~ linux/arm64
Windows x64     ~ windows/amd64
macOS arm64     ~ darwin/arm64
~~~

Đây là tên thường dùng trong một số toolchain, không phải tên được mọi API sử dụng giống hệt. `os.arch` có thể báo `amd64`, `x86_64` hoặc `aarch64` tùy JVM. Nên **chuẩn hóa giá trị để so sánh** nhưng giữ lại giá trị gốc trong test evidence.

### 9.2. Không chỉ nhìn `uname -m`

Một shell chạy trên host ARM64 nhưng container/JVM có thể sử dụng binary khác hoặc cơ chế emulation. Hãy ghi:

- Host architecture.
- Container platform.
- JVM `os.arch` và JVM build.
- Architecture của native library thực sự được nạp.

Nếu những giá trị này không cùng ý nghĩa như mong đợi, báo cáo test phải nêu rõ thay vì gắn nhãn “native ARM64 pass”.

## 10. Container image: một chiều có thể phải tách riêng

Với deployment container, test ma trận JDK/vendor/OS/arch tốt nhất thường dựa trên **image digest**, không chỉ tên tag:

~~~text
registry.example/orders:java21
registry.example/orders@sha256:<immutable-image-digest>
~~~

Tag có thể được cập nhật và trỏ sang manifest khác, trong khi digest giúp xác định artifact image đã chạy. Một multi-arch image có manifest list/index và các child manifests; khi cần truy nguyên lỗi native, lưu cả image reference/digest và platform đã chọn.

### 10.1. Cấu hình container ảnh hưởng JVM

- Giới hạn CPU/memory qua cgroups.
- User ID, permissions, filesystem read-only.
- `/tmp` và thư mục dump/log có quyền ghi không.
- Container/PID namespaces và attach mechanism.
- Certificate store, timezone data, DNS configuration.
- Native libs có trong base image.
- `JAVA_TOOL_OPTIONS`, `JDK_JAVA_OPTIONS` và entrypoint.
- JVM agent hoặc instrumentation do platform inject.

Vì vậy “test JDK 21 Linux AMD64” phải chỉ ra **test trong image production tương ứng hay test bằng JDK cài trên CI runner**. Hai kết quả không thay thế nhau.

### 10.2. Distroless, slim và `jlink` images

Image tối giản có thể thiếu shell, command-line diagnostics hoặc JDK modules/provider đã từng có trong full JDK. Nếu ứng dụng dùng ServiceLoader, reflection, TLS hoặc JNI, cần test trực tiếp trên runtime image cuối.

Không coi `java -version` trong full JDK container là bằng chứng một `jlink` runtime image có đủ modules.

## 11. Những chiều thường bị bỏ sót ngoài bốn trục chính

Để ma trận có giá trị, đôi khi phải ghi các chiều thứ cấp:

| Chiều thứ cấp | Ví dụ | Khi nào ưu tiên |
| --- | --- | --- |
| Compiler JDK và `--release` | JDK 21, `--release 17` | Library/SDK duy trì Java minimum |
| Runtime Java flags | GC, memory, `--add-opens` | JVM migration/agent/tooling |
| Application framework | Spring, Jakarta, Quarkus, custom | Framework major upgrade đồng thời |
| Database/driver | Vendor DB, JDBC version, TLS | Backend persistence |
| Network/security | TLS protocol, cipher, FIPS policy | Regulated/secure services |
| Native/agent versions | JNI, Netty native, APM | OS/architecture variants |
| Packaging | JAR, fat JAR, module path, `jlink` | Libraries, modules và launchers |
| Workload | CPU-bound, I/O-bound, latency-sensitive | Non-functional regression |
| Cloud/instance type | ARM vs x86 node, VM family | Runtime performance/architecture |

Không nhất thiết biến mọi chiều thành tích Descartes khổng lồ. Hãy **gắn các chiều thứ cấp vào test case hoặc nhóm tương thích** khi chúng có khả năng thay đổi kết quả.

## 12. Quy tắc chọn các tổ hợp hợp lệ

Một tổ hợp chỉ nên được lên lịch nếu:

1. JDK vendor phát hành binary cho release/OS/architecture đó.
2. Binary thuộc phạm vi hỗ trợ hoặc có lý do thử nghiệm.
3. CI runner/container có thể chạy đúng architecture, không bị emulation ngoài ý muốn.
4. Ứng dụng và native dependencies có thể được đóng gói cho môi trường đó.
5. Có bộ test thích hợp và test evidence lưu được.
6. Nếu là production-supported, có owner xử lý regression.

Ví dụ giả định:

~~~text
JDK 21 × Vendor A × Linux x64   => Supported + mandatory
JDK 21 × Vendor A × Linux arm64 => Supported after JNI validation
JDK 21 × Vendor B × macOS x64   => Experimental CLI
JDK 17 × Vendor A × Windows arm64 => Unsupported by product policy
~~~

Nhãn ở đây chỉ là minh họa về **phương pháp phân loại**, không khẳng định vendor A/B có hỗ trợ binary cụ thể.

### 12.1. “Không có runner” khác “không hỗ trợ”

Nếu sản phẩm hứa hỗ trợ một OS/arch mà CI hiện chưa có runner, đó là **testing coverage gap**. Không được chuyển nó thành “unsupported” chỉ để báo cáo xanh nếu hợp đồng sản phẩm chưa thay đổi. Cần bổ sung runner, quy trình kiểm thử thủ công được kiểm soát, hoặc thay đổi support policy có phê duyệt.

## 13. Mẫu bảng ma trận mức sản phẩm

Giả sử ứng dụng server đang chuyển từ JDK 17 sang JDK 21:

| ID | JDK | Distribution | OS/image | Arch | Support | CI depth |
| --- | --- | --- | --- | --- | --- | --- |
| P01 | 17 latest-approved patch | Temurin | Linux glibc image A | amd64 | Baseline supported | Full |
| P02 | 21 latest-approved patch | Temurin | Linux glibc image B | amd64 | Target supported | Full |
| P03 | 21 latest-approved patch | Corretto | Linux glibc image B | amd64 | Target supported nếu được duyệt | Full |
| P04 | 21 latest-approved patch | Temurin | Linux glibc image B | arm64 | Target candidate | Native + integration |
| P05 | 21 latest-approved patch | Temurin | Linux musl image C | amd64 | Experimental | Smoke + native |
| P06 | 21 latest-approved patch | Temurin | Windows image D | x64 | Outside server policy | Optional CLI test |

Tên images và support labels là dữ liệu giả định để minh họa. **Không kết luận P03/P04 được hỗ trợ trước khi vendor/platform và ứng dụng xác nhận.**

### 13.1. Cột bắt buộc nên có

Tối thiểu:

~~~text
matrix_id
application_artifact_or_commit
jdk_feature
jdk_full_version_and_build
distribution
jvm_implementation
os_name_and_version
libc_or_base_image
cpu_architecture
deployment_mode
support_status
test_profile
expected_result
owner
evidence_link_or_artifact_id
last_validated_at
~~~

Thêm JDK flags, native/agent versions và container digest khi có rủi ro liên quan.

## 14. Phân tầng mức kiểm thử để tránh chi phí nổ theo tích số

Không cần chạy 20 giờ end-to-end trên mọi ô. Có thể chia profile:

| Profile | Bao gồm | Khi áp dụng |
| --- | --- | --- |
| **Compile/API** | Build, bytecode target, API diff, dependency resolution | Tất cả artifact/target release |
| **Smoke** | Startup, health, route quan trọng, class loading | Hầu hết tổ hợp hợp lệ |
| **Core regression** | Unit, integration chính, serialization, TLS/DB | Tất cả production-supported |
| **Native/agent** | JNI/JNA, drivers, profilers, bytecode instrumentation | Tổ hợp OS/CPU/JDK có native |
| **Full E2E** | Business workflows, migration scenarios, persistence | Production/reference environments |
| **Non-functional** | Startup, memory, GC, p95/p99, throughput | Representative/critical platforms |
| **Exploratory** | New JDK, vendor, OS, architecture | Không mặc định release-blocking |

Chọn profile theo **rủi ro**, không chỉ phân phối đều cho đẹp. Nếu Linux ARM64 là một môi trường production có JNI và yêu cầu latency khắt khe, nó cần core regression + native + non-functional thích hợp, dù chi phí cao hơn.

### 14.1. Quy tắc chặn release

Ví dụ:

~~~text
Release blocked when:
  - any mandatory production matrix row has failed or not-run core tests
  - any mandatory native/agent validation has failed
  - API compatibility contract is broken
  - security-critical TLS/crypto tests fail
  - a mandatory platform has no trustworthy test evidence
  - severe unresolved performance or stability regression exceeds policy
~~~

Không coi “chưa chạy” là pass. Nếu bỏ qua một ô bắt buộc vì sự cố runner, trạng thái phải là **blocked/unknown** theo policy, chứ không tự đổi sang xanh.

## 15. Risk-based selection và pairwise testing

Khi số tổ hợp lớn, **pairwise testing** (bao phủ từng cặp giá trị của các chiều) có thể tìm một số lỗi tương tác trong khi giảm số ca so với full Cartesian product.

Ví dụ các chiều:

~~~text
JDK: 17, 21
Vendor: Temurin, Corretto
OS: Linux, Windows, macOS
Arch: x64, arm64
~~~

Không phải mọi OS/arch/vendor đều có binary hợp lệ. Trước khi chạy pairwise, phải **lọc theo constraints**. Một pairwise generator không biết constraints có thể sinh testcase không thể triển khai.

### 15.1. Khi pairwise hữu ích

- Rà soát tương tác JDK × vendor, vendor × OS, OS × arch.
- Chọn tập smoke/integration đại diện.
- Mở rộng phạm vi của những môi trường không phải sản xuất trọng yếu.
- Giảm thời gian cho PR checks trong khi giữ full matrix ở nightly/release.

### 15.2. Khi pairwise là không đủ

- Mọi tổ hợp production đã cam kết phải có bằng chứng theo policy.
- Native library chỉ lỗi với bộ ba JDK 21 × ARM64 × musl.
- TLS provider/FIPS phụ thuộc cả vendor, OS và policy.
- Multi-agent/bytecode instrumentation có tương tác 3–4 yếu tố.
- Rủi ro security/compliance yêu cầu certification cụ thể.

Do đó nên kết hợp:

1. **Mandatory full coverage** cho các tổ hợp production-critical.
2. **Constraint-aware pairwise** cho phần hỗ trợ mở rộng.
3. **Targeted high-order tests** cho các tương tác có rủi ro cao.
4. **Exploratory tests** khi có JDK/OS/vendor mới.

Không dùng pairwise để thay thế trách nhiệm support.

## 16. Ưu tiên theo mức rủi ro và tác động

Một mô hình xếp ưu tiên đơn giản:

| Tier | Điều kiện | Hướng test |
| --- | --- | --- |
| P0 | Production đang chạy hoặc yêu cầu pháp lý/bảo mật | Full release-blocking |
| P1 | Target migration, native/agent/TLS quan trọng | Core + targeted deep tests |
| P2 | Supported noncritical consumer footprint | Smoke + contract + representative integration |
| P3 | Experimental/new platform | Exploratory và documentation |

Tổ hợp có thể tăng tier theo evidence:

- Lỗi production từng xảy ra ở architecture đó.
- Vendor phát hành JVM build có thay đổi quan trọng.
- Image đổi libc hoặc certificate store.
- Một dependency native chưa có support matrix.
- Dự án dùng custom class loader, JPMS hoặc `jlink`.
- Có nhiều external consumers hoặc rollback phức tạp.

### 16.1. Không đánh giá chỉ theo độ phổ biến

Một môi trường chỉ chiếm 5% traffic nhưng là kênh thanh toán có yêu cầu chính xác cao có thể cần P0. Ngược lại một OS ít được dùng ở tool nội bộ có thể chỉ yêu cầu smoke. Độ ưu tiên phải phản ánh **impact × likelihood × khả năng phát hiện**, không chỉ số người dùng.

## 17. Baseline, target và phép thử tách nguyên nhân

Một migration JDK thường đổi nhiều yếu tố cùng lúc: JDK, framework, image, libraries và agent. Nếu chỉ chạy trạng thái đầu/cuối, rất khó xác định tác nhân khi regression xuất hiện.

Ma trận đối chứng:

| Case | JDK | Dependency graph | Runtime image | Mục đích |
| --- | --- | --- | --- | --- |
| A | Old | Old | Old | Baseline |
| B | New | Old | Old-equivalent | Tách tác động JDK, nếu tổ hợp hợp lệ |
| C | Old | New | Old-equivalent | Tách tác động libraries, nếu còn hỗ trợ JDK cũ |
| D | New | New | Old-equivalent | Đánh giá JDK + dependency |
| E | New | New | New target image | Kiểm tra triển khai cuối |

**Không phải mọi ô đều chạy được.** Ví dụ framework mới có minimum Java 21 khiến case C không hợp lệ; ghi “unsupported combination” thay vì cố ép chạy.

Nếu B fail nhưng D pass, bản nâng dependency có thể đã xử lý JDK blocker. Nếu D pass nhưng E fail, điều tra OS image, libc, permissions, TLS certs hoặc native packaging thay vì quy ngay cho JDK.

## 18. Build JDK, compiler JDK và runtime JDK phải ghi riêng

Trong Java build hiện đại có thể có:

- JDK chạy Maven/Gradle daemon.
- JDK compiler toolchain.
- `--release`/source/API target.
- Test JVM.
- JVM của application/container.

Ví dụ:

~~~text
Gradle daemon:      JDK 21
Compiler toolchain: JDK 21
javac --release:   17
JUnit on Java 17:  mandatory
JUnit on Java 21:  mandatory
Production floor:  Java 17
~~~

Điều này hợp lệ cho một library muốn tiếp tục hỗ trợ Java 17. Nhưng không được suy ra rằng test chạy Java 21 đã chứng minh compatibility Java 17 chỉ vì compiler dùng `--release 17`.

### 18.1. `--release` kiểm soát gì?

`javac --release N` giới hạn ngôn ngữ, Java platform API và bytecode theo release `N` được compiler hỗ trợ. Nó **không kiểm tra mọi third-party dependency** có class-file version/runtime minimum phù hợp và không thay runtime execution tests.

### 18.2. Toolchain version khác build daemon version

Gradle version có khả năng chạy trên JDK mới hay chưa là chuyện khác với Gradle có thể dùng JDK ấy để compile/test qua toolchains. Với Maven, toolchains cũng khác JVM chạy Maven. Ma trận cần lưu cả hai để tái hiện lỗi compiler plugin hoặc processor.

## 19. Ma trận JVM vendors cần kiểm chứng gì?

Một suite vendor comparison nên kiểm tra:

1. Startup, classpath/module path và Java agent initialization.
2. Security providers, truststore, key/trust management, TLS negotiation.
3. Reflection, strong encapsulation và JVM flags mà app dùng.
4. Garbage collector/JIT options có được runtime hỗ trợ không.
5. Thread scheduling và concurrency liveness/correctness.
6. Native JNI/JNA libraries và JVM TI agents nếu có.
7. Performance baseline trên cùng workload/hardware.
8. Diagnostic tooling, crashes, logs và supportability.
9. ServiceLoader và provider discovery trong runtime image.
10. Runtime packaging, CA certificates và system properties.

### 19.1. Kiểm tra JVM implementation

Chạy:

~~~bash
java -version
java -XshowSettings:properties -version
~~~

Các output có thể chứa:

~~~text
java.vendor
java.vendor.version
java.version
java.runtime.version
java.vm.name
java.vm.vendor
java.vm.version
os.name
os.arch
os.version
~~~

Lưu cả output và artifact provenance; một property đơn lẻ không xác minh đủ distribution binary/build.

### 19.2. Không áp đặt JVM flags của một implementation lên mọi vendor

GC, compiler flags, diagnostic options hoặc native profiling support không phải lúc nào cũng giống nhau giữa các JVM implementations. Nếu một bộ startup flags chỉ phù hợp HotSpot, cần:

- Giới hạn support policy đến JVM implementation đó, hoặc
- Có cấu hình được lựa chọn theo runtime với kiểm thử tương ứng.

Không coi một warning “unrecognized VM option” là bug của ứng dụng; đó có thể là cấu hình JVM không portable.

## 20. OS và architecture: những bộ test nên chạy

### 20.1. Filesystem và process

- Path separators, Unicode filenames, symlinks.
- Case sensitivity, file locking và permission errors.
- Temporary directories và read-only filesystem.
- Child process creation, termination, stdout/stderr encoding.
- File watcher event behavior và quotas.

### 20.2. Network và security

- TLS handshake/certificate validation với endpoints thử nghiệm.
- Proxy/DNS/IPv4/IPv6 nếu nằm trong phạm vi deployment.
- HTTP/2, keepalive, connection pool và timeouts.
- Keystore/truststore initialization, algorithm availability.
- Clock/timezone/datetime representation.

### 20.3. Native integration

- JNI/JNA binary thực sự được load.
- Native dependency search paths và glibc/musl.
- Compression/crypto libraries, epoll/kqueue/native transport.
- Signal handling, native profiler/agents.
- Off-heap buffer allocation/free và memory pressure.

### 20.4. Concurrency và performance

- Long-running workload trên CPU architecture thật.
- Thread pools, virtual threads nếu ứng dụng dùng.
- Atomic/volatile correctness under contention.
- Throughput, p95/p99 latency, GC, CPU steal/memory constraints.

Một test “Java app prints Hello World” chỉ giúp chứng minh launcher chạy; nó không đủ phát hiện những khác biệt trên.

## 21. JDK patch updates và security regression

JDK cập nhật có thể thay:

- TLS/protocol/cipher defaults.
- Certificate trust decisions.
- Security algorithm constraints.
- Timezone data hoặc locale data.
- Provider implementations.
- Native/JIT/GC bug fixes.
- JVM warnings/options behavior.

Không cần chạy full matrix trên mỗi pull request chỉ để theo dõi patch changes. Nhưng **khi cập nhật JDK baseline được triển khai**, cần suite tương ứng với rủi ro, nhất là TLS, crypto, serialized data và agent/tooling.

### 21.1. Chính sách update định kỳ

Một workflow:

~~~text
New approved JDK update available
            |
            v
Create updated immutable runtime image
            |
            v
Run mandatory compatibility matrix
            |
            v
Compare functional + nonfunctional baseline
            |
            v
Canary / staged rollout
            |
            v
Promote or rollback with documented evidence
~~~

Đừng dùng tag `latest` cho CI và production mà không lưu digest/build. Có thể hai nơi chạy hai binary khác nhau dưới cùng nhãn.

## 22. API/binary compatibility và runtime compatibility là hai cửa riêng

Với Java libraries, cần phân biệt:

- **Source compatibility:** consumer build lại với public API còn compile được?
- **Binary compatibility:** consumer đã compile có còn liên kết method/field/class không?
- **Java platform compatibility:** class-file major và Java SE APIs có phù hợp runtime thấp nhất không?
- **Behavioral compatibility:** cùng input và trạng thái có cho kết quả/hành vi đúng không?
- **Data/protocol compatibility:** dữ liệu/HTTP/serialization giữa phiên bản cũ mới có được xử lý đúng không?
- **Operational compatibility:** monitoring, diagnostics, resource budgets còn đáp ứng không?

Một class được compile với `--release 17` có thể chạy trên Java 21, nhưng một dependency native hoặc agent vẫn có thể fail. Ngược lại, runtime Java 17 không nạp class-file major 65 dù trên Java 21 source đã compile tốt.

### 22.1. Phân biệt lỗi thường thấy

| Lỗi | Điều tra trước |
| --- | --- |
| `UnsupportedClassVersionError` | Compiler release target và JVM runtime |
| `NoSuchMethodError` | Dependency graph, ABI và JAR thực tế |
| `InaccessibleObjectException` | Reflection/module access và tool/library |
| `UnsatisfiedLinkError` | Native binary, OS/CPU/ABI, `java.library.path` |
| `Unsupported class file major version` trong ASM/agent | Bytecode parser/tool version |
| TLS handshake failure | Certificates, providers, protocols, policy, network |
| OOMKilled | Container limits, heap/direct/native memory, GC/agents |

**Không kết luận lỗi Java language level** khi gốc là Alpine musl không nạp được native binary.

## 23. JNI, JNA và native libraries phải có ma trận riêng khi cần

Nếu ứng dụng dùng JNI/JNA, việc test ARM64 là một hoạt động khác test mã Java thuần:

~~~text
JDK distribution
    × OS image
    × CPU architecture
    × libc / native ABI
    × JNI library version
~~~

Nên tạo bảng native artifact:

| Artifact | OS | Arch | libc/ABI | Nguồn binary | Test |
| --- | --- | --- | --- | --- | --- |
| `libcodec.so` | Linux | amd64 | glibc | Vendor/build approved | Load + encode/decode |
| `libcodec.so` | Linux | arm64 | glibc | Vendor/build approved | Load + encode/decode |
| `nativecodec.dll` | Windows | x64 | Windows ABI | Vendor/build approved | Load + encode/decode |
| `libcodec.dylib` | macOS | arm64 | Mach-O | Vendor/build approved | Load + encode/decode |

Mỗi hàng phải được xác nhận binary tồn tại và hợp lệ. Không lấy một thư viện `.so` x64 rồi đổi tên file thành arm64.

### 23.1. Tests phải gọi chức năng native thật

Một library có thể nạp native code theo kiểu lazy. Unit test chỉ tạo DTO/bean sẽ pass mà chưa động tới `System.loadLibrary`. Với JNI, test cần thực thi path thực, kiểm tra kết quả, failure cases và memory/lifetime dưới tải phù hợp.

### 23.2. Kiểm tra Java/native artifact version alignment

Java wrapper và native library phải tương ứng với nhau. Một thay đổi JNI method signature có thể gây `UnsatisfiedLinkError` ngay cả khi OS loader nạp file thành công. Khi nâng JDK/image, không để một bản wrapper mới dùng binary cũ do cache hoặc đường dẫn deployment.

## 24. Java agents, JVMTI và test tooling cũng theo vendor/architecture

Các công cụ dễ bị bỏ sót:

- APM/tracing Java agents.
- Native JVMTI profilers.
- Coverage/mocking agents như instrumentation được dùng trong test.
- Class-file transformers dựa vào ASM/Byte Buddy.
- Debugger, attach tools và JFR integration.

Với JDK 21+, dynamic agent loading có bối cảnh cảnh báo từ JEP 451; trên release khác cần đối chiếu chính sách hiện hành của JVM. Một agent chạy được lúc startup bằng `-javaagent` không có nghĩa dynamic attach luôn được phép trong mọi container.

### 24.1. Không coi mất tracing là test pass

Sau JDK/vendor/image migration, app có thể trả HTTP 200 nhưng:

- Thiếu JDBC spans.
- Context propagation qua async threads sai.
- Crash/overhead khi profiling.
- Agent chỉ hỗ trợ x64, chưa hỗ trợ ARM64.
- Metrics names thay đổi khiến dashboard/alert không hoạt động.

Với hệ thống mà observability là yêu cầu vận hành, những lỗi này phải có checks riêng.

## 25. TLS, cryptography và compliance cần các ô bắt buộc

Trong hệ thống thanh toán, định danh hoặc kết nối mật mã, một tổ hợp JDK/vendor/OS có thể có truststore, provider setup, HSM/PKCS#11, policy hoặc FIPS configuration khác.

Kiểm thử nên bao phủ:

1. TLS handshake với certificates/cipher suites được duyệt.
2. Client/server certificate validation và mTLS.
3. Truststore/keystore format và password handling.
4. Key generation/signature/verification với providers thực.
5. Certificate chain, revocation checks khi được yêu cầu.
6. PKCS#11/HSM native provider hoặc FIPS mode nếu là yêu cầu.
7. Expired/invalid certificates và negative tests.
8. Tính đúng của dữ liệu đã ký/mã hóa qua các JDK versions.

Không dùng `-Djdk.tls.client.protocols=...` hoặc bỏ certificate verification như cách “làm cho test xanh” nếu không có phân tích bảo mật rõ ràng. Thay đổi này có thể làm mất chính sách bảo vệ quan trọng hơn mục tiêu migration.

### 25.1. Tách “có algorithm” khỏi “được phép sử dụng”

JDK distribution có thể cung cấp một thuật toán nhưng security policy của application/OS vô hiệu hóa hoặc hạn chế nó. Test phải xác minh **hợp đồng thực tế** chứ không chỉ `Security.getProviders()` có tên provider.

## 26. Tests cho localization, timezone và dữ liệu

Những tác động không hiển thị ở compile stage:

- Locale/collation, Unicode normalization, case folding.
- Timezone databases và DST transitions.
- Default charset nếu code không chỉ định encoding.
- Parsing/formatting số, tiền tệ và ngày giờ.
- Java serialization, JSON/XML/protobuf compatibility.
- Filesystem path encoding.
- Database timestamp/timezone mappings.

### 26.1. Không phụ thuộc môi trường mặc định ngoài ý muốn

Code:

~~~java
new String(bytes)
~~~

phụ thuộc default charset. Trong nhiều hệ thống hiện đại, UTF-8 là mặc định theo nền tảng Java mới, nhưng việc tương thích trên JDK cũ/OS khác vẫn cần được xét. Nếu contract quy định UTF-8, hãy chỉ định:

~~~java
new String(bytes, java.nio.charset.StandardCharsets.UTF_8)
~~~

Tương tự, nếu nghiệp vụ yêu cầu UTC, nên cấu hình/tham chiếu timezone rõ ràng thay vì kỳ vọng host OS luôn đúng.

### 26.2. Dữ liệu golden fixtures

Với serialization và protocol, tạo fixtures từ bản đã phát hành:

- Writer trên JDK cũ, reader trên JDK mới.
- Writer mới, reader cũ nếu rolling deployment/rollback yêu cầu.
- Input có `null`, missing field, enum chưa biết, dữ liệu lớn, ký tự Unicode và ngày DST.

Không tạo cả fixture “v1” và “v2” bằng cùng implementation mới rồi coi như đã kiểm tra backward compatibility.

## 27. Concurrency và hiệu năng có thể khác theo JVM và CPU

Nâng JDK hoặc đổi architecture có thể làm rõ những lỗi race condition vốn hiếm:

- Lock contention và thread scheduling.
- Parallel streams và fork-join behavior theo workload.
- Garbage collection pauses/throughput.
- Memory fences/atomic operations trong native integration.
- Virtual threads nếu ứng dụng dùng JDK hỗ trợ.
- Connection pool, executor saturation, backpressure.
- CPU vector instructions, cryptographic intrinsics.

### 27.1. Performance baseline cần cùng điều kiện

Khi so JDK17 với JDK21:

- Cùng application workload và input distribution.
- Cùng hardware/instance class nếu có thể.
- CPU/memory limits, JVM flags và agent settings được ghi lại.
- Warmup/JIT và cache state có phương pháp nhất quán.
- Mỗi phép đo có đủ repetitions và phân tích biến thiên.
- Quan sát latency percentiles, throughput, CPU, memory, GC và error rate.

Không kết luận “JDK mới nhanh hơn 20%” từ một lần chạy không kiểm soát, nhất là khi đồng thời đổi x86_64 sang ARM64 hoặc container image.

### 27.2. Chỉ số regression phải dựa trên SLO

Ví dụ policy minh họa:

~~~text
P0: business correctness is mandatory
P0: no new crash/OOM under reference workload
P1: p99 latency must stay within approved SLO
P1: native memory overhead monitored against budget
P2: startup time trend reviewed and recorded
~~~

Threshold thực tế phải do sản phẩm và SRE/QA thống nhất; không đặt số phần trăm tùy ý cho mọi dịch vụ.

## 28. Thiết kế CI matrix: cấu trúc trước, cú pháp sau

Nên có một **matrix definition** là nguồn dữ liệu được quản lý trong repository:

~~~yaml
matrix:
  - id: linux-amd64-jdk17-baseline
    jdk: "17"
    vendor: temurin
    os: linux
    arch: amd64
    profile: full
    support: baseline

  - id: linux-amd64-jdk21-target
    jdk: "21"
    vendor: temurin
    os: linux
    arch: amd64
    profile: full
    support: target

  - id: linux-arm64-jdk21-target
    jdk: "21"
    vendor: temurin
    os: linux
    arch: arm64
    profile: native-integration
    support: candidate
~~~

Đây là dữ liệu minh họa, không phải cú pháp bắt buộc của một CI provider. Giá trị vendor/image/build phải được kiểm tra theo distribution đã duyệt.

**Nguyên tắc quản trị:** một thay đổi support policy cần review như thay đổi code. Không tự bỏ một row đang fail khỏi matrix chỉ để pipeline xanh.

## 29. Ví dụ GitHub Actions cho tập CI đại diện

Ví dụ này dùng những runner labels và JDK distribution được dự án phải kiểm tra tính khả dụng tại thời điểm triển khai. Nó thể hiện cơ chế CI matrix, không khẳng định bao phủ mọi kiến trúc:

~~~yaml
name: Java compatibility

on:
  push:
  pull_request:

jobs:
  tests:
    strategy:
      fail-fast: false
      matrix:
        include:
          - os: ubuntu-22.04
            distribution: temurin
            java: "17"
          - os: ubuntu-22.04
            distribution: temurin
            java: "21"
          - os: windows-2022
            distribution: temurin
            java: "21"
          - os: macos-14
            distribution: temurin
            java: "21"

    runs-on: ${{ matrix.os }}

    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-java@v4
        with:
          distribution: ${{ matrix.distribution }}
          java-version: ${{ matrix.java }}
      - name: Record JDK
        run: java -version
      - name: Run regression tests
        run: ./mvnw -B verify
~~~

**Lưu ý nền tảng:** `./mvnw` có thể không chạy trực tiếp bằng cùng cách trên Windows runner, tùy wrapper files/shell; một workflow dùng đa OS cần lệnh thích hợp theo runner, chẳng hạn chọn `mvnw.cmd` cho Windows hoặc dùng một script portable. Ví dụ chỉ trình bày ý tưởng matrix và không thay việc kiểm chứng syntax/runner support trong repository thật.

### 29.1. Cần chứng minh architecture thật

Danh sách runner ở trên **không phải** coverage ARM64. Muốn test Linux ARM64, cần có runner/host ARM64 hoặc image/platform được đảm bảo thật, ví dụ self-hosted runner được quản lý và gắn label rõ.

Không thêm một giá trị `arch: arm64` vào matrix mà vẫn để job chạy trên host x64 rồi đánh dấu “ARM64 PASS”. Một parameter không đổi architecture của CPU.

### 29.2. Artifact provenance của GitHub Actions

Ngoài job result, nên lưu:

- `java -version` và các JVM properties.
- Container digest/OS/architecture evidence.
- Maven/Gradle versions và dependency graph khi cần.
- Test reports và logs.
- Artifact checksum và commit SHA.

Runner labels như `ubuntu-latest` có thể thay đổi OS release; với release-blocking validation, nên pin runner/image version hoặc lưu OS build đầy đủ.

## 30. Mẫu CI độc lập nền tảng khi cần nhiều providers

Nếu CI provider khác, nguyên tắc vẫn là:

~~~text
load approved-matrix.yml
for each row:
    verify runner provides real OS + CPU architecture
    provision approved JDK vendor/full build
    verify JDK/runtime image and artifact checksum
    run test profile for this row
    collect logs, reports and environment metadata
    apply gating policy
aggregate mandatory row results
publish compatibility evidence
~~~

Đặc biệt: bước **verify runner provides real OS + architecture** không được bỏ. Nếu CI tự chuyển qua QEMU/emulation, đó là điều kiện test khác và phải được ghi rõ.

### 30.1. Fail-fast và điều tra

Khi chạy matrix, việc tắt fail-fast giúp thu thập tất cả kết quả trong một lần. Nhưng điều này không có nghĩa lỗi nào cũng có thể bỏ qua. Cuối pipeline cần tổng hợp:

~~~text
P0 required:  PASS / FAIL / NOT_RUN
P1 targeted:  PASS / FAIL / NOT_RUN
P2 exploratory: PASS / FAIL / NOT_RUN
release decision: PASS only if policy requirements satisfied
~~~

Một row chưa chạy do runner unavailable cần trạng thái minh bạch.

## 31. Maven Toolchains và Gradle Java Toolchains trong ma trận

### 31.1. Maven

Maven Toolchains có thể chỉ định JDK cho compiler hoặc tool-aware plugins trong khi Maven process chạy trên JDK khác. Điều này hữu ích khi compile nhiều Java release targets, nhưng không tự đảm bảo JUnit fork đã chạy trên JDK mong đợi.

Khi tạo test matrix, xác minh:

~~~bash
mvn -version
./mvnw -version
~~~

Chỉ dùng command phù hợp repository. Bổ sung log compiler/test fork JVM và versions.

### 31.2. Gradle

Ví dụ toolchain Java 21 và release 17:

~~~groovy
plugins {
    id 'java'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

tasks.withType(JavaCompile).configureEach {
    options.release = 17
}
~~~

Đây là cách build artifact giữ Java 17 target. Để **chạy tests trên Java 17 và 21**, cần lựa chọn `Test.javaLauncher`/test tasks hoặc CI jobs phù hợp; một toolchain compiler không tự tạo test matrix.

### 31.3. Không dùng IDE SDK làm bằng chứng

IDE có thể dùng JDK 21 để code insight nhưng terminal/CI runtime khác. Cần lưu JDK của build daemon, compiler và test JVM trực tiếp từ runtime, thay vì dựa vào màn hình Project SDK.

## 32. Test JVM thật và image cuối: nguyên tắc kiểm chứng

Một report "Java 21 pass" phải có đủ:

~~~text
Artifact source commit:
Artifact SHA-256:
JDK distribution:
java.version:
java.runtime.version:
java.vm.name:
OS name/version:
Architecture:
Container image digest:
JVM arguments:
Test suite/profile:
Test count/passed/failed/skipped:
CI run ID:
Timestamp:
Owner:
~~~

### 32.1. Test skips không được ẩn

Test report có 1.000 cases, pass 900 và skipped 100 không tương đương “1.000 tests pass”. Nếu skipped cases bao gồm JNI ARM64 hoặc TLS security checks, đó có thể là một coverage gap làm chặn release.

Nên ghi **reason code** cho skip:

- Feature ngoài phạm vi platform.
- Có waiver được duyệt.
- Dependency/vendor binary không có.
- Runner hoặc service unavailable.
- Flaky/quarantined có owner và hạn xử lý.

Không coi skipped tests là bằng chứng hỗ trợ.

## 33. Đoạn Java nhỏ để ghi dấu môi trường

Một diagnostic helper có thể được chạy trước suite:

~~~java
import java.util.List;

public final class RuntimeFingerprint {
    public static void main(String[] args) {
        List<String> keys = List.of(
                "java.version",
                "java.runtime.version",
                "java.vendor",
                "java.vm.name",
                "java.vm.vendor",
                "java.vm.version",
                "os.name",
                "os.version",
                "os.arch");

        for (String key : keys) {
            System.out.println(
                    key + "=" + System.getProperty(key));
        }
    }
}
~~~

Ví dụ này dùng `List.of` nên cần Java 9+; nếu test floor Java 8, thay bằng `Arrays.asList` hoặc mảng chuỗi. Diagnostic helper không nên vô tình đòi JDK mới hơn phiên bản cần kiểm thử.

Ngoài các properties, nên thu thập OS distribution, container image digest và platform architecture bằng các công cụ infrastructure phù hợp. `System.getProperty("os.arch")` chưa đủ phát hiện emulation hoặc native binary architecture thực.

### 33.1. Tránh in secrets

`java -XshowSettings` và JVM arguments/log có thể chứa config nhạy cảm. Khi thu thập fingerprint cho CI, chọn trường cần thiết và redact tokens/passwords. Đừng upload nguyên environment variables và core dumps vào artifact công khai.

## 34. Tính ổn định của test: flaky khác incompatibility

Khi chạy matrix nhiều OS/CPU/JVM, thời gian xử lý và scheduling khác nhau có thể làm lộ các test phụ thuộc timing.

Ví dụ anti-pattern:

~~~java
Thread.sleep(100);
assertTrue(asyncResult.isCompleted());
~~~

Test này có thể pass trên máy x64 nhanh nhưng fail khi ARM64 runner đang tải cao; nó không tự chứng minh JDK/architecture có lỗi. Cần thay chờ thời gian cứng bằng đồng bộ/tín hiệu có timeout hợp lý, rồi kiểm tra đúng business invariant.

### 34.1. Flaky test phải được quản lý

- Ghi failure rate theo matrix row.
- Lưu logs và timing.
- Re-run theo policy để phân loại, không xóa kết quả đầu.
- Tìm root cause: race, môi trường, resource pressure hay bug JVM.
- Đặt owner/quarantine deadline nếu cho phép.
- Không vô hiệu hóa tests có tỷ lệ fail cao mà không có quyết định rõ.

Một test fail liên tục chỉ trên ARM64 là tín hiệu cần điều tra, không nên gắn nhãn “flaky ARM” rồi bỏ qua.

## 35. Quản lý môi trường test và dữ liệu ngoại vi

CI matrix thường cần DB, message broker, HTTP dependencies và secrets. Những thành phần này cũng có version và ảnh hưởng đến kết quả.

Nên:

- Sử dụng infrastructure test có version/image cố định.
- Tách database/protocol compatibility khỏi lỗi JDK khi có thể.
- Reset dữ liệu giữa cases và giữa jobs.
- Tránh dùng cùng một shared database không cô lập cho nhiều matrix rows.
- Ghi network/proxy/certificate behavior.
- Đảm bảo timezone/locale được đặt rõ trong tests cần tính xác định.
- Lưu schema version/migrations và migration state.
- Hạn chế external services không ổn định trong release gate.

### 35.1. Rolling deployment cần cross-version tests

Khi service mới chạy Java 21 và service cũ chạy Java 17 song song, bản thân JDK không bắt hai service truyền dữ liệu giống nhau; framework, JSON/XML/protobuf serializer, TLS và code có thể đồng thời thay đổi.

Test nên gồm:

~~~text
Old producer -> New consumer
New producer -> Old consumer (if rollback/rolling requires)
Old client   -> New server
New client   -> Old server (if supported)
~~~

Đừng mặc định việc nâng JDK giữ nguyên wire contract nếu cùng lần migration có đổi schema/framework/serialization.

## 36. Cách lập báo cáo tổng hợp theo từng lớp

Một báo cáo tối thiểu:

| Matrix row | Compile/API | Smoke | Core regression | Native/agent | E2E | Perf | Decision |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Linux x64 / JDK17 / vendor A | PASS | PASS | PASS | PASS | PASS | Baseline | Baseline |
| Linux x64 / JDK21 / vendor A | PASS | PASS | PASS | PASS | PASS | Within SLO | Supported |
| Linux arm64 / JDK21 / vendor A | PASS | PASS | PASS | FAIL | NOT_RUN | N/A | BLOCKED |
| Linux musl / JDK21 / vendor A | PASS | PASS | NOT_RUN | FAIL | NOT_RUN | N/A | Experimental |

Tất cả trạng thái trên đều minh họa. Một bảng thực tế phải có liên kết tới CI run, JDK build, image digest và reason cho fail/skip.

### 36.1. Ý nghĩa của kết quả

- **PASS:** suite đã chạy đủ theo profile và không có failures trái policy.
- **FAIL:** có test failure hoặc gate failure.
- **NOT_RUN:** chưa chạy hoặc bị infrastructure blocking.
- **N/A:** mục đó không áp dụng có lý do.
- **WAIVED:** có quyết định cho phép ngoại lệ, owner và expiry.

Không gộp NOT_RUN, N/A và WAIVED thành PASS.

## 37. Ví dụ điều tra: Java 21 ARM64 bị `UnsatisfiedLinkError`

Tình huống:

~~~text
Java 21 Linux AMD64: PASS
Java 21 Linux ARM64: FAIL
java.lang.UnsatisfiedLinkError: no codecnative in java.library.path
~~~

Hướng điều tra:

1. Xác minh runner thực sự là ARM64, không chỉ label trong CI.
2. Xác định JDK distribution, container image digest và `os.arch`.
3. Kiểm tra Java wrapper chọn native classifier nào.
4. Xác nhận file `.so` ARM64 có trong artifact/image.
5. Kiểm tra ELF architecture và phụ thuộc libc.
6. Kiểm tra `java.library.path` cùng OS dynamic linker paths.
7. Nếu JNI method không resolve, so Java/native version và symbols.
8. Chạy native integration tests trên image thực.

Nếu lỗi chỉ xảy ra ARM64, không tăng source compatibility hoặc thêm `--add-opens` ngẫu nhiên: chúng không cung cấp binary ARM64.

### 37.1. Quyết định release

Nếu ARM64 là P0 supported target, release bị chặn cho đến khi sửa hoặc có quyết định chính thức thay đổi scope. Nếu ARM64 chỉ exploratory, vẫn ghi lỗi và kế hoạch trước khi tuyên bố hỗ trợ.

## 38. Ví dụ điều tra: đổi JDK vendor gây lỗi TLS

Tình huống:

~~~text
JDK 21 vendor A / Linux x64: PASS
JDK 21 vendor B / Linux x64: TLS handshake FAIL
Application JAR, code, service endpoint identical
~~~

Các câu hỏi:

- Có cùng security providers và truststore không?
- Java security properties/cipher/algorithm constraints khác chỗ nào?
- CA certificates hoặc hệ thống OS trust khác không?
- Mutual TLS cert chain và alias lựa chọn có đúng không?
- Có FIPS/PKCS#11/native provider đặc thù không?
- Container image có cùng base packages không?
- JVM flags hoặc proxy settings có khác không?

Đặt cùng JDK feature release không loại bỏ khác biệt distribution packaging và security configuration. Đừng tắt certificate validation để “khắc phục”. Thay vào đó, chọn truststore/provider configuration phù hợp với security policy và test lại.

## 39. Ví dụ điều tra: CI xanh nhưng production Java 21 fail

Tình huống:

~~~text
CI: Ubuntu hosted runner + full JDK 21, tests pass
Production: minimal jlink image + agents, startup fails
~~~

Nguyên nhân có thể:

- `jlink` image thiếu module/providing service mà ứng dụng cần.
- Agent/JVMTI bị inject ở production nhưng không có trong CI.
- JDK distribution hoặc update build khác.
- OS/native libraries/certificates khác.
- Runtime flags và permissions/container limits khác.

Lộ trình:

1. So fingerprint CI và production.
2. Kiểm tra image digest cùng `java -version`.
3. Liệt kê modules `jlink` image và service providers.
4. Xác định startup JVM arguments, agent JARs và permissions.
5. Chạy smoke/integration tests trên **production-like final image**.
6. Thay đổi image/modules/agents đúng nguyên nhân và tái chạy gate.

**Bài học:** ma trận chỉ có giá trị khi mỗi row đại diện cho môi trường thực sự được tuyên bố, không phải một runner gần giống.

## 40. Ví dụ điều tra: ARM64 chậm hơn x64

Tình huống:

~~~text
Java 21 x64:  p99 within SLO
Java 21 ARM:  p99 exceeds SLO
No functional test failures
~~~

Không kết luận CPU architecture kém hơn chỉ từ kết quả này. Kiểm tra:

- Instance SKU, CPU quotas và noisy neighbors.
- JVM flags/GC, vendor build và CPU features.
- JIT warmup và compilation.
- Native crypto/compression libraries có tối ưu cho ARM không.
- Network/storage throughput.
- Profiling/telemetry overhead.
- Thread pools và contention.
- Workload và dataset có giống nhau không.

Nếu sau khi giữ workload/điều kiện công bằng mà vẫn có regression, có thể cần tối ưu, giới hạn deployment hoặc ghi performance support policy cho platform.

## 41. Từ matrix tới rollout: không dừng ở CI

Sau khi release gates pass, migration production vẫn cần kiểm chứng:

1. Triển khai canary với đúng JDK vendor/build/OS/image/arch.
2. Theo dõi functional errors, latency, memory, CPU, GC và traces.
3. So với baseline ở traffic tương tự.
4. Tăng traffic/replicas từng đợt theo policy.
5. Giữ rollback/roll-forward plan thực tế.
6. Xác nhận logging, metrics, traces và alerts.
7. Ghi mọi hotfix và JDK patch được triển khai.

### 41.1. Rollback không chỉ là khôi phục Docker image

Nếu migration kèm đổi database schema, serialization, message payload, authentication hoặc public API, một consumer cũ có thể không đọc được dữ liệu mới. Cần kiểm thử **cross-version compatibility** và đặt giới hạn rollback rõ.

### 41.2. Sau rollout vẫn phải tiếp tục duy trì matrix

Mỗi thay đổi sau có thể khiến ma trận cần chạy lại:

- JDK security update.
- OS base image hoặc kernel/container runtime upgrade.
- Thêm ARM64 nodes.
- Đổi JDK vendor.
- JDBC/native library/agent upgrade.
- Thay framework major hoặc bytecode generator.
- Thay security policy hoặc truststore.

Đó là lý do matrix nên tồn tại trong repository và release process thay vì một spreadsheet làm một lần rồi quên.

## 42. Những sai lầm phổ biến

**“Đã test Java 21 là đủ.”** Không đủ nếu sản phẩm hỗ trợ nhiều vendor, OS, CPU hoặc runtime images.

**“Java bytecode portable nên JNI cũng portable.”** Sai. Native binaries còn phụ thuộc OS/architecture/libc và ABI.

**“Vendor khác chỉ là logo.”** Không nên giả định. Distribution build, JVM implementation, security providers và support policy cần được xét.

**“Linux là một môi trường thống nhất.”** Sai với glibc/musl, OS image, kernel và native libraries.

**“Ghi arch=arm64 trong CI nghĩa là test ARM64.”** Sai nếu runner thật vẫn x64 hoặc đang emulation mà không ghi nhận.

**“`--release 17` chứng minh runtime Java 17 pass.”** Sai. Phải chạy artifact với Java 17 thật và dependencies phù hợp.

**“CI pass trên full JDK nên `jlink` image cũng pass.”** Sai nếu image thiếu modules/providers hoặc khác agents.

**“Pairwise đủ cho mọi production combination.”** Sai với mandatory support cases và high-order native/security interactions.

**“Không có runner thì đánh dấu N/A.”** Sai nếu product contract vẫn yêu cầu tổ hợp ấy.

**“Một test skipped vẫn là pass.”** Sai. Phải có lý do và policy xử lý skipped/waived.

**“App trả HTTP 200 nghĩa là toàn bộ migration pass.”** Sai nếu observability, TLS/crypto, persistence hoặc performance vi phạm contract.

**“Thay base image không ảnh hưởng JDK migration.”** Sai: libc, certificates, native libs và filesystem semantics có thể khác.

**“Tất cả LTS releases đều có cùng hỗ trợ.”** Sai: vendor lifecycle, license và update policy khác nhau.

**“Dùng tag latest cho test vẫn tái lập được.”** Không chắc; cần JDK full build và immutable image digest.

**“Flaky failures trên ARM64 không cần điều tra.”** Sai; đó có thể là concurrency bug hoặc resource regression thật.

**“Chỉ cần một bảng ô xanh, không cần bằng chứng.”** Sai: phải ghi test suite, runtime fingerprint, artifact hash, logs và ngày kiểm thử.

## 43. Checklist khi phê duyệt ma trận JDK migration

- [ ] Đã định nghĩa current baseline, target support và experimental scope.
- [ ] Đã xác định chủ sở hữu support policy cùng thời hạn rà soát.
- [ ] Mỗi ô có JDK feature, full update/build, distribution và JVM implementation.
- [ ] Mỗi ô có OS release/image, libc khi cần và CPU architecture thực.
- [ ] Đã xác minh vendor có binary phù hợp với OS/architecture tương ứng.
- [ ] Đã xác minh product hỗ trợ tổ hợp, không chỉ vendor.
- [ ] Không có unsupported combinations được trình bày là pass.
- [ ] Đã ghi compiler JDK, `--release`, test JVM và runtime JVM riêng khi cần.
- [ ] Đã cố định application artifact checksum và runtime image digest.
- [ ] CI runners thực sự chạy trên architecture được ghi.
- [ ] Đã xác định mandatory/optional test profile cho từng row.
- [ ] Tất cả production-supported rows có core regression và smoke coverage.
- [ ] JNI/JNA/native libraries có binary và integration tests theo OS/arch.
- [ ] Java agents, JVMTI, bytecode parsers và coverage tools được kiểm tra.
- [ ] TLS/crypto/security-provider tests đáp ứng policy khi liên quan.
- [ ] Đã kiểm tra serialization/data/protocol cross-version nếu rolling/rollback yêu cầu.
- [ ] Có performance/GC/memory tests cho platform trọng yếu.
- [ ] Test reports phân biệt PASS/FAIL/NOT_RUN/SKIPPED/WAIVED/N/A.
- [ ] Không còn mandatory row thiếu evidence do runner outage.
- [ ] Đã lưu runtime fingerprint, test counts, logs, commit và timestamp.
- [ ] Dữ liệu logs/core/arguments được bảo vệ và redact secrets.
- [ ] Có process cho JDK patch, vendor hoặc OS image change.
- [ ] Có canary, monitoring và rollback/roll-forward plan.
- [ ] Support matrix và những giới hạn đã được công bố đúng trong release notes.

## 44. Mẫu hồ sơ quyết định hỗ trợ một tổ hợp

~~~text
Matrix ID: COMPAT-JDK-021
Application / release: orders-service / candidate-build
Purpose: target production
JDK feature: 21
JDK full version/build: verified at execution
Distribution: approved JDK vendor
JVM implementation: recorded from runtime
OS image/version: immutable image digest
Architecture: linux/arm64, native
libc: recorded
Java artifact SHA256: recorded
JNI/JNA dependencies: approved ARM64 variants
Java agent: approved agent version
Compiler target: --release 17 or approved product floor
Test profile: smoke + core + native + TLS + E2E
Performance criteria: approved product SLO
Support status: candidate until validated
CI run / evidence: link or artifact identifier
Owner: runtime-platform + service team
Decision: PASS / FAIL / BLOCKED / WAIVED
Expiry / next review: next JDK/image update cycle
~~~

Không để câu `verified at execution` thay cho version thực tế trong báo cáo cuối: đó chỉ là vị trí giữ chỗ trong mẫu. Mỗi release phải có thông tin JDK build, image digest và artifact thật để truy nguyên.

## 45. Tài liệu nên đối chiếu khi lập ma trận

Do support matrix, JDK release policy và danh sách runner thay đổi theo thời gian, cần dùng tài liệu chính thức **đúng phiên bản**:

- **OpenJDK/JDK release notes:** thay đổi API, JVM flags, security và known issues.
- **Tài liệu support platform của từng JDK distribution:** supported OS, CPU architectures, JVM variants và lifecycle.
- **Java SE Specification/Java Virtual Machine Specification:** tính tương thích của ngôn ngữ, bytecode, class loading.
- **`javac` Tool Guide:** `--release` và giới hạn platform APIs.
- **Gradle Java Compatibility Matrix / Toolchains:** Gradle daemon JVM khác compiler/test toolchain.
- **Maven Compiler/Toolchains/Surefire/Failsafe documentation:** compiler JDK, release target và test JVM forks.
- **CI runner provider documentation:** runner labels, architectures, images và lifecycle.
- **Container runtime/Docker multi-platform docs:** architecture selection và immutable image references.
- **OS native loader/JNI/JVMTI documentation:** native architecture/ABI và agent compatibility.
- **Vendor APM/JDBC/HTTP/framework support matrices:** dependency và instrumentation với JDK target.
- **Security/TLS/provider docs:** certificates, algorithm constraints, FIPS/PKCS#11 khi liên quan.

Không ghi cứng một câu “vendor X hỗ trợ mọi JDK trên mọi OS” vào bài kiểm thử. Phải kiểm tra **distribution release cụ thể** tại thời điểm lập và cập nhật ma trận.

## 46. Kết luận

Lập ma trận JDK, nhà cung cấp, hệ điều hành và kiến trúc là một phần trọng yếu của **kiểm thử hồi quy trong Java Advance Compatibility Migration**. Cùng số phiên bản Java vẫn có thể tạo kết quả khác khi JDK vendor/build, JVM implementation, OS image, libc, architecture, native dependencies hoặc agents thay đổi.

Một ma trận có giá trị bắt đầu bằng **support policy của sản phẩm**, xác định các tổ hợp hợp lệ, phân tầng kiểm thử theo rủi ro, rồi xác thực từng ô bằng **runtime và artifact thực**, không chỉ source-level compatibility. Những môi trường production phải có release gates rõ; pairwise và exploratory tests giúp mở rộng coverage nhưng không thay nghĩa vụ kiểm thử các tổ hợp đã cam kết.

Cuối cùng, hãy ghi lại JDK full build, distribution, OS/CPU, container digest, artifact hash, test profile và kết quả. Ma trận không nên dừng ở báo cáo CI: nó phải kết nối với canary, giám sát, rollback và quy trình JDK security updates. Khi đó lời khẳng định **“ứng dụng hỗ trợ Java trên những nền tảng này”** trở thành một hợp đồng kỹ thuật có bằng chứng, người chịu trách nhiệm và khả năng tái lập.
