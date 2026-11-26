# `@Secret` và ánh xạ lớp dữ liệu trong Spring Vault Repository

## 1. `@Secret` giải quyết vấn đề gì?

Trong module **SPRING_VAULT**, ứng dụng Java truy cập HashiCorp Vault qua `VaultTemplate` để lấy KV secrets, sử dụng token do workload authentication cấp, làm việc với Transit encryption, PKI và các secret có lease. Ngoài API thao tác trực tiếp theo path, **Spring Vault Repository** cung cấp cách tiếp cận giống Spring Data: khai báo **lớp dữ liệu (domain object)** và interface repository, rồi thực hiện `save`, `findById`, `deleteById` mà không phải tự dựng JSON/request cho mỗi lần.

Trọng tâm của bài là annotation **`org.springframework.vault.repository.mapping.Secret`**, viết là `@Secret`. Annotation này đánh dấu một **aggregate root được lưu trong KV secrets engine** và quy định *keyspace* cùng mount lưu trữ. Kết hợp với `@Id` của Spring Data, framework tính đường dẫn vật lý của từng đối tượng trong Vault.

Giả sử dịch vụ Orders cần lưu *cấu hình nội bộ* theo từng môi trường:

~~~text
Vault mount: secret/                 (KV v2)
Domain:      OrdersSettings          (@Secret)
Keyspace:    orders                  (@Secret("orders"))
Identifier:  checkout-dev            (@Id)
Logical key: secret/orders/checkout-dev
KV v2 API:   secret/data/orders/checkout-dev
~~~

Khi đọc bản ghi, repository chuyển JSON thành `OrdersSettings`. Khi ghi bản ghi, repository chuyển object thành JSON và đặt vào một key. **`@Secret` không đồng nghĩa với một loại credential động hay cơ chế xác thực:** nó là metadata mapping cho *dữ liệu KV*. Token và policy vẫn quyết định có được đọc, ghi, liệt kê hoặc xóa key hay không.

### Khi nào nên dùng Repository?

| Tình huống | Lựa chọn phù hợp |
| --- | --- |
| Một tập bản ghi KV theo `id`, cấu trúc Java rõ ràng, cần CRUD | `@Secret` + `CrudRepository`. |
| Cần đọc một key hoặc quản lý version/metadata cụ thể | `VaultTemplate.opsForVersionedKeyValue(...)` có thể trực tiếp và rõ hơn. |
| Secrets thay đổi cùng lifecycle database lease | `VaultTemplate` hoặc `SecretLeaseContainer`, **không** coi repository là lease manager. |
| Transit encrypt/decrypt, PKI issue, cấp dynamic database users | Sử dụng API secrets engine tương ứng, **không** `@Secret` repository. |
| Ứng dụng cần query phức tạp, joins, tìm theo nhiều field | Database/engine có chỉ mục thích hợp; Vault KV **không phải SQL database**. |

Mục tiêu: ánh xạ `@Secret`/`@Id`, cấu hình CRUD, versioning và kiểm thử Vault ACL.

## 2. Các annotation quyết định đường dẫn và định danh

### 2.1. `@Secret` thuộc package nào?

~~~java
import org.springframework.vault.repository.mapping.Secret;
import org.springframework.data.annotation.Id;

@Secret(value = "orders", backend = "secret")
public class OrdersSettings {
    @Id
    private String id;
    private String endpoint;
}
~~~

Đây là **minh họa metadata**; lớp đầy đủ với constructor/getters ở mục tiếp theo. Các thuộc tính chính:

| Thuộc tính | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| `@Secret.value` | Keyspace: prefix phân biệt nhóm entity. Tên rỗng dùng quy ước mặc định theo loại entity. | `"orders"` |
| `@Secret.backend` | **Secrets engine mount path**, không phải tên auth method. Mặc định `"secret"`. | `"secret"` |
| `@Secret.engine` | Alias của `backend` trong **Spring Vault 4.1+**. | `"secret"` |
| `@Id` | Định danh dùng làm phần key bên dưới keyspace; Vault Repository yêu cầu ID kiểu `String`. | `"checkout-dev"` |
| `@Version` | Phiên bản số của KV v2 để cập nhật theo CAS/optimistic locking. | `Long version` |

