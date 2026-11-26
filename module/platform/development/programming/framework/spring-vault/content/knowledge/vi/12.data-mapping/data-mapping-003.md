# Ánh xạ phản hồi thành DTO thay vì truyền Map xuyên ứng dụng

## Mục tiêu bài học

Khi dùng **Spring Vault**, một ứng dụng Java thường nhận secret từ HashiCorp Vault dưới dạng `VaultResponse`, trong đó phần `data` là `Map<String, Object>`. Cách đọc này tiện để khám phá API, nhưng nếu truyền `Map` từ lớp kết nối Vault qua service, client HTTP và các lớp nghiệp vụ, mỗi nơi sẽ tự lấy khóa, ép kiểu và suy đoán về cấu trúc dữ liệu. Lỗi chính tả trong tên khóa hoặc thay đổi schema của secret có thể chỉ xuất hiện khi chương trình chạy.

Giải pháp là **ánh xạ phản hồi thành DTO có kiểu ngay tại ranh giới tích hợp**, kiểm tra tính hợp lệ, rồi truyền một đối tượng cấu hình rõ ràng vào ứng dụng. DTO ở đây là *Data Transfer Object*: một cấu trúc dữ liệu mô tả các trường cần trao đổi, không phải đối tượng quản lý token, lease hay toàn bộ phản hồi của Vault.

Sau bài học, bạn có thể:

1. Giải thích vì sao `Map<String, Object>` nên dừng ở lớp tích hợp thay vì lan ra mã nghiệp vụ.
2. Phân biệt `VaultResponse`, `VaultResponseSupport<T>`, DTO chứa secret và đối tượng cấu hình sau validation.
3. Đọc secret KV v2 thành DTO bằng `VaultKeyValueOperations.get(path, Class<T>)`.
4. Thiết kế DTO có trường lồng nhau, collection và kiểu nullable để phát hiện cấu hình thiếu.
5. Đặt validation và xử lý lỗi ở đúng ranh giới, tránh làm lộ token/password/API key qua log.
6. Thử nghiệm hành vi khi dữ liệu Vault thiếu, sai kiểu, thay đổi schema hoặc cần rotation.

> **Bối cảnh:** Đây là bài thuộc chương **Ánh xạ dữ liệu** của module `SPRING_VAULT`. Module hướng đến việc Java truy cập Vault qua `VaultTemplate`, xác thực theo workload và Vault policy; đồng thời thực hành KV, vòng đời token/lease, Transit, PKI, xử lý lỗi, quan sát và kiểm thử tích hợp. Trong bài này, kết nối, xác thực và policy đọc secret được giả định đã cấu hình đúng. Chúng ta tập trung vào ranh giới dữ liệu trong Java.

## 1. Vấn đề khi truyền `Map<String, Object>` xuyên ứng dụng

Giả sử một dịch vụ thanh toán đọc secret KV v2 với nội dung nghiệp vụ:

```json
{
  "apiKey": "<gia-tri-bi-mat>",
  "endpoint": "https://payments.internal.example/api",
  "timeoutSeconds": 15,
  "retry": {
    "maxAttempts": 3
  },
  "regions": ["ap-southeast-1", "eu-west-1"]
}
```

Ứng dụng có thể đọc phần dữ liệu vào `Map` và truyền đi:

```java
// Ví dụ cách tổ chức cần cải thiện.
Map<String, Object> secretData = response.getRequiredData();
paymentService.initialize(secretData);
```

Trong `PaymentService`, một lập trình viên gọi:

```java
String endpoint = (String) secretData.get("endpoint");
Integer timeout = (Integer) secretData.get("timeoutSeconds");
```

Một lớp khác lại tự đọc `retry.maxAttempts` bằng cách ép sang `Map<String, Object>`. Các lỗi sau có thể xuất hiện:

- Sai khóa `timeoutSeconds` thành `timeOutSeconds`: `Map.get(...)` trả `null`, trình biên dịch không phát hiện.
- Giá trị timeout được chuyển thành `Long` hoặc `String`: phép ép kiểu sang `Integer` có thể lỗi hoặc hành vi bị che khuất.
- `retry` không có, hoặc là chuỗi: ép kiểu và truy cập sâu có thể gây `NullPointerException` hoặc `ClassCastException`.
- Nhiều lớp tự quyết định timeout mặc định khác nhau, tạo hành vi thiếu nhất quán.
- `Map.toString()` hoặc log toàn bộ request nội bộ có thể làm lộ `apiKey`.
- Logic nghiệp vụ bị ràng buộc với đường dẫn, tên khóa và cấu trúc phản hồi của Vault, khó thay bằng nguồn cấu hình khác khi kiểm thử.

Vấn đề lớn nhất không nằm ở bản thân `Map`: đó là một cấu trúc hợp lý cho dữ liệu động. Vấn đề là **không có hợp đồng kiểu và nơi chịu trách nhiệm xác nhận dữ liệu**. Khi schema đã rõ ràng, DTO cho phép tập trung việc ánh xạ và kiểm tra vào một điểm.

### So sánh hai luồng dữ liệu

