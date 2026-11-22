# MBeanServerConnectionFactoryBean trong Spring

## Mục đích

Spring Framework cung cấp `org.springframework.jmx.support.MBeanServerConnectionFactoryBean` để cấu hình một kết nối JMX client dưới dạng Spring bean. Bean được tạo có kiểu `javax.management.MBeanServerConnection`, dùng để truy vấn hoặc tương tác với những MBean đã được đăng ký trong một JVM, thường là JVM từ xa. Đây không phải `MBeanExporter`: exporter đăng ký Spring bean vào MBeanServer, còn connection factory cung cấp đường kết nối để truy cập MBeanServer đã tồn tại.

## Các thành phần

| API | Chức năng |
|---|---|
| `MBeanServer` | Registry của MBeans tại JVM đích |
| `MBeanServerConnection` | Interface truy vấn attributes, operations và MBean metadata |
| `JMXConnector` | Quản lý transport kết nối remote JMX |
| `JMXServiceURL` | Định danh địa chỉ connector |
| `MBeanServerConnectionFactoryBean` | FactoryBean Spring cung cấp connection cho DI |
| `MBeanExporter` | Export Spring bean thành MBean tại server |

## Cấu hình Java

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.jmx.support.MBeanServerConnectionFactoryBean;

@Configuration
public class RemoteJmxConfig {
    @Bean
    public MBeanServerConnectionFactoryBean ordersJmxConnection(
            @Value("${app.jmx.orders.url}") String serviceUrl)
            throws Exception {
        MBeanServerConnectionFactoryBean factory =
            new MBeanServerConnectionFactoryBean();
        factory.setServiceUrl(serviceUrl);
        return factory;
    }
}
```

Ví dụ property: `app.jmx.orders.url=service:jmx:rmi:///jndi/rmi://jmx.example.internal:9999/jmxrmi`. Endpoint chỉ hoạt động nếu JVM đích bật JMX connector và network cho phép truy cập. JMX RMI có thể sử dụng registry port và RMI stub port khác nhau, đặc biệt cần chú ý khi chạy trong NAT, Docker hoặc Kubernetes.

## Credentials và bảo mật

```java
Map<String,Object> env = new HashMap<>();
env.put(JMXConnector.CREDENTIALS, new String[] {username, password});
factory.setEnvironment(env);
```

Lấy username và password từ secret management; không hardcode hoặc log credentials. Bảo mật JMX cần authentication, authorization, TLS hoặc transport security và network isolation phía server. Client environment không tự bảo mật endpoint.

## Inject connection vào service

```java
import javax.management.MBeanServerConnection;
import javax.management.ObjectName;

public final class RemoteWorkerMonitor {
    private final MBeanServerConnection connection;

    public RemoteWorkerMonitor(MBeanServerConnection connection) {
        this.connection = connection;
    }

    public int activeWorkers() throws Exception {
        ObjectName name = new ObjectName(
            "com.example.app:type=WorkerPool,name=main");
        return (Integer) connection.getAttribute(name, "ActiveWorkers");
    }
}
```

Khi có nhiều remote connections, dùng `@Qualifier("ordersJmxConnection")` để inject đúng JVM. Remote call có thể timeout, không được xem như truy cập field Java local.

## Truy vấn metadata và gọi operation

```java
ObjectName pattern = new ObjectName("com.example.app:type=WorkerPool,*");
for (ObjectName name : connection.queryNames(pattern, null)) {
    System.out.println(name.getCanonicalName());
    var info = connection.getMBeanInfo(name);
    for (var attribute : info.getAttributes()) {
        System.out.println(attribute.getName() + ":" + attribute.getType());
    }
}

ObjectName target = new ObjectName(
    "com.example.app:type=WorkerPool,name=main");
connection.invoke(target, "resize",
    new Object[] {Integer.valueOf(12)}, new String[] {"int"});
```

JMX `invoke` yêu cầu signature theo kiểu khai báo của method. `resize(int)` dùng `"int"`, không phải `"java.lang.Integer"` dù mảng `Object[]` chứa giá trị boxed. Nên đọc `MBeanInfo` trước khi hardcode tên operation, parameter type hoặc writable attribute.

## Lifecycle, lỗi mạng và retry

Với Java JMX trực tiếp, có thể dùng `JMXConnectorFactory.connect(url)` trong `try-with-resources` để đóng connector khi xong. Với Spring FactoryBean, vòng đời connector thường do context quản lý theo implementation, cần tránh đóng connection đang được singleton bean khác sử dụng.

Nếu JVM đích restart, reference `MBeanServerConnection` phía client vẫn tồn tại nhưng transport có thể hỏng. `@Lazy` không tự bảo đảm reconnect. Khi cần giám sát lâu dài, thiết kế health checks, retry với backoff và quản lý connection. **Không retry mù operation có tác dụng phụ** khi timeout: server có thể đã xử lý request nhưng response bị mất.

| Lỗi | Hướng xử lý |
|---|---|
| `IOException` | Kiểm tra network, JMX RMI endpoint, hostname và port |
| `SecurityException` | Kiểm tra credentials và quyền JMX phía server |
| `InstanceNotFoundException` | Xác minh ObjectName, đúng JVM và MBean registration |
| `AttributeNotFoundException` | So attribute với `MBeanInfo` |
| `ReflectionException` | Kiểm tra operation name và signature |
| `MBeanException` | Xem exception từ business MBean |
| `ListenerNotFoundException` | Kiểm tra lifecycle notification listener |

Notification listener có thể được đăng ký bằng `connection.addNotificationListener(name, listener, filter, handback)` và hủy bằng `removeNotificationListener`. Nếu reconnect, subscription thường phải được thiết lập lại; JMX Notifications không mặc định replay các event bị bỏ lỡ.

## Thực hành

1. Cấu hình FactoryBean tới một JMX server thử nghiệm đã bảo mật và dùng `queryNames` để liệt kê MBeans.
2. Đọc `java.lang:type=Memory` với attribute `HeapMemoryUsage` (thường là `CompositeData` qua JMX MXBean mapping).
3. Thử gọi một operation an toàn với đúng signature; kiểm tra bằng metadata thay vì đoán kiểu.
4. Ngắt kết nối remote và quan sát `IOException`; thiết kế reconnect với backoff.
5. Tắt JVM đích sau khi đăng ký listener; xác định cơ chế đăng ký lại khi connection khôi phục.

## Ghi nhớ

`MBeanServerConnectionFactoryBean` chuyển cấu hình JMX endpoint thành dependency `MBeanServerConnection` trong Spring. Nó giúp tách hạ tầng kết nối khỏi code giám sát, nhưng không thay thế việc export MBean ở JVM đích, không bảo đảm reconnect tự động và không miễn trừ yêu cầu bảo mật JMX. Thiết kế đúng cần quản lý ObjectName, metadata, quyền truy cập, timeout, lifecycle và retry an toàn.
