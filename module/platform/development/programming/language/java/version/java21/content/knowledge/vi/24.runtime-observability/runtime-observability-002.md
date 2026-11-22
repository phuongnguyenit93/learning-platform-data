# Sự kiện virtual thread start, end, pinned và submit failed

Java 21 bổ sung các sự kiện JDK Flight Recorder (JFR) dành riêng cho virtual thread. Bốn sự kiện cần biết là `jdk.VirtualThreadStart`, `jdk.VirtualThreadEnd`, `jdk.VirtualThreadPinned` và `jdk.VirtualThreadSubmitFailed`. Chúng giúp quan sát vòng đời virtual thread, phát hiện trường hợp virtual thread bị giữ trên carrier khi blocking và nhận biết lỗi scheduler khi bắt đầu hoặc tiếp tục chạy virtual thread.

Các sự kiện này có trạng thái bật/tắt mặc định khác nhau. Đặc biệt, `VirtualThreadStart` và `VirtualThreadEnd` bị tắt mặc định, còn `VirtualThreadPinned` và `VirtualThreadSubmitFailed` được bật trong cấu hình JFR mặc định của JDK 21. Vì vậy, không thấy start/end trong file ghi hình không có nghĩa ứng dụng không tạo hoặc kết thúc virtual thread.

## 1. Bốn sự kiện JFR dành cho virtual thread

| Sự kiện | Khi nào được ghi nhận? | Mặc định trong cấu hình JFR JDK 21 | Mục đích quan sát |
|---|---|---|---|
| `jdk.VirtualThreadStart` | Virtual thread bắt đầu thực thi task | Tắt | Theo dõi số lượng và nhịp tạo virtual thread |
| `jdk.VirtualThreadEnd` | Virtual thread kết thúc thực thi | Tắt | Theo dõi vòng đời, thời điểm kết thúc và churn |
| `jdk.VirtualThreadPinned` | Virtual thread bị pin trong lúc blocking và carrier không được giải phóng lâu hơn threshold | Bật, threshold 20 ms | Tìm các điểm pinning có thể ảnh hưởng throughput |
| `jdk.VirtualThreadSubmitFailed` | Scheduler không thể submit continuation để bắt đầu hoặc unpark virtual thread | Bật | Điều tra lỗi tài nguyên hoặc lỗi khi scheduler lập lịch virtual thread |

Các trạng thái trên là thiết lập của cấu hình JFR mặc định đi kèm JDK 21. Một file `.jfc` tùy chỉnh, cấu hình `profile`, lệnh khởi động hoặc JFR API có thể thay đổi chúng. Khi phân tích, luôn kiểm tra cấu hình recording thay vì suy luận chỉ từ tên sự kiện.

## 2. VirtualThreadStart và VirtualThreadEnd

Hai sự kiện này đánh dấu thời điểm virtual thread thực sự bắt đầu và kết thúc thực thi. Chúng không đơn thuần là sự kiện tạo đối tượng `Thread`:

- `jdk.VirtualThreadStart` được ghi khi virtual thread bắt đầu chạy task.
- `jdk.VirtualThreadEnd` được ghi khi quá trình chạy task kết thúc, kể cả khi task kết thúc bất thường.

Có thể dùng cặp sự kiện này để phân tích:

- Tốc độ tạo virtual thread theo thời gian.
- Số lượng virtual thread bắt đầu và kết thúc trong một khoảng đo.
- Các đợt tăng đột biến về số task ngắn.
- Vòng đời của task và mức độ churn khi hệ thống nhận tải cao.

Ví dụ, một dịch vụ nhận request và tạo virtual thread cho từng request có thể có lượng `VirtualThreadStart` tăng mạnh trong một đợt traffic burst. Nếu `VirtualThreadEnd` không tăng tương ứng trong cùng khoảng thời gian, cần kiểm tra các task đang chạy lâu, đang chờ I/O hoặc chưa hoàn tất. Tuy nhiên, chỉ so sánh hai số đếm trong một recording chưa đủ để kết luận có rò rỉ thread: recording có thể bắt đầu khi một số thread đã chạy và kết thúc trước khi chúng hoàn tất.

### Vì sao start/end bị tắt mặc định?