```text
Truyền Map xuyên ứng dụng:
Vault → VaultResponse → Map<String, Object>
                           ├── PaymentService tự ép kiểu
                           ├── HttpClientFactory tự đọc các key
                           └── RetryPolicyService tự duyệt Map lồng nhau

Ánh xạ ở ranh giới:
Vault → VaultResponseSupport<PaymentSecretDto>
                           └── validate + chuyển đổi
                                 └── PaymentGatewaySettings (có kiểu, hợp lệ)
                                       ├── PaymentService
                                       └── HttpClientFactory
```

Ở luồng thứ hai, chỉ lớp adapter biết secret được lấy từ KV v2. Các thành phần nghiệp vụ nhận một hợp đồng Java rõ ràng. Việc thay đường dẫn Vault hay đổi cách đọc KV không nhất thiết làm thay đổi public API của các lớp nghiệp vụ.

## 2. Ba lớp đối tượng cần phân biệt

Spring Vault có các kiểu phản hồi trong package `org.springframework.vault.support`:

| Đối tượng | Vai trò | Nên xuất hiện ở đâu? |
|---|---|---|
| `VaultResponse` | Phản hồi có phần `data` là `Map<String, Object>`; phù hợp với thao tác chưa định kiểu | Tầng giao tiếp Vault, adapter |
| `VaultResponseSupport<T>` | Phản hồi có phần `data` thuộc kiểu `T`; vẫn mang thông tin phản hồi như request ID/lease nếu endpoint cung cấp | Tầng giao tiếp Vault, adapter |
| `PaymentSecretDto` (tự định nghĩa) | Chứa riêng các trường nghiệp vụ mà Vault lưu, ví dụ `apiKey`, `timeoutSeconds`, `retry` | Tầng ánh xạ cấu hình |
| `PaymentGatewaySettings` (tự định nghĩa) | Đối tượng Java đã được kiểm tra và chuẩn hóa để ứng dụng sử dụng | Các thành phần cần cấu hình hợp lệ |

Kiểu tổng quát biểu thị quan hệ:

```java
// Minh họa quan hệ kiểu; không phải khai báo cần thêm vào dự án.
class VaultResponseSupport<T> { /* getData() trả về T */ }
class VaultResponse extends VaultResponseSupport<Map<String, Object>> {}
```

Điều này dẫn đến hai cách đọc:

```java
VaultResponse raw = kv.get("payment/gateway");
Map<String, Object> rawData = raw.getRequiredData();

VaultResponseSupport<PaymentSecretDto> typed =
        kv.get("payment/gateway", PaymentSecretDto.class);
PaymentSecretDto typedData = typed.getRequiredData();
```

Hai đoạn mã minh họa **kiểu kết quả**, giả định các phản hồi tồn tại. Trong chương trình thực tế phải kiểm tra `raw == null` và `typed == null` trước khi gọi accessor. `getRequiredData()` không xử lý việc biến phản hồi là `null`; nó yêu cầu phần `data` của phản hồi không được `null`.

**DTO không cần chứa `request_id`, `lease_id` hoặc `warnings`** chỉ vì các trường đó xuất hiện ở lớp phản hồi. Chúng thuộc cơ chế quản lý yêu cầu hoặc vòng đời dữ liệu của Vault. Nếu đọc secrets động có lease, adapter hoặc thành phần quản lý lease phải xử lý metadata liên quan thay vì nhét chúng vào DTO nghiệp vụ.

## 3. Thiết kế DTO phản ánh schema secret

Với JSON ở mục 1, ta tạo một DTO JavaBean. Ví dụ dùng Java 17+ và các kiểu dữ liệu phổ biến, tránh phụ thuộc vào Lombok:

```java
import java.util.List;

public class PaymentSecretDto {

    private String apiKey;
    private String endpoint;
    private Integer timeoutSeconds;
    private RetryDto retry;
    private List<String> regions;

    public PaymentSecretDto() {
        // Constructor không tham số cho cơ chế ánh xạ kiểu JavaBean.
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

    public RetryDto getRetry() {
        return retry;
    }

    public void setRetry(RetryDto retry) {
        this.retry = retry;
    }

    public List<String> getRegions() {
        return regions;
    }

    public void setRegions(List<String> regions) {
        this.regions = regions;
    }

    public static class RetryDto {
        private Integer maxAttempts;

        public RetryDto() {
        }

        public Integer getMaxAttempts() {
            return maxAttempts;
        }

        public void setMaxAttempts(Integer maxAttempts) {
            this.maxAttempts = maxAttempts;
        }
    }
}
```

DTO này có năm đặc điểm đáng chú ý:

1. **Tên thuộc tính khớp schema:** `apiKey` trong JSON tương ứng thuộc tính `apiKey` trong JavaBean. Nếu Vault lưu `api_key` thì cần cấu hình quy tắc đặt tên hoặc ánh xạ field phù hợp; không mặc định trình chuyển đổi tự hiểu mọi quy ước.
2. **Dùng `Integer` thay vì `int` ở đầu vào:** Khi thiếu `timeoutSeconds`, DTO có thể giữ `null` để bước validation phát hiện. Nếu dùng `int`, giá trị mặc định `0` dễ gây nhầm với giá trị đã được cung cấp.
3. **Object lồng nhau có kiểu:** `retry` ánh xạ vào `RetryDto`, thay cho `Map` lồng nhau.
4. **Collection có kiểu phần tử:** `regions` là `List<String>`, không phải `List<Object>`. Bộ ánh xạ cần hỗ trợ kiểu property này; vẫn phải kiểm tra collection rỗng và phần tử bất hợp lệ.
5. **Không sinh chuỗi chứa secret:** DTO không khai báo `toString()` in các trường. Tránh đặt `@Data` hoặc tự động sinh `toString()` liệt kê `apiKey` nếu DTO có thể đi qua log.

