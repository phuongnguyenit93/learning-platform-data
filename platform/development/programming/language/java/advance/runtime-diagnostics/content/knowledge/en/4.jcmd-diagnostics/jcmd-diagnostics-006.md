# 4.6 Phân biệt lệnh quan sát với lệnh có thể gây GC, dump hoặc thay đổi trạng thái

## Mục tiêu học tập

`jcmd` là công cụ trong JDK dùng để gửi **diagnostic command** tới một JVM đang chạy. Không phải lệnh `jcmd` nào cũng chỉ “đọc thông tin”: một số lệnh có thể yêu cầu garbage collection (GC), thu thập dữ liệu trên toàn heap, tạo file lớn, bật/tắt ghi JFR, thay đổi cấu hình logging hoặc sửa một flag có thể điều chỉnh lúc chạy.

Bài học này giúp bạn:

- Phân biệt **ý định quan sát**, **chi phí thu thập bằng chứng** và **tác dụng làm thay đổi trạng thái** của một lệnh.
- Nhận diện các nhóm lệnh phổ biến trên **HotSpot/JDK 17+**: `VM.*`, `Thread.print`, `GC.*` và `JFR.*`.
- Biết vì sao nhãn **Impact: Low/Medium/High** trong phần trợ giúp không đồng nghĩa “read-only” hoặc “luôn an toàn khi production có tải”.
- Chọn chuỗi thao tác từ ít xâm lấn đến xâm lấn hơn, giữ bằng chứng ban đầu trước khi dùng lệnh có thể làm lệch hiện tượng.
- Ước lượng rủi ro pause, CPU, memory, I/O, ổ đĩa, lộ dữ liệu và thay đổi runtime, rồi ghi lại mọi can thiệp để diễn giải kết quả chẩn đoán.
- Thực hành với một JVM Java 17 do chính mình khởi chạy, tách rõ ví dụ quan sát với ví dụ chỉ nên thử trong môi trường lab.

## 1. Ba câu hỏi phải đặt ra trước mỗi lệnh

Một thao tác chẩn đoán có thể thuộc nhiều nhóm cùng lúc. Để đánh giá đúng, tách ba câu hỏi độc lập:

1. **Lệnh nhằm mục đích gì?** Đọc cấu hình, xem trạng thái, thu snapshot, tạo recording, hay chủ động làm JVM thực hiện một hành động?
2. **Lệnh tốn tài nguyên đến mức nào?** Công việc đó có buộc JVM đi qua nhiều thread/đối tượng, tạm dừng hoặc đồng bộ tại một điểm nhất quán, cấp phát bộ đệm, ghi file lớn hay tăng CPU/I/O không?
3. **Lệnh thay đổi điều gì?** Có gọi GC, làm thay đổi tập object sống, tạo/sửa file, bật sampling, xoay log, bật remote management agent hoặc thay một flag đang có hiệu lực không?

Ví dụ `VM.version` chủ yếu đọc thông tin phiên bản và có chi phí thấp. Ngược lại, `GC.heap_dump` tạo file HPROF dung lượng có thể rất lớn; trên JDK 17, mặc định lệnh này **yêu cầu full GC**, trừ khi chỉ định `-all`. Như vậy cùng được gọi là “diagnostic command” nhưng hai lệnh có tác động rất khác nhau.

Đặc biệt: lệnh được tài liệu gắn **Impact: Low** vẫn có thể **thay đổi trạng thái có chủ đích**. `VM.set_flag` được mô tả là lệnh đặt lại một VM flag, `VM.log` có thể đổi log output, `JFR.start` có thể bắt đầu một recording và `ManagementAgent.start` có thể mở remote management. “Low” là đánh giá **chi phí/ảnh hưởng vận hành dự kiến của việc thực hiện lệnh**, không phải cam kết “không ghi, không thay trạng thái”.

## 2. Bốn nhóm hành vi để phân loại lệnh

| Nhóm theo hành vi | Ví dụ JDK 17 | Bạn đang làm gì? | Điều vẫn phải cân nhắc |
| --- | --- | --- | --- |
| **A. Chủ yếu quan sát** | `VM.version`, `VM.uptime`, `VM.flags`, `VM.command_line`, `JFR.check` | Đọc metadata, flag, tình trạng recording | Attach có chi phí; output có thể chứa thông tin nhạy cảm |
| **B. Thu snapshot có chi phí** | `Thread.print`, `GC.heap_info`, `VM.native_memory summary`, `GC.class_histogram` | Đi qua thread/heap/native metadata để xuất thông tin | Có thể tạo pause, tải CPU, output lớn; histogram được tài liệu đánh giá Impact: High |
| **C. Tạo artifact hoặc hoạt động ghi dữ liệu** | `JFR.dump`, `GC.heap_dump`, `JFR.start` | Ghi JFR/HPROF hoặc bắt đầu thu thập liên tục | Đĩa, dữ liệu nhạy cảm, sampling overhead, GC và vòng đời recording |
| **D. Can thiệp trạng thái JVM** | `GC.run`, `VM.set_flag`, `VM.log` khi cấu hình, `JFR.stop`, `ManagementAgent.start` | Yêu cầu GC, đổi flag/log, kết thúc recording hoặc khởi động agent | Làm thay đổi điều kiện đo và hành vi tiến trình, cần phân biệt tác động mong muốn với side effect |

Đây là **phân loại theo mục đích vận hành**, không phải bốn nhóm loại trừ nhau. `GC.heap_dump` vừa là snapshot nặng vừa có thể kích hoạt GC; `JFR.dump` ghi file nhưng không mặc định dừng recording; `VM.log` có thể chỉ liệt kê cấu hình nếu dùng `list`, nhưng cũng có các tùy chọn thật sự thay đổi logging.

