# Khác biệt kernel, thư viện hệ thống và môi trường native

CRaC (Coordinated Restore at Checkpoint) cho phép lưu trạng thái một tiến trình Java rồi khôi phục tiến trình đó trong một môi trường tương thích. Vì checkpoint chứa trạng thái tiến trình ở cấp JVM và hệ điều hành, khả năng restore phụ thuộc vào nhiều yếu tố bên ngoài bytecode Java: kernel, kiến trúc CPU, thư viện native, dynamic linker, filesystem, namespace, cấu hình bảo mật và runtime container.

Một ứng dụng có thể chạy bình thường trên hai máy Linux nhưng checkpoint được tạo trên máy thứ nhất vẫn không restore an toàn trên máy thứ hai. Hai máy có thể khác kernel feature, ABI của thư viện, CPU instruction set, mount, network namespace hoặc quyền hệ thống. Các khác biệt này ảnh hưởng đến những tài nguyên mà tiến trình đang sử dụng tại thời điểm tạo ảnh.

Vì vậy, khi triển khai CRaC, cần xác định rõ **ranh giới tương thích của checkpoint**. Hãy xem checkpoint như một artifact gắn với một nền tảng runtime cụ thể, mô tả các điều kiện đã được kiểm chứng và restore trong một môi trường đáp ứng các điều kiện đó. Việc dùng cùng một file JAR hoặc cùng phiên bản Java chưa đủ để chứng minh hai môi trường tương thích.

## 1. Vì sao kernel và môi trường native quan trọng?

Một chương trình Java không chỉ chạy bằng bytecode. JVM là một tiến trình native được xây dựng cho hệ điều hành và kiến trúc CPU cụ thể. JVM sử dụng system call, memory mapping, thread, signal, file descriptor, socket và thư viện native.

Khi checkpoint, cơ chế ở cấp hệ điều hành cần lưu và khôi phục trạng thái tiến trình. Trên Linux, các giải pháp CRaC thường phối hợp với CRIU (Checkpoint/Restore In Userspace) để xử lý trạng thái tiến trình. CRIU tương tác với kernel nhằm lưu và phục hồi những thành phần như:

- Tiến trình và quan hệ giữa các process.
- Thread, trạng thái CPU và signal.
- Vùng nhớ và memory mapping.
- File descriptor và một số loại tài nguyên kernel.
- Socket và trạng thái mạng trong các điều kiện được hỗ trợ.
- Namespace và các tài nguyên liên quan đến môi trường chạy.

JDK CRaC bổ sung sự phối hợp ở tầng Java để ứng dụng có thể chuẩn bị tài nguyên trước checkpoint và phục hồi sau restore thông qua các callback như `beforeCheckpoint()` và `afterRestore()`.

~~~mermaid
flowchart TD
    A["Java application"] --> B["JVM runtime"]
    B --> C["Native libraries and JNI"]
    B --> D["Linux system calls"]
    D --> E["Kernel process state"]
    D --> F["Filesystem and file descriptors"]
    D --> G["Network stack and namespaces"]
    H["CRaC integration"] --> I["CRIU checkpoint/restore"]
    I --> E
    I --> F
    I --> G
    H --> B
~~~

Sơ đồ cho thấy checkpoint nằm ở nhiều lớp. Nếu một lớp không đáp ứng điều kiện restore, tiến trình có thể không khôi phục được hoặc khôi phục nhưng hoạt động sai khi sử dụng tài nguyên đó.

### 1.1. Java bytecode có tính di động, checkpoint thì không tương đương JAR

Bytecode Java thường có thể chạy trên nhiều hệ điều hành và kiến trúc nếu có JVM phù hợp. Checkpoint lại chứa trạng thái của một tiến trình cụ thể, bao gồm cả thông tin native và kernel.

| Artifact | Nội dung chính | Phạm vi di động |
|---|---|---|
| JAR / class files | Bytecode và resource ứng dụng | Có thể dùng trên nhiều nền tảng có JDK phù hợp |
| Native library | Mã máy theo ABI và kiến trúc | Phụ thuộc OS, CPU, linker và thư viện hệ thống |
| JVM process | Heap, thread, runtime và native state | Gắn với runtime và môi trường đang chạy |
| CRaC checkpoint | Trạng thái tiến trình tại thời điểm lưu | Phụ thuộc mạnh vào điều kiện checkpoint/restore |

Một JAR có thể chạy trên cả hai host trong khi checkpoint của tiến trình từ host A không thể restore trực tiếp trên host B. Đây là lý do quy trình phát hành checkpoint cần kiểm tra môi trường ở cả hai đầu.

## 2. Vai trò của Linux kernel

Kernel cung cấp các cơ chế mà JVM và CRIU cần để quản lý tiến trình. Phiên bản kernel là một phần quan trọng của môi trường tương thích, nhưng chỉ so sánh số phiên bản kernel là chưa đủ.

Hai máy có cùng chuỗi phiên bản kernel vẫn có thể khác:

- Kernel configuration.
- Các module đã nạp.
- Namespace được bật hoặc giới hạn.
- Cgroup mode và controller.
- Quyền truy cập system call.
- Security module và policy.
- Filesystem driver và mount option.
- Network stack, route và interface.
- Các feature được phân phối kernel bật hoặc tắt.

Ngược lại, kernel có phiên bản khác nhau đôi khi vẫn tương thích cho một workload cụ thể nếu các tính năng cần thiết và điều kiện CRIU được đáp ứng. Không nên tự suy ra điều đó chỉ từ số phiên bản; cần kiểm tra tài liệu và thử restore thực tế.

### 2.1. Kernel feature và CRIU

CRIU cần các khả năng kernel phù hợp để dump và restore tiến trình. Khả năng cụ thể phụ thuộc vào loại tài nguyên tiến trình đang sử dụng và phiên bản CRIU.

Ví dụ, một ứng dụng có thể dùng:

- Thread và process state.
- Memory mapping và shared memory.
- Unix domain socket.
- TCP connection.
- File descriptor.
- Namespace.
- Mount và file lock.
- Một số loại IPC hoặc thiết bị.

