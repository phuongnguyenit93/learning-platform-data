# Tái sử dụng đối tượng sự kiện JFR qua `setReuse`: hiệu năng và an toàn dữ liệu

## 1. Mục tiêu và bản chất của vấn đề

Java Flight Recorder (**JFR**) ghi nhận hoạt động của JVM dưới dạng các sự kiện có kiểu và trường dữ liệu cụ thể. Khi đọc sự kiện bằng `jdk.jfr.consumer.EventStream` hoặc `RecordingStream`, mã ứng dụng có thể đăng ký callback với `onEvent(...)`. Mỗi lần callback được gọi, nó nhận một đối tượng `RecordedEvent` mô tả sự kiện đang được tiêu thụ.

Khi tốc độ sự kiện lớn, việc tạo quá nhiều đối tượng Java cho consumer có thể tạo thêm áp lực cấp phát và thu gom rác. Để điều chỉnh chi phí đó, API cung cấp:

```java
stream.setReuse(true);
stream.setReuse(false);
```

Đây là **hai lựa chọn thay thế** cho cùng một stream, không phải hai lệnh nên gọi liên tiếp. `setReuse(boolean)` quy định **consumer có được phép tái sử dụng đối tượng `RecordedEvent` trong callback hay không**.

Hai mục tiêu thiết kế thường xung đột:

- **Giảm cấp phát:** cho phép tái sử dụng đối tượng wrapper khi xử lý nhiều sự kiện, phù hợp với callback xử lý ngay và không lưu tham chiếu.
- **Giữ sự kiện sau callback:** yêu cầu một đối tượng riêng cho mỗi event nếu ứng dụng cần giữ tham chiếu `RecordedEvent` để đọc về sau.

**Quy tắc quan trọng nhất:** nếu `setReuse(true)`, **không giữ tham chiếu `RecordedEvent` sau khi callback kết thúc**. Nếu cần chuyển dữ liệu sang một luồng khác hoặc lưu lâu dài, trích các trường cần thiết thành dữ liệu riêng **ngay trong callback**.

Bài học dùng JFR Event Streaming hiện hành của Java 17+, không sử dụng tính năng preview hay cơ chế legacy. Event streaming được giới thiệu trong Java 14 (JEP 349); `EventStream.setReuse` và `RecordingStream.setReuse` vẫn là API chuẩn trên các JDK hiện đại.

## 2. Phân biệt `jdk.jfr.Event` và `RecordedEvent`

Hai đối tượng có tên gần giống nhưng ở **hai phía khác nhau** của JFR:

| Khái niệm | Vai trò | Cách sử dụng |
| --- | --- | --- |
| `jdk.jfr.Event` | Đối tượng do ứng dụng **phát sinh sự kiện** | Tạo instance, điền trường, gọi `begin()`/`end()`/`commit()` |
| `jdk.jfr.consumer.RecordedEvent` | Đối tượng do consumer dùng để **đọc sự kiện đã ghi** | Nhận từ `onEvent(...)`, gọi `getString(...)`, `getInt(...)`, `getDuration()`, v.v. |
| `EventStream` | API đăng ký callback và tiêu thụ event từ stream/file/repository | `onEvent(...)`, `setReuse(...)`, `start()`/`startAsync()` |
| `RecordingStream` | Stream vừa quản lý recording JFR vừa cung cấp API tiêu thụ trực tiếp | `enable(...)`, `onEvent(...)`, `setReuse(...)`, `startAsync()` |

`setReuse` tác động tới **đối tượng `RecordedEvent` được truyền cho callback của consumer**. Nó **không** có nghĩa JFR sẽ tự tái sử dụng instance `jdk.jfr.Event` do chương trình tạo, không thay thế `Event.commit()` và không bảo đảm có ít bản ghi JFR hơn.

Ví dụ khai báo một custom event:

```java
import jdk.jfr.Event;
import jdk.jfr.Name;

@Name("demo.Measurement")
class Measurement extends Event {
    String sensor;
    int reading;
}
```

Đây là một khai báo lớp; không phải chương trình có `main`. Bên phát sự kiện có thể tạo `new Measurement()` rồi gán `sensor`, `reading` và gọi `commit()`. Bên tiêu thụ nhận một **`RecordedEvent` khác về vai trò** và đọc các trường đó.

Không suy luận chi phí cấp phát ở producer chỉ từ việc bật `setReuse(true)` ở consumer.

