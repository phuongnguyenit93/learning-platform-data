# Chi phí giám sát và giới hạn khả năng đo trên từng JVM

## 1. Giám sát cũng là một phần công việc của ứng dụng

Một lệnh đọc chỉ số có thể trông rất đơn giản:

```java
int liveThreads = ManagementFactory.getThreadMXBean().getThreadCount();
```

Nhưng một hệ thống giám sát còn phải lấy mẫu, tạo dữ liệu, chuyển đổi định dạng, gửi qua mạng, lưu trữ và xử lý lỗi. Một phép đọc rẻ không có nghĩa toàn bộ đường thu thập miễn phí.

Mục tiêu là lấy đủ bằng chứng để hiểu ứng dụng với mức tác động phù hợp. Cần trả lời đồng thời:

1. JVM này có hỗ trợ phép đo không?
2. Tính năng cần thiết đã bật chưa?
3. Mẫu đọc hiện tại có giá trị hợp lệ không?
4. Việc thu thập với tần suất và mức chi tiết đã chọn ảnh hưởng ứng dụng ra sao?

API chung giúp mã truy cập nhất quán, nhưng không bảo đảm mọi JVM cung cấp cùng chi tiết, độ chính xác hoặc chi phí.

## 2. Chi phí nằm ở đâu?

| Thành phần | Chi phí có thể phát sinh |
| --- | --- |
| Đọc bộ đếm hoặc trạng thái hiện tại | Truy cập dữ liệu JVM, đồng bộ hóa hoặc tính toán nội bộ |
| Thu thập thông tin chi tiết | Duyệt nhiều luồng/pool, lấy stack trace, tìm quan hệ khóa |
| Tạo kết quả | Cấp phát đối tượng, sao chép mảng, định dạng chuỗi |
| Truy cập quản lý từ xa | Truyền mạng, tuần tự hóa, xử lý kết nối |
| Xuất số liệu | Bộ đệm, hàng đợi, mã hóa, nén, I/O |
| Lưu chuỗi có quá nhiều nhãn | Nhiều chuỗi thời gian, nhiều bộ nhớ và dữ liệu lưu trữ |

