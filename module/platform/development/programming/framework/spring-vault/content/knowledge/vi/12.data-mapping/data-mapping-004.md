# Quy ước tên thuộc tính và cấu hình bộ chuyển đổi JSON

## Mục tiêu bài học

Trong Spring Vault, một secret đọc từ HashiCorp Vault thường đi qua JSON trước khi trở thành đối tượng Java. JSON có thể sử dụng các tên như `api_key` hoặc `retry-policy`, trong khi mã Java quen dùng `apiKey` và `retryPolicy`. Nếu không thống nhất quy ước hoặc cấu hình ánh xạ đúng cách, trường dữ liệu có thể thành `null`, bị bỏ qua hoặc làm bước chuyển đổi thất bại. Với API key, mật khẩu hoặc cấu hình bảo mật, các sai lệch như vậy cần được phát hiện rõ ràng.

Đây là bài thuộc chương **Ánh xạ dữ liệu** của module **SPRING_VAULT**. Sau khi học, bạn có thể:

1. Phân biệt tên trường JSON, tên thuộc tính Java, path secret và metadata của Vault.
2. Chọn quy ước tên ổn định cho KV secrets và ánh xạ chính xác khi Java và JSON sử dụng phong cách khác nhau.
3. Dùng Jackson `@JsonProperty`, `@JsonAlias` hoặc `@JsonNaming` cho DTO, biết khi nào chúng tác động đến đọc và ghi.
4. Hiểu phạm vi của `ObjectMapper`, bộ chuyển đổi HTTP của Spring Vault và `VaultConverter` trong Vault Repository.
5. Kiểm tra cả tên thuộc tính, kiểu dữ liệu, giá trị thiếu hoặc null, nested object và collection khi đọc KV v2.
6. Thiết kế kiểm thử và quy trình thay đổi schema mà không làm lộ secrets hoặc mất dữ liệu không chủ ý.

> **Bối cảnh:** Ứng dụng Java được giả định đã có `VaultOperations`/`VaultTemplate` được cấu hình, xác thực theo workload và Vault policy cho phép đọc path cần thiết. Các nội dung về token/lease, Transit encryption, PKI, xử lý lỗi, giám sát và kiểm thử tích hợp vẫn là một phần của quá trình học Spring Vault; ở bài này chúng chỉ được nhắc đến khi ảnh hưởng đến việc đọc và ánh xạ JSON.

## 1. Có ba loại tên khác nhau: path Vault, key JSON, property Java

Giả sử KV v2 được mount ở `secret` và secret ứng dụng lưu ở đường dẫn logic `payment/gateway`. Phần dữ liệu nghiệp vụ có dạng:

```json
{
  "client_id": "checkout-service",
  "api_key": "<gia-tri-bi-mat>",
  "connect_timeout_seconds": 15,
  "enabled": true,
  "retry_policy": {
    "max_attempts": 3,
    "backoff_millis": 250
  },
  "allowed_regions": ["ap-southeast-1", "eu-west-1"]
}
```

Tên của ba thành phần có ý nghĩa riêng:

| Thành phần | Ví dụ | Ý nghĩa |
|---|---|---|
| KV mount | `secret` | Vị trí gắn secrets engine trong Vault |
| Path logic của secret | `payment/gateway` | Định danh bản ghi secret tương đối với mount |
| Key JSON | `connect_timeout_seconds` | Thuộc tính trong dữ liệu nghiệp vụ |
| Thuộc tính Java | `connectTimeoutSeconds` | Tên thành viên của DTO trong Java |
| Metadata phiên bản KV v2 | `metadata.version` | Phiên bản lưu trữ của secret; không phải một key nghiệp vụ tương ứng |

Với API KV v2 mức cao của Spring Vault:

```java
VaultKeyValueOperations kv = vaultOperations.opsForKeyValue(
        "secret", KeyValueBackend.KV_2);

VaultResponseSupport<GatewaySecretDto> response =
        kv.get("payment/gateway", GatewaySecretDto.class);
```

Spring Vault sẽ sử dụng mount và path tương ứng với engine. **Quy tắc đổi `snake_case` thành `camelCase` chỉ liên quan đến tên trường trong dữ liệu JSON và thuộc tính DTO; nó không tự đổi `payment/gateway`, không đổi tên mount và không sửa policy Vault.**

Nếu gọi endpoint KV v2 trực tiếp bằng `vaultOperations.read("secret/data/payment/gateway")`, phản hồi JSON có thể lồng theo `data.data`; khi dùng `opsForKeyValue("secret", KV_2).get(...)`, Spring Vault xử lý lớp bao của KV v2 và hướng đến dữ liệu nghiệp vụ.

## 2. Các quy ước đặt tên thường gặp

| Phong cách | Ví dụ | Bối cảnh thường gặp |
|---|---|---|
| `camelCase` | `connectTimeoutSeconds` | Tên field, getter và setter trong Java |
| `snake_case` | `connect_timeout_seconds` | Key trong một số JSON API, dữ liệu cấu hình |
| `kebab-case` | `connect-timeout-seconds` | Key cấu hình hoặc API có dấu gạch nối; không phải identifier Java |
| `PascalCase` | `ConnectTimeoutSeconds` | Tên lớp hoặc schema riêng; không nên suy từ `camelCase` |
| `SCREAMING_SNAKE_CASE` | `CONNECT_TIMEOUT_SECONDS` | Tên hằng hoặc biến môi trường; khi xuất hiện trong JSON cần quy ước rõ |
| Tên có dấu chấm | `database.url` | **Một key literal** trong JSON object, trừ khi API quy định cú pháp path |
| Object lồng nhau | `"database": {"url": "..."}` | Hai cấp JSON, khác hoàn toàn với key `"database.url"` |

