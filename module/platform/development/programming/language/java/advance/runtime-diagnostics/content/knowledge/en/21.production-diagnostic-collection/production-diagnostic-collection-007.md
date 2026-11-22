# 21.7 Xử lý giới hạn quyền attach, filesystem chỉ đọc hoặc môi trường thiếu công cụ JDK

## Mục tiêu học tập

Khi vận hành Java trong container, Kubernetes, môi trường distroless hoặc production có hardening, cách thu thập quen thuộc như `jcmd <pid> Thread.print`, `jcmd <pid> JFR.dump` hay tạo heap dump có thể thất bại vì **không đủ quyền attach**, **không có nơi ghi file**, hoặc **runtime image không có công cụ JDK**. Một số trường hợp còn gặp cả ba rào cản cùng lúc.

Bài học hướng dẫn **chẩn đoán theo từng giới hạn và chọn phương án thu thập an toàn**, thay vì mở quyền root, tắt hardening hay khởi động lại ứng dụng một cách mù quáng.

Sau bài này, bạn có thể:

- Phân biệt lỗi **PID/namespace**, **quyền hệ điều hành**, **attach bị tắt**, **socket/thư mục tạm**, **tool không có trong image** và **filesystem chỉ đọc**.
- Biết `jcmd` cần gì để hoạt động và tại sao `jcmd -l` không thấy JVM **chưa đủ** để kết luận JVM không chạy.
- Xác định nơi một file JFR, heap dump, GC log, fatal-error log thực sự được **JVM đích** ghi; chọn volume writable và retention hợp lý.
- Thay `jcmd` bằng số đo **MXBeans/JMX**, thread snapshot trong process, GC logs ra stdout, JFR khởi tạo bằng JVM flags/API hoặc tín hiệu thread dump được JVM hỗ trợ khi phù hợp.
- Hiểu vai trò, khả năng và giới hạn của **debug/ephemeral container** trong Kubernetes mà không tự động tăng đặc quyền hoặc thay đổi bảo mật.
- Thiết kế runbook thu thập bằng chứng có timestamp, PID, JDK version, quyền, đường dẫn và tác động vận hành.
- Chạy một ví dụ **Java 17+ tự quan sát JVM bằng MXBeans** không cần attach và không tạo file.

**Phạm vi:** các lựa chọn VM flags và `jcmd` minh họa cho HotSpot/OpenJDK Java 17+. Linux/container/Kubernetes là bối cảnh vận hành chính; chương trình Java dùng API tiêu chuẩn, chạy được cả trên Windows. Công cụ, câu chữ lỗi và cơ chế attach có thể khác theo JDK vendor, OS, security policy và container runtime. Đừng suy rộng HotSpot diagnostics thành cam kết cho mọi JVM.

## 1. Ba rào cản khác nhau, ba câu hỏi cần tách biệt

Một sự cố “không thu được diagnostics” phải được phân loại trước khi sửa:

| Rào cản | Triệu chứng điển hình | Câu hỏi xác minh | Hướng đi ban đầu |
| --- | --- | --- | --- |
| **Attach** | `AttachNotSupportedException`, không thấy PID, `Permission denied`, timeout chờ attach listener | Đúng process chưa? Cùng host/PID namespace, effective UID/GID và temp path chưa? JVM có tắt attach không? | Sửa context/quyền **đúng mức**, hoặc dùng capture không cần attach |
| **Filesystem** | `Read-only file system`, `AccessDeniedException`, `No space left on device` khi ghi `.jfr`/`.hprof`/log | Thư mục nào readonly? Có volume writable cho user JVM không? Dung lượng/inode/quota đủ không? | Chọn stdout hoặc writable volume, giới hạn file, phân biệt output path và scratch |
| **Thiếu công cụ JDK** | `jcmd: not found`, `jfr: not found`, không có `jstack`, `jmap` | Image dùng JRE/jlink/distroless? Binary bị bỏ khỏi PATH hay không được đóng gói? | Dùng MXBeans/JFR startup/logging; debug image tương thích khi chính sách cho phép |

Ba rào cản **không tương đương**. Ví dụ:

- Có `jcmd` nhưng user sai → attach không được.
- Có quyền attach nhưng JVM khởi động `-XX:+DisableAttachMechanism` → attach vẫn không hoạt động.
- Có `jcmd` và attach thành công nhưng `JFR.dump` vào `/app` readonly → lỗi ở **đường dẫn ghi file**, không phải attach.
- Có filesystem writable và đủ quyền nhưng image không có `jcmd` → không thể chạy câu lệnh chưa được đóng gói.
- Root filesystem readonly **không có nghĩa toàn bộ mount đều readonly**: `/tmp` hoặc `/diagnostics` có thể là writable volume riêng.

**Nguyên tắc:** ghi nhận **đúng thông báo lỗi, process, UID/GID, mount và thời gian**. Không dùng lỗi ở tầng filesystem để suy luận ngay rằng bảo mật attach cần bị tắt.

## 2. Cây quyết định khi cần thu thập ngay

~~~text
Cần lấy bằng chứng lúc JVM đang gặp vấn đề
                    |
                    v
      Có công cụ thích hợp trong môi trường?
             /                    \
            Có                    Không
            |                       |
            v                       v
     Xác định đúng PID       MXBeans / app metrics,
     & context tool          GC stdout / JFR startup,
            |                 tín hiệu thread dump
            v                 (nếu được phép)
      Attach thành công?
       /           \
      Có           Không
      |              |
      v              v
   Chọn lệnh      Phân loại:
   ít tác động    PID/UID/GID/namespace,
      |           attach disabled,
      v           temp path, container
  Nếu lệnh ghi         |
  file: có mount        v
  writable không?     Khắc phục đúng
    /      \           quyền/cấu hình
   Có      Không       hoặc fallback
   |         |
   v         v
 Dump vào  stdout/logs
 volume    /MXBeans/
 hợp lệ    JFR có kế hoạch
   |
   v
 Xác minh file và tính toàn vẹn -> lưu evidence + thời gian
~~~

Ở một sự cố cần phản ứng nhanh, ưu tiên **dữ liệu đã có**: application logs, metrics, tracing, GC logging, JFR đang ghi, container events và lịch sử restart. Chỉ tiến hành attach/heap dump sau khi biết lợi ích, tác động và quyền vận hành.

## 3. `jcmd` cần những điều kiện nào?

`jcmd` là công cụ diagnostic của JDK gửi lệnh đến JVM đang chạy. Theo tài liệu Oracle Java 21, lệnh cần chạy trên **cùng máy** với tiến trình đích và có **effective user/group identity** phù hợp. Trong container, còn có vấn đề namespace, nhìn thấy PID và khả năng dùng thư mục/socket attach của JVM.

### 3.1 Bước xác minh không làm thay đổi JVM

