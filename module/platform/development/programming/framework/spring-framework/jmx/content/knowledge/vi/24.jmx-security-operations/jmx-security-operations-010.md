# Quy trình tắt hoặc thu hồi remote JMX trong Spring Framework

## 1. Mục tiêu và phạm vi

Remote JMX cho phép công cụ vận hành truy cập `MBeanServer` qua một kết nối từ JVM hoặc máy khác. Cấu hình phổ biến sử dụng JMX RMI, có thể được khởi động bởi **JVM management agent**, một `JMXConnectorServer` viết bằng Java, hoặc thành phần Spring như `ConnectorServerFactoryBean`.

Khi phát hiện kết nối không còn cần thiết, credential bị lộ, thay đổi chính sách bảo mật hoặc chuẩn bị ngừng ứng dụng, đội vận hành phải biết **tắt hoặc thu hồi remote JMX một cách có kiểm soát**. Chỉ đóng một cổng firewall đôi khi chưa đủ; chỉ gọi `stop()` trên một connector cũng chưa bảo đảm các connector khác không còn hoạt động.

Bài này hướng dẫn phân biệt các mục tiêu:

- **Tạm chặn truy cập mạng:** client mới không đi qua lớp mạng đã chặn, nhưng connector trong JVM có thể vẫn đang chạy.
- **Dừng JMX remote connector:** ngừng một endpoint cụ thể do ứng dụng/JVM sở hữu.
- **Thu hồi credential hoặc quyền:** làm mất hiệu lực khả năng xác thực/ủy quyền của principal hoặc secret bị lộ.
- **Gỡ cấu hình để không tự mở lại:** điều chỉnh JVM options, Spring configuration và deployment.
- **Xác minh không còn đường truy cập từ xa:** kiểm tra cấu hình có hiệu lực và thử kết nối theo góc nhìn của client đã được phép.

Một quy trình an toàn cần xét **khả năng tái khởi động**, **các phiên/kết nối đang tồn tại**, **tính liên tục của monitoring** và **khả năng rollback**.

## 2. Bản đồ các đường remote JMX có thể tồn tại

Không phải ứng dụng nào cũng mở JMX cùng một cách:

```text
                          JVM ứng dụng
                +---------------------------+
                |        MBeanServer        |
                |             ^             |
                |             |             |
                |  JVM management agent     | <-- JVM flags / launcher
                |             |             |
                |  ConnectorServerFactoryBean| <-- Spring context
                |             |             |
                |  Custom JMXConnectorServer | <-- code/library
                +-------------|-------------+
                              |
                    RMI Registry / RMI stub
                              |
                    Network / firewall
                              |
                    Remote management client
```

Ba nguồn có thể cùng tồn tại trong một JVM. Ví dụ đội phát triển tắt `ConnectorServerFactoryBean` nhưng JVM vẫn được khởi động với `-Dcom.sun.management.jmxremote.port=...`; kết quả là remote JMX vẫn nghe cổng.

Vì vậy, bước đầu của mọi quy trình thu hồi là **kiểm kê chủ sở hữu connector**, không bắt đầu bằng việc sửa ngẫu nhiên một property.

## 3. Phân biệt local JMX và remote JMX

Local JMX thường được công cụ trong cùng JVM hoặc cơ chế attach cục bộ của JDK sử dụng. Remote JMX cần một connector/network endpoint để client ở xa tạo `MBeanServerConnection`.

- `MBeanExporter` đăng ký MBean vào `MBeanServer`.
- `JMXConnectorServer` công bố quyền truy cập server đó qua một connector.
- `RMI Registry` phục vụ lookup stub nếu connector dùng mô hình JNDI/RMI.
- JVM management agent có thể mở endpoint remote theo cấu hình riêng của JVM.
- `spring.jmx.enabled` liên quan khả năng Spring export MBean, **không phải công tắc bảo đảm mọi remote JMX connector đã tắt**.

Trong nhiều tình huống, cần **giữ MBean local** cho chẩn đoán tại JVM nhưng **ngăn client từ xa**. Đừng vội vô hiệu hóa toàn bộ export MBean khi mục tiêu chỉ là thu hồi network access.

## 4. Quy trình chuẩn theo giai đoạn

Một runbook nên có bốn pha:

