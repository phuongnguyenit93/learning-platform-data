# Phát hiện vùng giữ monitor lâu hoặc có I/O bên trong

Một vùng `synchronized` có thể trở thành điểm nghẽn khi thread giữ monitor lâu, khiến các thread khác phải chờ để vào cùng vùng tới hạn. Tình huống đáng chú ý hơn là khi code thực hiện thao tác có thể block như gọi HTTP, truy vấn database, đọc file hoặc chờ dịch vụ bên ngoài trong lúc vẫn giữ monitor.

Để tìm đúng nguyên nhân, cần phân biệt ba khoảng thời gian: thời gian thread chờ lấy monitor, thời gian thread thực sự giữ monitor và thời gian thread bị block do I/O. JDK Flight Recorder (JFR), JDK Mission Control (JMC), thread dump và một số phép đo trong ứng dụng có thể kết hợp để xác định vùng mã gây vấn đề.

## 1. Nhận biết dấu hiệu của monitor bị giữ lâu

Các biểu hiện thường gặp:

- Request có độ trễ tăng dù CPU không sử dụng hết.
- Nhiều thread ở trạng thái `BLOCKED`, cùng chờ một monitor.
- Một số monitor class xuất hiện thường xuyên trong báo cáo lock contention.
- Một nhóm thread chờ lâu tại cùng dòng code hoặc cùng method.
- Khi một thread thực hiện I/O, nhiều thread khác không thể cập nhật hoặc đọc trạng thái được bảo vệ bởi cùng monitor.
- Với virtual thread trên JDK 21–23, blocking trong synchronized còn có thể giữ carrier platform thread do pinning.

Ví dụ:

```java
class ProfileService {
    private final Object lock = new Object();
    private Profile cached;

    Profile load(String userId) throws Exception {
        synchronized (lock) {
            if (cached == null) {
                // Gọi dịch vụ bên ngoài trong lúc đang giữ monitor.
                cached = fetchFromRemoteService(userId);
            }
            return cached;
        }
    }

    private Profile fetchFromRemoteService(String userId) throws Exception {
        // Đại diện cho HTTP hoặc database call có thể chờ lâu.
        return remoteClient.fetch(userId);
    }
}
```

Nếu `fetchFromRemoteService` mất 800 ms, mọi thread cần monitor `lock` đều phải đợi trong khoảng đó. Vấn đề không chỉ là request đầu tiên chậm; các request khác cũng bị xếp hàng dù chúng có thể chỉ cần đọc dữ liệu cache.

Không phải cứ thấy nhiều thread `BLOCKED` là kết luận có I/O bên trong synchronized. Có thể thread giữ monitor đang chạy tính toán, xử lý logging hoặc chờ một khóa khác. Cần xem stack trace và thời gian thực tế để xác định nguyên nhân.

## 2. Phân biệt các loại chờ liên quan đến monitor

Các trạng thái và sự kiện monitor không có cùng ý nghĩa:

| Trạng thái/sự kiện | Ý nghĩa | Cần kiểm tra |
|---|---|---|
| Thread state `BLOCKED` | Thread đang chờ vào hoặc vào lại monitor | Thread đang sở hữu monitor và vị trí chờ |
| JFR `jdk.JavaMonitorEnter` | Ghi nhận thời gian thread bị block khi cố vào monitor đã được thread khác giữ | Stack trace của thread chờ, monitor class và `previousOwner` |
| JFR `jdk.JavaMonitorWait` | Ghi nhận thread gọi `Object.wait()` và nằm trong wait set của monitor | Điều kiện chờ, notifier, timeout và logic notify |
| JFR `jdk.SocketRead` / `jdk.SocketWrite` | Thời gian chờ đọc/ghi socket | Network, remote service và call stack |
| JFR `jdk.FileRead` / `jdk.FileWrite` | Thời gian đọc/ghi file | File system, storage và call stack |
| JFR `jdk.VirtualThreadPinned` | Virtual thread bị pin vào carrier lâu hơn ngưỡng ghi nhận | Stack trace và nguyên nhân pinning trên runtime tương ứng |