Trong container/host có shell và công cụ hệ điều hành thích hợp:

~~~sh
# Xác định user hiện tại của shell:
id
id -u
id -g

# Xem process (nếu image có ps):
ps -eo pid,uid,gid,args

# Xem tool có trên PATH không (nếu có shell):
command -v java
command -v jcmd

# Nếu JVM là process PID 1 trong cùng namespace:
cat /proc/1/status
~~~

`/proc/1` chỉ là ví dụ kiểm PID 1, **không mặc định mọi ứng dụng Java đều có PID 1**. Nếu container không có `sh`, `ps` hay `cat`, đừng diễn giải lệnh “not found” là không có process. Dùng process metadata/metrics từ orchestrator, hoặc cơ chế debug đã được tổ chức cho phép.

Trong môi trường có JDK:

~~~sh
# Liệt kê JVM mà công cụ có thể nhìn thấy:
jcmd -l

# Dùng PID thực đã xác minh; lệnh dưới tác động rất nhỏ:
jcmd 1234 VM.version

# Liệt kê lệnh được JVM hiện tại hỗ trợ:
jcmd 1234 help
~~~

`1234` chỉ là PID minh họa. **Không dùng `jcmd 0 ...` trong lúc điều tra một service riêng**, vì theo cú pháp `jcmd`, PID 0 có thể gửi lệnh đến **tất cả JVM tìm thấy**. Tương tự, chọn main-class thay vì PID có thể match nhiều process; PID thực tế được kiểm tra sẽ an toàn hơn.

Đặc biệt, tài liệu `jcmd -l` nêu ngoại lệ với các JVM chạy trong Docker process riêng. Nếu danh sách trống, hãy tìm PID bằng metadata/process view phù hợp, không tự kết luận JVM đã chết.

### 3.2 Những lý do attach thất bại

**Sai user:** app chạy dưới UID 10001 nhưng shell debug/host là UID khác. Chỉ vì user debug là “root trong container” không có nghĩa tương tác với một JVM non-root ở namespace/security context khác sẽ tự động thành công. Yêu cầu effective UID/GID và các policy OS cần được xác minh theo JVM thật.

**Sai PID namespace / host context:** PID 1 trong container có thể mang PID khác trên node. Một helper không nhìn thấy đúng process có thể không thể attach, ngay cả khi có binary `jcmd`.

**Cơ chế attach bị tắt:** HotSpot hỗ trợ khởi động với:

~~~sh
java -XX:+DisableAttachMechanism -jar app.jar
~~~

Đây là **JVM flag**, phải nằm trước `-jar`. Trong thử nghiệm trên HotSpot JDK 24, `jcmd <pid> VM.version` đến JVM đã bật flag này trả `AttachNotSupportedException: The VM does not support the attach mechanism`. Thay `jcmd` bằng `jstack`/`jmap` thông thường không tự giải quyết khi các công cụ cũng cần Attach API. Không giả định có thể “bật lại” attach trong một JVM đang chạy chỉ bằng một lần `jcmd`.

**Temp/socket không sẵn sàng:** trên HotSpot/Linux, cơ chế attach có thể sử dụng các special files/socket liên quan PID và thư mục tạm (ví dụ `/tmp/.java_pid<PID>`), đồng thời bị ảnh hưởng mount namespace/UID/quyền. `/tmp` chỉ đọc hoặc không có không gian có thể làm attach không hoàn tất. **Không tự tạo, sửa quyền rộng hoặc xóa socket trong `/tmp` của JVM đang sống** để thử vận may: có thể gây gián đoạn/đụng vào dữ liệu của tiến trình khác.

**Attach listener chưa phản hồi:** JVM đang quá tải hoặc trong trạng thái không phản hồi có thể khiến lệnh timeout. Phân biệt với JVM đã chết, PID tái sử dụng, namespace sai hoặc security policy chặn tín hiệu/socket.

**Quyền hệ điều hành bổ sung:** container security policy, user namespaces, `/proc` visibility, seccomp, AppArmor/SELinux và mount layout có thể ảnh hưởng các công cụ. Không giả định thêm `CAP_SYS_PTRACE`, chạy privileged hay root là điều kiện chung để `jcmd` hoạt động; chỉ cấp quyền thực sự cần thiết sau khi xác định cơ chế và được phê duyệt.

### 3.3 Không dùng các “mẹo” chưa kiểm chứng

- `-Djava.io.tmpdir=/somewhere` **không được coi là bảo đảm** sửa được attach. Hành vi socket/attach là implementation-specific và có thể không theo mọi đường dẫn tạm mà ứng dụng Java dùng.
- `-Djdk.attach.allowAttachSelf=true` liên quan self-attach của cùng JVM trong tình huống nhất định; **không thay thế** yêu cầu user/PID/namespace của một công cụ từ process khác.
- `-XX:+StartAttachListener` có thể cấu hình listener sớm trên HotSpot hỗ trợ, nhưng không vượt qua `-XX:+DisableAttachMechanism`, file permission hay security context. Cần kiểm option và thử trong staging.
- Chạy tool từ JDK mới hơn/khác vendor **không phải luôn tương thích** với JVM đích; ưu tiên version/vendor phù hợp và kiểm chứng lệnh `help`.
- Không đưa `/tmp` hay các mount nhạy cảm về mode `777`, không tắt seccomp/AppArmor và không triển khai container privileged chỉ để làm lệnh chạy.

Nếu chính sách cố ý không cho attach, hãy chọn phương thức **không cần attach** thay vì tìm cách vượt qua chính sách.

## 4. Filesystem chỉ đọc: xác định chính xác nơi nào không ghi được

Trong container đã bật `readOnlyRootFilesystem: true`, những phần thuộc root filesystem của image được bảo vệ khỏi ghi, nhưng **writable volume mounts** vẫn có thể được cung cấp. Vấn đề không phải “JVM không có quyền ghi vào mọi chỗ”, mà là nơi nào đã được mount, user nào sở hữu và phần nào có đủ dung lượng.

### 4.1 Điều tra vị trí và dung lượng

Trên Linux có shell/utilities:

~~~sh
# Các mount liên quan, quyền thư mục và dung lượng:
ls -ld /tmp /diagnostics
df -h /tmp /diagnostics
df -i /tmp /diagnostics
cat /proc/mounts
~~~

Các lệnh có thể không có trong distroless image. Đọc `/proc/mounts` để phân biệt mount readonly (`ro`) với writable (`rw`) khi có quyền xem. `df -h` đo dung lượng, `df -i` đo inode; thiếu một trong hai vẫn có thể khiến không tạo được file.

**Kiểm tra ghi** chỉ ở thư mục đã được chỉ định để chẩn đoán, không đụng vào source/config hay thư mục nhạy cảm:

~~~sh
# Chỉ chạy khi /diagnostics là vùng được phép và mktemp có sẵn:
tmpfile=$(mktemp /diagnostics/probe.XXXXXX) || exit 1
rm -- "$tmpfile"
~~~

Lệnh `mktemp` có thể khác giữa GNU/BusyBox; trên image không có shell hoặc tool thì dùng cơ chế kiểm mount khác. `test -w` hoặc `Files.isWritable(...)` đôi khi chỉ là kiểm quyền dự đoán; **thử tạo file thực sự ở đúng mount** là bằng chứng rõ hơn khi được phép.

### 4.2 Phân biệt bốn loại đường dẫn

| Loại đường dẫn | Ai sử dụng | Rủi ro khi readonly/quota |
| --- | --- | --- |
| **Ứng dụng / user.dir** | Relative file path, config/cache/log của app | Relative `filename=...` có thể ghi nhầm vào `/app` readonly |
| **JVM temporary area** | Một phần temp files, cơ chế VM/attach tùy OS/JDK | `/tmp` readonly/quyền sai có thể làm diagnostics thất bại |
| **JFR repository** | Các chunks lưu tạm khi JFR recording vào disk | Repo không writable có thể khiến JFR không thu/dump như kỳ vọng |
| **Final output** | `.jfr`, `.hprof`, `hs_err_pid...log` và file logs | Cần writable path, đủ dung lượng và quyền bảo vệ dữ liệu |

Một `filename=/diagnostics/capture.jfr` hợp lệ **chưa tự chứng minh repository tạm của JFR đã writable**. Với HotSpot Java 17+, có thể cấu hình nơi lưu JFR repository bằng `-XX:FlightRecorderOptions=repository=...` và đặt final output tương ứng.

### 4.3 Khi cần heap dump

Nếu JVM có heap OOM và bạn cần file để phân tích hậu sự cố, chuẩn bị trước:

~~~sh
java -XX:+HeapDumpOnOutOfMemoryError \
     -XX:HeapDumpPath=/diagnostics \
     -XX:ErrorFile=/diagnostics/hs_err_pid%p.log \
     -jar app.jar
~~~

Đây là ví dụ command cho **lần khởi động mới**, yêu cầu `/diagnostics` tồn tại/writable. Heap dump có thể **rất lớn**, tác động thời gian và chứa dữ liệu nhạy cảm; đặt ngân sách disk, chính sách bảo vệ/truy xuất/xóa. JVM OOM do **container cgroup OOMKill** hoặc `SIGKILL` không phải lúc nào cũng cho JVM cơ hội ghi heap dump hoặc fatal-error log; không dùng sự vắng mặt của file làm bằng chứng không có sự cố bộ nhớ.

`-XX:ErrorFile` dùng cho các **fatal JVM errors** khi HotSpot có thể tạo báo cáo, không phải một file dành cho mọi Java exception. Không lẫn fatal-error log với heap dump/GC log.

## 5. Không có nơi ghi file: ưu tiên stdout/stderr và dữ liệu có sẵn

Container thường thu stdout/stderr bằng logging driver/orchestrator. Khi filesystem readonly nhưng luồng console vẫn hoạt động, **Unified Logging** giúp thu GC/safepoint/JVM startup data mà không tạo file trong image:

~~~sh
# Chạy từ lúc JVM khởi động; không cần jcmd:
java '-Xlog:gc*:stdout:time,uptime,level,tags' -jar app.jar
~~~

Cú pháp đã được thử trên HotSpot JDK 24 (thành công với `-XX:+DisableAttachMechanism`). Chọn tags/levels tối thiểu theo câu hỏi. `gc*` thu khá nhiều thông tin, nhất là tại startup; với hệ thống nhạy chi phí hoặc log volume lớn, bắt đầu `-Xlog:gc=info:stdout:uptime,level,tags` rồi mở chi tiết khi cần.

Một ví dụ stdout hẹp hơn:

~~~sh
java '-Xlog:gc=info:stdout:uptime,level,tags' -jar app.jar
~~~

**Ưu điểm:** không cần quyền ghi file do app sở hữu, log có timestamp và được collector đưa ra ngoài container (nếu pipeline cấu hình đúng). **Giới hạn:** log không thay thế heap dump/JFR, có thể bị mất nếu collector không thu/retention quá ngắn, và chi phí logging vẫn cần được tính. Khi app chỉ chạy sẵn mà không có logging, bạn không thể “bổ sung JVM startup flags” vào process hiện tại nếu không có lần restart/deploy mới.

### 5.1 Lấy thread dump không cần Attach API (có điều kiện)

Trên HotSpot/Linux, khi có **quyền gửi tín hiệu** đúng process:

~~~sh
# PID phải được xác minh; đây là tín hiệu QUIT, không phải TERM/KILL.
kill -QUIT 1234
~~~

Thông thường HotSpot xử lý `SIGQUIT` bằng cách **in thread dump** tới output của **JVM đích** rồi tiếp tục chạy. Đây là một cơ chế khác attach: không cần `jcmd` nhưng vẫn chịu OS signal permissions và policy. **Không nhầm `kill -QUIT` với `kill -9`, `SIGTERM` hoặc `SIGABRT`**. Kiểm tra `stdout/stderr` của JVM (ví dụ orchestrator logs), không chờ dump xuất hiện trong terminal gọi lệnh.

Các giới hạn:

- `-Xrs` có thể vô hiệu hóa handler thread dump dựa trên `SIGQUIT`; signal handling cũng có thể khác theo JVM/platform.
- Cần cùng PID namespace hoặc cách định danh process đúng; user gửi tín hiệu phải có quyền.
- Thread dump có thể chứa tên thread, method và dữ liệu nhạy cảm trong stack; giới hạn chia sẻ.
- Lệnh không cung cấp heap histogram, NMT hoặc JFR đầy đủ; tránh gửi liên tục gây nhiễu.
- Với Windows, cơ chế **Ctrl+Break** là một lựa chọn khi app có console/handler tương ứng; không dùng `kill -QUIT` từ ví dụ Linux lên Windows.

### 5.2 Tận dụng logs/metrics ngay cả khi process không phản hồi

Ngay cả khi không attach, bạn có thể còn những nguồn đã được bật trước:

- **Application metrics/health endpoints:** latency, request rate, errors, heap/GC/thread/classloading qua metrics bridge.
- **Orchestrator logs/events:** container restarts, exit code, OOMKilled, probe failures, cgroup limits, pod/node pressure, timestamp.
- **OpenTelemetry/APM/tracing** đã tích hợp: spans, error attributes, deployment version.
- **Host/container OS metrics:** RSS, CPU, file descriptors, cgroup memory usage, I/O; cần phân biệt OS metrics với JMX heap used.
- **JFR ghi từ startup** và được xuất có kế hoạch; có thể phân tích offline bằng máy khác.

