# Đánh giá tương thích trước khi đổi kiến trúc CPU hoặc nhà cung cấp

Chuyển một workload từ x86-64 sang Arm64, đổi thế hệ CPU, hoặc di chuyển VM từ cloud provider này sang provider khác có thể giảm chi phí và mở thêm lựa chọn hạ tầng. Tuy nhiên, một image khởi động được chưa chắc ứng dụng chạy đúng, đạt hiệu năng yêu cầu hoặc giữ được các đặc tính bảo mật và vận hành hiện tại.

Tương thích cần được đánh giá ở nhiều lớp: tập lệnh CPU, ABI, binary và thư viện native, hệ điều hành, kernel, firmware, image/container, runtime, driver, dịch vụ cloud, dữ liệu, license và quy trình vận hành. Khi đổi nhà cung cấp, cần kiểm tra thêm sự khác biệt về network, storage, identity, secret, load balancer, monitoring và API quản lý.

Bài học này cung cấp quy trình đánh giá trước migration, từ lập inventory và xây ma trận tương thích đến benchmark, backup/restore, cutover và rollback. Mục tiêu là xác định sớm thành phần không tương thích, đo được rủi ro và chỉ chuyển workload khi có bằng chứng đáp ứng yêu cầu chức năng, hiệu năng, bảo mật, RTO/RPO và chi phí.

## 1. Xác định chính xác thay đổi cần thực hiện

Trước khi kiểm tra tương thích, cần mô tả rõ phạm vi thay đổi. Ba trường hợp dưới đây có rủi ro khác nhau.

| Loại thay đổi | Ví dụ | Rủi ro chính |
|---|---|---|
| Đổi thế hệ hoặc vendor CPU trong cùng ISA | Intel x86-64 sang AMD x86-64 | CPU feature flags, microcode, hiệu năng, NUMA và license |
| Đổi kiến trúc CPU | x86-64 sang Arm64 | Binary, thư viện native, kernel module, runtime và image |
| Đổi cloud provider | Provider A sang Provider B | API, IAM, network, storage, managed services, image và dữ liệu |
| Kết hợp đổi kiến trúc và provider | VM x86-64 ở provider A sang Arm64 ở provider B | Tất cả các lớp trên cùng rủi ro migration dữ liệu và vận hành |

Đổi CPU vendor nhưng vẫn cùng ISA thường dễ hơn đổi ISA. Tuy nhiên, hai CPU cùng x86-64 vẫn có thể khác tập lệnh mở rộng, hiệu năng mỗi core, memory bandwidth, NUMA topology hoặc giới hạn instance.

Đổi cloud provider không nhất thiết phải đổi CPU architecture. Có thể chuyển workload x86-64 giữa hai provider để giảm phụ thuộc dịch vụ, sau đó mới đánh giá chuyển sang Arm64 ở một giai đoạn riêng. Tách các thay đổi giúp xác định nguyên nhân nếu benchmark hoặc kiểm thử thất bại.

### Viết rõ trạng thái trước và sau

Một yêu cầu migration nên nêu:

- Kiến trúc nguồn và đích: x86-64, Arm64 hoặc CPU family cụ thể.
- Hệ điều hành và phiên bản nguồn/đích.
- Loại VM hoặc container runtime.
- Cloud provider, region và zone.
- Dịch vụ managed đang sử dụng.
- Mô hình dữ liệu và replication.
- SLO, RTO, RPO và cửa sổ downtime.
- Ràng buộc bảo mật, compliance và license.
- Tiêu chí thành công và điều kiện rollback.

Không bắt đầu bằng câu “chuyển sang máy mới tương đương”. Tương đương phải được xác định theo năng lực và hành vi workload, không chỉ số vCPU hoặc dung lượng RAM.

## 2. Phân biệt ISA, microarchitecture và ABI

### Instruction Set Architecture (ISA)

ISA là tập lệnh và mô hình thực thi mà phần mềm máy có thể sử dụng. Ví dụ:

- x86-64 hoặc AMD64.
- AArch64, thường được gọi là Arm64.

Binary được biên dịch cho x86-64 thường không thể chạy trực tiếp trên CPU Arm64. Ngược lại cũng vậy, trừ khi có lớp giả lập hoặc dịch lệnh tương thích. Lớp giả lập có thể giúp chạy một số ứng dụng, nhưng không tự bảo đảm hiệu năng, độ ổn định hoặc hỗ trợ production.

### Microarchitecture

Microarchitecture là cách một CPU cụ thể triển khai ISA: pipeline, cache, branch prediction, số core, vector unit, memory controller và các đặc tính khác.

Hai CPU cùng ISA vẫn có thể có hiệu năng khác nhau đáng kể. Workload nhạy với single-thread latency, memory bandwidth, cache size hoặc vector instruction cần được benchmark trên loại máy đích.

### ABI (Application Binary Interface)

ABI quy định cách binary tương tác với hệ điều hành và thư viện: calling convention, register usage, kiểu dữ liệu, alignment, system call interface và định dạng binary.

Một chương trình có ISA phù hợp vẫn có thể không chạy nếu ABI, dynamic loader hoặc thư viện hệ thống không tương thích.

### CPU feature và extension

Ngoài ISA cơ bản, CPU có thể hỗ trợ các extension khác nhau, ví dụ:

- SIMD/vector instruction như SSE, AVX hoặc AVX-512 trên một số CPU x86.
- NEON hoặc SVE trên các nền tảng Arm tương ứng.
- Các extension cho cryptography hoặc thao tác nguyên tử.

