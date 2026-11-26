# CAS không khớp và xử lý cập nhật cạnh tranh

## 1. Bối cảnh và mục tiêu

Trong một ứng dụng Java sử dụng **Spring Vault**, nhiều instance, pipeline triển khai hoặc công cụ quản trị có thể cùng đọc và cập nhật một secret trong **HashiCorp Vault KV version 2**. Ví dụ hai worker cùng đọc cấu hình của dịch vụ Orders: A muốn tăng thời gian chờ kết nối, B muốn bật một tính năng mới. Nếu cả hai cùng ghi bản dữ liệu cũ đã chỉnh sửa, lần ghi sau có thể ghi đè thay đổi của lần ghi trước. Hiện tượng này gọi là **lost update**.

**CAS (Compare-and-Set)** trong KV v2 là cơ chế kiểm soát cập nhật cạnh tranh theo phiên bản. Writer chỉ được ghi khi phiên bản hiện tại của secret vẫn đúng với phiên bản writer đã đọc. Nếu phiên bản thay đổi, Vault từ chối write và ứng dụng phải đọc lại, đánh giá xung đột rồi quyết định xử lý.

Bài học thuộc chương **Lỗi và khả năng phục hồi** của module **SPRING_VAULT**. Phạm vi là KV v2, tích hợp từ `VaultTemplate` hoặc `VaultOperations`, authentication theo workload, Vault policy và xử lý lỗi/retry. Token, lease của dynamic secrets, Transit key version và PKI certificate có vòng đời khác với KV secret version; không áp dụng quy tắc CAS KV v2 một cách máy móc cho các engine đó.

Sau bài học, bạn có thể giải thích CAS 0 và CAS theo version, đọc đúng metadata, viết request CAS qua CLI/API/Java, phân loại lỗi conflict, triển khai retry có giới hạn và kiểm thử cập nhật cạnh tranh thực tế.

## 2. Lost update khi không dùng CAS

Giả sử secret `secret/orders/runtime` đang ở version 7:

~~~json
{
  "apiTimeoutMs": 1500,
  "featureEnabled": false
}
~~~

Hai worker chạy đồng thời:

| Thời điểm | Worker A | Worker B | Version mới nhất |
| --- | --- | --- | --- |
| T0 | Đọc version 7 | Đọc version 7 | 7 |
| T1 | Sửa timeout thành 3000 | Sửa featureEnabled thành true | 7 |
| T2 | Ghi cả document, không CAS | Chưa ghi | 8 |
| T3 | Hoàn tất | Ghi document cũ đã sửa, không CAS | 9 |

Dữ liệu ở version 9 có thể là `apiTimeoutMs=1500` và `featureEnabled=true`. B đã vô tình khôi phục timeout cũ, làm mất cập nhật của A. KV v2 vẫn giữ lịch sử phiên bản theo cấu hình retention, nhưng lịch sử **không tự ngăn bản hiện tại bị ghi đè**.

Với CAS, cả hai cùng đọc version 7. A ghi với CAS 7 thành công và tạo version 8; B ghi với CAS 7 thất bại vì current version đã là 8. B phải đọc lại rồi tính lại document mới trên version 8.

~~~mermaid
sequenceDiagram
    autonumber
    participant A as Worker A
    participant B as Worker B
    participant V as Vault KV v2
    A->>V: Read orders/runtime
    V-->>A: version=7, data=old
    B->>V: Read orders/runtime
    V-->>B: version=7, data=old
    A->>V: Write options.cas=7 + document A
    V-->>A: Success; new version=8
    B->>V: Write options.cas=7 + document B
    V-->>B: CAS mismatch; write rejected
    B->>V: Read latest
    V-->>B: version=8, document A
    B->>B: Áp dụng thay đổi lên dữ liệu mới
    B->>V: Write options.cas=8 + merged document
    V-->>B: Success; version=9
~~~

CAS là **optimistic concurrency control** trên từng secret path. Vault kiểm tra điều kiện version khi ghi; ứng dụng vẫn phải quyết định **merge như thế nào**. CAS không tự động hợp nhất hai document và không tạo giao dịch trên nhiều secret path.

