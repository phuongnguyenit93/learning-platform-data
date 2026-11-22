# 20.2 Thu `hs_err_pid` log với `-XX:ErrorFile` và giữ dữ liệu ngay sau sự cố

> **Bối cảnh:** Java Advance – runtime diagnostics, phần **20. Crash và phân tích sau lỗi**. Khi **HotSpot JVM** gặp *fatal error* (chẳng hạn lỗi native nghiêm trọng, lỗi nội bộ VM), nó thường cố gắng ghi một báo cáo văn bản có tên `hs_err_pid<pid>.log`. Dùng `-XX:ErrorFile` để ấn định nơi nhận file, đồng thời chuẩn bị cách bảo quản chứng cứ **ngay sau crash** trước khi tiến trình khởi động lại, thư mục tạm bị xóa hoặc log bị ghi đè.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt **HotSpot fatal error log** với Java exception, heap dump, core dump, GC log và JFR recording.
2. Cấu hình `-XX:ErrorFile=/path/hs_err_pid%p.log`, giải thích `%p`, `%%`, đường mặc định và fallback.
3. Kiểm tra đúng **quyền ghi, storage, quota, vị trí mount và chính sách restart** trước khi có sự cố.
4. Thu thập nguyên trạng `hs_err_pid` cùng stderr, GC/JFR, core và dữ liệu OS/container **nếu có**, sau đó bảo toàn metadata/checksum.
5. Đọc header, `Problematic frame`, current thread, VM arguments và native libraries để bắt đầu điều tra, **không vội suy ra nguyên nhân chỉ từ một dòng**.
6. Chạy lab **Java 17+ không gây crash** để kiểm tra thư mục và startup argument.

**Nguyên tắc xuyên suốt:** `-XX:ErrorFile` chỉ định **vị trí và tên báo cáo lỗi nếu VM có khả năng ghi**. Nó không ngăn sự cố, không bảo đảm file được tạo trong mọi trường hợp, không tự động xuất heap dump và không biến mọi loại kết thúc tiến trình thành JVM fatal error.

## 2. Khi nào có `hs_err_pid`, khi nào không?

| Hiện tượng | Khả năng có `hs_err_pid` | Bằng chứng nên tìm |
| --- | --- | --- |
| HotSpot fatal VM error, native `SIGSEGV` trên Linux hoặc `EXCEPTION_ACCESS_VIOLATION` trên Windows | **Thường có nếu error handler còn thực thi và ghi được** | `hs_err_pid...log`, console fatal header, core/minidump nếu được tạo |
| VM internal error/assertion/guarantee failure | Có thể | Fatal header, build JVM, current thread, internal-error information |
| Java `NullPointerException` hoặc exception không được bắt | Không chỉ vì exception Java | Application logs, Java stack trace, exit status |
| `System.exit`, shutdown bình thường, SIGTERM được xử lý | Không chỉ vì shutdown | Shutdown/service logs, supervisor reason |
| `java.lang.OutOfMemoryError: Java heap space` hoặc `Metaspace` | **Không mặc định** tạo fatal log chỉ vì Java OOME | Exception logs, GC metrics, heap dump nếu đã bật cờ |
| Kernel/cgroup **OOMKilled**, `kill -9`/`SIGKILL` | **Không kỳ vọng**: OS không cho JVM chạy error handler | Container exit reason, kernel/cgroup events, node metrics |
| Mất điện, filesystem hỏng, crash rất sớm hoặc memory corruption nặng | Có thể không có hoặc **chỉ một phần** | Console, host logs, backup, partial file, core nếu có |

Vì vậy **không có file `hs_err` không chứng minh JVM không gặp lỗi nghiêm trọng**. Và ngược lại, có file `hs_err` không có nghĩa root cause nằm trong HotSpot; lỗi có thể do JNI, agent, thư viện native, driver, hardware hoặc memory corruption xảy ra trước thời điểm crash.

**Phân biệt OOM cho đúng:** `-XX:+HeapDumpOnOutOfMemoryError` và `-XX:HeapDumpPath` áp dụng cho cơ chế **heap dump khi có Java OOME**; khác hoàn toàn mục tiêu `-XX:ErrorFile`. Nếu container bị kernel OOM killer chấm dứt, thường không có cơ hội tạo Java OOME, `hs_err` hoặc heap dump. Không nên cố làm JVM chết để “kiểm tra” trên môi trường production.

## 3. `-XX:ErrorFile` hoạt động thế nào?

### 3.1. Cú pháp đặt đường dẫn

Ví dụ Linux:

```bash
java '-XX:ErrorFile=/var/lib/myapp/crash/hs_err_pid%p.log' -jar app.jar
```

Các điểm cần nhớ:

