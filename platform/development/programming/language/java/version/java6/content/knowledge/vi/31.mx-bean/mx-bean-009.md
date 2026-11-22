# MXBean: Notification và quan sát thay đổi trạng thái trong Java 17+

## 1. Vì sao cần Notification khi đã có MXBean?

MXBean cho phép công cụ quản trị truy vấn các **attributes** và gọi những **operations** của đối tượng Java thông qua JMX (Java Management Extensions). Ví dụ một ứng dụng có MXBean đại diện cho trạng thái dịch vụ:

- `State`: `STOPPED` hoặc `RUNNING`.
- `Version`: số lần trạng thái thực sự thay đổi.
- `start()` và `stop()`: operations làm thay đổi trạng thái.

Một dashboard có thể liên tục gọi `getState()`; đây là **polling**. Tuy nhiên, polling mỗi vài giây vừa tốn tài nguyên vừa không thấy được những chuyển trạng thái ngắn giữa hai lần đọc. **JMX Notification** cho phép nguồn phát chủ động thông báo tới các bên đã đăng ký nghe khi sự kiện xảy ra.

~~~text
                     JMX MBeanServer
  +--------------------------------------------------+
  | ObjectName = example.monitor:type=Service        |
  |                                                  |
  | MXBean:                                          |
  |  getState()  getVersion()  start()  stop()         |
  |  Service extends NotificationBroadcasterSupport  |
  |           |                                      |
  |           | State changed: STOPPED -> RUNNING    |
  |           v                                      |
  |    AttributeChangeNotification                  |
  |           |                                      |
  |           +--> NotificationFilter                |
  |                       |                          |
  |                       +--> NotificationListener  |
  |                                |                 |
  |                                v                 |
  |                    dashboard / metrics / audit   |
  +--------------------------------------------------+
~~~

**Điều quan trọng:** một interface đặt tên `ServiceMXBean` và một setter làm thay đổi giá trị **không tự khiến JMX phát notification**. Đối với MXBean tự xây dựng, **chính implementation** phải tạo `Notification` và gọi `sendNotification(...)`, hoặc dùng một emitter đã cung cấp sẵn hành vi đó.

### Khi nào dùng notification?

- Quan sát trạng thái khởi động/dừng của service, feature hoặc worker.
- Cảnh báo cấu hình, capacity, threshold hoặc độ sẵn sàng thay đổi.
- Theo dõi một sự kiện hiếm, khó nhận ra nếu chỉ polling.
- Kết hợp JMX dashboard với monitoring nội bộ để chuyển trạng thái gần thời gian thực.
- Kết hợp `MemoryMXBean` phát thông báo khi JVM vượt ngưỡng sử dụng bộ nhớ được hỗ trợ/cấu hình.

**Không dùng notification làm nguồn dữ liệu duy nhất cho trạng thái quan trọng.** JMX Notification là cơ chế quan sát và chuyển phát sự kiện, **không phải durable message queue** với persistence, acknowledgement, replay và exactly-once delivery. Muốn biết trạng thái hiện tại một cách có thẩm quyền, vẫn phải đọc thuộc tính hiện hành từ MXBean.

## 2. API vẫn còn áp dụng trên Java hiện đại

Các API chính nằm trong module **`java.management`**, package **`javax.management`** và `java.lang.management`. Chúng còn được hỗ trợ trong Java 17 và Java SE 25.

| API | Vai trò |
| --- | --- |
| `@MXBean` hoặc interface tên kết thúc bằng `MXBean` | Định nghĩa management contract với Open Type mapping |
| `MBeanServer` | Đăng ký MXBean theo `ObjectName`; đọc attributes/gọi operations/thêm listener |
| `ManagementFactory.getPlatformMBeanServer()` | Lấy local platform MBeanServer của JVM |
| `Notification` | Dữ liệu sự kiện: type, source, sequence, timestamp, message, userData |
| `AttributeChangeNotification` | Notification chuyên dụng khi attribute đổi giá trị |
| `NotificationListener` | Callback `handleNotification(Notification,Object handback)` |
| `NotificationFilter` | Predicate xác định event được chuyển đến listener |
| `NotificationBroadcaster` | Cho phép đăng ký listener và công bố metadata |
| `NotificationEmitter` | Bổ sung khả năng gỡ listener theo bộ ba listener/filter/handback |
| `NotificationBroadcasterSupport` | Implementation hỗ trợ đăng ký/gỡ listener và `sendNotification` |
| `MBeanNotificationInfo` | Metadata công bố các notification types mà MBean có thể phát |
| `JMX.newMXBeanProxy(...)` | Tạo typed proxy gọi attributes/operations qua MBeanServerConnection |
| `MBeanServerDelegate` | JMX MBean đặc biệt phát notification khi MBean được đăng ký/gỡ |
| `MemoryMXBean` | MXBean nền tảng có thể phát memory threshold notifications |
| `MemoryNotificationInfo` | Chuyển dữ liệu `CompositeData` trong memory notification thành thông tin có kiểu |

**Không nhầm `NotificationListener` của JMX** với `java.beans.PropertyChangeListener`, `java.util.concurrent.Flow.Subscriber`, event listeners của GUI, hoặc distributed messaging qua Kafka. Mỗi cơ chế có contract khác nhau, đặc biệt về scheduling, buffering, ordering và độ tin cậy.

### MXBean khác Standard MBean ở đâu?

Một interface có tên kết thúc bằng `MXBean` được JMX nhận dạng là MXBean theo conventions, ví dụ:

~~~java
public interface ServiceMXBean {
    String getState();
    long getVersion();
    void start();
    void stop();
}
~~~

Đây chỉ là một **interface**, không phải một class chạy độc lập. Các getter được ánh xạ thành attributes `State` và `Version`; `start`/`stop` là operations. MXBean dùng **Open Types** để biểu diễn dữ liệu management tương thích qua kết nối, trong khi notifications vẫn được vận chuyển qua cơ chế JMX `NotificationEmitter`.

Có thể dùng annotation `@MXBean` khi không dùng naming convention, nhưng hãy nhất quán để JMX introspector nhận đúng interface. Không tự cho rằng mọi class có tên `SomethingMXBean` đều là một broadcaster: **phải triển khai notification mechanism**.

## 3. Hợp đồng của một JMX Notification

Một notification thông thường chứa các trường:

| Trường | API | Giải thích |
| --- | --- | --- |
| Type | `getType()` | Chuỗi phân loại, ví dụ `jmx.attribute.change` |
| Source | `getSource()` | Nguồn phát, thường dùng `ObjectName` ổn định |
| Sequence number | `getSequenceNumber()` | Số thứ tự do emitter cấp |
| Timestamp | `getTimeStamp()` | Thời điểm tạo notification, thường epoch milliseconds |
| Message | `getMessage()` | Nội dung ngắn, dễ đọc, không chứa bí mật |
| User data | `getUserData()` | Payload tùy biến; phải xem xét serialization/compatibility |

`Notification.getType()` **không phải** Java class name. Một object `AttributeChangeNotification` thường có type **`AttributeChangeNotification.ATTRIBUTE_CHANGE`**, với giá trị `jmx.attribute.change`. Listener nên dựa vào type contract, và khi cần đọc old/new values thì kiểm subclass phù hợp.

