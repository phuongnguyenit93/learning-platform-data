# Tổng hợp số liệu theo khoảng thời gian và loại sự kiện trong JFR

> **Ngữ cảnh:** **Java 14 → Xử lý sự kiện JFR**. Bài tập trung vào việc biến các `jdk.jfr.consumer.RecordedEvent` thành bảng thống kê **theo cửa sổ thời gian (time window)** và **tên loại sự kiện (event type)**. Những API JFR trong bài vẫn được dùng trong Java hiện hành; ví dụ chạy với **Java 17+**, không sử dụng tính năng preview hay quy trình legacy. Cần phân biệt **thời điểm event xảy ra**, **thời điểm event được nhận** và **thời điểm hoàn tất một cửa sổ thống kê**.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Đọc `RecordedEvent.getEventType().getName()`, `getStartTime()`, `getEndTime()` và `getDuration()`, rồi xác định trường phù hợp để phân nhóm.
2. Tạo khóa tổng hợp **(windowStart, eventType)**, đếm số lượng, tính tổng, trung bình, giá trị lớn nhất hoặc các số đo bổ sung theo từng loại event.
3. Giải thích cửa sổ cố định **tumbling window** với khoảng nửa mở `[start, end)` và phân biệt với **sliding window**.
4. Chọn **event time** thay vì nhầm với **processing time** khi thống kê lịch sử.
5. Tạo bucket theo UTC bằng `Instant.truncatedTo(ChronoUnit.MINUTES)` cho cửa sổ 1 phút và bằng `Math.floorDiv` cho cửa sổ có kích thước tùy chọn.
6. Xử lý sự kiện tới trễ hoặc **out of order** giữa các batch JFR; hiểu vì sao `onFlush` **không tự động đóng** một cửa sổ tính theo đồng hồ.
7. Dùng `RecordingFile` để tổng hợp offline từ `.jfr`, hoặc `EventStream` / `RecordingStream` để cập nhật số liệu khi JVM đang chạy.
8. Tránh những sai lầm về `threshold`, retention, event duration, số liệu p95/p99, thiếu event, concurrency và phát hành kết quả trùng lặp.
9. Chạy các chương trình Java 17+ và phân biệt ví dụ có stdout xác định với ví dụ có timestamp phụ thuộc môi trường.

**Ý chính:** Mỗi event được chuyển thành **một đóng góp có timestamp + loại sự kiện + metric**. Bộ tổng hợp gán đóng góp ấy vào **cửa sổ thời gian** và **nhóm loại sự kiện**, sau đó cập nhật số liệu. JFR đưa dữ liệu tới consumer theo batch, nhưng **batch của JFR không phải cửa sổ một phút của bạn**.

## 2. Nguồn dữ liệu: từ `Event` tới `RecordedEvent`

Một event được phát sinh trong JVM, nếu đã enable và thỏa điều kiện recording, sẽ được JFR ghi lại. Code ứng dụng có thể khai báo:

```java
import jdk.jfr.Event;
import jdk.jfr.Name;

@Name("demo.RequestFinished")
class RequestFinished extends Event {
    public int statusCode;
}
```

Producer có thể tạo, đo thời gian và commit:

```java
RequestFinished e = new RequestFinished();
e.statusCode = 200;
e.begin();

// Công việc thực tế của ứng dụng diễn ra tại đây.

e.end();
e.commit();
```

Hai khối trên là **mã minh họa**, không phải một file có `main`. Phía consumer nhận đối tượng **`RecordedEvent`**, không phải cùng instance `RequestFinished`:

```java
// Trong callback onEvent hoặc vòng đọc RecordingFile:
String type = recorded.getEventType().getName();
java.time.Instant end = recorded.getEndTime();
java.time.Duration duration = recorded.getDuration();
```

Các giá trị trong `RecordedEvent`:

| API | Trả về | Nên dùng khi |
| --- | --- | --- |
| `getEventType().getName()` | Tên loại JFR event, ví dụ `jdk.GarbageCollection` hoặc `demo.RequestFinished` | Nhóm theo **loại sự kiện**. |
| `getStartTime()` | `Instant` | Cần biết sự kiện bắt đầu lúc nào. |
| `getEndTime()` | `Instant` | Muốn gán event vào cửa sổ theo **thời điểm kết thúc**. |
| `getDuration()` | `Duration` | Đo thời lượng event, trung bình thời lượng, max duration. |
| `getInt("statusCode")` hoặc getter tương ứng | Trường cụ thể của event type | Phân nhóm thêm theo status, số byte, định danh kỹ thuật... nếu schema có. |
| `getEventType().getName()` so với prefix | String | Lọc đúng namespace event, tránh trộn events hệ thống khác. |

**Chú ý:** Không phải mọi event đo một khoảng thời gian có ý nghĩa. Với **instant events**, `getStartTime()` và `getEndTime()` bằng nhau, thời lượng bằng zero theo hợp đồng của `RecordedEvent`. Vì thế, việc tính trung bình `getDuration()` chỉ có ích cho những loại event thực sự biểu diễn duration. Đừng gom `jdk.CPULoad` và `jdk.FileRead` vào cùng một phép tính «thời lượng trung bình» mà chưa hiểu schema.

### 2.1. Chọn trường thời gian và điều kiện lọc

Với bài toán «số request hoàn tất trong mỗi phút», chọn **`getEndTime()`** là phù hợp. Với bài toán «số request bắt đầu trong mỗi phút», chọn **`getStartTime()`**. Với bài toán «thời gian GC tạm dừng chồng lên mỗi phút», cần xử lý **đoạn thời gian [start, end)** và phân bổ phần giao của nó với từng cửa sổ, thay vì đơn giản đếm một lần theo `endTime`.

Nếu một event kéo dài từ 10:00:58 tới 10:01:03, cách nhóm theo **end time** chỉ đặt event vào cửa sổ 10:01. Điều này đúng cho **đếm số sự kiện kết thúc**, nhưng không đủ để khẳng định toàn bộ 5 giây xử lý diễn ra trong phút 10:01.

## 3. Định nghĩa chính xác «cửa sổ thời gian»

### 3.1. Tumbling window: những khoảng cố định không chồng lấp

Ví dụ chia mỗi phút theo UTC:

```text
[10:00:00, 10:01:00)
[10:01:00, 10:02:00)
[10:02:00, 10:03:00)
```

Ký hiệu `[start, end)` nghĩa là **bao gồm thời điểm start, không bao gồm thời điểm end**. Vì thế:

| Timestamp event | Thuộc cửa sổ 1 phút |
| --- | --- |
| `10:00:00.000Z` | 10:00 |
| `10:00:59.999Z` | 10:00 |
| `10:01:00.000Z` | **10:01** |
| `10:01:59.999Z` | 10:01 |

Một timestamp chỉ thuộc **một** tumbling window với cùng time zone, time origin và độ rộng.

Dùng `Instant` trong Java:

```java
import java.time.Instant;
import java.time.temporal.ChronoUnit;

Instant eventEnd = Instant.parse("2026-11-07T10:00:59.999Z");
Instant start = eventEnd.truncatedTo(ChronoUnit.MINUTES);
// start = 2026-11-07T10:00:00Z
```

