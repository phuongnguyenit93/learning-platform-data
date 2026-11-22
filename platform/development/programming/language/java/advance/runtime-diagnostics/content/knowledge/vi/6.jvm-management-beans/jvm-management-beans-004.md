# 6.4 GarbageCollectorMXBean cho số lần, thời gian GC và giới hạn của số liệu tổng

Trong Java runtime diagnostics, câu hỏi “GC có nhiều quá không?” thường dẫn tới hai số dễ lấy: **số lần thu gom** và **thời gian dành cho thu gom**. Java cung cấp giao diện chuẩn `java.lang.management.GarbageCollectorMXBean` để đọc hai giá trị tích lũy ấy từ JVM đang chạy. Tuy nhiên, chúng chỉ là **bộ đếm tổng hợp**. Chúng không kể được một sự kiện GC kéo dài bao nhiêu, request nào chịu ảnh hưởng, thời gian nào là stop-the-world (STW), vì sao GC xuất hiện, hay tại sao heap tăng.

Ví dụ: một bean báo `getCollectionCount() = 200` và `getCollectionTime() = 3_000`. Không thể kết luận ứng dụng “tạm dừng 3 giây”, “mỗi pause đúng 15 ms”, “GC chiếm 15% CPU” hoặc “p99 latency là 15 ms”. Cần biết bean thuộc collector nào, chỉ số này được JVM định nghĩa ra sao, thời gian đo từ bao giờ và hai ảnh chụp có thuộc **cùng một JVM instance** hay không.

Bài này hướng dẫn cách tìm `GarbageCollectorMXBean`, đọc chính xác hai phương thức, tính **delta theo cửa sổ đo**, xử lý `-1` và reset, tránh diễn giải sai thống kê tổng, đối chiếu nhiều collectors và bổ sung GC logs/JFR/metrics khi cần dữ liệu sự kiện. Ví dụ Java 17+ có cả phần kết quả **xác định** để kiểm chứng và chế độ đọc số liệu **thực tế, thay đổi theo JVM**.

## 1. Vị trí của GarbageCollectorMXBean trong hệ sinh thái MXBeans

### 1.1 MXBean cung cấp giao diện quản trị JVM

MXBean (management bean) là giao diện quản lý/quan sát cho các đối tượng runtime. Trong module `java.management`, `GarbageCollectorMXBean` đại diện cho **một bộ thu gom rác** mà JVM công bố. Nó kế thừa `MemoryManagerMXBean` và `PlatformManagedObject`; do đó bên cạnh số lần và thời gian GC, nó còn có tên, thông tin memory pools và `ObjectName` trong JMX.

Một JVM có thể có **một hoặc nhiều** collector beans; số lượng, tên và ý nghĩa từng bean phụ thuộc implementation, thuật toán GC, cấu hình và phiên bản. Không viết code luôn giả định có đúng hai bean là “Young” và “Old”.

Các cách lấy bean phổ biến:

```java
import java.lang.management.GarbageCollectorMXBean;
import java.lang.management.ManagementFactory;
import java.util.List;

List<GarbageCollectorMXBean> collectors =
        ManagementFactory.getGarbageCollectorMXBeans();
```

Đây là **đoạn minh họa cần đặt trong một method/class**; chương trình độc lập có đầy đủ ở phần thực hành. Danh sách lấy từ JVM **đang thực thi đoạn code**. Nó không tự truy vấn JVM khác bằng PID; để đọc từ xa qua JMX cần kết nối/phân quyền theo cơ chế quản lý phù hợp.

### 1.2 Thuộc tính nhận dạng và mối liên hệ với memory pools

| API | Trả về | Dùng để làm gì? | Giới hạn |
| --- | --- | --- | --- |
| `getName()` | `String` | Tên collector do JVM công bố | Tên có thể khác giữa collector/JDK/vendor |
| `getObjectName()` | `ObjectName` | Định danh JMX của bean, dạng `java.lang:type=GarbageCollector,name=...` | Không phải định danh bền vững qua các JVM/restart |
| `getMemoryPoolNames()` | `String[]` | Tên memory pools mà memory manager quản lý | Không cho biết số byte được thu hồi của mỗi lần GC |
| `isValid()` | `boolean` | Bean/manager còn hợp lệ theo JVM không | Không phản ánh chất lượng latency hay health của service |
| `getCollectionCount()` | `long` | Số lần GC tích lũy, nếu được định nghĩa | Có thể `-1`; không có thời điểm từng lần |
| `getCollectionTime()` | `long`, đơn vị **ms** | Thời gian GC tích lũy gần đúng, nếu được định nghĩa | Có thể `-1`; không phải pause histogram |

Tên collector là **nhãn do runtime cung cấp**, không phải bằng chứng độc lập rằng bean thuộc một thế hệ cố định. Trên một số HotSpot collector, có thể gặp tên kiểu “G1 Young Generation” và “G1 Old Generation”; ở cấu hình khác, có thể là bean khác hoặc số lượng khác. Code nên duyệt danh sách và **ghi đúng tên thực tế**, không tự ghép nhãn Young/Old bằng tên giả định.

### 1.3 Có sẵn qua Java API và JMX

`ManagementFactory.getGarbageCollectorMXBeans()` lấy danh sách trong tiến trình hiện tại. Cùng các bean đó có thể được expose qua **platform MBeanServer**, với ObjectName dạng `java.lang:type=GarbageCollector,name=<collector-name>`.

JMX từ xa có thể cho hệ thống giám sát truy vấn các thuộc tính, nhưng phải cấu hình quyền, kết nối và bảo mật riêng; **không bật JMX remote công khai, không dùng cấu hình xác thực yếu chỉ để xem GC**. Trên ứng dụng đã có exporter (Micrometer/JMX exporter), dữ liệu có thể được chuyển thành time series, cần kiểm tra naming và semantics của exporter thay vì tưởng metric nào cũng tương ứng 1:1 với phương thức Java.

## 2. Hiểu chính xác getCollectionCount()

Tài liệu Java SE 21 mô tả `getCollectionCount()` là **tổng số lần collection đã xảy ra** cho collector này. Kiểu trả về `long` nhưng **`-1` nghĩa là không xác định** đối với collector đó.

Ví dụ:

```java
long count = bean.getCollectionCount();
if (count == -1L) {
    // Count không được collector này cung cấp.
} else {
    // Count là số lần tích lũy được JVM công bố.
}
```

Đoạn trên cần có biến `bean` kiểu `GarbageCollectorMXBean` trong scope; nó minh họa cách kiểm tra giá trị, không phải chương trình chạy độc lập.

### 2.1 Đây là counter, không phải tốc độ

Giả sử collector A có count:

| Thời điểm | `getCollectionCount()` |
| --- | ---: |
| 10:00:00 | 120 |
| 10:00:30 | 128 |

