# Thu gom nối tiếp, song song và đồng thời với ứng dụng

## 1. Trọng tâm: “serial”, “parallel” và “concurrent” không cùng một trục

Khi nghiên cứu **garbage collection (GC)** trong JVM, ba thuật ngữ thường xuất hiện là:

- **Serial (thu gom nối tiếp):** một luồng GC thực hiện công việc thu gom chính của pha đang xét.
- **Parallel (thu gom song song):** nhiều luồng GC cùng thực hiện công việc trong một pha để tăng tốc xử lý.
- **Concurrent with the application (thu gom đồng thời với ứng dụng):** một hoặc nhiều luồng GC thực hiện **một phần công việc trong lúc các luồng ứng dụng vẫn chạy**.

Hai từ **parallel** và **concurrent** rất dễ bị dịch/hiểu lẫn. Trong ngữ cảnh GC, câu hỏi quyết định là:

1. **Có bao nhiêu GC workers cùng thực hiện một pha?** → trục **serial ↔ parallel**.
2. **Trong lúc pha GC chạy, các application threads (mutators) có bị dừng hay vẫn tiếp tục hoạt động?** → trục **stop-the-world (STW) ↔ concurrent**.

Một collector hoàn toàn có thể **parallel trong những STW pauses** và **concurrent ở những pha khác**. Ví dụ HotSpot **G1** sử dụng các GC workers **song song** khi evacuate regions trong STW pause, nhưng còn có **concurrent marking** diễn ra đồng thời với mutators.

### 1.1. Mô hình hai trục

```text
                        ỨNG DỤNG
                       bị dừng?              còn chạy?
                  +--------------------+--------------------+
1 GC worker       | Serial STW         | Serial concurrent  |
                  | VD: Serial GC      | (pha GC một worker |
                  |                    | chạy với mutator)  |
                  +--------------------+--------------------+
N GC workers      | Parallel STW       | Parallel concurrent|
                  | VD: Parallel GC,   | VD: concurrent     |
                  | G1 evacuation      | marking nhiều GC   |
                  |                    | workers, tùy VM    |
                  +--------------------+--------------------+
```

Các ô trên là **khái niệm về pha thực thi**, không phải danh sách cứng “mỗi collector chỉ nằm trong một ô”. Một collector có thể đi qua **nhiều ô trong một chu kỳ GC**.

**Điểm nhớ quan trọng nhất:** *Parallel GC không nhất thiết là concurrent với ứng dụng*. Trong HotSpot, collector tên **Parallel GC** chủ yếu dùng **nhiều GC threads cho các pha STW**, nghĩa là ứng dụng vẫn có thể bị dừng trong lúc các GC workers chạy song song.

## 2. Vì sao ứng dụng đang chạy làm GC phức tạp?

Ứng dụng Java tạo object, cập nhật reference fields, thay đổi dữ liệu trong collections, và có thể giữ các object còn sống theo những đường tham chiếu mới. Những thread thực thi code ứng dụng thường được gọi là **mutator threads**, vì chúng **làm thay đổi đồ thị object references** trong heap.

GC muốn xác định object nào còn reachable và thu hồi vùng bộ nhớ không còn cần thiết.

```text
GC quan sát đồ thị:                  Mutator có thể thay đổi:
Root -> A -> B                      Root -> A -> B
         \                               \
          C                               D (mới)
```

Nếu GC đánh dấu những object reachable trong lúc mutators vẫn thay đổi các cạnh tham chiếu, collector cần **giao thức nhất quán/đồng bộ thích hợp** để không nhầm một object còn cần thành rác.

Hai cách tổ chức lớn:

- **Dừng mutators trong một pha:** đồ thị ứng dụng không tiếp tục bị những threads ấy cập nhật theo cách thường thấy trong pha này; GC có thể thực hiện nhiều thao tác với một trạng thái ổn định hơn.
- **Cho mutators tiếp tục chạy:** collector phải theo dõi/sửa lại những thay đổi đáng kể, sử dụng **write/read/load barriers**, snapshots, remembered sets, forwarding/colored-pointer metadata hoặc cơ chế khác tùy collector.

**Concurrent collection không có nghĩa không còn phối hợp.** Nó làm tăng yêu cầu về correctness, đồng bộ, CPU time và các barriers. Nó cũng có thể vẫn có các **STW pauses ngắn** để xử lý những điểm nhạy cảm của thuật toán.

## 3. Stop-the-world (STW) là gì?

**STW pause** là khoảng thời gian JVM **tạm dừng các luồng ứng dụng thuộc phạm vi dừng đó** để runtime thực hiện một số công việc phối hợp, như những pha của garbage collection. Các GC worker threads có thể vẫn chạy trong pause.

Sơ đồ trục thời gian:

```text
Thời gian ---------------------------------------------->

Application:  RUNNING █████ | STOPPED .... | █████ RUNNING
GC worker 1:          idle | work work ... | idle
GC worker 2:          idle | work work ... | idle
                          ^ STW pause ^
```

Trong STW, **GC có thể là parallel** nếu có nhiều workers, nhưng **application không đồng thời chạy cùng các GC workers cho pha STW ấy**.

### 3.1. Pause time khác tổng thời gian GC

- **Pause time:** thời gian chương trình bị ngừng tiến triển vì một pause GC cụ thể, theo cách JVM ghi nhận.
- **GC work time:** tổng thời gian GC workers làm việc; nếu nhiều workers làm song song, **tổng CPU time** không bằng đúng wall-clock pause time.
- **Concurrent phase time:** thời gian trôi qua khi GC thực hiện công việc cùng lúc với ứng dụng.
- **Application latency:** thời gian request/task hoàn tất từ góc nhìn người dùng; có thể chịu ảnh hưởng GC pause **lẫn CPU contention** trong concurrent phases.
- **Throughput:** tỷ lệ công việc hữu ích mà hệ thống hoàn thành trong một khoảng thời gian.

**Không dùng “một GC cycle dài 500 ms” làm bằng chứng request bị pause 500 ms** nếu phần lớn cycle chạy concurrently. Ngược lại, không chỉ nhìn “STW pause 2 ms” rồi kết luận GC không ảnh hưởng latency: concurrent worker competition, allocation stalls và barriers cũng có thể tăng thời gian xử lý.

### 3.2. STW không đồng nghĩa toàn bộ các nguyên nhân dừng ứng dụng

Application latency còn bị ảnh hưởng bởi OS scheduling, I/O, locks, JIT compilation, safepoint operations, CPU throttling và memory pressure. GC logs là **một phần** để điều tra latency, không là bằng chứng duy nhất.

### 3.3. Safepoints và handshakes

HotSpot dùng **safepoint/handshake machinery** cho những hoạt động cần phối hợp thread states ở mức VM. GC pauses có thể cần đưa mutators vào trạng thái an toàn để quan sát/update references.

