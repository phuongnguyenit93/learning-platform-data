# Rà lại cơ chế tuần tự hóa, hợp đồng null và mô hình dữ liệu

## 1. Mục tiêu khi nâng cấp Spring Vault

Trong module **SPRING_VAULT**, ứng dụng Java giao tiếp với HashiCorp Vault bằng `VaultTemplate` / `VaultOperations` và các API chuyên biệt để đọc KV secrets, xác thực workload, quản lý token/lease, dùng Transit encryption hoặc PKI. Khi nâng phiên bản **Spring Vault**, **Spring Boot / Spring Cloud Vault**, thư viện Jackson, JDK hoặc Vault server, một lời gọi API vẫn có thể trả HTTP 200 nhưng **dữ liệu đi vào ứng dụng lại mang hình dạng khác kỳ vọng**.

Ví dụ thực tế:

- Trước đây một service đọc KV v1 bằng `VaultOperations.read("secret/orders")`; sau khi chuyển mount sang KV v2, JSON phản hồi xuất hiện lớp `data.data` và `data.metadata`.
- Code `(String) response.getData().get("maxAttempts")` ném `ClassCastException` vì trường JSON có giá trị số, không phải chuỗi.
- Trước đây khóa `clientToken` luôn có; sau thay đổi fixture hoặc chính sách, dữ liệu chứa `null`, không có khóa, hay response đọc trả `null`.
- Một bản ghi Java `record` khởi tạo từ JSON được tạo ra dù trường bắt buộc thiếu; lỗi chỉ xuất hiện khi ứng dụng gọi URL hoặc tạo kết nối.
- Một method Spring Vault mới bổ sung hợp đồng null rõ ràng; static analyzer bắt đầu cảnh báo những đoạn code trước đây giả định phản hồi không bao giờ null.
- Dùng DTO hoặc các kiểu chuyên biệt của PKI/Transit làm biến mất một số truy cập map vốn không có type safety.

Vì vậy, chủ đề **“Rà lại cơ chế tuần tự hóa, hợp đồng null và mô hình dữ liệu”** không đơn thuần là đổi package/import. Bài học hướng tới việc xây dựng **hợp đồng dữ liệu kiểm chứng được** giữa Vault và ứng dụng, bảo đảm sau nâng cấp các thao tác đúng vẫn thành công, tình huống thiếu dữ liệu được phân loại đúng, và secret không bị lộ trong thông báo lỗi.

### Sau bài học, bạn cần làm được

1. Mô tả ba tầng dữ liệu: HTTP JSON của Vault, response model của Spring Vault và DTO nghiệp vụ.
2. Phân biệt `VaultResponse`, `VaultResponseSupport<T>`, `Versioned<T>` và những API theo secrets engine.
3. Phân loại **response null**, **data null**, **field thiếu**, **field có JSON null**, **field sai kiểu** và **HTTP error**.
4. Viết code Java ánh xạ KV v2 theo đúng API mà không ép kiểu map thiếu kiểm tra.
5. Thiết kế regression tests và migration checklist cho thay đổi JSON shape, naming, kiểu dữ liệu, nullability và lỗi.

## 2. Ba hợp đồng khác nhau, không được đánh đồng

~~~mermaid
flowchart LR
    A["Vault HTTP API: JSON envelope"] --> B["Spring Vault HTTP client / Jackson"]
    B --> C["VaultResponse / VaultResponseSupport / Versioned"]
    C --> D["Mapper/validation do ứng dụng sở hữu"]
    D --> E["DTO bất biến và logic nghiệp vụ"]
    F["KV v1 / KV v2 / Transit / PKI / Database"] --> A
    G["Vault ACL + auth + version server"] --> A
~~~

| Tầng | Đầu vào / đầu ra | Bên sở hữu | Hợp đồng cần kiểm tra |
|---|---|---|---|
| HTTP Vault | JSON body, status, headers, mount path | Vault server và phiên bản API | `data`, `auth`, `lease_id`, `errors`, trường lồng nhau và mã lỗi |
| Spring Vault | `VaultResponse`, `VaultResponseSupport<T>`, `Versioned<T>`, exceptions | Spring Vault và HTTP converter được cấu hình | Nullability, typed mapping, abstraction KV, error handling |
| Application DTO | `OrdersSettings`, `DatabaseCredential`, cấu hình nghiệp vụ | Nhóm ứng dụng | Trường bắt buộc, optional, định dạng, giới hạn, validation, tính tương thích |
| Spring Cloud Vault Config Data (nếu dùng) | `Environment` / property sources | Spring Cloud Vault + Spring Boot | Kiểu giá trị và độ ưu tiên nguồn; binding lúc khởi động |
| Hạ tầng runtime | Token session, TLS, PKI certificate, pool DB | Ứng dụng + Vault + backend | Vòng đời và tính hiệu lực khác với việc JSON parse thành công |

**Cùng một JSON không phải lúc nào cũng cần tự giải bọc bằng map.** Với API `VaultOperations.read` trực tiếp, application tự biết cấu trúc HTTP. Với `opsForKeyValue(..., KV_2)`, Spring Vault đã giải quyết phần khác biệt giữa KV v1/v2. Nếu giải bọc thêm một lần ở application, bạn có thể lấy nhầm `null` dù secret tồn tại.

## 3. Chuẩn hóa thuật ngữ trước khi đánh giá compatibility

| Thuật ngữ | Ví dụ | Lỗi nếu hiểu sai |
|---|---|---|
| Serialization | Java object/Map → JSON khi `put` hoặc `write` | Tên field, null và số lượng trường gửi không đúng |
| Deserialization | JSON → `VaultResponse` / DTO | Bị sai kiểu, mất metadata, nhận default ngoài ý muốn |
| JSON envelope | `request_id`, `data`, `lease_duration` | Dữ liệu nghiệp vụ nhầm với metadata Vault |
| Business payload | `data.apiUrl` hoặc `data.data.apiUrl` | Đọc sai tầng khiến field trở thành null |
| Nullability | Method có thể trả `null` | NPE hoặc biến lỗi missing thành default |
| Backward compatibility | Client mới đọc được dữ liệu do server/fixture cũ tạo | Production fail khi rollout không đồng bộ |
| Forward compatibility | Client xử lý được field mới không có tác động nghiệp vụ | Deserialization fail vì thuộc tính lạ |
| Error contract | 403 vs 404 vs timeout vs validation | Chẩn đoán sai ACL thành “không có secret” |

Một yêu cầu nâng cấp nên liệt kê cụ thể **cặp phiên bản trước/sau**, server Vault, JDK, Jackson và starter Spring Cloud Vault. Không suy ra từ tên phiên bản rằng mọi behavior đã được giữ nguyên; cần đọc migration guide, JavaDoc và chạy test với các phiên bản thực tế trong hệ thống.

## 4. Đọc hiểu cấu trúc Vault HTTP JSON

Phản hồi JSON của nhiều Vault APIs có một số trường ở **cấp ngoài**:

~~~json
{
  "request_id": "request-id-mau",
  "lease_id": "",
  "renewable": false,
  "lease_duration": 0,
  "data": {
    "example": "value"
  },
  "auth": null,
  "warnings": null
}
~~~

