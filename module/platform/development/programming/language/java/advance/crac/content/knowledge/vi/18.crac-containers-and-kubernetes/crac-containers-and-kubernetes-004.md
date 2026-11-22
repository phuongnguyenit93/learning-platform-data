# Capabilities, seccomp và security context theo checkpoint engine

Checkpoint/restore trong container không chỉ là thao tác của JVM. Engine tạo ảnh phải đọc trạng thái tiến trình, dừng thread, truy cập thông tin trong /proc, làm việc với namespace, file descriptor, cgroup và đôi khi khôi phục trạng thái mạng. Linux bảo vệ những thao tác này bằng capabilities, seccomp, user namespace, AppArmor, SELinux và các chính sách của container runtime.

Vì vậy, không có một bộ quyền duy nhất áp dụng cho mọi ứng dụng CRaC. Quyền cần thiết phụ thuộc vào engine đang tạo checkpoint, vị trí chạy engine, kernel, runtime container và loại tài nguyên mà tiến trình sử dụng. Một ứng dụng Java dùng engine Warp có yêu cầu khác với ứng dụng dùng CRIU; checkpoint một container qua kubelet lại có ranh giới quyền khác với việc chạy CRIU ngay bên trong container ứng dụng.

Điểm đầu tiên cần xác định là **ai thực sự thực hiện checkpoint**:

- JVM CRaC engine như CRIU engine hoặc Warp.
- Container runtime và low-level runtime như containerd/CRI-O, runc/crun, gọi CRIU ở phía node.
- Một tiến trình CRIU do người vận hành hoặc một checkpoint service chạy trực tiếp.

Sau khi xác định engine và ranh giới thực thi, mới chọn capabilities, seccomp profile và security context phù hợp. Không nên bật privileged hoặc tắt toàn bộ seccomp chỉ vì một lần checkpoint gặp lỗi Operation not permitted.

## 1. Phân biệt các lớp checkpoint engine

CRaC API được thiết kế độc lập với cơ chế tạo ảnh. API thông báo cho ứng dụng rằng checkpoint hoặc restore đang diễn ra; engine cụ thể mới quyết định cách lưu và dựng lại trạng thái tiến trình. Cùng một ứng dụng có thể chạy với engine khác nhau tùy bản phân phối JDK.

### 1.1. Các engine thường gặp

| Engine | Cơ chế | Quyền Linux | Phạm vi sử dụng |
|---|---|---|---|
| OpenJDK CRaC criuengine | Gọi CRIU để dump/restore tiến trình | Cần quyền nâng cao; trong container thường cần CAP_CHECKPOINT_RESTORE và CAP_SYS_PTRACE; một số tính năng cần thêm quyền | Tạo ảnh tiến trình thật trên Linux |
| OpenJDK CRaC simengine | Gọi callback trước checkpoint rồi callback sau restore ngay trong cùng tiến trình | Không cần quyền CRIU để tạo ảnh hệ điều hành | Phát triển và kiểm thử logic Resource; không tạo ảnh có thể triển khai |
| Azul Zulu warp | Engine riêng của Azul, không dùng CRIU | Không cần thêm Linux capability cho checkpoint/restore theo tài liệu Azul | Checkpoint/restore thật trên các bản build và nền tảng được Azul hỗ trợ |
| Container checkpoint qua Docker/containerd/CRI-O | Container runtime gọi low-level runtime, thường là runc và CRIU | Quyền chủ yếu thuộc runtime/helper phía node; không mặc định cấp cho ứng dụng | Lưu trạng thái toàn container và phục hồi container |

OpenJDK CRaC hiện cung cấp criuengine và simengine. criuengine là engine mặc định trên Linux trong upstream OpenJDK CRaC và cần quyền cao hơn; simengine chỉ mô phỏng chu trình callback, không ghi ảnh tiến trình. Một số bản phân phối của nhà cung cấp có thể bổ sung engine riêng.

Azul có engine warp, không phụ thuộc CRIU và không cần cấp thêm capabilities để checkpoint/restore. Theo tài liệu Azul, Warp trở thành engine mặc định trong bản phát hành Zulu tháng 4 năm 2026. Cần kiểm tra chính xác JDK build đang triển khai; không suy luận rằng mọi JDK có CRaC đều có Warp.

### 1.2. Cách chọn engine

Với OpenJDK CRaC dùng CRIU:

~~~bash
java -XX:CRaCEngine=criuengine \
     -XX:CRaCCheckpointTo=/opt/checkpoints \
     -jar app.jar
~~~

Với bản Azul Zulu có Warp:

~~~bash
java -XX:CRaCEngine=warp \
     -XX:CRaCCheckpointTo=/opt/checkpoints \
     -jar app.jar
~~~

Với mô phỏng callback trong môi trường phát triển:

~~~bash
java -XX:CRaCEngine=simengine \
     -XX:CRaCCheckpointTo=./checkpoint \
     -jar app.jar
~~~

Tên engine hợp lệ phụ thuộc JDK build. Nếu chọn engine không có trong runtime, JVM có thể báo lỗi ngay khi khởi động. simengine giúp phát hiện Resource callback không phối hợp đúng, nhưng không kiểm tra được kernel, seccomp, file descriptor, socket hay khả năng tạo ảnh thật.

### 1.3. CRaC trong JVM và checkpoint container là hai ranh giới khác nhau

Trong CRaC của JVM, ứng dụng yêu cầu runtime lưu trạng thái JVM. CRIU có thể được gọi bởi helper của JDK. Trong container checkpoint của Kubernetes, kubelet gọi API checkpoint ở node; container runtime như containerd hoặc CRI-O chuyển yêu cầu tới low-level runtime như runc, rồi runc gọi CRIU.

Luồng Kubernetes ở mức khái quát:

~~~mermaid
flowchart TD
    A[Quản trị viên hoặc controller] --> B[Kubelet checkpoint API trên node]
    B --> C[Container runtime: containerd hoặc CRI-O]
    C --> D[Low-level runtime: runc]
    D --> E[CRIU trên node]
    E --> F[Checkpoint archive]
~~~

