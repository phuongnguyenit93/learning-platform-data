# 2.6 Đồng bộ timestamp, múi giờ và uptime khi ghép nhiều nguồn dữ liệu

Khi điều tra một sự cố JVM, dữ liệu thường đến từ nhiều nơi: log ứng dụng, log GC, Java Flight Recorder (JFR), thread dump, metrics hệ điều hành, Kubernetes, Prometheus và distributed traces. Các nguồn này có thể cùng ghi về **một sự kiện thật** nhưng thể hiện thời gian theo **UTC, giờ địa phương, epoch, uptime từ lúc JVM chạy, uptime từ lúc máy khởi động hoặc thời điểm hệ thống giám sát nhận dữ liệu**. Nếu ghép trực tiếp các con số chưa quy đổi, timeline có thể bị lệch nhiều giờ, nhầm thứ tự nhân quả hoặc tạo ra “độ trễ âm”.

Mục tiêu của bài là xây dựng **một timeline chẩn đoán đáng tin cậy**: hiểu ngữ nghĩa từng đồng hồ, chuẩn hóa thời điểm về UTC khi có đủ căn cứ, chuyển uptime bằng mốc tham chiếu thuộc đúng tiến trình hoặc boot, ghi độ không chắc chắn, và giữ nguyên dữ liệu gốc để kiểm toán.

## 1. Hai câu hỏi khác nhau: “khi nào?” và “mất bao lâu?”

Một sự kiện có ít nhất hai khía cạnh thời gian:

- **Thời điểm tuyệt đối (absolute time, wall-clock time):** “GC bắt đầu lúc 08:14:05.400 UTC”. Dùng để đặt sự kiện từ nhiều máy lên cùng timeline.
- **Khoảng thời gian đã trôi qua (elapsed duration):** “Một tác vụ chạy 150 ms”. Dùng để đo latency, thời lượng pause hoặc timeout; ưu tiên một đồng hồ đo thời gian trôi qua có tính đơn điệu trong cùng môi trường.

Những đại lượng này không tự động chuyển đổi được cho nhau:

- `2026-10-29T08:14:05.400Z` là một thời điểm UTC có ý nghĩa toàn cục **theo độ chính xác của đồng hồ nguồn**.
- `905400 ms` kể từ lúc JVM bắt đầu **không có nghĩa gì trên timeline toàn cục** nếu chưa biết nó thuộc JVM nào và mốc JVM start.
- `8045400 ms` kể từ lúc hệ điều hành boot khác hoàn toàn với JVM uptime, dù đơn vị đều là mili giây.
- `System.nanoTime()` trả giá trị từ gốc thời gian tùy ý; chỉ phép **trừ hai giá trị trong cùng JVM** mới là khoảng đo có ý nghĩa.
- Thời điểm collector nhận được log thường **muộn hơn** lúc log được sinh ra; đó là một trường thời gian khác.

Một câu hỏi chẩn đoán như “GC có xảy ra trong lúc p99 tăng không?” cần **thời điểm và khoảng kéo dài của GC**, một khoảng thời gian p99 được đo, nguồn đồng hồ, độ lệch đồng hồ giữa các node, cùng phạm vi workload. Chỉ thấy hai dòng log gần nhau chưa đủ kết luận quan hệ nhân quả.

## 2. Nhận diện đúng loại đồng hồ

| Kiểu thời gian | Ý nghĩa và cách xuất hiện | Có thể ghép trực tiếp với nguồn khác? | Giới hạn |
| --- | --- | --- | --- |
| **UTC instant** | `2026-10-29T08:14:05.250Z`; Java `Instant`, ISO 8601 có `Z` | Có, sau khi đánh giá sai số và thời điểm phát sinh | Đồng hồ host có thể sai hoặc bị điều chỉnh |
| **Wall-clock có offset** | `2026-10-29T15:14:05.250+07:00` | Có: đổi về cùng `Instant` | Offset cho biết vị trí trên timeline; không cho biết độ chính xác đồng hồ |
| **Giờ địa phương không kèm zone/offset** | `2026-10-29 15:14:05` | **Không**; cần metadata zone và quy tắc DST tại ngày đó | Có thể mơ hồ hoặc không tồn tại khi chuyển giờ mùa hè |
| **Epoch timestamp** | Giây/ms/µs/ns từ `1970-01-01T00:00:00Z` | Có nếu biết **đơn vị** và semantics | Nhầm giây với mili giây gây lệch hàng chục nghìn năm; ns trong số thực có thể mất chính xác |
| **JVM uptime** | `905400ms` hoặc `905.400s` từ lúc JVM bắt đầu | Chỉ sau khi xác định đúng JVM instance và mốc tham chiếu | Reset khi JVM restart; thời điểm start có thể chỉ xấp xỉ |
| **OS boot uptime / monotonic** | `[8045.400000]` trong journal theo thời gian kể từ boot | Chỉ sau khi xác định đúng máy/boot ID và mốc | Reset sau reboot; phụ thuộc clock và chế độ suspend/virtualization |
| **High-resolution elapsed clock** | `System.nanoTime()` | Chỉ so hiệu số trong **cùng JVM** | Không phải epoch nanoseconds; không dùng số nguyên thô để ghép nhiều JVM |
| **Event duration** | JFR `duration=120 ms`, span duration, GC pause 18 ms | So sánh độ dài sau khi xác minh đơn vị | Không tự chỉ ra event bắt đầu vào lúc nào |
| **Observed/ingest/scrape time** | Collector nhận log lúc 08:14:06; Prometheus sample lúc scrape | Được nếu cần phân tích ingestion/scrape | Không mặc định là lúc sự kiện nghiệp vụ xảy ra |

