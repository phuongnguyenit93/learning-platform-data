# Quyền hệ điều hành và capabilities theo yêu cầu của từng cơ chế

Khi thực hành CRaC, một trong những nguyên nhân khiến checkpoint hoặc restore thất bại là tiến trình không có đủ quyền ở cấp hệ điều hành. Ứng dụng có thể chạy bình thường, các callback `org.crac.Resource` có thể được đăng ký đúng, nhưng thao tác chụp hoặc khôi phục trạng thái tiến trình vẫn bị kernel, container runtime hay chính sách bảo mật từ chối.

Muốn cấp quyền chính xác, trước hết phải xác định cơ chế checkpoint/restore đang sử dụng và thao tác hệ điều hành mà cơ chế đó cần thực hiện. CRaC API và quyền hệ điều hành là hai lớp khác nhau: API giúp ứng dụng chuẩn bị tài nguyên; cơ chế checkpoint/restore cần quyền để quan sát, lưu và khôi phục trạng thái tiến trình. Không có một danh sách capability cố định đúng cho mọi JDK, CRIU, kernel, container runtime và loại tài nguyên.

## 1. Phân biệt quyền của ứng dụng và quyền checkpoint/restore

Trong một triển khai Java có CRaC, có thể gặp các lớp quyền sau:

| Lớp quyền | Kiểm soát điều gì? | Ví dụ |
|---|---|---|
| User và group của tiến trình | Danh tính mà ứng dụng và callback sử dụng | UID/GID chạy JVM, quyền đọc cấu hình, quyền ghi thư mục checkpoint |
| Quyền file và thư mục (DAC) | Ai được đọc, ghi, thực thi hoặc truy cập đường dẫn | Owner/mode của checkpoint directory, quyền truy cập file cấu hình |
| Linux capabilities | Các thao tác đặc quyền được tách khỏi quyền root truyền thống | Theo dõi tiến trình, thao tác namespace, cấu hình network namespace |
| Namespace và cgroup | Phạm vi tiến trình, mount, mạng, IPC và tài nguyên mà tiến trình nhìn thấy | PID namespace, mount namespace, cgroup v2 |
| Chính sách bảo mật bổ sung | Những hành động bị giới hạn dù UID hoặc capability có vẻ phù hợp | seccomp, SELinux, AppArmor, Yama ptrace policy |

Điểm cần nhớ là quyền tạo file checkpoint không đồng nghĩa với quyền chụp một tiến trình. Ngược lại, một tiến trình có quyền checkpoint vẫn có thể thất bại khi không ghi được ảnh vào thư mục đích. Hãy kiểm tra từng lớp riêng biệt.

### CRaC API không tự cấp quyền root

Ứng dụng sử dụng `org.crac.Core`, `Context` và `Resource` để đăng ký callback như `beforeCheckpoint` và `afterRestore`. Các callback này chạy trong ngữ cảnh của ứng dụng. Bản thân việc gọi API Java không tự cấp `CAP_SYS_ADMIN`, `CAP_SYS_PTRACE` hay quyền quản trị hệ điều hành.

Với các bản phân phối CRaC trên Linux sử dụng CRIU để dump/restore tiến trình, CRIU và kernel thực hiện phần thao tác cấp hệ điều hành. Quyền cần thiết phụ thuộc vào cách CRIU chạy, tiến trình được chụp, loại namespace, tài nguyên đang mở, kernel và cấu hình bảo mật. Một bản phân phối hoặc nền tảng khác có thể đóng gói cơ chế này theo cách khác; cần đọc yêu cầu của đúng runtime đang dùng.

## 2. Linux capabilities là gì?

Linux truyền thống có mô hình phân biệt user thường và root. Root thường có quyền thực hiện rất nhiều thao tác quản trị. Linux capabilities chia một phần quyền đặc biệt thành các nhóm nhỏ hơn, để một tiến trình có thể được cấp một số thao tác cần thiết mà không cần chạy toàn bộ dưới quyền root.

