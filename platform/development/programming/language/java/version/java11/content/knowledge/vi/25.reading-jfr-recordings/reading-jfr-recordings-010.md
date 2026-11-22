# Đọc bản ghi JFR: So sánh trước, sau thay đổi bằng cùng kịch bản tải (Java 11+)

## 1. Vì sao phải kiểm soát kịch bản tải khi so sánh JFR?

**JDK Flight Recorder (JFR)** ghi các sự kiện về JVM và ứng dụng như CPU sampling, garbage collection (GC), allocation, I/O, thread blocking và application-defined events. Sau khi tối ưu Java code, người phát triển có thể muốn so sánh hai file:

~~~text
before.jfr  <-- ứng dụng trước khi thay đổi
after.jfr   <-- ứng dụng sau khi thay đổi
~~~

Tuy nhiên, hai file có sự kiện khác nhau **không tự chứng minh** hiệu năng đã thay đổi vì code. Có thể số lượng request khác nhau, dữ liệu khác, cache nóng/lạnh, JIT warm-up không giống nhau, JVM flags thay đổi hoặc một lần chạy chịu tải từ process khác. **Điều kiện quan trọng nhất: hai phiên cần cùng kịch bản tải, cùng cách đo và cùng tiêu chí đúng/sai.**

Quy trình phù hợp:

1. Đặt **giả thuyết cụ thể**, chẳng hạn “tái sử dụng regex `Pattern` giúp giảm thời gian xử lý mỗi batch”.
2. Thiết kế **input và công việc giống nhau** cho baseline (*before*) và candidate (*after*).
3. Giữ **JDK, JVM flags, CPU/memory limits, GC, JFR event settings** càng giống nhau càng tốt.
4. Cùng nguyên tắc **warm-up** trước khi bắt đầu so sánh steady-state.
5. Ghi đúng loại sự kiện trong cả hai file với **cùng threshold/stacktrace/sampling policy**.
6. Đọc file `.jfr`, kiểm đủ số mẫu và **đầu ra nghiệp vụ bằng nhau**.
7. Tính median, p95, rate/byte-per-operation khi phù hợp, rồi **lặp lại thí nghiệm** để đánh giá nhiễu.
8. Đọc các JVM events liên quan để đề xuất nguyên nhân, không suy diễn từ một số đo duy nhất.

JFR **không phải công cụ tạo tải**. Nó quan sát những gì JVM thực sự làm; load generator, test script hoặc chương trình benchmark phải chịu trách nhiệm tạo **cùng lượng công việc**.

## 2. Điều gì là “cùng kịch bản tải”?

Một phép so sánh công bằng không nhất thiết mọi thứ đều hoàn hảo tuyệt đối, nhưng các biến quan trọng phải được **cố định hoặc ghi nhận**.

| Nhóm | Điều cần giữ nhất quán | Tại sao quan trọng |
| --- | --- | --- |
| Input | Cùng dataset, seed, payload sizes, thứ tự, tỉ lệ valid/invalid | Input khác khiến thời gian xử lý khác |
| Work volume | Cùng số items, requests, batches hoặc thời gian và RPS mục tiêu | Không so tổng events khi khối lượng khác |
| Load shape | Cùng concurrency, request mix, ramp-up, think time, steady-state window | QPS/queueing phụ thuộc tải đồng thời |
| Runtime | Cùng JDK build, GC, `-Xms`/`-Xmx`, CPU/OS/architecture | JVM và hệ thống có ảnh hưởng lớn |
| Environment | CPU quota, memory/cgroup, cache, DB dataset, service dependencies | Tránh bottleneck ngoài code đổi theo |
| JFR | Cùng `default`/`profile`, event types, threshold, stack traces, sampling | Không biến chênh lệch cấu hình thành chênh lệch hiệu năng |
| Warm-up | Cùng nguyên tắc làm nóng JIT/class loading/cache | Tránh so cold với hot |
| Correctness | Cùng số kết quả và lỗi; cùng side effects | Nhanh hơn nhưng tính sai là không đạt |

**Chỉ thay biến mà muốn đánh giá.** Khi thay đổi đồng thời JVM, database schema, library và implementation, có thể so hai hệ thống tổng thể nhưng không khẳng định tăng tốc chỉ do một dòng code.

### Đo steady-state hay startup?

- Muốn so **startup**: bao gồm class loading/JIT startup trong phép đo, dùng cấu hình JFR bắt từ lúc JVM launch và cùng phương pháp khởi động.
- Muốn so **steady-state**: warm-up trước, rồi ghi/đọc một cửa sổ tải tương đương. Không tính startup theo cách không đồng nhất vào median.
- Muốn so **production latency**: đo tại boundary của request/transaction; một duration event ôm một method chỉ đo **method đó**, không đo network, queueing hoặc downstream latency nếu chúng nằm ngoài event.

Đừng cố gộp ba mục tiêu vào một con số `speedup`.

## 3. Chọn chỉ số đúng trước khi thu dữ liệu

