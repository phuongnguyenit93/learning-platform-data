# Spring Framework JMX: Giám sát lỗi connector và đăng nhập thất bại

## 1. Mục tiêu

Trong hệ thống dùng Spring Framework JMX, lỗi kết nối và lỗi đăng nhập tại JMX connector khiến client không thể đọc MBeans hoặc gọi operations. Bài học phân biệt network failure, TLS failure, authentication failure, authorization denial, MBean registration và business operation failure; đồng thời hướng dẫn logging, metrics, alerting, reconnect và bảo vệ thông tin nhạy cảm.

## 2. Đường đi của một yêu cầu JMX

```text
Spring JMX client -> JMXConnector -> network/RMI/TLS
                 -> JMX connector server -> authentication
                 -> authorization -> MBeanServer -> MBean
```

Một lỗi ở tầng trước có thể khiến tầng sau chưa được gọi. Ví dụ khi DNS không hoạt động thì chưa đến bước kiểm tra mật khẩu; khi kết nối thành công nhưng operation bị chặn, đó là authorization denial chứ không phải login failure.

| Lớp | Dấu hiệu | Kiểm tra |
|---|---|---|
| DNS/TCP | UnknownHostException, connection refused hoặc timeout | DNS, firewall, port |
| JMX RMI | Registry reachable nhưng RMI stub không kết nối | advertised hostname, RMI server port |
| TLS | SSLHandshakeException hoặc certificate không tin cậy | truststore, certificate, hostname |
| Authentication | Credentials không được chấp nhận | server authenticator, secret rotation |
| Authorization | Login thành công nhưng thao tác bị từ chối | policy, role và operation |
| MBean registry | InstanceNotFoundException | ObjectName, đúng server |
| Contract | AttributeNotFoundException hoặc ReflectionException | MBeanInfo, signature |
| Business | MBeanException, RuntimeMBeanException | target exception, trạng thái nghiệp vụ |

## 3. Giám sát phía JMX client

Với JMXConnectorFactory, ghi connect attempt, connect success/failure và độ trễ kết nối. Ví dụ các metric do ứng dụng tự định nghĩa:

- jmx_connect_attempts_total{target}
- jmx_connect_failures_total{target,category}
- jmx_connect_duration_seconds{target}
- jmx_connection_up{target}
- jmx_connection_last_success_timestamp_seconds{target}

Không đưa raw IP, URL chứa credentials hoặc username tự do vào metric labels vì nguy cơ rò rỉ và cardinality cao. Target nên là ID logic như orders-prod thay vì định danh động theo từng pod.

```java
long start = System.nanoTime();
try (JMXConnector connector =
        JMXConnectorFactory.connect(serviceUrl, environment)) {
    metrics.recordConnectSuccess(System.nanoTime() - start);
    MBeanServerConnection connection = connector.getMBeanServerConnection();
    connection.getDefaultDomain(); // phép thử đọc nhẹ
} catch (SecurityException ex) {
    metrics.recordConnectFailure("security");
    throw ex;
} catch (IOException ex) {
    metrics.recordConnectFailure("transport");
    throw ex;
}
```

Trong ví dụ, metrics là interface minh họa do ứng dụng định nghĩa. Không mặc định mọi SecurityException đều là sai mật khẩu; phải xác định giai đoạn xảy ra lỗi, provider và chuỗi nguyên nhân.

## 4. Theo dõi JMXConnectionNotification

JMXConnector hỗ trợ lifecycle notifications, gồm JMXConnectionNotification.OPENED, CLOSED, FAILED và NOTIFS_LOST. Đăng ký NotificationListener để cập nhật health và ghi nhận lỗi:

```java
NotificationListener listener = (notification, handback) -> {
    if (!(notification instanceof JMXConnectionNotification event)) return;
    switch (event.getType()) {
        case JMXConnectionNotification.OPENED -> monitoring.opened();
        case JMXConnectionNotification.CLOSED -> monitoring.closed();
        case JMXConnectionNotification.FAILED -> monitoring.failed();
        case JMXConnectionNotification.NOTIFS_LOST -> monitoring.lostEvents();
        default -> { }
    }
};
connector.addConnectionNotificationListener(listener, null, null);
```

