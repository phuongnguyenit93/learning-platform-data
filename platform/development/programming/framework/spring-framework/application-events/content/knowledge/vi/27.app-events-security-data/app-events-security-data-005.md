# Ẩn hoặc băm định danh nhạy cảm trong Spring Framework Application Events

## 1. Mục tiêu và nguyên tắc thiết kế

Spring Framework Application Events giúp các thành phần trong một ứng dụng giao tiếp theo mô hình publish/subscribe. Tuy nhiên, khi phát event về khách hàng, tài khoản, người dùng, đơn hàng, thiết bị hoặc phiên đăng nhập, dữ liệu nhận diện có thể **đi xa hơn phạm vi ban đầu**: nhiều listener cùng đọc payload, ghi log, đưa thông tin vào trace, xuất metrics, tạo task async hoặc chuyển event sang outbox/message broker.

Một lỗi phổ biến là nghĩ rằng event nội bộ chỉ chạy trong JVM nên có thể thoải mái chứa email, số điện thoại, customer ID, session ID, địa chỉ, token hoặc toàn bộ entity. Thực tế, event có thể bị in qua `toString()`, bị giữ trong queue, được serialize ở lớp tích hợp hay xuất hiện trong lỗi.

Bài này tập trung đúng vào **ẩn, loại bỏ hoặc băm định danh nhạy cảm** trong ngữ cảnh Spring Application Events:

- Nhận diện định danh trực tiếp và gián tiếp, cũng như những kênh có thể làm lộ dữ liệu.
- Chọn giữa **không gửi**, **che/xóa**, **pseudonymization bằng HMAC có khóa**, **random opaque ID** và **mã hóa**.
- Hiểu vì sao băm SHA-256 thuần trên email/số điện thoại/ID dễ đoán thường **không đủ để bảo vệ**.
- Thiết kế event chỉ mang thông tin nghiệp vụ tối thiểu và reference phù hợp mục đích.
- Viết Java 17+ với `Mac(HmacSHA256)` và Spring `@EventListener`, gồm code Gradle chạy được, output an toàn và JUnit 5.
- Quản lý khóa, tenant/domain separation, key rotation, retention, logging/metrics/tracing và kiểm thử không rò rỉ.
- Tránh nhầm **pseudonymization** với **anonymization**, hoặc dùng token đã băm làm bằng chứng phân quyền.

**Nguyên tắc ưu tiên:** Nếu listener không cần danh tính, **đừng cho danh tính vào event**. Nếu phải liên kết các lần xảy ra mà không hiển thị định danh gốc, dùng cơ chế pseudonymization phù hợp và quản trị khóa. Việc “đã hash” không biến dữ liệu tự động thành vô danh hay được phép công bố.

## 2. Spring Application Event đi qua những đâu?

Đường đi thường gặp:

~~~text
Controller / Domain Service
            |
            | dữ liệu gốc được dùng trong nghiệp vụ
            v
ApplicationEventPublisher.publishEvent(event)
            |
            v
ApplicationEventMulticaster
            |
            +--> AuditListener ----------> log / SIEM
            |
            +--> NotificationListener ---> email / HTTP
            |
            +--> AnalyticsListener ------> metrics / tracing
            |
            +--> AsyncListener ----------> executor queue
            |
            +--> IntegrationListener ----> outbox / broker
~~~

`ApplicationEventPublisher.publishEvent(Object)` cho phép phát POJO/record, không nhất thiết subclass `ApplicationEvent`. Spring hỗ trợ `@EventListener` để nhận event theo loại. Với multicaster mặc định, listener thông thường chạy đồng bộ trên thread publisher; nếu có `@Async` hoặc executor, event có thể bị giữ lâu hơn trong task queue.

**Spring không tự redaction, mã hóa hoặc băm các field trong event.** Bất kỳ bean nào đủ điều kiện nhận loại event đó có thể đọc payload mà nó được cấp tham chiếu. Việc một event được phân phối trong process không có nghĩa payload được giới hạn theo quyền nghiệp vụ của từng listener.

Trong code:

~~~java
// Thiết kế cần xem lại: email và entity gốc được chia sẻ rộng.
publisher.publishEvent(new CustomerUpdated(customerEmail, customerEntity));
~~~

Nếu listener log `event.toString()`, một record chứa email trực tiếp có thể tự in cả email ra log. Nếu `customerEntity` giữ object graph hay token nhạy cảm, event cũng giữ tham chiếu đến chúng.

**Bảo vệ ngay tại thiết kế payload**, sau đó tiếp tục hạn chế dữ liệu ở output sinks. Chỉ xử lý redaction trong log appender không ngăn listener khác đọc dữ liệu từ event.

## 3. Định danh trực tiếp, gián tiếp và khả năng liên kết

Không phải mọi ID đều vô hại. Một giá trị có thể trở nên nhạy cảm khi kết hợp với dữ liệu khác.

| Loại dữ liệu | Ví dụ giả lập | Rủi ro |
| --- | --- | --- |
| Định danh trực tiếp | Email, điện thoại, họ tên, số giấy tờ | Có thể xác định cá nhân trực tiếp |
| ID nội bộ | `customerId`, `accountId`, `patientId` | Tra cứu hoặc liên kết đến hồ sơ cá nhân |
| Định danh phiên | Session ID, refresh token, API token | Có thể trở thành credential nếu tiết lộ |
| Định danh thiết bị | Device ID, advertising ID | Theo dõi hoạt động theo thiết bị |
| Định danh gián tiếp | IP, địa chỉ, thời điểm, vị trí, tổ hợp thuộc tính | Có thể tái nhận diện khi ghép dữ liệu |
| Business ID | Order/payment/document ID | Có thể liên kết đến dữ liệu nhạy cảm và không nên log công khai |
| Correlation ID | Request ID, trace ID, event ID | Thường không trực tiếp định danh người, nhưng có thể liên kết hoạt động hoặc tạo high-cardinality metrics |

Một email đã được biến thành chuỗi HMAC ổn định vẫn có thể cho phép hệ thống theo dõi “cùng một người” xuyên nhiều event. Đó là **pseudonymous identifier**, không mặc nhiên là dữ liệu đã ẩn danh hoàn toàn.

Một `UUID.randomUUID()` ngẫu nhiên không chứa email, nhưng nếu database ánh xạ UUID tới user và log ghi lại nhiều hoạt động dưới cùng UUID thì vẫn có khả năng liên kết. Mức bảo vệ phụ thuộc **khả năng tra cứu, thời gian lưu giữ, người có quyền truy cập và mục đích xử lý**.

Với dữ liệu nhạy cảm, xác định trước:

1. Ai là producer và những listener nào sẽ nhận?
2. Ai cần biết danh tính gốc; ai chỉ cần trạng thái/số đếm?
3. Event có đi ra ngoài process hoặc được lưu bền vững?
4. Có cần join những event của cùng đối tượng không?
5. Người sở hữu log, metrics, trace hoặc DLQ có quyền xem dữ liệu ở mức nào?
6. Bao lâu phải giữ dữ liệu và xử lý yêu cầu xóa thế nào?

## 4. Chọn đúng biện pháp: loại bỏ, che, băm, token hay mã hóa

Các kỹ thuật có mục tiêu khác nhau. Không có một hàm `hash()` giải quyết mọi yêu cầu bảo mật.

| Kỹ thuật | Cơ chế | Dùng khi | Giới hạn |
| --- | --- | --- | --- |
| **Data minimization** | Không đưa identifier vào event | Handler không cần định danh | Ít thông tin để tương quan |
| **Redaction** | Thay bằng `[REDACTED]` hoặc bỏ hẳn | Chỉ cần biết có sự kiện, không cần identity | Không thể theo dõi cùng đối tượng |
| **Masking** | Chỉ hiển thị phần được phép, ví dụ `***@example.test` | Người được phép nhìn một phần dữ liệu | Phần còn lại vẫn có thể định danh |
| **SHA-256 thuần** | Băm không khóa, deterministic | Kiểm tra toàn vẹn dữ liệu có entropy đủ và mục tiêu phù hợp | Dữ liệu dễ đoán dễ bị dictionary/enumeration |
| **HMAC-SHA256** | Băm có khóa bí mật | Cần reference ổn định theo phạm vi nhưng không phát định danh gốc | Ai có key và danh sách ứng viên có thể tính token; token vẫn liên kết được |
| **Random opaque ID** | Sinh token ngẫu nhiên + mapping bảo vệ | Consumer cần tra cứu danh tính thật theo quyền | Phải quản lý mapping/lifecycle/retention |
| **Encryption** | Mã hóa có khóa, có thể giải mã | Consumer được ủy quyền phải khôi phục dữ liệu | Key, nonce, kiểm soát truy cập và giao thức phức tạp |
| **Aggregation** | Chỉ gửi tổng số/thống kê | Analytics không cần per-user event | Mất chi tiết, cần xét nguy cơ suy luận từ nhóm nhỏ |

**Quy tắc lựa chọn:** Không cần liên kết → bỏ hoặc redaction; cần liên kết nhưng không cần giải ngược → HMAC có khóa theo scope; cần tra cứu danh tính thật → random opaque reference và restricted mapping; cần chuyển dữ liệu để người nhận giải mã hợp lệ → authenticated encryption với quản lý khóa chuyên nghiệp.

Đừng dùng partial masking như `a***@domain.com` nếu hệ thống không thực sự cần hiển thị địa chỉ. Với tập dữ liệu nhỏ, phần được lộ có thể đủ để suy đoán lại đối tượng.

## 5. Vì sao SHA-256(email) không đủ an toàn?

Một ví dụ thiết kế sai thường gặp:

~~~java
String exposedRef = sha256(email);
publisher.publishEvent(new CustomerChanged(exposedRef));
~~~

Đoạn này là **mã minh họa**, chưa có method/class hoàn chỉnh. Vấn đề không nằm ở việc SHA-256 bị “phá” trong nghĩa tìm preimage tổng quát. Vấn đề là nhiều identifier có **không gian giá trị nhỏ, có cấu trúc hoặc dễ đoán**.

Kẻ có bản hash của email có thể tính SHA-256 cho một danh sách email dự đoán và so sánh kết quả. Với số điện thoại, mã bưu chính, ID tăng dần hoặc một tập user ID được biết trước, chi phí liệt kê có thể rất thấp.

~~~text
SHA256("user1@example.test") -> hash A
SHA256("user2@example.test") -> hash B

Ai có danh sách ứng viên có thể tự tính cùng một phép băm.
Không cần biết "salt bí mật" vì ở đây không có khóa.
~~~

Các biến thể cũng cần hiểu đúng:

- **Salt riêng từng record**: giảm hiệu quả bảng hash tính trước và việc liên kết trực tiếp giữa những bản ghi, nhưng nếu salt được lưu cùng hash thì kẻ tấn công vẫn có thể thử candidate với salt đó; không biến dữ liệu dễ đoán thành bí mật.
- **Một salt cố định công khai**: vẫn cho phép tính lại mọi ứng viên, không nên coi như khóa.
- **Một pepper/khóa giữ bí mật**: chuyển hướng thiết kế về keyed hashing như HMAC, cần quản trị key thực sự.
- **Cắt ngắn SHA-256**: chỉ làm mất bớt thông tin trong digest, không giải quyết tấn công thử candidate; còn tăng xác suất collision.

**Đặc biệt:** Password, access token, OTP hoặc session secret không nên xuất hiện trong event. Quy trình **lưu mật khẩu** cần password-hashing/KDF chuyên dụng (Argon2id, scrypt, bcrypt tùy hệ thống), không thay bằng SHA-256 hoặc demo HMAC event identifier.

## 6. HMAC-SHA256: pseudonym ổn định nhưng có ranh giới

HMAC dùng **khóa bí mật** và một thông điệp:

~~~text
digest = HMAC-SHA256(secretKey, canonicalInput)
ref    = formatVersion + Base64UrlNoPadding(digest)
~~~

Khi cùng key và cùng input, HMAC trả cùng digest. Người chỉ nhìn digest nhưng không có key khó tạo token của một danh sách email đoán trước, miễn key được giữ bí mật và đủ entropy. Tuy vậy, người có key hoặc truy cập service sinh token có thể tính lại candidate, và cùng digest vẫn có thể liên kết nhiều sự kiện.

HMAC là **pseudonymization**, không phải phép ẩn danh bảo đảm tuyệt đối. Nó cũng **không phải phân quyền**: việc một request gửi đúng `subjectRef` không có nghĩa caller được phép đọc profile tương ứng.

### 6.1. Tách phạm vi bằng tenant và purpose

Không nên dùng duy nhất:

~~~text
HMAC(key, customerEmail)
~~~

cho mọi chức năng vì cùng email có cùng token trên nhiều module, có thể liên kết chéo dữ liệu.

Thiết kế tốt hơn:

~~~text
HMAC(
  key,
  lengthPrefix("spring-event/customer-preference/v1")
  || lengthPrefix(tenantId)
  || lengthPrefix(canonicalCustomerIdentifier)
)
~~~

Điểm quan trọng:

- **Purpose/domain separation**: token dùng cho event customer preference không tự trùng token dùng cho audit billing, ngay cả khi cùng identifier và key.
- **Tenant separation**: một identifier ở tenant A có token khác khi dùng tenant B (với xác suất collision cực nhỏ).
- **Length-prefix encoding**: tránh nhập nhằng khi nối các chuỗi, chẳng hạn `("a","bc")` với `("ab","c")`.
- **Version**: mô tả hợp đồng canonicalization/encoding/algorithm để thay đổi có kiểm soát.