Một capability có thể nằm trong các tập quyền khác nhau của tiến trình:

- **Permitted:** tập quyền mà tiến trình được phép kích hoạt.
- **Effective:** tập quyền đang có hiệu lực khi kernel kiểm tra thao tác.
- **Inheritable:** tập quyền có thể tham gia vào quá trình kế thừa khi thực thi chương trình khác.
- **Bounding:** giới hạn trên đối với capability mà tiến trình có thể nhận qua `execve`.
- **Ambient:** một tập quyền có thể được giữ qua một số lần `execve` đối với chương trình không có file capability đặc biệt.

Vì vậy, chỉ nhìn thấy tên capability trong cấu hình container chưa đủ để kết luận thao tác sẽ thành công. Cần kiểm tra quyền thực tế của tiến trình, cách runtime áp dụng capability, namespace hiện hành và các chính sách bảo mật khác.

### Những capability có thể liên quan

Bảng dưới đây mô tả các capability thường được xem xét trong một số cơ chế CRIU trên Linux. Đây là bản đồ để điều tra, không phải danh sách cần cấp đồng loạt.

| Capability | Cơ chế hoặc thao tác có thể liên quan | Lưu ý khi thực hành |
|---|---|---|
| `CAP_CHECKPOINT_RESTORE` | Một số thao tác đặc thù cho checkpoint/restore, ví dụ thiết lập PID trong một số trường hợp, đọc một số thông tin tiến trình qua `/proc` | Được bổ sung từ Linux 5.9. Không thay thế tất cả quyền mà CRIU có thể cần. |
| `CAP_SYS_PTRACE` | Kiểm tra hoặc truy cập trạng thái của tiến trình khác qua cơ chế ptrace | Còn phụ thuộc quan hệ UID, Yama, namespace và chính sách bảo mật. |
| `CAP_SYS_ADMIN` | Một số thao tác quản trị rộng như mount hoặc thao tác namespace trong các cấu hình nhất định | Rất rộng; không cấp theo thói quen. Xác định chính xác thao tác nào cần nó. |
| `CAP_NET_ADMIN` | Cấu hình interface, route hoặc thành phần mạng trong network namespace | Chỉ xem xét khi quy trình restore thực sự quản lý cấu hình mạng. |
| `CAP_SYS_RESOURCE` | Một số thao tác vượt giới hạn tài nguyên hoặc khôi phục giới hạn tiến trình | Kiểm tra giới hạn cụ thể; không cấp nếu chỉ cần điều chỉnh cấu hình ulimit hợp lệ. |
| `CAP_SETUID`, `CAP_SETGID` | Chuyển danh tính user/group trong một số quy trình khôi phục | Phải khớp UID/GID mapping và mô hình cô lập của môi trường. |
| `CAP_DAC_OVERRIDE`, `CAP_DAC_READ_SEARCH` | Bỏ qua một phần kiểm tra quyền truy cập file thông thường | Thường nên sửa owner, group, mode hoặc mount trước khi cân nhắc quyền bypass. |
| `CAP_MKNOD` | Tạo device node trong trường hợp cơ chế cần khôi phục loại file này | Không phải yêu cầu mặc định của mọi ứng dụng Java. |

`CAP_CHECKPOINT_RESTORE` là capability chuyên biệt, nhưng tên của nó không có nghĩa là cứ cấp capability này là CRIU có thể hoạt động. Một thao tác có thể còn cần quyền ptrace, mount, network, cgroup hoặc quyền truy cập file. Tương tự, capability có mặt trong container nhưng bị seccomp, LSM hoặc namespace giới hạn thì thao tác vẫn có thể thất bại.

### Root trong container không nhất thiết là root trên host

