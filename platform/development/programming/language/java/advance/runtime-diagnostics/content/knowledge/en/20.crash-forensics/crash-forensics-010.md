# 20.10 Lập gói bằng chứng tối thiểu và tình huống tái hiện cho việc điều tra tiếp

## 1. Mục tiêu: giao một sự cố cho người khác mà họ vẫn có thể điều tra

Sau khi JVM gặp sự cố, người tiếp nhận thường không có đúng terminal, phiên đăng nhập, dữ liệu và trí nhớ của người đã chứng kiến. Một dòng “Java crash lúc khoảng 10 giờ” hoặc một tệp `hs_err_pid*.log` đứng riêng lẻ thường chưa đủ. Muốn tiếp tục điều tra, phải có **gói bằng chứng tối thiểu, có nguồn gốc và thời gian rõ ràng**, kèm **công thức tái hiện an toàn**.

Một gói tốt trả lời được sáu câu hỏi:

1. **Chuyện gì xảy ra?** Triệu chứng quan sát được, tác động và điểm khác nhau giữa hành vi mong đợi với hành vi thực tế.
2. **Xảy ra với cái gì?** JDK vendor/build, JVM flags, ứng dụng/commit, OS, CPU architecture, container, cgroup, tài nguyên.
3. **Xảy ra khi nào?** Timeline, timezone, PID, thời điểm JVM bắt đầu và thời điểm lỗi, tương quan với deploy/tải/GC.
4. **Còn chứng cứ gốc nào?** Fatal error log, stderr/stdout, heap/core dump, JFR, GC log, exit status và OS events **tùy loại sự cố**.
5. **Làm thế nào thử lại?** Điều kiện ban đầu, dữ liệu thử đã được làm sạch, lệnh, bước kích hoạt, số lần thử, kết quả và phép thử đối chứng.
6. **Cần làm gì tiếp?** Giả thuyết, dữ kiện ủng hộ/phản bác, lỗ hổng bằng chứng, người phụ trách, phạm vi truy cập dữ liệu.

“**Tối thiểu**” không có nghĩa “ít file nhất bằng mọi giá”, mà là **đủ dữ liệu để người khác phân biệt các giả thuyết chính, không phơi lộ dữ liệu ngoài mức cần thiết**. Chỉ gửi một screenshot khi đã có timeline, log và tệp phân tích thường không đáp ứng được mục tiêu này.

Phạm vi: Java 17+ trên HotSpot với ví dụ lệnh JDK 21, trọng tâm **crash và điều tra sau lỗi**; không dùng cách tái hiện gây crash cưỡng bức trên hệ thống production. Với JVM khác, hệ điều hành khác hoặc môi trường container, cách tạo/lưu core và công cụ thu thập có thể khác.

## 2. Trước khi thu thập: phân loại đúng hiện tượng

Không phải mọi trường hợp “Java app chết” đều là **JVM fatal crash**. Loại sự cố quyết định artefact nào có khả năng tồn tại.

| Loại hiện tượng | Dấu hiệu thường gặp | Chứng cứ ưu tiên | Điều không được mặc định |
| --- | --- | --- | --- |
| **Unhandled Java exception** | Stack trace `Exception in thread "main"`, process có thể thoát nếu không còn thread non-daemon | App stderr/stdout, log, exception class/message/stack, exit status, input/path gây lỗi | Có `hs_err_pid*.log` hoặc core dump của JVM |
| **HotSpot fatal error/native crash** | `SIGSEGV`, `SIGBUS`, `EXCEPTION_ACCESS_VIOLATION`, thông báo fatal error của VM | `hs_err_pid*.log`, core/crash dump nếu có, native library/build, OS event | “Problematic frame” duy nhất đã xác nhận nguyên nhân |
| **`java.lang.OutOfMemoryError`** | `Java heap space`, `Metaspace`, `Direct buffer memory`... | Message/stack, heap metrics/GC, `.hprof` nếu đã bật và ghi thành công, config memory | Mọi OOME đều là heap leak; heap dump luôn có |
| **OS/container OOM kill** | Process biến mất, orchestrator có thể ghi `OOMKilled`, host có OOM killer event | Kernel/cgroup/orchestrator events, limits/usage, restart history, exit status | JVM đủ thời gian tạo `hs_err`, heap dump hoặc shutdown JFR |
| **Forced termination** | `SIGKILL`, container bị hủy, watchdog/timeout | Service manager, audit/orchestrator, exit reason/timeline | Exit code 137 **một mình** chứng minh OOM kill |
| **Hang/deadlock, chưa crash** | Process vẫn sống, request timeout; thread không tiến triển | Thread dumps nhiều mốc, JFR, metrics, queues, lock info | Có fatal error log; nên kill ngay để “lấy chứng cứ” |
| **JVM/process exit có chủ ý** | `System.exit`, shutdown do deploy/health policy | App shutdown logs, exit status, deploy/orchestration timeline | Đây chắc chắn là lỗi HotSpot |

**Quy tắc triage:** nếu không có `hs_err`, điều đó không chứng minh “không phải JVM crash” vì không đủ quyền/đĩa hoặc tiến trình bị kill quá sớm. Ngược lại, nếu có Java exception stack thì **không tự suy** rằng HotSpot hỏng. Cần kiểm tra chứng cứ độc lập.

### Điểm khác nhau quan trọng

- **Fatal error log** báo trạng thái HotSpot tại lỗi không thể khôi phục; không giống stack trace Java do exception.
- **Core dump** thường chứa bộ nhớ tiến trình ở tầng OS/native, rất lớn và có thể có mật khẩu/token/dữ liệu cá nhân trong memory.
- **Heap dump HPROF** mô tả Java object graph/heap; hữu ích với một số OOME/leak, nhưng không mô tả đầy đủ native heap, stacks, kernel hay mọi nguyên nhân crash.
- **JFR** kể lại sự kiện JVM trong cửa sổ còn giữ; hữu ích khi đã bật trước đó. Một crash/kill bất ngờ **không đảm bảo** bản ghi exit-dump được tạo.
- **App/OS logs** có thể xác nhận request, deploy, resource limit, signal và điểm bắt đầu triệu chứng; đôi khi chúng quan trọng hơn cả file lớn.

## 3. Thứ tự hành động khi sự cố vừa xảy ra

