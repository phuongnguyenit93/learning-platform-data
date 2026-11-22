# Điều chỉnh level khẩn cấp khi vận hành Java logging trong production

## 1. Khi nào cần đổi log level khẩn cấp?

Trong production, nhiều ứng dụng Java mặc định ghi các sự kiện quan trọng ở mức `INFO`, `WARN` hoặc `ERROR` để kiểm soát CPU, lượng dữ liệu log, độ trễ và nguy cơ lộ thông tin. Khi xuất hiện sự cố khó tái hiện — ví dụ một nhóm request bị timeout, một luồng message bị xử lý lặp hoặc một trạng thái nghiệp vụ bất thường — đội trực vận hành đôi khi cần **tạm thời nâng độ chi tiết logging**, thường là từ `INFO` lên `DEBUG` cho một package, class hoặc thành phần cụ thể.

**Điều chỉnh level khẩn cấp** là một thay đổi vận hành có chủ đích, có phạm vi, thời hạn và kế hoạch hoàn nguyên; không đơn thuần là đổi `root=DEBUG` rồi quên.

Ví dụ:

```text
Hiện trạng:
  com.example.payment        INFO
  com.example.order          INFO
  root                       INFO

Sự cố:
  Một nhánh payment có retry khác thường nhưng ERROR log thiếu ngữ cảnh.

Thay đổi tạm thời:
  com.example.payment.client DEBUG
  com.example.payment        INFO (giữ nguyên)
  root                       INFO (giữ nguyên)

Sau điều tra:
  Khôi phục đúng configured level ban đầu của
  com.example.payment.client (có thể là INHERIT/null).
```

Lợi ích mong đợi:
- Thu thập thêm thông tin cho **một giả thuyết điều tra cụ thể**.
- Không cần deploy lại ứng dụng nếu backend hỗ trợ đổi level runtime và kênh điều khiển đã được chuẩn bị.
- Giảm thời gian tìm nguyên nhân sự cố so với bật debug toàn bộ hệ thống.
- Giữ khả năng phục hồi bằng rollback/TTL, audit trail và giám sát tăng tải.

Rủi ro nếu làm sai:
- Ghi nhiều dữ liệu hơn dự kiến, đầy disk/collector hoặc tăng phí ingest.
- DEBUG/TRACE làm lộ request body, credential, thông tin cá nhân, SQL parameters hoặc stack trace.
- Async appender queue đầy, event quan trọng bị discard hoặc thread nghiệp vụ bị block.
- Chỉ một pod được chỉnh, các pod khác vẫn giữ level cũ; chẩn đoán bị lệch.
- Sau restart hoặc reload config, runtime override biến mất; nhân viên tưởng đã bật nhưng thực tế không còn.
- Không thể phục hồi đúng baseline nếu ban đầu logger **kế thừa level từ cha**.

**Mục tiêu kép:** đủ thêm tín hiệu để chẩn đoán và **không làm sự cố production nghiêm trọng hơn**. Có tình huống không nên bật DEBUG trong production, nhất là khi code hiện tại có khả năng log secret mà chưa có guardrails.

## 2. Hiểu đúng level, cấu hình kế thừa và filter

### 2.1. Hai hệ tên mức log phổ biến

| Mục đích | SLF4J/Logback/Log4j2 thường dùng | JUL (`java.util.logging`) |
| --- | --- | --- |
| Thông tin chẩn đoán chi tiết nhất | `TRACE` | Thường tương ứng `FINEST` |
| Chẩn đoán | `DEBUG` | Thường tương ứng `FINE` |
| Thông tin vận hành | `INFO` | `INFO` |
| Cảnh báo | `WARN` | `WARNING` |
| Lỗi | `ERROR` | `SEVERE` |
| Tắt mọi level | `OFF` | `OFF` |
| Cho phép tất cả | `ALL` ở backend có hỗ trợ | `ALL` |

Bảng chỉ là **ánh xạ ý nghĩa tương đối**, không phải phép chuyển đổi API tuyệt đối. JUL có thêm `CONFIG` và `FINER`; với bridge JUL sang SLF4J, cách map phụ thuộc bridge/version. Không áp dụng `DEBUG` trực tiếp vào `java.util.logging.Level` vì JUL không có hằng `Level.DEBUG`.

Các level thường được lọc theo ngưỡng. Ví dụ với Logback, logger ở `INFO` thường phát `INFO`, `WARN`, `ERROR` nhưng bỏ `DEBUG`, `TRACE`. Chuyển một logger sang `DEBUG` cho phép thêm `DEBUG`, **không đồng nghĩa luôn có log DEBUG tại sink**.

### 2.2. Configured level khác effective level

Logger có thể có **configured level** trực tiếp, hoặc `null` nghĩa là kế thừa từ parent (tùy backend). Ví dụ:

```text
root = WARN
com.example = INFO
com.example.payment = INHERIT
com.example.payment.client = INHERIT

effective level của com.example.payment.client = INFO
```

Nếu người vận hành tạm set `com.example.payment.client=DEBUG` rồi hoàn nguyên bằng cách set `INFO`, hành vi hiện thời có vẻ như cũ, nhưng **cấu hình kế thừa đã bị thay đổi**. Sau đó khi `com.example` chuyển `WARN`, child vẫn cố định `INFO` thay vì kế thừa. Rollback đúng phải trả về giá trị **configured level trước thay đổi**, kể cả `null`/inherit.

### 2.3. Logger level, filter và appender không phải một thứ

```text
logger.debug(...)
     |
     v
logger threshold / early filter
     |
     v
logging event
     |
     +----> ConsoleAppender -> threshold filter -> stdout
     |
     +----> AsyncAppender -> queue -> FileAppender -> file
     |
     +----> RemoteAppender -> transport -> collector
```

Bật `DEBUG` ở logger **không vượt qua mọi filter**. Appender có `ThresholdFilter` ở `INFO` vẫn có thể loại DEBUG. Một `TurboFilter` hoặc policy khác có thể chặn sớm. Ngược lại, đổi pattern hoặc mở sink cũng không cứu được sự kiện đã bị logger threshold loại bỏ.

**Xác minh ở hai nơi:** (1) effective logger level sau thay đổi, (2) event thử hoặc event thực **đến được đúng sink** mà nhóm điều tra đang sử dụng.

## 3. Những trường hợp nên và không nên đổi level

