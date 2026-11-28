# Kiểm tra readiness mà không tạo quá nhiều bind hoặc truy vấn

## 1. Tình huống: một endpoint health có thể làm LDAP quá tải

Trong module **SPRING_DATA_LDAP**, ứng dụng Java kết nối với directory bằng Spring Data LDAP (`LdapRepository`, Object-Directory Mapping) hoặc Spring LDAP (`LdapTemplate`, `ContextSource`). Những thao tác thường gặp gồm tra cứu DN, tìm kiếm theo LDAP filter, đọc các thuộc tính theo `objectClass`/schema, thêm sửa xóa entry và xác thực người dùng.

Khi triển khai Spring Boot trên Kubernetes, người vận hành cần biết **pod có sẵn sàng nhận request mới không**. Một cách làm thiếu cân nhắc là để mỗi lời gọi HTTP `/actuator/health/readiness` tạo một kết nối LDAP mới, bind bằng tài khoản dịch vụ, rồi thực hiện tìm kiếm `(objectClass=*)` trên toàn directory.

Ví dụ, hệ thống có **120 pod** và kubelet gọi readiness mỗi **10 giây**. Nếu mỗi request health chạm LDAP đúng một lần, tổng tải bổ sung xấp xỉ:

```text
120 pod / 10 giây = 12 readiness HTTP request/giây

Mỗi readiness request:
  tạo LDAP context -> TLS/Bind (tùy pooling)
                   -> LDAP Search
                   -> đóng/trả context

=> Có thể thêm khoảng 12 chu kỳ kiểm tra LDAP/giây,
   chưa tính kiểm tra từ load balancer, monitoring hoặc con người.
```

Lưu ý **12 request/giây là mức trung bình minh họa**, không phải phép đo bắt buộc: probe có thể đến thành cụm, nhiều endpoint cùng kiểm tra và mức tái sử dụng connection khác nhau. Trong sự cố LDAP, các request health bị timeout sẽ đồng thời giữ thread, tạo retry và làm trầm trọng thêm quá tải.

**Bài toán thực sự:** kiểm tra được tình trạng phục vụ của ứng dụng, biết khi nào LDAP không thể dùng, nhưng **không biến hệ thống giám sát thành nguồn lưu lượng LDAP đáng kể**.

### Kết quả học tập

Sau bài học, bạn có thể:

1. Phân biệt **liveness**, **readiness**, **startup** và **dependency health**.
2. Hiểu Spring Boot Actuator `LdapHealthIndicator` và vì sao readiness mặc định không nên gọi mọi phụ thuộc ngoài.
3. Lựa chọn giữa readiness **chỉ dựa trạng thái ứng dụng** và readiness **phụ thuộc tín hiệu LDAP được làm mới định kỳ**.
4. Triển khai một `HealthIndicator` đọc **snapshot đã cache**, không tạo Bind/Search trên từng HTTP request.
5. Thiết kế một kiểm tra LDAP nhỏ: DN cố định, scope hẹp, một vài attribute, identity quyền tối thiểu, timeout có giới hạn.
6. Tính ngân sách probe theo số pod, chu kỳ và pooling; giám sát chi phí thực tế bằng metrics.
7. Kiểm thử outage, timeout, stale sample, nhiều request đồng thời, lỗi ACL/TLS và khả năng phục hồi.

## 2. Bốn loại tín hiệu thường bị nhầm

| Tín hiệu | Câu hỏi cần trả lời | Hành động phổ biến | Có nên truy vấn LDAP mỗi lần? |
| --- | --- | --- | --- |
| **Liveness** | Tiến trình này còn hoạt động đúng và có cần khởi động lại không? | Kubelet khởi động lại container khi thất bại đủ ngưỡng. | **Không.** LDAP là phụ thuộc ngoài; restart hàng loạt thường không sửa được LDAP. |
| **Readiness** | Instance này hiện có nên nhận lưu lượng mới không? | Kubernetes ngừng đưa pod vào tập endpoint phục vụ. | **Không mặc định.** Chỉ bổ sung tín hiệu LDAP nếu nó thực sự quyết định khả năng phục vụ. |
| **Startup** | Ứng dụng đã qua giai đoạn khởi tạo chưa? | Cho ứng dụng thêm thời gian khởi động trước khi liveness bắt đầu được xét. | Thường không cần poll directory ở mỗi lần startup probe. |
| **Dependency health** | LDAP endpoint, bind, một entry ổn định hoặc truy vấn nghiệp vụ có hoạt động không? | Alert, dashboard, điều tra, có thể tác động readiness theo policy. | Có thể cần I/O, nhưng phải được **giới hạn tần suất và độ lớn**. |

### 2.1. Liveness không nên phụ thuộc LDAP

Giả sử LDAP server của tổ chức bị ngắt mạng trong vài phút nhưng ứng dụng web vẫn đang chạy tốt. Nếu `/actuator/health/liveness` thực hiện LDAP lookup và trả `DOWN`, Kubernetes có thể restart **mọi pod cùng lúc**. Những pod mới lại khởi tạo TLS, context và connection pool, khiến backend LDAP chịu thêm áp lực đúng lúc đang gặp sự cố.

Spring Boot khuyến nghị **không đưa hệ thống ngoài vào liveness**. Liveness nên phản ánh trạng thái tiến trình JVM/ứng dụng, không phải mọi dependency.

### 2.2. Readiness không đồng nghĩa “mọi backend đều UP”

Có hai trường hợp khác nhau:

- Ứng dụng là **API xác thực chỉ có thể trả kết quả khi LDAP hoạt động**: một lỗi LDAP kéo dài có thể khiến instance không đáp ứng được nhiệm vụ chính. Đưa một tín hiệu LDAP **đã giới hạn tải** vào readiness có thể phù hợp.
- Ứng dụng là **cổng thông tin có cache, fallback và phần lớn API không cần LDAP**: cho tất cả pod `unready` khi LDAP lỗi có thể cắt đứt các chức năng vẫn phục vụ được. Trong trường hợp này, nên giữ readiness theo khả năng phục vụ cốt lõi và báo LDAP qua **dependency health/metrics** riêng.

Ngay cả khi LDAP là phụ thuộc bắt buộc, nếu **mọi instance dùng chung một directory** và bạn làm toàn bộ pod unready khi LDAP outage, Kubernetes Service có thể không còn endpoint nhận lưu lượng. Điều đó không giải quyết sự cố shared dependency; cần đánh giá chính sách trả lỗi, circuit breaker, fallback và mục tiêu khả dụng của sản phẩm.

## 3. Spring Boot Actuator: mặc định nào cần nhớ?

Spring Boot Actuator cung cấp các health contributor, trong đó có **`LdapHealthIndicator`** để kiểm tra LDAP server được cấu hình khi điều kiện auto-configuration phù hợp. Global endpoint `/actuator/health` có thể tổng hợp contributor này cùng những contributor khác.

Nhưng với Kubernetes probes, Spring Boot có **health groups chuyên biệt**:

```text
/actuator/health
    |
    +-- các contributor được cấu hình cho global health
    |     (có thể gồm ldap, db, diskSpace, ...)
    |
    +-- /actuator/health/liveness
    |     thường dựa vào livenessState
    |
    +-- /actuator/health/readiness
          thường dựa vào readinessState
```

**Theo tài liệu Spring Boot, các external dependency health checks không tự động được đưa vào readiness group mặc định.** Vì vậy, không nên nói rằng mỗi readiness probe của Spring Boot mặc định đều bind LDAP. Nguy cơ xuất hiện khi:

- Kubernetes gọi nhầm **`/actuator/health`** thay vì endpoint readiness riêng.
- Cấu hình `readiness.include` chứa `ldap` hoặc một custom indicator trực tiếp làm LDAP I/O.
- Một reverse proxy/monitoring kiểm tra global health quá thường xuyên.
- Một custom readiness controller gọi `LdapRepository.findByUid` hoặc `ldapTemplate.search` trên từng HTTP request.

### 3.1. Cấu hình đề xuất cho readiness thuần nội bộ

```yaml
management:
  endpoint:
    health:
      probes:
        enabled: true
        add-additional-paths: true
      show-details: never
  endpoints:
    web:
      exposure:
        include: health
```

Ý nghĩa:

- `management.endpoint.health.probes.enabled=true` chủ động bật nhóm health probes, kể cả ngoài môi trường Kubernetes khi cần.
- `add-additional-paths=true` đưa `/livez` và `/readyz` ra **cổng HTTP ứng dụng chính**, hữu ích nếu management server chạy cổng riêng.
- `show-details=never` tránh công khai chi tiết chẩn đoán; có thể cấu hình riêng cho nhóm hoặc phân quyền khi thực sự cần xem thông tin.
- Không khai báo `readiness.include: ldap`, nên endpoint readiness **không chủ động truy cập LDAP** chỉ để đáp ứng probe.

Nếu `/actuator/health` vẫn chứa LDAP indicator, một monitoring system gọi global health liên tục có thể tiếp tục gây I/O. Cần kiểm tra **mọi consumer của health endpoint**, không chỉ kubelet.

### 3.2. Bật/tắt built-in LDAP health một cách có chủ ý

```yaml
management:
  health:
    ldap:
      enabled: false
```

Cấu hình trên **tắt built-in LDAP health contributor** của Actuator khi không cần dùng nó trong global health. Nó **không tắt kết nối LDAP phục vụ nghiệp vụ**, và cũng không xóa các custom health indicators do ứng dụng tự khai báo.

Nếu cần một health check LDAP chuyên sâu cho vận hành, có thể giữ contributor đó ở **một health group riêng** và chỉ cho hệ thống monitoring có tần suất thấp truy cập; đừng dùng nó làm liveness hay readiness mặc định mà chưa tính ngân sách. Chi tiết API và property cần được xác nhận với **phiên bản Spring Boot của dự án**.

## 4. Chọn chiến lược readiness theo mức phụ thuộc LDAP

| Tình huống nghiệp vụ | Readiness khuyến nghị | Theo dõi LDAP |
| --- | --- | --- |
| API có fallback/cache, các endpoint chính vẫn chạy khi LDAP mất kết nối. | `readinessState` hoặc tín hiệu nội bộ khác; **không gate trên LDAP**. | Health group/metric/alert riêng, tần suất thấp. |
| API tra cứu directory bắt buộc cho **mọi** request phục vụ. | Cân nhắc gate readiness bằng **trạng thái LDAP đã cache và có TTL**. | Poll có giới hạn, đồng thời theo dõi lỗi thật của request. |
| Một số endpoint cần LDAP, số khác không. | Không dễ quy về một readiness Boolean; ưu tiên giữ instance và xử lý lỗi theo route. | Metrics theo dependency/route; cân nhắc tách service nếu yêu cầu khác biệt lớn. |
| Nhiều pod dùng chung một LDAP server. | Thận trọng với policy khiến **tất cả pod** bị loại khỏi Service. | Alert trung tâm, circuit breaker, rate limit, recovery. |
| Mỗi pod có LDAP sidecar/endpoint riêng, lỗi chỉ ảnh hưởng pod đó. | Gating readiness theo tín hiệu cục bộ có thể có ích. | Poll nhẹ, phân biệt lỗi local và shared. |

Đây là quyết định về **khả năng phục vụ**, không phải quyết định về việc directory có “đẹp” trong dashboard hay không.

### 4.1. Hai kiến trúc mẫu

**Mẫu A — readiness nhẹ hoàn toàn:**

```text
kubelet --GET /readyz--> Spring Boot readinessState -> HTTP 200/503
                                  |
                                  +-- không tạo LDAP connection

monitoring --định kỳ--> kiểm tra LDAP/metrics nghiệp vụ
```

**Mẫu B — readiness đọc snapshot của probe nền:**

```text
                                  +-------------------------+
                                  | background LDAP poll    |
                                  | mỗi 30 giây (minh họa)  |
                                  | 1 base-object lookup    |
                                  +-----------+-------------+
                                              |
                                              v
                                       AtomicReference
                                     {UP/DOWN,checkedAt}
                                              ^
                                              |
kubelet --GET /readyz--> readinessState + cached ldapReadiness
                             |
                             +-- không bind/search tại mỗi GET
```

Trong mẫu B, **số HTTP readiness probe không còn quyết định trực tiếp số LDAP operations**. Tuy nhiên, mỗi pod vẫn có một poller; số LDAP calls vẫn tăng theo số bản sao. Khi số pod rất lớn, nên cân nhắc một dependency monitor dùng chung, kết hợp tín hiệu lỗi từ request thật hoặc một policy tính readiness không bắt buộc poll LDAP ở từng pod.

## 5. Chi phí thực của một LDAP readiness check

Không được dùng `number of HTTP requests` làm số lượng LDAP Bind một cách máy móc. Một health check có thể dẫn đến nhiều loại công việc:

```text
HealthIndicator.health()
   |
   +-- tạo hoặc mượn DirContext
   |      +-- DNS / TCP connection (nếu kết nối mới)
   |      +-- TLS handshake       (nếu kết nối mới)
   |      +-- LDAP Bind          (tùy provider/credential/pooling)
   |
   +-- LDAP Search / getAttributes / lookup
   |
   +-- đóng context hoặc trả về pool
          +-- validation query (nếu cấu hình kiểm tra trên return)
```

Với Spring LDAP `LdapContextSource`, việc lấy context có thể cần một kết nối mới. Spring LDAP cũng có `PoolingContextSource` để giảm chi phí tạo kết nối, nhưng **pooling không làm search biến mất**; ngược lại, `testOnBorrow`, `testOnReturn` hay `testWhileIdle` có thể thực hiện thêm validation requests. Vì thế việc “bật pool rồi cứ probe nhiều” không phải phương án đủ.

### 5.1. Công thức lập ngân sách

Nếu:

- `N` = số pod đang chạy;
- `T` = số giây giữa các lần mỗi pod kiểm tra LDAP;
- mỗi lần chỉ gửi `Q` thao tác LDAP chủ động;

thì lưu lượng LDAP chủ động từ scheduled probes **xấp xỉ**:

```text
LDAP operations/second ~= (N / T) * Q

Ví dụ N=120 pod, T=30 giây, Q=1:
    120 / 30 * 1 = 4 LDAP operations/giây (trung bình)
```

Con số này **chưa gồm** Bind, connection validation, DNS, retry, nghiệp vụ thực, monitoring khác và tình trạng request bị dồn sau khi server phục hồi. Hãy theo dõi metrics tại **client và LDAP server** để điều chỉnh `T`, timeout và pool.

### 5.2. Vì sao thundering herd xuất hiện?

Khi nhiều pod được deploy cùng lúc, các scheduler có thể bắt đầu poll gần như cùng thời điểm. Dù trung bình là 4 operations/giây, một thời điểm vẫn có thể nhận hàng chục hoặc hàng trăm yêu cầu đồng loạt.

