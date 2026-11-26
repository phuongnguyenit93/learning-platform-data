# Ánh xạ giá trị lồng nhau thành thuộc tính ứng dụng trong Spring Vault

Ứng dụng Java sử dụng **Spring Vault** để truy cập HashiCorp Vault có thể đặt cấu hình nhạy cảm ở KV secrets engine thay vì ghi password, API key hoặc thông tin kết nối vào `application.yml`. Nếu secret chứa JSON lồng nhau, làm thế nào Spring hiểu `gateway.tls.enabled`, `payments.retry.delays[0]` hoặc ánh xạ chúng sang một Java record có kiểu?

Bài thuộc chương **Nguồn cấu hình** của module **SPRING_VAULT**. Mục tiêu là phân biệt cấu trúc phản hồi KV v1/v2 với dữ liệu thực, hiểu cách `VaultPropertySource` flatten map/list, thiết lập prefix và thứ tự ưu tiên nguồn cấu hình, dùng Spring `Environment` và Spring Boot `@ConfigurationProperties`, xử lý các tình huống khó (list, map đặc biệt, va chạm tên), đồng thời hiểu giới hạn cập nhật cấu hình khi Vault rotation.

> **Nguyên tắc:** Spring Vault **nạp** secret rồi cung cấp property key; Spring Boot Binder **chuyển đổi** những key/value thành Java object. Việc dữ liệu trong Vault được cập nhật không có nghĩa các Spring bean đã khởi tạo sẽ tự đổi theo.

## 1. Ba tầng dữ liệu của KV v2

Giả sử mount `secret/` là **KV v2**, có logical path `secret/payments/runtime`. Vault HTTP API đọc secret thực tế qua `GET /v1/secret/data/payments/runtime`. Ví dụ response (đã che secret):

~~~json
{
  "request_id": "f2e3...",
  "lease_id": "",
  "lease_duration": 0,
  "renewable": false,
  "data": {
    "data": {
      "gateway": {
        "url": "https://gateway.internal.example",
        "connect-timeout": "3s",
        "tls": {"enabled": true}
      },
      "retry": {
        "max-attempts": 3,
        "delays": ["200ms", "1s"]
      },
      "credentials": {
        "api-key": "<REDACTED>"
      }
    },
    "metadata": {
      "version": 4,
      "created_time": "2026-11-25T00:00:00Z"
    }
  }
}
~~~

Có ba nhóm thông tin:

| Vùng dữ liệu | Nội dung | Có phải cấu hình nghiệp vụ? |
| --- | --- | --- |
| `response.data.data` | Map `gateway`, `retry`, `credentials` do ứng dụng lưu. | **Có.** Đây là dữ liệu cần đưa vào property source. |
| `response.data.metadata` | Phiên bản, thời gian tạo và metadata của KV v2. | **Không** trong trường hợp binding cấu hình thông thường. |
| `request_id`, `lease_id`, `lease_duration` | Envelope của Vault HTTP response. | Không phải các thuộc tính như timeout/retry của ứng dụng. |

`VaultPropertySource` và cơ chế KV của Spring Vault biết cách đọc **dữ liệu secret**, thay vì bắt người dùng lấy property `data.data.gateway.url`. Sau khi flatten, tên sẽ là `gateway.url` hoặc `payments.gateway.url` nếu ứng dụng thêm prefix.

**Lưu ý về path:** khi tạo `VaultPropertySource` hoặc `@VaultPropertySource` cho **KV v2**, dùng **logical path** `secret/payments/runtime`, **không tự chèn `data/`**. Trong Vault ACL policy, đường dẫn thực vẫn cần capability `read` trên `secret/data/payments/runtime`. Hai quy tắc không mâu thuẫn vì một bên là đường dẫn Spring Vault quản lý, một bên là REST API của Vault.

## 2. Flatten map và list thành tên property

Spring Vault có `org.springframework.vault.support.JsonMapFlattener`. Nó biến `Map<String,Object>` lồng nhau thành map phẳng, trong đó key là **đường dẫn tới giá trị**.

Đầu vào là map nghiệp vụ (không bao gồm envelope):

~~~json
{
  "gateway": {
    "url": "https://gateway.internal.example",
    "connect-timeout": "3s",
    "tls": {"enabled": true}
  },
  "retry": {
    "max-attempts": 3,
    "delays": ["200ms", "1s"]
  },
  "credentials": {"api-key": "<REDACTED>"}
}
~~~

Đầu ra tương đương:

~~~properties
gateway.url=https://gateway.internal.example
gateway.connect-timeout=3s
gateway.tls.enabled=true
retry.max-attempts=3
retry.delays[0]=200ms
retry.delays[1]=1s
credentials.api-key=<REDACTED>
~~~

| Kiểu nguồn | Quy tắc key | Ví dụ |
| --- | --- | --- |
| Scalar (String, number, boolean) | Giữ đường dẫn tới leaf. | `gateway.url`, `retry.max-attempts`, `gateway.tls.enabled`. |
| Map chứa Map | Ghép các nhánh bằng dấu chấm. | `gateway.tls.enabled`. |
| List các giá trị | Chỉ số dùng `[0]`, `[1]`… | `retry.delays[0]`, `retry.delays[1]`. |
| List các Map | Dùng chỉ số rồi đến tên trường. | `clients[0].name`, `clients[1].timeout`. |
| Key vốn có dấu chấm | Có nguy cơ trùng với đường dẫn sau flatten. | `"gateway.url"` và `{"gateway":{"url":...}}`. |

### 2.1. Ví dụ Java dùng JsonMapFlattener

~~~java
import java.util.List;
import java.util.Map;
import org.springframework.vault.support.JsonMapFlattener;

public final class FlattenExample {

    public static void main(String[] args) {
        Map<String, Object> data = Map.of(
                "gateway", Map.of(
                        "url", "https://gateway.internal.example",
                        "tls", Map.of("enabled", true)),
                "retry", Map.of(
                        "max-attempts", 3,
                        "delays", List.of("200ms", "1s")));

        Map<String, Object> properties = JsonMapFlattener.flatten(data);

        System.out.println(properties.get("gateway.url"));      // URL minh họa.
        System.out.println(properties.get("gateway.tls.enabled")); // true
        System.out.println(properties.get("retry.delays[0]"));   // 200ms
    }
}
~~~

`flatten(...)` giữ các leaf value là `Object` phù hợp; `flattenToStringMap(...)` trả về `Map<String,String>`. Đây là bước **đổi cấu trúc key**, không phải giải mã mật khẩu hay tự động chuyển một chuỗi `"3s"` thành `Duration`. Type conversion diễn ra khi Binder hoặc conversion service sử dụng các property.

Trong ứng dụng thật, **không log toàn bộ** `properties` hoặc input map vì chúng có thể chứa bearer token và password.

### 2.2. Tránh tên va chạm

Đây là JSON có hai cách biểu diễn cùng một key phẳng:

~~~json
{
  "gateway.url": "https://a.example",
  "gateway": {
    "url": "https://b.example"
  }
}
~~~

Khi trải phẳng, cả hai có thể trở thành `gateway.url`. Không được dựa vào thứ tự duyệt map để xác định giá trị thắng. Chọn **một schema nhất quán**: hoặc lưu nested object, hoặc lưu flat key, nhưng không để trùng nhau.

## 3. VaultPropertySource đọc secret và đưa vào Environment

`VaultPropertySource` nằm ở package `org.springframework.vault.core.env` và kế thừa `EnumerablePropertySource`. Spring Vault cung cấp constructor đọc secret bằng `VaultOperations`/`VaultTemplate`:

~~~java
import org.springframework.vault.core.env.VaultPropertySource;

// vaultTemplate đã được cấu hình Vault URL, TLS và ClientAuthentication.
VaultPropertySource source =
        new VaultPropertySource(
                vaultTemplate, "secret/payments/runtime");
~~~

Property source đọc dữ liệu khi **khởi tạo**, flatten nested map thành các key như `gateway.url` và `retry.delays[0]`. Nó không tự động đưa các key vào Spring `Environment` cho đến khi được **đăng ký**.

Để truy cập Vault KV v2, Spring Vault có thể cần tra cứu thông tin mount qua `sys/internal/ui/mounts/...`. Vì thế workload token cần quyền truy cập path secret thực tế và môi trường Vault cần cho phép xác định mount. Đừng ghi đè ACL quá rộng khi gặp lỗi; xác định request nào bị từ chối.

### 3.1. Đăng ký bằng @VaultPropertySource

Cách khai báo ngắn gọn trên một lớp `@Configuration`:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.vault.annotation.VaultPropertySource;

@Configuration
@VaultPropertySource(
        value = "secret/payments/runtime",
        propertyNamePrefix = "payments.",
        ignoreSecretNotFound = false)
public class PaymentVaultConfiguration {
}
~~~

Annotation sẽ đóng góp property source vào Spring Environment. `propertyNamePrefix` được **ghép nguyên văn** vào tên property đã flatten; với `"payments."` sẽ có:

~~~properties
payments.gateway.url=https://gateway.internal.example
payments.gateway.connect-timeout=3s
payments.gateway.tls.enabled=true
payments.retry.max-attempts=3
payments.retry.delays[0]=200ms
payments.retry.delays[1]=1s
payments.credentials.api-key=<REDACTED>
~~~

**Prefix không đổi Vault path.** `payments.` chỉ giúp tổ chức tên property. Nếu viết `propertyNamePrefix="payments"` (không có dấu chấm cuối), key có thể trở thành `paymentsgateway.url` và không khớp prefix mà Binder tìm.

`ignoreSecretNotFound` mặc định **true** ở annotation. Nếu secret này bắt buộc, đặt `false` và kiểm tra lỗi khởi tạo. Không dùng giá trị rỗng thay cho credential chỉ để cho ứng dụng chạy tiếp.

### 3.2. Đọc qua Environment

~~~java
import org.springframework.core.env.Environment;
import org.springframework.stereotype.Component;

@Component
public final class PaymentEndpoint {

    private final String url;

    public PaymentEndpoint(Environment env) {
        String configured = env.getRequiredProperty(
                "payments.gateway.url");

        if (!configured.startsWith("https://")) {
            throw new IllegalStateException("Endpoint phải dùng HTTPS");
        }

        this.url = configured;
    }

    public String url() {
        return url;
    }
}
~~~

Có thể dùng `@Value("${payments.gateway.url}")` nếu source đã có tại thời điểm bean khởi tạo. Với cấu hình nhiều nhánh, nên dùng `@ConfigurationProperties` thay vì tạo nhiều chục `@Value`.

### 3.3. Placeholder trong path

~~~java
@Configuration
@VaultPropertySource(
        value = "secret/${my.vault.context:payments}/runtime",
        propertyNamePrefix = "payments.",
        ignoreSecretNotFound = false)
class ContextualVaultProperties {
}
~~~

`my.vault.context` phải đến từ một property source **đã đăng ký trước**, ví dụ môi trường hoặc system property. Nếu thiếu, path fallback thành `secret/payments/runtime`. Không trông chờ dùng property nằm trong chính secret Vault này để tính path của nó: điều đó gây vòng phụ thuộc bootstrap.

## 4. Bind JSON lồng nhau sang @ConfigurationProperties của Spring Boot

`Environment` cho phép lấy từng property dạng String/Object, còn Spring Boot **Binder** chuyển chúng thành Java object có cấu trúc. Ví dụ với **Spring Boot 3.x và Java 17+**, một record:

~~~java
import java.net.URI;
import java.time.Duration;
import java.util.List;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "payments")
public record PaymentProperties(
        Gateway gateway,
        Retry retry,
        Credentials credentials) {

    public record Gateway(URI url, Duration connectTimeout, Tls tls) {
    }

    public record Tls(boolean enabled) {
    }

    public record Retry(int maxAttempts, List<Duration> delays) {
    }

    public record Credentials(String apiKey) {
    }
}
~~~

Đăng ký bean cấu hình:

~~~java
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Configuration;

@Configuration
@EnableConfigurationProperties(PaymentProperties.class)
class PaymentPropertiesRegistration {
}
~~~

Sử dụng ở service:

~~~java
import org.springframework.stereotype.Service;

@Service
public final class PaymentService {

    private final PaymentProperties properties;

    public PaymentService(PaymentProperties properties) {
        this.properties = properties;
    }

    public void printSafeSettings() {
        System.out.println(properties.gateway().url().getScheme());
        System.out.println(properties.gateway().connectTimeout());
        System.out.println(properties.retry().maxAttempts());
        System.out.println(properties.retry().delays().get(0));

        // Không log properties.credentials().apiKey().
    }
}
~~~

Ánh xạ kết quả:

| Property được flatten và prefix | Field record | Type conversion |
| --- | --- | --- |
| `payments.gateway.url` | `gateway.url` | String URL → `URI`. |
| `payments.gateway.connect-timeout` | `gateway.connectTimeout` | `"3s"` → `Duration` 3 giây. |
| `payments.gateway.tls.enabled` | `gateway.tls.enabled` | `true` → `boolean`. |
| `payments.retry.max-attempts` | `retry.maxAttempts` | Số nguyên → `int`. |
| `payments.retry.delays[0]` | `retry.delays.get(0)` | `"200ms"` → `Duration`. |
| `payments.retry.delays[1]` | `retry.delays.get(1)` | `"1s"` → `Duration`. |
| `payments.credentials.api-key` | `credentials.apiKey` | Credential → `String` (nhạy cảm). |

