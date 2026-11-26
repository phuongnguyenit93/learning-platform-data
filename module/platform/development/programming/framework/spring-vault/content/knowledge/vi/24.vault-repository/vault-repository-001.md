# Khi nào dùng repository thay cho VaultOperations trong Spring Vault

**Spring Vault** cung cấp hai cách làm việc phổ biến với bí mật trong **HashiCorp Vault**: thao tác trực tiếp bằng giao diện `VaultOperations` (thường được triển khai bởi `VaultTemplate`), hoặc sử dụng **Vault Repository** dựa trên mô hình Spring Data. Hai cách này không cạnh tranh để thay thế toàn bộ chức năng của nhau: repository là lớp trừu tượng **chuyên cho lưu, đọc, liệt kê và ánh xạ đối tượng trên KV secrets engine**, còn `VaultOperations` là điểm vào bao quát hơn cho KV, Transit encryption, PKI, token, sys và các thao tác theo đường API.

Bài học thuộc chương **Vault Repository** và trả lời câu hỏi thực hành: **khi nào nên dùng repository thay cho `VaultOperations`, và khi nào phải giữ `VaultOperations`?** Bối cảnh là một ứng dụng Java xác thực theo workload, được Vault cấp policy tối thiểu, đọc KV secrets, quản lý token/lease, dùng Transit hoặc PKI và cần xử lý lỗi, giám sát, kiểm thử tích hợp.

> Nguyên tắc ra quyết định: nếu nghiệp vụ thật sự thao tác trên các **tài liệu KV có ID ổn định**, CRUD và object mapping của repository có thể tăng tính rõ ràng. Nếu cần gọi **một operation cụ thể của Vault**, xử lý TTL/lease, mã hóa Transit, phát hành chứng chỉ hoặc quản trị version/metadata chi tiết, nên dùng API phù hợp của `VaultOperations`.

## 1. Hai abstraction giải quyết hai mức nhu cầu

### VaultOperations: điều khiển thao tác cụ thể

`VaultOperations` là giao diện chính của Spring Vault cho các request có hoặc không có phiên xác thực, được `VaultTemplate` triển khai. Ví dụ:

~~~java
import org.springframework.vault.core.VaultOperations;
import org.springframework.vault.core.VaultKeyValueOperationsSupport.KeyValueBackend;

class DirectKvAccess {
    private final VaultOperations vault;

    DirectKvAccess(VaultOperations vault) {
        this.vault = vault;
    }

    String mode() {
        var response = vault
                .opsForKeyValue("secret", KeyValueBackend.KV_2)
                .get("orders/config");

        if (response == null || response.getData() == null) {
            throw new IllegalStateException("Missing Vault secret");
        }
        Object value = response.getData().get("app.mode");
        if (!(value instanceof String result)) {
            throw new IllegalStateException("Invalid app.mode");
        }
        return result;
    }
}
~~~

Ứng dụng **tự chọn mount, KV version, path, cách parse response và điều kiện lỗi**. Điều này phù hợp khi cần thao tác rõ ràng trên một secret cố định hoặc phải điều khiển chi tiết phiên bản và metadata của KV v2.

### Vault Repository: khai báo đối tượng và CRUD

Repository dùng **Spring Data `CrudRepository`** và annotation `@Secret` để tự xác định keyspace, đọc/ghi Java object và thực hiện thao tác CRUD:

~~~java
import org.springframework.data.repository.CrudRepository;

interface CredentialRepository
        extends CrudRepository<CredentialDocument, String> {
}
~~~

Lớp triển khai được Spring tạo khi bật repository support. Thay vì tự parse `VaultResponse`, code nghiệp vụ gọi:

~~~java
CredentialDocument document = repository.findById("orders-read")
        .orElseThrow(() -> new IllegalStateException("Secret not found"));
~~~

Điểm khác biệt là **repository có mô hình entity và identifier**, không phải một SQL database repository; backend vẫn là **Vault Key/Value secrets engine**, không có join, query planner hay transaction như cơ sở dữ liệu quan hệ.

## 2. Sơ đồ luồng truy cập và nơi khác biệt xuất hiện

~~~mermaid
flowchart TD
    A["Java business service"] --> B{"Nhu cầu?"}
    B -- "CRUD tài liệu KV theo ID" --> C["Spring Data CrudRepository"]
    B -- "Operation Vault/engine đặc thù" --> D["VaultOperations / VaultTemplate"]
    C --> E["VaultConverter + mapping @Secret/@Id"]
    E --> F["Vault key/value support"]
    D --> G["KV v1/v2, Transit, PKI, token, sys..."]
    F --> H["Vault HTTP client + SessionManager"]
    G --> H
    I["Workload identity / ClientAuthentication"] --> H
    H --> J["HashiCorp Vault: auth + ACL + secret engines"]
~~~

Dù gọi theo hướng nào, **Vault vẫn kiểm tra token, policy, mount và path**. Repository không bỏ qua xác thực, không tự chuyển quyền `403` thành thành công và không thay thế cấu hình TLS, CA hay vòng đời token.

## 3. Bảng quyết định nhanh