Không nên giảng rằng mỗi STW luôn đơn giản là “gửi signal đóng băng mọi OS threads cùng một instruction”: cách triển khai có thể phối hợp tại safepoints, sử dụng thread-local handshakes hoặc các cơ chế khác.

## 4. Thu gom nối tiếp (serial): ít GC workers, ít overhead phối hợp

**Serial collector** trong HotSpot dùng **một luồng** để thực hiện công việc GC theo thiết kế. Trong Java 17, bật collector này bằng:

```bash
java -XX:+UseSerialGC -jar application.jar
```

`application.jar` là **placeholder cho JAR có Main-Class hợp lệ**. Đây là minh họa cấu hình; bài thực hành riêng ở phần sau có tệp Java chạy được.

### 4.1. Hoạt động theo mô hình khái quát

```text
Application   ██████████ |       STOP       | ███████████
GC Worker 1   ---------- | MARK/COPY/SWEEP   | -----------
GC Worker 2   (không có worker thứ hai cho công việc thu gom chính)
```

Tùy thế hệ/pha, Serial collector có thể sử dụng kỹ thuật **copying**, **mark-sweep-compact** và các bước riêng. Điểm bản chất của từ “serial” là **độ song song của GC work**, không phải “JVM có duy nhất một application thread”.

### 4.2. Ưu điểm

- Ít overhead phối hợp giữa GC workers.
- Phù hợp với heap nhỏ, số CPU hạn chế hoặc ứng dụng có workload đơn giản.
- Dễ hình dung quan hệ “mutators dừng → một worker thu gom → mutators tiếp tục”.
- Trong một số workload nhỏ, chi phí tổ chức nhiều worker có thể lớn hơn lợi ích của parallelism.

### 4.3. Hạn chế

- Trên heap/live set lớn, một GC worker có thể không tận dụng nhiều CPU cores.
- STW pause có thể dài nếu lượng công việc thu gom lớn.
- Nếu SLA có yêu cầu latency chặt, Serial có thể không phù hợp.

**Không kết luận Serial luôn chậm nhất cho mọi workload.** Với lượng dữ liệu nhỏ, CPU quota thấp, hoặc overhead parallel setup đáng kể, một worker có thể đủ và đôi khi hiệu quả hơn.

## 5. Thu gom song song (parallel): chia việc cho nhiều GC workers

**Parallel collector**, còn được gọi là **throughput collector**, sử dụng nhiều GC workers để xử lý những pha thu gom của nó. Trong HotSpot JDK 17:

```bash
java -XX:+UseParallelGC -jar application.jar
```

Với các tác vụ phù hợp, tổng công việc GC được chia cho nhiều worker cùng tiến hành.

```text
Application   ██████████ |         STOP          | ███████████
GC worker 1   ---------- | MARK/COPY PARTITION 1 | -----------
GC worker 2   ---------- | MARK/COPY PARTITION 2 | -----------
GC worker 3   ---------- | MARK/COPY PARTITION 3 | -----------
GC worker 4   ---------- | MARK/COPY PARTITION 4 | -----------
```

**Cực kỳ quan trọng:** mặc dù **GC workers chạy parallel**, ứng dụng vẫn đang trong **STW pause**. Tên “Parallel GC” không có nghĩa GC song song với ứng dụng.

### 5.1. Tại sao parallel có thể rút ngắn pause?

Nếu có lượng công việc GC là `W` và có `P` workers, trực giác lý tưởng có thể là “mỗi worker xử lý khoảng `W/P`”. Tuy nhiên, thời gian thực tế có overhead:

- Phân chia công việc.
- Đồng bộ, barriers giữa GC workers.
- Work stealing hoặc mất cân bằng tải.
- CPU scheduling và quota trong container.
- Tranh chấp memory bandwidth, cache và NUMA effects.
- Những pha không thể song song hóa hoàn toàn.

Vì vậy **không có bảo đảm tăng gấp bốn workers thì pause giảm bốn lần**.

### 5.2. Throughput vs pause time

Parallel GC thường là lựa chọn được cân nhắc khi hệ thống cần **throughput cao** và có thể chấp nhận STW pauses dài hơn những ứng dụng low-latency.

Ví dụ một batch job xử lý dữ liệu lớn có thể ưu tiên tổng số records/second hơn p99 request latency, nên throughput GC đáng thử. Nhưng nếu đó là interactive service có SLA p99 rất thấp, nên đo thêm các collector có concurrent phases.

### 5.3. Khi parallel workers quá nhiều

Nếu JVM chạy trong container chỉ được cấp ít CPU quota, việc tạo nhiều GC workers có thể tạo overhead mà không có lượng CPU thực để dùng. Ergonomics của HotSpot thường tính toán workers từ CPU khả dụng, nhưng cần kiểm tra giá trị thực tế, đặc biệt khi thay đổi container/cgroup configuration.

Không giả định host có 64 cores là JVM container sẽ được dùng cả 64 cores.

## 6. Thu gom đồng thời (concurrent): mutator vẫn hoạt động trong một phần chu kỳ

Một **concurrent phase** của collector chạy khi **application threads vẫn có thể tiếp tục làm việc**. Nghĩa là GC và application chia sẻ CPU/memory bandwidth, phối hợp để truy vết/reference update theo mô hình của collector.

```text
Thời gian ---------------------------------------------------->

Application   ███████████ | pause | █████████████ | pause | ███
GC worker(s)  ----------- | init  | CONCURRENT   | final | ---
                                     ^
                          Mutators cũng đang RUNNING
```

Đây là mô hình **một chu kỳ có thể kết hợp pauses ngắn và concurrent work**, không phải timeline bắt buộc của mọi collector.

### 6.1. Concurrent không đồng nghĩa parallel worker count > 1

Một GC worker có thể làm việc **đồng thời với một application thread** nếu hai bên được hệ điều hành luân phiên hay chạy trên cores khác nhau. Ngược lại, nhiều GC workers có thể chạy song song nhau trong STW mà **không concurrent với mutators**.

Để trả lời câu hỏi “GC này là parallel hay concurrent?”, hãy hỏi **đang nói tới collector hay pha nào**, và xác định ai bị dừng trong khoảng thời gian đó.

### 6.2. Lợi ích

- Chuyển phần công việc GC ra khỏi những khoảng dừng ứng dụng.
- Có tiềm năng giảm **thời gian STW** và cải thiện tail latency.
- Có thể giảm sự phụ thuộc của độ dài pause vào kích thước heap/live set đối với những collector nhất định.
- Phù hợp với các ứng dụng yêu cầu latency thấp.

### 6.3. Chi phí