**Phân biệt rõ:** “đúng múi giờ” và “đúng đồng hồ” là hai vấn đề độc lập. Chuyển từ `+07:00` sang `Z` sửa *cách biểu diễn* cùng một instant; nó không sửa được một node đang chạy nhanh hơn giờ chuẩn 200 ms.

### 2.1. Wall clock và monotonic clock trong Java

- `Instant.now()` và `System.currentTimeMillis()` dựa vào thời gian hệ thống, dùng cho timestamp có thể trao đổi giữa tiến trình. Chúng chịu ảnh hưởng của đồng bộ giờ, thay đổi thủ công và độ phân giải đồng hồ.
- `System.nanoTime()` dành cho đo elapsed time; gốc tùy ý và không liên hệ trực tiếp với UTC. Lấy `endNs - startNs` trong cùng JVM để đo thời lượng; không lưu `nanoTime` như UNIX epoch.
- `ManagementFactory.getRuntimeMXBean().getStartTime()` trả **thời điểm khởi chạy JVM xấp xỉ**, theo epoch milliseconds; `getUptime()` trả JVM uptime theo milliseconds.
- `ZoneId.systemDefault()` chỉ quyết định cách hiển thị ngày giờ địa phương theo cấu hình tiến trình; nó **không sửa** giờ UTC của host.

Trong chẩn đoán, nên lưu cả `event_time_utc` và `elapsed_duration_ms` khi mỗi thông tin có ích. Một process có thể ghi đúng duration bằng monotonic clock ngay cả khi wall clock bị điều chỉnh, nhưng dùng wall clock đã lệch để so thứ tự sự kiện giữa hai máy vẫn có thể sai.

## 3. Chuẩn hóa múi giờ: một instant, nhiều cách viết

Cùng một thời điểm có thể biểu diễn như sau:

| Biểu diễn nguồn | Chuẩn hóa UTC | Ghi chú |
| --- | --- | --- |
| `2026-10-29T15:14:05.250+07:00` | `2026-10-29T08:14:05.250Z` | Trừ offset +07:00 **một lần** |
| `2026-10-29T08:14:05.250Z` | Giữ nguyên | `Z` tương ứng UTC+00:00 |
| `1793261645.25` UNIX seconds | `2026-10-29T08:14:05.250Z` | Số giây có phần thập phân |
| `1793261645250` UNIX milliseconds | `2026-10-29T08:14:05.250Z` | Số mili giây nguyên |

**Không được** đọc `15:14+07:00` thành `15:14Z` rồi tiếp tục cộng/trừ 7 giờ. Offset đã được tính khi chuyển `OffsetDateTime` sang `Instant`.

### 3.1. Offset khác ZoneId

- `+07:00` là **offset cố định** so với UTC tại một thời điểm.
- `Asia/Ho_Chi_Minh` là **zone ID** có quy tắc thời gian theo lịch sử.
- `America/New_York` là zone có quy tắc DST; cùng đồng hồ địa phương `01:30` tại ngày chuyển giờ mùa thu có thể ứng với **hai instant** khác nhau. Mùa xuân có các khoảng giờ địa phương **không tồn tại**.

Một chuỗi `2026-11-01 01:30:00` trên hệ thống New York không tự đủ để quyết định trước hay sau lần đổi giờ; cần offset, zone, dữ liệu hệ thống và ngữ cảnh. `LocalDateTime` không biểu diễn được một instant duy nhất khi thiếu zone/offset. Không tự gắn zone mặc định của **máy đang phân tích** vào log lấy từ máy khác.

Nếu log chỉ có dạng `dd/MM/yyyy HH:mm:ss` mà không có offset, đặt trạng thái **chưa xác định** cho đến khi xác minh cấu hình timezone của nguồn *ở thời điểm log được tạo*. Nếu buộc phải giả định một zone để điều tra, ghi nguyên giả định và giữ bản raw.

### 3.2. Precision khác accuracy

Timestamp có 9 chữ số sau dấu chấm chưa chắc đồng hồ chính xác tới nano giây. Cần phân biệt:

- **Precision / resolution:** độ mịn của trường số hoặc nguồn lấy mẫu (giây, mili giây, micro giây, nano giây).
- **Accuracy:** mức gần thời gian thực, chịu ảnh hưởng của NTP/PTP, lệch node, clock drift và timestamp ghi muộn.
- **Uncertainty:** khoảng sai số được ước lượng, ví dụ `±20 ms`.
- **Event time vs observed time:** ứng dụng tạo sự kiện trước; collector có thể nhận sau do hàng đợi, buffer hoặc mạng.

Đừng làm tròn về giây nếu cần so GC pause 20 ms với request timeout; cũng không in thêm chữ số `.000000` rồi ngụ ý đo được độ chính xác tốt hơn.

### 3.3. Tránh nhầm đơn vị epoch

Giá trị `1793261645250` trong ví dụ là **milliseconds**; chia 1.000 mới ra `1793261645.25` seconds. Không dự đoán đơn vị chỉ từ số chữ số, vì dữ liệu cũ, thời điểm âm, số thập phân và format riêng có thể phá quy tắc kinh nghiệm đó. Đặt trường hoặc metadata như `timestamp_unit=ms`, `epoch=unix`.

