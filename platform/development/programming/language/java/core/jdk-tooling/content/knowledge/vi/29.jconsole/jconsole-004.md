# MBean trong JConsole

## 1. MBean là gì?

**MBean (Managed Bean)** là một đối tượng Java được công bố qua Java Management Extensions (JMX) để công cụ quản trị có thể giám sát hoặc điều khiển một tài nguyên của ứng dụng hay của JVM.

MBean thường đại diện cho một thành phần có thể quản lý:

- Cache: dung lượng tối đa, số entry, thao tác xóa cache.
- Connection pool: số connection đang mở, giới hạn connection, thao tác kiểm tra hoặc đóng pool.
- Worker service: số job đang chờ, số worker hoạt động, thao tác tạm dừng hoặc tiếp tục.
- Cấu hình ứng dụng: giá trị cấu hình hiện tại, thao tác lưu hoặc reload.
- JVM: memory, thread, garbage collector, class loading và thông tin runtime.

MBean không chỉ là một JavaBean thông thường. Nó có **management interface** mà JMX công bố cho công cụ quản trị. Interface này mô tả các thuộc tính có kiểu dữ liệu, các thao tác có thể gọi và những notification mà MBean có thể phát ra.

JConsole sử dụng JMX để hiển thị các MBean đã đăng ký trong MBean Server. Tab **MBeans** cho phép xem thông tin, đọc/ghi attribute, gọi operation và đăng ký nhận notification.

## 2. MBean cung cấp những thành phần nào?

Một management interface thường có ba nhóm:

| Thành phần | Ý nghĩa | Ví dụ |
|---|---|---|
| Attribute | Giá trị có tên và kiểu dữ liệu; có thể chỉ đọc hoặc đọc/ghi | `CacheSize`, `EntryCount`, `Enabled` |
| Operation | Hành động mà client có thể gọi | `clear()`, `reload()`, `resetStatistics()` |
| Notification | Sự kiện MBean gửi tới client đã đăng ký nhận | Cache được xóa, cấu hình thay đổi, ngưỡng bị vượt |

Ví dụ với cache:

- `CacheSize`: số entry tối đa được cấu hình.
- `EntryCount`: số entry hiện có, chỉ đọc.
- `addEntries(int count)`: thêm dữ liệu thử nghiệm vào cache.
- `clear()`: xóa toàn bộ entry.
- `com.example.cache.cleared`: notification phát ra sau khi cache được xóa.

Attribute khác với operation. Attribute thể hiện trạng thái hoặc cấu hình của tài nguyên; operation là hành động được yêu cầu thực hiện. Một setter của attribute có thể làm thay đổi trạng thái ứng dụng, vì vậy thao tác ghi attribute cũng cần được kiểm soát.

## 3. JMX, MBean Server và ObjectName

JMX là cơ chế quản lý. MBean là đối tượng được quản lý. MBean Server là nơi đăng ký và cung cấp quyền truy cập tới các MBean.

Một JVM Java SE có **platform MBean Server** được truy cập bằng:

```java
MBeanServer server = ManagementFactory.getPlatformMBeanServer();
```

Các thành phần trong cùng JVM có thể đăng ký MBean ứng dụng vào server này. Nhờ vậy, JConsole và các JMX client có thể tìm thấy cả platform MXBean lẫn MBean do ứng dụng tạo.

Mỗi MBean trong một MBean Server có một tên duy nhất kiểu `ObjectName`. Cấu trúc tổng quát:

```text
domain:key=value,key2=value2
```

Ví dụ:

```text
com.example:type=CacheControl,name=primary
```

Trong ví dụ này:

- `com.example` là domain, thường dùng để nhóm MBean của ứng dụng.
- `type=CacheControl` xác định loại tài nguyên.
- `name=primary` phân biệt instance cụ thể.

