# Kiểm thử khởi động lại và redeploy với Spring JMX registration policy

## 1. Vì sao restart và redeploy dễ gây lỗi JMX?

Trong Spring Framework JMX, `MBeanExporter` đăng ký các MBean với một `MBeanServer` khi ứng dụng khởi động. Khi ứng dụng hoặc `ApplicationContext` đóng, exporter cần giải phóng những đăng ký mà nó sở hữu. Vấn đề xuất hiện nếu khởi động lại module, tạo context mới trong cùng JVM hoặc redeploy ứng dụng mà registry vẫn giữ `ObjectName` cũ.

Một số triệu chứng thường gặp:

- Lần đầu startup thành công, lần thứ hai ném `InstanceAlreadyExistsException`.
- Đổi cấu hình export hoặc tên bean nhưng MBean cũ vẫn xuất hiện.
- Một ứng dụng khác sở hữu MBean trùng tên bị mất MBean khi module mới khởi động.
- Hot reload hoạt động, nhưng khi redeploy hoàn chỉnh lại có lỗi do shutdown không hoàn tất.
- Test chạy riêng lẻ thành công, chạy toàn suite lại thất bại do cùng `ObjectName` trong platform server.
- JConsole hiển thị MBean từ context cũ, hoặc operation gọi vào đối tượng đã bị đóng.

`MBeanExporter` có **registration policy** để quyết định hành vi khi ObjectName đã tồn tại. Nhưng policy không thay thế quản lý lifecycle. Kiểm thử restart/redeploy cần xác nhận cả **đăng ký**, **xử lý xung đột** và **unregister đúng chủ sở hữu**.

## 2. Mô hình vòng đời

```text
JVM / MBeanServer vẫn sống
        |
        +-- Context A startup
        |       +-- exporter đăng ký ObjectName X -> MBean A
        |
        +-- Context A shutdown
        |       +-- exporter unregister X (nếu sở hữu)
        |
        +-- Context B startup
        |       +-- exporter đăng ký ObjectName X -> MBean B
        |
        +-- Context B shutdown
                +-- dọn registration và connector do B sở hữu
```

Ở môi trường redeploy, JVM/MBeanServer có thể sống lâu hơn một `ApplicationContext` hoặc một web application classloader. Nếu MBean giữ tham chiếu tới bean/classloader cũ, việc không unregister có thể gây rò tài nguyên và classloader, ngoài lỗi trùng tên.

Phân biệt ba trạng thái: `ObjectName` **chưa tồn tại**, **đã tồn tại do exporter hiện tại**, hoặc **đã tồn tại do bên khác sở hữu**. Chính sách tốt phải rõ ở từng trạng thái.

## 3. Ba hành vi registration khi trùng tên

Spring `MBeanExporter` hỗ trợ các chế độ registration thông qua các giá trị tương ứng với `RegistrationPolicy`:

| Policy | Khi ObjectName chưa có | Khi ObjectName đã tồn tại | Điều cần thận trọng |
| --- | --- | --- | --- |
| `FAIL_ON_EXISTING` | Đăng ký | Báo lỗi | Giúp phát hiện collision, nhưng startup có thể thất bại |
| `IGNORE_EXISTING` | Đăng ký | Giữ MBean hiện có, bỏ qua bean mới | App mới có thể chạy nhưng client vẫn thấy MBean cũ |
| `REPLACE_EXISTING` | Đăng ký | Thay registration hiện có | Có thể chiếm tên của MBean do component khác sở hữu |

Các tên policy minh họa ngữ nghĩa chung. Khi cấu hình cụ thể, dùng API `setRegistrationPolicy(RegistrationPolicy....)` phù hợp phiên bản Spring, hoặc cấu hình `registrationBehavior` cũ nếu dự án còn dùng API đó.

Ví dụ:

```java
import org.springframework.jmx.export.MBeanExporter;
import org.springframework.jmx.support.RegistrationPolicy;

MBeanExporter exporter = new MBeanExporter();
exporter.setRegistrationPolicy(RegistrationPolicy.FAIL_ON_EXISTING);
```

**Không dùng `REPLACE_EXISTING` như phương án chữa mọi lỗi restart.** Nếu chính sách cho phép context mới thay MBean của context cũ, vẫn phải biết context cũ còn hoạt động hay không và ai chịu trách nhiệm cleanup. Thay thế có thể khiến một hệ thống đang vận hành mất endpoint quản trị đúng.

