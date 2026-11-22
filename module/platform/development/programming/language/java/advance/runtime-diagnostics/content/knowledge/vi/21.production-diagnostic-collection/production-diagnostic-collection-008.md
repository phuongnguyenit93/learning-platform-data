# 21.8 Tránh làm mất bằng chứng khi restart và ghi rõ các tác động do lệnh chẩn đoán tạo ra

## 1. Vấn đề: restart có thể xóa cả triệu chứng lẫn dấu vết

Một JVM chạy chậm, nhiều request timeout hoặc tăng bộ nhớ dần. On-call restart, service nhanh trở lại và dashboard đổi sang PID mới. Nhưng những Java thread stacks, lock owners, heap objects, JFR buffers chưa được xuất, GC/JIT counters, native memory mappings và trạng thái connection pool trong JVM cũ đã mất. Báo cáo “restart xong hết lỗi” **không chứng minh được root cause**.

Thậm chí thao tác chẩn đoán trước restart cũng có thể **thay đổi đối tượng đang được đo**. Thread dump đòi JVM phối hợp và tạo output; heap histogram/heap dump có thể gây pause, GC, disk I/O; bật JFR tạo CPU/memory overhead; thay đổi logging làm log mới khác log cũ. Nếu không ghi thời điểm và tác động của từng lệnh, người phân tích có thể nhầm **hậu quả của công cụ** thành **triệu chứng ứng dụng**.

Mục tiêu:

- Phân loại bằng chứng dễ mất khi **process restart**, container replacement, pod eviction, log rotation, forced kill và OOMKilled.
- Thu thập theo mức ưu tiên: **dữ liệu ngoài JVM → snapshot nhẹ → snapshot có tác động → chỉ khi cần mới lấy dump nặng**.
- Biết khi nào không nên trì hoãn restart, và ghi rõ **không lấy được gì, vì sao**.
- Đánh dấu chính xác **PID, start time, host/container namespace, JDK, UTC timestamp, incident ID**.
- Ghi **command ledger**: lệnh/flags, start/end, expected impact, observed impact, exit code, output path/size/checksum và quyết định tiếp theo.
- Hiểu `JFR.dump` khác `JFR.stop`; heap dump khác core; Java `OutOfMemoryError` khác kernel/cgroup OOMKilled; graceful termination khác SIGKILL.
- Có bài lab Java 17+ minh họa bằng chứng ghi ra file sống qua hai lần chạy JVM, nhưng shutdown hook **không phải phương án bảo đảm**.

**Nguyên tắc:** ưu tiên trạng thái **chỉ còn tồn tại khi đúng JVM đang sống**, nhưng không hy sinh tính sẵn sàng của hệ thống để chạy một lệnh chẩn đoán vượt quá ngân sách thời gian/tài nguyên.

## 2. Phân loại bằng chứng trước khi mất

| Nguồn | Điều có thể mất sau restart | Biện pháp bảo quản |
| --- | --- | --- |
| Live Java threads, monitor/lock state, park/wait stacks | Trạng thái thread và lock của incarnation lỗi | `jcmd Thread.print -l` hoặc thread dump phù hợp bản JDK, ghi timestamp |
| Java heap, objects, class loaders, metaspace | Objects/GC roots, state của ứng dụng đang lỗi | Heap dump/histogram **chỉ khi còn ngân sách**; không ép mặc định |
| JVM flags, process command line, uptime, GC counters, compiler/code-cache metrics | Số liệu reset hoặc configuration đổi theo JVM mới | `VM.version`, `VM.command_line`, `VM.flags`, `VM.uptime` + build/UID |
| Active JFR recording và repository | Buffer chưa flush; retention window ghi đè; file trong container bị hủy | `JFR.check` rồi `JFR.dump` ra location bền; kiểm tra file |
| GC/unified logs, stdout/stderr | Logrotate, container replacement, node eviction, retention ngắn | Centralized logs, export trước restart, ghi time range |
| `hs_err_pid*.log`, OS core, HPROF | Có thể chưa được tạo; file nằm trong local disk tạm | Cấu hình error/dump paths, core policy, volume hoặc export |
| RSS, open FDs/sockets, maps, cgroup memory, process tree | PID biến mất và OS counters thay đổi | `ps`, `/proc`, `ss`, OS/container monitoring |
| Downstream DB/pool metrics, application tracing | Có thể tồn tại ở backend ngoài JVM nhưng không mãi | Giữ query/dashboard range, incident IDs, log/trace correlation |

**Không trộn incarnations:** sau khi restart, OS có thể tái sử dụng cùng PID; trong container PID có thể luôn là 1. Vì vậy số PID **một mình không phải định danh**. Ghi thêm process start time, container ID, pod UID, image digest, JDK build và thời gian UTC.

