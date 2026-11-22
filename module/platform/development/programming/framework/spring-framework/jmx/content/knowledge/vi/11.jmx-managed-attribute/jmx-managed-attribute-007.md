# Không dùng attribute để lộ dữ liệu nhạy cảm

## 1. Vì sao ManagedAttribute có thể trở thành điểm rò rỉ dữ liệu?

Trong Spring Framework JMX, `@ManagedAttribute` công bố một getter hoặc setter như một **JMX attribute**. Đây là một cơ chế hữu ích cho quản trị và quan sát ứng dụng: người vận hành có thể đọc số lượng kết nối, trạng thái cache, ngưỡng cảnh báo hoặc số tác vụ đang chạy từ JConsole và các công cụ JMX khác.

Nhưng chính khả năng đọc giá trị runtime tạo ra một rủi ro: **một getter tưởng như vô hại có thể đưa secret hoặc dữ liệu nhạy cảm ra ngoài phạm vi vốn được phép biết**.

Ví dụ một bean chứa:

- mật khẩu database, API key, access token và refresh token;
- private key, client secret hoặc thông tin định danh tài khoản dịch vụ;
- connection string có credential nhúng;
- thông tin cá nhân của khách hàng, nội dung đơn hàng hoặc payload người dùng;
- session ID, cookie, header `Authorization` hoặc dữ liệu xác thực;
- cấu hình nội bộ có thể giúp kẻ tấn công hiểu hệ thống, như danh sách endpoint quản trị chưa được bảo vệ.

Nếu một getter trả trực tiếp các giá trị đó và được export dưới dạng JMX attribute, client có khả năng truy cập MBean có thể đọc chúng qua `MBeanServerConnection.getAttribute(...)`. Dữ liệu có thể xuất hiện trong giao diện đồ họa, script giám sát, log hoặc bản dump cấu hình.

**Nguyên tắc trung tâm:** JMX là mặt phẳng quản trị có đặc quyền. Mọi attribute được export phải được xem như một phần của API quản trị, và chỉ được công bố khi có mục đích vận hành rõ ràng.

## 2. Đường đi của dữ liệu từ Spring bean tới JMX client

Mô hình đơn giản:

```text
   Spring-managed bean
       |
       | @ManagedAttribute trên getter
       v
   AnnotationMBeanExporter / MBeanExporter
       |
       | xây dựng metadata + đăng ký MBean
       v
   MBeanServer (ObjectName, MBeanInfo)
       |
       | getAttribute(...)
       v
   JConsole / JMX client / monitoring tool
       |
       +--> hiển thị, thu thập, ghi log, lưu cache, chuyển tiếp
```

Khi công bố attribute, người phát triển thường chỉ nhìn thấy getter trong code Java. Nhưng ở phía JMX client, getter trở thành một phần của **giao diện truy cập từ bên ngoài bean**, có thể được khám phá qua `MBeanInfo`.

Với một MBean đã đăng ký, client có thể đọc metadata:

```java
MBeanInfo info = connection.getMBeanInfo(objectName);

for (MBeanAttributeInfo attribute : info.getAttributes()) {
    System.out.println(
        attribute.getName() + " readable=" + attribute.isReadable()
    );
}
```

Metadata không nhất thiết tiết lộ giá trị; nhưng nếu một attribute đọc được và connector/client có quyền truy cập, client có thể yêu cầu giá trị thật.

**Việc dữ liệu không hiện trong UI nghiệp vụ không có nghĩa nó không bị công bố.** Một getter chỉ phục vụ “debug” nhưng được export qua JMX vẫn là một đường đọc dữ liệu riêng cần kiểm soát.

## 3. Ví dụ không an toàn: export toàn bộ cấu hình

Xét bean sau:

```java
import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedResource;
import org.springframework.stereotype.Component;

@Component
@ManagedResource(objectName = "demo.config:type=PaymentConfig")
public class PaymentConfigMonitor {

    private final String apiKey;
    private final String endpoint;

    public PaymentConfigMonitor(PaymentProperties properties) {
        this.apiKey = properties.getApiKey();
        this.endpoint = properties.getEndpoint();
    }

    @ManagedAttribute
    public String getApiKey() {
        return apiKey; // KHÔNG AN TOÀN
    }

    @ManagedAttribute
    public String getEndpoint() {
        return endpoint;
    }
}
```