| Mục tiêu | Chỉ số phù hợp | Đơn vị, mẫu số |
| --- | --- | --- |
| Thời gian thực hiện công đoạn | Application event `getDuration()`, median và p95 | ms/batch hoặc ms/request |
| Tốc độ xử lý toàn hệ thống | Throughput từ load generator | successful requests/s |
| Tránh chậm ở đuôi phân phối | p95/p99 latency, timeout/error rates | ms/request, % |
| GC có đỡ ảnh hưởng? | GC events, pause-related events, allocation evidence | thời gian/nghìn ops, bytes/op |
| CPU có giảm? | `jdk.CPULoad`/`jdk.ThreadCPULoad`, execution samples | load %, samples theo stack, CPU ms/op nếu có counter |
| Thread có bớt chờ? | `jdk.JavaMonitorEnter`, `jdk.JavaMonitorWait`, `jdk.ThreadPark` | thời gian/block hoặc per-op |
| I/O có cải thiện? | `jdk.SocketRead`, `jdk.FileRead` và ứng dụng metrics | ms/op, bytes/s, errors |

**Không dùng tổng số event trong file làm KPI chung** khi hai recording có thời lượng khác nhau. Ví dụ số GC events của 120 giây không thể so trực tiếp với 30 giây; cần normalize theo **thời gian hoặc số request thành công**, đúng bản chất event.

**CPU samples không phải số lần method chạy.** `jdk.ExecutionSample` là sampling của các thread đang thực thi, không phải log đầy đủ mọi method call. `jdk.ObjectAllocationSample` cũng là sampling, không phải một bản ghi cho mọi đối tượng được cấp phát. Các event bị ảnh hưởng bởi sampling period, threshold và tải thực tế.

## 4. File `.jfr` chứa gì và đọc bằng công cụ nào?

JFR là định dạng **nhị phân**. File có event types với metadata, timestamp, duration (đối với duration event) và các fields. Để khảo sát ban đầu:

~~~bash
jfr summary before.jfr
jfr summary after.jfr

jfr print --events lesson.Batch before.jfr
jfr print --events lesson.Batch after.jfr
~~~

`jfr summary` cho thấy các loại event có mặt và số lượng. `jfr print --events ...` in chi tiết loại event mà bạn chọn.

Một event tùy chỉnh có dạng như sau (đã rút gọn):

~~~text
lesson.Batch {
  startTime = ...
  duration = ...
  variant = "before"
  batch = 0
  items = 1500
  matches = 1285
  checksum = 29873800
  eventThread = "main" (...)
}
~~~

Dấu `...` là các thông tin phụ thuộc lần chạy. **Không lấy timestamp giữa hai JVM rồi trừ nhau để suy ra thời lượng xử lý.** Với duration event bọc đúng code path, dùng **`RecordedEvent.getDuration()`**.

### JFR event type cần giống nhau

Nếu before có `lesson.Batch` nhưng after không có, đầu tiên phải hỏi:

- After có **bật event type đó** không?
- JFR đã `start()` trước khi business code chạy chưa?
- Cùng `threshold` không? Một event 2 ms có thể bị lọc nếu threshold là 20 ms.
- Code có gọi `Event.commit()` không?
- Có đọc **đúng file, đúng run, đúng thời điểm** không?
- JFR recording retention có xóa bớt dữ liệu không?
- Dữ liệu đầu ra có thay đổi, khiến code path không chạy nữa không?

**Không biến “không thấy event” thành “không còn bottleneck”** trước khi xác nhận cấu hình ghi nhận.

## 5. Java 11: đọc sự kiện qua `jdk.jfr.consumer.RecordingFile`

Nếu chỉ muốn đọc thủ công, CLI đủ dùng. Muốn kiểm tương đương và tính statistics tự động, dùng **`RecordingFile`** và **`RecordedEvent`** từ module `jdk.jfr`:

~~~java
try (RecordingFile file = new RecordingFile(Path.of("before.jfr"))) {
    while (file.hasMoreEvents()) {
        RecordedEvent event = file.readEvent();
        if ("lesson.Batch".equals(event.getEventType().getName())) {
            String variant = event.getString("variant");
            int batch = event.getInt("batch");
            int items = event.getInt("items");
            long nanos = event.getDuration().toNanos();
            // Kiểm metadata rồi thêm nanos vào phân phối thời gian.
        }
    }
}
~~~

Đây là **đoạn minh họa trong method có xử lý checked exceptions**, không phải chương trình độc lập; cần imports `RecordingFile`, `RecordedEvent`, `Path`.

Một số API:

- `recordingFile.hasMoreEvents()` và `readEvent()`: đọc tuần tự cho tới hết file.
- `event.getEventType().getName()`: xác định loại event.
- `event.getDuration()`: thời gian xảy ra giữa `Event.begin()` và `Event.end()` của một duration event.
- `event.getString("variant")`, `getInt("batch")`, `getLong("checksum")`: đọc typed fields do người phát event khai báo.
- `event.getStartTime()`/`getEndTime()`: xem timeline **trong recording**, không phải timestamp một lần chạy khác.

