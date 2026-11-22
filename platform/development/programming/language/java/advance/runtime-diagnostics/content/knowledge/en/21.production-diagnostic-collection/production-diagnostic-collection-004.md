# 21.4 Đặt điều kiện dừng, dung lượng tối đa và thời hạn giữ file chẩn đoán

## 1. Mục tiêu: giới hạn việc thu thập để không tạo sự cố mới

Trong vận hành Java/HotSpot, mỗi lần điều tra có thể tạo **Java Flight Recorder (JFR) recordings**, GC logs, thread dumps, Native Memory Tracking (NMT) snapshots, heap dumps (`.hprof`), fatal VM logs (`hs_err_pid...log`), core/minidumps và application diagnostics. Bằng chứng càng hữu ích khi được lấy đúng thời điểm, nhưng việc thu **quá lâu, quá nhiều hoặc để lại file vô hạn** có thể gây đầy ổ đĩa, tăng độ trễ, đẩy container tới OOM và rò rỉ dữ liệu nhạy cảm.

Một chính sách hoàn chỉnh phải trả lời **ba câu hỏi riêng**:

1. **Stop condition:** một công việc chẩn đoán được chạy bao lâu; điều gì khiến nó tự dừng hoặc được operator dừng sớm?
2. **Size budget:** có thể giữ tối đa bao nhiêu dữ liệu đang ghi, tạo ra bao nhiêu file và chiếm bao nhiêu dung lượng của volume/shared storage?
3. **Retention/TTL:** file chẩn đoán đã hoàn tất được giữ bao lâu tại local và remote; điều kiện nào cho phép xóa?

**Phân biệt cốt lõi:** `JFR maxage=2h` **không** có nghĩa file `.jfr` đã xuất bị xóa sau hai giờ. `JFR maxsize=256m` **không** biến toàn bộ thư mục chẩn đoán thành volume có hard quota 256 MB. `-XX:+HeapDumpOnOutOfMemoryError` **không** tự rotate hay xóa `.hprof`. Mỗi tầng cần policy và cơ chế vận hành riêng.

Các ví dụ dùng JDK 17+ trên HotSpot/OpenJDK. Cần xác minh cú pháp, quyền attach, filesystem và phiên bản JDK/vendor đích trước khi áp dụng lên production.

## 2. Vòng đời artifact: đừng nhầm dữ liệu đang ghi và file đã hoàn tất

| Trạng thái | Ví dụ | Giới hạn phải có |
| --- | --- | --- |
| **COLLECTING** | Recording JFR đang chạy; scheduler gọi `jcmd` định kỳ | Thời lượng, số lượt, tần suất, overhead, lệnh stop/cancel |
| **STAGING/WRITING** | JFR repository chunks; heap dump đang được ghi; upload `.part` | Dung lượng còn trống, quota, không xóa file đang mở |
| **FINALIZED** | File `.jfr` đã dump xong; thread dump text; `.hprof` hoàn chỉnh | Kiểm tra trạng thái, checksum, phân quyền, filename, timestamp |
| **ARCHIVED** | File đã upload và đối chiếu checksum | Kho bảo mật, expiry, legal hold, access log |
| **EXPIRED/DELETED** | File đủ điều kiện dọn sau TTL | Xóa đúng allowlist, audit, không xóa nhầm artifact đang dùng |

Ba thời điểm không giống nhau: **bắt đầu ghi**, **kết thúc recording/dump** và **hết hạn file**. Một recording dừng không có nghĩa file bị xóa. Ngược lại, ai đó xóa một file repository đang mở cũng không tự dừng recording an toàn.

Dùng **metadata/manifest** cho từng artifact: `artifact_id`, `service`, `instance`, `PID`, `incident_id`, `type`, `state`, `started_at_utc`, `finalized_at_utc`, `size_bytes`, `sha256`, `archive_location`, `expiry_at_utc`, `legal_hold` và `owner`. Nếu không có manifest, chỉ dựa vào phần mở rộng hoặc file mtime rất dễ xóa nhầm.

## 3. Ma trận cơ chế sẵn có theo loại file

| Artifact | Dừng thu bằng gì? | Giới hạn dữ liệu bằng gì? | TTL file đã xuất |
| --- | --- | --- | --- |
| **JFR** | `duration`, `JFR.stop`, `Recording.stop()` | `disk=true,maxage,maxsize` quản lý **repository**; `JFR.dump maxage/maxsize` lọc dump | **Không tự có**, cần quản lý ngoài JVM |
| **GC/unified logs** | JVM shutdown hoặc `jcmd VM.log` tùy runtime | `-Xlog:...:filecount=N,filesize=...` quay vòng theo size | Chỉ rotation theo size/count, không phải TTL |
| **Thread dump** | Mỗi `jcmd Thread.print` hoàn tất, scheduler hết số mẫu | Max số snapshot, command timeout, output quota của collector | Dọn file text bằng job ngoài |
| **NMT snapshot** | `jcmd VM.native_memory` hoàn tất, collector dừng lấy mẫu | Số mẫu, tần suất, số byte output | Dọn file ngoài JVM |
| **Heap dump** | Lệnh dump hoàn tất hoặc trigger OOME | Dung lượng/quota/điều kiện cho phép trước khi bắt đầu, **không có built-in rotation** | Job/archival TTL riêng |
| **`hs_err_pid`** | HotSpot fatal reporter | Vị trí và quota filesystem; không có `filecount`/`filesize` riêng | TTL riêng |
| **OS core/minidump** | OS/runtime crash handling | OS core policies/`systemd-coredump`/quota | OS/central archive policy |
| **Application logs** | Logging framework/agent | Logback/Log4j/collector rotation | Quy định riêng |

