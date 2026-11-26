# Ánh xạ phản hồi riêng của từng engine

Ứng dụng Java dùng **Spring Vault** thường truy cập nhiều HashiCorp Vault secrets engine: KV để đọc cấu hình, Database để nhận tài khoản có thời hạn, Transit để mã hóa, PKI để cấp chứng chỉ và đôi khi là engine/plugin mở rộng như AWS, SSH hoặc một engine tự triển khai. Tất cả cùng đi qua Vault HTTP API, nhưng **dữ liệu bên trong phản hồi không có một schema chung duy nhất**.

Bài thuộc chương **Engine mở rộng** của module `SPRING_VAULT`. Mục tiêu là biết **phải ánh xạ phần nào của phản hồi**, khi nào dùng `VaultTemplate`/`VaultOperations` với `VaultResponse` hoặc `VaultResponseSupport<T>`, khi nào dùng interface chuyên biệt như `VaultVersionedKeyValueOperations`, `VaultTransitOperations` và `VaultPkiOperations`, và cách giữ lại các thuộc tính có ý nghĩa vận hành như version, lease, TTL và thông tin chứng chỉ.

> **Nguyên tắc:** Hãy chọn adapter theo **engine và endpoint cụ thể**. Một trường `data` của KV v2, một trường `data` của Transit và một trường `data` của Database có cấu trúc cũng như vòng đời khác nhau. Đừng gom toàn bộ vào một DTO có `username`, `ciphertext`, `certificate` rồi chấp nhận mọi trường `null`.

## 1. Hai lớp cấu trúc trong một phản hồi Vault

Phần lớn response thành công của Vault HTTP API có một số field bao ngoài (*envelope*) như `request_id`, `lease_id`, `renewable`, `lease_duration`, `data`, `auth`, `warnings` hoặc `wrap_info`. Tuy nhiên, **không phải endpoint nào cũng trả đủ các field**, và một số endpoint trả HTTP 204 hoặc đối tượng dữ liệu khác.

Ví dụ phản hồi dạng tổng quát:

```json
{
  "request_id": "example-request-id",
  "lease_id": "database/creds/readonly/example-lease",
  "renewable": true,
  "lease_duration": 3600,
  "data": {
    "username": "v-example",
    "password": "<redacted>"
  },
  "warnings": null,
  "auth": null
}
```

Đây là **ví dụ minh họa**. Không log giá trị `password` thực khi kiểm tra một response tương tự.

Trong Spring Vault:

| Thành phần | Chứa gì? | API thường dùng |
|---|---|---|
| `VaultResponse` | Envelope và `data` dạng `Map<String, Object>` | `vault.read(path)` hoặc `vault.write(path, body)` |
| `VaultResponseSupport<T>` | Envelope và `data` đã ánh xạ sang `T` | `vault.read(path, T.class)` hoặc `opsForKeyValue(...).get(path, T.class)` |
| `Versioned<T>` | `T` cùng **version/metadata riêng của KV v2** | `opsForVersionedKeyValue(mount).get(path, T.class)` |
| `Ciphertext` / `Plaintext` | Kiểu chuyên dụng cho mã hóa/giải mã Transit | `opsForTransit(mount).encrypt/decrypt(...)` |
| `VaultCertificateResponse` | Envelope và `CertificateBundle` khi PKI cấp chứng chỉ | `opsForPki(mount).issueCertificate(...)` |

`VaultResponseSupport<T>` **chỉ gõ kiểu cho giá trị `data`**. Nó không tự biến một phản hồi PKI thành thông tin database hay đảm bảo mọi trường bên trong `data` đều hợp lệ theo quy tắc nghiệp vụ.

Đồng thời cần phân biệt:

- `data` là payload có thể chứa bí mật; **kiểu và ý nghĩa phụ thuộc engine**.
- `auth` là phần thông tin đăng nhập trong các phản hồi **authentication**, có thể chứa Vault client token; đừng giả định token luôn nằm trong `data.token`.
- `lease_id` và `lease_duration` ở **envelope** mô tả lease của secret khi được engine cấp lease; chúng **không** phải TTL của Vault client token trong `auth`.
- `wrap_info` xuất hiện khi response được response-wrapping, không phải payload gốc để parser domain đọc ngay.

## 2. Nhìn nhanh sự khác biệt giữa các engine

