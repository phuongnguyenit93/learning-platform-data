# Versioned và việc giữ metadata tách khỏi giá trị

## Mục tiêu bài học

Với HashiCorp Vault KV v2, mỗi lần ghi secret có thể tạo một **phiên bản lưu trữ** mới. Ứng dụng Java dùng **Spring Vault** không chỉ cần lấy được các trường nghiệp vụ như `api_key` hoặc `jdbc_url`; đôi khi nó còn cần biết dữ liệu thuộc phiên bản nào, được tạo khi nào, có bị đánh dấu xóa hay không, hoặc cần bảo vệ thao tác cập nhật trước các bản ghi cạnh tranh.

Spring Vault cung cấp kiểu `Versioned<T>` và API `VaultVersionedKeyValueOperations` để mô hình hóa trường hợp này. Mấu chốt là **giữ phần giá trị `T` tách khỏi version và metadata**: credential của ứng dụng không phải metadata của Vault, còn số phiên bản lưu trữ không phải thuộc tính nghiệp vụ của một credential.

Sau bài học, bạn có thể:

1. Phân biệt KV v1 và KV v2 về phiên bản, đồng thời nhận biết những lớp `data`/`metadata` trong JSON của KV v2.
2. Giải thích vai trò của `Versioned<T>`, `VaultVersionedKeyValueOperations` và sự khác nhau với `VaultResponse`/`VaultResponseSupport<T>`.
3. Đọc secret KV v2 theo kiểu có phiên bản, lấy riêng giá trị nghiệp vụ, phiên bản và metadata khi cần.
4. Xác định ranh giới DTO: các trường cần để chạy ứng dụng thuộc giá trị `T`, thông tin version thuộc lớp quản lý trạng thái/nguồn dữ liệu.
5. Phân biệt **KV storage version**, **schema version**, **thời điểm tạo dữ liệu** và **thời hạn lease/token**.
6. Hiểu cách version hỗ trợ kiểm tra cạnh tranh ghi (*compare-and-set*, CAS), kiểm thử, giám sát và chẩn đoán lỗi mà không lộ secrets.

> **Bối cảnh:** Bài thuộc chương **Ánh xạ dữ liệu** của module **SPRING_VAULT**. Module hướng đến ứng dụng Java truy cập HashiCorp Vault qua `VaultTemplate`/`VaultOperations`, xác thực theo workload và giới hạn quyền bằng Vault policy, đồng thời thực hành KV secrets, vòng đời token/lease, Transit encryption, PKI, xử lý lỗi, giám sát và kiểm thử tích hợp. Ví dụ ở đây giả định kết nối, workload authentication và quyền đọc KV đã được thiết lập; nội dung tập trung vào cách ánh xạ dữ liệu và metadata phiên bản.

## 1. Vì sao cần quan tâm đến phiên bản khi đọc secrets?

Giả sử một ứng dụng thanh toán lưu tại KV v2 mount `secret`, path logic `payments/gateway`:

```json
{
  "api_key": "<gia-tri-bi-mat>",
  "endpoint": "https://payments.internal.example",
  "timeout_seconds": 15
}
```

Ban đầu, secret ở **storage version 6**. Sau khi hệ thống xoay vòng `api_key`, Vault ghi một giá trị mới tại **storage version 7**, trong khi cấu trúc JSON không thay đổi. Một worker khác có thể vẫn giữ cấu hình ở version 6 trong bộ nhớ. Khi điều tra sự cố, việc biết một bản cấu hình đã được đọc từ version nào có thể giúp xác định worker đã nạp secret mới hay chưa.

Trong một trường hợp khác, một công cụ tự động và một người vận hành cùng định sửa secret. Nếu cả hai đọc version 7 rồi ghi dựa trên dữ liệu cũ, một bản ghi có thể làm mất thay đổi của bên kia. KV v2 cung cấp cơ chế kiểm tra điều kiện theo phiên bản (*check-and-set*) để giảm rủi ro ghi đè do cạnh tranh.

Có hai câu hỏi riêng:

- **Giá trị là gì?** Dữ liệu nghiệp vụ mà application client cần sử dụng: `api_key`, `endpoint`, `timeout_seconds`.
- **Giá trị đó thuộc trạng thái lưu trữ nào?** Phiên bản KV, dấu thời gian và trạng thái phiên bản. Thông tin này phục vụ kiểm soát đọc/ghi, quan sát và vòng đời.

Không nên làm cho mọi service phụ thuộc vào cấu trúc metadata chỉ để lấy một endpoint hoặc khóa API.

### 1.1. Luồng dữ liệu hợp lý

```text
Vault KV v2
   │
   ├── Giá trị secret (object JSON)
   │       ├── api_key
   │       ├── endpoint
   │       └── timeout_seconds
   │
   └── Thông tin phiên bản lưu trữ
           ├── version
           ├── created_time
           ├── deletion_time (nếu có)
           └── destroyed
                 │
                 ▼
          Spring Vault Versioned<T>
                 ├── data: T
                 │    └── GatewaySecretDto
                 └── version/metadata
                      └── lớp tích hợp và quản lý cấu hình
```

Đây là mô hình khái niệm, không phải cam kết mọi bản phát hành Spring Vault đều biểu diễn tất cả trường metadata theo cùng một tập accessor. Hãy kiểm tra API đúng phiên bản thư viện đang sử dụng khi cần trường chuyên biệt.

## 2. KV v1 và KV v2 khác nhau ở khả năng lưu phiên bản

