# Ảnh hưởng của thứ tự khởi tạo nhiều ApplicationContext đến JMX registration policy

## 1. Bài toán: nhiều context cùng sử dụng một MBeanServer

Trong một ứng dụng Spring Framework, không phải lúc nào cũng chỉ có một `ApplicationContext`. Một hệ thống có thể có root context và servlet context, nhiều module được nạp độc lập, nhiều test context chạy cùng JVM, hoặc các context tách biệt cho những thành phần khác nhau. Mỗi context có thể tạo một `MBeanExporter` để đưa bean của mình vào Java Management Extensions (JMX).

**Vấn đề nảy sinh khi hai exporter trong hai context muốn đăng ký cùng một `ObjectName` trên cùng `MBeanServer`.** ObjectName là định danh duy nhất của một MBean trong registry đó. Ai đăng ký trước, exporter nào dùng registration policy nào và context nào bị đóng trước đều có thể làm thay đổi MBean mà client quan sát được.

Ví dụ:

```text
JVM
 |
 +-- Platform MBeanServer
 |     |
 |     +-- demo.orders:type=Monitor,name=primary
 |
 +-- ApplicationContext A
 |     +-- OrderMonitor A
 |     +-- MBeanExporter A
 |
 +-- ApplicationContext B
       +-- OrderMonitor B
       +-- MBeanExporter B

Cả A và B đều muốn dùng:
demo.orders:type=Monitor,name=primary
```

Để giải quyết, Spring `MBeanExporter` cung cấp các **registration policy** nhằm quyết định cách xử lý khi ObjectName đã được đăng ký. Tuy nhiên, một policy chỉ giải quyết **xung đột registry**, không tự quy định module nào có quyền sở hữu hay bảo đảm dữ liệu quan sát đúng với mục đích vận hành.

Mục tiêu của bài:

- Hiểu ranh giới `ApplicationContext` và `MBeanServer`.
- Phân biệt ba chính sách `FAIL_ON_EXISTING`, `IGNORE_EXISTING` và `REPLACE_EXISTING`.
- Phân tích kết quả khi thứ tự khởi tạo A/B đảo chiều.
- Hiểu sự khác biệt giữa đăng ký, chiếm quyền hiển thị và cleanup khi shutdown.
- Xây dựng chiến lược ObjectName và ownership để tránh trùng lặp.
- Thực hành quan sát trạng thái thật thay vì suy đoán chỉ từ việc ứng dụng start thành công.

## 2. ApplicationContext không phải vùng tên JMX độc lập

Mỗi Spring `ApplicationContext` có bean registry, lifecycle và `BeanFactory` riêng. Nhưng JMX dùng `MBeanServer` làm điểm quản lý các MBean.

```text
ApplicationContext A              ApplicationContext B
   bean name: monitor               bean name: monitor
          |                                 |
     MBeanExporter A                  MBeanExporter B
          |                                 |
          +-----------+---------------------+
                      |
           cùng platform MBeanServer
                      |
       ObjectName: demo:type=Monitor
```

Hai bean có thể có cùng **Spring bean name** ở hai context khác nhau mà không xung đột trực tiếp trong hai bean factory. Ngược lại, nếu exporter tạo cùng **JMX ObjectName** trong một MBeanServer thì xung đột sẽ xảy ra dù bean name, class loader hoặc module của chúng khác nhau.

Phải phân biệt ba danh tính:

| Danh tính | Thuộc phạm vi | Ví dụ |
|---|---|---|
| Spring bean name | BeanFactory/ApplicationContext | `orderMonitor` |
| JMX ObjectName | Một `MBeanServer` | `demo.orders:type=Monitor,name=primary` |
| Java object identity | Một instance trong JVM | `OrderMonitor@...` |

Các danh tính này **không tương đương**. Một ObjectName có thể trỏ tới các instance khác nhau vào các thời điểm khác nhau nếu MBean bị unregister rồi register lại. JMX client thường dựa vào ObjectName để tìm đối tượng, nên thay đổi “ai đứng sau tên” có thể gây ảnh hưởng lớn hơn một lần startup error.

## 3. Ba registration policy quan trọng

Spring có `org.springframework.jmx.support.RegistrationPolicy` với những lựa chọn thường dùng:

| Policy | Khi ObjectName chưa tồn tại | Khi ObjectName đã tồn tại | Hệ quả cần lưu ý |
|---|---|---|---|
| `FAIL_ON_EXISTING` | Đăng ký MBean mới | Báo lỗi | Phát hiện collision sớm; có thể làm context refresh thất bại |
| `IGNORE_EXISTING` | Đăng ký MBean mới | Bỏ qua registration mới | Context sau có thể khởi động bình thường nhưng MBean đang thấy vẫn thuộc context trước |
| `REPLACE_EXISTING` | Đăng ký MBean mới | Thay registration đã có theo cơ chế của exporter | Context khởi tạo sau có thể thay đối tượng đang được quản trị |

Cấu hình thường theo mẫu:

```java
import org.springframework.jmx.export.MBeanExporter;
import org.springframework.jmx.support.RegistrationPolicy;

MBeanExporter exporter = new MBeanExporter();
exporter.setRegistrationPolicy(RegistrationPolicy.FAIL_ON_EXISTING);
```

**Đừng đồng nhất registration policy với authentication hoặc authorization.** Policy quyết định hành vi khi tên JMX trùng; nó không kiểm tra liệu context A có “được phép” thay context B xét theo ranh giới nghiệp vụ hay không.

### 3.1. FAIL_ON_EXISTING

Đây là lựa chọn phù hợp khi **trùng ObjectName là lỗi cấu hình** và team muốn phát hiện ngay. Nếu context B đăng ký một ObjectName đã do A chiếm, thao tác đăng ký sẽ thất bại, thường dẫn đến exception trong quá trình exporter khởi tạo hoặc context refresh.

Ưu điểm là không âm thầm dùng sai nguồn dữ liệu. Nhược điểm là trong hệ thống có nhiều context không được thiết kế tên rõ ràng, việc startup module sau có thể bị chặn.

### 3.2. IGNORE_EXISTING

Nếu tên đã tồn tại, exporter sau không thay MBean hiện tại. Điều này giúp tránh lỗi khởi động do collision trong một số mô hình, nhưng có một sự đánh đổi: **MBean thấy trên JConsole có thể đại diện cho context được khởi tạo trước chứ không phải context vừa start**.

Nếu monitor A trả `module=A` và monitor B trả `module=B` nhưng cùng ObjectName, JMX client tiếp tục thấy A khi B dùng IGNORE. Team của B không nên kết luận “B đã được export” chỉ vì B start không lỗi.

### 3.3. REPLACE_EXISTING

Exporter sau có thể thay registration đã tồn tại. Trong thí nghiệm tuần tự, nếu A đăng ký trước rồi B thay thế, ObjectName có thể trỏ tới MBean của B.

Nhưng kết quả này phải được hiểu như **chuyển đối tượng đang đứng sau tên** chứ không phải cơ chế “merge hai monitor”. Những JMX client đã cache metadata, trạng thái hoặc subscription có thể cần làm mới. Nếu hai MBean có hợp đồng khác nhau, một ObjectName ổn định không bảo đảm `MBeanInfo` vẫn giữ nguyên.

Không dùng REPLACE như cách sửa lỗi trùng tên khi chưa biết quyền sở hữu MBean. Thay platform MBean hoặc MBean của module khác có thể làm mất khả năng quan sát của thành phần đó.

## 4. Ma trận thứ tự khởi tạo: A rồi B hoặc B rồi A

Giả sử cả hai context dùng cùng MBeanServer và cùng ObjectName `demo:type=Status`. MBean A trả `Source=A`, MBean B trả `Source=B`.

### 4.1. A và B đều FAIL_ON_EXISTING

```text
Khởi tạo A -> A đăng ký thành công
Khởi tạo B -> B gặp collision và báo lỗi
MBean hiện hữu -> A
```

Nếu đổi thứ tự:

```text
Khởi tạo B -> B đăng ký thành công
Khởi tạo A -> A gặp collision và báo lỗi
MBean hiện hữu -> B
```

Như vậy, cùng source code và cùng policy nhưng **context được khởi tạo trước quyết định ai thắng**, còn context đến sau gặp lỗi. Điều này lý giải các lỗi chỉ xuất hiện khi thay đổi thứ tự startup giữa các module hoặc khi chạy integration tests.

### 4.2. A và B đều IGNORE_EXISTING

```text
A trước, B sau -> A đăng ký; B bỏ qua -> JMX thấy A
B trước, A sau -> B đăng ký; A bỏ qua -> JMX thấy B
```

Cả hai context có thể chạy mà không lỗi collision rõ ràng, nhưng kết quả quan sát phụ thuộc vào thứ tự khởi tạo. Đây là lỗi nguy hiểm trong monitoring: dashboard có thể đang đọc số liệu của một module khác với module tưởng rằng đã được export.

### 4.3. A và B đều REPLACE_EXISTING

