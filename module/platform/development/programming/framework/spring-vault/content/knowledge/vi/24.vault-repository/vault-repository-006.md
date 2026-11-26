# CrudRepository với thao tác lưu, đọc và xóa trong Spring Vault

## 1. Mục tiêu bài học và bài toán thực tế

Trong chương **Vault Repository** của module **SPRING_VAULT**, ứng dụng Java thường dùng `VaultTemplate` để truy cập HashiCorp Vault, lưu KV secrets, đọc cấu hình nhạy cảm, hoặc thao tác với Transit/PKI. Tuy nhiên, nếu ứng dụng có nhiều đối tượng Java phải lưu vào KV secrets engine, việc tự dựng đường dẫn, chuyển đổi `Map<String, Object>` sang POJO và xử lý thao tác đọc/ghi có thể lặp lại ở nhiều lớp.

**Spring Vault Repositories** áp dụng mô hình **Spring Data Repository** vào Vault KV secrets engine: một interface kế thừa `CrudRepository<T, String>` cung cấp các thao tác cơ bản như `save`, `findById`, `existsById`, `findAll`, `count`, `deleteById` và `delete`. Spring Vault dùng `VaultTemplate`, mapping metadata và Vault policy ở phía sau để thực hiện các yêu cầu tương ứng.

Ví dụ xuyên suốt: dịch vụ thanh toán lưu API key **giả** của từng đối tác vào mount KV v2 `kv-app`, dưới namespace dữ liệu `partner-credentials`. Mỗi đối tác có một `id` dạng chuỗi, một URL và một API key. Ứng dụng cần **lưu**, **đọc lại**, **cập nhật** và **xóa** bản ghi bằng Java; đồng thời hiểu đúng việc xóa KV v2 là xóa mềm, không phá hủy dữ liệu trong các version cũ.

Sau bài học, bạn có thể:

- Cấu hình entity bằng `@Secret` và `@Id`, repository bằng `CrudRepository` và `@EnableVaultRepositories`.
- Dùng `save` để tạo/cập nhật, `findById`/`existsById` để đọc và `deleteById`/`delete` để xóa.
- Nhận biết đường dẫn logic `keyspace/id` và đường dẫn HTTP thực tế của KV v1/KV v2.
- Phân biệt xóa KV v2 thông qua repository với destroy version và xóa metadata/toàn bộ lịch sử.
- Sử dụng `@Version` cho optimistic locking và tránh cập nhật đè phiên bản.
- Viết test cho business service và kiểm thử tích hợp với Vault test server, đồng thời tôn trọng ACL, lifecycle token và log an toàn.

> **Giả định:** Vault đã có mount `kv-app` dùng KV v2, Spring Vault có kết nối HTTPS và xác thực workload hợp lệ, Vault policy cho phép thao tác trên phạm vi bài học. Tên mount/role, URL và API key trong mã đều là dữ liệu minh họa; không dùng credential production.

## 2. Vault Repository thực sự là gì?

Một repository là lớp trừu tượng để thao tác **key/value secrets**, không phải database quan hệ, không phải JPA repository và cũng không phải công cụ xử lý mọi secrets engine của Vault.

~~~mermaid
flowchart LR
    A[Payment Service] --> B[PartnerCredentialRepository<br/>CrudRepository]
    B --> C[Spring Data Vault Repository<br/>Mapping + Converter]
    C --> D[VaultTemplate<br/>SessionManager]
    D --> E[Vault KV v2<br/>kv-app]
    E --> F[Secret key<br/>partner-credentials/partner-a]
~~~

| Thành phần | Vai trò | Điều cần nhớ |
|---|---|---|
| `@Secret` | Xác định **backend/mount** và **keyspace** của entity | `backend="kv-app"`, `value="partner-credentials"`; không phải endpoint HTTP đầy đủ. |
| `@Id` | Xác định mã định danh của object | ID của Vault Repository phải là `String`. |
| `CrudRepository<Entity, String>` | Định nghĩa các phương thức CRUD chuẩn Spring Data | Thực thi **đồng bộ**, dựa trên Vault KV. |
| `@EnableVaultRepositories` | Kích hoạt quét repository interface | Phải có Spring Data components và bean `VaultTemplate` tương thích. |
| `VaultConverter` | Chuyển POJO sang `SecretDocument`/JSON và ngược lại | Ghi object là ghi toàn bộ document, không phải patch từng field. |
| `VaultTemplate` | Gửi request Vault có xác thực | Sử dụng `SessionManager` lấy Vault client token. |
| Vault KV v1/v2 | Nơi lưu dữ liệu | KV v2 có các version; repository hỗ trợ KV v2 từ Spring Vault 2.4. |

Spring Vault xác định **phiên bản KV engine lúc chạy**. Khi dùng repository trên KV v2, thư viện biết cách dùng đường dẫn dữ liệu `/data/...` và metadata/version theo API Vault. Cơ chế nhận biết mount cần tra cứu endpoint `sys/internal/ui/mounts/...`; Vault token của ứng dụng phải có quyền phù hợp để tra cứu, nếu bị từ chối thì repository có thể thất bại ngay trước khi thao tác CRUD.

### Repository phù hợp khi nào?

**Nên dùng** khi lưu những nhóm đối tượng nhỏ, có ID rõ ràng, cần CRUD lặp lại trên một keyspace, và muốn ánh xạ POJO nhất quán.

**Cân nhắc dùng trực tiếp `VaultTemplate`** khi cần điều khiển chính xác KV metadata, CAS, destroy/version, Transit, PKI, lease hoặc API HTTP đặc thù. Repository không thay thế engine-specific operations cho những nghiệp vụ đó.

## 3. Dependency và kích hoạt repository

Vault Repository dựa trên Spring Data Commons/KeyValue và Spring Vault Core. Với một dự án Spring Boot đã chọn BOM tương thích, ví dụ dependency Gradle:

~~~groovy
dependencies {
    implementation("org.springframework.vault:spring-vault-core")
    implementation("org.springframework.data:spring-data-keyvalue")
    // Khi cần Vault tự cấu hình qua Spring Cloud Vault:
    // implementation("org.springframework.cloud:spring-cloud-starter-vault-config")
    testImplementation("org.springframework.boot:spring-boot-starter-test")
}
~~~

