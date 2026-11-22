# Java 11+ — Flight Recorder: Đọc bản ghi bằng công cụ phân tích tương thích

## 1. Mục tiêu: từ tệp `.jfr` đến kết luận có thể kiểm chứng

**Java Flight Recorder (JFR)** là cơ chế ghi các sự kiện có dấu thời gian từ JVM và ứng dụng Java. Kết quả có thể lưu trong một tệp **`.jfr`** để điều tra CPU, GC, cấp phát, luồng, khóa đồng bộ, I/O và các sự kiện ứng dụng tự định nghĩa. JFR đã được tích hợp trong **OpenJDK/JDK 11** và các JDK hiện đại; đây là kiến thức vẫn đang áp dụng.

Để đọc một bản ghi đúng cách, cần phân biệt:

- **Tạo/ghi bản ghi**: JVM hoặc API `jdk.jfr.Recording` thu thập events theo cấu hình và ghi tệp `.jfr`.
- **Đọc nhanh qua command line**: công cụ **`jfr`** của JDK có thể tóm tắt, liệt kê metadata hoặc in sự kiện theo bộ lọc.
- **Phân tích trực quan**: **JDK Mission Control (JMC)** mở tệp để xem timeline, phân tích tự động, biểu đồ, thread/lock, GC và những dữ liệu có sẵn.
- **Đọc có lập trình**: **`jdk.jfr.consumer.RecordingFile`** và **`RecordedEvent`** trên Java 11 cho phép duyệt, lọc, tổng hợp events.
- **Kiểm tra tương thích**: công cụ đọc phải hiểu **định dạng tệp, metadata và event schemas** của runtime đã ghi; không suy ra rằng mọi tool/version đều xử lý đầy đủ mọi bản ghi mới.
- **Bảo vệ dữ liệu**: bản ghi có thể chứa stack trace, tên lớp/phương thức/luồng, đường dẫn, args hoặc trường do ứng dụng ghi. Không nên coi `.jfr` là tệp vô hại để chia sẻ công khai.

**`.jfr` là tệp nhị phân**, không phải log text hoặc JSON chuẩn. Mở nó bằng text editor/`grep` trên raw bytes không phải cách phân tích đáng tin. Khi cần JSON hoặc định dạng hiển thị, hãy **xuất từ công cụ JFR có khả năng đọc tệp**.

Bài này trình bày quy trình **đọc bằng công cụ phân tích tương thích** và ví dụ **tạo một bản ghi .jfr thật, phân tích lại bằng API Java 11 và `jfr`**, có stdout xác định. Không yêu cầu dịch vụ ngoài Internet.

## 2. Phân biệt JFR, JMC, công cụ `jfr` và `.jfc`

| Thành phần | Vai trò | Có trong JDK 11? | Khi dùng |
| --- | --- | --- | --- |
| **JFR** | Bộ ghi sự kiện bên trong JVM và API `jdk.jfr`. | **Có** ở các bản JDK 11 triển khai JFR. | Khi cần chụp hoạt động JVM/ứng dụng. |
| **`.jfr`** | Tệp bản ghi nhị phân chứa dữ liệu và metadata sự kiện. | Được JFR tạo ra. | Đầu vào cho công cụ đọc/phân tích. |
| **`jfr` CLI** | Đọc tệp, in sự kiện, xem tổng hợp/metadata. | Có trong JDK hỗ trợ công cụ này; kiểm tra `jfr help` của bản cài. | Xem nhanh, lọc event, trích xuất để điều tra. |
| **JDK Mission Control (JMC)** | Ứng dụng GUI phân tích JFR và giám sát JVM. | **Không phải ứng dụng GUI được đóng sẵn trong JDK 11 thông thường**; cài riêng bản JMC phù hợp. | Điều tra tương tác và xem các tương quan trên timeline. |
| **`jdk.jfr.consumer`** | Java API đọc `.jfr`, ví dụ `RecordingFile`/`RecordedEvent`. | **Có** trong module `jdk.jfr` của Java 11. | Xây phân tích, báo cáo hoặc trích lọc tự động bằng Java. |
| **`.jfc`** | Tệp cấu hình Flight Recorder để chọn loại sự kiện và ngưỡng thu thập. | Có cấu hình JFR của JDK. | Cấu hình **khi ghi**, không phải bản ghi dữ liệu. |

**Đừng gửi một tệp `.jfc` cho JMC và mong thấy các sự kiện đã được ghi:** `.jfc` chỉ mô tả settings. Tệp cần mở khi phân tích là **`.jfr`**.

Tên `JFR` thường được dùng cho **cơ chế ghi**, còn `JMC` là **công cụ phân tích/GUI**. Chúng phối hợp với nhau nhưng có vòng đời phát hành/phiên bản khác nhau. Không suy luận rằng JDK đã cài là có ngay cửa sổ JMC.

### Tại sao “tương thích” quan trọng?

Một tệp `.jfr` có **metadata type**, danh sách events và fields. Khi JVM/runtime mới bổ sung một event, một field hoặc encoding mới, tool phân tích cũ có thể:

- Đọc file nhưng **không hiển thị** đúng một số events/fields;
- Không có giao diện phân tích chuyên biệt cho sự kiện mới;
- Báo không hiểu phiên bản/định dạng;
- Từ chối đọc toàn bộ file nếu file version vượt khả năng parser.

Cách xử lý an toàn: **kiểm tra JDK đã tạo file và bản JMC/JDK của công cụ đọc**; ưu tiên phiên bản reader có hỗ trợ bản ghi đó. Dù tool đọc được file, vẫn cần kiểm tra event names, fields, timestamp và dữ liệu có thực sự đủ để đưa ra kết luận.

**Không phải lúc nào cũng cần nâng JVM production** để mở một bản ghi: có thể sử dụng công cụ `jfr`/JMC của một JDK mới hơn **trên máy phân tích riêng**. Tính tương thích theo chiều đó cũng phải được thử với file cụ thể; không có quy tắc “mọi bản JFR luôn đọc được mọi file”.