Trong cửa sổ 30 giây, **8 lần collection đã được ghi nhận**. Tần suất quan sát xấp xỉ `8 / 30 = 0,267 collection/giây`, tương đương khoảng `16 collection/phút`. Đây là **rate trung bình theo cửa sổ**, không phải một nhịp đều “3,75 giây chắc chắn GC một lần”. Tám sự kiện có thể dồn ở đầu, cuối hoặc phân bố không đồng đều.

Không gọi số 128 là “số GC trong 30 giây”: đó là counter tích lũy. Để lấy số lượng trong cửa sổ phải trừ hai ảnh chụp **của cùng collector/cùng process instance**.

### 2.2 Không có nghĩa “mỗi object được giải phóng là một GC”

Một collection có thể thu hồi nhiều object, ít object hoặc tiến hành các bước có ý nghĩa khác nhau tùy thuật toán. Count **không đếm** số object đã dọn, số byte reclaimed, số allocation, lần finalization hay số request bị block. Muốn đánh giá hiệu quả thu hồi heap, cần dữ liệu memory usage trước/sau GC hoặc số liệu theo pool; một count nhỏ vẫn có thể đi kèm một lần GC kéo dài, trong khi count lớn có thể là nhiều lần GC nhanh.

### 2.3 Không mặc định count giống nhau giữa các collector

Young/old GC, G1, Parallel, Serial, ZGC, Shenandoah hoặc collector thế hệ mới có cơ chế pha, chu kỳ và cách công bố beans khác nhau. Một “collection” được count ở bean này không nhất thiết cùng loại công việc với một collection ở bean khác. Do đó:

- So count giữa **hai cấu hình giống nhau** hữu ích hơn so raw count giữa hai GC algorithms khác nhau.
- Khi đổi collector hoặc nâng JDK, baseline count có thể thay đổi vì **semantics quan sát khác**, chưa chắc do workload hay code lỗi.
- Không lấy count của từng bean cộng lại rồi gọi tuyệt đối là “số lần ứng dụng dừng vì GC”. Các cycles/phases có thể không tương ứng một-một với pause events.

## 3. Hiểu chính xác getCollectionTime()

Tài liệu Java SE 21 định nghĩa `getCollectionTime()` là **approximate accumulated collection elapsed time in milliseconds**: thời gian trôi qua tích lũy **gần đúng** cho các collection của collector đó, đơn vị mili giây. `-1` nghĩa là thời gian collection **không được định nghĩa** cho collector đó.

```java
long timeMs = bean.getCollectionTime();
if (timeMs == -1L) {
    // Không thể lấy elapsed GC time từ bean này.
}
```

JVM có thể dùng đồng hồ độ phân giải cao hơn để đo rồi quy đổi sang mili giây. Vì vậy count **có thể tăng trong khi timeMs không đổi**, nếu collection quá ngắn để làm thay đổi con số hiển thị ở đơn vị ms. Đây là hành vi được API docs đề cập, không tự chứng minh công cụ hỏng.

### 3.1 Time tích lũy không phải timestamp và không phải duration của event cuối

Ví dụ giả định:

| Thời điểm | Count | Collection time (ms) |
| --- | ---: | ---: |
| 10:00:00 | 120 | 2.400 |
| 10:00:30 | 128 | 2.560 |

Kết quả delta: **8 lần** và **160 ms accumulated collection elapsed time** trong cửa sổ 30 giây. Điều này **không** cho biết các event kéo dài `20 ms` đều nhau. Nếu lấy `160 / 8 = 20 ms`, con số là **trung bình báo cáo theo collector** cho cửa sổ, không phải p95/p99 pause hay độ trễ của request.

Không nhầm:

- `getCollectionTime()` = tổng thời gian tích lũy gần đúng do collector báo;
- `System.nanoTime()` = nguồn đo thời gian trôi qua giữa hai thời điểm bên trong cùng JVM;
- timestamp UTC của log/JFR = thời điểm gắn cho **mỗi sự kiện**;
- CPU time của các GC worker threads = tổng CPU bị tiêu thụ trên các lõi, không phải metric này.

### 3.2 “Elapsed collection time” không mặc định là stop-the-world pause time

Điểm rất quan trọng: **Java SE không định nghĩa phương thức này là tổng thời gian ứng dụng bị dừng**. JVM/collector có thể thực hiện công việc GC concurrent với application threads hoặc có nhiều pha. Cách hạch toán elapsed collection time là **phụ thuộc implementation**. Do đó không nên diễn giải:

```text
delta(getCollectionTime) = tổng thời gian pause gây trễ request
```

đó là một đẳng thức **không được API bảo đảm**.

Ngay cả khi JVM cụ thể có báo thời gian tương quan gần với một số pause, muốn kết luận nguyên nhân latency cần **event-level timing + timestamp** và ứng dụng metrics/traces cùng cửa sổ. Khi chuyển G1 sang ZGC hoặc thay JDK, ý nghĩa “GC time” trong dashboard phải được rà soát lại, không mang nhãn “STW time” bất biến.

### 3.3 Vì sao tổng thời gian có thể lớn hơn hoặc bằng 0 dù count khác kỳ vọng?

- Count tăng mà timeMs không tăng: event quá ngắn so với độ phân giải báo cáo, hoặc cách JVM xuất counter/time khác nhau.
- Count bằng 0 trong cửa sổ: chưa có collection được ghi nhận cho bean đó; không có nghĩa không có GC-related CPU work hoặc mọi thread đều không bị pause vì nguyên nhân khác.
- TimeMs có thể tăng trong khi cách đếm collection không phản ánh chi tiết các pha; cần đối chiếu implementation trước khi kết luận.
- Counter/time bằng `-1`: **undefined**, không phải một lượng âm, không phải error ratio và không được cộng vào tổng.
- Giá trị lấy trong hai câu gọi liên tiếp có thể thuộc những thời điểm hơi khác nhau, nhất là khi có GC đang diễn ra.

## 4. Từ số tích lũy đến metric theo cửa sổ đo

Trong điều tra performance, hai điểm đo **đủ gần về ngữ cảnh** mới có ý nghĩa. Ghi cùng run ID, PID/process start time, collector ObjectName/name, JDK version, GC algorithm và window.

### 4.1 Công thức delta cơ bản

Gọi:

- `C0`, `C1` là `getCollectionCount()` tại đầu/cuối cửa sổ.
- `T0`, `T1` là `getCollectionTime()` (ms) tại đầu/cuối.
- `W` là thời gian thực tế giữa hai lần lấy mẫu tính bằng giây.

Nếu cả bốn counter được định nghĩa và không giảm:

```text
collections_in_window = C1 - C0
gc_elapsed_ms_in_window = T1 - T0

collection_rate_per_second = (C1 - C0) / W

if C1 - C0 > 0:
    mean_reported_elapsed_ms_per_collection = (T1 - T0) / (C1 - C0)
else:
    mean_reported_elapsed_ms_per_collection = UNDEFINED
```

Đây là phép biến đổi của hai counter tích lũy. Chúng **không tái tạo histogram pause** và không thể phục hồi timestamp của từng GC.