| Tình huống | Cách tiếp cận |
| --- | --- |
| Sự cố chỉ xảy ra tại một thành phần nhỏ và DEBUG đã được thiết kế an toàn | Nâng DEBUG đúng logger/package, phạm vi instance nhỏ, TTL ngắn |
| Một request cụ thể khó tái hiện và platform hỗ trợ debug theo request/trace ID có kiểm soát | Ưu tiên cơ chế chọn lọc đó hơn nâng toàn package |
| Cần chi tiết từ HTTP client của hệ thống con | Chỉ bật logger của client cần thiết; rà soát wire/header/body logging |
| Lỗi runtime đã có đầy đủ stack và metric | Kiểm tra sẵn event/trace trước; có thể không cần đổi level |
| Ứng dụng đang thiếu CPU, memory hoặc collector sắp đầy | Cân nhắc ngưng/giảm tải, bổ sung metrics/tracing thay vì tăng log |
| Có nguy cơ DEBUG ghi token, cookie, số thẻ hoặc thông tin định danh | Không bật cho đến khi có redaction/allowlist và phạm vi an toàn |
| Cần audit bắt buộc hoặc điều tra security incident | Không thay thế đường audit bằng DEBUG; giữ chứng cứ và tuân thủ quyền |
| Không có đường rollback hoặc kênh điều khiển đã được phân quyền | Chuẩn bị cơ chế an toàn trước, tránh thay đổi ad hoc không kiểm soát |
| Muốn đổi `root=TRACE` toàn cluster để “xem hết” | Thường không phù hợp; thu hẹp giả thuyết, logger và thời hạn |

DEBUG/TRACE càng rộng thường càng làm tăng noise. Khuyến nghị thực dụng là **bắt đầu nhỏ nhất có thể**, quan sát rồi chỉ mở rộng nếu dữ liệu chưa đủ và tài nguyên còn an toàn.

## 4. Runbook điều chỉnh level khẩn cấp trong production

Một quy trình có kiểm soát nên chia thành các giai đoạn **chuẩn bị → thực hiện → xác minh → quan sát → hoàn nguyên → ghi nhận**.

### Bước 1 — Mô tả giả thuyết

Ghi rõ:
- Incident hoặc ticket ID.
- Vấn đề cần quan sát: ví dụ “tại sao HTTP client retry sau timeout”.
- Logger/package cần điều chỉnh và vì sao được chọn.
- Level dự định (thường `DEBUG` trước khi cân nhắc `TRACE`).
- Cluster, namespace, service, version, pod/instance chịu tác động.
- Mốc thành công: event, field hoặc luồng xử lý cần thấy.

Không bắt đầu từ “bật tất cả để lấy thêm dữ liệu”. Nếu có distributed trace, metrics, request ID hoặc log sẵn, dùng chúng để khoanh vùng trước.

### Bước 2 — Ghi baseline

Trước khi đổi, ghi lại:
- **Configured level** hiện tại của logger (có thể `null`/INHERIT).
- **Effective level** hiện tại.
- Parent/root level liên quan.
- Filter/appender/pattern hiện hành nếu cần.
- Những instance đã được kiểm tra; instance nào chưa tiếp cận được.
- Công cụ/API được dùng và thời điểm thay đổi.

Baseline phải đủ để **khôi phục đúng**, không chỉ “về lại INFO”. Khi một service có nhiều instance hoặc nhiều LoggerContext, trạng thái có thể khác nhau theo node.

### Bước 3 — Đánh giá rủi ro và phê duyệt

Kiểm tra:
- Code ở level mới có thể log payload, secrets, SQL params, header hoặc PII không?
- Queue/file/collector còn bao nhiêu capacity? Có quota hoặc retention phù hợp?
- Có người chịu trách nhiệm và thời hạn hết hạn bắt buộc không?
- Có kênh vận hành đã xác thực/ủy quyền, audit thay đổi và cơ chế rollback không?
- Có cần tránh bật ở production dữ liệu thật và thay bằng staging/canary/trace sampling?

Với thay đổi khẩn cấp, quy trình phê duyệt có thể được rút gọn theo chính sách ứng cứu incident, **không có nghĩa bỏ kiểm soát truy cập hoặc bỏ nhật ký thay đổi**.

### Bước 4 — Thực hiện thay đổi nhỏ, có TTL

- Chọn **class/package/logger** hẹp nhất và nếu được chỉ một instance/canary đầu tiên.
- Ghi ID, owner và `expiresAt` của override.
- Chỉ nâng một mức cần thiết, chẳng hạn `INFO -> DEBUG`.
- Dùng control plane đã được bảo vệ: admin endpoint, config service, công cụ vận hành có RBAC.
- Không sửa root level hoặc nhiều package cùng lúc nếu chưa có lý do và tác động được chấp nhận.

TTL giúp giảm nguy cơ “DEBUG tồn tại cả tuần”. Nếu hệ thống không hỗ trợ TTL nguyên bản, cần automation/đơn vị trực chịu trách nhiệm **hoàn nguyên tại hạn đã định**, đồng thời dự phòng trường hợp automation lỗi.

### Bước 5 — Xác minh hiệu lực

- GET/đọc lại configured và effective level tại instance đã đổi.
- Phát/quan sát một event thử an toàn trong đúng logger nếu có cách phù hợp, không chèn dữ liệu thật nhạy cảm.
- Kiểm tra event tới **sink đích**, không chỉ thấy trong console của một pod.
- Quan sát tần suất log, queue depth, dropped events, CPU, disk, collector ingest, error rate và p95/p99 latency.
- Nếu không có tín hiệu kỳ vọng, kiểm tra **filter/đúng logger/đúng instance** trước khi mở thêm nhiều scope.

### Bước 6 — Kết thúc và hoàn nguyên

- Ngay khi thu đủ bằng chứng hoặc đến TTL, hoàn nguyên configured level baseline **kể cả null/inherit**.
- Xác minh lại effective level, level của root/parent, và DEBUG event không còn đi qua nơi dự kiến sau rollback.
- Đối chiếu thay đổi ở tất cả instance/replica đã tác động.
- Lưu ghi chú về thời gian bật, loại dữ liệu đã thu, quyền truy cập và retention cần xử lý.
- Nếu thay đổi chưa thể rollback, mở incident/chặn mở rộng và chuyển giao rõ chủ sở hữu; không để một override vô chủ.

## 5. Lựa chọn phạm vi: class, package, root, instance và request

### Class hoặc logger cụ thể

Ví dụ logger `com.example.payment.client.GatewayClient` chỉ phát log của một thành phần. Đây là scope tốt nếu mã đã tạo log chẩn đoán phù hợp.

### Package

`com.example.payment.client` thường bao phủ nhiều class trong nhóm client, giảm thao tác set level từng class nhưng có thể tăng volume hơn dự đoán. Lưu ý **tên logger không bắt buộc trùng Java package**: ứng dụng có thể đặt logger tùy ý.

### Root logger

Thay `ROOT=DEBUG` ảnh hưởng phần lớn thư viện và appender; third-party components có thể ghi dữ liệu bạn chưa rà soát. Chỉ dùng nếu mọi scope hẹp đã bị loại trừ và có đánh giá rủi ro đầy đủ. **ROOT TRACE** đặc biệt nguy hiểm về volume và dữ liệu nhạy cảm.

