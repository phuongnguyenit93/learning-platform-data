# 18.7 Phân tích độ trễ tăng đồng thời với GC, safepoint, khóa hoặc I/O

> **Bối cảnh:** Java 21 / HotSpot, ứng dụng server có p95/p99 latency tăng, throughput giảm hoặc timeout. Trong cùng một khoảng thời gian có thể xuất hiện **GC**, **safepoint**, **tranh chấp khóa** và **I/O chậm**. Bài này hướng dẫn kết hợp **độ trễ request**, **JFR**, **GC/safepoint unified logs**, **thread stacks** và **trace/metrics** để biết yếu tố nào thực sự nằm trên đường đi tới phản hồi của request, yếu tố nào chỉ trùng thời gian hoặc là hậu quả thứ cấp.

## 1. Vấn đề cần giải: “cùng lúc” không có nghĩa “do nó gây ra”

Một dashboard báo p99 tăng từ 150 ms lên 1,2 giây vào 10:15 UTC; cùng phút, JVM ghi một GC 200 ms, một safepoint, nhiều thread chờ monitor và một loạt `jdk.SocketRead`. Có ít nhất năm cách giải thích:

1. Một **GC stop-the-world (STW) pause** chặn các thread Java đang xử lý request; sau pause, request tiếp tục và xuất hiện độ trễ tăng.
2. JVM vào một **safepoint không do GC**, làm Java threads bị gián đoạn dù không có GC pause tương ứng.
3. Nhiều request **tranh một monitor/lock**; những request chờ đủ lâu có tail latency cao. GC hoặc I/O ở cùng phút có thể không nằm trên critical path.
4. Một **downstream service, database hoặc filesystem** đáp ứng chậm; socket/file I/O kéo dài, khiến request chờ và dồn hàng. Monitor contention sau đó có thể chỉ là hậu quả của backlog.
5. **Nhiều yếu tố đồng thời:** một request vừa chờ lock vừa bị STW, rồi chờ downstream. Các khoảng thời gian **chồng lấn**, nên cộng mọi duration của JFR sẽ thổi phồng tổng độ trễ.

**Kết luận đúng không phải tên event có duration lớn nhất.** Kết luận cần nêu: *request nào bị ảnh hưởng*, *thời gian bắt đầu/kết thúc*, *tài nguyên/thread/peer liên quan*, *mức độ giao nhau với GC/safepoint/wait*, *bằng chứng độc lập* và *điều gì có thể bác bỏ giả thuyết*.

## 2. Phân biệt các đơn vị thời gian và tín hiệu

| Khái niệm | Đo điều gì? | Điều không được tự suy ra |
| --- | --- | --- |
| **Request latency** | Thời gian từ lúc một tầng bắt đầu xử lý request đến lúc hoàn thành theo định nghĩa của tầng đó | Không luôn chỉ là thời gian JVM chạy code; có thể gồm queue ở proxy, network và downstream |
| **p95/p99** | Phân vị của **một tập request** trong bucket thời gian, ví dụ 1 phút | Không phải duration của “request p99” bất kỳ, cũng không chứng minh mỗi request bị chậm cùng lúc |
| **GC duration** | Thời lượng hoạt động GC được event đo, có thể chứa việc chạy **đồng thời với ứng dụng** | Không đồng nghĩa toàn bộ là thời gian ứng dụng bị stop |
| **GC pause / STW** | Khoảng ứng dụng thực sự phải dừng do một pha GC; JFR có `jdk.GCPhasePause` | Không cộng thêm toàn bộ GC duration hoặc safepoint duration của cùng hoạt động |
| **Safepoint** | Điểm JVM phối hợp để thực hiện thao tác cần trạng thái thread phù hợp; có thể liên quan GC hoặc VM operation khác | Không phải mọi safepoint đều do GC; không phải mọi hoạt động GC chỉ có safepoint |
| **Monitor-enter wait** | Thời gian thread chờ lấy monitor khi vào `synchronized`, JFR `jdk.JavaMonitorEnter` | Không bằng tổng thời gian giữ lock của owner, và không phải CPU busy-loop |
| **Monitor wait / park** | `Object.wait`, `LockSupport.park` hoặc primitive chờ tương ứng | Không phải tất cả là lock contention; có thể là pool rỗng, queue chờ task, timer |
| **Socket/file I/O** | Thời gian thao tác I/O được JFR ghi, gồm thời gian chờ theo ý nghĩa API | Không tự chứng minh network “hỏng”; peer chậm, pool, kernel và backpressure đều có thể liên quan |
| **JFR execution sample** | Mẫu stack tại các thời điểm chạy, ví dụ `jdk.ExecutionSample` | Không cho thời gian CPU chính xác của một Java method hay số lần method được gọi |

Với **virtual threads Java 21**, nhiều virtual threads có thể được unmount khi chờ I/O; chúng không có OS thread ID cố định. Nếu blocking khi pinned trên carrier, `jdk.VirtualThreadPinned` (nếu bật và đạt ngưỡng) là một tín hiệu bổ sung. Không tự động coi mọi `SocketRead` của virtual thread là nó đã giữ một carrier bị chặn.

## 3. Khoanh thời điểm triệu chứng và chọn cửa sổ đúng

### 3.1. Lấy mốc từ phía người dùng trước

Thu từ APM, access logs, tracing, gateway, service metrics: service/endpoint, instance/pod, error rate, traffic, số request, request start/end, p95/p99, latency buckets, queue depth và upstream/downstream span. Ghi **timezone và độ phân giải**.

Ví dụ hoàn toàn **giả định**:

```text
Service:        checkout-api / pod checkout-7cd... / Java 21
Symptom UTC:    2026-10-29T10:15:00Z .. 2026-10-29T10:16:30Z
Metric bucket:  10s; p99 tăng từ 150ms lên 1200ms
Analysis UTC:   2026-10-29T10:14:30Z .. 2026-10-29T10:17:00Z
Control UTC:    2026-10-29T10:10:00Z .. 2026-10-29T10:12:30Z
JVM identity:   PID + process start time + JDK vendor/build + pod
```

Ba khoảng có mục đích khác nhau:

- **Symptom window:** nơi chỉ số người dùng xấu đi. Không đồng nhất điểm timestamp của một bucket với một thời điểm chính xác ở từng request.
- **Expanded analysis window:** thêm thời gian **trước** để tìm yếu tố đi trước (GC, downstream saturation, pool queue), thêm thời gian **sau** để xem phục hồi.
- **Control window:** một khoảng bình thường đủ tương đồng về độ dài, workload, phiên bản app, cấu hình collector và JFR settings; dùng làm đối chứng.

