# Giới hạn suy luận nguyên nhân độ trễ chỉ từ nhật ký ứng dụng khi có thread-local handshake

## 1. Bối cảnh: một khoảng trống trong log không phải lời giải thích nguyên nhân

Trong một ứng dụng Java, đôi khi ta thấy hai log của cùng một request cách nhau hàng trăm mili giây:

~~~text
2026-11-07T09:00:00.000Z requestId=r-42 step=begin thread=37
2026-11-07T09:00:00.180Z requestId=r-42 step=end thread=37
~~~

Ta có thể nói: **theo hai timestamp này, khoảng cách quan sát là khoảng 180 ms**. Nhưng chỉ từ hai dòng đó, ta **không biết** thread đã làm gì trong 180 ms.

Những khả năng đều cần xem xét:

- Thread đang thực thi mã Java hoặc native code và tốn CPU.
- Thread bị hệ điều hành tạm ngừng cấp CPU do scheduler hoặc container CPU throttling.
- Thread chờ một monitor/lock, `LockSupport.park`, `Thread.sleep` hoặc điều kiện đồng bộ.
- Thread chờ network, database, đĩa hoặc dịch vụ khác.
- JVM đang thực hiện một **global safepoint** như một đợt stop-the-world GC.
- Thread cụ thể gặp một **thread-local handshake** hoặc một tác vụ VM khác.
- Code thực tế chạy rất nhanh nhưng hệ thống ghi log bị buffer, trì hoãn hoặc timestamp bị điều chỉnh.
- Có nhiều nguyên nhân **đồng thời hoặc chồng lấn**, không phải một nguyên nhân duy nhất.

Đặc biệt, **không được kết luận “thread-local handshake đã gây độ trễ 180 ms”** chỉ vì biết ứng dụng đang chạy JDK 10+ và nhìn thấy một khoảng trống giữa hai log.

Bài thuộc chủ đề **Handshake theo luồng** (*thread-local handshakes*) của Java 10. Mục tiêu là nắm đúng cơ chế JVM và giới hạn bằng chứng, sau đó biết cách đo, tương quan và xác nhận nguyên nhân độ trễ bằng những công cụ hiện còn được hỗ trợ.

## 2. Thread-local handshake của Java 10 thực sự là gì?

### 2.1. JEP 312 cung cấp cơ chế nội bộ của HotSpot

**OpenJDK JEP 312 — Thread-Local Handshakes**, được tích hợp từ **JDK 10**, cho phép HotSpot thực hiện một thao tác (*callback / VM operation*) liên quan tới **một hoặc một nhóm Java thread** mà **không bắt buộc** đưa toàn bộ JVM vào một **global safepoint**.

Trước cơ chế này, một số thao tác muốn bảo đảm trạng thái an toàn của thread có thể phải dùng global safepoint, khiến nhiều thread ứng dụng phải phối hợp dừng. Thread-local handshakes tạo điều kiện thực hiện công việc ở phạm vi hẹp hơn, cải thiện khả năng mở rộng và giảm nhu cầu global safepoint cho những thao tác phù hợp.

**Điểm phân biệt quan trọng:**

- **Global safepoint:** JVM cần các Java thread liên quan đạt trạng thái an toàn cho một tác vụ toàn cục; một số trường hợp như stop-the-world GC khiến các thread ứng dụng bị dừng.
- **Thread-local handshake:** JVM yêu cầu một thao tác được thực hiện với **thread đích**, hoặc một nhóm thread đích; các thread không bị nhắm tới không **bắt buộc** phải chờ chung như một global safepoint.
- **Không đồng nghĩa không bao giờ có pause:** thread đích vẫn có thể tạm dừng công việc ứng dụng để phục vụ thao tác nội bộ.
- **Không đồng nghĩa mọi handshake do GC gây ra:** cơ chế được nhiều thành phần HotSpot tận dụng tùy phiên bản và hoạt động JVM.
- **Không đồng nghĩa mọi global safepoint đã biến mất:** các tác vụ toàn cục vẫn tồn tại trên JDK hiện đại.

JEP 312 trước hết là một **cải tiến hạ tầng JVM**, không phải một API public kiểu `Thread.handshake()` mà ứng dụng thông thường gọi để chủ động ra lệnh handshake. Không được tự tạo ví dụ với một phương thức Java SE không tồn tại.

### 2.2. Cơ chế gần điểm an toàn không phải lịch biểu ứng dụng

Gọi là *handshake* không có nghĩa thread thực hiện một cuộc gọi HTTP, bắt tay TLS hay giao tiếp mạng. Trong ngữ cảnh này, đây là **phối hợp giữa HotSpot VM với Java thread** để thực hiện một hoạt động khi trạng thái thread phù hợp.

Trong thuật toán triển khai, thread mục tiêu có thể xử lý một yêu cầu khi đi tới vị trí kiểm tra an toàn hoặc khi JVM có thể thực hiện thao tác với thread đang ở trạng thái phù hợp. Chi tiết về nơi đặt poll và những công việc được chuyển sang handshake có thể thay đổi giữa các JDK/kiến trúc; application developer không nên dựa vào một chuỗi log nội bộ duy nhất như hợp đồng Java SE.

Một cách nhìn khái niệm:

~~~text
Global safepoint (sơ đồ khái niệm)
Thread A: --work--| STOP .......... |--work--
Thread B: --work--| STOP .......... |--work--
Thread C: --work--| STOP .......... |--work--
VM:               | global work    |

Thread-local handshake tới B (sơ đồ khái niệm)
Thread A: --work------------------------------work--
Thread B: --work--| handshake work |----------work--
Thread C: --work------------------------------work--
VM:              | operation on B |

Dấu STOP chỉ minh họa phạm vi phối hợp, không diễn tả
thời gian chính xác, implementation hoặc cam kết không có
các pause khác trong cùng thời điểm.
~~~

Vì vậy nếu request chạy trên thread B bị chậm, *handshake* có thể nằm trong danh sách giả thuyết, nhưng vẫn phải có **bằng chứng cho thao tác đó**, thời gian bắt đầu/kết thúc và tính trùng khớp với request. JEP 312 chỉ chứng minh **khả năng cơ chế tồn tại**, không chứng minh nó đã xảy ra ở một request cụ thể.

## 3. Log ứng dụng có thể chứng minh điều gì?

