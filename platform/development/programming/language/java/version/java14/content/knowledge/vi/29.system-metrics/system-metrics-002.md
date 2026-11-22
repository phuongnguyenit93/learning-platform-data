# Lấy bean hệ điều hành và kiểm tra kiểu được hỗ trợ trong Java

## 1. Vấn đề: không phải mọi JVM đều cung cấp cùng bộ số liệu hệ điều hành

Java có sẵn **Java Management Extensions (JMX)** và hệ thống **platform MXBeans** để ứng dụng quan sát trạng thái của JVM và môi trường vận hành. Muốn đọc thông tin về hệ điều hành, CPU hoặc một số chỉ số bộ nhớ, điểm bắt đầu đúng là:

~~~java
java.lang.management.OperatingSystemMXBean bean =
        java.lang.management.ManagementFactory.getOperatingSystemMXBean();
~~~

Đây là **đoạn minh họa** trong phương thức, không phải file có `main`. Phương thức trả bean chuẩn của nền tảng Java mà JVM hiện tại cung cấp.

Nhưng có hai interface rất dễ nhầm vì **trùng tên đơn giản**:

1. **`java.lang.management.OperatingSystemMXBean`** — giao diện **chuẩn Java SE**, nằm trong module `java.management`; cho phép hỏi tên OS, phiên bản, kiến trúc, số bộ xử lý khả dụng và system load average.
2. **`com.sun.management.OperatingSystemMXBean`** — giao diện **mở rộng của JDK**, nằm trong module `jdk.management`, kế thừa interface chuẩn; bổ sung các số liệu như CPU load của môi trường, CPU load/thời gian CPU của process, bộ nhớ môi trường, swap và committed virtual memory.

**Ý chính của bài:** luôn lấy bean qua API quản lý chính thức, giữ nó dưới kiểu chuẩn, rồi **kiểm tra kiểu thực tế bằng `instanceof` trước khi dùng API mở rộng**. Không ép kiểu mù quáng và không giả định số liệu luôn hiện diện chỉ vì tên method đã được JDK cung cấp.

Một JVM/Java runtime chỉ triển khai giao diện chuẩn vẫn có thể cung cấp tên OS và số processor, trong khi không hỗ trợ các method mở rộng của `jdk.management`. Ngoài kiểm tra interface, còn phải xử lý **giá trị trả về báo không khả dụng**.

**Ngữ cảnh Java 14 và kiến thức còn áp dụng:** một số method mở rộng có tên mới từ **JDK 14**, chẳng hạn `getCpuLoad()`, `getFreeMemorySize()` và `getTotalMemorySize()`; những method có tên cũ tương ứng đã **deprecated since 14**. Các tên mới vẫn hiện diện trong tài liệu JDK 17/26. Bài dùng Java 17+ và tránh giới thiệu API deprecated như đường đi chính.

## 2. Phân biệt đúng hai loại OperatingSystemMXBean

| Đặc điểm | Giao diện chuẩn | Giao diện mở rộng |
| --- | --- | --- |
| Tên đầy đủ | `java.lang.management.OperatingSystemMXBean` | `com.sun.management.OperatingSystemMXBean` |
| Module | `java.management` | `jdk.management` |
| Phạm vi | Java SE API | JDK-specific API |
| Kế thừa | `PlatformManagedObject` | Kế thừa `java.lang.management.OperatingSystemMXBean` |
| Lấy qua factory | `ManagementFactory.getOperatingSystemMXBean()` | Kiểm tra `instanceof` trên bean chuẩn; hoặc hỏi `getPlatformMXBean(extendedInterface.class)` |
| Các chỉ số cơ bản | Name, Arch, Version, AvailableProcessors, SystemLoadAverage | Có toàn bộ chỉ số cơ bản và chỉ số mở rộng |
| Giả định mọi JVM hỗ trợ | Giao diện chuẩn hiện diện khi dùng `java.management` | **Không** nên giả định trên mọi JVM/runtime tùy chỉnh |

Tên `com.sun.management` có thể khiến người học nhầm đó là một class nội bộ cấm sử dụng. Ở đây, **`com.sun.management.OperatingSystemMXBean` là interface được tài liệu hóa và export công khai bởi module `jdk.management` của JDK hiện đại**. Dùng nó khi có lý do cần số liệu mở rộng là phù hợp với **JDK chứa module này**. Tuy nhiên nó **không phải hợp đồng portable của mọi triển khai Java SE**.

### Những phương thức chuẩn

| Method chuẩn | Giá trị |
| --- | --- |
| `getName()` | Tên hệ điều hành, tương ứng property `os.name` |
| `getArch()` | Kiến trúc OS, tương ứng `os.arch` |
| `getVersion()` | Phiên bản OS, tương ứng `os.version` |
| `getAvailableProcessors()` | Số processor khả dụng **đối với JVM**, luôn từ 1 trở lên; có thể thay đổi |
| `getSystemLoadAverage()` | Load average trong khoảng 1 phút; trả **giá trị âm** nếu không khả dụng |
| `getObjectName()` | Tên MXBean JMX, chuẩn là `java.lang:type=OperatingSystem` |

**Không nhầm:** `getAvailableProcessors()` không nhất thiết bằng số lõi vật lý của cả host. JVM có thể ở container, VM, cpuset hoặc bị giới hạn tài nguyên. `getSystemLoadAverage()` không phải tỷ lệ CPU chạy từ 0 đến 1; nó là một kiểu **load average** được hệ điều hành tính theo cách riêng, có thể vượt 1.

## 3. Cách lấy bean: lựa chọn API phù hợp

### Cách A — lấy theo convenience method của ManagementFactory

~~~java
import java.lang.management.ManagementFactory;
import java.lang.management.OperatingSystemMXBean;

OperatingSystemMXBean bean = ManagementFactory.getOperatingSystemMXBean();
~~~

Đây là cách **dễ hiểu nhất** khi bạn bắt đầu từ giao diện chuẩn. Interface này cung cấp thông tin OS trên chính JVM đang chạy.

Lúc này **kiểu tĩnh** của biến `bean` là `java.lang.management.OperatingSystemMXBean`. Bạn có thể gọi:

~~~java
String name = bean.getName();
int processors = bean.getAvailableProcessors();
double loadAverage = bean.getSystemLoadAverage();
~~~

Nhưng **không thể gọi** `bean.getCpuLoad()` trực tiếp, vì method này không khai báo trong interface chuẩn. Muốn dùng nó, phải xác định bean thực sự hỗ trợ extension và đi qua biến được kiểm tra kiểu.