Đây là đoạn lệnh minh họa trong một phương thức, không phải chương trình độc lập.

**Vì sao dùng UTC?** `Instant` là thời điểm tuyệt đối. Bucket một phút tính theo `Instant` không bị ảnh hưởng bởi timezone của máy, múi giờ người xem hoặc thay đổi giờ mùa hè. Khi hiển thị báo cáo theo thời gian địa phương, hãy chuyển **nhãn của cửa sổ** sau khi đã xác định rõ quy tắc nhóm dữ liệu; nếu nghiệp vụ đòi các ranh giới theo lịch địa phương, phải định nghĩa riêng theo `ZoneId`, không giả định bucket UTC luôn phù hợp.

### 3.2. Khóa nhóm là cặp (windowStart, eventType)

Giả sử có các event:

```text
10:00:02Z  demo.DB        12 ms
10:00:20Z  demo.HTTP      40 ms
10:00:59Z  demo.HTTP      20 ms
10:01:00Z  demo.HTTP      60 ms
10:01:15Z  demo.DB         8 ms
10:01:40Z  demo.HTTP      80 ms
```

Ta cần **bốn nhóm**:

| Window (UTC) | Event type | Count | Total duration | Average | Max |
| --- | --- | ---: | ---: | ---: | ---: |
| 10:00 | `demo.DB` | 1 | 12 ms | 12 ms | 12 ms |
| 10:00 | `demo.HTTP` | 2 | 60 ms | 30 ms | 40 ms |
| 10:01 | `demo.DB` | 1 | 8 ms | 8 ms | 8 ms |
| 10:01 | `demo.HTTP` | 2 | 140 ms | 70 ms | 80 ms |

Không gộp `demo.DB` với `demo.HTTP` chỉ vì chúng có cùng phút; mỗi loại có ý nghĩa riêng. Tương tự, không gộp mọi event `demo.HTTP` vào một tổng toàn cục khi bạn cần xu hướng theo thời gian.

Đối với một khoảng `W` giây, **rate** có thể tính bằng `count / W`, ví dụ 120 event trong 60 giây → 2 events/s trung bình cửa sổ. Đây là **rate trung bình**, không chứng minh event xuất hiện đều trong mọi giây của phút đó.

### 3.3. Sliding window: các khoảng chồng lấp

Một **sliding window** có chiều dài 60 giây và bước nhảy 10 giây:

```text
[10:00:00, 10:01:00)
[10:00:10, 10:01:10)
[10:00:20, 10:01:20)
...
```

Một event có thể đóng góp vào **nhiều** sliding windows. Đây là một lựa chọn hợp lý khi dashboard cần đường xu hướng mượt hoặc cảnh báo «60 giây gần nhất», nhưng **không** dùng thuật toán bucket một lần của tumbling window rồi gọi là sliding window.

**Chọn tumbling windows** khi cần các hàng báo cáo không chồng lấp, dễ cộng tổng theo ngày. **Chọn sliding windows** khi cần đánh giá cửa sổ trượt với bước cập nhật dày hơn. Nếu thêm sliding windows, phải nêu rõ kích thước cửa sổ, bước nhảy và cách xử lý event trễ.

## 4. Thuật toán tổng hợp căn bản

Với mỗi `RecordedEvent` hợp lệ, thao tác khái niệm:

```text
1. type      = event.getEventType().getName()
2. end       = event.getEndTime()
3. start     = floorToWindow(end, width)
4. key       = (start, type)
5. stats     = map.computeIfAbsent(key, new Stats())
6. stats.n++
7. stats.totalDuration += event.getDuration()
8. stats.maxDuration = max(stats.maxDuration, event.getDuration())
```

**Bộ nhớ tỉ lệ với số nhóm đang giữ**, không nhất thiết tỉ lệ với số event: `O(number_of_active_windows × number_of_types)`. Nhưng nếu không xóa các cửa sổ đã chốt, map vẫn tăng vô hạn theo thời gian. Streaming cần chính sách **eviction/retention** cho các nhóm cũ.

### 4.1. Nên lưu gì trong `Stats`?

Một `Stats` tối thiểu:

- `count`: số event đã được consumer nhận và tính vào nhóm.
- `totalDuration`: tổng thời lượng (nếu metric có ý nghĩa).
- `maxDuration`: duration lớn nhất.
- `minDuration` hoặc tổng giá trị trường số nếu có nhu cầu.
- Bộ đếm lỗi/thành công cho một event type có trường trạng thái rõ ràng.
- Histogram hoặc cấu trúc quantile nếu cần p95/p99; **không thể suy p95 chỉ từ count + sum + max**.

**Cẩn thận khi tính trung bình:** `avg = sum / count`. Khi `count == 0`, không chia; với tổng thời lượng tính bằng `Duration`, hãy chọn đơn vị/độ chính xác rõ ràng. `Duration.toMillis()` **làm tròn xuống đến mili-giây** (với thời lượng không âm), có thể làm mất thông tin của event microsecond. Với đo thời gian rất ngắn, dùng `toNanos()` hoặc đơn vị nhỏ hơn phù hợp, đồng thời xử lý khả năng tràn số khi tổng quá lớn.

### 4.2. Những dimension nào được phép nhóm thêm?

Ngoài event type, có thể nhóm theo:

- `statusCode` của một custom request event;
- Tên thao tác **được chuẩn hóa**, ví dụ `"GET /orders/:id"` thay vì URL chứa ID thật;
- Tên stage như `"deserialize"`/`"db-query"`;
- Thông tin về thread nếu cần phân tích có kiểm soát.

**Không đưa ID duy nhất của từng request vào key** nếu mục tiêu là aggregate: cardinality sẽ bùng nổ, mỗi nhóm gần như chỉ có một event. Cũng không để lọt token, email hoặc nội dung người dùng vào metric labels. Chọn dimension hữu hạn và không chứa dữ liệu nhạy cảm.

## 5. Ví dụ Java 17+ có output xác định: tổng hợp dữ liệu mẫu

Chương trình đầu tiên dùng dữ liệu mẫu **có timestamp cố định**, nhờ đó có thể kiểm tra thuật toán và stdout **mà không phụ thuộc thời gian JVM thật**. Dù chưa đọc file `.jfr`, cùng mô hình `Sample` bên dưới sẽ được dùng khi chuyển `RecordedEvent` sang dữ liệu tổng hợp.

Lưu file **`WindowAggregationDemo.java`**:

```java
import java.time.Duration;
import java.time.Instant;
import java.time.temporal.ChronoUnit;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

public class WindowAggregationDemo {
    record Sample(Instant endTime, String type, Duration duration) {}
    record Key(Instant windowStart, String eventType) {}

    static final class Stats {
        long count;
        long totalMillis;
        long maxMillis;

        void add(Duration duration) {
            long millis = duration.toMillis();
            count++;
            totalMillis += millis;
            maxMillis = Math.max(maxMillis, millis);
        }
    }

    static void aggregate(Map<Key, Stats> groups, Sample sample) {
        Instant start = sample.endTime()
                .truncatedTo(ChronoUnit.MINUTES);
        Key key = new Key(start, sample.type());
        groups.computeIfAbsent(key, k -> new Stats())
                .add(sample.duration());
    }

    public static void main(String[] args) {
        List<Sample> samples = List.of(
            new Sample(Instant.parse("2026-11-07T10:00:02Z"),
                    "demo.DB", Duration.ofMillis(12)),
            new Sample(Instant.parse("2026-11-07T10:00:20Z"),
                    "demo.HTTP", Duration.ofMillis(40)),
            new Sample(Instant.parse("2026-11-07T10:00:59.999Z"),
                    "demo.HTTP", Duration.ofMillis(20)),
            new Sample(Instant.parse("2026-11-07T10:01:00Z"),
                    "demo.HTTP", Duration.ofMillis(60)),
            new Sample(Instant.parse("2026-11-07T10:01:15Z"),
                    "demo.DB", Duration.ofMillis(8)),
            new Sample(Instant.parse("2026-11-07T10:01:40Z"),
                    "demo.HTTP", Duration.ofMillis(80))
        );

        Map<Key, Stats> groups = new HashMap<>();
        for (Sample sample : samples) {
            aggregate(groups, sample);
        }

        List<Map.Entry<Key, Stats>> rows =
                new ArrayList<>(groups.entrySet());
        rows.sort((a, b) -> {
            int time = a.getKey().windowStart()
                    .compareTo(b.getKey().windowStart());
            return time != 0 ? time
                    : a.getKey().eventType()
                            .compareTo(b.getKey().eventType());
        });

        for (Map.Entry<Key, Stats> row : rows) {
            Key key = row.getKey();
            Stats stats = row.getValue();

            System.out.println(key.windowStart()
                    + " " + key.eventType()
                    + " count=" + stats.count
                    + " totalMs=" + stats.totalMillis
                    + " maxMs=" + stats.maxMillis);
        }
        System.out.println("groups=" + groups.size());
        System.out.println("events=" + samples.size());
    }
}
```

Biên dịch và chạy:

```bash
javac --release 17 WindowAggregationDemo.java
java WindowAggregationDemo
```

**Stdout chính xác:**

```text
2026-11-07T10:00:00Z demo.DB count=1 totalMs=12 maxMs=12
2026-11-07T10:00:00Z demo.HTTP count=2 totalMs=60 maxMs=40
2026-11-07T10:01:00Z demo.DB count=1 totalMs=8 maxMs=8
2026-11-07T10:01:00Z demo.HTTP count=2 totalMs=140 maxMs=80
groups=4
events=6
```

**Giải thích code:**

1. `Sample` đại diện ba trường cần thống kê: thời gian kết thúc, loại event, thời lượng.
2. `Key` là Java record nên `equals/hashCode` được compiler sinh theo các component, phù hợp làm khóa `HashMap` vì `Instant` và `String` bất biến.
3. `truncatedTo(ChronoUnit.MINUTES)` đặt sự kiện vào phút UTC tương ứng. Timestamp `10:00:59.999` vẫn thuộc 10:00; `10:01:00.000` thuộc 10:01.
4. `computeIfAbsent` tạo một `Stats` riêng cho mỗi cặp (phút, loại), rồi cập nhật các trường thống kê.
5. `Map` không bảo đảm thứ tự duyệt, vì vậy ta sắp xếp `rows` theo `windowStart` và `eventType` trước khi in.
6. Mã dùng `Duration.toMillis()` vì dữ liệu demo đều có số mili-giây nguyên; trong hệ thống thực, cân nhắc giữ nanosecond hoặc phân phối histogram phù hợp.
7. `groups=4` khác `events=6` vì hai HTTP events trong cùng phút được gộp thành một hàng.

**QA quan trọng:** Ví dụ **không lấy đồng hồ hiện tại**, không dùng random và không gọi JFR streaming bất đồng bộ, nên stdout nêu trên là kết quả cố định khi biên dịch đúng và chạy trên Java 17+.

## 6. Đọc JFR thật và tổng hợp theo cửa sổ

Giờ áp dụng ý tưởng cho các `RecordedEvent` lấy từ file `.jfr`. Những API cần sử dụng:

```java
import jdk.jfr.consumer.RecordedEvent;
import jdk.jfr.consumer.RecordingFile;

// Đoạn lệnh minh họa trong phương thức throws Exception:
try (RecordingFile file = new RecordingFile(path)) {
    while (file.hasMoreEvents()) {
        RecordedEvent event = file.readEvent();
        String type = event.getEventType().getName();
        java.time.Instant time = event.getEndTime();
        java.time.Duration duration = event.getDuration();

        // Dùng time/type/duration để cập nhật các nhóm.
    }
}
```

**Ưu điểm:** Duyệt file lần lượt, không cần tải mọi event vào một `List` khổng lồ. `RecordingFile.readAllEvents(path)` vẫn hữu ích cho file nhỏ và test, nhưng Javadoc không khuyến nghị dùng cho file rất lớn.

### 6.1. Chương trình hoàn chỉnh tự ghi file và tổng hợp

Chương trình sau tự tạo hai loại custom JFR events, ghi một recording ngắn, dump ra file, đọc từng event rồi tổng hợp bằng khóa **(phút, type)**. Vì thời gian phát sinh event thật phụ thuộc lúc chạy, **số nhóm theo phút không cố định** (các event có thể nằm hai bên ranh giới phút). Tuy nhiên **tổng số event từng loại** được tạo trong recording mẫu là xác định khi môi trường JFR hoạt động đúng.

Lưu file **`JfrWindowFileDemo.java`**:

```java
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Instant;
import java.time.temporal.ChronoUnit;
import java.util.HashMap;
import java.util.Map;

import jdk.jfr.Event;
import jdk.jfr.Name;
import jdk.jfr.Recording;
import jdk.jfr.consumer.RecordedEvent;
import jdk.jfr.consumer.RecordingFile;

public class JfrWindowFileDemo {
    private static final String REQ = "demo.AggregateRequest";
    private static final String JOB = "demo.AggregateJob";

    @Name(REQ)
    public static class Request extends Event {
        public int id;
    }

    @Name(JOB)
    public static class Job extends Event {
        public int id;
    }

    record Key(Instant minute, String eventType) {}

    static void emitRequest(int id) {
        Request e = new Request();
        e.id = id;
        e.commit();
    }

    static void emitJob(int id) {
        Job e = new Job();
        e.id = id;
        e.commit();
    }

    public static void main(String[] args) throws Exception {
        Path path = Files.createTempFile("jfr-window-", ".jfr");

        try {
            try (Recording recording = new Recording()) {
                recording.setToDisk(true);
                recording.enable(Request.class).withoutThreshold();
                recording.enable(Job.class).withoutThreshold();

                recording.start();
                emitRequest(1);
                emitRequest(2);
                emitJob(1);
                emitRequest(3);
                emitJob(2);
                recording.stop();
                recording.dump(path);
            }

            Map<Key, Long> groups = new HashMap<>();
            long requestCount = 0;
            long jobCount = 0;

            try (RecordingFile file = new RecordingFile(path)) {
                while (file.hasMoreEvents()) {
                    RecordedEvent e = file.readEvent();
                    String type = e.getEventType().getName();
                    if (!type.equals(REQ) && !type.equals(JOB)) {
                        continue;
                    }

                    Instant minute = e.getEndTime()
                            .truncatedTo(ChronoUnit.MINUTES);
                    groups.merge(new Key(minute, type), 1L, Long::sum);

                    if (type.equals(REQ)) {
                        requestCount++;
                    } else {
                        jobCount++;
                    }
                }
            }

            long groupedTotal = groups.values().stream()
                    .mapToLong(Long::longValue).sum();

            System.out.println("request-count=" + requestCount);
            System.out.println("job-count=" + jobCount);
            System.out.println("grouped-total=" + groupedTotal);
            System.out.println("at-least-two-groups="
                    + (groups.size() >= 2));
        } finally {
            Files.deleteIfExists(path);
        }
    }
}
```