Phải áp dụng **global budget** nếu nhiều JVM/pod dùng chung volume: 20 JVM với mỗi recording tự giới hạn 256 MB vẫn có thể tạo nhiều GiB repository và **chưa tính file dump, logs hay core**.

## 4. Hiểu đúng `duration`, `maxage` và `maxsize` trong JFR

Các tham số quan trọng:

- **`duration=120s`**: recording được phép chạy **tối đa khoảng 120 giây** từ khi bắt đầu ghi; nó tự kết thúc khi đủ thời lượng. Có thể được dừng sớm bằng `JFR.stop`.
- **`maxage=2h`**: giữ những chunk đủ mới trong **JFR disk repository**. Chunks quá tuổi bị loại theo cơ chế của runtime. Nếu `maxsize` đến trước, thực tế có thể giữ **ít hơn** hai giờ.
- **`maxsize=256m`**: mức giới hạn cho lượng dữ liệu **đang giữ trong repository** của recording; cơ chế theo chunks có thể không byte-exact.
- **`disk=true`**: dữ liệu được flush/giữ trong JFR disk repository; `maxage`/`maxsize` là các giới hạn hữu ích cho cách này.
- **`filename=...`**: vị trí file đích được ghi khi recording dừng/kết thúc theo cấu hình, **không phải đường dẫn mọi chunk trong repository**.
- **`dumponexit=true`**: yêu cầu ghi recording khi JVM shutdown có thể thực hiện; **không bảo đảm** trên `SIGKILL`, kernel OOM kill hoặc host crash.

| Nhập nhằng | Thực tế |
| --- | --- |
| `maxage=2h` là “xóa file sau 2 giờ” | Sai: nó giới hạn **tuổi dữ liệu trong repository**, không xóa mọi `.jfr` đã export. |
| `maxsize=256m` là “volume chỉ chiếm 256 MB” | Sai: không bao gồm tất cả recorders, file dumps, logs, staging và metadata. |
| `duration=2m` là “file chỉ tồn tại 2 phút” | Sai: recording tự dừng sau 2 phút, file export có thể tồn tại nhiều năm nếu không cleanup. |
| `JFR.dump` là “dừng thu” | Sai: dump snapshot nhưng recording tiếp tục chạy. |
| `disk=false` kết hợp `maxage/maxsize` tạo rolling disk history | Sai về mục tiêu: dữ liệu bị giới hạn bởi memory buffers, không phải disk repository theo cấu hình trên. |
| `maxsize=0` là “không được giữ byte nào” | Với tùy chọn này, 0 thường có nghĩa **không giới hạn**. |

**Đừng đặt `maxsize` nhỏ hơn `maxchunksize` được JFR cấu hình**, vì `JFR.start` có ràng buộc tương ứng. Dùng `jcmd <PID> help JFR.start`/`JFR.configure` để kiểm tra chính xác theo JDK đích.

## 5. Recipe A: thu JFR có thời gian dừng tự động

### Thu khi JVM khởi động

```bash
java -XX:StartFlightRecording=name=boot,settings=profile,disk=true,duration=120s,maxage=120s,maxsize=128m,filename=/var/diag/jfr/boot-%p-%t.jfr -jar application.jar
```

Các cặp key=value trong **startup flag** nối bằng **dấu phẩy** và option JVM phải đứng **trước `-jar`**. Trong ví dụ, `profile` chỉ nên dùng cho cửa sổ chẩn đoán có mục tiêu vì có thể tốn CPU, disk I/O và bộ nhớ hơn `default`. Thư mục output phải tồn tại trong filesystem của **JVM đích** và có quyền ghi.

Sau khoảng 120 giây, recording được yêu cầu kết thúc và xuất file. `duration` giúp giới hạn tác động của một lần thu, nhưng file kết quả vẫn cần TTL bên ngoài. Nếu JVM chết đột ngột, không có bảo đảm file đích hoàn chỉnh.

### Thu trên JVM đang chạy, không restart

```bash
jcmd -l
jcmd <PID> VM.version
jcmd <PID> help JFR.start
jcmd <PID> JFR.start name=incident settings=profile disk=true duration=120s maxage=120s maxsize=128m filename=/var/diag/jfr/incident-%p-%t.jfr
jcmd <PID> JFR.check name=incident
```

Khác startup flag, options **`JFR.start` qua `jcmd` ngăn bởi khoảng trắng**. `<PID>` là placeholder, thay bằng PID thật; công cụ cần quyền attach và đúng PID namespace.

Nếu incident kết thúc sớm, chủ động chốt dữ liệu:

```bash
jcmd <PID> JFR.dump name=incident filename=/var/diag/jfr/incident-snapshot-%p-%t.jfr
jcmd <PID> JFR.stop name=incident filename=/var/diag/jfr/incident-final-%p-%t.jfr
```

`JFR.dump` xuất file snapshot và **không dừng** recording. `JFR.stop` dừng recording được chỉ định; luôn dùng `name` để không dừng nhầm recording nền. Nếu recording đã tự stop do `duration`, hãy kiểm tra file và trạng thái thực tế trước khi gửi `stop` thêm lần nữa.

## 6. Recipe B: JFR liên tục nhưng chỉ giữ lịch sử gần nhất

