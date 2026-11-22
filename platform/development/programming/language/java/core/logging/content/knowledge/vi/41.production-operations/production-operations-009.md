# Khôi phục cấu hình Java Logging trong production

## 1. Mục tiêu của “khôi phục cấu hình”

**Khôi phục cấu hình logging** là đưa hệ thống ghi log từ trạng thái sai, không ổn định hoặc không đáp ứng yêu cầu vận hành trở về một **trạng thái đã biết là tốt** (last-known-good configuration), đồng thời xác minh rằng log quan trọng vẫn được sinh, được chuyển tới đích và có thể tra cứu.

Trong nhóm **Vận hành production**, đây không chỉ là thao tác đổi `DEBUG` về `INFO`. Một cấu hình logging bao gồm nhiều phần cùng ảnh hưởng đến nhau:

- **Logger levels:** root level, package level, logger level, level inheritance.
- **Appender/handler:** console, rolling file, remote HTTP/TCP, Syslog hoặc OTLP.
- **Filters:** chấp nhận/từ chối log theo level, marker, message, request context.
- **Layouts/encoders:** pattern, JSON schema, timestamp, stack trace, charset.
- **Routing:** root logger, appender references, additivity, async wrappers.
- **Buffers/queues:** queue size, drop policy, flush/drain, backpressure.
- **Destinations:** file path, quyền ghi, disk quota, DNS, TLS, receiver/auth.
- **Context và bảo mật:** MDC/ThreadContext, trace ID, dữ liệu cá nhân, secret masking.
- **Lifecycle:** cấu hình lúc khởi động, file watcher, reload runtime, rollout/restart.
- **Operational controls:** config version, owner, audit trail, checksum, rollback và cảnh báo.

Vì vậy, **“đọc được XML/YAML” chưa đủ để kết luận khôi phục thành công**. Cấu hình mới có thể đúng cú pháp nhưng log đi nhầm đích, bị filter hết, không được ingest hoặc rò dữ liệu nhạy cảm.

Một luồng khôi phục điển hình:

```text
Detection: log không xuất hiện / tăng đột biến / sai đích
                 |
                 v
     Khoanh vùng phạm vi và loại lỗi
                 |
                 v
      Chọn last-known-good đã kiểm thử
                 |
                 v
   Validate + staged restore / controlled rollout
                 |
                 v
     Verify: logs, sinks, latency, privacy
                 |
           +-----+-----+
           |           |
         PASS         FAIL
           |           |
      Giữ version     Dừng rollout,
      và theo dõi     fallback an toàn
```

**Nguyên tắc:** khôi phục phải có **trạng thái đích rõ ràng, cách áp dụng xác định và bằng chứng kiểm chứng**, không chỉ sửa file rồi tin rằng framework đã tự nhận thay đổi.

## 2. Những triệu chứng cần nghĩ đến cấu hình logging

| Triệu chứng | Khả năng liên quan đến cấu hình | Dấu hiệu cần kiểm |
| --- | --- | --- |
| Không thấy log ứng dụng | Level quá cao, filter DENY, appender không được gắn | Effective level, logger name, root/appender refs |
| Có INFO nhưng mất ERROR | Filter/routing khác nhau, async drop, remote path lỗi | Appender-specific filters, status logger, queue |
| Một log xuất nhiều lần | Additivity, root + child cùng appender, dual ingest | Logger tree, appender references, shipper/OTLP |
| Log tràn disk hoặc ingest cost | DEBUG/TRACE bật rộng, stack trace, batch logging | Volume theo level/logger, rotation, sampling |
| Request latency tăng sau đổi config | Appender đồng bộ đi mạng, queue blocking, encoder đắt | Thread dump, send timeouts, queue depth |
| File không có dòng mới | Sai path/quyền, mount read-only, rotation/lock | Path resolved, OS permission, disk quota |
| Log có nhưng thiếu trace ID | MDC injection/encoder/context propagation lỗi | Active trace, MDC keys, structured output |
| JSON parser backend lỗi | Thay layout/schema, multiline, charset | Raw event từ source và parsed event tại sink |
| Startup báo parse error | XML/YAML/properties sai hoặc plugin/class không có | Internal status output và config artifact |
| Sau deploy không áp dụng level mới | Config location/precedence khác, chưa restart/reload | Active file, profile, environment, effective level |
| Sau đổi cấu hình lộ token/PII | Bỏ redaction, in body/header/MDC/SQL binds | Canary secret test và pipeline kiểm soát |
| Console có log nhưng backend không | Collector/exporter/receiver/network độc lập | Shipper offsets, retries, queue, TLS, backend query |

**Đừng mặc định mọi sự cố logging là do file cấu hình.** Collector down, dashboard query sai time range, expired certificate, node disk full, sampling hoặc application không gọi logger cũng có thể tạo triệu chứng tương tự.

## 3. Trước khi khôi phục: xác định phạm vi cấu hình đang chạy

Một ứng dụng có thể có nhiều “nguồn sự thật”:

```text
Source control (Git)
    |
    +-- packaged logback.xml / log4j2.xml / logging.properties
    |
    +-- application.yml / application.properties
    |
    +-- environment variables / JVM system properties
    |
    +-- ConfigMap / Secret / mounted files
    |
    +-- runtime API: Actuator /loggers hoặc JMX
    |
    +-- logging library defaults / auto-configuration
                 |
                 v
       Effective configuration per JVM
```

Khi có sự cố, cần xác định **effective configuration** đang chạy, không chỉ bản file nằm trong repo. Ví dụ:
- Package level được đổi qua Spring Boot Actuator, nhưng Git vẫn ở `INFO`.
- Container dùng `logging.config=/etc/app/logback-spring.xml`, không dùng `logback-spring.xml` đóng gói.
- Log4j 2 nạp config từ một vị trí khác qua system property.
- Một pod được restart, pod khác vẫn chạy cấu hình cũ.
- ConfigMap đã thay đổi, nhưng process chỉ đọc tại startup.
- File watcher gặp lỗi parser nên giữ hoặc khôi phục state cũ theo behavior của framework.

### 3.1. Thông tin tối thiểu cần ghi nhận