Trong sự cố thật, thao tác ưu tiên phải cân bằng **khôi phục dịch vụ** và **giữ chứng cứ dễ biến mất**. Áp dụng quy trình sự cố/ủy quyền của tổ chức; không tự giữ service hỏng chỉ để thu thập dữ liệu.

1. **Đánh dấu mốc thời gian:** ghi giờ theo UTC (ISO 8601), timezone đang hiển thị, host/pod/instance, tên service, phiên bản triển khai và người ghi nhận. Nếu đồng hồ các máy lệch, ghi cả chênh lệch đã biết.
2. **Xác nhận process còn sống không:** nếu còn sống, thu các snapshot rủi ro thấp và có mục tiêu; nếu đã chết, không cố `jcmd` vào PID cũ hoặc suy rằng một process mới có cùng PID là process lỗi.
3. **Giữ artifact sắp mất:** log còn trong buffer, tệp trong container sắp bị xóa, JFR còn retention, kernel/orchestrator events, `hs_err` và core location. Ưu tiên copy có kiểm soát **trước** khi restart/cleanup nếu khả thi.
4. **Chụp trạng thái vận hành liên quan:** resource limits, GC/JIT flags, CPU/memory pressure, queue, traffic, deploy/restart, các thay đổi cấu hình; ghi cách lấy từng số.
5. **Không ghi đè nguồn gốc:** tạo bản sao gốc ở nơi lưu an toàn, tính checksum khi khả thi; thao tác redaction trên **bản sao làm việc**, không sửa bản gốc.
6. **Khôi phục và theo dõi:** sau khi đã lưu chứng cứ cần thiết và theo runbook, khôi phục service, xác nhận health rồi ghi mốc hồi phục. Một lần restart có thể làm mất dữ liệu, vì vậy thứ tự hành động phải được ghi trong timeline.
7. **Đóng gói cho người tiếp theo:** cung cấp tóm tắt một trang, manifest, timeline, các tệp có liên quan và recipe tái hiện; nêu rõ phần **chưa thu được**.

Nếu việc thu core/heap dump có thể khiến hệ thống hết đĩa, tăng pause hoặc phơi lộ dữ liệu, **không cưỡng ép thu để “đủ checklist”**. Việc không có artifact phải được ghi rõ lý do và hướng thu lần sau.

## 4. “Gói tối thiểu” gồm những phần nào?

Tối thiểu nên có ba nhóm **tài liệu + dữ kiện + tái hiện**. Cấu trúc ví dụ:

```text
INC-LAB-001/
├── README.md                 # Tóm tắt: điều quan sát và câu hỏi cần trả lời
├── manifest.json             # Máy/JDK/build/flags/giới hạn/timestamps/nguồn
├── timeline.csv              # Mốc deploy, request, GC, lỗi, restart, lấy bằng chứng
├── reproduction.md           # Điều kiện + bước chạy + oracle xác nhận
├── artifacts/
│   ├── stdout.log            # Log đã được xét tính nhạy cảm
│   ├── stderr.log
│   ├── exit-code.txt
│   ├── app.log               # Chỉ khi có
│   ├── gc.log                # Chỉ khi có
│   ├── hs_err_pid12345.log   # CHỈ nếu là fatal log đã xuất hiện
│   ├── incident.jfr          # CHỈ nếu đã có recording hợp lệ
│   ├── java_pid12345.hprof   # CHỈ nếu phù hợp và đã thu được
│   └── core                 # CHỈ nếu được phép/thu được
└── SHA256SUMS.txt            # Hash của đúng các file thực sự được đóng gói
```

Cây thư mục là **ví dụ cấu trúc**, không hàm ý mọi lần lỗi phải có đủ các file. Với một Java exception đơn giản, `README.md`, `manifest.json`, `reproduction.md`, stderr, lệnh và exit status thường đủ để giao tiếp. Với fatal JVM crash phức tạp, `hs_err`/core/native libraries mới là trọng tâm.

Mọi file trong gói cần được phân loại:

- **Required:** phải có để người tiếp nhận hiểu lỗi, ví dụ bản build và thông điệp lỗi.
- **Conditional:** chỉ có khi loại lỗi/thiết lập hỗ trợ, như HPROF hoặc JFR.
- **Missing with reason:** lẽ ra hữu ích nhưng đã mất hoặc không thể thu; nêu lý do, đừng âm thầm bỏ qua.
- **Restricted:** có dữ liệu mật/nhạy cảm, chỉ cấp quyền cho người cần.

## 5. README của sự cố: một trang có cấu trúc

Một bản tóm tắt nên rõ hơn “gặp lỗi JVM, nhờ xem”. Ví dụ **giả định trong lab**:

> **INC-LAB-001, trạng thái:** chưa kết luận nguyên nhân.  
> **Triệu chứng:** chạy `IncidentReproDemo range-error` làm main thread ném `IllegalArgumentException` với thông điệp `quota out of range: 150` và process trả exit status khác 0.  
> **Mong đợi:** input hợp lệ `valid` tạo `quota=25` và thoát thành công; input ngoài phạm vi được xử lý theo hợp đồng ứng dụng thay vì gây crash luồng chính.  
> **Môi trường:** JDK 21 (ghi vendor/update thực tế vào manifest), local Linux, single JVM, không container.  
> **Tái hiện:** theo `reproduction.md`; đã lặp 3/3 lần với cùng build và input.  
> **Bằng chứng:** stdout/stderr, exit code, source test, phiên bản JDK, SHA-256.  
> **Chưa có:** `hs_err`/core không được kỳ vọng trong tình huống Java exception này.  
> **Điều tra tiếp:** kiểm tra validation và error handling tại ranh giới nhập liệu; đối chiếu điều kiện của môi trường thật.

Không ghi “**root cause confirmed**” chỉ vì tái hiện được một exception; tái hiện xác nhận **đường tạo triệu chứng**, còn nguyên nhân gốc ở production có thể chứa thêm concurrency, dữ liệu, cấu hình và chuỗi sự kiện chưa được kiểm chứng.

### Các trường quan trọng của bản tóm tắt

| Trường | Mức chi tiết cần |
| --- | --- |
| Incident ID và contact | Mã nhất quán; đầu mối liên hệ, quyền truy cập |
| Triệu chứng và impact | Observable fact, phạm vi người dùng/request, thời lượng |
| Expected vs actual | Hành vi mong đợi có thể kiểm tra và sai khác |
| Mức độ chắc chắn | Observed, suspected, confirmed-by-test; tránh kết luận quá mức |
| Môi trường | Version, OS, architecture, container, build, JVM flags |
| Time window | UTC và timezone, liên hệ tới logs/JFR |
| Hướng tái hiện | Command/script, input sạch, preconditions, tần suất thành công |
| Bằng chứng còn thiếu | Không có, vì sao thiếu, cách thu lần kế tiếp |
| Next actions | Giả thuyết ưu tiên, người phụ trách, phép thử phân biệt |

