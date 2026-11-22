# 8.2 Lấy stack bằng Thread.print, jstack hoặc cơ chế tín hiệu được hệ điều hành hỗ trợ

## Mục tiêu học tập

Khi ứng dụng Java bị treo, request kéo dài, nghi deadlock hoặc CPU tăng đột ngột, **thread dump** giúp quan sát nhiều luồng đang thực thi, chờ lock hoặc đợi tài nguyên tại thời điểm lấy mẫu. Vấn đề không chỉ là biết câu lệnh: nếu gọi nhầm PID, dùng công cụ khác namespace, gửi nhầm tín hiệu hoặc tìm output ở sai nơi, người điều tra có thể **không thu được bằng chứng** hoặc gây gián đoạn dịch vụ.

Bài này trình bày ba cơ chế chính:

1. **`jcmd <PID> Thread.print`**: gửi diagnostic command tới một JVM đang chạy.
2. **`jstack <PID>` / `jstack -l <PID>`**: in stack traces và thông tin lock bằng tiện ích JDK.
3. **Tín hiệu/console do hệ điều hành và JVM hỗ trợ**: `SIGQUIT` và `Ctrl+\` trên Linux; `Ctrl+Break` trên Windows trong trường hợp HotSpot xử lý được.

Đồng thời, bạn sẽ hiểu cách dùng **`Thread.dump_to_file`** cho virtual threads trên Java 21 khi JVM hỗ trợ, vì sao một snapshot không phải CPU profile, cách lấy nhiều dump an toàn, lựa chọn nơi lưu, xử lý lỗi attach và bảo vệ dữ liệu trong thread dump.

Sau bài học, bạn có thể tự thu một bản dump hoàn chỉnh từ **đúng JVM đích**, phân biệt nơi ghi kết quả của từng cách, đọc những trường quan trọng và đánh giá giới hạn kết luận. Ví dụ thực hành sử dụng **Java 17+** để tạo các thread có trạng thái dễ quan sát.

> Phạm vi chính: HotSpot/JDK 21. Công cụ, output, quyền và signal handlers phụ thuộc bản JDK/vendor/VM, hệ điều hành, container và chính sách vận hành. **Không gửi tín hiệu hoặc chẩn đoán vào production khi chưa xác minh đúng PID và quyền thực hiện.**

## 1. Thread dump là gì và không phải là gì?

Một **thread dump** là ảnh chụp thông tin các luồng trong JVM: tên, trạng thái, những Java method trên stack và có thể cả monitors, ownable synchronizers hoặc deadlock report. Tùy phương pháp, VM có thể hiển thị một tập thread và trường dữ liệu khác nhau; một số lệnh lấy snapshot nhất quán hơn hoặc có chi phí khác những lệnh còn lại.

| Dữ liệu | Trả lời được | Không tự trả lời |
| --- | --- | --- |
| **Exception stack trace** của `Throwable` | Exception được tạo/ghi stack ở đâu và đã đi qua những method nào? | Tất cả thread đang làm gì lúc service bị treo |
| **Thread dump** | Những thread đang nằm ở frame/state/lock nào trong khoảng thời điểm chụp? | Phần trăm CPU của từng method trong cả 10 phút |
| **CPU sampling profile** bằng JFR hoặc profiler | Những stack nào chiếm tỷ trọng samples cao qua một cửa sổ thời gian? | Tự chứng minh deadlock nếu không có lock/ownership evidence |
| **OS thread counters** | OS thread nào tiêu tốn CPU, có ID và scheduling state nào? | Toàn bộ Java call stack của thread |
| **Distributed trace** | Request đã đi qua những service/span nào và mất bao lâu? | Danh sách đầy đủ thread của một JVM tại cùng thời điểm |

Một thread `RUNNABLE` không mặc nhiên đang dùng 100% CPU. `WAITING` có thể là worker rảnh đợi hàng đợi. `BLOCKED` cho biết chờ **intrinsic monitor** ở thời điểm đo, nhưng không luôn là deadlock: đôi khi một thread giữ lock hợp lệ trong vài mili-giây rồi nhả. Hãy dùng stack + lock owner + nhiều snapshot + metrics để kết luận.

### 1.1 Trong một dump thường thấy gì?

Một đoạn **minh họa định dạng HotSpot**:

```text
"worker-17" #34 daemon prio=5 tid=0x... nid=0x2a waiting for monitor entry
   java.lang.Thread.State: BLOCKED (on object monitor)
        at com.example.OrderCache.update(OrderCache.java:88)
        - waiting to lock <0x...> (a java.lang.Object)
        at com.example.OrderService.handle(OrderService.java:40)

"worker-18" #35 daemon prio=5 tid=0x... nid=0x2b waiting on condition
   java.lang.Thread.State: TIMED_WAITING (parking)
        at jdk.internal.misc.Unsafe.park(Native Method)
        ...