### 4.2 Đo thời gian cửa sổ bằng đồng hồ đơn điệu

Trong cùng JVM, sử dụng `System.nanoTime()` để tính elapsed time; đừng lấy hiệu hai `System.currentTimeMillis()` cho cửa sổ rất ngắn khi wall-clock có thể chỉnh đồng bộ. Khi giám sát từ xa, dùng timestamp đáng tin của collector và ghi timezone; tránh lấy elapsed từ đồng hồ khác máy mà chưa đồng bộ.

Lưu ý hai phương thức `getCollectionCount()` và `getCollectionTime()` **không tạo một snapshot nguyên tử**. Khi một GC vừa hoàn thành giữa hai lệnh gọi, count có thể đã được cập nhật nhưng time chưa được quan sát đồng thời. Với cửa sổ dài và sampling hợp lý, sai số tương đối nhỏ hơn; với cửa sổ sát mức mili giây, sai số/nhiễu có thể rất lớn. Nếu cần số liệu sự kiện chính xác, dùng nguồn event-level.

### 4.3 Một số liệu tỷ lệ dễ bị đặt tên sai

Người ta thường tính:

```text
reported_gc_time_ratio = delta_collection_time_ms / elapsed_window_ms
reported_gc_time_percent = 100 * reported_gc_time_ratio
```

Giả sử trong cửa sổ **30.000 ms**, collector báo tăng **150 ms**: tỷ lệ báo cáo bằng **0,5%**. Con số này chỉ là **tỷ số giữa collection elapsed time do bean báo và wall time của cửa sổ**. Nó **không được tự động gọi** “% CPU spent on GC”, “% thời gian application threads bị dừng”, “GC overhead chuẩn cho mọi JVM” hoặc “mức độ ảnh hưởng người dùng”.

Khi nhiều collector beans có khả năng hạch toán các khoảng thời gian chồng lấn hoặc công việc concurrent, **tổng các time delta** có thể không tương ứng với một tổng thời gian độc lập trên trục wall-clock. Tỷ lệ tổng có thể khó diễn giải và thậm chí vượt một ngưỡng trực giác. **Không ép kết quả về 100%** để tạo một biểu đồ đẹp nếu semantics chưa được xác minh.

### 4.4 Phân biệt các mẫu đo

| Kiểu số | Nguồn | Cách đọc |
| --- | --- | --- |
| `C1` | Counter ở thời điểm cuối | Tổng theo lifetime/định nghĩa JVM, **không phải** rate |
| `C1 - C0` | Hai counter cùng bean | Số collection được báo trong cửa sổ |
| `T1 - T0` | Hai time counters | Tổng tăng **elapsed** gần đúng (ms) |
| `(C1 - C0) / W` | Counter delta / wall seconds | Collection rate trung bình |
| `(T1 - T0) / (C1 - C0)` | Delta time / delta count | Trung bình *thời gian được báo* cho các collection; không phải pause percentile |
| p95 GC pause | Phân bố các pause events | **Không suy ra được** từ count và total time |
| Total GC worker CPU | Counters về GC CPU, nếu có | **Không đồng nhất** với getCollectionTime |
| Heap used after GC | Memory pools/JFR/GC logs | Chưa có trong hai counter này |

## 5. Bài toán số minh họa: vì sao “trung bình GC” dễ gây hiểu nhầm

Giả sử hai chuỗi **giả định** có cùng count và tổng elapsed time:

```text
Cửa sổ A: 10 lần GC; durations = 10,10,10,10,10,10,10,10,10,10 ms
Cửa sổ B: 10 lần GC; durations = 1,1,1,1,1,1,1,1,1,91 ms

Cả hai: count_delta = 10; time_delta = 100 ms
Trung bình theo tổng/count: 10 ms
```

Nhưng phân bố hoàn toàn khác: A ổn định 10 ms, B có một event 91 ms có thể ảnh hưởng tail latency. `GarbageCollectorMXBean` chỉ có hai tổng nên **không phân biệt được A với B**. Không có cách toán học khôi phục p99, max hoặc tail shape từ đúng hai tổng ấy.

Hơn nữa, ở collector concurrent, “duration” do bean hạch toán có thể không phải pause duration; ví dụ trên là **mô hình số học**, không khẳng định từng GC event của mọi implementation là một STW pause.

### 5.1 Tính tổng theo nhiều bean còn có thêm vấn đề

Giả sử JVM báo hai beans:

| Bean | Δcount | ΔcollectionTime (ms) |
| --- | ---: | ---: |
| Collector X | 8 | 80 |
| Collector Y | 1 | 120 |

Bạn có thể **trình bày riêng**: X có tám collection, 80 ms elapsed tăng; Y có một collection, 120 ms elapsed tăng. Nhưng **không được vội** kết luận ứng dụng có đúng 9 khoảng pause khác nhau, tổng paused time 200 ms hay p95 pause là 120 ms. Các beans có thể khác scope công việc và định nghĩa; cần chứng minh những đại lượng ấy có thể cộng không trùng lặp trong implementation cụ thể.

Trong monitoring, giữ nhãn `collector_name`/`object_name` thay vì gộp vô danh. Khi số bean thay đổi sau JDK upgrade, dashboard phải xử lý nhãn mới và ghi version để không so các chuỗi khác semantics.

## 6. Ví dụ Java 17+ chạy độc lập: delta chính xác và snapshot thật

Ví dụ dưới đây có hai chế độ:

- **Mặc định:** dùng bộ số liệu giả định để trình bày phép trừ và kết quả stdout **cố định**, kiểm tra được.
- **`--live`:** chụp hai ảnh của các `GarbageCollectorMXBean` trong chính JVM đang chạy chương trình, cách nhau khoảng một giây, in delta thực tế **không thể dự đoán trước**.

Chương trình **không gọi `System.gc()`**, không cố tạo áp lực heap để “ép một con số đẹp”, không đọc JVM khác và không in dữ liệu nhạy cảm. Nó xử lý `-1` và counter giảm bằng cách đánh dấu không đủ cơ sở tính delta.

Lưu tệp `GcMxBeanWindowDemo.java`:

```java
import java.lang.management.GarbageCollectorMXBean;
import java.lang.management.ManagementFactory;
import java.util.List;
import java.util.Locale;

public class GcMxBeanWindowDemo {
    record Snapshot(long count, long elapsedMs) {}
    record Delta(long collections, long elapsedMs) {}

    static Snapshot read(GarbageCollectorMXBean bean) {
        return new Snapshot(bean.getCollectionCount(), bean.getCollectionTime());
    }

    static Delta difference(Snapshot before, Snapshot after) {
        if (before.count() < 0 || before.elapsedMs() < 0
                || after.count() < 0 || after.elapsedMs() < 0
                || after.count() < before.count()
                || after.elapsedMs() < before.elapsedMs()) {
            return null; // Undefined, reset hoặc không cùng chuỗi counter.
        }
        return new Delta(
                after.count() - before.count(),
                after.elapsedMs() - before.elapsedMs());
    }

    static void showSynthetic() {
        Snapshot before = new Snapshot(10, 250);
        Snapshot after = new Snapshot(13, 310);
        Delta d = difference(before, after);

        // d không null vì bộ số liệu cố định hợp lệ.
        System.out.println("SYNTHETIC_GC_COUNT_DELTA=" + d.collections());
        System.out.println("SYNTHETIC_GC_ELAPSED_MS_DELTA=" + d.elapsedMs());
        System.out.printf(Locale.ROOT,
                "SYNTHETIC_MEAN_REPORTED_MS=%.1f%n",
                d.elapsedMs() * 1.0 / d.collections());
        System.out.printf(Locale.ROOT,
                "SYNTHETIC_REPORTED_TIME_RATIO_PCT=%.1f%n",
                100.0 * d.elapsedMs() / 1000.0);
    }

    static void showLive() throws InterruptedException {
        List<GarbageCollectorMXBean> beans =
                ManagementFactory.getGarbageCollectorMXBeans();
        Snapshot[] before = new Snapshot[beans.size()];
        Snapshot[] after = new Snapshot[beans.size()];

        long startNanos = System.nanoTime();
        for (int i = 0; i < beans.size(); i++) {
            before[i] = read(beans.get(i));
        }

        Thread.sleep(1000);

        for (int i = 0; i < beans.size(); i++) {
            after[i] = read(beans.get(i));
        }
        double windowMs = (System.nanoTime() - startNanos) / 1_000_000.0;

        System.out.println("LIVE_COLLECTOR_BEANS=" + beans.size());
        System.out.printf(Locale.ROOT, "LIVE_WINDOW_MS=%.1f%n", windowMs);
        for (int i = 0; i < beans.size(); i++) {
            GarbageCollectorMXBean bean = beans.get(i);
            Delta d = difference(before[i], after[i]);
            String identity = bean.getObjectName().toString();
            if (d == null) {
                System.out.println("LIVE " + identity
                        + " COUNT_OR_TIME_UNDEFINED_OR_DECREASED");
            } else {
                System.out.println("LIVE " + identity
                        + " count_delta=" + d.collections()
                        + " elapsed_ms_delta=" + d.elapsedMs());
            }
        }
    }

    public static void main(String[] args) throws InterruptedException {
        showSynthetic();
        if (args.length == 1 && "--live".equals(args[0])) {
            showLive();
        }
    }
}
```

Biên dịch và chạy phần kiểm tra số học, bằng Java 17+:

```bash
javac GcMxBeanWindowDemo.java
java GcMxBeanWindowDemo
```

**Stdout chính xác** của chế độ mặc định:

```text
SYNTHETIC_GC_COUNT_DELTA=3
SYNTHETIC_GC_ELAPSED_MS_DELTA=60
SYNTHETIC_MEAN_REPORTED_MS=20.0
SYNTHETIC_REPORTED_TIME_RATIO_PCT=6.0
```

Giải thích: hai ảnh chụp giả định có delta count `13 - 10 = 3` và delta time `310 - 250 = 60 ms`. Trung bình **báo cáo** `60 / 3 = 20,0 ms/collection`. Nếu cửa sổ dài đúng 1.000 ms theo giả định, tỷ lệ thời gian báo cáo là `60 / 1.000 × 100 = 6,0%`. **6% này không phải CPU % và không được khẳng định là STW pause %.**

Chạy phiên đọc bean của **JVM demo**:

```bash
java GcMxBeanWindowDemo --live
```

Bốn dòng `SYNTHETIC_...` vẫn giữ nguyên, sau đó xuất hiện các dòng `LIVE_...` phụ thuộc JVM thật. Ví dụ cấu trúc đầu ra:

```text
LIVE_COLLECTOR_BEANS=<number-of-beans>
LIVE_WINDOW_MS=<observed-elapsed-milliseconds>
LIVE java.lang:type=GarbageCollector,name=<collector> count_delta=<delta> elapsed_ms_delta=<delta>
```

Khối trên là **mô tả cấu trúc, không phải stdout cố định**. Tên và số beans, thời gian đo, count/time delta đều biến thiên. Nếu chương trình quá ngắn hoặc chưa phát sinh GC trong cửa sổ, delta có thể bằng 0. Một collector không định nghĩa metric có thể in `COUNT_OR_TIME_UNDEFINED_OR_DECREASED`.

### 6.1 Vì sao bản thực hành không cộng tất cả collectors?

Chương trình cố ý in riêng từng ObjectName. Việc cộng có thể tiện cho dashboard nhưng cần xác minh có thể cộng không trùng lặp và mỗi số đại diện loại công việc nào. Ngoài ra, các getter được đọc lần lượt, **không phải một snapshot toàn JVM nguyên tử**. Một collector có thể ghi sự kiện khi chương trình đang lấy mẫu bean khác.

### 6.2 Vì sao thời gian LIVE_WINDOW_MS chỉ xấp xỉ?

Trong code, đồng hồ `System.nanoTime()` bao cả thời gian đọc đầu, ngủ và đọc cuối. Thời gian này đo “mất bao lâu để thực hiện lượt sampling” chứ **không bảo đảm chính xác cùng một cửa sổ cho từng bean**; getter được gọi ở những thời điểm riêng. Với sampling khoảng một giây, chú ý scheduling và độ phân giải ms. Trong một monitoring pipeline thật, ghi timestamp từng sample và cấu hình cadence/clock chính xác hơn.

### 6.3 Bổ sung cách xử lý window không hợp lệ

Hàm `difference` trả `null` nếu:

- Một trong các số trước/sau là `-1` hoặc âm.
- Counter/time ở mẫu sau **nhỏ hơn** mẫu trước.

Việc giảm có thể là reset/restart, thay đổi collector/JVM hoặc nguồn dữ liệu không liên tục. Không gọi ngay “GC có count âm” hoặc cộng delta âm vào rate. Trong một pipeline giám sát, cần phân biệt restart bằng process start time/instance ID và áp dụng chính sách counter reset thích hợp. Chương trình demo đọc **chính nó** trong cùng process nên tránh được phần lớn nhầm PID, nhưng vẫn minh họa phép kiểm tra cần có khi xử lý số liệu ngoài.

## 7. Thu thập trong monitoring: căn chỉnh tên bean, mốc thời gian và counter reset

### 7.1 Định danh cặp counter bằng collector và JVM instance

Nếu giám sát nhiều JVM, một time series GC hợp lệ nên có tối thiểu các nhãn hoặc metadata:

- **Workload/JVM instance:** service, pod/container/host scope, process startup epoch hoặc instance ID, version.
- **Collector identity:** `getName()` hay ObjectName, giữ nguyên khi đọc counter của đúng bean.
- **Metric và đơn vị:** count (lần), time (milliseconds), rate (events/second), elapsed ratio (phân số/%) nếu thực sự tính.
- **Sampling window:** timestamp UTC và scrape interval, missing data, restart markers.
- **Collector/JDK:** GC algorithm, JVM implementation/version, flags quan trọng và workload nếu dùng để so performance.