Khi bean được export đúng cấu hình, `ApiKey` là một attribute có thể đọc. Công cụ JMX không cần đi qua endpoint xác thực nghiệp vụ của hệ thống thanh toán để lấy giá trị đó.

Dù `apiKey` là `private final` và không có setter, điều này **không bảo vệ giá trị khỏi JMX**. Các modifier Java điều khiển truy cập trong code; `@ManagedAttribute` chủ động tạo một giao diện quản trị mới.

Đặc biệt, **read-only không có nghĩa bí mật**. Thuộc tính chỉ đọc ngăn việc đặt giá trị qua JMX, nhưng vẫn cho phép lấy giá trị. Đối với secret, chiều đọc thường là rủi ro lớn nhất.

Nếu connection string có dạng:

```text
jdbc:postgresql://db.internal:5432/orders?user=service&password=SECRET
```

thì export nguyên chuỗi cũng có thể tiết lộ credential, kể cả khi tên getter chỉ là `getJdbcUrl()`. Cần kiểm tra **nội dung thực tế**, không chỉ tên method.

## 4. Phân loại dữ liệu trước khi công bố attribute

Một cách thiết kế hữu ích là chia giá trị theo mục đích vận hành.

| Loại dữ liệu | Ví dụ | Cách xử lý khi thiết kế JMX |
|---|---|---|
| Chỉ số vận hành không nhạy cảm | Số request, queue depth, cache hit count | Có thể export nếu cần |
| Trạng thái tổng hợp | `READY`, `DEGRADED`, `AUTH_CONFIGURED` | Ưu tiên export dạng trạng thái |
| Ngưỡng cấu hình | Timeout, pool size, warning threshold | Chỉ export nếu có quyền và validation phù hợp |
| Định danh hạ tầng | Hostname, endpoint, database name | Xem xét độ nhạy và nhu cầu; không mặc định an toàn |
| Credential/secret | Password, access token, API key, private key | Không export giá trị |
| Dữ liệu người dùng | Email, số điện thoại, nội dung đơn hàng | Tránh export; dùng thống kê tổng hợp |
| Dữ liệu phiên | Session ID, cookie, Authorization header | Không export giá trị |
| Dữ liệu lỗi | Exception message, raw payload, request body | Lọc và giới hạn trước khi export |

Không có quy tắc “mọi URL đều an toàn” hoặc “mọi username đều nhạy cảm như mật khẩu”. Mức độ nhạy cảm phụ thuộc ngữ cảnh, mô hình đe dọa và yêu cầu vận hành. Nhưng với secret và dữ liệu xác thực, thiết kế mặc định nên là **không công bố giá trị dưới bất kỳ attribute nào**.

Một bản ghi JSON chứa object cấu hình cũng cần được xem xét từng trường. Export `Map<String, Object>` hoặc DTO không tự làm dữ liệu an toàn hơn chỉ vì không có getter `getPassword()` riêng.

## 5. Thay secret bằng thông tin trạng thái có ích

Thường người vận hành không cần biết **giá trị** API key. Họ chỉ cần biết:

- key đã được cấu hình hay chưa;
- key có hết hạn không, nếu ứng dụng biết ngày hết hạn;
- lần kiểm tra xác thực gần nhất thành công hay thất bại;
- subsystem đang hoạt động hay bị lỗi;
- có cần rotation hay không.

Thay vì:

```java
@ManagedAttribute
public String getPaymentApiKey() {
    return properties.getApiKey();
}
```

hãy cung cấp trạng thái:

```java
@ManagedAttribute(description = "Whether payment credentials are configured")
public boolean isPaymentCredentialConfigured() {
    String key = properties.getApiKey();
    return key != null && !key.isBlank();
}
```

Một thiết kế tốt hơn có thể dùng một component giữ trạng thái đã kiểm tra:

```java
public enum CredentialStatus {
    MISSING,
    CONFIGURED,
    VALIDATION_FAILED,
    READY
}
```

và export:

```java
@ManagedAttribute(description = "Payment credential readiness")
public String getCredentialStatus() {
    return credentialHealth.getStatus().name();
}
```

