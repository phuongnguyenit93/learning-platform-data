# Giới hạn việc in DTO chứa secret ra log hoặc thông báo lỗi

## Mục tiêu bài học

Khi sử dụng **Spring Vault**, việc ánh xạ phản hồi JSON thành DTO giúp mã Java có kiểu rõ ràng, dễ kiểm tra và giảm việc truyền `Map<String, Object>` xuyên ứng dụng. Nhưng nó cũng tạo ra một rủi ro ít được chú ý: một DTO chứa API key, password, token hoặc private key có thể bị **in ra ngoài ý muốn** qua `toString()`, ghi log có tham số, trình serialize JSON, exception, HTTP request/response logging, trace hoặc thông báo lỗi công khai.

Một bản ghi log thường được sao chép đến nhiều nơi: console, file, hệ thống thu thập log, dịch vụ giám sát, công cụ hỗ trợ khách hàng và kho lưu trữ dài hạn. Vì vậy, **đọc được secret không đồng nghĩa được phép ghi lại secret**. Việc Vault kiểm soát truy cập bằng workload authentication và policy không tự động áp dụng cùng quyền hạn cho hệ thống logging của ứng dụng.

Bài thuộc chương **Ánh xạ dữ liệu** của module **SPRING_VAULT**. Sau bài học, bạn có thể:

1. Nhận diện đường rò rỉ secrets qua DTO, `VaultResponse`, `Versioned<T>`, `toString()`, serializer và exception.
2. Thiết kế DTO chứa secrets và cấu trúc log **an toàn mặc định**, không phụ thuộc một bộ lọc che chuỗi cuối đường ống.
3. Giữ giá trị bí mật tách khỏi metadata và mã lỗi phục vụ chẩn đoán.
4. Xử lý lỗi đọc KV v2, lỗi mapping, Transit và PKI mà không ghi payload nhạy cảm.
5. Chọn thông tin quan sát vừa đủ: loại thao tác, trạng thái, mã lỗi ổn định, độ trễ và một số metadata đã được đánh giá.
6. Viết kiểm thử chống rò rỉ và rà soát cấu hình logging/tracing trước khi triển khai.

> **Bối cảnh:** Module **SPRING_VAULT** hướng đến Java truy cập HashiCorp Vault qua `VaultTemplate`/`VaultOperations`, xác thực theo workload và Vault policy, thực hành KV secrets, token/lease lifecycle, Transit encryption, PKI, xử lý lỗi, giám sát và kiểm thử tích hợp. Các ví dụ giả định ứng dụng đã kết nối Vault và dùng dữ liệu giả. Bài này tập trung vào bảo vệ bí mật khi **ánh xạ và quan sát** dữ liệu, không thay thế cấu hình bảo mật của Vault.

## 1. Xác định tài sản cần bảo vệ và đường đi của dữ liệu

Một ứng dụng đọc secret KV v2 tại path logic `payments/gateway` có thể nhận:

```json
{
  "apiKey": "<gia-tri-bi-mat>",
  "endpoint": "https://payments.internal.example",
  "timeoutSeconds": 15,
  "retry": {
    "maxAttempts": 3
  }
}
```

Ứng dụng có thể ánh xạ dữ liệu thành `GatewaySecretDto`. Mã cấu hình HTTP client được phép sử dụng `apiKey` để gọi hệ thống đích, nhưng phần giám sát **không cần biết giá trị** API key.

```text
Vault (workload auth + policy)
    │
    ▼
VaultOperations / VaultTemplate
    │
    ▼
VaultResponseSupport<GatewaySecretDto>
    │ getData()
    ▼
GatewaySecretDto chứa apiKey
    ├── Thành phần HTTP client được phép sử dụng ───► Header Authorization
    └── Logging/tracing/exception/metrics        ───► KHÔNG đưa apiKey vào

Thay thế cho log DTO:
  operation=kv.read
  resource=payment-gateway (nhãn an toàn đã định nghĩa)
  outcome=success
  duration_ms=...
```

Điểm phân quyền khác nhau:

| Bên nhận | Cần dữ liệu nào? | Không nên nhận |
|---|---|---|
| Adapter Spring Vault | Path cần truy cập, DTO/schema, giá trị để ánh xạ | Quyền ghi log payload nguyên vẹn |
| Client nghiệp vụ | Giá trị tối thiểu thực sự cần, như API key và endpoint | Thông tin auth token của Vault, response nguyên bản |
| Log vận hành | Loại thao tác, kết quả, nhóm lỗi, latency | Token, password, API key, private key, plaintext |
| Metric | Tên thao tác và trạng thái thuộc tập nhãn có giới hạn | Secret value, request body, path động, token |
| Trace | Span name ổn định, trạng thái và các thuộc tính đã kiểm duyệt | Header Authorization, request/response body, secrets |
| API trả lỗi cho người dùng | Mã lỗi công khai, thông điệp trung tính | Giá trị Vault, stack trace nội bộ, đường dẫn nhạy cảm |

**Nguyên tắc:** kiểm soát truy cập vào Vault và kiểm soát thông tin thoát khỏi ứng dụng là hai lớp bảo vệ độc lập.

## 2. Những giá trị nhạy cảm thường có trong phản hồi Spring Vault

Trong thực tế, không phải mọi chuỗi trong phản hồi Vault đều là password. Tuy nhiên, an toàn nhất là phân loại theo **vai trò dữ liệu**, không dựa vào việc chuỗi đó “trông có vẻ bí mật” hay không.

| Nguồn | Dữ liệu có thể xuất hiện | Nguy cơ khi in ra |
|---|---|---|
| KV v1/KV v2 | API key, username/password, khóa cấu hình, token bên thứ ba | Lộ thông tin đăng nhập, khóa truy cập hệ thống khác |
| `VaultResponse` / `VaultResponseSupport<T>` | `data`, metadata phản hồi, có thể có chi tiết engine | `toString()`/serialize nguyên object có thể bao gồm `data` |
| `Versioned<T>` | `data` có kiểu và phiên bản KV v2 | In nguyên `Versioned<T>` có thể làm lộ `T` |
| Vault auth | `client_token`, auth metadata, thông tin phiên làm việc | Lộ token truy cập Vault hoặc ngữ cảnh danh tính |
| Dynamic database credentials | Username/password và lease metadata | Lộ credential đang có hiệu lực |
| Transit encrypt/decrypt | Plaintext dạng Base64, ciphertext, context | Lộ plaintext hoặc dữ liệu mật mã/ngữ cảnh |
| PKI issue | `certificate`, `private_key`, `ca_chain` | Có thể lộ private key và cấu trúc danh tính nội bộ |
| Exception từ client HTTP/JSON | Path, header, trích đoạn response hoặc tên trường | Có thể lộ dữ liệu qua message/stack trace tùy client |