### 3.1. Khoảng thời gian quan sát khác thời gian chạy CPU

Nếu application code ghi:

~~~java
long start = System.nanoTime();
doWork();
long durationNs = System.nanoTime() - start;
~~~

`durationNs` là **elapsed time của đoạn code** theo đồng hồ monotonic dùng cho đo khoảng thời gian trong cùng JVM. Nó có thể gồm:

- CPU thực chạy trong `doWork()`.
- Chờ lock, park, I/O.
- Bị hệ điều hành preempt.
- Các pause JVM ảnh hưởng tới thread.
- Các thời gian chờ khác hoặc overhead trong đoạn đo.

Nó **không** tự trả về **CPU time** của thread. Đo `180 ms` bằng `System.nanoTime()` **không có nghĩa thread đã chiếm CPU 180 ms**.

### 3.2. Timestamp trong log là thời điểm ghi/quan sát, không phải dữ liệu CPU sampling

Ví dụ:

~~~text
09:00:00.000 start request r-42
09:00:00.180 finished request r-42
~~~

Nếu hai timestamp được phát sinh theo một định nghĩa nhất quán, chúng giúp ước lượng độ trễ giữa hai điểm được instrument. Nhưng:

- Logger bất đồng bộ có thể buffer và ghi xuống đĩa muộn hơn thời điểm tạo sự kiện.
- Các thread khác có thể xen log; thứ tự dòng trong file không luôn đại diện **happens-before** của mọi hành động nghiệp vụ.
- Đồng hồ wall-clock có thể bị chỉnh, đồng hồ ở nhiều máy có thể lệch.
- Nếu chỉ log sau mỗi bước lớn, không có thông tin về các khoảng nhỏ bên trong.
- Lấy thời điểm nhận log của hệ thống tập trung để trừ cho thời điểm tạo log trên JVM là phép tính dễ sai vì truyền mạng và buffering.

**Kết luận được phép:** “Request r-42 có khoảng thời gian log quan sát lớn”.

**Kết luận chưa đủ bằng chứng:** “JVM bị thread-local handshake 180 ms”, “GC chiếm 180 ms”, “database gây 180 ms”, “thread chạy CPU 180 ms”.

### 3.3. Nhật ký ứng dụng không ghi các hoạt động JVM không được instrument

Ngay cả khi tất cả đường code Java đều có log ở begin/end, các hoạt động như VM scheduling, safepoint synchronization, GC, native calls hay thao tác nội bộ của JVM không nhất thiết phát ra **ứng dụng log**.

Không có dòng `handshake` trong app log **không phải** bằng chứng không có handshake. Ngược lại, tên method ứng dụng có chữ `handshake` cũng không chứng minh thread-local handshake của HotSpot.

Đây là vấn đề **độ phủ instrumentation**: log ứng dụng chủ yếu trả lời câu hỏi “code ứng dụng đã quan sát gì”, không phải “toàn bộ VM làm gì bên trong”.

## 4. Vì sao một khoảng trống trong log có nhiều lời giải thích hợp lý?

| Giả thuyết | Ví dụ thực tế | Log ứng dụng thường cho thấy | Dữ liệu bổ sung để kiểm tra |
| --- | --- | --- | --- |
| CPU-bound code | Parser hoặc thuật toán xử lý quá nhiều dữ liệu | Begin/end cách xa, không rõ CPU time | JFR execution samples, thread CPU, profiler |
| Monitor contention | Nhiều request chờ chung một `synchronized` | Log trước và sau đoạn cần lock | JFR `jdk.JavaMonitorEnter`, thread dumps |
| Chờ điều kiện/park | Executor, queue, `CompletableFuture` chờ | Một bước “wait” dài | JFR `jdk.ThreadPark`, stack/queue metrics |
| Đợi database/network | JDBC call hoặc HTTP tới downstream | Log “DB begin / DB end” cách xa | Client metrics, distributed trace, JFR socket events, server logs |
| Blocking I/O | Đọc/ghi file, socket | Cùng thread chậm tiến | JFR file/socket events và OS I/O |
| Global STW | GC pause hoặc thao tác toàn VM | Nhiều thread cùng có log gap | `-Xlog:safepoint`, GC log, JFR GC events |
| Thread-local handshake | VM operation nhằm vào thread cụ thể | Một thread có thể chậm mà không có log giải thích | Bằng chứng VM/JFR/sampling phù hợp **JDK đang dùng** |
| OS descheduling | CPU cgroup throttling, máy quá tải | End log đến muộn | OS scheduler/cgroup/CPU metrics |
| Logging overhead | Logger khóa/đĩa chậm, queue đầy | Log thiếu, log dồn cụm hoặc latency tăng | JFR monitor/file events, logger queue/drop metrics |
| GC ngoài STW hoặc JIT | Cạnh tranh CPU, compilation | Latency biến động | JFR/compiler/GC/OS metrics |
| Lệch đồng hồ | Đồng bộ NTP, nhiều host | Dòng log trông lệch thời điểm | Nguồn clock, monotonic spans, clock-offset metrics |

Các nguyên nhân có thể **đồng thời**. Ví dụ request đang chờ socket trong một giai đoạn có STW GC, sau đó CPU lại bị scheduler trì hoãn. Không nên coi mỗi event trùng thời gian là một “mảnh độc lập có thể cộng lại” vào tổng latency.

## 5. Những suy luận sai thường thấy khi nói về handshake

### 5.1. “JDK 10 có thread-local handshake, nên mọi khoảng trống log do handshake”

**Sai.** JEP 312 chỉ cung cấp cơ chế để JVM thực hiện thao tác theo thread mà không cần global safepoint. Khi một request chậm, xác suất do mạng, lock, GC, CPU hoặc lịch hệ điều hành có thể phụ thuộc workload; không thể loại trừ chỉ vì tính năng handshake tồn tại.

Cần xác nhận có handshake liên quan, thời gian của thao tác và thread đích đúng là thread xử lý request.

### 5.2. “Không có GC log nên chắc chắn là handshake”

**Sai.** GC log và handshake có độ phủ khác nhau. Không thấy GC log có thể là do logging chưa bật, mức log không đủ, sự kiện không phải GC, log bị mất hoặc đồng hồ không được tương quan chính xác.

Ngoài handshake còn có CPU, lock, I/O, scheduler, async logging và nhiều yếu tố khác.

