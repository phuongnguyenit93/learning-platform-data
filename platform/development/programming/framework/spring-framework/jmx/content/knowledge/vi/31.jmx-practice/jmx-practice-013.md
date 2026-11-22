# Thực hành: Thiết lập checklist bảo mật cho remote JMX trong Spring Framework

## 1. Mục tiêu và bối cảnh

Remote JMX cho phép công cụ như JConsole, Java Mission Control hoặc monitoring agent kết nối từ một JVM/máy khác để đọc attributes, gọi operations và đăng ký nhận notifications. Cơ chế này rất hữu ích khi quản trị Spring application trong staging/production, nhưng đồng thời mở ra một **bề mặt quản trị nhạy cảm**: một MBean có thể phơi bày cấu hình, thông tin vận hành, dữ liệu nội bộ, thậm chí các thao tác thay đổi trạng thái như tạm dừng worker, reset thống kê hoặc đóng thành phần ứng dụng.

Bài thực hành thuộc **Spring Framework JMX → Thực hành**, tập trung xây dựng một **checklist bảo mật có thể thực thi và xác minh** trước khi bật remote JMX.

Sau bài này, bạn sẽ có thể:

- Giải thích sự khác nhau giữa **Spring MBeanExporter** và **remote JMX connector**.
- Thiết kế các lớp bảo vệ: xác thực, phân quyền, mã hóa, giới hạn mạng, quản lý secrets và kiểm soát operations.
- Hiểu vai trò của RMI registry port, RMI server port và `java.rmi.server.hostname`.
- Xây checklist áp dụng cho development, staging và production.
- Kiểm tra cả trường hợp **được phép** lẫn **bị từ chối** khi truy cập JMX.
- Nhận diện các cấu hình không an toàn như `authenticate=false`, `ssl=false`, public port hoặc quyền readwrite quá rộng.
- Đưa remote JMX vào quy trình vận hành có audit, rotation, rollback và kiểm tra định kỳ.

## 2. Remote JMX là gì và vì sao cần bảo vệ?

Một mô hình phổ biến:

```text
JConsole / JMC / Monitoring agent
                 |
                 |  JMX over RMI
                 v
        Network / firewall / TLS
                 |
                 v
        Remote JMX connector
                 |
                 v
             MBeanServer
                 |
          +------+------+
          |             |
    Platform MBeans   Spring MBeans
    java.lang:*      com.example:*
```

`MBeanServer` là registry JMX. Spring có thể dùng `MBeanExporter` hoặc annotation `@ManagedResource` để đưa ứng dụng vào registry. **Việc export MBean không đồng nghĩa ứng dụng đã mở cổng JMX từ xa.** Remote connector là một cấu hình bổ sung ở JVM hoặc hạ tầng ứng dụng.

Một remote JMX client có thể làm nhiều hơn đọc metrics:

```java
connection.getAttribute(name, "PendingCount");
connection.setAttribute(name, new Attribute("Paused", true));
connection.invoke(name, "restartWorker", new Object[0], new String[0]);
```

Quyền truy cập cần được thiết kế theo tính chất các thao tác này. Một endpoint chỉ được cho phép quan sát hệ thống không nên có quyền gọi operations làm thay đổi trạng thái.

## 3. Nguyên tắc phòng thủ nhiều lớp

Không có một cấu hình duy nhất thay thế toàn bộ bảo mật. Nên xây nhiều lớp kiểm soát:

| Lớp bảo vệ | Mục đích |
| --- | --- |
| Network exposure | Chỉ cho phép host/segment quản trị đã được duyệt |
| Authentication | Xác minh danh tính client |
| Authorization | Giới hạn ai được đọc/ghi/invoke |
| TLS | Bảo vệ thông tin và credentials trên đường truyền |
| Secrets management | Tránh lộ mật khẩu/key trong repository, log hoặc image |
| MBean surface | Không export operations, attributes nhạy cảm không cần thiết |
| Operational controls | Audit, rotation, patching, incident response |
| Validation | Kiểm thử allow/deny, kết nối, metadata và operations |

**Nguyên tắc nền tảng: deny by default.** Chỉ bật và cấp quyền khi đã xác định mục đích, chủ sở hữu, client và thời hạn sử dụng.

## 4. Checklist số 1: Kiểm kê mục tiêu và bề mặt JMX

Trước khi tạo endpoint, ghi nhận:

- [ ] Ứng dụng/JVM nào cần remote JMX? Environment: dev, staging, production.
- [ ] Ai là chủ sở hữu vận hành và ai phê duyệt cấu hình?
- [ ] Client nào cần kết nối: JConsole, JMC, agent tự động hay runbook?
- [ ] Chỉ cần **read-only monitoring** hay cần operations thay đổi trạng thái?
- [ ] Những MBean nào sẽ được công bố qua server đích?
- [ ] ObjectName/domain nào là tài nguyên của ứng dụng?
- [ ] Những attributes có chứa secrets, PII hoặc topology nội bộ không?
- [ ] Có MBean platform/third-party cung cấp operations nguy hiểm không?
- [ ] Kết nối là tạm thời phục vụ chẩn đoán hay hoạt động liên tục?
- [ ] Có cách quan sát an toàn hơn (metrics endpoint/agent chuyên dụng) phù hợp không?

JMX remote thường cho client thấy không chỉ MBean của ứng dụng mà còn các platform/third-party MBeans trên cùng server. **Đừng đánh giá rủi ro chỉ dựa trên một `@ManagedResource` tự viết.**

## 5. Checklist số 2: Giới hạn mạng và endpoint

- [ ] Không công khai JMX port ra Internet.
- [ ] Đặt connector trên private network, management VLAN, VPN hoặc tunnel an toàn.
- [ ] Firewall/security group chỉ cho phép các client quản trị đã duyệt.
- [ ] Kiểm tra inbound/outbound rules giữa client và server.
- [ ] Xác định rõ RMI registry port, RMI server port và hostname trong stub.
- [ ] Kiểm tra container/Kubernetes NAT, DNS và port mappings.
- [ ] Không phụ thuộc vào `localhost` như một ranh giới bảo mật duy nhất.
- [ ] Giới hạn truy cập qua jump host/bastion nếu cần.
- [ ] Thiết lập network logging/alert đối với kết nối bất thường.

Ví dụ một JMX service URL dạng RMI:

```text
service:jmx:rmi:///jndi/rmi://jmx.internal.example:9010/jmxrmi
```

Địa chỉ này thường chứa phần lookup qua RMI registry, nhưng sau khi lookup, client còn dùng RMI stub để kết nối server object. Vì vậy, **mở một cổng registry chưa chắc đã đủ** để kết nối hoàn chỉnh.

Một số JDK cho phép đặt registry port và RMI server port cùng giá trị qua `com.sun.management.jmxremote.port` và `com.sun.management.jmxremote.rmi.port`. Hãy xác minh trên JDK thực tế và trong môi trường mạng thật thay vì giả định mọi connector/JDK đều giống nhau.

## 6. Checklist số 3: Authentication

- [ ] Authentication luôn được bật đối với endpoint có thể truy cập qua mạng không tin cậy.
- [ ] Mỗi vai trò/client có danh tính hoặc credential riêng khi có thể.
- [ ] Không dùng một mật khẩu chia sẻ rộng cho mọi operator và agent.
- [ ] Credentials không được commit trong Git hoặc đưa trực tiếp vào Docker image.
- [ ] File password được bảo vệ bởi quyền hệ điều hành phù hợp.
- [ ] Có kế hoạch rotation, revoke và thay đổi khi nhân sự/quyền truy cập thay đổi.
- [ ] Test truy cập thiếu credentials phải thất bại.
- [ ] Test sai credentials phải thất bại, không tự fallback sang anonymous access.
- [ ] Có quy trình xử lý khi credentials bị lộ.

JDK management agent có cơ chế xác thực dựa trên password file, nhưng đây chỉ là một lựa chọn. Trong hệ thống enterprise, có thể ưu tiên kết nối qua cơ chế được tổ chức chuẩn hóa, như VPN/tunnel có kiểm soát hoặc connector/authentication provider phù hợp.

### Ví dụ file password cho lab

```text
# jmxremote.password (giá trị minh họa, không dùng thật)
observer strong-example-secret-CHANGE-ME
operator another-example-secret-CHANGE-ME
```

File này không được lưu như tài liệu triển khai có password thật. Với cấu hình password-file của JDK, quyền file phải đáp ứng yêu cầu bảo vệ của JDK/OS. Trên hệ thống Unix, ví dụ:

```bash
chmod 600 /secure/jmx/jmxremote.password
```

