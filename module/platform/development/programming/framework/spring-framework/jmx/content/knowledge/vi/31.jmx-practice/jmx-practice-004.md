# Thực hành phơi bày operation có tham số bằng @ManagedOperation trong Spring JMX

## 1. Mục tiêu bài học

Spring Framework hỗ trợ phơi bày các phương thức quản trị Java ra JMX thông qua `@ManagedOperation`. Khi operation có tham số, ngoài việc đánh dấu phương thức, bạn cần hiểu cách JMX mô tả kiểu tham số trong `MBeanInfo`, cách client gọi operation bằng `MBeanServer.invoke` và cách cấu hình metadata dễ hiểu với `@ManagedOperationParameters`.

Bài học thuộc **Spring Framework JMX → Thực hành**. Sau khi hoàn thành, bạn sẽ:

- Tạo một Spring bean chứa operation có tham số và đánh dấu `@ManagedOperation`.
- Bật export bằng `@EnableMBeanExport` hoặc cấu hình annotation-driven phù hợp.
- Dùng `@ManagedOperationParameter`/`@ManagedOperationParameters` để mô tả tên và ý nghĩa tham số.
- Đăng ký MBean dưới một `ObjectName` rõ ràng.
- Gọi operation từ JConsole/JMC hoặc code qua `MBeanServer.invoke(name, operation, params, signature)`.
- Phân biệt chữ ký kiểu nguyên thủy `int` và kiểu bao `java.lang.Integer`.
- Viết integration test trên `MBeanServer` thật, kiểm tra kết quả, validation và cleanup.
- Thiết kế operation quản trị có tham số sao cho an toàn, giới hạn tác động và không làm treo client.

## 2. Operation có tham số trong JMX là gì?

Một MBean thường có ba nhóm chức năng:

| Thành phần | Ví dụ | Client sử dụng |
| --- | --- | --- |
| Attribute | `PendingCount`, `Paused` | `getAttribute`/`setAttribute` |
| Operation | `retryFailed(int maxCount)` | `invoke` |
| Notification | `queue.overloaded` | `NotificationListener` |

Operation có tham số phù hợp khi người vận hành cần truyền một giá trị điều khiển rõ ràng, chẳng hạn:

- Chạy lại tối đa `maxCount` công việc bị lỗi.
- Làm mới cache theo tên `cacheName`.
- Điều chỉnh giới hạn xử lý `setLimit(int limit)`.
- Tạm dừng một nhóm worker theo `poolName`.

Trong JMX, client không gọi Java method trên target trực tiếp mà gửi:

```text
ObjectName:
  com.example.orders:type=QueueAdmin,name=Payment

Operation name:
  retryFailed

Parameters:
  [25]

Signature:
  ["int"]
```

**Chữ ký (signature) là tên kiểu Java theo từng vị trí**, không phải danh sách tên biến. Với phương thức `retryFailed(int maxCount)`, signature phải tương ứng với `"int"`.

## 3. Chuẩn bị ứng dụng mẫu

Giả sử ứng dụng có một service xử lý job lỗi. Định nghĩa hợp đồng nghiệp vụ:

```java
package com.example.orders.application;

public interface RetryService {
    int retryFailed(int maxCount);
}
```

Implementation mô phỏng:

```java
package com.example.orders.application;

import java.util.concurrent.atomic.AtomicInteger;
import org.springframework.stereotype.Service;

@Service
public class InMemoryRetryService implements RetryService {

    private final AtomicInteger failedJobs =
        new AtomicInteger(60);

    @Override
    public int retryFailed(int maxCount) {
        if (maxCount <= 0) {
            throw new IllegalArgumentException(
                "maxCount must be positive"
            );
        }

        while (true) {
            int current = failedJobs.get();
            int retryCount = Math.min(current, maxCount);

            if (failedJobs.compareAndSet(
                    current, current - retryCount)) {
                return retryCount;
            }
        }
    }

    public int getFailedJobs() {
        return failedJobs.get();
    }
}
```

Đây là demo không thực hiện công việc thật: service chỉ giảm bộ đếm. Trong ứng dụng production, retry thực tế cần hệ thống queue, trạng thái công việc, giới hạn concurrency và khả năng kiểm soát tác động trùng lặp.

