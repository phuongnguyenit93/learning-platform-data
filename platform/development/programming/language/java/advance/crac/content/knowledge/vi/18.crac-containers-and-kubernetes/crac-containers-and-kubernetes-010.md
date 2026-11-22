# Xác minh môi trường khôi phục trên node và kiến trúc CPU đích

Một CRaC checkpoint có thể được tạo trên một node và restore trên node khác, nhưng khả năng này phụ thuộc vào mức tương thích giữa hai môi trường. Việc cả hai node đều chạy Linux hoặc cùng được ghi nhãn `amd64` chưa đủ để kết luận restore sẽ thành công. JVM có thể đã sử dụng các tập lệnh CPU mà node đích không hỗ trợ; CRIU có thể cần kernel feature không được bật; container có thể thiếu capability, mount hoặc quyền cần thiết; và JDK/CRIU ở node đích có thể không tương thích với image.

Trong Kubernetes, scheduler mặc định chỉ biết các thuộc tính node được công bố qua label và resource. Nó không tự phân tích CRaC checkpoint để biết image cần AVX2, AVX-512, một phiên bản kernel cụ thể hay mount nào. Vì vậy, pipeline phải xác minh môi trường đích trước, lưu một hồ sơ tương thích cùng checkpoint, rồi dùng node label/affinity để giới hạn Pod vào nhóm node đã được kiểm chứng.

Quy trình đúng có ba lớp: **xác minh kiến trúc và CPU**, **xác minh hệ điều hành, CRIU và quyền runtime**, rồi **thử restore trên đúng container image và node pool dự kiến triển khai**. Lệnh kiểm tra tĩnh giúp phát hiện sớm khác biệt; restore test mới là bằng chứng cuối cùng rằng bộ image hoạt động trong môi trường thực tế.

## 1. Tương thích không chỉ là tên kiến trúc CPU

Checkpoint chứa trạng thái của một tiến trình đang chạy, bao gồm register, memory map, code đã được JIT biên dịch và trạng thái runtime. Khi restore trên máy khác, các thành phần này phải được môi trường đích hỗ trợ.

Các yếu tố cần đối chiếu:

- Kiến trúc instruction set: x86-64, AArch64/ARM64 hoặc kiến trúc khác.
- CPU features mà JVM đã sử dụng: SSE, AVX, AVX2, AVX-512, AES và các capability liên quan.
- FPU state và cách CPU hỗ trợ XSAVE.
- JDK vendor, version đầy đủ, build, kiến trúc và native libraries.
- Linux kernel, cấu hình kernel và các namespace/cgroup feature.
- CRIU version và engine mà JDK CRaC sử dụng.
- Container runtime, security context và Linux capabilities.
- Filesystem, mount path, file được tham chiếu và quyền truy cập.
- Dung lượng RAM, huge pages, cgroup limits và các tài nguyên khác cần để map lại memory.