Ngoài permission mode, đảm bảo file có owner phù hợp và không nằm trong artifact được phân phối công khai.

## 7. Checklist số 4: Authorization và quyền tối thiểu

Authentication trả lời “ai đang kết nối”, authorization trả lời “người đó được làm gì”.

JDK management agent thường dùng access file để mô tả các vai trò quản trị. Ví dụ:

```text
# jmxremote.access
observer readonly
operator readwrite
```

- `readonly`: phù hợp với agent chủ yếu đọc dữ liệu.
- `readwrite`: cấp quyền rộng hơn, cần kiểm soát rất chặt.

**Cảnh báo:** các vai trò `readwrite` có thể có khả năng tác động lớn đến JVM/ứng dụng, không chỉ những MBean bạn chủ động tạo. Access file cơ bản không phải cơ chế authorization chi tiết theo từng business operation.

Checklist:

- [ ] Monitoring agent thường chỉ dùng `readonly`.
- [ ] Không cấp `readwrite` cho tài khoản chỉ đọc metrics.
- [ ] Người vận hành có quyền write phải có nhu cầu được phê duyệt.
- [ ] Kiểm thử `setAttribute` và `invoke` bị từ chối đối với readonly client.
- [ ] Kiểm thử operation quản trị nhạy cảm chỉ được gọi khi đúng vai trò và quy trình.
- [ ] Nếu cần quyền theo MBean/operation, dùng cơ chế authorization riêng được triển khai/đánh giá phù hợp; đừng giả định access file cơ bản đủ.
- [ ] Kiểm tra quyền theo nguyên tắc least privilege sau mỗi lần thay cấu hình.

Đừng nhầm `@ManagedOperation(description = "...")` với một annotation bảo mật. Annotation đó mô tả operation, **không quyết định ai được invoke**.

## 8. Checklist số 5: Bảo vệ transport bằng TLS

- [ ] Bật mã hóa cho kết nối quản trị từ xa ở môi trường cần bảo vệ.
- [ ] Dùng certificate được quản lý, có hạn sử dụng và quy trình rotation.
- [ ] Client xác minh danh tính server/certificate theo chính sách TLS đã chọn.
- [ ] Kiểm tra truststore/keystore và quyền truy cập private keys.
- [ ] Không tắt xác minh certificate để sửa lỗi tạm thời trong production.
- [ ] Kiểm tra JDK/client hỗ trợ TLS protocols/cipher suites được tổ chức phê duyệt.
- [ ] Test handshake với client thực dùng trong vận hành.
- [ ] Xem xét các yêu cầu bảo vệ RMI registry/lookup path theo cấu hình JDK hiện hành.

Cấu hình `com.sun.management.jmxremote.ssl=true` có thể bật TLS cho JMX management connector theo cơ chế của JDK, nhưng chi tiết RMI registry và client setup còn phụ thuộc JDK/provider. Không dùng một flag rồi mặc định toàn bộ đường đi và certificate verification đã đáp ứng mọi chính sách.

Nếu dùng VPN/tunnel, vẫn cần xác định lớp bảo vệ nào chịu trách nhiệm mã hóa và xác thực, cùng rủi ro khi tunnel bị cấu hình sai.

## 9. Ví dụ cấu hình JVM cho remote JMX

### 9.1. Lab chỉ nghe loopback

Một ví dụ phục vụ **thử nghiệm cô lập trên máy cá nhân**, không dùng nguyên xi cho production:

```bash
java \
  -Dcom.sun.management.jmxremote \
  -Dcom.sun.management.jmxremote.port=9010 \
  -Dcom.sun.management.jmxremote.rmi.port=9010 \
  -Dcom.sun.management.jmxremote.local.only=true \
  -Djava.rmi.server.hostname=127.0.0.1 \
  -Dcom.sun.management.jmxremote.authenticate=false \
  -Dcom.sun.management.jmxremote.ssl=false \
  -jar order-service.jar
```

**Không xem `local.only=true` và hostname `127.0.0.1` là bằng chứng mạng tuyệt đối bị chặn.** `java.rmi.server.hostname` chủ yếu ảnh hưởng hostname được quảng bá trong RMI stub; cách bind sockets và `local.only` cần được xác minh theo JDK. Hãy kiểm tra listening addresses bằng công cụ hệ điều hành và firewall.

### 9.2. Production-oriented cấu hình nền

Ví dụ về các thành phần cần xác định:

```bash
-Dcom.sun.management.jmxremote
-Dcom.sun.management.jmxremote.port=9010
-Dcom.sun.management.jmxremote.rmi.port=9010
-Dcom.sun.management.jmxremote.authenticate=true
-Dcom.sun.management.jmxremote.ssl=true
-Dcom.sun.management.jmxremote.password.file=/secure/jmx/jmxremote.password
-Dcom.sun.management.jmxremote.access.file=/secure/jmx/jmxremote.access
-Djava.rmi.server.hostname=jmx.internal.example
```

Đây là **khung minh họa**, không phải cấu hình production hoàn chỉnh. Cần thêm TLS key/trust material, client configuration, chính sách mạng và kiểm thử trên JDK/runtime thực tế. Các tùy chọn management agent có thể khác giữa JDK distributions/versions; luôn kiểm tra tài liệu của bản JDK triển khai.

Không đưa password giá trị thật lên command line, tránh secrets xuất hiện trong process list/log. Đường dẫn tới secret files vẫn có thể được hiển thị và phải có quyền thích hợp.

## 10. Checklist số 6: Bảo vệ secrets và cấu hình

- [ ] Password/access files nằm ngoài source repository.
- [ ] Không đưa bí mật vào environment variables nếu pipeline/log/process inspection của tổ chức khiến chúng dễ lộ; đánh giá phương thức secret injection phù hợp.
- [ ] Không in credentials trong log, exception hoặc debug output.
- [ ] Backup và permission của secret files được kiểm soát.
- [ ] Secrets có TTL/rotation policy.
- [ ] Khi rotate, xác minh connector/client dùng credentials mới đúng cách.
- [ ] Không dùng secrets thật trong README, test fixtures hoặc ví dụ.
- [ ] Không để file password/readwrite role nằm trong container layer không được mã hóa hoặc image công khai.
- [ ] Tách credentials theo dev/staging/prod.
- [ ] Có quy trình thu hồi khi laptop/agent của operator bị mất hoặc xâm nhập.

Cân nhắc sử dụng secret manager của môi trường triển khai. Mục tiêu là giới hạn khả năng xem, thay đổi hoặc trích xuất credentials.

## 11. Checklist số 7: Giới hạn bề mặt MBean

Spring có thể export bean qua:

```java
@ManagedResource(
    objectName = "com.example.orders:type=QueueAdmin,name=Payment"
)
public class QueueAdmin {

    @ManagedAttribute
    public int getPendingCount() { return 12; }

    @ManagedOperation
    public void pauseIntake() { /* ... */ }
}
```

Trước khi deploy:

- [ ] Chỉ export attributes/operations cần thiết cho mục đích vận hành.
- [ ] Đánh giá từng operation có side effect.
- [ ] Dùng management adapter riêng thay vì xuất toàn bộ business service API.
- [ ] Tránh attributes chứa passwords, tokens, full request bodies, PII hoặc dữ liệu nội bộ quá chi tiết.
- [ ] Validate tham số operation và hạn chế giá trị nguy hiểm.
- [ ] Không cung cấp `eval`, arbitrary classloading, shell execution hay operations tương đương qua JMX.
- [ ] Kiểm soát lỗi và không làm lộ stack trace/secret trong return messages.
- [ ] Có audit và quy trình phê duyệt đối với operations nhạy cảm.
- [ ] Thường xuyên xem `MBeanInfo` của platform/third-party MBeans, không chỉ MBeans tự viết.

### Adapter quản trị an toàn hơn

```java
public interface QueueService {
    int pendingCount();
    void pauseIntake();
}

@ManagedResource(
    objectName = "com.example.orders:type=QueueAdmin,name=Payment"
)
public class QueueManagementAdapter {

    private final QueueService service;

    public QueueManagementAdapter(QueueService service) {
        this.service = service;
    }

    @ManagedAttribute
    public int getPendingCount() {
        return service.pendingCount();
    }

    @ManagedOperation
    public void pauseIntake() {
        service.pauseIntake();
    }
}
```

Adapter thu hẹp contract JMX. Tuy nhiên, ngay cả khi code adapter nhỏ, quyền remote JMX còn có thể bao gồm **các MBean khác** trên cùng MBeanServer. Hạn chế export là một lớp phòng thủ, không thay thế network/auth controls.

## 12. Checklist số 8: Bảo vệ operation có side effect