**Hợp đồng Java 11:** `RecordingFile.readAllEvents(Path)` có thể đọc toàn bộ events thành `List` nhưng Javadoc cảnh báo **không thích hợp với file lớn** vì tốn bộ nhớ. Nên dùng vòng lặp streaming ở trên cho production. Chỉ mở `.jfr` từ **nguồn tin cậy**; file sai/corrupt có thể gây `IOException`.

## 6. Kịch bản thực hành: regex trước và sau tối ưu

Để có thí nghiệm có thể chạy được, bài dùng cùng bài toán xử lý các chuỗi mã:

~~~text
ID-00000-bad   <-- không hợp lệ
ID-00001-OK    <-- hợp lệ
ID-00002-OK    <-- hợp lệ
...
ID-01499-OK    <-- theo quy tắc i % 7
~~~

Điều kiện hợp lệ là regex `^ID-[0-9]{5}-OK$`. Trong 1.500 đầu vào, những index chia hết cho 7 tạo suffix `-bad`, còn lại tạo `-OK`. Số lượng hợp lệ là **1.285**.

**Before** gọi:

~~~java
boolean matched = Pattern.matches(RE, text);
~~~

**After** giữ sẵn một `Pattern` bất biến:

~~~java
private static final Pattern CACHED = Pattern.compile(RE);
// Với mỗi input:
boolean matched = CACHED.matcher(text).matches();
~~~

Hai snippet là **mã minh họa**, biến `RE`/`text` và class context cần được định nghĩa. `Pattern.matches(...)` compile pattern trong mỗi lời gọi, trong khi phiên bản cached dùng lại `Pattern`. Mỗi lần so vẫn tạo một `Matcher` mới; **không tái sử dụng một `Matcher` mutable cho nhiều threads**, vì Matcher không thread-safe.

Cả hai cần cho cùng **matches** và **checksum**. Demo cố định:

| Thuộc tính | Giá trị |
| --- | --- |
| Input items mỗi batch | 1.500 |
| Số batch warm-up | 5 |
| Số batch đo | 8 |
| Regex | `^ID-[0-9]{5}-OK$` |
| Valid input count | 1.285 |
| Checksum | 29.873.800 |
| Event type đo | `lesson.Batch` |
| Cấu hình recording | `default` + bật custom event, threshold 0 |
| Cách đo | `begin()` / `end()` quanh `work(...)` |
| Hệ điều hành/JDK cho phép thử | Linux, OpenJDK 21, `javac --release 11` |

**Chỉ khác việc compile regex mỗi lần hay tái sử dụng Pattern.** Demo có warm-up 5 vòng cho mỗi process và ghi 8 batches. Tất cả input được tạo **trước khi bắt đầu thu events**, tránh cộng thời gian tạo dữ liệu vào duration của một batch.

**Lưu ý:** checksum ở đây chỉ là kiểm tra consistency giản lược, không phải bằng chứng mật mã rằng mọi kết quả hoàn toàn giống nhau. Trong dự án thật vẫn phải so response body, số lỗi, side effects và output nghiệp vụ.

## 7. Chương trình đầy đủ: tạo hai recording và so sánh bằng Java 11

Tạo file **`JfrCompareDemo.java`** như sau. Đây là chương trình **đã biên dịch và chạy bằng `javac --release 11` trên OpenJDK 21**.

Nó có ba chế độ:

- `before before.jfr`: chạy bản trước và tạo recording file.
- `after after.jfr`: chạy bản sau với cùng input và tạo file thứ hai.
- `compare before.jfr after.jfr`: đọc events trong hai file và tính median, p95, speedup; **từ chối** so sánh nếu thiếu sample, batch trùng hoặc kết quả khác nhau.

~~~java
import jdk.jfr.*;
import jdk.jfr.consumer.*;
import java.nio.file.*;
import java.time.*;
import java.util.*;
import java.util.regex.*;

public class JfrCompareDemo {
  static final int N = 1500, S = 8;
  static final String RE = "^ID-[0-9]{5}-OK$";
  static final Pattern CACHED = Pattern.compile(RE);

  @Name("lesson.Batch")
  static class Batch extends Event {
    String variant;
    int batch, items, matches;
    long checksum;
  }

  static class Result {
    int matches;
    long checksum;
  }

  static String[] input() {
    String[] a = new String[N];
    for (int i = 0; i < N; i++)
      a[i] = "ID-" + String.format(Locale.ROOT, "%05d", i)
          + (i % 7 == 0 ? "-bad" : "-OK");
    return a;
  }

  static Result work(String v, String[] a) {
    Result r = new Result();
    for (int i = 0; i < a.length; i++) {
      boolean ok = v.equals("before")
          ? Pattern.matches(RE, a[i])
          : CACHED.matcher(a[i]).matches();
      if (ok) {
        r.matches++;
        r.checksum += 31L * i + a[i].length();
      }
    }
    return r;
  }