Biên dịch và chạy khi JDK 17+ có module `jdk.jfr` và quyền tạo file:

```bash
javac --release 17 JfrWindowFileDemo.java
java JfrWindowFileDemo
```

**Stdout kỳ vọng khi JFR ghi được đủ các custom events:**

```text
request-count=3
job-count=2
grouped-total=5
at-least-two-groups=true
```

**Giải thích:**

1. Hai lớp `Request`/`Job` có `@Name` độc lập, giúp consumer lọc đúng tên loại event.
2. `Recording.enable(...).withoutThreshold()` bật cả hai loại và không loại event nhanh theo duration threshold.
3. `Recording.start()` mở khoảng ghi; năm lời gọi `commit()` được thực hiện trong khoảng đó.
4. `stop()` kết thúc ghi; `dump(path)` xuất file; `RecordingFile` đọc file offline.
5. Filter chỉ giữ hai tên `demo.AggregateRequest` và `demo.AggregateJob`, bỏ các loại JFR event khác.
6. `groups.merge(...)` tăng bộ đếm theo **phút kết thúc và loại event**.
7. `grouped-total=5` kiểm tra rằng tổng count của mọi nhóm đúng bằng số events đã lọc.
8. `at-least-two-groups` phải true nếu có cả hai loại event, dù tất cả năm events ở cùng một phút hay trải qua nhiều phút.

**Không khẳng định `groups.size() == 2`:** Nếu chương trình chạy đúng lúc ranh giới một phút, một loại event có thể xuất hiện trong hai cửa sổ và số nhóm lớn hơn 2. Đây chính là lý do output chỉ kiểm tra **tổng theo type và tổng toàn nhóm**, không in timestamp tùy máy như một kết quả cố định.

Với event duration thực tế, có thể thay `Map<Key, Long>` bằng `Map<Key, Stats>` như phần 5 và cập nhật `Stats.add(e.getDuration())`. Nếu muốn đếm byte hoặc lỗi, đọc field được định nghĩa trên event type sau khi đã kiểm tra đúng tên và sự tồn tại của field.

## 7. Chia cửa sổ không phải lúc nào cũng theo phút

### 7.1. Cửa sổ 5 phút bằng `Math.floorDiv`

Với tumbling window có độ rộng **5 phút** tính từ epoch, không nên chỉ thay `ChronoUnit.MINUTES` thành `ChronoUnit.FIVE_MINUTES` vì Java không có hằng đó. Tính toán ví dụ:

```java
import java.time.Duration;
import java.time.Instant;

static Instant bucketFiveMinutes(Instant end) {
    long widthMs = Duration.ofMinutes(5).toMillis();
    long startMs = Math.floorDiv(end.toEpochMilli(), widthMs)
            * widthMs;
    return Instant.ofEpochMilli(startMs);
}
```

Đây là phương thức minh họa để đặt trong class. Dùng `Math.floorDiv` thay vì phép chia nguyên trực tiếp vì nó xử lý **timestamp trước epoch** theo phép làm tròn xuống; chia `/` của Java làm tròn về zero, có thể cho bucket sai trước năm 1970.

**Giới hạn:** Cách dùng `toEpochMilli()` chỉ chính xác đến milli-second. Với bucket tính theo vài phút, điều này thường đủ; nếu cần cửa sổ nanosecond hoặc timestamp cực lớn ngoài phạm vi `long` epoch millis, phải dùng biểu diễn và kiểm tra overflow phù hợp.

### 7.2. Cửa sổ theo lịch địa phương

Nếu bài toán đòi «mỗi giờ theo giờ Việt Nam» hoặc «mỗi ngày theo múi giờ người dùng», không nên lấy `Instant.truncatedTo(DAYS)` rồi nói đây là ngày địa phương. Hãy xác định `ZoneId`:

```java
java.time.ZoneId zone = java.time.ZoneId.of("Asia/Ho_Chi_Minh");
java.time.LocalDate day = eventEnd.atZone(zone).toLocalDate();
```

Cách nhóm theo `LocalDate` có ý nghĩa **ngày địa phương**, khác với tumbling window 24 giờ bắt đầu ở nửa đêm UTC. Với vùng có DST, một «ngày lịch» có thể không đúng 24 giờ và giờ lặp/thiếu có thể xảy ra. Chọn kiểu bucket phù hợp với yêu cầu, không đổi ngầm giữa hai định nghĩa.

## 8. Streaming bằng `EventStream` và `RecordingStream`

`RecordingFile` đọc file sau khi ghi. Trong ứng dụng đang chạy, hai API khác phục vụ consumer liên tục:

- `EventStream.openRepository()` đọc repository của JVM hiện tại, **không tự tạo recording**. Mặc định bắt đầu từ sự kiện được JFR **flush tiếp theo**, không tự replay toàn bộ lịch sử.
- `RecordingStream` tạo recording cùng với stream trong JVM hiện tại; có thể `enable(type)` và đăng ký `onEvent` trên cùng đối tượng.
- `EventStream.openFile(path)` cũng hỗ trợ callback, nhưng nguồn là **file hữu hạn**, không phải live producer.

### 8.1. Đăng ký callback theo loại sự kiện

Đoạn code minh họa nằm trong phương thức có quyền truy cập stream:

```java
stream.onEvent("jdk.GarbageCollection", e -> {
    String type = e.getEventType().getName();
    java.time.Instant minute = e.getEndTime()
            .truncatedTo(java.time.temporal.ChronoUnit.MINUTES);

    // Cập nhật bucket (minute, type) tại đây.
});
```

Có thể đăng ký `stream.onEvent(callback)` để nhận mọi loại event hoặc `stream.onEvent("name", callback)` để lọc. Nếu một event type đang ghi ở tần suất rất lớn, **lọc sớm** và giảm công việc trong callback là quan trọng.

**Tuy nhiên:** Đăng ký callback không tự bật event producer. Với `RecordingStream`, dùng `enable("jdk.GarbageCollection")` hoặc loại tùy biến tương ứng nếu muốn recording do stream quản lý ghi loại event đó. Với `EventStream.openRepository()`, phải có một recording phù hợp đã ghi dữ liệu.

### 8.2. `onFlush` để xuất bản snapshot, không phải đóng cửa sổ thời gian

