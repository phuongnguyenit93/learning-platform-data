# 3.1 — Nhận diện đúng JVM bằng PID, lệnh khởi chạy, thời điểm bắt đầu và người sở hữu

## 1. Vấn đề cần giải quyết

Trên một máy chủ có thể đồng thời chạy nhiều Java Virtual Machine (JVM): API, batch job, công cụ build, chương trình thử nghiệm, agent giám sát hoặc hai phiên bản ứng dụng trong lúc triển khai. Chúng có thể cùng hiện tên tiến trình `java` hoặc cùng sử dụng một file `.jar`. Nếu chọn nhầm tiến trình để lấy thread dump, JFR, heap dump hoặc thực hiện thao tác quản trị, kết quả điều tra sẽ sai; một thao tác tốn tài nguyên còn có thể ảnh hưởng dịch vụ khác.

**Mục tiêu của bài:** nhận diện **đúng phiên JVM đang chạy** và xác minh đồng thời bốn bằng chứng:

1. **PID (Process ID):** số định danh của tiến trình trong **một không gian PID cụ thể**.
2. **Lệnh khởi chạy:** executable Java, ứng dụng `-jar` hoặc main class, classpath và tham số liên quan.
3. **Thời điểm bắt đầu:** mốc tiến trình được tạo để phân biệt những lần chạy/restart khác nhau.
4. **Người sở hữu:** danh tính hệ điều hành đang sở hữu/vận hành tiến trình, dùng để kiểm tra đúng service và quyền chẩn đoán.

Bối cảnh **host/container/pod**, instance và mốc thời gian là phần bổ sung cần thiết khi các ứng dụng chạy phân tán.

> **Quy tắc an toàn:** Không chọn mục tiêu chỉ vì “PID trông quen”, tên `java`, đường dẫn JAR hoặc dòng đầu tiên trong `jcmd -l`. Hãy đối chiếu ít nhất PID + launch command + start time + owner, rồi kiểm tra lại khi sắp thực hiện lệnh chẩn đoán.

## 2. PID là định danh tạm thời, không phải danh tính vĩnh viễn

Hệ điều hành cấp PID cho tiến trình sống trong một phạm vi nhất định. Khi tiến trình kết thúc, PID **có thể được tái sử dụng**. Vì vậy, “PID 18432” được ghi trong log lúc 09:00 chưa chắc vẫn là cùng JVM lúc 11:00.

Một bản ghi định danh hữu ích có dạng:

| Thuộc tính | Ví dụ minh họa | Giá trị trong điều tra |
| --- | --- | --- |
| Host / node | `node-03` | Tránh nhầm cùng PID trên hai máy |
| Namespace / container / pod | `orders-api-7b6d...`, container `app` | Phân biệt PID nhìn từ host và từ container |
| PID / PPID | `18432` / `1` | Chọn tiến trình và lần theo launcher/parent |
| Start time (kèm timezone) | `2026-10-29T08:15:00Z` | Phân biệt phiên trước và sau restart |
| Owner | `svc-orders` | Đối chiếu user vận hành và quyền attach |
| Executable | `/opt/jdk-17/bin/java` | Kiểm tra tiến trình thực sự chạy Java nào |
| Launch command | `java -jar /srv/orders/orders-api.jar` | Liên hệ đúng ứng dụng/build |
| Service / deployment | `orders-api.service` / deployment `orders-api` | Ghép với giám sát và cấu hình triển khai |

**Bốn trường chính phải cùng khớp trong cùng một thời điểm.** Host và namespace xác định *PID được hiểu ở đâu*. Mốc bắt đầu xác định *phiên sống nào* của PID đó. Owner và command xác định *đúng tiến trình Java nào*. Khi hai JVM cùng chạy một JAR, cần thêm instance ID, cổng dịch vụ, service manager hoặc pod/container identity để phân biệt.

Các khái niệm dễ nhầm:

- **PID** là mã tiến trình hệ điều hành. **PPID** là PID của tiến trình cha; không phải mã JVM và không đảm bảo cha luôn còn sống.
- **Thread ID (TID)** trong thread dump là thông tin luồng; không thay thế PID của JVM.
- **Owner của tiến trình** là tài khoản hệ điều hành, khác với chủ sở hữu file `.jar`, tài khoản CI/CD hoặc người viết code.
- **Start time** là lúc *tiến trình hiện tại* được tạo, khác với thời điểm deploy, build, máy khởi động hoặc service lần đầu được đăng ký.

## 3. Trình tự điều tra: phát hiện → đối chiếu → xác nhận lại

Có thể dùng quy trình năm bước trên Linux, macOS hoặc Windows:

1. **Khoanh đúng máy và dịch vụ.** Từ cảnh báo, ghi host/node, namespace/pod nếu có, tên dịch vụ, phiên bản và thời gian sự cố.
2. **Lập danh sách JVM ứng viên.** Dùng công cụ JDK như `jcmd -l` hoặc danh sách process của hệ điều hành. Đây chỉ là bước *khám phá*.
3. **Đọc thông tin hệ điều hành của từng ứng viên.** Đối chiếu PID, parent PID, user, start time, executable và command line. Không nhầm Java launcher với shell/service wrapper.
4. **Xác nhận từ phía JVM khi có thể.** Dùng `jcmd <PID> VM.command_line`, `VM.version` và `VM.uptime` để kiểm tra Java command và phiên bản; ghi rõ nếu attach không được.
5. **Preflight lại ngay trước tác vụ chẩn đoán.** Đọc lại PID, start time và owner; nếu tiến trình đã biến mất hoặc start time khác, phải định danh lại từ đầu. Một PID đã được tái sử dụng không còn trỏ đến JVM ban đầu.

Ví dụ hồ sơ ghi nhận:

```text
incident_utc:   2026-10-29T08:32:00Z
node:           node-03
service:        orders-api
pid_namespace:  host
pid:            18432
ppid:           1
start_utc:      2026-10-29T08:15:00Z
owner:          svc-orders
executable:     /opt/jdk-17/bin/java
entrypoint:     -jar /srv/orders/orders-api.jar
verification:   OS process details + jcmd VM.command_line
```

Đây là **hồ sơ minh họa**, không phải output được sinh ra bởi một lệnh đơn lẻ. Với môi trường production, chỉ ghi/đính kèm launch arguments sau khi đã loại bỏ thông tin bí mật.

## 4. Linux: nhìn từ hệ điều hành trước khi attach

### 4.1. Tìm JVM ứng viên

Trong terminal trên **đúng host hoặc đúng PID namespace**, chạy:

```bash
jcmd -l
```

Với JDK có `jps`, có thể đối chiếu:

```bash
jps -lv
```

`jcmd -l` thường hiển thị PID và thông tin main class/JAR của JVM mà công cụ có thể nhìn thấy. `jps -l` dùng tên đầy đủ của main class hoặc đường dẫn JAR; `-v` hiển thị JVM arguments. **Đừng cho rằng danh sách này đầy đủ**: quyền truy cập, container PID namespace, JDK vendor, cấu hình attach/performance counters và tình trạng tiến trình có thể làm một JVM không hiện ra. Một lệnh không thấy ứng dụng **không chứng minh** JVM không chạy.

Có thể tìm từ process table ngay cả khi ứng dụng không hiện trong công cụ JDK:

```bash
ps -eo pid,ppid,user,lstart,etime,args
```

Lệnh `ps` này chỉ là bước liệt kê; lọc bằng thông tin service, account hoặc executable khi cần. Nhiều tiến trình Java có tên hiển thị `java` hoặc `javaw`, nhưng wrapper, symlink và cách trình bày command line có thể khác nhau.

### 4.2. Ghi nhận chi tiết một PID cụ thể

Giả sử ứng viên là PID `18432`. Với Linux dùng `procps`:

```bash
ps -ww -p 18432 -o pid,ppid,user,ruser,lstart,etimes,args
```

Ý nghĩa cột:

- `pid`: PID đang được hệ điều hành nhìn thấy.
- `ppid`: PID của parent, hỗ trợ tìm launcher hoặc service manager.
- `user`: user hiệu lực (effective user) theo cách `ps` trình bày; `ruser` là real user. Hai giá trị có thể khác nhau ở một số tiến trình.
- `lstart`: thời điểm bắt đầu tiến trình theo giờ địa phương của host; **phải ghi timezone** khi lưu chứng cứ.
- `etimes`: số giây tiến trình đã chạy tại thời điểm đọc; hữu ích để kiểm tra chéo start time. Trường này thuộc `procps` trên Linux, không mặc định có trên mọi Unix.
- `args`: command line nhìn từ OS. `-ww` yêu cầu hiển thị rộng, nhưng không đảm bảo mọi ký tự đều tồn tại/có quyền truy cập.

Xem chính xác executable mà kernel liên kết với tiến trình:

```bash
readlink -f /proc/18432/exe
```

Xem command-line arguments được kernel lưu với **ranh giới từng tham số** trên Linux:

```bash
tr '\0' '\n' < /proc/18432/cmdline
```

Trong `/proc/PID/cmdline`, các tham số được phân tách bằng byte NUL. Chuyển NUL thành newline giúp dễ nhận thấy từng argument (đặc biệt với đường dẫn có dấu cách); đây là dạng **hiển thị hỗ trợ phân tích**, không phải chuỗi shell có thể copy để chạy y nguyên. Tiến trình vẫn có thể thay đổi thông tin argv mà hệ điều hành hiển thị, và file có thể trống hoặc bị chặn quyền. Đừng xem argv là nguồn xác thực tuyệt đối.

Đọc thông tin tiến trình và UID trên Linux:

```bash
grep -E '^(Name|Pid|PPid|Uid|NSpid):' /proc/18432/status
```

`Uid` liệt kê lần lượt real, effective, saved-set và filesystem UID. `NSpid` có thể cho biết các PID tương ứng trong những namespace mà kernel hiển thị, hữu ích khi dùng container. Nếu `NSpid` chỉ có một số hoặc không có thông tin cần thiết, đừng tự suy đoán mapping.

**Các giới hạn của `/proc`:** tiến trình có thể kết thúc giữa hai lệnh; chính sách `hidepid`, container isolation và quyền người dùng có thể ngăn đọc; `readlink -f /proc/PID/exe` có thể thất bại hoặc chỉ ra executable đã bị xóa/thay thế. Không tăng quyền chỉ để “đọc cho bằng được” nếu không có quyền vận hành tương ứng.

### 4.3. Kiểm tra Java command thực sự của JVM mục tiêu

Khi đã xác nhận ứng viên bằng OS:

```bash
jcmd 18432 VM.command_line
jcmd 18432 VM.version
jcmd 18432 VM.uptime
```

- `VM.command_line` cho biết thông tin launch mà JVM ghi nhận, giúp đối chiếu `-jar`/main class và JVM flags. Một số cờ có thể đến từ môi trường hoặc cơ chế launcher, nên thông tin hiển thị có thể khác cách nhìn của `ps`.
- `VM.version` xác nhận phiên bản/runtime JVM đang chạy, đáng tin hơn việc gọi `java -version` trong shell: Java trên `PATH` **có thể không phải Java của tiến trình đích**.
- `VM.uptime` cho biết thời gian chạy của JVM; dùng để kiểm tra tính nhất quán với `lstart`/`etimes`, không thay thế mốc start time của OS.

Nếu chưa chắc command khả dụng ở JDK/vendor cụ thể, đọc:

```bash
jcmd 18432 help
```

**Điều kiện attach:** `jcmd` cần nhìn thấy tiến trình mục tiêu và có quyền phù hợp (trên các hệ thống HotSpot thường cần cùng effective user/group), cùng các cơ chế attach mà JVM/OS cho phép. Container, quyền, cấu hình bảo mật hoặc `-XX:+DisableAttachMechanism` có thể khiến attach thất bại. **Attach thất bại không chứng minh PID sai**: quay lại đối chiếu bằng OS/service manager, ghi rõ lý do thất bại và nhờ người vận hành có quyền hợp lệ khi cần.

