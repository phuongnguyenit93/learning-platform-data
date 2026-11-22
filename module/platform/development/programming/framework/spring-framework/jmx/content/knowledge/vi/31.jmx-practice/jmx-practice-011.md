# Thực hành: Thử lỗi proxy AOP và khắc phục bằng target-class proxy trong Spring Framework JMX

## 1. Mục tiêu bài lab

Trong Spring Framework, một managed bean có thể được bọc bởi Spring AOP để áp dụng `@Transactional`, `@Cacheable`, tracing hoặc advice tùy chỉnh. Sau khi AOP được bật, object mà Spring container trả về không còn là implementation gốc. Nếu Spring sử dụng **JDK dynamic proxy**, proxy chủ yếu công khai các interfaces đã được cấu hình. Điều này có thể ảnh hưởng đến một JMX exporter hoặc metadata assembler cần truy cập những method chỉ tồn tại trên implementation class.

Bài thực hành này giúp bạn:

1. Tạo một bean quản trị có business interface và một operation quản trị không nằm trên interface đó.
2. Bật Spring AOP để quan sát JDK dynamic proxy.
3. Tái hiện **một lỗi có kiểm soát** khi cấu hình JMX inspection/export phụ thuộc API của implementation thay vì API của proxy.
4. Chuyển sang **target-class proxy** (class-based proxy, thường dùng CGLIB trong Spring AOP).
5. Kiểm tra lại Spring bean type, `MBeanInfo`, `ObjectName` và invocation qua `MBeanServer`.
6. Phân biệt lỗi do proxy với lỗi do exporter, assembler, naming hoặc server.
7. Đánh giá giới hạn của class-based proxy và khi nào một management facade là giải pháp tốt hơn.

> **Phạm vi:** Đây là lab dành cho một JVM Spring Framework, JMX local, không cần remote connector. Không mở JMX/RMI ra mạng trong bài này.

## 2. Kết quả mong đợi

Ta muốn quan sát hai tình huống:

| Tình huống | Kiểu proxy | Điều cần quan sát |
|---|---|---|
| A — JDK dynamic proxy | Proxy implement business interface | Method chỉ có ở implementation không trực tiếp xuất hiện trên interface proxy |
| B — Target-class proxy | Proxy là subclass của implementation | Method public không final trên implementation có thể được truy cập qua class-based proxy |
| C — JMX contract | Exporter dùng metadata phù hợp | `MBeanInfo` chứa attribute/operation được yêu cầu |
| D — Regression test | Test chạy ở cả hai cấu hình | Phát hiện thay đổi ngoài ý định của JMX API |

**Lưu ý về tính tái hiện:** Không phải mọi phiên bản/cấu hình Spring JMX đều mất MBean khi bật JDK proxy. Một số exporter và assembler biết tìm target class hoặc metadata gốc. Vì vậy lab chủ động tạo trường hợp cần concrete-type visibility; kết quả lỗi không nên được diễn giải thành quy luật rằng “JDK proxy luôn làm hỏng JMX”.

## 3. Kiến thức nền: hai cơ chế Spring AOP proxy

### 3.1. JDK dynamic proxy

Khi bean có interface và Spring AOP được cấu hình dùng interface-based proxy:

```text
OrderWorkerImpl implements OrderWorker
              |
              v
       JDK dynamic proxy
              |
              +-- implements OrderWorker
              |
              +-- does not extend OrderWorkerImpl
```

Ví dụ:

```java
public interface OrderWorker {
    void execute();
}
```

```java
public class OrderWorkerImpl implements OrderWorker {

    @Override
    public void execute() {
        // Business work.
    }

    public int getProcessedJobs() {
        return 10;
    }

    public void resetProcessedJobs() {
        // Management operation.
    }
}
```

Một JDK proxy implement `OrderWorker` không phải là instance của `OrderWorkerImpl`. Dù target vẫn có `getProcessedJobs()`, một client chỉ nhìn proxy qua interface `OrderWorker` không thể gọi method ấy. Nếu một bộ phận export/inspection tùy chỉnh chỉ phản ánh proxy class mà không tìm target, JMX metadata có thể thiếu method.

### 3.2. Target-class proxy

Khi `proxyTargetClass=true`, Spring AOP sử dụng class-based proxy khi phù hợp:

```text
OrderWorkerImpl
      ^
      |
Class-based proxy extends OrderWorkerImpl
      |
      +-- execute()
      +-- getProcessedJobs()
      +-- resetProcessedJobs()
```