- GC và application cạnh tranh CPU/memory bandwidth.
- Write/load barriers và GC bookkeeping có overhead.
- Cần heap headroom để mutators tiếp tục allocate trong lúc GC cycle chưa xong.
- Nếu tốc độ cấp phát vượt tốc độ collector thu hồi, có thể xảy ra **allocation stall**, fallback hoặc OOME tùy collector và tình huống.
- Implementation phức tạp hơn, cần cơ chế duy trì tính đúng khi object graph thay đổi.

**Không có collector nào tạo “GC miễn phí” hoặc bảo đảm zero-pause tuyệt đối chỉ nhờ concurrent.**

## 7. Các cơ chế đồng bộ để concurrent collector vẫn đúng

Một bài GC cần trả lời: nếu mutator liên tục cập nhật reference trong lúc GC mark, làm sao không thu hồi nhầm object?

### 7.1. Marking, write barriers và snapshots

Giả sử GC đã quét object `A` rồi mutator đổi `A.child` từ `B` sang `C`. Một thuật toán concurrent mark cần xử lý thay đổi này theo cách bảo toàn các invariants của nó.

Các họ kỹ thuật gồm:

- **Snapshot-at-the-beginning (SATB):** ghi nhận một góc nhìn snapshot logic tại thời điểm bắt đầu marking, với các cơ chế barrier để theo dõi những reference có thể bị loại khỏi đồ thị.
- **Incremental-update marking:** theo dõi/thích ứng những cạnh mới làm thay đổi đồ thị đang mark.
- **Load/read barriers:** kiểm tra/điều chỉnh references khi ứng dụng đọc, quan trọng trong một số collector có concurrent relocation.
- **Remembered sets/card tables:** theo dõi vùng heap/nhóm generations liên quan, tránh phải quét toàn bộ heap cho mỗi GC nhỏ.

**Không có một barrier protocol duy nhất áp dụng cho mọi collector**. Ví dụ G1 trong các cấu hình được mô tả bởi tài liệu Oracle sử dụng **SATB concurrent marking** và cơ chế remembered sets; ZGC/Shenandoah dùng các kỹ thuật riêng cho marking/relocation.

### 7.2. Tại sao remark vẫn cần dừng?

Sau một concurrent marking phase, collector có thể cần chốt những dữ liệu được tích lũy và trạng thái liveness nhất quán. Với G1, **Remark** là một **STW pause**, xử lý phần còn lại của concurrent marking theo thuật toán.

Do đó:

```text
G1 concurrent mark ≠ “G1 không còn STW”
```

Một collector được mô tả là **mostly concurrent** vẫn có thể cần các stop-the-world phases khác.

### 7.3. Mutation rate ảnh hưởng concurrent GC

Nếu ứng dụng có rate cập nhật references và allocation rất cao, lượng GC bookkeeping và marking cần thực hiện có thể tăng. Một collector có concurrent marking không thể bỏ qua mọi object mutations.

Khi benchmark, ngoài heap size, cần đo **allocation rate, live-set size, mutation rate và CPU capacity**. Hai ứng dụng dùng cùng `-Xmx` có thể có GC behavior rất khác nhau.

## 8. Phân loại theo pha thay vì gắn một nhãn cho toàn collector

| Collector/pha trong HotSpot | GC workers có thể parallel? | Mutators còn chạy trong pha ấy? | Ý nghĩa |
| --- | --- | --- | --- |
| **Serial GC — collection pause** | Không, một GC worker chính | **Không — STW** | Đơn giản, ít coordination |
| **Parallel GC — collection pause** | **Có, nhiều workers** | **Không — STW** | Ưu tiên throughput |
| **G1 — young/mixed evacuation** | **Có** | **Không — STW** | Evacuate/copy live objects theo regions |
| **G1 — concurrent marking** | **Có thể nhiều workers** | **Có** | Truy vết live data trong lúc ứng dụng chạy |
| **G1 — remark** | Có thể parallel GC work | **Không — STW** | Hoàn tất phần marking cần synchronization |
| **ZGC — phần lớn expensive GC work** | Có nhiều workers tùy pha | **Có** | Hướng latency thấp, vẫn có pauses ngắn |
| **Shenandoah — nhiều mark/evacuation phases** | Có thể parallel | **Có** | Concurrent mark và relocation, tùy build/mode |
| **Full GC fallback, nếu xảy ra** | Tùy collector/phiên bản | Thường có **STW** đáng kể | Không nên nhầm với cycle thường gặp |

Bảng mang tính mô tả các **phases điển hình**, không phải hợp đồng mọi bản HotSpot đều dùng đúng số threads/phases. Flag, collector version và architecture có thể làm thay đổi chi tiết.

## 9. Serial GC: cơ chế và lựa chọn sử dụng

Serial GC là ví dụ rõ của **thu gom nối tiếp và STW**. Những điểm cần nhớ:

1. **Single GC worker** làm công việc thu gom.
2. **Young collection** trong mô hình generational thường chuyển các object còn sống và thu hồi vùng young.
3. **Old collection** có thể thực hiện marking, sweep/compact tùy hoạt động cụ thể của Serial collector.
4. Công việc thu gom chính tạo ra pause khi mutators bị dừng.
5. Không có overhead phải phối hợp nhiều GC workers cho mỗi collection.

### 9.1. Chọn Serial khi nào?

- Heap nhỏ hoặc object graph nhỏ.
- Môi trường có CPU cực hạn chế.
- Tool/CLI hoặc batch workload ít concurrency.
- Thời gian pause đo được đáp ứng yêu cầu.
- Muốn đo baseline đơn giản trước khi thử collector phức tạp hơn.

### 9.2. Khi nào nên cân nhắc thay?

Nếu request p99 bị ảnh hưởng bởi STW pauses dài hoặc ứng dụng có nhiều cores và GC chiếm phần đáng kể wall time, thử Parallel/G1/ZGC theo mục tiêu đo lường.

Đừng đổi collector chỉ vì “Serial nghe có vẻ lỗi thời”: một cấu hình nhỏ vẫn có thể dùng nó rất hợp lý.

## 10. Parallel GC: thông lượng và các điều chỉnh

Parallel collector dùng nhiều workers cho GC, thường tập trung **throughput**. Nó vẫn có những pause mà ứng dụng ngừng.

### 10.1. Điều chỉnh workers với dữ liệu thật

Cờ HotSpot hay gặp:

```text
-XX:ParallelGCThreads=<n>
```

Đây là **placeholder**; khi cấu hình thực tế phải thay `<n>` bằng số nguyên hợp lệ, xem tương tác với collector và runtime. Flag này liên quan số GC workers cho những công việc parallel trong các collectors có hỗ trợ.

Không phải “đặt workers = toàn bộ CPU cores” luôn tối ưu. Cần tính toán CPU quota, application threads, pause target và overhead.

