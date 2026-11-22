# Tách cấu hình khỏi mã và kiểm tra cấu hình lúc khởi động

Một Java function có thể được triển khai ở development, staging và production từ cùng một artifact, nhưng mỗi môi trường dùng database, queue, endpoint, giới hạn tải và secret khác nhau. Nếu các giá trị này nằm rải rác trong mã nguồn hoặc được sửa thủ công sau khi build, mỗi lần thay đổi môi trường đều có nguy cơ tạo ra một bản ứng dụng khác nhau và khó tái tạo.

**Tách cấu hình khỏi mã** nghĩa là giữ logic và artifact độc lập với các giá trị thay đổi theo môi trường. Khi function khởi động, ứng dụng đọc cấu hình từ nguồn đã được cấp, chuyển thành kiểu dữ liệu rõ ràng, kiểm tra tính hợp lệ và chỉ bắt đầu nhận công việc khi các giá trị bắt buộc đáp ứng hợp đồng.

Với serverless, bước này đặc biệt quan trọng vì nhiều instance có thể khởi động đồng thời. Một cấu hình sai có thể khiến mọi instance mới cùng thất bại, tạo retry storm hoặc làm request được gửi đến nhầm tài nguyên. Bài học này trình bày cách tổ chức cấu hình, phân biệt cấu hình thường với secret, kiểm tra sớm bằng Java và Spring Boot, và quản lý thay đổi an toàn qua vòng đời function.

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Giải thích vì sao cấu hình theo môi trường cần được tách khỏi mã và artifact.
- Chọn nguồn phù hợp cho environment variables, file cấu hình, parameter store và secret manager.
- Thiết kế tên, kiểu dữ liệu, default và precedence cho cấu hình.
- Bind cấu hình thành object bất biến, có kiểu rõ ràng trong Java.
- Kiểm tra giá trị bắt buộc, phạm vi, định dạng và quan hệ giữa các thuộc tính lúc khởi động.
- Dùng Spring Boot `@ConfigurationProperties` và Bean Validation để fail fast.
- Phân biệt cấu hình tĩnh theo instance với cấu hình động cần cập nhật khi function đang chạy.
- Xử lý cấu hình trong môi trường serverless có cold start, warm reuse, revision và retry.
- Kiểm thử cấu hình hợp lệ, thiếu, sai định dạng và không tương thích trước khi triển khai.

## 1. Vì sao phải tách cấu hình khỏi mã?

Cùng một Java application có thể cần chạy với nhiều giá trị khác nhau:

| Giá trị | Development | Staging | Production |
|---|---|---|---|
| Database endpoint | Local/test database | Database staging | Database production |
| Queue/topic | orders-dev | orders-staging | orders-prod |
| External API | Sandbox URL | Staging URL | Production URL |
| Log level | DEBUG | INFO | INFO/WARN |
| Request timeout | Giá trị phục vụ test | Gần production | Theo SLA |
| Feature flag | Bật cho thử nghiệm | Bật có kiểm soát | Theo quyết định release |
| Secret | Credential test | Credential staging | Credential production |

Nếu viết cứng các giá trị này vào code, mỗi môi trường có thể cần build artifact riêng. Điều đó làm giảm khả năng tái tạo, gây nhầm lẫn khi rollback và tăng nguy cơ đưa endpoint hoặc credential production vào bản test.

Một quy tắc hữu ích là: **build một artifact đã kiểm thử, sau đó đưa artifact đó qua các môi trường bằng cấu hình và quyền khác nhau**. Cấu hình không nhạy cảm có thể được truyền qua environment variables hoặc file được mount. Credential và API key nên được lấy từ secret manager hoặc cơ chế secret injection của nền tảng.

### Cấu hình không phải dữ liệu nghiệp vụ

Cấu hình mô tả cách ứng dụng hoạt động trong một môi trường, ví dụ tên queue, timeout hoặc endpoint. Dữ liệu nghiệp vụ như đơn hàng, số dư, tồn kho và trạng thái workflow phải được lưu trong hệ thống dữ liệu phù hợp.

Không dùng environment variable để lưu trạng thái thay đổi theo từng request. Environment variable thuộc cấu hình của process/instance và thường không phải nơi có thể cập nhật nguyên tử theo nghiệp vụ.

## 2. Phân loại cấu hình trước khi chọn nguồn

Không phải mọi giá trị đều nên đặt ở cùng một nơi. Hãy phân loại theo độ nhạy, tần suất thay đổi, phạm vi áp dụng và thời điểm cần đọc.

