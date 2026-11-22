# Kiểm thử sự kiện JFR bị thiếu do cấu hình, ngưỡng hoặc thời điểm quan sát

## 1. Bài toán: không thấy event chưa chắc ứng dụng không phát event

Trong **Java Flight Recorder (JFR)**, một sự kiện có thể đã được ứng dụng tạo ra nhưng **không xuất hiện trong kết quả phân tích**. Nguyên nhân không chỉ nằm ở code phát sự kiện: bản ghi có thể chưa chạy, event type bị tắt, duration không đủ ngưỡng, event chưa được `commit()`, phạm vi thời gian quá hẹp, callback lọc sai tên, stream chưa được bắt đầu hoặc file được đọc không phải file vừa ghi.

Muốn kiểm thử đúng, hãy tách **hai tầng**:

1. **Tầng ghi (*production/recording*)**: JVM có tạo và lưu event vào recording không? Kiểm tra trạng thái `Recording`, setting `enabled`, `threshold`, cơ chế `period` khi có periodic event, thời điểm `commit()` và phạm vi dữ liệu được giữ.
2. **Tầng đọc (*consumption/observation*)**: event có tồn tại trong tệp `.jfr` nhưng bị loại khỏi phần ta đang xem hay không? Kiểm tra `EventStream.openFile`, `onEvent`, `setStartTime`, `setEndTime`, `start`/`startAsync`, tên event, thời điểm flush và đúng tệp nguồn.

**Nguyên tắc kiểm thử:** không thấy callback **không đồng nghĩa** event không có trong file; thấy `event.isEnabled() == true` **không đồng nghĩa** event sẽ qua threshold; đặt `withPeriod` cũng **không bảo đảm** số lần phát chính xác trong một khoảng thời gian ngắn.

Bài dùng các API JFR **ổn định, còn áp dụng trong Java hiện đại**, với chương trình biên dịch bằng **Java 17+**. Event Streaming có từ JDK 14 (JEP 349), nhưng các ví dụ ở đây không dùng preview, API nội bộ hoặc cơ chế legacy.

## 2. Bản đồ các điểm một event có thể “biến mất”

```text
Ứng dụng muốn ghi sự kiện
          │
          ▼
[1] Recording đang chạy?
    ├─ Không → sự kiện không được ghi vào recording đó
    └─ Có
          │
          ▼
[2] Event type đã enabled?
    ├─ Không → không ghi
    └─ Có
          │
          ▼
[3] Event có được commit và vượt điều kiện lọc?
    ├─ Chưa commit / duration dưới threshold → không ghi
    └─ Có
          │
          ▼
[4] Event nằm trong dữ liệu retained/dumped?
    ├─ Không → không có trong file được phân tích
    └─ Có → sự kiện tồn tại trong .jfr
          │
          ▼
[5] File/stream đang đọc có đúng nguồn?
    ├─ Không → không quan sát được sự kiện mong muốn
    └─ Có
          │
          ▼
[6] Có lọc sai tên hoặc sai cửa sổ thời gian?
    ├─ Có → callback không thấy event dù file có event
    └─ Không
          │
          ▼
[7] Stream đã start, xử lý xong và chưa bị close sớm?
    ├─ Không → xử lý không đầy đủ hoặc không có callback
    └─ Có → consumer nhận event
```

Sơ đồ là **quy trình chẩn đoán**, không mô tả thứ tự chính xác của mọi bộ lọc bên trong JVM. Các yếu tố khác như nhiều recording đồng thời, file hỏng, hệ thống hết dung lượng, event metadata, mức lưu trữ hoặc chính code callback cũng có thể ảnh hưởng.

**Cách chứng minh nguyên nhân:** xây dựng **một sự kiện đối chứng được kỳ vọng có mặt** và một sự kiện **cố ý bị loại**. Đọc file với bộ lọc tối thiểu trước, rồi mới thêm các điều kiện quan sát để xác định tầng gây thiếu.

## 3. Thiết lập một baseline có thể lặp lại

Giả sử dùng ba event types tự định nghĩa:

```java
import jdk.jfr.Event;
import jdk.jfr.Name;

@Name("demo.Work")
class Work extends Event {
    String label;
}

@Name("demo.Marker")
class Marker extends Event {
    String label;
}

@Name("demo.Hidden")
class Hidden extends Event {
    String label;
}
```

Đây là **khai báo minh họa**, không phải tệp chạy độc lập; toàn bộ các class, vòng đời recording và kiểm thử được cung cấp tại mục 10.

Mục tiêu baseline:

- `demo.Work`: một công việc **nhanh hơn ngưỡng** bị loại, một công việc **dài hơn ngưỡng** được ghi.
- `demo.Marker`: hai instant events phát **trong thời gian recording chạy**; sự kiện trước `start()` và sau `stop()` không thuộc recording đó.
- `demo.Hidden`: type bị `disable`; gọi `commit()` cũng không làm nó xuất hiện trong recording.
- Khi đọc file, callback dùng đúng tên `demo.Marker` nhìn thấy hai marker; callback dùng tên sai `demo.Makr` nhận 0; bộ lọc `setStartTime(...)` đặt giữa hai marker chỉ giữ marker sau.

Bộ kiểm thử này tạo **dữ liệu nguồn xác định**, nên dễ phân biệt thiếu do recorder và thiếu do consumer. Không nên dùng một built-in event như `jdk.CPULoad` làm kiểm thử duy nhất nếu lượng hoạt động của JVM thay đổi theo môi trường.

## 4. Thiếu do recording chưa chạy hoặc đã dừng

### 4.1. `Recording.start()` và `Recording.stop()` xác lập phạm vi thu thập

```java
try (Recording recording = new Recording()) {
    recording.enable("demo.Marker").withoutThreshold();

    // Event commit trước thời điểm này không thuộc recording.
    recording.start();

    // Event commit trong khoảng recording đang chạy có thể được thu thập.

    recording.stop();
    // Event commit sau thời điểm này không thuộc recording vừa dừng.
}
```

Một sự kiện `Event.commit()` chỉ có thể được ghi vào JFR khi điều kiện ghi của runtime cho phép, trong đó ít nhất một recording cần đang chạy và event type được bật. Đối với ví dụ **chỉ có một recording**, `new Marker().isEnabled()` sẽ trả `false` trước `start()` và sau `stop()`, còn trong khoảng ghi có thể trả `true`.

