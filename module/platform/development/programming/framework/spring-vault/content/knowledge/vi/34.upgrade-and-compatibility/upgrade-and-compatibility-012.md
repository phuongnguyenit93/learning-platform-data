# Lập kế hoạch triển khai khi nhiều phiên bản ứng dụng cùng hoạt động

## 1. Bài toán nâng cấp không dừng đồng loạt

Trong hệ thống sử dụng **Spring Vault**, quá trình nâng cấp thường không đưa toàn bộ các instance Java sang phiên bản mới cùng một thời điểm. Khi triển khai **rolling update**, **canary** hoặc **blue/green**, trong một khoảng thời gian sẽ có cả ứng dụng **v1** và **v2** đang truy cập **cùng HashiCorp Vault**.

Cả hai có thể dùng **VaultTemplate/VaultOperations** để đọc KV secrets, xin dynamic credentials, gọi Transit encryption, nhận chứng thư PKI và quản lý token/lease. Nếu cùng lúc thay đổi đường dẫn secret, cấu trúc JSON, policy ACL hoặc khóa Transit mà không chuẩn bị tương thích, bản cũ có thể hỏng ngay cả khi bản mới vẫn chạy tốt.

Ví dụ:

- **orders-api v1** đọc trường **db_url** trong KV v2 tại **kv-app/orders/service**.
- **orders-api v2** chuyển sang trường **jdbc_url**, đồng thời dùng phiên bản Spring Vault mới hơn.
- Kubernetes đang chạy 70% v1 và 30% v2, còn một số v1 có thể được khởi động lại do autoscaling.
- Nếu người vận hành xóa **db_url** trước khi toàn bộ v1 biến mất, các instance v1 đang chạy hoặc được khởi động lại sẽ không thể đọc cấu hình.

Bài này hướng dẫn lập kế hoạch triển khai **khi nhiều phiên bản cùng tồn tại**, bao gồm:

1. Xác định **hợp đồng chia sẻ** giữa ứng dụng và Vault.
2. Thiết kế thay đổi **tương thích ngược** trong giai đoạn triển khai hỗn hợp.
3. Tạo **ma trận tương thích** cho runtime, Spring Vault, Vault server, auth, KV, Transit, PKI và policy.
4. Thực hiện **expand → migrate → contract**, rollout theo canary và rollback có thể kiểm chứng.
5. Viết Java hỗ trợ đọc cả schema cũ và mới, không lộ secret.
6. Kiểm thử tích hợp và giám sát lỗi riêng cho từng version trước khi dọn hợp đồng cũ.

**Nguyên tắc bao trùm:** trạng thái **“v2 chạy thành công” không chứng minh “v1 đã an toàn”**. Trong toàn bộ cửa sổ mixed-version, mọi thao tác thay đổi ở Vault phải tiếp tục phục vụ **toàn bộ các version còn có thể chạy hoặc rollback**.

## 2. Những lớp tương thích phải quản lý

Có nhiều “phiên bản” khác nhau, không được dùng một con số chung để suy luận chúng tương thích.

| Lớp | Ví dụ | Rủi ro khi nâng cấp |
| --- | --- | --- |
| **Ứng dụng** | orders-api v1 và v2 | Tên trường, fallback, validation và cache khác nhau |
| **Spring Vault Core** | Dependency của mỗi image Java | Method signature, serialization, exception/HTTP adapter hoặc yêu cầu framework khác |
| **Spring Boot / Spring Cloud Vault** | BOM, auto-configuration, auth properties | Lệch release train, cách khởi tạo bean/session khác |
| **Java runtime / TLS** | JDK, truststore và HTTP client | Trust chain, hostname verification, cipher suites và kết nối |
| **Vault server** | Vault cluster đang vận hành | Endpoint, auth plugin, policy behavior, giới hạn hoặc tính năng phụ thuộc server version |
| **Secrets engine + mount** | KV v1/v2, Transit, PKI | API path, dữ liệu phiên bản, khả năng mã hóa/giải mã |
| **Vault policy / identity** | Kubernetes role, AppRole, JWT, ACL | 403 khi path mới chưa được cấp quyền; role cũ bị thu hồi |
| **Secret contract** | db_url, jdbc_url, credential, expires_at | Bản cũ không đọc được schema mới |
| **Token/lease/certificate lifecycle** | TTL, renewal, notAfter | Workload cũ vẫn giữ token, lease hoặc chứng thư chưa hết hạn |

**Version của ứng dụng khác version của secret KV v2.** Ví dụ **orders-api v2** có thể đọc **version 7** của bản ghi KV; số **7** là lần cập nhật dữ liệu ở Vault, không phải schema version hay version của ứng dụng.

Tương tự, tiền tố **vault:v3:** trong ciphertext Transit nói tới **phiên bản khóa Transit**, không chỉ ra ứng dụng v3 hoặc Spring Vault v3.

### Ma trận kiểm chứng tối thiểu

Trước khi rollout, lập một ma trận từ dữ liệu thật của từng môi trường:

| Thành phần | v1 đang chạy | v2 chuẩn bị triển khai | Điều cần xác minh |
| --- | --- | --- | --- |
| Java / Spring Boot | Ghi version hiện tại | Ghi version đích | BOM, JDK và migration notes |
| spring-vault-core | Ghi resolved dependency | Ghi resolved dependency | API đang gọi, auth/session, client HTTP |
| Vault server | Cùng cluster | Cùng cluster | Endpoint mà cả hai client sử dụng |
| KV mount | kv-app, KV v2 | kv-app, KV v2 | Path và schema đọc/ghi |
| Auth role | orders-api-v1 | orders-api-v2 hoặc role phù hợp | Token TTL, policy, namespace và service account |
| Transit key | orders | orders | Khả năng decrypt ciphertext cũ sau rotate |
| PKI role/trust | server role, CA chain cũ | Role/CA chain dự kiến | Chứng thư cũ và mới đều được client tin cậy |
| Tính năng mới | Chưa biết trường mới | Có thể dùng trường mới | Có feature flag và khả năng rollback |