| Loại | Ví dụ | Nguồn phù hợp | Đặc điểm |
|---|---|---|---|
| Runtime/platform | Port, region, memory limit | Nền tảng serverless | Do môi trường chạy cung cấp |
| Deployment config | Queue name, database host, feature mode | Environment variables, deployment manifest, config store | Thường cố định cho một revision/version |
| Secret | Password, API key, signing key | Secret Manager, Secrets Manager, Parameter Store SecureString | Cần IAM, audit và rotation |
| Dynamic config | Feature flag, tỷ lệ rollout, ngưỡng có thể đổi nhanh | Config service hoặc parameter store | Có thể cần refresh trong lúc instance đang chạy |
| Business data | Order status, customer preference, inventory | Database hoặc event store | Có vòng đời và transaction nghiệp vụ |

Hãy xác định nguồn chuẩn cho từng giá trị. Nếu cùng một timeout được khai báo trong YAML, environment variable và remote config mà không có quy tắc precedence, đội vận hành sẽ khó biết giá trị thực tế mà function đang dùng.

### Cấu hình thường và secret

Cấu hình thường có thể được hiển thị trong deployment metadata, log có kiểm soát hoặc màn hình vận hành. Secret phải được bảo vệ riêng.

Không xem một giá trị là an toàn chỉ vì nó nằm trong environment variable. Environment variable có thể xuất hiện trong cấu hình deployment, diagnostic dump hoặc log do ứng dụng tự ghi. Dùng secret manager hoặc secret integration của nền tảng cho credential, rồi cấp quyền đọc đúng secret cho runtime identity.

Không đưa secret vào:

- Git repository, Dockerfile hoặc image layer.
- Build argument hoặc command line có thể bị lưu trong log.
- Event payload, URL query string hoặc exception message.
- Log, trace attribute, metric label hay dashboard.
- Test fixture dùng chung hoặc tài liệu onboarding.

## 3. Đặt tên và thiết kế hợp đồng cấu hình

Một cấu hình tốt có tên thể hiện ý nghĩa, kiểu dữ liệu, đơn vị và quy tắc bắt buộc.

Ví dụ:

~~~text
APP_DATABASE_URL=jdbc:postgresql://db.internal:5432/orders
APP_DATABASE_POOL_MAX_SIZE=12
APP_ORDER_QUEUE=orders-prod
APP_REQUEST_TIMEOUT=PT3S
APP_FEATURE_NEW_CHECKOUT=false
APP_ALLOWED_ORIGINS=https://shop.example.com,https://admin.example.com
~~~

Tránh tên mơ hồ như `TIMEOUT`, `URL` hoặc `MODE` khi ứng dụng có nhiều dependency. Tên `APP_PAYMENT_CONNECT_TIMEOUT_MS` rõ hơn vì cho biết phạm vi, mục đích và đơn vị.

### Quy ước nên có

- Dùng prefix riêng của ứng dụng, ví dụ `APP_`, để giảm trùng tên.
- Ghi rõ đơn vị trong tên hoặc định dạng, chẳng hạn `_MS`, `_SECONDS` hoặc duration ISO-8601 `PT3S` (nếu dùng parser Java chuẩn).
- Dùng tên phân cấp theo module: `APP_DATABASE_URL`, `APP_QUEUE_ORDERS`.
- Xác định trường bắt buộc và trường tùy chọn.
- Chỉ đặt default khi default đó an toàn trong mọi môi trường dự kiến.
- Quy định định dạng cho URL, region, enum, list và duration.
- Ghi schema/version cho cấu hình có thể thay đổi cấu trúc.

Default sai có thể nguy hiểm hơn lỗi khởi động. Ví dụ, nếu thiếu `PAYMENT_API_URL` mà ứng dụng âm thầm dùng sandbox URL trong production, request có thể đi nhầm hệ thống. Với giá trị bắt buộc, fail fast thường an toàn hơn tự chọn một default đoán mò.

### Ví dụ catalog cấu hình

| Key | Kiểu | Bắt buộc | Quy tắc |
|---|---|---:|---|
| `APP_DATABASE_URL` | JDBC URL | Có | Scheme được hỗ trợ, host và database hợp lệ |
| `APP_ORDER_QUEUE` | String | Có | Không rỗng, đúng queue của môi trường |
| `APP_REQUEST_TIMEOUT` | Duration | Có | Lớn hơn 0 và nhỏ hơn giới hạn nền tảng |
| `APP_DATABASE_POOL_MAX_SIZE` | Integer | Có | Trong phạm vi đã load test |
| `APP_FEATURE_NEW_CHECKOUT` | Boolean | Không | Default false nếu an toàn |
| `APP_PAYMENT_SECRET_ID` | Secret reference | Có | ARN hoặc tên secret được phép đọc |
| `APP_ALLOWED_ORIGINS` | List<URI> | Tùy API | Chỉ origin hợp lệ, không nhận wildcard ngoài ý muốn |

Catalog này có thể được lưu trong tài liệu vận hành hoặc schema cấu hình của ứng dụng. Không đưa secret value vào catalog; chỉ mô tả tên tham chiếu và quyền cần thiết.

## 4. Nguồn cấu hình và thứ tự ưu tiên