### 2.1. Một số giá trị không phải secret vẫn cần thận trọng

Địa chỉ host nội bộ, path Vault, tên role, request ID, serial chứng chỉ hay metadata phiên bản không nhất thiết là credential. Nhưng chúng có thể tiết lộ kiến trúc, tên tenant hoặc thông tin vận hành. Chỉ đưa ra log những trường **đã được phân loại** là phù hợp với môi trường quan sát đó.

### 2.2. Base64 và ciphertext không phải “vé miễn kiểm duyệt”

Base64 là mã hóa biểu diễn thuận nghịch, **không phải mã hóa bảo mật**. Trong Transit, request `plaintext` thường chứa Base64 của bytes và response decrypt `plaintext` cũng là Base64; ai đọc được đều có thể decode. Ciphertext Transit có thể không tiết lộ plaintext khi mật mã được dùng đúng, nhưng vẫn chứa metadata phiên bản khóa hoặc tạo ra những rủi ro vận hành/phân tích tần suất. Vì vậy không tự động log ciphertext, context hay toàn bộ response chỉ vì nó không đọc được thành văn bản.

## 3. Những cách làm lộ DTO rất phổ biến

### 3.1. `toString()` và tham số log của SLF4J

Ví dụ một DTO:

```java
public record GatewaySecret(
        String apiKey,
        String endpoint,
        Integer timeoutSeconds) {
}
```

Java tự tạo `toString()` cho `record` từ các thành phần. Với một record chứa `apiKey`, đây là hành vi **không phù hợp để ghi log**:

```java
GatewaySecret secret = loadFromVault();

// Không an toàn:
log.info("Gateway secret: {}", secret);
log.debug("Gateway secret = " + secret);
System.out.println(secret);
```

Tương tự, một class dùng Lombok `@Data` thường được sinh `toString()` chứa các property, trừ khi có cấu hình/annotation khác.

**Parameterized logging không phải cơ chế che secrets.** Trong lời gọi `log.info("{}", secret)`, framework vẫn có thể gọi `toString()` để định dạng object khi ghi log. Việc dùng `{}` thay vì nối chuỗi giúp tránh một số chi phí định dạng khi log level tắt, **không làm cho dữ liệu trở nên an toàn**.

### 3.2. Log cả `Map` hoặc phản hồi Vault

```java
VaultResponse response = kv.get("payments/gateway");

// Không an toàn:
log.debug("Vault response={}", response);
log.debug("Vault data={}", response.getData());
```

`Map.toString()` in key và value; nếu có `apiKey` hoặc password, dữ liệu xuất hiện ngay trong log. Dù một phiên bản cụ thể của `VaultResponse.toString()` có thể che một số trường, **không nên dựa vào cách triển khai nội bộ hoặc phiên bản thư viện để bảo vệ** khi in nguyên response.

Với KV v2, response raw còn có metadata và object lồng nhau `data.data`. Điều đó không làm nội dung bên trong trở thành dữ liệu được phép log.

### 3.3. Ghi object qua JSON serializer

```java
// Không an toàn khi secret chứa giá trị nhạy cảm:
log.info("Mapped DTO={}", objectMapper.writeValueAsString(secret));
```

Ở đây `objectMapper` có thể xuất tất cả property được phép serialize. Ghi đè `toString()` **không** ngăn Jackson gọi getter/record component khi serialize JSON.

Một số endpoint trả lỗi debug bằng object:

```java
// Không an toàn:
return Map.of(
        "error", "Vault request failed",
        "secret", secret);
```

Dù không có lời gọi logger, REST controller vẫn có thể serialize object trả về và đưa bí mật ra HTTP response. Cần kiểm soát đồng thời **log, exception và mọi đường serialize đối tượng**.

### 3.4. Exception chứa payload

```java
// Không an toàn:
throw new IllegalStateException(
        "Invalid secret: " + secret);

// Không an toàn nếu value nhạy cảm:
throw new IllegalArgumentException(
        "Invalid apiKey=" + secret.apiKey());
```

Một exception có thể đi qua middleware, log aggregator, tracing agent hoặc HTTP error handler. Nếu message chứa secret, dữ liệu đã thoát khỏi ranh giới tích hợp, kể cả khi người viết không trực tiếp gọi `log.error(...)`.

### 3.5. Exception có `cause` cũng có thể làm lộ dữ liệu

```java
try {
    return parseSecret(raw);
} catch (RuntimeException ex) {
    // Cần cân nhắc:
    throw new IllegalStateException("Invalid Vault payload", ex);
}
```

Message bên ngoài đã trung tính, nhưng nếu logger/framework in **toàn bộ stack trace và cause chain**, exception gốc vẫn có thể chứa tên field, path, header hoặc một phần giá trị sai. Không phải mọi exception của Spring Vault/Jackson đều làm lộ secret; vấn đề là **không được mặc định toàn bộ cause chain an toàn để công khai**.

Có thể giữ cause trong ranh giới xử lý nội bộ được kiểm soát để phục vụ chẩn đoán, nhưng không đưa nó vào client response/log tập trung khi chưa đánh giá nội dung. Đừng xóa mọi dấu vết lỗi một cách mù quáng; hãy lưu **mã lỗi và ngữ cảnh an toàn** để vẫn phân biệt lỗi xác thực, policy, schema và mạng.

## 4. Thiết kế DTO có hành vi hiển thị an toàn

Đối với kiểu chứa secrets, **an toàn mặc định** nên có nghĩa: ngay cả khi lập trình viên vô tình gọi `toString()`, chuỗi kết quả không chứa secret.

### 4.1. Record với `toString()` được ghi đè

```java
import java.net.URI;
import java.time.Duration;

public record GatewaySettings(
        String apiKey,
        URI endpoint,
        Duration timeout) {

    @Override
    public String toString() {
        return "GatewaySettings[redacted]";
    }
}
```

`GatewaySettings.toString()` không chứa bất kỳ trường dữ liệu nào, kể cả `endpoint` có thể chứa tên host nhạy cảm. Hành vi này khác với `record` tự sinh `toString()`.

**Giới hạn:** accessor `apiKey()` vẫn trả về giá trị để client được phép sử dụng. Jackson, reflection, debugger, heap dump hoặc một serializer khác có thể truy cập giá trị mà không gọi `toString()`. Vì vậy ghi đè `toString()` là **một lớp phòng vệ**, không phải cơ chế cô lập bí mật hoàn chỉnh.

### 4.2. DTO JavaBean với `toString()` tối giản