Các thuộc tính của ObjectName có ý nghĩa như một tập key/value đối với JMX; thứ tự key không làm thay đổi định danh. Tuy nhiên, JConsole dùng thứ tự key để xây dựng cây hiển thị MBean. Nên thống nhất thứ tự, thường đặt `type` trước rồi tới `name`, để cây dễ đọc.

MBean được đăng ký bằng `registerMBean`:

```java
ObjectName name =
    new ObjectName("com.example:type=CacheControl,name=primary");

server.registerMBean(new CacheControl(), name);
```

Nếu tên đã được sử dụng trong cùng MBean Server, việc đăng ký sẽ thất bại với `InstanceAlreadyExistsException`. Hãy chọn ObjectName duy nhất cho từng instance.

## 4. Các loại MBean phổ biến

Java JMX hỗ trợ một số kiểu MBean:

| Loại | Đặc điểm | Khi dùng |
|---|---|---|
| Standard MBean | Management interface được xác định bằng quy ước tên và getter/setter | Cách đơn giản để công bố một thành phần Java |
| MXBean | Ánh xạ kiểu dữ liệu sang Open Types để client có thể hiểu mà không cần lớp miền riêng | Dữ liệu quản lý cần tương thích tốt với client từ xa |
| Dynamic MBean | Tự cung cấp `MBeanInfo` và xử lý attribute/operation tại runtime | Interface quản lý thay đổi động hoặc được cấu hình lúc chạy |
| Model MBean | Kiểu MBean linh hoạt, thường dùng trong framework quản trị | Hệ thống quản trị có metadata và hành vi phức tạp |

### 4.1. Standard MBean

Đây là kiểu phù hợp cho ví dụ học tập. Nếu class triển khai tên `CacheControl`, interface quản lý theo quy ước phải tên `CacheControlMBean` và cùng package với class triển khai.

Các getter/setter được nhận diện thành attribute:

- `getCacheSize()` và `setCacheSize(int)` tạo attribute `CacheSize` đọc/ghi.
- `getEntryCount()` tạo attribute `EntryCount` chỉ đọc.
- Các method khác như `clear()` và `addEntries(int)` trở thành operation.

Interface phải công khai các method muốn quản lý. Chỉ những method được khai báo trong management interface mới được công bố theo quy ước Standard MBean.

### 4.2. MXBean

MXBean có hậu tố `MXBean` hoặc được đánh dấu bằng annotation `@MXBean`. MXBean ánh xạ các kiểu Java được hỗ trợ sang Open Types, giúp client JMX từ xa không phải tải các class miền riêng của ứng dụng chỉ để đọc dữ liệu.

Các platform MBean của JVM đều là MXBean. Vì vậy, khi mở tab MBeans, bạn sẽ thường thấy các mục như Memory, Threading, Runtime và GarbageCollector.

### 4.3. Dynamic MBean

Dynamic MBean triển khai `DynamicMBean` và tự mô tả interface qua `MBeanInfo`. Cách này hữu ích nếu danh sách attribute hoặc operation chỉ được biết khi ứng dụng chạy, chẳng hạn cấu hình được đọc từ file hoặc plugin.

## 5. Platform MXBean có sẵn trong JVM

JVM đã công bố nhiều MXBean mà không cần viết MBean riêng. Một số ObjectName thường gặp:

| ObjectName | Chức năng |
|---|---|
| `java.lang:type=Memory` | Heap và non-heap memory |
| `java.lang:type=Threading` | Thread count, thread info, deadlock |
| `java.lang:type=Runtime` | Uptime, VM name, input arguments |
| `java.lang:type=ClassLoading` | Số class đã load và unload |
| `java.lang:type=OperatingSystem` | Thông tin hệ điều hành và process |
| `java.lang:type=GarbageCollector,name=...` | Số lần và thời gian GC |
| `java.lang:type=MemoryPool,name=...` | Mức sử dụng từng memory pool |
| `java.lang:type=Compilation` | Thông tin JIT compilation khi JVM hỗ trợ |

Tên collector và memory pool phụ thuộc JVM, GC và phiên bản Java. Không giả định mọi máy đều có cùng danh sách.