1. **Xác định phạm vi và mức độ khẩn cấp:** endpoint nào, JVM nào, ai đang dùng, có credential compromise không.
2. **Cắt đường truy cập mới:** dùng biện pháp phù hợp tại firewall/security group/network policy hoặc stop connector.
3. **Loại bỏ nguồn tái kích hoạt:** thay đổi launch flags, Spring config, secret và deployment.
4. **Xác minh và ghi nhận:** kiểm tra listener/endpoint, thử kết nối có kiểm soát từ client, cập nhật monitoring, audit và rollback plan.

Đối với sự cố credential bị lộ, ưu tiên containment ngay ở lớp mạng/identity, sau đó triển khai thay đổi bền vững. Đối với shutdown theo kế hoạch, thông báo chủ sở hữu giám sát để dashboard và cảnh báo không tạo tín hiệu giả.

## 5. Kiểm kê cấu hình JVM management agent

Với remote JMX do JVM agent cung cấp, các property thường gặp:

```text
-Dcom.sun.management.jmxremote
-Dcom.sun.management.jmxremote.port=9010
-Dcom.sun.management.jmxremote.rmi.port=9011
-Djava.rmi.server.hostname=jmx.example.internal
-Dcom.sun.management.jmxremote.authenticate=true
-Dcom.sun.management.jmxremote.ssl=true
```

Một số môi trường còn cấu hình password file, access file, SSL socket factories hoặc management agent qua công cụ attach. Không suy ra remote JMX được bảo vệ chỉ từ việc có `authenticate=true`; cần kiểm tra certificate, policy, file permissions và cách credential được phân phối.

Để **ngừng khởi động remote agent ở lần chạy sau**:

- Xác định nguồn các JVM options: systemd unit, container command, `JAVA_TOOL_OPTIONS`, `JDK_JAVA_OPTIONS`, script startup, IDE, helm chart hoặc platform configuration.
- Gỡ/sửa những option thực sự kích hoạt remote listener theo phiên bản JDK và launcher.
- Không chỉ thay hostname/port sang địa chỉ khác mà vẫn để connector mở nếu mục tiêu là tắt hoàn toàn.
- Redeploy/restart JVM theo quy trình bảo trì phù hợp để cấu hình mới có hiệu lực.
- Sau restart, xác nhận không còn remote connector ngoài ý muốn.

**Chú ý:** Xóa một dòng cấu hình ở repository không làm dừng agent đang chạy. Cần thao tác runtime và xác minh trên tiến trình thực.

## 6. Tắt connector do Spring quản lý

Nếu ứng dụng dùng `ConnectorServerFactoryBean`, lifecycle của Spring context có thể start/stop `JMXConnectorServer` mà factory sở hữu. Ví dụ:

```java
import javax.management.MBeanServer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.support.ConnectorServerFactoryBean;

@Configuration
public class RemoteJmxConfiguration {

    @Bean
    ConnectorServerFactoryBean remoteConnector(
            MBeanServer mbeanServer) throws Exception {
        ConnectorServerFactoryBean factory =
            new ConnectorServerFactoryBean();
        factory.setServer(mbeanServer);
        factory.setServiceUrl(
            "service:jmx:rmi:///jndi/rmi://127.0.0.1:9010/jmxrmi"
        );
        return factory;
    }
}
```

Đây là skeleton minh họa; registry, authentication và TLS chưa được cấu hình đầy đủ.

Nếu remote JMX được điều khiển bởi Spring configuration, một cách thiết kế rõ ràng là đặt connector bean sau một property:

```java
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;

@Configuration
public class OptionalRemoteJmxConfig {

    @Bean
    @ConditionalOnProperty(
        name = "management.remote-jmx.enabled",
        havingValue = "true"
    )
    ConnectorServerFactoryBean remoteConnector(
            MBeanServer server) throws Exception {
        var factory = new ConnectorServerFactoryBean();
        factory.setServer(server);
        factory.setServiceUrl(
            "service:jmx:rmi:///jndi/rmi://127.0.0.1:9010/jmxrmi"
        );
        return factory;
    }
}
```

`management.remote-jmx.enabled` ở đây là **property tùy chỉnh do ứng dụng định nghĩa**, không phải property Spring Boot tiêu chuẩn. Chọn mặc định an toàn là không tạo bean khi property không được bật.