**Tránh lệnh mở rộng mục tiêu ngoài ý muốn:** dùng PID cụ thể. Trong `jcmd`, PID `0` có ý nghĩa gửi lệnh đến tất cả Java processes có thể truy cập; không dùng nó cho một tác vụ kiểm tra đơn JVM.

## 5. Windows: PID, CreationDate, CommandLine và GetOwner

Trong Windows PowerShell có thể dùng Windows Management Instrumentation qua CIM. Ví dụ PID cần kiểm tra là `18432`:

```powershell
$targetPid = 18432
$proc = Get-CimInstance -ClassName Win32_Process -Filter "ProcessId = $targetPid"

if ($null -eq $proc) {
    throw "Process no longer exists"
}

$proc | Select-Object ProcessId, ParentProcessId, CreationDate, ExecutablePath, CommandLine
$proc.CreationDate.ToUniversalTime().ToString("o")

Invoke-CimMethod -InputObject $proc -MethodName GetOwner |
    Select-Object Domain, User, ReturnValue
```

Giải thích:

- `ProcessId` và `ParentProcessId` xác định process hiện tại và cha; có thể có nhiều Java khác nhau.
- `CreationDate` là thời điểm tạo tiến trình; dòng `ToUniversalTime().ToString("o")` giúp lưu mốc ISO 8601 UTC thay vì một chuỗi phụ thuộc ngôn ngữ hiển thị.
- `ExecutablePath` là đường dẫn executable nếu hệ thống cấp quyền đọc.
- `CommandLine` là command line của tiến trình; có thể trả về `null` khi thiếu quyền.
- `GetOwner` trả `Domain`/`User` và `ReturnValue`; kiểm tra mã trả về trước khi coi user là xác minh thành công (thông thường `0` chỉ thành công).

Có thể lấy start time từ object process:

```powershell
Get-Process -Id $targetPid |
    Select-Object Id, ProcessName, StartTime, Path
```

Đôi khi `StartTime` hoặc `Path` không đọc được do quyền; dùng CIM để kiểm tra chéo. **Tránh dùng biến `$PID` để lưu PID mục tiêu**: trong PowerShell, `$PID` là biến tự động chứa PID của chính tiến trình PowerShell và không phải biến gán tùy ý. Dùng tên `$targetPid`.

Nếu JDK tool đã cài và khả dụng, chạy `jcmd -l` rồi `jcmd 18432 VM.command_line` giống Linux. Khi JVM thuộc Windows service, có thể đối chiếu tên service và account cấu hình, nhưng service có thể là wrapper hoặc host của nhiều process; vẫn kiểm tra ProcessId và CreationDate của JVM thực.

## 6. macOS và các nền tảng Unix khác

Trên macOS, dùng `ps` để quan sát PID hiện tại:

```bash
ps -ww -p 18432 -o pid,ppid,user,lstart,etime,command
```

Sau đó dùng `jcmd -l` và `jcmd 18432 VM.command_line` nếu JDK/vận hành cho phép. Tên trường và tùy chọn `ps` khác nhau giữa GNU/Linux, BSD/macOS và BusyBox; ví dụ trên Linux có `etimes` không nhất thiết chạy trên macOS. Nếu tùy chọn không được hỗ trợ, xem `man ps` của chính hệ thống. **Không dùng `/proc/PID/cmdline` theo hướng dẫn Linux trên macOS** vì macOS không cung cấp cùng giao diện `procfs` mặc định.

## 7. Service manager, shell wrapper và ứng dụng có cùng tên

### 7.1. Linux systemd

Nếu hệ thống dùng systemd, lấy ngữ cảnh service:

```bash
systemctl show orders-api.service \
    -p MainPID -p User -p ExecStart -p ExecMainStartTimestamp
```

Sau đó đối chiếu `MainPID` với PID Java từ `ps` hoặc `jcmd`, và đối chiếu thời gian khởi động. Không mặc định rằng `MainPID` luôn là JVM: một launcher `sh`, script, wrapper hoặc process supervisor có thể là main process còn Java là child. Cờ `Type=`, `ExecStart=`, việc fork và cấu hình service có thể ảnh hưởng cây process.