### 10.2. Cấu hình throughput-oriented

Parallel GC có thể được điều chỉnh với các mục tiêu throughput/pause và adaptive sizing của collector trong HotSpot, nhưng các cờ có ý nghĩa/tác động cụ thể theo phiên bản.

```text
-XX:+UseParallelGC
-XX:ParallelGCThreads=4
```

Là ví dụ tùy chọn, không phải mặc định khuyến nghị cho mọi server. Tốt hơn là bắt đầu từ ergonomic defaults và đo GC logs, p95/p99, throughput, CPU và pause distribution.

### 10.3. Một vấn đề hay hiểu sai: nhiều CPU làm STW biến mất?

Không. Parallelization có thể rút ngắn **thời gian wall-clock** của pha GC được song song hóa, nhưng vẫn là một **STW pause**. Nếu live set lớn, heap pressure nặng hoặc nhiều data phải di chuyển, pause vẫn có thể đáng kể.

## 11. G1: collector vừa parallel, vừa mostly concurrent, vừa STW

**G1 (Garbage-First)** là collector mặc định trong nhiều cấu hình HotSpot Java 17 phổ biến, nhưng default lựa chọn thực tế còn phụ thuộc VM ergonomics và môi trường. Cờ bật tường minh:

```bash
java -XX:+UseG1GC -jar application.jar
```

G1 chia heap thành **regions**, quản lý các phần logical young/old và chọn những vùng đáng thu hồi. Nó dùng concurrent marking để xác định liveness/ứng viên cũ và dùng những STW evacuations để thu hồi tập regions.

### 11.1. Những pha tiêu biểu

```text
G1 cycle — sơ đồ khái quát

[STW Young / Concurrent Start]
            |
            v
   Concurrent Root Region Scan
            |
            v
     Concurrent Marking
            |
            +-- Có thể xen các STW Young collections
            |
            v
       [STW Remark]
            |
            v
   [STW + Concurrent Cleanup]
            |
            v
  Một số [STW Mixed collections]
            |
            v
    Quay lại young-only phase
```

Các tên/sắp xếp cụ thể phản ánh mô tả G1 của JDK 17 trong tình huống hoạt động điển hình; không phải một trace buộc xảy ra mọi lần GC.

### 11.2. G1 evacuation vẫn là STW

Trong young/mixed GC:

- JVM chọn tập regions.
- Nhiều GC workers có thể **copy/evacuate** live objects sang regions khác.
- Object references được cập nhật theo thuật toán.
- **Mutators bị dừng trong pause evacuation**.

Vì G1 có **concurrent marking** nên gọi “G1 là collector không STW” là sai.

### 11.3. G1 pause goal không phải deadline chắc chắn

```text
-XX:MaxGCPauseMillis=200
```

Ví dụ này thể hiện **pause-time goal** cho collector có hỗ trợ, **không phải bảo đảm mọi pause ≤200 ms**. G1 điều chỉnh công việc dựa trên các dự báo, và có thể bỏ lỡ mục tiêu khi áp lực bộ nhớ, live set, CPU hoặc workload bất lợi.

Không dùng pause goal làm thay thế đo tail latency.

### 11.4. Full GC fallback

Trong một số tình huống allocation/evacuation/marking không theo kịp và heap quá chật, G1 có thể phải thực hiện một **Full GC fallback** tốn kém, thường gây STW pause dài.

Không suy luận “chọn G1 thì sẽ không bao giờ Full GC”. Cần có headroom và điều tra nguyên nhân áp lực.

## 12. ZGC và Shenandoah: đưa thêm công việc ra concurrent phases

### 12.1. ZGC

**Z Garbage Collector (ZGC)** tập trung vào **low latency**, thực hiện phần lớn công việc đắt đỏ **đồng thời với mutators**; vẫn có các phối hợp/pauses ngắn tùy version và phase.

Bật trên một bản HotSpot hỗ trợ bằng:

```bash
java -XX:+UseZGC -jar application.jar
```

ZGC thiết kế để giới hạn pauses mà không cần để toàn bộ marking/relocation của live set trong một STW window. Nó có thể sử dụng specialized pointer/barrier mechanisms và cần CPU/headroom cho concurrent work.

Nhưng:

- Không hứa **0 ms pause**.
- Không hứa p99 của mọi endpoint sẽ tốt hơn trong mọi workload.
- Có thể chịu throughput overhead và allocation stalls khi không đủ CPU/headroom.
- Flag và mode generational/non-generational **thay đổi theo JDK**; không áp dụng mọi tuning recipe cho Java 17, 21, 25 và những bản mới.

### 12.2. Shenandoah

**Shenandoah** là collector hướng **low-pause**, thực hiện nhiều hoạt động (gồm marking và, trong thiết kế tương ứng, evacuation/compaction) concurrently với application.

Một số OpenJDK/HotSpot builds hỗ trợ:

```bash
java -XX:+UseShenandoahGC -jar application.jar
```

**Không phải mọi vendor/build/platform đều cung cấp Shenandoah**. Nếu tùy chọn không được VM nhận, đó là vấn đề hỗ trợ tính năng của runtime; dùng `java -version` và tài liệu vendor trước khi chọn.

### 12.3. Tại sao concurrent relocation khó?

Trong marking, collector xác định objects còn sống. Trong **relocation**, collector có thể chuyển live objects sang vị trí mới. Nếu mutators vẫn đang chạy, reference loads/stores cần thấy đối tượng đúng trong quá trình chuyển; VM phải phối hợp pointer forwarding, barriers hoặc cơ chế khác.

**Concurrent compaction không phải đơn giản gọi `System.arraycopy` trong background rồi hy vọng mọi Java references tự đúng**. Đây là một bài toán phối hợp tinh vi giữa mutator, GC và runtime representation.

### 12.4. “Pause time độc lập hoàn toàn heap size” cần hiểu có điều kiện

Các collector low-pause thường thiết kế để tránh pause tăng tỷ lệ trực tiếp với lượng live data lớn, nhưng các yếu tố như OS scheduling, root processing, CPU starvation, safepoint latency và fallback vẫn ảnh hưởng pause. Đừng coi một biểu thức marketing “sub-millisecond” là SLA tuyệt đối của mọi JDK/build/workload.

## 13. “Concurrent” là giao thoa thời gian, không bảo đảm đồng thời trên các core riêng

Trong một môi trường container có **một CPU quota**, các GC workers và application threads có thể xen kẽ trên cùng CPU. Họ vẫn được coi là **concurrent** nếu collector phase hoạt động trong giai đoạn mutators được phép chạy, dù không thực sự có hai instruction thực thi **đúng cùng một nanosecond** trên hai CPU cores.

Phân biệt:

- **Concurrency:** các tác vụ có khoảng sống/thực thi chồng nhau về mặt logic.
- **Parallelism:** nhiều tác vụ thực sự tiến hành cùng lúc trên các xử lý song song, trong điều kiện thích hợp.
- **STW:** mutators không tiến hành bình thường trong khoảng pause, dù GC workers có thể dùng nhiều CPU.

Lúc đọc tài liệu GC, **parallel** thường là số **GC worker threads** tham gia một phase, không chỉ là định nghĩa tổng quát của concurrency trong lập trình đa luồng.

## 14. Chi phí của concurrent GC: CPU, barriers, allocation headroom

Một concurrent collector có thể giảm pause bằng cách trả “giá” ở nơi khác.

### 14.1. CPU contention

Nếu GC workers hoạt động concurrent trong 300 ms, ứng dụng vẫn chạy nhưng có thể thiếu CPU capacity. Một request không bị STW pause vẫn có thể tăng latency do scheduler contention.

### 14.2. Allocation headroom

Mutators tiếp tục cấp phát memory trong lúc collector chưa hoàn tất việc reclaim. Nếu heap quá đầy, collector có thể không có chỗ để giữ đối tượng tạm thời hoặc copy/relocate. Khi đó xuất hiện những **failure/stall paths** tùy thuật toán.

### 14.3. Barriers và metadata

Write/load barriers làm tăng một số instructions/memory operations của mutators, tùy collector. Remembered sets, mark bitmaps và forwarding data cũng cần memory.

### 14.4. Throughput trade-off

Một benchmark có thể cho:

- Parallel GC: throughput cao hơn nhưng p99 pause dài hơn.
- G1: throughput thấp hơn một chút, p99 pause dễ kiểm soát hơn.
- ZGC/Shenandoah: pause thấp hơn nhưng có thể sử dụng thêm CPU/heap cho concurrent work.

**Đây là tình huống minh họa, không phải bảng ranking cố định.** Kết quả thực tế thay đổi theo workload, hardware, JDK/GC version và cách đo.

## 15. Một ví dụ Java 17+ chạy được trên nhiều collector

Chương trình dưới đây tạo một **allocation workload có kiểm soát**. Nó giữ lại một số arrays trong list, còn các arrays khác không được giữ lâu dài. Vì GC schedule là không xác định, chương trình **không in số GC events hay pause timings**; những số liệu ấy được xem trong GC logs.

Tạo tệp **`GCWorkloadDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;

public class GCWorkloadDemo {
    public static void main(String[] args) {
        List<byte[]> retained = new ArrayList<>();
        long checksum = 0;

        for (int i = 0; i < 512; i++) {
            byte[] block = new byte[512 * 1024];
            block[0] = (byte) i;

            checksum += block[0] & 0xFF;
            if (i % 32 == 0) {
                retained.add(block);
            }
        }

        long sum = 0;
        for (byte[] block : retained) {
            sum += block[0] & 0xFF;
        }

        System.out.println("checksum=" + checksum);
        System.out.println("retained arrays=" + retained.size());
        System.out.println("retained first bytes sum=" + sum);
    }
}
```

### 15.1. Biên dịch

```bash
javac --release 17 GCWorkloadDemo.java
```

### 15.2. Chạy với các collectors

Trên một OpenJDK/HotSpot build có hỗ trợ các collector tương ứng:

```bash
java -Xms64m -Xmx64m -XX:+UseSerialGC GCWorkloadDemo
java -Xms64m -Xmx64m -XX:+UseParallelGC GCWorkloadDemo
java -Xms64m -Xmx64m -XX:+UseG1GC GCWorkloadDemo
java -Xms64m -Xmx64m -XX:+UseZGC GCWorkloadDemo
```

**Stdout của ứng dụng khi các lần chạy hoàn tất bình thường:**

```text
checksum=65280
retained arrays=16
retained first bytes sum=1792
```

Mã được biên dịch bằng `javac --release 17` trên OpenJDK 21 và chạy thử với **Serial, Parallel, G1 và ZGC ở 64 MiB heap**; cả bốn đều in cùng kết quả như trên.

Đừng xem `-Xmx64m` là cấu hình khuyến nghị cho production: đây là heap nhỏ tạo áp lực GC để dễ thực hành. Trong môi trường thiếu native memory, GC mode chưa được build, có cờ khác tương tác hoặc CPU quota quá thấp, một lệnh có thể thất bại hay cho GC timeline khác.

### 15.3. Giải thích phép tính

- Có 512 lần cấp phát `byte[512*1024]`.
- `block[0]` là byte của `i`; khi đọc lại dưới dạng unsigned với `& 0xFF`, các giá trị `0..255` lặp hai lần.
- Tổng là `2 × (0+1+...+255) = 65280`.
- Mỗi 32 vòng giữ một array: `i = 0,32,...,480`, tổng **16 arrays**.
- Các byte đầu của 16 arrays giữ lại là `0,32,...,224` lặp hai lần, tổng **1792**.

Ứng dụng không phụ thuộc collector để tính đúng. Khác biệt thuộc **GC throughput, pause/concurrent timings, CPU usage, memory footprint**.

### 15.4. Tại sao không viết test “GC phải xảy ra đúng 12 lần”?

Collector chọn thời điểm và lượng work theo heuristics, allocation patterns, JDK/VM options, heap pressure và JIT. Không có guarantee một chương trình cấp phát 512 arrays thì Java phải chạy đúng N GCs.

Để đo, dùng logging/profiling và so sánh phân phối thay vì hardcode số events.

## 16. Bật GC logging để quan sát STW và concurrent phases

HotSpot JDK 17 có **Unified Logging**. Ví dụ:

```bash
java -Xms64m -Xmx64m -XX:+UseSerialGC -Xlog:gc*=info GCWorkloadDemo
java -Xms64m -Xmx64m -XX:+UseParallelGC -Xlog:gc*=info GCWorkloadDemo
java -Xms64m -Xmx64m -XX:+UseG1GC -Xlog:gc*=info GCWorkloadDemo
java -Xms64m -Xmx64m -XX:+UseZGC -Xlog:gc*=info GCWorkloadDemo
```

**Output GC logs KHÔNG cố định** và sẽ xuất hiện ngoài ba dòng stdout của ứng dụng: timestamp, GC ID, event count, heap occupancy, workers và timings thay đổi theo runtime và môi trường. Không được lấy một log sample rồi khẳng định mọi máy phải cho kết quả y hệt.

### 16.1. Đọc các chữ quan trọng trong logs

Trên những bản HotSpot phù hợp:

- `Pause Young`: một khoảng STW pause liên quan young collection.
- `Pause Full`: một khoảng dừng thu gom toàn heap hoặc fallback tương ứng.
- `Concurrent Mark` hoặc `Concurrent ...`: pha GC được tổ chức làm việc concurrent với mutators.
- `Using ...`: các dòng startup có thể nêu collector được chọn.
- `workers` hoặc các tag phase/worker: giúp quan sát mức parallelism và thời gian worker.