Ưu tiên `@Secret(value = "orders", backend = "secret")` khi viết bài có thể dùng trên nhiều phiên bản Spring Vault; không dùng `engine` khi dự án còn ở 3.x/4.0. `@Secret` không tự mount KV engine; mount do Vault admin cấu hình.

Các thuộc tính trên hỗ trợ **SpEL**, nhưng không lấy tenant ID chưa xác thực để tính path hoặc mount tùy ý.

### 2.2. ID là thành phần của key chứ không phải auto-increment

Repository dùng key theo quy ước **`keyspace/id`**. Với entity trên, lệnh `save` cho id `checkout-dev` đi vào key logic `orders/checkout-dev` dưới mount `secret/`. Spring Vault cũng có quy ước nhận diện field tên `id` khi không có annotation; nhưng **đặt `@Id` tường minh** giúp tránh thay đổi ý nghĩa khi refactor.

ID phải là `String` ổn định và hợp lệ; sinh/validate tại tầng nghiệp vụ, không trông chờ sequence tự động. Chặn `/`, `..`, ký tự điều khiển và PII để ngăn path injection, lộ dữ liệu qua audit logs. `@Id` không phải Vault login token hay lease ID.

> Ví dụ trong bài dùng `secret/` như tên mount và `orders/` như keyspace. Trên Vault thật, mount có thể tên `kv/` hoặc `config/`; hãy kiểm tra bằng `vault secrets list` trước khi cấu hình.

## 3. Thiết kế lớp Java có thể ánh xạ được

Một đối tượng domain không cần kế thừa lớp Vault chuyên biệt. Spring Vault Repository dùng **`VaultConverter`** để biến POJO thành các cặp field JSON, kể cả cấu trúc lồng nhau. Ví dụ cho cấu hình không chứa mật khẩu thực:

~~~java
package example.orders;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.Version;
import org.springframework.vault.repository.mapping.Secret;

@Secret(value = "orders", backend = "secret")
public class OrdersSettings {

    @Id
    private String id;

    @Version
    private Long version;

    private String endpoint;
    private RetryPolicy retryPolicy;
    private List<String> regions = new ArrayList<>();
    private Map<String, String> labels = Map.of();

    protected OrdersSettings() {
        // Constructor cho object mapper.
    }

    public OrdersSettings(String id, String endpoint, RetryPolicy retryPolicy) {
        this.id = id;
        this.endpoint = endpoint;
        this.retryPolicy = retryPolicy;
    }

    public String getId() { return id; }
    public Long getVersion() { return version; }
    public String getEndpoint() { return endpoint; }
    public RetryPolicy getRetryPolicy() { return retryPolicy; }
    public List<String> getRegions() { return regions; }
    public Map<String, String> getLabels() { return labels; }
    public void setEndpoint(String endpoint) { this.endpoint = endpoint; }
    public void setRetryPolicy(RetryPolicy policy) { this.retryPolicy = policy; }
    public void setRegions(List<String> regions) { this.regions = regions; }
    public void setLabels(Map<String, String> labels) { this.labels = labels; }

    public static class RetryPolicy {
        private int attempts;
        private long backoffMillis;

        protected RetryPolicy() { }
        public RetryPolicy(int attempts, long backoffMillis) {
            this.attempts = attempts;
            this.backoffMillis = backoffMillis;
        }
        public int getAttempts() { return attempts; }
        public long getBackoffMillis() { return backoffMillis; }
    }
}
~~~

Chỉ sửa các field nghiệp vụ được phép; Spring Vault xử lý version, không tự tăng version trước `save`.

### Một vài bẫy về thiết kế dữ liệu

- **Constructor:** bảo đảm mapper có thể khởi tạo object; kiểm thử records, final fields và polymorphism thật.
- **Logs:** không sinh `toString()` hoặc debug dump lộ secrets.
- **Kiểu dữ liệu:** custom converters cho các kiểu phức tạp; Vault Repository không phải JPA.

## 4. Từ domain object sang JSON của Vault

Giả sử ứng dụng lưu `OrdersSettings("checkout-dev", "https://orders.dev.example", new RetryPolicy(3, 250))`. Nội dung JSON logic của secret có thể giống:

~~~json
{
  "_class": "example.orders.OrdersSettings",
  "endpoint": "https://orders.dev.example",
  "retryPolicy": {
    "attempts": 3,
    "backoffMillis": 250
  },
  "regions": ["ap-southeast-1"],
  "labels": {
    "owner": "orders-team"
  }
}
~~~

Đây là JSON minh họa. Mapper có thể ghi `_class` ở root/kiểu nested trừu tượng; thứ tự field và metadata tùy converters. ID/version có vai trò riêng nên **không suy diễn JSON luôn có `id` hoặc `version`**.

| Kiểu thuộc tính | Hình dạng JSON thông dụng | Điều cần kiểm tra |
| --- | --- | --- |
| `String`, `int`, `boolean` | Scalar string/number/boolean | Định dạng và kiểu sau deserialize. |
| POJO lồng `RetryPolicy` | Object JSON `retryPolicy` | Constructor và nested conversion. |
| `List<String>` | JSON array | Element order và null values. |
| `Map<String,String>` | JSON object | Key/value có đúng kiểu mong đợi. |
| Kiểu phức tạp tùy chỉnh | Có thể cần `VaultCustomConversions` | Không serialize nhầm internal state hoặc secret. |
| Interface/abstract type | Có thể có `_class` type hint | Kiểm soát polymorphic type và thay đổi package khi refactor. |

### Không coi `save` là thao tác PATCH

Một đặc điểm quan trọng: **ghi entity vào Vault có thể thay nội dung toàn bộ key**, không phải cập nhật vài field rồi giữ nguyên dữ liệu cũ. Giả sử dữ liệu hiện tại có `endpoint`, `apiKey` và `region`, nhưng phiên bản Java chỉ map `endpoint`; gọi `save` có thể làm mất hai field chưa map.

Ví dụ:

~~~text
Ban đầu ở secret/orders/checkout-dev:
  endpoint = https://...
  region   = asia
  legacy   = "giá trị do hệ thống khác ghi"

Java chỉ ánh xạ endpoint rồi gọi repository.save(entity).

Kết quả có thể:
  endpoint = https://...
  (region và legacy đã biến mất khỏi bản ghi mới)
~~~

Chỉ định owner ghi dữ liệu, kiểm thử schema migration. `@Version` phát hiện xung đột nhưng không cứu field vắng mặt trong DTO.

### `VaultConverter` và `VaultCustomConversions`

`VaultConverter` chuyển giữa `SecretDocument` và POJO; `VaultCustomConversions` đăng ký converter property hoặc document. Kiểm thử read/write hai chiều.

Không hardcode khóa decrypt trong converter; Transit có policy riêng.

## 5. Bật Vault Repository và thực hành CRUD

### 5.1. Phụ thuộc và cấu hình

Vault repositories dùng **Spring Data Commons** và **Spring Data KeyValue** bên cạnh Spring Vault core. Với Maven, chọn bộ phiên bản Spring Vault/Spring Data tương thích (ưu tiên dependency management/BOM của ứng dụng) rồi khai báo phần cần thiết:

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

`spring-data-commons` thường đến theo dependencies của Spring Data KeyValue; không tự phối các major version thiếu tương thích. Đoạn pom trên giả định parent/BOM đã cung cấp version; nếu dự án Maven thuần không có BOM, phải khai báo version rõ ràng.

~~~java
package example.orders;

import org.springframework.context.annotation.Configuration;
import org.springframework.vault.repository.configuration.EnableVaultRepositories;

@Configuration
@EnableVaultRepositories(basePackageClasses = OrdersSettingsRepository.class)
public class OrdersRepositoryConfiguration {
    // VaultTemplate được cấu hình dưới dạng bean ở cấu hình Vault chung.
}
~~~

`VaultTemplate` cần endpoint HTTPS, CA tin cậy, `SessionManager` hoặc `ClientAuthentication` đúng workload, và token chỉ có quyền cần thiết. **`@EnableVaultRepositories` kích hoạt repository factory**, không thay thế cấu hình xác thực. Nếu ứng dụng có nhiều `VaultTemplate`, phải cấu hình bean được repository sử dụng một cách có chủ đích và kiểm tra namespace/mount chính xác.

### 5.2. Interface repository

~~~java
package example.orders;

import java.util.List;
import org.springframework.data.repository.CrudRepository;

