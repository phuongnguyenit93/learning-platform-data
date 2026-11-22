# 20.8. Ảnh hưởng nghiêm trọng khi jhsdb attach trực tiếp vào tiến trình sống

**Cảnh báo cần nhớ trước mọi thao tác:** `jhsdb` là công cụ dựa trên **HotSpot Serviceability Agent (SA)** để phân tích cấu trúc nội bộ JVM. Theo tài liệu **Oracle JDK 21**, attach `jhsdb` vào **process Java đang sống** sẽ làm process bị treo và nhiều khả năng **crash khi debugger detach**. Đây không chỉ là tác động hiệu năng: thao tác vốn để chẩn đoán có thể trực tiếp gây gián đoạn dịch vụ.

Nguyên tắc của bài: **không coi `jhsdb ... --pid` là lệnh đọc trạng thái thông thường trên production**. Với JVM còn đáp ứng, ưu tiên metrics/JFR/log hoặc diagnostic command `jcmd` có mức tác động được công bố. Nếu có core dump, dùng `jhsdb ... --exe ... --core ...` để **phân tích sau sự cố**. Việc thu core từ process còn sống là bước riêng cũng có rủi ro và phải được phê duyệt.

Mục tiêu học tập:

- Nhận diện chính xác thao tác `jhsdb` nào là **live SA attach**, kể cả chế độ `jstack`/`jmap` nhìn có vẻ vô hại.
- Hiểu vì sao live attach có thể dẫn tới hang, crash, timeout, restart, mất bằng chứng và tác động dây chuyền.
- Phân biệt `--pid` với `--exe --core`, `jhsdb` với `jcmd`, JFR và heap dump.
- Lựa chọn cách thu bằng chứng theo mức rủi ro và trạng thái JVM.
- Đọc core bằng `jhsdb` offline theo ví dụ, và thực hành với Java 17+ **mà không attach SA vào tiến trình sống**.
- Thiết kế runbook, giới hạn tác động và bảo vệ dữ liệu khi xử lý sự cố JVM.

## 1. Serviceability Agent và vai trò thực sự của `jhsdb`

**HotSpot Serviceability Agent (SA)** cung cấp khả năng đọc các cấu trúc nội bộ như heap layout, thread, class metadata, code cache và những dữ liệu liên quan đến native JVM. Không giống một API monitoring thông thường, SA có thể đọc trạng thái JVM từ **core dump** hoặc từ một tiến trình đang chạy khi debugger attach.

Các chế độ được tài liệu `jhsdb` JDK 21 liệt kê:

| Lệnh | Dữ liệu hoặc khả năng chính | Cảnh báo khi dùng `--pid` của JVM sống |
| --- | --- | --- |
| `jhsdb jstack` | Java thread stacks, thông tin locks; có thể kèm native frames bằng `--mixed` | Có rủi ro SA live attach |
| `jhsdb jmap` | Heap summary, histogram, class loader statistics, HPROF trong chế độ hỗ trợ | Có rủi ro SA live attach |
| `jhsdb jinfo` | VM flags và system properties | Có rủi ro SA live attach |
| `jhsdb jsnap` | Performance counters | Có rủi ro SA live attach |
| `jhsdb clhsdb` | CLI debugger tương tác ở mức JVM | Có rủi ro SA live attach |
| `jhsdb hsdb` | GUI debugger tương tác | Có rủi ro SA live attach |
| `jhsdb debugd` | SA debug server để truy cập từ xa | Có rủi ro SA live attach nếu server gắn với PID sống |

**Sai lầm phổ biến:** tưởng rằng lệnh có tên `jstack`/`jmap` chỉ in dữ liệu nên không ảnh hưởng tới chương trình. Thực ra từ khóa quan trọng là **`jhsdb` và `--pid`**, chứ không phải đầu ra chỉ đọc hay đầu ra tương tác. Lệnh `jhsdb jstack --pid` **khác cơ chế** với `jcmd PID Thread.print`. Cảnh báo của Oracle áp dụng cho thao tác live attach của `jhsdb`.

## 2. Phân biệt live attach và postmortem bằng core