`CONFIGURED` không có nghĩa `READY`: một chuỗi key không rỗng có thể đã hết hạn hoặc bị thu hồi. Bởi vậy cần đặt tên attribute chính xác với điều được đo.

**Tư duy tối ưu:** xuất một tín hiệu điều hành đủ để ra quyết định, tránh xuất dữ liệu gốc dùng để tính tín hiệu đó.

## 6. Một ví dụ Spring an toàn, có thể áp dụng

Giả sử hệ thống có service giao tiếp với bên thứ ba. Thay vì để bean JMX giữ/công bố token, tạo lớp trạng thái vận hành độc lập.

```java
// PaymentHealth.java
import java.time.Instant;
import java.util.concurrent.atomic.AtomicReference;
import org.springframework.stereotype.Component;

@Component
public class PaymentHealth {

    public enum State {
        NOT_CONFIGURED, STARTING, READY, DEGRADED
    }

    private final AtomicReference<State> state =
        new AtomicReference<>(State.STARTING);

    private final AtomicReference<Instant> lastSuccess =
        new AtomicReference<>();

    public State currentState() {
        return state.get();
    }

    public Instant lastSuccessfulCheck() {
        return lastSuccess.get();
    }

    public void markReady() {
        lastSuccess.set(Instant.now());
        state.set(State.READY);
    }

    public void markDegraded() {
        state.set(State.DEGRADED);
    }

    public void markNotConfigured() {
        state.set(State.NOT_CONFIGURED);
    }
}
```

MBean chỉ đọc trạng thái tổng hợp:

```java
// PaymentOperationsMBean.java
import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedResource;
import org.springframework.stereotype.Component;

import java.time.Instant;

@Component
@ManagedResource(
    objectName = "demo.payment:type=PaymentOperations",
    description = "Operational status without credentials"
)
public class PaymentOperationsMBean {

    private final PaymentHealth health;

    public PaymentOperationsMBean(PaymentHealth health) {
        this.health = health;
    }

    @ManagedAttribute(description = "Payment subsystem state")
    public String getState() {
        return health.currentState().name();
    }

    @ManagedAttribute(description = "Last successful health check epoch millis")
    public long getLastSuccessEpochMillis() {
        Instant last = health.lastSuccessfulCheck();
        return last == null ? -1L : last.toEpochMilli();
    }

    @ManagedAttribute(description = "Whether payment subsystem is ready")
    public boolean isReady() {
        return health.currentState() == PaymentHealth.State.READY;
    }
}
```

Bean trên không cần giữ password hay token; nó chỉ phụ thuộc state holder. Trạng thái `lastSuccess` được cập nhật bởi code nghiệp vụ hoặc health checking **ở nơi phù hợp**, không phải ngay trong getter JMX. Getter trả nhanh và không gọi network mỗi lần client refresh.

Để các annotation trên được export trong Spring Framework thuần, bật cấu hình tương ứng, chẳng hạn:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableMBeanExport;

@Configuration
@EnableMBeanExport
public class JmxConfiguration {
}
```

Cần cấu hình và dependency tương ứng với phiên bản Spring đang dùng; trong Spring Boot, JMX auto-configuration có thiết lập riêng như `spring.jmx.enabled`. Một `@Component` đơn lẻ không tự bảo đảm MBean xuất hiện.

Đây là một mẫu **allowlist**: chỉ một số getter rõ mục đích được gắn `@ManagedAttribute`. Class chứa secret ở tầng cấu hình không được export trực tiếp.

## 7. Allowlist: chỉ công bố đúng getter cần thiết

Chiến lược an toàn nhất cho MBean quản trị là **chọn rõ các thuộc tính được công bố**, thay vì quét toàn bộ state của bean hay trả một DTO tổng hợp không kiểm soát.

Ví dụ một lớp nghiệp vụ có:

```java
class ConnectionSettings {
    private String endpoint;
    private String username;
    private String password;
    private int connectTimeoutMillis;
    private int maxConnections;
}
```

Không xuất nguyên `ConnectionSettings` qua JMX. Hãy tạo một view nhỏ:

```java
@ManagedAttribute
public int getConnectTimeoutMillis() {
    return settings.getConnectTimeoutMillis();
}