Để tránh nhầm, đặt hai nhãn riêng khi lập kế hoạch:

- **Impact do JVM mô tả:** Low/Medium/High theo output `jcmd <PID> help <COMMAND>` hoặc tài liệu của bản JDK.
- **Operational effect:** đọc thông tin / thu thập chi phí đáng kể / ghi artifact / thay đổi runtime state, cùng dự kiến CPU, pause, I/O và dữ liệu phát sinh.

Với cùng một lệnh, mức ảnh hưởng thực tế còn phụ thuộc **bản JDK/vendor, kích thước heap, số lượng threads/classes, workload, loại GC, tốc độ ổ đĩa và cấu hình đang bật**. Không biến một nhãn tài liệu thành một con số “pause tối đa” khi chưa có phép đo.

## 3. Nhận diện đúng JVM và xem trợ giúp trước khi thực thi

Ví dụ dưới đây giả định bạn có **JDK 17+ và JVM mục tiêu thuộc quyền quản lý hợp lệ**. Trên máy có nhiều JVM, luôn xác nhận đúng PID, lệnh khởi động và môi trường.

Trên hệ điều hành có hỗ trợ, bắt đầu bằng:

```bash
jcmd -l
jcmd <PID> help
jcmd <PID> help VM.version
jcmd <PID> help GC.heap_dump
jcmd <PID> help GC.run
```

Trong các ví dụ shell, `<PID>` là **ký hiệu cần thay bằng PID số thực**, không phải chuỗi gõ nguyên văn. Cú pháp chính xác và mức Impact cần xem trên **JVM mục tiêu**; các lệnh có thể không khả dụng hoặc khác option giữa các JDK.

Những điều cần biết trước khi attach:

- `jcmd` gửi yêu cầu tới JVM đang chạy trên cùng máy/không gian attach phù hợp; thông thường cần effective user/group phù hợp với tiến trình mục tiêu.
- `jcmd -l` có thể không liệt kê JVM nằm trong container/namespace khác. Khi đó phải xác định PID bằng công cụ quản lý container/process thích hợp; không suy ra JVM không tồn tại.
- `jcmd 0 <COMMAND>` có khả năng gửi yêu cầu tới **nhiều Java process**, nên không dùng cho thao tác có side effect; chỉ làm việc với **PID đã xác minh**.
- JDK tools có thể không có trong runtime image tối giản; cơ chế attach có thể bị vô hiệu hóa và quyền truy cập có thể hạn chế. Không tự suy từ một lỗi attach thành “JVM đang treo”.
- Ghi **PID, container/pod, start time, JVM vendor/version, thời gian và mục đích**; PID có thể được tái sử dụng sau restart nên cần gắn với identity của tiến trình.

`jcmd <PID> help <COMMAND>` hiển thị mô tả, quyền yêu cầu, option và nhãn Impact đối với JVM hỗ trợ command đó. Luôn xem **option cụ thể** vì cùng tên lệnh nhưng hai chế độ có thể khác hành vi đáng kể.

## 4. Các lệnh chủ yếu quan sát: bắt đầu bằng gì?

| Lệnh | Thông tin thu được | Mức Impact trong tài liệu JDK 17 | Chú ý |
| --- | --- | --- | --- |
| `VM.version` | Phiên bản JVM/VM | Low | Phù hợp bước xác nhận target |
| `VM.uptime` | Thời gian JVM chạy | Low | Giúp nhận ra process vừa restart |
| `VM.command_line` | Command line dùng để khởi chạy JVM | Low | Có thể hiện argument/đường dẫn nhạy cảm |
| `VM.flags` | Giá trị flags đang sử dụng | Low | Đọc flags, không thay flags |
| `VM.system_properties` | Java system properties | Low | Có thể chứa token, URL kết nối, dữ liệu cấu hình riêng |
| `JFR.check` | Danh sách/thông tin recording đang chạy | Low | Không tự bắt đầu recording |
| `VM.log list` | Cấu hình logging hiện có | Lệnh `VM.log` được ghi Low | `list` là thao tác xem; các option khác có thể sửa logging |

Ví dụ **chỉ quan sát** một JVM đã xác nhận:

```bash
jcmd <PID> VM.version
jcmd <PID> VM.uptime
jcmd <PID> VM.command_line
jcmd <PID> VM.flags
jcmd <PID> JFR.check
jcmd <PID> VM.log list
```

Không cần chạy tất cả mỗi khi điều tra. Chọn đủ dữ liệu cho giả thuyết. Nếu vấn đề là độ trễ tăng sau restart, `VM.uptime`, `VM.flags` và thông tin recording thường hữu ích hơn việc lập tức tạo heap dump.

**“Quan sát” không có nghĩa “miễn phí tuyệt đối”.** Attach cần trao đổi với tiến trình, tạo output và có thể cạnh tranh tài nguyên. Hãy tránh polling dày và thu output quá nhiều khi ứng dụng đã quá tải. Đồng thời bảo vệ kết quả `VM.system_properties` và `VM.command_line` trước khi chuyển cho người khác.

## 5. Snapshot quan sát nhưng vẫn có chi phí

### 5.1 `Thread.print`: không sửa cấu hình, nhưng có thể ảnh hưởng thời gian

```bash
jcmd <PID> Thread.print
jcmd <PID> Thread.print -l
```

`Thread.print` xuất stack trace của các luồng Java. `-l` bổ sung thông tin lock của `java.util.concurrent` khi được hỗ trợ. Trên JDK 17, tài liệu gắn **Impact: Medium**, tùy số lượng luồng.

Tại sao phải cân nhắc?