Đây là ví dụ Java sử dụng switch arrow syntax; monitoring là dependency tự triển khai. Nếu client gọi JMXConnectorFactory.connect trước khi đăng ký listener, sự kiện OPENED ban đầu có thể đã phát. Vì vậy kết quả connect thành công phải được ghi riêng; listener không phải nguồn duy nhất cho connect success.

NOTIFS_LOST cho biết có thể mất notifications: cần đọc lại attributes hoặc MBean state để đồng bộ, không giả định những sự kiện bị mất có thể replay tự động.

## 5. Spring MBeanServerConnectionFactoryBean

Trong Spring, MBeanServerConnectionFactoryBean tạo MBeanServerConnection để inject:

```java
@Configuration
public class RemoteJmxConfiguration {
    @Bean
    public MBeanServerConnectionFactoryBean ordersConnection(
            @Value("${app.jmx.orders.url}") String url) throws Exception {
        var factory = new MBeanServerConnectionFactoryBean();
        factory.setServiceUrl(url);
        return factory;
    }
}
```

FactoryBean giảm boilerplate của client nhưng không mặc định cung cấp sẵn metrics, exactly-once operations hoặc reconnect tin cậy cho mọi cấu hình. Theo dõi startup exceptions, lời gọi sau khi kết nối, lifecycle và tình trạng endpoint. Nếu cần quan sát connector transport chi tiết, cân nhắc connection manager do ứng dụng quản lý kết hợp JMXConnectorFactory.

## 6. Authentication failure và authorization denial

Authentication xác định danh tính được chấp nhận khi kết nối. Authorization quyết định danh tính đã đăng nhập có được gọi operations hay đọc/ghi attributes hay không.

Ví dụ hai audit events khác nhau:

```json
{"event":"jmx.authentication","target":"orders-prod","outcome":"denied","category":"invalid_credentials"}
{"event":"jmx.authorization","target":"orders-prod","outcome":"denied","action":"resetQueue"}
```

Các event JSON chỉ minh họa schema do ứng dụng thiết kế. Đừng sử dụng một bộ đếm login failures cho cả hai trường hợp. Auth failure có thể do secret cũ sau rotation, client trỏ nhầm realm hoặc truy cập trái phép. Authorization denial có thể do monitoring account read-only cố gọi một operation ghi.

Ở server-side, một custom JMXAuthenticator hoặc connector integration có thể ghi số lần authentication success/failure. Không log credentials thô, mật khẩu, token, full environment map hoặc certificate private keys. Có thể log target ID, thời gian, loại lỗi và principal đã xác thực nếu chính sách cho phép.

## 7. Cảnh báo vận hành

Phân biệt một số loại cảnh báo:

1. Connector unavailable: health probe thất bại liên tục hoặc thời gian từ lần kết nối thành công cuối vượt ngưỡng.
2. Authentication failures tăng bất thường: có thể do credential rotation lỗi hoặc một nguồn liên tục thử kết nối.
3. Authorization denials ở operation nhạy cảm: điều tra quyền và nguồn yêu cầu.
4. TLS failures: kiểm tra certificate expiry, truststore và hostname.
5. JMXConnectionNotification.NOTIFS_LOST: đồng bộ lại state bằng read-only query.

Rule cần kết hợp tốc độ lỗi, số lỗi tối thiểu, baseline và tầm quan trọng target. Nếu chỉ xét failure ratio trên lượng kết nối rất nhỏ dễ gây false alert. Nếu connector hoàn toàn không thể liên lạc, authentication failures có thể bằng 0 dù dịch vụ không khả dụng.

## 8. Health check an toàn

Chọn thao tác đọc nhẹ, ví dụ kiểm tra một MBean marker ổn định:

```java
boolean healthy(MBeanServerConnection connection) {
    try {
        ObjectName marker = new ObjectName("java.lang:type=Memory");
        return connection.isRegistered(marker);
    } catch (Exception ex) {
        return false;
    }
}
```

Platform Memory MBean có thể không hiện diện trên một custom server, vì vậy môi trường đó nên dùng marker riêng. Không dùng setAttribute hoặc invoke(operation có side effects) làm health probe. Cần timeout, giới hạn concurrency và tần suất phù hợp.

## 9. Reconnect có backoff

Khi JVM đích restart hoặc network đứt:

- Đánh dấu connection degraded/unavailable.
- Tạo kết nối mới với exponential backoff và jitter, tránh vòng lặp dày.
- Đóng connector cũ khi thay thế và xác minh đúng server identity.
- Đăng ký lại notification listeners nếu cần.
- Đọc lại MBean state sau khoảng mất sự kiện.
- Không retry mù operation có tác dụng phụ nếu request trước timeout.

Nếu client gọi clearQueue rồi mất response, server có thể đã thực thi xong. Retry ngay có thể gây hành vi lặp ngoài ý muốn. Trạng thái không rõ phải được xử lý bằng kiểm tra hậu trạng thái hoặc một hợp đồng idempotent có request ID.

## 10. RMI, TLS và container

Với JMX RMI trong Docker/Kubernetes, registry port có thể truy cập được nhưng remote stub trỏ hostname hoặc server port không truy cập được. Kiểm tra java.rmi.server.hostname, cấu hình RMI server port, firewall/NAT, DNS, TLS và network policy. Không mở toàn bộ cổng hoặc tắt authentication để giải quyết nhanh lỗi. Thay vào đó xác định giai đoạn hỏng và sửa cấu hình tương ứng.

## 11. Kịch bản kiểm thử

| Kịch bản | Điều mong đợi |
|---|---|
| Host không resolve | Connection failure thuộc DNS/transport |
| Port đóng | Failure và reconnect backoff |
| Sai mật khẩu | Auth denial được ghi ở server boundary |
| Đúng mật khẩu nhưng thiếu quyền | Auth success, authorization denial riêng |
| Chứng chỉ không tin cậy | TLS handshake failure |
| JVM restart | Health down, reconnect và reconcile |
| Operation signature sai | Contract/invocation error, không tính login failure |
| ObjectName sai | InstanceNotFoundException, không tính auth failure |

Thực hiện kiểm thử credential không hợp lệ trong môi trường cho phép với số lần hữu hạn để tránh lockout hoặc gây ảnh hưởng production.

## 12. Bài thực hành

**Bài 1:** Phân loại UnknownHostException, SSLHandshakeException, SecurityException trong authenticate và InstanceNotFoundException vào các nhóm lỗi khác nhau.

**Bài 2:** Thiết kế các metrics connect_attempts_total, connect_failures_total{category,target} và connection_up{target}; giải thích vì sao không dùng password hoặc username tự do làm label.

**Bài 3:** Tạo NotificationListener xử lý FAILED và NOTIFS_LOST, cập nhật health metric và khởi tạo read-only reconcile sau reconnect.

**Bài 4:** Một tài khoản đọc được attributes nhưng không thể gọi shutdown(): đây thường là authorization denial, không nhất thiết là đăng nhập thất bại.

**Bài 5:** Khi resetCounters() timeout, giải thích tại sao không được retry mù nếu chưa biết kết quả phía server.

## 13. Tổng kết

Giám sát lỗi connector và đăng nhập thất bại trong Spring JMX cần quan sát cả client, connector server và MBean invocation. Hãy thu thập connect attempts, latency, failure category, trạng thái health và JMXConnectionNotification; phân biệt authentication với authorization, network, TLS và lỗi hợp đồng JMX. Bảo vệ secrets trong logs, dùng cảnh báo dựa trên baseline, reconnect có backoff, và không retry operation không idempotent khi kết quả không rõ. 