Chọn nguồn bằng chứng theo câu hỏi thay vì cố lấy mọi thứ. Không có heap dump không ngăn bạn phân tích ban đầu một vụ timeout; có GC logs, thread metrics và request timeline đôi khi đã đủ khoanh vùng.

## 6. Không có `jcmd` trong image: hiểu runtime thực sự đang có gì

Trong JDK build đầy đủ, `java`, `javac`, `jcmd`, `jfr` là các công cụ khác nhau; một **runtime image** được rút gọn bằng jlink có thể chỉ chứa `java` và các modules cần chạy ứng dụng. Một image distroless có thể không có cả shell, package manager, `ps` và `jcmd`. **“Có lệnh `java`” không chứng minh “có toàn bộ JDK tools”**.

Nếu có khả năng chạy lệnh:

~~~sh
java -version
java --list-modules
command -v jcmd
command -v jfr
command -v jstack
~~~

`java --list-modules` giúp kiểm các module như `java.management`, `jdk.jfr` và `jdk.management.jfr` (nếu có). **Thiếu `jcmd` binary không đồng nghĩa `jdk.jfr` vắng mặt**, và có `jdk.jfr` không đồng nghĩa đã có file `jfr` tool hoặc đủ quyền ghi recording. Kiểm từng capability riêng.

### 6.1 Các lựa chọn hợp lệ khi thiếu tool

1. **Không thay đổi image**: dùng logs, JMX/MXBeans đã tích hợp, in-process diagnostics, JFR tại JVM startup nếu module hỗ trợ; lưu file trên writable mount.
2. **Dùng image/tooling cho môi trường staging**: chạy lại workload dưới image JDK đầy đủ để tái hiện, giữ cùng JDK vendor/version, GC, flags và constraints quan trọng. Đây là phép thử mới, không phải dữ liệu trực tiếp của process production.
3. **Tạo bản debug/deployment có kiểm soát**: theo quy trình vận hành, thêm công cụ cần thiết vào image hoặc môi trường có quyền tương ứng; không cài trực tiếp package vào production image bất biến.
4. **Ephemeral debug container** (Kubernetes): cung cấp shell/JDK tools cho quá trình điều tra **khi chính sách cho phép**, nhưng phải xác minh PID, effective user/group, mount/attach socket và version. Có tool trong sidecar **không bảo đảm** attach đến app image khác.
5. **API quản lý từ xa đã được bảo vệ**: JMX/`FlightRecorderMXBean` nếu JVM/module cho phép và có xác thực/TLS; không bật cổng mở toàn mạng để đổi lấy vài metric.

**Không xem `jhsdb` là “jcmd thay thế luôn thành công”.** Serviceability Agent/ptrace có yêu cầu OS privileges, có thể tạm dừng process hoặc tăng tác động và có điều kiện tương thích khắt khe. Chỉ chọn khi phương án nhẹ hơn thất bại, có người vận hành phê duyệt và hiểu rủi ro.

## 7. Thực hành Java 17+: thu thập MXBeans ngay trong process, không attach và không file

Nếu bạn có khả năng thêm code vào ứng dụng hoặc chạy một chương trình diagnostic riêng **trong đúng JVM cần quan sát**, `java.lang.management` cung cấp nhiều metric mà không cần `jcmd`, JNI hay file system. Ví dụ dưới đây dùng:

- `MemoryMXBean` để đọc `getHeapMemoryUsage().getUsed()`.
- `ThreadMXBean` để lấy thread count và một thread snapshot `dumpAllThreads(false, false)`.
- `ClassLoadingMXBean` để xem số lớp đang loaded.

Mã chỉ in những **điều kiện xác nhận** có giá trị ổn định thay vì hard-code số thread, heap bytes hoặc class count vốn khác giữa JVMs. Trong ứng dụng thật, bạn sẽ gửi số đo cụ thể ra **metrics endpoint/stdout** theo chính sách quan sát.

Lưu đúng tên **NoAttachSnapshot.java**:

~~~java
import java.lang.management.ClassLoadingMXBean;
import java.lang.management.ManagementFactory;
import java.lang.management.MemoryMXBean;
import java.lang.management.ThreadInfo;
import java.lang.management.ThreadMXBean;

public final class NoAttachSnapshot {
    public static void main(String[] args) {
        MemoryMXBean memory = ManagementFactory.getMemoryMXBean();
        ThreadMXBean threads = ManagementFactory.getThreadMXBean();
        ClassLoadingMXBean classes = ManagementFactory.getClassLoadingMXBean();

        long heapUsed = memory.getHeapMemoryUsage().getUsed();
        int threadCount = threads.getThreadCount();
        int loadedCount = classes.getLoadedClassCount();
        ThreadInfo[] snapshot = threads.dumpAllThreads(false, false);

        System.out.println("HEAP_USED_NONNEGATIVE=" + (heapUsed >= 0));
        System.out.println("THREAD_COUNT_POSITIVE=" + (threadCount > 0));
        System.out.println("LOADED_CLASSES_POSITIVE=" + (loadedCount > 0));
        System.out.println("THREAD_SNAPSHOT_NONEMPTY=" + (snapshot.length > 0));
        System.out.println("NO_JCMD_REQUIRED");
    }
}
~~~

Biên dịch và chạy (trong môi trường build có JDK 17+):

~~~sh
javac --release 17 NoAttachSnapshot.java
java NoAttachSnapshot
~~~

**Stdout chính xác** trong lần chạy kiểm thử HotSpot JDK 24:

~~~text
HEAP_USED_NONNEGATIVE=true
THREAD_COUNT_POSITIVE=true
LOADED_CLASSES_POSITIVE=true
THREAD_SNAPSHOT_NONEMPTY=true
NO_JCMD_REQUIRED
~~~

Có thể thử **cấm attach từ startup** nhưng chương trình vẫn chạy bình thường:

~~~sh
java -XX:+DisableAttachMechanism NoAttachSnapshot
~~~

Mã trên **không gọi** `jcmd`, không dùng Attach API và không tạo file. Nó chỉ kiểm tra các giá trị quan sát được, **không phải profiler đủ để xác định memory leak**. Trong production, nên đọc và xuất số thật (heap used/committed, thread states, loaded classes) tại một endpoint đã xác thực hoặc metrics pipeline; `dumpAllThreads(false,false)` có thể tốn tài nguyên khi có rất nhiều thread, nên không chạy liên tục với tần suất cao.

**Lưu ý về môi trường:** ứng dụng cần module `java.management`; trong runtime image jlink cực nhỏ không chứa module này, chương trình sẽ không chạy cho đến khi build image có module tương ứng. Không thể lấy dữ liệu **của process production khác** bằng cách chạy `NoAttachSnapshot` như một process mới: mỗi JVM chỉ tự đọc số liệu **của chính nó**. Phải tích hợp vào JVM cần quan sát từ trước hoặc có cơ chế agent/management được triển khai hợp lệ.