Đây chỉ là **sơ đồ minh họa**, không phải mọi endpoint đều trả tất cả các field. Một số lệnh thành công có body rỗng (ví dụ HTTP 204) hoặc response shape riêng. `lease_id` có thể không có/chuỗi rỗng ở KV static nhưng tồn tại và có ý nghĩa với database dynamic credentials.

### Mô hình Spring Vault cơ bản

- `VaultResponse` là model generic dùng `Map<String, Object>` cho phần `data`.
- `VaultResponseSupport<T>` cho phép phần `data` có kiểu `T` khi API chuyên biệt hoặc typed read hỗ trợ.
- Những property như `getRequestId()`, `getLeaseId()`, `getLeaseDuration()`, `isRenewable()` và `getAuth()` thuộc envelope, **không** phải trường nghiệp vụ bên trong map `data`.
- `getData()` có thể trả `null`; ở những phiên bản hỗ trợ, `getRequiredData()` ném `IllegalStateException` khi thiếu data.
- API KV v2 versioned có thể trả `Versioned<T>` để giữ **nội dung** và **version/metadata** tách biệt.

Không nên coi `getAuth()` và `getData()` là hai alias cùng giá trị. Phản hồi tạo token có thể đặt token ở phần `auth`, trong khi đọc KV có thông tin ở `data`.

### Hai loại metadata không được trộn

1. **Envelope metadata:** request ID, lease ID, duration, warnings, wrap info ở ngoài.
2. **KV v2 metadata:** số phiên bản, thời gian tạo/xóa, trạng thái `destroyed`, custom metadata của **một phiên bản key**.

Ví dụ, `VaultResponseSupport.getMetadata()` không tự đồng nghĩa với `data.metadata` khi gọi KV v2 qua HTTP API trực tiếp. Muốn thao tác theo phiên bản, nên dùng API `VaultVersionedKeyValueOperations`.

## 5. KV v1 và KV v2: thay đổi hình dạng dữ liệu lớn nhất

Một secret logic được lưu ở key `apps/orders/settings` và mount `kv` có nội dung:

~~~json
{
  "apiUrl": "https://orders.internal.example.test",
  "maxAttempts": 3,
  "enabled": true
}
~~~

Với KV **v1**, response HTTP giả định có dạng:

~~~json
{
  "data": {
    "apiUrl": "https://orders.internal.example.test",
    "maxAttempts": 3,
    "enabled": true
  }
}
~~~

Với KV **v2**, khi gọi `GET /v1/kv/data/apps/orders/settings`:

~~~json
{
  "data": {
    "data": {
      "apiUrl": "https://orders.internal.example.test",
      "maxAttempts": 3,
      "enabled": true
    },
    "metadata": {
      "created_time": "2026-11-25T08:00:00Z",
      "deletion_time": "",
      "destroyed": false,
      "version": 2
    }
  }
}
~~~

Hai response đã rút gọn envelope để tập trung vào phần dữ liệu. **KV v2 có hai lớp `data` khi gọi HTTP trực tiếp.**

| Điều cần so sánh | KV v1 | KV v2 |
|---|---|---|
| API đọc raw | `kv/apps/orders/settings` | `kv/data/apps/orders/settings` |
| Payload raw đọc được | `response.data.apiUrl` | `response.data.data.apiUrl` |
| Metadata version | Không có mô hình version | `response.data.metadata.version` |
| Ghi raw | Body là nội dung secret | Body `{"data": {...}}`, tùy chọn CAS |
| Xóa | Theo endpoint KV v1 | Soft-delete/destroy/undelete có semantics riêng |
| Spring API khuyến nghị | `opsForKeyValue("kv", KV_1)` | `opsForKeyValue("kv", KV_2)` hoặc `opsForVersionedKeyValue("kv")` |

**Quy tắc:** nếu đã dùng `VaultKeyValueOperations` với `KV_2`, hãy đọc `getData()` ở đối tượng `VaultResponse` trả về từ **abstraction đó** thay vì tự lấy tiếp trường `"data"`. Spring Vault đảm nhiệm giải bọc KV v2. Ngược lại, khi gọi `VaultOperations.read("kv/data/...")` trực tiếp, map `getData()` còn chứa hai key `data` và `metadata`.

### Code dễ sai sau khi chuyển KV v1 → KV v2

~~~java
VaultResponse raw = vault.read("kv/data/apps/orders/settings");

// SAI: payload raw ở KV v2 không có key apiUrl ngay tầng này.
String url = (String) raw.getRequiredData().get("apiUrl");

// SAI: cast mà không xác nhận map lồng và kiểu từng phần tử.
@SuppressWarnings("unchecked")
Map<String, String> payload =
    (Map<String, String>) raw.getRequiredData().get("data");
~~~

Một `Map<String, String>` chỉ là cast erasure ở runtime; giá trị bên trong vẫn có thể là số, Boolean, map hoặc null. Việc ép kiểu thường chỉ nổ khi lấy key cụ thể.

## 6. Dùng API KV chuyên biệt để giữ hợp đồng ổn định

Khi nhiệm vụ là đọc secret logic, dùng API `VaultKeyValueOperations` giúp tách Java code khỏi khác biệt path/envelope của KV v1/v2:

~~~java
import org.springframework.vault.core.VaultKeyValueOperations;
import org.springframework.vault.core.VaultKeyValueOperationsSupport.KeyValueBackend;
import org.springframework.vault.core.VaultOperations;
import org.springframework.vault.support.VaultResponse;

VaultKeyValueOperations kv =
    vaultOperations.opsForKeyValue("kv", KeyValueBackend.KV_2);

VaultResponse response = kv.get("apps/orders/settings");

if (response == null) {
    throw new IllegalStateException("Required Vault secret is absent");
}

Object attempts = response.getRequiredData().get("maxAttempts");
~~~

Phía Java sử dụng key logic `apps/orders/settings`, không tự chèn `data/` vào tham số `get`. Cú pháp trên phù hợp kiểu API được mô tả trong tài liệu Spring Vault về `VaultKeyValueOperations`.

### Mapping trực tiếp vào DTO có kiểu

Spring Vault hỗ trợ overload `get(path, Class<T>)`. Dùng một DTO tương thích JSON:

~~~java
import com.fasterxml.jackson.annotation.JsonIgnoreProperties;

@JsonIgnoreProperties(ignoreUnknown = true)
public record OrdersSettings(
        String apiUrl,
        Integer maxAttempts,
        Boolean enabled) {

    public OrdersSettings {
        if (apiUrl == null || apiUrl.isBlank()) {
            throw new IllegalArgumentException("apiUrl is required");
        }
        if (maxAttempts == null || maxAttempts < 1 || maxAttempts > 10) {
            throw new IllegalArgumentException("maxAttempts must be 1..10");
        }
        if (enabled == null) {
            throw new IllegalArgumentException("enabled is required");
        }
    }
}
~~~

Reader:

~~~java
import java.util.Objects;

import org.springframework.vault.core.VaultKeyValueOperations;
import org.springframework.vault.core.VaultKeyValueOperationsSupport.KeyValueBackend;
import org.springframework.vault.core.VaultOperations;
import org.springframework.vault.support.VaultResponseSupport;

public final class OrdersSettingsRepository {

    private final VaultKeyValueOperations kv;

    public OrdersSettingsRepository(VaultOperations vault) {
        this.kv = Objects.requireNonNull(vault)
                .opsForKeyValue("kv", KeyValueBackend.KV_2);
    }