## 6. Manifest là bản ghi bối cảnh, không phải bản sao tràn lan mọi env var

Một `manifest.json` có schema đơn giản để giao người khác máy vẫn đọc được. Dưới đây là **ví dụ dùng dữ liệu lab giả định**, không phải số liệu của một service thật:

```json
{
  "incident_id": "INC-LAB-001",
  "classification": "uncaught-java-exception",
  "observed_at_utc": "2026-10-29T09:20:00Z",
  "timezone_of_reporter": "Asia/Ho_Chi_Minh",
  "service": "incident-repro-lab",
  "environment": "local-lab",
  "jdk": {
    "major": 21,
    "vendor": "verify-from-java-version",
    "full_build": "record-the-actual-java-version-output"
  },
  "application": {
    "source_file": "IncidentReproDemo.java",
    "build_revision": "record-the-exact-commit-or-artifact-hash",
    "scenario": "range-error"
  },
  "runtime": {
    "os": "record-os-and-architecture",
    "pid": "record-pid-from-the-failed-run",
    "jvm_flags": "record-relevant-flags-without-secrets"
  },
  "symptom": {
    "error_class": "java.lang.IllegalArgumentException",
    "error_message": "quota out of range: 150",
    "process_exit": "nonzero"
  },
  "files": [
    "artifacts/stdout.log",
    "artifacts/stderr.log",
    "artifacts/exit-code.txt"
  ],
  "missing_expected": [],
  "sensitive_data_reviewed": true
}
```

Các giá trị mô tả như `record-the-actual-java-version-output` nhấn mạnh **quy tắc không giả mạo metadata**: khi áp dụng thật, điền giá trị **đã đo**; nếu chưa thu được thì lưu `null` và giải thích trong `README`. Không điền bừa thông tin vendor, version, commit hay PID. Có thể dùng một schema JSON riêng của tổ chức, miễn là người tiếp nhận hiểu ý nghĩa từng trường.

**Trường nên được ghi khi sự cố production:** JDK distribution/build/update, kiến trúc CPU, tên host/pod/container và restart count, base image, OS/kernel, deployment ID/commit, thời gian process start và uptime, `-Xms/-Xmx`, collector, heap/native/cgroup limits, tình trạng disk, tính năng/thao tác đã bật, traffic/queue tại mốc lỗi. Ghi cả **config source và thời điểm**; đừng copy nguyên environment variables vì có thể chứa secrets.

## 7. Ghi timeline: thời gian là bằng chứng, không phải phần trang trí

Một timeline tách **sự kiện đã ghi** khỏi **giả thuyết**. Mẫu giả định:

```csv
timestamp_utc,source,event,evidence,confidence
2026-10-29T09:19:30Z,deployment,build activated,deploy-log,observed
2026-10-29T09:19:55Z,application,request batch began,app-log,observed
2026-10-29T09:20:00Z,application,exception printed,stderr.log,observed
2026-10-29T09:20:01Z,supervisor,process exited,exit-record,observed
2026-10-29T09:20:15Z,operator,incident acknowledged,incident-log,observed
```

Đừng ghi một giả thuyết kiểu “GC gây crash” vào cột `event` như sự thật. Hãy ghi “GC pause reported in GC log”; nhận định “có thể có quan hệ nhân quả” nằm trong phần phân tích, với mức độ tin cậy riêng.

Các timestamp có thể đến từ đồng hồ JVM, OS, collector, APM và load balancer:

- Giữ ISO 8601 với **offset/timezone**; đừng trộn `09:20` UTC với `09:20` giờ Việt Nam.
- Ghi **start và end** của event có duration (GC pause, request) thay vì một điểm.
- Khi đồng hồ các host bị lệch, ghi ước lượng skew/nguồn đồng bộ; thứ tự nhìn thấy trên dashboard chưa chắc là thứ tự vật lý.
- Sau restart, PID có thể được cấp lại; ghép **PID + process start time + instance/container ID** để phân biệt.
- JFR có thể có cửa sổ retention; file còn dữ liệu sau thời điểm T không chứng minh nó từng lưu sự kiện trước T.

## 8. Chuẩn bị trước: thiết lập để lần sau không mất chứng cứ

Nếu chỉ bắt đầu chuẩn bị **sau** khi JVM đã chết, nhiều artefact không thể tạo ngược lại. Trên HotSpot, có thể cân nhắc cấu hình trước theo mức rủi ro, dung lượng đĩa và chính sách riêng của hệ thống.

Ví dụ các **lựa chọn cấu hình riêng lẻ** khi khởi động JVM (Linux, đường dẫn chỉ mang tính minh họa):

```bash
# Fatal VM error: file tai duong dan co quyen ghi.
java -XX:ErrorFile=/var/log/java/hs_err_pid%p.log -jar service.jar

# Khi OutOfMemoryError: heap dump neu co du cho va JVM co the ghi.
java -XX:+HeapDumpOnOutOfMemoryError \
     -XX:HeapDumpPath=/var/log/java/ -jar service.jar

# GC + safepoint log co gio va vong log huu han.
java -Xlog:gc*,safepoint:file=/var/log/java/gc.log:time,uptime,level,tags:filecount=5,filesize=20m \
     -jar service.jar
```

Đây là **các ví dụ thay thế/độc lập** để đọc cú pháp, không phải ba lệnh cần chạy cùng lúc cho một service; trong vận hành sẽ phối hợp những option cần thiết vào **một** cấu hình launch được kiểm thử. Trước đó hãy tạo thư mục, cấp quyền cho **user của JVM**, định mức dung lượng và retention; path phải tồn tại trong filesystem của JVM/container.

Những điều cần hiểu:

- `-XX:ErrorFile=...` chọn vị trí fatal error log. Không phải mọi exception Java đều tạo file này. Nếu vị trí không ghi được, JVM có thể thử chỗ khác như thư mục temp của hệ điều hành.
- `-XX:+HeapDumpOnOutOfMemoryError` với `-XX:HeapDumpPath=...` hỗ trợ một số trường hợp OOME. File `.hprof` có thể rất lớn và chứa dữ liệu nhạy cảm; thiếu đĩa/permission/loại lỗi có thể khiến dump không xuất hiện.
- `-Xlog` giúp lưu GC/safepoint evidence có mốc thời gian; rotation có thể xóa giai đoạn sớm khi log quay vòng. Khi incident kéo dài, phải bảo đảm vẫn còn cửa sổ cần phân tích.
- Core dump do **OS/runtime policy** quyết định, không chỉ do flag Java. Nhiều môi trường container/service manager có giới hạn `ulimit`, kernel core pattern, systemd-coredump, disk quota hoặc cơ chế thu khác.
- Trong production, thay JVM flags có thể cần restart và thay đổi overhead; phải theo quy trình triển khai được phê duyệt.

### Thu JFR có cửa sổ lịch sử

Khi cần timeline trước sự cố và chấp nhận chi phí lưu trữ:

```bash
java -XX:StartFlightRecording=name=service_ring,settings=default,disk=true,maxage=30m,maxsize=256m,dumponexit=true,filename=/var/log/java/exit-%p-%t.jfr -jar service.jar
```

- `maxage/maxsize` giới hạn phần dữ liệu **còn giữ trong repository**, không phải toàn bộ file `.jfr` đã xuất.
- `dumponexit=true` có cơ hội dump khi JVM **shutdown bình thường và recording còn chạy**. Với `SIGKILL`, mất điện hoặc crash không có shutdown thông thường, **không được hứa** file exit-dump sẽ xuất hiện.
- Khi JVM **còn sống**, có thể gọi `JFR.dump` để chốt dữ liệu trước khi incident trôi khỏi retention; không thể gọi sau khi process đã chết.

Các thiết lập cần được kiểm thử trước incident: có đủ disk hay không, event nào được bật, naming tránh ghi đè, nơi file nằm trong container, kiểm tra tệp bằng `jfr summary`, chính sách cất giữ và quyền truy cập.

## 9. Khi JVM vẫn sống: bộ lệnh thu thập có chọn lọc

Với HotSpot còn sống và **PID đã xác nhận là 12345**, trong môi trường được phép:

```bash
jcmd -l
jcmd 12345 VM.version
jcmd 12345 VM.uptime
jcmd 12345 VM.command_line
jcmd 12345 VM.flags
jcmd 12345 VM.info
jcmd 12345 Thread.print -l
```

Đây là **các lệnh đọc trạng thái tại thời điểm chạy**; phù hợp khi phát hiện hang/latency bất thường mà process vẫn hoạt động. `jcmd` cần JDK tool, quyền attach và namespace phù hợp. Một số lệnh có chi phí đáng kể nếu nhiều thread; đừng lấy snapshot quá thường xuyên.

Để xuất thành các file riêng trong thư mục chứng cứ đã tạo và cấp quyền:

```bash
jcmd 12345 VM.version > vm-version.txt
jcmd 12345 VM.command_line > vm-command-line.txt
jcmd 12345 VM.flags > vm-flags.txt
jcmd 12345 Thread.print -l > threads-T0.txt
```

Đảm bảo file thu được có timestamp trong manifest/tên file và log lệnh đã dùng. **`VM.command_line` hoặc `VM.info` có thể lộ token/URI/config**, nên phải hạn chế truy cập và redaction trước khi chia sẻ.

Nếu JVM đang có recording JFR tên `service_ring`:

```bash
jcmd 12345 JFR.check
jcmd 12345 JFR.dump name=service_ring filename=/var/log/java/on-incident-%p-%t.jfr
```

`JFR.dump` xuất bản ghi còn giữ **mà không dừng** recording. File nằm ở đường dẫn được giải quyết từ **JVM đích**, nhất là trong container. Chỉ dùng `name=service_ring` nếu `JFR.check` thật sự báo tên đó; không đoán rằng mọi JVM đều đang bật JFR.

**Không phải hành động “tối thiểu” mặc định:** `jcmd PID GC.heap_dump ...`, `GC.class_histogram` hoặc ép Full GC. Những lệnh này có thể gây pause/lượng I/O cao, có thể ảnh hưởng chính hiện tượng đang khảo sát. Chỉ dùng khi giả thuyết cần và đã có phê duyệt/dung lượng.

Nếu JVM **đã chết**, phải dừng tại đây: các lệnh `jcmd` không thể hồi sinh một process. Chuyển sang `hs_err`, core, app/OS logs, JFR đã xuất, OOM records và build/environment metadata còn lưu.

## 10. Chọn bằng chứng đúng theo triệu chứng

### 10.1. Fatal error log: `hs_err_pid*.log`

Với fatal HotSpot error, tìm log theo vị trí cấu hình `-XX:ErrorFile` hoặc working directory/temp fallback. Đọc theo thứ tự có lợi:

1. **Header:** loại tín hiệu/native exception, JDK vendor/build, VM, OS/architecture.
2. **Problematic frame:** frame native/VM/JIT liên quan nơi crash được phát hiện; phân biệt kí hiệu `C` (native), `V` (VM code), `J` (compiled Java) trong định dạng liên quan.
3. **Current thread / native & Java frames:** thread nào báo sự cố, ngữ cảnh stack, nguồn gọi JNI/JNA/native library.
4. **Process/VM info:** loaded libraries, `VM Arguments`, heap, thread stack, address/memory map, môi trường.
5. **Trước/sau trong timeline:** deploy, native library update, GC activity, resource pressure, container events.

**Không kết luận** “library X chắc chắn là root cause” chỉ vì nó xuất hiện trong problematic frame. Nó có thể là nơi lỗi truy cập bộ nhớ **biểu lộ**, trong khi memory corruption đã xảy ra trước đó. Cần core, symbol/build, reproducer và phép thử giả thuyết.

File fatal log có thể **không hoàn chỉnh** nếu sự cố nặng hoặc ghi file thất bại; không làm sai lệch chứng cứ bằng cách tự bổ sung nội dung đoán.

### 10.2. Core/crash dump: khi cần điều tra native state

Core dump là artifact rất lớn, chỉ thu khi có nhu cầu. Nó có thể chứa **toàn bộ vùng nhớ của process**: bí mật xác thực, dữ liệu người dùng, nội dung heap và native buffers. Cần hạn chế quyền, mã hóa/lưu giữ theo chính sách và đánh dấu dữ liệu nhạy cảm.