Ứng dụng dùng virtual thread có thể tạo hàng chục nghìn hoặc hàng triệu thread trong thời gian hoạt động. Ghi một event cho mỗi lần bắt đầu và kết thúc có thể tạo lượng dữ liệu JFR rất lớn. Vì vậy, cấu hình mặc định tắt hai sự kiện này để giảm lượng event trong recording liên tục.

Khi cần phân tích vòng đời, hãy bật chúng trong một khoảng thời gian có mục tiêu. Nếu chỉ cần chẩn đoán pinning hoặc lỗi scheduler, có thể dùng hai sự kiện mặc định đã bật mà không cần thu toàn bộ start/end.

## 3. VirtualThreadPinned

`jdk.VirtualThreadPinned` cho biết virtual thread bị pin vào carrier trong khi blocking và carrier không được trả về scheduler trong khoảng thời gian dài hơn threshold. Trong cấu hình mặc định của JDK 21, threshold là 20 ms.

Trên JDK 21, các tình huống có thể gây pinning gồm:

- Virtual thread thực hiện thao tác blocking khi đang ở trong `synchronized` block hoặc method.
- Virtual thread chạy native method hoặc foreign function.

Sự kiện thường cung cấp stack trace để xác định vị trí blocking. Stack trace giúp lần từ thao tác I/O hoặc lời gọi native về đoạn code ứng dụng cần điều tra.

Phạm vi quan sát có giới hạn: trong JDK 21, event được phát khi virtual thread thử park nhưng không thể unmount và phải park carrier. Một native/foreign call có thể giữ carrier khi block ngay bên trong mã native mà không đi qua điểm park của JVM; không nên xem việc không có `VirtualThreadPinned` là bằng chứng mọi native/foreign pinning đều không xảy ra. Với các lời gọi native, cần kết hợp stack trace, thread dump và metric thời gian thực thi.

Ví dụ, nếu một virtual thread gọi I/O khi vẫn giữ monitor:

```java
final class ReportService {
    private final Object lock = new Object();

    void refresh() throws IOException {
        synchronized (lock) {
            // Trên JDK 21, blocking ở đây có thể pin virtual thread.
            callRemoteService();
        }
    }

    private void callRemoteService() throws IOException {
        // Thực hiện I/O có thể chờ lâu.
    }
}
```

Nếu event xuất hiện thường xuyên với stack trace trỏ tới `callRemoteService`, cần xem xét rút ngắn vùng synchronized hoặc chuyển thao tác blocking ra ngoài monitor khi invariant nghiệp vụ cho phép.

### Ý nghĩa của threshold 20 ms

Threshold là thời gian tối thiểu để JFR ghi event, không phải giới hạn thời gian tối đa mà virtual thread được phép bị pin. Với threshold mặc định 20 ms:

- Pinning ngắn hơn threshold thường không xuất hiện trong recording.
- Pinning kéo dài vượt threshold có thể tạo event.
- Hạ threshold có thể thu được nhiều event hơn, nhưng làm tăng lượng dữ liệu và chi phí ghi nhận.
- Không có event không chứng minh rằng ứng dụng không có pinning.

Có thể đặt threshold khác trong recording để điều tra:

```bash
jfr configure --input default.jfc --output vt-debug.jfc \
  jdk.VirtualThreadPinned#enabled=true \
  jdk.VirtualThreadPinned#threshold=5ms \
  jdk.VirtualThreadPinned#stackTrace=true
```

Threshold thấp hơn hữu ích khi cần tìm các lần pinning ngắn hơn, nhưng nên dùng trong một khoảng đo có kiểm soát và so sánh overhead trước/sau.

### Lưu ý khác biệt giữa JDK 21 và JDK mới hơn

Ý nghĩa của event vẫn là phát hiện virtual thread bị pin, nhưng nguyên nhân monitor-related thay đổi theo runtime:

| Runtime | Blocking trong `synchronized` | Nguyên nhân pinning còn đáng chú ý |
|---|---|---|
| JDK 21–23 | Có thể gây pinning | `synchronized`, native method và foreign function |
| JDK 24 trở lên | JEP 491 loại bỏ pinning chỉ vì đang giữ monitor | Native method và foreign function vẫn có thể pin |