Trước khi chỉnh cấu hình, thu thập metadata **không chứa secret**:
- Tên service, môi trường, instance/pod, version ứng dụng và logging backend.
- Version/digest của cấu hình đã triển khai; commit hoặc artifact ID.
- Đường dẫn/nguồn thực sự được nạp và profile hiện tại.
- Thời điểm bắt đầu lỗi, thời điểm deploy/change gần nhất.
- Level hiệu lực của logger bị ảnh hưởng và root level.
- Appender names, đích sink logical name, queue policy.
- Vị trí xảy ra lỗi: ngay trong JVM, file/stdout, shipper, Collector hay backend.
- Logs/metrics của logging infrastructure trên **kênh độc lập** còn hoạt động.

Không in raw config nếu nó có password, API key, auth header hoặc TLS keystore secret. Dùng checksum/digest versioned và bản đã redacted để đối chiếu.

## 4. Last-known-good không chỉ là “file trước đó”

Một baseline tốt nên là một **bộ cấu hình được định danh và đã kiểm thử**, gồm:
1. File XML/properties/YAML và mọi file được include.
2. Version framework và encoder/plugin dependencies tương ứng.
3. Tên logger, appender, filter và đường routing đã được chấp nhận.
4. Các biến cấu hình bắt buộc, nhưng **không chép secret nguyên giá trị** vào backup public.
5. Đường dẫn/mount/destination assumptions và khả năng đọc/ghi.
6. Kết quả kiểm thử canary log, expected levels và privacy.
7. Hash hoặc release ID để chứng minh bản đã áp dụng.

Một bản config “hôm qua chạy tốt” có thể **không tương thích** với application version mới nếu plugin/appender đổi class name hoặc runtime đã nâng Java/Logback/Log4j 2. Vì thế phải gắn **config version với application/library version** và kiểm tra compatibility trước rollback.

Ví dụ metadata triển khai:

```yaml
logging_configuration:
  version: "logging-v12"
  git_revision: "example-commit-123"
  compatible_service_release: "orders-2026.11"
  backend: "logback"
  root_level: "INFO"
  required_sinks: ["stdout", "central-logs"]
  rollback_target: "logging-v11"
  validation: ["startup", "canary", "error-event", "sensitive-data"]
```

Đây là schema minh họa của một deployment manifest, **không phải cấu hình chuẩn để Logback trực tiếp đọc**. Nó giúp đội vận hành truy vết việc rollback đã chọn đúng bundle hay chưa.

## 5. Runbook khôi phục an toàn trong production

### Bước 1 — Ổn định tình huống

Khi mất log hoặc log storm:
- Xác định lỗi có ảnh hưởng **security/audit events bắt buộc** hay chỉ DEBUG/INFO.
- Nếu log level quá chi tiết gây nghẽn, ưu tiên hạ level theo **cơ chế runtime được cấp quyền** hoặc rollback rollout có kiểm soát.
- Nếu remote destination lỗi làm blocking request, cần giảm coupling theo policy đã phê duyệt, không xóa tất cả ERROR logging.
- Duy trì **kênh chẩn đoán tối thiểu** như stderr/container console/health metrics nếu còn hoạt động.
- Lưu lại mốc thời gian và config version; không tạo thêm log chứa credential trong lúc debug.

### Bước 2 — Khoanh vùng và thu bằng chứng

Trả lời: service nào, tất cả pod hay chỉ một pod, từ khi nào, sink nào thiếu, có config rollout nào trùng thời điểm? Quan sát source event count, appender errors, Collector queue/export metrics và backend query.

### Bước 3 — Chọn rollback target

Lấy **last-known-good đã xác minh từ Git/immutable artifact hoặc config registry**. Không “chọn file .bak mới nhất” theo thời gian sửa nếu không biết nó tương ứng với deploy nào. Kiểm tra dependency, schema, đường dẫn, quyền, secret reference và routing trước khi kích hoạt.

### Bước 4 — Validate trước khi apply

Kiểm tra ít nhất:
- XML/JSON/YAML/properties syntactically parse được.
- Appender class/plugin có mặt, layout/encoder property được hỗ trợ.
- Không tham chiếu appender chưa khai báo; không có filter vô tình DENY mọi event.
- File path/mount/permission đúng; network/TLS destination hợp lệ.
- Root/package levels và additivity đúng mục tiêu.
- Kênh WARN/ERROR/audit bắt buộc không bị tắt.
- Không đưa raw secret, request body, Authorization hoặc SQL bind values vào log.
- Không tạo duplicate giữa console/file/OTLP/shipper.
- Chính sách queue/retry/blocking phù hợp service SLO.

**Parser validation không chứng minh network endpoint đang sống hoặc backend đã lưu event.** Cần test hành vi sau apply.

### Bước 5 — Apply theo cơ chế cụ thể

Chọn một trong:
- **Redeploy/restart** với version đã pin: đáng tin cậy nhất khi config chỉ được đọc lúc khởi động hoặc thay đổi lớn.
- **File-based automatic reload** nếu backend hỗ trợ và đã kiểm thử toàn bộ lifecycle.
- **Runtime level override** cho tình huống khẩn cấp hẹp, ví dụ Spring Boot Actuator `/loggers`.
- **Programmatic update** cho một số hệ thống JUL/custom configuration, nhưng cần hiểu handler lifecycle.

Không áp đồng thời nhiều nguồn mới (Git, environment, runtime API) rồi mất khả năng biết cái nào thắng. Nếu rollback nhiều pod, dùng canary/rolling strategy và giữ đường quay về bản đang chạy.

### Bước 6 — Xác minh bằng event canary

Phát một event tổng hợp có mã định danh an toàn, chẳng hạn:

```text
INFO event=logging.config_verified config_version=logging-v11
     verification_id=verify-20261110-01 service=orders
```

Kiểm tra nó ở:
1. Logger/appender source (nếu có local sink).
2. File/stdout hoặc remote receiver.
3. Collector/shipper ingestion.
4. Backend search/dashboard theo đúng service, environment, time range.
5. Đúng số bản ghi dự kiến, đúng JSON schema, timestamp, level và trace metadata.
6. Không chứa bất kỳ synthetic password/token canary nào.

**Một event thành công chưa chứng minh mọi logger/level đều hoạt động.** Thêm test WARN/ERROR, kiểm tra filters và các đường logging quan trọng khác.