## 3. Version và tham số CAS trong KV v2

### 3.1. Đường dẫn KV v2

Ví dụ mount KV v2 là `secret`, đường dẫn nghiệp vụ là `orders/runtime`:

| Công việc | Vault HTTP API |
| --- | --- |
| Đọc dữ liệu và version mới nhất | `GET /v1/secret/data/orders/runtime` |
| Tạo/cập nhật secret có CAS | `POST /v1/secret/data/orders/runtime` |
| Xem metadata của key | `GET /v1/secret/metadata/orders/runtime` |
| Sửa metadata/cấu hình key | `POST /v1/secret/metadata/orders/runtime` |

Không nhầm endpoint KV v2 `/data/` với cách truy cập KV v1. Khi dùng `VaultOperations.read()` hoặc `write()`, truyền đường dẫn logic `secret/data/orders/runtime`, không thêm prefix `/v1/`.

Một response đọc KV v2 thường có cấu trúc:

~~~json
{
  "data": {
    "data": {
      "apiTimeoutMs": 1500,
      "featureEnabled": false
    },
    "metadata": {
      "version": 7,
      "created_time": "2026-11-25T10:00:00Z",
      "deletion_time": "",
      "destroyed": false
    }
  }
}
~~~

**Chú ý hai lớp `data`**: `response.data.data` là nội dung secret, `response.data.metadata.version` là phiên bản dùng cho CAS. Metadata của một path khác, hoặc lease ID/TTL của secret động, không dùng làm điều kiện CAS.

### 3.2. CAS bằng 0 và CAS dương

| Tham số | Ý nghĩa | Tình huống |
| --- | --- | --- |
| `cas=0` | Chỉ tạo khi key chưa có phiên bản đã tồn tại | Khởi tạo cấu hình một lần, ngăn hai producer tạo trùng |
| `cas=n` với n lớn hơn 0 | Chỉ ghi nếu **current version = n** | Cập nhật dữ liệu từ snapshot version n |
| Không gửi CAS, `cas_required=false` | Có thể ghi không so sánh version | Nguy cơ lost update khi có nhiều writer |
| Không gửi CAS, `cas_required=true` | Write bị từ chối vì thiếu CAS | Buộc các writer dùng concurrency control |

**Soft delete không đưa version về zero.** Nếu một secret đã từng có version và bị soft delete, metadata còn ghi current version. CAS 0 không phải cách tạo lại secret đã bị soft delete. Với workflow khôi phục hoặc ghi mới sau xóa, phải kiểm tra current version và chính sách nghiệp vụ.

Một lần write thành công tạo version mới ngay cả khi nội dung mới bằng nội dung cũ. CAS so sánh **version của toàn bộ path**, không so từng field JSON. Vì thế hai writer sửa hai field khác nhau vẫn có thể conflict.

### 3.3. Bắt buộc CAS tại mount hoặc key

Quản trị viên có thể bật CAS bắt buộc trong môi trường test:

~~~bash
# Áp dụng cho mount KV v2; ảnh hưởng các writer trong mount.
vault write secret/config cas_required=true

# Hoặc yêu cầu CAS cho một path cụ thể.
vault kv metadata put -mount=secret \
  -cas-required orders/runtime
~~~

Không chạy thay đổi mount-wide trên production nếu chưa kiểm kê các writer cũ: script CI, ứng dụng Spring, thao tác CLI thủ công và công cụ admin đều phải gửi CAS khi cấu hình yêu cầu. Lệnh thay metadata cũng cần được kiểm tra các tùy chọn retention/config hiện có trước khi áp dụng.

## 4. Thực hành CAS bằng Vault CLI

### 4.1. Tạo mới với CAS 0

~~~bash
vault kv put -mount=secret -cas=0 orders/runtime \
  apiTimeoutMs=1500 featureEnabled=false
~~~

Nếu hai tiến trình cùng thực hiện, chỉ một tiến trình có thể tạo path khi chưa tồn tại. Tiến trình thứ hai sẽ nhận lỗi CAS. Không đưa password, API key hoặc token thật vào ví dụ command line vì command history và công cụ quan sát process có thể làm lộ giá trị.