```java
public final class GatewaySecretDto {

    private String apiKey;
    private String endpoint;
    private Integer timeoutSeconds;

    public GatewaySecretDto() {
    }

    public String getApiKey() {
        return apiKey;
    }

    public void setApiKey(String apiKey) {
        this.apiKey = apiKey;
    }

    public String getEndpoint() {
        return endpoint;
    }

    public void setEndpoint(String endpoint) {
        this.endpoint = endpoint;
    }

    public Integer getTimeoutSeconds() {
        return timeoutSeconds;
    }

    public void setTimeoutSeconds(Integer timeoutSeconds) {
        this.timeoutSeconds = timeoutSeconds;
    }

    @Override
    public String toString() {
        return "GatewaySecretDto[redacted]";
    }
}
```

Không cần dùng `@Data` chỉ để có getter/setter nếu hệ thống chưa có chính sách che field. Nếu dự án sử dụng Lombok, có thể đánh dấu `@ToString.Exclude` trên trường nhạy cảm hoặc ưu tiên `@ToString(onlyExplicitlyIncluded = true)` và chỉ chọn các trường đã được duyệt. **Không** quên rằng các object lồng nhau, map hoặc danh sách có thể vẫn chứa secrets.

Ví dụ với Lombok khi thư viện đã được dự án cấu hình:

```java
import lombok.Getter;
import lombok.Setter;
import lombok.ToString;

@Getter
@Setter
@ToString(onlyExplicitlyIncluded = true)
public class LegacyCredentialsDto {

    private String username;
    private String password;
    private String token;

    // Không có @ToString.Include => không in bất kỳ field nào.
}
```

Lombok chỉ điều khiển phương thức `toString()` được sinh. **Không** mặc định điều đó thay đổi cách Jackson, một error renderer hoặc một APM agent serialize object.

### 4.3. Không để secret vào `equals()`/`hashCode()` và collection một cách tùy tiện

Java record tự sinh `equals()` và `hashCode()` dựa trên các component, kể cả secret. Điều này có thể tạo rủi ro khác như giữ secret trong map key, giữ tham chiếu dài hạn hoặc để giá trị đi qua công cụ quan sát collection. Đây không đồng nghĩa bản thân `hashCode()` luôn làm lộ plaintext; vấn đề là **đừng coi record chứa credential như một object giá trị thông thường được tự do in, cache, serialize, so sánh hoặc đưa vào key metric**.

Khi thiết kế cấu trúc dữ liệu, cân nhắc tách **định danh cấu hình** với **vật liệu secret**. Thành phần cần so sánh “đã nạp bản mới chưa” nên ưu tiên version/metadata chọn lọc thay vì so sánh hoặc in credential.

## 5. Có nên dùng annotation Jackson để giấu trường?

Khi DTO vừa dùng để **đọc JSON từ Vault** vừa có thể bị serialize, annotation Jackson có thể giảm một số đường lộ dữ liệu. Nhưng phải hiểu tác động đến hướng đọc và ghi:

| Cách làm | Tác dụng chính | Cảnh báo |
|---|---|---|
| `@JsonIgnore` | Bỏ qua property trong một số đường serialize/deserialize | Có thể khiến field không được đọc vào DTO từ Vault |
| `@JsonProperty(access = WRITE_ONLY)` | Cho phép deserialize nhưng không serialize property qua Jackson hỗ trợ | Không thích hợp nếu cùng DTO cần serialize secret để **ghi** vào Vault |
| `@JsonIgnoreProperties` | Loại trừ nhóm property theo cấu hình | Phải kiểm tra chiều đọc/ghi và getter/setter |
| JSON view/mixin/serializer riêng | Quy định định dạng theo ngữ cảnh | Dễ cấu hình sai nếu nhiều ObjectMapper/client |
| DTO công khai riêng | Chỉ chứa field được phép xuất ra ngoài | Ranh giới rõ ràng và thường dễ kiểm tra nhất |

### 5.1. Ví dụ `WRITE_ONLY` cho DTO chỉ nhận giá trị từ Vault

Với Jackson 2.x:

```java
import com.fasterxml.jackson.annotation.JsonProperty;

public class InboundCredentialDto {

    private String username;
    private String apiKey;

    public InboundCredentialDto() {
    }

    public String getUsername() {
        return username;
    }

    public void setUsername(String username) {
        this.username = username;
    }

    @JsonProperty(
            value = "api_key",
            access = JsonProperty.Access.WRITE_ONLY)
    public String getApiKey() {
        return apiKey;
    }

    public void setApiKey(String apiKey) {
        this.apiKey = apiKey;
    }

    @Override
    public String toString() {
        return "InboundCredentialDto[redacted]";
    }
}
```

Khi một mapper Jackson có nhận diện annotation, `WRITE_ONLY` theo ngữ nghĩa Jackson nghĩa là property có thể được **ghi vào object Java trong quá trình deserialization**, nhưng bị loại khi **serialize object Java thành JSON**. Trong Java, getter vẫn có thể được gọi bởi mã ứng dụng.

Đây không phải cơ chế bảo mật cho mọi serializer hay framework: Gson, một logger dùng reflection hoặc Spring MVC với mapper/annotation khác có thể hành xử khác. Quan trọng hơn, nếu đối tượng cũng được dùng để **ghi secret trở lại Vault**, `WRITE_ONLY` có thể làm cho `api_key` bị bỏ qua khi serialize, gây mất dữ liệu. Do đó:

- Dùng DTO inbound chuyên biệt nếu cần `WRITE_ONLY`.
- Dùng DTO outbound riêng chứa những field được phép xuất, **không** tái sử dụng DTO chứa secret làm REST response.
- Kiểm thử đúng `ObjectMapper`/HTTP converter được Spring Vault sử dụng, thay vì cho rằng mapper MVC luôn là cùng một instance.

### 5.2. DTO trả ra API công khai phải khác DTO đọc secrets

Không nên trả `GatewaySecretDto` nguyên vẹn từ REST controller. Thay vào đó, xác định response riêng:

```java
public record GatewayStatusResponse(
        boolean configured,
        String state) {
}

public final class GatewayStatusMapper {

    private GatewayStatusMapper() {
    }

    public static GatewayStatusResponse toPublicStatus(
            GatewaySecretDto secret) {

        boolean configured = secret != null
                && secret.getApiKey() != null
                && !secret.getApiKey().isBlank();

        return new GatewayStatusResponse(
                configured,
                configured ? "READY" : "UNAVAILABLE");
    }
}
```

Hai kiểu `public` trong ví dụ được đặt trong hai file Java tương ứng (`GatewayStatusResponse.java` và `GatewayStatusMapper.java`) khi đưa vào dự án. `GatewayStatusResponse` không có field `apiKey`, `endpoint` hay thông tin nhạy cảm. Trạng thái `READY` ở đây chỉ xác nhận DTO có API key theo ví dụ tối thiểu, **không** bảo đảm token còn hiệu lực hoặc endpoint đích đang hoạt động. Trong sản phẩm thật cần validator đầy đủ và xác định rõ ý nghĩa của trạng thái.