`JavaMonitorEnter` là sự kiện quan trọng để phân tích contention: nó đo thời gian thread chờ lấy monitor, không đo trực tiếp thời gian thread sở hữu monitor. Sự kiện có trường `previousOwner` để nhận diện thread đã giữ monitor trước đó. Stack trace đi kèm chủ yếu cho biết vị trí thread đang chờ.

`JavaMonitorWait` liên quan đến `Object.wait()`. Khi gọi `wait()`, thread đưa mình vào wait set và nhả monitor của object đó; nó phải lấy lại monitor trước khi tiếp tục sau khi được đánh thức. Đây là cơ chế chờ theo điều kiện, khác với việc một thread bị block khi cố đi vào synchronized block.

Phân biệt đúng các loại chờ giúp tránh đọc nhầm một thread đang chờ `notify` thành thread đang bị chặn bởi một owner giữ monitor quá lâu.

## 3. Dùng JFR để ghi nhận lock contention

JFR có thể ghi lại thời gian thread bị block, stack trace, loại monitor và thread sở hữu trước đó. Đây là cách thực tế để phát hiện monitor contention trên ứng dụng đang chạy.

Có thể bắt đầu một recording ngắn bằng `jcmd`:

```bash
jcmd <pid> JFR.start name=MonitorIO settings=profile duration=2m filename=monitor-io.jfr
```

Trong đó:

- `<pid>` là process ID của JVM cần quan sát.
- `settings=profile` thu thập nhiều dữ liệu hơn cấu hình mặc định, phù hợp với một lần chẩn đoán ngắn.
- `duration=2m` giới hạn thời gian recording trong hai phút.
- `filename` là file recording được ghi ra khi kết thúc.

Sau khi recording hoàn tất, có thể xem các event liên quan:

```bash
jfr print --events jdk.JavaMonitorEnter,jdk.JavaMonitorWait,jdk.SocketRead,jdk.SocketWrite,jdk.FileRead,jdk.FileWrite,jdk.VirtualThreadPinned --stack-depth 64 monitor-io.jfr
```

Có thể xem tổng quan recording trước khi đọc chi tiết:

```bash
jfr summary monitor-io.jfr
```

Nếu cần quan sát lock contention ngắn hơn ngưỡng mặc định, có thể giảm threshold cho một recording ngắn:

```bash
jcmd <pid> JFR.start name=ShortLockCheck settings=profile duration=30s filename=short-lock-check.jfr jdk.JavaMonitorEnter#threshold=5ms jdk.JavaMonitorWait#threshold=5ms
```

Các cấu hình JFR phổ biến thường bỏ qua event ngắn hơn một ngưỡng nhất định (thường là 20 ms trong cấu hình mặc định cho các event ứng dụng liên quan). Giảm threshold giúp nhìn thấy nhiều lần chờ ngắn hơn nhưng tạo thêm dữ liệu và có thể tăng overhead. Hãy bắt đầu bằng recording ngắn, theo dõi tác động và chỉ giảm ngưỡng khi dữ liệu hiện tại chưa đủ để tìm vấn đề.

## 4. Phân tích JavaMonitorEnter và xác định thread giữ khóa

Một event `jdk.JavaMonitorEnter` thường cung cấp các thông tin quan trọng:

- `duration`: thời gian thread chờ để lấy monitor.
- `monitorClass`: class của object được dùng làm monitor.
- `previousOwner`: thread sở hữu monitor trước khi thread đang chờ lấy được khóa.
- `eventThread`: thread đang chờ monitor.
- `stackTrace`: vị trí code nơi thread cố đi vào monitor.
- `address`: định danh monitor trong phạm vi recording, hữu ích khi đối chiếu event.

Khi phân tích, hãy nhóm event theo `monitorClass`, tổng thời gian chờ, số lần chờ và thời lượng lớn nhất. Một monitor có nhiều event ngắn có thể đáng chú ý nếu tổng thời gian chờ cao; một event rất dài cũng cần được kiểm tra dù số lần xuất hiện ít.

Ví dụ minh họa một event:

```text
jdk.JavaMonitorEnter {
  duration = 240 ms
  monitorClass = com.example.ProfileService
  previousOwner = "request-17"
  eventThread = "request-42"
  stackTrace = [
    com.example.ProfileService.load(String) line: 18
    com.example.ProfileController.getProfile(String) line: 31
  ]
}
```

Trong ví dụ, `request-42` chờ 240 ms để vào monitor của `ProfileService`; thread `request-17` là owner trước đó. Stack trace của event cho biết nơi thread chờ khóa, chưa cho biết chính xác owner đang thực thi dòng code nào trong toàn bộ khoảng 240 ms.

Để tìm owner:

1. Lấy tên hoặc thread ID từ `previousOwner`.
2. Kiểm tra các event khác cùng thời điểm để xem owner có đang thực hiện socket/file I/O, sleep hoặc thao tác blocking hay không.
3. So sánh với thread dump hoặc execution sample quanh thời điểm đó.
4. Mở Lock Instances trong JMC để xem monitor nào có nhiều thread chờ và stack trace liên quan.
5. Đối chiếu stack trace với code synchronized thực tế để xác định đoạn nào giữ monitor.

Không suy ra thời gian giữ khóa bằng cách lấy duration của một event `JavaMonitorEnter`. Duration đó là thời gian của thread chờ, không phải thời gian owner đã giữ monitor. Nhiều thread có thể chờ cùng một owner và tổng thời gian chờ cộng dồn có thể lớn hơn thời gian monitor thực sự bị giữ.

## 5. Dùng JDK Mission Control để xem Lock Instances

JMC cung cấp giao diện phân tích recording JFR. Khi mở file recording:

1. Chọn Automated Analysis Results để xem các dấu hiệu hiệu năng nổi bật.
2. Mở phần Lock Instances để xem các monitor có contention.
3. Sắp xếp theo tổng thời gian blocked hoặc số lần blocked.
4. Chọn một lock để xem stack trace của thread chờ và thông tin owner khi event cung cấp.
5. Kiểm tra xem các stack trace có tập trung vào một method, logger, cache hoặc object dùng chung hay không.

Ví dụ, nếu monitor của `Logger` xuất hiện với số lần blocked lớn, có thể nhiều thread đang tranh chấp trong quá trình ghi log. Nếu monitor thuộc một service hoặc cache, hãy kiểm tra xem code có gọi network, database hoặc file I/O trong khi giữ monitor hay không.

Lock Instances cho thấy nơi thread chờ monitor. Nó là điểm bắt đầu để tìm owner và vùng tới hạn; không nên chỉ dựa vào class của monitor để kết luận method nào đang giữ khóa lâu.

## 6. Phát hiện I/O trong lúc giữ monitor

Một cách phát hiện là đối chiếu các event monitor với event I/O theo thread và thời gian:

- `jdk.SocketRead` và `jdk.SocketWrite` cho biết thời gian đọc/ghi socket.
- `jdk.FileRead` và `jdk.FileWrite` cho biết thời gian đọc/ghi file.
- `jdk.JavaMonitorEnter` cho biết thread nào đang chờ monitor và owner trước đó.
- `jdk.VirtualThreadPinned` giúp nhận diện một số trường hợp virtual thread bị pin khi block.

Quy trình kiểm tra:

1. Tìm event `JavaMonitorEnter` có duration lớn.
2. Ghi lại `previousOwner`, monitor class và thời điểm event.
3. Tìm event I/O có cùng thread owner và thời gian chồng lấn.
4. Kiểm tra stack trace của event I/O để xác định call stack.
5. Mở code của owner để xác nhận lời gọi I/O có nằm trong vùng synchronized đang giữ monitor hay không.

Ví dụ, nếu owner đang thực thi `ProfileService.load()` và cùng thời điểm có event `SocketRead` trong `HttpClient.send()`, đó là dấu hiệu cần kiểm tra xem lời gọi HTTP có nằm bên trong synchronized block hay không.

