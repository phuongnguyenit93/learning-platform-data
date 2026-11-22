# Theo dõi bản vá, cảnh báo bảo mật và nhật ký thao tác quản trị

> **Chương:** Bảo mật  
> **Học phần:** `INTEGRATION_MESSAGING_MESSAGE_BROKER_ACTIVEMQ` — Apache ActiveMQ Classic và Artemis trong giao tiếp bất đồng bộ bằng queue, topic, routing và JMS; thực hành producer/consumer Java, acknowledgment, transaction, redelivery, DLQ, bảo mật và vận hành broker đáng tin cậy.  
> **Phạm vi:** Quy trình theo dõi advisory, xác định phiên bản bị ảnh hưởng, triển khai bản vá an toàn và lưu bằng chứng **ai thực hiện thao tác quản trị nào, trên broker nào, lúc nào**. Ví dụ tập trung vào Artemis 2.x và Classic 5.x, có cấu hình logging và Java/JMS. Các mẫu cấu hình phải được kiểm tra với phiên bản broker đang vận hành.

## 1. Bản vá và audit giải quyết hai nửa của một sự cố

Một cụm ActiveMQ Artemis có queue `payments.commands` bị tạm dừng, backlog tăng. Cùng ngày, có deployment thay đổi image broker và security roles. Đội vận hành cần trả lời đồng thời:

- **Đang chạy bản nào?** Release, image digest, JVM, plugin, client library và cấu hình thực tế.
- **Có advisory nào liên quan?** Phạm vi affected/fixed versions, protocol và management endpoints thực sự được bật.
- **Ai đổi gì?** Thao tác pause queue, tạo/xóa destination, thay roles/ACL hoặc redeploy do ai thực hiện?
- **Có an toàn khi vá/rollback?** Broker store/journal, HA/cluster, JMS client compatibility và các message chưa ACK có được giữ không?

Nếu chỉ theo dõi CVE mà không ghi thao tác quản trị, đội phản ứng sự cố khó phân biệt hành vi trái phép với thay đổi hợp lệ. Nếu chỉ lưu audit.log nhưng không giữ inventory phiên bản runtime, khó kết luận bản vá đã thực sự được triển khai.

~~~mermaid
flowchart LR
    A["Asset inventory + SBOM"] --> B["Apache advisories / CVE / vendor"]
    B --> C["Triage phạm vi + exposure"]
    C --> D["Patch plan + staging + backup"]
    D --> E["Rollout + verify running versions"]
    E --> F["Update inventory / close risk"]
    G["Broker admin + security audit"] --> H["SIEM + immutable evidence"]
    I["Git / CI-CD / OS / K8s audit"] --> H
    H --> C
    H --> E
~~~

**Nguyên tắc:** Một phiếu “đã vá” cần có **bằng chứng runtime version và regression tests**. Một phiếu “đã kiểm toán” cần có **bằng chứng từ nhiều đường quản trị**, không chỉ một file log.

## 2. Inventory phải bao phủ broker, client và control plane

| Tài sản | Cần ghi lại | Vì sao cần |
|---|---|---|
| **Artemis broker** | Release, build/image digest, JVM, HA topology, protocols/acceptors | Advisory có thể ở Core, AMQP, security manager, management, journal hoặc dependency |
| **Classic broker** | Release, image/package, JVM, OpenWire/other connectors, KahaDB, plugins | Codebase và cơ chế vá khác Artemis |
| **Java JMS client** | Resolved Maven GAV, `jakarta.jms`/`javax.jms`, wire protocol | Vá broker không tự nâng client đang nằm trong ứng dụng |
| **Spring Boot service** | Starter, BOM, dependency tree, SBOM, runtime JRE | Thư viện transitive có thể cần patch độc lập |
| **Management** | Web console, Jolokia, JMX, CLI, reverse proxy, RBAC, network reachability | Nhiều thao tác đặc quyền nằm ngoài JMS data plane |
| **Configuration** | broker.xml/activemq.xml, login modules, roles/ACL, TLS/secret refs, Git revision | Patch không thay thế least privilege hoặc chứng chỉ hợp lệ |
| **Persistence** | Journal/KahaDB, page/large-message store, HA replication và backup policy | Upgrade/rollback ảnh hưởng dữ liệu đang giữ |

**Không đánh đồng Classic với Artemis.** Một advisory ghi ActiveMQ Classic không tự động áp lên Artemis; nhưng một client Classic hoặc thư viện dùng chung có thể vẫn cần xử lý. Chỉ kết luận sau khi đọc chính xác **sản phẩm, thành phần, affected version, điều kiện khai thác và fixed version**.

### 2.1. Inventory có thể dùng cho triage

~~~yaml
# Schema inventory minh họa, KHÔNG phải cấu hình broker.
asset_id: mq-orders-prod-01
environment: production
product: apache-artemis
runtime_version: "<verified-runtime-version>"
container_digest: "sha256:<verified-digest>"
jvm_version: "<runtime-jvm-version>"
protocols_enabled: [CORE, AMQP]
management_exposure: "private-network-behind-auth-gateway"
data_store: "journal+paging+large-message"
owner_team: platform-messaging
security_baseline_revision: "<git-commit>"
last_verified_at_utc: "<timestamp>"
~~~

Không gán phiên bản dựa vào `pom.xml` của producer rồi cho rằng broker cũng dùng bản đó. Trong rolling deployment, cần biết **phiên bản đang chạy của từng node**, không chỉ deployment manifest đã thay.

## 3. Nguồn cảnh báo bảo mật và chu kỳ theo dõi

