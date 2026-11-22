# Audit thay đổi cấu hình logging trong Java

## 1. Audit thay đổi cấu hình là gì?

**Audit thay đổi cấu hình (configuration change auditing)** là việc tạo, lưu và bảo vệ dấu vết có thể kiểm tra được mỗi khi cấu hình logging được đề nghị thay đổi, thay đổi thành công, bị từ chối, thất bại hoặc được hoàn nguyên.

Trong Java, cấu hình logging không chỉ có `INFO` hay `DEBUG`. Một thao tác có thể sửa **logger level**, bộ lọc, appender/handler, nơi gửi log, quy tắc che dữ liệu, cấu hình logging bất đồng bộ, retention hoặc cơ chế tự nạp lại cấu hình. Những thay đổi này ảnh hưởng trực tiếp đến **khả năng quan sát, bảo mật, lưu trữ và điều tra sự cố**.

Ví dụ: một người vận hành tạm bật DEBUG cho `com.example.payment` để điều tra lỗi. Hệ thống cần ghi nhận người yêu cầu, quyền được kiểm tra, cấu hình trước/sau, lý do, thời điểm, phạm vi, kết quả và thời gian dự kiến hoàn nguyên. Nếu có người cố tắt audit logger hoặc chuyển log sang một máy chủ không được phép, ngay cả **nỗ lực bị từ chối** cũng cần được ghi nhận theo chính sách.

**Cần phân biệt hai khái niệm:**

- **Audit log** là một loại sự kiện nhằm giải trình hoạt động và phục vụ kiểm tra.
- **Audit thay đổi cấu hình logging** là việc ghi bằng chứng cho những thao tác làm thay đổi **chính cơ chế tạo/ghi/xử lý log**.

Điểm khó nằm ở chỗ: nếu hệ thống chỉ dùng pipeline logging đang bị thay đổi để ghi audit, kẻ có quyền cấu hình có thể vô tình hoặc cố ý làm **mất chính bằng chứng về thay đổi đó**. Vì thế cần có luồng kiểm toán độc lập đủ mức theo yêu cầu bảo mật, thay vì chỉ gọi `log.info("config changed")`.

## 2. Vì sao kiểm toán cấu hình logging là yêu cầu bảo mật?

Một thay đổi nhỏ có thể gây hậu quả lớn:

| Thay đổi | Rủi ro | Dữ liệu audit cần có |
| --- | --- | --- |
| `INFO -> OFF` ở logger bảo mật | Mất khả năng ghi nhận sự kiện đáng chú ý | Tên logger, mức trước/sau, actor, kết quả, lý do |
| `INFO -> DEBUG/TRACE` ở production | Ghi thừa payload, rò PII/secret, bão log | Phạm vi, thời hạn, phê duyệt, trạng thái rollback |
| Đổi appender từ file nội bộ sang URL lạ | Chuyển dữ liệu ra nơi không được phép | Loại đích, định danh đích đã kiểm duyệt, quyền phê duyệt |
| Tắt bộ lọc che dữ liệu | Phơi lộ thông tin nhạy cảm trong log | Rule/phiên bản trước–sau, nguồn thay đổi và kết quả |
| Giảm retention hoặc tắt rotation sai cách | Thiếu chứng cứ, mất lịch sử, đầy đĩa | Chính sách retention trước/sau và lý do |
| Bật `neverBlock` hoặc tăng discard | Log có thể bị bỏ khi queue đầy | Backend, ngưỡng, queue policy, mức được ảnh hưởng |
| Nạp lại `logback.xml`/`log4j2.xml` | Cấu hình runtime có thể khác bản duyệt | Nguồn file, phiên bản/hash hợp lệ, xác nhận trạng thái |
| Sửa cấu hình chỉ trên một instance | Hệ thống chạy lệch chính sách | Service, environment, instance, version, rollout ID |

Audit phục vụ điều tra “ai làm gì, khi nào, theo phê duyệt nào và hiệu lực ra sao?”, nhưng **không tự ngăn** hành động không được phép. Ngăn chặn phải thực hiện bằng **authentication, authorization, validation và policy enforcement** trước khi áp dụng thay đổi.

Audit cũng khác với một dòng log chẩn đoán thông thường. Một thông báo không có định danh tác nhân đáng tin cậy hoặc không có bản ghi kết quả sau khi áp dụng sẽ khó giải trình trong sự cố.

## 3. Những thay đổi cần được ghi nhận

Nên xác định danh mục đối tượng và hành động rõ ràng:

1. **Logger level:** thay `TRACE/DEBUG/INFO/WARN/ERROR/OFF`, theo logger/package/root; phân biệt tên mức theo JUL, Logback hoặc Log4j 2.
2. **Sink/appender/handler:** thêm, xóa, thay console/file/network destination, thay encoder/layout, thay logging provider.
3. **Filter và privacy rules:** sửa luật loại sự kiện, mask token, lọc PII, thay cấu hình structured logging.
4. **Routing:** đổi nhánh audit/security, additivity, threshold, marker/MDC routing hoặc đích collector.
5. **Reliability:** đổi async queue capacity, overflow/drop policy, timeout, flush/retention/rotation.
6. **Access và audit controls:** đổi quyền truy cập log, quyền quản trị cấu hình, audit destination, retention, cơ chế bất biến/integrity.
7. **Nguồn cấu hình:** sửa file, config map, hệ thống cấu hình tập trung, biến môi trường ở lần khởi động kế tiếp, system properties hoặc API runtime.
8. **Vận hành:** khởi động với cấu hình mới, reload tự động, đổi cấu hình qua endpoint/JMX, rollback và thay đổi khẩn cấp.

