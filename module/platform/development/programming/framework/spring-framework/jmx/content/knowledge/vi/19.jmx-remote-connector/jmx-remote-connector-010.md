# Không coi remote JMX là kênh không cần bảo vệ

## Mục tiêu học tập

Sau bài học này, bạn có thể:

- Giải thích vì sao **remote JMX** là một bề mặt quản trị nhạy cảm, không phải một cổng chỉ đọc hoặc kênh nội bộ mặc nhiên an toàn.
- Phân biệt JMX local, remote connector, MBeanServer, MBean, ObjectName và cơ chế phân quyền.
- Nhận biết rủi ro khi mở JMX remote endpoint ra mạng mà không kiểm soát authentication, transport security và phạm vi truy cập.
- Hiểu các lớp bảo vệ: network isolation, authentication, authorization, TLS, quản lý secret và giới hạn MBean được công bố.
- Biết cách đọc một cấu hình JMX remote ở mức nguyên tắc và tránh những lựa chọn vô hiệu hóa bảo mật trong production.
- Thiết kế checklist đánh giá trước khi vận hành remote JMX cho ứng dụng Spring Framework.
- Phân tích lỗi kết nối do RMI hostname, port, firewall mà không biến workaround thành lỗ hổng bảo mật.

## 1. Remote JMX dùng để làm gì?

Java Management Extensions (JMX) cung cấp cơ chế quản trị và quan sát JVM thông qua MBeans. Một MBean có thể công bố các thành phần:

- **Attribute:** giá trị trạng thái hoặc thông số cấu hình.
- **Operation:** hành động quản trị như làm mới cache, reset counter hoặc đổi ngưỡng.
- **Notification:** thông báo về sự kiện vận hành.