    public OrdersSettings loadRequired() {
        VaultResponseSupport<OrdersSettings> result =
                kv.get("apps/orders/settings", OrdersSettings.class);

        if (result == null) {
            throw new IllegalStateException("Orders settings not found");
        }

        OrdersSettings settings = result.getData();

        if (settings == null) {
            throw new IllegalStateException("Orders settings data is null");
        }

        return settings;
    }
}
~~~

Ưu điểm:

- Application xử lý `OrdersSettings` thay vì rải rác các `Map<String,Object>`.
- Phần nghiệp vụ không cần biết `data.data` của KV v2.
- DTO có ràng buộc rõ ràng cho field bắt buộc: không nhận URL rỗng hay số lần retry âm.
- Field bổ sung từ phía server được bỏ qua **theo lựa chọn chủ động** của DTO qua `@JsonIgnoreProperties(ignoreUnknown=true)`.

Cần thận trọng: Jackson có thể bọc exception do constructor validation trong exception mapping, không nhất thiết trả nguyên `IllegalArgumentException` như code trong record. Nên test theo **loại lỗi deserialization/contract ở boundary**, thay vì assert chuỗi exception quá chặt.

### Có nên cho phép unknown fields?

| Chính sách | Ưu điểm | Rủi ro |
|---|---|---|
| `ignoreUnknown=true` | Tolerant reader; thêm field metadata/nghiệp vụ mới không làm app cũ fail | Field đặt sai chính tả có thể bị bỏ qua |
| Strict unknown-field validation | Bắt lỗi nhập nhầm schema sớm | Thêm field phía Vault có thể làm client cũ fail |
| Kiểm tra schema/allowlist tường minh ở CI | Tách khả năng tương thích khỏi policy phê duyệt dữ liệu | Tốn thêm bước quản lý schema |

Không có lựa chọn mặc định đúng cho mọi hệ thống. Với credential bảo mật cao, có thể yêu cầu schema strict; với payload thường xuyên được mở rộng, có thể bỏ qua trường mới nhưng vẫn **validate tất cả field bắt buộc**.

## 7. Versioned KV v2: model dữ liệu giàu metadata

Nếu ứng dụng cần quản lý CAS/version hoặc đọc lịch sử, sử dụng `VaultVersionedKeyValueOperations`:

~~~java
import org.springframework.vault.core.VaultOperations;
import org.springframework.vault.core.VaultVersionedKeyValueOperations;
import org.springframework.vault.support.Versioned;

VaultVersionedKeyValueOperations kv =
        vaultOperations.opsForVersionedKeyValue("kv");

Versioned<OrdersSettings> versioned =
        kv.get("apps/orders/settings", OrdersSettings.class);

if (versioned == null) {
    throw new IllegalStateException("Secret version was not found");
}

OrdersSettings settings = versioned.getData();
if (settings == null) {
    throw new IllegalStateException(
        "Version exists without readable data (deleted/destroyed?)");
}

Versioned.Version version = versioned.getVersion();
// Kiểm tra version theo contract, không log nội dung secret.
~~~

Ở đây `versioned.getData()` có thể là `null` với trạng thái liên quan xóa/hủy phiên bản. `versioned.getMetadata()` có thể cung cấp metadata theo model của Spring Vault. Để ghi với CAS, tham khảo đúng API `Versioned.create(...)` / `put(...)` đang dùng: metadata version và điều kiện ghi phải được quản lý có chủ đích.

**Không ánh xạ** `Versioned<OrdersSettings>` thành `OrdersSettings` rồi vứt version nếu ứng dụng cần tránh lost update. Khả năng giữ metadata và kiểm soát CAS là một phần hợp đồng quan trọng khi nâng từ KV v1 sang KV v2.

## 8. Phân loại null: ít nhất sáu trường hợp khác nhau

Ở boundary với Vault, `null` có nhiều nguồn và nhiều ý nghĩa.

| Tình huống | Ví dụ | Ứng dụng nên xử lý |
|---|---|---|
| **Không có response đọc** | `kv.get(path) == null` cho path không tồn tại | Phân loại `SecretNotFound` / fallback được phê duyệt |
| **Có response nhưng `data == null`** | Envelope không có payload | Phân biệt endpoint trả metadata với secret bắt buộc thiếu |
| **Map có key nhưng giá trị null** | `{"enabled":null}` | Xác nhận có phải giá trị bị cấm theo schema |
| **Map không có key** | `{"apiUrl":"..."}` thiếu `enabled` | Lỗi schema hoặc default rõ ràng do app định nghĩa |
| **Danh sách rỗng / chuỗi rỗng** | `[]` / `""` | Không được coi luôn là “không có data”; validate theo nghiệp vụ |
| **Typed mapping tạo đối tượng với field null** | `new OrdersSettings(..., null)` khi thiếu validation | Cần validate trước khi dùng |
| **KV version bị deleted/destroyed** | Version metadata còn nhưng data không đọc được | Xem lifecycle KV v2, không đánh đồng với secret chưa từng có |
| **HTTP 403, timeout, TLS fail** | Vault không cho đọc hoặc không kết nối được | Đây **không** phải `null`; xử lý exception riêng |

**Nguyên tắc cốt lõi:** “không tồn tại” khác “không được quyền đọc” và khác “không đọc được do sự cố”. Nếu một catch block chuyển mọi exception thành `Optional.empty()`, ứng dụng có thể che lỗi ACL hoặc mất kết nối, rồi kích hoạt fallback nguy hiểm.

### Java: phân biệt absent key và explicit null

~~~java
import java.util.Map;

Map<String, Object> payload = response.getRequiredData();

if (!payload.containsKey("enabled")) {
    throw new IllegalStateException("Missing required field: enabled");
}

Object enabledValue = payload.get("enabled");

if (enabledValue == null) {
    throw new IllegalStateException("enabled must not be null");
}

if (!(enabledValue instanceof Boolean enabled)) {
    throw new IllegalStateException("enabled must be JSON boolean");
}

// enabled có giá trị true/false và đã qua kiểm tra kiểu.
~~~

`Map.get("enabled") == null` không cho biết key vắng mặt hay có giá trị JSON null. Phải dùng `containsKey` khi sự khác biệt đó quan trọng cho contract.

Nếu contract cho phép giá trị `enabled` bị bỏ qua và sử dụng default, hãy ghi default tường minh và có test, ví dụ phiên bản schema cũ chưa có field. Không tự thay `null` bằng `false` nếu điều đó có thể làm thay đổi quyền truy cập hay hành vi bảo mật.

## 9. Hợp đồng trả về của Spring Vault có thể thay đổi theo phiên bản

Khi nâng Spring Vault, cần xem **JavaDoc của phiên bản đích** thay vì dựa vào kinh nghiệm hoặc compiler warning.

