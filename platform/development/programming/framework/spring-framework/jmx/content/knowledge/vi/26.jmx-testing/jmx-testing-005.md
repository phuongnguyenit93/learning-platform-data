# Kiểm thử duplicate registration theo từng policy trong Spring Framework JMX

## Mục tiêu

Bài học này hướng dẫn kiểm thử khi hai Spring MBeanExporter hoặc hai thành phần cố đăng ký MBean dưới cùng một ObjectName trong cùng MBeanServer. Bạn sẽ phân biệt ba RegistrationPolicy: FAIL_ON_EXISTING, IGNORE_EXISTING và REPLACE_EXISTING; xác minh object thực tế được công bố; kiểm tra cleanup và tránh đụng chạm MBeans của context khác.

## 1. Duplicate registration là gì?

Trong JMX, một MBeanServer không thể giữ hai MBeans có cùng ObjectName tại cùng thời điểm. Ví dụ:

```text
learning.jmx:type=CacheMonitor,name=Primary
```

Nếu context A đã đăng ký MBean OLD dưới tên này, context B muốn đăng ký MBean NEW cùng tên vào chính server đó sẽ gặp duplicate registration.

Hai ObjectNames giống nhau ở hai MBeanServers khác nhau không xung đột. Tên Java class giống nhau cũng không tự tạo lỗi nếu ObjectNames khác nhau.

```text
Context A -> MBeanExporter A --+
                               +--> one MBeanServer
Context B -> MBeanExporter B --+
                               |
                    same ObjectName -> collision
```

Vì ObjectName là management identity, chính sách xử lý xung đột ảnh hưởng trực tiếp tới client đang đọc attributes hoặc gọi operations.

## 2. Ba policy của Spring MBeanExporter

Spring Framework cung cấp enum org.springframework.jmx.support.RegistrationPolicy.

| Policy | Khi tên đã tồn tại | Điều cần kiểm thử |
|---|---|---|
| FAIL_ON_EXISTING | Báo lỗi, không đăng ký thay | OLD còn nguyên, startup B thất bại |
| IGNORE_EXISTING | Bỏ qua registration mới | OLD vẫn là object mà client nhìn thấy |
| REPLACE_EXISTING | Hủy registration cũ, đăng ký mới | NEW được công bố dưới tên cũ |

Chỉ assert Spring context khởi động được là thiếu. Với IGNORE_EXISTING, context B có thể khởi động nhưng MBean được truy vấn vẫn là OLD. Với REPLACE_EXISTING, cùng ObjectName có thể trỏ tới một management contract khác.

Cần xác minh cả registration status, owner identity, attributes/operations và cleanup.

## 3. Chuẩn bị Standard MBean làm test fixture

Để nhận diện đối tượng đang được export, dùng attribute OwnerId.

Tệp TestResourceMBean.java:

```java
package example.jmx;

public interface TestResourceMBean {
    String getOwnerId();
}
```

Tệp TestResource.java:

```java
package example.jmx;

public class TestResource implements TestResourceMBean {
    private final String ownerId;

    public TestResource(String ownerId) {
        this.ownerId = ownerId;
    }

    @Override
    public String getOwnerId() {
        return ownerId;
    }
}
```

Một object OLD trả về OwnerId bằng "OLD", object NEW trả về "NEW". Như vậy có thể xác minh object thực sự được công bố bằng getAttribute, thay vì chỉ kiểm tra isRegistered.

## 4. Tạo MBeanServer riêng

Không nên mặc định dùng platform MBeanServer cho mọi integration test vì nó có thể được các test hoặc framework khác cùng JVM sử dụng.

```java
import javax.management.MBeanServer;
import javax.management.MBeanServerFactory;
import javax.management.ObjectName;

MBeanServer server =
    MBeanServerFactory.createMBeanServer("test.duplicate");

ObjectName name = new ObjectName(
    "learning.jmx:type=TestResource,name=Primary"
);
```

Server riêng giúp các test độc lập, nhất là khi cùng ObjectName được sử dụng ở từng case.

Sau khi context/exporter đã đóng và không còn consumer, test có thể release server do mình tạo:

```java
MBeanServerFactory.releaseMBeanServer(server);
```

Không gọi release trên platform server hoặc shared server mà test không sở hữu.

## 5. Tạo old registration trước khi thử policy

```java
server.registerMBean(new TestResource("OLD"), name);

assertTrue(server.isRegistered(name));
assertEquals("OLD", server.getAttribute(name, "OwnerId"));
```

Đây là precondition. Nếu tên chưa tồn tại, bạn không đang kiểm thử duplicate registration và mọi policy có thể hành xử giống nhau.

Một test tốt phải đặt precondition rõ ràng để FAIL, IGNORE và REPLACE được kiểm tra trên cùng tình huống logic.

## 6. Cấu hình MBeanExporter bằng policy

Ví dụ tạo exporter:

```java
import java.util.Map;

import org.springframework.jmx.export.MBeanExporter;
import org.springframework.jmx.support.RegistrationPolicy;

MBeanExporter exporter = new MBeanExporter();
exporter.setServer(server);
exporter.setRegistrationPolicy(RegistrationPolicy.IGNORE_EXISTING);
exporter.setBeans(Map.of(
    "learning.jmx:type=TestResource,name=Primary",
    new TestResource("NEW")
));
```

Trong chương trình Spring, nên để exporter là bean được quản lý bởi ApplicationContext để callbacks register/unregister chạy theo lifecycle Spring.

Cấu hình ở trên mô tả cách đặt policy. Việc chỉ new exporter chưa bảo đảm toàn bộ vòng đời initialization/destroy đã được thực hiện.

## 7. Helper xây một Spring context theo policy

Có thể tạo một helper cho integration tests để mỗi case dùng một ApplicationContext riêng.

```java
package example.jmx;

import java.util.Map;
import javax.management.MBeanServer;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.jmx.export.MBeanExporter;
import org.springframework.jmx.support.RegistrationPolicy;

public final class TestContexts {

    private TestContexts() {}

    public static AnnotationConfigApplicationContext start(
            MBeanServer server,
            RegistrationPolicy policy,
            String owner) {

        AnnotationConfigApplicationContext context =
            new AnnotationConfigApplicationContext();

        context.registerBean("testResource", TestResource.class,
            () -> new TestResource(owner));

        context.registerBean("mbeanExporter", MBeanExporter.class,
            () -> {
                MBeanExporter exporter = new MBeanExporter();
                exporter.setServer(server);
                exporter.setRegistrationPolicy(policy);
                exporter.setBeans(Map.of(
                    "learning.jmx:type=TestResource,name=Primary",
                    context.getBean(TestResource.class)
                ));
                return exporter;
            });

        try {
            context.refresh();
            return context;
        } catch (RuntimeException failure) {
            context.close();
            throw failure;
        }
    }
}
```

Lợi ích: một context sở hữu một exporter. Khi test đóng context, exporter cleanup registrations thuộc phạm vi nó quản lý. Nếu refresh thất bại, helper vẫn close context để không giữ tài nguyên dở dang.

Từng test tạo server mới, nên không cần thay đổi những MBeans khác trong JVM.

## 8. Test FAIL_ON_EXISTING

Kỳ vọng: exporter B không được ghi đè OLD; startup bị từ chối và ObjectName vẫn trỏ đến OLD.

```java
@Test
void failOnExistingRejectsDuplicate() throws Exception {
    MBeanServer server =
        MBeanServerFactory.createMBeanServer("test.fail");

    ObjectName name = new ObjectName(
        "learning.jmx:type=TestResource,name=Primary"
    );

    server.registerMBean(new TestResource("OLD"), name);

    try {
        assertThrows(RuntimeException.class, () ->
            TestContexts.start(
                server,
                RegistrationPolicy.FAIL_ON_EXISTING,
                "NEW"
            )
        );

        assertTrue(server.isRegistered(name));
        assertEquals("OLD", server.getAttribute(name, "OwnerId"));
    } finally {
        if (server.isRegistered(name)) {
            server.unregisterMBean(name);
        }
        MBeanServerFactory.releaseMBeanServer(server);
    }
}
```