Do đó, khi đọc `VirtualThreadPinned`, cần biết chính xác phiên bản JDK đã tạo recording. Trên JDK 21, stack trace có thể dẫn tới vùng synchronized; trên JDK 24 trở lên, không nên mặc định kết luận `synchronized` là nguyên nhân monitor-related pinning.

## 4. VirtualThreadSubmitFailed

`jdk.VirtualThreadSubmitFailed` được ghi khi runtime không thể submit công việc tiếp tục của virtual thread cho scheduler, chẳng hạn khi bắt đầu hoặc unpark virtual thread thất bại. Tài liệu Oracle mô tả đây thường là dấu hiệu có vấn đề về tài nguyên.

Parking một virtual thread cho phép nó nhường carrier trong lúc chờ; khi điều kiện chờ được đáp ứng, runtime cần unpark và lập lịch virtual thread để tiếp tục. Nếu scheduler không thể nhận continuation, quá trình bắt đầu hoặc tiếp tục thực thi có thể thất bại và event này được ghi.

Sự kiện này không đồng nghĩa với mọi trường hợp `ExecutorService.submit()` bị từ chối. Ví dụ, `ThreadPoolExecutor` có thể ném `RejectedExecutionException` theo rejection policy của ứng dụng khi queue đầy; điều đó không tự động có nghĩa JFR sẽ phát `jdk.VirtualThreadSubmitFailed`. Event này phản ánh lỗi submit continuation ở tầng runtime scheduler.

Khi event xuất hiện, cần kiểm tra:

- Thông điệp exception được ghi cùng event nếu có.
- Thời điểm và tần suất xảy ra; lỗi đơn lẻ khác với lỗi lặp lại liên tục.
- Áp lực bộ nhớ heap/native, giới hạn tài nguyên tiến trình và trạng thái scheduler.
- Các đợt tăng đột biến về số lượng virtual thread hoặc workload tạo/unpark thread.
- Log ứng dụng tại cùng timestamp để liên kết event với request hoặc workload tương ứng.

Không nên tự động tăng số carrier hoặc tạo thêm thread chỉ vì thấy event. Trước tiên cần xác định nguyên nhân tài nguyên, vì tăng concurrency có thể làm tình trạng quá tải nặng hơn.

## 5. Bật start/end bằng jfr configure

Cách chuẩn để bật `VirtualThreadStart` và `VirtualThreadEnd` là tạo một cấu hình `.jfc` riêng dựa trên `default.jfc`. Không sửa file cấu hình mặc định trong JDK.

```bash
jfr configure --input default.jfc --output virtual-threads.jfc \
  jdk.VirtualThreadStart#enabled=true \
  jdk.VirtualThreadEnd#enabled=true
```

Lệnh này tạo `virtual-threads.jfc`, bật hai event start/end và giữ các thiết lập còn lại từ `default.jfc`. Trong cấu hình mặc định JDK 21, `VirtualThreadPinned` và `VirtualThreadSubmitFailed` đã bật; có thể chỉ định tường minh nếu muốn recording dễ đọc và ổn định theo cấu hình đã chọn:

```bash
jfr configure --input default.jfc --output virtual-threads.jfc \
  jdk.VirtualThreadStart#enabled=true \
  jdk.VirtualThreadEnd#enabled=true \
  jdk.VirtualThreadPinned#enabled=true \
  jdk.VirtualThreadPinned#threshold=20ms \
  jdk.VirtualThreadSubmitFailed#enabled=true
```

Khởi chạy ứng dụng với cấu hình đó:

```bash
java -XX:StartFlightRecording:filename=virtual-threads.jfr,dumponexit=true,settings=virtual-threads.jfc \
     -jar application.jar
```

Nếu ứng dụng đã chạy, có thể bắt đầu recording bằng `jcmd`:

```bash
jcmd <pid> JFR.start name=virtual-threads settings=virtual-threads.jfc filename=virtual-threads.jfr
```

Sau khi thu thập đủ dữ liệu, dừng recording:

```bash
jcmd <pid> JFR.stop name=virtual-threads
```

`<pid>` là process ID của JVM cần quan sát. Cần dùng `jcmd` thuộc JDK phù hợp và có quyền attach tới tiến trình đó.

## 6. Thu thập và đọc các event