```

Các địa chỉ và line number đã được rút gọn vì **không có dữ liệu từ một JVM thật**. Cần hiểu:

- Tên thread giúp định vị workload, nhưng nhiều luồng có thể **trùng tên**.
- `nid` trên HotSpot/Linux thường chỉ native thread ID theo **hexadecimal**, khác Java ID và khác `tid` là con trỏ/cấu trúc nội bộ VM.
- `java.lang.Thread.State` là state Java; nó **không tương đương trực tiếp** mọi trạng thái scheduling của OS.
- `at ...` cho thấy stack frames được VM lấy khi chụp; frame gần đầu thường là nơi đang thực thi/chờ.
- Các dòng `waiting to lock`, `locked` và `Locked ownable synchronizers` giúp điều tra lock nếu được command hỗ trợ.
- Một số dump in thêm `Found one Java-level deadlock` khi phát hiện chu trình theo cơ chế JVM; việc **không có** báo cáo này không loại trừ mọi loại chờ.

### 1.2 Chi phí không bằng 0

Theo tài liệu Oracle JDK 21, `Thread.print` có **Impact: Medium — depends on the number of threads**. Một JVM có hàng nghìn thread và stack sâu có thể tạo output rất lớn. Công cụ thu dump cũng cần CPU, bộ nhớ và thời gian để tập hợp/in. Vì vậy không mặc định chạy 100 dumps/giây khi chỉ muốn quan sát một sự cố vài phút.

Mỗi lần lấy cần ghi timestamp UTC, identity của JVM và khoảng sự cố. Nếu process restart giữa hai lần đo, **không ghép thread IDs của hai process như cùng một vòng đời**.

## 2. Chọn phương pháp nào?

| Phương pháp | Chạy ở đâu? | Output nằm ở đâu? | Điều kiện chính |
| --- | --- | --- | --- |
| `jcmd PID Thread.print` | Terminal có JDK tool và quyền attach tới JVM | **stdout của lệnh jcmd**, bên người gọi | Đúng PID/namespace, user/group, target VM hỗ trợ |
| `jcmd PID Thread.print -l -e` | Như trên | stdout của `jcmd` | `help` xác nhận options, thêm lock/extended info |
| `jstack -l PID` | Terminal có `jstack` tương thích | **stdout của jstack** | Đúng process và attach/permission; công cụ có thể không có |
| `kill -QUIT PID` (Linux) | Host/container namespace nhìn đúng PID | **stdout/log stream của JVM đích** | HotSpot signal handler hoạt động; không `-Xrs` |
| `Ctrl+\` (Linux console) | Terminal gắn đúng Java foreground process group | Console/stdout của JVM | Console điều khiển được và JVM xử lý SIGQUIT |
| `Ctrl+Break` (Windows) | Cửa sổ console sở hữu Java process | Console/stdout của JVM | JVM có console control handler và phím được chuyển tiếp |
| `jcmd PID Thread.dump_to_file ...` | Công cụ và target hỗ trợ command này | **File mà JVM đích ghi** theo filesystem của nó | `jcmd PID help Thread.dump_to_file` xác nhận lệnh |
| `jhsdb jstack` | Công cụ chuyên sâu, thường dùng với core dump | Terminal/file phân tích | Bộ binary, quyền và thao tác có thể xâm nhập mạnh hơn |

**Điểm xuất phát hợp lý cho HotSpot/JDK 21:** ưu tiên `jcmd Thread.print` nếu có công cụ và attach được; chọn `-l` khi cần ownable synchronizers; nếu `jcmd` không có mà `jstack` sử dụng được, thử `jstack -l`. Tín hiệu chỉ nên dùng khi biết rõ JVM hỗ trợ và output destination. Với ứng dụng có rất nhiều **virtual threads**, cân nhắc thêm `Thread.dump_to_file` hoặc JFR chứ không dựa độc nhất vào dump truyền thống.

## 3. Xác minh đúng JVM trước mọi thao tác

### 3.1 Đừng chỉ nhìn tên “java”

Một host có thể chạy service chính, build daemon, test runner, agent, ứng dụng phụ hoặc nhiều replica. PID có thể bị **tái sử dụng**. Hãy ghi:

- Service/application, environment, host/node.
- Container/pod ID, namespace hoặc deployment revision nếu có.
- PID và **process start time**.
- JDK/VM vendor/version khi lấy được.
- Thời điểm xảy ra vấn đề và timestamp UTC của từng capture.
- Quyền đang sử dụng và nơi sẽ lưu dump.

Trên Linux, ví dụ kiểm tra một PID đã biết:

```bash
ps -p 12345 -o pid,ppid,lstart,etime,comm,args
```

**12345 chỉ là PID giả định.** Trường `args` có thể chứa token, password hoặc đường dẫn nội bộ; không chia sẻ raw output ra nơi công khai. Nếu process manager cho PID khác với PID tìm thấy trong container, cần xác định **namespace** trước khi gắn công cụ.

### 3.2 Tìm PID bằng jcmd -l

```bash
jcmd -l
```

Lệnh này liệt kê các JVM mà công cụ nhìn thấy; tài liệu JDK 21 lưu ý một số JVM chạy trong Docker namespace riêng **không có trong danh sách `jcmd -l`**. Vì vậy “không tìm thấy” không phải bằng chứng ứng dụng không chạy Java.

`jcmd` thường yêu cầu chạy **cùng máy** và dưới effective user/group tương ứng với JVM đích. Không cố vượt policy qua `sudo`, container privileged hoặc thay quyền file hệ thống khi chưa được cho phép. Nếu tool không khả dụng trong image tối giản, dùng phương pháp thu đã được triển khai/hợp thức hóa thay vì sửa production container chỉ để thêm GUI/JDK tools.

### 3.3 PID host và PID container

Một JVM có thể có **PID 1 trong container** nhưng mang PID 21874 ở host. `kill -QUIT 1` từ host có thể nhắm tiến trình init của máy; từ container, PID 1 cũng có thể là **shell/supervisor**, không phải JVM. Phải kiểm tra bằng process metadata ở **cùng namespace gửi lệnh**.

Trong Kubernetes, xác minh đúng namespace/pod/container, restart count, image digest và bản deploy; cùng một tên pod logic không bảo đảm JVM vẫn là lần chạy trước đó. Nếu nhiều replicas, lấy dump tại **replica đang xảy ra sự cố**.

## 4. jcmd Thread.print trên JDK 21

### 4.1 Xác minh cú pháp trực tiếp trên target

```bash
jcmd 12345 help
jcmd 12345 help Thread.print
```

Dùng `help` vì diagnostic commands thuộc implementation/phiên bản VM. Với HotSpot/JDK 21, các lệnh phổ biến:

```bash
jcmd 12345 Thread.print
jcmd 12345 Thread.print -l
jcmd 12345 Thread.print -e
jcmd 12345 Thread.print -l -e
```

- **Không options:** lấy stack và trạng thái các thread mà command trình bày.
- **`-l`:** in thêm thông tin về `java.util.concurrent` locks/ownable synchronizers khi được hỗ trợ; hữu ích khi nghi `ReentrantLock`.
- **`-e`:** in extended thread information phụ thuộc VM.
- **`-l -e`:** kết hợp hai mức chi tiết khi thật sự cần; output lớn hơn, không nhất thiết tốt hơn cho mọi incident.

Đây là **lệnh thu dữ liệu**, không phải yêu cầu GC hoặc heap dump; nhưng impact vẫn phụ thuộc số lượng threads. Không chạy liên tục quá dày. Nếu lệnh không có trong `help`, không cố đoán syntax của bản khác.

### 4.2 Dùng shell redirect để lưu file

```bash
jcmd 12345 Thread.print -l > threads-12345.txt
```

Đầu ra của `jcmd` đi vào **stdout của lệnh trong shell đang chạy**. Toán tử `>` được **shell gọi command** xử lý, vì vậy file `threads-12345.txt` xuất hiện tại working directory của shell đó. Nó **không tự xuất hiện** trong thư mục của service Java khi tool được gọi từ host/container khác.

Một ví dụ POSIX shell ghi file có timestamp:

```bash
pid=12345
stamp=$(date -u +%Y%m%dT%H%M%SZ)
jcmd "$pid" Thread.print -l > "threads-$pid-$stamp.txt"
```

Không dùng cú pháp shell này nguyên dạng trong PowerShell nếu chưa chuyển sang cú pháp Windows. Sau khi thu, kiểm tra **exit code** và file thực sự có thread entries, không chỉ một thông báo lỗi attach. File tồn tại không tự chứng minh command thành công.

### 4.3 Khi nào thêm lock details?

Nếu nghi một `synchronized` block bị giữ lâu hoặc `ReentrantLock` contention, `-l` có thể giúp lấy ownership/ownable synchronizer details. Nếu đang điều tra một socket read blocked, thông tin lock bổ sung chưa chắc trả lời được vì trạng thái external network/DB không thể suy ra từ monitor ownership.

Các thread dumps thu ở hai thời điểm khác nhau không nhất thiết byte-for-byte giống nhau: JVM đang chạy, scheduling/GC/I/O tiếp tục biến động.

## 5. jstack: lệnh thay thế và giới hạn

Tài liệu JDK 21 mô tả:

```bash
jstack 12345
jstack -l 12345
```

`-l` in additional lock information, hữu ích với ownable synchronizers. Có thể dùng redirect:

```bash
jstack -l 12345 > jstack-12345.txt
```

**JDK 21 đánh dấu `jstack` là experimental and unsupported**, và có thể không có trong future JDK. Vì vậy `jcmd` thường là công cụ được ưu tiên nếu đáp ứng nhu cầu và sẵn trên target.

**Không mặc định dùng các options cũ `jstack -F` hoặc `-m`** theo hướng dẫn dành cho JDK nhiều năm trước. Hãy dùng `jstack -help` và man page ứng với bản JDK đang gọi. Khi `jstack` attach thất bại, không suy ra JVM đã deadlock: có thể do permission, namespace, process restart, attach bị tắt, JDK tool khác phiên bản hoặc VM không hỗ trợ.

### 5.1 jhsdb jstack khác jstack ra sao?

`jhsdb jstack` là công cụ chuyên sâu, có thể đọc core dump và trong một số chế độ làm việc với live process theo những điều kiện quyền đặc biệt. Tài liệu Oracle JDK 21 có ví dụ đọc core file:

```bash
# Tham khảo: cần Java binary và core dump thực tế, có quyền phân tích.
jhsdb jstack --exe /path/to/java --core /path/to/core-file
```

Đây là **phương án điều tra nâng cao**, không phải cách thay thế `jstack -l` mà không có rủi ro. Phân tích live process qua serviceability agent có thể tạm dừng/ảnh hưởng tiến trình, cần kế hoạch riêng. Nếu không có core file hoặc quyền, đừng thực thi bừa trên production.

### 5.2 Chỉ dùng output jstack khi gắn đúng process

So với `Thread.print`, công cụ có thể thêm/bớt header và lock data; không đòi hai bản dump giống nhau hoàn toàn. Đặc biệt với short-lived threads, một luồng có thể đã thoát trước khi lệnh thứ hai chạy.

Nếu PID biến mất trong khoảng giữa hai lần gọi, ghi trạng thái **process ended/restarted**, không tiếp tục dùng PID cũ vì hệ điều hành có thể đã tái sử dụng.

## 6. Linux và Unix: SIGQUIT và Ctrl+\

### 6.1 Cơ chế HotSpot signal handler

Theo Oracle JDK 21 Troubleshooting Guide, trên Linux khi HotSpot có handler thích hợp, gửi **SIGQUIT** đến process Java có thể làm JVM **in thread dump vào stdout của ứng dụng**, sau đó ứng dụng tiếp tục chạy. Câu lệnh có tên tín hiệu:

```bash
# CHỈ dùng khi đã xác minh PID và HotSpot handler đang hỗ trợ SIGQUIT.
kill -QUIT 12345
```

Trên một số Unix/Linux, `kill -3` cũng gửi SIGQUIT vì signal số 3 là QUIT trong môi trường đó, nhưng nên ưu tiên **tên tín hiệu** để giảm nhầm với các con số có thể khác trên OS khác.

**Cảnh báo cực kỳ quan trọng:** việc `kill` chỉ gửi tín hiệu không bảo đảm đích sẽ sống tiếp. Nếu target không phải HotSpot phù hợp hoặc handler SIGQUIT bị vô hiệu/không được cài, **hành vi mặc định của OS có thể kết thúc process và tạo core dump**. Vì vậy tuyệt đối không dùng SIGQUIT như một thao tác “chắc chắn read-only” với PID chưa xác minh.

### 6.2 Tại sao -Xrs làm signal dump không khả dụng?

`-Xrs` là JVM option giảm mức sử dụng OS signals. Tài liệu `java` của JDK 21 nêu nếu chạy với `-Xrs`, JVM không cung cấp **SIGQUIT thread dumps** trên hệ không phải Windows; trên Windows cũng không cung cấp dump qua Ctrl+Break handler. Ứng dụng hoặc thư viện native cài signal handler riêng cũng có thể làm hành vi thay đổi.

Do đó, khi lệnh signal không in dump:

- Kiểm tra PID, process start và target đúng JVM.
- Kiểm tra `-Xrs`/VM implementation/signal handler.
- Xem output nơi Java process thật sự ghi stdout/stderr.
- Kiểm tra log collector có truncate, rate-limit hoặc rotate.
- **Không gửi lại signal liên tục** khi chưa xác minh vì có thể dẫn đến gián đoạn.

### 6.3 Ctrl+\ và Ctrl+C không giống nhau

Trong terminal Linux/Unix có controlling terminal thích hợp, **Ctrl+\** thường gửi SIGQUIT tới **foreground process group**. Nếu terminal Java đang ở foreground và HotSpot handler hoạt động, JVM có thể in dump. Nhưng nếu một process khác đang foreground, phím này có thể gửi signal nhầm; vì vậy không dùng một terminal ngẫu nhiên để thử.

Ngược lại:

- **Ctrl+C** thường gửi SIGINT và có thể làm dừng ứng dụng, không phải tổ hợp lấy dump.
- **SIGTERM** thường là yêu cầu shutdown.
- **`kill -9` / SIGKILL** khiến process bị kết thúc không theo Java shutdown bình thường; **không phải phương án tạo Java thread dump**.

Dù mục tiêu của bạn là “lấy stack”, lệnh gửi tín hiệu vẫn có tác dụng OS thật; phải biết chính xác signal type, JVM handler và đối tượng nhận.

### 6.4 Output nằm trong log Java, không nằm ở terminal kill

Nếu SSH vào máy rồi gọi `kill -QUIT 12345`, **terminal của lệnh `kill` không tự hiển thị thread dump**. Bản dump được HotSpot ghi vào **stdout của JVM đích**. Nó có thể nằm ở:

- Console ban đầu chạy lệnh `java`.
- File mà Java service đã redirect stdout vào.
- `journalctl` nếu systemd đưa stdout của service vào journal.
- Docker container logs hoặc Kubernetes pod/container logs.
- Logging stream do process manager/app server wrapper quản lý.

Ví dụ, với một service systemd **giả định**:

```bash
journalctl -u example-java.service --since "10 minutes ago"
```

Đây là lệnh **đọc log** chứ không tạo dump. Trước khi chạy, cần biết đúng tên service, thời gian sự cố và nơi stdout được chuyển đến. Nếu JVM chạy trong container, capture có thể được thu bởi container logging driver; một sự cố log retention/multiline parser có thể cắt giữa thread dump.

### 6.5 Vì sao không thấy dump không có nghĩa là JVM không nhận signal?

`kill -QUIT` trả exit code thành công chỉ xác nhận hệ điều hành chấp nhận gửi signal; nó **không chứng minh** JVM in đầy đủ dump hoặc log collector lưu đúng. Ngược lại, không thấy text trong SSH console không có nghĩa thất bại, vì stdout nằm bên process. Cần kiểm tra service logs, handler, PID namespace và timestamp.

## 7. Windows: Ctrl+Break

Đối với HotSpot chạy trong một **console Windows** hỗ trợ control events, tổ hợp **Ctrl+Break** có thể yêu cầu JVM in thread dump ra **console/stdout của process Java**. Đây là Ctrl + phím Break/Pause, **không phải Ctrl+C**. Một số laptop/terminal emulator không có phím Break hoặc không chuyển tiếp phím này, nên cách làm có thể không khả dụng.

Nếu ứng dụng chạy như **Windows Service** hoặc dưới `javaw` mà không có console tương tác, không giả định có thể bấm Ctrl+Break. Trong trường hợp đó, ưu tiên `jcmd PID Thread.print` hoặc `jstack -l PID` bằng JDK tool có quyền thích hợp.

Để xác minh process bằng PowerShell:

```powershell
Get-Process -Id 12345 |
    Select-Object Id, ProcessName, StartTime
