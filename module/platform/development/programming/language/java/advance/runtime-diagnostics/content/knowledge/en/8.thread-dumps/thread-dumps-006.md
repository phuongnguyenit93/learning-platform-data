# 8.6 Thu nhiều thread dump cách nhau một khoảng để xác định tiến triển

> **Java Advance – runtime-diagnostics** · **8. Thread dump**

## 1. Vì sao cần nhiều ảnh chụp thay vì chỉ một?

Một **thread dump** cho biết các Java threads đang ở đâu trên call stack, ở trạng thái nào, và — tùy công cụ/JVM — đang giữ hoặc đợi những khóa nào **tại thời điểm thu thập**. Nó rất có ích để đặt giả thuyết về request bị chặn, contention, deadlock hoặc thread pool không còn tiến triển. Nhưng một ảnh không cho biết thread đã chờ bao lâu, nó có vừa hoàn tất một task không, hay trạng thái đang thấy chỉ là trạng thái nghỉ bình thường.

**Thu nhiều thread dump cách nhau một khoảng** giúp so sánh các thời điểm để thấy **dấu hiệu tiến triển** (*progress*): thread đổi stack/state; lock owner thay đổi; request/task hoàn tất; queue giảm; counter tăng; hoặc ngược lại, nhiều workers vẫn cùng chờ một tài nguyên khi hệ thống không xử lý thêm công việc.

Điều quan trọng: **nhiều ảnh là bằng chứng theo thời điểm, không phải một bộ phim liên tục**. Kể cả cùng stack ở ba lần chụp, thread có thể rời stack ấy, hoàn thành công việc, rồi quay lại giữa các lần chụp. Ngược lại, thread liên tục đổi frame nhưng vẫn không hoàn thành một yêu cầu nào — đó có thể là *livelock*, retry loop hoặc thao tác vô ích.

### Mục tiêu học tập

Sau bài này bạn có thể:

1. Thiết kế một đợt lấy mẫu thread dump có **số ảnh, khoảng cách, thời gian ghi và giới hạn tác động** phù hợp triệu chứng.
2. Chụp các ảnh của **đúng JVM instance**, lưu danh tính process, UTC timestamp, lệnh, lỗi và đường file.
3. So sánh thread identity, state, stack signature, monitor/lock owner và sự xuất hiện/biến mất **đúng phạm vi**.
4. Phân biệt **tiến triển thực sự của nghiệp vụ** với “thấy một thread di chuyển”, “thấy cùng một stack” hoặc “state đổi”.
5. Kết hợp thread dumps với **completed-task/request counters, queue depth, traces, logs, OS CPU, JFR và GC logs** để tăng độ tin cậy.
6. Biết những điều **không thể** suy ra, kể cả từ nhiều dump rời rạc.
7. Thực hành một ví dụ Java 17+ chứng minh **hai snapshot cùng WAITING nhưng đã có task hoàn thành ở giữa**.
8. Viết kết luận incident theo cấu trúc **quan sát → giả thuyết → kiểm chứng → giới hạn**, không nhầm tương quan với nhân quả.

## 2. Ba lớp “tiến triển” cần phân biệt

Từ *progress* nghe đơn giản nhưng trong hệ Java có ít nhất ba lớp khác nhau.

| Lớp | Dấu hiệu | Vì sao thread dump riêng lẻ chưa đủ? |
| --- | --- | --- |
| **Thread-level** | Frame/state/owner thay đổi; thread thoát một đoạn chờ | Có thể chỉ là thread thức dậy rồi lại ngủ, hoặc quay lại cùng loop |
| **Task/request-level** | Một task hoàn tất, request có response, span kết thúc, queue giảm | Dump không tự có task ID, request ID hay completion counter |
| **Service-level** | Thông lượng tăng, backlog giảm, lỗi/latency phục hồi | Cần metrics theo thời gian và đúng instance/tải |

**Ví dụ:** một worker nằm ở *LinkedBlockingQueue.take()* trong hai ảnh cách nhau 5 giây. Đó có thể là:

- Worker **rảnh** trong cả khoảng vì không có task.
- Worker **đã xử lý một task** ở giữa hai ảnh rồi quay lại *take()*.
- Worker không nhận việc do producer/dispatcher trục trặc.
- Worker đang bị chặn ở queue sai vì cấu hình luồng dữ liệu sai.

Nếu chỉ đọc hai ảnh có cùng *WAITING* và cùng stack, **bốn khả năng vẫn còn mở**. Cần *submitted count, completed count, queue depth, application logs* hoặc trace để phân biệt.

Một cách diễn đạt kỹ thuật chính xác là:

> “Ở hai thời điểm lấy mẫu, thread X đều được quan sát đang chờ ở queue.take(). Chưa đủ dữ liệu để biết nó có xử lý task trong khoảng giữa hay không.”

Không nên viết:

> “Thread X đã stuck 5 giây vì hai dump cùng WAITING.”

## 3. Khi nào nên lấy nhiều mẫu?

Lấy nhiều dump hữu ích khi triệu chứng **kéo dài đủ lâu để quan sát**:

- HTTP requests đang đợi rất lâu nhưng process còn sống.
- Thread pool có backlog, throughput giảm, worker có vẻ không nhả.
- Nhiều threads tranh một monitor hoặc chờ một lock owner.
- CPU tăng dai dẳng, cần so stack và đối chiếu per-thread CPU.
- Service vẫn nhận request nhưng không hoàn thành công việc.
- Nghi *deadlock*, *livelock*, starvation hoặc repeated retry/park.
- Hệ thống chậm từng đợt, và có thể chủ động thu trong đúng cửa sổ.

**Khi không phù hợp:** sự cố chỉ dài 50 ms nhưng bạn bắt đầu chụp sau 30 giây; ảnh có thể hoàn toàn bình thường. Với sự kiện ngắn, JFR, trace, logging hoặc metrics/histogram đã bật trước khi sự cố thường hữu ích hơn.

### 3.1 Số mẫu và khoảng cách là quyết định vận hành

Một đợt thử phổ biến là **3–5 ảnh cách nhau vài giây**, chẳng hạn 3 ảnh cách khoảng **5 giây sau khi lệnh trước hoàn tất**, khi điều này phù hợp độ dài triệu chứng và chi phí thực tế. Đây chỉ là **ví dụ** — không có quy tắc JVM bắt buộc “lấy đúng ba dump cách nhau đúng năm giây”.

Chọn khoảng cách theo **giả thuyết**:

| Triệu chứng | Cửa sổ gợi ý | Lưu ý |
| --- | --- | --- |
| Thread pool treo hàng phút | Một số ảnh cách nhau vài giây | Đủ thấy dấu lặp, nhưng chưa đo được duration state chính xác |
| Lock contention chỉ vài trăm ms | Thread dump thủ công có thể bỏ lỡ | Ưu tiên JFR monitor contention/events và metrics |
| CPU cao duy trì vài chục giây | Nhiều ảnh có ghi thời điểm, cùng per-thread CPU delta | Dump chỉ gợi ý frames, không là CPU profiler |
| Sporadic timeout vài lần/giờ | Trigger có kiểm soát hoặc continuous event telemetry | Lấy mẫu ngẫu nhiên sau sự kiện thường không khớp |
| Rất nhiều threads/virtual threads | Giảm tần suất; chọn tool phù hợp | File lớn, overhead cao, coverage thay đổi |

**Khoảng chờ 5 giây sau khi dump trước xong không có nghĩa timestamps của hai ảnh cách nhau đúng 5 giây.** Nếu thu mỗi dump mất 1,2 giây, thời gian giữa *start* của ảnh 1 và ảnh 2 khoảng 6,2 giây. Phải ghi **capture start/end**; nếu cần tần suất đều, thiết kế scheduler có giám sát overhead, không khởi nhiều lần chụp song song vào một JVM.