Một vài ví dụ có ích trong JConsole:

- **Memory**: xem `HeapMemoryUsage`, `NonHeapMemoryUsage`, `ObjectPendingFinalizationCount`; một số attribute có thể thay đổi.
- **Threading**: xem số thread, lấy thông tin stack và gọi thao tác phát hiện deadlock.
- **GarbageCollector**: xem `CollectionCount` và `CollectionTime`.
- **ClassLoading**: theo dõi số class đang được load.
- **Runtime**: xem `Uptime`, `VmName`, `VmVersion` và các VM input argument.

HotSpot còn cung cấp `HotSpotDiagnostic` MXBean, cho phép gọi operation như `dumpHeap` hoặc thay đổi một số VM option. Đây là các thao tác có ảnh hưởng tới process và file hệ thống; chỉ thực hiện khi đã hiểu tác động và có quyền phù hợp.

## 6. Mở JConsole và kết nối tới JVM

JConsole nằm trong thư mục `bin` của JDK. Kiểm tra công cụ và phiên bản:

```bash
java -version
jconsole -?
```

### 6.1. Kết nối local

Khởi chạy ứng dụng Java trước, sau đó mở JConsole:

```bash
jconsole
```

Trong hộp thoại kết nối:

1. Chọn tab hoặc danh sách **Local Process**.
2. Tìm JVM của ứng dụng theo PID, tên class hoặc tham số khởi chạy.
3. Chọn process cần giám sát.
4. Nhấn **Connect**.
5. Chọn **MBeans** để xem các MBean đã đăng ký.

Có thể truyền PID trực tiếp:

```bash
jconsole <PID>
```

Kết nối local dựa trên quyền truy cập của hệ điều hành. JConsole và JVM mục tiêu cần chạy bằng cùng user. Với Java SE hiện đại, JConsole có thể attach và bật management agent khi cần nếu JVM hỗ trợ Attach API và chính sách hệ thống cho phép.

Nếu process không xuất hiện hoặc không thể chọn, kiểm tra PID, user, quyền truy cập, filesystem tạm và khả năng attach của JVM. Không phải mọi process mang tên Java đều hỗ trợ attach.

### 6.2. Kết nối remote

Kết nối từ xa cần bật JMX agent trên JVM đích và cấu hình port. Ví dụ minh họa:

```bash
java \
  -Dcom.sun.management.jmxremote.port=7091 \
  -Dcom.sun.management.jmxremote.rmi.port=7092 \
  -Djava.rmi.server.hostname=monitor.example.internal \
  -jar application.jar
```

Các giá trị trong ví dụ cần thay bằng port chưa được sử dụng và hostname/IP có thể truy cập từ máy chạy JConsole. Hai port được cố định để dễ cấu hình firewall cho RMI registry và connector. `java.rmi.server.hostname` phải trỏ tới địa chỉ mà client có thể kết nối.

Trên máy quản trị, mở JConsole:

```bash
jconsole monitor.example.internal:7091
```

Nhập thông tin xác thực nếu agent yêu cầu. JMX remote dùng RMI; cấu hình mạng, DNS, firewall và certificate phải cho phép cả kết nối registry lẫn RMI connector.

Remote JMX có thể cho phép cả đọc thông tin lẫn điều khiển ứng dụng. Không mở port ra Internet hoặc mạng không tin cậy.

## 7. Cách đọc tab MBeans trong JConsole

Sau khi kết nối, JConsole có các tab chính như Overview, Memory, Threads, Classes, VM và MBeans. Mỗi tab trình bày một góc nhìn khác nhau; tab MBeans cho phép truy cập management interface tổng quát của MBean Server.

Trong tab **MBeans**:

- Cây bên trái liệt kê MBean theo domain và ObjectName.
- Chọn một MBean để xem metadata `MBeanInfo` và Descriptor.
- Các nhánh bên dưới thường gồm Attributes, Operations và Notifications.
- Chọn từng mục để xem giá trị, kiểu dữ liệu, mô tả và quyền truy cập tương ứng.