Không phải mọi loại tài nguyên đều được hỗ trợ trong mọi cấu hình. Một số tính năng cần quyền đặc biệt hoặc yêu cầu kernel mới hơn. Một số tài nguyên phải được ứng dụng đóng trước checkpoint vì không thể khôi phục đáng tin cậy.

Hãy kiểm tra ma trận hỗ trợ của CRIU và JDK CRaC đang dùng. Khi một lỗi dump hoặc restore xuất hiện, log của CRIU và kernel thường cung cấp thông tin chi tiết hơn lỗi Java ở phía ứng dụng.

### 2.2. Kernel version không phải tiêu chí duy nhất

Ví dụ, hai container có thể cùng chạy trên một host kernel, nhưng container A có quyền và namespace phù hợp trong khi container B bị giới hạn bởi seccomp hoặc capability. Kết quả checkpoint/restore có thể khác nhau dù `uname -r` giống nhau.

Một môi trường cần được mô tả bằng nhiều yếu tố:

- Kernel release và build.
- CRIU version.
- JDK distribution và version.
- Container runtime và cấu hình.
- Namespace và capability.
- Seccomp, AppArmor hoặc SELinux policy.
- Cgroup version và resource limit.
- Filesystem và mount layout.
- CPU architecture và feature set.

### 2.3. Kiểm tra kernel và CRIU

Các lệnh Linux dưới đây giúp thu thập thông tin môi trường:

~~~bash
uname -a
uname -r
cat /proc/version
criu --version
criu check
~~~

`criu check` là bước kiểm tra khả năng của CRIU trong môi trường hiện tại. Kết quả không thay thế việc thử dump/restore một workload thực tế, nhưng giúp phát hiện sớm một số thiếu hụt của kernel hoặc quyền hệ thống.

Nếu CRIU không có trong image ứng dụng, hãy chạy kiểm tra ở môi trường host hoặc tool image có quyền phù hợp. Container application không nhất thiết được phép tự kiểm tra mọi khả năng kernel.

## 3. Khác biệt giữa host và container

Container chia sẻ kernel của host nhưng có thể có namespace, cgroup, filesystem và security policy riêng. Vì vậy, cùng một image container có thể hoạt động khác nhau trên hai host hoặc hai cấu hình runtime.

Các thành phần cần xem xét:

- PID namespace.
- Mount namespace.
- Network namespace.
- User namespace.
- IPC namespace.
- UTS namespace.
- Cgroup namespace và resource controller.
- Bind mount và volume.
- Capability và seccomp profile.
- Runtime như containerd hoặc CRI-O.
- Chính sách orchestration như Kubernetes.

### 3.1. PID namespace

PID namespace tạo góc nhìn process riêng cho container. CRIU cần khôi phục process trong một quan hệ PID phù hợp với namespace và môi trường đích.

Nếu checkpoint được tạo trong một cấu hình namespace nhưng restore trong cấu hình khác, PID mapping hoặc quan hệ process có thể không phù hợp. Cần tuân theo cách CRIU và runtime quản lý container checkpoint/restore.

Không nên giả định rằng chỉ cần chạy lại cùng container image là mọi process ID và process relationship sẽ được giữ nguyên.

### 3.2. User namespace và quyền hệ thống

User namespace có thể ánh xạ UID/GID bên trong container sang UID/GID khác trên host. Điều này ảnh hưởng đến quyền sở hữu file, capability và quyền truy cập tài nguyên.

Một tiến trình có thể mở được file khi tạo checkpoint nhưng không có quyền tương ứng trong môi trường restore. Hoặc file được khôi phục với ownership không phù hợp.

Cần kiểm tra:

- UID/GID mapping.
- Linux capabilities.
- Quyền trên file và directory.
- Quyền truy cập device.
- Quyền thực hiện các thao tác checkpoint/restore.
- Security policy áp dụng cho process.

### 3.3. Mount namespace và volume

Một container có thể nhìn thấy filesystem qua mount namespace riêng. Đường dẫn trong container có thể trỏ đến bind mount hoặc volume khác nhau giữa hai host.

Ví dụ, ứng dụng mở `/var/lib/app/data.db` trước checkpoint. Khi restore, đường dẫn đó có thể:

- Không còn được mount.
- Trỏ đến volume khác.
- Có ownership hoặc permission khác.
- Có nội dung đã thay đổi.
- Được mount với option khác.
- Nằm trên filesystem không hỗ trợ hành vi cần thiết.

Nếu file descriptor được giữ trong checkpoint, khả năng sử dụng sau restore phụ thuộc vào hỗ trợ của cơ chế checkpoint và tính tương thích của mount/file. Với file quan trọng, cần kiểm tra trạng thái và nội dung sau restore thay vì chỉ dựa vào việc descriptor tồn tại.

### 3.4. Network namespace

Network namespace chứa interface, địa chỉ IP, route và các thành phần mạng của container. Môi trường restore có thể có địa chỉ hoặc route khác.

Một socket đã được mở trước checkpoint có thể phụ thuộc vào địa chỉ local, port, route hoặc network namespace cũ. Với outbound connection đến database, broker hoặc dịch vụ HTTP, ứng dụng thường nên đóng và tạo lại connection theo callback CRaC. Với listening socket, phải kiểm tra cách runtime khôi phục port và tránh bind lại một cách mù quáng.

### 3.5. Cgroup và resource limit

Cgroup quản lý giới hạn CPU, memory, process và một số tài nguyên khác. Restore trong cgroup có giới hạn khác có thể làm ứng dụng:

- Không đủ memory để khôi phục heap hoặc native allocation.
- Không đủ PID/thread quota để tạo worker.
- Bị throttling CPU khi JIT hoặc warm-up.
- Gặp giới hạn I/O hoặc file descriptor.
- Không khởi động được các background thread cần thiết.

Cần kiểm tra cgroup version, controller và giới hạn thực tế tại môi trường restore. Không chỉ so sánh cấu hình trong manifest; hãy kiểm tra giá trị mà process thực sự nhận được.