public interface OrdersSettingsRepository
        extends CrudRepository<OrdersSettings, String> {

    List<OrdersSettings> findByIdStartsWith(String prefix);
}
~~~

Phương thức `save`, `findById`, `existsById`, `findAll`, `count` và `deleteById` kế thừa từ `CrudRepository`. Phương thức `findByIdStartsWith` được dẫn xuất **theo trường ID**, không cần tự viết HTTP request; nhưng đừng suy ra repository hỗ trợ tìm kiếm bằng tất cả field của object.

### 5.3. Sử dụng từ service

~~~java
package example.orders;

import java.util.Optional;
import org.springframework.stereotype.Service;

@Service
public class OrdersSettingsService {

    private final OrdersSettingsRepository repository;

    public OrdersSettingsService(OrdersSettingsRepository repository) {
        this.repository = repository;
    }

    public OrdersSettings createDemo() {
        OrdersSettings entity = new OrdersSettings(
            "checkout-dev",
            "https://orders.dev.example",
            new OrdersSettings.RetryPolicy(3, 250));
        return repository.save(entity);
    }

    public Optional<OrdersSettings> find(String id) {
        return repository.findById(id);
    }

    public void remove(String id) {
        repository.deleteById(id);
    }
}
~~~

Ví dụ chỉ để luyện tập ở Vault test. Không đặt đoạn tạo dữ liệu demo trong startup production, vì `save` có thể ghi đè key thực. Trước khi gọi `remove`, cần xác thực và phân quyền **người gọi nghiệp vụ**: Vault token của service có quyền delete không đồng nghĩa mọi user HTTP của service được phép xóa.

## 6. KV v1, KV v2 và optimistic locking

Spring Vault Repository sử dụng **KV secrets engine**. Từ Spring Vault 2.4, repository hỗ trợ thêm KV v2 và phát hiện phiên bản engine tại runtime; điều này có tác động đến ACL, version và delete semantics.

| Nội dung | KV v1 | KV v2 |
| --- | --- | --- |
| Đường dẫn API | `secret/orders/checkout-dev` | `secret/data/orders/checkout-dev` |
| Phiên bản hóa | Không có history/CAS như KV v2 | Có version, metadata, CAS. |
| `@Version` optimistic locking | Không dùng cơ chế CAS KV v2 | Dùng thuộc tính version số để kiểm soát concurrent writes. |
| Xóa qua `CrudRepository.delete(...)` | Xóa key của KV v1 | Thông thường **soft-delete** version, không destroy mọi version. |
| Phép list keyspace | List dưới path dữ liệu | List qua `secret/metadata/orders`. |

**Đừng thêm `data/` vào `@Secret.value`.** Repository phát hiện KV v2 và chuyển API path khi tương tác. Với `@Secret(value="orders", backend="secret")` và ID `checkout-dev`, keyspace vẫn là `orders`, không phải `data/orders`.

### 6.1. Optimistic locking bằng `@Version`

`@Version` của `org.springframework.data.annotation.Version` trong class `OrdersSettings` cho Spring Vault biết version đã đọc. Trên KV v2, lúc `save`, repository đưa version tương ứng vào **CAS** (check-and-set). Vault chỉ chấp nhận write nếu version hiện tại khớp điều kiện.

~~~text
Repo A đọc checkout-dev ở version N
Repo B đọc checkout-dev ở version N
Repo A đổi endpoint rồi save -> version N+1
Repo B đổi retryPolicy rồi save với version N
                                  |
                                  +--> OptimisticLockingFailureException
~~~

Ứng dụng không nên bắt mọi `OptimisticLockingFailureException` rồi ghi đè bằng bản B ngay. Thay vào đó: đọc lại bản mới nhất, xác định business intent, merge các field hợp lệ và retry **có giới hạn**. `@Version` chỉ hữu ích khi dùng KV v2 và đủ quyền đọc/ghi; field version phải là kiểu số như `int` hoặc `long` và kiểu wrapper tương ứng khi API hỗ trợ.

### 6.2. Revision history không phải database transaction

Khi muốn đọc các phiên bản cũ của KV v2, Spring Vault cung cấp `RevisionRepository<T, String, Integer>`:

~~~java
import org.springframework.data.repository.CrudRepository;
import org.springframework.data.repository.history.RevisionRepository;