PID hữu ích để tìm process tại một thời điểm, nhưng có thể tái sử dụng và trùng giữa containers. Đừng coi `PID=1` là một JVM duy nhất xuyên suốt mọi lần deploy.

### 7.2 Counter bắt đầu lại khi JVM restart

Hai giá trị tích lũy đại diện JVM hiện tại; JVM khác có lifetime counters khác, ngay cả khi dùng cùng service và pod name. Nếu thấy:

```text
T0 count=800; elapsedMs=21000
T1 count=12;  elapsedMs=300
```

phép trừ cho số âm không có nghĩa GC “đảo ngược”. Có khả năng service restart hoặc series bị nối nhầm. Cần kiểm tra process start time, deployment/restart events và collector identity rồi mới mở một cửa sổ đo mới. **Không gộp thời gian trước/sau restart thành một delta đơn giản**.

Một hệ thống như Prometheus có các hàm xử lý counter reset, nhưng vẫn phải đảm bảo metric thực sự là counter, nhãn JVM instance đúng và scrape interval đủ. Đừng tự chia `getCollectionCount()` cho uptime rồi gọi đó là rate ở thời điểm hiện tại: đó chỉ là **average rate kể từ startup**, dễ giấu spike ngắn.

### 7.3 Dữ liệu -1: số không xác định phải biểu diễn rõ

Nếu một bean trả `getCollectionCount() = -1`, exporter nên đánh dấu **not available/undefined** theo hợp đồng metric. Những cách xử lý sai:

- Thay `-1` bằng 0 rồi dashboard diễn giải “không GC”.
- Tính delta `-1 - 20` rồi ghi “-21 collections”.
- Cộng `-1` vào tổng bean khác.
- Giữ lại giá trị cuối cùng mãi không ghi mất dữ liệu.

Một lựa chọn là bỏ sample không hợp lệ khỏi series kèm metric “availability”, hoặc báo `NaN` theo semantics của hệ thống, nhưng không biến thiếu số liệu thành thành công. Với time counter undefined mà count vẫn có giá trị, **vẫn có thể theo dõi count**, không tự suy ra time.

### 7.4 Chọn chu kỳ lấy mẫu và xử lý sự kiện ngắn

Thu quá thưa có thể bỏ mất shape spike (chỉ thấy tổng 1 phút); thu quá dày làm tăng overhead và khuếch đại vấn đề **getter không nguyên tử, thời gian tròn về ms, không có event**. Chọn khoảng đo dựa vào mục tiêu: 10–30 giây cho dashboard tổng quan có thể chấp nhận ở một số hệ thống; với điều tra pause vài chục ms, sampling counter dù mỗi giây vẫn **không tái tạo được độ dài từng pause**.

Cửa sổ GC counters nên đi cùng **latency count/histogram, throughput, error, heap used, allocation rate, CPU/cgroup** cùng mốc thời gian. Nếu muốn chứng minh GC gây spike p99, phải có event-level data và trace/request timing, không chỉ hai counter delta gần đó.

## 8. Không thể suy ra gì từ hai số tổng?

### 8.1 Không có p50, p95, p99 hoặc max GC pause

Hai aggregate chỉ đủ tính count và tổng thời gian báo cáo. Tất cả phân bố có cùng count/tổng cho kết quả bean như nhau. Do đó:

- Không suy p99 pause từ `getCollectionTime / getCollectionCount`.
- Không suy “worst pause” từ tổng elapsed.
- Không kết luận GC smooth chỉ vì average nhỏ.
- Không dùng mean collection elapsed để thay SLO latency của API.

Muốn percentile, cần quan sát **từng pause/event** hoặc histogram từ nguồn đáng tin.

### 8.2 Không xác định thời điểm một collection diễn ra

`getCollectionCount()` không mang timestamp từng sự kiện. Nếu trong phút 10:00–10:01 có 20 collections, không biết chúng tập trung khi traffic peak lúc nào. Khi latency p99 tăng ở 10:00:45, counter delta phút đó chỉ cho phép đặt **giả thuyết**, không chứng minh sự kiện GC trùng 10:00:45. GC logs/JFR/notification giúp giải quyết câu hỏi thời gian.

### 8.3 Không phân biệt cause, phase, type và object reclamation

Count/time không có sẵn:

- GC cause: allocation failure, metadata threshold, explicit GC, periodic cycle, v.v.
- Young pause/remark/cleanup/mixed/full theo semantics thực tế.
- Trước/sau GC có bao nhiêu byte used, reclaimed, committed.
- Từng memory pool tăng/giảm, promotion, allocation rate hay humongous regions.
- Công việc concurrent, thread parallelism, CPU GC worker và heap pressure.

Tên bean có thể gợi loại collector nhưng **không thay thế event metadata**. Số count tăng không chứng minh GC là vì thiếu heap; một JVM khỏe vẫn GC thường xuyên.

### 8.4 Không nói được bao nhiêu CPU core bận làm GC

GC có thể dùng nhiều worker threads song song, nên **elapsed time** và **CPU time** là hai đại lượng khác nhau. Ví dụ giả định 20 ms wall với bốn worker bận đồng thời có thể tương ứng nhiều hơn 20 ms tổng CPU, nhưng thực tế còn scheduling/overhead. `getCollectionTime()` không được định nghĩa là tổng CPU time đó. Muốn đo CPU spent on GC, cần nguồn chuyên dụng được hỗ trợ và biết semantics JVM/collector; không lấy “GC elapsed / wall” làm CPU %.

### 8.5 Không thể dùng riêng để giải thích RSS/OOM hoặc memory leak

Một application OOM có thể do heap, direct buffers, metaspace, native allocations, threads, container memory limit hoặc nguồn khác. `GarbageCollectorMXBean` không trả RSS, max heap, committed heap hay retained object graph. Cần thêm `MemoryMXBean`, `MemoryPoolMXBean`, `BufferPoolMXBean`, OS/cgroup metrics, GC logs/JFR và khi được phép mới sử dụng heap analysis.

Heap used lớn hoặc GC count tăng có thể là biểu hiện tải tăng bình thường; **memory leak không được chẩn đoán chỉ bằng count/time**.

## 9. Các collector khác nhau và rủi ro so sánh trực tiếp

### 9.1 Không đóng cứng tên “young collector” và “old collector”

Nhiều tài liệu minh họa HotSpot bằng hai beans young/old. Nhưng API không cam kết đúng số lượng/tên/thuật toán. Một JVM có thể đổi collector khi đổi flags/JDK; tên bean có thể đổi. Một số thuật toán concurrent có khái niệm cycle/phase không tương ứng trực tiếp với “Young GC” quen thuộc.

Vì vậy nên:

1. Liệt kê `ManagementFactory.getGarbageCollectorMXBeans()` tại runtime thật.
2. Ghi tên, ObjectName, memory pools liên quan và count/time có khả dụng không.
3. Xác minh GC algorithm/JVM implementation/version qua cấu hình/startup logs hoặc công cụ phù hợp.
4. Xây dashboard theo nhãn linh hoạt; không gắn nhãn “Old GC = bean thứ hai”.
5. Khi nâng JDK hoặc đổi collector, lập lại baseline về count/time thay vì ghép các chuỗi như tương đương.

### 9.2 Count và thời gian của các bean không bắt buộc có thể cộng

Một phép cộng chỉ có ý nghĩa khi đại lượng cùng semantics và không trùng lặp. Với GC collectors:

- Một bean có thể đại diện một nhánh thu gom, bean khác đại diện chu kỳ concurrent.
- Một event có thể liên quan nhiều pha; cách JVM cập nhật count/time không chuẩn hóa thành một sổ cái pause chung.
- Cộng elapsed milliseconds của những quá trình xảy ra đồng thời có thể vượt độ dài wall-clock mà không phải “lỗi số học”.
- Nếu tool/exporter đã tổng hợp, cộng lại ở dashboard nữa có nguy cơ **double count**.

Khi không chứng minh được điều kiện cộng, giữ riêng từng bean và chỉ báo tổng là “sum of reported collector counters”, không gọi “total STW pause time”.

### 9.3 Khác biệt GC algorithm có thể làm hai run không so được

Giả sử thay G1 bằng ZGC cùng workload, p95 request giảm nhưng count GC thay đổi hoàn toàn. Không thể kết luận “ZGC ít GC hơn = nhanh hơn” chỉ từ count. Cần so:

- Application latency distribution, throughput và error rate.
- Heap usage/commit/allocation, memory limits.
- GC events và pause durations do collector thực tế phát ra.
- CPU usage, container throttling và work performed concurrently.
- Same workload/payload, JDK release, heap flags và measurement windows.

Chỉ khi so đúng điều kiện và hiểu semantics mới dùng count/time như **bằng chứng bổ trợ**.

## 10. Kết hợp với MemoryMXBean, MemoryPoolMXBean và số liệu OS

`GarbageCollectorMXBean` là một mảnh ghép. Để hiểu “GC có hiệu quả không?” cần các lớp khác:

| Nguồn | Dữ liệu chính | Tình huống |
| --- | --- | --- |
| `GarbageCollectorMXBean` | Count/time tích lũy cho từng collector | Xu hướng số lần và reported elapsed time |
| `MemoryMXBean.getHeapMemoryUsage()` | Used, committed, init, max của heap | Heap có tiến gần limit không? |
| `MemoryPoolMXBean` | Usage/peak/collection usage khi hỗ trợ | Pool nào tăng, có bao nhiêu heap sau GC? |
| GC unified logs | Event, tags, thời gian, cause, heap trước/sau tùy cấu hình | So pause theo timestamp và hành vi collector |
| JFR | GC pause/cycle, allocation, thread và các events tùy recording | Liên hệ GC với latency/CPU/tải |
| OS/container | Process CPU, RSS, cgroup memory, throttling/OOM events | JVM có bị giới hạn tài nguyên ngoài heap? |
| Application metrics | p50/p95/p99 latency, errors, queue, throughput | Người dùng có bị ảnh hưởng không? |

Ví dụ, nếu count tăng nhanh và memory after GC không giảm, có thể điều tra allocation pressure, live set tăng, giới hạn heap hoặc thay đổi workload. Nhưng **không tự gọi đó là leak**. Nếu count/time thấp mà RSS tăng, xem native memory/direct buffers, code cache hoặc memory accounting thay vì tuyên bố GC metrics bị lỗi.

### 10.1 GC logs giúp nhìn điều không có trong aggregate

Trên HotSpot/JDK 17+, có thể cấu hình Unified JVM Logging tại startup, ví dụ:

```bash
java "-Xlog:gc*=info:file=gc-%p-%t.log:utctime,uptime,level,tags:filecount=5,filesize=10M" -jar app.jar
```

Lệnh yêu cầu `app.jar` thực sự tồn tại, nơi ghi file có quyền và collector phát events. Log có thể chứa timestamp, GC ID, loại pause và các chi tiết theo tags. **Không thay thế cấu hình mặc định của production chỉ để thử**: debug/trace có overhead/dung lượng; chọn level phù hợp, retention/bảo mật và time correlation.

GC log có thể phân tích từng event để tìm pause dài hoặc đối chiếu p99 latency. Tuy vậy, loại event và trường log phụ thuộc JVM/collector; không parse format tùy tiện như giao thức bất biến qua mọi JDK.

### 10.2 JFR và GcInfo: khi cần event-level data

Trên một số JDK/HotSpot, extension `com.sun.management.GarbageCollectorMXBean` có `getLastGcInfo()` (trả thông tin GC gần nhất hoặc `null`). `GcInfo` có thể cung cấp start time, end time, duration, memory usage trước/sau một collection, cùng thuộc tính implementation-specific. Đây là **API mở rộng của `jdk.management`, không phải** hai phương thức chuẩn `java.lang.management.GarbageCollectorMXBean` và không bảo đảm mọi collector hỗ trợ.

Hệ thống cũng có thể cung cấp GC notifications thông qua JMX `NotificationEmitter` và `GarbageCollectionNotificationInfo` ở những collector hỗ trợ. Nhận notification cần đăng ký listener; có thể mất dữ liệu nếu listener không hoạt động, collector không phát hoặc monitoring disconnect. Event-level **không tự đảm bảo** một histogram pause hoàn chỉnh nếu semantics và pipeline chưa được xác minh.

JFR recording là lựa chọn khi cần lịch sử events đủ chi tiết, bao gồm timing/cause/memory/stack/CPU theo loại event cấu hình. Không phải JFR event nào cũng là STW pause. Kiểm tra recording template, sampling, overhead và quyền dữ liệu trước khi suy ra câu chuyện performance.

## 11. Vận hành JMX và chất lượng dữ liệu

### 11.1 Local sampling và remote sampling khác nhau

Lấy bean trong chính ứng dụng qua `ManagementFactory` không cần JMX network. Nhưng monitoring system đọc từ xa thường cần JMX connector/agent/exporter:

- Quản lý TLS, authentication/authorization và network boundaries; không phơi cổng JMX không bảo vệ lên Internet.
- Nếu dùng exporter, xác nhận metric name, unit và labels: Java báo `getCollectionTime()` bằng **ms**, nhiều backend lại biểu diễn time bằng **seconds**.
- Kiểm tra cỡ mẫu và timeout JMX. Một scrape bị lỗi không có nghĩa GC count=0.
- Tách bean identity và JVM instance trước khi rate; tránh tăng đột biến giả khi đổi PID/replica/collector.
- Kiểm soát overhead của nhiều scraper đồng thời, công cụ profiling và metadata có thể chứa chi tiết nội bộ.