## 4. Thư viện native và ABI

Java application có thể gọi native code thông qua JNI, Foreign Function & Memory API hoặc thư viện gián tiếp phụ thuộc vào native library. Các thành phần này làm tăng ranh giới tương thích.

ABI (Application Binary Interface) xác định cách mã máy tương tác ở mức nhị phân, bao gồm calling convention, symbol, kiểu dữ liệu và quy tắc liên kết. Native library được build cho một ABI cụ thể không nhất thiết hoạt động trên môi trường khác.

### 4.1. JNI library

Một ứng dụng có thể nạp native library:

~~~java
public final class NativeCrypto {
    static {
        System.loadLibrary("nativecrypto");
    }

    public native byte[] digest(byte[] input);
}
~~~

File `libnativecrypto.so` phải phù hợp với:

- CPU architecture.
- ABI của hệ điều hành.
- Dynamic linker.
- Các thư viện phụ thuộc.
- Phiên bản symbol mà binary yêu cầu.
- Cấu hình runtime của tiến trình.

Nếu library đã được nạp trước checkpoint, trạng thái native của nó có thể nằm trong tiến trình. Restore cần môi trường tương thích với những mapping và tài nguyên native đó. Nếu library phụ thuộc vào thiết bị, thread nội bộ hoặc daemon riêng, cần kiểm tra khả năng checkpoint/restore cụ thể.

### 4.2. glibc và musl

Linux distribution có thể dùng glibc hoặc musl làm C library. Binary được build cho một môi trường không nhất thiết chạy được trong môi trường còn lại.

Ví dụ, một native library build trong image dùng glibc có thể phụ thuộc vào symbol version không có trong image restore. Một binary build cho musl có thể cần dynamic linker và runtime musl tương ứng.

Không nên xem việc cả hai môi trường đều là Linux là đủ. Cần kiểm tra:

- Loại libc.
- Phiên bản libc.
- Dynamic loader path.
- Symbol version.
- Các thư viện C/C++ phụ thuộc.
- Cấu hình tìm kiếm thư viện.

Các lệnh thường dùng:

~~~bash
file libnativecrypto.so
ldd libnativecrypto.so
readelf -h libnativecrypto.so
readelf -d libnativecrypto.so
readelf --version-info libnativecrypto.so
~~~

`ldd` có thể hữu ích để xem dependency trong môi trường tin cậy. Với binary không tin cậy, nên ưu tiên công cụ phân tích ELF không thực thi binary. Kết quả cần được kiểm tra trong đúng container image và runtime.

### 4.3. C++ runtime và các thư viện phụ thuộc

Native component viết bằng C++ có thể phụ thuộc vào:

- `libstdc++`.
- `libgcc_s`.
- OpenSSL.
- zlib.
- libcurl.
- Thư viện compression hoặc image processing.
- Thư viện database client.
- Driver hoặc SDK của nhà cung cấp.

Khác phiên bản có thể gây thiếu symbol, thay đổi ABI hoặc thay đổi hành vi. Đừng chỉ kiểm tra file thư viện chính; cần kiểm tra toàn bộ dependency chain.

### 4.4. Native library có trạng thái nội bộ

Một thư viện native có thể tạo thread riêng, giữ mutex, file descriptor, shared memory, timer hoặc handle đến thiết bị. Những tài nguyên này có vòng đời độc lập với object Java gọi chúng.

Trước checkpoint, cần xác định thư viện có hỗ trợ checkpoint/restore hay không. Nếu không, hãy gọi API shutdown/close của thư viện và tạo lại instance sau restore. Đừng giả định garbage collection hoặc việc giữ nguyên Java wrapper sẽ khôi phục trạng thái native.

## 5. Khác biệt CPU architecture và instruction set

Checkpoint chứa trạng thái tiến trình đã chạy trên một kiến trúc CPU cụ thể. Restore trên kiến trúc khác thường không phải một phép chuyển đổi đơn giản.

Các yếu tố gồm:

- x86-64, AArch64 hoặc kiến trúc khác.
- Endianness.
- Kích thước page và memory layout.
- CPU feature flags.
- SIMD instruction set như SSE, AVX, AVX2 hoặc AVX-512.
- Các extension CPU mà JVM hoặc native library sử dụng.
- Mã máy đã được JIT compiler sinh ra.

### 5.1. Cùng kiến trúc không có nghĩa CPU feature giống nhau

Hai host đều là x86-64 nhưng có thể khác AVX2 hoặc AVX-512. Native library hoặc JIT code có thể sử dụng instruction set có trên máy tạo checkpoint nhưng không có trên máy restore.

Một số JVM có cơ chế chọn tập instruction phù hợp và có thể kiểm soát CPU feature được sử dụng. Tuy nhiên, checkpoint/restore vẫn cần tuân theo hỗ trợ của JDK và nền tảng. Không nên tự giả định JIT code sẽ được biên dịch lại hoàn toàn hoặc tự động thích nghi trong mọi trường hợp.

Cách an toàn là tạo và restore checkpoint trên nhóm host có CPU feature tương thích, hoặc dùng một baseline CPU chung đã được xác nhận.

### 5.2. Kiểm tra CPU

Trên Linux:

~~~bash
uname -m
lscpu
grep -m1 '^flags' /proc/cpuinfo
~~~

Ghi nhận architecture và các CPU flags trên cả môi trường tạo checkpoint lẫn môi trường restore. Nếu chạy trên cloud hoặc Kubernetes, kiểm tra cả loại instance/node pool và cấu hình CPU model mà hypervisor cung cấp.

### 5.3. JIT và mã native được tạo trong runtime

HotSpot có thể biên dịch method thành mã máy theo CPU feature được phát hiện. Checkpoint có thể chứa trạng thái runtime liên quan đến mã đã biên dịch. Do đó, khác biệt CPU không chỉ ảnh hưởng đến JNI library được đóng gói cùng ứng dụng mà còn có thể ảnh hưởng đến code do JVM tạo ra.