`AttributeChangeNotification` cung cấp thêm:

- `getAttributeName()`: tên thuộc tính thay đổi, ví dụ `State`.
- `getAttributeType()`: tên kiểu thuộc tính, ví dụ `java.lang.String`.
- `getOldValue()` và `getNewValue()`: hai giá trị tại thời điểm tạo event.

**Timestamp và sequence là metadata, không tự là đồng hồ/trật tự toàn cục.** Sequence number do từng emitter quyết định; nó không được JMX tự phát sinh cho mỗi MXBean và không bảo đảm duy nhất giữa nhiều instances hoặc sau restart. Nếu phần mềm cần phát hiện event bị bỏ lỡ, nên phát **version đơn điệu theo nguồn** và có phương pháp đọc lại trạng thái hiện tại.

### Ví dụ tạo một AttributeChangeNotification

~~~java
AttributeChangeNotification event = new AttributeChangeNotification(
        objectName,
        42L,
        System.currentTimeMillis(),
        "State changed",
        "State",
        "java.lang.String",
        "STOPPED",
        "RUNNING");
event.setUserData(Long.valueOf(42L));
sendNotification(event);
~~~

Đây là **snippet trong một class extends NotificationBroadcasterSupport**, có biến `objectName` hợp lệ và đã cập nhật trạng thái. Số 42 chỉ là minh họa. Trong chương trình chạy độc lập bên dưới, số thứ tự tăng theo `Version`.

**Phát event sau khi state đã thực sự commit**. Nếu emit trước rồi update thất bại, người quan sát nhận một sự kiện không phản ánh trạng thái. Nếu một operation bị từ chối hoặc giá trị mới bằng giá trị cũ, quyết định có phát “attempted change” hay không phải là một event contract riêng — **không giả gọi AttributeChangeNotification là có thay đổi thật**.

## 4. NotificationBroadcasterSupport và getNotificationInfo

Cách phổ biến để tự phát notifications:

~~~java
public final class Service extends NotificationBroadcasterSupport
        implements ServiceMXBean {
    // Đọc/ghi state và gọi sendNotification khi state thay đổi.
}
~~~

Đây là **khung minh họa**, thiếu định nghĩa interface/constructor/methods nên không chạy độc lập. `NotificationBroadcasterSupport` đã triển khai `NotificationEmitter`, quản lý registrations và cung cấp `sendNotification`.

Khai báo trước notification types hỗ trợ:

~~~java
super(new MBeanNotificationInfo(
        new String[]{AttributeChangeNotification.ATTRIBUTE_CHANGE},
        AttributeChangeNotification.class.getName(),
        "Notifies when State changes"));
~~~

Đây là lời gọi **ở constructor của subclass**. Nó tạo metadata để `getNotificationInfo()` và `MBeanServer.getMBeanInfo(ObjectName).getNotifications()` công bố loại thông báo mong đợi. Nếu MBean phát nhiều loại sự kiện, cung cấp metadata cho từng nhóm type/class phù hợp.

**Metadata không tự phát sự kiện.** Ngược lại, nếu implementation có phát notifications nhưng metadata không mô tả chúng, công cụ khám phá JMX dễ không biết MXBean có khả năng gì. Hãy giữ `MBeanNotificationInfo[]` đồng bộ với event contract thực sự.

JMX client có thể kiểm:

~~~java
MBeanNotificationInfo[] info =
        server.getMBeanInfo(objectName).getNotifications();
~~~

Đây là đoạn code ở nơi đã có `server`, `objectName`, không phải file độc lập. Nó cho biết **các loại sự kiện được công bố**, không cho biết listener đã đăng ký hay notification đã từng phát.

## 5. Đăng ký listener, filter và handback

Người quan sát không bắt buộc có reference trực tiếp tới Java object. Có thể đăng ký qua JMX server:

~~~java
NotificationFilter filter =
        n -> AttributeChangeNotification.ATTRIBUTE_CHANGE
                     .equals(n.getType());

NotificationListener listener = (notification, handback) -> {
    if (notification instanceof AttributeChangeNotification change) {
        // Xử lý change.getAttributeName(),
        // change.getOldValue(), change.getNewValue().
    }
};

Object handback = "my-observer";
server.addNotificationListener(objectName, listener, filter, handback);
~~~

Đây là snippet trong method với server/objectName hợp lệ, không phải toàn chương trình. `NotificationListener` là functional interface. `NotificationFilter` cho phép giữ lại event đúng type; demo hoàn chỉnh còn kiểm `attributeName="State"`.

**Handback** là dữ liệu do bên đăng ký cung cấp, JMX sẽ trả lại callback khi event được chuyển đến. Nó có thể giúp listener nhận ra subscription hoặc correlation context; **không phải bằng chứng xác thực người phát và không nên là nơi chứa secret**. Với kết nối remote, cân nhắc payload nhỏ, serializable và tương thích.

Khi ứng dụng đóng observer:

~~~java
server.removeNotificationListener(
        objectName, listener, filter, handback);
~~~

**Dùng đúng các object references filter/handback đã đăng ký** khi gỡ theo bộ ba. Overload chỉ nhận `listener` thường gỡ mọi registrations của listener ấy trên broadcaster, dễ rộng hơn ý định. Việc gỡ listener không biến mất một callback đang chạy; với dispatch bất đồng bộ cần chính sách shutdown và in-flight handling.

### NotificationFilterSupport: một lưu ý nhỏ

`NotificationFilterSupport.enableType(typePrefix)` là tiện ích cho type strings, nhưng Javadoc mô tả cơ chế **prefix matching**, không phải chỉ so bằng tuyệt đối. Nếu ứng dụng chỉ muốn event chính xác `jmx.attribute.change` và không muốn `jmx.attribute.change.extra`, hãy dùng một `NotificationFilter` với `equals(...)` như trong ví dụ.

Không đưa logic phân quyền vào filter: client có thể thay filter, còn authorization phải được thực thi tại nguồn sự kiện/remote connector dựa vào policy riêng.

## 6. Chương trình Java 17+ hoàn chỉnh: một MXBean phát và nhận thay đổi State

File độc lập **`MxBeanNotificationDemo.java`** sử dụng **chỉ JDK chuẩn**, không Maven, không network port, không JMX remote connector. Nó đăng ký một MXBean vào **platform MBeanServer cục bộ**, gắn listener và filter, thao tác qua **`JMX.newMXBeanProxy`**, kiểm metadata, gỡ listener và dọn MXBean.

Thiết kế:

1. Interface `ServiceMXBean` định nghĩa `State`, `Version`, `start`, `stop`.
2. Class `Service` extends `NotificationBroadcasterSupport`, implements `ServiceMXBean`.
3. Trạng thái ban đầu `STOPPED`, `Version=0`.
4. `start()` đổi sang `RUNNING`: phát event 1 (old/new).
5. Gọi `start()` lần thứ hai khi đã `RUNNING`: **không** phát event.
6. `stop()` đổi về `STOPPED`: phát event 2.
7. Gỡ listener, gọi `start()` lần nữa: trạng thái vẫn đổi và `Version=3`, nhưng observer không nhận event 3.
8. Gỡ MXBean khỏi MBeanServer trong `finally`; tránh giữ name/listener sau test.
9. Source của event là `ObjectName("example.monitor:type=Service")`, phù hợp khai báo JMX.