## 6. Đọc KV v2 và chỉ log dữ liệu quan sát có chọn lọc

Đoạn code minh họa sử dụng `VaultKeyValueOperations` cho KV v2 mount `secret`. Mã không log DTO hoặc `VaultResponseSupport<T>`.

```java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.vault.core.VaultKeyValueOperations;
import org.springframework.vault.core.VaultOperations;
import org.springframework.vault.core.VaultKeyValueOperationsSupport.KeyValueBackend;
import org.springframework.vault.support.VaultResponseSupport;

public final class GatewaySecretLoader {

    private static final Logger log =
            LoggerFactory.getLogger(GatewaySecretLoader.class);

    private final VaultKeyValueOperations kv;

    public GatewaySecretLoader(VaultOperations operations) {
        this.kv = operations.opsForKeyValue(
                "secret", KeyValueBackend.KV_2);
    }

    public GatewaySecretDto load() {
        long started = System.nanoTime();

        try {
            VaultResponseSupport<GatewaySecretDto> response =
                    kv.get("payments/gateway", GatewaySecretDto.class);

            if (response == null || response.getData() == null) {
                log.warn("vault_operation=kv_read outcome=missing resource=gateway");
                throw new SecretConfigurationException(
                        SecretFailureCode.MISSING_SECRET);
            }

            GatewaySecretDto secret = response.getRequiredData();
            validate(secret);

            log.info("vault_operation=kv_read outcome=success resource=gateway");
            return secret;
        } finally {
            long durationMs =
                    (System.nanoTime() - started) / 1_000_000L;
            log.debug(
                    "vault_operation=kv_read resource=gateway duration_ms={}",
                    durationMs);
        }
    }

    private static void validate(GatewaySecretDto secret) {
        if (secret.getApiKey() == null
                || secret.getApiKey().isBlank()
                || secret.getEndpoint() == null
                || secret.getEndpoint().isBlank()
                || secret.getTimeoutSeconds() == null
                || secret.getTimeoutSeconds() < 1
                || secret.getTimeoutSeconds() > 120) {
            throw new SecretConfigurationException(
                    SecretFailureCode.INVALID_SECRET);
        }
    }
}
```

Ví dụ giả định có `SecretFailureCode` và `SecretConfigurationException`, được định nghĩa ngay sau đây. Log sử dụng nhãn `resource=gateway` **cố định do ứng dụng định nghĩa**, không lấy tên path động hoặc giá trị credential từ dữ liệu đầu vào. Một ứng dụng thực tế nên đo trạng thái và thời lượng qua công cụ observability phù hợp; đây là cú pháp log dễ đọc để minh họa các trường an toàn.

### 6.1. Mã lỗi ổn định thay cho nội dung secret

```java
public enum SecretFailureCode {
    MISSING_SECRET,
    INVALID_SECRET,
    VAULT_UNAVAILABLE
}
```

```java
public final class SecretConfigurationException
        extends RuntimeException {

    private final SecretFailureCode code;

    public SecretConfigurationException(SecretFailureCode code) {
        super(code.name());
        this.code = code;
    }

    public SecretFailureCode code() {
        return code;
    }
}
```

`SecretConfigurationException` chỉ chứa **mã lỗi không có payload**. Để phân loại thêm lỗi policy (403), authentication, TLS, HTTP hoặc deserialize, thiết kế lớp chuyển lỗi ở ranh giới tích hợp dựa trên **loại/status lỗi**, không ghép raw response vào message.

Một điểm quan trọng: ví dụ loader trên chưa bắt mọi exception phát sinh từ `kv.get(...)`. Các lỗi I/O, Vault policy, xác thực và deserialize có thể đi lên tầng gọi. Trong hệ thống production, cần có **exception boundary** để phân loại và xử lý chúng trước khi log/đưa ra client; không giả định chỉ cần log thành công và thiếu data là đủ bảo vệ toàn bộ đường lỗi.

### 6.2. Không dùng path hoặc metadata một cách tùy tiện

Trong ví dụ, `"payments/gateway"` là path cố định do mã nguồn quyết định. Nếu path chứa tenant ID hay thông tin động của người dùng, **không** đưa nguyên path vào log, exception hoặc metric label. Tạo nhãn ổn định như `resource=gateway` và chỉ ghi metadata đã được đánh giá.

Nếu dùng `Versioned<T>` để theo dõi storage version KV v2, có thể đo số phiên bản đã nạp khi mục đích vận hành thực sự yêu cầu, nhưng không log `Versioned<T>` nguyên object. Storage version khác schema version, token lifetime và lease ID; không suy rằng “version tăng” đồng nghĩa credential đã hết hạn hoặc toàn bộ client đã refresh.

## 7. Xử lý exception tại ranh giới API

Trong ứng dụng web, lỗi nội bộ khi đọc Vault nên được chuyển thành **phản hồi công khai được giới hạn thông tin**. Ví dụ với Spring Web:

```java
public record PublicError(String code, String message) {
}
```

```java
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class PublicExceptionHandler {

    @ExceptionHandler(SecretConfigurationException.class)
    public ResponseEntity<PublicError> secretUnavailable(
            SecretConfigurationException ex) {

        // Không đưa DTO, secret path, stack trace hoặc cause ra client.
        return ResponseEntity
                .status(HttpStatus.SERVICE_UNAVAILABLE)
                .body(new PublicError(
                        "SERVICE_CONFIGURATION_UNAVAILABLE",
                        "Dịch vụ tạm thời chưa sẵn sàng"));
    }
}
```

Đoạn này chỉ xử lý `SecretConfigurationException` do ứng dụng định nghĩa. Các exception khác từ client Vault, converter hoặc hệ thống cần handler/đường xử lý tương ứng; nếu không, framework có thể tạo phản hồi/lỗi log ngoài ý muốn. Không vì thế mà dùng một handler bắt tất cả rồi che sự cố nghiêm trọng; **phân loại nguyên nhân** cho vận hành và **giới hạn nội dung trả ra** cho client là hai mục tiêu cùng tồn tại.

### 7.1. Mẫu xử lý lỗi có phân loại

| Nhóm lỗi | Điều vận hành cần biết | Điều không nên log hoặc trả về |
|---|---|---|
| Secret không tồn tại | `MISSING_SECRET`, tên adapter cố định | Toàn bộ path động, payload |
| Secret thiếu trường hoặc sai kiểu | `INVALID_SECRET`, field name an toàn khi phù hợp | Giá trị sai, object DTO/Map, JSON raw |
| Workload authentication lỗi | Nhóm `AUTHENTICATION_FAILED`, số lần lỗi | Vault token, client secret, request auth body |
| Vault policy từ chối | Nhóm `ACCESS_DENIED`, vai trò/mount đã được kiểm duyệt nếu cần | Credential và thông tin tenant/path không được phép |
| Lỗi kết nối/TLS | `VAULT_UNAVAILABLE`, latency, số lần retry | Header, body, thông tin xác thực |
| Transit decrypt thất bại | `TRANSIT_OPERATION_FAILED`, tên thao tác | Base64 plaintext, ciphertext hoặc context nhạy cảm |
| PKI issue lỗi | `PKI_ISSUANCE_FAILED`, nhóm lỗi | `private_key`, response issuance nguyên vẹn |