Một incident hiếm khi có thể xảy ra và kết thúc trước lúc người vận hành kịp bật `profile`. Cách phổ biến là ghi **continuous recording** với giới hạn rõ ràng:

```bash
java -XX:StartFlightRecording=name=ring,settings=default,disk=true,maxage=2h,maxsize=256m -jar application.jar
```

Không đặt `duration` nghĩa recording chạy liên tục đến khi được stop/JVM kết thúc. Cấu hình trên chỉ cố giữ dữ liệu **tối đa hai giờ và tối đa một lượng repository đã chọn**; nếu throughput JFR cao làm đạt 256 MB sớm, chunks cũ có thể bị loại trước đủ hai giờ.

Khi cảnh báo phát sinh, dump đúng cửa sổ:

```bash
jcmd <PID> JFR.check name=ring
jcmd <PID> JFR.dump name=ring maxage=15m maxsize=64m filename=/var/diag/jfr/ring-%p-%t.jfr
```

Ở **`JFR.dump`**, `maxage`/`maxsize` giới hạn **phần dữ liệu xuất trong lần dump đó**; không thay chính sách lưu dữ liệu của recording gốc. Dump xong, `ring` tiếp tục ghi. Điều kiện size dựa trên chunks, không cam kết file xuất nhỏ hơn hoặc bằng đúng từng byte của cấu hình. Dùng `jfr summary` và kiểm tra size thực tế sau khi dump.

**Bài toán ẩn:** nếu cứ 10 phút dump một file mới, một ngày tạo **144 file**. `ring maxsize=256m` không tự xóa 143 file cũ. Vì vậy cần policy riêng cho **số bản dump, tổng bytes đã xuất và TTL**.

Nếu cần ngừng `ring`:

```bash
jcmd <PID> JFR.stop name=ring filename=/var/diag/jfr/ring-final-%p-%t.jfr
```

Sau đó chỉ có thể tiếp tục thu bằng recording mới/cấu hình lại; không mặc định `JFR.dump` đã dừng bất kỳ recording nào.

## 7. Điều kiện dừng phải có nhiều cấp ưu tiên

Không chỉ dừng khi hết `duration`. Trong chiến dịch chẩn đoán, đặt các trigger theo priority:

| Trigger | Ví dụ **minh họa**, không phải mặc định JVM | Kết quả |
| --- | --- | --- |
| **Thời lượng tối đa** | Profile JFR không quá 120 giây | Stop/export khi đủ thời gian |
| **Đã đủ chứng cứ** | Thu 3 slow traces, 5 thread dumps, 1 JFR hợp lệ | Dừng collection bổ sung |
| **Sự cố hồi phục** | p99 bình thường liên tục 5 phút | Dừng recording on-demand; giữ ring nếu được thiết kế |
| **Số lượt tối đa** | Thread dump 5 mẫu; NMT 3 mẫu | Không phát thêm lượt chụp |
| **Collector timeout** | Một lệnh `jcmd` không trả sau 15 giây | Đánh dấu attempt lỗi/partial; không xem file dở là hoàn chỉnh |
| **Giới hạn overhead** | CPU, disk I/O, latency bị việc thu làm xấu thêm | Giảm sampling hoặc ngừng collection phụ |
| **Disk high-watermark** | Volume diagnostics chạm 80% | Không tạo artifact mới quá lớn; ưu tiên an toàn |
| **Ngân sách incident** | Tổng finalized + staging gần 2 GiB | Từ chối capture mới hoặc chuyển archive trước |
| **Bảo mật/chính sách** | File chứa data không được phép lưu hoặc có legal hold | Cô lập/xử lý theo policy, tránh publish |
| **Lifecycle** | Restart JVM, pod bị thay, deploy kết thúc | Chốt metadata, lưu artifact hoàn thành |

Các ngưỡng **120s, 5 lượt, 80%, 2 GiB** chỉ giúp minh họa; cần thiết kế lại theo tải, quota, dữ liệu cần giữ và yêu cầu phản ứng sự cố.

**Quy tắc ưu tiên:** an toàn của dịch vụ và dữ liệu > bằng chứng tối thiểu đáng tin > mở rộng thu. Nếu volume thiếu chỗ, không cố dump heap nhiều GiB bằng cách xóa bừa file đang được ứng dụng dùng.

## 8. Cài GC/unified log rotation theo kích thước

HotSpot JDK 9+ có Unified Logging. Ví dụ cấu hình giới hạn độ lớn và số file quay vòng:

```bash
java -Xlog:gc*:file=/var/diag/gc/gc-%p.log:time,uptime,level,tags:filecount=5,filesize=10M -jar application.jar
```

- `gc*` ghi nhóm sự kiện GC theo tag selection của JVM.
- `file=...gc-%p.log` tạo tên có PID, tránh lẫn các instance.
- `filecount=5` giới hạn số log trong cơ chế rotation.
- `filesize=10M` là **kích thước mục tiêu** để rotate, không phải byte-exact hard limit.
- Khi quay vòng, dữ liệu cũ có thể bị ghi đè. Đây là **size/count retention**, không phải giữ chính xác 7 ngày.

**Cảnh báo:** trên HotSpot, `filecount=0` nghĩa là **không quay vòng**, không phải “giữ zero files”, nên file có thể tăng không giới hạn. Trên mỗi JDK cụ thể, kiểm tra:

```bash
java -Xlog:help
```