**Lưu ý về nhiều recording:** `Event.isEnabled()` hỏi trạng thái hiệu lực ở **JVM**: nó có thể trả `true` nếu một recording khác vẫn đang chạy và bật loại event. Vì vậy khi kiểm thử việc một recording cụ thể thiếu event, cần cô lập các recording hoặc xác nhận thiết lập của từng recording; không dùng một lần `isEnabled()` làm bằng chứng tuyệt đối về dữ liệu trong file riêng.

### 4.2. Mốc thời gian cần ghi rõ

| Hành động | Ý nghĩa khi kiểm thử một recording duy nhất |
| --- | --- |
| `event.commit()` trước `recording.start()` | Không thể được thu thập vào recording chưa chạy |
| `event.commit()` sau `recording.start()` và trước `stop()` | Có cơ hội được ghi nếu enabled, qua threshold và các điều kiện khác |
| `event.commit()` sau `recording.stop()` | Không thuộc recording đã dừng |
| `recording.dump(path)` sau `stop()` | Xuất dữ liệu đã được thu thập/giữ lại vào tệp JFR |
| `recording.getStartTime()` và `getStopTime()` | Hỗ trợ xác định thời điểm recording, nhưng không thay thế việc kiểm tra timestamp từng event |

**Đừng suy ra từ thời gian tạo file:** một file `.jfr` có thể được dump sau khi event xảy ra. Metadata của file hoặc thời gian sửa file không phải bằng chứng rằng từng event diễn ra lúc đó.

### 4.3. `commit()` không đồng nghĩa “chắc chắn có trong file”

Ngay cả khi một event được tạo bên trong khoảng recording chạy, nó vẫn có thể không xuất hiện vì type chưa enabled, duration dưới threshold, điều kiện JFR khác hoặc dữ liệu bị loại theo retention. Hãy xem cả **settings** lẫn **file được dump**, không chỉ số lần gọi constructor của event.

## 5. Thiếu do `enabled`: event type bị tắt hoặc sai tên

Bật và tắt loại event trong một recording:

```java
try (Recording recording = new Recording()) {
    recording.enable("demo.Work");
    recording.disable("demo.Hidden");

    recording.start();
    // Tạo các event ở đây.
    recording.stop();
}
```

`recording.disable("demo.Hidden")` đặt loại event tương ứng thành disabled cho recording này; `new Hidden().commit()` vẫn là lời gọi Java hợp lệ, nhưng **không làm event đó xuất hiện trong recording đã tắt loại event**.

### 5.1. Kiểm tra settings theo tên event

```java
String enabled = recording.getSettings().get("demo.Work#enabled");
String threshold = recording.getSettings().get("demo.Work#threshold");
```

Đây là **trích đoạn trong phạm vi có biến `recording`**. Khi dùng `enable("tên-event")`/`disable("tên-event")`, `Recording.getSettings()` chứa các khóa có dạng `eventName#settingName` cho các setting đã cấu hình. Nếu dùng overload `enable(MyEvent.class)`, runtime có thể dùng **event ID** thay cho tên trong key. Đừng hardcode ID này hoặc giả định rằng map hiển thị mọi setting mặc định chưa được thiết lập tường minh.

Trong lỗi thực tế, hãy đối chiếu:

- `@Name("demo.Work")` trong class khai báo event.
- Chuỗi dùng cho `Recording.enable("demo.Work")`.
- Chuỗi dùng trong `EventStream.onEvent("demo.Work", callback)`.
- `EventType.getName()` của sự kiện **thực sự có trong file**.

Lỗi `"demo.Makr"` thay `"demo.Marker"` sẽ khiến callback tên sai nhận **0** sự kiện, **ngay cả khi file vẫn có các event `demo.Marker`**. Đây là lỗi **quan sát**, không phải lỗi ghi.

### 5.2. `isEnabled()` và `shouldCommit()` không tương đương

`jdk.jfr.Event` cung cấp hai phép kiểm tra:

| API | Ý nghĩa | Điều nó **không** chứng minh |
| --- | --- | --- |
| `event.isEnabled()` | Có recording đang chạy và setting `enabled` cho event type cho phép ghi ở mức JVM | Không chứng minh duration qua threshold hoặc event đã `commit()` |
| `event.shouldCommit()` | Event đang đáp ứng điều kiện enabled và duration threshold hiệu lực | Không chứng minh file cuối cùng đang đọc là file đúng hoặc đã chứa event |
| `event.commit()` | Đề nghị ghi dữ liệu event vào JFR | Không bảo đảm event xuất hiện trong mọi recording hoặc mọi cửa sổ consumer |

**Lưu ý:** `shouldCommit()` phản ánh mức ngưỡng hiệu lực của **các recording đang chạy** (minimum threshold khi có nhiều recording phù hợp), không nhất thiết biểu diễn đúng ngưỡng của **một file đích** nếu nhiều recording có settings khác nhau. Khi cần kiểm chứng chính xác một recording, kiểm soát các recording đồng thời và kiểm tra dữ liệu dump.

### 5.3. Event chưa được `commit()`

```java
Work work = new Work();
work.label = "notCommitted";
// Thiếu work.commit();
```

Chỉ tạo object event hoặc gọi `begin()/end()` mà **không `commit()`** chưa đủ để ghi một custom event. Ngược lại, `commit()` có thể tự kết thúc duration nếu đã `begin()` nhưng chưa `end()`, theo hợp đồng `jdk.jfr.Event`. Đừng dùng việc tạo đối tượng làm tín hiệu “đã gửi event”.

## 6. Thiếu do `threshold`: sự kiện quá ngắn

`EventSettings.withThreshold(Duration)` đặt thời lượng **tối thiểu** để event đủ điều kiện được ghi vào recording. Ví dụ:

```java
recording.enable("demo.Work")
        .withThreshold(Duration.ofMillis(30));
```

Trong một test, có thể tạo hai trường hợp:

```java
Work quick = new Work();
quick.label = "short";
quick.commit(); // Duration = 0, nằm dưới threshold 30 ms.

Work slow = new Work();
slow.label = "long";
slow.begin();
Thread.sleep(100);
slow.end();
slow.commit(); // Duration > 30 ms trên môi trường test thông thường.
```