### 7.1. Xem Attributes

Chọn MBean rồi mở nhánh **Attributes**.

JConsole hiển thị danh sách attribute và giá trị hiện tại. Khi chọn một attribute, khung bên phải hiển thị giá trị, kiểu và metadata.

Một số attribute có thể đọc/ghi, một số chỉ đọc. Ví dụ:

| Attribute | Quyền thường gặp | Ý nghĩa |
|---|---|---|
| `CacheSize` | Read/Write | Số entry tối đa |
| `EntryCount` | Read-only | Số entry hiện có |
| `HeapMemoryUsage` | Read-only | Thông tin mức dùng heap |
| `Uptime` | Read-only | Thời gian JVM đã chạy |

Attribute dạng số có thể được mở thành biểu đồ trong JConsole nếu giao diện hỗ trợ. Giá trị có thể thay đổi theo chu kỳ refresh hoặc theo hoạt động của ứng dụng.

Chỉ sửa attribute khi biết rõ setter làm gì. Ví dụ, giảm `CacheSize` có thể khiến ứng dụng loại bỏ entry hoặc thay đổi hành vi cache.

### 7.2. Gọi Operations

Mở nhánh **Operations** để xem các method được công bố cho MBean. Chọn operation để xem mô tả, tham số và nút gọi.

Ví dụ:

- `clear()` xóa dữ liệu cache.
- `addEntries(int count)` thêm số entry thử nghiệm.
- `findDeadlockedThreads()` kiểm tra deadlock trên Threading MXBean.
- `dumpHeap(...)` yêu cầu JVM tạo heap dump trên HotSpotDiagnostic MXBean.

Khi gọi operation có tham số, nhập giá trị theo đúng kiểu được hiển thị rồi nhấn nút thực thi. Kết quả trả về sẽ hiển thị trong giao diện nếu operation có return value.

Operation có thể thay đổi trạng thái ứng dụng, tiêu tốn CPU, ghi file lớn hoặc làm tăng pause time. Hãy đọc mô tả và xác nhận tác động trước khi gọi trên production.

### 7.3. Nhận Notifications

Nếu MBean hỗ trợ notification, mở nhánh **Notifications** rồi nhấn **Subscribe**.

Sau khi đăng ký, JConsole hiển thị các notification nhận được và số lượng sự kiện. Chọn từng loại notification để xem metadata.

Notification hữu ích cho các sự kiện xảy ra theo thời gian như:

- Cache được xóa.
- Cấu hình thay đổi.
- Memory usage vượt ngưỡng.
- Một thành phần chuyển trạng thái.

MBean muốn phát notification cần hỗ trợ `NotificationBroadcaster` hoặc `NotificationEmitter` và công bố metadata notification. Nếu MBean không hỗ trợ, nhánh Notifications có thể không xuất hiện hoặc không có sự kiện để subscribe.

## 8. Tạo Standard MBean đơn giản cho ứng dụng

Ví dụ dưới đây tạo một MBean quản lý cache. Nó có hai attribute, hai operation và phát notification khi dung lượng cache thay đổi hoặc cache được xóa.

Tạo ba file trong cùng thư mục.

### 8.1. CacheControlMBean.java

```java
public interface CacheControlMBean {
    int getCacheSize();

    void setCacheSize(int size);

    int getEntryCount();

    void addEntries(int count);

    void clear();
}
```

`CacheSize` là attribute đọc/ghi, `EntryCount` là attribute chỉ đọc. `addEntries` và `clear` là operation.

### 8.2. CacheControl.java