**Không chỉ dựa vào `ex.getMessage()` để phân loại**: message là văn bản dành cho mô tả và có thể thay đổi theo phiên bản client. Nên dựa vào loại exception, HTTP status/chi tiết lỗi có cấu trúc khi có thể, rồi chuyển sang enum hoặc mã lỗi nội bộ đã chuẩn hóa.

### 7.2. Giữ thông tin chẩn đoán mà không nhân bản bí mật

Không phải lúc nào cũng nên bỏ hoàn toàn cause; điều đó có thể làm khó điều tra outage. Cách thực tế là có hai kênh:

1. **Kênh công khai/thu thập log thông thường:** mã lỗi, loại thao tác, thời lượng, kết quả, định danh theo dõi đã kiểm duyệt.
2. **Kênh chẩn đoán quyền hạn cao:** thông tin exception đã được đánh giá, kiểm soát truy cập và thời gian lưu; không tự động cho phép log toàn bộ request/response hay credential.

Nếu không thể bảo đảm nội dung của exception gốc an toàn, **không** gọi `log.error("...", ex)` ở sink chung. Một chính sách xử lý lỗi không chỉ là câu lệnh Java mà còn là cấu hình của web framework, log appender, APM agent và công cụ thu thập.

## 8. Các đường rò rỉ ngoài `toString()` cần kiểm tra

### 8.1. HTTP wire logging

Một HTTP client gửi:

```text
GET /v1/secret/data/payments/gateway
X-Vault-Token: <vault-auth-token>
```

hoặc POST Transit encrypt có body chứa `plaintext` Base64. Nếu bật **wire logging** hoặc logging toàn bộ request/response, hệ thống có thể ghi:

- Header `X-Vault-Token` và các thông tin auth khác.
- Body KV chứa API key/password.
- Base64 plaintext trước Transit encryption hoặc sau Transit decryption.
- PKI private key khi issuance trả private key.
- Path/role/namespace có ngữ cảnh nội bộ.

Không mặc định rằng log cấp debug của Spring, RestTemplate, RestClient, Reactor Netty hoặc proxy chỉ chứa metadata. Hãy kiểm tra chính xác cấu hình logger, interceptor, HTTP request/response logging và redaction của thư viện **đang được sử dụng**.

**Cách tiếp cận an toàn:** tắt body/header logging cho client Vault theo mặc định; dùng event mức nghiệp vụ đã giới hạn như `kv_read.success` hoặc `transit_encrypt.failed`. Nếu buộc phải theo dõi một phần header, cấu hình danh sách cho phép (allowlist) thay vì ghi tất cả rồi cố che bằng regex.

### 8.2. APM, distributed tracing và baggage

Một tracing agent có thể ghi URL, query parameters, exception, header, body hoặc thuộc tính tùy chỉnh do lập trình viên gắn. Không đưa token, path động có tenant ID hoặc secret vào `Span.setAttribute(...)`, MDC hay baggage. Baggage có thể được truyền qua nhiều dịch vụ và lan rộng hơn một dòng log tại chỗ.

Ví dụ event cấu trúc **được phép**:

```text
span.name = "vault.kv.read"
attribute["vault.operation"] = "kv_read"
attribute["vault.resource"]  = "gateway"
attribute["vault.outcome"]   = "success"
```

Tránh:

```text
attribute["vault.secret"] = "<gia-tri-bi-mat>"
attribute["http.request.header.x-vault-token"] = "<vault-token>"
attribute["vault.raw_response"] = "{...}"
```

Các dòng trên chỉ minh họa thuộc tính nguy hiểm, không phải gợi ý cấu hình agent thực tế.

### 8.3. Metric labels và cardinality

Không dùng `apiKey`, email, user ID, path secret động hoặc request ID làm metric label. Điều này vừa có rủi ro bảo mật, vừa tạo số lượng tổ hợp nhãn rất lớn, gây tăng chi phí và giảm khả năng quan sát. Ví dụ một metric hợp lý:

```text
vault_client_operations_total{
  operation="kv_read",
  resource="gateway",
  outcome="success"
}
```

Nhãn `resource` trong ví dụ là **tập hữu hạn do mã ứng dụng định nghĩa**, không lấy từ nội dung secret. Với Micrometer hoặc hệ thống tương đương, xem xét cả histogram/timer, exemplars và tag tự động của client HTTP.

### 8.4. Actuator, cấu hình và diagnostic endpoints

Spring Boot Actuator hoặc các endpoint hỗ trợ có thể hiển thị thông tin cấu hình, bean, exception hay môi trường. Cần áp dụng kiểm soát truy cập, cấu hình ẩn/che giá trị nhạy cảm và hạn chế những endpoint không cần thiết. Cơ chế hiển thị configuration properties **không thay thế** việc giữ DTO chứa Vault secret khỏi REST serialization và log.

### 8.5. Test failure, assertion và snapshot

Ngay cả môi trường test/CI cũng có thể làm lộ secret nếu dùng dữ liệu thật trong:

```java
// Không sử dụng với secret thật:
// assertEquals(expectedSecret, actualSecret);
// assertThat(dto).isEqualTo(expectedDto);
// System.out.println(vaultResponse);
```

Khi assertion thất bại, framework có thể in cả giá trị kỳ vọng và thực tế. Chỉ dùng fixture giả và kiểm tra các property không nhạy cảm hoặc hành vi công khai; tránh snapshot toàn bộ phản hồi Vault.

## 9. Một lớp tóm tắt log được thiết kế riêng

Thay vì đưa cả DTO vào logger, hãy định nghĩa **sự kiện an toàn có chủ đích**. Ví dụ:

```java
public enum SecretOperation {
    KV_READ,
    TRANSIT_ENCRYPT,
    TRANSIT_DECRYPT,
    PKI_ISSUE
}
```

```java
public enum OperationOutcome {
    SUCCESS,
    MISSING,
    INVALID_DATA,
    ACCESS_DENIED,
    FAILED
}
```

```java
public record SafeSecretLogEvent(
        SecretOperation operation,
        OperationOutcome outcome,
        long elapsedMillis) {

    public SafeSecretLogEvent {
        if (operation == null || outcome == null) {
            throw new IllegalArgumentException(
                    "Thiếu operation/outcome");
        }
        if (elapsedMillis < 0) {
            throw new IllegalArgumentException(
                    "elapsedMillis không thể âm");
        }
    }
}
```