Trong ví dụ trên, `quick` bị loại do duration dưới threshold. `slow` được đo trong khoảng `begin()` đến `end()` và vượt ngưỡng, nên đủ điều kiện ghi. Khi debug, việc **`quick.isEnabled() == true` vẫn có thể xảy ra**, vì enabled và threshold kiểm tra hai thuộc tính khác nhau.

Với `slow`, có thể kiểm tra **sau khi `end()` nhưng trước khi `commit()`**:

```java
boolean allowed = slow.shouldCommit();
```

Trên một recording đang chạy, type enabled và threshold 30 ms, `allowed` sẽ là `true` khi duration đo được đã đạt ngưỡng.

### 6.1. `withoutThreshold()` có tác dụng gì?

```java
recording.enable("demo.Marker").withoutThreshold();
```

Điều này tương đương đặt threshold bằng 0, do đó **instant event** của `demo.Marker` có duration 0 sẽ không bị loại vì ngưỡng dương. Nó **không** có nghĩa là recorder bắt buộc ghi mọi event bất chấp enabled, retention hay thời điểm quan sát.

### 6.2. Nên kiểm thử threshold như thế nào?

- Một event **duration 0** đối chiếu với ngưỡng dương là ca âm tính rõ ràng.
- Một event duration dài hơn ngưỡng với **khoảng cách đủ lớn** là ca dương tính; đừng kiểm tra đúng 30 ms khi ngưỡng cũng là 30 ms vì scheduling/timing jitter.
- Khi thật sự kiểm thử ranh giới bằng nanoseconds/microseconds, dùng thời lượng ghi trong `RecordedEvent.getDuration()` hoặc công cụ chuyên dụng, không suy luận dựa vào thời gian `Thread.sleep` tuyệt đối.
- `withThreshold(Duration.ZERO)` hay `withoutThreshold()` hữu ích để **bỏ lọc duration trong bài test chẩn đoán**, nhưng có thể tạo nhiều dữ liệu/overhead trong production.

**Công thức tư duy:** **period ≠ threshold**. `withPeriod` dành cho loại event định kỳ; `withThreshold` lọc theo thời lượng. Đổi `withPeriod(Duration.ofMillis(30))` không tương đương “chỉ ghi công việc chậm hơn 30 ms”.

## 7. Thiếu do thời điểm phát và độ dài cửa sổ quan sát

Có ít nhất **ba cửa sổ thời gian** cần phân biệt:

1. **Cửa sổ recording**: từ `Recording.start()` đến `Recording.stop()`, cùng retention và điều kiện thu thập.
2. **Thời điểm sự kiện được tạo/commit**: custom event phải thực sự xảy ra khi recording đang hoạt động và đáp ứng settings.
3. **Cửa sổ đọc**: khi consumer gọi `EventStream.setStartTime(Instant)`/`setEndTime(Instant)` hoặc khi một stream trực tiếp chỉ theo dõi phần dữ liệu mới.

### 7.1. Một file có event nhưng bộ lọc chỉ hiển thị phần sau

Giả sử tạo hai marker:

```java
mark("first");
Thread.sleep(30);
Instant cutoff = Instant.now();
Thread.sleep(30);
mark("second");
```

Các lời gọi này nằm trong code có recording đang chạy và `mark(...)` là hàm commit custom `Marker`. `cutoff` được lấy **sau marker thứ nhất, trước marker thứ hai**.

Khi đọc toàn bộ file:

```java
try (EventStream stream = EventStream.openFile(file)) {
    stream.onEvent("demo.Marker", event ->
            System.out.println(event.getString("label")));
    stream.start();
}
```

Ta nhận **first** và **second**. Nhưng khi đặt lọc thời gian:

```java
try (EventStream stream = EventStream.openFile(file)) {
    stream.setStartTime(cutoff);

    stream.onEvent("demo.Marker", event ->
            System.out.println(event.getString("label")));
    stream.start();
}
```

Chỉ marker **second** xuất hiện. Event **first** vẫn có trong file! Đây là ví dụ rõ ràng của **consumer-side omission**.

Cả hai là **trích đoạn**; chương trình hoàn chỉnh có `mark`/`cutoff`/`file` và chính xác các output ở mục 10.

### 7.2. `setEndTime(Instant)` cũng có thể loại dữ liệu mới hơn

`setEndTime` đặt mốc kết thúc cửa sổ stream. Nếu mốc quá sớm, event xảy ra sau đó không được dispatch. Phải cấu hình `setStartTime`/`setEndTime` **trước** `start()` hoặc `startAsync()`.

Khi kiểm tra test fail, ghi lại:
- Mốc `startTime` và `endTime` của stream;
- Thời điểm `getStartTime()`/`getEndTime()` của các `RecordedEvent` thực;
- Múi giờ **chỉ ở lớp trình bày**; `Instant` là thời điểm tuyệt đối;
- Nguồn file và recording thực tế, không nhầm với thời gian file được dump.

Đừng ép ranh giới test chính xác bằng thời gian cực sát nhau, vì việc lấy timestamp và chạy event ở các thread khác nhau có sai số đo/lịch; hãy dùng **khoảng cách đủ rõ** và xác minh dữ liệu thực.

### 7.3. `EventStream.openRepository()` không giống `openFile()`

- `EventStream.openFile(file)` mặc định đọc từ **event đầu tiên trong file**, phù hợp kiểm thử offline.
- `EventStream.openRepository()` mặc định bắt đầu từ **event kế tiếp được flush** trong JFR repository của JVM. Mở stream **sau khi sự kiện đã trôi qua** có thể không thấy event đó nếu không đặt mốc phù hợp.
- `RecordingStream` dùng cho một recording do ứng dụng tạo và quan sát trong vòng đời chạy; cần bảo đảm stream đã start/ready khi workload phát event.

Vì vậy, khi nghi **bỏ lỡ do thời điểm đăng ký listener**, hãy đọc lại một **file dump hoàn chỉnh** bằng `openFile`/`RecordingFile` trước khi khẳng định recorder không phát event.

## 8. `period` và sự kiện định kỳ: thiếu do quan sát quá ngắn

Với một built-in periodic event (ví dụ `jdk.CPULoad`):

```java
recording.enable("jdk.CPULoad")
        .withPeriod(Duration.ofSeconds(1));
```

