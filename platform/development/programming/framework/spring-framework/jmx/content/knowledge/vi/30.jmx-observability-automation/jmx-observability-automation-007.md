# Giới hạn quyền của tài khoản tự động hóa khi sử dụng Spring Framework JMX

## Mục tiêu bài học

Sau bài học này, bạn có thể:

- Giải thích vì sao tài khoản tự động hóa truy cập JMX phải tuân thủ nguyên tắc **least privilege**.
- Phân biệt các quyền **kết nối**, **đọc attributes**, **đăng ký notification listener**, **ghi attributes** và **gọi operations**.
- Hiểu cách JMX remote connector, cơ chế authentication/authorization của JDK và hạ tầng quản trị ảnh hưởng đến quyền của monitoring bot hoặc automation service account.
- Biết giới hạn bề mặt quản trị bằng cách tách **read-only MBean**, **management operation** và **transport/connector**.
- Tránh nhầm HTTP Spring Security với bảo vệ remote JMX; không cho rằng một tài khoản có quyền vào mạng là được phép làm mọi thao tác.
- Lập kế hoạch credential rotation, audit, network isolation và test quyền theo cả positive lẫn negative cases.
- Xác định các hạn chế của access-file đơn giản và thời điểm cần authorization model chi tiết hơn.

## 1. Tại sao tài khoản tự động hóa cần quyền tối thiểu?

Tài khoản tự động hóa có thể được sử dụng bởi:

- Monitoring collector định kỳ đọc \`ThreadCount\`, \`HeapMemoryUsage\` hoặc các custom attributes.
- Một tác vụ SRE định kỳ kiểm tra queue depth.
- Hệ thống cảnh báo đọc JMX notification.
- Bot vận hành thực hiện thao tác đã được phê duyệt, chẳng hạn refresh cấu hình.
- Một job CI hoặc maintenance tool cần thao tác có giới hạn thời gian.

Những tài khoản này thường chạy **không có người ngồi trực tiếp** và có thể lưu credentials trong secret store, environment hoặc hệ thống điều phối.

Nếu cùng một tài khoản dùng để đọc metrics cũng có quyền gọi \`shutdown\`, \`resetAllCounters\`, \`clearCache\` hoặc ghi cấu hình, việc lộ credential có thể gây tác động vượt xa yêu cầu quan sát ban đầu.

Ví dụ:

\`\`\`text
Monitoring bot
    |
    | Need: read QueueDepth
    v
JMX remote connector
    |
    +-- QueueDepth [read]
    +-- pauseProcessing() [write-like operation]
    +-- clearAllData() [dangerous operation]
\`\`\`

Nếu bot chỉ cần đọc \`QueueDepth\`, không nên mặc định cấp quyền tương đương quản trị toàn bộ MBeanServer.

**Nguyên tắc chính:** Mỗi identity tự động hóa chỉ được cấp đúng những quyền cần để hoàn thành tác vụ được định nghĩa, trên đúng resource, trong đúng môi trường và thời gian cần thiết.

## 2. JMX khác một metrics endpoint chỉ đọc

JMX có thể công bố:

1. **Read-only attributes**: ví dụ số kết nối đang hoạt động.
2. **Writable attributes**: ví dụ tăng/giảm worker limit.
3. **Operations**: ví dụ reset state, restart component, flush cache.
4. **Notifications**: client có thể đăng ký nhận sự kiện.
5. **Metadata**: tên MBeans, attributes, operations và descriptions.

Một JMX client được quyền truy cập quá rộng có thể nhìn thấy hoặc sử dụng những tính năng vượt quá nhu cầu thu thập metrics.

Ví dụ Spring:

\`\`\`java
@ManagedResource(
    objectName = "learning.jmx:type=Queue,name=Primary"
)
public class QueueManagement {

    @ManagedAttribute
    public long getPendingJobs() {
        return queue.pendingJobs();
    }

    @ManagedOperation
    public void pauseProcessing() {
        queue.pause();
    }
}
\`\`\`

Một monitoring job có thể chỉ cần gọi:

\`\`\`java
connection.getAttribute(name, "PendingJobs");
\`\`\`

Nhưng cùng MBean còn có operation \`pauseProcessing()\` gây side effect. Việc operation có được gọi hay không phụ thuộc quyền thực tế của connector và các lớp kiểm soát bổ sung.

Không nên dựa vào quy ước nội bộ “bot này chỉ gọi getter” như một cơ chế bảo mật.

## 3. Ba lớp quyền cần phân biệt

### 3.1. Network reachability

Có thể gửi request tới host/port JMX hay không? Firewall, VPN, bastion, security group, Kubernetes NetworkPolicy hoặc private networking thường xử lý lớp này.

### 3.2. Authentication

Connector xác minh người kết nối là ai? Tùy runtime, có thể sử dụng cấu hình xác thực của JMX management agent hoặc cơ chế authentication do ứng dụng/connector tích hợp.

### 3.3. Authorization

Identity đã được xác thực được phép thực hiện những thao tác nào? Cần phân biệt các tác vụ đọc, ghi và gọi operation.

\`\`\`text
Network policy:  Có tới được endpoint?
       |
       v
Authentication: Ai đang gọi?
       |
       v
Authorization:  Được phép làm gì?
       |
       v
MBeanServer:    Thao tác trên MBean cụ thể
\`\`\`

Network isolation không thay thế authentication. Authentication không tự đồng nghĩa chỉ đọc. TLS bảo vệ đường truyền nhưng không tự giới hạn operation nào được gọi.

## 4. Phân loại tài khoản theo vai trò

Ví dụ thiết kế quyền:

| Identity | Mục đích | Quyền mong muốn |
|---|---|---|
| \`jmx-metrics-reader\` | Poll counters, gauges | Read-only; chỉ các resources cần thiết nếu cơ chế cho phép |
| \`jmx-health-reader\` | Health/diagnostics | Read-only, có thể cần metadata |
| \`jmx-notification-reader\` | Subscribe notification | Chỉ truy cập broadcaster và listener registration cần thiết |
| \`jmx-maintenance-operator\` | Một số operation bảo trì | Quyền ghi/gọi có giới hạn, kiểm soát và audit |
| \`jmx-platform-admin\` | Quản trị kỹ thuật khẩn cấp | Quyền rộng hơn, chỉ cấp cho workflow được quản lý |

Đây là **mô hình vai trò đề xuất**, không phải tên roles được Java JMX mặc định hiểu. Muốn thực thi phân quyền theo từng MBean/operation, cần chọn authorization mechanism hỗ trợ mức chi tiết đó.

Một service account không nên dùng chung cho monitoring và các hành động bảo trì có rủi ro cao chỉ vì cả hai sử dụng JMX.

## 5. JDK remote JMX access file: read-only và readwrite

JDK management agent có thể hỗ trợ cấu hình thông tin xác thực và access control qua các tệp được JVM đọc theo runtime configuration.

Một access file minh họa:

\`\`\`text
monitorRole readonly
operatorRole readwrite
\`\`\`

Ý nghĩa khái quát:

- \`readonly\`: tài khoản bị giới hạn theo chính sách read-only do management agent thực thi.
- \`readwrite\`: tài khoản có thể thực hiện các thao tác ghi/gọi trong giới hạn cơ chế hỗ trợ.

**Cảnh báo rất quan trọng:** Quyền \`readwrite\` trong cấu hình cơ bản không tương đương “chỉ được gọi một operation cụ thể”. Đừng gán quyền readwrite cho monitoring account vì một operation tiện lợi nào đó cần chạy.

Cách cấu hình và các tùy chọn chi tiết khác nhau theo JDK version và deployment model. Luôn đối chiếu tài liệu JDK được sử dụng; không xem ví dụ trên là một cấu hình production hoàn chỉnh.

### Nếu chỉ có readonly/readwrite thì phải làm gì?

Có một số lựa chọn:

- Giữ monitoring dùng \`readonly\`.
- Tách automation thay đổi state sang một workflow khác có identity và endpoint được quản lý.
- Không công bố operation nguy hiểm trên MBeanServer mà readwrite account có thể truy cập.
- Dùng connector hoặc authorization layer có khả năng enforce quyền chi tiết hơn nếu có yêu cầu thực tế.
- Xây một API bảo trì chuyên dụng với authorization/audit phù hợp nếu JMX access file quá thô.

Điều quan trọng là phải đánh giá **granularity mà runtime thực sự cung cấp**, không giả định có per-operation RBAC khi chỉ cấu hình access file đơn giản.

## 6. Không nhầm quyền đọc với quyền gọi operation

Ngay cả khi operator nhìn thấy MBean trong JConsole, không nên suy ra nó có quyền thay đổi state. Ngược lại, nếu tài khoản có quyền write/invoke rộng, việc script hiện tại chỉ gọi getter không phải giới hạn kỹ thuật.

Ví dụ:

\`\`\`java
MBeanServerConnection connection =
        connector.getMBeanServerConnection();

Object count = connection.getAttribute(
    new ObjectName("learning.jmx:type=Queue,name=Primary"),
    "PendingJobs"
);
\`\`\`

Một tác vụ automation khác có thể thử:

\`\`\`java
connection.invoke(
    new ObjectName("learning.jmx:type=Queue,name=Primary"),
    "pauseProcessing",
    new Object[0],
    new String[0]
);
\`\`\`

Hai lời gọi dùng cùng JMX connection nhưng có intent khác. Chính sách cần bảo đảm read-only account bị từ chối khi gọi tác vụ thay đổi trạng thái, không chỉ yêu cầu developers “không gọi”.

### Read-only vẫn có thể lộ dữ liệu

Chỉ đọc không đồng nghĩa không có rủi ro. Attribute có thể chứa:

- Secret hoặc API key nếu thiết kế sai.
- Hostnames, database connection strings.
- Thông tin topology nội bộ.
- Personal data.
- Configurations có thể hỗ trợ tấn công.

Vì vậy least privilege còn bao gồm **giới hạn dữ liệu được công bố** và **phạm vi kết nối**, không chỉ loại thao tác.

## 7. Thiết kế MBeans theo mức nhạy cảm

Một hướng kiến trúc là tách MBeans chỉ đọc khỏi MBeans quản trị.

\`\`\`text
MBeanServer / connector for monitoring
    |
    +-- QueueMetricsView
    +-- CacheMetricsView
    +-- PoolStatusView

Management context / connector with stronger controls
    |
    +-- QueueAdministration
    +-- CacheAdministration
\`\`\`

Ví dụ read-only facade:

\`\`\`java
package example.jmx;

import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedResource;

@ManagedResource(
    objectName = "learning.jmx:type=QueueMetrics,name=Primary"
)
public class QueueMetricsView {

    private final QueueService service;

    public QueueMetricsView(QueueService service) {
        this.service = service;
    }

    @ManagedAttribute(
        description = "Current number of waiting jobs"
    )
    public long getPendingJobs() {
        return service.pendingJobs();
    }
}
\`\`\`

Administrative facade:

\`\`\`java
package example.jmx;

import org.springframework.jmx.export.annotation.ManagedOperation;
import org.springframework.jmx.export.annotation.ManagedResource;

@ManagedResource(
    objectName = "learning.jmx:type=QueueAdmin,name=Primary"
)
public class QueueAdministration {

    private final QueueService service;

    public QueueAdministration(QueueService service) {
        this.service = service;
    }

    @ManagedOperation(description = "Pause accepting new jobs")
    public void pauseProcessing() {
        service.pause();
    }
}
\`\`\`

Hai classes riêng giúp làm rõ management contract và review security dễ hơn.

**Tuy nhiên:** Nếu chúng được export vào cùng MBeanServer và mọi readwrite account đều có quyền với toàn bộ server, việc tách thành hai ObjectNames **không tự động tạo được per-MBean authorization**. Cần có enforcement thực sự ở connector/policy, hoặc phân vùng vào những registry/connector riêng có kiểm soát.

## 8. Đừng giả định Spring Security HTTP bảo vệ JMX

Một ứng dụng Spring Boot có thể cấu hình HTTP security cho Actuator endpoints và các REST APIs.

Ví dụ các HTTP request có thể đi qua SecurityFilterChain, nhưng JMX remote connector thường không đi qua servlet filter chain đó.

\`\`\`text
HTTP client
    |
    v
Spring Security HTTP filters
    |
    v
HTTP endpoint

JMX client
    |
    v
JMX connector / MBeanServer
    |
    v
MBean operation
\`\`\`

Vì vậy:

- Bảo vệ \`/actuator\` không đồng nghĩa remote JMX đã được bảo vệ.
- Một \`@PreAuthorize\` trên service method chỉ có tác dụng theo đúng Spring method-security proxy/advice call path.
- Nếu JMX operation gọi target trực tiếp, có thể bỏ qua advice trong một số thiết kế.
- Connector-level authentication/authorization và network policy vẫn cần thiết.

Nếu có operation nhạy cảm, hãy kiểm thử thực tế qua JMX với tài khoản được phép và không được phép.

## 9. Quản lý credentials của automation account

Không lưu credential JMX trực tiếp trong source code:

\`\`\`java
// Không nên hardcode.
String username = "monitorRole";
String password = "hardcoded-password";
\`\`\`

Thay vào đó:

1. Dùng secret manager hoặc cơ chế quản lý secrets được tổ chức phê duyệt.
2. Chỉ cấp quyền đọc secret cho workload cần dùng.
3. Tránh in password, token hoặc private key vào logs.
4. Có vòng đời rotate credential.
5. Không dùng cùng secret giữa development, staging và production.
6. Thu hồi identity/credential khi automation job không còn cần.
7. Kiểm soát quyền truy cập file cấu hình authentication và keystore trên host.

Với JMX remote username/password ở client Java, credentials thường được cung cấp qua connector environment. Cách nạp từ secret source phụ thuộc hạ tầng.

\`\`\`java
Map<String, Object> environment = new HashMap<>();
environment.put(
    JMXConnector.CREDENTIALS,
    new String[] { username, password }
);
\`\`\`

Đây là minh họa API client, không phải cơ chế bảo mật hoàn chỉnh. Trong production cần TLS, connector trust, secret lifecycle và identity management phù hợp.

## 10. Không vô hiệu hóa authentication hoặc TLS

Những lựa chọn:

\`\`\`text
com.sun.management.jmxremote.authenticate=false
com.sun.management.jmxremote.ssl=false
\`\`\`

vô hiệu hóa những lớp bảo vệ quan trọng. Chúng không nên được sao chép vào production chỉ để làm bot kết nối dễ hơn.

Nếu một automation account không kết nối được:

- Xác minh credentials và policy.
- Xác minh certificate/trust configuration.
- Kiểm tra hostname/RMI port/network.
- Đọc exception và server logs.
- Kiểm tra tài khoản có được cấp đúng quyền chưa.

Không giải quyết lỗi bằng cách cấp readwrite cho mọi account hoặc tắt authentication/TLS.

## 11. Quyền mạng là một phần least privilege

Bot chỉ cần poll một JVM trong môi trường production không nhất thiết phải truy cập mọi JMX endpoint trong tổ chức.

Có thể giới hạn:

- Source IP hoặc workload identity.
- Destination host/namespace.
- Port của connector.
- Thời gian kết nối qua bastion/VPN khi có yêu cầu.
- NetworkPolicy hoặc firewall rules cho đúng tuyến.
- Không expose remote JMX public Internet.
- Không cho CI runner không được quản lý tự do truy cập production management network.

Khi dùng Kubernetes, quyền \`kubectl port-forward\` hoặc quyền tạo debug pod có thể mở đường tới management endpoint. Hãy đưa những khả năng này vào threat model và audit theo quyền thực tế.

## 12. Đặc điểm của JMX remote connector

JMX remote thường dùng connector, có thể dựa trên RMI. Automation account muốn đọc dữ liệu phải:

1. Kết nối được tới endpoint.
2. Xác minh đúng server identity nếu dùng TLS.
3. Hoàn thành authentication.
4. Được authorization cho thao tác muốn thực hiện.
5. Truy vấn đúng MBeanServer/ObjectName.

Một client dùng nhầm endpoint hoặc JVM có thể nhìn thấy MBeans khác mong đợi.

Một JMX remote connector có thể công bố nhiều MBeans ngoài custom Spring MBeans, bao gồm platform MBeans của JVM và các MBeans do thư viện khác đăng ký. Vì vậy phải đánh giá **toàn bộ registry có thể truy cập**, không chỉ vài bean do team viết.

## 13. Quyền subscription notification

Một automation job có thể đăng ký \`NotificationListener\` để nhận sự kiện:

\`\`\`java
connection.addNotificationListener(
    objectName,
    listener,
    filter,
    handback
);
\`\`\`

Đây là một dạng thao tác quản trị cần được policy cho phép theo connector. Tùy cơ chế authorization, nó có thể có quy tắc khác với \`getAttribute\`.

Những điều cần cân nhắc:

- Bot có cần subscribe notification thật không, hay polling là đủ?
- MBean nào được phép phát thông tin tới bot?
- Notification message/userData có chứa dữ liệu nhạy cảm không?
- Listener cần reconnect/re-register ra sao?
- Credentials có bị reuse cho những thao tác write không?
- Có giới hạn listener count hoặc tải do registration không?

Không giả định \`readonly\` đồng nghĩa được phép thực hiện mọi subscription operation trong mọi JMX runtime. Hãy thử quyền thực tế theo phiên bản JDK và connector.

## 14. Audit hoạt động của tài khoản tự động hóa

Với operations nhạy cảm, cần xác định:

- Ai/cái gì đã kết nối?
- Danh tính được xác thực là gì?
- Operation nào được gọi?
- ObjectName và parameters có gì?
- Lời gọi thành công hay thất bại?
- Khi nào xảy ra?
- Hành động có được phê duyệt không?

Tùy JMX connector và runtime, không phải mọi lời gọi đều tự tạo audit log chi tiết. Có thể cần instrumentation trong management facade, connector layer hoặc workflow thực thi.

Ví dụ:

\`\`\`java
@ManagedOperation
public void requestMaintenance() {
    audit.record("maintenance requested");
    maintenanceService.request();
}
\`\`\`

Nhưng không nên coi log string tĩnh như trên là đủ để biết caller identity. Nếu cần audit chính xác người gọi, phải truyền identity qua cơ chế được tin cậy và có enforcement ở tầng quản trị.

Không ghi secret hoặc dữ liệu nhạy cảm nguyên văn vào log/audit.

## 15. Phân quyền theo môi trường

Development, staging và production có mức rủi ro khác nhau.

Ví dụ:

| Environment | Monitoring bot | Maintenance bot |
|---|---|---|
| Development | Read-only hoặc quyền thử nghiệm có giới hạn | Có thể dùng test identities tách biệt |
| Staging | Read-only với endpoint test | Quyền hành động được kiểm thử, không dùng production secret |
| Production | Read-only tối thiểu | Quyền ghi/gọi theo runbook và approval |

Các tài khoản hoặc secrets giữa môi trường không nên dùng chung nếu một credential bị lộ có thể dẫn đến truy cập cross-environment.

Ngay cả ở development, một endpoint JMX không xác thực có thể bị truy cập từ mạng chia sẻ; đừng suy đoán an toàn chỉ vì nhãn “dev”.

## 16. Ví dụ client chỉ đọc

Đoạn Java client đọc một attribute:

\`\`\`java
import java.util.HashMap;
import java.util.Map;

import javax.management.MBeanServerConnection;
import javax.management.ObjectName;
import javax.management.remote.JMXConnector;
import javax.management.remote.JMXConnectorFactory;
import javax.management.remote.JMXServiceURL;

public class ReadOnlyJmxClient {

    public static long readPendingJobs(
            JMXServiceURL url,
            String username,
            String password) throws Exception {

        Map<String, Object> env = new HashMap<>();
        env.put(
            JMXConnector.CREDENTIALS,
            new String[] { username, password }
        );

        try (JMXConnector connector =
                JMXConnectorFactory.connect(url, env)) {

            MBeanServerConnection connection =
                connector.getMBeanServerConnection();

            ObjectName queue = new ObjectName(
                "learning.jmx:type=QueueMetrics,name=Primary"
            );

            Object value =
                connection.getAttribute(queue, "PendingJobs");

            return ((Number) value).longValue();
        }
    }
}
\`\`\`

Đây là client pattern đơn giản. Nó chưa biểu thị cách credentials được lưu an toàn, cấu hình TLS, timeout hoặc audit. Trong production, username/password nên được lấy từ secret source được kiểm soát; endpoint cần authentication, authorization và TLS đúng.

Một bot read-only không nên có method gọi arbitrary \`invoke\` trong workflow nếu không cần.

## 17. Kiểm thử positive và negative cases

Chỉ kiểm tra tài khoản đọc thành công là chưa đủ. Cần chứng minh tài khoản đó **không được phép** làm những hành động ngoài scope.

### Test matrix

| Test | Reader | Operator |
|---|---|---|
| Kết nối tới endpoint được cấp | Cho phép | Cho phép |
| Đọc \`PendingJobs\` | Cho phép | Theo nhu cầu |
| Gọi \`pauseProcessing\` | Từ chối | Chỉ nếu được phê duyệt |
| Ghi writable attribute | Từ chối | Chỉ những attribute được phép |
| Truy cập endpoint môi trường khác | Từ chối | Từ chối trừ khi được cấp riêng |
| Đọc dữ liệu nhạy cảm không cần thiết | Không nên công bố | Chỉ khi có nhu cầu được phê duyệt |

Khi authorization layer chỉ hỗ trợ quyền rộng, ma trận dự định không tự thực thi được. Khi đó phải thay kiến trúc để có registry/connector hoặc API tách biệt, thay vì chỉ đặt tên role đẹp.

### Test thực tế

Một test kỹ thuật có thể:

1. Tạo connector được bảo vệ trong test environment.
2. Kết nối với reader credentials.
3. Đọc một attribute được phép và xác nhận giá trị.
4. Thử một thao tác thay đổi state trên test MBean an toàn.
5. Xác nhận quyền bị từ chối ở lớp phù hợp.
6. Kết nối bằng operator credentials và kiểm tra một operation được phép.
7. Dừng connector, cleanup MBeanServer và credentials test.

Không thực hiện destructive operation trên production để chứng minh quyền; dùng test fixture riêng.

## 18. Không trộn identity của bot với identity người vận hành

Một human operator và một automation bot có yêu cầu khác nhau:

- Human có thể phê duyệt và giải thích hành động.
- Bot chạy định kỳ, nhiều lần, không nhất thiết có approval cho mỗi invocation.
- Credential của bot thường lưu trong hệ thống máy, có nguy cơ bị truy cập qua workload.
- Một bot bị compromise có thể lặp thao tác nhiều lần.

Do đó, không cấp credential admin của người vận hành cho một cron job.

Nên dùng dedicated service account, với owner, purpose, scope, rotation policy và audit rõ ràng.

Khi một bot không còn hoạt động, phải thu hồi credential và xóa những firewall routes hoặc permissions không cần nữa.

## 19. Giới hạn tần suất và tác động của automation

Least privilege không chỉ là “được phép loại action nào”, mà còn liên quan phạm vi và tần suất.

Một read-only bot poll \`getFullReport\` mỗi 100 ms có thể gây CPU/GC pressure. Một maintenance bot gọi \`rebuildIndexes\` 50 lần có thể gây downtime dù nó có quyền hợp lệ.

Cần thiết kế:

- Polling intervals hợp lý.
- Backoff khi lỗi.
- Rate limiting ở workflow hoặc connector layer nếu được hỗ trợ.
- Concurrency controls cho operations.
- Idempotency hoặc job IDs để tránh duplicate retries.
- Timeouts và retry semantics.
- Monitoring về chính automation bot.

Nếu operation có thể gây tác động lớn, việc cấp quyền hợp lệ không có nghĩa bot được chạy vô hạn hoặc liên tục.

## 20. Tình huống thực tế

### Tình huống A — Metrics bot yêu cầu quyền readwrite

Một metrics exporter chỉ cần đọc \`QueueDepth\` nhưng được cấp \`readwrite\` vì kết nối thử nghiệm trước đó gặp lỗi.

Rủi ro: bot có thể gọi operation thay đổi trạng thái nếu connector cho phép.

Giải pháp: xác định lỗi thật (authentication, network, JMX read permissions, MBean semantics), sử dụng read-only identity, không mở rộng quyền khi chưa có bằng chứng.

### Tình huống B — CI job cần refresh configuration

Một CI job muốn gọi \`refreshConfiguration\` trong staging. Không nên cho CI runner truy cập chung credentials production admin.

Giải pháp: tạo identity staging riêng; giới hạn connector, credentials, role và window; audit invocation. Nếu policy JMX chỉ hỗ trợ readwrite quá rộng, cân nhắc API bảo trì riêng có scope chặt hơn.

### Tình huống C — Bot dùng cùng tài khoản cho monitoring và maintenance

Monitoring agent và maintenance scheduler dùng chung tài khoản \`jmx-admin\`. Khi monitoring container bị compromise, attacker có thể dùng credential đó cho write operations.

Giải pháp: tách identities và quyền; thu hồi credential cũ; kiểm tra log và toàn bộ connector access.

### Tình huống D — JMX endpoint trong Kubernetes

Một bot trong namespace monitoring cần poll một JVM. NetworkPolicy chỉ nên cho phép traffic cần thiết; không expose JMX port rộng tới mọi pod/ingress. Kiểm tra thêm quyền port-forward và secrets access.

### Tình huống E — Readonly nhưng lộ secret

Reader account không gọi được operations nhưng MBean \`ApplicationConfig\` có attribute chứa database password.

Giải pháp: sửa management API loại bỏ secret; giới hạn những MBeans/attributes có thể truy cập; rotate secret đã bị expose nếu cần.

## 21. Các lỗi thường gặp

| Vấn đề | Nguyên nhân | Cách xử lý |
|---|---|---|
| Bot được cấp readwrite chỉ để đọc metrics | Phân quyền quá rộng | Cấp readonly và sửa lỗi kết nối thực |
| Bot đọc được secret qua attribute | MBean export dữ liệu nhạy cảm | Không công bố secret, kiểm soát access |
| HTTP Security đã bật nhưng JMX vẫn mở | Hai đường truy cập độc lập | Bảo vệ JMX connector riêng |
| Bot không kết nối được sau bật TLS | Trust/identity/certificate sai | Sửa TLS config, không tắt SSL |
| Port JMX được mở cho toàn cluster | Network policy lỏng | Giới hạn source/destination |
| Bot không được phép subscribe notification | Authorization không hỗ trợ hoặc policy từ chối | Test quyền, điều chỉnh kiến trúc |
| Không có audit cho JMX operation | Connector mặc định không log đủ | Instrument operation/workflow |
| Secret của bot xuất hiện trong log | Logging credentials | Loại bỏ/redact log, rotate credential |
| Retry operation gây side effect nhiều lần | Thiếu idempotency/rate control | Giới hạn concurrency và dùng job ID |
| Một credential dùng nhiều môi trường | Secret reuse | Tách identity và secret theo environment |
| Tên role read-only nhưng thực tế vẫn ghi được | Label không phải enforcement | Test negative cases qua JMX |
| Chỉ phân tách MBeans nhưng dùng chung readwrite connector | Không có per-MBean policy | Tách connector/registry hoặc bổ sung enforcement |

## 22. Checklist triển khai

Trước khi cấp quyền cho một automation account:

1. Bot phục vụ mục đích nghiệp vụ/vận hành nào?
2. Cần read, write, invoke hay notifications?
3. Có MBeans/attributes/operations nào hoàn toàn không cần công bố?
4. Connector có hỗ trợ quyền cần cấp ở độ chi tiết mong muốn không?
5. Có dùng chung MBeanServer với các MBeans nhạy cảm khác không?
6. Identity của bot có tách khỏi human operator và bot khác không?
7. Credentials có được cấp từ secret manager và rotate được không?
8. Network route có giới hạn host, namespace, port và môi trường không?
9. TLS/authentication đã được cấu hình, không bị vô hiệu hóa không?
10. Có test reader không thể gọi operation không?
11. Có test operator chỉ được gọi thao tác cần thiết không?
12. Có audit cho lời gọi nhạy cảm không?
13. Bot có giới hạn polling, retry, rate và concurrency không?
14. Có owner và runbook thu hồi quyền khi không cần nữa không?
15. Có kế hoạch kiểm tra định kỳ quyền và unused accounts không?

## 23. Bài tập thực hành

### Bài tập 1 — Thiết kế roles

Một hệ thống có MBean \`QueueMetrics\` với \`PendingJobs\`, \`QueueAdmin\` với \`pauseProcessing\` và \`CacheAdmin\` với \`clearAllCache\`. Thiết kế quyền cho metrics reader, queue operator và cache operator. Nêu giới hạn của access-file readonly/readwrite đơn giản.

### Bài tập 2 — Positive/negative tests

Tạo test JMX connector có hai identities, reader và operator. Kiểm tra reader đọc được attribute, nhưng không được gọi operation thay đổi state. Dùng một test MBean an toàn thay vì production operation.

### Bài tập 3 — Threat model

Một monitoring container bị compromise. Hãy liệt kê những gì attacker có thể làm nếu credential có readwrite, so với readonly và network policy giới hạn.

### Bài tập 4 — Review MBean contract

Tìm các attributes trả secret hoặc dữ liệu nhạy cảm, operations làm thay đổi trạng thái và writable attributes. Đề xuất cách giảm surface mà không ảnh hưởng nhu cầu quan sát.

### Bài tập 5 — Runbook rotation

Một JMX automation account cần thay credentials. Viết checklist rotate secret, cập nhật workload, kiểm thử connection, thu hồi secret cũ và xác nhận không có credentials trong logs.

## 24. Ghi nhớ cốt lõi

- **Tài khoản tự động hóa phải tuân thủ least privilege theo nhu cầu thực tế.**
- JMX có thể cho phép đọc, ghi và gọi operations; không phải một kênh chỉ đọc mặc định.
- Phân biệt network access, authentication và authorization.
- Quyền readonly/readwrite của JDK management agent có thể quá thô cho nhu cầu per-operation; đừng tự giả định có fine-grained RBAC.
- Tách monitoring và maintenance identities, quản lý secret và network routes riêng.
- Không coi Spring HTTP Security là bảo vệ cho remote JMX connector.
- Giới hạn dữ liệu/MBeans được export; readonly không tự ngăn lộ secret nếu attribute chứa dữ liệu nhạy cảm.
- Kiểm thử cả hành vi được phép và bị từ chối trên đường kết nối JMX thực tế.
- Audit, rotation, rate limiting và cleanup là một phần của chiến lược giới hạn quyền.

## Tài liệu tham khảo

- Oracle Java Management and Monitoring with JMX: https://docs.oracle.com/en/java/javase/21/management/monitoring-and-management-using-jmx-technology.html
- Oracle Java SE Management and Monitoring Guide: https://docs.oracle.com/en/java/javase/21/management/
- Java SE API — JMXConnector: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/remote/JMXConnector.html
- Java SE API — MBeanServerConnection: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanServerConnection.html
- Spring Framework JMX Reference: https://docs.spring.io/spring-framework/reference/integration/jmx.html
- Spring Framework ManagedResource: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/export/annotation/ManagedResource.html
