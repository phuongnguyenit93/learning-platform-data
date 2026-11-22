# Đăng ký và hủy đăng ký MBean trong MBeanServer

## Mục tiêu học tập

Sau bài này, bạn có thể giải thích vai trò của `MBeanServer` trong Java Management Extensions (JMX); thực hiện `registerMBean` và `unregisterMBean`; dùng `ObjectName` để định danh đúng đối tượng; kiểm tra trạng thái đăng ký; xử lý các lỗi thường gặp; và tổ chức vòng đời quản lý MBean khi tích hợp với Spring Framework.

## 1. MBeanServer là nơi đăng ký các MBean

Trong JMX, MBean là thành phần công bố các thuộc tính (attributes), thao tác (operations) và đôi khi các notifications phục vụ giám sát, vận hành ứng dụng Java. `MBeanServer` đóng vai trò **registry và điểm truy cập quản lý**: mỗi MBean được đăng ký dưới một `ObjectName`, sau đó JMX client có thể truy vấn đối tượng đó qua API của server.

Các bước điển hình:

1. Tạo đối tượng đáp ứng hợp đồng JMX (Standard MBean, MXBean, Dynamic MBean hoặc dạng hợp lệ khác).
2. Chọn `MBeanServer` sẽ chứa đối tượng.
3. Tạo `ObjectName` phân biệt đối tượng với các MBean khác.
4. Gọi `registerMBean(instance, objectName)`.
5. Trong lúc ứng dụng chạy, kiểm tra và thao tác với đối tượng thông qua server.
6. Khi không còn quản lý đối tượng, gọi `unregisterMBean(objectName)` hoặc dùng cơ chế quản lý vòng đời tương ứng.

Một instance chỉ có thể được đăng ký dưới một tên cụ thể trong cùng `MBeanServer` mà không gây trùng tên. Các MBean cùng loại vẫn có thể cùng tồn tại nếu có `ObjectName` khác nhau.

**Phân biệt quan trọng:** tạo một Spring bean trong `ApplicationContext` không tự động bảo đảm bean đó đã trở thành JMX MBean. `MBeanServer` là registry của JMX; Spring IoC container là registry của bean Spring. `MBeanExporter` có thể kết nối hai cơ chế.

## 2. Chuẩn bị một Standard MBean đơn giản

Ví dụ khai báo hợp đồng quản lý bộ đếm tác vụ:

**TaskCounterMBean.java**

```java
package com.example.jmx;

public interface TaskCounterMBean {
    long getCompletedCount();
    void increment();
    void reset();
}
```

**TaskCounter.java**

```java
package com.example.jmx;

import java.util.concurrent.atomic.AtomicLong;

public class TaskCounter implements TaskCounterMBean {
    private final AtomicLong completed = new AtomicLong();

    @Override
    public long getCompletedCount() {
        return completed.get();
    }

    @Override
    public void increment() {
        completed.incrementAndGet();
    }

    @Override
    public void reset() {
        completed.set(0L);
    }
}
```

Với Standard MBean, lớp `TaskCounter` triển khai giao diện `TaskCounterMBean` theo quy ước JMX. Khi đăng ký hợp lệ, thuộc tính `CompletedCount` sẽ ở trạng thái read-only; `increment` và `reset` sẽ là operations. Dùng `AtomicLong` vì các lời gọi JMX và luồng xử lý ứng dụng có thể đồng thời truy cập bộ đếm.

## 3. Đăng ký bằng registerMBean

Có thể lấy platform MBean server đã được JVM cung cấp:

```java
MBeanServer server = ManagementFactory.getPlatformMBeanServer();
```

Ví dụ đăng ký hoàn chỉnh:

```java
package com.example.jmx;

import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import javax.management.ObjectInstance;
import javax.management.ObjectName;

public class RegisterDemo {
    public static void main(String[] args) throws Exception {
        MBeanServer server = ManagementFactory.getPlatformMBeanServer();

        TaskCounter counter = new TaskCounter();
        ObjectName name = new ObjectName(
                "com.example.jmx:type=TaskCounter,name=main"
        );

        ObjectInstance registered = server.registerMBean(counter, name);

        System.out.println("Registered: " + registered.getObjectName());
        counter.increment();

        Object value = server.getAttribute(name, "CompletedCount");
        System.out.println("CompletedCount: " + value);

        server.invoke(name, "reset", new Object[0], new String[0]);
        System.out.println(server.getAttribute(name, "CompletedCount"));
    }
}
```

Giải thích:

- `ManagementFactory.getPlatformMBeanServer()` lấy platform MBean server, thường là lựa chọn tự nhiên để công cụ JVM quản trị nhìn thấy các MBean ứng dụng.
- `ObjectName` là định danh JMX, có cấu trúc `domain:key=value,...`. Ở đây, domain là `com.example.jmx` và các key phân biệt loại với instance.
- `registerMBean` kiểm tra object là MBean hợp lệ và thêm nó vào server. Nếu thành công, kết quả là `ObjectInstance`, chứa class name và object name theo thông tin JMX.
- `getAttribute` và `invoke` truy cập hợp đồng MBean qua server, không cần truyền reference Java của đối tượng cho JMX client.

Trong phạm vi một server, `ObjectName` phải duy nhất. Hai object khác nhau không thể cùng dùng `com.example.jmx:type=TaskCounter,name=main` tại một thời điểm. Ngược lại, `name=worker-1` và `name=worker-2` có thể dùng để đại diện hai bộ đếm độc lập.

## 4. Kiểm tra trước khi đăng ký

`MBeanServer.isRegistered(ObjectName)` cho biết một tên hiện có trong registry hay chưa:

```java
if (!server.isRegistered(name)) {
    server.registerMBean(counter, name);
}
```

Tuy vậy, **kiểm tra trước không biến thao tác thành nguyên tử**. Một thread khác có thể đăng ký cùng tên sau `isRegistered` nhưng trước `registerMBean`. Do đó, cần xử lý `InstanceAlreadyExistsException` tại lời gọi đăng ký nếu có cạnh tranh:

```java
import javax.management.InstanceAlreadyExistsException;

try {
    server.registerMBean(counter, name);
} catch (InstanceAlreadyExistsException duplicate) {
    // Tên đã có chủ sở hữu trong MBeanServer.
    // Quyết định rõ: giữ MBean hiện có, báo lỗi hoặc chọn tên khác.
    throw duplicate;
}
```

Không nên tự ý gọi `unregisterMBean` để chiếm lại tên nếu bạn không biết đối tượng hiện tại do thành phần nào sở hữu. Trong ứng dụng chứa nhiều context hoặc library, hành động đó có thể gỡ MBean của module khác.

Có thể dùng `queryNames(ObjectName pattern, QueryExp query)` để tìm các MBean theo mẫu, ví dụ:

```java
ObjectName pattern =
        new ObjectName("com.example.jmx:type=TaskCounter,*");

for (ObjectName match : server.queryNames(pattern, null)) {
    System.out.println(match.getCanonicalName());
}
```

Khi tạo `ObjectName` động từ dữ liệu có ký tự đặc biệt, sử dụng cú pháp quote/escape được JMX hỗ trợ và tránh tự ghép chuỗi không kiểm soát.

## 5. Hủy đăng ký bằng unregisterMBean

MBean ngừng được cung cấp qua registry sau khi gọi:

```java
server.unregisterMBean(name);
```

Ví dụ:

```java
if (server.isRegistered(name)) {
    server.unregisterMBean(name);
}
```

`unregisterMBean` chỉ xóa mục đăng ký JMX. Nó **không có nghĩa** đối tượng Java bị hủy, thread đã dừng hay tài nguyên ngoài (socket, executor, database connection) tự đóng. Nếu ứng dụng vẫn còn reference tới `TaskCounter`, object vẫn tồn tại như bình thường và method Java trực tiếp vẫn hoạt động.

Tương tự như thao tác đăng ký, `isRegistered` trước khi unregister chỉ là kiểm tra tại một thời điểm. Nếu đối tượng đã bị gỡ bởi thread khác, `unregisterMBean` có thể ném `InstanceNotFoundException`. Hãy thiết kế chính sách cleanup theo ownership và vòng đời, thay vì dựa vào giả định kiểm tra trước là đủ.

```java
import javax.management.InstanceNotFoundException;

try {
    server.unregisterMBean(name);
} catch (InstanceNotFoundException alreadyGone) {
    // Chỉ bỏ qua nếu hành vi "đã hủy" được xem là hợp lệ
    // trong chính sách cleanup của thành phần này.
}
```

Với MBean có lifecycle callbacks (`MBeanRegistration`), server có thể gọi `preRegister`, `postRegister`, `preDeregister` và `postDeregister` tại các giai đoạn tương ứng. Đây là hook của JMX, không thay thế việc đóng tài nguyên theo vòng đời ứng dụng.

## 6. Mẫu quản lý vòng đời an toàn trong Java thuần

Khi một thành phần tạo ra MBean thì thành phần đó cũng nên chịu trách nhiệm dọn dẹp. Sử dụng `try/finally` trong bài thực hành để bảo đảm unregister nếu đã đăng ký thành công.