@ManagedAttribute
public int getMaxConnections() {
    return settings.getMaxConnections();
}
```

Ngay cả `endpoint` và `username` cũng nên cân nhắc có thực sự cần cho người vận hành hay không. Thông tin tưởng không bí mật có thể giúp suy luận topology, tên tài khoản dịch vụ hoặc môi trường.

**Không dùng phản chiếu tự động hoặc công bố tất cả getter mà thiếu kiểm soát.** Một DTO lúc đầu chỉ có thông tin không nhạy cảm có thể được bổ sung field `token` trong tương lai. Nếu cả DTO được export, một thay đổi ở domain có thể vô tình mở rộng surface JMX mà không ai chủ động phê duyệt.

Mọi thuộc tính mới cần được xem như thay đổi API quản trị.

## 8. Vì sao masking đơn giản vẫn có rủi ro?

Nhiều code cố “ẩn” secret bằng cách trả một phần ký tự:

```java
@ManagedAttribute
public String getMaskedApiKey() {
    String key = properties.getApiKey();
    return "****" + key.substring(key.length() - 4);
}
```

Có một số vấn đề:

- Secret ngắn có thể gây exception nếu không kiểm tra độ dài.
- Một phần prefix/suffix có thể vẫn hỗ trợ tương quan hoặc nhận diện credential.
- Sự kết hợp nhiều giá trị “đã che” có thể rò rỉ thêm thông tin.
- Bản thân việc gọi `getApiKey()` trong getter JMX mở rộng chỗ code chạm tới credential.
- Người vận hành hiếm khi cần biết vài ký tự cuối để đánh giá sức khỏe hệ thống.

Nếu có nhu cầu xác minh rotation hoặc phiên bản key, ưu tiên **định danh phiên bản không bí mật** được hệ thống cấp riêng, ví dụ `credentialVersion=2026-11` hoặc một trạng thái `rotationRequired`. Không tự suy ra rằng hash của secret chắc chắn không nhạy cảm; digest có thể phục vụ nhận diện, correlation hoặc bị tấn công nếu input có entropy thấp.

Masking có thể phù hợp trong một số UI chẩn đoán được thiết kế riêng, nhưng nó không thay thế nguyên tắc hạn chế dữ liệu công bố qua JMX.

## 9. Phân biệt read-only, write-only và read-write

Một attribute JMX có metadata `isReadable()` và `isWritable()`. Cần hiểu rõ:

| Kiểu attribute | Đọc qua JMX | Ghi qua JMX | Rủi ro chính |
|---|---|---|---|
| Read-only | Có | Không | Lộ dữ liệu đang có |
| Write-only | Không | Có | Thay đổi trạng thái ngoài ý muốn |
| Read-write | Có | Có | Vừa lộ dữ liệu vừa bị thay đổi |

**Đặt secret thành read-only là không an toàn.** Nó vẫn đọc được.

**Đặt secret thành write-only cũng không mặc nhiên an toàn.** Một setter nhận API key qua JMX tạo đường truyền secret cần quản trị nghiêm ngặt. Secret có thể lộ trong công cụ gọi, kết nối, log hoặc code xử lý. Nếu ứng dụng cần rotation, dùng secret manager hoặc quy trình bảo mật chuyên dụng, không mặc định dùng một MBean setter.

**Read-write cho secret đặc biệt nguy hiểm:** client có quyền có thể đọc và thay đổi credential. Hạn chế quyền kết nối có thể giảm rủi ro nhưng không giải quyết việc công bố dữ liệu không cần thiết.

Với cấu hình vận hành thông thường, read-write có thể phù hợp nếu có validation và bảo vệ; ví dụ threshold hoặc mức logging. Cần tách các tham số đó khỏi thông tin xác thực.

## 10. Không chỉ password: dữ liệu gián tiếp cũng nhạy cảm

Một số đường rò rỉ không mang tên rõ ràng:

### 10.1. Exception message

```java
@ManagedAttribute
public String getLastError() {
    return lastException.getMessage();
}
```

Lỗi của HTTP client, database driver hoặc SDK có thể chứa endpoint, username, query, request metadata hoặc thông tin cấu hình. Một exception message do thư viện tạo ra không phải dữ liệu đã được lọc an toàn.

Thay bằng error category hoặc mã trạng thái ổn định:

```java
@ManagedAttribute
public String getLastFailureCategory() {
    return failureState.getCategory().name();
}
```

Nếu cần chi tiết debug, đưa vào logging với cơ chế redaction và phân quyền riêng phù hợp. Không coi log mặc nhiên là an toàn; log cũng có thể rò rỉ nếu ghi raw payload.

### 10.2. Object.toString()

```java
@ManagedAttribute
public String getConfigurationSummary() {
    return configuration.toString();
}
```

Nếu `toString()` được sinh tự động từ record, Lombok hoặc IDE, nó có thể bao gồm cả field `password` hoặc `clientSecret`. Những thay đổi trong class cũng có thể làm nội dung summary thay đổi mà không sửa getter JMX.

Thay bằng một chuỗi rõ thành phần:

```java
return "timeoutMillis=" + config.getTimeoutMillis()
    + ", poolSize=" + config.getPoolSize();