| Khía cạnh | KV v1 | KV v2 |
|---|---|---|
| Lưu nhiều phiên bản mỗi secret | Không cung cấp lịch sử phiên bản ở mức engine như KV v2 | Có lịch sử các phiên bản theo cấu hình |
| Đường dẫn HTTP để đọc | Ví dụ `legacy-kv/payments/gateway` | Ví dụ `secret/data/payments/gateway` |
| Phần dữ liệu phản hồi | `data` chứa trực tiếp các field nghiệp vụ | `data` của phản hồi chứa `data` nghiệp vụ và `metadata` của phiên bản |
| Đọc phiên bản cụ thể | Không theo mô hình KV v2 | Có khi phiên bản còn khả dụng và có quyền đọc |
| Chống ghi cạnh tranh theo version (CAS) | Không có semantics CAS theo version KV v2 | Có cơ chế CAS do engine hỗ trợ |
| Xóa mềm, hủy phiên bản | Không theo mô hình lưu nhiều phiên bản KV v2 | Có trạng thái xóa/hủy theo phiên bản và chính sách retention |

Trong Spring Vault, API `VaultKeyValueOperations` giúp ẩn khác biệt đường dẫn KV v1/KV v2 khi chỉ cần đọc/ghi dữ liệu logic. Khi ứng dụng cần thao tác có ý thức về **phiên bản KV v2**, sử dụng `VaultVersionedKeyValueOperations`.

### 2.1. Đường dẫn logic khác đường dẫn HTTP

Giả sử mount KV v2 là `secret`:

```text
Path logic trong API Spring Vault:     payments/gateway
Path HTTP để đọc dữ liệu KV v2:        secret/data/payments/gateway
Path HTTP để đọc metadata KV v2:       secret/metadata/payments/gateway
```

Không truyền `"data/payments/gateway"` vào phương thức mức cao đã nhận mount `secret`: đoạn `data/` thuộc cấu trúc API HTTP của engine KV v2, không thuộc tên secret logic.

Vault policy cho KV v2 thường được thiết kế theo **đường dẫn HTTP** có `data/` hoặc `metadata/` tùy hành động; việc Java gọi path logic không làm thay đổi policy đã cấp.

## 3. Quan sát phản hồi KV v2 trực tiếp

Phản hồi HTTP rút gọn từ endpoint dữ liệu KV v2 có thể như sau:

```json
{
  "request_id": "request-example",
  "data": {
    "data": {
      "api_key": "<gia-tri-bi-mat>",
      "endpoint": "https://payments.internal.example",
      "timeout_seconds": 15
    },
    "metadata": {
      "created_time": "2026-11-20T09:00:00Z",
      "deletion_time": "",
      "destroyed": false,
      "version": 7
    }
  }
}
```

Từ JSON này, có **ba khu vực** cần phân biệt:

1. **Các trường bao ngoài phản hồi Vault**: `request_id` và những trường phản hồi HTTP khác tùy endpoint.
2. **Phần `data.data`**: đối tượng do bên ghi secret quyết định, dùng để cấu hình dịch vụ hoặc lấy credential.
3. **Phần `data.metadata`**: metadata của **phiên bản KV v2** mà lần đọc này trả về, ví dụ version, thời điểm tạo và trạng thái xóa/hủy.

Nếu gọi API tổng quát:

```java
VaultResponse raw =
        vaultOperations.read("secret/data/payments/gateway");

if (raw == null || raw.getData() == null) {
    throw new IllegalStateException("Không có dữ liệu ở path yêu cầu");
}

Map<String, Object> outerData = raw.getRequiredData();
Object business = outerData.get("data");
Object versionMetadata = outerData.get("metadata");
```

Ở đây:

- `outerData` có các key `data` và `metadata` của KV v2.
- `business` chưa được kiểm tra kiểu; trước khi dùng phải xác nhận nó là `Map<?, ?>` hoặc chuyển đổi theo DTO mong đợi.
- `versionMetadata` chưa được kiểm tra kiểu; không ép sang DTO nghiệp vụ.

**Không dùng `raw.getData().get("api_key")` ở cách đọc thẳng này**: khóa `api_key` thuộc `data` lồng bên trong. Đừng nhầm `metadata` nội bộ KV v2 với mọi metadata bao ngoài mà kiểu phản hồi Spring Vault có thể hỗ trợ.

### 3.1. Metadata không được coi là “không nhạy cảm tuyệt đối”

Thông tin version, thời gian ghi và trạng thái xóa thường không phải giá trị secret; tuy nhiên tên path, custom metadata, thông tin người ghi hay ngữ cảnh vận hành vẫn có thể tiết lộ cấu trúc hệ thống. Chỉ log những trường metadata có nhu cầu thực tế, theo chính sách truy cập log phù hợp.

## 4. `Versioned<T>`: ghép giá trị có kiểu với thông tin phiên bản

Spring Vault hỗ trợ `org.springframework.vault.support.Versioned<T>` để biểu diễn một giá trị `T` cùng version và thông tin phiên bản liên quan. Đối với KV v2, API `VaultVersionedKeyValueOperations` cho phép làm việc với giá trị này.

Hình dung:

```text
Versioned<GatewaySecretDto>
├── getData()       → GatewaySecretDto
│     ├── apiKey
│     ├── endpoint
│     └── timeoutSeconds
├── getVersion()    → định danh version KV
└── getMetadata()   → metadata phiên bản (nếu có)
```

Khác với `VaultResponseSupport<T>`, `Versioned<T>` được thiết kế quanh **phiên bản của giá trị**. Không nên mặc định `Versioned<T>` chứa đầy đủ mọi trường HTTP response như request ID hoặc auth payload.