Container có thể chạy UID 0 bên trong nhưng được ánh xạ sang một UID không đặc quyền trên host. Khi user namespace hoặc user namespace remapping được bật, capability của tiến trình được xét trong phạm vi user namespace tương ứng. Một capability trong namespace con không tự động cho phép quản trị tài nguyên của host.

Điều này giải thích vì sao `id` trong container có thể hiển thị `uid=0(root)` nhưng CRIU vẫn không thể truy cập một tiến trình host, mount filesystem của host hoặc thay đổi tài nguyên nằm ngoài namespace của container.

## 3. Xác định quyền theo từng cơ chế hệ điều hành

Thay vì hỏi chung chung “CRaC cần capability nào?”, hãy phân rã thao tác checkpoint/restore thành các cơ chế mà nó thực sự sử dụng.

### 3.1. Quan sát và đóng băng trạng thái tiến trình

Để dump một tiến trình, công cụ checkpoint có thể cần kiểm tra memory map, thread, trạng thái tiến trình và các file descriptor. Nếu công cụ thao tác trên tiến trình khác, quyền ptrace và chính sách kiểm soát ptrace có thể ảnh hưởng.

Các yếu tố cần kiểm tra:

- JVM và công cụ checkpoint có chạy cùng user hay không.
- Tiến trình mục tiêu có nằm trong PID namespace mà công cụ nhìn thấy hay không.
- Capability ptrace có trong tập quyền hiệu lực và đúng user namespace hay không.
- Kernel có bật Yama hay không; giá trị `ptrace_scope` có hạn chế quan hệ giữa tiến trình tracer và target hay không.
- seccomp hoặc LSM có chặn syscall hay hành động truy cập tiến trình hay không.

Không nên tắt kiểm soát ptrace toàn hệ thống chỉ để làm một bài thực hành chạy được. Hãy thu hẹp phạm vi tiến trình và cấp quyền cho đúng công cụ, đúng container hoặc đúng môi trường thử nghiệm theo chính sách của máy.

### 3.2. PID, user và các namespace

Checkpoint có thể phải khôi phục tiến trình trong các namespace tương ứng hoặc thiết lập một số thông tin định danh. Các thao tác này chịu ảnh hưởng bởi kernel, loại namespace và cấu hình user namespace.

Hãy xác định:

- Công cụ checkpoint có nhìn thấy PID của JVM hay không.
- PID namespace có được giữ nguyên hoặc tái tạo theo cách mà runtime hỗ trợ hay không.
- UID/GID của tiến trình có ánh xạ hợp lệ trong user namespace đích hay không.
- Runtime có cho phép thao tác namespace cần thiết hay không.
- Tiến trình restore có được cấp đúng danh tính và quyền truy cập file sau khi khôi phục hay không.

Một số thao tác namespace cần quyền quản trị trong namespace tương ứng; một số thao tác khác có thể được hỗ trợ thông qua user namespace. Không suy ra rằng `CAP_SYS_ADMIN` trong container luôn có hiệu lực trên host.

### 3.3. Mount namespace và filesystem

CRIU có thể cần tái tạo hoặc kiểm tra các mount phụ thuộc vào tiến trình. Quyền mount phụ thuộc loại filesystem, mount namespace, user namespace, kernel và cách host cho phép thao tác. Các mount bind, filesystem đặc biệt hoặc mount thuộc host có thể có giới hạn riêng.

Ngoài quyền mount, thư mục lưu checkpoint phải đáp ứng các yêu cầu thông thường:

- User chạy quy trình tạo checkpoint có quyền ghi và traverse tất cả thư mục cha.
- User chạy restore có quyền đọc ảnh checkpoint và các file phụ trợ.
- Dung lượng đĩa và quota đủ cho toàn bộ ảnh cùng file tạm.
- Mount chứa ảnh checkpoint có hành vi tương thích với runtime; kiểm tra các tùy chọn như read-only, `noexec` hoặc chính sách bảo mật của mount khi có lỗi liên quan.
- Owner, group, mode và nhãn SELinux của thư mục/file cho phép đúng tiến trình truy cập.
- Các đường dẫn được tham chiếu trong ảnh vẫn tồn tại và có ý nghĩa trong môi trường restore.