DTO đang là cấu trúc chuyển dữ liệu, **chưa phải bảo đảm về tính hợp lệ**. Kiểu `Integer` không ngăn được timeout âm; `String` không bảo đảm endpoint là URL hợp lệ; `List<String>` không ngăn danh sách rỗng.

### DTO `record` có dùng được không?

Java `record` giúp giảm mã lặp:

```java
public record RetryDto(Integer maxAttempts) {}
```

Tuy nhiên, khả năng ánh xạ constructor/record phụ thuộc phiên bản Java và bộ chuyển đổi được cấu hình trong Spring Vault. JavaBean với constructor rỗng và getter/setter là lựa chọn dễ đọc cho ví dụ; hãy kiểm thử với phiên bản phụ thuộc của dự án trước khi chuyển toàn bộ DTO sang `record`. Đặc biệt, `record` tự sinh `toString()` từ các thành phần: không dùng mặc định này cho DTO chứa API key hoặc password.

## 4. Đọc DTO bằng API KV của Spring Vault

Giả sử hệ thống dùng KV v2 được mount ở `secret`. Path logic của secret là `payment/gateway`. Nếu đọc ở mức HTTP, path dữ liệu KV v2 tương ứng là `secret/data/payment/gateway`; cách gọi `VaultKeyValueOperations` sẽ xử lý phần `data/` này.

```java
import org.springframework.vault.core.VaultKeyValueOperations;
import org.springframework.vault.core.VaultOperations;
import org.springframework.vault.core.VaultKeyValueOperationsSupport.KeyValueBackend;
import org.springframework.vault.support.VaultResponseSupport;

public final class PaymentVaultReader {

    private final VaultKeyValueOperations kv;

    public PaymentVaultReader(VaultOperations vaultOperations) {
        this.kv = vaultOperations.opsForKeyValue(
                "secret", KeyValueBackend.KV_2);
    }

    public PaymentSecretDto readDto() {
        VaultResponseSupport<PaymentSecretDto> response =
                kv.get("payment/gateway", PaymentSecretDto.class);

        if (response == null || response.getData() == null) {
            throw new IllegalStateException(
                    "Thiếu cấu hình payment/gateway trong Vault");
        }

        return response.getRequiredData();
    }
}
```

Trong ví dụ, `VaultOperations` thường được ứng dụng cung cấp qua dependency injection; `VaultTemplate` là một triển khai tiêu biểu. Phương thức `get(path, Class<T>)` biểu diễn phần dữ liệu nghiệp vụ dưới dạng `T` trong `VaultResponseSupport<T>`. Path `payment/gateway` là tương đối với mount `secret`; không truyền `data/payment/gateway` cho API KV v2 mức cao.

Với secret KV v2, phản hồi HTTP thô có dạng gần như:

```json
{
  "request_id": "request-example",
  "data": {
    "data": {
      "apiKey": "<gia-tri-bi-mat>",
      "endpoint": "https://payments.internal.example/api",
      "timeoutSeconds": 15,
      "retry": { "maxAttempts": 3 },
      "regions": ["ap-southeast-1", "eu-west-1"]
    },
    "metadata": {
      "version": 4
    }
  }
}
```

Nếu gọi trực tiếp `vaultOperations.read("secret/data/payment/gateway")`, `VaultResponse.getData()` chứa object gồm `data` và `metadata` của KV v2; muốn đọc `apiKey` phải tiếp tục vào lớp `data` bên trong. Ngược lại, `kv.get("payment/gateway", PaymentSecretDto.class)` xử lý cấu trúc KV tương ứng và trả về DTO chứa ngay các trường nghiệp vụ. Đây là một lý do thực tế nên chọn API KV chuyên biệt.

> **Phân biệt:** `metadata.version` trong phản hồi KV v2 là thông tin phiên bản secret. Nếu ứng dụng cần đọc phiên bản cụ thể hay quản lý metadata, hãy cân nhắc `VaultVersionedKeyValueOperations`. DTO `PaymentSecretDto` không nên tự thêm `version` rồi giả định trường này nằm cạnh `apiKey` trong dữ liệu nghiệp vụ.

### Yêu cầu về policy và danh tính

Đường dẫn policy của Vault KV v2 được xác định theo API engine, chẳng hạn quyền đọc tương ứng với `secret/data/payment/gateway`. Path trong lời gọi `kv.get(...)` lại là path logic `payment/gateway`. Hai dạng đường dẫn phục vụ hai mục đích khác nhau, không nên ghép thủ công.