```text
A trước, B sau -> B thay A -> JMX thấy B
B trước, A sau -> A thay B -> JMX thấy A
```

Trong quá trình tuần tự và không có tác nhân khác, context **đăng ký sau** thường quyết định instance cuối cùng. Với khởi tạo song song, kết quả còn phụ thuộc vào thời điểm thực tế của các thao tác đăng ký. Không suy đoán “thứ tự tạo bean” từ danh sách trong configuration là tương đương thời điểm registry hoàn tất.

### 4.4. Hai context dùng policy khác nhau

Policy cần xét ở **exporter thực hiện thao tác sau** khi tên đã tồn tại:

| Context tạo trước | Policy của context tạo sau | Tình huống khi trùng |
|---|---|---|
| A đã đăng ký | B = FAIL | B lỗi, A vẫn là registration đang có |
| A đã đăng ký | B = IGNORE | B bỏ qua, A vẫn được hiển thị |
| A đã đăng ký | B = REPLACE | B thay A |
| B đã đăng ký | A = FAIL | A lỗi, B vẫn là registration đang có |
| B đã đăng ký | A = IGNORE | A bỏ qua, B vẫn được hiển thị |
| B đã đăng ký | A = REPLACE | A thay B |

Policy của context đã tạo trước có thể ảnh hưởng những registration trước đó và cleanup sau này; nhưng ở thời điểm context sau gặp tên đã tồn tại, chính policy của exporter đang cố đăng ký là điều cần xem trước.

## 5. Đừng quên lifecycle và unregister

Collision không chỉ xảy ra khi khởi động. Khi context đóng, `MBeanExporter` thường unregister những MBean mà nó quản lý theo lifecycle. Trong hệ thống nhiều context, thời điểm shutdown có thể làm tình hình phức tạp:

```text
T1: Context A đăng ký ObjectName X
T2: Context B xuất hiện, policy cho phép thay X
T3: Context A đóng
T4: Context B tiếp tục hoạt động
```

Cần biết **exporter nào ghi nhận ownership registration nào** và cách version/configuration xử lý cleanup, đặc biệt với REPLACE. Không nên mặc định đóng A sẽ phục hồi MBean A, cũng không mặc định B vẫn còn nguyên nếu có thành phần khác can thiệp registry.

Ở mức JMX, một ObjectName chỉ trỏ tới **một registration tại một thời điểm**. Khi registration bị thay, không có nghĩa JMX lưu stack các phiên bản để tự “quay lại” MBean trước đó.

Một quy trình kiểm tra đúng gồm:

1. Truy vấn ObjectName và `MBeanInfo` sau khi A start.
2. Truy vấn lại sau khi B start.
3. Truy vấn sau khi A đóng.
4. Truy vấn sau khi B đóng.
5. Ghi nhận registration còn tồn tại hay không và thuộc bean nào.

Mỗi lần shutdown có thể làm thay đổi bề mặt quản trị. Không chỉ kiểm tra startup rồi kết luận đã xong.

## 6. Parent/child ApplicationContext có tạo hai registry JMX không?

Spring có mô hình parent/child context: child có thể tìm bean từ parent theo cơ chế lookup phù hợp, nhưng parent không tự nhìn thấy bean con. Điều này **không đồng nghĩa có hai MBeanServer**.

Ví dụ một ứng dụng web:

```text
Root ApplicationContext
  - DataSource
  - BusinessService
  - MBeanExporter (có thể có)

Child WebApplicationContext
  - Controller
  - WebMonitor
  - MBeanExporter (có thể có)

Cả hai exporter -> platform MBeanServer của JVM
```

Dù root và child là hai ApplicationContext riêng, nếu cả hai exporter đăng ký vào platform MBeanServer và tạo cùng ObjectName thì vẫn xung đột.

Cần đặc biệt xem xét:

- Hai context có cùng tạo exporter hay child chỉ dùng hạ tầng do parent quản lý?
- Có cùng ObjectNamingStrategy không?
- MBean được chọn qua explicit beans hay autodetection?
- Autodetection ở mỗi context có quét cùng loại bean không?
- ObjectName có phản ánh context/module/instance không?

Không nên bật exporter ở cả root và child theo thói quen nếu các bean cần export chỉ được sở hữu bởi một trong hai. Một chiến lược ownership rõ ràng thường đơn giản hơn việc xử lý xung đột bằng policy.

## 7. Ví dụ thực hành Spring: hai context, một MBeanServer

Ví dụ dưới đây dùng một interface và hai instance monitor khác nhau để kiểm tra collision. Dùng hai `AnnotationConfigApplicationContext` độc lập, chung một platform MBeanServer.