Ví dụ, nếu JVM chạy bằng UID `10001` nhưng thư mục `/var/lib/myapp/checkpoint` thuộc `root:root` và mode `0700`, JVM không thể tự ghi checkpoint. Có thể chuẩn bị thư mục với owner/group phù hợp trong bước dựng image hoặc khởi tạo volume, thay vì cấp `CAP_DAC_OVERRIDE` cho ứng dụng.

Checkpoint có thể chứa heap, cấu hình, token hoặc dữ liệu nhạy cảm tại thời điểm chụp. Hãy giới hạn quyền đọc, bảo vệ nơi lưu trữ và đường truyền ảnh checkpoint, đặt chính sách lưu giữ/xóa, và tránh đưa ảnh vào artifact công khai.

### 3.4. Network namespace và kết nối

Nếu quy trình checkpoint/restore phải khôi phục network namespace hoặc cấu hình interface, route hay firewall, các thao tác đó có thể cần `CAP_NET_ADMIN` trong network namespace thích hợp. Nếu ứng dụng đóng socket và tạo lại kết nối trong `afterRestore`, nhu cầu quyền có thể khác đáng kể so với việc khôi phục nguyên trạng socket.

Không phải socket nào cũng có thể được tiếp tục an toàn sau restore. Kết nối tới database, broker, HTTP service hoặc DNS có thể đã hết hạn, peer đã đóng hoặc địa chỉ đã thay đổi. Trong ứng dụng Java, cách thường dùng là đóng resource trước checkpoint và kết nối lại sau restore qua `Resource` callback. Khi đó, hãy cấp quyền network theo nhu cầu thông thường của ứng dụng; không cấp `CAP_NET_ADMIN` chỉ vì ứng dụng mở kết nối TCP.

### 3.5. Cgroup và giới hạn tài nguyên

Cgroup giới hạn và thống kê tài nguyên của nhóm tiến trình. Môi trường container thường chỉ cho phép container quản lý một subtree cgroup được delegate, không cho phép ghi tùy ý vào toàn bộ cây cgroup của host.

Khi checkpoint/restore liên quan tới freezer, cgroup hoặc giới hạn tài nguyên, cần kiểm tra:

- Hệ thống dùng cgroup v1 hay v2.
- Runtime có hỗ trợ thao tác checkpoint/restore trên phiên bản cgroup đó hay không.
- Công cụ có quyền truy cập đúng cgroup và subtree đã được delegate hay không.
- CPU, memory, PID limit và các giới hạn khác có đủ cho cả giai đoạn dump lẫn restore hay không.
- Sau restore, tiến trình có nằm trong cgroup đích với giới hạn dự kiến hay không.

Không cấp quyền ghi toàn bộ `/sys/fs/cgroup` cho ứng dụng chỉ để vượt qua lỗi permission. Nếu nền tảng không delegate cgroup cần thiết, thay đổi cấu hình container runtime hoặc nhờ quản trị viên chuẩn bị môi trường thử nghiệm phù hợp.

### 3.6. File descriptor, thiết bị và IPC

Tiến trình Java có thể giữ file, pipe, Unix domain socket, shared memory, semaphore, device hoặc tài nguyên native do thư viện tạo ra. Một số loại có thể được CRIU xử lý trong điều kiện nhất định; một số loại cần đóng và tạo lại; một số loại không được hỗ trợ trong cấu hình đang dùng.

Đừng mặc định rằng giữ nguyên object Java đồng nghĩa với việc handle ở kernel còn dùng được. Hãy kiểm kê resource của ứng dụng và xác định rõ loại nào:

1. Có thể được giữ qua checkpoint theo đúng tài liệu runtime.
2. Phải đóng trong `beforeCheckpoint` và mở lại trong `afterRestore`.
3. Phải drain hoặc hoàn tất công việc trước checkpoint.
4. Không thể hỗ trợ trong môi trường triển khai hiện tại và cần thay đổi thiết kế.

Quyền tạo device node hoặc truy cập thiết bị chỉ nên được xem xét nếu ứng dụng thực sự dùng thiết bị đó. Một dịch vụ Spring Boot thông thường không nên nhận các capability liên quan tới thiết bị theo cấu hình mẫu của một workload khác.

## 4. Những lớp bảo mật có thể chặn thao tác dù đã cấp capability

Linux capabilities chỉ là một phần của quyết định cho phép. Khi điều tra lỗi, hãy kiểm tra thêm các lớp sau.

| Lớp bảo mật | Ảnh hưởng có thể gặp | Hướng kiểm tra |
|---|---|---|
| seccomp | Chặn syscall mà CRIU hoặc runtime cần gọi | Kiểm tra seccomp profile của container và log của runtime |
| SELinux | Từ chối truy cập file, process hoặc thao tác kernel theo security label | Kiểm tra AVC denial và label của file/process |
| AppArmor | Giới hạn đường dẫn, capability hoặc hành động của tiến trình | Kiểm tra profile đang gắn và log denial |
| Yama ptrace | Hạn chế tiến trình nào được attach hoặc inspect tiến trình khác | Kiểm tra `ptrace_scope` và quan hệ tracer/target |
| User namespace | Giới hạn phạm vi UID/GID và capability | Kiểm tra mapping và namespace mà tiến trình đang ở |
| Capability bounding set | Loại bỏ capability khỏi tập quyền tối đa của tiến trình | Kiểm tra cấu hình container/systemd và `/proc` |
| No-new-privileges | Ngăn tiến trình có thêm quyền qua một số lần `execve` | Kiểm tra cách công cụ checkpoint được khởi chạy và capability đã có sẵn |

Ví dụ, container được cấu hình `cap_add` nhưng seccomp profile chặn syscall cần thiết thì thao tác vẫn thất bại. Tương tự, file checkpoint có mode cho phép ghi nhưng SELinux không cho domain của JVM ghi vào đường dẫn đó. Hãy tìm đúng lớp từ chối qua log và thông báo kernel thay vì lần lượt tắt toàn bộ chính sách bảo mật.

## 5. Cấu hình container theo nguyên tắc least privilege

Khi chạy Java trong Docker hoặc Kubernetes, quyền của tiến trình được hình thành từ nhiều nguồn: user/group trong image, capability được runtime cấp, namespace, seccomp, LSM, mount và cgroup. `privileged: true` thường làm mở rộng quyền rất lớn và giảm đáng kể hiệu quả cô lập của container.

Một cấu hình ứng dụng có thể bắt đầu từ danh sách capability rỗng, user không phải root và thư mục checkpoint được cấp quyền tường minh:

```yaml
services:
  crac-app:
    image: my-java-app:latest
    user: "10001:10001"
    volumes:
      - ./checkpoint:/var/lib/myapp/checkpoint
    cap_drop:
      - ALL
    security_opt:
      - no-new-privileges:true
    # Chỉ bổ sung capability sau khi kiểm tra đúng cơ chế CRIU,
    # kernel, runtime và chính sách bảo mật của môi trường đích.
    # cap_add:
    #   - CHECKPOINT_RESTORE
    #   - SYS_PTRACE
```

Đây là điểm xuất phát để thiết kế quyền, không phải cấu hình bảo đảm checkpoint/restore sẽ chạy. Với một số cơ chế, container sẽ cần capability hoặc policy bổ sung; ví dụ trên cố ý không đoán một tập quyền đầy đủ cho mọi môi trường. Nếu cần `SYS_ADMIN`, hãy xác định thao tác cụ thể, phạm vi namespace và khả năng thay thế bằng một thiết kế ít quyền hơn trước khi thêm nó.