Hãy tham khảo tài liệu JDK CRaC cho đúng phiên bản và kiểm tra các ràng buộc CPU. Nếu cần hỗ trợ nhiều loại host, hãy tạo checkpoint riêng cho từng nhóm nền tảng đã xác nhận tương thích.

## 6. Dynamic linker và thứ tự nạp thư viện

Dynamic linker tìm và nạp shared library khi tiến trình khởi động hoặc khi ứng dụng yêu cầu load library. Kết quả phụ thuộc vào:

- ELF interpreter được ghi trong binary.
- `LD_LIBRARY_PATH`.
- `RPATH` hoặc `RUNPATH`.
- Cấu hình `ld.so.cache`.
- Thư mục thư viện hệ thống.
- Symbol version và dependency chain.

Một checkpoint được tạo khi library đã được map vào tiến trình có thể giữ những mapping đó. Tuy nhiên, các lần nạp library sau restore, việc tạo native component mới hoặc việc mở lại resource vẫn phụ thuộc môi trường filesystem và linker hiện tại.

Không nên thay thư viện trong image container sau khi checkpoint được tạo mà vẫn kỳ vọng trạng thái native cũ tương thích. Hãy xem base image, native package và JDK là một phần của định danh checkpoint.

## 7. Filesystem, file descriptor và memory mapping

Ứng dụng Java thường sử dụng file thông qua stream, channel, memory mapping hoặc native library. Một số trạng thái có thể được checkpoint, nhưng khả năng khôi phục phụ thuộc loại file và filesystem.

Các khác biệt đáng chú ý:

- ext4, XFS, overlayfs, tmpfs hoặc filesystem mạng.
- Mount option.
- Bind mount và volume identity.
- File descriptor đang mở.
- File lock và advisory lock.
- Memory-mapped file.
- File đã bị đổi tên hoặc thay thế.
- Nội dung file đã thay đổi trong lúc checkpoint.
- Permission, ownership và SELinux label.

### 7.1. File descriptor không chỉ là một số nguyên

Trong process, file descriptor là một handle đến open file description hoặc tài nguyên kernel. Giá trị số như 17 không đủ để mô tả resource có thể dùng ở môi trường khác.

Nếu ứng dụng giữ file descriptor xuyên qua checkpoint, hãy kiểm tra loại tài nguyên đó có được CRIU hỗ trợ và filesystem ở đích có tương thích hay không. Với file tạm, file lock hoặc file được quản lý bởi ứng dụng, thường an toàn hơn khi đóng trước checkpoint và mở lại sau restore.

### 7.2. Memory-mapped file

Memory mapping liên kết vùng nhớ của tiến trình với file hoặc tài nguyên backing. Nếu file bị thay đổi, thay thế hoặc mount khác sau checkpoint, mapping có thể không còn mang ý nghĩa mà ứng dụng kỳ vọng.

Các ứng dụng dùng mapped file cho index, database hoặc cache cần có chính sách kiểm tra version và mở lại mapping sau restore nếu dữ liệu nguồn có thể thay đổi.

### 7.3. File lock

Một file lock có thể được quản lý bởi kernel hoặc filesystem. Không nên giả định lock còn thuộc quyền sở hữu của ứng dụng sau khi tiến trình bị checkpoint và khôi phục trong một môi trường khác.

Với lock dùng để bảo vệ dữ liệu, hãy xác minh ownership và trạng thái lock sau restore. Nếu lock là distributed lock hoặc lease, cần kiểm tra thời hạn và fencing token ở hệ thống quản lý lock.

## 8. Network stack và các thư viện hệ thống

Kết nối mạng phụ thuộc vào kernel, network namespace, interface, route, firewall, NAT và peer ở xa. Cùng một Java client có thể hoạt động khác nhau khi restore ở host khác.

Các khác biệt có thể bao gồm:

- Địa chỉ IP local.
- Route và gateway.
- DNS resolver.
- Network namespace.
- Port allocation.
- Firewall và network policy.
- NAT mapping.
- Proxy và load balancer.
- TLS library và trust store.
- Kernel TCP behavior.

Với outbound connection đến database, Redis, Kafka hoặc HTTP service, ứng dụng thường nên drain và đóng kết nối trước checkpoint, rồi tạo connection mới sau restore theo cấu hình hiện tại.

Với listening socket, cần xác định socket có được CRIU/runtime hỗ trợ restore trong môi trường đó hay không. Nếu listener đã được khôi phục và port vẫn được giữ, bind lại có thể gây lỗi address already in use. Nếu listener không được khôi phục, ứng dụng phải mở listener mới trước khi báo readiness.

### 8.1. DNS và resolver

DNS có thể thay đổi trong thời gian checkpoint. Một connection TCP đã thiết lập không tự chuyển sang địa chỉ mới khi DNS record thay đổi. Sau restore, tạo connection mới sẽ dùng resolver và cache theo cấu hình hiện tại, nhưng JVM hoặc thư viện có thể giữ DNS cache.

Hãy kiểm tra TTL, resolver configuration và chính sách DNS cache của JVM. Với dịch vụ dùng service discovery, nên refresh endpoint trước khi reconnect.

### 8.2. OpenSSL và TLS

Một native TLS library có thể phụ thuộc vào phiên bản OpenSSL, provider, certificate store và cấu hình cipher. Nếu môi trường restore khác, handshake mới có thể thất bại hoặc chọn thuật toán khác.

Sau restore, nên tạo lại connection và thực hiện handshake theo trust configuration hiện tại. Không giữ TLS session hoặc credential trong heap mà không kiểm tra expiry và chính sách bảo mật.

## 9. Security policy: seccomp, AppArmor và SELinux

Checkpoint/restore cần một số thao tác hệ thống có thể bị giới hạn bởi security policy. Trong container, seccomp profile có thể chặn system call. Linux capabilities quyết định process có được thực hiện một số thao tác quản trị hay không. AppArmor và SELinux có thể giới hạn quyền truy cập file, socket hoặc process.

