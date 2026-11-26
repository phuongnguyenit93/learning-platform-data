# Xử lý trường thiếu, null và dữ liệu thay đổi cấu trúc

## Mục tiêu bài học

Trong **Spring Vault**, đọc được một phản hồi từ HashiCorp Vault chưa có nghĩa ứng dụng Java đã nhận được secret đầy đủ và hợp lệ. Có thể toàn bộ đường dẫn secret không tồn tại; một JSON object có thể thiếu key; key có mặt nhưng giá trị là `null`; dữ liệu có thể là chuỗi rỗng, danh sách rỗng hoặc đổi từ số sang chuỗi. Khi schema thay đổi theo thời gian, một phiên bản ứng dụng cũ còn có thể đọc nhầm hoặc bỏ qua trường do phiên bản mới ghi.

Bài thuộc chương **Ánh xạ dữ liệu** của module **SPRING_VAULT**. Người học sẽ thực hành ranh giới giữa `VaultTemplate`/`VaultOperations`, dữ liệu JSON từ KV v1/KV v2, DTO Java và các quy tắc cấu hình an toàn. Sau khi học, bạn có thể:

1. Phân biệt **không có phản hồi**, **không có trường**, **JSON null**, **giá trị rỗng** và **giá trị sai kiểu**.
2. Đọc `Map<String, Object>` với `containsKey()` để giữ thông tin một key có mặt hay không.
3. Hiểu vì sao DTO JavaBean và `record` thường không phân biệt được key thiếu với key chứa `null` chỉ qua getter.
4. Xây hàm ánh xạ/validation tập trung, chỉ áp dụng giá trị mặc định cho các trường được phép mặc định.
5. Xử lý đổi tên, thêm trường, đổi kiểu và thay đổi cấu trúc lồng nhau mà không âm thầm bỏ qua lỗi cấu hình.
6. Thiết kế kiểm thử và quy trình chuyển schema song song với rotation, quyền truy cập và cơ chế phiên bản KV v2.

> **Bối cảnh:** Giả sử ứng dụng Java đã được kết nối tới Vault bằng Spring Vault, xác thực theo workload (ví dụ AppRole, Kubernetes hoặc phương thức thích hợp), và có policy đọc đúng path. Các ví dụ dùng secret giả, không đưa token hay mật khẩu sản xuất vào mã nguồn. Quản lý token/lease, Transit encryption, PKI và giám sát là những nội dung liên quan trong chương trình Spring Vault; kiểu dữ liệu Java không thay thế các cơ chế đó.

## 1. Các trạng thái dữ liệu không được đánh đồng

Giả sử cấu hình cổng thanh toán cần một `api_key`, một `endpoint` HTTPS, và một thời gian timeout. Hãy xét sáu trạng thái thường gặp:

| Trạng thái | Ví dụ | Ý nghĩa có thể có | Cách xử lý ban đầu |
|---|---|---|---|
| Secret tại path không tồn tại | `kv.get("payments/runtime") == null` | Không có bản ghi ở path đang đọc | Kiểm tra phản hồi trước khi dùng `getData()` |
| Phản hồi tồn tại nhưng không có payload `data` | `response.getData() == null` | Phản hồi không chứa phần dữ liệu mong đợi | Không tiếp tục như dữ liệu hợp lệ |
| JSON thiếu key | `{"endpoint":"https://example.invalid"}` không có `api_key` | Bên ghi không cung cấp trường | Dùng `containsKey("api_key")` để phát hiện |
| JSON có key với `null` | `{"api_key":null}` | Key có mặt nhưng được ghi giá trị null | Phân biệt với key vắng mặt nếu hợp đồng yêu cầu |
| JSON có giá trị rỗng | `{"api_key":""}` hoặc `{"regions":[]}` | Đúng kiểu, nhưng có thể không dùng được | Kiểm tra ràng buộc nghiệp vụ |
| JSON có kiểu sai | `{"timeout_seconds":"thirty"}` | Schema không đúng hoặc dữ liệu bị ghi sai | Từ chối hoặc chuyển đổi có quy tắc rõ ràng |

Đây là các trường hợp **khác nhau về ngữ nghĩa**. Nếu một secret chứa API key bắt buộc, thường phải từ chối cả key thiếu, `null` và chuỗi trắng. Với trường `description` tùy chọn, có thể chấp nhận cả thiếu và null. Với cấu hình `timeout_seconds`, có thể cho phép **thiếu key** để dùng mặc định nhưng vẫn từ chối **key có giá trị null**, nhằm phát hiện cấu hình bị ghi dở hoặc sai schema.

### 1.1. “Không tìm thấy” khác lỗi truy cập

Một HTTP 403 do Vault policy từ chối hoặc một lỗi xác thực workload không có nghĩa secret không tồn tại. Tương tự, timeout mạng và lỗi deserialize không phải dữ liệu `null`. Không viết một khối `catch (Exception)` chuyển tất cả thất bại thành `Map.of()` hoặc DTO rỗng: làm vậy mất thông tin nguyên nhân và có thể khiến ứng dụng chạy với credential sai.

### 1.2. “Giá trị rỗng” phụ thuộc loại dữ liệu

- `""` là một chuỗi hợp lệ về cú pháp JSON nhưng thường không hợp lệ cho password, API key hoặc hostname.
- `"   "` khác chuỗi rỗng về mặt ký tự; có thể dùng `isBlank()` khi hợp đồng không chấp nhận toàn khoảng trắng.
- `[]` là một array rỗng; hợp lệ nếu trường là danh sách tùy chọn, không hợp lệ nếu dịch vụ cần tối thiểu một endpoint.
- `{}` là một object rỗng; có thể không đáp ứng schema nested object bắt buộc.
- `0`, `false` là **giá trị hiện diện**, không phải “thiếu”; không dùng kiểm tra kiểu truthy/falsy kiểu ngôn ngữ khác để coi chúng là không có giá trị.

Các ví dụ trong bài dùng Java 17+ để minh họa pattern matching với `instanceof` và `record`. Khi dùng Java phiên bản cũ hơn, hãy điều chỉnh cú pháp Java tương ứng.

## 2. JSON ở KV v2 có lớp bao riêng

Ở KV v2, khi gọi endpoint HTTP trực tiếp, trường `data` xuất hiện ở **hai cấp**:

```json
{
  "request_id": "request-example",
  "data": {
    "data": {
      "api_key": "<gia-tri-bi-mat>",
      "endpoint": "https://payments.internal.example",
      "timeout_seconds": 20
    },
    "metadata": {
      "version": 7,
      "created_time": "2026-11-20T09:00:00Z"
    }
  }
}
```