Khi giao core cho người phân tích, thường cần **đúng** executable/runtime build, native libraries, debug symbols nếu có, OS/architecture, container context và thời gian capture. Không thay bằng một JDK “gần giống” rồi coi backtrace là chứng cứ chính xác. Trên Linux, core có thể được systemd-coredump giữ thay vì tạo file `core` trong working directory; liên hệ người quản trị về cấu hình và quyền truy cập.

Ví dụ **chỉ để kiểm tra sự tồn tại metadata** trên một Linux có systemd-coredump, khi được phép:

```bash
coredumpctl list
coredumpctl info
```

Không phải hệ điều hành nào cũng có `coredumpctl`; kết quả đọc từ host/container khác nhau. Không dùng lệnh tạo core cưỡng bức trên production chỉ để hoàn thành checklist.

### 10.3. OOME: đừng nhầm vùng bộ nhớ

`OutOfMemoryError` có thể xảy ra vì `Java heap space`, `Metaspace`, native allocation, thread creation hoặc direct buffers. Heap dump hữu ích khi hỏi Java object nào chiếm heap, **không** đủ để giải thích mọi native OOM hoặc OS kill. Nếu ứng dụng không còn sống, `jcmd` không thể tạo heap dump hồi tố.

Thu thêm nếu sẵn có: `-Xmx`, cgroup limit, GC logs/after-GC used, metaspace/NMT khi được bật, native allocation metrics, số thread, container OOM events, history và kích thước input/batch. Khi `.hprof` tồn tại, kiểm tra path, kích thước, khả năng mở và quyền trước khi chuyển; không gửi file nhạy cảm qua email công khai.

### 10.4. OS kill: tìm chứng cứ từ bên ngoài JVM

Nếu container báo `OOMKilled` hoặc process thoát với status `137`, đối chiếu **orchestrator events/kernel/cgroup metrics, limit/peak usage và lịch sử restart**. Status 137 thường phù hợp với SIGKILL theo quy ước shell/container, nhưng **không đủ chứng minh** OOM killer: lệnh `kill -9` của người vận hành hoặc policy timeout cũng có thể dẫn tới cùng dạng kết thúc.

Đừng tìm `hs_err` như điều kiện bắt buộc của OS kill; JVM có thể không có cơ hội tạo fatal log/heap/JFR exit dump.

### 10.5. Hang: nhiều stack snapshots và tiến triển

Một thread dump duy nhất cho biết trạng thái thời điểm đó, không cho biết thread có **tiến triển** hay kẹt lâu. Nếu được phép và process vẫn sống, lấy nhiều snapshot cách nhau có chủ đích, ghi timestamps, so stack/lock/queue cùng request metrics. Đừng suy “deadlock” chỉ vì nhiều thread ở trạng thái `WAITING`: nhiều thread pool bình thường vẫn chờ nhiệm vụ.

## 11. Tình huống tái hiện: thế nào là đủ cho người không chứng kiến?

Bản mô tả “thỉnh thoảng crash khi nhiều tải” không phải recipe hoàn chỉnh. Một **reproducer** nên có:

| Thành phần | Câu trả lời phải rõ |
| --- | --- |
| **Preconditions** | JDK vendor/build, OS/arch, flags, memory/CPU limits, input dataset đã làm sạch, cấu hình phụ thuộc |
| **Artifact chính xác** | Commit hoặc SHA-256 của JAR/container image/native library; source và cách build khi cần |
| **Điểm khởi đầu** | Process mới hay service warm; cache, DB state, queue/traffic, thời gian từ start |
| **Trigger** | Lệnh cụ thể, request pattern, endpoint/case, sequence, concurrency và thời lượng |
| **Oracle** | Dấu hiệu kết quả mong đợi và lỗi thực tế: exception class/message, exit code, `hs_err`, tín hiệu, timeline |
| **Tần suất** | Ví dụ 3/3 lần hay 2/20 lần, tổng số lần thử, khoảng tin cậy/độ biến động nếu cần |
| **Control** | Cùng điều kiện nhưng không kích hoạt; hoặc đổi **một** biến để phân biệt giả thuyết |
| **Evidence per run** | Thư mục/log, timestamp, PID/start time, seed, flags, OS events, checksum |
| **Safety boundary** | Chỉ lab/staging; dữ liệu synthetic; giới hạn tài nguyên/thời gian; không làm sập production |
| **Known gaps** | Phụ thuộc bên ngoài chưa mô phỏng được, data đã ẩn, tác động concurrency khó đo |

**Phân biệt determinism và xác suất:** lỗi có thể tái hiện 3/3 lần với input cụ thể hoặc 2/20 lần dưới concurrency 50 threads. Cả hai đều có giá trị nếu điều kiện và mẫu số được ghi chính xác. Không tuyên bố “luôn xảy ra” từ một lần thành công.

### Chuẩn hóa một run

1. Khởi tạo **môi trường và dataset** theo commit/artifact hash đã chọn; ghi các biến khác nhau so với production.
2. Xác nhận JVM/OS/flags/limits; dọn **chỉ dữ liệu lab đã được phép**, không xóa chứng cứ gốc.
3. Bắt đầu bộ thu log/timeline ở trạng thái rõ ràng; đánh dấu UTC và run ID.
4. Thực hiện đúng trigger với seed/input/concurrency/timeout cố định nếu có.
5. Đo oracle một cách độc lập: code/exit status, logs, health, JFR/GC, OS events.
6. Dừng thí nghiệm an toàn, thu file và checksum; đánh dấu **pass-to-reproduce** hay **not-reproduced**.
7. Lặp lại cùng điều kiện; làm **negative control**, rồi thay một giả thuyết mỗi lần.
8. Ghi những khác biệt vẫn còn, không che đi các lần tái hiện thất bại.

## 12. Ví dụ Java 17+: reproducible Java exception, không gây JVM fatal crash

Thí nghiệm này minh họa **cách ghi trigger và oracle**, không cố tình dùng JNI, `Unsafe` hoặc lệnh native để làm sập JVM. Một **uncaught Java exception** là lỗi ứng dụng và **thường không tạo `hs_err`**.

Lưu file `IncidentReproDemo.java`:

```java
public final class IncidentReproDemo {
    private static int parseQuota(String raw) {
        int quota = Integer.parseInt(raw);
        if (quota < 1 || quota > 100) {
            throw new IllegalArgumentException(
                    "quota out of range: " + quota);
        }
        return quota;
    }

    public static void main(String[] args) {
        String scenario = args.length == 0 ? "valid" : args[0];
        String raw = switch (scenario) {
            case "valid" -> "25";
            case "range-error" -> "150";
            case "format-error" -> "many";
            default -> throw new IllegalArgumentException(
                    "unknown scenario: " + scenario);
        };

        System.out.println("scenario=" + scenario);
        System.out.println("pid=" + ProcessHandle.current().pid());
        System.out.println("quota=" + parseQuota(raw));
    }
}
```

Biên dịch và chạy bằng JDK 17+:

```bash
javac -g IncidentReproDemo.java
java IncidentReproDemo valid
java IncidentReproDemo range-error
java IncidentReproDemo format-error
```

**Dự kiến về mặt logic:**

- `valid` in `scenario=valid`, `pid=...` và **`quota=25`**, kết thúc với exit status thành công khi môi trường không có lỗi khác.
- `range-error` in `scenario=range-error`, `pid=...` rồi ném `java.lang.IllegalArgumentException` với message **`quota out of range: 150`**. Dòng `quota=...` **không được in**, vì exception xảy ra khi đánh giá biểu thức trước `println`.
- `format-error` in `scenario=format-error`, `pid=...` rồi ném `NumberFormatException` từ `Integer.parseInt("many")`.
- PID và số dòng stack trace phụ thuộc JVM/build/source, nên **không bịa stdout/stderr y hệt**. Tình huống có thể được xác nhận bằng class/message/exit status cùng các dòng đầu đã biết.

Để lưu lại chứng cứ của một run trong **Linux shell** với thư mục riêng:

```bash
mkdir -p INC-LAB-001/artifacts
javac -g IncidentReproDemo.java

java IncidentReproDemo range-error \
  > INC-LAB-001/artifacts/stdout.log \
  2> INC-LAB-001/artifacts/stderr.log

printf 'exit=%s\n' "$?" > INC-LAB-001/artifacts/exit-code.txt
java -version 2> INC-LAB-001/artifacts/java-version.txt
```

Các lệnh phải chạy trong shell **không được cấu hình dừng toàn bộ script ngay khi lệnh Java trả nonzero** (chẳng hạn `set -e`); nếu dùng `set -e`, phải xử lý riêng exit status để bước lưu chứng cứ vẫn chạy. `$?` ở lệnh `printf` là exit code của **lệnh `java` ngay trước nó**, không được chèn lệnh khác giữa hai bước.

Có thể ghi lại một run đối chứng:

```bash
java IncidentReproDemo valid \
  > INC-LAB-001/artifacts/control-stdout.log \
  2> INC-LAB-001/artifacts/control-stderr.log
printf 'exit=%s\n' "$?" > INC-LAB-001/artifacts/control-exit.txt
```

Tổng hợp: **cùng JDK, cùng class, thay một biến `scenario`**. Nếu `range-error` luôn thất bại còn `valid` luôn qua, ta đã chứng minh được sự khác biệt **của ví dụ này**. Đừng nói đó là JVM crash: không có fatal error/`hs_err` được kỳ vọng. Trong production, muốn kết nối ví dụ với sự cố thật phải chứng minh input path/logic tương đương.

### Tình huống tái hiện cho fatal crash thực sự

Nếu sự cố thật là SIGSEGV trong native/JNI code, chỉ nên thử tái hiện **trong môi trường được phép**, đúng JDK build/native library/OS/architecture, dataset synthetic và giới hạn tài nguyên. Không yêu cầu đồng nghiệp chạy code “chủ động làm sập JVM” trên production để thu đủ hồ sơ.

Một recipe an toàn cho người điều tra có thể ghi: “Đưa input synthetic thuộc lớp dữ liệu X qua parser JNI version Y trên staging cùng bản native library; đợi callback Z; lỗi có dấu `SIGSEGV` và problematic frame cùng signature; nếu xuất hiện, lưu hs_err/core bằng policy đã chuẩn bị”. Nó vẫn cần thông số đo thật và số lần thành công; **không biến một phương pháp nguy hiểm thành điều kiện bắt buộc**.

## 13. Checksums, tính toàn vẹn và chuỗi bàn giao

Tệp `hs_err`, `.hprof`, `.jfr` hoặc core có thể đổi kích thước khi đang ghi; **đừng hash rồi kết luận “đã hoàn tất” khi producer chưa đóng file**. Xác nhận file ổn định, có quyền đọc và không còn được ghi trước khi lưu bản bất biến. Với JFR đã export:

```bash
jfr summary /var/log/java/incident.jfr
```

Dùng **tên file thật và filesystem đúng**; nếu report `jfr` lỗi thì chưa thể đánh dấu JFR là artifact hợp lệ. Sau khi có file chứng cứ đã được duyệt chia sẻ, tính hash:

```bash
cd INC-LAB-001
sha256sum artifacts/stdout.log \
          artifacts/stderr.log \
          artifacts/exit-code.txt \
          artifacts/java-version.txt \
          > SHA256SUMS.txt
sha256sum -c SHA256SUMS.txt
```

Các lệnh trên dành cho gói `INC-LAB-001` khi bốn file được tạo đúng như ví dụ mục 12. Nếu gửi thêm file, đưa **đúng file đã thực sự tồn tại** vào danh sách hash. File SHA256 chỉ chứng minh **byte content không đổi giữa hai lần kiểm tra**, không chứng minh file có nguồn gốc đúng hoặc nội dung không bị chỉnh trước khi hash; vì vậy vẫn cần log về ai/when/how đã thu.

Tạo archive nếu được phép:

```bash
cd ..
tar -czf INC-LAB-001.tar.gz INC-LAB-001
sha256sum INC-LAB-001.tar.gz > INC-LAB-001.tar.gz.sha256
```

**Cảnh báo:** archive này chỉ nên chứa tài liệu **đã qua duyệt quyền chia sẻ và kiểm tra dữ liệu nhạy cảm**. Không đưa raw heap/core/secrets vào một archive trao đổi rộng. Hash không phải mã hóa. File gốc nhạy cảm lưu ở kho hạn chế quyền, còn bản redacted có checksum riêng và nêu rõ đã che những gì.

### Khi cần chỉnh để bảo vệ thông tin

Giữ hai lớp rõ ràng:

- **Original, restricted:** bản gốc không đổi, có hash, thời điểm thu, ACL và thời hạn lưu giữ.
- **Sanitized, shareable:** bản sao đã che token, email, payload, PII, thông tin người dùng, credential trong command line/env; hash của bản sao và mô tả thao tác redaction.

Không thể chỉ xóa vài dòng tùy tiện rồi gọi sanitized dump. Heap/core chứa dữ liệu nhị phân, và text output có thể có secret ở chỗ khó nhìn; đôi khi **không thể chia sẻ dump** ngoài nhóm được cấp quyền. Đối với investigation ticket, có thể cung cấp **chỉ metadata, signature và đường dẫn kho hạn chế**, thay vì đính kèm dữ liệu đầy đủ.

## 14. Từ bằng chứng tới giả thuyết, không nhảy thẳng tới kết luận

Ví dụ một sự cố sau deploy có dấu fatal error trong JNI library, đồng thời memory usage cao. Ít nhất các giả thuyết sau cần được phân biệt:

| Giả thuyết | Bằng chứng có thể ủng hộ | Cách thử phản chứng |
| --- | --- | --- |
| Native library version mới gây lỗi | `hs_err` ở native frame phù hợp, chỉ xảy ra với build chứa library mới | Chạy cùng input trên hai phiên bản native library trong lab |
| Memory pressure tạo điều kiện lỗi | GC/native memory pressure đi trước crash, giới hạn container gần trần | Tái hiện cùng input với memory budget khác, kiểm tra loại crash |
| Dữ liệu đầu vào kích hoạt code path lỗi | Crash gắn với một payload/format cụ thể, stack path nhất quán | Input synthetic tương đương vs input đối chứng |
| Concurrency/race | Chỉ xuất hiện ở mức tải cao, nhiều thread/interleaving | Lặp nhiều runs, thay concurrency/seed nhưng giữ các biến khác |
| OS kill chứ không phải fatal JVM crash | Kernel/cgroup OOM events, `OOMKilled`, không có fatal signature | So exit reason ngoài JVM, kiểm tra metrics và kill policy |

Dòng trong `hs_err` có thể chỉ là **nơi phát hiện** lỗi. Một correlation giữa thời điểm GC và crash chưa xác nhận GC là nguyên nhân. Kết luận nên chia mức:

1. **Observed:** “Process exit, kernel báo OOMKilled” hoặc “hs_err header ghi SIGSEGV”.
2. **Consistent with:** “Tình huống phù hợp với race trong native callback”.
3. **Confirmed by controlled reproduction:** “Trong lab, thay duy nhất library version A→B dưới cùng input/limits làm signature chỉ xuất hiện trên B trong nhiều runs”.
4. **Fix validated:** “Sau bản vá, test tái hiện và regression tests không còn xuất hiện signature trong phạm vi mẫu đã nêu”.

Ngay cả “0 lỗi sau 100 lần” không chứng minh xác suất bằng 0; báo số lần và điều kiện cụ thể. Tránh viết kết luận lớn hơn bằng chứng.

## 15. Tiêu chí một gói đủ để chuyển giao

Người nhận không chứng kiến sự cố phải có khả năng trả lời được bảng kiểm:

| Kiểm tra | Pass khi |
| --- | --- |
| **Định danh** | Incident ID, service, build/commit, JVM version, instance/PID/start time rõ ràng |
| **Phân loại** | Phân biệt exception, fatal HotSpot crash, OOME, OS kill hay hang |
| **Timeline** | Có cửa sổ thời gian cùng timezone, các mốc kích hoạt/crash/restart |
| **Raw facts** | Ghi evidence filenames/source/commands; không chỉ screenshot hoặc lời kể |
| **Tính toàn vẹn** | File đã hoàn tất, checksum/ownership/retention được quản lý |
| **Khả năng phân tích** | `hs_err`/HPROF/JFR (nếu có) mở/đọc được, hoặc giải thích cụ thể vì sao thiếu |
| **Reproducer** | Điều kiện, trigger, oracle, cách build/run, số lần thử và kết quả đối chứng |
| **An toàn** | Dữ liệu nhạy cảm được phân loại, redaction/hạn quyền, không gửi secret |
| **Giới hạn** | Hypothesis khác fact; ghi lỗ hổng bằng chứng, tính bất định |
| **Bàn giao** | Người phụ trách, nơi lưu được phép, next action và cách đo việc khắc phục |

Nếu một điều kiện chưa pass, nói rõ **chưa đủ** chứ không bịa artifact hoặc rút ngắn quy trình thành kết luận vô căn cứ. Một gói thiếu core vì policy cấm có thể vẫn **đủ để định hướng** nếu đã có signature và kế hoạch thu/repro tiếp theo; gói tối thiểu không đồng nghĩa check tất cả file bất kể hoàn cảnh.

### Những dấu hiệu gói chưa đủ

- “Lỗi cách đây vài hôm” mà không có giờ, timezone hoặc process instance.
- Chỉ lưu stack trace đã cắt mất exception message, `Caused by` hoặc thread context.
- Có heap dump lớn nhưng không biết JDK build, `-Xmx` hoặc diễn biến trước OOME.
- Có `hs_err` nhưng không ghi native libraries/build/symbols; không biết file còn nguyên vẹn không.
- Chỉ có command “`java -jar app.jar`” nhưng JAR không có version/hash, input đã bị mất.
- Tái hiện 1/1 lần nhưng ghi “luôn xảy ra”, bỏ qua 10 lần fail-to-reproduce trước đó.
- Screenshot monitoring không có timestamp/timezone, trục đơn vị hoặc phạm vi filter.
- Dùng một loạt env var chứa secret trong ticket công khai để “đảm bảo đầy đủ”.
- Tệp `.jfr` chưa kiểm tra `jfr summary`, hoặc file chỉ chứa thời gian **sau** sự cố.
- Copy `hs_err` ra đường chia sẻ nhưng không xác nhận quyền/retention.

## 16. Sai lầm thường gặp và cách khắc phục