Hai hướng phân tích có ý nghĩa vận hành rất khác:

~~~text
A. LIVE ATTACH BẰNG SA — KHÔNG THỬ TRÊN SERVICE PRODUCTION

   JVM đang xử lý request
           |
           +-- jhsdb ... --pid <PID>
                       |
                       +-- debugger/SA attach tới process còn sống
                       +-- process có thể ngừng tiến triển
                       +-- detached debugger có thể để lại process crash
                       +-- timeout, liveness failure, restart, outage

B. POSTMORTEM / OFFLINE — HƯỚNG ĐƯỢC ƯU TIÊN

   JVM đã crash và có core dump hợp lệ
           |
           +-- [core file] + [executable của JVM gốc] + [runtime/symbols]
                       |
                       +-- jhsdb ... --exe ... --core ...
                       |
                       +-- đọc stack / heap / flags trên máy phân tích
                           không attach JVM production đang chạy
~~~

`--pid` lựa chọn **một process còn đang tồn tại**. `--exe` và `--core` lựa chọn **file executable** cùng **ảnh core**; không cần giữ JVM gốc sống để đọc. Đây là cú pháp được Oracle tài liệu hóa, không phải phép biến đổi tên file tùy ý.

Vì sao live attach nguy hiểm? SA cần xem cấu trúc HotSpot ở mức thấp, thường thông qua cơ chế native debugger và điều khiển trạng thái process. Việc debugger giữ các thread không tiến triển gây ảnh hưởng trực tiếp tới JVM đang phục vụ. Oracle cảnh báo kết quả **treo trong lúc attach và nhiều khả năng crash khi detach**. Chi tiết phụ thuộc OS, debugger, HotSpot build và tình trạng JVM; **không có bảo đảm rằng thoát khỏi tool sẽ khôi phục process bình thường**.

Điểm cần phân biệt: **đọc core offline không tác động tới JVM gốc đang chạy**, nhưng **tạo core của JVM còn sống** có thể phải tạm dừng process, dùng ptrace hoặc tạo I/O rất lớn. “Offline analysis” an toàn hơn ở khâu phân tích; nó không biến mọi phương pháp **core capture** thành không có chi phí.

## 3. Những hậu quả nghiêm trọng trong production

| Tác động | Tình huống minh họa | Hệ quả |
| --- | --- | --- |
| **Treo process** | Thread không tiến triển khi debugger attach | HTTP timeout, không xử lý message, backlog tăng |
| **Crash lúc detach** | Sau khi người vận hành thoát `jhsdb`, JVM không tiếp tục được | Mất instance và cần recovery |
| **Health check thất bại** | Readiness/liveness không được phục vụ | Kubernetes loại pod hoặc restart |
| **Tác động dây chuyền** | Load balancer chuyển traffic sang các replica còn lại | Retry storm, overload, latency tăng |
| **Dữ liệu vận hành bị gián đoạn** | Request/transaction/queue consumer đang hoạt động bị dừng | Rollback, duplicate retry, lease timeout |
| **Mất bằng chứng nguyên bản** | JVM crash/restart làm biến mất heap/thread state vừa cần điều tra | Không thể quay lại trạng thái cũ để đo lại |
| **Chiếm tài nguyên host** | Dump/core hoặc thao tác đọc nhiều memory, ghi file lớn | Đĩa đầy, I/O contention, gián đoạn process khác |
| **Tiết lộ dữ liệu** | SA/core có thể đọc string, secrets, properties, object state | Rủi ro PII/credentials và trách nhiệm lưu trữ |

Không phải tất cả hậu quả đều xảy ra ở mọi lần attach; tuy nhiên **mức độ có thể mất tiến trình** đủ cao để buộc thao tác phải được phân loại là **risk of outage**. Không nên nói “chỉ attach vài giây” vì thời gian debugger attach hoặc detach **không có SLA ngắn cố định** mà ứng dụng có thể dựa vào.

Kể cả hệ thống có high availability, một replica ngừng xử lý làm thay đổi throughput khả dụng. Nếu còn ít capacity dự phòng, retry và failover có thể làm những replica khác chậm theo. Nếu JVM bị treo ở thời điểm đang xử lý transaction, trạng thái giao dịch và retry idempotency cần được đánh giá sau recovery.