### Bước 7 — Xác minh vận hành

Trong khoảng theo dõi sau rollback:
- Log rate theo level và logger category trở về baseline?
- Appender error/drop/retry/queue depth giảm?
- Error events có tới sink dự kiến không?
- HTTP latency, CPU, GC, disk/network có cải thiện?
- Có duplicate log do additivity hay multi-ingest không?
- Collector/backend ingest delay có trở lại mức chấp nhận không?
- Có rò PII/token trong output đã parse hay không?

### Bước 8 — Chốt hoặc dừng rollout

Chỉ coi rollback hoàn tất nếu version mới **thực sự active** và các tiêu chí verify đạt. Nếu không đạt, dừng rollout, đưa ứng dụng vào fallback operational mode theo quy trình đã duyệt hoặc rollback ứng dụng/config cùng nhau. Ghi incident timeline, người phê duyệt, phạm vi thay đổi và kết quả.

## 6. Logback: cách reload, fallback và giới hạn cần nhớ

Logback Classic hỗ trợ cấu hình XML, thường nằm ở `logback.xml` hoặc đường dẫn cấu hình được chỉ định. Ví dụ local:

```xml
<configuration scan="true" scanPeriod="30 seconds">
    <appender name="CONSOLE"
              class="ch.qos.logback.core.ConsoleAppender">
        <encoder>
            <pattern>%d{ISO8601} %-5level [%thread] %logger - %msg%n</pattern>
        </encoder>
    </appender>

    <logger name="com.example.repository" level="WARN"/>

    <root level="INFO">
        <appender-ref ref="CONSOLE"/>
    </root>
</configuration>
```

Giải thích:
- `scan="true"` yêu cầu Logback theo dõi thay đổi cấu hình file.
- `scanPeriod="30 seconds"` định nghĩa khoảng kiểm tra; **có đơn vị** để tránh hiểu nhầm.
- `root level="INFO"` là ngưỡng gốc, repository logger có override WARN.
- `CONSOLE` cho một đường local giúp giữ tín hiệu khi remote sink gặp lỗi.

Khi file được thay đổi và watcher hỗ trợ, Logback có thể reconfigure. **Tài liệu Logback nêu rằng với cấu hình mới có lỗi cú pháp XML, nó có thể quay về một cấu hình trước đó hợp lệ về cú pháp**. Nhưng giới hạn quan trọng:
- Cơ chế đó **không bảo đảm** fallback khi XML hoàn toàn hợp lệ nhưng log bị filter hết, file path sai, plugin không có hoặc remote endpoint không nhận.
- Không giả định các thay đổi luôn được phát hiện tức thì; phụ thuộc scan interval và loại file.
- Không tự cho rằng every external URL/mounted source đều được watch giống file.
- Khi thay appender, có thể có thay đổi lifecycle/queue; verify actual event output và status diagnostics.
- Auto reload là **một cơ chế cấu hình**, không phải bộ điều phối change management/rollback cho production.

### 6.1. Không edit trực tiếp file active từng ký tự

Nếu file watcher đang hoạt động, việc ghi file theo nhiều lần write có thể khiến watcher nhìn thấy **file trung gian chưa hoàn chỉnh**. Quy trình safer:
1. Tạo file candidate riêng ở cùng filesystem/mount được kiểm soát.
2. Parse, review và test candidate ngoài production hoặc trên canary.
3. Triển khai file hoàn chỉnh theo cơ chế atomically replace phù hợp platform, hoặc đổi immutable config artifact rồi restart/roll.
4. Ghi version/digest, theo dõi reconfigure status.
5. Phát canary log và verify.

Không mọi storage/mount đều hỗ trợ atomic replace theo cùng semantics; với Kubernetes ConfigMap hay container immutable filesystem, **rollout/restart thường dễ kiểm soát hơn**.

### 6.2. Spring Boot với Logback: một ngoại lệ đặc biệt

Spring Boot hỗ trợ các extension trong `logback-spring.xml` như `<springProfile>` và `<springProperty>`. Tài liệu Spring Boot cảnh báo **các extension này không tương thích với cơ chế Logback configuration scanning**.

Đây là cấu hình minh họa đúng hướng khi dùng Boot extensions (không bật scan):

```xml
<configuration>
    <springProfile name="prod">
        <appender name="CONSOLE"
                  class="ch.qos.logback.core.ConsoleAppender">
            <encoder>
                <pattern>%d{ISO8601} %-5level %logger - %msg%n</pattern>
            </encoder>
        </appender>
        <root level="INFO">
            <appender-ref ref="CONSOLE"/>
        </root>
    </springProfile>
</configuration>
```

File minh họa này cần được đặt vào **`logback-spring.xml`** trong một dự án Spring Boot/Logback hỗ trợ extension, không phải file `logback.xml` thông thường. Khi cần khôi phục một cấu hình có `<springProfile>`/`<springProperty>`, ưu tiên deploy/restart đúng version hoặc cơ chế Spring Boot được hỗ trợ; **không thêm `scan="true"` như cách sửa nóng**.

Khi lỗi `no applicable action for [springProfile]` hoặc `[springProperty]` xuất hiện sau khi bật scanning, kiểm tra tính tương thích của configuration lifecycle trước khi thay XML.

## 7. Log4j 2: monitorInterval và reconfiguration

Với Apache Log4j 2 Core, một cấu hình file có thể bật polling:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<Configuration monitorInterval="30">
    <Appenders>
        <Console name="CONSOLE" target="SYSTEM_ERR">
            <PatternLayout
                pattern="%d{ISO8601} %-5p %c - %m%n"/>
        </Console>
    </Appenders>

    <Loggers>
        <Logger name="com.example.repository"
                level="warn" additivity="true"/>
        <Root level="info">
            <AppenderRef ref="CONSOLE"/>
        </Root>
    </Loggers>