`JsonMapFlattener` không tự chuyển kebab-case sang camelCase. **Spring Boot relaxed binding** mới làm cho `connect-timeout` và `connectTimeout` khớp nhau.

Đừng dùng `toString()` của record `PaymentProperties` trong log: record chứa cả `apiKey` và `toString()` mặc định có thể tiết lộ nó. Với credential production, cân nhắc tách secret object và cơ chế truyền trực tiếp cho consumer.

### 4.1. Validation và dữ liệu bị thiếu

Một secret có thể thiếu `gateway.url`, chứa timeout sai định dạng hoặc một `retry.delays` rỗng. Sau binding, nên kiểm tra các invariant cần thiết và fail startup nếu cấu hình bắt buộc không hợp lệ. Có thể dùng `@Validated` + Jakarta Bean Validation nếu dự án đã cấu hình dependency và annotation tương ứng.

`@ConfigurationProperties` thuộc **Spring Boot**, không thuộc Spring Vault core. Nếu dùng Spring Framework thuần và chỉ có `VaultTemplate`, bạn có thể dùng `Environment` rồi chuyển đổi, hoặc tích hợp Binder riêng. Không giả định chỉ thêm dependency `spring-vault-core` là đủ để bind record theo kiểu Spring Boot.

## 5. Điều khiển thứ tự các nguồn bằng MutablePropertySources

Khi nhiều nguồn cùng cung cấp `payments.gateway.url` (Vault, YAML, environment variables), **thứ tự ưu tiên** quyết định giá trị nào được dùng.

Ví dụ đăng ký bằng code trong một pha bootstrap thích hợp:

~~~java
import org.springframework.context.support.GenericApplicationContext;
import org.springframework.core.env.MutablePropertySources;
import org.springframework.vault.core.env.VaultPropertySource;

GenericApplicationContext context = new GenericApplicationContext();
MutablePropertySources sources =
        context.getEnvironment().getPropertySources();

// vaultTemplate đã được tạo và xác thực trước, không phụ thuộc
// vào chính secret đang chờ nạp.
VaultPropertySource vaultSource = new VaultPropertySource(
        "vault-payments",
        vaultTemplate,
        "secret/payments/runtime");

// Nguồn Vault được tìm kiếm đầu tiên trong ví dụ này.
sources.addFirst(vaultSource);

String url = context.getEnvironment()
        .getRequiredProperty("gateway.url");

// Đây chỉ minh họa property source ordering; production cần
// đăng ký trước context.refresh() và bean binding.
~~~

| API `MutablePropertySources` | Ý nghĩa |
| --- | --- |
| `addFirst(source)` | Ưu tiên source mới cao nhất. |
| `addLast(source)` | Ưu tiên source mới thấp hơn những source có sẵn. |
| `addBefore(name, source)` | Chèn source trước nguồn có tên xác định. |
| `addAfter(name, source)` | Chèn source sau nguồn có tên xác định. |
| `replace(name, source)` | Thay source bằng source khác. |

Nếu có:

~~~properties
# Vault source (ưu tiên cao)
gateway.url=https://vault.example

# YAML source (ưu tiên thấp)
gateway.url=https://yaml.example
~~~

`Environment.getProperty("gateway.url")` nhận `https://vault.example`. Nhưng điều này **không đồng nghĩa** Spring ghép hai object JSON trước khi bind. Các key được xử lý theo từng tên property và quy tắc Binder.

### 5.1. Danh sách thường thay thế toàn bộ, không ghép từng phần

Một trường hợp dễ sai:

~~~properties
# application.yml biểu diễn dạng flat:
payments.retry.delays[0]=200ms
payments.retry.delays[1]=1s
~~~

Source có ưu tiên cao hơn chỉ cung cấp:

~~~properties
payments.retry.delays[0]=500ms
~~~

Khi Binder bind `List<Duration>`, Spring Boot thường dùng **list từ source ưu tiên cao hơn**, không tự ghép thêm `[1]` của source thấp hơn. Với `Map`, có thể kết hợp key khác nhau từ nhiều nguồn, nhưng **cùng key** thì nguồn ưu tiên cao thắng. Vì vậy, khi thay đổi precedence hãy test cả **giá trị** và **hình dạng object kết quả**.

### 5.2. Annotation order có thể khó dự đoán

Khi dùng nhiều `@VaultPropertySource` ở những class `@Configuration` được component-scan, thứ tự đăng ký không phải lúc nào cũng tiện kiểm soát. Nếu cần precedence tuyệt đối, nên dùng `MutablePropertySources` có chủ đích hoặc Spring Cloud Vault ConfigData ở pha bootstrap.