`spring-data-commons` thường là dependency bắc cầu của `spring-data-keyvalue`, nhưng cần có trong dependency graph. **Không ghép phiên bản Spring Vault/Spring Data/Spring Framework tùy ý**: dùng BOM Spring Boot/Spring Cloud tương thích, hoặc Spring Data BOM nếu dự án tự quản dependency.

Cấu hình Java sau bật scan các repository trong package của `PartnerCredentialRepository`:

~~~java
package com.example.payments.vault;

import org.springframework.context.annotation.Configuration;
import org.springframework.vault.repository.configuration.EnableVaultRepositories;

@Configuration(proxyBeanMethods = false)
@EnableVaultRepositories(
        basePackageClasses = PartnerCredentialRepository.class)
public class VaultRepositoryConfiguration {
    // Bean VaultTemplate phải tồn tại trong ApplicationContext.
    // Có thể do Spring Cloud Vault cấu hình hoặc do dự án tự khai báo.
}
~~~

Nếu ứng dụng có nhiều `VaultTemplate`, có thể cần chọn bean bằng `vaultTemplateRef` của `@EnableVaultRepositories` (mặc định là `vaultTemplate`). Cần bảo đảm repository dùng **đúng Vault endpoint/namespace và session manager** như phần còn lại của ứng dụng.

Trong test hoặc production, đừng dùng Vault root token chỉ để repository chạy được. Xác thực theo workload (Kubernetes, AppRole, cloud identity...) phải được cấu hình trước, và Vault policy chỉ cấp quyền theo đúng keyspace.

## 4. Tạo entity với @Secret và @Id

Ví dụ entity lưu trên KV v2:

~~~java
package com.example.payments.vault;

import org.springframework.data.annotation.Id;
import org.springframework.vault.repository.mapping.Secret;

@Secret(backend = "kv-app", value = "partner-credentials")
public class PartnerCredential {

    @Id
    private String id;

    private String endpoint;
    private String apiKey;

    public PartnerCredential() {
        // Cho Spring Data mapping.
    }

    public PartnerCredential(String id, String endpoint, String apiKey) {
        this.id = id;
        this.endpoint = endpoint;
        this.apiKey = apiKey;
    }

    public String getId() {
        return id;
    }

    public void setId(String id) {
        this.id = id;
    }

    public String getEndpoint() {
        return endpoint;
    }

    public void setEndpoint(String endpoint) {
        this.endpoint = endpoint;
    }

    public String getApiKey() {
        return apiKey;
    }

    public void setApiKey(String apiKey) {
        this.apiKey = apiKey;
    }
}
~~~

`@Secret` ở package `org.springframework.vault.repository.mapping.Secret` đánh dấu aggregate root lưu trên Vault. Trong ví dụ:

- `backend = "kv-app"` là **tên mount** KV secrets engine trong Vault; nếu không chỉ định, giá trị mặc định của annotation là `secret`.
- `value = "partner-credentials"` là **keyspace/prefix** phân biệt nhóm entity trong mount.
- `@Id String id` là phần tên khóa, ví dụ `partner-a`. ID dạng `String` là yêu cầu của Vault repository.
- Không dùng `@Entity` của JPA hoặc `@Table`: đây không phải mapping database SQL.

### Đường dẫn logic và đường dẫn KV v2

Khi entity có `id = "partner-a"`, đường dẫn logic bên trong mount là:

~~~text
Mount KV v2:      kv-app
Keyspace:         partner-credentials
ID:               partner-a
Logical key:      partner-credentials/partner-a
Vault KV v2 data: /v1/kv-app/data/partner-credentials/partner-a
Vault KV v2 meta: /v1/kv-app/metadata/partner-credentials/partner-a
~~~

Đừng nhập `kv-app/data/partner-credentials/...` làm giá trị `@Secret.value`: thư viện xử lý API path theo phiên bản KV engine. Nếu mount là KV v1, HTTP path không có nhánh `data/`. Để tránh đọc/ghi nhầm secret, luôn đối chiếu mount thực tế và quyền trên nó.

### JSON document và dữ liệu nhạy cảm

Spring Vault repository serialize entity thành JSON và thường có thể kèm type hint `_class` để hỗ trợ converter. Ví dụ cấu trúc nội dung ở mức KV v2:

~~~json
{
  "_class": "com.example.payments.vault.PartnerCredential",
  "endpoint": "https://partner.example.invalid",
  "apiKey": "fake-api-key-for-tests"
}
~~~

Đây là **giá trị bên trong secret document**, không phải response JSON đầy đủ của HTTP KV v2 (HTTP API còn wrapper `data.data` và `data.metadata`). ID nằm trong key path nên không nhất thiết là field `id` trong JSON mapping.

Không viết `toString()` lộ `apiKey`; tránh debug logging chứa entity/map hoặc raw response Vault. Đối với dữ liệu Java nhạy cảm, cân nhắc loại khỏi serializer log, tránh đưa vào exception message, audit rộng quyền hoặc metric labels.

## 5. Định nghĩa interface CrudRepository

Repository là interface, không cần tự viết implementation CRUD:

~~~java
package com.example.payments.vault;

import java.util.List;
import org.springframework.data.repository.CrudRepository;

public interface PartnerCredentialRepository
        extends CrudRepository<PartnerCredential, String> {

    // Vault query derivation chỉ hỗ trợ predicate trên @Id.
    List<PartnerCredential> findByIdStartsWith(String prefix);
}
~~~

Một số thao tác quan trọng từ `CrudRepository`:

| Phương thức | Kết quả/thao tác | Ghi chú |
|---|---|---|
| `save(entity)` | Tạo hoặc cập nhật document theo entity ID | Dùng `@Version` khi cần chống ghi đè KV v2. |
| `saveAll(entities)` | Lưu tập entity | **Không có giao dịch nguyên tử trên tất cả các key**. |
| `findById(id)` | `Optional<PartnerCredential>` | Thường trả rỗng nếu key hiện hành không đọc được vì không tồn tại/đã bị delete; 403 phải là lỗi. |
| `existsById(id)` | `boolean` | Không dùng làm bước kiểm soát race condition trước khi `save`. |
| `findAll()` | Danh sách entities | Có thể cần LIST trên metadata/keyspace và đọc nhiều key. |
| `findAllById(ids)` | Đọc theo tập ID | Chỉ cấp danh sách ID đã được phép xử lý. |
| `count()` | Đếm các entity trong keyspace | Cần list; không phải phép SQL `COUNT(*)` tối ưu. |
| `deleteById(id)` | Xóa key theo ID | Trên KV v2 **không destroy toàn bộ version history**. |
| `delete(entity)` | Xóa entity | Với entity có `@Version`, semantics xóa có thể nhắm đúng version. |
| `deleteAll()` | Xóa tất cả entity trong keyspace | Thao tác rất nguy hiểm; không chạy trên production chỉ để dọn test. |