**Mã đầy đủ:**

~~~java
import java.lang.management.ManagementFactory;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import javax.management.AttributeChangeNotification;
import javax.management.JMX;
import javax.management.MBeanNotificationInfo;
import javax.management.MBeanServer;
import javax.management.Notification;
import javax.management.NotificationBroadcasterSupport;
import javax.management.NotificationFilter;
import javax.management.NotificationListener;
import javax.management.ObjectName;

public final class MxBeanNotificationDemo {
    public interface ServiceMXBean {
        String getState();
        long getVersion();
        void start();
        void stop();
    }

    public static final class Service extends NotificationBroadcasterSupport
            implements ServiceMXBean {
        private final ObjectName objectName;
        private String state = "STOPPED";
        private long version;

        Service(ObjectName objectName) {
            super(new MBeanNotificationInfo(
                    new String[]{AttributeChangeNotification.ATTRIBUTE_CHANGE},
                    AttributeChangeNotification.class.getName(),
                    "Notifies when State changes"));
            this.objectName = objectName;
        }

        @Override public synchronized String getState() {
            return state;
        }

        @Override public synchronized long getVersion() {
            return version;
        }

        @Override public void start() {
            changeState("RUNNING");
        }

        @Override public void stop() {
            changeState("STOPPED");
        }

        private void changeState(String next) {
            AttributeChangeNotification notification;
            synchronized (this) {
                if (state.equals(next)) return;
                String previous = state;
                state = next;
                long sequence = ++version;
                notification = new AttributeChangeNotification(
                        objectName, sequence, System.currentTimeMillis(),
                        "State changed", "State", "java.lang.String",
                        previous, next);
                notification.setUserData(Long.valueOf(sequence));
            }
            // Outside lock: listener code must not block state mutation lock.
            sendNotification(notification);
        }
    }

    public static void main(String[] args) throws Exception {
        MBeanServer server = ManagementFactory.getPlatformMBeanServer();
        ObjectName name = new ObjectName("example.monitor:type=Service");
        Service service = new Service(name);
        List<String> events = new ArrayList<>();
        NotificationFilter filter = notification ->
                AttributeChangeNotification.ATTRIBUTE_CHANGE.equals(
                        notification.getType())
                && notification instanceof AttributeChangeNotification change
                && "State".equals(change.getAttributeName());
        NotificationListener listener = (notification, handback) -> {
            AttributeChangeNotification change =
                    (AttributeChangeNotification) notification;
            events.add(change.getSequenceNumber() + ":"
                    + change.getOldValue() + "->" + change.getNewValue()
                    + ";source=" + change.getSource()
                    + ";handback=" + handback
                    + ";data=" + change.getUserData());
        };
        String handback = "consumer-A";
        boolean listenerAdded = false;
        boolean beanAdded = false;
        try {
            server.registerMBean(service, name);
            beanAdded = true;
            server.addNotificationListener(name, listener, filter, handback);
            listenerAdded = true;
            ServiceMXBean proxy =
                    JMX.newMXBeanProxy(server, name, ServiceMXBean.class);

            MBeanNotificationInfo[] info =
                    server.getMBeanInfo(name).getNotifications();
            boolean advertised = Arrays.stream(info)
                    .flatMap(i -> Arrays.stream(i.getNotifTypes()))
                    .anyMatch(AttributeChangeNotification.ATTRIBUTE_CHANGE::equals);
            System.out.println("is MXBean interface: "
                    + JMX.isMXBeanInterface(ServiceMXBean.class));
            System.out.println("registered: " + server.isRegistered(name));
            System.out.println("advertises AttributeChangeNotification: "
                    + advertised);
            System.out.println("initial State: " + proxy.getState());
            proxy.start();
            proxy.start(); // Repeated state: no change event.
            proxy.stop();
            System.out.println("events from two real transitions: "
                    + events.size());
            System.out.println("event one: " + events.get(0));
            System.out.println("event two: " + events.get(1));
            System.out.println("current State: " + proxy.getState());
            System.out.println("current Version: " + proxy.getVersion());
            server.removeNotificationListener(name, listener, filter, handback);
            listenerAdded = false;
            proxy.start();
            System.out.println("events after listener removal: "
                    + events.size());
            System.out.println("State after third transition: "
                    + proxy.getState());
            System.out.println("Version after third transition: "
                    + proxy.getVersion());
        } finally {
            if (listenerAdded) {
                server.removeNotificationListener(
                        name, listener, filter, handback);
            }
            if (beanAdded) server.unregisterMBean(name);
        }
        System.out.println("unregistered: " + !server.isRegistered(name));
    }
}
~~~

Chạy trên Java 17 trở lên:

~~~bash
javac --release 17 MxBeanNotificationDemo.java
java MxBeanNotificationDemo
~~~

**Stdout chính xác** đã được biên dịch và chạy trên OpenJDK 24.0.2 với `--release 17`:

~~~text
is MXBean interface: true
registered: true
advertises AttributeChangeNotification: true
initial State: STOPPED
events from two real transitions: 2
event one: 1:STOPPED->RUNNING;source=example.monitor:type=Service;handback=consumer-A;data=1
event two: 2:RUNNING->STOPPED;source=example.monitor:type=Service;handback=consumer-A;data=2
current State: STOPPED
current Version: 2
events after listener removal: 2
State after third transition: RUNNING
Version after third transition: 3
unregistered: true
~~~

### Từng kết quả cho ta biết điều gì?

- `is MXBean interface: true`: naming convention `ServiceMXBean` được `JMX.isMXBeanInterface` xác nhận.
- `registered: true`: object đã được MBeanServer đăng ký với `ObjectName` cụ thể.
- `advertises AttributeChangeNotification: true`: `MBeanNotificationInfo` xuất hiện trong metadata quản trị.
- `initial State: STOPPED`: proxy đọc thuộc tính hiện hành qua JMX.
- `events from two real transitions: 2`: chỉ `STOPPED→RUNNING` và `RUNNING→STOPPED` tạo event; gọi `start()` khi đã RUNNING không tạo event ảo.
- Hai dòng `event one/two` cho thấy sequence, old/new values, source ObjectName, handback và userData version.
- `current State: STOPPED`, `current Version: 2`: trạng thái authoritative sau hai lần chuyển đổi.
- `events after listener removal: 2`: listener không nhận event khi đã gỡ; điều này **không** có nghĩa emitter ngừng thay đổi.
- `State after third transition: RUNNING` và `Version after third transition: 3`: một sự kiện khác đã phát mà listener không còn quan sát.
- `unregistered: true`: dọn MBean có ObjectName demo khỏi local MBeanServer.

**Phạm vi chứng minh:** demo đồng bộ, chạy trong một thread và local JMX server. Khi ứng dụng thật dùng executor bất đồng bộ, nhiều threads hoặc JMX remote, callbacks có thể chạy ở thread khác, cần cấu trúc dữ liệu thread-safe, xử lý reordering/delivery gaps và shutdown.

