# 10.6 Quan sát `VirtualThreadPinned`, `VirtualThreadSubmitFailed` và cấu hình JFR

> **Phạm vi:** Java 21+ (virtual thread là tính năng chính thức từ JDK 21). Ví dụ thực hành pinning dùng JDK 21–23; JDK 24+ có thay đổi quan trọng nhờ JEP 491. Các tên sự kiện bên dưới là tên đầy đủ trong Java Flight Recorder (JFR).

## 1. Mục tiêu và mô hình quan sát

Sau bài này, bạn có thể:

- Giải thích vì sao một virtual thread đôi khi giữ chặt **carrier thread** khi chờ đợi, và điều gì khiến việc đó ảnh hưởng đến khả năng mở rộng.
- Phân biệt `jdk.VirtualThreadPinned` (chờ đợi khi đang pinned) với `jdk.VirtualThreadSubmitFailed` (thất bại khi đưa công việc của virtual thread vào bộ lập lịch).
- Bật, điều chỉnh và kiểm tra các event JFR qua `.jfc`, `jfr`, `jcmd`; thu thập và đọc bản ghi `.jfr`.
- Dựa trên thời lượng, stack trace và ngữ cảnh tải thực tế để xác định điểm cần sửa; nhận biết khác biệt JDK 21–23 và JDK 24+.

**Nhắc lại cơ chế:** virtual thread (VT) chạy Java code bằng cách **mount** lên một platform thread gọi là *carrier*. Khi một thao tác chờ hỗ trợ unmount, VT nhường carrier để carrier chạy VT khác. Khi VT không thể unmount vì bị *pinned*, carrier vẫn bị chiếm trong thời gian VT chờ. Pinning không đồng nghĩa deadlock, lỗi nghiệp vụ hay `OutOfMemoryError`; tác động chính là giảm khả năng dùng lại số carrier có hạn nếu thời gian chờ dài **và** lặp lại nhiều.

Trong JDK 21–23, blocking khi đang ở trong một `synchronized` block/method hoặc khi đang chạy qua native/foreign frame có thể gây pinning. Một đoạn `synchronized` chỉ thực hiện tính toán ngắn không tự động trở thành vấn đề: điều đáng tìm là **blocking lâu trong trạng thái không unmount được**. Từ JDK 24, JEP 491 cho phép virtual thread chờ trong các cấu trúc `synchronized` mà không cần giữ carrier như trước; pinning do native/VM frames và một số tình huống runtime vẫn cần được quan sát.

## 2. Bốn event JFR cần biết

| Event | Ý nghĩa | Mặc định với `default.jfc` của JDK 21 | Khi dùng |
| --- | --- | --- | --- |
| `jdk.VirtualThreadPinned` | VT thực hiện thao tác blocking khi còn pinned đủ lâu để vượt ngưỡng. | `enabled=true`, `threshold=20 ms`, `stackTrace=true` | Tìm đoạn giữ carrier trong lúc chờ và đo độ dài của lần blocking đó. |
| `jdk.VirtualThreadSubmitFailed` | Runtime không submit được continuation/task để VT bắt đầu hoặc chạy lại sau unpark; có thể liên quan tới cạn tài nguyên hay scheduler từ chối. | `enabled=true`, `stackTrace=true` | Điều tra lỗi scheduling; kết hợp exception, log và tình trạng tài nguyên. |
| `jdk.VirtualThreadStart` | VT bắt đầu chạy. | `enabled=false` | Theo dõi vòng đời ngắn hạn khi cần đối chiếu số lượng VT. |
| `jdk.VirtualThreadEnd` | VT kết thúc. | `enabled=false` | Đối chiếu thời điểm hoàn tất VT khi điều tra vòng đời. |

Các giá trị trên là cấu hình **mặc định theo bản JDK**, không có nghĩa JFR luôn ghi liên tục. Phải **khởi động một recording**, và recording đó phải dùng profile có event tương ứng. File `.jfc` tùy chỉnh, phiên bản JDK hoặc nhà phân phối có thể thay đổi cấu hình thực tế.