- Hệ thống có nhiều thread và stack sâu có thể tạo output rất lớn, tốn thời gian duyệt/thu dữ liệu.
- Việc chụp thông tin nhất quán có thể cần đồng bộ và tạo độ trễ; không hứa “không có safepoint/pause”.
- Một thread dump chỉ là ảnh chụp tại một thời điểm. `WAITING` không tự chứng minh deadlock; phải xét lock owner, call path, tình trạng tiến trình và nhiều mẫu khi cần.
- Nếu cần nhiều mẫu cách nhau theo thời gian, đặt nhịp lấy mẫu có chủ đích và ghi khoảng cách; không dùng loop dày không giới hạn trên production.

Ví dụ nếu nhiều request bị treo, thử `Thread.print` với thời gian lấy mẫu đã định có thể phù hợp hơn heap dump. Tuy nhiên chính thao tác lấy dump có thể làm latency nhích lên, cần đánh dấu timestamp trong biểu đồ.

### 5.2 `GC.heap_info`: đọc thông tin heap, không phải kích hoạt GC bằng chủ đích

```bash
jcmd <PID> GC.heap_info
```

Lệnh cung cấp thông tin tổng quát về heap; tài liệu JDK 17 xếp **Impact: Medium**. Nó không được thiết kế như lệnh “bắt GC chạy ngay”, nhưng vẫn có chi phí chẩn đoán.

Không nhầm `GC.heap_info` với `GC.class_histogram`:

- `GC.heap_info` trả thông tin cấu trúc/tình trạng heap tổng quát.
- `GC.class_histogram` duyệt object để thống kê số lượng/bytes theo class; tài liệu đánh giá **Impact: High**, tùy kích thước và nội dung heap. Trên một số đường thực thi, việc thống kê có thể đi cùng yêu cầu GC hoặc một pha xử lý tốn kém, cần xem tùy chọn và thực nghiệm trên JDK mục tiêu.

Nếu chỉ cần biết heap đang cấu hình/commit bao nhiêu, không nên bắt đầu bằng histogram toàn heap.

### 5.3 `VM.native_memory summary`: chỉ có giá trị nếu NMT sẵn sàng

```bash
jcmd <PID> VM.native_memory summary
```

Tài liệu JDK 17 xếp `VM.native_memory` **Impact: Medium**. Việc dùng báo cáo NMT đòi hỏi JVM đã bật Native Memory Tracking ở thời điểm khởi động phù hợp; nếu chưa bật, lệnh có thể báo không có số liệu NMT.

Phân biệt các option:

- `summary` / `detail`: đọc báo cáo từ hệ thống tracking.
- `baseline`: đặt **mốc so sánh nội bộ** cho NMT, do đó đây là một thay đổi trạng thái chẩn đoán.
- `summary.diff` / `detail.diff`: so sánh với baseline đã thiết lập.
- `shutdown`: thay đổi trạng thái theo dõi NMT; không phải cách đọc số liệu.

NMT theo dõi phần bộ nhớ nội bộ JVM mà nó hỗ trợ, không bao quát mọi allocation do thư viện native bên ngoài. Một báo cáo “NMT thấp” không chứng minh RSS hoặc memory cgroup thấp.

## 6. Nhóm cần cảnh giác: có thể yêu cầu GC

### 6.1 `GC.run` thực sự yêu cầu điều gì?

```bash
jcmd <PID> GC.run
```

Theo tài liệu `jcmd` JDK 17, lệnh này gọi `java.lang.System.gc()` và được xếp **Impact: Medium** tùy heap/nội dung. Đây là yêu cầu rõ ràng để JVM thực hiện cơ chế GC theo ngữ nghĩa `System.gc()`.

Điều đó **không đồng nghĩa** lúc nào cũng có một full stop-the-world GC giống nhau:

- Với JVM flags như `-XX:+DisableExplicitGC`, yêu cầu explicit GC có thể bị bỏ qua.
- Các collector có thể xử lý `System.gc()` theo cơ chế khác nhau tùy JDK/flags; pause, concurrency và lượng object thu hồi không phải hằng số.
- Ngay cả khi không thu hồi nhiều object, quá trình GC có thể dùng CPU, làm thay đổi heap occupancy, allocation/pause metrics và tình trạng cache hoặc hiệu ứng gián tiếp.
- Nếu đang điều tra “heap tăng trước GC”, một lần `GC.run` có thể **xóa dấu vết cần quan sát** và làm khó so sánh trạng thái tự nhiên trước/sau.

Do đó không xem `GC.run` là “lệnh lấy báo cáo GC”. Khi cần nghiên cứu retention sau explicit GC trong lab, ghi rõ đây là **phép can thiệp có chủ đích**, không phải snapshot trung tính của trạng thái trước điều tra.

### 6.2 `GC.class_histogram`: nhìn như báo cáo nhưng rất nặng

```bash
jcmd <PID> GC.class_histogram
jcmd <PID> GC.class_histogram -all
```

- Histogram cho số lượng object và bytes theo class, hữu ích để nhận diện loại object chiếm nhiều heap.
- Theo tài liệu JDK 17, **Impact: High**; nó có thể gây chi phí đáng kể khi quét heap.
- `-all` yêu cầu xét **cả object unreachable**, làm thay đổi *tập object được đưa vào thống kê*. Dùng option đó không biến histogram thành một phép đo nhẹ hoặc hoàn toàn không xâm lấn.
- Đối với HotSpot, quá trình thu histogram mặc định có thể liên quan xử lý/GC để phản ánh object còn sống; điều cần xác minh là hành vi trên **JDK/collector/option cụ thể**, không tự giả định mỗi lần đều có một “full GC 100%”.
- Histogram là thống kê theo class, chưa chỉ ra **đường giữ tham chiếu (retaining path)** hay nguồn allocation, cũng không đủ một mình để khẳng định memory leak.