- Đây là **HotSpot `-XX` option**, đặt **trước** `-jar app.jar` hoặc tên main class. Đặt sau `-jar` thường biến nó thành **tham số của ứng dụng**, không cấu hình JVM.
- Dùng đường dẫn **tuyệt đối** để tránh phụ thuộc vào current working directory.
- `%p` được thay bằng **PID của tiến trình JVM**, ví dụ PID `28471` → `hs_err_pid28471.log`.
- `%%` biểu diễn một dấu `%` trong filename. Đừng nhầm với các placeholder riêng của `-Xlog`, nơi có thể có quy ước khác.
- Thư mục **phải có trước khi crash** và tài khoản thực chạy JVM phải có quyền ghi. JVM không thể tự cứu một đường dẫn nằm trên filesystem đã mất hoặc chỉ đọc.
- Nếu chọn filename cố định và file đã tồn tại, có thể xảy ra **ghi đè**. Dùng `%p`, nhưng PID có thể **được tái sử dụng** sau restart hoặc trùng trong các PID namespaces khác nhau. Hãy archive thêm **UTC timestamp, host/container/pod UID và release**.

Ví dụ Windows PowerShell với directory tồn tại:

```powershell
java '-XX:ErrorFile=C:/java-diag/crash/hs_err_pid%p.log' -jar app.jar
```

Khi path chứa khoảng trắng, quote để JVM nhận toàn bộ `-XX:ErrorFile=...` như **một đối số**. Không assume shell Bash, CMD và PowerShell xử lý quoting giống nhau. `app.jar` ở đây là một ví dụ tên ứng dụng, cần thay bằng deployment thật.

### 3.2. Vị trí mặc định và fallback

Khi không có `-XX:ErrorFile`, HotSpot thường thử tạo `hs_err_pid<pid>.log` trong **current working directory** của process. CWD **không nhất thiết** là thư mục chứa `.jar`; với systemd, container hoặc IDE, nó do launcher/entrypoint/WorkingDirectory quyết định.

Theo tài liệu Oracle, nếu file không được tạo tại đường định trước/CWD do quyền, dung lượng hoặc lỗi khác, VM có thể thử **OS temporary directory**, ví dụ `/tmp` trên Linux, `%TMP%` hoặc `%TEMP%` trên Windows. Đây là **cơ chế dự phòng**, không phải chiến lược lưu trữ đáng tin: `/tmp` có thể đầy, bị dọn, nằm trong container filesystem tạm, hoặc VM không còn đủ khả năng chạy fallback.

Tìm ở những vị trí có căn cứ:

```bash
find /var/lib/myapp/crash -maxdepth 1 -type f -name 'hs_err_pid*.log' -ls
find /tmp -maxdepth 1 -type f -name 'hs_err_pid*.log' -ls
```

Nếu không đặt ErrorFile, còn phải kiểm tra **CWD lúc JVM chạy** (lấy từ service unit, deployment/entrypoint hoặc `/proc/<PID>/cwd` **khi PID còn sống**). Sau crash, `/proc/<PID>` thường không còn nên không thể suy CWD từ shell của người đang điều tra. Không tùy tiện quét toàn bộ host hoặc truy cập dữ liệu ngoài quyền.

### 3.3. Không có file khi chạy bình thường là đúng

Lệnh:

```bash
java '-XX:ErrorFile=/var/lib/myapp/crash/hs_err_pid%p.log' -version
```

chỉ kiểm tra **JVM parse được option**. Nó **không sinh** `hs_err` vì không có fatal error; cũng không chứng minh thực tế filesystem/permissions sẽ cho phép tạo file tại thời điểm crash. Cần có một **write preflight** chạy bằng chính account, mount và security context của service.

Không chủ động kích hoạt `Unsafe`, JNI segmentation fault hoặc flags làm VM crash trên production chỉ để thử cơ chế này. Với yêu cầu kiểm tra end-to-end việc ghi file khi fatal error, làm trong môi trường kiểm thử cô lập, giới hạn storage, có phê duyệt và cleanup được kiểm soát.

## 4. Chuẩn bị từ trước: thư mục, quyền và storage

### 4.1. Cấu trúc đề xuất

```text
/var/lib/myapp/
  crash/       # hs_err fatal logs, lưu bền
  jfr/         # recordings/chunks, chính sách riêng
  logs/        # GC/application logs, rotation riêng
```

Ví dụ Linux, chạy dưới quyền quản trị khi provisioning:

```bash
sudo install -d -m 0700 -o myapp -g myapp /var/lib/myapp/crash
sudo install -d -m 0700 -o myapp -g myapp /var/lib/myapp/logs
```

`myapp` chỉ là ví dụ user/group. Đảm bảo chính tài khoản service ghi được. Permission `0700` minh họa nguyên tắc quyền tối thiểu; doanh nghiệp có thể dùng group cho nhóm SRE/incident response, cùng ACL rõ ràng.

Khởi động ứng dụng:

```bash
java \
  '-XX:ErrorFile=/var/lib/myapp/crash/hs_err_pid%p.log' \
  '-Xlog:gc*,safepoint:file=/var/lib/myapp/logs/gc-%p.log:time,uptime,level,tags:filecount=5,filesize=20m' \
  -jar app.jar
```