Hai môi trường có cùng kernel nhưng policy khác nhau có thể cho kết quả khác.

Cần xem xét:

- Seccomp profile và system call được phép.
- Linux capabilities được cấp.
- AppArmor profile.
- SELinux mode, type và label.
- Quyền truy cập /proc và /sys.
- Quyền truy cập CRIU image directory.
- Quyền truy cập mount và file descriptor.
- User namespace mapping.

Không nên giải quyết lỗi bằng cách tắt toàn bộ cơ chế bảo mật. Hãy xác định thao tác cụ thể bị chặn, sau đó dùng policy tối thiểu đáp ứng yêu cầu của CRaC/CRIU và nền tảng.

## 10. Locale, timezone, environment và cấu hình runtime

Một số trạng thái môi trường được đọc lúc JVM khởi động hoặc lúc thư viện native được nạp. Sau restore, tiến trình có thể vẫn giữ giá trị cũ dù environment bên ngoài đã thay đổi.

Các giá trị cần quan tâm:

- `TZ` và timezone database.
- Locale và character encoding.
- `LANG` và `LC_*`.
- `PATH` và `LD_LIBRARY_PATH`.
- Proxy environment variables.
- Trust store và certificate path.
- Secret mount.
- JVM system properties.
- Native library configuration.
- File cấu hình và feature flags.

Không phải mọi biến môi trường đều được đọc lại sau restore. Một số thư viện cache giá trị trong static field hoặc native state. Nếu cấu hình có thể thay đổi giữa các lần chạy, cần có cơ chế refresh rõ ràng thay vì giả định process tự nhận giá trị mới.

## 11. JDK distribution và native runtime

JDK CRaC là một phần của môi trường checkpoint. Hai JDK cùng ghi một số version Java nhưng được build khác nhau có thể khác:

- Vendor và build.
- CRaC patch hoặc integration.
- JVM implementation.
- GC và compiler.
- Native library được đóng gói.
- Default JVM flags.
- Module và security provider.
- Cách tích hợp với CRIU.

Checkpoint nên được tạo và restore bằng JDK distribution/version được xác nhận tương thích. Tránh thay JDK image hoặc cập nhật package native giữa hai giai đoạn mà không tạo và kiểm thử checkpoint mới.

### 11.1. Kiểm tra runtime Java

Có thể ghi nhận:

~~~bash
java -version
java -XshowSettings:properties -version
~~~

Các thông tin nên lưu cùng checkpoint manifest:

- JDK vendor.
- Java runtime version và build.
- JVM flags.
- GC configuration.
- CRaC support/version.
- Native library paths.
- Module hoặc provider quan trọng.

### 11.2. Không thay thế JDK chỉ dựa vào cùng major version

Ví dụ, hai image cùng báo Java 21 nhưng khác vendor build, CRaC patch hoặc native library. Điều đó không chứng minh checkpoint tạo bởi image này có thể restore bởi image kia.

Giữ nguyên image digest hoặc tạo một build mới và thực hiện lại quy trình warm-up/checkpoint khi nâng cấp runtime. Với thay đổi security patch, hãy đánh giá cả yêu cầu bảo mật lẫn tương thích và phát hành checkpoint mới đã kiểm thử.

## 12. Ma trận tương thích giữa môi trường tạo ảnh và restore

Không cần mọi trường hợp đều phải giống nhau tuyệt đối. Điều quan trọng là xác định yếu tố nào bắt buộc tương thích, yếu tố nào được phép khác và bằng chứng kiểm thử cho mỗi tổ hợp.

| Thành phần | Nên giữ tương thích | Có thể thay đổi khi nào? |
|---|---|---|
| CPU architecture | Cùng kiến trúc được hỗ trợ | Chỉ khi CRaC/runtime xác nhận hỗ trợ |
| CPU features | Tập feature tương thích với code native/JIT | Khi dùng baseline chung đã kiểm thử |
| JDK distribution/build | Cùng bản đã xác nhận | Khi tạo checkpoint mới và kiểm thử |
| Kernel | Đủ kernel feature CRIU cần | Khi CRIU/JDK hỗ trợ và restore đã kiểm thử |
| CRIU | Version và image format tương thích | Theo ma trận tương thích của CRIU |
| libc/dynamic linker | ABI và symbol dependency phù hợp | Khi binary được build tương thích |
| Native libraries | Cùng ABI và dependency chain | Khi library được chứng minh tương thích |
| Filesystem/mount | Resource và mount cần thiết còn đúng | Khi không phụ thuộc file/mapping cũ |
| Namespace | Process và resource mapping tương thích | Theo runtime và CRIU support |
| Security policy | Cho phép các thao tác cần thiết | Khi policy mới đã được kiểm thử |
| Network | Endpoint và route có thể thiết lập lại | Thường có thể đổi nếu app reconnect |
| Secret/configuration | Phải hợp lệ ở môi trường đích | Có thể refresh qua provider sau restore |

Bảng là hướng dẫn thiết kế, không phải cam kết tương thích chính thức cho mọi bản CRaC. Ma trận cuối cùng phải dựa vào tài liệu JDK, CRIU, kernel và kết quả thử nghiệm.

## 13. Xây dựng checkpoint manifest

Nên tạo manifest đi cùng mỗi checkpoint để biết ảnh được tạo trong môi trường nào. Manifest không làm cho ảnh trở nên portable, nhưng giúp phát hiện sai khác trước khi restore.

Ví dụ nội dung manifest:

~~~yaml
checkpoint:
  applicationVersion: "2026.11.13"
  imageDigest: "sha256:..."
  createdAt: "2026-11-13T08:00:00Z"

runtime:
  jdkVendor: "Example JDK distribution"
  javaVersion: "21"
  jdkBuild: "record-exact-build"
  jvmFlags:
    - "-Xms512m"
    - "-Xmx512m"

platform:
  os: "Linux"
  architecture: "x86_64"
  kernelRelease: "record-exact-kernel"
  libc: "glibc"
  libcVersion: "record-version"
  criuVersion: "record-version"
  containerRuntime: "containerd"
  cgroupMode: "v2"

