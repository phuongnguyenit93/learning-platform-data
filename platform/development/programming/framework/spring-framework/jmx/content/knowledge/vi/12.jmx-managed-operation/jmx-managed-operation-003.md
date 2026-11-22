# Tham số operation và @ManagedOperationParameter

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Khai báo một operation JMX bằng \`@ManagedOperation\` trong Spring Framework.
- Dùng \`@ManagedOperationParameter\` và \`@ManagedOperationParameters\` để mô tả tên, ý nghĩa của từng tham số.
- Phân biệt **metadata mô tả tham số** với **kiểu tham số và chữ ký Java** thực sự dùng khi gọi operation.
- Đọc \`MBeanOperationInfo\` và \`MBeanParameterInfo\` từ \`MBeanServer\` để kiểm tra metadata.
- Gọi operation có tham số bằng JConsole hoặc \`MBeanServer.invoke\` với đúng thứ tự, giá trị và signature.
- Nhận biết vấn đề về kiểu dữ liệu, overload, tác dụng phụ của operation và lỗi gọi JMX trong một ứng dụng Spring.

## 1. Operation trong Spring JMX là gì?

JMX (Java Management Extensions) cho phép các công cụ quản trị như JConsole tương tác với ứng dụng Java đang chạy. Một MBean có thể cung cấp attributes để đọc/ghi trạng thái và operations để thực hiện các hành động.

Trong Spring Framework, \`@ManagedOperation\` đánh dấu một method cần được công bố như **JMX operation**. Với annotation-based exporting, class thường được đánh dấu \`@ManagedResource\`, và \`AnnotationMBeanExporter\` hoặc \`@EnableMBeanExport\` chịu trách nhiệm đọc metadata, đăng ký bean với \`MBeanServer\`.

Ví dụ một operation giới hạn kích thước cache:

\`\`\`java
@ManagedOperation(description = "Set the maximum cache size")
public void resizeCache(int newMaxSize) {
    // Thay đổi trạng thái cache
}
\`\`\`

Khi method có tham số, công cụ JMX cần biết các thông tin: tên operation, thứ tự tham số, **kiểu Java** của từng tham số và các giá trị khi gọi. Tên biến \`newMaxSize\` trong source Java không nhất thiết tự xuất hiện như tên hiển thị có ý nghĩa ở client. Spring cung cấp \`@ManagedOperationParameter\` để bổ sung metadata mô tả tham số.

## 2. @ManagedOperationParameter dùng để làm gì?

\`@ManagedOperationParameter\` thuộc package:

\`\`\`java
import org.springframework.jmx.export.annotation.ManagedOperationParameter;
\`\`\`

Nó định nghĩa thông tin mô tả cho một tham số JMX operation, chủ yếu là:

| Thuộc tính annotation | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| \`name\` | Tên tham số hiển thị cho công cụ quản trị | \`"newMaxSize"\` |
| \`description\` | Giải thích ý nghĩa tham số | \`"Maximum number of cached entries"\` |

Khi method có nhiều tham số, \`@ManagedOperationParameters\` dùng để gom nhiều khai báo metadata theo **đúng thứ tự tham số Java**.

\`\`\`java
import org.springframework.jmx.export.annotation.ManagedOperation;
import org.springframework.jmx.export.annotation.ManagedOperationParameter;
import org.springframework.jmx.export.annotation.ManagedOperationParameters;

@ManagedOperation(description = "Adjust cache configuration")
@ManagedOperationParameters({
    @ManagedOperationParameter(
        name = "newMaxSize",
        description = "Maximum number of entries; must be positive"),
    @ManagedOperationParameter(
        name = "evictImmediately",
        description = "Whether to evict entries above the new limit now")
})
public void configureCache(int newMaxSize, boolean evictImmediately) {
    // implementation
}
\`\`\`

Trong ví dụ này, annotation thứ nhất mô tả \`int newMaxSize\`; annotation thứ hai mô tả \`boolean evictImmediately\`.

**Điều quan trọng:** \`@ManagedOperationParameter\` không thay đổi kiểu Java của phương thức, không tự chuyển giá trị, không xác thực khoảng số hợp lệ và không cấp quyền để gọi operation. Kiểu tham số vẫn được xác định từ chữ ký method: \`int\`, \`boolean\`, \`java.lang.String\`... Kiểm tra nghiệp vụ phải nằm trong implementation hoặc một tầng kiểm soát phù hợp.

## 3. Ví dụ đầy đủ với @ManagedResource và hai tham số

Tạo class \`CacheAdmin\` làm đối tượng quản trị trong ứng dụng Spring. Class này có thể được đăng ký thành Spring bean và xuất qua JMX annotation exporter.

\`\`\`java
package com.example.jmx;

import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedOperation;
import org.springframework.jmx.export.annotation.ManagedOperationParameter;
import org.springframework.jmx.export.annotation.ManagedOperationParameters;
import org.springframework.jmx.export.annotation.ManagedResource;

@ManagedResource(
        objectName = "com.example.jmx:type=CacheAdmin,name=primary",
        description = "Cache administration through Spring JMX")
public class CacheAdmin {

    private volatile int maxSize = 100;
    private volatile boolean evictionEnabled = true;

    @ManagedAttribute(description = "Maximum cache size")
    public int getMaxSize() {
        return maxSize;
    }

    @ManagedAttribute(description = "Whether eviction is enabled")
    public boolean isEvictionEnabled() {
        return evictionEnabled;
    }

    @ManagedOperation(description = "Configure cache size and eviction")
    @ManagedOperationParameters({
        @ManagedOperationParameter(
                name = "newMaxSize",
                description = "New positive capacity limit"),
        @ManagedOperationParameter(
                name = "enableEviction",
                description = "Enable or disable automatic eviction")
    })
    public String configure(int newMaxSize, boolean enableEviction) {
        if (newMaxSize <= 0) {
            throw new IllegalArgumentException(
                    "newMaxSize must be greater than zero");
        }

        this.maxSize = newMaxSize;
        this.evictionEnabled = enableEviction;
        return "Updated maxSize=" + newMaxSize
                + ", evictionEnabled=" + enableEviction;
    }
}
\`\`\`

Ở đây:

- \`@ManagedResource\` đánh dấu class là managed resource, đồng thời chỉ định JMX \`ObjectName\`.
- \`@ManagedAttribute\` công bố thông tin hiện tại qua \`MaxSize\` và \`EvictionEnabled\`.
- \`@ManagedOperation\` công bố method \`configure\` làm operation.
- \`@ManagedOperationParameters\` mô tả thứ tự hai tham số.
- Kiểu \`int\` và \`boolean\` thuộc Java method signature; client cần dùng đúng chúng khi invoke.
- Phần thân method chịu trách nhiệm validation và thay đổi trạng thái.

Hai thuộc tính ở ví dụ chỉ có getter được gắn \`@ManagedAttribute\`, do đó người vận hành đọc trạng thái hiện tại qua JMX nhưng không trực tiếp ghi các attributes này. Thay đổi được thực hiện thông qua operation có validation, phù hợp khi cần đảm bảo nhiều giá trị được cập nhật cùng một hành động.

Ví dụ dùng \`volatile\` để bảo đảm visibility của từng field. Khi cần tính nhất quán nguyên tử giữa nhiều trường, implementation phải có chiến lược đồng bộ hoặc snapshot thích hợp; hai phép gán \`volatile\` riêng lẻ không tạo thành transaction.

## 4. Đăng ký bean trong ApplicationContext

Dùng \`@EnableMBeanExport\` để bật cơ chế export annotation của Spring Framework.

\`\`\`java
package com.example.jmx;

import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableMBeanExport;

@Configuration
@EnableMBeanExport(server = "platformMBeanServer")
public class JmxConfiguration {

    @Bean
    public MBeanServer platformMBeanServer() {
        return ManagementFactory.getPlatformMBeanServer();
    }

    @Bean
    public CacheAdmin cacheAdmin() {
        return new CacheAdmin();
    }
}
\`\`\`

\`CacheAdmin\` là Spring bean được đăng ký qua \`@Bean\`, nên không cần \`@Component\` trên class. Cấu hình \`@EnableMBeanExport\` tạo hỗ trợ export theo annotation và dùng bean \`platformMBeanServer\` để đăng ký các managed resources phù hợp.

Ví dụ sử dụng platform \`MBeanServer\` để JConsole có thể kết nối đến đúng JVM. Nếu ứng dụng đã có MBean server hoặc exporter được cấu hình bởi Spring Boot, nên kiểm tra và dùng cơ chế hiện có để tránh đăng ký trùng \`ObjectName\`.

Để chạy bằng Java thuần cùng Spring context:

\`\`\`java
package com.example.jmx;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;

public class Main {
    public static void main(String[] args) throws Exception {
        try (var context = new AnnotationConfigApplicationContext(
                JmxConfiguration.class)) {
            System.out.println("PID: " + ProcessHandle.current().pid());
            System.out.println("JMX ready");
            System.in.read(); // Giữ context tồn tại khi thử JConsole.
        }
    }
}
\`\`\`

Khi context đóng, exporter do Spring quản lý sẽ thực hiện lifecycle cleanup cho các MBean thuộc trách nhiệm đăng ký của nó.

## 5. Kiểm tra metadata tham số bằng MBeanInfo

JMX API cho phép tra cứu các operation và tham số mà server thực sự công bố. Đây là cách chắc chắn hơn việc chỉ dựa trên source annotation hoặc giao diện của một client.

\`\`\`java
package com.example.jmx;

import java.lang.management.ManagementFactory;
import javax.management.MBeanInfo;
import javax.management.MBeanOperationInfo;
import javax.management.MBeanParameterInfo;
import javax.management.MBeanServer;
import javax.management.ObjectName;

public class InspectOperations {

    public static void inspect() throws Exception {
        MBeanServer server = ManagementFactory.getPlatformMBeanServer();
        ObjectName name = new ObjectName(
                "com.example.jmx:type=CacheAdmin,name=primary");

        MBeanInfo info = server.getMBeanInfo(name);

        for (MBeanOperationInfo operation : info.getOperations()) {
            System.out.printf(
                    "Operation: %s, returns %s%n",
                    operation.getName(),
                    operation.getReturnType());

            for (MBeanParameterInfo parameter : operation.getSignature()) {
                System.out.printf(
                        "  %s : %s — %s%n",
                        parameter.getName(),
                        parameter.getType(),
                        parameter.getDescription());
            }
        }
    }
}
\`\`\`

Với \`configure(int, boolean)\`, metadata dự kiến có hai tham số theo thứ tự:

\`\`\`text
Operation: configure, returns java.lang.String
  newMaxSize : int — New positive capacity limit
  enableEviction : boolean — Enable or disable automatic eviction
\`\`\`

Thông tin \`name\` và \`description\` được cung cấp từ annotation. \`type\` lấy từ chữ ký Java, không lấy từ \`description\`.

Nếu operation chưa được exporter đăng ký, \`getMBeanInfo\` sẽ không tìm thấy \`ObjectName\`. Nếu metadata tham số thiếu mô tả, hãy kiểm tra \`@ManagedOperationParameters\` có nằm cùng method với \`@ManagedOperation\`, thứ tự phần tử và assembler đang được cấu hình có thực sự đọc annotation Spring hay không.

## 6. Gọi operation có tham số bằng MBeanServer.invoke

JMX API có dạng:

\`\`\`java
Object invoke(
        ObjectName name,
        String operationName,
        Object[] params,
        String[] signature
);
\`\`\`

Ở ví dụ:

\`\`\`java
import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import javax.management.ObjectName;

MBeanServer server = ManagementFactory.getPlatformMBeanServer();

ObjectName name = new ObjectName(
        "com.example.jmx:type=CacheAdmin,name=primary");

Object result = server.invoke(
        name,
        "configure",
        new Object[]{250, false},
        new String[]{"int", "boolean"}
);

System.out.println(result);
System.out.println(server.getAttribute(name, "MaxSize"));
System.out.println(server.getAttribute(name, "EvictionEnabled"));
\`\`\`

Chú ý bốn điều kiện:

1. \`ObjectName\` phải khớp đúng tên MBean được đăng ký.
2. \`"configure"\` phải khớp tên operation.
3. \`params\` phải đúng số lượng, thứ tự và kiểu giá trị mà implementation chấp nhận. Trong Java, \`250\` và \`false\` được autobox thành \`Integer\` và \`Boolean\` trong \`Object[]\`.
4. \`signature\` là **tên kiểu Java của tham số khai báo**, ví dụ \`"int"\` và \`"boolean"\`, không phải \`"java.lang.Integer"\` và \`"java.lang.Boolean"\` khi method dùng primitive.

\`@ManagedOperationParameter(name="newMaxSize")\` không cho phép client gọi bằng một map \`{"newMaxSize": 250}\`. JMX \`invoke\` vẫn dùng mảng vị trí. Tên tham số phục vụ metadata và giao diện hiển thị, không thay đổi protocol thành named arguments.

Nếu signature bị sai hoặc thiếu, client thường nhận lỗi không tìm thấy operation/chữ ký tương ứng (có thể được phản ánh qua \`ReflectionException\` và nguyên nhân đi kèm), dù trong Java source có method cùng tên.

## 7. Gọi bằng JConsole

Khi Spring context đang chạy và MBean đã xuất:

1. Mở \`jconsole\` từ JDK phù hợp.
2. Chọn JVM theo PID được ứng dụng in ra.
3. Vào tab **MBeans** và tìm \`com.example.jmx:type=CacheAdmin,name=primary\`.
4. Mở khu vực **Operations**, tìm \`configure\`.
5. Quan sát hai tham số trong thứ tự \`newMaxSize\` và \`enableEviction\`; công cụ có thể hiển thị cả description.
6. Nhập giá trị \`250\` cho tham số kiểu \`int\` và \`false\` cho kiểu \`boolean\`.
7. Gọi operation, xem giá trị trả về nếu được hiển thị.
8. Đọc \`MaxSize\` và \`EvictionEnabled\` trong phần **Attributes** để xác minh trạng thái đã đổi.

JConsole hoặc công cụ JMX khác có thể hiển thị tên tham số khác nhau tùy cách đọc metadata, version và kiểu MBean. Một số công cụ yêu cầu nhập chuỗi rồi tự chuyển sang kiểu Java theo signature; người dùng cần kiểm tra thông báo lỗi nếu không chuyển được.

Không thử trực tiếp trên dữ liệu sản xuất khi operation có side effect. Đặc biệt, các operation như xóa cache, reset thống kê, kích hoạt job hoặc đổi cấu hình có thể ảnh hưởng request đang chạy.

## 8. Một tham số và nhiều tham số

Với method chỉ có một tham số, có thể khai báo \`@ManagedOperationParameter\` riêng:

\`\`\`java
@ManagedOperation(description = "Pause processing")
@ManagedOperationParameter(
        name = "reason",
        description = "Reason recorded for the pause")
public void pause(String reason) {
    // ...
}
\`\`\`

Khi dùng nhiều tham số, khai báo container annotation rõ ràng:

\`\`\`java
@ManagedOperation(description = "Schedule an administrative task")
@ManagedOperationParameters({
    @ManagedOperationParameter(
        name = "taskName",
        description = "Name of the task to schedule"),
    @ManagedOperationParameter(
        name = "delaySeconds",
        description = "Delay before execution, in seconds"),
    @ManagedOperationParameter(
        name = "force",
        description = "Whether to override a pending task")
})
public void scheduleTask(
        String taskName,
        long delaySeconds,
        boolean force) {
    // ...
}
\`\`\`

Thứ tự metadata phải tương ứng với thứ tự \`String taskName\`, \`long delaySeconds\`, \`boolean force\`. Nếu đổi thứ tự tham số trong method, cần cập nhật metadata tương ứng. Trình biên dịch Java không tự xác minh \`description\` có đúng ý nghĩa của tham số; điều này thuộc trách nhiệm tác giả API quản trị.

Chữ ký invoke tương ứng:

\`\`\`java
server.invoke(
        name,
        "scheduleTask",
        new Object[]{"refresh-index", 10L, false},
        new String[]{
            "java.lang.String",
            "long",
            "boolean"
        }
);
\`\`\`

Ví dụ minh họa method \`scheduleTask\` phải thực sự được khai báo và công bố trên MBean đã đăng ký; không thể gọi operation chỉ vì tên xuất hiện trong đoạn mã invoke.

## 9. Tham số phức tạp: DTO, enum, collection và giới hạn dữ liệu

Không phải mọi kiểu Java thuận tiện cho JMX client. JMX operation cần các kiểu dữ liệu mà cả MBean server và client có thể xử lý.

Các trường hợp:

| Tham số Java | Điều cần chú ý |
| --- | --- |
| Primitive \`int\`, \`long\`, \`boolean\` | Dễ hiển thị và truyền qua JMX |
| \`String\` | Phổ biến, cần kiểm tra nội dung hợp lệ |
| \`ObjectName\` | Kiểu JMX chuẩn, yêu cầu tên hợp lệ |
| \`enum\` | Standard MBean có thể đòi hỏi class ở client; MXBean có quy tắc ánh xạ sang chuỗi |
| DTO tùy biến | Standard MBean remote client có thể cần class tương ứng và khả năng serialization phù hợp |
| \`Map\`, collection | Cần hiểu kiểu cụ thể và cách JMX/MXBean ánh xạ; không nên giả định client nào cũng nhập được |
| Tham số generic không rõ kiểu | Dễ gây mơ hồ về mapping và metadata |

\`@ManagedOperationParameter\` chỉ mô tả tên/ý nghĩa tham số; nó không tự chuyển một DTO thành \`CompositeData\`. Nếu cần truyền cấu trúc dữ liệu tương thích các JMX client tổng quát, xem xét MXBean hoặc một contract quản trị dùng kiểu đơn giản.

Đối với operation cần nhiều tham số, nên ưu tiên API quản trị nhỏ, dễ hiểu và có kiểm tra giá trị. Ví dụ \`setThreshold(int percent)\` kèm description ghi rõ khoảng 0–100 dễ thao tác hơn một DTO cấu hình phức tạp nếu yêu cầu quản trị chỉ cần chỉnh ngưỡng.

## 10. Overload operation và chữ ký chính xác

Java cho phép method overload:

\`\`\`java
@ManagedOperation
@ManagedOperationParameter(name = "key", description = "Cache key")
public void evict(String key) {
    // ...
}

@ManagedOperation
@ManagedOperationParameter(name = "groupId", description = "Numeric group ID")
public void evict(int groupId) {
    // ...
}
\`\`\`

JMX có thể phân biệt các operation cùng tên bằng danh sách kiểu tham số, nhưng mức hỗ trợ và cách hiển thị các overload có thể khác giữa JMX clients và giữa các dạng MBean. Khi gọi bằng \`MBeanServer.invoke\`, signature là yếu tố quyết định:

\`\`\`java
server.invoke(
        name, "evict",
        new Object[]{"product:42"},
        new String[]{"java.lang.String"});
\`\`\`

hoặc:

\`\`\`java
server.invoke(
        name, "evict",
        new Object[]{42},
        new String[]{"int"});
\`\`\`

Trong một API quản trị có người dùng thao tác bằng JConsole, đôi khi đặt tên operation tách biệt như \`evictByKey\` và \`evictByGroupId\` dễ sử dụng hơn nhiều overload cùng tên. Đây là quyết định thiết kế để giảm nhầm lẫn, không phải giới hạn tuyệt đối của Java.

## 11. Tên tham số và mô tả có ảnh hưởng đến việc invoke không?

Không. Cần phân biệt ba lớp thông tin:

- **Java method signature**: tên method và kiểu/thứ tự tham số, quyết định cách JMX \`invoke\` tìm operation.
- **Spring annotation metadata**: \`name\`, \`description\` của \`@ManagedOperationParameter\`, giúp client/người vận hành hiểu từng tham số.
- **Giá trị runtime**: dữ liệu thực tế truyền vào, được implementation kiểm tra và sử dụng.

Ví dụ cùng Java method:

\`\`\`java
public void setLimit(int value)
\`\`\`

có thể mô tả bằng \`@ManagedOperationParameter(name="maximumItems", description="...")\`. JMX signature vẫn là \`setLimit(int)\`. Đổi metadata \`maximumItems\` thành \`limit\` không làm client phải đổi \`new String[]{"int"}\`.

Ngược lại, đổi kiểu \`int\` thành \`long\` làm signature JMX thay đổi dù annotation giữ nguyên tên tham số.

## 12. Kiểm thử annotation metadata trong ApplicationContext

Để xác minh exporter thực sự đọc và công bố metadata:

\`\`\`java
package com.example.jmx;

import javax.management.MBeanInfo;
import javax.management.MBeanOperationInfo;
import javax.management.MBeanParameterInfo;
import javax.management.MBeanServer;
import javax.management.ObjectName;
import org.junit.jupiter.api.Test;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

import static org.junit.jupiter.api.Assertions.*;

class ManagedOperationParameterTest {

    @Test
    void operationContainsParameterMetadata() throws Exception {
        try (var context = new AnnotationConfigApplicationContext(
                JmxConfiguration.class)) {

            MBeanServer server = context.getBean(MBeanServer.class);
            ObjectName name = new ObjectName(
                    "com.example.jmx:type=CacheAdmin,name=primary");

            assertTrue(server.isRegistered(name));

            MBeanInfo info = server.getMBeanInfo(name);

            MBeanOperationInfo configure = null;
            for (MBeanOperationInfo operation : info.getOperations()) {
                if ("configure".equals(operation.getName())) {
                    configure = operation;
                    break;
                }
            }

            assertNotNull(configure);
            MBeanParameterInfo[] params = configure.getSignature();

            assertEquals(2, params.length);
            assertEquals("newMaxSize", params[0].getName());
            assertEquals("int", params[0].getType());
            assertEquals("enableEviction", params[1].getName());
            assertEquals("boolean", params[1].getType());

            server.invoke(name, "configure",
                    new Object[]{250, false},
                    new String[]{"int", "boolean"});

            assertEquals(250, server.getAttribute(name, "MaxSize"));
            assertEquals(
                    false,
                    server.getAttribute(name, "EvictionEnabled"));
        }
    }
}
\`\`\`

Bài test cần dependency Spring Framework JMX và JUnit Jupiter phù hợp. Nó chứng minh ba yếu tố: Spring context đã đăng ký MBean, operation metadata có đúng thứ tự/tên/kiểu, và \`invoke\` tác động tới instance được quản lý.

Trong một test suite chạy song song, nên dùng \`MBeanServer\` riêng thay vì platform server dùng chung, hoặc đặt \`ObjectName\` riêng cho từng fixture. Các test dùng cùng \`ObjectName\` trên platform MBean server dễ xung đột \`InstanceAlreadyExistsException\` nếu lifecycle chồng nhau.

## 13. Lỗi thường gặp và hướng chẩn đoán

| Hiện tượng | Nguyên nhân thường gặp | Cách kiểm tra |
| --- | --- | --- |
| Operation không xuất hiện | Chưa có \`@ManagedOperation\`, bean chưa được export hoặc assembler không dùng annotation | Kiểm tra \`@ManagedResource\`, exporter và \`MBeanInfo\` |
| Tham số hiện tên mặc định như \`p1\`, \`p2\` | Annotation metadata không được khai báo/đọc đúng | Kiểm tra \`@ManagedOperationParameters\` và thứ tự |
| \`invoke\` báo operation không khớp | Sai tên, số lượng hoặc kiểu \`signature\` | Đọc \`MBeanOperationInfo.getSignature()\` |
| \`int\` truyền như \`"java.lang.Integer"\` trong signature | Nhầm primitive với wrapper | Dùng \`"int"\` nếu method khai báo \`int\` |
| JConsole nhập \`boolean\` thất bại | Chuỗi đầu vào không được client chuyển thành boolean hợp lệ | Dùng giá trị \`true\`/\`false\`, xem lỗi client |
| Operation thực thi nhưng giá trị không đổi như mong đợi | Implementation từ chối, async hoặc cập nhật instance khác | Kiểm tra log, cùng instance và thuộc tính sau invoke |
| \`MBeanException\` hoặc \`RuntimeMBeanException\` | Method đã ném exception | Đọc cause/target exception và điều kiện nghiệp vụ |
| \`InstanceNotFoundException\` | Sai \`ObjectName\` hoặc MBean chưa đăng ký | Kiểm tra \`isRegistered\` và \`queryNames\` |
| Gọi đúng operation nhưng nhầm JVM | JMX client kết nối server khác | Đối chiếu PID, domain và full \`ObjectName\` |

Metadata \`description\` là tài liệu dành cho công cụ quản trị, không phải ràng buộc dữ liệu. Nếu tham số yêu cầu số dương, code vẫn phải kiểm tra và ném lỗi có ý nghĩa khi nhập 0 hoặc âm.

## 14. Lưu ý với operation có side effect

Một operation JMX có thể thay đổi trạng thái ứng dụng ngay trong JVM. \`configureCache\`, \`clearCache\`, \`reloadRules\` hoặc \`resetStatistics\` đều có thể tác động tới request đang xử lý.

Thiết kế hợp đồng quản trị cần:

1. Mô tả rõ tham số, đơn vị, giá trị hợp lệ, điều kiện trước khi gọi và tác động dự kiến.
2. Kiểm tra và từ chối giá trị không hợp lệ trong method.
3. Bảo đảm thread safety và tính nhất quán nếu thay đổi nhiều field.
4. Xem xét tính idempotent: client mất kết nối sau invoke có thể không biết operation đã hoàn thành, nên retry mù có thể gây gọi lặp.
5. Kiểm soát quyền truy cập JMX, đặc biệt khi dùng kết nối từ xa.
6. Có log/metrics đủ để xác nhận operation thực hiện khi cần chẩn đoán.
7. Không đưa bí mật hoặc dữ liệu nhạy cảm vào parameter description hay attribute trả về.

Đối với tác vụ dài, có thể thiết kế operation \`startJob(...)\` trả về mã công việc rồi cung cấp attribute/operation theo dõi trạng thái; tránh buộc JConsole chờ một operation kéo dài mà không có cơ chế kiểm tra kết quả.

## 15. Bài tập thực hành

**Bài 1 — Một tham số.** Tạo \`QueueAdmin\` với \`pauseForSeconds(int seconds)\`, thêm \`@ManagedOperation\` và \`@ManagedOperationParameter(name="seconds", description="Pause duration in seconds; 1..300")\`. Kiểm tra metadata và nhập giá trị qua JConsole. Implementation phải tự kiểm tra khoảng 1–300.

**Bài 2 — Nhiều tham số.** Tạo \`MaintenanceAdmin\` với \`schedule(String taskName, long delaySeconds, boolean force)\`. Khai báo ba \`@ManagedOperationParameter\` đúng thứ tự. Gọi qua \`MBeanServer.invoke\` bằng signature \`java.lang.String\`, \`long\`, \`boolean\`; xác minh metadata đúng.

**Bài 3 — Sai signature.** Gọi method khai báo \`int\` với signature \`java.lang.Integer\` rồi đọc lỗi. Sửa thành \`int\`; giải thích khác biệt giữa kiểu primitive khai báo và wrapper của giá trị boxed truyền trong \`Object[]\`.

**Bài 4 — Metadata và validation.** Thay description của \`newMaxSize\` thành \`"Positive size between 1 and 10000"\`, nhưng không thay code validation. Thử nhập 10001 để chứng minh description không tự ràng buộc giá trị. Sau đó thêm kiểm tra khoảng trong implementation và thử lại.

**Bài 5 — ApplicationContext test.** Tạo Spring test context có \`@EnableMBeanExport\`, đọc \`MBeanInfo\` và assert số lượng, tên, kiểu, mô tả của từng tham số. Kiểm tra operation được đăng ký và có thể gọi trên đúng bean đang dùng trong ứng dụng.

## Kết luận

\`@ManagedOperation\` công bố một Java method thành JMX operation; \`@ManagedOperationParameter\` và \`@ManagedOperationParameters\` bổ sung **tên và mô tả** cho tham số để các công cụ quản trị đọc hiểu. Chúng không đổi chữ ký Java, không biến positional arguments thành named arguments và không tự xác thực giá trị. Để gọi operation chính xác, phải dùng đúng \`ObjectName\`, tên method, thứ tự giá trị và \`signature\` mà \`MBeanOperationInfo\` công bố. Trong Spring Framework, annotation exporter kết nối metadata đó với \`MBeanServer\` để JConsole và các JMX clients có thể quan sát hoặc điều khiển ứng dụng.