### 5.3. “Một thread chậm còn thread khác bình thường, vậy chắc chắn là per-thread handshake”

**Sai.** Lock contention, I/O hoặc CPU scheduling có thể chỉ ảnh hưởng một thread. Sự khác biệt giữa các thread là **manh mối về phạm vi tác động**, không phải danh tính nguyên nhân.

Nếu **nhiều** request/thread dừng ở thời điểm gần giống nhau, đó cũng chỉ là gợi ý cho một tác vụ chung như safepoint hoặc hạ tầng chung; vẫn cần log JVM/OS để xác nhận.

### 5.4. “Global safepoint và thread-local handshake giống nhau”

**Sai.** Global safepoint yêu cầu phối hợp trạng thái toàn cục; thread-local handshake có thể xử lý một tập thread hẹp hơn. Cả hai đều liên quan tới cơ chế điểm an toàn, nhưng **phạm vi và mục đích khác nhau**.

Đừng đọc một event `Safepoint` từ JFR rồi mặc định nó là thread-local handshake. Đừng cho rằng mọi global safepoint đều đã bị loại bỏ trên JDK mới.

### 5.5. “JVM log hoặc JFR event trùng giờ với request chậm là bằng chứng nhân quả tuyệt đối”

**Chưa đủ.** Một event của VM trùng thời gian với request giúp tăng độ tin cậy cho giả thuyết **có liên quan**, nhưng cần kiểm:

- Thread đích thực sự thuộc request nào.
- Event có **tác động làm thread chậm** không, hay request lúc đó đang chờ việc khác.
- Thời lượng event giao với thời lượng request bao nhiêu.
- Có event nào **chồng lấn** hay không.
- Kết quả có lặp lại trên những request tương tự hay không.
- Khi kiểm soát workload hoặc thay một biến, latency có đổi theo không.

Tương quan thời gian là **bằng chứng hữu ích**, nhưng chưa đủ để định lượng *causal contribution*.

## 6. Thiết kế application log để đo tốt hơn

### 6.1. Ghi request ID/trace ID và danh tính thread

Một log phục vụ điều tra nên có ít nhất:

- Thời điểm tạo event theo clock được mô tả rõ.
- `requestId` / `traceId` để liên kết các bước.
- Span hoặc tên bước cụ thể: `authorize`, `dbQuery`, `serialize`...
- Thread name/ID theo API hợp lệ của JDK đang chạy.
- Kết quả/thời gian của **đoạn code được đo**, nếu có.
- Thông tin phiên bản JDK, service version, instance/container khi phục vụ phân tích liên máy.
- Lỗi ngoại lệ hoặc status nếu bước thất bại.

Ví dụ **mang tính minh họa**, không phải một event cấu trúc bắt buộc:

~~~text
ts=2026-11-07T09:00:00Z trace=t42 span=db thread=37 action=start
ts=2026-11-07T09:00:00.180Z trace=t42 span=db thread=37 action=end elapsedMs=180
~~~

Có `elapsedMs` giúp giảm rủi ro khi người đọc tự trừ hai timestamp wall clock, nhưng con số đó vẫn là **elapsed time**, chưa phải CPU time hay pause time.

### 6.2. Dùng System.nanoTime cho elapsed time cục bộ

~~~java
// Mã minh họa trong một phương thức, không phải file đầy đủ.
long startNs = System.nanoTime();
try {
    serviceOperation();
} finally {
    long elapsedNs = System.nanoTime() - startNs;
    long elapsedMs =
            java.util.concurrent.TimeUnit.NANOSECONDS.toMillis(
                    elapsedNs);

    logger.info("span=serviceOperation elapsedMs=" + elapsedMs);
}
~~~

`System.nanoTime()` lấy mốc bất kỳ thích hợp để đo **hiệu giữa hai lần gọi trong cùng JVM**; giá trị tuyệt đối của nó không phải Unix timestamp. Không ghép một `nanoTime()` từ máy A với một từ máy B rồi đem trừ.

Đo lường bằng `nanoTime()` chưa tách được thời gian chạy CPU, I/O hoặc VM pause. Cần dùng thêm những nguồn phù hợp.

### 6.3. Wall-clock timestamp dùng để tương quan, không thay CPU time

`Instant.now()` hoặc logger timestamp phục vụ đối chiếu với các hệ khác. Nhưng đối với tính duration cục bộ, nên dùng monotonic clock. Việc điều chỉnh hệ thống thời gian có thể làm phép trừ wall clock không đáng tin.

Khi so log từ hai host:

1. Kiểm chuẩn thời gian (UTC, độ lệch và chất lượng NTP).
2. Gắn trace/span xuyên dịch vụ.
3. Dùng duration nội bộ của mỗi span nếu có.
4. Chấp nhận sai số khi tương quan với event JVM/OS ở host khác.
5. Không dùng một dòng timestamp gần nhau trong hai log làm bằng chứng chúng nằm trên cùng một timeline tuyệt đối chính xác tới microsecond.

### 6.4. Đừng biến logging thành nút cổ chai mới

Bật log debug quá rộng, log đồng bộ ra đĩa, format stack trace thường xuyên hoặc log từng vòng lặp có thể khiến hệ thống chậm hơn. Logger bất đồng bộ giảm chi phí đồng bộ trong nhiều trường hợp nhưng có thể:

- Ghi ra file muộn so với lúc event được tạo.
- Làm đổi thứ tự quan sát giữa nhiều producer.
- Mất event khi queue/buffer đầy theo cấu hình.
- Khiến lượng dữ liệu log quá lớn, khó tìm signal quan trọng.

Đo overhead của instrumentation và chọn mức logging vừa đủ; tránh thay đổi nguyên nhân đang cố điều tra.

## 7. Dùng công cụ JVM hiện đại để bổ sung bằng chứng

### 7.1. JVM Unified Logging: GC và global safepoint

Trên HotSpot Java 17+ có thể bật:

~~~bash
java -Xlog:gc=info,safepoint=info:file=jvm-events.log:time,uptime,level,tags -jar app.jar
~~~

Cấu hình này tạo JVM log riêng gồm GC và safepoint ở mức info. Nó **không tự động báo mọi per-thread handshake** và **không** thay thế log ứng dụng.

Muốn xem tag và option mà **đúng build JVM** hỗ trợ:

~~~bash
java -Xlog:help
~~~

Khi điều tra sâu hơn, hãy chọn tag/level phù hợp **sau khi xác nhận bằng `-Xlog:help`**; không copy một tên tag nội bộ không tồn tại trên mọi JDK. Các chuỗi log có thể khác giữa các bản HotSpot, và `-Xlog:safepoint` chủ yếu giúp quan sát **global safepoint activity**, không đủ để gán mọi độ trễ cá nhân cho handshake.

Nếu thấy một global safepoint dài trùng với nhiều request chậm, ta có thêm bằng chứng cho giả thuyết STW. Nhưng cần phân biệt **đợi thread đạt safepoint**, **tác vụ tại safepoint** và **resume**; không tự gộp mọi con số của log thành thời gian thread cụ thể bị dừng.

### 7.2. Java Flight Recorder (JFR)

**JDK Flight Recorder** là công cụ profiling/diagnostics còn được hỗ trợ và tích hợp với JDK. Có thể start recording khi khởi động:

~~~bash
java -XX:StartFlightRecording=filename=latency.jfr,settings=profile,dumponexit=true -jar app.jar
~~~

Hoặc với một JVM đang chạy (thay PID thực vào lệnh):

~~~bash
jcmd 12345 JFR.start name=latency duration=60s settings=profile filename=latency.jfr
~~~

`12345` chỉ là **PID minh họa**, phải thay bằng PID của JVM đích. `jcmd` cần quyền truy cập thích hợp và thường chạy trên cùng host/container context. Với chương trình hoạt động lâu, `duration=60s` thu một cửa sổ quan sát; cần bảo đảm cửa sổ đó bao gồm sự cố.

Dùng CLI để xem event:

~~~bash
jfr print --events jdk.ThreadPark,jdk.JavaMonitorEnter,jdk.JavaMonitorWait,jdk.SocketRead,jdk.FileRead,jdk.GCPhasePause latency.jfr
~~~

Event phải được **bật và ghi nhận** theo cấu hình recording. Những loại thường hữu ích:

| JFR event | Tín hiệu | Điều không nên suy |
| --- | --- | --- |
| `jdk.ThreadPark` | Thời gian thread bị park | Mọi park đều do handshake |
| `jdk.JavaMonitorEnter` | Chờ vào monitor có contention | Mọi gap là lock |
| `jdk.JavaMonitorWait` | Thời gian chờ theo `Object.wait` | Giống hoàn toàn với chờ vào monitor |
| `jdk.SocketRead` / `SocketWrite` | Thời gian thao tác network I/O | Chỉ JVM mới có lỗi nếu socket chậm |
| `jdk.FileRead` / `FileWrite` | Thời gian I/O file | Mọi I/O nhỏ đều được thu mặc định |
| `jdk.GCPhasePause` | Hoạt động GC pause được ghi nhận | Mọi request trùng GC đều do GC gây ra toàn bộ |
| `jdk.CPULoad` / `jdk.ThreadCPULoad` | Sử dụng CPU trong các kỳ lấy mẫu | Số liệu luôn cho nguyên nhân chính xác từng ns |
| `jdk.ExecutionSample` | Mẫu stack các thread thực thi code | Không có sample = không chạy code |

**Phân biệt `JavaMonitorEnter` và `JavaMonitorWait`:** cái đầu liên quan **tranh chấp lúc vào monitor**; cái sau là chờ sau khi gọi `Object.wait`. Cả hai có thể liên quan synchronized code nhưng ngữ nghĩa khác nhau.

### 7.3. Event threshold và sampling có thể che sự kiện ngắn

Oracle JFR troubleshooting lưu ý nhiều event chờ/I/O trong cấu hình mặc định chỉ được ghi nếu vượt một ngưỡng thời lượng (thường ở khoảng **20 ms** trong các template/bản được mô tả). Vì vậy:

- Không thấy `jdk.ThreadPark` **không chứng minh thread chưa hề park**.
- Một trăm lần chờ 1 ms có thể tác động hiệu năng nhưng không xuất hiện dưới dạng một trăm event trong recording ở ngưỡng 20 ms.
- CPU stack sampling mang tính **lấy mẫu**, không phải bản ghi liên tục của mọi instruction.
- Recording profile thường thu nhiều dữ liệu hơn default, có thể tăng overhead.
- Event có thể bị tắt hoặc điều chỉnh threshold bởi template/custom configuration.

Khi cần kiểm chứng một loại chờ ngắn, có thể tạo **JFR configuration riêng** và tăng độ nhạy trong một **cửa sổ thử nghiệm ngắn**, rồi đo overhead. Không hứa rằng JFR sẽ cho phép tính chính xác 100% từng microsecond.

### 7.4. Thread dump và CPU thread metrics

Lệnh chẩn đoán:

~~~bash
jcmd 12345 Thread.print
~~~

Thread dump cho một **ảnh chụp** trạng thái/stack của JVM. Nó có thể gợi ý BLOCKED/WAITING, lock hoặc phương thức đang chạy, nhưng **một ảnh chụp không phải lịch sử đầy đủ** của 180 ms trước đó.

Có thể dùng `java.lang.management.ThreadMXBean` để kiểm CPU time của thread được hỗ trợ:

~~~java
// Java 17+, mã minh họa trong method.
var bean = java.lang.management.ManagementFactory
        .getThreadMXBean();

if (bean.isThreadCpuTimeSupported()
        && bean.isThreadCpuTimeEnabled()) {
    long cpuNs = bean.getThreadCpuTime(
            Thread.currentThread().getId());
    // cpuNs là thông tin CPU của thread theo MXBean.
}
~~~

Trên một số JVM, thread CPU time không được hỗ trợ hoặc chưa được bật; không tự mặc định số đo luôn có. Các phép đo có thể trả giá trị báo không khả dụng theo API. Và CPU time khác elapsed time: request chờ socket 200 ms có thể dùng rất ít CPU.

### 7.5. OS/container data là phần không thể bỏ qua

Nếu JVM log và JFR không giải thích hết, xem:

- CPU utilization, run queue, scheduler delay.
- Container CPU throttling/cgroup quota.
- Memory pressure và swapping/page fault.
- Disk I/O saturation và network timeouts.
- Các process cạnh tranh CPU/I/O với JVM.
- Thay đổi nền tảng triển khai, autoscaling hoặc resource limits.

