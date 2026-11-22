# Quan sát ứng dụng bằng JConsole qua kết nối được kiểm soát

## 1. JConsole giúp trả lời câu hỏi nào?

JConsole là công cụ giao diện đồ họa của JDK để đọc thông tin JVM qua JMX và thao tác với các MBean được công bố. Bạn có thể xem bộ nhớ, luồng, nạp lớp, thông tin JVM và các thuộc tính của Platform MXBean.

Một phiên quan sát có mục đích nên bắt đầu bằng câu hỏi cụ thể: “heap có tăng rồi giảm theo tải không?”, “luồng nào đang chờ?” hoặc “đây có đúng tiến trình cần đo không?”. JConsole cho thấy bằng chứng tại các thời điểm lấy mẫu; biểu đồ không tự giải thích nguyên nhân cuối cùng. [jconsole](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jconsole.html).

“Kết nối được kiểm soát” gồm ba việc: xác định đúng JVM, dùng đường truy cập và quyền phù hợp, rồi giới hạn những thao tác có thể làm thay đổi ứng dụng. JConsole có cả khả năng quản trị, nên mở được màn hình không đồng nghĩa mọi nút đều chỉ đọc.

## 2. Chọn đường kết nối trước khi mở công cụ

| Tình huống | Đường truy cập phù hợp | Điều cần kiểm tra |
| --- | --- | --- |
| Bài thực hành trên máy cá nhân | Kết nối cục bộ theo PID | Cùng người dùng hệ điều hành, đúng tiến trình |
| JVM trên máy chủ | JMX từ xa đã cấu hình bảo vệ | Mạng, TLS, danh tính, xác thực và quyền |
| JVM trong container hoặc tài khoản dịch vụ | Cách truy cập do môi trường triển khai cung cấp | Namespace, quyền attach, địa chỉ/cổng và chính sách vận hành |