Ví dụ hai JSON sau không tương đương:

```json
{
  "database.url": "jdbc:postgresql://db.internal.example:5432/app"
}
```

```json
{
  "database": {
    "url": "jdbc:postgresql://db.internal.example:5432/app"
  }
}
```

Trường hợp đầu là một key literal tên `database.url`; trường hợp sau là object `database` chứa thuộc tính `url`. Một naming strategy thông thường không biến tự động cả hai cấu trúc thành cùng một DTO. Muốn thay đổi độ sâu của object phải viết DTO/mapper phù hợp.

### 2.1. Quy ước phải đi cùng hợp đồng dữ liệu

Một hợp đồng KV secret có thể quy định:

- Keys lưu trong Vault dùng `snake_case`, chữ thường, không chứa thông tin định danh bí mật trong tên.
- DTO Java dùng `camelCase` theo quy ước Java.
- Nested object được định nghĩa rõ trong schema và được ánh xạ bằng DTO lồng nhau.
- Key của cấu hình quan trọng như `api_key` là bắt buộc; trường tùy chọn phải nêu rõ giá trị mặc định.
- Thay tên key cần quy trình chuyển đổi có kiểm thử, thay vì đổi trực tiếp rồi giả định client sẽ tự tương thích.

**Không nên kết hợp nhiều kiểu đặt tên tùy hứng** trong một secret, ví dụ `api_key`, `connectionTimeout` và `retry-policy`, trừ khi có lý do và quy tắc ánh xạ tường minh.

## 3. Đọc JSON vào DTO: vì sao tên trường rất quan trọng?

Khi đọc dữ liệu chưa định kiểu, `VaultResponse.getData()` thường là `Map<String, Object>`. Trong `Map`, khóa giữ nguyên chuỗi từ dữ liệu nguồn:

```java
Map<String, Object> data = response.getRequiredData();
Object timeout = data.get("connect_timeout_seconds"); // Có giá trị khi key tồn tại.
Object wrong = data.get("connectTimeoutSeconds");      // Có thể là null.
```

**Không có chuyện `Map.get()` tự áp dụng quy tắc Jackson**. Naming strategy tác động khi bộ ánh xạ chuyển dữ liệu sang DTO hoặc serialize DTO, không làm biến đổi tên key của `Map` đã nhận được.

Với DTO:

```java
public class GatewaySecretDto {
    private String apiKey;
    private Integer connectTimeoutSeconds;

    // Constructors, getters, setters...
}
```

Nếu JSON dùng `api_key` nhưng converter chỉ nhận `apiKey`, thuộc tính `apiKey` có thể không được gán; kết quả chính xác còn tùy cách xử lý unknown fields và cấu hình của bộ chuyển đổi. Một số cấu hình ném lỗi khi gặp key không biết, số khác bỏ qua. **Không được cho rằng đọc thành DTO thành công nghĩa là mọi field bắt buộc đều được gán.**

Giải pháp gồm ba mức:

1. Đặt tên JSON trùng với property Java khi có thể kiểm soát schema.
2. Chỉ định tên ngoài bằng annotation cho từng property hoặc cho toàn DTO.
3. Cấu hình một naming strategy/converter nhất quán tại nơi client Vault thực sự deserialize JSON; sau đó vẫn kiểm tra dữ liệu nghiệp vụ.

## 4. Cách 1 — Ánh xạ từng trường bằng `@JsonProperty`

Khi một schema đã tồn tại hoặc chứa các tên khác quy ước chung, annotation `@JsonProperty` của Jackson 2.x cho phép chỉ định **tên JSON chính xác**. Ví dụ DTO dạng JavaBean:

```java
import com.fasterxml.jackson.annotation.JsonProperty;
import java.util.List;

public class GatewaySecretDto {

    @JsonProperty("client_id")
    private String clientId;

    @JsonProperty("api_key")
    private String apiKey;

    @JsonProperty("connect_timeout_seconds")
    private Integer connectTimeoutSeconds;

    @JsonProperty("enabled")
    private Boolean enabled;

    @JsonProperty("retry_policy")
    private RetryPolicyDto retryPolicy;

    @JsonProperty("allowed_regions")
    private List<String> allowedRegions;

    public GatewaySecretDto() {
    }

    public String getClientId() {
        return clientId;
    }
    public void setClientId(String clientId) {
        this.clientId = clientId;
    }

    public String getApiKey() {
        return apiKey;
    }
    public void setApiKey(String apiKey) {
        this.apiKey = apiKey;
    }

    public Integer getConnectTimeoutSeconds() {
        return connectTimeoutSeconds;
    }
    public void setConnectTimeoutSeconds(Integer connectTimeoutSeconds) {
        this.connectTimeoutSeconds = connectTimeoutSeconds;
    }

    public Boolean getEnabled() {
        return enabled;
    }
    public void setEnabled(Boolean enabled) {
        this.enabled = enabled;
    }

    public RetryPolicyDto getRetryPolicy() {
        return retryPolicy;
    }
    public void setRetryPolicy(RetryPolicyDto retryPolicy) {
        this.retryPolicy = retryPolicy;
    }

    public List<String> getAllowedRegions() {
        return allowedRegions;
    }
    public void setAllowedRegions(List<String> allowedRegions) {
        this.allowedRegions = allowedRegions;
    }

    public static class RetryPolicyDto {
        @JsonProperty("max_attempts")
        private Integer maxAttempts;

        @JsonProperty("backoff_millis")
        private Integer backoffMillis;

        public RetryPolicyDto() {
        }

        public Integer getMaxAttempts() {
            return maxAttempts;
        }
        public void setMaxAttempts(Integer maxAttempts) {
            this.maxAttempts = maxAttempts;
        }

        public Integer getBackoffMillis() {
            return backoffMillis;
        }
        public void setBackoffMillis(Integer backoffMillis) {
            this.backoffMillis = backoffMillis;
        }
    }
}
```