### Cách B — lấy qua generic `getPlatformMXBean`

~~~java
OperatingSystemMXBean bean =
        ManagementFactory.getPlatformMXBean(OperatingSystemMXBean.class);
~~~

Đây cũng là API chính thức. `getOperatingSystemMXBean()` và `getPlatformMXBean(OperatingSystemMXBean.class)` đều hướng đến **platform bean hệ điều hành** của JVM hiện tại. Interface chuẩn có một instance thuộc loại này trong mỗi JVM.

Nếu đang sử dụng JDK extension, có thể viết:

~~~java
com.sun.management.OperatingSystemMXBean extended =
        ManagementFactory.getPlatformMXBean(
                com.sun.management.OperatingSystemMXBean.class);

if (extended != null) {
    double cpu = extended.getCpuLoad();
}
~~~

Đoạn này là **minh họa trên JDK có module `jdk.management`**. `getPlatformMXBean(Class)` có thể trả `null` nếu interface platform MXBean đó không được JVM triển khai, vì vậy phải kiểm tra trước khi sử dụng. Nó cũng có thể ném `IllegalArgumentException` nếu class đưa vào không phải platform management interface hợp lệ hoặc không phải loại singleton phù hợp; không truyền class tùy ý vào factory rồi cho rằng nhận được bean.

### Cách C — lấy bean chuẩn rồi kiểm tra kiểu runtime

Đây là cách chủ đạo trong bài:

~~~java
OperatingSystemMXBean bean = ManagementFactory.getOperatingSystemMXBean();

if (bean instanceof com.sun.management.OperatingSystemMXBean extended) {
    System.out.println(extended.getTotalMemorySize());
} else {
    System.out.println("No JDK-specific OS metrics available");
}
~~~

Với **Java 16+**, `instanceof ... extended` sử dụng **pattern matching for instanceof** ổn định để khai báo biến `extended` ngay trong nhánh được bảo vệ. Nếu cần biên dịch cho Java 14, dùng cách kiểm tra `instanceof` thường rồi cast trong nhánh; các ví dụ đầy đủ của bài ưu tiên Java 17+ nên dùng cú pháp hiện đại.

**Tại sao an toàn?** Khi điều kiện đúng, JVM chứng minh object implement interface mở rộng; biến `extended` mới được dùng. Nếu điều kiện sai, không xảy ra `ClassCastException` do ép kiểu. Tuy nhiên việc code đã compile phụ thuộc vào API của module `jdk.management` vẫn đòi module có sẵn ở runtime; muốn chạy trên runtime không có module đó, thiết kế tách thành phần JDK-specific thay vì chỉ dựa vào `instanceof`.

## 4. Chương trình Java 17+ số 1: lấy bean thật, kiểm tra type và đọc thông tin an toàn

Chương trình dưới đây thực hiện những việc thiết yếu:

1. Lấy **bean chuẩn** bằng `ManagementFactory.getOperatingSystemMXBean()`.
2. Lấy bean chuẩn lần nữa bằng `ManagementFactory.getPlatformMXBean(...)` để đối chiếu tên JMX.
3. Ghi nhận các thuộc tính cơ bản mà interface chuẩn công bố.
4. Kiểm tra có **com.sun.management.OperatingSystemMXBean** hay không.
5. Nếu hỗ trợ extension, đọc các method **không deprecated**; chỉ kiểm tra **miền giá trị hợp lệ** thay vì đóng đinh số RAM hoặc tỷ lệ CPU của máy thử.

Tạo file **`OperatingSystemBeanDemo.java`**:

~~~java
import java.lang.management.ManagementFactory;
import java.lang.management.OperatingSystemMXBean;

public class OperatingSystemBeanDemo {
    static boolean loadUsable(double load) {
        return load >= 0.0 && load <= 1.0 && Double.isFinite(load);
    }

    public static void main(String[] args) {
        OperatingSystemMXBean bean =
                ManagementFactory.getOperatingSystemMXBean();
        OperatingSystemMXBean viaPlatform =
                ManagementFactory.getPlatformMXBean(OperatingSystemMXBean.class);

        System.out.println("beanPresent=" + (bean != null));
        System.out.println("objectName=" + bean.getObjectName());
        System.out.println("platformBeanSameName="
                + bean.getObjectName().equals(viaPlatform.getObjectName()));
        System.out.println("osNamePresent="
                + (bean.getName() != null && !bean.getName().isBlank()));
        System.out.println("architecturePresent="
                + (bean.getArch() != null && !bean.getArch().isBlank()));
        System.out.println("processorsPositive="
                + (bean.getAvailableProcessors() >= 1));

        double loadAverage = bean.getSystemLoadAverage();
        System.out.println("loadAverageValidOrUnavailable="
                + (loadAverage >= 0 || loadAverage < 0));

        if (bean instanceof com.sun.management.OperatingSystemMXBean extended) {
            System.out.println("extendedSupported=true");
            System.out.println("memoryTotalPositive="
                    + (extended.getTotalMemorySize() > 0));
            System.out.println("memoryFreeNonnegative="
                    + (extended.getFreeMemorySize() >= 0));

            double cpuLoad = extended.getCpuLoad();
            double processLoad = extended.getProcessCpuLoad();
            System.out.println("cpuLoadValidOrUnavailable="
                    + (loadUsable(cpuLoad) || cpuLoad < 0));
            System.out.println("processLoadValidOrUnavailable="
                    + (loadUsable(processLoad) || processLoad < 0));

            long processCpuTime = extended.getProcessCpuTime();
            System.out.println("processCpuTimeValidOrUnavailable="
                    + (processCpuTime >= -1));
        } else {
            System.out.println("extendedSupported=false");
            System.out.println("fallbackUsesStandardMetrics=true");
        }
    }
}
~~~

Biên dịch và chạy trên **JDK 17+ có module `jdk.management`**:

~~~bash
javac --release 17 -encoding UTF-8 OperatingSystemBeanDemo.java
java OperatingSystemBeanDemo
~~~

**Stdout đã kiểm thử trên OpenJDK 24 / Windows** (máy có hỗ trợ extension):

~~~text
beanPresent=true
objectName=java.lang:type=OperatingSystem
platformBeanSameName=true
osNamePresent=true
architecturePresent=true
processorsPositive=true
loadAverageValidOrUnavailable=true
extendedSupported=true
memoryTotalPositive=true
memoryFreeNonnegative=true
cpuLoadValidOrUnavailable=true
processLoadValidOrUnavailable=true
processCpuTimeValidOrUnavailable=true
~~~