**Nguyên tắc:** logic nghiệp vụ không cần import JMX annotation. Một adapter quản trị sẽ gọi service.

## 4. Tạo management adapter với @ManagedOperation

Ví dụ một resource quản trị:

```java
package com.example.orders.management;

import com.example.orders.application.RetryService;
import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedOperation;
import org.springframework.jmx.export.annotation.ManagedOperationParameter;
import org.springframework.jmx.export.annotation.ManagedOperationParameters;
import org.springframework.jmx.export.annotation.ManagedResource;

@ManagedResource(
    objectName =
        "com.example.orders:type=QueueAdmin,name=Payment",
    description = "Operations for payment queue management"
)
public class PaymentQueueAdmin {

    private final RetryService retryService;

    public PaymentQueueAdmin(RetryService retryService) {
        this.retryService = retryService;
    }

    @ManagedOperation(
        description = "Retries up to maxCount failed jobs"
    )
    @ManagedOperationParameters({
        @ManagedOperationParameter(
            name = "maxCount",
            description =
                "Maximum number of failed jobs to retry (1..100)"
        )
    })
    public int retryFailed(int maxCount) {
        if (maxCount < 1 || maxCount > 100) {
            throw new IllegalArgumentException(
                "maxCount must be between 1 and 100"
            );
        }

        return retryService.retryFailed(maxCount);
    }
}
```

Điểm cần chú ý:

1. `@ManagedResource` giúp Spring nhận diện bean là managed resource và cung cấp ObjectName.
2. `@ManagedOperation` đánh dấu phương thức `retryFailed` được công bố cho JMX.
3. `@ManagedOperationParameters` mô tả tham số cho công cụ quản trị, giúp người dùng hiểu ý nghĩa và ràng buộc.
4. Method `retryFailed` trả `int`, biểu thị số job được chấp nhận xử lý.
5. Validation nằm trước khi gọi service để tránh giá trị gây tác động quá lớn.

`@ManagedOperationParameter(name = "maxCount")` **không thay đổi tên kiểu JMX** và không phải cơ chế validation tự động. Việc giới hạn giá trị vẫn cần code kiểm tra.

## 5. Bật annotation-driven MBean export

Trong Spring Java configuration:

```java
package com.example.orders.config;

import com.example.orders.application.RetryService;
import com.example.orders.management.PaymentQueueAdmin;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableMBeanExport;

@Configuration
@EnableMBeanExport
public class JmxConfiguration {

    @Bean
    public PaymentQueueAdmin paymentQueueAdmin(
            RetryService retryService) {
        return new PaymentQueueAdmin(retryService);
    }
}
```

Và bật component scan cho service:

```java
import org.springframework.context.annotation.ComponentScan;
import org.springframework.context.annotation.Configuration;

@Configuration
@ComponentScan("com.example.orders.application")
public class ServiceConfiguration {
}
```

Ứng dụng có thể tạo context:

```java
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

try (var context = new AnnotationConfigApplicationContext(
        ServiceConfiguration.class,
        JmxConfiguration.class)) {

    // Spring đăng ký các annotated MBean khi context khởi tạo.
}
```

Hãy đảm bảo dependency `spring-context`, `spring-aop` và các module Spring cần thiết cho cơ chế export được chọn có mặt theo phiên bản dự án. Không dùng hai exporter khác nhau để đăng ký cùng ObjectName ngoài ý muốn.

Nếu ứng dụng dùng Spring Boot, hành vi bật/tắt JMX có thể được kiểm soát thêm bởi auto-configuration và properties theo phiên bản. Trong ví dụ thực hành này, cấu hình Java trực tiếp giúp nhìn rõ hạ tầng cần thiết.

## 6. ObjectName phải chính xác và ổn định

Operation được công bố dưới ObjectName:

```text
com.example.orders:type=QueueAdmin,name=Payment
```

Không nhầm với Spring bean name:

```text
paymentQueueAdmin
```

Hai chuỗi dùng để làm hai việc khác nhau:

- Spring bean name để wiring trong `ApplicationContext`.
- `ObjectName` để JMX client tìm MBean bên trong `MBeanServer`.

Tên có thể đảo thứ tự key properties:

```text
com.example.orders:name=Payment,type=QueueAdmin
```