</Configuration>
```

`monitorInterval="30"` là số **giây** giữa các lần poll theo tài liệu Log4j 2; `0` là tắt. Thay file config mà framework đã load và watcher nhận diện sẽ kích hoạt reconfiguration.

Lưu ý:
- Watcher chỉ hoạt động cho **nguồn/cấu hình được Log4j hỗ trợ**; file nằm trong JAR/classpath hoặc remote source có thể không reconfigure như file thực trên filesystem.
- Log4j 2 cố giảm mất log khi reconfigure, có thể tái sử dụng appender resources và bỏ qua vài thay đổi option gây nguy cơ log loss; **không có bảo đảm zero-loss end-to-end qua network/backend**.
- Cấu hình hợp lệ cú pháp vẫn có thể tạo routing sai hoặc drop log; phải verify source/sink.
- Nếu dùng async loggers/appenders, hiểu queue và shutdown, không coi việc config “đã nạp” là queue đã drain.
- Các thông báo internal errors được ghi qua **Status Logger**; trên Log4j 2 mới, cấu hình level chẩn đoán có thể dùng system property `log4j2.statusLoggerLevel`. Không bật TRACE nội bộ lâu dài trên production.

### 7.1. Cẩn thận với additivity

Một logger cụ thể và root cùng gắn appender có thể khiến một event xuất nhiều lần nếu additivity được bật. Trong ví dụ trên, `com.example.repository` **không** gắn riêng appender nên event đi lên root là hợp lý.

Nếu muốn tách file cho repository, cần quyết định:
- Có để event đi lên root console không?
- Có gắn cùng appender vào cả parent và child không?
- `additivity=false` có vô tình làm log mất khỏi central pipeline không?

Việc rollback một level nhưng bỏ sót additivity hoặc appender refs không được coi là khôi phục hoàn chỉnh.

## 8. Java Util Logging (JUL): tránh reset toàn hệ thống tùy tiện

JUL trong JDK dùng `java.util.logging.Logger`, `Handler`, `Filter` và `LogManager`. Có thể chỉ định cấu hình lúc khởi động bằng JVM property:

```bash
java -Djava.util.logging.config.file=/path/to/logging.properties \
     -jar application.jar
```

Đây là ví dụ **Bash**: cần đường dẫn file có thật và JAR. Trên Windows PowerShell/cmd cách xuống dòng và quoting khác; không copy ký tự `\` của Bash nguyên văn sang shell khác.

Một cấu hình `logging.properties` minh họa:

```properties
handlers=java.util.logging.ConsoleHandler
.level=INFO
java.util.logging.ConsoleHandler.level=ALL
java.util.logging.ConsoleHandler.formatter=java.util.logging.SimpleFormatter
com.example.repository.level=WARNING
```

Nếu phải khôi phục, ưu tiên restore file đã kiểm tra rồi restart theo cách vận hành có kiểm soát, hoặc dùng API update phù hợp.

### 8.1. Vì sao `LogManager.reset()` có rủi ro?

Theo tài liệu JDK 17, `LogManager.reset()`:
- Loại bỏ và đóng các `Handler` trên những logger được quản lý.
- Đặt logger levels về trạng thái mặc định/inherit theo quy tắc JUL.
- Xóa các properties đang giữ trong LogManager.

Vì vậy gọi:

```java
LogManager.getLogManager().reset();
```

**Không phải là “khôi phục mặc định an toàn” cho mọi service.** Nó có thể làm file/network handlers bị đóng và log biến mất nếu chưa khởi tạo lại đúng. Nếu phải quản lý JUL runtime, xem API `LogManager.updateConfiguration(...)` (JDK 9+) và lifecycle handler, nhưng đừng giả định update mọi handler property in place: có thay đổi chỉ áp lên handler được tạo mới.

`readConfiguration(InputStream)` trên một ứng dụng đã khởi tạo logger có thể **reset các logger hiện tại**, theo API note của JDK 17; không gọi nó trong đường request đang chạy mà thiếu kế hoạch/kiểm thử.

## 9. Spring Boot Actuator: đổi logger level runtime nhưng không thay config artifact

Spring Boot Actuator hỗ trợ endpoint `/actuator/loggers` để xem/cập nhật logger level hiệu lực khi đã được enable/expose và cấp quyền phù hợp.

Ví dụ đọc (endpoint nội bộ được bảo vệ, cú pháp shell minh họa):

```bash
curl --fail --silent \
  "http://127.0.0.1:8080/actuator/loggers/com.example.repository"
```

Ví dụ thay logger level tạm thời:

```bash
curl --fail --silent --show-error \
  -X POST \
  -H "Content-Type: application/json" \
  -d '{"configuredLevel":"WARN"}' \
  "http://127.0.0.1:8080/actuator/loggers/com.example.repository"
```

Reset override của logger về việc kế thừa/default:

```bash
curl --fail --silent --show-error \
  -X POST \
  -H "Content-Type: application/json" \
  -d '{"configuredLevel":null}' \
  "http://127.0.0.1:8080/actuator/loggers/com.example.repository"