Nếu traffic thay đổi từ 100 lên 1000 requests/s, số event tăng 10 lần có thể là sản phẩm của lưu lượng. Khi cần, so **số event/request**, **số event/giây**, duration percentile và thành phần request critical path thay vì chỉ event count.

### 3.2. Chuẩn hóa tất cả nguồn về một clock

JFR có timestamp ở dạng thời gian tuyệt đối; unified log có thể chứa uptime JVM hoặc `utctime` nếu được cấu hình. Distributed trace, APM và log ingress thường dùng epoch/UTC nhưng có thể xuất ra giờ địa phương. Không so chuỗi “10:15” với “10:15” nếu timezone và clock chưa xác nhận.

```text
10:15:00.000Z     = 17:15:00.000 +07:00
Request [start,end) = [10:15:00.000Z, 10:15:00.900Z)
```

- Ghi **NTP/clock skew** giữa JVM, proxy, DB và monitoring collector. Nếu lệch ±3 giây, không thể khẳng định GC có trước socket timeout 200 ms dựa trên hai máy khác nhau.
- Ghi JVM **start time/PID**, vì sau restart có thể thấy PID mới hoặc PID cũ được tái sử dụng.
- Với logs chỉ có `uptime` (ví dụ 473.250 s), phải căn theo startup time **cùng tiến trình**; tốt nhất thu `utctime,uptime` từ đầu.
- Nếu APM có server span từ khi request vào handler nhưng gateway đo cả queue, chênh lệch nằm **ngoài handler** cần được điều tra.
- Định nghĩa cửa sổ nửa mở **`[start,end)`** để không đếm event tức thời tại ranh giới hai bucket liên tiếp hai lần.

**Không dùng `System.nanoTime()` của hai máy khác nhau như cùng một đồng hồ tuyệt đối.** Nó phù hợp đo duration tại một nơi, không mặc nhiên có origin chung với UTC ở nơi khác.

## 4. Bản đồ event theo bốn giả thuyết

| Nhóm | Bằng chứng JFR / log Java 21 | Đọc chi tiết | Điểm cần xác minh ngoài JFR |
| --- | --- | --- | --- |
| GC | `jdk.GarbageCollection`, `jdk.GCPhasePause`, các GC events theo collector; `-Xlog:gc*` | GC ID, phase pause, start/end và lý do GC nếu có | Allocation rate, heap occupancy, GC collector, pause thực sự giao request |
| Safepoint | `-Xlog:safepoint` / safepoint debug; event safepoint nếu đã bật trong JFR | VM operation, thời gian để các thread đạt safepoint, thời gian ở safepoint | GC cùng lúc hay hoạt động JVM khác, độ dài request thực sự bị ảnh hưởng |
| Khóa/chờ | `jdk.JavaMonitorEnter`, `jdk.JavaMonitorWait`, `jdk.ThreadPark`, `jdk.ThreadSleep`, `Thread.print -e -l` | Thread/stack, monitor class/address, thời gian chờ, lock owner nếu có | Thread nào trên critical path, thread owner bận/chờ điều gì, pool và queue metrics |
| I/O | `jdk.SocketRead`, `jdk.SocketWrite`, `jdk.FileRead`, `jdk.FileWrite` | Duration, thread/stack, remote endpoint, file/path, bytes nếu event chứa | Downstream span, network retries, TCP/DB/pool, disk queue/timeouts |
| Bổ trợ | `jdk.CPULoad`, `jdk.ThreadCPULoad`, `jdk.ExecutionSample`; tracing, metrics | CPU saturation, runnable code, mẫu stack có liên quan | CPU quota/throttling, thread scheduling, host/process pressure |

**Đừng mặc định mọi event đều bật** trong `default.jfc` hay `profile.jfc`. Có loại event bị threshold, sampling hoặc retention giới hạn. Dùng `jcmd ... JFR.check verbose=true`, `jfr metadata`, `jfr summary` và config `.jfc` thật để xác nhận. Không có event **không đồng nghĩa** không có lock wait hoặc I/O delay; một số thao tác dưới ngưỡng ghi nhận có thể lặp dày đặc.

### 4.1. GC: phân biệt collector activity và pause của application

Với G1 và các collectors có pha concurrent, `jdk.GarbageCollection` có thể phản ánh phần activity dài hơn thời gian dừng ứng dụng. Để xem tail latency bị tác động bao nhiêu, ưu tiên **STW pause interval** (`jdk.GCPhasePause`, mục GC pauses trong JDK Mission Control, và unified GC logs).

- Một concurrent marking kéo dài 800 ms không có nghĩa mọi request bị dừng 800 ms.
- Một pause 120 ms giao request 900 ms chỉ giải thích **tối đa phần giao nhau** theo timeline và cơ chế, không tự giải thích toàn bộ 900 ms.
- Có nhiều GC pauses lặp trong một request, phải tính **hợp các khoảng giao** chứ không cộng cả những phase event đã lồng nhau.
- Nếu p99 tăng nhưng GC pauses trong đúng symptom window vẫn nhỏ và có khoảng đối chứng tương tự, hạ ưu tiên giả thuyết “GC là nguyên nhân chính”, không bỏ qua hoàn toàn.

**GC count, total GC duration và sum of pauses là ba đại lượng khác nhau.** Dùng GC ID và phase names để tránh đếm nhiều lần các event cùng GC.

### 4.2. Safepoint: có thể xảy ra mà không có GC

Safepoint cho phép JVM thực hiện một số VM operations cần sự phối hợp của Java threads. Trong log, cần tách: thời gian yêu cầu/đợi thread đạt safepoint, thời gian thực hiện operation khi các thread đã sẵn sàng và tổng thời gian ngừng/ảnh hưởng theo cách JVM báo.

Trường hợp cần xét:

- **GC-triggered safepoint:** safepoint và STW GC pause liên quan chặt chẽ. **Không cộng** tổng safepoint với GC pause như hai lần dừng độc lập.
- **Non-GC safepoint:** sự kiện safepoint có thể liên quan VM operation không phải GC, tùy workload/JVM. Nếu GC log không có pause tương ứng, phải đọc tên operation thay vì tự gán cho collector.
- **Đợi tới safepoint lâu:** khả năng có thread mất thời gian mới tới trạng thái phù hợp; cần kiểm tra log safepoint ở mức chi tiết được phép, thread states và native/JNI context.
- **Một hoạt động JVM đồng thời:** nhìn vào thứ tự `start/end` của safepoint so với request/GC chứ không quy mọi chậm trễ vào nhãn “safepoint”.