Proxy là subclass của implementation, vì vậy phần lớn public methods của target class vẫn hiện diện trong type hierarchy của proxy. Cơ chế này không loại bỏ các giới hạn:

- `final class` không thể subclass để proxy theo kiểu này.
- `final method` không được override/advised.
- `private method` không thể được advised bằng subclass override.
- `self-invocation` thường bỏ qua Spring proxy-based advice.
- Class-based proxy có thể ảnh hưởng behavior ở các nơi đang phụ thuộc vào interface proxy.
- Method visibility, module system và constructor constraints vẫn cần kiểm tra theo phiên bản Spring/JDK.

**Không dùng target-class proxy như giải pháp bảo mật hoặc giao dịch mặc định:** nó chỉ thay cách tạo proxy, không bảo đảm JMX exporter tự công bố đúng mọi method.

## 4. Chuẩn bị môi trường

Yêu cầu:

- JDK 17 hoặc mới hơn.
- Spring Framework 6.x hoặc phiên bản tương thích.
- Spring Context, Spring AOP và các dependencies AOP như AspectJ Weaver khi dùng `@Aspect`.
- JUnit 5 cho integration tests.
- Một IDE hoặc terminal chạy Maven/Gradle.
- Không cần Spring Boot; nếu dùng Boot, phải kiểm soát auto-configured exporters và AOP settings để không lẫn kết quả.

Đặt packages:

```text
src/main/java/example/jmx/lab/
    OrderWorker.java
    OrderWorkerImpl.java
    TraceAspect.java
    LabConfiguration.java
    JmxInspector.java

src/test/java/example/jmx/lab/
    AopJmxProxyTest.java
```

Ví dụ Maven dependencies trong `pom.xml` (chọn một Spring version tương thích và thống nhất toàn bộ modules):

```xml
<dependencies>
  <dependency>
    <groupId>org.springframework</groupId>
    <artifactId>spring-context</artifactId>
  </dependency>
  <dependency>
    <groupId>org.springframework</groupId>
    <artifactId>spring-aop</artifactId>
  </dependency>
  <dependency>
    <groupId>org.aspectj</groupId>
    <artifactId>aspectjweaver</artifactId>
  </dependency>
  <dependency>
    <groupId>org.junit.jupiter</groupId>
    <artifactId>junit-jupiter</artifactId>
    <scope>test</scope>
  </dependency>
</dependencies>
```

Đoạn dependencies minh họa; dự án cần khai báo versions qua BOM hoặc dependency management và cấu hình Surefire/JUnit phù hợp. Không chép nguyên rồi mong Maven tự biết versions nếu không có dependency management.

## 5. Bước 1 — Tạo business interface

File `OrderWorker.java`:

```java
package example.jmx.lab;

public interface OrderWorker {
    void execute(String orderId);
}
```

Interface chỉ có một business operation. Đây là chủ đích để tạo khác biệt giữa **API được JDK proxy expose** và các management methods nằm trên implementation.

Không thêm `getProcessedJobs()` hoặc `resetProcessedJobs()` vào interface ngay, bởi khi đó sẽ khó quan sát nguyên nhân của bài lab.

## 6. Bước 2 — Tạo implementation có management methods

File `OrderWorkerImpl.java`:

```java
package example.jmx.lab;

import java.util.concurrent.atomic.AtomicInteger;
import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedOperation;
import org.springframework.jmx.export.annotation.ManagedResource;

@ManagedResource(
    objectName = "training.aop:type=OrderWorker,name=Primary",
    description = "Order worker management view")
public class OrderWorkerImpl implements OrderWorker {

    private final AtomicInteger processed = new AtomicInteger();

    @Override
    public void execute(String orderId) {
        processed.incrementAndGet();
    }

    @ManagedAttribute(
        description = "Number of processed orders")
    public int getProcessedJobs() {
        return processed.get();
    }

    @ManagedOperation(
        description = "Reset the demonstration counter")
    public void resetProcessedJobs() {
        processed.set(0);
    }
}
```

Trong ví dụ này:

- `execute(String)` là method nằm trên business interface.
- `getProcessedJobs()` và `resetProcessedJobs()` chỉ nằm trên implementation.
- `@ManagedResource`, `@ManagedAttribute`, `@ManagedOperation` cho Spring JMX metadata.
- `AtomicInteger` giúp counter đúng hơn trong test đa luồng.
- Operation reset chỉ thay demo counter; không gây mất dữ liệu thực.