```

**Phân biệt rõ:** `configuredLevel:null` nghĩa là **xóa mức được cấu hình cụ thể cho logger** để dùng lại default/inherited level. Nó **không đồng nghĩa** khôi phục toàn bộ file cấu hình trước đó, appender, filter hoặc layout.

Lưu ý vận hành:
- Endpoint này có thể bị tắt/không expose mặc định. Cần cấu hình và bảo vệ theo security policy.
- Thay đổi là **trạng thái runtime**, thường không tự cập nhật Git, YAML hay config artifact; khi process restart có thể trở lại cấu hình khởi động.
- Với nhiều pod, gọi endpoint của một pod chỉ ảnh hưởng pod đó. Cần kiểm tra rollout toàn cụm.
- Không expose write endpoint công khai Internet; dùng authentication/authorization, network restriction, audit trail.
- Nếu cần khôi phục sau một thay đổi DEBUG khẩn cấp, nhớ reset runtime override **và** xác nhận bản config source vẫn đúng; tránh để override âm thầm làm khác giữa pods.

**Không coi Actuator /loggers là công cụ rollback mọi loại logging config.** Nó hữu ích nhất khi cần thay đổi **logger levels** nhanh và có kiểm soát.

## 10. Java 17 runnable: validate candidate trước, giữ last-known-good và rollback

Ví dụ này **chỉ dùng JDK 17**. Nó mô phỏng một config registry nhỏ gồm `version` và `level`, phân biệt ba thao tác:

1. Apply baseline `v1` với INFO.
2. Apply candidate `v2` với FINE.
3. Reject cấu hình `v3` có level không hợp lệ **trước khi thay đổi logger**, rồi rollback chủ động về `v1`.

Vì muốn stdout xác định, chương trình dùng một custom `Handler` trong bộ nhớ; không ghi timestamp/stack trace và không phụ thuộc tốc độ máy. Đây **không phải một trình reload XML/Logback/Log4j 2 production**; nó mô tả thiết kế *stage → validate → apply → rollback* ở phạm vi **một logger level**.

Lưu file `LoggingConfigRecoveryDemo.java`:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public final class LoggingConfigRecoveryDemo {
    private record Config(String version, Level level) { }

    private static final class CaptureHandler extends Handler {
        private final List<String> events = new ArrayList<>();

        @Override
        public void publish(LogRecord record) {
            if (isLoggable(record)) {
                events.add(record.getLevel().getName()
                        + " " + record.getMessage());
            }
        }

        @Override public void flush() { }
        @Override public void close() { }

        List<String> events() {
            return List.copyOf(events);
        }
    }

    private static Config parseConfig(String text) {
        String[] lines = text.split("\\n", -1);
        if (lines.length != 2
                || !lines[0].startsWith("version=")
                || !lines[1].startsWith("level=")) {
            throw new IllegalArgumentException("INVALID_FORMAT");
        }

        String version = lines[0].substring("version=".length());
        String levelText = lines[1].substring("level=".length());
        if (!version.matches("v[0-9]+")) {
            throw new IllegalArgumentException("INVALID_VERSION");
        }

        Level level = switch (levelText) {
            case "INFO" -> Level.INFO;
            case "FINE" -> Level.FINE;
            case "WARNING" -> Level.WARNING;
            default -> throw new IllegalArgumentException("INVALID_LEVEL");
        };
        return new Config(version, level);
    }

    private static void apply(Logger logger, Config config) {
        logger.setLevel(config.level());
    }

    public static void main(String[] args) {
        Logger logger = Logger.getLogger("demo.config.recovery");
        CaptureHandler capture = new CaptureHandler();
        capture.setLevel(Level.ALL);
        logger.setUseParentHandlers(false);
        logger.setLevel(Level.ALL);
        logger.addHandler(capture);

        try {
            Config lastKnownGood =
                    parseConfig("version=v1\nlevel=INFO");
            apply(logger, lastKnownGood);
            logger.info("event=service.started config_version=v1");

            Config candidate =
                    parseConfig("version=v2\nlevel=FINE");
            apply(logger, candidate);
            logger.fine("event=diagnostics.enabled config_version=v2");

            try {
                Config invalid =
                        parseConfig("version=v3\nlevel=BOGUS");
                apply(logger, invalid);
            } catch (IllegalArgumentException ex) {
                logger.warning("event=config.rejected "
                        + "candidate=v3 reason=INVALID_LEVEL");
            }

            apply(logger, lastKnownGood);
            logger.info("event=config.rollback restored_version=v1");
            logger.fine("event=debug.after_rollback");
            logger.info("event=service.ready config_version=v1");

            for (String event : capture.events()) {
                System.out.println(event);
            }
        } finally {
            logger.removeHandler(capture);
            capture.close();
        }
    }
}
```

Biên dịch, chạy:

```bash
javac --release 17 LoggingConfigRecoveryDemo.java
java LoggingConfigRecoveryDemo
```

Stdout **chính xác**:

```text
INFO event=service.started config_version=v1
FINE event=diagnostics.enabled config_version=v2
WARNING event=config.rejected candidate=v3 reason=INVALID_LEVEL
INFO event=config.rollback restored_version=v1
INFO event=service.ready config_version=v1
```

Giải thích:
- `parseConfig` là bước **validation trước khi apply**: chỉ chấp nhận level trong danh sách và version đúng quy ước.
- Khi `v3` có `BOGUS`, parse ném exception và không gọi `setLevel`; logger vẫn đang ở FINE khi log WARNING.
- `apply(logger, lastKnownGood)` chủ động phục hồi INFO. Sau đó event `FINE event=debug.after_rollback` **không xuất hiện** vì logger đã ở INFO.
- `CaptureHandler` chấp nhận ALL, do đó lọc FINE lúc rollback là từ **logger level**, không phải handler level.
- `setUseParentHandlers(false)` tránh root logger in thêm timestamp hoặc duplicate output.
- Bộ config gồm một level duy nhất nên apply đơn giản; cấu hình production với nhiều appenders, filters, network destinations và threads **không phải một transaction nguyên tử** chỉ nhờ gọi vài setter.
- Không đọc file ngoài, không cần Spring/Logback dependencies, không có network; vì vậy ví dụ là bài thực hành logic recovery, không phải proof rằng một backend log đã lưu event.

**Điểm học được:** cần có cấu hình tốt đã định danh, bước validation tách khỏi apply, cách rollback chủ động và test đầu ra thực. Với runtime configuration lớn, nên versioned redeploy thay vì tự đổi từng property bằng code ứng dụng.

## 11. Kiểm tra hiệu lực logger level, appender và filter

Một nguyên nhân rất thường gặp khiến rollback thất bại: “root đã INFO” nhưng không thấy INFO. Level chỉ là một trong các điều kiện cần.

Luồng đơn giản hóa:

```text
logger.isEnabledFor(level)?
         |
         v
Logger filters / hierarchy
         |
         v
Appender reference(s) / additivity
         |
         v
Appender filter (ACCEPT, DENY, NEUTRAL)
         |
         v
Encoder/layout -> stdout/file/network
         |
         v
Collector -> backend
```

Cần xét:
- Logger cụ thể có `level=ERROR` ghi đè root INFO?
- Appender có `ThresholdFilter` loại INFO?
- AsyncAppender/queue có discard policy và đang drop?
- Logger con có `additivity=false` nhưng không gắn appender?
- Filter theo message/marker có deny nhầm?
- Có wrapper root/child cùng appender gây duplicate?
- Remote appender destination hoặc certificate đã thay đổi?
- JSON encoder dùng key khác khiến backend parser bỏ record?

Ví dụ **Logback**:

```xml
<logger name="com.example.payment" level="INFO"/>
<root level="INFO">
    <appender-ref ref="CONSOLE"/>
</root>
```