## 4. Tạo một MBean nhỏ để kiểm thử lifecycle

Một Standard MBean tối giản:

```java
package com.example.jmx;

public interface LifecycleProbeMBean {
    String getGeneration();
}
```

```java
package com.example.jmx;

public final class LifecycleProbe implements LifecycleProbeMBean {
    private final String generation;

    public LifecycleProbe(String generation) {
        this.generation = generation;
    }

    @Override
    public String getGeneration() {
        return generation;
    }
}
```

`Generation` giúp phân biệt instance trước và sau restart. Nếu chỉ kiểm tra `isRegistered(name)`, test có thể báo thành công dù registry đang giữ một MBean cũ; đọc một thuộc tính thể hiện thế hệ của bean sẽ xác nhận đúng instance đã được đăng ký.

## 5. Test bằng MBeanServer riêng

Khi kiểm thử chính sách đăng ký, nên cô lập bằng `MBeanServerFactory.createMBeanServer()` và giải phóng tài nguyên sau test:

```java
import javax.management.MBeanServer;
import javax.management.MBeanServerFactory;

MBeanServer server =
    MBeanServerFactory.createMBeanServer("com.example.test");

try {
    // Khởi tạo các exporter với server test này.
} finally {
    MBeanServerFactory.releaseMBeanServer(server);
}
```

Server riêng giúp giảm va chạm với MBean JVM và các test khác. Nhưng **release khỏi factory không tự bảo đảm dọn các tài nguyên khác**: đóng Spring context để exporter unregister, đóng connector nếu test tự tạo, và tránh để các reference sống lâu hơn test.

Nếu cần kiểm tra tích hợp vào platform server, dùng domain/ObjectName duy nhất theo từng test và tuyệt đối không unregister MBean do test khác sở hữu.

## 6. Cấu hình exporter có ObjectName cố định

Ví dụ dùng `MBeanExporter` tường minh:

```java
import java.util.Map;
import javax.management.MBeanServer;
import org.springframework.jmx.export.MBeanExporter;
import org.springframework.jmx.support.RegistrationPolicy;

public final class ExporterFactory {
    public static MBeanExporter create(
            MBeanServer server,
            String generation,
            RegistrationPolicy policy) {

        MBeanExporter exporter = new MBeanExporter();
        exporter.setServer(server);
        exporter.setBeans(Map.of(
            "com.example.test:type=Lifecycle,name=Primary",
            new LifecycleProbe(generation)
        ));
        exporter.setRegistrationPolicy(policy);
        return exporter;
    }
}
```

Nếu exporter được dùng như bean trong Spring context, container gọi các callback khởi tạo và hủy phù hợp. Nếu chỉ `new MBeanExporter()` trong test thuần mà không đặt vào Spring, cần gọi lifecycle tương ứng của exporter theo API hiện hành; ví dụ ở đây minh họa cách cấu hình, chưa tự khởi động exporter.

Cần kiểm tra tên MBean là Standard MBean hợp lệ, naming strategy và server đang dùng. Khi truyền map với key ObjectName đầy đủ, hãy xác nhận mapping tên được exporter thực sự áp dụng trong cấu hình cuối cùng.

## 7. Tình huống A: shutdown sạch rồi startup lại

Đây là tình huống cơ bản nhất. Mục tiêu:

1. Context A start, `ObjectName X` tồn tại, thuộc tính `Generation=A`.
2. Context A close, `ObjectName X` không còn.
3. Context B start với cùng `ObjectName X`, startup thành công, thuộc tính `Generation=B`.
4. Context B close, `ObjectName X` không còn.

Pseudo-flow:

```java
ObjectName name = new ObjectName(
    "com.example.test:type=Lifecycle,name=Primary"
);

ConfigurableApplicationContext contextA =
    startContext(server, "A", RegistrationPolicy.FAIL_ON_EXISTING);

assertTrue(server.isRegistered(name));
assertEquals("A", server.getAttribute(name, "Generation"));

contextA.close();
assertFalse(server.isRegistered(name));

ConfigurableApplicationContext contextB =
    startContext(server, "B", RegistrationPolicy.FAIL_ON_EXISTING);

assertEquals("B", server.getAttribute(name, "Generation"));

contextB.close();
assertFalse(server.isRegistered(name));
```