Nếu nghi ngờ leak, trước tiên xem chuỗi heap/GC sau GC theo thời gian, số liệu allocation và các dấu hiệu restart/OOM. Chỉ nâng lên histogram hoặc dump khi một phép đo nhẹ hơn chưa giải đáp câu hỏi.

### 6.3 Vì sao snapshot sau GC có thể làm sai câu chuyện sự cố?

Giả sử heap trước chẩn đoán đang 85% mức `-Xmx` và độ trễ tăng. Bạn gọi `GC.run`, sau đó heap used giảm và latency trở lại bình thường. Điều đó **không chứng minh** nguyên nhân gốc là “Java cần GC thường xuyên hơn”: bạn vừa làm thay đổi trạng thái, timing, tập object còn sống và có thể cả tải hệ thống.

Ghi rõ trong timeline:

```text
14:00:00  p99 tăng, heap used cao, không có explicit GC
14:01:00  thu GC metrics / flags / log hiện trạng
14:02:00  người vận hành gọi jcmd <PID> GC.run
14:02:02  heap used giảm sau hoạt động GC (nếu có)
14:03:00  p99 được đo lại
```

Đây là tình huống **minh họa**, không phải bằng chứng của một JVM thực. Mọi số đo **sau 14:02** phải được gắn nhãn “sau can thiệp”, không gộp với baseline tự nhiên như thể môi trường chưa thay đổi.

## 7. `GC.heap_dump`: vừa có thể GC, vừa tạo file lớn

Cú pháp phổ biến với JDK 17:

```bash
jcmd <PID> GC.heap_dump /path/to/diagnostics/app-heap.hprof
```

Lệnh ghi heap dump định dạng HPROF. Tài liệu JDK 17 nêu rõ **Impact: High** và **mặc định yêu cầu full GC**, trừ khi chỉ định `-all`. Option `-all` dùng để dump cả object unreachable; thay đổi tập dữ liệu và không đảm bảo dump sẽ nhẹ, không pause hoặc không ảnh hưởng tiến trình.

Đánh giá bốn nhóm rủi ro:

1. **Tác động đến JVM:** yêu cầu GC, quá trình chụp heap và ghi dữ liệu có thể gây pause/CPU overhead, nhất là với heap lớn và ứng dụng nhạy latency.
2. **Dung lượng/I/O:** HPROF có thể rất lớn, làm nghẽn disk bandwidth hoặc đầy ổ/container ephemeral storage; áp lực I/O có thể ảnh hưởng các request bình thường.
3. **Dữ liệu nhạy cảm:** dump có thể chứa string, session, token, thông tin khách hàng, buffer và nội dung object thực tế. Cần quyền đọc phù hợp, nơi lưu bảo vệ và quy trình dọn file.
4. **Diễn giải số liệu:** nếu dump mặc định yêu cầu full GC, heap sau dump **không còn phản ánh nguyên vẹn trạng thái trước hành động**. Nếu sử dụng `-all`, cũng không so trực tiếp tập object với một dump chỉ tính reachable object.

Một dump tạo thành công không xác nhận nguyên nhân memory leak. Phải phân tích object dominators, retaining paths, số lượng đối tượng, đặc điểm giữ tham chiếu và so với workload/lifecycle.

**Dữ liệu cần ghi trước khi dump:** lý do cần dump, PID/build, heap size, memory/container headroom, dung lượng đĩa khả dụng, đường dẫn file tuyệt đối, thời gian chạy dự kiến, metric baseline, nơi lưu và ai có quyền xem.

**Lệnh chỉ minh họa cho máy lab** với tiến trình thử nghiệm do bạn quản lý:

```bash
# Ví dụ: thay <PID> bằng PID lab thật, chọn đường dẫn tuyệt đối có dung lượng.
jcmd <PID> GC.heap_dump /tmp/jcmd-lab-heap.hprof
```

Trên Windows, dùng đường dẫn phù hợp với JVM đích. File được tạo theo ngữ cảnh hệ thống tệp của tiến trình đích; với container, đường dẫn nhìn từ máy host và trong container có thể khác nhau. Không dựa vào đường dẫn tương đối khi cần truy xuất artifact chắc chắn.

## 8. JFR: vừa quan sát vừa thay đổi quá trình thu thập

Java Flight Recorder (JFR) hữu ích để ghi CPU, allocation, GC, threads, locks và nhiều sự kiện runtime với overhead phụ thuộc cấu hình. Các lệnh `JFR.*` cần phân biệt chính xác:

| Lệnh | Ý nghĩa | Tác dụng phụ cần ghi |
| --- | --- | --- |
| `JFR.check` | Xem recording hiện có | Chủ yếu đọc trạng thái; Impact Low |
| `JFR.start` | Bắt đầu recording mới | Đổi trạng thái JVM; tạo sự kiện/buffer, có thể ghi disk; profile/setting ảnh hưởng overhead |
| `JFR.dump` | Ghi dữ liệu recording ra file | I/O và artifact; theo JDK 17, recording **tiếp tục chạy** sau dump |
| `JFR.stop` | Kết thúc recording | Đổi trạng thái; tùy `filename`, dữ liệu có thể được ghi hoặc bỏ |
| `JFR.configure` | Xem hoặc sửa cấu hình JFR | Không mặc định “read-only”: không có option có thể hiển thị settings, có option có thể sửa |

Ví dụ chỉ xem:

```bash
jcmd <PID> JFR.check
```

Ví dụ **thao tác có chủ đích trong môi trường lab**:

```bash
jcmd <PID> JFR.start name=lab-profile settings=profile duration=30s filename=/tmp/lab-profile.jfr
jcmd <PID> JFR.check
```