### 4.2. Đọc rồi cập nhật đúng version

~~~bash
# Đọc dữ liệu kèm metadata version.
vault kv get -mount=secret orders/runtime

# Chỉ khi đã xác minh current version của path này là 7:
vault kv put -mount=secret -cas=7 orders/runtime \
  apiTimeoutMs=3000 featureEnabled=false
~~~

**Đừng chỉ truyền field cần sửa nếu đang dùng put/POST**: request put ghi **toàn bộ document data mới**, không phải patch tự động. Nếu muốn giữ `featureEnabled` và các field khác, phải xây dựng document từ dữ liệu mới nhất hoặc dùng endpoint PATCH theo đúng contract/policy của PATCH.

Nếu CAS 7 không khớp, đừng sửa lệnh thành CAS 8 mà vẫn gửi document được tính từ version 7: điều đó lại tạo mất cập nhật ở tầng nghiệp vụ.

## 5. HTTP API và phân loại CAS mismatch

Một request ghi có điều kiện:

~~~http
POST /v1/secret/data/orders/runtime
X-Vault-Token: <WORKLOAD_TOKEN>
Content-Type: application/json

{
  "options": {
    "cas": 7
  },
  "data": {
    "apiTimeoutMs": 3000,
    "featureEnabled": false
  }
}
~~~

Nếu current version đúng bằng 7, Vault chấp nhận và phản hồi metadata có version mới, chẳng hạn 8. Nếu version đã khác, Vault từ chối và có thể trả HTTP 400 với thông điệp về **check-and-set parameter did not match current version**. Không có write mới được chấp nhận cho request CAS mismatch đó.

Không được xem **mọi HTTP 400 đều là CAS mismatch**:

| Tín hiệu | Nguyên nhân có thể | Hành động |
| --- | --- | --- |
| 400 có bằng chứng CAS mismatch | Version stale | Đọc lại snapshot, merge hoặc trả conflict |
| 400 do thiếu CAS | Mount/key yêu cầu CAS | Sửa client, không retry vô hạn |
| 400 do payload sai | `options`/`data` sai schema | Sửa request |
| 403 | Token hết hạn, policy chưa cấp quyền hoặc auth lỗi | Kiểm tra workload identity, session/policy |
| 404 hoặc đọc thiếu dữ liệu | Sai path, chưa tồn tại hoặc version bị xóa | Kiểm tra metadata và trạng thái path |
| 429/5xx | Quá tải, Vault/đường truyền sự cố | Retry lỗi tạm thời có giới hạn |
| Timeout POST | Không xác định Vault đã ghi hay chưa | Đối soát trước khi gửi lại |

Các exception cụ thể phụ thuộc Spring Vault client/HTTP adapter và phiên bản. Không viết một luật cố định “exception là 400 thì retry CAS”; phải phân biệt đúng nguyên nhân từ response và các tín hiệu đáng tin.

### 5.1. POST khác PATCH

KV v2 hỗ trợ **JSON Merge Patch** ở endpoint `PATCH /v1/secret/data/orders/runtime` khi key phù hợp và token có quyền `patch`. PATCH thay đổi một phần document, sử dụng Content-Type `application/merge-patch+json`; nó cũng có tùy chọn CAS khi cần kiểm soát version. PATCH yêu cầu path đã có secret và current version lớn hơn 0.

Bài này dùng **POST với toàn bộ document** để minh họa lost update và CAS. `VaultOperations.write()` là đường gọi POST; không nhầm nó với PATCH, vì tham số và policy khác nhau.

## 6. Spring Vault: đọc và ghi kèm phiên bản

Spring Vault có `VaultVersionedKeyValueOperations` dành riêng cho KV v2, hỗ trợ dùng đối tượng `Versioned` khi ghi có CAS. Interface `VaultKeyValueOperations` thông thường không đáp ứng đủ thao tác CAS của KV v2. Để hiểu rõ cấu trúc HTTP, ví dụ dưới đây dùng `VaultOperations` (do `VaultTemplate` hiện thực), với đường dẫn đúng.