mà vẫn là cùng ObjectName, vì JMX canonicalize danh tính theo key properties. Dùng `ObjectName.equals()` thay vì so sánh raw strings khi cần.

## 7. Gọi operation có tham số bằng MBeanServer.invoke

Sau khi resource đã được đăng ký, client local có thể gọi:

```java
import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import javax.management.ObjectName;

MBeanServer server =
    ManagementFactory.getPlatformMBeanServer();

ObjectName name = new ObjectName(
    "com.example.orders:type=QueueAdmin,name=Payment"
);

Object result = server.invoke(
    name,
    "retryFailed",
    new Object[] { 25 },
    new String[] { "int" }
);

System.out.println("Retried: " + result);
```

Cú pháp:

```java
Object invoke(
    ObjectName name,
    String operationName,
    Object[] params,
    String[] signature
);
```

Tương ứng:

| Thành phần | Giá trị | Ý nghĩa |
| --- | --- | --- |
| `name` | ObjectName quản trị queue | MBean nào nhận lời gọi |
| `operationName` | `"retryFailed"` | Method JMX được công bố |
| `params` | `new Object[] { 25 }` | Giá trị tham số |
| `signature` | `new String[] { "int" }` | Kiểu tham số Java theo thứ tự |

Lưu ý: `new Object[] { 25 }` sử dụng autoboxing thành `Integer`, nhưng method được khai báo `int`, vì vậy **signature vẫn là `"int"`**, không phải `"java.lang.Integer"`.

Kết quả trả về `Object` có thể cast:

```java
int retried = (Integer) result;
```

Nếu method khai báo `long`, kiểu wrapper trả về thường là `Long`; client cần kiểm tra hợp đồng, không cast tùy tiện.

## 8. Phân biệt @ManagedOperation và @ManagedAttribute

Các JavaBeans accessor như:

```java
public int getPendingCount();
public void setPaused(boolean paused);
```

có thể được công bố dưới dạng JMX attributes nếu đánh dấu bằng `@ManagedAttribute` và cấu hình exporter annotation phù hợp.

Ngược lại, method:

```java
public int retryFailed(int maxCount);
```

là một action có tham số mang ngữ nghĩa nghiệp vụ, phù hợp với `@ManagedOperation`.

Có thể viết adapter:

```java
@ManagedAttribute(
    description = "Number of failed jobs currently waiting"
)
public int getFailedCount() {
    return retryService.failedCount();
}
```

`RetryService` trong ví dụ cần thêm method `failedCount()` nếu sử dụng đoạn mở rộng này; phần demo ban đầu chỉ có `retryFailed(int)`.

**Không sử dụng @ManagedAttribute trên mọi method có tham số** chỉ vì muốn chúng xuất hiện trên JConsole. Getter/setter attribute và action operation là hai hợp đồng JMX khác nhau.

## 9. Dùng nhiều tham số với @ManagedOperationParameters

Giả sử muốn chọn queue và giới hạn retry:

```java
@ManagedOperation(
    description = "Retries failed jobs from a named queue"
)
@ManagedOperationParameters({
    @ManagedOperationParameter(
        name = "queueName",
        description = "Logical queue name"
    ),
    @ManagedOperationParameter(
        name = "maxCount",
        description = "Maximum number of jobs to retry"
    )
})
public int retryFailedInQueue(
        String queueName, int maxCount) {

    if (queueName == null || queueName.isBlank()) {
        throw new IllegalArgumentException(
            "queueName is required"
        );
    }

    if (maxCount < 1 || maxCount > 100) {
        throw new IllegalArgumentException(
            "maxCount must be between 1 and 100"
        );
    }

    return retryService.retryFailedInQueue(
        queueName, maxCount
    );
}
```

Đây là một mở rộng có chủ đích: `RetryService` phải có `retryFailedInQueue(String, int)` trong triển khai tương ứng.

Gọi qua JMX:

```java
Object result = server.invoke(
    objectName,
    "retryFailedInQueue",
    new Object[] { "payment-dead-letter", 20 },
    new String[] { "java.lang.String", "int" }
);
```

Thứ tự tham số **cần trùng với thứ tự khai báo method**. Chuỗi signature có kiểu `String` đầy đủ là `java.lang.String`, còn `int` là tên primitive.