Đoạn Java không chứa token Vault. Ứng dụng cần sử dụng cơ chế xác thực workload phù hợp, giới hạn policy theo nguyên tắc quyền tối thiểu và xử lý vòng đời token qua cấu hình Spring Vault. Đổi từ `Map` sang DTO **không** tự thay đổi quyền truy cập, thời hạn secret hay hành vi gia hạn lease.

## 5. DTO sau deserialize cần bước validation

Ngay cả khi `readDto()` trả về `PaymentSecretDto`, ứng dụng vẫn phải kiểm tra hợp đồng dữ liệu trước khi tạo HTTP client thanh toán. Ta có thể dùng một lớp cấu hình **bất biến** được xây dựng từ DTO sau validation:

```java
import java.net.URI;
import java.time.Duration;
import java.util.List;

public final class PaymentGatewaySettings {

    private final URI endpoint;
    private final String apiKey;
    private final Duration timeout;
    private final int maxAttempts;
    private final List<String> regions;

    private PaymentGatewaySettings(
            URI endpoint,
            String apiKey,
            Duration timeout,
            int maxAttempts,
            List<String> regions) {
        this.endpoint = endpoint;
        this.apiKey = apiKey;
        this.timeout = timeout;
        this.maxAttempts = maxAttempts;
        this.regions = regions;
    }

    public static PaymentGatewaySettings from(PaymentSecretDto dto) {
        if (dto == null) {
            throw new IllegalArgumentException("PaymentSecretDto không tồn tại");
        }

        String apiKey = requireText(dto.getApiKey(), "apiKey");
        String endpointText = requireText(dto.getEndpoint(), "endpoint");

        URI endpoint;
        try {
            endpoint = URI.create(endpointText);
        } catch (IllegalArgumentException invalidUri) {
            // Không nối endpointText hay nguyên exception của parser vào log.
            throw new IllegalArgumentException("endpoint không đúng định dạng URI");
        }

        if (!"https".equalsIgnoreCase(endpoint.getScheme())
                || endpoint.getHost() == null
                || endpoint.getUserInfo() != null) {
            throw new IllegalArgumentException(
                    "endpoint phải là HTTPS URL có hostname và không chứa userinfo");
        }

        Integer seconds = dto.getTimeoutSeconds();
        if (seconds == null || seconds < 1 || seconds > 120) {
            throw new IllegalArgumentException(
                    "timeoutSeconds phải nằm trong khoảng 1..120");
        }

        PaymentSecretDto.RetryDto retry = dto.getRetry();
        if (retry == null
                || retry.getMaxAttempts() == null
                || retry.getMaxAttempts() < 1
                || retry.getMaxAttempts() > 5) {
            throw new IllegalArgumentException(
                    "retry.maxAttempts phải nằm trong khoảng 1..5");
        }

        List<String> regions = dto.getRegions();
        if (regions == null || regions.isEmpty()) {
            throw new IllegalArgumentException("regions không được rỗng");
        }
        for (int i = 0; i < regions.size(); i++) {
            if (regions.get(i) == null || regions.get(i).isBlank()) {
                throw new IllegalArgumentException(
                        "regions[" + i + "] phải là chuỗi không rỗng");
            }
        }

        return new PaymentGatewaySettings(
                endpoint,
                apiKey,
                Duration.ofSeconds(seconds),
                retry.getMaxAttempts(),
                List.copyOf(regions));
    }

    private static String requireText(String value, String field) {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException(
                    field + " phải là chuỗi không rỗng");
        }
        return value;
    }

    public URI endpoint() {
        return endpoint;
    }

    public String apiKey() {
        return apiKey;
    }

    public Duration timeout() {
        return timeout;
    }

    public int maxAttempts() {
        return maxAttempts;
    }

    public List<String> regions() {
        return regions;
    }

    @Override
    public String toString() {
        return "PaymentGatewaySettings[redacted]";
    }
}
```

Đoạn code này cố ý tách ba việc:

- **Deserialize:** chuyển JSON `data` sang `PaymentSecretDto`.
- **Validate:** kiểm tra secret bắt buộc, URL HTTPS, khoảng timeout/retry, danh sách vùng.
- **Normalize:** chuyển `String` endpoint thành `URI`, giây thành `Duration`, sao chép collection bằng `List.copyOf(...)` để tránh sửa đổi ngẫu nhiên.

Lớp `PaymentGatewaySettings` bất biến về cấu trúc, nhưng `String apiKey` vẫn tồn tại trong bộ nhớ JVM và có thể được dùng bởi thành phần tích hợp thực sự cần nó. Không có bảo đảm xóa sạch một `String` khỏi heap sau khi sử dụng. Vì vậy, cần kiểm soát phạm vi truyền, thời gian giữ tham chiếu, logging và vòng đời rotation phù hợp.

Đây là validation **minh họa**; một hệ thống thực tế còn có thể bắt buộc host thuộc allowlist, kiểm tra scheme/port/path, quy tắc cho query và fragment, cũng như chính sách timeout khác. Nếu các thành phần khác ghi log `URI` hoặc URL có query nhạy cảm, cần kiểm soát và che dữ liệu tương ứng.

## 6. Đưa DTO vào adapter, cung cấp cấu hình có kiểu cho nghiệp vụ

Ta kết hợp bước đọc và validation trong một lớp cung cấp cấu hình:

```java
public interface PaymentSettingsProvider {
    PaymentGatewaySettings load();
}
```

```java
import org.springframework.stereotype.Component;
import org.springframework.vault.core.VaultKeyValueOperations;
import org.springframework.vault.core.VaultOperations;
import org.springframework.vault.core.VaultKeyValueOperationsSupport.KeyValueBackend;
import org.springframework.vault.support.VaultResponseSupport;

@Component
public final class VaultPaymentSettingsProvider implements PaymentSettingsProvider {

    private final VaultKeyValueOperations kv;

    public VaultPaymentSettingsProvider(VaultOperations vaultOperations) {
        this.kv = vaultOperations.opsForKeyValue(
                "secret", KeyValueBackend.KV_2);
    }

    @Override
    public PaymentGatewaySettings load() {
        VaultResponseSupport<PaymentSecretDto> response =
                kv.get("payment/gateway", PaymentSecretDto.class);

        if (response == null || response.getData() == null) {
            throw new IllegalStateException(
                    "Không tìm thấy cấu hình payment/gateway");
        }

        PaymentSecretDto dto = response.getRequiredData();
        return PaymentGatewaySettings.from(dto);
    }
}
```

`PaymentSettingsProvider` là một interface do ứng dụng định nghĩa. Chỉ `VaultPaymentSettingsProvider` phụ thuộc API Spring Vault và biết path KV v2. Khi sử dụng trong một service:

```java
public final class PaymentService {

    private final PaymentSettingsProvider settingsProvider;

    public PaymentService(PaymentSettingsProvider settingsProvider) {
        this.settingsProvider = settingsProvider;
    }

    public void initializeClient() {
        PaymentGatewaySettings settings = settingsProvider.load();
        // Cấu hình client HTTP bằng endpoint(), timeout(), maxAttempts().
        // Chỉ thành phần gửi request được lấy apiKey() để gắn vào header.
        // Không log settings hoặc apiKey().
    }
}
```

Mô hình phụ thuộc có dạng:

```text
             ┌────────────────────────────────┐
             │         PaymentService         │
             │ dùng PaymentGatewaySettings    │
             └──────────────┬─────────────────┘
                            │
                     interface load()
                            │
             ┌──────────────▼─────────────────┐
             │     PaymentSettingsProvider    │
             └──────────────▲─────────────────┘
                            │
             ┌──────────────┴─────────────────┐
             │  VaultPaymentSettingsProvider  │
             │  KV_2.get(..., DTO.class)      │
             │  validate + normalize          │
             └──────────────┬─────────────────┘
                            │
                       Spring Vault
                            │
                         Vault KV v2
```

Vì `PaymentService` chỉ biết interface, unit test có thể cấp một bản triển khai giả trả về `PaymentGatewaySettings` hợp lệ. Không cần mở kết nối Vault thật để kiểm tra logic thanh toán. Ngược lại, kiểm thử tích hợp của adapter tập trung vào mount, path, policy, mapping và lỗi truy cập Vault.

**Chú ý thời điểm gọi `load()`:** ví dụ gọi khi khởi tạo client; không có nghĩa mọi request thanh toán đều cần tải lại secret. Cơ chế cache hoặc refresh phải được chọn theo yêu cầu sử dụng, độ trễ, thời điểm rotation, lease và chính sách của tổ chức. DTO có kiểu không tự cập nhật credentials khi Vault đổi giá trị.

## 7. Khi nào vẫn nên dùng `Map`?

DTO không phải thay thế bắt buộc cho mọi phản hồi JSON. Chọn theo mức ổn định của schema:

| Trường hợp | Lựa chọn hợp lý | Giải thích |
|---|---|---|
| Secret có cấu trúc cố định, được một dịch vụ sử dụng | `VaultResponseSupport<PaymentSecretDto>` | Ánh xạ có kiểu ngay tại ranh giới, dễ validation và refactor |
| DTO đã deserialize nhưng chưa kiểm tra ràng buộc | DTO + bước validate/normalize | Tách lỗi mapping và lỗi cấu hình nghiệp vụ |
| Adapter đọc nhiều path, mỗi path có tập key khác nhau | `VaultResponse`/`Map` trong adapter | Dữ liệu linh hoạt; cần kiểm tra kiểu cho từng thao tác |
| Muốn xem chính xác cấu trúc API khi tích hợp secrets engine mới | Đọc phản hồi chưa định kiểu trong môi trường thử nghiệm | Hữu ích để hiểu schema; không in giá trị bí mật ra log |
| Cần metadata của KV v2 hoặc đọc phiên bản cụ thể | API chuyên biệt, như `VaultVersionedKeyValueOperations` | Metadata phiên bản khác với DTO nghiệp vụ |
| Nhận credentials động có lease | API phù hợp và thành phần quản lý lease/token | DTO nghiệp vụ không thay thế quản lý vòng đời thông tin đăng nhập |

Một DTO có thể chứa `Map<String, String>` **nếu đó chính là hợp đồng nghiệp vụ**, ví dụ tập các header tùy biến có tên bất kỳ. Điều cần tránh là biến toàn bộ kết quả Vault thành `Map<String, Object>` rồi yêu cầu mọi lớp tự tìm hiểu schema.