Với bộ chuyển đổi Jackson 2.x có nhận diện annotation, `@JsonProperty("api_key")` ánh xạ giữa JSON `api_key` và thuộc tính Java `apiKey`. Quy tắc này áp dụng cho cả đọc và ghi JSON theo hành vi thông thường của Jackson; nó không tự thay đổi bản ghi đã lưu trong Vault.

**Ưu điểm:** rõ ràng, hợp với schema có một số ngoại lệ hoặc tên key chứa dấu gạch nối. **Hạn chế:** nhiều annotation lặp lại nếu hầu hết tên key đều là `snake_case`. Vì vậy nên cân nhắc `@JsonNaming` ở mục tiếp theo.

> **Lưu ý về dữ liệu nhạy cảm:** Không dùng `dto.toString()`, serializer hoặc debugger dump trong log vì DTO có trường `apiKey`. Annotation ánh xạ tên không phải cơ chế che secrets.

## 5. Cách 2 — Áp dụng `@JsonNaming` cho toàn bộ DTO

Nếu JSON dùng `snake_case` một cách nhất quán, có thể khai báo chiến lược cho class bằng `@JsonNaming` (Jackson 2.x):

```java
import com.fasterxml.jackson.databind.PropertyNamingStrategies;
import com.fasterxml.jackson.databind.annotation.JsonNaming;
import java.util.List;

@JsonNaming(PropertyNamingStrategies.SnakeCaseStrategy.class)
public class GatewaySecret {
    public String clientId;
    public String apiKey;
    public Integer connectTimeoutSeconds;
    public Boolean enabled;
    public Retry retryPolicy;
    public List<String> allowedRegions;

    // DTO dùng public field để rút gọn ví dụ; mã thực tế có thể dùng JavaBean.
    public GatewaySecret() {
    }

    @JsonNaming(PropertyNamingStrategies.SnakeCaseStrategy.class)
    public static class Retry {
        public Integer maxAttempts;
        public Integer backoffMillis;
    }
}
```

Với mapper áp dụng annotation, các cặp tên tương ứng là:

| Thuộc tính Java | Tên JSON |
|---|---|
| `clientId` | `client_id` |
| `apiKey` | `api_key` |
| `connectTimeoutSeconds` | `connect_timeout_seconds` |
| `retryPolicy` | `retry_policy` |
| `retryPolicy.maxAttempts` | `retry_policy.max_attempts` (*đường dẫn mô tả hai cấp*) |
| `allowedRegions` | `allowed_regions` |

Ở hàng `retryPolicy.maxAttempts`, tên JSON thực là hai key lồng nhau: `retry_policy` và `max_attempts`. **Không** có một key literal tên `retry_policy.max_attempts` trong JSON ví dụ.

**Đừng quên class lồng nhau.** Annotation đặt trên `GatewaySecret` không đồng nghĩa chiến lược đó được tự động áp dụng cho mọi class bên trong; nếu dùng DTO lồng nhau như `Retry`, hãy khai báo cho class đó hoặc cấu hình naming strategy tại mapper được sử dụng.

So với `@JsonProperty`:

- `@JsonNaming` phù hợp khi gần như mọi property đều có cùng quy tắc đổi tên.
- `@JsonProperty` phù hợp cho các ngoại lệ như key `client-id`, `x509_certificate` hoặc tên legacy không thể suy từ quy tắc.
- Có thể kết hợp cả hai để ngoại lệ được mô tả rõ; nên kiểm thử trường hợp annotation ghi đè naming strategy.

Ví dụ xử lý tên ngoại lệ:

```java
@JsonProperty("client-id")
private String clientId;
```

Đây là key `client-id` có dấu gạch nối; `SNAKE_CASE` thông thường không tạo tên này từ `clientId`.

## 6. Cách 3 — `@JsonAlias` khi đổi tên schema

Một secret cũ lưu `timeout_seconds`. Phiên bản mới muốn chuẩn hóa thành `connect_timeout_seconds`. Trong thời gian chuyển tiếp, DTO có thể chấp nhận cả hai dạng khi **đọc**:

```java
import com.fasterxml.jackson.annotation.JsonAlias;
import com.fasterxml.jackson.annotation.JsonProperty;

public class TimeoutDto {

    @JsonProperty("connect_timeout_seconds")
    @JsonAlias({"timeout_seconds"})
    private Integer connectTimeoutSeconds;

    public TimeoutDto() {
    }

    public Integer getConnectTimeoutSeconds() {
        return connectTimeoutSeconds;
    }
    public void setConnectTimeoutSeconds(Integer value) {
        this.connectTimeoutSeconds = value;
    }
}
```

`@JsonAlias` nhận các tên thay thế khi **deserialize**; khi serialize DTO, Jackson sử dụng tên chính `connect_timeout_seconds` theo `@JsonProperty`. Alias không tự viết lại secret đang lưu và không giải quyết vòng đời migration.

Lưu ý quan trọng: nếu JSON chứa **cả** `timeout_seconds` và `connect_timeout_seconds`, không nên dựa vào thứ tự xử lý field để quyết định giá trị cuối cùng. Hãy đặt quy tắc chuyển đổi tường minh (chẳng hạn cấm xuất hiện đồng thời hoặc ưu tiên một trường và cảnh báo khi mâu thuẫn), rồi kiểm tra dữ liệu **trước** khi các alias bị gộp thành một property.

