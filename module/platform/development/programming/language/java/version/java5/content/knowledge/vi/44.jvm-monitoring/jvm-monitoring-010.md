# OperatingSystemMXBean và giới hạn ý nghĩa số liệu hệ thống

## 1. Trước khi đọc số, xác định nó đang đo gì

Khi quan sát một ứng dụng Java, các câu hỏi sau có liên quan nhưng không giống nhau:

- JVM đang chạy trên hệ điều hành và kiến trúc nào?
- JVM thấy bao nhiêu bộ xử lý có thể sử dụng?
- Môi trường thực thi đang chịu tải ra sao?
- Riêng tiến trình JVM dùng bao nhiêu CPU?
- Bộ nhớ của môi trường còn trống bao nhiêu, và heap của JVM còn chỗ hay không?

`OperatingSystemMXBean` cung cấp góc quan sát về hệ điều hành/môi trường thực thi. Nó không thay thế mọi công cụ giám sát tiến trình và không phải bean quản lý heap.

Một cách đọc số liệu đúng là luôn ghi rõ **nguồn, phạm vi, đơn vị, khoảng thời gian và trạng thái không có dữ liệu**. Hai màn hình cùng ghi “CPU 50%” vẫn có thể nói về hai đại lượng khác nhau.

## 2. Giao diện chuẩn cung cấp những gì?

Lấy bean cục bộ của JVM đang chạy mã:

```java
// Đoạn minh họa; cần import từ java.lang.management.
OperatingSystemMXBean os = ManagementFactory.getOperatingSystemMXBean();
```

Tên JMX là `java.lang:type=OperatingSystem`. Giao diện chuẩn ở gói `java.lang.management` có các phương thức chính:

| Phương thức | Cách đọc |
| --- | --- |
| `getName()` | Tên hệ điều hành |
| `getVersion()` | Phiên bản hệ điều hành được báo cáo |
| `getArch()` | Kiến trúc hệ điều hành được báo cáo |
| `getAvailableProcessors()` | Số bộ xử lý khả dụng đối với JVM |
| `getSystemLoadAverage()` | Tải trung bình hệ thống trong phút gần nhất; số âm nếu không có |