## 3. Quy trình đọc nhanh một bản ghi có sẵn

Giả sử bạn đã có tệp **`sample.jfr`** trong thư mục đang làm việc. Nếu chưa có, mục 8 hướng dẫn tạo tệp thật bằng Java.

### Bước 1 — Xác định runtime và công cụ đang dùng

```bash
java -version
javac -version
jfr help
```

Những lệnh này cho biết runtime/compiler và danh sách lệnh được công cụ `jfr` hiện có hỗ trợ. Trong môi trường có nhiều JDK, phải chú ý lệnh `java` và `jfr` có thể đến từ **hai JDK khác nhau** theo `PATH`. Nếu nghi ngờ, gọi `jfr` từ **thư mục `bin` của JDK được chọn** hoặc kiểm tra đường dẫn thực tế theo hệ điều hành.

Cẩn thận với tài liệu tham khảo: các JDK hiện đại có thể có **subcommand mới** như `jfr view`, `jfr scrub` hoặc thêm option khác. Không đưa các lệnh đó vào workflow yêu cầu **chắc chắn chạy trên JDK 11** khi chưa xác minh help của bản 11 đang dùng. Các thao tác nền tảng phù hợp cho bài này là **`summary`, `print` và `metadata`**.

### Bước 2 — Xem tổng quan bản ghi

```bash
jfr summary sample.jfr
```

Lệnh này hiển thị các thông tin tổng hợp như số chunk, version, khoảng thời gian và thống kê **loại sự kiện / số lần / kích thước**. Trước khi mở toàn bộ file, hãy trả lời:

- Đây có thật sự là một tệp `.jfr` mà công cụ đọc được không?
- Khoảng thời gian của recording có bao phủ thời điểm cần điều tra không?
- Event type mình cần có xuất hiện không, và **đếm có lớn hơn 0** không?
- File có kích thước/số events rất lớn khiến việc in toàn bộ trở nên tốn kém không?
- Những events quan trọng có thể đã bị tắt bởi recording configuration hay không?

Với tệp sinh ở mục 8, dòng tổng hợp có **`demo.WorkStep` với count 3**. Các số khác như kích thước file, thời gian bắt đầu, duration và tổng events phụ thuộc JDK, máy chạy và cấu hình recording; **không** dùng chúng làm expected output tuyệt đối.

### Bước 3 — Chỉ in events đang quan tâm

```bash
jfr print --events demo.WorkStep sample.jfr
```

Bộ lọc **`--events`** giúp tránh hàng nghìn dòng system events không liên quan. Với example, output sẽ có **ba đối tượng `demo.WorkStep`**, lần lượt mang:

```text
phase = "parse"
items = 10

phase = "compute"
items = 20

phase = "write"
items = 30
```

Đây là **những dòng field đã trích ra từ output thật**; `jfr print` còn in timestamp, duration, object nesting và các trường hệ thống tùy event, nên không trình bày khối trên như **toàn bộ** output.

Bộ lọc là **event type name**, không nhất thiết là nhãn hiển thị của GUI. Sự kiện do Java định nghĩa bằng `@Name("demo.WorkStep")` sẽ có tên type `demo.WorkStep`, còn các sự kiện của JVM thường có dạng `jdk.CPULoad`, `jdk.GarbageCollection`, `jdk.JavaMonitorEnter`... Tên thực tế cần kiểm tra bằng metadata/summary của chính tệp, không áp đặt một danh sách bất biến cho mọi JDK.

### Bước 4 — Xuất dạng máy đọc được

```bash
jfr print --json --events demo.WorkStep sample.jfr
```

JSON là **kết quả xuất ra bởi CLI**, không phải byte layout gốc của `.jfr`. Nó phù hợp để xem hoặc đưa vào pipeline parsing có kiểm soát. Với tệp lớn, xuất toàn bộ JSON ra stdout có thể chiếm RAM, CPU và log storage; lọc events trước và tránh lưu dữ liệu nhạy cảm không cần thiết.

Ngoài JSON, những phiên bản `jfr print` hỗ trợ `--xml` có thể xuất XML; phải kiểm tra help của JDK đang dùng nếu dựa vào một option cụ thể.

### Bước 5 — Kiểm tra schema/metadata

```bash
jfr metadata sample.jfr
```

Metadata giúp xác nhận tên event type, category, kiểu field, annotation như timestamp/timespan/label và cách biểu diễn nested values. **Không nên đoán field** (ví dụ `durationMs`, `threadName`) chỉ từ màn hình GUI rồi gọi API `getString(...)`; hãy dùng tên field có trong bản ghi và kiểm tra kiểu thật.

Cần phân biệt:

- **Event type ID** có thể thay đổi giữa recordings/runtime; không dùng một con số event ID cố định để parse mọi file.
- **Event type name** có ích cho bộ lọc nhưng không bảo đảm fields y hệt qua mọi JDK/plugin.
- **Nhãn hiển thị** từ `@Label` và **tên field kỹ thuật** có thể khác nhau.
- Nếu thiếu field hoặc kiểu thay đổi, cần fallback có chủ đích hoặc báo version incompatibility, không tự gán giá trị 0 rồi kết luận “không có hoạt động”.

## 4. Phân tích bằng JDK Mission Control (JMC)

**JMC** là công cụ GUI phù hợp khi muốn hiểu **mối quan hệ giữa các events và diễn biến theo thời gian**, thay vì chỉ xem từng bản ghi text.

Quy trình chung:

1. Cài **bản JMC phù hợp** từ nguồn phát hành chính thức, phù hợp với môi trường và định dạng JFR đang phân tích. JMC chạy như một ứng dụng riêng; không mặc định có sẵn trong JDK.
2. Mở JMC, dùng chức năng **Open File** trong menu hoặc mở một tệp `.jfr` bằng giao diện của JMC. Tên menu/vị trí màn hình có thể khác giữa các bản JMC.
3. Xem **Automated Analysis Results** để tìm cảnh báo và gợi ý ban đầu. Đây là **heuristic/rule-based analysis**, không phải bằng chứng nguyên nhân gốc.
4. Chọn **khoảng thời gian (time range)** liên quan đến sự cố: giảm nhiễu do dữ liệu trước/sau.
5. Dùng các trang và views như **Event Browser**, **Threads**, **Memory/GC**, **Code/Method Profiling**, **Locks** và **I/O** theo dữ liệu có trong file và tính năng của JMC đã cài.
6. Duyệt **event type tự định nghĩa** trong Event Browser; với ví dụ mục 8, tìm `demo.WorkStep` hoặc nhóm category **Demo / Workflow** và xem các field `phase`, `items`.
7. Đối chiếu timestamps, durations, thread/stack information, GC events và application events trước khi kết luận. Không chỉ nhìn một cột “hot method” rồi tuyên bố đã tìm đúng bottleneck.
8. Lưu lại **thời gian, filter, recording source, JDK và phiên bản JMC** khi chia sẻ kết quả điều tra, để người khác tái hiện.

<escape>Lưu ý:</escape> các recordings lấy từ JDK cũ thường có thể được đọc trong nhiều bản JMC mới, nhưng đây không phải giấy phép bỏ qua kiểm tra tương thích thực tế. Khi JMC không mở được, hãy phân biệt lỗi format, lỗi file bị cắt, lỗi quyền truy cập và phiên bản JMC quá cũ; xác minh thêm bằng **`jfr summary`** và một reader khác nếu cần.

### Màn hình nào hữu ích cho từng câu hỏi?

| Câu hỏi điều tra | Dữ liệu/view nên tìm | Cẩn trọng |
| --- | --- | --- |
| Vì sao latency tăng? | Thread states, lock contention, socket/file I/O, method samples, custom duration events. | Correlation **không tự chứng minh** nguyên nhân. |
| Có GC pause liên quan? | GarbageCollection, GC phases, allocation events, heap usage. | Recording có thể không bật mọi GC event cần thiết. |
| Chương trình dùng CPU ở đâu? | Execution samples, allocation, method/stack views. | **Sampling** cho thống kê, không phải đếm tuyệt đối số lời gọi. |
| Thread nào đang chờ khóa? | Java monitor enter/wait, thread park, stack traces. | Threshold có thể lọc bỏ wait ngắn. |
| Mạng/đĩa có nghẽn? | Socket read/write, file read/write, durations và thread context. | Thời gian chờ không đồng nghĩa lượng byte hoặc server lỗi. |
| Các bước nghiệp vụ mất bao lâu? | Custom events có `@Name`, `@Label`, duration và field metadata. | Cần event được bật và commit đúng; không nên ghi dữ liệu cá nhân vào event. |

**JMC không phải bản thân cơ chế recording.** Nó có thể mở một `.jfr` đã lưu ở nơi khác và chạy offline, miễn phiên bản tương thích và chính sách bảo mật cho phép.

## 5. Phân tích bằng Java 11 API: `jdk.jfr.consumer`

Từ Java 11, có thể dùng **API chính thức** thay vì parse byte format tự tạo:

```java
try (RecordingFile reader = new RecordingFile(Path.of("sample.jfr"))) {
    while (reader.hasMoreEvents()) {
        RecordedEvent event = reader.readEvent();
        System.out.println(event.getEventType().getName());
    }
}
```

Đây là snippet cần đặt trong một method có xử lý `IOException` và import `Path`, `RecordingFile`, `RecordedEvent`. Mục 8 có chương trình đầy đủ.

Những đối tượng quan trọng:

| API | Vai trò | Lưu ý khi đọc |
| --- | --- | --- |
| `RecordingFile(Path)` | Mở tệp JFR cho consumer API. | Dùng `try-with-resources` để đóng; API khuyến cáo chỉ đọc file từ **nguồn đáng tin**. |
| `hasMoreEvents()` | Kiểm tra có events chưa đọc. | Đi cùng `readEvent()`; không cần giữ toàn bộ recording trong RAM. |
| `readEvent()` | Đọc một `RecordedEvent` tiếp theo. | Có thể ném `IOException`; không truy cập field không tồn tại. |
| `readEventTypes()` | Liệt kê các `EventType` có trong recording. | Giúp khám phá schema, không nên dùng như thống kê count của events. |
| `RecordingFile.readAllEvents(path)` | Đọc toàn bộ events thành một `List`. | Chỉ phù hợp **file nhỏ**; Oracle nói rõ không dành cho file lớn. |
| `RecordedEvent.getEventType()` | Lấy tên, category/fields và metadata type. | Lọc bằng `getName()` thay vì class JVM của sự kiện. |
| `RecordedEvent.getStartTime()` | Thời điểm bắt đầu event (`Instant`). | Là timestamp, không phải duration. |
| `RecordedEvent.getDuration()` | `Duration` của event. | Có thể bằng 0 với instant event; không phải CPU time của thread. |
| `RecordedEvent.hasField(name)` | Kiểm tra field có tồn tại trong type đó. | Tốt cho schema khác nhau giữa runtimes. |
| `RecordedEvent.getString/getInt/getLong/getValue` | Đọc giá trị field với kiểu tương ứng. | Cần đúng tên/kiểu; có thể lỗi nếu không phù hợp. |
| `RecordedEvent.getThread()` | Metadata thread được ghi kèm event, hoặc `null`. | Không phải event nào cũng giữ thread. |
| `RecordedEvent.getStackTrace()` | Stack trace khi event được commit, hoặc `null`. | Phụ thuộc event settings và runtime; không bảo đảm có stack. |