Không tự động `addFirst` trong mọi ứng dụng: có hệ thống cần environment override để xử lý khẩn cấp, có hệ thống bắt buộc Vault là nguồn quyền cao nhất của credential. Cần lựa chọn quy tắc theo chính sách vận hành.

## 6. Spring Vault core khác Spring Cloud Vault ConfigData

Spring Vault core và Spring Cloud Vault đều có thể đưa secret vào `Environment` nhưng khác cấp độ tích hợp:

| Giải pháp | Ưu điểm | Lưu ý |
| --- | --- | --- |
| `@VaultPropertySource` | Dùng trực tiếp trong Spring configuration; phù hợp ứng dụng đã có `VaultTemplate`. | Cần đúng thứ tự khởi tạo source và consumer. |
| `new VaultPropertySource(...)` | Kiểm soát rõ path và vị trí trong `MutablePropertySources`. | Phải tự đảm bảo client Vault/TLS/auth đã sẵn sàng ở pha bootstrap. |
| Spring Cloud Vault `spring.config.import` | Spring Boot import Vault contexts qua ConfigData từ sớm. | Cần starter và phiên bản Spring Boot/Cloud tương thích. |
| `VaultTemplate.opsForKeyValue(...)` | Mã nghiệp vụ nhận object secret trực tiếp, metadata/version theo nhu cầu. | Không tự đưa map vào `Environment` hay binder. |

Ví dụ Spring Cloud Vault khi đã có dependency tương ứng:

~~~yaml
spring:
  application:
    name: payments-api
  config:
    import: "vault://"
  cloud:
    vault:
      uri: "https://vault.internal.example:8200"
      kv:
        enabled: true
        backend: secret
~~~

`vault://` dùng những context paths mặc định theo application/profile. Có thể chỉ định contextual path và prefix theo tính năng ConfigData:

~~~yaml
spring:
  config:
    import: "vault:///secret/payments/runtime?prefix=payments."
~~~

Đây là **cấu hình Spring Cloud Vault**, không phải annotation của Spring Vault core. Cần kiểm tra context path thực, KV backend, phiên bản và cấu hình auth trong deployment. Đừng tự thêm `data/` vào logical path chỉ vì Vault KV v2 REST API sử dụng đoạn đó.

Nếu đã dùng ConfigData nạp cùng path, việc thêm một `@VaultPropertySource` riêng có thể tạo nguồn trùng và precedence khó hiểu; nên chọn một chiến lược phù hợp.

## 7. Các kiểu dữ liệu lồng nhau cần kiểm thử riêng

### 7.1. List chứa object

~~~json
{
  "gateway": {
    "endpoints": [
      {"name": "primary", "url": "https://primary.internal"},
      {"name": "backup", "url": "https://backup.internal"}
    ]
  }
}
~~~

Sau flatten:

~~~properties
gateway.endpoints[0].name=primary
gateway.endpoints[0].url=https://primary.internal
gateway.endpoints[1].name=backup
gateway.endpoints[1].url=https://backup.internal
~~~

Có thể bind sang `List<Endpoint>` nếu model Java đúng. Trường bắt buộc thiếu hoặc index không liên tục cần được validate; đừng coi list rỗng mặc nhiên là cấu hình hợp lệ.

### 7.2. Map có key chứa dấu chấm

~~~json
{
  "limits": {
    "api.v1": {"requests": 100}
  }
}
~~~

Flatten thông thường tạo `limits.api.v1.requests`; Binder có thể hiểu `api.v1` là nhiều cấp thay vì một literal key trong `Map`. Nếu business key phải giữ dấu chấm, kiểm tra cú pháp map bracket của Spring Boot hoặc đổi schema sang key an toàn (`api-v1`) trước khi nạp.

### 7.3. Null, map rỗng và list rỗng

Flat properties không giữ nguyên mọi phân biệt giữa `null`, nhánh không tồn tại, map rỗng hay list rỗng. `Environment.getProperty(...) == null` không luôn đủ để biết nguyên nhân. Với nhu cầu phải bảo toàn JSON đầy đủ, nên đọc trực tiếp qua `VaultTemplate`/`VaultKeyValueOperations` và parse object theo schema riêng, thay vì ép tất cả vào application properties.

### 7.4. Một tên key xuất hiện nhiều dạng

Tránh vừa có:

~~~json
{
  "gateway.url": "https://flat.example",
  "gateway": {"url": "https://nested.example"}
}
~~~