### Cân nhắc khi DTO trực tiếp đi vào tầng nghiệp vụ

Với ứng dụng nhỏ, `PaymentSecretDto` có thể đã đủ để cấu hình client sau khi kiểm tra. Tạo riêng `PaymentGatewaySettings` sẽ có ích khi:

- Cần đổi đơn vị hoặc kiểu, như `timeoutSeconds → Duration`.
- Muốn tránh cho mã nghiệp vụ thấy phương thức setter hoặc object lồng nhau còn `null`.
- Muốn giấu tên trường Vault khỏi interface ứng dụng.
- Muốn tách hợp đồng dữ liệu lưu trữ khỏi hợp đồng nghiệp vụ để schema KV có thể thay đổi mà không lan sang nhiều lớp.

Không nên thêm quá nhiều lớp chỉ để sao chép thuộc tính y hệt nhau. Mục tiêu là có **một ranh giới rõ ràng, kiểm soát được**, không phải số lượng DTO càng nhiều càng tốt.

## 8. Thay đổi schema và tương thích dữ liệu

Khi Vault secrets thay đổi, một DTO có kiểu giúp xác định những điểm cần xem xét:

| Thay đổi JSON trong Vault | Tác động có thể gặp | Cách xử lý |
|---|---|---|
| Thêm trường tùy chọn `description` | DTO hiện tại có thể bỏ qua nếu bộ chuyển đổi hỗ trợ unknown fields | Xác nhận chính sách unknown property, sau đó mới phụ thuộc vào hành vi đó |
| Đổi `timeoutSeconds` thành `timeoutMillis` | DTO cũ nhận `null` cho trường bắt buộc | Phối hợp thay đổi schema và mã ánh xạ; nếu cần chuyển tiếp, hỗ trợ hai tên có thời hạn |
| Đổi `retry` từ object sang chuỗi | Deserialize hoặc validation thất bại | Từ chối dữ liệu sai kiểu, không âm thầm dùng giá trị mặc định |
| Bỏ trường `apiKey` | Không thể khởi tạo client | Fail fast với thông báo thiếu trường; không fallback về token cố định trong mã |
| Thêm vùng vào `regions` | Collection mới có thể hợp lệ | Tiếp tục kiểm tra phần tử và ràng buộc nghiệp vụ |
| Xoay vòng giá trị `apiKey` nhưng không đổi schema | DTO vẫn ánh xạ thành công | Cần chiến lược làm mới giá trị trong bộ nhớ theo rotation |

**Unknown fields:** mức độ chấp nhận trường mới phụ thuộc bộ chuyển đổi và cấu hình thực tế. Không mặc định mọi bản Spring Vault luôn tự bỏ qua trường lạ hoặc luôn từ chối. Hãy kiểm tra hành vi bằng ca tích hợp tương ứng, đặc biệt trước khi triển khai thay đổi schema có chủ đích.

**Missing versus null:** DTO `PaymentSecretDto` có `apiKey == null` khi trường thiếu hoặc được đặt thành JSON `null`, nên thường không phân biệt được hai trạng thái đó chỉ bằng property. Nếu nghiệp vụ yêu cầu phân biệt “không xuất hiện” với “có mặt nhưng null”, cần thiết kế hợp đồng và cơ chế deserialize phù hợp, hoặc kiểm tra bằng `Map.containsKey(...)` ở ranh giới.

**Đổi tên trường:** nếu muốn phiên bản hóa cấu hình, có thể ghi một trường schema version **trong chính dữ liệu nghiệp vụ** như `schemaVersion` và validate rõ ràng. Trường này khác `metadata.version` của KV v2; metadata chỉ cho biết phiên bản lưu trữ secret, không tự diễn tả phiên bản hợp đồng DTO.

## 9. Xử lý lỗi ở ranh giới tích hợp

Mỗi giai đoạn có loại lỗi khác nhau. Khi quan sát production, việc phân biệt chúng giúp xác định đúng nguyên nhân và hành động:

| Giai đoạn | Dấu hiệu | Hướng xử lý |
|---|---|---|
| Kết nối, TLS, workload authentication hoặc policy | Vault/Spring Vault báo lỗi HTTP, xác thực, quyền hay I/O | Theo dõi status và request ID khi phù hợp; xử lý credentials/policy/kết nối theo nguyên nhân |
| Path không tồn tại hoặc secret không đọc được | Có thể nhận `null` từ lời gọi đọc khi path không tồn tại; trường hợp khác có thể báo lỗi | Kiểm tra response trước khi đọc data; không gộp mọi lỗi thành “không có secret” |
| Dữ liệu JSON không ánh xạ được DTO | Lỗi chuyển đổi/deserialize, schema sai hoặc kiểu field không tương thích | Xác định field lỗi; báo cấu hình không hợp lệ mà không in payload |
| DTO ánh xạ được nhưng vi phạm quy tắc | `timeoutSeconds == null`, `maxAttempts < 1`, `apiKey` rỗng | Validation có chủ đích; tránh đưa cấu hình chưa hợp lệ vào client |
| Secret bị rotate trong khi client dùng bản cũ | Client có thể bị từ chối khi gọi hệ thống đích | Thiết kế refresh/rebuild client phù hợp; xem xét token và lease nếu có |