Theo Javadoc `EventStream`, events được giao theo **batches**. `onFlush(Runnable)` thông báo khi một batch kết thúc, là điểm thuận tiện để gửi **snapshot các nhóm đang có** sang metrics backend.

```java
// Code minh họa trong phương thức, với stream chưa start.
java.util.concurrent.ConcurrentHashMap<String,
        java.util.concurrent.atomic.LongAdder> counts =
        new java.util.concurrent.ConcurrentHashMap<>();

stream.onEvent("jdk.GarbageCollection", event -> {
    counts.computeIfAbsent(
            event.getEventType().getName(),
            ignored -> new java.util.concurrent.atomic.LongAdder()
    ).increment();
});

stream.onFlush(() -> {
    long seen = counts.values().stream()
            .mapToLong(java.util.concurrent.atomic.LongAdder::sum)
            .sum();
    System.out.println("seen-so-far=" + seen);
});
```

Đây là ví dụ **snapshot tổng theo loại event** để minh họa cách `onFlush` được sử dụng; muốn thêm chiều thời gian, thay khóa `String` bằng cặp `(windowStart, type)` như ở phần 5. Không có stdout cố định: số GC event, số flush và thời gian callback do JVM quyết định.

**Quan trọng:** Một batch **không phải** cửa sổ 1 phút. Một batch có thể chứa event thuộc **nhiều phút**; một phút có thể trải qua **nhiều batch**. `onFlush` không chứng minh rằng một cửa sổ phút đã đủ dữ liệu để chốt vĩnh viễn.

### 8.3. `start()` và `startAsync()`

- `start()` xử lý callback trên thread gọi và có thể chặn cho tới khi stream dừng.
- `startAsync()` xử lý callback trên thread riêng; thread còn lại có thể tiếp tục phục vụ ứng dụng.
- `close()` đóng stream; Javadoc không bảo đảm mọi action đã hoàn tất ngay khi phương thức trả về.
- `onError(...)` giúp bắt lỗi callback và tránh nhầm lỗi xử lý với việc event chưa được ghi.
- Khi đọc/ghi bảng tổng hợp từ nhiều thread, dùng cơ chế synchronization hoặc concurrent collections phù hợp.

Ví dụ một bộ `HashMap` chỉ được xử lý trong callback thread không nên bị thread khác duyệt mà thiếu bảo vệ. Một `ConcurrentHashMap<Key, LongAdder>` hỗ trợ cập nhật count đồng thời, nhưng **không biến snapshot gồm nhiều key thành một transaction nhất quán tuyệt đối**. Nếu yêu cầu snapshot chính xác, cần thiết kế lock, single-threaded aggregator hoặc trao đổi dữ liệu theo batch bất biến.

## 9. Sự kiện tới trễ và không đúng thứ tự

Theo Javadoc `EventStream`:

- Events **trong cùng batch** được sắp theo thời điểm kết thúc, trừ khi bạn tắt sorting.
- **Giữa các batch**, một event đến sau có thể mang timestamp **sớm hơn** event ở batch trước.
- `onFlush` không cam kết «từ đây không còn event nào của phút trước».
- `setOrdered(false)` có thể giảm chi phí sorting khi thứ tự không cần thiết, nhưng không thay đổi định nghĩa event time.

Ví dụ:

```text
Batch 1 đã giao:
  10:01:05  demo.HTTP
  10:01:08  demo.DB

Batch 2 giao sau:
  10:00:59  demo.HTTP  (event đến trễ so với batch 1)
  10:01:09  demo.HTTP
```

Nếu code chốt bucket 10:00 ngay khi nhận event 10:01 ở batch 1, thì event `10:00:59` ở batch 2 bị thiếu khỏi số liệu đã phát hành. Đây là lỗi **thiết kế chính sách đóng cửa sổ**, không phải lỗi toán cộng.

### 9.1. Chính sách cửa sổ cho streaming

Một thiết kế thường sử dụng:

1. **Giữ các bucket đang mở** trong map, theo key `(windowStart, eventType)`.
2. **Định nghĩa một khoảng chờ trễ (allowed lateness)** theo mục tiêu vận hành, ví dụ cửa sổ 60 giây và cho phép cập nhật thêm 10 giây sau ranh giới.
3. **Phát hành kết quả tạm thời (provisional snapshot)** qua `onFlush` hoặc theo timer nếu dashboard cần cập nhật nhanh.
4. Khi đã vượt ranh giới đóng cửa sổ theo chính sách, **xuất kết quả cuối** và xóa state của bucket để giới hạn bộ nhớ.
5. Nếu event đến **muộn hơn chính sách**, chọn một trong các cách: sửa kết quả (upsert/revision), ghi vào late-events counter, hoặc bỏ với lý do rõ ràng.
6. Nếu consumer restart hoặc đọc lại file, phải có chính sách **đếm lại, dedup hoặc replace snapshot** để không double-count dữ liệu đã xử lý.

**Lưu ý:** Việc chọn grace period 10 giây **là quyết định của ứng dụng**, không phải bảo đảm của JFR rằng mọi event sẽ tới trong 10 giây. Khi cần tính toàn vẹn offline, có thể tạo recording hữu hạn, stop/dump và xử lý toàn bộ file thay vì chốt cửa sổ trực tiếp từ một stream đang chạy.

### 9.2. Event time so với processing time

| Cách nhóm | Khóa thời gian | Khi phù hợp | Rủi ro |
| --- | --- | --- | --- |
| **Event time** | `RecordedEvent.getEndTime()` | Báo cáo «event thực sự kết thúc phút nào» | Cần late-event policy khi streaming |
| **Processing time** | `Instant.now()` trong `onEvent` | Báo cáo tải quan sát hiện tại của consumer | Event đến trễ bị đặt vào phút nhận, làm lệch phân bố lịch sử |
| **Start time** | `getStartTime()` | Báo cáo thời điểm bắt đầu thao tác | Không phản ánh phút hoàn tất |
| **Overlap time** | Giao của `[start,end)` với mỗi bucket | Tổng thời lượng trải qua nhiều bucket | Phải xử lý interval overlap và metric semantics |

Phần lớn báo cáo performance theo JFR nên có **time semantics rõ ràng**, không dùng chung một nhãn «per minute» cho cả bốn cách.

## 10. Tính thống kê thời lượng đúng cách

### 10.1. Sum/average/max cho mỗi nhóm

Giả sử bucket chứa durations `12 ms`, `20 ms`, `40 ms`:

- `count = 3`;
- `sum = 72 ms`;
- `avg = 24 ms`;
- `max = 40 ms`.

**Đơn vị:** Phải công bố rõ là ms, ns, byte hay count. Với `Duration`, `toMillis()` có thể cắt bớt phần dưới 1 ms. Nếu thu thập event microsecond, nên cộng ở ns hoặc dùng histogram có bucket đủ nhỏ. Các tổng cộng long cần kiểm tra overflow nếu thời gian/khối lượng dữ liệu rất lớn hoặc chạy lâu dài.