Để áp dụng thay đổi cho một context đang chạy, đa số cấu hình tĩnh cần restart/recreate context; thay property trong file cấu hình không tự động hủy một bean đã được tạo. Nếu có cơ chế runtime toggle, phải thiết kế đồng bộ và lifecycle stop/restart rõ ràng.

## 7. Dừng custom JMXConnectorServer theo lifecycle

Với connector được tạo bằng JMX API:

```java
import javax.management.remote.JMXConnectorServer;

public final class JmxConnectorOwner
        implements AutoCloseable {

    private final JMXConnectorServer connector;

    public JmxConnectorOwner(JMXConnectorServer connector) {
        this.connector = connector;
    }

    @Override
    public void close() throws Exception {
        connector.stop();
    }
}
```

Nếu component tạo connector qua `JMXConnectorServerFactory.newJMXConnectorServer`, việc gọi `stop()` phải do **cùng owner** quản lý. Không dừng một connector dùng chung cho các ứng dụng khác nếu không có thỏa thuận vận hành.

Các trường hợp cần xem kỹ:

- Connector có thể chưa start nhưng stop được gọi trong đường cleanup.
- Có thể có nhiều connector cùng gắn vào một `MBeanServer`.
- Registry RMI có thể vẫn chạy sau khi connector stop; registry tồn tại không nhất thiết nghĩa remote JMX còn hoạt động.
- Một số client hoặc luồng callback có thể đang dùng connection; cần xác minh thực tế sau khi stop.
- Nếu Spring container sở hữu connector, ưu tiên lifecycle của Spring thay vì một thread quản trị ngoài tự dừng nó không đồng bộ.

Không dùng `MBeanServer.unregisterMBean(...)` để thay thế việc stop connector. Unregister từng MBean chỉ xóa các đối tượng quản trị khỏi server; nó không tự đóng network endpoint.

## 8. Firewall và network policy: containment nhanh

Khi cần chặn truy cập khẩn cấp, đội vận hành có thể giới hạn ingress tới:

- Registry port của JMX RMI.
- RMI endpoint port thực tế được stub quảng bá.
- Các port connector phụ trợ nếu cấu hình có.
- Network segment dành riêng cho quản trị.

JMX RMI có thể dùng **hai port**: một port registry để lookup và một port RMI endpoint để gọi. Đóng mỗi registry port có thể chặn lookup mới nhưng không nên coi đó là bằng chứng rằng mọi kết nối/endpoint RMI đang tồn tại đã hết hiệu lực.

Trong Docker/Kubernetes, cần xem cả host port mapping, pod/service networking, firewall, security group, network policy và port-forward/tunnel. Không chỉ nhìn container `EXPOSE` hoặc một rule riêng lẻ.

Cách vận hành:

1. Xác định endpoint thực tế và route từ các client.
2. Áp dụng deny rule hoặc allowlist chỉ những nguồn được cấp phép.
3. Kiểm tra tác động tới monitoring phụ thuộc JMX.
4. Xác minh từ mạng client bằng một phép thử kết nối phù hợp.
5. Lưu thay đổi vào infrastructure-as-code để không bị ghi đè trong deployment tiếp theo.

Cắt truy cập mạng là một **biện pháp containment**, không thay thế việc dừng connector hoặc thu hồi credential khi cần.

## 9. Thu hồi credential và quyền truy cập

Nếu secret JMX bị lộ, chỉ đổi port không đủ: credential cũ vẫn có thể dùng tại endpoint khác hoặc khi endpoint mở lại.

Một quy trình thu hồi nên:

1. Xác định tất cả tài khoản/credential được connector chấp nhận.
2. Xác định secret được lưu ở đâu: password file, secret store, deployment variable, client configuration.
3. Thu hồi hoặc rotate credential trên **server**, rồi cập nhật client được phép.
4. Kiểm tra quyền truy cập của từng role/tài khoản; thu hẹp quyền nếu cần.
5. Xác minh credential cũ không còn tạo được session mới.
6. Xác minh credential mới hoạt động với client hợp lệ khi dịch vụ vẫn được duy trì.
7. Kiểm tra khả năng tồn tại session đã xác thực trước khi rotate.