### Tại sao tạo notification bên trong synchronized nhưng gửi bên ngoài?

Trong `changeState`, đoạn cập nhật `state`, `version` và tạo event được đồng bộ hóa để old/new/version nhất quán. Sau khi rời lock mới gọi `sendNotification(notification)`. Với dispatch **đồng bộ mặc định**, gọi listener dưới lock có thể khiến listener blocking, gọi lại MXBean hoặc lấy lock khác dẫn đến delay/deadlock.

Nhưng quyết định này có trade-off: **khi nhiều threads cùng gọi `start/stop`**, event của phiên bản 2 có thể được gửi trước phiên bản 1 vì hai threads rời lock ở thời điểm khác nhau. Vì vậy `Version` tăng đúng theo state transitions **không tự bảo đảm thứ tự giao event** trên nhiều threads. Nếu ordering là yêu cầu bắt buộc, cần **single-thread sequencer/outbox** hoặc serial executor với logic enqueue ngay trong critical section, backpressure và failure handling rõ ràng.

## 7. Phân biệt State, Version và Notification sequence

Ba loại dữ liệu không nên bị nhầm:

| Loại | Mục đích | Cách dùng |
| --- | --- | --- |
| Current state | Sự thật hiện tại được MXBean lưu | `getState()` hoặc snapshot authoritative |
| State version | Số lần chuyển trạng thái được commit | `getVersion()`, phát hiện state đã đổi |
| Notification sequence | Số thứ tự của event từ emitter | Dedupe/đánh giá gap trong phạm vi emitter |

Trong demo, `Version` được dùng luôn làm sequence number. Đây là quyết định thiết kế, không phải điều mà JMX bắt buộc. Một emitter có thể phát nhiều loại notification cho cùng một cập nhật hoặc chỉ phát một subset, khi đó sequence và attribute version sẽ không đồng nhất.

### Tại sao polling vẫn cần?

Sự kiện có thể đến sau, listener có thể mới được gắn, kết nối JMX có thể đứt, và event **không được lưu mãi cho người đăng ký muộn**. Khởi động dashboard an toàn:

~~~text
1. Kết nối tới MBeanServer/management endpoint đáng tin.
2. Đăng ký NotificationListener với filter rõ ràng.
3. Đọc State và Version hiện tại.
4. Trong quá trình chạy, dùng event để cập nhật gần thời gian thực.
5. Nếu reconnect, thấy sequence/version gap hoặc trạng thái không chắc chắn:
      đọc lại State/Version authoritative và resynchronize.
6. Khi dừng dashboard: removeNotificationListener và đóng connector.
~~~

**Đăng ký trước rồi đọc trạng thái** giảm cửa sổ bỏ lỡ event khi khởi tạo, nhưng sự kiện có thể đến **trong lúc snapshot đang được đọc**. Nếu hai getters State/Version không cung cấp snapshot atomic, hãy dùng version trước/sau, retry khi thấy thay đổi hoặc bổ sung một **management operation có snapshot nhất quán** với Open Types phù hợp. Một event consumer phải xử lý duplicates/reordering/races thay vì giả định đọc trạng thái và sự kiện luôn có total order toàn hệ thống.

### Xử lý gap

Giả sử đã thấy version 8 rồi nhận notification version 11. Có thể version 9/10 đã bị bỏ lỡ hoặc đến trễ — không thể biết nội dung chỉ bằng version 11. Đừng tự tổng hợp “đã đi qua tất cả các trạng thái”. Hãy đọc `getState/getVersion` lại, ghi một metric gap và nếu yêu cầu audit chính xác, dùng một **event log durable riêng** do nghiệp vụ quản lý.

Sequence có thể được reset khi process restart hoặc MBean re-registration. Nên định danh emitter bằng ObjectName **và lifecycle instance ID** nếu cần so sánh qua restart, không chỉ dựa vào sequence. Đối với nguồn không có version contract, event chỉ là tín hiệu nên kiểm trạng thái, không có nghĩa là state log đầy đủ.

## 8. NotificationListener và điều kiện vận hành an toàn

`NotificationBroadcasterSupport` có **dispatch đồng bộ theo mặc định**: `sendNotification` thường gọi `handleNotification` của listeners trong thread phát sự kiện. API cũng có các constructors nhận `Executor` để xử lý notification delivery theo cách khác. Một dispatch mechanism bất đồng bộ không tự tạo hàng đợi vô hạn đáng tin, retry hoặc bảo đảm ordering.

**Không nên làm trong listener:**
- Gọi mạng chậm, query database blocking không timeout.
- Thực hiện I/O lớn hoặc nén hàng MB khi đang callback.
- Lock vào đối tượng đang được emitter dùng theo thứ tự lock nguy hiểm.
- Gửi raw credential, session ID, token hoặc PII qua `userData`/logs.
- Throw unchecked exception như cách ra lệnh broadcaster phải retry.
- Tin rằng callback sẽ gọi đúng một lần cho mỗi trạng thái ở hệ thống phân tán.

**Nên làm:**
- Filter hẹp theo type/attribute.
- Chỉ đọc những metadata cần thiết và sao chép giá trị đơn giản.
- Đẩy việc xử lý tốn thời gian vào **bounded queue hoặc executor có kiểm soát**.
- Có policy rõ khi queue đầy: drop có metric, hợp nhất trạng thái mới nhất, hoặc backpressure nếu contract hỗ trợ.
- Xử lý exceptions bên trong callback, ghi logs được redact.
- Gỡ listener và đóng JMX connector khi không sử dụng.
- Resynchronize bằng polling/snapshot khi phát hiện mất sự kiện.

Javadoc `NotificationBroadcasterSupport` nói exception từ filter/listener không ngăn các listeners khác được gọi, nhưng **không nên dựa vào việc này như cơ chế phục hồi lỗi**. Nếu người quan sát thực thi side effects quan trọng cần idempotency, retry, durable queue và auditing ở một thành phần khác.

### Thread-safety của collector

Trong demo, `ArrayList` đủ vì mọi lệnh thay state trên một thread và default broadcaster gọi listeners đồng bộ. Nếu thay bằng `NotificationBroadcasterSupport(Executor, info...)`, hoặc khi JMX remote chuyển phát ở thread khác, `ArrayList` có thể không còn an toàn. Dùng `ConcurrentLinkedQueue`, `CopyOnWriteArrayList`, synchronized collections hoặc một pipeline sự kiện chuyên dụng tùy profile tải.

**Không giữ reference tới listener vô thời hạn:** một MXBean sống lâu có thể giữ listener và mọi object mà callback capture, tạo memory leak sau khi module/class loader đã bỏ dùng. Điều này đặc biệt quan trọng với application servers, plugin systems và long-lived platform MBeanServer.

## 9. MBeanServer, ObjectName, registration và event nguồn

### ObjectName là định danh JMX, không phải Java class name

ObjectName ví dụ:

~~~text
example.monitor:type=Service
~~~

Mỗi `ObjectName` phải duy nhất tại thời điểm register trong một MBeanServer. Đặt domain/property có ý nghĩa, phù hợp quy tắc ObjectName và không chứa dữ liệu bí mật. Nếu nhiều tenants/processes, tên nên có các tags có thể quản lý cardinality, nhưng đừng để một user tự tạo vô hạn ObjectNames.