### 7.1. Management interface và implementation

```java
// SourceMonitorMBean.java
public interface SourceMonitorMBean {
    String getSource();
}
```

```java
// SourceMonitor.java
public class SourceMonitor implements SourceMonitorMBean {
    private final String source;

    public SourceMonitor(String source) {
        this.source = source;
    }

    @Override
    public String getSource() {
        return source;
    }
}
```

Standard MBean dựa trên interface `SourceMonitorMBean`. `Source` là attribute chỉ đọc. Hai object có thể trả giá trị khác nhau mà dùng cùng kiểu quản trị.

### 7.2. Factory tạo context có MBeanExporter

```java
// ContextFactory.java
import java.lang.management.ManagementFactory;
import java.util.Map;
import javax.management.MBeanServer;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.jmx.export.MBeanExporter;
import org.springframework.jmx.support.RegistrationPolicy;

public final class ContextFactory {

    public static AnnotationConfigApplicationContext create(
            String source,
            RegistrationPolicy policy) {

        AnnotationConfigApplicationContext context =
            new AnnotationConfigApplicationContext();

        MBeanServer server =
            ManagementFactory.getPlatformMBeanServer();

        context.registerBean(
            "sourceMonitor",
            SourceMonitor.class,
            () -> new SourceMonitor(source)
        );

        context.registerBean(
            "jmxExporter",
            MBeanExporter.class,
            () -> {
                MBeanExporter exporter = new MBeanExporter();
                exporter.setServer(server);
                exporter.setRegistrationPolicy(policy);
                exporter.setBeans(Map.of(
                    "demo.multicontext:type=SourceMonitor,name=shared",
                    context.getBean("sourceMonitor")
                ));
                return exporter;
            }
        );

        context.refresh();
        return context;
    }
}
```

Ở đây mỗi context có một `MBeanExporter` với cùng ObjectName. Chỉ khác giá trị `source` và `RegistrationPolicy`. Việc gọi `context.getBean("sourceMonitor")` xảy ra khi Spring tạo exporter và context đã có BeanDefinition của monitor.

Trong môi trường thực, có thể khai báo các bean bằng `@Configuration` và dependency injection. Factory này chỉ giúp thay policy cho từng lần chạy một cách rõ ràng.

### 7.3. Đọc ObjectName từ platform server

```java
import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import javax.management.ObjectName;

MBeanServer server = ManagementFactory.getPlatformMBeanServer();
ObjectName name = new ObjectName(
    "demo.multicontext:type=SourceMonitor,name=shared"
);

if (server.isRegistered(name)) {
    System.out.println(
        "Currently visible: " +
        server.getAttribute(name, "Source")
    );
} else {
    System.out.println("No MBean registered at " + name);
}
```

### 7.4. Thử nghiệm A rồi B

```java
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.jmx.support.RegistrationPolicy;

public class MultiContextDemo {
    public static void main(String[] args) throws Exception {
        try (AnnotationConfigApplicationContext a =
                 ContextFactory.create(
                     "A", RegistrationPolicy.REPLACE_EXISTING
                 );
             AnnotationConfigApplicationContext b =
                 ContextFactory.create(
                     "B", RegistrationPolicy.REPLACE_EXISTING
                 )) {

            // Gọi đoạn đọc getAttribute ở đây để thấy Source của
            // registration đang có tại thời điểm sau khi B start.
            Thread.sleep(30_000L);
        }
    }
}
```

Khi dùng `REPLACE_EXISTING` cho cả A và B trong trình tự này, kỳ vọng ObjectName cuối cùng trỏ tới B. Nếu đảo hai lời gọi `create`, kết quả kỳ vọng đổi theo.

Sau đó thử:

```java
RegistrationPolicy.IGNORE_EXISTING
RegistrationPolicy.FAIL_ON_EXISTING
```

Với `FAIL_ON_EXISTING`, tạo context thứ hai có thể ném exception. Nên chạy các tổ hợp trong **process JVM riêng** hoặc bảo đảm cleanup đúng để kết quả không bị MBean của lần trước ảnh hưởng. Không thử trên shared MBeanServer production.

### 7.5. Vì sao ví dụ cần đọc lại runtime?

Kết quả sau hai lần start mới là một nửa bài toán. Hãy mở rộng để đóng A trước B hoặc B trước A và quan sát. Với `try-with-resources` như trên, resource được đóng theo thứ tự ngược: B rồi A. Nếu muốn kiểm tra A đóng trước, tạo context và gọi `a.close()` một cách có chủ đích trong `try/finally`, rồi đọc registration.