JFR ghi nhận event I/O được runtime hoặc thư viện instrument hỗ trợ. Không phải mọi loại I/O, native call hoặc driver đều xuất hiện dưới cùng một event. Nếu không thấy `SocketRead` hoặc `FileRead`, điều đó không chứng minh rằng code không thực hiện I/O; cần xem stack trace, thư viện, driver và các công cụ quan sát phù hợp.

### 6.1. Ví dụ về code cần kiểm tra

```java
class SettingsService {
    private final Object lock = new Object();
    private Settings current;

    Settings getSettings() throws Exception {
        synchronized (lock) {
            if (current == null) {
                current = loadFromRemote();
            }
            return current;
        }
    }

    private Settings loadFromRemote() throws Exception {
        return httpClient.fetchSettings();
    }
}
```

Nếu `loadFromRemote()` chờ network, monitor vẫn bị giữ trong suốt thời gian chờ. JFR có thể cho thấy thread khác bị block khi vào monitor, đồng thời ghi nhận event socket trên owner. Khi ghép hai nguồn thông tin, có thể xác định I/O là một phần của vùng tới hạn.

Một cách thiết kế thường phù hợp hơn là lấy snapshot hoặc kiểm tra trạng thái trong monitor, thực hiện I/O bên ngoài, rồi lấy khóa lại để cập nhật:

```java
Settings getSettings() throws Exception {
    synchronized (lock) {
        if (current != null) {
            return current;
        }
    }

    Settings loaded = loadFromRemote();

    synchronized (lock) {
        if (current == null) {
            current = loaded;
        }
        return current;
    }
}
```

Ví dụ này tránh giữ monitor trong lúc chờ network. Nếu nhiều thread cùng tải dữ liệu khi cache đang rỗng, có thể xảy ra nhiều request đồng thời; nếu nghiệp vụ yêu cầu chỉ một lần tải, cần bổ sung cơ chế phối hợp riêng như future dùng chung hoặc trạng thái loading. Không nên mở rộng vùng synchronized để bao trùm I/O chỉ nhằm tránh duplicate request mà không đánh giá tác động tới các thread khác.

## 7. Thread dump để kiểm tra trạng thái tại một thời điểm

Thread dump giúp xem stack trace và trạng thái thread tại thời điểm lấy mẫu. Có thể dùng:

```bash
jcmd <pid> Thread.print -l
```

Tùy chọn `-l` bổ sung thông tin về các ownable synchronizer của `java.util.concurrent`. Thread dump truyền thống cũng thể hiện trạng thái monitor và vị trí thread đang chờ.

Với ứng dụng dùng virtual thread trên Java 21, có thể tạo dump gồm cả virtual thread:

```bash
jcmd <pid> Thread.dump_to_file -format=text threads.txt
```

Hoặc dạng JSON để công cụ khác phân tích:

```bash
jcmd <pid> Thread.dump_to_file -format=json threads.json
```

Trong JDK 21, `Thread.dump_to_file` bao gồm virtual thread nhưng không cung cấp đầy đủ thông tin object monitor/lock như thread dump HotSpot truyền thống. Vì vậy, hãy dùng nó để xem stack và trạng thái của virtual thread; dùng JFR và các thông tin lock phù hợp để phân tích contention.

Một thread dump là ảnh chụp tại một thời điểm. Nếu chỉ thấy một thread đang ở trong method synchronized, chưa đủ để kết luận method đó giữ monitor lâu. Có thể lấy nhiều dump cách nhau một khoảng ngắn, so sánh trạng thái và stack trace; JFR phù hợp hơn để định lượng thời gian và tần suất trong cả khoảng quan sát.

## 8. Đo trực tiếp thời gian giữ monitor khi cần

JFR event `JavaMonitorEnter` đo thời gian chờ lấy monitor, không đo trực tiếp thời gian một đoạn code giữ monitor. Nếu cần đo chính xác một vùng tới hạn do ứng dụng sở hữu, có thể tạo custom JFR event hoặc thêm instrumentation có kiểm soát.

Ví dụ custom event:

```java
import jdk.jfr.Category;
import jdk.jfr.Event;
import jdk.jfr.Label;
import jdk.jfr.Name;
import jdk.jfr.StackTrace;

@Name("com.example.CriticalSection")
@Label("Critical Section Duration")
@Category({"Application", "Synchronization"})
@StackTrace(false)
class CriticalSectionEvent extends Event {
    @Label("Section")
    String section;
}
```