Nếu đảo hai phần tử signature hoặc truyền `"java.lang.Integer"` thay `"int"`, JMX có thể không tìm thấy overload tương ứng.

## 10. Metadata tham số có xuất hiện trong MBeanInfo không?

JMX công bố metadata operation qua `MBeanOperationInfo`, chứa chữ ký các tham số.

```java
import javax.management.MBeanInfo;
import javax.management.MBeanOperationInfo;
import javax.management.MBeanParameterInfo;

MBeanInfo info = server.getMBeanInfo(name);

for (MBeanOperationInfo op : info.getOperations()) {
    if ("retryFailed".equals(op.getName())) {
        System.out.println("Return: " + op.getReturnType());

        for (MBeanParameterInfo param : op.getSignature()) {
            System.out.println(
                param.getName() + " : " + param.getType()
                + " — " + param.getDescription()
            );
        }
    }
}
```

Nếu annotation metadata source và assembler của Spring đã hoạt động, thông tin `@ManagedOperationParameter` có thể cung cấp tên và mô tả tham số cho `MBeanInfo`. Kiểm tra metadata ở runtime để xác nhận cấu hình đang dùng thực sự xuất đúng thông tin.

Đừng giả định Java compiler luôn giữ tên tham số nguồn trong bytecode hoặc mọi JMX client đều hiển thị description theo cùng cách. Annotation metadata giúp công bố ý nghĩa tham số rõ ràng hơn, nhưng hành vi hiển thị phụ thuộc tool.

## 11. Cách thao tác trong JConsole và JMC

Một quy trình thử nghiệm:

1. Khởi động ứng dụng với JMX đang được bật trong môi trường test phù hợp.
2. Mở JConsole hoặc Java Mission Control và kết nối tới đúng JVM.
3. Mở phần quản trị MBeans và tìm domain `com.example.orders`.
4. Chọn `type=QueueAdmin,name=Payment`.
5. Mở danh sách operations.
6. Tìm `retryFailed`; xem các parameter names/types nếu tool hỗ trợ.
7. Nhập `maxCount` (ví dụ 5 hoặc 10), thực thi operation.
8. Kiểm tra return value hoặc attribute liên quan để xác minh hiệu quả.

Cần phân biệt **MBean đã được đăng ký** với **client đang nối đúng server**. Nếu exporter dùng custom MBeanServer nhưng tool nối platform server, bạn có thể không thấy resource mặc dù cấu hình export đúng.

Không mở public remote JMX port chỉ để thực hành. Dùng local development hoặc một endpoint được bảo vệ.

## 12. Spring XML khi ứng dụng chưa dùng Java configuration

Trong các dự án XML cũ, annotation-driven JMX export có thể được bật qua:

```xml
<context:mbean-export/>
```

Với XML cấu hình đầy đủ, đảm bảo namespace và schema `context` phù hợp phiên bản Spring đang dùng.

Khi bean được khai báo:

```xml
<bean id="paymentQueueAdmin"
      class="com.example.orders.management.PaymentQueueAdmin">
    <constructor-arg ref="retryService"/>
</bean>
```

và hạ tầng annotation-driven đang bật, Spring có thể nhận diện `@ManagedResource` trên class và xuất `@ManagedOperation`.

Nếu đã có `MBeanExporter` thủ công, không bật thêm đường export thứ hai cùng ObjectName ngoài chủ đích. Xung đột có thể gây `InstanceAlreadyExistsException` hoặc phụ thuộc vào `RegistrationPolicy`.

## 13. Kiểm thử bằng MBeanServer riêng

Một integration test tốt không phụ thuộc platform MBeanServer dùng chung:

```java
import javax.management.MBeanServer;
import javax.management.MBeanServerFactory;

MBeanServer testServer =
    MBeanServerFactory.newMBeanServer("test.management");
```

Với cách annotation export, cần cấu hình exporter để **dùng đúng server test**. Việc chỉ tạo `MBeanServer` bean không luôn đủ nếu annotation exporter đang ưu tiên một server khác.

Có thể viết test configuration sử dụng `AnnotationMBeanExporter` do Spring cung cấp hoặc cấu hình exporter/metadata assembler tương ứng với phiên bản. Một đường đơn giản là tạo Spring context có `MBeanExporter` và `MetadataMBeanInfoAssembler` được cấu hình rõ, sau đó khẳng định server test có MBean.