**Hiểu đúng `threshold`:** `20 ms` là ngưỡng thời lượng cho một lần blocking **trong khi pinned**, không phải thời gian chạy của VT, thời gian giữ monitor, hoặc tổng latency request. Event dưới ngưỡng không xuất hiện trong bản ghi; `VirtualThreadSubmitFailed` là event về lỗi submit, không có ngưỡng thời lượng tương đương. `Thread.sleep`, `SocketRead`, `ThreadPark` hoặc `JavaMonitorEnter` tự chúng **không chứng minh** VT đang pinned; chúng chỉ hữu ích để liên hệ nguyên nhân.

## 3. Cấu hình event và khởi động recording

### 3.1. Kiểm tra công cụ và định nghĩa event

Dùng JDK có `java`, `javac`, `jfr`, `jcmd` trên `PATH`. Nên lấy công cụ từ **cùng phiên bản JDK với JVM đang chẩn đoán**.

```bash
java -version
jfr help configure
jfr metadata --events jdk.VirtualThreadPinned,jdk.VirtualThreadSubmitFailed
```

`jfr metadata` cho biết tên trường thực có trên JDK đang dùng. Ví dụ trên JDK 21, tập trung vào `duration`, `eventThread`, `stackTrace` của pinned event; với submit failure, chú ý `javaThreadId` và `exceptionMessage`. JDK 24+ bổ sung thông tin chẩn đoán pinning như `blockingOperation`, `pinnedReason`, `carrierThread`; **đừng giả định các trường mới này có ở JDK 21**.

### 3.2. Tạo `.jfc` để quan sát ngắn hạn

Không cần viết XML bằng tay. `jfr configure` lấy `default.jfc` làm nền nếu không chỉ rõ `--input`:

```bash
jfr configure --output vt-diagnostics.jfc "jdk.VirtualThreadPinned#enabled=true" "jdk.VirtualThreadPinned#threshold=5ms" "jdk.VirtualThreadPinned#stackTrace=true" "jdk.VirtualThreadSubmitFailed#enabled=true" "jdk.VirtualThreadSubmitFailed#stackTrace=true"
```

File `vt-diagnostics.jfc` giữ các event cơ bản của `default.jfc` và thay ngưỡng pinned từ 20 ms xuống **5 ms** để điều tra. Dấu `#` nằm **trong tên setting JFR**, không phải chú thích shell; đặt đối số trong dấu ngoặc kép giúp dễ dùng trên các terminal khác nhau.

- `enabled=true`: ghi nhận event khi có recording phù hợp.
- `threshold=5ms`: bắt thêm các lần blocking pinned ngắn hơn; ngưỡng càng thấp, số lượng event và overhead tiềm năng càng tăng.
- `stackTrace=true`: giữ chuỗi lời gọi để lần về vị trí blocking; tăng lượng dữ liệu so với chỉ ghi event.
- Không thêm `threshold` cho `VirtualThreadSubmitFailed`: đây không phải event đo một khoảng chờ.
- Không bật `VirtualThreadStart`/`End` vô hạn trên hệ thống tạo hàng triệu VT; chúng có thể sinh nhiều event. Nếu thực sự cần trong một cửa sổ ngắn, thêm `"jdk.VirtualThreadStart#enabled=true" "jdk.VirtualThreadEnd#enabled=true"` vào lệnh cấu hình.

Với phép đo sản xuất dài hạn, hãy bắt đầu bằng `default.jfc` và ngưỡng 20 ms; chỉ hạ ngưỡng cho đợt chẩn đoán có thời hạn. `profile.jfc` thu thập nhiều dữ liệu hơn, nên thường tốn tài nguyên hơn `default.jfc`.

### 3.3. Thu thập lúc khởi động chương trình

```bash
java -XX:StartFlightRecording=filename=vt-diagnostics.jfr,dumponexit=true,settings=vt-diagnostics.jfc -cp . MyApp
```

Thay `MyApp` bằng main class hoặc lựa chọn chạy phù hợp của ứng dụng (ví dụ có thể dùng `-jar app.jar`). Recording dùng file cấu hình bạn vừa tạo; `dumponexit=true` yêu cầu ghi file khi JVM kết thúc. File `.jfr` là **nhị phân**, cần mở bằng JFR/JDK Mission Control, không đọc như log text. Nên dùng đường dẫn tuyệt đối nếu chưa chắc working directory.

### 3.4. Thu thập trên JVM đã chạy