## 3. `setReuse(true)` làm gì?

Tài liệu Java SE của `EventStream` mô tả rằng, theo mặc định, **cùng một đối tượng `RecordedEvent` có thể được dùng để biểu diễn từ hai sự kiện khác nhau trở lên**, kể cả khi gửi đến nhiều callback. `setReuse(true)` cho phép cơ chế này hoạt động.

```java
// Đoạn bên trong phương thức, với stream là EventStream/RecordingStream.
stream.setReuse(true);

stream.onEvent("demo.Measurement", event -> {
    String sensor = event.getString("sensor");
    int reading = event.getInt("reading");
    System.out.println(sensor + "=" + reading);
});
```

Đoạn trên là **mẫu callback**, cần có stream đã cấu hình và nguồn event; nó chưa phải chương trình hoàn chỉnh. Trong callback:

1. `event` mô tả **sự kiện hiện tại**.
2. Gọi getter và sử dụng giá trị **ngay khi callback còn thực thi** là hợp đồng phù hợp với chế độ reuse.
3. Sau khi callback trả về, stream **có quyền** dùng lại cùng đối tượng `event` để biểu diễn sự kiện khác.

**Lưu ý về từ “có thể”:** `setReuse(true)` là **cho phép tái sử dụng**, không hứa rằng mọi event đều dùng chung đúng một object hay `System.identityHashCode(event)` luôn giống nhau. Chiến lược cụ thể phụ thuộc triển khai, loại event và cách stream phân phối dữ liệu.

Vì vậy đừng xây kiểm thử kiểu “mọi lần callback nhận cùng tham chiếu bằng `==`” để chứng minh reuse hoạt động. Không thấy reuse trong một tập dữ liệu nhỏ **không** chứng minh chế độ này vô hiệu.

### Tại sao giữ tham chiếu lại nguy hiểm?

Giả sử mã giữ đối tượng event vào một danh sách:

```java
List<RecordedEvent> captured = new ArrayList<>();

stream.setReuse(true);
stream.onEvent("demo.Measurement", captured::add);
```

Đây là **anti-pattern** khi người lập trình định đọc lại `captured` sau khi callback kết thúc. Một đối tượng trong danh sách có thể bị stream tái sử dụng để biểu diễn event khác. Danh sách có vẻ đã thêm nhiều phần tử, nhưng các phần tử có thể cùng tham chiếu hoặc không còn nội dung tương ứng ở thời điểm chúng được thêm.

Đừng phụ thuộc vào việc chương trình hiện tại “thỉnh thoảng vẫn cho ra dữ liệu đúng”: khi `reuse=true`, quyền sử dụng `RecordedEvent` **sau callback** không nằm trong hợp đồng an toàn.

## 4. `setReuse(false)` làm gì?

Khi gọi:

```java
stream.setReuse(false);
```

API yêu cầu **một đối tượng `RecordedEvent` mới cho mỗi event**. Đây là lựa chọn đúng khi ứng dụng muốn giữ `RecordedEvent` sau khi callback kết thúc để đọc về sau.

Ví dụ:

```java
List<RecordedEvent> retained = new ArrayList<>();

stream.setReuse(false);
stream.onEvent("demo.Measurement", retained::add);
```

Sau khi stream xử lý xong, những `RecordedEvent` được thêm vào danh sách có thể được dùng sau callback theo hợp đồng chế độ không reuse.

Tuy nhiên, **tính tiện lợi có chi phí**: tạo nhiều đối tượng hơn, tăng áp lực cấp phát/bộ nhớ ở luồng tiêu thụ khi lượng event lớn. Dù `reuse=false`, lưu **toàn bộ** event vô hạn vào một danh sách cũng không phải thiết kế tốt cho dịch vụ chạy liên tục.

Nếu chỉ cần vài trường, một **snapshot nhỏ** vẫn thường là thiết kế tốt hơn việc giữ toàn bộ đối tượng event.