public interface OrdersRevisionRepository
        extends CrudRepository<OrdersSettings, String>,
                RevisionRepository<OrdersSettings, String, Integer> {
}
~~~

Đọc revision bằng `findRevisions(id)` hoặc overload có phân trang. Đây là **lịch sử của một key**, không phải ACID transaction nhiều key. Các phiên bản đã **destroy** hoặc nằm ngoài policy có thể không còn đọc được. `CrudRepository.delete(...)` trên KV v2 không tương đương với `destroy` tất cả historical versions; nếu cần xóa vĩnh viễn phải tuân thủ API và policy riêng.

## 7. Truy vấn của Vault Repository có giới hạn

KV engine không có bảng, chỉ mục SQL, full-text search hoặc join. Query derivation của Vault Repository chỉ hỗ trợ **predicate dựa trên thuộc tính ID**. Ví dụ:

~~~java
public interface OrdersSettingsRepository
        extends CrudRepository<OrdersSettings, String> {

    List<OrdersSettings> findByIdStartsWith(String prefix);
    List<OrdersSettings> findByIdBetween(String from, String to);
}
~~~

Một phương thức `findByEndpoint(String endpoint)` **không** phải cách truy vấn nội dung `endpoint` được hỗ trợ như trong JPA. Nếu cần tìm theo endpoint, team hoặc trạng thái, hãy thiết kế key theo nhu cầu tra cứu (trong giới hạn an toàn), hoặc dùng storage/query engine chuyên dụng.

### Cách query thực tế hoạt động

~~~mermaid
flowchart TD
    A["Repository.findByIdStartsWith('checkout-')"] --> B["LIST keyspace orders/"]
    B --> C["Lọc ID theo predicate"]
    C --> D["Áp dụng sorting/paging theo triển khai"]
    D --> E["READ các secret cần thiết"]
    E --> F["VaultConverter -> OrdersSettings"]
~~~

Vault list key thường chỉ trả **tên**. Repository có thể lọc ID rồi fetch từng entry, đồng thời sorting/paging có thể yêu cầu liệt kê toàn bộ key và đọc thêm bản ghi để sắp xếp chính xác. Vì vậy:

- `findAll`, `count`, tìm prefix và phân trang không nên được coi là thao tác O(1) như truy vấn có index.
- Token có quyền **read một key** không nhất thiết có quyền **list cả keyspace**; `findById` có thể thành công trong khi `findAll` bị 403.
- Danh sách ID bản thân có thể tiết lộ thông tin. Không cấp `list` rộng chỉ để tiện debug.
- Với nhiều nghìn/millions keys hoặc nhu cầu sort/filter nghiệp vụ, Vault KV repository không phải lựa chọn kho dữ liệu hiệu quả.

Nếu chia nhiều tenant, prefix `tenant-x` trong ID **không phải ranh giới phân quyền**. Vault ACL cần ràng buộc path/mount của mỗi tenant hoặc workload, không trông chờ service lọc ID đúng trong mọi phương thức.

## 8. Vault ACL và đường dẫn thật phía server

`@Secret` chỉ tính đường dẫn lưu trữ; Vault policy quyết định token có thể làm gì trên đó. Với ví dụ KV v2 ở mount `secret/`, policy cho **lab CRUD trong keyspace orders** có thể viết:

~~~hcl
path "secret/data/orders/*" {
  capabilities = ["create", "read", "update", "delete"]
}

# Chỉ để sử dụng các phép LIST/COUNT/FIND_ALL trong keyspace này:
path "secret/metadata/orders" {
  capabilities = ["list"]
}

path "secret/metadata/orders/*" {
  capabilities = ["list", "read"]
}
~~~

Áp dụng:

~~~bash
# Chỉ chạy với identity quản trị ở môi trường thử nghiệm.
vault policy write orders-repository orders-repository.hcl
vault token capabilities secret/data/orders/checkout-dev
~~~

Trong production, nên tách role **read-only** và **writer**. Một service chỉ cần đọc key cụ thể có thể dùng chính sách chặt hơn `secret/data/orders/checkout-dev` với `read`; không cấp `list` hay `delete` nếu không cần. Lưu ý `metadata` và `data` là **hai đường dẫn khác nhau của KV v2**, vì vậy policy cho `secret/data/orders/*` không tự cấp `list` ở `secret/metadata/orders`.