  static void capture(String v, Path file) throws Exception {
    if (!v.equals("before") && !v.equals("after"))
      throw new IllegalArgumentException("variant");

    String[] data = input();
    Result expected = work(v, data);
    for (int i = 0; i < 5; i++) work(v, data);

    try (Recording rec =
             new Recording(Configuration.getConfiguration("default"))) {
      rec.setToDisk(true);
      rec.enable(Batch.class)
          .withThreshold(Duration.ZERO)
          .withoutStackTrace();
      rec.start();

      for (int i = 0; i < S; i++) {
        Batch e = new Batch();
        e.variant = v;
        e.batch = i;
        e.items = N;
        e.begin();
        Result r = work(v, data);
        e.end();
        e.matches = r.matches;
        e.checksum = r.checksum;
        e.commit();

        if (r.matches != expected.matches ||
            r.checksum != expected.checksum)
          throw new IllegalStateException("changed result");
      }

      rec.stop();
      rec.dump(file);
    }

    System.out.println(v + " batches=" + S
        + " items=" + N
        + " matches=" + expected.matches
        + " checksum=" + expected.checksum);
  }

  static class Stats {
    ArrayList<Long> ns = new ArrayList<>();
    int matches = -1;
    long checksum = -1;
  }

  static Stats read(Path path, String variant) throws Exception {
    Stats s = new Stats();
    boolean[] seen = new boolean[S];

    try (RecordingFile f = new RecordingFile(path)) {
      while (f.hasMoreEvents()) {
        RecordedEvent e = f.readEvent();
        if (!e.getEventType().getName().equals("lesson.Batch"))
          continue;

        int i = e.getInt("batch");
        if (!e.getString("variant").equals(variant)
            || i < 0 || i >= S || seen[i] || e.getInt("items") != N)
          throw new IllegalStateException("different load");
        seen[i] = true;

        int m = e.getInt("matches");
        long c = e.getLong("checksum");
        if (s.matches == -1) {
          s.matches = m;
          s.checksum = c;
        }
        if (m != s.matches || c != s.checksum)
          throw new IllegalStateException("different result");

        s.ns.add(e.getDuration().toNanos());
      }
    }

    if (s.ns.size() != S)
      throw new IllegalStateException("missing samples");
    return s;
  }

  static double median(Stats s) {
    long[] a = s.ns.stream().mapToLong(x -> x).sorted().toArray();
    return (a[3] / 2.0 + a[4] / 2.0) / 1000000.0;
  }

  static double p95(Stats s) {
    long[] a = s.ns.stream().mapToLong(x -> x).sorted().toArray();
    return a[7] / 1000000.0;
  }

  static void compare(Path a, Path b) throws Exception {
    Stats before = read(a, "before"), after = read(b, "after");
    if (before.matches != after.matches ||
        before.checksum != after.checksum)
      throw new IllegalStateException("not comparable");

    System.out.println("comparability=PASS");
    System.out.println("samplesEach=" + S);
    System.out.println("itemsEach=" + N);
    System.out.println("matchesEach=" + before.matches);
    System.out.println("checksumEach=" + before.checksum);

    System.out.printf(Locale.ROOT,
        "beforeMedianMs=%.3f%n", median(before));
    System.out.printf(Locale.ROOT,
        "afterMedianMs=%.3f%n", median(after));
    System.out.printf(Locale.ROOT,
        "beforeP95Ms=%.3f%n", p95(before));
    System.out.printf(Locale.ROOT,
        "afterP95Ms=%.3f%n", p95(after));
    System.out.printf(Locale.ROOT,
        "medianSpeedup=%.2fx%n", median(before) / median(after));
  }

  public static void main(String[] x) throws Exception {
    if (x.length == 2)
      capture(x[0], Path.of(x[1]));
    else if (x.length == 3 && x[0].equals("compare"))
      compare(Path.of(x[1]), Path.of(x[2]));
    else
      throw new IllegalArgumentException("args");
  }
}
~~~

### Vì sao event chỉ bọc `work`?

~~~java
e.begin();
Result r = work(v, data);
e.end();
~~~

Khoảng thời gian JFR ghi là duration của **phần work**. Tạo `Batch`, gắn các fields, gọi `commit` và ghi file `.jfr` đều nằm **ngoài boundary đo**. Như vậy ta không vô tình tính cả thời gian parse JFR vào duration của từng batch.

Dù vậy, event instrumentation và JVM vẫn có overhead, ảnh hưởng bởi scheduler, GC, JIT và runtime state. Với microbenchmark thật cần dùng JMH; chương trình ở đây phục vụ **học cách đọc/so sánh recording dưới tải đã cố định**.

### Vì sao threshold zero và tắt stack trace?

`rec.enable(Batch.class).withThreshold(Duration.ZERO).withoutStackTrace()` giữ custom duration events rất ngắn và tránh ghi thêm stacktraces không cần thiết. Cấu hình này phải **giống hệt** giữa before và after để không làm lệch overhead và event counts.