Nếu nghi ngờ wrapper:

```bash
pstree -aps 18432
```

`pstree` chỉ có khi hệ thống cài công cụ tương ứng (thường từ gói `psmisc`). Kiểm tra parent chain để biết launcher nào sinh JVM. Một file unit có `User=svc-orders` là **cấu hình kỳ vọng**; `ps`/`Uid` vẫn cần xác nhận user thực tế của tiến trình.

### 7.2. Vì sao tên JAR hoặc tên main class chưa đủ?

Hai phiên JVM có thể cùng chạy:

```text
18432 svc-orders java -jar /srv/orders/orders-api.jar
18597 svc-orders java -jar /srv/orders/orders-api.jar
```

Cả hai đều khớp bằng tên JAR. Chỉ PID + tên file không cho biết instance nào nhận request đang chậm. Cần thêm start time, host/namespace, port, service identity, instance ID hoặc correlation với metrics. Không suy luận PID nhỏ hơn là bản cũ hay PID lớn hơn là bản mới: PID được hệ điều hành tái sử dụng và có thể wrap.

Tương tự, parent của JVM có thể là systemd, container init hoặc một process launcher đã thay đổi. `PPID=1` không chứng minh đây là ứng dụng duy nhất hay là JVM khởi động đầu tiên.

## 8. Container và Kubernetes: cùng JVM, nhiều góc nhìn PID

Trong container, PID phụ thuộc **PID namespace**. Một Java process có thể hiện PID `1` khi nhìn từ bên trong container, nhưng mang PID `31842` trên host Linux. Hai container khác nhau đều có thể nhìn thấy tiến trình nội bộ của mình là PID `1`. Nếu operator ghi “PID 1” mà bỏ container identity, chứng cứ gần như không thể ghép lại.

Cần ghi **node/host + pod UID + container name/ID + PID namespace + PID trong namespace tương ứng + start time + owner**. Không coi PID bên trong container là PID có thể dùng trực tiếp trên host.

Trên Kubernetes, ví dụ kiểm tra đúng pod/container:

```bash
kubectl get pod -n commerce orders-api-abc -o wide
kubectl describe pod -n commerce orders-api-abc
kubectl exec -n commerce orders-api-abc -c app -- jcmd -l
```

Các tên `commerce`, `orders-api-abc` và `app` ở đây **chỉ là ví dụ**, phải thay bằng namespace/pod/container thực tế. Lệnh cuối chỉ chạy nếu trong container có JDK với `jcmd` và quyền tương ứng. Ảnh runtime tối giản có thể không có `ps`, `jcmd`, shell hay đủ quyền; khi đó dùng dữ liệu từ service orchestrator/host hoặc quy trình debug được vận hành phê duyệt, **không đoán** container PID.

Thông tin cần phân biệt:

- **Pod age / pod creation time:** tuổi của pod, **không phải** start time của JVM; container có thể đã restart trong cùng pod.
- **Container restart count / container ID:** cho thấy lần khởi động container; dùng để đối chiếu với mốc JVM restart.
- **PID trong container:** có thể là `1` nếu JVM là entrypoint, hoặc là child của shell/`tini`; xem process thực tế.
- **PID trên node:** khác PID nhìn từ container nếu có PID namespace riêng; Linux `/proc/PID/status` có thể chứa `NSpid` để hỗ trợ ánh xạ, nhưng phải đọc từ góc nhìn namespace thích hợp.
- **Container user:** UID được image/pod cấu hình có thể chịu user namespace mapping; đừng mặc định UID `0` trong container đồng nghĩa root không giới hạn trên host.

Một output `jcmd -l` từ host không tìm thấy JVM trong container **chưa phải** bằng chứng JVM không tồn tại. Cần tìm từ **đúng nơi quan sát**, nhất là khi incident được báo theo pod.

## 9. Tự nhận diện JVM trong Java 17+ bằng ProcessHandle

Khi có quyền sửa ứng dụng hoặc tạo chương trình demo, Java cung cấp `ProcessHandle.current()` và `ProcessHandle.Info` từ Java 9. Đây là cách hữu ích để ghi PID và thời điểm bắt đầu **từ chính process đang chạy**, phục vụ đối chiếu với log/metrics và OS.

