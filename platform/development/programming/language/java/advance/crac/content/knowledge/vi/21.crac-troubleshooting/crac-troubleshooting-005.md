# Đọc log JVM, log checkpoint engine và log CRIU

Khi checkpoint hoặc restore một ứng dụng Java bằng CRaC gặp lỗi, thông tin nguyên nhân thường nằm ở nhiều lớp khác nhau. JVM có thể ghi stack trace từ callback Java; phần tích hợp CRaC của JDK có thể ghi tiến trình điều phối; CRIU ghi chi tiết thao tác đóng băng và khôi phục tiến trình ở mức hệ điều hành; kernel và container runtime có thể ghi lỗi về namespace, cgroup, quyền, mount hoặc tài nguyên hệ thống.

Đọc riêng một file log thường không đủ. Một dòng `Checkpoint failed` trong log ứng dụng chỉ cho biết thao tác thất bại, chưa chỉ ra nguyên nhân. Một dòng `Error` trong log CRIU có thể là nguyên nhân gốc hoặc chỉ là hậu quả sau một lỗi trước đó. Cần ghép các log theo cùng một lần chạy, xác định giai đoạn xảy ra lỗi và lần theo chuỗi sự kiện từ Java xuống hệ điều hành.

Trong bài này, “checkpoint engine” chỉ lớp runtime/tích hợp CRaC của JDK điều phối callback và backend checkpoint. Cách đặt tên, vị trí file và mức độ chi tiết của log phụ thuộc JDK distribution và phiên bản. Không có một tên file log CRaC chung áp dụng cho mọi nhà cung cấp.

## 1. Các lớp log trong một lần checkpoint/restore

Một ứng dụng CRaC có thể tạo ra bằng chứng ở ít nhất năm lớp:

| Lớp | Nguồn log | Nội dung thường thấy |
|---|---|---|
| Ứng dụng Java | Logging framework, stdout/stderr | Trạng thái nghiệp vụ, callback do ứng dụng viết, lỗi dependency |
| JVM | JVM startup, Unified Logging, exception/stack trace | Cấu hình JVM, class loading, GC, thread, container detection, lỗi runtime |
| CRaC integration/checkpoint engine | JDK distribution hoặc runtime wrapper | Bắt đầu checkpoint/restore, điều phối resource, gọi backend, đường dẫn ảnh và lỗi tích hợp |
| CRIU | CRIU dump/restore log | Process tree, task/thread, file descriptor, socket, namespace, mount, memory mapping và kernel feature |
| Kernel/container/orchestrator | kernel journal, audit log, container runtime, systemd, Kubernetes events | Permission denial, seccomp, SELinux/AppArmor, OOM, cgroup, mount và vòng đời container |

Các lớp này có thể ghi vào cùng một nơi. Ví dụ, JDK có thể gửi thông báo CRaC ra stderr, trong khi CRIU ghi file riêng trong thư mục làm việc hoặc thư mục checkpoint. Một service manager có thể thu cả stdout và stderr vào journal. Hãy xác định cấu hình của môi trường đang chạy thay vì giả định log luôn nằm trong một thư mục cố định.

### Mối quan hệ giữa các lớp

~~~mermaid
flowchart TD
    A[Ứng dụng Java] --> B[CRaC Resource callbacks]
    B --> C[JDK CRaC integration / checkpoint engine]
    C --> D[CRIU]
    D --> E[Kernel và filesystem]
    D --> F[Namespace, cgroup, socket]
    A --> G[Database, broker, HTTP client]
    E --> H[Kernel/audit/container logs]
    C --> I[JVM stdout/stderr hoặc runtime log]
    D --> J[CRIU dump/restore log]
~~~

Khi đọc sự cố, bắt đầu từ thời điểm thao tác được yêu cầu, sau đó lần theo các lớp theo chiều sâu. Nếu callback Java ném exception trước khi backend chạy, việc tìm lỗi kernel sẽ không giúp ích. Nếu callback hoàn tất nhưng CRIU thất bại khi khôi phục file descriptor, cần xem CRIU và kernel log.

## 2. Phân biệt log checkpoint và log restore

Checkpoint và restore là hai pha riêng. Một ảnh có thể được tạo thành công nhưng không restore được trên môi trường đích. Ngược lại, restore có thể thành công nhưng ứng dụng thất bại khi làm mới dependency hoặc mở readiness.

### Pha checkpoint

Luồng tổng quát:

1. Ứng dụng đóng admission hoặc dừng nhận request theo chính sách.
2. CRaC gọi `beforeCheckpoint(...)` trên các Resource đã đăng ký.
3. Ứng dụng và thư viện dừng hoặc giải phóng tài nguyên cần xử lý.
4. JDK CRaC integration yêu cầu backend tạo checkpoint.
5. CRIU thu thập trạng thái tiến trình và tài nguyên được hỗ trợ.
6. Runtime hoàn tất thao tác và công bố trạng thái checkpoint.

Các điểm cần tìm trong log:

- Thời điểm bắt đầu yêu cầu checkpoint.
- Resource nào bắt đầu và kết thúc callback.
- Resource nào ném exception hoặc mất quá nhiều thời gian.
- Backend có được gọi hay không.
- CRIU có bắt đầu dump process tree không.
- Lỗi đầu tiên xuất hiện ở file, socket, namespace, cgroup hay memory.
- Runtime có xác nhận checkpoint hoàn tất và đường dẫn ảnh không.

Nếu `beforeCheckpoint` thất bại, backend có thể chưa được gọi hoặc checkpoint bị hủy trước khi tạo ảnh hoàn chỉnh. Không lấy sự tồn tại của thư mục checkpoint làm bằng chứng ảnh hợp lệ.