Việc `JFR.start` được tài liệu đánh giá Impact Low **không** chứng minh mọi recording ít overhead. Trong JDK có các cấu hình `default` và `profile`; `profile` thu nhiều dữ liệu hơn và có overhead cao hơn, phù hợp cửa sổ ngắn khi cần. Các event như đường tới GC roots (`path-to-gc-root`) có thể tốn thời gian đáng kể; cần kiểm tra option, workload, file size và resource budget trước khi bật.

`JFR.dump name=lab-profile filename=...` tạo file nhưng **không tự dừng recording** trên JDK 17. `JFR.stop name=lab-profile` mới kết thúc recording; nếu không chỉ định đường ghi, dữ liệu có thể bị bỏ theo ngữ nghĩa lệnh. Không dùng `JFR.stop` chỉ để “xem JFR có chạy không”.

Với recording đã được bật từ trước bởi đội vận hành, tránh tự khởi động/stop một recording trùng tên hoặc điều chỉnh config. Đầu tiên xác minh recording ID/name, owner, phạm vi và mục tiêu thu thập.

## 9. `VM.log`, `VM.set_flag` và công cụ đổi trạng thái khác

### 9.1 `VM.log`: đọc hoặc sửa logging tùy option

Trên JDK 17, `VM.log` có thể liệt kê, bật/tắt, cấu hình output hoặc rotate logs.

```bash
jcmd <PID> VM.log list
```

Lệnh trên dùng `list` để **xem** cấu hình hiện tại. Ngược lại, những lệnh có các tham số cấu hình `output`, `what`, `decorators`, `disable` hay `rotate` có thể **thay đổi logging hoặc file log**.

Chẳng hạn việc tăng mức GC logging từ `info` sang `debug` làm tăng số sự kiện và I/O; nếu log lên stdout của container, nó có thể ảnh hưởng collector và đường thu log của hệ thống. Tắt hoặc xoay log cũng có thể phá hỏng dữ liệu đang cần trong lúc điều tra. Vì vậy ghi trước **cấu hình gốc**, tác động ước lượng, thời điểm bắt đầu, thời điểm khôi phục và ai sẽ kiểm chứng.

Tài liệu gắn Impact Low cho lệnh `VM.log`, nhưng điều đó không loại bỏ tác dụng phụ do **lượng log sinh ra sau khi thay đổi**.

### 9.2 `VM.set_flag`: mức Impact Low, nhưng không phải thao tác đọc

`VM.flags` **đọc** giá trị flags. `VM.set_flag` **đặt** giá trị một flag có thể thay đổi động và được JVM cho phép. Cú pháp theo trợ giúp mục tiêu có dạng:

```bash
jcmd <PID> help VM.set_flag
```

Không dùng `VM.set_flag` làm bước kiểm tra “cho biết giá trị flag”: chọn `VM.flags` hoặc `VM.command_line`. Không phải mọi flag đều chỉnh sửa được tại runtime; một số flag cần JVM restart mới có hiệu lực hoặc bị chặn bởi VM. Nếu thay flag, phải xác nhận giá trị ban đầu, cơ chế ảnh hưởng, giá trị mới có hiệu lực thực hay không và cách khôi phục.

Lệnh `Compiler.directives_add/remove/clear` là một ví dụ tương tự: nhãn Impact Low trong documentation nhưng **thay đổi directives**. Không đánh đồng các lệnh trong một nhóm chỉ vì tên có chứa “print” hoặc document ghi “Low”.

### 9.3 Management agent và native agent: tác động ngoài hiệu năng

- `ManagementAgent.status` là cách đọc trạng thái agent.
- `ManagementAgent.start` có thể bắt đầu **remote management agent**, làm thay đổi bề mặt kết nối, cấu hình quản trị, port và kiểm soát truy cập. Nhãn Impact Low không có nghĩa bỏ qua chính sách bảo mật.
- `JVMTI.agent_load` tải native agent vào JVM. Đây là hành động thay đổi code/instrumentation đang có hiệu lực, không phải lệnh đọc trạng thái.

Đừng tùy tiện kích hoạt agent chỉ vì `help` hiển thị Impact Low. Các thao tác này có thể thay đổi hành vi hệ thống lâu dài hơn bản thân thời gian chạy lệnh.

## 10. Bảng tra quyết định cho những lệnh `jcmd` thường gặp

Bảng sau phân biệt **Impact theo tài liệu Oracle JDK 17** với **tác dụng thực tế cần quản lý**. Tùy vendor/JDK khác, hãy ưu tiên trợ giúp của JVM mục tiêu.