Với JVM cục bộ hỗ trợ attach, không cần mở một cổng JMX từ xa chỉ để xem bài thực hành. JConsole và JVM đích phải chạy dưới cùng người dùng; quyền hệ điều hành là ranh giới truy cập của đường cục bộ. Nếu tiến trình không xuất hiện, không vội chạy công cụ bằng quyền cao hơn hoặc mở một cổng công khai. [JConsole: Local Monitoring](https://docs.oracle.com/en/java/javase/21/management/using-jconsole.html).

Trên môi trường vận hành, bản thân JConsole cũng tiêu thụ tài nguyên. Việc chạy công cụ đồ họa trên chính máy chủ chịu tải có thể làm thay đổi môi trường quan sát; thường nên dùng máy quản trị riêng với đường kết nối đã được kiểm soát.

## 3. Chuẩn bị JVM để quan sát

Bạn cần một JDK có công cụ `jconsole` và môi trường hiển thị đồ họa. Runtime được đóng gói tối giản hoặc bản headless có thể không chứa đầy đủ công cụ/giao diện cần thiết. Kiểm tra gói JDK đang dùng thay vì tải một chương trình không rõ nguồn.

Dùng chương trình Java 17+ sau làm đích quan sát. Nó:

- in PID để chọn đúng JVM;
- cấp phát một khối 256 KiB mỗi giây;
- giữ vòng tròn 32 tham chiếu đến các khối, khoảng 8 MiB nội dung mảng;
- tự kết thúc theo thời lượng đã chọn.

Lưu thành `ConsoleTarget.java`:

```java
import java.lang.ref.Reference;

public class ConsoleTarget {
    public static void main(String[] args) throws InterruptedException {
        int seconds = args.length == 0 ? 300 : Integer.parseInt(args[0]);
        if (seconds < 1 || seconds > 900) {
            throw new IllegalArgumentException("Duration must be 1..900 seconds");
        }

        byte[][] retained = new byte[32][];
        System.out.println("PID=" + ProcessHandle.current().pid());
        System.out.println("Observation seconds=" + seconds);
        try {
            for (int tick = 0; tick < seconds; tick++) {
                byte[] block = new byte[256 * 1024];
                block[0] = (byte) tick;
                retained[tick % retained.length] = block;
                Thread.sleep(1000);
            }
        } finally {
            Reference.reachabilityFence(retained);
        }
        System.out.println("Finished");
    }
}
```

`Reference.reachabilityFence(retained)` giữ mảng tham chiếu có thể tiếp cận đến cuối phần quan sát; nó không ép JVM chạy GC. [Reference.reachabilityFence](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ref/Reference.html#reachabilityFence(java.lang.Object)). Kích thước khoảng 8 MiB chỉ tính phần nội dung các khối được giữ, chưa bao gồm đối tượng/mảng tham chiếu và tài nguyên JVM.

Biên dịch và chạy trong cửa sổ lệnh thứ nhất:

```shell
javac ConsoleTarget.java
java -Xms32m -Xmx128m ConsoleTarget 300
```

PID thay đổi mỗi lần chạy. Hai dòng đầu có dạng:

```text
PID=65184
Observation seconds=300
```

65184 ở đây là PID minh họa; phải dùng số vừa được JVM của bạn in, không sao chép số đó để chọn tiến trình.

Nếu chỉ kiểm tra chương trình chạy được, dùng thời lượng hai giây:

```shell
java -Xms32m -Xmx128m ConsoleTarget 2
```

Một lần chạy thực tế trên JDK 24 in:

```text
PID=65184
Observation seconds=2
Finished
```

Trong phiên 300 giây, dòng `Finished` chỉ xuất hiện sau khi vòng quan sát kết thúc. Kết thúc sớm bằng ngắt từ cửa sổ lệnh có thể tạo thông báo ngắt thay vì dòng đó; đó không phải kết quả của lỗi JConsole.

## 4. Kết nối cục bộ bằng PID

Giữ cửa sổ chương trình đích đang chạy. Ở cửa sổ lệnh thứ hai, chạy:

```shell
jconsole
```

Trong hộp kết nối, chọn tiến trình có tên lớp `ConsoleTarget` và PID khớp với cửa sổ thứ nhất. Hoặc dùng dạng lệnh `jconsole PID`, thay PID bằng số của chính phiên đó.

Có thể dùng lệnh sau để đối chiếu tên lớp và PID:

```shell
jcmd -l
```

Danh sách phát hiện phụ thuộc quyền và môi trường. JVM trong container khác có thể không xuất hiện như tiến trình cục bộ thông thường; không coi “không có trong danh sách” là bằng chứng JVM đã tắt. [jcmd](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html).

Sau khi vào được phiên:

1. Đối chiếu PID, tên ứng dụng, thời gian chạy và phiên bản JVM.
2. Xác nhận đang quan sát JVM đích, không phải JVM chạy JConsole.
3. Dùng nhịp cập nhật vừa phải; chưa cần rút xuống mức quá dày.

Có thể khởi động công cụ với khoảng cập nhật năm giây:

```shell
jconsole -interval=5
```

Tùy chọn này điều khiển khoảng cập nhật của JConsole theo giây. Nó không thay tần suất chạy GC hoặc nhịp xử lý công việc của ứng dụng. JConsole có JVM riêng; các tùy chọn bắt đầu bằng `-J` được gửi cho JVM của **công cụ**, không tự sửa JVM đích. [jconsole options](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jconsole.html).

Nếu xuất hiện cảnh báo kết nối không bảo vệ, phải xác định nó thuộc đường cục bộ dự kiến hay một endpoint từ xa. Không biến việc chấp nhận kết nối không mã hóa thành thao tác mặc định cho mọi trường hợp. Với endpoint từ xa yêu cầu TLS, lỗi TLS cần được chẩn đoán trước khi gửi thông tin đăng nhập.

## 5. Quan sát theo thứ tự để tránh đọc sai biểu đồ

### Bắt đầu bằng danh tính và thời gian

Ở phần thông tin JVM/VM Summary, đối chiếu phiên bản, thời gian chạy và thông tin khởi động với phiên đang đo. `RuntimeMXBean` là một nguồn của dữ liệu này: chẳng hạn PID, uptime và đối số JVM. Đối số JVM không nhất thiết bao gồm các đối số của hàm `main`. [RuntimeMXBean](https://docs.oracle.com/en/java/javase/21/docs/api/java.management/java/lang/management/RuntimeMXBean.html).

Đừng chụp ảnh toàn bộ phần đối số/cấu hình rồi chia sẻ ngay. Chúng có thể chứa đường dẫn, tên máy hoặc thông tin nhạy cảm nếu ứng dụng cấu hình không đúng. Ghi bằng chứng cần thiết và che dữ liệu trước khi chia sẻ.

### Memory: chọn phạm vi rồi đọc xu hướng

Xem heap, non-heap và các pool được JVM hiện tại công bố. Danh sách pool không cố định giữa các collector hoặc các bản JVM. `used` là phần đang dùng, `committed` là phần đã được bảo đảm sẵn cho JVM, còn `max` là giới hạn nếu xác định được. Không lấy heap `used` làm toàn bộ bộ nhớ của tiến trình. [MemoryMXBean](https://docs.oracle.com/en/java/javase/21/docs/api/java.management/java/lang/management/MemoryMXBean.html), [MemoryUsage](https://docs.oracle.com/en/java/javase/21/docs/api/java.management/java/lang/management/MemoryUsage.html).

Với chương trình mẫu, số khối được giữ tăng đến 32 rồi bị thay thế vòng tròn. Sau khi đạt mức đó, dữ liệu mới vẫn tiếp tục được tạo, còn khối cũ có thể trở thành đối tượng không còn dùng. Vì thời điểm GC và cách thống kê phụ thuộc JVM, không yêu cầu biểu đồ phải giảm đúng mỗi giây hoặc có cùng hình dạng trên mọi máy.

Một đoạn tăng rồi giảm có thể là hoạt động cấp phát/thu gom bình thường. Một đoạn tăng ngắn chưa đủ kết luận rò rỉ. Muốn điều tra cần so tải, mức còn lại sau thu gom và nhiều khoảng quan sát tương đương.

### Threads: xem luồng nào, không chỉ xem tổng số

Ở phần Threads, xem số luồng, chọn `main` của chương trình mẫu và đọc stack. Trong phần lớn thời gian nó ngủ giữa các lần cấp phát, nên thường thấy `TIMED_WAITING` quanh `Thread.sleep`. Đây là hành vi chủ động của mẫu, không phải một deadlock.

Các số liệu ThreadMXBean thuộc **luồng nền tảng**; chúng không tạo một danh sách đầy đủ mọi luồng ảo. Tính năng phát hiện deadlock cũng có phạm vi loại luồng và khóa được hỗ trợ. Không dùng một kết quả không phát hiện được để khẳng định mọi tác vụ đang tiến triển. [ThreadMXBean](https://docs.oracle.com/en/java/javase/21/docs/api/java.management/java/lang/management/ThreadMXBean.html).

### Classes và CPU: thêm ngữ cảnh

Số lớp đang nạp tăng lúc khởi động hoặc do thư viện được dùng lần đầu có thể là bình thường. Cần phân biệt số lớp đang tồn tại với tổng đã từng nạp; không gọi mọi mức tăng là rò rỉ class loader. [ClassLoadingMXBean](https://docs.oracle.com/en/java/javase/21/docs/api/java.management/java/lang/management/ClassLoadingMXBean.html).

Ứng dụng mẫu dành nhiều thời gian ngủ, nên CPU có thể thấp. JConsole không phải công cụ xác định phương thức nóng chỉ từ một đường CPU tổng thể; khi câu hỏi chuyển thành “đoạn mã nào tốn thời gian?”, cần bằng chứng chuyên sâu hơn như ghi nhận JFR hoặc công cụ phù hợp.

## 6. MBeans: đọc giao diện quản lý trực tiếp

Tab MBeans hiển thị các MBean đăng ký trong Platform MBeanServer. Cây có thể được nhóm theo các thuộc tính của ObjectName; cách trình bày cụ thể có thể thay đổi theo phiên bản công cụ. Mục tiêu là tìm đúng định danh, không học thuộc vị trí một dòng trong ảnh chụp cũ. [Using JConsole: MBeans](https://docs.oracle.com/en/java/javase/21/management/using-jconsole.html).

Các định danh chuẩn có ích:

| ObjectName | Dữ liệu nên đọc trong bài |
| --- | --- |
| `java.lang:type=Runtime` | Uptime, phiên bản, PID hoặc dữ liệu môi trường được công bố |
| `java.lang:type=Memory` | HeapMemoryUsage, NonHeapMemoryUsage |
| `java.lang:type=Threading` | Thông tin luồng nền tảng |
| `java.lang:type=ClassLoading` | Số lớp đang nạp và bộ đếm liên quan |
| `java.lang:type=MemoryPool,name=...` | Dữ liệu của pool thực tế |

Tên hiển thị của các thuộc tính tương ứng getter của MXBean: ví dụ `getHeapMemoryUsage()` được công bố là `HeapMemoryUsage`. Kiểu phức hợp có thể được trình bày thành bảng/cấu trúc để mở các trường con. [ManagementFactory](https://docs.oracle.com/en/java/javase/21/docs/api/java.management/java/lang/management/ManagementFactory.html).

**Attributes** có thể có cả thuộc tính đọc và ghi. **Operations** là các thao tác có thể gọi vào JVM hoặc ứng dụng. Với nhiệm vụ quan sát, ưu tiên đọc các thuộc tính cần thiết; không bấm một thao tác chỉ để xem nó làm gì.

Ví dụ, yêu cầu GC, đặt lại thống kê đỉnh, đổi ngưỡng hoặc chụp heap đều có thể thay đổi điều kiện đo hoặc tiêu thụ tài nguyên. Quyền truy cập và tác động phải được biết trước. Nút mang tên “Perform GC” không phải một bước bắt buộc để biểu đồ trở nên đúng.

Khu vực **Notifications** cho phép đăng ký nhận thông báo, nhưng đăng ký không tự tạo ra điều kiện kích hoạt. Với thông báo bộ nhớ, pool phải hỗ trợ loại ngưỡng tương ứng và có chính sách ngưỡng thích hợp; không nhận sự kiện trong vài giây chưa chứng minh công cụ hỏng. [MemoryNotificationInfo](https://docs.oracle.com/en/java/javase/21/docs/api/java.management/java/lang/management/MemoryNotificationInfo.html).

## 7. Khi cần kết nối từ xa: chuẩn bị một endpoint được bảo vệ

JMX từ xa qua agent tích hợp thường dùng RMI. Cần phân biệt cổng registry để tìm connector và cổng connector để trao đổi tiếp theo; mở được một cổng không bảo đảm toàn bộ đường kết nối hoạt động.

Một cấu hình vận hành cần trả lời rõ:

| Mặt kiểm soát | Câu hỏi cần có đáp án |
| --- | --- |
| Địa chỉ/cổng | Registry và connector nghe ở đâu, máy quản trị đi tới được đâu? |
| Phạm vi mạng | Chỉ máy hoặc mạng quản trị nào được phép tiếp cận? |
| TLS | Máy chủ dùng chứng chỉ nào, máy khách tin cậy bằng cách nào? |
| Xác thực | Ai được kết nối, có yêu cầu chứng chỉ máy khách không? |
| Phân quyền | Danh tính quan sát có chỉ quyền đọc hay có cả quyền thay đổi? |
| Vòng đời | Ai cấp, thay thế và thu hồi quyền/chứng chỉ? |

Các thuộc tính agent thường gặp gồm `com.sun.management.jmxremote.port` cho registry, `com.sun.management.jmxremote.rmi.port` để ấn định cổng connector và `java.rmi.server.hostname` cho địa chỉ được quảng bá trong tham chiếu RMI. Địa chỉ quảng bá **không phải** quy tắc firewall hay bảo đảm chỉ lắng nghe trên một giao diện. [JMX Monitoring: Remote Monitoring](https://docs.oracle.com/en/java/javase/25/management/monitoring-and-management-using-jmx-technology.html).

Với endpoint dùng TLS, phải chuẩn bị keystore/truststore và danh tính đúng cho cả hai phía theo chính sách. Khi dùng xác thực chứng chỉ hai chiều, máy quản trị cũng phải có khóa/chứng chỉ được máy chủ tin cậy. Không sửa lỗi chứng chỉ bằng cách tin mọi chứng chỉ hoặc tắt mã hóa.

Mô hình bảo vệ agent cần xem cả connector và registry. Các thuộc tính liên quan gồm `com.sun.management.jmxremote.ssl`, `com.sun.management.jmxremote.registry.ssl`, `com.sun.management.jmxremote.ssl.need.client.auth` và `com.sun.management.jmxremote.authenticate`. Chỉ bật TLS cho connector không tự bảo vệ một registry còn mở không đúng chính sách. [JMX security configuration](https://docs.oracle.com/en/java/javase/25/management/monitoring-and-management-using-jmx-technology.html).

Ở JConsole, nhập endpoint đã được cấp và thông tin xác thực qua luồng được quản lý. Các tùy chọn truststore/keystore phía công cụ thuộc JVM JConsole; các tùy chọn phía server thuộc JVM ứng dụng. Không đặt mật khẩu thật vào lệnh được lưu lịch sử hay chia sẻ cùng ảnh chụp.

### Chọn quyền đọc cho mục đích quan sát

Với cơ chế phân quyền bằng access file, mức `readonly` cho phép đọc thuộc tính và nhận thông báo, còn mức `readwrite` cho phép thêm các thao tác thay đổi/quản trị. Dùng danh tính quan sát có quyền tối thiểu; không cấp quyền ghi chỉ vì muốn hết một lỗi “access denied”. Cơ chế đăng nhập và ánh xạ quyền trong triển khai cụ thể vẫn phải được cấu hình đúng. [Java SE 21 Monitoring and Management Guide](https://docs.oracle.com/en/java/javase/21/management/java-se-monitoring-and-management-guide.pdf).

Kết nối local attach cùng người dùng thường không bị hạn chế bởi access file của connector từ xa. Vì vậy, lựa chọn đúng thao tác và bảo vệ tài khoản hệ điều hành vẫn cần thiết; đừng coi chữ “cục bộ” là đồng nghĩa quyền chỉ đọc.

Một tunnel hoặc VPN có thể giới hạn đường mạng, nhưng không tự giải quyết địa chỉ RMI quảng bá, mọi cổng cần thiết, danh tính TLS hay quyền JMX. Giữ các lớp kiểm soát có trách nhiệm rõ ràng thay vì mặc định có tunnel là đủ.

## 8. Chẩn đoán lỗi theo lớp

| Hiện tượng | Hướng kiểm tra |
| --- | --- |
| Không có lệnh `jconsole` | JDK/gói công cụ, PATH và môi trường đồ họa |
| JVM cục bộ không xuất hiện | PID còn sống, cùng người dùng, quyền attach, container và cấu hình runtime |
| Kết nối bị từ chối ngay | Agent đã bật chưa, đúng địa chỉ/cổng chưa, đường mạng có cho phép không |
| Registry tới được nhưng sau đó treo/lỗi | Cổng connector và địa chỉ RMI quảng bá |
| TLS bắt tay lỗi | Chuỗi tin cậy, chứng chỉ, khóa, thời gian hệ thống và chính sách TLS |
| Đăng nhập thất bại | Danh tính, cấu hình xác thực và quyền đọc tài liệu xác thực của agent |
| Đọc được nhưng thao tác bị từ chối | Có thể đúng thiết kế quyền quan sát; xem phạm vi quyền |
| Biểu đồ ngắt hoặc đứng yên | Tiến trình đã dừng, kết nối mất, JVM quá bận hoặc khung thời gian đang xem |

Trên Windows, quyền file/thư mục tạm và quyền của tài khoản cũng ảnh hưởng local monitoring. Không chữa một lỗi bằng việc đồng loạt mở quyền file, mở firewall hoặc tắt xác thực. Hãy xác định lớp thất bại rồi sửa đúng cấu hình của lớp đó.

Không dựa vào ảnh giao diện nhiều năm trước để kết luận thiếu một pool hoặc thiếu một nút. Đối chiếu JDK, loại JVM, collector, quyền và MBean metadata đang có.

## 9. Kết thúc phiên quan sát có bằng chứng

Ghi lại JVM/PID, thời gian, tải trong khoảng đo, biểu đồ hoặc thuộc tính liên quan và giới hạn của kết luận. Nếu xuất dữ liệu, ghi rõ đơn vị và phạm vi; dữ liệu heap không mang nghĩa RSS của hệ điều hành.

Ngắt kết nối JConsole khi xong. Đóng công cụ không dừng JVM đích và không tự thu hồi endpoint JMX từ xa đã mở. Chương trình mẫu tự kết thúc theo thời lượng; endpoint quản trị thật phải có vòng đời và chính sách truy cập riêng.

Bài tập thực hành:

1. Chạy `ConsoleTarget` trong 300 giây, kết nối đúng PID và xác nhận uptime tăng.
2. Xem heap cùng một pool thực tế; giải thích vì sao hai góc nhìn không bắt buộc có cùng đường biểu diễn.
3. Tìm luồng `main`, đối chiếu stack ngủ với mã nguồn, rồi giải thích vì sao trạng thái chờ đó là bình thường.
4. Đọc `HeapMemoryUsage` ở MBeans mà không gọi thao tác thay đổi.
5. Viết kết luận ngắn có nguồn dữ liệu, khoảng thời gian và điều chưa thể suy ra; không kết luận rò rỉ chỉ từ vài điểm tăng.

Một phiên JConsole hữu ích là phiên chọn đúng JVM, giữ đúng ranh giới truy cập và trả lời được câu hỏi quan sát bằng dữ liệu có ngữ cảnh.