Tạo file **`JvmIdentityDemo.java`**:

```java
public class JvmIdentityDemo {
    public static void main(String[] args) throws InterruptedException {
        ProcessHandle self = ProcessHandle.current();
        ProcessHandle.Info info = self.info();

        System.out.println("pid=" + self.pid());
        System.out.println("start_utc=" + info.startInstant()
                .map(Object::toString).orElse("<unavailable>"));
        System.out.println("owner=" + info.user().orElse("<unavailable>"));
        System.out.println("command=" + info.command().orElse("<unavailable>"));

        if (args.length > 0 && "--stay".equals(args[0])) {
            Thread.sleep(60_000);
        }
    }
}
```

Biên dịch và chạy bằng JDK 17+:

```bash
javac --release 17 JvmIdentityDemo.java
java JvmIdentityDemo
```

**Ví dụ hình thức stdout** (giá trị PID, start time, owner, executable là **biến thiên theo máy và lần chạy**, không phải chuỗi cố định):

```text
pid=18432
start_utc=2026-10-29T08:15:00.123Z
owner=svc-orders
command=/opt/jdk-17/bin/java
```

`startInstant()`, `user()` và `command()` trả về `Optional`; `<unavailable>` là kết quả hợp lệ khi hệ điều hành/JVM không cung cấp thông tin hoặc thiếu quyền. `Instant.toString()` hiển thị timestamp UTC với hậu tố `Z` nếu có. Chương trình cố ý **không** in toàn bộ arguments vì command line có thể chứa secrets.

Để có thời gian nhìn thấy tiến trình từ terminal khác, chạy:

```bash
java JvmIdentityDemo --stay
```

Lúc này chương trình in bốn dòng rồi chờ khoảng **60 giây**. Trong khoảng đó, lấy PID in ra (ví dụ `18432`) và dùng `ps`/`jcmd 18432 VM.command_line` trên đúng host/namespace. Khi process kết thúc, PID đó không còn là định danh hợp lệ cho phiên JVM demo vừa chạy.

**Giới hạn:** `ProcessHandle.Info` cho biết thông tin từ cơ chế OS hỗ trợ, không chứng thực rằng “PID này chính là deployment X”. Muốn xác minh service identity phải ghép với app config, container/pod, runtime command, logs và hệ thống triển khai. Thông tin process có thể không truy cập được ở môi trường cô lập.

## 10. Chống nhầm PID sau restart: kiểm tra cùng một phiên sống

Một quy trình điều tra điển hình:

1. 08:31 — Cảnh báo heap tăng trên `orders-api` ở `node-03`.
2. 08:32 — `jcmd -l` và `ps` phát hiện PID `18432`; xác nhận owner `svc-orders`, start `08:15Z`, lệnh khởi chạy đúng JAR.
3. 08:34 — JVM bị supervisor restart. Tiến trình cũ kết thúc; JVM mới có thể nhận PID khác hoặc, về sau, PID cũ được tái sử dụng.
4. 08:35 — Người điều tra định lấy heap dump theo PID đã lưu từ 08:32. **Không thực hiện ngay**: đọc lại process details. Nếu start time không còn khớp hoặc PID đã mất, phải tìm JVM phiên mới và ghi nhận thay đổi.

**Khóa nhận diện thực tế** nên là tổ hợp *(host/node, PID namespace, PID, process start time)*. Có thể thêm container ID, pod UID, owner và command fingerprint để tăng độ tin cậy. PID tái sử dụng là lý do quan trọng phải lưu **start time ở mỗi lần lấy bằng chứng**.

Với systemd/Kubernetes, kiểm tra dấu hiệu restart từ manager, đồng thời đối chiếu log bắt đầu process và JVM uptime. Sau restart, **PID, heap, thread pool, trạng thái cache và JFR recording đều có thể không liên tục**; không ghép dump của hai phiên thành một snapshot duy nhất.

### Cách đối chiếu không làm thay đổi ứng dụng