Không phải mọi phép đọc `System.getProperty(...)` là một thay đổi; chỉ ghi audit những thao tác **được xác định là thay đổi hoặc nỗ lực thay đổi**. Ngược lại, thay file trên đĩa nhưng chưa reload cũng cần phân biệt với việc cấu hình **thực sự có hiệu lực** ở JVM.

### 3.1. Bằng chứng cần cho cả thay đổi thành công lẫn thất bại

Tối thiểu hãy phân biệt:

- `REQUESTED`: có yêu cầu, chưa xác định được hợp lệ hay không.
- `DENIED`: bị từ chối do xác thực, phân quyền hoặc policy.
- `VALIDATION_FAILED`: input sai, cấu hình không hợp lệ hoặc không tương thích.
- `APPLY_FAILED`: thao tác đã được phê duyệt nhưng backend không áp dụng thành công.
- `APPLIED`: trạng thái mong muốn đã được áp dụng và xác minh ở phạm vi đã kiểm tra.
- `ROLLED_BACK`: đã thực hiện hoàn nguyên và kiểm chứng theo tiêu chí rõ ràng.
- `PARTIAL`: mới một phần instance hoặc một phần chính sách có hiệu lực; không được báo thành công toàn cục.

Trạng thái `APPLIED` không có nghĩa “đã bền vững sau restart”: có thể chỉ là một thay đổi runtime. Cần thêm thông tin phạm vi, version và thời gian hiệu lực.

## 4. Cấu trúc một audit event có ích

Một sự kiện kiểm toán nên là **dữ liệu cấu trúc (structured event)** với khóa ổn định, thay vì chỉ ghi một câu “Changed settings”.

| Trường | Ý nghĩa |
| --- | --- |
| `eventType` | Loại sự kiện, ví dụ `LOGGING_CONFIG_CHANGE` |
| `changeId` / `requestId` | ID duy nhất để nối yêu cầu, kết quả, rollback |
| `eventTime` | Thời điểm ứng dụng ghi nhận, có timezone rõ (thường UTC) |
| `actorId` | Định danh tác nhân đã **được xác thực**, không lấy mù từ request body |
| `authContext` | Vai trò/quyền hoặc nguồn xác thực đã dùng để quyết định |
| `service`, `environment`, `instanceId` | Phạm vi triển khai của thay đổi |
| `configKey` / `target` | Đối tượng bị đổi, như `logging.level.com.example.orders` |
| `before`, `requested`, `after` | Giá trị trước, giá trị yêu cầu, giá trị sau xác minh |
| `status` | `REQUESTED`, `DENIED`, `APPLIED`, `PARTIAL`, ... |
| `reasonCode` / `ticketId` | Lý do nghiệp vụ, sự cố, thay đổi được phê duyệt |
| `approvalId` / `policyVersion` | Phê duyệt và policy áp dụng (nếu có) |
| `configVersion` | Định danh snapshot/cấu hình được áp dụng |
| `errorCode` | Mã lỗi được chuẩn hóa nếu không thành công |

Ví dụ sự kiện **minh họa**, không chứa dữ liệu bí mật:

```json
{
  "eventType": "LOGGING_CONFIG_CHANGE",
  "changeId": "CHG-2041",
  "eventTime": "2026-11-10T02:00:00Z",
  "actorId": "ops-42",
  "service": "payment-api",
  "environment": "production",
  "instanceId": "payment-api-3",
  "target": "logging.level.com.example.payment",
  "before": "INFO",
  "requested": "DEBUG",
  "after": "DEBUG",
  "status": "APPLIED",
  "reasonCode": "INCIDENT_DIAGNOSIS",
  "ticketId": "INC-2041",
  "approvalId": "APR-142",
  "configVersion": "cfg-v28"
}
```

Trường `eventTime` ở đây là **giá trị ví dụ**, không phải timestamp lấy từ hệ thống thật.

**Không ghi toàn bộ cấu hình không kiểm soát** vào `before`/`after`: đường dẫn hoặc URL appender có thể mang credential, token; cấu hình mask/filter có thể nhắc tới dữ liệu nhạy cảm. Với đối tượng phức tạp, lưu **phiên bản, ID chính sách, những thuộc tính đã allowlist, và tham chiếu đến snapshot được bảo vệ** thay vì nội dung thô.

Có thể giữ cả `observedEffectiveBefore` và `observedEffectiveAfter` nếu backend hỗ trợ, vì giá trị được cấu hình trực tiếp khác với **giá trị đang có hiệu lực do kế thừa**.

### 4.1. Ai là `actor` đáng tin?

Không lấy `actorId` từ chuỗi `userId` do client tự gửi rồi coi đó là bằng chứng danh tính. Một audit record cần lấy tác nhân từ security context đã xác thực: principal của session/JWT đã kiểm chứng, tài khoản dịch vụ, vai trò của automation hoặc định danh deploy pipeline.

Nếu thao tác tự động, có thể cần cả:

- `initiator`: người hoặc hệ thống tạo yêu cầu.
- `executor`: controller/agent thực thi.
- `approval`: người/quy trình phê duyệt.
- `trigger`: thao tác thủ công, startup, reload hay rollback tự động.

Khi nhiều người cùng thay đổi cấu hình, `changeId` và `configVersion` giúp phân biệt các lần cập nhật, không chỉ dựa vào timestamp.