Các thao tác như `restartWorker`, `retryFailed`, `clearCache`, `rebuildIndex` có thể ảnh hưởng availability hoặc dữ liệu.

- [ ] Đánh giá quyền trước khi expose.
- [ ] Giới hạn tần suất/số lượng invocation.
- [ ] Không cung cấp operation nguy hiểm cho readonly client.
- [ ] Validate input.
- [ ] Có trạng thái trước/sau thao tác để operator xác nhận.
- [ ] Thiết kế idempotent nếu có thể.
- [ ] Với operation dài, sử dụng job ID/status thay vì block quá lâu.
- [ ] Khi remote call timeout, **không retry mù** vì server có thể đã thực thi.
- [ ] Ghi audit event với principal, target instance, ObjectName, operation, timestamp và kết quả khi hệ thống hỗ trợ.
- [ ] Với tác vụ nghiêm trọng, ưu tiên kênh quản trị chuyên dụng có approval/audit đầy đủ thay vì JMX đơn giản.

Một operation `togglePaused()` thường rủi ro hơn `setPaused(true)` nếu có retry. Lệnh đặt trạng thái đích dễ idempotent hơn, nhưng vẫn cần xét side effects khác như event publication.

## 13. Checklist số 9: Xác minh client kết nối an toàn

Một client Java cơ bản có thể dùng:

```java
import java.util.HashMap;
import java.util.Map;
import javax.management.MBeanServerConnection;
import javax.management.remote.JMXConnector;
import javax.management.remote.JMXConnectorFactory;
import javax.management.remote.JMXConnector.CREDENTIALS;
import javax.management.remote.JMXServiceURL;

Map<String, Object> env = new HashMap<>();
env.put(JMXConnector.CREDENTIALS, new String[] {
    System.getenv("JMX_USER"),
    System.getenv("JMX_PASSWORD")
});

JMXServiceURL url = new JMXServiceURL(
    "service:jmx:rmi:///jndi/rmi://jmx.internal.example:9010/jmxrmi"
);

try (JMXConnector connector =
         JMXConnectorFactory.connect(url, env)) {

    MBeanServerConnection connection =
        connector.getMBeanServerConnection();

    System.out.println(connection.getDefaultDomain());
}
```

Trong project thực, lấy credentials qua secret management có kiểm soát thay vì giả định environment variables luôn là lựa chọn tốt nhất. Với TLS, client cần trust configuration đúng và không tắt xác minh server certificate. Thêm timeout/reconnect policy theo connector provider và JDK đang dùng.

**Không log `env` hoặc credentials.**

## 14. Checklist số 10: Test negative authorization

Một checklist chỉ xác minh “operator đăng nhập được” là chưa đủ. Cần test các truy cập **phải bị từ chối**.

| Test case | Kết quả mong đợi |
| --- | --- |
| Kết nối không credentials | Bị từ chối (nếu authentication yêu cầu) |
| Sai username/password | Bị từ chối |
| Readonly account đọc attribute hợp lệ | Thành công |
| Readonly account gọi write operation | Bị từ chối |
| Readonly account ghi writable attribute | Bị từ chối |
| Readwrite account thực hiện thao tác được duyệt | Thành công, có audit phù hợp |
| Untrusted source IP kết nối | Bị chặn bởi network controls |
| Certificate không tin cậy / sai policy | TLS handshake bị từ chối |
| Secret đã revoke | Không thể đăng nhập bằng secret cũ |
| Đúng credential nhưng sai environment | Quy trình kiểm tra target phải phát hiện |

Để tránh tác động nghiệp vụ, nên dùng **MBean test** có operation vô hại trong staging hoặc môi trường cô lập. Không kiểm tra readwrite bằng cách gọi operation phá hủy dữ liệu production.

Khi authorization fail, exception có thể được bọc qua connector/JMX API. Test nên xác minh hành vi từ chối và không có side effect, không dựa vào một message lỗi cụ thể.

## 15. Test TLS và danh tính server

Checklist xác minh TLS gồm:

1. Client chỉ kết nối với trust material được phê duyệt.
2. Kết nối với certificate không tin cậy phải bị từ chối.
3. Chính sách xác minh hostname/danh tính server được áp dụng theo transport/client configuration.
4. Hết hạn certificate phải tạo alert và có rotation trước hạn.
5. Private key chỉ được đọc bởi account chạy JVM/connector.
6. Client và server không dùng protocol/cipher không còn được duyệt.
7. Sau JDK update, kiểm tra handshake end-to-end thay vì chỉ kiểm tra property `ssl=true`.

