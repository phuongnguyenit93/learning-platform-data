# Xây dựng HealthIndicator cho thành phần đặc thù của ứng dụng

## 1. Khi kết nối khỏe nhưng chức năng vẫn chưa dùng được

Giả sử một ứng dụng tính phí vận chuyển tải bảng quy tắc tính phí vào bộ nhớ. Cơ sở dữ liệu vẫn kết nối được, Redis vẫn phản hồi và tiến trình vẫn phục vụ HTTP, nhưng bảng quy tắc chưa được tải hoặc đã quá cũ. Khi đó, những phép kiểm tra hạ tầng có sẵn chưa trả lời được câu hỏi: **thành phần tính phí đã có dữ liệu đủ điều kiện để hoạt động hay chưa?**

Bộ kiểm tra sức khỏe tùy chỉnh (`HealthIndicator`) diễn đạt điều kiện đó bằng mã của ứng dụng. Nó đọc bằng chứng từ một thành phần cụ thể, đối chiếu với tiêu chí đã định và trả về một đối tượng `Health` gồm trạng thái cùng các chi tiết cần thiết.

Không nên tạo indicator chỉ để tăng số thành phần trong JSON. Hãy tạo khi có một điều kiện vận hành quan trọng mà các indicator hiện có chưa quan sát được, chẳng hạn dữ liệu tham chiếu đã được nạp, bộ máy xử lý đã khởi tạo hoặc một kết nối chuyên dụng đã sẵn sàng.

Trong bài này, ta xây dựng indicator `rateCatalog` cho bảng quy tắc tính phí. Ví dụ dùng **Java 21 và Spring Boot 3.3.0**, gồm phần kiểm tra chạy độc lập và phần đăng ký vào Actuator. Chính sách “dữ liệu tối đa được cũ bao lâu” là quyết định của ví dụ, không phải mặc định do Spring Boot quy định.

## 2. Xác định hợp đồng trước khi viết mã

Một indicator hữu ích phải có câu trả lời rõ ràng cho bốn câu hỏi:

1. **Kiểm tra thành phần nào?** Bảng quy tắc đang nằm trong bộ nhớ của chính tiến trình này.
2. **Bằng chứng nào được đọc?** Bản chụp gồm số quy tắc và thời điểm cập nhật thành công gần nhất.
3. **Khi nào đạt yêu cầu?** Có dữ liệu, có ít nhất một quy tắc, thời gian cập nhật không nằm trong tương lai và tuổi dữ liệu không vượt ngưỡng.
4. **Kết quả không chứng minh điều gì?** Không chứng minh mọi công thức tính phí đúng, mọi đơn hàng tính được hoặc nguồn tải dữ liệu bên ngoài đang truy cập được.

Ví dụ chọn ngưỡng năm phút và thứ tự đánh giá sau:

| Điều kiện | Trạng thái | Mã lý do |
| --- | --- | --- |
| Chưa có bản chụp | `OUT_OF_SERVICE` | `NOT_LOADED` |
| Bản chụp không có quy tắc nào | `DOWN` | `EMPTY_CATALOG` |
| Thời điểm cập nhật nằm trong tương lai | `DOWN` | `CLOCK_SKEW` |
| Tuổi dữ liệu lớn hơn năm phút | `DOWN` | `STALE_CATALOG` |
| Đủ dữ liệu và tuổi dữ liệu không quá năm phút | `UP` | `READY` |

Ở đây, `OUT_OF_SERVICE` biểu đạt việc thành phần chưa đủ điều kiện phục vụ; `DOWN` biểu đạt bản chụp đã có nhưng không đạt tiêu chí. Đội phát triển có thể chọn chính sách khác nếu yêu cầu nghiệp vụ khác, nhưng phải diễn giải nhất quán và kiểm thử được.

Ngưỡng bao gồm cả điểm biên: **đúng năm phút vẫn `UP`; quá năm phút mới `DOWN`**. Một chi tiết nhỏ như dấu `>` hay `>=` sẽ thay đổi hành vi thật, nên cần nêu trước thay vì quyết định ngẫu nhiên trong mã.

## 3. Hợp đồng HealthIndicator và lớp hỗ trợ