Nếu exporter sử dụng annotation assembler phù hợp, contract JMX mong muốn là:

```text
ObjectName:
  training.aop:type=OrderWorker,name=Primary

Attribute:
  ProcessedJobs (readable)

Operation:
  resetProcessedJobs()
```

**Mục tiêu không phải chứng minh annotation bị mất**, mà kiểm tra exporter có thể nhận ra chúng trên target khi proxy thay đổi.

## 7. Bước 3 — Tạo aspect để Spring thực sự sinh proxy

File `TraceAspect.java`:

```java
package example.jmx.lab;

import org.aspectj.lang.ProceedingJoinPoint;
import org.aspectj.lang.annotation.Around;
import org.aspectj.lang.annotation.Aspect;

@Aspect
public class TraceAspect {

    @Around("execution(* example.jmx.lab.OrderWorker.execute(..))")
    public Object aroundExecute(ProceedingJoinPoint point)
            throws Throwable {

        long started = System.nanoTime();
        try {
            return point.proceed();
        } finally {
            long elapsed = System.nanoTime() - started;
            System.out.println(
                "execute latency ns=" + elapsed);
        }
    }
}
```

Aspect này không đòi transaction manager hoặc database. Mục đích duy nhất là làm Spring tạo AOP proxy, giúp lab tái hiện cả JDK và target-class proxy mà không đưa thêm transaction configuration phức tạp.

Dùng `@EnableAspectJAutoProxy` trong hai configuration classes để thay đổi proxy mode.

## 8. Bước 4 — Cấu hình Spring cho JDK dynamic proxy

File `JdkProxyConfig.java`:

```java
package example.jmx.lab;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;

@Configuration(proxyBeanMethods = false)
@EnableAspectJAutoProxy(proxyTargetClass = false)
public class JdkProxyConfig {

    @Bean
    public OrderWorker orderWorker() {
        return new OrderWorkerImpl();
    }

    @Bean
    public TraceAspect traceAspect() {
        return new TraceAspect();
    }
}
```

Khi context tạo bean `orderWorker`, aspect áp dụng lên `execute(..)` và Spring có thể trả về JDK dynamic proxy implements `OrderWorker`.

Kiểm tra runtime:

```java
Object bean = context.getBean("orderWorker");

System.out.println("Bean type: " + bean.getClass());
System.out.println("Is AOP proxy: " + AopUtils.isAopProxy(bean));
System.out.println("Is JDK proxy: " +
    AopUtils.isJdkDynamicProxy(bean));
System.out.println("Target type: " +
    AopUtils.getTargetClass(bean));
```

Imports:

```java
import org.springframework.aop.support.AopUtils;
```

Một assertion hữu ích:

```java
assertTrue(AopUtils.isJdkDynamicProxy(bean));
assertFalse(bean instanceof OrderWorkerImpl);
assertTrue(bean instanceof OrderWorker);
```

Những assertions này xác minh **proxy mode**, chưa khẳng định JMX exporter sẽ lỗi.

## 9. Bước 5 — Tái hiện lỗi concrete-type visibility

Một cách tái hiện có thể kiểm soát là giả lập thành phần export/inspection cần concrete implementation type:

```java
Object bean = context.getBean("orderWorker");

OrderWorkerImpl concrete = (OrderWorkerImpl) bean;
```

Với JDK proxy, cast thường thất bại:

```text
java.lang.ClassCastException:
  ...JdkDynamicAopProxy... cannot be cast to OrderWorkerImpl
```

Không phụ thuộc exact proxy class name hoặc exception message khi viết test. Điều cần chứng minh là `OrderWorkerImpl.class.isInstance(bean)` là `false`.

Đây là failure có tính quyết định của **client/inspector phụ thuộc implementation class**. Trong Spring JMX thực tế, một assembler có thể tìm target class và vẫn export thành công. Để kiểm chứng JMX behavior, cần inspect `MBeanInfo` riêng, không kết luận từ `ClassCastException` đơn lẻ.

### 9.1. Vì sao một exporter có thể mất operation?

Một bộ metadata assembler tùy chỉnh có thể làm như sau:

```java
for (Method method : bean.getClass().getMethods()) {
    // Tìm @ManagedOperation trực tiếp ở runtime proxy methods.
}
```

