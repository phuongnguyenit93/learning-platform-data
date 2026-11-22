# Spring Framework JMX — Kiểm thử quyền truy cập và lỗi xác thực

## 1. Mục tiêu

Kiểm thử bảo mật Spring JMX phải kiểm chứng hai giai đoạn độc lập: authentication tại JMX connector (xác định danh tính) và authorization (quyết định quyền đọc/ghi thuộc tính, gọi operation). Mục tiêu không chỉ nhận exception khi bị từ chối mà còn xác nhận rằng trạng thái của MBean không thay đổi sau thao tác không được phép.

## 2. Kiến trúc

```text
JMX client / credentials
   -> JMXConnectorServer / JMXAuthenticator
   -> authorization policy
   -> MBeanServer
   -> Spring MBeanExporter / exported MBean
   -> getAttribute / setAttribute / invoke
```

Spring Security `@PreAuthorize` và bảo mật JMX connector là hai cơ chế khác nhau. Method security chỉ hoạt động khi lời gọi đi qua Spring AOP proxy và có Authentication hợp lệ. Một JMX connector không tự chuyển đăng nhập JMX thành Spring SecurityContext; vì thế phải kiểm thử cả connector policy và phương thức nghiệp vụ khi cần.

## 3. Phân biệt authentication và authorization

| Tình huống | Phân loại |
|---|---|
| Username hoặc password sai ở bước connect | Authentication failure |
| Không cung cấp credentials khi server bắt buộc | Authentication failure |
| User read-only kết nối được nhưng không thể ghi | Authorization denial |
| User có quyền đọc nhưng không được invoke resetJobs | Authorization denial |
| DNS không resolve | Transport error |
| TLS certificate không được tin cậy | TLS/transport error |
| MBean không tồn tại | Registry error |
| Operation signature sai | Contract/invocation error |

Không nên đếm lỗi network, ObjectName hoặc MBean method thành login failure. Nếu dùng SecurityException, phải xác định nó xuất hiện tại giai đoạn nào.

## 4. Chuẩn bị MBean fixture

```java
public interface TestControlMBean {
    int getJobs();
    int getLimit();
    void setLimit(int limit);
    void resetJobs();
}

public class TestControl implements TestControlMBean {
    private int jobs = 5;
    private int limit = 10;
    public synchronized int getJobs() { return jobs; }
    public synchronized int getLimit() { return limit; }
    public synchronized void setLimit(int value) {
        if (value < 1 || value > 100) throw new IllegalArgumentException();
        limit = value;
    }
    public synchronized void resetJobs() { jobs = 0; }
}
```

Đăng ký trong một MBeanServer dành riêng cho test:

```java
MBeanServer server = MBeanServerFactory.newMBeanServer("test");
ObjectName name = new ObjectName("com.example.test:type=Control,name=fixture");
server.registerMBean(new TestControl(), name);
```

Test data phải tách khỏi production. Dùng namespace ObjectName riêng, hủy registration khi xong, không gọi operation nguy hiểm trên môi trường thật.

## 5. Thiết kế ma trận quyền

| Principal | Connect | Read Jobs | Write Limit | Invoke resetJobs |
|---|---|---|---|---|
| Invalid credentials | Denied | N/A | N/A | N/A |
| monitor | Allowed | Allowed | Denied | Denied |
| operator | Allowed | Allowed | Allowed | Denied |
| admin | Allowed | Allowed | Allowed | Allowed |

Ma trận trên là policy đề xuất cho môi trường test, không phải quyền mặc định của JMX. Phải cấu hình authorization enforcement tại JMX connector, MBeanServer wrapper hoặc lớp quản trị tin cậy, rồi mới có ý nghĩa khi assert.

## 6. Test credential sai

```java
Map<String, Object> env = Map.of(
    JMXConnector.CREDENTIALS,
    new String[] {"monitor", "wrong-password"}
);

assertThrows(SecurityException.class, () -> {
    try (JMXConnector ignored = JMXConnectorFactory.connect(url, env)) {
        // Kết nối không được thành công.
    }
});
```

Loại exception cụ thể có thể khác theo JMX provider hoặc bị bọc. Kiểm tra contract của implementation, không so sánh nguyên văn một error message dễ thay đổi. Test các trường hợp credential trống, sai user, sai password, bị revoke, và credential mới sau rotation. Giới hạn số lần thử để không gây account lockout.

## 7. Test quyền đọc, ghi và invoke

Đọc thuộc tính:

```java
int jobs = (Integer) connection.getAttribute(name, "Jobs");
```

Ghi thuộc tính:

```java
connection.setAttribute(name, new Attribute("Limit", 20));
```

Gọi operation:

```java
connection.invoke(name, "resetJobs", new Object[0], new String[0]);
```

Với user monitor, xác nhận thao tác ghi bị từ chối và giá trị không đổi:

```java
int before = (Integer) connection.getAttribute(name, "Limit");
assertThrows(SecurityException.class, () ->
    connection.setAttribute(name, new Attribute("Limit", before + 1))
);
int after = (Integer) connection.getAttribute(name, "Limit");
assertEquals(before, after);
```

Nếu provider bọc SecurityException, assert cause chain đúng thay vì chỉ assert một loại. Với operation có tác dụng phụ, cần kiểm tra counter hoặc fake service không hề được gọi; chỉ thấy exception chưa chứng minh state không thay đổi.

## 8. Kiểm thử Spring Security proxy

```java
@ManagedOperation
@PreAuthorize("hasAuthority('ops:reset')")
public void resetJobs() { /* ... */ }
```

Để method security hiệu lực, ứng dụng phải bật infrastructure như `@EnableMethodSecurity`, lời gọi phải đi qua AOP proxy, và security context phải có danh tính phù hợp. JMX connector thread không mặc định có HTTP Authentication. Nếu MBeanExporter export raw target và gọi trực tiếp target method, proxy advice có thể bị bypass.

Giải pháp dễ kiểm thử là một JMX management facade nhỏ, inject business service qua Spring proxy. Integration test phải chứng minh: principal không đủ quyền khiến call bị chặn trước side effect; principal đủ quyền cho phép đúng một lần gọi. Nếu dùng JDK dynamic proxy, operation muốn gọi qua proxy cần có trong interface; self-invocation cũng có thể bypass method-security advice.

## 9. Phân loại lỗi

| Exception | Nhóm vấn đề |
|---|---|
| UnknownHostException / ConnectException | DNS hoặc mạng |
| SSLHandshakeException | TLS, certificate, trust |
| SecurityException ở connect | Authentication hoặc connector policy |
| SecurityException khi invoke | Authorization hoặc policy |
| InstanceNotFoundException | Sai ObjectName hoặc server |
| AttributeNotFoundException | Sai tên hoặc quyền attribute |
| ReflectionException | Sai operation signature |
| MBeanException | Logic MBean ném lỗi |

Không tự động retry operation đã gửi khi client timeout, vì server có thể đã thực thi xong mà response bị mất. Kiểm tra idempotency và hậu trạng thái trước khi gọi lại.

## 10. Audit và kiểm thử vận hành

Audit event nên ghi thời điểm, logical target, connector type, outcome, failure category và principal đã được xác thực nếu được phép. Không ghi password, token, credential map hoặc dữ liệu bí mật. Metrics có thể gồm `jmx_authentication_failures_total`, `jmx_authorization_denials_total` và `jmx_connect_failures_total{category}` — đây là tên minh họa do ứng dụng định nghĩa.

Test cleanup gồm đóng JMXConnector bằng try-with-resources, dừng JMXConnectorServer, unregister MBean fixture, giải phóng cổng RMI và không để lại tài khoản test có quyền cao. Với CI, dùng loopback và port được quản lý; tránh hardcode port gây va chạm. Đừng kiểm thử brute-force hoặc lockout trên tài khoản production.

## 11. Bài thực hành

1. Tạo MBean fixture có attribute đọc, attribute ghi và operation resetJobs; đăng ký trong test MBeanServer.
2. Tạo account monitor chỉ đọc; xác nhận connect và getAttribute thành công nhưng setAttribute và invoke bị từ chối.
3. Kiểm tra Limit và Jobs không thay đổi sau mỗi thao tác bị từ chối.
4. Dùng credential sai, xác nhận kết nối bị từ chối và có audit authentication failure.
5. Test operator được ghi Limit nhưng không được gọi resetJobs.
6. Test Spring @PreAuthorize qua JMX facade, xác minh AOP proxy thực sự tham gia đường invocation.
7. Ngắt kết nối hoặc dùng URL sai, xác nhận lỗi được phân loại transport thay vì login failure.

## 12. Kết luận

Kiểm thử quyền truy cập JMX không dừng ở việc kiểm tra connection thành công. Phải thử cả authentication failure và authorization denial, kiểm tra đọc/ghi/gọi operation theo từng principal, xác minh không có side effects khi bị từ chối và giữ log an toàn. Nếu dựa vào Spring Security, cần kiểm chứng đường gọi thực tế qua proxy; bảo mật connector và method security là hai ranh giới riêng, không tự thay thế nhau.