**Chỉ lấy trung bình từ những mẫu thực sự được ghi**. Nếu JFR event có `threshold=10 ms`, các event ngắn hơn không có trong tập đã ghi; trung bình của các event còn lại **không phải** trung bình của tất cả thao tác thực tế.

### 10.2. P95/P99 cần dữ liệu phân phối, không chỉ aggregate đơn giản

Nếu chỉ lưu `count`, `sum` và `max`, không thể suy ra p95, p99 hoặc median chính xác. Muốn percentiles:

- Dùng histogram với các ngưỡng đã định nghĩa;
- Hoặc dùng cấu trúc quantile estimator cho data stream;
- Hoặc giữ mẫu nếu số lượng hữu hạn và được phép về bộ nhớ.

Với tần suất lớn, giữ toàn bộ mỗi `RecordedEvent` để tính p95 có thể làm heap tăng nhanh. Chọn histogram/ước lượng phù hợp và ghi rõ độ chính xác. Không gọi trung bình là p95.

### 10.3. Tổng thời lượng không luôn là «thời gian tường»

Nếu ba request chạy **song song** và mỗi request 100 ms, tổng duration là 300 ms nhưng elapsed wall-clock của toàn nhóm có thể gần 100 ms. Với GC events cũng cần hiểu ý nghĩa loại event trước khi diễn giải tổng duration là «tổng downtime» hoặc «CPU time»; các khoảng thời gian có thể chồng lấp hoặc đo các đại lượng không đồng nhất.

Khi cần biết **thời gian hệ thống bận trong một cửa sổ**, cần định nghĩa metric chính xác, có thể là union of intervals, throughput, CPU load hoặc phần overlap của event span; không dùng cộng duration một cách máy móc.

### 10.4. Phân bổ một event qua hai cửa sổ

Ví dụ một thao tác kéo dài từ `10:00:58` đến `10:01:03`, tổng duration 5 giây:

- Bucket `[10:00:00,10:01:00)` giao với event: 2 giây;
- Bucket `[10:01:00,10:02:00)` giao với event: 3 giây.

Nếu yêu cầu **phân bổ duration theo thời gian**, cần tính:

```text
overlap = max(0,
    min(eventEnd, windowEnd) - max(eventStart, windowStart))
```

Đây là một **công thức khái niệm**. Nếu yêu cầu chỉ là **đếm số thao tác hoàn tất**, hãy nhóm event **một lần** vào bucket chứa `endTime`, không chia count ra nhiều bucket. Tách hai bài toán này để tránh double-count.

## 11. Số liệu và sự thiếu vắng event

Một kết quả `count = 0` có thể mang nhiều nghĩa:

- **Không có** tác vụ tương ứng trong cửa sổ;
- Event type **chưa được enable**;
- Threshold/period/sampling của loại event làm dữ liệu chưa được ghi;
- Stream chưa start hoặc đã close trước khi event được flush;
- Consumer mở repository sau thời điểm flush và mặc định chỉ đọc từ flush tiếp theo;
- Dữ liệu lịch sử đã vượt `maxAge/maxSize`, mất khỏi repository;
- Callback lọc sai event name hoặc ném exception;
- Mã tổng hợp đã chốt/evict bucket trước khi late event tới.

Vì vậy một hệ thống dashboard cần **health/coverage metrics** bên cạnh event counts. Đừng trình bày «0 events = không có vấn đề gì» nếu bạn chưa kiểm chứng rằng recording và consumer đang hoạt động.

### 11.1. Đối chiếu với ghi file offline

Khi cần QA số lượng:

1. Bật recording cho đúng loại custom event.
2. Phát sinh một số event kiểm thử với ID/loại xác định.
3. `stop()` và `dump()` recording, rồi đọc file bằng `RecordingFile`.
4. Cộng counts theo type, đối chiếu tổng các bucket với tổng số event đã lọc.
5. So sánh với số event consumer stream đã quan sát trong cùng khoảng, lưu ý sự khác nhau về time window và retention.

Một `RecordingFile` đọc dữ liệu đã ghi là cách thuận tiện để kiểm tra **producer/recording** có hoạt động; nó không tự chứng minh mọi live stream đã nhận toàn bộ events đúng deadline.

## 12. Tối ưu hiệu năng và bộ nhớ

### 12.1. Không tạo nhóm với cardinality vô hạn

Nếu nhóm theo `(minute, eventType, requestId)` và `requestId` là unique, mỗi request tạo một bucket riêng. Trên hệ thống có nhiều request, map sẽ tăng gần bằng số event, mất lợi ích aggregate.

Ưu tiên dimension đã chuẩn hóa và hữu hạn:

```text
Tốt:  (minute, "demo.HttpRequest", statusClass=2xx)
Tốt:  (minute, "demo.HttpRequest", route="/items/:id")
Rủi ro: (minute, "demo.HttpRequest", rawURL="/items/781239?token=...")
```

Ví dụ này mô tả **metric labels**, không phải thông tin người dùng thật. Raw URL có thể chứa dữ liệu nhạy cảm; cần redaction và giới hạn cardinality.

### 12.2. Kích thước state

Với 10 event types và 15 cửa sổ đang mở, tối thiểu có thể có 150 nhóm, ngoài histogram/dimensions phụ. Với thêm 20 status/route labels, số nhóm có thể tăng nhanh. Cần đo:

- Số nhóm hoạt động;
- Thời hạn retention state sau khi chốt;
- Số late events;
- Thời gian xử lý mỗi `onEvent`;
- Thời gian phát hành snapshot;
- Bộ nhớ histogram và backlog.

**Đừng giữ toàn bộ `RecordedEvent` để «lúc nào cần thì tính lại»** nếu chỉ cần count/sum/max. Đọc field cần thiết và cập nhật stats ngay trong callback. Theo Javadoc `EventStream`, có chế độ tái sử dụng `RecordedEvent` objects; nếu cần giữ object qua callback, phải kiểm tra `setReuse(false)` hoặc sao chép dữ liệu cần thiết.

### 12.3. Callback phải nhẹ

Trong `onEvent`:

- Lọc event name/schema sớm;
- Xác định bucket bằng phép toán thời gian nhỏ;
- Cập nhật counter/summary;
- Tránh synchronous network I/O, ghi file nặng và sleep;
- Nếu cần xuất dữ liệu, làm theo batch/timer qua một thành phần riêng có giới hạn queue.

Nếu collector không theo kịp, độ trễ tăng; khi có retention giới hạn, có thể không quan sát được toàn bộ lịch sử. **JFR không phải message broker bảo đảm exactly-once**, nên không dùng event aggregation như hệ thống ghi nhận giao dịch bắt buộc chính xác.

## 13. Thread safety và snapshot consistency

Một thiết kế offline đơn luồng có thể dùng `HashMap<Key, Stats>` đơn giản. Nhưng với `startAsync()`, callback chạy trên thread riêng. Nếu thread dashboard cũng đang duyệt map, phải dùng synchronization thích hợp.