Trong Java, dùng `Instant.ofEpochMilli(epochMs)` cho ms; với giây và nano, dùng `Instant.ofEpochSecond(seconds, nanos)`. Khi xuất sang JavaScript, JSON hoặc bảng phân tích, tránh chuyển epoch nanoseconds 19 chữ số qua số thực IEEE-754 double vì dễ mất đơn vị ns; ưu tiên chuỗi nguyên hoặc kiểu số nguyên 64-bit có hỗ trợ.

## 4. Uptime phải gắn với **đúng gốc thời gian**

Có ít nhất ba gốc khác nhau trong một hệ thống:

1. **Boot của node/OS:** Linux monotonic/boottime theo một boot instance; systemd journal có thông tin boot và có thể hiển thị `short-monotonic`.
2. **Khởi chạy JVM:** Java unified log `uptime`/`uptimemillis` và RuntimeMXBean uptime tính từ JVM startup.
3. **Khởi chạy task/request/recording:** `System.nanoTime()` đo elapsed từ một mốc tùy chọn; JFR recording có start/end time riêng.

**Mỗi gốc phải đi cùng danh tính của nó**. PID có thể tái sử dụng sau restart; pod name có thể tiếp tục tồn tại khi container restart; boot uptime có thể reset sau reboot. Nên mang theo node ID, boot ID, container ID, JVM start instant, PID, deployment version, recording ID khi cần.

### 4.1. Phép chuyển uptime → UTC có điều kiện

Nếu ta có một **mốc ghép đồng thời** cho cùng loại đồng hồ:

- Mốc `anchor_utc` là thời điểm tuyệt đối đã chuẩn hóa.
- Mốc `anchor_uptime_ms` là uptime tương ứng của **chính tiến trình/JVM đó**.
- Sự kiện có `event_uptime_ms`.

Khi clock chạy ổn định trong đoạn quan sát:

```text
event_utc_estimate = anchor_utc
                   + (event_uptime_ms - anchor_uptime_ms)

Ví dụ: anchor_utc=08:14:05.000Z, JVM uptime tại anchor=905000ms
        event_uptime=905400ms
        => event_utc ước tính = 08:14:05.400Z
```

Đây là **ước lượng theo anchor**, không phải một định luật luôn chính xác: thu thập mốc có trễ, các clock có thể bị điều chỉnh hoặc drift. Nếu có vài anchor ở nhiều thời điểm, kiểm tra độ lệch để phát hiện clock step/slew. Với dữ liệu quan trọng, mang theo `uncertainty_ms` thay vì ghi thời điểm tính ra như chân lý chính xác tuyệt đối.

Một cách đơn giản hơn khi log GC có **cả `utctime` và `uptimemillis` trên cùng dòng** là dùng timestamp UTC của dòng đó và thời gian uptime của nó để kiểm chứng chéo. Đây là lý do nên bật đồng thời hai decorator khi cấu hình log chẩn đoán ngay từ đầu.

### 4.2. Đừng dùng uptime của OS thay cho JVM

Giả sử trong **ví dụ tổng hợp**:

- OS boot lúc `2026-10-29T06:00:00Z`.
- JVM start lúc `2026-10-29T07:59:00Z`.
- Có GC ở `2026-10-29T08:14:05.400Z`.

Tại thời điểm GC, JVM uptime là **905.400 s**, còn OS uptime là **8.045,400 s** (2 giờ, 14 phút, 5,400 giây). Nếu cộng `905.400 s` vào OS boot, ta đặt GC sai sớm gần **1 giờ 59 phút**. Mọi phép ghép phải dùng đúng clock origin và đúng instance.

Với container, không mặc định thời điểm pod được tạo trùng JVM start: container có thể restart; init container và app container khởi động khác lúc; PID namespace cũng có thể khiến PID nhìn thấy từ host khác PID bên trong container. Một số môi trường còn có clock/time namespace hoặc thay đổi thời gian do VM suspend; kiểm tra ngữ cảnh thực tế trước khi suy ra mốc.

## 5. Mỗi nguồn chẩn đoán có ngữ nghĩa thời gian riêng

### 5.1. Application logs

Ưu tiên một trường timestamp có offset rõ ràng, chẳng hạn `2026-10-29T08:14:05.250Z`; dùng `Instant` hoặc formatter ISO 8601 chuẩn. Nếu ứng dụng ghi local time, phải biết zone/offset thực tế của process khi log tạo. Ghi kèm request/trace ID, service, instance/container, PID hoặc process start ID khi có ích.

Phân biệt `event_time` (lúc code ghi sự kiện) và `observed_time`/`ingest_time` (lúc agent hoặc collector nhận). Trong pipeline bất đồng bộ, cùng một dòng có thể đến dashboard muộn; việc sort theo thời điểm ingest có thể đảo thứ tự hai sự kiện.

### 5.2. GC logs của HotSpot JDK 17+

JVM unified logging hỗ trợ các decorator chính:

| Decorator `-Xlog` | Ý nghĩa | Cách ghép |
| --- | --- | --- |
| `utctime` | Timestamp UTC trên dòng log | Dùng làm instant nếu host clock đủ tin cậy |
| `time` | Timestamp theo timezone hiển thị của môi trường | Parse cả offset, tránh mặc định UTC |
| `uptime` | Giây từ khi JVM start | Chỉ ghép trong cùng JVM |
| `uptimemillis` | Mili giây từ khi JVM start | Thuận tiện map sang instant với anchor |
| `timemillis` | Giá trị wall-clock epoch milliseconds | Xác minh đơn vị và timestamp semantics |
| `timenanos` | Từ nguồn `System.nanoTime()`, **không phải epoch ns** | Không dùng như UNIX epoch |
| `pid`, `tid`, `tags`, `level` | Metadata gắn dòng log với tiến trình/loại sự kiện | Hạn chế nhầm nguồn và cảnh báo |