## 5. Quy trình bảo mật từ đề nghị đến áp dụng

Một pipeline thay đổi cấu hình có kiểm toán nên thực hiện:

```text
Authenticated request / approved deployment
                   |
                   v
     Validate identity + authorization + policy
                   |
                   v
       Capture controlled before snapshot
                   |
                   v
      Emit durable attempt/audit event (*)
                   |
                   v
      Apply change through approved API
                   |
                   v
      Read/verify actual effective state
                   |
            +------+------+
            |             |
          success        failure
            |             |
       audit APPLIED   audit FAILED/PARTIAL
            |             |
            +------+------+
                   |
        Alert/rollback/expiry if needed
```

Dấu `(*)`: khi tính chất nghiệp vụ yêu cầu không bỏ mất audit, thao tác phải có chính sách rõ nếu **không ghi/xác nhận** được audit event trước khi thay đổi. Với thay đổi đặc biệt nhạy cảm, có thể chọn **fail-closed** (không cho phép thay đổi nếu không thể ghi audit bền vững). Với một số thay đổi vận hành khẩn cấp, hệ thống có thể cần chính sách khôi phục đã được phê duyệt; không tùy tiện chọn fail-open mà không có bằng chứng và cảnh báo độc lập.

Một chuỗi hợp lý gồm:

1. **Xác thực** người hoặc automation yêu cầu.
2. **Phân quyền ở mức hành động:** ai được bật DEBUG, ai được sửa root, ai được chuyển đích audit, ai được hạ retention?
3. **Kiểm tra allowlist:** level cho phép, package cho phép, thời hạn tối đa, những đích log được phép.
4. **Chụp trạng thái cũ** và version để tránh ghi đè thay đổi đồng thời.
5. **Ghi nỗ lực thay đổi** và mã tương quan ở nơi không dễ bị chính thay đổi đó vô hiệu hóa.
6. **Áp dụng qua một service quản lý cấu hình**, thay vì cho từng controller tự chỉnh backend.
7. **Đọc lại cấu hình hiệu lực**, ghi kết quả `APPLIED`, `FAILED` hoặc `PARTIAL`.
8. **Hoàn nguyên nếu cần**, gắn `rollbackOf` tới ID thay đổi gốc, kiểm tra kết quả rollback.
9. **Đối chiếu với hệ thống triển khai** để phát hiện thay đổi trực tiếp ngoài quy trình.

Một “audit event” chỉ được gửi qua in-memory async queue chưa chắc đã đến nơi lưu. **Đảm bảo ghi nhận** phải được định nghĩa đến tầng nào: nhận vào queue, nhận bởi collector hay được lưu bền vững có xác nhận. Không gọi tất cả những trạng thái đó là “audit thành công”.

## 6. Ví dụ Java 17 độc lập: ghi nhận nỗ lực và kết quả thay đổi mức log

Ví dụ dùng **`java.util.logging` (JUL)** có sẵn trong JDK. Nó minh họa việc:

- Chỉ cho phép actor giả lập `ops-admin` thay level.
- Chỉ chấp nhận hai level `INFO` và `FINE` theo policy ví dụ.
- Phát sự kiện `CONFIG_ATTEMPT` rồi `CONFIG_RESULT`, gồm ID, actor, target, level trước/sau và trạng thái.
- Giữ **logger audit riêng**, không đổi level của nó khi thay đổi logger nghiệp vụ.
- Chỉ ghi dữ liệu cố định để kết quả chạy có thể kiểm chứng.

Lưu tệp **`ConfigChangeAuditDemo.java`**:

```java
import java.util.Set;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public class ConfigChangeAuditDemo {
    private static final Set<String> ALLOWED = Set.of("INFO", "FINE");

    public static void main(String[] args) {
        Logger service = Logger.getLogger("demo.orders");
        service.setLevel(Level.INFO);

        Logger audit = Logger.getLogger("demo.config-audit");
        audit.setLevel(Level.INFO);
        audit.setUseParentHandlers(false);

        Handler stdout = new Handler() {
            {
                setLevel(Level.ALL);
            }

            @Override
            public void publish(LogRecord record) {
                if (record != null && isLoggable(record)) {
                    System.out.println(record.getLevel().getName()
                            + " " + record.getMessage());
                }
            }

            @Override
            public void flush() {
                System.out.flush();
            }

            @Override
            public void close() {
                flush(); // Không đóng System.out dùng chung.
            }
        };

        audit.addHandler(stdout);
        try {
            change(service, audit, "chg-101", "ops-admin", "FINE");
            change(service, audit, "chg-102", "guest", "OFF");
            System.out.println("Final service level: "
                    + service.getLevel().getName());
        } finally {
            audit.removeHandler(stdout);
            stdout.close();
        }
    }

    private static void change(Logger service, Logger audit,
                               String id, String actor, String desired) {
        String before = service.getLevel().getName();

        audit.info("CONFIG_ATTEMPT id=" + id
                + " actor=" + actor
                + " target=demo.orders before=" + before
                + " requested=" + desired);

        if (!"ops-admin".equals(actor) || !ALLOWED.contains(desired)) {
            audit.warning("CONFIG_RESULT id=" + id
                    + " status=DENIED after=" + before);
            return;
        }

        service.setLevel(Level.parse(desired));
        String after = service.getLevel().getName();

        audit.info("CONFIG_RESULT id=" + id
                + " status=APPLIED after=" + after);
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```bash
javac ConfigChangeAuditDemo.java
java ConfigChangeAuditDemo
```

Kết quả **`stdout`**:

```text
INFO CONFIG_ATTEMPT id=chg-101 actor=ops-admin target=demo.orders before=INFO requested=FINE
INFO CONFIG_RESULT id=chg-101 status=APPLIED after=FINE
INFO CONFIG_ATTEMPT id=chg-102 actor=guest target=demo.orders before=FINE requested=OFF
WARNING CONFIG_RESULT id=chg-102 status=DENIED after=FINE
Final service level: FINE
```

Giải thích:

- Logger nghiệp vụ `demo.orders` bắt đầu ở `INFO`; lần thay đổi đầu được policy minh họa cho phép và đặt thành `FINE`.
- Lần thứ hai dùng actor không được phép và yêu cầu `OFF`; policy từ chối, giữ `FINE`. Sự kiện `DENIED` vẫn được ghi vào audit.
- `audit.setUseParentHandlers(false)` loại đường gửi lên root handler, giúp ví dụ không in trùng. Handler riêng xuất ra `stdout` và có formatter cố định, nên các dòng trên không phụ thuộc timestamp.
- `audit` không nằm trong logger nghiệp vụ đang bị thay level; nó được cấu hình riêng để việc thay level của `service` không trực tiếp tắt audit ở ví dụ.
- `Set.of(...)` dùng để biểu diễn **danh sách level được phép**, không phải quy tắc bắt buộc của JUL.

**Giới hạn của ví dụ:** `actor` được truyền bằng chuỗi cố định nhằm minh họa, **không phải xác thực thật**. Chương trình không có authorization service, audit sink bền vững, xử lý lỗi I/O, khóa chống cập nhật đồng thời hoặc rollback. `System.out` và một handler in-memory **không** bảo đảm không thể sửa/xóa bằng chứng. Trong production, identity phải đến từ security context đáng tin và audit phải được xuất tới hệ thống độc lập đủ mức.

### 6.1. Vì sao cần kiểm tra lại cấu hình sau khi áp dụng?

Đọc `service.getLevel()` trả mức **được gán trực tiếp** tại logger JUL. Nếu giá trị `null`, logger có thể đang **kế thừa** mức từ cha. Một hệ thống audit cần phân biệt `configuredBefore` với `effectiveBefore`, không ghi nhầm `null` thành “không bật log”.

Trong ví dụ, ta đã `setLevel(Level.INFO)` trước nên `getLevel()` không null. Với cấu hình thực, cần đọc theo API backend và mô hình kế thừa tương ứng. Cũng phải xem cả filter và handler/appender: đặt logger thành DEBUG/FINE chưa chắc sink đã nhận được những sự kiện đó.

### 6.2. Nếu ghi audit thất bại thì sao?

Ví dụ dùng `Handler` đơn giản để dễ học, không cho thấy chính sách lỗi. Trong production:

- Nếu **audit event trước thay đổi** phải được lưu bền vững, endpoint quản trị cần đợi acknowledgment theo hợp đồng của audit service, hoặc từ chối thao tác khi không nhận được.
- Nếu thao tác đã áp dụng nhưng **ghi result thất bại**, đừng tự coi như giao dịch đã hoàn chỉnh: phát metric/cảnh báo độc lập, ghi nhận trạng thái chưa xác định và cho phép đối soát.
- Nếu thay đổi cấu hình thành công cục bộ nhưng rollout thất bại ở instance khác, ghi `PARTIAL` kèm danh sách phạm vi đã/không áp dụng.
- Không gửi thông báo lỗi của audit appender **vào lại chính appender đó** theo vòng lặp đệ quy.

Tài liệu của hệ thống phải nêu rõ khi nào chọn fail-closed và quy trình xử lý khẩn cấp nếu audit service không hoạt động.

## 7. Tách riêng đường audit khỏi logging đang được thay đổi

Một lỗi thiết kế phổ biến:

```java
Logger log = Logger.getLogger("demo.orders");
log.setLevel(Level.OFF);
log.info("Changed logger level to OFF"); // Sự kiện bị chặn.
```

Đoạn trên là **mã minh họa tích hợp**, không phải chương trình độc lập. Sau `setLevel(Level.OFF)`, chính logger đó có thể không phát dòng thông báo về việc đã bị tắt.

Với thay đổi đặc biệt nhạy cảm, nên tạo audit qua **control plane** hoặc **audit service** không bị vô hiệu hóa bởi cấu hình của logger mục tiêu:

```text
Management API
      |
      +-- independent audit writer --> protected remote sink
      |
      +-- apply logging change ----> application logging backend