Tìm PID của JVM mục tiêu rồi attach:

```bash
jcmd -l
jcmd <PID> JFR.start name=vt-diag settings=vt-diagnostics.jfc duration=60s filename=vt-diagnostics.jfr
jcmd <PID> JFR.check name=vt-diag verbose=true
```

`JFR.check verbose=true` giúp xác minh recording đang chạy và các event setting thực tế, tránh suy luận từ một file `.jfc` không được sử dụng. Khi cần snapshot trong lúc recording còn chạy:

```bash
jcmd <PID> JFR.dump name=vt-diag filename=vt-snapshot.jfr
```

Hoặc để **dừng một recording chưa tự kết thúc** và ghi file cuối:

```bash
jcmd <PID> JFR.stop name=vt-diag filename=vt-final.jfr
```

Với `duration=60s`, recording sẽ tự hết hạn sau khoảng thời gian đó; không cần gọi `JFR.stop` lần nữa. Lệnh attach cần chạy với quyền truy cập phù hợp đến process. Tùy cách khởi động và cấu hình, `jcmd` có thể không attach được; khi đó hãy dùng tùy chọn `-XX:StartFlightRecording` lúc khởi động.

**Phân biệt hai lệnh dễ nhầm:** `jfr configure` tạo/sửa **event settings file** `.jfc`. `jcmd <PID> JFR.configure` chủ yếu cấu hình tham số recorder toàn cục (buffer, repository, v.v.); để chọn event cho một recording, dùng `JFR.start settings=...` hoặc API JFR tương ứng.

### 3.5. Đọc kết quả và đối chiếu metadata

```bash
jfr summary vt-diagnostics.jfr
jfr print --events jdk.VirtualThreadPinned,jdk.VirtualThreadSubmitFailed vt-diagnostics.jfr
jfr print --events jdk.VirtualThreadStart,jdk.VirtualThreadEnd vt-diagnostics.jfr
jfr metadata --events jdk.VirtualThreadPinned,jdk.VirtualThreadSubmitFailed vt-diagnostics.jfr
```

- `jfr summary` kiểm tra có event, tổng số và dung lượng; giúp phát hiện nhầm recording hoặc thiếu event.
- `jfr print --events` lọc đúng loại event, rồi xem thời điểm, duration, thread, stack và thông tin lỗi. Nếu Start/End không được bật, lệnh in hai event này sẽ không có kết quả, và đó là bình thường.
- `jfr metadata ... <file>` kiểm tra **schema được lưu trong chính recording**; hữu ích khi công cụ phân tích và JVM tạo file khác phiên bản.
- JDK Mission Control (JMC) thuận tiện hơn khi cần nhóm theo stack trace, lọc thời gian, xem các event liên quan và so sánh với CPU/GC/latency.

## 4. Diễn giải `jdk.VirtualThreadPinned`

Một pinned event cho biết có **lần blocking đủ dài khi VT không thể nhường carrier**. Với JDK 21–23, các trường thường cần quan sát là:

| Thông tin | Cách đọc |
| --- | --- |
| `startTime`, `duration` | Lần blocking xảy ra lúc nào, kéo dài bao lâu; dùng để đối chiếu latency hoặc các đợt nghẽn. |
| `eventThread` | Virtual thread phát sinh sự kiện (nếu metadata/recording cung cấp). |
| `stackTrace` | Chuỗi lời gọi tại nơi runtime ghi nhận tình huống pinned; lần theo frame thuộc package của ứng dụng. |
| `blockingOperation`, `pinnedReason`, `carrierThread` | Thông tin chi tiết hơn trên JDK mới (JDK 24+), cho biết thao tác chờ, lý do pinned và carrier liên quan. Không coi đây là trường bắt buộc của JDK 21. |

**Trình tự phân tích thực tế:**