Với Spring Data hiện đại, `findById` trả `Optional`; không dùng ví dụ API rất cũ `findOne(id)` nếu dự án chạy phiên bản gần đây. Các phương thức repository là **blocking** và cần kết nối Vault. Trong WebFlux, không gọi trực tiếp chúng trên event-loop; dùng các API reactive thích hợp hoặc chuyển blocking operations sang scheduler riêng với giới hạn rõ ràng.

## 6. Thực hành lưu, đọc, sửa và xóa qua service Java

Tạo một service bao bọc repository để validate ID, phân biệt secret không tồn tại và kiểm soát thao tác sửa:

~~~java
package com.example.payments.vault;

import java.util.NoSuchElementException;
import java.util.Optional;
import java.util.regex.Pattern;
import org.springframework.stereotype.Service;

@Service
public class PartnerCredentialService {

    private static final Pattern SAFE_ID =
            Pattern.compile("[a-z0-9][a-z0-9_-]{0,63}");

    private final PartnerCredentialRepository repository;

    public PartnerCredentialService(PartnerCredentialRepository repository) {
        this.repository = repository;
    }

    // Tạo mới hoặc thay toàn bộ document tại cùng một ID.
    public PartnerCredential put(
            String id, String endpoint, String apiKey) {

        validateId(id);
        if (endpoint == null || endpoint.isBlank()
                || apiKey == null || apiKey.isBlank()) {
            throw new IllegalArgumentException(
                    "Endpoint and API key must be present");
        }

        PartnerCredential credential =
                new PartnerCredential(id, endpoint, apiKey);
        return repository.save(credential);
    }

    public Optional<PartnerCredential> find(String id) {
        validateId(id);
        return repository.findById(id);
    }

    public boolean exists(String id) {
        validateId(id);
        return repository.existsById(id);
    }

    public PartnerCredential rotateApiKey(String id, String newApiKey) {
        validateId(id);
        if (newApiKey == null || newApiKey.isBlank()) {
            throw new IllegalArgumentException("API key must be present");
        }

        PartnerCredential current = repository.findById(id)
                .orElseThrow(() -> new NoSuchElementException(
                        "Partner credential not found: " + id));
        current.setApiKey(newApiKey);
        return repository.save(current);
    }

    public void delete(String id) {
        validateId(id);
        repository.deleteById(id);
    }

    private static void validateId(String id) {
        if (id == null || !SAFE_ID.matcher(id).matches()) {
            throw new IllegalArgumentException("Invalid partner ID");
        }
    }
}
~~~

**Vì sao validate ID?** ID tham gia tạo key path trong Vault, nên không nhận tùy ý dấu `/`, `..` hoặc chuỗi không kiểm soát từ HTTP request. Biểu thức mẫu cho phép chữ thường, chữ số, gạch dưới và dấu gạch ngang, tối đa 64 ký tự. Quy tắc thực tế phải theo mô hình domain, không phải chính sách chung cho mọi Vault key.

**Vì sao cập nhật bằng `findById` rồi `save`?** Repository serialize **toàn bộ entity** thành document mới. Không thể giả định `save(new PartnerCredential(id, null, newApiKey))` chỉ sửa `apiKey` mà giữ nguyên `endpoint`; các trường không ánh xạ có thể bị mất. Khi nhiều request cùng sửa một ID, phần đọc-sửa-ghi cần `@Version`/CAS ở KV v2, được trình bày trong mục 9.

### 6.1. Tạo mới bằng save

~~~java
PartnerCredential created = service.put(
        "partner-a",
        "https://partner.example.invalid",
        "fake-api-key-A");

// ID chính là phần cuối của keyspace trong Vault.
assert "partner-a".equals(created.getId());
~~~

`save` có nghĩa **lưu entity theo ID**, không cam kết “insert only”. Nếu ID đã tồn tại mà entity không dùng optimistic locking, thao tác có thể ghi đè document đang có và ở KV v2 tạo **version mới**. Đừng dùng `existsById` rồi `save` để bảo đảm insert duy nhất: hai luồng có thể cùng thấy “chưa tồn tại”, sau đó cùng ghi. Dùng CAS hoặc thiết kế kiểm soát cạnh tranh khác cho yêu cầu này.

### 6.2. Đọc bằng findById

~~~java
Optional<PartnerCredential> found = service.find("partner-a");

found.ifPresent(entity -> {
    String endpoint = entity.getEndpoint();
    // Sử dụng endpoint theo nghiệp vụ; KHÔNG in entity.getApiKey().
});
~~~

`Optional.empty()` biểu thị entity hiện tại không được tìm thấy. Còn trường hợp Vault trả `403 permission denied` hoặc kết nối timeout **phải được coi là lỗi**, không được tùy tiện chuyển thành “không tồn tại” rồi phát sinh credential mặc định/hard-code.

### 6.3. Thay API key

~~~java
PartnerCredential updated =
        service.rotateApiKey("partner-a", "fake-api-key-B");
~~~

Với KV v2, phiên bản cũ vẫn có thể tồn tại trong lịch sử nếu Vault chưa xóa/destroy và `max_versions` chưa dọn phiên bản đó. Vì thế, **xoay API key trong KV v2** không đồng nghĩa API key A đã bị hệ thống đối tác vô hiệu hóa. Cần phối hợp issuer/đối tác để revoke A, cập nhật HTTP client dùng B và xác minh B thực sự được sử dụng.

### 6.4. Xóa bằng deleteById

~~~java
service.delete("partner-a");

boolean present = service.find("partner-a").isPresent();
assert !present;
~~~