### 6.1. Adapter Java 17+ cho một secret path

~~~java
package com.example.orders.vault;

import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Objects;

import org.springframework.stereotype.Service;
import org.springframework.vault.core.VaultOperations;
import org.springframework.vault.support.VaultResponse;

@Service
public final class VersionedConfigStore {
    private static final String PATH = "secret/data/orders/runtime";
    private final VaultOperations vault;

    public VersionedConfigStore(VaultOperations vault) {
        this.vault = vault;
    }

    public Snapshot readLatest() {
        VaultResponse response = vault.read(PATH);
        Map<String, Object> outer = requireData(response);

        Map<String, Object> values =
                requireMap(outer.get("data"), "data");
        Map<String, Object> metadata =
                requireMap(outer.get("metadata"), "metadata");

        Object rawVersion = metadata.get("version");
        if (!(rawVersion instanceof Number number)
                || number.intValue() <= 0) {
            throw new IllegalStateException("Invalid KV v2 version");
        }

        // Shallow copy: nested maps/objects vẫn cần được kiểm soát.
        Map<String, Object> copy =
                Collections.unmodifiableMap(
                        new LinkedHashMap<>(values));

        return new Snapshot(copy, number.intValue());
    }

    /**
     * Ghi toàn bộ data map chỉ khi version chưa thay đổi.
     * CAS được kiểm tra ở Vault, không tự so sánh trên JVM.
     */
    public int replaceAtVersion(
            int expectedVersion,
            Map<String, Object> completeData) {

        if (expectedVersion <= 0) {
            throw new IllegalArgumentException("Expected version > 0");
        }
        Objects.requireNonNull(completeData, "completeData");

        Map<String, Object> payload = Map.of(
                "options", Map.of("cas", expectedVersion),
                "data", new LinkedHashMap<>(completeData));

        VaultResponse response = vault.write(PATH, payload);
        Map<String, Object> result = requireData(response);

        Object rawVersion = result.get("version");
        if (!(rawVersion instanceof Number number)
                || number.intValue() <= 0) {
            throw new IllegalStateException("Missing write version");
        }

        return number.intValue();
    }

    private static Map<String, Object> requireData(
            VaultResponse response) {
        if (response == null || response.getData() == null) {
            throw new IllegalStateException("Missing Vault data");
        }
        return response.getData();
    }

    private static Map<String, Object> requireMap(
            Object raw, String field) {
        if (!(raw instanceof Map<?, ?> value)) {
            throw new IllegalStateException("Missing " + field);
        }
        Map<String, Object> result = new LinkedHashMap<>();
        for (Map.Entry<?, ?> entry : value.entrySet()) {
            if (!(entry.getKey() instanceof String key)) {
                throw new IllegalStateException("Invalid map key");
            }
            result.put(key, entry.getValue());
        }
        return result;
    }

    public record Snapshot(
            Map<String, Object> data, int version) {}
}
~~~

Những điểm quan trọng:

- `readLatest()` đọc **data và version trong cùng response**, tránh ghép dữ liệu ở version này với metadata version khác.
- `replaceAtVersion()` gửi `options.cas` tới Vault. Chính Vault mới quyết định write có hợp lệ.
- Dữ liệu thay thế là **toàn bộ map**; reader phải xử lý cả field không muốn sửa.
- Copy map chỉ là shallow copy; nested map/list cần được bảo vệ riêng khi có khả năng thay đổi trong JVM.
- `PATH` cố định theo workload policy; không nhận tên secret path từ HTTP client tùy ý.
- Không in `VaultResponse.getData()` ra log vì có thể chứa secret.

Mẫu này minh họa read/write và kiểm tra response; nó không tự bắt CAS mismatch, 403 hay timeout. Tầng điều phối phải xử lý exception theo loại lỗi. Tùy Spring Vault version, bạn cũng có thể dùng `VaultVersionedKeyValueOperations` với `Versioned`; khi triển khai hãy đối chiếu API chính xác của dependency đang khóa.