Một request có thể chậm do **thiếu CPU để được scheduling** mà không có một app log nào chỉ rõ điều đó, cũng không bắt buộc do per-thread handshake.

## 8. Phạm vi JFR và log trên các JDK khác nhau

### Java 10 và Java 17

- JEP 312 được tích hợp từ Java 10 trong HotSpot.
- JFR và JVM Unified Logging là hướng chẩn đoán còn được hỗ trợ trên JDK 17+.
- Những công cụ thông thường **không cung cấp một phép ánh xạ tự động** từ từng log-gap của application tới một thread-local handshake.
- Không viết code dựa vào `-XX:ThreadLocalHandshakes` hoặc một flag đặc thù từ bản JDK cổ mà chưa xác nhận nó vẫn được hỗ trợ; có những cờ chẩn đoán đã thay đổi trong quá trình phát triển HotSpot.

### Các cải tiến ở JDK mới

Từ **JDK 25**, JFR có những cải tiến về **cooperative sampling** (JEP 518). Một event như `jdk.SafepointLatency` ghi thông tin về độ trễ khi thread được sampling đi tới điểm poll phù hợp trên các build hỗ trợ event này.

**Cực kỳ quan trọng:**

- `jdk.SafepointLatency` **không phải** một bộ đếm tổng thời gian mọi thread-local handshake.
- Một sampling delay **không** chứng minh request đã chịu delay tương ứng vì một handshake.
- Event này **không có trên JDK 17**, nên không dùng nó làm lệnh bắt buộc của ví dụ Java 17.
- Khi dùng những event/flag mới, cần kiểm JDK thực đang chạy và cấu hình JFR tương ứng.

JDK mới cải thiện khả năng quan sát, nhưng **không thay đổi nguyên tắc suy luận có bằng chứng**.

## 9. Ví dụ Java 17+ hoàn chỉnh: thời gian chồng lấn không chứng minh nguyên nhân

Không thể tạo một chương trình Java đơn giản mà **bắt buộc JVM thực hiện đúng một thread-local handshake vào thời điểm xác định** chỉ bằng public Java SE API. Vì thế ví dụ chạy được này cố ý dùng **dữ liệu thời gian giả định** để tập luyện phép tính và kết luận đúng mức.

Giả sử ba khoảng trên **cùng một trục thời gian đã được đồng bộ hợp lệ**:

~~~text
Request   : [100 ms, 220 ms)  => 120 ms elapsed
Safepoint : [140 ms, 160 ms)  =>  20 ms
ThreadPark: [150 ms, 200 ms)  =>  50 ms

Trục thời gian:
100       140    150    160               200     220
|---------|------|------|-----------------|-------|
Request  =============================================
Safepoint         =======
ThreadPark               ==================

Chồng lấn Safepoint và ThreadPark: [150,160) = 10 ms.
Hợp các khoảng quan sát: 20 + 50 - 10 = 60 ms.
Không được cộng 20 + 50 = 70 ms như hai nguồn độc lập.
~~~

Đoạn biểu đồ chỉ có tính minh họa; JFR event có thể mang nhiều semantics khác nhau và đôi lúc bản thân event đã bao gồm thời gian dừng JVM. Phép tính hợp là một phép **toán trên timeline**, không phải mô hình causal attribution hoàn chỉnh.

Lưu file **`HandshakeLatencyEvidenceDemo.java`**:

~~~java
public class HandshakeLatencyEvidenceDemo {

    record Window(String name, long startMs, long endMs) {
        Window {
            if (startMs < 0 || endMs < startMs) {
                throw new IllegalArgumentException("invalid window");
            }
        }

        long durationMs() {
            return endMs - startMs;
        }
    }

    static long overlapMs(Window a, Window b) {
        long from = Math.max(a.startMs(), b.startMs());
        long to = Math.min(a.endMs(), b.endMs());
        return Math.max(0L, to - from);
    }

    public static void main(String[] args) {
        Window request = new Window("request", 100, 220);
        Window globalSafepoint = new Window("safepoint", 140, 160);
        Window threadPark = new Window("park", 150, 200);

        long safepointOverlap = overlapMs(
                request, globalSafepoint);
        long parkOverlap = overlapMs(request, threadPark);
        long commonOverlap = overlapMs(
                globalSafepoint, threadPark);

        long unionObserved = safepointOverlap
                + parkOverlap - commonOverlap;

        System.out.println("requestMs="
                + request.durationMs());
        System.out.println("safepointOverlapMs="
                + safepointOverlap);
        System.out.println("parkOverlapMs=" + parkOverlap);
        System.out.println("commonOverlapMs="
                + commonOverlap);
        System.out.println("observedUnionMs="
                + unionObserved);
        System.out.println("notCoveredByTheseSignalsMs="
                + (request.durationMs() - unionObserved));

        boolean hasDirectHandshakeEvidence = false;
        boolean isHandshakeCauseProven =
                hasDirectHandshakeEvidence
                        && safepointOverlap > 0;

        System.out.println("handshakeCauseProven="
                + isHandshakeCauseProven);
        System.out.println("appLogsAloneEnough=false");

        Window unrelated = new Window("other", 300, 350);
        System.out.println("noOverlap="
                + (overlapMs(request, unrelated) == 0));
    }
}
~~~

Biên dịch và chạy trên JDK 17+:

~~~bash
javac --release 17 HandshakeLatencyEvidenceDemo.java
java HandshakeLatencyEvidenceDemo
~~~

**Stdout chính xác, không phụ thuộc môi trường:**

~~~text
requestMs=120
safepointOverlapMs=20
parkOverlapMs=50
commonOverlapMs=10
observedUnionMs=60
notCoveredByTheseSignalsMs=60
handshakeCauseProven=false
appLogsAloneEnough=false
noOverlap=true
~~~

### Phân tích đúng cách

