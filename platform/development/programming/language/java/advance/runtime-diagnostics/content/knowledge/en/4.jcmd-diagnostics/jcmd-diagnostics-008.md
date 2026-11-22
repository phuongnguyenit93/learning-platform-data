# 4.8 — Vai trò bổ sung và trạng thái experimental của jstack, jmap, jinfo và jstat

## 1. Vì sao cần biết bốn công cụ này khi đã có jcmd?

Khi chẩn đoán một JVM đang chạy, `jcmd` là công cụ tổng hợp để gửi diagnostic command đến tiến trình đích. Tuy nhiên, tài liệu, runbook và câu lệnh của nhiều hệ thống vẫn sử dụng bốn tiện ích JDK chuyên biệt: **`jstack`**, **`jmap`**, **`jinfo`** và **`jstat`**. Chúng không hoàn toàn giống nhau: mỗi công cụ trả lời một nhóm câu hỏi và có đặc điểm về dữ liệu, cách truy cập, chi phí và độ ổn định riêng.

Mục tiêu bài học:

1. Nhận diện chính xác **vai trò bổ sung** của từng công cụ và tình huống nên dùng.
2. Biết các thao tác `jcmd` tương ứng khi có, đồng thời nhận ra những nơi **không có thay thế một-một**.
3. Hiểu nhãn **experimental and unsupported** trong tài liệu công cụ Java SE 17: nó có nghĩa gì cho runbook, automation và nâng cấp JDK.
4. Đọc được các ví dụ lệnh hợp lệ, phát hiện sai phạm vi PID, sai phiên JVM hoặc nguy cơ tác động tới production.
5. Áp dụng một luồng chẩn đoán thực tế: xác minh mục tiêu → đặt câu hỏi → chọn bằng chứng → đối chiếu trước khi kết luận.

> **Nguyên tắc:** “Experimental/unsupported” mô tả mức cam kết hỗ trợ và khả năng tương thích của **công cụ dòng lệnh**; không mặc định rằng công cụ bị xóa hoặc vô dụng. Ngược lại, việc một công cụ vẫn chạy được trên máy bạn không biến cú pháp/output của nó thành một hợp đồng ổn định cho mọi JDK.

## 2. Bản đồ nhanh: jstack / jmap / jinfo / jstat so với jcmd

| Công cụ | Câu hỏi chính | Ví dụ đặc trưng | `jcmd` liên quan | Điều cần phân biệt |
| --- | --- | --- | --- | --- |
| **`jstack`** | Các Java thread đang chạy/chờ ở đâu, có tranh chấp lock không? | `jstack -l <pid>` | `jcmd <pid> Thread.print -l` | Snapshot thread/lock, không phải CPU profiler hay lịch sử |
| **`jmap`** | Heap có các class/đối tượng nào; cần heap dump không? | `jmap -histo <pid>`; `jmap -dump:format=b,file=... <pid>` | `GC.class_histogram`, `GC.heap_dump`, `GC.heap_info` | Có thể tốn tài nguyên, gọi GC hoặc tạo file lớn; không tự chứng minh leak |
| **`jinfo`** | Runtime flags và system properties hiện tại là gì? | `jinfo -flags <pid>`; `jinfo -sysprops <pid>` | `VM.flags`, `VM.command_line`, `VM.system_properties`; khi cho phép mới xét `VM.set_flag` | Một số chế độ **đổi flag**, không chỉ đọc; properties có thể chứa secret |
| **`jstat`** | Các bộ đếm JVM/GC biến đổi như thế nào qua thời gian? | `jstat -gcutil -t <pid> 1000 5` | `PerfCounter.print` và các command GC chỉ cung cấp **một phần góc nhìn**; JFR/metrics hỗ trợ theo thời gian | `jstat` là lấy mẫu counter theo chu kỳ, không có `jcmd` tương đương từng cột |

**Đặt theo loại bằng chứng:**

- `jstack` → **thread dump** tại thời điểm chụp.
- `jmap` → **class histogram** hoặc **heap dump**, chủ yếu cho bộ nhớ Java.
- `jinfo` → **cấu hình runtime** và một số flag có thể thay đổi.
- `jstat` → **chuỗi mẫu thống kê JVM**, đặc biệt GC/heap/class loading/compilation.

Cùng một triệu chứng như “độ trễ tăng” có thể cần hơn một công cụ: `jstat` cho thấy GC xảy ra dày hơn, `jstack` kiểm tra thread có bị khóa, và JFR bổ sung phân tích CPU/GC/lock theo thời gian. Bản đồ trên dùng để **chọn đúng bằng chứng**, không phải để chạy mọi lệnh một lượt.

## 3. “Experimental and unsupported” thực sự có nghĩa gì?