```

Những field đó cũng phải qua xét duyệt theo nhu cầu vận hành.

### 10.3. DTO hoặc Map chứa dữ liệu gốc

```java
@ManagedAttribute
public Map<String, String> getAllProperties() {
    return systemProperties;
}
```

Một map “tiện dụng” có thể chứa credential hoặc các đường dẫn nhạy cảm. Với MXBean, map/DTO có thể được ánh xạ sang `TabularData` hoặc `CompositeData`; sự thay đổi biểu diễn không làm dữ liệu bên trong bớt nhạy cảm.

Chỉ export DTO được thiết kế riêng cho observability với một tập field ổn định.

### 10.4. Thread dump, system properties và environment

Các API diagnostic có thể cho biết stack trace, JVM arguments, biến môi trường hoặc system properties. Những nguồn này đôi khi chứa secret nếu ứng dụng truyền credential qua command-line hoặc cấu hình không phù hợp.

Không tạo custom MBean để xuất toàn bộ `System.getenv()`, `System.getProperties()` hoặc danh sách JVM arguments. Đồng thời, khi bảo vệ JMX remote, cần nhớ một số platform MXBean cung cấp thông tin chẩn đoán sẵn có: chỉ xóa custom getter nhạy cảm chưa đủ để tuyên bố toàn bộ JMX surface không có dữ liệu cần bảo vệ.

## 11. JMX local và remote có mức rủi ro khác nhau

JMX local thường dựa trên quyền truy cập tiến trình/hệ điều hành và cơ chế attach. Một người có quyền thao tác với JVM local có thể có nhiều khả năng chẩn đoán khác ngoài JMX. Nhưng điều đó không biến mọi attribute thành an toàn: thông tin có thể vẫn được copy, ghi log hoặc chuyển vào công cụ khác.

Remote JMX có bề mặt tấn công lớn hơn. Tùy cách triển khai, nó có thể dùng RMI và cần cấu hình endpoint, port, TLS, xác thực và phân quyền. Không nên mở JMX management port công khai ra Internet hoặc triển khai cấu hình thử nghiệm tắt bảo mật trên môi trường production.

Một số nguyên tắc:

1. Ưu tiên mạng quản trị riêng hoặc kênh truy cập được kiểm soát.
2. Bật authentication và bảo vệ đường truyền khi có truy cập từ xa.
3. Áp dụng quyền tối thiểu: tài khoản monitoring chỉ nên có những khả năng cần thiết.
4. Giới hạn MBean, attribute và operation được export theo mục đích.
5. Ghi audit cho thay đổi quản trị, đặc biệt với operation hoặc writable attribute.
6. Quản lý vòng đời credential ở nơi phù hợp; không dùng JMX làm kho giữ hoặc kênh hiển thị secret.
7. Kiểm tra khả năng export/thu thập tự động của monitoring tools để tránh dữ liệu nhạy cảm bị sao chép sang metrics/log storage.

Không giả định rằng mọi JMX connector có RBAC chi tiết đến từng attribute. Cơ chế phân quyền phụ thuộc server, connector và cấu hình thực tế. Vì vậy **data minimization ở ngay lớp MBean** vẫn là biện pháp rất quan trọng.

## 12. Monitoring tool cũng có thể lan truyền dữ liệu

Ngay cả khi chỉ một client quản trị có quyền đọc, client đó có thể:

- tự động scrape attribute theo chu kỳ;
- lưu raw value trong file log hoặc cache;
- xuất metrics sang backend tập trung;
- chuyển dữ liệu qua gateway/agent trung gian;
- hiển thị trong dashboard mà nhiều người có quyền xem.

Đây là lý do không thể chỉ hỏi “ai được phép mở JConsole?”. Cần hỏi **dữ liệu sẽ đi đâu sau khi được đọc**.

Ví dụ một exporter tự động thu mọi attribute kiểu `String` có thể đưa `ApiKey` vào label hoặc diagnostic payload. Thêm một bước làm sạch phía monitoring có thể giúp giảm rủi ro, nhưng nguồn ứng dụng vẫn không nên export credential.

Thiết kế phòng thủ theo nhiều lớp:

```text
Application bean
   |
   +--> Không export dữ liệu nhạy cảm
   |