1. Chọn khoảng thời gian có request latency tăng, throughput giảm hoặc carrier bị chiếm nhiều.
2. Lọc `VirtualThreadPinned`, nhóm theo stack trace/vị trí mã nguồn. Đếm tần suất và xem phân phối duration thay vì nhìn một event đơn lẻ.
3. Tìm frame ứng dụng gần vị trí gọi I/O, `sleep`, park, monitor hoặc native boundary; đối chiếu JDK version và source để xác định vì sao không unmount được.
4. Đối chiếu event liên quan (`jdk.SocketRead`, `jdk.ThreadPark`, `jdk.JavaMonitorEnter`, `jdk.JavaMonitorWait`) và metric thực tế; chúng cung cấp bối cảnh chứ không tự xác nhận pinning.
5. Chỉ sửa nơi **blocking pinned dài và thường xuyên**. Sau thay đổi, lặp lại tải tương đương, đo cả số event, thời lượng, throughput và request latency.

Tránh kết luận "cứ thấy synchronized là phải thay hết": monitor dùng ngắn, chủ yếu CPU hoặc hiếm khi chờ không nhất thiết là nút thắt. Trên JDK 21–23, nếu có I/O hoặc chờ lâu trong monitor, ưu tiên chuyển blocking ra ngoài khối đồng bộ; khi cần khóa loại trừ lẫn nhau trong lúc chờ, cân nhắc `ReentrantLock` với `try/finally`. JDK 24+ thường giải quyết nguyên nhân monitor pinning bằng nâng cấp runtime; vẫn phải xác minh các nguyên nhân khác.

**Không thấy event** có thể vì không xảy ra blocking pinned, thời gian chờ dưới threshold, cửa sổ recording không trùng tải, sai `.jfc`, thiếu stack do setting, hoặc behavior đã thay đổi ở JDK mới. Điều đó **không chứng minh** toàn hệ thống không thể gặp pinning.

## 5. Diễn giải `jdk.VirtualThreadSubmitFailed`

Khác với pinned, `VirtualThreadSubmitFailed` báo sự cố trong đường **submit/schedule continuation** của một virtual thread để bắt đầu hoặc chạy tiếp sau unpark. Theo implementation OpenJDK JDK 21, một đường đi là scheduler từ chối tiếp nhận task bằng `RejectedExecutionException`; event chứa thông tin như `javaThreadId` của VT và `exceptionMessage`. Event được bật theo mặc định, nhưng **không có nghĩa tất cả exception trong task, mọi `ExecutorService.submit()` bị reject, hoặc mọi tình huống thiếu bộ nhớ đều tự động biến thành event này**.

Khi thấy event:

1. Đọc `startTime`, `javaThreadId`, `exceptionMessage`, `stackTrace` nếu có; `eventThread` là thread ghi event và có thể **khác** VT có ID `javaThreadId`.
2. Đối chiếu application logs/exception cùng thời điểm, vòng đời của executor/scheduler và các thay đổi triển khai. Tìm bằng chứng scheduler bị shutdown, từ chối task, hoặc đường phục hồi/unpark gặp lỗi.
3. Kiểm tra áp lực tài nguyên: memory/GC, số platform/carrier threads, tải CPU, file descriptors, giới hạn container, backlog và giới hạn downstream; phân biệt nguyên nhân thực tế với giả thuyết.
4. Khắc phục nguồn reject/cạn tài nguyên hoặc lifecycle race đã được chứng minh; chạy lại tình huống tương đương và bảo đảm event không tái diễn.

Đừng diễn giải `VirtualThreadSubmitFailed` là "task chạy và trả về lỗi". Đây là sự cố **đưa công việc vào bộ lập lịch**, có thể xảy ra trước khi task chạy hoặc lúc VT cần tiếp tục. Một pinned event cũng không đồng nghĩa sau đó sẽ có submit failure: hai tín hiệu mô tả **hai cơ chế khác nhau**.

## 6. Lab kiểm chứng pinning (JDK 21–23)

Thí nghiệm sau cố tình cho một VT ngủ 250 ms **trong monitor** ở chế độ `monitor`, rồi dùng `ReentrantLock` ở chế độ `lock`. Mục tiêu là nhìn thấy event, không phải benchmark hiệu năng. Hãy thực hiện trên JDK 21–23 để so sánh nguyên nhân pinning do `synchronized`.

Tạo file `VirtualThreadJfrDemo.java`:

```java
import java.util.concurrent.locks.ReentrantLock;

public class VirtualThreadJfrDemo {
    private static final Object MONITOR = new Object();
    private static final ReentrantLock LOCK = new ReentrantLock();

    private static void pause() {
        try {
            Thread.sleep(250);
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
        }
    }

    public static void main(String[] args) throws InterruptedException {
        boolean useMonitor = args.length == 0 || !"lock".equals(args[0]);
        Thread vt = Thread.ofVirtual().name("vt-demo").start(() -> {
            if (useMonitor) {
                synchronized (MONITOR) {
                    pause();
                }
            } else {
                LOCK.lock();
                try {
                    pause();
                } finally {
                    LOCK.unlock();
                }
            }
        });
        vt.join();
        System.out.println(useMonitor ? "monitor completed" : "lock completed");
    }
}
```

Biên dịch bằng JDK 21+ và chạy hai lần với `.jfc` ở mục 3:

```bash
javac VirtualThreadJfrDemo.java
java -XX:StartFlightRecording=filename=monitor.jfr,dumponexit=true,settings=vt-diagnostics.jfc VirtualThreadJfrDemo monitor
java -XX:StartFlightRecording=filename=lock.jfr,dumponexit=true,settings=vt-diagnostics.jfc VirtualThreadJfrDemo lock
jfr print --events jdk.VirtualThreadPinned monitor.jfr
jfr print --events jdk.VirtualThreadPinned lock.jfr
```

Dòng output do **chương trình Java** in ra, theo thứ tự hai lần chạy:

```text
monitor completed
lock completed
```

JVM có thể in thêm thông báo startup/recording của JFR; hai dòng trên không phải toàn bộ stdout của JVM khi bật recording.

**Kết quả kỳ vọng:** trên JDK 21–23, lần `monitor` thường tạo một `jdk.VirtualThreadPinned` có duration gần thời gian chờ (tùy thực tế), vì `Thread.sleep` diễn ra khi VT đang giữ monitor. Lần `lock` thường không có event pinned cho đoạn ngủ này vì VT có thể unmount. Quan sát còn phụ thuộc thời điểm recording, threshold, JDK cụ thể và hệ thống. Trên JDK 24+, JEP 491 đã thay đổi cách monitor hoạt động, vì vậy **không dùng việc thiếu pinned event ở lần `monitor` để kết luận lab bị lỗi**.

Trong chương trình nghiệp vụ, thường còn lựa chọn tốt hơn: giảm phạm vi `synchronized`, chỉ bảo vệ thay đổi trạng thái ngắn và đưa I/O/blocking ra ngoài khóa nếu invariant cho phép. `ReentrantLock` cần cặp `lock()`/`unlock()` chính xác; thay máy móc tất cả monitor có thể tăng độ phức tạp mà không cải thiện hiệu năng.

## 7. Cách điều tra một sự cố thực tế

Giả sử server dùng virtual threads để gọi HTTP downstream và có các đợt latency cao khi tải tăng.

**Nếu `VirtualThreadPinned` xuất hiện nhiều:** nhóm theo stack, thấy các VT blocking ở client call bên trong monitor trên JDK 21; kiểm tra vì sao monitor bao trùm I/O, cân nhắc thu hẹp critical section hoặc dùng khóa phù hợp. Đo lại với cùng tải, không chỉ nhìn số event giảm. Trên JDK 24+, xem `pinnedReason` và `blockingOperation` khi có, vì monitor pinning thông thường đã được giải quyết.

**Nếu `VirtualThreadSubmitFailed` xuất hiện:** đọc message và stack; kiểm tra có scheduler/executor reject task, shutdown race, thiếu tài nguyên hay thay đổi hạ tầng. Đừng chỉ nâng scheduler parallelism hoặc thêm VT: số VT lớn không làm downstream pool, CPU hay bộ nhớ vô hạn. Theo dõi cả error rate và tài nguyên khi khắc phục.

**Nếu không có hai event nhưng latency vẫn cao:** kiểm tra config/recording, sau đó xét nghẽn connection pool, giới hạn request downstream, DB, GC, CPU, lock contention, timeout và queue ở tầng ứng dụng. Virtual threads giúp giảm chi phí chờ trên platform threads; chúng không tự làm I/O hay downstream nhanh hơn.

Một phép đo có ý nghĩa nên ghi rõ **JDK version, `.jfc` sử dụng, duration của recording, thời điểm tải, ngưỡng pinned, số event, nhóm stack nổi bật và latency/throughput**. So sánh trước/sau dưới điều kiện tương tự.