`jcmd <PID> VM.log` trên các phiên bản hỗ trợ có thể điều chỉnh logging đang chạy; cần xác nhận `help VM.log` và tránh làm thay đổi hệ thống logging trong incident mà không lưu cấu hình trước.

**Không áp dụng `-Xlog` để quản lý Logback/Log4j2 application logs.** Các framework và log shipper có rotation/TTL/quota riêng; chính sách phải bao phủ chúng nếu cùng volume.

## 9. Heap dump: không có built-in rotation cho file `.hprof`

Bật dump khi OOME:

```bash
java -XX:+HeapDumpOnOutOfMemoryError -XX:HeapDumpPath=/var/diag/heap -jar application.jar
```

`-XX:HeapDumpPath` chỉ định nơi ghi. Nó **không** đặt tổng dung lượng tối đa, số file, giới hạn tuổi hoặc cơ chế tự xóa. Một heap dump lớn có thể gây pressure về disk/I/O; tình huống container/kernel OOM kill có thể khiến JVM **không kịp tạo file**.

Chủ động thu khi JVM còn hoạt động (chỉ khi đã đánh giá tác động):

```bash
jcmd <PID> GC.heap_dump /var/diag/heap/manual-investigation.hprof
```

Heap dump là thao tác **nặng**, có thể tạo safepoint/pause và file rất lớn, thường chứa secrets, object payloads hoặc thông tin người dùng. Không nên chụp liên tục trên production chỉ để “có thêm dữ liệu”.

Cần ba guardrail **ngoài** `HeapDumpPath`:

1. **Admission:** chỉ cho phép khi incident hợp lệ, có quyền, còn đủ dung lượng và đúng snapshot nhu cầu.
2. **Concurrency:** hạn chế số heap/core dumps đồng thời trên cùng pod/host/volume; áp cooldown.
3. **Retention:** chỉ xóa local sau khi file hoàn tất, upload được xác nhận và không có legal hold.

**Không ngắt một dump đang ghi rồi khẳng định file `.hprof` dở là hợp lệ.** Nếu một collector timeout hoặc process chết giữa chừng, đánh dấu artifact `INCOMPLETE`. Cần kiểm tra bằng tool chuyên dụng mới được dùng làm bằng chứng.

`-Xmx` là giới hạn Java heap, **không** đồng nghĩa file dump có size đúng bằng `-Xmx` và **không** phải tổng RSS/container memory budget.

## 10. Fatal error log, OS core dumps và bằng chứng sau crash

Khi HotSpot gặp fatal error, có thể tạo `hs_err_pid...log`. Đặt đường dẫn:

```bash
java -XX:ErrorFile=/var/diag/crash/hs_err_pid%p.log -jar application.jar
```

`ErrorFile` không có `filecount`/`filesize` như Unified Logging; muốn dọn các file crash cũ cần policy riêng. Dù cấu hình đúng, reporter có thể không ghi được khi disk đầy/permission lỗi hoặc JVM bị kill cưỡng bức.

Native core/minidump có thể **lớn hơn đáng kể** nhiều file chẩn đoán khác và chứa dữ liệu nhạy cảm. Nơi lưu/size/retention phụ thuộc chính sách OS và môi trường, ví dụ `ulimit -c`, `core_pattern`, `systemd-coredump`, WER, container policy, filesystem quota. **Không** dùng tham số JFR để giới hạn OS core dump.

Một container exit code `137` thường tương ứng `SIGKILL` nhưng **không tự chứng minh OOMKilled**; kiểm tra orchestrator/kernel evidence. Trong tình huống kernel kill, `dumponexit=true`, `finally` và JVM shutdown hooks **không được đảm bảo**; nên có continuous recording và export sớm khi còn cơ hội.

Với fatal artifacts, đặt owner, encryption, access control, TTL và xem xét legal hold theo quy trình incident. Không lưu core dumps vô thời hạn trong cùng volume chứa dữ liệu ứng dụng.

## 11. Thread dump, NMT snapshot và script lấy mẫu: đặt số lượt, không loop vô hạn

Một thread dump được tạo bằng:

```bash
jcmd <PID> Thread.print -l
```

Một NMT snapshot (chỉ hữu dụng nếu HotSpot đã bật Native Memory Tracking từ lúc JVM khởi động):

```bash
jcmd <PID> VM.native_memory summary scale=MB
```

Các command thường **tự kết thúc** khi trả dữ liệu; vấn đề nằm ở scheduler/script gọi chúng **bao nhiêu lần** và output được lưu thế nào. Quy ước minh họa: 5 thread dumps cách nhau 2 giây, 3 NMT snapshots cách nhau 30 giây, timeout 15 giây mỗi lệnh, tối đa 1 job collector cùng thời điểm trên một JVM. Các giới hạn thực tế phải điều chỉnh theo workload.

Mỗi lần thu phải có tên file mới, timestamp UTC, PID và sequence. **Đừng redirect liên tục cùng một lệnh vào một file không giới hạn size**, cũng đừng coi output của một lệnh timeout là đầy đủ.

Ví dụ Linux cho **một** mẫu (thay PID thật và bảo đảm quyền):

```bash
STAMP=$(date -u +%Y%m%dT%H%M%SZ)
jcmd <PID> Thread.print -l > "/var/diag/threads/thread-$STAMP.txt"
```