| API | Hợp đồng quan trọng | Điểm kiểm tra khi upgrade |
|---|---|---|
| `VaultOperations.read(String)` | Có thể trả `null` khi path không tồn tại | Caller đã kiểm tra null trước `getData()` chưa? |
| `VaultOperations.read(String, Class<T>)` | Có thể trả `VaultResponseSupport<T>` hoặc null | DTO có hợp đồng null của field không? |
| `VaultKeyValueOperations.get(String)` | Có thể trả `VaultResponse` hoặc null | Đang dùng KV version đúng và key logic đúng? |
| `VaultKeyValueOperations.get(String, Class<T>)` | Typed deserialization, có thể null | DTO Jackson constructor/record có tương thích? |
| `VaultVersionedKeyValueOperations.get(...)` | Có thể trả `Versioned<T>` hoặc null; data có thể vắng theo trạng thái version | Có cần phân biệt deleted/destroyed và metadata? |
| `VaultOperations.list(String)` | Có thể trả null khi path không có entries | Caller có phân biệt null với list rỗng không? |
| `VaultResponseSupport.getData()` | Data nullable trong tài liệu mới | Có đang dereference mặc định? |
| `VaultResponseSupport.getRequiredData()` | Ném `IllegalStateException` khi data null | Chỉ dùng khi secret bắt buộc phải hiện diện |
| `VaultResponseSupport.hasData()` | Phương thức tiện ích ở một số phiên bản mới (ví dụ 4.1) | Không copy sang version cũ nếu API chưa tồn tại |
| `VaultOperations.readRequired(...)` | API trợ giúp ở nhánh mới (ví dụ 4.x) | Không dùng khi code vẫn phải build trên version cũ |

**Quan trọng:** annotations `@Nullable` hiển thị trong JavaDoc có thể thay đổi về hệ thống annotation khi nâng phiên bản. Compiler Java không tự làm giá trị trở nên non-null; thay đổi của NullAway, Checker Framework, JSpecify hoặc IDE có thể khiến code bắt đầu báo lỗi đúng chỗ từng bị bỏ qua.

Đối với một SDK hỗ trợ nhiều major versions, nên chọn giao diện chung ổn định hoặc định nghĩa adapter nội bộ. Không chèn method mới vào shared source module khi một môi trường production vẫn chạy thư viện cũ.

## 10. Dữ liệu số, Boolean và timestamp: không được ép kiểu tùy tiện

Vault JSON có số, chuỗi, Boolean, object, array. Khi parse về `Map<String,Object>`, kiểu số cụ thể phụ thuộc JSON converter và cấu hình:

- `"maxAttempts": 3` có thể trở thành `Integer`, `Long` hoặc kiểu số khác; không giả định lúc nào cũng là `Integer`.
- `"maxAttempts": "3"` là **chuỗi** và cần một quyết định compatibility rõ ràng trước khi chuyển thành số.
- `"enabled": true` là Boolean; `"enabled": "true"` là chuỗi và có thể làm app hiểu sai kiểu.
- `"created_time": "2026-11-25T08:00:00Z"` là timestamp ISO-8601; không cast trực tiếp thành `Instant` nếu mapper chưa được cấu hình.
- `lease_duration` trong envelope là thời lượng dạng **giây** trong JSON API; không được coi số 3600 là mili-giây.
- TTL request có thể biểu diễn bằng chuỗi như `"1h"`, còn TTL response có thể là số giây; không dùng cùng một parser mù quáng.

### Mapping số an toàn khi phải đọc Map

~~~java
import java.math.BigDecimal;

Object raw = payload.get("maxAttempts");

if (!(raw instanceof Number number)) {
    throw new IllegalStateException("maxAttempts must be JSON number");
}

// Sử dụng BigDecimal để tránh làm tròn khi có số thực.
// intValueExact sẽ ném ArithmeticException khi không là số nguyên
// hoặc nằm ngoài phạm vi int.
int attempts;
try {
    attempts = new BigDecimal(number.toString()).intValueExact();
} catch (NumberFormatException | ArithmeticException ex) {
    throw new IllegalStateException(
        "maxAttempts is not an exact integer", ex);
}

if (attempts < 1 || attempts > 10) {
    throw new IllegalStateException("maxAttempts out of range");
}
~~~

Ví dụ trên cũng phải được điều chỉnh nếu data source cho phép số dạng chuỗi như `"3"`. Không dùng `String.valueOf(raw)` rồi parse tràn lan: với `null` nó trả chuỗi `"null"`, che mất ý nghĩa thiếu dữ liệu; với số thập phân có thể làm đổi giá trị nếu chuyển không kiểm soát.

### Nhận timestamp theo model đúng

Nếu cần đọc metadata KV v2, có thể dùng `Versioned.Metadata`; khi parse raw string, dùng `Instant.parse(...)` sau khi xác nhận là chuỗi ISO-8601 hợp lệ. Cần giữ timezone UTC và precision phù hợp, không giả định timestamp từ Vault là local time của máy chạy ứng dụng.

## 11. Khi ghi dữ liệu: serialization cũng là một hợp đồng

Với KV v2, `VaultKeyValueOperations.put(path, Object)` chấp nhận object được serialize vào body theo abstraction của Spring Vault. Ví dụ:

~~~java
VaultKeyValueOperations kv =
        vaultOperations.opsForKeyValue("kv", KeyValueBackend.KV_2);

OrdersSettings desired = new OrdersSettings(
        "https://orders.internal.example.test", 3, true);

kv.put("apps/orders/settings", desired);
~~~

Ghi bằng model có tên thuộc tính rõ ràng và đọc lại thành cùng DTO là cách kiểm tra roundtrip.

Nếu thay vì API KV chuyên biệt bạn gọi `VaultOperations.write` trực tiếp, Vault KV v2 yêu cầu body dạng:

~~~json
{
  "data": {
    "apiUrl": "https://orders.internal.example.test",
    "maxAttempts": 3,
    "enabled": true
  }
}
~~~

Ví dụ:

~~~java
vaultOperations.write(
    "kv/data/apps/orders/settings",
    java.util.Map.of("data", java.util.Map.of(
        "apiUrl", "https://orders.internal.example.test",
        "maxAttempts", 3,
        "enabled", true)));
~~~

**Không gửi cùng một object theo hai API mà không kiểm tra envelope.** Nếu đưa `{"data": {...}}` vào `kv.put(...)`, Spring Vault có thể lưu một key nghiệp vụ có tên `data` hoặc tạo hình dạng ngoài ý muốn vì abstraction đã tự xử lý phần bọc KV v2.

### Vấn đề Jackson khi nâng cấp

Cần đánh giá:

1. **Tên field:** camelCase, snake_case, `@JsonProperty`, naming strategy toàn cục.
2. **Constructor/record:** Jackson version có hỗ trợ record/creator đang dùng không?
3. **Null serialization:** `@JsonInclude` hay global inclusion có bỏ qua null fields không?
4. **Unknown properties:** strict hay tolerant reader?
5. **Date/time module:** mapping `Instant`, `Duration`, Java Time module và timezone.
6. **Enum:** unknown enum value nên fail hay map theo giá trị dự phòng?
7. **Binary:** `byte[]` thường được JSON converter biểu diễn Base64; không được giả định chuỗi đang ở UTF-8 nguyên thủy.
8. **Property visibility:** getters/fields khác nhau có thể khiến JSON output đổi.
9. **Polymorphic types:** không bật default typing không tin cậy cho dữ liệu secret mà không kiểm soát nguồn và subtype.
10. **ObjectMapper ownership:** custom `ObjectMapper` của Spring Boot có thể khác mapper thật mà Spring Vault HTTP converter đang dùng; cần kiểm thử **qua Vault client thật**, không chỉ serialize bằng một mapper trong unit test.

