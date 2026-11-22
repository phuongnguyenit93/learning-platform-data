# PID namespace và xung đột định danh khi dùng cơ chế CRIU

CRaC giúp khôi phục trạng thái của tiến trình Java, còn CRIU (Checkpoint/Restore In Userspace) cung cấp cơ chế checkpoint và restore tiến trình trên Linux. Khi ứng dụng chạy trong container, một chi tiết quyết định khả năng restore là **PID namespace**: cùng một tiến trình có thể mang nhiều PID khác nhau tùy namespace đang quan sát nó. Vì vậy, PID ghi trong checkpoint không thể được hiểu đơn giản là PID trên host, và hai tiến trình có cùng số PID chưa chắc đã xung đột.

Xung đột xảy ra khi runtime cố khôi phục một tiến trình vào PID namespace mà số PID cần cấp đã được một tiến trình khác sử dụng, hoặc khi tiến trình được khôi phục vào sai namespace so với cấu trúc process tree và môi trường container. Các vấn đề liên quan còn bao gồm PID 1, tiến trình init của namespace, PID file cũ, PID reuse, `/proc` được mount từ namespace nào và những thành phần bên ngoài đang giữ tham chiếu tới process cũ.

Để checkpoint/restore container ổn định, cần hiểu ranh giới PID namespace, tạo đúng namespace đích trước khi restore, phối hợp với container runtime, và không dùng PID số học như một định danh bền vững xuyên qua vòng đời process.

## 1. PID namespace là gì?

PID namespace là một Linux namespace cô lập không gian định danh process. Một process trong PID namespace có thể nhìn thấy các process thuộc namespace đó và các namespace con theo quy tắc của kernel, nhưng không nhìn thấy đầy đủ process ở các namespace ngang hàng hoặc namespace bên ngoài.

Một process có thể có nhiều PID cùng lúc: một PID trong namespace của chính nó và một PID khác trong từng namespace cha. Khi gọi `getpid()`, process nhận PID theo namespace mà nó đang chạy. Process ở host có thể quan sát một PID khác cho cùng tiến trình.

Ví dụ minh họa:

```text
Host PID namespace
  PID 1     systemd
  PID 4200  container init
      |
      +-- Container PID namespace A
            PID 1   init/pause process
            PID 7   java application
            PID 9   helper process

  PID 5100  process khác trên host
      |
      +-- Container PID namespace B
            PID 1   init process
            PID 7   worker process
```

Trong ví dụ, PID `7` xuất hiện ở cả namespace A và B nhưng không xung đột vì chúng thuộc hai không gian PID độc lập. Host nhìn thấy hai process bằng PID `4200` và `5100` (cùng các PID host khác của process con nếu cần), trong khi bên trong mỗi container process có thể thấy PID `7`.

Điều này dẫn tới nguyên tắc quan trọng: **PID chỉ có ý nghĩa khi đi kèm PID namespace**. Một PID đơn lẻ không đủ để xác định duy nhất một process trong toàn hệ thống.

## 2. Namespace lồng nhau và ánh xạ PID

PID namespace có tính phân cấp. Khi một namespace được tạo bên trong namespace khác, process trong namespace con vẫn có PID được cấp trong các namespace cha. Process trong namespace cha có thể quan sát process con bằng PID ở namespace cha; process con không thể nhìn thấy process ở namespace cha chỉ bằng cách dùng PID nội bộ của nó.

Ví dụ một tiến trình có thể được nhìn thấy như sau:

| Góc nhìn | PID của cùng tiến trình |
| --- | ---: |
| PID namespace của container | 7 |
| PID namespace cha | 4207 |
| Host PID namespace | 4207 |

Số liệu trên chỉ minh họa. PID thực tế được kernel cấp và có thể khác trên mỗi lần khởi chạy/restore.

Trên Linux, `/proc/<pid>/status` có thể hiển thị trường `NSpid`, cho biết các PID của tiến trình theo các tầng PID namespace nhìn thấy từ procfs mount đó. Ví dụ:

```text
Name:   java
Pid:    4207
PPid:   4199
NSpid:  4207 7
```

Nếu procfs được mount từ host namespace, `NSpid` có thể hiển thị PID ở các namespace cha và namespace con. Kết quả cụ thể phụ thuộc vị trí procfs được mount và cấu trúc namespace. Không nên giả định mọi container đều hiển thị cùng một số cột hoặc cùng góc nhìn.