Hai nhánh có thể flatten thành cùng `gateway.url`; giá trị cuối có thể phụ thuộc thứ tự duyệt map. Không dựa vào kết quả ngẫu nhiên: định nghĩa quy ước tên và kiểm thử fixture có va chạm.

## 8. Secret thay đổi: property source có cập nhật bean không?

Một hiểu lầm phổ biến: cập nhật KV v2 trong Vault thì các field `@Value` hoặc `@ConfigurationProperties` của bean đang chạy sẽ lập tức đổi theo.

Thực tế có nhiều tầng:

1. Vault KV v2 tạo **phiên bản dữ liệu mới**.
2. `VaultPropertySource` mặc định **đọc dữ liệu khi được tạo**, không tự nhận mọi thay đổi KV theo thời gian thực.
3. `LeaseAwareVaultPropertySource` hoặc cơ chế renewal/rotation có thể cập nhật **property source hiện tại** khi nó xử lý sự kiện, tùy backend và cấu hình.
4. `@Value` thông thường tiêm một giá trị vào bean khi khởi tạo; không tự động tiêm lại.
5. `@ConfigurationProperties` thường bind lúc bean khởi tạo; không tự rebind chỉ vì một property source vừa thay đổi.
6. Nếu consumer cần cập nhật runtime, phải triển khai **refresh/rebinding hoặc callback rotation** tương ứng và kiểm tra kết nối thực sự sử dụng credential mới.

### 8.1. Renewal/rotation của @VaultPropertySource

`@VaultPropertySource` có thuộc tính `renewal`, mặc định `Renewal.OFF`. Với dynamic database secrets, ví dụ:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.vault.annotation.VaultPropertySource;
import org.springframework.vault.annotation.VaultPropertySource.Renewal;

@Configuration
@VaultPropertySource(
        value = "database/creds/reporting",
        propertyNamePrefix = "reporting.",
        renewal = Renewal.ROTATE)
class ReportingVaultPropertySource {
}
~~~

Ví dụ này liên quan **dynamic secret có lease**, không có nghĩa KV v2 tĩnh luôn có `lease_id`. Khi credential được rotate, property source có thể nhận giá trị mới; JDBC pool đã mở không tự đổi username/password trên mọi connection.

Nếu cần cập nhật pool hoặc client theo vòng đời secret, cân nhắc `SecretLeaseContainer` và listener/`ManagedSecret` (khi phiên bản hỗ trợ), kiểm tra consumer kết nối thành công với credential mới rồi mới đánh readiness=READY. Tránh block thread renewal bằng tác vụ JDBC kéo dài.

## 9. Troubleshooting: sai schema, path, prefix và thứ tự

| Triệu chứng | Nguyên nhân thường gặp | Hướng xử lý |
| --- | --- | --- |
| `getProperty("data.data.gateway.url")` là null | Nhầm envelope KV v2 với data business mà property source đã bóc. | Tra cứu `gateway.url` hoặc `payments.gateway.url` nếu có prefix. |
| `payments.gateway.url` là null | Prefix thiếu dấu chấm, path sai, source chưa được thêm hoặc key không có. | Kiểm tra `propertyNamePrefix="payments."` và thời điểm bootstrap. |
| HTTP 403 khi tạo VaultPropertySource | Token thiếu ACL, namespace/mount sai hoặc kiểm tra mount không được cho phép. | Xem Vault ACL tại `secret/data/...` và mount lookup, không cấp root để sửa tạm. |
| HTTP 404 / secret không tồn tại | Path/mount sai hoặc key chưa được ghi. | Kiểm tra logical path, KV version và `ignoreSecretNotFound`. |
| Bean record có field null | Binder chưa chạy, model/prefix sai hoặc field không tồn tại. | Kiểm tra `@EnableConfigurationProperties`, property key và validation. |
| `Duration` không parse được | String không đúng duration format hoặc type dữ liệu bất thường. | Dùng `3s`, `200ms`, `1m` theo Binder. |
| List bị mất phần tử | Source ưu tiên cao thay toàn bộ list. | Định nghĩa list đầy đủ và test precedence. |
| API key bị log ra console | In `Map`/`Environment` hoặc record `toString()`. | Redact, không expose Actuator env values. |
| Vault đã rotate nhưng bean giữ password cũ | Source và bean lifecycle khác nhau; không có rebind/cập nhật consumer. | Thiết kế callback/reload và chuyển pool có kiểm soát. |
| App start dù secret bắt buộc không tồn tại | `ignoreSecretNotFound` mặc định true, không có validation. | Đặt false và kiểm tra required config khi khởi động. |
| Cấu hình đúng nhưng precedence bất ngờ | Có nhiều Vault path/YAML/config imports cùng tên property. | Xác định `PropertySources` order, dùng prefix hoặc thứ tự chèn tường minh. |