Không viết:

```java
try {
    return readFromVault();
} catch (Exception ex) {
    return new HashMap<>(); // Sai: che tất cả lỗi truy cập và schema.
}
```

Với các secrets bắt buộc, trả về dữ liệu rỗng sau lỗi 403 hoặc lỗi deserialize có thể đẩy hệ thống vào trạng thái hoạt động không an toàn. Trong hệ thống cần độ sẵn sàng cao, chính sách dùng giá trị đã kiểm tra gần nhất (*last known good*) phải được thiết kế riêng với thời hạn và ràng buộc phù hợp, không phải fallback ngẫu nhiên.

### Tránh rò rỉ secrets khi log

- Không ghi `response`, `response.getData()`, `dto` hoặc `settings.apiKey()` trực tiếp vào log, metric labels, thông báo exception, trace hay phản hồi HTTP của ứng dụng.
- Cẩn thận với `toString()` tự sinh của `record`, Lombok `@Data` và công cụ serialize object tự động.
- Khi xác thực URL thất bại, thông báo chỉ nên nêu tên trường `endpoint` và lý do; không đính kèm URI thô nếu URI có thể chứa thông tin nhạy cảm.
- Có thể log loại thao tác và mã yêu cầu Vault khi chính sách observability cho phép. Hãy kiểm soát metadata khác, đặc biệt `auth` payload và token.
- Không truyền DTO secrets sang REST controller hoặc serialization công khai chỉ vì class đó có getter.

Trong các endpoint có lease, response metadata về lease hoặc auth không thể được thay thế bởi DTO chứa username/password. Khi dùng Spring Vault để quản lý token và lease, cần áp dụng cơ chế vòng đời tương ứng; không suy từ sự thành công của phép ánh xạ rằng credentials luôn còn hiệu lực.

## 10. Chiến lược kiểm thử

Việc tách `PaymentGatewaySettings.from(dto)` khỏi phần gọi Vault giúp tạo kiểm thử nhanh chỉ bằng Java. Bộ tình huống nên bao phủ:

| Dữ liệu kiểm thử | Kết quả mong đợi |
|---|---|
| DTO có đủ field đúng kiểu | Tạo `PaymentGatewaySettings` chứa URI, Duration và các giá trị đúng |
| `apiKey` là `null` hoặc chuỗi trắng | Validation từ chối, không log token |
| `timeoutSeconds` là `null`, `0` hoặc `121` | Validation từ chối |
| `retry` là `null` hoặc `maxAttempts` ngoài `1..5` | Validation từ chối |
| `regions` rỗng, chứa `null` hoặc chuỗi trống | Validation từ chối và chỉ rõ vị trí lỗi |
| `endpoint` sai định dạng hoặc không phải HTTPS | Validation từ chối, không lộ giá trị URI |
| JSON thiếu `timeoutSeconds` khi đọc vào DTO | Phát hiện trường thiếu ở bước validation, hoặc lỗi ở bước mapping theo cấu hình thực tế |
| JSON đổi `retry.maxAttempts` sang object/list | Lỗi deserialize hoặc validation, không cho chạy tiếp với cấu hình mặc định |
| Vault trả 403 do policy | Lỗi truy cập được giữ riêng; không chuyển thành DTO rỗng |
| Secret không tồn tại | Adapter phát hiện phản hồi không có dữ liệu và báo lỗi cấu hình |

### Ví dụ unit test độc lập với Vault

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.time.Duration;
import java.util.List;
import org.junit.jupiter.api.Test;

class PaymentGatewaySettingsTest {

    @Test
    void mapsValidDtoToValidatedSettings() {
        PaymentSecretDto dto = new PaymentSecretDto();
        dto.setApiKey("fake-token-for-test");
        dto.setEndpoint("https://payments.internal.example/api");
        dto.setTimeoutSeconds(15);
        dto.setRegions(List.of("ap-southeast-1"));

        PaymentSecretDto.RetryDto retry = new PaymentSecretDto.RetryDto();
        retry.setMaxAttempts(3);
        dto.setRetry(retry);

        PaymentGatewaySettings settings = PaymentGatewaySettings.from(dto);

        assertEquals(Duration.ofSeconds(15), settings.timeout());
        assertEquals(3, settings.maxAttempts());
        assertEquals("PaymentGatewaySettings[redacted]", settings.toString());
    }