Vì record này **không có field secret, path hay exception**, `toString()` tự sinh của nó không thể in secret value. Cách tiếp cận **allowlist trường** thường an toàn hơn “serialize DTO nguyên bản rồi dùng regex để mask”.

Ví dụ:

```java
SafeSecretLogEvent event = new SafeSecretLogEvent(
        SecretOperation.KV_READ,
        OperationOutcome.SUCCESS,
        12);

log.info("{}", event);
```

Việc định nghĩa kiểu log riêng còn giúp code review: nếu một lập trình viên muốn thêm `String token` vào `SafeSecretLogEvent`, thay đổi đó sẽ hiển thị rõ ở schema event và có thể bị từ chối trước khi triển khai.

### 9.1. Vì sao “masking regex” không nên là lớp bảo vệ duy nhất?

Giả sử log formatter chỉ tìm các tên trường `password` hoặc `token` để thay bằng `***`. DTO vẫn có thể chứa:

- `apiKey`, `clientSecret`, `privateKey`, `authorization` hoặc tên trường legacy không khớp regex.
- Nested `Map` với key do bên ngoài tạo ra.
- Base64 plaintext hoặc PEM nhiều dòng.
- Chuỗi secret đi qua exception dưới hình thức không có tên field.

Regex masking tại appender/collector có thể là biện pháp phòng vệ bổ sung, nhưng không đủ để chứng minh “không có secret nào được log”. Tốt nhất **không đưa secret vào đối tượng log ngay từ đầu**.

## 10. Đặc thù Spring Vault: KV, Versioned, Transit, PKI và lease

### 10.1. KV và DTO có kiểu

`VaultResponseSupport<GatewaySecretDto>` cho phép ánh xạ dữ liệu thành DTO. Adapter có thể validate field bắt buộc mà **chỉ báo tên trường**:

```java
if (dto.getApiKey() == null || dto.getApiKey().isBlank()) {
    throw new SecretConfigurationException(
            SecretFailureCode.INVALID_SECRET);
}
```

Đừng nối `dto.getApiKey()` vào exception để “dễ debug”. Nếu JSON thiếu/đổi kiểu, cần kiểm tra naming convention, converter và schema bằng dữ liệu giả hoặc metadata được phép, không bằng cách bật log raw response trong production.

### 10.2. `Versioned<T>` và metadata KV v2

Với `VaultVersionedKeyValueOperations`, ứng dụng có thể nhận `Versioned<T>` chứa phần `data` và thông tin phiên bản. Có thể tách:

```text
Versioned<GatewaySecretDto>
  ├── getData()       → DTO chứa secret, KHÔNG LOG
  ├── getVersion()    → version lưu trữ, cân nhắc log theo policy
  └── getMetadata()   → metadata chọn lọc, cần phân loại trước khi log
```

Không log nguyên `Versioned<T>` để lấy version. Hãy truy xuất đúng trường version cần thiết, đánh giá xem version có cần thiết trong log/metric hay không, và giữ metadata ngoài DTO nghiệp vụ.

### 10.3. Dynamic secrets và token/lease

Một phản hồi cấp dynamic database credentials có thể chứa username, password cùng thông tin lease. Token/lease ID là định danh quản trị phiên hoặc truy cập, không phải dữ liệu nên xuất hiện trong log thường. Nếu cần quan sát renewal/revocation, theo dõi loại thao tác, trạng thái, độ trễ và nhóm lỗi thay vì in credential hay lease ID nguyên dạng.

Không suy từ việc một DTO có field `expiresAt` hay `leaseDuration` rằng Spring Vault sẽ tự renew/revoke. Cần cơ chế vòng đời token/lease tương ứng. Logging an toàn và lifecycle management là hai trách nhiệm riêng.

### 10.4. Transit encrypt/decrypt

Trong Vault Transit, `plaintext` ở request encrypt hoặc response decrypt thường là Base64 của bytes ban đầu. **Base64 có thể decode dễ dàng**, nên phải coi nó nhạy cảm tương đương plaintext. Không log:

```java
// Không an toàn:
// log.debug("plaintextBase64={}", plaintextBase64);
// log.debug("decrypt response={}", response.getData());
```

Ciphertext `vault:vN:...` cũng không nên được in mặc định. Nếu cần theo dõi, log `operation=transit_decrypt`, `outcome=failed` và một mã lỗi ổn định. Nếu key sử dụng `context`, cần bảo vệ cả context có thể chứa thông tin tenant hoặc dữ liệu phân loại nhạy cảm.

### 10.5. PKI issue và private key

Phản hồi cấp chứng chỉ có thể chứa `certificate`, `issuing_ca`, `serial_number`, `private_key` và `ca_chain`. Trong đó `private_key` là dữ liệu đặc biệt nhạy cảm. Không in toàn bộ `VaultResponse` hoặc DTO issuance.

Để giám sát hạn chứng chỉ, có thể parse certificate bằng `CertificateFactory` và sử dụng trường hạn `notAfter` đã được cho phép quan sát; không cần log private key hoặc PEM nguyên bản. Chỉ công bố thông tin issuer/subject/serial nếu chính sách bảo mật cho phép.

## 11. Kiểm thử ngăn lộ secret qua biểu diễn và lỗi

### 11.1. Unit test cho `toString()`

Đặt một chuỗi **giả** dễ nhận diện trong DTO và xác nhận biểu diễn log không chứa nó:

```java
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

import org.junit.jupiter.api.Test;

class GatewaySecretDtoSafetyTest {

    private static final String FAKE_SECRET =
            "FAKE_SECRET_DO_NOT_LOG_12345";

    @Test
    void dtoToStringDoesNotExposeSecret() {
        GatewaySecretDto dto = new GatewaySecretDto();
        dto.setApiKey(FAKE_SECRET);
        dto.setEndpoint("https://payments.internal.example");
        dto.setTimeoutSeconds(15);

        String text = dto.toString();

        assertFalse(text.contains(FAKE_SECRET));
        assertTrue(text.contains("redacted"));
    }

    @Test
    void publicResponseDoesNotHaveSecretField() {
        GatewaySecretDto dto = new GatewaySecretDto();
        dto.setApiKey(FAKE_SECRET);

        GatewayStatusResponse status =
                GatewayStatusMapper.toPublicStatus(dto);

        assertFalse(status.toString().contains(FAKE_SECRET));
    }
}
```

Trong test này, `GatewayStatusMapper.toPublicStatus(dto)` là helper ở mục 5.2. Đây là cách xác nhận luồng xuất ra công khai **không chứa vật liệu bí mật**, không phải lý do để dùng credential sản xuất trong fixture.