Nếu proxy là JDK proxy chỉ implement business interface, `resetProcessedJobs` không có ở `bean.getClass().getMethods()`. Vì vậy inspector có thể không tìm thấy operation và bỏ qua khi export.

**Đây là lỗi thiết kế của introspection path**, không phải một đặc tính chung bắt buộc của mọi Spring JMX exporter.

Cách tốt hơn là dùng `AopUtils.getTargetClass(bean)` và cơ chế metadata phù hợp của Spring, hoặc tách management facade.

## 10. Bước 6 — Cấu hình target-class proxy

File `TargetClassProxyConfig.java`:

```java
package example.jmx.lab;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;

@Configuration(proxyBeanMethods = false)
@EnableAspectJAutoProxy(proxyTargetClass = true)
public class TargetClassProxyConfig {

    @Bean
    public OrderWorkerImpl orderWorker() {
        return new OrderWorkerImpl();
    }

    @Bean
    public TraceAspect traceAspect() {
        return new TraceAspect();
    }
}
```

Với `proxyTargetClass=true`, Spring tạo subclass proxy khi class có thể được proxied.

Kiểm tra:

```java
Object bean = context.getBean("orderWorker");

assertTrue(AopUtils.isCglibProxy(bean));
assertTrue(bean instanceof OrderWorkerImpl);
assertTrue(bean instanceof OrderWorker);
```

Do proxy là subclass, một bộ inspector vốn yêu cầu `OrderWorkerImpl` có thể truy cập các public methods này. Nhưng phương án này có trade-off về type, final methods, native/AOT constraints và tác động lên các advisors khác.

### 10.1. Khi đang dùng @Transactional

Trong ứng dụng transaction proxy-based, có thể cấu hình:

```java
@EnableTransactionManagement(proxyTargetClass = true)
```

Tham số này điều chỉnh proxy strategy trong phạm vi cấu hình transaction tương ứng. Nếu ứng dụng có nhiều auto-proxy creators, thiết lập class-based proxy có thể ảnh hưởng tới các proxy khác do Spring thống nhất cấu hình AOP proxy. Cần kiểm thử hồi quy, không đổi toàn ứng dụng chỉ vì một MBean.

Đối với lab hiện tại, `@EnableAspectJAutoProxy` là đủ để tái hiện proxy và không cần database.

## 11. Bước 7 — Dùng MBeanServer cô lập

Không cần bật remote JMX. Tạo server trong test:

```java
MBeanServer server =
    MBeanServerFactory.newMBeanServer("aop.test");
```

Ví dụ `@Bean`:

```java
@Bean
public MBeanServer testMBeanServer() {
    return MBeanServerFactory.newMBeanServer("aop.test");
}
```

Điều quan trọng là exporter phải dùng **chính server** đó. Nếu exporter đăng ký vào platform server nhưng test đọc server riêng, bạn sẽ nhận `InstanceNotFoundException` và tưởng AOP là nguyên nhân.

ObjectName cố định:

```java
ObjectName name = new ObjectName(
    "training.aop:type=OrderWorker,name=Primary");
```

Không sinh ObjectName từ proxy class name vì nó có thể thay đổi theo proxy mode, JVM restart hoặc cấu hình Spring.

## 12. Bước 8 — Export MBean từ target-class proxy

Dưới đây là cách cấu hình `MBeanExporter` với Spring JMX annotation metadata; trong dự án thật có thể dùng `@EnableMBeanExport` nếu cần autodetection.

```java
import java.util.Map;
import javax.management.MBeanServer;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.export.MBeanExporter;
import org.springframework.jmx.export.assembler.MetadataMBeanInfoAssembler;
import org.springframework.jmx.export.metadata.AnnotationJmxAttributeSource;

@Configuration(proxyBeanMethods = false)
public class JmxExporterConfig {

    @Bean
    public MBeanServer testMBeanServer() {
        return MBeanServerFactory.newMBeanServer("aop.test");
    }

    @Bean
    public AnnotationJmxAttributeSource jmxAttributeSource() {
        return new AnnotationJmxAttributeSource();
    }

    @Bean
    public MetadataMBeanInfoAssembler jmxAssembler(
            AnnotationJmxAttributeSource source) {
        MetadataMBeanInfoAssembler assembler =
            new MetadataMBeanInfoAssembler();
        assembler.setAttributeSource(source);
        return assembler;
    }

    @Bean
    public MBeanExporter mbeanExporter(
            MBeanServer testMBeanServer,
            OrderWorker orderWorker,
            MetadataMBeanInfoAssembler assembler) {

        MBeanExporter exporter = new MBeanExporter();
        exporter.setServer(testMBeanServer);
        exporter.setAssembler(assembler);
        exporter.setBeans(Map.of(
            "training.aop:type=OrderWorker,name=Primary",
            orderWorker));
        return exporter;
    }
}
```