Đây chỉ là fragment. Nếu `com.example.payment` đã bị gắn `additivity="false"` mà không có appender-ref nào, log có thể biến mất dù logger level INFO.

Không chỉ kiểm tra “đã nạp file đúng”: phát canary ở **ít nhất INFO, WARN, ERROR**, kiểm tra sink và schema của từng đường. Với privacy, cũng cần chắc chắn không có filter/redaction bị gỡ.

## 12. Khôi phục appender và pipeline vận chuyển

Rollback config có thể thay đổi tuyến log:

```text
JVM Logger
  |---- ConsoleAppender -> container stdout -> shipper
  |---- FileAppender -> rolling file -> filelog receiver
  |---- RemoteAppender -> OTLP/TCP/HTTP -> Collector
                                       |
                                       v
                                  Log backend
```

Mỗi chặng có failure mode riêng. Có log tại stdout nhưng backend không thấy không chứng minh lỗi logger-level. Lần lượt kiểm tra:
1. Logger có tạo event và appender được tham chiếu không?
2. Appender có ghi bytes/record thành công vào local sink không?
3. File path và rotation có hợp lệ không?
4. Shipper có đọc đúng file/pod/node/offset không?
5. OTLP endpoint/port/protocol/TLS/auth có đúng không?
6. Collector `logs` pipeline có receiver/processors/exporters đã active không?
7. Collector exporter queue, retries và drop counters có bình thường?
8. Backend parser, index/retention, time range, tenant có đúng?
9. Có duplicate nếu ingest đồng thời stdout và OTLP?
10. Cấu hình mới có làm thay `service.name` hoặc timestamp format khiến dashboard không match?

### 12.1. TCP/HTTP ACK không bảo đảm backend durable

Một TCP write thành công không chứng minh receiver đã persist; một HTTP 2xx/OTLP success chỉ mang ý nghĩa **theo contract của ingest endpoint**. Collector còn có queue, batching, retry và downstream exporter. Khi recovery remote appender, chỉ kiểm tra “connected” là thiếu: phải **tra được canary event ở backend** trong khoảng thời gian hợp lý.

### 12.2. AsyncAppender: rollback phải xét queue và shutdown

Nếu appender gửi network synchronously, thay config có thể giảm chi phí log nhưng vẫn đang có in-flight I/O/queues. Nếu async queue đầy, event có thể bị block/drop theo policy. Khi rollout/restart:
- Biết queue capacity và current depth.
- Cho grace period đủ để drain theo yêu cầu vận hành.
- Kiểm tra dropped/retry counters.
- Không cho rằng SIGKILL/crash sẽ gọi shutdown hook.
- Khi audit bắt buộc zero-loss, dùng durable audit/outbox thay vì chỉ appender async in-memory.

## 13. Kubernetes và GitOps: triển khai rollback ở quy mô nhiều pod

Với ứng dụng Java triển khai bằng Kubernetes, cấu hình logging thường đến từ:
- File đóng gói trong image.
- ConfigMap được mount thành file.
- Environment variables hoặc JVM system properties.
- Helm/Kustomize overlays và GitOps deployment manifest.
- External configuration service/secret manager.

**Thay ConfigMap không bảo đảm Java process tự reload.** Khả năng reload phụ thuộc file watcher của framework, cách mount và lifecycle. Environment variables đã được truyền khi process start **không tự thay đổi trong JVM** khi ConfigMap được sửa. Volume dùng `subPath` thường không nhận các cập nhật ConfigMap qua cơ chế projected volume như mount thông thường.

Một quy trình an toàn:
1. Pin version/digest config với release.
2. Deploy một canary pod với logging bundle đã kiểm thử.
3. Kiểm tra startup status, INFO/WARN/ERROR canary, remote ingest, privacy và performance.
4. Rolling update theo readiness/availability constraints.
5. Theo dõi mỗi pod báo active config version như thế nào.
6. Dừng rollout khi loss/duplicate/leak/latency vượt ngưỡng.
7. Nếu rollback, trở về exact artifact/version trước đó, không dựa vào file đã sửa tay không audit.

Đừng restart tất cả pod cùng lúc chỉ vì một logger level sai nếu thay đổi hẹp qua actuator có thể xử lý tạm; nhưng cũng đừng giữ runtime override lâu dài khiến cluster drift khỏi Git.

### 13.1. Audit thay đổi và phân quyền

Cần record người đề xuất/phê duyệt, diff config redacted, thời gian apply, pod/version bị ảnh hưởng, kết quả test và rollback target. Chỉ cho phép người được cấp quyền chỉnh logging production. Một cấu hình logging có thể chứa remote endpoint, auth reference, regex redaction và output path: thay đổi thiếu kiểm soát có thể gây mất log hoặc rò bí mật.

## 14. Phát hiện “khôi phục chưa thật sự thành công”

Một số log pipeline có thể im lặng khi lỗi. Vì vậy nên có **health/metrics độc lập**:

| Tín hiệu | Vì sao quan trọng |
| --- | --- |
| Log records emitted by level | Có phát event từ JVM không? |
| Appender failures/status logger | Cấu hình class/path/connection có lỗi không? |
| Queue depth/capacity | Ingest có nghẽn và nguy cơ drop không? |
| Dropped event counter | Quan sát log loss thay vì chỉ nhìn log không tới |
| Collector exporter queue/retry | Đường vận chuyển có phục hồi không? |
| Source-to-backend canary delay | Mất bao lâu để một event đến nơi có thể query? |
| Duplicate ratio / event IDs | Có ingest từ hai tuyến không? |
| Application request latency | Async/sync appender có làm chậm workload không? |
| Disk usage/rotation | Rolling files có chiếm hết disk không? |
| Security/PII canary test | Redaction/schema có vô tình bị thay không? |

Các tên trên là **loại metric gợi ý**, không phải tên API mặc định của mọi logging framework. Dùng metric/health thực sự mà Logback, Log4j 2, Collector và hạ tầng cung cấp.

### 14.1. Canary event nên có gì?

Một event kiểm tra được thiết kế để:
- Nhìn ra version config (một field an toàn).
- Có một ID tổng hợp duy nhất cho lần verify.
- Được phát ở log level chắc chắn nằm trong policy.
- Không mang credential/PII.
- Có nguồn service và môi trường rõ.
- Dễ search theo event code và time range.
- Không chiếm dụng luồng audit bảo mật như một transaction thật.