Trong Kubernetes, các trường `runAsUser`, `runAsGroup`, `allowPrivilegeEscalation`, `capabilities`, `seccompProfile` và chính sách Pod Security cùng quyết định khả năng hoạt động. Môi trường áp dụng Pod Security Standards ở mức Restricted thường không cho phép tùy ý thêm capability. Nếu CRIU cần quyền vượt chính sách của workload thông thường, hãy chuẩn bị node hoặc môi trường lab riêng với cấu hình được quản trị viên phê duyệt, thay vì nới lỏng chính sách cho toàn namespace.

### Rootless và rootful

**Rootful checkpoint/restore** thường chạy công cụ với quyền quản trị cao hơn để thao tác trên tiến trình và tài nguyên hệ thống. Cách này có thể dễ thiết lập hơn trong lab do quản trị viên kiểm soát, nhưng cần giới hạn phạm vi host, dữ liệu và workload được phép chụp.

**Rootless checkpoint/restore** chạy dưới user thường, thường dựa vào user namespace và các tính năng kernel hỗ trợ. Nó có thể giảm phạm vi ảnh hưởng tới host, nhưng không phải mọi loại namespace, mount, network, device hoặc process đều được hỗ trợ giống rootful. Thành công phụ thuộc kernel, CRIU, UID/GID mapping và tính năng mà ứng dụng sử dụng.

Không nên kết luận rằng rootless luôn không cần capability, hoặc rootful luôn phải chạy toàn bộ ứng dụng bằng root. Hãy tách user chạy JVM, user chạy công cụ checkpoint và quyền quản trị cần cho từng thao tác. Khi nền tảng cho phép, một helper có phạm vi quyền hẹp có thể thực hiện thao tác đặc quyền thay cho việc cấp toàn bộ quyền đó cho tiến trình ứng dụng lâu dài.

## 6. Quyền khi chạy dưới systemd

Nếu JVM chạy như một service trên Linux host, systemd có thể giới hạn quyền thông qua các tùy chọn của unit:

- `User=` và `Group=` xác định danh tính tiến trình.
- `CapabilityBoundingSet=` giới hạn capability tối đa.
- `AmbientCapabilities=` có thể chuyển một số capability sang tiến trình được thực thi.
- `NoNewPrivileges=` ngăn việc tăng quyền qua `execve` theo các cơ chế bị tùy chọn này kiểm soát.
- `RestrictNamespaces=` giới hạn loại namespace được tạo.
- `SystemCallFilter=` giới hạn syscall.
- `PrivateUsers=`, `PrivateNetwork=`, `ProtectProc=` và các tùy chọn hardening khác thay đổi phạm vi mà service nhìn thấy hoặc truy cập.

Các tùy chọn hardening có thể làm CRIU không thực hiện được thao tác cần thiết dù capability đã được khai báo. Khi service được bảo vệ bởi systemd, hãy xem toàn bộ unit và drop-in đang có hiệu lực; đừng chỉ xem một file unit gốc rồi bỏ qua override. Cấu hình capability trong unit cũng cần được kiểm tra cùng user namespace, LSM và chính sách của host.

## 7. Quy trình xác định quyền tối thiểu trong môi trường lab

Hãy làm theo một chuỗi kiểm tra có thể lặp lại để biết chính xác lớp nào đang từ chối thao tác.

### Bước 1: Ghi lại nền tảng

Thu thập phiên bản JDK/CRaC, CRIU nếu có, kernel, kiến trúc CPU, container runtime, Docker/Kubernetes hoặc systemd và loại cgroup. Checkpoint chỉ nên được tạo và restore trong tổ hợp môi trường được runtime hỗ trợ.

```bash
uname -a
id
java -version
criu --version
```