```java
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicLong;
import javax.management.MBeanNotificationInfo;
import javax.management.Notification;
import javax.management.NotificationBroadcasterSupport;

public class CacheControl extends NotificationBroadcasterSupport
        implements CacheControlMBean {

    private final AtomicInteger cacheSize = new AtomicInteger(1000);
    private final AtomicInteger entryCount = new AtomicInteger();
    private final AtomicLong sequence = new AtomicLong();

    @Override
    public int getCacheSize() {
        return cacheSize.get();
    }

    @Override
    public void setCacheSize(int size) {
        if (size < 1) {
            throw new IllegalArgumentException("size must be positive");
        }

        int previous = cacheSize.getAndSet(size);
        entryCount.updateAndGet(current -> Math.min(current, size));

        if (previous != size) {
            sendNotification(new Notification(
                "com.example.cache.size.changed",
                this,
                sequence.incrementAndGet(),
                System.currentTimeMillis(),
                "Cache size changed from " + previous + " to " + size
            ));
        }
    }

    @Override
    public int getEntryCount() {
        return entryCount.get();
    }

    @Override
    public void addEntries(int count) {
        if (count < 0) {
            throw new IllegalArgumentException("count must not be negative");
        }

        entryCount.updateAndGet(current ->
            (int) Math.min(cacheSize.get(), (long) current + count)
        );
    }

    @Override
    public void clear() {
        int previous = entryCount.getAndSet(0);

        sendNotification(new Notification(
            "com.example.cache.cleared",
            this,
            sequence.incrementAndGet(),
            System.currentTimeMillis(),
            "Cache cleared; removed " + previous + " entries"
        ));
    }

    @Override
    public MBeanNotificationInfo[] getNotificationInfo() {
        String[] types = {
            "com.example.cache.size.changed",
            "com.example.cache.cleared"
        };

        return new MBeanNotificationInfo[] {
            new MBeanNotificationInfo(
                types,
                Notification.class.getName(),
                "Cache configuration and content events"
            )
        };
    }
}
```

`NotificationBroadcasterSupport` cung cấp cơ chế gửi notification. `getNotificationInfo()` mô tả các loại sự kiện để JConsole biết MBean có thể phát ra notification nào.

### 8.3. MBeanDemo.java

```java
import java.lang.management.ManagementFactory;
import java.util.concurrent.CountDownLatch;
import javax.management.MBeanServer;
import javax.management.ObjectName;

public class MBeanDemo {
    public static void main(String[] args) throws Exception {
        MBeanServer server =
            ManagementFactory.getPlatformMBeanServer();

        ObjectName name = new ObjectName(
            "com.example:type=CacheControl,name=primary"
        );

        server.registerMBean(new CacheControl(), name);

        System.out.println("Registered MBean: " + name);
        System.out.println("READY");

        new CountDownLatch(1).await();
    }
}
```

Chương trình đăng ký MBean vào platform MBean Server rồi chờ để JConsole có thời gian kết nối. Dừng chương trình bằng Ctrl+C trong terminal sau khi thực hành xong.

### 8.4. Biên dịch và chạy

Dùng JDK 17 trở lên:

```bash
javac CacheControlMBean.java CacheControl.java MBeanDemo.java
java MBeanDemo
```

Stdout:

```text
Registered MBean: com.example:type=CacheControl,name=primary
READY
```

Giữ terminal này mở. Mở terminal khác và chạy:

```bash
jconsole
```

Chọn process `MBeanDemo`, nhấn Connect rồi mở tab MBeans.

### 8.5. Thực hành trên MBeans tab

Trong cây MBeans, tìm domain `com.example`, chọn `CacheControl` với instance `primary`.

**Thử attribute:**

1. Mở Attributes.
2. Đọc `CacheSize`; giá trị ban đầu là `1000`.
3. Đọc `EntryCount`; giá trị ban đầu là `0`.
4. Sửa `CacheSize` thành `250`.
5. Đọc lại `CacheSize` để xác nhận setter đã được gọi.

**Thử operation:**

1. Mở Operations.
2. Chọn `addEntries`.
3. Nhập `40` cho tham số `count` rồi gọi operation.
4. Đọc `EntryCount`; kết quả mong đợi là `40`.
5. Gọi `clear()`.
6. Đọc lại `EntryCount`; kết quả mong đợi là `0`.