1. Khoảng request dài 120 ms, là elapsed time của mẫu giả định.
2. Khoảng safepoint trùng request 20 ms; khoảng park trùng request 50 ms.
3. Hai khoảng tự chồng lấn nhau 10 ms. Nếu cộng riêng 20+50 sẽ đếm trùng thời gian `[150,160)`.
4. Hợp hai khoảng là 60 ms. 60 ms còn lại **không được phủ bởi hai tín hiệu này**, nhưng không có nghĩa 60 ms là CPU time, handshake hay “thời gian hoàn toàn không có nguyên nhân”.
5. Tên biến `globalSafepoint` không tương đương thread-local handshake. Chương trình không hề có bằng chứng trực tiếp về handshake, nên `handshakeCauseProven=false`.
6. Ngay cả nếu có một event handshake trùng cửa sổ request, vẫn cần xem nó nhắm đúng thread và làm chậm phần xử lý request đến mức nào; một phép giao khoảng thời gian tự nó chưa chứng minh causal contribution.
7. `noOverlap=true` minh họa một event nằm ngoài request không trực tiếp trùng khoảng quan sát.

**Đây không phải test kích hoạt handshake hoặc GC thực**, mà là chương trình Java chạy được để tránh lỗi **nhầm tương quan với nguyên nhân** và **cộng trùng duration**.

## 10. Ba tình huống suy luận với dữ liệu thực tế

### Tình huống A: một request chậm, log ứng dụng không có gì thêm

~~~text
trace=r7, thread=worker-7, requestStart=10:00:00.000
trace=r7, thread=worker-7, requestEnd  =10:00:00.220
~~~

**Được phép nói:** khoảng thời gian từ start tới end theo log là ~220 ms.

**Chưa được nói:** bị handshake, GC, CPU hoặc database gây ra. Chưa rõ timestamp sinh ở đâu, có buffering không, workload của thread và event JVM thời điểm đó là gì.

**Bước tiếp theo:** thêm elapsed time bằng `nanoTime`, log span con, trace downstream và thu JFR/GC/safepoint để giảm không gian giả thuyết.

### Tình huống B: nhiều thread cùng có log gap và có STW GC

~~~text
10:00:00.000 nhiều request đang chạy
10:00:00.070 JVM bắt đầu global safepoint / GC pause
10:00:00.110 JVM kết thúc pause
10:00:00.160 nhiều request ghi end log
~~~

Nếu mốc thời gian đã được tương quan đúng, ta có bằng chứng **global safepoint/GC trùng với một phần thời gian request**. Điều đó hỗ trợ giả thuyết GC làm tăng latency, nhưng chưa cho biết nó đóng góp chính xác bao nhiêu vào từng request: có thread đang chờ socket/lock vào thời điểm pause, và end-to-end duration còn gồm các pha khác.

**Không đổi tên global safepoint thành thread-local handshake.**

### Tình huống C: chỉ một thread chậm và JFR ghi chờ monitor

Một request đang xử lý ở thread T; JFR cho thấy T chờ vào monitor nhiều chục mili giây cùng thời điểm, stack trace chỉ ra vị trí lock contention.

Đây là **bằng chứng mạnh hơn** cho giả thuyết chờ lock. Nhưng vẫn cần kiểm trace ID gắn với thread T trong khoảng đó, xem thread có xử lý nhiều task nối tiếp không và đo ảnh hưởng end-to-end.

**Không cần bịa một handshake** để giải thích khi đã có bằng chứng chờ lock rõ ràng. Ngược lại, nếu không thấy monitor event, chưa được khẳng định không có contention ngắn vì threshold và sampling.

## 11. Quy trình thực tế để điều tra “log gap” đáng ngờ

### Bước 1 — Xác định triệu chứng

- Request nào bị chậm, endpoint nào, bao nhiêu lượt?
- p50/p95/p99 latency theo thời gian thế nào?
- Chỉ một JVM hay mọi instance?
- Chỉ thread pool nào hay toàn bộ dịch vụ?
- Mức ảnh hưởng là một bước, một request hay cả hệ thống?
- Có release/config/traffic thay đổi trước đó?

Một log gap đơn lẻ đôi khi chỉ là outlier; để đánh giá sự cố cần phân bố latency và mẫu đủ đại diện.

### Bước 2 — Xác định phương pháp đo

- Timestamp được tạo ở đâu: app, logging framework hay log collector?
- Duration có dùng `System.nanoTime()` hay phép trừ wall clock?
- Có async logging, queue, mất log hoặc time sync drift?
- Trace/span có liên kết chính xác các request xuyên thread và dịch vụ?
- Thread ID có đi kèm từng bước hay chỉ tên thread chung?

Không tính một duration từ hai clock khác hệ quy chiếu rồi đổ lỗi cho handshake.

### Bước 3 — Đặt các giả thuyết cạnh tranh

Ghi rõ danh sách: CPU, lock, I/O, scheduler, global safepoint, handshake, logging overhead, queue wait và downstream latency. Với mỗi giả thuyết, nêu một **tín hiệu sẽ ủng hộ hoặc bác bỏ**.

Ví dụ:

| Giả thuyết | Tín hiệu ủng hộ | Tín hiệu khiến giả thuyết yếu đi |
| --- | --- | --- |
| Lock contention | JFR JavaMonitorEnter trùng thread và span | Không có contention đáng kể sau khi đã tăng độ phủ phù hợp |
| Network wait | SocketRead dài, trace downstream dài | Socket events ngắn, không có lời gọi network trong span |
| CPU hot path | Thread CPU và samples tăng | Thread chủ yếu WAITING/I/O |
| Global STW | GC/safepoint log trùng nhiều thread | Không có STW trong cửa sổ được thu đủ log |
| Per-thread handshake | VM signal/trace có thao tác đúng thread | Không có bằng chứng VM dù chỉ có log ứng dụng thì vẫn chưa thể loại trừ |
| OS scheduling | CPU throttling/run queue delay trùng | Không quan sát thấy áp lực hệ điều hành trong cửa sổ đủ dài |

Tín hiệu “không quan sát thấy” chỉ có giá trị loại trừ khi biết **độ phủ và ngưỡng đo**, không tự coi absence là proof.

### Bước 4 — Thu dữ liệu tương quan

1. App logs có request ID/span ID và thời gian của những bước quan trọng.
2. JFR trong cửa sổ có spike, dùng template phù hợp.
3. Unified JVM logs `gc` và `safepoint` khi cần.
4. Thread dumps lặp lại có kiểm soát nếu nghi khóa/chờ.
5. CPU, container quota/throttle, disk/network metrics của host.
6. Trace xuống dịch vụ downstream và kết quả trên server đích.