```

Đây là lệnh **xem process**, không sinh dump. Nếu dùng `jcmd` từ PowerShell, output nằm trong terminal đó hoặc file redirect của PowerShell, không liên quan đến console nơi service Java được start.

**Windows `-Xrs`:** khi JVM bật lựa chọn này, Ctrl+Break thread dump không khả dụng theo tài liệu Java launcher. Không “sửa nhanh” bằng cách gửi những sự kiện console khác có thể dừng service.

## 8. Virtual threads JDK 21: không suy từ Thread.print truyền thống

Virtual threads là thành phần chuẩn của Java 21. Một virtual thread có thể **unmount** khỏi carrier platform thread khi đang chờ, vì vậy những traditional HotSpot thread dumps theo platform threads có thể **không hiển thị đầy đủ các virtual threads đang chờ**.

Tài liệu Oracle JDK 21 “Virtual Threads” giới thiệu `jcmd Thread.dump_to_file` để tạo file text hoặc JSON gồm thông tin virtual threads:

```bash
# Kiểm tra target JVM hỗ trợ command trước khi thực hiện.
jcmd 12345 help Thread.dump_to_file

# Chỉ dùng nếu help xác nhận -format và filepath.
jcmd 12345 Thread.dump_to_file -format=json /path/approved/threads-12345.json
```

Tài liệu virtual threads JDK 21 minh họa `-format=text` và `-format=json`, nhưng bảng command của trang man `jcmd` JDK 21 không phải lúc nào liệt kê tên này đồng nhất; **lấy `help` từ chính JVM đích làm nguồn quyết định**. Không dùng syntax từ JDK 22/25/26 mà giả định hợp lệ với tất cả build JDK 21.

### 8.1 File nằm ở đâu?

So sánh hai lệnh:

```bash
jcmd 12345 Thread.print -l > caller-side.txt
jcmd 12345 Thread.dump_to_file -format=json /path/approved/target-side.json
```

- `caller-side.txt` được shell gọi `jcmd` tạo ở **máy/container đang chạy shell**.
- `target-side.json` được command yêu cầu **JVM đích tạo** trong filesystem của target JVM. Nếu JVM chạy trong container, file có thể nằm bên trong container và phải được lấy bằng quy trình được cho phép.
- Hai lệnh **không tương đương** về bộ dữ liệu. File dump cho virtual threads có thể thiếu một số chi tiết truyền thống về object addresses/locks/JNI/heap, tùy JDK và implementation.

Nếu cần timeline pinning/blocking, kết hợp JFR events như `jdk.VirtualThreadPinned` và dữ liệu monitoring khác. `Thread.dump_to_file` chụp **trạng thái hiện tại**, không tự khôi phục incident đã xảy ra trước lúc capture.

### 8.2 Không dùng ThreadMXBean làm tổng số virtual threads

Trên Java 21, `ThreadMXBean` chủ yếu quản lý **platform threads** theo contract của JDK. Vì vậy số thread mà một nguồn platform-oriented công bố **không phải** số tất cả virtual tasks của ứng dụng. Khi sự cố có hàng chục nghìn virtual threads, dùng phương pháp có scope phù hợp và ghi rõ giới hạn.

## 9. Thực hành Java 17+: tạo thread BLOCKED và TIMED_WAITING

Bài lab tạo ba thread có tên rõ để quan sát:

- `lab-monitor-owner` giữ object monitor và ngủ 90 giây.
- `lab-monitor-contender` muốn vào cùng monitor nên thường `BLOCKED`.
- `lab-timed-waiter` chờ `CountDownLatch` có timeout nên thường `TIMED_WAITING`.

**Giữ monitor trong lúc sleep là anti-pattern cố ý cho lab**, không sao chép sang production. Chương trình không cần Internet, framework hoặc third-party dependency.

Tạo tệp **`ThreadDumpLab.java`**:

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;

public final class ThreadDumpLab {
    private static final Object MONITOR = new Object();

    public static void main(String[] args) throws InterruptedException {
        CountDownLatch monitorHeld = new CountDownLatch(1);
        CountDownLatch neverReleased = new CountDownLatch(1);

        Thread owner = new Thread(() -> {
            synchronized (MONITOR) {
                monitorHeld.countDown();
                try {
                    Thread.sleep(90_000L);
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                }
            }
        }, "lab-monitor-owner");

        owner.start();
        monitorHeld.await();

        Thread contender = new Thread(() -> {
            synchronized (MONITOR) {
                // Vào được sau khi owner nhả monitor.
            }
        }, "lab-monitor-contender");

        Thread timedWaiter = new Thread(() -> {
            try {
                neverReleased.await(90L, TimeUnit.SECONDS);
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        }, "lab-timed-waiter");

        contender.start();
        timedWaiter.start();

        System.out.println("ThreadDumpLab READY");
        System.out.println("PID=" + ProcessHandle.current().pid());

        owner.join();
        contender.join();
        timedWaiter.join();
        System.out.println("ThreadDumpLab DONE");
    }
}
```