Cấu hình này yêu cầu chu kỳ khoảng 1 giây cho loại periodic event; nó **không bảo đảm** cứ 1 giây sẽ có chính xác một event ở mọi runtime/tải.

Nếu recording chỉ chạy **100 ms**, test yêu cầu `jdk.CPULoad` xuất hiện là không đáng tin: có thể chưa đến lần phát/flush phù hợp.

Với **custom periodic event**, phải đăng ký hook phát event:

```java
@Name("demo.Tick")
@jdk.jfr.Period("1 s")
class Tick extends Event {
    int sequence;
}
```

Cấu hình `@Period` hoặc `withPeriod` **không tự chạy constructor/commit** của ứng dụng. Cần cơ chế `FlightRecorder.addPeriodicEvent(Tick.class, hook)` rồi trong hook tạo/commit event và tháo hook khi không dùng nữa.

Khi test loại event định kỳ:
- Cho stream/recording **thời gian quan sát đủ dài** so với period.
- Xác nhận event type enabled và hook đã được đăng ký (nếu custom).
- Không assert đúng `N` events trong `N × period`; kiểm tra **có ít nhất một event** hoặc tiêu chí thống kê phù hợp.
- Không biến event `period` thành duration event rồi gán ý nghĩa threshold sai.

### 8.1. Streaming/buffering/flush không phải “sự kiện đã mất”

JFR có thể thu thập dữ liệu rồi **flush theo batch/chunk** trước khi consumer thấy. Trong EventStream, `onFlush(Runnable)` giúp biết một batch đã được đẩy qua quá trình dispatch; đây không phải cơ chế tạo event. Một stream live chưa gọi flush hoặc chưa đến batch có thể tạm thời không thấy dữ liệu, trong khi file sau khi stop/dump vẫn có.

Khi kiểm tra, cần tách:
- Event có trong recording/file hoàn chỉnh hay không?
- Consumer live có nhận được sau thời điểm flush hay không?
- Async handler đã kịp xử lý chưa trước khi kiểm tra biến kết quả?

Không mặc định “đợi 100 ms là đủ”; điều này phụ thuộc period, flush, môi trường và workload.

## 9. Khác biệt giữa missing event ở recorder và missing callback ở consumer

| Quan sát | Giải thích khả dĩ | Cách kiểm chứng |
| --- | --- | --- |
| `isEnabled() == false` | Không recording phù hợp đang chạy hoặc loại event không enabled | Kiểm tra `Recording.getState()`, `getSettings()`, event name |
| `isEnabled() == true` nhưng `shouldCommit() == false` | Duration chưa đạt threshold | Đo `begin/end`, xem ngưỡng, thử `withoutThreshold` |
| Event không gọi `commit()` | Chỉ tạo object chứ chưa yêu cầu ghi | Thêm commit ở đúng điểm, đối chiếu số lần |
| Event trước start/sau stop không có | Nằm ngoài cửa sổ recording | Ghi mốc start/stop, đặt đối chứng trong cửa sổ |
| `RecordingFile.readAllEvents` không có event đích | Event không được ghi/giữ trong file hiện tại | Kiểm tra enabled, threshold, file nguồn, retention |
| `RecordingFile` có event nhưng callback không thấy | Sai event name, filter giờ hoặc lifecycle stream | Dùng callback tổng quát, bỏ time filter, kiểm tra start/close |
| Filter từ cutoff chỉ có event thứ hai | Event thứ nhất cũ hơn cửa sổ đọc | Bỏ `setStartTime` hoặc đổi mốc |
| Periodic event có 0 bản ghi | Không hook, chưa đến chu kỳ, bị disabled hoặc quá ngắn | Tăng thời gian quan sát và kiểm tra period/hook |
| Live stream không thấy ngay | Chưa có flush hoặc stream chưa sẵn sàng/đã đóng sớm | Đọc file dump sau stop, awaitTermination nếu async |
| File chứa dữ liệu nhưng tên event không đúng | Callback `onEvent("tên sai", ...)` không match | So sánh `EventType.getName()` từ dữ liệu thật |

`RecordingFile.readAllEvents(path)` tải **toàn bộ** các event từ tệp vào danh sách; hữu ích cho kiểm thử file nhỏ, nhưng đối với file lớn nên đọc tăng dần bằng `RecordingFile` hoặc `EventStream` để tránh dùng nhiều bộ nhớ.

### 9.1. Chuỗi chẩn đoán ngắn gọn

**Kiểm tra recorder trước:** bật loại event bằng tên đúng, bảo đảm `start` trước khi phát, đặt threshold 0 cho instant events hoặc duration đủ dài cho event chậm, gọi `commit`, `stop` rồi `dump`. Sau đó đọc file bằng cơ chế không có time filter và đếm event theo **`EventType.getName()`**.

**Kiểm tra consumer sau:** nếu file đã có event nhưng callback là 0, kiểm tra tên `onEvent`, thời gian `setStartTime`/`setEndTime`, `start()`/`startAsync()`, `awaitTermination()` và `onError`. Không sửa settings recorder khi vấn đề thật ra là bộ lọc đọc.

## 10. Chương trình Java 17+ hoàn chỉnh: tái hiện ba nguyên nhân thiếu event

Ví dụ tạo và kiểm tra đồng thời:

- **Cấu hình:** `demo.Hidden` bị disable → không xuất hiện trong file.
- **Ngưỡng:** `demo.Work` có threshold 30 ms → instant event `short` bị loại, duration event `long` được ghi.
- **Thời điểm ghi:** `beforeStart` và `afterStop` không thuộc recording.
- **Thời điểm đọc:** file có hai marker `first`/`second`, nhưng `setStartTime(cutoff)` chỉ nhận `second`.
- **Lọc tên sai:** callback `"demo.Makr"` nhận 0 event dù file có `demo.Marker`.

Lưu tệp với tên **`JfrMissingEventsDemo.java`**:

```java
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Duration;
import java.time.Instant;
import java.util.ArrayList;
import java.util.List;
import jdk.jfr.Event;
import jdk.jfr.Name;
import jdk.jfr.Recording;
import jdk.jfr.consumer.EventStream;

public class JfrMissingEventsDemo {
    @Name("demo.Work")
    static class Work extends Event { String label; }

    @Name("demo.Marker")
    static class Marker extends Event { String label; }

    @Name("demo.Hidden")
    static class Hidden extends Event { String label; }

    static void mark(String label) {
        Marker event = new Marker();
        event.label = label;
        event.commit();
    }

    public static void main(String[] args) throws Exception {
        Path file = Files.createTempFile("missing-events-", ".jfr");
        try {
            boolean beforeEnabled = new Marker().isEnabled();
            boolean afterEnabled;
            Instant cutoff;
            boolean fastAllowed;
            boolean slowAllowed;
            boolean hiddenEnabled;

            try (Recording recording = new Recording()) {
                recording.enable("demo.Work")
                        .withThreshold(Duration.ofMillis(30));
                recording.enable("demo.Marker")
                        .withoutThreshold();
                recording.disable("demo.Hidden");

                mark("beforeStart"); // Không có trong recording này.
                recording.start();

                hiddenEnabled = new Hidden().isEnabled();
                Hidden hidden = new Hidden();
                hidden.label = "hidden";
                hidden.commit();

                Work shortWork = new Work();
                shortWork.label = "short";
                shortWork.commit();
                fastAllowed = shortWork.shouldCommit();

                Work longWork = new Work();
                longWork.label = "long";
                longWork.begin();
                Thread.sleep(100);
                longWork.end();
                slowAllowed = longWork.shouldCommit();
                longWork.commit();

                mark("first");
                Thread.sleep(30);
                cutoff = Instant.now();
                Thread.sleep(30);
                mark("second");

                recording.stop();
                mark("afterStop"); // Không có trong recording vừa dừng.
                afterEnabled = new Marker().isEnabled();
                recording.dump(file);
            }

            List<String> workLabels = new ArrayList<>();
            List<String> markerLabels = new ArrayList<>();
            List<String> incorrectCallback = new ArrayList<>();

            try (EventStream stream = EventStream.openFile(file)) {
                stream.onEvent("demo.Work",
                        e -> workLabels.add(e.getString("label")));
                stream.onEvent("demo.Marker",
                        e -> markerLabels.add(e.getString("label")));
                stream.onEvent("demo.Makr",
                        e -> incorrectCallback.add(e.getString("label")));
                stream.start();
            }

            List<String> filtered = new ArrayList<>();
            try (EventStream stream = EventStream.openFile(file)) {
                stream.setStartTime(cutoff);
                stream.onEvent("demo.Marker",
                        e -> filtered.add(e.getString("label")));
                stream.start();
            }

            System.out.println("beforeEnabled=" + beforeEnabled);
            System.out.println("hiddenEnabled=" + hiddenEnabled);
            System.out.println("afterEnabled=" + afterEnabled);
            System.out.println("shortShouldCommit=" + fastAllowed);
            System.out.println("longShouldCommit=" + slowAllowed);
            System.out.println("work=" + workLabels);
            System.out.println("markers=" + markerLabels);
            System.out.println("badNameEvents=" + incorrectCallback.size());
            System.out.println("afterCutoff=" + filtered);
            System.out.println("fileValid=" + (Files.size(file) > 0));
        } finally {
            Files.deleteIfExists(file);
        }
    }
}
```

### 10.1. Biên dịch và chạy

```bash
javac --release 17 JfrMissingEventsDemo.java
java JfrMissingEventsDemo
```

**Stdout đã kiểm chứng (chạy hai lần trên JDK 17):**

```text
beforeEnabled=false
hiddenEnabled=false
afterEnabled=false
shortShouldCommit=false
longShouldCommit=true
work=[long]
markers=[first, second]
badNameEvents=0
afterCutoff=[second]
fileValid=true
```

### 10.2. Đọc từng dòng để xác định nguyên nhân

| Kết quả | Ý nghĩa thực tế |
| --- | --- |
| `beforeEnabled=false` | Trước khi recording start, trong môi trường test không có recording khác đang thu sự kiện `Marker` |
| `hiddenEnabled=false` | `Hidden` bị `disable` trong recording đang chạy |
| `afterEnabled=false` | Sau khi stop, không còn recording nào khác bật `Marker` trong môi trường test |
| `shortShouldCommit=false` | Instant event `Work` với duration 0 bị threshold 30 ms loại |
| `longShouldCommit=true` | Work duration ~100 ms vượt threshold 30 ms |
| `work=[long]` | File có duration event `long`, **không có** `short` |
| `markers=[first, second]` | File chứa hai marker trong cửa sổ recording |
| `badNameEvents=0` | Callback dùng tên không tồn tại `demo.Makr`, không phải lỗi recorder |
| `afterCutoff=[second]` | Consumer áp dụng `setStartTime` nên không thấy `first` dù file có nó |
| `fileValid=true` | Tệp được dump có dữ liệu; việc đọc stream thành công cũng cho thấy nó là JFR file hợp lệ cho bài test |

**Vì sao không thấy `beforeStart`/`afterStop`?** Chúng được gọi ngoài vòng đời của recording duy nhất. Nếu có recording khác đang thu `demo.Marker` đồng thời, kết quả cần đánh giá lại trong ngữ cảnh nhiều recording; ví dụ giả định **chỉ có recording do chương trình tạo**.

**Vì sao không thấy `hidden`?** `recording.disable("demo.Hidden")` loại event type đó ngay tại tầng ghi. **Vì sao không thấy `short`?** Nó nằm dưới threshold, không phải vì consumer lọc tên. **Vì sao `first` biến mất ở `afterCutoff`?** Vì cửa sổ đọc bắt đầu sau khi `first` đã được commit; file gốc vẫn chứa `first`.

Ví dụ này đã dùng `EventStream.openFile` với `start()` **đồng bộ**, trích xuất **`String` ngay trong callback**. Nó không giữ `RecordedEvent` để dùng sau callback, nên không cần `setReuse(false)`. Nếu bạn lưu `RecordedEvent` vào list để dùng lâu dài, phải tắt reuse hoặc chỉ lưu dữ liệu đã trích xuất, vì `EventStream` có thể tái sử dụng object event.

### 10.3. Hạn chế thời gian của test demo

`Thread.sleep(100)` vượt xa threshold 30 ms để test không phụ thuộc vào một ranh giới cực sát; `Thread.sleep(30)` trước/sau `Instant.now()` tạo khoảng cách hai phía của cutoff. Trên hệ thống tải quá nặng, bộ lập lịch hoặc độ phân giải timestamp có thể khiến test cần khoảng cách dài hơn. Điều này là **giới hạn của test dựa trên thời gian thực**, không phải của `EventSettings`.