Lưu ý: RMI/JMX có chi tiết TLS về registry/stub và socket factories. Một client JConsole có thể yêu cầu cấu hình đặc thù theo JDK; test với **công cụ thực tế** đang dùng.

## 16. Test mạng: không chỉ check port mở

Một lỗi vận hành phổ biến:

```text
telnet jmx.internal.example 9010
-> connected

JConsole connect
-> failed
```

Nguyên nhân có thể do RMI registry chỉ trả về stub trỏ sang hostname/port khác.

Checklist:

- [ ] DNS resolve đúng.
- [ ] Registry port reachable từ client được duyệt.
- [ ] RMI server port cũng reachable.
- [ ] RMI stub quảng bá hostname mà client truy cập được.
- [ ] Firewall chặn client không được duyệt.
- [ ] Container port publishing và hostNetwork/NAT được kiểm tra.
- [ ] Remote `getAttribute`/queryNames thành công, không chỉ connect TCP.
- [ ] Nếu dùng SSH tunnel, mapping port và advertised hostname tương thích.

Với container, `127.0.0.1` bên trong pod/container không phải `127.0.0.1` của máy client. Cần thiết kế network routing đúng và tránh lộ endpoint ra public.

## 17. Checklist số 11: Quan sát và audit

Nên giám sát:

- Số lượng và nguồn kết nối JMX.
- Authentication failures.
- Authorization denials.
- Connector startup/shutdown và lỗi RMI/TLS.
- Latency các operations có side effect.
- Trạng thái/counter của tác vụ quản trị.
- Thay đổi cấu hình bảo mật.
- Secrets/certificate rotation và thời hạn.
- Những yêu cầu truy cập bất thường theo thời gian.

Không phải JDK management agent nào cũng cung cấp audit chi tiết cho mọi `invoke` mặc định. Nếu cần record principal/operation cho compliance, phải có **cơ chế audit được triển khai và kiểm thử**, ví dụ ở management service/adapter hoặc connector authorization layer phù hợp.

Logging không nên chứa password, TLS private keys hoặc dữ liệu nhạy cảm. Cân bằng khả năng chẩn đoán với nguyên tắc tối thiểu hóa dữ liệu.

## 18. Checklist số 12: Hardening và cập nhật phiên bản

- [ ] Dùng JDK distribution còn được hỗ trợ, cập nhật security patches.
- [ ] Xác minh các flags JMX/RMI/TLS vẫn hoạt động sau JDK upgrade.
- [ ] Kiểm tra Spring `MBeanExporter` và AOP proxy sau framework upgrade.
- [ ] Kiểm tra dependency/agent bên thứ ba có MBeans nhạy cảm.
- [ ] Rà soát file access permissions sau redeploy/container rebuild.
- [ ] Rà soát security group/firewall drift.
- [ ] Kiểm tra có endpoint debug cũ mở sau sự cố không.
- [ ] Chạy test allow/deny và TLS sau nâng cấp.
- [ ] Có rollback plan và owner chịu trách nhiệm.
- [ ] Ghi runbook để tắt connector/thu hồi credentials khi có dấu hiệu bị xâm nhập.

Không xem remote JMX là dịch vụ “bật một lần rồi quên”. Nó cần lifecycle/security ownership giống các management endpoints khác.

## 19. Mẫu bảng kiểm nghiệm thu triển khai

Có thể dùng bảng này cho một change request:

| Hạng mục | Điều kiện đạt | Bằng chứng đề xuất |
| --- | --- | --- |
| Endpoint exposure | Chỉ private/VPN/tunnel, không public | Firewall rules, network scan nội bộ |
| Authentication | Anonymous và invalid credentials bị từ chối | Negative connection tests |
| Authorization | Readonly không được write/invoke | Test MBean vô hại |
| TLS | Client xác minh server, protocol hợp lệ | Handshake test/certificate review |
| Secrets | Không có secret trong repo/image/log | Repo/image scanning, file permissions |
| MBeans | Không expose dữ liệu/operation thừa | `MBeanInfo` inventory |
| RMI configuration | Registry + server ports và host đúng | Remote getAttribute từ client thật |
| Lifecycle | Connector đóng/revoke được | Startup/shutdown test |
| Operations | Side effects được giới hạn, auditable | Review và integration test |
| Monitoring | Có tín hiệu phát hiện lỗi/tấn công | Dashboard/alerts |
| Version compatibility | JDK/Spring/JMC hoạt động | Compatibility matrix test |