### Một instance hay toàn cluster?

Một điều chỉnh runtime thường chỉ đổi level **trong đúng JVM được gọi**. Kubernetes có nhiều pod; load balancer có thể đưa request vào pod không bật DEBUG. Một pod mới sau autoscaling có thể khởi động từ cấu hình chuẩn và không biết runtime override đang tồn tại.

Nếu cần thay đổi toàn cluster, nên có control plane phân phối, kiểm soát phiên bản, ACK từng instance, TTL và kiểm tra trạng thái drift. Tránh thao tác thủ công bằng một loạt lệnh không có danh sách kết quả vì có thể tạo nửa cluster DEBUG, nửa cluster INFO.

### Theo request/correlation ID

Một số nền tảng có cơ chế **selective logging** hoặc sampling dựa trên request/trace ID; cách này có thể giảm tác động. Tuy nhiên, không phải SLF4J/Logback mặc định có “set level cho một request” chỉ bằng MDC. Phải có filter/cơ chế riêng được thiết kế và kiểm thử; đồng thời tránh làm lộ giá trị `Authorization`, session ID hoặc user input chưa validate trong MDC.

## 6. Java 17 chạy độc lập: đổi JUL level và khôi phục kế thừa

Ví dụ sau dùng **`java.util.logging` (JUL)** có sẵn trong JDK 17. Nó chứng minh ba điểm:
1. Logger con có thể kế thừa level cha khi `getLevel()==null`.
2. `setLevel(Level.FINE)` tạm cho phép log chẩn đoán.
3. Khôi phục bằng `setLevel(originalLevel)` giữ lại đúng trạng thái `null`/inherit.

Chương trình chỉ chạy trong bộ nhớ, không tạo endpoint admin production. Nó dùng handler riêng in kết quả cố định, không phụ thuộc timestamp, thread name hoặc format mặc định của `ConsoleHandler`.

### 6.1. Tạo file `EmergencyLevelDemo.java`

```java
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public class EmergencyLevelDemo {
    private static String name(Level level) {
        return level == null ? "INHERIT" : level.getName();
    }

    public static void main(String[] args) {
        Logger parent = Logger.getLogger("example.ops");
        Logger child =
                Logger.getLogger("example.ops.payment");

        Level oldParentLevel = parent.getLevel();
        Level oldChildLevel = child.getLevel();
        boolean oldParentHandlers = child.getUseParentHandlers();

        Handler testSink = new Handler() {
            @Override
            public void publish(LogRecord record) {
                if (isLoggable(record)) {
                    System.out.println(
                            "EVENT " + record.getLevel().getName()
                                    + " " + record.getMessage());
                }
            }

            @Override
            public void flush() {}

            @Override
            public void close() {}
        };
        testSink.setLevel(Level.ALL);

        try {
            parent.setLevel(Level.WARNING);
            child.setLevel(null); // Kế thừa WARNING.
            child.setUseParentHandlers(false);
            child.addHandler(testSink);

            Level baseline = child.getLevel();
            System.out.println(
                    "baselineConfigured=" + name(baseline));
            System.out.println(
                    "beforeFineEnabled=" + child.isLoggable(Level.FINE));
            child.fine("hidden-diagnostic");
            child.warning("initial-warning");

            // Thay đổi tạm thời theo incident:
            child.setLevel(Level.FINE);
            System.out.println(
                    "duringFineEnabled=" + child.isLoggable(Level.FINE));
            child.fine("diagnostic-request-id-test-42");
            child.info("active-info");

            // Khôi phục đúng configured level, kể cả null.
            child.setLevel(baseline);
            System.out.println(
                    "restoredConfigured=" + name(child.getLevel()));
            System.out.println(
                    "afterFineEnabled=" + child.isLoggable(Level.FINE));
            child.fine("hidden-after-restore");
            child.warning("restored-warning");
        } finally {
            child.removeHandler(testSink);
            testSink.close();
            child.setUseParentHandlers(oldParentHandlers);
            child.setLevel(oldChildLevel);
            parent.setLevel(oldParentLevel);
        }
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```bash
javac EmergencyLevelDemo.java
java EmergencyLevelDemo
```

**Stdout dự kiến chính xác** khi chạy chương trình này riêng:

```text
baselineConfigured=INHERIT
beforeFineEnabled=false
EVENT WARNING initial-warning
duringFineEnabled=true
EVENT FINE diagnostic-request-id-test-42
EVENT INFO active-info
restoredConfigured=INHERIT
afterFineEnabled=false
EVENT WARNING restored-warning
```

### 6.2. Giải thích

- Parent có `Level.WARNING`; child có configured level `null`, nên `FINE` và `INFO` không được chấp nhận ở giai đoạn đầu.
- Handler có level `ALL` để **chính logger threshold** là yếu tố duy nhất được kiểm tra; nếu handler ở `WARNING` thì nâng child lên `FINE` cũng chưa đủ để thấy FINE.
- `child.setLevel(Level.FINE)` cho phép `FINE`, `INFO` và `WARNING` của child theo thứ tự ngưỡng JUL.
- Khôi phục `null` giúp child kế thừa parent một lần nữa. Nếu thay bằng `Level.WARNING`, ta sẽ phá vỡ cơ chế inheritance dù log trông giống nhau trong phiên thử.
- `finally` phục hồi trạng thái trước khi ví dụ tác động lên JVM, gỡ handler và cờ `useParentHandlers` để tránh làm nhiễu mã khác.
- Các message “diagnostic” là dữ liệu thử an toàn, không chứa token hay payload thật.

**Giới hạn:** đây là minh họa đổi level bằng API trong một JVM, không có TTL tự động, RBAC, phê duyệt, nhiều replica, persistence hay distributed control plane. `java.util.logging` có cơ chế cấu hình khác Logback; không chuyển nguyên tên `FINE` sang backend dùng `DEBUG`.

## 7. Logback: chỉnh level runtime qua backend, không qua SLF4J facade

**SLF4J là facade.** API `org.slf4j.Logger` cho phép gọi `debug/info/warn/error` nhưng **không định nghĩa `setLevel`**. Nếu backend thật là Logback, có thể dùng API của Logback trong kênh quản trị đã được kiểm soát.

Snippet **chỉ minh họa**, cần dependency `logback-classic` và `slf4j-api` tương thích, cùng logger thực sự do Logback quản lý:

```java
import ch.qos.logback.classic.Level;
import ch.qos.logback.classic.Logger;
import ch.qos.logback.classic.LoggerContext;
import org.slf4j.LoggerFactory;

LoggerContext context =
        (LoggerContext) LoggerFactory.getILoggerFactory();

Logger target = context.getLogger(
        "com.example.payment.client.GatewayClient");