Thí dụ:

```json
{
  "event": "logging.config_verified",
  "config.version": "logging-v11",
  "verification_id": "verify-demo-01",
  "service.name": "orders-service",
  "severity": "INFO"
}
```

Đây là schema minh họa. Không yêu cầu mọi ứng dụng dùng chính xác key này; quan trọng là **một tiêu chí kiểm chứng end-to-end đã thống nhất**.

## 15. Bảo mật và quyền riêng tư khi rollback logging

Một rollback không được phép “chữa mất log” bằng cách bật full request logging chứa secret. Các rủi ro:
- Bật `TRACE` ở Hibernate bind parameters, làm lộ email/token/PII.
- Dump `Authorization`, `Cookie`, request/response body.
- Đưa access token vào MDC hoặc span baggage.
- Thay JSON encoder làm lộ nested fields mà allowlist cũ đã chặn.
- Bỏ regex redaction/filter quan trọng khi chuyển về config cũ.
- Chuyển log từ TLS endpoint sang plain TCP/HTTP để “fix nhanh”.
- Dùng debug exporter ở Collector trên production để xem payload thật.
- Lộ password trong file path, URL, status error hoặc exception message.

Một **last-known-good** về availability có thể **không còn đáp ứng security policy hiện tại**. Phải kiểm tra privacy requirements trước khi apply bản cũ. Nếu buộc phải tạm giảm chi tiết log, cần giữ những security events bắt buộc theo policy.

Các secret reference (ví dụ key alias hoặc mounted secret path) cũng cần được kiểm tra: config cũ có thể trỏ tới certificate đã hết hạn hoặc credential đã rotate. Không rollback secret giá trị cũ chỉ để theo kịp file logging.

## 16. Các tình huống rollback điển hình

### 16.1. Bật DEBUG quá rộng khiến log storm

**Triệu chứng:** ingest cost tăng, disk đầy, request latency xấu. **Khôi phục:** hạ package/root level bằng runtime override được kiểm soát hoặc redeploy known-good. **Verify:** log rate, disk, Collector queue, request p95 và INFO/WARN/ERROR canary. **Không làm:** disable toàn bộ logs hoặc drop lỗi bảo mật.

### 16.2. Chuyển XML mới khiến app không startup

**Triệu chứng:** Logback/Log4j 2 parser/plugin exception. **Khôi phục:** restore version hợp lệ từ artifact; với Logback scanning, biết rõ fallback cú pháp có thể xảy ra nhưng không dựa vào nó để cứu startup. **Verify:** startup log và active config, các sink thực nhận.

### 16.3. Log xuất ở console nhưng không có ở hệ thống tập trung

**Triệu chứng:** logger vẫn hoạt động; receiver/exporter/cert hoặc Collector pipeline lỗi. **Khôi phục:** kiểm tra remote appender, OTLP endpoint, TLS, queue, filelog receiver, credentials. Có thể không cần rollback entire logging config nếu sự cố nằm ở backend. **Verify:** canary query ở backend.

### 16.4. JSON layout đổi làm mất trace correlation

**Triệu chứng:** source có event nhưng backend không map trace/span ID. **Khôi phục:** dùng schema encoder tương thích, kiểm tra MDC injection và parser. **Verify:** một request có active span, log được gắn trace ID và tìm thấy trace nếu sampling/retention cho phép.

### 16.5. Rollback làm tăng duplicate

**Triệu chứng:** một event có hai record trong cùng index. **Kiểm tra:** root+child appender, stdout shipper đồng thời OTLP direct, retry/duplicate transport. **Khôi phục:** xác định một source path per logical event và kiểm tra additivity, nhưng không xóa một tuyến quan trọng khi chưa biết retention/consumers khác.

### 16.6. Runtime logger level không đồng nhất giữa pods

**Triệu chứng:** pod A DEBUG, pod B INFO sau hotfix. **Khôi phục:** xem runtime overrides từng pod, reset về inherited/default, hoặc redeploy cấu hình chuẩn đã pin. **Verify:** effective level và canary trên nhiều pod. **Không làm:** chỉ sửa Git rồi cho rằng mọi process đang chạy sẽ tự đổi.

## 17. Ma trận kiểm thử sau khôi phục

| Test | Hành động | Kết quả mong đợi |
| --- | --- | --- |
| Cấu hình parse được | Start process bằng candidate | Không có lỗi parser/plugin |
| Active config version | Query metadata/status của process | Đúng version/hash được pin |
| INFO event | Phát synthetic INFO | Xuất ở các sink cần theo policy |
| WARN/ERROR event | Phát synthetic WARN và ERROR | Không bị filter hoặc drop nhầm |
| Package override | Phát DEBUG ở package cụ thể | Effective level đúng, không rộng quá |
| Appender additivity | Một event qua logger con | Số bản ghi đúng mong đợi |
| File appender | Ghi rồi rotate trong lab | Path/perms/quota đúng, không bị cắt bất thường |
| Remote appender | Gửi event tới receiver | Có ingest theo schema, time range phù hợp |
| TLS certificate change | Dùng cert đúng/sai trong lab | Verify hostname/trust, không silent downgrade |
| Collector outage | Tắt receiver trong thử nghiệm | Bounded queue/retry/drop theo policy, app SLO phù hợp |
| Async shutdown | Graceful stop | Drain/flush theo hợp đồng và timeout |
| JVM crash | Kill có kiểm soát trong lab | Hiểu rõ log-loss window, không giả zero-loss |
| Logging privacy | Phát synthetic token canary | Không lộ raw secret ở bất cứ sink nào |
| Trace correlation | Phát log trong active span | Trace/span fields hiện khi instrumented |
| Multi-pod | Rolling canary/rest | Không có pod drift ngoài ý muốn |
| Restart | Start lại bằng same artifact | Runtime level không bất ngờ khác baseline |
| ERROR dispatch | Có exception HTTP/DB | Error summary có outcome đúng |
| Performance | Benchmark workload tương đương | Latency/CPU/log volume ở mức chấp nhận |
| Backend query | Tìm `verification_id` | Có record đúng time/resource và không duplicate |
| Revert again | Test đường rollback trong staging | Khôi phục được last-known-good khác nếu cần |