**Khám phá mount:** Vault Repositories cần xác định engine mount/version thông qua endpoint `sys/internal/ui/mounts/...`. Nếu ứng dụng không nhận diện được mount, hãy xem audit log, response 403, chính sách/khả năng truy cập endpoint này và cấu hình Vault; đừng mặc định mọi 403 là quyền đọc key. Không cấp `sys/*` rộng chỉ để khắc phục lỗi phát hiện mount.

### Bảo vệ credential và thông tin nhạy cảm

Ví dụ trong tài liệu không chứa mật khẩu thật. Nếu entity lưu password hoặc API key, cần đảm bảo: TLS/CA tin cậy; token workload được cấp policy tối thiểu; không log `VaultResponse`/entity; không đưa giá trị secret vào metrics, exception, snapshot test hoặc HTTP response; quản lý TTL/rotation theo loại secret.

**`_class` type hint** có thể làm lộ tên package/class và là chi tiết schema phải kiểm tra khi đổi package. Không lấy payload không đáng tin từ user để chỉ định arbitrary class trong converter; kiểm soát nguồn dữ liệu và cơ chế mapping cụ thể.

## 9. Phân biệt repository với `VaultTemplate` và các API khác

Ba cách làm thường gặp trong Spring Vault:

| API | Đơn vị thao tác | Khi nào ưu tiên |
| --- | --- | --- |
| `CrudRepository<OrdersSettings,String>` | Entity theo ID, KV keyspace | Lưu/đọc nhiều object cùng loại bằng CRUD. |
| `VaultTemplate.opsForKeyValue(...)` | Path + map/object trong KV v1/v2 | Cần tương tác trực tiếp, chọn backend version hoặc trả data map. |
| `VaultTemplate.opsForVersionedKeyValue(...)` | KV v2 path, version và metadata | Cần CAS, đọc version cụ thể, metadata và hành vi riêng KV v2. |
| `SecretLeaseContainer` | Dynamic secret có lease | Cần renew/rotate database credential liên tục. |
| Transit/PKI operations | Crypto request, certificate issue | Không phải lưu entity qua `@Secret`. |

Ví dụ đọc cùng key bằng KV v2 operations:

~~~java
import java.util.Map;
import org.springframework.vault.core.VaultOperations;
import org.springframework.vault.support.Versioned;

public class DirectKvReader {
    private final VaultOperations vault;

    public DirectKvReader(VaultOperations vault) {
        this.vault = vault;
    }

    public Versioned<Map<String, Object>> read(String id) {
        // Validate id bằng allowlist trước khi ghép vào path.
        if (!id.matches("[A-Za-z0-9_-]{1,64}")) {
            throw new IllegalArgumentException("Invalid id");
        }
        return vault.opsForVersionedKeyValue("secret")
            .get("orders/" + id);
    }
}
~~~

Repository và direct KV operations có thể cùng dùng một mount/keyspace, nhưng **không nên để hai bộ serializer/DTO khác nhau ghi cùng key**: ghi toàn bộ object có thể làm mất field chưa map. Chọn một owner ghi và mô tả hợp đồng JSON rõ ràng nếu có hệ thống khác đọc.

Trong mô hình reactive, `ReactiveVaultTemplate` có API KV reactive và `ReactiveSessionManager`; interface `CrudRepository` ở đây theo **mô hình đồng bộ**, không tự biến thành `ReactiveCrudRepository`. Ứng dụng WebFlux không nên gọi repository blocking trực tiếp trong event loop. Khi cần reactive end-to-end, ưu tiên API `ReactiveVaultTemplate` tương ứng hoặc tách phần blocking ra worker scheduler có kiểm soát.

## 10. Kiểm thử mapping, CRUD, version và bảo mật

### 10.1. Chuẩn bị Vault test

Trên môi trường lab riêng (Vault dev hoặc Testcontainers được cấu hình an toàn), mount KV v2:

~~~bash
# Chỉ enable nếu secret/ chưa được mount.
vault secrets enable -path=secret -version=2 kv

# Kiểm tra trực tiếp key do repo.save sinh sau khi chạy ứng dụng.
vault kv get -mount=secret orders/checkout-dev

# Chỉ dùng môi trường test; delete version hiện hành:
vault kv delete -mount=secret orders/checkout-dev
~~~