Một core dump của OS **khác** HPROF heap dump; `hs_err_pid*.log` lại là báo cáo text về fatal error. Java OOME không bảo đảm có OS core; container OOMKilled do kernel gửi SIGKILL thường **không cho JVM kịp ghi** heap dump/JFR/shutdown hook. Những artifact này cần chuẩn bị trước hoặc xuất chủ động lúc process còn sống.

## 3. Thứ tự quyết định trong sự cố thật

Không phải lúc nào “capture trước, restart sau” cũng đúng tuyệt đối. Nếu service đang vi phạm SLO nặng, disk sắp đầy hoặc kernel chuẩn bị OOMKill, incident commander có thể quyết định restart ngay và **báo rõ phần bằng chứng không lấy được**. Một heap dump vài GiB không đáng đổi lấy việc kéo dài outage hoặc làm cạn dung lượng node.

Một quy trình cân bằng:

1. **T0 – ghi bối cảnh và time budget:** severity, thời điểm phát hiện, môi trường, người chịu trách nhiệm, SLO, thời gian tối đa dành cho capture.
2. **T1 – chụp dữ liệu đã có bên ngoài process:** dashboard CPU/RSS/GC, error/trace logs, request rate, downstream latency, OOM/eviction events; lưu time range/query.
3. **T2 – xác định chính xác JVM lỗi:** PID + start time/uptime, JDK version, flags, deployment image, container ID, filesystem/memory headroom.
4. **T3 – lấy dữ liệu ít/mức vừa tác động:** thread dump nếu có lý do, JFR dump khi recording đang chạy, NMT summary nếu đã bật NMT từ startup.
5. **T4 – cân nhắc tác vụ nặng có phê duyệt:** histogram, HPROF, OS core; phải có disk/CPU/pause/secret-handling budget, không mặc định.
6. **T5 – xác minh file ngoài vòng đời JVM:** output có giá trị, exit code 0, file tồn tại, size hợp lý, checksum, đã copy ra nơi bền vững.
7. **T6 – restart và ghi lý do:** ai quyết định, lúc nào, bằng phương thức gì, PID/incarnation mới.
8. **T7 – so sánh trước/sau:** health, throughput, CPU, GC, memory, p95/p99; gắn dấu tác động của từng lệnh và việc reset counters.

Một ví dụ về deadline **minh họa**, không phải SLA bắt buộc: chỉ dành tối đa 60–90 giây cho snapshot ít tác động; **không chạy heap dump** khi container đã còn rất ít memory/disk. Ngân sách thật do kiến trúc, tải, thời hạn khôi phục và người phê duyệt quyết định.

## 4. Bảng tác động của công cụ – phải ghi vào ledger

Mức `Low/Medium/High` bên dưới là định hướng từ `jcmd` của Oracle JDK 21, không có nghĩa chi phí cố định. Tác động thực còn do số threads, size heap, GC, storage, container quotas và bản JDK.

| Công cụ/hành động | Bằng chứng cần lấy | Can thiệp có thể phát sinh |
| --- | --- | --- |
| `date`, `ps`, `/proc/<PID>/status`, external metrics | UTC, process identity, RSS, FD, cgroup state | OS overhead nhỏ, quyền đọc/namespace và race nếu PID đã exit |
| `jcmd <PID> VM.version`, `VM.command_line`, `VM.flags` | JVM vendor/build, launch options, flags | Thường **Low**, attach có thể chờ; command line chứa secrets |
| `jcmd <PID> JFR.check` | Có recording nào đang chạy? | Thường **Low**, chỉ xem trạng thái |
| `jcmd <PID> JFR.dump name=... filename=...` | Xuất những JFR events còn được giữ | **Low** theo docs nhưng vẫn ghi file I/O; **không dừng recording** |
| `jcmd <PID> Thread.print -l` | Java platform-thread stacks và locks | **Medium**: phụ thuộc số thread, thời gian JVM phối hợp, output lớn |
| `jcmd <PID> Thread.dump_to_file -format=json ...` (JDK phù hợp) | Snapshot gồm virtual và platform threads | Dung lượng lớn khi có rất nhiều virtual threads; không phải timeline |
| `jcmd <PID> VM.native_memory summary` | Native memory phần HotSpot theo dõi | NMT phải bật khi startup; có chi phí của NMT và không bao phủ mọi native allocation |
| `jcmd <PID> GC.heap_info` | Heap summary | Oracle xếp **Medium** |
| `jcmd <PID> GC.class_histogram` | Histogram objects/classes | **High**: quét heap, có thể gây pause/GC; tùy mode và JVM |
| `jcmd <PID> GC.heap_dump /path/file.hprof` | Heap dump HPROF | **High**: tốn I/O/CPU/disk, **mặc định yêu cầu full GC trừ khi dùng `-all`** |
| `jcmd <PID> GC.run` | Gửi yêu cầu `System.gc()` | **Thay đổi heap/GC state**; không phải phép quan sát thuần túy |
| `jcmd <PID> JFR.start` hoặc đổi recording settings | Bắt đầu thu event mới | Overhead sampling/recording; không khôi phục timeline trước khi bắt đầu |
| `jcmd <PID> VM.log ...` / `VM.native_memory baseline` | Thay log configuration hoặc mốc diff NMT | **Đổi state chẩn đoán** và dữ liệu so sánh, có thể rotate log |
| `jhsdb ... --pid` | HotSpot SA live inspect | **Rủi ro cao**: tài liệu Oracle cảnh báo có thể làm JVM treo/crash khi detach |
| `kill -QUIT <PID>` (Unix/HotSpot) | Có thể sinh thread dump vào output JVM | Signal và output stream không trung tính; file/log có thể thất lạc |
| `SIGTERM` / restart / `SIGKILL` | Dừng JVM | Mất memory state; hard kill không cho Java shutdown hook chạy |