Giảm rủi ro bằng:

1. Khởi tạo lịch poll có **jitter** khác nhau giữa pod.
2. Dùng `fixedDelay` hoặc cơ chế single-flight để không chạy chồng kiểm tra trên cùng pod.
3. Hạn chế concurrency và timeout; không retry vô hạn.
4. Không để request HTTP readiness tự phát động một probe mới khi cache hết hạn.
5. Tính ngân sách cho cả autoscaling và startup burst, không chỉ số pod bình thường.

## 6. Thiết kế một phép kiểm tra LDAP đủ nhỏ

Một readiness check **không** nên:

- Search subtree `dc=example,dc=org` với `(objectClass=*)` rồi map tất cả entry.
- `findAll()` trên `LdapRepository` hoặc tải toàn bộ người dùng.
- Dùng wildcard filter từ dữ liệu người dùng để “chắc chắn có kết quả”.
- Thực hiện `bind`/`unbind` tạo xóa entry thử nghiệm.
- Đổi password, sửa group member hoặc ghi operational attributes.
- Follow referral ngoài allowlist, thử mọi LDAP URL hoặc tài khoản admin khi lỗi.
- Xác thực một người dùng thật trên mỗi probe.

### 6.1. Ba mức kiểm tra

| Kiểm tra | Ví dụ | Chứng minh được | Không chứng minh được |
| --- | --- | --- | --- |
| TCP connect tới host/port | Kết nối socket tới `ldap.example.org:636`. | Port đang nhận kết nối. | Bind, ACL, DN/search, schema hoặc chức năng LDAP. |
| Lấy context LDAP | `ContextSource.getReadOnlyContext()`. | Có thể tạo/lấy context với cấu hình hiện tại; tùy provider có thể kết nối lazy. | Không chắc entry được lookup hay quyền đọc hoạt động. |
| **Base-object read nhỏ** | Đọc `objectClass` ở một DN cố định đã biết. | TLS/Bind/đọc entry thử nghiệm hoạt động theo quyền hiện tại. | Không bảo đảm mọi query hoặc mọi server replica thành công. |

Một phép đọc **entry ổn định** là lựa chọn thường hợp lý nếu hệ thống phải kiểm tra end-to-end. Ví dụ:

```text
ContextSource base: dc=example,dc=org
Probe DN relative:  ou=people
Attribute requested: objectClass
Expected:           entry tồn tại, được phép đọc
```

`ou=people` là một OU cố định trong directory thử nghiệm. Nếu tài khoản bind được phép đọc nó, một lệnh `getAttributes` cho đúng DN và attribute là đủ để xác minh đường đi kỹ thuật. Trong môi trường khác, nên tạo **entry probe riêng** hoặc dùng entry ổn định vốn đã được cấp quyền, không phụ thuộc vào user/người thật.

**Lưu ý:** nếu server dùng ACL làm ẩn OU entry nhưng vẫn cho phép tìm kiếm con, phép thử trên `ou=people` có thể báo thất bại giả. Chọn DN, thuộc tính và identity theo policy thực tế; không mở rộng ACL chỉ để health check “xanh”.

### 6.2. JNDI không bảo đảm một GetAttributes luôn tương ứng một LDAP packet

Ở phía client, `DirContext.getAttributes(dn, names)` diễn đạt **đọc một entry và chỉ vài attribute**. LDAP provider có thể thực thi dưới dạng một LDAP Search scope base hoặc cơ chế tương đương; không đoán chính xác số request ở mức wire nếu chưa quan sát bằng server metrics/tracing. Mục tiêu thiết kế là **bounded work**, không khẳng định một phương thức Java luôn tạo đúng một packet.

## 7. Mẫu triển khai: readiness đọc kết quả được làm mới định kỳ

Mục này minh họa **Spring Boot 3.x, Java 17, Actuator và Spring LDAP**. Ý tưởng có thể áp dụng ở các phiên bản khác, nhưng package và SPI của Spring Boot 4.x có thể thay đổi; hãy đối chiếu tài liệu phiên bản đang sử dụng.

### 7.1. Các dependency

```xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-actuator</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-data-ldap</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
```

### 7.2. Bật scheduling

```java
package com.example.directory;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.scheduling.annotation.EnableScheduling;

@SpringBootApplication
@EnableScheduling
public class DirectoryApplication {
    public static void main(String[] args) {
        SpringApplication.run(DirectoryApplication.class, args);
    }
}
```

Lưu ý `@EnableScheduling` chỉ bật scheduler trong ứng dụng; bản thân nó không phát động truy vấn LDAP trên mỗi HTTP health request.

### 7.3. Custom HealthIndicator có snapshot an toàn giữa các thread

```java
package com.example.directory.health;

import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;
import javax.naming.NamingException;
import javax.naming.directory.Attributes;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.actuate.health.Health;
import org.springframework.boot.actuate.health.HealthIndicator;
import org.springframework.ldap.core.LdapTemplate;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

@Component("ldapReadiness")
public final class CachedLdapReadiness implements HealthIndicator {

    private record Sample(boolean ok, long completedAtNanos) {}

    private final LdapTemplate ldap;
    private final long maxAgeNanos;
    private final AtomicReference<Sample> latest =
        new AtomicReference<>();

    public CachedLdapReadiness(
            LdapTemplate ldap,
            @Value("${directory.readiness.max-age-ms:90000}")
            long maxAgeMillis) {
        if (maxAgeMillis <= 0) {
            throw new IllegalArgumentException("maxAge must be positive");
        }
        this.ldap = ldap;
        this.maxAgeNanos = TimeUnit.MILLISECONDS.toNanos(maxAgeMillis);
    }

    // fixedDelay: tính khoảng cách sau khi lần kiểm tra trước kết thúc.
    // Đây là background scheduler, KHÔNG chạy từ health().
    @Scheduled(
        fixedDelayString = "${directory.readiness.interval-ms:30000}",
        initialDelayString = "${directory.readiness.initial-delay-ms:0}"
    )
    public void refresh() {
        boolean ok;
        try {
            ldap.executeReadOnly(ctx -> {
                // DN tương đối với ContextSource.base.
                // Không search subtree, không tải danh sách người dùng.
                Attributes attrs = ctx.getAttributes(
                    "ou=people", new String[] {"objectClass"});
                if (attrs.get("objectClass") == null) {
                    throw new NamingException(
                        "Probe attribute is not readable");
                }
                return null;
            });
            ok = true;
        } catch (RuntimeException ex) {
            // Ghi metrics/log giới hạn và KHÔNG lộ secret/DN nhạy cảm.
            ok = false;
        }

        latest.set(new Sample(ok, System.nanoTime()));
    }

    @Override
    public Health health() {
        Sample sample = latest.get();
        if (sample == null) {
            return Health.down()
                .withDetail("reason", "notCheckedYet")
                .build();
        }

        long age = System.nanoTime() - sample.completedAtNanos();
        if (age < 0 || age > maxAgeNanos) {
            return Health.down()
                .withDetail("reason", "stale")
                .build();
        }

        return sample.ok()
            ? Health.up().build()
            : Health.down()
                .withDetail("reason", "lastCheckFailed")
                .build();
    }
}
```

Giải thích:

1. `@Component("ldapReadiness")` đặt tên HealthContributor là `ldapReadiness` để có thể đưa vào readiness group.
2. `@Scheduled(fixedDelayString=...)` định kỳ thực hiện LDAP operation độc lập với request HTTP. Dùng `fixedDelay` hạn chế chạy chồng các lần gọi do chính scheduler này; vẫn phải điều tra nếu một ứng dụng có nhiều scheduler/bean thực hiện cùng công việc.
3. `executeReadOnly` lấy context được cấu hình, đọc một **DN cố định** với một attribute và đóng/trả context theo Spring LDAP. Không gọi `LdapRepository.findAll()`.
4. `AtomicReference` cho phép thread của Actuator đọc sample nhất quán mà không phải chờ LDAP I/O.
5. `System.nanoTime()` là đồng hồ đơn điệu phù hợp đo **độ tuổi sample**; không dùng `LocalDateTime.now()` để tính TTL khi đồng hồ hệ thống có thể bị chỉnh.
6. Trước lần kiểm tra đầu tiên, hoặc khi sample quá cũ, indicator trả `DOWN`: **fail closed** theo policy mẫu. Đây là một lựa chọn cho hệ thống bắt buộc dùng LDAP, không phải lựa chọn chung cho mọi ứng dụng.
7. Một lần kiểm tra thất bại lập tức ghi sample `ok=false`. Sự dao động ngắn có thể được làm mượt bằng `failureThreshold` của Kubernetes; nếu cần hysteresis ở mức ứng dụng, hãy thiết kế và kiểm thử riêng.

**Không mặc định context “read-only” luôn bind bằng principal được cấu hình:** Spring LDAP có tùy chọn `anonymousReadOnly`. Nếu ứng dụng đã bật nó, phép thử có thể dùng anonymous identity và không chứng minh service-account bind hợp lệ. Phải kiểm tra chính xác `ContextSource`/`AuthenticationSource` đang sử dụng.

### 7.4. Độ tươi và thời điểm thất bại

Giả sử:

```text
interval = 30 giây
maxAge   = 90 giây

t=0s     LDAP OK;  sample=UP
t=10s    HTTP GET /readyz -> đọc cache UP
t=20s    HTTP GET /readyz -> đọc cache UP
t=30s    LDAP poll thất bại -> sample=DOWN
t=40s    HTTP GET /readyz -> đọc cache DOWN
```

Tham số không nên được chọn độc lập:

- `maxAge` phải đủ dài để tính đến thời gian một poll có thể chậm và scheduler bị bận, nhưng không quá dài khiến ứng dụng tiếp tục dùng sample “xanh” đã lỗi thời.
- `interval` không nên ngắn hơn thời gian trung bình hoặc tail latency của phép thử, kẻo chi phí probe tăng mạnh.
- **Cần timeout hữu hạn** ở LDAP client; nếu một poll bị treo rất lâu, scheduler không làm mới sample và TTL phải đánh dấu stale.
- Nếu đây là shared dependency thường xuyên chập chờn, có thể **không** đưa nó vào readiness group; chỉ cảnh báo và điều khiển lỗi trong nghiệp vụ.

## 8. Cấu hình Actuator để GET readiness không chạm LDAP

Khi chủ động chọn **mẫu B** (readiness có cached LDAP sample), cấu hình:

```yaml
spring:
  ldap:
    urls: ${LDAP_URL:ldaps://ldap.example.org:636}
    base: dc=example,dc=org
    username: ${LDAP_BIND_DN}
    password: ${LDAP_BIND_PASSWORD}

directory:
  readiness:
    interval-ms: 30000
    initial-delay-ms: 0
    max-age-ms: 90000

management:
  health:
    ldap:
      enabled: false   # Tắt built-in check đồng bộ, dùng custom snapshot.
  endpoint:
    health:
      probes:
        enabled: true
        add-additional-paths: true
      group:
        readiness:
          include: "readinessState,ldapReadiness"
      show-details: never
  endpoints:
    web:
      exposure:
        include: health
```

Với cấu hình minh họa:

| Endpoint | Nguồn thông tin | Có LDAP I/O ngay trong HTTP request? |
| --- | --- | --- |
| `/livez` hoặc `/actuator/health/liveness` | `livenessState`. | **Không**. |
| `/readyz` hoặc `/actuator/health/readiness` | `readinessState` + `ldapReadiness` **đọc sample**. | **Không**, vì `health()` chỉ đọc `AtomicReference`. |
| `/actuator/health` | Các contributor đang bật, gồm `ldapReadiness` nhưng không gồm built-in `ldap`. | Không từ custom cached indicator; contributor khác có thể có I/O riêng. |
| Scheduler 30 giây | `CachedLdapReadiness.refresh()`. | **Có**, một phép thử nhỏ mỗi chu kỳ. |

Nếu ứng dụng **không muốn LDAP quyết định readiness**, bỏ `ldapReadiness` khỏi `readiness.include` và dùng readiness mặc định; vẫn có thể thu metrics từ poll nền mà không gate lưu lượng. Đừng thêm `ldap` và `ldapReadiness` đồng thời vào cùng group, vì built-in check có thể khiến request readiness lại thực hiện LDAP I/O đồng bộ.

### 8.1. Vấn đề liên quan cổng management

Nếu actuator chạy cổng riêng, Kubernetes chỉ hỏi cổng management có thể nhận 200 ngay cả khi cổng ứng dụng đang lỗi. `add-additional-paths=true` giúp phơi bày `/readyz` và `/livez` trên cổng ứng dụng chính; kubelet nên sử dụng **đúng cổng HTTP của ứng dụng** theo kiến trúc triển khai.

Không mở các endpoint quản trị khác (`/env`, `/beans`, `/configprops`...) ra Internet chỉ để có health probe. Cần giới hạn network exposure và authentication/authorization phù hợp.

## 9. Kubernetes readinessProbe: nhịp HTTP khác nhịp LDAP

Ví dụ một phần của Deployment Kubernetes (cổng web container là `8080`):

```yaml
containers:
  - name: directory-api
    image: example/directory-api:demo
    ports:
      - containerPort: 8080
    livenessProbe:
      httpGet:
        path: /livez
        port: 8080
      periodSeconds: 15
      timeoutSeconds: 2
      failureThreshold: 3
    readinessProbe:
      httpGet:
        path: /readyz
        port: 8080
      periodSeconds: 10
      timeoutSeconds: 2
      failureThreshold: 3
    startupProbe:
      httpGet:
        path: /livez
        port: 8080
      periodSeconds: 5
      failureThreshold: 30
```

Đây là ví dụ **fragment**, không phải manifest Deployment hoàn chỉnh. Tần suất/ngưỡng cần điều chỉnh theo thời gian startup, p95 latency và SLO thực tế.

Với cached indicator:

- `periodSeconds: 10` tạo HTTP readiness request khoảng mỗi 10 giây trên mỗi pod.
- `directory.readiness.interval-ms: 30000` mới quyết định lịch **LDAP poll** mỗi pod.
- `timeoutSeconds: 2` giới hạn thời gian HTTP probe của Kubernetes, không thay cho timeout LDAP/JNDI bên trong scheduled worker.
- `failureThreshold: 3` giúp giảm flapping nếu có một vài lần readiness trả thất bại liên tiếp; nó không hạn chế số LDAP calls.
- `startupProbe` có thể cho pod thời gian khởi động lâu mà không bị liveness restart sớm; không thay thế cơ chế cached dependency sampling.

**Không đặt HTTP readiness interval quá ngắn rồi cấu hình health() tự poll khi stale**. Như vậy ngân sách LDAP lại gắn với lưu lượng HTTP và có thể xảy ra stampede khi cache hết hạn.

## 10. Timeout: bảo đảm phép kiểm tra có giới hạn

Một cache chỉ an toàn nếu background poll **không treo vô hạn**. LDAP client cần quản lý:

- **Connect timeout**: giới hạn chờ mở kết nối.
- **Read timeout**: giới hạn chờ phản hồi LDAP request.
- **Borrow wait timeout** nếu dùng context pool.
- **Quy tắc retry**: không gửi lại không giới hạn khi LDAP lỗi.
- **Resource cleanup**: đóng/trả `DirContext` và `NamingEnumeration` nếu có search.

JNDI LDAP provider thường dùng các environment properties:

```text
com.sun.jndi.ldap.connect.timeout = milliseconds
com.sun.jndi.ldap.read.timeout    = milliseconds
```

### 10.1. Ví dụ cấu hình LdapContextSource có timeout

Khi cần tự tạo `ContextSource` thay vì dùng bean auto-configured, có thể cấu hình:

```java
package com.example.directory.config;

import java.util.Map;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.ldap.core.support.LdapContextSource;

@Configuration
public class LdapClientConfig {

    @Bean
    LdapContextSource ldapContextSource(
            @Value("${spring.ldap.urls}") String ldapUrl,
            @Value("${spring.ldap.base}") String baseDn,
            @Value("${spring.ldap.username}") String bindDn,
            @Value("${spring.ldap.password}") String secret) {

        LdapContextSource source = new LdapContextSource();
        source.setUrl(ldapUrl);
        source.setBase(baseDn);
        source.setUserDn(bindDn);
        source.setPassword(secret);
        source.setBaseEnvironmentProperties(Map.of(
            "com.sun.jndi.ldap.connect.timeout", "1500",
            "com.sun.jndi.ldap.read.timeout", "2000"
        ));
        return source; // Spring quản lý vòng đời @Bean.
    }
}
```

**Đây là phương án cấu hình thủ công để minh họa timeout**, không bắt buộc tạo thêm bean này nếu dự án đã có `ContextSource` được cấu hình đầy đủ. Nếu dự án dùng nhiều `LdapTemplate`, cần xác minh template của health poll và template nghiệp vụ đang trỏ tới đúng source/identity; đừng tạo ambiguity do bean trùng.

**Các timeout JNDI không nhất thiết là giới hạn tuyệt đối toàn bộ hàm Java**: DNS, TLS, connection pool borrow, referral follow và các phần xử lý khác có thể cần thời gian riêng. Đo **thời gian thực tế** và bổ sung cơ chế deadline/cancellation phù hợp nếu môi trường yêu cầu SLO chặt.

### 10.2. Bắt ngoại lệ nào?

`LdapTemplate` thường chuyển `javax.naming.NamingException` của JNDI thành runtime exception thuộc `org.springframework.ldap`. Ví dụ:

```text
org.springframework.ldap.CommunicationException
org.springframework.ldap.NameNotFoundException
org.springframework.ldap.NoPermissionException
org.springframework.ldap.AuthenticationException
```

Với bài toán readiness, tất cả có thể làm **probe cụ thể** thất bại, nhưng nguyên nhân khác nhau:

- `CommunicationException`: mạng/TLS/server chậm hoặc unavailable.
- `AuthenticationException`: bind identity/secret có vấn đề.
- `NoPermissionException`: bind được nhưng thiếu quyền đọc DN/attribute probe.
- `NameNotFoundException`: DN probe không tồn tại hoặc base DN cấu hình sai.

Không coi mọi lỗi là “LDAP down toàn hệ thống”. Để điều tra, theo dõi **loại lỗi tổng quát** trong metrics/log nội bộ, không in bind password, raw LDAP diagnostic message hoặc dữ liệu người dùng ra health HTTP response.

## 11. Pooling không thay thế việc giới hạn probe

Spring LDAP hỗ trợ **`PoolingContextSource`**; mục tiêu là tái sử dụng connection/context và quản lý validation/eviction. Dù pooling giảm chi phí TCP/TLS/Bind của kết nối mới, mỗi health check vẫn có thể thực hiện LDAP request.

### 11.1. Ba ngộ nhận phổ biến

| Ngộ nhận | Thực tế |
| --- | --- |
| “Có pool thì mọi readiness check đều không tốn LDAP.” | Pool có thể tái sử dụng connection, nhưng `getAttributes`/Search vẫn là request tới server. |
| “`testOnBorrow=true` chỉ kiểm tra local memory.” | Pool validator có thể thực hiện LDAP Search để xác minh context còn hoạt động. |
| “Bật native JNDI pooling giải quyết mọi vấn đề.” | Native pooling có hạn chế về validation/configuration và các tình huống TLS/authentication; phải đánh giá theo Spring LDAP docs. |

Theo Spring LDAP, validator mặc định có thể làm một Search nhỏ ở base để kiểm tra context khi thiết lập validation. Nếu đồng thời cấu hình `testOnBorrow`, `testOnReturn`, `testWhileIdle` với tần suất dày, **một lượt health poll có thể phát sinh thêm LDAP operations** ngoài phép kiểm tra chính.

### 11.2. Đặc biệt lưu ý principal động

Nếu `ContextSource` thay credential theo HTTP user bằng `AuthenticationSource`, pooling có thể gây vấn đề cách ly identity nếu không được cấu hình tương thích. Spring LDAP cảnh báo về `PoolingContextSource` với authentication source thay đổi theo thread. Readiness nên dùng **một service account đọc tối thiểu**, không dùng tài khoản của người dùng thật.

### 11.3. Có cần giữ connection riêng cho health?

Không mặc định. Một pool/connection riêng có thể giúp isolation nhưng cũng làm tăng số session LDAP duy trì, tăng quản trị credential và phức tạp. Chỉ tách khi đã đo và có lý do rõ (ví dụ pool nghiệp vụ đôi lúc cạn và chính sách yêu cầu phân biệt “directory khỏe” với “pool của ứng dụng lỗi”).

Nếu readiness dùng một context khác hoàn toàn với nghiệp vụ, kết quả có thể **xanh giả**: health bind được, nhưng credential/ACL/pool của truy vấn thật lại lỗi. Hãy định nghĩa chính xác **độ bao phủ** mong muốn của phép thử và không gắn nhãn “application fully healthy” cho một ping hẹp.

## 12. Bảo mật readiness và tài khoản LDAP

### 12.1. Dùng quyền tối thiểu

Nếu phép thử là đọc `objectClass` ở `ou=people`, bind account chỉ cần quyền đủ để:

- Mở kết nối TLS và xác thực;
- Xác định/read entry probe theo ACL;
- Đọc `objectClass`, nếu policy server yêu cầu;
- Không cần quyền `ADD_ATTRIBUTE`/`REPLACE_ATTRIBUTE`/`REMOVE_ATTRIBUTE` hay xóa entry.

Không dùng tài khoản quản trị schema, không thử thay mật khẩu, không dùng `ldapTemplate.bind` tạo user “test” mỗi 10 giây.

### 12.2. Không bỏ qua TLS và hostname verification

```yaml
spring:
  ldap:
    urls: ldaps://ldap.example.org:636
```

Vẫn phải xác minh certificate chain, truststore và hostname/SAN. Việc sửa nhanh lỗi `PKIX path building failed` bằng trust manager “accept all” sẽ khiến cả health và request nghiệp vụ mất lớp bảo vệ TLS quan trọng.

Nếu dùng StartTLS, bảo đảm negotiation và kiểm chứng TLS thành công **trước** khi simple bind gửi credential. Không dùng `ldap://` plaintext trong mạng không đáng tin cậy chỉ để health check rẻ hơn.