| Nhu cầu thực tế | Repository | VaultOperations | Lựa chọn đề xuất |
| --- | --- | --- | --- |
| Đọc một cấu hình KV cố định theo path | Có thể, nhưng cần entity/ID. | Ngắn gọn qua `opsForKeyValue(...).get(...)`. | **VaultOperations** nếu không có domain CRUD. |
| Lưu nhiều đối tượng KV cùng schema, key theo ID | Hỗ trợ `save/findById/deleteById`, mapping tự động. | Phải tự dựng path và mapping. | **Repository** khi aggregate có ý nghĩa. |
| Tìm các ID bắt đầu bằng prefix | Có query derivation theo ID. | Có thể `list` rồi tự lọc. | **Repository** với keyspace nhỏ, kiểm soát quyền LIST. |
| Tìm document theo password/status/tenant field | Không có query engine tổng quát cho field. | Không có truy vấn server-side như SQL. | **Không coi Vault là database tìm kiếm.** |
| Đọc/ghi KV v2 có version, optimistic locking | `@Version` và `RevisionRepository` hỗ trợ trường hợp phổ biến. | `opsForVersionedKeyValue(...)` cho thao tác rõ version/CAS. | Tùy mức kiểm soát. |
| Soft delete, undelete, destroy KV v2 version | `delete` ở repository không destroy. | Có các API versioned KV cụ thể. | **VaultOperations** cho lifecycle phiên bản. |
| Lấy dynamic database credential và theo dõi lease | Không phải chức năng repository KV. | API Vault/`SecretLeaseContainer`. | **VaultOperations + lease management**. |
| Encrypt/decrypt/rotate key Transit | Không. | `opsForTransit(...)`. | **VaultOperations**. |
| Issue/sign/revoke PKI certificate | Không. | `opsForPki(...)` hoặc API tương ứng. | **VaultOperations**. |
| Token lookup/renew, policy, sys hoặc auth | Không. | `opsForToken`, `opsForSys`, session/auth. | **VaultOperations** và thành phần chuyên trách. |
| Reactive pipeline WebFlux | Repository ở đây theo kiểu Spring Data imperative. | Dùng `ReactiveVaultOperations`. | **Reactive API** khi cần end-to-end reactive. |

**Tóm lại:** lựa chọn dựa trên **công việc cần làm**, không dựa trên việc tên “repository” nghe giống một kiến trúc hiện đại hơn.

## 4. Cài đặt tối thiểu một Vault Repository

### 4.1. Dependency

Vault repositories dùng Spring Data Commons và Spring Data KeyValue, bên cạnh Spring Vault Core. Với Maven sử dụng **BOM tương thích**:

~~~xml
<dependencies>
  <dependency>
    <groupId>org.springframework.vault</groupId>
    <artifactId>spring-vault-core</artifactId>
  </dependency>
  <dependency>
    <groupId>org.springframework.data</groupId>
    <artifactId>spring-data-keyvalue</artifactId>
  </dependency>
</dependencies>
~~~

Tài liệu Spring Vault cũng liệt kê dependency `spring-data-commons`; `spring-data-keyvalue` thường kéo Commons theo dependency transitive, nhưng hãy kiểm tra dependency graph của dự án. Chọn phiên bản Spring Vault, Spring Data và Spring Framework theo BOM tương thích, không ghép tùy ý các major version.

### 4.2. Entity với @Secret và @Id

Ví dụ một secret thuộc loại **tài liệu thông tin xác thực tĩnh, riêng cho môi trường thử nghiệm**; không dùng dữ liệu thật:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.Version;
import org.springframework.vault.repository.mapping.Secret;

@Secret(value = "orders-credentials", backend = "secret")
public class CredentialDocument {

    @Id
    private String id;

    @Version
    private Long version;

    private String username;
    private String password;

    public CredentialDocument() {}

    public CredentialDocument(String id, String username, String password) {
        this.id = id;
        this.username = username;
        this.password = password;
    }

    public String getId() { return id; }
    public void setId(String id) { this.id = id; }

    public Long getVersion() { return version; }
    public void setVersion(Long version) { this.version = version; }

    public String getUsername() { return username; }
    public void setUsername(String username) { this.username = username; }

    public String getPassword() { return password; }
    public void setPassword(String password) { this.password = password; }
}
~~~

- `@Secret(value="orders-credentials")` xác định **keyspace**. `backend="secret"` chọn KV mount; trong Spring Vault 4.1 có thêm thuộc tính alias `engine`. Đối với mã cần tương thích phiên bản cũ, `backend` thường dễ dùng hơn.
- `@Id` phải ánh xạ sang **`String`**; `id="orders-read"` sẽ dùng key logic dạng `orders-credentials/orders-read` trên mount `secret/`.
- `@Version` là trường số cho KV v2 optimistic locking; không bắt buộc nếu ứng dụng không cần concurrency control, và không có ý nghĩa versioning tương đương trên KV v1.
- Có constructor mặc định và accessors giúp mapper tạo/điền đối tượng. Không sinh `toString()` chứa `password`.
- Secret được serialize thành một JSON document tại một đường KV; repository không biến từng field thành một secret riêng lẻ.

**Đừng dùng Vault repository để sao chép dynamic database password sang KV** nếu chúng đã có lease do Database engine quản lý. Sao chép làm mất liên hệ với vòng đời account/lease và tạo thêm bản secret phải thu hồi.

### 4.3. Interface repository

~~~java
import java.util.List;
import org.springframework.data.repository.CrudRepository;

public interface CredentialRepository
        extends CrudRepository<CredentialDocument, String> {

    List<CredentialDocument> findByIdStartsWith(String prefix);
}
~~~

Kế thừa `CrudRepository` cung cấp `save`, `findById`, `findAll`, `existsById`, `count` và `deleteById`; phương thức `findByIdStartsWith` có thể được suy ra theo quy tắc Spring Data dành cho **ID**.

### 4.4. Bật repository trong Spring context

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.vault.repository.configuration.EnableVaultRepositories;