### 7.1 Ví dụ sử dụng đúng mục đích trong service

Nếu service đã expose metrics, có thể thêm phép đo:

~~~java
long heapUsed = ManagementFactory.getMemoryMXBean()
        .getHeapMemoryUsage().getUsed();
int threads = ManagementFactory.getThreadMXBean().getThreadCount();
~~~

Đây là **Java snippet**, không phải program độc lập. Dùng hệ thống metrics để gửi những giá trị này với labels về JVM start time, instance ID, pod và deployment version. Không lưu thread dump hay full stack trace vào một metrics label: vừa nhạy cảm, vừa có thể gây cardinality rất lớn.

## 8. Thu JFR từ startup khi attach bị cấm

JFR có thể chạy **không cần `jcmd`** nếu được bật bằng JVM flags ngay từ lúc khởi động và runtime có module/hỗ trợ tương ứng. Lúc này cần hai lớp đường dẫn có khả năng ghi:

1. **Repository tạm** chứa JFR chunks nếu recording ghi xuống disk.
2. **Final filename** được xuất khi recording dừng/dump.

Ví dụ HotSpot JDK 17+ khi có `/diagnostics/jfr-repo` và `/diagnostics` writable:

~~~sh
java \
  -XX:FlightRecorderOptions=repository=/diagnostics/jfr-repo \
  -XX:StartFlightRecording=settings=default,filename=/diagnostics/incident.jfr,dumponexit=true,maxsize=32m \
  -jar app.jar
~~~

- `settings=default` chọn profile theo dõi phù hợp tương đối dài; không cần bật mọi event.
- `maxsize=32m` giới hạn **dữ liệu giữ lại trong recording**; file và repository vẫn cần dung lượng thực và quota cho overhead, nên không xem 32 MiB là quota tuyệt đối của tất cả tệp.
- `dumponexit=true` yêu cầu export khi JVM **shutdown có cơ hội xử lý**; process bị `SIGKILL` hoặc cgroup OOM kill có thể không kịp dump.
- Nếu cần lấy bản ghi **khi process vẫn chạy**, phải có đường điều khiển được thiết kế trước (như `jdk.jfr.Recording` trong app, management API có bảo vệ hoặc attach được phép). Không kỳ vọng flag `dumponexit` tự tạo file mới mỗi khi thấy latency tăng.
- File `incident.jfr` nằm trong filesystem mà **JVM nhìn thấy**, không tự động có trên terminal gọi `kubectl` hay máy operator.
- Cần cân nhắc permission, mount durability và thời điểm thu; container bị xóa có thể làm mất file trên `emptyDir`.

Một thí nghiệm local với HotSpot JDK 24 đã chạy JVM có cả `-XX:FlightRecorderOptions=repository=...` và `-XX:StartFlightRecording=...`, tạo được file `.jfr` rồi đọc bằng `jfr summary`. Đây là xác minh cú pháp/chế độ trong môi trường có JDK; **không chứng minh mọi image readonly sẽ thành công** nếu mount hoặc module khác.

### 8.1 Không có `jfr` trong image vẫn đọc được file bằng máy khác

Sau khi copy bản ghi ra một môi trường phân tích có JDK tương thích và quyền truy cập phù hợp, chạy:

~~~sh
jfr summary incident.jfr
jfr print --events jdk.GarbageCollection incident.jfr
~~~

Hoặc mở trong JDK Mission Control. Trên môi trường phân tích, cần xem metadata/event types thực tế; nếu ứng dụng không có `jfr` tool tại runtime thì **đây không phải lý do để bỏ thu** nếu VM đã ghi được file. Đừng thay `.jfr` bằng `.jfc`: file `.jfc` chỉ là cấu hình.

### 8.2 Cân nhắc JFR và disk bất biến

Một root filesystem readonly nhưng repository được mount writable riêng vẫn có thể chạy JFR. Ngược lại, nếu toàn bộ nơi JVM có thể ghi đều bị khóa, **không nên mặc định JFR disk recording hoặc dump vào file sẽ hoạt động**. Một số trường hợp có thể thu dữ liệu dạng streaming/memory trong process, nhưng tính khả dụng và cơ chế truy xuất phụ thuộc phiên bản/JVM và cách bạn đã tích hợp; không dùng `disk=false` như “cách chắc chắn tạo được .jfr mà không có filesystem”.

Nếu không thể tạo vùng writable, ưu tiên **metrics/JMX đã có, stdout/stderr logging, in-process thread snapshots** và công cụ bên ngoài dựa trên quyền hợp lệ. Khả năng thu JFR hậu kiểm nên được thiết kế trong deployment ngay từ đầu.

## 9. Mẫu Kubernetes: root readonly nhưng vẫn có chỗ ghi diagnostics

Dưới đây là **mảnh YAML minh họa** trong một Pod template, không phải Deployment hoàn chỉnh:

~~~yaml
spec:
  securityContext:
    fsGroup: 10001
  containers:
    - name: app
      image: example/java-service:1.0
      securityContext:
        runAsNonRoot: true
        runAsUser: 10001
        readOnlyRootFilesystem: true
      volumeMounts:
        - name: tmp
          mountPath: /tmp
        - name: diagnostics
          mountPath: /diagnostics
  volumes:
    - name: tmp
      emptyDir:
        sizeLimit: 128Mi
    - name: diagnostics
      emptyDir:
        sizeLimit: 1Gi
~~~

Đây là thiết kế **giữ root filesystem readonly** nhưng mount `/tmp` và `/diagnostics` riêng. Cần điều chỉnh theo PodSecurity policy, storage class/permissions, UID/GID, tài nguyên node và nhu cầu lưu dữ liệu. `fsGroup` **không bảo đảm tất cả volume driver/permission case sẽ hoạt động**; vẫn phải kiểm quyền ghi bằng effective user của tiến trình JVM.

**Quan trọng với `emptyDir`:**

- Dữ liệu thuộc vòng đời Pod, không phải nơi lưu bền vững khi Pod bị xóa; phải chuyển file sang storage được phê duyệt trước khi mất Pod.
- `emptyDir.sizeLimit` là một giới hạn lưu trữ, không phải bảo đảm node luôn có đủ không gian hay IOPS.
- Nếu dùng `emptyDir.medium: Memory` thì dữ liệu dùng tài nguyên bộ nhớ của node/container theo quy tắc Kubernetes; với heap dump lớn, tránh dùng tmpfs tùy tiện.
- Volume mount có thể bị giới hạn bởi chính sách; ghi nhận cách cấu hình thực tế thay vì suy luận từ YAML dự kiến.