Nguồn cấu hình thường gặp:

1. Giá trị mặc định trong ứng dụng cho trường tùy chọn.
2. File cấu hình đóng gói trong artifact, dùng cho default không nhạy cảm.
3. File hoặc biến môi trường được cung cấp khi deploy.
4. Secret/parameter được đọc từ dịch vụ quản lý cấu hình.
5. Override rõ ràng cho môi trường kiểm thử hoặc local development.

Thứ tự chính xác phụ thuộc framework và cách triển khai. Không nên tự giả định rằng secret manager luôn ghi đè environment variable hoặc command-line argument. Hãy xác định một precedence duy nhất, kiểm tra bằng integration test và ghi lại nguồn của từng giá trị mà không ghi giá trị nhạy cảm.

### Spring Boot configuration

Spring Boot hỗ trợ nhiều property source và quy tắc relaxed binding. Các tên dưới đây là canonical property names tương ứng với các component của `AppProperties`:

~~~text
app.database-url
app.order-queue
app.request-timeout
app.database-pool-max-size
app.new-checkout-enabled
~~~

có thể được bind từ environment variables:

~~~text
APP_DATABASEURL
APP_ORDERQUEUE
APP_REQUESTTIMEOUT
APP_DATABASEPOOLMAXSIZE
APP_NEWCHECKOUTENABLED
~~~

Với tên property có dấu gạch nối, quy tắc environment variable của Spring Boot chuyển dấu chấm thành dấu gạch dưới, bỏ dấu gạch nối và viết hoa. Hãy kiểm tra đúng tên biến theo property thực tế; không tùy tiện suy ra tên từ cách viết trong tài liệu.

Với ứng dụng không dùng Spring, nên xây một lớp loader duy nhất đọc environment variables hoặc file cấu hình, parse sang kiểu dữ liệu và trả về object đã validate. Tránh gọi `System.getenv()` rải rác trong mọi service vì điều đó làm khó kiểm thử và không thể nhìn thấy hợp đồng cấu hình tại một chỗ.

## 5. Kiểm tra cấu hình lúc khởi động

Cấu hình nên được đọc và kiểm tra trước khi ứng dụng nhận request hoặc xử lý message. Quy trình tổng quát:

~~~mermaid
flowchart TD
    A["Process / function starts"] --> B["Read config sources"]
    B --> C["Parse into typed values"]
    C --> D["Validate required fields"]
    D --> E["Validate ranges and relationships"]
    E --> F{"Configuration valid?"}
    F -->|Yes| G["Initialize clients and handlers"]
    G --> H["Become ready"]
    F -->|No| I["Fail startup with safe diagnostic"]
~~~

Kiểm tra nên bao gồm:

- **Presence:** giá trị bắt buộc có tồn tại và không rỗng.
- **Format:** URL, URI, ARN, enum, duration hoặc JSON đúng định dạng.
- **Range:** số lượng, timeout, pool size và tỷ lệ nằm trong giới hạn.
- **Relationship:** timeout của dependency nhỏ hơn timeout tổng; pool size không vượt giới hạn đã chọn; queue name phù hợp với môi trường.
- **Compatibility:** schema version được hỗ trợ; tên feature flag và mode hợp lệ.
- **Security assumptions:** không bật debug hoặc public access ngoài ý muốn trong production.

Không chỉ kiểm tra chuỗi khác rỗng. `APP_REQUEST_TIMEOUT=abc` có thể hiện diện nhưng không thể parse thành duration; `APP_DATABASE_POOL_MAX_SIZE=-5` có thể parse được nhưng không hợp lệ.

### Fail fast

Nếu cấu hình bắt buộc sai, dừng startup và báo lỗi có thể hành động. Không để function nhận request rồi mới phát hiện thiếu database URL hoặc queue name.

Thông báo lỗi nên nói rõ key nào sai và vì sao, nhưng không in secret value. Ví dụ:

~~~text
Invalid configuration: APP_REQUEST_TIMEOUT must be between 100ms and 30s
~~~

Không ghi:

~~~text
Database password rejected: <secret-value>
~~~

Khi chạy serverless, nền tảng có thể thử tạo instance khác hoặc trigger retry sau lỗi khởi động. Nếu cấu hình sai là lỗi cố định, retry liên tục chỉ làm tăng log và chi phí. Cần cảnh báo rõ lỗi startup, giới hạn retry ở nơi gọi và sửa cấu hình trước khi tiếp tục traffic.

## 6. Java thuần: parse và validate thành object bất biến

Ví dụ sau dùng Java 17, đọc cấu hình từ environment variables rồi tạo một record bất biến. Mọi validation tập trung ở một nơi.

~~~java
import java.net.URI;
import java.time.Duration;
import java.util.Map;