Các trường `Pid`, `PPid`, `NSpid` và namespace inode giúp xác định process đang được nhìn từ đâu. Chúng hữu ích hơn việc chỉ so sánh con số PID giữa output của `ps` trên host và trong container.

## 3. PID namespace và process identity khác nhau

Process identity không chỉ gồm PID. Đối với container và CRIU, cần quan tâm ít nhất:

- PID trong từng PID namespace.
- PID namespace mà process thuộc về.
- Parent/child relationship và process tree.
- User, mount, network, IPC, UTS và cgroup namespace liên quan.
- Cgroup membership, capabilities và security profile.
- File descriptor, socket, mount và tài nguyên kernel khác.

Hai process có thể có cùng PID nhưng thuộc namespace khác nhau. Ngược lại, hai process trong cùng PID namespace không thể đồng thời chiếm cùng một PID. Nếu CRIU cần khôi phục một process tree với PID cụ thể vào namespace đã có process sử dụng số đó, kernel không thể cấp lại định danh đang bận và restore có thể thất bại.

PID namespace cũng là một đối tượng kernel, không phải một chuỗi tên hoặc số PID. Có thể quan sát namespace handle qua `/proc/<pid>/ns/pid`; giá trị symlink thường chứa inode identifier, ví dụ `pid:[4026533001]`. Inode này giúp so sánh hai process hiện tại có cùng namespace hay không. Nó không phải định danh ổn định để lưu rồi kỳ vọng namespace sau restore có cùng inode.

## 4. Vì sao CRIU cần khôi phục đúng PID namespace?

CRIU lưu thông tin cần thiết để tái tạo process tree và các namespace liên quan. Khi restore, runtime phải thiết lập môi trường namespace phù hợp rồi khôi phục process theo cấu trúc và PID cần thiết trong namespace đích.

Nếu namespace đích không đúng, có thể gặp các tình huống:

1. Process được khôi phục vào host PID namespace thay vì PID namespace riêng của container.
2. Process tree được restore vào một namespace đã có tiến trình khác chiếm PID mà ảnh checkpoint cần.
3. PID namespace đích đã tồn tại nhưng init process hoặc các process nền không còn đúng trạng thái.
4. Process được restore trong namespace mới nhưng `/proc` vẫn được mount theo namespace khác, khiến ứng dụng hoặc công cụ giám sát nhìn thấy PID không như mong đợi.
5. Container runtime tạo namespace hoặc cgroup không khớp với metadata mà CRIU cần để dựng process tree.

CRIU có thể cần tạo PID namespace mới cho process tree được restore. Tùy phiên bản và cách tích hợp, CRIU có tùy chọn `--pidns` để yêu cầu restore trong PID namespace mới; container runtime thường điều phối các tùy chọn và namespace thay cho người vận hành. Không nên tự thêm cờ CRIU vào một lệnh runtime nếu runtime không hỗ trợ hoặc đã tự quản lý namespace. Hãy kiểm tra `criu restore --help`, tài liệu CRIU và tài liệu của runtime đang dùng.

Một điểm đặc biệt của Linux: `setns()` vào PID namespace chỉ ảnh hưởng các process con được tạo sau đó; nó không di chuyển process gọi `setns()` sang namespace mới. Vì thế runtime phải tạo/nhập namespace đúng thời điểm trước khi khởi chạy process tree cần restore.

## 5. Xung đột PID khi restore vào namespace đã có process

Giả sử checkpoint lưu process tree có PID nội bộ `1`, `7` và `9` trong một PID namespace. Nếu restore vào namespace đã có process PID `7`, kernel không thể tạo process mới với PID đó trong cùng namespace. CRIU có thể báo lỗi khi thiết lập PID hoặc dựng process tree.

```text
Checkpoint image yêu cầu:        PID namespace đích hiện tại:

PID 1  init                       PID 1  existing init
PID 7  java                       PID 7  unrelated process
PID 9  helper                     PID 12 another process
          |                                  |
          +---------------+------------------+
                          |
                          v
             Không thể cấp PID 7 lần nữa
```

Đây là xung đột thật vì cả hai process cùng thuộc một namespace. Nó khác với trường hợp một process trong namespace A và một process trong namespace B cùng có PID `7`, vốn hợp lệ.

Các cách giảm rủi ro:

- Tạo PID namespace mới, riêng biệt cho process tree cần restore khi kiến trúc/runtime hỗ trợ.
- Đảm bảo namespace đích không có process không thuộc ảnh checkpoint chiếm PID cần thiết.
- Không restore đồng thời nhiều bản của cùng checkpoint vào một namespace dùng chung.
- Để container runtime sở hữu việc tạo sandbox, namespace và process tree thay vì tự dựng một phần namespace bên ngoài runtime.
- Nếu dùng PID namespace chia sẻ giữa nhiều container/process, xác định rõ toàn bộ process tree và thứ tự restore.

Không cố giải quyết collision bằng cách đổi thủ công PID trong file checkpoint. PID là một phần của cấu trúc process tree và các tham chiếu kernel; sửa một vài con số có thể làm hỏng quan hệ parent/child, process group, session hoặc tài nguyên liên quan.

## 6. Vai trò đặc biệt của PID 1

Process đầu tiên trong một PID namespace nhận PID `1` trong namespace đó. Process này đóng vai trò init của namespace và có trách nhiệm quan trọng trong việc nhận tín hiệu, xử lý orphan process và thu gom zombie.

PID 1 có một số semantics đặc biệt:

- Khi process con mồ côi được chuyển cho init, init phải thu gom trạng thái kết thúc của chúng bằng `wait()`/`waitpid()` để tránh zombie tích tụ.
- Cách kernel xử lý signal mặc định đối với namespace init có khác biệt; chương trình init cần cài signal handler phù hợp.
- Khi init của một PID namespace kết thúc, kernel gửi `SIGKILL` tới các process còn lại trong namespace và namespace không thể tiếp tục hoạt động như trước.
- Process mới trong namespace đó không thể được tạo bình thường sau khi init đã chết.

Trong container, PID 1 có thể là ứng dụng Java hoặc một init/supervisor như `tini`/pause process tùy cấu hình. Nếu init là process riêng, Java có PID khác. Khi checkpoint/restore, cần xác định process nào là namespace init và process tree nào được CRIU quản lý.

Không nên giả định Java luôn là PID 1. Trong Kubernetes với `shareProcessNamespace: true`, các container trong Pod chia sẻ PID namespace; process sandbox/pause có thể giữ PID 1, còn Java trong container ứng dụng có PID khác. Khi đó restore một container riêng lẻ cần phối hợp với sandbox và các container cùng namespace.

## 7. PID namespace tồn tại theo vòng đời của namespace init

PID namespace là kernel object. Nó được giữ sống khi còn process thuộc namespace hoặc còn tham chiếu namespace phù hợp. Tuy nhiên, việc process init PID 1 kết thúc có tác động mạnh: các process khác trong namespace bị kết thúc và namespace không còn là môi trường hoạt động bình thường cho process mới.

Điều này quan trọng khi tổ chức restore:

- Không để supervisor/container runtime vô tình kill namespace init trước khi CRIU hoàn tất.
- Không dùng một namespace đã bị init cũ kết thúc như namespace đích còn hợp lệ.
- Tạo namespace mới đúng cách khi cần khôi phục toàn bộ process tree.
- Bảo đảm init process được restore hoặc tạo theo mô hình mà runtime yêu cầu.
- Kiểm tra các process phụ trợ có đang chia sẻ PID namespace với ứng dụng hay không.

Một namespace inode còn xuất hiện trong `/proc` không chứng minh process tree bên trong vẫn ở trạng thái có thể restore. Cần kiểm tra cả init, process membership và trạng thái runtime.

## 8. PID reuse và PID file cũ

Kernel có thể tái sử dụng một số PID sau khi process cũ kết thúc. Ví dụ process Java cũ có PID `4207`; sau khi nó kết thúc, một process khác có thể được cấp PID `4207`. Nếu một script hoặc ứng dụng chỉ đọc file `/run/myapp.pid` rồi gửi signal tới PID đó, nó có thể tác động nhầm process mới.

Checkpoint/restore làm vấn đề phức tạp hơn:

- PID trong container có thể giống PID trước checkpoint nhưng host PID sau restore có thể khác.
- PID file được lưu trong heap hoặc filesystem có thể còn chứa PID host cũ.
- Một supervisor bên ngoài có thể giữ PID cũ và cho rằng process đã chết.
- PID cũ có thể đã được tái sử dụng cho process không liên quan.
- PID trong một namespace có thể trùng số với PID của process khác ở namespace khác.