### Pha restore

Luồng tổng quát:

1. Runtime đọc cấu hình và ảnh checkpoint.
2. Backend kiểm tra điều kiện môi trường và tái lập tiến trình.
3. JVM tiếp tục từ trạng thái đã checkpoint.
4. CRaC gọi `afterRestore(...)` trên các Resource.
5. Ứng dụng làm mới identity, secret, connection và tài nguyên phụ thuộc.
6. Ứng dụng kiểm tra health và mở readiness.

Các điểm cần tìm:

- Đường dẫn ảnh và metadata runtime đã chọn.
- CRIU bắt đầu restore và có tạo lại process/thread hay không.
- Có lỗi về kernel feature, mount, file descriptor, socket hoặc permission không.
- JVM có tiếp tục chạy sau restore không.
- Resource nào thất bại trong `afterRestore`.
- Dependency nào không kết nối lại được.
- Readiness có mở quá sớm hoặc không mở hay không.

### Đừng gộp ba kết quả thành một

| Kết quả | Ý nghĩa |
|---|---|
| Checkpoint thành công | Ảnh được tạo theo xác nhận của runtime |
| Restore thành công | Runtime/JVM khôi phục được tiến trình và tiếp tục thực thi |
| Ứng dụng sẵn sàng | Resource, dependency và health check của ứng dụng đã đạt điều kiện phục vụ |

Một lần restore có thể thành công ở mức CRIU/JVM nhưng ứng dụng vẫn chưa sẵn sàng vì database credential đã rotate hoặc broker chưa rejoin group. Hãy ghi nhận ba kết quả riêng.

## 3. Xác định log nằm ở đâu

Vị trí log phụ thuộc cách ứng dụng được khởi chạy, JDK distribution, cấu hình CRaC, CRIU và nền tảng triển khai.

### JVM stdout và stderr

Thông báo JVM, exception từ callback và một số thông báo CRaC có thể xuất hiện trên stdout/stderr. Nếu chạy qua systemd, container runtime hoặc Kubernetes, các luồng này thường được thu bởi hệ thống log của nền tảng.

Với systemd:

~~~bash
journalctl -u myapp.service --since "2026-11-13 08:00:00" --until "2026-11-13 09:00:00" -o short-iso-precise
~~~

Với Docker:

~~~bash
docker logs --timestamps --since 2026-11-13T08:00:00Z myapp
~~~

Với Kubernetes:

~~~bash
kubectl logs -n production myapp-pod --timestamps
kubectl logs -n production myapp-pod --previous --timestamps
~~~

Lệnh `--previous` hữu ích khi container đã restart và log của lần chạy trước vẫn được runtime lưu. Quyền truy cập log phụ thuộc RBAC và retention của cluster.

### Log của checkpoint engine

Thông báo của JDK CRaC integration có thể được ghi:

- Trực tiếp ra stdout/stderr của JVM.
- Vào file do runtime hoặc launcher cấu hình.
- Vào journal/container log nếu process được quản lý bởi nền tảng.
- Vào thư mục làm việc/checkpoint tùy implementation.

Đọc tài liệu của đúng JDK distribution để biết cách bật verbosity, cấu hình log file và vị trí CRIU output. Không suy luận tên file chỉ từ một bản JDK khác. Nếu runtime có wrapper script, kiểm tra nơi wrapper redirect output và nơi nó lưu metadata của checkpoint.

### CRIU log

CRIU thường ghi log riêng cho thao tác dump và restore. Tên file và thư mục phụ thuộc cách CRIU được gọi, tham số logging, thư mục image/work và cách JDK tích hợp CRIU.

Một số môi trường có thể tạo log với tên liên quan đến dump/restore hoặc PID. Môi trường khác có thể chuyển nội dung ra stderr hoặc đặt trong thư mục do runtime chỉ định. Tìm theo timestamp và PID trong thư mục được cấu hình; không giả định mọi bản CRIU dùng cùng một tên file.

### Kernel và container log

Nếu CRIU báo lỗi quyền hoặc tài nguyên, kiểm tra thêm kernel journal:

~~~bash
journalctl -k --since "2026-11-13 08:00:00" --until "2026-11-13 09:00:00"
dmesg -T
~~~

Tìm các sự kiện OOM kill, seccomp, audit denial, SELinux AVC, AppArmor, cgroup và lỗi filesystem. Trong Kubernetes, kiểm tra pod events, node events và log của container runtime nếu có quyền.

### Tìm log mà không đọc nhầm checkpoint image

Thư mục checkpoint có thể chứa binary image, metadata và log. Không mở hoặc sửa các file image bằng editor. Dùng `find` để liệt kê tên, loại và thời gian; đọc những file được xác định là log/text theo cấu hình runtime.