Không tạo DTO nghiệp vụ bằng `Map<String,Object>` chỉ vì dễ viết; khả năng mở rộng tên field và lỗi runtime sẽ khó kiểm soát khi schema thay đổi.

## 12. Phân biệt hợp đồng “nullable” và “optional”

Một API có thể thiếu secret vì nhiều lý do, nhưng ứng dụng phải định nghĩa hành vi:

| Ngữ cảnh | Contract nên dùng | Lý do |
|---|---|---|
| `spring.datasource.password` bắt buộc khi khởi động | **Required**: fail-fast nếu thiếu | Không kết nối được database hoặc fallback nhầm credentials |
| Cờ tính năng không quan trọng | **Optional** với default đã duyệt | Cho phép triển khai dần mà không vỡ startup |
| Token của workload | Required và quản lý vòng đời ở SessionManager | Không được fallback sang root token |
| Database dynamic credentials | Required username/password + lease metadata | Không được coi password trống là thành công |
| Transit ciphertext | Required và giữ đúng định dạng `vault:vN:...` | Không thể decrypt nếu payload không hợp lệ |
| PKI certificate/private key | Required theo endpoint, kiểm tra SAN/validity | Không dùng chứng thư thiếu key hoặc sai mục đích |
| KV version đã bị destroy | Có thể không đọc được data, cần thể hiện trạng thái | Không đồng nhất với chưa từng tồn tại |

Có hai lựa chọn thường gặp trong repository:

- `loadRequired()` trả DTO non-null và **ném ngoại lệ có kiểm soát** khi secret không tồn tại hoặc sai schema.
- `findOptional()` trả `Optional<DTO>` **chỉ** khi “không tìm thấy” là kết quả được cho phép của nghiệp vụ.

Không viết:

~~~java
// Anti-pattern: mọi lỗi Vault đều biến thành "không có secret".
try {
    return Optional.ofNullable(kv.get("apps/orders/settings"));
} catch (Exception ignored) {
    return Optional.empty();
}
~~~

Hậu quả: một lỗi 403, TLS handshake hay server unavailable khiến ứng dụng tin rằng secret không tồn tại. Nếu service tiếp tục với default hoặc quyền rộng hơn, đây có thể là lỗi an toàn nghiêm trọng.

Với `VaultOperations.readRequired(...)` ở phiên bản hỗ trợ, API có thể ném `SecretNotFoundException` khi path vắng; nhưng code đang phải tương thích Spring Vault 3.x không nên dùng method được giới thiệu ở nhánh 4.x.

## 13. HTTP status, lỗi JSON và lỗi client khác nhau

Khi quan sát một exception, cần phân loại **tầng gây lỗi** trước khi đưa ra quyết định fallback hoặc retry:

| Biểu hiện | Tầng | Cách diễn giải |
|---|---|---|
| `null` từ `get(path)` | Contract của method đọc | Có thể là path không tồn tại; kiểm tra mount, role và fixture |
| HTTP 404 từ endpoint raw | Vault HTTP/engine | Không tìm thấy path/key/version; kiểm tra liệu abstraction trả null hay ném exception |
| HTTP 403 `permission denied` | ACL/auth | Không phải null và không có lý do bỏ qua chính sách |
| HTTP 400 với `errors` | Request validation/engine | Payload, body, role, version hoặc schema không hợp lệ |
| Timeout, SSL, connection refused | Transport | Có thể Vault chưa nhận request; retry có giới hạn theo idempotency |
| Jackson mapping exception | Converter/model | JSON không phù hợp constructor/field type |
| `ClassCastException` | Code tự ép kiểu | Thường do map mất type safety, không nhất thiết lỗi Vault |
| `IllegalStateException` từ `getRequiredData()` | Contract required data | Response thiếu phần data cần thiết |
| Secret exists nhưng `enabled == null` | Business payload | Schema thiếu hoặc JSON null, cần validation |

Một negative test chỉ dùng `assertThrows(Exception.class)` là chưa đủ: nó có thể pass vì Vault offline chứ không phải do schema/ACL muốn kiểm tra.

**Đừng retry vô hạn lệnh ghi KV, cấp PKI certificate hoặc sinh dynamic database credentials.** Request đầu có thể đã thành công trên Vault nhưng client mất response, dẫn đến side effect lặp lại. Việc deserialization sau một request POST lỗi không luôn đồng nghĩa request chưa xảy ra.

### Phân biệt khi dùng Spring Cloud Vault

Spring Cloud Vault có thể nạp key thành property source trong giai đoạn Config Data. Khi value đi qua Spring Boot binding (`@ConfigurationProperties`), lỗi có thể chuyển từ Jackson mapping sang **conversion/binding exception**. Vì vậy cần test riêng:

- Thao tác `VaultTemplate` / `VaultKeyValueOperations` tại runtime.
- Cấu hình `spring.config.import=vault://` tại startup.
- Property precedence và lỗi binding khi cùng key nằm ở nhiều sources.

Không giả định việc một DTO đọc được ở runtime chứng minh `@ConfigurationProperties` sẽ bind cùng kiểu/semantics.

## 14. Soát mô hình dữ liệu cho từng secrets engine

Không có một `VaultResponse<Map<String,Object>>` đủ tốt cho mọi endpoint:

| Engine/endpoint | Dữ liệu/loại đáng quan tâm | Rủi ro sau upgrade |
|---|---|---|
| KV v1 | `data` là map nghiệp vụ | Data keys đổi kiểu, missing fields |
| KV v2 | `data.data` + `data.metadata` (raw); `Versioned<T>` (typed) | Sai lớp bọc, bỏ mất version/CAS, deleted states |
| Transit encrypt/decrypt | Plaintext Base64 (HTTP API), ciphertext `vault:vN:...` | Nhầm byte[] với text, charset/default charset, mất context |
| PKI issue/sign | PEM certificate, private key, serial, lease info | Không validate chuỗi CA, SAN, validity; lộ private key |
| Database dynamic creds | `username`, `password`, lease ID, duration, renewable | Password null, lease seconds sai đơn vị, mất renewal |
| Kubernetes/AppRole login | `auth.client_token` / auth metadata | Đọc nhầm `data.client_token`, token bị log |
| System API ACL policies | `data.policy` / các field khác theo endpoint | Lẫn legacy `sys/policy` và `sys/policies/acl` |
| Token/lease APIs | Metadata TTL, policies, flags | Nhầm nullable, số giây và boolean |

### Transit: tính nhị phân

Khi dùng raw Transit HTTP API, `plaintext` đầu vào phải được Base64-encode. Spring Vault cung cấp types `Plaintext`, `Ciphertext` và `VaultTransitOperations` để xử lý dữ liệu binary an toàn hơn. Không dùng `new String(bytes)` với default charset hoặc serialize byte[] theo assumption tùy tiện; khi cần conversion String phải chọn `StandardCharsets.UTF_8` một cách rõ ràng.

### PKI: metadata khác bí mật

Spring Vault cung cấp `VaultPkiOperations` và model `CertificateBundle`/response chuyên biệt. Nếu sau nâng cấp API chuyển sang typed certificate model, không viết code chỉ kiểm tra “response có string certificate”; cần xác minh private key (khi endpoint issue trả key), SAN, issuer, NotAfter và chuỗi tin cậy. Không log toàn bộ object certificate response vì có thể chứa private key.