Không coi PID file là nguồn sự thật sau restore nếu file chứa PID được tạo trước checkpoint. Cần cập nhật PID file theo PID hiện tại trong namespace phù hợp, hoặc để container runtime/supervisor quản lý process identity.

Đối với ứng dụng Java, `ProcessHandle.current().pid()` trả PID mà process nhìn thấy trong PID namespace hiện tại. Giá trị này có thể khác host PID. Không ghi giá trị đó vào hệ thống điều khiển host rồi giả định host có thể dùng trực tiếp để gửi signal.

Khi cần kiểm tra một PID có còn trỏ tới đúng process, ngoài PID hãy xác minh start time, executable, command line và PID namespace. Trên Linux, có thể dùng `pidfd` trong chương trình native để giữ tham chiếu tới process identity mà không bị nhầm với PID được tái sử dụng; pidfd là kernel handle, không phải số PID có thể lưu bền vững qua checkpoint và dùng lại tùy ý sau restore.

## 9. PID file, lock file và Unix domain socket

Một số server ghi PID vào file để ngăn chạy nhiều instance hoặc để script stop service. File này có thể tồn tại trong filesystem container sau khi process cũ kết thúc hoặc sau khi checkpoint được khôi phục.

Các vấn đề thường gặp:

- PID file cũ trỏ tới host PID không còn thuộc process Java.
- PID file chứa PID container nhưng script chạy ở host.
- Lock file còn tồn tại dù process sở hữu lock đã chết; hoặc process mới thấy file nhưng không xác minh được owner.
- Unix domain socket path còn file socket cũ nhưng listener đã biến mất.
- Supervisor kiểm tra PID ở namespace khác và kết luận nhầm process không tồn tại.

Nên quản lý các file này như tài nguyên cần reconcile:

1. Trước checkpoint, dừng listener và giải phóng lock/socket theo API ứng dụng.
2. Không dùng file PID làm cơ chế khóa duy nhất; dùng file lock/kernel lock hoặc registry có kiểm tra owner phù hợp.
3. Sau restore, xác định PID hiện tại từ process và namespace mới.
4. Xóa/recreate PID file hoặc socket path cũ chỉ sau khi xác minh không có process đang sử dụng.
5. Cập nhật supervisor/health registration theo identity mới.

Không xóa lock file chỉ dựa vào tuổi file. Một file có thể còn được process đang hoạt động sử dụng; ngược lại, file cũ không bảo đảm lock kernel còn được giữ.

## 10. `/proc` phải phản ánh PID namespace đúng

`/proc` là procfs và cách mount của nó quyết định góc nhìn về process. Nếu procfs được mount trong PID namespace khác với namespace của process đang quan sát, lệnh `ps`, `top` hoặc code đọc `/proc` có thể hiển thị process list không như ứng dụng mong đợi.

Trong container, runtime thường mount procfs phù hợp với PID namespace của container. Khi restore, cần giữ hoặc tạo lại mount namespace và procfs theo yêu cầu runtime. Không nên mount một procfs host vào container rồi giả định PID nội bộ vẫn nhất quán.

Các dấu hiệu có thể quan sát:

- `getpid()` trả PID trong namespace hiện tại.
- `/proc/self/status` cung cấp `Pid`, `PPid` và có thể có `NSpid`.
- `/proc/<pid>/ns/pid` cho biết namespace handle của process được quan sát.
- `/proc` được mount ở namespace nào có thể làm thay đổi danh sách PID nhìn thấy.

Sau restore, kiểm tra từ cả host và bên trong container. So sánh PID namespace inode, `NSpid`, parent PID và process list để xác định mapping.

## 11. PID namespace trong container runtime

Container runtime thường tạo namespace và cgroup trước khi khởi chạy container. Khi checkpoint, runtime cần phối hợp CRIU với cấu hình container ban đầu. Khi restore, runtime phải dựng lại môi trường tương thích, bao gồm PID namespace, mount namespace, cgroup và các resource cần thiết.

Không nên chạy CRIU trực tiếp trên một PID host mà không biết process thuộc namespace nào. Nếu dump process container từ host, cần xác định đúng host PID của container init hoặc target process theo yêu cầu CRIU/runtime, không lấy PID nội bộ từ `ps` trong container rồi truyền thẳng cho lệnh host.