| Engine/endpoint tiêu biểu | Vị trí dữ liệu nghiệp vụ trong JSON | Thông tin bổ sung quan trọng | Hướng ánh xạ Spring Vault |
|---|---|---|---|
| KV v1 `GET /v1/legacy/apps/orders` | `data.endpoint`, `data.timeoutSeconds` | Thường không có version | `VaultKeyValueOperations`, `VaultResponseSupport<AppSettings>` |
| KV v2 `GET /v1/secret/data/apps/orders` | `data.data.endpoint`; metadata ở `data.metadata` | `version`, `deletion_time`, `destroyed` | `VaultVersionedKeyValueOperations` → `Versioned<AppSettings>` |
| Transit `POST /v1/transit/encrypt/customer-pii` | `data.ciphertext` | Tiền tố `vault:vN:...`; key version | `VaultTransitOperations` → `Ciphertext` |
| Transit `POST /v1/transit/decrypt/customer-pii` | `data.plaintext` (Base64) | Quyền decrypt và context nếu có | `VaultTransitOperations` → `Plaintext` |
| PKI `POST /v1/pki/issue/service` | `data.certificate`, `data.private_key`, `data.serial_number` | Chain CA, thời hạn X.509, thông tin khóa | `VaultPkiOperations` → `VaultCertificateResponse`/`CertificateBundle` |
| Database `GET /v1/database/creds/readonly` | `data.username`, `data.password` | `lease_id`, `lease_duration`, `renewable` | `VaultResponseSupport<DatabaseLogin>` + lease |
| AWS hoặc plugin mở rộng | Trường tùy role/engine, ví dụ access key hoặc token | Cơ chế hết hạn/thu hồi phụ thuộc engine | DTO/adapter **riêng cho endpoint**; bắt đầu với typed read hoặc raw response |

Các đường dẫn trên là ví dụ với các mount giả định `legacy/`, `secret/`, `transit/`, `pki/`, `database/`. Mount thực tế là cấu hình trên Vault server; **không hardcode tên mount trong parser nghiệp vụ nếu môi trường triển khai có cấu hình khác nhau**.

## 3. Vì sao một DTO chung dễ làm sai dữ liệu?

Giả sử tự viết một parser:

```java
// ANTI-PATTERN: cố dùng cùng một kiểu cho mọi secrets engine.
record AnyVaultData(
    String username,
    String password,
    String ciphertext,
    String certificate,
    Integer version
) {}
```

Nó không cho biết `version` thuộc KV v2 hay Transit, có chứa `lease_id` hay không, và bỏ qua tính nhạy cảm của `password`/private key. Với KV v2 còn có một lớp `data` lồng bên trong. Kết quả có thể là mapper âm thầm trả toàn bộ field `null` nhưng ứng dụng vẫn tưởng request thành công.

Một cách tổ chức tốt hơn là **tách DTO theo ý nghĩa**:

```text
Spring Vault APIs
    │
    ├── KV adapter ──────────> AppSettings + KvVersion
    ├── Database adapter ────> LeasedDatabaseLogin
    ├── Transit adapter ─────> OpaqueCiphertext
    ├── PKI adapter ─────────> IssuedCertificate
    └── Custom-engine adapter -> CustomEngineResult
                                  │
                                  ▼
                         Business services
```

Mỗi adapter chịu trách nhiệm ba việc: **chọn đúng endpoint**, **đọc đúng cấu trúc** và **kiểm tra các điều kiện bắt buộc**. Service nghiệp vụ nhận kiểu đã được xác nhận thay vì một `Map<String, Object>` chứa mọi dữ liệu chưa biết.

Một cấu trúc package có thể là:

```text
com.example.vault
  kv/KvSettingsAdapter.java
  database/DatabaseCredentialAdapter.java
  transit/TransitCryptoAdapter.java
  pki/CertificateIssueAdapter.java
  custom/CustomEngineAdapter.java
```

Các ví dụ code tiếp theo là những đoạn minh họa **độc lập**, giả định Spring Vault đã có `VaultOperations` bean được xác thực theo workload và các mount/key/role đã được provision.

## 4. KV v1 và KV v2: cùng dữ liệu, khác lớp bao

### 4.1. KV v1 có `data` trực tiếp

Ví dụ engine KV v1 mount tại `legacy/`, key `apps/orders`:

```json
{
  "data": {
    "endpoint": "https://internal.example",
    "timeoutSeconds": 10
  }
}
```

Với KV v1, `VaultKeyValueOperations` giúp lấy phần payload vào POJO Java:

```java
import java.util.Objects;
import org.springframework.vault.core.VaultOperations;
import org.springframework.vault.core.VaultKeyValueOperations;
import org.springframework.vault.core.VaultKeyValueOperationsSupport.KeyValueBackend;
import org.springframework.vault.support.VaultResponseSupport;

// DTO minh họa; tên field trùng với key trong dữ liệu KV.
record AppSettings(String endpoint, int timeoutSeconds) {}

class KvV1SettingsAdapter {
    private final VaultKeyValueOperations kv;

    KvV1SettingsAdapter(VaultOperations vault) {
        kv = vault.opsForKeyValue("legacy", KeyValueBackend.KV_1);
    }

    AppSettings read() {
        VaultResponseSupport<AppSettings> response =
            Objects.requireNonNull(
                kv.get("apps/orders", AppSettings.class),
                "KV v1 key is absent"
            );
        return Objects.requireNonNull(
            response.getData(), "KV v1 payload is absent"
        );
    }
}
```