Binary được build với yêu cầu extension mà CPU đích không có có thể lỗi khi chạy, ví dụ illegal instruction. Build nên chọn baseline feature được hỗ trợ trên toàn bộ loại máy đích, hoặc phát hiện capability lúc chạy và dùng code path phù hợp.

Không nên suy ra extension chỉ từ tên kiến trúc. Cần kiểm tra CPU feature flags trên instance đích và tài liệu instance family của provider.

## 3. Kiểm tra kiến trúc CPU và hệ điều hành nguồn

### Linux

Các lệnh quan sát:

~~~sh
uname -m
lscpu
cat /proc/cpuinfo
getconf LONG_BIT
cat /etc/os-release
uname -r
~~~

Ý nghĩa:

- `uname -m` cho biết machine architecture mà kernel đang chạy báo cáo.
- `lscpu` hiển thị CPU architecture, model, sockets, cores, threads và flags.
- `/proc/cpuinfo` cung cấp thông tin CPU theo cách kernel trình bày.
- `getconf LONG_BIT` cho biết user space đang dùng mô hình 32-bit hay 64-bit.
- `/etc/os-release` xác định bản phân phối và phiên bản.
- `uname -r` cho biết kernel đang chạy.

VM có thể hiển thị CPU model ảo hóa. Vì vậy, hãy kết hợp thông tin guest với metadata instance type của provider.

### Windows

Có thể dùng PowerShell:

~~~powershell
Get-CimInstance Win32_Processor |
  Select-Object Name, Manufacturer, Architecture, AddressWidth, NumberOfCores, NumberOfLogicalProcessors

Get-CimInstance Win32_OperatingSystem |
  Select-Object Caption, Version, OSArchitecture

systeminfo
~~~

Architecture code trong WMI có thể khác cách gọi phổ biến; cần đối chiếu tài liệu Windows Management Instrumentation và phiên bản hệ điều hành.

### Xác định ứng dụng và binary

Linux:

~~~sh
file /opt/app/bin/service
readelf -h /opt/app/bin/service
readelf -A /opt/app/bin/service
~~~

Các lệnh này giúp nhận diện loại ELF, machine architecture và một số thuộc tính ABI. Với thư viện native, kiểm tra từng shared object quan trọng, không chỉ executable chính.

Trên Windows, công cụ như `dumpbin /headers` trong Visual Studio Developer Command Prompt có thể hiển thị machine type của PE binary. Kiểm tra cả DLL native mà ứng dụng nạp.

Không chạy hoặc nạp binary không tin cậy chỉ để kiểm tra. Dùng công cụ phân tích tĩnh và môi trường sandbox phù hợp.

## 4. Lập inventory binary, thư viện và thành phần native

Đây thường là bước phát hiện nhiều vấn đề nhất khi đổi x86-64 sang Arm64.

### Thành phần cần kiểm kê

- Executable do tổ chức tự build.
- Shared library như .so, .dll hoặc .dylib.
- Native extension của ngôn ngữ.
- Database driver và client library.
- Agent bảo mật, monitoring và backup.
- Kernel module và driver thiết bị.
- Runtime launcher và JIT compiler.
- Package cài từ repository của hệ điều hành.
- Công cụ vendor hoặc phần mềm thương mại.
- Script gọi binary bên ngoài.

Một ứng dụng Java có bytecode JVM thường dễ chuyển kiến trúc hơn chương trình C/C++ được build cố định cho x86-64. Nhưng nếu Java dùng JNI, Netty native transport, compression library, cryptographic provider hoặc agent native, các thành phần đó vẫn phải có bản Arm64 tương thích.

Python code thuần thường portable, nhưng package có extension C/C++ cần wheel đúng platform tag. Node.js có native addon cũng cần binary phù hợp. Go binary phải được build cho đúng GOARCH và các dependency native nếu có.

### Kiểm tra dependency động

Trên Linux có thể dùng `readelf -d` hoặc `objdump -p` để xem dynamic dependencies. Lệnh `ldd` tiện cho binary đáng tin cậy trong môi trường kiểm soát, nhưng không nên dùng trên executable không tin cậy vì một số cách triển khai có thể thực thi code khi phân tích.

Kiểm tra:
- Library có sẵn cho architecture đích không.
- Version và SONAME có tương thích không.
- Dynamic loader có đúng đường dẫn không.
- glibc hoặc musl version có đáp ứng yêu cầu không.
- Có dependency chỉ được phát hành cho x86-64 không.
- License có giới hạn theo CPU, socket hoặc core không.

### Native dependency matrix

| Thành phần | Kiến trúc nguồn | Bản đích | Trạng thái cần ghi |
|---|---|---|---|
| Application binary | x86-64 | Arm64 build | Supported / rebuild / unsupported |
| Native library | x86-64 | Arm64 package | Version và ABI |
| Database driver | x86-64 | Arm64 package | Vendor support |
| Monitoring agent | x86-64 | Arm64 agent | Feature parity |
| Security agent | x86-64 | Arm64 agent | Vendor certification |
| Kernel module | Kernel/arch nguồn | Module đích | Build và signing |
| Backup agent | x86-64 | Arm64 package | Restore compatibility |

Một thành phần chưa có bản Arm64 không nhất thiết chặn toàn bộ migration nếu có thể thay thế hoặc loại bỏ. Tuy nhiên, phải có quyết định và kiểm thử rõ ràng; không được bỏ qua chỉ vì ứng dụng chính đã khởi động.

## 5. Kiểm tra hệ điều hành, kernel và firmware

### OS release và support lifecycle