Các file `.hprof`, `.jfr` và `hs_err_pid...log` có thể chứa dữ liệu nhạy cảm. Chỉ copy ra nơi có ACL/retention phù hợp, ghi audit, xóa theo chính sách sau khi điều tra.

### 9.1 Thu JFR rồi lấy file ra ngoài

Khi service đã ghi vào `/diagnostics` và tổ chức cho phép:

~~~sh
# Ví dụ khái niệm, thay namespace/pod/container/path theo môi trường thật:
kubectl cp -n team payments-0:/diagnostics/incident.jfr ./incident.jfr -c app
~~~

`kubectl cp` có thể yêu cầu `tar` trong container; distroless/minimal image có thể **không có tar**, nên lệnh thất bại dù file tồn tại. Không tự kết luận file không có. Có thể dùng cách copy được vận hành cho phép (volume extraction, storage upload từ app/sidecar, hoặc luồng `kubectl exec -- cat` khi container thực sự có binary và chính sách cho phép). Chọn phương pháp có thể kiểm checksum/kích thước file và không làm lộ dữ liệu nhạy cảm ra log công khai.

## 10. Debug/ephemeral container có JDK tools: hữu ích nhưng không phải phép màu

Nếu application image không có shell/`jcmd`, Kubernetes hỗ trợ debug container tạm:

~~~sh
# Lệnh minh họa; image JDK phải được tổ chức cho phép:
kubectl debug -n team -it pod/payments-0 \
  --image=example/approved-jdk-tools:21 \
  --target=app -- sh
~~~

Lệnh tạo ephemeral container nhắm tới `app`, nhưng khả năng nhìn thấy process của container đích phụ thuộc hỗ trợ của container runtime và policy. Kubernetes ghi rõ nếu không thấy process, có thể do runtime không hỗ trợ targeting tương ứng.

Ngay cả khi đã nhìn thấy PID:

- **PID namespace**: tool có thể thấy process nhưng PID trong context không khớp kỳ vọng của JVM; xác minh `ps`/`/proc`.
- **Effective user/group**: debug container có thể chạy UID khác app; không tự tăng đặc quyền để ép attach.
- **Filesystem/mount namespace**: debug container có image và mounts riêng. Thư mục `/tmp` và attach socket của app có thể **không** hiện ở cùng đường dẫn; muốn attach thực sự phải thỏa cơ chế của JVM đó.
- **JDK version/vendor**: lựa chọn binary phù hợp với target JVM khi có thể.
- **Security policy**: PodSecurity/OPA/RBAC/Admission có thể cấm hoặc giới hạn ephemeral container. Quyền cluster để tạo debug container là quyền nhạy cảm.
- **Output paths**: chạy `jcmd ... JFR.dump filename=...` yêu cầu **JVM đích** có thể ghi path; file không nhất thiết được ghi vào filesystem của ephemeral container.

**Không biến mọi incident thành Pod privileged hoặc `--profile=sysadmin`.** Những tùy chọn này có tác động bảo mật lớn và không tự chữa lỗi sai namespace/temp/socket. Chỉ dùng profile/permission cao theo quy trình phê duyệt với phạm vi hẹp, có audit và thời hạn.

## 11. Bảng lỗi → chẩn đoán → hướng khắc phục

| Dấu hiệu | Lớp vấn đề thường gặp | Cách xác minh an toàn | Giải pháp ít xâm lấn |
| --- | --- | --- | --- |
| `jcmd: command not found` | Tool không đóng gói/PATH | Xem image/JDK runtime và `command -v` nếu có shell | MXBeans/logging/JFR startup; debug tooling được phê duyệt |
| `jcmd -l` không thấy JVM | PID namespace/container visibility hoặc JVM chưa sống | Xem process metadata, `/proc`, orchestrator | Dùng PID đúng context; không gửi lệnh bừa bằng PID 0 |
| `AttachNotSupportedException` | Attach disabled hoặc không thể kết nối | Kiểm startup flags, quyền, PID và trạng thái JVM | Không bypass; dùng in-process metrics hoặc startup capture |
| `Permission denied` khi attach | Sai UID/GID, security policy hoặc mount | So effective identities, process owner, policy | Chạy dưới identity được phép; không mặc định root/privileged |
| Attach timeout | JVM không phản hồi, temp/socket lỗi, process mismatch | Kiểm timestamps, JVM còn sống, `/tmp`, load | Thu stdout/OS metrics/SIGQUIT nếu hợp lệ, tránh attach lặp liên tục |
| `Read-only file system` khi dump | Output path hoặc JFR repository readonly | Kiểm mount thực tế và user JVM, thử file scoped | Đổi sang writable volume/stdout, chuẩn bị paths từ deploy |
| `No space left on device` | Disk/inode/quota đầy | `df -h`, `df -i`, volume usage | Dừng dump lớn, giảm retention/di chuyển dữ liệu theo chính sách |
| `JFR.dump` báo file không ghi được dù attach OK | JVM đích không có quyền path | Kiểm filesystem của **target JVM** | Chọn output writable mà target nhìn thấy |
| Không tạo được `.hprof` sau OOMKill | Process bị kill trước khi Java xử lý | Xem Pod/container termination reason và logs | Dùng JFR/metrics trước OOM, tăng observability ở lần deploy sau |
| `jfr: not found` nhưng đã có `.jfr` | Thiếu **tool phân tích**, không phải lỗi dữ liệu | Kiểm file size và magic/đọc bằng JDK tương thích bên ngoài | Copy qua môi trường phân tích an toàn, dùng `jfr summary`/JMC |
| Không có file sau `dumponexit=true` | Chưa shutdown có kiểm soát, wrong path, readonly/quota | Kiểm VM exit mode, output/repository, flags | Thu snapshot qua API/management trước khi process mất |
| `kill -QUIT` không cho dump | Sai PID/quyền, `-Xrs` hoặc signal handling khác | Kiểm cờ JVM và logs của process đích | MXBean/in-process debug hoặc phương pháp đã cho phép khác |

Tất cả các hàng trên là **các khả năng**, không phải mệnh đề “một lỗi luôn có một nguyên nhân”. Đặc biệt, error message của `jcmd` phụ thuộc JDK/OS: lưu nguyên văn và kèm phiên bản.

## 12. Ba kịch bản vận hành: chọn chiến lược thu thập

### Kịch bản A — distroless, JVM chạy ổn nhưng có latency spikes

**Bối cảnh:** app container thiếu `sh`, `jcmd` và `jfr`, root filesystem readonly; metric request latency, GC logs và metrics từ ứng dụng đang sẵn.

**Cách làm:**