`-Xlog:safepoint` là nguồn bằng chứng trực tiếp, nhưng **mức log và trường output thay đổi theo JDK build/collector**. Đừng cứng hóa parser dựa vào một ví dụ log cho mọi JVM.

### 4.3. Khóa: đọc đúng ba cơ chế chờ khác nhau

| JFR event | Mô tả | Cách điều tra |
| --- | --- | --- |
| `jdk.JavaMonitorEnter` | Thời gian thread bị tranh chấp khi **muốn vào** Java monitor `synchronized` | Tìm waiter stack, monitor class, thread đang giữ lock nếu dữ liệu cho phép; so với `Thread.print -l` |
| `jdk.JavaMonitorWait` | Thread gọi `Object.wait(...)`, **nhả monitor** rồi chờ notify/timeout trước khi tiếp tục | Đừng nhầm với thời gian không vào được `synchronized`; kiểm tra condition và nơi notify |
| `jdk.ThreadPark` | Thread tạm park bằng `LockSupport`/concurrency primitives; có thể do queue, `ReentrantLock`, `Future`, pool, latch | Đọc stack/caller/queue length; `ThreadPark` **không chứng minh** lock owner đang bận |

Lock holder có thể bị GC pause hoặc chờ I/O, làm thời gian waiter tăng. Khi ấy một `JavaMonitorEnter` dài là **hậu quả của critical section bị kéo dài**; tối ưu phần xử lý giữ lock hoặc downstream có thể đúng hơn chỉ thay loại lock.

Không dùng nhiều thread `BLOCKED` làm bằng chứng “CPU quá tải”. Chờ monitor thường không có nghĩa thread đang thực thi phép tính trên CPU. Với virtual threads trên Java 21, `jdk.VirtualThreadPinned` có thể bổ sung góc nhìn nhưng phải đọc thời lượng, blocking behavior và stack thực tế.

### 4.4. I/O: sự kiện dài chỉ là điểm bắt đầu

`jdk.SocketRead` có thể dài khi request đang chờ dữ liệu từ server downstream. Nguyên nhân tiềm năng gồm:

- Downstream xử lý chậm hoặc queue ở DB, cache, HTTP service.
- Network jitter, retransmission, DNS/pool/connect phase, backpressure.
- Request đã chậm trước khi đọc socket, ví dụ phải chờ connection pool; `SocketRead` chỉ là pha cuối.
- Thread giữ lock trong lúc chờ I/O, khiến các thread khác chờ monitor.
- File I/O bị ảnh hưởng bởi disk saturation hoặc storage/network filesystem.

Kiểm tra **`eventThread`, stack, endpoint/port/path, bytes, request span, timestamp** và toàn bộ vòng đời request. Một `SocketRead` dài không mặc nhiên là lỗi mạng: có thể peer đang tính toán đúng logic nhưng chậm, hoặc ứng dụng gọi API theo kiểu tuần tự.

Không cộng tổng duration của 100 `SocketRead` đồng thời và báo “100 giây downtime” nếu chúng diễn ra trong một cửa sổ thực chỉ 1 giây. Tổng thời gian thread chờ **khác** elapsed wall-clock của một request và khác thời gian dừng toàn JVM.

## 5. Thu thập an toàn bằng JDK 21

### 5.1. Xác định JVM và ghi triệu chứng trước

Trên máy/container nơi JVM chạy, với account attach thích hợp (thay `<PID>` bằng PID xác minh):

```bash
jcmd -l
jcmd <PID> VM.version
jcmd <PID> VM.uptime
jcmd <PID> JFR.check verbose=true
jcmd <PID> help JFR.dump
```

`jcmd` cần cùng máy và effective UID/GID phù hợp với JVM; process namespace của container có thể làm PID host và PID container khác nhau. Không dùng `jcmd 0` hoặc main-class selector khi cần thao tác **một** JVM cụ thể.

Lưu các metric từ monitoring trong **cùng UTC window**: process CPU, GC pause/count, heap usage, request latency and throughput, error rate, OS I/O, network, CPU quota/throttling, queue/pool size và timestamps của downstream service.

### 5.2. Nếu đã có recording chứa sự cố

Giữ file `.jfr` gốc bất biến và kiểm tra thời gian của recording:

```bash
jfr summary incident.jfr
jfr metadata --events jdk.GCPhasePause,jdk.SocketRead incident.jfr
jfr print --events jdk.GarbageCollection,jdk.GCPhasePause incident.jfr
jfr print --events jdk.JavaMonitorEnter,jdk.ThreadPark incident.jfr
jfr print --events jdk.SocketRead,jdk.SocketWrite,jdk.FileRead,jdk.FileWrite incident.jfr
```

`jfr print --events` **lọc loại event**, không tự chọn khoảng thời gian triệu chứng. Một tệp có 30 phút dữ liệu không thể được quy về phút có p99 tăng chỉ bằng cách nhìn count toàn tệp. Dùng JDK Mission Control chọn khoảng hoặc chương trình API ở mục 9 để thống kê phần giao cửa sổ.

Nếu recording **đang chạy và vẫn giữ event**, có thể dump phần lịch sử theo `begin`/`end`:

```bash
jcmd <PID> JFR.dump name=latency \
  begin=2026-10-29T10:14:30Z end=2026-10-29T10:17:00Z \
  filename=/srv/diagnostics/incident-window.jfr
```

`latency`, đường dẫn và timestamp đều là **mẫu**. Đây là cú pháp JDK 21 cho một recording tên `latency`; phải kiểm tra tên bằng `JFR.check`. JVM đích cần quyền ghi thư mục **trong filesystem của chính JVM**. `JFR.dump` không dừng recording, nhưng không tạo lại event trước khi recording bắt đầu hoặc đã bị xóa vì retention.

### 5.3. Nếu chưa có JFR mà sự cố còn tái diễn

Dựa trên rủi ro thu thập và nguồn lực, bật một recording **từ bây giờ** để chờ lần tái diễn; không thể xem lại quá khứ chưa được ghi:

```bash
jcmd <PID> JFR.start name=latency settings=profile \
  disk=true maxage=30m maxsize=256m
jcmd <PID> JFR.check verbose=true
```

Khi có symptom và đủ dữ liệu:

```bash
jcmd <PID> JFR.dump name=latency \
  filename=/srv/diagnostics/incident-full.jfr
```

`profile` thường có nhiều dữ liệu hơn `default` và có chi phí cao hơn; các số `30m`/`256m` chỉ minh họa, phải dự phòng theo rate event, quota, băng thông. Nếu cần event ngắn hơn ngưỡng, chuẩn bị `.jfc` với threshold riêng, kiểm thử trên staging/canary và ghi lại settings thực dùng. Bật quá nhiều exception/stack events ở ngưỡng cực thấp có thể tự làm thay đổi latency.

**Không bật Heap Statistics chỉ để phân tích latency**, vì tính năng này có thể kích hoạt old collections bổ sung và làm nhiễu phép đo.

### 5.4. Thu GC và safepoint unified logs để đối chiếu

Cấu hình từ startup (ví dụ Linux, thư mục đã tạo và có quyền ghi):

```bash
java -Xlog:gc*,safepoint:file=/srv/logs/gc-safe-%p.log:utctime,uptime,level,tags:filecount=4,filesize=20M \
  -jar app.jar
```

Cú pháp này bật nhóm GC và safepoint ở mức mặc định của lựa chọn tag, lưu log có **UTC timestamp + uptime JVM** và xoay vòng. `app.jar`/đường dẫn chỉ là ví dụ; không bật đồng thời vô số tags `trace` trên production nếu chưa đo overhead. `filecount`/`filesize` là hạn mức xoay vòng gần đúng, không là cam kết chính xác từng byte.

Nếu ứng dụng đã chạy nhưng chưa có log cần thiết, **khả năng thay đổi log runtime qua `jcmd <PID> VM.log`** được JDK 21 hỗ trợ ở mức nhất định; đọc `jcmd <PID> help VM.log` và xin quyền vận hành trước khi làm. Việc bật log bây giờ chỉ cho bằng chứng từ thời điểm đó, không phục hồi các safepoints trước đó.

Trong report, giữ cả **GC ID, phase, pause duration và safepoint operation**. Đừng quy một safepoint do GC thành một “lần dừng thêm” ngoài GC pause đã ghi trong cùng khoảng.

### 5.5. Khi nghi ngờ monitor contention hoặc thread bị kẹt

Thu **vài snapshot** trong cửa sổ sự cố, có timestamp, nhưng chú ý chi phí của `Thread.print`:

```bash
jcmd <PID> help Thread.print
jcmd <PID> Thread.print -e -l
```

`Thread.print` được tài liệu JDK 21 xếp tác động **Medium**, tùy số thread; không chụp hàng trăm full dumps liên tiếp ở dịch vụ có nhiều threads. Một snapshot `BLOCKED`/`WAITING` chỉ là một lát cắt; so nhiều mốc và JFR event để thấy vùng chờ lặp.

Với virtual threads, `Thread.print` truyền thống không hiển thị đầy đủ mọi virtual thread; tùy trường hợp cân nhắc công cụ virtual-thread dump và JFR. Không giả định virtual thread có một OS TID cố định để ghép với `top -H`.

## 6. Đối chiếu trên cùng timeline: ví dụ tính đúng phần giao

Một request bị chậm mất **900 ms**. Dưới đây là các khoảng **giả định trên cùng một request/JVM** và tính theo mili giây kể từ khi request bắt đầu:

```text
Request wall-clock: [0,900) ms

                         0   100  200  300  400  500  600  700  800  900
Request             :     |=============================================|
JavaMonitorEnter    :         [ 80.............250)
Safepoint interval  :                [195............335)
GCPhasePause        :                 [200........330)
SocketRead          :                             [350................770)
```

| Hiện tượng | Khoảng | Duration | Diễn giải |
| --- | --- | --- | --- |
| Chờ vào monitor | `[80,250)` | 170 ms | Thread trên critical path có thể chờ lock |
| Safepoint JVM | `[195,335)` | 140 ms | Giao với monitor wait; cần biết operation |
| GC pause | `[200,330)` | 130 ms | Đã nằm **trong** safepoint ở ví dụ này |
| Socket read | `[350,770)` | 420 ms | Request chờ dữ liệu từ peer/DB giả định |
| Request | `[0,900)` | 900 ms | Tổng elapsed tại một tầng đo xác định |

Nếu cộng bốn duration được `170+140+130+420 = 860 ms`, sẽ có ít nhất hai lỗi: **GC đã nằm trong safepoint**, và safepoint **giao** với monitor wait. Không thể gán 860 ms thành “phần delay do bốn nguyên nhân” theo cách cộng đơn giản.

Tính hợp khoảng của ba nhóm chờ/safepoint/IO (GC con của safepoint):

```text
Monitor [80,250) ∪ Safepoint [195,335)  = [80,335)  (255 ms)
Socket  [350,770)                       = [350,770) (420 ms)

Hợp các khoảng được quan sát trong ví dụ = 255 + 420 = 675 ms
Thời gian request còn lại ngoài hợp       = 900 - 675 = 225 ms
```

**Ngay cả 675 ms cũng KHÔNG là “thời gian chắc chắn đã mất do bốn nguyên nhân”**: vài interval thuộc thread khác hoặc safepoint có thể không tác động request cụ thể; số liệu nhiều thread có thể lồng nhau; phần 225 ms chưa phân loại có thể gồm CPU, queue, xử lý application hoặc chờ chưa được ghi vì threshold.

Phép giao cho một event duration `[a,b)` và symptom `[c,d)`:

```text
overlap = max(0, min(b,d) - max(a,c))
```

Với event **tức thời** (duration = 0), xét `c ≤ timestamp < d`; không tính tổng duration bằng 0 rồi kết luận “không có event”. Với event kéo dài bắt đầu trước symptom, lọc **chỉ theo startTime** sẽ bỏ sót giao cửa sổ.

### 6.1. Tập sự kiện không có request ID

Phần lớn JFR events là telemetry JVM, **không kèm HTTP request ID**. Có thể cùng JVM thời điểm 10:15 có 50 request, một GC và 200 `SocketRead`; không thể biết event nào thuộc request p99 chỉ từ chung timestamp.

