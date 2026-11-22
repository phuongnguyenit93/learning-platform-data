# RuntimeMXBean, CompilationMXBean và đặc tính JVM

## 1. Hai góc nhìn bổ sung cho nhau

Khi một ứng dụng chạy khác nhau giữa hai môi trường, cần biết chính xác JVM nào đang thực thi, phiên chạy bắt đầu lúc nào, nhận cấu hình gì và có hệ thống biên dịch JIT hay không.

Hai giao diện trong `java.lang.management` cung cấp các thông tin đó:

- **RuntimeMXBean** mô tả môi trường và phiên chạy JVM: tên/phiên bản triển khai, PID, thời điểm bắt đầu, thời gian hoạt động, tham số JVM và system properties.
- **CompilationMXBean** mô tả hệ thống biên dịch JIT của JVM, nếu có: tên trình biên dịch và khả năng đo thời gian biên dịch tích lũy.

Lấy chúng qua `ManagementFactory`:

~~~java
RuntimeMXBean runtime = ManagementFactory.getRuntimeMXBean();
CompilationMXBean compiler = ManagementFactory.getCompilationMXBean();
~~~

Đây là đoạn minh họa cần import các kiểu tương ứng trong `java.lang.management` và đặt trong phương thức. `runtime` là bean của JVM hiện tại; **compiler có thể null**. JVM không có hệ thống biên dịch thì không cung cấp CompilationMXBean. [ManagementFactory](https://docs.oracle.com/en/java/javase/25/docs/api/java.management/java/lang/management/ManagementFactory.html#getCompilationMXBean())

Các giao diện này vẫn áp dụng trong Java hiện hành. Bài dùng API chuẩn và ví dụ Java 17+, không dựa vào lớp JVM nội bộ hoặc tùy chọn đã bị loại bỏ.

## 2. Đọc đúng tên và phiên bản JVM

Một JVM có nhiều loại thông tin phiên bản. Không gộp tất cả thành một trường “Java version” rồi suy luận tùy ý.

| Getter của RuntimeMXBean | Ý nghĩa |
|---|---|
| `getVmName()` | Tên triển khai JVM |
| `getVmVendor()` | Nhà cung cấp triển khai JVM |
| `getVmVersion()` | Phiên bản triển khai JVM |
| `getSpecName()` | Tên đặc tả JVM |
| `getSpecVendor()` | Nhà cung cấp đặc tả JVM |
| `getSpecVersion()` | Phiên bản đặc tả JVM |
| `getManagementSpecVersion()` | Phiên bản đặc tả giao diện quản lý mà JVM triển khai |

Ví dụ, tên triển khai có thể là `OpenJDK 64-Bit Server VM`, trong khi phiên bản triển khai chứa cả thông tin bản cập nhật/build. Phiên bản đặc tả quản lý là một khái niệm khác, không phải phiên bản ngôn ngữ Java hay số bản vá JVM.

Không dùng việc chuỗi tên có chứa “Server VM” làm bằng chứng rằng một ứng dụng đang phục vụ máy chủ web, hoặc dùng tên nhà cung cấp đặc tả làm tên nhà cung cấp bản JDK đang cài. [RuntimeMXBean](https://docs.oracle.com/en/java/javase/25/docs/api/java.management/java/lang/management/RuntimeMXBean.html)

### Tên phiên JVM không phải hợp đồng định dạng PID

`getName()` trả chuỗi đại diện cho JVM đang chạy. Định dạng do triển khai lựa chọn; không viết mã tách chuỗi theo dấu `@` rồi mặc định phần đầu luôn là PID.

Trên Java hiện hành, lấy PID bằng:

~~~java
long pid = runtime.getPid();
~~~

PID giúp đối chiếu với công cụ hệ điều hành trong cùng bối cảnh máy/container. Nó không phải định danh duy nhất vĩnh viễn: PID có thể được tái sử dụng sau khi tiến trình kết thúc, và số PID ở các môi trường khác nhau có thể trùng nhau. Khi lưu chuỗi số liệu, ghép thêm môi trường và phiên chạy phù hợp.

## 3. Thời điểm khởi động khác với thời gian đã hoạt động

| Getter | Đại lượng |
|---|---|
| `getStartTime()` | Thời điểm JVM khởi động gần đúng, biểu diễn bằng mili giây theo mốc epoch |
| `getUptime()` | Số mili giây JVM đã hoạt động |

Để hiển thị thời điểm bắt đầu:

~~~java
Instant startedAt = Instant.ofEpochMilli(runtime.getStartTime());
~~~

Đoạn này cần import `java.time.Instant`. Dữ liệu từ `getStartTime()` đi vào `Instant.ofEpochMilli`, không phải `Instant.ofEpochSecond`.

Đối với thời gian hoạt động, đọc trực tiếp `getUptime()`. Không tự thay thế bằng phép trừ đồng hồ lịch `System.currentTimeMillis() - startTime` rồi coi hai phép đo luôn tương đương trong mọi điều kiện điều chỉnh đồng hồ.

Một JVM có thể chứa nhiều thành phần ứng dụng. Khởi tạo lại một bean, nạp lại một ngữ cảnh Spring hoặc chạy lại một tác vụ không đồng nghĩa khởi động lại JVM; các thao tác đó không tự đặt uptime về 0. Uptime cũng không phải thời gian xử lý của một yêu cầu. Nếu cần đo một đoạn mã, dùng công cụ đo thời gian thích hợp cho đoạn đó.

## 4. Tham số JVM, tham số main và system properties

Ba nguồn thông tin này có quan hệ nhưng không đồng nhất.

### 4.1. getInputArguments: tham số đưa vào JVM

Xét lệnh:

~~~shell
java -Dlesson.mode=demo JvmRuntimeDemo hello
~~~

Trong đó:

- `-Dlesson.mode=demo` cấu hình system property lúc khởi chạy JVM.
- `JvmRuntimeDemo` là tên lớp chính.
- `hello` là phần tử trong mảng `args` của phương thức `main`.

`runtime.getInputArguments()` không chứa các đối số của `main`. Nó cũng **không bảo đảm tái tạo đầy đủ nguyên văn lệnh java ban đầu**: có tùy chọn thuộc launcher không được chuyển cho JVM, và đầu vào JVM có thể đến từ nhiều nguồn như môi trường hoặc cấu hình. [getInputArguments](https://docs.oracle.com/en/java/javase/25/docs/api/java.management/java/lang/management/RuntimeMXBean.html#getInputArguments())

Vị trí trên lệnh có ý nghĩa. Với cú pháp chạy lớp, các đối số sau tên lớp là đối số ứng dụng; đặt một chuỗi `-D...` ở đó không tự biến nó thành tùy chọn JVM. [Lệnh java](https://docs.oracle.com/en/java/javase/25/docs/specs/man/java.html)

### 4.2. getSystemProperties: các thuộc tính hệ thống đang đọc được

`getSystemProperties()` trả `Map<String, String>` của các system properties. Các mục có tên hoặc giá trị không phải String bị bỏ qua. Đây không phải bản sao của biến môi trường hệ điều hành, cũng không phải danh sách duy nhất những thuộc tính đã được truyền bằng `-D`.

Ví dụ, `java.vm.name` do môi trường Java cung cấp; `lesson.mode` trong lệnh trên do ta chủ động truyền. System properties còn có thể được ứng dụng thay đổi khi chạy. Vì thế, danh sách tham số khởi động và giá trị thuộc tính ở thời điểm đọc có thể khác nhau về vai trò.

Khi cần chẩn đoán một cấu hình cụ thể, đọc đúng khóa đó. Không mặc định in toàn bộ map hoặc mọi tham số JVM: giá trị có thể chứa đường dẫn nội bộ, token hoặc thông tin cấu hình nhạy cảm.

### 4.3. Class path và library path có phạm vi riêng

`getClassPath()` phản ánh class path dùng bởi system class loader; `getLibraryPath()` phản ánh đường tìm thư viện native. Chúng không thay thế nhau.

Trên ứng dụng dùng module hoặc nhiều class loader, class path cũng không phải bản đồ đầy đủ mọi lớp/phụ thuộc có thể được nạp. Không suy ra toàn bộ dependency graph chỉ từ một chuỗi này.

Nếu phân tích danh sách đường dẫn của một JVM khác, chú ý dấu phân tách thuộc nền tảng JVM được giám sát, không mặc định luôn là dấu `:` hoặc luôn theo máy đang chạy công cụ.

## 5. CompilationMXBean giám sát JIT, không phải javac

`javac` biên dịch mã nguồn thành class file trước khi chạy. JIT (just-in-time compilation) là hoạt động JVM biên dịch mã đang thực thi sang mã máy trong quá trình chạy. CompilationMXBean giám sát hệ thống biên dịch của JVM, không báo thời gian chạy lệnh javac của dự án.

Giao diện chuẩn có ba phương thức chính:

| Phương thức | Ý nghĩa |
|---|---|
| `getName()` | Tên trình biên dịch JIT |
| `isCompilationTimeMonitoringSupported()` | JVM có hỗ trợ đo thời gian biên dịch hay không |
| `getTotalCompilationTime()` | Thời gian biên dịch tích lũy gần đúng, tính bằng mili giây |

Ba trường hợp phải phân biệt:

1. **Không có bean:** `ManagementFactory.getCompilationMXBean() == null`.
2. **Có bean nhưng không hỗ trợ đo thời gian:** vẫn có thể đọc tên, nhưng không gọi phương thức đo thời gian.
3. **Có bean và hỗ trợ đo thời gian:** đọc được bộ đếm tích lũy theo hợp đồng API.

Nếu gọi `getTotalCompilationTime()` khi không được hỗ trợ, API ném `UnsupportedOperationException`. Không ghi số 0 thay cho “không có dữ liệu”; 0 là một giá trị đo có ý nghĩa khác. [CompilationMXBean](https://docs.oracle.com/en/java/javase/25/docs/api/java.management/java/lang/management/CompilationMXBean.html)

## 6. Diễn giải thời gian biên dịch tích lũy

Giá trị của `getTotalCompilationTime()` không phải:

- Thời gian từ lúc bắt đầu đến khi ứng dụng sẵn sàng.
- Tổng thời gian CPU của ứng dụng.
- Thời gian biên dịch riêng của một phương thức.
- Một phần trăm hiệu năng.
- Bằng chứng rằng mọi tối ưu JIT đã hoàn tất.

Nếu nhiều luồng cùng biên dịch, phép đo cộng thời gian gần đúng của các luồng biên dịch. Do đó, không mặc định thời gian biên dịch tích lũy phải nhỏ hơn uptime, hoặc chỉ cần lấy `compilationTime / uptime` là ra phần trăm CPU của tiến trình.

Trong cùng một phiên JVM, hiệu giữa hai mẫu hợp lệ cho biết số đo biên dịch đã tăng bao nhiêu trong khoảng quan sát. Nếu JVM khởi động lại thì đường cơ sở cũng phải bắt đầu lại; không lấy hiệu giữa hai phiên.

Một giai đoạn JIT tăng nhanh lúc tải mới xuất hiện có thể đi cùng hoạt động làm nóng (warm-up). Muốn kết luận nó gây chậm, cần đối chiếu thêm tải, độ trễ và CPU. Không dùng riêng bộ đếm này để so sánh tốc độ của hai hãng JVM: định nghĩa và cách đo có thể khác nhau.

## 7. Ví dụ Java 17+ chạy độc lập

Chương trình sau chỉ xuất một tập trường được chọn. Nó kiểm tra sự có mặt của CompilationMXBean trước, rồi kiểm tra khả năng đo thời gian.

Lưu thành `JvmRuntimeDemo.java`:

~~~java
import java.lang.management.CompilationMXBean;
import java.lang.management.ManagementFactory;
import java.lang.management.RuntimeMXBean;
import java.time.Instant;
import java.util.Arrays;
import java.util.Map;

public class JvmRuntimeDemo {
    public static void main(String[] args) {
        RuntimeMXBean runtime = ManagementFactory.getRuntimeMXBean();
        Map<String, String> properties = runtime.getSystemProperties();

        System.out.println("vm.name=" + runtime.getVmName());
        System.out.println("vm.vendor=" + runtime.getVmVendor());
        System.out.println("vm.version=" + runtime.getVmVersion());
        System.out.println("vm.spec.version=" + runtime.getSpecVersion());
        System.out.println("management.spec.version="
                + runtime.getManagementSpecVersion());
        System.out.println("pid=" + runtime.getPid());
        System.out.println("started.at="
                + Instant.ofEpochMilli(runtime.getStartTime()));
        System.out.println("uptime.ms=" + runtime.getUptime());

        System.out.println("lesson.mode="
                + properties.getOrDefault("lesson.mode", "unset"));
        System.out.println("jvm.lesson.flag.present="
                + runtime.getInputArguments().contains("-Dlesson.mode=demo"));
        System.out.println("application.args=" + Arrays.toString(args));

        CompilationMXBean compiler = ManagementFactory.getCompilationMXBean();
        if (compiler == null) {
            System.out.println("compiler.present=false");
            return;
        }

        System.out.println("compiler.present=true");
        System.out.println("compiler.name=" + compiler.getName());
        boolean supported = compiler.isCompilationTimeMonitoringSupported();
        System.out.println("compiler.time.supported=" + supported);
        if (supported) {
            System.out.println("compiler.total.ms="
                    + compiler.getTotalCompilationTime());
        } else {
            System.out.println("compiler.total.ms=unavailable");
        }
    }
}
~~~

Biên dịch và chạy từ thư mục chứa tệp:

~~~shell
javac JvmRuntimeDemo.java
java -Dlesson.mode=demo JvmRuntimeDemo hello
~~~

Stdout của một lần chạy đã kiểm chứng với OpenJDK 24:

~~~text
vm.name=OpenJDK 64-Bit Server VM
vm.vendor=Azul Systems, Inc.
vm.version=24.0.2+12
vm.spec.version=24
management.spec.version=4.0
pid=54512
started.at=2026-10-30T02:08:53.699Z
uptime.ms=70
lesson.mode=demo
jvm.lesson.flag.present=true
application.args=[hello]
compiler.present=true
compiler.name=HotSpot 64-Bit Tiered Compilers
compiler.time.supported=true
compiler.total.ms=16
~~~

Các giá trị PID, thời điểm bắt đầu, uptime, thời gian JIT và thông tin triển khai có thể khác trên máy/lần chạy khác. Đây là dữ liệu quan sát thật, không phải bộ giá trị hằng để kiểm thử.

Những quan hệ cần thấy trong kết quả:

- `lesson.mode=demo` cho thấy khóa được đọc từ system properties.
- `jvm.lesson.flag.present=true` đối chiếu đúng tham số mẫu do ta đưa vào.
- `application.args=[hello]` cho thấy đối số ứng dụng được tách khỏi tùy chọn JVM.
- `management.spec.version=4.0` là phiên bản đặc tả quản lý trong lần chạy đó; nó không mâu thuẫn với `vm.spec.version=24`.
- Nhánh JIT chỉ đọc thời gian khi `compiler.time.supported` là true.

Chương trình thu thập tuần tự nên các trường động không phải ảnh chụp nguyên tử ở cùng một nano giây. Việc tự lấy thông tin và in kết quả cũng tạo ra công việc trong JVM, có thể ảnh hưởng các số đo rất nhỏ.

## 8. Thí nghiệm nhánh không có CompilationMXBean trên HotSpot

Đối với HotSpot, có thể chạy **riêng chương trình thí nghiệm** ở chế độ thông dịch:

~~~shell
java -Xint -Dlesson.mode=demo JvmRuntimeDemo hello
~~~

`-Xint` tắt biên dịch JIT sang mã máy trong chế độ này. Đây là tùy chọn bổ sung của HotSpot, không phải tùy chọn được bảo đảm bởi mọi JVM. Nó dùng ở đây để quan sát khác biệt, không phải đề xuất cấu hình hiệu năng cho ứng dụng thật. [HotSpot -Xint](https://docs.oracle.com/en/java/javase/25/docs/specs/man/java.html)

Trong lần chạy OpenJDK 24 đã kiểm chứng, phần kết quả liên quan là:

~~~text
compiler.present=false
~~~

Các dòng runtime và đối số vẫn được in trước dòng trên. Chương trình xử lý nhánh không có bean mà không gây NullPointerException.

Không dùng thí nghiệm này để khẳng định mọi triển khai JVM hay mọi chế độ chạy đều trả cùng kết quả. Mã ứng dụng vẫn cần kiểm tra null theo hợp đồng chuẩn, thay vì nhận diện bằng chuỗi tên JVM hoặc tự suy đoán từ một cờ.

## 9. Dùng trong chẩn đoán và thu thập số liệu

Hai nhóm dữ liệu nên có nhịp thu thập khác nhau:

- **Thông tin mô tả phiên chạy:** nhà cung cấp, tên/phiên bản JVM, PID, start time và các cấu hình đã chọn. Thường chỉ cần ghi lúc khởi động hoặc khi tạo báo cáo chẩn đoán.
- **Số liệu thay đổi theo thời gian:** uptime và thời gian biên dịch tích lũy nếu có. Lưu cùng mốc lấy mẫu và danh tính phiên phù hợp.

Đừng biến PID hoặc start time của từng phiên thành nhãn tùy ý trên mọi chuỗi metric mà không cân nhắc thiết kế lưu trữ; trước hết xác định cách hệ thống nhận diện instance và thời điểm khởi động lại.

Khi dùng JMX, các tên chuẩn là:

| Bean | ObjectName |
|---|---|
| RuntimeMXBean | `java.lang:type=Runtime` |
| CompilationMXBean nếu có | `java.lang:type=Compilation` |

Gọi trực tiếp ManagementFactory không cần mở cổng JMX từ xa. Nếu một công cụ dùng proxy đến JVM khác, dữ liệu phải được hiểu là của JVM đích; phân biệt rõ với JVM đang chạy chính công cụ.

Một bộ thu thập cần biểu diễn được “không có bean” và “không hỗ trợ phép đo”. Những trạng thái này là một phần của mô hình dữ liệu, không nên bị ép thành số 0 hoặc làm dừng ứng dụng được giám sát.

## 10. Lỗi thường gặp và bài tập

| Cách làm | Cách sửa |
|---|---|
| Tách `getName()` theo dấu @ để lấy PID | Dùng `getPid()` trên Java hiện hành |
| Coi uptime là thời gian ứng dụng web đã phục vụ | Uptime thuộc phiên JVM; định nghĩa thêm thời điểm sẵn sàng nếu cần |
| Đưa start time mili giây vào `ofEpochSecond` | Dùng `Instant.ofEpochMilli` |
| Tưởng `getInputArguments()` chứa args của main | Đọc `args` ở ứng dụng; phân biệt vai trò trên lệnh |
| Coi system properties là biến môi trường | Đây là hai nguồn dữ liệu khác nhau |
| Coi class path là toàn bộ phụ thuộc của mọi class loader | Hiểu đúng phạm vi của getter |
| Gọi compiler getter mà không kiểm tra null/khả năng | Xử lý ba trạng thái của hệ thống biên dịch |
| Dùng thời gian JIT làm điểm xếp hạng JVM | Đối chiếu workload và phép đo hiệu năng phù hợp |
| Log toàn bộ tham số và system properties | Chọn các trường chẩn đoán thực sự cần xuất |

Bài tập kiểm chứng:

1. Chạy chương trình với đối số main khác và xác định dòng nào phải thay đổi về mặt ngữ nghĩa; không yêu cầu PID hoặc uptime giữ nguyên.
2. Đổi `-Dlesson.mode=demo` thành một giá trị khác và giải thích vì sao thuộc tính đọc được thay đổi, còn phép kiểm tra đúng chuỗi `demo` có thể thành false.
3. Lưu hai mẫu thời gian biên dịch trong cùng một phiên chạy dài hơn; chỉ tính hiệu nếu bean tồn tại và phép đo được hỗ trợ.
4. Đối chiếu bản chạy thường với bản thí nghiệm `-Xint` trên HotSpot; phân biệt khác biệt của hệ thống biên dịch với các giá trị động luôn đổi sau mỗi lần khởi chạy.

Sau các bước này, cần giải thích được **JVM nào đang chạy, phiên chạy bắt đầu khi nào, cấu hình nào được quan sát và số đo JIT thực sự nói lên điều gì**.