Cấu hình này cần các imports và Spring JMX dependencies phù hợp. Ví dụ chủ yếu minh họa **wiring giữa target/proxy, metadata assembler và MBeanServer**.

**Cảnh báo về constructor/cấu hình tùy phiên bản:** Một số Spring JMX API có thêm contract initialization hoặc naming strategy. Luôn kiểm tra phiên bản Spring project và chạy integration test xem `MBeanInfo` thực tế. Nếu cần prototype đơn giản, dùng `@EnableMBeanExport` trong context không có exporter trùng nhau.

### 12.1. Tránh hai exporters đăng ký trùng

Nếu bật `@EnableMBeanExport` đồng thời với `MBeanExporter` custom cùng ObjectName, test có thể thất bại vì `InstanceAlreadyExistsException`. Lab chỉ nên có **một owner** đăng ký một ObjectName trên test MBeanServer.

## 13. Bước 9 — Inspect MBeanInfo sau khi export

Đọc metadata của resource đã đăng ký:

```java
ObjectName name = new ObjectName(
    "training.aop:type=OrderWorker,name=Primary");

assertTrue(server.isRegistered(name));

MBeanInfo info = server.getMBeanInfo(name);

for (MBeanAttributeInfo attribute : info.getAttributes()) {
    System.out.println("ATTR: " + attribute.getName());
}

for (MBeanOperationInfo operation : info.getOperations()) {
    System.out.println("OP: " + operation.getName());
}
```

Kiểm tra:

```java
boolean attributeVisible =
    Arrays.stream(info.getAttributes())
        .anyMatch(a -> a.getName().equals("ProcessedJobs")
            && a.isReadable());

boolean operationVisible =
    Arrays.stream(info.getOperations())
        .anyMatch(o -> o.getName().equals("resetProcessedJobs"));

assertTrue(attributeVisible);
assertTrue(operationVisible);
```

Nếu JDK proxy configuration vẫn export chính xác attribute/operation, hãy ghi nhận điều đó: Spring exporter đang xử lý metadata/target class tốt. Khi ấy sự cố cast concrete type vẫn đúng nhưng **không chứng minh lỗi JMX**. Bài lab nên giải thích kết quả quan sát được, không ép một lỗi không tồn tại.

## 14. Bước 10 — Gọi attribute và operation qua JMX

Sau khi `MBeanInfo` cho biết contract:

```java
Object value =
    server.getAttribute(name, "ProcessedJobs");

System.out.println("Processed jobs = " + value);
```

Gọi operation:

```java
server.invoke(
    name,
    "resetProcessedJobs",
    new Object[0],
    new String[0]);
```

Sau đó:

```java
assertEquals(0,
    server.getAttribute(name, "ProcessedJobs"));
```

Nếu operation không tồn tại, JMX có thể báo `ReflectionException`; nếu MBean chưa đăng ký, `InstanceNotFoundException`; nếu metadata đúng nhưng business method ném exception, có thể gặp `MBeanException` hoặc `RuntimeMBeanException`.

Các exception này giúp xác định lỗi ở **registration**, **exposure**, **signature** hay **business execution**. Không mặc định mọi lỗi sau khi bật AOP đều do proxy strategy.

## 15. JUnit test cho JDK proxy và target-class proxy

Ví dụ test phần type visibility, độc lập JMX:

```java
import org.junit.jupiter.api.Test;
import org.springframework.aop.support.AopUtils;
import org.springframework.context.annotation
    .AnnotationConfigApplicationContext;

import static org.junit.jupiter.api.Assertions.*;

class ProxyModeTest {

    @Test
    void jdkProxyDoesNotExposeConcreteType() {
        try (var context =
                new AnnotationConfigApplicationContext(
                    JdkProxyConfig.class)) {

            Object bean = context.getBean("orderWorker");

            assertTrue(AopUtils.isJdkDynamicProxy(bean));
            assertTrue(bean instanceof OrderWorker);
            assertFalse(bean instanceof OrderWorkerImpl);
        }
    }

    @Test
    void targetClassProxyRetainsConcreteType() {
        try (var context =
                new AnnotationConfigApplicationContext(
                    TargetClassProxyConfig.class)) {

            Object bean = context.getBean("orderWorker");

            assertTrue(AopUtils.isCglibProxy(bean));
            assertTrue(bean instanceof OrderWorker);
            assertTrue(bean instanceof OrderWorkerImpl);
        }
    }
}
```