**Không lưu mọi event vào `List` chỉ để đếm vài loại:** duyệt từng event qua `RecordingFile` là cách thường phù hợp hơn với recordings lớn. Lưu ý parser vẫn cần tài nguyên cho metadata/chunks; thiết lập hạn mức kích thước file, nguồn nhận và thời gian xử lý.

### Xử lý field không tồn tại và khác kiểu

```java
if (event.hasField("items")) {
    int items = event.getInt("items");
    // Dùng items sau khi đã xác định event type/schema phù hợp.
}
```

Đây là đoạn minh họa trong vòng lặp consumer. `hasField` kiểm tra **sự tồn tại**, không chứng minh giá trị chắc chắn có kiểu mong đợi. Khi cần xử lý file nhiều phiên bản, xem `EventType.getFields()` hoặc `ValueDescriptor` để kiểm tra type/metadata. Nếu schema đã thay đổi, chọn nhánh tương thích rõ ràng hoặc thông báo không hỗ trợ.

**Không dùng `event.getValue("thread.name")` cho mọi event**: cấu trúc nested fields tùy event type và có thể null. `RecordedObject` hỗ trợ đường dẫn field lồng nhau nhưng có thể ném lỗi khi một phần không tồn tại/null. Với tệp từ các JDK khác nhau, cần validate.

## 6. Thiết kế một bộ đọc JFR có khả năng phân tích đúng

Một consumer dùng trong dịch vụ phân tích cần xử lý:

1. **Nguồn file và giới hạn:** chỉ tiếp nhận `.jfr` từ nơi đáng tin, giới hạn kích thước, số file, timeout, CPU/RAM và quyền đọc. Không parse các tệp lạ từ Internet trực tiếp trong một dịch vụ có đặc quyền cao.
2. **Version/metadata:** lưu JDK source, tool reader version; xem `jfr summary` hoặc metadata trước khi ánh xạ vào schema nghiệp vụ.
3. **Streaming iteration:** ưu tiên `hasMoreEvents/readEvent` hơn `readAllEvents` khi recording lớn.
4. **Lọc theo event type:** dùng `getEventType().getName()`, không hard-code numeric event type ID.
5. **Schema guard:** dùng `hasField`, field descriptors và nhận diện event type; không dựa vào tên label GUI.
6. **Quy đổi thời gian:** `Instant` là timestamp, `Duration` là khoảng; chuyển sang ms/us/nanos khi báo cáo và ghi rõ đơn vị.
7. **Aggregation:** group theo type, thread, time window hoặc phase; đặt lại kết quả theo context workload, không chỉ số đếm thô.
8. **Tính không đầy đủ:** events có thể bị tắt, lọc bởi threshold, sampling hoặc ghi trong cửa sổ chưa đủ thời gian; absence không luôn có nghĩa không có vấn đề.
9. **Đầu ra bảo mật:** không xuất command-line chứa secret, data custom events hoặc stack trace nhạy cảm ra kênh không được phép.
10. **Độ tin cậy:** test với recording từ các JDK thực tế, file hỏng/truncated, file mới hơn và events bị thiếu trường.

### Khi nào nên dùng event `getDuration()`?

`RecordedEvent.getDuration()` là khoảng giữa start/end theo event metadata, đo **wall-clock duration** của event. Nó không phải “CPU time đã tiêu thụ”, không phải thời gian chỉ chạy trên CPU và không thay được profiling CPU. Một event I/O dài thường bao gồm **thời gian chờ**, không chỉ thời gian thực thi.

Muốn tìm CPU bottleneck, kết hợp method samples, thread state, CPU load và bối cảnh workload; không cộng tất cả `getDuration()` rồi gọi đó là tổng CPU. Nhiều events có thể chồng lấn thời gian trên các luồng khác nhau.

Khi một custom event gọi `begin()` và `end()` liền nhau, duration có thể cực ngắn hoặc bằng zero tùy độ phân giải thời gian. Điều này không có nghĩa JFR thu thập sai.

## 7. Tạo dữ liệu kiểm chứng an toàn: custom event có schema rõ

Để bài học có tệp thật mà không cần một service production, ta tạo custom event **`demo.WorkStep`**:

- Metadata `@Name("demo.WorkStep")` là tên event type mà `jfr print --events` và consumer dùng để lọc.
- `@Label("Work step")` cung cấp nhãn dễ đọc; `@Category({"Demo","Workflow"})` giúp phân nhóm trong công cụ phân tích.
- Field `phase` kiểu `String` lưu các bước `parse`, `compute`, `write`.
- Field `items` kiểu `int` có giá trị `10`, `20`, `30`.
- Dùng `Recording.enable(WorkStep.class).withThreshold(Duration.ZERO)` để giữ cả những events có duration rất ngắn. `withoutStackTrace()` để giảm thông tin bổ sung không cần trong fixture.
- Gọi `recording.start()`, commit ba events, `recording.stop()` và `recording.dump(path)` tạo tệp.
- Mở file bằng `RecordingFile`, lọc đúng `getEventType().getName()`, cộng `items` và sắp xếp `phase` trước khi in để stdout ổn định.

**Điểm QA:** ví dụ **tạo một tệp `.jfr` thật** bằng API JFR, rồi **đọc tệp thật ấy**. Nó không phải tự tạo danh sách Java đối tượng giả rồi tuyên bố đã parse JFR.

Tuy nhiên, chương trình demo **không đo hiệu năng thật**: events được commit ngay trong vòng lặp, không có truy vấn DB, GC stress hoặc I/O production. Các con số `10/20/30` là dữ liệu do fixture đặt, không phải kết quả profiler.

## 8. Chương trình Java 11 hoàn chỉnh: ghi mẫu và phân tích lại

Lưu tệp **`JfrAnalysisDemo.java`**:

```java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Duration;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import jdk.jfr.Category;
import jdk.jfr.Event;
import jdk.jfr.Label;
import jdk.jfr.Name;
import jdk.jfr.Recording;
import jdk.jfr.consumer.RecordedEvent;
import jdk.jfr.consumer.RecordingFile;

public final class JfrAnalysisDemo {
    @Name("demo.WorkStep")
    @Label("Work step")
    @Category({"Demo", "Workflow"})
    static class WorkStep extends Event {
        @Label("Phase")
        String phase;

        @Label("Items")
        int items;
    }

    private static void capture(Path file) throws IOException {
        try (Recording recording = new Recording()) {
            recording.enable(WorkStep.class)
                    .withThreshold(Duration.ZERO)
                    .withoutStackTrace();
            recording.start();
            String[] phases = {"parse", "compute", "write"};
            int[] items = {10, 20, 30};
            for (int i = 0; i < phases.length; i++) {
                WorkStep event = new WorkStep();
                event.phase = phases[i];
                event.items = items[i];
                event.begin();
                event.end();
                event.commit();
            }
            recording.stop();
            recording.dump(file);
        }
        System.out.println("recording-created=" + Files.isRegularFile(file));
    }

    private static void analyze(Path file) throws IOException {
        long count = 0;
        long items = 0;
        boolean durationsOk = true;
        boolean fieldsOk = true;
        List<String> phases = new ArrayList<>();
        try (RecordingFile reader = new RecordingFile(file)) {
            while (reader.hasMoreEvents()) {
                RecordedEvent event = reader.readEvent();
                if (!"demo.WorkStep".equals(event.getEventType().getName())) {
                    continue;
                }
                fieldsOk &= event.hasField("phase") && event.hasField("items");
                count++;
                items += event.getInt("items");
                phases.add(event.getString("phase"));
                durationsOk &= !event.getDuration().isNegative();
            }
        }
        Collections.sort(phases);
        System.out.println("work-step-events=" + count);
        System.out.println("total-items=" + items);
        System.out.println("phases=" + String.join(",", phases));
        System.out.println("expected-fields=" + fieldsOk);
        System.out.println("nonnegative-durations=" + durationsOk);
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 2) {
            throw new IllegalArgumentException(
                    "Use: capture|analyze <recording.jfr>");
        }
        Path file = Path.of(args[1]);
        if ("capture".equals(args[0])) {
            capture(file);
        } else if ("analyze".equals(args[0])) {
            analyze(file);
        } else {
            throw new IllegalArgumentException("Unknown mode");
        }
    }
}
```

### Biên dịch và thực thi

Dùng JDK có module `jdk.jfr`, Java 11 trở lên; `--release 11` xác minh cú pháp và API từ Java 11:

```bash
javac -encoding UTF-8 --release 11 JfrAnalysisDemo.java
java JfrAnalysisDemo capture sample.jfr
java JfrAnalysisDemo analyze sample.jfr
```

**Stdout chính xác đã được kiểm thử:**

```text
recording-created=true
work-step-events=3
total-items=60
phases=compute,parse,write
expected-fields=true
nonnegative-durations=true
```

Giải thích:

1. `recording-created=true` xác nhận đường dẫn `sample.jfr` là regular file sau khi recording được dump.
2. `work-step-events=3` vì người tạo gọi `commit()` ba lần cho đúng event type được bật. Reader vẫn duyệt những event types khác có thể xuất hiện trong tệp nhưng chỉ đếm `demo.WorkStep`.
3. `total-items=60` vì `10+20+30=60`; đây là tổng field nghiệp vụ, không phải tổng CPU hoặc số byte của JFR.
4. `phases=compute,parse,write` là kết quả **sắp xếp bảng tên phase theo alphabet** trước khi in. Nó không chứng minh recording phát sinh theo thứ tự này (fixture tạo theo thứ tự `parse,compute,write`).
5. `expected-fields=true` cho biết các events đã chọn đều có field `phase` và `items`. Với recording thực tế, cần kiểm tra **kiểu field** nữa nếu nguồn JDK/schema có thể khác.
6. `nonnegative-durations=true` cho biết thời lượng mà API trả về của các events đó không âm; nó không xác minh latency production, sampling accuracy hay thời gian thật của từng bước.

**Tệp `sample.jfr` là file nhị phân được JVM tạo ra**, có thể mở lại bằng `jfr` hoặc JMC. Tệp có thể chứa **những events/metadata khác** ngoài `demo.WorkStep` tùy JDK và runtime. Không assert kích thước `sample.jfr` cố định hoặc số event JVM khác.

### Kiểm chứng độc lập bằng công cụ `jfr`

Sau khi chạy `capture`:

```bash
jfr summary sample.jfr
jfr print --events demo.WorkStep sample.jfr
jfr print --json --events demo.WorkStep sample.jfr
jfr metadata sample.jfr
```

Trong môi trường kiểm chứng:

- `jfr summary` liệt kê `demo.WorkStep` với **count 3**.
- `jfr print --events demo.WorkStep` in các field `phase` bằng `parse`/`compute`/`write` và `items` bằng `10`/`20`/`30`.
- `jfr print --json --events demo.WorkStep` tạo JSON có tên event `demo.WorkStep`.
- Các số như file size, chunk count, timestamp, duration và cấu trúc JSON chi tiết do runtime/phiên bản `jfr` quyết định, nên ví dụ không khóa cứng vào một giá trị.

### Mở chính file này bằng JMC

Trong JMC đã cài tương thích, chọn chức năng mở file và trỏ tới `sample.jfr`. Tìm **Event Browser**, chọn sự kiện `demo.WorkStep` / category `Demo / Workflow` rồi xem ba records với `phase` và `items`. Đừng tìm một đồ thị GC đặc biệt cho `WorkStep`: đây là **custom event** và không được JMC biết trước như một GC/JVM built-in event; việc hiển thị phụ thuộc cách JMC trình bày event custom.

## 9. Khi phân tích bản ghi thật: kiểm tra dữ liệu có đủ chưa