Với production, bắt đầu bằng công cụ overhead thấp, thu trong cửa sổ ngắn hoặc lấy mẫu, bảo vệ dữ liệu nhạy cảm và không bật tất cả mức debug không giới hạn.

### Bước 5 — Căn chỉnh timeline và phân tích chồng lấn

Trước khi so một event JFR với một request:

- Xác định VM instance, thread, request/span, host và timezone.
- Đưa mọi timestamp về cùng time reference đáng tin.
- Với monotonic duration, so bằng thời lượng từ cùng nguồn đo.
- Tính giao khoảng thời gian; không cộng các sự kiện chồng nhau.
- Phân biệt một event phát sinh **trong lúc request chờ** với một event thực sự làm request chậm.
- Nhắc rõ mức độ kết luận: *observed*, *correlated*, *strongly supported*, hoặc *unproven*.

Không lấy `duration của JFR event` rồi trừ nguyên vẹn khỏi request latency nếu event chỉ trùng một phần hoặc đã chồng với thời gian chờ khác.

### Bước 6 — Kiểm tra lại bằng thay đổi có kiểm soát

Một giả thuyết mạnh nên tái hiện được trong workload có kiểm soát:

- Với lock: giảm phạm vi critical section, so JFR và p99.
- Với network: xem downstream latency hoặc mock phù hợp, so kết quả.
- Với CPU: đo profile và tối ưu hot path thực.
- Với GC: so GC logs, heap pressure, object allocation và pause.
- Với thread-local handshake: cần đủ bằng chứng JVM phù hợp, và không dùng cờ chẩn đoán/flag nội bộ chưa được xác nhận ở JDK đang chạy.

Đừng tắt safepoint, tắt handshake hoặc tùy tiện chỉnh cờ HotSpot chỉ để “thử hết lag”: đây không phải một phương án vận hành an toàn hay phổ quát.

## 12. Lỗi thường gặp và cách sửa

| Nhận định/biện pháp sai | Vấn đề | Cách đúng |
| --- | --- | --- |
| “Thấy log gap 200 ms là JVM ngừng chạy 200 ms.” | Khoảng giữa log không đồng nghĩa STW | Đo spans, JFR, JVM logs |
| “Java 10 có handshake nên gap do handshake.” | Cơ chế tồn tại không xác nhận một event cụ thể | Cần bằng chứng VM + thread + timeline |
| “Không thấy GC log nghĩa là handshake.” | Có nhiều nguyên nhân và độ phủ log giới hạn | Kiểm CPU, lock, I/O, OS |
| “Chỉ thread T chậm là handshake cục bộ.” | Lock/scheduler/I/O cũng có tính cục bộ | Quan sát trạng thái/sự kiện T |
| “Safepoint log chứng minh mọi handshake.” | Global safepoint và per-thread khác nhau | Không đánh đồng hai cơ chế |
| “JFR không ghi ThreadPark nên chắc không park.” | Event threshold, sampling, cấu hình | Kiểm template/threshold, tăng độ phủ có kiểm soát |
| “Thread dump một lần cho biết cả 5 giây trước.” | Snapshot không phải timeline | Dùng JFR/chuỗi snapshots/tracing |
| “Elapsed=CPU time.” | Elapsed gồm chờ và scheduling | CPU time/profiling riêng |
| “Cộng thời lượng GC và lock cho request.” | Các interval có thể chồng lấn | Tính overlap/union và ngữ nghĩa của event |
| “Hai log từ hai host có cùng timestamp chính xác tuyệt đối.” | Clock skew và network buffering | Trace IDs + clock sync + local durations |
| “Ghi log rất nhiều không ảnh hưởng kết quả.” | Logging có thể tạo overhead/contended locks | Đo overhead, bật mức vừa đủ |
| “Không thấy event đồng nghĩa không xảy ra.” | Sampling và threshold có thể bỏ lỡ | Báo giới hạn độ phủ |
| “JFR SafepointLatency là tổng handshake pause.” | Event khác mục đích và không có ở mọi JDK | Đọc đặc tả riêng, không gán nhầm |
| “STW GC trùng request là toàn bộ nguyên nhân latency.” | Còn pha CPU/chờ khác | Phân tích phần giao và evidence khác |
| “Tắt cơ chế JVM để hết chậm.” | Rủi ro lớn, cờ có thể không còn hỗ trợ | Tối ưu theo bằng chứng, đúng JDK |
| “Benchmark chỉ một lần là đủ.” | JIT, GC, OS, load tạo biến động | Đo nhiều lần với workload ổn định |

## 13. Checklist code review và vận hành

### Khi viết instrumentation

- [ ] Log hoặc tracing có request/span ID rõ ràng và phù hợp khi chuyển thread?
- [ ] Có biết timestamp được lấy ở thời điểm nào và clock type nào?
- [ ] Đo elapsed time của một đoạn trong cùng JVM bằng `System.nanoTime()`?
- [ ] Không dùng `nanoTime()` như epoch timestamp hoặc trừ giữa hai JVM?
- [ ] Phân biệt elapsed time, CPU time, queue wait, I/O wait và VM pause?
- [ ] Có ghi phiên bản JVM và môi trường triển khai cần thiết?
- [ ] Có kiểm overhead và khả năng drop/reorder của logger?
- [ ] Không ghi dữ liệu người dùng nhạy cảm vô tình vào trace/log?
- [ ] Log đủ phân đoạn để định vị vấn đề, không log quá dày?

### Khi kết luận sự cố

- [ ] Đã phân biệt **application log gap** với **thread-local handshake**?
- [ ] Đã thu JFR hoặc JVM logs trên đúng instance/time window?
- [ ] Đã xác nhận log tags hỗ trợ bằng `java -Xlog:help`?
- [ ] Có dữ liệu lock, I/O, CPU, OS scheduling và GC phù hợp?
- [ ] Biết ngưỡng ghi JFR và event nào bị tắt?
- [ ] Có thread identity tương ứng request trong khoảng quan sát?
- [ ] Các khoảng event đã được căn cùng timeline và xét chồng lấn?
- [ ] Đã phân biệt một event **trùng thời gian** với nguyên nhân **gây chậm**?
- [ ] Có nhiều lượt quan sát hoặc một phép thử có kiểm soát hỗ trợ kết luận?
- [ ] Kết luận báo rõ mức tin cậy và những dữ liệu còn thiếu?

### Câu hỏi tự đánh giá