Các thông tin cần giữ trong deployment metadata:

- Container ID và sandbox/pod identity.
- Host PID của container init tại thời điểm thao tác, chỉ để truy vết attempt đó.
- PID namespace inode và namespace topology tại thời điểm dump, chỉ để chẩn đoán.
- Cấu hình `--pid`/PID namespace mode của runtime.
- Process tree và init process trong container.
- Cgroup path, mount namespace, network namespace và runtime version.
- Phiên bản kernel, CRIU và container runtime.

Host PID và namespace inode là thông tin tạm thời, không phải identity bền vững để dùng cho lần restore sau. Khi restore, runtime có thể cấp host PID mới và tạo namespace mới; điều quan trọng là cấu trúc trong namespace đích phù hợp với ảnh.

## 12. Kubernetes và PID namespace của Pod

Trong Kubernetes, các container trong một Pod thường có network namespace chung, nhưng PID namespace không mặc định luôn được chia sẻ. Với cấu hình `shareProcessNamespace: true`, các container trong Pod có thể nhìn thấy process của nhau trong một PID namespace chung.

Ví dụ cấu hình:

```yaml
apiVersion: v1
kind: Pod
metadata:
  name: java-worker
spec:
  shareProcessNamespace: true
  containers:
    - name: app
      image: example/java-worker:1.0
    - name: sidecar
      image: example/diagnostics:1.0
```

Khi chia sẻ PID namespace:

- Process trong container app và sidecar nằm trong cùng không gian PID.
- Hai container có thể quan sát và gửi signal tới process của nhau tùy quyền.
- PID 1 có thể là process sandbox/pause của Pod, không nhất thiết là Java.
- Restore một container trong khi các process khác của Pod vẫn sống có thể gây xung đột nếu process tree cần PID đã bị chiếm.
- Việc checkpoint/restore cần được điều phối ở cấp runtime/Pod theo khả năng hỗ trợ; không thể coi mỗi container là một PID namespace độc lập.

Nếu không bật chia sẻ PID namespace, mỗi container có PID namespace riêng theo cấu hình runtime. Khi đó hai container có thể cùng có PID `1` hoặc `7` mà không xung đột.

Kubernetes checkpoint API, nếu có trong phiên bản/feature set đang dùng, vẫn phụ thuộc container runtime và CRIU; không đồng nghĩa Kubernetes có thể restore tùy ý một process tree vào bất kỳ Pod nào. Kiểm tra tài liệu đúng phiên bản Kubernetes, kubelet, container runtime và CRIU. Đừng giả định một API checkpoint container tự động xử lý mọi sidecar hoặc process trong PID namespace dùng chung.

## 13. PID namespace dùng chung và sidecar

Khi Pod chia sẻ PID namespace, sidecar có thể giám sát hoặc gửi signal tới ứng dụng. Điều này hữu ích cho debugging nhưng làm checkpoint/restore phức tạp hơn:

- Ảnh checkpoint một container có thể chỉ chứa một phần process tree trong namespace chung.
- Các process khác vẫn chiếm PID trong namespace đích.
- PID 1 của namespace có thể thuộc sandbox hoặc process khác không nằm trong ảnh.
- Quan hệ parent/child có thể đi qua ranh giới container.
- Một sidecar có thể giữ PID file, process handle hoặc socket liên quan tới ứng dụng.

Trước khi chọn chiến lược checkpoint, xác định phạm vi process tree nào được dump. Nếu runtime chỉ checkpoint một container nhưng PID namespace được chia sẻ, cần xác nhận rõ cách CRIU/runtime xử lý process bên ngoài container đó. Nếu không có hỗ trợ được tài liệu xác nhận, không nên tự giả định restore an toàn.

Một lựa chọn kiến trúc là không chia sẻ PID namespace nếu ứng dụng không cần quan sát process của sidecar. Namespace riêng giảm khả năng collision giữa các container và làm ranh giới process tree rõ hơn.

## 14. PID namespace, cgroup và các namespace khác

PID namespace chỉ cô lập định danh process. Nó không tự cô lập tài nguyên CPU/memory, filesystem, network hoặc quyền. Container runtime thường kết hợp nhiều namespace và cgroup:

| Thành phần | Phạm vi quản lý | Vì sao ảnh hưởng restore |
| --- | --- | --- |
| PID namespace | Process ID và process visibility | Cần cấp PID đúng và dựng đúng process tree. |
| Mount namespace | Mount table và filesystem view | Đường dẫn, procfs và file descriptor cần trỏ đúng mount. |
| User namespace | UID/GID mapping và quyền | Owner/capability khi restore có thể khác nếu mapping sai. |
| Network namespace | Interface, route, socket và network stack | Socket/endpoint có thể không hợp lệ hoặc cần reconnect. |
| IPC namespace | SysV IPC và POSIX message queue namespace | IPC identifier/resource cần được phục hồi đúng phạm vi. |
| UTS namespace | Hostname và domain name | Hostname có thể khác môi trường restore. |
| Cgroup | Resource accounting/limits và membership | Process cần nằm đúng cgroup và tuân thủ quota/limit. |

Không sửa PID namespace riêng lẻ mà bỏ qua các namespace/cgroup liên quan. Một process có PID đúng nhưng mount, user mapping hoặc cgroup sai vẫn có thể không hoạt động hoặc restore thất bại.

## 15. Quy trình chuẩn bị PID namespace trước restore

Một quy trình restore container có kiểm soát thường gồm:

1. Chọn checkpoint artifact và xác nhận tính tương thích của kernel, CRIU, runtime, CPU và filesystem.
2. Xác định PID namespace topology của container tại thời điểm checkpoint.
3. Dừng hoặc cô lập instance đích để tránh process không liên quan chiếm PID trong namespace sẽ dùng.
4. Để container runtime tạo sandbox và namespace theo đúng cấu hình; nếu CRIU yêu cầu namespace mới, để runtime/CRIU thực hiện theo chế độ được hỗ trợ.
5. Kiểm tra init process và procfs mount trong namespace đích.
6. Restore process tree qua container runtime/CRIU integration.
7. Kiểm tra PID mapping từ host và trong container, parent/child relationship và process count.
8. Xác minh cgroup, mount, user và network namespace.
9. Cập nhật PID file, supervisor registration và health monitoring nếu chúng lưu PID cũ.
10. Chỉ mở traffic sau khi callback CRaC hoàn tất và readiness đạt.

Không khởi chạy một ứng dụng mới trong cùng PID namespace trước khi restore ảnh nếu ứng dụng mới có thể chiếm PID mà ảnh cần. Không chạy hai restore attempt đồng thời vào cùng namespace đích.

## 16. Chẩn đoán PID namespace và mapping

Các lệnh sau giúp kiểm tra process từ host Linux. Cần thay `<host-pid>` bằng PID nhìn thấy trên host:

```bash
# Xem namespace inode của process
readlink /proc/<host-pid>/ns/pid

# Xem PID, parent PID và mapping theo namespace
grep -E '^(Name|Pid|PPid|NSpid):' /proc/<host-pid>/status

# Liệt kê PID namespaces đang tồn tại
lsns -t pid

# Xem process từ host
ps -o pid,ppid,ns,pidns,comm -p <host-pid>
```

Các cột `ns` hoặc `pidns` của `ps` có thể không có trong mọi bản procps; nếu lệnh không hỗ trợ, dùng `readlink` và `lsns`.

Để quan sát từ PID namespace của container, có thể dùng `nsenter` với process đại diện:

```bash
nsenter -t <host-pid> -p -- ps -ef
```

Lệnh này chạy process con trong PID namespace đích; góc nhìn `/proc` vẫn phụ thuộc procfs mount trong mount namespace hiện tại. Trong container, cách đơn giản và đáng tin cậy thường là chạy `ps` và đọc `/proc/self/status` trực tiếp bên trong container.

Ví dụ kiểm tra PID hiện tại từ Java:

```java
public class PidInfo {
    public static void main(String[] args) {
        System.out.println("PID visible to this process: "
                + ProcessHandle.current().pid());
    }
}
```

Giá trị này là PID theo namespace mà JVM đang chạy, không nhất thiết là host PID. Đối chiếu với `NSpid` từ host để xác định mapping.

## 17. Đọc lỗi CRIU liên quan tới PID

Khi restore thất bại, hãy đọc log CRIU và log container runtime để phân biệt:

- **PID đã tồn tại:** namespace đích có process chiếm PID cần khôi phục.
- **Không tạo được PID namespace:** kernel capability, user namespace, runtime hoặc quyền không đáp ứng.
- **Không tìm thấy namespace/init:** namespace handle hoặc process init đã kết thúc/không còn đúng.
- **Process tree không đầy đủ:** checkpoint không chứa process cần thiết hoặc phạm vi dump không khớp.
- **Procfs/mount không khớp:** process được khôi phục nhưng công cụ trong container quan sát sai process list.
- **Cgroup/namespace restore lỗi:** PID setup có thể đúng nhưng môi trường container chưa đầy đủ.

Không kết luận mọi lỗi `EEXIST` đều là PID collision; cần xác định syscall và resource cụ thể trong log. Tương tự, lỗi `EPERM` có thể liên quan capability, namespace hoặc security policy chứ không phải số PID đã bị chiếm.

Quy trình điều tra:

1. Ghi lại PID host, PID trong container, PID namespace inode và container ID.
2. Xác định runtime đang restore vào namespace mới hay namespace hiện có.
3. Liệt kê process hiện tại trong namespace đích trước restore.
4. Đối chiếu PID trong checkpoint/process tree với các PID đang sử dụng.
5. Kiểm tra process PID 1, parent/child relationship và shared PID namespace.
6. Đọc log CRIU, runtime, kubelet và kernel quanh thời điểm lỗi.
7. Sau khi sửa cấu hình, tạo namespace đích sạch theo runtime và thử restore lại từ artifact còn nguyên vẹn.

## 18. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể gặp | Hướng xử lý |
| --- | --- | --- |
| CRIU không tạo được process với PID đã lưu | PID đó đang bị process khác chiếm trong cùng namespace | Dùng namespace đích sạch hoặc chế độ namespace mới được runtime hỗ trợ. |
| Cùng PID số nhưng process không phải cùng instance | PID reuse sau khi process cũ kết thúc | Kiểm tra namespace, start time và process identity; không tin PID file đơn lẻ. |
| PID trong container khác PID trên host | Hai góc nhìn namespace khác nhau | Dùng `NSpid`, `/proc/<pid>/ns/pid` và kiểm tra từ đúng namespace. |
| Process Java không phải PID 1 | Có init/pause/supervisor đứng đầu namespace | Xác định đúng namespace init và process tree trước khi dump/restore. |
| Namespace không còn hoạt động sau khi init thoát | PID 1 của namespace đã kết thúc | Tạo namespace mới và restore theo runtime; không tái sử dụng namespace đã chết. |
| `ps` trong container hiển thị process lạ/thiếu | Procfs mount thuộc namespace khác hoặc PID namespace chia sẻ | Kiểm tra mount namespace và procfs; xác nhận `shareProcessNamespace`. |
| PID file trỏ tới process không liên quan | PID cũ đã được tái sử dụng hoặc PID file dùng sai namespace | Reconcile PID file sau restore và xác minh process identity trước khi signal. |
| Restore một container làm ảnh hưởng sidecar | Pod chia sẻ PID namespace hoặc process tree chung | Xác định phạm vi checkpoint; điều phối ở cấp Pod/runtime hoặc tách PID namespace. |
| Restore chạy được nhưng supervisor không quản lý được process | Host PID mới khác PID cũ | Đăng ký lại process với supervisor bằng container/runtime identity và PID mới. |
| Lỗi quyền khi tạo namespace | Thiếu capability, user mapping hoặc security policy | Kiểm tra runtime, user namespace, capabilities và policy kernel. |

## 19. Các nguyên tắc thiết kế để tránh xung đột

- Coi PID là định danh tạm thời, có phạm vi namespace và có thể được tái sử dụng.
- Lưu container ID, workload identity và checkpoint artifact id làm định danh quản lý; chỉ dùng PID để chẩn đoán tại một thời điểm.
- Ưu tiên PID namespace riêng cho process tree cần checkpoint/restore nếu kiến trúc cho phép.
- Để container runtime quản lý việc tạo namespace, cgroup và process init.
- Không restore vào namespace đang có process không thuộc ảnh nếu chúng có thể chiếm PID cần thiết.
- Không restore đồng thời hai bản vào cùng PID namespace.
- Hiểu rõ process nào là PID 1 và ai chịu trách nhiệm reap zombie.
- Không dùng PID file cũ hoặc host PID đã lưu trước checkpoint như tham chiếu hợp lệ sau restore.
- Rebuild process registration, monitoring, lock và socket theo namespace/host mới.
- Nếu dùng Kubernetes `shareProcessNamespace`, đánh giá toàn bộ Pod process tree và sidecar trước khi chọn phạm vi checkpoint.
- Kiểm tra procfs mount đúng namespace.
- Kiểm tra PID, mount, user, network, IPC namespace và cgroup như một tập hợp.
- Xác minh bằng restore test trên đúng container runtime và kernel đích.

