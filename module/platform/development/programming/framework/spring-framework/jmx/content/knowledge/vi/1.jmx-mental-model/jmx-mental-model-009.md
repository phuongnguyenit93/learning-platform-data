# Ranh giới giữa quan sát, chẩn đoán và điều khiển thay đổi trạng thái trong Spring Framework JMX

## Mục tiêu

Khi nhìn một ứng dụng Spring qua Java Management Extensions (JMX), điều quan trọng không chỉ là biết cách xuất một MBean hay gọi một operation. Người vận hành cần phân biệt ba loại hành động có mức độ tác động khác nhau: **quan sát** hệ thống đang như thế nào, **chẩn đoán** vì sao nó có biểu hiện đó, và **điều khiển** để hệ thống chuyển sang trạng thái khác.

Sau bài này, bạn có thể:
- Phân loại attribute, operation và notification của MBean theo tác động thực tế thay vì chỉ dựa vào tên hoặc kiểu API.
- Xác định ranh giới an toàn giữa đọc số liệu, chạy phép kiểm tra và thay đổi trạng thái của ứng dụng Spring.
- Thiết kế một bề mặt quản trị JMX có quyền tối thiểu, tính ổn định và khả năng truy vết.
- Đánh giá rủi ro của các thao tác như refresh cache, đổi mức logging, tạm dừng worker, reset thống kê hoặc kích hoạt reconnect.
- Xây dựng tư duy xử lý sự cố: có bằng chứng, giả thuyết, hành động có kiểm soát và kiểm chứng kết quả.

## 1. Ba tầng hành động và câu hỏi của từng tầng

Hãy hình dung JMX như bảng điều khiển trong phòng máy. Cùng một giao diện có thể hiển thị nhiệt độ, cho phép chạy bài tự kiểm tra và chứa nút thay đổi cách máy vận hành. Ba hành động này không có cùng mức an toàn.

| Tầng | Câu hỏi | Ví dụ trong ứng dụng Spring | Tác động mong đợi |
|---|---|---|---|
| Quan sát (observation) | Điều gì đang xảy ra? | Đọc kích thước hàng đợi, số kết nối đang dùng, trạng thái worker | Không làm thay đổi trạng thái nghiệp vụ |
| Chẩn đoán (diagnosis) | Vì sao điều đó xảy ra? | Lấy bản tóm tắt pool, tính tình trạng backlog, chạy health probe | Có thể tốn tài nguyên hoặc tạo hoạt động phụ |
| Điều khiển (control) | Cần thay đổi điều gì? | Pause/resume, thay đổi cấu hình runtime, reset cache, trigger reconnect | Chủ ý thay đổi trạng thái hoặc hành vi |

Đây là **phân loại theo hiệu ứng thực tế**, không phải tên phương thức. Một method tên `getReport()` có thể quét hàng triệu bản ghi; một operation tên `checkConnection()` có thể tạo kết nối thật; một thuộc tính có setter là bề mặt điều khiển. Ngược lại, một operation chỉ trả về snapshot đã có vẫn có thể thuộc nhóm quan sát.

Một cách nhận diện nhanh:

1. **Đọc**: Kết quả chủ yếu là dữ liệu; cùng điều kiện, gọi lại không nên làm hệ thống thay đổi đáng kể.
2. **Chẩn đoán**: Kết quả là bằng chứng giúp xác nhận hoặc loại bỏ giả thuyết; tác vụ có thể tiêu tốn CPU, I/O, lock hoặc gọi downstream.
3. **Điều khiển**: Mục tiêu là đổi state, cấu hình hoặc luồng xử lý; cần xét quyền, điều kiện trước, tác dụng phụ và phương án khôi phục.

Ranh giới không luôn tuyệt đối. Đọc metric cập nhật bộ đếm truy cập hoặc tạo object tạm là tác dụng phụ kỹ thuật nhỏ; việc gọi một health check thực hiện truy vấn DB thật là chẩn đoán có tác động; reset bộ đếm là thao tác thay đổi trạng thái quản trị, dù không sửa dữ liệu nghiệp vụ.