@Configuration(proxyBeanMethods = false)
@EnableVaultRepositories(basePackageClasses = CredentialRepository.class)
class VaultRepositoryConfiguration {
    // Ứng dụng phải cung cấp bean VaultTemplate/VaultOperations có xác thực.
    // Thường do cấu hình Spring Vault của hệ thống tạo sẵn.
}
~~~

`@EnableVaultRepositories` quét các interface repository trong package tương ứng. Nếu không cấu hình package, nó dùng package của lớp được annotate. Annotation cũng cho phép tùy chỉnh `vaultTemplateRef` hoặc `keyValueTemplateRef` khi có nhiều template.

**Lưu ý bootstrap:** ví dụ giả định bean `vaultTemplate` đã có, kết nối HTTPS với CA đúng, có `SessionManager` và `ClientAuthentication` thích hợp. Repository support không tự biến root token thành workload identity. Nếu ứng dụng chỉ dùng `spring-vault-core`, cần cấu hình các bean đó theo thư viện và runtime đang dùng.

## 5. Sử dụng CRUD từ service Java

~~~java
import org.springframework.stereotype.Service;

@Service
public class OrdersCredentialService {

    private final CredentialRepository repository;

    public OrdersCredentialService(CredentialRepository repository) {
        this.repository = repository;
    }

    public void writeExampleForTest() {
        repository.save(
                new CredentialDocument("orders-read", "orders_demo", "demo-only"));
    }

    public CredentialDocument readRequired(String id) {
        return repository.findById(id)
                .orElseThrow(() -> new IllegalArgumentException(
                        "Credential document not found"));
    }

    public void removeForTest(String id) {
        repository.deleteById(id);
    }
}
~~~

Ví dụ ghi **giá trị giả** vào Vault test. Với ứng dụng thật, không để password được hardcode trong source/CI, không trả `CredentialDocument` nguyên vẹn qua controller và giới hạn người có thể gọi các phương thức ghi/xóa.

Repository tự tạo proxy và mapping, nên code dịch vụ tương tự Spring Data repository quen thuộc. Nhưng các thao tác trên Vault **không nằm trong một transaction SQL**, và không có bảo đảm atomic cho một chuỗi `save(A)` → `save(B)` → `delete(C)`. Nếu cần update có điều kiện, dùng CAS hoặc cơ chế kiểm soát thay đổi phù hợp với KV v2.

### Khác biệt với direct KV access

Đọc trực tiếp cùng một secret bằng `VaultOperations`:

~~~java
import org.springframework.vault.core.VaultOperations;
import org.springframework.vault.core.VaultKeyValueOperationsSupport.KeyValueBackend;

class DirectCredentialReader {
    private final VaultOperations vault;

    DirectCredentialReader(VaultOperations vault) {
        this.vault = vault;
    }

    String readUsername() {
        var response = vault
                .opsForKeyValue("secret", KeyValueBackend.KV_2)
                .get("orders-credentials/orders-read");

        if (response == null || response.getData() == null) {
            throw new IllegalStateException("Missing credential document");
        }
        return String.valueOf(response.getData().get("username"));
    }
}
~~~

API trực tiếp có thể ngắn hơn khi chỉ đọc **một field** từ một path cố định, nhưng không tự cung cấp aggregate mapping, ID query derivation và Spring Data repository lifecycle. Ngược lại, khi cùng schema được CRUD lặp lại trên hàng trăm document, repository có thể giảm boilerplate đáng kể.

## 6. Object mapping: tiện lợi nhưng có rủi ro

Repository dùng `VaultConverter` để chuyển Java objects thành `SecretDocument` và JSON. Loại dữ liệu phổ biến gồm String, number, list, map và nested objects. Mapper có thể đưa trường loại `_class` vào JSON để phục vụ type metadata.

Ví dụ hình dạng JSON tại path logic `orders-credentials/orders-read`:

~~~json
{
  "_class": "com.example.vault.CredentialDocument",
  "username": "orders_demo",
  "password": "demo-only"
}
~~~

`_class` minh họa cách converter có thể lưu thông tin type. Schema thực tế còn phụ thuộc loại entity, cấu hình converter và version Spring Data. `@Id` được dùng để xác định key trong Vault, không phải bắt buộc nằm trong body JSON.

### Trường hợp mapper giúp ích

- Nhiều tài liệu có cấu trúc ổn định, có nested objects hoặc list.
- Dịch vụ có nhiều thao tác create/read/update/delete cùng một loại.
- Đội phát triển muốn dùng converter tùy biến cho `LocalDate` hoặc value object.
- Cần cô lập API lưu trữ phía sau một repository interface để test/mock.

### Trường hợp mapper gây hại nếu không kiểm soát

- **Lưu cả object:** một lần `save` có thể ghi đè toàn bộ document. Field tồn tại trước đó nhưng không được mapper giữ lại sẽ bị mất.
- **Schema drift:** service A ghi một tập field, service B dùng model cũ và `save` làm mất field mới.
- **Metadata:** `_class` có thể lộ tên class/package trong dữ liệu Vault; cân nhắc chính sách sử dụng, tương thích migration và converter.
- **Bản sao bí mật:** password sau khi được map sang `String` có thể tồn tại trong heap, exception, cache và log.
- **ID không được validate:** để người dùng cung cấp ID tùy ý có thể dẫn đến path ngoài dự kiến hoặc tấn công logic ở tầng truy cập.

**Biện pháp:** định nghĩa DTO/domain chỉ gồm các field thật sự sở hữu; kiểm soát sửa đổi bằng version/CAS; giữ schema nhất quán; validate ID bằng quy tắc rõ, không nhận raw Vault path hoặc URI từ HTTP request.

## 7. KV v1, KV v2 và Vault path thực tế