Đoạn mã minh họa “giá trị hiện hành không còn được tìm thấy” sau khi xóa theo repository. **Nó không chứng minh toàn bộ version history đã biến mất**. Hành vi xóa chi tiết phụ thuộc KV engine và có khác biệt quan trọng ở mục tiếp theo.

## 7. Hiểu chính xác thao tác xóa trên KV v1 và KV v2

Đây là phần dễ gây nhầm lẫn nhất khi dùng `CrudRepository.delete(...)`: Spring Data gọi “delete”, nhưng Vault KV v2 phân biệt **soft delete**, **destroy version** và **delete metadata/toàn bộ lịch sử**.

| Thao tác | KV v1 | KV v2 | Kết quả |
|---|---|---|---|
| `repository.deleteById(id)` | Xóa key theo semantics KV v1 | Xóa mềm version hiện hành bằng operation `DELETE` | Không bảo đảm phá hủy các version KV v2 cũ. |
| `repository.delete(entity)` | Xóa key theo semantics KV v1 | Với entity có `@Version`, có thể xóa đúng version entity đó | Không destroy metadata/lịch sử. |
| Vault CLI `kv delete` | Xóa secret key | Soft delete latest hoặc version được chỉ định tùy lệnh | Version có thể được undelete nếu chưa destroy. |
| Vault CLI `kv destroy -versions=...` | Không áp dụng kiểu version | Hủy dữ liệu của **các version đã chỉ định** | Những version đó không thể undelete. |
| Vault CLI `kv metadata delete` | Không áp dụng kiểu version | Xóa metadata và **toàn bộ lịch sử** của key | Không thể phục hồi bằng KV undelete. |

Với KV v2, sau `deleteById`, key có thể không đọc được theo cách thông thường nhưng metadata vẫn còn. Một `save` mới cho cùng ID có thể tiếp tục version history; không coi key là hoàn toàn mới chỉ vì `findById` trả rỗng.

### Ví dụ CLI tương đương về ý nghĩa

Các lệnh sau **chỉ dùng trong Vault lab** với dữ liệu giả và role riêng:

~~~bash
# Xem version/metadata trước khi xóa:
vault kv metadata get -mount=kv-app partner-credentials/partner-a

# Soft delete phiên bản mới nhất; tương tự mục tiêu thông thường
# của deleteById trên KV v2:
vault kv delete -mount=kv-app partner-credentials/partner-a

# Xem lại metadata: version history có thể vẫn còn:
vault kv metadata get -mount=kv-app partner-credentials/partner-a

# Nguy hiểm: các lệnh dưới đây KHÔNG dành cho CRUD thường lệ.
# Destroy một version riêng và không thể undelete version đó:
# vault kv destroy -mount=kv-app -versions=1 partner-credentials/partner-a

# Xóa toàn bộ metadata/lịch sử key, không thể undelete:
# vault kv metadata delete -mount=kv-app partner-credentials/partner-a
~~~

Không cấp `destroy` hoặc `delete` trên `kv-app/metadata/*` cho workload chỉ cần CRUD thường lệ. Nếu có yêu cầu **xóa vĩnh viễn vì bảo mật/tuân thủ**, hãy thiết kế thao tác quản trị độc lập, được xác nhận bởi người có thẩm quyền, có audit và chính sách backup/snapshot tương ứng. Vault KV version bị destroy không thể phục hồi qua undelete, nhưng hệ thống backup, log hoặc cache bên ngoài có thể vẫn giữ dữ liệu; cần xem xét phạm vi đó riêng.

### Phân biệt deleteById và delete(entity) khi dùng @Version

Tài liệu Spring Vault nêu rõ với KV v2:

- **Delete by ID:** xóa version mới nhất.
- **Delete by entity có version:** nhắm đến version ghi trên entity.

Điều này quan trọng nếu entity được đọc ở version 3 nhưng key đã lên version 4 trước khi xử lý xóa. Không giả định `delete(entity)` luôn giống `deleteById(entity.getId())`. Chọn hành vi phù hợp và kiểm thử chính xác trước khi sử dụng với dữ liệu nhạy cảm.

## 8. Vault ACL cần thiết cho CRUD và LIST

Một repository không tự tăng quyền của `VaultTemplate`. Vault kiểm tra policy của **Vault client token** gắn với ứng dụng. Với KV v2 mount `kv-app`, keyspace `partner-credentials`:

| Repository operation | KV v2 API path chính | Capability thường cần |
|---|---|---|
| `save` tạo key | `kv-app/data/partner-credentials/<id>` | `create` (hoặc `update` theo trạng thái/logic ACL Vault) |
| `save` cập nhật key | `kv-app/data/partner-credentials/<id>` | `update` |
| `findById` | `kv-app/data/partner-credentials/<id>` | `read` |
| `deleteById` | `kv-app/data/partner-credentials/<id>` | `delete` |
| `findAll`, `count`, query theo ID | `kv-app/metadata/partner-credentials` | `list` trên keyspace (và `read` trên các data path nếu lấy entity) |
| Kiểm tra mount/engine version | `sys/internal/ui/mounts/...` | Cần quyền truy cập endpoint tra cứu mount theo tài liệu Spring Vault |

Ví dụ policy thử nghiệm cho CRUD trong phạm vi keyspace (phải kiểm tra với Vault version, mount path và môi trường thực tế):

~~~hcl
# Tạo/đọc/cập nhật/soft-delete document KV v2.
path "kv-app/data/partner-credentials/*" {
  capabilities = ["create", "read", "update", "delete"]
}

# LIST các ID trong keyspace, dùng cho findAll/count và
# một số query derivation theo ID.
path "kv-app/metadata/partner-credentials" {
  capabilities = ["list"]
}

path "kv-app/metadata/partner-credentials/*" {
  capabilities = ["read", "list"]
}

# Spring Vault Repositories tra cứu mount qua internal UI mounts.
# Phạm vi có thể thay đổi theo request thực tế; kiểm tra audit.
path "sys/internal/ui/mounts/kv-app" {
  capabilities = ["read"]
}

path "sys/internal/ui/mounts/kv-app/*" {
  capabilities = ["read"]
}
~~~

Trong HashiCorp Vault, `sys/internal/ui/mounts` là endpoint nội bộ phục vụ tra cứu mount; cách áp dụng ACL/đặc quyền có thể phụ thuộc Vault version và cơ chế endpoint. **Không nới rộng quyền sang `sys/*` chỉ để hết lỗi**. Dùng Vault audit log và tài liệu đang chạy để xác định chính xác path bị từ chối, chỉ cấp quyền tối thiểu.