Đăng ký:

~~~java
MBeanServer server = ManagementFactory.getPlatformMBeanServer();
ObjectName name = new ObjectName("example.monitor:type=Service");
server.registerMBean(service, name);
~~~

Đây là snippet trong method, `service` là MBean instance hợp lệ và caller phải xử lý cleanup/errors. `registerMBean` chỉ đăng ký khả năng quản trị; **không tự bật JMX remote** trong ví dụ này. `ManagementFactory.getPlatformMBeanServer()` là local server của JVM hiện tại.

### Notification khi một MBean được đăng ký/gỡ

JMX còn có built-in **`MBeanServerDelegate`** được nhận diện bởi:

~~~text
JMImplementation:type=MBeanServerDelegate
~~~

Nếu muốn nghe **registration/unregistration**, đăng ký listener trên `MBeanServerDelegate`, và xử lý `MBeanServerNotification.REGISTRATION_NOTIFICATION` hoặc `UNREGISTRATION_NOTIFICATION`. Đây là **loại sự kiện khác** với `AttributeChangeNotification` của Service. Việc một MXBean được register không có nghĩa attribute `State` đã đổi.

Snippet mô tả cơ chế:

~~~java
ObjectName delegate = new ObjectName(
        "JMImplementation:type=MBeanServerDelegate");
NotificationFilter registrations = n ->
        MBeanServerNotification.REGISTRATION_NOTIFICATION.equals(n.getType())
        || MBeanServerNotification.UNREGISTRATION_NOTIFICATION.equals(n.getType());
NotificationListener observer = (notification, handback) -> {
    if (notification instanceof MBeanServerNotification event) {
        ObjectName changedBean = event.getMBeanName();
        // Kiểm domain/type và làm công việc rất nhẹ.
    }
};
server.addNotificationListener(delegate, observer, registrations, null);
// Trong finally: server.removeNotificationListener(
//        delegate, observer, registrations, null);
~~~

Đây là đoạn code trong method có imports `ObjectName`, `MBeanServerNotification`, `NotificationFilter`, `NotificationListener`; không phải file Java chạy độc lập. Gỡ listener trong finally để tránh giữ reference.

## 10. Platform MXBean: MemoryMXBean cũng phát Notification

Ngoài MXBean tự tạo, `ManagementFactory.getMemoryMXBean()` trả đối tượng thực thi `MemoryMXBean` và có thể dùng như một **`NotificationEmitter`**. Tài liệu Java SE 25 mô tả các loại memory threshold notifications:

- `MemoryNotificationInfo.MEMORY_THRESHOLD_EXCEEDED`: usage threshold bị vượt tại một `MemoryPoolMXBean` hỗ trợ cơ chế này.
- `MemoryNotificationInfo.MEMORY_COLLECTION_THRESHOLD_EXCEEDED`: collection usage threshold bị vượt sau hoạt động thu gom, nếu pool hỗ trợ.

**Không phải mọi lần cấp phát heap đều có notification.** Chỉ các threshold event khi pool có hỗ trợ/cấu hình điều kiện phù hợp; loại pool/provider/collector có thể khác nhau. Kiểm `MemoryPoolMXBean.isUsageThresholdSupported()` và `isCollectionUsageThresholdSupported()` trước khi định cấu hình threshold. Không lấy notification memory làm cơ chế duy nhất chống OutOfMemoryError hoặc cố ép GC để hy vọng nhận event.

**Payload của MemoryMXBean có cấu trúc:** `notification.getUserData()` là `CompositeData` có thể chuyển thành `MemoryNotificationInfo` qua `MemoryNotificationInfo.from(...)`, cho biết pool name, memory usage và crossing count. Không cast trực tiếp userData thành `MemoryNotificationInfo`.

### Mã Java 17+ số 2: quan sát MemoryMXBean không đổi threshold

File độc lập **`PlatformMemoryNotificationDemo.java`** có listener đúng type và giải mã `CompositeData`, nhưng **không** thay đổi thresholds, không cố cấp phát làm đầy heap và không kỳ vọng sẽ luôn nhận event trong vài milliseconds. Điều này giúp kết quả kiểm thử ổn định trên những JVM có memory pool layout khác nhau.

~~~java
import java.lang.management.ManagementFactory;
import java.lang.management.MemoryMXBean;
import java.lang.management.MemoryNotificationInfo;
import java.lang.management.MemoryPoolMXBean;
import java.util.concurrent.atomic.AtomicLong;
import javax.management.NotificationEmitter;
import javax.management.NotificationFilter;
import javax.management.NotificationListener;
import javax.management.openmbean.CompositeData;

public final class PlatformMemoryNotificationDemo {
    public static void main(String[] args) throws Exception {
        MemoryMXBean memory = ManagementFactory.getMemoryMXBean();
        NotificationEmitter emitter = (NotificationEmitter) memory;
        AtomicLong handled = new AtomicLong();
        NotificationFilter filter = notification ->
                MemoryNotificationInfo.MEMORY_THRESHOLD_EXCEEDED.equals(
                        notification.getType())
                || MemoryNotificationInfo.MEMORY_COLLECTION_THRESHOLD_EXCEEDED
                        .equals(notification.getType());
        NotificationListener listener = (notification, handback) -> {
            if (notification.getUserData() instanceof CompositeData data) {
                MemoryNotificationInfo details = MemoryNotificationInfo.from(data);
                if (details != null && details.getPoolName() != null) {
                    handled.incrementAndGet();
                }
            }
        };
        emitter.addNotificationListener(listener, filter, null);
        try {
            System.out.println("memory MXBean: " + memory.getObjectName());
            System.out.println("is emitter: "
                    + (memory instanceof NotificationEmitter));
            System.out.println("pool list available: "
                    + (ManagementFactory.getMemoryPoolMXBeans() != null));
            // No threshold is changed here; no event is guaranteed.
        } finally {
            emitter.removeNotificationListener(listener, filter, null);
        }
        System.out.println("listener removed: true");
    }
}
~~~

Chạy:

~~~bash
javac --release 17 PlatformMemoryNotificationDemo.java
java PlatformMemoryNotificationDemo
~~~

**Stdout chính xác** đã kiểm thử trên OpenJDK 24.0.2:

~~~text
memory MXBean: java.lang:type=Memory
is emitter: true
pool list available: true
listener removed: true
~~~

Tại runtime khác, số memory pools và mức hỗ trợ threshold có thể thay đổi. Code chỉ kiểm danh sách pools **có sẵn**, không giả định một pool cụ thể hoặc tên GC cố định. `AtomicLong handled` minh họa một counter thread-safe cho callback; nó không xuất ra dòng “event count=0” vì event ngưỡng có thể phát ở thời điểm không kiểm soát.

### Nếu muốn giám sát threshold trong production

