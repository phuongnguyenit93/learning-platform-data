# GarbageCollectorMXBean và thời gian, số lần thu gom

## 1. Hai con số giúp trả lời câu hỏi nào?

Khi ứng dụng Java chậm đi, một câu hỏi thường gặp là: “Trong khoảng vừa rồi, JVM có thu gom rác nhiều hơn hoặc dành nhiều thời gian hơn cho hoạt động đó không?”

`GarbageCollectorMXBean` cung cấp các bộ đếm của từng bộ thu gom rác (garbage collector, GC):

- **Số lần thu gom tích lũy** qua `getCollectionCount()`.
- **Thời gian thu gom tích lũy, xấp xỉ** qua `getCollectionTime()`.

Đây là điểm bắt đầu để quan sát xu hướng GC. Chúng không cung cấp danh sách mọi lần dừng, phần trăm CPU hay nguyên nhân trực tiếp khiến một yêu cầu HTTP chậm.

Mỗi JVM có thể có nhiều bean GC. Lấy danh sách của JVM hiện tại bằng `ManagementFactory.getGarbageCollectorMXBeans()`. Giao diện và tên JMX của từng bean được mô tả trong [GarbageCollectorMXBean](https://docs.oracle.com/en/java/javase/25/docs/api/java.management/java/lang/management/GarbageCollectorMXBean.html).

## 2. Đọc đúng dữ liệu tích lũy

| Phương thức | Dữ liệu | Đơn vị và trường hợp đặc biệt |
| --- | --- | --- |
| `getCollectionCount()` | Tổng số lần thu gom được bean báo cáo | Số lần; `-1` nếu không xác định |
| `getCollectionTime()` | Tổng thời gian thu gom xấp xỉ được bean báo cáo | Mili giây; `-1` nếu không xác định |
| `getName()` | Tên bộ quản lý bộ nhớ tương ứng | Chuỗi mô tả, phụ thuộc JVM |
| `getMemoryPoolNames()` | Các pool bộ nhớ mà bộ quản lý phụ trách | Danh sách tên pool |
| `isValid()` | Bean còn đại diện cho bộ quản lý hợp lệ không | `boolean` |

Các phương thức về tên, pool và tính hợp lệ được kế thừa từ [MemoryManagerMXBean](https://docs.oracle.com/en/java/javase/25/docs/api/java.management/java/lang/management/MemoryManagerMXBean.html).

Ví dụ một mẫu đọc trả về `count=500`, `time=4000` không có nghĩa “vừa có 500 lần GC trong một giây”. Đó là số tích lũy tại thời điểm đọc. Muốn hiểu khoảng thời gian gần nhất, cần lấy hiệu giữa hai mẫu thuộc cùng một bean và cùng vòng đời JVM.

Không đổi `-1` thành 0. Số 0 có nghĩa đã có phép đo và giá trị bằng không; `-1` có nghĩa không có số liệu xác định. Hai bộ đếm có thể cần được xử lý độc lập nếu chỉ một trường có giá trị hợp lệ.

Một đặc điểm về độ phân giải: thời gian tích lũy có thể không đổi dù số lần đã tăng, nếu các lần thu gom rất ngắn. Hợp đồng của [getCollectionTime()](https://docs.oracle.com/en/java/javase/25/docs/api/java.management/java/lang/management/GarbageCollectorMXBean.html#getCollectionTime()) nêu rõ trường hợp này. Vì vậy, `deltaTime == 0` không chứng minh GC hoàn toàn không thực hiện công việc.

## 3. Từ bộ đếm sang số liệu trong một khoảng

Giả sử hai mẫu hợp lệ của cùng một bean:

```text
Mẫu đầu:    count = 12, time = 40 ms
Mẫu sau:    count = 17, time = 90 ms
Khoảng đo:  2 giây
```

Tính được:

```text
Số lần tăng          = 17 - 12 = 5
Thời gian tăng       = 90 - 40 = 50 ms
Tần suất được báo cáo = 5 / 2 = 2.5 lần/giây
Tỷ lệ thời gian       = 50 / 2000 * 100 = 2.5%
Thời gian trung bình  = 50 / 5 = 10 ms/lần
```

Cần gắn nhãn đúng:

- `2.5 lần/giây` là tốc độ tăng bộ đếm trong khoảng đo.
- `2.5%` là tỷ số thời gian tích lũy GC tăng thêm trên thời gian quan sát.
- `10 ms/lần` chỉ là trung bình từ hai hiệu số.

Không gọi tỷ số thứ hai là “CPU GC” hoặc mặc định là “phần trăm thời gian mọi luồng ứng dụng bị dừng”. Không gọi số trung bình là p95/p99 hoặc thời gian dừng dài nhất.

Ví dụ, các lần kéo dài `1, 1, 1, 1, 46 ms` cũng có trung bình `10 ms`. Số trung bình không mô tả sự phân bố, càng không xác định được yêu cầu nào bị ảnh hưởng.

## 4. Ví dụ Java: tính hiệu an toàn và lấy mẫu thật

Chương trình có hai chế độ:

- Mặc định: dùng dữ liệu cố định để kiểm tra phép tính và các đường xử lý số liệu không hợp lệ.
- `--live`: lấy hai mẫu từ JVM đang chạy chương trình, cách nhau khoảng một giây.

Lưu thành **GcCounterDemo.java**, dùng Java 17 trở lên:

```java
import java.lang.management.GarbageCollectorMXBean;
import java.lang.management.ManagementFactory;
import java.util.LinkedHashMap;
import java.util.Locale;
import java.util.Map;

public class GcCounterDemo {
    record Sample(long nanos, long count, long timeMillis) {}

    public static void main(String[] args) throws InterruptedException {
        if (args.length == 0) {
            report("normal",
                    new Sample(0L, 12L, 40L),
                    new Sample(2_000_000_000L, 17L, 90L));
            report("unknown",
                    new Sample(0L, -1L, -1L),
                    new Sample(2_000_000_000L, -1L, -1L));
            report("counter-decreased",
                    new Sample(0L, 12L, 40L),
                    new Sample(2_000_000_000L, 1L, 5L));
            report("no-new-collection",
                    new Sample(0L, 12L, 40L),
                    new Sample(2_000_000_000L, 12L, 40L));
            return;
        }

        if (args.length != 1 || !"--live".equals(args[0])) {
            throw new IllegalArgumentException("Use no arguments or --live");
        }

        Map<String, Sample> before = read();
        Thread.sleep(1000L);
        Map<String, Sample> after = read();

        for (var entry : after.entrySet()) {
            String id = entry.getKey();
            Sample previous = before.get(id);
            if (previous == null) {
                System.out.println(id + ": baseline unavailable");
                continue;
            }
            report(id, previous, entry.getValue());
        }
    }

    private static Map<String, Sample> read() {
        Map<String, Sample> samples = new LinkedHashMap<>();
        for (GarbageCollectorMXBean bean
                : ManagementFactory.getGarbageCollectorMXBeans()) {
            if (!bean.isValid()) {
                continue;
            }
            long count = bean.getCollectionCount();
            long time = bean.getCollectionTime();
            long stamp = System.nanoTime();
            samples.put(bean.getObjectName().getCanonicalName(),
                    new Sample(stamp, count, time));
        }
        return samples;
    }

    private static Long delta(long before, long after) {
        if (before < 0L || after < 0L || after < before) {
            return null;
        }
        return after - before;
    }

    private static void report(String name, Sample before, Sample after) {
        double elapsedMillis = (after.nanos() - before.nanos()) / 1_000_000.0;
        if (elapsedMillis <= 0.0) {
            System.out.println(name + ": invalid interval");
            return;
        }

        Long count = delta(before.count(), after.count());
        Long time = delta(before.timeMillis(), after.timeMillis());

        String rate = count == null ? "n/a"
                : number(count * 1000.0 / elapsedMillis);
        String share = time == null ? "n/a"
                : number(time * 100.0 / elapsedMillis) + "%";
        String mean = count == null || time == null || count == 0L ? "n/a"
                : number(time / (double) count);

        System.out.printf(Locale.ROOT,
                "%s deltaCount=%s deltaTimeMs=%s ratePerSec=%s "
                        + "timeRatio=%s meanMs=%s%n",
                name, value(count), value(time), rate, share, mean);
    }

    private static String value(Long value) {
        return value == null ? "n/a" : value.toString();
    }

    private static String number(double value) {
        return String.format(Locale.ROOT, "%.2f", value);
    }
}
```

Biên dịch và chạy:

```shell
javac GcCounterDemo.java
java GcCounterDemo
```

Stdout chính xác:

```text
normal deltaCount=5 deltaTimeMs=50 ratePerSec=2.50 timeRatio=2.50% meanMs=10.00
unknown deltaCount=n/a deltaTimeMs=n/a ratePerSec=n/a timeRatio=n/a meanMs=n/a
counter-decreased deltaCount=n/a deltaTimeMs=n/a ratePerSec=n/a timeRatio=n/a meanMs=n/a
no-new-collection deltaCount=0 deltaTimeMs=0 ratePerSec=0.00 timeRatio=0.00% meanMs=n/a
```

Dữ liệu mặc định là dữ liệu tự tạo cho phép tính, không phải kết quả GC của một JVM thật.

Để lấy mẫu thật:

```shell
java GcCounterDemo --live
```

Tên bean, số dòng và các giá trị thay đổi theo JVM, thuật toán GC và hoạt động trong khoảng đo. Một chương trình ít cấp phát hoàn toàn có thể không quan sát thấy lần thu gom mới. Không cần ép GC chỉ để làm số đếm tăng.

### Các quyết định đáng chú ý trong mã

**Đo khoảng bằng thời gian thực tế.**  
Chương trình không mặc định `sleep(1000)` tạo đúng 1000 ms giữa hai mẫu. Nó tính hiệu `System.nanoTime()`, vốn được dùng để đo khoảng thời gian thay vì ngày giờ lịch. Xem [System.nanoTime()](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/System.html#nanoTime()).

**Ghép mẫu theo định danh bean.**  
Dùng tên JMX chuẩn hóa thay vì ghép theo vị trí trong danh sách. Trong hệ thống giám sát nhiều JVM, cần thêm định danh tiến trình và lần khởi động; cùng một ObjectName ở hai JVM không có nghĩa cùng một chuỗi bộ đếm.

**Không kẹp hiệu âm thành 0.**  
Bộ đếm giảm là tín hiệu cần bỏ phép tính và lấy lại mẫu nền. Có thể đã ghép sai vòng đời JVM hoặc nguồn dữ liệu thay đổi. Gán 0 sẽ che lỗi ghép dữ liệu.

**Không chia cho 0 khi không có lần mới.**  
Tần suất bằng 0 vẫn có ý nghĩa, nhưng thời gian trung bình trên mỗi lần trong khoảng đó không xác định.

**Không giả vờ có ảnh chụp nguyên tử.**  
Hai lệnh đọc count/time diễn ra nối tiếp. GC vẫn có thể tiến triển giữa hai lần đọc. Khoảng lấy mẫu hợp lý làm dữ liệu dễ diễn giải hơn, nhưng không biến chúng thành bản ghi sự kiện chính xác.

## 5. Nhiều bean không đồng nghĩa nhiều “GC độc lập” có thể cộng tùy ý

Không viết logic với giả định JVM luôn có đúng hai bean “trẻ” và “già”. Tên và cách chia bộ đếm phụ thuộc bộ thu gom và cách triển khai JVM.

Nên giữ số liệu theo từng bean trước khi tổng hợp. Nếu muốn cộng, phải hiểu các bean báo cáo loại hoạt động nào và có khả năng mô tả các phần liên quan của cùng một chu kỳ hay không. Tổng thời gian các bean không mặc nhiên là thời gian ứng dụng dừng trên đồng hồ thực.

Tương tự, nhiều luồng GC chạy song song không có nghĩa `getCollectionTime()` tự động trở thành tổng CPU của từng luồng. API nói về thời gian thu gom tích lũy xấp xỉ, không cung cấp bộ đếm CPU GC tiêu chuẩn qua hai phương thức này.

Một tỷ lệ bất thường cần được điều tra theo nguồn đo, khoảng đo và cách tổng hợp. Không âm thầm chặn kết quả về 100% rồi xem như dữ liệu đã đúng.

## 6. Từ biểu đồ GC đến giả thuyết chẩn đoán

Các tình huống sau định hướng điều tra, chưa phải kết luận nguyên nhân:

| Quan sát trong tải tương đương | Câu hỏi tiếp theo |
| --- | --- |
| Số lần tăng nhanh, thời gian mỗi lần thấp | Ứng dụng có tạo nhiều đối tượng ngắn hạn hơn không? |
| Thời gian tích lũy tăng mạnh, số lần tăng ít | Có sự kiện GC dài cần xem chi tiết không? |
| GC tăng đồng thời heap sau GC vẫn cao dần | Những đối tượng nào đang bị giữ lại, tải hoặc bộ đệm có thay đổi không? |
| Độ trễ yêu cầu tăng nhưng bộ đếm GC gần như không đổi | Có chờ I/O, tranh chấp khóa, CPU hoặc nguyên nhân khác không? |

Đối chiếu với số liệu heap, tải, độ trễ yêu cầu và dữ liệu sự kiện. Không kết luận rò rỉ chỉ từ việc count tăng: GC thường xuyên cũng có thể là hoạt động bình thường của một ứng dụng có nhiều đối tượng sống ngắn.

Giữ mốc thời gian và nhãn bean trong dữ liệu. Cùng giá trị tích lũy có thể tương ứng với nhiều phân bố thời gian khác nhau. Lấy mẫu định kỳ phù hợp cho xu hướng; nó không tái dựng được đầy đủ những gì xảy ra giữa hai lần lấy mẫu.

## 7. Khi cần từng sự kiện thay vì số tổng

Để biết khoảng dừng dài nhất, phân bố độ trễ hoặc các pha của một chu kỳ, dùng dữ liệu sự kiện như nhật ký GC hoặc JDK Flight Recorder, rồi kiểm tra loại sự kiện thực sự được thu thập.

Một số JVM hỗ trợ giao diện mở rộng `com.sun.management.GarbageCollectorMXBean` với `getLastGcInfo()`. Đây là phần mở rộng theo nền tảng, không phải bảo đảm mọi triển khai giao diện Java chuẩn đều có. Cần kiểm tra kiểu và xử lý kết quả `null` khi chưa có thông tin. Xem [giao diện GC mở rộng](https://docs.oracle.com/en/java/javase/25/docs/api/jdk.management/com/sun/management/GarbageCollectorMXBean.html).

`GcInfo` có thời điểm bắt đầu, kết thúc, thời lượng và số liệu bộ nhớ trước/sau một lần GC. Tuy nhiên, “lần gần nhất” không phải kho lưu mọi sự kiện: lấy mẫu chậm có thể bỏ qua các lần ở giữa. Tài liệu [GcInfo](https://docs.oracle.com/en/java/javase/25/docs/api/jdk.management/com/sun/management/GcInfo.html) mô tả dữ liệu này.

Không suy ra histogram độ trễ chỉ từ hiệu bộ đếm hoặc một `GcInfo` mới nhất. Cần nguồn sự kiện và cách thu thập phù hợp với câu hỏi.

## 8. Tự kiểm tra trước khi dùng trong giám sát

1. **Count tăng nhưng time không tăng thì có lỗi không?** Không nhất thiết; độ phân giải và tính xấp xỉ có thể tạo tình huống đó.
2. **Hai mẫu có time = -1 thì hiệu bằng 0 có hợp lệ không?** Không; số liệu thời gian không xác định, không được trừ rồi coi như số đo.
3. **Hiệu count bằng 0 thì mean bằng 0 ms có đúng không?** Không có lần mới để tính trung bình; dùng trạng thái không xác định.
4. **Mean 10 ms có chứng minh p99 dưới 10 ms không?** Không; trung bình không chứa phân bố.
5. **Tiến trình khởi động lại có thể nối tiếp bộ đếm cũ không?** Không; cần tạo mẫu nền cho vòng đời JVM mới.
6. **Có nên gọi System.gc() mỗi chu kỳ giám sát?** Không dùng cách đó để tạo “dữ liệu thật hơn”; nó tác động đến hệ thống đang quan sát.

Thực hành bằng cách chạy chế độ mặc định, giải thích từng cột, rồi chạy `--live`. Mục tiêu là tính được số tăng theo khoảng một cách trung thực, giữ trạng thái không có dữ liệu và biết khi nào cần chuyển từ số tổng sang điều tra sự kiện.