### Đọc kết quả mà không suy diễn quá mức

- **`beanPresent=true`**: factory trả bean của JVM hiện tại. Cơ chế standard MXBean được Java quản lý, không cần tự new một bean của OS.
- **`objectName=java.lang:type=OperatingSystem`**: đây là **tên JMX chuẩn**, không phải tên class của implementation.
- **`platformBeanSameName=true`**: hai cách lấy bean chỉ tới cùng **đối tượng quản lý logic**, xác nhận bằng `ObjectName`; không cần giả định luôn cùng identity Java object.
- **`osNamePresent=true` và `architecturePresent=true`**: xác nhận có chuỗi thuộc tính, **không hardcode** Windows/Linux hay x86/AArch64.
- **`processorsPositive=true`**: kiểm tra ràng buộc trong Java SE; không suy ra “số core vật lý trên host”.
- **`loadAverageValidOrUnavailable=true`**: nhấn mạnh load average có thể **không âm** hoặc **âm để báo không khả dụng**; bài không in số thực tế vì tùy nền tảng.
- **`extendedSupported=true`**: đúng trên JVM thử nghiệm. Trên một runtime không triển khai interface mở rộng, chương trình sẽ chạy nhánh `extendedSupported=false` nếu mã extension có thể được resolve hợp lệ.
- **Các dòng `memory...`** kiểm tra miền giá trị từ thông tin môi trường; không suy diễn heap max hoặc RAM toàn host từ một lần đọc.
- **`cpuLoadValidOrUnavailable=true`** và **`processLoadValidOrUnavailable=true`**: tỷ lệ hợp lệ nằm trong [0,1]; số âm báo không đo được. Đây là kiểm tra hợp đồng, không cam kết tỷ lệ CPU cụ thể.
- **`processCpuTimeValidOrUnavailable=true`**: thời gian CPU của process nếu hỗ trợ là giá trị nanoseconds không âm; `-1` nghĩa là không được hỗ trợ. Nó không phải elapsed wall-clock time.

**Lưu ý về stdout:** những dòng liên quan extension là **kết quả đã chạy trên máy thử**, không bảo đảm mọi JVM đều trả `extendedSupported=true`. Nếu viết bài test portable, chỉ khẳng định chính xác những giá trị mà tài liệu bảo đảm theo loại bean được hỗ trợ.

## 5. Chương trình Java 17+ số 2: mô phỏng JVM chỉ có interface chuẩn và kiểm tra nhánh fallback

Chỉ thử chương trình trên OpenJDK vốn có `jdk.management` sẽ không thực sự chạy được nhánh `instanceof == false`. Để **kiểm thử logic fallback**, ta tạo một **test double** chỉ implement interface chuẩn. Nó không giả làm một MBean đã được đăng ký bởi JVM và không được dùng để lấy dữ liệu OS thật.

Tạo file **`OperatingSystemBeanFallbackDemo.java`**:

~~~java
import java.lang.management.ManagementFactory;
import java.lang.management.OperatingSystemMXBean;
import javax.management.MalformedObjectNameException;
import javax.management.ObjectName;

public class OperatingSystemBeanFallbackDemo {
    static final class BasicOnlyBean implements OperatingSystemMXBean {
        @Override public String getName() { return "DemoOS"; }
        @Override public String getArch() { return "demo-arch"; }
        @Override public String getVersion() { return "1"; }
        @Override public int getAvailableProcessors() { return 2; }
        @Override public double getSystemLoadAverage() { return -1.0; }

        @Override public ObjectName getObjectName() {
            try {
                return new ObjectName("example:type=OperatingSystem");
            } catch (MalformedObjectNameException e) {
                throw new AssertionError(e);
            }
        }
    }

    static String cpuStatus(OperatingSystemMXBean bean) {
        if (!(bean instanceof com.sun.management.OperatingSystemMXBean extended)) {
            return "not-available-on-this-implementation";
        }
        double value = extended.getCpuLoad();
        return value < 0.0 ? "measurement-unavailable" :
                (Double.isFinite(value) && value <= 1.0)
                        ? "measurement-available"
                        : "invalid-sample";
    }

    static String classifyLoad(double value) {
        if (value < 0) return "unavailable";
        if (Double.isFinite(value) && value <= 1) return "valid";
        return "invalid";
    }