Không phải recording nào cũng chứa mọi thông tin mong muốn. Bộ cấu hình JFR quyết định những gì được ghi:

- **`settings=default`** thường phù hợp cho ghi có overhead thấp và thời gian dài hơn; những loại event chi tiết có thể không được bật.
- **`settings=profile`** thường bật thêm dữ liệu phục vụ phân tích theo profile; có thể tăng overhead và lượng dữ liệu, cần kiểm tra runtime.
- **Threshold** có thể lọc bỏ duration events rất ngắn. Không thấy event không đồng nghĩa hành động không xảy ra.
- **Sampling/period** làm events được ghi theo mẫu hoặc chu kỳ; số lần ghi trong `.jfr` không nhất thiết bằng số lần function được gọi.
- **Stack traces** có thể bị tắt vì chi phí. `getStackTrace() == null` không tự chứng minh một event “không có call stack”.
- **Recording window** có thể không bao trùm lúc lỗi xảy ra, hoặc data bị giới hạn `maxage`/`maxsize`/chunk retention.
- **Custom event** chỉ có khi code/instrumentation thực sự tạo event và recording bật đúng event type.

**Ví dụ quan trọng:** nếu `jdk.JavaMonitorEnter` không xuất hiện trong summary, có thể do không có contention **hoặc** event bị tắt/threshold chưa đạt. Không thể lập luận “ứng dụng không hề chờ lock” chỉ dựa vào count 0 khi chưa kiểm tra settings và thời gian chụp.

Khi so sánh hai recordings, cần chuẩn hóa:

- Cùng hoặc tương đương workload, throughput và môi trường;
- Cùng time window/duration thu thập;
- Tương đương JDK/GC/OS/CPU và recording settings;
- Cùng cách tính duration/count, chú ý sampling và event loss/dropped data nếu có;
- Có giải thích thay đổi trong JFR event metadata giữa các JDK/provider.

## 10. Timestamp, thời lượng, biểu đồ và ý nghĩa số liệu

Một bản ghi JFR không phải một dãy “CPU usage per method” mặc định. Nó là tập các **event types** với các trường riêng và cơ chế thu thập khác nhau.

| Dữ liệu | Diễn giải đúng | Sai lầm thường gặp |
| --- | --- | --- |
| `getStartTime()` → `Instant` | Thời điểm bắt đầu event. | Coi nó là duration hoặc số mili giây từ start của process. |
| `getEndTime()` → `Instant` | Thời điểm kết thúc event. | Bỏ qua múi giờ khi đối chiếu hệ thống khác. |
| `getDuration()` → `Duration` | Khoảng thời gian của event. | Coi mọi duration là **CPU time** của thread. |
| `getThread()` | Thread metadata nếu có. | Mặc định mọi event luôn có thread. |
| `getStackTrace()` | Stack trace nếu được ghi. | Null nghĩa là “không có stack trace trong JVM”. |
| Event count | Số events được ghi của type đó. | Số lần method thực sự được gọi, kể cả khi sampling/threshold. |
| Event payload bytes | Trường dữ liệu do event type định nghĩa, nếu có. | Đánh đồng size của event trong file với size của object/file/network. |
| JMC warning/score | Gợi ý cần điều tra. | Kết luận nhân-quả hoặc mức ưu tiên khẩn cấp chắc chắn. |

**Chuyển đơn vị có kiểm soát:**

```java
long millis = event.getDuration().toMillis();
long nanos = event.getDuration().toNanos();
```

Snippet này nằm trong code có `RecordedEvent event`. Khi duration không chia hết cho đơn vị, `toMillis()` có thể bỏ phần lẻ; với thống kê latency nhỏ nên dùng độ phân giải phù hợp. Khi ghép events từ nhiều host, phải xem đồng hồ hệ thống, UTC/timezone và khả năng clock skew.

Không được cộng duration của hai event xảy ra **song song** rồi xem đó là elapsed time của toàn hệ thống. Muốn tìm critical path, cần tương quan bằng trace ID, request ID hoặc timestamps/threads/causal context một cách thận trọng.

## 11. Lấy bản ghi từ chương trình đang chạy để đọc

Mục tiêu bài học là **đọc**, nhưng để có đầu vào thật, người học cần biết một workflow ghi phổ biến. Java 11 hỗ trợ công cụ `jcmd` và JFR commands để làm việc với JVM local khi có quyền thích hợp.

Ví dụ **minh họa trong môi trường test được ủy quyền**:

```bash
jcmd -l
jcmd 12345 JFR.start name=diagnostic settings=profile
jcmd 12345 JFR.dump name=diagnostic filename=diagnostic.jfr
jcmd 12345 JFR.stop name=diagnostic
jfr summary diagnostic.jfr
```

**`12345` là PID ví dụ**, phải thay bằng PID của JVM bạn được phép kiểm tra; không tự chạy lên một process người khác sở hữu. Lệnh `JFR.dump` tạo một snapshot/dump theo recording được chọn, còn `JFR.stop` ngừng recording đó. Tên output và vị trí lưu phải kiểm tra theo quyền file của **JVM đích** và đặc tính của `jcmd` đang dùng.

Với một Java program độc lập, cũng có thể khởi động recording ngay từ command line bằng option JFR của `java` trên JDK hỗ trợ:

```bash
java -XX:StartFlightRecording=filename=sample.jfr,duration=30s,settings=profile MyApp
```

`MyApp` là **tên lớp ví dụ của chương trình cần chạy**, không phải một lớp định nghĩa trong bài này; muốn chạy lệnh phải thay bằng entrypoint và classpath hợp lệ của chính ứng dụng. Với production, đừng bật `profile`, stack traces hay kích thước recording lớn mà không đánh giá overhead, CPU, storage, quyền truy cập và thời hạn lưu.