| Kiểu | Dữ liệu chính | Bối cảnh sử dụng |
|---|---|---|
| `VaultResponse` | `Map<String, Object>` | Đọc response chưa định kiểu hoặc thao tác API tổng quát |
| `VaultResponseSupport<T>` | `T` | Đọc dữ liệu nghiệp vụ có kiểu kèm thông tin phản hồi thông thường |
| `Versioned<T>` | `T` và version/metadata | Đọc giá trị KV v2 khi cần biết phiên bản lưu trữ |
| `GatewaySecretDto` (do ứng dụng viết) | Các field secret nghiệp vụ | Tầng ánh xạ dữ liệu ứng dụng, không phụ thuộc version của Vault |

Một hệ thống có thể dùng `VaultResponseSupport<GatewaySecretDto>` khi chỉ cần giá trị, và chuyển sang API versioned khi cần pin version hoặc theo dõi thay đổi. **Không cần nhét `version` vào DTO để thu được khả năng này**.

## 5. Đọc secret KV v2 dưới dạng `Versioned<Map<String, Object>>`

Đoạn Java dưới đây minh họa cách lấy một secret theo path logic. `vaultOperations` là biến đã được ứng dụng cung cấp:

```java
import java.util.Map;

import org.springframework.vault.core.VaultOperations;
import org.springframework.vault.core.VaultVersionedKeyValueOperations;
import org.springframework.vault.support.Versioned;

VaultVersionedKeyValueOperations versionedKv =
        vaultOperations.opsForVersionedKeyValue("secret");

Versioned<Map<String, Object>> result =
        versionedKv.get("payments/gateway");

if (result == null || result.getData() == null) {
    throw new IllegalStateException("Thiếu secret payments/gateway");
}

Map<String, Object> businessData = result.getData();
var storageVersion = result.getVersion();
var metadata = result.getMetadata();
```

Ý nghĩa từng dòng:

- `opsForVersionedKeyValue("secret")` chọn mount KV v2 mà Spring Vault thao tác theo mô hình có phiên bản.
- `get("payments/gateway")` đọc secret bằng path logic tương đối với mount.
- `result.getData()` là dữ liệu nghiệp vụ đã được bóc khỏi lớp bao KV v2; nếu đọc dạng Map, phải kiểm tra từng key/giá trị.
- `result.getVersion()` biểu diễn **version của giá trị được đọc**, thích hợp cho kiểm soát thay đổi, so sánh trạng thái hoặc chẩn đoán.
- `result.getMetadata()` biểu diễn thông tin metadata phiên bản khi API trả về; cần xử lý khả năng không có một số trường trong phản hồi.

**Lưu ý:** Sử dụng `var` (Java 10+) ở hai biến cuối để ví dụ không giả định metadata hay version là một số nguyên trực tiếp. Khi viết mã production, dùng đúng kiểu/accessor của phiên bản Spring Vault đã chọn; không ép `storageVersion` sang `int` khi chưa hiểu API kiểu version.

### 5.1. Đọc Map vẫn cần kiểm tra schema

Giả sử `businessData` chứa những giá trị đã nêu ở đầu bài. Cách lấy giá trị an toàn:

```java
Object apiKey = businessData.get("api_key");
Object timeout = businessData.get("timeout_seconds");

if (!(apiKey instanceof String key) || key.isBlank()) {
    throw new IllegalArgumentException("api_key không hợp lệ");
}
if (!(timeout instanceof Number)) {
    throw new IllegalArgumentException("timeout_seconds phải là number");
}
```

Với timeout, tiếp tục xác thực tính nguyên và phạm vi `1..120` trước khi cấu hình HTTP client. Không được log `businessData`, `key` hay toàn bộ `result` nếu có chứa secrets.

`Versioned<Map<String, Object>>` cung cấp metadata phiên bản; nó **không** biến dữ liệu `Map` thành schema có kiểu hoặc mặc định xác thực các giá trị.

## 6. Đọc `Versioned<T>` với DTO nghiệp vụ

Nếu schema ổn định, có thể đọc trực tiếp sang một kiểu DTO cụ thể. JSON nghiệp vụ ví dụ:

```json
{
  "apiKey": "<gia-tri-bi-mat>",
  "endpoint": "https://payments.internal.example",
  "timeoutSeconds": 15
}
```

DTO dạng JavaBean:

```java
public class GatewaySecretDto {

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
}
```

Mã đọc (khi dùng overload `get(path, Class<T>)` của API versioned):

```java
VaultVersionedKeyValueOperations versionedKv =
        vaultOperations.opsForVersionedKeyValue("secret");

Versioned<GatewaySecretDto> result =
        versionedKv.get("payments/gateway", GatewaySecretDto.class);

if (result == null || result.getData() == null) {
    throw new IllegalStateException("Thiếu cấu hình gateway");
}

GatewaySecretDto dto = result.getData();
var version = result.getVersion();

if (dto.getApiKey() == null || dto.getApiKey().isBlank()) {
    throw new IllegalStateException("Gateway apiKey không hợp lệ");
}
if (dto.getEndpoint() == null || dto.getEndpoint().isBlank()) {
    throw new IllegalStateException("Gateway endpoint không hợp lệ");
}
if (dto.getTimeoutSeconds() == null
        || dto.getTimeoutSeconds() < 1
        || dto.getTimeoutSeconds() > 120) {
    throw new IllegalStateException("Gateway timeout không hợp lệ");
}
```

Kết quả:

- `dto` chứa **chỉ dữ liệu cấu hình** mà bên ghi KV lưu.
- `version` được giữ riêng để theo dõi phiên bản lưu trữ nếu cần.
- Metadata về ngày tạo, xóa hoặc hủy phiên bản, nếu được trả về và cần dùng, nên được xử lý tại adapter hoặc một lớp quản lý trạng thái của secret.