Đảm bảo hệ điều hành đích hỗ trợ architecture mới và vẫn nằm trong thời gian hỗ trợ của vendor. Kiểm tra:

- Phiên bản distribution và repository.
- Kernel version và configuration.
- glibc/musl và dynamic loader.
- Package availability theo architecture.
- Security update và patch cadence.
- Init system và service manager.
- Boot mode BIOS/UEFI.
- Secure Boot và ký kernel module.
- TPM/vTPM nếu ứng dụng phụ thuộc.
- Driver và guest tools.

Một image x86-64 không thể mặc định boot trên Arm64. Thường cần build hoặc chọn image riêng cho kiến trúc đích.

### Kernel module và driver

Kernel module thường phụ thuộc cả architecture lẫn kernel ABI. Các module cho filesystem, network, storage, GPU, security monitoring hoặc backup có thể cần build riêng.

Kiểm tra:
- Module có source hoặc package cho architecture đích không.
- Có hỗ trợ kernel version mục tiêu không.
- Module signing và Secure Boot có hợp lệ không.
- Driver có feature parity không.
- Vendor có chứng nhận trên instance family và OS đó không.

### Firmware và thiết bị ảo

Các VM có thể dùng thiết bị ảo khác nhau giữa provider hoặc instance family. Kiểm tra driver cho:
- Block storage và NVMe.
- Virtual network interface.
- Console và boot device.
- Entropy/random source.
- GPU hoặc accelerator.
- TPM/vTPM.
- Timekeeping và clock source.

Provider khác nhau có thể dùng firmware, device model và guest agent khác nhau. Image cần được kiểm thử trên loại VM đích, không chỉ boot trong emulator.

### Cloud-init và bootstrap

Script khởi tạo có thể chứa giả định:
- Tên thiết bị như `/dev/sda`.
- Package chỉ có trên một architecture.
- Repository hoặc URL tải binary x86-64.
- Network interface name cố định.
- Metadata endpoint riêng của provider.
- User-data syntax hoặc agent riêng.

Chuyển provider cần kiểm tra bootstrap, cloud-init, startup script và configuration management.

## 6. Tương thích runtime và ngôn ngữ lập trình

### Java/JVM

Bytecode Java thường portable giữa các architecture nếu có JDK/JRE tương thích. Cần kiểm tra:
- JDK vendor và version có hỗ trợ architecture đích không.
- Native library/JNI có bản tương ứng không.
- JVM flags và JIT behavior.
- Garbage collector và CPU feature support.
- Container awareness và số CPU hiệu dụng.
- Agent APM, profiler, security và monitoring.

Không giả định hiệu năng JVM giống nhau chỉ vì bytecode không đổi. JIT có thể tạo machine code khác và cần benchmark warm-up, throughput, GC và tail latency.

### .NET

Kiểm tra runtime version, architecture package, native dependency, globalization library, profiler/diagnostic agent và support matrix của vendor. Một số workload có thể dùng framework-dependent deployment, nhưng runtime trên máy đích vẫn phải tương thích.

### Python

Kiểm tra:
- Python interpreter architecture.
- Wheel availability theo platform tag.
- Native extension và system library.
- Package chỉ có source build hoặc yêu cầu compiler.
- C/C++/Fortran dependency.
- Runtime performance và numerical library support.

Nếu phải build wheel từ source, kiểm tra toolchain và dependency system ở CI.

### Node.js

Kiểm tra:
- Node runtime architecture và version.
- Native addon như module dùng node-gyp.
- Prebuilt binary availability.
- OpenSSL và system library compatibility.
- Build script và package postinstall.
- Agent instrumentation.

### Go, Rust, C/C++

Go và Rust thường hỗ trợ cross-compilation tốt, nhưng cần xác minh target, cgo và native dependency. C/C++ cần toolchain, sysroot, compiler flags, ABI và CPU baseline phù hợp.

Không chỉ cross-compile thành công là đủ. Cần test runtime, concurrency, memory ordering, cryptography, SIMD path và behavior trên CPU đích.

## 7. Container image và multi-architecture

### Image manifest list

OCI image có thể được phát hành dưới dạng multi-platform image index, chứa manifest riêng cho từng architecture như linux/amd64 và linux/arm64. Container runtime chọn manifest phù hợp với node.

Một tag giống nhau không bảo đảm image hỗ trợ mọi kiến trúc. Nếu registry chỉ có manifest amd64, pod trên Arm64 node có thể lỗi pull hoặc không chạy.

### Kiểm tra image

Có thể dùng:

~~~sh
docker buildx imagetools inspect registry.example.com/team/api:1.4
docker manifest inspect registry.example.com/team/api:1.4
~~~

Các công cụ và output phụ thuộc Docker/Buildx version. Kiểm tra manifest có platform mục tiêu, digest và provenance đúng.

### Build multi-architecture

Ví dụ dùng Buildx:

~~~sh
docker buildx build \
  --platform linux/amd64,linux/arm64 \
  --tag registry.example.com/team/api:1.4 \
  --push .
~~~

Dockerfile cần dùng base image hỗ trợ cả hai architecture. Mọi package được cài trong build stage và binary copy sang runtime stage phải tương thích với target platform.

### Cross-build và native build

Cross-build có thể tạo binary cho kiến trúc khác, nhưng một số package cần chạy test hoặc generate code trên target. Có thể dùng native builder cho từng architecture hoặc emulation trong CI.

QEMU/emulation hữu ích cho build và smoke test, nhưng không đại diện đầy đủ hiệu năng, timing hoặc behavior phần cứng native. Benchmark production phải chạy trên CPU đích thực.

