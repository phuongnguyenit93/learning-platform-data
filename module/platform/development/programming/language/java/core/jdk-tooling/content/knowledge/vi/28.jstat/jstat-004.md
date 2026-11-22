# Đọc class loading statistics bằng jstat

Class loading statistics cho biết JVM đã nạp và gỡ bao nhiêu class, khối lượng dữ liệu class đã xử lý và thời gian dành cho thao tác nạp/gỡ class. Đây là dữ liệu hữu ích khi kiểm tra startup chậm, ứng dụng liên tục sinh class mới, plugin được nạp động, hot redeploy hoặc nghi ngờ class loader leak làm Metaspace tăng.

Trong JDK 17, lệnh chính cho bài này là `jstat -class`. Output có năm cột: `Loaded`, `Bytes`, `Unloaded`, `Bytes` và `Time`. Bài hướng dẫn cách lấy mẫu, đọc từng cột, phân biệt số liệu tích lũy với số class hiện đang tồn tại, nhận diện xu hướng bất thường và chọn công cụ sâu hơn khi cần xem thống kê theo từng class loader.

> **Lưu ý về công cụ:** Oracle đánh dấu `jstat` là experimental và unsupported; định dạng hoặc tùy chọn có thể thay đổi ở các bản JDK sau. Hãy kiểm tra `jstat -options` trên đúng JDK đang dùng và tránh viết parser phụ thuộc lâu dài vào định dạng output.

## 1. Class loading trong JVM là gì?

Trước khi đọc số liệu, cần hiểu JVM đang đếm điều gì.

Class loading là quá trình JVM tìm và nạp định nghĩa class vào runtime. Class loader tìm bytecode, JVM đọc và tạo biểu diễn class, sau đó liên kết và khởi tạo class khi cần.

Các giai đoạn thường được nhắc tới:

1. **Loading:** tìm bytecode theo tên class và tạo đối tượng biểu diễn class trong JVM.
2. **Linking:** kiểm tra bytecode (verification), chuẩn bị cấu trúc dữ liệu (preparation) và giải quyết symbolic references (resolution).
3. **Initialization:** chạy các static initializer và gán giá trị khởi tạo cho static field theo quy tắc Java.

`jstat -class` phản ánh hoạt động class loader ở mức thống kê tổng hợp. Nó không hiển thị tên từng class hoặc stack trace đã yêu cầu nạp class.

### 1.1. Class loader và danh tính của class

Java có nhiều loại class loader:

- **Bootstrap class loader:** nạp các class nền tảng của Java.
- **Platform class loader:** nạp các module/platform class được giao cho platform loader.
- **Application class loader:** thường nạp class trên application classpath/module path.
- **Custom class loader:** do ứng dụng hoặc framework tạo, ví dụ plugin loader, application server loader, module loader.

Danh tính của một class không chỉ là tên đầy đủ. Nó gắn với tên class và class loader đã định nghĩa class đó. Hai class cùng tên nhưng do hai loader khác nhau định nghĩa có thể là hai kiểu khác nhau; điều này ảnh hưởng tới cast, tương thích kiểu và việc unload class.

Các framework plugin, application server, hot deployment, proxy generation và runtime bytecode generation có thể tạo nhiều class loader hoặc nhiều định nghĩa class trong suốt vòng đời ứng dụng.

## 2. Lấy PID và gọi jstat -class

Liệt kê JVM đang chạy:

~~~powershell
jps -l
~~~

Ví dụ:

~~~text
8120 com.example.ClassLoadingStatsTarget
9204 org.apache.catalina.startup.Bootstrap
10440 jdk.jcmd/sun.tools.jps.Jps
~~~

Dùng PID của tiến trình cần kiểm tra:

~~~powershell
jstat -class 8120
~~~

Nếu không truyền interval và count, công cụ lấy một mẫu rồi kết thúc. Để quan sát theo thời gian, thêm interval và số mẫu:

~~~powershell
jstat -class 8120 1000 5
~~~

Lệnh trên lấy năm mẫu, cách nhau 1000 millisecond (một giây).

Có thể dùng hậu tố thời gian:

~~~powershell
jstat -class 8120 1s 5
~~~