```bash
# Linux: chụp thông tin mục tiêu trước
ps -ww -p 18432 -o pid,ppid,user,lstart,etimes,args

# Thực hiện lệnh đọc thông tin JVM nếu quyền cho phép
jcmd 18432 VM.command_line

# Chụp lại: cùng PID nhưng start time thay đổi => không còn cùng phiên
ps -ww -p 18432 -o pid,ppid,user,lstart,etimes,args
```

Chuỗi này **giảm** nguy cơ nhầm PID, nhưng không loại bỏ hoàn toàn race giữa lúc kiểm tra và hành động; các lệnh không tạo một “khóa” nguyên tử trên process. Với tác vụ nặng hoặc nhạy cảm, ưu tiên quy trình chẩn đoán do đội vận hành kiểm soát và kiểm tra instance ID sát thời điểm thao tác.

## 11. Các lỗi chẩn đoán thường gặp

| Nhận định hoặc thao tác sai | Vì sao có thể sai | Cách làm đúng |
| --- | --- | --- |
| “`jcmd -l` chỉ có một dòng nên chắc chắn đúng service.” | JVM có thể nằm namespace khác, thiếu quyền hoặc tool không nhìn thấy. | Đối chiếu process table, host, owner và container. |
| “Ứng dụng chạy `orders-api.jar` nên chọn PID bất kỳ có JAR đó.” | Có thể có nhiều replica/canary/startup trùng JAR. | Ghép PID, start, host/pod và instance. |
| “PID trong alert hôm qua vẫn là PID hiện tại.” | PID có thể hết hiệu lực và được tái sử dụng. | Kiểm tra start time hiện tại trước thao tác. |
| “`java -version` trong terminal cho biết JDK của service.” | `PATH` trong shell có thể trỏ đến JDK khác. | Kiểm tra `/proc/PID/exe` và `jcmd PID VM.version`. |
| “Owner của file JAR là owner của JVM.” | User thực thi process không phụ thuộc owner của artifact. | Đọc effective/real UID hoặc Windows GetOwner. |
| “Systemd `MainPID` chắc chắn là JVM.” | Launcher/wrapper có thể giữ MainPID. | Kiểm tra cây parent–child và executable thực. |
| “Pod khởi chạy 3 giờ trước, JVM cũng chạy 3 giờ.” | Container/JVM có thể restart trong cùng pod. | Kiểm tra start time JVM, container ID và restart count. |
| “Host PID giống container PID.” | PID namespaces có thể ánh xạ các số khác nhau. | Xác định góc nhìn và namespace trước khi đối chiếu. |
| “Không attach được nghĩa là PID sai.” | Thiếu quyền, thiếu attach, vendor/JDK và isolation có thể gây lỗi. | Xác minh bằng OS trước; không tự nâng quyền. |
| “`CommandLine` luôn đầy đủ và an toàn để chia sẻ.” | Có thể null/truncated/đã sửa, chứa secrets. | Kiểm tra thêm OS + JVM; che/redact dữ liệu nhạy cảm. |

## 12. Những chi tiết nâng cao cần biết khi điều tra khó

### 12.1. Start time đến từ đâu?

- Trên Linux, `ps -o lstart` hiển thị start time theo định dạng/giờ địa phương. Dữ liệu nền của Linux có thể lấy từ `/proc/PID/stat`: trường `starttime` (field 22) là số clock ticks từ lúc boot; việc chuyển đổi sang wall clock cần thông tin clock tick/boot time. **Không** tự tách chuỗi `/proc/PID/stat` bằng một phép `split(" ")` đơn giản, vì trường tên process trong ngoặc có thể chứa dấu cách hoặc dấu ngoặc.
- Trên Windows, `Win32_Process.CreationDate` và `Get-Process.StartTime` phản ánh thời điểm process tạo nếu đọc được.
- Từ Java, `ProcessHandle.Info.startInstant()` là nguồn hữu ích để đối chiếu, nhưng là `Optional` và không được đảm bảo trên mọi hệ điều hành.