Đối với ứng dụng **chỉ đọc** KV mà không cần `findAll/count`, có thể tạo repository/service với policy chỉ `read` trên key cụ thể và không cấp `create/update/delete/list`, nhưng phải kiểm tra repository có yêu cầu tra cứu mount trong quá trình initialization. Tách workload read-only khỏi workload được phép chỉnh sửa để giảm rủi ro.

**Lưu ý về `list`:** quyền `list` cho phép lộ tên các ID/path ngay cả khi không được đọc giá trị; metadata key names có thể chứa thông tin nhạy cảm. Đặt ID vô nghĩa về mặt PII và chỉ cấp `list` khi thực sự cần.

## 9. Optimistic locking khi dùng KV v2 và @Version

Nếu có hai tiến trình sửa cùng một ID, quy trình “đọc rồi `save`” có thể gây **lost update**:

~~~mermaid
sequenceDiagram
    participant A as Pod A
    participant B as Pod B
    participant V as Vault KV v2
    A->>V: Đọc key partner-a, version 5
    B->>V: Đọc key partner-a, version 5
    A->>V: Lưu dữ liệu mới với CAS=5
    V-->>A: Thành công, version 6
    B->>V: Lưu dữ liệu cũ đã sửa với CAS=5
    V-->>B: Từ chối vì current version là 6
~~~

KV v2 hỗ trợ **Check-And-Set (CAS)**. Spring Vault repository có thể quản lý CAS khi entity khai báo field `@Version`. Ví dụ một entity riêng để minh họa:

~~~java
package com.example.payments.vault;

import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.Version;
import org.springframework.vault.repository.mapping.Secret;

@Secret(backend = "kv-app", value = "versioned-partner-credentials")
public class VersionedPartnerCredential {

    @Id
    private String id;

    @Version
    private int version;

    private String endpoint;
    private String apiKey;

    public VersionedPartnerCredential() {
    }

    public VersionedPartnerCredential(
            String id, String endpoint, String apiKey) {
        this.id = id;
        this.endpoint = endpoint;
        this.apiKey = apiKey;
    }

    public String getId() {
        return id;
    }

    public void setId(String id) {
        this.id = id;
    }

    public int getVersion() {
        return version;
    }

    public void setVersion(int version) {
        this.version = version;
    }

    public String getEndpoint() {
        return endpoint;
    }

    public void setEndpoint(String endpoint) {
        this.endpoint = endpoint;
    }

    public String getApiKey() {
        return apiKey;
    }

    public void setApiKey(String apiKey) {
        this.apiKey = apiKey;
    }
}
~~~

Interface repository tương ứng:

~~~java
import org.springframework.data.repository.CrudRepository;

public interface VersionedPartnerCredentialRepository
        extends CrudRepository<VersionedPartnerCredential, String> {
}
~~~

Kịch bản kiểm thử đồng thời bằng hai snapshot:

~~~java
import static org.junit.jupiter.api.Assertions.assertThrows;
import org.springframework.dao.OptimisticLockingFailureException;

// Chạy trong bài kiểm thử tích hợp có key "partner-a" tồn tại.
VersionedPartnerCredential first =
        versionedRepository.findById("partner-a").orElseThrow();
VersionedPartnerCredential stale =
        versionedRepository.findById("partner-a").orElseThrow();

first.setApiKey("fake-api-key-from-first");
versionedRepository.save(first);

stale.setApiKey("fake-api-key-from-stale");
assertThrows(OptimisticLockingFailureException.class,
        () -> versionedRepository.save(stale));
~~~

`@Version` phải là thuộc tính kiểu số, ví dụ `int` hoặc `long`. Khi ghi KV v2, Spring Vault đưa version hiện tại vào `cas`; nếu key đã được sửa từ một tiến trình khác, Vault từ chối update và Spring biểu diễn thành `OptimisticLockingFailureException`. **Không** bắt lỗi này rồi retry `save(stale)` vô hạn: phải đọc lại version mới, xác định có được phép hợp nhất dữ liệu hay không, sau đó mới thử ghi có giới hạn.

Từ phía nghiệp vụ, một lỗi CAS không phải lỗi Vault hạ tầng: đó là tín hiệu **xung đột cập nhật hợp lệ**. Trả về lỗi conflict hoặc đưa request qua hàng đợi xử lý theo thứ tự có thể phù hợp hơn retry ngay.

### CAS không thay thế quản lý secret rotation

Nếu bạn vừa lưu `apiKey` B vào Vault, HTTP client ở các Pod khác có thể vẫn dùng A trong bộ nhớ. `@Version` chỉ bảo vệ **ghi chồng dữ liệu KV**, không push secret tới ứng dụng và không thu hồi A ở nhà cung cấp API. Rotation an toàn cần xác nhận consumer thực sự nhận B và bên ngoài đã revoke A theo thời điểm phù hợp.

## 10. Truy vấn theo ID, findAll, count và giới hạn hiệu năng

Vault KV **không có query engine SQL**. Các phương thức Spring Data query derivation của Vault Repository chủ yếu làm việc trên **thuộc tính `@Id`**: liệt kê ID dưới keyspace, lọc ID theo predicate rồi đọc các secret thỏa mãn. Ví dụ:

~~~java
List<PartnerCredential> partners =
        repository.findByIdStartsWith("partner-");

Iterable<PartnerCredential> all = repository.findAll();
long count = repository.count();
~~~

Hãy cẩn thận:

- `findByIdStartsWith("partner-")` không phải phép tìm kiếm server-side tối ưu như index database; repository có thể phải **LIST toàn bộ ID trước khi lọc**.
- Không tạo method `findByApiKey(...)` rồi kỳ vọng Vault query nội dung secret. Spring Vault Repository chỉ hỗ trợ predicate truy vấn dựa trên ID; nếu cần tìm theo thuộc tính khác, hãy giữ một chỉ mục riêng phù hợp nghiệp vụ hoặc chọn datastore khác.
- `findAll` và `count` đòi quyền list metadata/keyspace, có thể tốn nhiều request khi số key lớn. Với KV v2 có các key đã soft-delete và metadata vẫn tồn tại, cần **kiểm tra số liệu thực tế** trước khi dùng `count` như một chỉ số nghiệp vụ chính xác.
- Sorting/paging của repository dựa trên việc lấy ID và áp dụng lọc/phân trang ở phía client; không tương đương SQL `ORDER BY`/`LIMIT` được đẩy xuống datastore. Hạn chế danh sách lớn.
- `deleteAll()` có thể duyệt keyspace và xóa nhiều key; không dùng làm cách dọn dẹp khi phạm vi chưa được kiểm soát. Cần audit, role hạn chế và xác minh môi trường.