1. Thu timeline request p99, CPU, GC pauses, container throttling, heap/thread metrics đã có.
2. Không cố `kubectl exec -- sh` rồi lặp lại khi shell thật sự không có; kiểm deployment image.
3. Nếu cần thread state, tích hợp endpoint diagnostic có xác thực dùng `ThreadMXBean.dumpAllThreads(...)` với rate limit; hoặc triển khai lại khi có cửa sổ bảo trì với startup JFR + writable volume.
4. Khi tái hiện, lấy nhiều snapshot có timestamp; so stack của thread ở cùng request, không dựa vào một điểm.
5. Giữ hardening và audit, không mở JDWP/JMX không bảo vệ.

**Kết luận:** thiếu JDK tools trong image không ngăn quan sát bằng ứng dụng/OS metrics; việc phải deploy lại để bật thêm bằng chứng nên là quyết định có kiểm soát.

### Kịch bản B — `jcmd` có mặt nhưng attach bị khóa theo policy

**Bối cảnh:** image có `jcmd`, PID đúng, cùng UID, nhưng JVM khởi động với `-XX:+DisableAttachMechanism`.

**Cách làm:**

1. Lưu error text, startup args và policy: đây có thể là hardening có chủ đích, **không phải lỗi ngẫu nhiên**.
2. Dùng console logs, JFR startup đã có, metrics/JMX được quản lý hợp lệ.
3. Nếu cần thay đổi policy, yêu cầu phê duyệt và triển khai thay JVM startup flags trong lần release sau; không dựa vào runtime attach để “bật lại”.
4. Sau khi được phép, thử `jcmd <pid> VM.version` trên staging trước rồi mới những command tác động cao hơn.

**Kết luận:** mục tiêu là bảo toàn bằng chứng và không phá security boundary, không phải bằng mọi giá làm `jcmd` hoạt động.

### Kịch bản C — attach thành công nhưng không ghi được heap dump/JFR

**Bối cảnh:** `jcmd <pid> Thread.print` thành công, nhưng `jcmd <pid> GC.heap_dump ...`/`JFR.dump` báo readonly hoặc thiếu disk.

**Cách làm:**

1. Phân loại đây là **I/O output path**, không phải lỗi attach.
2. Kiểm mount/UID/GID/quota trong **filesystem của target JVM**; tìm volume writable đã được cấp.
3. Nếu không có chỗ ghi, ưu tiên thread print ra command response, metrics và stdout GC logs; không đẩy heap dump vào `/tmp` chỉ vì có một chút dung lượng.
4. Lập kế hoạch volume có dung lượng/retention bảo mật, giới hạn hoặc tạm dừng những lệnh tạo file lớn.
5. Với lần triển khai sau, cấu hình `HeapDumpPath`, `ErrorFile` và JFR repository/output chính xác từ startup.

**Kết luận:** một command không phải lúc nào cũng cần file (ví dụ `Thread.print` trả text), nhưng những artefact lớn cần cả quyền, disk và kế hoạch lưu trữ.

## 13. Runbook thu thập chứng cứ có khả năng kiểm toán

Một phiếu đơn giản để các điều tra viên khác tái hiện và kiểm tra chéo:

~~~text
Incident ID / thời điểm UTC / timezone:
Namespace, Pod, container, node (nếu có):
JVM PID trong namespace nào / JVM start time:
Java vendor/version, GC, flags liên quan:
Image/runtime (full JDK, jlink, distroless):
Target JVM effective UID/GID:
Tool được gọi ở host/container nào, UID/GID nào:
Lệnh và output/error nguyên văn:
Attach: enabled/disabled/unknown; kết quả VM.version nếu thử:
Mount /tmp, JFR repository, output folder: rw/ro và owner:
Dung lượng/inode/quota:
Nguồn dữ liệu thu được: logs, JMX, JFR, thread, OS metrics:
Nơi lưu artifact, checksum, quyền truy cập, retention:
Ảnh hưởng lên latency/CPU/disk và thời gian thu:
Hạn chế và những dữ liệu vẫn còn thiếu:
Giả thuyết tiếp theo / tiêu chí bác bỏ:
~~~

**Ưu tiên thu thập theo mức tác động tăng dần:**

1. Logs, metrics, events đã có; bảo tồn timestamp/version.
2. MXBeans/app endpoints và `jcmd VM.version`/`Thread.print` (nếu attach được).
3. JFR profile có giới hạn duration/size, GC/safepoint logs theo target; quan sát overhead.
4. Heap dump hoặc diagnostic sâu hơn chỉ khi cần bằng chứng object/retention và đã duyệt impact, dung lượng, dữ liệu nhạy cảm.
5. Post-mortem core/SA debugging là lựa chọn đặc biệt, không phải bước mặc định.

Không thay đổi nhiều yếu tố cùng lúc (root permission, JVM flags, image, pod placement, collector): nếu vấn đề biến mất sẽ khó biết điều gì thật sự cải thiện. Với điều tra sau sự cố, **đừng khởi động lại sớm** làm mất evidence chưa được thu, trừ khi khôi phục dịch vụ là ưu tiên an toàn/vận hành rõ ràng.

## 14. Những sai lầm thường gặp

1. **“`jcmd -l` trống nghĩa là không có JVM.”** Có thể do container/PID visibility hoặc quyền.
2. **“Có `java` là chắc chắn có `jcmd`.”** Runtime image tối giản có thể bỏ công cụ.
3. **“Chạy root hoặc privileged chắc chắn giải quyết attach.”** Namespace/socket/policy/compatibility vẫn có thể khiến thất bại; tăng quyền còn gây rủi ro.
4. **“Tắt `DisableAttachMechanism` bằng `jcmd` ngay lúc JVM đang chạy.”** Chính cơ chế attach có thể đã bị vô hiệu hóa từ startup.
5. **“`-Djava.io.tmpdir` chắc chắn sửa attach.”** Attach implementation có quy tắc socket/temp riêng; phải xác minh đúng JVM/JDK.
6. **“Root filesystem readonly đồng nghĩa mọi mount readonly.”** Writable volumes có thể tồn tại nếu được cấu hình.
7. **“`JFR.dump filename=...` ghi file vào máy của người gọi.”** File được JVM đích ghi theo filesystem mà JVM thấy.
8. **“Có `filename` writable là JFR repository chắc chắn writable.”** Output cuối và scratch/repository là hai nơi khác nhau.
9. **“`dumponexit=true` bảo đảm có dump sau `SIGKILL`/OOMKill.”** Kill cưỡng bức có thể không cho JVM thực hiện dump.
10. **“Khi không có JDK tools, phải mở remote JMX/JDWP công khai.”** Có thể dùng metrics/JFR startup; debug ports phải được bảo vệ.
11. **“Dùng debug container có `jcmd` thì attach thành công 100%.”** Cần PID/mount/user/security và JVM compatibility.
12. **“`emptyDir` là nơi lưu trữ dài hạn.”** Dữ liệu có thể mất khi Pod bị xóa; cần export hợp lệ.
13. **“`kill -QUIT` giống `kill -9`.”** Là các tín hiệu khác nhau; với HotSpot/Linux, SIGQUIT thường dùng in thread dump, không mặc định kết thúc ứng dụng.
14. **“Không thu được heap dump nghĩa là không có heap leak.”** Thiếu artifact không chứng minh điều gì về nguyên nhân.
15. **“Thu được snapshot là chắc chắn đủ phân tích.”** Cần đối chiếu workload, timestamps, retained data và tính đại diện.
16. **“Không cần bảo vệ JFR/heap dump vì chỉ là diagnostics.”** Dữ liệu có thể chứa thông tin nội bộ/nhạy cảm.