| Tiêu chí | `setReuse(true)` | `setReuse(false)` |
| --- | --- | --- |
| Có cho phép tái sử dụng `RecordedEvent` giữa các event không? | Có | Không, đối tượng mới cho từng event |
| Được giữ tham chiếu `RecordedEvent` sau callback không? | **Không nên / không được dựa vào tính ổn định** | Có thể |
| Phù hợp nhất | Xử lý ngay trong callback, đọc trường và tổng hợp | Cần giữ `RecordedEvent` cho xử lý sau |
| Ảnh hưởng chi phí | Có thể giảm cấp phát object phía consumer | Có thể tăng cấp phát và dung lượng giữ trong heap |
| Có bảo đảm giảm lượng event JFR phát sinh không? | Không | Không |
| Có bảo đảm thread safety cho collection của ứng dụng không? | Không | Không |
| Có thay đổi `onEvent`, `start`, `onFlush` hay thứ tự event không? | Không phải mục đích của cờ này | Không phải mục đích của cờ này |

**Mặc định cần nhớ:** Theo Java SE API, reuse **được cho phép theo mặc định**. Vì vậy nếu ứng dụng cần giữ `RecordedEvent` để dùng sau callback, nên thiết lập **tường minh** `setReuse(false)` thay vì phỏng đoán rằng mỗi lần callback đã nhận một object mới.

## 5. Cách nên ưu tiên: trích dữ liệu thành snapshot riêng

Muốn xử lý tiếp ở nơi khác nhưng vẫn tận dụng `setReuse(true)`, hãy lấy những giá trị cần thiết trong callback rồi lưu một object do ứng dụng **tự sở hữu**.

Ví dụ dữ liệu quan tâm chỉ có `sensor` và `reading`:

```java
record Snapshot(String sensor, int reading) {}

List<Snapshot> snapshots = new ArrayList<>();

stream.setReuse(true);
stream.onEvent("demo.Measurement", event -> {
    snapshots.add(new Snapshot(
            event.getString("sensor"),
            event.getInt("reading")
    ));
});
```

Đây là **đoạn minh họa trong ngữ cảnh có stream**, và `Snapshot` cần được khai báo trong phạm vi thích hợp. Ở đây:

- `RecordedEvent event` chỉ được truy cập **khi callback đang chạy**.
- `event.getString("sensor")` và `event.getInt("reading")` được đọc ngay; giá trị được đưa vào `Snapshot` riêng.
- `Snapshot` là record chứa `String` (bất biến) và `int`, nên có thể được giữ sau callback.
- Danh sách lưu các **snapshot độc lập**, không phải đối tượng `RecordedEvent` có thể bị reuse.

**Không phải mọi snapshot tự động bất biến sâu.** Nếu trích một component có kiểu mutable hoặc đối tượng phức tạp, cần copy phù hợp với cấu trúc đó. Với các trường JFR phức tạp như thông tin stack/thread, hãy lấy những thuộc tính cần thiết thành dữ liệu riêng và cân nhắc thông tin nhạy cảm, thay vì giả định việc giữ một tham chiếu tới đối tượng lồng nhau luôn an toàn.

### Đẩy việc xử lý sang luồng khác

Với executor, mã sau có nguy cơ sai:

```java
// Cố ý không an toàn nếu reuse=true.
stream.onEvent("demo.Measurement", event ->
        executor.execute(() -> process(event)));
```

Callback có thể kết thúc **trước khi** task trong executor chạy. Khi ấy đối tượng `event` có thể đã được dùng lại.

Cách đúng cho yêu cầu xử lý sau:

```java
stream.onEvent("demo.Measurement", event -> {
    Snapshot snapshot = new Snapshot(
            event.getString("sensor"),
            event.getInt("reading"));
    executor.execute(() -> process(snapshot));
});
```

Hai đoạn trên là **mẫu tích hợp**, yêu cầu `executor`, `process(...)` và `Snapshot` đã được định nghĩa. Việc trích dữ liệu trước khi giao task tránh phụ thuộc vòng đời `RecordedEvent`, nhưng không tự giải quyết mọi vấn đề backpressure, hàng đợi vô hạn, lỗi task hoặc shutdown executor. Với hệ thống tải lớn, cần thêm giới hạn queue và chính sách xử lý quá tải.

## 6. Chương trình Java 17+ hoàn chỉnh: cùng recording, hai chế độ

Ví dụ dùng **một tệp `.jfr` có ba custom event** để hai lần đọc cùng một bộ dữ liệu, giúp kiểm chứng hai hợp đồng khác nhau mà không phụ thuộc vào việc JVM có tình cờ tạo GC, socket hay allocation event trong khoảng đo ngắn.