Để theo dõi liên tục cho tới khi dừng bằng Ctrl+C:

~~~powershell
jstat -class 8120 1s
~~~

Thực hiện trên cùng máy với JVM đích và dùng tài khoản có quyền truy cập phù hợp. Với Docker/container, PID nhìn từ host có thể khác PID trong container; hãy chạy công cụ trong đúng namespace hoặc dùng PID mà môi trường chẩn đoán yêu cầu.

## 3. Cấu trúc output của jstat -class

Một output mẫu có dạng:

~~~text
Loaded  Bytes  Unloaded  Bytes     Time
  812   1542.3        12    18.6    0.43
  825   1568.7        12    18.6    0.44
  841   1601.2        12    18.6    0.45
  841   1601.2        12    18.6    0.45
~~~

Các con số trên chỉ là ví dụ minh họa để giải thích cách đọc, không phải kết quả cố định của một chương trình.

Năm cột gồm:

| Cột | Ý nghĩa |
|---|---|
| `Loaded` | Số class đã được nạp |
| `Bytes` (sau Loaded) | Số KB dữ liệu class đã nạp |
| `Unloaded` | Số class đã được unload |
| `Bytes` (sau Unloaded) | Số KB dữ liệu class đã unload |
| `Time` | Thời gian dành cho thao tác nạp và unload class |

Hai cột có tên `Bytes` có ý nghĩa khác nhau tùy vị trí: cột đầu là KB đã nạp, cột thứ hai là KB đã unload. Khi đọc, luôn nhìn cả tiêu đề và vị trí cột, không chỉ nhìn tên.

Các bộ đếm class load/unload là số liệu tích lũy trong vòng đời JVM. Chúng thường tăng dần; việc một dòng không đổi qua vài mẫu chỉ cho biết trong khoảng lấy mẫu không có hoạt động làm thay đổi counter đó.

## 4. Hiểu từng cột

### 4.1. Loaded

`Loaded` là số class đã được nạp. Đây là counter tích lũy, không phải số class đang tồn tại tại đúng thời điểm lấy mẫu.

Ví dụ:

~~~text
Loaded
812
825
841
~~~

Số class đã nạp tăng từ 812 lên 841 trong các mẫu. Có thêm hoạt động nạp class trong khoảng quan sát.

Loaded tăng là điều bình thường trong startup, warm-up, lúc framework khởi tạo, khi nạp plugin hoặc khi ứng dụng tạo proxy/bytecode động. Chỉ riêng việc số này tăng không chứng minh có memory leak.

### 4.2. Bytes đã nạp

Cột `Bytes` ngay sau `Loaded` là số KB dữ liệu class đã nạp.

Ví dụ:

~~~text
Loaded  Bytes
812     1542.3
825     1568.7
841     1601.2
~~~

Cả số class và lượng KB đã nạp đều tăng. Điều này cho biết JVM tiếp tục nạp class và dữ liệu class tương ứng.

Giá trị này không phải tổng heap đã dùng, cũng không phải số đo trực tiếp của Metaspace đang committed. Nó mô tả lượng dữ liệu liên quan tới class loading theo bộ đếm của công cụ.

### 4.3. Unloaded

`Unloaded` là số class đã được unload kể từ khi JVM bắt đầu.

Ví dụ:

~~~text
Unloaded
12
12
15
~~~

Counter tăng từ 12 lên 15 cho biết đã có thêm ba class được unload trong khoảng quan sát.

Class thường chỉ có thể được unload khi class loader định nghĩa nó không còn được tham chiếu có thể truy cập và JVM thực hiện quá trình thu hồi phù hợp. Nếu class loader vẫn được giữ bởi static field, thread, ThreadLocal, cache, MBean, callback hoặc một object còn sống khác, class của loader đó có thể không được unload.

Không phải class nào cũng được unload trong suốt đời JVM. Các class nền tảng được nạp bởi bootstrap loader thường tồn tại trong suốt vòng đời tiến trình.

### 4.4. Bytes đã unload

Cột `Bytes` thứ hai là lượng KB dữ liệu class đã unload.