```java
package com.example.jmx;

import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import javax.management.ObjectName;

public class LifecycleDemo {
    public static void main(String[] args) throws Exception {
        MBeanServer server = ManagementFactory.getPlatformMBeanServer();
        ObjectName name = new ObjectName(
                "com.example.jmx:type=TaskCounter,name=demo"
        );
        TaskCounter counter = new TaskCounter();

        boolean registered = false;
        try {
            server.registerMBean(counter, name);
            registered = true;

            counter.increment();
            System.out.println(
                    server.getAttribute(name, "CompletedCount")
            );
        } finally {
            if (registered) {
                server.unregisterMBean(name);
            }
        }
    }
}
```

Biến `registered` giúp không gỡ một MBean trùng tên do thành phần khác đăng ký trước đó: nếu `registerMBean` ném lỗi, `registered` vẫn là `false`. Trong ví dụ này, giả định không có bên khác tự thay thế hoặc gỡ đăng ký cùng `ObjectName` trong lúc chạy; ứng dụng thực cần quy ước ownership đủ chặt.

Nếu MBean cần tồn tại suốt vòng đời service, nơi đăng ký có thể là startup của service; nơi unregister là shutdown hook hoặc callback dừng component. Đừng dùng `try/finally` theo phạm vi request nếu MBean dự kiến được truy cập lâu dài.

## 7. Tích hợp Spring Framework với MBeanExporter

Spring cung cấp `org.springframework.jmx.export.MBeanExporter` để quản lý thao tác đăng ký/export các đối tượng quản lý. Đây thường là cách phù hợp khi đối tượng là Spring bean và cần cùng lifecycle với `ApplicationContext`.

Ví dụ cấu hình Spring Framework thuần:

```java
package com.example.jmx;

import java.lang.management.ManagementFactory;
import java.util.Map;

import javax.management.MBeanServer;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.export.MBeanExporter;

@Configuration
public class JmxConfiguration {
    @Bean
    public TaskCounter taskCounter() {
        return new TaskCounter();
    }

    @Bean
    public MBeanServer mBeanServer() {
        return ManagementFactory.getPlatformMBeanServer();
    }

    @Bean
    public MBeanExporter mBeanExporter(
            TaskCounter taskCounter,
            MBeanServer mBeanServer) {
        MBeanExporter exporter = new MBeanExporter();
        exporter.setServer(mBeanServer);
        exporter.setBeans(Map.of(
                "com.example.jmx:type=TaskCounter,name=main",
                taskCounter
        ));
        return exporter;
    }
}
```

Khi Spring khởi tạo context, `MBeanExporter` thực hiện xuất/đăng ký các MBean đã cấu hình; khi context được đóng đúng vòng đời, exporter hỗ trợ hủy đăng ký các MBean thuộc phạm vi quản lý của nó. Không cần tự gọi `server.registerMBean` cho cùng một object và `ObjectName` nếu đã dùng exporter, nếu không sẽ tạo tranh chấp đăng ký.

**Lưu ý Spring Boot:** JMX exposure có thể được điều khiển qua cấu hình và auto-configuration của Boot. Kiểm tra những gì context đang tạo trước khi định nghĩa thêm `MBeanServer` hoặc `MBeanExporter`. Với Spring Framework thuần, ví dụ trên tạo các bean cần thiết ngay trong cấu hình.

### Đăng ký thủ công theo vòng đời Spring

Khi cần toàn quyền điều khiển `registerMBean` và `unregisterMBean`, có thể dùng lifecycle callback. Ví dụ bean quản lý registration thông qua `InitializingBean` và `DisposableBean`:

```java
package com.example.jmx;

import javax.management.MBeanServer;
import javax.management.ObjectName;

import org.springframework.beans.factory.DisposableBean;
import org.springframework.beans.factory.InitializingBean;

public class TaskCounterRegistration
        implements InitializingBean, DisposableBean {

    private final MBeanServer server;
    private final TaskCounter counter;
    private final ObjectName name;
    private boolean registered;

    public TaskCounterRegistration(
            MBeanServer server, TaskCounter counter
    ) throws Exception {
        this.server = server;
        this.counter = counter;
        this.name = new ObjectName(
                "com.example.jmx:type=TaskCounter,name=manual"
        );
    }

    @Override
    public void afterPropertiesSet() throws Exception {
        server.registerMBean(counter, name);
        registered = true;
    }

    @Override
    public void destroy() throws Exception {
        if (registered) {
            server.unregisterMBean(name);
            registered = false;
        }
    }
}
```