    @Test
    void rejectsMissingApiKey() {
        PaymentSecretDto dto = new PaymentSecretDto();
        dto.setEndpoint("https://payments.internal.example/api");
        dto.setTimeoutSeconds(15);

        assertThrows(IllegalArgumentException.class,
                () -> PaymentGatewaySettings.from(dto));
    }
}
```

Những unit test trên kiểm tra logic validation/normalize, không chứng minh Vault đã trả đúng payload. Cần thêm kiểm thử tích hợp trong môi trường cô lập để xác nhận:

1. Mount KV v2 và policy thử nghiệm được cấu hình đúng.
2. `kv.get("payment/gateway", PaymentSecretDto.class)` tạo DTO với field lồng nhau và collection như mong đợi.
3. Dữ liệu thiếu/sai kiểu gây lỗi phù hợp với bộ ánh xạ thực tế.
4. Workload không đủ quyền nhận lỗi truy cập rõ ràng.
5. Những thay đổi schema có kế hoạch không làm hỏng dịch vụ ngoài ý muốn.

Sử dụng secret giả và môi trường Vault thử nghiệm; không đưa giá trị thật của sản xuất vào fixture, assertion, snapshot hay log. Nếu framework hỗ trợ Vault trong Testcontainers hoặc môi trường CI, có thể dùng để kiểm thử luồng kết nối hoàn chỉnh mà không phụ thuộc Vault production.

## 11. Bài tập thực hành

### Bài tập 1 — Chuyển `Map` sang DTO

Một service hiện nhận `Map<String, Object>` với các field `jdbcUrl`, `username`, `password`, `pool.maxSize` và truyền `Map` vào ba lớp khác nhau.

1. Thiết kế `DatabaseSecretDto` với `PoolDto` lồng nhau.
2. Viết validator yêu cầu `jdbcUrl` hợp lệ, `username/password` không rỗng và `maxSize` trong một khoảng đã thống nhất.
3. Tạo `DatabaseConnectionSettings` với các field đã được chuẩn hóa và chỉ đưa kiểu này vào lớp cấu hình datasource.
4. Giải thích vì sao `toString()` của DTO không nên hiển thị `password`.

### Bài tập 2 — Phân biệt lỗi đọc và lỗi dữ liệu

Với `PaymentVaultReader` ở mục 4, mô tả hành vi cho ba trường hợp: (a) secret không tồn tại, (b) workload bị policy từ chối, (c) `retry.maxAttempts` có kiểu JSON object thay vì number. Xác định trường hợp nào xảy ra trước khi ánh xạ DTO và trường hợp nào cần kiểm tra sau khi DTO được tạo.

**Gợi ý:** Không có dữ liệu cần được kiểm tra sau lời gọi đọc; từ chối quyền là lỗi truy cập; kiểu JSON sai có thể bị bộ chuyển đổi từ chối, hoặc trở thành trạng thái DTO không hợp lệ cần validator bắt lại.

### Bài tập 3 — Nâng cấp schema

Secret hiện tại có `timeoutSeconds`. Hệ thống mới muốn lưu `timeoutMillis` và hỗ trợ song song hai phiên bản trong một khoảng chuyển tiếp. Hãy đề xuất:

- Cách xác định trường nào được ưu tiên khi cả hai cùng xuất hiện.
- Cách chuyển sang một kiểu `Duration` duy nhất cho mã nghiệp vụ.
- Điều kiện để phát hiện cấu hình mâu thuẫn hoặc thiếu cả hai trường.
- Kế hoạch cập nhật bên ghi và bên đọc, thêm kiểm thử và gỡ tương thích cũ.

Không sử dụng metadata phiên bản KV v2 làm đại diện duy nhất cho phiên bản schema nếu ứng dụng chưa thiết kế hợp đồng đó.

## 12. Ghi nhớ

1. `Map<String, Object>` hữu ích tại ranh giới dữ liệu động; **DTO có kiểu** phù hợp khi schema secret ổn định và được nhiều thành phần sử dụng.
2. `VaultResponseSupport<T>` vẫn là **phản hồi Vault**, còn `T` là phần dữ liệu nghiệp vụ được ánh xạ; không truyền metadata lease/auth xuyên tầng nghiệp vụ nếu không cần.
3. Với KV v2, `VaultKeyValueOperations.get(path, DTO.class)` cho phép đọc path logic và ánh xạ dữ liệu nghiệp vụ mà không tự bóc `data.data` của phản hồi HTTP thô.
4. DTO chỉ xác nhận cấu trúc có thể deserialize; **validation** mới xác định dữ liệu có phù hợp yêu cầu nghiệp vụ hay không.
5. Một adapter đọc Vault và trả cấu hình đã kiểm tra giúp giảm lỗi ép kiểu, cô lập thay đổi schema, kiểm thử độc lập và bảo vệ secrets.
6. Tách biệt hoàn toàn dữ liệu nghiệp vụ với quyền truy cập, token/lease, rotation, giám sát và các cơ chế Transit/PKI; việc đổi sang DTO không tự giải quyết các quy trình đó.

## Tài liệu đối chiếu

- [Spring Vault — `VaultKeyValueOperations` API](https://docs.spring.io/spring-vault/docs/current/api/org/springframework/vault/core/VaultKeyValueOperations.html): phương thức đọc KV với `Class<T>`.
- [Spring Vault — `VaultResponseSupport<T>` API](https://docs.spring.io/spring-vault/docs/current/api/org/springframework/vault/support/VaultResponseSupport.html): dữ liệu có kiểu và thông tin phản hồi.
- [Spring Vault — Vault Secrets Engines](https://docs.spring.io/spring-vault/reference/vault/vault-secret-engines.html): thao tác KV v1/KV v2 và API mức cao.
- [HashiCorp Vault — KV v2 API](https://developer.hashicorp.com/vault/api-docs/secret/kv/kv-v2): lớp `data` và `metadata` trong kết quả KV v2.