| Cách xử lý | Ưu điểm | Giới hạn |
| --- | --- | --- |
| Một thread duy nhất cập nhật và xuất snapshot | Dễ đảm bảo nhất quán, ít locking | Chậm nếu thực hiện việc nặng trên callback thread |
| `ConcurrentHashMap<Key, LongAdder>` cho counts | Hỗ trợ increment đồng thời | Snapshot nhiều key không tự atomic |
| `synchronized` hoặc `ReadWriteLock` quanh map/stats | Có thể lấy snapshot nhất quán | Cẩn thận lock contention và callback latency |
| Immutable snapshot giao sang thread khác | Consumer không cần giữ lock khi render | Phải copy state ở đúng ranh giới và giới hạn tần suất copy |

Nếu `onFlush` và `onEvent` cùng truy cập map, hãy xác định **threading model của API và cách chia sẻ state ngoài stream**. Một callback đang in ra stdout có thể chậm; tránh để nó trở thành phần chính của latency.

### 13.1. Snapshot chưa phải kết quả cuối

Các hàng aggregate trong stream thường có trạng thái:

- **OPEN:** cửa sổ vẫn nhận updates;
- **PROVISIONAL:** đã công bố bản tạm để dashboard thấy số liệu;
- **FINAL:** ứng dụng quyết định đóng cửa sổ theo chính sách allowed lateness và nguồn dữ liệu.

Đây là **trạng thái do ứng dụng thiết kế**, không phải loại object của JFR. `onFlush` giúp có thời điểm phát hành tạm thời, nhưng không tự suy ra watermarks hay finalization của cửa sổ.

## 14. Các lỗi thường gặp và cách sửa

| Hiểu nhầm | Hậu quả | Cách đúng |
| --- | --- | --- |
| «Mỗi flush là một cửa sổ một phút». | Batch có thể chứa nhiều phút và một phút có nhiều batch. | Tự tạo bucket bằng event timestamp; dùng flush chỉ để cập nhật snapshot. |
| Dùng `Instant.now()` để báo thời điểm event xảy ra. | Dữ liệu tới trễ bị dịch sang phút callback. | Dùng `RecordedEvent.getEndTime()` khi muốn event-time analytics. |
| Gộp mọi event name vào một nhóm. | Metric không còn phân biệt GC, I/O, custom event. | Key gồm `windowStart` và `eventType`. |
| Dùng event type mà không hiểu schema. | Cộng duration sai ý nghĩa hoặc đọc field không tồn tại. | Đọc JFR event metadata, chỉ tính metric có ý nghĩa. |
| Dùng phút đầu tiên nhìn thấy để chốt mọi window cũ. | Bỏ sót late events từ batch sau. | Có allowed-lateness/revision/drop policy. |
| Gọi `onFlush` là tín hiệu «đủ mọi event». | Tổng thiếu nhưng được gắn nhãn FINAL. | Chỉ phát provisional snapshot hoặc chốt theo chính sách riêng. |
| Tính p99 từ `sum/count`. | Nhầm average với percentile. | Dùng histogram/quantile estimator. |
| Group theo raw request ID/URL. | Cardinality và dữ liệu nhạy cảm tăng vọt. | Chuẩn hóa dimension, giới hạn nhãn. |
| Không xử lý retention map. | Mất bộ nhớ khi chạy dài hạn. | Evict buckets đã chốt; giới hạn history state. |
| Không xử lý event threshold. | Count phản ánh subset đã ghi, không phải toàn bộ thao tác. | Cấu hình và ghi rõ coverage của recording. |
| Đọc file lớn bằng `RecordingFile.readAllEvents`. | Có thể gây áp lực heap. | Duyệt `hasMoreEvents()/readEvent()`. |
| In/log hoặc gọi mạng trong mỗi callback. | Làm chậm consumer, tăng lag. | Chỉ cập nhật stats; xuất batch với queue có giới hạn. |
| Kết luận «0 event = 0 workload». | Có thể event chưa bật hoặc collector bỏ lỡ. | Có health check và đối chiếu producer/recording. |
| Dùng local time không xác định timezone. | Ngày/giờ nhóm khác nhau giữa môi trường. | Chọn UTC hoặc `ZoneId` rõ ràng. |
| Restart consumer rồi cộng lại snapshot cũ. | Có thể double-count dữ liệu replay. | Dùng idempotent replace/upsert hoặc dedup policy. |

## 15. Quy trình triển khai vào hệ thống thật

Một quy trình triển khai JFR aggregation có thể làm theo các bước:

1. **Xác định metric:** Bạn cần số lượng, tần suất, duration hay histogram? Sự kiện nào thực sự có field phù hợp?
2. **Chọn event types:** Ví dụ `jdk.GarbageCollection`, `jdk.FileRead` hoặc custom `demo.RequestFinished`; kiểm tra Javadoc/metadata và loại event đã enable.
3. **Chọn time semantics:** Bắt đầu, kết thúc, callback time hay overlap duration? Viết rõ trong tài liệu.
4. **Chọn window:** 1 phút tumbling UTC, 5 phút epoch-aligned, hay sliding 60 giây mỗi 10 giây.
5. **Thiết kế key:** `(windowStart, eventType)` và dimension hữu hạn nếu cần.
6. **Định nghĩa stats:** count, total/max duration, error count, histogram; nêu đơn vị và chính sách overflow.
7. **Lập bộ tổng hợp offline trước:** Với dữ liệu mẫu có timestamp cố định, kiểm tra bucket boundaries và output chính xác như phần 5.
8. **Nối JFR input:** Dùng `RecordingFile` với file test hoặc `RecordingStream` cho live events; đăng ký callback và enable đúng event.
9. **Xử lý batching/late:** `onFlush` để snapshot, allowed lateness/watermark do ứng dụng quyết định, quy tắc final/revision.
10. **Giới hạn state:** Evict windows cũ, giới hạn cardinality/histogram, theo dõi lag và callback time.
11. **Định nghĩa output:** Nhãn UTC/zone, interval `[start,end)`, event type, count, units, coverage và trạng thái provisional/final.
12. **Kiểm thử:** Synthetic boundary cases; offline recording; restart/replay; late events; không có event; threshold; sai schema; time zone và DST.
13. **Triển khai an toàn:** Giới hạn quyền file/repository, không xuất dữ liệu nhạy cảm; benchmark overhead dưới tải thật.
14. **Giám sát collector:** Event counts, số cửa sổ đang giữ, số lần flush đã nhận, độ trễ callback, số errors và late arrivals.
15. **Đánh giá độ tin cậy:** Nếu số liệu phải là sổ cái chính xác, hãy dùng kênh lưu nghiệp vụ khác để đối chiếu vì JFR là hệ thống quan sát.

## 16. Bài tập tự kiểm tra

### Bài 1 — Phân bucket tại ranh giới phút

Các event kết thúc vào `10:00:59.999Z` và `10:01:00.000Z`. Chúng cùng bucket không?

**Đáp án:** Không. Với cửa sổ nửa mở 1 phút, event đầu thuộc `[10:00,10:01)`, event thứ hai thuộc `[10:01,10:02)`.

### Bài 2 — Khóa nhóm gồm những gì?

Bạn có hai loại event `demo.HTTP` và `demo.DB` trong cùng một phút. Nếu key chỉ là timestamp phút, có vấn đề gì?