| Nguồn | Cung cấp điều gì? | Cần đối chiếu |
|---|---|---|
| **Trang security advisories chính thức Apache ActiveMQ** | Phạm vi ảnh hưởng, cách khắc phục và tham chiếu upstream | Đúng Artemis hay Classic, affected/fixed release |
| **Apache release notes / announce mailing list** | Bản vá đã phát hành, incompatibilities, hướng upgrade | Release đã thực sự có artifact được phát hành chưa |
| **CVE / NVD** | Định danh và mô tả lỗ hổng, tham chiếu, điểm mức độ | Dữ liệu NVD có thể được cập nhật sau; không chỉ nhìn score |
| **Vendor JDK, OS, base image và distro** | Backported patches và thay đổi package dependencies | Version string có thể chưa phản ánh vendor backport |
| **SBOM/SCA tooling** | Client, transitive dependency và library hiện diện | False positives, shaded jars, reachability |
| **SIEM / pentest / incident evidence** | Bằng chứng cố gắng khai thác hoặc policy sai | Có thể cần can thiệp ngay cả khi chưa có CVE |

**Không hardcode danh sách CVE hay “bản mới nhất” cố định vào giáo trình.** Khi triage, phải truy nguồn advisory hiện hành, ghi **ngày xác minh**, artifact/version và bằng chứng áp dụng, đặc biệt đối với sản phẩm có release nhanh.

### 3.1. Một chu kỳ vận hành rõ ràng

- **Tự động hoặc hàng ngày:** nhận advisory/release và quét asset/SBOM; cảnh báo có đường khai thác đáng kể được chuyển vào security queue.
- **Theo lịch, chẳng hạn hàng tuần:** rà tất cả advisory mở, ngoại lệ chưa vá, và client/broker chưa được kiểm tra.
- **Khi khẩn:** kích hoạt SLA incident/patch theo đánh giá rủi ro, không đợi chu kỳ thông thường.
- **Trước rollout:** chốt affected/fixed version, patch test plan, backup và rollback.
- **Sau rollout:** xác minh binary/runtime, security regression, messaging/HA recovery và cập nhật evidence.

Một subscription tới mailing list chưa phải quy trình nếu không có người chịu trách nhiệm phân loại và đóng việc.

### 3.2. Mẫu phiếu xử lý advisory

~~~text
Advisory ID / nguồn / ngày công bố:
Product, component, affected version range:
Fixed release hoặc vendor backport:
Broker nodes / Java clients bị ảnh hưởng:
Protocol, management endpoint, network exposure:
Tiền điều kiện khai thác (authn, roles, config):
Bằng chứng scanning/incident nếu có:
Kết luận: AFFECTED / NOT_AFFECTED / INVESTIGATING
Độ ưu tiên, SLA, owner:
Mitigation tạm và ngày hết hạn:
Patch window, HA/store compatibility, rollback:
Test ID và runtime verification sau triển khai:
Approval, ticket và audit evidence reference:
~~~

**CVSS không phải câu trả lời duy nhất.** Một management interface exposed Internet có mức rủi ro khác với cùng component được khóa trong private segment có strong auth. Nhưng “chỉ nội bộ” cũng không làm một lỗi critical biến mất; còn khả năng credential theft và lateral movement.

## 4. Kiểm tra đúng phiên bản broker và dependency Java

### 4.1. Runtime broker khác image tag và client version

Với Artemis, dùng công cụ `artemis` đi kèm distribution để kiểm tra version, ví dụ khi CLI có subcommand phù hợp:

~~~powershell
# Chạy tại instance hoặc bộ công cụ quản trị được cho phép.
# Kiểm tra syntax hỗ trợ của đúng bản Artemis đang dùng.
./artemis version
~~~

Bổ sung bằng broker startup banner, management API hoặc release metadata từ distribution, tùy cách tổ chức quản trị. Với container, lưu **image digest**, không chỉ mutable tag như `latest` hoặc `stable`.

Với Classic, xem version thực từ startup/management và distribution image/package, **không dùng version của Artemis client** để suy ra bản Classic server.

**Bằng chứng cần khớp nhau:** runtime process/version, image digest, broker node ID, config revision và thời điểm đo.

### 4.2. Maven dependency tree cho ứng dụng

Tại dự án Maven sử dụng Spring Boot starter Artemis/Classic:

~~~powershell
mvn dependency:tree "-Dincludes=org.apache.activemq"
~~~

Khi kết quả khác mong đợi, kiểm tra BOM, dependencyManagement, exclusions, overrides và các JAR được đóng gói thực tế. `spring-boot-starter-artemis` và `spring-boot-starter-activemq` là hai nhánh khác nhau; Spring Boot 3 dùng `jakarta.jms`, Classic client cũ có thể dùng `javax.jms`.

### 4.3. Sinh SBOM với Maven để phân loại CVE

Ví dụ một bản plugin được pin cho bài học:

~~~powershell
mvn -DskipTests org.cyclonedx:cyclonedx-maven-plugin:2.9.1:makeBom
~~~

Theo cấu hình plugin, artifact thường là `target/bom.xml` hoặc `target/bom.json`; hãy xác minh file đầu ra thật và giữ cùng build. **SBOM ứng dụng chưa bao gồm broker image, JVM và OS** nếu chúng được deploy riêng. Cần SBOM/inventory cả hai phía.

Nếu SCA báo một library có CVE, phải đánh giá: library có mặt ở artifact runtime không, version chính xác không, component có reachable không, vendor có backport không, và advisory có điều kiện đặc biệt nào. Không tự bỏ qua vì “chưa thấy exception”.

### 4.4. Bằng chứng supply-chain

Sau khi quyết định target release, lưu:

~~~text
Package SHA-256 hoặc OCI image digest
Release notes và advisory reference
Source/signature/provenance verification theo chính sách
Broker/JVM/plugin effective versions
Git config revision và image rollout revision
Backup/restore rehearsal ID
Staging tests và canary result
Change approver, window, rollback decision
Post-patch runtime version và audit sample
~~~

Checksum chỉ mạnh nếu **nguồn checksum đáng tin**; nếu tổ chức sử dụng chữ ký phát hành, phải kiểm tra chữ ký/chains từ nguồn phù hợp chứ không so một hash với giá trị lấy từ cùng host bị nghi xâm nhập.

## 5. Triage lỗ hổng theo bề mặt thật của broker

Khi một advisory xuất hiện, xét tuần tự:

1. **Product:** Artemis, Classic, console, management, client hoặc dependency transitive?
2. **Affected version:** bản hiện chạy nằm trong phạm vi nào? Có bản vá backport không?
3. **Entry point:** CORE/OpenWire/AMQP/STOMP/MQTT, HTTP/Jolokia, JMX hay thao tác local?
4. **Reachability:** acceptor có bật không, ai từ đâu chạm tới, có TLS/gateway/firewall?
5. **Permissions:** cần user thường, admin, unauthenticated, hoặc quyền tạo destination?
6. **Impact:** lộ dữ liệu, sửa/làm mất message, DoS, leo quyền quản trị hay execution?
7. **Remediation:** fixed release, mitigation tạm, restart/rolling rollout và compatibility?
8. **Evidence:** cách kiểm tra bản vá đã chạy và đường tấn công bị chặn?

Một advisory management API không thể được coi là xử lý xong chỉ vì **JMS listener** đã nối TLS. Cần kiểm tra management port, JMX/Jolokia/console, identity provider và phân quyền quản trị riêng.

### 5.1. Ví dụ tình huống giả định, không phải CVE thực tế

~~~text
Affected broker version: YES
Vulnerable management path enabled: YES
Reachable trực tiếp từ Internet: NO
Reachable từ bastion/admin network: YES
Mitigation: giới hạn network + MFA + kiểm soát admin roles
Owner & exception expiry: assigned
Permanent remediation: fixed release sau test staging
Evidence: node version, gateway rule, auth deny test, audit
~~~

Không đánh dấu `NOT_AFFECTED` chỉ vì management nằm trong private subnet. Có thể ghi `AFFECTED_WITH_MITIGATION` cho tới khi patch đúng và xác minh kết quả.

## 6. Patch broker có thể đụng đến durability, HA và rollback

~~~mermaid
flowchart TD
    A["Advisory + fixed version"] --> B["Review compatibility + data store format"]
    B --> C["Backup/restore rehearsal"]
    C --> D["Staging: security + JMS + persistence tests"]
    D --> E{"PASS?"}
    E -->|Không| F["Sửa plan; không rollout"]
    E -->|Có| G["Canary hoặc maintenance window"]
    G --> H["Runtime version + broker health + audit"]
    H --> I{"Kết quả ổn?"}
    I -->|Có| J["Close advisory + inventory update"]
    I -->|Không| K["Rollback theo store compatibility plan"]
~~~

### 6.1. Trước khi nâng cấp

- Ghi rõ **dòng broker**: Classic dùng mô hình store/config khác Artemis; không thay executable này lên data directory dòng kia.
- Đọc upgrade guidance: store/journal schema, serialization, TLS/client protocol, broker.xml/activemq.xml, security plugin compatibility.
- Kiểm tra queues, durable subscriptions, in-flight, DLQ, scheduled message, prepared transactions và disk headroom.
- Backup nhất quán, **đã restore thử**, không chỉ chụp thư mục data đang thay đổi trong khi broker chạy.
- Dự kiến downtime/rolling upgrade theo topology thực; không tuyên bố mọi version tương thích rolling.
- Xác định producer retry và consumer idempotency: broker restart có thể gây trạng thái gửi/ACK không chắc chắn.

### 6.2. Staging regression cần có

| Test | Bằng chứng cần |
|---|---|
| Authentication | User đúng được chấp nhận; password sai bị từ chối |
| Authorization | Writer send, reader consume, user thường không quản trị |
| TLS | Certificate chain/SAN đúng, truststore và ciphers theo policy |
| Queue/topic | Đúng routing, durable subscription và destination |
| JMS transactions | Commit/rollback, redelivery, DLQ và không mất persistent message |
| Storage | Journal/paging/large-message recovery khi broker restart |
| HA/failover | Backup/replication/reconnect theo topology đang dùng |
| Management | Console/JMX/Jolokia không mở rộng quyền, audit hoạt động |
| Client compatibility | Java clients/Spring Boot hiện hữu handshake và xử lý |
| Rollback | Khả năng đọc store/config của bản cũ đã được kiểm chứng |

### 6.3. Vì sao downgrade có thể không an toàn?

Bản broker mới có thể thay cấu trúc dữ liệu store, file journal hoặc config. Khi đã ghi dữ liệu bằng bản mới, **đổi image về bản cũ không tự chứng minh broker cũ đọc được store**. Kế hoạch rollback cần nêu rõ: có hỗ trợ downgrade không, hay phải restore backup nhất quán, và chấp nhận mất bao nhiêu dữ liệu theo RPO.

Sau rollout, đóng ticket chỉ khi có **runtime version từng node + digest**, smoke tests, HA/storage, ACL/TLS tests và bằng chứng audit; một Git merge chưa đủ.

## 7. Phân loại nhật ký: application log không phải audit đầy đủ

| Loại log | Phục vụ | Điểm mù điển hình |
|---|---|---|
| Broker application/error log | Restart, journal errors, failover, exception | Có thể thiếu actor của JMX operation thành công |
| Authentication/security log | Login failure, authorization denial, TLS error | Có thể không ghi mọi admin operation thành công |
| Management/resource audit | Ai tạo/xóa/pause queue, gọi quản trị, thời gian/kết quả | Không tự biết ai sửa file ngoài broker |
| Message audit | Quan sát send/receive theo cấp broker nếu hỗ trợ | Không chứng minh business DB transaction đã commit |
| HTTP console/proxy access | HTTP request, nguồn truy cập, authentication gateway | Không phải mọi thay đổi đi qua console |
| Git/CI-CD/Kubernetes/OS audit | Ai đổi binary, deployment, config, secret/cert | Không tự ghi một JMS message được publish |

Ví dụ một operator sửa `broker.xml` rồi restart: broker có thể log restart nhưng **không tự ghi “operator sửa role X thành Y”** như management method. Cần **Git change review, deployment logs, Kubernetes API audit hoặc OS file audit** tương ứng.

### 7.1. Audit record chuẩn hóa cho SIEM