native:
  libraries:
    - "libexample.so"
    - "libssl.so"
  cpuBaseline: "record-supported-feature-set"

security:
  seccompProfile: "record-profile-version"
  capabilities:
    - "record-required-capability"

restorePolicy:
  allowedNodePool: "crac-compatible-pool"
  requiresNetworkReconnect: true
  requiresNativeResourceReinitialization: true
~~~

Các giá trị trong ví dụ là placeholder. Hãy điền dữ liệu thực tế từ build pipeline và host/container nơi checkpoint được tạo. Không ghi password, token, private key hoặc secret vào manifest.

### 13.1. Manifest và image digest

Nên gắn checkpoint với image digest thay vì chỉ tag như `latest`. Tag có thể được trỏ sang image khác sau khi checkpoint được tạo. Digest giúp xác định chính xác container image chứa JDK, libc và native package.

Nếu image được cập nhật, hãy tạo checkpoint mới theo quy trình đã kiểm chứng. Không thay đổi các file thư viện bên trong image rồi tiếp tục dùng checkpoint cũ.

## 14. Quy trình build và kiểm tra môi trường

Một quy trình có thể chia thành các giai đoạn:

~~~mermaid
flowchart TD
    A["Build application image"] --> B["Pin JDK and native dependencies"]
    B --> C["Record OS, CPU and CRIU baseline"]
    C --> D["Run CRIU capability checks"]
    D --> E["Start application and warm up"]
    E --> F["Prepare resources through CRaC"]
    F --> G["Create checkpoint"]
    G --> H["Store checkpoint with manifest"]
    H --> I["Select compatible restore node"]
    I --> J["Compare environment with manifest"]
    J --> K{"Compatibility checks pass?"}
    K -->|No| L["Reject restore or rebuild checkpoint"]
    K -->|Yes| M["Restore and run smoke checks"]
    M --> N["Open readiness"]
~~~

### Bước 1: Pin nền tảng

Chọn JDK distribution, base image, libc, native libraries và architecture. Tránh dùng package floating version trong image tạo checkpoint.

### Bước 2: Ghi nhận host và container

Thu thập kernel release, CRIU version, CPU architecture, CPU features, cgroup mode, namespace, mount và security policy.

### Bước 3: Kiểm tra CRIU

Chạy kiểm tra khả năng CRIU trong môi trường thực tế. Xác nhận quyền và tính năng kernel cần thiết.

### Bước 4: Chạy ứng dụng và warm-up

Khởi động ứng dụng trong image đã pin. Làm nóng workload đại diện và chuẩn bị cache theo chính sách.

### Bước 5: Chuẩn bị native resource

Đóng hoặc làm mới connection, file descriptor, thread, native handle và resource mà thư viện không hỗ trợ restore. Dùng CRaC Resource hoặc integration của thư viện.

### Bước 6: Tạo checkpoint và manifest

Tạo ảnh bằng quy trình được JDK CRaC hỗ trợ. Lưu manifest và image digest cùng artifact.

### Bước 7: Chọn môi trường restore

Chỉ đưa ảnh đến node pool hoặc host có kernel, CPU, JDK, native dependency và policy tương thích.

### Bước 8: Kiểm tra trước restore

So sánh manifest với môi trường đích. Nếu thiếu điều kiện bắt buộc, từ chối restore và tạo checkpoint mới trong nền tảng đích.

### Bước 9: Smoke test sau restore

Kiểm tra ứng dụng, native library, database, Redis, broker, filesystem và endpoint thiết yếu. Chỉ mở readiness sau khi các kiểm tra thành công.

## 15. Kiểm tra khác biệt bằng lệnh hệ thống

Các lệnh sau giúp thu thập bằng chứng. Chạy ở cả môi trường tạo checkpoint và môi trường restore, rồi lưu kết quả cùng manifest.

### 15.1. Kernel và OS

~~~bash
uname -a
cat /etc/os-release
cat /proc/version
~~~

### 15.2. CPU architecture và feature

~~~bash
uname -m
lscpu
grep -m1 '^flags' /proc/cpuinfo
~~~

### 15.3. JDK và CRIU

~~~bash
java -version
criu --version
criu check
~~~

### 15.4. Cgroup

Trên hệ thống sử dụng cgroup v2, có thể kiểm tra:

~~~bash
stat -fc %T /sys/fs/cgroup
cat /proc/self/cgroup
~~~

Kết quả `cgroup2fs` thường cho biết filesystem cgroup v2 được mount tại vị trí kiểm tra. Cần đọc thêm cấu hình controller và limit áp dụng cho container.

### 15.5. Namespace

Có thể xem namespace của process hiện tại:

~~~bash
ls -l /proc/self/ns
readlink /proc/self/ns/pid
readlink /proc/self/ns/mnt
readlink /proc/self/ns/net
readlink /proc/self/ns/user
~~~

Namespace inode khác nhau giữa host không tự động chứng minh không tương thích. Mục tiêu là hiểu process đang chạy trong loại namespace nào và runtime sẽ khôi phục chúng ra sao.

### 15.6. Native library

~~~bash
file /opt/app/lib/libexample.so
ldd /opt/app/lib/libexample.so
readelf -h /opt/app/lib/libexample.so
readelf -d /opt/app/lib/libexample.so
~~~

Đường dẫn là ví dụ. Thay bằng vị trí thư viện thực tế. So sánh dependency và ABI trong cả hai image.

## 16. Lỗi tương thích thường gặp và cách phân tích