## 4. Nhận diện các thao tác tuyệt đối không dùng như kiểm tra thường kỳ

Dưới đây là **mẫu cú pháp nguy hiểm để nhận diện**, không phải hướng dẫn thực hành:

~~~text
KHÔNG CHẠY CÁC DẠNG SA LIVE ATTACH TRÊN PRODUCTION:

jhsdb jstack --pid <PID>
jhsdb jmap --pid <PID>
jhsdb jinfo --pid <PID>
jhsdb jsnap --pid <PID>
jhsdb clhsdb --pid <PID>
jhsdb hsdb --pid <PID>
jhsdb debugd --pid <PID>
~~~

Thay `<PID>` bằng một PID thật biến những dòng trên thành thao tác attach vào process sống. Không có nhánh `jhsdb` nào trong danh sách trở nên an toàn chỉ vì “không định sửa gì”. `jhsdb debugd --pid` cũng không được bảo vệ bởi việc người dùng kết nối từ xa: **server vẫn attach vào JVM sống**. Remote SA còn có thể mở bề mặt truy cập qua mạng nếu thiết lập không được cô lập.

**Quy tắc:** khi không có core dump mà người vận hành muốn thêm `--pid` vào lệnh `jhsdb` để lệnh chạy được, đó là tín hiệu **dừng lại, đánh giá rủi ro và chọn phương án khác**.

## 5. Các công cụ thay thế khi JVM còn đáp ứng

Với HotSpot JDK 21, `jcmd` cung cấp diagnostic commands có mô tả **Impact**. Đây là con đường hợp lý hơn cho live triage khi đúng quyền và JVM responsive, nhưng **không có lệnh chẩn đoán nào là hoàn toàn miễn phí**.

| Câu hỏi | Lựa chọn trước khi nghĩ tới SA live | Impact theo JDK 21 hoặc lưu ý |
| --- | --- | --- |
| Đang chạy VM/version nào? | `jcmd PID VM.version` | Low |
| Command line/flags là gì? | `jcmd PID VM.command_line` / `VM.flags` | Low |
| Thông tin VM tổng hợp? | `jcmd PID VM.info` | Low |
| Thread nào block/deadlock? | `jcmd PID Thread.print -l` | Medium, phụ thuộc số lượng thread |
| Heap đang sử dụng? | `jcmd PID GC.heap_info` | Medium |
| Cần loại object đang giữ heap? | JFR trend, JMX; cân nhắc `jcmd PID GC.class_histogram` | Histogram High impact |
| Cần Java heap snapshot? | `jcmd PID GC.heap_dump filename=...` | High impact, thường yêu cầu Full GC |
| Cần biểu đồ theo thời gian? | JFR có cấu hình phù hợp | Recording thường low overhead, phụ thuộc event settings |
| JVM đã chết? | `hs_err_pid*.log`, JFR đã ghi, core dump | Dùng postmortem, không attach PID đã mất |

**Ví dụ lệnh cho PID 12345** (PID chỉ minh họa, phải xác nhận đúng process, host và quyền trước khi chạy):

~~~bash
jcmd 12345 VM.version
jcmd 12345 VM.command_line
jcmd 12345 VM.info
jcmd 12345 Thread.print -l
~~~

Theo JDK 21, `VM.info` là Low, `Thread.print` là Medium. Nếu JVM đang chịu tải hoặc có hàng nghìn thread, ngay cả `Thread.print` cũng có thể tốn thời gian. Không dùng vòng lặp lấy thread dump vô hạn và không spam `jcmd` khi nó đã timeout.

Ví dụ dùng JFR để thu thông tin theo thời gian nếu JVM còn hoạt động, đường dẫn thuộc filesystem của JVM và có quyền ghi:

~~~bash
jcmd 12345 JFR.check
jcmd 12345 JFR.start name=triage settings=default duration=2m filename=/var/tmp/triage-12345.jfr
~~~