Ở ví dụ này DTO dùng `camelCase`. Nếu key trong Vault là `snake_case` như `api_key`, cần áp dụng quy tắc ánh xạ tên phù hợp (ví dụ `@JsonProperty` hoặc `@JsonNaming` với bộ chuyển đổi tương ứng). **Versioned không tự giải quyết mismatch tên trường**.

### 6.1. Tại sao dùng `Integer` thay vì `int`?

Nếu JSON thiếu `timeoutSeconds`, field `Integer` cho phép biểu diễn `null` và validator có thể từ chối. Dùng `int` sẽ khiến thuộc tính có giá trị mặc định `0` trong JavaBean, dễ nhầm với dữ liệu được cấp. Với field có tác động đến an toàn hay kết nối, cần validation tường minh cho cả “thiếu” và “sai phạm vi”.

### 6.2. Không phải mọi giá trị có kiểu đều hợp lệ

DTO có thể deserialize thành công nhưng `apiKey` là chuỗi trắng, `endpoint` là URI HTTP, timeout bằng 0 hoặc một collection rỗng. Nếu schema yêu cầu HTTPS, hãy chuyển `String` thành `URI` và kiểm tra scheme, host, userinfo và allowlist phù hợp. Nếu DTO có list nested objects, kiểm tra từng phần tử trước khi đưa ra service.

## 7. Tách value, version và metadata trong kiến trúc ứng dụng

Một ứng dụng có thể tổ chức hai lớp dữ liệu:

1. **Giá trị cấu hình đã kiểm tra**: những trường cần cho client nghiệp vụ, với kiểu Java thích hợp.
2. **Trạng thái nguồn**: version và metadata chọn lọc dùng để phát hiện thay đổi hoặc hỗ trợ vận hành, không lan sang mọi thành phần nghiệp vụ.

Sơ đồ:

```text
                     Vault KV v2
                          │
          VaultVersionedKeyValueOperations
                          │
                          ▼
              Versioned<GatewaySecretDto>
                          │
              ┌───────────┴────────────┐
              │                        │
              ▼                        ▼
         getData()              getVersion(),
              │                 getMetadata()
              ▼                        │
   validate/normalize                   │
              │                        │
              ▼                        ▼
    GatewaySettings              SecretSourceState
       (nghiệp vụ)                (vận hành/refresh)
              │                        │
              └──────────┬─────────────┘
                         ▼
                Adapter/API nội bộ
                         │
                    PaymentClient
                  chỉ nhận Settings
```

Ở đây `GatewaySettings` và `SecretSourceState` là các **kiểu do ứng dụng thiết kế**, không phải class bắt buộc của Spring Vault. Nếu hệ thống rất nhỏ và không cần metadata, adapter có thể chỉ trả `GatewaySettings` mà không tạo `SecretSourceState`.

### 7.1. DTO không nên có field `vaultVersion` chỉ để đọc metadata

Tránh thiết kế:

```java
// Ví dụ cấu trúc gây nhầm ngữ nghĩa.
public class GatewaySecretDto {
    String apiKey;
    String endpoint;
    int vaultVersion; // Không tự được điền từ metadata KV v2.
}
```

Vì payload nghiệp vụ của KV v2 không tự có key `vaultVersion`, trình ánh xạ DTO sẽ không tự lấy `data.metadata.version` vào field này. Nếu bên ghi thực sự lưu một key `vaultVersion` trong `data` thì đó lại chỉ là **giá trị nghiệp vụ tự đặt tên**, không phải nguồn chân lý của storage version.

### 7.2. Đối tượng cấu hình đã được chuẩn hóa

Ví dụ dùng Java record để biểu đạt cấu hình:

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

Và helper chuyển DTO:

```java
static GatewaySettings validateAndMap(GatewaySecretDto dto) {
    if (dto == null) {
        throw new IllegalArgumentException("Gateway DTO không tồn tại");
    }
    String token = dto.getApiKey();
    if (token == null || token.isBlank()) {
        throw new IllegalArgumentException("apiKey bắt buộc");
    }
    if (dto.getTimeoutSeconds() == null
            || dto.getTimeoutSeconds() < 1
            || dto.getTimeoutSeconds() > 120) {
        throw new IllegalArgumentException("timeoutSeconds ngoài phạm vi");
    }

    String endpointText = dto.getEndpoint();
    if (endpointText == null || endpointText.isBlank()) {
        throw new IllegalArgumentException("endpoint bắt buộc");
    }

    URI endpoint;
    try {
        endpoint = URI.create(endpointText);
    } catch (IllegalArgumentException ex) {
        throw new IllegalArgumentException("endpoint không phải URI hợp lệ");
    }
    if (!"https".equalsIgnoreCase(endpoint.getScheme())
            || endpoint.getHost() == null
            || endpoint.getUserInfo() != null) {
        throw new IllegalArgumentException("endpoint phải là HTTPS URL");
    }

    return new GatewaySettings(
            token,
            endpoint,
            Duration.ofSeconds(dto.getTimeoutSeconds()));
}
```

Hàm minh họa giả định được đặt trong một utility/service cùng phạm vi với DTO và các import đã khai báo. Nó phân biệt endpoint bị thiếu với endpoint sai định dạng; mã production còn cần kiểm tra các ràng buộc cụ thể như allowlist host, port và path.

`GatewaySettings` chỉ giữ cấu hình cần cho ứng dụng; storage version không nằm trong record. Tránh ghi record hoặc serialize tự động thành JSON công khai, bởi `apiKey()` vẫn là một accessor chứa dữ liệu nhạy cảm ngay cả khi `toString()` đã che.

## 8. Storage version khác schema version, secret rotation và lease

Đây là bốn khái niệm rất dễ nhầm:

| Khái niệm | Ví dụ | Trả lời câu hỏi nào? | Có tự đảm bảo secret còn hợp lệ không? |
|---|---|---|---|
| **KV storage version** | Version 7 | Đây là lần ghi nào của bản ghi KV v2? | Không |
| **Schema version** | `"schema_version": 2` trong `data` | Dữ liệu tuân theo hợp đồng JSON nghiệp vụ nào? | Không |
| **Rotation time** | Lần thay `api_key` | Khi nào giá trị credential thay đổi? | Không |
| **Lease/token lifecycle** | Dynamic credential có lease hoặc auth token hết hạn | Quyền/credential còn thời hạn, có thể renew/revoke không? | Cần cơ chế quản lý riêng |

### 8.1. Storage version không phải số phiên bản schema

Ví dụ:

```text
KV version 5 → data có schema_version = 1
KV version 6 → xoay vòng api_key, schema_version vẫn = 1
KV version 7 → đổi tên field, schema_version = 2
KV version 8 → tiếp tục xoay vòng api_key, schema_version vẫn = 2
```

Mỗi lần ghi KV có thể tăng version, trong khi schema chỉ đổi khi hợp đồng dữ liệu thay đổi. Do đó **không viết điều kiện kiểu `if (kvVersion >= 7) schemaV2()`** nếu chưa thiết kế sự tương ứng cố định, được kiểm thử và được kiểm soát ở mọi môi trường.

Nếu cần, lưu `schema_version` như **một field trong dữ liệu nghiệp vụ** và validate theo các phiên bản ứng dụng hỗ trợ:

```json
{
  "schema_version": 2,
  "api_key": "<gia-tri-bi-mat>",
  "endpoint": "https://payments.internal.example",
  "timeout_seconds": 15
}
```

Khi đó DTO/mapper có thể đọc `schema_version`, còn `Versioned<T>` giữ storage version ở lớp ngoài. Tránh gán hai trường này thành một ý nghĩa.

### 8.2. KV v2 không tạo lease cho mọi secret tĩnh

Phần lớn dữ liệu KV không có lease động gia hạn được như credentials do database secrets engine cấp. `created_time` của một version không có nghĩa credential đó tự hết hạn sau một khoảng cố định; ngược lại, version mới hơn cũng không chứng minh API key được bên thứ ba chấp nhận.

Ứng dụng cần cơ chế xoay vòng và cập nhật client, theo chính sách hệ thống. Token dùng để xác thực **vào Vault** có vòng đời riêng với API key được lưu **trong Vault**. Đừng nhầm `Versioned.getVersion()` với token version hoặc lease ID.

## 9. Đọc version cụ thể: snapshot có thể tái lập

Một ứng dụng bình thường đọc **phiên bản mới nhất đang khả dụng**. Tuy nhiên, khi kiểm thử hồi quy hoặc điều tra một lần triển khai, đôi khi cần đọc một version KV v2 xác định.

API versioned của Spring Vault hỗ trợ yêu cầu version cụ thể thông qua đối tượng version theo chữ ký của bản thư viện đang dùng. Luồng khái niệm:

```text
Input: mount = "secret"
       path = "payments/gateway"
       requestedVersion = 6
             │
             ▼
VaultVersionedKeyValueOperations
  └── read with requested version
             │
             ▼
Versioned<GatewaySecretDto>
  ├── data của version 6
  └── metadata/version của version 6
```

Vì chữ ký overload đọc version có thể khác nhau theo bản Spring Vault, hãy lấy từ API reference của dependency đang dùng thay vì đoán thứ tự tham số. Điều quan trọng về mặt thiết kế là **request version** được truyền qua API versioned, không bằng cách thêm một field `version` vào DTO nghiệp vụ hoặc sửa path logic thành `data/...`.

### 9.1. Những giới hạn khi “pin” version

- Version cũ có thể đã bị **soft delete**, **destroy**, hoặc bị loại theo cấu hình giới hạn lịch sử, khi đó không thể coi nó luôn đọc được.
- Vault policy của workload và trạng thái phiên bản quyết định khả năng truy cập.
- Việc đọc version cũ **không phục hồi** credential đã bị hệ thống ngoài thu hồi; một API key ở version 6 có thể đã vô hiệu sau rotation.
- Pin một version quá lâu có thể làm dịch vụ giữ cấu hình lỗi thời. Nếu cần pin cho mục đích tái lập, hãy đặt giới hạn và cách quay lại phiên bản mới nhất.

### 9.2. Metadata phiên bản và metadata của toàn bộ key

KV v2 có thể cung cấp nhiều tầng metadata:

| Nguồn thông tin | Ví dụ | Phạm vi |
|---|---|---|
| Metadata đi cùng một lần đọc dữ liệu KV v2 | `version`, `created_time`, `deletion_time`, `destroyed` | Phiên bản cụ thể được đọc |
| API metadata riêng cho một key KV v2 | `current_version`, `oldest_version`, `max_versions`, `cas_required`, phiên bản đã lưu và custom metadata | Toàn bộ lịch sử/chính sách áp dụng cho key |
| Metadata phản hồi HTTP Vault | `request_id` và trường điều phối request | Lần gọi HTTP hiện tại |
| Field `schema_version` trong `data` | `schema_version = 2` | Hợp đồng do ứng dụng quy định |

Không suy từ `getMetadata()` của một giá trị có version rằng nó luôn chứa **toàn bộ cấu hình/hàng loạt version** của metadata endpoint. Khi cần lịch sử đầy đủ hoặc thuộc tính cấu hình của key, hãy dùng API metadata KV v2 phù hợp và Vault policy cho phép, thay vì cố lấy chúng từ DTO dữ liệu.

## 10. CAS: phiên bản giúp tránh mất cập nhật khi nhiều bên cùng ghi

Giả sử hai tác nhân cùng sửa dữ liệu:

```text
Thời điểm    Writer A                          Writer B
─────────    ───────────────────────────────   ───────────────────────────────
t0           Đọc version 7                     Đọc version 7
t1           Sửa retry_policy                  Sửa endpoint
t2           Ghi với CAS mong đợi = 7
t3                                             Ghi với CAS mong đợi = 7

Kết quả:     A thành công, tạo version 8.       B bị từ chối CAS vì version
                                                hiện tại đã thay đổi.
```

CAS (*check-and-set*) yêu cầu **phiên bản hiện tại ở thời điểm ghi** phải khớp phiên bản mà bên ghi mong đợi. Nó giúp phát hiện cạnh tranh thay vì âm thầm ghi đè.

Một quy trình an toàn về mặt khái niệm:

1. Đọc dữ liệu cùng storage version hiện tại (ví dụ 7).
2. Tạo bản dữ liệu cập nhật và kiểm tra schema, không xóa nhầm các key khác.
3. Ghi với điều kiện `cas = 7` bằng API KV v2 phù hợp.
4. Nếu Vault từ chối điều kiện, **đọc lại** version mới nhất, giải quyết xung đột và cân nhắc ghi lại.
5. Không retry cùng payload mù quáng với CAS mới vì có thể ghi đè thay đổi hợp lệ của bên khác.

**Lưu ý:** Các phương thức ghi và cách truyền CAS phụ thuộc API Spring Vault/phiên bản được dùng. Bài này mô tả semantics CAS, không giả định một overload Java không được xác nhận. Nếu cần viết thao tác ghi cụ thể, hãy tra `VaultVersionedKeyValueOperations`/API KV v2 của đúng dependency và kiểm thử bằng Vault thử nghiệm.

### 10.1. CAS không giải quyết mọi vấn đề dữ liệu

CAS bảo vệ khỏi một số **lost updates**, nhưng không bảo đảm payload mới đúng schema hay credential còn dùng được. Bên ghi vẫn phải kiểm tra:

- Danh sách field được giữ lại nếu thao tác ghi là **thay toàn bộ**.
- Semantics `put` so với `patch` trong KV v2, đặc biệt khi có field mới hoặc null.
- Đồng bộ nhiều writer và chính sách ưu tiên khi thay đổi cùng field.
- Quy tắc rotation, thời điểm cập nhật client và giới hạn giữ phiên bản cũ.
- Quyền ghi, sửa metadata và CAS requirement của mount/key.

Metadata version giúp đưa ra **quyết định cạnh tranh ghi**, chứ không nên bị chuyển thành một field mật khẩu hoặc endpoint của ứng dụng.

## 11. Xử lý trạng thái xóa mềm, hủy phiên bản và lỗi đọc

Một cách xử lý yếu thường gặp là:

```java
try {
    return loadFromVault();
} catch (Exception ex) {
    return defaultCredentials(); // Sai: che lỗi quyền, kết nối và dữ liệu.
}
```

Cần phân biệt:

| Tình huống | Dấu hiệu có thể gặp | Cách tiếp cận |
|---|---|---|
| Secret path không tồn tại | API trả giá trị không có hoặc lỗi not found theo API | Kiểm tra path/mount và xử lý secret bắt buộc |
| Đọc yêu cầu version không tồn tại | Version chưa từng có hoặc đã ngoài phạm vi lịch sử | Báo version không khả dụng, không tự lấy bản bất kỳ |
| Version bị soft delete | Không có dữ liệu đọc được ở version đó theo trạng thái engine | Không mặc định giá trị cũ có thể được dùng |
| Version đã bị destroy | Dữ liệu version bị hủy vĩnh viễn theo semantics của engine | Không lập kế hoạch khôi phục từ chính version đã hủy |
| Workload không có quyền | Vault từ chối theo policy | Kiểm tra danh tính, policy và path API tương ứng |
| Token Vault hết hạn | Yêu cầu bị lỗi xác thực | Sửa cơ chế token lifecycle; version không thay thế authentication |
| Mạng/TLS/server không khả dụng | HTTP/I/O exception | Retry có giới hạn và giám sát theo chính sách |
| Dữ liệu trong version thiếu `api_key` | DTO/Map không hợp lệ | Validator báo lỗi schema, không điền credential mặc định |
| CAS ghi không khớp | Ghi bị từ chối vì version hiện tại khác dự kiến | Đọc lại, giải quyết xung đột, ghi lại có kiểm soát |

Không chuyển lỗi 403 thành `null` rồi tự đọc một version khác. Một số lỗi không tồn tại/version bị xóa có thể được SDK diễn giải khác nhau tùy phương thức và bản Spring Vault; cần kiểm thử các trạng thái thực tế của engine thay vì chỉ dựa vào một giả định HTTP status duy nhất.

## 12. Logging và giám sát phiên bản an toàn

Khi hệ thống cần biết phiên bản nào đã được nạp, có thể đo các thông tin không nhạy cảm trong giới hạn chính sách:

- Kết quả đọc thành công/thất bại, độ trễ, loại lỗi.
- Version KV được đọc nếu có nhu cầu chẩn đoán rollout/rotation.
- Tỷ lệ lỗi CAS hoặc số lần phải đọc lại do xung đột.
- Thời điểm refresh cấu hình ở ứng dụng, khi không làm lộ giá trị secret.

**Không log**:

- Toàn bộ `Versioned<T>`, `getData()`, `VaultResponse` hoặc DTO chứa `api_key`, mật khẩu, token hay private key.
- `record.toString()` tự sinh hoặc JSON serializer tự động của DTO nhạy cảm.
- Raw response, payload exception của converter, stack trace chứa trích đoạn dữ liệu hoặc header xác thực khi chưa kiểm soát nội dung.
- Custom metadata hoặc tên path có thể tiết lộ cấu trúc nội bộ, nếu chưa được đánh giá về nhạy cảm.

