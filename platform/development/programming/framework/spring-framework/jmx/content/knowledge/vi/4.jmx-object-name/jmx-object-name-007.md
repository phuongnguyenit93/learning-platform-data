# ObjectName trong truy vấn, listener và proxy

> **Chủ đề:** Spring Framework JMX  
> **Nhóm kiến thức:** ObjectName  
> **Bài học:** ObjectName trong truy vấn, listener và proxy

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

- Giải thích \`ObjectName\` là định danh MBean trong \`MBeanServer\`, đồng thời phân biệt **tên chính xác** và **name pattern**.
- Dùng \`MBeanServerConnection.queryNames()\` để tìm MBean theo \`ObjectName\` pattern, kết hợp \`QueryExp\` khi cần lọc thêm.
- Gắn và tháo \`NotificationListener\` với một MBean qua \`ObjectName\`, hiểu việc đăng ký listener thuộc về MBean/connection và vòng đời tài nguyên.
- Tạo client proxy qua JMX API hoặc \`MBeanProxyFactoryBean\` của Spring, nắm cách proxy chuyển method call thành thao tác JMX.
- Đánh giá hệ quả của tên động, nhiều instance, remote connection, missing MBean, quyền truy cập và thay đổi đăng ký MBean.

## 2. Mô hình nền tảng: ba cách dùng một ObjectName

Trong JMX, \`ObjectName\` định danh MBean đã đăng ký trong một \`MBeanServer\`. Cấu trúc cơ bản:

\`\`\`text
domain:key1=value1,key2=value2,...
\`\`\`

Ví dụ:

\`\`\`text
learning.jmx:type=WorkerPool,name=main
learning.jmx:type=WorkerPool,name=background
learning.jmx:type=Cache,name=users
\`\`\`

Trong ba trường hợp phổ biến, vai trò của \`ObjectName\` hơi khác nhau:

\`\`\`text
             MBeanServer / MBeanServerConnection
                          |
       +------------------+-------------------+
       |                  |                   |
       v                  v                   v
   queryNames()    addNotificationListener()  JMX proxy
   + name pattern      + exact ObjectName    + exact ObjectName
       |                  |                   |
       v                  v                   v
  Tìm nhiều MBean   Theo dõi một MBean     Gọi MBean như
  đang đăng ký      và nhận notification   một Java interface
\`\`\`

- **Truy vấn:** một \`ObjectName\` có thể là **pattern** để lấy danh sách nhiều tên thực tế.
- **Listener:** khi đăng ký listener, \`ObjectName\` thông thường là **tên chính xác** của một MBean phát notification.
- **Proxy:** một proxy thường nhắm đến **một ObjectName chính xác**, đại diện cho một MBean cụ thể. Proxy không tự làm công việc truy vấn tất cả MBean phù hợp với pattern.

Điểm quan trọng là \`ObjectName\` không chứa tham chiếu trực tiếp đến Spring bean. Nó là tên JMX mà MBeanServer dùng để định tuyến yêu cầu đến tài nguyên được đăng ký.

## 3. ObjectName chính xác và pattern

### 3.1. Tên chính xác

\`\`\`java
ObjectName mainPool = new ObjectName(
    "learning.jmx:type=WorkerPool,name=main"
);
\`\`\`

Dùng tên này khi muốn:

- Đọc attribute: \`connection.getAttribute(mainPool, "ActiveCount")\`.
- Gọi operation: \`connection.invoke(mainPool, "reset", new Object[0], new String[0])\`.
- Gắn listener: \`connection.addNotificationListener(mainPool, listener, filter, handback)\`.
- Tạo proxy: \`newProxyInstance(connection, mainPool, WorkerPoolMBean.class, true)\`.

Tên chính xác không có wildcard và phải khớp MBean đã đăng ký trong đúng MBeanServer.

### 3.2. Pattern trong domain

\`\`\`java
ObjectName pattern = new ObjectName(
    "learning.*:type=WorkerPool,name=*"
);
\`\`\`

Dấu \`*\` trong domain có thể khớp nhiều phần ký tự, và \`*\` trong value \`name=*\` khớp nhiều giá trị property.

### 3.3. Pattern theo property list

\`\`\`java
ObjectName pattern = new ObjectName(
    "learning.jmx:type=WorkerPool,*"
);
\`\`\`

Dấu \`,*\` cuối cho phép MBean có thêm key properties khác, ví dụ \`name\`, \`node\`, \`region\`. Đây là mẫu phổ biến khi chỉ quan tâm loại tài nguyên.

So sánh:

\`\`\`text
learning.jmx:type=WorkerPool
\`\`\`

là một tên chính xác có đúng property \`type\`, còn:

\`\`\`text
learning.jmx:type=WorkerPool,*
\`\`\`

là pattern cho phép có thêm properties. Một MBean tên \`learning.jmx:type=WorkerPool,name=main\` không khớp tên chính xác đầu tiên, nhưng khớp pattern thứ hai.

### 3.4. Dấu * và ? trong pattern

- \`*\`: khớp chuỗi ký tự có độ dài tùy ý.
- \`?\`: khớp một ký tự.
- Một \`ObjectName\` pattern có thể chứa wildcard trong domain hoặc value, và property-list pattern có cú pháp riêng.

\`\`\`java
ObjectName byDomain = new ObjectName("learning.*:*");
ObjectName byName = new ObjectName(
    "learning.jmx:type=WorkerPool,name=worker-?"
);
ObjectName anyPool = new ObjectName(
    "learning.jmx:type=WorkerPool,*"
);
\`\`\`

Với key property value có ký tự đặc biệt như dấu phẩy, dấu bằng, dấu hai chấm, dấu nháy hoặc wildcard cần hiểu như ký tự dữ liệu, hãy dùng \`ObjectName.quote(value)\` khi xây tên. Wildcard có thể trở thành toán tử pattern nếu được diễn giải ngoài ngữ cảnh quoted phù hợp.

## 4. Truy vấn MBean với queryNames()

API chính:

\`\`\`java
Set<ObjectName> queryNames(
    ObjectName name,
    QueryExp query
) throws IOException;
\`\`\`

Trên \`MBeanServer\` local, lời gọi tương đương không khai báo \`IOException\` checked; trên giao diện \`MBeanServerConnection\` có \`IOException\` do connection có thể là remote.

- \`name\`: tên chính xác hoặc pattern; \`null\` nghĩa là không giới hạn theo tên.
- \`query\`: bộ lọc truy vấn JMX bổ sung; \`null\` nghĩa là không lọc thêm theo biểu thức.
- Giá trị trả về: \`Set<ObjectName>\` của các MBean đang đăng ký và đáp ứng truy vấn tại thời điểm thực hiện.
- \`queryNames\` trả về **tên**, trong khi \`queryMBeans\` trả về các \`ObjectInstance\` chứa tên và thông tin lớp.

### 4.1. Tìm tất cả WorkerPool

\`\`\`java
import java.lang.management.ManagementFactory;
import java.util.Set;
import javax.management.MBeanServer;
import javax.management.ObjectName;

MBeanServer server = ManagementFactory.getPlatformMBeanServer();

ObjectName pattern = new ObjectName(
    "learning.jmx:type=WorkerPool,*"
);

Set<ObjectName> names = server.queryNames(pattern, null);

for (ObjectName name : names) {
    System.out.println(name.getCanonicalName());
}
\`\`\`

Ví dụ kết quả:

\`\`\`text
learning.jmx:name=background,type=WorkerPool
learning.jmx:name=main,type=WorkerPool
\`\`\`

\`getCanonicalName()\` sắp xếp các key properties theo dạng canonical. Nó có thể khác thứ tự khi bạn nhập \`ObjectName\`, nhưng vẫn biểu diễn cùng một tên. Không dựa vào thứ tự phần tử của \`Set\` khi tạo giao diện hoặc báo cáo; cần sort nếu muốn kết quả ổn định.

### 4.2. Lọc theo domain và instance

\`\`\`java
ObjectName pattern = new ObjectName(
    "learning.jmx:type=WorkerPool,name=worker-*,*"
);

Set<ObjectName> names = server.queryNames(pattern, null);
\`\`\`

Mẫu này hữu ích khi các instance được đặt tên theo số thứ tự: \`worker-1\`, \`worker-2\`, hoặc tên miền môi trường.

### 4.3. Kết hợp QueryExp để lọc thuộc tính

JMX hỗ trợ các biểu thức truy vấn qua \`javax.management.Query\`. Ví dụ chỉ tìm WorkerPool có attribute \`ActiveCount\` lớn hơn 10:

\`\`\`java
import javax.management.Query;
import javax.management.QueryExp;

ObjectName poolPattern = new ObjectName(
    "learning.jmx:type=WorkerPool,*"
);

QueryExp busyPools = Query.gt(
    Query.attr("ActiveCount"),
    Query.value(10)
);

Set<ObjectName> names = server.queryNames(
    poolPattern,
    busyPools
);
\`\`\`

Ở đây:

1. \`poolPattern\` giới hạn tập ứng viên theo tên.
2. \`QueryExp\` đánh giá điều kiện trên attribute của MBean.
3. MBean đáp ứng cả hai điều kiện mới nằm trong kết quả.

Để truy vấn này hữu ích, các MBean ứng viên phải công bố attribute \`ActiveCount\` có kiểu số phù hợp. Không nên coi \`QueryExp\` là SQL tổng quát hay một query engine trên Spring beans; nó chỉ vận hành trên thông tin JMX công bố.

### 4.4. Kiểm tra tên trước khi sử dụng

\`\`\`java
ObjectName exact = new ObjectName(
    "learning.jmx:type=WorkerPool,name=main"
);

if (!server.isRegistered(exact)) {
    throw new IllegalStateException("MBean not registered: " + exact);
}

Object activeCount = server.getAttribute(
    exact,
    "ActiveCount"
);
\`\`\`

Một lưu ý về đồng thời: \`isRegistered\` rồi \`getAttribute\` là hai thao tác riêng. MBean có thể được unregister giữa chúng. Client vẫn cần xử lý \`InstanceNotFoundException\` khi thao tác thực tế.

## 5. Ví dụ Standard MBean để minh họa truy vấn và listener

Một MBean phát notification về sự kiện reset có thể triển khai \`NotificationBroadcasterSupport\` và interface \`WorkerPoolMBean\`.

### 5.1. Hợp đồng MBean

\`\`\`java
package example.jmx;

public interface WorkerPoolMBean {
    int getActiveCount();

    void reset();
}
\`\`\`

### 5.2. Implementation có notification

\`\`\`java
package example.jmx;

import java.util.concurrent.atomic.AtomicLong;
import javax.management.AttributeChangeNotification;
import javax.management.MBeanNotificationInfo;
import javax.management.Notification;
import javax.management.NotificationBroadcasterSupport;

public class WorkerPool extends NotificationBroadcasterSupport
        implements WorkerPoolMBean {

    private final AtomicLong sequence = new AtomicLong();
    private volatile int activeCount;

    public WorkerPool(int activeCount) {
        this.activeCount = activeCount;
    }

    @Override
    public int getActiveCount() {
        return activeCount;
    }

    @Override
    public void reset() {
        int oldValue = activeCount;
        activeCount = 0;

        Notification notification = new AttributeChangeNotification(
            this,
            sequence.incrementAndGet(),
            System.currentTimeMillis(),
            "Worker pool active count reset",
            "ActiveCount",
            "int",
            oldValue,
            0
        );
        sendNotification(notification);
    }

    @Override
    public MBeanNotificationInfo[] getNotificationInfo() {
        String[] types = {
            AttributeChangeNotification.ATTRIBUTE_CHANGE
        };

        return new MBeanNotificationInfo[] {
            new MBeanNotificationInfo(
                types,
                AttributeChangeNotification.class.getName(),
                "Worker pool active-count changes"
            )
        };
    }
}
\`\`\`

MBean này expose attribute read-only \`ActiveCount\`, operation \`reset()\` và notification loại \`jmx.attribute.change\`. Notification là một cơ chế được implementation **chủ động phát** bằng \`sendNotification\`; thay đổi Java field đơn thuần không tự động phát notification.

### 5.3. Đăng ký hai instance với ObjectName khác nhau

\`\`\`java
import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import javax.management.ObjectName;

MBeanServer server = ManagementFactory.getPlatformMBeanServer();

ObjectName main = new ObjectName(
    "learning.jmx:type=WorkerPool,name=main"
);
ObjectName background = new ObjectName(
    "learning.jmx:type=WorkerPool,name=background"
);

server.registerMBean(new WorkerPool(12), main);
server.registerMBean(new WorkerPool(4), background);
\`\`\`

Sau khi đăng ký, pattern \`learning.jmx:type=WorkerPool,*\` tìm thấy cả hai. Nhưng để gắn listener hoặc tạo proxy cho \`main\`, cần dùng \`main\` — một tên chính xác.

## 6. ObjectName khi đăng ký NotificationListener

Một MBean có thể phát \`Notification\` để báo sự kiện quản trị: thay đổi cấu hình, lỗi, trạng thái tài nguyên, hoàn tất tác vụ, hoặc một sự kiện tự định nghĩa.

Lời gọi:

\`\`\`java
connection.addNotificationListener(
    objectName,
    listener,
    filter,
    handback
);
\`\`\`

Trong đó:

| Thành phần | Mục đích |
|---|---|
| \`objectName\` | Tên MBean đang phát notification, phải chỉ tới MBean thích hợp. |
| \`listener\` | Đối tượng \`NotificationListener\` nhận callback \`handleNotification\`. |
| \`filter\` | Chấp nhận/bỏ qua notification theo điều kiện; có thể \`null\`. |
| \`handback\` | Đối tượng context do client cung cấp và nhận lại trong callback; có thể \`null\`. |

### 6.1. Gắn listener vào một MBean

\`\`\`java
import javax.management.NotificationFilterSupport;
import javax.management.NotificationListener;

NotificationListener listener = (notification, handback) -> {
    System.out.println(
        "source=" + notification.getSource()
            + ", type=" + notification.getType()
            + ", message=" + notification.getMessage()
            + ", context=" + handback
    );
};

NotificationFilterSupport filter =
    new NotificationFilterSupport();

filter.enableType("jmx.attribute.change");

server.addNotificationListener(
    main,
    listener,
    filter,
    "main-pool-listener"
);

try {
    // Kích hoạt reset() -> MBean gửi notification.
    server.invoke(
        main,
        "reset",
        new Object[0],
        new String[0]
    );
} finally {
    server.removeNotificationListener(
        main,
        listener,
        filter,
        "main-pool-listener"
    );
}
\`\`\`

Lúc \`reset\` chạy, implementation gửi notification qua broadcaster. Callback có thể được gọi theo cơ chế dispatch của broadcaster; **không được giả định callback luôn chạy trên cùng thread với caller hay hoàn thành trước khi \`invoke\` trả về**. Với \`NotificationBroadcasterSupport\` mặc định, việc gửi notification sử dụng executor đồng bộ nếu không cung cấp executor khác, nhưng một client remote có thêm tầng vận chuyển riêng.

### 6.2. Vì sao dùng đúng ObjectName quan trọng?

Nếu listener được gắn vào \`main\`, nó không tự động nhận notification từ \`background\`, kể cả hai MBean cùng loại và cùng domain.

\`\`\`text
main ObjectName ─────── listener A
background ObjectName ─ listener B

queryNames(pattern) -> {main, background}
\`\`\`

Để theo dõi tất cả MBean phù hợp pattern, có thể:

1. \`queryNames(pattern, null)\` lấy danh sách hiện tại.
2. Lặp qua từng **ObjectName chính xác**.
3. Gắn listener vào từng MBean có khả năng phát notification.
4. Lưu lại danh sách đăng ký để tháo listener khi không còn cần.

Truy vấn bằng pattern không tự động duy trì listener trên những MBean đăng ký **sau** thời điểm truy vấn. Muốn theo dõi các MBean mới/xóa đi, có thể lắng nghe notification của \`MBeanServerDelegate\` hoặc tổ chức cơ chế refresh tập MBean.

### 6.3. MBeanServerDelegate cho đăng ký/hủy đăng ký

JMX có MBean hệ thống \`JMImplementation:type=MBeanServerDelegate\` (hằng \`MBeanServerDelegate.DELEGATE_NAME\`) thông báo khi MBean được register/unregister.

\`\`\`java
import javax.management.MBeanServerDelegate;
import javax.management.MBeanServerNotification;
import javax.management.NotificationListener;

NotificationListener registryListener =
    (notification, handback) -> {
        if (notification instanceof MBeanServerNotification event) {
            ObjectName changed = event.getMBeanName();

            System.out.println(
                event.getType() + " " + changed
            );
        }
    };

server.addNotificationListener(
    MBeanServerDelegate.DELEGATE_NAME,
    registryListener,
    null,
    null
);

// Khi dừng theo dõi:
// server.removeNotificationListener(
//     MBeanServerDelegate.DELEGATE_NAME,
//     registryListener
// );
\`\`\`

Có thể kết hợp callback từ Delegate và \`pattern.apply(changed)\` để quyết định có gắn hoặc tháo listener cho một MBean phù hợp. Do query snapshot và notification đăng ký không phải một thao tác nguyên tử, triển khai production nên thiết kế chống race và xử lý đăng ký trùng.

### 6.4. Đăng ký bằng ObjectName của một listener-MBean

Ngoài overload nhận Java \`NotificationListener\`, JMX còn overload:

\`\`\`java
server.addNotificationListener(
    broadcasterName,
    listenerMBeanName,
    filter,
    handback
);
\`\`\`

Overload này chỉ dùng được khi **listener cũng là MBean đã đăng ký và triển khai \`NotificationListener\`** theo yêu cầu của JMX. Không nhầm \`listenerMBeanName\` với \`ObjectName\` của broadcaster. Trong client code thông thường, overload nhận trực tiếp object \`NotificationListener\` thường đơn giản hơn.

## 7. Quản lý vòng đời listener và connection

Gắn listener là đăng ký callback có trạng thái. Nếu quên tháo, ứng dụng có thể giữ tham chiếu không cần thiết hoặc tiếp tục xử lý sự kiện sau khi thành phần tiêu thụ đã dừng.

Mẫu an toàn:

\`\`\`java
NotificationListener listener = (n, h) ->
    System.out.println(n.getMessage());

server.addNotificationListener(
    main,
    listener,
    null,
    null
);

try {
    // Công việc cần theo dõi MBean
} finally {
    server.removeNotificationListener(
        main,
        listener
    );
}
\`\`\`

Nếu dùng overload \`removeNotificationListener(name, listener, filter, handback)\`, phải truyền lại đúng bộ listener/filter/handback tương ứng. Overload chỉ nhận \`name, listener\` có thể gỡ tất cả đăng ký khớp listener đó trên MBean, tùy hợp đồng API.

Các trường hợp cần suy xét:

- **MBean bị unregister:** listener gắn với MBean cũ không tự động chuyển sang instance mới dù instance mới dùng lại cùng ObjectName. Theo dõi lifecycle nếu cần resubscribe.
- **Remote connector bị ngắt:** callback có thể không đến, cần phát hiện mất kết nối và thiết lập lại listener sau khi reconnect.
- **Listener xử lý chậm:** không xử lý tác vụ nặng trực tiếp trong callback; đưa sự kiện vào executor/queue thích hợp và quản lý backlog.
- **MBean không hỗ trợ notification:** đăng ký có thể bị từ chối, ví dụ \`RuntimeOperationsException\` hoặc lỗi JMX thích hợp theo implementation. Kiểm tra \`getMBeanInfo(name).getNotifications()\` trước khi gắn khi cần.
- **Notification trùng hoặc bị bỏ lỡ:** thiết kế xử lý idempotent nếu notification dùng để giám sát, không coi JMX notification là một message broker đảm bảo lưu trữ.

## 8. ObjectName khi tạo JMX proxy

JMX proxy giúp client gọi phương thức Java thông qua interface. Proxy định tuyến lời gọi đến MBean được đặt tên bởi \`ObjectName\`.

### 8.1. JMX API: JMX.newMBeanProxy()

Với Standard MBean:

\`\`\`java
import javax.management.JMX;
import javax.management.MBeanServerConnection;

MBeanServerConnection connection = server;

WorkerPoolMBean proxy = JMX.newMBeanProxy(
    connection,
    main,
    WorkerPoolMBean.class,
    true
);

int active = proxy.getActiveCount();
System.out.println("active=" + active);

proxy.reset();
\`\`\`

Tham số \`true\` yêu cầu tạo proxy hỗ trợ giao diện \`NotificationEmitter\` để có thể quản lý notification listener qua proxy, khi MBean tương ứng hỗ trợ notification.

Điểm quan trọng:

- \`main\` là ObjectName **chính xác** của một MBean.
- \`WorkerPoolMBean.class\` mô tả interface client kỳ vọng.
- \`getActiveCount()\` thường ánh xạ tới thao tác JMX **đọc attribute** \`ActiveCount\`.
- \`reset()\` ánh xạ tới JMX **invoke operation** \`reset\`.
- Proxy không chứa state của WorkerPool; state ở MBean bên phía server.
- Method call có thể thất bại khi MBean biến mất, chữ ký không khớp hoặc remote connection lỗi. Proxy không bảo đảm tự reconnect.

\`\`\`text
Java caller
   |
   v
WorkerPoolMBean proxy.reset()
   |
   v
JMX invocation handler
   |
   v
MBeanServerConnection.invoke(main, "reset", [], [])
   |
   v
WorkerPool MBean server-side
\`\`\`

Với MXBean, dùng \`JMX.newMXBeanProxy(...)\` và tuân thủ mapping kiểu của MXBean; không giả định Standard MBean proxy và MXBean proxy có cùng cơ chế chuyển đổi mọi giá trị.

### 8.2. Spring: MBeanProxyFactoryBean

Spring cung cấp \`org.springframework.jmx.access.MBeanProxyFactoryBean\`, tạo proxy theo \`ObjectName\` và management interface.

Ví dụ interface client:

\`\`\`java
package example.jmx;

public interface WorkerPoolOperations {
    int getActiveCount();
    void reset();
}
\`\`\`

Cấu hình proxy:

\`\`\`java
import javax.management.MBeanServerConnection;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.access.MBeanProxyFactoryBean;

@Configuration
public class JmxClientConfiguration {

    @Bean
    public MBeanProxyFactoryBean workerPoolProxy(
            MBeanServerConnection connection
    ) throws Exception {
        MBeanProxyFactoryBean factory =
            new MBeanProxyFactoryBean();

        factory.setServer(connection);
        factory.setObjectName(
            "learning.jmx:type=WorkerPool,name=main"
        );
        factory.setProxyInterface(
            WorkerPoolOperations.class
        );

        return factory;
    }
}
\`\`\`

Sau khi Spring khởi tạo FactoryBean, đối tượng được inject theo \`WorkerPoolOperations\` sẽ là một proxy JMX:

\`\`\`java
import org.springframework.stereotype.Component;

@Component
public class PoolDashboard {

    private final WorkerPoolOperations pool;

    public PoolDashboard(WorkerPoolOperations pool) {
        this.pool = pool;
    }

    public void printAndReset() {
        System.out.println(pool.getActiveCount());
        pool.reset();
    }
}
\`\`\`

\`MBeanProxyFactoryBean\` dùng \`ObjectName\` để nhắm tới MBean và ánh xạ lời gọi interface theo metadata phù hợp. Chỉ dùng interface với các method/attribute thực sự được MBean công bố; một interface Java tự khai báo thêm method không khiến MBean server-side có thêm operation.

Nếu ứng dụng dùng \`MBeanServerConnection\` remote, cấu hình connection đó qua JMX connector hoặc một \`MBeanServerConnectionFactoryBean\` phù hợp. Local Spring exporter và remote client đều chia sẻ mô hình ObjectName, nhưng connection phải trỏ tới server chứa MBean đích.

### 8.3. Cấu hình proxy bằng tên exact, không bằng pattern

Ví dụ này thích hợp cho truy vấn:

\`\`\`text
learning.jmx:type=WorkerPool,*
\`\`\`

Nhưng khi tạo một proxy, hãy chọn cụ thể:

\`\`\`text
learning.jmx:type=WorkerPool,name=main
\`\`\`

Nếu cần một proxy cho mỗi WorkerPool đang tồn tại, client có thể \`queryNames(pattern, null)\`, rồi tạo từng proxy với mỗi ObjectName được trả về.

\`\`\`java
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Set;
import javax.management.JMX;
import javax.management.ObjectName;

ObjectName pattern = new ObjectName(
    "learning.jmx:type=WorkerPool,*"
);

Set<ObjectName> discovered =
    connection.queryNames(pattern, null);

Map<ObjectName, WorkerPoolMBean> proxies =
    new LinkedHashMap<>();

for (ObjectName name : discovered) {
    WorkerPoolMBean proxy = JMX.newMBeanProxy(
        connection,
        name,
        WorkerPoolMBean.class,
        false
    );
    proxies.put(name, proxy);
}
\`\`\`

Đây là **snapshot** của các MBean tại thời điểm truy vấn. Những MBean được đăng ký sau đó không tự động xuất hiện trong map. Nếu MBean bị xóa, proxy đã tạo có thể vẫn tồn tại ở phía client nhưng lời gọi sẽ lỗi.

## 9. Pattern matching: ví dụ có và không khớp

Giả sử server có các MBean:

\`\`\`text
learning.jmx:type=WorkerPool,name=main
learning.jmx:type=WorkerPool,name=background
learning.jmx:type=WorkerPool,name=main,node=n1
learning.jmx:type=Cache,name=users
system.jmx:type=WorkerPool,name=main
\`\`\`

| Pattern | Những MBean phù hợp | Giải thích |
|---|---|---|
| \`learning.jmx:type=WorkerPool,name=main\` | Chỉ WorkerPool main không có property thêm | Tên chính xác. |
| \`learning.jmx:type=WorkerPool,name=*\` | WorkerPool main và background không có property thêm | Value pattern nhưng property list cố định. |
| \`learning.jmx:type=WorkerPool,name=*,*\` | Ba WorkerPool thuộc domain learning.jmx | Cho phép thêm key property. |
| \`learning.jmx:type=WorkerPool,*\` | Ba WorkerPool thuộc domain learning.jmx | Chỉ ràng buộc \`type\`. |
| \`*:type=WorkerPool,*\` | Tất cả WorkerPool ở cả hai domain | Domain wildcard + property-list pattern. |
| \`learning.jmx:type=Cache,*\` | Cache users | Lọc theo type Cache. |

Một \`ObjectName\` có cùng key properties nhưng thứ tự khác nhau vẫn biểu diễn cùng tên nếu giá trị tương ứng như nhau. Ví dụ \`learning.jmx:name=main,type=WorkerPool\` tương đương \`learning.jmx:type=WorkerPool,name=main\`.

## 10. Query rồi subscribe: mẫu theo dõi nhiều MBean

Bài toán: theo dõi notification cho mọi \`WorkerPool\` thuộc domain \`learning.jmx\`.

\`\`\`java
import java.util.HashSet;
import java.util.Set;
import javax.management.MBeanServerConnection;
import javax.management.NotificationListener;
import javax.management.ObjectName;

public final class WorkerPoolSubscriptions
        implements AutoCloseable {

    private final MBeanServerConnection connection;
    private final ObjectName pattern;
    private final NotificationListener listener;
    private final Set<ObjectName> subscriptions =
        new HashSet<>();

    public WorkerPoolSubscriptions(
            MBeanServerConnection connection
    ) throws Exception {
        this.connection = connection;
        this.pattern = new ObjectName(
            "learning.jmx:type=WorkerPool,*"
        );
        this.listener = (notification, handback) ->
            System.out.println(
                notification.getType() + ": "
                    + notification.getMessage()
            );
    }

    public void subscribeCurrent() throws Exception {
        for (ObjectName name :
                connection.queryNames(pattern, null)) {
            if (subscriptions.contains(name)) {
                continue;
            }

            connection.addNotificationListener(
                name,
                listener,
                null,
                null
            );
            subscriptions.add(name);
        }
    }

    @Override
    public void close() {
        for (ObjectName name : subscriptions) {
            try {
                connection.removeNotificationListener(
                    name,
                    listener
                );
            } catch (Exception ignored) {
                // MBean đã unregister hoặc remote đã ngắt.
            }
        }
        subscriptions.clear();
    }
}
\`\`\`

Sử dụng:

\`\`\`java
try (WorkerPoolSubscriptions subscriptions =
         new WorkerPoolSubscriptions(connection)) {
    subscriptions.subscribeCurrent();
    // Thực hiện công việc hoặc duy trì tiến trình nhận sự kiện.
}
\`\`\`

Lưu ý: ví dụ đăng ký **những MBean hiện có** và giải phóng các listener đã đăng ký khi kết thúc. Nó chưa bao gồm subscription động khi MBean mới xuất hiện, chưa xử lý reconnect và race giữa query/register. Với hệ thống thực tế, dùng thông báo từ \`MBeanServerDelegate\` hoặc chiến lược refresh, đồng thời tránh duplicate listener và cập nhật tập subscription khi MBean biến mất.

## 11. Spring NotificationListenerBean và listener mapping

Ngoài đăng ký listener trực tiếp qua JMX API, Spring JMX export hỗ trợ cấu hình notification listener cho các MBean được quản lý bởi exporter. Cấu trúc thường gồm:

- \`NotificationListenerBean\`: mô tả callback, filter và danh sách mapped object names.
- \`MBeanExporter.setNotificationListeners(...)\`: cung cấp cấu hình listener cho exporter.
- \`mappedObjectNames\`: xác định tên của MBean mà listener sẽ được đăng ký.

Ví dụ minh họa:

\`\`\`java
import java.util.Map;
import javax.management.NotificationListener;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.export.MBeanExporter;
import org.springframework.jmx.export.NotificationListenerBean;

@Configuration
class SpringNotificationConfig {

    @Bean
    MBeanExporter exporter(
            WorkerPool monitoredPool
    ) {
        MBeanExporter exporter = new MBeanExporter();
        exporter.setBeans(Map.of(
            "learning.jmx:type=WorkerPool,name=main",
            monitoredPool
        ));

        NotificationListener listener =
            (notification, handback) ->
                System.out.println(notification.getMessage());

        NotificationListenerBean subscription =
            new NotificationListenerBean(listener);

        subscription.setMappedObjectNames(
            "learning.jmx:type=WorkerPool,name=main"
        );

        exporter.setNotificationListeners(subscription);
        return exporter;
    }
}
\`\`\`

Ví dụ này giả định bean \`WorkerPool\` được Spring quản lý và phù hợp để export dưới dạng MBean. Đừng đồng thời cấu hình một exporter khác cố đăng ký cùng ObjectName. Spring quản lý registration/listener lifecycle theo cấu hình exporter, nhưng **không suy diễn** rằng \`mappedObjectNames\` là một ngôn ngữ query hoàn chỉnh thay cho \`MBeanServerConnection.queryNames\` trong mọi tình huống.

Ở phía client, một ứng dụng Spring vẫn có thể dùng \`MBeanClientInterceptor\` hoặc \`MBeanProxyFactoryBean\` để gọi MBean qua ObjectName. Server-side listener configuration và client-side proxy giải quyết hai nhu cầu khác nhau: nhận notification và thực thi operation/attribute access.

## 12. Tác động khi ObjectName thay đổi

Một \`ObjectName\` chỉ có ý nghĩa trong phạm vi registry của một \`MBeanServer\`. Việc thay tên, unregister/re-register hoặc thay đổi MBeanServer có thể phá vỡ tham chiếu đang dùng.

| Thay đổi | Query theo pattern | Listener đã gắn | Proxy đã tạo |
|---|---|---|---|
| MBean mới được đăng ký với tên phù hợp | Lần query sau sẽ thấy | Không tự gắn listener | Không tự tạo proxy mới |
| MBean unregister | Lần query sau không thấy | Đăng ký với instance cũ mất hiệu lực | Gọi có thể lỗi \`InstanceNotFoundException\` (thường được proxy bọc) |
| MBean re-register cùng tên | Lần query sau lại thấy | Có thể cần đăng ký lại listener | Proxy có thể tiếp tục định tuyến theo tên, nhưng phải bảo đảm interface/contract còn phù hợp |
| ObjectName đổi property | Phụ thuộc pattern có khớp tên mới | Listener theo tên cũ không theo sang tên mới | Proxy tiếp tục nhắm tới tên cũ |
| Client chuyển MBeanServer | Kết quả truy vấn theo server mới | Listener cũ nằm ở connection/server cũ | Phải cấu hình connection phù hợp |

Bởi vậy nên chọn quy tắc đặt ObjectName có tính ổn định, duy nhất và có cấu trúc. Tránh dùng giá trị ngẫu nhiên thay đổi mỗi lần khởi động nếu client phụ thuộc vào tên cố định; khi cần nhiều instance, đưa các chiều \`instance\`, \`node\` hoặc \`region\` vào key properties.

## 13. Local và remote: cùng ObjectName, khác kết nối

\`\`\`text
Local:
MBeanServer -> ObjectName -> MBean

Remote:
JMXConnector -> MBeanServerConnection -> ObjectName -> MBean
\`\`\`

Tên \`learning.jmx:type=WorkerPool,name=main\` **không chứa hostname hoặc endpoint remote**. Việc chọn máy/JVM được thực hiện thông qua connection, sau đó \`ObjectName\` chọn MBean trong server ấy.

Ví dụ client remote:

\`\`\`java
import javax.management.MBeanServerConnection;
import javax.management.ObjectName;
import javax.management.remote.JMXConnector;
import javax.management.remote.JMXConnectorFactory;
import javax.management.remote.JMXServiceURL;

JMXServiceURL url = new JMXServiceURL(
    "service:jmx:rmi:///jndi/rmi://localhost:9999/jmxrmi"
);

try (JMXConnector connector =
         JMXConnectorFactory.connect(url)) {

    MBeanServerConnection remote =
        connector.getMBeanServerConnection();

    ObjectName pattern = new ObjectName(
        "learning.jmx:type=WorkerPool,*"
    );

    for (ObjectName name :
            remote.queryNames(pattern, null)) {
        System.out.println(name);
    }
}
\`\`\`

Đoạn mã giả định JMX connector đã chạy và được phép kết nối. Export một Spring bean qua JMX không tự bật remote connector. Khi mở remote, cần xác thực, phân quyền và cấu hình mạng phù hợp, đặc biệt với MBean có operation thay đổi trạng thái.

Notification từ remote client có thêm rủi ro ngắt kết nối và độ trễ. Nên theo dõi trạng thái connector, làm lại subscription sau reconnect và không xem notification như nguồn dữ liệu bảo đảm lưu trữ.

## 14. Lỗi thường gặp và cách xác định nguyên nhân

### Query không trả về MBean

Kiểm tra:

1. Kết nối có đúng JVM/MBeanServer nơi exporter đăng ký không?
2. MBean đã thực sự đăng ký với \`ObjectName\` dự kiến chưa?
3. Pattern có quên \`,*\` khi MBean có nhiều key properties không?
4. Domain, key và value có đúng chính tả và chữ hoa/thường không?
5. Có ký tự đặc biệt trong value cần \`ObjectName.quote()\` không?

Ví dụ:

\`\`\`java
ObjectName strict = new ObjectName(
    "learning.jmx:type=WorkerPool"
);
ObjectName pattern = new ObjectName(
    "learning.jmx:type=WorkerPool,*"
);
\`\`\`

Một MBean có thêm \`name=main\` không khớp \`strict\`, nhưng có thể khớp \`pattern\`.

### Listener không nhận notification

- MBean có hỗ trợ \`NotificationBroadcaster\`/\`NotificationEmitter\` và công bố notification metadata thích hợp không?
- Listener có được gắn vào đúng **ObjectName** không?
- Bộ lọc \`NotificationFilter\` có chặn nhầm loại sự kiện không?
- Implementation có thực sự gọi \`sendNotification\` hoặc cơ chế phát notification tương ứng không?
- MBean đã bị unregister và đăng ký lại chưa?
- Với remote client, connection còn hoạt động không?

### Proxy gọi thất bại

- Proxy trỏ tới đúng server và ObjectName chưa?
- Giao diện proxy có đúng method/attribute đã expose không?
- Operation có chữ ký, số lượng tham số và kiểu trả về phù hợp không?
- MBean đã bị unregister hoặc thay bằng phiên bản khác chưa?
- Spring exporter có xuất bản attribute theo annotation/assembler như client kỳ vọng không?

### Query nhiều MBean nhưng proxy chỉ truy cập một

Đây là hành vi được thiết kế: query trả về **tập tên**, còn proxy đại diện **một tên**. Nếu ứng dụng cần dashboard nhiều instance, xây dựng tập proxy từ kết quả \`queryNames\` và refresh khi registry thay đổi.

## 15. Bài tập thực hành

Giả sử hệ thống có:

\`\`\`text
app.monitoring:type=Cache,name=users,node=a
app.monitoring:type=Cache,name=orders,node=a
app.monitoring:type=Cache,name=users,node=b
app.monitoring:type=Queue,name=emails,node=a
\`\`\`

**Câu 1.** Viết pattern lấy tất cả Cache:

\`\`\`java
ObjectName allCaches = new ObjectName(
    "app.monitoring:type=Cache,*"
);
\`\`\`

**Câu 2.** Viết pattern lấy Cache \`users\` trên mọi node:

\`\`\`java
ObjectName userCaches = new ObjectName(
    "app.monitoring:type=Cache,name=users,*"
);
\`\`\`

**Câu 3.** Có thể dùng \`userCaches\` làm ObjectName cho một \`JMX.newMBeanProxy\` đại diện tất cả instance không?

Không. Proxy JMX nhắm vào một MBean. Truy vấn \`queryNames(userCaches, null)\`, sau đó tạo proxy cho từng \`ObjectName\` chính xác trong kết quả.

**Câu 4.** Nếu listener đang gắn với \`app.monitoring:type=Cache,name=users,node=a\`, nó có tự nhận notification từ node \`b\` không?

Không. Cần đăng ký listener riêng cho MBean node \`b\` hoặc có lớp tổng hợp notification khác.

**Câu 5.** Nếu node \`a\` đăng ký lại cùng ObjectName, điều gì cần xử lý?

Truy vấn có thể thấy MBean mới với cùng tên, nhưng đăng ký listener cũ không bảo đảm còn hiệu lực. Client theo dõi lifecycle và gắn listener lại; proxy phải kiểm tra contract của MBean mới.

## 16. Ghi nhớ

\`\`\`text
ObjectName exact:
    Chọn đúng một MBean
    -> attribute / operation / listener / proxy

ObjectName pattern:
    Chọn tập MBean khi query
    -> queryNames(pattern, QueryExp?)
    -> Set<ObjectName> exact
    -> listener hoặc proxy cho từng tên cụ thể
\`\`\`

**Quy tắc thực hành:** dùng **pattern để khám phá**, dùng **exact ObjectName để tương tác**, và quản lý **vòng đời đăng ký MBean, listener và proxy** vì registry có thể thay đổi trong khi ứng dụng đang chạy.