Cấp `data` ngoài cùng thuộc cấu trúc phản hồi Vault; object `data` bên trong chứa các trường nghiệp vụ và `metadata` bên cạnh nó mô tả phiên bản lưu trữ KV v2. Khi gọi:

```java
VaultResponse response =
        vaultOperations.read("secret/data/payments/runtime");
```

`response.getData()` tương ứng object chứa `data` và `metadata` của KV v2. Để tới `api_key` cần lấy key `data` từ map này rồi kiểm tra kiểu trước khi đọc sâu.

Với cách làm thông dụng hơn, dùng API chuyên biệt của Spring Vault:

```java
import java.util.Map;
import org.springframework.vault.core.VaultKeyValueOperations;
import org.springframework.vault.core.VaultOperations;
import org.springframework.vault.core.VaultKeyValueOperationsSupport.KeyValueBackend;
import org.springframework.vault.support.VaultResponse;

VaultKeyValueOperations kv = vaultOperations.opsForKeyValue(
        "secret", KeyValueBackend.KV_2);

VaultResponse response = kv.get("payments/runtime");

if (response == null || response.getData() == null) {
    throw new IllegalStateException(
            "Thiếu dữ liệu thanh toán bắt buộc trong Vault");
}

Map<String, Object> businessData = response.getRequiredData();
```

`"secret"` là tên mount, `"payments/runtime"` là **path logic tương đối với mount**. Với `opsForKeyValue(..., KV_2)`, không đưa thêm `data/` vào path logic. `businessData` ở đoạn trên chứa các field nghiệp vụ ngay tại cấp cần dùng.

Sơ đồ:

```text
KV v2 endpoint trực tiếp:                API KV mức cao:

VaultResponse.getData()                 kv.get("payments/runtime")
  ├── data                                └── VaultResponse.getData()
  │    ├── api_key                              ├── api_key
  │    ├── endpoint                             ├── endpoint
  │    └── timeout_seconds                      └── timeout_seconds
  └── metadata
       └── version
```

Điều này quan trọng khi chẩn đoán “thiếu trường”: nếu ứng dụng đọc sai cấp, `data.get("api_key")` có thể trả `null` dù secret vẫn có key đó ở object lồng bên trong. Hãy xác định API đọc và đường dẫn trước khi kết luận dữ liệu bị thiếu.

## 3. `Map.containsKey()` để phân biệt thiếu key và null

Trong Java, `Map.get(key)` trả `null` cho **cả hai tình huống**: key vắng mặt hoặc key có giá trị null.

```java
import java.util.LinkedHashMap;
import java.util.Map;

Map<String, Object> data = new LinkedHashMap<>();
data.put("description", null);

System.out.println(data.get("description"));          // null
System.out.println(data.get("unknown"));              // null
System.out.println(data.containsKey("description"));  // true
System.out.println(data.containsKey("unknown"));      // false
```

`containsKey()` là công cụ đơn giản để giữ **presence information**, tức thông tin một key có mặt trong object hay không. Cách này phù hợp khi cần xử lý thay đổi cấu hình theo kiểu PATCH hoặc migration, trong đó “không ghi trường” có thể khác với “ghi trường thành null”.

### 3.1. Đọc field bắt buộc

```java
static String requireText(
        Map<String, Object> data, String key) {

    if (!data.containsKey(key)) {
        throw new IllegalArgumentException(
                "Thiếu trường bắt buộc: " + key);
    }

    Object value = data.get(key);
    if (!(value instanceof String text) || text.isBlank()) {
        throw new IllegalArgumentException(
                key + " phải là chuỗi không rỗng");
    }
    return text;
}
```

Nếu key thiếu, thông báo nêu rõ “Thiếu trường”. Nếu key có mặt nhưng null, sai kiểu hoặc chỉ chứa khoảng trắng, hàm từ chối theo yêu cầu về **giá trị**. Mã này cố ý không in nội dung secret; `key` ở ví dụ là tên trường trong schema do ứng dụng xác định.

### 3.2. Đọc field tùy chọn

Giả sử `description` có thể vắng mặt, null hoặc là chuỗi:

```java
static String optionalDescription(Map<String, Object> data) {
    if (!data.containsKey("description")) {
        return null; // Không cung cấp mô tả.
    }

    Object value = data.get("description");
    if (value == null) {
        return null; // Cho phép JSON null theo hợp đồng.
    }
    if (value instanceof String description) {
        return description;
    }

    throw new IllegalArgumentException(
            "description phải là chuỗi hoặc null");
}
```

Trong trường hợp này, hai trạng thái “thiếu” và “null” được **chủ động chuẩn hóa** thành cùng giá trị Java `null`. Nếu nghiệp vụ cần phân biệt, không nên xóa bỏ sự khác nhau quá sớm.

### 3.3. Một mô hình rõ ràng cho presence

Khi ứng dụng thật sự cần biết field có mặt hay không, có thể tạo một kiểu trung gian:

```java
public record FieldPresence<T>(boolean present, T value) {

    public static <T> FieldPresence<T> absent() {
        return new FieldPresence<>(false, null);
    }

    public static <T> FieldPresence<T> present(T value) {
        return new FieldPresence<>(true, value);
    }
}
```

```java
static FieldPresence<Object> field(
        Map<String, Object> source, String key) {
    return source.containsKey(key)
            ? FieldPresence.present(source.get(key))
            : FieldPresence.absent();
}

FieldPresence<Object> note = field(businessData, "description");

if (!note.present()) {
    // Không có key trong dữ liệu JSON.
} else if (note.value() == null) {
    // Key có mặt, giá trị JSON null.
} else {
    // Cần kiểm tra kiểu của note.value() trước khi dùng.
}
```

`FieldPresence` là **kiểu ứng dụng tự định nghĩa**, không phải kiểu bắt buộc của Spring Vault. Nó minh họa ranh giới giữa việc **phát hiện presence** và việc **chuyển đổi giá trị**. Đừng suy diễn `T` đã được xác thực chỉ vì nó xuất hiện trong một `record` generic.

## 4. DTO có kiểu: ưu điểm và giới hạn khi gặp null

Đọc trực tiếp KV thành DTO giúp tránh truyền `Map<String, Object>` qua các lớp nghiệp vụ:

```java
import java.util.List;

public class PaymentSecretDto {

    private String apiKey;
    private String endpoint;
    private Integer timeoutSeconds;
    private List<String> regions;

    public PaymentSecretDto() {
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

    public List<String> getRegions() {
        return regions;
    }
    public void setRegions(List<String> regions) {
        this.regions = regions;
    }
}
```

```java
VaultResponseSupport<PaymentSecretDto> response =
        kv.get("payments/runtime", PaymentSecretDto.class);

if (response == null || response.getData() == null) {
    throw new IllegalStateException("Thiếu payment secret");
}

PaymentSecretDto dto = response.getRequiredData();
```

Ví dụ này dùng `VaultResponseSupport<T>` của Spring Vault; nó bao bọc phần `data` đã được ánh xạ thành `PaymentSecretDto`. Dữ liệu nghiệp vụ nằm trong DTO, còn request ID/lease của phản hồi (nếu endpoint có) vẫn thuộc đối tượng phản hồi và cơ chế vòng đời Vault.

### 4.1. Vì sao nên dùng wrapper types?

| Thuộc tính | Kiểu Java nguyên thủy | Kiểu tham chiếu |
|---|---|---|
| Timeout | `int`, giá trị mặc định khi khởi tạo là `0` | `Integer`, mặc định là `null` |
| Cờ bật/tắt | `boolean`, mặc định `false` | `Boolean`, mặc định `null` |
| Số thực | `double`, mặc định `0.0` | `Double`, mặc định `null` |

Nếu JSON thiếu `enabled` nhưng DTO dùng `boolean`, việc nhận `false` có thể khiến người đọc nhầm “Vault đã gửi false”. Với `Boolean`, `null` báo hiệu chưa có giá trị Java; bước validation có thể quyết định đó là cấu hình thiếu hay trường được phép mặc định.

**Giới hạn:** chỉ nhìn getter `getTimeoutSeconds() == null` thường không phân biệt được key **không xuất hiện** và key **có mặt với JSON null**. Cả hai có thể trở thành `null`. Hãy dùng Map, tree model hoặc cơ chế theo dõi setter nếu cần phân biệt.

### 4.2. `Optional<T>` không tự giải quyết bài toán presence

`Optional<T>` hợp lý ở một số API Java để biểu đạt giá trị có thể không tồn tại, nhưng không nên giả định JSON mapper mặc định:

- ánh xạ mọi `Optional<T>` mà không cần module/hỗ trợ cụ thể;
- giữ nguyên sự khác biệt giữa key thiếu và key có JSON null;
- thực hiện validation của trường bắt buộc chỉ vì property có kiểu `Optional`.

Nếu schema thực sự có ba trạng thái (*absent / present-null / present-value*), cần biểu diễn có chủ đích như `FieldPresence<T>` hoặc kiểm tra bằng `Map.containsKey()`/JSON tree trước khi chuyển DTO. Đưa `Optional` vào mọi field không làm schema tự chính xác hơn.

### 4.3. Jackson và giá trị null

Khi client chuyển đổi JSON bằng Jackson 2.x, có thể kiểm soát một số hành vi theo property:

```java
import com.fasterxml.jackson.annotation.JsonSetter;
import com.fasterxml.jackson.annotation.Nulls;

public class StrictApiKeyDto {
    private String apiKey;

    public StrictApiKeyDto() {
    }

    public String getApiKey() {
        return apiKey;
    }

    @JsonSetter(value = "api_key", nulls = Nulls.FAIL)
    public void setApiKey(String apiKey) {
        this.apiKey = apiKey;
    }
}
```

Trong Jackson 2.x, `Nulls.FAIL` có thể làm bước deserialize từ chối **JSON null tường minh** ở property đó. Điều này **không đồng nghĩa** một key bị thiếu sẽ bị từ chối; setter có thể không được gọi khi key không xuất hiện. Vì vậy vẫn cần validation hậu ánh xạ:

```java
if (dto.getApiKey() == null || dto.getApiKey().isBlank()) {
    throw new IllegalStateException("api_key bắt buộc");
}
```

Nếu dùng `@JsonProperty(required = true)`, đừng giả định mọi kiểu JavaBean và mọi cấu hình Jackson sẽ áp dụng ràng buộc thiếu-field giống nhau; hành vi với constructor/creator properties có thể khác với setter thông thường. Hãy xác minh trên phiên bản mapper thực tế.

**Quan trọng:** những annotation trên chỉ tác động khi quá trình ánh xạ dùng bộ chuyển đổi hỗ trợ Jackson tương ứng. Không mặc định một `ObjectMapper` tạo riêng cho MVC cũng là instance Spring Vault đang sử dụng.

## 5. Chọn chính sách mặc định: mặc định an toàn hoặc từ chối

Giá trị mặc định có thể giảm lỗi cấu hình cho một số trường **không nhạy cảm** như timeout; đồng thời có thể che sự cố nghiêm trọng nếu áp dụng nhầm cho API key hoặc quyền truy cập.

| Trường | Chính sách minh họa | Lý do |
|---|---|---|
| `api_key` | Bắt buộc, từ chối thiếu/null/rỗng | Không được sử dụng token mặc định hay credential cứng |
| `endpoint` | Bắt buộc, xác thực HTTPS và host | Không tự gửi secrets đến đích không xác định |
| `timeout_seconds` | Có thể mặc định khi **thiếu key**, nhưng từ chối khi key tồn tại với null/sai kiểu | Hỗ trợ cấu hình cũ mà vẫn phát hiện dữ liệu được ghi không hợp lệ |
| `regions` | Bắt buộc, array không rỗng | Dịch vụ ví dụ cần ít nhất một vùng |
| `description` | Tùy chọn; thiếu và null đều được chấp nhận | Chỉ là metadata phục vụ diễn giải nội bộ |
| `enabled` | Tùy chính sách; thường nên yêu cầu Boolean tường minh nếu điều khiển hành vi nhạy cảm | Tránh tự biến thiếu key thành false/true gây lệch chức năng |

Lưu ý **default-on-missing** khác **default-on-null**. Không viết:

```java
// Không dùng cho field cần phân biệt thiếu với null:
Object rawTimeout = data.getOrDefault("timeout_seconds", 10);
```

`Map.getOrDefault(...)` trả về giá trị `null` khi key **có mặt** với giá trị null; nó chỉ lấy mặc định nếu key thiếu. Mã này không “sửa” được một key null, cũng không xác thực rằng key chứa number hợp lệ. Tự viết `value == null ? default : value` còn nguy hiểm hơn trong trường hợp null phải gây lỗi.