Các trang lệnh **`jstack`**, **`jmap`**, **`jinfo`** và **`jstat`** trong **Oracle Java SE 17 Tool Specifications** đều ghi chú rằng command là **experimental and unsupported**. Tài liệu mô tả rằng công cụ hoặc option của chúng có thể đổi hoặc không còn được cung cấp ở một phiên bản JDK tương lai.

### 3.1. Ba hệ quả vận hành

1. **Không giả định giao diện ổn định giữa JDK/vendor.** Option, tên cột, định dạng output, khả năng attach và lệnh thay thế có thể khác nhau. Trước khi dùng, kiểm tra tool thực tế với `-help`/`-options` và JDK đang vận hành.
2. **Không xây automation phụ thuộc chặt vào output văn bản.** Đặc biệt, tài liệu `jstat` cảnh báo không nên viết script parse output vì định dạng có thể thay đổi. Nếu bắt buộc parse, gắn phiên bản công cụ, kiểm tra header, ghi lại rủi ro nâng cấp và có test phù hợp.
3. **Không coi “unsupported” đồng nghĩa “luôn lỗi”.** Công cụ vẫn có thể nằm trong JDK 17 và chạy hữu ích trong môi trường đáp ứng điều kiện. Điều phải thay đổi là mức độ thận trọng khi thiết kế quy trình phụ thuộc vào nó.

### 3.2. “Experimental tool” khác với “experimental VM option”

Ba khái niệm thường bị trộn:

| Khái niệm | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| **Experimental/unsupported tool** | Nhãn trên tài liệu `jmap`, `jstat` | Giao diện công cụ không được cam kết hỗ trợ/ổn định như API Java SE chuẩn |
| **Experimental HotSpot VM option** | Một số `-XX:...` cần `-XX:+UnlockExperimentalVMOptions` | Nhóm tùy chọn khởi động JVM có chính sách mở khóa riêng |
| **Preview feature của Java language** | Tính năng ngôn ngữ dùng `--enable-preview` | Cơ chế thử nghiệm tính năng ngôn ngữ/API ở các bản Java cụ thể |

**Không cần thêm `-XX:+UnlockExperimentalVMOptions` chỉ để gọi `jstack`/`jmap`/`jinfo`/`jstat`.** Cờ này quản lý nhóm JVM startup options, **không thay đổi** trạng thái hỗ trợ của các command-line tools.

### 3.3. Đừng ngoại suy từ bản JDK này sang bản khác

Bài sử dụng **cú pháp tham khảo của JDK 17**. Với JDK mới hơn, GraalVM, OpenJ9, runtime đóng gói tối giản hoặc vendor khác, cần xác nhận tính hiện diện và hành vi thực tế. `java -version` của shell chưa chứng minh đó là Java của tiến trình đích; đối chiếu `jcmd <pid> VM.version` khi attach được và đường dẫn executable của tiến trình.

Nếu công cụ không có hoặc không tương thích, **lựa chọn thay thế** nên dựa trên câu hỏi chẩn đoán: `jcmd`, JFR, OS metrics, logs hoặc công cụ do vendor hỗ trợ. Không chỉ đổi tên executable rồi giả định dữ liệu tương đương hoàn toàn.

## 4. jstack — chụp stack của các Java thread

### 4.1. jstack trả lời được câu hỏi gì?

`jstack` in stack trace của nhiều Java thread trong một JVM. Trên JDK 17, cú pháp cơ bản:

```bash
jstack <pid>
jstack -l <pid>
```

`-l` in thêm thông tin về lock. Kết quả giúp nhận ra thread:

- `RUNNABLE`: có thể thực thi từ góc nhìn JVM; **không tự chứng minh** đang sử dụng CPU.
- `BLOCKED`: đang đợi quyền vào Java monitor (ví dụ `synchronized`).
- `WAITING` / `TIMED_WAITING`: đợi qua cơ chế `wait`, `join`, `park`, `sleep` hoặc các dạng chờ tương ứng.
- Chuỗi thread cùng đợi một monitor, hoặc nhiều worker kẹt trong chỗ gọi I/O/connection pool.

Ví dụ một đoạn **minh họa**:

```text
"worker-7" #31 ... java.lang.Thread.State: BLOCKED
    at example.OrderCache.get(OrderCache.java:42)
    - waiting to lock <0x...> (a java.lang.Object)
```

Dấu `<0x...>`, số thread, frame và cách trình bày là minh họa; không phải output cố định. Từ **một** ảnh chụp không thể biết thời gian thread đã chờ. Với sự cố kéo dài, thu 2–3 dump cách nhau vài giây, kèm timestamp và metrics; tránh liên tục lấy dump nếu JVM nhiều thread.

### 4.2. Lệnh jcmd thường dùng thay thế

```bash
jcmd <pid> Thread.print -l
```