Nếu `Unloaded` tăng nhưng `Bytes` thay đổi rất ít, có thể các class được gỡ có kích thước nhỏ. Nếu cả hai tăng, JVM đã unload thêm class và dữ liệu class tương ứng.

Không nên so sánh riêng cột bytes để kết luận Metaspace đã giảm đúng bằng lượng đó. Metaspace có cơ chế cấp phát, chunk, fragmentation và thu hồi riêng; số liệu `jstat -class` không thay thế thống kê memory pool.

### 4.5. Time

`Time` biểu thị thời gian JVM dành cho thao tác class loading và unloading.

Đây là số liệu thời gian của hoạt động nạp/gỡ class, không phải interval mà bạn truyền vào cuối lệnh. `-t` là một cột riêng để hiển thị thời gian đã trôi qua kể từ khi JVM khởi động.

Nếu `Time` tăng nhanh cùng với `Loaded` hoặc `Unloaded`, hoạt động class loading/unloading đang diễn ra nhiều hơn. Nếu thời gian tăng nhưng số class tăng ít, cần xem loại class được nạp, chi phí đọc/verify/link và tải hệ thống. Không thể kết luận chỉ từ một cột; hãy so sánh các mẫu và đối chiếu startup log/JFR.

## 5. Cách đọc xu hướng qua nhiều mẫu

Điều quan trọng nhất của `jstat -class` là xu hướng, không phải một con số đơn lẻ.

### 5.1. Startup bình thường

Ví dụ:

~~~text
Loaded  Bytes  Unloaded  Bytes   Time
  420   780.0         0     0.0   0.12
  610  1120.5         0     0.0   0.19
  790  1460.2         0     0.0   0.27
  805  1482.4         0     0.0   0.28
  805  1482.4         0     0.0   0.28
~~~

Loaded tăng mạnh lúc đầu rồi ổn định. Đây thường là hình ảnh hợp lý khi ứng dụng nạp framework, thư viện và các class của ứng dụng trong giai đoạn startup/warm-up.

### 5.2. Ứng dụng nạp class động liên tục

Ví dụ:

~~~text
Loaded  Bytes  Unloaded  Bytes   Time
  805  1482.4         0     0.0   0.28
  910  1660.8         0     0.0   0.35
 1040  1912.6         0     0.0   0.43
 1195  2204.1         0     0.0   0.55
~~~

Loaded và Bytes tiếp tục tăng trong khi Unloaded đứng yên. Có thể ứng dụng đang nạp plugin, sinh proxy, nạp module theo request hoặc tạo class loader mới. Nếu đây là hành vi có chủ đích, xu hướng có thể bình thường; nếu số liệu tăng mãi sau warm-up, cần kiểm tra class loader lifecycle.

### 5.3. Có unload class

Ví dụ:

~~~text
Loaded  Bytes  Unloaded  Bytes   Time
 1200  2210.0        10    18.0   0.60
 1300  2400.0        10    18.0   0.68
 1315  2430.0        25    42.0   0.74
 1315  2430.0        25    42.0   0.74
~~~

Unloaded tăng từ 10 lên 25, cho biết có class được unload trong giai đoạn đó. Điều này có thể xảy ra khi custom class loader trở nên unreachable và JVM thực hiện class unloading trong quá trình GC phù hợp.

### 5.4. Dấu hiệu cần điều tra class loader leak

Một tình huống đáng chú ý:

- Sau mỗi lần redeploy hoặc tạo plugin mới, `Loaded` tiếp tục tăng.
- `Unloaded` gần như không tăng qua nhiều chu kỳ.
- Thống kê `VM.classloader_stats` cho thấy nhiều loader cũ vẫn còn.
- Metaspace used tăng dần và không trở về mức ổn định sau các chu kỳ thu hồi.
- Heap dump cho thấy loader cũ vẫn được tham chiếu từ static cache, thread, ThreadLocal, MBean hoặc registry.

Đây là tập hợp dấu hiệu mạnh hơn nhiều so với chỉ nhìn `Loaded` tăng. Hãy kiểm tra nguyên nhân giữ reference trước khi kết luận có leak.

## 6. Phân biệt tổng số đã nạp và số class hiện đang được nạp