Cần xác thực bằng **request trace và stack/thread/endpoint**, custom JFR event hoặc instrumentation đã có. Nếu app dùng executor, async callbacks hoặc virtual threads, một request có thể chuyển thread. Thread ID và eventThread chỉ là đầu mối, không đủ xây dựng parent-child request chain.

### 6.2. Tách pha nguyên nhân và hiệu ứng thứ cấp

Giả sử timeline: downstream response chậm trước, sau đó connection pool hết, nhiều caller park, rồi một monitor trong logger bị tranh. Tất cả xảy ra “đồng thời” trên dashboard nhưng quan hệ khả dĩ là:

```text
Downstream queue / slow response
        ↓
SocketRead duration và các request đang chờ tăng
        ↓
Connection-pool queue / ThreadPark tăng
        ↓
Request backlog, retries, thread contention tăng
        ↓
p99 và timeout tăng
```

Đây mới là **giả thuyết có thể kiểm chứng** bằng span phía downstream, pool metrics, retry counts và thời điểm tăng. Không được tuyên bố causality chỉ từ một file JFR.

## 7. Quy trình JDK Mission Control: kiểm tra từng lớp

Trong JMC (tên trang có thể khác theo phiên bản):

1. Mở `.jfr` và xác minh **JDK build, JVM identity, recording start/end, config, duration**.
2. Chọn đúng **analysis window** trên timeline; so timestamp với APM/gateway và clock drift. Giữ selection nhất quán khi chuyển tab.
3. Xem **GC pauses**: đừng nhìn chỉ số “GC duration” chung; tìm pause thực, GC ID và xem có trùng request spikes không. So với safepoint log.
4. Xem **threads/locks**: monitor contention, thread parking/waiting, stack của waiter và owner nếu có. Dùng duration/timestamp, không kết luận từ count thuần.
5. Xem **Socket I/O / File I/O**: peer/file nào dài bất thường, tập trung vào thread/stack liên quan và span downstream.
6. Kiểm tra **CPU/ExecutionSample** để loại trừ CPU saturation làm request chạy chậm; đồng thời kiểm tra GC, safepoint và thread scheduling.
7. Mở **khoảng đối chứng** cùng độ dài và settings; đánh giá tỷ lệ/percentile thay vì số event thô.
8. Quay về tracing/metrics để xác định request critical path và xác nhận giả thuyết. Xuất bảng bằng chứng với cả dữ liệu ủng hộ và dữ liệu chống.

JMC giúp nhìn timeline, **không tự suy luận quan hệ nhân quả**. Nếu không có event type trong recording, phải ghi “không đủ dữ liệu”, không tự coi nhóm đó bằng 0.

## 8. Lab Java 21: tạo lock wait và I/O wait trong cùng recording

Lab này chạy **độc lập**, chỉ dùng loopback socket trong chính máy, không truy cập server ngoài. Nó tạo hai pha rõ ràng:

- Thread `monitor-owner` giữ một `synchronized` monitor trong khi chờ `CountDownLatch`; thread `monitor-waiter` cố vào monitor và bị chặn.
- Thread `mock-peer` chờ khoảng 180 ms rồi gửi một byte; client `SocketRead` phải chờ peer.
- Custom JFR instant events `demo.Phase` đánh dấu mốc pha để so với `jdk.JavaMonitorEnter`, `jdk.ThreadPark` và `jdk.SocketRead`. Tất cả duration chính xác phụ thuộc scheduler, OS và JDK; **không phải benchmark latency production**.
- Lab **không cố ép GC/safepoint** và vì thế có thể không có GC pause đáng kể. Dùng một recording Java 21 khác có GC và safepoint logs để làm phần đối chiếu GC thực tế; không gọi `System.gc()` trên production chỉ để tạo bằng chứng.

Tạo file **`LatencySignalsLab.java`**:

```java
import java.net.InetAddress;
import java.net.ServerSocket;
import java.net.Socket;
import java.nio.file.Path;
import java.time.Duration;
import java.util.concurrent.CountDownLatch;
import jdk.jfr.Configuration;
import jdk.jfr.Event;
import jdk.jfr.Label;
import jdk.jfr.Name;
import jdk.jfr.Recording;

public class LatencySignalsLab {
    private static final Object MONITOR = new Object();

    @Name("demo.Phase")
    @Label("Lab phase marker")
    public static class Phase extends Event {
        @Label("Phase name")
        String name;
    }

    private static void mark(String name) {
        Phase phase = new Phase();
        phase.name = name;
        phase.commit();
    }

    public static void main(String[] args) throws Exception {
        try (Recording recording = new Recording(
                Configuration.getConfiguration("profile"))) {
            recording.setToDisk(true);
            recording.enable(Phase.class);
            recording.enable("jdk.JavaMonitorEnter")
                     .withThreshold(Duration.ofMillis(1));
            recording.enable("jdk.SocketRead")
                     .withThreshold(Duration.ofMillis(1));
            recording.enable("jdk.ThreadPark")
                     .withThreshold(Duration.ofMillis(1));
            recording.start();

            mark("lock-start");
            lockPhase();
            mark("lock-end");
            System.out.println("LOCK PHASE COMPLETE");

            mark("io-start");
            socketPhase();
            mark("io-end");
            System.out.println("IO PHASE COMPLETE");

            recording.stop();
            recording.dump(Path.of("latency-signals.jfr"));
        }
        System.out.println("LAB DONE: latency-signals.jfr");
    }

    private static void lockPhase() throws Exception {
        CountDownLatch locked = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);
        CountDownLatch attempting = new CountDownLatch(1);

        Thread owner = new Thread(() -> {
            synchronized (MONITOR) {
                locked.countDown();
                try {
                    release.await();
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                }
            }
        }, "monitor-owner");
        Thread waiter = new Thread(() -> {
            attempting.countDown();
            synchronized (MONITOR) {
            }
        }, "monitor-waiter");

        owner.start();
        locked.await();
        waiter.start();
        attempting.await();
        try {
            Thread.sleep(180);
        } finally {
            release.countDown();
        }
        owner.join();
        waiter.join();
    }

    private static void socketPhase() throws Exception {
        try (ServerSocket server = new ServerSocket(
                0, 1, InetAddress.getLoopbackAddress())) {
            Thread peer = new Thread(() -> {
                try (Socket conn = server.accept()) {
                    Thread.sleep(180);
                    conn.getOutputStream().write(42);
                    conn.getOutputStream().flush();
                } catch (Exception e) {
                    throw new IllegalStateException(e);
                }
            }, "mock-peer");
            peer.start();
            try (Socket client = new Socket(
                    InetAddress.getLoopbackAddress(), server.getLocalPort())) {
                int value = client.getInputStream().read();
                if (value != 42) {
                    throw new IllegalStateException("Unexpected response: " + value);
                }
            }
            peer.join();
        }
    }
}
```