### 3.2 Chọn trước điều kiện dừng

Để việc thu có kiểm soát, xác định:

- **Số mẫu tối đa** (ví dụ ba ảnh trong lượt đầu).
- **Tổng cửa sổ** điều tra và khoảng nghỉ.
- Ngưỡng tài nguyên/disk/log impact khiến cần ngừng.
- **Người chịu trách nhiệm** và nơi lưu file.
- **Dữ liệu bổ sung** phải lấy đồng thời (latency/queue/CPU/errors).
- Cách xử lý khi PID mất, attach failed, process restart.

Không tạo vòng *while true; jcmd Thread.print* trong production. Công cụ chẩn đoán cũng tiêu CPU/I/O, có thể thay đổi scheduling và ảnh hưởng chính triệu chứng cần đo.

## 4. Preflight: đảm bảo mọi ảnh thuộc **cùng JVM**

Một chuỗi nhiều file chỉ có thể so sánh có ý nghĩa nếu biết **mỗi file đo process nào**.

### 4.1 Những định danh nên lưu

- Service, application version, deployment/commit version.
- Host/container/pod và **pod UID** nếu ở Kubernetes.
- JVM process ID trong **namespace nơi công cụ chạy**.
- VM vendor/build/version, JVM start time hoặc uptime (để nhận diện restart).
- **Thời điểm UTC bắt đầu và kết thúc** mỗi lần chụp.
- Lệnh thu, tool/JDK version, options.
- Tên file, file size, **trạng thái thu thành công/thất bại**.
- Thông tin incident/tải tại thời điểm thu, nếu có.
- Coverage: platform threads hay virtual threads, có locks/ownable synchronizers không.

**PID không đủ.** Một process có thể restart và OS tái sử dụng PID. Hai JVM thuộc hai pod khác nhau có thể đều hiển thị PID 1 **bên trong container**. Một ObjectName hoặc thread name cũng không thay thế process identity.

Nếu giữa hai lần thu *JVM start time* thay đổi, đó là **hai JVM instances**. Không suy ra thread mới “đã tiến triển” chỉ vì tên thread giống tên trong JVM trước. Restart cũng reset các counter như GC count, process CPU time và nhiều thread IDs.

### 4.2 Điều kiện attach của jcmd

Với HotSpot, *jcmd* thường cần chạy **cùng máy** với JVM, có quyền OS phù hợp (trên Unix cùng effective user/group theo tài liệu), đúng PID namespace/attach mechanism và JDK tool hỗ trợ. Trong container, *jcmd -l* không luôn liệt kê JVM bên trong namespace Docker khác; kiểm tra PID bằng cơ chế process discovery có thẩm quyền trong môi trường đó.

Bắt đầu ở JVM đích:

~~~bash
java -version
jcmd -l
jcmd 12345 help Thread.print
~~~

*12345* là **PID ví dụ**, phải thay bằng PID JVM đã xác minh; không chạy vào PID bất kỳ. *jcmd -l* chỉ là gợi ý liệt kê, không chứng minh “không có JVM” nếu thiếu kết quả.

Nếu công cụ không attach được, **không** tùy tiện nâng quyền container, thay permission của thư mục hệ thống, mở JMX không bảo vệ hoặc vô hiệu cơ chế bảo mật chỉ để chụp. Tìm đường thu hợp lệ qua operator/platform team.

## 5. Thu ba dump bằng jcmd: quy trình có dấu thời gian

Trên HotSpot hỗ trợ, một lần thu platform-thread stack với ownable synchronizer information có thể dùng:

~~~bash
jcmd 12345 Thread.print -l
~~~

Tùy phiên bản còn có *-e* cho extended thread information. Xem **help từ JVM đích**, vì flags, output và virtual-thread coverage có thể khác giữa release:

~~~bash
jcmd 12345 help Thread.print
~~~

Tài liệu Oracle đánh giá *Thread.print* có **impact medium**, phụ thuộc số thread. Vì vậy ví dụ dưới **chỉ chụp tối đa ba lần**, không tự phát hiện rồi sửa lỗi hay tạo loop vô hạn.

### 5.1 Ví dụ Bash (Linux/macOS khi môi trường có jcmd)

Đây là script độc lập **minh họa**, chỉ thực thi ở môi trường được phép; thay PID và chọn thư mục lưu an toàn trước khi chạy:

~~~bash
#!/usr/bin/env bash
set -euo pipefail

PID=12345
OUT_DIR="./thread-dumps-$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -p -- "$OUT_DIR"

for i in 1 2 3; do
  started="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  file="$(printf '%s/thread-%02d.txt' "$OUT_DIR" "$i")"

  if jcmd "$PID" Thread.print -l > "$file"; then
    finished="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    printf 'sample=%s start=%s end=%s status=ok file=%s\n' \
      "$i" "$started" "$finished" "$file" >> "$OUT_DIR/manifest.txt"
  else
    finished="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    printf 'sample=%s start=%s end=%s status=failed file=%s\n' \
      "$i" "$started" "$finished" "$file" >> "$OUT_DIR/manifest.txt"
    exit 1
  fi

  if [ "$i" -lt 3 ]; then
    sleep 5
  fi
done
~~~

**Cách hiểu kết quả:**

- Có ba file, tên tăng theo sample index. *manifest.txt* ghi UTC **start/end** và kết quả mỗi lần. Có thể thêm instance ID, JVM start time và service version từ hệ quản trị ngoài script.
- *sleep 5* chạy **sau** khi lệnh lấy dump trả kết quả, không phải chính xác năm giây giữa mọi timestamp của ảnh.
- Redirect *>* ghi stdout của **jcmd client** vào file. Nó **không** yêu cầu JVM đích ghi file tới filesystem của process JVM.
- Nếu *jcmd* trả lỗi, script dừng. Một file rỗng/partial khi lỗi **không phải bằng chứng không có thread**.
- Nếu JVM restart, script có thể vẫn chạy vào PID mới/khác; **manifest phải được đối chiếu với process identity** trước khi diff.
- Thời gian ghi chỉ có độ phân giải **giây** trong ví dụ; khi cần độ chính xác hơn và OS hỗ trợ, dùng timestamp có fractional seconds. Không tuyên bố microsecond timing từ script này.
- Dòng lệnh có thể thất bại nếu chạy từ host/pod khác, JDK không có, hoặc quyền attach không đủ. Không dùng nó để phỏng đoán nguyên nhân deadlock.

### 5.2 Ví dụ PowerShell (Windows)

Trong PowerShell, **$PID** là biến tự động chỉ PID của PowerShell hiện tại. Đừng gán *$PID = 12345*; hãy dùng tên khác như *$targetPid*.

~~~powershell
$ErrorActionPreference = "Stop"
$targetPid = 12345
$out = Join-Path (Get-Location) (
    "thread-dumps-" + (Get-Date).ToUniversalTime().ToString("yyyyMMddTHHmmssZ")
)
New-Item -ItemType Directory -Path $out -ErrorAction Stop | Out-Null

for ($i = 1; $i -le 3; $i++) {
    $started = (Get-Date).ToUniversalTime().ToString("o")
    $file = Join-Path $out ("thread-{0:D2}.txt" -f $i)

    & jcmd.exe $targetPid Thread.print -l |
        Out-File -FilePath $file -Encoding UTF8 -Width 32767
    $exitCode = $LASTEXITCODE
    $finished = (Get-Date).ToUniversalTime().ToString("o")

    "sample=$i start=$started end=$finished exit=$exitCode file=$file" |
        Add-Content -Path (Join-Path $out "manifest.txt") -Encoding UTF8

    if ($exitCode -ne 0) {
        throw "jcmd failed for sample $i with exit code $exitCode"
    }
    if ($i -lt 3) {
        Start-Sleep -Seconds 5
    }
}
~~~