Ví dụ có thể kiểm tra sự xuất hiện của key ở mức `Map`:

```java
boolean oldPresent = rawData.containsKey("timeout_seconds");
boolean newPresent = rawData.containsKey("connect_timeout_seconds");

if (oldPresent && newPresent) {
    throw new IllegalArgumentException(
            "Secret chứa đồng thời hai tên timeout không được phép");
}
```

Trong đoạn trên, `rawData` là map chứa **phần dữ liệu nghiệp vụ**, không phải `data` bao ngoài của endpoint KV v2. Chỉ cần cách kiểm tra này khi hợp đồng nghiệp vụ đòi phát hiện hai tên trùng nghĩa; nếu schema đã được cập nhật đồng loạt, sử dụng một tên chuẩn thường đơn giản hơn.

## 7. Cấu hình `ObjectMapper` và bộ chuyển đổi JSON

Với Jackson, có hai vị trí thường gặp để đặt quy tắc:

1. **Tại DTO:** dùng `@JsonProperty`, `@JsonAlias` hoặc `@JsonNaming`. Quy tắc đi theo kiểu DTO và được mapper hỗ trợ annotation áp dụng.
2. **Tại bộ chuyển đổi:** cấu hình `ObjectMapper` để mọi kiểu được xử lý bởi chính mapper đó dùng chung naming strategy, định dạng ngày giờ và cách xử lý trường lạ.

### 7.1. Ví dụ cấu hình Jackson 2.x một cách độc lập

```java
import com.fasterxml.jackson.databind.DeserializationFeature;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.PropertyNamingStrategies;

ObjectMapper vaultMapper = new ObjectMapper();
vaultMapper.setPropertyNamingStrategy(PropertyNamingStrategies.SNAKE_CASE);
vaultMapper.configure(
        DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES, true);
```

Với mapper trên, class JavaBean có property `apiKey` sẽ tìm key `api_key`. Cài đặt `FAIL_ON_UNKNOWN_PROPERTIES` là **một lựa chọn hợp đồng**: khi bật, JSON có key lạ sẽ bị từ chối nếu không được xử lý bằng annotation hoặc cơ chế khác. Khi tắt, những key lạ có thể bị bỏ qua. Việc chọn strict hay tolerant phải dựa vào yêu cầu tương thích:

| Tình huống | Strict (từ chối key không biết) | Tolerant (bỏ qua key mới) |
|---|---|---|
| Secret chứa giá trị có tác động đến bảo mật | Giúp phát hiện lỗi chính tả hoặc key bị thêm sai | Có nguy cơ làm key quan trọng bị bỏ qua |
| Nhiều phiên bản ứng dụng cùng đọc một secret | Có thể gây lỗi khi schema được mở rộng | Dễ hỗ trợ thêm trường tùy chọn |
| Cần phát hiện migration dở dang | Dễ phát hiện dữ liệu lệch schema | Cần validator/giám sát bổ sung |

Không có lựa chọn nào thay thế validation của các field bắt buộc. Ví dụ, bật `FAIL_ON_UNKNOWN_PROPERTIES` không có nghĩa mapper tự ném lỗi nếu `api_key` vắng mặt trong JSON; DTO vẫn có thể chứa `null`.

### 7.2. Chỉ cấu hình mapper riêng chưa đủ để đổi cách Spring Vault đọc

Đây là chỗ dễ hiểu sai nhất:

```java
ObjectMapper vaultMapper = new ObjectMapper();
vaultMapper.setPropertyNamingStrategy(PropertyNamingStrategies.SNAKE_CASE);

// Việc tạo biến vaultMapper ở đây không tự làm
// VaultTemplate hoặc VaultClient sử dụng chính instance này.
```

Spring Vault sử dụng hạ tầng HTTP/JSON tương ứng với phiên bản để thực hiện chuyển đổi. Trong những phiên bản dùng Spring Web `RestTemplate`, Jackson có thể được đưa vào bằng `MappingJackson2HttpMessageConverter`; các phiên bản mới hỗ trợ `RestClient`/`VaultClient` và có cơ chế cấu hình converter riêng. Spring Vault 4.1 còn hỗ trợ Jackson 3 khi phù hợp classpath, bên cạnh Jackson 2. Vì thế, API xây dựng client và package import có thể khác nhau giữa các dòng phiên bản.

Ví dụ **tạo một HTTP message converter cho Jackson 2.x**, chưa phải cấu hình hoàn chỉnh của Vault client:

```java
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.http.converter.json.MappingJackson2HttpMessageConverter;

MappingJackson2HttpMessageConverter jsonConverter =
        new MappingJackson2HttpMessageConverter(vaultMapper);

// Cần gắn converter này vào HTTP client thực sự được VaultOperations dùng
// theo API cấu hình của đúng phiên bản Spring Vault trong dự án.
```

Để cấu hình an toàn trong dự án thực tế:

1. Xác định **phiên bản Spring Vault, Spring Framework và Jackson** đang dùng.
2. Xác định `VaultOperations`/`VaultTemplate` thực sự sử dụng HTTP client và message converter nào; nếu ứng dụng có nhiều client, đừng giả định mapper của MVC hoặc một bean `ObjectMapper` sẽ tự động được chia sẻ.
3. Cấu hình đúng mapper/converter được client Vault sử dụng theo API chính thức của **phiên bản đó**.
4. Chạy kiểm thử tích hợp trên `kv.get("payment/gateway", GatewaySecretDto.class)` với JSON snake_case và các field lồng nhau.
5. Tránh thay naming strategy trên một mapper đã được các thread sử dụng; hãy cấu hình trước khi client bắt đầu xử lý yêu cầu.