Không hardcode một bảng **Spring Boot X chỉ dùng Spring Vault Y** khi chưa đối chiếu tài liệu tương thích chính thức của phiên bản cụ thể. Với Spring Cloud Vault, dùng BOM/release train được hỗ trợ; với Spring Vault Core, kiểm tra dependencies thực đã resolve và yêu cầu Java/Spring Framework trong tài liệu release tương ứng.

## 3. Hình dung cửa sổ triển khai hỗn hợp

~~~mermaid
sequenceDiagram
    participant Ops as Release/Secrets job
    participant KV as Vault KV v2
    participant Old as orders-api v1
    participant New as orders-api v2

    Ops->>KV: Expand: giữ db_url, thêm jdbc_url
    Old->>KV: GET orders/service
    KV-->>Old: db_url + jdbc_url
    Old->>Old: Chỉ dùng db_url
    New->>KV: GET orders/service
    KV-->>New: db_url + jdbc_url
    New->>New: Ưu tiên jdbc_url, fallback db_url
    Note over Old,New: Canary/rolling: cả hai chạy song song
    Ops->>Ops: Kiểm tra traffic, jobs, autoscaling, rollback
    Ops->>KV: Contract: bỏ db_url sau khi hết cửa sổ rollback
    New->>KV: GET orders/service
    KV-->>New: Chỉ còn jdbc_url
~~~

Điều quan trọng nhất không phải thứ tự Kubernetes tạo pod, mà là **thứ tự thay đổi hợp đồng**:

1. **Expand** ở Vault trước: thêm dữ liệu/path/quyền mà v2 cần, giữ nguyên dữ liệu v1 đang dùng.
2. **Rollout v2** đã có fallback và hỗ trợ cả hai trạng thái.
3. **Migrate** trạng thái, lưu lượng, job và dữ liệu theo kế hoạch.
4. **Contract**: chỉ xóa đường dẫn/trường/quyền cũ khi chứng minh không còn client cũ và không cần rollback về v1.

Nếu người vận hành thực hiện bước 4 trước bước 2 hoặc trong lúc v1 còn chạy, nâng cấp không còn tương thích ngược.

## 4. Ví dụ hợp đồng KV v2: thêm trường trước, xóa sau

Giả sử một bản ghi KV v2 ở mount **kv-app**, logical path **orders/service**, có schema ban đầu:

~~~json
{
  "db_url": "jdbc:postgresql://db.example.internal/orders"
}
~~~

**v1** chỉ biết trường **db_url**. **v2** muốn dùng tên mới **jdbc_url**.

### 4.1 Bước Expand — giữ cả hai trường

Dữ liệu trong giai đoạn hỗn hợp:

~~~json
{
  "db_url": "jdbc:postgresql://db.example.internal/orders",
  "jdbc_url": "jdbc:postgresql://db.example.internal/orders"
}
~~~

Hai tên phải trỏ tới **cùng ý nghĩa nghiệp vụ** trong lúc chuyển tiếp. Trong trường hợp chỉ đổi tên, giá trị cần đồng nhất; nếu đồng thời chuyển sang một database khác, đó là một thay đổi hành vi riêng cần kế hoạch tương thích DB và dữ liệu, không thể coi là rename đơn giản.

Trong Vault lab, người vận hành có thể thêm trường mới bằng KV v2 patch:

~~~bash
# Dùng dữ liệu minh họa, không đưa password/token thật vào shell history.
vault kv patch -mount=kv-app orders/service \
  jdbc_url="jdbc:postgresql://db.example.internal/orders"

# Kiểm tra key name mà không in giá trị bí mật thực.
vault kv get -mount=kv-app -format=json orders/service \
  | jq '.data.data | keys'
~~~

Lưu ý **vault kv patch** giữ các trường khác trong bản ghi theo semantics KV v2, trong khi **vault kv put** thường ghi **một bản dữ liệu mới từ body được gửi**, có thể bỏ mất trường không được đưa vào. Nếu nhiều writer đồng thời thay đổi bản ghi, cần phối hợp **CAS (compare-and-set)** hoặc chiến lược ghi có kiểm soát để tránh mất cập nhật.