Chạy `get`/`delete` **sau khi** ứng dụng ghi bản ghi test. Dùng token workload riêng, không dùng root để kiểm thử quyền.

### 10.2. Bài kiểm thử CRUD cơ bản

Ví dụ JUnit chạy với Spring test context có `OrdersSettingsRepository`, `VaultTemplate`, mount và policy được cấu hình:

~~~java
import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBootTest
class OrdersSettingsRepositoryIT {

    @Autowired OrdersSettingsRepository repository;

    @Test
    void saveFindAndDeleteMappedObject() {
        String id = "checkout-test";
        OrdersSettings settings = new OrdersSettings(
            id, "https://orders.test.example",
            new OrdersSettings.RetryPolicy(2, 100));

        try {
            OrdersSettings saved = repository.save(settings);
            assertEquals(id, saved.getId());

            OrdersSettings loaded = repository.findById(id).orElseThrow();
            assertEquals("https://orders.test.example", loaded.getEndpoint());
            assertEquals(2, loaded.getRetryPolicy().getAttempts());
        } finally {
            repository.deleteById(id);
        }
    }
}
~~~

Mẫu test này giả định test class đã được đặt đúng package và class entity/config có thể scan. Dùng ID duy nhất cho mỗi test chạy song song; không xóa key của môi trường dùng chung. Trường hợp test thất bại khi `save`, `deleteById` trong `finally` cũng có thể gặp lỗi quyền; cần cleanup bằng identity test-admin tách biệt.

### 10.3. Ma trận xác minh

| Mã | Bài thử | Kỳ vọng |
| --- | --- | --- |
| MAP-01 | Lớp có `@Secret("orders")` và `@Id String` | ID `checkout-dev` ánh xạ key `orders/checkout-dev`. |
| MAP-02 | Nested POJO, list và map | Readback khôi phục đúng dữ liệu sau `save`. |
| MAP-03 | Đọc JSON bằng CLI sau `save` | Kiểm tra field, `_class`, thiếu/thừa field nhạy cảm. |
| KV-01 | Repo với KV v2 | Tương tác API `data/` và `metadata/` đúng phiên bản engine. |
| CAS-01 | Hai bản đọc cùng version, cả hai sửa rồi save | Save thứ hai bị `OptimisticLockingFailureException`. |
| QUERY-01 | `findByIdStartsWith("checkout-")` | Chỉ trả ID matching và mapping tương ứng. |
| QUERY-02 | `findAll()` với token thiếu `list` | Lỗi quyền rõ ràng; không tự nâng quyền. |
| ACL-01 | Token chỉ có quyền `read` trên một key | Đọc key đó PASS; save/delete key khác DENY 403. |
| DELETE-01 | Repo delete KV v2 | Version hiện hành bị soft-delete; không nhầm thành destroy mọi version. |
| SCHEMA-01 | Java DTO thiếu một field cũ rồi save | Phát hiện mất field chưa map và chặn rollout schema không tương thích. |
| ID-01 | ID chứa slash/`..`/ký tự lạ | Validation từ chối trước khi chạm Vault API. |

Ngoài test CRUD, cần đo số HTTP request khi `findAll`, phân trang và sorting để tránh biến một thao tác “tìm danh sách” thành hàng trăm hoặc hàng nghìn request Vault. Test mức tích hợp nên sử dụng secrets giả, thu hồi token sau test khi thích hợp, và không commit log chứa value thật.

## 11. Lỗi thường gặp, checklist và tự đánh giá

### Lỗi thường gặp