Ở lượt đầu, `setReuse(true)` và callback chuyển trường sang `Snapshot`. Ở lượt sau, `setReuse(false)` và callback giữ `RecordedEvent` để đọc **sau khi `EventStream.start()` đã kết thúc**.

**Tệp `Main.java`:**

```java
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Duration;
import java.util.ArrayList;
import java.util.List;
import jdk.jfr.Event;
import jdk.jfr.Name;
import jdk.jfr.Recording;
import jdk.jfr.consumer.EventStream;
import jdk.jfr.consumer.RecordedEvent;

public class Main {
    @Name("demo.Measurement")
    static class Measurement extends Event {
        String sensor;
        int reading;
    }

    record Snapshot(String sensor, int reading) {}

    static void produce(Path output) throws Exception {
        try (Recording recording = new Recording()) {
            recording.enable(Measurement.class).withThreshold(Duration.ZERO);
            recording.start();
            for (int i = 1; i <= 3; i++) {
                Measurement event = new Measurement();
                event.sensor = "s-" + i;
                event.reading = i * 10;
                event.commit();
            }
            recording.stop();
            recording.dump(output);
        }
    }

    public static void main(String[] args) throws Exception {
        Path output = Files.createTempFile("jfr-reuse-", ".jfr");
        try {
            produce(output);

            List<Snapshot> snapshots = new ArrayList<>();
            try (EventStream stream = EventStream.openFile(output)) {
                stream.setReuse(true);
                stream.onEvent("demo.Measurement", event -> {
                    snapshots.add(new Snapshot(
                            event.getString("sensor"),
                            event.getInt("reading")));
                });
                stream.start();
            }
            System.out.println("REUSE_TRUE=" + snapshots);

            List<RecordedEvent> retained = new ArrayList<>();
            try (EventStream stream = EventStream.openFile(output)) {
                stream.setReuse(false);
                stream.onEvent("demo.Measurement", retained::add);
                stream.start();
            }
            List<String> values = retained.stream()
                    .map(event -> event.getString("sensor")
                            + ":" + event.getInt("reading"))
                    .toList();
            System.out.println("REUSE_FALSE=" + values);
            System.out.println("COUNT=" + retained.size());
        } finally {
            Files.deleteIfExists(output);
        }
    }
}
```

Biên dịch và chạy với JDK 17 trở lên:

```bash
javac --release 17 -encoding UTF-8 Main.java
java Main
```

**Stdout đã kiểm chứng:**

```text
REUSE_TRUE=[Snapshot[sensor=s-1, reading=10], Snapshot[sensor=s-2, reading=20], Snapshot[sensor=s-3, reading=30]]
REUSE_FALSE=[s-1:10, s-2:20, s-3:30]
COUNT=3
```

### Giải thích từng bước

1. `produce(...)` bật custom event `demo.Measurement`, phát ba giá trị khác nhau (`s-1`/`10`, `s-2`/`20`, `s-3`/`30`), dừng recording và ghi tệp.
2. `EventStream.openFile(output)` mở một stream đọc từ recording file; `start()` **xử lý đồng bộ**, không trả về trước khi stream đọc file hoàn tất.
3. Với `reuse=true`, callback đọc `sensor` và `reading` ngay trong thời gian callback còn hiệu lực, tạo `Snapshot`. Danh sách snapshot được sử dụng an toàn sau đó.
4. Với `reuse=false`, mỗi event được biểu diễn bằng một `RecordedEvent` mới, nên danh sách `retained` có thể chứa những event để đọc lại sau khi callback hoàn tất.
5. Hai lượt xử lý có **cùng dữ liệu nghiệp vụ**; `setReuse` thay đổi hợp đồng vòng đời đối tượng phía consumer, không thay nội dung logic của ba sự kiện.
6. Khối `finally` xóa tệp tạm. Đây là ví dụ có giới hạn, phù hợp kiểm thử. Trong hệ thống thực tế, cần chọn vị trí lưu recording và chính sách giữ/xóa dữ liệu theo yêu cầu vận hành.

**Không so sánh `==` giữa các `RecordedEvent` của lượt `reuse=true`.** Bài kiểm thử đúng ở đây là kết quả nghiệp vụ được snapshot hoặc lưu theo hợp đồng. Cho phép reuse không có nghĩa JVM phải sử dụng lại object trong tất cả tình huống.

## 7. Cách áp dụng trong `RecordingStream` đang chạy trực tiếp