**Câu 1.** JEP 312 từ Java 10 cho phép điều gì?

**Đáp án:** HotSpot có thể thực hiện những thao tác/handshake hướng tới từng Java thread hoặc nhóm thread mà không luôn phải thực hiện global VM safepoint. Đây là hạ tầng JVM, không phải API Java SE gọi trực tiếp.

**Câu 2.** Hai log cùng request cách nhau 180 ms có chứng minh handshake kéo dài 180 ms không?

**Đáp án:** Không. Nó chỉ cho thấy khoảng thời gian quan sát; chưa biết CPU, lock, I/O, GC, scheduling, log buffer hoặc hoạt động JVM nào gây ra.

**Câu 3.** Thread-local handshake có đồng nghĩa global safepoint không?

**Đáp án:** Không. Global safepoint yêu cầu phối hợp toàn cục; handshake có thể nhắm riêng từng thread và tránh dừng tất cả thread cho thao tác đó.

**Câu 4.** Dùng `System.nanoTime()` đo 100 ms có nghĩa thread đã chạy CPU đúng 100 ms?

**Đáp án:** Không. Đây là elapsed time của đoạn đo, có thể bao gồm chờ, descheduling và VM pause.

**Câu 5.** Không thấy `jdk.ThreadPark` có nghĩa thread không bị park?

**Đáp án:** Không. Event có thể bị tắt, có threshold hoặc bị bỏ lỡ do phạm vi đo. Cần hiểu recording configuration.

**Câu 6.** `jdk.JavaMonitorEnter` và `jdk.JavaMonitorWait` có giống nhau?

**Đáp án:** Không. MonitorEnter quan sát tranh chấp khi vào monitor; MonitorWait quan sát chờ theo `Object.wait`.

**Câu 7.** `-Xlog:safepoint` đủ xác nhận mọi thread-local handshake?

**Đáp án:** Không. Nó hữu ích cho global safepoints, nhưng không phải bảng liệt kê bảo đảm mọi per-thread handshake.

**Câu 8.** Một event GC 20 ms và park 50 ms chồng nhau 10 ms thì có thể cộng thành 70 ms nguyên nhân request không?

**Đáp án:** Không. Hợp thời gian của hai interval là `20+50-10=60` ms và thời gian giao chỉ giúp tương quan, chưa định lượng nguyên nhân thực.

**Câu 9.** Thread dump một lần có tái tạo được toàn bộ lịch sử thread không?

**Đáp án:** Không. Nó là snapshot; dùng JFR/tracing và những lần lấy mẫu có kiểm soát khi cần lịch sử.

**Câu 10.** Vì sao không dùng trực tiếp `jdk.SafepointLatency` trên Java 17?

**Đáp án:** Đây là event bổ sung trong các JDK mới hơn như JDK 25, không phải event sẵn có ở Java 17; hơn nữa nó không đo tổng handshake pause.

**Câu 11.** Bước hợp lý sau khi thấy log gap là gì?

**Đáp án:** Ghi nhận triệu chứng, xác minh cách đo, liệt kê giả thuyết cạnh tranh và thu bằng chứng JFR/JVM/OS phù hợp, rồi thử kiểm chứng có kiểm soát.

**Câu 12.** Một log cho thấy GC trùng thời điểm request chậm có đủ chứng minh GC gây toàn bộ latency không?

**Đáp án:** Chưa. Cần xác định phần giao, thread nào bị tác động, các chờ khác và bằng chứng thời lượng thực.

## 14. Tài liệu chính thức còn áp dụng

- [OpenJDK JEP 312 — Thread-Local Handshakes](https://openjdk.org/jeps/312): mục tiêu của cải tiến JDK 10, cho phép handshake theo thread mà không bắt buộc global safepoint.
- [Oracle — Introducing Java SE 10](https://blogs.oracle.com/java/introducing-java-se-10): xác nhận JEP 312 là một thành phần của Java 10 và mô tả cơ chế dừng thread cá nhân.
- [Oracle Java SE 25 — Troubleshoot Performance Issues Using Flight Recorder](https://docs.oracle.com/en/java/javase/25/troubleshoot/troubleshoot-performance-issues-using-jfr.html): phân tích bottlenecks do thread blocking, I/O, GC, CPU và các ngưỡng ghi event.
- [Oracle Java SE 17 — Troubleshoot Performance Issues Using JFR](https://docs.oracle.com/en/java/javase/17/troubleshoot/troubleshoot-performance-issues-using-jfr.html): danh sách JFR events phù hợp với target Java 17.
- [Oracle Java SE 17 — The java Command](https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html): `-Xlog`, tag `gc`/`safepoint`, `-XX:StartFlightRecording` và ví dụ command line còn được hỗ trợ.
- [Oracle Java SE 17 — The jcmd Command](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jcmd.html): `JFR.start`, `JFR.dump`, `Thread.print` và những điều kiện sử dụng công cụ.
- [Oracle Java SE 17 — System.nanoTime](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/System.html#nanoTime()): đo elapsed time với hiệu của các lần đọc nanoTime.
- [Oracle Java SE 17 — ThreadMXBean](https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/ThreadMXBean.html): CPU time và trạng thái quan sát thread theo khả năng JVM.
- [OpenJDK JEP 518 — JFR Cooperative Sampling](https://openjdk.org/jeps/518): cải tiến sampling trong JDK 25 và bối cảnh event `jdk.SafepointLatency` ở các JVM mới.
- [Inside Java — What's New for JFR in JDK 25](https://inside.java/2025/06/03/new-jfr-jdk25/): giải thích phạm vi event `SafepointLatency`, tránh dùng như một bộ đếm handshake tổng quát.

**Ghi nhớ:** **Nhật ký ứng dụng cho thấy những gì ứng dụng đã ghi, không phải toàn bộ những gì JVM và hệ điều hành đã làm.** Thread-local handshake từ Java 10 giúp HotSpot thực hiện một số thao tác theo thread mà không cần global safepoint, nhưng không thể lấy một khoảng trống 180 ms trong log làm bằng chứng handshake đã gây delay. Muốn kết luận đáng tin, hãy **đo elapsed time đúng cách, thu JFR/JVM/OS evidence cùng một cửa sổ, kiểm thread/span identity, tránh cộng trùng interval và phân biệt tương quan với quan hệ nhân quả**.