**Thử notification:**

1. Mở Notifications.
2. Nhấn Subscribe.
3. Gọi `addEntries` hoặc thay đổi `CacheSize`.
4. Gọi `clear()`.
5. Quan sát notification `com.example.cache.size.changed` hoặc `com.example.cache.cleared`.

Ví dụ giúp thấy rõ quan hệ giữa Java object, management interface, MBean Server và JConsole: thao tác trên giao diện được chuyển thành lời gọi JMX tới MBean đang chạy.

## 9. Đăng ký và hủy đăng ký MBean trong ứng dụng

Ứng dụng thường đăng ký MBean trong giai đoạn khởi tạo và hủy đăng ký khi thành phần dừng.

Ví dụ hủy đăng ký:

```java
if (server.isRegistered(name)) {
    server.unregisterMBean(name);
}
```

Có thể dùng `MBeanRegistration` để nhận callback trước/sau khi đăng ký hoặc hủy đăng ký. Điều này hữu ích khi MBean cần chuẩn bị tài nguyên hoặc dọn dẹp listener.

Nếu đăng ký nhiều instance, hãy đặt ObjectName khác nhau, chẳng hạn `name=primary`, `name=secondary`. Không dùng cùng ObjectName cho hai MBean trong một MBean Server.

## 10. Bảo mật khi dùng MBean và JConsole

JMX có thể cung cấp cả quyền đọc dữ liệu lẫn quyền gọi operation và sửa attribute. Vì vậy, quyền truy cập JMX phải được xem như quyền quản trị ứng dụng.

### Local monitoring

- Chạy JConsole bằng user phù hợp với process mục tiêu.
- Không chia sẻ quyền truy cập máy chủ vượt quá nhu cầu.
- JConsole tiêu thụ tài nguyên; cân nhắc mức ảnh hưởng khi dùng trên production.

### Remote monitoring

- Bật remote JMX có xác thực và TLS.
- Chỉ cho phép kết nối từ mạng hoặc host quản trị được phê duyệt.
- Cấu hình firewall cho đúng port RMI registry và connector.
- Cấu hình hostname/IP mà client có thể truy cập được.
- Dùng certificate và cơ chế xác thực phù hợp với chính sách tổ chức.
- Phân quyền read-only cho người chỉ cần quan sát; chỉ cấp read/write cho người thực sự cần điều khiển.
- Bảo vệ password/access file bằng quyền file nghiêm ngặt. File password dạng văn bản rõ chỉ phù hợp cho môi trường phát triển; production nên dùng xác thực bảo mật như SSL client certificate kết hợp password hoặc JAAS/LDAP theo hướng dẫn vận hành.

Không tắt xác thực hoặc SSL để làm cho kết nối hoạt động dễ hơn trên production. Không công khai JMX port trên Internet. Remote JMX cho phép gọi operation của MBean, vì vậy người có quyền điều khiển có thể gây thay đổi trạng thái ứng dụng.

## 11. Lỗi thường gặp khi làm việc với MBeans

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Không thấy MBean tự tạo trong cây | Chưa đăng ký, đăng ký vào MBean Server khác hoặc process chưa chạy đúng bản | Kiểm tra `registerMBean`, ObjectName và log khởi động |
| `NotCompliantMBeanException` | Sai quy ước tên interface, interface không hợp lệ hoặc method không tuân theo pattern | Kiểm tra class `Foo` có triển khai interface `FooMBean` phù hợp |
| `InstanceAlreadyExistsException` | ObjectName đã được đăng ký trong cùng server | Chọn tên instance duy nhất hoặc unregister instance cũ |
| Attribute không chỉnh sửa được | Không có setter hoặc attribute được công bố read-only | Kiểm tra management interface và setter |
| Operation không xuất hiện | Method không được khai báo trong interface quản lý | Thêm method vào management interface rồi build lại |
| Không thấy Notifications | MBean không hỗ trợ broadcaster/emitter hoặc không khai báo notification metadata | Triển khai `NotificationBroadcasterSupport` và `getNotificationInfo()` |
| Local process không kết nối được | Khác user, quyền attach hoặc JVM không hỗ trợ attach | Kiểm tra PID, user và chính sách Attach API |
| Remote connection timeout | Sai host/port, firewall hoặc RMI connector dùng port khác | Kiểm tra cả registry port và RMI connector port |
| Remote authentication thất bại | Sai password/access file, certificate hoặc truststore | Kiểm tra cấu hình xác thực và TLS ở cả client/server |
| JConsole thấy MBean nhưng gọi operation lỗi | Operation ném exception hoặc giá trị tham số không hợp lệ | Đọc lỗi trả về và kiểm tra validation trong MBean |