Nếu muốn test có độ tin cậy cao trong CI: tránh assert **thời lượng bằng chính xác 100 ms**; chỉ kiểm tra event đủ ngưỡng và label mong đợi. Nếu cần kiểm thử chính xác ranh giới threshold, đo dữ liệu `RecordedEvent.getDuration()` thay vì suy luận từ lệnh sleep.

## 11. Viết bộ test positive/negative có thể hành động được

Thay vì một phép assert “số sự kiện > 0”, hãy phân chia test theo nguyên nhân:

| Test case | Cấu hình/kịch bản | Kỳ vọng trên file đầy đủ | Kỳ vọng consumer |
| --- | --- | --- | --- |
| **P1 — baseline** | Marker enabled, commit khi recording chạy | Hai marker có mặt | Callback đúng tên nhận hai |
| **N1 — disabled** | `disable("demo.Hidden")`, vẫn gọi commit | Không có `demo.Hidden` trong recording | Callback Hidden = 0 |
| **N2 — threshold** | Work instant duration 0, threshold 30 ms | Không có `short` | Callback Work chỉ có `long` |
| **P2 — duration pass** | Work begin/end ~100 ms, threshold 30 ms | `long` xuất hiện | `work=[long]` |
| **N3 — trước start** | Marker commit trước `start()` | Không có `beforeStart` | Không được dispatch |
| **N4 — sau stop** | Marker commit sau `stop()` | Không có `afterStop` | Không được dispatch |
| **N5 — cutoff** | Hai marker có trong file, startTime ở giữa | **Cả hai vẫn tồn tại** trong file | Filter chỉ nhận `second` |
| **N6 — sai tên** | Callback đăng ký `demo.Makr` | File **vẫn có** `demo.Marker` | Callback tên sai = 0 |
| **P3 — bỏ bộ lọc** | Đọc lại cùng file không đặt cutoff | Hai marker có mặt | Cả `first` và `second` |
| **N7 — thiếu commit** | Tạo event nhưng không `commit()` | Không có event đó | Callback = 0 |

Đối với test threshold, chọn **một ca dương rõ ràng** thay vì chỉ có event bị loại. Đối với test time filter, hãy chứng minh file đầy đủ có event **trước và sau** mốc; nếu không, kết quả filter 0 không đủ để khẳng định nguyên nhân.

### 11.1. Các assertion nên kiểm tra

Trong một bộ test JUnit hoặc test framework tương thích, các ý tưởng cốt lõi là:

```java
// PSEUDOCODE mô tả điều kiện, KHÔNG phải file JUnit độc lập:
assertTrue(allMarkers.contains("first"));
assertTrue(allMarkers.contains("second"));
assertEquals(List.of("second"), markersAfterCutoff);
assertEquals(List.of("long"), recordedWorkLabels);
assertEquals(0, callbackWithWrongNameCount);
```

Để tránh test flaky, tạo file riêng mỗi lần chạy, phân biệt event name của ứng dụng và không dựa vào thứ tự của các built-in JVM events. Đừng dùng file JFR cũ từ lần test trước.

### 11.2. Đọc tệp bằng `RecordingFile` để xác minh độc lập

Nếu nghi callback sai, có thể kiểm tra file mà **không dùng cùng callback đang bị nghi lỗi**:

```java
import jdk.jfr.consumer.RecordedEvent;
import jdk.jfr.consumer.RecordingFile;
import java.nio.file.Path;
import java.util.List;

List<RecordedEvent> events =
        RecordingFile.readAllEvents(Path.of("capture.jfr"));

long markerCount = events.stream()
        .filter(e -> e.getEventType().getName().equals("demo.Marker"))
        .count();

System.out.println(markerCount);
```

Đây là **đoạn mã minh họa đặt trong method**; cần một file `capture.jfr` thực. `RecordingFile.readAllEvents` lưu toàn bộ event vào RAM, phù hợp file test nhỏ. Với file lớn, dùng `RecordingFile` incremental (`hasMoreEvents`/`readEvent`) hoặc `EventStream` đọc tuần tự.

Nếu file đọc được có event nhưng callback không hoạt động, hãy kiểm tra **tầng consumer**. Nếu file không có, quay lại **tầng producer/config/retention**.

## 12. Kiểm thử với EventStream/RecordingStream bất đồng bộ

Một nguồn false negative rất phổ biến là **kiểm tra kết quả trước khi stream chạy xong**:

```java
// KHÔNG an toàn nếu muốn đọc hết file:
try (EventStream stream = EventStream.openFile(file)) {
    stream.onEvent("demo.Marker", e -> counter.incrementAndGet());
    stream.startAsync();
}
// try đóng stream ngay, có thể chưa dispatch xong.
```

Đoạn trên chỉ có ý nghĩa khi đã có `Path file` và `AtomicInteger counter`. Cách sử dụng async rõ ràng:

```java
try (EventStream stream = EventStream.openFile(file)) {
    stream.onEvent("demo.Marker", e -> counter.incrementAndGet());

    stream.startAsync();
    stream.awaitTermination();
}

System.out.println(counter.get());
```

`startAsync()` xử lý event trên thread khác; `awaitTermination()` chờ stream kết thúc. Nếu muốn đọc một **tệp hữu hạn** và không cần song song, **`start()` đồng bộ** thường đơn giản và ít rủi ro hơn.

**Cẩn thận:** `awaitTermination(Duration timeout)` là thời gian **chờ tối đa**, không cam kết stream đã xử lý xong khi timeout hết. Kiểm tra trạng thái/lifecycle thay vì tuyên bố đã đủ dữ liệu chỉ vì đã hết thời gian đợi.

Khi theo dõi JVM live bằng `RecordingStream`, listener cần được thiết lập và stream thực sự chạy trước khi workload phát event. Không dùng `Thread.sleep(50)` như một cơ chế đồng bộ chắc chắn cho mọi môi trường; dùng tín hiệu readiness/lifecycle có ý nghĩa hoặc thiết kế test theo file dump để cô lập vấn đề.

## 13. Kiểm tra settings thực và file, không suy luận từ ý định cấu hình