Ngoài `EventStream.openFile(...)`, `RecordingStream` cũng hỗ trợ `setReuse(boolean)`. Với stream đang ghi và đọc sự kiện JVM theo thời gian thực, nguyên tắc vòng đời hoàn toàn tương tự.

Ví dụ khung tích hợp:

```java
// Đoạn bên trong một thành phần quản lý lifecycle.
try (jdk.jfr.consumer.RecordingStream stream =
        new jdk.jfr.consumer.RecordingStream()) {
    stream.enable("jdk.GarbageCollection");
    stream.setReuse(true);

    stream.onEvent("jdk.GarbageCollection", event -> {
        String type = event.getEventType().getName();
        long durationMillis = event.getDuration().toMillis();
        System.out.println(type + ": " + durationMillis + " ms");
    });

    stream.startAsync();

    // Ứng dụng cần giữ stream sống trong giai đoạn đo.
    // Đường kết thúc/đóng stream phải thuộc lifecycle của ứng dụng.
}
```

**Đây chỉ là khung để chỉ ra vị trí cấu hình**, không phải ứng dụng hoàn chỉnh để thu thập dữ liệu dài hạn: nếu khối `try` kết thúc ngay sau `startAsync()`, stream sẽ đóng quá sớm và có thể không nhận event. Cần tổ chức phạm vi sống của stream theo dịch vụ, tín hiệu shutdown hoặc công việc cần đo.

Trong ví dụ này, callback chỉ đọc thông tin và in **khi callback còn chạy**, nên phù hợp với reuse. Khi chuyển dữ liệu tới thread khác, hãy chuyển `String`, số, thời điểm hoặc snapshot tự sở hữu, **không chuyển trực tiếp `RecordedEvent`** khi reuse được bật.

Không nên coi `setReuse` là cách đảm bảo callback đã chạy. `setReuse` quản lý khả năng tái sử dụng **đối tượng sự kiện**; `startAsync()`, `awaitTermination(...)`, tín hiệu callback và `close()` là những vấn đề **vòng đời và đồng bộ khác**.

## 8. Quan hệ với `onFlush`, `setOrdered` và event filtering

### `onFlush` không tự kéo dài vòng đời `RecordedEvent`

JFR consumer có thể giao các event theo batch; `onFlush(Runnable)` báo khi hoàn thành một lần flush và hữu ích cho việc tổng hợp/push dữ liệu ra ngoài.

Nếu `reuse=true`, không nên lưu một danh sách `RecordedEvent` rồi chờ `onFlush` để đọc lại. **Callback đã kết thúc trước đó**, và stream có thể đã dùng lại các đối tượng. Thay vào đó, hãy trích trường, cộng số liệu hoặc tạo snapshot **ngay trong `onEvent`**, rồi `onFlush` xử lý **kết quả tổng hợp do ứng dụng sở hữu**.

```java
// Khung minh họa: counters do ứng dụng sở hữu và được thiết kế đồng bộ phù hợp.
stream.setReuse(true);
stream.onEvent("demo.Measurement", event -> {
    snapshots.add(new Snapshot(
            event.getString("sensor"),
            event.getInt("reading")));
});
stream.onFlush(() -> flushSnapshots(snapshots));
```

Mẫu này cần định nghĩa `snapshots`, `Snapshot` và `flushSnapshots`, và **phải** xem xét thread-safety, việc làm rỗng danh sách sau flush, xử lý lỗi và backpressure trong ứng dụng thực tế. Cốt lõi là dữ liệu trong `snapshots` **không phụ thuộc tham chiếu `RecordedEvent`**.

### `setOrdered` là lựa chọn riêng

`setOrdered(boolean)` điều chỉnh chính sách thứ tự giao event cho callback; nó **không** quyết định object có được tái sử dụng hay không. Nếu bạn cần sắp xếp theo thời điểm hoặc tổng hợp theo cửa sổ, hãy chọn cấu hình ordering và kiểm tra sự phù hợp với mục tiêu. Đừng giả định `setReuse(false)` làm event luôn theo thứ tự timestamp hoặc `setReuse(true)` làm callback chạy song song.

### Filter theo event type thường có ích hơn xử lý mọi event

Khi chỉ cần một loại event, ưu tiên:

```java
stream.onEvent("demo.Measurement", event -> {
    // xử lý một type đã chọn
});
```