Ví dụ với Spring annotation configuration:

```java
import javax.management.MBeanServer;
import javax.management.MBeanServerFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableMBeanExport;

@Configuration
@EnableMBeanExport
public class JmxTestConfiguration {
    @Bean
    public MBeanServer mbeanServer() {
        return MBeanServerFactory.newMBeanServer(
            "test.management"
        );
    }

    @Bean
    public RetryService retryService() {
        return maxCount -> Math.min(maxCount, 3);
    }

    @Bean
    public PaymentQueueAdmin paymentQueueAdmin(
            RetryService retryService) {
        return new PaymentQueueAdmin(retryService);
    }
}
```

Sau đó test nên lấy `MBeanServer` từ context và xác nhận exporter sử dụng server này. Nếu annotation exporter của phiên bản/configuration hiện tại không chọn đúng server test, hãy cấu hình server reference tường minh thay vì thay assertion để hỏi platform server.

## 14. JUnit integration test gọi operation thật

Một test minh họa:

```java
import static org.junit.jupiter.api.Assertions.*;

import javax.management.MBeanServer;
import javax.management.ObjectName;
import org.junit.jupiter.api.Test;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

class ManagedOperationParameterTest {

    @Test
    void invokesOperationWithIntArgument() throws Exception {

        try (var context =
                 new AnnotationConfigApplicationContext(
                     JmxTestConfiguration.class)) {

            MBeanServer server =
                context.getBean(MBeanServer.class);

            ObjectName name = new ObjectName(
                "com.example.orders:type=QueueAdmin,name=Payment"
            );

            assertTrue(server.isRegistered(name));

            Object result = server.invoke(
                name,
                "retryFailed",
                new Object[] { 2 },
                new String[] { "int" }
            );

            assertEquals(2, ((Integer) result).intValue());
        }
    }
}
```

Đoạn test này xác minh:

- Annotation exporter đã đăng ký MBean vào server test.
- Operation `retryFailed` tồn tại trong MBean metadata.
- Chữ ký `int` đúng.
- Giá trị tham số được chuyển tới implementation.
- Return value phản ánh business result.

Trong dự án thực, nếu Spring context có nhiều `MBeanServer` beans, inject đúng bean theo `@Qualifier` hoặc bean name để test không chọn nhầm registry.

## 15. Kiểm thử validation với tham số không hợp lệ

Operation quản trị thường không được gọi với mọi giá trị tùy ý.

Ví dụ `maxCount` chỉ được từ 1 đến 100:

```java
public int retryFailed(int maxCount) {
    if (maxCount < 1 || maxCount > 100) {
        throw new IllegalArgumentException(
            "maxCount must be between 1 and 100"
        );
    }
    return retryService.retryFailed(maxCount);
}
```

Test qua `MBeanServer`:

```java
assertThrows(
    Exception.class,
    () -> server.invoke(
        name,
        "retryFailed",
        new Object[] { 1000 },
        new String[] { "int" }
    )
);
```

Trong implementation JMX/Spring, exception gốc có thể được bọc bởi `MBeanException`, `ReflectionException` hoặc Spring `JmxException`, tùy đường export và thời điểm lỗi.

Vì vậy, với integration test nên kiểm tra **exception chain** để xác minh root cause là validation và đảm bảo service không thực hiện side effect. Không chỉ assert bất kỳ exception rồi bỏ qua nguyên nhân.

Nếu muốn unit test business validation, có thể gọi `PaymentQueueAdmin.retryFailed(1000)` trực tiếp và assert `IllegalArgumentException` mà không cần JMX.

## 16. Operation overload và chữ ký tham số

Giả sử adapter có hai operation:

```java
@ManagedOperation
public void retryFailed(int maxCount) { ... }

@ManagedOperation
public void retryFailed(String queueName) { ... }
```

Khi invoke, tên operation giống nhau nhưng signature khác:

```java
server.invoke(
    name,
    "retryFailed",
    new Object[] { 25 },
    new String[] { "int" }
);

server.invoke(
    name,
    "retryFailed",
    new Object[] { "payment" },
    new String[] { "java.lang.String" }
);
```