`startContext` là test fixture cần triển khai với cấu hình Spring thực của dự án. Không thể chạy nguyên đoạn pseudo-flow nếu chưa có fixture. Ý tưởng chính là kiểm tra **hai vòng đời liên tiếp trên cùng server**, không phải mỗi vòng đời một server mới (vì trường hợp đó không phát hiện registry tồn dư).

Một test cần đóng context trong `finally` hoặc try-with-resources nếu loại context hỗ trợ `AutoCloseable`. Nếu startup B lỗi, vẫn cần dọn A và server.

## 8. Tình huống B: startup mới khi MBean cũ chưa được gỡ

Giữ context A đang hoạt động, mở thêm context B cùng ObjectName:

```text
Context A -> MBean A registered as X
Context B -> attempts to register MBean B as X
```

Với `FAIL_ON_EXISTING`, mong đợi context B thất bại rõ ràng với lỗi gốc liên quan `InstanceAlreadyExistsException`.

Phép kiểm thử cần xác nhận:

- Startup B thất bại đúng vì collision, không phải do dependency thiếu.
- MBean A vẫn tồn tại và `Generation` vẫn là A.
- Context A vẫn hoạt động bình thường.
- Cleanup sau test không xóa nhầm registration của A.

Không cần chạy JConsole để xem xung đột; `getAttribute(name, "Generation")` trên server là bằng chứng trực tiếp.

## 9. Tình huống C: IGNORE_EXISTING

Với `IGNORE_EXISTING`, B có thể khởi động mà không thay MBean A. Kiểm thử cần thể hiện rõ hệ quả này:

```text
A exports X -> Generation=A
B starts with IGNORE_EXISTING for X
X remains registered -> Generation=A
B does not own X's existing registration
```

Test nên assert:

```java
assertEquals("A", server.getAttribute(name, "Generation"));
```

Đây có thể là hành vi có chủ ý trong một container chia sẻ MBean. Nhưng nếu mục tiêu là sau redeploy công cụ giám sát phải làm việc với bean mới, `IGNORE_EXISTING` có thể **che giấu lỗi cleanup**. Hệ thống khởi động thành công nhưng vận hành đang quan sát dữ liệu cũ.

Khi đóng B, registry không được mất MBean A vì B không sở hữu registration của A. Khi đóng A, MBean A cần được unregister theo lifecycle của A.

## 10. Tình huống D: REPLACE_EXISTING

Với `REPLACE_EXISTING`, B thay registration X của A. Điều cần kiểm thử không chỉ là `Generation=B`, mà còn **cleanup theo ownership**.

```text
A registers X -> Generation=A
B replaces X -> Generation=B
A closes -> must not accidentally remove B
B closes -> X cleaned up
```

Không nên giả định mọi phiên bản/framework có hành vi ownership hoàn hảo trong tình huống hai exporter thay cùng ObjectName. Test thực sự phải xác định thứ tự shutdown được hệ thống hỗ trợ. Nếu A đóng sau khi B thay tên và vô tình unregister X, công cụ JMX sẽ mất MBean B dù B vẫn sống.

Vì có rủi ro đó, khi thiết kế module chạy song song trong cùng JVM:

- Ưu tiên một owner duy nhất cho một `ObjectName`.
- Thêm key định danh `instance` hoặc `context` nếu hai context thật sự cần đồng tồn tại.
- Hạn chế `REPLACE_EXISTING` cho quy trình takeover có kiểm soát.
- Dùng integration test để chứng minh thứ tự A/B shutdown được hỗ trợ.

## 11. Tình huống E: redeploy web application

Trong application server, JVM và platform `MBeanServer` có thể sống lâu hơn một web application. Khi deploy version mới:

1. Web app cũ bị undeploy hoặc stop.
2. Spring context cũ được đóng.
3. Exporter unregister các MBean nó sở hữu.
4. Classloader và resource của web app cũ được giải phóng.
5. Version mới tạo context và đăng ký MBean.

Nếu bước 2–3 không chạy đúng, version mới có thể gặp `InstanceAlreadyExistsException`; thậm chí khi chính sách `IGNORE_EXISTING` khiến startup thành công, registry vẫn có thể tham chiếu tới classloader cũ.

Một kịch bản kiểm thử redeploy hữu ích:

- Deploy version A, đọc `BuildVersion=A` từ MBean.
- Undeploy A, xác nhận MBean biến mất.
- Deploy version B, đọc `BuildVersion=B`.
- Undeploy B, xác nhận MBean biến mất.
- Lặp lại nhiều chu kỳ, quan sát số MBean theo domain và tài nguyên giữ lại.

Đừng chỉ kiểm tra trạng thái HTTP health của ứng dụng; một deployment có thể healthy trong khi JMX registry đang giữ endpoint quản trị cũ.

## 12. Test fixture Spring Context gần thực tế

Một cấu hình test minh họa tạo exporter cho mỗi context:

```java
import java.util.Map;
import javax.management.MBeanServer;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.jmx.export.MBeanExporter;
import org.springframework.jmx.support.RegistrationPolicy;

static AnnotationConfigApplicationContext startContext(
        MBeanServer server,
        String generation,
        RegistrationPolicy policy) {

    AnnotationConfigApplicationContext context =
        new AnnotationConfigApplicationContext();

    context.registerBean("lifecycleProbe",
        LifecycleProbe.class,
        () -> new LifecycleProbe(generation));

    context.registerBean("mbeanExporter",
        MBeanExporter.class,
        () -> {
            MBeanExporter exporter = new MBeanExporter();
            exporter.setServer(server);
            exporter.setBeans(Map.of(
                "com.example.test:type=Lifecycle,name=Primary",
                context.getBean("lifecycleProbe")
            ));
            exporter.setRegistrationPolicy(policy);
            return exporter;
        });

    try {
        context.refresh();
        return context;
    } catch (RuntimeException ex) {
        context.close();
        throw ex;
    }
}
```

Đoạn fixture này minh họa việc tạo context độc lập và wiring exporter; khi dùng `registerBean` với supplier truy xuất bean khác trong lúc refresh, cần hiểu thứ tự tạo bean và có thể thay bằng một `@Configuration` class rõ dependency để tránh phụ thuộc thứ tự startup. Với test production, dùng cùng kiểu wiring mà ứng dụng thực sự sử dụng thay vì chỉ mô phỏng lý thuyết.

Nếu dự án có Spring Boot auto-configuration JMX, không tạo thêm exporter thứ hai vô tình; chọn test một context Boot thực hoặc một context Spring Framework cô lập. Kiểm thử phải tái hiện đúng chính sách mà production đang dùng.

## 13. Kiểm thử tự động với JUnit

Một skeleton kiểm thử vòng đời:

```java
import static org.junit.jupiter.api.Assertions.*;
import javax.management.MBeanServer;
import javax.management.MBeanServerFactory;
import javax.management.ObjectName;
import org.junit.jupiter.api.Test;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.jmx.support.RegistrationPolicy;

class MBeanRedeployTest {

    @Test
    void cleanRestartReRegistersFreshInstance() throws Exception {
        MBeanServer server =
            MBeanServerFactory.createMBeanServer("restart-test");

        ObjectName name = new ObjectName(
            "com.example.test:type=Lifecycle,name=Primary"
        );

        try {
            ConfigurableApplicationContext first = null;
            ConfigurableApplicationContext second = null;

            try {
                first = startContext(
                    server, "first", RegistrationPolicy.FAIL_ON_EXISTING
                );
                assertEquals(
                    "first", server.getAttribute(name, "Generation")
                );

                first.close();
                first = null;
                assertFalse(server.isRegistered(name));

                second = startContext(
                    server, "second", RegistrationPolicy.FAIL_ON_EXISTING
                );
                assertEquals(
                    "second", server.getAttribute(name, "Generation")
                );
            } finally {
                if (second != null) second.close();
                if (first != null) first.close();
            }

            assertFalse(server.isRegistered(name));
        } finally {
            MBeanServerFactory.releaseMBeanServer(server);
        }
    }
}
```

Khi test policy B khởi động đồng thời với A, dùng cùng server/name nhưng đừng gọi `releaseMBeanServer` khi một context vẫn còn sống. Đặt timeout cho các bước startup/shutdown nếu hệ thống có connector hoặc worker bất đồng bộ để test không treo vô hạn.

## 14. Các tình huống cần kiểm thử khi chạy thật