| Hiện tượng | Nguyên nhân phổ biến | Hướng điều tra |
| --- | --- | --- |
| Repository bean không được tạo | Thiếu `@EnableVaultRepositories`, dependency Spring Data hoặc package scan. | Kiểm tra dependency/BOM, component scan và `VaultTemplate` bean. |
| Đọc `findById` trả empty | Sai `backend`, keyspace, ID, deleted KV v2 version. | Xác nhận mount/key bằng Vault CLI và token đúng. |
| `findById` PASS nhưng `findAll` 403 | Chưa có capability `list` trên KV v2 metadata path. | Kiểm tra `secret/metadata/orders`. |
| `save` 403 | Token thiếu `create`/`update` trên KV v2 data path. | Kiểm tra auth role, policy và target path. |
| Lỗi phát hiện mount/version | Truy cập `sys/internal/ui/mounts/...` không được phép hoặc mount sai. | Xem audit log và mount configuration. |
| `OptimisticLockingFailureException` | Version cũ, CAS không khớp. | Đọc lại version mới, merge và retry có giới hạn. |
| Mất field sau khi `save` | Mapper ghi nguyên bản JSON, DTO không mang field cũ. | Quản lý schema/version và converter; không patch ngầm. |
| Query theo `endpoint` không chạy | Vault query derivation chỉ lọc predicate ID. | Đổi thiết kế key/index hoặc database khác. |
| Xóa xong vẫn thấy version cũ | KV v2 delete không destroy lịch sử. | Phân biệt soft-delete với destroy theo API riêng. |

### Checklist triển khai

- [ ] Dùng `@Secret` đúng package, `value` là keyspace, `backend` là mount; không nhầm `data/` với tên keyspace.
- [ ] `@Id` dùng `String`, không nhận path từ input chưa validate; ID không chứa PII.
- [ ] Domain object ánh xạ đúng nested object/list/map; kiểm tra `_class` và converters khi refactor.
- [ ] Có chiến lược schema evolution vì `save` có thể ghi đè toàn bộ JSON của key.
- [ ] Dùng `@Version`/CAS khi nhiều writer cập nhật cùng key KV v2; xử lý xung đột rõ ràng.
- [ ] Vault token workload có quyền đúng `data`, `metadata` và endpoint nhận diện mount; không dùng root token.
- [ ] Phân biệt `delete` và `destroy` trong KV v2; bảo vệ history và retention theo chính sách.
- [ ] Không dùng repository thay cho lease lifecycle, Transit, PKI hoặc query database.
- [ ] Có test CRUD, mapping round-trip, query ID, 403, soft-delete và concurrency.
- [ ] Không đưa secret value, token hoặc payload raw vào log/metrics/HTTP response.

### Câu hỏi tự kiểm tra

1. `@Secret(value = "orders", backend = "secret")` và `@Id String id` kết hợp tạo key nào nếu ID là `checkout-dev`?
2. Sự khác nhau giữa key logic `secret/orders/checkout-dev` và API path `secret/data/orders/checkout-dev` là gì?
3. Vì sao một class chỉ dùng `@Secret` vẫn cần cấu hình Vault token, policy và `VaultTemplate`?
4. Tại sao repository `save` có thể làm mất field `legacy` được hệ thống khác ghi vào cùng key?
5. `findByEndpoint(...)` có tương đương query trong JPA không? Vì sao?
6. Khi hai phiên cùng sửa KV v2, `@Version` giúp phát hiện xung đột bằng cách nào?
7. Vì sao `findById` có thể thành công nhưng `findAll` bị 403?
8. KV v2 `delete` có làm mọi version biến mất vĩnh viễn không? Trường hợp nào cần API khác?
9. Khi cần rotating database credentials hoặc PKI certificates, tại sao `@Secret` repository không phải công cụ đúng?

## Tài liệu chính thức

- [Spring Vault — Vault Repositories](https://docs.spring.io/spring-vault/reference/vault/vault-repositories.html)
- [Spring Vault API — `@Secret`](https://docs.spring.io/spring-vault/reference/api/java/org/springframework/vault/repository/mapping/Secret.html)
- [Spring Vault — KV v1 và KV v2 operations](https://docs.spring.io/spring-vault/reference/vault/vault-secret-engines.html)
- [Spring Data Commons — Repository interfaces](https://docs.spring.io/spring-data/commons/reference/repositories.html)
- [HashiCorp Vault — KV v2 secrets engine](https://developer.hashicorp.com/vault/docs/secrets/kv/kv-v2)

**Kết luận:** `@Secret` biến POJO thành một thực thể có keyspace/mount xác định; `@Id String` chọn key, còn `VaultConverter` phụ trách JSON. Repository thuận tiện cho CRUD trên Vault KV nhưng vẫn chịu giới hạn query theo ID, semantics KV v2 và Vault ACL. Kết hợp validation, versioning, schema discipline và kiểm thử tích hợp để tránh ghi đè hoặc lộ dữ liệu nhạy cảm.