~~~json
{
  "timestamp": "2026-11-17T08:30:00Z",
  "assetId": "mq-orders-prod-01",
  "category": "BROKER_ADMIN",
  "actor": "operator-id",
  "source": "management-api",
  "operation": "pauseQueue",
  "target": "queue:orders.work",
  "outcome": "SUCCESS",
  "changeTicket": "CHG-0142"
}
~~~

Đây là **schema khuyến nghị khi parse/enrich vào SIEM**, **không phải log JSON nguyên bản bắt buộc của Artemis/Classic**. Một số field như source IP, ticket ID hoặc SSO identity cần ghép từ gateway/identity/CI-CD chứ không có sẵn trong mọi broker event. Không bịa field khi nguồn không cung cấp.

### 7.2. Nhóm thao tác cần có audit

- Queue/address create, delete, purge, move/expire messages, pause/resume.
- Thay DLQ, redelivery, expiry, max size, paging hoặc routing policy.
- Thêm/xóa user, role, ACL, TLS certificate và management access.
- Thao tác JMX/Jolokia/web console có quyền cao.
- Thay acceptor/connector, protocol exposure hoặc network policy.
- Disable audit logger, đổi log retention hoặc ngừng log collector.
- Thay broker image/config/secret, deploy/restart, downgrade.

Hai dòng cuối thường cần **control-plane audit ngoài broker**. Một file `audit.log` dù rất chi tiết vẫn không thể thay thế chúng.

## 8. Artemis: audit logger và Log4j2

Artemis có audit logging theo những category phổ biến trên các phiên bản hỗ trợ:

- `org.apache.activemq.audit.base` — activity nền/quản trị theo cơ chế broker.
- `org.apache.activemq.audit.resource` — activity với resources như queue/address.
- `org.apache.activemq.audit.message` — sự kiện message; có thể rất nhiều.

**Quan trọng:** kiểm tra tài liệu và **cấu hình logging được nạp ở runtime** của phiên bản Artemis đang chạy. Các bản cũ có thể dùng `logging.properties` hoặc cấu hình khác; snippet `log4j2.properties` không áp dụng nguyên xi cho mọi version.

### 8.1. Mảnh cấu hình Log4j2 cho audit file

Thêm/hợp nhất vào `etc/log4j2.properties` **nếu broker đang dùng Log4j2**:

~~~properties
# MẢNH cấu hình, KHÔNG thay thế cả file.
# Thêm audit_file vào danh sách appenders nếu file yêu cầu.
# Thêm audit_base/audit_resource/audit_message vào danh sách loggers
# mà không xóa cấu hình logger/appender khác.

appender.audit_file.type = RollingFile
appender.audit_file.name = AUDIT_FILE
appender.audit_file.fileName = ${sys:artemis.instance}/log/audit.log
appender.audit_file.filePattern = ${sys:artemis.instance}/log/audit-%d{yyyy-MM-dd}-%i.log.gz
appender.audit_file.layout.type = PatternLayout
appender.audit_file.layout.pattern = %d{ISO8601} %-5p [%c] %m%n
appender.audit_file.policies.type = Policies
appender.audit_file.policies.size.type = SizeBasedTriggeringPolicy
appender.audit_file.policies.size.size = 20MB
appender.audit_file.strategy.type = DefaultRolloverStrategy
appender.audit_file.strategy.max = 10

logger.audit_base.name = org.apache.activemq.audit.base
logger.audit_base.level = INFO
logger.audit_base.additivity = false
logger.audit_base.appenderRef.audit_file.ref = AUDIT_FILE

logger.audit_resource.name = org.apache.activemq.audit.resource
logger.audit_resource.level = INFO
logger.audit_resource.additivity = false
logger.audit_resource.appenderRef.audit_file.ref = AUDIT_FILE

# Không bật toàn bộ message audit nếu chưa tính volume/PII.
logger.audit_message.name = org.apache.activemq.audit.message
logger.audit_message.level = OFF
logger.audit_message.additivity = false
logger.audit_message.appenderRef.audit_file.ref = AUDIT_FILE
~~~

**Ghi chú cấu hình:**

- `${sys:artemis.instance}` là Log4j2 system-property substitution theo ví dụ; phải xác minh property/path được thiết lập trong deployment thực tế.
- Nếu file đang có danh sách `appenders` và `loggers`, thêm các tên trên theo syntax thực tế, đừng thay cả danh sách làm mất log hệ thống.
- `audit_message` có thể tạo lượng lớn record, ảnh hưởng hiệu năng/disk và privacy; mặc định **OFF** trong bài, chỉ bật khi có mục tiêu và thời hạn điều tra.
- Đảm bảo file audit có permission/owner đúng, rotation và retention; tránh cùng volume đầy với journal/paging.
- Xác minh broker thực sự load logger mới sau reload/restart phù hợp; đọc file config đơn lẻ chưa đủ chứng minh.

### 8.2. Những gì broker audit không tự ghi

~~~text
Admin qua management API/JMX/Jolokia:
    broker operation -> audit logger (nếu bật/có coverage)

Admin sửa ConfigMap/broker.xml, secret, image:
    Git / CI-CD / Kubernetes API / OS audit
    -> broker restart/reload có thể xuất hiện trong application log
    -> không mặc định có record "ai sửa ACL" từ broker audit
~~~

Một audit category có thể ghi method/resource nhưng không có đầy đủ IP nguồn hoặc SSO identity. Đối chiếu access logs, JMX gateway, deployment change log và identity provider khi cần bằng chứng có thể điều tra.

### 8.3. Kiểm thử audit logger trên broker lab

1. Ghi timestamp UTC, broker node ID, config revision và kích thước `audit.log` ban đầu.
2. Dùng management console/API **được cấp quyền** để đọc danh sách queue, quan sát log nếu operation được bao phủ.
3. Tạo queue test `lab.audit.ephemeral` bằng admin đã được ủy quyền.
4. Kiểm tra audit event với operation, resource, result và identity có sẵn; nếu thiếu trường, xác định nguồn enrich.
5. Dùng account **không có quyền admin** thử quản lý queue lab và xác nhận DENIED ở security/audit path.
6. Chỉ xóa queue lab vừa tạo sau khi xác minh không có message.
7. Kiểm tra rotation và central collector; không purge log để “làm sạch”.