### 12.3. Giữ health response ít thông tin

`Health.down().withDetail("reason","stale")` có ích cho vận hành, nhưng việc công khai chi tiết qua HTTP phải được kiểm soát. Không trả:

- LDAP bind DN đầy đủ trong một hạ tầng nhạy cảm;
- LDAP password hoặc properties JVM chứa secret;
- LDAP filter, DN người dùng, email hoặc kết quả search;
- Traces của `SSLHandshakeException` hay raw server diagnostic text.

Cấu hình `management.endpoint.health.show-details=never` cho probe được kubelet dùng; nếu cần dashboard chuyên sâu, dùng endpoint/metrics nội bộ có phân quyền.

## 13. Observability: đo chất lượng probe, không chỉ trả UP/DOWN

Một readiness check có thể quá chậm, quá thường xuyên hoặc stale mà vẫn thỉnh thoảng trả `UP`. Nên theo dõi:

| Metric/tín hiệu | Ý nghĩa | Lưu ý |
| --- | --- | --- |
| Số lần poll LDAP theo kết quả `success/failure` | Mức tải và tỉ lệ thất bại. | Không gắn DN, UID hay tên người dùng vào label. |
| Thời gian một lần poll | Nhìn p50/p95/p99 và timeout. | Phân biệt network/TLS/Bind/Search khi có khả năng instrument. |
| Tuổi của sample thành công gần nhất | Đo độ stale và lỗ hổng lịch chạy. | Không nhầm với thời điểm HTTP request. |
| Số lần readiness trả `DOWN` | Ảnh hưởng traffic/rolling deployments. | So sánh với lỗi LDAP thật và uptime ứng dụng. |
| Số LDAP Bind/Search/connection đang hoạt động | Phát hiện probe tạo tải bất thường. | Thu thập từ client + server/pool nếu có. |
| Pool borrowed/idle/wait/rejected | Phân biệt cạn pool với server down. | Đọc đúng exporter và phiên bản pool. |
| Kết quả request LDAP nghiệp vụ | Có thể phát hiện lỗi mà probe hẹp không thấy. | Phân loại theo loại operation, không theo filter có dữ liệu cá nhân. |

### 13.1. Đếm probe bằng Micrometer

Một cách tối giản để instrument scheduler:

```java
import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;

// Khởi tạo một lần (ví dụ trong constructor của probe service).
Counter success = Counter.builder("directory.ldap.probe")
    .tag("outcome", "success")
    .register(meterRegistry);

Counter failure = Counter.builder("directory.ldap.probe")
    .tag("outcome", "failure")
    .register(meterRegistry);

// Sau mỗi lần thực hiện LDAP poll:
if (ok) {
    success.increment();
} else {
    failure.increment();
}
```

Đây là **đoạn minh họa trích ra**, không phải một class Java độc lập: `meterRegistry` là bean được inject, `ok` là kết quả poll. Có thể dùng `Timer` để đo duration và `Gauge` để công bố tuổi sample. Trong metrics, tránh gắn label là raw `DN`, `uid`, filter, exception message hoặc hostname động vì gây **high cardinality** và có thể lộ thông tin.

### 13.2. Giới hạn log khi LDAP outage

Khi LDAP lỗi trong 30 phút, poll mỗi 30 giây có thể ném lỗi 60 lần cho mỗi pod. Đừng log stack trace đầy đủ ở mọi lần thất bại. Nên:

- Ghi **state transition** từ healthy → unhealthy và unhealthy → recovered;
- Có thể log periodic summary ở tần suất thấp;
- Ghi metrics tỉ lệ lỗi và loại lỗi;
- Không in credentials/giá trị attribute/DN nhạy cảm.

## 14. Kiểm thử: chứng minh GET /readyz không truy vấn LDAP

Unit test chỉ assert `health().getStatus()==UP` là **chưa đủ** cho yêu cầu của bài. Phải chứng minh **số lần gọi LDAP không tăng** khi kubelet gửi nhiều request readiness.

### 14.1. Test đơn vị với Mockito

Ví dụ JUnit 5 và Mockito, dùng class `CachedLdapReadiness` ở mục 7. Giả sử `LdapTemplate.executeReadOnly` không ném lỗi:

```java
package com.example.directory.health;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.times;
import static org.mockito.Mockito.verify;

import org.junit.jupiter.api.Test;
import org.springframework.boot.actuate.health.Status;
import org.springframework.ldap.core.LdapTemplate;

class CachedLdapReadinessTest {

    @Test
    void httpHealthReadsCachedStateInsteadOfCallingLdap() {
        LdapTemplate ldap = mock(LdapTemplate.class);
        CachedLdapReadiness indicator =
            new CachedLdapReadiness(ldap, 90_000L);

        assertThat(indicator.health().getStatus())
            .isEqualTo(Status.DOWN); // Chưa có poll đầu tiên.

        indicator.refresh(); // Một lần poll được mô phỏng.
        assertThat(indicator.health().getStatus())
            .isEqualTo(Status.UP);

        for (int i = 0; i < 100; i++) {
            assertThat(indicator.health().getStatus())
                .isEqualTo(Status.UP);
        }

        // Đã gọi LDAP đúng một lần, dù gọi health() 101 lần.
        verify(ldap, times(1)).executeReadOnly(any());
    }
}
```

Lưu ý Mockito mặc định trả `null` cho lời gọi generic, nên trong ví dụ `executeReadOnly` không ném lỗi và `refresh()` có thể đánh dấu `UP` mà không chạy lambda. Unit test **chỉ xác minh cơ chế cache và số lời gọi**, **không chứng minh** LDAP thực có thể kết nối hay thao tác đọc hợp lệ. Những điều này cần integration test.

### 14.2. Các trường hợp unit test khác

| Trường hợp | Kỳ vọng |
| --- | --- |
| Chưa từng chạy `refresh()` | `health()` trả `DOWN` theo chính sách fail-closed. |
| Poll thành công | Snapshot `UP`, HTTP chỉ đọc state. |
| LDAP mock ném lỗi | Snapshot `DOWN`, health không ném stack trace ra HTTP. |
| Nhiều thread gọi `health()` đồng thời | Không làm tăng số `executeReadOnly`. |
| Snapshot quá `maxAge` | `DOWN` (stale) dù lần kiểm tra cuối thành công. |
| Poll lần sau phục hồi | Chuyển lại `UP` sau khi sample mới thành công. |
| Config `max-age-ms<=0` | Fail ngay khi cấu hình sai, tránh cache vĩnh viễn. |

Để kiểm thử stale mà không phải `Thread.sleep(90_000)`, có thể refactor class để inject một **monotonic ticker** trong constructor dành cho test; ví dụ giữ một `LongSupplier` trả nanos và điều khiển nó qua fake clock. Đừng dùng test sleep dài khiến CI chậm và flakiness.

## 15. Integration test với LDAP test và Kubernetes

Integration test cần một **directory thử nghiệm** có:

- LDAP server qua LDAPS hoặc StartTLS hợp lệ;
- `dc=example,dc=org` và `ou=people` tồn tại;
- Tài khoản `svc-reader` có quyền đọc `objectClass` của OU;
- Cấu hình truststore và timeouts như môi trường dự kiến;
- Khả năng giả lập network failure/LDAP stop/TLS failure ở môi trường lab.

### 15.1. Ma trận kiểm thử