Spring Boot mô tả việc restore trên một máy khác như một khả năng khi hệ điều hành và kiến trúc CPU tương tự. Điều đó không có nghĩa checkpoint có thể chuyển tùy ý giữa mọi node cùng tên OS hoặc cùng kiến trúc. [Spring Boot: Checkpoint and Restore With the JVM](https://docs.spring.io/spring-boot/reference/packaging/checkpoint-restore.html)

### 1.1. Không restore chéo kiến trúc

Một checkpoint được tạo bởi JVM trên `x86_64` không phải image có thể chuyển trực tiếp sang `aarch64`. Register state, instruction set, machine code đã JIT, ABI và binary của JDK phụ thuộc kiến trúc.

Trong Kubernetes, các giá trị thường gặp là:

| Nơi kiểm tra | x86-64 | ARM 64-bit |
|---|---|---|
| `uname -m` trên Linux | `x86_64` | `aarch64` |
| Kubernetes `kubernetes.io/arch` | `amd64` | `arm64` |
| OCI image platform | `linux/amd64` | `linux/arm64` |
| JDK `os.arch` thường gặp | `amd64` hoặc `x86_64` | `aarch64` |

Tên có thể khác giữa kernel, JVM và Kubernetes. Hãy chuẩn hóa trong manifest của checkpoint, ví dụ `linux/amd64` hoặc `linux/arm64`, và kiểm tra đúng image variant mà container runtime sẽ tải.

Nếu cần chạy ứng dụng trên cả amd64 và arm64, hãy tạo checkpoint riêng cho từng kiến trúc từ JDK và container image tương ứng. Multi-architecture OCI image chỉ giúp chọn đúng binary/container layer; nó không chuyển đổi nội dung một checkpoint đã được tạo trên kiến trúc khác.

### 1.2. Cùng kiến trúc vẫn có thể thiếu CPU instruction

Hai node đều là `amd64` nhưng có thể khác thế hệ CPU và tập lệnh được hỗ trợ. Ví dụ, node tạo checkpoint có AVX-512 nhưng node đích chỉ có AVX2. JVM đã khởi động trên CPU nguồn có thể đã dùng những instruction mà CPU đích không thực thi được.

CRaC không thể tự cấu hình lại một JVM đang được restore để ngừng dùng các CPU feature đã được chọn khi JVM khởi động. Đây là nguyên nhân có thể dẫn tới lỗi CPU compatibility ngay trong quá trình restore. [CRaC: CPU features](https://crac.org/reference/cpu-features/)

Vì vậy, phải xác minh feature set, không chỉ xác minh architecture string.

## 2. Thu thập fingerprint trên node tạo checkpoint

Trước khi tạo checkpoint, ghi lại môi trường đã chạy JVM. Nên thu thập thông tin từ cả host và container, vì container có thể nhìn thấy CPU feature hoặc filesystem khác với thông tin quản trị viên đọc từ một máy khác.

### 2.1. Kiến trúc, kernel và CPU model

Trên Linux node nguồn:

~~~bash
uname -m
uname -r
cat /etc/os-release
lscpu
getconf LONG_BIT
getconf PAGE_SIZE
~~~

Ý nghĩa:

- `uname -m` cho biết machine architecture mà kernel đang chạy.
- `uname -r` ghi nhận kernel release.
- `/etc/os-release` ghi nhận distribution và version.
- `lscpu` cho biết CPU model, vendor, topology và một số CPU flags.
- `getconf LONG_BIT` cho biết userspace là 32-bit hay 64-bit.
- `getconf PAGE_SIZE` ghi nhận page size mà process sử dụng.

Đối với `x86_64`, kiểm tra thêm flags:

~~~bash
grep -m1 '^flags' /proc/cpuinfo
~~~

Đối với ARM, kernel thường công bố capability qua trường `Features`:

~~~bash
grep -m1 '^Features' /proc/cpuinfo
~~~

Không nên chỉ lưu tên CPU model. Một VM có thể trình bày CPU model ảo và mask một số feature của host. Các flags mà process thực sự nhìn thấy mới là dữ liệu cần so sánh.

### 2.2. CPU features mà JVM thực sự sử dụng

Trên JDK CRaC có hỗ trợ option hiển thị CPU feature, chạy:

~~~bash
"$JAVA_HOME/bin/java" -XX:+ShowCPUFeatures --version
~~~

Kết quả thường hiển thị hai dòng quan trọng:

~~~text
This machine's CPU features are: -XX:CPUFeatures=...
CPU features being used are: -XX:CPUFeatures=...
~~~

Dòng đầu cho biết feature set mà JVM nhìn thấy trên máy hiện tại. Dòng thứ hai cho biết feature set JVM sử dụng. Hãy lưu nguyên văn kết quả vào manifest cùng checkpoint.

Lệnh cần chạy với **đúng JDK vendor/build và đúng container image** dùng để tạo checkpoint. Không lấy kết quả từ một JDK khác trên host rồi suy ra JVM trong Pod có cùng feature set.

Nếu option `-XX:+ShowCPUFeatures` không tồn tại ở JDK đang dùng, không tự suy luận feature mask. Kiểm tra tài liệu của vendor/runtime và dùng công cụ CPU phù hợp. Các option liên quan CPU feature có thể khác giữa các bản phân phối JDK.

### 2.3. Ghi nhận JDK và CRIU

~~~bash
"$JAVA_HOME/bin/java" -version
"$JAVA_HOME/bin/java" -XshowSettings:properties -version 2>&1 \
    | grep -E 'java.vendor|java.version|java.runtime.version|os.arch|os.name'
criu --version
~~~

Nếu CRIU được đóng gói cùng JDK thay vì cài ở PATH, kiểm tra binary mà CRaC engine thực sự gọi. Ví dụ với một số OpenJDK CRaC build, helper nằm dưới `$JAVA_HOME/lib/criu`. Không giả định binary trên PATH là binary được engine sử dụng; xác nhận theo JDK vendor và cấu hình `-XX:CRaCEngine`.

OpenJDK CRaC hiện hướng dẫn sử dụng CRIU gần đây, README upstream nêu CRIU 4.0 trở lên làm mốc cài đặt. Vendor JDK có thể có ma trận hỗ trợ riêng, do đó phiên bản CRIU phải theo đúng tài liệu của runtime đang triển khai. [OpenJDK CRaC README](https://github.com/openjdk/crac/blob/crac/README.md)

## 3. Thu thập fingerprint trên node đích

Lặp lại cùng bộ lệnh trên node dự kiến restore. Dùng cùng cách thu thập để so sánh kết quả nguồn và đích.

~~~bash
uname -m
uname -r
cat /etc/os-release
lscpu
getconf LONG_BIT
getconf PAGE_SIZE
grep -m1 '^flags' /proc/cpuinfo
"$JAVA_HOME/bin/java" -XX:+ShowCPUFeatures --version
"$JAVA_HOME/bin/java" -version
criu --version
~~~

Nếu target là ARM, thay lệnh đọc `flags` bằng `Features` như phần trước.

### 3.1. So sánh hai fingerprint

Có thể dùng bảng sau trong manifest hoặc báo cáo kiểm tra:

| Thuộc tính | Checkpoint source | Restore target | Quyết định |
|---|---|---|---|
| OS | Linux | Linux | Kiểm tra kernel/runtime chi tiết |
| Architecture | amd64 | amd64 | Phải trùng kiến trúc |
| CPU features JVM sử dụng | Feature set A | Feature set B | B phải đáp ứng mọi feature bắt buộc của image |
| JDK vendor/build | Vendor + build A | Vendor + build B | Ưu tiên cùng vendor/build đã kiểm chứng |
| CRIU | Version A | Version B | Theo ma trận hỗ trợ của JDK; restore test xác nhận |
| Kernel | Release A | Release B | Kiểm tra feature bằng CRIU, không chỉ so sánh chuỗi version |
| Page size | 4 KiB | 4 KiB | Ghi nhận và kiểm tra với image thực tế |
| Container image | Digest A | Digest A | Ưu tiên cùng image digest |
| Mount/security | Profile A | Profile B | Phải đáp ứng yêu cầu của process và CRIU |

Một số thuộc tính có thể khác nhau mà vẫn restore được; một số khác là điều kiện cứng. Không dùng một phép so sánh version duy nhất để kết luận. Ví dụ, kernel target không nhất thiết phải có chuỗi version giống source, nhưng phải cung cấp các feature cần thiết và được CRIU/runtime hỗ trợ.

### 3.2. Đọc thông tin kernel qua Kubernetes API

Từ máy quản trị cluster:

~~~bash
kubectl get nodes \
  -L kubernetes.io/arch,kubernetes.io/os,node.kubernetes.io/instance-type
~~~

Để xem chi tiết một node:

~~~bash
kubectl get node <NODE_NAME> -o jsonpath='{.status.nodeInfo.architecture}{"\n"}{.status.nodeInfo.operatingSystem}{"\n"}{.status.nodeInfo.kernelVersion}{"\n"}{.status.nodeInfo.osImage}{"\n"}{.status.nodeInfo.containerRuntimeVersion}{"\n"}{.status.nodeInfo.kubeletVersion}{"\n"}'
~~~

Các trường `Node.status.nodeInfo` giúp biết kiến trúc, kernel, OS image, container runtime và kubelet mà cluster ghi nhận. Chúng không thay thế việc chạy `lscpu`, kiểm tra CRIU hoặc thử restore trên node.

## 4. Xác minh CPU feature compatibility

Đây là bước quan trọng khi checkpoint được tạo trên một node rồi restore trên node khác cùng kiến trúc.

### 4.1. Đối chiếu feature set của JVM

Giả sử JVM nguồn sử dụng các feature:

~~~text
CPUFeatures used on source = FEATURE_SET_A
~~~

Node đích phải hỗ trợ các feature mà image yêu cầu. Nếu target thiếu một instruction mà JVM/JIT code đã sử dụng, process có thể không chạy an toàn.

CRaC có thể phát thông báo restore yêu cầu chỉ định `-XX:CPUFeatures=...` khi checkpoint được tạo với feature set không phù hợp với các node đích. Hãy dùng thông tin mà runtime cung cấp để cấu hình **lúc tạo checkpoint**, không đợi tới lúc production restore mới thử bỏ qua kiểm tra.

### 4.2. Dùng feature baseline chung

Nếu checkpoint cần chạy trên nhiều node khác thế hệ CPU, có thể tạo image với feature baseline chung thấp hơn. Trên các JDK CRaC hỗ trợ, option `-XX:CPUFeatures=generic` chọn một tập lệnh bảo thủ hơn để tăng khả năng tương thích trên cùng kiến trúc.

Ví dụ:

~~~bash
"$JAVA_HOME/bin/java" \
    -XX:CRaCCheckpointTo=/var/lib/orders/checkpoint \
    -XX:CPUFeatures=generic \
    -jar orders-service.jar
~~~

Cách này có thể giảm hiệu năng vì JVM không sử dụng một số instruction tối ưu mà CPU nguồn hỗ trợ. Đổi lại, image có thể chạy trên tập node rộng hơn. Phải xác nhận option có trong JDK vendor/build đang dùng và chạy benchmark để đánh giá trade-off.

Nếu target node pool đã biết trước, có thể dùng feature set chung của nhóm node thay vì baseline generic. Tài liệu CRaC mô tả cách lấy feature mask của các máy và tính phần giao logic AND (`&`) để tạo tập feature chung. Chỉ dùng cách này khi định dạng mask và option được JDK hiện tại hỗ trợ. [CRaC: CPU features](https://crac.org/reference/cpu-features/)

### 4.3. Không tắt kiểm tra CPU để ép restore

Không dùng chế độ bỏ qua CPU feature check như một cách sửa lỗi production. Một số runtime có option experimental để bỏ qua kiểm tra; bỏ qua kiểm tra không bổ sung instruction còn thiếu vào CPU đích.

Nếu image yêu cầu AVX-512 nhưng target không có AVX-512, ép restore có thể dẫn tới lỗi instruction khi code được thực thi. Hãy tạo checkpoint mới với baseline phù hợp hoặc giới hạn workload vào node có feature tương thích.

### 4.4. CRIU cũng có kiểm tra CPU riêng

CRIU có cơ chế kiểm tra CPU capability độc lập với option CPU feature của JVM. Công cụ `criu cpuinfo dump` có thể lưu CPU capability vào image `cpuinfo.img`, còn `criu cpuinfo check` so sánh image đó với CPU hiện tại. CRIU cũng có option `--cpu-cap` để kiểm soát các nhóm kiểm tra như FPU, instruction compatibility và CPU capability.

Ví dụ kiểm tra bổ sung bằng CRIU:

~~~bash
mkdir -p /tmp/source-cpu-profile
cd /tmp/source-cpu-profile
criu cpuinfo dump
~~~

Chuyển file `cpuinfo.img` vừa tạo sang môi trường kiểm tra target, rồi chạy:

~~~bash
cd /tmp/source-cpu-profile
criu cpuinfo check
~~~

Đây là phép kiểm tra CPU của CRIU, không phải thao tác tạo hay sửa CRaC checkpoint. Việc CRIU image CPU riêng được kiểm tra thành công không thay thế `-XX:+ShowCPUFeatures` của JVM và cũng không chứng minh toàn bộ process image restore được. Tùy CRIU version và cách JDK gọi engine, mức kiểm tra CPU có thể khác nhau. [CRIU: cpuinfo](https://www.criu.org/CLI/cmd/cpuinfo) · [CRIU: --cpu-cap](https://github.com/checkpoint-restore/criu/blob/criu-dev/Documentation/criu.txt)

## 5. Xác minh kernel và các feature CRIU cần

CRIU dựa vào chức năng của Linux kernel để dump và restore process. Kernel version là một thông tin quan trọng, nhưng chỉ nhìn `uname -r` chưa đủ vì feature có thể bị tắt trong kernel config hoặc bị giới hạn bởi môi trường container.

### 5.1. Chạy CRIU check trên node đích

Trên target node hoặc trong môi trường có cùng quyền và namespace với Pod restore:

~~~bash
criu check
criu check --extra
~~~

`criu check` kiểm tra các yêu cầu kernel cơ bản của CRIU. `criu check --extra` kiểm tra thêm những feature có thể cần cho process sử dụng resource đặc thù. Kết quả `Looks good` là điều kiện thuận lợi để tiếp tục, không phải bằng chứng rằng một checkpoint cụ thể chắc chắn restore được.

Nếu ứng dụng sử dụng AIO, TUN device trong network namespace hoặc resource đặc biệt khác, cần kiểm tra các feature tương ứng. [CRIU: Check the kernel](https://criu.org/CLI/cmd/check)

### 5.2. Các kernel feature cần lưu ý

CRIU có thể phụ thuộc vào các tính năng như:

- Checkpoint/restore support.
- Process, network, IPC và UTS namespaces.
- PID namespace và khả năng tạo lại PID.
- File handle và các syscall liên quan.
- Eventfd, epoll và socket diagnostics.
- Cgroup và mount namespace.
- Các feature riêng theo loại resource mà ứng dụng sử dụng.

Danh sách chính xác phụ thuộc CRIU version, kernel config và process tree. CRIU duy trì tài liệu về kernel options cần thiết; không nên tự kết luận chỉ dựa vào một con số kernel tối thiểu. [CRIU: Linux kernel requirements](https://criu.org/Linux_kernel)

### 5.3. Ghi nhận cgroup và mount

Trên node/Pod đích:

~~~bash
stat -fc %T /sys/fs/cgroup
mount | grep -E 'cgroup|overlay|tmpfs'
findmnt -R /
~~~

Kết quả `cgroup2fs` thường cho biết cgroup v2; các môi trường khác có thể dùng cgroup v1 hoặc cấu hình kết hợp. Ghi nhận phiên bản cgroup và mount layout ở cả source lẫn target. Khả năng restore còn phụ thuộc CRIU, kernel, container runtime và cách cgroup được cấu hình.

Không coi cgroup v1 và v2 là tương đương chỉ vì cả hai đều hiển thị resource limit. Kiểm tra đúng CRIU/runtime đang dùng và thử restore trên node có cùng loại cấu hình.

## 6. Xác minh container runtime và quyền trên node đích

Ngay cả khi host hỗ trợ CRIU, Pod có thể không có đủ quyền để gọi các thao tác cần thiết. CRaC engine dựa trên CRIU thường cần quyền cao hơn một ứng dụng Java thông thường.

### 6.1. Kiểm tra CRIU binary và capability

Tùy JDK/vendor, CRIU có thể được cung cấp cùng JDK hoặc được cài ở host. Xác định binary thực sự được engine gọi, sau đó kiểm tra:

~~~bash
criu --version
command -v criu
ls -l "$JAVA_HOME/lib/criu"
~~~

OpenJDK CRaC hiện mô tả CRIU engine cần quyền đặc biệt; trong container có thể cần các Linux capability như `CHECKPOINT_RESTORE` và `SYS_PTRACE`. Một số build hướng dẫn cấu hình SUID cho helper CRIU. Yêu cầu chính xác phụ thuộc JDK build, CRIU version, container runtime và cách triển khai. [CRaC: Checkpoint engines](https://crac.org/reference/engines/) · [OpenJDK CRaC runtime requirements](https://crac.org/use/crac-runtime/)

### 6.2. Kiểm tra capability của process trong Pod

~~~bash
id
grep '^Cap' /proc/self/status
~~~

Nếu có công cụ `capsh`:

~~~bash
capsh --print
~~~

Đọc kết quả từ chính container chạy Java. Kiểm tra trên host không chứng minh Pod được cấp cùng capability. Ngoài Linux capability, còn phải xem seccomp profile, AppArmor/SELinux policy, user namespace và quyền truy cập `/proc`.

Không dùng `privileged: true` hoặc cấp toàn bộ capability như một giải pháp mặc định. Hãy cấu hình theo yêu cầu của CRaC runtime và chính sách bảo mật cluster; nếu môi trường dùng SUID helper, xác nhận owner và permission của đúng binary theo hướng dẫn vendor.

### 6.3. Container runtime và node runtime

Ghi nhận:

- Container runtime name/version: containerd, CRI-O hoặc runtime khác.
- RuntimeClass nếu Pod dùng runtime đặc biệt.
- Kernel của node.
- SecurityContext của Pod.
- PID namespace và user namespace.
- Seccomp, AppArmor và SELinux policy.
- Cgroup driver và cgroup version.

Restore test phải chạy trong cùng loại runtime và security profile với workload production. Một phép thử CRIU chạy trực tiếp trên host có thể thành công nhưng Pod vẫn thất bại do thiếu capability hoặc namespace khác.

## 7. Xác minh filesystem, mount và native library

CRIU khôi phục trạng thái process, nhưng không có nghĩa toàn bộ filesystem bên ngoài container image tự được đóng gói cùng checkpoint.

Các đường dẫn và file mà process phụ thuộc cần được kiểm tra:

- JDK home và native library.
- Application JAR và dependency.
- File được memory-map.
- File cấu hình cần đọc sau restore.
- Volume mount và secret mount.
- Thư mục làm việc, temp directory và symlink.
- File descriptor được giữ lại hoặc được xử lý qua callback.
- Quyền owner/group và mode của file.

### 7.1. Ưu tiên cùng container image digest

Cách đơn giản để giảm khác biệt là tạo checkpoint và restore bằng cùng container image digest. Điều này giữ nguyên JDK, JAR, native library, đường dẫn và các file trong image layer.

Ví dụ lấy image digest đang chạy:

~~~bash
kubectl get pod <POD_NAME> -o jsonpath='{.status.containerStatuses[?(@.name=="app")].imageID}{"\n"}'
~~~

Dùng digest cố định trong Deployment thay vì chỉ dùng tag có thể bị thay đổi. Nếu image thay đổi giữa checkpoint và restore, cần xác minh các file được ánh xạ hoặc tham chiếu vẫn có cùng nội dung và ABI.

### 7.2. So sánh mount và volume

~~~bash
findmnt -R /
df -h
df -i
~~~

Đối chiếu source/target:

- Mount path có tồn tại không?
- Volume có đúng loại và nội dung không?
- File được tham chiếu có quyền đọc/ghi phù hợp không?
- Tmpfs có đủ dung lượng không?
- Secret/config mount có đúng revision không?
- Thư mục checkpoint có thể truy cập được không?

Nếu một resource không thể giữ an toàn qua checkpoint, ứng dụng cần đóng trước checkpoint và tạo lại sau restore qua CRaC callback. Không cố giữ socket hoặc file descriptor bên ngoài chỉ vì đường dẫn mount giống nhau.

## 8. Xác minh tài nguyên bộ nhớ và giới hạn container

Checkpoint có thể chứa lượng memory lớn. Node đích phải có đủ tài nguyên để CRIU/JVM map lại memory và tiếp tục hoạt động.

Kiểm tra trên node:

~~~bash
free -h
grep -E 'MemTotal|MemAvailable|HugePages|Hugepagesize' /proc/meminfo
ulimit -a
~~~

Kiểm tra trong Kubernetes:

~~~bash
kubectl describe node <NODE_NAME>
kubectl describe pod <POD_NAME>
kubectl top nodes
kubectl top pod <POD_NAME>
~~~

Cần đối chiếu:

- Memory request/limit của Pod.
- Memory khả dụng trên node tại thời điểm restore.
- Huge page nếu ứng dụng/JVM sử dụng.
- `ulimit` và giới hạn file descriptor/process.
- Cgroup memory limit và memory accounting.
- CPU request/limit và throttling.
- Ephemeral storage cho image/checkpoint nếu đặt trên node local.

Một node có đúng CPU feature nhưng thiếu RAM hoặc ephemeral storage vẫn có thể không restore được. Khi nhiều Pod restore đồng thời, cần tính tổng nhu cầu memory và tránh để scheduler dồn chúng vào một node.

## 9. Dùng Node Feature Discovery để phân loại CPU node

Kubernetes tự gắn một số label chuẩn lên Node, trong đó có:

- `kubernetes.io/arch`
- `kubernetes.io/os`
- `kubernetes.io/hostname`
- `node.kubernetes.io/instance-type` nếu kubelet/cloud provider cung cấp.

Các label này hữu ích để phân loại architecture và OS, nhưng **không mô tả đầy đủ CPU instruction set**. [Kubernetes: Node labels](https://kubernetes.io/docs/reference/node/node-labels/)

Nếu cluster có nhiều thế hệ CPU, Node Feature Discovery (NFD) có thể phát hiện hardware feature và công bố thành Node labels. Ví dụ:

~~~text
feature.node.kubernetes.io/cpu-cpuid.AVX2=true
feature.node.kubernetes.io/cpu-cpuid.AVX512F=true
feature.node.kubernetes.io/cpu-cpuid.AESNI=true
~~~

Tên label phụ thuộc feature source và cấu hình NFD. NFD ghi nhận CPU capability được hỗ trợ; một feature có thể được hỗ trợ ở phần cứng nhưng chưa được bật hoặc không được JVM sử dụng. Vì vậy, NFD giúp scheduler lọc node, còn JVM/CRIU vẫn phải thực hiện kiểm tra compatibility thực tế. [NFD: Feature labels](https://kubernetes-sigs.github.io/node-feature-discovery/master/usage/features.html)

### 9.1. Xem label trên node

~~~bash
kubectl get nodes --show-labels
kubectl get nodes -L kubernetes.io/arch,kubernetes.io/os,feature.node.kubernetes.io/cpu-cpuid.AVX2,feature.node.kubernetes.io/cpu-cpuid.AVX512F
~~~

Nếu NFD chưa được triển khai, có thể dùng label do quản trị viên gắn sau khi đã kiểm tra node. Không gắn nhãn chỉ dựa vào tên instance type hoặc CPU model do cloud provider quảng cáo.

Ví dụ label profile đã được xác minh:

~~~bash
kubectl label node <NODE_NAME> \
    crac.example.com/restore-profile=orders-amd64-v2
~~~

Chỉ gắn profile sau khi node vượt qua bộ kiểm tra tương thích. Có thể dùng admission policy hoặc quy trình provisioning để bảo đảm label không bị gắn nhầm.

### 9.2. Chọn node bằng nodeSelector

Với checkpoint chỉ chạy trên amd64:

~~~yaml
spec:
  nodeSelector:
    kubernetes.io/os: linux
    kubernetes.io/arch: amd64
    crac.example.com/restore-profile: orders-amd64-v2
~~~

Cách này đơn giản khi một nhóm node đã được gắn profile chung và được kiểm chứng.

### 9.3. Chọn node bằng node affinity và CPU features

Nếu muốn chọn dựa trên NFD label:

~~~yaml
spec:
  affinity:
    nodeAffinity:
      requiredDuringSchedulingIgnoredDuringExecution:
        nodeSelectorTerms:
          - matchExpressions:
              - key: kubernetes.io/os
                operator: In
                values:
                  - linux
              - key: kubernetes.io/arch
                operator: In
                values:
                  - amd64
              - key: feature.node.kubernetes.io/cpu-cpuid.AVX2
                operator: In
                values:
                  - "true"
~~~

Nếu image yêu cầu AVX-512, thêm điều kiện tương ứng với feature thực sự cần. Không yêu cầu AVX-512 chỉ vì node nguồn có nó; điều quan trọng là feature set mà JVM image đã sử dụng.

Kubernetes nodeSelector và node affinity chỉ kiểm tra label. Chúng không tự chạy CRIU hoặc phân tích checkpoint. Vì vậy, label phải được tạo từ một quy trình phát hiện/kiểm chứng đáng tin cậy. [Kubernetes: Assigning Pods to Nodes](https://kubernetes.io/docs/concepts/scheduling-eviction/assign-pod-node/)

## 10. Tạo profile tương thích cho từng checkpoint

Thay vì ghi chung "Linux amd64", hãy tạo profile mô tả các yêu cầu của checkpoint.

Ví dụ manifest do pipeline định nghĩa:

~~~yaml
checkpoint:
  id: orders-service-2.4.0-amd64-001
  createdAt: "2026-11-13T07:00:00Z"
  imageDirectory: ./checkpoint
  checksumFile: ./checkpoint.sha256

application:
  name: orders-service
  version: 2.4.0
  artifactDigest: "sha256:<digest>"

runtime:
  javaVendor: "<vendor>"
  javaVersion: "<full version and build>"
  javaArchitecture: amd64
  javaImageDigest: "sha256:<container-image-digest>"
  criuVersion: "<version>"
  criuEngine: criuengine

sourceNode:
  architecture: x86_64
  kernelRelease: "<uname -r>"
  osImage: "<distribution and version>"
  pageSize: 4096
  cpuModel: "<vendor and model>"
  cpuFeaturesUsed: "<output from ShowCPUFeatures>"
  cpuFlags: ["sse4_2", "avx", "avx2"]

restoreRequirements:
  os: linux
  architecture: amd64
  cpuFeatureProfile: orders-amd64-v2
  kernelFeatures: "criu-check-and-restore-test-required"
  requiredMounts:
    - "/run/app-config"
    - "/run/secrets"
  requiredCapabilities:
    - CHECKPOINT_RESTORE
    - SYS_PTRACE
  restoreTested: false
~~~

Đây là schema minh họa cho pipeline, không phải manifest chính thức của CRaC/CRIU. Các trường capability và mount phải phản ánh đúng runtime thực tế; không sao chép nguyên xi vào mọi cluster.

Manifest nên được ký hoặc bảo vệ cùng artifact. Không ghi secret value, password, token hoặc private key vào profile. Lưu checksum của checkpoint và container image để xác định chính xác bộ image đã được kiểm tra.

## 11. Quy trình kiểm tra node đích trước khi triển khai

Một quy trình thực tế có thể thực hiện theo các bước sau.

### Bước 1: Xác định đúng target node pool

Lấy danh sách node, architecture, OS và instance type:

~~~bash
kubectl get nodes -o wide
kubectl get nodes \
  -L kubernetes.io/arch,kubernetes.io/os,node.kubernetes.io/instance-type
~~~

Chia node theo architecture, CPU generation/feature profile, kernel baseline và container runtime. Không gom tất cả node amd64 vào một nhóm nếu chúng có feature set khác nhau.

### Bước 2: Thu thập CPU feature từ node và container

Trên từng loại node:

~~~bash
uname -m
lscpu
grep -m1 '^flags' /proc/cpuinfo
~~~

Sau đó chạy cùng JDK/container image dự kiến restore:

~~~bash
java -XX:+ShowCPUFeatures --version
java -version
~~~

Đối chiếu feature set mà JVM sẽ sử dụng. Nếu node chạy trong VM, hãy xác minh CPU feature mà guest và container nhìn thấy, không chỉ feature vật lý của hypervisor host.

### Bước 3: Kiểm tra kernel và CRIU

~~~bash
uname -r
criu --version
criu check
criu check --extra
~~~

Chạy trong môi trường có quyền tương đương Pod production. Nếu `criu check --extra` báo thiếu feature, xem xét process resource mà checkpoint sử dụng và đánh giá liệu thiếu feature đó có ảnh hưởng restore hay không.

### Bước 4: Kiểm tra quyền và mount

~~~bash
id
grep '^Cap' /proc/self/status
findmnt -R /
df -h
ulimit -a
~~~

Đối chiếu securityContext, mount, secret/config path, user ID, group ID và runtime class giữa môi trường tạo checkpoint và môi trường đích.

### Bước 5: Chạy canary restore trên từng profile node

Dùng đúng checkpoint, đúng image digest và đúng cấu hình Pod. Chọn ít nhất một node cho mỗi profile CPU/kernel/runtime khác nhau. Không chỉ test trên một node đại diện rồi giả định toàn bộ cluster tương thích nếu cluster có nhiều loại hardware.

### Bước 6: Kiểm tra application sau restore

Sau khi restore:

- CRaC `afterRestore` callbacks hoàn tất.
- Database/client/broker kết nối lại thành công.
- Readiness chỉ chuyển thành công sau khi dependency cần thiết hoạt động.
- Health endpoint phản hồi.
- Request đại diện chạy được.
- Không có lỗi CPU instruction, memory map, file descriptor, permission hoặc namespace.
- Memory/CPU usage nằm trong giới hạn Pod.

### Bước 7: Gắn label profile và triển khai

Chỉ sau khi canary restore thành công mới gắn label profile cho node pool và cho Deployment dùng `nodeSelector` hoặc node affinity để chọn đúng nhóm node.

## 12. Kiểm tra restore bằng đúng lệnh và đúng runtime

Với JDK CRaC, checkpoint thường được tạo bằng `-XX:CRaCCheckpointTo` và restore bằng `-XX:CRaCRestoreFrom`. [CRaC: Checkpoint and restore](https://crac.org/use/checkpoint-and-restore/)

Ví dụ:

~~~bash
"$JAVA_HOME/bin/java" \
    -XX:CRaCRestoreFrom=/opt/checkpoints/orders-service \
    -jar orders-service.jar
~~~

Cách gọi cụ thể phụ thuộc JDK/vendor và image layout. Một số quy trình restore khởi chạy trực tiếp từ image mà không truyền lại JAR như cold start; hãy dùng đúng command line được ghi nhận khi tạo checkpoint và tài liệu của runtime.

Không lấy một checkpoint được tạo bởi `simengine` làm bằng chứng cho CRIU restore. `simengine` mô phỏng callback cycle trong cùng process, không ghi và restore một process image thật. Muốn xác nhận node đích, phải dùng cùng loại engine tạo checkpoint production. [CRaC: Checkpoint engines](https://crac.org/reference/engines/)

### 12.1. Test trên cùng container image

Khi tạo Pod canary:

- Pin container image bằng digest.
- Dùng đúng JDK vendor/build.
- Dùng cùng RuntimeClass và securityContext.
- Mount cùng loại volume và path.
- Dùng cùng user/group.
- Giới hạn memory/CPU gần với cấu hình production.
- Đặt Pod lên node thuộc profile cần kiểm chứng.

Một lệnh restore chạy trên host với root privilege không chứng minh Pod production có cùng điều kiện.

### 12.2. Kiểm tra log CRIU và JVM

Khi restore thất bại, thu thập:

- Application stdout/stderr.
- Log CRaC/JVM.
- Log CRIU mà runtime tạo ra.
- Kubernetes Pod Events.
- Container exit code và restart count.
- Node kernel/runtime information.
- CPU feature output từ node đích.

Nếu log ứng dụng không đủ chi tiết, kiểm tra tùy chọn verbosity/log của CRIU theo JDK vendor. Không giả định đường dẫn log hoặc option engine giống nhau giữa các build.

## 13. Các lỗi tương thích thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Restore báo thiếu CPU feature | CPU đích thiếu instruction JVM đã sử dụng | Chọn node có feature phù hợp hoặc tạo checkpoint với baseline chung |
| Cùng amd64 nhưng restore thất bại | CPU microarchitecture, FPU hoặc XSAVE khác nhau | So sánh JVM feature set và CRIU CPU check |
| Restore chéo amd64/arm64 | Image process không tương thích kiến trúc | Tạo checkpoint riêng cho từng kiến trúc |
| `criu check` thất bại | Kernel thiếu feature hoặc CRIU không được cấp quyền | Kiểm tra kernel config, capability và runtime |
| `criu check` thành công nhưng restore lỗi | Check cơ bản không kiểm tra image cụ thể hoặc resource đặc thù | Đọc CRIU log và chạy restore test thật |
| `Operation not permitted` | Thiếu capability, SUID helper hoặc policy bảo mật chặn syscall | Kiểm tra securityContext, CRIU helper, seccomp và LSM |
| Không thể tạo lại PID | PID namespace, quyền hoặc PID conflict | Kiểm tra namespace, `ns_last_pid` và log CRIU |
| Không tìm thấy file/native library | Container image hoặc mount khác source | Dùng đúng image digest và mount layout |
| Memory mapping thất bại | Thiếu RAM, page/hugepage hoặc giới hạn cgroup | Kiểm tra memory availability, page size, huge pages và Pod limits |
| Restore trong Pod lỗi nhưng host test thành công | Container có capability/namespace/mount khác | Test trong cùng Pod security profile |
| Pod bị schedule lên node không phù hợp | Scheduler chỉ lọc architecture hoặc label thiếu chính xác | Dùng NFD/custom profile label và required node affinity |
| Checkpoint từ simengine "pass" nhưng CRIU fail | Simengine không tạo process image thật | Thực hiện canary bằng CRIU engine thật |

## 14. Xử lý CPU feature mismatch

Khi target thiếu CPU feature, có ba hướng xử lý:

### 14.1. Giữ checkpoint trong nhóm node có CPU tương thích

Đây là cách đơn giản nhất khi node pool có nhiều thế hệ CPU. Gắn label profile sau khi xác minh và dùng node affinity để Pod chỉ được schedule lên node phù hợp.

Ưu điểm là JVM vẫn dùng được các optimization đã có trong checkpoint. Nhược điểm là số node có thể chạy image bị giới hạn.

### 14.2. Tạo checkpoint mới với feature baseline thấp hơn

Nếu muốn checkpoint chạy trên nhiều node cùng kiến trúc, tạo checkpoint mới bằng JDK có hỗ trợ CPU feature baseline chung, ví dụ `-XX:CPUFeatures=generic`. Kiểm tra option của vendor và đánh giá ảnh hưởng hiệu năng trước khi dùng.

Đây là quyết định phải thực hiện **trước checkpoint**. Không thể lấy một image đã chứa JIT code phụ thuộc feature cao rồi yêu cầu JVM tự hạ cấp instruction khi restore.

### 14.3. Chia checkpoint theo CPU profile

Nếu cluster có các nhóm node rõ ràng, có thể tạo một checkpoint cho từng profile:

~~~text
checkpoint artifacts
├── orders-amd64-generic/
├── orders-amd64-avx2/
├── orders-amd64-avx512/
└── orders-arm64/
~~~

Mỗi artifact phải được tạo bằng JDK phù hợp, có manifest riêng và restore test riêng. Không đổi tên một checkpoint amd64 thành arm64 hoặc dùng chung image giữa các profile khác nhau.

## 15. Tích hợp kiểm tra vào pipeline và Kubernetes rollout

Không nên đợi tới lúc Pod production được schedule mới phát hiện node không tương thích. Hãy đưa kiểm tra vào pipeline tạo checkpoint và pipeline triển khai.

### 15.1. Pipeline tạo checkpoint

~~~text
BUILD APPLICATION
      │
      ▼
SELECT JDK + CONTAINER IMAGE
      │
      ▼
COLLECT SOURCE FINGERPRINT
  - architecture
  - JVM CPU features
  - kernel / CRIU
  - image digest
  - mounts / runtime
      │
      ▼
CREATE CHECKPOINT
      │
      ▼
WRITE MANIFEST + CHECKSUM
      │
      ▼
RESTORE TEST ON SOURCE PROFILE
      │
      ▼
PUBLISH CHECKPOINT ARTIFACT
~~~

### 15.2. Pipeline triển khai

~~~text
DISCOVER TARGET NODE POOL
      │
      ▼
COMPARE TARGET FINGERPRINT
      │
      ▼
CRIU CHECK + CPU FEATURE CHECK
      │
      ▼
CANARY RESTORE ON EACH PROFILE
      │
      ▼
SMOKE TEST + HEALTH CHECK
      │
      ▼
APPLY VERIFIED NODE LABELS
      │
      ▼
DEPLOY WITH REQUIRED NODE AFFINITY
~~~

Nếu node pool thay kernel, firmware, CPU model hoặc container runtime, profile cần được đánh giá lại. Không giữ label tương thích vô thời hạn nếu hạ tầng bên dưới đã thay đổi.

### 15.3. Triển khai theo từng nhóm node

Với nhiều node pool, có thể triển khai canary trước trên một nhóm đã xác minh, sau đó mở rộng dần. Giữ readiness false cho Pod cho tới khi restore và reconnect hoàn tất. Nếu restore fail, dừng rollout và thu log trước khi chuyển sang node pool khác.

Đừng tự động fallback sang node có CPU yếu hơn bằng cách bỏ qua kiểm tra. Nếu profile không tương thích, cần chọn artifact khác hoặc tạo checkpoint mới.

## 16. Checklist xác minh trước khi cho phép restore

Trước khi đánh dấu một node pool đủ điều kiện chạy checkpoint, cần có bằng chứng cho các mục sau:

- [ ] Node architecture trùng với architecture của checkpoint.
- [ ] Container image/JDK có đúng platform variant và digest đã kiểm chứng.
- [ ] JDK vendor, version và build tương thích.
- [ ] CPU feature set mà JVM đã sử dụng được node đích hỗ trợ.
- [ ] FPU/XSAVE và các capability liên quan không bị thiếu.
- [ ] CRIU version được JDK/vendor hỗ trợ.
- [ ] `criu check` và `criu check --extra` đã được thực hiện trong môi trường có quyền phù hợp.
- [ ] Kernel và namespace/cgroup feature đáp ứng yêu cầu.
- [ ] Container runtime, RuntimeClass và securityContext đã được xác minh.
- [ ] Capability, seccomp, AppArmor/SELinux và user namespace phù hợp.
- [ ] Mount, volume, file và native library cần thiết có mặt.
- [ ] RAM, huge pages, file descriptor và Pod resource limits đủ.
- [ ] Node label phản ánh đúng profile CPU/kernel đã kiểm chứng.
- [ ] Required node affinity giới hạn Pod vào nhóm node tương thích.
- [ ] Canary restore từ checkpoint thật đã thành công.
- [ ] Application smoke test và readiness check đã thành công.
- [ ] Manifest và log kiểm thử được lưu cùng artifact.

Checklist này là điều kiện vận hành để quyết định node pool có được phép nhận checkpoint hay không. Một số mục có thể khác nhau theo JDK vendor, CRIU engine và resource của ứng dụng; hãy ghi rõ ngoại lệ trong manifest.

## 17. Nguyên tắc vận hành

Hãy xem checkpoint là artifact gắn với một profile runtime cụ thể. Kiến trúc CPU là điều kiện đầu tiên; CPU feature, JDK build, kernel, CRIU, container runtime, quyền và filesystem quyết định khả năng restore thực tế.

Trong Kubernetes, dùng `kubernetes.io/arch` để loại node sai kiến trúc, dùng Node Feature Discovery hoặc custom profile label để chọn CPU node phù hợp, rồi áp dụng required node affinity. Scheduler chỉ dùng label; nó không thay thế việc kiểm tra CRIU và JVM.

Trước khi phát hành, hãy thu thập fingerprint ở source và target, chạy CRIU kernel checks trong đúng security context, xác nhận CPU feature set mà JVM sử dụng và thử restore trên mỗi nhóm node. Chỉ sau khi restore test cùng smoke test thành công mới đánh dấu node pool tương thích và cho phép Deployment sử dụng checkpoint đó.

## 18. Tài liệu tham khảo

- [CRaC: CPU features](https://crac.org/reference/cpu-features/): CPU feature mismatch, baseline generic và cách xác định feature set.
- [CRaC: Runtimes with CRaC support](https://crac.org/use/crac-runtime/): JDK CRaC và quyền cần cho CRIU engine.
- [CRaC: Checkpoint engines](https://crac.org/reference/engines/): phân biệt CRIU engine và simengine.
- [CRaC: Checkpoint and restore](https://crac.org/use/checkpoint-and-restore/): cách tạo và restore image.
- [CRIU: Check the kernel](https://criu.org/CLI/cmd/check): kiểm tra kernel feature cơ bản và mở rộng.
- [CRIU: CPU info](https://www.criu.org/CLI/cmd/cpuinfo): lưu và kiểm tra CPU capability.
- [OpenJDK CRaC README](https://github.com/openjdk/crac/blob/crac/README.md): yêu cầu CRIU và quyền cho runtime.
- [Kubernetes: Node labels](https://kubernetes.io/docs/reference/node/node-labels/): label architecture và OS chuẩn.
- [Kubernetes: Assigning Pods to Nodes](https://kubernetes.io/docs/concepts/scheduling-eviction/assign-pod-node/): nodeSelector và node affinity.
- [Node Feature Discovery: Feature labels](https://kubernetes-sigs.github.io/node-feature-discovery/master/usage/features.html): công bố CPU feature thành node label.