### 6.2. Canonicalization phải được thống nhất

Các chuỗi `"Alice@example.test"` và `"alice@example.test"` có thể được coi giống hoặc khác tùy hệ thống identity gốc. Không tự ý lowercase toàn bộ email, Unicode normalize hoặc loại ký tự nếu identity store không dùng cùng quy tắc. “Chuẩn hóa an toàn” phải dựa trên **hợp đồng định danh nghiệp vụ**, không phải một helper hash tiện tay.

Khi input đã được canonicalize ở domain service, pseudonymizer nên giữ byte representation nhất quán như UTF-8. Không đưa `Locale.getDefault()` hoặc timezone hệ điều hành vào đường biến đổi ID.

## 7. Event payload nên trông thế nào?

Đối với listener cần biết “một customer preference vừa thay đổi” nhưng không cần email thật:

~~~java
public record CustomerPreferenceChanged(
        String subjectRef,
        String changeKind,
        Instant occurredAt) {}
~~~

Đây là event **tối thiểu**, không phải một đối tượng `CustomerEntity` chứa email, số điện thoại, địa chỉ, session và quyền.

So sánh:

~~~java
// Rủi ro: record.toString() có thể in email.
public record UnsafeEvent(
        String email,
        String phone,
        Object customerEntity) {}

// Hướng tốt hơn khi consumer chỉ cần tương quan:
public record SafeEvent(
        String subjectRef,
        String changeKind) {}
~~~

Nếu consumer **cần thực sự lấy customer ID** để truy vấn database, HMAC một chiều **không tự giải ngược** về ID gốc. Có ba cách thường gặp:

1. **Đừng bỏ ID khỏi vùng tin cậy nếu nơi nhận cần nó để thực hiện nghiệp vụ.** Giữ một internal event giới hạn subscriber/trust boundary; không serialize/log raw ID ra kênh yếu hơn.
2. **Dùng random opaque ID + bảng ánh xạ có quyền truy cập.** Listener được ủy quyền tra cứu reference để lấy ID thật; monitoring không có quyền truy cập bảng ánh xạ.
3. **Dùng lookup/index theo pseudonym có chủ đích** nếu data layer cho phép tra bằng token đã tính sẵn và có quản trị key/rotation; đừng giả định mọi repository `findById` sẽ nhận HMAC token.

Với email sender, đôi khi nhiệm vụ cần địa chỉ thật. Đừng cố thay email bằng hash trong event rồi viết một hàm “unhash” không tồn tại; nên lưu delivery job có reference hợp lệ trong storage được bảo vệ, rồi worker có quyền tra cứu dữ liệu.

### 7.1. Phát POJO thay vì bọc dữ liệu gốc trong source

Spring hỗ trợ `ApplicationEvent` subclass có `source`. Nếu chọn kiểu này, **source cũng có thể giữ thông tin nhạy cảm**.

~~~java
// Cần cân nhắc: source giữ nguyên CustomerEntity.
public class CustomerUpdatedEvent extends ApplicationEvent {
    public CustomerUpdatedEvent(CustomerEntity customer) {
        super(customer);
    }
}
~~~

Đây là minh họa chưa có class `CustomerEntity`. Đừng chỉ sanitize field tùy chỉnh mà quên `getSource()` vẫn trả entity gốc. Với nhiều use case, record/POJO chỉ chứa trường cho phép giúp giảm bề mặt dữ liệu hơn.

## 8. Ví dụ Java 17+ chạy được với Spring và HMAC-SHA256

Ví dụ dùng **Spring Framework 6.2.15**, `@EventListener` và JDK crypto APIs. Nó tạo một event chứa **reference HMAC**, event type và thời điểm, **không chứa email gốc**.

Chú ý thiết kế key:

- **Để demo chạy ngay:** ứng dụng sinh một khóa HMAC ngẫu nhiên khi Spring context khởi tạo.
- **Trong production:** key phải đến từ secret manager/keystore phù hợp, đủ entropy, được giữ ổn định qua restart và giữa các instance khi cần cùng token, có key ID và quy trình rotation.
- **Không log** khóa, raw identifier hay digest đầy đủ.
- Mỗi lần hash tạo một `Mac` mới vì `Mac` không được giả định thread-safe để dùng chung trên nhiều listener threads.

### 8.1. Cấu trúc thư mục

~~~text
sensitive-id-event-demo/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/
    │   └── java/
    │       └── demo/
    │           └── SensitiveIdentifierEventDemo.java
    └── test/
        └── java/
            └── demo/
                └── SensitiveIdentifierEventDemoTest.java
~~~

`settings.gradle`:

~~~groovy
rootProject.name = 'sensitive-id-event-demo'
~~~