`duration=2m` giúp recording có thời gian kết thúc; đây là một cách thu event, **không phải** ảnh chụp toàn bộ memory của tiến trình. File có thể chưa tồn tại cho đến lúc recording kết thúc theo cấu hình. `JFR.start` không có nghĩa ứng dụng chắc chắn không chịu thêm overhead; `settings=profile` thường thu chi tiết hơn `default`.

### Vì sao `GC.heap_dump` không phải giải pháp không rủi ro?

`GC.heap_dump` tạo HPROF của **Java heap**, không phải toàn bộ native process. JDK 21 xếp lệnh này High impact và mặc định yêu cầu Full GC nếu không dùng `-all`. Việc thu file nhiều GiB có thể tạm dừng ứng dụng và làm đầy disk. Không nên thay `jhsdb` live bằng heap dump nặng nếu mục tiêu chỉ là lấy thread stack hoặc flags.

## 6. Quy trình quyết định khi service gặp sự cố

~~~text
Service Java lỗi / chậm / có dấu hiệu crash
    |
    +-- Có log, JFR, metrics hoặc hs_err? --> phân tích trước
    |
    +-- JVM còn sống và responsive?
    |       |
    |       +-- CÓ --> chọn jcmd/JFR/JMX theo câu hỏi,
    |       |           hạn chế tần suất và cân nhắc Impact
    |       |
    |       +-- KHÔNG --> không tự chuyển sang jhsdb --pid;
    |                   gọi incident owner và chuẩn bị phương án
    |                   lấy core theo runbook đã phê duyệt
    |
    +-- Có core dump sẵn từ lỗi cũ?
            |
            +-- CÓ --> chuẩn bị đúng binary, libraries và symbols;
            |           dùng jhsdb --exe --core trên bản core offline
            |
            +-- KHÔNG --> ưu tiên khôi phục service,
                        ghi nhận khoảng trống bằng chứng,
                        bổ sung kế hoạch thu dữ liệu lần sau
~~~

Không nên tiến hành song song nhiều công cụ “để chắc chắn”: thread dump, heap dump, native core và SA attach có mức tác động cộng dồn. Mỗi bước cần có câu hỏi cần trả lời, chủ sở hữu quyết định, thời điểm, giới hạn tài nguyên, cách xác minh sức khỏe service sau thao tác.

### Khi `jcmd` không phản hồi

Đó là một dữ kiện quan trọng, nhưng **không tự chứng minh** SA live attach là an toàn hay cần thiết. Nếu JVM/hệ điều hành đang không tiến triển hoặc diagnostic attach bị tắt/quyền khác, hãy:

1. Ghi lại thời điểm, PID/namespace, CPU/RSS, số thread, tình trạng disk, cgroup, host và các thông báo lỗi.
2. Kiểm tra có JFR, log hoặc thread dump được ghi trước đó không.
3. Đánh giá failover/recovery và cơ chế lấy core có sẵn trong runbook, hiểu rằng live core capture cũng gây pause.
4. Không gửi một loạt `jhsdb ... --pid` chỉ vì một lệnh nhẹ thất bại.
5. Sau khi có artifact, phân tích offline rồi so kết quả với log/metrics để tránh nhầm thời điểm.

## 7. Phân tích core dump offline bằng `jhsdb`

Đầu vào của postmortem thường gồm:

- **Core dump thật** (`core.*` hoặc tên hệ điều hành ghi), đã xác nhận là core của JVM liên quan.
- **Executable gốc** dùng để chạy JVM (đôi khi không tên là `java` nếu dùng JNI Invocation API).
- JDK/HotSpot build/vendor, architecture, OS, native libraries, `libjvm` và symbols phù hợp.
- `hs_err_pid*.log`, ứng dụng logs, GC logs, JFR recordings, timestamp và thông tin container/host.

Theo Oracle JDK 21, ví dụ **khi file đã tồn tại**:

~~~bash
jhsdb jstack --exe /opt/jdk-21/bin/java --core /secure/incident/core.12345
jhsdb jmap --heap --exe /opt/jdk-21/bin/java --core /secure/incident/core.12345
jhsdb jinfo --flags --exe /opt/jdk-21/bin/java --core /secure/incident/core.12345
~~~