Đừng suy ra kết quả unregister chỉ từ policy name. Tác động khi cleanup chịu ảnh hưởng lifecycle của exporter, ownership, cơ chế MBeanServer và có thể khác giữa các phiên bản Spring.

## 8. RegistrationPolicy được cấu hình ở đâu?

Với `MBeanExporter`:

```java
@Bean
public MBeanExporter exporter(
        MBeanServer server,
        SourceMonitor monitor) {

    MBeanExporter exporter = new MBeanExporter();
    exporter.setServer(server);
    exporter.setRegistrationPolicy(
        RegistrationPolicy.FAIL_ON_EXISTING
    );
    exporter.setBeans(Map.of(
        "demo.source:type=Monitor,name=primary",
        monitor
    ));
    return exporter;
}
```

Đối với `AnnotationMBeanExporter`, cơ chế exporter kế thừa hỗ trợ điều chỉnh registration policy theo cấu hình tương ứng. Khi dùng `@EnableMBeanExport` hoặc Spring Boot auto-configuration, phải kiểm tra API/cấu hình thực tế của phiên bản đang dùng thay vì giả định có thể chèn một setter vào exporter do framework tạo mà không ảnh hưởng đến lifecycle.

**Nguyên tắc:** cấu hình ownership và naming trước, dùng policy như lớp bảo vệ hành vi collision. Policy không nên là công cụ duy nhất để điều phối nhiều context.

## 9. Tại sao dùng IGNORE_EXISTING có thể che giấu cấu hình sai?

Hãy xét một hệ thống có hai module:

- Module A sở hữu `InventoryMonitor`, trả `InventorySize=1200`.
- Module B cũng có bean `InventoryMonitor`, trả `InventorySize=30`.
- Cả hai exporter muốn đăng ký `company.inventory:type=Monitor`.

Nếu B khởi tạo sau với IGNORE, application log có thể không có startup exception, nhưng dashboard query ObjectName đó vẫn đọc giá trị 1200 từ A.

Điều nguy hiểm là **application context B tồn tại bình thường nhưng JMX API mà team B nghĩ nó đã công bố lại không trỏ đến B**. Khi phát hiện thiếu metric, người vận hành có thể nghi nhầm rằng getter cache sai hoặc service B chưa update.

Do đó, nếu chủ đích là hai monitor khác nhau, phải dùng ObjectName khác nhau hoặc phân vùng MBeanServer, không dùng IGNORE để “chia sẻ tên”.

## 10. Tại sao REPLACE_EXISTING có thể làm client mất tính ổn định?

Một JMX client thường giữ `ObjectName` và đọc metadata:

```java
MBeanInfo info = connection.getMBeanInfo(name);
```

Nếu exporter khác thay MBean tại cùng ObjectName, những giả định của client có thể không còn đúng:

- Attribute có thể thay đổi tên hoặc kiểu.
- Operation có thể được bổ sung hoặc bị loại bỏ.
- Notification subscriptions có thể bị ảnh hưởng bởi unregister/register.
- Counter có thể reset về giá trị ban đầu của instance mới.
- Đường biểu đồ có thể có bước nhảy khiến người vận hành hiểu sai.
- Một lệnh gọi giữa hai mốc thay thế có thể gặp `InstanceNotFoundException` hoặc lỗi khác.

REPLACE không phải cơ chế chuyển trạng thái liên tục hay transaction cho client. Nếu cần nâng cấp MBean mà vẫn giữ cùng ObjectName, nên quản lý phiên bản API, trình tự triển khai, việc register/unregister và cách client refresh metadata.

## 11. Context tạo song song: race condition thực sự

Trong ứng dụng modular hoặc test suite, hai context có thể refresh song song trên cùng JVM.

```text
Thread 1 (Context A)           Thread 2 (Context B)
    |                               |
    +-- create exporter             +-- create exporter
    +-- register X                  +-- register X
    |                               |
             timing-dependent
```

Ngay cả khi A bắt đầu refresh sớm hơn, B có thể tới `registerMBean` trước vì phụ thuộc khác nhau. Vì vậy, **“context bắt đầu tạo trước” không luôn bằng “context đăng ký MBean trước”**.

Với `FAIL_ON_EXISTING`, một context có thể lỗi không ổn định tùy scheduling. Với IGNORE, người thắng có thể khác giữa các lần chạy. Với REPLACE, registration cuối cùng có thể thay đổi theo timing.

Để loại bỏ race:

1. Có một context/exporter duy nhất chịu trách nhiệm MBean cụ thể.
2. Tạo ObjectName phân biệt module, instance hoặc tenant khi cần nhiều MBean.
3. Nếu cần startup ordering, dùng cơ chế orchestration rõ ràng, không dựa vào thread timing.
4. Tránh chạy các integration test độc lập cùng dùng một ObjectName trên shared platform server nếu không cô lập/cleanup.
5. Xác minh registry sau mỗi giai đoạn startup và shutdown.

Registration policy có thể quyết định **điều gì xảy ra khi đụng tên**, nhưng không tạo thứ tự tuần tự giữa các thread.

## 12. Thiết kế ObjectName để tránh trùng không cần thiết

Một ObjectName tốt mô tả duy nhất resource quản trị:

```text
company.orders:type=QueueMonitor,service=checkout,instance=worker-1
company.orders:type=QueueMonitor,service=checkout,instance=worker-2
company.cache:type=CacheMonitor,context=web
company.cache:type=CacheMonitor,context=background
```

Nếu hai instance thực sự khác nhau, hãy phân biệt trong `ObjectName`. Nếu chúng đại diện cùng một resource logic, xác định **một owner** có trách nhiệm đăng ký MBean thay vì để hai context cạnh tranh.

Một số lưu ý:

- Domain nên mô tả subsystem hoặc namespace có chủ quyền.
- Key property nên ổn định, không chứa secret.
- Tránh dùng PID, timestamp, random UUID nếu client cần một tên ổn định xuyên restart, trừ khi có cơ chế discovery phù hợp.
- Nếu cần nhiều instance, định danh instance phải đủ phân biệt nhưng không tiết lộ dữ liệu người dùng nhạy cảm.
- Có thể dùng `ObjectName.quote(...)` khi giá trị key chứa ký tự cần quote.
- Tránh thay đổi naming strategy giữa các phiên bản mà không cập nhật dashboard, alert hoặc script.

Một chiến lược naming nhất quán có giá trị hơn việc cấu hình `IGNORE_EXISTING` để che tất cả collision.

## 13. Khi nào nên chọn từng policy?

### Chọn FAIL_ON_EXISTING khi

- Mỗi ObjectName phải có một owner duy nhất.
- Collision thể hiện lỗi cấu hình cần phát hiện nhanh.
- Hệ thống ưu tiên correctness của JMX API hơn khởi động “êm”.
- Không có lý do hợp lệ để một module chiếm MBean của module khác.

Đây là policy phù hợp để làm lộ vấn đề ownership trong nhiều ứng dụng.

### Chọn IGNORE_EXISTING khi

- Có chủ đích cho phép một MBean đã đăng ký trước là nguồn chuẩn.
- Exporter đến sau không được quyền thay registration đang có.
- Team hiểu rõ rằng bean mới có thể **không được export**.
- Có cách kiểm tra ai đang giữ ObjectName và không sử dụng tên trùng cho resource khác nhau.

Không dùng nó chỉ vì muốn startup không lỗi.

### Chọn REPLACE_EXISTING khi

- Có ownership và lifecycle rõ ràng cho việc chuyển registration.
- Thay thế một MBean là hoạt động thiết kế có chủ đích, chẳng hạn trong một tiến trình nâng cấp kiểm soát.
- Client và giám sát có thể xử lý việc metadata, notification và counter thay đổi.
- Đã kiểm tra tác động của shutdown/restart và xung đột với module khác.

Không dùng REPLACE để tự động “sửa” mọi tình huống trùng ObjectName.

## 14. Phân biệt registration policy với các cơ chế lifecycle khác

| Cơ chế | Giải quyết | Không đảm bảo |
|---|---|---|
| `RegistrationPolicy` | Xử lý khi một ObjectName đã tồn tại | Thứ tự startup, ownership nghiệp vụ |
| `@DependsOn` | Thứ tự khởi tạo bean theo dependency | External readiness hay thứ tự giữa JVM khác nhau |
| Constructor injection | Đảm bảo dependency cần thiết để tạo bean | Background warm-up đã hoàn tất |
| `SmartLifecycle` | Start/stop theo phase của lifecycle beans | Mọi MBean sẽ register đúng thứ tự mong muốn |
| `@Primary` / `@Qualifier` | Chọn bean khi injection | Chọn JMX ObjectName owner |
| ObjectNamingStrategy | Sinh ObjectName | Quyền thay MBean đã đăng ký |
| Authorization của JMX connector | Kiểm soát client được thực hiện gì | Không tự ngăn hai exporter cùng JVM cạnh tranh tên |