### Vì sao tạo Recording sau warm-up?

Ta chỉ muốn đo **steady-state work**, nên khởi tạo input và warm-up trước khi `rec.start()`. Nếu mục tiêu là startup performance, thiết kế khác: ghi từ JVM launcher, ví dụ `-XX:StartFlightRecording`, và xem cả class loading/JIT startup. Không dùng cách steady-state để kết luận về tốc độ khởi động.

## 8. Lệnh chạy và kết quả đã kiểm chứng

Trong thư mục có file `JfrCompareDemo.java`:

~~~bash
javac --release 11 JfrCompareDemo.java

java JfrCompareDemo before before.jfr
java JfrCompareDemo after after.jfr

jfr summary before.jfr
jfr summary after.jfr

java JfrCompareDemo compare before.jfr after.jfr
~~~

**Hai dòng output deterministic** từ hai lần capture:

~~~text
before batches=8 items=1500 matches=1285 checksum=29873800
after batches=8 items=1500 matches=1285 checksum=29873800
~~~

Hai recording được tạo bằng **hai tiến trình JVM khác nhau**. `jfr summary` trên hai file đều đếm **8 events `lesson.Batch`** trong lần thử; parser cũng kiểm mỗi batch index 0–7 xuất hiện đúng một lần, `items==1500` và kết quả business giống nhau.

**Một lần chạy thực tế của lệnh compare** trên OpenJDK 21 cho kết quả:

~~~text
comparability=PASS
samplesEach=8
itemsEach=1500
matchesEach=1285
checksumEach=29873800
beforeMedianMs=7.121
afterMedianMs=1.636
beforeP95Ms=14.725
afterP95Ms=3.069
medianSpeedup=4.35x
~~~

**Chỉ năm dòng đầu là ổn định theo input của chương trình.** Các dòng `Median`, `P95` và `speedup` **dao động giữa các lần chạy**. Những lần lặp lại đã quan sát được median before khác đáng kể, dù input/checksum không thay đổi. Không biến `4.35x` thành cam kết performance.

### Đọc đúng logic kiểm tính so sánh

Hàm `read(path, variant)` thực hiện:

1. Lọc theo `eventType.name == "lesson.Batch"`.
2. Kiểm `variant` trùng nhãn mong đợi để không hoán nhầm file.
3. Kiểm 8 batch indices nằm trong 0–7 và **không trùng**.
4. Kiểm `items == 1500` cho từng batch.
5. Kiểm `matches/checksum` giống nhau trong một run.
6. Lấy duration bằng `RecordedEvent.getDuration().toNanos()`.
7. Kiểm đúng 8 events; nếu thiếu hoặc sai thì **ném exception**.
8. Trong `compare(...)`, kiểm cả hai runs có cùng matches/checksum rồi mới tính metrics.

**Đánh dấu `comparability=PASS` không chứng minh phần cứng, cache, GC hoặc phụ thuộc bên ngoài đã giống hoàn toàn.** Nó chỉ xác nhận các điều kiện **mà code thực sự kiểm được**. Các điều kiện khác phải ghi trong test manifest và kiểm ở môi trường.

## 9. Cách hiểu median, p95 và tỷ lệ speedup

### Median

Với tám duration measurements đã sort tăng dần:

~~~text
d0 <= d1 <= d2 <= d3 <= d4 <= d5 <= d6 <= d7
median = (d3 + d4) / 2
~~~

Demo tính median từ nanoseconds rồi đổi sang milliseconds. Median thể hiện giá trị trung tâm của các batches đo được; **không tự đại diện cho toàn bộ request latency** nếu event chỉ bọc một công đoạn.

### P95 nearest-rank

Một cách tính p95 đơn giản là nearest-rank:

~~~text
index = ceil(0.95 * N) - 1
N = 8  ->  index = 7  -> p95 = max(durations)
~~~

Vì số mẫu chỉ 8, p95 của demo thực chất là **max**. Nó hữu ích để giải thích API và tính toán nhưng **không đủ độ tin cậy cho production p95/p99**. Với throughput/latency thật, cần nhiều samples và nhiều runs, thống nhất định nghĩa percentile và tránh gộp những percentiles không có raw observations.

### Tỷ lệ chênh lệch

~~~text
medianSpeedup = beforeMedianMs / afterMedianMs

medianLatencyReductionPercent
  = (beforeMedianMs - afterMedianMs) / beforeMedianMs * 100
~~~

Ví dụ số đo 7.121 ms và 1.636 ms cho tỷ lệ khoảng **4.35×** và giảm median gần **77%** trong **lần chạy đó**. Nếu sau nhiều runs kết quả không ổn định, không đủ cơ sở kết luận thay đổi có lợi. Nên báo thêm chênh lệch tuyệt đối (ms), độ dao động, khoảng tin cậy khi có phương pháp phù hợp, và các giới hạn môi trường.

### Throughput không phải nghịch đảo median