Nếu số lượng bản ghi tăng lớn, throughput và latency quan trọng, hoặc cần filter theo nhiều trường nội dung, **Vault KV không nên thay thế database ứng dụng**. Vault ưu tiên lưu trữ/kiểm soát secrets. Một datastore nghiệp vụ riêng có thể lưu metadata hoặc chỉ mục, còn Vault giữ phần secret theo key ID.

## 11. Kiểm thử unit cho service bằng mock repository

Unit test giúp kiểm tra validation và cách service gọi repository mà không cần mở kết nối tới Vault. Dùng Mockito và JUnit Jupiter:

~~~java
package com.example.payments.vault;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.*;

import java.util.Optional;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.ArgumentCaptor;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

@ExtendWith(MockitoExtension.class)
class PartnerCredentialServiceTest {

    @Mock
    PartnerCredentialRepository repository;

    @InjectMocks
    PartnerCredentialService service;

    @Test
    void savesCompleteDocument() {
        when(repository.save(any(PartnerCredential.class)))
                .thenAnswer(invocation -> invocation.getArgument(0));

        PartnerCredential saved = service.put(
                "partner-a",
                "https://partner.example.invalid",
                "fake-api-key-A");

        ArgumentCaptor<PartnerCredential> captor =
                ArgumentCaptor.forClass(PartnerCredential.class);
        verify(repository).save(captor.capture());

        assertEquals("partner-a", saved.getId());
        assertEquals("https://partner.example.invalid",
                captor.getValue().getEndpoint());
        assertEquals("fake-api-key-A",
                captor.getValue().getApiKey());
    }

    @Test
    void returnsEmptyWhenIdNotFound() {
        when(repository.findById("partner-missing"))
                .thenReturn(Optional.empty());

        assertTrue(service.find("partner-missing").isEmpty());
        verify(repository).findById("partner-missing");
    }

    @Test
    void deletesById() {
        service.delete("partner-a");
        verify(repository).deleteById("partner-a");
    }

    @Test
    void rejectsPathLikeIdentifier() {
        assertThrows(IllegalArgumentException.class,
                () -> service.delete("../other-tenant"));
        verifyNoInteractions(repository);
    }
}
~~~

Các giá trị `fake-api-key-A` là **literal giả trong test**, không phải credential thật. Chỉ vì unit test gọi `verify(repository).deleteById(...)` thành công **không có nghĩa Vault đã xóa key**: repository đã bị mock nên không phát sinh HTTP request. Unit test cũng không kiểm tra được keyspace mapping, quyền ACL, CAS hay khả năng xóa mềm của KV v2.

### Test thao tác update qua entity hiện có

Một test riêng nên cho `repository.findById("partner-a")` trả entity A, sau đó gọi `service.rotateApiKey("partner-a", "fake-api-key-B")`. Dùng `ArgumentCaptor` kiểm tra `endpoint` cũ vẫn được giữ và `apiKey` đổi thành B. Điều đó phát hiện lỗi vô tình ghi đè toàn bộ document bằng một entity thiếu field.

## 12. Kiểm thử tích hợp CRUD với Vault KV v2 thật

Một integration test cần Vault server thật (Vault dev/Testcontainers hoặc test cluster), mount KV v2 `kv-app`, auth method riêng cho workload test và Vault policy CRUD trên keyspace thử nghiệm. Không dùng mount hoặc credential production và không cấp root token cho ứng dụng.

### 12.1. Chuẩn bị môi trường kiểm thử

Ví dụ lệnh minh họa dành cho quản trị viên **trong Vault lab**:

~~~bash
# Tạo mount KV v2 nếu chưa có ở môi trường test.
vault secrets enable -path=kv-app -version=2 kv

# Kiểm tra engine type/version, không dùng lệnh ghi bí mật thật.
vault secrets list -detailed

# Policy CRUD phải cho phép kv-app/data/partner-credentials/*
# và list tại kv-app/metadata/partner-credentials.
# Ngoài ra kiểm tra quyền tra cứu sys/internal/ui/mounts/...
~~~

Không chạy lệnh `vault secrets enable` lên production nếu mount đã tồn tại: lệnh này có thể báo lỗi mount trùng và hoàn toàn không phải thao tác được cấp quyền cho workload. Trong CI, hãy tạo môi trường Vault riêng, bootstrap bằng cơ chế admin test, sau đó **ứng dụng test đăng nhập bằng role giới hạn**.

### 12.2. JUnit kiểm tra save → findById → update → deleteById

~~~java
package com.example.payments.vault;

import static org.junit.jupiter.api.Assertions.*;

import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBootTest
class PartnerCredentialRepositoryIT {

    @Autowired
    PartnerCredentialRepository repository;

    @Test
    void createsReadsUpdatesAndSoftDeletesKvV2() {
        // Mỗi lần test dùng ID riêng để không đụng dữ liệu khác.
        String id = "it-" + UUID.randomUUID().toString().substring(0, 8);

        try {
            PartnerCredential created = repository.save(
                    new PartnerCredential(
                            id,
                            "https://partner.example.invalid",
                            "fake-test-key-1"));

            assertEquals(id, created.getId());

            PartnerCredential read =
                    repository.findById(id).orElseThrow();
            assertEquals("fake-test-key-1", read.getApiKey());

            read.setApiKey("fake-test-key-2");
            repository.save(read);

            PartnerCredential reread =
                    repository.findById(id).orElseThrow();
            assertEquals("fake-test-key-2", reread.getApiKey());
        } finally {
            // Chỉ soft-delete current KV v2 version. Không dọn lịch sử.
            repository.deleteById(id);
        }

        assertTrue(repository.findById(id).isEmpty());
    }
}
~~~