Không xếp mọi getter vào cùng một nhóm chi phí. Chẳng hạn, tài liệu [MemoryPoolMXBean](https://docs.oracle.com/en/java/javase/25/docs/api/java.management/java/lang/management/MemoryPoolMXBean.html) mô tả `getUsage()` thường là phép đọc nhẹ, nhưng một số pool có thể cần tính toán tốn kém hơn.

Tài liệu [ThreadMXBean](https://docs.oracle.com/en/java/javase/25/docs/api/java.management/java/lang/management/ThreadMXBean.html) cũng chỉ rõ việc bật đo CPU luồng có thể tốn kém trên một số triển khai; các thao tác tìm deadlock phục vụ chẩn đoán có thể đắt. Không suy ra “cùng thuộc MXBean” thì có cùng giá thành.

Một ví dụ số học giả định: nếu một tác vụ giám sát thực sự dùng 200 micro giây CPU mỗi lần và chạy 100 lần/giây, riêng phần đó dùng 20 mili giây CPU mỗi giây, tương đương 2% năng lực một CPU. Đây không phải số đo chung của JMX; chi phí thật phải đo với ứng dụng và JVM cụ thể.

## 3. Khả năng hỗ trợ, trạng thái bật và dữ liệu hợp lệ là ba lớp khác nhau

Không gom các tình huống sau thành số 0:

| Trạng thái | Ý nghĩa | Hướng xử lý |
| --- | --- | --- |
| Không hỗ trợ | JVM không cung cấp phép đo | Đánh dấu khả năng không có; chọn nguồn khác nếu cần |
| Có hỗ trợ nhưng chưa bật | Tính năng tồn tại nhưng đang tắt | Báo trạng thái; quyết định bật riêng với chi phí được xem xét |
| Đã bật nhưng mẫu chưa có | Chưa thu được giá trị dùng được tại thời điểm đọc | Giữ trạng thái thiếu dữ liệu |
| Có mẫu bằng 0 | Phép đo hợp lệ báo giá trị 0 | Ghi nhận 0 đúng nghĩa |
| Đọc lỗi | Có sự cố khi lấy dữ liệu | Ghi nhận lỗi và thời điểm mẫu thành công gần nhất |

Ví dụ đối với CPU của luồng:

- `isCurrentThreadCpuTimeSupported()` kiểm tra khả năng đo CPU của luồng nền tảng hiện tại.
- `isThreadCpuTimeEnabled()` kiểm tra tính năng đã bật.
- `getCurrentThreadCpuTime()` vẫn có thể trả `-1` khi không có số liệu hợp lệ theo hợp đồng.

Xem [hợp đồng ThreadMXBean](https://docs.oracle.com/en/java/javase/25/docs/api/java.management/java/lang/management/ThreadMXBean.html). Đừng gọi phương thức kiểm tra enabled vô điều kiện trên một khả năng hoàn toàn không được hỗ trợ.

Dấu hiệu thiếu dữ liệu phụ thuộc từng API: có nơi dùng số âm, nơi dùng `null`, nơi ném `UnsupportedOperationException`. Không đặt quy tắc chung rằng mọi trường số âm đều phải đổi thành 0.

Ví dụ khác: [ManagementFactory.getCompilationMXBean()](https://docs.oracle.com/en/java/javase/25/docs/api/java.management/java/lang/management/ManagementFactory.html#getCompilationMXBean()) có thể trả `null` nếu JVM không có hệ thống biên dịch. Khi bean có tồn tại, còn cần kiểm tra `isCompilationTimeMonitoringSupported()` trước khi đọc thời gian biên dịch.

## 4. Ví dụ chạy được: phát hiện khả năng và lấy mẫu có giới hạn

Chương trình sau không tự bật tính năng đo mới và không lấy toàn bộ stack trace. Nó có hai chế độ:

- Mặc định: minh họa bốn trạng thái dữ liệu bằng đầu vào cố định.
- `--live`: đọc khả năng của JVM và lấy ba mẫu nhỏ.

Lưu thành **MonitoringCapabilityDemo.java**, dùng Java 17 trở lên:

```java
import java.lang.management.ClassLoadingMXBean;
import java.lang.management.CompilationMXBean;
import java.lang.management.ManagementFactory;
import java.lang.management.MemoryMXBean;
import java.lang.management.ThreadMXBean;

public class MonitoringCapabilityDemo {
    public static void main(String[] args) throws InterruptedException {
        if (args.length == 0) {
            System.out.println(state(false, false, -1L));
            System.out.println(state(true, false, -1L));
            System.out.println(state(true, true, -1L));
            System.out.println(state(true, true, 0L));
            return;
        }

        if (args.length != 1 || !"--live".equals(args[0])) {
            throw new IllegalArgumentException("Use no arguments or --live");
        }

        ThreadMXBean threads = ManagementFactory.getThreadMXBean();
        MemoryMXBean memory = ManagementFactory.getMemoryMXBean();
        ClassLoadingMXBean classes = ManagementFactory.getClassLoadingMXBean();

        boolean cpuSupported = threads.isCurrentThreadCpuTimeSupported();
        boolean cpuEnabled = cpuSupported && threads.isThreadCpuTimeEnabled();
        long cpuNanos = cpuEnabled ? threads.getCurrentThreadCpuTime() : -1L;
        System.out.println("current-platform-thread-cpu="
                + state(cpuSupported, cpuEnabled, cpuNanos));

        boolean contentionSupported =
                threads.isThreadContentionMonitoringSupported();
        String contention = !contentionSupported ? "UNSUPPORTED"
                : threads.isThreadContentionMonitoringEnabled()
                        ? "ENABLED" : "DISABLED";
        System.out.println("thread-contention=" + contention);

        CompilationMXBean compilation = ManagementFactory.getCompilationMXBean();
        if (compilation == null) {
            System.out.println("compilation-time=NO_BEAN");
        } else if (!compilation.isCompilationTimeMonitoringSupported()) {
            System.out.println("compilation-time=UNSUPPORTED");
        } else {
            System.out.println("compilation-time-ms="
                    + compilation.getTotalCompilationTime());
        }

        threads.getThreadCount();
        memory.getHeapMemoryUsage();
        classes.getLoadedClassCount();

        for (int i = 1; i <= 3; i++) {
            long start = System.nanoTime();
            int threadCount = threads.getThreadCount();
            long heapUsed = memory.getHeapMemoryUsage().getUsed();
            int classCount = classes.getLoadedClassCount();
            long elapsedNanos = System.nanoTime() - start;

            System.out.println("sample=" + i
                    + " platform-threads=" + threadCount
                    + " heap-used-bytes=" + heapUsed
                    + " loaded-classes=" + classCount
                    + " local-read-wall-ns=" + elapsedNanos);
            if (i < 3) {
                Thread.sleep(200L);
            }
        }
    }

    private static String state(
            boolean supported, boolean enabled, long value) {
        if (!supported) {
            return "UNSUPPORTED";
        }
        if (!enabled) {
            return "DISABLED";
        }
        if (value < 0L) {
            return "UNAVAILABLE";
        }
        return "AVAILABLE:" + value;
    }
}
```

Biên dịch và chạy chế độ cố định:

```shell
javac MonitoringCapabilityDemo.java
java MonitoringCapabilityDemo
```

Stdout chính xác:

```text
UNSUPPORTED
DISABLED
UNAVAILABLE
AVAILABLE:0
```

Đây là kiểm tra cách biểu diễn trạng thái, không giả lập một JVM.

Đọc JVM thật:

```shell
java MonitoringCapabilityDemo --live
```

Kết quả gồm thông tin hỗ trợ và ba dòng `sample=1`, `sample=2`, `sample=3`. Số luồng, bộ nhớ, lớp, thời gian và trạng thái thực tế phụ thuộc môi trường; không kiểm thử bằng một bộ giá trị cố định.

### Ví dụ chứng minh và chưa chứng minh điều gì?

Nó chứng minh cách kiểm tra hỗ trợ trước khi đọc và cách giữ số 0 khác thiếu dữ liệu. Vòng lặp hữu hạn tránh biến ví dụ thành tác vụ nền không có điểm kết thúc.

`local-read-wall-ns` đo khoảng thời gian trôi qua cho nhóm lời gọi cục bộ ở mỗi mẫu. Nó **không phải** toàn bộ chi phí giám sát:

- Không gồm phần in dòng kết quả vì phép in ở sau mốc kết thúc.
- Không gồm đường xuất dữ liệu qua mạng hoặc lưu trữ.
- Có thể chịu ảnh hưởng của lập lịch luồng, JIT, GC và độ phân giải bộ đếm thời gian.
- Một vài mẫu không đủ để xác định phân bố chi phí hoặc so sánh JVM.

Các lời gọi làm nóng trước vòng lặp chỉ giảm một phần ảnh hưởng lần đầu; chúng không biến chương trình thành bộ đo hiệu năng chuẩn.

## 5. Giới hạn dữ liệu còn phụ thuộc đối tượng được quan sát

Trên Java hiện đại có luồng ảo, `ThreadMXBean` hỗ trợ các luồng nền tảng (platform thread), không hỗ trợ giám sát/quản lý luồng ảo qua giao diện này. Vì vậy, số luồng thấp từ bean không chứng minh ứng dụng có ít công việc đồng thời.

Tương tự:

- Không phải mọi pool đều hỗ trợ ngưỡng bộ nhớ; kiểm tra phương thức hỗ trợ của từng pool.
- Tên và danh sách GC/pool có thể khác giữa JVM hoặc thuật toán thu gom.
- API mở rộng theo nhà cung cấp cần được kiểm tra kiểu và sự hiện diện.
- Runtime được thu gọn có thể không chứa mọi mô-đun của JDK đầy đủ.
- Cấu hình container và cách JVM nhìn tài nguyên ảnh hưởng phạm vi số liệu hệ thống.

Đối với công cụ ghi sự kiện, [FlightRecorder.isAvailable()](https://docs.oracle.com/en/java/javase/25/docs/api/jdk.jfr/jdk/jfr/FlightRecorder.html#isAvailable()) là phép kiểm tra khả năng của JVM khi API/mô-đun JFR có trong runtime. “Có khả năng JFR” không đồng nghĩa phiên ghi đã chạy hoặc mọi sự kiện cần thiết đều đã bật.

Khả năng có tồn tại không thay thế việc đọc hợp đồng dữ liệu. Ví dụ [CompilationMXBean](https://docs.oracle.com/en/java/javase/25/docs/api/java.management/java/lang/management/CompilationMXBean.html) nêu thời gian biên dịch không được dùng như thước đo so sánh hiệu năng các JVM có cách định nghĩa/đo khác nhau.

## 6. Chọn tần suất theo câu hỏi và mức chi tiết

Không có tần suất duy nhất phù hợp cho mọi chỉ số. Có thể thiết kế theo hai mức:

| Nhu cầu | Cách tiếp cận |
| --- | --- |
| Nhìn xu hướng dài hạn | Lấy nhóm số tổng hợp nhỏ với chu kỳ ổn định |
| Điều tra sự cố trong một khoảng | Tạm thu chi tiết cần thiết, có thời hạn và giới hạn dữ liệu |

Đây là hướng thiết kế, không phải cam kết rằng mọi số tổng hợp đều rẻ hoặc mọi thu thập chi tiết đều đắt như nhau.

Lấy mẫu nhanh hơn có thể thấy thêm biến động, nhưng không tạo thông tin mà nguồn đo không cung cấp. Chẳng hạn, đọc một số tổng GC liên tục không thể khôi phục đầy đủ phân bố độ trễ từng sự kiện.

Một số nguyên tắc thực hành:

- Giảm số phép đọc và dữ liệu không cần cho câu hỏi hiện tại.
- Không lấy toàn bộ stack trace ở mỗi lần kiểm tra sức khỏe chỉ để biết số luồng.
- Chọn độ sâu stack và thông tin khóa theo mục đích khi thực sự cần.
- Tránh nhiều bộ thu cùng đọc một tập số liệu với tần suất cao mà không có kế hoạch.
- Với nhiều phiên bản ứng dụng, có thể làm lệch lịch lấy mẫu để giảm đợt tải đồng thời.
- Không gọi GC, reset bộ đếm hoặc bật tùy chọn chẩn đoán chỉ để tạo số đo “đẹp”.

Khi ghi sự kiện, cấu hình cũng là một phần của chi phí. [Tài liệu chẩn đoán JDK](https://docs.oracle.com/en/java/javase/25/troubleshoot/diagnostic-tools.html) phân biệt các cấu hình JFR với mức dữ liệu và tác động khác nhau; không suy ra một phần trăm overhead cố định cho mọi cấu hình và tải.

## 7. Bộ thu chậm hoặc lỗi không nên tích lũy vô hạn

Nếu lấy mẫu mất 3 giây nhưng cứ mỗi giây lại xếp thêm một tác vụ mới, hàng đợi giám sát có thể lớn dần. Bộ thu lúc đó tự tạo áp lực CPU, bộ nhớ và I/O.

Hãy định nghĩa rõ:

- Một nguồn có được lấy mẫu chồng lấn không?
- Khi quá chậm, bỏ lần lấy mẫu, giảm tần suất hay giữ một hàng đợi có giới hạn?
- Khi lỗi, có tăng khoảng chờ trước lần thử tiếp theo không?
- Dữ liệu cũ được đánh dấu hết hạn sau bao lâu?
- Ai dừng tác vụ nền và đóng tài nguyên khi ứng dụng kết thúc?

Đối với truy cập từ xa, một timeout ở bên chờ không phải lời hứa công việc trong JVM đích đã dừng ngay. Cần hiểu khả năng hủy và giới hạn thực tế của công cụ dùng.

Ghi nhận riêng thời điểm thành công gần nhất, số lần lỗi và thời gian thu thập. Nếu mẫu không đến, đừng để một giá trị cũ trông như giá trị mới. Một bộ thu đã hỏng không được khiến màn hình tiếp tục khẳng định ứng dụng khỏe từ dữ liệu hết hạn.

## 8. Đo tác động bằng so sánh có kiểm soát

Để đánh giá cấu hình giám sát thực tế:

1. Chọn cùng ứng dụng, JDK, cấu hình tài nguyên và tải đại diện.
2. Đo mức nền với cấu hình giám sát tối thiểu cần thiết.
3. Bật cấu hình cần đánh giá, giữ các điều kiện còn lại tương đương.
4. So sánh thông lượng, phân bố độ trễ, CPU, cấp phát, GC và lượng I/O.
5. Lặp lại đủ để phân biệt thay đổi ổn định với dao động do môi trường.
6. Thử cả trạng thái xuất dữ liệu chậm/lỗi, không chỉ đường thành công.

Ví dụ giả định thông lượng giảm từ 1000 xuống 970 yêu cầu/giây dưới điều kiện so sánh tương đương: mức giảm là 3%. Con số đó mô tả thử nghiệm cụ thể, không trở thành “overhead của JMX” nói chung.

Không chỉ nhìn trung bình. Một phép thu chi tiết hiếm gặp có thể ảnh hưởng phần đuôi độ trễ mà trung bình che đi. Ngược lại, phần trăm khác nhỏ trong một thử nghiệm nhiễu chưa đủ để kết luận nguyên nhân.

Ghi lại chính sách thu thập cùng kết quả: tập chỉ số/sự kiện, chu kỳ, độ sâu, nhãn, nơi xuất và giới hạn dữ liệu. Không có cấu hình cụ thể thì một con số chi phí rất khó tái kiểm chứng.

## 9. Tự kiểm tra

1. Getter trả số 0 có luôn có nghĩa “không có dữ liệu” không? **Không**, phải đọc hợp đồng của từng trường.
2. JVM hỗ trợ CPU time có bảo đảm tính năng đã bật không? **Không.**
3. Đo ba getter bằng nanoTime có xác định overhead toàn hệ thống không? **Không.**
4. ThreadMXBean có bao quát luồng ảo không? **Không** trên hợp đồng Java hiện đại đang dùng.
5. Lấy mẫu nhanh hơn có làm số tổng thành bản ghi từng sự kiện không? **Không.**
6. Bộ thu bị chậm cần làm gì trước hết? **Giữ giới hạn tài nguyên và biểu diễn rõ dữ liệu thiếu/cũ**, thay vì tiếp tục xếp công việc vô hạn.

Mục tiêu là xây phép quan sát có phạm vi rõ, thích nghi với khả năng của JVM và có chi phí đã được kiểm chứng trong điều kiện sử dụng thực tế.