Trong mô hình này, ứng dụng trong Pod không nhất thiết cần tự có CAP_CHECKPOINT_RESTORE hay CAP_SYS_PTRACE. Các quyền có thể được cấp cho runtime/helper ở node. Cấp capability vào Pod chỉ vì node cần quyền đó là mở rộng đặc quyền sai ranh giới.

Kubernetes cung cấp kubelet checkpoint API ở node-local endpoint. Tài liệu CRIU mô tả đường đi từ kubelet qua container runtime tới runc và CRIU; checkpoint được lưu thành archive tại thư mục checkpoint trên node. Đây là tính năng của container runtime, không phải thao tác Core.getGlobalContext().register() trong ứng dụng Java.

## 2. Linux capabilities mà CRIU có thể cần

Linux chia một phần quyền vốn gắn với root thành các capability nhỏ hơn. Capability là thuộc tính của thread; quyền thực tế còn phụ thuộc effective, permitted, inheritable, bounding set, user namespace và cách runtime khởi chạy helper.

### 2.1. CAP_CHECKPOINT_RESTORE

CAP_CHECKPOINT_RESTORE được thêm vào Linux kernel 5.9 để tách một số quyền phục vụ checkpoint/restore khỏi capability rộng CAP_SYS_ADMIN. Theo Linux capabilities manual, nó cho phép các thao tác như:

- Cập nhật /proc/sys/kernel/ns_last_pid.
- Dùng tính năng set_tid của clone3().
- Đọc symlink trong /proc/<pid>/map_files của tiến trình khác.

Đây là capability quan trọng với CRIU. Trên Linux hỗ trợ capability này, CRIU có thể chạy non-root trong một số cấu hình với CAP_CHECKPOINT_RESTORE, nhưng không có nghĩa mọi tính năng CRIU đều hoạt động chỉ với quyền đó.

Một giới hạn cần chú ý: một số thao tác truy cập /proc/<pid>/map_files yêu cầu capability ở init user namespace. Có CAP_CHECKPOINT_RESTORE trong user namespace lồng bên trong container không nhất thiết tương đương có capability đó ở init namespace của host.

### 2.2. CAP_SYS_PTRACE

CAP_SYS_PTRACE cho phép thực hiện các thao tác ptrace vượt qua một số kiểm tra quyền thông thường. CRIU dùng cơ chế tracing để dừng và kiểm tra tiến trình cần dump. Khi chạy CRIU non-root, tài liệu CRIU nêu rằng nó cần CAP_SYS_PTRACE hoặc cấu hình kernel.yama.ptrace_scope=0 để có thể interrupt tiến trình.

Không nên hạ ptrace_scope toàn node chỉ để tránh cấp capability cho một workload. Thay đổi đó ảnh hưởng phạm vi tracing trên host. Hãy dùng quyền có phạm vi nhỏ, đúng helper và đúng node khi engine yêu cầu.

### 2.3. CAP_SYS_ADMIN

CAP_SYS_ADMIN là capability rất rộng, bao phủ nhiều thao tác quản trị kernel như mount, namespace và một số thao tác cgroup. Tài liệu CRIU cho phép chạy non-root với CAP_SYS_ADMIN hoặc CAP_CHECKPOINT_RESTORE, nhưng CAP_SYS_ADMIN không phải lựa chọn mặc định an toàn cho mọi container.

Một số đường đi của CRIU có thể vẫn cần CAP_SYS_ADMIN, ví dụ khi xử lý mount/cgroup hoặc tính năng seccomp suspend. Một issue CRIU mở ngày 21-10-2026 ghi nhận rằng CAP_CHECKPOINT_RESTORE không đủ cho đường seccomp-suspend dùng PTRACE_O_SUSPEND_SECCOMP; kernel kiểm tra CAP_SYS_ADMIN trong init user namespace. Vì vậy, nếu checkpoint tiến trình có seccomp filter, hãy kiểm tra đúng CRIU build và kernel thay vì suy luận từ yêu cầu capability tối thiểu của trường hợp không có seccomp.

Nếu tính năng cụ thể yêu cầu CAP_SYS_ADMIN, nên đặt CRIU trong helper hoặc node service được quản trị riêng, với quyền, node, process target và thời gian tồn tại được giới hạn. Tránh cấp CAP_SYS_ADMIN lâu dài cho toàn bộ ứng dụng Java chỉ để hỗ trợ checkpoint.

### 2.4. Các capability bổ sung

Tùy tài nguyên được checkpoint và tính năng CRIU được bật, các capability khác có thể cần:

| Capability | Trường hợp có thể cần | Ghi chú |
|---|---|---|
| CAP_NET_ADMIN | Khôi phục hoặc điều chỉnh network namespace, interface và route | Phụ thuộc cách xử lý network namespace; không phải mọi ứng dụng đều cần |
| CAP_SYS_CHROOT | Thao tác root filesystem/chroot trong một số quy trình restore | Phụ thuộc cấu hình mount namespace |
| CAP_SETUID | Khôi phục UID hoặc chuyển identity của tiến trình | Cần đối chiếu user namespace và mapping UID/GID |
| CAP_SYS_RESOURCE | Một số thao tác liên quan giới hạn tài nguyên | Phụ thuộc tiến trình và runtime |

Danh sách này không phải một manifest cấp quyền dùng chung. Tài liệu CRIU liệt kê các capability bổ sung mà CRIU có thể sử dụng trong chế độ non-root; việc có cần hay không phải dựa trên log, feature check và tài nguyên thực tế.

### 2.5. Bảng quyết định nhanh

| Mô hình | Quyền cần kiểm tra trước |
|---|---|
| Azul Warp trong container | Không cần thêm capability cho engine; vẫn cần quyền filesystem và cấu hình container hợp lệ |
| OpenJDK CRaC criuengine trong Docker | Thường bắt đầu kiểm tra CHECKPOINT_RESTORE và SYS_PTRACE |
| CRIU chạy trực tiếp trong container | CAP_CHECKPOINT_RESTORE, CAP_SYS_PTRACE, user namespace, procfs và các quyền bổ sung theo tài nguyên |
| CRIU do container runtime chạy ở node | Cấu hình capability của runtime/helper trên node; không mặc định cấp cho Pod ứng dụng |
| Containerd/CRI-O checkpoint qua kubelet | Quyền node-side của kubelet/runtime và khả năng CRIU của node |
| simengine | Không cần quyền tạo ảnh hệ điều hành; chỉ dùng để kiểm thử callback |