PowerShell *Out-File* có thể thêm BOM/re-encode text; bản thân file là **text diagnostic capture**, không được tuyên bố là byte-for-byte stream từ JVM nếu chưa kiểm tra encoding. Dùng encoding/collector thích hợp khi cần parser tự động. Redirect và lỗi stderr cũng cần kiểm tra riêng; một exit code 0 không thay thế việc xác minh file có đúng dump của JVM mong muốn.

### 5.3 Khi ảnh rất lớn

Mỗi dump có thể chiếm hàng megabyte hoặc hơn ở JVM nhiều threads. Đọc/ghi toàn bộ trong terminal, shipping qua collector hoặc copy file có thể gây overhead. Cần giới hạn số mẫu, dung lượng, quyền lưu, thời hạn giữ và tránh dán nguyên dữ liệu production vào công cụ công khai. Không lấy dump trong vòng lặp dày chỉ để cố bắt một lỗi ngắn; JFR/metrics có thể phù hợp hơn.

## 6. So sánh nhiều dump: ghép đúng thread trước khi diff

Một lỗi thường gặp là dùng *thread name* làm khóa duy nhất. Nhưng pool worker names có thể lặp sau restart, rename, hoặc nhiều threads có tên giống nhau. Một số dump ghi *tid*, *nid*, Java ID và stack frame; các ID này **không có cùng ý nghĩa**.

### 6.1 Thứ tự đối chiếu identity

1. **Cùng JVM instance:** process start time + host/pod UID + PID trong namespace của capture.
2. **Cùng thread trong instance đó:** Java thread ID nếu output cung cấp đúng, hoặc native ID *nid* khi biết chắc encoding/OS namespace; cần tính đến thread lifecycle/ID reuse.
3. **Thread name:** gợi ý vai trò, nhưng **không** dùng duy nhất để nối mẫu.
4. **Stack + pool metadata:** giúp phát hiện worker được tái tạo hoặc tên giống nhau nhưng code path khác.
5. **Application correlation:** requestId/taskId/traceId nếu có từ logs/tracing (không tự có trong thread dump).

Trong một số HotSpot *Thread.print*:
- *nid=0x...* là native thread ID theo biểu diễn của tool; cần chuyển hex/decimal và đối chiếu đúng OS thread khi dùng OS metrics.
- *tid=0x...* là định danh/địa chỉ nội bộ, không nên coi tự động bằng *Thread.getId()*.
- *#n* ở header không phải request number.
- JVM main PID khác từng native thread ID.

Không biến việc *Thread A không xuất hiện ở dump 2* thành “A đã hoàn tất thành công”. Nó có thể kết thúc do lỗi, bị thay mới, snapshot có coverage khác hoặc JVM đã restart.

### 6.2 Chỉ diff sau khi chuẩn hóa metadata và loại nhiễu

Giữa hai file thô, có nhiều thứ thay đổi mà **không phản ánh progress nghiệp vụ**:

- Timestamp và VM uptime trong header.
- Process/thread CPU time tích lũy.
- Counters, allocator addresses, JIT frame details.
- Thread name order trong file, lock object addresses nếu không cùng process.
- Các helper threads của GC/JIT, scheduler, logging collectors.
- Lúc capture, chính thread công cụ/diagnostics có thể xuất hiện.

**Không xóa tất cả các trường động.** Thông tin CPU delta, owner, native ID và timestamp có thể là bằng chứng quan trọng. Hãy giữ **bản gốc** và tạo bản trích xuất/normalized riêng có chú giải; xác định rõ trường nào bị lược bỏ. Không chỉ chạy *diff -u* hai file rồi lấy số dòng khác biệt làm chỉ số tiến triển.

## 7. Mô hình bảng so sánh mỗi lần chụp

Một bảng phân tích tốt không chỉ có state; nó còn có nơi chờ, owner, stack signature, counters và nhận định mức chắc chắn.

| UTC/sample | JVM/thread identity | State | Stack/điểm chờ | Lock/owner | Progress counter/metric | Kết luận mức ảnh |
| --- | --- | --- | --- | --- | --- | --- |
| 10:00:00 / A | JVM-1 / worker-7 | WAITING | queue.take | — | completed=100 | Đang chờ task lúc A |
| 10:00:06 / B | JVM-1 / worker-7 | WAITING | queue.take | — | completed=121 | Service có completion giữa A–B, **chưa chứng minh chính worker-7 làm** |
| 10:00:12 / C | JVM-1 / worker-7 | WAITING | queue.take | — | completed=140 | Đang chờ task lúc C; tổng service vẫn tiến triển |

**Lưu ý quan trọng:** nếu *completed* ở bảng là **service-wide counter**, nó không chứng minh **worker-7** xử lý 21 task. Nó chỉ chứng minh **service hoặc nhóm được counter bao phủ** có progress. Muốn nói worker-7 tiến triển, cần per-thread/per-task evidence, ví dụ counter riêng của worker trong lab, trace mapping hoặc log task completion đáng tin.

Với lock contention:

| Sample | Thread | State | Chờ | Owner | Diễn giải |
| --- | --- | --- | --- | --- | --- |
| A | request-12 | BLOCKED | monitor X | worker-3 | Đang tranh X ở A |
| B | request-12 | BLOCKED | monitor X | worker-3 | Lại thấy chờ X ở B |
| C | request-12 | RUNNABLE | method sau critical section | — | Có bằng chứng thread đã đổi vị trí/trạng thái ở C |

**Không nói “request-12 chờ X liên tục 10 giây” chỉ vì xuất hiện BLOCKED ở A và B.** Giữa hai ảnh thread có thể vào được lock rồi lại tranh nó. Muốn đo duration thực tế, ưu tiên JFR monitor enter events hoặc thống kê contention được bật có kiểm soát.

### 7.1 Stack signature là gì?

**Stack signature** là cách chuẩn hóa một số frame quan trọng — thường gồm top N frames, phương thức ứng dụng, vị trí chờ, loại lock/condition — để so nhiều mẫu. Ví dụ:

~~~text
request-12
  com.example.Inventory.reserve(...)
  com.example.Checkout.placeOrder(...)
  waiting monitor X; owner=worker-3
~~~

Mục tiêu là nhóm các thread **đang có cùng kiểu triệu chứng**, không phải chứng minh chúng đang làm cùng request. Tránh gộp mọi stack có *Unsafe.park* thành một nhóm duy nhất: *park* là primitive; phải xem những frame phía dưới như *LinkedBlockingQueue.take*, *CompletableFuture.get* hay *ReentrantLock.lock*.

### 7.2 Bảng progress bổ sung

Nên có một bảng thứ hai thể hiện dấu tiến triển **ngoài dump**:

| Thời điểm | Submitted tasks | Completed tasks | In-flight | Queue depth | Error rate | p99 latency |
| --- | --- | --- | --- | --- | --- | --- |
| A | 1.000 | 980 | 20 | 5 | 1% | 400 ms |
| B | 1.100 | 985 | 115 | 90 | 8% | 2.000 ms |
| C | 1.200 | 987 | 213 | 170 | 12% | 4.000 ms |

Số trên **chỉ là minh họa**, không phải dữ liệu production. Khi *submitted* tăng nhanh còn *completed* gần như đứng, *queue depth* tăng và request workers bị quan sát chờ cùng tài nguyên qua nhiều ảnh, giả thuyết thiếu tiến triển có **nhiều bằng chứng hơn**. Tuy nhiên counter phải cùng instance/group, không reset và có semantics đúng; khi autoscale/restart, không lấy hiệu raw của tổng toàn fleet một cách máy móc.

## 8. Các mẫu lặp cần hiểu khác nhau

### 8.1 Cùng WAITING + cùng queue, nhưng counter completion tăng