Biên dịch và chạy:

```bash
javac ThreadDumpLab.java
java ThreadDumpLab
```

**Dòng stdout đầu tiên chính xác**:

```text
ThreadDumpLab READY
```

Dòng thứ hai có dạng `PID=<giá-trị-PID-thực>`, khác nhau trên mỗi lần chạy. Sau khoảng 90 giây nếu không bị ngắt, chương trình in `ThreadDumpLab DONE` rồi thoát. `javac` không in gì khi compile thành công. Không cố dự đoán số PID, `nid`, line number hay thời điểm chính xác scheduler chuyển thread sang BLOCKED.

### 9.1 Thử jcmd và jstack

Mở **terminal thứ hai** cùng máy/user và thay `12345` bằng PID thật của lab:

```bash
jcmd 12345 help Thread.print
jcmd 12345 Thread.print
jcmd 12345 Thread.print -l
jstack -l 12345
```

Nếu đúng thời điểm trước khi các thread kết thúc:

| Thread | Kỳ vọng | Cách đọc |
| --- | --- | --- |
| `lab-monitor-owner` | `TIMED_WAITING (sleeping)` | Trong `Thread.sleep` và vẫn giữ monitor của demo |
| `lab-monitor-contender` | `BLOCKED (on object monitor)` | Chờ monitor mà owner đang giữ |
| `lab-timed-waiter` | `TIMED_WAITING` | Chờ latch với timeout |
| `main` | Thường chờ trong `Thread.join` | Đợi các worker kết thúc |