## 8. Những khác biệt phiên bản và lỗi thường gặp

| Tình huống | Giải thích đúng |
| --- | --- |
| JDK 21–23 có blocking trong `synchronized` | VT có thể giữ carrier khi chờ; `VirtualThreadPinned` là tín hiệu đáng kiểm tra. |
| JDK 24+ chạy lại cùng code mà hết event | Có thể là tác dụng của **JEP 491**, không phải JFR hỏng; pinning khác vẫn có thể xảy ra. |
| Có `synchronized` nhưng không có event | Event không đếm mọi monitor; cần lần blocking pinned vượt threshold trong recording. |
| Bật event trong `.jfc` nhưng file `.jfr` không có event | Kiểm tra recording thực sự dùng đúng `.jfc`, `JFR.check verbose=true`, khoảng tải và threshold. |
| `VirtualThreadStart`/`End` không hiện ra | Hai event lifecycle bị tắt theo `default.jfc`; chỉ bật ngắn hạn khi cần. |
| `VirtualThreadSubmitFailed` không xuất hiện khi task ném exception | Event phản ánh lỗi scheduler submit, không phải mọi lỗi trong thân task. |
| Muốn bỏ hẳn threshold để thấy mọi pin | Có thể làm dữ liệu bùng nổ; chọn ngưỡng nhỏ hơn cho cửa sổ ngắn rồi đưa về cấu hình ổn định. |
| Phân tích file JFR từ JDK khác phiên bản | Dùng `jfr metadata ... file.jfr`; tên/trường event có thể thay đổi theo phiên bản. |

Trên JDK 21–23, có thêm công cụ debug cục bộ `-Djdk.tracePinnedThreads=full` hoặc `short` để in stack khi xảy ra pinning. Đây là mẹo chẩn đoán của những bản JDK cũ; **không dựa vào thuộc tính này ở JDK 24+** sau thay đổi JEP 491. JFR vẫn là cách phù hợp hơn để thu thập dữ liệu có timestamp, duration và tương quan với event khác.

## 9. Checklist thao tác và kết luận cần đạt

1. Xác định phiên bản JVM đang chạy và tái hiện tải.
2. Bật `jdk.VirtualThreadPinned`, `jdk.VirtualThreadSubmitFailed` bằng `.jfc` phù hợp; xem lại ngưỡng và `stackTrace`.
3. Chạy recording bằng `-XX:StartFlightRecording` hoặc attach bằng `jcmd JFR.start`; xác nhận bằng `JFR.check verbose=true`.
4. Dùng `jfr summary`, `jfr print` và JMC để phân nhóm event theo stack, thời điểm, thời lượng hoặc exception.
5. Với pinned: tìm **blocking giữ carrier**, xem tần suất và JDK version. Với submit failure: tìm **đường submit bị từ chối** và bằng chứng áp lực tài nguyên/lifecycle.
6. Sửa đúng nguyên nhân, ghi lại cùng kịch bản và đối chiếu latency, throughput cùng số lượng/thời lượng event. Nếu cần tăng độ nhạy, hạ threshold trong một cửa sổ ngắn rồi khôi phục.

**Ghi nhớ:** `VirtualThreadPinned` phục vụ điều tra **mất khả năng nhường carrier khi chờ**; `VirtualThreadSubmitFailed` phục vụ điều tra **lỗi scheduling continuation**. Chỉ dựa vào sự tồn tại của một event không đủ để quy lỗi hoặc quyết định tối ưu hóa; phải ghép stack, cấu hình recording, JDK version và dữ liệu ứng dụng.

## Tài liệu tham khảo

- [Oracle JDK 21 — Virtual Threads, pinning và các JFR events](https://docs.oracle.com/en/java/javase/21/core/virtual-threads.html)
- [OpenJDK — JEP 491: Synchronize Virtual Threads without Pinning](https://openjdk.org/jeps/491)
- [Dev.java — Configuring the JDK Flight Recorder](https://dev.java/learn/jvm/jfr/configure/)
- [Oracle JDK 21 — lệnh `jfr`](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jfr.html)
- [Oracle JDK 21 — lệnh `jcmd`](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html)