`-Xlog` ở đây bổ sung GC/safepoint evidence trước crash. Nó **không thay thế fatal log**; output `gc-%p.log` có retention riêng, `filecount=5` có thể loại file cũ. `%p` của unified logging không được dùng để suy đoán rằng mọi placeholder tương tự hoạt động trong `-XX:ErrorFile`.

**Preflight cần kiểm tra:**

- Directory tồn tại và nằm trong namespace/container thật nơi JVM chạy.
- User chạy JVM có thể **tạo, ghi, đóng file** tại directory.
- Filesystem/mount ghi được: không `read-only`, không chặn bởi SELinux/AppArmor/systemd sandbox, quota/inodes/disk capacity còn đủ.
- Crash volume có phương án **giữ nguyên qua restart/reschedule** theo yêu cầu.
- Có phân biệt file theo **instance + PID + timestamp**; tránh trùng tên trên shared volume.
- Có cảnh báo dung lượng và retention **sau khi bảo quản**, không cron xóa ngay sau crash.
- Crash artifacts nhạy cảm không nằm trong public web root hoặc thư mục dùng chung không giới hạn quyền.

`chmod` hoặc `Files.isWritable` chỉ phản ánh một phần điều kiện. Một service dưới systemd `ProtectSystem`, container `readOnlyRootFilesystem` hoặc security policy có thể không ghi được dù chủ sở hữu host nhìn thấy quyền `rw`. Nên thử bằng **cùng execution context**.

### 4.2. Kubernetes/Docker: mount đúng quan trọng hơn tên file

Trong container, `/tmp` và writable layer có thể mất khi container/pod bị thay thế. Kubernetes `emptyDir` **thường tồn tại qua lần restart container khi Pod còn sống trên node**, nhưng bị xóa khi Pod bị dọn/evict/recreate. Vì vậy `emptyDir` chưa phải là kho bằng chứng bền vững lâu dài.

Muốn giữ `hs_err` qua vòng đời Pod, cần persistent volume, host collector hoặc cơ chế snapshot/sidecar thích hợp. Ví dụ **chỉ phần mount, không phải manifest triển khai đầy đủ**:

```yaml
containers:
  - name: java-service
    volumeMounts:
      - name: crash-artifacts
        mountPath: /var/lib/myapp/crash
volumes:
  - name: crash-artifacts
    persistentVolumeClaim:
      claimName: myapp-crash-pvc
```

`-XX:ErrorFile` phải trỏ vào **đúng mountPath** trong container. Xác minh PVC, `fsGroup`/user ID, ownership và quota. Shared volume giữa nhiều instances có thể có nhiều PID `1`; `%p` **không bảo đảm global uniqueness**. Chia thư mục con theo pod UID/instance hoặc thu ngay vào case storage có tên duy nhất.

**Không nên chỉ dựa vào `kubectl cp` sau khi container chết**: lệnh này cần một container đang truy cập được; pod replacement, crash loop hoặc thiếu `tar` có thể khiến việc lấy artifact thất bại. Thu từ PVC/snapshot/collector thiết kế trước thường tin cậy hơn.

### 4.3. systemd/service managers

Một phần unit **minh họa**, không phải production unit hoàn chỉnh:

```ini
[Service]
User=myapp
WorkingDirectory=/opt/myapp
ExecStart=/usr/bin/java -XX:ErrorFile=/var/lib/myapp/crash/hs_err_pid%p.log -jar /opt/myapp/app.jar
Restart=on-failure
```

`WorkingDirectory=/opt/myapp` không thay đổi đường output khi ErrorFile dùng absolute path. Nhưng `User=myapp` phải ghi được vào crash directory, và các sandbox settings của unit vẫn có thể hạn chế path. `Restart=on-failure` khiến thời gian giữa crash và khởi động lại ngắn; một collector hoặc runbook không được xóa artifact trước khi copy.

Lệnh đọc journal trong cửa sổ sự cố (timestamp và unit là ví dụ):

```bash
journalctl -u myapp.service --since '2026-10-29 10:00:00' \
  --until '2026-10-29 10:30:00' --no-pager
```

Đồng bộ múi giờ giữa systemd journal, HotSpot log, GC/JFR, application logs và Kubernetes events trước khi quyết định chuỗi nguyên nhân.

## 5. Bên trong `hs_err_pid`: những phần nên đọc trước

Fatal error log là file **text** gồm nhiều phần; định dạng thay đổi theo JDK/build/platform. Những mục thường thấy:

| Thành phần | Mục đích khi điều tra |
| --- | --- |
| **Header** | Loại fatal signal/internal error, `pc`, `pid`, `tid`, JRE/VM build, `Problematic frame` |
| **Current thread** | Java/native stack của thread crash, thread state và đôi khi registers/stack bytes |
| **Other threads** | Trạng thái các thread khác và bối cảnh JVM đang làm gì |
| **VM arguments/process** | JVM flags, command line, agent configuration, dynamic libraries và memory mappings |
| **Heap/GC summary** | Một phần cấu hình/bộ nhớ heap/collector gần thời điểm lỗi |
| **System** | OS, CPU, memory, environment và thông tin platform khi có |
| **Core dump information** | Có hoặc không có core dump, vị trí hoặc lý do bị hạn chế |