Không cần những cờ thương mại hóa JFR của các hướng dẫn JDK 8 cũ cho workflow Java 11 này. Đặc biệt, không sao chép các chỉ dẫn Java 8 đã lỗi thời chỉ vì gặp trong một blog cũ. Từ Java 11, nên dựa vào tài liệu/hỗ trợ chính thức của JDK được triển khai.

### Lưu file trước khi chia sẻ hoặc chuyển máy

- Xác nhận command đã tạo file hoàn chỉnh, không phải đang copy một file bị ghi dở hoặc cắt mất chunks.
- Dùng nơi lưu có quyền truy cập thích hợp, quota và retention. File có thể chứa **metadata nhạy cảm**.
- Khi chuyển qua mạng, dùng kênh đã xác thực/mã hóa, tránh đính kèm lên issue tracker công khai.
- Ghi kèm JDK/vendor/runtime version, thời gian ghi, settings và thông tin workload đã **loại bỏ bí mật**; điều này quan trọng khi so sánh giữa máy ghi và máy phân tích.
- Kiểm tra file bằng `jfr summary` trên máy đọc trước khi đưa vào pipeline xử lý lớn.

## 12. Xử lý lỗi tương thích và lỗi bản ghi

| Triệu chứng | Nguyên nhân có thể | Cách xử lý có kiểm chứng |
| --- | --- | --- |
| `jfr` không được nhận diện | Chưa cài JDK phù hợp hoặc `PATH` chỉ có JRE/tool thiếu. | Kiểm tra cài đặt JDK, đường dẫn `bin`, `jfr help`. |
| JMC không có trong JDK | JMC là ứng dụng riêng; không tự có trong JDK. | Cài bản JMC được hỗ trợ từ nguồn chính thức. |
| CLI/JMC không mở được file | File hỏng/truncated, thiếu quyền, file version không hỗ trợ hoặc không phải JFR. | Kiểm tra nguồn, size, `jfr summary` bằng tool phù hợp, đối chiếu version. |
| `jfr summary` không liệt kê event mong đợi | Event không được bật, chưa commit, threshold, sampling/time window hoặc tên type khác. | Xem settings, metadata, event name, recording time. |
| `jfr print --events` trả không có event | Bộ lọc sai tên, file không có type đó hoặc type count=0. | Dùng `jfr summary`/`jfr metadata` để lấy tên chính xác. |
| `getInt("items")` ném exception | Không đúng type hoặc field không tồn tại/khác kiểu. | `hasField` rồi kiểm tra `EventType.getFields()`/schema. |
| `getStackTrace() == null` | Không bật stack trace hoặc event không chứa stack. | Xem event settings, không suy luận “không có stack”. |
| `RecordingFile.readAllEvents` gây tốn RAM | Đã nạp toàn bộ events vào một list. | Chuyển sang `RecordingFile` streaming loop. |
| Timestamp trong GUI lệch log ứng dụng | Timezone, định dạng display, clock skew hoặc thời gian ghi khác. | Chuẩn hóa thời gian, đối chiếu UTC và nguồn. |
| Reader mới nhìn thấy field khác reader cũ | Event schema/provider/JDK thay đổi hoặc UI cũ không render đầy đủ. | Dùng metadata thật, cập nhật reader/tool có hỗ trợ, test version pair. |
| Sự kiện không có duration hữu ích | Instant events, threshold hoặc thời gian quá ngắn. | Đọc event semantics, dùng độ phân giải đúng. |
| Báo “không có bottleneck” chỉ vì GUI không cảnh báo | Automated Analysis không đủ điều kiện phát hiện hoặc settings thiếu dữ liệu. | Điều tra theo timeline, event types, workload và counter khác. |

### Không dùng API của JDK mới rồi nhận là Java 11

Ở những JDK mới hơn có các khả năng bổ sung cho `jfr` và `RecordingFile`. Ví dụ API `RecordingFile.write(Path, Predicate<RecordedEvent>)` chỉ được giới thiệu ở **Java 19**, không có trong API Java 11. Nếu code cần biên dịch với `javac --release 11`, không dùng API bổ sung đó.

Tương tự, `jdk.jfr.consumer.RecordingStream` phục vụ consumption từ live recording và có API/availability phụ thuộc JDK; bài này **chỉ dùng `RecordingFile` để đọc tệp đã lưu** nhằm tương thích Java 11. Đừng nhầm “đọc file offline” với “subscribe event stream realtime”. Với tính năng mới, kiểm tra `@since` trong Javadoc đúng target JDK.

## 13. Bảo mật và quyền riêng tư khi phân tích JFR

Theo Javadoc Java 11, `RecordingFile` **chỉ nên đọc bản ghi từ nguồn đáng tin cậy**. Đây là một chỉ dẫn có ý nghĩa: parser nhận tệp nhị phân chứa cấu trúc metadata phức tạp, có thể cần nhiều CPU/RAM và chịu lỗi nếu file bị tạo ác ý hoặc bị hỏng.

Các nguyên tắc:

1. **Nguồn tin cậy:** chỉ mở file do hệ thống/nhóm được phép cung cấp. Nếu phải nhận file từ bên ngoài, xử lý trong môi trường cô lập, cập nhật JDK/JMC và giới hạn tài nguyên.
2. **Giới hạn dung lượng:** thiết lập quota upload, không chạy `readAllEvents` trên file lớn, kiểm tra quyền đọc và nơi lưu.
3. **Bảo vệ nội dung:** bản ghi có thể chứa path, tên máy, tên thread, command line, stack frame, dữ liệu JVM và **custom event fields** do ứng dụng tự định nghĩa. Không tự động đăng nguyên bản file lên issue, chat công khai hoặc dịch vụ phân tích không được phê duyệt.
4. **Chia sẻ có kiểm soát:** khi cần gửi cho người hỗ trợ, ưu tiên xác định scope, ẩn/xóa dữ liệu không cần, kênh an toàn và retention rõ. Không giả định một lệnh lọc output JSON đã “ẩn danh” toàn bộ thông tin còn lại.
5. **Không in secret qua custom events:** tránh ghi password, access token, cookie, PII hoặc giá trị object tùy ý vào event payload.
6. **Phân quyền vận hành:** `jcmd` dùng cho JVM cần có quyền; không chạy JFR commands vào tiến trình không được ủy quyền.
7. **Điều tra có thể tái hiện:** lưu bối cảnh version/settings/diagnostic window nhưng loại bỏ dữ liệu bí mật khỏi báo cáo.
8. **Đừng đánh giá thấp overhead:** JFR thường có overhead thấp, nhưng việc bật nhiều events, stack traces hoặc duration threshold bằng 0 cho mọi sự kiện ở tải cao vẫn có chi phí. Đo trong môi trường thực tế.