Đó có thể là một **worker khỏe**, liên tục lấy việc rồi trở lại chờ task. Nhiều ảnh ở *queue.take()* có thể chỉ vì phần lớn thời gian worker nằm chờ giữa các task ngắn.

**Kết luận:** không đủ bằng chứng thread bị kẹt. Cần per-worker progress nếu thực sự muốn đánh giá thread đó.

### 8.2 Cùng BLOCKED + cùng monitor + cùng owner trong nhiều ảnh

Đây là **dấu hiệu contention đáng ưu tiên**. Nhưng phải hỏi owner làm gì: giữ monitor rồi I/O lâu, đang ở một lock khác, hay bị OS scheduling trì hoãn? Cần lock owner stack và telemetry trong khoảng đó.

**Kết luận đúng:** “Ở các thời điểm được chụp, nhiều request threads cùng chờ monitor X do worker Y giữ.” Chưa biết **tổng thời lượng chờ liên tục** hoặc root cause nếu thiếu JFR/lock timing và request correlation.

### 8.3 Cùng WAITING ở Future.get hoặc CountDownLatch.await

Có thể là hợp lý khi chờ kết quả asynchronous task. Có thể là **starvation** nếu task cần thực thi được submit vào cùng thread pool đang bận chờ. Cần hiểu đồ thị phụ thuộc task, queue depth và executor completion; dump không tự biết future đó do tác vụ nào hoàn thành.

### 8.4 Cùng RUNNABLE với top frame tính toán qua nhiều mẫu

Có thể gợi ý CPU hotspot hoặc tight loop, nhưng **RUNNABLE không bằng CPU%**. Thread ở native I/O cũng có thể hiện RUNNABLE. Dùng **per-thread CPU delta** đúng native ID và JFR/profiler trong cùng cửa sổ; tránh kết luận “method đang ngốn CPU” từ hai stack frames.

### 8.5 Stack/lock thay đổi liên tục nhưng không có completion

Đó có thể là **livelock** hay retry loop. Thread đang “hoạt động” ở cấp CPU nhưng hệ thống không tiến triển nghiệp vụ. Cần business progress counter, retry count, errors, state transitions. **Thay đổi state là dấu hiệu thực thi**, không chắc là progress hữu ích.

### 8.6 Thread biến mất khỏi dump sau

Có thể do hoàn tất, exception, thread pool shrink, thread renamed, JVM restart, hoặc phạm vi công cụ khác. Cần application completion/event logs, lifecycle metadata và instance identity; đừng tự ghi “thread fixed”.

### 8.7 Pool rảnh nhưng backlog tăng

Một số workers ở WAITING tại *BlockingQueue.take()* trong khi queue depth ngoài dashboard tăng. Trước khi kết luận queue bị hỏng, xác nhận **đúng queue instance/endpoint**, cùng pod, cùng thời điểm và metrics semantics. Có thể producer ghi sang queue khác hoặc dashboard đo toàn fleet chứ dump đo một pod.

### 8.8 Deadlock detector không báo deadlock

Không thấy một **Java-level deadlock** trong dump không loại trừ starvation, database/distributed deadlock, livelock, socket wait hoặc deadlock ngoài phạm vi detector. Nhiều dumps càng không tự chứng minh phủ hết các cơ chế đồng bộ.

## 9. Lab Java 17+: cùng WAITING hai lần nhưng đã làm việc ở giữa

Bài thực hành dưới đây là **chương trình Java 17+ độc lập**, mô phỏng một thread nhận một task rồi quay lại chờ task tiếp theo. Main lấy **hai snapshot ThreadInfo** qua *ThreadMXBean*. Một thread thứ hai chỉ chờ một latch để đối chiếu.

Đây không phải là lệnh *jcmd* sinh ra file thread dump đầy đủ; nó dùng **cùng nền tảng quan sát Java management** để biểu diễn đúng lập luận “snapshot A/B có cùng state không chứng minh không có progress”.

Cách kiểm soát thử nghiệm:

1. *progress-worker* chờ *BlockingQueue.take()* ở một call-site.
2. *idle-worker* chờ *CountDownLatch.await()*.
3. Ở snapshot A, cả hai có state **WAITING**, completed=0.
4. Main đưa một task vào queue; worker lấy task, tăng counter và phát tín hiệu hoàn tất.
5. Worker quay lại **cùng câu lệnh take()** để chờ task thứ hai.
6. Ở snapshot B, cả hai lại **WAITING**, nhưng completed=1.
7. *finally* đánh thức/interrupt và join để tránh để thread lơ lửng.

Tạo file **RepeatedThreadDumpDemo.java**:

~~~java
import java.lang.management.ManagementFactory;
import java.lang.management.ThreadInfo;
import java.lang.management.ThreadMXBean;
import java.util.concurrent.BlockingQueue;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.LinkedBlockingQueue;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

public final class RepeatedThreadDumpDemo {
    private static final BlockingQueue<Integer> TASKS = new LinkedBlockingQueue<>();
    private static final CountDownLatch DONE_SIGNAL = new CountDownLatch(1);
    private static final CountDownLatch RELEASE_IDLE = new CountDownLatch(1);
    private static final AtomicInteger COMPLETED = new AtomicInteger();