MBeanServer / JMX connector
   |
   +--> Xác thực, mã hóa, giới hạn mạng và quyền
   |
Monitoring collector
   |
   +--> Allowlist metrics, redaction, hạn chế label/payload
   |
Storage / Dashboard
   |
   +--> Quyền truy cập, retention, audit
```

Một lỗi tại lớp sau không nên khiến các secret vốn không cần thiết đã bị công bố từ lớp trước.

## 13. Thiết kế metadata và tên attribute an toàn

Tên attribute tự nó cũng là một phần metadata có thể được client khám phá. Không nên dùng tên để chứa customer ID, token hoặc bí mật, ví dụ:

```text
ApiKey_abc123SECRET
SessionToken_<raw value>
```

Dùng tên ổn định, mô tả ý nghĩa:

```text
PaymentCredentialConfigured
PaymentState
ConnectionPoolActive
LastSuccessfulHealthCheckEpochMillis
```

Mô tả trong `@ManagedAttribute(description = "...")` cũng là metadata công khai với JMX client; tránh chèn nội dung bí mật, internal URL nhạy cảm hoặc giá trị runtime vào description.

Nếu cần thông tin theo tenant hoặc tài khoản, cân nhắc xuất thống kê aggregate thay vì tạo một ObjectName/attribute cho mỗi người dùng. ObjectName chứa user ID nhạy cảm cũng là một kênh rò rỉ metadata.

## 14. Kiểm tra danh sách attribute được công bố

Việc rà soát nên dựa trên **MBeanInfo thực tế**, vì export thông qua Spring annotation, Standard MBean hoặc MXBean có thể tạo những giao diện khác nhau.

Một đoạn Java kiểm kê tên và quyền đọc/ghi:

```java
import javax.management.MBeanAttributeInfo;
import javax.management.MBeanInfo;
import javax.management.MBeanServer;
import javax.management.ObjectName;

MBeanServer server = ManagementFactory.getPlatformMBeanServer();
ObjectName name = new ObjectName("demo.payment:type=PaymentOperations");