### 13.1. `Recording.getSettings()`

Ví dụ khi đã dùng `recording.enable("demo.Work").withThreshold(Duration.ofMillis(30))`:

```java
Map<String, String> actualSettings = recording.getSettings();
System.out.println(actualSettings.get("demo.Work#threshold"));
```

**Đây là trích đoạn**, không phải một method độc lập. Giá trị thường được chuẩn hóa thành chuỗi theo đơn vị như `"30000000 ns"` trên JDK đã thử, nhưng **không hardcode đơn vị/format** làm điều kiện correctness xuyên các JDK. Map settings cho thấy **cấu hình của recording**, không chứng minh số event thực có trong file.

### 13.2. `jfr print` để kiểm tra file từ CLI

Ngoài Java API, JDK cung cấp công cụ `jfr`:

```bash
jfr print --events demo.Marker capture.jfr
```

Với file đúng và runtime hỗ trợ, lệnh hiển thị các event thuộc loại đã chọn, giúp kiểm tra độc lập callback trong ứng dụng. Trong môi trường thực tế, hãy xem `jfr help print` của chính JDK đang chạy để xác nhận cú pháp/option. **Chỉ mở file từ nguồn đáng tin**, vì file JFR là dữ liệu nhị phân có thể chứa thông tin kỹ thuật nhạy cảm.

### 13.3. Dữ liệu có thể bị loại do retention hoặc chọn nhầm file

Một recording có thể giới hạn kích thước/thời gian lưu bằng `setMaxSize` hoặc `setMaxAge`. Nếu dữ liệu cũ bị loại khỏi recording do retention, việc dump file sau đó không khôi phục được phần đã mất. Không nên nhầm **retention** với **time filter của EventStream**.

Trước khi kết luận sự kiện thiếu do Java:
- Xác nhận `Path` và file đang đọc đúng run, đúng recording/host.
- Xác nhận recording đã start/stop và dump thành công.
- Xem cài đặt giữ dữ liệu, thời điểm thu thập và kích thước file.
- Bảo đảm callback không tự lọc thêm theo label, category, duration hoặc điều kiện nghiệp vụ không được log.

## 14. Những lỗi thường gặp cần tránh

### Lỗi A — Dựa duy nhất vào `isEnabled()`

`isEnabled() == true` không chứng minh duration qua ngưỡng. Dùng thêm `shouldCommit()` và kiểm tra file kết quả; lưu ý nhiều recording có thể ảnh hưởng effective settings.

### Lỗi B — Gọi `withThreshold` cho instant events rồi bất ngờ không thấy dữ liệu

Instant event có duration 0, nên ngưỡng dương lọc nó. Dùng `withoutThreshold()` hoặc `withThreshold(Duration.ZERO)` trong test cần instant events. Trong code thật, chọn threshold theo mục tiêu đo.

### Lỗi C — Dùng `withPeriod` để thử duration threshold

`period` điều khiển loại event **định kỳ**; không thay `threshold` và không phát event một cách tự động nếu custom periodic hook không được đăng ký.

### Lỗi D — Nghĩ ghi event trước start cũng thuộc recording

Event commit trước `Recording.start` không thuộc recording đó; tương tự commit sau stop. Đặt event đối chứng rõ ràng **bên trong** thời gian recording.

### Lỗi E — Chưa `commit()` nhưng mong thấy custom event

Chỉ `new Work()` hoặc `begin()/end()` không đủ. Cần `commit()`; dù đã commit, sự kiện vẫn phải đủ điều kiện để ghi.

### Lỗi F — Callback dùng sai event name

`onEvent("demo.Makr", ...)` sẽ không nhận `demo.Marker`. Kiểm tra `@Name` và `EventType.getName()` thực, tránh tên label hoặc tên Java class không khớp.

### Lỗi G — Quên bỏ `setStartTime`/`setEndTime` trong kiểm thử baseline

Nếu cắt khoảng quan sát quá hẹp, file có event nhưng callback không thấy. Đọc lại toàn bộ file không filter thời gian để phân biệt.

### Lỗi H — Mở live stream sau khi event đã phát

`EventStream.openRepository` mặc định theo dõi sự kiện flush tiếp theo. Nếu bắt đầu muộn, không thấy lịch sử cũ. Đọc file dump bằng `openFile` hoặc đặt khoảng thời gian được hỗ trợ.

### Lỗi I — `startAsync` rồi kết luận quá sớm

Callback chạy ở thread khác. Chờ kết thúc hoặc có cơ chế đồng bộ; không đọc counter khi callback chưa chạy hoặc đóng stream quá sớm.

### Lỗi J — Đếm chính xác sự kiện định kỳ theo đồng hồ

Với `period=1 s`, recording chạy một giây không bảo đảm chính xác một tick. Chọn thời gian quan sát đủ, kiểm tra có event thay vì count tuyệt đối khi thời gian/lịch không được kiểm soát.

### Lỗi K — Tự coi file có kích thước > 0 là đã có event cần tìm

File JFR có thể chứa metadata hoặc loại sự kiện khác. Cần đọc `EventType.getName()`/fields thực và đếm **loại event đích**.

### Lỗi L — Quên `onError` hoặc lỗi callback bị bỏ qua

Nếu callback có exception mà không theo dõi `onError`/stderr, test có thể hiểu nhầm là thiếu sự kiện. Với job tự động, chuyển lỗi callback/stream thành trạng thái thất bại rõ ràng.

### Lỗi M — Gộp lỗi do nhiều recording đồng thời

Một event type có thể enabled vì recording khác đang chạy; `shouldCommit()` dùng ngưỡng hiệu lực từ các recording. Cần cô lập hoặc ghi rõ các recording đồng thời khi test file riêng, tránh kết luận sai từ một lần kiểm tra method.

## 15. Bài tập tự kiểm tra

**Câu 1.** `Work.isEnabled()` trả true, nhưng event không có trong file. Có thể vì sao?

**Đáp án:** Type enabled không đảm bảo duration qua threshold, code đã commit, file đúng recording hay dữ liệu còn được giữ. Kiểm tra `shouldCommit()`, duration, vòng đời và nội dung file.

**Câu 2.** Vì sao `Work` duration 0 bị threshold 30 ms loại nhưng `Work` duration 100 ms được ghi?