    public static void main(String[] args) throws Exception {
        Thread worker = new Thread(() -> {
            try {
                for (int cycle = 0; cycle < 2; cycle++) {
                    TASKS.take(); // Cùng call-site trong cả hai lần chụp.
                    if (cycle == 0) {
                        COMPLETED.incrementAndGet();
                        DONE_SIGNAL.countDown();
                    }
                }
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        }, "progress-worker");

        Thread idle = new Thread(() -> {
            try {
                RELEASE_IDLE.await();
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        }, "idle-worker");

        try {
            worker.start();
            idle.start();
            awaitState(worker, Thread.State.WAITING);
            awaitState(idle, Thread.State.WAITING);

            ThreadMXBean mx = ManagementFactory.getThreadMXBean();
            printSample("A", mx, worker, idle);

            TASKS.put(1);
            if (!DONE_SIGNAL.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Worker did not finish task");
            }
            awaitState(worker, Thread.State.WAITING);
            printSample("B", mx, worker, idle);
        } finally {
            RELEASE_IDLE.countDown();
            worker.interrupt();
            worker.join(2_000);
            idle.join(2_000);
        }
    }

    private static void printSample(String label, ThreadMXBean mx,
                                    Thread worker, Thread idle) {
        long[] ids = {worker.getId(), idle.getId()};
        ThreadInfo[] infos = mx.getThreadInfo(ids, 8);
        if (infos[0] == null || infos[1] == null) {
            throw new IllegalStateException("Thread ended before snapshot");
        }
        System.out.println(label + ".workerState=" + infos[0].getThreadState());
        System.out.println(label + ".idleState=" + infos[1].getThreadState());
        System.out.println(label + ".completed=" + COMPLETED.get());
    }

    private static void awaitState(Thread thread, Thread.State desired)
            throws InterruptedException {
        for (int attempt = 0; attempt < 200; attempt++) {
            if (thread.getState() == desired) {
                return;
            }
            Thread.sleep(10);
        }
        throw new IllegalStateException("Expected " + desired
                + ", observed " + thread.getState());
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 RepeatedThreadDumpDemo.java
java RepeatedThreadDumpDemo
~~~

**Sáu dòng stdout của chương trình đã được kiểm thử trên JDK:**

~~~text
A.workerState=WAITING
A.idleState=WAITING
A.completed=0
B.workerState=WAITING
B.idleState=WAITING
B.completed=1
~~~

*javac* trên một số JDK mới có thể in **cảnh báo riêng** rằng *Thread.getId()* đã deprecated; đó không phải stdout của chương trình, và mã vẫn dùng API có sẵn trên Java 17. Bài lab sử dụng **platform threads**, không phải virtual threads. Việc đồng bộ bằng latch + kiểm tra trạng thái trong vòng lặp hữu hạn giảm rủi ro test phụ thuộc scheduler, nhưng hệ quá tải cực đoan vẫn có thể khiến *awaitState* hết thời gian và ném lỗi thay vì in sáu dòng.

### 9.1 Kết luận nào chắc chắn từ lab?

Tại A: progress-worker đang chờ task và completed=0. Sau A, main có bằng chứng bằng *DONE_SIGNAL* rằng worker đã xử lý một task và tăng chính counter của mình. Tại B, worker đã trở lại **WAITING ở cùng call-site take()**, nhưng counter=1.

Vì counter gắn với **chính worker**, đây là bằng chứng nó **đã tiến triển giữa hai lần chụp**. Không cần stack frame ở B khác A. Đây là phản ví dụ có chủ đích cho suy luận “hai stack/state giống nhau = thread không tiến triển”.

Ngược lại, *idle-worker* WAITING ở cả A và B vì đang chờ latch; nhưng **không thể kết luận lỗi** — main sẽ thả latch trong finally. Chờ đợi ổn định có thể là thiết kế đúng.

### 9.2 Cần kết hợp với app metrics thế nào?

Trong hệ thống thật, bạn ít khi có per-worker counter chuẩn như lab. Thay vào đó:

- **Service-wide completed counter tăng:** chứng minh một số tasks của service đã hoàn tất, không chứng minh worker X.
- **Queue depth giảm:** có thể do consumer xử lý, nhưng cũng có thể producer/policy xóa task; cần kết hợp completed/failed metrics.
- **Request spans kết thúc:** bằng chứng request-level progress nếu trace đầy đủ và sampling không bỏ sót.
- **Worker-specific log/context:** có thể chỉ ra task do worker X xử lý, nhưng kiểm tra thread reuse và correlation.
- **OS per-thread CPU delta:** có CPU activity, chưa tự chứng minh business progress.

Tách tầng identity và tầng progress trước khi đưa ra kết luận.

## 10. So ảnh trên một timeline thay vì chỉ đọc từng file

Một quy trình thuyết phục xây **timeline**:

~~~text
10:00:00  Incident: p99 latency tăng, completed/s giảm
10:00:02  Dump A: 20 request workers BLOCKED chờ monitor X
10:00:04  Metrics: queue length tăng; throughput gần 0
10:00:08  Dump B: nhiều worker vẫn chờ X, owner stack tại DB call
10:00:11  Traces: dependency DB wait tăng, cùng khoảng
10:00:14  Dump C: owner đi qua đoạn code khác; số worker BLOCKED giảm
10:00:16  Metrics: completed/s phục hồi
~~~

Mốc và dữ liệu trên là **tình huống giả định**. Kết luận phù hợp: lock X và owner có liên hệ thời gian đáng điều tra với sự cố; request workers quan sát chờ X ở A/B; metrics và trace cung cấp evidence tiến triển ở mức service. Chưa thể tuyên bố lock X **chắc chắn** là root cause nếu chưa có thông tin critical section, khả năng thay đổi tải, các nguyên nhân cạnh tranh và phép kiểm liên quan.

### 10.1 Một quy trình phân tích tám bước

1. **Định nghĩa triệu chứng và cửa sổ thời gian.** Chọn service, route, pod, error rate, latency, throughput, queue depth và thời điểm incident.
2. **Đóng khung mục tiêu chụp.** Process instance, VM version, PID namespace, quyền, công cụ và expected virtual-thread coverage.
3. **Chụp tối thiểu cần thiết.** Ví dụ ba ảnh với khoảng cách có chủ đích, timestamp đầu/cuối, hạn chế impact.
4. **Kiểm tra file hợp lệ.** Jcmd exit code, dữ liệu có header/stack/threads, cùng JVM; không phân tích file trống do attach failed.
5. **Ghép threads qua ảnh.** Đúng JVM/thread identity; phân loại pool, request workers, scheduler, GC/JIT/helper.
6. **Phân nhóm stack/lock signatures.** Chỗ chờ, lock owner/owner stack, liệu có cùng pool/queue/call path không; ghi state từng ảnh.
7. **Đối chiếu progress ngoài dump.** Completed counters, queue, request spans, JFR, CPU deltas, GC pauses; xem dữ liệu cùng instance và timestamp.
8. **Viết kết luận có mức chắc chắn, giới hạn và bước xác nhận tiếp.** Không biến một tương quan thành causal claim vô căn cứ.

Nếu sau bước 4 phát hiện JVM đã restart, **tách thành hai đợt**, không diff thread IDs như thể cùng process. Nếu sau bước 7 tiến triển service rõ ràng, điều chỉnh giả thuyết stuck dù stack/state của một nhóm threads trông lặp.

## 11. Những giới hạn ngay cả khi đã có 3, 5 hoặc 10 dump

### 11.1 Không đo chính xác thời gian chờ

Thấy thread X *BLOCKED* ở t0 và t10 **không** chứng minh X chờ liên tục 10 giây. Nó có thể nhả/giành lock nhiều lần giữa hai ảnh. Khoảng t0–t10 chỉ là **khoảng quan sát**, không phải phép đo dwell time. Cần JFR monitor events hoặc contention timing được hỗ trợ, bật có kiểm soát.

### 11.2 Không chứng minh thiếu tiến triển chỉ từ stack giống nhau

Một thread có thể quay lại cùng call-site mỗi lần nhận task. Lab đã chứng minh điều này. Kết luận “không progress” cần một **thước đo completion hoặc state transition nghiệp vụ** có thể quan sát theo thời gian, cùng đúng scope.

### 11.3 Không chứng minh CPU hotspot từ vài RUNNABLE stacks

Một thread RUNNABLE có thể chưa được OS schedule hoặc đang trong native call. CPU time là số đo tích lũy; muốn CPU load phải tính **delta theo cùng thread và cùng khoảng**. Đếm top-frame occurrences thủ công ở ba ảnh không tương đương statistically sampled CPU profiler.

### 11.4 Không tự có request latency distribution

Thread dump không cung cấp tất cả request durations để tính p95/p99. Cần metrics/tracing với sample/cửa sổ phù hợp, cùng business semantics. Một nhóm thread chờ 5 giây **không** có nghĩa p99 = 5 giây.

### 11.5 Không tự nhận diện mọi deadlock/livelock

Các detector trong JVM có phạm vi khóa nhất định. Chờ qua network, DB transactions, distributed locks, queues, futures, thread pool starvation hoặc vòng retry không tiến triển có thể không tạo Java-level monitor deadlock. Không thấy “Found deadlock” chưa đủ loại trừ các dạng này.

### 11.6 Không có bảo đảm snapshot nguyên tử trên mọi công cụ

Một lần dump có thể mất thời gian, output có thể không đại diện cho cùng một nano-giây. Các định dạng virtual-thread-specific của JDK mới có coverage và consistency khác. Nhiều dump không tự chữa vấn đề này; cần ghi tool/version/capture window.

### 11.7 Không nhất thiết thấy mọi virtual thread

Trên Java 21+, virtual threads được JVM quản lý, không ánh xạ 1:1 với OS native threads. Các công cụ/dạng dump truyền thống có thể chỉ bao phủ platform threads và một phần virtual threads đang mounted. *ThreadMXBean* trong Java Management API cũng có phạm vi khác với công cụ virtual-thread dump chuyên dụng.

Đối với JDK 21, tài liệu Oracle mô tả *Thread.dump_to_file* tạo file text/JSON chứa platform và virtual threads, nhưng không có toàn bộ object addresses/lock/JNI/heap metadata như dump truyền thống. Phải kiểm tra *jcmd PID help Thread.dump_to_file* trên **chính build JDK**; cú pháp/khả năng thay đổi theo version. Đừng so trực tiếp số lượng virtual threads giữa hai file **khác công cụ/coverage** rồi gọi đó là progress.

### 11.8 Không chứng minh một thread biến mất là thành công

Thread có thể kết thúc bởi uncaught exception, bị thread pool thay thế hoặc JVM restart; file mới không thấy thread không đủ xác định outcome. Hãy xem error/completion logs, task IDs, active/in-flight counters và lifecycle.

## 12. Virtual threads và phương pháp lấy nhiều mẫu trên JDK 21+

Ứng dụng dùng virtual threads cần thiết kế thu mẫu khác so với platform-thread pool truyền thống.

Trên Oracle JDK 21, ví dụ cú pháp tham khảo:

~~~bash
jcmd 12345 help Thread.dump_to_file
jcmd 12345 Thread.dump_to_file -format=json threads-01.json
~~~

*threads-01.json* là đường file do command tạo trong **filesystem của JVM đích**, có thể khác nơi terminal jcmd đang chạy. Tránh ghi đè file cũ; tên theo sample index/timestamp và quyền bảo vệ phải được thiết kế trước. Dạng JSON phù hợp cho parser và hỗ trợ quan sát virtual threads trong phiên bản này, nhưng không được giả định có deadlock detector hoặc tất cả lock internals.

**Khi so các virtual threads:**

- Ghi rõ dùng *Thread.dump_to_file* hay *Thread.print*, JDK version, content scope.
- Kiểm tra giá trị identity thực sự có trong format đó và tính ổn định qua mẫu.
- Không coi carrier OS thread là identity bền vững của virtual thread; virtual thread có thể mount/unmount.
- Dùng trace/task IDs, scheduler/queue metrics và JFR events để phân biệt “nhiều virtual threads WAITING” với thật sự không hoàn thành task.
- Tránh lấy dump toàn bộ hàng triệu virtual threads quá thường xuyên: file/processing overhead và bảo mật có thể đáng kể.
- Trên JDK khác 21, **đọc help của VM**, không chép mù *-format=json* hoặc tên command.

Nếu một chương trình dùng virtual threads và ba platform-thread dumps không cho thấy request workers, điều đó **không chứng minh requests không tồn tại**. Có thể bạn đã dùng công cụ có coverage không phù hợp.

## 13. Đối chiếu với CPU, GC, queue và ứng dụng để biết progress thật

### 13.1 OS thread CPU delta

Nếu dump ghi *nid* của native thread, có thể đối chiếu một metric per-thread CPU theo OS — sau khi xác minh **nid/PID namespace và quá trình không restart**. CPU delta dương cho biết thread đã tiêu CPU trong khoảng đo; không nhất thiết nó hoàn thành business task.

Để tránh sai đơn vị:

\[
\text{CPU cores trung bình} \approx \frac{\Delta \text{thread CPU seconds}}
{\Delta \text{wall seconds}}
\]

Một thread không thể chạy trên nhiều cores cùng thời điểm theo mô hình native thread thông thường; giá trị tính từ đúng một native thread thường quanh 0–1 core nếu dữ liệu hợp lệ. Process CPU delta có thể trên 1 core do nhiều threads. Không nhầm cumulative CPU seconds với CPU% tức thời.

**Bẫy:** *nid* hex từ HotSpot không thể so trực tiếp chuỗi với decimal TID trên công cụ OS; quy đổi đúng và gắn đúng host/namespace.

### 13.2 Queue metrics và thread pool metrics

Với ExecutorService/ThreadPoolExecutor, cần quan tâm:
- Active worker count.
- Queue depth.
- Submitted/completed task counts (đúng semantics của executor).
- Rejection count.
- Time in queue, execution duration nếu có instrumentation.
- Task error/timeout rate.
- Nested tasks phụ thuộc cùng pool.

Một pool có 100 workers WAITING và queue depth=0 có thể hoàn toàn khỏe. Ngược lại, pool active=100, queue depth tăng và completed/s≈0 trong nhiều mốc là dấu hiệu đáng điều tra; cần xem workers chờ gì và vì sao producer tiếp tục đẩy việc.

### 13.3 App logs/tracing

Trong một Java service, request có thể qua nhiều thread (async continuation, executor handoff, virtual threads). **Thread name không phải request identity**. Để liên kết dump với triệu chứng:
- Dùng traceId/requestId có bảo mật trong logs/spans.
- Ghi start/end task và dependency calls.
- Kiểm tra retry loops, timeouts, circuit breaker, queue waits.
- Tách thời gian thực của event khỏi timestamp do collector gắn.
- Kiểm tra sampling/truncation khiến một phần events mất đi.

### 13.4 GC logs và JFR

Trong giai đoạn GC pause/safepoint, việc thu dump có thể bị ảnh hưởng về thời điểm và cách JVM tạo snapshot. Nếu throughput đứng lại đồng thời GC pause kéo dài, GC Unified Logging và JFR có thể cung cấp sự kiện/duration tốt hơn thread dumps rời rạc.

JFR recording có các events liên quan monitor enter, thread park, execution sampling, CPU allocation/GC tùy JDK và cấu hình. Không đồng nhất “JFR có recording” với “mọi event hữu ích đã bật và thu được”; cấu hình và sampling window quyết định chất lượng bằng chứng.

## 14. Các tình huống chẩn đoán thực tế

### 14.1 HTTP thread pool có vẻ “đóng băng”

**Quan sát:**
- Dump A/B/C: phần lớn request workers đều WAITING tại *CompletableFuture.get()*.
- Metrics cùng pod: submitted tăng, completed hầu như không tăng, queue đang mở rộng.
- Logs: nhiều request đang chờ result của task được submit vào **chính pool có số workers đã chờ**.

**Giả thuyết mạnh:** thread pool starvation do nested blocking dependency. Chưa được kết luận chỉ từ dumps; các metrics và task dependency graph cung cấp phần bằng chứng quyết định. Cần xem executor topology, synchronous waits và có thực sự task nào có thể hoàn tất không.

**Không làm:** restart liên tục mà không lưu bằng chứng, hoặc nâng pool size mù quáng không hiểu nested dependency.

### 14.2 Nhiều threads cùng tranh monitor

**Quan sát:** 12 request workers BLOCKED tại *Inventory.reserve*, đều chờ monitor X trong hai ảnh. Owner Y có stack tại network call; throughput giảm.

**Giả thuyết:** một đoạn synchronized giữ monitor trong khi chờ downstream, gây lock convoy. Xác minh bằng code critical section, JFR monitor enter durations, trace downstream và một vài mẫu bổ sung nếu cần.

**Giới hạn:** không thể khẳng định từng worker bị BLOCKED liên tục giữa hai ảnh; owner có thể thay đổi ở thời điểm không chụp.

### 14.3 CPU 250%, stack RUNNABLE lặp tại JSON parser

**Quan sát:** một thread RUNNABLE tại JSON parser trong nhiều file; process CPU cao.

**Không được kết luận:** JSON parser chắc chắn chiếm 250% CPU. Một thread native thường không tự dùng 2,5 cores cùng lúc. Cần map native thread IDs, lấy CPU delta theo thread và execution samples qua JFR/profiler. Có thể các threads khác (GC/JIT/native) mới chiếm phần lớn CPU.

### 14.4 WAITING giống nhau nhưng request throughput vẫn tăng

**Quan sát:** ba dump cùng thấy worker-7 ở *LinkedBlockingQueue.take()*; completed request count cùng service tăng đều.

**Kết luận phù hợp:** service có tiến triển; chưa có bằng chứng worker-7 stuck. Nếu quan trọng phải biết worker-7 có hoàn thành task không, cần per-worker context hoặc traces; service-wide counter chỉ nói tiến triển cấp service.

### 14.5 Task retries liên tục, hoàn thành bằng 0

**Quan sát:** stacks đổi liên tục giữa retry/future/HTTP call, CPU có hoạt động, completed counter không tăng, error count cao.

**Giả thuyết:** livelock/retry amplification hoặc dependency failure. Cần request/task outcome, retry policy và dependency traces. Chỉ thấy thread chuyển state không là tiến triển nghiệp vụ.

### 14.6 Thread “biến mất” sau deploy restart

**Quan sát:** dump A trong pod X, dump B trong pod mới cùng tên logical workload; thread name *worker-1* xuất hiện ở cả hai nhưng PID/start time khác.

**Kết luận:** hai process instances; không thể diff identity/CPU/stack như một thread duy nhất. Tách incident thành trước/sau restart, xem shutdown/recovery logs và counters reset.

### 14.7 Virtual thread app có hàng nghìn requests WAITING

**Quan sát:** platform Thread.print có vài chục carrier/OS threads, nhưng app metrics nói hàng nghìn requests đang in-flight.

**Không kết luận:** JVM không có nhiều threads/request. Tool có thể không liệt kê virtual threads unmounted; cần virtual-thread-aware dump/JFR và task/request progress data. “Nhiều virtual threads WAITING” cũng có thể bình thường nếu chờ I/O; đo timeout/latency để đánh giá.

## 15. Sai lầm phổ biến khi thu và so nhiều dump

| Sai lầm | Vì sao sai | Cách sửa |
| --- | --- | --- |
| Hai ảnh cùng WAITING ⇒ thread stuck | Worker có thể xử lý việc giữa hai ảnh | Kèm completion/task counters |
| Cùng stack ⇒ thời gian ở frame bằng khoảng cách ảnh | Thread có thể rời rồi quay lại | Dùng timing/JFR, chỉ nói “quan sát tại hai mốc” |
| Frame thay đổi ⇒ request đã xử lý xong | Có thể retry loop/livelock | Kiểm tra business completion |
| Chỉ dùng thread name để ghép | Tên có thể lặp/tái sử dụng | Cùng JVM instance + thread identity |
| Giả định PID không bao giờ tái sử dụng | Restart/OS PID reuse có thể xảy ra | Ghi JVM start time/pod UID |
| Đếm dòng diff để đo progress | Timestamps/addresses/order thay đổi | Diff có ngữ nghĩa: state/stack/lock/counter |
| File dump thiếu thread ⇒ thread không tồn tại | Thread có thể kết thúc hoặc tool coverage khác | Kiểm tra lifecycle/format/virtual threads |
| Chụp cách “đúng 5s” chỉ vì sleep 5 | Dump có thời gian chạy riêng | Log start/end timestamps |
| Một dump fail nhưng file vẫn tồn tại ⇒ ảnh hợp lệ | Redirect có thể tạo file rỗng/partial | Kiểm tra exit code và nội dung |
| RUNNABLE lặp ⇒ CPU hotspot chắc chắn | Có thể native I/O hoặc OS wait | Per-thread CPU delta/JFR |
| GC pause không thấy ⇒ không liên quan GC | Thread dump không là GC event log | GC logging/JFR và timestamps |
| Không phát hiện deadlock ⇒ không starvation | Detector giới hạn loại lock/cycle | Queue/progress/dependency analysis |
| Toàn bộ WAITING ⇒ service chết | Workers có thể idle bình thường | Throughput, incoming load và queue metrics |
| completed counter tăng ⇒ thread X đã làm việc | Counter có thể toàn service | Per-thread/task correlation |
| Dùng file từ hai JVM chung một bảng | Khác process thì không cùng thread identity | Tách instance trước khi so |
| Mỗi ảnh là atomic snapshot | Tool/VM có thể lấy theo thời gian | Ghi capture window/coverage |
| Lấy 100 dump mỗi 100 ms | Overhead/I/O có thể làm sự cố nặng hơn | Giới hạn mẫu, dùng telemetry chuyên dụng |
| Public upload raw thread dumps | Dễ lộ class paths, internals, identifiers | Quyền truy cập, redaction và retention |

## 16. Bài tập có đáp án

### Bài 1 — Hai lần WAITING

A lúc 10:00:00 và B lúc 10:00:05: worker-1 đều WAITING ở *queue.take()*. Completed tasks của chính worker tăng 10 → 11.

**Hỏi:** Có tiến triển không?

**Đáp án:** Có bằng chứng **worker-1 đã hoàn thành ít nhất một task giữa hai mẫu**, dù trạng thái/stack tại hai mốc giống nhau. Không được gọi nó stuck chỉ từ hai ảnh.

### Bài 2 — Không có per-worker counter

Hai ảnh đều thấy worker-1 WAITING; total service completed tăng 300 → 350.

**Hỏi:** Có thể khẳng định worker-1 đã xử lý 50 requests không?

**Đáp án:** Không. Counter toàn service chỉ chứng minh service hoặc nhóm instance được đo có hoàn thành công việc. Muốn kết luận cho worker-1 cần task correlation cụ thể.

### Bài 3 — Hai lần BLOCKED

Thread A BLOCKED trên monitor X ở t0 và t10, cùng lock owner B.

**Hỏi:** A đã chờ liên tục 10 giây?

**Đáp án:** Chưa đủ. A có thể vào lock rồi quay lại chờ giữa hai ảnh. Chỉ biết A được quan sát BLOCKED ở cả hai mốc. Cần timing/monitor events để đo duration.

### Bài 4 — Thay đổi stack liên tục

Một thread chuyển qua *send → timeout → retry → send* trong nhiều mẫu, nhưng successful requests bằng 0.

**Hỏi:** Có progress không?

**Đáp án:** Có hoạt động ở cấp thread, **chưa có business progress**. Đây có thể là retry amplification/livelock; cần dependency traces/error metrics và retry budgets.

### Bài 5 — Tên thread giống nhau sau restart

Hai file đều có *pool-1-thread-1*, nhưng JVM start time của B sau A 2 phút.

**Hỏi:** Có được so hai thread như một thread duy nhất?

**Đáp án:** Không. Process instance khác; tên thread có thể được đặt lại. Cần tách timeline và nhìn shutdown/startup evidence.

### Bài 6 — Script sleep 5

Script chạy *jcmd Thread.print* mất 1,8 giây, rồi *sleep 5*.

**Hỏi:** Khoảng cách giữa bắt đầu hai lần thu có phải chính xác 5 giây?

**Đáp án:** Không. Khoảng cách khoảng 6,8 giây nếu không có overhead khác; cần timestamps thực tế để biết chính xác.

### Bài 7 — CPU quá cao

Process dùng trung bình 300% CPU; một thread RUNNABLE trên parser xuất hiện ở ba ảnh.

**Hỏi:** Có thể quy toàn bộ 300% cho thread đó không?

**Đáp án:** Không. Cần per-native-thread CPU deltas, mapping nid và profiler. Một thread có thể chỉ là một phần vấn đề.

### Bài 8 — Kết luận deadlock

Ba ảnh đều có nhiều threads WAITING ở Future.get, nhưng detector Java-level không thấy deadlock.

**Hỏi:** Có thể loại trừ starvation do task chờ nhau không?

**Đáp án:** Không. Future/task dependency không nhất thiết tạo monitor deadlock được detector tìm thấy. Cần executor graph và task progress metrics.

### Bài 9 — Dump có file rỗng

Lần chụp B có *thread-02.txt* dung lượng 0 byte, *jcmd* exit code 1.

**Hỏi:** Có thể nói “tại B không còn thread sống”?

**Đáp án:** Không. Đây là lỗi thu thập. Phải ghi status failed, xác minh attach/PID/quyền và không dùng B như một snapshot hợp lệ.

### Bài 10 — Virtual threads

JDK 21 service có 50.000 virtual threads đang chờ network; tool platform-thread dump chỉ thấy 80 platform threads.

**Hỏi:** Đã thấy toàn bộ requests chưa?

**Đáp án:** Chưa. Cần xác minh coverage và dùng virtual-thread-aware dump/JFR/traces. Đếm carrier threads không đại diện số virtual threads/task.

### Bài 11 — Queue tăng, workers chờ task

Metrics báo queue backlog tăng nhưng dump của một pod thấy workers WAITING ở queue.take().

**Hỏi:** Queue bị hỏng chắc chắn?

**Đáp án:** Chưa. Cần xác minh metric và dump thuộc **cùng pod/queue instance**, cùng thời điểm, executor topology; queue toàn fleet có thể khác local queue.

### Bài 12 — Owner thay đổi

A: thread W1 BLOCKED chờ monitor X do W2 giữ. B: W1 RUNNABLE, W2 không còn trong dump.

**Hỏi:** Chắc chắn W2 đã giải quyết xong mọi vấn đề?

**Đáp án:** Không. Có bằng chứng W1 không còn được quan sát BLOCKED tại B, nhưng chưa có W2 completion outcome hay business progress. W2 có thể kết thúc bình thường, thất bại hoặc biến mất do process/coverage khác.

### Bài 13 — Mức tin cậy

Bốn ảnh trong 20 giây liên tục quan sát 15 request workers BLOCKED tại cùng monitor X; queue tăng, completed/s gần bằng 0, JFR cho monitor wait durations tăng trong cùng khoảng.

**Hỏi:** Nêu kết luận phù hợp.

**Đáp án:** Có **bằng chứng mạnh** cho lock contention liên quan việc giảm tiến triển, nhất là khi JFR đo duration và metrics đồng bộ. Vẫn cần kiểm tra owner code path và quan hệ với requests để xác định root cause chính xác.

### Bài 14 — Thread biến mất

Một worker RUNNABLE ở A, không có ở B; metrics completed không tăng, error log có uncaught exception của worker.

**Hỏi:** Có thể gọi đây là “tiến triển thành công”?

**Đáp án:** Không. Lifecycle evidence gợi ý worker kết thúc do lỗi. “Không còn trong dump” không đồng nghĩa thành công.

## 17. Checklist vận hành và mẫu báo cáo

### 17.1 Trước khi chụp

- [ ] Xác định **triệu chứng cụ thể** và cửa sổ xảy ra.
- [ ] Xác minh đúng service, JVM instance, PID namespace, start time/pod UID.
- [ ] Kiểm tra tool/version và quyền attach; chạy *help* với command thực tế.
- [ ] Chọn số ảnh, khoảng cách và giới hạn tài nguyên/disk.
- [ ] Xác định nơi lưu file, quyền truy cập, TTL/retention.
- [ ] Chuẩn bị các metrics/logs/traces cần đối chiếu.

### 17.2 Trong khi chụp

- [ ] Ghi **UTC start/end**, tool, options, exit code và filename từng mẫu.
- [ ] Chụp theo thứ tự, không dồn dump đồng thời khi JVM đang yếu.
- [ ] Dừng khi attach lỗi, thay PID hoặc nguy cơ ảnh hưởng production.
- [ ] Không tự động bật diagnostic operations nặng nếu chưa được phê duyệt.
- [ ] Giữ raw files nguyên vẹn, hạn chế sharing và redaction khi cần.

### 17.3 Khi phân tích

- [ ] Xác minh các file cùng JVM instance và cùng tool coverage.
- [ ] Ghép thread identity; không dùng tên thread làm khóa duy nhất.
- [ ] So state + stack signature + locks/owners ở **từng thời điểm**.
- [ ] Đọc **completed/failed/in-flight/queue** metrics cùng instance/time.
- [ ] Nếu nghi CPU, đối chiếu per-thread CPU delta/JFR.
- [ ] Nếu nghi lock wait duration, đối chiếu JFR/contended monitor events.
- [ ] Nếu dùng virtual threads, kiểm tra coverage/format trước khi đếm.
- [ ] Đặt giả thuyết cạnh tranh và đánh dấu những điều **chưa chứng minh**.

### 17.4 Mẫu báo cáo incident

~~~text
Service/Version:
JVM identity: host/pod UID/PID/start time/JDK build
Symptom and affected window (UTC):
Capture method: tool/version/options/coverage
Samples: count, UTC start/end, file sizes, exit codes
Observed thread groups and stack signatures:
Repeated lock/owner or queue-wait evidence:
Evidence of progress: submitted/completed/failed/queue deltas
Other evidence: traces/app logs/GC/JFR/OS CPU
Hypotheses ranked by evidence:
What snapshots cannot establish:
Next safe validation:
Operational impact and data retention:
~~~

**Ví dụ kết luận đúng:**

> Trên JVM checkout-pod-7 (cùng PID/start time), ba lần thu lúc 10:00:02, 10:00:08 và 10:00:14 UTC ghi nhận 14–18 HTTP workers BLOCKED tại cùng monitor X, owner có stack trong đoạn gọi dependency. Trong khoảng tương ứng, completed requests tăng rất ít còn queue depth tiếp tục tăng. Đây là bằng chứng ủng hộ giả thuyết lock contention cản trở tiến triển. Chưa đo được thời gian chờ liên tục của từng thread; cần kiểm tra JFR monitor-enter durations và trace calls của owner trước khi kết luận nguyên nhân gốc.

**Ví dụ kết luận sai:**

> Vì ba dump có thread WAITING nên tất cả requests bị deadlock 12 giây; restart là giải pháp duy nhất.

Không có bằng chứng tự thân cho *deadlock*, *12 giây liên tục*, *tất cả requests* hay *giải pháp duy nhất* chỉ từ ba snapshot.

## 18. Tài liệu chính thức để tra đúng JVM đang dùng

- **Oracle JDK 21 – jcmd**, *Thread.print* impact/options và các diagnostic commands: https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html
- **Oracle JDK 21 – Diagnostic Tools**, cách lấy thread dumps và hiểu tác động công cụ: https://docs.oracle.com/en/java/javase/21/troubleshoot/diagnostic-tools.html
- **Java SE 17 – ThreadMXBean**, *getThreadInfo*, *dumpAllThreads*, deadlock/monitor support: https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/ThreadMXBean.html
- **Java SE 17 – ThreadInfo**, stack/state/lock owner và semantics snapshot: https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/ThreadInfo.html
- **Java SE 17 – Thread.State**, sáu trạng thái Java thread: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Thread.State.html
- **Oracle JDK 21 – Virtual Threads**, thread dumps cho virtual-thread applications: https://docs.oracle.com/en/java/javase/21/core/virtual-threads.html

Cú pháp, hỗ trợ virtual threads, output fields, cách attach và độ nhất quán của thread dump **thay đổi giữa JDK/VM/tool**. Luôn kiểm tra command *help* và tài liệu **đúng version** của process đang chẩn đoán.

## Kết luận

**Nhiều thread dumps giúp so ảnh theo thời gian, nhưng không tự biến snapshot thành lịch sử liên tục.** Hai lần cùng *WAITING* hoặc cùng stack không chứng minh thread stuck; một worker có thể hoàn thành task rồi quay lại cùng chỗ chờ. Ngược lại, stack đổi liên tục không chứng minh nghiệp vụ đã tiến triển.

Cách làm đúng là **chọn số mẫu/khoảng cách hợp lý → ghi đầy đủ identity/timestamps/status → ghép đúng threads → so state, stack, locks và owners → đối chiếu counters, traces, CPU/JFR/GC → kết luận đúng mức bằng chứng**. Không suy duration hay root cause từ khoảng cách giữa những ảnh rời rạc.