`jstat -class` tập trung vào số liệu load/unload tích lũy. Khi cần biết số class hiện đang được nạp tại thời điểm kiểm tra, dùng Java Management API `ClassLoadingMXBean`.

Ba giá trị quan trọng:

- `getTotalLoadedClassCount()`: tổng số class đã được nạp kể từ khi JVM bắt đầu.
- `getLoadedClassCount()`: số class hiện đang được nạp.
- `getUnloadedClassCount()`: tổng số class đã unload kể từ khi JVM bắt đầu.

Trong điều kiện cùng một JVM và cùng định nghĩa counter, tổng số đã nạp trừ tổng số đã unload tương ứng với số class hiện đang được nạp. Khi cần số hiện tại, dùng trực tiếp `getLoadedClassCount()` thay vì suy ra từ một output đã cũ.

## 7. Ví dụ Java 17+: đọc ClassLoadingMXBean

Tạo file `ClassLoadingStatsTarget.java`:

~~~java
import java.lang.management.ClassLoadingMXBean;
import java.lang.management.ManagementFactory;
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Path;
import java.util.concurrent.CountDownLatch;

public final class ClassLoadingStatsTarget {
    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            System.err.println("Usage: java ClassLoadingStatsTarget <plugin.jar>");
            return;
        }

        ClassLoadingMXBean bean =
                ManagementFactory.getClassLoadingMXBean();

        printStats("before", bean);

        Path pluginPath = Path.of(args[0]).toAbsolutePath();
        URL pluginUrl = pluginPath.toUri().toURL();

        try (URLClassLoader loader = new URLClassLoader(
                new URL[] { pluginUrl },
                ClassLoader.getPlatformClassLoader())) {

            Class<?> pluginClass = Class.forName(
                    "demo.PluginMarker",
                    true,
                    loader
            );

            System.out.println("Loaded plugin class: " + pluginClass.getName());
        }

        printStats("after", bean);
        System.out.println("PID: " + ProcessHandle.current().pid());
        System.out.println("READY - use jstat -class with this PID.");

        new CountDownLatch(1).await();
    }

    private static void printStats(
            String label,
            ClassLoadingMXBean bean
    ) {
        System.out.printf(
                "%s: current=%d total=%d unloaded=%d%n",
                label,
                bean.getLoadedClassCount(),
                bean.getTotalLoadedClassCount(),
                bean.getUnloadedClassCount()
        );
    }
}
~~~

Tạo class plugin trong file `plugin-src/demo/PluginMarker.java`:

~~~java
package demo;

public final class PluginMarker {
    public String message() {
        return "Plugin loaded";
    }
}
~~~

Biên dịch plugin và đóng gói thành JAR:

~~~powershell
javac -d plugin-classes plugin-src/demo/PluginMarker.java
jar --create --file plugin.jar -C plugin-classes .
~~~

Biên dịch ứng dụng theo dõi:

~~~powershell
javac ClassLoadingStatsTarget.java
~~~

Chạy ứng dụng:

~~~powershell
java ClassLoadingStatsTarget plugin.jar
~~~

Ứng dụng sẽ in số class hiện tại, tổng số class đã nạp và tổng số class đã unload trước/sau khi tạo `URLClassLoader`. Giá trị số cụ thể phụ thuộc JDK và các class runtime đã được nạp; dòng `Loaded plugin class: demo.PluginMarker` là phần output xác nhận plugin class đã được tìm thấy và nạp thành công.

Giữ tiến trình chạy. Mở terminal thứ hai, dùng PID được in ra để lấy thống kê:

~~~powershell
jstat -class <PID> 1000 5
~~~

Nếu cần, đối chiếu bằng:

~~~powershell
jcmd <PID> VM.classloader_stats
~~~

Kết thúc chương trình thử nghiệm bằng Ctrl+C ở terminal đầu tiên. Ví dụ này minh họa việc nạp class bằng custom loader; việc class được unload sau khi loader không còn tham chiếu không được bảo đảm xảy ra ngay lập tức.

## 8. Các tùy chọn lấy mẫu hữu ích

### 8.1. Lấy một mẫu

~~~powershell
jstat -class 8120
~~~