### Kubernetes scheduling

Khi cluster có node nhiều architecture:
- Gắn label architecture và OS đúng cho node.
- Dùng nodeSelector hoặc node affinity nếu workload cần binary riêng.
- Kiểm tra image manifest.
- Kiểm tra DaemonSet agent có image hỗ trợ architecture.
- Kiểm tra CSI/CNI và device plugin.
- Không để pod bị schedule lên node không tương thích.

Ví dụ:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: api-arm64
spec:
  replicas: 3
  selector:
    matchLabels:
      app: api-arm64
  template:
    metadata:
      labels:
        app: api-arm64
    spec:
      nodeSelector:
        kubernetes.io/arch: arm64
      containers:
        - name: api
          image: registry.example.com/team/api:1.4
          resources:
            requests:
              cpu: "500m"
              memory: "512Mi"
            limits:
              cpu: "2"
              memory: "1Gi"
~~~

Đây là ví dụ giới hạn workload vào node Arm64. Image vẫn phải có manifest Arm64 và các dependency của cluster phải hỗ trợ node architecture đó.

## 8. Kiểm tra CPU feature và hiệu năng ứng dụng

Tương thích chức năng không đồng nghĩa hiệu năng tương đương.

### Các yếu tố ảnh hưởng

- Số core và thread.
- Single-thread performance.
- Clock behavior và sustained frequency.
- Cache size và hierarchy.
- Memory bandwidth và latency.
- NUMA topology.
- SIMD/vector support.
- CPU credit hoặc burst behavior.
- Thermal/power policy.
- Hypervisor scheduling và CPU quota.
- Compiler/JIT optimization.
- Encryption/compression instruction.
- GPU hoặc accelerator attachment.

Một instance 8 vCPU trên provider A không nhất thiết tương đương 8 vCPU trên provider B. vCPU có thể đại diện cho một hardware thread hoặc scheduling unit khác nhau theo loại máy.

### Benchmark theo workload thực tế

Dùng workload đại diện, không chỉ chạy synthetic CPU benchmark. Đo:
- Throughput.
- p50/p95/p99 latency.
- CPU time và utilization theo core.
- Memory footprint và allocation.
- GC pause hoặc runtime pause.
- Disk IOPS/throughput/latency.
- Network throughput/latency.
- Queue depth và concurrency.
- Error rate và timeout.
- Chi phí trên mỗi request hoặc transaction.

### Kiểm tra hiệu năng theo tải

Thực hiện:
1. Warm-up runtime và cache.
2. Chạy tải nền.
3. Tăng dần tới tải mục tiêu.
4. Chạy burst.
5. Giữ tải dài để phát hiện throttling hoặc leak.
6. Chạy khi một replica/site bị mất.
7. So sánh với baseline nguồn.
8. Lặp lại đủ lần để giảm nhiễu.

Đặt ngưỡng chấp nhận trước khi test. Ví dụ, p95 không được xấu hơn quá 10% ở tải mục tiêu và chi phí mỗi request phải giảm ít nhất một tỷ lệ đã thống nhất. Con số cụ thể phải theo SLO và mục tiêu kinh doanh, không dùng chung cho mọi hệ thống.

## 9. Kiểm tra phần mềm thương mại và license

License có thể phụ thuộc:
- Số physical core hoặc vCPU.
- Socket hoặc host.
- CPU vendor/model.
- Cloud provider hoặc authorized environment.
- Instance family và dedicated host.
- Architecture.
- Region hoặc môi trường triển khai.
- Số node hoặc số instance đồng thời.

Một license hợp lệ trên x86-64 ở provider hiện tại không tự động hợp lệ trên Arm64 hoặc provider mới. Liên hệ vendor và lưu xác nhận bằng văn bản khi license có điều khoản theo nền tảng.

Kiểm tra cả:
- Database engine và extension.
- Backup/restore agent.
- Security/EDR.
- Monitoring/APM.
- Middleware và message broker.
- Commercial runtime.
- GPU software stack và driver.

Tính license vào TCO. Một instance Arm64 rẻ hơn có thể không giảm tổng chi phí nếu agent hoặc database license không hỗ trợ, hoặc cần duy trì một nhóm x86-64 riêng.

## 10. Đánh giá tương thích khi đổi cloud provider

Đổi provider là thay đổi platform contract. Ứng dụng có thể phụ thuộc nhiều API và dịch vụ mà không xuất hiện trong source code nghiệp vụ.

### Compute và image

Kiểm tra:
- Instance family và CPU architecture.
- Image format, boot mode và guest driver.
- Metadata service và instance identity.
- Startup/user-data mechanism.
- Autoscaling và lifecycle hook.
- Console, serial access và rescue process.
- Quota, region, AZ và capacity reservation.

Image snapshot của provider thường không phải artifact portable trực tiếp. Có thể cần export, convert, import hoặc build lại image từ pipeline chuẩn hóa. Kiểm tra license, encryption và boot configuration trong quá trình chuyển.

### Network

Kiểm tra mapping giữa:
- VPC/VNet và subnet.
- Route table và route propagation.
- Security group/firewall/NACL.
- Private endpoint và service endpoint.
- NAT gateway và egress.
- Load balancer L4/L7.
- DNS, private DNS và service discovery.
- Static IP, floating IP và public IP.
- Peering, VPN, Direct Connect/ExpressRoute/Interconnect.
- Network policy trong Kubernetes.

Không sao chép rule theo tên mà không kiểm tra semantics. Một provider có thể áp dụng stateful firewall, provider khác có NACL stateless hoặc khác thứ tự xử lý.