## 20. Kiểm thử PID namespace qua checkpoint–restore

Một bộ kiểm thử tích hợp nên bao gồm các trường hợp:

1. **Hai namespace có cùng PID số:** chạy process PID `7` trong hai namespace riêng và xác nhận không có collision.
2. **Cùng namespace có PID bị chiếm:** tạo process giữ PID cần thiết rồi thử restore; xác nhận runtime báo lỗi rõ ràng và không làm hỏng process hiện tại.
3. **Restore vào namespace mới:** xác nhận process tree được khôi phục với PID nội bộ mong đợi và host PID có thể khác.
4. **PID 1:** xác nhận namespace init tồn tại, xử lý signal và reap orphan/zombie theo yêu cầu.
5. **PID reuse:** dừng process, tạo process khác và xác nhận công cụ quản lý không nhầm process chỉ vì PID giống nhau.
6. **PID file cũ:** restore và xác nhận PID file được cập nhật/reconcile trước khi supervisor gửi signal.
7. **Procfs mount:** xác nhận `ps`, `/proc/self/status` và `NSpid` phản ánh đúng namespace.
8. **Shared PID namespace trong Pod:** thử với `shareProcessNamespace` bật và tắt; xác nhận phạm vi process tree và sidecar.
9. **Namespace init kết thúc:** xác nhận runtime tạo namespace mới thay vì dùng namespace không còn khả năng hoạt động.
10. **Restore lặp lại:** xác nhận mỗi attempt dùng namespace/process context riêng và không chồng lấn PID.

Kiểm thử cần quan sát cả host và bên trong container. Chỉ kiểm tra `ProcessHandle.current().pid()` không đủ để xác định PID mapping hoặc namespace identity.

## 21. Checklist vận hành

- [ ] Biết process đang chạy trong PID namespace nào.
- [ ] Phân biệt PID host, PID container và PID ở namespace cha/con.
- [ ] Ghi nhận PID namespace topology và process tree tại thời điểm checkpoint.
- [ ] Xác định process giữ PID 1 và trách nhiệm init/reaping.
- [ ] Đảm bảo namespace đích sạch hoặc được runtime chuẩn bị đúng trước restore.
- [ ] Không restore hai process tree vào cùng namespace nếu có thể xung đột PID.
- [ ] Không sửa PID trực tiếp trong checkpoint image.
- [ ] Kiểm tra `/proc/<pid>/ns/pid`, `NSpid` và procfs mount.
- [ ] Reconcile PID file, lock file, socket và supervisor registration sau restore.
- [ ] Không dùng host PID cũ như định danh bền vững.
- [ ] Nếu Kubernetes chia sẻ PID namespace, xác định phạm vi Pod và sidecar.
- [ ] Kiểm tra cgroup, mount, user và network namespace cùng PID namespace.
- [ ] Dùng đúng container runtime/CRIU integration được hỗ trợ.
- [ ] Lưu log CRIU/runtime và metadata compatibility để điều tra.
- [ ] Đã thử restore trên kernel/runtime/container configuration đích.

## 22. Kết luận

PID namespace tạo không gian định danh process riêng và có tính phân cấp. Một process có thể có PID khác nhau trong container và trên host; hai process cùng số PID ở hai namespace khác nhau không xung đột. Xung đột thực sự xảy ra khi CRIU phải khôi phục một PID đã được sử dụng trong cùng namespace, hoặc khi namespace/init/process tree đích không phù hợp với ảnh checkpoint.

Hãy xác định đúng namespace và PID 1, tạo namespace đích theo container runtime, tránh restore vào namespace đang có process chiếm PID, và coi PID file/host PID là dữ liệu tạm thời cần reconcile sau restore. Với Kubernetes, đặc biệt chú ý `shareProcessNamespace` và các process sidecar. Kết hợp kiểm tra `NSpid`, namespace inode, procfs, cgroup và log CRIU sẽ giúp phân biệt PID collision với lỗi namespace hoặc quyền, từ đó khôi phục container Java an toàn hơn.
