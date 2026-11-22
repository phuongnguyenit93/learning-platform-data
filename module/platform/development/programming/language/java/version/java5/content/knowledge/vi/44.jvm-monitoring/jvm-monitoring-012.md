# MBeanServer, ObjectName và đăng ký Standard MBean

## 1. Từ đối tượng Java đến tài nguyên có thể quản lý

Giả sử ứng dụng có một bộ đếm yêu cầu. Mã nghiệp vụ có thể gọi trực tiếp đối tượng đó, nhưng công cụ vận hành cần một cách thống nhất để đọc thống kê hoặc điều chỉnh việc đếm trong lúc chương trình chạy.

JMX giải quyết nhu cầu này bằng ba thành phần:

| Thành phần | Vai trò |
| --- | --- |
| **MBean** | Đối tượng cung cấp giao diện quản lý cho một tài nguyên |
| **MBeanServer** | Nơi đăng ký, tìm và truy cập các MBean |
| **ObjectName** | Tên định danh MBean trong một MBeanServer |

Với **Standard MBean**, một giao diện Java công khai mô tả các thuộc tính và thao tác quản lý theo quy tắc đặt tên. Không phải mọi phương thức public của lớp nghiệp vụ đều được công bố.

Luồng sử dụng:

```text
Ứng dụng tạo đối tượng triển khai
    -> đăng ký trong MBeanServer bằng ObjectName
    -> phía quản lý đọc/ghi thuộc tính hoặc gọi thao tác
    -> thành phần sở hữu hủy đăng ký khi kết thúc vòng đời
```