### 11.2 Mất mẫu, counter lag, độ phân giải và chú giải

Tài liệu API cho phép time counter không thay đổi dù count tăng vì event ngắn. Ngoài ra, những lần lấy mẫu và exporter có thể chịu buffering, scrape delay hoặc reset. Các biểu đồ GC không phải bằng chứng tuyệt đối về duration từng event.

Một dashboard đáng tin nên hiển thị ít nhất:

- Tên collector, tên service/instance, JVM version/GC algorithm.
- Count/time counter hoặc rate delta, ghi **đúng đơn vị** và cửa sổ tính.
- Khả dụng của các metrics (`-1`/missing/collector disappeared).
- Application p95 latency, error rate, throughput trong cùng khoảng UTC.
- JVM heap used/committed/max và GC pause histogram nếu có nguồn riêng.
- Deployment/restart markers để tránh so ghép trước và sau JVM restart.

### 11.3 Không áp đặt một ngưỡng cảnh báo chung cho mọi JVM

GC count 100/phút có thể là bình thường với tải/cấu hình A và bất thường với tải B. Tỷ lệ delta collection time 5% có thể hữu ích như mô tả, nhưng ý nghĩa đối với STW/p99 hoặc throughput phụ thuộc collector. Cảnh báo nên dựa vào **baseline theo workload, độ biến động, chất lượng dịch vụ và bằng chứng bổ trợ**, không chỉ một con số tổng.

Ví dụ một thiết kế alert tốt hơn “count > 10” là: application p95 latency vượt ngưỡng đã xác định liên tục trong cửa sổ đủ mẫu, cùng lúc GC events/pause distribution có dấu hiệu thay đổi, và có links tới runtime/heap/CPU metrics để kiểm chứng. Alert này còn cần chống nhiễu, xử lý traffic thấp và phân biệt nguyên nhân từ DB/network.

## 12. Các tình huống chẩn đoán có thể gặp

### 12.1 Cứ mỗi 30 giây count lại tăng nhưng p95 không đổi

**Quan sát:** collector A tăng 5 collections/30 giây, time báo tăng vài chục ms, p95 và error rate ổn định, heap sau GC quay về baseline.

**Diễn giải hợp lý:** có hoạt động GC nhưng **chưa có bằng chứng ảnh hưởng người dùng**. Chưa nên tối ưu GC chỉ vì count tăng; cần biết allocation/workload, baseline và event-level pause nếu có rủi ro.

**Không kết luận:** “GC luôn không ảnh hưởng” vì aggregate có thể che một pause cá biệt và p95 không phản ánh p99.

### 12.2 Count tăng ít nhưng một request bị chậm 800 ms

**Quan sát:** chỉ một collection trong cửa sổ, total time tăng 100 ms; một request mất 800 ms.

**Diễn giải:** hai sự kiện có thể liên quan hoặc không. Count/time không cho timestamp và không chứng minh 100 ms GC tạo toàn bộ 800 ms latency. Cần trace request, GC event timestamp, CPU, queue và dependency calls. Có thể request chờ connection, lock, DB hoặc thread pool độc lập.

### 12.3 JVM đổi GC algorithm sau khi nâng phiên bản

**Quan sát:** bean names mới, count giảm mạnh, nhưng throughput/latency thay đổi ít.

**Diễn giải:** nguồn đo đã thay semantics/tên bean. Trước khi nói “GC giảm 90%”, xác minh collector/JDK release, metric mapping, event support và count definitions. Cần thiết lập baseline mới và so các chỉ số phục vụ người dùng.

### 12.4 Collector time trả -1 nhưng count vẫn tăng

**Quan sát:** `getCollectionCount()` có giá trị, `getCollectionTime()` là `-1`.

**Diễn giải:** thời gian không được định nghĩa qua bean đó. Có thể giữ count để tính rate, nhưng không suy time delta=0 hoặc percent. Dùng GC logs/JFR/metrics khác nếu cần GC duration.

### 12.5 Process restart giữa hai lần scrape

**Quan sát:** count từ 2.100 về 7, time từ 40.000 về 120 ms.

**Diễn giải:** không được tạo rate âm và vẽ “GC reversed”. Kiểm tra JVM restart/deploy, process identity, reset counter handling. Chỉ so các điểm của cùng instance.

### 12.6 Heap tăng nhưng GC time gần như không đổi

**Quan sát:** heap occupancy và RSS tăng, count/time ít thay đổi.

**Diễn giải:** có thể workload giữ nhiều object, GC policy chưa chạy collection tương ứng, hoặc memory tăng nằm ngoài heap. Cần MemoryMXBean/MemoryPoolMXBean, OS/container metrics và allocation evidence. Không dùng count/time thấp để loại trừ memory pressure.

## 13. Sai lầm phổ biến và cách sửa

| Sai lầm | Vì sao sai | Cách làm đúng |
| --- | --- | --- |
| `getCollectionCount() = 100` nghĩa “100 GC trong phút vừa rồi” | Counter tích lũy | Trừ hai mẫu cùng bean/instance trong đúng cửa sổ |
| `getCollectionTime() = 3000` nghĩa “ứng dụng đã pause 3 giây” | Elapsed collection time không đồng nhất STW | Gọi đúng tên reported elapsed; đối chiếu GC event timing |
| Lấy tổng time/count làm p95 pause | Trung bình không chứa thông tin phân bố | Dùng event-level/histogram đáng tin |
| Dùng `-1` như count/time thật | API định nghĩa đó là undefined | Báo not available, không tính delta |
| Count tăng mà time không tăng ⇒ bean lỗi | Độ phân giải ms có thể làm time không thay đổi | Đọc đúng semantics, tăng cửa sổ nếu phù hợp |
| Cộng time của mọi beans thành “total pause” | Khác scope/overlap/concurrent work | Giữ series riêng, chỉ tổng hợp có căn cứ |
| Mặc định mọi JVM có Young/Old bean | API không bảo đảm số/tên beans | Duyệt danh sách và ghi collector identity thực |
| So raw counters giữa các process | Lifetime khác nhau; restart reset | Dùng delta và instance identity |
| So G1 với ZGC bằng số count | Semantics collector khác | So performance metrics + event logs, điều kiện tương đương |
| Gán delta time / wall = CPU % | Time do bean không phải CPU worker time | Dùng CPU metrics phù hợp, chú giải reported ratio |
| Kết luận GC là nguyên nhân p99 từ một điểm tổng | Thiếu thời điểm từng event và trace | Correlate event-level GC với latency/CPU/queue |
| Biểu đồ không hiển thị unit | ms/seconds hoặc rate/count dễ bị nhầm | Ghi explicit units, collector labels và window |
| Bỏ qua collector `isValid()`, reset hoặc missing | Có thể dùng sample stale không còn hợp lệ | Kiểm tra validity và health của pipeline |
| Export raw JVM metadata không kiểm soát | Có thể lộ path, host, credentials | Chia sẻ tối thiểu, RBAC và redaction |