Đây là **trạng thái dự kiến trong cửa sổ lab**. Do scheduling và thời điểm capture, output có thể khác; phải đọc **kết quả thật**, không chép số mẫu giả.

### 9.2 Thử SIGQUIT trên Linux chỉ với JVM lab

Khi chắc chắn PID thuộc **ThreadDumpLab** và HotSpot có handler:

```bash
kill -QUIT 12345
```

Xem terminal **chạy `java ThreadDumpLab`**, không chỉ terminal gửi `kill`. Dump thường xuất hiện bên stdout của JVM lab. Nếu không xuất hiện, kiểm tra signal handler và phiên chạy, không gửi tiếp vào process khác.

### 9.3 Thử Ctrl+Break trên Windows chỉ với JVM lab

Nếu có console Windows thực sự chứa Java process, dùng **Ctrl+Break**. Dump, nếu được VM hỗ trợ, in trong console đó. Nếu terminal không có Break, thử `jcmd` hoặc `jstack` thay vì dùng Ctrl+C hoặc tổ hợp có thể terminate JVM.

### 9.4 Đặt câu hỏi đúng khi so hai dump

Hai dump cách nhau 5 giây không buộc giống hệt nhau; thread states được chụp vào hai thời điểm khác nhau. Nhưng trong lab, `lab-monitor-contender` thường **tiếp tục BLOCKED** cho tới khi owner nhả lock. Khi thấy điều đó, bạn có bằng chứng **thời lượng tranh chấp kéo dài trong nhiều mẫu**, tốt hơn so với chỉ một ảnh.

## 10. Thu nhiều dump để quan sát xu hướng

Một snapshot tại T0 là một điểm trong thời gian. Với hiện tượng request kẹt trong 30–60 giây, vài snapshots cách 5–10 giây có thể cho thấy cùng một thread/lock xuất hiện lặp lại. Chọn khoảng dựa trên **độ dài sự cố**, không có “3 dumps cách 5 giây” là quy tắc bất biến.

Mẫu POSIX shell sau chỉ nên chạy ở **JVM lab** hoặc trong production khi có quyền và đã tính overhead:

```bash
pid=12345
for i in 1 2 3; do
  stamp=$(date -u +%Y%m%dT%H%M%SZ)
  jcmd "$pid" Thread.print -l > "threads-$pid-$i-$stamp.txt"
  code=$?
  printf 'sample=%s exitCode=%s\n' "$i" "$code"
  if [ "$code" -ne 0 ]; then
    break
  fi
  if [ "$i" -lt 3 ]; then
    sleep 5
  fi
done
```

Từng file nằm ở **shell đang gọi jcmd**, có timestamp trong tên. Cần kiểm tra exit code, dump header và số thread entries. Nếu JVM restart, **dừng** chuỗi đo và ghi identity mới. Đừng chạy script trên mọi replica đồng thời nếu chưa có ngân sách tác động.

### 10.1 Cần chụp thêm gì ngoài thread dumps?

- UTC timestamp, host/container/pod, PID và process start.
- Error rate, p95/p99 request latency, throughput và queue length cùng khoảng.
- OS per-thread CPU khi nghi hot loop, mapping native TID với HotSpot `nid`.
- GC pauses, heap pressure và safepoint metrics/JFR khi cần.
- App build/version và deployment/rollout events.
- Ghi rõ nguồn của mỗi snapshot: `jcmd`, `jstack`, `SIGQUIT` hoặc `Thread.dump_to_file`.