Vault Repository hỗ trợ cả KV v1 và KV v2. Từ Spring Vault 2.4, repository có khả năng dùng KV v2 và phát hiện version của mount tại runtime.

Giả sử `@Secret(value="orders-credentials", backend="secret")` và `id="orders-read"`.

| Khái niệm | KV v1 | KV v2 |
| --- | --- | --- |
| Mount | `secret/` | `secret/` |
| Logical document key | `orders-credentials/orders-read` | `orders-credentials/orders-read` |
| HTTP read/write API | `secret/orders-credentials/orders-read` | `secret/data/orders-credentials/orders-read` |
| HTTP list API | Cơ chế LIST trên keyspace mount v1 | `secret/metadata/orders-credentials` |
| Versioning/CAS | Không có version theo KV v2 | Có version, metadata, CAS, soft delete và destroy |
| Repository save/get | CRUD qua mapper | CRUD qua mapper, có thể dùng `@Version` |
| Repository delete | Xóa theo semantics KV v1 | Không phải destroy vĩnh viễn mọi version |

Khi viết policy, **đường API** quan trọng, không phải chỉ key logic của entity. Policy minh họa cho repository CRUD trên **KV v2** trong môi trường test:

~~~hcl
path "secret/data/orders-credentials/*" {
  capabilities = ["create", "read", "update", "delete"]
}

path "secret/metadata/orders-credentials" {
  capabilities = ["list"]
}

path "secret/metadata/orders-credentials/*" {
  capabilities = ["list"]
}
~~~

Các khả năng trên là **quyền tối thiểu tương đối cho một bài test CRUD + list** theo keyspace. Nếu service chỉ đọc bằng ID, có thể loại `create/update/delete/list` và cấp `read` cho path chính xác. `list` của Vault kiểm tra trên metadata/keyspace; việc list có thể làm lộ tên key dù không đọc giá trị. Với keyspace chứa bí mật phân loại cao, không cấp list nếu không cần.

### Mount discovery và quyền

Repository có bước phát hiện mount/version qua endpoint dạng `sys/internal/ui/mounts/...`. Nếu Vault báo 403 ở bước này, request repository có thể thất bại trước khi đến đường `secret/data/...`. Kiểm tra audit và policy của auth token trên **endpoint thực sự được gọi**, theo phiên bản Vault và quyền access path. Không tự cấp `sys/*` rộng rãi để bỏ qua lỗi, và không mặc định mọi role đã có đủ quyền để khám phá mount.

Với API direct, có thể chỉ rõ `KeyValueBackend.KV_2` trong `opsForKeyValue`, giúp giảm tính mơ hồ về version ở phía client trong môi trường đã biết mount rõ. Dù vậy, TLS, token/policy và đường API vẫn phải đúng.

## 8. Query derivation: chỉ theo ID, không theo thuộc tính tùy ý

Spring Data repository thông thường khiến nhiều người quen viết:

~~~java
// Không phải truy vấn được Vault hỗ trợ như SQL:
List<CredentialDocument> findByUsername(String username);
~~~

**Không nên kỳ vọng repository sẽ tìm theo field `username`.** Spring Vault không có query engine tìm field phía server như MongoDB/SQL. Query derivation được hỗ trợ cho predicate giới hạn trên **`@Id`**, ví dụ:

~~~java
import java.util.List;
import org.springframework.data.repository.CrudRepository;

interface CredentialRepository extends CrudRepository<CredentialDocument, String> {
    List<CredentialDocument> findByIdStartsWith(String prefix);
    List<CredentialDocument> findByIdIn(List<String> ids);
}
~~~

Spring Vault thực hiện query theo khả năng LIST/path của Vault rồi lọc tên ID ở phía client, có thể đọc document tương ứng sau khi lọc. Điều này **không tương đương index** hoặc thao tác tìm kiếm server-side.

### Cẩn thận với count, findAll và paging

- `findById(id)` dùng định danh cụ thể và tránh quét toàn keyspace.
- `count()` và `findAll()` có thể phải LIST keyspace và, tùy operation, lấy các secret liên quan.
- Query theo ID prefix cần LIST; dùng với một keyspace rộng có thể phát sinh số request nhiều hơn mong đợi.
- Sort/page là hoạt động phía client trên các ID/document được liệt kê/đọc theo thiết kế library; **không phải** Vault hỗ trợ `ORDER BY` hoặc `LIMIT` có index.
- `PagingAndSortingRepository` có thể giảm mã Java, **không tạo truy vấn tiết kiệm băng thông như database**.

Nếu cần tìm theo tenant, trạng thái xử lý, thời gian phát hành hoặc nhiều điều kiện phức tạp, thường nên đặt metadata/tìm kiếm trong một hệ thống database hoặc index thích hợp và lưu đúng secret nhạy cảm trong Vault. Khi làm như vậy, phải bảo vệ ánh xạ ID và tránh metadata tiết lộ đường dẫn bí mật ngoài quyền.

## 9. Optimistic locking và revisions khi dùng KV v2

KV v2 cung cấp version và cơ chế **Compare-and-Set (CAS)**. Spring Vault repository hỗ trợ `@Version` trên entity để gửi version mong đợi khi ghi; nếu tài liệu đã đổi bởi thao tác cạnh tranh, `save` có thể ném `OptimisticLockingFailureException`.

~~~java
// Trong hai execution contexts khác nhau, cùng đọc một version:
CredentialDocument a = repository.findById("orders-read").orElseThrow();
CredentialDocument b = repository.findById("orders-read").orElseThrow();

a.setUsername("orders-reader-v2");
repository.save(a);

// b vẫn giữ version cũ; ghi có thể thất bại vì CAS:
b.setUsername("orders-reader-v3");
repository.save(b); // dự kiến OptimisticLockingFailureException với KV v2/CAS
~~~