### 6.2. Một thao tác cập nhật

~~~java
VersionedConfigStore.Snapshot current = configStore.readLatest();

Map<String, Object> updated =
        new LinkedHashMap<>(current.data());

updated.put("apiTimeoutMs", 3000);

int newVersion = configStore.replaceAtVersion(
        current.version(), updated);

// Chỉ coi thao tác thành công khi nhận kết quả write hợp lệ.
~~~

Với hai JVM đọc cùng version, một write có thể thành công và write còn lại nhận mismatch. Một biến `synchronized` trong JVM không bảo vệ các Pod khác; CAS của Vault mới chặn việc ghi stale version tại server.

## 7. Xử lý CAS mismatch đúng cách

### 7.1. Đọc lại, tính lại rồi ghi có điều kiện

Nếu worker B nhận CAS mismatch:

1. Xác nhận đây thực sự là **version mismatch**, không phải lỗi mạng hoặc token.
2. Đọc lại data và current version của **cùng key**.
3. Xác định **ý định thay đổi**: sửa trường nào, giá trị kỳ vọng nào, có còn hợp lệ trên dữ liệu mới không?
4. Tính lại toàn bộ document từ snapshot mới, giữ thay đổi hợp lệ của writer khác.
5. Ghi CAS bằng version mới; giới hạn số lần thử và dùng backoff/jitter khi xảy ra tranh chấp.
6. Nếu không thể merge hợp lệ, trả conflict nghiệp vụ hoặc chuyển phê duyệt thủ công.

Ví dụ:

~~~text
v7 = { timeout: 1500, enabled: false }

A muốn timeout=3000.
B muốn enabled=true.

A ghi CAS(7): v8 = { timeout: 3000, enabled: false }.
B ghi CAS(7) -> mismatch.
B đọc v8 rồi chỉ sửa enabled.
B ghi CAS(8): v9 = { timeout: 3000, enabled: true }.
~~~

Không tăng CAS lên 8 rồi gửi nguyên document B được tính từ v7, vì điều đó tái tạo lost update dưới hình thức write có CAS.

### 7.2. Không được tự merge mọi thay đổi

Nếu A và B cùng sửa `paymentProvider` theo hai quyết định khác nhau, hoặc một worker tắt một feature do sự cố còn worker khác bật nó dựa trên snapshot cũ, chọn giá trị nào thắng là **quyết định nghiệp vụ**. CAS không quyết định thay người vận hành.

Nếu không thể hợp nhất có căn cứ, ứng dụng có thể ánh xạ sang HTTP 409 Conflict ở API của mình, kèm thông báo yêu cầu tải trạng thái mới. HTTP 409 là **quyết định của tầng Java**, không phải mã mà Vault chắc chắn trả cho lỗi CAS.

### 7.3. Retry có giới hạn

~~~java
// Pseudocode: helper phân loại exception và backoff
// do ứng dụng tự xây dựng, không phải API có sẵn của Spring Vault.
for (int attempt = 0; attempt < MAX_ATTEMPTS; attempt++) {
    var snapshot = configStore.readLatest();
    var newDocument = applyBusinessChange(snapshot.data());

    try {
        configStore.replaceAtVersion(
                snapshot.version(), newDocument);
        return;
    } catch (RuntimeException error) {
        if (!isVerifiedCasMismatch(error)) {
            throw error; // 403, timeout, lỗi cấu hình ... xử lý riêng
        }

        if (attempt == MAX_ATTEMPTS - 1) {
            throw new ConcurrentUpdateException(
                    "Cannot update after repeated conflicts");
        }
        boundedBackoffWithJitter(attempt);
    }
}
~~~

Đây là pseudocode có helper chưa triển khai, chỉ để biểu diễn **quy tắc retry**. Không triển khai `isVerifiedCasMismatch` đơn giản bằng cách coi mọi `VaultException` hay HTTP 400 là conflict. Nếu exception không có bằng chứng đủ rõ, xử lý ở nhánh lỗi chưa xác định.