~~~bash
find /var/lib/myapp/crac -maxdepth 4 -type f -printf '%TY-%Tm-%TdT%TH:%TM:%TS %s %p\n'
file /var/lib/myapp/crac/release-001/*
~~~

Đừng gửi toàn bộ nội dung thư mục checkpoint vào hệ thống log hoặc ticket. Image có thể chứa dữ liệu nhạy cảm trong heap.

## 4. Thu thập thông tin để ghép log

Trước khi phân tích, tạo một record cho từng lần checkpoint/restore. Những trường sau giúp phân biệt các lần chạy:

| Trường | Vì sao cần |
|---|---|
| Checkpoint ID | Nhận diện ảnh đang được tạo hoặc restore |
| Restore attempt ID | Phân biệt nhiều lần restore cùng một ảnh |
| Application build/version | Xác định code và dependency |
| JDK vendor/version | Xác định implementation CRaC |
| CRIU version | Đối chiếu hành vi backend |
| Kernel version | Đối chiếu feature và giới hạn hệ điều hành |
| Container/runtime version | Xác định namespace, cgroup và policy |
| PID và namespace | Ghép log của đúng tiến trình |
| Host/pod/container ID | Xác định môi trường thực tế |
| Checkpoint/restore path | Xác định đúng bộ ảnh |
| Thời điểm bắt đầu/kết thúc | Ghép các log theo cùng cửa sổ |
| User/UID/GID | Điều tra permission và ownership |
| Exit code và signal | Phân biệt process exit, runtime failure và OOM |

Không dùng PID một mình làm correlation ID vì PID có thể được tái sử dụng hoặc khác nhau giữa namespace. Gắn PID với host/container, thời điểm và checkpoint ID.

### Thời gian và clock skew

Ưu tiên timestamp có timezone hoặc UTC trong log. Khi ghép log giữa nhiều node, kiểm tra đồng bộ thời gian. Nếu đồng hồ các node lệch nhau, một sự kiện có thể xuất hiện sai thứ tự khi sắp xếp theo timestamp.

Trong ứng dụng, có thể ghi cả:

- Wall-clock timestamp để đối chiếu giữa máy.
- Monotonic elapsed time để đo khoảng thời gian trong cùng tiến trình.

Không lấy timestamp từ hai máy khác nhau trừ nhau nếu chưa xử lý clock skew.

### Tạo một timeline

Ví dụ timeline đã chuẩn hóa:

| UTC | Thành phần | Sự kiện |
|---|---|---|
| 08:10:00.100 | Application | Nhận yêu cầu checkpoint `cp-42` |
| 08:10:00.120 | CRaC Resource | Bắt đầu `beforeCheckpoint` |
| 08:10:00.180 | CRaC Resource | Tất cả callback hoàn tất |
| 08:10:00.210 | Checkpoint engine | Bắt đầu gọi backend |
| 08:10:00.250 | CRIU | Bắt đầu dump PID trong namespace |
| 08:10:00.490 | CRIU | Ghi nhận lỗi khi xử lý một socket |
| 08:10:00.510 | Checkpoint engine | Backend trả lỗi |
| 08:10:00.520 | Application | Checkpoint thất bại |

Đây là dữ liệu minh họa. Khi điều tra thực tế, ghi nguyên văn timestamp, message và nguồn log; không tự tạo sự kiện còn thiếu.

## 5. Đọc log JVM

Log JVM giúp xác định runtime đang chạy với cấu hình nào, callback Java có thất bại không và JVM đã đi đến giai đoạn nào.

### Xác minh đúng JDK và tùy chọn CRaC

Ghi lại:

~~~bash
java -version
java -XshowSettings:properties -version
~~~

Nếu process còn chạy và có quyền attach:

~~~bash
jcmd <pid> VM.version
jcmd <pid> VM.flags
~~~

Kiểm tra JDK distribution, version, build number, VM flags và các thuộc tính liên quan. Không giả định một JDK tiêu chuẩn có cùng tính năng hoặc cùng option CRaC với bản JDK được đóng gói riêng.

Lỗi startup như `Unrecognized VM option`, `Could not create the Java Virtual Machine`, `NoClassDefFoundError` hoặc `ClassNotFoundException` có thể xảy ra trước khi checkpoint engine được gọi. Khi đó, kiểm tra JDK, classpath/module path, API CRaC và cấu hình launch trước.

### Exception trong Resource callback

Tìm stack trace có method của ứng dụng hoặc thư viện trong:

- `beforeCheckpoint(...)`
- `afterRestore(...)`
- Các method prepare/refresh/reconnect do ứng dụng gọi từ callback.

Ví dụ lỗi minh họa:

~~~text
java.lang.IllegalStateException: database pool is still active
    at com.example.DatabaseResource.beforeCheckpoint(DatabaseResource.java:42)
    at ...
~~~

Điều cần đọc:

1. Exception type và message.
2. Dòng đầu tiên thuộc code ứng dụng.
3. Resource nào ném lỗi.
4. Callback nào đang chạy.
5. Exception có cause hoặc suppressed exception không.
6. Runtime có ghi nhận callback đã hoàn tất hay checkpoint bị hủy.

Đừng chỉ đọc dòng cuối của stack trace. Exception gốc có thể nằm trong `Caused by`, còn exception phía trên chỉ là wrapper.

### JVM Unified Logging

JVM có thể ghi log chi tiết bằng Unified Logging (`-Xlog`). Tag và output có thể khác theo JDK build; kiểm tra tag được hỗ trợ bằng:

~~~bash
java -Xlog:help
~~~

Một ví dụ cấu hình ghi log container detection nếu tag tương ứng có trong build:

~~~bash
-Xlog:os+container=info:file=/var/log/myapp/container.log:time,uptime,level,tags
~~~

Không bật `all=trace` trong production một cách tùy tiện. Log quá chi tiết có thể tạo lượng dữ liệu lớn, tăng overhead và làm lộ thông tin nội bộ. Chọn tag theo giả thuyết cần kiểm tra, bật trong thời gian giới hạn rồi quay về cấu hình bình thường.

### Thread và trạng thái JVM

Nếu JVM vẫn sống sau restore nhưng ứng dụng không tiến triển, lấy thread dump:

~~~bash
jcmd <pid> Thread.print
~~~

Tìm:

- Thread đang chờ network hoặc file I/O.
- Thread bị block trên monitor/lock.
- Executor worker đã dừng nhưng queue vẫn còn.
- Background thread chạy lặp hoặc bị nhân đôi.
- Thread của client không reconnect.

Nếu process đã thoát, `jcmd` không thể attach; dùng thread dump, hs_err log hoặc diagnostic artifact đã được thu trước đó. Đừng giả định có thể lấy thread dump sau khi process chết.

### GC và bộ nhớ

Nếu restore xong nhưng hiệu năng hoặc readiness bất thường, đối chiếu GC log, heap, non-heap và native memory. Dữ liệu GC có thể giúp phát hiện allocation burst, heap pressure hoặc pause kéo dài, nhưng không tự giải thích lỗi CRIU.

Nếu Native Memory Tracking đã được bật từ lúc JVM khởi chạy, có thể xem:

~~~bash
jcmd <pid> VM.native_memory summary
~~~

Không thể bật đầy đủ NMT hồi tố cho một JVM đã chạy nếu startup option yêu cầu chưa được cấu hình. Ghi rõ khi một loại số liệu không có sẵn.

## 6. Đọc log checkpoint engine và CRaC integration

Lớp checkpoint engine là cầu nối giữa API CRaC của Java và backend hệ điều hành. Nó có thể điều phối resource, thiết lập thư mục làm việc, gọi CRIU, thu kết quả và trả lỗi cho JVM.

Tên logger, option verbosity, file log và message phụ thuộc JDK distribution. Hãy dùng tài liệu của đúng nhà cung cấp và ghi lại version trước khi so sánh với ví dụ trên Internet.

### Các loại message cần tìm

- Bắt đầu checkpoint hoặc restore.
- Đường dẫn ảnh và thư mục làm việc.
- Số lượng hoặc tên Resource được gọi nếu runtime có ghi.
- Callback nào hoàn tất hoặc thất bại.
- Backend được gọi và exit status nếu được ghi.
- CRIU log path.
- Thời gian thực hiện từng giai đoạn.
- Lỗi khi đọc metadata hoặc chuẩn bị môi trường.
- Trạng thái cuối cùng: success, failure, cancelled hoặc timeout.

### Phân biệt lỗi điều phối và lỗi backend

**Lỗi điều phối** thường xuất hiện trước khi CRIU chạy: option không hợp lệ, thư mục ảnh không thể tạo, Resource ném exception, runtime không tìm thấy backend hoặc cấu hình không tương thích.

**Lỗi backend** xuất hiện sau khi engine gọi CRIU: CRIU không thể dump/restore process, file descriptor, namespace, mount, memory mapping hoặc kernel state.

Nếu log engine chỉ báo `CRIU failed`, hãy tìm CRIU log được tham chiếu. Nếu không có CRIU log, kiểm tra xem backend có thực sự được gọi hay lỗi xảy ra trước đó.

### Cẩn thận với log bị lặp hoặc thiếu

Một số launcher có thể ghi cùng thông báo vào stderr và file. Một số hệ thống chỉ giữ log của container hiện tại và làm mất log sau restart. Kiểm tra timestamp, PID và nguồn để tránh đếm một sự kiện hai lần.

Nếu runtime không xuất đủ thông tin, bật diagnostic mode theo tài liệu của JDK distribution trong môi trường tái hiện. Không sửa script nội bộ hoặc chèn tham số CRIU tùy tiện nếu nhà cung cấp không hỗ trợ cách đó.

## 7. Đọc log CRIU

CRIU thực hiện phần lớn công việc checkpoint/restore ở mức tiến trình Linux. Log CRIU thường có chi tiết hơn log JVM về tài nguyên kernel.

Một dòng lỗi CRIU có thể có dạng:

~~~text
Error (criu/cr-restore.c:1234): failed to restore task: Operation not permitted
~~~

Tên file và số dòng trong ví dụ chỉ minh họa định dạng. Khi phân tích, giữ nguyên dòng thực tế cùng các dòng trước/sau và version CRIU.

### Severity và thứ tự đọc

CRIU có thể ghi các mức như `Error`, `Warn`, `Info` hoặc debug tùy version/cấu hình. Không phải mọi `Warn` đều làm thao tác thất bại. Một số cảnh báo mô tả feature tùy chọn hoặc trạng thái được xử lý bằng fallback.

Khi có lỗi:

1. Tìm lần xuất hiện đầu tiên của `Error` trong đúng lần dump/restore.
2. Đọc thêm các dòng ngay trước đó để thấy thao tác đang được thực hiện.
3. Tìm cùng PID, FD, mount ID, namespace hoặc resource identifier ở các dòng liên quan.
4. Kiểm tra các lỗi tiếp theo có phải hậu quả của lỗi đầu tiên không.
5. Đối chiếu kernel log và cấu hình môi trường.

Không mặc định dòng `Error` cuối cùng là nguyên nhân gốc. Sau khi một bước thất bại, các bước phụ thuộc có thể phát sinh thêm nhiều lỗi.

### Nhóm lỗi thường gặp

| Nhóm | Dấu hiệu | Hướng điều tra |
|---|---|---|
| Kernel feature | Feature hoặc syscall không được hỗ trợ | Kernel version/configuration và CRIU compatibility |
| Permission/capability | `Operation not permitted`, `Permission denied` | UID/GID, capability, user namespace, seccomp và LSM |
| Cgroup | Không đọc/ghi hoặc tái lập cgroup | Cgroup v1/v2, mount và quyền của runtime |
| Namespace | Không thể tạo hoặc tham gia namespace | User/PID/network/mount namespace và policy container |
| File descriptor | File hoặc FD không thể khôi phục | File path, owner, mount, socket và trạng thái file |
| Network/socket | TCP/Unix socket không được hỗ trợ hoặc endpoint không còn | Loại socket, peer state, port, network namespace |
| Mount/filesystem | Mount point hoặc filesystem không phù hợp | Mount table, filesystem type, propagation và quyền |
| Memory mapping | Mapping, shared memory hoặc file-backed mapping lỗi | File backing, address mapping, kernel và CRIU feature |
| Process/thread | Task/thread không thể khôi phục | Thread state, ptrace, signal và process tree |
| Resource limit | Thiếu memory, PID, file descriptor hoặc quota | ulimit, cgroup limits, host capacity |

### Permission và capability

`Operation not permitted` không nhất thiết có nghĩa file permission sai. Nó có thể đến từ capability, user namespace, seccomp, SELinux/AppArmor hoặc syscall bị kernel từ chối.

Đối chiếu:

~~~bash
id
grep -E '^(Uid|Gid|Groups|Cap(Inh|Prm|Eff|Bnd|Amb)|NoNewPrivs|Seccomp):' /proc/<pid>/status
~~~

Nếu process đã thoát, thông tin `/proc/<pid>` có thể không còn. Thu thập thông tin này trước checkpoint hoặc từ container/runtime config khi tái hiện.

### File descriptor và mount

Nếu lỗi liên quan FD, socket hoặc mount, xác định tài nguyên được mở ở checkpoint và trạng thái tại restore. Một FD có thể trỏ đến file đã bị xóa, mount đã đổi hoặc socket không thể tái lập trong môi trường mới.

Không khắc phục bằng cách tạo file rỗng cùng tên mà chưa hiểu semantics. Runtime có thể cần inode, mount hoặc trạng thái file cụ thể.

### Socket và kết nối TCP

Không phải mọi socket đều có thể checkpoint/restore trong mọi cấu hình. Kết nối TCP có thể phụ thuộc kernel feature, network namespace, trạng thái peer và khả năng phối hợp giữa hai đầu. Với client tới database/broker, ứng dụng thường cần đóng và tạo lại connection theo lifecycle thư viện thay vì phụ thuộc vào việc giữ socket xuyên qua restore.

Nếu CRIU log đề cập established TCP connection, kiểm tra loại socket, cấu hình hỗ trợ TCP, peer có còn tồn tại không và JDK/CRIU có được cấu hình theo hướng dẫn hay không. Đừng bật một tùy chọn cho phép giữ socket chỉ vì muốn bỏ qua lỗi; phải đánh giá tính đúng đắn của peer và ứng dụng sau restore.

### Kernel feature và version mismatch

Một ảnh tạo trên kernel hoặc môi trường khác có thể phụ thuộc feature mà host đích không hỗ trợ. Ghi:

~~~bash
uname -a
criu --version
criu check
~~~

`criu check` là kiểm tra khả năng của môi trường theo CRIU version hiện tại; nó không chứng minh mọi tài nguyên cụ thể của ứng dụng có thể checkpoint/restore. Kết quả còn phụ thuộc quyền, cấu hình và feature mà bài kiểm tra kích hoạt.

## 8. Log kernel, audit và container runtime

CRIU có thể báo một syscall thất bại nhưng nguyên nhân chính sách nằm trong kernel hoặc security subsystem. Khi đó cần ghép log ở lớp host.

### OOM và memory pressure

Nếu process biến mất hoặc container restart, kiểm tra OOM:

~~~bash
journalctl -k --since "2026-11-13 08:00:00" | grep -i -E 'oom|out of memory|killed process'
~~~

Trong container, kiểm tra memory limit và cgroup event. OOM kill có thể làm JVM biến mất mà không có Java exception hoặc stack trace. Phân biệt OOM của host với OOM trong cgroup/container.

### SELinux và AppArmor

Permission bits có thể đúng nhưng LSM vẫn từ chối thao tác. Tìm audit denial và security context tương ứng với process/path. Không tắt policy trên toàn host để thử nghiệm. Nếu cần thay đổi, tạo rule giới hạn và ghi lại policy/version dùng trong test.

### Seccomp và capability

Container profile có thể chặn syscall cần thiết hoặc loại bỏ capability CRIU yêu cầu. So sánh cấu hình security của container nguồn và đích. Một pod có thể chạy Java bình thường nhưng không có quyền thực hiện thao tác checkpoint/restore.

### Cgroup và namespace

Ghi rõ cgroup version, mount point, container runtime, PID namespace, user namespace và network namespace. Khi restore sang môi trường khác, các namespace hoặc cgroup có thể không giống môi trường tạo ảnh.

### Pod và container events

Trong Kubernetes, kiểm tra:

~~~bash
kubectl describe pod -n production myapp-pod
kubectl get events -n production --sort-by=.lastTimestamp
~~~

Tìm lý do restart, OOMKilled, probe failure, mount error, image pull hoặc scheduling. Pod event có thể giải thích vì sao process bị thay thế trong khi log JVM chỉ cho thấy nó đột ngột kết thúc.

## 9. Đọc lỗi theo triệu chứng

Thay vì tìm kiếm một message đơn lẻ, bắt đầu bằng triệu chứng và kiểm tra các lớp có liên quan.

### Checkpoint thất bại trước khi có CRIU log

Khả năng:

- JVM option CRaC không được nhận diện.
- API Resource không có trên runtime.
- `beforeCheckpoint` ném exception.
- Ứng dụng chưa drain request hoặc chưa dừng tài nguyên.
- Thư mục checkpoint không thể tạo/ghi.
- Engine không tìm thấy hoặc không khởi chạy backend.

Hướng xử lý:

1. Đọc JVM startup log và exception đầy đủ.
2. Xác nhận JDK distribution/version và flags.
3. Tìm log callback theo tên Resource.
4. Kiểm tra owner/mode và path của checkpoint directory.
5. Xác định engine đã gọi CRIU hay chưa.

### CRIU dump thất bại

Khả năng:

- Tài nguyên tiến trình không được hỗ trợ.
- Thiếu capability hoặc bị seccomp/LSM chặn.
- File descriptor, socket hoặc mount không thể xử lý.
- Kernel thiếu feature.
- Thiếu tài nguyên hoặc giới hạn PID/FD.

Hướng xử lý:

1. Tìm CRIU `Error` đầu tiên và các dòng trước đó.
2. Ghép PID, FD, mount và namespace.
3. Đọc kernel/audit log cùng timestamp.
4. So sánh kernel, CRIU và container policy.
5. Tái hiện trên môi trường thử nghiệm với cùng cấu hình.

### Restore thất bại trước khi JVM tiếp tục

Khả năng:

- Ảnh không đầy đủ hoặc checksum sai.
- Runtime/JDK/CRIU không tương thích.
- Mount, path, namespace hoặc kernel khác môi trường nguồn.
- Resource hệ điều hành không thể tái lập.

Hướng xử lý:

1. Xác minh đúng checkpoint ID và toàn bộ cây ảnh.
2. Kiểm tra checksum/manifest nếu có.
3. Đọc CRIU restore log và engine log.
4. So sánh môi trường tạo ảnh với môi trường đích.
5. Không sửa trực tiếp binary image để thử vượt lỗi.

### Restore thành công nhưng callback thất bại

Khả năng:

- `afterRestore` không lấy được workload identity hoặc secret.
- Database/broker/HTTP client không thể reconnect.
- Client cũ vẫn giữ socket hoặc credential stale.
- Thread/executor chưa được tạo lại.
- Callback phụ thuộc thứ tự Resource không được bảo đảm.

Hướng xử lý:

1. Xác nhận JVM đã tiếp tục chạy.
2. Tìm exception đầu tiên trong `afterRestore`.
3. Xác định dependency nào chưa sẵn sàng.
4. Giữ readiness false và kiểm tra retry/timeout.
5. Xác minh client được tạo mới và health check thực hiện thao tác thật.

### Ứng dụng ready nhưng request lỗi

Khả năng:

- Readiness mở quá sớm.
- Một dependency tùy chọn chưa phục hồi.
- DNS, certificate, credential hoặc endpoint đã đổi.
- Background thread hoặc scheduler chưa hoạt động.
- Ứng dụng dùng cache hoặc runtime identity cũ.

Hướng xử lý:

1. Ghép request ID/trace ID với incarnation ID.
2. Đọc application log và dependency metrics.
3. Kiểm tra thread dump và connection pool.
4. Kiểm tra secret version, endpoint và service discovery.
5. Sửa readiness để phản ánh dependency thực sự cần cho traffic.

## 10. Quy trình điều tra từng bước

Một quy trình nhất quán giúp giảm thời gian đọc log và tránh sửa nhầm lớp.

### Bước 1 — Chốt lần chạy và triệu chứng

Ghi checkpoint ID, restore attempt ID, PID/host/container, thời điểm, exit code, signal và triệu chứng quan sát được. Xác định lỗi xảy ra trong checkpoint, restore hay sau khi ứng dụng đã ready.

### Bước 2 — Thu thập log nguyên bản

Lưu bản sao:

- JVM stdout/stderr.
- Application log.
- CRaC integration/checkpoint engine log.
- CRIU dump/restore log.
- Kernel/audit log.
- Container runtime/orchestrator events.

Giữ nguyên timestamp, timezone, PID và thứ tự dòng. Không chỉ copy một vài dòng `Error` vì các dòng trước đó thường giải thích thao tác đang thực hiện.

### Bước 3 — Xây dựng timeline

Sắp xếp sự kiện theo timestamp đã chuẩn hóa. Đánh dấu callback bắt đầu/kết thúc, thời điểm backend được gọi, dòng lỗi CRIU đầu tiên, thời điểm process tiếp tục và thời điểm readiness mở.

### Bước 4 — Xác định lớp phát sinh lỗi đầu tiên

Hỏi:

- Lỗi xuất hiện trước hay sau khi engine gọi CRIU?
- CRIU có bắt đầu dump/restore không?
- Kernel có denial/OOM không?
- JVM có chạy callback tương ứng không?
- Dependency bên ngoài có trả lỗi không?

Lớp phát sinh lỗi đầu tiên thường là nơi nên điều tra trước.

### Bước 5 — Kiểm tra cấu hình và môi trường

Ghi lại JDK/CRaC build, CRIU version, kernel, container runtime, UID/GID, capability, seccomp/LSM, cgroup, mount và checkpoint path. So sánh với môi trường đã tạo ảnh.

### Bước 6 — Tái hiện có kiểm soát

Thử cùng image, cùng JDK/CRIU và cấu hình gần giống môi trường lỗi. Chỉ thay đổi một yếu tố mỗi lần. Nếu tăng verbosity, làm trong thời gian giới hạn và bảo vệ log.

### Bước 7 — Ghi kết luận dựa trên bằng chứng

Báo cáo:

- Triệu chứng.
- Lần chạy và image bị ảnh hưởng.
- Dòng lỗi đầu tiên cùng nguồn.
- Nguyên nhân đã xác nhận hoặc giả thuyết còn mở.
- Bằng chứng hỗ trợ.
- Điều kiện tái hiện.
- Thay đổi đã thử và kết quả.
- Giới hạn/điểm chưa xác định.

Không kết luận `CRIU lỗi` chỉ vì log cuối cùng có dòng CRIU failed; hãy nêu resource hoặc syscall cụ thể nếu bằng chứng cho phép.

## 11. Các lệnh hỗ trợ thu thập log

Những lệnh dưới đây là ví dụ cho Linux. Điều chỉnh service, namespace, path và thời gian theo môi trường. Chạy bằng user có quyền đọc log cần thiết.

### Thông tin phiên bản

~~~bash
java -version
criu --version
uname -a
~~~

### systemd journal

~~~bash
journalctl -u myapp.service --since "1 hour ago" -o short-iso-precise
journalctl -k --since "1 hour ago" -o short-iso-precise
~~~

### Lọc lỗi trong log đã thu thập

~~~bash
grep -n -E 'Error|ERROR|Exception|Caused by|Warn|WARNING|CRIU|CRaC|checkpoint|restore' app.log
~~~

Nếu có `rg`, có thể dùng:

~~~bash
rg -n -i 'error|exception|caused by|warn|criu|crac|checkpoint|restore' logs/
~~~

Đây là bước tìm điểm bắt đầu; sau khi tìm thấy dòng phù hợp, đọc cả vùng xung quanh để giữ ngữ cảnh.

### CRIU preflight

~~~bash
criu check
~~~

Lệnh này giúp kiểm tra một số khả năng của môi trường CRIU hiện tại. Nó không thay thế một lần checkpoint/restore ứng dụng thật và không kiểm tra đầy đủ từng file descriptor, socket hoặc native resource mà ứng dụng đang dùng.

### Process và cgroup

~~~bash
id
cat /proc/<pid>/status
cat /proc/<pid>/cgroup
~~~

Các file `/proc/<pid>` chỉ tồn tại khi process còn sống và có thể truy cập. Nếu PID đã kết thúc, dùng thông tin được thu trước đó hoặc cấu hình container/orchestrator.

### Xem log CRIU chi tiết hơn

CRIU CLI có các tùy chọn logging tùy phiên bản, thường bao gồm mức verbosity và file log. Xác minh cú pháp trên đúng binary:

~~~bash
criu --help
criu dump --help
criu restore --help
~~~

Với CRIU được JDK gọi nội bộ, chỉ cấu hình verbosity hoặc log path theo tài liệu của JDK distribution. Không chạy một lệnh `criu dump` thủ công lên JVM đang được JDK quản lý để thay thế quy trình CRaC; thao tác đó có thể bỏ qua callback và phá vỡ trạng thái ứng dụng.

## 12. Ví dụ phân tích một lỗi minh họa

Giả sử ứng dụng báo checkpoint thất bại. Các log đã thu thập có dạng:

~~~text
08:10:00.100 app  INFO  checkpoint requested id=cp-42
08:10:00.120 app  INFO  beforeCheckpoint resource=DatabaseResource
08:10:00.180 app  INFO  beforeCheckpoint completed resource=DatabaseResource
08:10:00.210 engine INFO backend checkpoint started id=cp-42
08:10:00.250 criu  INFO  dumping process tree
08:10:00.490 criu  Error (criu/files.c:123): cannot open file descriptor: Permission denied
08:10:00.510 engine ERROR backend checkpoint failed
08:10:00.520 app  ERROR checkpoint failed id=cp-42
~~~

Cách đọc:

1. Callback ứng dụng đã hoàn tất, nên lỗi không xuất phát từ `DatabaseResource.beforeCheckpoint`.
2. Engine đã gọi backend và CRIU đã bắt đầu dump.
3. Lỗi đầu tiên có trong CRIU log liên quan file descriptor và `Permission denied`.
4. Cần xác định FD nào bị từ chối, file/path/mount tương ứng và user/capability của tiến trình.
5. Ghép kernel/audit log để xem có SELinux, AppArmor, seccomp hoặc permission denial hay không.

Chưa thể kết luận chỉ từ dòng trên rằng cần chmod file. `Permission denied` có thể đến từ quyền trên file, thư mục cha, namespace hoặc security policy. Cần tìm FD và bằng chứng host trước khi thay đổi.

### Ví dụ lỗi ở restore callback

~~~text
09:05:10.100 engine INFO restore completed
09:05:10.130 app  INFO  afterRestore resource=SecretResource
09:05:10.210 app  ERROR java.net.SocketTimeoutException: secret manager timed out
09:05:10.220 app  WARN  readiness remains closed
~~~

Trong trường hợp này, log cho thấy backend đã hoàn tất restore và lỗi xuất hiện khi ứng dụng lấy secret sau restore. Hướng điều tra là workload identity, network, DNS, secret manager và timeout; không bắt đầu bằng việc thay kernel hoặc CRIU nếu chưa có bằng chứng cho thấy backend thất bại.

## 13. Bật verbosity có kiểm soát

Log chi tiết có ích khi cần biết CRIU đang xử lý resource nào, nhưng có thể:

- Tạo lượng log rất lớn.
- Tăng thời gian thao tác hoặc ảnh hưởng hiệu năng.
- Ghi thông tin path, process, user, network hoặc dữ liệu nhạy cảm.
- Làm đầy disk nếu không có rotation.

Quy trình phù hợp:

1. Tái hiện trong môi trường test hoặc staging trước.
2. Chọn đúng thành phần cần tăng verbosity.
3. Xác minh option theo đúng JDK/CRIU version.
4. Giới hạn thời gian và số lần chạy.
5. Đặt log path có quyền truy cập chặt chẽ và đủ dung lượng.
6. Thu thập stdout/stderr, engine log và CRIU log cùng một lần chạy.
7. Tắt verbosity sau khi có đủ bằng chứng.

Không bật trace toàn bộ JVM và CRIU trong thời gian dài ở production. Nếu cần thu thập production, phối hợp cửa sổ bảo trì hoặc cơ chế diagnostic đã được vận hành phê duyệt.

## 14. Bảo vệ log và checkpoint khi điều tra

Log có thể chứa thông tin hạ tầng hoặc dữ liệu nhạy cảm. Checkpoint image còn có thể chứa object graph và secret trong heap.

Khi chia sẻ log:

- Redact password, token, authorization header, cookie và private key.
- Redact URL có credential hoặc query parameter bí mật.
- Giữ lại timestamp, PID, exception type, source file và message kỹ thuật cần thiết.
- Không xóa dòng lỗi gốc hoặc các dòng context giúp hiểu thứ tự.
- Hạn chế quyền truy cập và đặt retention cho bản log thô.

Khi chia sẻ checkpoint:

- Không gửi image qua ticket/chat thông thường.
- Dùng storage mã hóa và quyền truy cập giới hạn.
- Chỉ cấp ảnh cho người cần điều tra.
- Không chỉnh sửa binary image để che secret.
- Nếu ảnh chứa credential bị lộ, rotate/revoke credential và xử lý mọi bản sao artifact.

Tạo bản log đã redact để chia sẻ và giữ bản gốc trong vùng lưu trữ được bảo vệ. Ghi lại ai đã truy cập artifact và thời điểm truy cập theo chính sách vận hành.

## 15. Những lỗi đọc log thường gặp

| Cách đọc sai | Vì sao sai | Cách làm phù hợp |
|---|---|---|
| Chỉ xem log ứng dụng | Ứng dụng thường chỉ nhận thông báo backend thất bại | Ghép JVM, engine, CRIU và kernel log |
| Chỉ xem dòng `Error` cuối | Có thể là hậu quả của lỗi trước | Tìm lỗi đầu tiên và đọc context |
| Cho rằng `Warn` luôn vô hại | Một cảnh báo có thể chỉ ra fallback hoặc giới hạn ảnh hưởng | Đối chiếu với kết quả và tài liệu phiên bản |
| Cho rằng mọi `Error` đều là nguyên nhân gốc | Một số error là lỗi dây chuyền | Lần theo thao tác đầu tiên thất bại |
| Tìm CRIU log theo một tên cố định | Tên/path phụ thuộc runtime và cấu hình | Kiểm tra log path được engine chỉ ra |
| Gộp checkpoint và restore | Hai pha có tài nguyên và lỗi khác nhau | Gắn action và checkpoint ID cho từng log |
| Chỉ ghép bằng PID | PID có thể tái sử dụng hoặc khác namespace | Dùng PID + host/container + timestamp + image ID |
| Chỉ nhìn CRIU version | Kernel, capability và namespace cũng quyết định | Ghi toàn bộ môi trường |
| Chạy CRIU thủ công lên JVM để tái hiện | Bỏ qua lifecycle CRaC và có thể làm hỏng process | Dùng quy trình JDK CRaC được hỗ trợ |
| Bật log trace liên tục | Tạo overhead, đầy disk và có thể lộ dữ liệu | Tăng verbosity có thời hạn và giới hạn phạm vi |
| Chia sẻ nguyên log/checkpoint công khai | Có thể lộ secret và hạ tầng | Redact log; bảo vệ artifact |

## 16. Checklist điều tra sự cố

### Nhận diện lần chạy

- [ ] Có checkpoint ID và restore attempt ID.
- [ ] Có timestamp, timezone, PID, host/container và application version.
- [ ] Đã ghi JDK distribution/version, CRIU version và kernel version.
- [ ] Đã xác định lỗi ở checkpoint, restore hay sau khi ứng dụng ready.

### Thu thập log

- [ ] Có application stdout/stderr và stack trace đầy đủ.
- [ ] Có log JVM cần thiết.
- [ ] Có log CRaC integration/checkpoint engine.
- [ ] Có CRIU dump/restore log tương ứng.
- [ ] Có kernel/audit/container/orchestrator events.
- [ ] Log được giữ nguyên timestamp và thứ tự, có context trước/sau lỗi.

### Phân tích

- [ ] Đã xác định callback Java có hoàn tất không.
- [ ] Đã xác định backend CRIU có được gọi không.
- [ ] Đã tìm dòng lỗi CRIU đầu tiên và resource liên quan.
- [ ] Đã kiểm tra permission, namespace, cgroup, mount, socket và kernel feature khi phù hợp.
- [ ] Đã kiểm tra dependency, secret, connection và readiness nếu restore đã thành công.
- [ ] Đã ghép timeline và kiểm tra clock skew.

### Kết luận và chia sẻ

- [ ] Nguyên nhân được phân biệt với giả thuyết chưa xác nhận.
- [ ] Có bằng chứng log và môi trường hỗ trợ kết luận.
- [ ] Có điều kiện tái hiện và kết quả thử nghiệm.
- [ ] Log chia sẻ đã được redact secret.
- [ ] Checkpoint image được bảo vệ và không gửi qua kênh không an toàn.
- [ ] Verbosity bổ sung đã được tắt sau khi điều tra.

Đọc log CRaC hiệu quả đòi hỏi nhìn xuyên suốt từ callback Java đến checkpoint engine, CRIU và kernel. Trước tiên hãy xác định đúng lần chạy và giai đoạn thất bại; sau đó ghép log bằng checkpoint ID, PID, host/container và timestamp; cuối cùng tìm thao tác đầu tiên thất bại rồi đối chiếu với môi trường. Cách đọc theo lớp giúp phân biệt lỗi ứng dụng, lỗi điều phối, lỗi CRIU và lỗi hệ điều hành, đồng thời tránh thay đổi cấu hình sai chỗ hoặc bỏ sót dữ liệu cần thiết để tái hiện sự cố.