Level configuredBefore = target.getLevel(); // Có thể null.
try {
    target.setLevel(Level.DEBUG);
    // Trigger một thao tác thử an toàn và xác minh tại sink.
} finally {
    target.setLevel(configuredBefore);
}
```

Code trên **không phải class Java hoàn chỉnh**: cần đặt các câu lệnh trong một method và cung cấp quá trình thử phù hợp. Việc cast `ILoggerFactory` sang `LoggerContext` chỉ hợp lệ khi backend là Logback. Với Log4j2, cast này sẽ thất bại. Không thêm đoạn code quản trị này vào mọi request vì nó có thể làm level nhảy liên tục giữa các thread.

### Trạng thái inherited cần giữ nguyên

Trong Logback, `target.getLevel()` có thể trả `null` khi không cấu hình level riêng; `target.getEffectiveLevel()` cho biết level thực tế. Trong công cụ quản trị nên lưu **cả hai**:

```text
loggerName = com.example.payment.client.GatewayClient
configuredBefore = null
effectiveBefore = INFO
temporaryConfigured = DEBUG
expiresAt = [thời điểm được duyệt]
```

Khi rollback, set configured level về `null`, không luôn set về `INFO`. Lưu chú ý rằng một logger cấp cha hoặc root có thể bị chỉnh bởi một thay đổi khác trong lúc incident đang diễn ra; phải đánh giá **xung đột cấu hình** trước khi hoàn nguyên mù ghi đè thay đổi mới.

### Đừng coi runtime override là cấu hình vĩnh viễn

Một reconfiguration hoặc restart có thể nạp lại `logback.xml`/`logback-spring.xml` và xóa override tạm. Ngược lại, một hệ thống config runtime tập trung có thể giữ override qua restart nếu được lập trình như vậy. Không thể kết luận chỉ từ việc thay đổi đã thành công trên một JVM; cần biết **source of truth và thứ tự ưu tiên cấu hình**.

## 8. Spring Boot Actuator: điều chỉnh level qua endpoint quản trị

Ứng dụng Spring Boot dùng Actuator có endpoint `loggers` cho phép **xem level hiện tại** và, trong cấu hình hỗ trợ, **đổi configured level tại runtime**. Đây là lựa chọn hay dùng trong incident, nhưng là một **bề mặt điều khiển nhạy cảm**.

### 8.1. Xem trước khi đổi

Đường dẫn phổ biến khi endpoint được bật và sử dụng HTTP:

```text
GET /actuator/loggers/com.example.payment.client
```

Một response minh họa:

```json
{
  "configuredLevel": null,
  "effectiveLevel": "INFO"
}
```

`null` ở đây thường thể hiện logger đang kế thừa. **Ghi lại giá trị này** cùng tên instance, thời điểm, người thay đổi và ticket. Đừng chỉ chép effective level.

### 8.2. Đổi tạm thời

Payload thường dùng:

```http
POST /actuator/loggers/com.example.payment.client
Content-Type: application/json

{"configuredLevel":"DEBUG"}
```

Sau đó GET lại để xác minh. Khi cần khôi phục trạng thái `inherit` ban đầu:

```http
POST /actuator/loggers/com.example.payment.client
Content-Type: application/json

{"configuredLevel":null}
```

Nếu configured level ban đầu là `WARN` hoặc `INFO` được đặt trực tiếp, hãy khôi phục **đúng giá trị đã ghi**, không set `null` theo thói quen. Một ứng dụng có thể dùng backend hỗ trợ level khác biệt; câu trả lời thực tế của endpoint và hệ thống quản trị mới là dữ liệu để xác minh.

### 8.3. Cấu hình exposure phải đi cùng bảo mật

Với Spring Boot Actuator được cấu hình có web endpoint `loggers`, có thể cấu hình exposure tương ứng, ví dụ:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: "health,info,loggers"
```

**Không sao chép cấu hình này vào production mà không bảo vệ endpoint.** Exposure chỉ cho phép route tồn tại; nó **không tự áp dụng RBAC**. Cần triển khai authentication, authorization, network segmentation, TLS/mTLS hoặc đường truy cập nội bộ đúng tiêu chuẩn vận hành. Kiểm tra policy Spring Security/management context hiện hành. Không mở `/actuator/loggers` công khai ra Internet hoặc bỏ xác thực để “xử lý nhanh”.

Một quy trình vận hành an toàn thường dùng admin gateway có audit, hoặc truy cập local đã được xác thực qua port-forward/tunnel có phân quyền. Việc có thể `curl` từ localhost **không thay thế** xác thực hoặc phê duyệt điều chỉnh level.

### 8.4. Trường hợp nhiều pod

Mỗi JVM thường có logger context riêng. `POST` đến một instance qua Service/load balancer có thể chỉ ảnh hưởng **pod được chọn** ở lần request đó; lần GET sau có thể đến pod khác và trả level cũ. Cần truy cập/định danh từng target, phân phối override qua control plane hoặc dùng công cụ operator bảo đảm all-target acknowledgment, thay vì lặp POST vào một URL load-balanced và tự kết luận mọi pod đã đổi.

### 8.5. Phản hồi lỗi

Nếu POST nhận `403`, kiểm tra policy authentication/authorization và CSRF của management endpoint; không tự tắt bảo mật trên toàn app để làm request đi qua. Nếu `404`, endpoint có thể chưa được enable/expose, base path khác hoặc management port khác. Nếu GET báo effective level không đúng, kiểm tra logger name, parent, backend và reconfiguration.

**Về phiên bản:** hành vi chi tiết có thể khác theo Spring Boot version, backend và management security configuration. Xác minh trên đúng bản ứng dụng đang chạy; các payload ở trên mô tả hợp đồng Actuator loggers thông dụng, không bảo đảm mọi triển khai dùng đúng port/base path.

## 9. Log4j2 và JUL trong môi trường production

### Log4j2

Với ứng dụng thực sự dùng Log4j2 Core, API cấu hình runtime và management có thể được hỗ trợ. Một cách programmatic phổ biến là `Configurator.setLevel(loggerName, Level.DEBUG)` của Log4j2 Core. Tuy nhiên:

- Đây **không phải** lời gọi trên facade SLF4J.
- Hiệu lực, propagation và cơ chế phục hồi phải theo logger configuration/context của Log4j2 đang dùng.
- Cần lưu trạng thái trước thay đổi, kể cả inherit, và xác minh thực tế ở đúng context.
- Reload file cấu hình hoặc thay context có thể ghi đè runtime level.
- Không dùng sample cast của Logback trong Log4j2, và ngược lại.

Nếu môi trường dùng một công cụ quản trị Log4j2, hãy dùng **API/phương thức được chính stack đó hỗ trợ** thay vì tự viết remote endpoint chưa có authentication/audit.

### JUL