Ví dụ gắn `@DependsOn("exporterA")` cho exporter B có thể khiến A được tạo trước B trong cùng context, nhưng nếu B dùng REPLACE thì B vẫn có thể thay A. Nếu chúng thuộc hai context độc lập, `@DependsOn` trong một context không tự định nghĩa global ordering giữa cả hai.

## 15. Integration test: kiểm tra collision và cleanup

Một test tốt không nên chỉ khẳng định `ApplicationContext` tạo thành công. Nên kiểm tra ObjectName và giá trị thực sự tại từng giai đoạn.

### 15.1. Các bước

1. Chuẩn bị một MBeanServer dùng cho test, tách biệt khỏi tài nguyên production.
2. Tạo context A với monitor `Source=A`.
3. Kiểm tra ObjectName đã đăng ký và attribute `Source` trả A.
4. Tạo context B với policy cần kiểm tra.
5. Kiểm tra kết quả start và attribute `Source` sau B.
6. Đóng B, kiểm tra registry.
7. Đóng A, kiểm tra registry.
8. Đảo thứ tự A/B và lặp lại để quan sát dependency vào ordering.

### 15.2. Một vài assertion

```java
assertTrue(server.isRegistered(name));
assertEquals("A", server.getAttribute(name, "Source"));
```

Khi B dùng IGNORE, có thể kỳ vọng `Source=A` nếu A đăng ký trước và không có tác nhân thứ ba. Khi B dùng REPLACE, kỳ vọng `Source=B` sau B đăng ký trong tiến trình tuần tự. Khi B dùng FAIL, kiểm tra exception phù hợp và không khẳng định B start thành công.

Với shutdown, nên quan sát kết quả thay vì hard-code một giả định chưa kiểm chứng về ownership cleanup. Việc test cần gỡ các MBean do chính test tạo ra và đóng context theo `finally` để tránh ảnh hưởng các ca sau.

### 15.3. Vì sao cần MBeanServer riêng trong test?

Platform MBeanServer của một JVM có thể tồn tại xuyên suốt nhiều test class. Nếu test trước không cleanup, test sau có thể bị collision giả hoặc đọc nhầm trạng thái. Một MBeanServer test riêng giúp kiểm soát registry, nhưng cần đảm bảo tất cả exporter trong test cùng dùng instance đó.

Nếu bài kiểm tra bắt buộc quan sát platform MXBeans hoặc attach JConsole, có thể dùng platform server trong JVM test riêng. Không nên giả định thay đổi MBeanServer trong một context sẽ cô lập mọi thành phần đang dùng platform server qua API khác.

## 16. Những tình huống dễ hiểu nhầm

### 16.1. “Context B start thành công nên B đã được export”

Không đúng nếu B dùng IGNORE và A đã chiếm tên. Phải đọc JMX attribute hoặc metadata của ObjectName.

### 16.2. “Context A tạo trước nên A luôn là owner”

Không chắc trong startup song song; thứ tự tới MBeanServer phụ thuộc timing. Với REPLACE, context đăng ký sau có thể thay A.

### 16.3. “Hai Spring bean khác nhau thì ObjectName phải khác”

Không tự động. ObjectName được tạo theo naming strategy hoặc mapping, không phải Java object identity.

### 16.4. “REPLACE sẽ lưu MBean cũ để khôi phục”

Không có hợp đồng JMX chung như vậy. Một registration bị thay không tạo stack phục hồi. Cần quản lý lifecycle và ownership rõ.

### 16.5. “Đóng context sau luôn đưa MBean trước trở lại”

Không nên giả định. Việc unregister/register và ownership phụ thuộc exporter, policy và thứ tự shutdown.

### 16.6. “Dùng @DependsOn là hết collision”

`@DependsOn` chỉ sắp thứ tự tạo bean; hai exporter vẫn có thể dùng cùng tên và policy sẽ quyết định phản ứng.

### 16.7. “JMX có nhiều context nên cần nhiều MBeanServer”

Không bắt buộc. Một MBeanServer có thể chứa MBean của nhiều context nếu ObjectName duy nhất. Cần chọn server theo yêu cầu discovery, quản trị và vận hành.

### 16.8. “Dùng IGNORE làm hệ thống an toàn hơn”

IGNORE tránh thay registration đã có, nhưng có thể che một lỗi cấu hình khiến module mới không được giám sát. An toàn vận hành cần đúng nguồn metric và ownership minh bạch.

## 17. Bảo mật và phạm vi ảnh hưởng