## 14. Một workflow phân tích end-to-end phù hợp Java 11+

```text
Ứng dụng/JVM (JDK 11 hoặc mới hơn)
               |
               | Recording hoặc jcmd / -XX:StartFlightRecording
               v
       Tệp nhị phân .jfr
               |
               | Bảo vệ nguồn, copy hoàn chỉnh, ghi version/settings
               v
   jfr summary + jfr metadata
               |
         +-----+-------+
         |             |
         v             v
     jfr print      JDK Mission Control
  --events / --json   Timeline, Event Browser,
         |            Automated Analysis, GC/CPU/Threads
         +-------------+
               |
               v
   jdk.jfr.consumer.RecordingFile
   hasMoreEvents/readEvent
               |
               v
     Lọc event type/fields
     chuẩn hóa timestamp/duration
     tính tổng hợp và đối chiếu workload
               |
               v
     Kết luận có bằng chứng
     + giới hạn dữ liệu/phiên bản
```

Trước khi kết luận về sự cố, kiểm tra ba câu hỏi: **(1) Có ghi đúng sự kiện không? (2) Công cụ đọc có hiểu đúng file/field không? (3) Chỉ số có thật sự chứng minh điều được kết luận không?**

### Checklist thực hành

1. Biết rõ tệp cần đọc là **`.jfr`**, không phải `.jfc`.
2. Xác định JDK đã tạo file, JDK/tool `jfr` đang đọc và bản **JMC** đã cài.
3. Thử **`jfr summary`** để nắm thời gian, event counts và kích thước.
4. Dùng **`jfr metadata`** để biết event schema/type; không đoán field.
5. Dùng **`jfr print --events`** cho dữ liệu cần điều tra và **`--json`** khi cần xuất máy đọc được.
6. Mở cùng recording trong **JMC** để quan sát timeline, threads, CPU/GC/I/O/locks và custom events.
7. Khi viết Java, dùng **`jdk.jfr.consumer.RecordingFile`**, `hasMoreEvents/readEvent` và `RecordedEvent`; tránh `readAllEvents` trên file lớn.
8. Dựa vào **`getEventType().getName()`, `hasField` và metadata** để không bị lỗi khi schema/version thay đổi.
9. Phân biệt timestamp, duration, sampled counts và CPU time; không kết luận từ một count thiếu bối cảnh.
10. Đọc event settings và time window, nhất là khi **không thấy sự kiện mong đợi**.
11. Kiểm soát file size, retention và dữ liệu nhạy cảm; chỉ mở file từ nguồn tin cậy.
12. Chạy các lệnh `javac --release 11` và `jfr` trên môi trường được phép; ghi rõ nếu dùng JDK mới hơn để phân tích một file cũ.
13. Không dùng API/subcommand chỉ xuất hiện ở JDK mới rồi trình bày như tính năng bắt buộc của Java 11.
14. Khi báo cáo, nêu **event type, khoảng thời gian, filter, settings, số liệu, giới hạn của kết luận và phiên bản công cụ**.

### Tài liệu chính thức, còn phù hợp hiện nay

- [Oracle Java SE 11 — `jdk.jfr.consumer.RecordingFile` và cách đọc bản ghi](https://docs.oracle.com/en/java/javase/11/docs/api/jdk.jfr/jdk/jfr/consumer/RecordingFile.html)
- [Oracle Java SE 11 — `RecordedEvent`, timestamp, duration, thread, stack trace](https://docs.oracle.com/en/java/javase/11/docs/api/jdk.jfr/jdk/jfr/consumer/RecordedEvent.html)
- [Oracle Java SE 11 — `RecordedObject`, `hasField`, `getInt`, `getString` và type safety](https://docs.oracle.com/en/java/javase/11/docs/api/jdk.jfr/jdk/jfr/consumer/RecordedObject.html)
- [Oracle Java SE 11 — `jdk.jfr.Recording`, enable/start/stop/dump](https://docs.oracle.com/en/java/javase/11/docs/api/jdk.jfr/jdk/jfr/Recording.html)
- [Oracle Java SE 11 — module `jdk.jfr`](https://docs.oracle.com/en/java/javase/11/docs/api/jdk.jfr/module-summary.html)
- [Oracle Java SE 11 — công cụ chẩn đoán JFR và `jcmd`](https://docs.oracle.com/en/java/javase/11/troubleshoot/diagnostic-tools.html)
- [OpenJDK JEP 328 — Flight Recorder (JDK 11)](https://openjdk.org/jeps/328)
- [Oracle — JDK Mission Control User Guide, đọc và phân tích Flight Recorder](https://docs.oracle.com/en/java/java-components/jdk-mission-control/9/user-guide/using-jdk-flight-recorder.html)
- [Oracle — JDK Mission Control overview và cài đặt riêng](https://docs.oracle.com/en/java/java-components/jdk-mission-control/9/user-guide/jdk-mission-control.html)
- [Oracle Java SE 25 — `jfr` command reference để đối chiếu các subcommand hiện đại](https://docs.oracle.com/en/java/javase/25/docs/specs/man/jfr.html)