Ví dụ **minh họa đã rút gọn**, không phải output của một lần chạy thật:

```text
#
# A fatal error has been detected by the Java Runtime Environment:
#
# SIGSEGV (0xb) at pc=0x..., pid=28471, tid=28483
#
# JRE version: ...
# Java VM: OpenJDK 64-Bit Server VM (...)
# Problematic frame:
# C  [libexample.so+0x...]  example_function+0x...
#
# An error report file with more information is saved as:
# /var/lib/myapp/crash/hs_err_pid28471.log
```

Các marker như `pc`, `tid` và `Problematic frame` giúp đối chiếu với core và native stack. Trên Windows có thể là `EXCEPTION_ACCESS_VIOLATION` thay vì `SIGSEGV`. Trong crash nặng, file có thể **bị cắt giữa chừng**; đừng vứt bỏ chỉ vì thiếu section cuối.

### Đọc `Problematic frame` đúng mức độ chắc chắn

- `C`: frame C/C++ native (JNI, thư viện hệ thống hoặc external code).
- `V`: HotSpot VM frame.
- `J`: compiled Java frame.
- `j`: interpreted Java frame.
- `v`: VM-generated stub.

Một frame `C [libfoo.so+...]` nói **nơi thực thi khi crash**, nhưng memory corruption có thể phát sinh trước đó ở thư viện hay thread khác. Frame `V [libjvm.so+...]` **không tự chứng minh** bug của HotSpot; native agents, JNI, data corruption, JDK build và CPU/OS issues cũng có thể liên quan.

Khi đọc nhanh, hãy nối **signal → problematic frame → current thread native/Java stack → libraries/agents → JDK build → recent deploy changes**. Không chọn giải pháp chỉ vì hai file có cùng một dòng hex address hoặc internal error ID; address và layout có thể khác nhau sau mỗi build/restart.

### Vì sao log có thể không đầy đủ?

Fatal error handler hoạt động trong điều kiện bất thường: memory corruption, gần cạn tài nguyên, stack hỏng, file descriptors không hoạt động, disk lỗi hoặc signal chồng. VM có thể ghi được header nhưng chưa kịp ghi process/system sections. Trong báo cáo incident phải đánh dấu **partial / missing / apparently complete**, không tự coi mọi thiếu hụt là trạng thái “normal”.

## 6. Quy trình thu thập ngay sau crash (runbook)

**Mục tiêu 5 phút đầu:** giữ nguyên bằng chứng và gắn đúng identity; phân tích root cause chỉ thực hiện sau khi đã có bản sao/metadata. Việc restart, rollout, retention hoặc dọn thư mục có thể làm mất file trong vài phút.

### Bước 1 — Ghi nhận danh tính sự cố

Tối thiểu cần:

```text
Incident ID: INC-2026-001
Time of failure (UTC): 2026-10-29T10:15:00Z
Service / release / image digest: ...
Node / host / container / Pod UID: ...
Java vendor, full version & build: ...
PID / native TID if available: ...
Termination signal, exit code and reason: ...
Configured -XX:ErrorFile path: ...
Actual hs_err path found: ...
Collector case directory: ...
```

Đây là **mẫu biểu dữ kiện**, không phải thông tin lấy từ một production incident thật. PID có thể trùng giữa các containers; nên lưu Pod UID, host và timestamp. Phân biệt thời điểm lỗi từ JVM, journal, Docker/Kubernetes và hệ thống log tập trung; quy đổi về UTC trước khi dựng timeline.

Nếu JVM **đã chết**, `jcmd <PID> ...` không thể lấy thêm thread dump/JFR/heap từ process đó. Chỉ thu những artifact đã được ghi trước khi chết, hoặc những thông tin OS/container vẫn giữ.

### Bước 2 — Xác định file thật, không chọn bừa file mới nhất

Kiểm tra stdout/stderr trước: HotSpot thường in fatal header và đường dẫn report nếu còn khả năng. Đối chiếu theo PID, thời điểm, JDK version, service/build. Sau đó tìm ở:

1. Path `-XX:ErrorFile` của JVM **thật đang chạy lúc crash**.
2. CWD của process, nhất là khi flag không được truyền đúng.
3. OS temp fallback, ví dụ `/tmp`.
4. Volume/mount của container đã chết, nếu còn.

```bash
find /var/lib/myapp/crash -maxdepth 1 -type f -name 'hs_err_pid*.log' -ls
find /tmp -maxdepth 1 -type f -name 'hs_err_pid*.log' -ls
```

Chỉ chạy trong host/container/volume được phép và xác nhận đúng namespace. File 0 bytes hoặc chỉ vài dòng là evidence **chưa đầy đủ**, không phải lý do để dọn. Nếu file quá lớn, không mở trong editor có khả năng autosave hoặc sửa encoding; dùng `head`, `grep`/`less` **trên bản sao** khi đã bảo toàn.