Dùng event bên trong vùng synchronized để đo thời gian thực thi khi monitor đang được giữ:

```java
void reserve(int quantity) {
    synchronized (lock) {
        CriticalSectionEvent event = new CriticalSectionEvent();
        event.section = "inventory.reserve";
        boolean recording = event.isEnabled();

        if (recording) {
            event.begin();
        }

        try {
            if (quantity <= 0 || available < quantity) {
                return;
            }
            available -= quantity;
        } finally {
            if (recording) {
                event.end();
                if (event.shouldCommit()) {
                    event.commit();
                }
            }
        }
    }
}
```

Event này đo phần thân được instrument sau khi đã lấy monitor và kết thúc trước khi thoát khỏi vùng synchronized. Nó giúp phân biệt thời gian giữ khóa với thời gian chờ lấy khóa. Đặt threshold cho custom event trong JFR để chỉ lưu những vùng vượt ngưỡng cần theo dõi.

Instrumentation có chi phí và có thể làm thay đổi nhẹ thời gian thực thi. Chỉ thêm vào vùng nghi vấn hoặc bật trong giai đoạn chẩn đoán; tránh tạo event cho mọi thao tác rất ngắn nếu không cần dữ liệu đó.

## 9. Lưu ý khi dùng virtual thread

Nếu ứng dụng chạy Java 21–23, virtual thread có thể bị pin vào carrier platform thread khi thực hiện thao tác blocking trong synchronized method/block. JFR event `jdk.VirtualThreadPinned` được dùng để nhận diện các lần pin vượt ngưỡng ghi nhận; cấu hình mặc định thường dùng ngưỡng 20 ms.

Tuy nhiên, cần phân biệt thời gian monitor bị giữ với pinning:

- Monitor contention xảy ra khi thread khác phải chờ lấy cùng monitor.
- Pinning xảy ra khi virtual thread không thể nhường carrier trong một tình huống blocking.
- Một vùng synchronized ngắn, chỉ cập nhật dữ liệu trong bộ nhớ, không tự động là vấn đề.
- Một vùng synchronized có I/O kéo dài có thể gây contention; trên JDK 21–23 còn có thể gây pinning.

Từ JDK 24, JEP 491 cho phép virtual thread nhường carrier khi block trong synchronized method/block, nên monitor-related pinning đã được xử lý. Pinning vẫn có thể xuất hiện trong một số tình huống khác, chẳng hạn native method hoặc foreign function. Vì vậy, khi chẩn đoán ứng dụng đang chạy trên JDK mới hơn, không nên xem mọi event pinning là bằng chứng rằng synchronized gây ra nó.

Mã nguồn được biên dịch theo Java 21 có thể chạy trên runtime mới hơn. Hành vi pinning phụ thuộc JDK runtime thực tế; hãy kiểm tra `java --version` của môi trường đang gặp vấn đề trước khi áp dụng kết luận.

## 10. Quy trình chẩn đoán thực tế

Có thể thực hiện theo trình tự sau:

1. **Xác nhận triệu chứng:** ghi nhận thời điểm latency tăng, throughput giảm hoặc số request bị chờ.
2. **Ghi JFR:** chạy recording ngắn với cấu hình `profile` trong lúc vấn đề đang xảy ra.
3. **Tìm contention:** xem `JavaMonitorEnter`, duration, monitor class, stack trace và `previousOwner`.
4. **Tìm I/O:** đối chiếu event socket/file trên thread owner trong cùng khoảng thời gian.
5. **Kiểm tra stack:** dùng JMC Lock Instances và thread dump để xác định code đang giữ monitor hoặc chờ monitor.
6. **Đo vùng tới hạn:** nếu chưa xác định được thời gian owner giữ khóa, instrument custom JFR event quanh đúng vùng nghi vấn.
7. **Sửa đúng nguyên nhân:** tách I/O khỏi monitor khi invariant cho phép, giảm thời gian giữ khóa hoặc thay đổi cấu trúc phối hợp.
8. **Ghi JFR lần nữa:** so sánh recording trước và sau trong cùng workload để xác nhận contention, I/O wait và latency đã giảm.