## 6. Ví dụ đầy đủ: ánh xạ Map sang cấu hình đã xác thực

Ở ranh giới đọc Vault, có thể chọn đọc `Map` trước để phân biệt presence, sau đó chuyển thành cấu hình ứng dụng có kiểu. Giả sử hợp đồng thanh toán:

```json
{
  "api_key": "<gia-tri-bi-mat>",
  "endpoint": "https://payments.internal.example/api",
  "timeout_seconds": 15,
  "regions": ["ap-southeast-1", "eu-west-1"],
  "description": null
}
```

Quy tắc:

- `api_key` và `endpoint`: bắt buộc, kiểu String và không rỗng.
- `regions`: mảng không rỗng, mỗi phần tử là String không trắng.
- `timeout_seconds`: mặc định 10 giây **chỉ khi thiếu key**; nếu được cung cấp phải là JSON number nguyên trong khoảng 1–120.
- `description`: tùy chọn; vắng mặt hoặc null được phép, còn giá trị không null phải là String.

### 6.1. Định nghĩa đầu ra có kiểu

```java
import java.net.URI;
import java.time.Duration;
import java.util.List;

public record PaymentSettings(
        String apiKey,
        URI endpoint,
        Duration timeout,
        List<String> regions,
        String description) {

    @Override
    public String toString() {
        return "PaymentSettings[redacted]";
    }
}
```

Đây là `record` tự định nghĩa với các field đã được chuẩn hóa. Việc ghi đè `toString()` hạn chế rò rỉ `apiKey` khi ghi log dạng chuỗi; vẫn cần **không** tự serialize object này ra log hoặc HTTP response, vì serializer có thể đọc các accessor và ghi trường bí mật.

### 6.2. Parser kiểm tra cả presence và kiểu dữ liệu

```java
import java.math.BigDecimal;
import java.net.URI;
import java.time.Duration;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;

public final class PaymentSettingsMapper {

    private static final int DEFAULT_TIMEOUT_SECONDS = 10;

    private PaymentSettingsMapper() {
    }

    public static PaymentSettings from(Map<String, Object> data) {
        if (data == null) {
            throw new IllegalArgumentException("Thiếu dữ liệu payment");
        }

        String apiKey = requireText(data, "api_key");
        String endpointValue = requireText(data, "endpoint");
        URI endpoint = requireHttpsEndpoint(endpointValue);

        int timeoutSeconds = data.containsKey("timeout_seconds")
                ? requireInt(data, "timeout_seconds")
                : DEFAULT_TIMEOUT_SECONDS;

        if (timeoutSeconds < 1 || timeoutSeconds > 120) {
            throw new IllegalArgumentException(
                    "timeout_seconds phải nằm trong khoảng 1..120");
        }

        List<String> regions = requireStrings(data, "regions");
        if (regions.isEmpty()) {
            throw new IllegalArgumentException(
                    "regions phải có ít nhất một phần tử");
        }

        String description = optionalDescription(data);

        return new PaymentSettings(
                apiKey,
                endpoint,
                Duration.ofSeconds(timeoutSeconds),
                regions,
                description);
    }

    private static String requireText(
            Map<String, Object> data, String key) {

        if (!data.containsKey(key)) {
            throw new IllegalArgumentException(
                    "Thiếu trường bắt buộc: " + key);
        }
        Object value = data.get(key);
        if (!(value instanceof String text) || text.isBlank()) {
            throw new IllegalArgumentException(
                    key + " phải là chuỗi không rỗng");
        }
        return text;
    }

    private static int requireInt(
            Map<String, Object> data, String key) {

        Object value = data.get(key);
        if (!(value instanceof Number number)) {
            throw new IllegalArgumentException(
                    key + " phải là JSON number nguyên");
        }
        try {
            return new BigDecimal(number.toString()).intValueExact();
        } catch (ArithmeticException | NumberFormatException ex) {
            throw new IllegalArgumentException(
                    key + " phải là số nguyên hợp lệ");
        }
    }

    private static List<String> requireStrings(
            Map<String, Object> data, String key) {

        Object value = data.get(key);
        if (!(value instanceof List<?> raw)) {
            throw new IllegalArgumentException(
                    key + " phải là JSON array");
        }

        List<String> result = new ArrayList<>();
        for (int index = 0; index < raw.size(); index++) {
            Object element = raw.get(index);
            if (!(element instanceof String text) || text.isBlank()) {
                throw new IllegalArgumentException(
                        key + "[" + index + "] phải là chuỗi không rỗng");
            }
            result.add(text);
        }
        return List.copyOf(result);
    }

    private static String optionalDescription(Map<String, Object> data) {
        if (!data.containsKey("description")
                || data.get("description") == null) {
            return null;
        }
        Object value = data.get("description");
        if (!(value instanceof String description)) {
            throw new IllegalArgumentException(
                    "description phải là chuỗi hoặc null");
        }
        return description;
    }

    private static URI requireHttpsEndpoint(String text) {
        URI uri;
        try {
            uri = URI.create(text);
        } catch (IllegalArgumentException ex) {
            throw new IllegalArgumentException(
                    "endpoint không đúng định dạng URI");
        }

        if (!"https".equalsIgnoreCase(uri.getScheme())
                || uri.getHost() == null
                || uri.getUserInfo() != null) {
            throw new IllegalArgumentException(
                    "endpoint phải là HTTPS URL có host hợp lệ");
        }
        return uri;
    }
}
```

Hàm `requireInt()` chấp nhận các Java subtype của `Number` nhưng kiểm tra tính nguyên và phạm vi `int` bằng `BigDecimal.intValueExact()`. Đây là kiểm tra **sau deserialize**: nếu bộ giải mã đã làm mất độ chính xác JSON number trước đó, phương thức này không khôi phục được giá trị gốc. Với dữ liệu tài chính hoặc số quan trọng, cần chọn kiểu và quy tắc JSON mapper phù hợp ngay từ đầu.

Hàm `requireStrings()` sử dụng `List<?>` để kiểm tra từng phần tử, tránh ép `Object` trực tiếp sang `List<String>` không có xác minh runtime. Với DTO và nested object khác, áp dụng cùng nguyên tắc cho từng cấp.

Để tránh mở ra host không mong đợi trong hệ thống thật, `requireHttpsEndpoint()` có thể cần thêm allowlist host, kiểm tra port, path, query hoặc fragment. Ví dụ chỉ thể hiện một số điều kiện tối thiểu để minh họa validation.

### 6.3. Đặt parser tại ranh giới Spring Vault