Một batch nhanh hơn 4 lần trong một luồng không đồng nghĩa một API server xử lý **4 lần request/s** với nhiều concurrent users. Queueing, DB, locks, network và GC có thể giới hạn throughput. Để kiểm throughput, đo trực tiếp số request **thành công** mỗi giây với concurrency và error rate tương đương.

## 10. Đọc JVM events để tìm nguyên nhân thay đổi

Custom event `lesson.Batch` trả lời “mất bao lâu?”. Để trả lời “vì sao?”, xem các event đã được bật trong JFR:

| Event/nhóm | Ý nghĩa | Cách đối chiếu |
| --- | --- | --- |
| `jdk.CPULoad` | CPU load tại thời điểm lấy mẫu | So cùng khoảng tải; không lấy từng sample làm CPU time |
| `jdk.ThreadCPULoad` | CPU usage của thread theo period | Xem thread quan trọng, hệ thống ngoài JVM |
| `jdk.ExecutionSample` | Sampled stack traces trong code đang chạy | Xem hot methods/call tree, tỷ trọng samples |
| `jdk.GarbageCollection` | Các sự kiện GC được ghi | Count/duration và bổ sung pause-related events |
| `jdk.ObjectAllocationSample` | Allocation sampling | Xem allocation hotspots, không coi là tổng exact |
| `jdk.JavaMonitorEnter` | Contended monitor enter khi vượt threshold | So waiting time/count theo đúng threshold |
| `jdk.JavaMonitorWait` | Thời gian thread đợi monitor | Kiểm block/notification bottlenecks |
| `jdk.ThreadPark` | Thread parking/blocking | Xem thread contention và wait sites |
| `jdk.SocketRead` / `jdk.FileRead` | I/O operations vượt threshold nếu bật | So time/bytes theo cùng workload |

Lệnh xem thử:

~~~bash
jfr print --events jdk.GarbageCollection before.jfr
jfr print --events jdk.GarbageCollection after.jfr

jfr print --events jdk.CPULoad before.jfr
jfr print --events jdk.CPULoad after.jfr
~~~

**Không hứa có events trong demo ngắn**. Nếu không có `jdk.CPULoad` vì recording chỉ ngắn vài milliseconds, cần ghi lâu hơn/đổi settings **ở cả hai phía**. Nếu không có GC event, chưa thể tuyên bố “không có cấp phát/GC pressure”.

**GC duration không luôn đồng nghĩa stop-the-world pause.** Một số collector có concurrent phases; để kết luận “GC pause giảm”, dùng đúng pause events và so với GC logs/metrics khi cần.

**ExecutionSample là sampling**, số sample khác nhau có thể do thời lượng recording khác. Đừng so raw stack count giữa before 60 giây và after 10 giây rồi suy ra cải thiện 6 lần. Hãy kiểm recording duration, sampling interval và chuẩn hóa/diễn giải tỷ lệ hợp lý.

**ObjectAllocationSample không đo từng object.** Đây là dữ liệu lấy mẫu hữu ích cho tìm hotspot, không phải total exact allocated bytes từ mọi site trong mọi cấu hình.

## 11. Chuẩn hóa theo công việc hoặc thời gian

Khi so workload thực, cần thống nhất mẫu số:

~~~text
GC events per 1,000 successful requests
  = GC event count / successful request count * 1,000

GC pause milliseconds per 1,000 requests
  = tổng relevant pause durations / successful requests * 1,000

Average bytes allocated per request (khi có metric đáng tin)
  = tổng estimated allocated bytes / successful requests

Successful throughput
  = successful request count / steady-state seconds
~~~

**Các công thức chỉ hữu ích khi mẫu số và tử số phản ánh đúng đơn vị mà bạn muốn đo**. Đừng lấy byte count của sampled event rồi gọi là “exact total heap allocations”, hoặc lấy tổng duration GC phase concurrent như tổng ứng dụng bị dừng.

Nếu hai recording có cùng thời gian nhưng một phiên đạt ít request vì chậm hơn, so events/second vẫn chưa nói rõ **cost/request**. Đôi khi cần xem **cả per-second lẫn per-operation metrics**.

## 12. Quy trình thực tế cho staging/CI

### Bước A — đặt mục tiêu trước khi chạy

Viết một đoạn test contract ngắn:

~~~text
Hypothesis: reuse Pattern reduces batch-processing time.
Builds: before=<revision A>, after=<revision B>.
Runtime: same JDK build, heap, GC and CPU quota.
Dataset: 1,500 identifiers, fixed order, known valid count.
Warm-up: 5 batches.
Measured: 8 batches per run (tutorial only).
JFR: same event settings, threshold and stacktraces.
Correctness: matches == 1,285; checksum == 29,873,800.
Decision: compare multiple independent runs, not just one speedup.
~~~

Các tên revision ở đây là **mẫu metadata cần điền khi dùng thật**, không phải file nguồn được tạo cho bài. Trong hệ thống thực nên lưu manifest đi kèm file `.jfr`: JVM flags, Git revision, dataset hash/seed, test runner version, OS, CPU, memory/GC configuration, recording settings, error metrics và timestamp.