### 9.1. Kiểm tra chỉ tên thuộc tính

`VaultPropertySource` có `getPropertyNames()`. Khi kiểm tra, chỉ xác nhận key tồn tại, không in giá trị nhạy cảm:

~~~java
import java.util.Arrays;
import org.springframework.vault.core.env.VaultPropertySource;

// source là VaultPropertySource đã được tạo bằng VaultTemplate.
String[] names = source.getPropertyNames();

if (!Arrays.asList(names).contains("gateway.url")) {
    throw new IllegalStateException("Thiếu gateway.url");
}
~~~

Đừng in toàn bộ `source`, `Map` chứa secret hoặc exception chứa HTTP body/token để debug.

## 10. Kiểm thử tích hợp trên Vault

Dùng Vault trong môi trường test cô lập, mount KV v2 `secret/` và policy chỉ cho đọc `secret/data/payments/runtime`. Hãy kiểm tra bằng token của workload, không chỉ bằng Vault root token.

| Ca thử | Dữ liệu đầu vào | Kỳ vọng |
| --- | --- | --- |
| Nested map | `gateway.tls.enabled = true` trong map lồng nhau. | `payments.gateway.tls.enabled` tồn tại và bind boolean. |
| List | `retry.delays = ["200ms","1s"]`. | Có `[0]`/`[1]` và bind `List<Duration>`. |
| Scalar conversion | `"connect-timeout": "3s"`. | Bind thành `Duration.ofSeconds(3)`. |
| Prefix sai | Dùng `"payments"` thay vì `"payments."`. | Test phát hiện key sai; sửa prefix. |
| KV2 API path | Path logical cho annotation và path REST cho ACL khác nhau. | Source đọc được khi ACL đúng; không cần tự chèn `data/` vào annotation. |
| Source priority | Cùng key ở Vault và application YAML. | Environment nhận giá trị từ source ưu tiên cao. |
| List override | Nguồn cao chỉ đặt `delays[0]`. | Binder dùng quy tắc list replacement, không trộn ngầm. |
| Missing secret | `ignoreSecretNotFound=false`, key không tồn tại. | Khởi tạo fail theo chính sách; không silently dùng credential null. |
| Secret refresh | Sửa giá trị Vault sau khi bean được tạo. | Xác minh source và bean có đổi hay không; thiết kế refresh nếu cần. |
| Collision | Flat key và nested key trùng tên sau flatten. | Bộ kiểm thử phát hiện dữ liệu mơ hồ, schema bị từ chối. |

### 10.1. Bài tập tình huống

**A.** Vault KV v2 trả:

~~~json
{
  "data": {
    "data": {
      "service": {
        "port": 8443,
        "tls": {"enabled": true}
      }
    },
    "metadata": {"version": 2}
  }
}
~~~

Annotation có `propertyNamePrefix="internal."`. Tên thuộc tính là gì?

**Đáp án:** `internal.service.port` và `internal.service.tls.enabled`; không phải `internal.data.data.service.port` hay `internal.metadata.version`.

**B.** Vault có `{"retry":{"delays":["100ms","500ms"]}}`. Tại sao `retry.delays.0` không tìm thấy?

**Đáp án:** List được flatten thành `retry.delays[0]` và `retry.delays[1]`; hãy dùng cú pháp bracket.

**C.** `@VaultPropertySource("secret/payments/runtime")` không có prefix, còn bean bind `@ConfigurationProperties(prefix="payments")`. Điều gì xảy ra?

**Đáp án:** Source cung cấp `gateway.*` nhưng binder tìm `payments.gateway.*`, dẫn tới thiếu cấu hình. Thêm `propertyNamePrefix="payments."` hoặc thay schema/binding cho phù hợp.

**D.** Vault property source đã đổi password nhưng bean `PaymentProperties` vẫn giữ password ban đầu. Tại sao?

**Đáp án:** Binding thường xảy ra khi bean khởi tạo; cập nhật property source không tự động rebind bean. Cần refresh hoặc callback rotation chuyển credential mới tới consumer.

**E.** Hai nguồn đặt `payments.retry.delays`: nguồn ưu tiên cao chỉ có index 0, nguồn thấp có index 0 và 1. Có thể giả định Binder nối hai list không?