## 2. Bề mặt JMX nói gì và chưa nói gì?

JMX trình bày tài nguyên quản trị dưới dạng MBean, thường được đặt tên bằng `ObjectName`. Công cụ như JConsole hoặc Java Mission Control có thể thấy các **attributes**, **operations**, **notifications** và metadata. Với Spring Framework, `@ManagedResource`, `@ManagedAttribute`, `@ManagedOperation`, `MBeanExporter` và `@EnableMBeanExport` giúp đưa đối tượng Spring ra JMX.

Tuy nhiên, dạng kỹ thuật của thành phần không tự xác nhận tác động:

- **Attribute chỉ đọc**: thường dành cho quan sát, nhưng getter có thể thực hiện tính toán nặng hoặc truy vấn bên ngoài.
- **Attribute có thể ghi**: setter là một lệnh điều khiển. Ghi giá trị có thể kích hoạt reload, reschedule hoặc ảnh hưởng request mới.
- **Operation**: có thể chỉ tính một kết quả, chạy probe, reset một trạng thái hoặc điều khiển nghiệp vụ. Metadata và tên operation không thay thế việc đọc hợp đồng hành vi.
- **Notification**: thông báo một sự kiện đã xảy ra; subscription và emission vẫn có chi phí, và notification có thể thiếu, trễ hoặc lặp tùy thiết kế.

Vì vậy không nên lấy kết luận “operation là nguy hiểm, getter là an toàn” làm chính sách. Chính sách phải nêu **hiệu ứng**, **chi phí**, **mức nhạy cảm của dữ liệu** và **quyền sử dụng** cho từng mục.

### 2.1 Một bảng hợp đồng quản trị mẫu

| JMX member | Phân loại | Hợp đồng cần công bố |
|---|---|---|
| `QueueDepth` (read-only) | Quan sát | Snapshot tại thời điểm đọc; không đảm bảo số liệu giữ nguyên ngay sau đó |
| `LastFailureSummary` (read-only) | Quan sát, dữ liệu nhạy cảm | Che thông tin cá nhân/token; giới hạn độ dài và chi phí tạo dữ liệu |
| `diagnoseBacklog()` | Chẩn đoán | Có thể quét metadata; giới hạn thời gian, kích thước kết quả, tần suất gọi |
| `probeDatabase()` | Chẩn đoán | Gọi DB thật, có timeout; kết quả probe không đồng nghĩa toàn bộ hệ thống khỏe |
| `setPauseRequested(true)` | Điều khiển | Chỉ tác động đến xử lý mới; công việc đang chạy có thể hoàn tất |
| `resetCounters()` | Điều khiển | Mất baseline metric trong bộ nhớ; cần lưu bằng chứng trước khi reset |
| `clearCache()` | Điều khiển | Tăng tải hệ thống dữ liệu sau khi cache bị xóa; có thể gây hiệu ứng lan truyền |

Bảng này nên có mặt trong tài liệu vận hành. Một người nhìn thấy phương thức trên console không thể tự suy ra đầy đủ hậu quả của nó.

## 3. Tư duy về trạng thái: bạn đang đọc hay đang đổi cái gì?

Trạng thái ứng dụng không phải một biến đơn. Có thể chia thành:

- **Trạng thái quan sát được**: số request, độ sâu queue, latency, số connection và timestamp gần nhất.
- **Trạng thái runtime điều chỉnh được**: pause flag, mức log, số worker theo giới hạn, chế độ bảo trì.
- **Trạng thái nghiệp vụ**: đơn hàng, giao dịch, thanh toán, sự kiện đã phát ra; có nguồn sự thật riêng.
- **Trạng thái bên ngoài**: database, broker, dịch vụ khác, node khác hoặc cơ sở hạ tầng.