### Bước B — chạy nhiều phiên độc lập

~~~text
Warm-up / baseline run A1 -> before-A1.jfr
Warm-up / candidate run B1 -> after-B1.jfr
Candidate run B2         -> after-B2.jfr
Baseline run A2          -> before-A2.jfr
... lặp A/B hoặc ABBA để giảm bias do thứ tự
~~~

Nếu chạy before lúc máy mát, after sau khi CPU nóng hoặc trong lúc backup, timing khác có thể không do code. Dùng nhiều runs và đảo thứ tự là tốt hơn một cặp đơn lẻ. Không cần mở cả hai phiên cùng lúc nếu chúng cùng tranh chấp CPU/disk/database.

### Bước C — kiểm file trước khi tính stats

- Hai file tồn tại, `jfr summary` đọc thành công.
- Event type có trong cả hai, cùng tên và fields tương thích.
- Cùng số samples/mẫu số hoặc có normalization rõ ràng.
- Duration không bị threshold khác nhau làm lọc mẫu.
- Không có batch trùng, event bị thiếu hoặc file đọc nhầm version.
- Kết quả business/error rates giống nhau.
- Ghi nhận nếu GC/JIT/background jobs chen vào cửa sổ đo.

### Bước D — đưa ra kết luận

Báo cáo nên gồm **before/after metric table**, số runs, phương pháp tính percentile, correctness, thay đổi tài nguyên liên quan, các yếu tố nhiễu và quyết định có giữ thay đổi không. Nếu p95 xấu đi hoặc error rate tăng, không nên chỉ dựa vào median tốt hơn để release.

## 13. JFR, JDK Mission Control, JMH và load testing

**JFR** là công cụ chẩn đoán runtime. **JDK Mission Control (JMC)** giúp xem timeline, threads, garbage collection, execution samples, memory allocation và hot methods trong recording. Với các file lớn/production, JMC thường hiệu quả hơn việc in hàng triệu dòng bằng `jfr print`.

**JMH (Java Microbenchmark Harness)** phù hợp hơn nếu mục tiêu là đo chi phí một phép toán Java rất nhỏ ở mức nano-/microseconds per operation: nó quản lý warm-up, forks, iterations và một số bẫy JIT benchmark. Ví dụ `Pattern.matches` so với cached `Pattern` rất thích hợp để xác minh lại bằng JMH nếu muốn một ước lượng microbenchmark đáng tin.

**Load tester ngoài JVM** phù hợp khi câu hỏi là throughput, request latency, concurrent load và SLO production. Client-side latency có thể khác thời gian một method ở server vì network, TLS, queueing và downstream dependencies.

Không nên nói “có JFR rồi thì không cần JMH/load test”, cũng không nên nói “JFR cho ra số CPU time chính xác của mỗi method” từ một tập sampled stacks. Chọn công cụ theo câu hỏi.

## 14. Lỗi phổ biến và cách sửa

| Nhầm lẫn | Cách đúng |
| --- | --- |
| So file size before/after để kết luận nhanh hơn | Đọc đúng event metrics và mẫu số |
| Workload khác nhau nhưng so raw event counts | Replay cùng input hoặc normalize có giải thích |
| Before chưa warm-up, after đã hot | Warm-up/phase measurement nhất quán |
| `settings=default` một bên, `profile` bên kia | Giữ cùng JFR settings và thresholds |
| Chỉ kiểm source code giống, không kiểm output | So kết quả, error/timeout rates và side effects |
| `Event.commit()` được gọi nên event chắc xuất hiện | Kiểm file thực và threshold/state |
| Dùng một file 30 giây so file 180 giây | Normalize theo op/time và recording window |
| `getStartTime()` hai JVM dùng làm latency | Dùng duration event/metric boundary đúng |
| p95 của 8 samples được gọi production p95 | Tăng samples/independent runs và ghi rõ phương pháp |
| Gộp mean của p95 thành p95 chung | Dùng raw data/histogram cùng định nghĩa |
| Execution samples coi là số lần method gọi | Đó là sampled stack evidence |
| Allocation sample coi là exact bytes | Phân biệt sampled và exact counters |
| GC event duration luôn là pause duration | Phải xét collector/phases/GC pause events |
| File JFR không có event nên bottleneck đã hết | Kiểm settings, sampling, timing và workload |
| Đọc file lớn với `RecordingFile.readAllEvents` | Dùng streaming `hasMoreEvents/readEvent` |
| Một cặp before/after có speedup là chứng minh | Lặp runs và đánh giá biến thiên |
| Sau tối ưu chạy nhanh nhưng sai dữ liệu | Correctness là yêu cầu bắt buộc |
| JFR file không có dữ liệu nhạy cảm | Giới hạn quyền và retention; kiểm custom fields |
| Dùng shared Matcher giữa threads | `Pattern` có thể reuse, `Matcher` không thread-safe |

## 15. Checklist trước khi chấp nhận một thay đổi hiệu năng