### Database credentials: dữ liệu gắn với lease

Một username/password hợp lệ không đủ: cần biết lease ID, duration và khả năng renewal để lập lịch xoay credential. Chuyển model `VaultResponse` sang DTO chỉ chứa hai string mà vứt lease metadata sẽ khiến application mất khả năng quản lý lifecycle. JDBC pool phải được thiết kế chuyển credential an toàn, không tự cập nhật chỉ vì JSON đã parse thành công.

## 15. Quy trình rà soát khi nâng cấp thư viện

Một quy trình có thể lặp lại, thay vì chỉ “nâng dependency rồi build xanh”:

~~~mermaid
flowchart TD
    A["Chốt baseline: Vault / Spring Vault / Jackson / JDK"] --> B["Liệt kê API và DTO đang sử dụng"]
    B --> C["Đọc JavaDoc, migration notes, nullability"]
    C --> D["So sánh JSON envelopes và field types"]
    D --> E["Chạy unit contract tests: JSON fixtures"]
    E --> F["Chạy integration tests trên Vault thật"]
    F --> G{"Missing, null, error và version đều pass?"}
    G -->|Không| H["Sửa adapter/DTO + migration test"]
    H --> E
    G -->|Có| I["Canary deploy, metrics/log an toàn"]
    I --> J["Rollback theo runbook nếu phát hiện regressions"]
~~~

### Bước 1 — Inventory các API mà project gọi

Tìm những nơi đang dùng `VaultOperations.read/write/list`, `opsForKeyValue`, `opsForVersionedKeyValue`, `opsForTransit`, `opsForPki` và `VaultResponse`. Đặc biệt chú ý:

- `Map<String,Object>` với cast trực tiếp `(String)` / `(Map)` / `(Long)`.
- `response.getData().get(...)` không kiểm tra null.
- Code parse JSON envelope bằng logic tự viết.
- Fallback `catch (Exception) { ... }`.
- Entity/DTO mới được bind từ `@ConfigurationProperties` sau khi import Vault.
- DTO có secret trong `toString()`, `equals`, logger hoặc exception message.

### Bước 2 — Chốt phiên bản và điểm khác biệt

Lập bảng:

| Hạng mục | Phiên bản hiện tại | Phiên bản mục tiêu | Việc cần chứng minh |
|---|---|---|---|
| Vault server | Điền thực tế | Điền thực tế | API response/status không đổi ngoài phạm vi đã duyệt |
| Spring Vault | Điền thực tế | Điền thực tế | Method/annotation/model còn phù hợp |
| Spring Boot / Spring Cloud Vault | Điền thực tế | Điền thực tế | Config Data/property binding tương thích |
| Jackson | Điền thực tế | Điền thực tế | Records, timestamps, unknown fields, null behavior ổn định |
| JDK | Điền thực tế | Điền thực tế | Serialization reflection/records/modules không vỡ |
| Auth method | Điền thực tế | Điền thực tế | Workload token còn policy đúng, TTL đúng |
| KV mounts/engine | v1/v2 từng mount | Mount sau upgrade | JSON shape và path semantics đúng |

Không tự điền số phiên bản nếu không có dependency tree/BOM của dự án. Những ví dụ trong bài là **hợp đồng API đã được mô tả trong tài liệu chính thức**, không phải một compatibility matrix đủ cho mọi tổ hợp version.

### Bước 3 — So sánh dữ liệu theo từng trạng thái

Bắt buộc test:

- Object đầy đủ.
- Object có field mới không dùng.
- Thiếu một field optional.
- Thiếu một field required.
- Field required có JSON null.
- Field có kiểu sai: số thành chuỗi, Boolean thành chuỗi.
- Boundary value: số ngoài phạm vi, chuỗi rỗng, TTL bằng 0.
- 404/missing secret và KV v2 version đã xóa/hủy.
- 403/invalid token và lỗi transport.
- Secret có version mới, ghi CAS và đọc version cũ khi dùng KV v2.
- Mã hóa nhị phân Transit và certificate PKI nếu ứng dụng có dùng.

### Bước 4 — Đọc lại output và đo tác động

Sau khi ghi lại secret hoặc dùng converter mới, phải xác nhận raw JSON thật ở Vault test, không chỉ roundtrip cùng một mapper giả lập. Có trường hợp cả write/read trong unit test dùng cùng logic sai nên vẫn pass, nhưng production workload khác đọc secret sẽ fail.

## 16. Unit contract tests cho JSON schema

Các test dưới đây dùng Jackson với DTO `OrdersSettings` ở trên. Chúng chứng minh contract của **DTO**, nhưng không thay thế test qua Vault HTTP client thật.

~~~java
import static org.junit.jupiter.api.Assertions.*;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;

class OrdersSettingsJsonContractTest {

    private final ObjectMapper mapper = new ObjectMapper();

    @Test
    void acceptsKnownFieldsAndIgnoresApprovedNewField() throws Exception {
        String json = """
            {
              "apiUrl": "https://orders.internal.example.test",
              "maxAttempts": 3,
              "enabled": true,
              "newServerField": "metadata-only"
            }
            """;

        OrdersSettings settings =
                mapper.readValue(json, OrdersSettings.class);

        assertEquals(3, settings.maxAttempts());
        assertTrue(settings.enabled());
    }

    @Test
    void rejectsMissingRequiredBoolean() {
        String json = """
            {
              "apiUrl": "https://orders.internal.example.test",
              "maxAttempts": 3
            }
            """;

        assertThrows(JsonProcessingException.class,
                () -> mapper.readValue(json, OrdersSettings.class));
    }

    @Test
    void rejectsExplicitNullBoolean() {
        String json = """
            {
              "apiUrl": "https://orders.internal.example.test",
              "maxAttempts": 3,
              "enabled": null
            }
            """;

        assertThrows(JsonProcessingException.class,
                () -> mapper.readValue(json, OrdersSettings.class));
    }

    @Test
    void rejectsInvalidAttemptCount() {
        String json = """
            {
              "apiUrl": "https://orders.internal.example.test",
              "maxAttempts": 0,
              "enabled": true
            }
            """;

        assertThrows(JsonProcessingException.class,
                () -> mapper.readValue(json, OrdersSettings.class));
    }
}
~~~

Những ca trên kiểm thử behavior của record constructor/Jackson trên phiên bản đang chạy. Khi nâng Jackson, chạy lại để xác định exception class và cấu hình creator có còn giống kỳ vọng. Không hardcode nội dung exception vì có thể chứa source JSON hoặc trường secret.

**Một chỗ cần chú ý về strict typing:** Jackson có thể mặc định **coerce** một chuỗi `"3"` thành `Integer 3` hoặc chuỗi `"true"` thành Boolean trong một số cấu hình. Nếu contract yêu cầu từ chối kiểu JSON không đúng tuyệt đối, cần **cấu hình coercion/mapper rõ ràng hoặc validate ở tầng JsonNode** rồi kiểm thử. Đừng chỉ dựa vào kiểu trường DTO để coi input string đã bị từ chối.

## 17. Integration tests với Vault thật