Khi một điều kiện không đạt, phải có risk acceptance được phê duyệt hoặc remediation trước khi mở endpoint theo chính sách tổ chức.

## 20. Kịch bản thực hành an toàn

**Bối cảnh:** một Spring application tên `order-service` cần quan sát queue từ JConsole trên một bastion nội bộ.

### Bước 1: Xác định nhu cầu

- Mục đích: đọc JVM memory, threads và queue metrics.
- Người dùng: một monitoring agent + một nhóm operator.
- Operation ghi: không cần trong giai đoạn đầu.
- Network: chỉ bastion/agent nội bộ.
- Thời hạn: theo nhu cầu vận hành đã được duyệt.

### Bước 2: Chuẩn bị MBean chỉ đọc

```java
@ManagedResource(
    objectName = "com.example.orders:type=Queue,name=Payment"
)
public class PaymentQueueMetrics {

    @ManagedAttribute
    public int getPendingCount() {
        return 12;
    }
}
```

Không thêm `@ManagedOperation` thay đổi trạng thái nếu không có yêu cầu cụ thể.

### Bước 3: Cấu hình xác thực và quyền

Dùng credential riêng cho observer, quyền `readonly`, file password/access được bảo vệ. Đặt file trong secret volume hoặc thư mục cấu hình được quản lý, không commit repo.

### Bước 4: Bật TLS và giới hạn mạng

Đặt registry/RMI ports ổn định, hostname quảng bá phù hợp, mở firewall chỉ tới bastion/agent. Cấu hình certificate và client trust phù hợp theo JDK đang dùng.

### Bước 5: Kiểm tra allow và deny

- Observer đọc `PendingCount` thành công.
- Anonymous client không kết nối được.
- Incorrect password không kết nối được.
- Observer không được thực hiện write/invoke.
- Host ngoài allowlist không kết nối được.
- Client certificate/trust không hợp lệ bị từ chối theo policy.

### Bước 6: Kiểm tra lifecycle

Khởi động lại JVM, xác minh connector và MBean trở lại đúng endpoint/ObjectName. Tắt/revoke theo runbook và đảm bảo endpoint không còn phục vụ nếu bị vô hiệu hóa.

## 21. Incident response và emergency shutdown

Nếu nghi ngờ remote JMX bị lộ:

1. Hạn chế hoặc chặn network access tới endpoint ngay theo quy trình sự cố.
2. Thu hồi/rotate credentials và certificates bị ảnh hưởng.
3. Xác định JVM, connector và MBeans đã có thể bị truy cập.
4. Kiểm tra logs/audit records sẵn có; nếu audit chưa đầy đủ, ghi rõ giới hạn điều tra.
5. Kiểm tra những operations có side effect và tình trạng dữ liệu/hệ thống.
6. Patch/configure lại endpoint và xác minh negative tests.
7. Chỉ mở lại khi các kiểm soát đã được phê duyệt.
8. Cập nhật runbook/checklist để giảm nguy cơ tái diễn.

Việc đổi password file trong khi JVM đang chạy có được áp dụng ngay hay không phụ thuộc cơ chế JDK/connector; đừng dựa vào giả định rotation có hiệu lực tức thì. Có thể cần restart connector/JVM và xác minh lại.

## 22. Những hiểu nhầm cần tránh

**“ObjectName bí mật nên không ai gọi được MBean.”** Sai. ObjectName là tên quản trị, không phải credential. Một client có quyền có thể query và liệt kê MBeans.

**“Đã bật TLS thì không cần authentication.”** Sai. TLS bảo vệ transport và có thể cung cấp xác thực theo cấu hình, nhưng quyền truy cập vẫn cần được thiết kế.

**“Firewall mở đúng một cổng là remote JMX chắc chắn chạy.”** Sai. RMI có thể sử dụng registry và server endpoint khác nhau.

**“Chỉ export một Spring bean thì remote client chỉ thấy bean đó.”** Sai. Connector tới MBeanServer có thể expose platform và third-party MBeans khác.

**“Readonly account chỉ không được invoke, còn setAttribute vẫn được.”** Sai. Quyền readonly cần chặn các hoạt động thay đổi trạng thái theo security implementation.