**Audit coverage phải được chứng minh bằng một thao tác quản trị cụ thể**, không phải chỉ kiểm tra file tồn tại.
## 9. ActiveMQ Classic: đừng nhầm broker logging với audit đầy đủ

Classic dùng cơ chế plugin, cấu hình `activemq.xml` và hệ thống logging theo release/distribution. **Không copy logger category và Log4j2 snippet của Artemis** rồi mặc định chúng ghi được các thao tác Classic.

Một plugin có thể giúp quan sát sự kiện broker/connection là `loggingBrokerPlugin`. Mảnh XBean đặt trong phần `<plugins>` của Classic:

~~~xml
<!-- Mảnh lab: kiểm tra syntax và sự hỗ trợ với Classic đang dùng. -->
<loggingBrokerPlugin
    logAll="false"
    logConnectionEvents="true"
    logConsumerEvents="true"
    logProducerEvents="true"
    logInternalEvents="false"/>
~~~

**Giới hạn rất quan trọng:** plugin này chủ yếu ghi các hoạt động broker/client mà plugin hỗ trợ. Nó **không bảo đảm** ghi đầy đủ mọi thao tác qua JMX, web console, cập nhật `activemq.xml`, thay file JAAS, đổi binary và deployment. Nó cũng không phải kho audit chống sửa/xóa.

Khi vận hành Classic, cần ghép nhiều nguồn:

| Loại thao tác | Nguồn nên kiểm tra |
|---|---|
| Connection, consumer, producer | Broker application/plugin logs |
| Authentication/authorization failure | Authentication/JAAS/ACL/security logs |
| Web console | Jetty/reverse proxy access logs và identity provider |
| JMX management | JMX gateway/instrumentation hoặc management audit phù hợp |
| Sửa `activemq.xml`, TLS hoặc users | Git, CI/CD, OS filesystem audit |
| Nâng binary, restart, thay image | Runtime/container/orchestrator logs và change record |

Không bật `logAll=true` cho mọi broker production chỉ vì muốn “audit tốt hơn”: có thể phát sinh throughput log lớn, tốn I/O và lộ metadata, nhưng vẫn còn khoảng trống control plane. Từng nguồn phải có **test chứng minh coverage**.

### 9.1. Classic permissions và đường quản trị

Classic ACL thường phân loại `read`, `write` và `admin` với các authorization plugin/entries phù hợp. Artemis tách `send`, `consume`, `browse` và các quyền tạo/xóa queue/address riêng. Do đó:

- Một thao tác JMS bị từ chối cần ghi **quyền của đúng sản phẩm**.
- Không suy rằng quyền `read` của Classic tương đương một user audit chỉ được browse như `browse` của Artemis.
- Một service account chỉ cần gửi/nhận không nên được cấp quyền quản trị queue.
- Console/JMX có thể sử dụng security realm/quyền riêng; kiểm chứng tường minh thay vì chỉ nhìn JMS ACL.

## 10. Lab Java/JMS: sinh sự kiện được phép và bị từ chối

Mục tiêu của chương trình sau là sinh **bằng chứng authentication/authorization** để đối chiếu với broker security logs. Đây **không phải** công cụ quản trị JMX; để kiểm tra audit của thao tác admin, cần thao tác lab ở mục 8.3.

Ví dụ dùng Artemis **2.40.0**, Java 17 và Jakarta JMS 3.1. Broker lab có address/queue `lab.security.audit`; hai user:

- `lab-writer` thuộc role `lab-audit-writer`, được gửi.
- `lab-reader` thuộc role `lab-audit-reader`, không được gửi.

### 10.1. Queue và quyền thử nghiệm trong Artemis

Mảnh cấu hình `broker.xml` đặt dưới `<addresses>` đang tồn tại:

~~~xml
<address name="lab.security.audit">
    <anycast>
        <queue name="lab.security.audit" durable="true"/>
    </anycast>
</address>
~~~

Mảnh dưới `<security-settings>`:

~~~xml
<security-setting match="lab.security.audit">
    <permission type="send" roles="lab-audit-writer"/>
    <permission type="consume" roles="lab-audit-reader"/>
</security-setting>
~~~

Phải provision role/user bằng security backend thực của broker (JAAS/properties/LDAP...) và **đảm bảo rule match hiệu lực**. Nếu một user còn role admin hoặc wildcard permissive, phép thử `DENIED` có thể không phản ánh cấu hình dự định. Không đổi quyền queue production chỉ để thực hiện lab.

### 10.2. Maven dependencies

Cấu trúc:

~~~text
artemis-security-audit-lab/
├── pom.xml
└── src/main/java/lab/AuditSecurityProbe.java
~~~

`pom.xml`:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <groupId>lab</groupId>
  <artifactId>artemis-security-audit-lab</artifactId>
  <version>1.0.0</version>
  <properties>
    <maven.compiler.release>17</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
  </properties>
  <dependencies>
    <dependency>
      <groupId>org.apache.activemq</groupId>
      <artifactId>artemis-jakarta-client</artifactId>
      <version>2.40.0</version>
    </dependency>
    <dependency>
      <groupId>jakarta.jms</groupId>
      <artifactId>jakarta.jms-api</artifactId>
      <version>3.1.0</version>
    </dependency>
  </dependencies>
  <build>
    <plugins>
      <plugin>
        <groupId>org.apache.maven.plugins</groupId>
        <artifactId>maven-compiler-plugin</artifactId>
        <version>3.13.0</version>
      </plugin>
      <plugin>
        <groupId>org.codehaus.mojo</groupId>
        <artifactId>exec-maven-plugin</artifactId>
        <version>3.5.0</version>
      </plugin>
    </plugins>
  </build>
</project>
~~~

### 10.3. Java: một thao tác gửi có định danh để đối chiếu

File `src/main/java/lab/AuditSecurityProbe.java`:

~~~java
package lab;

import java.util.UUID;