Cần chạy một Vault test instance (chẳng hạn dev container qua Testcontainers) và chuẩn bị KV v2 mount `kv-it`, fixture cùng workload token có `read`. Test tiếp theo chứng minh overload typed KV thực sự giải bọc đúng `data.data`:

~~~java
import static org.junit.jupiter.api.Assertions.*;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.vault.core.VaultKeyValueOperations;
import org.springframework.vault.core.VaultKeyValueOperationsSupport.KeyValueBackend;
import org.springframework.vault.core.VaultOperations;
import org.springframework.vault.support.VaultResponseSupport;

@SpringBootTest
class VaultDataContractIT {

    @Autowired
    VaultOperations vault;

    @Test
    void typedKvV2ReadUsesBusinessPayload() {
        // Fixture chuẩn bị key apps/orders/settings trong mount kv-it.
        VaultKeyValueOperations kv =
            vault.opsForKeyValue("kv-it", KeyValueBackend.KV_2);

        VaultResponseSupport<OrdersSettings> response =
            kv.get("apps/orders/settings", OrdersSettings.class);

        assertNotNull(response);
        OrdersSettings data = response.getData();
        assertNotNull(data);
        assertEquals("https://orders.internal.example.test", data.apiUrl());
        assertEquals(3, data.maxAttempts());
        assertTrue(data.enabled());
    }

    @Test
    void missingPathIsNotAnEmptySettingsObject() {
        VaultKeyValueOperations kv =
            vault.opsForKeyValue("kv-it", KeyValueBackend.KV_2);

        VaultResponseSupport<OrdersSettings> result =
            kv.get("apps/orders/not-created", OrdersSettings.class);

        assertNull(result);
    }
}
~~~

**Điều kiện cần:** `@SpringBootTest` phải nối tới đúng Vault test (không phải production) bằng workload token, fixture đã tạo mount/secret với payload phù hợp trước khi context đọc nó. Nên chạy test 403 riêng bằng một token thực sự thiếu quyền và xác nhận loại exception/HTTP status; test missing key không thay thế test quyền.

Một bộ regression tests tốt còn xác minh:

| Test ID | Fixture | Bằng chứng pass |
|---|---|---|
| K01 | KV v1 + secret hợp lệ | Typed get trả đúng DTO |
| K02 | KV v2 + secret hợp lệ | Typed get bỏ envelope đúng, metadata version không làm bẩn DTO |
| K03 | KV v2 version cũ và version mới | `Versioned<T>` trả đúng version, CAS không bị bỏ qua |
| K04 | Key chưa từng được tạo | Read trả null hoặc dedicated not-found theo API đã chọn |
| K05 | Key bị soft-delete/destroy | Xử lý theo lifecycle KV v2, không dùng dữ liệu stale |
| K06 | Token không có `read` | Vault từ chối; không chuyển thành empty/null |
| K07 | Trường mới không nhạy cảm | Tolerant DTO vẫn parse và required fields hợp lệ |
| K08 | Trường required bị thiếu/JSON null | Validation fail có kiểm soát |
| K09 | Số/boolean sai kiểu | Fail hoặc coerce theo rule đã được phê duyệt |
| K10 | Ghi typed DTO rồi đọc qua raw API | JSON shape đúng `data.data`, không double-wrapping |
| K11 | Transit binary roundtrip | Byte arrays không mất dữ liệu do encoding |
| K12 | PKI/DB response | Không mất certificate/lease metadata; không log private key/password |

Với các test có secret, log chỉ ghi type, test ID, outcome, Vault request ID khi nhận được và thời gian; không log DTO đầy đủ hoặc response body.

## 18. Cách tổ chức adapter để giảm rủi ro nâng cấp

Thay vì để mọi service gọi Vault và đọc map trực tiếp, cô lập logic ở một adapter:

~~~mermaid
flowchart TD
    A["Service nghiệp vụ"] --> B["OrdersSettingsPort: loadRequired"]
    B --> C["SpringVaultOrdersSettingsAdapter"]
    C --> D["VaultKeyValueOperations KV_2"]
    D --> E["Vault HTTP API"]
    C --> F["Validate OrdersSettings / map lỗi"]
    G["DTO contract tests"] --> F
    H["Vault Testcontainers IT"] --> C
    I["Migration/compatibility test"] --> D
~~~

Adapter nên có:

- **Output rõ kiểu:** trả `OrdersSettings`, không trả generic `Map`.
- **Input rõ nghĩa:** key logic được kiểm soát, không nhận tùy ý toàn bộ Vault path từ HTTP request ngoài.
- **Null/error policy:** phân biệt missing secret được cho phép hay bị lỗi; không swallow 403.
- **Validation tại boundary:** xử lý required/optional fields, range, format.
- **Logging an toàn:** chỉ operation, path template, trạng thái, request ID; không log secret.
- **Schema version policy:** nếu có thay đổi không tương thích, dùng key/field schema version hoặc migrator được duyệt.
- **Test kép:** unit JSON contract + integration Vault thật.
- **Tương thích hướng nâng cấp:** tránh phụ thuộc vào một helper method chỉ có ở major mới khi phải hỗ trợ major cũ.

**Không đóng băng implementation detail thành API ứng dụng.** Ví dụ service nghiệp vụ không nên biết `VaultResponseSupport#getData()` hay `Versioned#getMetadata()`; service chỉ cần dữ liệu đã validate hoặc một business error ổn định.

## 19. Quan sát và xử lý sự cố sau nâng cấp

| Biểu hiện | Nghi ngờ | Kiểm tra |
|---|---|---|
| NPE sau nâng Spring Vault | API đọc/data bắt đầu được kiểm tra null rõ ràng; caller thiếu guard | JavaDoc, nullable annotation, stack trace đã lọc |
| ClassCastException với số | Map từ JSON giữ kiểu Number chứ không phải String/Long mong đợi | Xem schema/JSON fixture, dùng Number + validate |
| DTO parse fail sau thêm field | Strict unknown-field setting | Quyết định tolerant/strict rõ ràng, migration test |
| DTO parse thành công nhưng field null | Thiếu field/JSON null/record constructor không validate | Test schema required fields |
| App đọc KV v2 trả map chứa `data` | Dùng raw `VaultOperations.read` và giải bọc sai | Chuyển sang KV_2 hoặc đọc đúng tầng raw |
| Metadata version mất | Chuyển từ Versioned API về generic KV get | Dùng `VaultVersionedKeyValueOperations` nếu cần CAS |
| 403 bị báo là secret missing | Catch-all exception → Optional.empty | Tách HTTP/auth errors khỏi absent |
| Missing secret không được phát hiện | Dùng default business không được duyệt | Fail-fast hoặc optional contract tường minh |
| Lease renew fail sau nâng cấp | Bỏ lease metadata trong DTO; thời lượng sai đơn vị | Kiểm tra `lease_id` / `lease_duration` và event |
| Transit decrypt lỗi với dữ liệu UTF-8 | Binary chuyển thành String theo default charset | Dùng `Plaintext` / `Ciphertext` và charset tường minh |
| PKI certificate không dùng được | DTO bỏ SAN/issuer/validity, role/issuer thay đổi | Parse X.509, kiểm tra chain và EKU |
| Unit tests pass nhưng production fail | Mock không mô phỏng Vault envelope/ACL hoặc Jackson thực | Chạy Vault integration test với phiên bản mục tiêu |