## 3. Seccomp và checkpoint/restore

Seccomp (secure computing mode) lọc system call mà một tiến trình được phép gọi vào kernel. Container runtime thường áp dụng seccomp profile mặc định để giảm bề mặt tấn công. Kubernetes cho phép chọn profile ở Pod hoặc container.

Seccomp khác với Linux capabilities:

- Capability quyết định tiến trình có được phép thực hiện một nhóm thao tác đặc quyền hay không.
- Seccomp quyết định system call nào được phép đi qua ranh giới userspace/kernel, có thể dựa thêm vào tham số của system call.
- Một tiến trình có capability nhưng seccomp chặn system call cần thiết vẫn nhận lỗi.
- Một system call được seccomp cho phép không tự cấp capability cần thiết cho thao tác đó.

### 3.1. Hai lớp seccomp cần phân biệt

Khi checkpoint một container, có thể có ít nhất hai bộ lọc:

1. **Seccomp của môi trường chạy CRIU/helper:** quyết định CRIU có gọi được system call cần để đọc trạng thái, tạo namespace hoặc khôi phục tiến trình không.
2. **Seccomp của tiến trình đích:** bộ lọc mà ứng dụng đang chạy trước checkpoint. CRIU phải có khả năng xử lý và khôi phục đúng trạng thái filter này.

Đây là hai vấn đề khác nhau. Nới seccomp cho helper không có nghĩa nên xóa bộ lọc bảo vệ của ứng dụng sau restore. Ngược lại, giữ seccomp quá chặt cho CRIU helper có thể khiến chính thao tác dump/restore thất bại trước khi xử lý được tiến trình đích.

### 3.2. CRIU và seccomp filter của tiến trình đích

CRIU có thể lưu và khôi phục trạng thái seccomp của tiến trình. Nhưng để checkpoint tiến trình đang chạy dưới filter, CRIU có thể cần tạm dừng hoặc vượt qua filter trong một số bước kiểm tra/tiêm mã. Khả năng này phụ thuộc kernel và CRIU.

Tài liệu Docker hiện hành ghi rõ seccomp chỉ được CRIU hỗ trợ trên các kernel rất mới. Ngoài ra, issue CRIU #3244 (tháng 10-2026) mô tả đường seccomp_suspend: kernel kiểm tra CAP_SYS_ADMIN trong init user namespace cho PTRACE_O_SUSPEND_SECCOMP; CAP_CHECKPOINT_RESTORE đơn lẻ không thỏa mãn kiểm tra đó. Đây là chi tiết phụ thuộc phiên bản kernel/CRIU, nên cần chạy preflight trên chính node mục tiêu.

Một số hệ thống thử nghiệm dùng seccomp không giới hạn để xác định lỗi có đến từ filter hay không. Đây chỉ là bước chẩn đoán trong môi trường cô lập. Không dùng Unconfined hoặc seccomp=unconfined như giải pháp production mặc định.

### 3.3. Các lựa chọn seccomp trong Kubernetes

Kubernetes hỗ trợ ba kiểu seccompProfile.type:

| Kiểu | Ý nghĩa | Khi dùng |
|---|---|---|
| RuntimeDefault | Dùng profile mặc định của container runtime | Lựa chọn cơ sở cho workload thông thường; profile có thể khác giữa containerd và CRI-O |
| Localhost | Dùng JSON profile đã cài trên node, thường dưới /var/lib/kubelet/seccomp | Khi cần allowlist syscall riêng cho CRIU/helper hoặc workload đặc thù |
| Unconfined | Không áp dụng seccomp filter | Chỉ nên dùng cho chẩn đoán có kiểm soát hoặc trường hợp đặc biệt đã được phê duyệt |

Có thể đặt profile ở Pod-level hoặc container-level. Cấu hình container cụ thể có độ ưu tiên cao hơn Pod-level; container không khai báo sẽ kế thừa profile của Pod. Profile Localhost phải tồn tại trên node, nếu không container có thể không được tạo.

Ví dụ Pod dùng profile mặc định:

~~~yaml
apiVersion: v1
kind: Pod
metadata:
  name: java-service
spec:
  securityContext:
    seccompProfile:
      type: RuntimeDefault
  containers:
    - name: app
      image: example/java-service:latest
      securityContext:
        runAsNonRoot: true
        runAsUser: 10001
        allowPrivilegeEscalation: false
        capabilities:
          drop:
            - ALL
~~~

Đây là cấu hình baseline cho một workload không chạy CRIU helper bên trong container. Với Warp, đây thường là hướng tiếp cận phù hợp hơn vì engine không cần capability CRIU; ứng dụng vẫn phải có quyền ghi vào checkpoint volume và các quyền cần thiết cho chính workload.

### 3.4. Localhost seccomp profile cho CRIU

Khi CRIU chạy bên trong container, profile RuntimeDefault có thể chặn một system call mà engine cần. Khi đó, có thể triển khai một Localhost profile được xây dựng từ đúng phiên bản CRIU, kernel và loại tài nguyên cần checkpoint.

Ví dụ cách tham chiếu profile:

~~~yaml
apiVersion: v1
kind: Pod
metadata:
  name: criu-helper
spec:
  containers:
    - name: checkpoint-helper
      image: example/criu-helper:tested-version
      securityContext:
        seccompProfile:
          type: Localhost
          localhostProfile: crac/criu-helper.json
~~~

Trong ví dụ này, kubelet tìm profile tại vị trí tương ứng dưới /var/lib/kubelet/seccomp/crac/criu-helper.json. Nội dung profile không thể lấy một cách an toàn từ một mẫu chung trên mạng vì danh sách system call phụ thuộc CRIU, kernel, kiến trúc CPU, runtime và tính năng checkpoint được dùng.

Hãy tạo profile theo nguyên tắc allowlist:

1. Bắt đầu từ profile runtime hiện hành.
2. Chạy CRIU preflight và một workload đại diện trong môi trường kiểm thử.
3. Thu thập syscall bị từ chối từ audit/log.
4. Chỉ thêm syscall cần thiết cho tính năng cụ thể.
5. Kiểm thử cả dump lẫn restore, bao gồm lỗi và rollback.
6. Đóng băng phiên bản profile cùng phiên bản kernel, CRIU và runtime đã kiểm thử.