public record AppConfig(
        URI databaseUrl,
        String orderQueue,
        Duration requestTimeout,
        int databasePoolMaxSize,
        boolean newCheckoutEnabled) {

    public static AppConfig from(Map<String, String> env) {
        URI databaseUrl = requiredUri(env, "APP_DATABASE_URL");
        String orderQueue = required(env, "APP_ORDER_QUEUE");
        Duration timeout = requiredDuration(
                env, "APP_REQUEST_TIMEOUT");
        int poolSize = requiredInt(
                env, "APP_DATABASE_POOL_MAX_SIZE");
        boolean newCheckout = optionalBoolean(
                env, "APP_FEATURE_NEW_CHECKOUT", false);

        if (!"jdbc".equalsIgnoreCase(databaseUrl.getScheme())) {
            throw new IllegalArgumentException(
                    "APP_DATABASE_URL must use a JDBC URL");
        }
        if (timeout.compareTo(Duration.ofMillis(100)) < 0
                || timeout.compareTo(Duration.ofSeconds(30)) > 0) {
            throw new IllegalArgumentException(
                    "APP_REQUEST_TIMEOUT must be between 100ms and 30s");
        }
        if (poolSize < 1 || poolSize > 50) {
            throw new IllegalArgumentException(
                    "APP_DATABASE_POOL_MAX_SIZE must be between 1 and 50");
        }

        return new AppConfig(
                databaseUrl,
                orderQueue,
                timeout,
                poolSize,
                newCheckout);
    }

    private static String required(
            Map<String, String> env, String key) {
        String value = env.get(key);
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException(
                    "Missing required configuration: " + key);
        }
        return value.trim();
    }

    private static URI requiredUri(
            Map<String, String> env, String key) {
        String raw = required(env, key);
        try {
            return URI.create(raw);
        } catch (IllegalArgumentException error) {
            throw new IllegalArgumentException(
                    key + " must be a valid URI");
        }
    }

    private static Duration requiredDuration(
            Map<String, String> env, String key) {
        String raw = required(env, key);
        try {
            return Duration.parse(raw);
        } catch (RuntimeException ignored) {
            // Hợp đồng ví dụ dùng ISO-8601, chẳng hạn PT3S.
            throw new IllegalArgumentException(
                    key + " must use ISO-8601 duration, for example PT3S");
        }
    }

    private static int requiredInt(
            Map<String, String> env, String key) {
        try {
            return Integer.parseInt(required(env, key));
        } catch (NumberFormatException error) {
            throw new IllegalArgumentException(
                    key + " must be an integer");
        }
    }

    private static boolean optionalBoolean(
            Map<String, String> env,
            String key,
            boolean defaultValue) {
        String raw = env.get(key);
        if (raw == null || raw.isBlank()) {
            return defaultValue;
        }
        if ("true".equalsIgnoreCase(raw.trim())) {
            return true;
        }
        if ("false".equalsIgnoreCase(raw.trim())) {
            return false;
        }
        throw new IllegalArgumentException(
                key + " must be true or false");
    }
}
~~~

Trong ví dụ, timeout dùng định dạng ISO-8601 như `PT3S`. Nếu muốn dùng `3s`, hãy dùng parser duration có hỗ trợ cú pháp đó hoặc viết parser riêng; không trộn hai định dạng trong cùng một hợp đồng.

Có thể gọi `AppConfig.from(System.getenv())` một lần trong quá trình khởi động. Trong unit test, truyền một Map giả để kiểm tra nhiều trường hợp mà không phải thay đổi environment của process.

### Vì sao dùng record bất biến?

Record giúp biểu diễn một snapshot cấu hình đã được kiểm tra. Sau khi khởi động, service nhận cùng một object thay vì đọc biến môi trường ở nhiều nơi. Điều này giảm nguy cơ một request thấy nửa cấu hình cũ và nửa cấu hình mới.

Nếu cấu hình cần thay đổi động, hãy dùng một cơ chế snapshot/version riêng và thay toàn bộ object đã validate một cách nguyên tử. Không sửa từng field mutable trong lúc request đang đọc.

## 7. Spring Boot: @ConfigurationProperties và Bean Validation

Spring Boot có thể bind property vào một class hoặc record và kiểm tra bằng Jakarta Bean Validation. Ví dụ sau dùng Spring Boot 3 và Java 17 trở lên.

~~~java
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

import java.net.URI;
import java.time.Duration;

@Validated
@ConfigurationProperties(prefix = "app")
public record AppProperties(
        @NotNull URI databaseUrl,
        @NotBlank String orderQueue,
        @NotNull Duration requestTimeout,
        @Min(1) @Max(50) int databasePoolMaxSize,
        boolean newCheckoutEnabled) {

    public AppProperties {
        if (databaseUrl != null
                && !"jdbc".equalsIgnoreCase(databaseUrl.getScheme())) {
            throw new IllegalArgumentException(
                    "app.database-url must use a JDBC URL");
        }
        if (requestTimeout != null
                && (requestTimeout.compareTo(Duration.ofMillis(100)) < 0
                || requestTimeout.compareTo(Duration.ofSeconds(30)) > 0)) {
            throw new IllegalArgumentException(
                    "app.request-timeout must be between 100ms and 30s");
        }
    }
}
~~~

