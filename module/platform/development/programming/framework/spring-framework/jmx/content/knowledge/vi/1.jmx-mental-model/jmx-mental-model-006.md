# Quản trị trạng thái qua JMX: đọc thuộc tính, ghi thuộc tính và gọi operation

## 1. Bức tranh tư duy

JMX (Java Management Extensions) cung cấp một **giao diện quản trị đang chạy** cho ứng dụng Java. Thay vì xem đối tượng như một lớp Java thông thường, hãy xem một **MBean** (Managed Bean) như một bảng điều khiển có ba kiểu tương tác:

- **Đọc thuộc tính (read attribute):** quan sát trạng thái hiện tại mà MBean công bố. Ví dụ: \`Active\`, \`MaxConnections\`, \`ProcessedCount\`.
- **Ghi thuộc tính (write attribute):** thay đổi một thông số runtime đã được MBean cho phép chỉnh sửa. Ví dụ: đổi \`MaxConnections\` từ \`20\` thành \`30\`.
- **Gọi operation (invoke operation):** yêu cầu MBean thực hiện một hành động có tên, có thể nhận tham số và trả kết quả. Ví dụ: \`resetCounters()\`, \`refreshCache()\`.

Ba kiểu tương tác có ý nghĩa khác nhau dù đều được gửi qua cùng một \`MBeanServer\`. Thuộc tính mô tả *trạng thái có thể quan sát hoặc cấu hình*; operation thể hiện *hành vi có chủ đích*. Một giá trị chỉ đọc không tự nhiên trở thành có thể ghi chỉ vì code Java có một field tương ứng.

\`\`\`text
JMX client (JConsole / VisualVM / code JMX)
             |
             v
       MBeanServer
             |
             v
 ObjectName: com.example.app:type=WorkerControl,name=main
             |
       +-----+-----------------------+
       |                             |
 Attributes                      Operations
  Active (read)                resetCounters()
  MaxThreads (read/write)      pause()
  ProcessedCount (read)        resume()
       |                             |
       +-------------+---------------+
                     v
            Runtime service state
\`\`\`

Trong Spring Framework, cơ chế export JMX có thể bọc một Spring bean thành MBean. Vì thế, người quản trị không cần biết trực tiếp cách lấy bean từ \`ApplicationContext\`; họ tương tác qua tên JMX (\`ObjectName\`) và hợp đồng quản trị mà ứng dụng công bố.

## 2. Hợp đồng trước khi thao tác

Trước khi đọc, ghi hoặc gọi operation, cần xác định bốn thông tin:

1. **ObjectName** định danh đúng MBean, chẳng hạn \`com.example.app:type=WorkerControl,name=main\`. Đừng suy diễn từ class name; kiểm tra tên thực sự đã được export.
2. **Tên attribute hoặc operation** là tên trong metadata JMX; nó có thể khác cách viết của field/method nội bộ.
3. **Khả năng truy cập**: attribute có thể readable, writable hoặc cả hai; operation có chữ ký tham số và kiểu trả về xác định.
4. **Ý nghĩa và giới hạn nghiệp vụ**: ghi giá trị nào là hợp lệ, một operation có idempotent không, thao tác có tác động đến lưu lượng đang phục vụ không.

MBean expose metadata qua \`MBeanInfo\`. Trong code, \`MBeanAttributeInfo.isReadable()\` và \`isWritable()\` cho biết khả năng đọc/ghi; \`MBeanOperationInfo\` mô tả tên và tham số operation. Metadata là bước kiểm tra kỹ thuật; tài liệu vận hành vẫn cần giải thích tác dụng thực tế.

### Attribute không giống operation

| Câu hỏi | Attribute | Operation |
|---|---|---|
| Mục đích | Xem hoặc cấu hình một phần trạng thái | Kích hoạt một hành động |
| Cách gọi JMX | \`getAttribute\`, \`setAttribute\` | \`invoke\` |
| Có tham số? | Ghi một giá trị đã khai báo kiểu | Có thể có nhiều tham số với chữ ký |
| Có thể thay đổi hệ thống? | Có, khi writable | Có thể; tùy hợp đồng operation |
| Ví dụ | Đọc \`ProcessedCount\`, ghi \`MaxThreads\` | \`resetCounters()\`, \`pause()\` |

Không nên biểu diễn hành động \`resetCounters\` như một thuộc tính boolean để “bật rồi tắt” nếu nó vốn là một lệnh. Ngược lại, cấu hình \`MaxThreads\` phù hợp hơn với writable attribute khi cần quan sát lại giá trị sau khi ghi.

## 3. Tạo ví dụ Spring export qua JMX

Ví dụ dưới đây cố tình tách lớp nghiệp vụ khỏi lớp công bố JMX. Nó biểu diễn một worker giả lập bằng trạng thái trong bộ nhớ; không kết nối đến tài nguyên thật. Các thao tác được đồng bộ đơn giản để dễ thấy thay đổi runtime.

\`\`\`java
package com.example.jmx;

import java.util.concurrent.atomic.AtomicLong;

public class WorkerRuntime {
    private volatile int maxThreads = 8;
    private volatile boolean active = true;
    private final AtomicLong processedCount = new AtomicLong();

    public int getMaxThreads() {
        return maxThreads;
    }

    public void setMaxThreads(int value) {
        if (value < 1 || value > 64) {
            throw new IllegalArgumentException("maxThreads phải từ 1 đến 64");
        }
        maxThreads = value;
    }

    public boolean isActive() {
        return active;
    }

    public long getProcessedCount() {
        return processedCount.get();
    }

    public void recordProcessed() {
        processedCount.incrementAndGet();
    }

    public void resetCounters() {
        processedCount.set(0);
    }

    public void pause() {
        active = false;
    }

    public void resume() {
        active = true;
    }
}
\`\`\`

Trong ứng dụng thực tế, cập nhật \`maxThreads\` cần được áp dụng lên executor/pool tương ứng; thay đổi field cấu hình **không tự động** thay đổi kích thước thread pool. Ở đây field đại diện cho trạng thái của ví dụ.

Dùng \`@ManagedResource\`, \`@ManagedAttribute\` và \`@ManagedOperation\` để khai báo chính xác bề mặt quản trị:

\`\`\`java
package com.example.jmx;

import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedOperation;
import org.springframework.jmx.export.annotation.ManagedResource;

@ManagedResource(
    objectName = "com.example.app:type=WorkerControl,name=main",
    description = "Runtime control for example worker"
)
public class WorkerControl {
    private final WorkerRuntime runtime;

    public WorkerControl(WorkerRuntime runtime) {
        this.runtime = runtime;
    }

    @ManagedAttribute(description = "Maximum configured worker threads")
    public int getMaxThreads() {
        return runtime.getMaxThreads();
    }

    @ManagedAttribute(description = "Change the worker thread limit")
    public void setMaxThreads(int maxThreads) {
        runtime.setMaxThreads(maxThreads);
    }

    @ManagedAttribute(description = "Whether the worker accepts work")
    public boolean isActive() {
        return runtime.isActive();
    }

    @ManagedAttribute(description = "Number of processed items")
    public long getProcessedCount() {
        return runtime.getProcessedCount();
    }

    @ManagedOperation(description = "Reset the processed counter to zero")
    public void resetCounters() {
        runtime.resetCounters();
    }

    @ManagedOperation(description = "Pause accepting new work")
    public void pause() {
        runtime.pause();
    }

    @ManagedOperation(description = "Resume accepting work")
    public void resume() {
        runtime.resume();
    }
}
\`\`\`

Ở mức hợp đồng JMX của ví dụ: \`MaxThreads\` đọc/ghi được vì có cả getter và setter được export; \`Active\` và \`ProcessedCount\` chỉ đọc vì chỉ công bố getter; \`resetCounters\`, \`pause\`, \`resume\` là operations.

Cấu hình một Spring context dùng annotation-based export:

\`\`\`java
package com.example.jmx;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableMBeanExport;

@Configuration
@EnableMBeanExport
public class JmxConfiguration {
    @Bean
    public WorkerRuntime workerRuntime() {
        return new WorkerRuntime();
    }

    @Bean
    public WorkerControl workerControl(WorkerRuntime workerRuntime) {
        return new WorkerControl(workerRuntime);
    }
}
\`\`\`

Trong Spring Framework, \`@EnableMBeanExport\` đăng ký cơ chế export cùng cách phát hiện annotation quản trị; môi trường Spring Boot có thể cung cấp cấu hình JMX riêng, vì vậy cần kiểm tra runtime thực tế trước khi bật thêm exporter để tránh đăng ký trùng. Đối tượng JMX chỉ xuất hiện khi context được khởi tạo và export thành công vào \`MBeanServer\`.

## 4. Đọc trạng thái bằng JMX client

Một client Java có thể truy cập \`MBeanServerConnection\`. Khi chạy cùng JVM, dùng \`ManagementFactory.getPlatformMBeanServer()\`; khi chạy từ process khác, connection được lấy từ \`JMXConnector\` với cấu hình truy cập tương ứng.

Ví dụ cùng JVM:

\`\`\`java
import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import javax.management.ObjectName;

MBeanServer server = ManagementFactory.getPlatformMBeanServer();
ObjectName name = new ObjectName(
    "com.example.app:type=WorkerControl,name=main"
);

boolean registered = server.isRegistered(name);
if (!registered) {
    throw new IllegalStateException("MBean chưa được đăng ký: " + name);
}

int threads = (Integer) server.getAttribute(name, "MaxThreads");
boolean active = (Boolean) server.getAttribute(name, "Active");
long count = (Long) server.getAttribute(name, "ProcessedCount");

System.out.printf(
    "maxThreads=%d, active=%s, processed=%d%n",
    threads, active, count
);
\`\`\`

Giá trị đọc là snapshot tại thời điểm call; nếu worker tiếp tục xử lý công việc, \`ProcessedCount\` có thể thay đổi ngay sau đó. Không được xem chuỗi nhiều lần \`getAttribute\` là một transaction nhất quán xuyên suốt các thuộc tính.

Trước khi dựa vào tên hoặc quyền sửa, có thể kiểm tra metadata:

\`\`\`java
import javax.management.MBeanInfo;
import javax.management.MBeanAttributeInfo;

MBeanInfo info = server.getMBeanInfo(name);
for (MBeanAttributeInfo attribute : info.getAttributes()) {
    System.out.printf(
        "%s: type=%s, readable=%s, writable=%s%n",
        attribute.getName(),
        attribute.getType(),
        attribute.isReadable(),
        attribute.isWritable()
    );
}
\`\`\`

Một client đồ họa như JConsole cũng có thể liệt kê MBean theo domain/type/name, hiển thị attributes và operations. Trước khi bấm \`set\` hoặc \`invoke\`, hãy đối chiếu ObjectName và kiểu dữ liệu mà client đang hiển thị.

## 5. Ghi thuộc tính: cấu hình phải được xác nhận

\`setAttribute\` mang cặp tên và giá trị. Với \`MaxThreads\` trong ví dụ:

\`\`\`java
import javax.management.Attribute;

server.setAttribute(name, new Attribute("MaxThreads", 16));

int observed = (Integer) server.getAttribute(name, "MaxThreads");
if (observed != 16) {
    throw new IllegalStateException(
        "Giá trị sau ghi không khớp: " + observed
    );
}
\`\`\`

Tư duy khi ghi:

1. **Đọc trước** để biết trạng thái hiện tại và đánh giá thay đổi có cần thiết không.
2. **Kiểm tra giới hạn**: ở ví dụ này \`1 <= MaxThreads <= 64\`; ứng dụng thực có thể có giới hạn tài nguyên riêng.
3. **Ghi đúng kiểu**: JMX phân biệt \`Integer\`, \`Long\`, \`Boolean\`, \`String\`, v.v. Truyền \`"16"\` (String) thay vì \`16\` (Integer) không tương đương.
4. **Đọc lại** để xác nhận trạng thái mà MBean đang công bố.
5. **Theo dõi tác động**: giảm/tăng giới hạn runtime có thể ảnh hưởng throughput hoặc độ trễ; readback thành công không chứng minh hành vi hạ tầng thực tế đã đổi.

Nếu setter ném \`IllegalArgumentException\` khi nhận giá trị \`1000\`, JMX có thể bọc lỗi ứng dụng trong \`MBeanException\` hoặc các ngoại lệ thích hợp theo cách export/adapter. Client cần ghi nhận chi tiết nguyên nhân; đừng mặc định mọi lỗi ghi là thiếu quyền.

**Phân biệt cấu hình bền vững:** thay đổi qua JMX thường tác động đến state đang chạy. Khi restart, bean có thể được dựng lại bằng giá trị từ cấu hình tĩnh. Nếu cần giữ thay đổi qua restart, hãy triển khai và công bố một cơ chế persist rõ ràng; JMX không tự động ghi ngược vào \`application.properties\` hay nguồn cấu hình.

## 6. Gọi operation: hành động có chủ đích

Để đặt counter về không:

\`\`\`java
server.invoke(
    name,
    "resetCounters",
    new Object[0],
    new String[0]
);

long afterReset = (Long) server.getAttribute(
    name, "ProcessedCount"
);
System.out.println("processedCount=" + afterReset);
\`\`\`

\`invoke\` có bốn thành phần: ObjectName đích; tên operation; mảng giá trị tham số; mảng chữ ký kiểu tương ứng. Khi không có tham số, cả hai mảng đều rỗng.

Ví dụ operation nhận tham số:

\`\`\`java
@ManagedOperation(description = "Set desired worker limit")
public void resize(int targetThreads) {
    runtime.setMaxThreads(targetThreads);
}
\`\`\`

Client gọi:

\`\`\`java
server.invoke(
    name,
    "resize",
    new Object[] { 12 },
    new String[] { "int" }
);
\`\`\`

Chữ ký JMX cho tham số primitive \`int\` là \`"int"\`. Nếu operation nhận \`java.lang.String\`, cần dùng \`"java.lang.String"\`. Client phải khớp chính xác overload và kiểu khai báo; chỉ đúng tên operation chưa đủ.

### Đừng suy diễn an toàn từ HTTP-like semantics

JMX không có sẵn quy tắc \`GET\`/ \`POST\` hay transaction như API database. Một operation \`refreshCache\` có thể tốn thời gian, \`resetCounters\` làm mất số đo đang tích lũy, \`pause\` thay đổi khả năng phục vụ. Việc gọi lặp lại có thể tạo tác dụng phụ hoặc kết quả khác nhau tùy hiện trạng. Hãy mô tả tiền điều kiện, hậu điều kiện và khả năng gọi lại cho từng operation quản trị.

Đối với \`pause()\` và \`resume()\`, kiểm tra trạng thái sau lệnh:

\`\`\`java
server.invoke(name, "pause", new Object[0], new String[0]);
boolean paused = !(Boolean) server.getAttribute(name, "Active");

server.invoke(name, "resume", new Object[0], new String[0]);
boolean resumed = (Boolean) server.getAttribute(name, "Active");
\`\`\`

Trong ví dụ, \`Active\` là cờ mô phỏng; với worker thật, hành động pause/resume phải tích hợp cơ chế scheduler/queue và có hợp đồng rõ về các tác vụ đã nhận trước đó.

## 7. Lỗi và tình huống vận hành thường gặp

| Tình huống | Dấu hiệu thường gặp | Cách xử lý |
|---|---|---|
| Sai ObjectName | \`InstanceNotFoundException\` | Liệt kê MBeans đã đăng ký, dùng ObjectName chính xác |
| Attribute không tồn tại | \`AttributeNotFoundException\` | Đọc \`MBeanInfo\`, kiểm tra getter được export và tên JMX |
| Cố ghi attribute chỉ đọc | \`AttributeNotFoundException\` hoặc lỗi ghi tương ứng | Kiểm tra \`isWritable()\`, thiết kế lại hợp đồng nếu cần |
| Sai kiểu giá trị | \`InvalidAttributeValueException\` hoặc lỗi từ setter | Dùng đúng kiểu Java và giới hạn hợp lệ |
| Operation sai tên/chữ ký | \`ReflectionException\` hoặc lỗi invocation | Đọc metadata operation và chữ ký tham số |
| Lỗi bên trong business method | \`MBeanException\` hoặc exception adapter | Kiểm tra cause và log ứng dụng |
| Không thể kết nối remote | Kết nối timeout, lỗi xác thực hoặc port | Kiểm tra endpoint, network, transport và thông tin xác thực |
| Đọc lại khác giá trị vừa ghi | Có logic chuẩn hóa hoặc cập nhật đồng thời | Kiểm tra hợp đồng setter và hoạt động concorrency |

Một số loại ngoại lệ phụ thuộc vào kiểu MBean (Standard/Dynamic/Model MBean) và adapter Spring đang dùng; bảng là chỉ dẫn chẩn đoán, không phải cam kết một loại exception duy nhất cho mọi runtime.

### Tính đồng thời và nhất quán

- JMX request là lời gọi đến thành phần đang chạy; nhiều client có thể đọc, ghi hoặc invoke gần như đồng thời.
- Một setter thay đổi nhiều field cần có đồng bộ phù hợp nếu muốn trạng thái không bị lộ ở mức trung gian. \`volatile\` chỉ giải quyết visibility cho field đơn, không cung cấp transaction nhiều field.
- Nếu operation chạy lâu, nên cân nhắc mô hình trả \`jobId\` và xuất thêm thuộc tính tiến độ, thay vì khiến client chờ quá lâu hoặc không biết trạng thái.
- Trường hợp attribute trả về nhiều chỉ số liên quan, hãy thiết kế một snapshot nhất quán trong implementation nếu cần đảm bảo chúng cùng thời điểm; nhiều \`getAttribute\` riêng lẻ không đảm bảo điều này.

## 8. Biên giới bảo mật và quản trị

JMX thường cho phép truy cập năng lực rất mạnh của process Java. Khi mở kết nối quản trị từ xa, cần thiết kế xác thực, phân quyền và bảo vệ transport; không đưa cổng JMX nhạy cảm ra mạng công cộng. Ngoài ra:

- Chỉ export thuộc tính/operation cần thiết, tránh tiết lộ mật khẩu, access token hay dữ liệu cá nhân.
- Tách quyền read-only khỏi quyền có khả năng ghi hoặc invoke khi hệ thống quản trị hỗ trợ.
- Giới hạn và xác thực input ngay trong service, không chỉ dựa vào giao diện người dùng của JConsole.
- Ghi audit có ngữ cảnh cho thao tác thay đổi: MBean đích, loại thao tác, thời gian, giá trị hoặc lệnh (không lộ bí mật), kết quả.
- Đặt operation nguy hiểm dưới chính sách phù hợp với môi trường; \`shutdown()\` và \`resetAll()\` cần được cân nhắc riêng.

Phân quyền remote JMX phụ thuộc cấu hình connector, cơ chế authentication/authorization và nền tảng triển khai; annotation \`@ManagedOperation\` tự nó không định nghĩa quyền truy cập.

## 9. Quy trình thực hành từng bước

Giả sử ứng dụng đã chạy với MBean \`com.example.app:type=WorkerControl,name=main\`:

1. **Khám phá:** mở JConsole, kết nối JVM, vào tab MBeans và tìm ObjectName này.
2. **Quan sát:** đọc \`MaxThreads\`, \`Active\`, \`ProcessedCount\`; ghi lại snapshot trước khi thay đổi.
3. **Xác minh metadata:** \`MaxThreads\` writable; \`Active\` và \`ProcessedCount\` chỉ readable; operations gồm \`resetCounters\`, \`pause\`, \`resume\`.
4. **Cấu hình runtime:** ghi \`MaxThreads = 16\`, rồi đọc lại và xác nhận \`16\`.
5. **Thực thi hành động:** gọi \`pause()\`, đọc \`Active = false\`; sau đó gọi \`resume()\`, đọc \`Active = true\`.
6. **Quản trị số đo:** gọi \`resetCounters()\` và đọc lại \`ProcessedCount\`; lưu ý worker thật có thể tăng counter ngay sau reset.
7. **Đối chiếu tác động:** với hệ thống thật, xem log/metric/throughput để xác nhận pool, scheduler hoặc service đã phản ứng như mong đợi.

Lệnh kiểm tra kỹ thuật tối thiểu bằng Java có thể biểu diễn tuần tự như sau (chạy sau khi MBean đã được export):

\`\`\`java
ObjectName target = new ObjectName(
    "com.example.app:type=WorkerControl,name=main"
);
System.out.println(server.getAttribute(target, "MaxThreads"));

server.setAttribute(target, new Attribute("MaxThreads", 16));
System.out.println(server.getAttribute(target, "MaxThreads"));

server.invoke(target, "pause", new Object[0], new String[0]);
System.out.println(server.getAttribute(target, "Active"));

server.invoke(target, "resume", new Object[0], new String[0]);
System.out.println(server.getAttribute(target, "Active"));
\`\`\`

## 10. Tự kiểm tra hiểu biết

**Tình huống A.** MBean có \`getProcessedCount()\` nhưng không có setter được export. Client cố \`setAttribute("ProcessedCount", 0)\`. Vì sao không nên dùng cách này để reset?  
*Gợi ý:* \`ProcessedCount\` là read-only; reset là hành vi có tác dụng phụ nên cần operation có tên và hợp đồng rõ, chẳng hạn \`resetCounters()\`.

**Tình huống B.** \`setAttribute("MaxThreads", 16)\` thành công, nhưng thread pool thực tế vẫn có tám worker. Điều đó chứng minh điều gì?  
*Gợi ý:* Bean đang lưu một cấu hình, chưa chắc đã thực thi thay đổi lên tài nguyên runtime. Cần nối setter đến pool và xác minh trạng thái hệ thống thật.

**Tình huống C.** Hai lần \`getAttribute("ProcessedCount")\` trả 105 và 109. Có phải lỗi JMX?  
*Gợi ý:* Không. Đây là dữ liệu động; hệ thống có thể xử lý thêm công việc giữa hai lần đọc.

**Tình huống D.** Tại sao code \`invoke(name, "resize", new Object[]{12}, new String[]{"java.lang.Integer"})\` có thể không khớp operation \`resize(int)\`?  
*Gợi ý:* Chữ ký \`int\` và \`java.lang.Integer\` khác nhau; JMX cần chữ ký đúng với operation được export.

**Tình huống E.** Một script từ xa có quyền gọi \`pause()\` trong production. Cần cân nhắc điều gì?  
*Gợi ý:* Authentication, authorization, network isolation, audit, kiểm soát ảnh hưởng đến traffic và quy trình khôi phục.

## 11. Ghi nhớ

**Read attribute = quan sát**, **write attribute = thay đổi một cấu hình/state được phép**, **invoke operation = yêu cầu hệ thống thực hiện hành động**. Cả ba đều cần ObjectName đúng, hợp đồng JMX rõ và nhận thức rằng đối tượng là state đang chạy, có thể đổi đồng thời. Đọc lại sau ghi/gọi lệnh giúp xác nhận trạng thái được công bố; muốn xác nhận tác động thật, cần kiểm chứng cả thành phần nghiệp vụ phía sau MBean.