1. **Tưởng mọi Java exception đều là JVM crash.** Java stack trace thường không tạo `hs_err`; phải phân loại trước.
2. **Cố chạy `jcmd` sau khi process đã chết.** Không thể hỏi một JVM không tồn tại; tập trung vào file/OS evidence.
3. **Để restart ghi đè hoặc xóa log.** Cần snapshot/copy trước khi cleanup nếu có thể, và ghi timeline restart.
4. **Nhầm PID với identity bất biến.** PID có thể được dùng lại; cần process start time/instance ID.
5. **Cho rằng thiếu `hs_err` chứng minh không có fatal error.** Path/permission/disk/kill có thể làm mất file.
6. **Cho rằng `SIGKILL/137` chứng minh OOM.** Có nhiều nguyên nhân bị kill; cần OS/orchestrator evidence.
7. **Cho rằng heap dump giải thích native memory.** HPROF chỉ một phần bức tranh.
8. **Thu core/heap dump vô điều kiện.** Rủi ro pause/disk/security; cần câu hỏi điều tra và phê duyệt.
9. **Không giữ JDK vendor/update/native library.** Không đủ để phân tích crash phụ thuộc binary.
10. **Đưa secrets vào manifest.** Không lưu toàn bộ env/command line chưa xét quyền.
11. **Chỉ nói “tái hiện được” mà không ghi trigger.** Đồng nghiệp không thể kiểm chứng.
12. **Không giữ control case.** Khó phân biệt input/flag/traffic nào làm lỗi xuất hiện.
13. **Bịa stdout/exit status hoặc tái hiện “3/3”.** Nếu chưa chạy, mô tả là dự kiến và ghi khoảng trống.
14. **Ghép số liệu ở timezone khác nhau.** Timeline có thể tạo nhân quả giả.
15. **Hash sau khi tự sửa file gốc.** Không còn bảo đảm nội dung phát sinh lúc sự cố.
16. **Hash file đang được ghi.** Hash không đại diện artifact cuối cùng.
17. **Dùng checksum như cơ chế bảo mật.** Hash không mã hóa hay hạn quyền.
18. **Gửi file nhị phân nhạy cảm qua kênh tự do.** Core/heap có thể chứa token và dữ liệu khách hàng.
19. **Gán root cause từ problematic frame.** Frame phát hiện lỗi khác nơi tạo lỗi.
20. **Kết luận “fixed” sau một lần không lỗi.** Phải lặp lại theo tần suất và điều kiện tương đương.

## 17. Bài tập thực hành và tự đánh giá

**Bài 1 — sự cố kiểu gì?** Ứng dụng in `Exception in thread "main" java.lang.IllegalArgumentException` rồi thoát nonzero; không có `hs_err`. Gói tối thiểu nên có gì?

*Gợi ý:* Source/build, lệnh/input, Java stderr/stack, exit status, JVM version, expected/actual và reproducer. Không bắt buộc core hay fatal error log.

**Bài 2 — JVM fatal native:** Có `hs_err_pid12345.log` với problematic frame ở `libparser.so` nhưng không có core vì OS policy. Có thể kết luận thư viện đó là nguyên nhân chắc chắn?

*Gợi ý:* Chưa. Giữ file fatal log, JDK/native build, flags, library version, OS, timeline và mô tả thiếu core. Tạo lab repro để kiểm tra giả thuyết, tránh gọi frame là root cause đã xác nhận.

**Bài 3 — OOMKilled:** Một container exit 137, không có heap dump. Có thể kết luận Java heap leak?

*Gợi ý:* Không. Đọc kernel/cgroup/orchestrator events và container limits; 137 có thể là SIGKILL do nguồn khác. Heap dump vắng mặt không loại trừ OOM kill hay native memory pressure.

**Bài 4 — thời gian:** JFR báo GC pause lúc 09:20 UTC, app log báo request 16:20 GMT+7. Hai mốc có trùng thời gian thực không?

*Gợi ý:* 09:20 UTC tương ứng 16:20 tại Việt Nam cùng ngày. Vẫn cần đối chiếu ngày, seconds và clock skew trước khi suy quan hệ nhân quả.

**Bài 5 — tái hiện:** Run A lỗi 2/20 lần ở 100 requests/s; run B không lỗi 0/5 lần ở 10 requests/s. Có chứng minh tải là nguyên nhân?

*Gợi ý:* Chưa đủ; khác cả workload và sample size. Thiết kế nhiều lần thử với cùng build/input/limits, thay một biến mỗi vòng và ghi kết quả âm tính/dương tính.

**Bài 6 — chia sẻ:** Heap dump chứa session tokens và payload khách hàng. Có nên đính kèm trực tiếp vào issue tracker công khai?

*Gợi ý:* Không. Chỉ lưu ở nơi được phép có ACL, encryption và retention; ticket công khai chỉ cần signature, manifest và tham chiếu quyền hạn. Redacted copy được đánh hash riêng.

**Bài 7 — chạy ví dụ:** Biên dịch `IncidentReproDemo.java`, tạo `INC-LAB-001` bằng lệnh mục 12, so `stdout.log`/`stderr.log`/exit-code của `range-error` với `valid`, tính SHA-256. Viết `README` năm dòng mô tả phân loại, expected/actual, oracle, evidence còn thiếu và bước xác minh tiếp theo.

## 18. Nguồn tham chiếu chính thức

- [Oracle JDK 21 — Prepare Java for Troubleshooting: bật flags trước và gather relevant data](https://docs.oracle.com/en/java/javase/21/troubleshoot/prepare-java-troubleshooting.html).
- [Oracle JDK 21 — Fatal Error Log: vị trí, header, threads, process và system sections](https://docs.oracle.com/en/java/javase/21/troubleshoot/fatal-error-log.html).
- [Oracle JDK 21 — `java` launcher: `-XX:ErrorFile`, `-XX:+HeapDumpOnOutOfMemoryError` và `-XX:HeapDumpPath`](https://docs.oracle.com/en/java/javase/21/docs/specs/man/java.html).
- [Oracle JDK 21 — `jcmd`: `Thread.print`, `VM.version`, `VM.flags`, `JFR.dump`](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html).
- [Oracle JDK 21 — `jfr`: `summary`, `print` và kiểm tra file](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jfr.html).
- [Oracle JDK 21 — Troubleshoot Memory Leaks: phân biệt `Java heap space` và các dạng OOME](https://docs.oracle.com/en/java/javase/21/troubleshoot/troubleshooting-memory-leaks.html).

**Kết luận thực hành:** Gói bằng chứng tốt giúp người khác **kiểm tra lại**, không buộc họ tin lời kể. Hãy bàn giao **triệu chứng + bối cảnh + timeline + artifact gốc có thể xác minh + công thức tái hiện + phạm vi bất định**. Chỉ báo nguyên nhân khi chứng cứ và phép thử đủ mạnh; đừng hy sinh bí mật dữ liệu hoặc ổn định production để có thêm một file.