```java
import org.springframework.vault.core.VaultKeyValueOperations;
import org.springframework.vault.core.VaultOperations;
import org.springframework.vault.core.VaultKeyValueOperationsSupport.KeyValueBackend;
import org.springframework.vault.support.VaultResponse;

public final class PaymentSettingsProvider {

    private final VaultKeyValueOperations kv;

    public PaymentSettingsProvider(VaultOperations operations) {
        this.kv = operations.opsForKeyValue(
                "secret", KeyValueBackend.KV_2);
    }

    public PaymentSettings load() {
        VaultResponse response = kv.get("payments/runtime");

        if (response == null || response.getData() == null) {
            throw new IllegalStateException(
                    "Không tìm thấy payment secret bắt buộc");
        }

        return PaymentSettingsMapper.from(
                response.getRequiredData());
    }
}
```

`PaymentSettingsProvider` có trách nhiệm truy cập Vault và trả cấu hình đã kiểm tra. Service thanh toán chỉ cần `PaymentSettings`, không phải biết `Map`, cấu trúc JSON `data.data` hoặc đường dẫn KV. Với cấu hình quan trọng, ứng dụng phải quyết định rõ **lúc nào đọc lại** dữ liệu sau rotation và có được giữ bản cấu hình gần nhất hay không; generic/DTO tự nó không làm mới giá trị.

## 7. Khi JSON đổi cấu trúc: các loại thay đổi schema

Các secrets trong Vault có thể được cập nhật bởi công cụ triển khai, pipeline, nhà vận hành hoặc phiên bản ứng dụng khác. **Schema** là hợp đồng về tên field, kiểu, bắt buộc/tùy chọn và cấu trúc lồng nhau; Vault KV lưu dữ liệu nhưng không tự áp đặt toàn bộ hợp đồng đó cho DTO Java.

| Loại thay đổi | Ví dụ cũ → mới | Rủi ro với ứng dụng cũ |
|---|---|---|
| Thêm field tùy chọn | Thêm `description` | Mapper strict có thể từ chối key lạ |
| Thêm field bắt buộc | Thêm `tenant_id` | Client cũ không cung cấp; client mới có thể từ chối dữ liệu cũ |
| Đổi tên key | `timeout_seconds` → `connect_timeout_seconds` | Getter cũ nhận null hoặc dùng mặc định sai |
| Đổi kiểu | `"15"` → `15` | Phụ thuộc coercion policy, có thể lỗi khi deserialize |
| Đổi cấp lồng nhau | `db_url` → `database.url` | DTO/map cũ không tìm thấy field |
| Đổi ý nghĩa | `timeout_seconds` thực tế chuyển thành milliseconds | Dữ liệu nhìn vẫn là số nhưng đơn vị bị hiểu sai |
| Thu hẹp tập giá trị | `region` chỉ chấp nhận một số vùng | Dữ liệu cũ còn đúng kiểu nhưng không hợp lệ nghiệp vụ |
| Xóa field | Bỏ `api_key` hoặc `regions` | Thiếu cấu hình có thể gây lỗi khởi động hoặc hành vi không an toàn |

Tương thích schema không đồng nghĩa JSON “vẫn deserialize được”. Một số thay đổi **cú pháp trông giống nhau nhưng ngữ nghĩa khác**: ví dụ đổi đơn vị thời gian từ giây sang mili giây khi giữ nguyên tên key sẽ âm thầm làm ứng dụng chạy sai.

### 7.1. Phân biệt schema version với KV v2 version

KV v2 có metadata phiên bản lưu trữ, ví dụ `metadata.version = 7`. Đây là thông tin lịch sử ghi secret, **không phải** mã phiên bản hợp đồng dữ liệu của ứng dụng. Một lần xoay vòng giá trị `api_key` có thể tạo phiên bản KV mới dù schema không đổi.

Nếu cần quản lý schema tường minh, có thể đặt `schema_version` ngay trong **dữ liệu nghiệp vụ**:

```json
{
  "schema_version": 2,
  "api_key": "<gia-tri-bi-mat>",
  "endpoint": "https://payments.internal.example",
  "connect_timeout_seconds": 15
}
```

Trường này có quy tắc riêng: số nguyên thuộc tập phiên bản đã hỗ trợ, không phải metadata của Vault. Không nên tự động cho rằng `metadata.version == schema_version`.

## 8. Đổi tên field trong giai đoạn chuyển tiếp

Giả sử version cũ lưu `timeout_seconds`, version mới lưu `connect_timeout_seconds`. Trong khoảng thời gian triển khai cuốn chiếu (*rolling upgrade*), adapter cần xử lý dữ liệu cũ và mới.

### 8.1. Kiểm tra presence trước khi chọn tên

Không nên âm thầm đọc key mới rồi fallback về key cũ khi key mới **có mặt nhưng null**; đó có thể là cấu hình sai cần được phát hiện.

```java
static int readMigratingTimeout(Map<String, Object> data) {
    boolean hasOld = data.containsKey("timeout_seconds");
    boolean hasNew = data.containsKey("connect_timeout_seconds");

    if (hasOld && hasNew) {
        throw new IllegalArgumentException(
                "Hai tên timeout cùng xuất hiện trong secret");
    }

    if (hasNew) {
        return requireInt(data, "connect_timeout_seconds");
    }
    if (hasOld) {
        return requireInt(data, "timeout_seconds");
    }

    throw new IllegalArgumentException(
            "Thiếu cấu hình timeout bắt buộc");
}
```

`requireInt` ở đây là helper có cùng hợp đồng như trong `PaymentSettingsMapper`, được đặt trong cùng lớp mapper hoặc dùng một utility phù hợp. Nó từ chối null, chuỗi và số không nguyên; không mặc định khi key đã có mặt với dữ liệu sai.

Một số hệ thống có thể chọn chính sách “key mới được ưu tiên nếu cả hai cùng tồn tại”. Nếu vậy, phải mô tả rõ cách kiểm tra **hai giá trị có mâu thuẫn** hay không, cách ghi cảnh báo an toàn và thời điểm loại bỏ tên cũ. Ví dụ trên chọn phương án nghiêm ngặt: từ chối đồng thời hai key để tránh thứ tự ngầm.

### 8.2. Dùng `@JsonAlias` cho DTO khi không cần phát hiện xung đột

Với Jackson 2.x:

```java
import com.fasterxml.jackson.annotation.JsonAlias;
import com.fasterxml.jackson.annotation.JsonProperty;

public class TimeoutDto {

    @JsonProperty("connect_timeout_seconds")
    @JsonAlias("timeout_seconds")
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

`@JsonAlias` hỗ trợ nhận tên thay thế khi deserialize; khi serialize theo quy tắc thông thường, tên chính là `connect_timeout_seconds`. Nhưng alias không tự **phát hiện hai key có mặt đồng thời** theo hợp đồng riêng, cũng không chuyển secret đã lưu sang schema mới. Khi cần phát hiện presence và xung đột tên, hãy kiểm tra ở mức Map hoặc JSON tree **trước** khi gộp alias vào một property.

### 8.3. Quy trình triển khai thay đổi an toàn

1. **Xác định các bên đọc/ghi** secret, phiên bản ứng dụng đang chạy và schema hiện hành.
2. **Cập nhật phía đọc tương thích trước:** cho phép dữ liệu cũ và mới nhưng kiểm tra rõ xung đột, null, kiểu và phạm vi.
3. **Triển khai phía ghi schema mới:** thống nhất key chuẩn và cách xử lý các field cũ; không để hai bên ghi tranh nhau đổi schema.
4. **Kiểm thử triển khai cuốn chiếu:** xác minh cả ứng dụng cũ đang chạy và ứng dụng mới đọc được dữ liệu trong giai đoạn chuyển.
5. **Quan sát lỗi không lộ secrets:** đo tỷ lệ lỗi schema, thiếu key và thất bại đọc Vault; không log payload.
6. **Gỡ hỗ trợ tên cũ:** khi tất cả bên đọc đã được nâng cấp, xóa alias và quy tắc legacy.

Giá trị `api_key` có thể bị rotation trong cùng giai đoạn này; hãy quản lý rotation như một thay đổi giá trị có vòng đời riêng, thay vì coi mỗi lần KV version tăng là một migration schema.

## 9. Thay đổi cấu trúc lồng nhau: tránh flatten sai ngữ nghĩa

Một secret cũ có:

```json
{
  "database_url": "jdbc:postgresql://db.internal.example:5432/app",
  "pool_max_size": 10
}
```

Phiên bản mới:

```json
{
  "database": {
    "url": "jdbc:postgresql://db.internal.example:5432/app",
    "pool": {
      "max_size": 10
    }
  }
}
```

Đây là thay đổi **độ sâu JSON**, không chỉ quy ước `snake_case` → `camelCase`. Một naming strategy thông thường không biến `"database_url"` thành `"database": {"url": ...}`. Cần DTO lồng nhau hoặc hàm chuyển cấu trúc tường minh.

Ví dụ đọc một object nested an toàn:

```java
static Map<?, ?> requireObject(Object value, String path) {
    if (!(value instanceof Map<?, ?> object)) {
        throw new IllegalArgumentException(
                path + " phải là JSON object");
    }
    return object;
}

Map<?, ?> database = requireObject(
        data.get("database"), "database");
Map<?, ?> pool = requireObject(
        database.get("pool"), "database.pool");