### Bước 3 — Copy, giữ metadata và đối chiếu SHA-256

Ví dụ Linux với một file đã xác định rõ. `CASE_DIR` cần là thư mục **mới, chỉ thuộc incident này** trên storage được bảo vệ, không trùng đích từ lần copy khác:

```bash
umask 077
SOURCE=/var/lib/myapp/crash/hs_err_pid28471.log
CASE_DIR=/srv/incidents/INC-2026-001

mkdir -p "$CASE_DIR"
stat -- "$SOURCE" > "$CASE_DIR/source-stat.txt"
sha256sum -- "$SOURCE" > "$CASE_DIR/source-sha256.txt"

cp -p -- "$SOURCE" "$CASE_DIR/hs_err_pid28471.log"
sha256sum -- "$CASE_DIR/hs_err_pid28471.log" \
  > "$CASE_DIR/copy-sha256.txt"
```

`stat` ghi timestamp/size/ownership sẵn có của **nguồn**; `cp -p` cố giữ timestamp/mode theo khả năng filesystem; SHA-256 cho phép so bản gốc với bản copy. Lưu ý khi so hai file `source-sha256.txt`/`copy-sha256.txt`: phần **pathname** khác nhau dù hash giống nhau, nên so hai chuỗi hash chứ không so nguyên dòng.

Kiểm tra lại:

```bash
sha256sum -- "$SOURCE" "$CASE_DIR/hs_err_pid28471.log"
```

**Không** chỉnh sửa, đổi newline, nén-xóa, rename hoặc xóa file gốc trước khi đã có bản sao verify được. Nếu filesystem hoặc file vẫn thay đổi, việc chụp snapshot có kiểm soát và đối chiếu hash sẽ phù hợp hơn. Với log gửi cho vendor/ticket, tạo **bản copy đã che dữ liệu nhạy cảm**, giữ forensic original riêng.

### Bước 4 — Thu dữ liệu quanh thời điểm crash

| Artifact (nếu tồn tại) | Vị trí/cách lấy | Giá trị chẩn đoán |
| --- | --- | --- |
| `hs_err_pid<pid>.log` | ErrorFile path/CWD/fallback | Fatal signal, problematic frame, threads, VM state |
| Stderr/stdout, launcher log | Console, journal, container log collector | Fatal header, actual report path, restart/exit reason |
| GC/safepoint logs | `-Xlog` output hoặc log aggregation | Memory/GC timeline, pauses trước crash |
| JFR `.jfr` / repository chunks | JFR disk recording/repository còn được giữ | CPU, GC, locks, I/O events trước crash, nếu đã flush |
| `.hprof` **nếu được tạo** | `HeapDumpPath` hoặc pre-captured heap | Java heap OOME, retained objects |
| Core/minidump **nếu có** | OS core handler/Windows dump | Native memory, registers, stacks |
| Kernel/cgroup/container events | Node/orchestrator logs, cgroup metrics | OOMKilled, SIGKILL, disk/host resource issues |
| Deployment metadata | Image digest, JDK build, startup args đã kiểm duyệt | Tái hiện đúng software/config versions |
| Service/dependency metrics | Hệ thống monitoring hiện có | Error burst, memory/CPU/network context |

Không phải lúc nào cũng cần hoặc có được tất cả. **Core dump là một cơ chế khác** và phụ thuộc OS policy, `ulimit`, kernel `core_pattern`/systemd-coredump, filesystem, container settings, dung lượng. `hs_err` **không** tự động chứa toàn bộ core hay Java heap. JFR có thể mất những event chưa flush ở đoạn cuối trước crash.

### Bước 5 — Tạo manifest để không mất nguồn gốc

Ví dụ schema của manifest (phải điền giá trị thật cho từng incident):

```text
incident_id: INC-2026-001
capture_time_utc: 2026-10-29T10:18:05Z
service_release: ...
source_host: ...
source_pod_uid: ...
source_pid: 28471
jdk_build: ...
source_path: /var/lib/myapp/crash/hs_err_pid28471.log
case_copy: /srv/incidents/INC-2026-001/hs_err_pid28471.log
copy_sha256: ...
source_mtime_utc: ...
file_state: partial / apparently complete / unknown
collector: ...
permissions: restricted
```

Manifest cần nêu **cách thu thập, ai/hệ thống nào thu, thời điểm, nguồn, checksum và trạng thái đầy đủ**. Trường chưa xác minh phải để *unknown*, không tự điền “complete” chỉ vì file tồn tại. Đừng công bố error log thiếu đuôi là báo cáo toàn trạng thái JVM.

## 7. Kubernetes: nhận diện OS kill và giữ log cũ

Khi pod/container restart, lấy termination reason và previous logs **nếu Kubernetes vẫn còn giữ**:

```bash
kubectl get pod checkout-7c48 -n production \
  -o jsonpath='{.status.containerStatuses[*].lastState.terminated.reason}'

kubectl logs checkout-7c48 -n production -c java-service \
  --previous --timestamps
```

Tên Pod/namespace/container ở đây là **ví dụ**, phải dùng đúng identity. `--previous` chỉ hoạt động khi logs container instance trước còn được kubelet/API cung cấp; nếu Pod đã bị xóa hoặc replacement xảy ra, logs có thể đã mất.

Cách đọc:

- `OOMKilled`, thường `exitCode=137`: ưu tiên memory cgroup/node/limit; **không kỳ vọng** JVM tạo `hs_err` trước khi bị kill.
- `SIGSEGV` fatal header: tìm `hs_err` ở persistent crash volume và stderr.
- `Error`/exit code khác 0 nhưng **không có fatal header**: có thể là app exception, startup error, failed health check hoặc OS signal khác; không tự quy thành JVM bug.
- Multiple restarts: lưu **pod UID, container ID và thời gian**, không chỉ tên service. Pod mới không đồng nhất với container filesystem cũ.

Ở cgroup v2, `memory.events` có thể ghi nhận `oom`/`oom_kill`, nhưng cần đọc tại **đúng cgroup** trong thời gian còn tồn tại. Khi cgroup bị xóa, dựa thêm metrics và events đã thu trước đó. `memory.current` là mức accounting theo cgroup, không bằng RSS của riêng JVM.

**Đừng** xóa/rollout/migrate crash volume trước khi copy nếu việc đó có thể làm mất bằng chứng; cân đối với yêu cầu khôi phục dịch vụ và phân quyền incident response.

## 8. Lab Java 17+: kiểm tra khả năng ghi mà không crash

Lab chủ động **không tạo fatal error**, chỉ kiểm tra JVM nhận cờ và current user có thể tạo/ghi/xóa file tạm trong directory. Không cần JNI/Unsafe, không tác động project.

### 8.1. Tạo `CrashArtifactPreflight.java`

```java
import java.lang.management.ManagementFactory;
import java.nio.file.Files;
import java.nio.file.Path;

public class CrashArtifactPreflight {
    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            throw new IllegalArgumentException("Pass the existing crash directory");
        }
        Path dir = Path.of(args[0]);
        System.out.println("directory.exists=" + Files.isDirectory(dir));

        Path probe = null;
        try {
            probe = Files.createTempFile(dir, ".crash-write-probe-", ".tmp");
            Files.writeString(probe, "write check");
            System.out.println("probe.write=OK");
        } finally {
            if (probe != null) Files.deleteIfExists(probe);
        }

        boolean configured = ManagementFactory.getRuntimeMXBean()
                .getInputArguments().stream()
                .anyMatch(flag -> flag.startsWith("-XX:ErrorFile="));
        System.out.println("errorfile.argument.present=" + configured);
        System.out.println("pid.positive=" + (ProcessHandle.current().pid() > 0));
    }
}
```

Giải thích:

- `Files.isDirectory(dir)`: directory có tồn tại không, chưa tự chứng minh writable.
- `Files.createTempFile` và `Files.writeString` thử **ghi file thật**, sau đó `finally` xóa file test. Thất bại sẽ ném exception để preflight FAIL.
- `getInputArguments()` trả startup flags, kiểm tra `-XX:ErrorFile=` có mặt. Nó **không** xác minh path cụ thể và tuyệt đối không đảm bảo handler ghi được khi crash.
- `ProcessHandle.current().pid()` có PID hợp lệ, giúp hiểu `%p` nhưng không in giá trị thay đổi theo từng lần chạy.

### 8.2. Biên dịch/chạy Linux

Giả sử `/var/lib/myapp/crash` đã được provision và writable với user hiện hành:

```bash
javac CrashArtifactPreflight.java
java '-XX:ErrorFile=/var/lib/myapp/crash/hs_err_pid%p.log' \
  CrashArtifactPreflight /var/lib/myapp/crash
```

Stdout **chính xác khi mọi kiểm tra thành công**, đã kiểm tra bằng `javac --release 17` và chạy trên OpenJDK 24:

```text
directory.exists=true
probe.write=OK
errorfile.argument.present=true
pid.positive=true
```

Vì JVM kết thúc bình thường, **không có** `hs_err_pid...log` được tạo — đây là điều đúng. Nếu directory không ghi được, có thể có stack trace Java cho `AccessDeniedException` hoặc lỗi I/O khác; **đó vẫn không phải fatal VM error**.

Trên Windows PowerShell:

```powershell
New-Item -ItemType Directory -Force -Path C:\java-diag\crash
javac CrashArtifactPreflight.java
java '-XX:ErrorFile=C:/java-diag/crash/hs_err_pid%p.log' CrashArtifactPreflight 'C:\java-diag\crash'
```

**Giới hạn của preflight:** tại thời điểm crash vẫn có thể phát sinh disk full, inode exhaustion, readonly remount, memory corruption, hết file descriptors hoặc process bị `SIGKILL`; không có kiểm tra trước nào biến `ErrorFile` thành bảo đảm 100%.