Đây là đường tiếp cận phổ biến để lấy **thread dump** qua diagnostic command. Hai công cụ cùng phục vụ điều tra thread nhưng không được giả định output byte-for-byte giống nhau ở mọi JDK. Trước khi chạy lệnh nặng hơn, có thể hỏi:

```bash
jcmd <pid> help Thread.print
```

Các tùy chọn và mức impact cần lấy từ **JVM thực tế**. `Thread.print` có thể tạo output lớn và tốn thời gian nếu ứng dụng có rất nhiều thread.

### 4.3. Lỗi thường gặp

- Kết luận có deadlock chỉ vì nhiều thread `WAITING`. Thread pool rỗi thường `WAITING` ở điểm lấy task; cần xem stack và quan hệ lock.
- Đọc thread dump của PID đã restart, rồi gắn kết quả cho phiên ứng dụng cũ.
- Quy tất cả `RUNNABLE` thành CPU hotspot; cần JFR/CPU profiling và số đo CPU để xác thực.
- Dùng thread dump để trả lời “đối tượng nào giữ RAM” — câu hỏi đó thuộc heap analysis, không phải stack hiện tại.

**Chọn `jstack`/`Thread.print` khi:** request bị treo, nghi lock contention, deadlock, thread pool cạn hoặc muốn đối chiếu trạng thái thread với spike latency.

## 5. jmap — histogram, heap dump và quan hệ giữ bộ nhớ

### 5.1. Xem phân bố class/instance

`jmap` giúp xem thông tin liên quan heap của JVM đích. Ví dụ JDK 17:

```bash
jmap -histo <pid>
```

Histogram thường có class name, số lượng instance và dung lượng nông (shallow bytes), không phải retained size hay đường tham chiếu. Lệnh tương ứng trong `jcmd`:

```bash
jcmd <pid> GC.class_histogram
```

**Lưu ý hiệu năng:** cả histogram và dump có thể gây chi phí đáng kể phụ thuộc heap và trạng thái JVM; hãy xem help/impact và chạy khi có mục tiêu điều tra rõ ràng. Nếu cần phân biệt object “đang còn sống”, tài liệu JDK 17 có:

```bash
jmap -histo:live <pid>
```

Chế độ `:live` chỉ đếm live objects, nhưng có thể tác động tới hoạt động GC và latency; đừng sử dụng làm metric monitoring thường xuyên. `GC.class_histogram` có tùy chọn `-all` với ý nghĩa bao gồm cả unreachable objects; **không** mặc định ghép `:live` với một option `jcmd` khác theo cú pháp giống hệt.

### 5.2. Tạo heap dump HPROF

Khi nghi object giữ quá lâu, cần heap dump để phân tích với Eclipse Memory Analyzer (MAT) hoặc công cụ tương đương.

Ví dụ `jmap` trên JDK 17:

```bash
jmap -dump:format=b,file=/var/tmp/service-heap.hprof <pid>
```

Nếu thêm `live`:

```bash
jmap -dump:live,format=b,file=/var/tmp/service-live.hprof <pid>
```

`-dump:...` là một nhóm suboptions của **`jmap`**, không phải option chung cho `jcmd`. Với `jcmd`:

```bash
jcmd <pid> GC.heap_dump /var/tmp/service-heap.hprof
```

Tài liệu JDK 17 ghi `GC.heap_dump` có **impact cao**, phụ thuộc heap size/content, và mặc định yêu cầu full GC trừ khi dùng `-all`. Vì thế không coi đây là thao tác xem cấu hình vô hại. `jmap` và `jcmd` có **cú pháp, mặc định và chi tiết triển khai khác nhau**; khi muốn so live/all objects phải đọc help đúng runtime.

**Đường dẫn output quan trọng:** file dump được tạo theo filesystem và quyền của **JVM đích**, có thể là đường dẫn trong container chứ không phải thư mục của terminal bên ngoài. Heap dump có thể chiếm vài GB, gây pause/I/O lớn và chứa token, session, dữ liệu người dùng. Cần đủ đĩa, quyền lưu trữ và chính sách kiểm soát truy cập trước khi tạo.

### 5.3. Đọc kết quả đúng cách

- Histogram cho biết class/instance nào chiếm bộ nhớ, **không tự chứng minh memory leak**.
- **Shallow size** là kích thước trực tiếp của object; **retained size** phụ thuộc đồ thị tham chiếu. Muốn tìm ai giữ object, cần dominator tree và path to GC roots từ heap dump.
- Heap Java lớn có thể do cache hợp lệ hoặc tải tăng. Đối chiếu heap used sau GC qua thời gian, allocation rate và hành vi nghiệp vụ.
- Heap dump không đại diện cho mọi **native/off-heap memory**, memory-mapped file hoặc file descriptors; không suy luận tất cả RSS cao đều là Java heap leak.

**Chọn `jmap`/`GC.class_histogram`/`GC.heap_dump` khi:** có nghi vấn giữ object, heap tăng sau nhiều chu kỳ GC, OOM do Java heap, hoặc cần phân tích retained graph.