Đường dẫn và tên file chỉ là **ví dụ**, không phải giá trị mặc định phải có trên mọi máy. Chỉ chạy khi core là của đúng executable/JVM build. Những lệnh trên **không dùng `--pid`**, nên không attach vào JVM production mới đang sống.

Một số tùy chọn hữu ích khi platform hỗ trợ:

~~~bash
jhsdb jstack --mixed --exe /opt/jdk-21/bin/java --core /secure/incident/core.12345
jhsdb jmap --histo --exe /opt/jdk-21/bin/java --core /secure/incident/core.12345
jhsdb clhsdb --exe /opt/jdk-21/bin/java --core /secure/incident/core.12345
~~~

- `--mixed` cố gắng hiện Java và native stack frames, phụ thuộc symbols và hệ điều hành.
- `--histo` tạo thống kê object heap theo class từ core, không là bằng chứng độc lập của memory leak.
- `clhsdb` cho phép khám phá sâu nội dung core. Nó có thể dùng nhiều CPU/RAM trên máy phân tích; không làm JVM production đang chạy bị attach.
- `jhsdb jmap --binaryheap` có thể ghi HPROF từ core khi dữ liệu và môi trường phù hợp; xem `jhsdb jmap --help` về `--dumpfile` và dung lượng file.
- Core thiếu vùng memory, bị cắt cụt hoặc không tương thích version/architecture có thể khiến SA fail; phải báo **giới hạn kết quả**, không chọn đại một runtime khác.

**Không truyền `hs_err_pid12345.log` vào `--core`.** `hs_err` là báo cáo văn bản về fatal error, không phải ảnh native memory của process. Không dùng core của service A với executable của service B chỉ vì cả hai cùng chạy Java.

## 8. Tạo core khi JVM đang sống cũng có chi phí

Sau khi đọc cảnh báo `jhsdb`, có thể có phản ứng “vậy cứ lấy core bằng `gcore` rồi phân tích”. Cách này **tránh SA live attach trong giai đoạn đọc**, nhưng `gcore` hoặc cơ chế native snapshot có thể tạm dừng process, dùng ptrace, đọc rất nhiều memory và ghi file lớn.

Rủi ro cụ thể:

- **Tạm dừng dịch vụ** để tạo một ảnh đủ nhất quán; thời gian phụ thuộc memory và cơ chế dump.
- **Disk đầy/quota** khi core rất lớn; tổng process memory không giới hạn bằng `-Xmx` vì còn native stacks, Metaspace, mapping và các vùng khác.
- **Ảnh chụp không đầy đủ** do limit của OS, container permissions, core filters hoặc crash trong lúc capture.
- **Bảo mật** vì core có thể chứa bearer token, passwords, dữ liệu khách hàng, nội dung request và object heap.
- **Không tương thích khi phân tích** nếu core, executable, shared libraries hoặc symbols không khớp.
- **Cascading failures** nếu ghi core làm nghẽn I/O trên cùng volume với data/log.

Do đó, tạo core live phải là **một thủ tục có phê duyệt**, giám sát dung lượng, vị trí lưu an toàn, kế hoạch rollback và chấp nhận pause đã được đánh giá. Không tự thay `ulimit`, `core_pattern`, `systemd-coredump` hoặc container security context trên production chỉ để làm được một lần dump.

**Phân biệt ngôn ngữ:**
- *Postmortem analysis* = phân tích sau sự cố từ dữ liệu đã lưu, không attach JVM gốc đang sống.
- *Core capture* = hành động lấy bằng chứng; nếu lấy từ live process thì vẫn có rủi ro.
- *Live Serviceability Agent attach* = hành động mà Oracle có cảnh báo đặc biệt về hang/crash.

## 9. Ví dụ Java 17+ an toàn: kiểm tra JVM bằng `jcmd` thay vì SA live

Để học cách quan sát thread và JVM, tạo một chương trình Java nhỏ với một worker ngủ hữu hạn. Ta cố tình **không gọi `jhsdb --pid`**, kể cả trên JVM test này, vì bài tập nhắm vào quy tắc tránh nguy hiểm.