Đoạn code là **kịch bản minh họa**, không phải lời khuyên ghi credential production để test. Điều kiện test phải bảo đảm cả hai đối tượng là hai snapshot độc lập và version field được mapper cập nhật theo contract. `@Version` cần kiểu số như `int` hoặc `long` (wrapper số tương ứng khi được hỗ trợ) theo version Spring Vault/Spring Data. Khi bắt conflict, đọc lại giá trị mới và đối chiếu nghiệp vụ trước khi retry; không ghi đè vô điều kiện.

### Đọc revision lịch sử

Nếu cần đọc nhiều version của **một secret KV v2**, có thể mở rộng repository theo Spring Data revision abstraction:

~~~java
import org.springframework.data.repository.CrudRepository;
import org.springframework.data.repository.history.RevisionRepository;

interface CredentialRevisionRepository
        extends CrudRepository<CredentialDocument, String>,
                RevisionRepository<CredentialDocument, String, Integer> {
}
~~~

Spring Vault sử dụng **String ID** và **Integer revision number** cho KV v2. `RevisionRepository` giúp truy xuất revisions theo ID. Nhưng hệ thống bảo mật vẫn phải kiểm tra policy đối với các API versioned read và việc giữ lịch sử secret:

- Một secret đã bị rotate ở hệ thống đích không đồng nghĩa lịch sử Vault đã bị xóa.
- API **DELETE** của KV v2 chỉ đánh dấu version bị xóa; không đồng nghĩa hủy vĩnh viễn dữ liệu.
- Nếu yêu cầu destroy/undelete, cần dùng API versioned KV riêng, có policy và quy trình phê duyệt thích hợp.
- Việc bật revision history có thể tăng diện tích lưu trữ bí mật cũ; quản trị retention và max versions theo yêu cầu bảo mật.

### Khi cần API versioned rõ ràng hơn

~~~java
import java.util.Map;
import org.springframework.vault.core.VaultOperations;
import org.springframework.vault.core.VaultVersionedKeyValueOperations;
import org.springframework.vault.support.Versioned;

VaultVersionedKeyValueOperations kv2 =
        vaultOperations.opsForVersionedKeyValue("secret");

Versioned<Map<String, Object>> snapshot =
        kv2.get("orders-credentials/orders-read");
~~~

`vaultOperations` ở đây là biến `VaultOperations` đã inject. Với API `VaultVersionedKeyValueOperations`, bạn có thể đọc version cụ thể, thực hiện CAS bằng `Versioned`, `delete` version, `undelete` và `destroy` theo quyền. Nếu muốn thao tác này, API direct thể hiện ý định và đường kiểm soát rõ hơn repository CRUD.

## 10. Xóa trong repository: đừng nhầm delete với destroy

Khi gọi:

~~~java
repository.deleteById("orders-read");
~~~

Trên KV v2, thao tác repository tương ứng **DELETE**, không hủy vĩnh viễn tất cả version như `destroy`. Dữ liệu hoặc metadata có thể vẫn tồn tại theo cơ chế version của Vault. Do đó, ứng dụng phải phân biệt:

| Operation | Ý nghĩa |
| --- | --- |
| Repository `deleteById(...)` | Xóa theo semantics Vault KV; KV v2 không phải destroy. |
| KV v2 `delete(...)` | Đánh dấu version không còn hiển thị ở đường đọc thông thường. |
| KV v2 `undelete(...)` | Phục hồi version đã soft-delete nếu còn dữ liệu. |
| KV v2 `destroy(...)` | Hủy vĩnh viễn dữ liệu ở version chỉ định, có ảnh hưởng không đảo ngược. |
| Revoke dynamic DB credential | Thu hồi credential do Database engine quản lý theo lease. |

**Delete repository không thay thế revoke password/API token tại hệ thống đích.** Nếu đã lộ password tĩnh, ngoài việc chỉnh/xóa KV còn phải xoay hoặc vô hiệu hóa password ở database/upstream. Nếu là dynamic secret, dùng vòng đời lease/revoke của engine thay vì xem nó như một record KV.

## 11. Trường hợp bắt buộc dùng VaultOperations

### 11.1. Dynamic database credentials và lease

~~~java
var response = vaultOperations.read("database/creds/orders-reader");
~~~

Lời gọi có thể cấp **username/password mới**, kèm `lease_id`/`lease_duration` tùy engine. Đây là secret động, không phải tài liệu do ứng dụng lưu bằng `@Secret`. Nếu cần renewal, rotation, revoke hoặc cập nhật JDBC pool, dùng `SecretLeaseContainer`/`ManagedSecret` hoặc cơ chế quản lý phù hợp. **Không** chuyển endpoint `database/creds/...` thành một `CrudRepository` giả.

### 11.2. Transit encryption

~~~java
byte[] plaintext = "example-only".getBytes(java.nio.charset.StandardCharsets.UTF_8);

String ciphertext = vaultOperations
        .opsForTransit()
        .encrypt("orders-encryption", plaintext,
                 org.springframework.vault.support.VaultTransitContext.empty());
~~~

Transit mã hóa phía Vault, khóa mã hóa có thể không cần xuất khỏi Vault. `CrudRepository.save` không thay thế lệnh encrypt/decrypt/sign/verify hoặc key rotation. Policy cũng là capability trên endpoint `transit/encrypt/<key>` hay `transit/decrypt/<key>`, khác hẳn KV.

### 11.3. PKI, token và sys