MBeanInfo info = server.getMBeanInfo(name);
for (MBeanAttributeInfo attr : info.getAttributes()) {
    System.out.printf(
        "Attribute=%s, type=%s, readable=%s, writable=%s%n",
        attr.getName(),
        attr.getType(),
        attr.isReadable(),
        attr.isWritable()
    );
}
```

Đoạn code cần import thêm `java.lang.management.ManagementFactory`. Nó chỉ đọc metadata; không in giá trị attribute. Với production, tránh “kiểm tra an toàn” bằng cách tự động đọc và dump mọi giá trị JMX ra stdout.

Đối với các MBean tự tạo, kiểm kê những tên như `Password`, `Token`, `Secret`, `Authorization`, `Cookie`, `PrivateKey`, `JdbcUrl`, `Environment`, `Properties`, `DebugContext`. Đây là dấu hiệu để điều tra, không phải tiêu chí đầy đủ: một attribute mang tên `Info` cũng có thể chứa secret, trong khi một attribute `TokenConfigured` chỉ trả boolean có thể được thiết kế hợp lý.

Cần kiểm tra loại dữ liệu được trả về, nguồn gốc của giá trị và đường truyền tới client. Tên an toàn chưa chứng minh nội dung an toàn.

## 15. Không để operation và notification trở thành đường vòng rò rỉ

Bài tập trung vào `ManagedAttribute`, nhưng JMX còn có `@ManagedOperation` và notifications. Nếu không export token qua getter nhưng có:

```java
@ManagedOperation
public String dumpConfiguration() {
    return configuration.toString();
}
```

thì dữ liệu nhạy cảm vẫn có thể được đọc qua một operation. Tương tự, `Notification.setUserData(...)` có thể đưa raw request hoặc secret đến listener.

Do đó khi thiết kế bề mặt quản trị, phải kiểm tra toàn bộ:

- Attribute đọc được.
- Operation có giá trị trả về.
- Exception/error message do operation hoặc getter phát ra.
- Notification payload, `userData` và message.
- ObjectName, description và metadata mở.

Không phải mọi thông tin quản trị đều nên được truyền qua JMX. Một hành động như rotation credential thường cần một hệ thống quản lý bí mật, audit, quyền và quy trình xác nhận riêng.

## 16. Một tình huống thực tế: debug lỗi kết nối thanh toán

Giả sử payment gateway liên tục trả về lỗi `401 Unauthorized`. Người vận hành muốn biết key đúng hay sai. Có hai hướng thiết kế:

**Hướng có rủi ro:**

```java
@ManagedAttribute
public String getApiKey() {
    return paymentProperties.getApiKey();
}
```

Người vận hành có thể nhìn vào key, nhưng cùng lúc mọi client có quyền đọc attribute đó cũng có khả năng truy xuất credential. Thao tác hỗ trợ debug làm tăng mức phơi bày bí mật.

**Hướng phù hợp hơn:**

```java
@ManagedAttribute
public boolean isCredentialConfigured() {
    return paymentHealth.isConfigured();
}

@ManagedAttribute
public String getAuthenticationStatus() {
    return paymentHealth.getAuthenticationStatus().name();
}

@ManagedAttribute
public long getLastSuccessfulAuthenticationEpochMillis() {
    return paymentHealth.getLastSuccessEpochMillis();
}
```

Kèm theo logging đã redaction và một mã chẩn đoán/correlation ID, người vận hành có thể biết rằng credential có tồn tại, việc xác thực đang thất bại, lần thành công gần nhất khi nào. Nếu cần thay đổi secret, thực hiện qua secret management pipeline thay vì đọc secret qua JMX.

Sự khác biệt là **quan sát kết quả sử dụng credential**, thay vì công bố credential.

## 17. Các lỗi thường gặp khi bảo vệ JMX attribute

### 17.1. “Chỉ đọc nên an toàn”

Sai. Read-only attribute vẫn có thể đọc qua `getAttribute`. Đây chính là đường rò rỉ đối với secret.

### 17.2. “MBean chỉ chạy local, không cần xét dữ liệu”

Không đủ. Local access vẫn là một privilege boundary, và dữ liệu có thể được sao chép sang client/monitoring khác. Không xuất secret vẫn là nguyên tắc đúng.

### 17.3. “Tôi đã che bốn ký tự cuối”

Masking có thể vẫn tiết lộ định danh credential hoặc dữ liệu tương quan. Ưu tiên trạng thái/phiên bản không nhạy cảm do hệ thống cấp riêng.

### 17.4. “Trả Map sẽ không lộ được gì”

Map và DTO có thể chứa nhiều field nhạy cảm; MXBean còn có thể ánh xạ sang OpenData dễ khám phá. Phải xem nội dung, không chỉ kiểu dữ liệu.

### 17.5. “Getter chỉ để debug, không ai sử dụng”

Một khi getter được export, công cụ quản trị hoặc exporter tự động có thể khám phá và đọc. Không nên xem nhãn “debug” như cơ chế bảo mật.

### 17.6. “Không có password trong code là đủ”

Secret có thể đến từ environment, config server, vault, system properties hoặc SDK runtime. Dữ liệu được trả về qua getter mới là yếu tố quyết định.

### 17.7. “Dùng write-only setter để rotate key là xong”

Gửi secret qua JMX setter vẫn cần phân quyền, bảo vệ truyền tải, kiểm soát log và quy trình rotation. Write-only không bảo đảm kênh an toàn.

### 17.8. “Tôi chỉ export trạng thái lỗi”

Trạng thái lỗi có thể chứa raw exception message, request URL, username hoặc request body. Thiết kế mã lỗi tổng hợp, không trả nguyên error object.

## 18. Bài tập thực hành

**Bài 1 — Tìm rủi ro trong MBean:**

```java
@ManagedResource(objectName = "demo:type=Config")
public class ConfigMonitor {