Đăng ký configuration properties bằng `@ConfigurationPropertiesScan` trên class ứng dụng hoặc `@EnableConfigurationProperties(AppProperties.class)` trong cấu hình.

~~~java
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan
public class OrdersApplication {
    public static void main(String[] args) {
        SpringApplication.run(OrdersApplication.class, args);
    }
}
~~~

Khai báo dependency validation tương ứng, ví dụ `spring-boot-starter-validation`, để các annotation như `@NotBlank`, `@Min` và `@Max` được thực thi. Constructor validation trong record ở trên bổ sung quy tắc quan hệ cho Duration; có thể chuyển thành custom constraint khi ứng dụng có nhiều quy tắc phức tạp.

Cấu hình mặc định không nhạy cảm trong `application.yaml` (các property bên dưới khớp trực tiếp với các component của record):

~~~yaml
app:
  request-timeout: 3s
  database-pool-max-size: 12
  new-checkout-enabled: false
~~~

Các giá trị theo môi trường được override bằng environment variables hoặc config source được triển khai. Ví dụ:

~~~text
APP_DATABASEURL=jdbc:postgresql://db.internal:5432/orders
APP_ORDERQUEUE=orders-prod
APP_REQUESTTIMEOUT=3s
APP_DATABASEPOOLMAXSIZE=12
APP_NEWCHECKOUTENABLED=false
~~~

Spring Boot chuyển đổi Duration từ chuỗi như `3s`. Hãy kiểm tra tên biến và kết quả binding bằng một test khởi động hoặc log metadata an toàn. Không log toàn bộ object nếu nó chứa secret hoặc thông tin kết nối nhạy cảm.

### Validation nhiều thuộc tính

Bean Validation kiểm tra từng thuộc tính tốt, nhưng một số quy tắc phụ thuộc lẫn nhau cần kiểm tra ở constructor, custom validator hoặc bước startup riêng. Ví dụ:

- Connect timeout phải nhỏ hơn request timeout.
- Database pool size phải phù hợp concurrency và giới hạn connection tổng.
- Batch size phải tương thích với timeout và memory.
- Retry count không được âm và tổng thời gian retry phải nằm trong SLA.
- Nếu bật feature mới, phải có endpoint hoặc secret reference bắt buộc.

Không đặt quy tắc này trong controller vì controller chỉ chạy sau khi ứng dụng đã nhận traffic.

## 8. Cấu hình serverless: những giá trị cần kiểm tra đặc biệt

Ngoài cấu hình ứng dụng thông thường, Java function thường cần các giá trị liên quan trigger, concurrency và thời hạn thực thi.

| Nhóm | Ví dụ | Kiểm tra nên có |
|---|---|---|
| HTTP | Port, allowed origins, request timeout | Port hợp lệ; origin đúng định dạng; timeout dưới giới hạn nền tảng |
| Queue | Queue name, batch size, visibility/ack deadline | Queue tồn tại; batch size dương; timeout tương thích cơ chế giao nhận |
| Event | Schema version, event type allowlist | Version được hỗ trợ; loại event không rỗng |
| Database | JDBC URL, pool size, connect timeout | URL hợp lệ; pool không vượt tổng connection budget |
| Retry | Max attempts, backoff, DLQ | Giá trị dương; không retry lỗi vĩnh viễn vô hạn |
| Idempotency | Key namespace, retention TTL | TTL đủ dài cho khoảng retry/replay dự kiến |
| Security | Secret reference, allowed issuer/audience | Tham chiếu đúng môi trường; không tắt auth ngoài ý muốn |
| Observability | Log level, trace sampling | Giá trị trong tập cho phép; không bật debug nhạy cảm ở production |

Một số giá trị thuộc cấu hình nền tảng chứ không phải environment variable của ứng dụng. Ví dụ batch size hoặc max instances có thể được đặt trong event source mapping hoặc service deployment. Hãy tránh tạo hai nguồn sự thật cho cùng một giới hạn.

### Ràng buộc timeout giữa các tầng

Giả sử HTTP request có timeout tổng 10 giây. Database connect timeout là 2 giây, query timeout là 5 giây và phần xử lý còn lại cần thời gian trả response. Tổng thời gian của các dependency không nên vượt quá timeout request.

Với queue, visibility timeout hoặc acknowledgment deadline cần phù hợp thời gian xử lý và retry semantics của nguồn. Nếu message được giao lại trước khi invocation cũ kết thúc, hai consumer có thể cùng xử lý một message. Cấu hình phải được kiểm tra cùng idempotency, không chỉ từng giá trị riêng lẻ.