## 15. Bài tập vận dụng có lời giải

**Bài A.** Bạn dùng image distroless, `kubectl exec ... -- jcmd` báo executable không tồn tại. Service vẫn xuất metrics GC/thread. Điều gì cần làm trước?

**Giải:** Dựa vào metrics/logs đã có, phân loại thiếu tool trong image; không tăng quyền hoặc thay container chỉ để tìm một binary không tồn tại. Nếu thiếu bằng chứng, lên kế hoạch dùng debug image phù hợp hoặc startup JFR + writable volume theo chính sách.

**Bài B.** JVM PID 1 chạy với UID 10001. `jcmd` trong debug sidecar chạy UID 0 và nhìn thấy PID 1 nhưng attach thất bại. Có thể kết luận JVM hỏng?

**Giải:** Chưa. Kiểm effective UID/GID, namespace và cách mount `/tmp`/socket, security policy, compat JDK và startup attach flag. PID visibility chỉ là một điều kiện. Chạy privileged không phải biện pháp mặc định.

**Bài C.** `jcmd 1234 Thread.print` trả stack, nhưng `JFR.dump filename=/app/problem.jfr` báo `Read-only file system`. Cần sửa lỗi attach?

**Giải:** Không. Attach đã thành công. Đổi đường dẫn đầu ra sang mount được **JVM đích** phép ghi, bảo đảm repo/output và dung lượng theo nhu cầu; hoặc dùng phương án stdout/metrics nếu không có volume phù hợp.

**Bài D.** Có `-XX:+HeapDumpOnOutOfMemoryError`, nhưng Pod kết thúc với reason OOMKilled và không có `.hprof`. Có thể khẳng định không xảy ra vấn đề bộ nhớ Java?

**Giải:** Không. Cgroup OOM kill có thể kết thúc tiến trình trước khi JVM tự phát hiện Java `OutOfMemoryError` và dump. Cần đối chiếu cgroup memory, OS RSS, heap metrics/GC logs và startup recording nếu có.

**Bài E.** Một JVM khởi động với `-XX:+DisableAttachMechanism`, trong khi `NoAttachSnapshot` vẫn in `NO_JCMD_REQUIRED`. Có mâu thuẫn?

**Giải:** Không. MXBeans hoạt động **bên trong** JVM và không cần Attach API từ process ngoài. Chỉ số của nó không tự đại diện cho mọi JVM khác.

**Bài F.** Một debug container có `jfr` command nhưng ứng dụng không có JFR module và không có file `.jfr`. Có thể dùng lệnh `jfr` bên ngoài để “bắt đầu ghi” trong app không?

**Giải:** Không. `jfr` là công cụ quản lý/đọc file recording, không thay thế năng lực JFR của **target runtime** và không tự tạo các sự kiện mà JVM không hỗ trợ. Muốn thu cần JVM có JFR và cơ chế khởi động/điều khiển hợp lệ.

**Bài G.** Mọi đường dẫn ghi trong image bị khóa, nhưng hệ thống đã cấu hình `-Xlog:gc=info:stdout:...`. Có thể thu GC logs không?

**Giải:** Có, nếu HotSpot hỗ trợ flag và logging pipeline đang thu stdout. Dữ liệu đi qua stream, không yêu cầu app ghi GC log vào file trong root filesystem. Nhưng pipeline phải đủ retention/quota và không mất log.

**Bài H.** SRE gửi `kill -QUIT` trên Linux khi JVM có `-Xrs` và không thấy thread dump. Có thể tiếp tục spam signal để “ép” chưa?

**Giải:** Không. `-Xrs` có thể tắt handler SIGQUIT; cần xem cấu hình JVM và chính sách hệ điều hành, rồi chuyển sang MXBeans/metrics/JFR có kế hoạch. Gửi tín hiệu lặp không tạo thêm quyền hay khả năng.

## 16. Ghi nhớ bằng ba câu hỏi

1. **Không attach được vì sao?** Kiểm PID, namespace, effective UID/GID, attach flag, temp/socket, JVM responsiveness và policy; đừng tự động dùng root.
2. **Không ghi file được ở đâu?** Phân biệt root readonly, mount, JFR repository, output file, disk/inode và user JVM; ưu tiên stdout hoặc volume bảo mật.
3. **Không có JDK tools thì còn gì?** Sử dụng in-process MXBeans, application/JMX metrics đã được bảo vệ, JFR startup/API nếu có, GC stdout, OS/orchestrator evidence và debug container được phê duyệt.

**Mục tiêu vận hành không phải “làm cho mọi lệnh chạy được”, mà là “thu đúng bằng chứng với đặc quyền thấp nhất, tác động chấp nhận được và khả năng xác minh rõ ràng”.**

### Tài liệu tham khảo chính thức

- Oracle Java 21, `The jcmd Command`: https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html
- Oracle Java 21, `The java Command` (`-Xlog`, `-XX:StartFlightRecording`, `-XX:FlightRecorderOptions`, heap/fatal logs): https://docs.oracle.com/en/java/javase/21/docs/specs/man/java.html
- Oracle Java 21, `Diagnostic Tools`: https://docs.oracle.com/en/java/javase/21/troubleshoot/diagnostic-tools.html
- Oracle Java 21, `Prepare Java for Troubleshooting`: https://docs.oracle.com/en/java/javase/21/troubleshoot/prepare-java-troubleshooting.html
- Oracle Java 21, `Flight Recorder Configurations`: https://docs.oracle.com/en/java/javase/21/jfapi/flight-recorder-configurations.html
- Oracle Java 21 API, `ThreadMXBean`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/java/lang/management/ThreadMXBean.html
- Oracle Java 21 API, `MemoryMXBean`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/java/lang/management/MemoryMXBean.html
- Kubernetes, `kubectl debug`: https://kubernetes.io/docs/reference/kubectl/generated/kubectl_debug/
- Kubernetes, `Debug Running Pods`: https://kubernetes.io/docs/tasks/debug/debug-application/debug-running-pod/