## 6. jinfo — flags, system properties và cấu hình JVM

`jinfo` cung cấp thông tin cấu hình của tiến trình Java. Trên JDK 17:

```bash
jinfo -flags <pid>
jinfo -sysprops <pid>
jinfo -flag <flag-name> <pid>
```

- `-flags`: các JVM command-line flags mà công cụ hiển thị.
- `-sysprops`: system properties của Java runtime đích.
- `-flag <name>`: xem giá trị của một flag cụ thể theo cú pháp JDK đang sử dụng.

Một số chế độ `-flag` của `jinfo` **có thể thay đổi flag**:

```text
jinfo -flag +<boolean-flag> <pid>
jinfo -flag -<boolean-flag> <pid>
jinfo -flag <flag-name>=<value> <pid>
```

Đây là **mẫu cú pháp mô tả**, không phải khuyến nghị chạy trên production: chỉ những flag được runtime cho phép chỉnh động mới có thể thay đổi, và giá trị phải hợp lệ. Một thay đổi có thể kéo dài cho đến khi JVM dừng hoặc cấu hình được hoàn nguyên.

### 6.1. Các lệnh jcmd liên quan

```bash
jcmd <pid> VM.command_line
jcmd <pid> VM.flags
jcmd <pid> VM.system_properties
```

`VM.command_line` giúp đối chiếu launch command/JVM arguments; `VM.flags` và `VM.system_properties` cung cấp các lát cắt cấu hình. Có thể xem trợ giúp:

```bash
jcmd <pid> help VM.flags
jcmd <pid> help VM.set_flag
```

**`VM.set_flag` là command thay đổi cấu hình**, không phải bản sao chỉ-đọc của `jinfo -flags`. Không thử chỉnh flag chỉ để “xác minh công cụ hoạt động”. `VM.flags -all` (nếu được hỗ trợ trên JVM đích) có thể in phạm vi flags rộng hơn `VM.flags` mặc định.

### 6.2. Hệ quả bảo mật

System properties và command-line arguments có thể chứa database URLs, API tokens, tên tài khoản, đường dẫn nhạy cảm hoặc cấu hình bảo mật. Bất kỳ việc lấy `jinfo -sysprops` hay `jcmd VM.system_properties` đều cần quyền truy cập phù hợp và loại bỏ dữ liệu bí mật trước khi gửi log/đính kèm ticket.

**Chọn `jinfo`/`VM.flags` khi:** cần so sánh cấu hình thực tế với deployment, kiểm tra flag GC/JIT/memory, hoặc tìm sự khác biệt giữa hai JVM. Với thông số ứng dụng, phải phân biệt **startup flag**, **system property**, **environment variable** và **cấu hình ứng dụng**; chúng không đồng nhất.

## 7. jstat — chuỗi thống kê JVM theo khoảng thời gian

`jstat` khác ba công cụ trên ở chỗ nó chủ yếu **lấy mẫu các counters JVM theo chu kỳ**. Điển hình:

```bash
jstat -options
jstat -gcutil <pid> 1000 5
jstat -gcutil -t <pid> 1000 5
```

Giải nghĩa `jstat -gcutil -t <pid> 1000 5`:

1. `-gcutil`: lấy nhóm thống kê tóm tắt GC.
2. `-t`: thêm cột **Timestamp** là số giây kể từ lúc JVM đích bắt đầu, **không phải giờ UTC**.
3. `<pid>`: VM identifier (vmid) cục bộ ở ví dụ này.
4. `1000`: interval mặc định tính bằng **mili giây**, tức 1 giây giữa các mẫu.
5. `5`: số mẫu hữu hạn để lấy. **Nếu bỏ count**, lệnh có thể tiếp tục in cho đến khi JVM kết thúc hoặc được dừng.

### 7.1. Hiểu cột và giới hạn

Các cột phổ biến của `-gcutil` trên HotSpot có thể gồm tỉ lệ dùng các vùng memory, số GC và thời gian GC. Tên/ý nghĩa cụ thể **phụ thuộc JDK, collector và phiên bản công cụ**. Ví dụ:

- `YGC`: số sự kiện young GC theo định nghĩa thống kê của collector tương ứng.
- `YGCT`: tổng thời gian young GC đã ghi.
- `FGC` và `FGCT`: số lần và thời gian full GC theo cơ chế JVM/collector tương ứng.
- `GCT`: tổng thời gian GC tích lũy theo cách runtime báo cáo.
- `E`/`O`/`M`: có thể phản ánh mức sử dụng Eden, old generation, metaspace ở cấu hình phân thế hệ thích hợp.