### 11.2. Kiểm thử serialized JSON của DTO công khai

`toString()` an toàn chưa đủ; cần chứng minh JSON response công khai không có secret:

```java
import static org.junit.jupiter.api.Assertions.assertFalse;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;

class PublicStatusJsonTest {

    @Test
    void publicJsonDoesNotContainSecret() throws Exception {
        String fakeSecret = "FAKE_SECRET_DO_NOT_LOG_12345";

        GatewaySecretDto dto = new GatewaySecretDto();
        dto.setApiKey(fakeSecret);

        GatewayStatusResponse publicDto =
                GatewayStatusMapper.toPublicStatus(dto);
        String json = new ObjectMapper()
                .writeValueAsString(publicDto);

        assertFalse(json.contains(fakeSecret));
        assertFalse(json.contains("apiKey"));
        assertFalse(json.contains("api_key"));
    }
}
```

Kịch bản này chỉ kiểm tra **một mapper và một DTO cụ thể**. Trong ứng dụng web, hãy kiểm thử HTTP serialization đúng converter và configuration thực tế, đồng thời xác nhận response không bao gồm DTO secrets qua field lồng nhau.

### 11.3. Kiểm thử exception và mã lỗi

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;

import org.junit.jupiter.api.Test;

class SecretConfigurationErrorTest {

    @Test
    void exceptionMessageIsStableAndDoesNotRevealPayload() {
        String fakeSecret = "FAKE_SECRET_DO_NOT_LOG_12345";

        SecretConfigurationException ex =
                new SecretConfigurationException(
                        SecretFailureCode.INVALID_SECRET);

        assertEquals(SecretFailureCode.INVALID_SECRET, ex.code());
        assertFalse(ex.getMessage().contains(fakeSecret));
    }
}
```

Đây là test thông điệp exception do ứng dụng tạo. Để kiểm tra cả **exception cause của Spring Vault/client HTTP**, cần thêm bài test tích hợp hoặc giả lập lỗi cụ thể, đưa kết quả qua exception boundary và quan sát đúng nơi hệ thống ghi log/HTTP response.

### 11.4. Capture log thay vì chỉ đọc code

Trong dự án dùng SLF4J + Logback, có thể dùng appender kiểm thử như `ListAppender<ILoggingEvent>` để thu log của một logger, sau đó xác nhận không chứa chuỗi sentinel:

```java
import static org.junit.jupiter.api.Assertions.assertFalse;

import ch.qos.logback.classic.Level;
import ch.qos.logback.classic.Logger;
import ch.qos.logback.classic.spi.ILoggingEvent;
import ch.qos.logback.core.read.ListAppender;
import org.junit.jupiter.api.Test;
import org.slf4j.LoggerFactory;

class SecretLoggingTest {

    @Test
    void doesNotEmitSecretValue() {
        Logger logger = (Logger) LoggerFactory
                .getLogger("vault.security.example");
        Level originalLevel = logger.getLevel();

        ListAppender<ILoggingEvent> appender = new ListAppender<>();
        appender.start();
        logger.addAppender(appender);
        logger.setLevel(Level.INFO);

        String fakeSecret = "FAKE_SECRET_DO_NOT_LOG_12345";
        try {
            GatewaySecretDto dto = new GatewaySecretDto();
            dto.setApiKey(fakeSecret);

            GatewayStatusResponse safeStatus =
                    GatewayStatusMapper.toPublicStatus(dto);
            logger.info(
                    "operation=kv_read configured={}",
                    safeStatus.configured());

            String recorded = appender.list.stream()
                    .map(ILoggingEvent::getFormattedMessage)
                    .reduce("", (a, b) -> a + "\n" + b);
            assertFalse(recorded.contains(fakeSecret));
        } finally {
            logger.detachAppender(appender);
            logger.setLevel(originalLevel);
            appender.stop();
        }
    }
}
```

Đoạn test này cần `logback-classic` trên test runtime và chỉ kiểm tra logger được cấu hình trong test. Nó minh họa việc ghi **trạng thái đã được chọn lọc** thay vì DTO chứa secret; trong ứng dụng thực tế, hãy gọi đường mã xử lý thật giữa các bước attach và assert. Với nhiều appender/agent, hãy kiểm thử ở từng sink quan trọng hoặc có kiểm tra cấu hình tập trung. Không được cho rằng một test đơn giản chứng minh mọi framework/agent đều đã được cấu hình an toàn.

### 11.5. Ma trận kiểm thử cần có

| Kịch bản | Điều cần xác nhận |
|---|---|
| DTO chứa `apiKey`, password | `toString()` không lộ giá trị |
| Lombok/record được thêm mới | Chính sách sinh `toString()` vẫn an toàn |
| Jackson serialize đối tượng trả ra API | Response DTO công khai không có secrets |
| Mất field khi đọc KV | Thông báo lỗi chỉ có mã/trường, không có payload |
| Mapping JSON sai kiểu | Exception/cause không bị log nguyên vẹn ngoài chính sách |
| Vault trả 403 hoặc token hết hạn | Log mã lỗi và trạng thái, không có token/header |
| HTTP wire logging bật nhầm | Kiểm tra config hoặc test phát hiện body/header bị ghi |
| Transit encrypt/decrypt | Không log Base64 plaintext, ciphertext, context |
| PKI issue | Không log PEM private key hoặc phản hồi nguyên bản |
| Metric/trace | Không có secret trong tag, MDC, baggage, span attributes |
| CI assertion/snapshot thất bại | Không in secret thật; dùng fixture giả |

## 12. Checklist review trước khi triển khai

Khi review một thay đổi liên quan Spring Vault, hãy tự kiểm tra:

1. **Đường dữ liệu:** secret đi từ Vault tới DTO nào, service nào và logger/serializer nào có thể nhìn thấy?
2. **DTO:** có `record.toString()`, Lombok `@Data`, getter public hoặc nested object chứa secrets không?
3. **Thông báo lỗi:** có chuỗi ghép với `dto`, `response`, `value`, body JSON hoặc `ex.getMessage()` không?
4. **Exception boundary:** lỗi 403, lỗi mạng, lỗi mapping và lỗi secret thiếu có được phân loại và trả thông điệp công khai an toàn?
5. **HTTP client:** có interceptor/wire logger/debug config nào ghi header `X-Vault-Token` hay request/response body không?
6. **Observability:** metric, trace, MDC, baggage, tag và request ID có được phân loại/giới hạn không?
7. **PKI/Transit:** plaintext Base64, ciphertext, PEM private key và context có được bảo vệ ở mọi đoạn xử lý?
8. **Kiểm thử:** có test với chuỗi sentinel giả để phát hiện rò rỉ qua `toString()`, JSON, exception và sink log chính?
9. **Vận hành:** hệ thống thu thập log, thời hạn lưu, phân quyền truy cập và công cụ hỗ trợ có tuân theo chính sách secrets không?
10. **Rotation:** khi secret đổi, hệ thống cập nhật client/cache và tiếp tục ghi log **trạng thái** thay vì giá trị credential chứ?

Ưu tiên phòng ngừa ngay tại nguồn. Redaction/masking của collector là lớp bổ sung, không phải lý do để log toàn bộ DTO rồi hy vọng bộ lọc che được tất cả.

## 13. Bài tập thực hành

### Bài tập 1 — Sửa logger làm lộ DTO

Cho đoạn mã:

```java
VaultResponseSupport<GatewaySecretDto> response =
        kv.get("payments/gateway", GatewaySecretDto.class);