Nếu chỉ một loại DTO cần đọc `snake_case`, `@JsonNaming` tại class thường giúp phạm vi thay đổi rõ ràng hơn thay vì sửa converter dùng chung cho toàn ứng dụng.

### 7.3. DTO có annotation khác với `VaultConverter` của Vault Repository

Spring Vault có **hai cơ chế ánh xạ phục vụ các tầng khác nhau**:

| Cơ chế | Nơi sử dụng | Cách tùy biến tiêu biểu |
|---|---|---|
| Jackson/HTTP JSON mapping | Các lời gọi `VaultOperations`, `VaultKeyValueOperations` và một số API dạng phản hồi | Annotation Jackson; cấu hình mapper và HTTP converter được client thực tế dùng |
| `VaultConverter`/`MappingVaultConverter` | Spring Vault Repository và mapping đối tượng sang `SecretDocument` | Quy tắc mapping của Repository, `VaultCustomConversions` và converter chuyên biệt |

Không nên giả định rằng đăng ký `VaultCustomConversions` cho repository sẽ tự thay đổi việc ánh xạ của `kv.get(path, Dto.class)`. Ngược lại, đổi naming strategy của HTTP mapper không đồng nghĩa mọi repository entity sẽ tự đổi tên field.

Theo tài liệu Spring Vault về repositories, `VaultConverter` có thể ánh xạ nested objects, collections và có cơ chế custom conversions riêng; một số trường hợp còn lưu metadata kiểu như `_class` để tái tạo entity. Đó là hợp đồng lưu trữ của repository, không nên lẫn với metadata phiên bản KV v2 hoặc DTO mà ứng dụng tự đọc qua KV API.

## 8. Bộ chuyển đổi giá trị khác với bộ chuyển đổi **tên**

Tên trường hợp lệ không đảm bảo **kiểu dữ liệu** hợp lệ. JSON không có các kiểu Java `Instant`, `Duration` hoặc enum được bảo đảm mặc định ở mọi bộ chuyển đổi.

### 8.1. Date/time: thống nhất biểu diễn đầu vào

Giả sử JSON có:

```json
{
  "rotated_at": "2026-11-25T07:00:00Z",
  "timeout_seconds": 15
}
```

`rotated_at` là chuỗi JSON theo ISO-8601, còn `timeout_seconds` là JSON number. Có thể:

- Đọc `rotatedAt` vào `String` rồi dùng `Instant.parse(...)` tại ranh giới validation.
- Hoặc ánh xạ thẳng sang `Instant` khi Jackson đã có module/hỗ trợ phù hợp, chẳng hạn `JavaTimeModule` trong Jackson 2.x.
- Chuyển `timeoutSeconds` sang `Duration.ofSeconds(...)` sau khi đã kiểm tra số nguyên và phạm vi.

Ví dụ cấu hình Jackson 2.x dùng thư viện `jackson-datatype-jsr310`:

```java
import com.fasterxml.jackson.datatype.jsr310.JavaTimeModule;

vaultMapper.registerModule(new JavaTimeModule());
```

Module này xử lý các kiểu thời gian theo cách Jackson 2.x hỗ trợ; **không** thay thế việc quyết định định dạng hợp đồng dữ liệu hoặc xử lý timezone ở tầng nghiệp vụ. Module chỉ có tác dụng nếu nó được đăng ký trên mapper thực sự dùng để giải mã.

### 8.2. Boolean, enum và số

| Giá trị trong JSON | Cạm bẫy | Nguyên tắc |
|---|---|---|
| `true` và `"true"` | Boolean khác String; mapper có thể có chế độ ép kiểu | Nêu rõ schema cần Boolean thực, kiểm thử coercion của mapper |
| `15` và `"15"` | Number khác String | Nếu không cho phép chuỗi số, cấu hình/validator phải từ chối |
| `1.25` | Có thể thành floating-point với giới hạn độ chính xác | Dùng cơ chế/kiểu phù hợp khi cần độ chính xác thập phân |
| `"PRIMARY"` | Enum có thể phụ thuộc chính tả và chữ hoa/thường | Định nghĩa rõ giá trị hợp lệ hoặc converter có chủ đích |
| `null` và thiếu key | Cả hai có thể thành `null` trên DTO | Xác định trường bắt buộc và phân biệt khi nghiệp vụ cần |

Ví dụ validation sau deserialize:

```java
GatewaySecretDto dto = response.getRequiredData();

if (dto.getApiKey() == null || dto.getApiKey().isBlank()) {
    throw new IllegalStateException("Thiếu trường api_key bắt buộc");
}

Integer timeout = dto.getConnectTimeoutSeconds();
if (timeout == null || timeout < 1 || timeout > 120) {
    throw new IllegalStateException(
            "connect_timeout_seconds phải trong khoảng 1..120");
}

if (dto.getRetryPolicy() == null
        || dto.getRetryPolicy().getMaxAttempts() == null
        || dto.getRetryPolicy().getMaxAttempts() < 1) {
    throw new IllegalStateException("retry_policy.max_attempts không hợp lệ");
}
```

Không dùng `String.valueOf(dto.getApiKey())` để xử lý thiếu key: nó biến `null` thành chuỗi `"null"` và che khuất dữ liệu sai.

## 9. Ví dụ tích hợp: đọc KV v2 với DTO có naming strategy