`VaultOperations.opsForPki(...)` cung cấp API phù hợp cho phát hành/ký chứng thư và lifecycle PKI. `opsForToken()` và `opsForSys()` phục vụ các chức năng chuyên biệt tương ứng. Xác thực theo workload và quản lý token phiên thuộc `ClientAuthentication`/`SessionManager`. Những việc này **không phải** CRUD tài liệu KV.

Với certificate/private key, hãy ưu tiên CSR signing khi cần giữ private key tại nơi sử dụng; nếu API PKI trả private key, response đó là bí mật phải được bảo vệ. Một repository Java không tự động quản lý keystore, TLS reload hoặc certificate `notAfter`.

## 12. Quyền hạn, mount discovery và chuẩn bảo mật

Hai cách tiếp cận đều chịu chính sách ACL của Vault. Hệ thống production cần:

1. **Workload identity**: Kubernetes, AppRole, GCP/AWS hoặc cơ chế được hạ tầng hỗ trợ; tránh root token lưu cố định.
2. **Policy đúng API path**: với KV v2 là `secret/data/...` cho data và `secret/metadata/...` cho list.
3. **Nguyên tắc chỉ cấp quyền cần thiết**: service chỉ đọc một ID không nên có `findAll`/LIST, ghi, delete hoặc destroy.
4. **Mount discovery có kiểm soát**: xác minh `sys/internal/ui/mounts/...` của repository hoạt động với token hiện tại.
5. **TLS end-to-end**: trust CA và hostname Vault; không tắt TLS validation để bỏ lỗi môi trường.
6. **Không lưu/log secret**: tránh Spring Actuator `/env`, exception, request/response body, `toString`, JSON controller, CI artifacts và heap dump.
7. **Giới hạn ID từ người dùng**: dùng regex/whitelist hoặc mapping ID nghiệp vụ; tránh truyền path Vault thô từ HTTP request.
8. **Tách ownership**: repository quản lý static KV documents; database secret lease, PKI và Transit phải có chủ sở hữu vòng đời tương ứng.

Đặc biệt, repository method trả về entity chứa password có thể bị JSON serializer của controller công khai hóa nếu return trực tiếp. Đừng làm:

~~~java
// Anti-pattern: DTO có thể chứa password và thông tin nhạy cảm.
@GetMapping("/credentials/{id}")
public CredentialDocument read(@PathVariable String id) {
    return repository.findById(id).orElseThrow();
}
~~~

Thay bằng một service kiểm soát caller, chỉ dùng secret ở backend có quyền và **không trả tài liệu nhạy cảm** cho API công khai. Vault có audit devices, nhưng chúng không xóa được password đã vô tình rò qua log của Java.

## 13. Hiệu năng và mức độ nhất quán

| Hành vi | Cơ chế thực tế | Hệ quả vận hành |
| --- | --- | --- |
| `findById` | Đọc một key theo path. | Hiệu quả cho ID xác định; vẫn chịu network latency. |
| `findAll` / `count` | LIST keyspace, có thể cần nhiều request. | Chi phí tăng theo số key, cần quyền LIST. |
| Query theo prefix ID | LIST rồi lọc theo ID. | Không có server index; giữ keyspace vừa phải. |
| Paging/sorting | Thực hiện phía client trên danh sách/data. | Không coi là phân trang database có index. |
| `save` | Ghi tài liệu KV dưới một key, thường thay toàn body. | Cẩn thận schema drift và race. |
| `@Version` | KV v2 CAS để chống lost update. | Có thể conflict; cần xử lý retry sau khi đọc lại. |
| `deleteById` | Theo semantics KV version. | Không destroy hoặc revoke credential hệ thống đích. |

Vault không được thiết kế thay cho database giao dịch hoặc hệ thống tìm kiếm với cardinality lớn. Hãy dùng repository cho tập tài liệu bí mật tương đối nhỏ, có ID ổn định và chỉ số thao tác phù hợp SLA. Với ứng dụng nhiều replica, cache hoặc retries có thể tạo phiên bản cũ và lost updates; dùng CAS khi có ghi cạnh tranh.

### Giám sát cần có

- Số lượng `findById/save/delete` và độ trễ theo operation/mount logic.
- Tỷ lệ `403`, `404`, lỗi schema mapping và `OptimisticLockingFailureException`.
- Số request LIST và độ trễ/trang truy vấn repository.
- Token login/renew failure (tách khỏi lỗi dữ liệu KV).
- Vault TLS/connectivity errors và khả năng failover.
- Secret refresh/rotation downstream; repository save thành công không chứng minh consumer đã reload password.

Không đưa giá trị password, token, full secret path chứa ID nhạy cảm hoặc JSON payload vào metric labels/log. Khi xảy ra lỗi, phân biệt `auth denied` với `policy denied` và với lỗi query/mapping.

## 14. Tích hợp chung repository và VaultOperations

Không cần chọn **một trong hai cho toàn ứng dụng**. Một service có thể inject cả hai nhưng tách rõ trách nhiệm:

~~~java
import org.springframework.stereotype.Service;
import org.springframework.vault.core.VaultOperations;

@Service
class OrdersVaultFacade {

    private final CredentialRepository documents;
    private final VaultOperations vault;

    OrdersVaultFacade(CredentialRepository documents, VaultOperations vault) {
        this.documents = documents;
        this.vault = vault;
    }

    CredentialDocument loadStaticConfig(String id) {
        return documents.findById(id).orElseThrow();
    }

    String encryptOneValue(byte[] data) {
        return vault.opsForTransit().encrypt(
                "orders-encryption", data,
                org.springframework.vault.support.VaultTransitContext.empty());
    }
}
~~~