Không sao chép profile của một bản phân phối CRIU sang bản khác mà chưa kiểm chứng. Một profile cho ứng dụng không có network namespace, không có seccomp filter và không có mount đặc biệt có thể không dùng được cho tiến trình khác.

## 4. Security context trong Kubernetes

Security context là tập hợp các thuộc tính quyền và cách ly áp dụng cho Pod hoặc container. Nó không chỉ là capabilities. Khi checkpoint/restore, cần quan tâm đồng thời tới UID/GID, capability set, no_new_privs, seccomp, AppArmor, SELinux, filesystem và namespace.

### 4.1. Các trường quan trọng

| Trường | Tác động | Liên quan checkpoint/restore |
|---|---|---|
| runAsUser, runAsGroup | UID/GID của process | CRIU phải đọc/khôi phục identity và quyền file tương thích |
| runAsNonRoot | Yêu cầu container không chạy UID 0 | Có thể ảnh hưởng cách chạy helper và quyền truy cập /proc |
| capabilities.add/drop | Thêm hoặc bỏ Linux capabilities | Quyết định CRIU có quyền tracing, checkpoint hoặc thao tác namespace không |
| allowPrivilegeEscalation | Điều khiển no_new_privs | Có thể chặn việc lấy thêm quyền qua setuid/file capabilities |
| seccompProfile | Lọc system call | Có thể chặn CRIU hoặc được lưu/khôi phục theo trạng thái tiến trình |
| appArmorProfile | Giới hạn truy cập theo profile AppArmor | Có thể chặn ptrace, procfs, checkpoint path hoặc thao tác file |
| seLinuxOptions | Gắn nhãn SELinux cho process/volume | Có thể chặn truy cập process, file image hoặc mount |
| readOnlyRootFilesystem | Root filesystem chỉ đọc | Checkpoint path và thư mục tạm cần volume ghi riêng |
| privileged | Cấp quyền rất rộng và bỏ qua một số lớp bảo vệ | Có thể làm seccomp/AppArmor/SELinux bị vô hiệu hóa; tránh dùng nếu không bắt buộc |

### 4.2. allowPrivilegeEscalation và no_new_privs

Trong Kubernetes, allowPrivilegeEscalation: false đặt cờ no_new_privs cho container process. Cờ này ngăn tiến trình nhận thêm quyền thông qua một số cơ chế như thực thi setuid binary. Nếu CRIU được cài theo mô hình setuid helper, no_new_privs có thể khiến đường nâng quyền đó không hoạt động.

allowPrivilegeEscalation: false không thể kết hợp với container chạy privileged hoặc có CAP_SYS_ADMIN. Nếu CRIU feature cụ thể cần CAP_SYS_ADMIN, cần đánh giá lại security context và chuyển phần đặc quyền sang helper được quản trị riêng thay vì cố ép mọi thuộc tính vào một Pod.

Khi capability được cấp trực tiếp bởi runtime, không nên tự suy luận rằng no_new_privs làm mất toàn bộ capability đã cấp. Hãy kiểm tra capability set thực tế của helper và cách JDK/CRIU được cài đặt. Điều cần tránh là phụ thuộc vào setuid path trong khi no_new_privs đang chặn việc tăng quyền.

### 4.3. AppArmor và SELinux

Capabilities và seccomp không phải toàn bộ security boundary. AppArmor và SELinux có thể tiếp tục từ chối một thao tác dù process đã có capability và syscall đã được seccomp cho phép.

Các khu vực CRIU thường cần truy cập gồm:

- /proc/<pid>/status, /proc/<pid>/fd, /proc/<pid>/fdinfo.
- /proc/<pid>/maps, /proc/<pid>/map_files và các thông tin memory mapping.
- Checkpoint image directory và thư mục log/work.
- Cgroup filesystem và namespace liên quan.
- File, mount, socket hoặc device được khai báo là external resource.

AppArmor profile cần cho phép đúng đường dẫn và thao tác cần thiết. SELinux cần nhãn phù hợp cho process, checkpoint volume và mount. Không nên chuyển toàn bộ workload sang unconfined chỉ để né một AVC denial; hãy đọc audit log và cập nhật policy có phạm vi hẹp.

CRIU có tùy chọn xử lý LSM profile trong restore, ví dụ --lsm-profile với AppArmor hoặc SELinux, cùng các tùy chọn mount context. Đây là cấu hình của CRIU và runtime; không phải mọi orchestrator đều cho ứng dụng truyền trực tiếp các tùy chọn này.

### 4.4. User namespace và quyền trong init namespace

Container có thể chạy trong user namespace riêng. UID 0 trong container không đồng nghĩa UID 0 trên host. Capability có trong user namespace lồng cũng không tự động có hiệu lực đối với tài nguyên thuộc init user namespace.

Một số thao tác CRIU như đọc map_files của tiến trình khác hoặc suspend seccomp có thể yêu cầu quyền ở init user namespace. Vì vậy:

- Xác định CRIU chạy trong user namespace nào.
- Kiểm tra UID/GID mapping.
- Xác minh capability effective/permitted của CRIU helper.
- Kiểm tra ptrace_scope và quyền truy cập procfs.
- Không cho rằng thêm capability vào Pod là đủ nếu thao tác cần quyền ở namespace của host.

## 5. Cấp quyền cho CRIU mà không mở rộng quyền của ứng dụng

### 5.1. Ưu tiên engine không cần CRIU khi phù hợp

Nếu JDK build cung cấp Warp và ứng dụng không phụ thuộc vào PID/TID được giữ nguyên, đây có thể là cách giảm nhu cầu cấp quyền trong container. Theo tài liệu Azul, Warp không dùng CRIU và không cần thêm Linux capabilities cho checkpoint/restore.

Tuy vậy, cần kiểm tra các giới hạn của engine cụ thể:

- Engine có trong bản JDK đang dùng không?
- Hệ điều hành và kiến trúc CPU có được hỗ trợ không?
- PID/TID sau restore có thay đổi không?
- Ứng dụng hoặc thư viện có lưu PID, TID hay dùng chúng làm identity không?
- Checkpoint image có tương thích giữa các version runtime không?