### Storage và dữ liệu

Kiểm tra:
- Block volume type, IOPS và throughput.
- Snapshot format và khả năng export/import.
- Filesystem và device naming.
- Shared file service và protocol.
- Object storage API, lifecycle và versioning.
- Encryption key ownership và portability.
- Backup format và restore tooling.
- Replication và consistency.
- Data egress cost và transfer time.

Snapshot mã hóa bằng key do provider quản lý có thể không di chuyển trực tiếp sang provider khác. Cần giải mã/export bằng quy trình được phép hoặc tạo backup logical và mã hóa lại bằng key đích.

### Identity và security

Kiểm tra:
- IAM role/policy và service account.
- Federated identity và workload identity.
- KMS/key vault/HSM.
- Secret manager và rotation.
- Certificate issuance và trust chain.
- Audit log và retention.
- Security posture, policy-as-code và compliance.
- Private registry và image signing.

Không chuyển secret bằng cách copy vào user-data hoặc file image. Dùng kênh secret bootstrap và identity phù hợp ở provider đích.

### Managed services

Lập danh sách dịch vụ phụ thuộc:

- Managed database.
- Cache.
- Message queue/stream.
- Object storage.
- Search service.
- API gateway.
- Scheduler.
- Monitoring/logging/tracing.
- Backup service.
- Container registry và orchestration.

Nếu provider đích không có dịch vụ tương đương, cần chọn giữa thay thế managed service, tự vận hành phần mềm tương ứng hoặc thay đổi kiến trúc. Mỗi lựa chọn có chi phí vận hành và rủi ro khác nhau.

## 11. Portability của ứng dụng và infrastructure as code

### Provider-specific API

Mã ứng dụng có thể gọi SDK trực tiếp của provider để:
- Đọc metadata.
- Upload object.
- Gửi message.
- Lấy secret.
- Gọi managed database hoặc queue.
- Tạo signed URL.
- Điều khiển autoscaling.

Tạo abstraction layer chỉ hữu ích khi nó giữ được semantics cần thiết. Không phải mọi object store hoặc queue đều có cùng consistency, ordering, retention hoặc transaction behavior.

### Infrastructure as Code

Terraform, Pulumi hoặc công cụ tương tự có thể giúp tái tạo hạ tầng, nhưng resource và provider schema khác nhau. Một module dùng chung có thể cần interface riêng cho:
- Network.
- VM/instance group.
- Load balancer.
- Database.
- Storage.
- IAM.
- Monitoring.
- Secret.
- DNS.

Không giả định đổi provider chỉ cần thay provider block. Cần kiểm tra state migration, resource replacement, import, dependency graph và nguy cơ destroy resource.

### Configuration và policy

Chuẩn hóa cấu hình có thể giảm phụ thuộc:
- Image build pipeline.
- Ansible/cloud-init hoặc configuration management.
- Policy-as-code.
- Secret reference.
- Monitoring instrumentation.
- Deployment artifact.
- Service discovery contract.

Giữ cấu hình tách khỏi image và code để có thể build lại trên architecture/provider mới.

## 12. Tương thích dữ liệu và định dạng lưu trữ

### Binary format và data format là hai vấn đề khác nhau

Đổi CPU architecture có thể yêu cầu build lại executable nhưng không nhất thiết phải chuyển đổi dữ liệu nghiệp vụ. Tuy nhiên, database engine, storage engine hoặc extension có thể có giới hạn về architecture/version.

Đổi provider có thể yêu cầu chuyển dữ liệu giữa hai dịch vụ khác nhau. Cần kiểm tra:
- Database version và supported upgrade path.
- Collation, encoding và timezone.
- Extension, stored procedure và plugin.
- Transaction isolation và consistency.
- Index format và query behavior.
- Backup format và restore tooling.
- CDC/replication support.
- Large object, binary file và metadata.

### Logical backup và physical backup

- **Logical backup:** export schema và record theo định dạng logic như SQL dump hoặc application export. Thường portable hơn nhưng có thể chậm với dữ liệu lớn.
- **Physical backup:** copy data files, snapshots hoặc storage-level backup. Thường nhanh hơn trong cùng engine/platform nhưng có thể phụ thuộc version, architecture hoặc provider.
- **Snapshot:** điểm khôi phục của volume/service. Không tự bảo đảm tính nhất quán ứng dụng nếu dữ liệu đang ghi.

Cần kiểm tra công cụ backup có chạy trên architecture đích không và format có được hỗ trợ khi restore sang provider mới không.

### Application-level compatibility

Ngoài database, cần kiểm tra:
- File serialization format.
- Message schema và version.
- Encryption envelope và key ID.
- Timestamp precision.
- Numeric representation.
- Endianness nếu có dữ liệu binary phụ thuộc architecture.
- Compression codec.
- Object metadata và ACL.

Các định dạng chuẩn có versioning giúp giảm phụ thuộc, nhưng cần test thực tế với dữ liệu đã lưu nhiều năm.

## 13. Ma trận đánh giá tương thích

Tạo một ma trận có owner và bằng chứng cho từng thành phần.