Dùng khi cần kiểm tra nhanh trạng thái tại một thời điểm.

### 8.2. Lấy nhiều mẫu với interval

~~~powershell
jstat -class 8120 1s 10
~~~

Lấy 10 mẫu, cách nhau một giây. Dùng để quan sát quá trình startup hoặc thời điểm nạp plugin.

### 8.3. Thêm timestamp của JVM

~~~powershell
jstat -class -t 8120 1s 10
~~~

Cột `Timestamp` được thêm ở đầu output và biểu thị số giây đã trôi qua kể từ lúc target JVM khởi động. Đây không phải đồng hồ ngày giờ thực tế.

### 8.4. Lặp lại header

~~~powershell
jstat -class -h 5 8120 1s 20
~~~

Header được in lại sau mỗi năm dòng dữ liệu, giúp đọc file dài dễ hơn.

### 8.5. Kết hợp timestamp và header

~~~powershell
jstat -class -t -h 5 8120 1s 20
~~~

Lưu ý: stat option `-class` phải đứng trước các output option như `-t` và `-h`.

### 8.6. Xem các stat option có sẵn

~~~powershell
jstat -options
~~~

Lệnh này liệt kê các lựa chọn thống kê mà bản JDK/platform hiện tại hỗ trợ. Ngoài `-class`, một số lựa chọn hữu ích:

- `-compiler`: thống kê JIT compilation.
- `-gc`: dung lượng và mức sử dụng các vùng heap, Metaspace và số liệu GC.
- `-gcutil`: tỷ lệ sử dụng các vùng bộ nhớ và counter GC.
- `-gcmetacapacity`: thống kê capacity của Metaspace.
- `-printcompilation`: thông tin method compilation gần nhất.

## 9. Class loading statistics khác Metaspace statistics thế nào?

Class metadata được lưu trong Metaspace ở các JVM HotSpot hiện đại. Tuy nhiên, không nên nhầm cột `Bytes` của `jstat -class` với dung lượng Metaspace đang sử dụng.

| Số liệu | Ý nghĩa |
|---|---|
| `jstat -class` Loaded/Unloaded Bytes | KB dữ liệu class đã nạp hoặc unload theo bộ đếm class loading |
| `jstat -gc` MC/MU | Metaspace committed size và mức sử dụng |
| `jstat -gc` CCSC/CCSU | Compressed class space committed và used |
| `jstat -gcmetacapacity` | Capacity của Metaspace và compressed class space |
| `jcmd VM.classloader_stats` | Thống kê theo từng ClassLoader |

Nếu `Loaded Bytes` tăng, điều đó cho biết hoạt động nạp class và dữ liệu class tăng. Để biết Metaspace đang sử dụng bao nhiêu, đọc `MU` trong `jstat -gc` hoặc các số liệu Metaspace phù hợp.

Ví dụ:

~~~powershell
jstat -gc 8120 1s 5
jstat -gcmetacapacity 8120 1s 5
~~~

`MU` là Metaspace utilization theo KB trong output `-gc`; `MC` là committed size. Committed không đồng nghĩa used. Metaspace có thể giữ vùng đã commit để tái sử dụng ngay cả khi một số class đã unload.

## 10. Xem thống kê theo từng ClassLoader

`jstat -class` chỉ cung cấp tổng hợp cho JVM. Nếu cần biết loader nào đang giữ class, dùng diagnostic command của `jcmd`:

~~~powershell
jcmd 8120 VM.classloader_stats
~~~

Lệnh này in thống kê cho tất cả ClassLoader. Đây là bước tiếp theo khi nghi ngờ plugin loader, application server loader hoặc custom loader tích lũy theo thời gian.

Có thể dùng `jmap -clstats` để lấy thống kê class loader:

~~~powershell
jmap -clstats 8120
~~~

Trong JDK 17, Oracle Troubleshooting Guide mô tả việc dùng `jcmd <PID> VM.classloader_stats` và `jmap -clstats <PID>` để điều tra class loader và memory leak liên quan Metaspace.

Nếu cần xem class hierarchy hoặc class cụ thể, kiểm tra các diagnostic command có sẵn:

~~~powershell
jcmd 8120 help
jcmd 8120 help VM.classloader_stats
~~~

Không phải mọi command đều có cùng option trên mọi phiên bản JDK. Hãy dùng help của target JVM.

## 11. Phân tích class loader leak

Class loader leak thường xuất hiện khi ứng dụng tạo loader mới nhưng loader cũ vẫn bị giữ tham chiếu sau khi module/plugin/redeploy kết thúc.

Một số nguyên nhân thường gặp:

- Static collection giữ class, instance hoặc ClassLoader của ứng dụng cũ.
- Thread sống lâu giữ context class loader trỏ tới loader cũ.
- ThreadLocal chưa được remove trên thread pool dùng lại.
- MBean hoặc registry giữ đối tượng thuộc ứng dụng đã undeploy.
- JDBC driver, logging framework, callback hoặc shutdown hook chưa được deregister.
- Cache hoặc listener giữ class instance từ loader cũ.
- Plugin manager đóng URLClassLoader nhưng vẫn giữ tham chiếu tới loader hoặc object do loader định nghĩa.

Cách điều tra:

1. Chụp `jstat -class` sau khi ứng dụng ổn định.
2. Thực hiện một chu kỳ deploy/undeploy hoặc load/unload plugin.
3. Chụp lại `Loaded`, `Unloaded` và Metaspace.
4. Lặp lại vài chu kỳ để xem xu hướng có tích lũy hay không.
5. Chạy `jcmd PID VM.classloader_stats` để tìm loader và số class của chúng.
6. Nếu cần, lấy heap dump và tìm đường dẫn reference giữ class loader cũ.
7. Kiểm tra thread, ThreadLocal, static cache, MBean, driver registry và callback.

Nếu Loaded tăng sau mỗi chu kỳ nhưng Unloaded không tăng, đây là dấu hiệu cần điều tra, không phải kết luận cuối cùng. Xác nhận bằng class loader stats và heap reference trước khi sửa code.

## 12. Phân biệt class loading với JIT compilation

Class loading và JIT compilation là hai hoạt động khác nhau:

- **Class loading:** nạp định nghĩa class vào JVM.
- **JIT compilation:** biên dịch method bytecode thành mã máy để thực thi hiệu quả hơn.

Một class có thể đã được nạp nhưng các method của nó chưa được JIT compile. Ngược lại, JIT có thể biên dịch method trong các class đã được nạp từ lâu.

Dùng:

~~~powershell
jstat -class 8120
jstat -compiler 8120
~~~

`-class` theo dõi hoạt động class loader; `-compiler` theo dõi compilation tasks, lỗi và method compile gần nhất. Không dùng `Loaded` để kết luận có bao nhiêu method đã được JIT compile.

## 13. Lỗi thường gặp khi đọc jstat -class

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| `jstat is not recognized` | Chưa cài JDK hoặc JDK `bin` chưa nằm trong PATH | Cài JDK phù hợp hoặc gọi `jstat` bằng đường dẫn đầy đủ |
| `Could not find any processes matching` | PID/VMID sai hoặc JVM đã dừng | Dùng `jps -l` hoặc công cụ hệ điều hành để tìm đúng PID |
| Không kết nối được target JVM | Khác user, container namespace hoặc hạn chế perfdata/attach | Dùng đúng tài khoản và môi trường của JVM |
| `-class` không có output như mong đợi | Sai thứ tự option hoặc target VM không hỗ trợ instrumentation tương ứng | Kiểm tra `jstat -help`, `jstat -options` và phiên bản JDK |
| Loaded tăng liên tục | Startup, plugin, proxy generation hoặc class loader được tạo mới | So sánh sau warm-up và qua nhiều chu kỳ |
| Unloaded luôn bằng 0 | Không có class loader nào đủ điều kiện unload trong khoảng quan sát | Kiểm tra lifecycle loader; không mặc định đây là leak |
| Bytes tăng nhưng Metaspace không tăng tương ứng | Counter class bytes và Metaspace used đo các khía cạnh khác nhau | Đối chiếu `jstat -gc`, `-gcmetacapacity` và `VM.classloader_stats` |
| Metaspace tăng nhưng Loaded ổn định | Loader/class metadata cũ có thể vẫn được giữ hoặc allocation khác tăng | Kiểm tra classloader stats và heap dump |
| Số liệu đứng yên | Ứng dụng đã ổn định, không có class loading/unloading trong interval | Lấy mẫu trong startup, deploy hoặc workload tạo class mới |