Trong JUL:
- `Logger.setLevel(Level.FINE)` bật các message `FINE` trở lên cho logger được chọn.
- `Logger.getLevel()==null` thường có nghĩa kế thừa parent level.
- `Logger.isLoggable(Level.FINE)` cho biết level có được chấp nhận ở logger lúc kiểm tra.
- `Handler.setLevel` và `Filter` có thể chặn event sau logger, nên logger enabled chưa đảm bảo sink sẽ nhận.
- `LogManager` có thể load/reload cấu hình từ `logging.properties`; tác động lên runtime level tùy quá trình nạp cấu hình và logger hiện có.

Với Spring Boot, ứng dụng có thể dùng Logback mặc định hoặc bridge giữa logging APIs; cần xác định **provider/backend đang hiệu lực**, không chỉ nhìn một dependency trong mã nguồn rồi suy cơ chế điều chỉnh.

## 10. Phạm vi thay đổi trong Kubernetes, container và nhiều instance

Một hệ thống nhiều pod cần phân biệt ít nhất ba “nơi tồn tại” của level:

1. **Static config:** file YAML/properties, ConfigMap, environment variables, image config và profile được load khi khởi động.
2. **Runtime in-memory override:** API admin điều chỉnh logger trong một JVM hiện sống.
3. **Central dynamic config:** công cụ điều phối phát và thu hồi override qua tất cả instance, có trạng thái và version.

Ví dụ vận hành:

```text
Namespace: prod
Service: payments
Replicas: 4

pod-A  client.DEBUG  (đã đổi)
pod-B  client.INFO   (chưa đổi)
pod-C  client.INFO   (chưa đổi)
pod-D  client.INFO   (chưa đổi)
```

Nếu request lỗi đi vào pod B, ta sẽ không thấy DEBUG dù nhìn GET trên pod A đã đúng. Có hai hướng hợp lý:

- **Canary scope:** chủ động route request thử có kiểm soát tới pod A; ghi rõ chỉ pod A được bật.
- **Cluster scope:** dùng control plane để phát override cho A/B/C/D, xác minh trạng thái từng pod và lưu danh sách những pod chưa thành công.

Một pod mới được tạo khi autoscale có thể không được áp override tạm. Một pod restart có thể mất level in-memory. Điều này không hẳn là bug; nó là đặc tính của scope. **Runbook phải có bước giám sát drift và điều chỉnh thay đổi lifecycle** khi incident còn đang mở.

### Vì sao không đơn giản sửa ConfigMap?

Sửa ConfigMap hoặc environment variable có thể yêu cầu restart/redeploy để có hiệu lực, tùy cơ chế reload của ứng dụng. Nếu muốn debug nhanh, runtime endpoint có lợi nhưng dễ mất sau restart. Nếu muốn cấu hình lâu dài, thay đổi được review trong source of truth có thể phù hợp hơn nhưng cần rolling deployment và rollback plan.

Không dùng hai nguồn cấu hình độc lập mà không quyết định ưu tiên. Ví dụ GitOps reconciler sửa config trong khi admin endpoint tiếp tục override, khiến level quan sát được thay đổi ngoài ý muốn.

## 11. TTL, rollback và chống configuration drift

“Bật DEBUG khoảng 15 phút” phải biến thành một **hợp đồng có thể kiểm chứng**, không chỉ là lời nhắc miệng.

Một bản ghi thay đổi tối thiểu:

```json
{
  "changeId": "loglevel-inc-204",
  "incidentId": "INC-204",
  "service": "payment-service",
  "scope": "com.example.payment.client",
  "targets": ["pod-A"],
  "configuredBefore": null,
  "effectiveBefore": "INFO",
  "temporaryLevel": "DEBUG",
  "requestedBy": "oncall-operator",
  "expiresAt": "2026-11-10T10:15:00Z",
  "status": "ACTIVE"
}
```

JSON mang dữ liệu **giả lập**, không phải thông tin về một incident thật. Cần bổ sung source config version/ownership/version token trong hệ thống có nhiều người thay đổi.

### Khôi phục đúng giá trị

Nếu configuredBefore là:
- `null` → khôi phục inherit, không ép thành `INFO`.
- `WARN` → khôi phục `WARN` trực tiếp.
- `DEBUG` → nếu scope đó vốn đã DEBUG theo một thay đổi hợp lệ trước, không “hoàn nguyên” thành INFO.
- Một override khác đang tồn tại → cần xác định **quyền sở hữu và thứ tự thay đổi** để tránh ghi đè cấu hình mới.

### Compare-and-swap hoặc lease khi nhiều operator

Giả sử operator A bật DEBUG, operator B sau đó đổi TRACE để điều tra khác. Khi TTL của A hết, job của A **không nên mù ghi INFO** làm mất thay đổi của B. Một control plane tốt lưu `changeId`/version và chỉ rollback khi override đang sở hữu vẫn là bản được phép hoàn nguyên.

Lưu ý đây là **thiết kế control plane**, không phải tính năng sẵn có của `Logger.setLevel`, SLF4J hoặc Actuator loggers. Nếu công cụ hiện tại chỉ có GET/POST đơn giản, quy trình phải kiểm tra trạng thái và có cơ chế phối hợp thay đổi ngoài API. Một phép GET trước POST không tự bảo đảm atomic compare-and-swap nếu có thay đổi đồng thời.

### Nếu automation rollback lỗi

Không được im lặng bỏ qua. Đặt alert cho:
- Override quá hạn vẫn ACTIVE.
- Level quan sát sau rollback không giống baseline mong đợi.
- Có pod chưa ACK hoặc inaccessible.
- Pod mới/restart không đồng bộ với scope incident.
- Runtime config trái với source of truth ngoài khoảng change đã duyệt.

## 12. Bảo mật: rủi ro lớn nhất của DEBUG/TRACE production

Nâng log level có thể biến những dòng logging trước đó không phát thành dữ liệu lưu trữ và có thể export. Một code path an toàn ở INFO chưa chắc an toàn khi DEBUG.

Ví dụ cần rà soát:

```java
// Không an toàn nếu headerMap chứa Authorization/cookie.
logger.debug("headers={}", headerMap);

// Không an toàn nếu DTO.toString() có PII/secret.
logger.debug("paymentRequest={}", paymentRequest);

// Không an toàn nếu URL chứa query credentials.
logger.trace("outboundUrl={}", requestUrl);

// Không an toàn nếu exception message chứa raw payload.
logger.debug("external response", exception);
```

Đoạn trên chỉ là **mã minh họa** trong ứng dụng có SLF4J logger và biến liên quan, không phải file Java độc lập. Parameterized logging giúp giảm chi phí format trong một số trường hợp nhưng **không tự che secret**.

### Guardrails tối thiểu