**GC.heap_dump `-all` không có nghĩa “an toàn”:** có thể tránh request full GC mặc định theo Oracle nhưng vẫn là thao tác High impact, dump thêm unreachable objects và có thể làm thay đổi cách diễn giải heap. Tương tự `GC.class_histogram -all` thay đổi tập object được đếm. Luôn lưu **option chính xác** cùng artifact.

Các cảnh báo cần phân biệt:

- **Expected impact**: rủi ro từ tài liệu và kiến trúc, ví dụ “histogram high impact, có thể pause”.
- **Observed impact**: con số thực từ log/metrics trước–trong–sau lệnh, ví dụ thời lượng command, GC count/pause/CPU/p99. Nếu chưa đo, ghi **unknown**, không ghi 0.
- **Causality**: p99 tăng cùng thời điểm heap dump là mối tương quan; cần kiểm tra workload, GC log và các yếu tố nhiễu trước khi khẳng định do lệnh.

## 5. Runbook Linux: lấy mẫu nhẹ và giữ nguyên provenance

Chỉ thực hiện trên JVM mà bạn có quyền quản trị. Đây là **ví dụ thao tác có chọn lọc**, không phải yêu cầu chạy hàng loạt trên production. Thay PID/incident ID bằng thông tin đã xác minh. `OUT` phải thuộc storage bền, đủ dung lượng và bị giới hạn quyền truy cập.

### 5.1 Snapshot OS trước khi lệnh JVM có thể can thiệp

~~~bash
PID=12345
INCIDENT=INC-2026-10-29-001
OUT="/secure/persistent/incidents/$INCIDENT/$PID"
umask 077
mkdir -p "$OUT"

date -u '+%Y-%m-%dT%H:%M:%SZ' > "$OUT/start-utc.txt"
ps -o pid,ppid,lstart,etime,rss,comm -p "$PID" > "$OUT/process.txt"
cat "/proc/$PID/status" > "$OUT/status.txt"
cat "/proc/$PID/smaps_rollup" > "$OUT/smaps-rollup.txt"
cat "/proc/$PID/limits" > "$OUT/limits.txt"
cat "/proc/$PID/cgroup" > "$OUT/cgroup.txt"
~~~

Lưu cả stderr/exit code nếu lệnh thất bại; thiếu quyền, file không tồn tại, OS khác Linux và PID đã exit là nguyên nhân phổ biến. `ps` và `/proc` cho trạng thái tức thời **của đúng process**; về sau không được thay thế bằng PID mới khi file cũ không thu được. `smaps_rollup` phụ thuộc kernel.

### 5.2 Diagnostic commands có chủ đích

~~~bash
jcmd "$PID" VM.version > "$OUT/version.txt" 2>&1
jcmd "$PID" VM.command_line > "$OUT/command-line.txt" 2>&1
jcmd "$PID" VM.flags > "$OUT/flags.txt" 2>&1
jcmd "$PID" VM.uptime > "$OUT/uptime.txt" 2>&1
jcmd "$PID" JFR.check > "$OUT/jfr-check.txt" 2>&1
# Chỉ khi cần lock/thread evidence và có pause budget:
jcmd "$PID" Thread.print -l > "$OUT/thread-01.txt" 2>&1
~~~

Không phải command nào cũng nên chạy theo cùng thứ tự nếu app đã gần chết: nếu chỉ có 10 giây, ưu tiên dữ liệu bên ngoài JVM + JFR dump sẵn có; không để thread dump làm trễ việc phục hồi quá ngân sách.

**Lưu timing và return code.** Ví dụ một lệnh:

~~~bash
START_MS="$(date +%s%3N)"
jcmd "$PID" VM.version > "$OUT/version-2.txt" 2>&1
STATUS=$?
END_MS="$(date +%s%3N)"
printf 'command=VM.version exit_code=%s duration_ms=%s\n' \
  "$STATUS" "$((END_MS - START_MS))" >> "$OUT/ledger.txt"