## 14. Lưu ý về độ tin cậy và ảnh hưởng vận hành

`jstat` đọc instrumentation data của HotSpot VM. Đây là công cụ giám sát nhanh, không phải giao diện quản lý ổn định cho ứng dụng.

- Output format có thể thay đổi theo JDK; không nên xây dashboard parser lâu dài dựa trên cột và spacing cố định nếu không kiểm soát phiên bản.
- `interval` quá ngắn có thể tạo nhiều output mà không tăng đáng kể giá trị chẩn đoán.
- PID có thể thay đổi sau khi restart JVM.
- Dùng cùng môi trường/JDK phù hợp với tiến trình đích để tránh khác biệt về công cụ và quyền.
- Không dùng một mẫu duy nhất để kết luận class loader leak.
- Khi lấy thống kê theo từng loader, nhớ rằng class loader stats và heap dump có thể tiết lộ tên class, cấu trúc ứng dụng và thông tin triển khai nội bộ; giới hạn quyền truy cập file output.

Nếu cần giám sát lâu dài, cân nhắc JMX `ClassLoadingMXBean`, JFR class loading events, APM hoặc metrics đã được thiết kế cho production. Dùng `jstat` cho kiểm tra trực tiếp và đối chiếu xu hướng trong lúc điều tra.

## 15. Checklist đọc class loading statistics

- [ ] Đã xác định đúng PID của JVM.
- [ ] Đã chạy `jstat -class` và đọc đúng năm cột.
- [ ] Đã phân biệt hai cột `Bytes`: KB nạp và KB unload.
- [ ] Hiểu `Loaded` và `Unloaded` là counter tích lũy.
- [ ] Không nhầm tổng số đã nạp với số class hiện đang tồn tại.
- [ ] Đã lấy nhiều mẫu với interval phù hợp.
- [ ] Đã dùng `-t` khi cần mốc uptime của JVM.
- [ ] Đã kiểm tra xu hướng sau startup/warm-up hoặc sau redeploy.
- [ ] Không kết luận memory leak chỉ từ `Loaded` tăng hoặc `Unloaded` bằng 0.
- [ ] Đã phân biệt class loading bytes với Metaspace used/committed.
- [ ] Đã dùng `ClassLoadingMXBean` khi cần số class hiện tại.
- [ ] Đã dùng `jcmd VM.classloader_stats` hoặc `jmap -clstats` khi cần số liệu theo loader.
- [ ] Đã kiểm tra classloader lifecycle, ThreadLocal, thread, static cache và registry nếu nghi ngờ leak.
- [ ] Đã cân nhắc `jstat` là công cụ experimental và unsupported, không phụ thuộc output format cố định.

`jstat -class` là cách nhanh để quan sát hoạt động class loading và unloading của một JVM. Đọc `Loaded`, `Unloaded`, hai cột KB và `Time` theo chuỗi mẫu để thấy xu hướng sau startup hoặc redeploy. Khi cần biết số class hiện tại, dùng `ClassLoadingMXBean`; khi cần tìm loader nào giữ class và liên quan Metaspace, dùng `jcmd VM.classloader_stats` hoặc `jmap -clstats`. Chỉ kết luận class loader leak sau khi đã xác nhận loader cũ còn bị giữ tham chiếu.

## Tài liệu tham khảo

- Oracle, The jstat Command, JDK 17: https://docs.oracle.com/en/java/javase/17/docs/specs/man/jstat.html
- Oracle, The jcmd Command, JDK 17: https://docs.oracle.com/en/java/javase/17/docs/specs/man/jcmd.html
- Oracle, Troubleshooting Memory Leaks, JDK 17: https://docs.oracle.com/en/java/javase/17/troubleshoot/troubleshooting-memory-leaks.html
- Oracle, ClassLoadingMXBean, Java SE 17 API: https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/ClassLoadingMXBean.html