Khi so timestamp, ghi timezone rõ ràng (ưu tiên UTC/ISO 8601), thời gian lấy snapshot và sai lệch đồng hồ giữa node. Hai thông tin “08:15” và “08:15Z” **không thể** coi là tương đương nếu chưa biết timezone.

### 12.2. “Lệnh khởi chạy” có nhiều lớp

Một shell script hoặc service unit có thể thiết lập `JAVA_TOOL_OPTIONS`, `JDK_JAVA_OPTIONS`, system properties, classpath rồi mới gọi Java. JVM có thể chạy bằng `java -jar app.jar`, `java -cp ... com.example.Main` hoặc một launcher khác. Command line OS chỉ cho biết argv mà OS đang cung cấp, trong khi JVM command-line view có thể phản ánh những cấu hình được áp dụng tại startup.

Khi có mâu thuẫn, ghi lại **cả hai góc nhìn** (sau khi redaction) và kiểm tra cấu hình deploy/launcher. Không quyết định ứng dụng bằng cách tìm mỗi chuỗi `.jar` vì classpath nhiều file, module launch và wrapper có cách khởi động khác.

### 12.3. Ai có quyền thấy process?

Khả năng xem command line, executable hoặc attach khác nhau theo account, OS policy và namespace. Người có quyền xem PID chưa chắc đọc được arguments hoặc sử dụng `jcmd`. Owner có thể cần được biểu diễn bằng UID thay vì tên nếu account database trong container khác host. Không suy luận “không có dữ liệu” là “không có tiến trình”.

Khi thu thập để chia sẻ, loại bỏ access token, mật khẩu, connection string hoặc tham số chứa dữ liệu người dùng từ `ps`, `/proc/PID/cmdline`, `jps` và `jcmd VM.command_line`. Chỉ chia sẻ danh tính đã tối thiểu hóa và timestamp cần thiết. Các lệnh nêu trong bài là lệnh quan sát; không cần dừng, kill hoặc thay đổi JVM để nhận diện.

## 13. Checklist xác nhận mục tiêu trước thread dump, heap dump hoặc JFR

- [ ] Đã xác nhận **host/node** và **namespace/container/pod** tương ứng với cảnh báo.
- [ ] Đã ghi **PID**, **PPID**, **start time có timezone**, **owner/UID** của JVM hiện tại.
- [ ] Đã đối chiếu **executable path**, **command line** với tên service và deployment; nếu có wrapper, xác nhận cây process.
- [ ] Đã đối chiếu từ phía JVM (`VM.command_line`/`VM.version`) khi attach được; nếu không, ghi nguyên nhân và chứng cứ OS thay thế.
- [ ] Đã phân biệt **pod age**, **container restart**, **service start** và **JVM process start**.
- [ ] Đã kiểm tra **PID + start time lần cuối** ngay trước lệnh chẩn đoán để tránh chọn phiên đã restart.
- [ ] Đã loại bỏ secrets khỏi các bản ghi lệnh khởi chạy trước khi gửi hoặc lưu chung.

**Tài liệu tham khảo:**

- [Oracle Java SE 17 — `jcmd`](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jcmd.html): tìm PID JVM và gửi lệnh chẩn đoán tới JVM cụ thể.
- [Oracle Java SE 17 — `jps`](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jps.html): liệt kê Java processes khả dụng và tham số.
- [Java SE 17 API — `ProcessHandle`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ProcessHandle.html): PID và `Info` (`startInstant`, `command`, `user`).
- [Linux `/proc/PID/stat`](https://man7.org/linux/man-pages/man5/proc_pid_stat.5.html) và [`/proc/PID/cmdline`](https://man7.org/linux/man-pages/man5/proc_pid_cmdline.5.html): start time và argv từ kernel.
- [Microsoft — `Win32_Process`](https://learn.microsoft.com/en-us/windows/win32/cimwin32prov/win32-process): `ProcessId`, `CreationDate`, `CommandLine`, `GetOwner`.

**Ghi nhớ:** PID chỉ là một tọa độ đang sống trong một namespace. Nhận diện đúng JVM cần **PID + launch command + start time + owner**, gắn với đúng host/container và được kiểm tra lại sát thời điểm lấy bằng chứng.