Ví dụ cấu hình lúc khởi động ứng dụng; đường dẫn và kích thước file là ví dụ, điều chỉnh theo môi trường:

```bash
java '-Xlog:gc*,safepoint:file=gc.log:utctime,uptimemillis,pid,level,tags:filecount=5,filesize=20M' -jar app.jar
```

Thao tác này gắn cả **UTC** và **JVM uptime** vào GC/safepoint log. Xem `java -Xlog:help` trên đúng phiên bản JDK để xác nhận decorators, tags và quyền ghi file. Đừng thay đổi logging trên production chỉ để phục vụ ví dụ học tập; cần cân nhắc overhead và quy trình cấu hình.

Một dòng minh họa có thể được đọc thành “vào khoảng UTC 08:14:05.400, JVM instance X đạt uptime 905.400 s và xảy ra một GC event”. Nhãn event, duration, pause phase phải đọc từ **thông điệp GC thật**; không suy ra thời lượng pause chỉ từ timestamp của một dòng.

### 5.3. Java Flight Recorder (JFR)

JFR ghi các sự kiện có **start time, duration** và thuộc tính riêng (GC, allocation, lock, I/O...). File recording có mốc start/stop. Phần mềm xem JFR có thể hiển thị theo timezone người phân tích; ghi lại zone đang hiển thị và chuyển về `Instant` trước khi ghép với log khác.

Sự kiện JFR kéo dài là **một khoảng [start, end]**; `end = start + duration`, không ép về một điểm duy nhất. Nếu event bắt đầu lúc `08:14:05.300Z` và duration `120 ms` thì nó kết thúc `08:14:05.420Z`. Một GC tại `08:14:05.400Z` nằm trong khoảng đó, nhưng sự trùng thời gian chưa chứng minh GC gây ra toàn bộ latency. Xem loại event, thread, correlation ID, phase và dữ liệu định lượng.

Ví dụ xem metadata/tóm tắt và một loại event trong file đã thu thập:

```bash
jfr summary incident.jfr
jfr print --events jdk.GarbageCollection incident.jfr
```

Đọc output theo phiên bản JDK và công cụ hiển thị; khi cần so từng mili giây nên xuất thời gian tuyệt đối có zone rõ ràng, ghi thêm metadata của recording và kiểm tra giới hạn precision.

### 5.4. Thread dump và snapshot từ lệnh chẩn đoán

Một thread dump là **ảnh chụp trong quá trình lệnh chạy**, có thể mất thời gian thu thập. Không giả định timestamp hiển thị ở đầu file chính là thời điểm của mọi thread state trong file. Nếu dump không có timestamp tin cậy, kẹp nó giữa hai lần lấy UTC từ cùng host:

```bash
# Minh họa trên Linux, với PID ví dụ của đúng JVM.
date -u '+%Y-%m-%dT%H:%M:%S.%NZ'
jcmd 12345 Thread.print -l > thread-dump.txt
date -u '+%Y-%m-%dT%H:%M:%S.%NZ'
```

Bây giờ biết **cửa sổ thu thập** của dump thay vì gán một thời điểm chính xác giả tạo. Ghi PID, JVM start, host, timezone và nguyên nhân thu thập. Nếu có nhiều dump, chú ý thời gian thực hiện khác nhau; đừng so thời điểm file được upload lên storage với thời điểm dump được tạo.

### 5.5. Linux kernel, systemd journal và thời gian OS boot

- `journalctl -b -o short-iso-precise` hiển thị journal của một boot với timestamp dạng ISO có precision cao.
- `journalctl -b -o short-monotonic` hiển thị timestamp theo monotonic clock của boot đó.
- `journalctl --list-boots` giúp xác định boot instance khi có reboot.
- `/proc/uptime` thể hiện uptime hệ thống, **không phải thời gian JVM đã chạy**.
- `dmesg` có thể in timestamp tương đối từ boot; cách đổi sang giờ dân sự bằng tùy chọn của công cụ có thể sai khi đồng hồ hệ thống được chỉnh hoặc hệ thống suspend/resume.

Minh họa lệnh đọc-only trên máy Linux có systemd:

```bash
journalctl --list-boots
journalctl -b -o short-iso-precise
journalctl -b -o short-monotonic
cat /proc/uptime
```

Khi ghép mono time với wall clock, gắn **boot ID** và mốc UTC từ chính boot đó; hai dòng `[123.456]` ở hai boot khác nhau không có quan hệ so sánh trực tiếp. Nếu timezone hiển thị khác giữa máy và terminal, chỉ chuyển **biểu diễn** sang UTC chứ không sửa giá trị thời gian tại nguồn.

### 5.6. Container/Kubernetes

Lúc rà soát pod cần phân biệt thời điểm:

- Pod được tạo, scheduled, container bắt đầu, JVM bắt đầu, container restart, liveness/readiness event và lúc hệ thống thu log.
- Kubelet/CRI log có timestamp riêng; `kubectl logs --timestamps` có thể bổ sung timestamp từ container log stream. Timestamp do runtime gán không luôn trùng timestamp ứng dụng tự ghi trong payload.
- `kubectl logs --previous` (khi có) giúp xem log instance trước của container restart; dùng container ID và restart count để tách hai đời JVM.
- Giờ địa phương hiển thị bên trong container có thể khác timezone host dù chúng chia sẻ wall clock nền; sự khác biệt chuỗi hiển thị không nhất thiết là clock skew.