~~~

`date +%s%3N` là GNU date, không bảo đảm trên macOS/BSD. Runbook production nên ghi start/end UTC, operator ID, tool version, impact và destination. **Không dùng `jcmd 0`** vì theo tài liệu nó có thể gửi command cho **tất cả JVM** phù hợp trên host, vượt xa một incident PID.

Nếu dump lần hai, ghi khoảng cách giữa hai lần và số threads. Một thread dump không đủ chứng minh deadlock kéo dài hoặc giúp đo thời gian waiting; chuỗi snapshots + lock owner + metrics đáng tin hơn.

### 5.3 JFR: snapshot khác stop

Sau khi `JFR.check` xác nhận recording name, chẳng hạn `baseline`:

~~~bash
jcmd "$PID" JFR.dump name=baseline filename=/secure/persistent/jfr/before-restart.jfr
~~~

`JFR.dump` **ghi dữ liệu đang được giữ ra file mà recording vẫn chạy**; `JFR.stop` mới kết thúc recording. Không nhầm hai lệnh. Nếu muốn giữ lại trước restart, cần kiểm tra **đường dẫn file theo filesystem namespace của JVM target**: trong Kubernetes một path nhìn thấy ở container không nhất thiết tồn tại trên terminal host và ngược lại. Tên file đầu ra nên chứa incident ID/PID/timestamp; không ghi đè bản đã có.

JFR chỉ giữ sự kiện trong **retention window** (`maxage/maxsize`, repository và buffers) và theo loại event được bật. Dump tại phút thứ 30 không đảm bảo còn phút thứ 1. Nếu JFR chưa chạy, `JFR.start` mới **bắt đầu từ lúc bật**, không thể “ghi lại quá khứ” trước incident. Bật JFR cũng tạo overhead và cần ledger.

`JFR.dump` có thể trả lỗi do không có recording, thiếu quyền, thiếu disk; phải kiểm tra **file tồn tại và đọc được** chứ không chỉ nhìn exit code. Đọc bằng `jfr summary /path/file.jfr` trên máy có JDK tương thích sau khi file đã copy ra storage an toàn.

### 5.4 Heap dump/histogram: lệnh có tác dụng phụ, không phải baseline mặc định

~~~bash
# Chỉ xem syntax theo chính JDK đang chạy:
jcmd "$PID" help GC.heap_dump
jcmd "$PID" help GC.class_histogram

# HIGH IMPACT: chỉ dùng khi đã có approval, disk/memory/latency budget.
jcmd "$PID" GC.class_histogram > "$OUT/histogram.txt" 2>&1
jcmd "$PID" GC.heap_dump /secure/persistent/dumps/before-restart.hprof
~~~

Heap dump mặc định yêu cầu full GC trừ khi `-all` được bật theo JDK 21; công cụ vẫn tốn disk/CPU và có thể khiến process thiếu headroom. Nếu đã gọi một lệnh có GC tác động, so sánh heap used/GC count **sau lệnh** với trước phải ghi dấu can thiệp. HPROF có thể chứa token, password, dữ liệu khách hàng; không gửi trực tiếp vào ticket công khai.

Nếu nghi Java heap leak nhưng app đã sắp OOMKilled, **có thể bỏ qua heap dump** và ghi rõ thiếu bằng chứng để bảo vệ availability. Các lựa chọn nhẹ hơn gồm GC logs/JFR đã có hoặc OS/cgroup memory history. Không dùng `GC.run` để “làm sạch” trước khi ghi hiện trạng mà không nói rõ đây là thay đổi state.

### 5.5 Trước restart, xác thực artifact và chuyển khỏi vòng đời process

~~~bash
date -u '+%Y-%m-%dT%H:%M:%SZ' > "$OUT/capture-end-utc.txt"
ls -lah "$OUT"
find "$OUT" -maxdepth 1 -type f -name '*.txt' -print0 |
  sort -z | xargs -0 -r sha256sum > "$OUT/manifest.sha256"
~~~

Kiểm tra file chứa dữ liệu hợp lệ: `thread-01.txt` có thể chỉ chứa “Unable to attach to target VM”, chứ không phải thread dump. File HPROF chưa ghi xong không được hash như final. Khi bản đầu nằm trong ephemeral container, phải **copy/export ra persistent store rồi kiểm tra hash của bản copy** trước restart.

Checksum cho biết integrity qua copy, **không chứng minh** file đã lấy từ đúng PID; phải kèm metadata. Đừng xóa/rename evidence gốc hoặc ghi đè snapshot của thời điểm trước.

## 6. Kubernetes/containers: các bẫy mất evidence

### Kubernetes `--previous` chỉ là phương án cứu vãn