Engine không cần CRIU không có nghĩa ứng dụng được miễn mọi kiểm soát filesystem, volume, network, identity hoặc secret.

### 5.2. Nếu dùng CRIU trong container

Trong Docker, tài liệu Azul hướng dẫn thêm:

~~~bash
docker run \
  --cap-add=CHECKPOINT_RESTORE \
  --cap-add=SYS_PTRACE \
  --name java-crac \
  my-java-crac-image
~~~

Đây là cấu hình khởi đầu cho CRIU engine trong Docker theo tài liệu Azul. Nó không bảo đảm đủ cho mọi tính năng CRIU, đặc biệt khi checkpoint tiến trình có seccomp filter, thao tác mount/cgroup hoặc external resource. Kiểm tra đúng kernel và CRIU version trước khi đưa vào production.

Tài liệu Docker CLI có ví dụ dùng --security-opt=seccomp:unconfined cho checkpoint. Cần hiểu đó là ví dụ minh họa khả năng tương thích, không phải cấu hình bảo mật khuyến nghị cho production. Hãy ưu tiên profile seccomp chuyên biệt và chỉ dùng unconfined trong môi trường kiểm thử cô lập để xác định nguyên nhân lỗi.

### 5.3. Nếu CRIU được runtime chạy trên node

Với Kubernetes container checkpoint, kubelet và container runtime chạy ở node. Trong mô hình này:

- Quản trị viên node chịu trách nhiệm cài CRIU và cấu hình runtime.
- Capabilities cần thiết được cấp cho runtime/helper theo cách triển khai của node.
- Pod ứng dụng giữ security context của workload thông thường.
- Người dùng gọi kubelet checkpoint API cần quyền xác thực/ủy quyền phù hợp.
- Checkpoint archive phải được lưu ở vị trí bảo vệ trên node.

Không nên cấp CAP_SYS_PTRACE, CAP_CHECKPOINT_RESTORE hoặc CAP_SYS_ADMIN cho mọi Pod chỉ để node có thể checkpoint container. Nếu nền tảng cần một helper privileged, hãy giới hạn nó theo node, service account, API và thao tác cần thực hiện.

## 6. Ví dụ security context cho các mô hình khác nhau

### 6.1. Ứng dụng Java dùng Warp hoặc không chạy CRIU bên trong Pod

Đây là baseline tham khảo cho workload không cần capability CRIU:

~~~yaml
apiVersion: v1
kind: Pod
metadata:
  name: java-crac-warp
spec:
  securityContext:
    runAsNonRoot: true
    runAsUser: 10001
    runAsGroup: 10001
    seccompProfile:
      type: RuntimeDefault
  containers:
    - name: app
      image: example/java-crac:latest
      args:
        - "-XX:CRaCEngine=warp"
        - "-XX:CRaCCheckpointTo=/var/lib/crac"
        - "-jar"
        - "/opt/app/app.jar"
      securityContext:
        allowPrivilegeEscalation: false
        readOnlyRootFilesystem: true
        capabilities:
          drop:
            - ALL
      volumeMounts:
        - name: checkpoint
          mountPath: /var/lib/crac
  volumes:
    - name: checkpoint
      persistentVolumeClaim:
        claimName: java-crac-checkpoints
~~~

Đây là cấu hình minh họa. Image cần có quyền đọc JAR và ghi checkpoint volume; volume phải được mount với ownership phù hợp. Nếu engine hoặc runtime có yêu cầu khác, điều chỉnh dựa trên tài liệu đúng version.

### 6.2. CRIU chạy bên trong container chuyên dụng

Nếu CRIU thật sự chạy bên trong container helper, có thể bắt đầu thử nghiệm với capability riêng:

~~~yaml
apiVersion: v1
kind: Pod
metadata:
  name: criu-helper
spec:
  containers:
    - name: helper
      image: example/criu-helper:tested-version
      securityContext:
        runAsUser: 10001
        runAsGroup: 10001
        runAsNonRoot: true
        allowPrivilegeEscalation: false
        capabilities:
          drop:
            - ALL
          add:
            - CHECKPOINT_RESTORE
            - SYS_PTRACE
        seccompProfile:
          type: Localhost
          localhostProfile: crac/criu-helper.json
      volumeMounts:
        - name: checkpoint
          mountPath: /var/lib/crac
  volumes:
    - name: checkpoint
      persistentVolumeClaim:
        claimName: criu-checkpoints
~~~

Đây chỉ là cấu hình thử nghiệm cho một helper chạy CRIU trong container. Cần xác minh capability có hiệu lực trong đúng user namespace, CRIU có quyền truy cập tiến trình đích, seccomp profile cho phép syscall cần thiết và AppArmor/SELinux cho phép đường dẫn liên quan. Nếu cần seccomp suspend hoặc mount/cgroup, hai capability trên có thể chưa đủ.

Không thêm SYS_ADMIN hoặc bật privileged: true theo kiểu thử lần lượt cho tới khi lệnh chạy được. Nếu log chỉ ra tính năng cần CAP_SYS_ADMIN ở init user namespace, hãy quyết định đặt chức năng đó ở node-side helper có kiểm soát, hoặc thay engine nếu phù hợp.

### 6.3. Kubernetes Restricted Pod Security

Pod Security Standards mức Restricted yêu cầu seccomp là RuntimeDefault hoặc Localhost, drop toàn bộ capabilities và chỉ cho phép add lại NET_BIND_SERVICE. Vì vậy, Pod chạy CRIU trực tiếp với CHECKPOINT_RESTORE và SYS_PTRACE không đáp ứng Restricted profile mặc định.

Nếu tổ chức áp dụng Restricted policy, hãy để checkpoint engine chạy ở node/helper được phê duyệt hoặc tạo ngoại lệ có phạm vi nhỏ, được kiểm soát bằng admission policy và RBAC. Không hạ mức bảo vệ của toàn namespace chỉ để một workload checkpoint được.

## 7. Kubernetes container checkpoint và quyền ở node

### 7.1. Kubelet checkpoint API

Kubernetes cung cấp checkpoint API ở kubelet trên node. Yêu cầu được gửi tới endpoint node-local, kubelet gọi CRI runtime, runtime gọi low-level runtime và CRIU. Quy trình này có thể yêu cầu quyền quản trị node và chứng chỉ client để xác thực API.