Không khẳng định JVM dùng collector nào chỉ từ một cột, và không cố áp nghĩa của generational collector lên mọi collector. Đối chiếu `java -version` của tiến trình, collector flags và mô tả option thực tế. Các dấu `-` hoặc `0` có thể biểu thị không có vùng/không hỗ trợ/counter chưa cập nhật tùy ngữ cảnh.

**Đọc các cột tích lũy:** nếu `YGC` tăng từ 12 lên 14 trong 5 giây, đó là hai sự kiện theo bộ đếm trong cửa sổ quan sát, không phải “14 lần mỗi giây”. Cần lấy hiệu hai mẫu và chia cho khoảng thời gian thực. `YGCT` cũng là thời gian tích lũy, không phải độ dài của GC vừa xảy ra.

### 7.2. Ưu điểm và giới hạn của sampling

- Hữu ích để xem **xu hướng ngắn hạn**, GC frequency, tỉ lệ dùng heap và dấu hiệu GC pause tăng.
- Không cho biết object nào giữ bộ nhớ lâu (cần heap dump), thread nào gây latency (cần dump/JFR) hoặc riêng từng request chậm (cần log/trace).
- Dữ liệu chịu ảnh hưởng thời điểm lấy mẫu; một pause ngắn có thể bị “lọt” qua khoảng 1 giây. Thu mẫu không thay thế latency histogram hay JFR event timeline.
- JVM phải có dữ liệu performance instrumentation khả dụng; cấu hình, quyền và môi trường có thể khiến `jstat` không lấy được counters.
- **Không parse cứng output văn bản trong automation.** Oracle JDK 17 cảnh báo định dạng `jstat` có thể thay đổi giữa các release.

### 7.3. jcmd có thay thế jstat không?

```bash
jcmd <pid> PerfCounter.print
jcmd <pid> GC.heap_info
```

`PerfCounter.print` có thể in performance counters của JVM, còn `GC.heap_info` cung cấp ảnh chụp heap tổng quan. **Không có một lời gọi `jcmd` mặc định tạo đúng cùng bảng `jstat -gcutil`, cùng cột, ý nghĩa và sampling interval.** Khi cần chuỗi thời gian lâu dài có nhãn service, dùng metrics instrumentation/monitoring phù hợp; khi cần giải thích từng event GC và tác động latency, cân nhắc GC logs/JFR.

**Chọn `jstat` khi:** cần quan sát số liệu GC/heap theo khoảng ngắn để thu hẹp sự cố, hoặc gặp runbook cũ có `jstat -gcutil` và muốn hiểu cách diễn giải đúng.

## 8. Bảng quy đổi lệnh: giống mục đích nhưng không hoàn toàn tương đương

| Nhu cầu | Câu lệnh công cụ chuyên biệt (JDK 17) | Lựa chọn `jcmd` | Kiểm tra khác biệt |
| --- | --- | --- | --- |
| Stack của các Java thread | `jstack -l <pid>` | `jcmd <pid> Thread.print -l` | Nội dung/format phụ thuộc runtime; đều là snapshot |
| Histogram heap | `jmap -histo <pid>` | `jcmd <pid> GC.class_histogram` | Bộ object và hành vi GC có thể khác theo option |
| Histogram chỉ live objects | `jmap -histo:live <pid>` | Đọc `help GC.class_histogram` và options thực tế | Không áp ánh xạ option 1:1 theo tên |
| Tạo heap dump | `jmap -dump:format=b,file=/tmp/h.hprof <pid>` | `jcmd <pid> GC.heap_dump /tmp/h.hprof` | Path thuộc target, overhead cao, semantics GC/default cần đọc kỹ |
| Flags | `jinfo -flags <pid>` | `jcmd <pid> VM.flags` | Phạm vi flags hiển thị không nhất thiết trùng |
| System properties | `jinfo -sysprops <pid>` | `jcmd <pid> VM.system_properties` | Dữ liệu nhạy cảm, cần redaction |
| Đọc một flag | `jinfo -flag <name> <pid>` | `jcmd <pid> VM.flags -all` nếu phù hợp | `VM.flags` là danh sách; cách lọc khác |
| Chuỗi thống kê GC | `jstat -gcutil -t <pid> 1000 5` | `PerfCounter.print`, `GC.heap_info`, metrics/JFR bổ sung | Không có cùng semantics/output/sampling mặc định |

**Điều chỉnh flag:** `jinfo -flag ...` hoặc `jcmd ... VM.set_flag` chỉ nên dùng khi có yêu cầu vận hành riêng, hiểu rõ tính “manageable” của flag và biết cách xác minh/hoàn nguyên. Bảng này chủ yếu dành cho **chẩn đoán và so sánh**, không cho phép tự động thay đổi runtime.