## 9. Secret và cấu hình nhạy cảm

Environment variable thuận tiện cho cấu hình theo deployment, nhưng không phải lựa chọn mặc định cho mọi secret. Hãy dùng secret manager hoặc secret integration của nền tảng để giữ credential bên ngoài source code và image.

Một cấu hình có thể chứa tham chiếu:

~~~text
APP_DATABASE_SECRET_ID=projects/example/secrets/orders-db/versions/latest
APP_PAYMENT_SECRET_ARN=arn:aws:secretsmanager:region:account:secret:payment-key
~~~

Các giá trị trên chỉ minh họa hai kiểu tham chiếu của nền tảng khác nhau. Không trộn cú pháp của Google Secret Manager và AWS Secrets Manager trong cùng một deployment. Mỗi môi trường cần dùng đúng provider, region/project và IAM identity của nó.

### Khi nào đọc secret?

Có hai cách phổ biến:

- **Startup snapshot:** đọc secret lúc khởi động, parse và tạo client. Request sau dùng client đã cấu hình. Cách này giảm API call nhưng secret có thể cũ cho đến khi instance được thay hoặc refresh.
- **TTL cache:** đọc secret qua provider có cache thời hạn. Cách này hỗ trợ rotation mà không gọi secret store ở mọi request.

Không nên đọc secret từ remote store trên mọi request nếu không có yêu cầu đặc biệt; việc đó tăng latency, chi phí và phụ thuộc vào khả năng sẵn sàng của secret service.

### Rotation và instance đang chạy

Khi secret được xoay, instance warm có thể vẫn giữ credential cũ trong memory hoặc connection pool. Cần xác định:

- Secret reference dùng version cụ thể hay version hiện hành.
- Cơ chế cache refresh và TTL.
- Connection pool được recycle khi credential thay đổi như thế nào.
- Hành vi khi secret service tạm thời không khả dụng.
- Cách rollout instance mới và loại bỏ instance dùng cấu hình cũ.

Không assume cập nhật secret sẽ tự sửa environment variable hoặc object Java đã khởi tạo. Cách cập nhật phụ thuộc vào nền tảng và phương thức mount/inject secret.

## 10. Cấu hình tĩnh và cấu hình động

**Cấu hình tĩnh theo instance** được đọc khi process/function khởi động và thường giữ nguyên trong vòng đời instance. Ví dụ database endpoint, queue name, pool size và region. Nếu thay đổi, thường cần tạo revision/version mới hoặc khởi động instance mới.

**Cấu hình động** có thể thay đổi khi service đang chạy mà không cần deploy lại, ví dụ feature flag hoặc ngưỡng rollout. Dùng dynamic config khi có nhu cầu thực sự, và phải định nghĩa cách refresh, cache, version, rollback và hành vi khi config service lỗi.

| Tiêu chí | Startup/static config | Dynamic config |
|---|---|---|
| Thời điểm đọc | Khi khởi động | Theo refresh/poll/event hoặc request có kiểm soát |
| Tính nhất quán | Snapshot ổn định trong instance | Có thể khác nhau tạm thời giữa instance |
| Độ phức tạp | Thấp hơn | Cần version, refresh và xử lý lỗi |
| Phù hợp | Endpoint, pool size, queue, timeout | Feature flag, rollout percentage, policy thay đổi nhanh |
| Khi nguồn lỗi | Instance mới có thể fail startup nếu giá trị bắt buộc không đọc được | Cần quyết định giữ snapshot cũ hay chặn tính năng |

Với dynamic config, không thay đổi từng field rời rạc. Hãy đọc một bộ cấu hình, validate toàn bộ rồi publish snapshot bất biến mới bằng atomic reference. Request đang chạy có thể tiếp tục dùng snapshot cũ; request tiếp theo dùng snapshot mới. Điều này tránh trạng thái nửa cũ, nửa mới.

Nếu không thể refresh, giữ snapshot cũ trong thời gian cho phép và phát cảnh báo. Với cấu hình bảo mật hoặc policy cần thu hồi ngay, có thể phải fail closed thay vì tiếp tục dùng giá trị cũ. Quyết định phụ thuộc tác động nếu cấu hình stale.

## 11. Vòng đời cấu hình trong serverless

Serverless instance có thể được tạo mới, tái sử dụng và thu hồi. Điều đó ảnh hưởng thời điểm đọc và hiệu lực cấu hình.

### Cold start

Khi instance mới được tạo, ứng dụng đọc cấu hình, validate, khởi tạo SDK client, connection pool và framework context. Nếu startup phải gọi nhiều dịch vụ từ xa, cold start có thể tăng đáng kể.

Chỉ đọc những cấu hình cần thiết để sẵn sàng nhận request. Có thể trì hoãn khởi tạo dependency không bắt buộc cho mọi request, nhưng đừng trì hoãn kiểm tra một cấu hình quan trọng đến lúc request production đầu tiên mới phát hiện sai.