```

Điểm quan trọng là **quyền thay đổi backend** và **quyền xóa/sửa trail** không được gộp tùy tiện vào một tài khoản. Một tài khoản có quyền điều chỉnh DEBUG ở logger ứng dụng không nên mặc định có quyền tắt audit pipeline, hạ retention hoặc xóa file kiểm toán.

Đặt một logger `audit` riêng trong cùng JVM là bước tách **logic**, chưa phải tách **miền lỗi**: process crash, ổ đĩa lỗi hoặc tài khoản quyền cao bị xâm nhập vẫn có thể tác động tới cả hai. Nếu cần chống sửa/xóa, dùng nơi lưu độc lập có quyền riêng, append-only hoặc immutable retention, bằng chứng integrity và kiểm soát truy cập.

## 8. Cấu hình Logback để gửi audit event sang appender riêng

Với ứng dụng dùng **SLF4J + Logback Classic**, code nghiệp vụ có thể ghi qua `org.slf4j.Logger`, còn tệp `logback.xml` định tuyến một logger chuyên dụng sang file audit.

Ví dụ `src/main/resources/logback.xml`:

```xml
<configuration>
    <appender name="APPLICATION"
              class="ch.qos.logback.core.ConsoleAppender">
        <encoder>
            <pattern>%d{yyyy-MM-dd'T'HH:mm:ss.SSS} %-5level %logger - %msg%n</pattern>
        </encoder>
    </appender>

    <appender name="CONFIG_AUDIT"
              class="ch.qos.logback.core.FileAppender">
        <file>logs/config-audit.log</file>
        <append>true</append>
        <encoder>
            <pattern>%d{yyyy-MM-dd'T'HH:mm:ss.SSS} %-5level %logger - %msg%n</pattern>
        </encoder>
    </appender>

    <logger name="com.example.security.LoggingConfigAudit"
            level="INFO" additivity="false">
        <appender-ref ref="CONFIG_AUDIT"/>
    </logger>

    <root level="INFO">
        <appender-ref ref="APPLICATION"/>
    </root>
</configuration>
```

Ứng dụng phải có dependency Logback phù hợp và thư mục `logs` cần tồn tại/có quyền ghi; cách nạp cấu hình phụ thuộc deployment. Đây là **ví dụ định tuyến**, không phải một hệ thống audit chống sửa đổi.

- `CONFIG_AUDIT` là đường riêng cho những event của logger tên `com.example.security.LoggingConfigAudit`.
- `additivity="false"` ngăn gửi lại audit event lên appender root `APPLICATION`; tránh log trùng hoặc vô tình phát audit event qua sink không được phép.
- `append=true` yêu cầu ghi nối vào file, **không** làm file thành immutable, không có xác nhận từ collector và không chứng minh chống chỉnh sửa.
- `level="INFO"` trên logger audit giúp nó có cấu hình level độc lập với root, nhưng một người có quyền sửa toàn bộ file Logback có thể vẫn thay đổi hoặc gỡ appender này.
- Tính bảo mật còn phụ thuộc quyền đọc/ghi file, log rotation, retention, encryption, hệ thống thu thập và nơi lưu cuối cùng.

Ví dụ code tích hợp với SLF4J:

```java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

// Trong lớp chịu trách nhiệm quản trị cấu hình:
private static final Logger CONFIG_AUDIT =
        LoggerFactory.getLogger(
                "com.example.security.LoggingConfigAudit");

// Chỉ ghi các trường đã xác thực/kiểm duyệt:
CONFIG_AUDIT.info(
        "CONFIG_RESULT changeId={} actor={} key={} status={}",
        changeId, authenticatedActorId, approvedConfigKey, status);
```

Đây là **đoạn tích hợp**, không phải Java class độc lập; cần khai báo biến được dùng, một class chứa trường `private static final` và dependency SLF4J. Tham số hóa giúp tránh nối chuỗi không cần thiết, nhưng **không tự thoát ký tự xuống dòng hoặc che secret**. Nên sử dụng encoder structured log phù hợp và ràng buộc kích thước, ký tự đầu vào.

**Quan trọng:** file audit trong cùng JVM và cùng máy có thể bị đổi/xóa bởi tác nhân có đủ quyền. Với kiểm toán an ninh nghiêm túc, control plane nên gửi thêm bản ghi tới hệ thống kiểm toán độc lập hoặc kho lưu immutable có kiểm soát quyền riêng.

## 9. Audit các kiểu thay đổi cấu hình khác nhau

### 9.1. Thay level runtime qua API

Đối với JUL, code có thể dùng `Logger.setLevel(...)`. Với Logback Classic, dùng API backend như `ch.qos.logback.classic.Logger.setLevel(...)`. Log4j 2 có cơ chế cấu hình mức log riêng (ví dụ API `Configurator` phù hợp phiên bản). Spring Boot có hệ thống `LoggingSystem`/management endpoint theo phiên bản và cấu hình triển khai.

Đối với mỗi thao tác, cần **đặt đường thay đổi trong một service quản trị duy nhất**:

1. Nhận principal từ security context.
2. Kiểm tra quyền trên logger/config key cụ thể.
3. Ghi `CONFIG_ATTEMPT` độc lập.
4. Áp dụng qua backend đúng loại.
5. Kiểm tra lại trạng thái hiệu lực ở backend.
6. Ghi `CONFIG_RESULT` và lịch hoàn nguyên nếu thay đổi chỉ được bật tạm thời.

Nếu để nhiều nơi gọi `setLevel()` trực tiếp, service trung tâm khó biết đã có thao tác nào và khó audit đầy đủ. Với Spring Boot Actuator hoặc endpoint tương tự, phải bảo vệ xác thực/phân quyền và thu thập cả lịch sử thay đổi ở control plane; không coi endpoint quản trị tự động là một hệ thống audit hoàn chỉnh.

### 9.2. Sửa file cấu hình / reload tự động

Các file như `logging.properties`, `logback.xml`, `logback-spring.xml`, `log4j2.xml` có thể được nạp khi startup hoặc reload. Thay đổi file trên đĩa **không nhất thiết đã được áp dụng vào JVM**.

Có thể ghi hai loại sự kiện riêng:

- **`CONFIG_SOURCE_CHANGED`**: một nguồn cấu hình đã thay đổi, ví dụ Git commit mới, phiên bản config map mới hoặc hash nội dung cấu hình được phê duyệt.
- **`CONFIG_RUNTIME_APPLIED`**: một JVM/instance xác nhận đã nạp và áp dụng phiên bản tương ứng.

Nếu appender/file bị sửa ngoài quy trình deployment, controller cần phát hiện **drift** giữa trạng thái đang chạy và cấu hình được phê duyệt; một audit log của chính backend có thể không quan sát được mọi đường sửa file. Tích hợp nguồn sự thật như GitOps/change-management system với audit từ ứng dụng và giám sát file/config thực tế.

### 9.3. System properties và biến môi trường

`-Dlogging.level...`, `-Dlogback.configurationFile=...` hoặc các giá trị môi trường thường được đọc lúc khởi động (tùy framework), không tự động reload mỗi khi `System.setProperty` thay đổi.

Audit startup nên ghi **version cấu hình được sử dụng thực tế** và danh sách thuộc tính đã được kiểm duyệt. Không dump toàn bộ `System.getProperties()` hay environment variables vào log vì có thể chứa credential và thông tin hạ tầng nhạy cảm.

Nếu đổi launcher/manifest để restart với cấu hình mới, cần liên kết `changeId` từ pipeline deployment với phiên bản cấu hình của từng instance sau khởi động. Nếu đổi system property trong process nhưng backend không nhận lại, trạng thái chỉ là **property changed**, không được gắn `APPLIED` cho logger.

### 9.4. Thay đổi phân tán nhiều instance

Khi hệ thống có nhiều JVM, một bản cập nhật cấu hình có thể thành công ở instance A nhưng thất bại ở B. Không dùng một log `APPLIED` trên một node để kết luận toàn cluster đã đồng nhất.

Nên ghi một event **yêu cầu cấp cụm** và các event **kết quả theo instance** với cùng `changeId` hoặc `rolloutId`. Sau đó controller tổng hợp:

```text
CHG-2041
  |- instance-a: APPLIED cfg-v28
  |- instance-b: APPLIED cfg-v28
  |- instance-c: APPLY_FAILED cfg-v27
  \- overall: PARTIAL