Một thao tác JMX có thể đổi trạng thái runtime cục bộ nhưng không tự động đổi trạng thái của các node còn lại. Ví dụ, `pause()` chỉ trên một instance Spring Boot chạy trong cụm ba node không phải nút “dừng toàn hệ thống”. Tương tự, `clearCache()` ở JVM A chưa chắc xóa cache ở JVM B hoặc cache phân tán.

Phân biệt tiếp giữa **ý định điều khiển** và **kết quả đã xảy ra**. Đặt `pauseRequested=true` chỉ thể hiện yêu cầu. Trạng thái `paused=true` nên phản ánh rằng bộ xử lý thực sự ngừng nhận việc mới. Nếu đây là quá trình bất đồng bộ, hệ thống nên công bố `requestedState`, `effectiveState`, `lastTransitionTime` và `lastTransitionError` thay vì trả về thành công sớm.

### 3.1 Sơ đồ tư duy cho một thao tác

```text
Cần hiểu vấn đề
      |
      v
Đọc trạng thái và lịch sử gần nhất
      |
      v
Có đủ bằng chứng? -- Không --> Chạy chẩn đoán có giới hạn
      |                              |
     Có <----------------------------+
      |
      v
Có thật sự cần đổi trạng thái?
      |                |
     Không             Có
      |                |
Theo dõi tiếp   Kiểm tra quyền, phạm vi,
                tiền điều kiện, rủi ro
                       |
                       v
                Thực thi một thay đổi
                       |
                       v
                Đọc lại effective state,
                metric và tác động phụ
```

Không phải lần phát hiện lỗi nào cũng cần điều khiển. Có tình huống việc quan sát thêm hoặc điều chỉnh nguyên nhân gốc bên ngoài JVM là quyết định phù hợp hơn.

## 4. Ví dụ Spring JMX: tách đọc trạng thái khỏi yêu cầu pause/resume

Ví dụ sau minh họa cách xuất MBean cho một bộ xử lý background. Các phương thức quan sát trả về snapshot đơn giản; lệnh điều khiển có tên hành động rõ ràng. Chính sách xác thực, ủy quyền, audit và kiểm soát phạm vi phải được cấu hình thêm tại lớp quản trị và hạ tầng, vì annotation Spring **không tự tạo hệ thống phân quyền**.

```java
import java.time.Instant;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicLong;
import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedOperation;
import org.springframework.jmx.export.annotation.ManagedResource;
import org.springframework.stereotype.Component;

@Component
@ManagedResource(
    objectName = "learning.operations:type=WorkerControl,name=ImportWorker",
    description = "Observation and controlled lifecycle actions")
public class ImportWorkerControl {

    private final AtomicBoolean pauseRequested = new AtomicBoolean();
    private final AtomicBoolean acceptingNewWork = new AtomicBoolean(true);
    private final AtomicLong completedJobs = new AtomicLong();
    private volatile String lastTransitionTime = Instant.now().toString();

    @ManagedAttribute(description = "Requested pause intent")
    public boolean isPauseRequested() {
        return pauseRequested.get();
    }

    @ManagedAttribute(description = "Whether new work is actually accepted")
    public boolean isAcceptingNewWork() {
        return acceptingNewWork.get();
    }

    @ManagedAttribute(description = "Completed job count since process start")
    public long getCompletedJobs() {
        return completedJobs.get();
    }

    @ManagedAttribute(description = "Timestamp of last effective transition")
    public String getLastTransitionTime() {
        return lastTransitionTime;
    }

    @ManagedOperation(description = "Request a pause of new work")
    public void requestPause() {
        pauseRequested.set(true);
        // The actual worker loop must observe this intent.
    }

    @ManagedOperation(description = "Request resuming new work")
    public void requestResume() {
        pauseRequested.set(false);
        // The actual worker loop must observe this intent.
    }

    // Called only by the worker lifecycle when state really changes.
    public void recordAcceptingNewWork(boolean accepting) {
        acceptingNewWork.set(accepting);
        lastTransitionTime = Instant.now().toString();
    }

    // Called after a job actually completes.
    public void recordCompletedJob() {
        completedJobs.incrementAndGet();
    }
}
```