Dòng trên chỉ tạo snapshot một lần; không tự thêm timeout/loop. Một collector production cần chụp exit code, hoàn tất write rồi mới gắn state `FINALIZED`. Với NMT `summary.diff`, đặt `baseline` và lưu timestamp; không tự coi delta tăng là leak mà không đối chiếu workload.

## 12. Tính quota tổng trước khi chọn `maxsize`

Ví dụ một volume diagnostics **10 GiB** được chia như sau:

| Hạng mục | Dung lượng **minh họa** |
| --- | ---: |
| Tổng dung lượng volume | 10 GiB |
| Safety headroom không cấp phát cho diagnostics | 3 GiB |
| Ngân sách còn có thể dùng | 7 GiB |
| JFR repository và một số file đã dump | 1 GiB |
| GC logs + thread/NMT text logs | 0,5 GiB |
| Một heap/core dump có phê duyệt | 4 GiB |
| Staging upload, metadata và dự phòng | 1,5 GiB |

Đây là **budget thiết kế**, không phải giới hạn JVM tự thực thi. Nếu heap dump dự kiến 8 GiB mà chỉ có 4 GiB trong budget, **không nên bắt đầu** mà chưa có phương án volume/artifact khác. Kế hoạch phải tính cả nhiều pod dùng chung volume và các collector đồng thời.

Công thức:

```text
usable_diag_budget = min(volume_quota,
                         available_bytes - safety_headroom)

peak_storage_demand = active_repositories
                    + active_rotating_logs
                    + concurrent_heap_core_dumps
                    + finalized_local_files
                    + upload_staging
                    + filesystem_overhead
```

Giới hạn bảo vệ **cần được thực thi** bởi filesystem/volume quota, collector admission, alert high-watermark và cleanup logic. Chỉ ghi các con số trong runbook mà không đo `free_bytes`/`used_bytes` thì chưa phải an toàn.

**Một GiB = 1.073.741.824 bytes.** Tránh trộn GiB với MB thập phân trong bảng ngân sách; JFR `m`/`M` và APIs có quy ước riêng, cần kiểm tra cụ thể.

## 13. Retention: quản lý file **đã hoàn tất** bằng metadata và TTL

Một ma trận ví dụ (không phải khuyến cáo pháp lý bắt buộc):

| Artifact | Giữ local sau finalized/upload | Giữ remote archive | Lưu ý |
| --- | --- | --- | --- |
| JFR incident `.jfr` | 7 ngày | 30 ngày | Xác minh `jfr summary`, checksum, mã hóa |
| GC log đã rotate/đóng | 3–7 ngày | 14–30 ngày | Không xóa active GC log |
| Thread/NMT text | 3 ngày | 14 ngày | Đã giới hạn số mẫu |
| `.hprof` | 24–48 giờ sau upload thành công | Theo ticket/policy, ví dụ 7–30 ngày | Chứa object và có thể chứa secrets |
| `hs_err_pid` | 7 ngày | 30 ngày nếu còn incident | Lưu JDK/vendor/build context |
| Core/minidump | Chỉ khi cần, local ngắn | Theo incident security process | File lớn, nhạy cảm, quyền đặc biệt |

**TTL tính từ đâu?** Nên lưu `finalized_at_utc` hoặc `archived_at_utc` trong manifest rồi dùng nó làm mốc; `mtime` chỉ là proxy có thể bị thay đổi khi copy/restore/touch. Nếu policy là “xóa local 48 giờ sau upload”, phải kiểm tra đúng `uploaded_at_utc`, không lấy thời điểm file được JVM bắt đầu ghi.

Hai vùng lưu trữ cần **hai chính sách riêng**:

- **Local staging**: TTL ngắn, có headroom, bảo vệ file đang ghi hoặc upload.
- **Remote archive**: TTL đúng thời gian điều tra, mã hóa, owner, permissions, checksum, audit và legal hold.

Không xóa file local chỉ vì upload **đã bắt đầu**; phải có bằng chứng remote đã nhận đúng object/size/checksum. Nếu điều tra đang mở hoặc legal hold còn hiệu lực, policy cleanup phải bảo vệ artifact ngay cả khi đã quá TTL thông thường.

## 14. Quy trình cleanup an toàn, không xóa nhầm

Một job dọn file nên đi theo thứ tự:

1. **Scope:** chỉ một dedicated diagnostics directory đã được cấp quyền; dùng allowlist type/prefix; không tự follow symlink sang dữ liệu khác.
2. **Inventory:** lấy manifest, loại file, owner, timestamp UTC, state, size, checksum, incident ID, hold.
3. **State check:** bỏ qua `COLLECTING`, `WRITING`, `UPLOADING`, file có size còn thay đổi, file repository/GC log đang mở.
4. **Archive check:** remote object tồn tại, size/checksum khớp và access policy đã áp dụng; nếu chưa thì giữ local và báo lỗi.
5. **Expiry check:** đối chiếu TTL, incident đã đóng và không có legal hold; không suy từ filename/mtime một cách duy nhất.
6. **Quota policy:** nếu sắp đầy đĩa, hạn chế tạo artifact mới trước; chỉ chọn **artifact đủ điều kiện** để dọn, không xóa bằng mọi giá.
7. **Dry-run:** in danh sách filename, size, age, lý do dọn; cần được kiểm duyệt theo policy.
8. **Delete:** chỉ những file được allowlist và xác minh, không xóa symlink target hoặc file đang ghi; lưu audit trail.
9. **Verify:** đo disk used/free, kiểm tra manifest/remote archive, cảnh báo file không dọn được.