Một số exporter/metadata assembler có thể xử lý method overload khác nhau theo cấu hình. Hãy đọc `MBeanInfo.getOperations()` để biết những overload thực sự được công bố, thay vì giả định method nào có annotation cũng callable.

Nếu operation mang ý nghĩa khác nhau, dùng tên cụ thể như `retryFailedByQueue` đôi khi dễ vận hành và ít nhầm chữ ký hơn.

## 17. @ManagedOperationParameter có tự chuyển đổi kiểu không?

Không. Annotation metadata chỉ mô tả tham số. JMX invocation vẫn phụ thuộc vào:

- Method signature thực tế mà exporter công bố.
- Giá trị object `params`.
- Chuỗi tên kiểu trong `signature`.
- Khả năng chuyển đổi/serialization của connector và client.

Ví dụ:

```java
new Object[] { "25" },
new String[] { "int" }
```

không tương đương:

```java
new Object[] { 25 },
new String[] { "int" }
```

Mỗi JMX client UI có thể hỗ trợ nhập giá trị và chuyển đổi string thành kiểu Java, nhưng code gọi `MBeanServer.invoke` không nên dựa vào việc server tự parse chuỗi `"25"` thành integer.

Hãy giữ kiểu tham số đơn giản và dùng input validation rõ ràng.

## 18. Remote JMX và operation có tham số

`MBeanServerConnection` lấy qua `JMXConnector` hỗ trợ cùng API:

```java
MBeanServerConnection connection =
    connector.getMBeanServerConnection();

Object result = connection.invoke(
    name,
    "retryFailed",
    new Object[] { 5 },
    new String[] { "int" }
);
```

Nhưng remote JMX thêm các rủi ro:

- Authentication/authorization.
- TLS và kết nối mạng.
- Serialization của tham số và kết quả.
- Timeout hoặc mất kết nối khi operation đã chạy.
- Retry operation có side effect có thể dẫn tới thực thi hai lần.

**Không retry mù một operation như `retryFailed` sau network timeout**, vì server có thể đã thực hiện lệnh nhưng client không nhận được phản hồi.

Ưu tiên operation idempotent hoặc có request ID để deduplicate; với công việc dài, cân nhắc operation bắt đầu job trả jobId thay vì block tới khi xử lý xong.

## 19. Bảo mật khi công bố operation có tham số

Một operation có tham số có thể tạo bề mặt điều khiển mạnh hơn một attribute đọc:

```java
@ManagedOperation
public void deleteJobs(String queueName, int count) { ... }
```

Không nên công bố operation có tác động lớn chỉ vì nó tiện cho JConsole.

Cần:

1. Chỉ expose những thao tác thực sự cần quản trị.
2. Validate giá trị, độ dài chuỗi, phạm vi queue/tenant.
3. Giới hạn số lượng và tần suất invocation.
4. Kiểm soát quyền ở JMX connector và trong service nếu cần.
5. Audit operation có side effect.
6. Tránh trả dữ liệu nhạy cảm trong result/exception.
7. Thiết kế timeout, trạng thái công việc và idempotency.
8. Không cho phép operation tự ý vượt qua business invariants.

`@ManagedOperation(description = "...")` **không phải annotation security**. Description chỉ giúp giải thích phương thức, không bảo đảm ai được gọi.

## 20. Vấn đề Spring AOP và proxy

Nếu bean quản trị được bọc bởi JDK dynamic proxy, các method không thuộc interface proxy có thể không được expose/callable như mong đợi. Nếu dùng CGLIB/class-based proxy, vẫn cần xem giới hạn `final`, `private` và proxy advice.

Một thiết kế dễ duy trì:

```text
JMX Client
    |
    v
PaymentQueueAdmin (management adapter)
    |
    v
RetryService Spring bean/proxy
    |
    v
Business implementation
```

Adapter mang annotation JMX, service chứa business logic và AOP advice. Việc gọi qua service proxy giữ đường transaction/security rõ hơn so với export target object tùy ý.

Nếu `@ManagedOperation` có mặt nhưng `MBeanInfo` không thấy operation, kiểm tra annotation exporter, metadata assembler và proxy method surface.