Ở API này, path `apps/orders` **tương đối** với mount `legacy`. Không truyền `legacy/apps/orders` lần thứ hai vào `get(...)`.

### 4.2. KV v2 có `data.data` và `data.metadata`

KV v2 dùng một JSON khác:

```json
{
  "data": {
    "data": {
      "endpoint": "https://internal.example",
      "timeoutSeconds": 10
    },
    "metadata": {
      "version": 7,
      "created_time": "2026-01-01T00:00:00Z",
      "deletion_time": "",
      "destroyed": false
    }
  }
}
```

Không thể tùy ý đưa JSON này vào DTO dùng cho KV v1 vì `endpoint` đã chuyển xuống `data.data.endpoint`. Spring Vault cung cấp API versioned:

```java
import java.util.Objects;
import org.springframework.vault.core.VaultOperations;
import org.springframework.vault.core.VaultVersionedKeyValueOperations;
import org.springframework.vault.support.Versioned;

record VersionedAppSettings(AppSettings settings, int version) {}

class KvV2SettingsAdapter {
    private final VaultVersionedKeyValueOperations kv;

    KvV2SettingsAdapter(VaultOperations vault) {
        kv = vault.opsForVersionedKeyValue("secret");
    }

    VersionedAppSettings read() {
        Versioned<AppSettings> result = Objects.requireNonNull(
            kv.get("apps/orders", AppSettings.class),
            "KV v2 key or requested version is absent"
        );
        AppSettings settings = Objects.requireNonNull(
            result.getData(),
            "KV v2 version exists but has no readable payload"
        );
        return new VersionedAppSettings(
            settings,
            result.getVersion().getVersion()
        );
    }
}
```

Ở đây `Versioned<AppSettings>` mang dữ liệu đã bỏ lớp bao KV v2 cùng version. `result.getData()` có thể không có dữ liệu nếu version bị soft delete/destroy, vì vậy không bỏ qua kiểm tra `null` hoặc trạng thái version.

**Nếu chủ ý dùng API chung `VaultTemplate.read(...)`**, phải tự xử lý dữ liệu lồng:

```java
import java.util.Map;
import org.springframework.vault.support.VaultResponse;

VaultResponse response = vault.read("secret/data/apps/orders");
if (response == null || response.getData() == null) {
    throw new IllegalStateException("KV v2 secret not available");
}
Object nested = response.getData().get("data");
if (!(nested instanceof Map<?, ?> values)) {
    throw new IllegalStateException("Unexpected KV v2 payload");
}
Object endpoint = values.get("endpoint");  // Cần kiểm tra kiểu.
```

Mẫu raw phù hợp khi đang thăm dò API nhưng có nhiều điểm kiểm tra hơn và dễ nhầm metadata. Khi engine đã có operations chuyên biệt, nên ưu tiên operations đó.

## 5. Transit: dữ liệu đã được đóng gói thành kiểu mật mã

Một phản hồi encrypt của Transit thường có dạng:

```json
{
  "data": {
    "ciphertext": "vault:v3:<ciphertext-minh-hoa>",
    "key_version": 3
  }
}
```

Điểm quan trọng là `ciphertext` chứa **chuỗi opaque** có tiền tố version khóa. `key_version` là thông tin của **khóa Transit**, không phải version của KV. Response decrypt có `data.plaintext` dưới dạng Base64; đó chưa phải chuỗi plaintext UTF-8 để sử dụng trực tiếp.

Với Spring Vault, hãy sử dụng typed API:

```java
import java.nio.charset.StandardCharsets;
import org.springframework.vault.core.VaultOperations;
import org.springframework.vault.core.VaultTransitOperations;
import org.springframework.vault.support.Ciphertext;
import org.springframework.vault.support.Plaintext;

class TransitCryptoAdapter {
    private final VaultTransitOperations transit;

    TransitCryptoAdapter(VaultOperations vault) {
        transit = vault.opsForTransit("transit");
    }

    String encrypt(String secret) {
        Ciphertext encrypted = transit.encrypt(
            "customer-pii",
            Plaintext.of(secret, StandardCharsets.UTF_8)
        );
        // Lưu nguyên chuỗi vault:vN:...; không parse/cắt prefix.
        return encrypted.getCiphertext();
    }

    String decrypt(String storedCiphertext) {
        Plaintext value = transit.decrypt(
            "customer-pii",
            Ciphertext.of(storedCiphertext)
        );
        return value.asString(StandardCharsets.UTF_8);
    }
}
```