| Triệu chứng | Nguyên nhân có thể | Hướng điều tra |
|---|---|---|
| CRIU từ chối dump/restore | Kernel feature hoặc resource không được hỗ trợ | Đọc CRIU log, chạy capability check |
| Operation not permitted | Thiếu capability hoặc bị security policy chặn | Kiểm tra capability, seccomp, AppArmor/SELinux |
| Không tìm thấy file sau restore | Mount hoặc volume khác | So sánh mount namespace và path |
| Native library load thất bại | Thiếu .so hoặc sai dynamic linker | Kiểm tra ELF interpreter, ldd, symbol version |
| Undefined symbol | ABI hoặc thư viện phụ thuộc khác version | Kiểm tra readelf và package version |
| Illegal instruction | CPU thiếu instruction set mà binary/JIT sử dụng | So sánh architecture và CPU flags |
| Không tạo được thread | PID/thread limit hoặc resource limit | Kiểm tra cgroup và ulimit |
| Không bind được port | Listener đã được restore hoặc port đã bị chiếm | Kiểm tra socket, process và port mapping |
| Kết nối timeout | Network namespace, route hoặc peer thay đổi | Resolve DNS, kiểm tra route và reconnect |
| TLS handshake lỗi | OpenSSL, trust store hoặc certificate khác | Kiểm tra TLS config và certificate |
| Permission denied với file | UID/GID mapping hoặc security label | Kiểm tra ownership, mode, SELinux/AppArmor |
| Ứng dụng restore nhưng lỗi native | Native handle hoặc thread nội bộ không được phục hồi | Kiểm tra vendor support và lifecycle callback |

Không nên sửa nhiều thành phần cùng lúc khi điều tra. Hãy xác định lớp lỗi đầu tiên trong log, so sánh môi trường tạo/restore và thay đổi một yếu tố có kiểm soát.

## 17. Nên đóng gói checkpoint theo nhóm nền tảng nào?

Với hệ thống triển khai trên nhiều loại node, có thể tạo checkpoint riêng cho từng nhóm nền tảng đã được kiểm chứng.

Ví dụ:

| Checkpoint profile | Nền tảng mục tiêu | Quy tắc |
|---|---|---|
| linux-x86-baseline | Linux x86-64 với CPU baseline xác định | Chỉ restore vào node pool tương ứng |
| linux-arm64 | Linux AArch64 | Tạo ảnh riêng cho kiến trúc ARM64 |
| linux-x86-native-v2 | x86-64 với native dependency đặc thù | Gắn với image và ABI đã pin |
| linux-kernel-pool-a | Nhóm node có kernel/runtime tương thích đã kiểm thử | Chỉ phân phối trong pool được xác nhận |

Đây là cách đặt tên minh họa. Không nên tạo quá nhiều profile nếu khác biệt không ảnh hưởng đến tương thích. Ngược lại, không nên gộp các host có native ABI hoặc CPU feature không tương thích vào cùng một nhóm chỉ để giảm số artifact.

### 17.1. Node pool tương thích

Trong Kubernetes, có thể dùng node label và scheduling rule để giới hạn checkpoint restore vào nhóm node phù hợp. Cách đặt label cần thể hiện những đặc điểm có ý nghĩa như architecture, CRaC baseline hoặc native runtime profile.

Không nên chỉ dùng label chung như `linux=true`. Linux là quá rộng để mô tả ranh giới tương thích.

### 17.2. Khi nâng cấp kernel hoặc base image

Nâng cấp kernel, CRIU, container runtime, libc, OpenSSL hoặc JDK có thể làm thay đổi điều kiện restore. Trước khi rollout:

1. Tạo checkpoint mới trên nền tảng đã nâng cấp.
2. Restore trên node mục tiêu.
3. Chạy smoke test và kiểm tra native dependency.
4. Đo thời gian restore và readiness.
5. Chỉ phân phối checkpoint mới khi đã đạt điều kiện.
6. Giữ artifact cũ trong thời gian rollback nếu policy cho phép.

Không nên tiếp tục sử dụng checkpoint cũ chỉ vì application JAR không thay đổi.

## 18. Các tài nguyên nên được tái lập qua callback CRaC

Một số resource phụ thuộc mạnh vào môi trường và thường cần đóng trước checkpoint rồi tạo lại sau restore:

| Resource | Trước checkpoint | Sau restore |
|---|---|---|
| JDBC connection/pool | Drain và đóng theo thư viện | Tạo pool/connection mới |
| Redis client | Dừng command, listener và pool | Kết nối lại, refresh topology |
| HTTP client/socket | Drain request và đóng connection khi cần | Tạo client/connection mới |
| File watcher | Dừng watcher | Đăng ký watcher lại |
| Native device handle | Gọi API release nếu được hỗ trợ | Mở lại và xác nhận thiết bị |
| Native library worker | Dừng thread nội bộ theo vendor API | Khởi tạo lại worker |
| DNS/service discovery | Dừng refresh task nếu cần | Resolve endpoint hiện tại |
| Scheduler | Pause và drain task | Tính lại lịch và tạo scheduler |
| Client-side cache listener | Dừng listener | Resubscribe và reconcile cache |

Không phải mọi tài nguyên đều cần đóng. Hãy dùng tài liệu JDK CRaC và thư viện để xác định resource nào được hỗ trợ checkpoint/restore. Đóng trùng một resource do framework đã quản lý có thể gây lỗi vòng đời.

## 19. Chiến lược khi môi trường restore khác môi trường tạo ảnh

Nếu môi trường đích khác, hãy phân loại sai khác.

### 19.1. Sai khác có thể xử lý bằng ứng dụng

Ví dụ:

- Hostname hoặc IP của dịch vụ.
- Credential hoặc secret.
- DNS record.
- Feature flag.
- Endpoint của database.
- Cache entry và token.

Các giá trị này thường có thể được refresh sau restore nếu ứng dụng được thiết kế phù hợp.

### 19.2. Sai khác cần tương thích ở cấp runtime

Ví dụ:

- JDK build và CRaC integration.
- Kernel/CRIU support.
- CPU architecture và feature.
- Native library ABI.
- Dynamic linker và libc.
- Memory mapping và native runtime.

Những khác biệt này không thể được sửa chỉ bằng việc gọi một callback Java. Có thể cần build lại image, native library hoặc checkpoint trên môi trường đích.

### 19.3. Sai khác không nên cố phục hồi tại runtime