    public static void main(String[] args) {
        OperatingSystemMXBean basic = new BasicOnlyBean();
        System.out.println("basicOnlyExtended="
                + (basic instanceof com.sun.management.OperatingSystemMXBean));
        System.out.println("basicFallbackStatus=" + cpuStatus(basic));
        System.out.println("basicLoadAverageUnavailable="
                + (basic.getSystemLoadAverage() < 0));
        System.out.println("basicProcessors=" + basic.getAvailableProcessors());
        System.out.println("loadMinusOne=" + classifyLoad(-1));
        System.out.println("loadQuarter=" + classifyLoad(0.25));
        System.out.println("loadAboveOne=" + classifyLoad(1.5));

        OperatingSystemMXBean real =
                ManagementFactory.getOperatingSystemMXBean();
        String runtimeStatus = cpuStatus(real);
        System.out.println("runtimeStatusRecognized="
                + (runtimeStatus.equals("not-available-on-this-implementation")
                || runtimeStatus.equals("measurement-unavailable")
                || runtimeStatus.equals("measurement-available")));
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac --release 17 -encoding UTF-8 OperatingSystemBeanFallbackDemo.java
java OperatingSystemBeanFallbackDemo
~~~

**Stdout đã kiểm thử:**

~~~text
basicOnlyExtended=false
basicFallbackStatus=not-available-on-this-implementation
basicLoadAverageUnavailable=true
basicProcessors=2
loadMinusOne=unavailable
loadQuarter=valid
loadAboveOne=invalid
runtimeStatusRecognized=true
~~~

### Giải thích logic kiểm tra khả năng hỗ trợ

- `BasicOnlyBean` **cố ý chỉ implement `java.lang.management.OperatingSystemMXBean`**. Nó không implement `com.sun.management.OperatingSystemMXBean`. Đây là mô phỏng đơn vị để chắc chắn nhánh fallback hoạt động.
- `basicOnlyExtended=false` và `basicFallbackStatus=not-available-on-this-implementation` chứng minh code **không cast ép** khi bean không hỗ trợ interface mở rộng.
- `basicLoadAverageUnavailable=true` cho thấy interface chuẩn vẫn có thể được dùng ngay cả khi **một phép đo cụ thể** không khả dụng. Đây là hai loại giới hạn khác nhau: **thiếu interface** và **thiếu giá trị đo**.
- Các dòng `loadMinusOne`, `loadQuarter`, `loadAboveOne` minh họa cách xử lý miền hợp lệ cho **CPU load fraction**, thay vì tự quy đổi `-1` thành âm 100%.
- `runtimeStatusRecognized=true` kiểm tra nhánh trên bean **thật** của máy thử bằng một nhóm trạng thái được cho phép. Nó không in một giá trị CPU nhất định; kết quả phụ thuộc môi trường.
- `example:type=OperatingSystem` là **ObjectName của test double không đăng ký lên JMX server**; không nên hiểu nó là `java.lang:type=OperatingSystem` của JVM thật.

**Bài học quan trọng:** thiết kế tốt nên tách **lấy bean**, **phát hiện hỗ trợ API**, **đọc và phân loại phép đo**, rồi **trình bày kết quả hoặc fallback**. Kiểm thử nhánh không có extension không bắt buộc phải chạy trên một JVM không có extension; có thể dùng test double và kiểm chứng nhánh riêng như trên.

## 6. Kiểm tra kiểu với `instanceof` thay vì ép kiểu không an toàn

### Cách dễ lỗi

~~~java
java.lang.management.OperatingSystemMXBean standard =
        ManagementFactory.getOperatingSystemMXBean();

com.sun.management.OperatingSystemMXBean extended =
        (com.sun.management.OperatingSystemMXBean) standard;
double cpu = extended.getCpuLoad();
~~~

Đây là **đoạn minh họa cho điều không nên làm**, không phải ví dụ xử lý an toàn. Nếu runtime bean không implement extension, phép cast có thể ném **`ClassCastException`**, khiến chức năng giám sát hoặc thậm chí ứng dụng bị gián đoạn.

### Cách đúng trong Java 17+

~~~java
java.lang.management.OperatingSystemMXBean standard =
        ManagementFactory.getOperatingSystemMXBean();

if (standard instanceof com.sun.management.OperatingSystemMXBean extended) {
    double cpuLoad = extended.getCpuLoad();
    if (cpuLoad >= 0.0 && cpuLoad <= 1.0) {
        System.out.println("CPU load: " + cpuLoad);
    } else {
        System.out.println("CPU load not available");
    }
} else {
    System.out.println("Only standard OperatingSystemMXBean available");
}
~~~

Đây là đoạn minh họa cần import `ManagementFactory`; trong dự án thực, có thể ghi metric dưới dạng structured measurement hoặc Optional thay vì in log. **Phải kiểm tra cả interface và giá trị trả về**: `instanceof` đúng không đồng nghĩa `getCpuLoad()` luôn đo được.

### Nếu dùng cách kiểm tra type truyền thống

Khi source code không dùng pattern matching:

~~~java
if (standard instanceof com.sun.management.OperatingSystemMXBean) {
    com.sun.management.OperatingSystemMXBean extended =
            (com.sun.management.OperatingSystemMXBean) standard;
    // Có thể gọi getCpuLoad() tại đây.
}
~~~

Cách này vẫn hợp lệ nhưng dài hơn. Vì Java 17+ đã hỗ trợ pattern matching ổn định, đó là lựa chọn rõ ràng hơn cho code mới.

**Không dùng tên class implementation:** ví dụ đừng so `bean.getClass().getName()` với một chuỗi cụ thể kiểu `com.sun.management.internal.OperatingSystemImpl`. Implementation class có thể thay đổi theo JDK/vendor/OS. Kiểm tra **public interface** bằng `instanceof` là hợp đồng hợp lý hơn.

## 7. Số liệu nào cần extension? Đọc đúng đơn vị và phạm vi

Interface mở rộng `com.sun.management.OperatingSystemMXBean` hiện đại công bố:

| Phương thức | Đơn vị / ý nghĩa | Điều kiện cần xử lý |
| --- | --- | --- |
| `getCpuLoad()` | Tỷ lệ CPU gần đây của operating environment, **0.0 đến 1.0** | **Số âm** nếu không đo được; kỳ đo implementation-specific |
| `getProcessCpuLoad()` | Tỷ lệ CPU gần đây của **JVM process**, **0.0 đến 1.0** | Số âm nếu không khả dụng; không đồng nghĩa system CPU |
| `getProcessCpuTime()` | Thời gian CPU tích lũy của **JVM process**, nanoseconds | **-1** nếu không hỗ trợ; độ chính xác có thể thấp hơn nano |
| `getTotalMemorySize()` | Lượng memory tổng của operating environment, bytes | Phạm vi có thể là host/VM/container; không phải Java heap max |
| `getFreeMemorySize()` | Lượng memory còn rỗi của operating environment, bytes | Không đồng nghĩa Java heap free |
| `getTotalSwapSpaceSize()` | Tổng swap của operating environment, bytes | Có thể là 0 nếu không có swap |
| `getFreeSwapSpaceSize()` | Swap chưa dùng, bytes | Không phải số byte Java heap |
| `getCommittedVirtualMemorySize()` | Lượng virtual memory được cam kết cho **JVM process**, bytes | Có thể **-1** nếu không hỗ trợ |

Những method được Javadoc công bố không nên bị hiểu thành **mọi nền tảng đều cung cấp phép đo theo cùng cách**. Môi trường có thể là OS vật lý, máy ảo hoặc container. Vì thế khi xuất các metrics, hãy ghi lại **JVM version, runtime/container context và thời điểm lấy mẫu**, tránh so sánh các con số mà không biết ranh giới đo.

### `getSystemLoadAverage()` khác `getCpuLoad()`

| Phép đo | Loại giá trị | Có dùng như “% CPU” không? |
| --- | --- | --- |
| `standard.getSystemLoadAverage()` | Load average trong khoảng một phút; có thể **lớn hơn 1** hoặc âm nếu không hỗ trợ | **Không** |
| `extended.getCpuLoad()` | Fraction CPU gần đây của operating environment, **[0,1]** nếu hợp lệ | Có thể nhân 100 để mô tả %, nhưng vẫn cần nêu phạm vi và kỳ đo |
| `extended.getProcessCpuLoad()` | Fraction CPU gần đây của JVM process, **[0,1]** nếu hợp lệ | Có thể nhân 100, chú ý nó là process metric chứ không phải toàn hệ thống |
| `extended.getProcessCpuTime()` | Tổng thời gian CPU đã dùng, đơn vị **nanoseconds** | Không trực tiếp là %; có thể suy ra tỷ lệ trên khoảng thời gian nếu thiết kế phép đo phù hợp |

Một hệ thống 16 processor có thể có **load average 8.0** mà không có nghĩa “CPU 800%”. Ngược lại, CPU load fraction **0.75** có thể được hiển thị là **75%** trong ngữ cảnh mà bean định nghĩa. Đừng cộng/trừ các đơn vị khác nhau.

### Những giá trị động không thích hợp đưa vào stdout cố định

- `getName()`: Windows/Linux/macOS phụ thuộc hệ thống.
- `getAvailableProcessors()`: phụ thuộc CPU quota, affinity và thiết lập JVM.
- `getCpuLoad()`: thay đổi theo các khoảng lấy mẫu; có thể âm khi không khả dụng.
- `getTotalMemorySize()`: phụ thuộc memory scope được JVM nhận biết.
- `getProcessCpuTime()`: tăng theo hoạt động process và GC/runtime, không phải chỉ Java application threads.

Vì thế trong ví dụ chạy được, bài **in điều kiện Boolean và trạng thái** để đầu ra đáng tin hơn, thay vì bịa số GB RAM hoặc cố ép CPU đúng 50%.

## 8. Cách đọc an toàn: giá trị âm không phải metric hợp lệ

Có **hai tầng kiểm tra** độc lập:

**Tầng 1 — interface có được hỗ trợ?**

~~~java
if (standard instanceof com.sun.management.OperatingSystemMXBean extended) {
    // API có sẵn trong bean thực tế.
}
~~~

**Tầng 2 — phép đo có giá trị hữu dụng?**

~~~java
double load = extended.getCpuLoad();
if (Double.isFinite(load) && load >= 0.0 && load <= 1.0) {
    // Tỷ lệ CPU hợp lệ; chỉ tại đây mới nhân 100 hoặc ghi metric.
} else {
    // Không có số đo hợp lệ; ghi trạng thái unavailable.
}
~~~

Đây là các đoạn minh họa, biến `standard` và `extended` cần đặt trong cùng scope hợp lệ. Nếu phép đo trả số âm, đừng coi đó là **-100% CPU** hoặc ghi vào dashboard dưới dạng số liệu thật. Một monitoring system nên **bỏ qua sample** hoặc đánh dấu unavailable, tùy hợp đồng metrics.

Với `getSystemLoadAverage()`, không kiểm tra nó bằng đoạn [0,1] phía trên vì load average **không phải fraction**. Chỉ kiểm tra **không âm** và ngữ nghĩa OS-specific. Trong dữ liệu giám sát chất lượng, số đo không hợp lệ hoặc không lấy được phải thể hiện khác với số đo **0.0**, bởi 0.0 có nghĩa khác: tải CPU thật bằng 0 trong khoảng quan sát.

### Kỳ lấy mẫu và tác động của người đọc khác

Theo Javadoc, `getCpuLoad()` và `getProcessCpuLoad()` là **recent CPU usage**. Khoảng thời gian quan sát **do implementation quyết định**; với lần gọi đầu, khoảng quan sát không xác định. Việc code hoặc thành phần monitoring khác gọi các method này có thể ảnh hưởng kỳ quan sát và kết quả.

Do đó:

1. Không giả định hai lần gọi liên tiếp luôn là hai mẫu độc lập với cửa sổ đúng một giây.
2. Không so sánh một giá trị `getCpuLoad()` mới lấy với một giá trị process CPU từ nhiều phút trước.
3. Khi alerting, tránh dựa trên **một sample duy nhất** vừa khởi động ứng dụng.
4. Lấy mẫu có cadence phù hợp và gắn timestamp.
5. Ghi rõ interface và metric name: hệ thống hay process, load average hay fraction.
6. Không biến số âm thành 0 rồi tuyên bố hệ thống nhàn rỗi.

**Không chạy vòng lặp lấy mẫu dày đặc** chỉ để ép CPU load trả một số mong muốn; tài liệu không hứa window cố định và số đo có thể bị tác động bởi các caller khác.

## 9. Java 14+: dùng method hiện hành, tránh tên đã deprecated

Trong `com.sun.management.OperatingSystemMXBean`, JDK 14 bổ sung tên mới rõ nghĩa hơn:

| Tên cũ (deprecated since 14) | Method nên dùng |
| --- | --- |
| `getSystemCpuLoad()` | **`getCpuLoad()`** |
| `getFreePhysicalMemorySize()` | **`getFreeMemorySize()`** |
| `getTotalPhysicalMemorySize()` | **`getTotalMemorySize()`** |

Javadoc nêu các method cũ là **deprecated**, đồng thời yêu cầu default implementation trả cùng giá trị với method thay thế tương ứng. Trong **code mới**, sử dụng **bên phải** để tránh cảnh báo deprecation và để semantics phản ánh tốt hơn khái niệm operating environment, vốn có thể là môi trường ảo hóa hoặc container.

**Không nhầm:** `getProcessCpuLoad()` **không nằm trong ba tên deprecated này**. Nó vẫn là API mở rộng được dùng để quan sát tỷ lệ CPU của JVM process. `getProcessCpuTime()` cũng vẫn hữu ích nhưng nó trả **nanoseconds**, không trả fraction.

**Mối liên hệ với Java 14:** việc sửa API để tránh những tên nhấn mạnh “physical” một cách gây hiểu nhầm là kiến thức thích hợp cho Java 14 và các Java LTS hiện đại. Đừng sao chép ví dụ cũ dùng `getSystemCpuLoad()` như thể đó là API ưu tiên hiện nay.

## 10. Tài nguyên trong container/VM và giới hạn diễn giải

Javadoc của extension nói interface mô tả **operating environment** nơi JVM chạy: có thể là hệ điều hành vật lý, VM hoặc **container-managed environment**.

Vì vậy:

- **Số processor khả dụng cho JVM** có thể chịu CPU quota hoặc affinity. Nó không nhất thiết khớp số CPU của host.
- **Memory tổng/rỗi** có thể phản ánh environment mà JVM quan sát được; không đồng nghĩa dung lượng DIMM vật lý của cả host.
- **Process CPU load** và **process CPU time** nói về tiến trình JVM. CPU của ứng dụng còn bao gồm GC threads, JIT, compiler và runtime threads, không chỉ thread request/business.
- **CPU load** của operating environment không phải process CPU load. Nếu một ứng dụng chạy trong một container, định nghĩa scope thực tế phụ thuộc JVM/OS và cấu hình container.
- Nếu hệ điều hành không hỗ trợ load average, `getSystemLoadAverage()` có thể trả **âm** dù bean chuẩn hoàn toàn hợp lệ.

Từ một sample ở một VM/container, không thể suy ra “RAM host còn 10 GiB” hay “toàn bộ server có 4 core” nếu bạn chưa xác định tài nguyên process được cấp và số liệu đó đại diện cho môi trường nào.

**Cũng không nên** dùng những metrics này như nguồn duy nhất để quyết định process kill, scaling hoặc circuit-breaker có hệ quả nghiêm trọng. Cần đối chiếu số liệu từ orchestrator/OS, tình trạng GC, heap, số request và lịch sử vận hành.

## 11. Phân biệt OperatingSystemMXBean, MemoryMXBean và Runtime APIs

Ba nhóm API quan sát những phạm vi khác nhau:

| Nhu cầu | API phù hợp | Phạm vi |
| --- | --- | --- |
| OS name, CPU processors khả dụng | `ManagementFactory.getOperatingSystemMXBean()` | Môi trường chạy JVM |
| CPU/swap/memory mở rộng nếu hỗ trợ | `com.sun.management.OperatingSystemMXBean` sau kiểm tra `instanceof` | OS/environment/process |
| Java heap used/committed/max | `ManagementFactory.getMemoryMXBean().getHeapMemoryUsage()` | **Java heap**, không phải tổng RAM OS |
| Non-heap usage | `MemoryMXBean.getNonHeapMemoryUsage()` | JVM non-heap tracking |
| JVM heap free/total/max đơn giản | `Runtime.getRuntime()` (các phương thức memory) | JVM heap |
| JMX metadata của OS bean | `bean.getObjectName()` | Identity của platform MXBean |
| CPU count khả dụng | `Runtime.getRuntime().availableProcessors()` | Tương đương chỉ số processor của OS MXBean theo Javadoc |

Ví dụ đoạn minh họa:

~~~java
var memoryBean = ManagementFactory.getMemoryMXBean();
long heapUsedBytes = memoryBean.getHeapMemoryUsage().getUsed();

var osBean = ManagementFactory.getOperatingSystemMXBean();
int processors = osBean.getAvailableProcessors();
~~~

Đây là hai chỉ số ở **hai phạm vi khác nhau**: `heapUsedBytes` là byte Java heap đã dùng, `processors` là số CPU khả dụng. Không thể so trực tiếp `heapUsedBytes` với `getFreeMemorySize()` như thể cả hai cùng mô tả một vùng memory duy nhất; ngoài heap còn có native allocation, thread stacks, code cache và nhiều thành phần khác.

Việc dùng `MemoryMXBean` cho heap là cách phù hợp hơn nhiều so với gọi OS memory rồi giả định đó là heap mà GC đang sử dụng.

## 12. Kiểm tra extension khác: UnixOperatingSystemMXBean

Một số JVM trên hệ điều hành họ Unix cung cấp **interface mở rộng hơn nữa**:

~~~java
if (bean instanceof com.sun.management.UnixOperatingSystemMXBean unix) {
    long openDescriptors = unix.getOpenFileDescriptorCount();
    long descriptorLimit = unix.getMaxFileDescriptorCount();
    System.out.println(openDescriptors + " / " + descriptorLimit);
}
~~~

Đây là **đoạn minh họa** với `bean` đã lấy từ `ManagementFactory` và JDK có module `jdk.management`. `UnixOperatingSystemMXBean` kế thừa `com.sun.management.OperatingSystemMXBean`, có các method đếm **file descriptors** trên nền tảng hỗ trợ.

**Không** ép kiểu bean Windows sang interface Unix; cũng đừng chỉ nhìn `System.getProperty("os.name")` rồi cast. **Kiểm tra kiểu bằng `instanceof`**, sau đó mới dùng các phương thức chỉ có ở interface đó. Đây là một ví dụ khác cho nguyên tắc “kiểm tra kiểu được hỗ trợ”.

Nếu ứng dụng thực sự không cần số file descriptors, không cần phụ thuộc interface Unix này. Chọn **quyền truy cập và mức phụ thuộc nhỏ nhất đủ cho nhu cầu giám sát**.

## 13. Module system, tính tương thích và cách đóng gói

Nếu ứng dụng dùng **named modules** (JPMS), cần phân biệt:

~~~java
module app.metrics {
    requires java.management;  // MXBean chuẩn
    requires jdk.management;   // Chỉ khi dùng com.sun.management.*
}
~~~

Đây là **file `module-info.java` minh họa**, không phải file độc lập có `main`. Nếu **chỉ** dùng interface chuẩn, không cần `requires jdk.management`. Nếu gọi `com.sun.management.OperatingSystemMXBean`, phải compile và chạy trong JDK/runtime có module `jdk.management`; khi build runtime image bằng `jlink`, đừng loại module đó nếu chương trình cần nó.

Với **classpath** trên một bản OpenJDK/JDK đầy đủ, ví dụ đã kiểm thử có thể biên dịch/chạy bằng `javac --release 17` và `java` như phần 4 và phần 5.

**Lưu ý portability:** việc code chứa tham chiếu trực tiếp tới interface `com.sun.management` có nghĩa module này phải có sẵn khi JVM cần resolve loại đó. Một câu `instanceof` không phải cơ chế bảo đảm chương trình vẫn khởi động trong mọi custom Java runtime đã xóa `jdk.management`. Khi cần sản phẩm hoạt động cả trên Java SE-only runtimes, cách an toàn hơn là:

1. Tách code đọc thông tin chuẩn ra thành **thành phần chỉ yêu cầu `java.management`**.
2. Đóng gói bộ đọc extension thành **adapter tùy chọn**, chỉ kích hoạt khi runtime và module thực sự hỗ trợ.
3. Xác định dependencies tại build/launch; kiểm tra module availability ở pipeline thay vì chờ production fail.
4. Cho metric thiếu được biểu diễn là **unavailable**, không tự biến thành số 0.
5. Không dùng reflection trên class implementation không được export để vượt giới hạn module.

**Không nhầm package name với nội bộ JVM:** ở đây `com.sun.management` là package chính thức export từ `jdk.management`, khác với việc truy cập các package `jdk.internal.*` không công khai và phụ thuộc các cờ mở module rủi ro.

## 14. JMX và phạm vi bảo mật

Platform MXBean của JVM có thể được truy cập **trực tiếp trong process** qua `ManagementFactory`. Nó cũng nằm trong JMX/MBeanServer và có thể được quan sát bởi một ứng dụng quản trị qua JMX connection/proxy nếu hệ thống bật và cấu hình quyền phù hợp.

Ví dụ lấy MBeanServer nội bộ:

~~~java
javax.management.MBeanServer mbs =
        ManagementFactory.getPlatformMBeanServer();
~~~

Đây là mã minh họa; nó **không tự bật một cổng JMX từ xa** hoặc tự cấp quyền truy cập cho người khác. Việc vận hành JMX remote cần cấu hình riêng. Nếu bật JMX từ xa, phải quản lý **xác thực, phân quyền, kênh bảo mật, network access và audit**, vì platform beans có thể để lộ metadata của runtime và hệ điều hành.

**Nguyên tắc:** không cần mở remote JMX chỉ để ứng dụng tự đọc CPU/RAM của mình. Lấy bean local thường đơn giản và hạn chế bề mặt truy cập hơn. Nếu đưa các chỉ số đó ra HTTP endpoint, chính endpoint cũng cần chính sách truy cập/phân quyền phù hợp.

## 15. Những lỗi thường gặp

**Lỗi 1 — Gọi method mở rộng trên biến interface chuẩn.**  
`java.lang.management.OperatingSystemMXBean` không khai báo `getCpuLoad()`. Phải chuyển sang biến `com.sun.management.OperatingSystemMXBean` qua kiểm tra hợp lệ.

**Lỗi 2 — Ép kiểu trực tiếp mà không kiểm tra.**  
Có thể ném `ClassCastException` trên JVM không triển khai extension. Dùng `instanceof` pattern matching.

**Lỗi 3 — Dựa vào tên class implementation.**  
Không có bảo đảm class runtime luôn giữ cùng tên qua JDK vendor/version. Kiểm tra interface công khai.

**Lỗi 4 — Nghĩ `instanceof` đúng thì mọi phép đo đều dùng được.**  
Sai. CPU load có thể trả số âm, process CPU time có thể trả `-1`; phải kiểm tra từng giá trị.

**Lỗi 5 — Đổi `-1` thành 0% CPU.**  
Sai. `-1` là thông báo không đo được; 0 là một phép đo hợp lệ khác.

**Lỗi 6 — Xem `getSystemLoadAverage()` như phần trăm CPU.**  
Sai. Load average không phải fraction [0,1] và có thể lớn hơn 1.

**Lỗi 7 — Dùng `getSystemCpuLoad()` trong code mới.**  
Đã deprecated từ Java 14. Dùng `getCpuLoad()`.

**Lỗi 8 — Dùng tên `getFreePhysicalMemorySize()` và `getTotalPhysicalMemorySize()` trong code mới.**  
Hai method này cũng deprecated từ Java 14. Dùng `getFreeMemorySize()` và `getTotalMemorySize()`.

**Lỗi 9 — Nghĩ memory OS chính là Java heap.**  
Sai. Dùng `MemoryMXBean` cho heap và `OperatingSystemMXBean` extension cho môi trường.

**Lỗi 10 — Nghĩ `getAvailableProcessors()` luôn là số core vật lý host.**  
Sai. JVM thấy tài nguyên khả dụng, có thể bị container/cgroup/affinity giới hạn.

**Lỗi 11 — Gọi CPU load nhiều lần sát nhau rồi coi là các khoảng mẫu bằng nhau.**  
Sai. Khoảng quan sát implementation-specific; nhiều callers có thể tác động nhau.

**Lỗi 12 — Nghĩ `com.sun.management` là interface được mọi Java SE VM bắt buộc implement.**  
Sai. Đây là JDK extension; module/runtime phải hỗ trợ.

**Lỗi 13 — Tưởng `instanceof` có thể cứu mọi runtime thiếu module `jdk.management`.**  
Không đủ. Nếu code trực tiếp phụ thuộc class không tồn tại ở runtime, class loading/linkage có thể thất bại; tách adapter khi cần portability thực sự.

**Lỗi 14 — Dùng `UnixOperatingSystemMXBean` mà không kiểm tra kiểu.**  
Không nên. Đây là mở rộng Unix; trên Windows hoặc runtime khác, bean không nhất thiết implement.

**Lỗi 15 — So `processCpuTime` với thời gian tường `System.nanoTime()` như hai khái niệm giống nhau.**  
Sai. Một bên là CPU time đã sử dụng, bên kia là thời gian đơn điệu trôi qua giữa hai mốc; chúng khác nhau về đơn vị ý nghĩa dù đều có độ phân giải nanoseconds.

**Lỗi 16 — Bật JMX remote không bảo vệ để lấy vài chỉ số.**  
Không cần thiết và tăng nguy cơ lộ thông tin. Dùng local bean nếu chỉ giám sát JVM hiện tại.

## 16. Checklist triển khai an toàn

1. **Xác định metric cần đo:** tên OS, CPU count, load average, CPU usage fraction, process CPU time, memory hay swap?
2. **Lấy bean chuẩn:** `ManagementFactory.getOperatingSystemMXBean()`.
3. **Dùng interface chuẩn trước:** `getName()`, `getArch()`, `getAvailableProcessors()` hoặc `getSystemLoadAverage()`.
4. **Kiểm tra extension:** `bean instanceof com.sun.management.OperatingSystemMXBean extended`.
5. **Không ép kiểu mù quáng:** chỉ dùng biến `extended` trong nhánh đã được bảo vệ.
6. **Nếu cần metric Unix:** kiểm tra tiếp `UnixOperatingSystemMXBean`, không suy từ tên OS.
7. **Kiểm tra giá trị âm:** CPU load âm, CPU time `-1`, system load average âm cần thể hiện là unavailable.
8. **Dùng tên method hiện đại:** `getCpuLoad()`, `getFreeMemorySize()` và `getTotalMemorySize()` thay cho method deprecated.
9. **Phân biệt đơn vị:** CPU fraction, load average, nanoseconds, bytes là bốn kiểu số liệu khác nhau.
10. **Xác định phạm vi:** container/VM/host, JVM process, JVM heap; không gom lại thành một chỉ số mơ hồ.
11. **Lấy mẫu ổn định:** tránh hardcode một cửa sổ quan sát không được API hứa; lưu timestamp và tình trạng unavailable.
12. **Đóng gói đúng module:** `java.management` cho chuẩn; `jdk.management` nếu cần JDK extension.
13. **Kiểm thử nhánh fallback:** dùng test double như phần 5 cho runtime chỉ có interface chuẩn.
14. **Giới hạn phơi bày metrics:** bảo vệ dashboard, HTTP endpoints và JMX remote bằng cơ chế phù hợp.

## 17. Câu hỏi tự kiểm tra

**Câu 1.** API chuẩn nào lấy OperatingSystemMXBean của JVM hiện tại?  
**Đáp án:** `ManagementFactory.getOperatingSystemMXBean()`, trả kiểu chuẩn `java.lang.management.OperatingSystemMXBean`.

**Câu 2.** Khi biến chỉ có kiểu chuẩn, có thể gọi trực tiếp `getCpuLoad()` không?  
**Đáp án:** Không. Method này được khai báo trong extension `com.sun.management.OperatingSystemMXBean`.

**Câu 3.** Cách kiểm tra bean có hỗ trợ extension trong Java 17+?  
**Đáp án:** `if (bean instanceof com.sun.management.OperatingSystemMXBean extended) { ... }`.

**Câu 4.** Một bean có type extension rồi, CPU load có thể không khả dụng không?  
**Đáp án:** Có. `getCpuLoad()` có thể trả số âm, nên cần kiểm tra riêng.

**Câu 5.** `getSystemLoadAverage()` trả 3.2 có nghĩa CPU 320% không?  
**Đáp án:** Không. Đây là load average, không phải CPU usage fraction.

**Câu 6.** Ba tên method nào bị deprecated từ Java 14 và nên thay bằng gì?  
**Đáp án:** `getSystemCpuLoad() → getCpuLoad()`, `getFreePhysicalMemorySize() → getFreeMemorySize()`, `getTotalPhysicalMemorySize() → getTotalMemorySize()`.

**Câu 7.** Muốn quan sát Java heap used/max, nên gọi gì?  
**Đáp án:** `ManagementFactory.getMemoryMXBean().getHeapMemoryUsage()`, không nhầm với tổng memory môi trường của OS bean.

**Câu 8.** `getAvailableProcessors()` có được trả 0 không?  
**Đáp án:** Theo Javadoc chuẩn, không; kết quả tối thiểu là 1.

**Câu 9.** Trên JVM chỉ hỗ trợ interface chuẩn, cast ép sang extension sẽ gây gì?  
**Đáp án:** Có thể gây `ClassCastException`. Phải kiểm tra `instanceof` hoặc dùng thiết kế adapter tùy chọn.

**Câu 10.** `getProcessCpuTime()` trả `-1` có nghĩa process đã chạy âm một nanosecond không?  
**Đáp án:** Không. Đó là sentinel báo không hỗ trợ.

**Câu 11.** Có nên dùng method mở rộng của `UnixOperatingSystemMXBean` trực tiếp trên Windows?  
**Đáp án:** Không. Cần kiểm tra type bằng `instanceof`; chỉ dùng khi runtime thực sự hỗ trợ.

**Câu 12.** Vì sao khi compile cho một runtime JDK tùy chỉnh thiếu `jdk.management`, chỉ có `instanceof` chưa đủ?  
**Đáp án:** Vì code vẫn có thể phụ thuộc binary type không tồn tại khi linking/loading. Cần module/runtime phù hợp hoặc tách adapter JDK-specific.

**Câu 13.** Nếu người dùng muốn số CPU toàn host nhưng JVM chạy trong container, có thể lấy ngay `getAvailableProcessors()` rồi gọi đó là số CPU host không?  
**Đáp án:** Không. Nó mô tả CPUs **khả dụng cho JVM**, không bảo đảm số CPU vật lý host.

**Câu 14.** `getPlatformMXBean(com.sun.management.OperatingSystemMXBean.class)` có thể trả `null` không?  
**Đáp án:** Có nếu implementation không cung cấp interface đó, theo hợp đồng `getPlatformMXBean`; phải xử lý khả năng thiếu support.

## Tài liệu Java chính thức

- **Oracle Java SE 26 — `java.lang.management.OperatingSystemMXBean`:** interface chuẩn, `getName/Arch/Version/AvailableProcessors/SystemLoadAverage` và quy tắc giá trị âm cho load average. https://docs.oracle.com/en/java/javase/26/docs/api/java.management/java/lang/management/OperatingSystemMXBean.html
- **Oracle Java SE 26 — `com.sun.management.OperatingSystemMXBean`:** interface mở rộng, các chỉ số memory/swap/process/CPU, các method đã deprecated từ 14 và replacements vẫn được hỗ trợ. https://docs.oracle.com/en/java/javase/26/docs/api/jdk.management/com/sun/management/OperatingSystemMXBean.html
- **Oracle Java SE 17 — `com.sun.management.OperatingSystemMXBean`:** semantics Java 17+ và các method hiện hành, `getCpuLoad/getTotalMemorySize/getFreeMemorySize`. https://docs.oracle.com/en/java/javase/17/docs/api/jdk.management/com/sun/management/OperatingSystemMXBean.html
- **Oracle Java SE 26 — `ManagementFactory`:** `getOperatingSystemMXBean`, `getPlatformMXBean`, quy tắc singleton platform beans, MXBean/proxy/JMX. https://docs.oracle.com/en/java/javase/26/docs/api/java.management/java/lang/management/ManagementFactory.html
- **Oracle Java SE 26 — `UnixOperatingSystemMXBean`:** các chỉ số file descriptor theo nền tảng. https://docs.oracle.com/en/java/javase/26/docs/api/jdk.management/com/sun/management/UnixOperatingSystemMXBean.html
- **Oracle Java SE 26 — Module `jdk.management`:** module cho JDK-specific management interfaces, export `com.sun.management`. https://docs.oracle.com/en/java/javase/26/docs/api/jdk.management/module-summary.html
- **Oracle Java SE 26 — `MemoryMXBean` và `MemoryUsage`:** tách các số liệu Java heap khỏi số liệu memory môi trường. https://docs.oracle.com/en/java/javase/26/docs/api/java.management/java/lang/management/MemoryMXBean.html
- **OpenJDK JEP 394 — Pattern Matching for instanceof:** cú pháp `instanceof Type variable` ổn định từ Java 16, dùng trong ví dụ Java 17+. https://openjdk.org/jeps/394