Không ghi log đầu vào `secret` hoặc đầu ra `decrypt`. Nếu dữ liệu là nhị phân, dùng `Plaintext.of(byte[])` và nhận bytes thay vì ép về `String`. Nếu dùng derived key/context, context phải được truyền theo API Transit; không bỏ qua khi chuyển từ raw response sang typed operations.

**Phân quyền cũng là một phần của hợp đồng adapter:** workload encrypt-only chỉ có quyền `update` tại `transit/encrypt/customer-pii`; workload được phép giải mã cần `update` tại `transit/decrypt/customer-pii`. Một mapper không được tự suy ra rằng có `ciphertext` là có quyền decrypt.

## 6. Database: dữ liệu credential đi kèm lease

Sau khi operator cấu hình Database secrets engine và role `readonly`, ứng dụng gọi `GET /v1/database/creds/readonly`. Một phản hồi mẫu được **ẩn password**:

```json
{
  "lease_id": "database/creds/readonly/example-lease",
  "lease_duration": 3600,
  "renewable": true,
  "data": {
    "username": "v-readonly-example",
    "password": "<redacted>"
  }
}
```

`username` và `password` nằm trong `data`, còn `lease_id` và TTL lại nằm **ngoài**. Nếu chỉ parse `data` thành `DatabaseLogin` mà bỏ envelope thì ứng dụng mất khả năng theo dõi thời hạn sử dụng credential.

Ví dụ DTO và adapter:

```java
import java.time.Duration;
import java.util.Objects;

import org.springframework.vault.core.VaultOperations;
import org.springframework.vault.support.VaultResponseSupport;

record DatabaseLogin(String username, String password) {
    // record tự sinh toString() có thể làm lộ password trong log.
    @Override
    public String toString() {
        return "DatabaseLogin[REDACTED]";
    }
}

record LeasedDatabaseLogin(
    DatabaseLogin credentials,
    String leaseId,
    Duration ttl,
    boolean renewable
) {
    @Override
    public String toString() {
        return "LeasedDatabaseLogin[REDACTED]";
    }
}

class DatabaseCredentialAdapter {
    private final VaultOperations vault;

    DatabaseCredentialAdapter(VaultOperations vault) {
        this.vault = vault;
    }

    LeasedDatabaseLogin request() {
        VaultResponseSupport<DatabaseLogin> response =
            Objects.requireNonNull(
                vault.read("database/creds/readonly", DatabaseLogin.class),
                "Database credential response is absent"
            );

        DatabaseLogin login = Objects.requireNonNull(
            response.getData(), "Database credential data is absent"
        );
        if (login.username() == null || login.username().isBlank()
                || login.password() == null || login.password().isBlank()) {
            throw new IllegalStateException("Incomplete database credentials");
        }

        String leaseId = response.getLeaseId();
        long seconds = response.getLeaseDuration();
        if (leaseId == null || leaseId.isBlank() || seconds <= 0) {
            throw new IllegalStateException("Missing dynamic credential lease");
        }

        return new LeasedDatabaseLogin(
            login, leaseId, Duration.ofSeconds(seconds), response.isRenewable()
        );
    }
}
```

**Lưu ý phạm vi:** ví dụ trên dành cho role **dynamic database credentials** trả lease. Một role **static credentials** có cơ chế vòng đời và hình dạng metadata khác; không áp quy tắc `lease_id` bắt buộc cho mọi endpoint `database/*`.

Ứng dụng cần có chiến lược quản lý lease, renew/revoke theo quyền token và khả năng kết nối lại của connection pool. **Không mặc định kết nối database tiếp tục dùng được vô hạn chỉ vì credential đã được map thành POJO.** Không đưa DTO credential vào JSON của API, metrics labels, tracing spans hoặc cache không được bảo vệ.

## 7. PKI: CertificateBundle và dữ liệu có vòng đời riêng

PKI trả về một cấu trúc khác: với endpoint `pki/issue/<role>`, dữ liệu có thể gồm `certificate`, `issuing_ca`, `ca_chain`, `serial_number`, `private_key`, `private_key_type` và `expiration`.

Ví dụ dạng rút gọn:

```json
{
  "data": {
    "certificate": "-----BEGIN CERTIFICATE-----...",
    "issuing_ca": "-----BEGIN CERTIFICATE-----...",
    "private_key": "-----BEGIN PRIVATE KEY-----...",
    "private_key_type": "rsa",
    "serial_number": "12:34:56",
    "expiration": 1770000000
  }
}
```