Registration policy không phải cơ chế bảo mật. Một exporter trong cùng JVM có khả năng thao tác với MBeanServer mà nó được cấu hình dùng; policy không xác minh “context có được quyền chiếm tên này” theo nghiệp vụ.

Những rủi ro thực tế:

- REPLACE một monitor bảo mật bằng monitor khác khiến dashboard mất chỉ số quan trọng.
- IGNORE làm module mới không xuất hiện trong giám sát dù ứng dụng đã start.
- ObjectName dùng thông tin nhạy cảm về tenant/user.
- Expose operation có tác dụng phụ và client có quyền truy cập rộng.
- Remote JMX không được giới hạn đúng mạng và identity.

Biện pháp:

- Quy định owner và naming convention theo module.
- Hạn chế số exporter chịu trách nhiệm cho cùng vùng ObjectName.
- Chọn policy phù hợp với mong đợi collision.
- Audit việc đăng ký/thay thế MBean trong hệ thống cần tuân thủ.
- Kiểm tra sự tồn tại và nội dung `MBeanInfo` sau startup.
- Bảo vệ JMX connector bằng xác thực, bảo vệ đường truyền và phân quyền phù hợp.
- Không để client dựa vào tên MBean nếu metadata/implementation có thể bị thay bất ngờ.

## 18. Thực hành theo kịch bản

**Kịch bản A — FAIL.** Tạo hai context cùng đăng ký `demo:test=Monitor`. Start A rồi B với `FAIL_ON_EXISTING`. Ghi lại exception, trạng thái A và kết quả `isRegistered(name)`.

**Kịch bản B — IGNORE.** Start A trước, B sau với `IGNORE_EXISTING`. Đọc `Source` từ JMX. Đảo thứ tự và giải thích vì sao kết quả thay đổi.

**Kịch bản C — REPLACE.** Start A trước, B sau với `REPLACE_EXISTING`. Đọc `Source` trước/sau B. Đóng B và tiếp tục quan sát; không suy đoán rằng A tự trở lại.

**Kịch bản D — Parent/child.** Tạo root và child context, mỗi context export một monitor nhưng dùng cùng platform MBeanServer. Thiết kế ObjectName phân biệt `context=root` và `context=web` rồi xác nhận cả hai cùng tồn tại.

**Kịch bản E — Race.** Start hai context bằng hai thread với cùng ObjectName trong môi trường test. Ghi nhận số lần A/B thắng qua nhiều lần chạy. Không coi kết quả thống kê là contract; sửa thiết kế để tránh race bằng naming/ownership.

**Kịch bản F — Integration test cleanup.** Đặt mỗi test trong MBeanServer riêng, đóng context ở `finally`, kiểm tra registry không còn MBean do test sở hữu sau khi kết thúc.

## 19. Câu hỏi tự kiểm tra

1. Hai ApplicationContext khác nhau có tự động có hai MBeanServer riêng không?
2. `FAIL_ON_EXISTING` xử lý ObjectName trùng như thế nào?
3. Với `IGNORE_EXISTING`, vì sao context thứ hai start thành công nhưng dashboard vẫn thấy context thứ nhất?
4. Với `REPLACE_EXISTING`, điều gì xảy ra nếu đảo thứ tự A/B?
5. Vì sao bắt đầu refresh trước không chắc đăng ký MBean trước trong chạy song song?
6. ObjectName khác Spring bean name ở điểm nào?
7. `@DependsOn` có phải giải pháp đủ để tránh collision giữa hai context không?
8. Vì sao cần quan sát kết quả sau khi một context đóng?
9. Những tác động nào đến JMX client khi MBean cùng tên bị thay?
10. Khi nào nên chọn explicit ownership và ObjectName khác nhau thay vì dùng IGNORE?

## 20. Ghi nhớ

**Trong cùng một MBeanServer, ObjectName là duy nhất dù các MBean đến từ nhiều ApplicationContext.** `FAIL_ON_EXISTING` phát hiện collision bằng lỗi; `IGNORE_EXISTING` giữ registration đã có; `REPLACE_EXISTING` cho phép exporter mới thay registration cũ. Vì thế thứ tự khởi tạo, thời điểm register và thứ tự shutdown có thể thay đổi MBean mà client nhìn thấy.

Thiết kế đáng tin cậy không chỉ dựa vào policy. Hãy chỉ định rõ owner cho mỗi MBean, đặt ObjectName không trùng, dùng exporter phù hợp, kiểm tra kết quả runtime sau startup/shutdown và bảo vệ mặt phẳng JMX bằng các cơ chế bảo mật thích hợp.