import jakarta.jms.ConnectionFactory;
import jakarta.jms.DeliveryMode;
import jakarta.jms.JMSContext;
import jakarta.jms.JMSRuntimeException;
import jakarta.jms.Queue;
import jakarta.jms.TextMessage;
import org.apache.activemq.artemis.jms.client.ActiveMQConnectionFactory;

public final class AuditSecurityProbe {
    private static final String DESTINATION = "lab.security.audit";

    private AuditSecurityProbe() {}

    public static void main(String[] args) {
        if (args.length != 1 || !"send".equals(args[0])) {
            throw new IllegalArgumentException("Dùng: send");
        }

        String brokerUrl = System.getenv().getOrDefault(
                "BROKER_URL", "tcp://127.0.0.1:61616");
        String user = require("BROKER_USER");
        String password = require("BROKER_PASSWORD");
        String testId = "audit-lab-" + UUID.randomUUID();

        ConnectionFactory factory =
                new ActiveMQConnectionFactory(brokerUrl);

        try (JMSContext ctx = factory.createContext(
                user, password, JMSContext.SESSION_TRANSACTED)) {
            Queue queue = ctx.createQueue(DESTINATION);
            TextMessage message =
                    ctx.createTextMessage("test-audit-event");
            message.setStringProperty("testId", testId);

            ctx.createProducer()
               .setDeliveryMode(DeliveryMode.PERSISTENT)
               .send(queue, message);

            ctx.commit();  // Đây là producer JMS commit, không phải DB commit.
            System.out.println("JMS_PUBLISH_COMMITTED"
                    + " user=" + user
                    + " destination=" + DESTINATION
                    + " testId=" + testId);
        } catch (JMSRuntimeException e) {
            System.err.println("JMS_OPERATION_FAILED"
                    + " user=" + user
                    + " operation=send"
                    + " destination=" + DESTINATION
                    + " testId=" + testId
                    + " exceptionType=" + e.getClass().getSimpleName());
            throw e;
        }
    }

    private static String require(String key) {
        String result = System.getenv(key);
        if (result == null || result.isBlank()) {
            throw new IllegalArgumentException("Thiếu " + key);
        }
        return result;
    }
}
~~~

**Giải thích:**

- User có `send` và broker/queue hợp lệ sẽ nhận `JMS_PUBLISH_COMMITTED`. Đó là mốc **producer**, không phải consumer đã hoàn tất nghiệp vụ.
- User được xác thực nhưng thiếu `send` có thể thấy `JMSRuntimeException`; loại exception và thời điểm phát sinh phụ thuộc provider.
- Sai password cũng có thể gây `JMSRuntimeException` nhưng ở **authentication** chứ không phải authorization; phân loại bằng security log từ broker.
- `testId` là application correlation ID. Broker audit category có thể **không ghi custom JMS properties**, nhất là khi message audit đang OFF. Không giả định tìm được testId trực tiếp trong audit.log; đối chiếu bằng thời gian, user, operation/destination và log ứng dụng.
- Nếu connection mất lúc `commit()`, producer có thể không biết broker đã commit chưa. Thử lại cần event ID ổn định và idempotent consumer, không kết luận “gửi thất bại chắc chắn” chỉ từ timeout.

### 10.4. Chạy ba ca

Trong PowerShell:

~~~powershell
$env:BROKER_URL = "tcp://127.0.0.1:61616"
mvn -q -DskipTests package

# Có quyền gửi.
$env:BROKER_USER = "lab-writer"
$env:BROKER_PASSWORD = "LAB_ONLY_WRITER_PASSWORD"
mvn -q exec:java "-Dexec.mainClass=lab.AuditSecurityProbe" "-Dexec.args=send"

# Đăng nhập hợp lệ nhưng không có quyền gửi.
$env:BROKER_USER = "lab-reader"
$env:BROKER_PASSWORD = "LAB_ONLY_READER_PASSWORD"
mvn -q exec:java "-Dexec.mainClass=lab.AuditSecurityProbe" "-Dexec.args=send"

# Sai mật khẩu: authentication phải thất bại.
$env:BROKER_USER = "lab-writer"
$env:BROKER_PASSWORD = "WRONG_PASSWORD"
mvn -q exec:java "-Dexec.mainClass=lab.AuditSecurityProbe" "-Dexec.args=send"
~~~

Đối chiếu:

| Ca | Ứng dụng | Broker cần quan sát |
|---|---|---|
| Writer có `send` | Commit OK | Có giao dịch gửi; message audit nếu thực sự bật/phủ thao tác |
| Reader không có `send` | Thao tác gửi bị từ chối | Authorization failure, user/role/address |
| Sai credential | Context/connect thất bại | Authentication failure, không nhầm với thiếu quyền |
| Admin tạo queue lab | Không qua JMS code này | Management/resource audit + console/access log |

Không chạy trên queue production hoặc user thực có nhiều đặc quyền. Dọn message thử bằng management API có phê duyệt trên queue lab; không tự xóa file journal.

## 11. Từ broker audit tới SIEM: bằng chứng phải có toàn vẹn

~~~mermaid
flowchart LR
    A["Artemis audit.log"] --> C["Log collector"]
    B["Classic broker + console/JMX access"] --> C
    D["Git + CI/CD + Kubernetes / OS audit"] --> C
    C --> E["Parser / enrichment"]
    E --> F["SIEM / append-only retention"]
    F --> G["Alerts / investigation timeline"]
~~~

### 11.1. Trường cần bảo toàn

- Timestamp của nguồn và `ingestedAt` riêng; đồng bộ **UTC/NTP** để ghép sự kiện.
- Product, broker/node ID, environment, image digest và log source.
- Actor/role, operation, resource/destination và outcome **nếu nguồn cung cấp**.
- Client IP hoặc SSO identity từ proxy/identity system **nếu có**, không tự suy đoán.
- Change ticket/deployment revision từ CI/CD hoặc management gateway.
- Parser version và integrity/checksum nếu log retention policy yêu cầu.