Không thể dùng kiểu `DatabaseLogin` cho phản hồi này. Với Spring Vault có API PKI chuyên biệt, hãy yêu cầu certificate theo role:

```java
import java.util.Objects;

import org.springframework.vault.core.VaultOperations;
import org.springframework.vault.core.VaultPkiOperations;
import org.springframework.vault.support.CertificateBundle;
import org.springframework.vault.support.VaultCertificateRequest;
import org.springframework.vault.support.VaultCertificateResponse;

class PkiCertificateAdapter {
    private final VaultPkiOperations pki;

    PkiCertificateAdapter(VaultOperations vault) {
        pki = vault.opsForPki("pki");
    }

    CertificateBundle issue(String serverDns) {
        // Role server đã được operator tạo, có policy và domain restrictions.
        VaultCertificateRequest request =
            VaultCertificateRequest.create(serverDns);

        VaultCertificateResponse response =
            pki.issueCertificate("server", request);

        CertificateBundle bundle = Objects.requireNonNull(
            response.getData(), "PKI did not issue a certificate bundle"
        );
        if (bundle.getCertificate() == null || bundle.getSerialNumber() == null) {
            throw new IllegalStateException("Incomplete issued certificate");
        }
        return bundle;
    }
}
```

`CertificateBundle` giúp ứng dụng lấy `getCertificate()`, `getIssuingCaCertificate()`, `getSerialNumber()` và `getPrivateKey()` khi API issue thực sự sinh private key. **Private key là bí mật**: không ghi ra log hoặc trả qua endpoint quản trị. Việc lưu vào keystore cần password, phân quyền file và quy trình rotation phù hợp.

Không dùng một giả định TTL chung để xác định hạn chứng chỉ. Với X.509, hãy kiểm tra **`notBefore/notAfter` thực tế của chứng chỉ**, serial number và certificate chain. Nếu luồng dùng `sign` bằng CSR thì private key thường **được tạo và giữ ở phía client**, nên DTO của chứng chỉ đã ký không có lý do bắt buộc chứa private key. Ánh xạ `issue` và `sign` phải theo đúng response của endpoint.

## 8. Với engine không có Spring Vault operations riêng

Spring Vault không thể cung cấp một class cho mọi engine/plugin của Vault. Đối với API **GET** trả `data`, có thể dùng `VaultOperations.read(path, Class<T>)`; đối với endpoint cần body/POST, dùng `vault.write(path, body)` hoặc HTTP client session-aware phù hợp và parser riêng.

Giả sử một **engine minh họa** mount tại `custom/` có endpoint GET `custom/items/order-123` trả:

```json
{
  "data": {
    "item_id": "order-123",
    "state": "READY",
    "expires_at": "2026-12-31T00:00:00Z"
  }
}
```

Đây là **schema giả định để học cách map**, không phải một engine tích hợp mặc định của Vault. Khi làm việc với plugin thật, phải dùng schema đã công bố của plugin và thử nghiệm với phiên bản đó.

Có thể chọn cách map trực tiếp bằng JSON property:

```java
import java.time.Instant;
import java.util.Objects;
import com.fasterxml.jackson.annotation.JsonProperty;

import org.springframework.vault.core.VaultOperations;
import org.springframework.vault.support.VaultResponseSupport;

record CustomItemPayload(
    @JsonProperty("item_id") String itemId,
    String state,
    @JsonProperty("expires_at") Instant expiresAt
) {}

class CustomEngineAdapter {
    private final VaultOperations vault;

    CustomEngineAdapter(VaultOperations vault) {
        this.vault = vault;
    }

    CustomItemPayload read(String trustedItemId) {
        // trustedItemId đã được kiểm tra/giới hạn trước khi nối vào path.
        VaultResponseSupport<CustomItemPayload> response =
            Objects.requireNonNull(
                vault.read("custom/items/" + trustedItemId,
                           CustomItemPayload.class),
                "Custom item not found"
            );
        CustomItemPayload item = Objects.requireNonNull(
            response.getData(), "Custom payload missing"
        );
        if (item.itemId() == null || item.expiresAt() == null) {
            throw new IllegalStateException("Custom payload has missing fields");
        }
        return item;
    }
}
```

Ví dụ dùng Jackson `@JsonProperty` và `Instant`; cấu hình mapper cho Java Time/records phụ thuộc stack Jackson/Spring Vault thực tế. Không mặc định mọi phiên bản thư viện tự hỗ trợ cùng kiểu ngày giờ. Nếu engine trả timestamp dạng Unix seconds hoặc chuỗi không theo ISO-8601, phải chuyển đổi rõ ràng theo schema.