~~~bash
# Ví dụ namespace=payments, pod=api-7f9b6c, container=api:
kubectl -n payments get pod api-7f9b6c -o yaml > pod-before.yaml
kubectl -n payments describe pod api-7f9b6c > describe-before.txt
kubectl -n payments logs api-7f9b6c -c api --timestamps > current.log
kubectl -n payments logs api-7f9b6c -c api --previous --timestamps > previous.log
~~~

`kubectl logs --previous` chỉ lấy logs của instance trước **nếu còn được node lưu**. Kubernetes mặc định chỉ giữ một terminated container logs khi restart, và log rotation/pod eviction có thể loại dữ liệu đó. Nếu pod bị xóa, không thể chắc còn logs qua API. Dùng centralized logging, export với UTC/correlation ID và kiểm tra retention.

Chụp pod UID, container ID, restart count, image digest, node, PID namespace, cgroup memory events và quota. Process có PID 1 **trong container** không đồng nghĩa PID 1 của host. Một lệnh `kubectl exec` sau rollout có thể chạm **JVM mới**, không phải process đã phát sinh lỗi.

### Docker/storage và shutdown

File trong container writable layer hoặc `/tmp` không có **bảo đảm sống qua container replacement**. Bind mount, PVC hoặc hệ thống chuyển file sang object store bền hơn, nhưng vẫn phải kiểm tra permissions/quota và copy completion. Trên cùng container chỉ restart process có thể chưa xóa mọi file, nhưng không được dựa vào sự may mắn đó cho incident retention.

Khi shutdown, Java shutdown hook có thể chạy trên quá trình thoát bình thường, nhưng **SIGKILL không cho hook thực thi**. Kernel OOM kill, node crash, pod force kill hay hết grace period có thể cắt ngang việc xuất JFR/heap/log. Không khẳng định `dumponexit=true` hoặc `-XX:+HeapDumpOnOutOfMemoryError` luôn sinh artifact khi **OOMKilled**. Java-thrown `OutOfMemoryError` và OS OOMKilled là hai tình huống khác nhau.

Nếu dùng `systemd` và có quyền, kiểm tra `journalctl -u <unit>` và `coredumpctl list/info` để biết core/log còn không; core file không phải HPROF. Core và `hs_err_pid` có thể chứa secrets, nên dùng môi trường phân tích có kiểm soát.

## 7. Chuẩn bị giữ dấu vết ngay từ startup

Khi thiết kế vận hành, một số JVM options có thể bố trí artifact vào **volume bền** ngay từ đầu. Đây là **các lựa chọn độc lập**, không phải một chuỗi lệnh shell:

~~~text
-XX:ErrorFile=/persistent/incidents/hs_err_pid%p.log
-XX:+HeapDumpOnOutOfMemoryError
-XX:HeapDumpPath=/persistent/incidents
-XX:StartFlightRecording=name=baseline,settings=default,disk=true,maxage=20m,maxsize=256m,dumponexit=true,filename=/persistent/incidents/on-exit.jfr
-Xlog:gc*:file=/persistent/logs/gc.log:time,uptime,level,tags:filecount=5,filesize=20M
~~~

Điều kiện:

- `ErrorFile` chỉ có ích khi HotSpot **có cơ hội ghi** fatal-error log; đường dẫn phải tồn tại/writable.
- `HeapDumpOnOutOfMemoryError` không tương đương “tránh mất bằng chứng ở mọi OOM”; nếu OS kill trước, JVM có thể không tạo file.
- `StartFlightRecording` với `disk=true` ghi repository theo retention; `dumponexit=true` hỗ trợ xuất khi JVM thoát **thành công theo luồng được hỗ trợ**, không bảo đảm hoàn tất khi hard kill.
- Rotation của `-Xlog` sẽ xóa/đè các file cũ nếu collector không thu kịp; chọn `filecount/filesize` theo retention mục tiêu.
- Heap/core/JFR có thể tiêu tốn rất nhiều đĩa và chứa secrets. Đặt cảnh báo disk, access control, lifecycle policy và retention trên destination.

Đừng vừa tăng liên tục volume ghi log vừa chạy heap dump khi node sắp đầy. Ngoài performance và availability, **dữ liệu crash/heap** là dữ liệu nhạy cảm cần phê duyệt người được xem, hạn lưu và redaction.

## 8. Nhật ký tác động (diagnostic ledger): mỗi command có lý do và hiệu ứng

Tối thiểu mỗi diagnostic action có:

| Trường | Cách ghi |
| --- | --- |
| `incident_id`, `actor`, `approval` | Người chịu trách nhiệm và lý do |
| `start_utc` / `end_utc` / `duration_ms` | Timestamp có thể đối chiếu timeline |
| `node/pod/container/PID/process_start` | Xác định đúng JVM incarnation |
| `command` và options | Lệnh nguyên văn sau khi redacted secrets; kể cả `-all`, `-l` và sampling settings |
| `expected_impact` | Low/Medium/High theo tài liệu/đặc điểm workload, GC/safepoint/I/O risk |
| `observed_impact` | GC pause/count, CPU, p99, disk bytes, error, thread pause đo được |
| `exit_code`, `stderr` | Thành công hay lỗi attach/permission; không ghi “đã thu” nếu failed |
| `output_uri`, `bytes`, `sha256` | Vị trí storage bền, kích thước, integrity hash |
| `limitations` | Mẫu thiếu, JFR chưa bật, file bị rotation, process exit, snapshot không đầy đủ |
| `restart` | Ai quyết định, phương pháp/UTC, JVM PID mới, điều không thu được |

Ví dụ **minh họa**, không phải incident thực:

~~~text
incident=INC-2026-10-29-001
start_utc=2026-10-29T10:14:21Z
target=payments/api-7f9b6c;container=api;pid=12345
command=jcmd 12345 Thread.print -l
expected_impact=medium; actor=oncall; approval=INC-2026-10-29-001
duration_ms=850; exit_code=0; output=thread-01.txt; bytes=294321
observed=thread snapshot created; effect on p99 unknown
limitations=one instant only; no contention duration inference
~~~

Nếu không đo được thực tế, hãy ghi `unknown`, không bịa `0 ms pause`. Tách expected impact (rủi ro có thể có) với observed impact (số đo). Khi quay lại phân tích, gắn command timestamps lên đồ thị SLO, CPU, GC, RSS; nếu p99 tăng cùng lúc dump, cần cân nhắc traffic và GC khác nữa trước khi kết luận nhân quả.

## 9. Lab Java 17+: checkpoint tồn tại qua hai JVM incarnations

Lab này **không tự restart, không tạo crash và không chạy heap dump**. Chương trình tạo một file evidence riêng theo PID/UUID, ghi các checkpoint và một phép đo heap-used, rồi kết thúc. Chạy hai lần cùng thư mục để thấy các dấu vết của hai process tách biệt và file không bị ghi đè. Có shutdown hook minh họa graceful exit, nhưng **không được tin rằng hook sẽ chạy khi SIGKILL/node crash**.

Tạo file **`EvidenceCheckpointLab.java`**:

~~~java
import java.io.IOException;
import java.lang.management.ManagementFactory;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.time.Instant;
import java.util.UUID;

public final class EvidenceCheckpointLab {
    private static Path artifact;

    private static synchronized void append(String line) {
        try {
            Files.writeString(artifact,
                    Instant.now() + " " + line + System.lineSeparator(),
                    StandardCharsets.UTF_8, StandardOpenOption.APPEND);
        } catch (IOException e) {
            System.err.println("EVIDENCE_WRITE_FAILED="
                    + e.getClass().getSimpleName());
        }
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 2) {
            throw new IllegalArgumentException(
                    "Usage: EvidenceCheckpointLab <directory> <seconds>");
        }
        int seconds = Integer.parseInt(args[1]);
        if (seconds < 1 || seconds > 120) {
            throw new IllegalArgumentException("seconds must be 1..120");
        }
        Path directory = Path.of(args[0]).toAbsolutePath().normalize();
        Files.createDirectories(directory);

        long pid = ProcessHandle.current().pid();
        artifact = directory.resolve(
                "evidence-" + pid + "-" + UUID.randomUUID() + ".log");

        String header = "pid=" + pid + System.lineSeparator()
                + "java=" + System.getProperty("java.version")
                + System.lineSeparator()
                + "startUtc=" + Instant.now() + System.lineSeparator();
        Files.writeString(artifact, header, StandardCharsets.UTF_8,
                StandardOpenOption.CREATE_NEW);

        Runtime.getRuntime().addShutdownHook(
                new Thread(() -> append("shutdownHook=called"), "evidence-hook"));

        append("phase=start");
        System.out.println("PID=" + pid);
        System.out.println("EVIDENCE_FILE=" + artifact);
        System.out.println("PHASE=READY");

        Thread.sleep(seconds * 1_000L);
        long heapUsed = ManagementFactory.getMemoryMXBean()
                .getHeapMemoryUsage().getUsed();
        append("heapUsedBytes=" + heapUsed);
        append("phase=finished");
        System.out.println("PHASE=FINISHED");
    }
}
~~~

Giải thích:

1. `PID + UUID` ngăn ghi đè file incident của lần chạy khác; `CREATE_NEW` thất bại thay vì thay nội dung file đã có.
2. `append()` ghi UTC cho từng mốc cùng Java version/PID; đây là checkpoint, **không phải đầy đủ heap dump** hay OS RSS.
3. `MemoryMXBean.getHeapMemoryUsage().getUsed()` đo số byte Java heap-used tức thời, khác NMT `committed`, OS RSS và retained size.
4. `shutdownHook=called` xuất hiện trong exit bình thường; không có nghĩa hard kill hoặc filesystem hỏng sẽ ghi được.
5. Chỉ một directory thật sự **bền qua vòng đời container/pod** mới giữ được các file. File trong temp/writable layer không đủ làm retention strategy.

Biên dịch và chạy hai lần bằng JDK 17+:

~~~bash
javac EvidenceCheckpointLab.java
java EvidenceCheckpointLab ./incident-evidence 2
java EvidenceCheckpointLab ./incident-evidence 2
~~~

Dạng stdout (PID và đường dẫn thay đổi theo mỗi lần chạy):

~~~text
PID=<PID-do-OS-cap>
EVIDENCE_FILE=<duong-dan-tuyet-doi>/evidence-<PID>-<UUID>.log
PHASE=READY
PHASE=FINISHED
~~~

Sau hai lần chạy, `incident-evidence` sẽ có hai file riêng. Mỗi file được kỳ vọng có `pid=`, `java=`, `startUtc=`, `phase=start`, `heapUsedBytes=`, `phase=finished` và khi thoát bình thường có `shutdownHook=called`. Nếu bị lỗi ghi file, xem cả stderr. Các con số heap/PID/UUID là **không cố định**.

Nếu cần xem live state của **chính JVM lab**, chạy `120` giây rồi từ terminal khác dùng PID đã in:

~~~bash
java EvidenceCheckpointLab ./incident-evidence 120
# Trong lúc lab còn sống, ở terminal thứ hai:
jcmd <PID> VM.version
jcmd <PID> Thread.print
jcmd <PID> JFR.check
~~~

Các lệnh `jcmd` trên chỉ là thao tác kiểm tra có điều kiện trên **JVM demo**, không chứng minh kết quả sẽ giống production. Không dùng `kill -9` lên service người khác để minh họa. Việc SIGKILL không chạy shutdown hook đã đủ để giải thích vì sao cần **external persistence trước restart**.

## 10. Tình huống chẩn đoán và cách báo cáo đúng

### A. Service treo, cần restart sớm

Một API treo với hàng nghìn request waiting; trong ngân sách 60 giây có thể giữ alert timestamp, downstream/pool metrics, process identity, một hoặc hai thread dumps và JFR dump nếu đã chạy. Nếu `jcmd` không attach được hoặc quá budget, **ghi thất bại** và để incident commander phục hồi service. Không tự thay bằng `jhsdb --pid` vì live SA attach có thể làm target không tiến triển hoặc crash.

Sau restart, xem event/lock/wait state **trước restart**, so sánh với queue/pool metrics. Không tuyên bố restart đã giải quyết nguyên nhân chỉ vì latency trở lại bình thường.

### B. Memory gần OOMKilled, không đủ disk để dump

Heap hoặc native memory đang tăng, cgroup memory sát limit và disk ít chỗ. `GC.heap_dump` có nguy cơ pause và tốn thêm tài nguyên. Một quyết định hợp lý là **bỏ heap dump**, chụp OS/cgroup memory, GC logs/JFR đang có và ghi lý do: “heavy capture vượt budget; không có HPROF”. Phân biệt Java OOME với kernel OOMKill. Đừng tạo thêm OOM chỉ để có một file chưa chắc hoàn chỉnh.

### C. CPU cao rồi biến mất sau restart

Process trước restart CPU 100%, process mới 20%. Không xem `jcmd`/JFR **sau restart** là profile của JVM cũ. Chỉ so CPU time/throughput/JFR đã xuất trước restart và metrics lịch sử cùng mốc. Nếu JFR mới bắt đầu khi sự cố gần kết thúc, ghi rõ coverage, không tự bịa diễn biến CPU trước đó.

### D. Heap sau chẩn đoán thấp hơn trước

On-call chạy `GC.heap_dump` mặc định và sau đó thấy heap-used giảm. Việc dump có thể request full GC; bảng so sánh phải ghi “heap-used-before” và “heap-used-after-diagnostic-GC” riêng, không diễn giải giảm bộ nhớ như tự phục hồi. Nếu latency spike xuất hiện cùng lúc, kiểm tra GC event và thời lượng lệnh trước khi kết luận.

## 11. Lỗi thường gặp