Đây là assert exception tương đối rộng cho ví dụ. Khi ứng dụng yêu cầu độ chính xác cao, cần xác định root cause (ví dụ lỗi duplicate registration được Spring bọc thành startup exception) và không chỉ assert một RuntimeException bất kỳ.

Không giải quyết lỗi này bằng REPLACE_EXISTING trừ khi chủ đích là thay thế MBean cũ.

## 9. Test IGNORE_EXISTING

Kỳ vọng: context B có thể khởi động nhưng ObjectName tiếp tục trỏ tới OLD. Đóng B không được xóa MBean OLD.

```java
@Test
void ignoreExistingKeepsOldRegistration() throws Exception {
    MBeanServer server =
        MBeanServerFactory.createMBeanServer("test.ignore");

    ObjectName name = new ObjectName(
        "learning.jmx:type=TestResource,name=Primary"
    );

    server.registerMBean(new TestResource("OLD"), name);

    AnnotationConfigApplicationContext context = null;

    try {
        context = TestContexts.start(
            server,
            RegistrationPolicy.IGNORE_EXISTING,
            "NEW"
        );

        assertTrue(server.isRegistered(name));
        assertEquals("OLD", server.getAttribute(name, "OwnerId"));
    } finally {
        if (context != null) {
            context.close();
        }
    }

    try {
        assertTrue(server.isRegistered(name));
        assertEquals("OLD", server.getAttribute(name, "OwnerId"));
    } finally {
        server.unregisterMBean(name);
        MBeanServerFactory.releaseMBeanServer(server);
    }
}
```

Điểm đáng nhớ: IGNORE không có nghĩa NEW đã xuất thành công. Bỏ qua đăng ký khác với thay thế đăng ký.

Trong test production-grade, nên gói cleanup vào outer try/finally để vẫn cleanup khi startup/assertions bất ngờ ném exception.

## 10. Test REPLACE_EXISTING

Kỳ vọng: MBean mới được công bố và OwnerId trở thành NEW. Khi exporter B đóng và nó quản lý registration đó, có thể xác minh unexport.

```java
@Test
void replaceExistingPublishesNewRegistration() throws Exception {
    MBeanServer server =
        MBeanServerFactory.createMBeanServer("test.replace");

    ObjectName name = new ObjectName(
        "learning.jmx:type=TestResource,name=Primary"
    );

    server.registerMBean(new TestResource("OLD"), name);

    AnnotationConfigApplicationContext context =
        TestContexts.start(
            server,
            RegistrationPolicy.REPLACE_EXISTING,
            "NEW"
        );

    try {
        assertTrue(server.isRegistered(name));
        assertEquals("NEW", server.getAttribute(name, "OwnerId"));
    } finally {
        context.close();
    }

    try {
        assertFalse(server.isRegistered(name));
    } finally {
        MBeanServerFactory.releaseMBeanServer(server);
    }
}
```

Với một old registration thủ công và một exporter B, ví dụ này giúp thấy hiệu lực của policy. Nhưng khi cả A và B đều là Spring exporters cùng sống, cần thử thêm thứ tự đóng contexts để quan sát ownership; không nên suy luận rằng REPLACE là một cơ chế migration an toàn cho mọi trường hợp.

## 11. Test matrix tổng hợp

| Tình huống | FAIL | IGNORE | REPLACE |
|---|---|---|---|
| OLD đã đăng ký trước | Precondition | Precondition | Precondition |
| B khởi tạo thành công | Không | Có | Có |
| OwnerId sau attempt | OLD | OLD | NEW |
| MBean bị ghi đè | Không | Không | Có |
| B đóng có xóa OLD không? | Không | Không | OLD đã bị thay |
| B đóng có unregister NEW không? | NEW chưa đăng ký | NEW chưa đăng ký | Có nếu B sở hữu |
| Cần cẩn trọng về shared ownership | Có | Có | Đặc biệt quan trọng |

Một parameterized test theo enum có thể giảm code lặp, nhưng từng case vẫn cần MBeanServer, ObjectName và cleanup độc lập.