Một hệ thống thực phải:
1. Duyệt `ManagementFactory.getMemoryPoolMXBeans()`.
2. Lọc pools có `isUsageThresholdSupported()` hoặc `isCollectionUsageThresholdSupported()` tương ứng.
3. Chọn threshold hợp lý theo heap size/usage và capacity policy; set ngưỡng sau khi có quyền và kiểm giá trị hợp lệ.
4. Đăng ký `NotificationEmitter` listener và filter theo `MemoryNotificationInfo` types.
5. Dùng `MemoryNotificationInfo.from((CompositeData)notification.getUserData())`.
6. Ghi metric/alert với throttling; kết hợp polling, allocation metrics và JVM monitoring.
7. Không gọi `System.gc()` như một “cách tạo event” trong production.

Memory notifications là tín hiệu threshold crossing theo JVM provider, **không phải durable event stream từng lần cấp phát**. Oracle MemoryMXBean docs còn nói cơ chế theo dõi này hữu ích cho load distribution và không nhằm khôi phục khỏi một tình trạng thiếu memory nghiêm trọng.

## 11. Open Types, userData và remote compatibility

MXBean attribute/operation types sử dụng JMX **Open Type mapping**; ví dụ `String` và `long` có thể được expose qua MXBean proxy rõ ràng. Nhưng **`Notification.userData`** là một field `Object` tùy biến của Notification, không tự được chuyển mọi kiểu Java thành Open Types giống hệt getter MXBean.

Khi notification có thể đi qua JMX remote connector, nên thiết kế payload:
- Nhỏ, ít trường, có version;
- Dùng những kiểu dễ serialize/nhận diện như `String`, `Long`, `CompositeData`;
- Không chứa class application đặc thù nếu remote client không có class;
- Không chứa secrets, raw config chứa passwords hoặc PII;
- Có documentation về nullability, units và các trường ổn định.

Chương trình số 1 dùng `Long` làm `userData` cho version. Đó là kiểu đơn giản, dễ dùng, nhưng **contract của userData do ứng dụng định nghĩa**. `AttributeChangeNotification.getOldValue()/getNewValue()` là Object và có những cân nhắc tương tự khi truyền qua remote connector. Không đẩy một large mutable object graph/byte array hàng MB vào event.

### Metadata cũng là API công khai

Nếu client dựa vào `getNotificationInfo` để đăng ký tự động, thay đổi type strings hoặc attribute names là thay đổi contract. Nên đặt stable event types, tài liệu versioning, backward compatibility và khả năng client bỏ qua event chưa hiểu. Nếu thay sơ đồ `userData`, cần phối hợp migration.

**Không gắn schema version bằng cách thêm dữ liệu bí mật** hoặc dùng class name có yếu tố nội bộ không ổn định làm `getType` nếu không có lý do tương thích.

## 12. Quan sát thay đổi bằng JMX local và remote

### Local JMX

`ManagementFactory.getPlatformMBeanServer()` trả server trong JVM. Đăng ký MXBean rồi dùng JMX API trực tiếp như chương trình số 1 giúp test nhanh, không mở TCP port và không yêu cầu cấu hình RMI. Một môi trường dev có thể dùng công cụ hỗ trợ JMX/JConsole để xem MBeans nếu JVM được cấu hình và cho phép attach; không nên dựa vào UI như một phần của test có tính quyết định.

### Remote JMX

Qua `MBeanServerConnection` hoặc JMX connector, một công cụ ngoài process có thể đọc attributes, gọi operations và đăng ký notifications nếu được cấp quyền. **Đây là bề mặt tấn công nhạy cảm**: một MXBean có operation `stop` có thể bị lạm dụng để tắt dịch vụ.

Đối với remote:
- Bắt buộc authentication mạnh, authorization phù hợp và transport encryption/TLS;
- Giới hạn firewall/bind address, không mở remote RMI/JMX công khai;
- Phân quyền **read-only monitoring** khác **mutating management operations**;
- Đảm bảo secrets/notification payload được redact;
- Xử lý reconnect, reconnect gaps, timeouts và connector lifecycle;
- Không sao chép hướng dẫn mở JMX **không xác thực** để “test nhanh” trên máy production.

Nếu tạo `JMX.newMXBeanProxy(connection,name,ServiceMXBean.class,true)`, overload bật hỗ trợ `NotificationEmitter` ở proxy khi nguồn thực sự hỗ trợ, khác với proxy mặc định. Chương trình chính cố ý dùng `MBeanServer.addNotificationListener` trực tiếp để người học nhìn rõ nguồn đăng ký và dễ dọn.

## 13. Quan sát thay đổi trạng thái so với monitoring bằng metrics

Dùng notification cho **tín hiệu**:

~~~text
State STARTING -> RUNNING
Version 18
Notification: type=jmx.attribute.change, attribute=State,
old=STARTING, new=RUNNING, source=...
~~~

Dùng polling/snapshot cho **current state**, và metrics cho **đo lường theo thời gian**:

| Nhu cầu | Cơ chế |
| --- | --- |
| Đọc state hiện tại | MXBean getter |
| Biết có một thay đổi vừa xảy ra | JMX Notification |
| Biết bao nhiêu transitions trong 5 phút | Metric counter/histogram |
| Theo dõi thời gian ở trạng thái unhealthy | Timers/gauges và tracing |
| Xác định mọi thay đổi để audit pháp lý | Durable audit log/event store |
| Khôi phục đúng state sau reconnect | Read current state + version/snapshot |
| Tái phát tất cả missed events | Durable broker/log, không phải JMX Notification thuần |

Không coi notification là hệ thống lưu trạng thái lâu dài. Những transitions quan trọng cho recovery cần được commit vào database/outbox/event journal cùng nghiệp vụ. Notification được phát sau đó để monitoring có latency thấp; nếu phát không thành công, nguồn dữ liệu authoritative vẫn đúng.

## 14. Security và concurrency: những giới hạn không thể bỏ qua

### Event có thể reorder

Ví dụ service có hai concurrent threads:
1. Thread A commit `STOPPED→RUNNING` version 5 và rời lock.
2. Thread B commit `RUNNING→STOPPED` version 6.
3. Thread B gọi `sendNotification(version=6)` trước A.
4. Thread A gọi `sendNotification(version=5)` sau.

Nếu dashboard áp event vào state theo **arrival order**, nó có thể hiển thị RUNNING dù current state là STOPPED. Đây là lý do dùng version và chọn xử lý event cũ/lại trễ, đồng thời có snapshot reconciliation.

Muốn bảo đảm ordering per emitter, có thể dùng một **serial event dispatcher**, bảo đảm enqueue theo commit order; nhớ giới hạn queue và có chiến lược xử lý overload. Một serial Executor được cấu hình không tự đủ nếu **việc submit** vào executor còn có thể reorder giữa nhiều threads.

### Thời điểm event và nghiệp vụ

- **Không phát trước commit:** có thể thông báo trạng thái chưa tồn tại.
- **Không gửi dưới lock quá rộng:** listener chậm hoặc gọi lại nguồn gây lock contention.
- **Không cho listener lỗi phá state mutation:** nguồn dữ liệu có thẩm quyền phải độc lập.
- **Không gửi toàn bộ cấu hình nhạy cảm:** chỉ cung cấp field names hoặc redacted values.
- **Không để event trở thành permission check:** consumer có thể bỏ lỡ event; server vẫn phải áp quyền hiện hành.