**Hàm `applyBusinessChange` nên thuần dữ liệu:** không tạo credential, gửi email, cập nhật DB hay phát hành token bên trong hàm sẽ chạy lại nhiều lần. Nếu nghiệp vụ có side effect, cần idempotency key và ranh giới transaction riêng.

## 8. CAS khi tạo mới, soft delete và metadata

### 8.1. Create-only an toàn với CAS 0

~~~json
{
  "options": { "cas": 0 },
  "data": {
    "apiTimeoutMs": 1500,
    "featureEnabled": false
  }
}
~~~

Nếu key chưa tồn tại, Vault có thể tạo version 1. Nếu một writer khác đã tạo version, CAS 0 thất bại thay vì ghi đè.

### 8.2. Soft delete khác xóa toàn bộ lịch sử

KV v2 cho phép soft delete, undelete và destroy các version theo semantics khác nhau. Nếu latest version đã soft delete, `GET data` có thể không trả nội dung, nhưng metadata vẫn có current version. Vì vậy:

- Không kết luận key chưa từng tồn tại chỉ vì read data thất bại.
- Không dùng CAS 0 để phục hồi secret có lịch sử version.
- Nếu phục hồi/ghi tiếp được phép, kiểm tra metadata và current version thật rồi làm theo chính sách.
- Việc xóa/khôi phục key cần quyền riêng và audit, không phải nhánh retry tự động cho mismatch.

### 8.3. CAS không tạo transaction liên path

Một CAS bảo vệ **một secret path, một lần ghi**. Nếu cần cập nhật `secret/orders/runtime` và `secret/payments/runtime` cùng lúc, CAS của một path không bảo đảm cả hai thành công nguyên tử. Cũng vậy, CAS không biến thao tác Vault và transaction JDBC thành một transaction chung.

## 9. Workload authentication và policy ít quyền

Writer đọc và cập nhật một path hiện có có thể dùng Vault policy:

~~~hcl
path "secret/data/orders/runtime" {
  capabilities = ["read", "update"]
}
~~~

Nếu service phải tạo path mới, có thể cần thêm quyền `create`:

~~~hcl
path "secret/data/orders/runtime" {
  capabilities = ["create", "read", "update"]
}
~~~

Nếu service cần đọc metadata của path bị xóa mềm, cấp riêng:

~~~hcl
path "secret/metadata/orders/runtime" {
  capabilities = ["read"]
}
~~~

Không cấp wildcard `secret/*`, quyền sửa cấu hình engine hay Vault root token chỉ để ứng dụng chỉnh một secret. Bật `cas_required` là thao tác quản trị có kiểm soát. Dùng `ClientAuthentication` theo danh tính workload như Kubernetes ServiceAccount, AppRole hay JWT tùy hạ tầng; quản lý TTL và đăng nhập lại của Vault token độc lập với KV version.

Ngoài ACL ở Vault, API Java vẫn phải xác định người dùng cuối được phép cập nhật field nào. Không cho caller tự ghép path hoặc gửi toàn bộ map chưa kiểm tra dưới quyền writer có thể sửa secret.

## 10. Timeout và trạng thái không chắc chắn

**CAS mismatch xác nhận** nghĩa là request ghi đó bị Vault từ chối vì version khác. **Timeout** sau khi gửi POST thì không biết Vault đã chấp nhận, từ chối hay chưa nhận request.

Ba tình huống có thể xảy ra:

1. Vault chưa nhận request; không có write.
2. Vault nhận request nhưng CAS đã sai; không có write.
3. Vault đã chấp nhận CAS, ghi version mới, nhưng response không tới Java.

Sau timeout, gửi lại cùng CAS có thể bị từ chối. Nhưng CAS mismatch ở lần thử thứ hai **không chứng minh lần đầu của chính mình đã ghi thành công**; writer khác cũng có thể tạo version mới.

Quy trình đối soát:

- Ghi request ID, secret identifier được phép, expectedVersion và ý định cập nhật trong audit nghiệp vụ **không chứa plaintext**.
- Đọc latest data/version và kiểm tra thay đổi kỳ vọng có hiện diện không.
- Đối chiếu log/audit của hệ thống và Vault nếu được phép.
- Nếu bằng chứng không đủ, giữ trạng thái `UNKNOWN`; không tuyên bố thành công chỉ từ việc version tăng.
- Chỉ retry khi đã xác nhận điều kiện nghiệp vụ và tác dụng phụ; giữ CAS tường minh và số lần retry hữu hạn.

Trong môi trường nhiều replica, sử dụng CAS tại Vault thay vì chỉ dùng `synchronized` trên từng JVM.

## 11. Giám sát và vận hành

Một hệ thống ổn định nên phân biệt **contention** với lỗi policy và hạ tầng.

| Chỉ số gợi ý | Mục đích |
| --- | --- |
| `vault_kv_cas_conflicts_total` | Số lần mismatch đã xác nhận |
| `vault_kv_cas_retry_total` | Số lần thử lại sau khi đọc mới |
| `vault_kv_cas_retry_exhausted_total` | Số update không thể hoàn thành vì tranh chấp |
| `vault_kv_write_timeout_total` | Yêu cầu write không rõ đã thành công hay chưa |
| `vault_kv_auth_errors_total` | Lỗi token/policy, tách khỏi mismatch |
| `vault_kv_write_latency_seconds` | Độ trễ p50/p95/p99 |
| `vault_kv_unknown_reconciliations_total` | Các lần đối soát sau timeout |

Đây là metric **đề xuất ở phía ứng dụng**, không phải tên metric Vault mặc định. Tránh đưa plaintext, token, data map, response secret hoặc đường dẫn nhiều giá trị vào metrics label/log.

Khi CAS conflict tăng mạnh, có thể nhiều writer đang tranh cùng một key: cân nhắc tách key nhỏ hơn, giảm số writer trực tiếp hoặc đưa cập nhật qua một service điều phối. Khi 403 tăng, kiểm tra token TTL, auth role và policy. Khi timeout tăng, kiểm tra Vault HA, mạng và retry, không tắt CAS để “giảm lỗi”.

Audit Vault có thể giúp đối chiếu các request đã gửi, nhưng phải kiểm soát quyền xem audit log, retention và nội dung nhạy cảm.

## 12. Kiểm thử tích hợp với Vault thật

Dùng Vault test cô lập có KV v2 mount và test policy riêng; không ghi thử vào secret production. Unit test có thể kiểm tra merge, nhưng integration test mới xác nhận semantics version/CAS của Vault.

Các tình huống nên kiểm thử:

1. **Create-only:** CAS 0 tạo một path mới; CAS 0 lần nữa bị từ chối.
2. **Cập nhật đúng version:** đọc n, ghi CAS n, nhận version n+1.
3. **Cập nhật stale:** A/B đọc cùng n, A ghi thành công, B dùng n bị từ chối và không ghi đè A.
4. **Merge độc lập:** B đọc lại và chỉ sửa field mục tiêu, giữ thay đổi của A.
5. **Conflict nghiệp vụ:** hai writer sửa cùng field theo quyết định mâu thuẫn, ứng dụng trả conflict thay vì merge mù.
6. **CAS bắt buộc:** bật `cas_required` tại key test, write thiếu CAS bị từ chối.
7. **Soft delete:** không tái tạo key đã có lịch sử bằng CAS 0.
8. **Sai quyền:** token chỉ read không ghi được; phân loại lỗi khác CAS mismatch.
9. **Timeout sau write:** giả lập mất response, giữ trạng thái UNKNOWN và đối soát.
10. **Concurrency:** barrier buộc hai worker đọc cùng version trước khi write, tránh test race ngẫu nhiên khó tái hiện.

Ví dụ test JUnit 5 + AssertJ, với fixture đã tạo secret test và bean `configStore`:

~~~java
@Test
void staleCasMustNotOverwriteNewerVersion() {
    var a = configStore.readLatest();
    var b = configStore.readLatest();

    var byA = new LinkedHashMap<>(a.data());
    byA.put("apiTimeoutMs", 3000);
    int writtenVersion =
            configStore.replaceAtVersion(a.version(), byA);

    var staleByB = new LinkedHashMap<>(b.data());
    staleByB.put("featureEnabled", true);

    assertThatThrownBy(() ->
            configStore.replaceAtVersion(b.version(), staleByB))
            .isInstanceOf(RuntimeException.class);

    var latest = configStore.readLatest();
    assertThat(latest.version()).isEqualTo(writtenVersion);
    assertThat(latest.data().get("apiTimeoutMs")).isEqualTo(3000);
}
~~~

Đây là phác thảo test. Trong test thật, nên kiểm tra **đúng lỗi CAS**, không chỉ `RuntimeException` chung, đồng thời xác minh dữ liệu sau retry giữ cả hai thay đổi. Dùng countdown barrier hoặc orchestration có kiểm soát để buộc hai writer đọc cùng snapshot, thay vì kỳ vọng scheduler ngẫu nhiên tạo race.

## 13. Bài thực hành: cấu hình Orders có hai writer

**Tình huống:** một công cụ rollout muốn tăng timeout; công cụ feature flag muốn bật chức năng mới. Cả hai cùng quản lý `secret/orders/runtime`.

1. Bật KV v2 trên mount test và tạo secret bằng CAS 0.
2. Đọc version và bật `cas_required` cho key test bằng quyền quản trị.
3. Cấp hai workload identities chỉ có quyền đọc/cập nhật data path tương ứng.
4. Cho A và B cùng đọc version n; A ghi CAS n, B thử CAS n và xác nhận mismatch.
5. B đọc lại n+1, tính lại document chỉ thay feature flag rồi ghi CAS n+1.
6. Xác minh latest version có cả timeout mới lẫn feature flag.
7. Thử hai writer cùng đổi một field quan trọng và xử lý conflict nghiệp vụ.
8. Giả lập 403, timeout, soft delete; bảo đảm mỗi tình huống có hành động phù hợp.
9. Đo số conflict/retry, không ghi giá trị secret trong log.

**Câu hỏi tự kiểm tra:**

1. KV v2 có version history rồi, vì sao vẫn xảy ra lost update?
2. CAS 0 có ý nghĩa gì và tại sao không dùng để hồi sinh soft-deleted secret?
3. CAS n đang so sánh version của field hay của toàn path?
4. Vì sao retry nguyên document cũ với CAS mới vẫn sai?
5. Khi nào có thể merge tự động, và khi nào phải yêu cầu người dùng giải quyết conflict?
6. Tại sao 403 hoặc timeout không được xem là CAS mismatch?
7. Lần retry sau timeout bị mismatch có chứng minh write ban đầu thành công không?
8. Vì sao cần integration test với hai writer cùng đọc một version?

## 14. Kết luận

**CAS trong Vault KV v2** là cơ chế bảo vệ secret trước cập nhật cạnh tranh: `options.cas=0` chỉ tạo mới khi chưa có version, còn CAS dương chỉ ghi khi current version khớp với snapshot. Khi mismatch, Java phải **đọc lại, tính lại thay đổi theo ý định nghiệp vụ, ghi CAS mới hoặc trả conflict**. CAS không tự merge JSON, không thay quyền của workload và không tạo giao dịch nguyên tử qua nhiều secret/path hay database.

Với **Spring Vault**, sử dụng `VaultVersionedKeyValueOperations` hoặc `VaultTemplate`/`VaultOperations` với payload CAS tường minh. Kết hợp token theo workload, policy ít quyền, retry hữu hạn, đối soát timeout, audit/metrics và integration test để tránh lost update một cách có thể kiểm chứng.

**Tài liệu tham khảo:** [HashiCorp KV v2 HTTP API](https://developer.hashicorp.com/vault/api-docs/secret/kv/kv-v2), [KV v2 Check-and-Set tutorial](https://developer.hashicorp.com/vault/tutorials/secrets-management/versioned-kv), [Spring Vault versioned KV operations](https://docs.spring.io/spring-vault/reference/api/java/org/springframework/vault/core/VaultVersionedKeyValueOperations.html). Đối chiếu chức năng với phiên bản Vault/Spring Vault đang sử dụng.