**“@ManagedOperation mô tả operation nên mặc định chỉ admin gọi được.”** Sai. Metadata annotation không tạo authorization.

**“Timeout chứng minh operation chưa chạy.”** Sai. Lời gọi có thể đã tạo side effect trên server trước khi phản hồi mất.

**“Chạy localhost không cần bảo mật.”** Không luôn đúng. Localhost có thể bị truy cập bởi process không tin cậy trên host, qua port forwarding hoặc cấu hình container/tunnel sai. Phải xét threat model thực tế.

## 23. Checklist gọn dùng cho change review

```text
REMOTE JMX SECURITY ACCEPTANCE

[ ] Endpoint cần thiết, có owner và mục đích rõ ràng.
[ ] No public exposure; firewall/allowlist/VPN/tunnel phù hợp.
[ ] Registry port + RMI server port/hostname đã xác minh.
[ ] Authentication bật; anonymous và sai credentials bị chặn.
[ ] Readonly role cho monitoring; write privilege tối thiểu.
[ ] TLS/certificate/trust policy đạt yêu cầu.
[ ] Password, access, key files có permissions/secrets management.
[ ] Không lộ credentials trong repo, image, log.
[ ] Kiểm kê MBeans; không công bố sensitive data/operations thừa.
[ ] Operations nguy hiểm có guardrail, input validation, audit.
[ ] Negative tests: auth, authz, TLS, network đều pass.
[ ] Remote getAttribute/invoke test dùng đúng client và môi trường.
[ ] Monitor authentication failures, connection anomalies, config drift.
[ ] Runbook rotation, revoke, incident response, shutdown có sẵn.
[ ] JDK/Spring/connector compatibility đã được thử.
[ ] Có change approval, rollback và evidence khi nghiệm thu.
```

## 24. Bài tập thực hành

1. Tạo `PaymentQueueMetrics` chỉ đọc, export bằng Spring JMX và kiểm tra MBean xuất hiện dưới ObjectName cố định.
2. Tạo hai roles trong lab: `observer readonly` và `operator readwrite`; xác minh observer không được gọi operation ghi.
3. Đặt password/access files ngoài repository và kiểm tra OS permissions.
4. Cấu hình TLS trong staging và kết nối bằng JConsole/JMC với trust material được duyệt.
5. Cố tình cấu hình sai `java.rmi.server.hostname` trong lab, ghi nhận triệu chứng client có thể lookup được registry nhưng không gọi được MBean.
6. Thử từ host bị chặn để xác minh firewall rules, không chỉ dựa vào tài liệu cấu hình.
7. Đọc `MBeanInfo` và liệt kê mọi writable attributes/operations trước khi cho phép một client có quyền `readwrite`.
8. Viết một runbook thu hồi credentials và đóng endpoint khi phát hiện cấu hình public exposure.
9. Chạy lại các test sau khi nâng JDK hoặc thay container base image.
10. Thiết kế báo cáo nghiệm thu chứa kết quả allow/deny tests, TLS, network, secrets và lifecycle.

## 25. Câu hỏi tự kiểm tra

- Vì sao bật `MBeanExporter` chưa đồng nghĩa đã mở remote JMX port?
- Sự khác nhau giữa authentication và authorization là gì?
- Vai trò readonly có phù hợp với monitoring agent không? Vì sao?
- `java.rmi.server.hostname` có bảo đảm socket chỉ bind vào địa chỉ đó không?
- Vì sao JMX over RMI có thể cần kiểm tra nhiều endpoint?
- Tại sao `@ManagedOperation` không phải một security boundary?
- TLS có thay thế quyền truy cập tối thiểu không?
- Vì sao nên thực hiện negative tests thay vì chỉ xác minh kết nối thành công?
- Điều gì xảy ra nếu remote client timeout sau operation có side effect?
- Khi một credential bị lộ, checklist incident response cần làm gì trước?

**Ghi nhớ:** Bảo mật remote JMX không chỉ là đặt password. Phải kết hợp **giới hạn mạng**, **xác thực**, **phân quyền tối thiểu**, **TLS**, **quản lý secrets**, **thu hẹp bề mặt MBeans**, **kiểm thử allow/deny** và **runbook vận hành**. Chỉ coi endpoint đã sẵn sàng khi chính các kiểm soát đó được xác minh trên JDK, client và môi trường triển khai thực tế.