Vì endpoint nằm trên kubelet, cần bảo vệ:

- Quyền truy cập node-local endpoint và cổng kubelet.
- Client certificate/key hoặc cơ chế xác thực tương ứng.
- RBAC, quyền quản trị node và audit log.
- Thư mục checkpoint trên node và quyền đọc archive.
- Quy trình sao chép checkpoint ra khỏi node.

Không expose checkpoint API cho người dùng ứng dụng hoặc service account thông thường. Checkpoint chứa trạng thái tiến trình và có thể chứa dữ liệu nhạy cảm trong memory.

### 7.2. Capability của Pod và capability của runtime

Phân biệt hai câu hỏi:

1. Process trong Pod cần capability nào để chạy ứng dụng?
2. Kubelet/container runtime/CRIU trên node cần capability nào để checkpoint process của Pod?

Hai câu trả lời có thể khác nhau. Nếu CRIU chạy ở node, thêm capability vào spec.containers[*].securityContext.capabilities có thể không giúp ích gì. Ngược lại, nếu CRIU chạy bên trong container, runtime phải cấp quyền cho helper và seccomp/AppArmor/SELinux phải cho phép thao tác tương ứng.

### 7.3. Cgroup, mount và namespace

Checkpoint container có thể cần lưu hoặc dựng lại cgroup, mount namespace, PID namespace, network namespace và external resource. CRIU có các tùy chọn quản lý cgroup, mount và namespace, nhưng khả năng thực tế phụ thuộc kernel, cgroup v1/v2, runtime và cách node được cấu hình.

Một số tình huống thường gây lỗi:

- CRIU không thể mount hoặc truy cập cgroup hierarchy.
- Mountpoint trong checkpoint không tồn tại ở node đích.
- Volume external không được map đúng khi restore.
- PID namespace hoặc user namespace không tương thích.
- Network namespace đã thay đổi và socket cũ không thể phục hồi.
- Checkpoint archive được tạo trên kernel/CPU khác với môi trường restore.

Không nên giải quyết lỗi mount bằng cách cấp CAP_SYS_ADMIN cho workload lâu dài. Kiểm tra xem runtime có thể cung cấp cgroup yard, mount mapping hoặc external resource qua helper ở node hay không.

## 8. Bảo vệ security context khi restore checkpoint

Checkpoint archive không chỉ chứa dữ liệu ứng dụng. CRIU có thể lưu trạng thái process credential, capability set, no_new_privs, seccomp filter và trạng thái hệ điều hành khác. Vì vậy, checkpoint từ nguồn không tin cậy phải được coi như một artifact có thể mang theo trạng thái thực thi và quyền của tiến trình.

### 8.1. Rủi ro khi destination security context không được áp dụng

Ngày 21-09-2026, CRI-O công bố advisory CVE-2026-92574/GHSA-pgj4-7h26-2r47: trong các phiên bản bị ảnh hưởng, restore container từ checkpoint có thể giữ UID, capabilities, no_new_privs và seccomp state trong checkpoint thay vì áp dụng security context của container đích. Điều này có thể cho phép checkpoint được tạo có chủ đích khôi phục process với quyền cao hơn policy mà Kubernetes Pod yêu cầu.

Advisory của containerd, CVE-2026-95837/GHSA-p7v4-vr35-mj6f, mô tả vấn đề tương tự trong đường restore qua CRI CreateContainer: process được khôi phục có thể giữ credentials, capabilities, no_new_privs và seccomp state từ checkpoint thay vì security context đích.

Đây là lý do quan trọng để chỉ restore checkpoint từ nguồn tin cậy và giữ container runtime ở phiên bản đã vá. Manifest Pod đích hoặc trạng thái mà control plane báo cáo không tự chứng minh rằng process thực tế đang chạy với đúng UID, capability và seccomp filter.

### 8.2. Phiên bản đã vá theo advisory tháng 11-2026

Theo advisory công bố hiện tại:

| Thành phần | Phiên bản bị ảnh hưởng | Phiên bản đã vá |
|---|---|---|
| CRI-O | <=1.36.5, <=1.35.8, <=1.34.13 | 1.37.0, 1.36.6, 1.35.9, 1.34.14 |
| containerd CRI plugin v2 | >=2.1.0 và <2.2.7; >=2.3.0 và <2.3.4 | 2.2.7, 2.3.4; đường restore qua CreateContainer bị loại bỏ trong 2.4.0 |

CRI-O đưa cấu hình container_level_enabled để thay thế cờ cũ; giá trị mặc định checkpoint_only chặn đường restore bị ảnh hưởng. Advisory cũng khuyến nghị tắt restore path nếu chưa thể nâng cấp.

Containerd 2.2.7 và 2.3.4 vô hiệu hóa restore qua CreateContainer theo mặc định. Bật lại enable_experimental_restore_via_create sẽ tiếp tục để lại rủi ro mà advisory mô tả. Với containerd, hãy dùng phiên bản đã vá và không bật lại đường restore thử nghiệm nếu chưa đánh giá đầy đủ.

Các version trên phản ánh advisory được công bố vào tháng 9 và tháng 10-2026. Trước khi triển khai, cần kiểm tra advisory của nhà cung cấp và bản cập nhật downstream cho đúng bản Kubernetes/OpenShift hoặc bản phân phối runtime.

### 8.3. Quy tắc bảo vệ checkpoint archive

- Chỉ restore checkpoint do pipeline hoặc node tin cậy tạo.
- Xác thực nguồn, chữ ký, digest và provenance của archive/OCI image.
- Giới hạn ai được upload, annotate, publish hoặc yêu cầu restore checkpoint.
- Không cho phép người dùng không tin cậy tạo Pod từ image có chứa checkpoint.
- Bảo vệ thư mục checkpoint và registry như dữ liệu nhạy cảm.
- Mã hóa archive khi lưu trữ/truyền tải và giới hạn thời gian lưu giữ.
- Nâng cấp containerd/CRI-O và CRIU theo advisory bảo mật.
- Sau restore, xác minh process thật trong /proc, không chỉ dựa vào manifest hoặc status của control plane.

## 9. Kiểm tra trạng thái quyền thực tế