| Bài kiểm tra | Cách làm | Kết quả mong đợi |
| --- | --- | --- |
| Start ứng dụng bình thường | LDAP test hoạt động, scheduler chạy. | Readiness có thể bắt đầu `DOWN` trước sample, sau đó thành `UP`. |
| GET readiness liên tục | Gọi `/readyz` 100–1000 lần. | Số LDAP polls gần với lịch scheduler, **không** gần số GET. |
| DN probe tồn tại và được phép đọc | Dùng đúng bind identity. | Poll `UP`. |
| DN probe không tồn tại | Cố ý cấu hình sai trên test. | Poll `DOWN`; phân loại `NameNotFoundException`. |
| Bind secret sai/hết hạn | Secret test không hợp lệ. | Poll `DOWN`; không tự thử admin. |
| ACL chặn read | Tài khoản chỉ bind được, không đọc OU. | Poll `DOWN`; không coi server TCP “healthy” là đủ. |
| LDAPS certificate/SAN sai | Dùng endpoint test sai hostname. | Poll `DOWN`; TLS phải fail, không tắt verification. |
| LDAP server dừng | Dừng server trong lab. | Sample thất bại hoặc stale; HTTP readiness phản ánh policy trong ngưỡng dự kiến. |
| LDAP phục hồi | Khởi động lại server. | Poll tiếp theo thành công, readiness trở lại `UP`. |
| Pool cạn | Giới hạn pool trong test và tạo tải nghiệp vụ. | Thấy timeout/wait bounded và phân biệt pool exhaustion với LDAP outage. |
| 50 pod cùng startup | Test tải/chaos trong lab. | Không có burst Bind vượt ngân sách đã duyệt; áp dụng jitter nếu cần. |
| Scheduler bị giữ bởi tác vụ khác | Giả lập blocking scheduler. | Sau `maxAge`, trạng thái chuyển sang stale/down, không trả UP vô thời hạn. |
| LDAP mất nhưng app có fallback | Kiểm tra **mẫu A**, không gate LDAP. | Readiness vẫn theo khả năng phục vụ; dependency alert phát sinh riêng. |

### 15.2. Kiểm tra đầu ra HTTP

Ví dụ dùng `curl`:

```bash
curl -i http://localhost:8080/livez
curl -i http://localhost:8080/readyz
curl -i http://localhost:8080/actuator/health
```

Với Spring Boot health status thông thường, `UP` ánh xạ HTTP **200**, còn `DOWN` hoặc `OUT_OF_SERVICE` ánh xạ HTTP **503** theo cấu hình mặc định. `UNKNOWN` có thể ánh xạ 200 nếu chưa tùy chỉnh status mapping; do đó, ví dụ cached indicator cố tình dùng `DOWN` cho dữ liệu chưa có/stale khi policy yêu cầu fail-closed.

Trong bài thực hành, chạy cùng lúc kiểm tra **số LDAP Bind/Search thực tế từ server logs/metrics**. Chỉ thấy HTTP 200 hoặc 503 chưa chứng minh endpoint không gây quá nhiều LDAP traffic.

### 15.3. Load test phải tính cả health endpoint khác

Kubelet có thể chỉ gọi `/readyz`, nhưng monitoring vẫn có thể gọi `/actuator/health`, load balancer gọi `/health` tùy config hoặc dashboard truy cập health detail liên tục. Thu thập danh sách **các nguồn gọi**:

```text
Kubernetes readinessProbe -> /readyz
Kubernetes livenessProbe  -> /livez
Prometheus               -> /actuator/prometheus (nếu được bật và bảo vệ)
Monitoring               -> /actuator/health
Load balancer            -> endpoint được cấu hình riêng
```

Đừng mặc định `/actuator/prometheus`, khi được bật, chạy LDAP query; cần kiểm tra exporter/custom metrics và cách instrumentation được viết. Mục tiêu là không có **health hoặc metrics endpoint nào vô tình làm LDAP I/O tỷ lệ thuận với lưu lượng scrape**.

## 16. Rủi ro khi cache readiness

Cache giảm tải nhưng có những đánh đổi cần ghi rõ:

### 16.1. False positive: cache vẫn UP trong lúc LDAP vừa lỗi

Nếu LDAP lỗi ngay sau poll thành công, `health()` có thể tiếp tục trả `UP` cho đến lần poll kế tiếp hoặc TTL. Điều này chấp nhận được với nhiều hệ thống nếu nghiệp vụ đã có timeout/circuit breaker và thời gian phát hiện được đặt phù hợp SLO; nếu không thể chấp nhận, cần thiết kế khác, **không đơn giản tăng tần suất vô hạn**.

### 16.2. False negative: một query probe thất bại nhưng nghiệp vụ vẫn được

Ví dụ:

- Probe đọc `ou=people` nhưng một ACL thay đổi khiến entry OU bị ẩn, trong khi search theo user vẫn thành công.
- Một replica LDAP tạm thời lỗi, nhưng các endpoint khác hoạt động.
- Một network glitch khiến poll thất bại đúng một lần, dù request nghiệp vụ vẫn có retry hợp lý.

Vì vậy, cần biết **probe đo được điều gì** và không gắn nhãn “toàn directory unavailable” chỉ từ một lỗi đơn lẻ.

### 16.3. Stale sample khi scheduler bị kẹt

Nếu scheduler không thể chạy, một cache `UP` không có TTL sẽ gây xanh giả vô thời hạn. Chính vì thế code mẫu kiểm tra `completedAtNanos` và chuyển `DOWN` khi stale.

### 16.4. Shared outage và cascading unready

Nếu tất cả pod dùng chung LDAP, một outage có thể khiến tất cả cùng bị loại khỏi Kubernetes Service. Hãy so sánh hai chiến lược:

| Readiness gate LDAP | Không gate LDAP |
| --- | --- |
| Pod `unready` khi LDAP thất bại; thích hợp nếu request **không có cách phục vụ**. | Pod vẫn nhận lưu lượng; thích hợp khi có fallback hoặc vẫn có route sử dụng được. |
| Có thể khiến toàn bộ Service không có endpoint khi LDAP dùng chung lỗi. | Client có thể nhận lỗi nghiệp vụ/HTTP 503 nhưng vẫn truy cập được các route khác. |
| Cần poll bounded, TTL và recovery policy. | Cần alert/circuit breaker/metrics để không che outage. |

Không có một lựa chọn đúng cho mọi sản phẩm. Lựa chọn phải xuất phát từ **SLO, cấu trúc API và khả năng phục vụ khi LDAP mất**.

## 17. Các lỗi thiết kế phổ biến và cách khắc phục

