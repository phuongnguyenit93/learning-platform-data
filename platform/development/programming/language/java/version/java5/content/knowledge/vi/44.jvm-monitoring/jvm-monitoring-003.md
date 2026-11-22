# MemoryMXBean và số liệu heap, non-heap

## 1. Bắt đầu từ câu hỏi cần quan sát

Khi một ứng dụng Java sử dụng ngày càng nhiều bộ nhớ, cần phân biệt:

- Bộ nhớ dùng cho đối tượng Java đang tăng?
- JVM đang mở rộng vùng đã cam kết, dù lượng đang dùng chưa tăng tương ứng?
- Bộ nhớ phục vụ việc thực thi của JVM đang tăng?
- Hay mức sử dụng bộ nhớ của cả tiến trình tăng ở phần mà số liệu này không bao quát?

`MemoryMXBean` là giao diện quản lý để đọc tình hình bộ nhớ của JVM. Nó cung cấp hai ảnh chụp tổng hợp: **heap** và **non-heap**. Mỗi ảnh chụp là một `MemoryUsage`, không phải danh sách đối tượng và không phải kết luận về rò rỉ bộ nhớ.

Lấy bean của JVM hiện tại bằng:

```java
// Đoạn mã minh họa; cần các import java.lang.management tương ứng.
MemoryMXBean bean = ManagementFactory.getMemoryMXBean();
MemoryUsage heap = bean.getHeapMemoryUsage();
MemoryUsage nonHeap = bean.getNonHeapMemoryUsage();
```