Một raw audit record Artemis không nhất thiết đã có tất cả trường này. SIEM có thể enrich từ nhiều hệ thống, nhưng cần giữ **raw record** để kiểm chứng và tránh bịa dữ kiện.

### 11.2. Phân quyền, lưu trữ và bảo vệ audit

- Broker operator không được có quyền tự xóa bản lưu SIEM.
- Security auditor có quyền đọc theo nhu cầu, không được thay audit source tùy ý.
- Chọn **append-only/WORM hoặc cơ chế tamper-evident** nếu có yêu cầu chứng cứ/tuân thủ.
- Dùng rolling và retention để không làm đầy ổ chứa **journal/paging**. Kiểm tra log shipping lag, dropped records và collector uptime.
- Hạn chế log raw message payload, thông tin khách hàng, password, truststore secret, token.
- Khi cần audit message, bật có thời hạn, có giới hạn traffic và kế hoạch tắt.
- Có alert khi audit categories chuyển `OFF`, file logging config thay đổi hoặc collector mất tín hiệu.

**Không thấy log không tự chứng minh không có thao tác.** Có thể logger bị OFF, category không phủ operation, collector lag hoặc thao tác diễn ra ngoài broker management API.

### 11.3. Cảnh báo nên tạo từ tín hiệu nào?

| Tín hiệu | Điều tra ưu tiên |
|---|---|
| Authentication failures đột biến | Sai secret sau deploy, credential stuffing, brute-force, client config |
| Authorization denied vào management | Service account cố dùng quyền admin, policy drift hoặc misuse |
| Queue pause/purge/delete ngoài change window | Change ticket, actor, business impact, incident |
| Cấp role admin, mở ACL wildcard | Review least privilege, security approval, revert khi sai |
| Audit logging bị tắt hoặc log gap | Tampering, disk full, collector outage hoặc config error |
| Broker vẫn nằm trong affected version | Patch deadline, mitigation và asset reachability |
| Restart/failover bất thường sau patch | Compatibility, store health, performance và rollback path |

Ngưỡng cảnh báo phải phù hợp workload. Auto-scaling và health checks có thể tạo connection/auth events bình thường; chỉ đếm raw events sẽ gây false positives. Hãy ghép với **actor, thời gian, change ticket, source network và baseline**.

## 12. Runbook xử lý advisory và thao tác quản trị nghi vấn

### 12.1. Khi xuất hiện advisory có khả năng ảnh hưởng

1. Lưu advisory ID, ngày công bố, affected/fixed versions và nguồn.
2. Tìm mọi broker/client tương ứng trong inventory, đối chiếu **runtime version**.
3. Xác minh protocol, management endpoint, network exposure và preconditions.
4. Phân loại rủi ro, áp dụng mitigation có thời hạn nếu chưa vá kịp.
5. Chuẩn bị patch plan, compatibility, backup/restore rehearsal và owner.
6. Test staging: authn/authz, TLS, JMS transactions, DLQ, persistence, HA, audit.
7. Rollout có canary/change window; không downgrade bừa khi store schema thay đổi.
8. Xác minh trên từng node và cập nhật inventory/ticket.
9. Giữ bằng chứng liên kết giữa patch change, log/audit và test results.

### 12.2. Khi thấy dấu hiệu thao tác quản trị trái phép

1. **Bảo toàn bằng chứng** theo runbook incident; không xóa/rotate log bằng tay.
2. Xác định broker, thời gian, thao tác, target queue/address và user thực sự.
3. Ghép broker audit với console/JMX access, identity provider, Git, deployment và OS/Kubernetes logs.
4. Kiểm tra auth context, role, session, IP/gateway nếu có và change approval.
5. Đánh giá hậu quả: queue pause/purge/delete, DLQ, message delay/loss, security ACL drift.
6. Nếu phải cô lập hoặc revoke/rotate secret, thực hiện qua incident owner để tránh khóa dịch vụ quan trọng.
7. Sửa permission/configuration hoặc patch component, kiểm thử an toàn messaging.
8. Ghi timeline, root cause, detection gaps và action items.

Không dùng thao tác **purge queue hoặc xóa journal** chỉ để làm sạch bằng chứng. Mất message và mất audit trail có thể làm sự cố nghiêm trọng hơn.

## 13. Những nhầm lẫn thường gặp

**“Đã nâng version trong pom.xml nên broker hết CVE.”**  
Không. Client dependency của app không thay đổi broker runtime. Ngược lại, nâng broker không tự cập nhật thư viện client cũ trong các service.

**“Private network có nghĩa không bị ảnh hưởng.”**  
Không. Nội bộ vẫn có risk credential compromise/lateral movement. Reachability giúp đánh giá ưu tiên và mitigation nhưng không tự biến affected version thành fixed.

**“Có file audit.log thì mọi thay đổi đều được ghi.”**  
Sai. Thay config qua GitOps/Kubernetes hoặc hệ điều hành có thể không đi qua management API. Cần audit control plane.

**“Bật audit message cho toàn hệ thống càng nhiều càng an toàn.”**  
Không nhất thiết. Overhead, disk full và PII exposure có thể tạo rủi ro mới; phải đánh giá scope và retention.

**“Rollback chỉ là đổi image tag về bản cũ.”**  
Nguy hiểm nếu journal/store, config hoặc HA state đã khác compatibility. Cần phương án được thử trước.

**“Không có security error log nghĩa là không ai thử truy cập.”**  
Không chắc. Logger/collector có thể bị tắt, filter quá chặt hoặc endpoint khác không được thu thập.

**“Chỉ cần CVSS trên ngưỡng X mới vá.”**  
Không đủ. Exploitability, exposure, credentials/roles, active exploitation và blast radius quyết định priority thực tế.

## 14. Bảng nghiệm thu kiểm soát security operations