Đường dẫn HTTP đọc là **GET /v1/kv-app/data/orders/service**; không nhầm với **GET /v1/kv-app/orders/service** của KV v1. Nếu dùng Spring Vault API KV v2, truyền logical path **orders/service** tương đối với mount **kv-app**, không tự thêm **data/** vào logical path lần nữa.

### 4.2 Bước Migrate — v2 đọc được hai trạng thái

Trong giai đoạn rollback, v2 cần đọc được:

- Bản ghi **v1 schema** chỉ có **db_url**.
- Bản ghi **expand schema** có cả **db_url** lẫn **jdbc_url**.
- Bản ghi **contract schema** chỉ có **jdbc_url** (sau khi được phép dọn).

v1 chỉ cần đọc được hai trạng thái đầu; v1 **không cần** đọc được contract schema vì contract chỉ được thực hiện khi v1 không còn thuộc tập version được hỗ trợ/rollback.

### 4.3 Bước Contract — bỏ trường cũ

Chỉ sau khi không còn v1:

~~~json
{
  "jdbc_url": "jdbc:postgresql://db.example.internal/orders"
}
~~~

**Không làm việc này trong canary.** Dọn trường có thể yêu cầu ghi lại bản ghi KV (và CAS nếu nhiều writer). Đây là một release quản trị secret riêng, có preview/diff, audit và rollback plan; không nên làm như side effect khi v2 khởi động.

**KV v2 version history không phải backup vô hạn.** Số version được giữ bị giới hạn bởi cấu hình **max_versions** và version có thể bị soft-delete hoặc destroy. Không dựa vào khả năng đọc lại bản ghi cũ nếu dữ liệu đã bị destroy hoặc quá giới hạn lưu giữ.

## 5. Java: một reader tương thích hai schema

Sử dụng **VaultOperations.opsForKeyValue("kv-app", KeyValueBackend.KV_2)** để tránh nhầm KV v1/v2. Phần ví dụ không chứa credentials thật; giá trị URL được xem là cấu hình nội bộ, không nên in ra log production.

~~~java
import java.util.Map;

import org.springframework.stereotype.Service;
import org.springframework.vault.core.VaultOperations;
import org.springframework.vault.core.VaultKeyValueOperations;
import org.springframework.vault.core.VaultKeyValueOperationsSupport.KeyValueBackend;
import org.springframework.vault.support.VaultResponse;

@Service
public final class OrdersSettingsReader {

    private final VaultKeyValueOperations kv;

    public OrdersSettingsReader(VaultOperations operations) {
        this.kv = operations.opsForKeyValue(
                "kv-app", KeyValueBackend.KV_2);
    }

    public String readJdbcUrl() {
        VaultResponse response = kv.get("orders/service");

        if (response == null || response.getData() == null) {
            throw new IllegalStateException("Thiếu cấu hình orders/service");
        }

        return resolveJdbcUrl(response.getData());
    }

    static String resolveJdbcUrl(Map<String, Object> data) {
        String legacy = optionalString(data, "db_url");
        String modern = optionalString(data, "jdbc_url");

        if (legacy != null && modern != null && !legacy.equals(modern)) {
            // Không ghi giá trị URL hoặc nội dung secret vào exception.
            throw new IllegalStateException(
                    "Hai trường cấu hình DB không đồng nhất");
        }

        String result = modern != null ? modern : legacy;
        if (result == null) {
            throw new IllegalStateException(
                    "Không có trường db_url hoặc jdbc_url hợp lệ");
        }
        return result;
    }

    private static String optionalString(Map<String, Object> data, String key) {
        Object value = data.get(key);

        if (value == null) {
            return null;
        }
        if (!(value instanceof String text) || text.isBlank()) {
            throw new IllegalArgumentException(
                    "Trường " + key + " phải là chuỗi không rỗng");
        }
        return text;
    }
}
~~~

**Điểm thiết kế:**

- **v2** ưu tiên trường mới nhưng vẫn hỗ trợ trường cũ khi rollback dữ liệu.
- Nếu cả hai trường tồn tại nhưng khác nhau, reader **fail fast** thay vì âm thầm chọn một endpoint database khác.
- **v1** tiếp tục đọc **db_url** trong suốt cửa sổ mixed-version; không cần nâng cấp tất cả instance tức thì.
- Reader không tạo quyền truy cập Vault mới; workload phải có **read** trên đúng path.
- Nếu secret không tồn tại, reader dừng theo quy tắc nghiệp vụ; không dùng URL mặc định không an toàn.
- Với các giá trị thực sự nhạy cảm như password hoặc token, không log Map, VaultResponse hoặc chuỗi đã giải mã.

**Không áp dụng tự động mẫu “hai trường giống nhau” cho mọi loại bí mật.** Với khóa mã hóa, password, token và chứng thư, ý nghĩa của “hai phiên bản hợp lệ” thường là **hai credential cùng còn hạn trong một giai đoạn chuyển tiếp**, chứ không phải sao chép cùng một giá trị sang hai tên.

## 6. Nếu hai phiên bản đều ghi KV thì sao?

Đọc tương thích dễ hơn **ghi tương thích**. Nếu **v1 writer** dùng **put** với payload chỉ có **db_url**, nó có thể ghi đè toàn bộ bản ghi và làm mất **jdbc_url** mà provisioning vừa thêm. Nếu **v2 writer** dùng put chỉ với **jdbc_url**, nó có thể xóa **db_url** và phá v1.

Các phương án:

| Phương án | Khi thích hợp | Yêu cầu |
| --- | --- | --- |
| **Single writer** | Ít thay đổi, muốn giảm rủi ro | Chỉ một job/service chịu trách nhiệm ghi; cả v1 và v2 chỉ đọc |
| **KV v2 patch** | Cập nhật vài field trên một bản ghi | Hiểu semantics, capability và kiểm chứng version |
| **CAS/versioned operations** | Có nhiều writer hoặc cạnh tranh cập nhật | Dùng **VaultVersionedKeyValueOperations** và kiểm soát version |
| **Tách path theo schema** | Cần thay đổi không thể giữ chung dữ liệu | v2 có path mới; phải dual-read/dual-write hoặc chuyển có điều phối |
| **Cửa sổ đóng băng ghi** | Migration ngắn, writer không đa dạng | Thỏa thuận downtime ghi và kiểm tra sau migration |

Spring Vault có **VaultVersionedKeyValueOperations**, hỗ trợ thao tác KV v2 gắn version/CAS. **VaultKeyValueOperations** tiện cho đọc/ghi cơ bản, nhưng các cập nhật cần CAS nên dùng API versioned và thử nghiệm rõ với phiên bản thư viện đang triển khai.

**Không coi việc giữ lịch sử KV v2 là giải pháp tự động cho race condition.** Hai writer có thể lần lượt tạo các version “hợp lệ” nhưng làm biến mất field mà phiên bản kia cần. Phải kiểm tra tính toàn vẹn của **schema hiện hành** sau từng thay đổi.

## 7. Phân quyền và danh tính trong cửa sổ mixed-version

Hai bản ứng dụng có thể được triển khai dưới các Kubernetes ServiceAccount/roles khác nhau hoặc chia sẻ cùng một role được kiểm soát. Dù chọn phương án nào, ACL phải phục vụ **toàn bộ endpoints còn cần** trong cửa sổ.

Ví dụ nếu v1 và v2 cùng đọc một KV v2 path:

~~~hcl
path "kv-app/data/orders/service" {
  capabilities = ["read"]
}
~~~

Nếu v2 chuyển sang **kv-app/data/orders/service-v2**, trong lúc hỗn hợp phải giữ đường cũ cho v1 và cấp quyền đường mới cho v2 (không nhất thiết cấp cả hai quyền cho cùng một role nếu identities khác nhau).

**Ưu tiên tách policy theo ứng dụng và version** khi chức năng khác nhau:

| Identity | Phạm vi đọc | Quyền bổ sung |
| --- | --- | --- |
| orders-api-v1 | Path cũ | Chỉ endpoint nghiệp vụ cần cho v1 |
| orders-api-v2 | Path cũ (fallback), path mới khi cần | Chỉ endpoint nghiệp vụ cần cho v2 |
| vault-provisioner | Path cấu hình cần ghi và policy được giao | Quyền mutation trong job riêng |

Không cấp **sys/** hoặc root token cho v2 để “cho chắc”. Một **403 chỉ xảy ra ở v2** thường do policy chưa bao phủ path mới, role binding sai, namespace khác hoặc client library gọi endpoint khác; hãy điều tra nguyên nhân chính xác thay vì tăng quyền vô hạn.

Các bước kiểm tra:

~~~bash
# Thực hiện với token thực sự của mỗi workload, trong môi trường test.
vault token capabilities kv-app/data/orders/service
vault token capabilities kv-app/data/orders/service-v2
vault token lookup
~~~

Không in/commit token hay copy response **vault token lookup** chứa metadata nhạy cảm vào báo cáo công khai. Với auth Kubernetes/JWT/AppRole, kiểm tra từng role mapping, token TTL và gắn policy; thay đổi auth role/policy phải xảy ra **trước** khi triển khai client phụ thuộc nó.

### Cửa sổ token và lease

Một instance v1 có thể có token hợp lệ hoặc dynamic lease được cấp từ trước. Tháo pod khỏi load balancer **chưa chứng minh** tất cả công việc v1 đã hoàn thành: background jobs, queue consumers, cron và long-running connections vẫn có thể sử dụng credential cũ.

Quy trình phải xét:

- Drain request và dừng background consumer theo cách có kiểm soát.
- Thời gian sống tối đa của token/lease, khả năng renew và revocation.
- SessionManager/ClientAuthentication của từng version trong Spring Vault.
- Khả năng autoscaling hoặc rollback khởi động lại **image v1** sau khi tưởng rằng nó đã biến mất.
- Thu hồi quyền/credential cũ **sau** khi các phụ thuộc đã được xóa khỏi cửa sổ hỗ trợ.

**Thu hồi token v1 sớm có thể phá hoạt động của v1; để token cũ tồn tại quá lâu có thể làm tăng rủi ro.** Hai vấn đề phải được cân đối theo kế hoạch drain và chính sách bảo mật.

## 8. Transit: xoay khóa nhưng vẫn decrypt ciphertext cũ

Transit thường được sử dụng để mã hóa giá trị trước khi lưu DB. Ciphertext có tiền tố như **vault:v1:**, **vault:v2:** thể hiện key version dùng để mã hóa, không phải version của ứng dụng.

Khi xoay khóa Transit **orders**:

~~~bash
# Chỉ vận hành trên Vault lab hoặc theo quy trình được phê duyệt.
vault write -f transit/keys/orders/rotate
~~~

Vault tạo key version mới; những lời gọi encrypt sau này sử dụng key version mới theo cấu hình. Vault vẫn có thể decrypt ciphertext được tạo bằng version cũ khi key ring và **min_decryption_version** còn cho phép. Vì vậy, **rotate key không đồng nghĩa với việc phá ciphertext cũ ngay lập tức**.

Hệ quả cho rollout:

- **v1** và **v2** có thể vẫn cùng encrypt/decrypt bằng tên key **orders**, miễn là API, policy, context và cấu hình key tương thích.
- Trước khi tăng **min_decryption_version**, phải biết database/queue/backups còn ciphertext tạo từ version cũ hay không.
- Nếu ciphertext cũ vẫn được đọc, không được khóa khả năng decrypt version cũ chỉ vì mọi pod đã dùng thư viện mới.
- Có thể dùng **transit/rewrap/orders** để đưa ciphertext cũ sang key version mới mà không trả plaintext cho caller; ứng dụng phải quản lý cập nhật bản ghi/idempotency.
- Các key có **derived context**, convergent encryption hoặc key type khác nhau cần test đầy đủ; không đổi tham số mật mã tùy ý giữa hai bản.

Ví dụ ma trận:

| Dữ liệu | v1 cần đọc | v2 cần đọc | Hành động trước khi tăng min_decryption_version |
| --- | --- | --- | --- |
| ciphertext key v1 trong DB | Có thể còn | Có | Rewrap/migrate và kiểm chứng |
| ciphertext key v2 mới | Tùy client | Có | Test v1 decrypt nếu v1 còn chạy |
| ciphertext trong queue chưa xử lý | Có thể còn | Có thể còn | Drain queue hoặc giữ key version |
| Backups/archives | Có thể cần khi restore | Có thể cần | Thử restore có thể decrypt, giữ chính sách key retention |

**Đừng nâng min_decryption_version rồi chỉ kiểm tra dữ liệu mới.** Một version bị chặn decrypt có thể làm dữ liệu lịch sử hoặc snapshot rollback trở nên không sử dụng được.

## 9. PKI/TLS: giai đoạn chuyển CA phải có trust overlap

Ứng dụng Java có thể sử dụng Spring Vault để xin chứng thư PKI và cũng dùng TLS để kết nối Vault server. Khi thay CA hoặc issuer, nhiều phiên bản ứng dụng có thể giữ **truststore khác nhau**.

Kế hoạch chuyển CA thường gồm:

1. Phát hành **CA chain mới** và chuẩn bị trust bundle phù hợp.
2. Cập nhật **truststore của mọi client cần kết nối**, sao cho trong giai đoạn chuyển tiếp tin cậy cả CA cũ và mới theo chính sách tổ chức.
3. Chỉ sau khi các client cũ đã có khả năng trust chain mới, bắt đầu đổi chứng thư server/issuer.
4. Kiểm thử **DNS SAN, IP SAN, hostname verification**, notBefore/notAfter, mTLS và cipher suites.
5. Để CA cũ hết giai đoạn sử dụng rồi thu hồi loại bỏ có kiểm soát, không xóa sớm trong cửa sổ rollback.

~~~mermaid
flowchart LR
    Old["v1: trust CA cũ"] --> Overlap["Cập nhật trust: CA cũ + CA mới"]
    New["v2: trust CA cũ + CA mới"] --> Overlap
    Overlap --> Switch["Đổi certificate/issuer"]
    Switch --> Verify["Cả v1 và v2 bắt tay TLS thành công"]
    Verify --> Remove["Loại CA cũ sau khi hết khả năng rollback"]
~~~

Không hạ cấp **HTTPS → HTTP**, không dùng trust-all hoặc tắt hostname verification để vượt qua lỗi khi nâng cấp. Việc không thể bắt tay TLS cần được xử lý trước khi thao tác ACL, vì request có thể chưa đến Vault.

### Chứng thư do PKI cấp cho workload

Khi thay role PKI hoặc TTL cấp chứng thư, xét **notAfter của certificate đã cấp**, lease/token liên quan và cách TLS listener reload. Token của Vault hết hạn không làm chứng thư X.509 tự hết hạn đúng lúc đó, và deploy version mới không tự thay chứng thư đã load trong runtime.

Nếu service mesh/sidecar, Java app hoặc proxy khác nhau quản lý certificate, test cả hai đường cài đặt trong rollout, không chỉ API issue trả thành công.

## 10. Thư viện và cấu hình Spring Vault: đừng trộn các release tùy tiện

Nâng cấp thư viện Java khác với sửa schema secret. Một image v1 có thể dùng Spring Vault cũ, trong khi v2 dùng dependency mới và vẫn gọi cùng Vault cluster.

Những điểm cần kiểm tra trong từng artifact:

| Hạng mục | Câu hỏi cần trả lời |
| --- | --- |
| **Dependency management** | Spring Boot BOM, Spring Cloud release train, Spring Vault Core có cùng tập version được hỗ trợ không? |
| **Java/JDK** | Runtime target có đáp ứng yêu cầu library mới và truststore/cipher suites không? |
| **API** | Phương thức **VaultOperations**, **VaultKeyValueOperations**, Transit/PKI/Token APIs đang dùng có đổi signature/semantics không? |
| **KV backend** | Code gọi đúng KV v1 hay KV v2? API có tự phát hiện backend hay đã chỉ định **KeyValueBackend.KV_2**? |
| **Authentication** | Kubernetes/JWT/AppRole có đổi cấu hình role, login mount hoặc JWT audience không? |
| **Session lifecycle** | Client quản lý token renew/re-login/revoke thế nào? |
| **HTTP stack** | TLS trust, timeout, proxy, exception mapping và retry có thay đổi khi nâng library không? |
| **Serialization** | Null vs missing field, type conversion của JSON, Unicode, date/TTL có thay đổi không? |
| **Spring Cloud Vault** | ConfigData import, property sources, bootstrap và auto-config có còn hợp đồng mong đợi không? |

Ví dụ khác biệt API cần tránh:

~~~java
// Khi đã biết mount là KV v2:
VaultKeyValueOperations kv = vaultOperations.opsForKeyValue(
        "kv-app",
        VaultKeyValueOperationsSupport.KeyValueBackend.KV_2);

VaultResponse response = kv.get("orders/service");

// Khi cần đọc version cụ thể hoặc dùng CAS:
VaultVersionedKeyValueOperations versioned =
        vaultOperations.opsForVersionedKeyValue("kv-app");
~~~

**Không copy đoạn ví dụ của một release Spring Vault khác vào cả hai image mà chưa đối chiếu Javadoc tương ứng.** Một số phương thức và overload xuất hiện theo release; chọn dependency qua BOM và chạy compile/test cho từng version image.

Khi nâng Spring Cloud Vault, xem cả cơ chế nạp config ở startup; nếu một bản chỉ đọc secret khi khởi động, còn bản khác có refresh theo lifecycle khác, thời điểm nhìn thấy schema mới sẽ khác nhau. Không mặc định một thay đổi KV lập tức đi vào mọi JVM.

## 11. Rollout theo giai đoạn và điều kiện dừng

Đây là đề xuất vận hành cho nâng **orders-api v1 → v2**, trong đó thay field KV **db_url → jdbc_url**. Mỗi giai đoạn chỉ chuyển tiếp nếu điều kiện kiểm chứng đạt.

### Giai đoạn 0 — Inventory và chuẩn bị

- Chốt danh sách image version, số replica, cronjobs, consumers, long-lived tasks và cơ chế rollback.
- Ghi nhận Java/Spring Vault/Vault server/plugin versions đang dùng.
- Liệt kê path KV, policy, auth role, Transit keys, PKI issuers và TTL/token/lease liên quan.
- Kiểm tra có những phiên bản **v1 vẫn có thể được autoscale/restart** không.
- Chụp trạng thái cấu hình theo cơ chế backup an toàn; không xuất secret plaintext vào artifact báo cáo hoặc Git.
- Lập tiêu chí **go/no-go** và danh sách người có quyền rollback.

### Giai đoạn 1 — Expand hợp đồng

- Thêm **jdbc_url** vào secret, giữ **db_url**; xác minh hai trường cùng ý nghĩa.
- Tạo policy/auth binding cho v2 trước, không xóa policy cũ.
- Nếu cần CA mới, cập nhật truststore trước khi đổi issuer/server certificate.
- Nếu cần Transit key rotation, xác minh cả old/new ciphertext có thể decrypt.
- Dùng Vault lab/staging để chạy cả v1 và v2 với dữ liệu tương thích.

### Giai đoạn 2 — Canary v2

- Triển khai **1–5%** traffic hoặc một số replica v2 phù hợp với mức rủi ro.
- Cho v1 và v2 đọc cùng secret trong thời gian đủ để đi qua startup, cache refresh, token renewal và các đường nghiệp vụ chính.
- Chạy smoke tests: KV read, Transit encrypt/decrypt, PKI/TLS, token/lease renew nếu thuộc luồng ứng dụng.
- Đặt guardrail: tỷ lệ **403**, lỗi thiếu field, TLS handshake, latency p95/p99, startup failures, 5xx và token reauth.
- Nếu lỗi vượt ngưỡng, dừng rollout và điều tra trước khi tăng traffic.

Các tỷ lệ **1–5%** là ví dụ quy trình, không phải tiêu chuẩn bắt buộc; chọn theo lưu lượng và yêu cầu an toàn của hệ thống.

### Giai đoạn 3 — Rolling rollout và drain

- Tăng tỷ lệ v2 từng bước có thời gian quan sát.
- Bảo đảm v1 và v2 đều hoạt động trên hợp đồng **expand**.
- Đối chiếu cả request web, background jobs, queue messages, timers và migration tasks.
- Dừng v1 có kiểm soát, chặn cơ chế autoscale/rollback tự tạo thêm instance v1 ngoài kế hoạch.
- Giữ dữ liệu/quyền cũ qua một **rollback window** đủ cho hoạt động thực tế và vòng đời token/lease/chứng thư.

### Giai đoạn 4 — Contract có điều kiện

Chỉ sau khi chứng minh v1 không còn chạy và rollback về v1 không còn thuộc kế hoạch:

- Xóa **db_url** qua một thay đổi cấu hình riêng có phê duyệt.
- Thu hẹp policy/path cũ không còn sử dụng.
- Tắt auth role cũ khi không còn client/lease/token hợp lệ cần đến nó và kế hoạch thu hồi đã được chấp thuận.
- Điều chỉnh Transit **min_decryption_version** chỉ khi ciphertext và backups đã được đánh giá.
- Loại CA cũ chỉ khi không còn client/certificate phụ thuộc.
- Giữ khả năng phục hồi theo thủ tục mới thay vì giả định có thể quay lại v1.

**Contract là thay đổi có thể phá rollback.** Việc hoàn thành rolling update không tự động cho phép dọn tất cả thành phần cũ.

## 12. Ma trận thử nghiệm cho hai phiên bản cùng hoạt động

Một test suite cho v2 chạy độc lập là **chưa đủ**. Cần dựng **cặp version × schema** trong Vault test.

### 12.1 Test hợp đồng KV

| Ứng dụng | Secret chỉ có db_url | Secret có cả hai field | Secret chỉ có jdbc_url |
| --- | --- | --- | --- |
| **v1** | Pass | Pass | **Fail — dự kiến** |
| **v2 compatible reader** | Pass qua fallback | Pass; xác minh đồng nhất | Pass |
| **v2 strict sau contract** | Có thể Fail | Pass | Pass |

**Trong mixed-version window chỉ được dùng hai cột đầu**, trừ khi v1 đã được sửa để hỗ trợ schema mới.

Test đơn vị cho mapper ở mục 5:

~~~java
import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import java.util.Map;

import org.junit.jupiter.api.Test;

class OrdersSettingsCompatibilityTest {

    private static final String URL =
            "jdbc:postgresql://db.example.internal/orders";

    @Test
    void readsLegacySchema() {
        assertThat(OrdersSettingsReader.resolveJdbcUrl(
                Map.of("db_url", URL))).isEqualTo(URL);
    }

    @Test
    void readsExpandedSchema() {
        assertThat(OrdersSettingsReader.resolveJdbcUrl(
                Map.of("db_url", URL, "jdbc_url", URL))).isEqualTo(URL);
    }

    @Test
    void readsContractSchemaAfterOldVersionIsGone() {
        assertThat(OrdersSettingsReader.resolveJdbcUrl(
                Map.of("jdbc_url", URL))).isEqualTo(URL);
    }

    @Test
    void rejectsConflictingFields() {
        assertThatThrownBy(() -> OrdersSettingsReader.resolveJdbcUrl(
                Map.of(
                    "db_url", "jdbc:postgresql://db-a/orders",
                    "jdbc_url", "jdbc:postgresql://db-b/orders")))
                .isInstanceOf(IllegalStateException.class);
    }

    @Test
    void rejectsMissingFields() {
        assertThatThrownBy(() -> OrdersSettingsReader.resolveJdbcUrl(
                Map.of("feature_enabled", true)))
                .isInstanceOf(IllegalStateException.class);
    }
}
~~~

### 12.2 Integration test với Vault test

Vault test cần mount **kv-app** kiểu KV v2, bản ghi **orders/service** có cả hai field và workload được cấp **read**. Test chỉ đọc, không sửa bí mật dùng chung:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.vault.core.VaultOperations;
import org.springframework.vault.core.VaultKeyValueOperations;
import org.springframework.vault.core.VaultKeyValueOperationsSupport.KeyValueBackend;
import org.springframework.vault.support.VaultResponse;

@SpringBootTest
class MixedVersionKvContractIT {

    @Autowired
    VaultOperations vaultOperations;

    @Test
    void expandedSecretSupportsBothFieldNames() {
        VaultKeyValueOperations kv = vaultOperations.opsForKeyValue(
                "kv-app", KeyValueBackend.KV_2);

        VaultResponse response = kv.get("orders/service");
        assertThat(response).isNotNull();
        assertThat(response.getData()).isNotNull();
        assertThat(response.getData()).containsKeys(
                "db_url", "jdbc_url");

        // Không in URL/config/credential ra assertion message.
        assertThat(OrdersSettingsReader.resolveJdbcUrl(response.getData()))
                .isNotBlank();
    }
}
~~~

Với CI, chạy **image v1** và **image v2** tách biệt trên cùng một môi trường Vault test được cô lập; xác minh v1 vẫn đọc được schema expand, trong khi v2 đọc được cả schema legacy và expand. Unit test của một class v2 không chứng minh bytecode v1 vẫn tương thích với secret hiện hành.

### 12.3 Các tình huống bổ sung cần test

| Kịch bản | Đầu ra mong đợi |
| --- | --- |
| v1 và v2 đồng thời đọc một KV path | Không lỗi schema, cả hai dùng cùng cấu hình hợp lệ |
| Nhiều writer cùng cập nhật | CAS/patch chặn lost update hoặc có cơ chế điều phối |
| v2 cần path mới | Policy/auth role cấp đủ, v1 path cũ vẫn hoạt động |
| v1 decrypt ciphertext mới sau Transit rotate | Pass nếu key/context/policy hỗ trợ |
| v2 đọc ciphertext cũ trong DB | Pass trước khi đổi min_decryption_version |
| v1 nhận certificate mới | TLS handshake thành công sau trust overlap |
| Token v1 renew trong lúc v2 canary | Không 403 do policy/role bị xóa sớm |
| Workload có cache config | Khi refresh/restart vẫn đọc schema tương thích |
| Queue có message v1 | v2 đọc/ghi hoặc xử lý theo schema message thích hợp |
| Rollback v2 → v1 | Secret/policy/CA/key vẫn phục vụ v1 |
| Một instance dùng thư viện Spring Vault mới | Thực thi endpoint và exception mapping đúng |
| Một phần v2 fail | Traffic quay về v1 mà không cần phá contract đã expand |

**Không dùng production Vault để test phá dữ liệu** như destroy KV version, trim Transit key hoặc thu hồi CA. Dùng Vault lab hoặc bản sao cấu hình được phép, với fake secrets.

## 13. Quan sát theo version và điều kiện rollback

Khi hai version cùng chạy, chỉ xem error rate tổng có thể che giấu vấn đề: 5% v2 fail hoàn toàn nhưng 95% v1 vẫn tốt khiến tỷ lệ lỗi chung trông có vẻ chấp nhận được.

Các metric nên phân chia theo **app_version, operation, outcome** và **environment** với tập giá trị có kiểm soát:

| Metric gợi ý | Cần phát hiện |
| --- | --- |
| **vault_operation_errors_total{app_version,reason}** | 403, 404, TLS, timeout, 5xx theo version |
| **vault_secret_contract_failure_total{app_version}** | Thiếu field, sai type, hai field không đồng nhất |
| **vault_kv_read_duration_seconds{app_version}** | p95/p99 latency KV v1 vs v2 |
| **vault_auth_login_failures_total{app_version}** | Role/JWT/token login bất thường |
| **vault_token_renew_failures_total{app_version}** | Token/SessionManager thay đổi hành vi |
| **vault_transit_decrypt_errors_total{app_version}** | Ciphertext cũ mới, key/context mismatch |
| **vault_tls_handshake_failures_total{app_version}** | Truststore, SAN, CA rotation |
| **app_ready_replicas{app_version}** | Instance phiên bản nào chưa sẵn sàng |
| **queue_consumer_lag{app_version}** | Background consumers cũ/mới bị nghẽn |
| **rollback_readiness_check** | Hợp đồng cũ còn phục vụ rollback được không |

Tên metric chỉ là đề xuất cho Micrometer/Prometheus; không phải metric mặc định do Spring Vault tự phát sinh.

**Không gắn** token, full secret path nhạy cảm, plaintext KV, database URL, ciphertext hoặc tenant ID không kiểm soát vào metric labels/logs.

### Go/no-go và rollback

Một kế hoạch release nên có ngưỡng đã được nhóm vận hành thống nhất, ví dụ:

- Nếu lỗi **schema_contract** ở v2 lớn hơn 0 với một đường bắt buộc, **dừng tăng canary**.
- Nếu 403/TLS/token renewal tăng chỉ ở v2, **chặn rollout** và điều tra identity/compatibility.
- Nếu p95/p99 tăng vượt SLO hoặc v2 không xử lý được queue message v1, **rollback v2** khi contract cũ vẫn còn.
- Nếu đã contract và loại **db_url**, rollback về v1 có thể **không còn an toàn**. Phải phục hồi hợp đồng KV trước hoặc chọn hướng khắc phục khác theo runbook.

Những tiêu chí này cần cụ thể theo từng môi trường; không lấy số lượng request nhỏ ở canary làm bằng chứng an toàn cho mọi trường hợp.

## 14. Những sai lầm thường gặp

| Sai lầm | Hậu quả | Biện pháp |
| --- | --- | --- |
| Xóa field KV cũ ngay khi v2 deploy | v1 lỗi khi đọc/khởi động lại | Expand trước, contract sau |
| Chỉ test v2 trên schema mới | Không biết v1 còn chạy được không | Test v1 × schema expand |
| Đổi KV v1 sang KV v2 mà không sửa path | 404/403 vì endpoint và ACL khác | Kế hoạch migration engine/path và policy riêng |
| Nhiều writer dùng KV v2 put không CAS | Mất field giữa hai lần cập nhật | Single writer, patch/CAS, concurrency test |
| Tháo quyền auth/policy v1 quá sớm | v1 hoặc job cũ bị 403 | Drain, kiểm tra token/lease/rollback window |
| Xoay Transit rồi chặn decrypt key cũ ngay | Không giải mã được ciphertext lịch sử | Rewrap/migrate trước, test restore |
| Đổi CA không có trust overlap | TLS fail ở các pod cũ | Cập nhật truststore trước khi đổi cert |
| Nghĩ Spring Boot/Spring Vault có version giống nhau | Dependency conflict hoặc API không khớp | Kiểm tra BOM, release notes, resolved graph |
| Chỉ so sánh error rate chung | Lỗi canary bị che bởi traffic v1 | Metric theo app_version |
| Contract trong cùng release với canary | Rollback phá bí mật/đường dẫn cũ | Tách release dọn dữ liệu |
| Dùng root token để kiểm thử | Không phát hiện ACL sai | Token workload thật với policy tối thiểu |
| Log VaultResponse để debug | Lộ secret/credential | Log operation/status/correlation ID đã làm sạch |
| Coi pod v1 = 0 là đã hết v1 | Cron/queue/autoscale/rollback có thể khởi tạo v1 | Kiểm soát toàn bộ nguồn chạy v1 |

## 15. Checklist chốt kế hoạch triển khai

1. **Inventory:** biết chính xác version nào còn chạy/có thể rollback, kể cả jobs và consumers.
2. **Compatibility matrix:** đối chiếu Spring Boot/Cloud/Vault dependencies, Java, Vault server, plugins và API đang gọi.
3. **Secret contract:** định nghĩa field/path cũ-mới và thời gian cùng tồn tại; thử tất cả tổ hợp cần hỗ trợ.
4. **ACL/auth:** cấp quyền endpoint mới trước rollout; chỉ xóa quyền cũ sau drain/rollback window.
5. **KV writes:** kiểm soát put/patch, CAS và nhiều writer để không mất field.
6. **Transit:** giữ khả năng decrypt ciphertext cũ; trì hoãn thay đổi min_decryption_version cho đến khi dữ liệu được migrate.
7. **PKI/TLS:** chuẩn bị trust overlap, kiểm tra SAN, notAfter, reissue và TLS listener reload.
8. **Token/lease:** đánh giá TTL, renew/revoke và tác vụ nền lâu dài; không thu hồi sớm quyền cần cho v1.
9. **Canary/rolling:** tăng phiên bản theo giai đoạn, có tiêu chí dừng và rollback đã kiểm thử.
10. **Observability:** đo lỗi/latency/auth/TLS theo **app_version**; không log secret.
11. **Contract:** dọn path/field/role/CA/key cũ trong release riêng, sau khi xác nhận v1 không còn được dùng.
12. **Recovery:** biết khôi phục cả artifact lẫn hợp đồng Vault khi rollback, không chỉ redeploy image cũ.

**Kết luận:** nâng cấp **SPRING_VAULT** khi nhiều phiên bản ứng dụng cùng hoạt động là bài toán **tương thích hợp đồng và vòng đời bí mật**, không chỉ là thay dependency hoặc rolling restart. Trong giai đoạn mixed-version, thiết kế **expand → migrate → contract**, kiểm thử kết hợp v1/v2, giữ ranh giới ACL và mật mã, rồi dọn trạng thái cũ chỉ khi cửa sổ rollback đã thực sự kết thúc.

## Tài liệu tham khảo chính thức

- [Spring Vault — VaultOperations API](https://docs.spring.io/spring-vault/reference/api/java/org/springframework/vault/core/VaultOperations.html).
- [Spring Vault — VaultKeyValueOperations API](https://docs.spring.io/spring-vault/reference/api/java/org/springframework/vault/core/VaultKeyValueOperations.html).
- [Spring Vault — VaultVersionedKeyValueOperations API](https://docs.spring.io/spring-vault/reference/api/java/org/springframework/vault/core/VaultVersionedKeyValueOperations.html).
- [Spring Vault — Authentication](https://docs.spring.io/spring-vault/reference/vault/authentication.html).
- [Spring Cloud Release Train Reference](https://docs.spring.io/spring-cloud-release/reference/index.html).
- [Spring Boot — Upgrading](https://docs.spring.io/spring-boot/upgrading.html).
- [HashiCorp Vault — KV v1/v2 version comparison](https://developer.hashicorp.com/vault/docs/secrets/kv).
- [HashiCorp Vault — KV v2 HTTP API](https://developer.hashicorp.com/vault/api-docs/secret/kv/kv-v2).
- [HashiCorp Vault — Transit Secrets Engine](https://developer.hashicorp.com/vault/docs/secrets/transit).
- [HashiCorp Vault — Transit HTTP API](https://developer.hashicorp.com/vault/api-docs/secret/transit).