Tránh dùng `rm -rf /var/diag/*` hoặc lệnh xóa toàn bộ `*.hprof` trong môi trường vận hành. Các lệnh này không hiểu incident, trạng thái file, archive hay legal hold.

### Dry-run Linux: chỉ liệt kê, không xóa

Ví dụ file `incident-*.jfr` có **mtime** hơn khoảng 7 ngày trong một thư mục dành riêng:

```bash
find /var/diag/jfr -maxdepth 1 -type f -name 'incident-*.jfr' \
  -mmin +10080 -print
```

Lệnh này chỉ tạo **candidate list**. `mtime` không đảm bảo bằng `finalized_at_utc`; **không** tự chuyển ngay thành `-delete` trước khi đối chiếu manifest/archive/hold.

### Dry-run Windows PowerShell: chỉ liệt kê

```powershell
$cutoff = (Get-Date).ToUniversalTime().AddDays(-7)
Get-ChildItem -LiteralPath 'D:\diag\jfr' -File -Filter 'incident-*.jfr' |
  Where-Object { $_.LastWriteTimeUtc -lt $cutoff } |
  Select-Object FullName, Length, LastWriteTimeUtc
```

Lệnh read-only này cũng không thể xác định file đang được dùng hay có legal hold; nó chỉ hỗ trợ inventory trước khi cleanup policy ra quyết định.

## 15. Java 17+: demo `Recording` giới hạn duration, age, size và dừng sớm

JDK cung cấp API `jdk.jfr.Recording` để quản lý recording từ code Java. Dưới đây là chương trình **độc lập**: bật JFR custom event, giới hạn tối đa thời gian chạy, tuổi và dung lượng dữ liệu lưu trong repository, rồi dừng sớm và xuất file. Nó **không** tự thiết lập TTL xóa file sau khi xuất.

Lưu tên file **`BoundedJfrDemo.java`**:

```java
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Duration;
import jdk.jfr.Event;
import jdk.jfr.Label;
import jdk.jfr.Name;
import jdk.jfr.Recording;

public class BoundedJfrDemo {
    @Name("demo.diagnostics.Marker")
    @Label("Diagnostic Marker")
    public static final class Marker extends Event {
        @Label("Sequence")
        public int sequence;
    }

    public static void main(String[] args) throws Exception {
        Path output = Path.of("bounded-demo.jfr").toAbsolutePath();

        // Không ghi đè một file chẩn đoán đã tồn tại.
        if (Files.exists(output)) {
            throw new IllegalStateException(
                    "Output exists; run in a clean working directory");
        }

        try (Recording recording = new Recording()) {
            recording.setName("bounded-demo");
            recording.setToDisk(true);
            recording.setDuration(Duration.ofSeconds(5));
            recording.setMaxAge(Duration.ofMinutes(1));
            recording.setMaxSize(64L * 1024 * 1024);
            recording.setDestination(output);
            recording.enable(Marker.class).withThreshold(Duration.ZERO);

            recording.start();
            Marker event = new Marker();
            event.sequence = 1;
            event.commit();

            // Giả định đã thu đủ bằng chứng: dừng trước giới hạn 5 giây.
            // setDestination(...) khiến file được ghi khi stop thành công.
            recording.stop();
        }

        System.out.println(
                "recording_saved=" + Files.isRegularFile(output));
        System.out.println("stop_reason=manual");
    }
}
```

Chạy trên JDK 17+ có JFR, trong thư mục có quyền ghi và chưa có `bounded-demo.jfr`:

```bash
javac --release 17 BoundedJfrDemo.java
java BoundedJfrDemo
jfr summary bounded-demo.jfr
```

**Stdout của riêng chương trình Java**, với điều kiện thực thi thành công:

```text
recording_saved=true
stop_reason=manual
```

`jfr summary` có output riêng về event/file, thay đổi theo JDK. Program đặt `setDuration(5s)` làm thời lượng tối đa **nếu không stop sớm**, nhưng vì mẫu đã đủ nên `stop()` được gọi trước. `setMaxAge(1m)`/`setMaxSize(64 MiB)` đặt retention ở **repository**; ví dụ ngắn chưa chắc chạm các giới hạn đó. File đầu ra **không tự biến mất sau một phút**; việc xóa theo TTL vẫn thuộc collector/storage.

Các phương thức `Recording.setMaxSize(long)` nhận **bytes** nguyên, không nhận chuỗi `"64m"` như CLI. `setMaxAge(Duration)` và `setDuration(Duration)` nhận đối tượng `Duration`. Nếu muốn export khi còn chạy, dùng `recording.dump(Path)`; việc dừng sớm bằng `stop()` với destination đã cấu hình sẽ tạo output rồi recording chuyển trạng thái tương ứng. Một bản ghi kết thúc rồi **không được start lại** bằng cùng object `Recording`.

## 16. File chẩn đoán trong Docker/Kubernetes: lưu và dọn ở đâu?

Trong container, `/var/diag` thuộc filesystem **process JVM nhìn thấy**. Nếu dùng filesystem tạm của container, file có thể mất khi pod bị xóa hoặc deploy mới. Với các artifact cần điều tra sau crash:

- Dùng **dedicated volume/PVC hoặc exporter** có quy định size và retention; không sử dụng volume chứa database/data path quan trọng.
- Kiểm tra permissions: JVM phải ghi được `.jfr`, `.hprof`, GC logs; collector đọc/archiver theo quyền tối thiểu.
- Sử dụng dấu hiệu pod/container instance, hostname, PID, release và UTC timestamp trong tên file/manifest để tránh nhầm file giữa các lần restart.
- Biết `JFR.dump`/`GC.heap_dump` lưu file trên **JVM/container filesystem**, không nhất thiết ở máy gọi `jcmd`.
- Kiểm tra cgroup memory, disk ephemeral quota, pod eviction và runtime restart policy. Kích thước heap dump có thể vượt quota dù `-Xmx` có vẻ phù hợp.
- Chọn chính sách archive về object storage có mã hóa và checksum; nếu upload thất bại, **không** xóa local và **không** giả vờ incident đã lưu xong.
- Khi JFR/GC logs cần được thu liên tục, kiểm tra tổng chi phí của mọi pods thay vì nhân limit “một recording” với một service duy nhất.

Không tăng `maxage` hay `maxsize` liên tục để phản ứng với incident nếu còn thiếu quota/hard limits; cần phối hợp **CPU overhead, storage và SLA**.

## 17. Chính sách minh họa cho một chiến dịch (không phải file cấu hình JVM)

```yaml
diagnostics:
  incident_id: checkout-p99
  owner: oncall-platform

  jfr:
    settings: profile
    max_duration: 120s
    repository_max_age: 120s
    repository_max_size: 128MiB

  collection:
    max_concurrent_jobs_per_jvm: 1
    max_thread_dump_samples: 5
    max_nmt_samples: 3
    command_timeout: 15s

  storage:
    dedicated_path: /var/diag
    local_budget: 2GiB
    safety_headroom: 1GiB
    high_watermark: 80_percent
    verify_archive_checksum: true

  retention:
    jfr_local_ttl_after_finalization: 7d
    heap_local_ttl_after_verified_archive: 48h
    protect_active_files: true
    protect_open_incidents: true
    protect_legal_holds: true
    dry_run_cleanup: true

  stop_conditions:
    - max_duration_reached
    - enough_evidence_collected
    - incident_resolved_after_cooldown
    - disk_or_overhead_guardrail
```

YAML này là **mô hình policy cho người xây collector**, không phải syntax mà `java`/`jcmd` đọc trực tiếp. Nếu hệ thống dùng Prometheus/Alertmanager, Kubernetes jobs, agents hoặc một service orchestration, cần triển khai mapping từ policy sang lệnh JVM, volume quotas, upload/retention job và alert. Không dừng ở việc viết YAML mà chưa có thành phần **thực thi giới hạn**.

## 18. Tình huống thực tế: trước, trong và sau incident

### Trước incident

Một service có p99 spikes không dự đoán được. Bật ring JFR `settings=default,disk=true,maxage=2h,maxsize=256m`; cấu hình GC logs có rotation, không để JVM ghi vào filesystem dữ liệu quan trọng. Với OOME có thể cân nhắc heap dump trigger và volume đủ chỗ, nhưng phải tính chi phí.

### Khi incident bắt đầu

Collector xác nhận pod/PID, loại incident, latency/CPU/disk và số jobs đang chạy. Nếu cần profiling chi tiết, bật `JFR.start name=incident settings=profile duration=120s...`, giới hạn không quá một chiến dịch nặng cùng lúc. Đặt stop trigger nếu incident resolved, quota cao hoặc overhead bất thường. Chụp chỉ số lượng thread/NMT samples tối đa đã thống nhất.

### Khi dừng

Dùng `JFR.dump` để có snapshot trước khi dừng recording on-demand, hoặc chờ `duration` và xác nhận file đã xuất. **Không dừng ring background** trừ khi policy yêu cầu. File `.hprof` được coi là hoàn tất chỉ sau khi JVM/công cụ báo thành công và kiểm tra artifact; không xóa file đang ghi.

### Sau incident

Ghi manifest + SHA-256, kiểm tra `jfr summary` và loại event, upload bảo mật, kiểm tra remote object và checksum. Bản local chỉ được chọn dọn khi hoàn tất, đủ thời gian, không legal hold và archive đã xác nhận. Đo disk usage sau dọn và giữ audit trail để điều tra thao tác.

### Kiểm tra policy

Nếu alert thường đến chậm hơn hai giờ, `ring maxage=2h` có thể chưa đủ. Nếu `maxsize` bị chạm trước hai giờ, tăng `maxage` một mình không giúp, cần giảm event volume hoặc tính lại disk budget. Nếu p99 tăng do ghi `profile`, cần giảm event settings/duration. Nếu không có chỗ cho heap dump, phải điều chỉnh storage/collection strategy, **không** cố ghi rồi gây disk-full toàn hệ thống.

## 19. Các lỗi phổ biến cần tránh