| Lớp | Câu hỏi đánh giá | Bằng chứng cần có | Kết quả |
|---|---|---|---|
| CPU/ISA | Binary có chạy trên kiến trúc đích không? | Build target, ELF/PE header, CPU flags | Pass / rebuild / blocker |
| ABI/runtime | Runtime và loader có tương thích không? | Vendor support matrix, integration test | Pass / rebuild / blocker |
| Native libraries | Có package đúng architecture không? | Package manifest, dependency scan | Pass / replace / blocker |
| OS/kernel | OS, kernel và driver có được hỗ trợ không? | Support lifecycle, module test | Pass / upgrade / blocker |
| Container | Image có manifest đúng platform không? | OCI manifest, pull/run test | Pass / rebuild / blocker |
| Cloud services | Network, storage, IAM, LB và managed service có tương đương không? | Architecture mapping, POC | Pass / redesign / blocker |
| Data | Backup/restore và consistency có được bảo đảm không? | Restore test, reconciliation | Pass / transform / blocker |
| Performance | Đạt throughput và latency mục tiêu không? | Benchmark/load test | Pass / tune / blocker |
| License | Vendor cho phép chạy trên platform mới không? | Contract/vendor confirmation | Pass / renew / blocker |
| Security | Agent, key, certificate và policy có tương đương không? | Security validation | Pass / remediate / blocker |
| Operations | Monitoring, backup, patch và incident runbook có hoạt động không? | Operational rehearsal | Pass / adapt / blocker |
| Cost | TCO có đạt mục tiêu không? | Cost model và measured usage | Pass / revise / blocker |

Kết quả không nên chỉ là checkbox “hỗ trợ”. Ghi rõ phiên bản, architecture, provider, loại instance, người xác nhận, ngày kiểm tra và link tới bằng chứng.

## 14. Quy trình migration an toàn

~~~mermaid
flowchart TD
    I["Inventory workload và dependency"] --> M["Ma trận tương thích"]
    M --> G{"Có blocker?"}
    G -->|Có| R["Rebuild / replace / redesign"]
    R --> M
    G -->|Không| P["Build image và environment đích"]
    P --> T["Functional, security và performance test"]
    T --> V{"Đạt tiêu chí?"}
    V -->|Không| R
    V -->|Có| B["Backup và restore rehearsal"]
    B --> D["Data replication / migration rehearsal"]
    D --> C["Canary và cutover"]
    C --> H{"SLO và dữ liệu đạt?"}
    H -->|Không| RB["Rollback theo runbook"]
    H -->|Có| F["Mở rộng traffic và hoàn tất migration"]
~~~

### Giai đoạn 1: inventory và phân loại

Thu thập:
- VM/instance type và CPU architecture.
- OS, kernel, image và agent.
- Binary/native dependency.
- Container image và manifest.
- Cloud service và API phụ thuộc.
- Database, file, object và queue.
- License, security policy và monitoring.
- SLO, RTO/RPO, tải nền/đỉnh.

Phân loại workload:
- Portable trực tiếp.
- Cần rebuild/repackage.
- Cần thay thế dependency.
- Cần redesign.
- Chưa được hỗ trợ và phải giữ nguyên nền tảng hiện tại.

### Giai đoạn 2: build environment đích

- Chọn instance family và OS image được hỗ trợ.
- Build binary cho architecture đích.
- Tạo multi-arch container image nếu cần.
- Cài agent, driver và security tooling.
- Tái tạo network/IAM/secret.
- Cấu hình monitoring và backup.
- Chuẩn hóa deployment và bootstrap.

### Giai đoạn 3: kiểm thử

Thực hiện:
- Unit/integration test.
- End-to-end test.
- Data correctness và reconciliation.
- Load/stress/soak test.
- Failover và recovery test.
- Security scan và policy validation.
- Backup/restore test.
- License validation.
- Cost measurement.

### Giai đoạn 4: rehearsal dữ liệu

Chạy thử toàn bộ luồng backup, transfer, import, replication và validation với dữ liệu có kích thước gần production. Đo thời gian, throughput, egress, replication lag và lượng dữ liệu cần đồng bộ ở cutover.

### Giai đoạn 5: canary và cutover

Chuyển một phần traffic hoặc workload không trọng yếu trước. So sánh:
- Error rate.
- p95/p99 latency.
- Throughput.
- Data correctness.
- CPU/memory/storage/network.
- Dependency errors.
- Cost per request.
- Alert và operational events.

Chỉ tăng tỷ trọng khi mọi tiêu chí đạt. Cutover dữ liệu ghi cần có kế hoạch quiesce hoặc CDC/final sync để tránh mất hoặc ghi trùng.

## 15. Backup, restore và rollback trước khi chuyển

### Backup phải độc lập với nguồn lỗi

Trước khi thay architecture hoặc provider:
- Tạo backup nhất quán theo ứng dụng/database.
- Lưu bản backup ở failure domain độc lập.
- Bảo vệ bằng encryption và quyền tối thiểu.
- Kiểm tra retention và immutability nếu yêu cầu.
- Lưu key material hoặc quy trình truy cập key hợp lệ.
- Ghi nhận version của backup tool và format.
- Thử restore vào môi trường đích.

Snapshot volume khi ứng dụng đang ghi có thể chỉ crash-consistent. Database cần native backup, quiesce hoặc snapshot mechanism có application consistency nếu yêu cầu.

### Restore test là cổng bắt buộc

Một backup chỉ được xem là có ích khi đã restore thành công. Kiểm tra:
- Có thể giải mã backup không.
- Có thể đọc format trên architecture/provider đích không.
- Database có mở và recovery được không.
- File/object checksum có khớp không.
- Application có đọc dữ liệu sau restore không.
- RTO/RPO có đạt không.
- Quyền và key có sẵn trong môi trường phục hồi không.

### Rollback sau khi cutover