### Warm reuse

Một instance có thể giữ object cấu hình qua nhiều invocation. Hãy xem cấu hình đã load là snapshot bất biến. Không lưu tenant, user hoặc request-specific override vào object dùng chung.

Static field có thể giữ AppConfig đã validate trong cùng JVM, nhưng không được chia sẻ giữa các instance và có thể mất khi environment bị thu hồi. Không dùng static field làm nguồn cấu hình động chung toàn hệ thống.

### Revision và version

Khi deploy một revision/version mới với environment variables hoặc secret reference mới, instance mới sẽ chạy theo cấu hình của revision/version đó. Các instance hoặc execution cũ có thể tiếp tục tồn tại theo semantics của nền tảng trong quá trình rollout.

Vì vậy, cấu hình cần tương thích với các revision cùng hoạt động trong giai đoạn chuyển tiếp. Ví dụ, nếu đổi tên queue, hãy bảo đảm producer, consumer và quyền IAM được chuyển theo một trình tự không làm mất message. Không xóa tài nguyên cũ ngay khi deploy bản mới.

## 12. Kiểm thử cấu hình

Cấu hình là một phần của hợp đồng ứng dụng và cần được kiểm thử như code.

### Unit test

Với AppConfig thuần Java, truyền Map để kiểm tra:

- Đủ mọi trường bắt buộc.
- Thiếu từng trường bắt buộc.
- Chuỗi rỗng hoặc chỉ có khoảng trắng.
- URL/URI sai định dạng.
- Duration không parse được hoặc nằm ngoài phạm vi.
- Integer âm, bằng 0 hoặc vượt giới hạn.
- Boolean không phải true/false.
- Tổ hợp cấu hình mâu thuẫn.

Ví dụ JUnit:

~~~java
import static org.junit.jupiter.api.Assertions.*;
import java.util.Map;
import org.junit.jupiter.api.Test;

class AppConfigTest {

    @Test
    void rejectsMissingDatabaseUrl() {
        Map<String, String> env = Map.of(
                "APP_ORDER_QUEUE", "orders-test",
                "APP_REQUEST_TIMEOUT", "PT3S",
                "APP_DATABASE_POOL_MAX_SIZE", "8");

        IllegalArgumentException error = assertThrows(
                IllegalArgumentException.class,
                () -> AppConfig.from(env));

        assertTrue(error.getMessage().contains("APP_DATABASE_URL"));
    }

    @Test
    void rejectsPoolSizeOutsideRange() {
        Map<String, String> env = Map.of(
                "APP_DATABASE_URL",
                "jdbc:postgresql://localhost:5432/orders",
                "APP_ORDER_QUEUE", "orders-test",
                "APP_REQUEST_TIMEOUT", "PT3S",
                "APP_DATABASE_POOL_MAX_SIZE", "0");

        assertThrows(
                IllegalArgumentException.class,
                () -> AppConfig.from(env));
    }
}
~~~

### Startup/integration test

Khởi chạy application với cấu hình test và xác minh:

- Application context khởi tạo thành công khi cấu hình hợp lệ.
- Context fail khi thiếu hoặc sai property bắt buộc.
- Profile/môi trường được chọn đúng.
- Secret reference có thể đọc bằng identity của môi trường test.
- Không log secret value khi startup lỗi.
- Health/readiness chỉ báo sẵn sàng sau khi cấu hình và dependency thiết yếu được khởi tạo.

Không dùng production secret trong test. Dùng fake provider, local emulator hoặc secret riêng của môi trường test.

### Deployment validation

Pipeline có thể kiểm tra manifest hoặc deployment parameters trước khi tạo revision:

1. Kiểm tra key bắt buộc và kiểu dữ liệu.
2. Kiểm tra URL, region, queue/topic và secret reference.
3. Kiểm tra IAM role/service account có quyền cần thiết.
4. Kiểm tra giới hạn concurrency, pool size, timeout và batch size.
5. Deploy staging, chạy smoke test.
6. Chỉ promote artifact và cấu hình đã được phê duyệt.

Validation ở pipeline không thay thế validation trong ứng dụng. Cấu hình có thể thay đổi sau build hoặc bị sửa thủ công; ứng dụng vẫn cần kiểm tra trước khi nhận traffic.

## 13. Xử lý khi cấu hình không hợp lệ hoặc nguồn cấu hình bị lỗi

Cần phân biệt lỗi cấu hình cố định với lỗi tạm thời khi đọc remote config.