Sau khi recording hoàn tất, dùng `jfr summary` để xem tổng quan:

```bash
jfr summary virtual-threads.jfr
```

Lọc bốn sự kiện virtual thread:

```bash
jfr print --events jdk.VirtualThreadStart,jdk.VirtualThreadEnd,jdk.VirtualThreadPinned,jdk.VirtualThreadSubmitFailed \
  virtual-threads.jfr
```

Có thể ghi kết quả ra file để tìm kiếm và so sánh:

```bash
jfr print --events jdk.VirtualThreadPinned,jdk.VirtualThreadSubmitFailed \
  virtual-threads.jfr > virtual-thread-problems.txt
```

Để xem metadata và các trường được cung cấp bởi JDK tạo recording:

```bash
jfr metadata --events jdk.VirtualThreadStart,jdk.VirtualThreadEnd,jdk.VirtualThreadPinned,jdk.VirtualThreadSubmitFailed \
  virtual-threads.jfr
```

Lệnh `jfr print` chỉ in những event thực sự đã được ghi trong file. Nó không bật một event bị tắt trong recording. Nếu start/end không có dữ liệu, hãy kiểm tra lại `.jfc` đã được dùng khi bắt đầu recording.

### Đọc dữ liệu theo mục tiêu

| Mục tiêu | Event nên xem | Câu hỏi cần trả lời |
|---|---|---|
| Đo nhịp tạo và kết thúc virtual thread | Start + End | Có burst tạo thread? Task có kết thúc tương ứng? |
| Tìm thao tác blocking giữ carrier | Pinned | Stack trace chỉ tới synchronized, native hay foreign function? |
| Điều tra scheduler không thể lập lịch continuation | SubmitFailed | Event xảy ra lúc nào, exception message là gì, tài nguyên nào đang cạn? |
| So sánh trước/sau tối ưu | Cả bốn, với cùng workload và cấu hình | Tần suất event, duration và latency có thay đổi không? |

## 7. Ghi bằng JFR API trong Java

Nếu cần bật event từ code thay vì file `.jfc`, có thể dùng `Recording` API. Ví dụ sau tạo recording dựa trên cấu hình `default`, bật start/end và giữ stack trace cho pinned/submit failed:

```java
import java.nio.file.Path;
import java.time.Duration;
import jdk.jfr.Configuration;
import jdk.jfr.Recording;

public class VirtualThreadRecording {
    public static void main(String[] args) throws Exception {
        Configuration config = Configuration.getConfiguration("default");

        try (Recording recording = new Recording(config)) {
            recording.enable("jdk.VirtualThreadStart");
            recording.enable("jdk.VirtualThreadEnd");
            recording.enable("jdk.VirtualThreadPinned")
                    .withThreshold(Duration.ofMillis(20))
                    .withStackTrace();
            recording.enable("jdk.VirtualThreadSubmitFailed")
                    .withStackTrace();

            recording.setToDisk(true);
            recording.start();

            runApplicationWorkload();

            recording.stop();
            recording.dump(Path.of("virtual-threads.jfr"));
        }
    }

    private static void runApplicationWorkload() {
        // Chạy workload cần quan sát.
    }
}
```

Đoạn code này yêu cầu module `jdk.jfr` có mặt trong runtime image. Trong ứng dụng production, thường nên quản lý recording từ ngoài tiến trình bằng `jcmd`, JDK Mission Control hoặc cơ chế vận hành của nền tảng để không gắn vòng đời recording với một request nghiệp vụ.

## 8. Kết hợp với thread dump và metric ứng dụng

JFR cung cấp lịch sử event trong một khoảng recording. Thread dump là ảnh chụp trạng thái thread tại một thời điểm. Hai loại dữ liệu bổ sung cho nhau:

- Dùng JFR để biết sự kiện nào đã xảy ra, xảy ra bao lâu và stack trace liên quan.
- Dùng thread dump để xem virtual thread nào đang tồn tại và đang ở trạng thái nào tại thời điểm chụp.
- Dùng metric ứng dụng để liên kết event với số request in-flight, queue depth, latency, timeout và tải dependency.

Trên JDK 21, có thể tạo thread dump chứa virtual thread bằng:

```bash
jcmd <pid> Thread.dump_to_file -format=text threads.txt
jcmd <pid> Thread.dump_to_file -format=json threads.json
```

Đừng dùng số event Start/End làm metric active virtual thread tuyệt đối nếu recording không bao phủ toàn bộ vòng đời. Để đo số request đang xử lý, nên dùng metric admission/in-flight ở tầng ứng dụng. JFR giải thích hành vi runtime; metric nghiệp vụ giải thích tải mà ứng dụng đang phục vụ.

## 9. Những lỗi diễn giải thường gặp

| Hiểu nhầm | Cách hiểu đúng |
|---|---|
| Không thấy `VirtualThreadStart` nghĩa là không có virtual thread | Event này tắt mặc định; phải bật trong recording |
| Không thấy `VirtualThreadEnd` nghĩa là thread bị rò rỉ | Có thể event tắt hoặc recording không bao phủ thời điểm kết thúc |
| Không có `VirtualThreadPinned` nghĩa là không có pinning | Event có threshold; pinning ngắn hơn threshold có thể không được ghi |
| Mọi `RejectedExecutionException` đều tạo `VirtualThreadSubmitFailed` | Event phản ánh lỗi submit/unpark continuation ở scheduler runtime, không phải mọi rejection của executor ứng dụng |
| Một event pinned luôn chứng minh synchronized là nguyên nhân | Cần xem runtime version và stack trace; native/foreign function cũng có thể pin |
| Có thể cộng Start trừ End để biết chính xác số thread đang chạy | Chỉ đúng khi recording bao phủ đầy đủ lifecycle và không thiếu event; dùng metric ứng dụng để đo active request |
| Bật tất cả event và stack trace trong production luôn miễn phí | Start/end có thể phát sinh lượng event rất lớn; cần cân nhắc thời gian thu thập, dung lượng và overhead |

## 10. Checklist quan sát virtual thread

- [ ] Xác nhận phiên bản JDK đang chạy ứng dụng.
- [ ] Kiểm tra cấu hình `.jfc` và trạng thái enabled của từng event.
- [ ] Bật `VirtualThreadStart`/`VirtualThreadEnd` chỉ khi cần phân tích lifecycle.
- [ ] Hiểu `VirtualThreadPinned` có threshold mặc định 20 ms trong cấu hình JDK 21.
- [ ] Dùng stack trace của pinned event để tìm vị trí blocking.
- [ ] Phân biệt lỗi scheduler `VirtualThreadSubmitFailed` với rejection của executor ứng dụng.
- [ ] Dùng `jfr summary`, `jfr print` và `jfr metadata` để đọc recording.
- [ ] Kết hợp JFR với thread dump và metric in-flight/queue/latency.
- [ ] Không suy luận không có event đồng nghĩa không có vấn đề.
- [ ] Giới hạn thời gian và dung lượng khi bật start/end trên hệ thống tạo nhiều virtual thread.
- [ ] Khi chạy JDK 24+, diễn giải pinned event theo thay đổi JEP 491; monitor pinning đã được loại bỏ.

## Tài liệu tham khảo

- [Virtual Threads — Java SE 21 Guide](https://docs.oracle.com/en/java/javase/21/core/virtual-threads.html): bốn JFR event, trạng thái mặc định, threshold pinning và cách in event.
- [Flight Recorder Configurations — Java SE 21](https://docs.oracle.com/en/java/javase/21/jfapi/flight-recorder-configurations.html): `default.jfc`, `profile.jfc`, cấu hình recording và cách tạo cấu hình riêng.
- [The `jfr` Command — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jfr.html): `jfr configure`, `jfr summary`, `jfr print` và `jfr metadata`.
- [RecordingStream — Java SE 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/jdk.jfr/jdk/jfr/consumer/RecordingStream.html): cấu hình và tiêu thụ event bằng JFR API.
- [JDK 21 VirtualThread implementation](https://github.com/openjdk/jdk21/blob/master/src/java.base/share/classes/java/lang/VirtualThread.java): vị trí runtime phát start/end và submit-failed event.
- [JEP 491: Synchronize Virtual Threads without Pinning](https://openjdk.org/jeps/491): thay đổi từ JDK 24 ảnh hưởng cách diễn giải monitor-related pinning.