Đây là truy cập cục bộ vào JVM đang chạy đoạn mã, không tự mở kết nối giám sát đến một ứng dụng khác. [ManagementFactory](https://docs.oracle.com/en/java/javase/25/docs/api/java.management/java/lang/management/ManagementFactory.html) là điểm lấy các platform MXBean; bean bộ nhớ có tên JMX `java.lang:type=Memory`.

## 2. Heap và non-heap khác nhau thế nào?

**Heap** là vùng bộ nhớ cho các đối tượng và mảng Java. Số `used` của heap có thể gồm cả đối tượng còn được tham chiếu lẫn đối tượng đã trở thành rác nhưng chưa được bộ thu gom rác thu hồi.

**Non-heap** là nhóm vùng bộ nhớ JVM quản lý ngoài heap, phục vụ hoạt động thực thi, chẳng hạn cấu trúc mô tả lớp và mã máy do trình biên dịch JIT tạo ra. Hợp đồng và cách tổng hợp hai nhóm này được mô tả trong [MemoryMXBean](https://docs.oracle.com/en/java/javase/25/docs/api/java.management/java/lang/management/MemoryMXBean.html).

Hai hệ quả quan trọng:

1. Heap `used` không đồng nghĩa tổng kích thước đối tượng “thực sự còn sống”.
2. Non-heap không đồng nghĩa “toàn bộ phần còn lại của bộ nhớ tiến trình”.

Có thể hình dung hai đồng hồ này như hai góc quan sát về bộ nhớ do JVM quản lý. Không dùng chúng để suy ra rằng mọi vùng nhớ gốc của thư viện, bộ đệm, ngăn xếp luồng hay mọi trang bộ nhớ của tiến trình đều đã được thống kê đầy đủ.

## 3. Đọc đúng bốn trường của MemoryUsage

Tất cả giá trị dưới đây có đơn vị **byte** và kiểu `long`:

| Trường | Ý nghĩa |
| --- | --- |
| `init` | Lượng bộ nhớ ban đầu JVM yêu cầu để quản lý; có thể không xác định |
| `used` | Lượng đang được sử dụng ở ảnh chụp đó |
| `committed` | Lượng được bảo đảm sẵn có để JVM sử dụng cho vùng được đo |
| `max` | Giới hạn tối đa được báo cáo cho vùng đó; có thể không xác định |

`init` và `max` dùng **-1** để biểu thị không xác định. `used` và `committed` không âm; luôn có `used <= committed`. Nếu `max` xác định, có thêm `committed <= max`. `init` không phải cận dưới bất biến của `committed`: JVM có thể thay đổi lượng cam kết theo thời gian. Xem [MemoryUsage](https://docs.oracle.com/en/java/javase/25/docs/api/java.management/java/lang/management/MemoryUsage.html).

Ví dụ giả định, tính bằng MiB:

```text
used       = 48 MiB
committed  = 64 MiB
max        = 128 MiB
```

Có ba đại lượng khác nhau:

- `committed - used = 16 MiB`: phần chưa dùng trong lượng đã cam kết.
- `used / committed = 75%`: tỷ lệ dùng so với lượng đã cam kết.
- `used / max = 37.5%`: tỷ lệ dùng so với giới hạn được báo cáo.

Vì vậy, nhãn “bộ nhớ 75%” là thiếu thông tin. Cần nói rõ mẫu số.

`max - used` cũng không phải lời hứa mọi yêu cầu cấp phát nhỏ hơn phần chênh lệch đều thành công. JVM còn phải tăng cam kết khi cần; môi trường thực thi có thể không đáp ứng được yêu cầu đó. Hợp đồng của [MemoryUsage.getMax()](https://docs.oracle.com/en/java/javase/25/docs/api/java.management/java/lang/management/MemoryUsage.html#getMax()) nêu rõ giới hạn này.

Không dùng `max == -1` để kết luận máy có bộ nhớ vô hạn. Giá trị đó chỉ nói rằng giới hạn không xác định qua phép đo này.

## 4. Ví dụ chạy được: dữ liệu cố định và JVM thật

Chương trình sau có hai chế độ:

- Không có tham số: dùng ảnh chụp tự tạo để kiểm tra phép tính và stdout chính xác.
- `--live`: đọc số liệu thật từ JVM đang chạy chương trình.

Lưu thành **MemorySnapshotDemo.java**. Chương trình dùng API chuẩn, chạy trên Java 17 trở lên:

```java
import java.lang.management.ManagementFactory;
import java.lang.management.MemoryMXBean;
import java.lang.management.MemoryUsage;
import java.util.Locale;

public class MemorySnapshotDemo {
    private static final long MIB = 1024L * 1024L;

    public static void main(String[] args) {
        if (args.length == 0) {
            print("heap-demo", new MemoryUsage(
                    64L * MIB, 48L * MIB, 64L * MIB, 128L * MIB));
            print("nonheap-demo", new MemoryUsage(
                    -1L, 10L * MIB, 16L * MIB, -1L));
            return;
        }

        if (args.length == 1 && "--live".equals(args[0])) {
            MemoryMXBean bean = ManagementFactory.getMemoryMXBean();
            MemoryUsage heap = bean.getHeapMemoryUsage();
            MemoryUsage nonHeap = bean.getNonHeapMemoryUsage();
            print("heap-live", heap);
            print("nonheap-live", nonHeap);
            return;
        }

        throw new IllegalArgumentException("Use no arguments or --live");
    }

    private static void print(String name, MemoryUsage usage) {
        long used = usage.getUsed();
        long committed = usage.getCommitted();
        long max = usage.getMax();

        System.out.printf(Locale.ROOT,
                "%s init=%s used=%s committed=%s max=%s%n",
                name, size(usage.getInit()), size(used),
                size(committed), size(max));
        System.out.printf(Locale.ROOT,
                "  used/committed=%s used/max=%s committed-unused=%s%n",
                percentage(used, committed),
                percentage(used, max),
                size(committed - used));
    }

    private static String size(long bytes) {
        if (bytes < 0) {
            return "undefined";
        }
        return String.format(Locale.ROOT, "%.1fMiB", bytes / (double) MIB);
    }

    private static String percentage(long used, long denominator) {
        if (denominator <= 0) {
            return "n/a";
        }
        return String.format(Locale.ROOT,
                "%.1f%%", 100.0 * used / denominator);
    }
}
```

Biên dịch và chạy chế độ dữ liệu cố định:

```shell
javac MemorySnapshotDemo.java
java MemorySnapshotDemo
```

Stdout chính xác:

```text
heap-demo init=64.0MiB used=48.0MiB committed=64.0MiB max=128.0MiB
  used/committed=75.0% used/max=37.5% committed-unused=16.0MiB
nonheap-demo init=undefined used=10.0MiB committed=16.0MiB max=undefined
  used/committed=62.5% used/max=n/a committed-unused=6.0MiB
```

Các số ở chế độ này được tự tạo; chúng minh họa cách diễn giải, không phải kết quả đo một JVM thật.

Đọc JVM thật bằng:

```shell
java MemorySnapshotDemo --live
```

Các dòng có nhãn `heap-live` và `nonheap-live` vẫn theo cùng cấu trúc, nhưng số sẽ thay đổi theo JVM, cấu hình, bộ thu gom rác và thời điểm. Không kiểm thử chế độ này bằng một bộ số byte cố định.

Có thể chạy thêm với cấu hình heap khác:

```shell
java -Xms64m -Xmx128m MemorySnapshotDemo --live
```

`-Xms` và `-Xmx` là lựa chọn cấu hình heap, không phải giới hạn tổng bộ nhớ của tiến trình. Đọc giá trị JVM thực tế báo cáo thay vì suy ra mọi trường từ riêng hai cờ này.

### Vì sao mã tránh một số cách viết ngắn?

- Dùng `1024L * 1024L` và giữ số byte bằng `long`, tránh thu hẹp dữ liệu sang `int`.
- Dùng `double` khi chia để không mất phần thập phân.
- Kiểm tra mẫu số không dương để không chia cho 0 hoặc biến `max == -1` thành tỷ lệ sai.
- Dùng MiB đúng nghĩa `1024 * 1024` byte; không gắn nhãn MB cho cùng phép đổi.
- Lấy một đối tượng `MemoryUsage` cho mỗi vùng rồi đọc các trường từ ảnh chụp ấy.

Hai lệnh lấy heap và non-heap diễn ra nối tiếp, không tạo một ảnh chụp nguyên tử của toàn bộ tiến trình. Ứng dụng vẫn có thể cấp phát, nạp lớp hoặc chạy GC giữa hai lần gọi. Không dùng chênh lệch nhỏ giữa những phép đo khác thời điểm để khẳng định bộ nhớ đã “biến mất”.

## 5. Từ ảnh chụp sang quan sát xu hướng

Một điểm đo chỉ trả lời “đang thấy gì ở thời điểm đọc”. Để hiểu hành vi, hãy thu thập chuỗi có thời gian:

```text
timestamp, heap.used, heap.committed, heap.max,
           nonheap.used, nonheap.committed, nonheap.max
```

Đây là đề xuất cách tổ chức số liệu; không phải định dạng bắt buộc của JMX. Với hệ thống đo đạc, lưu các giá trị byte gốc, rồi đổi đơn vị khi hiển thị.

| Quan sát | Cách diễn giải hợp lý |
| --- | --- |
| Heap used tăng rồi giảm nhiều lần | Có thể là cấp phát và thu gom rác thông thường |
| Heap committed tăng trong khi used chưa cao | JVM có thể đang điều chỉnh sức chứa; chưa đủ để kết luận rò rỉ |
| Mức heap used sau những đợt GC tương đương tăng dần dưới tải ổn định | Dấu hiệu cần điều tra đối tượng bị giữ lại |
| Non-heap tăng lúc ứng dụng khởi động | Cần xem hoạt động nạp lớp và biên dịch mã trước khi kết luận |
| Bộ nhớ tiến trình tăng nhưng hai nhóm gần như ổn định | Cần mở rộng điều tra sang các vùng nhớ khác |

Các dòng trên là **giả thuyết chẩn đoán**, không phải quy luật bảo đảm. Tải, bộ đệm ứng dụng, quá trình khởi động và thuật toán GC có thể làm thay đổi biểu đồ.

Không gọi `bean.gc()` trước mỗi lần lấy mẫu để cố tạo “số đo chuẩn”. Nó làm thay đổi điều kiện quan sát. Thay vào đó, đối chiếu chuỗi bộ nhớ với hoạt động GC được ghi nhận riêng. Công cụ [JDK Flight Recorder và công cụ chẩn đoán JVM](https://docs.oracle.com/en/java/javase/25/troubleshoot/diagnostic-tools.html) hỗ trợ điều tra sâu hơn.

Nếu cần cảnh báo, thiết kế khoảng thời gian duy trì điều kiện và cách phục hồi cảnh báo; một lần tăng đột biến không nhất thiết là sự cố. Không coi một ngưỡng bộ nhớ đơn lẻ là cơ chế bảo đảm ứng dụng sẽ tự phục hồi khi hết bộ nhớ.

## 6. Khi nào cần đi sâu hơn MemoryMXBean?

### Xem từng vùng nhớ của JVM

`MemoryPoolMXBean` cung cấp số liệu theo từng pool, giúp phân biệt vùng nào đang tăng. Lấy danh sách qua `ManagementFactory.getMemoryPoolMXBeans()`; đọc `getType()` để phân loại `HEAP` hoặc `NON_HEAP`.

Không viết logic phụ thuộc duy nhất vào một tên pool cụ thể: danh sách và tên phụ thuộc cách triển khai JVM cùng bộ thu gom rác. API mô tả cách lấy số liệu chi tiết ở [MemoryPoolMXBean](https://docs.oracle.com/en/java/javase/25/docs/api/java.management/java/lang/management/MemoryPoolMXBean.html).

Nếu muốn dùng ngưỡng cảnh báo theo pool, phải kiểm tra khả năng hỗ trợ trước. Không giả định mọi pool đều hỗ trợ cùng loại ngưỡng.

### Xem bộ đệm trực tiếp và ánh xạ tệp

Đối với nhóm bộ đệm như direct/mapped, xem [BufferPoolMXBean](https://docs.oracle.com/en/java/javase/25/docs/api/java.management/java/lang/management/BufferPoolMXBean.html), lấy qua `ManagementFactory.getPlatformMXBeans(BufferPoolMXBean.class)`. Nó có các số ước lượng như lượng bộ nhớ sử dụng và tổng sức chứa bộ đệm.

Điểm này giúp tránh cách gọi sai “mọi bộ nhớ ngoài heap đều là số non-heap của MemoryMXBean”. Không cộng máy móc các nguồn số liệu có phạm vi khác nhau thành “tổng chính xác” nếu chưa hiểu chúng đo gì.

### Xem toàn bộ tiến trình

Để đánh giá bộ nhớ thường trú của tiến trình (RSS) hoặc giới hạn container, cần nguồn đo của hệ điều hành/môi trường triển khai. Với HotSpot, Native Memory Tracking có thể hỗ trợ phân tích các nhóm bộ nhớ gốc do JVM theo dõi; đó là công cụ bổ sung có giới hạn riêng, không phải trường thứ ba của `MemoryMXBean`. Hướng sử dụng nằm trong [tài liệu chẩn đoán JDK](https://docs.oracle.com/en/java/javase/25/troubleshoot/diagnostic-tools.html).

## 7. Lỗi thường gặp và cách tự kiểm tra

**“Heap đang dùng 90%, vậy chắc chắn sắp hết bộ nhớ.”**  
Cần biết 90% của committed hay max, tình trạng kéo dài bao lâu và GC có thu hồi được không. Một tỷ lệ không chứa đủ bối cảnh.

**“Max bằng -1 nên đổi thành 0 cho tiện vẽ biểu đồ.”**  
Làm vậy biến trạng thái không xác định thành một giới hạn có giá trị. Hãy lưu rõ trạng thái không xác định và không tính tỷ lệ theo max.

**“Heap used chính là số byte còn sống sau GC.”**  
Không đúng với ảnh chụp thông thường: rác chưa thu gom vẫn có thể được tính trong used.

**“Heap used cộng non-heap used là RSS.”**  
Hai phép đo khác phạm vi. Cần dùng số liệu tiến trình riêng.

**“Non-heap tăng thì tăng Xmx.”**  
Xmx cấu hình heap. Trước hết xác định thành phần đang tăng và giới hạn thực sự liên quan.

**“Số hiện tại tăng so với lần trước là rò rỉ.”**  
Cần dữ liệu theo thời gian, tải tương đương và bằng chứng về đối tượng/tài nguyên bị giữ lại.

Thực hành với chương trình:

1. Xác minh chế độ dữ liệu cố định cho đúng hai tỷ lệ 75.0% và 37.5%.
2. Xác minh ảnh chụp có max không xác định cho `used/max=n/a`.
3. Chạy `--live` nhiều lần và giải thích vì sao số liệu không nhất thiết giống nhau.
4. Đối chiếu hai lần chạy có cấu hình heap khác nhau, ghi rõ trường nào quan sát được thay đổi; không suy ra tổng bộ nhớ tiến trình từ các trường đó.

Kết quả cần đạt là đọc đúng từng trường, biết giới hạn của phép đo và chọn được nguồn quan sát tiếp theo khi câu hỏi vượt khỏi heap/non-heap tổng hợp.