**Đáp án:** Không. List thường bị thay thế hoàn toàn theo nguồn ưu tiên; test và khai báo list đầy đủ ở nguồn chủ đích.

**F.** Một secret có cả `"service.url"` và `{"service":{"url":...}}`. Rủi ro?

**Đáp án:** Hai nhánh có thể tạo cùng flat key, gây xung đột. Nên chuẩn hóa tên và tránh biểu diễn trùng.

## 11. Bảo mật và vận hành

Khi đưa dữ liệu Vault vào `Environment`, bí mật sẽ xuất hiện trong bộ nhớ ứng dụng, có thể được đưa qua cơ chế property binding và nguy cơ lọt vào error report hoặc monitoring nếu cấu hình bất cẩn.

- Chỉ cấp Vault token **quyền đọc đúng API path** cần thiết, không dùng root token hoặc policy wildcard để dễ chạy demo.
- Giữ `VaultTemplate` kết nối qua TLS hợp lệ; không tắt kiểm chứng certificate.
- Không commit token, password, SecretID hay JSON credential vào Git; dùng workload authentication thích hợp (AppRole, Kubernetes, GCP, AWS...).
- Không log raw Vault response, property map, record `toString()` chứa API key, hoặc `Environment` dump.
- Bảo vệ endpoint Actuator như `/actuator/env` và `/actuator/configprops` theo cấu hình an toàn; không expose secret values.
- Khi rotation, theo dõi cả **trạng thái Vault** lẫn **consumer đang dùng credential nào**, không coi source refresh là thành công cuối cùng.
- Tránh vòng phụ thuộc: muốn tạo Vault client cần một số bootstrap properties đã có **trước** khi đọc secret, không thể yêu cầu Vault cấp chính thông tin cần để kết nối tới Vault mà không có cơ chế bootstrap độc lập.
- Nếu secret là cấu hình bắt buộc, fail startup hoặc giữ readiness=false thay vì dùng chuỗi rỗng/giá trị giả làm credential.

## 12. Tóm tắt và tài liệu gốc

- `VaultPropertySource` nạp dữ liệu secret vào Spring `Environment`; với KV v2, dùng **logical path** không tự chèn `data/`.
- `JsonMapFlattener` chuyển nested map thành **dot notation** (`gateway.tls.enabled`), list thành **bracket notation** (`retry.delays[0]`).
- `propertyNamePrefix` thêm prefix **nguyên văn**; để tạo phân cấp hãy dùng `"payments."` thay vì `"payments"`.
- `@ConfigurationProperties` của **Spring Boot** bind các key phẳng sang Java records/object và đổi kiểu, gồm `Duration`, `URI`, `boolean` và list.
- **Precedence** quyết định giá trị của property key trùng; list từ nhiều nguồn thường **không** merge theo chỉ số.
- **Binding và refresh khác nhau**: secret đổi trong Vault không làm Java bean đã bind tự đổi nếu thiếu chiến lược reload/rotation.
- Hãy test schema, path, type, prefix, precedence và consumer rotation bằng workload token có quyền tối thiểu.

Tài liệu chính thức:

1. [Spring Vault – Property Sources](https://docs.spring.io/spring-vault/reference/vault/propertysource.html): `VaultPropertySource`, `@VaultPropertySource`, logical KV paths và precedence.
2. [Spring Vault – VaultPropertySource API](https://docs.spring.io/spring-vault/reference/api/java/org/springframework/vault/core/env/VaultPropertySource.html): constructor, `flattenMap`, `getPropertyNames()`.
3. [Spring Vault – JsonMapFlattener API](https://docs.spring.io/spring-vault/reference/api/java/org/springframework/vault/support/JsonMapFlattener.html): nested maps/lists và cú pháp flatten.
4. [Spring Vault – @VaultPropertySource API](https://docs.spring.io/spring-vault/reference/api/java/org/springframework/vault/annotation/VaultPropertySource.html): prefix, renewal, ignoreSecretNotFound.
5. [Spring Boot – Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html): Binder, relaxed binding, list/map precedence.
6. [Spring Cloud Vault – ConfigData](https://docs.spring.io/spring-cloud-vault/reference/config-data.html): ConfigData import và contextual locations.
7. [HashiCorp Vault – KV v2](https://developer.hashicorp.com/vault/docs/secrets/kv/kv-v2): versioned KV và metadata.

Hiểu đúng **các lớp dữ liệu của Vault**, **quy tắc flatten**, **Spring property naming** và **vòng đời bean** giúp ứng dụng ánh xạ cấu hình lồng nhau chính xác, giảm lỗi runtime và quản lý secret an toàn.