Một cấu hình có version mới hơn cũng không bảo đảm mọi worker đang dùng nó; khi cần quan sát rotation, phải hiểu chiến lược cache/refresh và thời điểm client được dựng lại. Không suy từ việc KV tăng version rằng kết nối cũ đã đóng hoặc credential cũ bị thu hồi.

### 12.1. Tránh metadata có cardinality cao trong metric

Đưa từng tên path/secret động hoặc request ID vào nhãn metric có thể tạo nhiều tổ hợp nhãn, khó giám sát và tiềm ẩn rò rỉ thông tin. Có thể dùng nhóm secret hoặc tên adapter ổn định theo chính sách observability; request ID nên nằm ở log/tracing được kiểm soát khi cần truy vết.

## 13. Kiểm thử có ý thức về version

### 13.1. Kiểm thử đơn vị: giữ metadata tách khỏi validation

Ví dụ, validator cho giá trị secret chỉ kiểm tra thuộc tính nghiệp vụ:

```java
import java.net.URI;

public final class GatewaySecretValidator {

    private GatewaySecretValidator() {
    }

    public static void validate(GatewaySecretDto dto) {
        if (dto == null) {
            throw new IllegalArgumentException("Không có Gateway DTO");
        }
        if (dto.getApiKey() == null || dto.getApiKey().isBlank()) {
            throw new IllegalArgumentException("apiKey bắt buộc");
        }
        if (dto.getEndpoint() == null || dto.getEndpoint().isBlank()) {
            throw new IllegalArgumentException("endpoint bắt buộc");
        }
        try {
            URI uri = URI.create(dto.getEndpoint());
            if (!"https".equalsIgnoreCase(uri.getScheme())
                    || uri.getHost() == null
                    || uri.getUserInfo() != null) {
                throw new IllegalArgumentException("endpoint phải là HTTPS");
            }
        } catch (IllegalArgumentException ex) {
            throw new IllegalArgumentException(
                    "endpoint không hợp lệ");
        }
        if (dto.getTimeoutSeconds() == null
                || dto.getTimeoutSeconds() < 1
                || dto.getTimeoutSeconds() > 120) {
            throw new IllegalArgumentException("timeoutSeconds ngoài phạm vi");
        }
    }
}
```

Lớp `GatewaySecretValidator` chỉ phụ thuộc `GatewaySecretDto`, không phụ thuộc `Versioned<T>` hay API truy cập Vault. Vì vậy có thể kiểm thử ngay cả khi Vault không chạy:

```java
import static org.junit.jupiter.api.Assertions.assertDoesNotThrow;
import static org.junit.jupiter.api.Assertions.assertThrows;

import org.junit.jupiter.api.Test;

class GatewaySecretValidatorTest {

    private GatewaySecretDto validDto() {
        GatewaySecretDto dto = new GatewaySecretDto();
        dto.setApiKey("fake-key-for-test-only");
        dto.setEndpoint("https://payments.internal.example");
        dto.setTimeoutSeconds(15);
        return dto;
    }

    @Test
    void acceptsValidBusinessData() {
        assertDoesNotThrow(() ->
                GatewaySecretValidator.validate(validDto()));
    }

    @Test
    void rejectsMissingKey() {
        GatewaySecretDto dto = validDto();
        dto.setApiKey(null);

        assertThrows(IllegalArgumentException.class,
                () -> GatewaySecretValidator.validate(dto));
    }

    @Test
    void rejectsNonHttpsEndpoint() {
        GatewaySecretDto dto = validDto();
        dto.setEndpoint("http://payments.internal.example");

        assertThrows(IllegalArgumentException.class,
                () -> GatewaySecretValidator.validate(dto));
    }

    @Test
    void rejectsTimeoutOutOfRange() {
        GatewaySecretDto dto = validDto();
        dto.setTimeoutSeconds(0);

        assertThrows(IllegalArgumentException.class,
                () -> GatewaySecretValidator.validate(dto));
    }
}
```

Các test này xác nhận dữ liệu nghiệp vụ được kiểm tra độc lập; nó không khẳng định metadata/version do Vault trả về đã được ánh xạ đúng.

### 13.2. Kiểm thử tích hợp với KV v2

Trong Vault thử nghiệm, không dùng credentials sản xuất. Nên có những ca:

| Ca | Kỳ vọng |
|---|---|
| Ghi secret giả lần đầu rồi đọc versioned | Có `data` đúng, có version lưu trữ tương ứng |
| Ghi thay giá trị mà schema không đổi | Version tăng, DTO vẫn cùng hợp đồng |
| Đọc một version cụ thể còn tồn tại | Nhận dữ liệu của đúng version yêu cầu |
| Đọc version đã xóa mềm | Không sử dụng như một secret đang khả dụng |
| Đọc version đã destroy | Không thể phục hồi payload bằng cách đọc version đó |
| Ghi với CAS đúng | Ghi thành công, version tiếp theo được tạo |
| Ghi với CAS cũ | Vault từ chối cập nhật; không làm mất thay đổi mới |
| Cố đọc khi không có policy | Lỗi truy cập được phân biệt với missing data |
| JSON đổi `timeoutSeconds` sang object | Mapping/validation thất bại |
| Tạo `schema_version` khác với storage version | Hai trường được xử lý riêng, không đồng nhất |

Thử cả đường đọc mức cao và endpoint raw (nếu cần) để hiểu lớp `data.data`/`data.metadata`. Nếu ứng dụng dùng `VaultVersionedKeyValueOperations` nhưng chạy trên mount KV v1, kiểm tra điều kiện lỗi thực tế và cấu hình mount; tránh giả định API tự biến KV v1 thành KV v2.