**Giới hạn:** timestamp hai công cụ khác nhau có thể lệch vì clock skew và latency thu thập. Không gán quan hệ nhân quả chỉ vì hai event “đồng thời” trong dashboard.

## 11. Đọc kết quả sau khi đã thu

### 11.1 Stack frames, lock owner và trạng thái

Một bản HotSpot dump có thể chứa:

```text
"worker-A" ... nid=0x...
   java.lang.Thread.State: BLOCKED (on object monitor)
      at demo.Resource.lockedSection(Resource.java:42)
      - waiting to lock <0x111> (a java.lang.Object)

"worker-B" ... nid=0x...
   java.lang.Thread.State: TIMED_WAITING (sleeping)
      at java.base/java.lang.Thread.sleep(Native Method)
      - locked <0x111> (a java.lang.Object)
```

Đoạn này **mô phỏng cấu trúc**, không phải output thực; địa chỉ `<0x111>` và source line được đặt chỉ để minh họa. Nếu owner B giữ monitor dài và A chờ vào cùng monitor trong nhiều dumps, đó là lock contention. Nếu A và B giữ hai monitor khác nhau, đồng thời mỗi thread chờ monitor của người kia, có thể hình thành deadlock cycle; cần xem toàn bộ owner relations.

Không phải mọi `WAITING` đều bất thường: thread pool workers, scheduled executors và queue consumers thường chờ nhiệm vụ. Với network I/O, stack có thể bắt đầu trong `sun.nio.ch` hoặc driver; cần nhìn caller application và downstream telemetry để biết vì sao chờ.

### 11.2 RUNNABLE và CPU cao

`RUNNABLE` không tương đương “sử dụng toàn bộ CPU” vì một số thread có thể đang thực hiện hoặc chờ ở native I/O và VM/OS có cách biểu diễn khác nhau. Khi OS metrics báo CPU cao:

1. Lấy process/thread CPU cùng thời điểm.
2. Trên HotSpot/Linux, `nid=0x...` thường là native TID dạng **hexadecimal**; một số OS tools in TID decimal.
3. Chuyển native TID từ decimal sang hex và ghép với `nid`, **không dùng `tid` internal pointer hoặc Java thread ID**.
4. So cùng thread qua nhiều snapshots và dùng JFR/CPU profiler nếu cần hotspot chính xác.

Ví dụ **decimal 42 = hex `0x2a`**; chỉ là minh họa phép chuyển đổi, không phải một TID đo thật.

### 11.3 Deadlock không phải mọi kiểu treo

Java-level deadlock detection tìm các chu trình monitor/ownable synchronizers theo phạm vi hỗ trợ. Một database lock, hung RPC, queue starvation hoặc missed signal có thể khiến request treo **mà không tạo deadlock Java-level**. “No deadlocks found” không đồng nghĩa “ứng dụng không treo”.

Khi thấy nhiều `BLOCKED`, cần hỏi **ai giữ lock**, stack của owner, thời gian giữ, có progress qua các mẫu và vai trò của thread (request worker, GC, housekeeping). Chỉ một snapshot thường chưa đủ để kết luận vấn đề ổn định.

## 12. Chẩn đoán khi công cụ hoặc output có vấn đề

### 12.1 jcmd / jstack không attach được

Một số nguyên nhân phổ biến:

- PID sai, process đã thoát/restart.
- Khác user/group hoặc policy attach.
- PID namespace/container mount khác.
- Runtime image không có JDK tools.
- VM tắt attach, JVM khác implementation hoặc công cụ không tương thích.
- JVM kẹt sâu hoặc bị OS security policies chặn.

Kiểm tra từng yếu tố thay vì lập tức tăng quyền. Nếu không có khả năng thu, ghi rõ **diagnostic unavailable** chứ không bịa stack. `jhsdb` hay core analysis có thể hữu ích cho sự cố nghiêm trọng nhưng cần quyền/tác động riêng.

### 12.2 SIGQUIT được gửi nhưng không thấy dump

Hãy kiểm tra:

1. JVM đích và PID/start time đã xác thực chưa?
2. Có dùng `-Xrs` hoặc handler không tồn tại không?
3. Output của Java đi vào console, systemd journal, stdout redirect, Docker/Kubernetes logs hay nơi khác?
4. Log collector có truncate, rate limit hoặc multiline parser sai không?
5. Có đang xem log của đúng container/replica, đúng timestamps không?
6. Signal gửi ở namespace nào; PID 1 ở host và container có khác không?

Nếu OS đã báo signal gửi thành công, đừng mặc định JVM in dump thành công. Nếu handler không có, **SIGQUIT có thể terminate process**, vì vậy không thử lặp lại bừa bãi.

### 12.3 Windows Ctrl+Break không hoạt động

Có thể JVM chạy như service không gắn console, dùng `javaw`, có `-Xrs` hoặc terminal không chuyển sự kiện Break. Dùng `jcmd`/`jstack` với quyền đúng và không thay Ctrl+Break bằng Ctrl+C.

### 12.4 File có dữ liệu nhưng bị cắt

Output thread dump có thể rất lớn, nhất là hàng nghìn threads. Nếu ghi qua stdout logging, parser multi-line, buffer limit, quota hoặc log rotation có thể cắt giữa dump. Khi đó:

- Ghi **capture incomplete**.
- Kiểm tra đầu/cuối file và timestamp.
- Không suy từ thiếu một thread trong phần đã cắt rằng nó không tồn tại.
- Nếu được phép, thử lưu output trực tiếp bằng shell redirect của `jcmd` thay vì đi qua log pipeline.
- Nếu dùng `Thread.dump_to_file`, kiểm tra file trên đúng JVM filesystem và quyền ghi.

### 12.5 Lỗi kết nối trong container

Một container có thể không chứa `ps`/`jcmd`; `jcmd -l` từ host cũng có thể không thấy JVM. Nếu cần tool, dùng quy trình incident debugging đã cho phép (ví dụ ephemeral/debug tooling được phê duyệt) thay vì đổi image đang chạy tùy tiện. Giữ identity node/pod/container và đối chiếu namespace PID trước khi gửi bất kỳ signal.