Nếu lệnh `criu` không tồn tại, có thể runtime đã đóng gói cơ chế theo cách khác hoặc công cụ chưa được cài. Không kết luận ngay rằng CRaC API không hoạt động; xác định cách bản phân phối JDK thực hiện checkpoint trước.

### Bước 2: Kiểm tra danh tính và capability thực tế

```bash
id
grep -E '^(Uid|Gid|CapInh|CapPrm|CapEff|CapBnd|CapAmb):' /proc/self/status
```

Nếu có công cụ `capsh`, có thể dùng `capsh --print` để đọc cách diễn giải các tập capability. Với tiến trình khác, `getpcaps <PID>` có thể hữu ích nếu công cụ được cài và user hiện tại được phép truy cập tiến trình đó.

Đối chiếu output với cấu hình container hoặc systemd. Một capability được khai báo trong manifest nhưng không xuất hiện trong tập quyền hiệu lực của tiến trình chưa chắc đã được cấp thành công.

### Bước 3: Kiểm tra khả năng của CRIU và kernel

Với môi trường dùng CRIU, lệnh kiểm tra của CRIU có thể phát hiện một số tính năng kernel hoặc quyền cần thiết:

```bash
criu check
```

Đọc toàn bộ output, đặc biệt là tính năng không được hỗ trợ và thông báo permission denied. Lệnh này là phép kiểm tra nền tảng, không thay thế việc thử dump và restore ứng dụng thực tế. Một ứng dụng có socket, mount hoặc device đặc biệt vẫn có thể thất bại dù `criu check` thành công.

### Bước 4: Kiểm tra đường dẫn và chính sách file

```bash
namei -l /var/lib/myapp/checkpoint
stat /var/lib/myapp/checkpoint
findmnt /var/lib/myapp/checkpoint
```

Kiểm tra owner, group, mode, mount options, dung lượng, quota và nhãn bảo mật nếu hệ thống dùng SELinux. Đảm bảo user tạo ảnh và user restore đều truy cập được các file cần thiết. Tránh cấp quyền bypass DAC chỉ để che một lỗi owner hoặc mount.

### Bước 5: Thử từng cơ chế với quyền tối thiểu

Trong một môi trường lab riêng, thực hiện dump và restore với một ứng dụng mẫu đơn giản. Bắt đầu từ quyền cơ bản; nếu thất bại, lấy thông báo lỗi từ CRIU, container runtime, kernel hoặc LSM. Bổ sung đúng quyền hoặc điều chỉnh đúng policy đã xác định là nguyên nhân, rồi chạy lại phép thử.

Không thêm đồng thời nhiều capability và tắt seccomp/SELinux/AppArmor trong một lần thử. Nếu thao tác thành công, bạn sẽ không biết thay đổi nào thực sự cần thiết. Ghi lại quyền tối thiểu và kiểm tra lại từ một container/service được tạo mới để tránh phụ thuộc vào trạng thái thủ công của phiên lab.

### Bước 6: Kiểm tra restore và ứng dụng sau restore

Checkpoint thành công mới xác nhận được giai đoạn dump. Cần restore tiến trình trong môi trường đích, kiểm tra `afterRestore`, xác nhận database/broker/client được kết nối lại và chỉ chuyển readiness sang thành công sau khi resource thiết yếu hoạt động. Kiểm tra log của ứng dụng và hệ điều hành để phân biệt lỗi restore với lỗi khởi tạo lại resource.

## 8. Bảng chẩn đoán nhanh