## 14. Checklist sử dụng GarbageCollectorMXBean đúng

- [ ] Dùng đúng module `java.management` và giao diện chuẩn `GarbageCollectorMXBean`.
- [ ] Liệt kê **tất cả beans thực tế**; không hard-code số lượng hoặc tên Young/Old.
- [ ] Với mỗi bean, lưu `getName()` hoặc `getObjectName()` và JVM instance/JDK/GC algorithm.
- [ ] Đọc riêng `getCollectionCount()` và `getCollectionTime()`, ghi rõ **count** và **ms**.
- [ ] Xử lý `-1` như **undefined**; không biến thành 0.
- [ ] Muốn tính rate/delta phải có **hai mẫu cùng bean, cùng process instance**, cùng định nghĩa.
- [ ] Ghi thời gian cửa sổ thực tế, sampling interval và timestamp/UTC phù hợp.
- [ ] Xử lý restart/counter giảm, bean biến mất và missing samples.
- [ ] Không giả định getter của count/time là một snapshot nguyên tử.
- [ ] Không gọi aggregate elapsed là tổng STW pause hoặc GC CPU time nếu chưa có chứng minh cho JVM cụ thể.
- [ ] Không tính p95/p99/max từ total/count; cần GC events hoặc histogram.
- [ ] Không cộng nhiều collector beans thành total pause mà bỏ qua khả năng chồng lấn.
- [ ] Đối chiếu GC counters với application latency, throughput, errors, heap usage và CPU/container resource metrics.
- [ ] Khi đổi JDK/collector, xác minh lại semantics và baseline.
- [ ] Nếu cần event-level/cause/memory before-after, sử dụng GC logs/JFR/notification được hỗ trợ.
- [ ] Bảo vệ kết nối JMX và dữ liệu monitoring theo quyền vận hành.

## 15. Bài tập tự kiểm tra

**Câu 1.** Một bean có count từ 45 lên 51 và time từ 200 lên 230 ms trong cửa sổ 10 giây. Suy ra được gì?

**Đáp án:** sáu collection được bean báo, collection elapsed time tăng 30 ms. Rate trung bình là `6 / 10 = 0,6 collection/giây`. Trung bình reported elapsed `30 / 6 = 5 ms/collection`. Không suy được pause p95 hoặc tác động lên API.

**Câu 2.** Count tăng từ 6 lên 7, time vẫn 10 ms. Có lỗi chắc chắn không?

**Đáp án:** Không. API nói time có thể không đổi nếu collection quá ngắn theo độ phân giải báo cáo; có thể còn semantics collector/độ trễ cập nhật. Cần lấy thêm samples hoặc event-level data nếu thực sự nghi ngờ.

**Câu 3.** Bean A báo time tăng 200 ms, bean B tăng 300 ms trong cửa sổ một giây. Có chắc application bị dừng 500 ms không?

**Đáp án:** Không. Cộng collector elapsed time chưa được chuẩn hóa thành tổng STW paused time; có thể khác loại công việc/chồng lấn. Cần GC pause events và timestamp.

**Câu 4.** Time trả `-1`, count trả 100. Có tính phần trăm GC được không?

**Đáp án:** Không, time undefined. Count có thể dùng để tính delta nếu cùng instance; phần trăm thời gian không có cơ sở từ bean này.

**Câu 5.** Sau deploy, count từ 5.000 xuống 20. Vì sao không vẽ delta -4.980?

**Đáp án:** counter là số tích lũy theo JVM/collector. Process có thể đã restart hoặc chuỗi bị nối khác instance; phải phân đoạn và xác minh danh tính. Giá trị âm không phải số GC trong cửa sổ.

**Câu 6.** Có thể dùng `GarbageCollectorMXBean` để trả lời “GC nào gây spike p99 lúc 14:05:03?” không?

**Đáp án:** Hai counter không mang timestamp/per-event duration. Chúng chỉ đặt ra giả thuyết. Cần JFR/GC logs/notifications và trace request/latency đồng bộ thời gian để đối chiếu.

**Câu 7.** Code lấy đúng bean từ `ManagementFactory` nhưng không có số collection trong một giây chạy demo. Có thể kết luận JVM không hỗ trợ GC không?

**Đáp án:** Không. Có thể không phát sinh collection trong cửa sổ, bean trả undefined hoặc event quá ngắn/không được hạch toán theo mong đợi. Kiểm tra count/time có hợp lệ, workload và collector semantics; không dùng một giây không tăng để kết luận khả năng runtime.

## Tài liệu tham khảo

- [Java SE 21 — GarbageCollectorMXBean](https://docs.oracle.com/en/java/javase/21/docs/api/java.management/java/lang/management/GarbageCollectorMXBean.html): `getCollectionCount()`, `getCollectionTime()`, `-1`, unit ms và tính gần đúng.
- [Java SE 21 — ManagementFactory](https://docs.oracle.com/en/java/javase/21/docs/api/java.management/java/lang/management/ManagementFactory.html): `getGarbageCollectorMXBeans()` và platform MBeans.
- [Java SE 21 — MemoryMXBean](https://docs.oracle.com/en/java/javase/21/docs/api/java.management/java/lang/management/MemoryMXBean.html): vùng nhớ, memory managers và memory pools.
- [Java SE 21 — MemoryPoolMXBean](https://docs.oracle.com/en/java/javase/21/docs/api/java.management/java/lang/management/MemoryPoolMXBean.html): usage/collection usage khi collector hỗ trợ.
- [JDK 21 — com.sun.management.GarbageCollectorMXBean](https://docs.oracle.com/en/java/javase/21/docs/api/jdk.management/com/sun/management/GarbageCollectorMXBean.html): extension có `getLastGcInfo()` ở collector được hỗ trợ.
- [JDK 21 — GcInfo](https://docs.oracle.com/en/java/javase/21/docs/api/jdk.management/com/sun/management/GcInfo.html): thời điểm/duration và memory usage của GC event gần nhất, khi có dữ liệu.
- [JDK 21 — java command Unified JVM Logging](https://docs.oracle.com/en/java/javase/21/docs/specs/man/java.html#enable-logging-with-the-jvm-unified-logging-framework): cấu hình `-Xlog` theo tag/level/output.

**Ghi nhớ:** `GarbageCollectorMXBean` cho biết **tổng số collection được công bố** và **thời gian collection elapsed tích lũy gần đúng**, theo từng collector bean. Muốn thấy sự thay đổi phải lấy **delta của hai mẫu cùng JVM** và xử lý `-1`/restart. Hai tổng này hữu ích để nhìn **xu hướng**, nhưng **không phải** GC pause histogram, total STW time, GC CPU time hay nguyên nhân của p99 latency. Khi cần chi tiết để kết luận, phải ghép thêm GC events, heap, CPU và chỉ số ứng dụng cùng cửa sổ.