Một JMX client có thể đọc thuộc tính và gọi operation qua \`MBeanServerConnection\`. Trong cùng JVM, ứng dụng thường dùng trực tiếp \`MBeanServer\`. Khi client ở JVM hoặc host khác, cần một **remote connector** hoặc cơ chế kết nối tương đương.

Sơ đồ khái niệm:

\`\`\`text
JMX client ở host khác
        |
        | network connection
        | authentication / TLS / policy
        v
JMX remote connector
        |
        v
MBeanServer của JVM đích
        |
        +-- Memory / Threading / ClassLoading MBeans
        +-- Spring-managed MBeans
        +-- Custom operations
\`\`\`

**Điểm quan trọng:** remote connector tạo một lối truy cập từ bên ngoài vào những khả năng quản trị mà MBeanServer cung cấp. Nó không chỉ là endpoint hiển thị số liệu.

## 2. Vì sao remote JMX là bề mặt nhạy cảm?

MBeans có thể cho phép client:

1. Xem tình trạng ứng dụng, thread, bộ nhớ hoặc cấu hình runtime.
2. Đọc các attribute chứa thông tin nội bộ.
3. Thay đổi attribute có setter được công bố.
4. Gọi operation gây tác động như reload, reset, clear, stop hoặc thao tác nghiệp vụ.
5. Đăng ký listener để quan sát notification.
6. Tương tác với những MBeans của JDK, framework hoặc thư viện không chỉ do ứng dụng tự viết.

Mức độ ảnh hưởng thực tế tùy những MBeans được đăng ký và policy của môi trường. Nhưng nếu một endpoint remote bị truy cập trái phép, rủi ro có thể vượt xa việc lộ vài chỉ số.

Ví dụ một Spring-managed MBean:

\`\`\`java
@ManagedResource(
    objectName = "learning.jmx:type=Cache,name=Products"
)
public class CacheAdministration {

    @ManagedAttribute
    public int getEntryCount() {
        return cache.size();
    }

    @ManagedOperation
    public void clear() {
        cache.clear();
    }
}
\`\`\`

Nếu caller có quyền gọi \`clear()\`, đó là một thao tác làm thay đổi trạng thái ứng dụng. Không thể coi toàn bộ JMX endpoint là chỉ đọc chỉ vì nhóm triển khai chủ yếu dùng nó để quan sát.

## 3. Local JMX khác remote JMX như thế nào?

**Local JMX** thường dựa trên khả năng quan sát/attach tới một JVM trên máy cùng host hoặc trong một namespace tương thích. Quyền thường gắn với người dùng hệ điều hành, quyền process, JDK và các hạn chế môi trường.

**Remote JMX** cho phép client tương tác qua mạng, chẳng hạn thông qua JMX Remote API và RMI connector. Khi đó xuất hiện thêm các lớp rủi ro:

- Ai có thể kết nối từ mạng?
- Danh tính của client được xác minh thế nào?
- Dữ liệu và credentials có bị nghe lén không?
- Caller được phép đọc hay ghi/gọi operations?
- Connector thực sự gắn vào MBeanServer nào?
- Đường mạng có đi qua NAT, load balancer hoặc proxy không?
- Log/audit có nhận diện được thao tác nhạy cảm không?

Chỉ vì service hoạt động trên “mạng nội bộ” không có nghĩa mọi người, container hay workload trong mạng đó đều đáng tin cậy.

## 4. Nguyên tắc phòng thủ nhiều lớp

Một remote JMX endpoint nên được bảo vệ theo nhiều lớp độc lập:

| Lớp | Mục tiêu | Ví dụ |
|---|---|---|
| Network | Giảm số nguồn có thể tiếp cận | Chỉ cho phép mạng quản trị/VPN/bastion |
| Authentication | Xác minh caller | Cơ chế xác thực được runtime hỗ trợ |
| Authorization | Giới hạn hành động | Quyền đọc, ghi và gọi operations |
| Transport encryption | Bảo vệ dữ liệu trên đường truyền | TLS/SSL theo cấu hình và JDK |
| MBean surface | Giảm khả năng nhạy cảm được công bố | Chỉ export attributes/operations cần thiết |
| Secret management | Bảo vệ credential | Không hardcode/commit password |
| Logging/audit | Điều tra thao tác quản trị | Ghi danh tính, thời điểm và operation quan trọng |
| Lifecycle | Tránh endpoint tồn tại ngoài nhu cầu | Bật theo phạm vi quản trị, đóng khi không cần |

Không có một cấu hình duy nhất giải quyết mọi rủi ro. Firewall không thay thế authentication; authentication không thay thế authorization; TLS không thay thế việc hạn chế MBeans nguy hiểm.

## 5. Những cấu hình không nên dùng trong production

Một số ví dụ trên Internet thường đề xuất:

\`\`\`text
-Dcom.sun.management.jmxremote.authenticate=false
-Dcom.sun.management.jmxremote.ssl=false
\`\`\`

Đây là các lựa chọn **vô hiệu hóa hai lớp bảo vệ quan trọng**, không phải cấu hình production an toàn. Chúng có thể xuất hiện trong ví dụ local rất hạn chế, nhưng không nên sao chép sang một service có cổng JMX truy cập được từ mạng chia sẻ.

Nguyên tắc:

- Không tắt authentication chỉ để khắc phục lỗi credential.
- Không tắt TLS chỉ để làm kết nối hoạt động qua firewall hoặc tool cũ.
- Không mở cổng JMX ra toàn bộ Internet.
- Không coi việc dùng một port số “khó đoán” là bảo mật.
- Không cho mọi tài khoản dùng chung credentials quyền cao nếu có cơ chế phân quyền phù hợp.
- Không dùng username/password mặc định trong tài liệu, image hoặc repository.
- Không giả định local-only binding có hiệu lực nếu chưa kiểm chứng hostname/bind address/connector thực tế.

Các property quản trị JDK thay đổi hoặc được mở rộng theo phiên bản; phải đối chiếu tài liệu JDK đang vận hành và yêu cầu tổ chức khi triển khai.

## 6. Phân biệt authentication và authorization

Hai khái niệm khác nhau:

**Authentication:** xác nhận “ai đang kết nối?”

**Authorization:** xác nhận “caller đó được phép làm gì?”

Ví dụ người vận hành A có thể chỉ cần đọc thuộc tính giám sát, trong khi người vận hành B mới được gọi operation thay đổi cấu hình. Nếu một tài khoản đọc số liệu cũng có khả năng reset hoặc stop module, chính sách quyền đang rộng hơn nhu cầu.

JMX remote trên JDK có các cơ chế xác thực và tệp quyền truy cập dành cho remote management agent, cùng khả năng cấu hình connector/environment tùy cách triển khai. Việc dùng cấu hình nào phải dựa trên runtime và chính sách vận hành thực tế.

Khi thiết kế quyền:

1. Phân loại MBeans và operations theo mức độ nhạy cảm.
2. Cấp quyền tối thiểu cho mỗi nhóm người dùng/tooling.
3. Ưu tiên read-only đối với công cụ thu thập metrics nếu phù hợp.
4. Không cấp write/invoke chỉ vì tool cần đọc vài attributes.
5. Kiểm tra quyền ở chính đường JMX, không suy luận từ quyền của HTTP API.
6. Đối với operation có tác động mạnh, cân nhắc bảo vệ bổ sung ở tầng ứng dụng.

**Lưu ý:** HTTP security filter của Spring Security không tự động bảo vệ một JMX connector. Đây là hai đường truy cập khác nhau.

## 7. TLS và bảo vệ dữ liệu trên đường truyền

Remote JMX có thể truyền:

- Credentials hoặc dữ liệu phục vụ xác thực.
- Giá trị attributes của MBeans.
- Tham số và kết quả operations.
- Notifications và metadata quản trị.

Khi các dữ liệu này đi qua mạng, cần bảo vệ tính bí mật và toàn vẹn theo yêu cầu tổ chức, thường thông qua TLS hoặc một kênh truyền an toàn được quản lý.

TLS cần được cấu hình đúng, không chỉ “bật một cờ”:

- Server certificate được xác minh theo trust policy.
- Client tin cậy đúng CA hoặc trust store phù hợp.
- Hostname/identity của endpoint được kiểm tra theo mô hình triển khai.
- Các thuật toán/protocol yếu không được cố tình bật lại để tương thích.
- Key store và trust store được bảo vệ.
- Rotation certificate có quy trình vận hành.

Nếu chứng chỉ lỗi, giải pháp đúng là chẩn đoán trust/identity/configuration; không phải vô hiệu hóa TLS và bỏ qua bước xác minh.

## 8. Hạn chế bề mặt mạng

Không nên public remote JMX giống một web endpoint dành cho người dùng. Nên đặt nó trong mạng quản trị có phạm vi rõ.

Các lựa chọn thường gặp:

- Chỉ cho phép kết nối từ bastion hoặc monitoring host đã được quản lý.
- Dùng VPN hoặc một kênh truy cập riêng đã kiểm soát.
- Áp dụng firewall/security group/NetworkPolicy cho nguồn và đích.
- Không publish cổng JMX ra Internet.
- Không route endpoint tới mọi workload trong cluster chỉ vì chúng cùng namespace.
- Theo dõi thay đổi cổng/đích trong cấu hình triển khai và pipeline hạ tầng.
- Tránh dùng load balancer chia sẻ không có lý do, đặc biệt vì JMX thường truy cập một JVM instance cụ thể.

Trong Kubernetes, port-forward có thể hữu ích cho vận hành tạm thời nhưng không tự động thay thế authorization hoặc chính sách truy cập. Phải bảo đảm ai được quyền port-forward, thời gian sử dụng và phạm vi endpoint.

## 9. RMI và sự phức tạp của hostname, port

Một JMX remote connector dùng RMI có thể liên quan tới hơn một bước kết nối. Client có thể kết nối tới một endpoint ban đầu rồi nhận thông tin host/port trong RMI stub để thực hiện lời gọi tiếp theo.

Vì vậy “telnet tới port thành công” hoặc “firewall đã mở port ban đầu” chưa chứng minh JMX connection hoạt động end-to-end.

Các property thường gặp của JDK management agent bao gồm:

\`\`\`text
-Dcom.sun.management.jmxremote
-Dcom.sun.management.jmxremote.port=<management-port>
-Dcom.sun.management.jmxremote.rmi.port=<rmi-port>
-Djava.rmi.server.hostname=<hostname-client-truy-cap-duoc>
\`\`\`

Đây chỉ là khung tham chiếu cho việc hiểu các thành phần cấu hình, **không phải hướng dẫn bật một endpoint không bảo vệ**. Khi triển khai thật vẫn phải cấu hình xác thực, TLS và mạng đúng.

Các lỗi thường gặp:

- RMI stub quảng bá \`localhost\` nên client ở máy khác không kết nối được.
- Hostname/IP quảng bá không thể định tuyến từ phía client.
- Port bổ sung bị firewall chặn.
- NAT thay đổi địa chỉ nhưng stub vẫn trỏ tới địa chỉ trước NAT.
- Connector lắng nghe trên interface khác mong đợi.
- Client thiếu trust store hoặc credentials.

Tránh cách xử lý “mở tất cả port” hoặc “tắt security cho dễ debug”. Hãy chẩn đoán chính xác hostname, port, binding và transport.

## 10. Spring Framework và remote JMX

Spring Framework có thể export managed beans thành MBeans bằng \`MBeanExporter\` hoặc annotation-driven JMX.

Ví dụ:

\`\`\`java
import org.springframework.jmx.export.annotation.ManagedResource;
import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedOperation;

@ManagedResource(
    objectName = "learning.jmx:type=Queue,name=Primary"
)
public class QueueManagement {

    private volatile boolean paused;

    @ManagedAttribute
    public boolean isPaused() {
        return paused;
    }

    @ManagedOperation
    public void pause() {
        paused = true;
    }
}
\`\`\`

Để export annotation-based bean:

\`\`\`java
@Configuration
@EnableMBeanExport
public class JmxConfiguration {

    @Bean
    QueueManagement queueManagement() {
        return new QueueManagement();
    }
}
\`\`\`

Hai quyết định phải tách biệt:

1. **Export MBean vào MBeanServer nào?** Đây là việc của Spring JMX exporter.
2. **MBeanServer đó có được truy cập từ xa hay không và bảo vệ thế nào?** Đây là việc của connector/JDK/runtime/hạ tầng quản trị.

Bật \`@EnableMBeanExport\` không đồng nghĩa tự mở một cổng remote JMX an toàn. Ngược lại, bật remote connector cho platform server có thể làm những MBeans đã đăng ký trong server đó truy cập được theo quyền của connector.

Do đó, khi một team thêm \`@ManagedOperation\`, cần đánh giá nó có thể xuất hiện trước remote JMX client nào, không chỉ trước JConsole local.

## 11. MBeanServer được connector phục vụ

Một JVM có thể có nhiều MBeanServers. JMXConnectorServer được gắn với một MBeanServer cụ thể khi tạo.

Ví dụ khái niệm:

\`\`\`java
JMXConnectorServer connector =
    JMXConnectorServerFactory.newJMXConnectorServer(
        serviceUrl,
        connectorEnvironment,
        mbeanServer
    );
\`\`\`

Client kết nối qua connector đó sẽ tương tác với MBeanServer tương ứng.

Vì vậy:

- Đăng ký MBean vào server A nhưng connector phục vụ server B sẽ không làm MBean xuất hiện từ xa.
- Một connector đã được bảo vệ không tự bảo vệ mọi connector khác trong JVM.
- Spring \`MBeanExporter.setServer(...)\` lựa chọn registry; nó không tự cung cấp network policy hoặc TLS.
- Nếu dùng nhiều remote connectors, phải kiểm tra từng đường truy cập và quyền.

Việc “không thấy MBean” có thể là vấn đề server identity, không phải vấn đề network. Việc “kết nối được” cũng không chứng minh rằng quyền đã được cấu hình an toàn.

## 12. Không công bố operation nguy hiểm tùy tiện

Một MBean có thể công bố:

\`\`\`java
@ManagedOperation
public void clearAllCaches() {
    // ...
}
\`\`\`

hoặc:

\`\`\`java
@ManagedOperation
public void reloadConfiguration() {
    // ...
}
\`\`\`

Đó là bề mặt có tác dụng phụ. Một công cụ giám sát chỉ cần đọc số liệu thường không cần các quyền này.

Nguyên tắc thiết kế:

- Chỉ công bố operation quản trị có lý do chính đáng.
- Đặt tên và mô tả thao tác rõ ràng.
- Kiểm soát tham số, không thực thi đầu vào tùy ý.
- Hạn chế operation có thể dừng dịch vụ hoặc xóa dữ liệu.
- Kiểm tra quyền thực tế qua JMX, không dựa vào annotation bảo mật của HTTP stack.
- Ghi nhận hành động quản trị nhạy cảm khi cần.
- Nếu operation có thể gây downtime, nên có quy trình change/approval phù hợp.

Một phương án là tách **read-only monitoring MBean** khỏi **administrative MBean** để tổ chức quyền dễ hơn.

## 13. Không để lộ thông tin nhạy cảm qua attributes

Không phải chỉ operations mới nguy hiểm. Một attribute đọc được có thể làm rò rỉ:

- Connection string chứa credentials.
- Access token hoặc API key.
- Tên tài khoản và định danh nội bộ.
- Dữ liệu cá nhân.
- Thông tin hạ tầng có thể hỗ trợ một cuộc tấn công tiếp theo.

Ví dụ không nên làm:

\`\`\`java
@ManagedAttribute
public String getDatabasePassword() {
    return password;
}
\`\`\`

Thay vào đó, export những thông tin vận hành cần thiết:

\`\`\`java
@ManagedAttribute
public boolean isDatabaseHealthy() {
    return healthChecker.isHealthy();
}
\`\`\`

Với configuration metadata, nên tránh đặt secret trong ObjectName, description, notification message hoặc userData. Những trường này cũng có thể được log hoặc đưa vào công cụ quản trị.

## 14. Authentication và TLS không thay thế quyền hệ điều hành

Remote JMX connector chỉ là một đường truy cập. JVM còn có thể được quan sát qua local attach, debug tooling, process inspection hoặc các API khác tùy quyền của hệ điều hành và runtime.

Bảo vệ remote connector không có nghĩa người dùng có quyền mạnh trên host/container đã bị giới hạn tương đương. Chính sách cần xét:

- Quyền truy cập máy chủ.
- Tài khoản chạy Java process.
- Khả năng attach/debug.
- Secrets trong environment, filesystem hoặc configuration.
- Quyền thao tác container và port-forward.
- Remote JMX authentication/authorization.
- Network segmentation và TLS.

Bảo mật tốt là sự kết hợp của những lớp này.

## 15. Ví dụ phân tách nhu cầu monitor và admin

Giả sử hệ thống cần:

- Monitoring agent đọc queue depth mỗi phút.
- Operator có quyền pause/resume queue khi ứng cứu.

Không nên cấp một tài khoản quản trị toàn quyền cho monitoring agent nếu nó chỉ cần đọc một attribute.

Có thể thiết kế:

\`\`\`java
@ManagedResource(
    objectName = "learning.jmx:type=QueueMetrics,name=Primary"
)
public class QueueMetricsView {

    @ManagedAttribute
    public int getQueueDepth() {
        return service.depth();
    }
}
\`\`\`

Và một management facade khác:

\`\`\`java
@ManagedResource(
    objectName = "learning.jmx:type=QueueAdmin,name=Primary"
)
public class QueueAdministration {

    @ManagedOperation
    public void pause() {
        service.pause();
    }
}
\`\`\`

Tuy nhiên việc chia làm hai MBeans **không tự tạo ra authorization riêng**. Connector và policy phải thực sự phân biệt quyền, hoặc các nhóm MBeans phải được đặt sau những kênh quản trị có mức bảo vệ phù hợp.

Thiết kế contract rõ giúp bạn nhận diện quyền cần cấp, nhưng policy kỹ thuật mới là lớp thực thi.

## 16. Checklist trước khi bật remote JMX

Trước khi triển khai, cần trả lời:

1. **Mục đích:** Vì sao cần remote JMX thay vì metrics/HTTP endpoint với phạm vi nhỏ hơn?
2. **Đối tượng:** MBeans nào được công bố? Có operation gây tác dụng phụ không?
3. **Network:** Những host/workloads nào có thể tiếp cận connector?
4. **Authentication:** Caller được xác minh theo cơ chế nào?
5. **Authorization:** Có phân biệt quyền đọc và quyền thay đổi không?
6. **Encryption:** Dữ liệu và credentials có được bảo vệ trên đường truyền không?
7. **Secrets:** Credentials/certificates được lưu và rotate thế nào?
8. **Identity:** Client kết nối đúng JVM instance, MBeanServer và endpoint chưa?
9. **RMI:** Hostname và các port cần thiết có được cấu hình đúng, không phải mở toàn mạng?
10. **Logging:** Có audit thao tác nhạy cảm và giám sát truy cập bất thường không?
11. **Lifecycle:** Connector có thể được đóng hoặc giới hạn thời gian sử dụng khi không cần?
12. **Testing:** Đã xác minh client được phép truy cập và client không có quyền bị từ chối?
13. **Incident response:** Có quy trình thu hồi credential hoặc cô lập endpoint khi nghi ngờ lộ?
14. **Documentation:** Có runbook cho cả kết nối, lỗi thường gặp và trách nhiệm vận hành?

Nếu chưa trả lời được các câu hỏi trên, không nên mở remote JMX rộng hơn chỉ vì muốn debug nhanh.

## 17. Kiểm thử bảo mật và vận hành

Một bộ kiểm thử hợp lý không chỉ xác minh “kết nối được”.

### Kiểm thử kết nối hợp lệ

Dùng JMX client được cấp quyền kết nối tới endpoint chính thức, đọc một MBean attribute không nhạy cảm và xác nhận đúng JVM/instance.

### Kiểm thử từ nguồn không được phép

Từ một môi trường không được phép truy cập, xác nhận network policy ngăn kết nối. Không cần quét chủ động toàn bộ mạng để chứng minh điều này; dùng test có phạm vi được phê duyệt.

### Kiểm thử sai credentials

Xác nhận kết nối bị từ chối và không lộ bí mật trong log.

### Kiểm thử phân quyền

Một tài khoản chỉ đọc phải không được gọi operation quản trị nếu policy thiết kế như vậy. Nên chọn operation an toàn hoặc môi trường test; không thử thao tác gây downtime trên production.

### Kiểm thử TLS identity

Client phải tin cậy đúng server certificate và từ chối endpoint không đáp ứng policy xác thực server.

### Kiểm thử cleanup

Khi connector được đóng hoặc cấu hình bị thu hồi, xác nhận đường truy cập không còn hoạt động.

## 18. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Remote client kết nối bị từ chối | Sai credentials, TLS hoặc policy | Kiểm tra log và cấu hình; không tắt bảo mật |
| Kết nối ban đầu thành công nhưng thao tác timeout | RMI stub chứa host/port không thể truy cập | Kiểm tra hostname, NAT và firewall |
| Monitoring agent có quyền gọi operation nguy hiểm | Phân quyền quá rộng | Thu hẹp quyền theo least privilege |
| Endpoint truy cập được từ ngoài mạng quản trị | Firewall/security group rộng | Giới hạn nguồn và đích |
| JMX client thấy MBeans không mong muốn | Connector phục vụ MBeanServer có surface lớn | Review registry và quyền; cân nhắc phân vùng |
| MBean không thấy từ xa | Export vào MBeanServer khác | Kiểm tra exporter.server và connector target |
| TLS handshake lỗi | Trust store, certificate, identity không phù hợp | Sửa cấu hình TLS; không bỏ qua validation |
| Sau deploy cổng JMX bị public | Thay đổi hạ tầng/container port mapping | Kiểm tra network policy và release checklist |
| HTTP security vẫn đúng nhưng JMX operation không được chặn | JMX không đi qua HTTP filter chain | Bảo vệ connector và management method |
| Secret xuất hiện trong log JMX | MBean attribute/message chứa dữ liệu nhạy cảm | Loại dữ liệu khỏi management contract và rotate secret liên quan |

## 19. Tình huống thực tế

### Tình huống A: Debug production nhanh

Một developer đề xuất bật remote JMX không xác thực và không TLS trong vài giờ để xem thread count.

Vấn đề: endpoint có thể mở nhiều khả năng quản trị hơn mục tiêu ban đầu. Khoảng thời gian ngắn không biến cấu hình nguy hiểm thành an toàn.

Hướng xử lý: ưu tiên đường quản trị đã được phê duyệt, giới hạn mạng, sử dụng xác thực/mã hóa, xác định người được truy cập và đóng lại theo quy trình.

### Tình huống B: Monitoring chạy trong Kubernetes

Một metrics collector cần đọc các attributes trong một JVM. Nếu dùng remote JMX, cần cấp cho collector quyền tối thiểu và giới hạn đường mạng chỉ giữa collector và workload liên quan. Không mở port cho tất cả pods hoặc public ingress.

Có thể cân nhắc JMX-to-metrics exporter nếu hệ thống chủ yếu cần số liệu. Dù chuyển thành metrics, vẫn cần đánh giá dữ liệu được công bố và quyền truy cập endpoint metrics.

### Tình huống C: MBean có thao tác shutdown

Một custom MBean có \`stopService()\`. Khi mở remote connector, operation có thể trở nên truy cập được theo quyền connector. Trước khi bật remote, cần xem operation này có thực sự cần được công bố không và ai được phép gọi.

### Tình huống D: Remote connection qua NAT

Client kết nối được tới cổng đầu tiên nhưng timeout. Một người đề xuất tắt TLS và authentication. Đây không giải quyết đúng nguyên nhân nếu RMI stub quảng bá địa chỉ không thể truy cập. Cần kiểm tra host/port và cấu hình mạng.

### Tình huống E: JConsole không thấy MBean

Spring MBeanExporter có thể đã đăng ký vào MBeanServer tùy biến; connector lại phục vụ platform MBeanServer. Cần kiểm tra server identity, không mở thêm cổng không bảo vệ để tìm MBean.

## 20. Bài tập tự đánh giá

### Bài 1 — Phân loại các lớp bảo vệ

Cho các biện pháp: firewall, TLS, password authentication, read-only policy, audit log. Hãy xác định mỗi biện pháp giải quyết rủi ro nào và vì sao không thể thay thế hoàn toàn nhau.

### Bài 2 — Đọc cấu hình có rủi ro

Một file triển khai chứa:

\`\`\`text
com.sun.management.jmxremote.authenticate=false
com.sun.management.jmxremote.ssl=false
\`\`\`

Hãy chỉ ra hai lớp bảo vệ bị vô hiệu hóa và nêu các bước cần đánh giá trước khi cho phép remote connector phục vụ môi trường có network access.

### Bài 3 — Bảo vệ thao tác clear cache

MBean chứa \`getEntryCount()\` và \`clear()\`. Một monitoring agent chỉ cần đọc EntryCount. Hãy thiết kế quyền và bề mặt JMX tối thiểu cho agent.

### Bài 4 — Debug RMI

Remote JMX client kết nối ban đầu nhưng lỗi ở bước tiếp theo. Hãy liệt kê những thứ cần kiểm tra trước khi đề xuất thay đổi bảo mật: RMI hostname, các port, firewall, NAT, endpoint identity và TLS trust.

### Bài 5 — Spring và JMX security

Giải thích vì sao \`@EnableMBeanExport\` không tương đương bật remote JMX, và vì sao Spring HTTP Security không tự động bảo vệ operation được gọi qua JMX.

## 21. Ghi nhớ cốt lõi

- **Remote JMX là một giao diện quản trị, không phải kênh đọc số liệu mặc nhiên vô hại.**
- JMX có thể công bố operation và dữ liệu nhạy cảm; phạm vi ảnh hưởng tùy MBeans và quyền thực tế.
- Bảo vệ bằng nhiều lớp: network isolation, authentication, authorization, TLS, secret management và thu hẹp management surface.
- Không sao chép cấu hình tắt authentication/TLS vào production.
- Spring JMX export và remote connector là hai cơ chế riêng; bật annotation export không tự bảo vệ hoặc mở cổng mạng.
- JMX connector phải phục vụ đúng MBeanServer, và remote client phải có quyền tương ứng.
- RMI hostname/port là vấn đề mạng; không giải bằng cách vô hiệu hóa security.
- Đánh giá, kiểm thử và audit các quyền quản trị trước khi triển khai, nhất là những operation có tác dụng phụ.

## Tài liệu tham khảo

- Oracle Java Management Extensions (JMX): https://docs.oracle.com/javase/8/docs/technotes/guides/jmx/
- Oracle Java SE — Monitoring and Management Using JMX: https://docs.oracle.com/en/java/javase/21/management/monitoring-and-management-using-jmx-technology.html
- Java SE — JMXConnectorServer: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/remote/JMXConnectorServer.html
- Java SE — MBeanServerConnection: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanServerConnection.html
- Spring Framework Reference — JMX: https://docs.spring.io/spring-framework/reference/integration/jmx.html