| Triệu chứng | Lớp cần kiểm tra trước | Hướng điều tra |
|---|---|---|
| `Permission denied` khi ghi ảnh | DAC, owner/mode, mount, SELinux/AppArmor | Kiểm tra đường dẫn, UID/GID, nhãn file và log LSM |
| CRIU không inspect được JVM | ptrace, UID, PID namespace, Yama, seccomp | Xác nhận target process, capability hiệu lực và chính sách ptrace |
| Không tạo hoặc khôi phục namespace | User namespace, capability trong namespace, seccomp | Xác định loại namespace và syscall bị từ chối |
| Lỗi khi phục hồi mount | Mount namespace, filesystem, quyền mount, đường dẫn host | Kiểm tra mount table, bind mount và hỗ trợ của runtime |
| Lỗi network namespace hoặc interface | `CAP_NET_ADMIN`, namespace mạng, network policy | Xác định có thật sự cần phục hồi cấu hình mạng hay nên reconnect socket |
| Không thao tác được cgroup | Cgroup v1/v2, subtree delegation, runtime | Kiểm tra cgroup đích và quyền ghi đúng subtree |
| `criu check` qua nhưng restore ứng dụng lỗi | File descriptor, socket, device, resource native, callback | Kiểm kê tài nguyên ứng dụng và đọc log chi tiết của lần restore |
| Capability đã khai báo nhưng vẫn bị từ chối | Bounding/effective set, namespace, seccomp, LSM | Kiểm tra quyền tiến trình thực tế và lớp policy đang chặn |

Một thông báo lỗi đơn lẻ có thể chưa chỉ ra nguyên nhân cuối cùng. Hãy ghép thời điểm lỗi với log CRIU, log container runtime, audit log của SELinux/AppArmor và log kernel mà quản trị viên có quyền đọc. Không bật debug hoặc audit rộng trên production nếu chưa đánh giá tác động dung lượng và thông tin nhạy cảm trong log.

## 9. Checklist trước khi đưa cấu hình lab vào sử dụng

- [ ] Đã xác định đúng bản phân phối CRaC/JDK và cơ chế checkpoint/restore thực tế.
- [ ] Đã ghi lại kernel, kiến trúc, CRIU, container runtime và cgroup version.
- [ ] JVM chạy bằng UID/GID có quyền tối thiểu cần thiết.
- [ ] Thư mục checkpoint có owner, mode, mount, quota và nhãn bảo mật phù hợp.
- [ ] Capability được cấp theo từng thao tác đã chứng minh là cần thiết.
- [ ] Không cấp `CAP_SYS_ADMIN` hoặc `privileged: true` như một giải pháp mặc định.
- [ ] PID/user/mount/network namespace và UID/GID mapping phù hợp với cơ chế restore.
- [ ] seccomp, SELinux, AppArmor, Yama và capability bounding set đã được kiểm tra.
- [ ] Cgroup được delegate đúng phạm vi nếu cơ chế cần thao tác với cgroup.
- [ ] Resource native, socket, file descriptor và device đã có phương án giữ hoặc tạo lại.
- [ ] Checkpoint được bảo vệ vì có thể chứa dữ liệu và bí mật trong bộ nhớ.
- [ ] Đã thử cả dump lẫn restore bằng đúng user, container profile và systemd unit sẽ dùng khi triển khai.
- [ ] Đã lưu lại cấu hình quyền tối thiểu cùng kết quả kiểm chứng để có thể tái tạo lab.

## 10. Kết luận

Quyền hệ điều hành của CRaC phải được xác định từ cơ chế checkpoint/restore cụ thể. Quyền ghi checkpoint directory, quyền inspect tiến trình, quyền thao tác namespace, mount, network và cgroup là những yêu cầu khác nhau. Linux capabilities giúp chia nhỏ một số quyền đặc biệt, nhưng hiệu lực thực tế còn phụ thuộc user namespace, capability set, seccomp, SELinux, AppArmor, Yama và cấu hình container hoặc systemd.

Hãy bắt đầu từ danh tính ít quyền, kiểm tra khả năng của kernel/CRIU, thử dump và restore trong môi trường lab, rồi chỉ bổ sung quyền đã chứng minh là cần thiết. Cách làm này giúp cấu hình thực hành có thể giải thích, tái lập và duy trì được ranh giới bảo mật của ứng dụng.