```

Nếu hệ thống thực sự cần thay đổi nguyên tử trên nhiều node, phải thiết kế phối hợp/rollback riêng; một API `setLevel()` ở từng JVM không tạo distributed transaction.

## 10. Bảo vệ tính toàn vẹn và độ sẵn có của audit trail

Audit trail cần chống **mất, sửa, xóa, xem trái phép** theo threat model cụ thể:

| Mục tiêu | Biện pháp thường dùng | Giới hạn cần hiểu |
| --- | --- | --- |
| Không dễ bị tắt bởi cấu hình đang thay | Control-plane audit writer hoặc sink tách biệt | Cùng host/credential vẫn có thể chung điểm lỗi |
| Bảo toàn khi JVM crash | Ghi ngoài JVM hoặc gửi có xác nhận tới durable service | “Đã enqueue vào RAM” chưa đủ |
| Chống sửa/xóa | Append-only/immutable retention, quyền riêng, phân tách nhiệm vụ | Phải kiểm tra việc enforce và quản lý khóa/quyền |
| Phát hiện thay đổi trái phép | Chữ ký/hash chain, xác thực bản ghi, đối soát snapshot | Hash đơn thuần lưu cùng file không chống được sửa cả file lẫn hash |
| Bảo vệ nội dung | TLS khi truyền, mã hóa và kiểm soát truy cập nơi lưu | Encryption không thay thế authorization |
| Đối soát sau sự cố | ID duy nhất, sequence/version, điểm xác nhận (ack) | Retry có thể dẫn tới duplicate; cần idempotency |
| Tuân thủ retention | Chính sách theo nhóm log và quy định áp dụng | Retention không nên bị tùy tiện giảm từ cùng quyền quản trị logging |

**Hash chain/chữ ký** hữu ích khi có cách quản lý khóa và điểm neo bằng chứng độc lập; nếu tài khoản có thể thay cả log lẫn chuỗi hash, kiểm tra cục bộ không còn đáng tin. Đồng bộ đồng hồ hỗ trợ phân tích thời điểm nhưng không dùng timestamp làm khóa duy nhất để chứng minh thứ tự. Cần lưu timestamp sự kiện, thời gian collector nhận và ID/sequence khi phù hợp.

Trong ứng dụng, xử lý audit failure cần chính sách riêng: nếu đây là thay đổi cấu hình mang tính bảo mật bắt buộc ghi bằng chứng, có thể phải **từ chối thay đổi khi hệ thống audit không xác nhận được**. Nếu là trạng thái khẩn cấp cần khôi phục dịch vụ, ngoại lệ phải được quy định, phân quyền và giám sát trước, không để mọi người tự chuyển sang fail-open.

## 11. Giữ bí mật trong chính bản ghi kiểm toán

Audit có giá trị cho điều tra, nhưng có thể trở thành nguồn lộ dữ liệu nếu ghi quá nhiều:

- **Không ghi password, access token, khóa bí mật**, thông tin định danh nhạy cảm không cần thiết hoặc chuỗi kết nối đầy đủ chứa credential trong `before`/`after`.
- Nếu thay URL sink, chỉ ghi **scheme/host đã kiểm duyệt**, resource ID hoặc tên policy; không in query string có token.
- Nếu thay cấu hình mask/redaction, ghi **ID và phiên bản rule**; tránh ghi dữ liệu mẫu nhạy cảm được dùng để kiểm thử.
- Không đặt toàn bộ text user gửi vào `reason` mà không giới hạn kích thước và làm sạch ký tự điều khiển.
- Bản ghi dạng text cần chống **log injection**: xuống dòng, escape sequences và chuỗi giả mạo level/timestamp có thể khiến một input tạo cảm giác như nhiều event. Ưu tiên encoder JSON/structured log và kiểm tra input.
- Không đưa requestId, actorId hoặc changeId có cardinality lớn vào **metric labels**; các trường này phù hợp ở audit record hơn là nhãn đo đạc.
- Áp dụng chính sách quyền đọc audit trail (security/compliance) độc lập với quyền đọc log debug thông thường.

**Không nên coi hash của một giá trị bí mật là cách che an toàn tuyệt đối:** giá trị có entropy thấp có thể bị suy đoán qua dictionary attack. Nếu cần so sánh phiên bản, ưu tiên ID chính sách/snapshot được quản lý, không tiết lộ nội dung secret.

## 12. Theo dõi và đối soát thay đổi cấu hình

Ngoài lưu event, cần cảnh báo các sự kiện bất thường:

- Root logger hoặc audit/security logger bị đặt `OFF`, giảm retention bất ngờ, tắt redaction, thêm appender trỏ ra ngoài.
- Thay đổi DEBUG/TRACE ở production kéo dài hơn TTL/approval.
- Nhiều lần `DENIED` từ một tác nhân hoặc một endpoint.
- Runtime config khác với phiên bản đã phê duyệt.
- Rollout `PARTIAL` kéo dài hoặc cấu hình của instance không đồng nhất.
- Không có audit event cho một thay đổi được phát hiện từ Git, config API, file watcher hoặc tool quản trị.
- Audit writer/collector không nhận, ack chậm, queue đầy hoặc số event chưa xác nhận tăng cao.

Các metric có thể được instrument như:

| Metric gợi ý | Ý nghĩa |
| --- | --- |
| `logging_config_change_attempts_total{result,type}` | Yêu cầu và kết quả theo nhóm |
| `logging_config_audit_write_failures_total` | Số lỗi khi ghi/xác nhận audit |
| `logging_config_audit_delivery_lag_seconds` | Độ trễ chuyển audit tới đích |
| `logging_config_drift_instances` | Số instance có cấu hình lệch chuẩn |
| `logging_config_temporary_overrides` | Số override còn hiệu lực |
| `logging_config_unapproved_changes_total` | Thay đổi không có approval hợp lệ |

Đây là **tên metric gợi ý**, không phải các metric có sẵn trong mọi logging framework. Chúng không nên phụ thuộc hoàn toàn vào chính appender đang lỗi. Cần thêm health check hoặc đường alert độc lập cho audit pipeline.

Một báo cáo đối soát có thể nối **control plane request → approvals → deployment version → per-instance effective config → audit receipts**. Nhờ vậy người vận hành biết thay đổi nào chưa có bằng chứng, thay vì chỉ tìm text `"changed"` trong application logs.

## 13. Các ca kiểm thử quan trọng

Kiểm thử audit thay đổi cấu hình cần bao gồm cả đường thành công và đường bị tấn công:

| Trường hợp | Kỳ vọng |
| --- | --- |
| Người được phép bật DEBUG có TTL | Có attempt + result, before/after, reason, expiry và rollback đúng |
| Tài khoản không đủ quyền yêu cầu `OFF` | Bị từ chối, cấu hình không thay đổi, có `DENIED` audit |
| Tên logger không hợp lệ | `VALIDATION_FAILED`, không có thay đổi ngoài phạm vi |
| Sửa redaction rule hoặc audit sink | Yêu cầu phê duyệt mạnh hơn và ghi nhận ở đường độc lập |
| Audit service không khả dụng | Hành vi đúng fail-closed hoặc emergency policy đã định |
| Backend báo áp dụng lỗi | Có `APPLY_FAILED`, không báo `APPLIED` |
| Nhiều thread đổi cùng logger | Có kiểm soát race/version; audit thể hiện thứ tự hoặc conflict |
| Reload file sau thay đổi runtime | Có event cho reload, trạng thái sau cùng được xác minh |
| Rollout nhiều instance chỉ thành công một phần | `PARTIAL`, có kết quả theo từng instance |
| Input chứa newline, ANSI escape, token | Không phá format audit, không lộ secret |
| Process crash trước khi ghi result | Có khả năng đối soát từ attempt và trạng thái thực tế |
| Collector nhận trùng do retry | Có `changeId`/event ID và cơ chế nhận diện duplicate |
| Thay đổi ngoài công cụ quản trị | Drift detection phát hiện, có cảnh báo và điều tra |

Trong test tích hợp, không chỉ kiểm tra `logger.isLoggable(...)` hoặc `getLevel()`. Cần kiểm tra **kết quả ghi vào audit sink**, khả năng đọc lại, bảo toàn trường dữ liệu, quyền truy cập và hành vi khi sink ngắt kết nối.

### 13.1. Kiểm thử điều kiện đua và rollback

Giả sử hai yêu cầu gần như đồng thời:

```text
T1 đọc before=INFO; muốn DEBUG
T2 đọc before=INFO; muốn WARN
T1 áp dụng DEBUG
T2 áp dụng WARN
```

Nếu audit của T1 ghi `after=DEBUG` và của T2 ghi `after=WARN`, cả hai log riêng có thể đúng tại từng thời điểm nhưng **không đủ để suy ra cấu hình cuối chỉ từ thứ tự nhận log**. Cần một controller có serialization, version check hoặc optimistic concurrency và nguồn sự thật về trạng thái thực.

Với override tạm, lịch hoàn nguyên phải gắn với `changeId` hoặc phiên bản ban đầu. Không tự khôi phục `INFO` nếu sau đó đã có một thay đổi hợp lệ khác sang `WARN`, vì rollback mù có thể ghi đè cấu hình mới.

## 14. Những sai lầm thường gặp

### Sai lầm 1: Ghi audit bằng logger đang bị tắt

Nếu code đặt logger `OFF` rồi gọi `logger.info("Logger disabled")`, thông báo có thể không được phát ra. Audit phải có kênh độc lập với mục tiêu thay đổi.

### Sai lầm 2: Chỉ ghi dòng “User X changed logging”

Thiếu `changeId`, target, trước/sau, xác minh và kết quả. Không thể biết thay đổi có thành công hay không hoặc có khôi phục được hay không.

### Sai lầm 3: Tin vào `actorId` từ request body

Một người có thể tự khai là admin. Danh tính audit phải đến từ authentication context và cần ghi kết quả kiểm tra authorization tương ứng.

### Sai lầm 4: Coi `FileAppender append=true` là tamper-proof

Append chỉ là kiểu mở file để ghi nối. Nếu tài khoản có quyền chỉnh sửa/xóa, audit trail vẫn có thể bị thay thế. Cần phân quyền và lưu trữ bảo vệ theo threat model.

### Sai lầm 5: Ghi tất cả properties vào audit

Dễ rò credential, đường dẫn nhạy cảm hoặc dữ liệu hệ thống. Ghi allowlist thay đổi đã kiểm duyệt, version/snapshot ID và tham chiếu tới kho cấu hình được bảo vệ.

### Sai lầm 6: Ghi `APPLIED` ngay khi nhận HTTP 200 từ endpoint

HTTP 200 của controller chưa chắc đồng nghĩa tất cả instance đã nhận cấu hình hoặc backend đã bật hiệu lực. Phải xác minh trạng thái ở đúng phạm vi cần cam kết.

### Sai lầm 7: Đổi cấu hình chỉ ở runtime nhưng không theo dõi restart

Sau khi restart, backend có thể nạp lại file cũ. Audit nên chỉ rõ runtime override có TTL hay đã cập nhật nguồn cấu hình bền vững.

### Sai lầm 8: Không audit thao tác bị từ chối

Các lần cố đổi logger audit sang `OFF` hoặc bật DEBUG trái phép có thể là tín hiệu tấn công. Ghi `DENIED` theo policy mà không để attacker tự chèn nội dung nguy hiểm vào log.

### Sai lầm 9: Cùng một tài khoản vừa thay chính sách vừa xóa audit

Nếu không có phân tách nhiệm vụ và hệ thống lưu độc lập, bằng chứng có thể bị thay đổi bởi chính người thao tác. Quyền vận hành logger và quyền quản trị audit trail nên được tách.

### Sai lầm 10: Có audit event trong queue nên coi là an toàn

Async queue in-memory có thể mất dữ liệu khi crash, queue đầy hoặc sink lỗi. Mức đảm bảo phải dựa trên acknowledgment/durability thực tế, không phải chỉ kết quả enqueue.

## 15. Checklist thiết kế trước production

- [ ] Xác định những cấu hình logging nào là **security-sensitive** và mức phê duyệt cần thiết.
- [ ] Dùng một API/control plane quản trị có authentication và authorization theo phạm vi logger/config.
- [ ] Ghi cả **attempt và result**, kể cả `DENIED`/`FAILED`/`PARTIAL`/`ROLLED_BACK`.
- [ ] Lưu `changeId`, actor đã xác thực, target, trạng thái trước/sau, reason, approval, environment, instance và version.
- [ ] Không ghi secret, token, URL chứa credential hoặc toàn bộ cấu hình không được kiểm duyệt.
- [ ] Tách audit writer/sink khỏi logger và cấu hình đang được thay đổi theo threat model.
- [ ] Định nghĩa durability/ack, quyền truy cập, retention, phát hiện sửa/xóa và policy khi audit sink lỗi.
- [ ] Với DEBUG/TRACE production, yêu cầu phạm vi hẹp, TTL và kế hoạch hoàn nguyên có version check.
- [ ] Kiểm chứng trạng thái hiệu lực của backend sau apply, reload và restart.
- [ ] Có kết quả theo instance và tổng hợp `PARTIAL` nếu rollout phân tán.
- [ ] Đối soát Git/change approvals/config inventory với audit receipts và drift detection.
- [ ] Test tính đúng đắn, thiếu quyền, lỗi ghi audit, log injection, race, crash, retry và duplicate.
- [ ] Có alert độc lập khi audit pipeline bị tắt, tắc nghẽn hoặc thiếu event.

**Kết luận:** Audit thay đổi cấu hình logging không chỉ là ghi thêm một dòng INFO. Đó là một quy trình **xác thực và cho phép thay đổi → lưu dấu vết nỗ lực → áp dụng → xác minh kết quả → bảo vệ và đối soát bằng chứng**. Với Java, cần hiểu cơ chế backend cụ thể (JUL, Logback, Log4j 2, Spring Boot), mức hiệu lực và nơi ghi log; với yêu cầu an ninh, cần bảo đảm đường kiểm toán không bị chính thay đổi logging hoặc lỗi queue/collector vô hiệu hóa.