## 9. Không nhầm `ErrorFile` với các dump khác

| Tùy chọn/công cụ | Kích hoạt ở tình huống nào | Kết quả |
| --- | --- | --- |
| `-XX:ErrorFile=...` | HotSpot fatal error, nếu handler chạy được | Text fatal error report (`hs_err_pid...log`) |
| `-XX:+HeapDumpOnOutOfMemoryError` | Một số Java OOME theo cơ chế VM | Heap profile `.hprof` |
| `-XX:HeapDumpPath=...` | Chỉ đường của heap dump khi tính năng tương ứng bật | Đường đến `.hprof`; không quyết định hs_err |
| OS core-dump settings | Core dump được OS/VM cho phép | Binary core/minidump, có thể rất lớn |
| `-XX:StartFlightRecording=...` | JFR recording được bật | Recording `.jfr` và/hoặc disk chunks tùy settings |
| `-Xlog:gc*` | Unified logging theo event và level | GC log với rotation riêng |
| `jcmd ...` | **JVM đang sống và attach được** | Thread dump, JFR dump, heap data hoặc các diagnostic views tùy command |

Ví dụ đồng thời chuẩn bị fatal log và heap dump cho Java OOME:

```bash
java \
  '-XX:ErrorFile=/var/lib/myapp/crash/hs_err_pid%p.log' \
  -XX:+HeapDumpOnOutOfMemoryError \
  -XX:HeapDumpPath=/var/lib/myapp/crash \
  -jar app.jar
```

**Hai loại file có điều kiện kích hoạt khác nhau.** Heap dump có thể rất lớn và chứa dữ liệu nhạy cảm. Cần riêng headroom và policy bảo quản. Với core dump cũng vậy: có `hs_err` không đồng nghĩa core có tồn tại; còn phụ thuộc OS, `ulimit -c`, kernel core handler, volume, quota và security settings.

Cờ `-XX:+ExtensiveErrorReports` trên một số HotSpot có thể tăng chi tiết fatal report, nhưng đồng thời khiến dữ liệu lớn/nhạy cảm hơn; không bật tràn lan nếu chưa có policy.

## 10. Xử lý khi không thấy file hoặc file thiếu dữ liệu

**Cây quyết định:**

```text
Service kết thúc bất thường
    |
    +-- Stderr có fatal header / native signal không?
    |        |
    |        +-- Có: tìm ErrorFile path -> CWD -> OS temporary fallback
    |        |          kiểm tra quyền, disk/quota, mount, container lifecycle
    |        |          file có thể partial -> vẫn bảo quản
    |        |
    |        +-- Không: kiểm tra Java exception, termination signal,
    |                   OOMKilled, orchestrator/host logs
    |
    +-- Có file hs_err thuộc đúng PID/instance/time không?
             |
             +-- Có: copy + stat + SHA-256 + incident manifest + liên hệ JDK
             |
             +-- Không: đánh dấu MISSING, thu evidence độc lập khác
```

Các nguyên nhân thường gặp:

1. **Không có fatal VM error:** Java exception/OOME/normal shutdown không trigger handler theo mặc định.
2. **OS chấm dứt process:** SIGKILL hoặc container OOMKill không cho handler chạy.
3. **Flag không nằm trong JVM args:** startup script dùng đường khác, option đặt sau `-jar`, config thay đổi mà chưa redeploy.
4. **Path không tồn tại hoặc không ghi được:** SELinux/AppArmor, container readonly root, user sai, quota đầy.
5. **Fallback nằm trong `/tmp`:** người điều tra chỉ tìm custom path, trong khi VM thực tế đã ghi nơi khác.
6. **CWD khác dự kiến:** service manager hoặc entrypoint đổi working directory.
7. **Pod/container bị tái tạo:** ephemeral layer cũ biến mất.
8. **PID reuse/trùng tên:** file bị ghi đè hoặc một file thuộc instance khác.
9. **Rotation/cleanup:** collector chưa kịp sao chép trước khi artifact bị dọn.
10. **Crash quá nặng:** file có thể rỗng hoặc chỉ chứa header trước khi error handler gặp lỗi thứ hai.

Nếu chỉ có header, xem nó là **partial artifact**, tiếp tục bảo quản. Không tạo file rỗng với tên `hs_err_pid` để giả làm bằng chứng; manifest nên ghi `missing`, `partial`, hoặc `apparently complete` đúng theo quan sát.

### Ba tình huống để luyện chẩn đoán

**A. Native SIGSEGV từ JNI:** stderr có `SIGSEGV` và `Problematic frame: C [libcodec.so+...]`; file `hs_err` còn trong crash volume. Thu ngay fatal log/core (nếu có), ghi phiên bản thư viện, JDK, flags, deploy timeline và SHA-256. **Chưa kết luận** đúng thư viện đó là nguyên nhân gốc nếu chưa xem memory corruption/lifetime.