1. Review logger cụ thể dự định bật và các event DEBUG/TRACE đã có trong code.
2. Ưu tiên log **allowlist field** như request ID, status code, duration, outcome, reasonCode.
3. Không log Authorization, cookie, access/refresh token, password, private key, full card number hoặc raw request body.
4. Nếu cần dữ liệu nhạy cảm cho forensic, dùng kho riêng có phân quyền, retention và phê duyệt; không mở rộng console/collector chung.
5. Xác nhận encoder escaping để input `\r`/`\n` không tạo log entry giả.
6. Giới hạn thời gian/scope; không để một thay đổi debug thành trạng thái production lâu dài.
7. Audit ai đã thay đổi, thời điểm, scope, lý do và thời điểm rollback.
8. Nếu đã lộ secret trong log, kích hoạt incident response: thu hồi/rotate secret khi cần, giới hạn quyền đọc, bảo toàn bằng chứng theo quy trình rồi xử lý bản sao dữ liệu theo chính sách.

### Endpoint điều khiển logging phải được bảo vệ

Một admin endpoint cho phép bật TRACE có thể gây log flooding hoặc lộ dữ liệu. Vì vậy phải có identity/RBAC, network control, chống CSRF khi phù hợp, audit, rate limit, TTL và quyền phê duyệt. Không đưa endpoint ra Internet chỉ vì việc vận hành cần tiện.

Một kênh break-glass khẩn cấp nên có **quy trình ủy quyền rõ ràng**, ghi dấu sử dụng và tự hết hạn. Break-glass không đồng nghĩa anonymous endpoint.

## 13. Chi phí hiệu năng và dung lượng khi đổi level

Đối với một service xử lý nhiều request, tăng DEBUG có thể tăng:
- CPU format message, encode JSON và stack trace.
- Allocation rate và GC pressure do object/string/Throwable.
- Thread contention hoặc I/O khi appender đồng bộ.
- Async queue depth, drop count hoặc producer blocking.
- Bytes/s gửi collector, phí ingest và chi phí lưu.
- Disk usage, log rotation và retention pressure.
- Độ trễ p95/p99 của request, nhất là khi sink chậm.

Một cách tính **ước lượng**:

```text
debug_events_per_sec = affected_requests_per_sec
                       * debug_events_per_request

extra_bytes_per_sec = debug_events_per_sec
                      * avg_encoded_bytes_per_event
```

Ví dụ minh họa: 2.000 request/s đi qua component cần debug, thêm 3 event/request, trung bình 400 bytes/event → khoảng **2.400.000 bytes/s** log mới, xấp xỉ **2,4 MB/s** theo đơn vị thập phân, chưa gồm overhead transport/replication. Trong 15 phút, lượng event mới cỡ **2,16 GB** trước nén và nhân bản. Đây chỉ là ước lượng; actual depends on traffic and payload distribution.

### Trước khi nâng level, đo những gì?

- Baseline log throughput theo service/logger và mức log.
- Queue utilization, drop metrics, retry/backpressure.
- Collector ingest capacity/quota; disk/spool free space.
- Request CPU/latency/error rate.
- Network egress và chi phí/retention.
- Có cần bật stack/caller location hay full HTTP wire logging không?

**Không đồng nhất đổi level và đổi appender pattern**: nếu pattern thêm `%class`/`%line`, backend có thể phải walk stack và tăng chi phí ngoài volume do DEBUG. Ngược lại, bật DEBUG trong logger nhưng appender threshold vẫn INFO có thể không tăng bytes ở sink, dù một số công việc trong quá trình phát event vẫn có thể phát sinh.

### Đặt ngưỡng dừng

Trước thay đổi, xác định tiêu chí buộc rollback ngay: ví dụ CPU/latency vượt giới hạn, collector drop, disk đầy nhanh hoặc có dấu hiệu dữ liệu nhạy cảm vào sink. Không chờ hết TTL khi hệ thống đang bị tổn hại.

## 14. Xác minh thay đổi sau khi POST/admin action

Một quy trình xác minh có thể dùng checklist:

| Bước | Phương pháp | Kết luận được phép |
| --- | --- | --- |
| Đúng target | Tên pod/instance, environment, logger | Điều chỉnh không nhầm service |
| Đúng configured level | GET admin API sau POST | Giá trị runtime đang được đặt như mong muốn |
| Đúng effective level | API/logger introspection | Kế thừa/hierarchy cho phép mức cần thiết |
| Event mới phát | Synthetic request an toàn tới đúng component | Code path có thể phát DEBUG |
| Event đến sink | Query event ID ở file/collector mục tiêu | Pipeline nhận event ở phạm vi đo |
| Không lộ dữ liệu nhạy cảm | Kiểm tra field/output với test giả, review sample | Guardrails được áp dụng trong phạm vi kiểm tra |
| Tải ổn định | CPU/p99, queue, drop, spool, disk/ingest | Thay đổi chưa gây tác động vượt ngưỡng |
| Phạm vi đúng | Đối chiếu danh sách pod/instance | Không có drift ngoài scope |
| TTL hoạt động | Kiểm tra lịch hoàn nguyên và người sở hữu | Có kế hoạch kết thúc đáng tin |

Một số lưu ý:

- Chỉ tìm thấy `"DEBUG"` trong message không chứng minh event level là DEBUG; nếu cần test level, dùng API/event metadata.
- `logger.isDebugEnabled()` đúng chỉ nói logger sẵn sàng phát DEBUG; appender/filter hoặc collector vẫn có thể bỏ event.
- Một record xuất hiện trong pod stdout không chứng minh nó đã ingest vào hệ thống tập trung.
- Một event không thấy ngay có thể do **async delay, sampling, wrong instance, filter, indexing latency hoặc timezone query**, không nhất thiết vì đổi level thất bại.
- Nếu lưu event theo batch, cần tìm bằng ID và khoảng thời gian đủ, không suy từ một query trống.

## 15. Hạn chế sự cố khi cần quan sát trong thời gian ngắn

Thay vì bật DEBUG rộng, cân nhắc:

- **Narrow logger:** một class hoặc package.
- **Canary instance:** một pod với traffic chọn lọc.
- **Request-scoped filter:** chỉ sự kiện có correlation ID an toàn, khi framework hỗ trợ.
- **Temporary metric:** counter, histogram, timer cho một điều kiện khó quan sát mà không cần log raw dữ liệu.
- **Tracing sampling:** trace chọn lọc, giới hạn quyền và thời gian.
- **Diagnostic endpoint read-only:** trả về trạng thái tổng hợp an toàn thay vì raw object.
- **Feature flag có TTL:** điều khiển việc thu thập trường diagnostic đã được allowlist, có audit.

Các lựa chọn này cũng cần đánh giá bảo mật. “Read-only” endpoint có thể vẫn tiết lộ topology, user data hoặc trạng thái nhạy cảm; sampling có thể bỏ sót trường hợp hiếm; log request-scoped cần đảm bảo filter theo context chính xác qua thread/executor.

### Phân biệt debug thu thập và audit sự kiện