**Đối với core dump/JVM đã crash:** `jcmd` và các lệnh attach live process không phải công cụ đọc core dump. Trên HotSpot có **`jhsdb`** với các chế độ như `jstack`/`jmap`/`jinfo` cho trường hợp Serviceability Agent và core dump, tùy nền tảng/quyền/tính tương thích. Đây là nhánh xử lý **khác** với gửi diagnostic command tới JVM đang chạy; không dùng cú pháp `jstack <executable> <core>` của bài JDK 8 rồi áp nguyên xi cho JDK 17.

## 9. Thực hành Java 17+: quan sát một JVM nhỏ bằng cả bốn công cụ

### 9.1. Tạo ứng dụng mục tiêu

Tạo file **`ToolingTarget.java`**:

```java
public class ToolingTarget {
    public static void main(String[] args) throws InterruptedException {
        System.out.println("READY");
        Thread.sleep(50_000);
        System.out.println("DONE");
    }
}
```

Đây là **một chương trình Java hoàn chỉnh**, không dùng thư viện ngoài JDK. Biên dịch và chạy trong terminal 1:

```bash
javac --release 17 ToolingTarget.java
java ToolingTarget
```

**Stdout chính xác nếu chương trình chạy hết 50 giây bình thường:**

```text
READY
DONE
```

`READY` được in ngay và `DONE` sau khoảng 50 giây. Nếu chủ động dừng chương trình hoặc lỗi trước khi sleep xong thì sẽ không có `DONE`, đây là **lần chạy bị ngắt**.

### 9.2. Tìm đúng PID

Khi terminal 1 đã in `READY`, trong terminal 2 **cùng máy/namespace**:

```bash
jcmd -l
```

Tìm dòng ứng với main class `ToolingTarget`. Giả sử PID là `18432` (chỉ là con số minh họa), trước khi thực hiện thao tác khác cần xác minh process start time và owner bằng công cụ OS phù hợp.

### 9.3. Thử lệnh có tác động thấp trước

Thay `18432` bằng PID thực tế:

```bash
jcmd 18432 VM.version
jcmd 18432 VM.command_line
jcmd 18432 help Thread.print
jstack -l 18432
jinfo -flags 18432
jstat -gcutil -t 18432 1000 3
```

**Kỳ vọng:**

- `jstack -l` có thể thấy thread `main` ở `TIMED_WAITING` với `java.lang.Thread.sleep` trong lúc ứng dụng ngủ; vị trí và format thay đổi theo runtime.
- `jinfo -flags` in danh sách flags/JVM options; không có output cố định giống mọi máy.
- `jstat -gcutil -t ... 1000 3` thường in header và **3 dòng mẫu** theo nhịp khoảng 1 giây nếu VM có counter và công cụ hỗ trợ.
- `jcmd VM.version` xác nhận đúng runtime đích.

Để xem histogram trên **JVM demo nhỏ** sau khi cân nhắc impact:

```bash
jmap -histo 18432
```

Histogram là dữ liệu động; ứng dụng và class library có thể tải object ở thời điểm khác nhau, không kỳ vọng giá trị giống hệt nhau. Đừng dùng histogram để suy ra “leak” từ một snapshot. Trong bài này **không cần tạo heap dump hoặc chỉnh JVM flag**.

### 9.4. Tại sao output các công cụ không được ghi sẵn?

Ngoại trừ hai dòng stdout của `ToolingTarget`, mỗi lệnh chẩn đoán quan sát JVM tại **thời điểm thực**: PID, số thread, GC counter, flag, class histogram, runtime build và owner khác nhau giữa máy. Chép một “output mẫu” cố định dễ khiến người học nhầm là giá trị chuẩn. Kiểm tra chính là **đúng process, lệnh không lỗi và nội dung tương ứng với mục đích**.

### 9.5. Kiểm chứng phần thực hành

Mã `ToolingTarget.java` được biên dịch thành công ở chế độ `javac --release 17`. Trên một JVM OpenJDK chạy thử, các lệnh `jcmd VM.version`, `jcmd Thread.print -l`, `jstack -l`, `jinfo -flags`, `jstat -gcutil -t` và `jmap -histo` đều chạy thành công trên JVM demo. Bài cố ý không hứa trước giá trị output động hoặc hành vi đồng nhất giữa vendor.

## 10. Chọn công cụ theo tình huống

### 10.1. Request treo, thread pool hết slot

1. Dùng metrics/log khoanh cửa sổ request bị treo, xác nhận instance/PID.
2. `jstack -l <pid>` hoặc `jcmd <pid> Thread.print -l` để xem thread states và lock ownership.
3. Lấy vài snapshot có timestamp cách nhau hợp lý, đối chiếu thread liên tục ở cùng chỗ đợi.
4. Nếu cần timeline, JFR ghi monitor contention/thread park/CPU samples để kiểm chứng.
5. Không gọi heap dump chỉ vì một thread đang `BLOCKED`.

### 10.2. Heap used sau GC tăng đều, nghi cache giữ object

