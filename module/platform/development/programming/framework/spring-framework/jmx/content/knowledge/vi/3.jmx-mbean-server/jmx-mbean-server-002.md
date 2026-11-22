# Tra cứu MBean bằng ObjectName trong MBeanServer

## 1. Mục tiêu

Khi một MBean đã được đăng ký trong JMX, muốn đọc thuộc tính, gọi operation, hoặc đăng ký nhận notification, ứng dụng cần xác định đúng **ObjectName** của MBean đó. **MBeanServer** lưu tập các MBean đã đăng ký và cung cấp các API truy vấn theo ObjectName.

Bài này tập trung vào câu hỏi: **Làm thế nào tra cứu MBean bằng ObjectName?** Ta sẽ đi từ cách hiểu ObjectName, phân biệt tên chính xác với pattern, đến các phương thức \`isRegistered\`, \`queryNames\`, \`queryMBeans\` và cách kết hợp với \`MBeanServerConnection\` trong ứng dụng Spring.

## 2. ObjectName là địa chỉ của MBean

Một ObjectName có dạng:

\`\`\`text
domain:key1=value1,key2=value2
\`\`\`

Ví dụ:

\`\`\`text
demo.app:type=Cache,name=Primary
java.lang:type=Memory
java.lang:type=GarbageCollector,name=G1 Young Generation
\`\`\`

Trong đó:

- **Domain** là namespace logic, chẳng hạn \`demo.app\` hoặc \`java.lang\`.
- **Key properties** là các cặp khóa/giá trị phân biệt MBean trong domain; ví dụ \`type=Cache\`, \`name=Primary\`.
- **Canonical name** là cách biểu diễn chuẩn hóa của ObjectName. Thứ tự key property trong chuỗi đầu vào không quyết định danh tính ObjectName.
- **ObjectName chính xác** đại diện cho một MBean cụ thể, còn **ObjectName pattern** mô tả tập MBean khớp một mẫu.

Hai biểu diễn sau xác định cùng một ObjectName:

\`\`\`text
demo.app:type=Cache,name=Primary
demo.app:name=Primary,type=Cache
\`\`\`

Vì vậy, khi so sánh hai ObjectName, nên dùng \`equals()\` thay vì so sánh chuỗi thô. Muốn lấy chuỗi ổn định để log, dùng \`getCanonicalName()\`.

\`\`\`java
import javax.management.ObjectName;

ObjectName first =
    new ObjectName("demo.app:type=Cache,name=Primary");
ObjectName second =
    new ObjectName("demo.app:name=Primary,type=Cache");

System.out.println(first.equals(second)); // true
System.out.println(first.getCanonicalName());
// demo.app:name=Primary,type=Cache
\`\`\`

**Điểm quan trọng:** ObjectName định danh **MBean đã đăng ký trong một MBeanServer**. Nó không phải Java class name, Spring bean name, địa chỉ URL hay object reference trong heap. Cùng một ObjectName có thể xuất hiện trên các MBeanServer khác nhau; muốn tra cứu đúng đối tượng cần kết nối đúng server.

## 3. Tra cứu theo tên chính xác

Khi biết chính xác ObjectName, cách đơn giản nhất là tạo ObjectName rồi kiểm tra với \`isRegistered\`.

\`\`\`java
import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import javax.management.ObjectName;

public class ExactMBeanLookup {
    public static void main(String[] args) throws Exception {
        MBeanServer server =
            ManagementFactory.getPlatformMBeanServer();

        ObjectName memoryName =
            new ObjectName("java.lang:type=Memory");

        boolean exists = server.isRegistered(memoryName);
        System.out.println("Registered: " + exists);

        if (exists) {
            Object heapMemoryUsage =
                server.getAttribute(memoryName, "HeapMemoryUsage");
            System.out.println("Heap usage: " + heapMemoryUsage);
        }
    }
}
\`\`\`

Trong ví dụ, \`java.lang:type=Memory\` là platform MBean có sẵn trên JVM thông thường; thuộc tính \`HeapMemoryUsage\` trả về dữ liệu tổng hợp bộ nhớ heap (thường ở dạng \`CompositeData\` khi truy cập qua JMX).

Quy trình chính xác:

1. Có \`MBeanServer\` hoặc \`MBeanServerConnection\` trỏ đến server cần tra cứu.
2. Tạo \`ObjectName\` theo đúng domain và bộ key properties của MBean.
3. Dùng \`isRegistered(name)\` kiểm tra sự hiện diện khi cần.
4. Dùng \`getMBeanInfo\`, \`getAttribute\`, \`setAttribute\` hoặc \`invoke\` theo đúng giao diện MBean.

\`isRegistered\` chỉ phản ánh trạng thái tại thời điểm gọi. MBean có thể bị unregister giữa bước kiểm tra và bước đọc; mã thực tế vẫn phải xử lý \`InstanceNotFoundException\`.

## 4. Tra cứu nhiều MBean bằng queryNames

Khi không biết toàn bộ tên, hoặc cần tìm nhiều MBean cùng nhóm, dùng:

\`\`\`java
Set<ObjectName> queryNames(ObjectName name, QueryExp query)
\`\`\`

Trong đó:

- \`name\`: \`ObjectName\` chính xác hoặc pattern; \`null\` nghĩa là không giới hạn theo tên.
- \`query\`: biểu thức lọc bổ sung \`QueryExp\`; \`null\` nghĩa là không có điều kiện lọc bổ sung.
- Giá trị trả về là \`Set<ObjectName>\` của các MBean khớp và đang được đăng ký trên server.

Ví dụ tìm tất cả MBean trong domain \`java.lang\`:

\`\`\`java
import java.lang.management.ManagementFactory;
import java.util.Set;
import javax.management.MBeanServer;
import javax.management.ObjectName;

public class PatternLookup {
    public static void main(String[] args) throws Exception {
        MBeanServer server =
            ManagementFactory.getPlatformMBeanServer();

        ObjectName pattern = new ObjectName("java.lang:*");
        Set<ObjectName> names = server.queryNames(pattern, null);

        for (ObjectName name : names) {
            System.out.println(name.getCanonicalName());
        }
    }
}
\`\`\`

Ví dụ lọc theo loại MBean:

\`\`\`java
ObjectName pattern =
    new ObjectName("java.lang:type=GarbageCollector,*");

Set<ObjectName> collectors = server.queryNames(pattern, null);
for (ObjectName collector : collectors) {
    System.out.println(collector);
}
\`\`\`

Dấu \`*\` sau dấu phẩy cho phép ObjectName có thêm các key properties ngoài \`type=GarbageCollector\`. Điều này đặc biệt hữu ích khi tên MBean khác nhau giữa các phiên bản JVM hoặc các GC implementation.

Nếu cần lấy metadata cùng với tên và tham chiếu \`ObjectInstance\`, dùng \`queryMBeans(pattern, null)\`, trả về \`Set<ObjectInstance>\`. Với nhu cầu chỉ cần danh sách tên để đọc tiếp, \`queryNames\` thường là đủ và đơn giản hơn.

### Phân biệt những pattern thường gặp

| ObjectName | Ý nghĩa |
| --- | --- |
| \`demo.app:type=Cache,name=Primary\` | Tên chính xác của một MBean |
| \`demo.app:*\` | Mọi MBean trong domain \`demo.app\` |
| \`demo.app:type=Cache,*\` | Các MBean có property \`type=Cache\`, cho phép thêm key khác |
| \`demo.*:type=Cache,*\` | Domain khớp \`demo.*\`, property \`type=Cache\` |
| \`*:type=Cache,*\` | Các domain bất kỳ có \`type=Cache\` |
| \`java.lang:type=Memory\` | Platform Memory MBean cụ thể |

\`ObjectName\` hỗ trợ pattern ở domain và key properties. Không phải mọi chuỗi có dấu \`*\` đều có ý nghĩa như regex: JMX áp dụng **ObjectName pattern matching**, với cú pháp riêng của nó. Kiểm tra \`pattern.isPattern()\` để biết ObjectName có phải mẫu không.

Ví dụ:

\`\`\`java
ObjectName exact =
    new ObjectName("demo.app:type=Cache,name=Primary");
ObjectName wildcard =
    new ObjectName("demo.app:type=Cache,*");

System.out.println(exact.isPattern());    // false
System.out.println(wildcard.isPattern()); // true
\`\`\`

## 5. Truy vấn theo QueryExp khi chỉ pattern là chưa đủ

Tham số thứ hai của \`queryNames\` có thể là \`QueryExp\` để lọc thêm theo giá trị thuộc tính hoặc thông tin có thể đánh giá từ MBean.

\`\`\`java
import java.util.Set;
import javax.management.MBeanServer;
import javax.management.ObjectName;
import javax.management.Query;
import javax.management.QueryExp;

ObjectName pattern = new ObjectName("demo.app:type=Worker,*");

QueryExp enabledFilter = Query.eq(
    Query.attr("Enabled"),
    Query.value(true)
);

Set<ObjectName> enabledWorkers =
    server.queryNames(pattern, enabledFilter);
\`\`\`

Ở đây, các MBean được xem xét cần có thuộc tính JMX \`Enabled\` có thể đọc và phù hợp điều kiện. Tên thuộc tính trong \`Query.attr("Enabled")\` là tên **JMX attribute**, không nhất thiết trùng với tên field Java. Một số MBean thiếu thuộc tính, không cho đọc, hoặc lỗi khi đánh giá điều kiện có thể không xuất hiện trong kết quả; không được hiểu kết quả rỗng là khẳng định mọi worker đang tắt.

Có thể kết hợp điều kiện với \`Query.and\`, \`Query.or\`, \`Query.gt\`, \`Query.lt\` hoặc các toán tử phù hợp. Trong công việc thông thường, nên ưu tiên lọc bằng domain/key properties trước vì ổn định và dễ quan sát, chỉ dùng QueryExp khi cần lọc theo thuộc tính runtime.

## 6. Khám phá metadata trước khi đọc hoặc gọi operation

Một ObjectName hợp lệ không bảo đảm mọi thuộc tính hoặc operation dự đoán đều có mặt. Sau khi tìm thấy MBean, \`getMBeanInfo(name)\` trả về mô tả giao diện quản lý:

\`\`\`java
import javax.management.MBeanAttributeInfo;
import javax.management.MBeanInfo;
import javax.management.MBeanOperationInfo;
import javax.management.ObjectName;

ObjectName name = new ObjectName("java.lang:type=Memory");
MBeanInfo info = server.getMBeanInfo(name);

System.out.println("MBean class: " + info.getClassName());

for (MBeanAttributeInfo attribute : info.getAttributes()) {
    System.out.printf(
        "Attribute %s, readable=%s, writable=%s%n",
        attribute.getName(),
        attribute.isReadable(),
        attribute.isWritable()
    );
}

for (MBeanOperationInfo operation : info.getOperations()) {
    System.out.println("Operation: " + operation.getName());
}
\`\`\`

Bước khám phá metadata giúp xác định:

- Thuộc tính nào có thể đọc hoặc ghi.
- Operation nào tồn tại và các kiểu tham số cần truyền.
- Tên MBean và tên attribute có đúng với giả định của client không.
- MBean là Standard MBean, MXBean, Spring-exported ModelMBean hoặc loại khác ở mức metadata và descriptor được công bố.

Chẳng hạn, muốn gọi operation cần dùng \`invoke(ObjectName name, String operationName, Object[] params, String[] signature)\`. Với operation có tham số, signature phải mô tả đúng kiểu Java đã công bố trong MBeanInfo.

## 7. Đọc thuộc tính sau khi đã tra cứu

Ví dụ đọc mức sử dụng heap của platform MBean:

\`\`\`java
import javax.management.ObjectName;
import javax.management.openmbean.CompositeData;

ObjectName name = new ObjectName("java.lang:type=Memory");
CompositeData heap = (CompositeData)
    server.getAttribute(name, "HeapMemoryUsage");

long used = (Long) heap.get("used");
long max = (Long) heap.get("max");

System.out.println("Heap used: " + used);
System.out.println("Heap max: " + max);
\`\`\`

\`HeapMemoryUsage\` được JMX biểu diễn dưới dạng \`CompositeData\`, có các trường như \`init\`, \`used\`, \`committed\` và \`max\`. \`max\` có thể là \`-1\` nếu không xác định, nên không được mặc định sử dụng phép chia \`used/max\` khi hiển thị phần trăm.

Ví dụ đọc nhiều MBean và xử lý lỗi riêng từng đối tượng:

\`\`\`java
ObjectName pattern =
    new ObjectName("java.lang:type=GarbageCollector,*");

for (ObjectName name : server.queryNames(pattern, null)) {
    try {
        Object count = server.getAttribute(name, "CollectionCount");
        System.out.println(name + " -> " + count);
    } catch (javax.management.InstanceNotFoundException e) {
        // MBean đã biến mất sau lúc query.
        System.out.println("MBean no longer registered: " + name);
    } catch (javax.management.AttributeNotFoundException e) {
        // MBean hiện tại không công bố thuộc tính kỳ vọng.
        System.out.println("Attribute unavailable on: " + name);
    }
}
\`\`\`

Đối với kết nối từ xa, cần xử lý thêm \`IOException\`, lỗi bảo mật và các lỗi JMX tùy lời gọi. Không nên giả định toàn bộ danh sách \`queryNames\` bất biến trong suốt vòng lặp.

## 8. MBeanServerConnection và ứng dụng Spring

\`MBeanServer\` thường được dùng khi truy cập server trong cùng JVM; \`MBeanServerConnection\` là giao diện chung cho cả kết nối local và remote. Các phương thức tra cứu cốt lõi \`queryNames\`, \`queryMBeans\`, \`isRegistered\` và \`getMBeanInfo\` đều có trên \`MBeanServerConnection\`.

Trong Spring, có thể inject kết nối JMX vào service:

\`\`\`java
import java.io.IOException;
import java.util.Set;
import javax.management.MBeanServerConnection;
import javax.management.ObjectName;
import org.springframework.stereotype.Service;

@Service
public class JmxDiscoveryService {
    private final MBeanServerConnection connection;

    public JmxDiscoveryService(MBeanServerConnection connection) {
        this.connection = connection;
    }

    public Set<ObjectName> findCacheMBeans() throws Exception {
        ObjectName pattern = new ObjectName("demo.app:type=Cache,*");
        return connection.queryNames(pattern, null);
    }

    public boolean exists(String objectName) throws Exception {
        return connection.isRegistered(new ObjectName(objectName));
    }
}
\`\`\`

Ví dụ cấu hình kết nối local bằng platform MBeanServer:

\`\`\`java
import java.lang.management.ManagementFactory;
import javax.management.MBeanServerConnection;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class LocalJmxClientConfiguration {
    @Bean
    public MBeanServerConnection mbeanServerConnection() {
        return ManagementFactory.getPlatformMBeanServer();
    }
}
\`\`\`

Với remote JMX, Spring cung cấp \`MBeanServerConnectionFactoryBean\` để đưa kết nối vào container qua cấu hình. Dù kết nối được tạo bằng Spring hay API JMX thuần, cách dùng \`ObjectName\` và \`queryNames\` vẫn như nhau.

Lưu ý \`MBeanProxyFactoryBean\` có nhiệm vụ **truy cập một MBean cụ thể bằng ObjectName**, không thay thế truy vấn nhiều MBean qua \`queryNames\`. Nếu cần discovery động, hãy query tên trước rồi tạo hoặc sử dụng client tương ứng theo các tên đã phát hiện.

## 9. Đăng ký một MBean tùy chỉnh để thử lookup

Có thể chạy ví dụ tối giản sau bằng Java JMX thuần; Spring chỉ bổ sung tiện ích export và quản lý lifecycle quanh cơ chế này.

\`\`\`java
import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import javax.management.ObjectName;
import java.util.Set;

interface CacheStatsMBean {
    int getItemCount();
}

public static class CacheStats implements CacheStatsMBean {
    @Override
    public int getItemCount() {
        return 42;
    }
}

MBeanServer server = ManagementFactory.getPlatformMBeanServer();
ObjectName target =
    new ObjectName("demo.app:type=Cache,name=Primary");

// Trong ví dụ thực thi, interface và class public cần đặt đúng
// cấu trúc Java/classpath để tuân theo quy ước Standard MBean.
server.registerMBean(new CacheStats(), target);

ObjectName pattern = new ObjectName("demo.app:type=Cache,*");
Set<ObjectName> matches = server.queryNames(pattern, null);
System.out.println(matches.contains(target)); // true

System.out.println(server.getAttribute(target, "ItemCount")); // 42

server.unregisterMBean(target);
System.out.println(server.isRegistered(target)); // false
\`\`\`

Đoạn code là các mảnh minh họa logic đặt trong một lớp/phương thức thích hợp. \`CacheStatsMBean\` và \`CacheStats\` cần được khai báo public ở dạng lớp/giao diện phù hợp với quy tắc Standard MBean, hoặc triển khai bằng \`StandardMBean\` khi cấu trúc class không theo quy tắc tên mặc định.

Với Spring \`@ManagedResource\` và \`@EnableMBeanExport\`, có thể bỏ phần đăng ký/hủy đăng ký thủ công: Spring sẽ export bean dưới ObjectName được cấu hình. Bước tra cứu \`queryNames\` của client vẫn không đổi.

## 10. Lỗi thường gặp và cách phân biệt

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| \`queryNames\` trả Set rỗng | Sai domain, sai key, sai pattern hoặc kết nối sai MBeanServer | In canonical ObjectName, thử \`queryNames(null, null)\` trong môi trường kiểm soát, xác định server |
| \`MalformedObjectNameException\` | ObjectName sai cú pháp, ký tự đặc biệt chưa quote | Dùng \`ObjectName.quote(value)\` cho giá trị chứa ký tự đặc biệt |
| \`InstanceNotFoundException\` | Tên chưa đăng ký hoặc đã bị unregister giữa hai lời gọi | Kiểm tra lifecycle và xử lý race condition |
| \`AttributeNotFoundException\` | Sai tên thuộc tính hoặc thuộc tính không được expose | Xem \`getMBeanInfo\` thay vì đoán field Java |
| \`ReflectionException\`, \`MBeanException\` | Operation không khớp signature hoặc mã phía MBean ném lỗi | Kiểm tra tên, tham số, signature và lỗi gốc |
| \`SecurityException\` hoặc lỗi kết nối | Quyền truy cập JMX, cấu hình remote hoặc mạng | Kiểm tra xác thực, TLS, firewall và quyền connector |
| Tìm được MBean nhưng dữ liệu không như kỳ vọng | Nối sai server/instance hoặc ObjectName tương tự | Xác minh JVM, server và key định danh instance |

### Ký tự đặc biệt trong ObjectName

Giá trị property được truyền từ cấu hình người dùng có thể chứa dấu phẩy, dấu bằng, dấu hai chấm, dấu ngoặc kép, dấu sao hoặc dấu hỏi. Khi xây tên động, đừng nối chuỗi mà không xét quy tắc escape.

\`\`\`java
String applicationName = "order,service";
String quoted = ObjectName.quote(applicationName);
ObjectName name = new ObjectName(
    "demo.app:type=Service,name=" + quoted
);
\`\`\`

\`ObjectName.quote\` xử lý phần **value**, không thay cho việc xác thực key hoặc domain. Nếu phải tìm MBean dựa vào giá trị có wildcard theo nghĩa literal, cần phân biệt pattern JMX với ký tự thực tế được quote/escape.

### Performance và độ ổn định

- \`queryNames(null, null)\` tìm toàn bộ MBean và có thể tốn chi phí, nhất là khi gọi từ remote; ưu tiên thu hẹp bằng domain/type.
- Kết quả truy vấn là tập hợp, không bảo đảm thứ tự. Muốn hiển thị ổn định thì sort theo \`getCanonicalName()\`.
- Đừng dùng ObjectName pattern như một tiêu chí phân quyền. MBeanServer/connector phải kiểm soát quyền độc lập.
- Tránh cache danh sách MBean vô thời hạn khi các thành phần được đăng ký/hủy đăng ký động.
- Nếu có nhiều JVM, mỗi kết nối đại diện cho một server/đích; JMX không tự tổng hợp MBean trên mọi JVM.

## 11. Mô hình tư duy

\`\`\`text
Spring application / JMX client
             |
             v
    MBeanServerConnection
             |
             +-- isRegistered(exactName) ------> Có MBean cụ thể?
             |
             +-- queryNames(namePattern, null) -> Tập ObjectName
             |                                     |
             |                                     +--> chọn ObjectName
             |                                               |
             +-- getMBeanInfo(name) <-------------------------+
             +-- getAttribute(name, attr)
             +-- invoke(name, operation, args, signature)
             |
             v
    MBeanServer đăng ký các MBean
             |
             +-- demo.app:type=Cache,name=Primary
             +-- demo.app:type=Cache,name=Secondary
             +-- java.lang:type=Memory
\`\`\`

Để nhớ nhanh: **ObjectName là định danh; MBeanServer là nơi đăng ký; \`isRegistered\` kiểm tra tên chính xác; \`queryNames\` tìm các tên theo mẫu; \`getMBeanInfo\` cho biết khả năng quản lý; \`getAttribute\`/\`invoke\` thực hiện tương tác.** Spring giúp cấu hình kết nối và xuất bản MBean thuận tiện hơn, nhưng chính các API JMX này thực hiện việc tra cứu.