`HealthIndicator` là interface thuộc gói `org.springframework.boot.actuate.health`. Phương thức trung tâm là:

```java
Health health();
```

Đây là chữ ký phương thức, không phải một chương trình Java độc lập. Implementation cần trả về `Health`, không trả trực tiếp chuỗi `"UP"`, không trả `null` và không trả `ResponseEntity`.

Hai cách triển khai thường dùng là:

| Cách | Phần ứng dụng phải tự làm |
| --- | --- |
| `implements HealthIndicator` | Cài đặt `health()`, tạo `Health` và xử lý lỗi phù hợp. |
| `extends AbstractHealthIndicator` | Cài đặt `doHealthCheck(Health.Builder)`; lớp cha tạo builder, gọi phép kiểm tra và chuyển `Exception` thoát ra thành `DOWN`. |

Bài dùng cách thứ hai. `AbstractHealthIndicator` bắt `Exception`, không phải mọi `Throwable`; nó cũng không đặt timeout cho mã bên trong. Không được dựa vào lớp cha để xử lý một lời gọi mạng treo vô hạn. Có thể xem chính xác cơ chế tại [mã AbstractHealthIndicator của Spring Boot 3.3.0](https://raw.githubusercontent.com/spring-projects/spring-boot/v3.3.0/spring-boot-project/spring-boot-actuator/src/main/java/org/springframework/boot/actuate/health/AbstractHealthIndicator.java).

Một lời gọi health cần tạo kết quả cho lần quan sát hiện tại. Không giữ `Health.Builder` dùng chung giữa nhiều request; builder của từng lần gọi phải độc lập để tránh trộn trạng thái và chi tiết giữa các luồng.

## 4. Tạo ví dụ có thể biên dịch và chạy

Đây là **dự án Maven độc lập**. Tạo các tệp đúng tên và đường dẫn bên dưới. Phần mô hình, indicator và chương trình kiểm tra không cần chạy web server; phần ứng dụng Spring Boot bổ sung ở mục 6 sẽ đưa cùng indicator vào Actuator.

### 4.1. Khai báo thư viện

Tệp `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.0</version>
        <relativePath/>
    </parent>
    <groupId>learning</groupId>
    <artifactId>custom-health-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>21</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-actuator</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

### 4.2. Thành phần được quan sát

Tệp `src/main/java/learning/customhealth/RateCatalog.java`:

```java
package learning.customhealth;

import java.time.Instant;
import java.util.Objects;
import java.util.concurrent.atomic.AtomicReference;

public final class RateCatalog {

    public record Snapshot(int ruleCount, Instant lastSuccessfulRefresh) {
        public Snapshot {
            if (ruleCount < 0) {
                throw new IllegalArgumentException("ruleCount must not be negative");
            }
            Objects.requireNonNull(lastSuccessfulRefresh, "lastSuccessfulRefresh");
        }
    }

    private final AtomicReference<Snapshot> current = new AtomicReference<>();

    public Snapshot snapshot() {
        return current.get();
    }

    public void publish(int ruleCount, Instant lastSuccessfulRefresh) {
        current.set(new Snapshot(ruleCount, lastSuccessfulRefresh));
    }
}
```

`Snapshot` là bản chụp bất biến: số quy tắc và thời điểm cập nhật đi cùng nhau. `AtomicReference` cho phép luồng tải dữ liệu công bố một bản chụp hoàn chỉnh, còn luồng health đọc một tham chiếu nhất quán. Indicator sẽ đọc `snapshot()` đúng một lần cho mỗi phép kiểm tra, tránh ghép số lượng của bản cũ với thời gian của bản mới.

Trong ứng dụng thật, `publish(...)` chỉ được gọi sau khi bộ tải đã lấy và kiểm tra thành công một bộ quy tắc. Ví dụ rút gọn chỉ lưu metadata đủ để học cơ chế health; nó chưa triển khai bộ quy tắc tính phí hoặc bộ tải dữ liệu bên ngoài.

Nếu một lần tải thất bại, không được cập nhật `lastSuccessfulRefresh` như thể đã thành công. Nếu làm vậy, health sẽ liên tục báo dữ liệu mới dù bảng quy tắc thật không được làm mới.

### 4.3. Indicator tùy chỉnh

Tệp `src/main/java/learning/customhealth/RateCatalogHealthIndicator.java`:

```java
package learning.customhealth;

import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.util.Objects;

import org.springframework.boot.actuate.health.AbstractHealthIndicator;
import org.springframework.boot.actuate.health.Health;

public final class RateCatalogHealthIndicator extends AbstractHealthIndicator {

    private final RateCatalog catalog;
    private final Clock clock;
    private final Duration maxAge;

    public RateCatalogHealthIndicator(RateCatalog catalog, Clock clock, Duration maxAge) {
        this.catalog = Objects.requireNonNull(catalog, "catalog");
        this.clock = Objects.requireNonNull(clock, "clock");
        this.maxAge = Objects.requireNonNull(maxAge, "maxAge");
        if (maxAge.isZero() || maxAge.isNegative()) {
            throw new IllegalArgumentException("maxAge must be positive");
        }
    }

    @Override
    protected void doHealthCheck(Health.Builder builder) {
        RateCatalog.Snapshot snapshot = catalog.snapshot();
        builder.withDetail("maxAgeSeconds", maxAge.toSeconds());

        if (snapshot == null) {
            builder.outOfService().withDetail("reason", "NOT_LOADED");
            return;
        }

        builder.withDetail("ruleCount", snapshot.ruleCount());
        if (snapshot.ruleCount() == 0) {
            builder.down().withDetail("reason", "EMPTY_CATALOG");
            return;
        }

        Duration age = Duration.between(snapshot.lastSuccessfulRefresh(), Instant.now(clock));
        builder.withDetail("ageSeconds", age.toSeconds());
        if (age.isNegative()) {
            builder.down().withDetail("reason", "CLOCK_SKEW");
            return;
        }
        if (age.compareTo(maxAge) > 0) {
            builder.down().withDetail("reason", "STALE_CATALOG");
            return;
        }

        builder.up().withDetail("reason", "READY");
    }
}
```

Những lựa chọn đáng chú ý:

- **Nhận thành phần qua constructor:** indicator quan sát đúng `RateCatalog` mà ứng dụng cung cấp, không tự tạo một catalog rỗng khác.
- **Nhận `Clock`:** kiểm thử điều khiển được thời gian, không phải chờ thật năm phút hoặc dùng `Thread.sleep()`.
- **Kiểm tra cấu hình khi tạo đối tượng:** ngưỡng không hợp lệ là lỗi cấu hình cần lộ sớm, không phải một lần health ngẫu nhiên trả `DOWN`.
- **So sánh `Duration`:** việc kết luận quá hạn giữ độ chính xác của thời gian; `ageSeconds` chỉ là chi tiết chẩn đoán đã làm tròn xuống theo đơn vị giây.
- **Chỉ đọc:** `doHealthCheck` không gọi `publish`, không tải lại dữ liệu và không tự sửa đồng hồ.

Các chi tiết như `reason`, `ruleCount` và `ageSeconds` là hợp đồng do ứng dụng này định nghĩa. Actuator không hiểu rằng `STALE_CATALOG` quan trọng hơn `EMPTY_CATALOG`; trạng thái do mã của indicator chọn mới được dùng để tổng hợp health.

## 5. Kiểm tra các nhánh bằng thời gian cố định

Tệp `src/main/java/learning/customhealth/RateCatalogHealthIndicatorDemo.java`:

```java
package learning.customhealth;

import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.ZoneOffset;

import org.springframework.boot.actuate.health.Health;
import org.springframework.boot.actuate.health.Status;

public class RateCatalogHealthIndicatorDemo {

    private static final Instant NOW = Instant.parse("2026-01-01T00:10:00Z");
    private static final Clock CLOCK = Clock.fixed(NOW, ZoneOffset.UTC);
    private static final Duration MAX_AGE = Duration.ofMinutes(5);

    public static void main(String[] args) {
        check("notLoaded", null, Status.OUT_OF_SERVICE, "NOT_LOADED");
        check("empty", new RateCatalog.Snapshot(0, NOW), Status.DOWN, "EMPTY_CATALOG");
        check("fresh", new RateCatalog.Snapshot(12, NOW.minusSeconds(30)), Status.UP, "READY");
        check("boundary", new RateCatalog.Snapshot(12, NOW.minusSeconds(300)), Status.UP, "READY");
        check("pastBoundary", new RateCatalog.Snapshot(12, NOW.minusSeconds(300).minusNanos(1)),
                Status.DOWN, "STALE_CATALOG");
        check("stale", new RateCatalog.Snapshot(12, NOW.minusSeconds(301)), Status.DOWN, "STALE_CATALOG");
        check("future", new RateCatalog.Snapshot(12, NOW.plusSeconds(1)), Status.DOWN, "CLOCK_SKEW");
    }

    private static void check(String name, RateCatalog.Snapshot input, Status expected, String reason) {
        RateCatalog catalog = new RateCatalog();
        if (input != null) {
            catalog.publish(input.ruleCount(), input.lastSuccessfulRefresh());
        }
        RateCatalog.Snapshot before = catalog.snapshot();
        RateCatalogHealthIndicator indicator = new RateCatalogHealthIndicator(catalog, CLOCK, MAX_AGE);
        Health result = indicator.health();

        if (!expected.equals(result.getStatus()) || !reason.equals(result.getDetails().get("reason"))) {
            throw new AssertionError("Unexpected result for " + name + ": " + result);
        }
        if (catalog.snapshot() != before) {
            throw new AssertionError("Health check changed the catalog");
        }
        System.out.println(name + "=" + result.getStatus().getCode() + " (" + reason + ")");
    }
}
```

Trong thư mục chứa `pom.xml`, kiểm tra `mvn -version` đang dùng JDK 21 rồi chạy:

```shell
mvn compile dependency:build-classpath "-Dmdep.outputFile=target/classpath.txt"
```

Trên PowerShell, chạy tiếp:

```powershell
$dependencyClasspath = (Get-Content -Raw -LiteralPath 'target/classpath.txt').Trim()
java -cp "target/classes;$dependencyClasspath" learning.customhealth.RateCatalogHealthIndicatorDemo
```

Trên Linux/macOS, phần chạy tương đương là:

```shell
java -cp "target/classes:$(cat target/classpath.txt)" learning.customhealth.RateCatalogHealthIndicatorDemo
```

Đây là mã có thư viện Spring Boot, nên `javac RateCatalogHealthIndicator.java` đơn lẻ sẽ thiếu classpath. Maven đã thực hiện phần biên dịch Java và giải quyết thư viện; lệnh `java` ở trên chỉ chạy chương trình kiểm tra đã biên dịch.

Stdout của chương trình kiểm tra là:

```text
notLoaded=OUT_OF_SERVICE (NOT_LOADED)
empty=DOWN (EMPTY_CATALOG)
fresh=UP (READY)
boundary=UP (READY)
pastBoundary=DOWN (STALE_CATALOG)
stale=DOWN (STALE_CATALOG)
future=DOWN (CLOCK_SKEW)
```

Trường hợp `pastBoundary` cố ý chỉ quá hạn một nano giây. Nó chứng minh logic không làm tròn tuổi dữ liệu về số giây trước khi quyết định trạng thái. Trong trường hợp đó, `ageSeconds` vẫn có thể là `300` dù trạng thái đã `DOWN`; chi tiết này có độ phân giải thấp hơn phép so sánh. Nếu hệ thống cần chẩn đoán sát điểm biên, có thể bổ sung chi tiết thời lượng với độ chính xác phù hợp.

Chương trình cũng kiểm tra rằng gọi health không thay thế bản chụp catalog. Đây là bằng chứng về tính chỉ đọc trong ví dụ, không phải một bài kiểm thử mọi tình huống đồng thời của ứng dụng thật.

## 6. Đăng ký cùng indicator vào Spring Boot Actuator

Chỉ tạo một đối tượng bằng `new` trong chương trình kiểm tra chưa khiến Actuator biết tới nó. Cần đăng ký đối tượng đó thành bean trong Spring context.

### 6.1. Tạo ứng dụng và các bean

Tệp `src/main/java/learning/customhealth/CustomHealthApplication.java`:

```java
package learning.customhealth;

import java.time.Clock;
import java.time.Duration;
import java.time.Instant;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class CustomHealthApplication {

    public static void main(String[] args) {
        SpringApplication.run(CustomHealthApplication.class, args);
    }

    @Bean
    RateCatalog rateCatalog() {
        return new RateCatalog();
    }

    @Bean
    Clock healthClock() {
        return Clock.systemUTC();
    }

    @Bean
    @ConditionalOnProperty(prefix = "app.health.rate-catalog", name = "enabled",
            havingValue = "true", matchIfMissing = true)
    RateCatalogHealthIndicator rateCatalogHealthIndicator(
            RateCatalog catalog,
            Clock clock,
            @Value("${app.health.rate-catalog.max-age-seconds:300}") long maxAgeSeconds) {
        return new RateCatalogHealthIndicator(catalog, clock, Duration.ofSeconds(maxAgeSeconds));
    }

    @Bean
    @ConditionalOnProperty(prefix = "demo.catalog", name = "load",
            havingValue = "true", matchIfMissing = true)
    ApplicationRunner loadDemoCatalog(
            RateCatalog catalog,
            Clock clock,
            @Value("${demo.catalog.rule-count:12}") int ruleCount,
            @Value("${demo.catalog.age-seconds:30}") long ageSeconds) {
        return args -> catalog.publish(ruleCount, Instant.now(clock).minusSeconds(ageSeconds));
    }
}
```

Để các lớp trong cùng gói giúp ví dụ dễ chạy; indicator được đăng ký bằng `@Bean`, nên không thêm `@Component` lên chính lớp `RateCatalogHealthIndicator`. Nếu dùng cả hai cách có thể tạo hai bean không mong muốn. Trong dự án lớn, có thể đặt cấu hình bean riêng nhưng vẫn cần giữ một cách đăng ký rõ ràng.

`loadDemoCatalog` chỉ là bộ nạp dữ liệu mô phỏng để thử các trạng thái, không phải tác vụ tải dữ liệu thật. Nó chạy khi ứng dụng khởi động; indicator không gọi ngược lại bộ nạp. Những thuộc tính bắt đầu bằng `demo.catalog` chỉ phục vụ thí nghiệm này.

### 6.2. Tên bean trở thành tên thành phần

Tên bean từ phương thức là `rateCatalogHealthIndicator`. Actuator bỏ hậu tố `HealthIndicator`, nên tên thành phần là `rateCatalog`, với đường dẫn mặc định:

```text
/actuator/health/rateCatalog
```

Tên bean là thông tin quyết định trong trường hợp này, không phải tên biến constructor hoặc tên catalog trong miền nghiệp vụ. Đổi tên bean có thể làm thay đổi đường dẫn và các cấu hình tham chiếu đến nó; cần coi đó là thay đổi hợp đồng vận hành. Xem [quy tắc đăng ký và tên custom indicator](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.health.writing-custom-health-indicators).

### 6.3. Cấu hình quan sát cho máy học tập

Tệp `src/main/resources/application.properties`:

```properties
server.address=127.0.0.1
server.port=8080
management.endpoints.web.exposure.include=health
management.endpoint.health.show-components=always
management.endpoint.health.show-details=always
app.health.rate-catalog.max-age-seconds=300
```

Cấu hình hiển thị đầy đủ này dùng để quan sát trên loopback. Khi đưa vào môi trường vận hành, cần chọn quyền truy cập và chính sách hiển thị phù hợp với nội dung chi tiết thực tế. Bật `show-details` không thay thế xác thực hoặc phân quyền của ứng dụng.

Chạy ứng dụng:

```shell
mvn spring-boot:run "-Dspring-boot.run.main-class=learning.customhealth.CustomHealthApplication"
```

Chỉ định main class giúp phân biệt với chương trình kiểm tra ở mục 5. Sau khi bộ nạp mô phỏng hoàn tất, mở terminal khác:

```shell
curl -i http://127.0.0.1:8080/actuator/health/rateCatalog
curl -i http://127.0.0.1:8080/actuator/health
```

Trên Windows PowerShell, dùng `curl.exe` nếu `curl` là bí danh của PowerShell. Trên Windows cũng có thể gọi `mvn.cmd` thay cho `mvn`.

Với mặc định, nếu gọi trong vòng năm phút kể từ thời điểm cập nhật mô phỏng, nhánh `rateCatalog` có trạng thái `UP`, lý do `READY` và `ruleCount=12`. Phần thân JSON có cấu trúc như sau; tuổi dữ liệu là số thay đổi theo lúc gọi:

```json
{
  "status": "UP",
  "details": {
    "maxAgeSeconds": 300,
    "ruleCount": 12,
    "ageSeconds": 31,
    "reason": "READY"
  }
}
```

`31` chỉ là số minh họa, không phải stdout cố định. Vì ví dụ chỉ nạp một lần, sau khi dữ liệu quá hạn, trạng thái chuyển thành `DOWN` mà không cần khởi động lại. Điều đó cho thấy health phụ thuộc bằng chứng hiện tại; một lần `UP` không có hiệu lực vĩnh viễn.

Ở endpoint tổng, kết quả của indicator nằm dưới `components.rateCatalog`. Các thành phần khác cũng tham gia tổng hợp, nên `rateCatalog=UP` chưa bảo đảm trạng thái tổng là `UP`.

## 7. Tạo tình huống lỗi có kiểm soát

Dừng phiên ứng dụng đang chạy trước mỗi lần thử lại. Các lệnh sau chạy từ thư mục dự án và giữ nguyên ngưỡng mặc định 300 giây.

### Chưa nạp dữ liệu

```shell
mvn spring-boot:run "-Dspring-boot.run.main-class=learning.customhealth.CustomHealthApplication" "-Dspring-boot.run.arguments=--demo.catalog.load=false"
```

Ứng dụng vẫn có thể khởi động nhưng `rateCatalog` trả `OUT_OF_SERVICE` với `reason=NOT_LOADED` vì không có bản chụp nào được công bố.

### Dữ liệu quá cũ ngay khi nạp

```shell
mvn spring-boot:run "-Dspring-boot.run.main-class=learning.customhealth.CustomHealthApplication" "-Dspring-boot.run.arguments=--demo.catalog.age-seconds=301"
```

Nhánh trả `DOWN` với `reason=STALE_CATALOG`. Không cần chờ thật năm phút để thử trường hợp này.

### Bảng quy tắc rỗng

```shell
mvn spring-boot:run "-Dspring-boot.run.main-class=learning.customhealth.CustomHealthApplication" "-Dspring-boot.run.arguments=--demo.catalog.rule-count=0"
```

Nhánh trả `DOWN` với `reason=EMPTY_CATALOG` dù đối tượng catalog vẫn tồn tại. Có bean không đồng nghĩa dữ liệu trong bean đã đạt yêu cầu.

Với ánh xạ HTTP mặc định của health endpoint, `DOWN` và `OUT_OF_SERVICE` tương ứng HTTP `503`; `UP` tương ứng `200`. `503` này là kết quả của bộ máy công bố health, không phải vì `doHealthCheck` ném một HTTP exception. Khi ứng dụng đã tùy chỉnh ánh xạ hoặc cách tổng hợp trạng thái, phải đọc chính sách đang có hiệu lực.

Ví dụ không tạo status mới như `STALE`. Mã lý do `STALE_CATALOG` chỉ bổ sung chẩn đoán bên cạnh status `DOWN`. Nếu tự định nghĩa status mới, còn phải xác định thứ tự tổng hợp và ánh xạ HTTP; không nên giả định mọi chuỗi mới đều tự được coi là lỗi.

## 8. Bật/tắt indicator do ứng dụng sở hữu

Không nên giả định cứ đặt `management.health.rateCatalog.enabled=false` thì mọi bean tùy chỉnh tên tương ứng sẽ bị xóa. Các thuộc tính bật/tắt chỉ có tác dụng khi cấu hình tạo bean thực sự dùng chúng làm điều kiện.

Trong ví dụ, ta chủ động khai báo `@ConditionalOnProperty` với khóa riêng:

```properties
app.health.rate-catalog.enabled=false
```

Khi khởi động với giá trị này, bean `rateCatalogHealthIndicator` không được tạo. Catalog và bộ nạp mô phỏng vẫn là các thành phần riêng; tắt quan sát không sửa dữ liệu và không làm thành phần nghiệp vụ hoạt động trở lại.

`havingValue="true"` yêu cầu giá trị là `true`; `matchIfMissing=true` cho phép tạo indicator khi chưa khai báo khóa. Đây là ý nghĩa trực tiếp của annotation, không phải cơ chế tự nhận diện tên thuộc tính. Có thể đối chiếu [hợp đồng ConditionalOnProperty](https://raw.githubusercontent.com/spring-projects/spring-boot/v3.3.0/spring-boot-project/spring-boot-autoconfigure/src/main/java/org/springframework/boot/autoconfigure/condition/ConditionalOnProperty.java).

Tương tự, `management.health.defaults.enabled=false` không tự xóa bean này: điều kiện mà ta viết chỉ đọc `app.health.rate-catalog.enabled`. Nếu muốn công tắc mặc định chung tác động tới indicator tùy chỉnh, phải thiết kế và kiểm thử rõ điều kiện đó.

Phân biệt ba hành động:

- **Tắt bean:** không còn phép kiểm tra của bean đó trong cây health.
- **Ẩn details:** phép kiểm tra vẫn có thể chạy và ảnh hưởng trạng thái, nhưng người gọi không nhận chi tiết.
- **Thay đổi tiêu chí:** vẫn có phép kiểm tra, nhưng điều kiện `UP`/`DOWN` đổi; đây là thay đổi chính sách có ảnh hưởng vận hành.

## 9. Thiết kế phép kiểm tra để việc quan sát không gây thêm sự cố

### Chỉ đọc và không tự sửa

Không tải lại toàn bộ bảng quy tắc, ghi bản ghi nghiệp vụ, gửi thư hoặc tạo giao dịch thật trong `health()`. Một hệ thống giám sát có thể gọi rất thường xuyên và từ nhiều nơi. Nếu mỗi lần gọi đều thay đổi hệ thống, tần suất giám sát sẽ trở thành một phần hành vi nghiệp vụ.

Ví dụ đọc bản chụp đã được công bố nên không làm mới dữ liệu. Vì vậy, nó trả lời **dữ liệu đang có dùng được theo tiêu chí tuổi và số lượng không**, chứ không trả lời **nguồn tải hiện có kết nối được không**. Nếu cần cả hai bằng chứng, hãy xác định ranh giới kiểm tra riêng, tránh lấy một tín hiệu để đại diện cho câu hỏi khác.

### Có giới hạn thời gian và chi phí

Nếu indicator thật cần I/O, phải đặt timeout trong client hoặc thao tác I/O tương ứng và giới hạn tổng chi phí. `AbstractHealthIndicator` chỉ xử lý exception sau khi exception xảy ra; nó không tự ngắt một thao tác bị treo.

Không tạo một thread mới hoặc một pool mới cho mỗi lần health. Bao lời gọi bằng `Future.get(timeout)` cũng không chứng minh I/O bên dưới đã bị hủy khi hết thời gian chờ. Cần hiểu cơ chế hủy và timeout của chính client đang dùng.

`management.endpoint.health.logging.slow-indicator-threshold` điều chỉnh mốc cảnh báo indicator chậm, không phải hạn chót để tự hủy nó. Với WebFlux và client thực sự reactive, hợp đồng phù hợp là `ReactiveHealthIndicator`; không gọi `.block()` trong luồng event loop chỉ để lắp vào một indicator đồng bộ.

### Không làm lộ thông tin nhạy cảm

Chỉ thêm chi tiết cần cho hành động vận hành: mã lý do ổn định, tuổi dữ liệu, số mục hoặc tên thành phần không nhạy cảm. Không đưa token, mật khẩu, chuỗi kết nối đầy đủ hoặc dữ liệu khách hàng vào `withDetail`.

Lớp cha chuyển exception thoát ra thành `DOWN` kèm thông tin lỗi; thông điệp exception có thể chứa nội dung nhạy cảm. Với lỗi có thể dự kiến, nên ánh xạ sang mã lý do an toàn và ghi log nội bộ theo chính sách của ứng dụng. `show-details=never` giảm dữ liệu trả qua endpoint, nhưng không biến việc đưa bí mật vào đối tượng `Health` thành một thiết kế tốt.

### Không gắn kết luận health với hành động điều phối một cách máy móc

Đăng ký `rateCatalog` vào cây health tổng không tự thêm nó vào mọi nhóm liveness/readiness. Việc hệ điều phối có dùng tín hiệu đó để nhận lưu lượng hay khởi động lại tiến trình là quyết định cấu hình riêng.

Một nguồn dữ liệu bên ngoài đang lỗi không mặc nhiên có nghĩa JVM cần bị khởi động lại. Trước khi dùng indicator trong probe, cần xác định thành phần có thể tự phục hồi không, có thể tiếp tục phục vụ bằng dữ liệu cũ không và hành động điều phối nào thực sự giúp khôi phục.

## 10. Kiểm chứng và lỗi thường gặp

Ngoài bảy tình huống của chương trình kiểm tra, khi tích hợp vào ứng dụng thật nên xác nhận:

| Cần kiểm chứng | Bằng chứng hữu ích |
| --- | --- |
| Đúng quy tắc trạng thái | Kiểm thử không có dữ liệu, dữ liệu rỗng, mới, đúng ngưỡng, vừa quá ngưỡng và thời gian tương lai. |
| Không có tác dụng phụ | Bản chụp và dữ liệu nghiệp vụ không đổi sau khi gọi health nhiều lần. |
| Đúng đăng ký | Bean có mặt, tên contributor là `rateCatalog`, và chỉ có một bean theo thiết kế. |
| Đúng công tắc | Đổi `app.health.rate-catalog.enabled`, khởi động lại context và kiểm tra bean có/không có. |
| Đúng phản hồi được công bố | Kiểm tra đường dẫn, HTTP status, JSON và chính sách hiển thị bằng HTTP ở môi trường chạy được. |
| Đúng giới hạn vận hành | Đo thời gian, số lời gọi I/O và hành vi khi client timeout nếu indicator có I/O. |

**Có lớp nhưng không xuất hiện trong Actuator:** kiểm tra lớp đã trở thành bean chưa, cấu hình có được nạp không và điều kiện thuộc tính có khớp không. Một unit test gọi `new RateCatalogHealthIndicator(...)` thành công chưa chứng minh Spring đã đăng ký nó.

**Có bean nhưng đọc nhầm catalog:** kiểm tra indicator có nhận chính bean mà luồng nghiệp vụ đang cập nhật không. Tạo `new RateCatalog()` bên trong `doHealthCheck` sẽ luôn quan sát một đối tượng mới chưa nạp, không phải trạng thái ứng dụng thật.

**Luôn trả `UP`:** kiểm tra có đặt lại thời gian cập nhật mỗi lần health, có nuốt lỗi bằng `catch` rồi báo khỏe hoặc có bỏ sót tiêu chí dữ liệu rỗng không.

**Cùng dữ liệu nhưng kiểm thử lúc đạt lúc trượt:** kiểm tra có phụ thuộc đồng hồ thật hoặc so sánh sai ở điểm biên không. Dùng `Clock.fixed` để biến điều kiện thời gian thành dữ liệu kiểm thử rõ ràng.

**Trả `DOWN` khi ruleCount âm hoặc maxAge bằng không:** trong thiết kế này, đó không phải kết quả mong đợi. Constructor từ chối dữ liệu hoặc cấu hình không hợp lệ, có thể làm bước khởi tạo thất bại. Cần phân biệt lỗi thiết lập với trạng thái sức khỏe được quan sát sau khi ứng dụng đã hoạt động.

Một indicator hoàn chỉnh phải nối được **điều kiện vận hành → bằng chứng đọc được → trạng thái → chi tiết an toàn → bean đã đăng ký → kết quả có thể kiểm chứng**. Với `rateCatalog`, chuỗi này được thể hiện bằng bản chụp nhất quán, tiêu chí tuổi dữ liệu rõ ràng, phép kiểm tra chỉ đọc và các tình huống có thời gian cố định.