Tạo file **`SafeDiagnosticsDemo.java`**:

~~~java
public final class SafeDiagnosticsDemo {
    public static void main(String[] args)
            throws InterruptedException {
        Thread worker = new Thread(() -> {
            try {
                Thread.sleep(120_000L);
            } catch (InterruptedException interrupted) {
                Thread.currentThread().interrupt();
            }
        }, "diagnostics-lab-worker");

        worker.start();
        System.out.println("PID=" + ProcessHandle.current().pid());
        System.out.println("Worker=" + worker.getName());
        worker.join();
        System.out.println("Finished");
    }
}
~~~

Biên dịch và chạy bằng JDK 17 trở lên:

~~~bash
javac SafeDiagnosticsDemo.java
java SafeDiagnosticsDemo
~~~

Đầu ra của ứng dụng trước khi chờ:

~~~text
PID=<PID thực tế được OS cấp, khác nhau mỗi lần chạy>
Worker=diagnostics-lab-worker
~~~

Trong khi `worker` đang ngủ, mở terminal khác trên **cùng host/namespace có quyền attach**, thay **12345** bằng PID thực:

~~~bash
jcmd 12345 VM.version
jcmd 12345 VM.info
jcmd 12345 Thread.print -l
~~~

Trong thời gian chờ, việc `Thread.print` thường có thể thấy `diagnostics-lab-worker` với trạng thái `TIMED_WAITING` và stack `Thread.sleep`; thread main chờ `join`. Trạng thái chính xác, line numbers và output `VM.info` phụ thuộc thời điểm, JVM và OS, **không có stdout cố định**. Sau khi worker hoàn tất, ứng dụng in:

~~~text
Finished
~~~

Lab minh họa một cách quan sát thread mà **không sử dụng SA live attach**. `Thread.print` vẫn có impact Medium, nên chỉ dùng có mục tiêu và không gọi trong vòng lặp vô hạn. Nếu không kết nối được bằng `jcmd` do PID/permission/namespace, không “chữa” bằng `jhsdb --pid`.

### Thực hành nhận diện lệnh sai

~~~text
Chỉ nhận diện, KHÔNG thực thi:

jhsdb jstack --pid <PID_THỰC>
jhsdb jmap --pid <PID_THỰC>
jhsdb debugd --pid <PID_THỰC>
~~~

Tất cả đều lựa chọn một **live PID**. Không cần tự làm treo/crash process để kiểm chứng cảnh báo của Oracle.

## 10. Quy trình chuẩn bị và xử lý sau JVM crash

### 10.1. Trước sự cố

- Quy định rõ ai được thao tác chẩn đoán trên service, mức impact chấp nhận được và thời điểm được phép.
- Cấu hình metrics, JFR hoặc log ở mức overhead phù hợp, có retention để bảo vệ dữ liệu trước khi process crash.
- Đặt chiến lược lưu `hs_err_pid*.log` và core dump phù hợp OS, quota và bảo mật, được kiểm thử trên staging. `-XX:ErrorFile` có thể điều chỉnh vị trí fatal error log nếu runtime hỗ trợ.
- Lưu release manifest: JDK vendor/build, container digest, JVM flags, native libraries và symbols cần thiết.
- Kiểm thử incident response với một JVM **cô lập, không có dữ liệu thật**; không thử live `jhsdb` trên service đang phục vụ.
- Dự trù disk, encryption, access control và thời hạn xóa core/HPROF.

### 10.2. Khi sự cố xảy ra

1. Ghi timestamp, host/container, PID, tình trạng health check, GC/JFR metrics và mức tải.
2. Xem hệ thống còn đáp ứng không; chọn một phép đo tương ứng với câu hỏi và tác động.
3. Cân nhắc traffic drain/failover nếu cần bảo vệ request đang thực hiện.
4. Nếu đã có core từ crash, ưu tiên đọc **offline**. Nếu chưa có và cần capture live, chỉ quyết định theo runbook về pause/size/permissions.
5. Không làm tăng severity bằng một lệnh SA live không được phép.
6. Sau thu thập, xác nhận request success, latency, queue/backlog, restarts và dung lượng đĩa.