## 21. Chẩn đoán lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra |
| --- | --- | --- |
| Không thấy MBean trong JConsole | Chưa bật exporter, sai server, sai ObjectName | `isRegistered`, config, endpoint |
| Thấy MBean nhưng không có operation | Annotation chưa được metadata source đọc | `MBeanInfo.getOperations()` |
| `ReflectionException` khi invoke | Tên operation hoặc signature không khớp | Đọc `MBeanOperationInfo` |
| Truyền `Integer` nhưng signature `Integer` bị lỗi | Method dùng primitive `int` | Dùng `"int"` |
| Tham số nhập trên UI không gọi được | Client chuyển đổi kiểu khác mong đợi | Kiểm tra kiểu JMX công bố |
| Operation trả kết quả sai | Business service/validation | Unit test adapter và service |
| `InstanceAlreadyExistsException` | Hai exporters đăng ký cùng ObjectName | Chọn owner, kiểm tra policy |
| Remote invoke timeout | Latency mạng hoặc operation chạy lâu | Thiết kế async job, tránh retry mù |
| Client bị từ chối invoke | JMX authorization/connector policy | Kiểm tra quyền và auth config |
| Operation chạy nhưng AOP advice không có | Export sai target/proxy | Dùng adapter gọi service proxy |

## 22. Checklist thực hành

- [ ] Tạo resource với `@ManagedResource` và ObjectName hợp lệ.
- [ ] Đánh dấu method cần công bố bằng `@ManagedOperation`.
- [ ] Mô tả đầy đủ tham số qua `@ManagedOperationParameters`.
- [ ] Đảm bảo annotation-driven exporter đang hoạt động.
- [ ] Kiểm tra `MBeanServer.isRegistered` trên đúng server.
- [ ] Đọc `MBeanInfo` xác minh operation name và signature.
- [ ] Gọi `invoke` với `params` và `signature` tương ứng.
- [ ] Test giới hạn tham số và error path.
- [ ] Không expose operation nhạy cảm vô tình.
- [ ] Không trộn runtime/remote configuration vào business logic.
- [ ] Đóng context/connector sau test.
- [ ] Với remote, kiểm tra idempotency và retry policy.

## 23. Bài tập mở rộng

1. Đổi operation thành `reprocess(String queueName, int maxCount, boolean dryRun)`. Viết `@ManagedOperationParameters` mô tả ba tham số.
2. Gọi operation trên qua `MBeanServer.invoke` với chữ ký `"java.lang.String", "int", "boolean"`.
3. Kiểm tra `MBeanInfo` xác minh số lượng tham số, tên, mô tả và kiểu.
4. Tạo hai overload khác kiểu tham số; thử gọi từng overload bằng signature chính xác.
5. Thêm validation `dryRun=false` chỉ được phép khi `maxCount <= 50`; kiểm tra error path.
6. Thêm `@ManagedAttribute` đọc số job còn lại; gọi operation rồi so sánh state trước/sau.
7. Tạo integration test Spring context và MBeanServer riêng để tránh xung đột.
8. Mô phỏng một remote invocation bị mất phản hồi; giải thích vì sao không tự gọi lại nếu operation có side effect.

## 24. Câu hỏi tự kiểm tra

- Vai trò của `@ManagedOperation` là gì?
- `@ManagedOperationParameters` cung cấp metadata nào?
- Tham số `int` phải xuất hiện trong signature với tên `"int"` hay `"java.lang.Integer"`?
- Vì sao tên biến `maxCount` không phải phần quyết định operation overload?
- Sự khác nhau giữa `getAttribute` và `invoke` là gì?
- Làm sao xác minh operation đã được exporter công bố thật?
- Tại sao operation có tham số phải validate input?
- Khi remote invocation timeout, có thể chắc chắn server chưa chạy operation không?
- Vì sao nên dùng management adapter thay vì export mọi method của business service?

**Ghi nhớ:** `@ManagedOperation` giúp Spring công bố một phương thức như **JMX operation**, kể cả phương thức có tham số. `@ManagedOperationParameters` bổ sung tên/mô tả, nhưng invocation vẫn dựa vào **operation name, values và ordered Java type signature**. Luôn kiểm tra metadata runtime bằng `MBeanInfo`, test `MBeanServer.invoke`, giới hạn tham số và bảo vệ thao tác quản trị có side effect.