**Đáp án:** Số liệu của hai loại sẽ bị gộp. Dùng key `(windowStart, eventType)` để mỗi loại có một hàng thống kê độc lập.

### Bài 3 — Số lần `onFlush` có bằng số cửa sổ không?

**Đáp án:** Không. `onFlush` báo ranh giới **batch JFR**, không phải ranh giới thời gian do ứng dụng chọn. Cửa sổ 1 phút có thể nhận dữ liệu từ nhiều batches và một batch có thể chứa nhiều cửa sổ.

### Bài 4 — Event đến trễ

Batch 1 đã chứa event 10:01:05, sau đó batch 2 chứa event 10:00:59. Nếu đã đóng bucket 10:00 ở batch 1 thì sao?

**Đáp án:** Bỏ sót event 10:00:59. Thiết kế allowed lateness/revision policy, không dùng `onFlush` như watermark cuối cùng.

### Bài 5 — Đọc duration từ instant event

Bạn tính average `getDuration()` cho một loại instant event. Kết quả thường bằng bao nhiêu?

**Đáp án:** Bằng zero vì start/end của instant event bằng nhau. Nếu cần đo thời gian hoạt động, hãy định nghĩa duration event và đo bằng `begin()/end()/commit()` hoặc dùng event type có duration phù hợp.

### Bài 6 — P95 từ count/sum/max

Một bucket có count=100, sum=1500 ms, max=80 ms. Có xác định p95 chính xác được không?

**Đáp án:** Không. Những đại lượng đó không mô tả đủ phân phối. Cần histogram, quantile estimator hoặc các samples thực tế.

### Bài 7 — Nên dùng `getEndTime()` hay `Instant.now()`?

Bạn muốn số lượng request **hoàn tất** trong từng phút theo UTC.

**Đáp án:** Dùng `getEndTime()` của `RecordedEvent`. `Instant.now()` trong callback là processing time và có thể khác nhiều nếu dữ liệu được flush/đọc trễ.

### Bài 8 — Khi nào `RecordingFile` tốt hơn live stream?

Bạn đã có file `.jfr` của một đợt benchmark, cần tổng hợp đúng tập event đã được lưu.

**Đáp án:** Đọc file bằng `RecordingFile`, duyệt tăng dần và group theo event time/type. Không cần waiting/flush callbacks lúc runtime.

### Bài 9 — Tần suất bị ảnh hưởng bởi threshold?

Bạn ghi các event chỉ khi duration vượt 10 ms, nhưng dashboard báo «số request mỗi phút». Có đúng không?

**Đáp án:** Đây chỉ là **số request được JFR ghi sau threshold**, không phải toàn bộ request. Chọn setting phù hợp hoặc ghi rõ giới hạn dữ liệu; khi cần đếm chính xác mọi request, đừng suy ra từ mẫu JFR bị lọc.

### Bài 10 — Tổng duration và tính song song

Ba request song song mỗi request 100 ms, cùng trong một cửa sổ. Sum durations=300 ms có nghĩa JVM đã dành 300 ms wall-clock bận liên tục không?

**Đáp án:** Không. Các khoảng có thể chồng lấp, nên tổng duration khác elapsed wall-clock hay CPU time. Xác định metric trước khi diễn giải.

### Bài 11 — Xử lý dữ liệu lịch sử khi stream restart

Consumer `openRepository()` khởi động lại. Có chắc mọi bucket trước đó sẽ được gửi lại từ đầu không?

**Đáp án:** Không. Mặc định bắt đầu từ **event flush tiếp theo**. Khi dùng `setStartTime` để đọc dữ liệu còn giữ, cần thiết kế chống double-count hoặc replace snapshot theo window key.

### Bài 12 — Tại sao cần UTC hoặc time zone cố định?

**Đáp án:** Để hai máy không tạo nhãn bucket khác nhau cho cùng thời điểm; khi báo theo ngày/giờ địa phương, cần `ZoneId` và xử lý DST theo quy tắc lịch thay vì dùng múi giờ hệ thống một cách ngầm định.

## 17. Nguồn chính thức và kiến thức còn áp dụng

1. [Javadoc Java SE 25 — `jdk.jfr.consumer.RecordedEvent`](https://docs.oracle.com/en/java/javase/25/docs/api/jdk.jfr/jdk/jfr/consumer/RecordedEvent.html): `getEventType`, `getStartTime`, `getEndTime`, `getDuration` và đặc tính instant event.
2. [Javadoc Java SE 25 — `jdk.jfr.consumer.EventStream`](https://docs.oracle.com/en/java/javase/25/docs/api/jdk.jfr/jdk/jfr/consumer/EventStream.html): `onEvent`, `onFlush`, batch delivery, ordering giới hạn trong batch, `openRepository` và `setStartTime`.
3. [Javadoc Java SE 25 — `jdk.jfr.consumer.RecordingFile`](https://docs.oracle.com/en/java/javase/25/docs/api/jdk.jfr/jdk/jfr/consumer/RecordingFile.html): đọc file `.jfr` tăng dần và giới hạn của `readAllEvents`.
4. [Javadoc Java SE 25 — `jdk.jfr.consumer.RecordingStream`](https://docs.oracle.com/en/java/javase/25/docs/api/jdk.jfr/jdk/jfr/consumer/RecordingStream.html): recording + stream trong JVM hiện tại.
5. [Javadoc Java SE 25 — `jdk.jfr.Recording`](https://docs.oracle.com/en/java/javase/25/docs/api/jdk.jfr/jdk/jfr/Recording.html): `enable`, `start`, `stop`, `dump` và quản lý recording.
6. [Javadoc Java SE 25 — `jdk.jfr.Event`](https://docs.oracle.com/en/java/javase/25/docs/api/jdk.jfr/jdk/jfr/Event.html): custom events, `begin`, `end`, `commit`, `shouldCommit`.
7. [Javadoc Java SE 17 — `RecordingFile`](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.jfr/jdk/jfr/consumer/RecordingFile.html): đối chiếu API với release biên dịch `--release 17`.
8. [Javadoc Java SE 17 — `java.time.Instant`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/Instant.html): `truncatedTo`, `atZone` và epoch timestamps.
9. [JEP 349 — JFR Event Streaming](https://openjdk.org/jeps/349): nguồn gốc API streaming từ Java 14; sử dụng Javadoc hiện hành để triển khai.
10. [Dev.java — công cụ `jfr` để đọc và phân tích file Flight Recorder](https://dev.java/learn/jvm/monitoring-troubleshooting/monitoring/jfr/): công cụ chính thức giúp kiểm tra các loại event/file `.jfr`.

**Ghi nhớ:** Dùng `RecordedEvent.getEndTime()` hoặc một time semantic được định nghĩa rõ, tạo khóa **(windowStart, eventType)**, cập nhật count/duration/metrics cho từng khóa. **Tumbling window** và **sliding window** có ý nghĩa khác nhau. `onFlush` là ranh giới batch của JFR, **không** phải lời xác nhận một time window đã đóng. Với stream, cần chính sách late events, bounded state, concurrency và snapshot; với dữ liệu offline, `RecordingFile` giúp phân tích tập sự kiện đã lưu.