## 13. An toàn, quyền truy cập và chi phí

Một thread dump có thể chứa **tên classes/methods nội bộ, thread names nhúng user/request IDs, path, endpoint, thông tin thư viện, địa chỉ object và lock metadata**. Mặc dù không mặc nhiên chứa toàn bộ local variables, nó không phải dữ liệu công khai. Bảo vệ bằng:

- Chỉ thu trên đúng service và với quyền hợp lệ.
- Lưu trong thư mục chẩn đoán có quyền giới hạn; đặt retention và quy trình xóa.
- Redact thread names/log labels hoặc metadata nhạy cảm trước khi chia sẻ.
- Không upload raw dumps lên dịch vụ phân tích bên thứ ba nếu chưa được cho phép.
- Gắn process identity, timestamp, tool/command và trạng thái complete/truncated vào artifact.
- Giới hạn tần suất, số lượng replicas, disk và logging overhead.

Việc thu dump có thể làm tăng CPU/I/O và làm dịch vụ đang quá tải nặng thêm; nhất là nếu lấy snapshot dày. Không gửi `SIGKILL`/`SIGTERM` chỉ để “lấy thread stack”. Với `SIGQUIT`, phải xác minh handler vì nếu không có, **tác động có thể phá hủy tiến trình**.

Một record metadata **giả định**:

```yaml
captureTimeUtc: "2026-10-29T08:45:00Z"
service: "checkout-api"
environment: "staging"
instance: "checkout-2"
pid: 12345
processStartUtc: "2026-10-29T08:05:00Z"
javaRuntime: "21.0.x"
tool: "jcmd"
command: "jcmd 12345 Thread.print -l"
outputLocation: "restricted-diagnostics/threads-12345.txt"
captureComplete: true
redactedBeforeSharing: true
incidentWindow: "2026-10-29T08:44:00Z/2026-10-29T08:46:00Z"
```

Các số và tên trên đều là **dữ liệu minh họa**. Không copy thành báo cáo thực tế nếu chưa thu thông tin từ JVM thật. Nếu thu bằng signal, cần ghi `method: SIGQUIT` và nơi stdout của JVM được chuyển đến thay vì ghi `jcmd`.

## 14. Quy trình xử lý incident trong sáu bước

**Bước 1 — Định nghĩa triệu chứng.** Request stuck, lock contention, CPU spike, hung I/O, thread leak hay virtual-thread stalls? Xác định khoảng thời gian và hệ đo có sẵn.

**Bước 2 — Chọn đúng JVM.** Xác minh service, host/container, PID, start time, runtime/version, quyền. Không lấy dump của replica khỏe rồi dùng làm bằng chứng cho replica lỗi.

**Bước 3 — Chọn công cụ và output location.** Ưu tiên `jcmd Thread.print` khi hỗ trợ; `jstack -l` là lựa chọn bổ sung; tín hiệu chỉ khi handler được xác minh; `Thread.dump_to_file` khi cần virtual-thread visibility và command có trong `help`.

**Bước 4 — Thu với ngân sách tác động.** Một số dump trong incident window đủ để xác định trạng thái kéo dài. Ghi timestamps, exits và kiểm tra file; nếu process restart, dừng bộ đo cũ.

**Bước 5 — Phân tích so với telemetry.** Đọc state/monitor/lock owner, so multiple snapshots, OS native TID CPU, GC pauses, request p99, downstream metrics. Tách một lần xuất hiện `BLOCKED` khỏi tranh chấp kéo dài hoặc cycle deadlock.

**Bước 6 — Ghi quan sát và kết luận đúng mức.** Ví dụ “12 request workers nằm ở cùng `OrderRepository.save` qua ba dumps” là quan sát. “DB connection pool quá nhỏ” vẫn là giả thuyết cho tới khi có pool/DB/queue metrics. Nếu dump thiếu, ghi rõ giới hạn.

## 15. Nhầm lẫn phổ biến

| Sai lầm | Cách hiểu đúng |
| --- | --- |
| “`jcmd -l` không thấy process là JVM không chạy.” | PID namespace/permission khiến công cụ không liệt kê mọi JVM. |
| “PID 1 trong Docker là PID 1 ngoài host.” | Namespace có thể khác; không gửi signal nếu chưa xác định process. |
| “`Thread.print` luôn không tác động.” | Impact Medium, tăng theo số threads và lượng output. |
| “`-l` chỉ in thêm method names.” | Bổ sung ownable synchronizers/`java.util.concurrent` locks. |
| “`jstack -F` luôn có trong JDK 21.” | Options thay đổi; đọc man/`-help` của tool đang dùng. |
| “`jstack -l` phải giống `jcmd Thread.print -l` từng ký tự.” | Hai lần chụp khác thời điểm và format có thể khác. |
| “`jcmd ... > file` lưu file bên trong JVM/container.” | Redirect là của shell **gọi jcmd**. |
| “`kill -QUIT PID` in stack ở terminal lệnh kill.” | Signal dump xuất ra **stdout/log stream của JVM đích**. |
| “SIGQUIT chắc chắn không làm dừng Java.” | Không có handler/`-Xrs` có thể khiến OS terminate/core dump. |
| “Ctrl+C là cách Windows lấy thread dump.” | Windows console dùng **Ctrl+Break** khi có hỗ trợ. |
| “`kill -9` giúp JVM in dump trước khi chết.” | SIGKILL không dùng để tạo Java thread dump. |
| “Không thấy output ở SSH terminal nghĩa signal không được JVM nhận.” | Kiểm tra app logs/stdout pipeline, PID, handler, `-Xrs`. |
| “Thread.print chắc chắn liệt kê đủ mọi virtual thread.” | Traditional dump có thể thiếu unmounted virtual threads; dùng công cụ phù hợp Java 21. |
| “`RUNNABLE` nghĩa thread đang dùng toàn bộ CPU.” | Cần OS CPU counters/JFR, không chỉ Java state. |
| “`WAITING` luôn là deadlock.” | Idle pool/queue worker thường chờ hợp lệ. |
| “Không có Java deadlock report nghĩa request không thể treo.” | Network/DB waits, starvation, missed signals có thể nằm ngoài phạm vi deadlock detection. |
| “Một dump sau restart mô tả được incident trước restart.” | Dữ liệu snapshot thuộc process/run mới, không khôi phục lịch sử. |
| “Có file đồng nghĩa capture thành công.” | File có thể chỉ chứa error text hoặc bị truncate; phải kiểm tra output. |
| “Raw thread dump không có dữ liệu nhạy cảm.” | Thread names, paths, packages, hostnames và structure có thể nhạy cảm. |