Khi gặp lỗi checkpoint, cần thu thập thông tin ở đúng nơi chạy engine. Nếu CRIU chạy trên node, kiểm tra node/helper; nếu CRIU chạy trong container, kiểm tra container đó.

### 9.1. Kiểm tra capability của process

Trong Linux:

~~~bash
grep -E '^(Uid|Gid|CapInh|CapPrm|CapEff|CapBnd|CapAmb|NoNewPrivs|Seccomp):' /proc/self/status
~~~

Các trường quan trọng:

- CapEff: capability đang có hiệu lực.
- CapPrm: capability được phép bật thành effective.
- CapBnd: bounding set giới hạn capability có thể nhận.
- CapAmb: ambient capabilities được kế thừa qua exec theo quy tắc Linux.
- NoNewPrivs: trạng thái no_new_privs.
- Seccomp: chế độ seccomp của process.

Có thể dùng capsh --print hoặc getpcaps <pid> nếu image có cài công cụ. Đừng chỉ kiểm tra UID bằng id; UID 0 trong user namespace không đồng nghĩa có quyền tương đương root trên host.

### 9.2. Kiểm tra seccomp và LSM

~~~bash
cat /proc/self/status | grep -E '^(Seccomp|NoNewPrivs):'
cat /proc/self/attr/current
~~~

Lệnh thứ hai có thể cho biết label LSM hiện tại, ví dụ AppArmor profile. Với SELinux, kiểm tra audit log trên node để tìm AVC denial. Tên công cụ và khả năng đọc audit phụ thuộc bản phân phối Linux.

### 9.3. CRIU preflight

Trên đúng host/container nơi CRIU chạy, dùng kiểm tra của phiên bản CRIU đã cài. Với phiên bản hỗ trợ feature probe seccomp suspend, có thể kiểm tra:

~~~bash
criu check --unprivileged --feature seccomp_suspend
~~~

Đây là kiểm tra một feature cụ thể; phải dùng đúng tùy chọn mà CRIU version đang cài hỗ trợ. Exit status khác 0 cần được đọc cùng stdout/stderr và log chi tiết, vì có thể là thiếu capability, thiếu kernel feature hoặc gọi sai chế độ kiểm tra.

Không coi criu check thành công là bằng chứng mọi loại process đều checkpoint được. Hãy chạy một thử nghiệm dump/restore với cùng namespace, seccomp profile, cgroup, volume và tài nguyên mà ứng dụng production đang sử dụng.

## 10. Troubleshooting theo triệu chứng

| Triệu chứng | Nguyên nhân có thể | Cách điều tra |
|---|---|---|
| Operation not permitted khi CRIU attach process | Thiếu CAP_SYS_PTRACE, ptrace_scope hoặc capability nằm sai user namespace | Kiểm tra CapEff, Yama ptrace_scope và namespace của helper |
| CRIU báo thiếu CAP_CHECKPOINT_RESTORE | Kernel cũ hoặc capability không nằm trong effective/permitted set | Kiểm tra kernel >= 5.9, bounding set và user namespace |
| couldn't suspend seccomp: Operation not permitted | Kernel gate PTRACE_O_SUSPEND_SECCOMP cần CAP_SYS_ADMIN trong init user namespace theo đường CRIU hiện hành | Kiểm tra CRIU/kernel version và feature probe; cân nhắc node-side helper |
| Checkpoint thất bại với RuntimeDefault | Runtime seccomp profile chặn syscall cần thiết | Kiểm tra audit/log, thử Localhost profile trong môi trường test |
| Checkpoint có thể tạo nhưng restore lỗi mount | Mountpoint, cgroup hoặc external volume không được map | Kiểm tra namespace, mount table, cgroup hierarchy và external resource |
| Không đọc được /proc/<pid>/map_files | Thiếu quyền hoặc capability không có trong init user namespace | Kiểm tra CAP_CHECKPOINT_RESTORE ở đúng namespace và procfs mount |
| SELinux AVC denial | Label hoặc policy không cho phép truy cập process/image path | Đọc audit log và tạo policy có phạm vi nhỏ |
| AppArmor DENIED | Profile chặn ptrace, procfs, mount hoặc checkpoint directory | Xem audit log và điều chỉnh profile của helper |
| Helper có capability nhưng vẫn lỗi khi exec CRIU | no_new_privs, setuid/file capability hoặc bounding set ngăn tăng quyền | Kiểm tra NoNewPrivs, CapBnd và cách cài CRIU |
| Container chạy được nhưng Pod bị admission từ chối | Pod Security Standards Restricted không cho phép capability CRIU | Chuyển engine về node/helper hoặc xin ngoại lệ hẹp |
| Checkpoint archive restore với quyền khác manifest | Runtime restore không áp dụng destination security context hoặc phiên bản có lỗ hổng | Kiểm tra CVE-2026-92574/CVE-2026-95837 và nâng cấp runtime |
| Restore thành công nhưng process không truy cập được volume | UID/GID, fsGroup, SELinux label hoặc mount permission khác | Xác minh owner, label, mount và quyền thực tế sau restore |

## 11. Quy trình triển khai an toàn

### Giai đoạn xác định engine

1. Xác định JDK vendor, version và engine thực tế.
2. Phân biệt JVM CRaC checkpoint với container checkpoint qua CRI.
3. Xác định CRIU chạy trong container hay ở node.
4. Xác nhận kernel, CRIU, container runtime, low-level runtime và cgroup version.
5. Xác định tiến trình có seccomp filter, network namespace, mount namespace hoặc tài nguyên external nào.

### Giai đoạn cấp quyền

1. Bắt đầu từ quyền mặc định của runtime.
2. Chỉ cấp CHECKPOINT_RESTORE và SYS_PTRACE cho CRIU helper nếu engine cần.
3. Xác minh capability có hiệu lực trong namespace mà thao tác yêu cầu.
4. Dùng seccomp Localhost profile nếu RuntimeDefault chặn syscall cần thiết.
5. Kiểm tra AppArmor và SELinux riêng biệt.
6. Chỉ dùng CAP_SYS_ADMIN khi feature cụ thể cần và được chứng minh bằng log/preflight.
7. Không bật privileged hoặc unconfined cho toàn bộ workload để giải quyết lỗi không rõ nguyên nhân.