Không nên kết luận chỉ từ một event hoặc một thread dump. Hãy tìm mẫu lặp lại trong khoảng thời gian có tải thực tế, rồi đối chiếu thời điểm, thread owner, monitor và stack trace.

## 11. Các lỗi thường gặp khi chẩn đoán

| Cách hiểu sai | Vì sao không chính xác | Cách làm đúng |
|---|---|---|
| Duration của `JavaMonitorEnter` là thời gian giữ khóa | Đây là thời gian thread chờ vào monitor | Dùng `previousOwner` để tìm owner; instrument vùng tới hạn nếu cần thời gian giữ trực tiếp |
| `JavaMonitorWait` là mọi trường hợp chờ vào synchronized | Event này liên quan đến `Object.wait()` | Dùng `JavaMonitorEnter` để phân tích contention khi vào monitor |
| Không có event I/O nghĩa là không có I/O | Event có threshold và phạm vi instrument nhất định | Kiểm tra threshold, stack trace, native code và driver |
| Một thread dump chứng minh monitor bị giữ lâu | Dump chỉ là snapshot tại một thời điểm | So sánh nhiều dump hoặc dùng JFR để đo duration |
| Thread `BLOCKED` luôn là nguyên nhân gốc | Đây là thread đang chờ; nguyên nhân có thể nằm ở owner | Tìm `previousOwner` và phân tích stack của owner |
| Mọi synchronized đều phải thay bằng ReentrantLock | Vùng tới hạn ngắn vẫn phù hợp với monitor; runtime mới đã xử lý monitor-related pinning | Đo và chỉ sửa vùng gây contention hoặc có yêu cầu đồng bộ đặc biệt |
| JFR threshold càng thấp càng tốt | Thu nhiều event hơn làm recording lớn và tăng overhead | Bắt đầu với cấu hình mặc định, chỉ hạ threshold trong lần đo ngắn |

## 12. Nguyên tắc áp dụng cho Java 21

Khi điều tra vùng giữ monitor lâu hoặc có I/O bên trong, hãy kết hợp JFR, JMC và thread dump thay vì dựa vào một dấu hiệu riêng lẻ. `JavaMonitorEnter` chỉ ra nơi thread chờ và owner trước đó; các event socket/file cho biết thread đang làm gì trong khoảng thời gian liên quan; custom JFR event có thể đo trực tiếp thời gian giữ vùng tới hạn do ứng dụng kiểm soát.

Nếu runtime là JDK 21–23, chú ý thêm `jdk.VirtualThreadPinned` khi ứng dụng dùng virtual thread. Nếu runtime là JDK 24 trở lên, monitor-related pinning đã được xử lý bởi JEP 491, nhưng lock contention và thời gian giữ monitor dài vẫn có thể làm giảm throughput.

Mục tiêu của chẩn đoán là tìm đúng vùng tới hạn gây chờ, xác định nó đang giữ monitor trong lúc thực hiện công việc nào, rồi thay đổi tối thiểu để bảo toàn invariant và giảm thời gian chờ của các thread khác.

## Tài liệu tham khảo

- [Oracle Java SE 21 — Troubleshoot Performance Issues Using Flight Recorder](https://docs.oracle.com/en/java/javase/21/troubleshoot/troubleshoot-performance-issues-using-jfr.html)
- [Oracle Java SE 21 — The jcmd Command](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html)
- [Oracle Java SE 21 — Virtual Threads](https://docs.oracle.com/en/java/javase/21/core/virtual-threads.html)
- [Oracle Java SE 21 API — Thread.State](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Thread.State.html)
- [Oracle Java SE 21 API — jdk.jfr](https://docs.oracle.com/en/java/javase/21/docs/api/jdk.jfr/jdk/jfr/package-summary.html)
- [JEP 491 — Synchronize Virtual Threads without Pinning](https://openjdk.org/jeps/491)