## 16. Câu hỏi tự kiểm tra

**Câu 1.** `jcmd 12345 Thread.print -l > a.txt` lưu `a.txt` ở đâu?

**Đáp án:** trong working directory của **shell gọi `jcmd`**. Không tự nằm trong filesystem của JVM container nếu lệnh chạy từ host khác.

**Câu 2.** Bạn SSH vào máy, gửi `kill -QUIT` thành công nhưng terminal SSH không hiển thị dump. Có chứng minh thất bại không?

**Đáp án:** không. HotSpot handler ghi dump vào **stdout của Java process**; kiểm tra journal, container logs, stdout redirect hoặc console sở hữu JVM.

**Câu 3.** Có thể gửi SIGQUIT vào mọi PID mang tên java mà không cần kiểm tra `-Xrs` không?

**Đáp án:** không. Không có handler SIGQUIT thì OS có thể terminate/core dump; cần xác minh PID, VM handler, quyền và rủi ro.

**Câu 4.** Tại sao chọn `Thread.print -l` khi nghi `ReentrantLock`?

**Đáp án:** `-l` thêm thông tin ownable synchronizers/`java.util.concurrent` locks khi VM hỗ trợ. Vẫn cần xác minh owner, call stacks và duration.

**Câu 5.** Java 21 dùng rất nhiều virtual threads nhưng `Thread.print` trả ít threads. Có thể khẳng định các virtual threads đã kết thúc?

**Đáp án:** không. Một số unmounted virtual threads có thể không có trong traditional thread dump. Dùng `Thread.dump_to_file` khi target hỗ trợ, hoặc JFR/monitoring có scope phù hợp.

**Câu 6.** Một thread `RUNNABLE` xuất hiện trong dump có phải CPU hotspot không?

**Đáp án:** chưa. Cần OS per-thread CPU, native `nid` correlation và CPU sampling qua một khoảng.

**Câu 7.** Cả ba dumps trong 15 giây đều có thread A `BLOCKED`. Có đủ bằng chứng deadlock?

**Đáp án:** chưa. Có thể lock held lâu nhưng vẫn có progress. Kiểm tra owner, vòng chờ, throughput và context; không đồng nhất contention với deadlock.

**Câu 8.** Vì sao không dùng `kill -9` để thu dump?

**Đáp án:** SIGKILL dừng tiến trình ngay ở mức OS, không cho JVM xử lý tín hiệu để xuất Java stacks theo cơ chế này.

**Câu 9.** `jstack -l` chạy thất bại sau khi lab in `DONE`. Có phải JVM bị deadlock?

**Đáp án:** không. JVM lab đã thoát; hãy kiểm tra PID/start time và không gửi tiếp signal vào PID đã có thể bị tái sử dụng.

**Câu 10.** Hai dumps từ cùng JVM cách nhau 5 giây cho kết quả khác nhau. Có lỗi công cụ không?

**Đáp án:** không nhất thiết. JVM đang chạy và threads thay đổi state liên tục. Quan trọng là ghi thời điểm, so các thread/lock liên quan và xác định xu hướng có ý nghĩa.

## 17. Checklist cuối bài

- Xác minh **đúng JVM, PID/start time, host/container namespace và quyền**.
- Chọn **`jcmd Thread.print`** nếu hỗ trợ; xem `help`, thêm `-l`/`-e` khi có mục tiêu.
- Dùng **`jstack -l`** khi phù hợp, nhớ JDK 21 đánh dấu tool experimental/unsupported.
- Chỉ dùng **Linux `SIGQUIT`/`Ctrl+\`, Windows `Ctrl+Break`** khi handler đã được xác minh; hiểu `-Xrs` và rủi ro default signal.
- Phân biệt **caller-side stdout/file** của `jcmd/jstack`, **target JVM stdout** của signal và **target filesystem** của `Thread.dump_to_file`.
- Không gán traditional platform-thread dump thành danh sách đầy đủ mọi Java 21 virtual threads.
- Lấy vài snapshots đúng **cửa sổ sự cố**, với timestamp UTC và process identity.
- Kiểm tra file có **thread dump thật, không bị cắt**, và lưu bảo mật.
- Đọc state, locks, owners, OS native TID và stack cùng telemetry; không kết luận root cause chỉ từ một snapshot.
- Không dùng SIGKILL, Ctrl+C hoặc thao tác dừng process khi mục tiêu chỉ là thu stack.

**Kết luận:** thu stack đúng là **xác định JVM → chọn công cụ phù hợp → biết output đi đâu → giới hạn rủi ro → đọc snapshot trong bối cảnh thời gian**. Trên HotSpot/JDK 21, `jcmd Thread.print` thường là bước đầu, `jstack` là lựa chọn bổ sung, còn SIGQUIT/Ctrl+Break có ích khi được VM/OS hỗ trợ nhưng phải cực kỳ cẩn thận để không làm hỏng chính ứng dụng đang cần chẩn đoán.

### Tài liệu tham khảo chính thức

- [Oracle JDK 21 — The jcmd Command](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html): cú pháp `Thread.print`, `-l`, `-e`, impact và điều kiện attach.
- [Oracle JDK 21 — The jstack Command](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jstack.html): `jstack`/`-l`, công cụ experimental/unsupported.
- [Oracle JDK 21 — Diagnostic Tools and Control+Break Handler](https://docs.oracle.com/en/java/javase/21/troubleshoot/diagnostic-tools.html): Linux SIGQUIT, Windows Ctrl+Break, stdout, thread states và deadlock report.
- [Oracle JDK 21 — The java Command](https://docs.oracle.com/en/java/javase/21/docs/specs/man/java.html): option `-Xrs` và Java/OS signal handling.
- [Oracle JDK 21 — Virtual Threads](https://docs.oracle.com/en/java/javase/21/core/virtual-threads.html): virtual threads và `Thread.dump_to_file` text/JSON.
- [Java SE 21 — ThreadMXBean API](https://docs.oracle.com/en/java/javase/21/docs/api/java.management/java/lang/management/ThreadMXBean.html): thread diagnostics, locks và khả năng theo dõi platform threads.