| Nhận định sai | Vì sao sai | Sửa bằng |
| --- | --- | --- |
| “`duration=2m` tự xóa file sau hai phút” | Chỉ dừng recording, không TTL file | Retention job riêng |
| “`maxage=2h` xóa tất cả `.jfr` hai giờ tuổi” | Chỉ dữ liệu trong JFR repository | Manifest + TTL |
| “`maxsize=256m` bảo đảm cả volume dưới 256 MB” | Dumps/logs/recordings khác nằm ngoài giới hạn | Volume quota/global budget |
| “`JFR.dump` cũng làm recording dừng” | Dump xong vẫn có thể tiếp tục thu | `JFR.stop name=...` khi muốn dừng |
| “`JFR.dump maxsize=64m` cho đúng 64 MB byte-exact” | Chunks/metadata/granularity | Kiểm tra file size thực tế và quota |
| “`filecount=0` nghĩa không giữ file log” | Có thể tắt rotation, khiến log tăng | Dùng filecount dương, filesize hợp lý |
| “GC log rotation giữ đủ dữ liệu đúng 7 ngày” | Rotate theo size/count, không theo TTL | Archive/retention theo thời gian |
| “HeapDumpPath giới hạn dung lượng dump” | Chỉ đặt path | Kiểm tra quota/headroom trước capture |
| “OOMKilled luôn để lại heap dump” | Kernel có thể kill trước khi JVM dump | OS/cgroup events, monitoring |
| “Xóa JFR repository đang mở để giải phóng disk” | Có thể làm hỏng recording/đang ghi | Stop/rotate và chỉ dọn finalized artifacts |
| “mtime chính là finalized time” | Có thể thay đổi do copy/touch/restore | Manifest UTC timestamp |
| “Upload bắt đầu thì có thể delete local” | Upload có thể dở/mismatch | Verify checksum remote trước delete |
| “Xóa tất cả file cũ bất kể ticket” | Có thể có legal hold/incident đang mở | Scope/hold/owner và audit |
| “Quota mỗi JVM đủ cho toàn cluster” | Tổng vượt nhiều lần khi nhiều pod đồng thời | Global budget/concurrency |
| “Lưu core/heap dump vô hạn cho an tâm” | Tăng rủi ro dữ liệu, chi phí | TTL, encryption, access control |
| “SIGKILL luôn chạy shutdown hooks/dumponexit” | Không có cơ hội Java cleanup | Chủ động dump trước khi kill |

## 20. Checklist trước khi bật và kết thúc thu thập

- [ ] Đã xác định mục tiêu, PID/JDK build, người chịu trách nhiệm và incident ID.
- [ ] Có `max_duration`, stop trigger sớm và cơ chế xác nhận recording đã dừng.
- [ ] Có **size budget** cho repository, dumps xuất, logs, staging và OS core — không chỉ một JFR maxsize.
- [ ] Nếu dùng JFR, đã phân biệt `duration`, `maxage`, `maxsize`, `disk`, `filename`, `dumponexit`.
- [ ] Đã chọn `settings=default` cho continuous hay `profile` ngắn theo mục tiêu, có đo overhead.
- [ ] GC/unified logs có `filecount`/`filesize`; app logs có rotation riêng.
- [ ] Với `.hprof`/core dump, đã có safety headroom, quota, giới hạn đồng thời và quy trình xét duyệt.
- [ ] Thread/NMT collectors có số mẫu tối đa, khoảng lấy mẫu, timeout và bounded output.
- [ ] Có dedicated diagnostics directory, permissions và đường dẫn đúng trong container/JVM đích.
- [ ] File hoàn tất có metadata: trạng thái, timestamp UTC, size, checksum, owner, incident.
- [ ] Archive được mã hóa, checksum xác minh; không xóa local chỉ vì upload đã bắt đầu.
- [ ] TTL áp lên **finalized/archived files**, có legal hold và chính sách bảo vệ incident đang mở.
- [ ] Cleanup dry-run, allowlist, không follow symlink ra ngoài path, có audit và xác minh disk sau dọn.
- [ ] Đã kiểm tra alerts disk pressure, collector failures, partial artifacts và các file quá hạn.
- [ ] Đã thực hành end-to-end: start → dump/stop → verify → archive → retention → cleanup.

## 21. Tài liệu chính thức

1. Oracle JDK 21 `jcmd` manual — `JFR.start`, `JFR.dump`, `JFR.stop` và các tham số duration/maxage/maxsize: https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html
2. Java SE 21 `Recording` API — `setDuration`, `setMaxAge`, `setMaxSize`, `setToDisk`, `setDestination` và `stop`: https://docs.oracle.com/en/java/javase/21/docs/api/jdk.jfr/jdk/jfr/Recording.html
3. Oracle JDK 26 `java` manual — `-XX:StartFlightRecording`, Unified Logging `-Xlog`, `filecount/filesize` và `ErrorFile`: https://docs.oracle.com/en/java/javase/26/docs/specs/man/java.html
4. Oracle JDK 21 `java` manual — các cú pháp Unified Logging trên JDK 21: https://docs.oracle.com/en/java/javase/21/docs/specs/man/java.html
5. Oracle Java 21 *Prepare Java for Troubleshooting* — continuous JFR, core/heap dumps, GC logs và chi phí vận hành: https://docs.oracle.com/en/java/javase/21/troubleshoot/prepare-java-troubleshooting.html
6. Oracle Java 21 *Diagnostic Tools* — `jcmd`, heap dumps và artifacts postmortem: https://docs.oracle.com/en/java/javase/21/troubleshoot/diagnostic-tools.html
7. Java SE 21 `java.nio.file.Files` — API file inspection và metadata cho collector: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/Files.html

**Kết luận:** đặt giới hạn **khi nào dừng**, **bao nhiêu dữ liệu được giữ trong lúc thu**, và **khi nào file đã hoàn tất hết hạn** ở ba lớp khác nhau. Các option của JFR, GC log rotation và JVM dump chỉ giải quyết **một phần**; quota/manifest/archive/checksum/TTL/cleanup mới giúp toàn bộ chiến dịch chẩn đoán an toàn, tái lập được và không tạo thêm sự cố disk hoặc bảo mật.