Ví dụ Java 17+ dưới đây minh họa **đường đi qua Spring Vault**. Để tránh lặp toàn bộ getter/setter, dùng class `GatewaySecret` có `@JsonNaming` ở mục 5 (trong dự án thực tế, nên dùng JavaBean với private fields hoặc DTO bất biến đã được kiểm thử).

```java
import org.springframework.vault.core.VaultKeyValueOperations;
import org.springframework.vault.core.VaultOperations;
import org.springframework.vault.core.VaultKeyValueOperationsSupport.KeyValueBackend;
import org.springframework.vault.support.VaultResponseSupport;

public final class GatewaySecretReader {

    private final VaultKeyValueOperations kv;

    public GatewaySecretReader(VaultOperations vaultOperations) {
        this.kv = vaultOperations.opsForKeyValue(
                "secret", KeyValueBackend.KV_2);
    }

    public GatewaySecret load() {
        VaultResponseSupport<GatewaySecret> response =
                kv.get("payment/gateway", GatewaySecret.class);

        if (response == null || response.getData() == null) {
            throw new IllegalStateException(
                    "Không tìm thấy secret payment/gateway");
        }

        GatewaySecret secret = response.getRequiredData();
        validate(secret);
        return secret;
    }

    private static void validate(GatewaySecret s) {
        if (s.apiKey == null || s.apiKey.isBlank()) {
            throw new IllegalStateException("api_key không được rỗng");
        }
        if (s.clientId == null || s.clientId.isBlank()) {
            throw new IllegalStateException("client_id không được rỗng");
        }
        if (s.connectTimeoutSeconds == null
                || s.connectTimeoutSeconds < 1
                || s.connectTimeoutSeconds > 120) {
            throw new IllegalStateException(
                    "connect_timeout_seconds ngoài phạm vi");
        }
        if (s.retryPolicy == null
                || s.retryPolicy.maxAttempts == null
                || s.retryPolicy.maxAttempts < 1) {
            throw new IllegalStateException(
                    "retry_policy.max_attempts không hợp lệ");
        }
        if (s.allowedRegions == null || s.allowedRegions.isEmpty()) {
            throw new IllegalStateException("allowed_regions không được rỗng");
        }
        for (int i = 0; i < s.allowedRegions.size(); i++) {
            String value = s.allowedRegions.get(i);
            if (value == null || value.isBlank()) {
                throw new IllegalStateException(
                        "allowed_regions[" + i + "] không hợp lệ");
            }
        }
    }
}
```

Một số điểm cần giữ đúng:

1. `get("payment/gateway", GatewaySecret.class)` trả về `VaultResponseSupport<GatewaySecret>` hoặc `null` khi không tìm thấy path; kiểm tra response trước khi truy cập `getData()`.
2. DTO chỉ thể hiện các trường nghiệp vụ. Request ID, auth metadata, lease ID và thời lượng lease thuộc lớp phản hồi/Vault operation tương ứng.
3. Khi có lỗi mapping, việc xử lý phải phân biệt với lỗi 403 do policy, lỗi workload authentication hoặc lỗi mạng. Không thay tất cả thành một DTO rỗng để tiếp tục chạy.
4. `@JsonNaming` phát huy tác dụng khi bộ chuyển đổi thực tế của client dùng Jackson và hỗ trợ annotation đó; kiểm thử tích hợp là cách xác nhận trong phiên bản Spring Vault đang chạy.
5. Ví dụ không giữ hoặc in giá trị secret trong log. Sau validation, có thể chuyển DTO thành một cấu hình bất biến dành riêng cho client thanh toán; không truyền DTO có mutable fields xuyên mọi tầng ứng dụng.

## 10. Kiểm thử: chứng minh tên JSON đã được ánh xạ đúng

### 10.1. Unit test ánh xạ của Jackson

Đây là phép thử nhanh **không cần Vault**, xác nhận một mapper Jackson 2.x có nhận diện `@JsonNaming`:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;

import com.fasterxml.jackson.databind.DeserializationFeature;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;

class GatewaySecretJsonTest {

    private final ObjectMapper mapper = new ObjectMapper()
            .configure(
                    DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES, true);