### 10.3. Bộ artifact nên lưu

~~~text
incident-2026-10-29/
  hs_err_pid12345.log
  core.12345
  runtime-manifest.txt
  gc.log
  application.log
  recording.jfr
  checksums.txt
~~~

Đây là ví dụ tổ chức hồ sơ, **không phải** JDK tự động ghi đúng toàn bộ tên file này. Ghi rõ bản ghi nào có thật, file nào không thể tạo và lý do. Một sự cố JVM native crash có thể không sinh HPROF; `OutOfMemoryError` của Java có thể sinh HPROF với `-XX:+HeapDumpOnOutOfMemoryError` nhưng không đồng nghĩa có OS core.

Đặc biệt, container bị **OOMKilled** bởi OS có thể mất process trước khi JVM kịp ghi `hs_err` hoặc HPROF. Không attach lại PID đã chết để “lấy bổ sung”. Hãy dùng dữ liệu telemetry đã lưu và chuẩn bị cho lần sau.

## 11. So sánh ba loại bằng chứng dễ bị nhầm

| Artifact | Chứa gì | Sử dụng thế nào | Không thay thế được |
| --- | --- | --- | --- |
| `hs_err_pid*.log` | Text report của fatal HotSpot error: signal, problematic frame, threads, VM flags, modules | Đọc ngay để xác định điểm crash và version | **Không phải** core dump |
| **OS core dump** | Snapshot memory/state process theo OS và core settings | `jhsdb ... --exe ... --core ...`, native debugger | Không phải recording timeline; rất lớn, nhạy cảm |
| **HPROF heap dump** | Java heap objects và reference graph | Eclipse MAT/histogram/dominator tree | Không phản ánh đầy đủ native stacks/OS memory |
| **JFR `.jfr`** | Các event được ghi theo thời gian (GC, allocation sample, thread/locks, I/O) | `jfr summary`, Java Mission Control | Không phải toàn bộ memory snapshot |

Có `hs_err` không đồng nghĩa có core; có JFR không đồng nghĩa có chính xác trạng thái tại thời điểm crash; có HPROF không có nghĩa biết nguyên nhân native SIGSEGV. Chọn artifact theo giả thuyết, không chọn theo tên công cụ dễ nhớ nhất.

## 12. Bốn tình huống thường gặp

### A. “Chỉ lấy stack một lần thôi”

Ứng dụng chậm, người trực ca muốn chạy `jhsdb jstack --pid` vì tin nó giống `jcmd Thread.print`. Nếu process bị treo và crash lúc detach, một diagnostic biến thành outage.

**Hướng xử lý:** ưu tiên metrics/logs/JFR, rồi `jcmd Thread.print` khi JVM còn phản hồi và mức tác động cho phép. Nếu JVM treo nặng, lên phương án core theo quy trình, không tự tăng rủi ro SA live.

### B. Remote `debugd` tưởng là cách tránh rủi ro

Người vận hành khởi chạy `jhsdb debugd --pid` trên host rồi kết nối từ laptop. Kênh từ xa không làm backend bớt xâm lấn: **debugd vẫn attach PID sống**; còn tăng bề mặt RMI/network nếu không được cô lập.

**Hướng xử lý:** nếu cần remote SA, chỉ phục vụ **core file đã có** trong môi trường quản trị an toàn, hoặc phân tích trực tiếp offline.

### C. Lấy core từ process sống ngay trên volume ứng dụng

Một core vài GiB làm đầy volume logs. Service không còn ghi log và instance khác cùng host bị ảnh hưởng. Mặc dù bước `jhsdb --core` sau đó offline, **hành động tạo core** đã tác động đáng kể.

**Hướng xử lý:** đánh giá quota, volume riêng, pause, quyền, encryption, nơi lưu; chỉ capture khi được phê duyệt.

### D. JVM cũ crash, instance mới chạy lại

PID mới không chứa trạng thái đã crash. Attach `jhsdb --pid` vào instance mới vừa mất bằng chứng cũ vừa có thể làm mất instance đang phục vụ.