Rollback đơn giản nhất khi workload đích chưa nhận ghi production. Khi đã có dữ liệu mới, cần biết cách đưa dữ liệu đó về nguồn cũ.

Các chiến lược:
- Giữ source read-only sau cutover và chỉ cho phép rollback trước khi có write mới.
- Dùng replication hai chiều được hỗ trợ và có conflict control.
- Dùng CDC hoặc event log để đồng bộ ngược.
- Dùng application dual-write chỉ khi có transaction/idempotency design rõ ràng.

Không bật dual-write tùy tiện. Hai hệ thống có thể ghi thành công ở một bên và thất bại ở bên kia, tạo trạng thái không nhất quán.

Đặt thời điểm hết hạn rollback. Sau khi hệ thống đích đã ghi nhiều dữ liệu và source không còn đồng bộ, rollback có thể trở thành một migration ngược riêng.

## 16. Kiểm thử cutover và điều kiện dừng

Trước cutover, xác định:
- Thời điểm freeze thay đổi schema/config.
- Cách dừng hoặc giảm write.
- Cách đồng bộ phần dữ liệu cuối.
- Điều kiện xác nhận replication lag bằng 0 hoặc nằm trong RPO.
- Cách đổi DNS/load balancer/service discovery.
- Cách xử lý connection đang mở.
- Cách xác minh giao dịch sau chuyển.
- Người có quyền quyết định tiếp tục hoặc rollback.

### Điều kiện dừng ví dụ

- Error rate vượt ngưỡng trong thời gian quy định.
- p95/p99 vượt SLO.
- Database replication lag vượt RPO.
- Data reconciliation phát hiện thiếu hoặc trùng.
- Security agent hoặc audit không hoạt động.
- License hoặc vendor support chưa xác nhận.
- Backup/restore chưa chứng minh được.
- Capacity đích không đáp ứng tải failover.

Điều kiện phải định lượng và được thống nhất trước khi bắt đầu. Không thay ngưỡng giữa cutover chỉ để tiếp tục migration.

## 17. Ví dụ: chuyển ứng dụng Java từ x86-64 sang Arm64

Một dịch vụ Java chạy trên VM x86-64 muốn chuyển sang VM Arm64 để tối ưu chi phí.

### Inventory

- Java 21 runtime.
- Ứng dụng Spring Boot dạng JAR.
- JDBC driver.
- JNI library dùng để nén dữ liệu.
- APM agent và endpoint security agent.
- Container base image.
- Database bên ngoài và object storage.

### Đánh giá

| Thành phần | Kết quả kiểm tra |
|---|---|
| Java bytecode | Có thể dùng lại nếu JDK đích hỗ trợ Arm64 |
| JDK | Chọn distribution/version có build Arm64 được vendor hỗ trợ |
| JDBC driver | Kiểm tra jar và native dependency nếu có |
| JNI compression library | Cần binary Arm64 hoặc thay thế bằng implementation portable |
| APM/security agent | Xác minh agent Arm64 và feature parity |
| Container image | Build manifest linux/amd64 và linux/arm64 |
| Runtime flags | Kiểm tra CPU count, heap và GC trên instance đích |
| Database connection | Đo latency, pool và tổng connection |
| Performance | Benchmark p95/p99, throughput, GC và cost/request |

### Rehearsal

1. Build image multi-arch.
2. Deploy Arm64 vào staging.
3. Chạy integration và data correctness test.
4. Chạy load test cùng workload source.
5. So sánh latency, throughput và memory.
6. Kiểm tra APM, security agent và backup.
7. Chạy canary với traffic nhỏ.
8. Tăng traffic theo từng bước.

Nếu JNI library chưa có Arm64, cần thay thế hoặc giữ workload đó trên x86-64. Không coi emulation là giải pháp production lâu dài nếu chưa được vendor hỗ trợ và benchmark.

## 18. Ví dụ: chuyển VM giữa hai cloud provider

Một ứng dụng web dùng VM, managed database, object storage và load balancer. Khi chuyển provider, nhóm không chỉ copy disk image.

### Mapping dịch vụ

| Thành phần nguồn | Thành phần đích cần đánh giá |
|---|---|
| VM image | Image mới hoặc convert/import có kiểm thử |
| Security group | Firewall/network policy tương đương |
| Load balancer | Listener, health check, TLS và draining |
| Managed database | Engine/version, replication, backup/restore |
| Object storage | API, metadata, versioning, lifecycle và ACL |
| IAM role | Workload identity và least-privilege policy |
| Secret manager/KMS | Secret bootstrap, key migration và rotation |
| Monitoring | Metrics, logs, traces, alert và audit |
| Autoscaling | Min/max/desired, health replacement và lifecycle |
| DNS | TTL, cutover, private zone và service discovery |

### Dữ liệu

Nhóm thử logical database export và object transfer trên tập dữ liệu đại diện. Họ đo thời gian export/import, egress, checksum, schema compatibility và application query behavior.

Nếu provider đích dùng database service khác, cần test transaction isolation, collation, extension, stored procedure và replication strategy. Không giả định hai database cùng tên engine có behavior hoàn toàn giống nhau.

### Cutover

- Dựng hạ tầng đích và chạy smoke test.
- Replicate dữ liệu liên tục hoặc đồng bộ theo phương án.
- Giảm write hoặc bật maintenance window.
- Đồng bộ phần dữ liệu cuối.
- Kiểm tra row count/checksum và business invariants.
- Chuyển traffic.
- Theo dõi SLO và audit.
- Chỉ ngừng nguồn sau khi hết cửa sổ rollback và có xác nhận.