```java
@ParameterizedTest
@EnumSource(RegistrationPolicy.class)
void duplicatePolicyBehavior(RegistrationPolicy policy) {
    // Arrange: server riêng, OLD registration.
    // Act: tạo exporter B theo policy.
    // Assert: exception/OwnerId/registration/cleanup.
}
```

## 12. Kiểm tra cả MBeanInfo

OwnerId giúp nhận diện object nhưng chưa chứng minh contract tương thích.

```java
MBeanInfo info = server.getMBeanInfo(name);

for (MBeanAttributeInfo a : info.getAttributes()) {
    System.out.println(a.getName() + ":" + a.getType());
}

for (MBeanOperationInfo op : info.getOperations()) {
    System.out.println(op.getName());
}
```

Với REPLACE, MBean mới có thể có attributes/operations khác mặc dù ObjectName giữ nguyên. Monitoring script hoặc JConsole có thể gặp AttributeNotFoundException hay operation mismatch sau replacement.

Nếu cần thay MBean trong môi trường thật, hãy xem ObjectName, attributes, types, operation signatures, read/write semantics và notification metadata như một contract cần migration.

## 13. Hai ApplicationContexts cùng sống

Một tình huống khác là A và B đều sở hữu exporters:

```text
Context A -- exporter A --+
                          +--> shared MBeanServer
Context B -- exporter B --+
```

Thứ tự:

1. Start A và đăng ký ObjectName.
2. Start B với REPLACE_EXISTING.
3. B thay registration của A.
4. A hoặc B đóng.

Không nên mặc định context A biết B đã thay MBean. Nếu exporter A vẫn giữ thông tin registration đã tạo, việc đóng A có thể tác động đến tên đó tùy implementation và ownership handling.

Các phép thử nên bao gồm:

- Start A → Start B(IGNORE) → Close B: A còn đăng ký.
- Start A → Start B(REPLACE) → Close B: xem B cleanup và A có tự khôi phục hay không.
- Start A → Start B(REPLACE) → Close A: quan sát liệu B còn registration hay không.
- Start A → Start B(FAIL): B thất bại; A vẫn hoạt động.

Trong thiết kế hệ thống, giải pháp thường là **chỉ một owner cho mỗi ObjectName**. Nếu có hai logical resources, hãy chọn ObjectNames phân biệt.

## 14. RegistrationPolicy không phải chính sách toàn JVM

Property trên exporter:

```java
exporter.setRegistrationPolicy(
    RegistrationPolicy.REPLACE_EXISTING
);
```

chỉ ảnh hưởng cơ chế đăng ký của exporter đó. Nó không thay đổi cách mọi lời gọi registerMBean thủ công vận hành.

Ví dụ JMX API trực tiếp:

```java
server.registerMBean(new TestResource("OLD"), name);
server.registerMBean(new TestResource("NEW"), name);
```

Lần thứ hai có thể ném InstanceAlreadyExistsException nếu tên vẫn đăng ký. Để thay thế thủ công cần logic unregister/register được kiểm soát, và đó là trách nhiệm code gọi JMX API.

Spring RegistrationPolicy là cơ chế trong MBeanExporter để xử lý tình huống này một cách cấu hình được.

## 15. Cleanup và tránh ảnh hưởng test khác

Không dùng cleanup mù quáng trên shared platform server:

```java
if (platformServer.isRegistered(name)) {
    platformServer.unregisterMBean(name);
}
```

Đoạn này có thể xóa MBean của component khác nếu test không sở hữu tên đó.

Quy trình isolation hợp lý:

1. Tạo MBeanServer riêng cho test.
2. Tạo OLD registration do test sở hữu.
3. Tạo exporter B với policy.
4. Assert trạng thái thực tế.
5. Đóng ApplicationContext B nếu đã mở.
6. Unregister những registrations test còn sở hữu.
7. Release MBeanServer nếu được tạo qua factory và không còn consumer.

Khi test được chạy song song, không chia sẻ cùng MBeanServer và ObjectName trừ khi chính việc chia sẻ là mục tiêu kiểm thử.