Audit bắt buộc như thay đổi quyền, giao dịch hoặc truy cập nhạy cảm không nên bị thay thế bằng một lệnh bật DEBUG trong lúc incident. Audit thường cần schema, retention, integrity, quyền truy cập và delivery guarantee riêng. Đừng giảm cấp hoặc tắt audit sink để lấy thêm dung lượng cho DEBUG mà không có quyết định đúng cấp.

## 16. Kiểm thử quy trình đổi level: test cả rollback và nhánh lỗi

### 16.1. Unit test/JUL

Từ `EmergencyLevelDemo`, các kiểm tra cốt lõi:

- Với parent `WARNING` và child `null`, `FINE` không được phát.
- Sau `child.setLevel(FINE)`, event FINE tới handler nếu handler/filter cho phép.
- Khôi phục child về `null`, `FINE` bị chặn trở lại.
- Nếu child có configured level ban đầu `INFO`, rollback phải là `INFO`, không phải `null`.
- Nếu handler ở `WARNING`, một logger DEBUG/FINE không ép handler nhận event; phải test lớp filter riêng.
- Gỡ handler, restore parent/child level và `useParentHandlers` trong `finally`.

Đối với JUnit 5, có thể dựng fixture kiểu test phía dưới. Đây là **snippet cần JUnit Jupiter trên classpath**, không phải chương trình độc lập:

```java
import static org.junit.jupiter.api.Assertions.*;
import java.util.logging.Level;
import java.util.logging.Logger;
import org.junit.jupiter.api.Test;

class EmergencyLevelTest {
    @Test
    void restoreInheritedConfiguredLevel() {
        Logger parent = Logger.getLogger("test.ops");
        Logger child = Logger.getLogger("test.ops.client");

        Level oldParent = parent.getLevel();
        Level oldChild = child.getLevel();
        try {
            parent.setLevel(Level.WARNING);
            child.setLevel(null);

            assertFalse(child.isLoggable(Level.FINE));

            Level before = child.getLevel();
            child.setLevel(Level.FINE);
            assertTrue(child.isLoggable(Level.FINE));

            child.setLevel(before);
            assertNull(child.getLevel());
            assertFalse(child.isLoggable(Level.FINE));
        } finally {
            child.setLevel(oldChild);
            parent.setLevel(oldParent);
        }
    }
}
```

Để tránh các test chạy song song đụng cùng named logger, nên dùng tên logger **duy nhất theo test** hoặc cô lập LoggerContext và quản lý lifecycle. Đừng thay root logger của toàn test suite mà không restore.

### 16.2. Integration test backend/admin

Kiểm thử trên một môi trường có quyền và network isolation thích hợp:

1. Đọc configured/effective level baseline.
2. Gọi management API set DEBUG cho logger thử có chứa thông tin an toàn.
3. GET lại và xác nhận configured/effective.
4. Phát một event thử với event ID duy nhất qua component tương ứng.
5. Đợi event tới sink với timeout/ack hoặc polling có giới hạn; không dùng một `Thread.sleep` cố định làm bằng chứng.
6. Kiểm tra output/metadata không có secret giả.
7. Khôi phục configured baseline, kể cả `null`.
8. Kiểm tra event DEBUG mới không còn xuất hiện và event WARN/ERROR cần thiết vẫn tới sink.
9. Nếu có nhiều replica, xác minh từng instance thuộc scope.
10. Kết thúc test phải cleanup/rollback ngay cả khi assertion thất bại.

### 16.3. Fault injection và tình huống phải xử lý

| Tình huống | Kết quả mong đợi |
| --- | --- |
| POST đổi level bị `403` | Không bỏ xác thực; báo thiếu quyền và theo runbook |
| Chỉ một pod đổi thành công | Báo partial scope, không gọi cluster-wide success |
| Pod restart giữa incident | Có drift detection, áp lại có kiểm soát hoặc đổi kế hoạch |
| Một operator đổi TRACE trong lúc TTL DEBUG đang chạy | Rollback có ownership/version policy, không ghi đè mù |
| Logger effective DEBUG nhưng không thấy event | Chẩn đoán appender filter, sink, query và code path |
| Collector đầy, drop tăng | Ngưỡng dừng kích hoạt rollback |
| Phát hiện bearer token trong DEBUG | Dừng phát log mới, bảo vệ dữ liệu, incident response |
| Admin endpoint bị gọi trái phép | Alert/audit, thu hẹp quyền, đánh giá tác động |
| TTL job thất bại | Alert có owner, rollback thủ công được kiểm soát |
| Root level được đổi trong khi child đang inherit | Xác minh effective level lại, không dựa vào giá trị cũ |

Đối với concurrent config operations, cần test rằng các bước kiểm tra trạng thái và rollback không phá thay đổi của người khác. API GET + POST đơn thuần không có atomicity cho bài toán này; nếu cần guarantee, dùng control plane hỗ trợ version/lease.

## 17. Tình huống thực hành: điều tra timeout tại payment client

Giả định dịch vụ `payment-service` gặp timeout 3% request, nhưng log `WARN` chỉ cho biết một dependency trả lỗi. Đội trực vận hành muốn xem các quyết định retry và đường đi request, **không cần log HTTP body**.

### 17.1. Chuẩn bị

- Incident: `INC-204` (giả định).
- Logger mục tiêu: `com.example.payment.client.GatewayClient`.
- Baseline: configured `null`, effective `INFO`.
- Temporary: `DEBUG`.
- Scope: một pod được chỉ định, traffic test không chứa dữ liệu thật nhạy cảm.
- TTL: 15 phút hoặc kết thúc sớm khi có tín hiệu đủ.
- Điều kiện dừng: collector drop, CPU/p99 vượt ngưỡng đã duyệt hoặc log xuất hiện dữ liệu nhạy cảm.
- Người phê duyệt/owner: theo on-call policy.

### 17.2. Thực hiện

```text
1. GET logger state ở pod được chọn -> lưu baseline.
2. POST configuredLevel=DEBUG qua kênh quản trị đã bảo vệ.
3. GET lại -> kiểm tra effective DEBUG.
4. Phát một payment request test an toàn tới pod đó.
5. Tìm requestId test trên collector và kiểm tra:
   - retry reasonCode
   - request attempt
   - downstream status
   - elapsed time
6. Theo dõi tần suất log và resource/ingest.
7. Kết thúc/đến TTL -> POST configuredLevel=null.
8. GET lại -> effective INFO, configured null.
9. Ghi thời gian thay đổi, dữ liệu thu, kết quả điều tra.
```

Một bảng ghi lại tình trạng:

| Mốc | Configured | Effective | Ghi chú |
| --- | --- | --- | --- |
| Trước | `null` | `INFO` | Kế thừa |
| Đang điều tra | `DEBUG` | `DEBUG` | Chỉ pod được chọn |
| Sau rollback | `null` | `INFO` | Kế thừa được khôi phục |