Ví dụ tách rõ CRUD tài liệu KV và thao tác Transit; với production nên thêm validate ID, quyền gọi, bộ lọc đầu vào và không phát tán `CredentialDocument` ra ngoài biên nghiệp vụ. Việc dùng chung `VaultOperations` được xác thực qua `SessionManager` giúp chính sách và token không bị tản mát vào từng repository/adapter tự tạo.

### Chiến lược migration từ code direct sang repository

1. Khoanh vùng các lời gọi `VaultOperations` chỉ thực hiện CRUD trên **cùng một tập KV documents**.
2. Xác định mount/keyspace, quy ước ID, JSON schema và các version đang tồn tại.
3. Tạo `@Secret` entity mapping tương thích với dữ liệu cũ; chú ý `_class`, nested fields và trường không được mapper bảo toàn.
4. Thêm repository interface và bật scan trong phạm vi package được chọn.
5. Đọc thử entity từ repository **không ghi** ở staging; so sánh với response cũ và chỉ kiểm thông tin không nhạy cảm.
6. Thêm `@Version` và kiểm CAS trước khi cho nhiều writer, hoặc giữ API direct nếu cần một phần update/phương thức đặc biệt.
7. Chuyển một nhóm call site từ read-only sang CRUD; giám sát LIST, lỗi converter và authorization.
8. Không chuyển Transit, PKI, dynamic secret leases, token renewal sang repository chỉ để “thống nhất API”.
9. Khi ổn định, loại mã mapping cũ và tăng coverage integration/negative tests.

**Rủi ro migration:** một lần repository `save` có thể thay JSON whole document. Trước khi migrate writer, test dữ liệu có field từ phiên bản cũ và bảo đảm không bị mất khi round-trip.

## 15. Xử lý lỗi theo tầng

| Triệu chứng | Nguyên nhân khả dĩ | Hướng chẩn đoán |
| --- | --- | --- |
| Application không tạo repository bean | Thiếu `@EnableVaultRepositories`, sai package scan, dependency không tương thích. | Kiểm config và dependency management. |
| Repository báo lỗi khi phát hiện mount | Token bị từ chối ở `sys/internal/ui/mounts/...` hoặc mount không tồn tại. | Xem HTTP status/path audit đã lọc, kiểm role/policy chính xác. |
| `findById` rỗng với KV v2 | Sai keyspace/ID, KV version/mount hoặc version đã soft-delete. | Kiểm logical key, HTTP data/metadata paths và dữ liệu test. |
| `findAll` hoặc query prefix `403` nhưng `findById` chạy | Thiếu quyền LIST trên `secret/metadata/...`. | Chỉ cấp LIST nếu nghiệp vụ thật sự cần. |
| `save` báo 403 | Thiếu create/update trên data path, token hết hạn hoặc policy sai. | Kiểm token validity, actual API path và capability. |
| `save` báo optimistic locking | Version/CAS cũ đã bị cập nhật đồng thời. | Đọc lại, merge theo nghiệp vụ rồi retry có giới hạn. |
| Dữ liệu bị mất field sau `save` | Entity mapping không biểu diễn mọi field, save whole body. | Thêm schema/version test; dùng direct API khi cần patch. |
| Latency tăng mạnh khi paging/sort | Repository phải LIST/fetch client-side. | Thu nhỏ keyspace hoặc dùng database/index riêng. |
| Secret đã xóa nhưng metadata/history còn | KV v2 soft delete không phải destroy. | Dùng lifecycle versioned KV có quyền và phê duyệt. |
| Token còn sống nhưng Database credential lỗi | Dynamic secret lease hết hạn độc lập. | Kiểm lease và consumer connection; không sửa repository. |
| TLS handshake thất bại | CA, SAN, mTLS, network. | Sửa TLS client; không tắt verification. |

Nếu lỗi xảy ra **trước khi có HTTP response** (DNS, TCP, TLS), sửa quyền Vault không giúp được. Nếu là 403, phải xác định chính xác endpoint từ repository (data, metadata/list hoặc mount discovery) trước khi thay policy.

## 16. Kiểm thử: chứng minh quyết định lựa chọn đúng

### Unit test lớp service bằng JUnit 5 và Mockito

Unit test logic nghiệp vụ nên mock repository interface, ví dụ:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

import java.util.Optional;
import org.junit.jupiter.api.Test;

class RepositoryConsumerTest {

    @Test
    void loadsKnownIdWithoutListingWholeKeyspace() {
        CredentialRepository repository = mock(CredentialRepository.class);
        CredentialDocument testValue =
                new CredentialDocument("orders-read", "demo-user", "demo-pass");

        when(repository.findById("orders-read"))
                .thenReturn(Optional.of(testValue));

        CredentialDocument loaded =
                repository.findById("orders-read").orElseThrow();

        assertEquals("orders-read", loaded.getId());
    }
}
~~~

Đây chỉ chứng minh contract mock và cách caller dùng `findById`; nó **không** kiểm tra Vault mapping, mount discovery, quyền LIST, KV version/CAS hay JSON round-trip. Không tự nhận một mock test là integration test.

### Integration test với Vault KV thật

Chuẩn bị Vault test instance cô lập, KV v2 mount `secret/` và role có policy đúng một keyspace. Các kịch bản nên có:

| Case | Dữ liệu/điều kiện | Assertion |
| --- | --- | --- |
| Repository save/find | ID hợp lệ, payload giả. | Đọc lại đúng field và keyspace. |
| ID bắt buộc String | Entity có `@Id String`. | Repository tạo key logic đúng. |
| JSON nested + schema cũ | Có nested map, field lạ. | Đọc/ghi không vô tình phá dữ liệu ngoài quyền sở hữu. |
| Không được LIST | Chỉ grant read data path. | `findById` có thể chạy nhưng query prefix/findAll bị deny theo endpoint thực. |
| Query prefix ID | Nhiều ID test. | Kết quả lọc theo ID, không tìm theo field khác. |
| CAS cạnh tranh | Hai snapshot cùng version. | Một update được nhận; update version cũ bị từ chối. |
| Revision KV v2 | Ghi nhiều version. | `RevisionRepository` truy xuất đúng lịch sử được phép. |
| Delete KV v2 | Xóa một ID test. | Không còn đọc version hiện tại như trước, nhưng không nhầm với destroy. |
| Policy sai | Token thiếu quyền read hoặc mount discovery. | Lỗi đúng tầng và không nâng quyền tự động. |
| Schema mismatch | Field không convert được hoặc thay class. | Báo lỗi mapping có kiểm soát, không log payload secret. |
| Network/TLS outage | Chặn kết nối hoặc CA không được trust. | Lỗi được phân loại, timeout hữu hạn. |
| Dynamic secret không phải KV | Gọi Database engine bằng API chuyên biệt. | Chứng minh repository không thay thế cơ chế cấp lease. |

**Không chạy kiểm thử ghi, delete hoặc CAS trên Vault production**. Chỉ dùng giá trị giả, token riêng cho test, rollback/cleanup theo quyền sở hữu. Khi tính năng phụ thuộc mount discovery, bảo đảm test kiểm cả đường `sys/internal/ui/mounts/...` và cấu hình quyền tương ứng.

## 17. Checklist ra quyết định cho dự án

Trước khi chọn repository thay cho `VaultOperations`, trả lời:

1. Đối tượng có phải là **document KV với ID String ổn định**, hay là dynamic credential, certificate hoặc thao tác mã hóa?
2. Nghiệp vụ có nhiều thao tác CRUD lặp lại và cần Java object mapping, hay chỉ đọc vài secret path cố định?
3. Cần tìm theo **ID** hay cần truy vấn theo field? Nếu theo field, Vault repository không phải query engine mong muốn.
4. Có dùng `findAll/count/paging` không? Keyspace bao nhiêu record, và policy có cho phép LIST?
5. KV version nào? Có yêu cầu `@Version`/CAS, revisions, undelete hoặc destroy không?
6. Khi `save` toàn document, có khả năng làm mất field do service khác ghi hoặc sai schema không?
7. Policy có đúng `secret/data/*` và `secret/metadata/*`; mount discovery có hoạt động theo Vault role thực tế không?
8. Ứng dụng có auth theo workload, TLS CA hợp lệ, token renewal và logging không lộ secret không?
9. Nếu secret dùng cho JDBC pool/TLS, consumer có xử lý rotation hay chỉ lưu password vào entity?
10. Có integration test Vault thật cho mapping, ACL, concurrency, delete semantics và lỗi mạng không?

### Ba tình huống lựa chọn mẫu

**Tình huống A — Nên dùng repository.** Một dịch vụ nội bộ có khoảng vài chục tài liệu KV của cùng một loại, được tìm theo ID xác định, đôi khi cập nhật bằng CAS và cần lưu nested JSON. `@Secret` + `CrudRepository` giúp chuẩn hóa mapping và kiểm thử. Không cần truy vấn phức tạp.

**Tình huống B — Nên dùng VaultOperations.** Một microservice chỉ đọc `secret/orders/config` lúc khởi động, dùng Transit để mã hóa một số giá trị và xin PKI certificate qua role. Repository sẽ làm tăng abstraction không cần thiết và không hỗ trợ đa số operation của nhu cầu này.

**Tình huống C — Dùng kết hợp.** Một hệ thống quản lý static secrets có CRUD documents riêng, đồng thời các ứng dụng runtime lấy dynamic database credential, renew token, xoay password và đổi JDBC pool. Dùng repository cho static KV aggregate; dùng `VaultOperations` cùng session/lease management cho các chức năng còn lại.

**Kết luận:** **Vault Repository là Spring Data CRUD/mapping đặt trên KV secrets engine**, không phải một “VaultOperations thế hệ mới” hay một database query engine. Chọn repository khi **aggregate có ID, cùng schema và cần CRUD nhất quán**. Chọn `VaultOperations` cho **API Vault cụ thể**, version lifecycle chuyên sâu, Database leases, Transit, PKI và token. Tách đúng trách nhiệm giúp code Java rõ ràng, policy gọn, tránh scan secret không cần thiết và duy trì an toàn của Vault.

## Tài liệu tham khảo chính thức

- [Spring Vault – Vault Repositories](https://docs.spring.io/spring-vault/reference/vault/vault-repositories.html).
- [Spring Vault – Vault Secret Engines và KV Operations](https://docs.spring.io/spring-vault/reference/vault/vault-secret-engines.html).
- [Spring Vault – VaultOperations API](https://docs.spring.io/spring-vault/reference/api/java/org/springframework/vault/core/VaultOperations.html).
- [Spring Vault – @EnableVaultRepositories API](https://docs.spring.io/spring-vault/reference/api/java/org/springframework/vault/repository/configuration/EnableVaultRepositories.html).
- [Spring Vault – @Secret API](https://docs.spring.io/spring-vault/reference/api/java/org/springframework/vault/repository/mapping/Secret.html).
- [Spring Vault – VaultVersionedKeyValueOperations API](https://docs.spring.io/spring-vault/reference/api/java/org/springframework/vault/core/VaultVersionedKeyValueOperations.html).
- [Spring Data Commons – Repository Interfaces](https://docs.spring.io/spring-data/commons/reference/repositories/core-concepts.html).