**Hướng xử lý:** dùng core của instance cũ với executable/runtime phù hợp; đối chiếu `hs_err`/log/JFR trước khi đưa ra kết luận.

## 13. Checklist trước khi gõ bất kỳ lệnh chẩn đoán nào

- [ ] Đã kiểm tra **đúng PID**, đúng host/container namespace, đúng JVM và quyền thao tác.
- [ ] Đã xác định câu hỏi: thread hang, native crash, Java heap leak, GC pressure hay RSS/native memory?
- [ ] Đã đọc mức Impact của command theo **JDK của JVM đích**; không mặc định mọi `jcmd` đều nhẹ.
- [ ] Nếu thấy `jhsdb` cùng `--pid` trên service sống, **dừng lại**, không chạy như diagnostic thường kỳ.
- [ ] Có dữ liệu đã lưu (JFR, logs, `hs_err`, core) có thể đọc trước không?
- [ ] Nếu định thu core/heap dump, đã chấp nhận pause, disk, I/O, security và nguy cơ mất tiến trình chưa?
- [ ] Nếu đọc core bằng `jhsdb` offline, đã xác minh đúng binary, build, libraries và file core đầy đủ chưa?
- [ ] Đã xác định người phê duyệt, khả năng failover và bước xác minh service khỏe lại sau thao tác chưa?

**Quy tắc ghi nhớ:** `jhsdb --pid` là **high-risk live SA attach**; `jhsdb --exe --core` là **postmortem core analysis**; `jcmd`/JFR là các lựa chọn quan sát JVM còn sống với mức tác động **phải đánh giá riêng**. Đừng để thao tác điều tra gây ra sự cố lớn hơn lỗi ban đầu.

## 14. Tự kiểm tra

**Câu 1:** Tại sao `jhsdb jinfo --pid` vẫn có thể nguy hiểm dù chỉ muốn xem flags?

*Đáp án:* Vì vấn đề nằm ở **SA attach tới live process**, không nằm ở việc đầu ra chỉ đọc. Oracle cảnh báo process có thể hang trong lúc attach và crash khi detach.

**Câu 2:** Có thể thay `--pid` bằng `--exe ... --core ...` khi đã có core không?

*Đáp án:* Có. Cách đọc offline phân tích dữ liệu đã lưu, không attach JVM production đang chạy; cần core thật và executable tương thích. Nếu chưa có core thì không thể thay thế bằng `hs_err` text file.

**Câu 3:** Nếu `jcmd Thread.print` trả timeout thì có nên lập tức chạy `jhsdb jstack --pid` không?

*Đáp án:* Không. Timeout chỉ cho thấy diagnostic command không trả lời trong điều kiện hiện tại; xem trạng thái host/process và runbook thu core, đồng thời ưu tiên bảo vệ service.

**Câu 4:** Core được thu từ process sống bằng công cụ OS có hoàn toàn không tác động không?

*Đáp án:* Không. Nó có thể tạm dừng tiến trình, dùng CPU/I/O/disk lớn và chịu quota/permissions; cần đánh giá trước.

**Câu 5:** JFR, HPROF và core dump có cùng nội dung không?

*Đáp án:* Không. JFR là event timeline; HPROF là Java heap snapshot; native core là process snapshot theo OS. Chúng bổ sung nhau nhưng không thay thế nhau.

## Tài liệu tham khảo chính thức

- Oracle JDK 21 — **The jhsdb Command** (cảnh báo live attach, `--pid`, `--exe`/`--core`, các mode): https://docs.oracle.com/en/java/javase/21/docs/specs/man/jhsdb.html
- Oracle JDK 21 — **The jcmd Command** (các mức Impact; `VM.info`, `Thread.print`, `GC.heap_dump`, `JFR.start`): https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html
- Oracle JDK 21 — **Diagnostic Tools** (postmortem, SA, JFR, `jcmd` và các ví dụ với core): https://docs.oracle.com/en/java/javase/21/troubleshoot/diagnostic-tools.html
- Oracle JDK 21 — **Troubleshooting Guide** (fatal error, core dumps và điều tra sự cố): https://docs.oracle.com/en/java/javase/21/troubleshoot/