**Khi nào cần Map?** Trong bước đầu tìm hiểu engine hoặc khi payload có một tập field động theo role, có thể đọc `VaultResponse`, kiểm tra `getData()` và chuyển từng field. Ngay khi biết contract ổn định, hãy tạo DTO riêng, xác thực trường bắt buộc và bỏ dữ liệu dư có chủ đích; tránh truyền raw Map xuyên nhiều lớp nghiệp vụ.

### Đặc biệt: response của POST không nhất thiết có `data`

`VaultOperations.write(path, body)` trả `VaultResponse` khi endpoint có response được map; một số thao tác thành công chỉ trả status và **không có body**. Do đó:

```java
// Ví dụ chung cho endpoint POST; không khẳng định engine cụ thể.
VaultResponse response = vault.write("custom/actions/validate", requestBody);

// response có thể null khi Vault không trả body.
// Không được coi null luôn là request thất bại:
// phải hiểu HTTP contract của chính endpoint đó.
```

Không dùng `vault.read(...)` cho endpoint chỉ hỗ trợ POST. Cũng không được coi HTTP `200` là chứng minh payload có đủ field: một API thành công về HTTP vẫn có thể thiếu field nghiệp vụ mà ứng dụng yêu cầu.

## 9. Quy tắc map an toàn: dữ liệu, metadata và lỗi

### 9.1. Phải kiểm tra cấu trúc trước khi sử dụng

Khi đọc một response, adapter nên xử lý theo thứ tự:

1. **Đúng endpoint và mount:** phân biệt `secret/data/...` của KV v2 với `database/creds/...` hay `transit/encrypt/...`.
2. **Đúng phương thức HTTP:** GET, POST, DELETE có hành vi và response khác nhau.
3. **Đúng envelope:** xác định `data`, `auth`, `wrap_info` hoặc response trống theo contract.
4. **Đúng DTO:** trường bắt buộc phải đủ và đúng kiểu, kể cả timestamp/số version/certificate.
5. **Đúng metadata vòng đời:** lease ID, thời hạn, key version, X.509 notAfter hoặc revision của plugin.
6. **Đúng quyền và phạm vi:** workload token, tenant, role, path; không cho client tùy ý chọn Vault mount.

Không chuyển mọi missing field thành chuỗi rỗng hoặc `0`. Ví dụ `lease_duration=0` không nên được hiểu là "còn hạn vô tận". Với một role dynamic đòi lease hợp lệ, đó là một vấn đề của contract cần xử lý.

### 9.2. Phân biệt lỗi truy cập với dữ liệu không tồn tại

| Kết quả | Khả năng cần kiểm tra | Cách xử lý |
|---|---|---|
| Không thấy dữ liệu/`404` | Sai mount/path, version bị xóa, key chưa tồn tại | Đối chiếu path, version, contract; chỉ coi là "không tồn tại" khi có bằng chứng phù hợp |
| `403 permission denied` | Token thiếu capability hoặc policy không khớp endpoint | Không suy diễn key vắng mặt; sửa policy/role và kiểm tra effective policies |
| `400` | Sai payload, sai schema, context Transit thiếu hoặc thông số PKI không hợp lệ | Sửa đầu vào theo API; không retry mù |
| `429`, `5xx` hoặc mất kết nối | Hệ thống quá tải hoặc sự cố Vault/network | Retry hạn chế, backoff và timeouts; không làm lộ payload trong log |
| HTTP thành công nhưng `data=null` | Endpoint không trả body, sai parser hoặc response không hoàn chỉnh | Phân biệt expected-empty với missing-required theo contract endpoint |
| `data` đủ nhưng `lease_id` trống | Secret có thể không được cấp lease hoặc parser dùng sai endpoint | Đối chiếu loại engine; không áp quy tắc lease chung |
| Payload giải mã không đúng format | Key/version/context sai hoặc dữ liệu bị biến đổi | Fail closed, kiểm tra nguồn ciphertext, không dùng plaintext thay thế |

Trên một số phiên bản Spring Vault, những đường đọc có thể trả `null` cho path không tồn tại; phiên bản khác có helper `readRequired(...)` để phát lỗi. Dùng API và hành vi tương ứng với dependency của dự án; đừng gom tất cả exception thành một `RuntimeException` rồi trả toàn bộ nội dung server response ra ngoài.

### 9.3. Giữ bí mật khỏi log và lỗi domain

Một DTO `record DatabaseLogin(String username, String password)` sẽ tự sinh `toString()` chứa password nếu không ghi đè. Cùng rủi ro xảy ra với class dữ liệu PKI có private key và phản hồi Transit decrypt. Vì vậy:

- Không log `VaultResponse` hoặc `getData()` nguyên bản.
- Tránh `@Data`, `record toString()` hoặc các công cụ tự sinh logger cho DTO chứa secret nếu chưa có redaction.
- Chỉ log operation, tên engine/mount đã chuẩn hóa, request correlation ID, latency và error category.
- Không đưa token, password, private key, plaintext, secret dynamic credentials vào exception message, labels của metrics hay trace attributes.
- Dữ liệu đã map có thể cần lưu trong bộ nhớ để hoạt động, nhưng phải có vòng đời/refresh/eviction rõ ràng.

## 10. Kiến trúc gợi ý cho một module Java

```mermaid
flowchart LR
    V["VaultTemplate / VaultOperations"] --> K["KV typed operations"]
    V --> D["Database typed read"]
    V --> T["Transit operations"]
    V --> P["PKI operations"]
    V --> X["Custom engine read/write"]

    K --> K2["AppSettings + Version"]
    D --> D2["Credentials + Lease"]
    T --> T2["Ciphertext / Plaintext"]
    P --> P2["CertificateBundle"]
    X --> X2["Custom DTO"]

    K2 --> S["Business service"]
    D2 --> S
    T2 --> S
    P2 --> S
    X2 --> S
```

Đối với ứng dụng Spring Boot, cấu hình mount, role và key trong properties **không chứa secret**, còn token Vault được cấp qua phương thức xác thực theo workload (Kubernetes/JWT/AppRole hoặc tương đương). Tách quyền:

| Workload | Quyền tối thiểu minh họa | Lý do |
|---|---|---|
| Service cấu hình | `read` trên `secret/data/apps/orders` | Chỉ cần đọc KV v2 |
| Service database | `read` trên `database/creds/readonly` | Yêu cầu tài khoản dynamic |
| Service encrypt | `update` trên `transit/encrypt/customer-pii` | Không tự có quyền decrypt |
| Service dùng chứng chỉ | `update` trên `pki/issue/server` | Chỉ cấp theo role đã được giới hạn |
| Service plugin | Quyền đúng endpoint của plugin và role | Tránh wildcard toàn bộ mount |

Policy của Vault **kiểm soát endpoint**, còn adapter Java kiểm soát cấu trúc dữ liệu. Hai lớp phải thống nhất: nếu dùng đúng DTO mà token có policy rộng hơn dự kiến, rủi ro vẫn tồn tại.

## 11. Thực hành kiểm chứng ánh xạ

Các lệnh dưới đây yêu cầu operator đã cấu hình engine, key và role **trong Vault thử nghiệm**. Dữ liệu ví dụ là giả. Không tạo PKI role hoặc database role production chỉ để chạy bài học.

### Bước 1 — So sánh hình dạng JSON của KV v2 và Database

```bash
# KV v2: đọc trực tiếp endpoint HTTP qua vault CLI.
vault read -format=json secret/data/apps/orders

# Database: role đã tồn tại mới cấp credential.
vault read -format=json database/creds/readonly
```

Khi đọc kết quả, xác định đường dẫn `.data.data` của KV v2, `.data.metadata.version` và `.data.username/password` của Database. Với Database, quan sát riêng các field top-level `.lease_id`, `.lease_duration` và `.renewable`. **Không dán output chứa password thật vào ticket/chat hoặc log**.

### Bước 2 — Xem dữ liệu Transit encrypt

```bash
# "demo" ở UTF-8 được encode Base64 thành ZGVtbw==.
vault write -format=json transit/encrypt/customer-pii plaintext=ZGVtbw==
```

Quan sát `.data.ciphertext` có tiền tố `vault:vN:...`. Không so sánh hai ciphertext theo `equals` để suy ra plaintext giống nhau vì Transit mặc định mã hóa không xác định.

### Bước 3 — Quan sát phản hồi PKI trong môi trường lab

```bash
# Giả sử PKI role tên server cho phép domain lab.example.test.
vault write -format=json pki/issue/server common_name=app.lab.example.test
```

Quan sát tên field `certificate`, `issuing_ca`, `serial_number` và `expiration`, nhưng **không in hoặc lưu response có private_key** vào artifact dùng chung. Khi triển khai thật, dùng API Java của PKI để nhận bundle trong bộ nhớ và cài đặt key/cert đúng nơi cần thiết.

### Bước 4 — Đối chiếu JSON với kiểu Java

Viết một test integration cho mỗi adapter, với credential/token chỉ được phép endpoint tương ứng:

| Adapter | Kiểm tra positive | Kiểm tra negative |
|---|---|---|
| KV v1 | `endpoint` và `timeoutSeconds` map đúng | Key thiếu/sai kiểu dẫn tới xử lý lỗi rõ ràng |
| KV v2 | Version N và settings đúng | Soft delete latest hoặc version không đọc được |
| Database | Username/password hiện diện; lease ID và TTL hợp lệ | Token thiếu policy và response thiếu lease bắt buộc |
| Transit | Encrypt → decrypt trả đúng bytes; ciphertext giữ `vault:vN:` | Token encrypt-only không gọi được decrypt; ciphertext sai bị từ chối |
| PKI | Bundle có certificate/serial, X.509 parse được | Role/domain không được phép; response thiếu trường |
| Custom | `item_id` / `expires_at` map đúng | Payload sai tên field, format timestamp hoặc path bị từ chối |

Nếu có nhiều version của plugin, lưu lại JSON **đã redacted** theo schema ở fixture và chạy contract test cho version đang hỗ trợ. Không snapshot raw secret hoặc private key vào repository.

### Bước 5 — Kiểm tra vòng đời và logging

Test thêm token hết hạn, kết nối Vault gián đoạn, response wrapping và cấp quyền sai engine. Xác minh log chỉ giữ mã lỗi/request ID, không giữ `data`, `auth.client_token` hay `private_key`. Đối với credential động, kiểm tra renew/rotate hoặc reconnect khi lease hết; với PKI, kiểm tra hạn chứng chỉ bằng `notAfter`.

## 12. Câu hỏi tự kiểm tra

1. Vì sao `VaultResponseSupport<AppSettings>` đọc từ KV v1 và `Versioned<AppSettings>` đọc từ KV v2 không phải cùng một wrapper?
2. Với KV v2 raw response, giá trị `endpoint` nằm ở `data.endpoint` hay `data.data.endpoint`?
3. Tại sao Database adapter phải giữ `lease_id` và `lease_duration` ngoài `username/password`?
4. Giá trị `vault:v3:...` của Transit chứa version thuộc hệ thống nào? Có phải version của KV v2 không?
5. Khi cấp chứng chỉ bằng PKI, vì sao `private_key` không nên được log và thời hạn chứng chỉ cần đọc từ X.509?
6. Khi custom plugin trả HTTP 204 và không có `data`, có thể kết luận request thất bại chỉ vì `VaultResponse` rỗng không?
7. Mapper trả DTO hợp lệ nhưng token workload có policy `secret/*` quá rộng: mô hình đã an toàn chưa?
8. Một field timestamp của plugin chuyển từ chuỗi ISO-8601 sang epoch seconds; bạn sẽ phát hiện thay đổi này bằng cách nào?

**Ghi nhớ:** Phản hồi Vault gồm **lớp bao chung** và **payload riêng theo engine**. KV v2 cần xử lý version và lớp `data` lồng, Database cần giữ lease, Transit cần dùng kiểu mật mã, PKI cần quản lý chứng chỉ/khóa riêng, còn engine mở rộng cần parser dựa trên contract của chính endpoint. Dùng API chuyên biệt khi có sẵn, và luôn kiểm tra dữ liệu trước khi đưa vào nghiệp vụ Java.

## Tài liệu chính thức

- [Spring Vault — Secrets engines và các operations chuyên biệt](https://docs.spring.io/spring-vault/reference/vault/vault-secret-engines.html)
- [Spring Vault — `VaultOperations` Javadoc](https://docs.spring.io/spring-vault/reference/api/java/org/springframework/vault/core/VaultOperations.html)
- [Spring Vault — `VaultResponseSupport<T>` Javadoc](https://docs.spring.io/spring-vault/reference/api/java/org/springframework/vault/support/VaultResponseSupport.html)
- [Spring Vault — `VaultVersionedKeyValueOperations` Javadoc](https://docs.spring.io/spring-vault/reference/api/java/org/springframework/vault/core/VaultVersionedKeyValueOperations.html)
- [Spring Vault — `VaultTransitOperations` Javadoc](https://docs.spring.io/spring-vault/reference/api/java/org/springframework/vault/core/VaultTransitOperations.html)
- [Spring Vault — `VaultPkiOperations` Javadoc](https://docs.spring.io/spring-vault/reference/api/java/org/springframework/vault/core/VaultPkiOperations.html)
- [HashiCorp Vault — KV v2 API](https://developer.hashicorp.com/vault/api-docs/secret/kv/kv-v2)
- [HashiCorp Vault — Transit API](https://developer.hashicorp.com/vault/api-docs/secret/transit)
- [HashiCorp Vault — Database secrets engine API](https://developer.hashicorp.com/vault/api-docs/secret/databases)
- [HashiCorp Vault — PKI API](https://developer.hashicorp.com/vault/api-docs/secret/pki)