so với đăng ký `onEvent(event -> ...)` cho tất cả type rồi lọc thủ công trong callback, nếu việc đăng ký theo tên đáp ứng nhu cầu. Điều này có thể giúp triển khai bỏ qua những event không liên quan và giảm công việc của consumer. Hiệu năng thực tế còn phụ thuộc việc ghi, decode và cấu hình stream.

## 9. Chi phí và đánh đổi: khi nào chọn true, khi nào chọn false?

**Chọn `setReuse(true)` khi:**

- Callback chỉ đọc một vài trường, tính metric hoặc cập nhật bộ đếm rồi trả về.
- Dữ liệu cần giữ được chuyển ngay thành snapshot nhỏ, immutable và độc lập.
- Khối lượng sự kiện cao và muốn giảm cấp phát ở phía consumer.
- Bạn đã kiểm tra cả đường xử lý bình thường lẫn callback/error-handling không vô tình giữ `RecordedEvent`.

**Chọn `setReuse(false)` khi:**

- Một số component của hệ thống thực sự cần giữ `RecordedEvent` sau callback, chẳng hạn bước phân tích tiếp theo đọc lại nhiều trường.
- Việc viết snapshot thích hợp chưa khả thi và bạn chủ động chấp nhận chi phí cấp phát/giữ dữ liệu.
- Có thể kiểm soát số sự kiện được lưu, thời gian lưu và cách giải phóng.

**Không nên quyết định chỉ dựa trên trực giác.** Benchmark trên workload tương ứng và theo dõi allocation rate, GC, CPU tiêu thụ của consumer, throughput callback, số event được xử lý và dung lượng dữ liệu giữ lại. `setReuse(true)` có thể giảm chi phí cấp phát wrapper nhưng không xóa bỏ chi phí parse JFR, I/O, callback, phép tính hay snapshot do ứng dụng tự tạo.

Một ứng dụng phải snapshot nhiều trường dữ liệu vẫn có thể cấp phát đáng kể dù `setReuse(true)`. Nếu lượng event quá lớn, giới hạn loại event, sampling/threshold và batch processing có thể quan trọng hơn bản thân cờ reuse.

## 10. Những hiểu nhầm dễ dẫn tới lỗi

| Hiểu nhầm | Sự thật | Cách xử lý |
| --- | --- | --- |
| “`setReuse(true)` là cache sự kiện đã ghi” | Nó cho phép tái sử dụng **đối tượng `RecordedEvent` của consumer** | Không nhầm với việc JFR giữ/ghi dữ liệu |
| “Tất cả callback nhận cùng một object khi reuse=true” | API chỉ nói **có thể** tái dùng, không bảo đảm identity cố định | Không assert `==` |
| “`setReuse(false)` giúp JFR ghi ít sự kiện hơn” | Nó liên quan số object ở phía đọc, không phải filter recording | Dùng `enable`/`disable` và settings event |
| “Có thể bỏ event vào queue rồi đọc sau khi reuse=true” | Event có thể bị tái sử dụng sau callback | Trích dữ liệu trong callback hoặc chọn false |
| “Giữ `List<RecordedEvent>` là an toàn trong mọi chế độ” | Chỉ phù hợp với hợp đồng không reuse; còn có vấn đề giữ bộ nhớ vô hạn | `setReuse(false)` hoặc snapshot + retention policy |
| “Dùng `setReuse(false)` là có deep copy mọi đối tượng lồng nhau” | API bảo đảm object event riêng; không đồng nghĩa một chiến lược deep copy cho mọi dữ liệu ứng dụng | Trích/copy đúng những trường cần |
| “`onFlush` bảo vệ các `RecordedEvent` đã lưu” | Flush không thay đổi hợp đồng vòng đời của đối tượng callback | Lưu snapshot hoặc số liệu tổng hợp |
| “`startAsync()` đã trả về thì mọi event đã xử lý” | Nó chỉ khởi động xử lý bất đồng bộ | Chờ tín hiệu, dùng lifecycle đúng |
| “`setReuse(true)` làm callback thread-safe” | Nó không đồng bộ hóa collection, biến và executor | Dùng cơ chế đồng bộ phù hợp |
| “Càng ít đối tượng mới thì luôn nhanh hơn” | Chi phí tùy workflow, decode, callback, snapshot và GC | Đo bằng workload đại diện |