| Tình huống | Phản ứng nên cân nhắc |
|---|---|
| Thiếu database URL bắt buộc | Fail startup, báo key bị thiếu |
| Timeout không parse được | Fail startup, báo định dạng mong đợi |
| Secret reference sai hoặc không có quyền | Fail startup nếu secret thiết yếu; cảnh báo và sửa IAM/config |
| Config service tạm thời timeout | Retry startup có giới hạn hoặc dùng snapshot hợp lệ theo policy |
| Dynamic config refresh thất bại | Giữ snapshot cũ trong giới hạn cho phép hoặc fail closed nếu policy nhạy cảm |
| Config version không được hỗ trợ | Fail fast, không tự bỏ qua field quan trọng |
| Cấu hình mới gây lỗi sau rollout | Rollback revision/alias và giữ dữ liệu tương thích |

Không retry vô hạn trong startup. Với lỗi tạm thời, dùng exponential backoff có jitter và giới hạn tổng thời gian. Nếu startup fail, cần log key/source bị lỗi, loại exception và correlation ID; không log credential hay giá trị cấu hình nhạy cảm.

### Readiness và liveness

Readiness trả lời ứng dụng đã sẵn sàng nhận traffic chưa. Liveness trả lời process còn sống và có thể tiếp tục hoạt động không. Không dùng liveness probe để kiểm tra mọi dependency bên ngoài ở mỗi chu kỳ vì database chập chờn có thể khiến instance bị restart liên tục. Cloud Run và các nền tảng container có thể dùng startup/readiness/liveness probes; AWS Lambda không có HTTP readiness probe tương đương, nên lỗi cấu hình trong initialization thường được thể hiện qua init/invocation failure và cần được theo dõi bằng log, metric cùng trạng thái deployment.

Kiểm tra cấu hình bắt buộc nên xảy ra trước readiness. Health endpoint có thể báo chưa sẵn sàng nếu service chưa hoàn tất startup. Với dependency tùy chọn, cần xác định rõ service có thể phục vụ một phần hay phải fail toàn bộ.

## 14. Checklist cấu hình cho Java serverless

- [ ] Artifact không chứa endpoint, queue name hoặc credential riêng của production.
- [ ] Mỗi key có tên rõ ràng, kiểu dữ liệu, đơn vị và mô tả.
- [ ] Có catalog phân biệt required, optional, secret và dynamic config.
- [ ] Có một nguồn chuẩn và precedence rõ ràng cho từng giá trị.
- [ ] Cấu hình được bind vào object có kiểu và bất biến.
- [ ] Required fields, format, range và cross-field rules được validate lúc startup.
- [ ] Default chỉ được dùng khi an toàn; giá trị bắt buộc bị thiếu thì fail fast.
- [ ] Secret nằm trong secret manager hoặc secret integration, không nằm trong source/image/log.
- [ ] Runtime identity chỉ đọc đúng secret/parameter cần thiết.
- [ ] Cấu hình trigger, timeout, retry, concurrency và connection pool tương thích.
- [ ] Startup không phụ thuộc vào các lời gọi remote không cần thiết.
- [ ] Warm instance dùng snapshot đã validate và không giữ request state trong cấu hình.
- [ ] Dynamic config có version, refresh, atomic snapshot và hành vi khi nguồn lỗi.
- [ ] Rotation có kế hoạch cập nhật cache và connection pool.
- [ ] Unit test bao phủ missing, malformed, out-of-range và conflicting values.
- [ ] Integration/deployment test xác minh IAM, secret reference và readiness.
- [ ] Log lỗi cấu hình không làm lộ secret hoặc dữ liệu nhạy cảm.

## Tự kiểm tra

1. Vì sao cùng một Java artifact nên được dùng qua nhiều môi trường với cấu hình khác nhau?
2. Những loại dữ liệu nào nên nằm trong secret manager thay vì file cấu hình hoặc environment variable?
3. Vì sao một default có thể làm ứng dụng chạy sai môi trường mà không phát hiện ngay?
4. Startup validation cần kiểm tra những gì ngoài việc property có tồn tại?
5. Vì sao nên bind cấu hình vào object bất biến thay vì gọi `System.getenv()` ở nhiều service?
6. Dynamic config khác startup/static config ở thời điểm đọc và yêu cầu consistency như thế nào?
7. Khi một secret được rotation, vì sao instance warm vẫn có thể dùng credential cũ?
8. Readiness khác liveness ra sao và tại sao không nên dùng liveness để kiểm tra mọi dependency?
9. Nếu cấu hình sai khiến tất cả instance mới fail startup, retry vô hạn có thể gây tác động gì?
10. Cần kiểm thử những trường hợp nào trước khi promote một revision lên production?

Tách cấu hình khỏi mã giúp một artifact Java có thể được triển khai nhất quán qua nhiều môi trường. Kiểm tra cấu hình ngay khi khởi động giúp phát hiện sai sót trước khi function nhận request hoặc message. Khi cấu hình được phân loại, bind thành object có kiểu, validate cả giá trị lẫn quan hệ giữa chúng và quản lý secret/dynamic update có chủ đích, hệ thống serverless sẽ dễ triển khai, kiểm thử và khôi phục hơn.