**Đừng hiểu mọi dòng chứa `GC(n)` là một lần STW.** Một GC cycle có thể có nhiều phase logs; các concurrent phases có thể mang cùng GC ID hoặc những cách tổ chức log khác nhau.

### 16.2. So sánh Serial và Parallel

Trong nhiều workload:

- Serial có GC work dựa trên một worker, STW times.
- Parallel có nhiều GC workers trong pause, STW times vẫn tồn tại.
- Các dòng log khác nhau vì collector-specific format và thuật toán.

Không kết luận “Parallel nhanh hơn Serial” nếu chỉ nhìn **một pause**: cần so sánh tổng throughput, pause distribution và CPU cost.

### 16.3. So sánh G1 và ZGC

- G1 có cả STW young/mixed evacuations và concurrent marking.
- ZGC chuyển nhiều công việc nặng sang các pha concurrent; vẫn có một số pauses/coordination.
- Mức phù hợp tùy latency budget, CPU và heap headroom.

### 16.4. Kiểm tra logging tags

```bash
java -Xlog:help
```

Các tag và levels có thể khác khi đổi JDK, không nên copy một tổ hợp `-Xlog` đặc thù từ blog cũ rồi dùng cho mọi HotSpot versions.

## 17. Các tham số nên đo khi quyết định collector

| Chỉ số | Ý nghĩa | Cách sử dụng |
| --- | --- | --- |
| **STW pause p50/p95/p99/max** | Distribution các khoảng dừng | Xem latency tail, outliers và SLA |
| **Request p95/p99** | Độ trễ người dùng thực | Kết hợp GC logs và tracing |
| **Throughput** | Requests/records/tasks mỗi giây | So sánh lợi ích ứng dụng cuối cùng |
| **CPU utilization** | Mutators + GC workers | Nhận biết GC contention |
| **Allocation rate** | Bytes tạo mới mỗi giây | Phân tích áp lực trên young/old heap |
| **Live set** | Dung lượng objects còn reachable | Quyết định lượng mark/copy/compact |
| **Heap occupancy / headroom** | Không gian còn cho allocation/relocation | Tránh stalls, fallback, OOME |
| **GC CPU time vs wall time** | Chi phí tính toán và thời gian trôi | Đừng cộng nhầm nhiều workers như một pause |
| **Concurrent cycle duration** | Thời gian GC còn chạy cùng mutators | Phát hiện cycle không theo kịp |
| **Full GC / allocation stalls** | Tình huống bất thường, có thể gây latency | Phân tích memory pressure và tuning |

### 17.1. Phân biệt latency và throughput

- Ứng dụng xử lý batch có thể tối ưu records/s, chấp nhận STW pauses.
- API cho người dùng có thể ưu tiên p99 end-to-end latency.
- Một hệ thống mixed workload phải cân bằng cả hai, tùy SLO.

Cùng một collector không luôn tối ưu cho mọi mục tiêu.

### 17.2. Kết quả benchmark cần lặp và có baseline

Một quy trình tốt:

1. Giữ **cùng JDK build**, cùng application artifact và workload.
2. Cố định heap options phù hợp, CPU quota và container limits.
3. Warm-up trước khi đo để giảm nhiễu JIT/class loading.
4. Lặp nhiều runs, đo throughput và pause/latency distribution.
5. Ghi số classes, live set, allocation rate, CPU, memory.
6. So sánh theo mục tiêu nghiệp vụ rồi mới chọn collector.

Nếu một run duy nhất cho Parallel GC p99 tốt hơn G1, đó là quan sát chứ không phải quy luật vĩnh viễn.

## 18. Các cờ liên quan và lưu ý không “tối ưu mù”

### 18.1. Chọn collector

```text
-XX:+UseSerialGC
-XX:+UseParallelGC
-XX:+UseG1GC
-XX:+UseZGC
-XX:+UseShenandoahGC  (khi bản HotSpot hỗ trợ)
```

Mỗi tiến trình JVM thường chọn **một collector phù hợp**; không gộp nhiều cờ lựa chọn collector khác nhau tùy tiện trong một lệnh. Tính khả dụng và defaults phụ thuộc VM/JDK build.

### 18.2. Mục tiêu G1 và workers

```text
-XX:MaxGCPauseMillis=200
-XX:ParallelGCThreads=4
-XX:ConcGCThreads=2
```

Các values trên **chỉ minh họa các loại cờ**, không là cấu hình production mặc định. `ParallelGCThreads` kiểm soát parallel work trong những collector/phases hỗ trợ; `ConcGCThreads` là tham số liên quan concurrent worker count theo collector.

Nếu đặt concurrent workers quá ít, collector có thể không theo kịp allocation/mutation rate. Nếu quá nhiều, ứng dụng có thể thiếu CPU.

### 18.3. Tránh dựa vào tuning recipe cũ

Các collectors, cờ và algorithms đã thay đổi qua JDK releases. Ví dụ **CMS** (Concurrent Mark Sweep) là collector lịch sử, bị loại khỏi HotSpot từ **JDK 14** (JEP 363), vì vậy không dùng `-XX:+UseConcMarkSweepGC` như một tùy chọn hiện hành của JDK 17.

Với ZGC, các phiên bản mới có hỗ trợ **generational** thay đổi lớn trong thiết kế và tuning. Không lấy một tập cờ từ JDK 17 rồi áp cho JDK 25/27 mà không xem migration notes.

### 18.4. “GC pause goal 50ms” không là real-time guarantee

Một số cờ giúp collector nhắm đến pause target bằng heuristics, nhưng không cam kết deadline tuyệt đối cho mọi tình huống. Bảo đảm thời gian thực (*hard real-time*) cần mô hình hệ thống và runtime chuyên dụng khác, không chỉ đổi cờ GC.

## 19. Một chu kỳ G1 có thể vừa parallel vừa concurrent: diễn giải đầy đủ

Hãy giả sử (để dễ hình dung) ứng dụng có 4 application threads và G1 được phân 4 parallel workers trong STW pauses, 2 workers trong concurrent phases. Đây là **con số minh họa**, không phải giá trị mặc định được bảo đảm.

```text
                t0              t1              t2             t3
                |               |               |              |
Mutators A-D    RUNNING  ...  [PAUSE]   RUNNING  ...          [PAUSE]
                                  |                              |
GC 4 workers                      | parallel evacuation          | parallel work
                                  |
GC 2 workers                                     concurrent mark
                                                 +------+--------+
                                                        |
                                               mutators RUNNING
```

Diễn giải:

1. Trong **STW evacuation**: 4 GC workers có thể chạy đồng thời nhau, còn 4 mutator threads bị dừng.
2. Trong **concurrent mark**: 2 GC workers làm việc trong giai đoạn 4 mutators được phép chạy.
3. Cuối marking có thể có **STW remark/cleanup**.
4. Không được tính tổng thời gian concurrent phase thành pause.
5. Application CPU có thể bị chia sẻ trong concurrent mark.

Chính vì thế một câu mô tả như **“G1 là parallel, mostly concurrent, evacuating và stop-the-world”** không tự mâu thuẫn; mỗi thuộc tính mô tả một khía cạnh/pha của collector.

## 20. Phân tích tình huống thực tế

### Tình huống A — CLI tool nhỏ, chạy vài giây

Một CLI tool có heap nhỏ, lượng objects không lớn và CPU quota thấp có thể thử **Serial GC**. Overhead tạo nhiều GC workers đôi khi không đem lại lợi ích. Nhưng cần xác minh runtime và độ trễ tổng, không dựa vào tên collector.

### Tình huống B — Batch processing cần throughput

Một batch worker chạy trên máy đa core, cho phép pauses khá dài nhưng muốn tổng thời gian xử lý ngắn có thể thử **Parallel GC**. Vẫn đo thời gian tạm dừng và memory, bởi pauses quá dài có thể ảnh hưởng job coordination.

### Tình huống C — HTTP API có p99 target

Một HTTP service cần giảm tail latency có thể bắt đầu với **G1** (thường là default trên cấu hình Java 17 server-class) và quan sát STW young/mixed pauses. Nếu p99 vẫn không đáp ứng, thử **ZGC** trên runtime hỗ trợ, đồng thời đo CPU, request latency và allocation stalls.

### Tình huống D — Ứng dụng tạo object cực nhanh

Một system có allocation rate cao, live set lớn và heap ít headroom có thể làm **concurrent collector không theo kịp**. Không đơn giản giải quyết bằng việc “chọn concurrent GC”; cần giảm allocation, sửa retention, tăng heap/headroom hợp lý hoặc điều chỉnh workload.

### Tình huống E — Container 2 vCPU bị CPU throttling

Một JVM chạy concurrent GC trong container có thể bị CPU contention/throttling, làm cả GC cycle và request time kéo dài. GC pauses đo được có thể nhỏ nhưng p99 request vẫn tăng. Kiểm tra CPU quota và throttling metrics thay vì nhìn mỗi GC logs.

## 21. Những hiểu lầm phổ biến

| Nhận định sai | Cách hiểu đúng |
| --- | --- |
| “Parallel GC chạy cùng ứng dụng.” | Parallel chủ yếu nói GC workers; Parallel collector có STW phases trong đó mutators dừng. |
| “Serial GC chỉ chạy khi ứng dụng có một thread.” | Một GC worker không giới hạn số application threads. |
| “Concurrent GC không bao giờ STW.” | Nhiều concurrent collectors vẫn có pauses/coordination ngắn. |
| “G1 chỉ concurrent, không parallel.” | G1 dùng cả parallel STW evacuation lẫn concurrent marking. |
| “Một GC cycle dài 500 ms nghĩa request pause 500 ms.” | Concurrent cycle elapsed time khác STW pause time. |
| “4 GC workers chắc chắn nhanh gấp 4.” | Đồng bộ/overhead/CPU và phần work không parallel giới hạn tốc độ. |
| “STW pause 2ms nghĩa GC không tốn CPU.” | Concurrent phases, barriers và runtime bookkeeping có thể tốn CPU. |
| “Concurrent GC không cần heap headroom.” | Mutators vẫn allocate trong lúc GC chưa reclaim xong. |
| “`MaxGCPauseMillis` là deadline tuyệt đối.” | Là mục tiêu heuristic, không phải hard SLA. |
| “Bật ZGC làm throughput luôn tốt hơn.” | Low-latency có trade-offs CPU/throughput và phụ thuộc workload. |
| “`System.gc()` bảo đảm một GC cycle bắt đầu/kết thúc theo lịch chính xác.” | Đây không phải công cụ test số GC events portable. |
| “Heap lớn thì không cần đo GC.” | Live set, allocation/mutation rates và latency vẫn quan trọng. |
| “CMS vẫn là lựa chọn bình thường trên JDK17.” | CMS đã bị loại khỏi HotSpot từ JDK14. |
| “Shenandoah luôn có trên mọi JDK.” | Tùy vendor/build/platform. |
| “G1 default trên tất cả mọi JVM.” | Default phụ thuộc implementation/ergonomics, dù G1 phổ biến trên HotSpot server configurations. |
| “Mọi GC log line biểu thị một pause.” | Có cả concurrent phase logs, startup info và nhiều events trong một cycle. |
| “CPU host có 64 cores nghĩa container dùng đủ 64.” | CPU quota/cgroup có thể giới hạn. |
| “Có một collector tốt nhất cho mọi hệ thống.” | Phải chọn theo SLO, workload, heap, CPU, version và đo lường. |

## 22. Bài tập tự kiểm tra kèm đáp án

**Câu 1.** Parallel GC có cần dừng application threads trong những collection pauses không?

**Đáp án:** Có. Nhiều GC workers làm việc **song song với nhau** trong **STW**, không có nghĩa họ chạy đồng thời với mutators.

**Câu 2.** Serial GC có cấm chương trình Java tạo nhiều threads không?

**Đáp án:** Không. “Serial” nói về GC work, không phải số application threads.

**Câu 3.** Một concurrent GC phase có đúng một GC worker và mutators vẫn chạy. Có phải concurrent không?

**Đáp án:** Có. Concurrent với ứng dụng là một trục khác với số GC workers parallel.

**Câu 4.** G1 có thể có concurrent mark và STW evacuation cùng trong một GC lifecycle không?

**Đáp án:** Có. G1 kết hợp nhiều pha; không mâu thuẫn giữa “mostly concurrent” và “stop-the-world phases”.

**Câu 5.** Tại sao concurrent collector cần write/load barriers?

**Đáp án:** Mutators còn thay đổi hoặc truy cập đồ thị references trong khi GC làm việc; barriers giúp bảo toàn invariants của thuật toán marking/relocation tương ứng.

**Câu 6.** Một concurrent marking phase dài 300 ms có nghĩa ứng dụng bị pause 300 ms không?

**Đáp án:** Không. Đây có thể là thời gian GC làm việc trong lúc mutators tiếp tục; pauses nếu có cần xem những pha/logs riêng.

**Câu 7.** Nếu ZGC có pause nhỏ nhưng CPU usage tăng, ứng dụng có chắc nhanh hơn không?

**Đáp án:** Không. CPU contention/barrier overhead có thể ảnh hưởng throughput và latency; phải benchmark end-to-end.