Một sự kiện OOMKilled hoặc restart từ Kubernetes Events là bằng chứng theo thời gian cần đối chiếu với pod/worker instance cụ thể, đồng thời lưu ý event có thể được ghi hay truyền đến control plane sau thời điểm tác động thực tế.

### 5.7. Prometheus và dashboard metrics

Prometheus lưu **timestamp cho mẫu metric** thường ở epoch seconds; mặc định timestamp phản ánh thời gian thu nhận/scrape hoặc thời gian do exporter cung cấp nếu phù hợp. Một mẫu CPU lúc `08:14:06` có thể đại diện giá trị tại thời điểm scrape; nó **không** có nghĩa mọi lần sử dụng CPU trong cửa sổ xảy ra đúng `08:14:06`.

- `timestamp(metric)` trong PromQL trả epoch seconds của mẫu được chọn.
- `rate(counter[5m])` biểu diễn tốc độ ước lượng trong một **cửa sổ**, không phải sự kiện xảy ra tại một điểm.
- Histogram p95/p99 trong dashboard là kết quả tổng hợp trên interval; phải biết step, query window, label filter và cách histogram được xây dựng.
- Grafana hoặc trình duyệt có thể hiển thị cùng timestamp thành giờ địa phương người xem; kiểm tra dashboard timezone trước khi báo cáo “lệch 7 giờ”.

Nếu dùng metric để đối chiếu JFR/GC, đặt **cửa sổ metric** cạnh **khoảng start–end của sự kiện**, không khẳng định những điểm dữ liệu khác ngữ nghĩa thời gian là đồng thời tuyệt đối.

### 5.8. Distributed tracing và telemetry liên node

OpenTelemetry span có start/end timestamp và trace/span ID. Log record có thể phân biệt **Timestamp** (khi sự kiện xảy ra) và **ObservedTimestamp** (khi được quan sát). Khi hai service chạy trên hai node có clock lệch, child span có thể nhìn như bắt đầu trước parent hoặc request “tới trước khi gửi” dù thứ tự nhân quả thực vẫn hợp lệ.

Để đối chiếu, ưu tiên trace ID, parent-child, request/response ID, giao thức và duration đo trong cùng process, đồng thời kiểm tra clock sync của các node. Không tự “sửa” bằng cách kéo một span vài trăm mili giây để biểu đồ đẹp hơn khi chưa xác định độ lệch thật.

## 6. Đồng bộ clock giữa các máy: NTP/PTP, drift, step và skew

Các máy có thể cùng dùng UTC nhưng **không cùng chỉ đúng một thời điểm**:

- **Clock offset/skew:** chênh lệch giữa đồng hồ nguồn và đồng hồ tham chiếu. Ví dụ máy A nhanh hơn giờ chuẩn 120 ms.
- **Clock drift:** độ lệch thay đổi dần theo thời gian do oscillator, VM, nhiệt độ hoặc phần cứng.
- **Slew:** dịch tốc độ đồng hồ dần dần để điều chỉnh thời gian.
- **Step:** nhảy đồng hồ tức thời, có thể khiến wall timestamp lùi hoặc nhảy tiến.
- **Suspend, migration, reboot:** có thể tạo khoảng trống và thay đổi hành vi các loại elapsed clock hoặc reset uptime.

NTP/chrony hoặc PTP giúp điều chỉnh clock; **không mặc định sai số = 0**. Thu trạng thái dịch vụ đồng bộ thời gian của **từng node**, offset ước lượng, nguồn tham chiếu, thời điểm kiểm tra và độ bất định. Lệnh như `timedatectl`, `chronyc tracking` có thể giúp khảo sát tùy OS và cách triển khai; đừng coi một lệnh chạy trên máy phân tích chứng minh tất cả node trong cluster đang đồng bộ tốt.

Nếu định nghĩa `offset = source_clock - reference_clock` thì:

```text
corrected_utc = source_reported_utc - estimated_offset
```

Máy chạy nhanh `+120 ms`: timestamp nguồn `08:14:05.370Z` được ước lượng là `08:14:05.250Z`. Phải ghi **dấu của offset** và uncertainty; sai dấu khiến độ lệch tăng gấp đôi. Nếu offset được đo cách sự cố nhiều giờ hoặc clock đã step sau đó, không dùng nó như hằng số tin cậy cho toàn khoảng điều tra.

Khi không có chứng cứ đồng bộ clock đủ tốt, có thể kết luận “hai hiện tượng ở gần nhau trong một cửa sổ” nhưng **không** kết luận thứ tự ở độ phân giải mili giây.

## 7. Ghép một timeline bằng quy trình có thể kiểm toán

### Bước 1 — Chọn câu hỏi và khung thời gian

Ví dụ: “Có phải GC pause trùng với 200 ms tăng latency khi checkout bị timeout?” Xác định cửa sổ sự cố UTC, service và instance, chứ không chỉ một ngày theo giờ địa phương.

### Bước 2 — Thu thập dữ liệu gốc cùng danh tính

Với mỗi nguồn, giữ nguyên raw timestamp và file gốc; ghi:

- `source_type`, `source_file`, `host/node`, `pod/container`, `pid`, `jvm_start_utc`, `boot_id` nếu áp dụng.
- `raw_time`, `raw_unit`, `clock_domain` (wall UTC, wall local, JVM uptime, OS uptime, elapsed clock, ingest).
- `time_zone` hoặc `offset`, thông tin DST nếu nguồn chỉ có local timestamp.
- `event_time`, `observed_time`, `collection_window` và timestamp tạo artifact nếu chúng khác nhau.
- `clock_offset_estimate`, `uncertainty`, phiên bản parser, giả định quy đổi và mọi chỗ thiếu dữ liệu.
- `trace_id`, `request_id`, `thread_id` hoặc `gc_id` để kết nối các sự kiện cùng ngữ cảnh.

Đây là metadata **phục vụ điều tra**, không nhất thiết nhồi mọi trường vào từng dòng log ứng dụng; có thể gắn ở mức nguồn/file/session.

### Bước 3 — Chuẩn hóa về một trục UTC

1. Timestamp có `Z` hoặc offset xác định: parse sang `Instant`.
2. Epoch seconds/ms/µs/ns: đổi bằng đơn vị **đã khai báo** và kiểm tra khoảng ngày hợp lý.
3. Timestamp local thiếu zone: truy xuất cấu hình zone tại thời điểm tạo, giải quyết DST nếu có; chưa đủ thì để “unresolved”.
4. JVM uptime: tìm mốc cùng JVM (tốt nhất event có cả UTC và uptime), kiểm tra JVM start và reset.
5. OS monotonic uptime: tìm mốc của cùng boot; kiểm tra boot ID.
6. Elapsed-only `nanoTime`: chỉ giữ duration trong cùng JVM; không ép số raw thành instant.
7. Log/snapshot lấy trong khoảng thời gian: giữ interval `[capture_start, capture_end]`.

Luôn giữ `original_timestamp` và `normalized_utc` ở hai trường khác nhau; không ghi đè dữ liệu gốc.

### Bước 4 — Gắn sai số trước khi sắp thứ tự

Có thể biểu diễn một sự kiện được ước lượng tại `t` với uncertainty `±e` thành khoảng `[t-e, t+e]`. Nếu hai khoảng chồng lên nhau, thứ tự thời gian giữa hai sự kiện **không chắc chắn** chỉ dựa trên clock.

Ví dụ:

- Node A ghi event tại `08:14:05.250Z ±40 ms` → khoảng `[.210, .290]`.
- Node B ghi event tại `08:14:05.280Z ±40 ms` → khoảng `[.240, .320]`.

Dù timestamp B lớn hơn A 30 ms, hai khoảng chồng lấp nên **không thể khẳng định A xảy ra trước B** ở mức tin cậy đã đặt. Nếu trace propagation chứng minh quan hệ gửi → nhận, đó là bằng chứng nhân quả bổ sung, độc lập với thứ tự hiển thị của wall clock.

### Bước 5 — Dựng timeline có duration, không chỉ điểm

Bảng timeline nên có ít nhất: `source`, `event`, `start_utc`, `end_utc` (nếu duration), `uncertainty`, `identity` và `evidence`. Lọc cùng request/instance, so khoảng GC/JFR/trace với khoảng tăng metric. Các metrics aggregate cần thể hiện **cửa sổ đo** (ví dụ 08:14:00–08:15:00), không giả vờ là điểm tại giữa cửa sổ.

### Bước 6 — Kiểm tra chéo và phản chứng

- Log GC có `utctime` và `uptimemillis` có phù hợp với JVM startup đã ghi không?
- JFR recording, log ứng dụng và JVM metrics có cùng process/container restart không?
- Offset giữa clocks có nhỏ hơn khoảng cách sự kiện mà bạn muốn kết luận không?
- Có clock step, DST switch, reboot hoặc replay/ingestion delay trong đoạn đó không?
- Sự kiện lấy từ sampling/aggregation có đủ resolution để khẳng định thứ tự không?
- Trace ID, GC ID, thread ID có khớp hay chỉ “gần nhau trên biểu đồ”?

Nếu một giả định bị bác bỏ, cập nhật mapping và dựng lại timeline; ghi rõ thay đổi. Tuyệt đối không lặng lẽ cộng một số giờ “cho có vẻ khớp” hoặc bỏ qua event không vừa giả thuyết.

## 8. Ví dụ ghép năm nguồn cho cùng khoảng sự cố

Đây là **dữ liệu giả lập để học cách quy đổi**, không phải output thật từ một JVM:

- Host boot: `2026-10-29T06:00:00Z`.
- JVM instance `checkout-1` start: `2026-10-29T07:59:00Z`.
- Giả sử clock nguồn đã được kiểm tra và chưa có sai lệch đáng kể; trong thực tế cần ghi uncertainty.

| Nguồn | Timestamp gốc hoặc interval gốc | UTC chuẩn hóa | Điều được biết |
| --- | --- | --- | --- |
| Application log | `2026-10-29T15:14:05.250+07:00` | `08:14:05.250Z` | Checkout ghi cảnh báo; request ID xác định |
| JFR event | `start=08:14:05.300Z`, `duration=120 ms` | `[08:14:05.300Z, 08:14:05.420Z]` | Một event kéo dài, có thể chồng với GC |
| OS journal | Boot uptime `8045.350 s` | `08:14:05.350Z` | Chỉ hợp lệ với đúng boot có mốc `06:00Z` |
| GC unified log | JVM uptime `905400 ms`, `utctime=08:14:05.400Z` | `08:14:05.400Z` | GC thuộc đúng JVM start `07:59Z` |
| Prometheus sample | Sample time `08:14:06.000Z` | `08:14:06.000Z` | Giá trị tại mốc sample/scrape, **không** xác nhận lúc sự kiện riêng lẻ |