**Đáp án:** Threshold là thời lượng tối thiểu. `0 ms < 30 ms` còn `100 ms > 30 ms`. Đây là lọc **theo duration**, không phải period.

**Câu 3.** File có `demo.Marker` nhưng `onEvent("demo.Makr", ...)` không chạy. Đây là lỗi ở tầng nào?

**Đáp án:** Tầng **consumer**, do sai event name. Sửa tên callback theo `EventType.getName()` thực trong file.

**Câu 4.** Vì sao `setStartTime(cutoff)` chỉ nhận `second` dù file có cả `first`?

**Đáp án:** Consumer chỉ dispatch các event trong cửa sổ đã cấu hình, còn bản thân file vẫn giữ cả hai. Bỏ filter sẽ thấy cả hai.

**Câu 5.** Đã gọi `new Hidden().commit()` thì `Hidden` có phải được ghi không?

**Đáp án:** Không. Loại event bị `disable` sẽ không được ghi vào recording đó, bất kể code vẫn gọi `commit()`.

**Câu 6.** Với một custom periodic event, có `@Period("1 s")` nhưng không có periodic hook, có chắc event được phát không?

**Đáp án:** Không. Cần `FlightRecorder.addPeriodicEvent` với hook thực sự tạo và commit event. Period không tự sinh logic ứng dụng.

**Câu 7.** `RecordingFile.readAllEvents` thấy event nhưng EventStream callback không thấy. Nên kiểm tra gì trước?

**Đáp án:** Tên event của `onEvent`, `setStartTime`/`setEndTime`, `start()`/`startAsync()`, việc đóng stream quá sớm, callback exceptions. File đã có event nên không nên sửa threshold recorder trước.

**Câu 8.** Vì sao phải làm test positive và negative song song?

**Đáp án:** Nếu mọi case đều nhận 0, test chưa chứng minh được file/consumer có hoạt động. Positive control khẳng định pipeline có thể thu thập và đọc event; negative control xác nhận bộ lọc đang làm đúng phần việc.

**Câu 9.** Dùng `Thread.sleep(100)` có chứng minh event duration chính xác bằng 100 ms không?

**Đáp án:** Không. Độ trễ thực tế chịu ảnh hưởng scheduler và runtime. Hãy tạo khoảng cách đủ với threshold và chỉ assert điều kiện đạt ngưỡng, hoặc đọc `RecordedEvent.getDuration()`.

**Câu 10.** Trong production, không thấy event trước đó khi vừa gọi `openRepository` có phải bug Java không?

**Đáp án:** Chưa chắc. Stream repository mặc định bắt đầu từ các sự kiện được flush tiếp theo, không mặc định hồi cứu mọi event cũ. Dùng file dump hoặc cấu hình start time phù hợp khi cần điều tra lịch sử.

## 16. Checklist gỡ lỗi khi thiếu event JFR

- [ ] Xác định rõ event type, `@Name` và tên callback; không nhầm label với name.
- [ ] Có **positive control** đã biết sẽ được ghi và **negative control** bị lọc có chủ đích.
- [ ] Kiểm tra recording `start/stop`, event `commit`, và phạm vi timestamp.
- [ ] Kiểm tra type enabled trong recording và mọi recording đồng thời có thể ảnh hưởng `isEnabled/shouldCommit`.
- [ ] Với duration event, kiểm tra `withThreshold` và `RecordedEvent.getDuration()`; với instant event kiểm tra ngưỡng 0.
- [ ] Với periodic event, kiểm tra period, hook, độ dài recording và cơ chế flush.
- [ ] Dump file đầy đủ sau khi stop và xác nhận file từ đúng run/host/recording.
- [ ] Đọc một lượt không filter bằng `EventStream.openFile` hoặc `RecordingFile` trước khi thử time filters.
- [ ] Nếu chỉ consumer thiếu, xem `setStartTime/setEndTime`, `onEvent`, `start/startAsync`, `awaitTermination`, `onError` và việc đóng sớm.
- [ ] Không dùng file size > 0 như bằng chứng event đích đã có trong file.
- [ ] Tránh assertion đúng số periodic events và thời gian sleep tuyệt đối khi runtime không deterministic.
- [ ] Ghi nhận settings/threshold/observation window trong test report, và bảo vệ quyền truy cập file `.jfr`.

## 17. Tài liệu chính thức vẫn còn áp dụng

1. [Oracle Java SE 26 — `jdk.jfr.Event`](https://docs.oracle.com/en/java/javase/26/docs/api/jdk.jfr/jdk/jfr/Event.html): `begin`, `end`, `commit`, `isEnabled`, `shouldCommit` và ý nghĩa ngưỡng.
2. [Oracle Java SE 26 — `jdk.jfr.EventSettings`](https://docs.oracle.com/en/java/javase/26/docs/api/jdk.jfr/jdk/jfr/EventSettings.html): `withThreshold`, `withoutThreshold`, `withPeriod` và cấu hình stack trace.
3. [Oracle Java SE 26 — `jdk.jfr.Recording`](https://docs.oracle.com/en/java/javase/26/docs/api/jdk.jfr/jdk/jfr/Recording.html): `enable`, `disable`, `start`, `stop`, `dump`, `getSettings`, retention và trạng thái.
4. [Oracle Java SE 26 — `jdk.jfr.consumer.EventStream`](https://docs.oracle.com/en/java/javase/26/docs/api/jdk.jfr/jdk/jfr/consumer/EventStream.html): `openFile`, `openRepository`, `onEvent`, `setStartTime`, `setEndTime`, `startAsync`, `awaitTermination`, `onError`.
5. [Oracle Java SE 26 — `jdk.jfr.consumer.RecordingFile`](https://docs.oracle.com/en/java/javase/26/docs/api/jdk.jfr/jdk/jfr/consumer/RecordingFile.html): đọc từng event, `readAllEvents` và đối chiếu tệp ghi.
6. [OpenJDK — JEP 349: JFR Event Streaming](https://openjdk.org/jeps/349): API streaming được bổ sung ở JDK 14, vẫn được hỗ trợ.
7. [Dev.java — Configuring the JDK Flight Recorder](https://dev.java/learn/jvm/monitoring-troubleshooting/jfr/configure/): ý nghĩa setting `enabled`, `period`, `threshold` và tùy chọn recording hiện đại.