**B. Java heap OOME:** log có `java.lang.OutOfMemoryError: Java heap space` nhưng không có fatal header. Nếu đã bật heap dump, thu `.hprof`, GC logs, app metrics. Không xem thiếu `hs_err` là lỗi cấu hình.

**C. Kubernetes OOMKilled:** container reason `OOMKilled`, không có `hs_err`. Thu cgroup/node memory evidence, host/container events, stdout/stderr trước kill, configured memory limits, heap/native memory metrics từ collector. Không tìm cách bắt `jcmd` vào PID đã mất.

## 11. Bảo mật và vòng đời của crash artifacts

Fatal log có thể chứa **JVM arguments, system properties, environment variables, đường dẫn file, stack trace, native libraries, memory addresses**. Một số hệ thống đặt token/secret ở command line hoặc environment. Vì thế:

- Lưu original trong restricted case storage, có phân quyền và encryption thích hợp; tránh public/share links.
- Không paste nguyên log lên ticket/chat công khai hoặc vendor chưa có chính sách dữ liệu.
- Khi chia sẻ, dùng **bản sao được che dữ liệu nhạy cảm**, giữ bản gốc và hash dưới quyền IR/SRE phù hợp.
- Thu đủ **host, process, deployment version, timestamp và chain of custody** để tái dựng nguồn gốc, không dùng filename đơn lẻ như identity.
- Đặt retention/quota cho crash artifacts; archive/copy **trước** khi xóa. Không để cleanup xóa log ngay lúc rollout sau crash.
- Theo dõi disk space; một crash loop có thể tạo nhiều logs và core dumps. Đừng làm đầy crash volume khiến incident kế tiếp không ghi được file.
- Nếu phát hiện secrets bị chia sẻ sai, thực hiện quy trình thu hồi/rotate phù hợp.

## 12. Checklist áp dụng

### Trước sự cố

- [ ] JVM sử dụng HotSpot/JDK phù hợp, `-XX:ErrorFile` nằm trong startup flags thật.
- [ ] Đường dẫn tuyệt đối trỏ tới directory có trước khi chạy; dùng `%p` và tránh tên dễ ghi đè.
- [ ] User/service/container security context ghi được; có disk/quota/inode headroom.
- [ ] Crash directory được mount để sống qua lifecycle cần thiết; biết rõ `emptyDir` vs persistent volume.
- [ ] Có collector và runbook bảo quản ngay, không để cleanup/rotation chạy trước.
- [ ] Có quyền truy cập hạn chế, retention và chính sách bảo vệ dữ liệu nhạy cảm.
- [ ] Chạy lab Java 17+ **không crash** bằng đúng user/mount, kiểm tra flag và khả năng ghi.

### Ngay sau sự cố

- [ ] Ghi time UTC, host, instance/container/pod UID, PID, JDK version, release, exit reason.
- [ ] Tìm `hs_err` ở ErrorFile path, CWD hoặc OS temp fallback theo bằng chứng.
- [ ] Xác định đúng file với PID/time/header; ghi rõ nếu file partial hoặc missing.
- [ ] Lưu bản gốc, tạo bản copy riêng, stat, checksum và manifest.
- [ ] Thu stdout/stderr, GC/JFR/heap/core nếu có, kernel/container events và deployment metadata.
- [ ] Đọc header, problematic frame, current/native thread, VM args, libraries; liên hệ phiên bản/recent changes.
- [ ] Không suy root cause chỉ từ `Problematic frame`, không nhầm Java OOME với kernel OOMKilled.
- [ ] Khi chia sẻ, chỉ chuyển bản đã kiểm duyệt và được phép.

**Kết luận:** thu `hs_err_pid` hiệu quả là một **quy trình gồm hai nửa**: chuẩn bị `-XX:ErrorFile`/writable persistent storage **trước crash**, và **bảo toàn chứng cứ ngay sau crash**. `hs_err` là snapshot khả dĩ tại thời điểm HotSpot gặp lỗi nghiêm trọng, **không phải** công cụ đảm bảo mọi lần process chết đều để lại báo cáo. Kết hợp nó với stderr, JFR/GC logs, heap/core và OS/container evidence để có kết luận đáng tin.

## Tài liệu tham khảo

- [Oracle JDK 21 — `java` command: `-XX:ErrorFile`, fallback, heap dump, extensive reports](https://docs.oracle.com/en/java/javase/21/docs/specs/man/java.html)
- [Oracle JDK 24 — Fatal Error Log: location, file naming, header/threads/process/system](https://docs.oracle.com/en/java/javase/24/troubleshoot/location-fatal-error-log.html)
- [Oracle JDK 21 — Troubleshooting Guide](https://docs.oracle.com/en/java/javase/21/troubleshoot/)
- [Oracle JDK 21 — `jcmd`: diagnostic commands](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html)
- [Oracle HotSpot — How to find and interpret the fatal error log](https://ops.java/troubleshooting/articles/fatal-error-log/)