Biên dịch/chạy bằng **JDK 21** trong thư mục thử nghiệm có quyền ghi:

```bash
javac LatencySignalsLab.java
java LatencySignalsLab
jfr summary latency-signals.jfr
jfr print --stack-depth 64 \
  --events demo.Phase,jdk.JavaMonitorEnter,jdk.ThreadPark,jdk.SocketRead \
  latency-signals.jfr
```

**Stdout do chương trình Java in**, không kể các lệnh `jfr` và thông điệp hệ thống:

```text
LOCK PHASE COMPLETE
IO PHASE COMPLETE
LAB DONE: latency-signals.jfr
```

Khi xem recording, `demo.Phase` có mốc `lock-start`, `lock-end`, `io-start`, `io-end`. Một `jdk.JavaMonitorEnter` dài ở `monitor-waiter` cho thấy chờ vào `synchronized`; `jdk.ThreadPark` có thể xuất hiện ở `monitor-owner` vì nó đang chờ `CountDownLatch` **trong khi vẫn giữ monitor**. Điều này minh họa tại sao **park không luôn là nơi gây tranh chấp, mà có thể là nguyên nhân khiến lock holder giữ monitor lâu**.

`jdk.SocketRead` thường xuất hiện trong pha `io-start` → `io-end`, nhưng không khẳng định count hay duration chính xác trên mọi JDK/OS. Nếu event thiếu, kiểm tra threshold, recording settings, JVM build và thời gian hoạt động. Không chạy demo trên server production.

## 9. Phân tích giao cửa sổ bằng chương trình Java 21

Nếu cần lọc chính xác `.jfr` theo **time window**, có thể dùng `RecordingFile` trong module `jdk.jfr`. Ví dụ `LatencyWindowReport.java` bên dưới đọc tuần tự events, đếm các event đã ghi có thời gian giao cửa sổ và tính tổng **millisecond-overlap theo từng event type**.

Tạo file **`LatencyWindowReport.java`**:

```java
import java.nio.file.Path;
import java.time.Duration;
import java.time.Instant;
import java.time.OffsetDateTime;
import java.util.Map;
import java.util.Set;
import java.util.TreeMap;
import jdk.jfr.consumer.RecordedEvent;
import jdk.jfr.consumer.RecordingFile;

public class LatencyWindowReport {
    private static final Set<String> SELECTED = Set.of(
        "jdk.GarbageCollection",
        "jdk.GCPhasePause",
        "jdk.JavaMonitorEnter",
        "jdk.JavaMonitorWait",
        "jdk.ThreadPark",
        "jdk.SocketRead",
        "jdk.SocketWrite",
        "jdk.FileRead",
        "jdk.FileWrite",
        "demo.Phase"
    );

    static class Totals {
        long count;
        long overlapNanos;
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 3) {
            System.err.println(
                "Usage: java LatencyWindowReport file.jfr fromISO toISO");
            return;
        }
        Instant from = OffsetDateTime.parse(args[1]).toInstant();
        Instant to = OffsetDateTime.parse(args[2]).toInstant();
        if (!from.isBefore(to)) {
            throw new IllegalArgumentException("from must precede to");
        }
        Map<String, Totals> totals = new TreeMap<>();
        try (RecordingFile recording = new RecordingFile(Path.of(args[0]))) {
            while (recording.hasMoreEvents()) {
                RecordedEvent event = recording.readEvent();
                String type = event.getEventType().getName();
                if (!SELECTED.contains(type)) {
                    continue;
                }
                Instant start = event.getStartTime();
                Instant end = event.getEndTime();
                boolean instant = !end.isAfter(start);
                boolean intersects = instant
                    ? !start.isBefore(from) && start.isBefore(to)
                    : start.isBefore(to) && end.isAfter(from);
                if (!intersects) {
                    continue;
                }
                long nanos = 0;
                if (!instant) {
                    Instant clippedStart =
                        start.isAfter(from) ? start : from;
                    Instant clippedEnd =
                        end.isBefore(to) ? end : to;
                    nanos = Duration.between(
                        clippedStart, clippedEnd).toNanos();
                }
                Totals t = totals.computeIfAbsent(
                    type, key -> new Totals());
                t.count++;
                t.overlapNanos += nanos;
            }
        }
        System.out.println("WINDOW: " + from + " .. " + to);
        for (Map.Entry<String, Totals> row : totals.entrySet()) {
            System.out.printf(java.util.Locale.ROOT,
                "%s count=%d overlap_ms=%.1f%n",
                row.getKey(), row.getValue().count,
                row.getValue().overlapNanos / 1_000_000.0);
        }
        if (totals.isEmpty()) {
            System.out.println("No selected events in window");
        }
    }
}
```

Biên dịch và truyền cửa sổ **ISO-8601 kèm offset**, ví dụ:

```bash
javac LatencyWindowReport.java
java LatencyWindowReport incident.jfr \
  2026-10-29T10:14:30Z 2026-10-29T10:17:00Z
```

Hoặc với lab, thay file bằng `latency-signals.jfr` và **tự lấy timestamp thật** từ `jfr print`. Vì recording khác nhau, **không có bảng stdout cố định**; chương trình luôn in `WINDOW: ...` và các dòng `event type count=... overlap_ms=...`. Nếu không có event đã chọn trong cửa sổ thì in `No selected events in window`.

**Giới hạn của báo cáo** rất quan trọng:

- `count` chỉ là số event **đã được thu** vượt ngưỡng, không phải số thao tác thực.
- `overlap_ms` theo từng type là **tổng duration của events** giao cửa sổ, **chưa loại trừ lồng nhau giữa các events cùng type** và càng không loại trừ trùng nhau giữa **nhiều thread**.
- `jdk.GarbageCollection` và `jdk.GCPhasePause` không thể cộng chung thành STW duration. Safepoint logs cần ghép riêng vì chương trình này không parse safepoint logs.
- Những event có duration bằng 0 (`demo.Phase`) có count nhưng `overlap_ms=0`. Đây là **mốc thời gian**, không phải bằng chứng “không có gì xảy ra”.
- Chương trình không biết request ID hay critical path; muốn phân tích nhân quả, cần thêm trace/stack/peer và thuật toán **hợp khoảng trên một request**.