## 19. Các rủi ro thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Binary báo illegal instruction | Build yêu cầu CPU extension không có trên máy đích | Build baseline phù hợp hoặc dispatch theo CPU feature |
| Container không chạy trên Arm64 | Image chỉ có manifest amd64 hoặc native dependency thiếu | Build/publish platform manifest và test native |
| Java chạy nhưng startup lỗi | JNI, agent hoặc native library chỉ có x86-64 | Kiểm tra dependency và vendor support |
| VM không boot sau import | Firmware, boot mode, disk driver hoặc image format khác | Rebuild image hoặc sửa boot config có kiểm thử |
| Kernel module không load | Module sai architecture/kernel ABI hoặc chưa ký | Build module đúng kernel/arch và ký theo policy |
| Hiệu năng giảm mạnh | CPU quota, single-thread performance, memory bandwidth hoặc JIT | Benchmark profile và chọn instance family phù hợp |
| Pod Pending trên node mới | Image/daemonset/CSI/CNI không hỗ trợ architecture | Kiểm tra manifest, scheduler constraint và add-on |
| Database restore thất bại | Backup format/version/extension không tương thích | Chọn logical migration hoặc upgrade path được hỗ trợ |
| Object copy xong nhưng app lỗi | Metadata, ACL, versioning hoặc API semantics khác | Kiểm tra checksum, metadata và authorization |
| Secret không giải mã được | Key thuộc KMS cũ hoặc policy không có ở provider đích | Lập kế hoạch key migration và re-encryption |
| License không hợp lệ | License theo core, architecture hoặc provider | Xác nhận vendor và cập nhật license |
| Rollback mất dữ liệu | Source không nhận các write sau cutover | Thiết kế CDC/replication ngược hoặc giới hạn rollback window |

## 20. Tiêu chí go/no-go trước migration

Chỉ chuyển khi các nhóm tiêu chí trọng yếu đều có bằng chứng:

### Tương thích chức năng
- Binary và native dependency chạy đúng trên architecture đích.
- Runtime, OS, kernel và driver được hỗ trợ.
- Container image có platform manifest phù hợp.
- Managed service/API có mapping và behavior đã kiểm tra.

### Hiệu năng và capacity
- Đạt throughput và p95/p99 theo SLO.
- CPU/RAM/storage/network còn headroom.
- Dependency không bị quá tải.
- Đạt capacity khi mất một replica/AZ theo yêu cầu.
- Cost per request/transaction đáp ứng mục tiêu.

### Dữ liệu và phục hồi
- Backup hoàn tất và restore test thành công.
- Replication lag nằm trong RPO.
- Cutover và final sync đã rehearsal.
- Có cách xử lý write mới nếu rollback.
- Data reconciliation không phát hiện sai lệch.

### Bảo mật và vận hành
- IAM, secret, key, certificate và audit hoạt động.
- Security/monitoring/backup agent được hỗ trợ.
- Patch và support lifecycle rõ ràng.
- Alert, dashboard và runbook sẵn sàng.
- License và compliance được phê duyệt.

### Tổ chức và quyết định
- Có owner cho từng hệ thống phụ thuộc.
- Có người quyết định go/no-go.
- Có maintenance window và thông báo.
- Có điều kiện dừng và rollback.
- Có thời điểm kết thúc rollback window.

## 21. Checklist đánh giá tương thích

- [ ] Đã ghi rõ kiến trúc CPU, provider, OS và instance type nguồn/đích.
- [ ] Đã phân biệt đổi CPU vendor, đổi ISA và đổi cloud provider.
- [ ] Đã kiểm kê executable, shared library, native extension và kernel module.
- [ ] Đã kiểm tra ISA, ABI, CPU feature và baseline compiler.
- [ ] Đã xác minh OS, kernel, firmware, Secure Boot và driver.
- [ ] Đã xác minh JDK/runtime và agent được hỗ trợ trên architecture đích.
- [ ] Đã kiểm tra container image manifest cho mọi architecture mục tiêu.
- [ ] Đã kiểm tra Kubernetes node labels, scheduler, CNI, CSI và DaemonSet.
- [ ] Đã mapping network, storage, IAM, KMS, secret, DNS và load balancer.
- [ ] Đã kiểm tra managed service và API-specific dependency.
- [ ] Đã xác minh license, vendor support và compliance.
- [ ] Đã kiểm tra backup format, restore tool và data portability.
- [ ] Đã rehearsal replication, final sync và cutover.
- [ ] Đã benchmark throughput, p95/p99, resource usage và cost.
- [ ] Đã kiểm thử security, failover và operational monitoring.
- [ ] Đã định nghĩa điều kiện go/no-go và rollback.
- [ ] Đã thử restore vào môi trường đích.
- [ ] Đã có owner, runbook và thời điểm kết thúc rollback window.

## Kết luận

Đánh giá tương thích trước khi đổi CPU architecture hoặc cloud provider phải bao quát cả binary, ABI, native library, OS, kernel, firmware, container, runtime, driver, dịch vụ cloud, dữ liệu, license và quy trình vận hành. Cùng ISA không có nghĩa hiệu năng giống nhau; cùng ngôn ngữ lập trình không có nghĩa mọi native dependency đều portable; cùng tên managed service không có nghĩa API và consistency giống nhau. Hãy lập inventory, xây ma trận tương thích, build môi trường đích, benchmark và thử restore trước khi cutover. Migration chỉ nên được phê duyệt khi chức năng, SLO, dữ liệu, bảo mật, RTO/RPO và rollback đều đã được kiểm chứng trên cấu hình đích.