log.info("Vault response={}", response);
log.debug("Secret data={}", response.getData());
```

Hãy viết lại để:

- Kiểm tra `response == null` trước khi đọc `getData()`.
- Kiểm tra DTO hợp lệ mà không đưa giá trị trường vào exception.
- Chỉ ghi loại thao tác, kết quả và thời lượng hoặc nhãn tài nguyên cố định.
- Không ghi nguyên `response`, DTO, `Map` hoặc token.

**Gợi ý:** Áp dụng `GatewaySecretLoader` và một event thuộc allowlist ở mục 6/9.

### Bài tập 2 — Lombok và JSON

Một DTO có:

```java
@lombok.Data
public class CredentialsDto {
    private String username;
    private String password;
    private String clientSecret;
}
```

Hãy chỉ ra rủi ro của `@Data`, hai cách thiết kế lại `toString()`, và vì sao chỉ thêm `@ToString.Exclude` chưa đảm bảo serializer JSON không xuất password. Nếu class phải dùng để ghi credentials vào Vault, giải thích rủi ro khi áp dụng `@JsonProperty(access = WRITE_ONLY)` mà không kiểm thử chiều serialize.

### Bài tập 3 — Exception an toàn nhưng vẫn chẩn đoán được

Một adapter đang dùng:

```java
try {
    return parseVaultResult(response);
} catch (RuntimeException ex) {
    log.error("Vault data={}, cause={}", response, ex.getMessage());
    throw new IllegalStateException(
            "Vault failed: " + ex.getMessage(), ex);
}
```

Đề xuất quy tắc thay thế có mã lỗi, phân loại lỗi truy cập/schema, không ghi raw response và không đẩy cause chưa được đánh giá ra HTTP. Trường hợp nào cần giữ thêm thông tin chẩn đoán ở một sink có phân quyền?

### Bài tập 4 — Transit, PKI và observability

Một hệ thống có hai span:

```text
span A: transit.decrypt
  attribute plaintext_base64 = ...

span B: pki.issue
  attribute private_key_pem = ...
```

Tại sao cả hai thuộc tính đều không phù hợp? Thiết kế lại các thuộc tính span chỉ có loại thao tác, kết quả, latency và mã lỗi ổn định. Đề xuất test phát hiện sentinel giả xuất hiện trong span, log hoặc error body.

### Bài tập 5 — Chính sách dữ liệu tối thiểu

Chọn ba nhóm thông tin: `apiKey`, `metadata.version` KV v2 và `request_id`. Xác định nhóm nào có thể đi vào log thông thường, nhóm nào cần chính sách bổ sung và nhóm nào phải tránh. Giải thích vì sao version và request ID dù không phải credential cũng không được tự động coi là công khai tuyệt đối.

## 14. Những điểm cần ghi nhớ

- **Đừng log DTO chứa secret**, dù đó là `GatewaySecretDto`, `VaultResponse`, `VaultResponseSupport<T>`, `Versioned<T>` hoặc `Map<String, Object>`.
- SLF4J `{}`, `toString()` tự sinh của record và Lombok, JSON serialization, exception cause, HTTP wire logging, APM và metric labels đều có thể trở thành đường thoát dữ liệu.
- Ghi đè `toString()` thành thông điệp redacted là một lớp bảo vệ cần thiết, nhưng **không** ngăn mọi serializer hay reflection truy cập trường bí mật.
- Với Jackson, `WRITE_ONLY` có thể hỗ trợ DTO chỉ nhận dữ liệu, nhưng cũng có thể làm mất secret khi cùng DTO được dùng để **ghi**. Ưu tiên DTO inbound/outbound tách biệt và kiểm thử đúng mapper.
- Thay vì tạo log từ DTO rồi mask, hãy **định nghĩa sự kiện log riêng** chỉ chứa các trường an toàn thuộc allowlist.
- Exception công khai nên dùng mã lỗi ổn định; nguyên nhân nội bộ cần được phân loại và lưu có kiểm soát, không để payload/cause chưa đánh giá lan qua logger, framework hoặc HTTP response.
- Base64 plaintext Transit không được phép log. PKI `private_key`, token Vault, dynamic credentials và lease/auth metadata cần được bảo vệ theo vai trò.
- Bảo vệ secrets trong observability, CI và support workflow quan trọng không kém Vault policy và TLS; kiểm thử chống rò rỉ với **dữ liệu giả** trước khi triển khai.

## Tài liệu tham khảo

- [Spring Vault — Vault Operations](https://docs.spring.io/spring-vault/reference/vault/imperative-template.html): `VaultTemplate`, `VaultOperations` và phản hồi Vault.
- [Spring Vault — Vault Secrets Engines](https://docs.spring.io/spring-vault/reference/vault/vault-secret-engines.html): KV, Transit, PKI và phương thức truy cập.
- [Spring Vault — `VaultResponseSupport<T>` API](https://docs.spring.io/spring-vault/docs/current/api/org/springframework/vault/support/VaultResponseSupport.html): dữ liệu có kiểu trong phản hồi.
- [Spring Vault — `Versioned<T>` API](https://docs.spring.io/spring-vault/docs/current/api/org/springframework/vault/support/Versioned.html): dữ liệu và metadata phiên bản KV v2.
- [HashiCorp Vault — Audit Devices](https://developer.hashicorp.com/vault/docs/audit): audit logging của Vault và chính sách bảo vệ thông tin.
- [HashiCorp Vault — Transit API](https://developer.hashicorp.com/vault/api-docs/secret/transit): `plaintext` Base64, ciphertext và context.
- [HashiCorp Vault — PKI API](https://developer.hashicorp.com/vault/api-docs/secret/pki): các trường response khi cấp chứng chỉ.
- [Jackson — `JsonProperty.Access`](https://fasterxml.github.io/jackson-annotations/javadoc/2.15/com/fasterxml/jackson/annotation/JsonProperty.Access.html): điều khiển deserialize/serialize theo hướng.
- [OWASP — Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html): phân loại nội dung log, tránh ghi dữ liệu nhạy cảm.