Với updates qua database, JMX MBean nên đọc state từ service/repository; notification phát **sau transaction commit** hoặc từ transactional outbox, tránh ghi trạng thái hai nơi không đồng bộ.

### Sequence, timestamp, runtime lifecycle

- Sequence number phải tăng trong một emitter nếu contract yêu cầu, thường dùng `AtomicLong` hoặc increment trong synchronized block.
- Event timestamp từ `System.currentTimeMillis()` phụ thuộc wall clock và có thể nhảy; không dùng nó cho duration chính xác hoặc total ordering trên nhiều máy.
- Một ObjectName có thể được đăng ký lại sau restart. Không giả version 1 của instance mới nối tiếp version 99 của instance cũ.
- Listener mới không nhận lịch sử notifications trước khi đăng ký.
- Khi unregistration/deregistration, dọn listener và reconnect; nếu cần phát hiện MBean xuất hiện trở lại, dùng `MBeanServerDelegate` notifications và query names.

## 15. Lỗi phổ biến, triệu chứng và cách sửa

| Lỗi | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Chỉ triển khai `ServiceMXBean` mà không dùng broadcaster | Không có notification | Implement `NotificationEmitter`/`NotificationBroadcasterSupport` |
| Setter đổi field nhưng không gọi `sendNotification` | Listener không nhận | Phát sau state change thành công |
| Phát cả khi newValue == oldValue | Event spam/metrics sai | Xác định rõ “thay đổi thực” |
| Không khai báo `MBeanNotificationInfo` | JMX client khó khám phá event types | Công bố metadata đúng |
| Dùng Java class name làm `type` tùy tiện | Client không nhận ra event | Dùng contract type ổn định |
| Không xét `getAttributeName` | Listener xử lý nhầm thuộc tính | Filter đúng type và attribute |
| Nhầm `NotificationFilterSupport` là exact-match | Nhận cả type prefix mở rộng | Dùng predicate `equals` khi cần |
| Dùng `Notification` thường nhưng cast thẳng `AttributeChangeNotification` | `ClassCastException` | Kiểm type và `instanceof` |
| Không gỡ listener | Memory leak/duplicate callbacks | remove trong finally |
| Gỡ listener với filter/handback khác | ListenerNotFoundException hoặc không gỡ | Giữ object references đăng ký |
| Dùng `ArrayList` khi dispatch async | Data race/corruption | Thread-safe queue/collection |
| Callback gửi request mạng chậm | Block thread thay đổi state | Async bounded queue + timeouts |
| Gửi notification trước commit | Observer thấy trạng thái chưa tồn tại | Commit trước, emit sau |
| Gửi ngoài lock rồi coi arrival order là commit order | State có thể hiển thị ngược | Version/snapshot/serial dispatch |
| Chỉ dựa notification để xác định current state | Mất đồng bộ khi thiếu events | Poll/resync version |
| Xem sequence là global unique | Trùng qua restart/emitters | Thêm source/lifecycle identity |
| Chỉ dùng `System.currentTimeMillis` để sort | Clock drift/ties | Per-source sequence, version/monotonic clock |
| UserData là object nội bộ khó serialize | Remote client không decode được | Simple types/CompositeData/schema |
| UserData chứa secret/PII | Rò rỉ qua monitoring | Redact + least privilege |
| Xem `MemoryMXBean` phát mọi lần heap tăng | Lỗi logic, nhiều misses | Chỉ threshold crossing có điều kiện |
| Cố gọi System.gc để tạo notification | Hiệu năng xấu, behavior không bảo đảm | Config threshold và monitoring đúng |
| Remote JMX không có auth/TLS | Lộ operations/metrics, có thể control JVM | Authenticated encrypted management network |
| Nhầm MBeanServerDelegate event là State change | Cập nhật dashboard sai | Tách registration/unregistration và AttributeChange |
| Quên unregisterMBean trong demo | Name collision khi chạy lại | finally + unregister |
| Coi notification như Kafka/exactly-once | Mất dữ liệu audit | Durable broker/event store riêng |

## 16. Checklist kiểm thử một MXBean có notifications

| Case | Kỳ vọng |
| --- | --- |
| Interface name kết thúc MXBean hoặc dùng @MXBean | JMX nhận đúng MXBean |
| Register với ObjectName duy nhất | Server.isRegistered == true |
| MBeanInfo.getNotifications | Type jmx.attribute.change được công bố |
| Lúc mới tạo, getState | State xác định và version 0 |
| Register listener/filter/handback | Không ném exception |
| Operation tạo change STOPPED→RUNNING | Một AttributeChangeNotification |
| Repeat operation khi RUNNING | Không tạo change notification mới |
| Operation đổi RUNNING→STOPPED | Một notification thứ hai |
| Event type | Bằng AttributeChangeNotification.ATTRIBUTE_CHANGE |
| Event attribute name/type | State/java.lang.String |
| Old/new values | Khớp đúng before/after |
| Event source | Đúng ObjectName/emitter |
| Event sequence | Tăng theo design |
| UserData version | Giải mã/cast đúng Long |
| Listener handback | Đúng object do subscriber cung cấp |
| Filter không match | Không deliver event |
| Remove exact listener/filter/handback | Không nhận thêm notification |
| Remove listener khi không tồn tại | Xử lý ListenerNotFoundException có chủ đích |
| Bean vẫn đổi state khi không listener | State/version vẫn cập nhật |
| Unregister MBean | MBeanServer.isRegistered == false |
| Multiple emitters cùng type | Phân biệt qua ObjectName |
| Concurrent state updates | Consistent old/new/version; xử lý reorder |
| Slow listener | Không làm block critical state operations |
| Async executor shutdown | Không leak threads hoặc mất events không báo |
| Remote JMX disconnected | Reconnect và resync snapshot |
| Source restarted | Không trộn sequence của instance mới |
| MemoryMXBean threshold support | Kiểm support flags trước khi set |
| Memory notification userData | CompositeData → MemoryNotificationInfo |
| MXBean notification chứa PII | Không lộ qua logs/remote connector |
| Remote permissions | Monitor không có quyền gọi mutating operations |

**Test chỉ kiểm callback count chưa đủ:** phải kiểm **type, attribute, source, old/new values, sequence và handback**. Nếu dùng JMX remote, bổ sung test ACL/TLS/connection loss/reconnect, và hiệu năng khi hàng trăm events/second.

## 17. Tự kiểm tra kiến thức