Object maxSize = pool.get("max_size");
if (!(maxSize instanceof Number)) {
    throw new IllegalArgumentException(
            "database.pool.max_size phải là number");
}
```

Đoạn trên minh họa kiểm tra cấu trúc từng cấp; nó chưa xác thực `maxSize` là số nguyên dương hoặc nằm trong giới hạn mong muốn. Khi cần những ràng buộc đó, hãy dùng helper chuyển số có kiểm tra chính xác và bổ sung validation.

**Đừng nhầm key có dấu chấm với object lồng nhau.** `"database.pool.max_size"` là một key JSON literal, khác với ba cấp `database → pool → max_size`. Muốn hỗ trợ cả schema cũ và mới phải xác định rõ cấu trúc tại mỗi phiên bản.

## 10. KV v2: thay đổi dữ liệu, phiên bản và thao tác ghi

Khi xử lý schema evolution trên KV v2, cần phân biệt **đọc và ghi nội dung** với **đọc metadata phiên bản**:

| Khái niệm | Vai trò | Lưu ý |
|---|---|---|
| KV v2 `data` | Các field secret do ứng dụng đọc | Có thể thay đổi schema theo bên ghi |
| KV v2 `metadata.version` | Phiên bản lưu trữ sau các lần ghi | Không tự là `schema_version` nghiệp vụ |
| CAS (*check-and-set*) | Điều kiện bảo vệ ghi trong môi trường có cạnh tranh | Cần xác định phiên bản mong đợi, không ghi đè thiếu kiểm soát |
| Ghi toàn bộ nội dung | Có thể thay toàn bộ tập key của phiên bản mới tùy API | Cẩn thận đánh rơi các field không được bên ghi giữ lại |
| PATCH với semantics phù hợp | Sửa một phần dữ liệu theo API được hỗ trợ | Không đồng nhất mọi `put` với `patch`; cần kiểm tra null/xóa trường và quyền |
| Xóa mềm/xóa version hoặc hủy version | Thay đổi khả năng đọc phiên bản secret | Không chỉ là một trường JSON thiếu trong payload |

**Ví dụ rủi ro khi ghi:** một công cụ cũ chỉ biết `api_key` và `endpoint`, trong khi bản mới còn có `retry_policy`. Nếu công cụ cũ ghi **toàn bộ** map chỉ với hai field, secret phiên bản mới có thể mất `retry_policy`. Ứng dụng đọc sau đó thấy “thiếu trường” dù lỗi bắt nguồn từ cơ chế ghi.

Trước khi thay đổi schema trên KV v2:

- Chọn API ghi phù hợp: thay toàn bộ hay sửa một phần theo semantics thực tế của engine và Spring Vault.
- Phối hợp bên ghi/bên đọc, nhất là trong rolling deployment.
- Sử dụng CAS hoặc cơ chế đồng bộ ghi khi có nhiều writer, nếu hệ thống yêu cầu tránh lost update.
- Kiểm tra trạng thái phiên bản, quyền đọc/ghi và cách phục hồi bản trước trong môi trường thử nghiệm.
- Tránh xem việc một phiên bản bị xóa/hủy hoặc bị policy từ chối là trường hợp tương đương JSON `null`.

Nếu cần đọc một **phiên bản KV v2 cụ thể**, dùng API tương ứng, chẳng hạn `VaultVersionedKeyValueOperations`, theo tài liệu phiên bản Spring Vault của dự án. Với bài học ánh xạ này, `kv.get(path)` minh họa việc đọc dữ liệu logic thông thường.

## 11. Phân loại lỗi để hệ thống có thể chẩn đoán

| Nhóm lỗi | Dấu hiệu | Xử lý phù hợp |
|---|---|---|
| Không có path/secret | `kv.get(path)` không có phản hồi đọc được | Báo thiếu cấu hình bắt buộc, xem lại mount và path |
| Không đủ quyền hoặc xác thực lỗi | Vault trả 403 hoặc lỗi authentication | Kiểm tra workload identity, token lifecycle và Vault policy |
| Lỗi vận chuyển/TLS/server | Exception HTTP/I/O/TLS | Theo dõi tính sẵn sàng kết nối, dùng retry có kiểm soát khi phù hợp |
| Dữ liệu thiếu key | `!data.containsKey(key)` | Áp dụng default **chỉ** nếu schema cho phép; còn lại fail fast |
| JSON null tường minh | `containsKey(key) && get(key) == null` | Chấp nhận, từ chối hoặc hiểu là lệnh xóa theo hợp đồng cụ thể |
| Dữ liệu sai kiểu | Chuỗi thay vì number, list thay vì object | Từ chối/convert theo schema và policy coercion |
| DTO ánh xạ xong nhưng sai nghiệp vụ | Timeout âm, URI không HTTPS, danh sách rỗng | Validation và chuẩn hóa trước khi tạo client |
| Schema thay đổi chưa tương thích | Key đổi tên, nested object mới | Adapter migration, kiểm thử cả phiên bản cũ và mới |
| Credentials hết hiệu lực | Secret đã rotate hoặc lease/token hết hạn | Cập nhật bản cấu hình đang sử dụng, xử lý lifecycle tương ứng |

Không dùng:

```java
try {
    return readAndMapFromVault();
} catch (Exception ignored) {
    return defaultCredentials(); // Không an toàn cho secrets bắt buộc.
}
```

Một chiến lược sử dụng cấu hình đã kiểm tra gần nhất (*last known good*) có thể phù hợp cho một số hệ thống cần độ sẵn sàng cao, nhưng phải có giới hạn thời gian, chính sách rotation, giám sát và tiêu chí an toàn được thiết kế riêng. Không biến nó thành fallback mặc định cho mọi lỗi.

### 11.1. Ghi log và thông điệp lỗi

Không ghi toàn bộ `VaultResponse`, `Map`, DTO hoặc `PaymentSettings` ra log nếu chứa API key/password/token. `record.toString()`, Lombok `@Data` và serializer có thể tự đưa tất cả trường vào log. Tránh đưa giá trị URI hoặc JSON raw vào exception nếu có khả năng chứa thông tin nhạy cảm.

Thông tin có thể ghi theo chính sách vận hành: loại thao tác, kết quả thành công/thất bại, nhóm lỗi, thời lượng, request ID Vault được kiểm soát và **tên trường schema** không chứa secret. Nếu sử dụng metadata cho quan sát, phải kiểm tra liệu giá trị metadata hoặc warnings có chứa dữ liệu nhạy cảm hay không.

## 12. Kiểm thử riêng parser: missing, null và schema migration

Tách `PaymentSettingsMapper.from(Map<String, Object>)` khỏi phần gọi Vault cho phép kiểm thử quy tắc dữ liệu mà không cần server hoặc token thật.

### 12.1. Ma trận kiểm thử

| Tình huống | Kết quả mong đợi |
|---|---|
| Đủ trường, đúng kiểu | Tạo `PaymentSettings` hợp lệ |
| Thiếu `api_key` | Từ chối, không dùng secret mặc định |
| `api_key` có JSON null | Từ chối |
| `api_key` là chuỗi trắng | Từ chối |
| Thiếu `timeout_seconds` | Sử dụng default 10 giây theo hợp đồng ví dụ |
| `timeout_seconds` có JSON null | Từ chối, không dùng default |
| `timeout_seconds` là chuỗi `"15"` | Từ chối vì schema yêu cầu number |
| `timeout_seconds` là `2.5` hoặc số ngoài phạm vi | Từ chối |
| Thiếu `regions` hoặc `regions: []` | Từ chối |
| `regions` chứa số, object hoặc null | Từ chối và chỉ rõ vị trí lỗi |
| Thiếu `description` hoặc có `description: null` | Chấp nhận, chuẩn hóa thành `null` |
| `description` là object | Từ chối |
| Có cả `timeout_seconds` và `connect_timeout_seconds` trong migration | Từ chối theo chính sách không cho xung đột |
| Đổi `database_url` thành object `database` | Cần adapter schema tương ứng; không suy từ naming strategy |

### 12.2. Ví dụ JUnit 5 kiểm tra hành vi có ý nghĩa

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.time.Duration;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.Test;

class PaymentSettingsMapperTest {

    private Map<String, Object> validInput() {
        Map<String, Object> data = new LinkedHashMap<>();
        data.put("api_key", "fake-key-for-test-only");
        data.put("endpoint", "https://payments.internal.example/api");
        data.put("timeout_seconds", 20);
        data.put("regions", List.of("ap-southeast-1"));
        return data;
    }

    @Test
    void usesDefaultOnlyWhenTimeoutFieldIsAbsent() {
        Map<String, Object> data = validInput();
        data.remove("timeout_seconds");

        PaymentSettings settings = PaymentSettingsMapper.from(data);
        assertEquals(Duration.ofSeconds(10), settings.timeout());
    }

    @Test
    void rejectsExplicitNullTimeout() {
        Map<String, Object> data = validInput();
        data.put("timeout_seconds", null);

        assertThrows(IllegalArgumentException.class,
                () -> PaymentSettingsMapper.from(data));
    }

    @Test
    void rejectsMissingApiKey() {
        Map<String, Object> data = validInput();
        data.remove("api_key");

        assertThrows(IllegalArgumentException.class,
                () -> PaymentSettingsMapper.from(data));
    }

    @Test
    void acceptsNullOptionalDescription() {
        Map<String, Object> data = validInput();
        data.put("description", null);

        PaymentSettings settings = PaymentSettingsMapper.from(data);
        assertNull(settings.description());
    }

    @Test
    void rejectsWrongRegionElementType() {
        Map<String, Object> data = validInput();
        data.put("regions", List.of("ap-southeast-1", 42));

        assertThrows(IllegalArgumentException.class,
                () -> PaymentSettingsMapper.from(data));
    }
}
```