**Đặc biệt cẩn thận** khi hai callback cùng được đăng ký trên một stream: cùng một đối tượng `RecordedEvent` có thể được giao nhiều lần, kể cả giữa các callback. Không được dùng **identity của object** làm khóa duy nhất cho event nghiệp vụ.

## 11. Hướng kiểm thử và xác minh

Không nên kiểm thử `setReuse` bằng cách đếm số lần xuất hiện của một object identity, vì reuse có thể **được phép nhưng không nhất thiết xảy ra trong một lần chạy cụ thể**.

Thay vào đó, viết test cho **hợp đồng cần thiết của ứng dụng**:

1. Phát một bộ custom event có trường định danh riêng (`sensor`, `reading`).
2. Với `reuse=true`, đọc trong callback và lưu snapshot; sau stream, khẳng định snapshot có đúng các giá trị.
3. Với `reuse=false`, giữ `RecordedEvent` để xử lý sau callback và xác nhận kết quả đọc khớp các event đã tạo.
4. Nếu đẩy sang executor, kiểm tra chỉ có **snapshot** được gửi khi reuse bật.
5. Thử tải dài hơn, số event lớn hơn và cơ chế kết thúc stream có kiểm soát để phát hiện giữ tham chiếu sai hoặc queue không giới hạn.
6. Kiểm tra lỗi consumer, ngắt stream, đường shutdown và retention policy; không chỉ kiểm tra một ca thành công.

### Vì sao ví dụ dùng `EventStream.openFile`?

Đọc tệp JFR hữu hạn cho phép `start()` chạy đến cuối file một cách xác định, giúp test tập trung vào **reuse của `RecordedEvent`**, thay vì phải đoán khi nào event realtime sẽ được flush. Trong một service thực tế có `RecordingStream.startAsync()`, vẫn cần quản lý vòng đời, chờ callback hoặc cấu hình shutdown riêng.

Ví dụ trong bài đã được biên dịch với `javac --release 17` và chạy trên JVM có JFR; kết quả xác nhận hai chế độ đều đọc đúng **ba sự kiện**. Điều này **không phải benchmark tốc độ** và không hứa cùng mức tiết kiệm memory trên mọi workload.

## 12. Checklist trước khi đưa `setReuse` vào ứng dụng

- **Consumer có giữ `RecordedEvent` sau callback không?** Nếu có, chọn false hoặc đổi sang snapshot.
- **Có giao tham chiếu event sang thread/task khác không?** Nếu có và reuse=true, phải trích dữ liệu trước khi callback kết thúc.
- **Có nhiều callback cho cùng stream không?** Không dùng identity để định danh sự kiện.
- **Có giới hạn dữ liệu lưu trong heap không?** `reuse=false` không tự giải quyết memory growth do ứng dụng giữ quá nhiều sự kiện.
- **Có kiểm chứng thông báo lỗi và thời điểm close không?** Reuse khác với lifecycle của stream.
- **Đã so sánh hiệu năng thực tế chưa?** Quyết định bằng kết quả đo, không bằng giả định “true luôn nhanh hơn”.

**Ghi nhớ:** `setReuse(true)` cho phép JFR consumer tái sử dụng đối tượng `RecordedEvent` và thường phù hợp với **xử lý ngay trong callback**. Muốn lưu hoặc bàn giao dữ liệu về sau, hãy **snapshot các trường cần dùng trong callback**. `setReuse(false)` cung cấp một object event mới cho từng event khi bạn thật sự cần giữ `RecordedEvent`, đổi lại có thể tạo thêm áp lực bộ nhớ. Đó là **hợp đồng về vòng đời đối tượng**, không phải cơ chế phát sự kiện, filtering hay đồng bộ bất đồng bộ.

### Tham khảo chính thức

- [Java SE 21 — EventStream, mục `setReuse` và mô tả mặc định](https://docs.oracle.com/en/java/javase/21/docs/api/jdk.jfr/jdk/jfr/consumer/EventStream.html).
- [Java SE 21 — RecordingStream](https://docs.oracle.com/en/java/javase/21/docs/api/jdk.jfr/jdk/jfr/consumer/RecordingStream.html).
- [Java SE 21 — RecordedEvent](https://docs.oracle.com/en/java/javase/21/docs/api/jdk.jfr/jdk/jfr/consumer/RecordedEvent.html).
- [JEP 349 — JFR Event Streaming](https://openjdk.org/jeps/349).