Nếu checkpoint yêu cầu CPU architecture hoặc ABI không tương thích, hoặc kernel không hỗ trợ resource cần thiết, hãy từ chối restore và tạo checkpoint mới. Cố chạy tiếp có thể gây crash hoặc lỗi dữ liệu khó chẩn đoán.

## 20. Checklist tương thích trước khi phát hành checkpoint

### Kernel và CRIU

- [ ] Kernel release và build đã được ghi nhận.
- [ ] CRIU version đã được ghi nhận và hỗ trợ môi trường.
- [ ] Capability check đã chạy trên host mục tiêu.
- [ ] Namespace và cgroup mode đã được xác định.
- [ ] Có đủ quyền hệ thống và security policy phù hợp.

### CPU và native ABI

- [ ] CPU architecture của build/restore tương thích.
- [ ] CPU feature baseline đã được xác định.
- [ ] JDK và JVM build đã được pin.
- [ ] libc và dynamic linker đã được kiểm tra.
- [ ] JNI/native library dependency chain đã được kiểm tra.
- [ ] Không có instruction set hoặc symbol dependency thiếu ở môi trường đích.

### Filesystem và network

- [ ] Mount, volume và đường dẫn quan trọng tương thích.
- [ ] File descriptor, lock và memory mapping đã được đánh giá.
- [ ] Network namespace, route và DNS được kiểm tra.
- [ ] Outbound connection có quy trình reconnect.
- [ ] Listening socket được xử lý theo cơ chế restore đã xác nhận.

### Container và security

- [ ] Container runtime và image digest được ghi nhận.
- [ ] UID/GID mapping và capability đã được xác nhận.
- [ ] Seccomp, AppArmor hoặc SELinux policy cho phép thao tác cần thiết.
- [ ] Cgroup memory, CPU và PID limit đủ cho restore.
- [ ] Không cần tắt toàn bộ security policy để checkpoint/restore hoạt động.

### Restore và vận hành

- [ ] Checkpoint manifest đi kèm artifact.
- [ ] Môi trường restore được so sánh với manifest.
- [ ] Đã thử restore trên từng nhóm node mục tiêu.
- [ ] Native library và external dependency được smoke test.
- [ ] Readiness chỉ mở sau khi resource thiết yếu sẵn sàng.
- [ ] Có quy trình tạo checkpoint mới khi nền tảng thay đổi.

## 21. Câu hỏi thường gặp

### Cùng chạy Linux có đủ để restore checkpoint không?

Không. Linux có nhiều kernel version, cấu hình, kiến trúc, namespace, filesystem, security policy và native runtime khác nhau. Cần kiểm tra những feature CRIU/JDK cần và thử restore trong môi trường mục tiêu.

### Hai máy có cùng kernel version có chắc tương thích không?

Không. Chúng vẫn có thể khác kernel configuration, module, capability, cgroup, security policy, mount, CPU feature hoặc native library. Kernel version là một dữ kiện trong ma trận, không phải chứng nhận tương thích.

### Có thể restore checkpoint x86-64 trên ARM64 không?

Không nên giả định có thể. Checkpoint chứa trạng thái CPU và tiến trình native gắn với kiến trúc. Hãy tạo checkpoint riêng cho từng kiến trúc được hỗ trợ và tuân theo tài liệu của JDK/CRIU.

### Có thể đổi glibc hoặc OpenSSL sau khi tạo checkpoint không?

Việc thay native library có thể làm thay đổi ABI, symbol hoặc trạng thái mapping của tiến trình. Không nên thay package trong image rồi tiếp tục dùng checkpoint cũ nếu chưa có xác nhận hỗ trợ. Hãy build và kiểm thử checkpoint mới với dependency mới.

### Container image giống nhau có bảo đảm restore được trên mọi host không?

Không. Container image không đóng gói kernel host. Các host vẫn có thể khác kernel, CPU, CRIU, cgroup, namespace và security policy. Cần kiểm tra cả image lẫn host.

### Vì sao CRIU check thành công nhưng restore vẫn thất bại?

Capability check chỉ xác nhận một số khả năng của môi trường. Workload thực tế có thể dùng resource đặc biệt, native library, socket, mount hoặc namespace mà check chung không bao phủ. Cần đọc log của lần dump/restore và kiểm thử đúng workload.

### Có nên đóng mọi native library trước checkpoint không?

Không. Chỉ đóng resource mà thư viện yêu cầu hoặc không hỗ trợ checkpoint/restore. Một số native library có thể giữ trạng thái an toàn; một số cần shutdown và init lại. Hãy theo tài liệu vendor và kiểm thử thực tế.

### Khi kernel được nâng cấp có phải tạo checkpoint mới không?

Nên kiểm thử lại. Nếu thay đổi ảnh hưởng đến feature kernel, CRIU, container runtime hoặc cách quản lý resource, checkpoint cũ có thể không còn tương thích. Với nền tảng production, tạo checkpoint mới và restore thử trước khi rollout là cách quản lý an toàn.

### Có thể khắc phục mọi sai khác bằng afterRestore() không?

Không. Callback Java phù hợp để refresh cấu hình, tạo lại connection, mở file hoặc khởi động worker. Nó không thể biến mã máy sai kiến trúc thành mã tương thích, bổ sung kernel feature còn thiếu hoặc sửa một ABI native không tương thích.

## Kết luận

Khả năng restore CRaC phụ thuộc vào nhiều lớp native bên dưới ứng dụng Java: kernel, CRIU, namespace, cgroup, CPU architecture, instruction set, dynamic linker, libc, JNI library, filesystem, network stack và security policy. Cùng một JAR hoặc container image chưa đủ để chứng minh checkpoint có thể chạy trên mọi host Linux.

Hãy pin JDK và native dependency, ghi nhận kernel/CRIU/CPU baseline, đóng hoặc tái lập các resource phụ thuộc môi trường qua CRaC callback, tạo manifest cho mỗi checkpoint và giới hạn restore vào nhóm nền tảng đã kiểm thử. Khi kernel, CPU, ABI hoặc native runtime thay đổi, hãy xác minh tương thích và tạo checkpoint mới nếu cần.