1. Dùng metrics, GC logs hoặc `jstat -gcutil -t` để xem xu hướng heap/GC và xác định giai đoạn tăng.
2. Nếu đã có đủ bằng chứng, dùng `jmap -histo` hoặc `GC.class_histogram` để tìm class/instance nổi bật, nhận thức rõ chi phí.
3. Khi cần trả lời **ai giữ object**, cân nhắc HPROF từ `GC.heap_dump`/`jmap -dump` với kế hoạch impact và dung lượng.
4. Phân tích dominator tree và GC roots trong MAT, so baseline và mô hình lưu trữ/cache.
5. Không kết luận “nhiều object” là leak nếu dữ liệu vẫn được thiết kế giữ lại.

### 10.3. GC pause tăng sau thay đổi cấu hình

1. `jinfo -flags` hoặc `jcmd VM.flags` để đọc thiết lập runtime; đừng suy từ lệnh `java -version` trong shell.
2. `jstat -gcutil` hoặc metrics để đối chiếu tần suất/thời gian GC trong cùng cửa sổ.
3. Dùng GC logs/JFR để xem loại event, pause duration và nguyên nhân theo timeline.
4. Nếu cần thay đổi flags, thực hiện theo thay đổi cấu hình được phép, có phương án hoàn nguyên và kiểm chứng.

### 10.4. CPU rất cao nhưng không có exception

1. `jstat` giúp loại trừ/khẳng định nghi vấn GC pressure, **không chứng minh** code CPU hotspot.
2. `jstack` cho điểm thời gian, `RUNNABLE` không trực tiếp đồng nghĩa consuming CPU.
3. JFR execution samples hoặc CPU profiler thích hợp hơn để định vị phương thức nóng.
4. Kết hợp process CPU/GC/traffic, tránh gọi heap dump chỉ vì CPU cao.

## 11. Những ranh giới vận hành phải kiểm tra

### 11.1. Định danh đúng JVM

PID chỉ có nghĩa trong một OS/PID namespace và có thể được tái sử dụng. Chọn đúng **host, pod/container, PID, start time, owner và command line** trước khi dùng lệnh chẩn đoán. Với nhiều replica, main class/JAR giống nhau chưa đủ.

### 11.2. Quyền và khả năng truy cập

Các lệnh attach vào JVM có thể yêu cầu cùng effective user/group và môi trường attach được phép. `-XX:+DisableAttachMechanism` có thể khiến `jcmd`/các công cụ attach không hoạt động. `jstat` còn phụ thuộc việc performance counters được phơi bày và đọc được. Một JVM không xuất hiện trong `jcmd -l` hay `jps` **không chứng minh** nó không tồn tại.

### 11.3. Container và runtime tối giản

Container có thể dùng PID nội bộ `1` trong khi host thấy PID khác. Một image JRE nhỏ hoặc custom runtime bằng `jlink` có thể không kèm `jstack`/`jmap`/`jinfo`/`jstat`. Khi công cụ thiếu, sử dụng JDK tương thích ở nơi chẩn đoán được ủy quyền, đồng thời tuân theo mapping namespace và chính sách attach; không ép nhập PID host vào command trong container mà chưa xác định.

### 11.4. Chi phí và thông tin nhạy cảm

| Thao tác | Rủi ro chính | Cách kiểm soát |
| --- | --- | --- |
| Lấy thread dump nhiều lần | Nhiều thread tạo output lớn, tăng overhead tại thời điểm chụp | Chỉ lấy đủ snapshot, có timestamp và giới hạn tần suất |
| Class histogram/heap dump | GC/pause, I/O, RAM/đĩa; HPROF có dữ liệu nhạy cảm | Đánh giá impact, dung lượng, nơi lưu, retention và quyền truy cập |
| In system properties/command line | Lộ credentials, connection strings, token | Không đăng nguyên output; redaction trước khi chia sẻ |
| Đổi manageable flag | Thay đổi hành vi runtime ngoài mục tiêu quan sát | Chỉ theo quy trình được ủy quyền; biết cách hoàn nguyên |
| Poll `jstat` không giới hạn count | Log quá lớn, command chạy dai, tăng tải và chi phí lưu | Dùng interval/count hữu hạn cho điều tra ngắn |
| Parse output experimental | Script hỏng âm thầm sau nâng cấp JDK | Đối chiếu tool/JDK version; ưu tiên API/metrics ổn định cho automation |

**Không đánh đồng “experimental” với “không nên bao giờ dùng”:** trên một JVM tương thích, chúng vẫn hữu ích trong sự cố. Nhưng **chi phí và tính đúng đắn của bằng chứng** quan trọng hơn sự quen tay với một lệnh cụ thể.

## 12. Các lỗi phổ biến và cách sửa