Với cơ chế dùng password/access file của JVM management agent, thay đổi file có thể không làm tất cả connector đang chạy lập tức áp dụng policy mới; hành vi phụ thuộc implementation và cách khởi tạo. Hãy kiểm tra và thực hiện restart connector/JVM nếu cần để bảo đảm thu hồi thực sự có hiệu lực.

Khi nghi ngờ credential compromise, **rotation chỉ là một bước**. Cần xem audit/network logs, rà soát operation nguy hiểm đã bị gọi và giải quyết mọi session hoặc route còn tồn tại.

## 10. Bảo mật kết nối khi không thể tắt hoàn toàn

Trong một số hệ thống, JMX remote vẫn cần cho vận hành. Thay vì mở rộng quyền, thiết kế lại truy cập:

- Dùng mạng quản trị tách biệt hoặc tunnel/VPN có kiểm soát.
- Bật authentication và phân quyền theo nhu cầu tối thiểu.
- Bảo vệ traffic bằng TLS và xác minh danh tính endpoint.
- Đặt hostname và cổng RMI cố định, dễ kiểm soát bằng firewall.
- Hạn chế các MBean/operation nhạy cảm.
- Ghi audit cho truy cập và thao tác thay đổi trạng thái.
- Giới hạn số lượng client và theo dõi hoạt động bất thường.
- Không cung cấp mật khẩu/JMX URL kèm secret qua tài liệu công khai.

JMX connector security và ứng dụng Spring Security không hoàn toàn giống nhau. Rule HTTP cho `/actuator/**` không tự bảo vệ RMI connector.

## 11. Phân biệt dừng remote JMX với tắt Spring JMX export

Một số cấu hình Spring Boot dùng:

```properties
spring.jmx.enabled=false
```

Property này có thể vô hiệu hóa cơ chế JMX export của Spring Boot theo auto-configuration tương ứng. Nhưng nếu JVM management agent vẫn được bật bằng `-Dcom.sun.management.jmxremote.port`, remote connector vẫn có thể hoạt động và công bố các MBean nền tảng của JVM.

Ngược lại, tắt JVM remote agent không nhất thiết xóa những MBean local do Spring đã đăng ký.

Phân biệt mục tiêu:

| Mục tiêu | Cơ chế nên xem xét |
| --- | --- |
| Không cho máy khác truy cập JMX | Stop remote connectors; network isolation; authentication |
| Không export MBean do Spring quản lý | Spring JMX/exporter configuration |
| Không expose Actuator endpoint qua JMX | `management.endpoints.jmx.exposure.*` và cấu hình Actuator |
| Thu hồi người dùng JMX cụ thể | Credential store/identity/access policy |
| Không còn listener network sau restart | Startup flags, connector bean, infra manifests |
| Dọn MBean sau khi context đóng | Exporter unregister và lifecycle context |

Đừng coi việc tắt một lớp là chứng nhận mọi lớp đã tắt.

## 12. Kiểm tra trạng thái trước và sau thay đổi

Trước khi tắt:

- Ghi nhận hostname, PID/JVM, container/pod, deployment version.
- Ghi nhận connector owner và service URL, registry/RMI ports.
- Liệt kê danh sách client/monitoring thực sự sử dụng endpoint.
- Ghi nhận credential/authorization mechanism mà không lưu secret.
- Xác nhận phương án rollback theo thay đổi được phép.

Sau khi tắt, xác minh ở hai hướng:

### 12.1. Phía server

Kiểm tra JVM startup arguments và cấu hình runtime, những process đang lắng nghe trên cổng quản trị, những connector beans còn hoạt động, registry bindings và các tuyến truy cập nội bộ.

Một cổng TCP không còn mở là một tín hiệu hữu ích nhưng **không chứng minh mọi connector đã dừng** nếu ứng dụng có nhiều endpoint.

### 12.2. Phía client

Thử tạo kết nối từ một client đã từng truy cập được:

```java
import javax.management.remote.JMXConnectorFactory;
import javax.management.remote.JMXServiceURL;

JMXServiceURL url = new JMXServiceURL(
    "service:jmx:rmi:///jndi/rmi://jmx.example.internal:9010/jmxrmi"
);

try (var connector =
        JMXConnectorFactory.connect(url)) {
    throw new IllegalStateException(
        "Unexpected: remote JMX is still reachable"
    );
} catch (java.io.IOException expected) {
    System.out.println("Remote JMX unavailable via this path");
}
```