Để test JMX, mở context gồm `TargetClassProxyConfig` và `JmxExporterConfig`, rồi dùng cùng MBeanServer.

### 15.1. Kiểm tra regression của JMX contract

```java
@Test
void targetClassProxyExportsManagementContract()
        throws Exception {

    try (var context =
            new AnnotationConfigApplicationContext(
                TargetClassProxyConfig.class,
                JmxExporterConfig.class)) {

        MBeanServer server =
            context.getBean(MBeanServer.class);

        ObjectName name = new ObjectName(
            "training.aop:type=OrderWorker,name=Primary");

        assertTrue(server.isRegistered(name));

        MBeanInfo info = server.getMBeanInfo(name);

        assertTrue(Arrays.stream(info.getAttributes())
            .anyMatch(a -> a.getName()
                .equals("ProcessedJobs")));

        assertTrue(Arrays.stream(info.getOperations())
            .anyMatch(op -> op.getName()
                .equals("resetProcessedJobs")));

        server.invoke(
            name, "resetProcessedJobs",
            new Object[0], new String[0]);

        assertEquals(
            0, server.getAttribute(name, "ProcessedJobs"));
    }
}
```

Các imports của `MBeanServer`, `ObjectName`, `MBeanInfo` và `Arrays` cần bổ sung trong test file.

Nếu implementation Spring JMX của dự án xử lý JDK proxies được, nên thêm một test tương tự cho JDK case để bảo vệ compatibility, thay vì gắn kỳ vọng test JDK luôn phải fail.

## 16. Thực nghiệm: custom inspector nhìn sai type

Để nhìn thấy nguyên nhân sâu hơn, viết một diagnostic inspector mô phỏng path sai:

```java
public static boolean hasOperationOnRuntimeClass(Object bean) {
    return Arrays.stream(bean.getClass().getMethods())
        .anyMatch(m -> m.getName()
            .equals("resetProcessedJobs"));
}
```

Kết quả có thể:

```text
JDK proxy: false
Class-based proxy: true
```

Sau đó viết path tốt hơn:

```java
public static boolean hasOperationOnTargetClass(Object bean) {
    Class<?> type = AopUtils.getTargetClass(bean);

    return Arrays.stream(type.getMethods())
        .anyMatch(m -> m.getName()
            .equals("resetProcessedJobs"));
}
```

Trong cả hai trường hợp, target class có thể chứa method.

**Bài học:** đổi sang class-based proxy là một cách sửa khi một component buộc phải dùng implementation type; còn nếu component có thể được sửa, introspection target class đúng cách hoặc thiết kế management facade thường bền vững hơn.

## 17. Khi target-class proxy không giải quyết được

Một số nguyên nhân nằm ngoài proxy strategy:

| Triệu chứng | Nguyên nhân có thể | Kiểm chứng |
|---|---|---|
| MBean hoàn toàn không có | Exporter chưa hoạt động | `isRegistered`, bean lifecycle |
| MBean ở ObjectName khác | Naming strategy khác | `queryNames` |
| Getter/operation thiếu | Metadata assembler không đọc annotation | `MBeanInfo`, config |
| JDK proxy thiếu method | Interface proxy không công bố method | `getInterfaces`, target class |
| Class-based proxy thất bại | Final class/method hoặc module constraints | Proxy creation error |
| Operation gọi lỗi | Signature sai hoặc method ném exception | `MBeanInfo`, exception cause |
| JConsole không thấy MBean | Exporter dùng MBeanServer khác | So server identity |
| Có MBean nhưng transaction không chạy | Bỏ qua AOP proxy/self-invocation | Kiểm tra advisor invocation |
| Test lúc pass lúc fail | Nhiều contexts cùng đăng ký ObjectName | Isolated server và lifecycle |

Không dùng target-class proxy để che một cấu hình exporter sai. Đầu tiên đọc registration và MBeanInfo, rồi mới thay đổi AOP.