## 12. Nguyên tắc thiết kế MBean tốt

- **Tên rõ ràng:** dùng domain và ObjectName thể hiện thành phần, loại và instance.
- **Attribute nhẹ:** getter nên trả về nhanh, không chạy truy vấn lớn hoặc I/O chậm.
- **Operation có chủ đích:** chỉ công bố hành động cần thiết cho quản trị; mô tả rõ tác động.
- **Kiểu dữ liệu ổn định:** ưu tiên primitive, String, enum và kiểu có thể ánh xạ phù hợp qua JMX.
- **Thread-safe:** JConsole và các client khác có thể đọc/ghi đồng thời với ứng dụng.
- **Notification có chọn lọc:** phát sự kiện có giá trị, tránh gửi quá nhiều thông báo.
- **Không lộ bí mật:** không công bố password, token, secret, dữ liệu cá nhân hoặc cấu hình nhạy cảm.
- **Tách monitor và control:** người chỉ quan sát nên được cấp quyền đọc; operation thay đổi trạng thái cần quyền cao hơn.
- **Kiểm soát tác động:** thao tác heap dump, GC, thay đổi VM option hoặc reload cấu hình cần được đánh giá trước khi gọi.

## 13. Tổng kết

MBean là giao diện quản trị của một tài nguyên Java thông qua JMX. Trong JConsole, tab MBeans hiển thị các MBean đã đăng ký và cho phép thao tác trên attribute, operation và notification.

Các điểm cần nhớ:

- MBean đại diện cho tài nguyên ứng dụng hoặc thành phần JVM.
- Attribute mô tả trạng thái/cấu hình; operation thực hiện hành động; notification thông báo sự kiện.
- MBean phải được đăng ký trong MBean Server bằng ObjectName duy nhất.
- Standard MBean dùng interface theo quy ước `ClassNameMBean`.
- MXBean cung cấp kiểu dữ liệu phù hợp cho client JMX từ xa.
- Platform MXBeans cung cấp sẵn thông tin Memory, Threading, Runtime, ClassLoading và GC.
- JConsole dùng tab MBeans để xem, sửa attribute, gọi operation và subscribe notification.
- Remote JMX phải được bảo vệ bằng xác thực, TLS, phân quyền và giới hạn mạng.
- Chỉ gọi operation có ảnh hưởng khi hiểu rõ tác động tới ứng dụng.

**Tài liệu tham khảo chính thức:**

- [Oracle Java SE 24 — Using JConsole](https://docs.oracle.com/en/java/javase/24/management/using-jconsole.html)
- [Oracle Java SE 24 — Overview of Java SE Monitoring and Management](https://docs.oracle.com/en/java/javase/24/management/overview-java-se-monitoring-and-management.html)
- [Oracle Java SE 24 — Monitoring and Management Using JMX Technology](https://docs.oracle.com/en/java/javase/24/management/monitoring-and-management-using-jmx-technology.html)
- [Oracle Java SE 24 — StandardMBean API](https://docs.oracle.com/en/java/javase/24/docs/api/java.management/javax/management/StandardMBean.html)
- [Oracle Java SE 24 — JMX Security](https://docs.oracle.com/en/java/javase/24/jmx/security.html)