1. **Restart xong ổn nên không cần thread dump:** có thể đã xóa bằng chứng lock/queue duy nhất.
2. **File tồn tại tức là lệnh thành công:** file có thể chỉ chứa “Unable to attach”, hoặc đã bị ghi dở.
3. **`JFR.dump` dừng recording:** không đúng; khác `JFR.stop`.
4. **`dumponexit=true` bảo đảm có recording khi OOMKilled:** sai, SIGKILL không cho shutdown bình thường.
5. **`HeapDumpOnOutOfMemoryError` luôn cứu được lúc kernel OOMKill:** sai, Java OOME khác OS kill.
6. **Histogram/heap dump là lệnh đọc miễn phí:** sai, có thể quét heap, GC/pause và tiêu thụ disk/CPU lớn.
7. **`GC.run` không thay đổi hệ thống:** sai, có thể thay đổi heap và số đo.
8. **`jcmd 0` nghĩa là process đầu tiên:** sai, có thể tác động tất cả JVM phù hợp.
9. **`kubectl logs --previous` lưu vĩnh viễn:** sai, chỉ còn nếu container logs được retention.
10. **`/tmp` trong container là bằng chứng bền:** sai khi container/pod bị thay thế.
11. **PID giống nhau nghĩa là JVM giống nhau:** sai vì PID reuse và namespaces.
12. **Cứ heap dump rồi restart ngay không cần verify:** file có thể chưa hoàn tất/copy chưa xong/không đủ quyền.
13. **Không ghi lệnh nào đã chạy thì vẫn suy nguyên nhân được:** dữ liệu đã bị công cụ can thiệp và thiếu timeline.
14. **Expected impact Low nghĩa là latency không thể đổi:** không đúng; cần đo thực trên workload và phiên bản cụ thể.
15. **Core/HPROF đưa công khai vào ticket không sao:** có thể lộ tokens, mật khẩu và dữ liệu người dùng.

## 12. Checklist trước/sau restart

### Trước

- [ ] Có incident ID, severity, SLO, operator, approval và **time budget** cho evidence.
- [ ] Đã ghi UTC, PID/start time, image/container/pod UID, JDK vendor/build và runtime flags.
- [ ] Đã lưu dashboard/metrics/logs/traces tại time range trước lỗi.
- [ ] Đã chọn diagnostic commands theo **độ cần thiết** và Impact Low/Medium/High.
- [ ] Mỗi command có start/end/exit code/output, expected impact và observed impact/unknown.
- [ ] JFR đang có đã được dump nếu phù hợp; đã kiểm tra file nằm ngoài filesystem dễ mất.
- [ ] Không làm GC/heap histogram/heap dump nặng khi thiếu disk/CPU/pause budget.
- [ ] Các file có permissions, size, checksum và bản copy đến storage bền đã được kiểm tra.
- [ ] Những gì **không thể thu** đã được ghi lý do trước restart.

### Sau

- [ ] Ghi thời điểm và cách restart, nguyên nhân bị SIGKILL/OOMKilled nếu có.
- [ ] Phân biệt JVM incarnation cũ và mới; không cộng/trừ GC counters khác PID/start time.
- [ ] Đảm bảo artifact cũ vẫn đọc được và phân quyền đúng.
- [ ] Đối chiếu throughput, CPU, memory, p95/p99, error rate theo cùng tải.
- [ ] Có incident timeline ghi lệnh gây thay đổi state, kết quả và giới hạn.
- [ ] Xây dựng kế hoạch instrumentation/continuous JFR/retention cho lần tái diễn.
- [ ] Đảm bảo chính sách bảo mật, redaction và thời hạn lưu HPROF/core/logs.

### Tài liệu tham khảo chính thức

- Oracle JDK 21 — `jcmd`, tác động từng lệnh, `GC.heap_dump`, `Thread.print` và `JFR.dump`: https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html
- Oracle JDK 21 — `java`, `StartFlightRecording`, `HeapDumpOnOutOfMemoryError`, unified logging: https://docs.oracle.com/en/java/javase/21/docs/specs/man/java.html
- Oracle JDK 21 — Recording API, `dump()`, `stop()`, retention: https://docs.oracle.com/en/java/javase/21/docs/api/jdk.jfr/jdk/jfr/Recording.html
- Oracle JDK 21 — Virtual Threads, `Thread.dump_to_file`: https://docs.oracle.com/en/java/javase/21/core/virtual-threads.html
- Kubernetes — Logging Architecture và lịch sử `--previous`: https://kubernetes.io/docs/concepts/cluster-administration/logging/
- Kubernetes — `kubectl logs` reference: https://kubernetes.io/docs/reference/kubectl/generated/kubectl_logs/

**Kết luận:** bằng chứng quan trọng nhất thường là **trạng thái không thể tái hiện của đúng JVM đang lỗi**. Hãy thu thập đúng thứ tự với giới hạn tác động, sao lưu ra vị trí bền, ghi rõ mọi command và ảnh hưởng của chính việc đo, rồi mới restart khi thích hợp. Báo cáo tốt phải tách **điều đã quan sát**, **điều do công cụ thay đổi**, **điều chưa có chứng cứ** và **giả thuyết cần kiểm tra**.