### 13.3. Test rollout/refresh với secret version thay đổi

Một ca hữu ích là:

1. Khởi tạo ứng dụng đọc version 4 trong môi trường thử nghiệm.
2. Ghi version 5 với API key giả mới.
3. Xác minh adapter có thể đọc version mới và validator chấp nhận dữ liệu.
4. Nếu ứng dụng cache cấu hình, xác minh cơ chế refresh tải được bản mới theo chính sách.
5. Kiểm tra client cũ không tiếp tục dùng credential lỗi thời ngoài thời gian cho phép.

Test này cần cơ chế quản lý refresh/rotation riêng của ứng dụng; `Versioned<T>` chỉ cho biết bản dữ liệu được đọc ở version nào.

## 14. Bài tập thực hành

### Bài tập 1 — Phân tách giá trị và metadata

Cho phản hồi KV v2:

```json
{
  "data": {
    "data": {
      "api_key": "<gia-tri-bi-mat>",
      "region": "ap-southeast-1"
    },
    "metadata": {
      "version": 8,
      "created_time": "2026-11-25T07:00:00Z",
      "destroyed": false
    }
  }
}
```

Hãy chỉ rõ:

1. Trường nào nên nằm trong DTO `GatewaySecretDto`?
2. Trường nào thuộc metadata phiên bản KV v2?
3. Nếu đọc bằng `vaultOperations.read(...)`, cần đi qua mấy cấp `data`?
4. Nếu đọc bằng `VaultVersionedKeyValueOperations`, nên lấy value ở đâu và version ở đâu?
5. Vì sao `created_time` không tự động biểu diễn thời hạn lease?

### Bài tập 2 — Hai phiên bản có cùng schema

Version 9 lưu `api_key = K1` và `timeout_seconds = 15`. Version 10 xoay vòng `api_key = K2`, giữ nguyên timeout và schema. Ứng dụng lưu `schema_version = 3` trong cả hai.

Giải thích vì sao storage version khác schema version. Nếu một worker tiếp tục sử dụng K1, bạn cần kiểm tra thêm những cơ chế nào ngoài `getVersion()`?

### Bài tập 3 — CAS và cập nhật cạnh tranh

Writer A và B cùng đọc version 10. A sửa `retry_policy` và ghi thành version 11. B sửa `endpoint` nhưng vẫn muốn ghi với CAS = 10.

- Vault nên phản hồi thế nào với ghi của B?
- B nên làm gì trước khi ghi lại?
- Vì sao không nên tự động đổi CAS thành 11 rồi gửi nguyên payload cũ?
- Nếu B đang dùng API `put` thay vì `patch`, cần chú ý điều gì về các field do A thêm?

### Bài tập 4 — Trường hợp version không khả dụng

Thiết kế một hàm đọc cấu hình được yêu cầu version 5. Hãy liệt kê hành vi cho version còn đọc được, version bị soft delete, version bị destroy, không có quyền đọc và lỗi mạng. Không sử dụng credential mặc định khi không đọc được dữ liệu bắt buộc.

**Định hướng:** xử lý trạng thái phiên bản theo semantics của KV v2, giữ lỗi quyền/kết nối tách biệt và chỉ chuyển DTO đã hợp lệ sang tầng nghiệp vụ.

## 15. Những điều cần ghi nhớ

- `Versioned<T>` diễn tả **dữ liệu có kiểu `T`** cùng thông tin phiên bản trong Spring Vault. Với KV v2, dùng `VaultVersionedKeyValueOperations` khi cần biết hoặc yêu cầu một version.
- `getData()` là dữ liệu nghiệp vụ; version và metadata là thông tin lưu trữ/vận hành. Không nhét chúng vào DTO bí mật chỉ để “đủ trường”.
- Khi gọi KV v2 qua endpoint HTTP trực tiếp, `data` của phản hồi chứa `data` nghiệp vụ và `metadata` phiên bản. API KV có phiên bản của Spring Vault giúp xử lý lớp bao này.
- **Storage version**, **schema_version**, **rotation time** và **lease/token lifecycle** là các khái niệm khác nhau.
- CAS giúp phát hiện một số xung đột ghi nhưng không thay thế kiểm tra schema, merge dữ liệu và kiểm soát quyền.
- Version cũ có thể bị xóa mềm, hủy hoặc hết lịch sử; không mặc định mọi version đều đọc được hay credential cũ vẫn hợp lệ.
- Ánh xạ có kiểu vẫn cần validation, kiểm thử tích hợp và cách giám sát an toàn. Không log `Versioned<T>` hoặc DTO chứa secrets.

## Tài liệu tham khảo

- [Spring Vault — `Versioned<T>` API](https://docs.spring.io/spring-vault/docs/current/api/org/springframework/vault/support/Versioned.html): giá trị có version và metadata.
- [Spring Vault — `VaultVersionedKeyValueOperations` API](https://docs.spring.io/spring-vault/docs/current/api/org/springframework/vault/core/VaultVersionedKeyValueOperations.html): thao tác KV v2 có phiên bản.
- [Spring Vault — Vault Secrets Engines](https://docs.spring.io/spring-vault/reference/vault/vault-secret-engines.html): KV v1/KV v2, đọc version và semantics dữ liệu.
- [HashiCorp Vault — KV v2 API](https://developer.hashicorp.com/vault/api-docs/secret/kv/kv-v2): lớp `data`/`metadata`, CAS, soft delete và destroy.
- [HashiCorp Vault — KV Secrets Engine](https://developer.hashicorp.com/vault/docs/secrets/kv): mục đích KV engine và khác biệt giữa các phiên bản.