### Logging và metrics gợi ý

- Đếm `vault_read_contract_failures_total` theo `engine`, `schema`, `reason` có số lượng giá trị giới hạn.
- Đo `vault_client_request_duration_seconds` và outcome để phân biệt lỗi mạng với lỗi mapping.
- Dùng `request_id` của Vault trong log điều tra khi response có ID, không đưa ID vào metric labels.
- Không log raw JSON, token, database password, PKI private key, Transit plaintext/ciphertext hoặc toàn bộ DTO.
- Khi test fixture thất bại, báo endpoint template, engine, môi trường thử nghiệm và loại lỗi, **không in secret values**.

Việc chuyển field sang non-null không có nghĩa production dữ liệu cũ chắc chắn đã thỏa contract. Trước rollout, rà soát/migrate các key đang tồn tại (qua quy trình kiểm soát an toàn) và có canary deployment để quan sát lỗi sớm.

## 20. Bài thực hành

### Bài A — Sửa reader KV v2 bị double unwrap

Cho code:

~~~java
VaultResponse response = vault.opsForKeyValue(
    "kv", KeyValueBackend.KV_2)
    .get("apps/orders/settings");

Map<?, ?> nested = (Map<?, ?>) response.getData().get("data");
String url = (String) nested.get("apiUrl");
~~~

Yêu cầu: giải thích vì sao đoạn trên có thể `null`/`ClassCastException` dù secret hợp lệ; sửa thành `response.getRequiredData().get("apiUrl")` có kiểm tra kiểu, hoặc dùng `get(path, OrdersSettings.class)` rồi validate.

**Tiêu chí đạt:** trả đúng `OrdersSettings` ở KV v2, không dùng raw cast nguy hiểm, và báo lỗi có kiểm soát nếu path hoặc field không tồn tại.

### Bài B — Thêm contract null rõ ràng

Tạo bốn JSON payloads: đủ field, thiếu `enabled`, `enabled=null`, `maxAttempts="3"`. Chọn chính sách strict/tolerant và viết JUnit assertions tương ứng. Dùng một DTO với constructor validation và chứng minh coercion được kiểm soát trong mapper thực tế.

**Tiêu chí đạt:** không có trường hợp bắt buộc nào âm thầm nhận null hoặc giá trị sai kiểu ngoài chính sách.

### Bài C — Kiểm tra KV v1 → KV v2

Dựng Vault test container, tạo hai mounts `kv1` và `kv2` với dữ liệu tương đương, so sánh raw HTTP JSON, `VaultKeyValueOperations` và `VaultVersionedKeyValueOperations`. Kiểm tra path `data/`, metadata và ít nhất một version cũ.

**Tiêu chí đạt:** layer nghiệp vụ nhận DTO tương đương cho cùng schema, nhưng adapter vẫn giữ version metadata khi cần.

### Bài D — Regression cho Transit, PKI hoặc database

Chọn một engine ứng dụng đang dùng. Viết test payload đúng, payload sai và thiếu dữ liệu; bảo đảm không lộ secret trong log. Nếu chọn database, kiểm tra lease duration tính bằng giây và credential được rotate; nếu chọn PKI, kiểm tra X.509 SAN, serial, validity; nếu chọn Transit, kiểm tra binary roundtrip và Base64.

**Tiêu chí đạt:** xác minh cả giá trị, kiểu dữ liệu, metadata và semantics của lỗi.

## 21. Câu hỏi tự kiểm tra

1. Vì sao response KV v2 có `data.data` ở HTTP raw nhưng `kv.get(...)` có thể trả payload đã được giải bọc?
2. `response == null`, `response.getData() == null` và `response.getData().get("enabled") == null` có luôn cùng ý nghĩa không?
3. Vì sao `Map<String,String>` cast từ JSON map không bảo vệ khỏi `ClassCastException` cho một field dạng số?
4. Khi muốn ghi có CAS hoặc đọc version cũ, nên dùng `VaultKeyValueOperations` hay `VaultVersionedKeyValueOperations`?
5. `getRequiredData()` khác `getData()` như thế nào khi data null?
6. Vì sao việc thêm một field mới có thể làm một số DTO bị fail deserialization dù HTTP status vẫn 200?
7. Một lỗi 403 có nên được chuyển thành `Optional.empty()` để ứng dụng dùng secret mặc định không?
8. Khi JSON chứa số `3600` trong `lease_duration`, đơn vị là giây hay mili-giây?
9. Nếu một unit test dùng cùng ObjectMapper để ghi/đọc đều pass, vì sao vẫn cần Vault integration test?
10. Làm thế nào chặn giá trị credential và private key xuất hiện trong log khi validator báo lỗi?

## 22. Tổng kết

Khi **nâng cấp và kiểm tra tương thích** trong **SPRING_VAULT**, hãy xem serialization, nullability và data model là các **hợp đồng phiên bản**. API Vault định nghĩa JSON envelope; Spring Vault cung cấp `VaultResponse`, `VaultResponseSupport<T>`, KV abstractions và `Versioned<T>`; ứng dụng chịu trách nhiệm mapper và validation sang DTO nghiệp vụ.

Những nguyên tắc quan trọng nhất là **không tự giải bọc KV v2 thêm lần nữa khi dùng abstraction KV_2**, không ép kiểu `Map` mà không kiểm tra, tách missing/explicit null khỏi HTTP 403 và lỗi transport, giữ version/lease metadata khi nghiệp vụ cần, và kiểm thử hành vi Jackson trên phiên bản thật. Với Transit, PKI và dynamic credentials, phải kiểm tra thêm binary, X.509 và lease lifecycle.

Một đợt nâng cấp đạt chất lượng khi **JSON contract tests**, **Vault integration tests**, các ca null/error và việc theo dõi sau rollout đều chứng minh behavior mong muốn; “build thành công” chưa đủ.

### Tài liệu tham khảo

- [Spring Vault — Vault Secrets Engines (KV v1/v2, Transit, PKI)](https://docs.spring.io/spring-vault/reference/vault/vault-secret-engines.html)
- [Spring Vault — VaultOperations API](https://docs.spring.io/spring-vault/reference/api/java/org/springframework/vault/core/VaultOperations.html)
- [Spring Vault — VaultKeyValueOperations API](https://docs.spring.io/spring-vault/reference/api/java/org/springframework/vault/core/VaultKeyValueOperations.html)
- [Spring Vault — VaultVersionedKeyValueOperations API](https://docs.spring.io/spring-vault/reference/api/java/org/springframework/vault/core/VaultVersionedKeyValueOperations.html)
- [Spring Vault — VaultResponse API](https://docs.spring.io/spring-vault/reference/api/java/org/springframework/vault/support/VaultResponse.html)
- [Spring Vault — VaultResponseSupport API](https://docs.spring.io/spring-vault/reference/api/java/org/springframework/vault/support/VaultResponseSupport.html)
- [Spring Vault — Versioned API](https://docs.spring.io/spring-vault/reference/api/java/org/springframework/vault/support/Versioned.html)
- [HashiCorp Vault — KV v2 HTTP API](https://developer.hashicorp.com/vault/api-docs/secret/kv/kv-v2)
- [HashiCorp Vault — KV v2 secrets engine](https://developer.hashicorp.com/vault/docs/secrets/kv/kv-v2)