| Command | Impact tài liệu JDK 17 | Thuộc tính vận hành | Lưu ý khi dùng |
| --- | --- | --- | --- |
| `VM.version`, `VM.uptime` | Low | Chủ yếu đọc | Xác nhận đúng JVM/PID |
| `VM.command_line`, `VM.flags` | Low | Chủ yếu đọc | Có thể lộ tham số nhạy cảm |
| `VM.system_properties` | Low | Chủ yếu đọc | Không chia sẻ nguyên trạng nếu có secrets |
| `JFR.check` | Low | Đọc trạng thái recording | Không thay thế `JFR.start` |
| `VM.log list` | Low (nhóm `VM.log`) | Đọc logging config | Phân biệt với option sửa config |
| `GC.heap_info` | Medium | Đọc thông tin heap | Vẫn có chi phí, không yêu cầu GC chủ động |
| `Thread.print` | Medium | Thu thread snapshot | Chi phí phụ thuộc số thread; có thể tạo độ trễ |
| `VM.native_memory summary` | Medium | Đọc NMT | NMT phải bật; `baseline` khác `summary` |
| `GC.class_histogram` | High | Thu thống kê trên heap | Có thể rất nặng; `-all` không làm “an toàn tuyệt đối” |
| `GC.run` | Medium | Yêu cầu `System.gc()` | Có thể làm thay đổi heap/latency, phụ thuộc GC/flags |
| `GC.heap_dump` | High | Dump + yêu cầu full GC mặc định | File lớn, dữ liệu nhạy cảm, I/O/pause |
| `JFR.start` | Low | **Bắt đầu recording** | Overhead phụ thuộc settings/duration |
| `JFR.dump` | Low | **Ghi file**, recording vẫn chạy | File output, I/O, có thể có tùy chọn tốn kém |
| `JFR.stop` | Low | **Kết thúc recording** | Không phải lệnh đọc |
| `VM.log` cấu hình | Low | **Đổi log output/level** | Thay đổi lượng log và I/O |
| `VM.set_flag` | Low | **Sửa flag động** | Chỉ những flag được phép; lưu trạng thái ban đầu |
| `ManagementAgent.start` | Low | **Bật agent quản trị** | Có thể thay đổi bề mặt mạng/bảo mật |
| `JVMTI.agent_load` | Low | **Tải native agent** | Thay đổi instrumentation/cơ chế chạy |

Không tự động gán `GC.heap_dump` vào nhóm “read-only” chỉ vì nó tạo ra bằng chứng. Đồng thời, không mặc định một lệnh chủ yếu đọc luôn an toàn ở mọi tần suất; cách **tự động hóa lặp lại** một lệnh có thể gây tác động lớn hơn một lần chạy.

## 11. Quy trình lựa chọn từ ít xâm lấn tới xâm lấn hơn

### Bước 1 — Xác định triệu chứng và bằng chứng cần có

Ví dụ: “p99 latency tăng sau deploy”, “heap sau GC liên tục tăng”, “request treo dù CPU thấp”. Đặt câu hỏi cụ thể: muốn biết version/flags, thread state, heap footprint, allocation path hay object retaining path?

### Bước 2 — Thu bằng chứng thụ động trước

Ghi timestamp, build/JDK/flags, request traces, GC logs đã có, CPU/memory/queue, trước khi attach. Với `jcmd`, khởi đầu từ `VM.version`, `VM.uptime`, `VM.command_line`, `VM.flags`, `JFR.check` nếu thích hợp.

### Bước 3 — Xem `help`, ước lượng chi phí theo JVM và workload

Không chỉ đọc tên command: hỏi nó duyệt bao nhiêu object/thread, có yêu cầu GC, có ghi file/đổi flag/agent/recording không; capacity đĩa, quyền truy cập, môi trường container, hệ quả với request latency. Ghi bản JDK và option cụ thể.

### Bước 4 — Thu snapshot mức vừa nếu đủ

Với hang/lock: cân nhắc `Thread.print` tại vài mốc; với heap sizing: `GC.heap_info`; với native memory: `VM.native_memory summary` nếu NMT bật; với performance đa chiều: JFR cấu hình phù hợp và thời lượng giới hạn.

Theo dõi sự khác biệt trước/sau thao tác: nếu chính lệnh làm CPU/GC/latency tăng, phải đánh dấu artifact/snapshot đó trong timeline.

### Bước 5 — Chỉ escalates khi câu hỏi đòi hỏi

Dùng `GC.class_histogram` hoặc `GC.heap_dump` khi cần thống kê object/retaining paths mà công cụ nhẹ hơn chưa trả lời được. Dùng `GC.run` chỉ khi phép điều tra có chủ đích cần explicit GC. Dùng `VM.set_flag`/`VM.log` config hoặc JFR recording khi mục tiêu thật sự đòi thay đổi runtime.

Chọn thời điểm, chủ sở hữu, ngân sách CPU/disk và cách phục hồi theo tình trạng hệ thống. Không đổi cấu hình và chạy histogram/dump cùng lúc rồi gán mọi thay đổi metric cho một nguyên nhân.

### Bước 6 — Gắn nhãn “trước can thiệp / sau can thiệp”

Một báo cáo tốt không gộp các cửa sổ:

```text
T0: p99 tăng, trước mọi thao tác jcmd
T1: VM.flags + GC.heap_info (quan sát)
T2: Thread.print -l (snapshot có chi phí)
T3: GC.run (can thiệp explicit GC)
T4: đo heap/GC/latency sau can thiệp
T5: GC.heap_dump (dump + có thể full GC theo option)
```

Các mốc chỉ minh họa. Chỉ số sau T3 phải được diễn giải là **đo sau can thiệp**, và snapshot sau T5 không phải “bằng chứng nguyên vẹn của T0”.

### Bước 7 — Đối chiếu outcome và dọn artifact

Đánh giá lời giải thích từ logs/JFR/thread/GC theo timestamp và workload. Kiểm tra nơi lưu HPROF/JFR, quyền truy cập, vòng đời file, recording còn chạy hay không, cấu hình logging/flags có cần khôi phục không. Với dump hoặc recording có dữ liệu ứng dụng, cần kiểm soát truy cập và thời hạn lưu.

## 12. Lab Java 17+ không đụng vào JVM production

Ví dụ này tạo **một tiến trình Java thử nghiệm** để bạn quan sát bằng `jcmd`, không yêu cầu tạo heap dump hay kích hoạt explicit GC. Nó cũng có chế độ `fixture` trả stdout cố định giúp người học kiểm tra phân biệt hành vi.

Tạo tệp `JcmdCommandKindsDemo.java`:

```java
public class JcmdCommandKindsDemo {
    public static void main(String[] args) throws InterruptedException {
        if (args.length == 1 && args[0].equals("fixture")) {
            System.out.println("VM.version: inspect version");
            System.out.println("Thread.print: inspect threads with cost");
            System.out.println("GC.run: request System.gc()");
            System.out.println("GC.heap_dump: write HPROF, request full GC by default");
            System.out.println("VM.set_flag: change manageable VM flag");
            return;
        }

        if (args.length == 1 && args[0].equals("target")) {
            System.out.println("PID=" + ProcessHandle.current().pid());
            System.out.println("READY");
            Thread.sleep(120_000L);
            System.out.println("DONE");
            return;
        }

        System.out.println("Usage: java JcmdCommandKindsDemo fixture|target");
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```bash
javac JcmdCommandKindsDemo.java
java JcmdCommandKindsDemo fixture
```

Stdout **chính xác** của chế độ `fixture`:

```text
VM.version: inspect version
Thread.print: inspect threads with cost
GC.run: request System.gc()
GC.heap_dump: write HPROF, request full GC by default
VM.set_flag: change manageable VM flag
```

Chế độ trên **không gửi bất kỳ command `jcmd` nào**; nó chỉ in một bảng nhắc nhớ, vì thế stdout ổn định. Để quan sát JVM đang chạy:

1. Mở terminal A, chạy `java JcmdCommandKindsDemo target`. Chương trình in PID thực và `READY`, rồi ngủ khoảng 120 giây.
2. Trong thời gian target còn chạy, mở terminal B, thay `<PID>` bằng số PID đã in, dùng `jcmd <PID> help`, `VM.version`, `VM.flags`, `Thread.print` hoặc `GC.heap_info`.
3. Ghi timestamp, thời gian phản hồi, kích thước output và tình trạng tiến trình. Nếu quá 120 giây, target kết thúc với `DONE`; muốn thử lại thì khởi động lần nữa và dùng **PID mới**.

Các lệnh ở terminal B:

```bash
jcmd <PID> help
jcmd <PID> VM.version
jcmd <PID> VM.flags
jcmd <PID> GC.heap_info
jcmd <PID> Thread.print
```

**Không có stdout cố định** cho chế độ `target` hoặc `jcmd`: PID, version, các flags, heap và stack trace phụ thuộc máy/JDK/trạng thái. Một dòng `READY` chỉ cho biết target đã bắt đầu ngủ; không chứng minh `jcmd` có thể attach từ mọi namespace/quyền.

**Bài mở rộng trong lab riêng, không phải bước bắt buộc:** thử tạo JFR ngắn rồi xem file; hoặc thử dump trên **tiến trình dùng heap nhỏ** với ổ đĩa đủ chỗ. Hãy đo latency/GC behavior và phân biệt file output với thay đổi runtime. Không làm các thao tác này trên JVM khác chỉ để học lệnh.

## 13. Ba tình huống ứng dụng

### Tình huống A — Dịch vụ latency cao, nghi do thread contention

**Câu hỏi:** luồng đang đợi lock hay chờ downstream? Một cách tiếp cận có giá trị là đọc metric/error/trace, sau đó lấy `Thread.print` có thời điểm rõ, có thể thêm `-l` nếu cần lock details.

**Không cần ngay:** `GC.heap_dump`, `GC.run` hoặc `VM.set_flag`. Chúng không trực tiếp cho biết queueing/lock cause và còn có thể làm lệch latency.

**Giới hạn:** một thread dump không thể chứng minh deadlock hoặc nơi nghẽn duy nhất. Cần nhiều mẫu/timestamp, cơ chế chờ và sự tương ứng với request.

### Tình huống B — Heap sau GC tăng dần, nghi memory leak

**Câu hỏi:** object nào được giữ lại, thuộc class nào, retaining path là gì? Bắt đầu với heap/GC logs, JFR/allocation metrics sẵn có, `GC.heap_info` và NMT nếu nghi native memory. Khi chưa đủ, cân nhắc histogram hoặc dump có kiểm soát.

**Rủi ro:** histogram có Impact High; heap dump có thể yêu cầu full GC, tạo HPROF lớn và chứa thông tin nhạy cảm. Nếu lấy dump sau explicit GC, phải ghi rõ baseline đã bị thay đổi.

**Giới hạn:** nhiều object cùng class chưa chứng minh leak; cần growth theo thời gian, retained references và vòng đời nghiệp vụ.

### Tình huống C — Chẩn đoán bằng JFR trong production

**Câu hỏi:** có recording nào đang chạy và đủ sự kiện cần phân tích chưa? Trước tiên `JFR.check`; nếu chưa có, chọn settings và duration phù hợp rồi mới cân nhắc `JFR.start`. Một recording `profile` trong 1 phút có thể có overhead cao hơn `default` chạy dài.

**Rủi ro:** JFR buffer, event sampling, file output và `path-to-gc-root` có chi phí; `JFR.dump` ghi file, `JFR.stop` dừng recording. Bật/tắt không đồng nghĩa chỉ quan sát.

**Giới hạn:** JFR sampling có thể bỏ sót event, thời gian ghi không trùng cửa sổ lỗi, hoặc cấu hình event không đủ để xác nhận nguyên nhân. Không nói “JFR không thấy gì nên lỗi không tồn tại”.

## 14. Checklist trước khi chạy lệnh chẩn đoán có side effect

Trả lời các câu hỏi sau **trước khi thao tác thật**:

- Có đúng **PID, container, JVM version/vendor và workload** mà mình được phép kiểm tra?
- Đã ghi symptom và baseline **trước can thiệp** chưa?
- Mục tiêu thông tin có cần đến `GC.run`, histogram, heap dump, recording mới hay thay flag không?
- Đã xem `jcmd <PID> help <COMMAND>` và hiểu từng option `-all`, `name`, `filename`, `settings`, `list` hoặc `disable` chưa?
- Dự kiến pause/CPU/I/O và lượng dữ liệu output ở quy mô heap/thread thực tế thế nào?
- Nếu tạo HPROF/JFR/log, đường dẫn có hợp lệ với tiến trình, còn đủ đĩa và quyền truy cập, đồng thời có quy trình lưu/dọn dữ liệu nhạy cảm không?
- Lệnh có thay đổi trạng thái GC, flags, logging, JFR, NMT baseline hoặc management/agent không? Cần ai theo dõi và khôi phục?
- Đã đặt timestamp, request/load correlation, ngưỡng dừng và cách phát hiện tác động phụ?
- Báo cáo sau cùng có ghi đủ command/flags/option/thời điểm, output, tác động quan sát và giới hạn kết luận không?

## 15. Những sai lầm thường gặp

1. **Thấy “Impact: Low” rồi coi command là read-only.** `VM.set_flag`, `JFR.start` và `VM.log` có thể sửa trạng thái dù nhãn Impact thấp.
2. **Thấy “snapshot” rồi coi không ảnh hưởng JVM.** `Thread.print` và histogram có chi phí phụ thuộc quy mô thực.
3. **Dùng `GC.run` làm công cụ xem GC.** Nó yêu cầu `System.gc()`; behavior tùy collector/flags, có thể phá baseline.
4. **Lấy dump trước khi đo heap/GC hiện trạng.** Dump mặc định có thể yêu cầu full GC, làm thay đổi tập object trước khi phân tích.
5. **Dùng `-all` rồi nói không còn rủi ro.** `-all` thay tập object được xét, không bảo đảm chi phí thấp.
6. **Đọc histogram sau full GC và so trực tiếp với histogram `-all`.** Hai tập object có thể khác ngữ nghĩa; không thể kết luận “mất object” do leak đã hết.
7. **Giả định `JFR.dump` sẽ stop recording.** Trên JDK 17, recording tiếp tục sau khi dump; `JFR.stop` mới dừng.
8. **Bật JFR `profile` dài hạn mà không đo overhead.** Settings nhiều events hơn có thể tác động CPU, disk và latency.
9. **Gọi `VM.log` không có kế hoạch rollback.** Tăng logging có thể gây I/O và thay đổi chính metric đang đo.
10. **Dùng tên main class hoặc PID 0 để gửi lệnh rộng.** Có thể tác động nhiều JVM; xác minh đúng PID duy nhất.
11. **Không kiểm tra container namespace và quyền attach.** `jcmd -l` không luôn thấy JVM trong container khác, và attach failure không chứng minh JVM treo.
12. **Lưu HPROF như log vô hại.** File có thể chứa dữ liệu nhạy cảm; cần kiểm soát access/storage.
13. **Không ghi lúc nào đã chạy lệnh.** Khi đồ thị CPU/GC/latency đổi ngay sau chẩn đoán, dễ kết luận sai quan hệ nhân quả.
14. **Chạy liên tiếp nhiều lệnh nặng trên JVM quá tải.** Các tác động chồng lên nhau, làm mất khả năng so sánh và có thể kéo dài sự cố.
15. **Tin tài liệu của một JDK khác hơn trợ giúp thực tế.** Các command/option/Impact có thể khác theo version/vendor; phải kiểm tra mục tiêu.

## 16. Tự kiểm tra kiến thức

1. `VM.flags` và `VM.set_flag` khác nhau ở ý định và side effect thế nào, dù cả hai có nhãn Impact Low trên JDK 17?
2. Vì sao `GC.heap_info` không tương đương `GC.class_histogram`? Lệnh nào phù hợp hơn khi chỉ cần xem cấu hình/tổng quan heap?
3. `GC.run` gọi API nào? Tại sao không thể cam kết luôn có một full stop-the-world GC giống nhau?
4. `GC.heap_dump` trên JDK 17 mặc định làm gì trước/đồng thời với việc ghi HPROF? `-all` thay đổi điều gì và không bảo đảm điều gì?
5. Một kỹ sư thấy heap used giảm ngay sau khi gọi `GC.run` rồi tuyên bố tìm ra nguyên nhân leak. Kết luận đó thiếu gì?
6. `JFR.check`, `JFR.start`, `JFR.dump`, `JFR.stop` thay đổi trạng thái recording/file như thế nào?
7. Một heap dump 4 GiB được tạo trong container gần đầy đĩa. Những rủi ro nào xuất hiện ngoài bản thân pause của JVM?
8. Vì sao `jcmd -l` không thấy Java PID trong một container khác chưa đủ chứng minh process không tồn tại?
9. Đâu là khác biệt giữa “lệnh có chi phí thấp” và “lệnh không thay đổi hành vi application”?
10. Khi ghi báo cáo sau một đợt chẩn đoán có histogram và JFR, bạn cần giữ những mốc thời gian và thông tin option nào để người khác phân biệt trước/sau can thiệp?

## Tài liệu đối chiếu

- Oracle, **The jcmd Command — Java SE 17**: https://docs.oracle.com/en/java/javase/17/docs/specs/man/jcmd.html
- Tự kiểm tra trên JVM đích: `jcmd <PID> help` và `jcmd <PID> help <COMMAND>`. Danh sách command, option và mức Impact **có thể thay đổi** theo JDK implementation/version.

**Ghi nhớ:** phân loại `jcmd` theo **tác dụng thực tế và chi phí** chứ không theo tên hoặc nhãn Impact đơn lẻ. Hãy thu bằng chứng ít xâm lấn trước, chỉ thực hiện GC/dump/recording/configuration có chủ đích khi thật sự cần, và luôn đánh dấu trong timeline những gì chính công cụ chẩn đoán đã thay đổi.