## 18. Management facade: giải pháp thay thế bền vững

Trong production, không phải lúc nào ta muốn JMX API phụ thuộc implementation business bean.

Một facade riêng:

```java
import org.springframework.jmx.export.annotation.ManagedResource;
import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedOperation;
import org.springframework.stereotype.Component;

@Component
@ManagedResource(
    objectName = "training.aop:type=WorkerManagement,name=Primary")
public class OrderWorkerManagementFacade {

    private final OrderWorker worker;
    private final OrderWorkerStatistics stats;

    public OrderWorkerManagementFacade(
            OrderWorker worker,
            OrderWorkerStatistics stats) {
        this.worker = worker;
        this.stats = stats;
    }

    @ManagedAttribute
    public int getProcessedJobs() {
        return stats.getProcessedJobs();
    }

    @ManagedOperation
    public void resetStatistics() {
        stats.reset();
    }
}
```

`OrderWorkerStatistics` là component do dự án tự định nghĩa. `OrderWorker` vẫn có thể là JDK proxy cho business methods; facade là managed resource với JMX contract ổn định.

Ưu điểm:

- Không buộc business interface phải chứa management methods.
- Không dựa vào runtime proxy class để sinh ObjectName.
- Có thể phân quyền/validate/audit cho từng management operation.
- Dễ test JMX API độc lập với transaction/caching implementation.
- Khi đổi AOP proxy mode, management facade ít bị ảnh hưởng hơn.

**Lưu ý:** nếu facade cũng bị AOP proxy, cần kiểm thử metadata và export như bất kỳ managed bean nào. Đừng giả định tách facade sẽ loại bỏ hoàn toàn mọi nguy cơ proxy.

## 19. Kiểm tra transaction semantics sau khi đổi proxy mode

Khi ứng dụng có `@Transactional`, đổi proxy mode có thể ảnh hưởng nhiều bean. Regression tests nên kiểm tra:

1. Gọi method qua Spring-managed bean, không gọi target trực tiếp.
2. Transaction advice thực sự kích hoạt trên method kỳ vọng.
3. Interface và concrete type injection vẫn hoạt động.
4. Methods final/private không bị giả định được advised.
5. Business exception rollback behavior vẫn đúng.
6. Self-invocation vẫn được hiểu là không đi qua proxy.
7. Custom advisors, caching và security không bị mất.
8. JMX operations không vô tình bypass authorization.
9. MBean ObjectName và attributes/operations vẫn ổn định.
10. Không có duplicate MBean registrations giữa contexts.

**Cẩn trọng:** target-class proxy cải thiện concrete method visibility nhưng không tự bảo đảm mọi lời gọi management operation sẽ qua transaction/security advice. Điều đó còn phụ thuộc export target, proxy và call path thực tế.

## 20. Kiểm thử thread, lifecycle và ObjectName

JMX operation có thể được gọi từ thread khác business execution. Một operation reset counters cần thread-safety. Ví dụ dùng `AtomicInteger` để tránh race không cần thiết.

Với MBeanServer cô lập:

```java
try (var context =
        new AnnotationConfigApplicationContext(
            TargetClassProxyConfig.class,
            JmxExporterConfig.class)) {
    // Verify registration and invoke operations.
}
// Spring context closes and exporter cleans up its registrations.
```

Không re-use cùng platform ObjectName giữa nhiều tests chạy song song. Nếu mỗi test có `newMBeanServer()`, đảm bảo exporter và client đều dùng reference của server riêng.

Một kiểm tra lifecycle:

```java
assertTrue(server.isRegistered(name));
context.close();
assertFalse(server.isRegistered(name));
```

Nếu test tự unregister MBean giữa chừng, cleanup behavior phụ thuộc exporter; không áp dụng test phá hủy trên shared server.

## 21. Quy trình chẩn đoán khi AOP gây sự cố JMX

```text
1. Bật AOP rồi MBean biến mất/thiếu methods?
          |
          v
2. Xác định proxy mode bằng AopUtils
          |
          v
3. Kiểm tra ObjectName trên đúng MBeanServer
          |
          v
4. Đọc MBeanInfo attribute/operation thực tế
          |
          +-- ObjectName không tồn tại?
          |      -> exporter/naming/server/context
          |
          +-- Method thiếu?
          |      -> proxy interfaces, assembler, target metadata
          |
          +-- Method có nhưng invoke lỗi?
                 -> signature, AOP/target exception
          |
          v
5. Thử management interface hoặc facade
          |
          v
6. Nếu vẫn cần concrete type:
   thử target-class proxy trong lab
          |
          v
7. Regression test JMX + AOP semantics
```