Có thể bật exporter bằng cấu hình phù hợp với ứng dụng:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableMBeanExport;

@Configuration
@EnableMBeanExport
public class JmxConfiguration {
}
```

Trong ứng dụng Spring Boot, cần kiểm tra cấu hình JMX hiện hành, cách đăng ký MBean và khả năng trùng `ObjectName` trước khi dùng đồng thời các cơ chế export. Đối tượng ví dụ chỉ là **adapter điều khiển**, chưa phải một worker hoàn chỉnh. Phần xử lý nền thực tế phải đọc `pauseRequested` tại điểm an toàn và gọi `recordAcceptingNewWork` khi quá trình chuyển trạng thái thực sự có hiệu lực. Nếu pause có thể thất bại hoặc kéo dài, nên mở rộng hợp đồng với trạng thái `PAUSING`, lỗi gần nhất và thời điểm chuyển đổi.

Từ góc nhìn người vận hành:

1. Đọc `PauseRequested` và `AcceptingNewWork` là **quan sát**.
2. So sánh hai giá trị, lịch sử chuyển đổi, queue và error là **chẩn đoán**.
3. Gọi `requestPause()` hoặc `requestResume()` là **điều khiển**.
4. Đọc lại hai giá trị sau operation là **xác minh hiệu quả**, tránh nhầm “operation được gọi thành công” với “hệ thống đã đạt trạng thái mong muốn”.

## 5. Vì sao một phép chẩn đoán có thể nguy hiểm?

Chẩn đoán nằm giữa đọc và điều khiển, nhưng không phải “đọc vô hại”. Một operation gọi là `dumpAllSessions()` có thể tạo bản sao lớn trong heap; `checkAllDependencies()` có thể gọi đồng thời nhiều dịch vụ và góp phần làm chúng quá tải; `threadDump()` hoặc phép chụp snapshot rộng có chi phí trong thời điểm JVM vốn đang chịu áp lực.

Thiết kế chẩn đoán an toàn thường có các đặc tính:

- **Giới hạn phạm vi**: chỉ một pool, một queue, một partition, một khoảng thời gian hoặc top-N.
- **Giới hạn tài nguyên**: timeout, mức đồng thời, số bản ghi, số byte kết quả, tốc độ gọi.
- **Không lộ dữ liệu**: chỉ xuất summary đã lọc; tránh password, token, raw payload và thông tin định danh người dùng.
- **Ngữ nghĩa rõ ràng**: báo thời điểm snapshot, độ trễ và dữ liệu có thể không nhất quán giữa nhiều chỉ số.
- **Thất bại có kiểm soát**: nếu phụ thuộc bên ngoài timeout, trả trạng thái chẩn đoán thất bại; không tự bật chế độ sửa chữa hoặc retry vô hạn.
- **Truy vết**: ghi ai chạy, khi nào, mục tiêu và mã tương quan nếu có.

Ví dụ `diagnoseBacklog()` nên có thể trả về một summary giới hạn như `queued=420, oldestAgeSeconds=95, sampledAt=...` thay vì cố gắng serialize toàn bộ job trong queue. Nếu summary cần quét, tài liệu cần nêu chi phí ước tính và giới hạn.

## 6. Điều khiển là thay đổi: cần hợp đồng mạnh hơn

Một operation thay đổi trạng thái nên trả lời sáu câu hỏi trước khi được đưa lên JMX:

1. **Ai** có quyền gọi? Quyền chỉ quan sát có được tách khỏi quyền điều khiển không?
2. **Đổi cái gì**? Một bean, một JVM, một tenant, một shard hay toàn cụm?
3. **Điều kiện trước** là gì? Có cấm gọi khi đang shutdown, đang migration hoặc đang xử lý giao dịch nhạy cảm không?
4. **Hiệu lực khi nào**? Đồng bộ hay bất đồng bộ, ngay hay sau khi job đang chạy kết thúc?
5. **Gọi lặp thì sao**? Idempotent, báo đã ở trạng thái mong muốn hay gây side effect lặp?
6. **Phục hồi thế nào**? Có thao tác ngược, thời gian hiệu lực, auto-expiry hay phải restart?

Một điều khiển tốt nên giới hạn ảnh hưởng (blast radius), kiểm tra input, trả kết quả có ý nghĩa và ghi audit. Ví dụ, thay đổi `logLevel=DEBUG` có thể làm tăng I/O và ghi dữ liệu nhạy cảm; nên cho phép trong phạm vi logger được duyệt, có thời hạn và tự quay lại mức ban đầu. Reset cache có thể gây cache stampede; nên hỗ trợ một key/prefix đã xác minh thay vì mặc định xóa toàn bộ.

Không nên dùng JMX như API nghiệp vụ tùy tiện. Giao dịch tạo đơn hàng, hoàn tiền hay sửa dữ liệu khách hàng cần đi qua ứng dụng có xác thực, kiểm tra bất biến nghiệp vụ, audit và kiểm soát giao dịch tương ứng. Việc gắn `@ManagedOperation` vào service không tự cung cấp các đảm bảo ấy.

### 6.1 Idempotency không đồng nghĩa không rủi ro

`pause()` có thể idempotent về trạng thái: gọi hai lần vẫn chỉ là “paused”. Nhưng việc gọi ở thời điểm sai vẫn gián đoạn hệ thống. `clearCache()` đôi khi đạt cùng trạng thái cache rỗng sau hai lần gọi, nhưng hai lần gọi có thể tạo hai đợt tải lại dữ liệu. Do đó, idempotency là một thuộc tính hữu ích, **không thay thế** kiểm soát quyền, thời điểm và ảnh hưởng.

### 6.2 Kiểm soát cạnh tranh và kết quả

Trong hệ thống nhiều thread, đọc rồi ra quyết định không phải thao tác nguyên tử:

```text
T0: Operator A đọc trạng thái RUNNING
T1: Operator B yêu cầu STOPPING
T2: Operator A gọi refresh/restart dựa trên snapshot cũ
```

Nếu hai lệnh xung đột, nên có state machine và cơ chế từ chối thao tác sai tiền điều kiện. Với hành động quan trọng, một phiên bản trạng thái (state version) hoặc yêu cầu có điều kiện giúp tránh áp dụng lệnh trên snapshot lỗi thời. JMX API không tự cung cấp tính nguyên tử nghiệp vụ này; logic ứng dụng phải đảm nhận.

## 7. Bảo mật: đọc cũng có thể là quyền nhạy cảm

JMX có thể để lộ cấu hình, topology, số liệu vận hành, exception, tên thread và thông tin liên quan dữ liệu người dùng. Vì thế một kết nối JMX “chỉ đọc” vẫn có thể chứa thông tin nhạy cảm.

Khi bật remote JMX, phải xét xác thực, phân quyền, mã hóa đường truyền, giới hạn network và cấu hình endpoint; không để cổng quản trị mở công khai. Trong nhiều cách triển khai, truy cập MBeanServer/JMX connector với quyền rộng có thể thực thi operation ngoài dự định. Quyền được áp ở connector, MBeanServer hoặc lớp bảo vệ phù hợp cần được kiểm chứng thực tế; nhãn “read-only” trong tài liệu không đủ để chặn lời gọi.

Nguyên tắc vận hành:

- Ưu tiên kênh quản trị nội bộ, xác thực mạnh và mã hóa.
- Phân biệt người đọc số liệu với người được gọi operation thay đổi trạng thái.
- Giảm số operation được xuất; không export public method chỉ vì tiện.
- Ẩn bí mật và dữ liệu cá nhân khỏi attribute, notification và exception message.
- Ghi audit các lệnh điều khiển với danh tính, đích, tham số an toàn, kết quả và thời điểm.
- Kiểm tra giới hạn theo **instance**, đặc biệt trong Kubernetes hoặc cụm nhiều node.

Spring JMX annotations chủ yếu mô tả và export tài nguyên; chúng **không phải** lớp bảo mật tự động cho từng operation.

## 8. Tình huống thực tế: backlog tăng trong một worker

Giả sử queue xử lý import của một Spring service tăng từ 20 lên 2.000 job và tỷ lệ hoàn thành giảm. Sự khác nhau giữa ba tầng thể hiện rất rõ.

**Bước 1 — Quan sát:** Đọc `QueueDepth`, `CompletedJobs`, `ActiveWorkers`, `OldestJobAge`, thời gian gần nhất có lỗi. Quan sát xu hướng qua nhiều thời điểm vì một snapshot đơn có thể đánh lừa. Đồng thời kiểm tra dashboard metric và log, không dựa duy nhất vào JMX.

**Bước 2 — Chẩn đoán:** Giả thuyết gồm downstream chậm, lỗi retry, worker bị pause, lock contention hoặc số consumer không đủ. Chạy operation summary có giới hạn, đối chiếu connection pool và độ trễ dependency. Không gọi đồng loạt probe nặng trên mọi node khi hệ thống đang quá tải.

**Bước 3 — Quyết định:** Nếu downstream đang lỗi, tăng worker có thể làm tình hình tệ hơn. Nếu queue là kết quả của thay đổi cấu hình, khôi phục cấu hình có kiểm soát có thể hợp lý. Nếu đang cần giảm áp lực DB, yêu cầu pause xử lý mới có thể hữu ích, nhưng phải xét dữ liệu tồn đọng và SLA.

**Bước 4 — Điều khiển:** Người có quyền gọi một operation với phạm vi rõ ràng, ví dụ `requestPause()` trên đúng instance. Ghi lại lý do, giá trị trước thay đổi và người thực hiện.

**Bước 5 — Xác minh:** Đọc `PauseRequested`, `AcceptingNewWork`, số job đang chạy và độ sâu queue; kiểm tra rằng không có job mới được lấy sau khi pause có hiệu lực. Nếu trạng thái không đạt trong giới hạn cho phép, không tự động gọi lặp vô hạn.

Một runbook ngắn giúp tránh phản xạ “có lỗi thì bấm reset”:

```text
Triệu chứng -> Snapshot có thời điểm -> Giả thuyết -> Probe giới hạn
-> Đánh giá tác động -> Lệnh có quyền & tiền điều kiện
-> Kiểm tra effective state -> Theo dõi hậu quả -> Ghi nhận
```

## 9. Những nhầm lẫn thường gặp

**“Getter luôn vô hại.”** Getter có thể tính toán tốn kém, chặn trên lock, gọi mạng hoặc lộ secret. Đánh giá implementation và hợp đồng của getter.

**“Có thể gọi operation thì nên gọi khi sự cố.”** Có khả năng thực thi không đồng nghĩa có lý do hoặc quyền thực thi. Cần bằng chứng và quy trình quyết định.

**“JMX command thành công nghĩa là ứng dụng đã chuyển trạng thái.”** Nếu lệnh chỉ đặt cờ hoặc enqueue yêu cầu, cần đọc effective state hoặc quan sát hành vi.

**“Pause một instance nghĩa là pause toàn cụm.”** MBean thường thuộc một JVM. Muốn điều khiển cluster phải có cơ chế phối hợp và tài liệu phạm vi rõ ràng.

**“Reset metric là thao tác read-only.”** Reset thay đổi dữ liệu quan sát được, phá continuity của chuỗi thời gian và có thể xóa dấu vết chẩn đoán.

**“Chỉ cần đặt tên `safeCheck()` là chẩn đoán an toàn.”** Phải giới hạn tài nguyên, tần suất, dữ liệu trả về và tác động tới dependency.

**“Một MBean đã export thì tự có phân quyền theo operation.”** Các annotation export của Spring không thay thế cấu hình connector, role và kiểm tra truy cập thực tế.

## 10. Bộ câu hỏi thiết kế trước khi xuất một MBean

Với mỗi attribute hoặc operation, ghi rõ:

| Tiêu chí | Câu hỏi kiểm tra |
|---|---|
| Mục đích | Quan sát, chẩn đoán hay điều khiển? |
| Dữ liệu | Trả snapshot nào, có nhạy cảm hoặc có thể lỗi thời không? |
| Tài nguyên | Tốn CPU/heap/I/O/lock/downstream bao nhiêu, giới hạn ra sao? |
| Hiệu ứng phụ | Có thay đổi state, làm mất metric hay kích hoạt công việc không? |
| Phạm vi | Tác động đến thread, bean, instance, tenant hay cluster? |
| Quyền | Ai được đọc, ai được thực thi, audit nằm ở đâu? |
| Đồng thời | Khi hai operator gọi cùng lúc hoặc trạng thái đổi giữa chừng thì sao? |
| Thất bại | Timeout, partial success và thông báo lỗi có nghĩa gì? |
| Khôi phục | Có lệnh đảo ngược, tự hết hạn hoặc runbook rollback không? |
| Xác minh | Đọc metric hoặc effective state nào để chứng minh kết quả? |

Nếu không trả lời được các câu hỏi về hiệu ứng, phạm vi và quyền, operation điều khiển chưa đủ rõ để đưa lên bề mặt vận hành.

## 11. Bài tập tư duy

Cho các thành phần JMX sau:

1. `getCacheHitRatio()`: đọc số liệu từ counters đang có.
2. `scanSlowQueries(1000)`: quét nhật ký truy vấn gần nhất, tốn CPU và bộ nhớ.
3. `setConsumerCount(16)`: điều chỉnh số consumer đang hoạt động.
4. `getRecentErrors()`: trả về stack trace và request parameters chưa lọc.
5. `resetRetryStatistics()`: đặt lại bộ đếm retry.
6. `pingDownstream()`: gửi một request thật tới service khác.

Hãy phân loại và nêu một điều kiện an toàn cho mỗi mục. Gợi ý đáp án: (1) quan sát, cần định nghĩa khoảng tính ratio; (2) chẩn đoán, giới hạn phạm vi và tài nguyên; (3) điều khiển, kiểm tra dải hợp lệ, khả năng tải và quyền; (4) quan sát có rủi ro dữ liệu nhạy cảm, phải lọc; (5) điều khiển trạng thái metric, lưu baseline trước khi reset; (6) chẩn đoán có tác động mạng, đặt timeout/rate limit.

Bài tập mở rộng: thiết kế `WorkerControlMBean` có bốn thuộc tính read-only (`RequestedState`, `EffectiveState`, `LastTransitionTime`, `LastTransitionError`) và hai operation (`requestPause`, `requestResume`). Viết state machine xử lý trạng thái `RUNNING → PAUSING → PAUSED → RESUMING → RUNNING`, mô tả điểm an toàn để dừng nhận job, hành vi khi gọi lặp và cách người vận hành xác minh kết quả.

## Kết luận

Trong Spring Framework JMX, **quan sát** xây dựng nhận thức về trạng thái, **chẩn đoán** kiểm tra nguyên nhân với chi phí được kiểm soát, và **điều khiển** chủ ý chuyển trạng thái theo quyền hạn và tiền điều kiện. Ranh giới nằm ở tác dụng thật của từng MBean member, phạm vi ảnh hưởng và điều kiện vận hành. Một bề mặt JMX tốt giúp người vận hành biết rõ điều gì đang diễn ra, vì sao có thể diễn ra và khi nào một hành động thay đổi trạng thái là hợp lệ, đồng thời cung cấp bằng chứng để kiểm tra hành động đó đã đạt hiệu quả hay chưa.