Dùng `LinkedHashMap` để có thể lưu JSON null trong dữ liệu thử; `Map.of(...)` của Java không chấp nhận key/value null. Các test trên kiểm tra hành vi **presence/default/validation**, không chỉ kiểm tra DTO có setter. Chỉ dùng dữ liệu giả, không đưa giá trị secret vào assertion message hoặc snapshot.

### 12.3. Kiểm thử tích hợp với Vault

Unit test parser không chứng minh việc đọc Vault đã giải mã đúng JSON. Trong môi trường cô lập, có thể chuẩn bị mount KV v2 và workload identity/policy chỉ có quyền cần thiết, sau đó:

1. Ghi secret dữ liệu giả có key đúng schema, dùng `opsForKeyValue(..., KV_2).get(...)` để đọc.
2. Kiểm tra cả response rỗng và dữ liệu nghiệp vụ; không làm lộ payload qua log.
3. Ghi lần lượt secret thiếu key, key null, array sai kiểu, schema cũ và schema mới để xác minh parser/DTO.
4. Xác minh hành vi khi path không tồn tại, policy từ chối, kết nối bị lỗi, cùng cách phân loại lỗi rõ ràng.
5. Thử cập nhật KV v2 trong tình huống có nhiều writer nếu ứng dụng dùng CAS/PATCH; kiểm tra không mất các key của schema mới.
6. Kiểm tra luồng rotation nếu cấu hình được cache hoặc client được khởi tạo một lần rồi giữ thông tin cũ.

Đối với ứng dụng Java sử dụng Transit hoặc PKI, payload và lifecycle khác KV có thể cần cách mapping riêng; không tái sử dụng mù quáng hợp đồng `PaymentSettings` cho mọi secrets engine.

## 13. Thực hành vận dụng

### Bài tập 1 — Bốn trạng thái của cùng một key

Cho bốn object:

```json
{}
```

```json
{"api_key": null}
```

```json
{"api_key": ""}
```

```json
{"api_key": "fake-key-for-practice"}
```

Hãy mô tả kết quả của `containsKey("api_key")`, `get("api_key")` và `requireText(data, "api_key")` trong từng trường hợp. Giải thích vì sao chỉ gọi `get()` không phân biệt được hai JSON đầu tiên.

**Gợi ý:** key vắng mặt khiến `containsKey` trả false; key có `null` khiến `containsKey` trả true nhưng `get` vẫn trả null. Hai trường hợp sau có giá trị kiểu String nhưng chỉ chuỗi không rỗng đáp ứng hợp đồng ví dụ.

### Bài tập 2 — Default có điều kiện

Thiết kế DTO/parser cho các field `enabled`, `batch_size` và `database_password` với quy tắc:

- `enabled` bắt buộc, phải có Boolean true/false tường minh.
- `batch_size` có default 50 khi **không có key**; nếu có key phải là số nguyên trong khoảng 1–500.
- `database_password` bắt buộc, không được dùng default và không được rỗng.

Viết test cho JSON `{"enabled": false}`, `{"enabled": null}` và `{"batch_size": null}`. Chỉ ra trường nào phải bị từ chối và lý do.

### Bài tập 3 — Rolling migration

Hệ thống cũ dùng:

```json
{"timeout_seconds": 15, "api_key": "<gia-tri-bi-mat>"}
```

Hệ thống mới dùng:

```json
{"connect_timeout_seconds": 15, "api_key": "<gia-tri-bi-mat>"}
```

Hãy đề xuất chiến lược cập nhật bên đọc, bên ghi, kiểm thử và gỡ alias. Viết logic từ chối khi hai key timeout có mặt đồng thời (kể cả khi một key mang `null`). Giải thích vì sao không nên xem `metadata.version` của KV v2 là schema version.

### Bài tập 4 — Nested object thay đổi

Giả sử secret cũ có `"db_url"`, còn secret mới có `"database": {"url": "..."}`. Thiết kế hai DTO hoặc một adapter có kiểm tra presence; từ chối khi không có cả hai biểu diễn hoặc khi cả hai cùng xuất hiện mâu thuẫn. Nêu những kiểm tra cần có cho URL và cách báo lỗi mà không tiết lộ credentials.

## 14. Những điểm cần ghi nhớ

- **Không có phản hồi**, **không có key**, **key có JSON null**, **giá trị rỗng** và **giá trị sai kiểu** là những trạng thái khác nhau cần chính sách rõ ràng.
- `Map.get()` không phân biệt key thiếu với key null; `Map.containsKey()` hoặc JSON tree/presence tracking giúp giữ thông tin này.
- DTO có kiểu thuận tiện cho mã nghiệp vụ nhưng các wrapper như `Integer`/`Boolean` thường không phân biệt được thiếu key và JSON null qua giá trị property; vẫn cần validation.
- Chỉ dùng default cho trường đã được quy định là tùy chọn; **không** mặc định API key, password, token hoặc quyền truy cập.
- Schema evolution bao gồm tên, kiểu, độ sâu, đơn vị và ý nghĩa field; `@JsonAlias` chỉ là một công cụ nhận tên cũ khi deserialize, không thay thế kế hoạch migration.
- KV v2 `metadata.version` mô tả phiên bản lưu trữ, khác `schema_version` của dữ liệu nghiệp vụ. Cần cân nhắc semantics ghi toàn bộ/PATCH/CAS để không làm mất field.
- Lỗi schema phải được phân biệt với lỗi policy, workload authentication, mạng, token/lease và rotation; không log DTO hay JSON chứa secrets.

## Tài liệu tham khảo

- [Spring Vault — `VaultKeyValueOperations` API](https://docs.spring.io/spring-vault/docs/current/api/org/springframework/vault/core/VaultKeyValueOperations.html): đọc dữ liệu KV dạng Map hoặc có kiểu.
- [Spring Vault — `VaultResponseSupport<T>` API](https://docs.spring.io/spring-vault/docs/current/api/org/springframework/vault/support/VaultResponseSupport.html): `getData()` và `getRequiredData()`.
- [Spring Vault — Vault Secrets Engines](https://docs.spring.io/spring-vault/reference/vault/vault-secret-engines.html): KV v1/KV v2 và API theo phiên bản.
- [HashiCorp Vault — KV v2 API](https://developer.hashicorp.com/vault/api-docs/secret/kv/kv-v2): `data`, `metadata`, phiên bản, CAS và thao tác đọc/ghi.
- [Jackson Annotations](https://github.com/FasterXML/jackson-annotations/wiki/Jackson-Annotations): quy tắc `@JsonSetter`, `@JsonProperty` và `@JsonAlias` theo phiên bản.