`build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'application'
}

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation 'org.springframework:spring-context:6.2.15'
    testImplementation 'org.junit.jupiter:junit-jupiter:5.11.4'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher:1.11.4'
}

application {
    mainClass = 'demo.SensitiveIdentifierEventDemo'
}

test {
    useJUnitPlatform()
}
~~~

Không cần thêm một thư viện crypto ngoài vì Java 17 đã hỗ trợ chuẩn `HmacSHA256`. Khi dùng Spring Boot, nên để Boot dependency management quản lý phiên bản Spring đồng bộ với hệ thống.

### 8.2. File Java đầy đủ

Tạo **`src/main/java/demo/SensitiveIdentifierEventDemo.java`**:

~~~java
package demo;

import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.time.Instant;
import java.util.Base64;
import java.util.Objects;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicReference;
import javax.crypto.KeyGenerator;
import javax.crypto.Mac;
import javax.crypto.SecretKey;

import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;

public class SensitiveIdentifierEventDemo {

    // Event không có email, customer entity, token xác thực.
    public record CustomerPreferenceChanged(
            String subjectRef,
            String changeKind,
            Instant occurredAt) {}

    public static final class Pseudonymizer {
        private static final byte[] PURPOSE =
                "spring-event/customer-preference/v1"
                        .getBytes(StandardCharsets.UTF_8);

        private final SecretKey key;

        public Pseudonymizer(SecretKey key) {
            this.key = Objects.requireNonNull(key);
        }

        public String subjectRef(String tenant, String rawCustomerId) {
            if (tenant == null || tenant.isBlank()
                    || rawCustomerId == null || rawCustomerId.isBlank()) {
                // Không echo input nhạy cảm trong exception.
                throw new IllegalArgumentException(
                        "Identifiers must be nonblank");
            }

            byte[] tenantBytes = tenant.getBytes(StandardCharsets.UTF_8);
            byte[] idBytes =
                    rawCustomerId.getBytes(StandardCharsets.UTF_8);

            // Length-prefix để tránh nhập nhằng khi ghép chuỗi.
            ByteBuffer input = ByteBuffer.allocate(
                    3 * Integer.BYTES
                    + PURPOSE.length + tenantBytes.length + idBytes.length);

            input.putInt(PURPOSE.length).put(PURPOSE);
            input.putInt(tenantBytes.length).put(tenantBytes);
            input.putInt(idBytes.length).put(idBytes);

            try {
                // Mac không chia sẻ mutable instance giữa threads.
                Mac mac = Mac.getInstance("HmacSHA256");
                mac.init(key);
                byte[] digest = mac.doFinal(input.array());

                return "h1_" + Base64.getUrlEncoder()
                        .withoutPadding().encodeToString(digest);
            } catch (GeneralSecurityException ex) {
                throw new IllegalStateException(
                        "Unable to create reference", ex);
            }
        }
    }

    public static final class ChangePublisher {
        private final ApplicationEventPublisher events;
        private final Pseudonymizer pseudonymizer;

        public ChangePublisher(
                ApplicationEventPublisher events,
                Pseudonymizer pseudonymizer) {
            this.events = events;
            this.pseudonymizer = pseudonymizer;
        }

        public void preferenceChanged(String tenant, String rawCustomerId) {
            String ref = pseudonymizer.subjectRef(
                    tenant, rawCustomerId);

            events.publishEvent(new CustomerPreferenceChanged(
                    ref,
                    "PREFERENCE_UPDATED",
                    Instant.now()));
        }
    }

    // Demo chỉ in thông tin không nhạy cảm, không log record.toString().
    public static final class AuditListener {
        private final AtomicInteger count = new AtomicInteger();
        private final AtomicReference<CustomerPreferenceChanged> last =
                new AtomicReference<>();

        @EventListener
        public void handle(CustomerPreferenceChanged event) {
            last.set(event);
            count.incrementAndGet();

            System.out.println("listener.event=customer_preference_changed");
            System.out.println("listener.identity=hidden");
        }

        public int count() {
            return count.get();
        }

        public CustomerPreferenceChanged last() {
            return last.get();
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class Config {
        @Bean
        public SecretKey demoHmacKey()
                throws GeneralSecurityException {
            // Chỉ cho demo: key mới khi mỗi Spring context được tạo.
            KeyGenerator generator =
                    KeyGenerator.getInstance("HmacSHA256");
            generator.init(256);
            return generator.generateKey();
        }

        @Bean
        public Pseudonymizer pseudonymizer(SecretKey demoHmacKey) {
            return new Pseudonymizer(demoHmacKey);
        }

        @Bean
        public ChangePublisher changePublisher(
                ApplicationEventPublisher events,
                Pseudonymizer pseudonymizer) {
            return new ChangePublisher(events, pseudonymizer);
        }

        @Bean
        public AuditListener auditListener() {
            return new AuditListener();
        }
    }

    public static void main(String[] args) {
        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext(Config.class)) {

            Pseudonymizer pseudonymizer =
                    context.getBean(Pseudonymizer.class);
            ChangePublisher publisher =
                    context.getBean(ChangePublisher.class);
            AuditListener listener =
                    context.getBean(AuditListener.class);

            // Dữ liệu mô phỏng, không phải email thật.
            String rawId = "user-42@example.test";
            String tenant = "tenant-demo";

            String first = pseudonymizer.subjectRef(tenant, rawId);
            String repeat = pseudonymizer.subjectRef(tenant, rawId);
            String otherTenant =
                    pseudonymizer.subjectRef("tenant-other", rawId);

            publisher.preferenceChanged(tenant, rawId);

            System.out.println(
                    "sameInputSameReference=" + first.equals(repeat));
            System.out.println(
                    "differentTenantDifferentReference="
                    + !first.equals(otherTenant));
            System.out.println(
                    "eventContainsRawId="
                    + listener.last().toString().contains(rawId));
            System.out.println(
                    "listenerCount=" + listener.count());
        }
    }
}
~~~

### 8.3. Chạy demo

Trong thư mục dự án, dùng JDK 17+ và Gradle:

~~~bash
gradle -q run
~~~

Nếu đã có Gradle Wrapper, dùng `./gradlew -q run` trên Linux/macOS hoặc `gradlew.bat -q run` trên Windows.

Các dòng **do mã demo in ra** theo thứ tự trong điều kiện bình thường:

~~~text
listener.event=customer_preference_changed
listener.identity=hidden
sameInputSameReference=true
differentTenantDifferentReference=true
eventContainsRawId=false
listenerCount=1
~~~

Không in giá trị digest vì nó vẫn là một định danh có khả năng liên kết. Sự khác nhau giữa token tenant A và B dựa trên tính chất HMAC; xác suất collision đối với HMAC-SHA256 trong use case này cực nhỏ, nhưng không phải tuyên bố rằng thuật toán không thể có collision về mặt toán học.

Thứ tự dòng log do `SimpleApplicationEventMulticaster` mặc định gọi listener đồng bộ: hai dòng của listener xuất hiện trước các dòng do `main` in sau `publishEvent`. Nếu đổi sang async, cần chờ callback hoàn tất trước khi đọc `listener.last()`.

### 8.4. Vì sao ví dụ không tiết lộ ID gốc trong event?

- Record `CustomerPreferenceChanged` chỉ có `subjectRef`, `changeKind` và `occurredAt`.
- `ChangePublisher` nhận raw identifier qua method argument để tính token nhưng **không** đưa nó vào event object.
- `Pseudonymizer` mã hóa input theo purpose, tenant và raw ID bằng UTF-8 có length prefixes rồi tính HMAC-SHA256.
- `AuditListener` chỉ in hai chuỗi cố định không chứa ID hay token.
- `Mac` được tạo mới mỗi phép tính; không chia sẻ trạng thái nội bộ có thể bị sửa giữa các threads.
- `SecretKey` được tạo ngẫu nhiên và **không in**; bản thân demo key không được lưu giữa các lần khởi động.

**Giới hạn quan trọng:** `eventContainsRawId=false` chỉ chứng minh record demo không chứa chuỗi raw ID dạng đó. Nó không chứng minh toàn bộ runtime, mọi log của dependency hay memory dump không có dữ liệu gốc. Thực tế raw ID vẫn tồn tại tạm thời ở service argument và string trong JVM; muốn bảo mật production phải thiết kế cả vòng đời dữ liệu, quyền truy cập và sinks.

## 9. JUnit 5: kiểm tra deterministic, scope, Spring wiring và input lỗi

Tạo **`src/test/java/demo/SensitiveIdentifierEventDemoTest.java`**:

~~~java
package demo;

import org.junit.jupiter.api.Test;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

class SensitiveIdentifierEventDemoTest {

    @Test
    void sameInputAndKeyProduceSameScopedReference() {
        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext(
                             SensitiveIdentifierEventDemo.Config.class)) {

            var pseudonymizer = context.getBean(
                    SensitiveIdentifierEventDemo.Pseudonymizer.class);

            String id = "user-42@example.test";
            String a = pseudonymizer.subjectRef("tenant-A", id);
            String again = pseudonymizer.subjectRef("tenant-A", id);
            String b = pseudonymizer.subjectRef("tenant-B", id);

            assertEquals(a, again);
            assertNotEquals(a, b);
            assertTrue(a.matches("h1_[A-Za-z0-9_-]{43}"));
            assertFalse(a.contains(id));
        }
    }

    @Test
    void springEventCarriesPseudonymInsteadOfRawId() {
        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext(
                             SensitiveIdentifierEventDemo.Config.class)) {

            var publisher = context.getBean(
                    SensitiveIdentifierEventDemo.ChangePublisher.class);
            var listener = context.getBean(
                    SensitiveIdentifierEventDemo.AuditListener.class);

            String raw = "another-user@example.test";
            publisher.preferenceChanged("tenant-A", raw);

            assertEquals(1, listener.count());
            var event = listener.last();
            assertEquals("PREFERENCE_UPDATED", event.changeKind());
            assertTrue(event.subjectRef().startsWith("h1_"));
            assertFalse(event.toString().contains(raw));
        }
    }

    @Test
    void emptyIdentifierIsRejectedWithoutEchoingInput() {
        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext(
                             SensitiveIdentifierEventDemo.Config.class)) {

            var pseudonymizer = context.getBean(
                    SensitiveIdentifierEventDemo.Pseudonymizer.class);

            var failure = assertThrows(
                    IllegalArgumentException.class,
                    () -> pseudonymizer.subjectRef("tenant-A", " "));

            assertEquals("Identifiers must be nonblank",
                    failure.getMessage());
        }
    }
}
~~~

Chạy:

~~~bash
gradle test
~~~

Các test xác minh ba hợp đồng:

1. **Deterministic trong cùng key/scope** và tách token khi đổi tenant.
2. **Event đi qua Spring publisher/listener thật**; không có raw ID trong payload của record ví dụ.
3. **Fail closed khi input không hợp lệ** và exception không echo dữ liệu người dùng.

Đây là kiểm tra logic và wiring, **không** thay thế một cuộc kiểm thử xâm nhập, kiểm toán log hoặc xác minh production key management. Bài này không tuyên bố đã chạy Gradle; kết quả cần được xác nhận khi triển khai trong môi trường build thật.

## 10. Quản lý khóa HMAC trong production

Code demo dùng `KeyGenerator` sinh 256-bit HMAC key trong memory để chạy độc lập. Nếu nhiều instance A/B tạo key khác nhau, **cùng customer ID sẽ cho reference khác nhau**, làm hỏng correlation, dedup hoặc lookup.

Một thiết kế production cần:

### 10.1. Nguồn key

- Sinh key đủ entropy bằng CSPRNG hoặc key management system.
- Lưu và cấp phát qua **secret manager, KMS, HSM hoặc keystore** phù hợp.
- Không hard-code key vào source, test fixture dùng cho production, Docker image, `application.yml` được commit, query parameter hay log.
- Hạn chế IAM của service chỉ được phép sử dụng key cần thiết; tách quyền của producer, consumer, operator và observability.
- Không ghi toàn bộ key hoặc Base64 key vào log để debug lỗi.

Nếu nhận key từ environment variable được cấp bí mật, cần bảo vệ cả cấu hình runtime, crash dump và diagnostic endpoints. Môi trường production có thể chọn KMS MAC operation để key không rời KMS, đổi lại có network latency, quota và tính sẵn sàng cần đánh giá.

### 10.2. Key ID và phiên bản

Một format có thể là:

~~~text
pseudonym token:
  hmac-v2.<keyId>.<base64url(digest)>

metadata:
  purpose = customer-preference
  tenant = isolated scope (không nhất thiết phát tenant raw)
  algorithm = HmacSHA256
  keyId = ID khóa không phải secret
~~~

Format này là **ví dụ thiết kế**, khác prefix `h1_` đơn giản trong demo. Đừng gộp key ID, algorithm version và canonicalization version một cách không kiểm soát; khi thay đổi cách mã hóa input, các consumer phải biết version để diễn giải.

### 10.3. Rotation

Khi đổi key, cùng ID sẽ cho token mới:

~~~text
reference(K_old, tenant, customer) != reference(K_new, tenant, customer)
~~~

Nếu hệ thống lưu event cũ hoặc dùng token để correlate trong nhiều ngày, cần kế hoạch:

1. Gắn `keyId`/version cho token mới.
2. Giữ key cũ trong phạm vi cho phép và thời hạn đủ để đọc/migrate dữ liệu hợp lệ.
3. Dùng dual-read hoặc mapping migration nếu cần tương quan dữ liệu cũ và mới.
4. Không phát sinh hai ID khác nhau cho cùng một nghiệp vụ mà không xử lý dedup/version.
5. Thu hồi key cũ theo retention và chính sách xóa khi hết nhu cầu.
6. Kiểm toán nơi key được sử dụng và tác động khi key lộ.

Key rotation **không** tự xóa các token đã từng đi vào log/outbox. Vòng đời dữ liệu và retention vẫn phải được xử lý riêng.

## 11. Một token HMAC vẫn có thể nhạy cảm

Một dạng hiểu sai: “đã hash nên log thoải mái”. HMAC token có thể không cho thấy email gốc, nhưng vẫn cho phép:

- Liên kết nhiều lần thao tác của cùng một subject trong cùng scope/key.
- Ghép với một hệ thống khác giữ mapping hoặc biết input/key.
- Suy luận hoạt động từ thời điểm, tần suất, event type hoặc thuộc tính đi kèm.
- Khôi phục mapping nếu key/service tính token bị lộ hoặc cho phép oracle queries không giới hạn.

Do đó:

- Chỉ log token khi có **nhu cầu tương quan rõ**; ưu tiên không log hoặc chỉ log event type/status.
- Dùng purpose/tenant isolation và retention giới hạn.
- Không sử dụng token như proof-of-identity hay authorization credential.
- Khi phân quyền, lấy danh tính từ authenticated principal/trust boundary và kiểm tra resource-level permissions; đừng tin một `subjectRef` do client gửi.
- Chống lạm dụng token-generation endpoint: auth, rate limit, auditing, không biến nó thành public dictionary oracle.
- Xem pseudonym là **dữ liệu vẫn cần bảo vệ** theo mô hình rủi ro/quy định áp dụng, không mặc nhiên là anonymous.

Nếu yêu cầu thật sự là **không thể liên kết các event**, deterministic HMAC không phù hợp. Dùng event ID ngẫu nhiên riêng cho mỗi lượt và không phát subject reference; với analytics, cân nhắc aggregation/k-anonymity hoặc phương pháp privacy phù hợp hơn tùy use case.

## 12. Thiết kế logging an toàn cho listener

### 12.1. Tránh stringify event

Không nên:

~~~java
@EventListener
public void on(CustomerPreferenceChanged event) {
    logger.info("Customer changed: {}", event);
}
~~~

Đây là code minh họa. Java record mặc định sinh `toString()` gồm tên các component và giá trị. Nếu event chứa email hoặc HMAC reference, log có thể lưu giá trị đó. Nếu field thêm mới về sau, log tự nhận thêm dữ liệu mà review không để ý.

Gợi ý:

~~~java
@EventListener
public void on(CustomerPreferenceChanged event) {
    logger.info("customer preference event processed; kind={}",
            event.changeKind());
}
~~~

Chỉ ghi field đã được phê duyệt. Nếu cần correlation, chọn `eventId` độc lập và kiểm soát mức độ liên kết. Log template có parameter không tự động che PII; **giá trị truyền vào vẫn cần được rà soát**.

### 12.2. Exception message có thể rò raw ID

Không nên:

~~~java
throw new IllegalArgumentException(
        "Invalid customer " + rawCustomerId);
~~~

Nếu exception được log, raw ID đi theo message. Dùng mã lỗi hữu hạn:

~~~java
throw new IllegalArgumentException(
        "Invalid customer identifier");
~~~

Với support investigation, dùng correlation ID hoặc mã lỗi và một restricted audit channel được kiểm soát, thay vì echo dữ liệu đầu vào vào exception public/log thường.

### 12.3. Log injection và thông tin do người dùng nhập

Dù đã masking identifier, các field text khác có thể chứa newline, control character hoặc delimiter gây log forging. Dùng structured logging và encoder xử lý escape đúng, validate field length, không nối raw user input vào log template. OWASP Logging Cheat Sheet khuyến nghị loại bỏ/che/hạn chế dữ liệu cá nhân, secret và session values trong log.

Log aggregation, file rotation, archive và backup đều cần retention, RBAC và đường truyền phù hợp; redaction tại UI hiển thị log **không** xóa dữ liệu gốc đã lưu ở backend.

## 13. Metrics và tracing: tránh high-cardinality và rò rỉ context

Một lỗi thường gặp:

~~~java
registry.counter(
        "customer.event",
        "customer_ref", event.subjectRef()).increment();
~~~

Dù là HMAC, mỗi subject vẫn tạo một label value khác nhau. Khi có hàng trăm nghìn người dùng, số lượng time series tăng mạnh; bạn đã đưa định danh liên kết được vào hệ thống metrics.

Metric tags nên là **low-cardinality**:

~~~java
registry.counter(
        "customer.event",
        "type", "preference_changed",
        "outcome", "success").increment();
~~~

Đây là đoạn minh họa cần Micrometer `MeterRegistry` và bean `registry`. `event type`, `outcome`, `handler`, `error kind` với tập giá trị hữu hạn có thể phù hợp hơn `customerId`, `email`, `eventId`, `traceId` hoặc digest.

### 13.1. Trace và log cũng có policy riêng

Trace span attributes/baggage có thể được export tới bên thứ ba; không tự đưa raw ID hoặc full HMAC token vào attributes. Nếu cần correlation theo user, phải có mục đích hợp lệ, access control, sampling và retention. Với async listeners, MDC/ThreadLocal context không mặc định được truyền sang executor; context propagation không thay thế chính sách sanitize dữ liệu.

Nên tách:

- Metrics: tổng hợp số lần, duration, outcome.
- Logs: sự kiện vận hành có giới hạn field.
- Traces: liên kết đường đi xử lý với correlation được phép.
- Restricted audit store: dữ liệu nhạy cảm thật sự cần cho kiểm toán, có quyền và retention riêng.

### 13.2. Không đưa secret vào error reporting

Sentry, APM, OpenTelemetry exporter hoặc crash reporter có thể tự thu request parameters, exception messages hoặc object fields. Kiểm tra SDK configuration, filters, before-send hooks và sample payload của telemetry, không chỉ kiểm tra `logger.info` trong source.

## 14. Transaction, async, outbox và dead-letter

### 14.1. Transaction-bound event

Với `@TransactionalEventListener(AFTER_COMMIT)`, việc xử lý có thể được hoãn đến sau commit, nhưng payload vẫn là object trong JVM. Nếu event chứa raw ID, nó có thể tồn tại đến khi callback chạy. HMAC không tự thay đổi thời điểm transaction và không làm side effect an toàn nếu callback chạy ngoài transaction.

### 14.2. Async queue

Khi có executor, task có thể giữ event/payload trong heap lâu hơn. Nếu payload chứa thông tin nhạy cảm, số bản tham chiếu và thời gian tồn tại tăng; nếu queue được dump hoặc crash report ghi object, nguy cơ lộ tăng. Chỉ đặt field thực sự cần trong event.

### 14.3. Outbox / message broker

Nếu event được serialize vào outbox JSON, Kafka, RabbitMQ hoặc HTTP, phạm vi người có thể truy cập dữ liệu khác với Spring event in-process. Một event nội bộ “được tin cậy” không mặc nhiên là public integration contract.

Cần:

- Tách event nội bộ và DTO integration nếu có trust boundary khác.
- Sanitize và validate **trước khi persist/publish** ra kênh rộng hơn.
- Schema version và data classification cho các field.
- Encryption at rest/in transit, ACL và retention phù hợp.
- DLQ/retry không tự giữ dữ liệu vô hạn hoặc sao chép dữ liệu nhạy cảm nhiều nơi.
- Chỉ serialize opaque reference nếu consumer có cơ chế xử lý/retrieval được ủy quyền.

Nếu cần không mất event qua crash, transactional outbox hoặc broker là kiến trúc delivery; HMAC chỉ giải quyết một phần **confidentiality/correlation**, không tạo bảo đảm delivery.

## 15. Thiết kế API và mô hình quyền

Một service có thể cần customer ID thật để cập nhật database nhưng listener audit không cần biết nó. Có thể dùng kiến trúc hai tầng:

~~~text
Authenticated request
     |
     v
Authorized domain service
  |  (giữ raw ID trong vùng tin cậy)
  |
  +--> database update
  |
  +--> event adapter / safe DTO
         |
         +--> pseudonymize raw ID with approved scope/key
         |
         +--> publish CustomerPreferenceChanged(subjectRef, kind)
                  |
                  +--> metrics/audit listeners: no raw ID
~~~

Nếu một notification listener cần email để gửi mail, đừng bắt nó “giải hash”. Tách một durable delivery job trong storage bảo vệ, giữ **opaque reference** tới customer record và để worker có quyền giải reference theo business rule.

Authorization cần thực hiện **trước thao tác domain** và **ở mọi data retrieval** sau đó. HMAC token không phải session token, access token hoặc capability được quyền truy cập. Nếu nhận token từ client, cần xác nhận tenant, quyền truy cập và trạng thái dữ liệu gốc qua hệ thống tin cậy.

### 15.1. Không dựa vào masking ở giao diện làm kiểm soát bảo mật

Nếu UI hiển thị `u***@example.test` nhưng backend event/log vẫn lưu email thật, rủi ro vẫn tồn tại. Tương tự, nếu API response xóa email nhưng message broker vẫn có field `rawEmail`, chính sách bảo mật chưa được đáp ứng. Cần phân loại và bảo vệ **từng điểm dữ liệu rời khỏi trust boundary**.

### 15.2. Dữ liệu cần xóa hoặc hết hạn

Pseudonym không tự cho phép xóa dữ liệu theo một ID thô nếu không có mapping hoặc khả năng tính lại token bằng key cũ. Nếu có quyền xóa, hệ thống phải biết token và bản ghi nào liên quan; thiết kế retention, key lifecycle và index phù hợp ngay từ đầu. Không xóa key vội khi còn cần xử lý bản ghi tồn đọng, nhưng cũng không giữ key vô hạn chỉ vì convenience.

## 16. Hiệu năng và trade-off của HMAC

HMAC-SHA256 với input ngắn thường có chi phí tính toán thấp, nhưng vẫn có các đánh đổi:

- Tạo `Mac` mới mỗi call tránh chia sẻ state không thread-safe. Benchmark throughput nếu event rate rất cao.
- HMAC với key từ KMS remote có thể có network latency; có quota, timeout và khả năng lỗi. Cân nhắc local KMS-protected key cache theo policy nếu được phép.
- Dữ liệu cần normalize/encode ổn định; biến đổi string lớn hoặc bất thường có thể làm tốn CPU/memory. Validate giới hạn kích thước input.
- Không đưa cả object graph vào dữ liệu băm; chọn đúng identifier canonical, purpose và tenant.
- Token dài hơn numeric ID, có chi phí index/storage nếu persistence; dùng index/length phù hợp và đánh giá collision nếu truncation.

Trong demo, digest HMAC-SHA256 gồm 32 byte; Base64URL không padding biểu diễn thành **43 ký tự ASCII**, cộng prefix `h1_` là **46 ký tự**. Đây là kích thước biểu diễn, không phải bằng chứng rằng dữ liệu đã an toàn cho mọi mục đích.

**Không tự cắt token thành 6 hoặc 8 ký tự** chỉ để log đẹp. Truncation làm tăng nguy cơ collision, đặc biệt khi có hàng triệu subject. Nếu chỉ cần log marker để điều tra một request cụ thể, tốt hơn là dùng correlation ID sinh ngẫu nhiên, không phải một digest subject bị cắt thiếu thiết kế.

## 17. Kiểm thử an toàn dữ liệu ngoài unit test

Bộ JUnit mục 9 xác nhận event demo không chứa raw ID. Production cần thêm kiểm thử theo các đường thoát thực tế:

| Test | Điều cần xác nhận |
| --- | --- |
| Event schema | Không có field raw email, phone, password, token, `CustomerEntity` hoặc request object |
| Stable pseudonym | Cùng key/scope/input cho token giống nhau |
| Scope isolation | Khác purpose/tenant cho token khác nhau theo thiết kế |
| Key rotation | Có thể đọc/migrate record còn hiệu lực mà không mất correlation cần thiết |
| Log capture | Không chứa raw ID/secret; không in full event/toString không được phép |
| Exception path | Error message và stacktrace đã qua redaction phù hợp |
| Metrics labels | Không có user ID, raw ID, event ID hoặc digest có cardinality cao |
| Tracing export | Span/baggage không phát dữ liệu không được phép |
| Async event | Queue và error handler không vô tình log payload |
| Outbox/DLQ | Serialized JSON không có field cấm; retention và quyền phù hợp |
| Authorization | Có token không cho phép vượt tenant hoặc đọc dữ liệu không có quyền |
| Key exposure | Không nằm trong logs, metrics, source, config public, build artifact |
| Deletion/retention | Dữ liệu và pseudonym hết hạn theo policy thực tế |

### 17.1. Test capture log hiệu quả hơn grep source

Chỉ tìm `logger.info(event)` trong code chưa đủ. Library hoặc exception handler có thể tự format object. Với Logback/SLF4J, dùng test appender bắt log của listener và assert không chứa email giả lập hoặc key. Với tracing, dùng in-memory exporter/test harness; với outbox, truy vấn JSON đã persist.

### 17.2. Test dictionary attack ở mức thiết kế

Không nên “test SHA-256 đã đủ an toàn” chỉ vì digest trông khó đọc. Hãy trình bày threat model: kẻ không có key nhưng có thể liệt kê candidate identifiers. HMAC bảo vệ tốt hơn trong tình huống này nếu key không bị lộ và token-generation service không thành oracle dễ khai thác.

### 17.3. Test trường hợp key khác giữa các instance

Nếu hai instance dùng key khác, cùng email tạo hai token khác nhau. Với hệ thống cần stable correlation xuyên instance, integration test phải chứng minh chúng được cấu hình cùng key version ở đúng thời điểm. Demo **cố ý** không đáp ứng điều kiện này vì key được sinh ngẫu nhiên trong context.

## 18. Những lỗi và ngộ nhận phổ biến

| Ngộ nhận/lỗi | Vì sao sai | Hướng sửa |
| --- | --- | --- |
| “Event nội bộ nên không có rủi ro PII” | Listener/log/trace/async/outbox có thể mở rộng phạm vi | Chỉ gửi dữ liệu tối thiểu, phân loại sink |
| Hash email với SHA-256 là ẩn danh | Có thể thử dictionary với email dễ đoán | Ưu tiên loại bỏ; nếu cần stable token thì HMAC có khóa |
| Mask `a***@domain` luôn an toàn | Có thể tái nhận diện bằng dữ liệu còn lộ | Chỉ mask khi use case thật cần |
| HMAC token là dữ liệu công khai | Nó vẫn liên kết nhiều event và có thể bị ánh xạ | Treat as pseudonymous, áp dụng retention/ACL |
| Hash xong có thể dùng như access token | Hash không chứng minh quyền sở hữu/authorization | Kiểm tra principal/tenant/resource permission |
| Đưa email vào event rồi chỉ che khi log | Listener khác vẫn đọc raw email | Sanitize ngay payload/trust boundary |
| Record tự che nội dung nhạy cảm | Record `toString` thường in component values | Không log object tùy tiện, DTO allowlist |
| Định danh nằm trong `ApplicationEvent.source` là vô hại | Source có thể là entity chứa nhiều dữ liệu | Không dùng sensitive entity làm source |
| HMAC không cần secret manager | Key lộ cho phép compute candidate | KMS/keystore, least privilege, rotation |
| Tạo random key mỗi restart vẫn có stable token | Token sẽ đổi qua restart | Production dùng key ổn định và version |
| Dùng cùng key/input cho mọi module | Có thể link chéo các domains | Scope/purpose/tenant separation |
| Dùng string nối thô `tenant+id` | Có ambiguity và collision logic của encoding | Length prefixes/canonical encoding |
| HMAC có thể unhash ra ID thật | HMAC không phải mã hóa hai chiều | Dùng restricted mapping/reference nếu cần lookup |
| Salt công khai thay được HMAC key | Attacker vẫn thử ứng viên với salt biết trước | Dùng secret-keyed HMAC khi phù hợp |
| Cắt digest còn vài ký tự vẫn đủ mọi quy mô | Collision risk tăng theo số lượng token | Đánh giá toán học; giữ digest đủ dài |
| Đưa subject hash vào Micrometer tag là an toàn | High cardinality và linkability | Tags hữu hạn, correlation có kiểm soát |
| Dùng `@Async` thì hết rủi ro dữ liệu | Queue giữ payload lâu và error path có thể log | Giảm field, bảo vệ async pipeline |
| Token không cần xóa vì đã hash | Retention và nghĩa vụ bảo vệ có thể vẫn áp dụng | Có lifecycle và deletion policy |
| Thử nghiệm pass thì production đã an toàn | Test chưa bao phủ log exporter, KMS, broker | Integration/security review theo đường thoát |
| Dùng HMAC event token để hash password | Password storage là bài toán khác | Password KDF thích hợp; không phát password |
| Cùng raw identifier phải luôn tạo token giống nhau mọi ngữ cảnh | Tăng khả năng link dữ liệu giữa modules | Namespace theo purpose và tenant |

## 19. Checklist code review và câu hỏi tự kiểm tra

**Checklist:**

- [ ] Đã biết trường nào là định danh trực tiếp/gián tiếp.
- [ ] Nếu listener không cần identity, payload không chứa identity.
- [ ] Không đưa email/phone/token/password/session hoặc entity nhạy cảm vào event.
- [ ] Nếu cần stable reference, HMAC có key đủ entropy, scope và version rõ.
- [ ] Không dùng SHA-256 thuần trên identifier dễ đoán rồi gọi là anonymous.
- [ ] Canonicalization nhất quán với hệ thống identity thật.
- [ ] Event source không giữ entity/request gốc ngoài ý muốn.
- [ ] Listener không log nguyên `event.toString()` hoặc exception chứa raw input.
- [ ] Metrics/traces/logs/queue/outbox/DLQ đã được rà soát theo trust boundary.
- [ ] Pseudonymization không được dùng làm authorization.
- [ ] Có key owner, IAM, rotation, key ID và retention policy.
- [ ] Đã có kế hoạch xử lý consumer cần ID gốc (mapping/restricted store).
- [ ] Các test không chỉ assert string không chứa ID mà còn kiểm tra actual sinks.
- [ ] Có khả năng phát hiện việc thêm field nhạy cảm vào event schema trong review.
- [ ] Đã xác định cách xử lý xóa/retention/correlation khi đổi key.

**Câu hỏi 1.** Khi listener chỉ đếm số lần customer đổi preference, có nên đưa email vào event không?

**Đáp án:** Không. Event type/counter có thể đủ; đừng pseudonymize nếu không cần identifier.

**Câu hỏi 2.** Vì sao SHA-256(email) không bảo vệ tốt với attacker có danh sách email ứng viên?

**Đáp án:** Attacker tự tính cùng phép băm cho từng candidate và so sánh; SHA-256 không có khóa bí mật.

**Câu hỏi 3.** HMAC-SHA256 có biến dữ liệu thành anonymous tuyệt đối không?

**Đáp án:** Không. Token có thể linkable và được tính lại bởi bên có key/nguồn candidate; phải bảo vệ như pseudonymous data.

**Câu hỏi 4.** Consumer muốn lấy customer entity từ database nhưng event chỉ có HMAC reference; có thể gọi `findById(hash)` không?

**Đáp án:** Chỉ khi data layer đã thiết kế index/lookup phù hợp. HMAC không thể tự giải ngược; thường cần opaque ID + mapping hoặc restricted workflow.

**Câu hỏi 5.** Vì sao phải đưa tenant và purpose vào input HMAC?

**Đáp án:** Giảm khả năng cùng identifier tạo token giống nhau giữa tenant/module, hạn chế link chéo.

**Câu hỏi 6.** Sinh random HMAC key mỗi lần ứng dụng khởi động có ổn cho demo không? Có ổn cho correlation production không?

**Đáp án:** Demo thì ổn để chạy độc lập; production cần key được cấp ổn định, version và rotation để không mất liên kết mong muốn.

**Câu hỏi 7.** Có nên ghi token HMAC đầy đủ làm `customer_ref` tag của Micrometer không?

**Đáp án:** Không. Nó có giá trị rất nhiều, tạo high cardinality và khả năng theo dõi; dùng tag loại event/outcome hữu hạn.

**Câu hỏi 8.** Khi đã che email trong log nhưng event vẫn mang raw email, đã giải quyết hết rủi ro chưa?

**Đáp án:** Chưa. Listener, memory, tracing, outbox/broker và error path vẫn có thể lộ; sanitize payload ngay tại boundary.

## 20. Tài liệu tham khảo

- Spring Framework 6.2 — Standard and Custom Events, POJO payload và `@EventListener`: https://docs.spring.io/spring-framework/reference/6.2/core/beans/context-introduction.html
- Spring Framework 6.2 — `ApplicationEventPublisher` Javadoc: https://docs.spring.io/spring-framework/docs/6.2.15/javadoc-api/org/springframework/context/ApplicationEventPublisher.html
- Spring Framework 6.2 — `PayloadApplicationEvent` Javadoc: https://docs.spring.io/spring-framework/docs/6.2.15/javadoc-api/org/springframework/context/PayloadApplicationEvent.html
- Java SE 17 — `javax.crypto.Mac`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/crypto/Mac.html
- Java SE 17 — `javax.crypto.KeyGenerator`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/crypto/KeyGenerator.html
- Java SE 17 — `java.util.Base64`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Base64.html
- Java SE 17 — `java.nio.ByteBuffer`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/ByteBuffer.html
- OWASP — Logging Cheat Sheet, dữ liệu cần loại/che/băm và ngăn log injection: https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html
- OWASP — Cryptographic Storage Cheat Sheet, nguyên tắc key management: https://cheatsheetseries.owasp.org/cheatsheets/Cryptographic_Storage_Cheat_Sheet.html
- OWASP — Password Storage Cheat Sheet (password hashing là bài toán khác HMAC event identity): https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html