Test nên dùng **synthetic data**, không phát token production vào log. Không nhất thiết mọi test chạy trên production; unit/integration/staging kiểm tra cơ chế trước, production canary xác minh các điểm cần thiết mà không gây gián đoạn.

## 18. Những sai lầm phổ biến

**Sai lầm 1 — chỉ đổi file, không biết ứng dụng đã reload chưa:** effective state có thể vẫn là bản cũ. Kiểm tra version và event output.

**Sai lầm 2 — nhầm parser success với operational success:** XML đúng cú pháp không chứng minh log tới backend.

**Sai lầm 3 — bật `scan=true` cho `logback-spring.xml` dùng Spring extensions:** không tương thích với vòng đời extension theo tài liệu Spring Boot.

**Sai lầm 4 — tin Logback tự fallback mọi lỗi:** fallback XML syntax không cứu được mọi lỗi appender/filter/network.

**Sai lầm 5 — nhầm Log4j 2 `monitorInterval` là milliseconds:** trong Log4j 2 giá trị là giây; `0` tắt polling.

**Sai lầm 6 — dùng `LogManager.reset()` để “sửa nhanh” JUL:** có thể đóng tất cả handlers và làm log biến mất.

**Sai lầm 7 — dùng Actuator `configuredLevel:null` để khôi phục toàn bộ pipeline:** chỉ reset logger-level override, không sửa appender/layout/TLS.

**Sai lầm 8 — rollback config nhưng không rollback plugin version:** class/attribute có thể không tương thích với library đang chạy.

**Sai lầm 9 — quên configuration precedence:** environment/command-line override vẫn thắng bản file đã restore.

**Sai lầm 10 — quên các pod/instances khác:** một pod rollback, cluster có state không nhất quán.

**Sai lầm 11 — ghi đè trực tiếp file watcher đang đọc:** có thể xuất hiện snapshot XML chưa hoàn chỉnh.

**Sai lầm 12 — tắt redaction hoặc bật SQL bind TRACE:** có thể làm lộ secret/PII, vượt xa sự cố logging ban đầu.

**Sai lầm 13 — giữ HTTP remote appender synchronous:** backend logging chậm làm request latency tăng.

**Sai lầm 14 — tin TCP write/HTTP ACK là durable:** cần xác minh backend receiver và queue semantics.

**Sai lầm 15 — chỉ nhìn log để xác nhận log pipeline khỏe:** chính đường log có thể đang lỗi; dùng metrics/health độc lập.

**Sai lầm 16 — không đo duplicate/drop:** sau restore tưởng có nhiều sự kiện hơn nhưng thực chất là routing/tracing lặp.

## 19. Checklist trước, trong và sau rollback

### Trước rollback
- [ ] Xác nhận sự cố và phạm vi service/pod/sink.
- [ ] Lưu metadata version/config digest và incident timestamp.
- [ ] Chọn last-known-good tương thích với application/library.
- [ ] Kiểm tra syntax, plugin, levels, additivity, filters, file paths và destinations.
- [ ] Đánh giá privacy/TLS/auth và hiện trạng secret rotation.
- [ ] Xác định rollback strategy, change owner và tiêu chí dừng.

### Khi rollback
- [ ] Áp dụng qua kênh đã phê duyệt (versioned deploy, file reload, runtime override).
- [ ] Không tự sửa ngầm nhiều nguồn cấu hình cùng lúc.
- [ ] Giữ kênh chẩn đoán tối thiểu hoạt động.
- [ ] Theo dõi startup/status logger và rollback status.
- [ ] Canary trên một instance trước nếu cần rolling deployment.
- [ ] Không mở DEBUG/TRACE hoặc tắt TLS tùy tiện.

### Sau rollback
- [ ] Xác nhận active version trên mỗi instance.
- [ ] Đảm bảo INFO/WARN/ERROR phù hợp policy.
- [ ] Xác nhận appender/collector/backend thực nhận event.
- [ ] Kiểm tra duplicate, drops, queue depth, retry, disk quota.
- [ ] Kiểm tra schema, timestamp, trace ID, không lộ synthetic secrets.
- [ ] Đo log volume, CPU, request latency và error rate.
- [ ] Ghi lại outcome, commit/config version và bài học phòng ngừa.
- [ ] Đưa hotfix runtime trở về GitOps/source of truth khi phù hợp.

**Kết luận:** khôi phục cấu hình logging production là **khôi phục một khả năng quan sát đáng tin**, không chỉ là sửa một file. Hãy có last-known-good được version hóa, áp dụng theo lifecycle đúng của Logback/Log4j 2/JUL/Spring Boot, và xác minh bằng canary event, metrics và kiểm tra privacy xuyên toàn pipeline. Khi chưa xác minh được dữ liệu đã tới đúng sink, chưa nên tuyên bố rollback hoàn tất.

## Tài liệu tham khảo chính thức

- [Logback — Configuration: automatic scanning, previous safe configuration](https://logback.qos.ch/manual/configuration.html).
- [Logback — Appenders, levels, filters và additivity](https://logback.qos.ch/manual/architecture.html).
- [Apache Log4j 2 — Configuration file, monitorInterval, reliability](https://logging.apache.org/log4j/2.x/manual/configuration.html).
- [Apache Log4j 2 — Status Logger](https://logging.apache.org/log4j/2.x/manual/status-logger.html).
- [Spring Boot — Logging and Logback extensions](https://docs.spring.io/spring-boot/reference/features/logging.html).
- [Spring Boot Actuator — Loggers endpoint](https://docs.spring.io/spring-boot/reference/actuator/loggers.html).
- [Oracle JDK 17 — LogManager: reset, readConfiguration, updateConfiguration](https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/LogManager.html).
- [Oracle JDK 17 — Logger and Handler](https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/Logger.html).
- [OpenTelemetry — Collector resiliency](https://opentelemetry.io/docs/collector/resiliency/).
- [OpenTelemetry — Logs Data Model](https://opentelemetry.io/docs/specs/otel/logs/data-model/).
- [OWASP — Logging Cheat Sheet, data to exclude](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html).