    @ManagedAttribute
    public String getApiKey() { return config.getApiKey(); }

    @ManagedAttribute
    public String getLastError() { return error.getMessage(); }

    @ManagedAttribute
    public int getConnectTimeoutMillis() {
        return config.getConnectTimeoutMillis();
    }
}
```

Hãy phân loại từng getter; sửa bean chỉ giữ lại trạng thái và cấu hình vận hành có mục đích. Với `LastError`, dùng một mã lỗi enum được chuẩn hóa thay vì raw exception message.

**Bài 2 — Thiết kế một trạng thái không tiết lộ key.** Tạo `CredentialStatus` với các giá trị `MISSING`, `CONFIGURED`, `INVALID`, `READY`. Export `getCredentialStatus()` và `getLastValidationEpochMillis()`. Giải thích vì sao hai attribute này phục vụ vận hành tốt hơn `getSecret()`.

**Bài 3 — Kiểm kê metadata.** Đăng ký một MBean Spring, dùng `MBeanServer.getMBeanInfo()` để liệt kê tên và kiểu attribute, nhưng không đọc giá trị. Đối chiếu với các `@ManagedAttribute` trong code.

**Bài 4 — Nguy cơ từ toString().** Tạo một DTO `ConnectionInfo` gồm `host`, `username`, `password`, `poolSize`. Viết một getter trả `info.toString()`, xác định nguy cơ, sau đó thay bằng một summary chỉ công bố `poolSize` và trạng thái kết nối.

**Bài 5 — Tách quan sát và điều khiển.** Thiết kế MBean có `getCredentialStatus()` (read-only) và `refreshCredentialStatus()` (operation yêu cầu kiểm tra lại trạng thái, không in secret). Giải thích vì sao operation không nên trả token hoặc raw exception khi thất bại.

**Bài 6 — Kiểm tra đường đi tới monitoring.** Giả sử một JMX exporter tự động scrape mọi attribute. Hãy lập allowlist chỉ gồm `PaymentState`, `ConnectionPoolActive`, `PaymentErrorsTotal` và giải thích vì sao không nên scrape `Configuration`, `Environment`, `LastRequest`.

## 19. Câu hỏi tự kiểm tra

1. `@ManagedAttribute` trên getter làm thay đổi bề mặt truy cập dữ liệu như thế nào?
2. Vì sao `private final String apiKey` không đủ bảo vệ nếu getter được export?
3. Read-only và confidential có phải cùng một khái niệm không?
4. Trạng thái `CredentialConfigured` giúp ích cho vận hành như thế nào?
5. Vì sao không nên export nguyên object cấu hình hoặc map properties?
6. Một exception message có thể chứa những dạng thông tin nhạy cảm nào?
7. Masking một phần token có luôn an toàn không?
8. Metadata của MBean có thể cho biết gì mà không cần đọc giá trị?
9. Tại sao bảo vệ remote connector chưa thay thế việc giảm thiểu dữ liệu xuất ra?
10. Ngoài attribute, những kênh JMX nào có thể làm lộ thông tin?

## 20. Ghi nhớ

**ManagedAttribute là một lời hứa công bố dữ liệu qua JMX.** Chỉ export những thuộc tính thực sự cần cho vận hành; không công bố mật khẩu, API key, token, dữ liệu người dùng, raw exception hay cấu hình tổng hợp không kiểm soát. Thay bằng trạng thái, số đo, mã lỗi và các tín hiệu tổng hợp được thiết kế riêng.

Sự an toàn đến từ việc giới hạn dữ liệu ngay ở nguồn, kết hợp với bảo vệ connector, quyền truy cập, audit và kiểm soát pipeline giám sát. Khi một attribute không cần tiết lộ giá trị gốc để phục vụ quyết định vận hành, hãy xuất **kết quả quan sát** thay vì **dữ liệu nhạy cảm đã tạo ra kết quả đó**.