## 16. Các lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| FAIL không báo lỗi | Không tạo duplicate trên cùng server | Kiểm tra server identity và ObjectName |
| IGNORE trả OwnerId NEW | OLD chưa tồn tại hoặc policy sai | Kiểm tra precondition và exporter config |
| REPLACE vẫn trả OLD | Exporter không thay registration | Đọc logs và getAttribute |
| Test lúc pass lúc fail | Shared platform server hoặc nhiều tests dùng cùng tên | Dùng server riêng |
| Context B refresh fail để lại state | Không close khi startup lỗi | Helper tự close trong catch |
| MBean biến mất sau close A | Shared ownership, cleanup tác động tên đã bị thay | Test shutdown order, tránh hai exporters sở hữu cùng tên |
| Contract thay đổi sau REPLACE | NEW có metadata khác OLD | So sánh MBeanInfo |
| Test cleanup làm mất MBean ngoài test | Unregister mù trên server dùng chung | Dùng isolated server và ownership |
| MBeanServerFactory giữ tham chiếu | Server test không được release | Release khi đúng owner |
| Assertion lỗi sai nguyên nhân | Chỉ assert RuntimeException quá rộng | Kiểm tra root cause |

## 17. Checklist kiểm thử

Trước khi chạy:

1. Có đúng một MBeanServer test không?
2. OLD đã được register trước chưa?
3. ObjectName của OLD và NEW có giống nhau trong cùng server không?
4. Effective RegistrationPolicy được set đúng chưa?
5. Có cách phân biệt OLD/NEW bằng dữ liệu rõ ràng không?
6. Có test exception khi FAIL không?
7. Có test giữ nguyên OLD khi IGNORE không?
8. Có test thay thành NEW khi REPLACE không?
9. Có test unregister/cleanup theo policy không?
10. Có test nhiều contexts và thứ tự close nếu cần không?
11. Có tránh platform server dùng chung không?
12. Có kiểm tra attributes/operations bằng MBeanInfo không?
13. Có tránh release server mà test không sở hữu không?
14. Có kiểm tra exception root cause khi startup fail không?

## 18. Bài tập thực hành

**Bài 1:** Tạo OLD, thử FAIL_ON_EXISTING, assert exception và OLD không đổi.

**Bài 2:** Tạo OLD, thử IGNORE_EXISTING, assert context B thành công nhưng OwnerId vẫn OLD. Đóng B và kiểm tra OLD vẫn tồn tại.

**Bài 3:** Tạo OLD, thử REPLACE_EXISTING, assert OwnerId thành NEW, rồi đóng B để kiểm tra cleanup.

**Bài 4:** Tạo hai contexts A/B cùng server, thử các thứ tự đóng khi REPLACE. Ghi lại registration state và giải thích nguy cơ shared ownership.

**Bài 5:** Tạo NEW có MBeanInfo khác OLD, so sánh metadata sau REPLACE và lập kế hoạch tương thích với JMX client.

## 19. Ghi nhớ

- Duplicate registration là hai đăng ký cùng ObjectName vào **cùng MBeanServer**.
- FAIL_ON_EXISTING báo lỗi và giữ MBean cũ.
- IGNORE_EXISTING giữ MBean cũ; không có nghĩa MBean mới đã được xuất.
- REPLACE_EXISTING công bố MBean mới và có thể thay đổi contract dưới cùng ObjectName.
- Test đúng phải kiểm tra OwnerId hoặc một giá trị phân biệt, không chỉ isRegistered.
- Với nhiều exporters cùng sống, ownership và shutdown order đặc biệt quan trọng.
- Tách MBeanServer theo test, cleanup có kiểm soát và test MBeanInfo để phát hiện thay đổi ngoài ý muốn.

## Tài liệu tham khảo

- Spring Framework JMX: https://docs.spring.io/spring-framework/reference/integration/jmx.html
- Spring MBeanExporter API: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/export/MBeanExporter.html
- Spring RegistrationPolicy API: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/support/RegistrationPolicy.html
- Java SE MBeanServer API: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanServer.html