Các khái niệm nền tảng được mô tả trong [gói javax.management](https://docs.oracle.com/en/java/javase/25/docs/api/java.management/javax/management/package-summary.html).

## 2. Standard MBean là một hợp đồng quản lý

Cách đặt tên thông thường:

```text
Lớp triển khai:       RequestMonitor
Giao diện quản lý:    RequestMonitorMBean
```

Lớp `RequestMonitor` triển khai giao diện `RequestMonitorMBean`. Giao diện quản lý phải là `public`; ví dụ dưới đây cũng dùng lớp triển khai public để việc biên dịch và khám phá giao diện rõ ràng.

Các phương thức được ánh xạ như sau:

| Phương thức trong giao diện | Thành phần JMX |
| --- | --- |
| `long getRequestCount()` | Thuộc tính `RequestCount`, chỉ đọc |
| `boolean isEnabled()` | Đọc thuộc tính `Enabled` |
| `void setEnabled(boolean value)` | Ghi thuộc tính `Enabled` |
| `void reset()` | Thao tác `reset` |

Tên thuộc tính là `RequestCount`, không phải `getRequestCount` hoặc `requestCount`. Tên và kiểu dữ liệu phải khớp khi truy cập.

Đây là cơ chế khám phá giao diện của Standard MBean; lớp hỗ trợ [StandardMBean](https://docs.oracle.com/en/java/javase/25/docs/api/java.management/javax/management/StandardMBean.html) cũng mô tả quan hệ đặt tên giữa lớp triển khai và giao diện.

Phân biệt thêm:

- **Standard MBean** là kiểu mô hình quản lý theo các mẫu đặt tên.
- **StandardMBean** là một lớp API có thể dùng làm bộ bọc để chọn giao diện quản lý tường minh.
- Không phải tạo Standard MBean nào cũng bắt buộc kế thừa lớp `StandardMBean`.

## 3. ObjectName gồm domain và các cặp khóa/giá trị

Một tên cụ thể có dạng:

```text
com.example.learning:type=RequestMonitor,name=main
```

Trong đó:

- `com.example.learning` là domain.
- `type=RequestMonitor` và `name=main` là các thuộc tính của **tên**.
- Các thuộc tính của tên khác thuộc tính quản lý như `Enabled` hay `RequestCount`.

Domain không phải địa chỉ mạng và không phải tên package bắt buộc của lớp. Chọn domain có không gian tên riêng giúp tránh va chạm giữa các thành phần.

`ObjectName` có cấu trúc, không phải chuỗi đường dẫn tùy ý. Cùng domain và cùng tập cặp khóa/giá trị vẫn có thể biểu diễn với thứ tự khóa khác nhau. Dùng `equals()` cho đối tượng tên và `getCanonicalName()` khi cần biểu diễn chuẩn hóa; không so sánh chuỗi tự ghép dựa vào thứ tự.

Một ObjectName chỉ định danh duy nhất trong MBeanServer tương ứng, không phải tên duy nhất trên mọi JVM.

### Giá trị có ký tự đặc biệt

Nếu giá trị chứa dấu phẩy hoặc ký tự cần xử lý đặc biệt, dùng `ObjectName.quote()`:

```java
// Đoạn minh họa; ObjectName thuộc javax.management.
String instance = "demo,local";
ObjectName name = new ObjectName(
        "com.example.learning:type=RequestMonitor,name="
                + ObjectName.quote(instance));
```

Kết quả là giá trị được đặt trong dấu nháy và escape theo cú pháp JMX. Không tự nối chuỗi từ dữ liệu động rồi hy vọng dấu phẩy, dấu nháy hoặc ký tự đại diện được hiểu như văn bản thường.

Quy tắc cú pháp, chuẩn hóa và quoting nằm trong [ObjectName](https://docs.oracle.com/en/java/javase/25/docs/api/java.management/javax/management/ObjectName.html). Giữ lại ObjectName đã tạo để sử dụng nhất quán; đừng tự bỏ dấu nháy vì cho rằng chúng không ảnh hưởng biểu diễn giá trị.

### Tên cụ thể khác mẫu truy vấn

```text
com.example.learning:type=RequestMonitor,name=main  -> tên cụ thể
com.example.learning:type=RequestMonitor,*          -> mẫu truy vấn
```

Mẫu thứ hai tìm các tên có khóa type tương ứng và có thể có thêm các khóa khác. `*` hoặc `?` trong một số vị trí có thể tạo pattern; không dùng pattern để đăng ký một MBean cụ thể. Có thể kiểm tra `ObjectName.isPattern()` khi nhận tên từ cấu hình.

## 4. Ví dụ đầy đủ: đăng ký, đọc, ghi, gọi và hủy đăng ký

Tạo ba tệp trong cùng một thư mục. Ví dụ dùng Java 17 trở lên, không cần framework hoặc thư viện ngoài.

### Tệp RequestMonitorMBean.java

```java
public interface RequestMonitorMBean {
    long getRequestCount();

    boolean isEnabled();

    void setEnabled(boolean enabled);

    void reset();
}
```

### Tệp RequestMonitor.java

```java
public class RequestMonitor implements RequestMonitorMBean {
    private long requestCount;
    private boolean enabled = true;

    @Override
    public synchronized long getRequestCount() {
        return requestCount;
    }

    @Override
    public synchronized boolean isEnabled() {
        return enabled;
    }

    @Override
    public synchronized void setEnabled(boolean enabled) {
        this.enabled = enabled;
    }

    @Override
    public synchronized void reset() {
        requestCount = 0L;
    }

    public synchronized void recordRequest() {
        if (enabled) {
            requestCount++;
        }
    }
}
```

`recordRequest()` là phương thức mà mã ứng dụng gọi trực tiếp. Nó không nằm trong giao diện quản lý nên không được công bố thành thao tác của Standard MBean này.

Ví dụ dùng `synchronized` để các lần đọc và thay đổi trạng thái của đối tượng được phối hợp khi mã ứng dụng và phía quản lý cùng truy cập. Đăng ký vào MBeanServer không tự làm đối tượng an toàn khi truy cập đồng thời.

### Tệp StandardMBeanDemo.java

```java
import java.lang.management.ManagementFactory;
import java.util.Arrays;
import javax.management.Attribute;
import javax.management.InstanceAlreadyExistsException;
import javax.management.MBeanServer;
import javax.management.ObjectName;

public class StandardMBeanDemo {
    public static void main(String[] args) throws Exception {
        MBeanServer server = ManagementFactory.getPlatformMBeanServer();

        ObjectName name = new ObjectName(
                "com.example.learning:type=RequestMonitor,name="
                        + ObjectName.quote("demo,local"));

        RequestMonitor monitor = new RequestMonitor();
        monitor.recordRequest();
        monitor.recordRequest();

        server.registerMBean(monitor, name);
        try {
            System.out.println("name=" + name.getCanonicalName());
            System.out.println("registered=" + server.isRegistered(name));
            System.out.println("request-count="
                    + server.getAttribute(name, "RequestCount"));
            System.out.println("enabled="
                    + server.getAttribute(name, "Enabled"));

            server.setAttribute(name, new Attribute("Enabled", false));
            monitor.recordRequest();
            System.out.println("after-disabled-request="
                    + server.getAttribute(name, "RequestCount"));

            server.invoke(name, "reset", new Object[0], new String[0]);
            System.out.println("after-reset="
                    + server.getAttribute(name, "RequestCount"));

            boolean exposed = Arrays.stream(
                    server.getMBeanInfo(name).getOperations())
                    .anyMatch(operation ->
                            "recordRequest".equals(operation.getName()));
            System.out.println("recordRequest-exposed=" + exposed);

            try {
                server.registerMBean(new RequestMonitor(), name);
            } catch (InstanceAlreadyExistsException expected) {
                System.out.println("duplicate=rejected");
            }
        } finally {
            server.unregisterMBean(name);
        }

        System.out.println("registered-after-cleanup="
                + server.isRegistered(name));
    }
}
```

Biên dịch và chạy trong thư mục chứa ba tệp:

```shell
javac RequestMonitorMBean.java RequestMonitor.java StandardMBeanDemo.java
java StandardMBeanDemo
```

Stdout chính xác:

```text
name=com.example.learning:name="demo,local",type=RequestMonitor
registered=true
request-count=2
enabled=true
after-disabled-request=2
after-reset=0
recordRequest-exposed=false
duplicate=rejected
registered-after-cleanup=false
```

Kết quả xác nhận cùng một đối tượng `monitor` được truy cập qua cả mã ứng dụng và MBeanServer:

- Hai lời gọi nghiệp vụ ban đầu tạo số đếm 2.
- Ghi thuộc tính Enabled=false làm lời gọi nghiệp vụ tiếp theo không tăng số đếm.
- Gọi thao tác reset qua MBeanServer đặt số đếm về 0.
- MBeanInfo cho thấy phương thức nghiệp vụ không được công bố.
- Đăng ký trùng tên bị từ chối; không ghi đè MBean trước.
- Khối finally hủy đăng ký sau khi lần đăng ký ban đầu đã thành công.

Các phương thức đăng ký và truy cập có trong [MBeanServer](https://docs.oracle.com/en/java/javase/25/docs/api/java.management/javax/management/MBeanServer.html).

## 5. Platform MBeanServer và phạm vi đăng ký

`ManagementFactory.getPlatformMBeanServer()` trả MBeanServer nền tảng của JVM; các platform MXBean như bộ nhớ và luồng được đăng ký ở đó. Ứng dụng cũng có thể đăng ký MBean riêng vào server này. Xem [ManagementFactory](https://docs.oracle.com/en/java/javase/25/docs/api/java.management/java/lang/management/ManagementFactory.html#getPlatformMBeanServer()).

Không tạo thêm server mới chỉ vì muốn lấy server hiện có. Một MBean đăng ký trong server A không tự xuất hiện trong server B. Nếu ứng dụng hoặc framework có nhiều MBeanServer, cần xác định server mà công cụ quản lý thực sự kết nối.

**Đăng ký cục bộ không đồng nghĩa mở cổng quản lý từ xa.** Ví dụ chỉ thao tác trong cùng JVM. Việc cung cấp kết nối quản lý qua mạng là một cấu hình riêng; không suy ra nó chỉ từ việc `registerMBean()` thành công.

MBeanServer không tự tạo luồng lấy mẫu thống kê cho RequestMonitor. Giá trị trong ví dụ được thay đổi bởi lời gọi ứng dụng hoặc thao tác quản lý, không do việc đăng ký tự sinh số liệu.

## 6. Đăng ký trùng, lỗi truy cập và quyền sở hữu vòng đời

Một số lỗi cần phân biệt:

| Ngoại lệ | Tình huống điển hình |
| --- | --- |
| `MalformedObjectNameException` | Chuỗi tên không đúng cú pháp |
| `NotCompliantMBeanException` | Đối tượng không đáp ứng mô hình MBean cần đăng ký |
| `InstanceAlreadyExistsException` | Tên đã có MBean trong server |
| `InstanceNotFoundException` | Tên không còn đăng ký khi truy cập/hủy |
| `AttributeNotFoundException` | Sai tên thuộc tính hoặc thuộc tính không truy cập được theo cách yêu cầu |
| `InvalidAttributeValueException` | Giá trị ghi không phù hợp kiểu/yêu cầu thuộc tính |
| `ReflectionException` | Không tìm thấy thao tác/chữ ký phù hợp hoặc có lỗi phản chiếu tương ứng |

Đối chiếu chính xác các trường hợp ở [hợp đồng MBeanServer](https://docs.oracle.com/en/java/javase/25/docs/api/java.management/javax/management/MBeanServer.html). Lỗi do phần triển khai thuộc tính/thao tác còn có thể được bọc trong ngoại lệ JMX tương ứng; khi điều tra, giữ nguyên nguyên nhân.

Không dùng mẫu “nếu tên đã có thì hủy rồi đăng ký lại” như cách xử lý chung cho đăng ký trùng. Có thể tên đó thuộc một thành phần khác. Xác định rõ thành phần sở hữu và chính sách va chạm tên.

`isRegistered()` hữu ích để quan sát, nhưng kiểm tra rồi đăng ký là hai thao tác khác nhau. Trong môi trường đồng thời, một bên khác có thể đăng ký giữa hai bước; vẫn phải xử lý lỗi của lần đăng ký thật.

Ví dụ đặt `try/finally` sau khi đăng ký thành công. Nếu đăng ký ban đầu thất bại do trùng tên, chương trình không đi vào khối hủy đăng ký để xóa nhầm MBean đã có. Trong ứng dụng nhiều thành phần, cần thêm phối hợp vòng đời để bên khác không thay thế đăng ký trong lúc chủ sở hữu đang sử dụng.

Hủy đăng ký chỉ loại bỏ đường truy cập qua MBeanServer. Nó không mặc nhiên đóng luồng, tệp hoặc các tài nguyên khác mà đối tượng nghiệp vụ đang giữ. Thành phần sở hữu vẫn phải quản lý những tài nguyên ấy.

## 7. Khi lớp triển khai không theo cặp tên thông thường

Nếu muốn chọn giao diện quản lý tường minh, có thể bọc đối tượng bằng `StandardMBean`:

```java
// Đoạn tích hợp thay cho lời gọi đăng ký trực tiếp trong ví dụ.
// monitor, server và name đã được tạo; name chưa được đăng ký.
javax.management.StandardMBean wrapper =
        new javax.management.StandardMBean(
                monitor, RequestMonitorMBean.class, false);
server.registerMBean(wrapper, name);
```

Tham số `false` chọn kiểu Standard MBean; đây không phải tùy chọn bật/tắt một tính năng nghiệp vụ. Lớp triển khai vẫn phải triển khai giao diện được chỉ định. [StandardMBean](https://docs.oracle.com/en/java/javase/25/docs/api/java.management/javax/management/StandardMBean.html) hỗ trợ cách chọn này mà không bắt buộc quan hệ tên lớp/giao diện.

Đoạn này là **cách thay thế**, không chạy tiếp trên cùng ObjectName đang đăng ký ở ví dụ trước.

## 8. Thiết kế giao diện quản lý có chủ đích

Một giao diện quản lý nhỏ giúp người vận hành hiểu rõ tác dụng:

- Thuộc tính đọc nên trả dữ liệu có ý nghĩa và tránh thao tác quá tốn kém.
- Setter phải kiểm tra giá trị hợp lệ và định nghĩa rõ thời điểm thay đổi có hiệu lực.
- Thao tác như reset cần được đặt tên và mô tả đúng; nó thay đổi trạng thái thật.
- Không đưa mọi phương thức nghiệp vụ vào giao diện MBean chỉ vì có sẵn phương thức public.

Trong ví dụ, reset làm bộ đếm giảm. Nếu số đếm được xuất sang hệ thống số liệu với giả định luôn tăng, phải xử lý việc đặt lại hoặc chọn mô hình thống kê khác. Đừng cho rằng việc công bố qua JMX tự quyết định ngữ nghĩa số liệu.

MBean quản lý có thể đọc thông tin và thay đổi hành vi ứng dụng. Chọn những gì cần công bố và xác định quyền truy cập của công cụ quản lý theo môi trường triển khai; bản thân một tên ObjectName không phải cơ chế phân quyền.

## 9. Tự kiểm tra

1. `RequestCount` là thuộc tính của ObjectName hay thuộc tính quản lý? **Thuộc tính quản lý** trong ví dụ.
2. `name=main` trong ObjectName có nghĩa tự động có getter getName không? **Không.**
3. Có thể đăng ký hai MBean cùng một tên trong cùng server không? **Không**, lần đăng ký sau bị từ chối.
4. Một phương thức public không nằm trong giao diện quản lý có tự xuất hiện không? **Không** với Standard MBean theo giao diện đang dùng.
5. Đăng ký thành công có nghĩa JMX từ xa đã được bật không? **Không.**
6. Hủy đăng ký có tự đóng mọi tài nguyên của đối tượng không? **Không.**

Sau khi chạy ví dụ, người học cần tự chỉ ra giao diện nào quyết định bề mặt quản lý, tên nào dùng để tìm đối tượng và thành phần nào chịu trách nhiệm đăng ký/hủy đăng ký.