Đoạn trên chỉ chứng minh **một đường kết nối cụ thể không thành công**. `IOException` có thể do DNS hoặc mạng bị lỗi, không nhất thiết do connector đã tắt. Với mô hình xác thực, test cần phân biệt tình huống credential cũ bị từ chối và tình huống endpoint không còn tồn tại. Một lần thử không đủ để kết luận mọi mạng/client đều đã bị thu hồi.

Để kiểm thử thu hồi credential, thử credential cũ (không log secret) và mong đợi authentication bị từ chối, rồi thử credential hợp lệ mới nếu vẫn cho phép một số client.

## 13. Session và kết nối đang tồn tại

Với kết nối JMX RMI, điều hành viên thường quan tâm liệu thao tác thu hồi có cắt cả phiên đang mở hay không.

- **Chặn ingress mới** không luôn đóng ngay những TCP session đã thiết lập.
- **Rotate credential** không mặc nhiên hủy mọi session đã xác thực từ trước.
- **Stop connector** có thể khiến kết nối/operation ngừng hoạt động tùy implementation, nhưng cần kiểm tra hành vi của client đang giữ stub.
- **Restart JVM** thường đóng toàn bộ connector thuộc process, nhưng cũng gây gián đoạn ứng dụng và cần được phê duyệt theo yêu cầu uptime.

Khi xử lý sự cố nghiêm trọng, cần kiểm tra các session hiện có bằng những bằng chứng khả dụng: connection audit, network flows, client disconnect hoặc bài test giữ một client connection trước khi containment rồi thử thao tác sau containment.

Không khẳng định đã thu hồi hoàn toàn cho đến khi các phiên hiện hành và đường mở lại đã được xử lý theo threat model.

## 14. Shutdown graceful và vận hành production

Khi tắt theo kế hoạch, một quy trình hợp lý là:

1. Thông báo thời điểm tắt remote JMX và lý do.
2. Xác nhận dashboard/alerting đang phụ thuộc JMX, chuyển sang nguồn metrics phù hợp nếu có.
3. Tạm ngăn tạo session mới nếu thiết kế hỗ trợ.
4. Dừng hoặc đóng connector qua lifecycle owner.
5. Kiểm tra không còn listener/registry bindings không mong muốn.
6. Sửa nguồn cấu hình để connector không tự bật sau restart.
7. Restart/redeploy nếu cần.
8. Thử truy cập từ các network zone và credential liên quan.
9. Cập nhật tài liệu vận hành, inventory, runbook và change record.

Không tắt MBean exporter nếu vẫn có monitoring local hoặc application code cần `MBeanServer`. Và không unregister toàn bộ MBean của JVM để “đảm bảo an toàn”: thao tác đó có thể phá công cụ quản lý bộ nhớ, thread và monitoring của thành phần khác.

## 15. Redeploy và vấn đề RMI Registry còn tồn tại

Khi application server hoặc container giữ JVM lâu hơn một Spring `ApplicationContext`, connector có thể bị tạo lại nhiều lần. Nếu shutdown context không stop connector đúng:

- Port vẫn bị chiếm khi khởi động lần sau.
- Binding `jmxrmi` có thể trỏ tới endpoint cũ.
- Classloader của deployment cũ có thể bị giữ bởi registry, connector hoặc listener.
- Client nhận stub đã lỗi và không kết nối được.
- Một cấu hình `IGNORE_EXISTING` với MBean có thể che lỗi cleanup ở registry MBean nhưng không sửa connector.

Trong integration test/redeploy, thực hiện:

```text
Start context A -> remote JMX works
Close context A -> endpoint and owned registration disappear
Start context B -> remote JMX works with new instance
Close context B -> no leftover connector/registration
```

Nếu registry do một service chung sở hữu, không unexport registry chung chỉ để dọn connector của context A. Tách ownership của registry khỏi ownership của connector.

## 16. Checklist thu hồi khẩn cấp

Trong sự cố truy cập trái phép hoặc credential compromise:

- [ ] Xác định JVM/deployment, RMI Registry và endpoint RMI liên quan.
- [ ] Chặn ingress từ nguồn không tin cậy tại mạng phù hợp.
- [ ] Kiểm kê mọi connector do JVM agent, Spring hoặc thư viện tạo.
- [ ] Stop connector không còn cần thiết bằng owner hợp lệ.
- [ ] Rotate/revoke credential, cập nhật access policy của server.
- [ ] Xử lý session đã tồn tại theo mức độ rủi ro.
- [ ] Gỡ launcher flags và Spring config có thể mở lại endpoint.
- [ ] Kiểm tra secret trong logs, env, config và deployment templates.
- [ ] Thử kết nối từ phía client ở các network zone cần kiểm chứng.
- [ ] Ghi lại kết quả, người thực hiện, thời gian và phạm vi.
- [ ] Theo dõi khởi động/redeploy để phát hiện remote JMX mở lại.
- [ ] Đảm bảo service monitoring thay thế có sẵn khi cần.

## 17. Ma trận lỗi sau khi tắt

| Hiện tượng | Nguyên nhân khả dĩ | Hướng xử lý |
| --- | --- | --- |
| Cổng registry đã đóng nhưng client cũ vẫn hoạt động | Session/endpoint RMI đang mở | Kiểm tra RMI server port, flow hiện tại |
| Tắt Spring connector nhưng port còn mở | JVM management agent hoặc connector khác | Kiểm kê tất cả owners |
| Xóa JVM flags rồi vẫn mở | Process chưa restart hoặc flags đến từ nguồn khác | Kiểm tra effective startup command |
| Credential cũ vẫn login được | Secret chưa apply, connector cache hoặc session cũ | Kiểm tra cơ chế auth và restart có kiểm soát |
| Không thấy cổng nhưng một service nội bộ vẫn truy cập | Network path khác hoặc endpoint khác | Kiểm kê bind addresses/routes |
| Dashboard mất metrics | Monitoring phụ thuộc remote JMX | Chuyển scrape/exporter hoặc nguồn khác |
| Redeploy mở lại connector | Config/helm/template chưa được sửa | Cập nhật infrastructure-as-code |
| Lỗi `Address already in use` | Registry hoặc connector cũ chưa cleanup | Kiểm tra ownership, stop/unexport |
| Chỉ tắt `spring.jmx.enabled` nhưng client vẫn kết nối | Agent/connector độc lập Spring vẫn chạy | Stop remote agent/connector |

Ma trận này hướng chẩn đoán, không thay thế bằng chứng xác minh theo môi trường cụ thể.

## 18. Kiểm thử regression: remote JMX không tự mở lại

Một bài kiểm thử pipeline hoặc môi trường staging có thể xác nhận:

1. Deploy ứng dụng với cấu hình remote JMX disabled.
2. Kiểm tra JVM startup arguments không chứa remote agent flags ngoài ý muốn.
3. Kiểm tra Spring context không có connector bean đang chạy theo cấu hình tùy chỉnh.
4. Thử kết nối tới những cổng JMX được phép dùng trước đây từ network phù hợp.
5. Restart JVM/application context.
6. Thử lại từ client, bảo đảm trạng thái disabled được giữ.
7. Khi có config profile mới, xác minh nó không override property và bật lại connector.
8. Xác nhận local MBean monitoring còn hoạt động nếu đó là yêu cầu vận hành.

Đừng dùng một phép thử `isRegistered` trên `MBeanServer` để chứng minh remote JMX đã tắt: local MBean có thể vẫn tồn tại dù connector network đã dừng. Cũng đừng dùng một lần timeout để kết luận chính sách security hoạt động đúng.

## 19. Ghi nhớ

**Tắt hoặc thu hồi remote JMX là một bài toán nhiều lớp:** xác định mọi connector, chặn đường mạng khi cần, stop endpoint đúng lifecycle, thu hồi credential/quyền và sửa cấu hình để tránh tự mở lại. `spring.jmx.enabled=false` chỉ tác động đến một phần của hệ thống Spring JMX, không tự đóng JVM management agent độc lập. Xác minh phải diễn ra cả phía server lẫn phía client, phân biệt kết nối mới với session đã tồn tại, và có kiểm thử restart/redeploy để đảm bảo kết quả bền vững.
