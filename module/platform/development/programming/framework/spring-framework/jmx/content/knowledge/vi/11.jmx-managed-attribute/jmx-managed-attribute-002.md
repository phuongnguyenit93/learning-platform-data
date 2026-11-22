# Getter tạo attribute chỉ đọc với @ManagedAttribute trong Spring Framework JMX

## 1. Mục tiêu học tập

Trong Spring Framework JMX, một phương thức getter có thể trở thành **attribute có thể đọc** của MBean khi được công khai qua metadata quản trị. Annotation \`@ManagedAttribute\` là một cách mô tả getter hoặc setter cho cơ chế export của Spring. Nếu Spring chỉ expose getter và không expose setter tương ứng, JMX client nhìn thấy attribute ở trạng thái **read-only**.

Ví dụ:

\`\`\`java
@ManagedAttribute
public int getActiveSessions() {
    return activeSessions.get();
}
\`\`\`

Khi bean được export đúng cách, client có thể đọc attribute \`ActiveSessions\` bằng \`MBeanServerConnection.getAttribute\` hoặc JConsole. Client không được ghi \`ActiveSessions\` nếu không có setter quản trị hợp lệ.

Sau bài học, bạn có thể:

1. Hiểu quy tắc JavaBeans biến \`getXxx()\` và \`isXxx()\` thành thuộc tính JMX.
2. Sử dụng \`@ManagedAttribute\` để chỉ cho phép đọc dữ liệu quản trị.
3. Phân biệt getter Java thông thường với getter thực sự được MBean exporter expose.
4. Dùng \`MBeanInfo\` và \`MBeanAttributeInfo\` kiểm tra tên, kiểu, cờ readable/writable.
5. Đọc attribute qua \`MBeanServerConnection\`, JConsole và công cụ quản trị.
6. Nhận diện nguy cơ xuất dữ liệu nhạy cảm, tính toán đắt đỏ hoặc không ổn định từ getter.
7. Kiểm thử hợp đồng read-only bằng ví dụ Spring và JUnit.

## 2. Getter Java và JMX attribute khác nhau thế nào?

Một getter theo quy ước JavaBeans là phương thức không tham số, thường có tên:

\`\`\`java
public int getActiveSessions();
public boolean isEnabled();
\`\`\`

Trong JavaBeans, \`getActiveSessions()\` tương ứng property \`activeSessions\`, còn \`isEnabled()\` tương ứng property \`enabled\`. Với JMX, metadata của MBean thường biểu diễn tên attribute là \`ActiveSessions\` và \`Enabled\` theo quy ước quản trị MBean/JavaBeans mà assembler áp dụng.

Dù code có getter, JMX client **không tự động nhìn thấy nó**. Cần có quá trình export và một cơ chế xác định interface:

- Standard MBean: interface \`SomethingMBean\` xác định getter/attribute.
- MXBean: interface MXBean định nghĩa thuộc tính với mapping Open Types.
- Spring JMX metadata: \`@ManagedAttribute\` cùng assembler/exporter phù hợp xác định getter được công khai.
- DynamicMBean: implementation tự mô tả và xử lý attribute.

\`\`\`text
Java object có getActiveSessions()
               |
      @ManagedAttribute
               |
   Spring annotation metadata
               |
         MBeanExporter
               |
          MBeanServer
               |
    ActiveSessions (read-only)
               |
     JConsole / JMX client
\`\`\`

**Nguyên tắc:** \`@ManagedAttribute\` mô tả giao diện quản trị, còn \`MBeanExporter\` đăng ký đối tượng vào \`MBeanServer\`. Annotation riêng lẻ chưa đủ tạo một MBean có thể truy cập.

## 3. Vì sao getter tạo attribute chỉ đọc?

Trong JMX, một attribute có hai chiều truy cập:

- **Read:** client dùng \`getAttribute(name, "ActiveSessions")\`.
- **Write:** client dùng \`setAttribute(name, new Attribute("ActiveSessions", value))\`.

Nếu chỉ cung cấp getter quản trị, metadata báo \`readable=true\`, \`writable=false\`. Không có đường cập nhật tương ứng trong giao diện quản trị.

Ví dụ hợp đồng:

\`\`\`text
ObjectName: training.spring:type=SessionMonitor,name=Primary

Attribute:
  Name       = ActiveSessions
  Type       = int
  Readable   = true
  Writable   = false

Client:
  getAttribute("ActiveSessions")  -> 12
  setAttribute("ActiveSessions")  -> bị từ chối
\`\`\`

Điều quan trọng là **không có setter được expose**, chứ không nhất thiết class Java hoàn toàn không có setter. Nếu class có setter chỉ dùng nội bộ nhưng assembler không expose setter, thuộc tính JMX vẫn có thể chỉ đọc. Ngược lại, nếu cấu hình exporter cho phép tất cả public setter được quản trị thì việc đánh dấu getter có thể không đủ để bảo đảm read-only. Hãy xác nhận \`MBeanInfo\` trên MBean được đăng ký.

## 4. Ví dụ Spring @ManagedResource và getter @ManagedAttribute

### 4.1. Bean chỉ công khai trạng thái

\`\`\`java
package example.jmx;

import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedResource;
import org.springframework.stereotype.Component;

import java.util.concurrent.atomic.AtomicInteger;

@Component
@ManagedResource(
    objectName = "training.spring:type=SessionMonitor,name=Primary",
    description = "Read-only session monitoring")
public class SessionMonitor {

    private final AtomicInteger activeSessions =
        new AtomicInteger();

    @ManagedAttribute(
        description = "Number of sessions currently active")
    public int getActiveSessions() {
        return activeSessions.get();
    }

    public void sessionStarted() {
        activeSessions.incrementAndGet();
    }

    public void sessionEnded() {
        activeSessions.updateAndGet(
            previous -> Math.max(0, previous - 1));
    }
}
\`\`\`

Ở đây:

- \`@ManagedResource\` mô tả resource quản trị.
- \`@ManagedAttribute\` trên \`getActiveSessions()\` cho phép Spring assembler xây dựng attribute.
- Không có \`setActiveSessions(...)\` được expose nên thuộc tính dự kiến là read-only.
- Hai method \`sessionStarted()\`, \`sessionEnded()\` cập nhật dữ liệu nội bộ nhưng không được công bố là JMX operations.
- \`AtomicInteger\` cung cấp cơ chế đọc/ghi số đếm thread-safe ở mức biến đơn.

Lưu ý: việc trừ số đếm có chặn ở 0 chỉ là hành vi mô phỏng; hệ thống thực cần quản lý lifecycle session và xử lý event trùng/mất bằng mô hình phù hợp.

### 4.2. Bật JMX export trong Spring Framework

Trong ứng dụng Spring Framework dùng Java configuration, có thể sử dụng:

\`\`\`java
package example.jmx;

import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.ComponentScan;
import org.springframework.context.annotation.EnableMBeanExport;

@Configuration
@ComponentScan(basePackageClasses = SessionMonitor.class)
@EnableMBeanExport
public class AppConfig {
}
\`\`\`

\`@EnableMBeanExport\` kích hoạt hỗ trợ export MBean dựa trên cơ chế Spring. Trong một dự án có nhiều exporter, context hoặc MBeanServer riêng, hãy cấu hình rõ server và ownership để tránh đăng ký trùng. Các tùy chọn cụ thể có thể khác theo phiên bản Spring Framework.

Một chương trình thử nghiệm:

\`\`\`java
package example.jmx;

import org.springframework.context.annotation
    .AnnotationConfigApplicationContext;

public class Main {
    public static void main(String[] args) throws Exception {
        try (var context =
                 new AnnotationConfigApplicationContext(
                     AppConfig.class)) {

            SessionMonitor monitor =
                context.getBean(SessionMonitor.class);

            monitor.sessionStarted();
            monitor.sessionStarted();

            System.out.println("JVM PID=" +
                ProcessHandle.current().pid());

            Thread.sleep(120_000);
        }
    }
}
\`\`\`

Dùng JDK phù hợp và Spring Context dependency đồng bộ phiên bản. Khi ứng dụng chạy, khởi động \`jconsole\`, chọn JVM local rồi mở tab **MBeans** để kiểm tra \`training.spring:type=SessionMonitor,name=Primary\`.

## 5. Kiểm tra metadata bằng JMX API

Đọc trực tiếp thuộc tính là bước đầu. Để chứng minh read-only, cần đọc metadata:

\`\`\`java
import java.lang.management.ManagementFactory;
import javax.management.*;

public class InspectSessionMonitor {
    public static void main(String[] args) throws Exception {
        MBeanServer server =
            ManagementFactory.getPlatformMBeanServer();

        ObjectName name = new ObjectName(
            "training.spring:type=SessionMonitor,name=Primary");

        MBeanInfo info = server.getMBeanInfo(name);

        for (MBeanAttributeInfo attr : info.getAttributes()) {
            System.out.printf(
                "%s type=%s read=%s write=%s%n",
                attr.getName(),
                attr.getType(),
                attr.isReadable(),
                attr.isWritable());
        }

        System.out.println(
            "ActiveSessions=" +
            server.getAttribute(name, "ActiveSessions"));
    }
}
\`\`\`

Chương trình \`InspectSessionMonitor\` trên dùng **platform MBeanServer trong cùng JVM**. Nếu chạy nó như một JVM riêng, nó sẽ đọc platform server của chính tiến trình \`InspectSessionMonitor\`, không phải MBeanServer của ứng dụng \`Main\`. Muốn kiểm tra tiến trình khác, dùng JConsole hoặc thiết lập một \`JMXConnector\` được phép rồi lấy \`MBeanServerConnection\` từ connector. Ngoài ra có thể tích hợp đoạn inspect vào ngay \`Main\` sau khi context khởi động.

Khi đã có kết nối tới đúng server, metadata mong đợi:

\`\`\`text
ActiveSessions type=int read=true write=false
ActiveSessions=2
\`\`\`

Tên attribute và cách biểu diễn kiểu cần kiểm tra theo assembler và phiên bản Spring cụ thể.

### 5.1. \`MBeanAttributeInfo\` là nguồn kiểm chứng

\`\`\`java
boolean readable = attr.isReadable();
boolean writable = attr.isWritable();
String type = attr.getType();
String name = attr.getName();
\`\`\`

Những cờ này là hợp đồng mà client nhìn thấy. Đừng dựa riêng vào việc class không có setter khi chưa xác minh exporter/assembler thực tế.

### 5.2. Kiểm tra bằng JConsole

Trong JConsole, mở tab MBeans và chọn MBean đã đăng ký. Attribute \`ActiveSessions\` xuất hiện với giá trị được đọc và không có cách ghi hợp lệ nếu metadata read-only. UI khác nhau theo JDK; điều có ý nghĩa nhất vẫn là \`MBeanAttributeInfo.isWritable() == false\`.

## 6. Getter boolean: \`isEnabled()\` và \`getEnabled()\`

Trong JavaBeans, boolean thường dùng:

\`\`\`java
@ManagedAttribute
public boolean isEnabled() {
    return enabled;
}
\`\`\`

hoặc:

\`\`\`java
@ManagedAttribute
public Boolean getEnabled() {
    return enabled;
}
\`\`\`

Một số quy tắc cần chú ý:

- \`isXxx()\` theo JavaBeans thường dành cho primitive \`boolean\`.
- \`getXxx()\` có thể dùng cho primitive \`boolean\` hoặc wrapper \`Boolean\`.
- Tên attribute được suy ra từ property descriptor; với getter \`isEnabled\`, tên quản trị thường là \`Enabled\`.
- Nếu vừa có \`isEnabled()\` vừa có \`getEnabled()\` với quy tắc không nhất quán, introspection có thể khó dự đoán. Chọn một mẫu thống nhất.
- Không tùy tiện đặt method dạng \`isActiveSessions()\` khi giá trị là \`int\`; đây không phải boolean getter hợp lệ.

Ví dụ:

\`\`\`java
@ManagedResource(
    objectName = "training.spring:type=Feature,name=Checkout")
public class CheckoutFeatureStatus {
    private volatile boolean enabled = true;

    @ManagedAttribute(description = "Feature switch state")
    public boolean isEnabled() {
        return enabled;
    }
}
\`\`\`

Nếu không công khai setter, MBean attribute \`Enabled\` được thiết kế chỉ đọc dù trạng thái có thể được thay đổi bởi logic nội bộ của ứng dụng.

## 7. Getter chỉ đọc không đồng nghĩa giá trị bất biến

**Read-only** nghĩa là client JMX không được ghi trực tiếp qua attribute đó. Giá trị vẫn có thể thay đổi theo trạng thái hệ thống:

\`\`\`text
T0: ActiveSessions = 1
T1: ActiveSessions = 4
T2: ActiveSessions = 2
\`\`\`

Tất cả các mốc này đều hợp lệ cho một attribute chỉ đọc. Điều phân biệt là client có thể quan sát nhưng không thể gọi \`setAttribute\` để đổi số đếm theo ý muốn.

Bảng khái niệm:

| Khái niệm | Ý nghĩa |
|---|---|
| Read-only attribute | Không có đường ghi JMX qua attribute |
| Immutable field | Giá trị không thay đổi sau khởi tạo |
| Thread-safe read | Đọc trả dữ liệu nhất quán theo cơ chế đồng bộ áp dụng |
| Cached metric | Giá trị đọc từ cache, có độ trễ cập nhật |
| Derived metric | Getter tính toán từ trạng thái khác |

Một getter quản trị nên mô tả rõ độ mới, đơn vị đo và semantics nếu nó là số liệu vận hành. Ví dụ \`getActiveSessions()\` có thể cần phân biệt session đã xác thực, session transport hoặc request đang xử lý.

## 8. Thử ghi vào read-only attribute sẽ xảy ra gì?

Client có thể cố ghi:

\`\`\`java
connection.setAttribute(
    name,
    new Attribute("ActiveSessions", 99));
\`\`\`

Với MBean thực sự công bố attribute read-only, thao tác ghi không được hỗ trợ. Tùy loại MBean, JMX implementation và đường xử lý, client nhận exception thích hợp, thường là \`AttributeNotFoundException\` khi attribute không writable. Một client nên xử lý lỗi theo hợp đồng JMX; không giả định mọi trường hợp đều trả cùng loại exception nếu implementation không thống nhất.

Test đơn giản:

\`\`\`java
import static org.junit.jupiter.api.Assertions.*;

MBeanAttributeInfo active = java.util.Arrays.stream(
    connection.getMBeanInfo(name).getAttributes())
    .filter(attr -> attr.getName().equals("ActiveSessions"))
    .findFirst()
    .orElseThrow();

assertTrue(active.isReadable());
assertFalse(active.isWritable());

assertThrows(
    AttributeNotFoundException.class,
    () -> connection.setAttribute(
        name, new Attribute("ActiveSessions", 99)));
\`\`\`

Với test của ứng dụng cụ thể, xác nhận exception thực tế từ exporter đang dùng. Một assertion trên \`isWritable()\` thường ổn định hơn so với phụ thuộc duy nhất vào thông điệp exception.

## 9. Điều gì xảy ra khi thêm setter?

Giả sử sau này class có:

\`\`\`java
@ManagedAttribute
public void setActiveSessions(int count) {
    activeSessions.set(count);
}
\`\`\`

Nếu assembler ghép getter và setter thành cùng một attribute, metadata có thể trở thành:

\`\`\`text
ActiveSessions:
  readable=true
  writable=true
\`\`\`

Như vậy client có thể thay đổi bộ đếm qua JMX. Điều này mở ra **một khả năng quản trị mới**, có thể nguy hiểm nếu giá trị phản ánh dữ liệu nghiệp vụ cần được tính từ sự kiện thay vì chỉnh tay.

Không thêm setter quản trị chỉ để “JConsole cho sửa cho tiện”. Nếu cần reset có kiểm soát, hãy dùng operation được định nghĩa rõ:

\`\`\`java
@ManagedOperation(
    description = "Reset demonstration session count")
public void resetDemoCount() {
    activeSessions.set(0);
}
\`\`\`

Một operation có tên mô tả ý nghĩa nghiệp vụ và có thể được bảo vệ/audit theo chính sách phù hợp. Tuy nhiên, việc đánh dấu operation cũng không tự cung cấp authorization; phân quyền cần thiết kế ở tầng thích hợp.

## 10. Khi nào nên dùng @ManagedAttribute, khi nào dùng @ManagedOperation?

| Yêu cầu | Gợi ý | Lý do |
|---|---|---|
| Đọc số lượng session hiện tại | Getter \`@ManagedAttribute\` | Số liệu trạng thái |
| Đọc phiên bản ứng dụng | Getter read-only | Thông tin gần như bất biến |
| Đọc số kết nối đang mở | Getter read-only | Quan sát |
| Bật/tắt một tính năng có kiểm soát | Getter và setter hoặc operation | Cần cân nhắc quyền và audit |
| Reset statistics | \`@ManagedOperation\` | Hành động rõ ràng |
| Clear cache | \`@ManagedOperation\` | Có tác dụng phụ và cần kiểm soát |
| Restart worker | \`@ManagedOperation\` | Hành động vận hành nhạy cảm |

Một attribute thích hợp khi dữ liệu có nghĩa như **trạng thái**. Một operation thích hợp khi client yêu cầu **hành động**. Giữ getter rẻ và ít tác dụng phụ; tránh đặt logic vận hành làm thay đổi dữ liệu trong getter.

## 11. Metadata và tính tương thích của hợp đồng JMX

Một JMX client có thể phụ thuộc:

\`\`\`text
ObjectName:
  training.spring:type=SessionMonitor,name=Primary
Attribute:
  ActiveSessions
Type:
  int
Readable:
  true
Writable:
  false
\`\`\`

Đổi tên getter có thể đổi tên attribute nếu metadata ánh xạ theo JavaBeans. Chuyển từ \`int\` sang \`String\`, đổi đơn vị đo hoặc đổi ý nghĩa số liệu cũng có thể phá dashboard/script dù code Java biên dịch thành công.

Để bảo vệ hợp đồng:

1. Đặt ObjectName có quy ước ổn định.
2. Đặt tên attribute mô tả rõ ý nghĩa.
3. Giữ kiểu và đơn vị đo nhất quán.
4. Kiểm thử metadata qua \`MBeanServerConnection\`.
5. Không thêm writable access ngoài ý định.
6. Nếu thay đổi có chủ đích, ghi chú migration và cập nhật client.
7. Cẩn trọng khi thay assembler hoặc exporter vì tập attribute được expose có thể đổi.

\`MBeanInfo\` và \`MBeanAttributeInfo\` nên được xem như API contract của công cụ quản trị.

## 12. Hiệu năng và an toàn trong getter quản trị

Không phải getter nào cũng phù hợp để export. Một công cụ monitoring có thể gọi getter liên tục, thậm chí nhiều client đọc đồng thời.

### 12.1. Tránh getter quá đắt

Không nên:

\`\`\`java
@ManagedAttribute
public long getTotalRecords() {
    return repository.countAllRecordsWithFullScan();
}
\`\`\`

Nếu phương thức thực hiện truy vấn toàn bảng, mỗi lần JConsole hoặc collector đọc attribute có thể gây tải lớn. Cân nhắc:

\`\`\`java
private final java.util.concurrent.atomic.AtomicLong
    cachedTotal = new java.util.concurrent.atomic.AtomicLong();

@ManagedAttribute
public long getTotalRecords() {
    return cachedTotal.get();
}
\`\`\`

Việc cập nhật \`cachedTotal\` nên có quy tắc riêng và mô tả độ trễ của số liệu.

### 12.2. Không trả dữ liệu nhạy cảm

Không công khai password, access token, session identifier, email hoặc dữ liệu cá nhân không cần thiết. Các công cụ JMX có thể có quyền đọc rộng; data classification và access control vẫn cần được xem xét.

### 12.3. Dữ liệu đồng thời

Nếu getter đọc nhiều biến liên quan, snapshot có thể không nhất quán:

\`\`\`java
public String getSummary() {
    return "pending=" + pending + ",completed=" + completed;
}
\`\`\`

Nếu hai biến thay đổi độc lập, kết quả có thể trộn dữ liệu ở hai thời điểm khác nhau. Dùng một snapshot bất biến hoặc cơ chế đồng bộ tương ứng nếu hợp đồng yêu cầu nhất quán.

### 12.4. Không gây side effect

Getter không nên reset counter, xóa cache, gửi message hoặc gọi API ngoài không cần thiết. Một lần refresh JConsole không nên vô tình thay đổi trạng thái ứng dụng.

## 13. Kiểm thử bằng Spring ApplicationContext

Một bài kiểm thử integration nên xác minh bean được export và attribute thực sự chỉ đọc. Ví dụ:

\`\`\`java
import org.junit.jupiter.api.Test;
import org.springframework.context.annotation
    .AnnotationConfigApplicationContext;

import javax.management.*;
import java.lang.management.ManagementFactory;
import java.util.Arrays;

import static org.junit.jupiter.api.Assertions.*;

class SessionMonitorJmxTest {

    @Test
    void activeSessionsIsReadOnly() throws Exception {
        try (var context =
                new AnnotationConfigApplicationContext(
                    AppConfig.class)) {

            MBeanServer server =
                ManagementFactory.getPlatformMBeanServer();

            ObjectName name = new ObjectName(
                "training.spring:type=SessionMonitor,name=Primary");

            assertTrue(server.isRegistered(name));

            MBeanAttributeInfo attr = Arrays.stream(
                server.getMBeanInfo(name).getAttributes())
                .filter(a -> a.getName().equals("ActiveSessions"))
                .findFirst()
                .orElseThrow();

            assertEquals("int", attr.getType());
            assertTrue(attr.isReadable());
            assertFalse(attr.isWritable());

            SessionMonitor monitor =
                context.getBean(SessionMonitor.class);
            monitor.sessionStarted();

            assertEquals(
                1,
                server.getAttribute(name, "ActiveSessions"));
        }
    }
}
\`\`\`

Ví dụ giả định exporter dùng platform MBeanServer và test chạy cô lập để không có registration trùng. Trong hệ thống nhiều ApplicationContext hoặc chạy test song song, nên inject MBeanServer riêng và kiểm tra chính xác server được exporter dùng.

**Không dùng một test chỉ gọi \`monitor.getActiveSessions()\` để kết luận JMX đã expose attribute.** Phần quan trọng là client truy cập qua \`MBeanServer\`.

## 14. Lỗi thường gặp

| Hiện tượng | Nguyên nhân khả dĩ | Hướng kiểm tra |
|---|---|---|
| Getter chạy trong code nhưng JConsole không thấy | Chưa export MBean hoặc annotation assembler không hoạt động | Kiểm tra \`@EnableMBeanExport\`, exporter, ObjectName |
| MBean có nhưng thiếu \`ActiveSessions\` | Getter chưa được expose hoặc naming không như dự kiến | Đọc \`MBeanInfo\` và metadata |
| Attribute trở thành writable ngoài ý định | Setter cũng được export | Kiểm tra \`isWritable()\` và assembler |
| \`getAttribute\` báo \`AttributeNotFoundException\` | Sai tên hoặc kết nối sai server | Xem danh sách attributes thực tế |
| JConsole hiển thị giá trị cũ | Getter trả cache hoặc state chưa cập nhật | Xác nhận semantics, cache refresh |
| Getter gây chậm ứng dụng | Tính toán/truy vấn đắt mỗi lần đọc | Dùng snapshot/counter cập nhật sẵn |
| Cùng ObjectName bị trùng | Nhiều exporter hoặc context | Xác định owner và registration policy |
| Remote JMX không đọc được | Connector/TLS/auth/network | Kiểm tra remote layer độc lập |

Một lỗi quan trọng trong học Spring JMX là nghĩ rằng \`@ManagedAttribute\` tự bật remote access. Annotation chỉ mô tả attribute; đường truy cập từ xa nằm ở JMX connector/management agent.

## 15. Bài tập thực hành

### Bài tập A — Hai getter chỉ đọc

Tạo \`ApplicationStatus\` với hai getter:

\`\`\`java
@ManagedAttribute
public int getRunningJobs() { ... }

@ManagedAttribute
public long getUptimeSeconds() { ... }
\`\`\`

Export MBean, dùng JConsole hoặc \`MBeanServerConnection\` xác nhận cả hai có \`readable=true\`, \`writable=false\`. Quan sát \`UptimeSeconds\` thay đổi dù thuộc tính chỉ đọc.

### Bài tập B — Thêm setter ngoài ý định

Thêm \`@ManagedAttribute\` vào setter của \`RunningJobs\`. Đọc lại \`MBeanInfo\` và giải thích vì sao API JMX thay đổi. Sau đó bỏ annotation setter và xác minh trở lại read-only.

### Bài tập C — Boolean getter

Tạo \`isHealthy()\` và \`getHealthy()\` trong hai class khác nhau. Kiểm tra tên attribute qua metadata, phân biệt primitive \`boolean\` với wrapper \`Boolean\`. Tránh tạo cả hai getter trong cùng class nếu không có mục tiêu đặc biệt.

### Bài tập D — Kiểm tra getter đắt

Tạo getter cố ý \`Thread.sleep(200)\` trong môi trường lab rồi đo thời gian đọc qua JMX. Thay bằng giá trị cache và so sánh. Rút ra yêu cầu hiệu năng của API quản trị được polling.

### Bài tập E — Contract test

Viết test JUnit 5 xác minh:
- ObjectName được đăng ký.
- Attribute có tên \`ActiveSessions\`, kiểu \`int\`.
- Readable true, writable false.
- Sau \`sessionStarted()\`, JMX đọc giá trị mới.
- Một yêu cầu ghi không hợp lệ bị từ chối theo hợp đồng của MBean.

## 16. Câu hỏi tự kiểm tra

1. Vì sao getter Java thường không tự động trở thành JMX attribute?
2. \`@ManagedAttribute\` cần phối hợp với thành phần Spring nào?
3. Thế nào là một JMX attribute read-only?
4. Thuộc tính chỉ đọc có thể thay đổi giá trị trong thời gian chạy không?
5. Làm thế nào xác nhận \`isWritable=false\`?
6. Điều gì xảy ra nếu setter cũng được expose?
7. \`isEnabled()\` khác \`getActiveSessions()\` ở quy tắc JavaBeans nào?
8. Vì sao getter quản trị nên nhẹ và không có side effect?
9. Vì sao nên kiểm tra qua \`MBeanServerConnection\` thay vì chỉ gọi method trực tiếp?
10. Annotation trên getter có mở remote JMX connector không?

## 17. Tài liệu tham khảo

- Spring Framework Reference — JMX: https://docs.spring.io/spring-framework/reference/integration/jmx.html
- Spring Framework API — \`@ManagedAttribute\`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/export/annotation/ManagedAttribute.html
- Spring Framework API — \`@ManagedResource\`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/export/annotation/ManagedResource.html
- Java SE 21 API — \`MBeanAttributeInfo\`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanAttributeInfo.html
- Java SE 21 API — \`MBeanServerConnection\`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanServerConnection.html

**Ghi nhớ:** getter được công khai bằng \`@ManagedAttribute\` cùng exporter và assembler phù hợp tạo ra một JMX attribute có thể đọc. Khi không có setter quản trị tương ứng, attribute là read-only. Hãy kiểm chứng cờ \`readable/writable\` trên MBean thực tế và bảo đảm getter nhanh, an toàn, có ngữ nghĩa rõ ràng.