| Cách làm sai | Hậu quả | Cách làm phù hợp hơn |
| --- | --- | --- |
| Gọi `ldapTemplate.search` trong `HealthIndicator.health()` mỗi lần HTTP GET. | Request readiness tạo tải LDAP tỷ lệ với tần suất probe. | Dùng state nội bộ hoặc cached background poll. |
| Đưa LDAP vào **liveness**. | LDAP outage làm restart hàng loạt pod. | Giữ liveness theo trạng thái JVM/ứng dụng. |
| Dùng `/actuator/health` làm kubelet readiness mà không xem contributor. | Có thể vô tình thực hiện check LDAP/db/remote service. | Dùng `/readyz` hoặc `/actuator/health/readiness`. |
| Dùng `findAll()` làm “health check”. | Search subtree rộng, tăng CPU/index/network ở directory. | Đọc một DN cố định với attribute nhỏ. |
| Tạo user rồi xóa lại để test ghi. | Có thể gây audit noise, tác động replication, lỗi dọn dữ liệu. | Kiểm tra read-only; tách write diagnostics chuyên biệt. |
| Dùng admin bind cho probe. | Credential quá rộng, khó audit, nguy cơ lớn nếu lộ. | Service account quyền đọc tối thiểu. |
| Dùng GET readiness tạo query khi cache hết hạn. | Stampede vào LDAP đúng thời điểm backend chậm. | Trả trạng thái stale theo policy; để scheduler làm mới. |
| Không đặt timeout. | Poll bị treo, thread/pool cạn, sample không cập nhật. | Giới hạn connect/read/borrow, dùng TTL. |
| Bật pool validation dày, bỏ qua chi phí query. | Lượng LDAP Search/Bind không giảm như dự đoán. | Đo lưu lượng server và cấu hình pool hợp lý. |
| Trả `UP` vô thời hạn sau sample cuối. | False positive trong outage. | `maxAge` và fail-closed khi stale nếu readiness phụ thuộc LDAP. |
| Cache global dùng chung mọi pod nhưng không xác minh local connectivity. | Không phát hiện lỗi network/credential riêng từng pod. | Phân biệt shared health với instance-local health. |
| Cho mỗi pod poll đúng lúc deploy. | Thundering herd. | Jitter và giới hạn concurrency. |
| Log stack trace/secret mỗi 10 giây. | Lộ dữ liệu, log storm. | Log state transition và metrics low-cardinality. |

## 18. Bài tập và checklist thực hành

### Bài tập

1. Một deployment có 80 pod, readiness gọi mỗi 5 giây. Nếu mỗi readiness request tạo một LDAP Search, ước lượng số Search/giây. Sau đó đề xuất chu kỳ poll độc lập để giảm tải ít nhất bốn lần.
2. Giải thích vì sao `/actuator/health` và `/actuator/health/readiness` có thể tạo **chi phí LDAP khác nhau** dù cùng do Actuator cung cấp.
3. Thiết kế readiness cho hai ứng dụng: (a) dịch vụ bắt buộc xác thực LDAP mọi request, (b) cổng thông tin có nhiều route không cần LDAP. Chọn có/không gate LDAP và giải thích.
4. Viết `HealthIndicator` trả snapshot bằng `AtomicReference`. Chứng minh `health()` không dùng `LdapTemplate`/`LdapRepository`.
5. So sánh `getReadOnlyContext()` với `getAttributes("ou=people",{"objectClass"})`. Cách nào chứng minh được nhiều hơn về tình trạng bind và ACL?
6. Tạo unit test gọi `health()` 100 lần sau một `refresh()`; dùng Mockito chứng minh LDAP bị gọi đúng một lần.
7. Thiết kế test stale cache không dùng `Thread.sleep` dài. Đề xuất inject đồng hồ đơn điệu giả vào class để điều khiển TTL.
8. Một LDAP server có nhiều replica và thỉnh thoảng bị lỗi. Hãy phân tích tại sao một poll failure không tự chứng minh cả LDAP service down, và cách thiết kế ngưỡng/metrics.
9. Tìm một trường hợp bật `testOnBorrow` và `testOnReturn` làm tăng số LDAP operations của health poll; giải thích cách đo.
10. Triển khai Kubernetes readiness dùng `/readyz` trên cổng ứng dụng chính. Xác minh source của readiness không chứa built-in `ldap` synchronous health contributor.
11. Đối chiếu lỗi `AuthenticationException`, `NameNotFoundException`, `NoPermissionException` và `CommunicationException` trong phép thử LDAP. Vì sao không nên sửa mọi lỗi bằng tài khoản admin?
12. Thiết kế dashboard gồm poll count, poll duration, last-success age, real business LDAP error rate và số pod unready. Các label nào không nên thêm?

### Checklist trước khi đưa vào môi trường thật

- [ ] Đã chọn rõ readiness có cần phụ thuộc LDAP hay không.
- [ ] **Liveness không gọi LDAP.**
- [ ] Kubernetes gọi đúng `/readyz`, không vô tình dùng global health.
- [ ] Nếu dùng cached LDAP indicator, `health()` **không tạo LDAP I/O**.
- [ ] Poll chạy theo lịch có giới hạn, không retry vô hạn.
- [ ] Có cấu hình connect/read/pool-borrow timeout và bảo đảm giải phóng context.
- [ ] Probe dùng DN/entry ổn định, chỉ yêu cầu ít attribute, không quét subtree.
- [ ] Probe account có quyền tối thiểu, không dùng admin.
- [ ] LDAPS/StartTLS, truststore và hostname verification hoạt động.
- [ ] `maxAge` tránh sample xanh lỗi thời; chính sách stale đã được kiểm thử.
- [ ] Có xem xét thundering herd khi autoscale/rollout nhiều pod.
- [ ] Số Bind/Search đo được trên LDAP server nằm trong ngân sách.
- [ ] Không log credential, raw DN/UID hoặc LDAP diagnostic chứa dữ liệu nhạy cảm.
- [ ] Có test outage, ACL, TLS, phục hồi và đồng thời.
- [ ] Có alert/metrics riêng ngay cả khi không gate readiness trên LDAP.

## 19. Tài liệu tham khảo

- [Spring Boot Actuator — Endpoints, Health Groups và Kubernetes Probes](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html): `LdapHealthIndicator`, readiness/liveness groups, kiểm tra external state và HTTP status mapping.
- [Spring Boot Actuator — Monitoring and Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html): Micrometer và các quan sát vận hành.
- [Spring LDAP — Configuration](https://docs.spring.io/spring-ldap/reference/configuration.html): `ContextSource`, `LdapTemplate`, base DN, pooled connections và identity.
- [Spring LDAP — Pooling Support](https://docs.spring.io/spring-ldap/reference/pooling.html): `PoolingContextSource`, connection validation, `testOnBorrow`/`testOnReturn` và chi phí LDAP requests.
- [Spring LDAP API — AbstractContextSource](https://docs.spring.io/spring-ldap/docs/current/api/org/springframework/ldap/core/support/AbstractContextSource.html): `getReadOnlyContext`, `setBaseEnvironmentProperties` và anonymous read-only.
- [Spring LDAP API — LdapTemplate](https://docs.spring.io/spring-ldap/docs/current/api/org/springframework/ldap/core/LdapTemplate.html): `executeReadOnly`, `lookup`, `search` và quản lý context.
- [Spring Data LDAP Reference](https://docs.spring.io/spring-data/ldap/reference/): repository, ODM và LDAP query.
- [Kubernetes — Liveness, Readiness and Startup Probes](https://kubernetes.io/docs/concepts/configuration/liveness-readiness-startup-probes/): ý nghĩa các loại probe.
- [Kubernetes — Configure Liveness, Readiness and Startup Probes](https://kubernetes.io/docs/tasks/configure-pod-container/configure-liveness-readiness-startup-probes/): `periodSeconds`, `timeoutSeconds` và `failureThreshold`.
- [Oracle JNDI LDAP — Connection Properties](https://docs.oracle.com/javase/jndi/tutorial/ldap/connect/config.html): timeout và cấu hình provider.
- [Micrometer — Counters](https://docs.micrometer.io/micrometer/reference/concepts/counters.html): đếm kết quả probe với label có cardinality thấp.
- [RFC 4511 — LDAP Protocol](https://www.rfc-editor.org/rfc/rfc4511): Search, Bind và result codes; tránh làm nhiều thao tác LDAP không cần thiết.
- [RFC 4513 — LDAP Authentication Methods and Security Mechanisms](https://www.rfc-editor.org/rfc/rfc4513): an toàn Bind và kết nối TLS.