Chương trình dùng `RecordingFile.hasMoreEvents()/readEvent()` để không cần tải mọi event vào một danh sách lớn trong RAM; với tệp rất lớn vẫn cần dự tính thời gian quét và dung lượng đĩa của bản sao.

## 10. Bốn tình huống phân biệt nguyên nhân chính

### 10.1. GC pause trùng một phần tail latency

**Quan sát:** P99 lên 900 ms; JFR có `jdk.GCPhasePause` 130 ms giao request; cùng lúc `SocketRead` 500 ms. **Diễn giải:** GC có thể đóng góp khoảng giao của 130 ms, nhưng không thể giải thích một mình 900 ms. Phải kiểm tra trace của request có đợi socket hay không và lúc GC kết thúc request tiếp tục thế nào.

**Kiểm tra tiếp:** Đối chứng request không giao GC, phân bố GC pauses khác nhau, pause metrics trên instance, correlation giữa GC phase và backlog. Đừng lập tức tăng `-Xmx` hoặc đổi collector khi bằng chứng chính nằm ở downstream.

### 10.2. Safepoint dài nhưng GC log yên lặng

**Quan sát:** p99 tăng trong 800 ms, safepoint log cho thấy một operation dài; GCPhasePause không đáng kể trong cùng khoảng. **Diễn giải:** Safepoint có thể liên quan nhưng **không được tự gọi nó là GC**.

**Kiểm tra tiếp:** Tên VM operation, thời gian threads đạt safepoint, thời gian operation, thread/JNI context; kiểm tra cùng JDK, GC logs và khung giờ. Nếu operation không đụng critical request threads hoặc clock lệch, phải điều chỉnh giả thuyết.

### 10.3. Monitor contention có owner chờ I/O

**Quan sát:** `JavaMonitorEnter` của nhiều workers kéo dài 400 ms; stack owner có I/O hoặc park trong critical section; `SocketRead` của owner cũng dài. **Diễn giải:** Lock contention là triệu chứng trực tiếp ở waiters, nhưng việc **giữ lock khi chờ I/O** có thể là nguyên nhân sâu hơn.

**Kiểm tra tiếp:** Lock owner thực tế và call stack, độ dài critical section, outbound span, số request đợi monitor, timeout. Hướng sửa đúng có thể là đưa blocking I/O **ra ngoài vùng synchronized**, sau khi chứng minh thread safety và correctness.

### 10.4. SocketRead dài, GC bình thường, CPU chưa bão hòa

**Quan sát:** GC pauses rất ngắn, safepoint activity bình thường, threads chủ yếu chờ socket trong 1 giây, peer DB cũng có queue/slow query. **Diễn giải:** Giả thuyết downstream I/O mạnh hơn JVM pause.

**Kiểm tra tiếp:** Trace DB, pool borrow time, TCP retry, network metrics, timeout/retry policy và số request/giây. Nếu JFR chỉ ghi socket read **sau** thời điểm request đã trễ lâu ở ingress queue, phải mở rộng timeline ra tầng ngoài JVM.

## 11. Những sai lầm thường gặp

| Sai lầm | Vì sao sai | Cách làm đúng |
| --- | --- | --- |
| “GC duration 1 giây → JVM pause 1 giây” | Có pha concurrent; duration khác STW pause | Dùng GC pause events/JMC GC pauses và safepoint log |
| “Safepoint + GC pause = hai lần dừng” | Cùng operation có thể lồng nhau | So timeline và GC ID, tính hợp khoảng |
| “Nhiều `JavaMonitorEnter` cùng lúc là CPU cao” | Waiters có thể BLOCKED, không chạy trên CPU | So thread state, CPU/OS metrics và owner stack |
| “`ThreadPark` nghĩa là deadlock” | Park là primitive bình thường ở queue/latch/pool | Tìm caller, owner, queue, progress và duration |
| “`JavaMonitorWait` giống chờ vào synchronized” | `Object.wait` nhả monitor trước khi chờ | Phân biệt wait condition với enter contention |
| “Một `SocketRead` lâu = lỗi mạng” | Peer, pool, retry, app logic hoặc scheduling có thể kéo dài | Ghép remote span, endpoint, file/socket metrics |
| “Không thấy event = nguyên nhân không tồn tại” | Threshold/config/retention/sampling/lost data | Kiểm tra `.jfc` và event metadata trước |
| “Cộng mọi event duration = request latency” | Song song, lồng nhau, khác request, khác thread | Giao/hợp khoảng trên **critical path** có xác thực |
| “Một thread dump đủ xác định chủ lock” | Snapshot có thể bắt pha không đại diện | Lấy nhiều snapshots và event trong symptom window |
| “p99 tăng phút 10:15 nghĩa là GC 10:15:00 gây ra” | Bucket metric không có độ chính xác từng request | Trace request start/end và kiểm tra clock skew |
| “JFR profile không ảnh hưởng latency” | Thu event, stack và threshold đều có overhead | Thử tải, chọn cấu hình đủ dùng, giới hạn thời gian |
| “Thấy correlation rồi sửa JVM flags” | Có thể xử lý nhầm triệu chứng | Đặt giả thuyết kiểm chứng và so metrics sau can thiệp |

## 12. Runbook sản xuất: trước, trong và sau

### Trước khi thu

- [ ] Xác định service/endpoint/pod/PID và startup/JDK build, vị trí của request latency (gateway hay application).
- [ ] Ghi symptom window, control window, timezone, độ phân giải và clock skew.
- [ ] Có quyền dùng JFR/jcmd, vị trí ghi file, quota/disk headroom, retention và phân quyền đọc.
- [ ] Chọn JFR config/threshold tương xứng; đo thử overhead nếu cần tăng số event/stack.
- [ ] Chuẩn bị GC/safepoint logging có timestamp UTC và quay vòng file, không tự thêm hoạt động có STW chỉ để thí nghiệm trên production.

### Trong khi điều tra