Các số trong bảng nhất quán: `07:59:00 + 905.400 s = 08:14:05.400Z`; `06:00:00 + 8045.350 s = 08:14:05.350Z`. JFR interval bao phủ mốc GC; nhưng để nói **GC làm tăng latency** phải có event type/duration phù hợp, request trace cùng ID, GC pause, workload và số liệu phân biệt nguyên nhân khác.

**Không ghép theo hàng ngẫu nhiên hoặc thứ tự file xuất hiện.** Log aggregation có thể nhận chậm hơn; tệp có thể đảo thứ tự khi rotate; công cụ JFR có thể hiển thị giờ địa phương. Chỉ sort theo normalized time **sau** khi mapping và uncertainty đã được ghi nhận.

## 9. Chương trình Java 17+ chuẩn hóa timestamp và đối chiếu uptime

Ví dụ độc lập sau dùng các giá trị giả lập cố định để có output chính xác. Chương trình chuyển timestamp `+07:00` sang UTC, tính gap giữa application event và GC, chuyển GC uptime từ một JVM start đã biết thành UTC, rồi kiểm tra hai cách đọc có khớp nhau không.

Lưu đúng tên **`TimelineAlign.java`**:

```java
import java.time.Duration;
import java.time.Instant;
import java.time.OffsetDateTime;

public class TimelineAlign {
    public static void main(String[] args) {
        Instant app = OffsetDateTime.parse(
                "2026-10-29T15:14:05.250+07:00").toInstant();

        Instant gc = Instant.parse("2026-10-29T08:14:05.400Z");
        Instant jvmStart = Instant.parse("2026-10-29T07:59:00Z");
        long gcUptimeMs = 905_400L;

        Instant gcFromUptime = jvmStart.plusMillis(gcUptimeMs);

        System.out.println("app_utc=" + app);
        System.out.println("gc_utc=" + gc);
        System.out.println("app_epoch_ms=" + app.toEpochMilli());
        System.out.println("gap_ms=" + Duration.between(app, gc).toMillis());
        System.out.println("gc_from_jvm_uptime=" + gcFromUptime);
        System.out.println("verified=" + gcFromUptime.equals(gc));
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```bash
javac TimelineAlign.java
java TimelineAlign
```

Stdout **chính xác**:

```text
app_utc=2026-10-29T08:14:05.250Z
gc_utc=2026-10-29T08:14:05.400Z
app_epoch_ms=1793261645250
gap_ms=150
gc_from_jvm_uptime=2026-10-29T08:14:05.400Z
verified=true
```

Giải thích:

1. `OffsetDateTime.parse(...).toInstant()` áp dụng offset `+07:00` **chỉ một lần**, kết quả là `08:14:05.250Z`.
2. `Duration.between(app, gc).toMillis()` cho khoảng 150 ms từ app event đến mốc GC. Đây là **khoảng giữa hai timestamp giả lập**, không phải độ dài của GC.
3. `Instant.plusMillis(905_400)` thêm JVM uptime vào mốc JVM start **được giả định đã biết và thuộc đúng tiến trình**. Trên production, `getStartTime()` chỉ xấp xỉ, clock có thể lệch; việc ra `true` trong ví dụ không chứng minh phép quy đổi uptime luôn chính xác cho mọi nguồn.

### 9.1. Đo latency trong code thật bằng đồng hồ elapsed

Cho latency của một thao tác nội bộ, cách đo đúng thường là:

```java
long startedNs = System.nanoTime();
try {
    // Thực hiện công việc cần đo.
} finally {
    long elapsedNs = System.nanoTime() - startedNs;
    // Ghi elapsedNs cùng timestamp UTC và trace/request ID.
}
```

Đây là **đoạn mã minh họa đặt trong một method**, không phải chương trình độc lập. Đừng dùng `Instant.now()` hai lần rồi suy ra duration có độ ổn định tương đương monotonic clock khi hệ điều hành có thể step wall clock. Đồng thời, đừng log số `startedNs` thô như UNIX epoch nanoseconds. Để ghép với hệ thống khác, ghi `Instant.now()` ở thời điểm event và duration theo `nanoTime` dưới hai trường rõ ràng.

### 9.2. Định dạng timestamp tốt cho logs

Một bản ghi JSON lý tưởng cho sự cố phân tán có thể có cấu trúc:

```json
{
  "event_time": "2026-10-29T08:14:05.250Z",
  "observed_time": "2026-10-29T08:14:05.310Z",
  "service": "checkout",
  "instance": "checkout-1",
  "jvm_start_time": "2026-10-29T07:59:00Z",
  "trace_id": "example-trace-42",
  "duration_ms": 150,
  "timestamp_unit": "iso8601-utc"
}
```

Dữ liệu chỉ là ví dụ: `observed_time` có thể do collector đặt, không nhất thiết là ứng dụng. `duration_ms` chỉ có nghĩa khi tài liệu sự kiện nói rõ đo từ đâu đến đâu. Trường `trace_id` hỗ trợ ghép request mà không dựa duy nhất vào độ gần nhau của timestamp.

## 10. Những lỗi thường làm sai timeline

1. **Ghép chuỗi local trực tiếp với UTC:** `15:14+07:00` bị xem thành `15:14Z`, lệch đúng 7 giờ.
2. **Chuyển timezone hai lần:** đã parse offset nhưng lại trừ thêm 7 giờ trong pipeline.
3. **Nhầm UTC với clock đã đồng bộ:** tất cả nguồn in `Z` vẫn có thể lệch hàng trăm mili giây giữa node.
4. **Ghép JVM uptime với OS uptime:** cùng đơn vị ms nhưng gốc thời gian khác; tạo lỗi có thể hàng giờ.
5. **Dùng `nanoTime` như epoch nanoseconds:** số không có ý nghĩa UTC; nếu so hai JVM khác nhau càng sai.
6. **Nhầm epoch seconds, milliseconds, microseconds và nanoseconds:** dữ liệu rơi ra ngoài khoảng ngày hợp lý hoặc mất precision.
7. **Không tách những lần restart:** PID/pod name được tái dùng, làm uptime giảm về 0 mà pipeline lại cộng vào mốc cũ.
8. **Tin thời gian collector thay cho thời gian event:** network/buffer/replay tạo thứ tự giả.
9. **Chỉ so điểm, bỏ duration:** một GC pause, JFR event hay query window là khoảng thời gian; trùng khoảng chưa chứng minh nhân quả.
10. **Bỏ qua DST:** giờ địa phương trong giờ chuyển mùa có thể mơ hồ hoặc không tồn tại.
11. **Tin vào số thập phân quá mức:** hiển thị nano giây không có nghĩa clock/sync chính xác nano giây.
12. **Không lưu raw source:** sau khi normalize sai, không còn căn cứ để khôi phục.
13. **Bỏ qua clock step/reboot:** timeline đột ngột nhảy/lùi hoặc monotonic reset khiến phép nội suy trên toàn khoảng bị sai.
14. **Giả định mọi span theo thứ tự startTime:** clock skew giữa service có thể đảo thứ tự hiển thị; kiểm tra trace ID và quan hệ nhân quả.

## 11. Checklist trước khi tuyên bố hai sự kiện có liên quan

- [ ] Đã xác định mục tiêu cần so: **thời điểm**, **thời lượng**, **cửa sổ đo** hay **thứ tự nhân quả**?
- [ ] Mỗi timestamp đã được phân loại UTC/offset/local/epoch/JVM uptime/boot uptime/elapsed/ingest?
- [ ] Đã ghi timezone hoặc offset và đơn vị, xử lý khả năng DST nếu cần?
- [ ] Uptime được ghép với đúng JVM start/boot ID, PID/container instance và không qua restart?
- [ ] Giá trị `System.nanoTime` chỉ dùng cho duration trong một JVM?
- [ ] Đã kiểm tra clock skew, sync status, step/drift và uncertainty của các node liên quan?
- [ ] Đã bảo tồn raw timestamp, xác định timestamp của event và timestamp nhận dữ liệu?
- [ ] Với JFR/GC/trace/metric, đã biểu diễn duration hoặc aggregation window đúng ngữ nghĩa?
- [ ] Timeline có căn cứ để đối chiếu ít nhất hai loại bằng chứng (ID, stack/event type/metrics)?
- [ ] Kết luận có nói rõ phần **chắc chắn**, phần **ước lượng** và các giả định còn mở?

**Bài tập tự kiểm tra:** Node A nhanh `+120 ms` so với nguồn chuẩn, ghi request tại `08:14:05.370Z`; node B được đồng bộ tốt ghi GC tại `08:14:05.400Z`; GC uptime là `905400 ms`, JVM start `07:59:00Z`. Quy đổi request của A thành `08:14:05.250Z`, giữ GC tại `08:14:05.400Z`; khoảng cách timestamp ước tính là **150 ms**. Nếu offset của A chỉ biết trong khoảng `+120 ±40 ms`, thứ tự và độ chính xác kết luận phải xét thêm uncertainty, không tuyên bố chính xác đến mili giây. Đồng thời cần thêm evidence về GC pause và request để khẳng định nguyên nhân timeout.

## Tài liệu tham khảo

- Oracle, [Java SE 17 — `java` command và Unified JVM Logging](https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html): decorators `utctime`, `uptime`, `uptimemillis`, `timemillis`, `timenanos`, `-Xlog`.
- Oracle, [Java SE 17 — `System.currentTimeMillis()` và `System.nanoTime()`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/System.html): phân biệt wall clock và elapsed clock.
- Oracle, [Java SE 17 — `RuntimeMXBean`](https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/RuntimeMXBean.html): `getStartTime()` và `getUptime()`.
- Oracle, [Java SE 17 — `java.time`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/package-summary.html): `Instant`, `OffsetDateTime`, `LocalDateTime` và `ZonedDateTime`.
- Oracle, [Java SE 17 — JFR events](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.jfr/jdk/jfr/package-summary.html): event timestamp và duration.
- systemd, [`journalctl` manual](https://www.freedesktop.org/software/systemd/man/latest/journalctl.html): định dạng `short-iso-precise` và `short-monotonic`.
- Prometheus, [PromQL functions](https://prometheus.io/docs/prometheus/latest/querying/functions/): `time()`, `timestamp()` và cửa sổ metrics.
- OpenTelemetry, [Logs Data Model](https://opentelemetry.io/docs/specs/otel/logs/data-model/): `Timestamp` và `ObservedTimestamp`; [Tracing API](https://opentelemetry.io/docs/specs/otel/trace/api/): start/end timestamps, span duration.

Khi điều tra sự cố thực, hãy lưu **raw values + normalized UTC + clock origin + instance identity + uncertainty**. Một timeline chỉ có thứ tự timestamp đẹp mắt nhưng thiếu năm yếu tố này dễ tạo kết luận sai.