| Sai lầm | Hậu quả | Cách sửa |
| --- | --- | --- |
| “Experimental nghĩa là phải bật JVM experimental flag” | Thêm flag không liên quan, nhầm cơ chế JVM | Phân biệt command-line tool với `-XX:+UnlockExperimentalVMOptions` |
| “Unsupported nghĩa là JDK 17 không có công cụ” | Bỏ qua một nguồn bằng chứng đang khả dụng | Kiểm tra `-help`, runtime và man page đúng JDK |
| “jcmd thay thế 100% mọi lệnh jstat” | Kỳ vọng sai format/counters/interval | Dùng metrics/JFR cho timeline, `PerfCounter.print` khi phù hợp |
| “jstack RUNNABLE = thread đó ăn CPU” | Chẩn đoán CPU sai | Dùng CPU samples và đối chiếu CPU process |
| “jmap -histo cho biết ai giữ object” | Nhầm shallow histogram với retained graph | Phân tích HPROF, dominator/GC roots |
| “jinfo -flag luôn chỉ đọc” | Có thể làm đổi runtime flag | Phân biệt `-flag name` với `-flag +name` hoặc `name=value` |
| “GC count 20 nghĩa là 20 GC/giây” | Nhầm counter tích lũy với tốc độ | Tính hiệu giữa hai mẫu và thời gian thực |
| “Bỏ count cho jstat cũng chỉ lấy một lần” | Công cụ tiếp tục in dữ liệu | Chỉ định interval và count hữu hạn |
| “Đổi sang JDK mới nhưng parser jstat vẫn ổn” | Biến động header/columns làm sai metrics | Không parse cứng; kiểm thử theo version hoặc chọn API ổn định |
| “Heap dump nằm ở thư mục shell đang đứng” | Không tìm được file, hết quota container | Phân biệt redirect phía client với file do JVM đích tạo |
| “Không attach được thì JVM không chạy” | Bỏ sót incident | Kiểm tra quyền, namespace, PID lifecycle, vendor/JDK và perfdata |
| “Có công cụ nghĩa là có quyền dùng trên production” | Thao tác tốn tài nguyên hoặc lộ dữ liệu | Đọc help, impact, owner và quy trình vận hành trước |

## 13. Checklist dùng trong thực tế

- [ ] Xác minh đúng phiên JVM: **host/namespace, PID, process start time, owner, launch command**.
- [ ] Xác định câu hỏi: thread, heap/object, runtime config hay chuỗi thống kê GC.
- [ ] Đọc **help** và kiểm tra tool/JDK/vendor; ghi nhớ bốn công cụ được Oracle JDK 17 đánh dấu **experimental/unsupported**.
- [ ] Ưu tiên `jcmd` tương ứng khi cần và khả dụng; không áp đặt phép đổi tên một-một cho mọi options hoặc `jstat`.
- [ ] Kiểm tra impact, khả năng GC, kích thước dump, quyền ghi và vị trí file của JVM đích.
- [ ] Không đổi flag nếu mục tiêu chỉ là quan sát; không chia sẻ system properties/heap dump chưa làm sạch.
- [ ] Lấy đủ nhiều mẫu cho **xu hướng**, đủ ngữ cảnh cho **snapshot**, và đối chiếu ít nhất một nguồn khác.
- [ ] Ghi kết quả cùng timestamp, PID/start time, JDK version, command, tham số và trạng thái thành công/lỗi.
- [ ] Khi nâng cấp JDK, kiểm tra lại runbook và script phụ thuộc output tool experimental.

## 14. Tài liệu chính thức (JDK 17)

- [Oracle — jstack](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jstack.html): command in Java thread stack traces, `-l`, ghi chú experimental/unsupported.
- [Oracle — jmap](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jmap.html): class histogram, heap dump options, ghi chú experimental/unsupported.
- [Oracle — jinfo](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jinfo.html): đọc flags/properties và các hình thức cập nhật flag, ghi chú experimental/unsupported.
- [Oracle — jstat](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jstat.html): VM statistics, `-gcutil`, `-t`, interval/count, và cảnh báo parse output.
- [Oracle — jcmd](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jcmd.html): danh sách diagnostic commands, syntax, help và impact.
- [Oracle — java launcher](https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html): `-XX:+DisableAttachMechanism` và các nhóm VM startup options.

**Kết luận kỹ thuật:** `jstack` hỗ trợ xem **thread**, `jmap` hỗ trợ xem **heap**, `jinfo` hỗ trợ xem **cấu hình JVM**, còn `jstat` hỗ trợ theo dõi **statistics theo thời gian**. `jcmd` bao phủ nhiều mục đích nhưng không hoàn toàn thay thế cú pháp, dữ liệu và sampling của bốn công cụ. Hiểu rõ nhãn experimental/unsupported, kiểm tra phiên JDK và mức tác động trước khi sử dụng sẽ giúp bằng chứng đáng tin cậy hơn và quy trình chẩn đoán ít rủi ro hơn.