| ID | Test | Dấu hiệu PASS |
|---|---|---|
| PATCH-01 | Inventory broker và client | Product/version runtime, digest, protocol, owner đầy đủ |
| PATCH-02 | Đối chiếu advisory thật | Affected/not affected có nguồn và lập luận rõ |
| PATCH-03 | Nâng broker staging/canary | Runtime version, TLS/authn/authz, JMS transaction/HA PASS |
| PATCH-04 | Kiểm tra rollback | Compatibility store/restore rehearsal được ghi |
| AUD-01 | Admin tạo queue lab có phép | Có audit/action evidence và change record |
| AUD-02 | User không có admin thử operation | Denied với identity/time/resource có thể truy vết |
| AUD-03 | GitOps thay config | CI/CD/Kubernetes audit lưu approver/revision |
| AUD-04 | Log rotation | Không mất log bất thường; không làm đầy volume journal |
| AUD-05 | Collector gián đoạn trong lab | Có gap/lag alert và kiểm tra recovery |
| AUD-06 | Access control log | Broker admin không được tự xóa dữ liệu SIEM |
| JMS-01 | Writer gửi `lab.security.audit` | Send/commit thành công; không lẫn admin audit |
| JMS-02 | Reader cố send | Authorization denied |
| JMS-03 | Sai password | Authentication denied |
| JMS-04 | Sau patch consumer crash | Redelivery/idempotency và dữ liệu persistent đúng |

Nghiệm thu phải dựa vào **evidence thực tế**, không chỉ có dòng “PASS” do một script tự in.

## 15. Câu hỏi tự kiểm tra

**1. Advisory chỉ nêu ActiveMQ Classic, doanh nghiệp có broker Artemis nhưng một ứng dụng dùng Classic client. Cần làm gì?**  
Đọc phạm vi component/versions của advisory, kiểm tra client artifact trong SBOM và broker từng dòng riêng. Không tự quy cùng hoặc loại trừ tất cả theo tên ActiveMQ chung.

**2. Broker đã nâng nhưng web console vẫn dùng admin chung và reachable từ mạng rộng. Đã giải quyết rủi ro chưa?**  
Chưa. Patch và hardening là hai lớp; cần least privilege, network isolation, strong auth/MFA ở gateway khi phù hợp, secret rotation và audit.

**3. Vì sao broker audit không thay thế audit Git/CI-CD?**  
Vì có thay đổi binary, ConfigMap, broker.xml, JAAS role file và TLS keystore diễn ra ngoài broker management operations.

**4. Khi nào bật message audit?**  
Khi có mục tiêu điều tra/tuân thủ rõ ràng, kiểm soát volume và dữ liệu nhạy cảm, và đã kiểm tra event nào thực sự được category ghi.

**5. Sau thay image, vì sao cần xác minh runtime từng node?**  
Rolling upgrade có thể chưa hoàn tất, instance cũ còn phục vụ, image tag mutable hoặc pod không restart thành công.

**6. Audit không có record thao tác pause queue nhưng có change trong deployment log. Có thể kết luận gì?**  
Một đường quản trị ngoài audit category hoặc gap collector có thể đã xảy ra. Cần ghép nhiều nguồn và kiểm tra coverage, chưa thể kết luận actor chính xác từ một log thiếu.

**7. Producer gửi JMS timeout có tự là dấu hiệu bị tấn công không?**  
Không. Có thể do mạng, broker overload hoặc reply mất. Điều tra performance/security context; retry dùng eventId ổn định và consumer idempotent.

**8. Vì sao không xóa local audit.log ngay khi collector dường như đang chạy?**  
Phải xác nhận ingest/retention theo quy trình; collector có thể lag hoặc thiếu acknowledgement, việc xóa phá bằng chứng.

## 16. Checklist vận hành

- [ ] Có inventory Artemis/Classic riêng, broker runtime versions, image digests, JDK, owner.
- [ ] Có danh sách ứng dụng/client JMS thực tế và SBOM/dependency tree.
- [ ] Theo dõi advisory Apache, CVE và vendor backport với owner/SLA.
- [ ] Đánh giá affected component, protocol exposure, management endpoint và role.
- [ ] Có patch/mitigation ticket, exception có hạn nếu chưa vá ngay.
- [ ] Có backup/restore rehearsal, compatibility và rollback plan.
- [ ] Staging/canary đã kiểm tra authn/authz/TLS, JMS transaction, persistence, HA.
- [ ] Artemis audit categories phù hợp phiên bản được bật và **test coverage**.
- [ ] Classic dùng log/plugin/management auditing phù hợp, không copy cấu hình Artemis.
- [ ] Có access log của console/JMX gateway và Git/CI-CD/OS/Kubernetes audit.
- [ ] Audit có timestamp UTC, broker node, actor, operation, resource, outcome theo nguồn sẵn có.
- [ ] Log được ship off-host, retention và quyền xóa/đọc được tách biệt.
- [ ] Có alert log gap, audit disabled, unauthorized admin action, ACL widening.
- [ ] Không log secret, private key hoặc payload nhạy cảm không cần thiết.
- [ ] Kiểm thử cả allowed và denied operations trên broker lab.
- [ ] Sau patch cập nhật runtime inventory và lưu test/audit evidence.
- [ ] Incident procedure bảo toàn bằng chứng trước khi khôi phục/sửa config.

## 17. Kết luận

**Theo dõi bản vá** phải đi từ inventory phiên bản **đang chạy**, advisory có nguồn, đánh giá exposure/điều kiện khai thác, staging có kiểm thử đến rollout được xác nhận. **Nhật ký quản trị** phải chứng minh có thể đối chiếu **ai làm gì trên broker nào, khi nào, kết quả gì**, không chỉ chứa lỗi ứng dụng.

Artemis hỗ trợ các audit categories theo cấu hình logging của phiên bản; Classic cần plugin/management/access audit theo cơ chế riêng. Cả hai cần **Git/CI-CD/OS/Kubernetes audit** vì nhiều thay đổi quan trọng diễn ra ngoài broker. Độ tin cậy của hệ thống messaging đòi hỏi vừa **vá đúng thành phần có rủi ro**, vừa **bảo vệ chứng cứ quản trị khỏi sửa/xóa**, trong khi vẫn giữ an toàn cho queue, transaction, journal, redelivery và DLQ trong suốt quá trình nâng cấp.