### Giai đoạn checkpoint/restore

1. Chuẩn bị volume ghi ảnh và quyền sở hữu.
2. Quiesce ứng dụng và xử lý Resource callback.
3. Tạo checkpoint trên đúng runtime/kernel mục tiêu.
4. Xác minh archive, metadata và log CRIU.
5. Restore trên môi trường tương thích.
6. Kiểm tra UID/GID, capabilities, NoNewPrivs, seccomp và LSM label thực tế.
7. Kiểm tra kết nối, volume, readiness và nghiệp vụ.
8. Chỉ phát hành checkpoint image khi pipeline xác nhận provenance và kiểm thử thành công.

## 12. Ma trận kiểm thử security context

| Trường hợp | Điều cần xác nhận |
|---|---|
| Warp + RuntimeDefault + non-root | Checkpoint/restore hoạt động mà không thêm capability CRIU |
| CRIU + RuntimeDefault | Ghi nhận syscall/capability nào bị chặn |
| CRIU + Localhost profile | Helper chỉ được thêm syscall cần thiết |
| CRIU + CHECKPOINT_RESTORE và SYS_PTRACE | Quyền có hiệu lực trong đúng user namespace |
| Process đích có seccomp filter | Kernel/CRIU hỗ trợ seccomp suspend và restore filter |
| no_new_privs=1 | Helper không phụ thuộc vào setuid path |
| AppArmor/SELinux enforcing | Không có denial ngoài policy được phê duyệt |
| Restore dưới UID/GID khác | Volume, file ownership và process identity đúng |
| Restore checkpoint không tin cậy | Runtime từ chối hoặc pipeline chặn artifact |
| CRI-O/containerd ở version đã vá | Destination security context được bảo vệ theo advisory |
| Kubernetes Restricted namespace | Pod app không phải nhận capability CRIU nếu engine chạy node-side |

## 13. Nguyên tắc cần nhớ

- Xác định engine trước khi cấp quyền: CRIU, Warp và simengine có yêu cầu khác nhau.
- OpenJDK CRaC criuengine dùng CRIU; trong container thường cần CAP_CHECKPOINT_RESTORE và CAP_SYS_PTRACE.
- CAP_CHECKPOINT_RESTORE không đồng nghĩa có đủ quyền cho mọi feature CRIU; seccomp suspend và namespace có thể cần điều kiện bổ sung.
- Warp của Azul không dùng CRIU và không cần thêm capability checkpoint/restore, nhưng phụ thuộc bản build và nền tảng được hỗ trợ.
- simengine chỉ mô phỏng callback, không tạo ảnh tiến trình có thể triển khai.
- Seccomp, capabilities, no_new_privs, AppArmor và SELinux là các lớp kiểm soát độc lập.
- Kubernetes RuntimeDefault, Localhost và Unconfined có phạm vi khác nhau; profile RuntimeDefault còn khác theo runtime.
- Không dùng privileged hoặc seccomp unconfined làm cấu hình mặc định.
- Khi CRIU chạy trên node, quyền node-side không nên được cấp cho mọi Pod ứng dụng.
- Checkpoint archive phải đến từ nguồn tin cậy và được bảo vệ như dữ liệu nhạy cảm.
- Cập nhật containerd/CRI-O theo advisory bảo mật và xác minh process thực tế sau restore.

## 14. Tài liệu tham khảo

- [CRaC — Checkpoint engines](https://crac.org/reference/engines/): phân biệt criuengine, simengine và engine vendor như Warp.
- [Azul — Running CRaC in a Container](https://docs.azul.com/crac/deployment/docker-container): cấu hình Docker và capability cho CRIU engine.
- [Azul — Anatomy of CRaC Processes](https://docs.azul.com/crac/detailed/anatomy): cách CRIU engine làm việc với process và PID.
- [Azul — CRaC Engines](https://docs.azul.com/crac/usage/crac-engines): Warp và CRIU engine theo bản phân phối Azul.
- [OpenJDK CRaC README](https://github.com/openjdk/crac/blob/crac/README.md): prerequisite CRIU và cách cài quyền cho binary.
- [CRIU documentation](https://github.com/checkpoint-restore/criu/blob/criu-dev/Documentation/criu.txt): non-root mode, capabilities, namespace, cgroup và external resource.
- [Linux capabilities manual](https://man7.org/linux/man-pages/man7/capabilities.7.html): định nghĩa CAP_CHECKPOINT_RESTORE và các capability khác.
- [Kubernetes — Configure a Security Context](https://kubernetes.io/docs/tasks/configure-pod-container/security-context/): UID/GID, capabilities, allowPrivilegeEscalation, no_new_privs và filesystem.
- [Kubernetes — Seccomp and Kubernetes](https://kubernetes.io/docs/reference/node/seccomp/): RuntimeDefault, Localhost, Unconfined và profile JSON.
- [Kubernetes — Linux kernel security constraints](https://kubernetes.io/docs/concepts/security/linux-kernel-security-constraints/): seccomp, AppArmor, SELinux và privileged container.
- [CRIU — Kubernetes checkpointing](https://criu.org/Kubernetes): kubelet checkpoint API và đường đi qua container runtime, runc, CRIU.
- [CRI-O GHSA-pgj4-7h26-2r47 / CVE-2026-92574](https://github.com/cri-o/cri-o/security/advisories/GHSA-pgj4-7h26-2r47): restore có thể bỏ qua destination security context trong các phiên bản bị ảnh hưởng.
- [containerd GHSA-p7v4-vr35-mj6f / CVE-2026-95837](https://github.com/advisories/GHSA-p7v4-vr35-mj6f): checkpoint restore qua CRI CreateContainer và destination security context.
- [CRIU issue #3244](https://github.com/checkpoint-restore/criu/issues/3244): yêu cầu CAP_SYS_ADMIN của đường seccomp-suspend trong kernel/CRIU được thảo luận tháng 10-2026.

Phiên bản kernel, CRIU, container runtime và JDK thay đổi theo thời gian. Hãy đối chiếu tài liệu của đúng bản đang triển khai, chạy preflight trên node đích và kiểm thử cả checkpoint lẫn restore trước khi áp dụng security context vào production.