| Tình huống | Kết quả phải xác minh |
| --- | --- |
| Startup sạch | MBean mới đăng ký theo ObjectName mong đợi |
| Shutdown sạch | Registration do context sở hữu đã được gỡ |
| Restart trong cùng JVM | MBean mới thay thế thế hệ cũ sau cleanup |
| Startup chồng lấn, FAIL_ON_EXISTING | B thất bại và A còn nguyên |
| Startup chồng lấn, IGNORE_EXISTING | A còn nguyên; B không giả mạo đã export thành công |
| Startup chồng lấn, REPLACE_EXISTING | B thay thế; cleanup không xóa nhầm B |
| Context refresh thất bại giữa chừng | Những registration đã thực hiện được dọn phù hợp |
| Spring Boot DevTools restart | Context mới không giữ stale MBean/classloader |
| Redeploy vào application server | Không rò MBean của deployment cũ |
| Test song song | ObjectName có namespace riêng, không gây ảnh hưởng chéo |

**Không cần cấu hình cả ba policy trong production.** Test những chính sách liên quan đến quyết định triển khai; đặc biệt cảnh báo về hành vi `REPLACE_EXISTING` khi nhiều owner cùng tồn tại.

## 15. Quan sát số lượng và danh tính MBean theo thời gian

Một probe để phát hiện registry tồn dư:

```java
import javax.management.MBeanServer;
import javax.management.ObjectName;

static void printOwnedNames(MBeanServer server) throws Exception {
    ObjectName pattern = new ObjectName("com.example.test:*");

    for (ObjectName name : server.queryNames(pattern, null)) {
        System.out.println(name.getCanonicalName());
    }
}
```

Sau mỗi chu kỳ restart, ghi lại số lượng và `ObjectName` của domain ứng dụng. Nếu số lượng liên tục tăng, có thể tên mới được tạo theo timestamp/identity mà tên cũ không được unregister; nếu số lượng không tăng nhưng generation vẫn là A, có thể policy `IGNORE_EXISTING` đang giữ MBean cũ.

Dùng tên ổn định cho một MBean logic; nếu cần nhiều instance chạy đồng thời, thêm một dimension như `instance=... ` được quote đúng. Tránh tạo ObjectName thay đổi vô hạn chỉ để tránh collision vì nó che lấp lỗi lifecycle và làm khó dashboard.

## 16. Connector và listener cũng phải theo vòng đời

Không chỉ MBean registration có thể rò. Nếu ứng dụng tự tạo `JMXConnectorServer`, connector có socket/registry/resource riêng và cần `stop()` khi shutdown. Với notification listener được gắn trên `MBeanServer`, cần gỡ listener do module sở hữu.

Trong redeploy, việc để lại listener hoặc connector có thể giữ tham chiếu tới classloader cũ, gây memory leak và callback vào object đã hết vòng đời.

Một thứ tự shutdown hợp lý:

1. Ngừng nhận request quản trị mới nếu có thể.
2. Dừng connector hoặc entrypoint do module tạo.
3. Gỡ listener/notification handler do module sở hữu.
4. Đóng exporter/context để unregister MBean.
5. Giải phóng executor, scheduler và tài nguyên subsystem.

Thứ tự chính xác có thể khác theo ứng dụng; mục tiêu là không còn đường gọi vào object đã shutdown.

## 17. Không sửa lỗi bằng cách xóa MBean toàn cục

Khi gặp `InstanceAlreadyExistsException`, không nên gọi:

```java
for (ObjectName name : server.queryNames(null, null)) {
    server.unregisterMBean(name); // NGUY HIỂM
}
```

Điều này có thể xóa MBean của JVM, thư viện và ứng dụng khác. Chỉ unregister chính xác những `ObjectName` mà context/module sở hữu, với lifecycle rõ.

Ngay cả việc unregister tất cả tên trong domain `com.example:* ` cũng có thể quá rộng nếu nhiều module cùng sử dụng domain ấy. Dùng namespace và ownership cụ thể.

## 18. Ghi nhớ

**Kiểm thử restart/redeploy phải chứng minh không còn MBean cũ và MBean mới thực sự đại diện cho instance mới.** `FAIL_ON_EXISTING` giúp phát hiện trùng tên, `IGNORE_EXISTING` có thể giữ endpoint cũ mà không báo lỗi, còn `REPLACE_EXISTING` có thể tạo rủi ro ownership khi context chồng lấn. Dùng cùng một `MBeanServer` qua nhiều vòng đời, đọc thuộc tính `Generation` để phân biệt instance, kiểm tra unregister lúc shutdown và thực hiện cleanup đúng chủ sở hữu.