    @Test
    void mapsSnakeCaseAndNestedObject() throws Exception {
        String body = """
                {
                  "client_id": "checkout-service",
                  "api_key": "test-only-key",
                  "connect_timeout_seconds": 15,
                  "enabled": true,
                  "retry_policy": {"max_attempts": 3, "backoff_millis": 250},
                  "allowed_regions": ["ap-southeast-1"]
                }
                """;

        GatewaySecret dto = mapper.readValue(body, GatewaySecret.class);
        assertEquals("checkout-service", dto.clientId);
        assertEquals(15, dto.connectTimeoutSeconds);
        assertEquals(3, dto.retryPolicy.maxAttempts);
        assertEquals("ap-southeast-1", dto.allowedRegions.get(0));
        assertNotNull(dto.apiKey);
        // Không đưa giá trị apiKey vào log hoặc snapshot.
    }
}
```

Trong đoạn này, `GatewaySecret` là DTO `@JsonNaming` ở mục 5. `FAIL_ON_UNKNOWN_PROPERTIES` giúp phép thử từ chối key ngoài schema; test không khẳng định mapper bên trong Spring Vault đã được cấu hình giống hệt như vậy.

### 10.2. Kiểm thử trường hợp lỗi

| Input JSON | Điều cần quan sát |
|---|---|
| Đổi `api_key` thành `api-key` | Có bị từ chối hoặc làm `apiKey == null` không? Validation phải bắt được |
| Bỏ `connect_timeout_seconds` | DTO có thể có `null`; validator phải từ chối |
| `retry_policy` là chuỗi thay vì object | Mapper phải báo lỗi kiểu hoặc validator phải từ chối |
| Có `retry_policy.max_attempts` với tên literal chứa dấu chấm | Không được nhầm với nested object `retry_policy: {max_attempts: ...}` |
| Có key mới `description` | Kiểm tra strict/tolerant theo hợp đồng |
| Có `"connect_timeout_seconds": "15"` | Kiểm tra tính nhất quán của quy tắc ép kiểu số |
| Có `"enabled": "true"` | Kiểm tra quy tắc ép kiểu Boolean |
| Có hai tên alias cũ và mới cùng tồn tại | Phải phát hiện hoặc xử lý xung đột theo quyết định rõ ràng |
| `allowed_regions` chứa số hoặc `null` | Mapping/validation không được âm thầm chấp nhận phần tử sai |

### 10.3. Kiểm thử tích hợp với Vault

Một unit test của `ObjectMapper` **không đủ** để khẳng định `VaultTemplate` dùng cùng mapper. Kiểm thử tích hợp nên chạy trên Vault thử nghiệm:

1. Tạo mount KV v2 thử nghiệm và một workload identity có policy chỉ đọc path thử nghiệm.
2. Lưu secret với key `snake_case`, nested object và collection chứa **dữ liệu giả**.
3. Dùng đúng `VaultOperations` và client config của ứng dụng thực tế gọi `kv.get(..., GatewaySecret.class)`.
4. Kiểm tra các property camelCase đã được gán đầy đủ; thử thêm một key không biết để xác nhận chính sách strict/tolerant.
5. Thử thiếu key bắt buộc, sai kiểu, không có path, bị 403 và lỗi kết nối; bảo đảm phân loại lỗi rõ ràng.

Tránh in phản hồi thô, DTO hoặc token vào assertion message, snapshot, CI log hoặc APM trace. Nếu cần đo thời gian truy cập hoặc đếm lỗi, chỉ ghi thông tin không nhạy cảm.

## 11. Hướng dẫn thay đổi tên key trong hệ thống đang chạy

Giả sử hệ thống đang lưu `dbPassword`, nhưng chuẩn mới yêu cầu `db_password`. Quy trình thay đổi an toàn:

1. **Khảo sát hợp đồng hiện tại:** ứng dụng nào đang đọc key, có dùng `Map.get(...)` trực tiếp hay DTO; xác định các phiên bản client cần được hỗ trợ.
2. **Chọn tên chuẩn và quy tắc tương thích:** ví dụ chỉ ghi `db_password` sau thời điểm chuyển, trong khi phía đọc tạm nhận thêm `dbPassword` bằng alias.
3. **Triển khai phía đọc tương thích trước:** thêm `@JsonAlias` hoặc adapter kiểm tra hai tên và ràng buộc rõ khi cả hai xuất hiện.
4. **Cập nhật bên ghi và dữ liệu:** ghi theo schema mới, giữ nguyên các trường không liên quan. Với KV v2, cân nhắc semantics của `put` và `patch` trước khi ghi thay vì mặc định mọi API đều chỉ sửa một key.
5. **Quan sát và kiểm thử:** xác nhận mọi workload đọc thành công, log chỉ chứa trạng thái không nhạy cảm; không ghi giá trị secret vào báo cáo migration.
6. **Gỡ tương thích cũ:** sau khi các client cũ kết thúc vòng đời, xóa alias và ràng buộc legacy, khóa schema mới bằng kiểm thử.

Không dùng metadata version của KV v2 làm thay thế duy nhất cho **schema version**. Phiên bản lưu trữ thay đổi mỗi lần ghi, kể cả khi cấu trúc tên key không đổi. Nếu cần, có thể thêm trường `schema_version` vào **dữ liệu nghiệp vụ** cùng quy ước triển khai cụ thể.

## 12. Các lỗi thường gặp và cách chẩn đoán

| Triệu chứng | Nguyên nhân khả dĩ | Hướng kiểm tra |
|---|---|---|
| DTO tạo thành công nhưng `apiKey == null` | JSON lưu `api_key`, mapper không áp dụng annotation/strategy; hoặc key thiếu | Kiểm tra schema, annotation, mapper thực tế, validation |
| Unit test Jackson pass nhưng gọi Vault vẫn sai | Client Vault dùng converter khác hoặc cấu hình không được gắn vào client | Kiểm tra HTTP client do `VaultOperations` sử dụng và thêm integration test |
| Key `retry_policy` ánh xạ được nhưng `maxAttempts == null` | DTO lồng nhau chưa có naming strategy hoặc `@JsonProperty` | Kiểm tra class lồng nhau và JSON thực tế |
| Đổi `ObjectMapper` chung làm controller REST thay đổi ngoài ý muốn | Dùng chung mapper toàn hệ thống | Giới hạn phạm vi converter hoặc dùng annotation tại DTO |
| `@JsonAlias` khiến không biết key nào được dùng | Dữ liệu chứa cả tên cũ và mới | Kiểm tra ở mức Map và đặt quy tắc xử lý xung đột |
| KV v2 đọc raw `VaultResponse.getData()` thấy thêm `data` | Lớp bao của API KV v2 | Dùng `VaultKeyValueOperations` hoặc bóc đúng lớp bao |
| Cấu hình `VaultCustomConversions` không ảnh hưởng typed KV get | Đang tùy biến Repository mapper thay vì HTTP JSON mapper | Phân biệt hai cơ chế và kiểm tra API đang gọi |
| Secret đọc được nhưng client sử dụng credential cũ | DTO đã được giữ trong bộ nhớ trước lần rotation | Thiết kế refresh phù hợp, xem xét lease/token lifecycle |

**Quan trọng:** sai tên field không phải là lỗi 403 do Vault policy; lỗi xác thực/policy cũng không phải lỗi cấu hình Jackson. Khi bắt exception, đừng biến cả hai thành `Map` hoặc DTO rỗng rồi tiếp tục. Việc đổi tên thuộc tính không làm thay đổi chính sách quyền của Vault, thời hạn token hay cách quản lý lease.

## 13. Thực hành

### Bài tập 1 — Chuyển `kebab-case` thành thuộc tính Java

Một KV secret chứa:

```json
{
  "client-id": "billing-service",
  "api-token": "<gia-tri-bi-mat>",
  "retry-limit": 4
}
```

Hãy thiết kế `BillingSecretDto` với các thuộc tính Java `clientId`, `apiToken`, `retryLimit`. Chọn cách áp dụng `@JsonProperty` hoặc một naming strategy tương ứng. Viết validator yêu cầu token không rỗng và retry limit trong khoảng `1..8`. Giải thích tại sao chỉ đổi tên thuộc tính Java không sửa secret đã lưu.

### Bài tập 2 — Nested object và quy ước khác nhau

JSON cho trước:

```json
{
  "database": {
    "jdbc_url": "jdbc:postgresql://db.internal.example:5432/app",
    "pool_settings": {
      "max_size": 12
    }
  }
}
```

Xây dựng `DatabaseSecretDto` gồm `DatabaseDto` và `PoolSettingsDto` sao cho mã nghiệp vụ đọc được `dto.getDatabase().getPoolSettings().getMaxSize()`. Đề xuất nên đặt `@JsonNaming` trên những class nào hoặc cần những `@JsonProperty` nào. Không được hiểu `database.pool_settings.max_size` là một key đơn trong JSON.

### Bài tập 3 — Cấu hình converter và migration

Trong unit test, một `ObjectMapper` có `SNAKE_CASE` đọc đúng `api_key`. Khi chạy qua `VaultTemplate`, `apiKey` vẫn là `null`. Hãy giải thích:

1. Vì sao unit test riêng chưa đủ để khẳng định mapper của Vault đã được cấu hình?
2. Phương án nào có phạm vi nhỏ nhất nếu chỉ một DTO cần dùng `snake_case`?
3. Nếu đổi tên `api_key` thành `secret_key`, cần kiểm tra hành vi gì khi cả hai cùng tồn tại?
4. Những dữ liệu nào tuyệt đối không nên ghi ra log khi chẩn đoán?

**Gợi ý đáp án:** (1) HTTP client Vault có thể đang dùng converter khác; (2) `@JsonProperty` hoặc `@JsonNaming` trên DTO phù hợp; (3) chính sách ưu tiên, mâu thuẫn và thời gian tương thích; (4) payload secret, token, password, khóa riêng, toàn bộ DTO/Map hoặc exception chứa giá trị nhạy cảm.

## 14. Những điểm cần ghi nhớ

- Path Vault, tên key JSON và thuộc tính Java là **ba lớp khái niệm độc lập**. Naming strategy chỉ xử lý ánh xạ tên ở tầng dữ liệu.
- Với schema ổn định, DTO có kiểu giúp mã Java rõ ràng và dễ kiểm thử hơn truyền `Map<String, Object>` qua nhiều tầng.
- `@JsonProperty` dùng cho tên JSON cụ thể; `@JsonNaming` cho một quy ước chung; `@JsonAlias` giúp nhận tên cũ khi **đọc** trong giai đoạn chuyển đổi.
- `ObjectMapper` riêng không tự điều chỉnh `VaultTemplate`; cần gắn đúng converter/client theo phiên bản hoặc ưu tiên annotation tại DTO khi đủ dùng.
- `VaultCustomConversions` phục vụ cơ chế mapping của Vault Repository, không nên coi là cấu hình thay thế cho mọi lời gọi typed KV get.
- Vẫn phải kiểm tra field bắt buộc, nested object, collection, giới hạn số và unknown fields; ánh xạ thành công không chứng minh cấu hình an toàn.
- Không log secrets trong quá trình chẩn đoán lỗi mapping, xác thực, policy hay rotation.

## Tài liệu tham khảo

- [Spring Vault — Introduction to VaultTemplate](https://docs.spring.io/spring-vault/reference/vault/imperative-template.html): `VaultOperations` và hạ tầng ánh xạ dữ liệu.
- [Spring Vault — `VaultKeyValueOperations` API](https://docs.spring.io/spring-vault/reference/api/java/org/springframework/vault/core/VaultKeyValueOperations.html): đọc secret theo path và kiểu `Class<T>`.
- [Spring Vault — Vault Repositories / Object to Vault JSON Mapping](https://docs.spring.io/spring-vault/reference/vault/vault-repositories.html): `VaultConverter`, `SecretDocument` và `VaultCustomConversions`.
- [Spring Vault — `VaultClients` API](https://docs.spring.io/spring-vault/reference/api/java/org/springframework/vault/client/VaultClients.html): cấu hình HTTP client và JSON converters theo phiên bản.
- [Jackson — Annotations](https://github.com/FasterXML/jackson-annotations/wiki/Jackson-Annotations): cơ chế `@JsonProperty` và `@JsonAlias` (theo phiên bản Jackson tương ứng).
- [HashiCorp Vault — KV v2 API](https://developer.hashicorp.com/vault/api-docs/secret/kv/kv-v2): đường dẫn và các lớp `data`/`metadata` trong phản hồi KV v2.