- [ ] Bảo toàn trace/metrics/request volume, CPU, GC pause, safepoint, pool và downstream latency.
- [ ] Lấy/JFR.dump recording đúng JVM và khoảng có symptom, tránh nhầm retention/cửa sổ.
- [ ] Xem `jdk.GCPhasePause` và GC ID **trước khi** kết luận GC nguyên nhân.
- [ ] Xem safepoint operation và thời gian (đợi thread + operation) **không cộng trùng** với GC pause.
- [ ] Xem lock owner/waiter stack, `ThreadPark`, I/O endpoint/file/peer; chỉ gắn vào request khi có tương quan đủ mạnh.
- [ ] So thời gian, event duration, sampling/threshold và đối chứng; ghi cả bằng chứng chống giả thuyết.

### Sau khi điều tra

- [ ] Báo cáo **một timeline UTC**, giả thuyết chính, phụ, độ tin cậy, dữ liệu thiếu và tác động tới SLO.
- [ ] Đề xuất **phép kiểm chứng có thể bác bỏ**: ví dụ sau giảm time holding lock, số monitor waits và p99 phải giảm ở cùng tải.
- [ ] Đo lại p95/p99, error rate, throughput, CPU-seconds/request, GC pause, pool queue và downstream latency sau thay đổi.
- [ ] Bảo toàn recording gốc, checksum và bối cảnh; file `.jfr` có thể chứa class/method/host/path nội bộ, không chia sẻ công khai.
- [ ] Xóa hoặc lưu trữ có thời hạn theo policy; không để data nhạy cảm tồn tại vô hạn trong thư mục tạm.

## 13. Mẫu kết luận có trách nhiệm

**Ví dụ giả định có bằng chứng:**

```text
Triệu chứng:
  checkout-api p99 tăng 150ms -> 1200ms trong 10:15:00..10:16:30 UTC.
Phạm vi:
  pod X, JVM Java 21 PID/uptime được xác minh; APM và JFR clock ±100ms.
Dữ liệu ủng hộ:
  70% slow traces có outbound DB span 500-900ms.
  JFR SocketRead trên cùng thread/stack/peer giao nhiều span.
  GCPhasePause trong cửa sổ tối đa 35ms; safepoint logs không có
  pause dài tương ứng; JavaMonitorEnter tăng sau khi pool queue tăng.
Giả thuyết ưu tiên:
  Chờ DB/downstream làm các request xếp hàng; monitor contention
  ở thành phần phụ là hậu quả khi concurrency tăng.
Không đủ bằng chứng:
  Chưa xác định nguyên nhân DB chậm (query, lock, storage hay network).
Kiểm chứng tiếp:
  Đối chiếu slow-query metrics, pool borrow times, DB tracing;
  thử thay đổi có kiểm soát và đo lại p99/error rate theo cùng tải.
```

Đây là **mẫu diễn giải**, không phải kết quả của lab hay hệ thống thật. Nếu 70% traces chưa đủ bao trùm mẫu hoặc clock sai, phải hạ mức tin cậy. Một báo cáo tốt chỉ ra **khoảng thời gian nào, request nào và event nào thực sự có liên hệ**, thay vì đổ lỗi cho event lớn nhất.

## 14. Bài tập tự đánh giá

1. Một request 1.000 ms giao GC pause 80 ms; `jdk.GarbageCollection` duration 1.400 ms. Bạn có thể kết luận bao nhiêu mili giây của request do GC gây ra? Nêu dữ liệu thiếu.
2. Dùng bảng mục 6, tính hợp của monitor wait, safepoint và I/O; giải thích vì sao 860 ms là tổng sai và vì sao hợp 675 ms chưa là “chi phí nhân quả”.
3. Chạy `LatencySignalsLab` trên JDK 21, mở `latency-signals.jfr`, chỉ ra mốc `demo.Phase`, các event monitor/park/socket trong cùng timeline. Thử đổi ngưỡng JFR và nói vì sao count thay đổi.
4. Trên một recording có GC activity, so `jdk.GCPhasePause` với safepoint logs theo UTC/uptime; xác nhận GC pause đã nằm trong khoảng safepoint nào (nếu có).
5. Giả sử 200 requests đang chờ socket đồng thời 500 ms. Vì sao tổng SocketRead duration có thể là 100.000 ms nhưng latency của từng request không cộng theo cách đó?
6. Vẽ một timeline có **GC pause ngoài symptom window** nhưng downstream timeout trùng symptom; giải thích cách loại bỏ giả thuyết “GC là nguyên nhân chính”.
7. Thiết kế một bản ghi incident với `service`, `JDK`, `GC`, `JFR settings`, `timestamp uncertainty`, `trace`, `GC pause`, `safepoint op`, `lock owner`, `peer`, `hypothesis` và phép kiểm chứng.

**Checklist tự hoàn thành:** đã định nghĩa latency ở đúng tầng; chuẩn hóa UTC; kiểm tra JFR settings/threshold; phân biệt GC activity với pause; phân biệt safepoint GC và non-GC; đọc đúng monitor enter/wait/park; ghép I/O với downstream trace; tính giao và hợp khoảng không double-count; sử dụng đối chứng; nêu kết luận với độ tin cậy và bước kiểm chứng.

## 15. Tài liệu gốc cho Java 21

- [Oracle JDK 21 — Troubleshoot Performance Issues Using Flight Recorder: GC, synchronization, I/O và threshold](https://docs.oracle.com/en/java/javase/21/troubleshoot/troubleshoot-performance-issues-using-jfr.html)
- [Oracle JDK 21 — `java`: Unified Logging, `-Xlog`, tags `gc` và `safepoint`, UTC decorators](https://docs.oracle.com/en/java/javase/21/docs/specs/man/java.html)
- [Oracle JDK 21 — `jcmd`: `JFR.start`, `JFR.check`, `JFR.dump`, `Thread.print` và `VM.log`](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html)
- [Oracle JDK 21 — `jfr`: `summary`, `print`, `metadata`](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jfr.html)
- [Oracle JDK 21 — `RecordedEvent` time interval API](https://docs.oracle.com/en/java/javase/21/docs/api/jdk.jfr/jdk/jfr/consumer/RecordedEvent.html)
- [Oracle JDK 21 — `RecordingFile` streaming reader](https://docs.oracle.com/en/java/javase/21/docs/api/jdk.jfr/jdk/jfr/consumer/RecordingFile.html)
- [Oracle JDK 21 — `Recording` and `Configuration` programmatic APIs](https://docs.oracle.com/en/java/javase/21/docs/api/jdk.jfr/jdk/jfr/Recording.html)