**Câu 8.** Vì sao Parallel GC có thể giúp batch job?

**Đáp án:** Nhiều GC workers có thể rút ngắn wall time của các pha collection trên hệ đa core, cải thiện throughput khi pauses dài vẫn chấp nhận được.

**Câu 9.** Có thể xem `-XX:MaxGCPauseMillis=50` là SLA p99 dưới 50ms không?

**Đáp án:** Không. Đó là GC pause goal, không bảo đảm mọi pause hay request response time dưới 50ms.

**Câu 10.** Concurrent collector còn làm việc khi mutators tạo thêm nhiều objects. Rủi ro gì?

**Đáp án:** Heap headroom có thể cạn trước khi GC reclaim đủ, gây allocation stalls/fallback/OOME tùy collector.

**Câu 11.** ZGC và Shenandoah có ở mọi Java 17 distribution không?

**Đáp án:** Không thể giả định. Tính năng và độ hỗ trợ phụ thuộc VM vendor/build/platform.

**Câu 12.** G1 young collection thường STW hay concurrent với ứng dụng?

**Đáp án:** Việc evacuation của selected young regions diễn ra trong **STW pause**; các GC workers có thể hoạt động parallel.

**Câu 13.** Vì sao không đo tốc độ GC bằng một dòng tổng elapsed time rồi so sánh?

**Đáp án:** Một collector có thể có concurrent work không dừng mutators; cần tách pause times, CPU work, throughput và effect đến application.

**Câu 14.** Thấy gc worker count 8 trong log, có chứng minh 8 CPU core thật chạy cùng lúc không?

**Đáp án:** Không. Số worker threads không đảm bảo parallel hardware execution, đặc biệt với CPU quota/throttling.

**Câu 15.** Đổi từ Serial sang Parallel luôn giảm p99 request latency?

**Đáp án:** Không. Có thể giảm một số STW duration nhưng còn overhead và workload differences; cần đo.

**Câu 16.** Vì sao `GCWorkloadDemo` có cùng stdout khi chạy các collector khác nhau?

**Đáp án:** GC chọn cách thu hồi bộ nhớ nhưng phải giữ Java program semantics. Checksum và các phần tử trong list được giữ có kết quả xác định.

**Câu 17.** Khi nào cân nhắc ZGC thay G1?

**Đáp án:** Khi latency SLO khó đạt dù đã tối ưu workload/heap và G1, trong khi runtime hỗ trợ ZGC và CPU/heap headroom cho concurrent GC. Phải xác minh bằng benchmark.

**Câu 18.** Nếu G1 đang concurrent mark nhưng có xen STW young collection, gọi G1 là concurrent có sai không?

**Đáp án:** Không. G1 là mostly concurrent ở một số công việc, nhưng vẫn có pauses. Cần mô tả ở cấp pha.

## 23. Checklist lựa chọn và vận hành

1. Xác định **SLO latency**, **throughput** và ngân sách CPU/memory.
2. Ghi nhận JVM vendor, version, architecture, cgroup quota và heap limits.
3. Bắt đầu với collector default nếu chưa có yêu cầu đặc biệt, xem log xác nhận collector thực tế.
4. Đo allocation rate, live set, promotion và heap headroom.
5. Quan sát **STW pause distribution**, không chỉ tổng GC duration.
6. Quan sát **CPU contention trong concurrent phases**.
7. Xem Full GC fallback, allocation stalls và OOME nếu có.
8. Với G1, hiểu concurrent marking khác STW evacuation.
9. Với Parallel, nhớ GC workers parallel không có nghĩa mutators còn chạy trong STW.
10. Với low-latency collectors, không giả định zero pause hoặc free CPU cost.
11. So sánh workloads sau warm-up, lặp runs, cùng resource limits.
12. Nếu container bị throttling, xem quota và available processor count.
13. Xem các cờ hiện tại bằng `java -XX:+PrintFlagsFinal -version`, đừng đoán defaults.
14. Kiểm tra hỗ trợ collector trước khi đặt cờ, nhất là Shenandoah và flags qua JDK versions.
15. Không cố kích hoạt GC trong unit test rồi đo số events cố định.
16. Sửa **unbounded allocation hoặc object retention** trước khi coi GC flag là thuốc chữa mọi vấn đề.
17. Với hệ thống production, kết hợp GC logs, JFR, application tracing và OS metrics.
18. Đảm bảo mọi tối ưu collector không đổi semantics và correctness của ứng dụng.

### Tổng kết cuối

```text
                   Có bao nhiêu GC workers?
                     1              N
                     |              |
               Serial GC work    Parallel GC work
                     \              /
                      \            /
               Mutators có còn chạy?
                 /             \
               Không            Có
                |                |
                v                v
           STW phase         Concurrent phase
                |                |
          Application pause    GC & application
                               cùng tiến triển
                                (chia sẻ CPU)

Một collector hiện đại có thể dùng N GC workers trong STW
VÀ nhiều GC workers chạy concurrent ở một pha khác.
```

**Kết luận:** **Serial/parallel** mô tả **mức độ song song của công việc GC**, còn **STW/concurrent** mô tả **GC làm việc trong khi ứng dụng bị dừng hay còn chạy**. Đừng gộp hai trục thành một.

### Tài liệu tham khảo chính thức

- [Oracle JDK 17 — Available Collectors](https://docs.oracle.com/en/java/javase/17/gctuning/available-collectors.html): Serial, Parallel, G1, ZGC và các tiêu chí lựa chọn.
- [Oracle JDK 17 — G1 Garbage Collector](https://docs.oracle.com/en/java/javase/17/gctuning/garbage-first-g1-garbage-collector1.html): GC workers, STW evacuation, concurrent marking, pause goals.
- [Oracle — G1 Garbage Collector Phases](https://www.oracle.com/java/technologies/g1gc.html): SATB, remark, young/mixed evacuation, phase-specific concurrency.
- [OpenJDK JEP 333 — ZGC: A Scalable Low-Latency Garbage Collector](https://openjdk.org/jeps/333): concurrent GC và low-latency objectives.
- [OpenJDK JEP 189 — Shenandoah: A Low-Pause-Time Garbage Collector](https://openjdk.org/jeps/189): concurrent compaction/reclamation.
- [OpenJDK JEP 363 — Remove the Concurrent Mark Sweep (CMS) Garbage Collector](https://openjdk.org/jeps/363): CMS lịch sử không còn trong JDK 14+ HotSpot.
- [Oracle JDK 17 — java command options](https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html): lựa chọn collector và Unified Logging `-Xlog`.
- [JVMS `2.5.3` — Heap (Java SE 17)](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-2.html#jvms-2.5.3): automatic storage management không bắt buộc một GC implementation.