1. **Notification trong JMX là gì?** Sự kiện do MBean/MXBean phát cho listeners đã đăng ký.
2. **MXBean có tự phát notification khi getter đổi không?** Không.
3. **Dùng class nào để dễ phát notification?** `NotificationBroadcasterSupport`.
4. **Emitter có interface nào?** `NotificationEmitter`, mở rộng `NotificationBroadcaster`.
5. **Tại sao cần `getNotificationInfo`?** Công bố metadata sự kiện cho clients.
6. **Đăng ký listener từ ngoài MBean instance?** `MBeanServer.addNotificationListener`.
7. **Gỡ đúng đăng ký?** `removeNotificationListener(name,listener,filter,handback)`.
8. **Filter dùng để làm gì?** Chỉ nhận notification types/attributes cần quan sát.
9. **Handback là gì?** Context do subscriber đặt, được trả cho callback.
10. **Notification.getType khác getSource thế nào?** Type là loại event; source là nguồn phát.
11. **AttributeChangeNotification chứa gì ngoài Notification?** AttributeName/Type và Old/NewValue.
12. **Tên type attribute change hiện hành?** `jmx.attribute.change`.
13. **Số thứ tự do ai cấp?** Emitter/application contract, không phải JMX tự đảm bảo.
14. **Timestamp có tạo total order phân tán không?** Không.
15. **Phát event trước hay sau commit state?** Sau commit.
16. **Nhận trễ hoặc thiếu event thì làm gì?** Poll/resync current state + version.
17. **Có guarantee replay cho listener mới không?** Không.
18. **NotificationBroadcasterSupport dispatch mặc định thế nào?** Đồng bộ.
19. **Một listener chậm có ảnh hưởng nguồn không?** Có thể, nếu dispatch sync.
20. **Khi đổi sang async executor có thể dùng ArrayList không?** Cần thread-safe coordination.
21. **Có thể reorder khi hai threads send ngoài lock không?** Có.
22. **Server đăng ký MBean có phát AttributeChangeNotification không?** Không tự động; delegate phát event registration riêng.
23. **ObjectName của MBeanServerDelegate là gì?** `JMImplementation:type=MBeanServerDelegate`.
24. **MemoryMXBean phát notification khi nào?** Khi các memory thresholds được hỗ trợ và điều kiện vượt ngưỡng xảy ra.
25. **Memory notification userData có kiểu gì?** `CompositeData`, chuyển bằng `MemoryNotificationInfo.from`.
26. **Có nên ép JVM full heap để lấy event?** Không.
27. **MXBean interface dùng Open Types ở đâu?** Attributes/operations qua JMX.
28. **Notification userData tùy biến có tự Open-Type map mọi object không?** Không.
29. **Sequence number có thể reset qua restart không?** Có.
30. **Notification có thay durable audit log không?** Không.
31. **Remote JMX cần gì?** Authentication, authorization, TLS, network isolation.
32. **Chứng minh current state từ đâu?** Getter/snapshot authoritative, không phải event history giả định.
33. **Sao cần finally khi add listener?** Tránh leaks và callback không mong muốn sau shutdown.
34. **Hai listeners có dùng cùng callback được không?** Có thể đăng ký nhiều lần; cần quản lý removal.
35. **Có nên log toàn bộ userData không?** Không nếu chứa dữ liệu nhạy cảm.
36. **Vì sao notification tốt hơn polling trong vài tình huống?** Độ trễ quan sát thấp và ít request liên tục.
37. **Vì sao polling vẫn quan trọng?** Khởi tạo, reconnect, recovery và kiểm trạng thái cuối.
38. **MXBean proxy có giúp nhận event tự động không?** Proxy mặc định để gọi attributes/operations; subscription cần cơ chế emitter/server và cấu hình thích hợp.
39. **Một consumer cần biết schema type nào?** Type, source, attribute, old/new, version, userData.
40. **MBeanServerNotification dùng làm gì?** Phát hiện MBeans được register/unregister, không phải value change.

## 18. Tài liệu chính thức còn áp dụng

- [Java SE 25 — javax.management.Notification](https://docs.oracle.com/en/java/javase/25/docs/api/java.management/javax/management/Notification.html): type/source/sequence/timestamp/message/userData.
- [Java SE 25 — AttributeChangeNotification](https://docs.oracle.com/en/java/javase/25/docs/api/java.management/javax/management/AttributeChangeNotification.html): old/new values và `ATTRIBUTE_CHANGE`.
- [Java SE 25 — NotificationBroadcasterSupport](https://docs.oracle.com/en/java/javase/25/docs/api/java.management/javax/management/NotificationBroadcasterSupport.html): `sendNotification`, metadata, default synchronous dispatch, Executor.
- [Java SE 25 — NotificationListener](https://docs.oracle.com/en/java/javase/25/docs/api/java.management/javax/management/NotificationListener.html): callback và handback.
- [Java SE 25 — NotificationEmitter](https://docs.oracle.com/en/java/javase/25/docs/api/java.management/javax/management/NotificationEmitter.html): register/remove overloads.
- [Java SE 25 — NotificationFilter](https://docs.oracle.com/en/java/javase/25/docs/api/java.management/javax/management/NotificationFilter.html): filter contract.
- [Java SE 25 — NotificationFilterSupport](https://docs.oracle.com/en/java/javase/25/docs/api/java.management/javax/management/NotificationFilterSupport.html): prefix-based type filter.
- [Java SE 25 — MBeanNotificationInfo](https://docs.oracle.com/en/java/javase/25/docs/api/java.management/javax/management/MBeanNotificationInfo.html): metadata phát notifications.
- [Java SE 25 — MBeanServer](https://docs.oracle.com/en/java/javase/25/docs/api/java.management/javax/management/MBeanServer.html): register/unregister/listener/metadata/query operations.
- [Java SE 25 — JMX](https://docs.oracle.com/en/java/javase/25/docs/api/java.management/javax/management/JMX.html): MXBean proxy và `isMXBeanInterface`.
- [Java SE 25 — MBeanServerNotification](https://docs.oracle.com/en/java/javase/25/docs/api/java.management/javax/management/MBeanServerNotification.html): registration/unregistration notification.
- [Java SE 25 — MemoryMXBean](https://docs.oracle.com/en/java/javase/25/docs/api/java.management/java/lang/management/MemoryMXBean.html): platform MXBean có notification threshold.
- [Java SE 25 — MemoryNotificationInfo](https://docs.oracle.com/en/java/javase/25/docs/api/java.management/java/lang/management/MemoryNotificationInfo.html): `CompositeData` payload và threshold types.
- [Java SE 25 — MemoryPoolMXBean](https://docs.oracle.com/en/java/javase/25/docs/api/java.management/java/lang/management/MemoryPoolMXBean.html): kiểm khả năng threshold monitoring.
- [Oracle Java SE 25 — JMX Guide](https://docs.oracle.com/en/java/javase/25/jmx/java-management-extensions-guide.pdf): triển khai notifications, broadcaster, listeners, JMX monitoring.
- [Oracle Java SE 25 — Management and Monitoring](https://docs.oracle.com/en/java/javase/25/management/): hướng dẫn quản lý/monitoring JVM hiện đại.

**Kết luận:** MXBean exposes current state và operations; `NotificationBroadcasterSupport` + `AttributeChangeNotification` cho phép phát tín hiệu khi state thực sự thay đổi. Listener đăng ký qua `MBeanServer` với filter và handback; metadata trong `MBeanNotificationInfo` giúp JMX tools khám phá event type. Sequence/version cần được thiết kế rõ, phát sau commit và tránh callback blocking. **Notification không thay current-state snapshot, không bảo đảm replay/đúng một lần**, nên luôn có polling/resync khi khởi tạo hoặc reconnect. Với platform MXBeans như `MemoryMXBean`, chỉ nghe các threshold notifications phù hợp support và giải mã `CompositeData` đúng API — tất cả là kiến thức vẫn áp dụng cho Java 17+ hiện nay.