- [ ] Có giả thuyết và metric mục tiêu rõ ràng.
- [ ] Cùng input, seed, load shape, concurrency và số công việc.
- [ ] Cùng JDK, JVM flags, heap/GC, CPU/memory limits và các dependencies.
- [ ] Warm-up và khoảng ghi JFR nhất quán.
- [ ] Hai file có cùng event types/fields, threshold và sampling settings.
- [ ] File mở được, đủ samples, không batch trùng hoặc thiếu.
- [ ] Before/after cho cùng business output và error rate không tăng.
- [ ] Metric dùng cùng đơn vị: ms/batch, ms/request, bytes/op hoặc events/s.
- [ ] Duration tính đúng từ `RecordedEvent.getDuration()` ở boundary cần đo.
- [ ] Median/p95 được tính theo cùng phương pháp và số mẫu đủ lớn cho kết luận.
- [ ] Có nhiều independent runs, xem noise/JIT/GC và thứ tự A/B.
- [ ] Khi cần tìm nguyên nhân, đọc GC/CPU/allocation/lock/I/O events có ý nghĩa.
- [ ] Không xem JFR sampling là số đo exact của từng method.
- [ ] Với microbenchmark dùng JMH; với API SLO dùng load testing phù hợp.
- [ ] Bảo vệ `.jfr`, tránh rò rỉ PII/secrets, giới hạn quyền đọc và retention.
- [ ] Có tiêu chí quyết định, nhận diện trade-off và kế hoạch rollback.

**Kết luận:** Khi dùng JFR để so sánh trước/sau, **cùng kịch bản tải** và **đầu ra đúng** quan trọng không kém kỹ thuật đọc file. Hãy kiểm cả số lượng công việc, event settings, duration measurements, thành phần CPU/GC/IO và biến thiên qua nhiều runs. Một `medianSpeedup` cao trong một lần chạy chỉ là **dấu hiệu cần xác minh**, không phải lời khẳng định về mọi môi trường production.

## Tài liệu chính thức và hiện hành

- [OpenJDK JEP 328 — Flight Recorder](https://openjdk.org/jeps/328): JFR trong OpenJDK 11.
- [Oracle Java SE 11 — RecordingFile](https://docs.oracle.com/en/java/javase/11/docs/api/jdk.jfr/jdk/jfr/consumer/RecordingFile.html): `hasMoreEvents()`, `readEvent()`, `readAllEvents()` và lưu ý về file lớn/nguồn tin cậy.
- [Oracle Java SE 11 — RecordedEvent](https://docs.oracle.com/en/java/javase/11/docs/api/jdk.jfr/jdk/jfr/consumer/RecordedEvent.html): duration và event metadata.
- [Oracle Java SE 11 — RecordedObject](https://docs.oracle.com/en/java/javase/11/docs/api/jdk.jfr/jdk/jfr/consumer/RecordedObject.html): typed access `getInt`, `getLong`, `getString`.
- [Oracle Java SE 11 — Recording](https://docs.oracle.com/en/java/javase/11/docs/api/jdk.jfr/jdk/jfr/Recording.html): `enable`, `start`, `stop`, `dump` và disk policy.
- [Oracle Java SE 11 — Event](https://docs.oracle.com/en/java/javase/11/docs/api/jdk.jfr/jdk/jfr/Event.html): `begin`/`end`/`commit`.
- [Oracle Java SE 11 — EventSettings](https://docs.oracle.com/en/java/javase/11/docs/api/jdk.jfr/jdk/jfr/EventSettings.html): threshold và stack trace.
- [Oracle Java SE 11 — Troubleshoot Performance Issues Using Flight Recorder](https://docs.oracle.com/en/java/javase/11/troubleshoot/troubleshoot-performance-issues-using-jfr.html): CPU, GC, thread, I/O, sampling và event threshold.
- [Oracle Java SE 25 — RecordingFile](https://docs.oracle.com/en/java/javase/25/docs/api/jdk.jfr/jdk/jfr/consumer/RecordingFile.html): consumer API vẫn được duy trì trên JDK hiện đại.
- [Oracle JDK 25 — jfr](https://docs.oracle.com/en/java/javase/25/docs/specs/man/jfr.html): `summary`/`print`.
- [Oracle JDK Mission Control](https://www.oracle.com/java/technologies/jdk-mission-control.html): phân tích JFR timeline, hot methods, GC, threads, memory.
- [OpenJDK JMH](https://github.com/openjdk/jmh): framework dành cho Java microbenchmark.

Bài học chỉ dùng **kiến thức Java 11+ hiện còn áp dụng**, không dựa vào JFR commercial/legacy flags. Chương trình đã kiểm chứng bằng OpenJDK 21 với `javac --release 11`, đọc được `before.jfr` và `after.jfr`, xác nhận tám sự kiện ở mỗi file, 1.285 matches và checksum 29.873.800. Giá trị thời gian của một lần chạy chỉ mang tính minh họa, không phải kết quả phổ quát.