Đăng ký bean lifecycle manager với `@Bean`, truyền hai dependency `MBeanServer` và `TaskCounter`. Các callback được Spring gọi khi bean được khởi tạo và khi context được đóng. Ví dụ có chủ ý dùng tên `name=manual` để không trùng với exporter trong ví dụ trước; khi áp dụng thực tế, chọn **một cơ chế sở hữu đăng ký** cho một MBean.

Mẫu thủ công hữu ích khi đăng ký phụ thuộc một điều kiện runtime hoặc cần kiểm soát hook đặc thù. Với trường hợp chỉ cần xuất Spring bean, `MBeanExporter` thường giảm mã quản lý vòng đời.

## 8. Các lỗi và tình huống cần xử lý

| Tình huống | Exception hoặc hiện tượng | Cách suy nghĩ |
| --- | --- | --- |
| Đăng ký `ObjectName` đã tồn tại | `InstanceAlreadyExistsException` | Kiểm tra owner của tên, không gỡ đối tượng của bên khác |
| Class không đáp ứng hợp đồng MBean | `NotCompliantMBeanException` | Kiểm tra Standard MBean interface, MXBean hoặc Dynamic MBean |
| Tên JMX sai cú pháp | `MalformedObjectNameException` khi tạo tên | Sửa domain/key/value, quote dữ liệu chứa ký tự đặc biệt |
| Gỡ đối tượng không tồn tại | `InstanceNotFoundException` | Xác định đây là lỗi lifecycle hay cleanup được phép lặp lại |
| Lời gọi MBean khi đang chạy phát sinh exception | `MBeanException`, `ReflectionException` hoặc lỗi liên quan | Kiểm tra method, signature, lỗi nghiệp vụ, metadata |
| Bean xuất qua Spring và đồng thời đăng ký thủ công | Trùng `ObjectName` | Chọn một bên chịu trách nhiệm đăng ký/hủy |
| Không thấy MBean trong JConsole | MBean chưa đăng ký, tên khác hoặc chọn nhầm JVM | Kiểm tra `isRegistered`, `queryNames` và kết nối |

Với remote JMX, thêm xác thực, giới hạn quyền truy cập và bảo vệ kết nối. Operation JMX có thể thay đổi trạng thái hệ thống, nên không mặc định xuất thao tác nguy hiểm hoặc dữ liệu nhạy cảm.

## 9. Bài thực hành và quan sát

1. Tạo `TaskCounterMBean` và `TaskCounter` theo ví dụ.
2. Đăng ký với `com.example.jmx:type=TaskCounter,name=lab`. Xác nhận `server.isRegistered(name)` trả `true`.
3. Gọi `increment()`, đọc `CompletedCount` qua `getAttribute` và kiểm tra kết quả.
4. Mở JConsole trên cùng JVM, quan sát thuộc tính và hai operation `increment`, `reset`.
5. Thử đăng ký một `TaskCounter` khác vào **cùng** `ObjectName`; ghi nhận `InstanceAlreadyExistsException`.
6. Đăng ký instance thứ hai với `name=lab2`; dùng `queryNames` tìm cả hai.
7. Hủy đăng ký `name=lab`, xác nhận `isRegistered(name)` trả `false`, còn `name=lab2` vẫn tồn tại.
8. Thử hủy đăng ký lại `name=lab`; giải thích `InstanceNotFoundException`. Dọn dẹp instance còn lại.

Các câu hỏi tự kiểm tra:

- Tại sao cùng class vẫn có thể tồn tại nhiều MBean trong cùng server?
- Tại sao `isRegistered` không đủ để bảo đảm không có lỗi do đăng ký đồng thời?
- Sau `unregisterMBean`, đối tượng Java đã bị garbage collect ngay hay chưa?
- Khi dùng `MBeanExporter`, ai nên chịu trách nhiệm hủy đăng ký?
- Spring bean name và JMX `ObjectName` khác nhau như thế nào?

## 10. Ghi nhớ

`registerMBean` thêm một đối tượng quản lý hợp lệ vào `MBeanServer` theo `ObjectName`; `unregisterMBean` loại bỏ đăng ký đó. `ObjectName` phải duy nhất trong server, trạng thái đăng ký có thể thay đổi đồng thời, và người tạo registration cần xác định rõ trách nhiệm cleanup. Trong Spring Framework, `MBeanExporter` giúp gắn việc xuất MBean với vòng đời application context; nếu chủ động đăng ký thủ công, phải bảo đảm cơ chế unregister tương ứng.