Theo [OperatingSystemMXBean chuẩn](https://docs.oracle.com/en/java/javase/25/docs/api/java.management/java/lang/management/OperatingSystemMXBean.html), số bộ xử lý khả dụng không nhỏ hơn 1 và có thể thay đổi trong vòng đời JVM. Đừng mặc định nó là số nhân vật lý của máy chủ hoặc toàn bộ năng lực CPU trên hạ tầng.

`getSystemLoadAverage()` là tín hiệu tải có cách tính phụ thuộc hệ điều hành. Nó không phải một tỷ lệ phần trăm CPU, không nằm trong thang bắt buộc 0 đến 1 và không phải số đo riêng của tiến trình Java.

Ví dụ `loadAverage=1.5` không có nghĩa CPU dùng 150%. Nếu một nền tảng không cung cấp giá trị này, giữ trạng thái “không có dữ liệu”; không hiển thị số âm như tải âm hoặc đổi thành “hệ thống rảnh”.

## 3. Giao diện mở rộng và phạm vi hỗ trợ

Trên các JDK hỗ trợ, bean có thể đồng thời triển khai:

```text
java.lang.management.OperatingSystemMXBean
    -> com.sun.management.OperatingSystemMXBean
```

Giao diện mở rộng cung cấp thêm số liệu CPU, bộ nhớ và swap. Đây là API mở rộng theo nền tảng của JDK, không phải cam kết mọi triển khai Java đều có. Kiểm tra bằng `instanceof` trước khi sử dụng.

Các phương thức hiện dùng cho bài này:

| Phương thức mở rộng | Đơn vị / ý nghĩa |
| --- | --- |
| `getCpuLoad()` | Mức sử dụng CPU gần đây của môi trường, thang 0..1; âm nếu không có |
| `getProcessCpuLoad()` | Mức sử dụng CPU gần đây của tiến trình JVM, thang 0..1; âm nếu không có |
| `getProcessCpuTime()` | Thời gian CPU tích lũy của tiến trình, nano giây; -1 nếu không hỗ trợ |
| `getTotalMemorySize()` | Tổng bộ nhớ theo phạm vi môi trường được báo cáo, byte |
| `getFreeMemorySize()` | Bộ nhớ trống theo phạm vi môi trường được báo cáo, byte |
| `getCommittedVirtualMemorySize()` | Bộ nhớ ảo được bảo đảm cho tiến trình, byte; -1 nếu không hỗ trợ |

Hợp đồng của [OperatingSystemMXBean mở rộng](https://docs.oracle.com/en/java/javase/25/docs/api/jdk.management/com/sun/management/OperatingSystemMXBean.html) mô tả môi trường có thể là hệ điều hành gốc, môi trường ảo hóa hoặc môi trường do container quản lý.

Với Java 17 trở lên, dùng các tên phương thức hiện hành trong bảng. Không cần thêm thư viện ngoài để chạy ví dụ trên JDK cung cấp mô-đun `jdk.management`. Nếu ứng dụng dùng mô-đun có tên, khai báo phụ thuộc mô-đun thích hợp khi tích hợp mã.

## 4. CPU load và thời gian CPU là hai loại số liệu

### CPU load gần đây

Giá trị `0.25` từ `getProcessCpuLoad()` được hiển thị thành 25%. Theo hợp đồng, nó liên quan đến hoạt động của các luồng trong tiến trình JVM, gồm cả luồng ứng dụng và luồng nội bộ JVM.

Không nhân giá trị ấy thêm với số CPU để rồi vẫn đặt nhãn “phần trăm toàn môi trường”. Khoảng quan sát của các phương thức load phụ thuộc cách triển khai; lần gọi đầu tiên có khoảng quan sát chưa xác định. Những nơi gọi khác cũng có thể ảnh hưởng khoảng quan sát và kết quả. Xem [getProcessCpuLoad()](https://docs.oracle.com/en/java/javase/25/docs/api/jdk.management/com/sun/management/OperatingSystemMXBean.html#getProcessCpuLoad()) và [getCpuLoad()](https://docs.oracle.com/en/java/javase/25/docs/api/jdk.management/com/sun/management/OperatingSystemMXBean.html#getCpuLoad()).

### CPU time tích lũy

CPU time đo thời gian các CPU thực sự thực hiện công việc cho tiến trình, không phải thời gian trên đồng hồ. Các luồng có thể chạy song song trên nhiều CPU nên hiệu CPU time có thể lớn hơn thời gian thực trôi qua.

Ví dụ giả định trong 1 giây thực:

```text
CPU time của tiến trình tăng 2 giây
Số bộ xử lý dùng làm mẫu số giả định: 4
```

Khi đó:

- So với năng lực của **một CPU**, tỷ lệ là `2 / 1 * 100 = 200%`.
- Chuẩn hóa theo **4 CPU**, tỷ lệ là `2 / (1 * 4) * 100 = 50%`.

Cả hai cách tính có thể hữu ích nếu gắn nhãn và mẫu số rõ ràng. Số trên 100% ở cách thứ nhất không tự động là lỗi.

Tỷ lệ tự tính này là phép quan sát theo khoảng do ứng dụng chọn, không phải lời hứa sẽ trùng `getProcessCpuLoad()`. Khác biệt về cửa sổ đo, thời điểm lấy mẫu và hạn mức CPU có thể làm kết quả khác nhau.

## 5. Ví dụ chạy được: đọc số và xử lý không có dữ liệu

Lưu thành **OsMetricsDemo.java**, dùng Java 17 trở lên:

```java
import java.lang.management.ManagementFactory;
import java.lang.management.OperatingSystemMXBean;
import java.util.Locale;

public class OsMetricsDemo {
    public static void main(String[] args) throws InterruptedException {
        if (args.length == 0) {
            System.out.println("process-load=" + percent(0.25));
            System.out.println("unavailable-load=" + percent(-1.0));
            cpuRatios(1_000_000_000L, 3_000_000_000L,
                    1_000_000_000L, 4);
            cpuRatios(-1L, -1L, 1_000_000_000L, 4);
            return;
        }

        if (args.length != 1 || !"--live".equals(args[0])) {
            throw new IllegalArgumentException("Use no arguments or --live");
        }

        OperatingSystemMXBean os = ManagementFactory.getOperatingSystemMXBean();
        System.out.println("os=" + os.getName());
        System.out.println("version=" + os.getVersion());
        System.out.println("arch=" + os.getArch());
        System.out.println("available-processors=" + os.getAvailableProcessors());

        double loadAverage = os.getSystemLoadAverage();
        System.out.println("load-average-1m="
                + (loadAverage < 0.0 ? "n/a" : number(loadAverage)));

        if (!(os instanceof com.sun.management.OperatingSystemMXBean extended)) {
            System.out.println("extended-metrics=unsupported");
            return;
        }

        System.out.println("environment-cpu-load=" + percent(extended.getCpuLoad()));
        System.out.println("process-cpu-load="
                + percent(extended.getProcessCpuLoad()));
        System.out.println("environment-total-memory="
                + bytes(extended.getTotalMemorySize()));
        System.out.println("environment-free-memory="
                + bytes(extended.getFreeMemorySize()));
        System.out.println("process-committed-virtual-memory="
                + bytes(extended.getCommittedVirtualMemorySize()));

        int processorsBefore = os.getAvailableProcessors();
        long wallBefore = System.nanoTime();
        long cpuBefore = extended.getProcessCpuTime();
        Thread.sleep(1000L);
        long cpuAfter = extended.getProcessCpuTime();
        long wallAfter = System.nanoTime();
        int processorsAfter = os.getAvailableProcessors();

        if (processorsBefore != processorsAfter) {
            System.out.println("derived-cpu-ratios=n/a: processor-count-changed");
            return;
        }
        cpuRatios(cpuBefore, cpuAfter, wallAfter - wallBefore, processorsAfter);
    }

    private static String percent(double value) {
        if (!Double.isFinite(value) || value < 0.0 || value > 1.0) {
            return "n/a";
        }
        return number(value * 100.0) + "%";
    }

    private static String bytes(long value) {
        return value < 0L ? "n/a" : value + "B";
    }

    private static String number(double value) {
        return String.format(Locale.ROOT, "%.2f", value);
    }

    private static void cpuRatios(
            long before, long after, long elapsedNanos, int processors) {
        if (before < 0L || after < before
                || elapsedNanos <= 0L || processors <= 0) {
            System.out.println("derived-cpu-ratios=n/a");
            return;
        }

        double oneCpuPercent = 100.0 * (after - before) / elapsedNanos;
        double normalizedPercent = oneCpuPercent / processors;
        System.out.println("cpu-vs-one=" + number(oneCpuPercent)
                + "% cpu-vs-available=" + number(normalizedPercent) + "%");
    }
}
```

Biên dịch và chạy dữ liệu cố định:

```shell
javac OsMetricsDemo.java
java OsMetricsDemo
```

Stdout chính xác:

```text
process-load=25.00%
unavailable-load=n/a
cpu-vs-one=200.00% cpu-vs-available=50.00%
derived-cpu-ratios=n/a
```

Dữ liệu mặc định chỉ kiểm tra phép định dạng và tính tỷ lệ. Nó không mô phỏng mức dùng CPU thật.

Đọc môi trường thực:

```shell
java OsMetricsDemo --live
```

Các giá trị thay đổi theo hệ điều hành, bản JDK và tải. Không có một bộ stdout số học cố định cho chế độ này. Load average có thể là `n/a`; các số mở rộng cũng có thể không hỗ trợ.

### Giới hạn của phép lấy mẫu trong ví dụ

- Dùng thời gian thực từ `System.nanoTime()`, không coi một lần ngủ là đúng một giây tuyệt đối.
- Giữ CPU time và số byte bằng `long`.
- Không trừ hai giá trị không hỗ trợ để tạo ra hiệu bằng 0.
- Không ghép bộ đếm qua các lần khởi động JVM.
- Kiểm tra số CPU ở hai đầu chỉ phát hiện một số thay đổi; không bảo đảm năng lực CPU không đổi trong toàn khoảng.
- Các phương thức được gọi nối tiếp, không tạo ảnh chụp nguyên tử của cả môi trường.

Mẫu số “số bộ xử lý khả dụng” là lựa chọn minh họa. Với hạn mức container phân số hoặc cấu hình CPU đặc biệt, cần xác minh mẫu số có đại diện đúng năng lực muốn so sánh không.

## 6. Container và máy chủ: đừng suy ra phạm vi chỉ từ tên phương thức

Ứng dụng chạy trong container vẫn chia sẻ hạ tầng với các tiến trình khác. Phạm vi dữ liệu bean phản ánh phụ thuộc hệ điều hành, JVM, bản JDK và cấu hình nhận biết giới hạn tài nguyên.

Khi đưa lên hệ thống giám sát, xác minh:

1. Số CPU JVM báo cáo có phù hợp giới hạn thực tế và cấu hình triển khai không?
2. Số bộ nhớ tổng/free đang nói về phạm vi nào trong môi trường này?
3. Chỉ số từ agent hạ tầng đang đo host, container hay tiến trình?
4. Hai số định so sánh có cùng phạm vi và khoảng thời gian không?

Không mặc định `getCpuLoad()` luôn là tải toàn máy vật lý, hoặc mọi phương thức trên mọi hệ điều hành luôn trả số container giống nhau. Cũng không dùng số CPU nguyên JVM nhìn thấy để suy ra chính xác mọi hạn mức thời gian CPU phân số.

Thay đổi JDK hoặc cấu hình triển khai có thể làm cách JVM nhìn tài nguyên khác đi. Ghi nhận thông tin môi trường để giải thích sự thay đổi, thay vì tự kết luận hiệu năng ứng dụng đã thay đổi tương ứng.

## 7. Bộ nhớ hệ thống khác bộ nhớ tiến trình và heap

Ba nhầm lẫn thường gặp:

**Free memory của môi trường không phải phần heap còn trống.**  
Muốn biết heap, dùng `MemoryMXBean`. Môi trường còn nhiều bộ nhớ không có nghĩa heap được cấu hình còn chỗ.

**Total trừ free không phải bộ nhớ của riêng Java.**  
Đó là phép chênh lệch theo phạm vi môi trường được báo cáo, không xác định tiến trình nào đang sử dụng. Ngoài ra, cách hệ điều hành quản lý bộ đệm và trang nhớ ảnh hưởng ý nghĩa “trống”.

**Committed virtual memory không phải bộ nhớ thường trú RSS.**  
Bộ nhớ ảo được bảo đảm cho tiến trình không đồng nghĩa số trang vật lý hiện nằm trong RAM, và cũng không đồng nghĩa heap committed. Không đặt cùng nhãn cho ba số này.

Nếu câu hỏi là “tiến trình Java chiếm bao nhiêu RAM thường trú” hoặc “container có nguy cơ chạm giới hạn bộ nhớ không”, dùng nguồn số liệu của tiến trình/container tương ứng, rồi đối chiếu với heap và các phần bộ nhớ JVM. Không suy ra tất cả từ một trường của bean OS.

## 8. Dùng số liệu để định hướng, không kết luận một bước

| Quan sát | Hướng kiểm tra tiếp |
| --- | --- |
| Process CPU load cao kéo dài | Lấy hồ sơ CPU, xem luồng và tải ứng dụng |
| Environment CPU load cao nhưng process load thấp | Xem tiến trình khác, năng lực cấp cho ứng dụng và hạ tầng |
| Load average cao | Kiểm tra định nghĩa nền tảng và trạng thái công việc, không đổi trực tiếp sang CPU% |
| Phản hồi chậm trong khi process CPU thấp | Điều tra chờ I/O, khóa, hàng đợi hoặc phụ thuộc bên ngoài |
| Bộ nhớ môi trường trống ít | Kiểm tra áp lực bộ nhớ và giới hạn đúng phạm vi; không tự kết luận heap rò rỉ |

Đây là giả thuyết điều tra. Một ảnh chụp CPU thấp có thể bỏ lỡ đợt tăng ngắn, và số load gần đây không giải thích chính xác yêu cầu cụ thể bị chậm ở đâu.

Khi xây chỉ số, đặt tên thể hiện phạm vi: `environment_cpu_load`, `jvm_process_cpu_load`, `jvm_process_cpu_time_ns`. Giữ riêng trạng thái không hỗ trợ; không để số 0 giả tạo làm hệ thống báo “khỏe” khi nguồn đo không có dữ liệu.

## 9. Tự kiểm tra

1. Load average bằng 2 có nghĩa CPU 200% không? **Không.**
2. Process CPU time tăng 2 giây trong 1 giây thực có hợp lý không? **Có**, khi công việc chạy song song trên nhiều CPU.
3. Giá trị load âm nên hiển thị ra sao? **Không có dữ liệu**, không phải CPU rảnh.
4. Có thể ép kiểu vô điều kiện sang giao diện mở rộng không? **Không**, hãy kiểm tra khả năng hỗ trợ.
5. Free memory còn nhiều có chứng minh heap không thể hết chỗ không? **Không.**
6. Hai biểu đồ CPU cùng ghi phần trăm có so sánh trực tiếp được không? **Chỉ sau khi xác minh cùng phạm vi, mẫu số và cửa sổ đo.**

Kỹ năng cần đạt là đọc số liệu kèm ý nghĩa và giới hạn của nó, từ đó chọn đúng phép đo bổ sung trước khi thay đổi cấu hình hay kết luận nguyên nhân.