### 17.3. Nếu không thấy log DEBUG

Không mở ngay `root=TRACE`. Kiểm tra:
- Tên logger trong code thực tế có trùng tên admin API không?
- Request có thật đến đúng pod đã điều chỉnh không?
- Code path đó có lời gọi DEBUG tại các điểm cần quan sát không?
- Appender/ThresholdFilter có chặn DEBUG không?
- Async queue có discard hoặc worker/sink chậm không?
- Query có đúng index, timezone, service, trace ID và thời gian ingest không?
- Pod đã restart/reload config làm override mất chưa?

**Đầu ra tốt của incident không nhất thiết là nhiều dòng DEBUG.** Mục tiêu là xác nhận/bác bỏ giả thuyết bằng tín hiệu có ích mà không gây sự cố thứ cấp.

## 18. Troubleshooting: thay level không có hiệu lực như mong đợi

| Hiện tượng | Nguyên nhân có thể | Cách kiểm tra |
| --- | --- | --- |
| POST thành công nhưng GET thấy level cũ | GET vào instance khác, reload config, API đổi sai logger | Gọi instance cụ thể, xem runtime context và source config |
| GET effective DEBUG nhưng không có debug output | Sai code path, appender threshold/filter, sink không hoạt động | Event thử an toàn và kiểm tra từng chặng |
| Có DEBUG trên stdout nhưng không có ở collector | Agent/index chậm, sampling/drop, time range | Query theo event ID, queue/ingest metrics |
| DEBUG quá nhiều từ thư viện ngoài | Scope package/root quá rộng | Thu hẹp logger, khôi phục root |
| Đổi level khiến latency tăng | Sync appender, queue blocking, formatting đắt | CPU/GC/p99, queue depth và drop |
| Sau restart level trở lại INFO | Runtime override không persistent | Theo dõi lifecycle, dùng control plane nếu cần |
| Sau rollback vẫn có DEBUG | Buffered event đến muộn, pod khác còn DEBUG, override khác | Check source timestamp, pod và configured level |
| Đã set INFO nhưng child không theo parent khi parent đổi | Rollback sai, thay `null` bằng `INFO` | Khôi phục inheritance đúng baseline |
| Endpoint `/actuator/loggers` 404 | Không enable/expose, management base path/port khác | Xác minh config đúng version |
| Endpoint trả 401/403 | Chưa xác thực/thiếu quyền/CSRF | Dùng kênh admin được phê duyệt |
| DEBUG lộ secrets | Call site log header/body/exception không kiểm soát | Ngừng override, incident response, sửa nguồn |
| TTL mất tác dụng | Scheduler lỗi hoặc lease ownership sai | Alert stale override, đối chiếu state, rollback thủ công |

### DEBUG còn xuất hiện sau khi rollback có phải thất bại?

Không phải luôn. Một event được tạo **trước rollback** có thể nằm trong async queue và chỉ tới collector **sau rollback**. Cần phân biệt timestamp nguồn với ingestion timestamp, event ID và trạng thái từng pod. Nếu những event **mới được tạo sau rollback** vẫn có DEBUG, mới cần tìm nguồn override, filter, logger khác hoặc pod chưa rollback.

## 19. Quy trình ghi nhận và kiểm soát thay đổi

Với thay đổi khẩn cấp, một change record nên có:

- Incident ID, người yêu cầu, người phê duyệt và người thực hiện.
- Thời điểm bắt đầu, TTL, thời điểm hoàn nguyên thực tế.
- Service, environment, cluster, pod/instance, logger name.
- Configured/effective level **trước, trong và sau**.
- Cơ chế thực hiện (Actuator, Logback admin, config service...).
- Rủi ro dữ liệu nhạy cảm đã được đánh giá, phạm vi truy cập log và retention.
- Metric ảnh hưởng: bytes/s, queue depth, drops, CPU/p99, ingest.
- Bằng chứng level và event tại sink sau thay đổi.
- Kết quả incident và vấn đề phát hiện được từ diagnostic log.
- Mọi trường hợp partial failure, pod không cập nhật, rollback trễ hoặc xung đột operator.

Nếu tổ chức dùng GitOps hoặc config repository để quản lý logging, phân biệt **thay đổi runtime tạm** với **thay đổi cấu hình lâu dài**; đừng lặng lẽ đưa DEBUG tạm thành default của release tiếp theo.

## 20. Checklist ứng cứu nhanh

### Trước khi đổi

- [ ] Có incident/giả thuyết cụ thể và scope logger hẹp.
- [ ] Đã đọc configured/effective baseline, bao gồm `null`/inherit.
- [ ] Xác định backend thật (JUL/Logback/Log4j2) và cơ chế quản trị phù hợp.
- [ ] Đã rà soát nguy cơ log token, PII, raw payload và exception message.
- [ ] Có owner, phê duyệt/break-glass, TTL và kế hoạch rollback.
- [ ] Có metrics CPU, latency, queue/drop, disk/ingest và ngưỡng dừng.
- [ ] Phạm vi instance/cluster và ảnh hưởng autoscaling/restart được ghi rõ.

### Trong khi đổi

- [ ] Chỉ nâng mức cần thiết (thường INFO → DEBUG cho target).
- [ ] Dùng API/control plane xác thực, phân quyền và audit.
- [ ] GET lại configured/effective sau thay đổi.
- [ ] Kiểm tra event test an toàn đi tới sink cần quan sát.
- [ ] Theo dõi tải, chi phí ingest, security guardrails và sai khác các instance.
- [ ] Không mở rộng root/TRACE nếu chưa có đánh giá rõ.

### Sau khi đổi

- [ ] Khôi phục configured baseline chính xác, kể cả inherit/null.
- [ ] Xác minh sau rollback trên mọi instance thuộc scope.
- [ ] Xử lý event buffered đến muộn đúng nghĩa, không nhầm với rollback lỗi.
- [ ] Kiểm tra rủi ro dữ liệu nhạy cảm phát sinh trong khoảng debug.
- [ ] Lưu kết quả điều tra và thời gian/owner/change ID.
- [ ] Nếu công cụ rollback/TTL thất bại, tạo cảnh báo và xử lý ngay, không coi là xong.
- [ ] Đánh giá liệu nên bổ sung metric/trace có cấu trúc để lần sau không cần bật DEBUG rộng.

**Ghi nhớ:** đổi level logging khẩn cấp trong production là **một thay đổi có rủi ro**, không phải thao tác debug vô hại. Hãy ghi baseline, chọn logger/instance nhỏ nhất, đặt TTL, bảo vệ kênh điều khiển, xác minh event thực sự tới sink, theo dõi chi phí và rollback **đúng configured level ban đầu**. Làm như vậy vừa tăng tín hiệu chẩn đoán vừa giữ độ ổn định, bảo mật và khả năng kiểm soát của hệ thống.