**Bằng chứng test cung cấp:** entity được lưu đúng keyspace, converter có thể đọc lại object, `save` cập nhật document, `deleteById` khiến bản ghi không còn được tìm thấy ở trạng thái mới nhất. Test **không** chứng minh metadata/version history đã bị xóa vĩnh viễn. Vì KV v2 còn metadata sau soft delete, bộ test lặp lại nhiều lần có thể tạo ra các key tombstone: thiết kế cleanup metadata riêng trên Vault test bằng credential quản trị được giới hạn, sau khi chắc chắn không xóa nhầm dữ liệu người khác.

Không đưa lệnh xóa metadata vào `finally` của test nếu role test không được phép hoặc chưa có quy trình cleanup cô lập. Dữ liệu test phải dùng namespace/mount/ID riêng; việc cần dọn môi trường bằng quyền cao hơn là một thao tác quản trị riêng.

### 12.3. Các ca kiểm thử bắt buộc khác

| Ca thử | Cách tạo tình huống | Kết quả mong đợi |
|---|---|---|
| Key không tồn tại | `findById("it-missing")` ở keyspace test | `Optional.empty()`, không tạo entity giả |
| ID không hợp lệ | Gọi service với `../other-tenant` | Validation chặn trước khi request Vault |
| Create/update đúng policy | Role có quyền trên `kv-app/data/partner-credentials/*` | Save và read thành công |
| Thiếu quyền `read` | Token chỉ có capability ghi | `findById` thất bại do ACL, không bị chuyển thành Optional rỗng |
| Thiếu quyền `list` | Có read trên key cụ thể, không list metadata | `findAll`/`count` hoặc query derivation có thể lỗi do LIST |
| Mount discovery bị từ chối | Giới hạn `sys/internal/ui/mounts/...` trong test | Xác nhận lỗi được ghi nhận ở bước tra cứu mount |
| KV v1 so với KV v2 | Chạy test trên hai mount độc lập | Đúng HTTP path và semantics xóa của từng engine |
| Update đè phiên bản | Hai snapshot cùng version dùng `@Version` | Save thứ hai ném `OptimisticLockingFailureException` |
| Xóa version cụ thể | Entity versioned và update song song | `delete(entity)` và `deleteById` có khác biệt theo version |
| Token hết hạn/re-login | Auth role TTL ngắn và session manager | Repository tiếp tục đọc bằng phiên token mới khi auth còn hoạt động |
| Vault timeout/5xx | Chặn kết nối trong Vault lab | Tầng service báo lỗi và retry theo chính sách, không lộ secret |
| LIST nhiều key | Tạo số lượng key test có kiểm soát | Đánh giá độ trễ, số request và giới hạn quy mô |

Với các ca có nhiều request/transaction hoặc expiry, cần đồng bộ bằng timeout/bộ đếm sự kiện; không dùng vòng `while(true)` hoặc `Thread.sleep` không giới hạn. Một bài test mock `CrudRepository` không thay thế cho những ca cần xác nhận hành vi thực tế của Vault KV engine.

## 13. Xử lý lỗi thường gặp khi sử dụng CrudRepository

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Không inject được `PartnerCredentialRepository` | Thiếu `@EnableVaultRepositories`, scan sai package, thiếu `spring-data-keyvalue` | Kiểm tra annotation, package và dependency tree |
| Repository bean khởi tạo nhưng không kết nối Vault | Không có `VaultTemplate` đúng tên, endpoint/TLS sai, auth token hết hạn | Kiểm tra bean, `vaultTemplateRef`, Vault URI và SessionManager |
| `403` dù KV data path đã được cấp quyền | Mount discovery tại `sys/internal/ui/mounts/...` hoặc metadata/list path thiếu quyền | Xem Vault audit đã được cấp quyền, cấp đúng path tối thiểu |
| `save` báo permission denied | Thiếu `create` hoặc `update` tại `kv-app/data/...` | Kiểm tra policy của role cùng trạng thái key hiện hành |
| `findById` trả rỗng sau delete | KV v2 latest version đã bị soft-delete | Đây có thể là hành vi đúng; kiểm tra metadata bằng quyền quản trị khi cần |
| `findAll` lỗi hoặc chạy chậm | Thiếu `list` hoặc keyspace có nhiều ID/secret | Kiểm tra ACL metadata; không dùng Vault như kho dữ liệu truy vấn lớn |
| `save` vô tình làm mất một field | Viết lại toàn bộ document từ object thiếu field | Dùng read-modify-save cùng mapping đầy đủ và CAS nếu có concurrent update |
| `OptimisticLockingFailureException` | Entity `@Version` lỗi thời so với KV version hiện tại | Đọc lại entity, giải quyết xung đột; retry có giới hạn nếu thích hợp |
| `delete(entity)` không xóa latest | Entity versioned nhắm tới một version khác | Kiểm tra version của entity và cách Spring Vault thực thi delete |
| Key “đã xóa” nhưng metadata còn | KV v2 soft delete khác destroy/delete metadata | Sử dụng quy trình admin riêng nếu thực sự cần xóa lịch sử |
| `findByApiKey(...)` không hoạt động | Vault query derivation không hỗ trợ predicate tùy ý trên secret field | Dùng query theo ID hoặc index riêng; không quét toàn Vault |
| Lỗi deserialize hoặc type mismatch | POJO thiếu constructor/setter, custom type chưa có converter, class schema đổi | Kiểm tra mapping, `VaultCustomConversions` và chiến lược migration |
| Token của ứng dụng không còn hiệu lực | Lỗi ở workload authentication/session lifecycle, không phải ID mapping | Kiểm tra Vault login/renew, role, policy, mạng và token expiry |

### Ghi nhận lỗi có phân loại

Ứng dụng nên phân biệt **authentication** (không có Vault token), **authorization** (token hợp lệ nhưng thiếu quyền), **missing secret**, **optimistic locking conflict**, **serialization** và **network**. Một lỗi `403` khi gọi `kv-app/data/...` không nên dẫn đến vòng đăng nhập lại vô hạn: vấn đề thường là Vault policy của token.

Để quan sát, đo:

- Số lần `save/find/delete` thành công hoặc thất bại theo **loại thao tác** và **loại lỗi**, không ghi raw secret value.
- Độ trễ của repository operations, số request Vault, tỷ lệ timeout và trạng thái mount/ACL.
- Số xung đột CAS và tần suất cập nhật cùng ID; tránh đưa ID chứa dữ liệu nhạy cảm vào metric labels.
- Số lượng key/list operations của keyspace; cảnh báo khi `findAll/count` tăng tải bất thường.
- Sự kiện token login/renew/re-login qua session manager, nhưng không đưa Vault token, JWT, SecretID hoặc `apiKey` vào log.

## 14. Các lưu ý bảo mật và thiết kế

1. **Phân quyền tối thiểu:** app chỉ đọc không cần `create/update/delete`; app CRUD không cần `destroy` hoặc xóa toàn bộ metadata.
2. **Vault không phải database nghiệp vụ:** repository thích hợp cho lượng secrets được quản lý nhỏ, không cho truy vấn tùy ý hàng triệu records.
3. **Kiểm soát đường dẫn:** giới hạn `id`, `keyspace` và mount cố định theo domain; không để người dùng tùy ý điều khiển backend hoặc namespace.
4. **Không log đối tượng secret:** tránh `toString`, Lombok `@Data` sinh `toString` nhạy cảm, JSON logging tự động, debug HTTP payload và lỗi chứa credential.
5. **Ghi nguyên document:** kiểm tra dữ liệu nào không được map; `save` có thể ghi đè và làm mất field không được converter hiểu.
6. **KV v2 có lịch sử:** soft-delete không bảo đảm bí mật cũ biến mất; thiết kế revoke token/API key cũ ở hệ thống sử dụng nó.
7. **Tách lifecycle:** `SessionManager` quản lý Vault token; secrets trong repository là dữ liệu KV. Khi KV version đổi, consumer chưa chắc được refresh.
8. **Kiểm soát concurrency:** dùng `@Version`/CAS cho record có nhiều writer; không giải quyết race bằng `existsById` rồi `save`.
9. **Không dùng root token trong production:** các thao tác admin như mount configuration, delete metadata, destroy versions phải qua workflow riêng có audit.
10. **Chuẩn bị migration:** nếu đổi tên Java package/class, converter có thể gặp type hint `_class` cũ trong JSON; thiết kế converter/alias/migration trước khi rollout.

## 15. Checklist nghiệm thu

- [ ] Entity có `@Secret(backend=..., value=...)` trỏ đúng KV mount/keyspace và `@Id String` hợp lệ.
- [ ] Repository `extends CrudRepository<Entity, String>`, được quét bởi `@EnableVaultRepositories` và dùng đúng bean `VaultTemplate`.
- [ ] Dependency Spring Data KeyValue/Commons tương thích Spring Vault và Spring Framework đang sử dụng.
- [ ] `save` tạo/cập nhật, `findById` trả `Optional`, `deleteById` không bị nhầm với permanent deletion.
- [ ] Đã phân biệt HTTP path của KV v1 với KV v2 `data/metadata`.
- [ ] ACL đúng cho `create/read/update/delete/list`; có kiểm tra quyền tra cứu mount.
- [ ] Có test trường hợp thiếu key, thiếu quyền, concurrency/CAS, Vault timeout và JSON mapping.
- [ ] Việc xóa vĩnh viễn version/history là một quy trình admin riêng; không cấp quyền destroy cho repository thường lệ.
- [ ] Key ID được validate và không mang thông tin nhận dạng cá nhân nhạy cảm không cần thiết.
- [ ] Không log token, SecretID, mật khẩu hoặc API key; chỉ log trạng thái theo loại thao tác và nguyên nhân đã phân loại.
- [ ] Có Vault test server/mount/role độc lập và kế hoạch dọn metadata/tombstone sau test.

## 16. Tổng kết

Trong **SPRING_VAULT**, `CrudRepository` giúp chuyển các thao tác **lưu, đọc và xóa** KV secrets thành API Java quen thuộc của Spring Data. Kết hợp `@Secret`, `@Id`, `@EnableVaultRepositories` và `VaultTemplate`, ứng dụng có thể lưu POJO theo đường dẫn `keyspace/id` và giảm code chuyển đổi JSON thủ công.

Điều quan trọng là không mang những giả định từ SQL/JPA sang Vault: **`save` ghi toàn bộ document**, truy vấn chủ yếu dựa trên ID, `findAll/count` có thể cần LIST và tốn nhiều request; **`delete` trên KV v2 chỉ xóa mềm, không destroy lịch sử**. Nếu nhiều writer, dùng `@Version`/CAS; nếu muốn xóa vĩnh viễn, dùng workflow quản trị riêng. Vault policy theo quyền tối thiểu, quản lý vòng đời token và kiểm thử tích hợp trên môi trường cô lập là điều kiện để repository hoạt động an toàn.

## Tài liệu tham khảo

- Spring Vault Reference — [Vault Repositories](https://docs.spring.io/spring-vault/reference/vault/vault-repositories.html), hướng dẫn CRUD, mapping, query theo ID, versioning và khác biệt delete KV v2.
- Spring Vault API — [`@EnableVaultRepositories`](https://docs.spring.io/spring-vault/reference/api/java/org/springframework/vault/repository/configuration/EnableVaultRepositories.html).
- Spring Vault API — [`@Secret`](https://docs.spring.io/spring-vault/reference/api/java/org/springframework/vault/repository/mapping/Secret.html), khai báo mount và keyspace của entity.
- Spring Vault API — [`VaultRepositoryFactoryBean`](https://docs.spring.io/spring-vault/reference/api/java/org/springframework/vault/repository/support/VaultRepositoryFactoryBean.html).
- Spring Vault Reference — [Vault Secrets Engines / Key-Value](https://docs.spring.io/spring-vault/reference/vault/vault-secret-engines.html).
- Spring Data Commons — [Repository Interfaces và CrudRepository](https://docs.spring.io/spring-data/commons/reference/repositories/core-concepts.html).
- HashiCorp Vault — [KV v2 HTTP API](https://developer.hashicorp.com/vault/api-docs/secret/kv/kv-v2), `delete`, `destroy` và `metadata/delete`.
- HashiCorp Vault — [Policy Concepts](https://developer.hashicorp.com/vault/docs/concepts/policies), các capabilities trên data/metadata paths.