Thứ tự này tránh thay đổi proxy mode toàn hệ thống khi nguyên nhân chỉ là ObjectName hoặc một config exporter.

## 22. Bài tập thực hành

### Bài tập A — Quan sát hai proxy modes

Chạy `JdkProxyConfig` và `TargetClassProxyConfig`. In class name, target class, kết quả `AopUtils.isJdkDynamicProxy`/`isCglibProxy`. Giải thích quan hệ giữa business interface và implementation.

### Bài tập B — Tái hiện ClassCastException

Lấy bean `orderWorker` từ JDK proxy context và thử cast sang `OrderWorkerImpl`. Dùng `assertThrows(ClassCastException.class, ...)` trong test. Sau đó thử class-based proxy.

### Bài tập C — Runtime vs target inspection

Viết hai helpers: `hasOperationOnRuntimeClass` và `hasOperationOnTargetClass`. So sánh dưới JDK proxy và target-class proxy.

### Bài tập D — JMX metadata

Export bean bằng Spring annotation metadata, đọc `MBeanInfo`, assert `ProcessedJobs` và `resetProcessedJobs`. So sánh hai proxy modes; đừng gán kết quả thất bại trước khi chạy.

### Bài tập E — Transaction

Thêm transaction manager và `@Transactional` trong một project lab có database in-memory. So sánh advisor activation giữa JDK/class-based proxy. Kiểm tra rollback behavior và tránh self-invocation khi thiết kế test.

### Bài tập F — Management facade

Tạo `OrderWorkerManagementFacade` lấy `OrderWorkerStatistics` từ một bean riêng. Giữ business bean theo JDK proxy, export facade. Kiểm tra JMX contract không phụ thuộc concrete type của business bean.

### Bài tập G — Failure matrix

Cố tình dùng sai ObjectName, sai operation signature và một exporter trên server khác. Phân loại các exception; giải thích vì sao đổi proxy mode không giải quyết những lỗi này.

## 23. Câu hỏi tự kiểm tra

1. JDK dynamic proxy và target-class proxy khác nhau ở quan hệ với implementation class?
2. Vì sao method chỉ có trên implementation có thể không nhìn thấy trên JDK proxy?
3. `AopUtils.getTargetClass` giúp debug điều gì?
4. Một JDK proxy có làm mọi Spring JMX exporter thất bại không?
5. Khi nào `proxyTargetClass=true` hợp lý?
6. Vì sao `final` methods/classes là vấn đề với class-based proxy?
7. Nếu `MBeanInfo` đã đúng, có cần đổi proxy mode không?
8. Tại sao cần kiểm tra transaction/security advice sau thay đổi?
9. Management facade giúp giữ JMX contract ổn định ra sao?
10. Làm sao phân biệt lỗi registration và lỗi invocation?
11. Vì sao cần MBeanServer cô lập trong tests?
12. Điều gì xảy ra nếu hai exporters đăng ký cùng ObjectName?

## 24. Tài liệu tham khảo

- Spring Framework Reference — Proxying Mechanisms: https://docs.spring.io/spring-framework/reference/core/aop/proxying.html
- Spring Framework Reference — JMX: https://docs.spring.io/spring-framework/reference/integration/jmx.html
- Spring Framework API — AopUtils: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/aop/support/AopUtils.html
- Spring Framework API — MBeanExporter: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/export/MBeanExporter.html
- Spring Framework API — MetadataMBeanInfoAssembler: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/export/assembler/MetadataMBeanInfoAssembler.html
- Spring Framework API — AnnotationJmxAttributeSource: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/export/annotation/AnnotationJmxAttributeSource.html

**Ghi nhớ:** target-class proxy có thể khắc phục lỗi khi một thành phần phụ thuộc concrete implementation type mà JDK proxy không expose. Tuy nhiên JMX exporter/assembler phù hợp đôi khi vẫn xử lý JDK proxy đúng. Luôn kiểm chứng **proxy mode, MBean registration, MBeanInfo và invocation** trước khi thay đổi cấu hình AOP, đồng thời kiểm thử transaction/security semantics sau thay đổi.
