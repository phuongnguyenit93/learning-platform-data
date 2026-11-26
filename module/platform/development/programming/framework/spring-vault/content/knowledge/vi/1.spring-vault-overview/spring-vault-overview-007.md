# Đối chiếu cách dùng API, PropertySource và repository

> **Chương:** Bản đồ Spring Vault  
> **Bối cảnh:** Spring Vault cho ứng dụng Java làm việc với HashiCorp Vault bằng các lời gọi API, nguồn thuộc tính của Spring hoặc mô hình Spring Data repository. Ba cách tiếp cận cùng dựa trên Vault server và chính sách phân quyền, nhưng khác nhau về **thời điểm đọc**, **mức trừu tượng**, **loại tác vụ** và **vòng đời bí mật**.

## Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích khi nào nên dùng `VaultOperations`/`VaultTemplate`, `VaultPropertySource`/Spring Cloud Vault, hoặc Vault Repositories.
2. Mô tả đường đi của một KV v2 secret từ **mount + key logic** đến lời gọi Java, `Environment` hoặc một entity repository.
3. Viết ví dụ đọc KV bằng API, khai báo `@VaultPropertySource`, cấu hình `vault://` và ánh xạ entity với `@Secret`/`@Id`.
4. Hiểu ranh giới của repository: CRUD trên KV, truy vấn dựa trên **ID**, liệt kê key, optimistic locking với KV v2; không xem repository như SQL database.
5. Xác định policy phù hợp, vòng đời token/lease, cache/refresh, nguy cơ lộ dữ liệu và lỗi cần xử lý ở từng cách.
6. Thiết kế một bộ kiểm thử tích hợp xác minh cả ba cách truy cập Vault với danh tính workload có quyền tối thiểu.

## 1. Bài toán: một Vault, ba kiểu tích hợp Java

Giả sử `orders-service` chạy bằng Spring Boot trên Kubernetes. Dịch vụ có ba nhu cầu:

- **Nhu cầu A:** Khi thanh toán, đọc API key theo tên đã biết và có thể gọi **Transit encrypt** cho dữ liệu nhạy cảm. Mã Java cần quyết định **khi nào gọi** và **xử lý kết quả**.
- **Nhu cầu B:** Khi khởi động, lấy vài property như client secret hoặc mật khẩu cấu hình của HTTP client. Bean Spring muốn sử dụng `@ConfigurationProperties` hoặc `Environment` mà không cần tự viết thao tác đọc Vault.
- **Nhu cầu C:** Một công cụ nội bộ quản lý các bộ credential của từng đối tác theo ID, ví dụ `acme`, `globex`. Công cụ cần CRUD và xử lý trường hợp hai người cùng sửa.

Ba tình huống này phù hợp với ba cách tiếp cận:

| Cách | Ý tưởng | Trường hợp thường hợp lý |
|---|---|---|
| **API trực tiếp** | Lập trình viên gọi `VaultOperations`/`VaultTemplate` hoặc API chuyên biệt theo engine | Đọc KV theo nghiệp vụ, yêu cầu credential động, Transit, PKI, thao tác có điều kiện |
| **PropertySource** | Đưa key/value từ Vault vào `Environment` để Spring bind cấu hình | Cấu hình nhạy cảm cần lúc startup và các property dùng bởi bean |
| **Vault repository** | Ánh xạ object Java vào bản ghi KV bằng `@Secret`, `@Id` và `CrudRepository` | Quản lý một tập hợp secret documents theo ID với CRUD và versioning có kiểm soát |

**Repository trong bài là Vault Repositories của Spring Vault**, không phải Git repository, không phải Spring Data JPA repository, và không phải một repository dùng để tìm tài liệu/source code. Nó dùng **KV secrets engine** làm backend lưu các document.

## 2. Chúng nằm ở đâu trong kiến trúc?

~~~mermaid
flowchart TB
    subgraph JVM["JVM: Spring Boot application"]
        B["Business service"]
        C["Bean cấu hình<br/>@ConfigurationProperties"]
        A["VaultOperations / VaultTemplate"]
        P["VaultPropertySource<br/>hoặc Spring Cloud Vault Config Data"]
        R["Spring Data Vault Repository<br/>@Secret + @Id"]
        ENV["Spring Environment"]
        B -->|"1. Gọi API"| A
        P -->|"2. Nạp key/value"| ENV
        ENV --> C
        B --> C
        B -->|"3. CRUD theo ID"| R
    end

    ID["Workload identity<br/>Kubernetes / AppRole / IAM"] --> AUTH["Vault auth method<br/>cấp Vault token"]
    A -->|"HTTPS"| AUTH
    P -->|"HTTPS"| AUTH
    R -->|"HTTPS"| AUTH

    subgraph SERVER["HashiCorp Vault server"]
        AUTH --> ACL["Policy: path + capability"]
        ACL --> KV["KV v1 / KV v2"]
        ACL --> OTHER["Database / Transit / PKI"]
    end
    A -->|"Tác vụ theo engine"| OTHER
    P -->|"Đọc context cấu hình"| KV
    R -->|"Đọc/ghi/list keyspace"| KV
~~~

Sơ đồ minh họa ba đường gọi độc lập ở phía Java nhưng **cùng một ranh giới tin cậy**: Vault server vẫn xác thực workload, kiểm tra Vault token và policy cho **mỗi yêu cầu**. Một `@Secret` annotation không cấp quyền ghi KV; một `@VaultPropertySource` không tạo mount KV; và một lệnh `vault.read(...)` không tự vượt qua policy.

### Cách đọc ranh giới trách nhiệm

1. **Ứng dụng Spring:** quyết định secret phục vụ nghiệp vụ nào, ai được gọi API nội bộ, khi nào nạp/làm mới và phải bảo vệ plaintext sau khi nhận.
2. **Spring Vault / Spring Cloud Vault:** ánh xạ Java API hoặc cấu hình thành request HTTPS, cung cấp auth/session integration, xử lý response và những cơ chế lifecycle được cấu hình.
3. **Vault server:** quản lý auth method, token, policy, KV/Database/Transit/PKI engines, audit, TTL/lease và tính sẵn sàng.
4. **Hệ thống đích:** xác thực credential tại PostgreSQL hoặc nhà cung cấp thanh toán; Vault đã đọc API key thành công không chứng minh key còn hiệu lực ở đối tác.

## 3. Bảng so sánh chi tiết ba cách

| Tiêu chí | API (`VaultOperations`) | PropertySource | Repository |
|---|---|---|---|
| Đơn vị làm việc | Một request/operation được code chọn | Các field trở thành property của `Environment` | Một entity được định danh bằng `@Id` |
| Thời điểm | Do Java code quyết định | Khi nguồn cấu hình được khởi tạo; cập nhật theo cơ chế riêng | Khi gọi `save`/`findById`/`delete` hoặc phương thức query |
| Độ tường minh | Cao: chỉ rõ mount, path, backend và thao tác | Trung bình: khai báo context và precedence | Cao ở domain model, thấp hơn ở HTTP paths do abstraction sinh |
| KV v2 | Chọn rõ `KV_2` khi dùng API KV | Tự nhận diện/đọc qua cấu hình tương ứng của framework | Hỗ trợ KV v2, phát hiện engine version lúc chạy |
| Engine khác | Có thể thao tác Database, Transit, PKI | Có thể đọc cấu hình/leased secrets theo hỗ trợ | Tập trung vào **KV**, không phải giao diện cho Transit/PKI |
| Cách lấy kết quả | `VaultResponse`, object map hoặc kiểu engine chuyên biệt | `Environment`, `@Value`, `@ConfigurationProperties` | Java entity và các method Spring Data |
| Đọc tập hợp | Tự viết logic list/get | Không nhằm query tập hợp document | `findAll`/truy vấn theo ID, có thể cần `list` + nhiều request |
| Ghi/xóa | Chủ động gọi API và kiểm soát semantics | Chủ yếu phục vụ đọc cấu hình | `save`/`delete` theo semantics KV |
| Khả năng version/CAS | Có thể dùng API KV v2 phù hợp | Thường lấy giá trị hiện hành cho config | `@Version` hỗ trợ optimistic locking khi dùng KV v2 |
| Chi phí ở runtime | Phụ thuộc tần suất gọi, cache, timeout | Thường tập trung ở nạp cấu hình; refresh tùy cơ chế | Nhiều call khi list/query/sort, tải cả document khi cần |
| Nguy cơ chính | Log response, gọi path sai, retry không phù hợp | Secret lan vào `Environment` và bean, thứ tự property | Quyền ghi/list rộng, ghi đè field, tưởng repository có query engine |

Không có một cách “cao cấp nhất” đúng cho mọi tình huống. Lựa chọn dựa trên **loại secret, quyền cần có, thời điểm sử dụng và tác động khi secret thay đổi**.

## 4. Cách 1 — Dùng API trực tiếp qua `VaultOperations`

`VaultOperations` là giao diện, `VaultTemplate` là triển khai thường dùng. Chúng cho Java quyền chủ động đọc/ghi/xóa một path, gọi các operation phù hợp với secrets engine và kiểm soát việc diễn giải response.

### 4.1. Đọc một KV v2 secret

Giả sử hạ tầng đã cấu hình:

~~~text
Vault endpoint: https://vault.internal.example:8200
Secrets mount: secret/                     (KV version 2)
Key logic:     apps/orders/payment
Field:         api-key
HTTP read:     GET /v1/secret/data/apps/orders/payment
Policy path:   secret/data/apps/orders/payment
~~~

Với `VaultOperations` bean đã cấu hình đúng endpoint, xác thực workload và TLS:

~~~java
import org.springframework.stereotype.Service;
import org.springframework.vault.core.VaultKeyValueOperations;
import org.springframework.vault.core.VaultKeyValueOperationsSupport.KeyValueBackend;
import org.springframework.vault.core.VaultOperations;
import org.springframework.vault.support.VaultResponse;

@Service
public class PaymentKeyGateway {

    private final VaultKeyValueOperations kv;

    public PaymentKeyGateway(VaultOperations vault) {
        this.kv = vault.opsForKeyValue("secret", KeyValueBackend.KV_2);
    }

    public String getApiKey() {
        VaultResponse response = kv.get("apps/orders/payment");
        if (response == null) {
            throw new IllegalStateException("Required payment secret is missing");
        }

        Object value = response.getRequiredData().get("api-key");
        if (!(value instanceof String apiKey) || apiKey.isBlank()) {
            throw new IllegalStateException("Required payment field is missing");
        }
        return apiKey;
    }
}
~~~

Lưu ý:

- `"secret"` là mount; `"apps/orders/payment"` là key logic. API KV cấp cao tự xử lý đoạn `data/` cần thiết của KV v2.
- `GET /v1/...` là URL HTTP; khi viết Vault policy, bỏ `/v1/`.
- `getApiKey()` có thể được gọi theo nhu cầu và tích hợp cache/refresh có chủ đích; ví dụ trên cố ý không cache.
- Không in `VaultResponse` ra log, không trả key trong API response và không lấy root token làm bằng chứng danh tính.

### 4.2. Khi API là lựa chọn rõ ràng

Transit encryption là ví dụ nổi bật: Java cần gửi plaintext đúng dạng payload rồi nhận ciphertext cho **mỗi** nghiệp vụ, không phải lấy một property cố định. Tương tự, việc cấp credential Database có lease, cấp certificate PKI, đọc KV theo phiên bản cụ thể hoặc thao tác trên nhiều mounts không nên bị ép thành một `@Value`.

Ví dụ gọi Transit ở mức API tổng quát:

~~~java
import java.nio.charset.StandardCharsets;
import java.util.Base64;
import java.util.Map;

import org.springframework.vault.core.VaultOperations;
import org.springframework.vault.support.VaultResponse;

class CustomerDataCrypto {
    private final VaultOperations vault;

    CustomerDataCrypto(VaultOperations vault) {
        this.vault = vault;
    }

    String encrypt(String plaintext) {
        String encoded = Base64.getEncoder().encodeToString(
            plaintext.getBytes(StandardCharsets.UTF_8));
        VaultResponse response = vault.write(
            "transit/encrypt/orders-pii", Map.of("plaintext", encoded));
        if (response == null) {
            throw new IllegalStateException("No Transit response");
        }
        Object value = response.getRequiredData().get("ciphertext");
        if (!(value instanceof String cipherText) || cipherText.isBlank()) {
            throw new IllegalStateException("No Transit ciphertext");
        }
        return cipherText;
    }
}
~~~

Ở đây Base64 chỉ là **encoding yêu cầu của Transit API**, không phải phép mã hóa bảo mật. Chính Vault server thực hiện encrypt bằng key có quyền sử dụng. `orders-service` cần capability phù hợp trên `transit/encrypt/orders-pii`; không cấp thêm decrypt nếu không cần. Secret/plaintext không được ghi log.

### 4.3. Rủi ro khi API do ứng dụng chủ động gọi

Code trực tiếp phải tự quyết định thời điểm lấy secret, giới hạn timeout/retry, cache, xử lý `403`/`404` và xử lý secret khi đổi. Với các API có side effect như cấp tài khoản DB động, một timeout có thể xảy ra **sau khi Vault đã xử lý yêu cầu**; retry mù quáng có thể cấp trùng credential. Cần hiểu semantics của từng endpoint.

## 5. Cách 2 — PropertySource: đưa secret vào cấu hình Spring

`PropertySource` là abstraction của Spring `Environment` cung cấp các giá trị cấu hình theo key. Với Vault, có **hai đường tích hợp liên quan nhưng không đồng nhất**:

1. **Spring Vault core:** dùng `VaultPropertySource` hoặc annotation `@VaultPropertySource` trong một Spring context đã có client Vault.
2. **Spring Cloud Vault:** dùng hệ thống Spring Boot Config Data, thường khai báo `spring.config.import: vault://` để tự chuẩn bị property sources trong quá trình khởi động.

Mục tiêu chung là **đọc dữ liệu cấu hình** để bind vào bean. Spring Cloud Vault mang cơ chế tự động hóa bootstrap và lựa chọn các config contexts theo tên ứng dụng/profile; không nên hiểu rằng Spring Vault core hoàn toàn không có hỗ trợ `PropertySource`.

### 5.1. `@VaultPropertySource` của Spring Vault core

Giả sử cùng KV v2 key logic `apps/orders/payment` chứa field `api-key`. Ta có thể đưa giá trị vào `Environment`:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.env.Environment;
import org.springframework.vault.annotation.VaultPropertySource;

@Configuration
@VaultPropertySource(
    value = "secret/apps/orders/payment",
    propertyNamePrefix = "payment."
)
class PaymentPropertiesConfiguration {

    @Bean
    PaymentClientSecret paymentClientSecret(Environment env) {
        return new PaymentClientSecret(
            env.getRequiredProperty("payment.api-key"));
    }
}

record PaymentClientSecret(String value) { }
~~~

Trong ví dụ:

- Annotation dùng path `secret/apps/orders/payment`, **không thêm `data/`** mặc dù engine là KV v2; Spring Vault xử lý backend path thông qua cơ chế tương ứng.
- Prefix `payment.` giúp key trong Spring thành `payment.api-key`.
- Một `VaultTemplate`/`VaultOperations` đã được cấu hình và sẵn sàng trong giai đoạn tạo property source. Phải bảo đảm **thứ tự khởi tạo**; nếu secret bắt buộc cho bean quá sớm thì đọc nó ở giai đoạn quá muộn sẽ thất bại.
- `PaymentClientSecret` nhận giá trị lúc bean được tạo. Nếu property source sau này được làm mới, bean đã giữ `String` cũ **không tự động thay giá trị**.

Spring Vault còn có lớp `org.springframework.vault.core.env.VaultPropertySource` để đăng ký bằng code với `ConfigurableEnvironment.getPropertySources()`, cho phép chọn thứ tự ưu tiên một cách tường minh. Ví dụ thêm bằng `addFirst` làm property từ Vault đứng trước những source khác có cùng key. Thứ tự này quan trọng khi file cấu hình, biến môi trường và Vault cùng khai báo `payment.api-key`.

### 5.2. Spring Cloud Vault với Config Data

Trong ứng dụng Spring Boot dùng Spring Cloud Vault tương thích, có thể dùng:

~~~yaml
spring:
  application:
    name: orders-service
  config:
    import: "vault://"
  cloud:
    vault:
      uri: "https://vault.internal.example:8200"
      authentication: KUBERNETES
      kubernetes:
        role: orders-role
      kv:
        enabled: true
        backend: secret
~~~

`vault://` nhập các nguồn cấu hình đã được bật theo quy tắc của Spring Cloud Vault; với KV mặc định, các context thường dựa trên `spring.application.name` và profile. Có thể dùng một **contextual location** như `vault:///secret/apps/orders/payment` để chỉ rõ một context, tùy phiên bản và thiết lập backend. Không đồng nhất khai báo hai kiểu mà chưa kiểm tra path nào thực sự được đọc.

Để ví dụ hoạt động, cần dependency tương thích, auth role Kubernetes đã cấu hình trong Vault, ServiceAccount token/trust relationship hợp lệ, CA trust của Vault và policy cho đúng context paths. Một property trong YAML **không tự tạo Vault server, secret mount hay role**.

### 5.3. Property precedence, refresh và độ nhạy cảm

| Vấn đề | Hệ quả |
|---|---|
| **Thứ tự PropertySource** | Giá trị trùng tên có thể bị source ưu tiên cao hơn che; cần khai báo và kiểm chứng precedence |
| **Startup dependency** | Vault không sẵn sàng hoặc auth thất bại có thể khiến config bắt buộc không đọc được và ứng dụng không khởi động |
| **Key không tồn tại** | Một số cơ chế có tùy chọn bỏ qua secret/context không tìm thấy; không được mặc định hiểu `404` luôn khiến startup fail |
| **Cấu hình đã bind vào bean** | Bean thường giữ bản snapshot; refresh property không đồng nghĩa HTTP client/datasource/connection pool tự được xây lại |
| **Secret hiện diện trong `Environment`** | Mã ứng dụng và công cụ chẩn đoán có quyền thích hợp có thể tiếp cận; cần giới hạn Actuator, debug dump và log |
| **Lease/rotation** | `@VaultPropertySource` có tùy chọn renewal/rotation; phải kiểm tra loại secret và cấu hình; KV version không phải lease credential |

Với secret động như Database credentials, `SecretLeaseContainer` và các property sources hiểu về lease có thể giúp yêu cầu/gia hạn/rotate theo cấu hình. **Việc đổi value trong `PropertySource` không tự bảo đảm HikariCP đã đổi username/password của connection pool**. Cần cơ chế ứng dụng nhận sự kiện, tạo pool mới, chuyển kết nối và xử lý TTL hợp lệ.

## 6. Cách 3 — Vault Repositories: ánh xạ entity và CRUD trên KV

Vault Repositories xây dựng trên mô hình **Spring Data repositories**. Thay vì viết `kv.get("...")` và `kv.put("...")` cho từng ID, ứng dụng mô tả một entity rồi gọi `CrudRepository`. Dữ liệu entity được ánh xạ thành **document JSON** trong KV. API này phù hợp với số lượng hữu hạn các bản ghi bí mật được quản trị theo định danh.

### 6.1. Một entity, một keyspace, một ID

Ví dụ công cụ nội bộ lưu credential cho các đối tác:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.Version;
import org.springframework.vault.repository.mapping.Secret;

@Secret(value = "partner-credentials", backend = "secret")
public class PartnerCredential {

    @Id
    String id;

    @Version
    long version;           // Dùng cho KV v2 optimistic locking.

    String apiKey;

    protected PartnerCredential() { }

    public PartnerCredential(String id, String apiKey) {
        this.id = id;
        this.apiKey = apiKey;
    }
}
~~~

~~~java
import java.util.List;
import org.springframework.data.repository.CrudRepository;

public interface PartnerCredentialRepository
        extends CrudRepository<PartnerCredential, String> {

    List<PartnerCredential> findByIdStartsWith(String prefix);
}
~~~

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.vault.repository.configuration.EnableVaultRepositories;

@Configuration
@EnableVaultRepositories(
    basePackageClasses = PartnerCredentialRepository.class)
class PartnerVaultRepositoryConfiguration {
    // Một VaultTemplate phù hợp phải đã được khai báo/cấu hình.
}
~~~

Ở đây:

- `@Secret` là annotation của **Spring Vault**: `org.springframework.vault.repository.mapping.Secret`. Giá trị `partner-credentials` xác định **keyspace**; `backend = "secret"` xác định mount KV ví dụ.
- `@Id` xác định ID của document; ID phải ánh xạ thành `String` theo cơ chế Vault Repositories.
- `@EnableVaultRepositories` bật cơ chế tạo implementation của các repository interface.
- Cần dependency `spring-vault-core` và những thành phần Spring Data phù hợp, gồm `spring-data-keyvalue` và `spring-data-commons` theo BOM/nhánh tương thích.
- `@Version` có ý nghĩa optimistic locking trên **KV v2**; không thể xem version này là TTL hoặc thời hạn API key ở nhà cung cấp.

Một thao tác có thể là:

~~~java
import java.util.List;
import org.springframework.stereotype.Service;

@Service
class PartnerCredentialAdmin {
    private final PartnerCredentialRepository repository;

    PartnerCredentialAdmin(PartnerCredentialRepository repository) {
        this.repository = repository;
    }

    void demonstrateWithFakeData() {
        // Chỉ dùng key giả trong test/demo.
        repository.save(
            new PartnerCredential("acme", "DEMO-NOT-A-REAL-KEY"));
        PartnerCredential loaded = repository.findById("acme").orElseThrow();
        List<PartnerCredential> matches =
            repository.findByIdStartsWith("ac");
        repository.deleteById("acme");
    }
}
~~~

Code minh họa constructor injection vào một service nội bộ; hai biến `loaded` và `matches` biểu diễn dữ liệu nhận về trong lúc demo. Không chạy quy trình tạo/xóa này trên secret thật khi chỉ muốn thử đọc. Trong ứng dụng thật, chỉ cấp quyền ghi cho đúng tác vụ quản trị và xử lý kết quả mà không làm lộ credential.

Nếu mount tên `secret` đang là KV v2 thì document có keyspace `partner-credentials` và ID `acme` tương ứng **key logic** `partner-credentials/acme`, với HTTP data path `secret/data/partner-credentials/acme`. Repository xác định đường dẫn dựa vào metadata/annotation và nhận diện engine version khi chạy; không tự gắn `data/` trong `@Secret`.

### 6.2. Repository không phải SQL query engine

Vault KV không có bộ máy thực thi truy vấn kiểu SQL. Vault Repositories hỗ trợ các phương thức query dựa trên **điều kiện ở ID**, ví dụ `findByIdStartsWith("ac")`. Việc query thường cần **liệt kê các ID dưới keyspace, lọc rồi đọc những document cần thiết**. Sorting/paging có thể phải thực hiện qua dữ liệu trong bộ nhớ, dẫn đến nhiều request và chi phí tăng khi keyspace lớn.

Vì vậy:

- Không mặc nhiên kỳ vọng `findByApiKey(...)` hoặc truy vấn theo thuộc tính bất kỳ như Spring Data JPA.
- `findAll()`, `count()`, query theo prefix và paging có thể cần capability `list` ở KV v2 metadata path.
- Danh sách ID và tên key bản thân cũng có thể nhạy cảm; không cấp `list` nếu ứng dụng chỉ đọc một ID cụ thể.
- Repository không phải nơi phù hợp để lưu hàng triệu đơn hàng/giao dịch rồi tìm kiếm, join, tổng hợp hoặc phân trang lớn.

### 6.3. Save, delete và optimistic locking

**Ghi entity:** repository có thể ghi **toàn bộ document** theo mapping. Nếu người khác lưu thêm field vào cùng KV key nhưng entity không ánh xạ field đó, một lần `save` có thể làm field không được ánh xạ biến mất trong phiên bản mới. Tránh nhiều ứng dụng ghi chồng cùng một document với các schema khác nhau.

**KV v2 version/CAS:** với `@Version`, Spring Vault có thể đưa phiên bản kỳ vọng vào cơ chế compare-and-set của KV v2. Nếu hai tiến trình đọc version N rồi cùng lưu, tiến trình thứ hai có thể nhận `OptimisticLockingFailureException` khi version đã đổi. Cần quyết định retry/merge theo dữ liệu thực; không tự động ghi đè bản mới.

**Xóa trong KV v2:** `CrudRepository.delete(...)` dùng thao tác **DELETE** theo semantics KV v2, thường là xóa mềm version hiện hành; nó **không** đồng nghĩa hủy vĩnh viễn nội dung phiên bản bằng operation `destroy`. Nếu nghiệp vụ đòi hỏi xóa dữ liệu không thể khôi phục, phải thiết kế quyền và quy trình riêng theo KV v2.

**Backend detection:** Vault Repositories và các property source có thể kiểm tra mount/version qua endpoint kiểu `sys/internal/ui/mounts/...`. Cần bảo đảm Vault server/policy cho phép cơ chế phát hiện mount phù hợp; chỉ kiểm tra quyền ở `secret/data/...` đôi khi chưa đủ để một abstraction tự khởi tạo thành công.

### 6.4. Vì sao repository không thay thế API Transit hay PKI?

`PartnerCredentialRepository.save(...)` lưu một document vào KV. Nó không mã hóa plaintext bằng Transit theo policy tách encrypt/decrypt, không yêu cầu Vault PKI ký CSR và không sinh credential Database theo lease. Nếu nghiệp vụ cần các thao tác này, dùng **API engine trực tiếp** hoặc abstraction engine chuyên biệt, ngay cả khi các metadata khác của nghiệp vụ được quản lý qua repository.

## 7. Một yêu cầu, ba cách truy cập: xem đúng đường dẫn

Giả sử quản trị viên đã mount `secret/` là KV v2 và tạo hai key logic:

~~~text
secret/                              # Mount KV v2
  apps/orders/payment                # Document cấu hình: api-key
  partner-credentials/acme           # Document quản trị: apiKey, ...
~~~

| Cách | Java/config input | HTTP/API path hệ thống có thể gọi | Vì sao khác nhau |
|---|---|---|---|
| API KV v2 | `opsForKeyValue("secret", KV_2).get("apps/orders/payment")` | `GET /v1/secret/data/apps/orders/payment` | Developer chọn rõ mount và key logic |
| `@VaultPropertySource` | `"secret/apps/orders/payment"` | Đọc key cấu hình qua KV v2 API tương ứng | Framework nhận context source và phơi bày các field thành property |
| Spring Cloud Vault contextual location | `vault:///secret/apps/orders/payment` | Đọc context cấu hình đã khai báo | Config Data xác định thời điểm nạp và precedence |
| Repository `findById("acme")` | `@Secret("partner-credentials")` và ID `acme` | `GET /v1/secret/data/partner-credentials/acme` | Key logic hình thành từ keyspace/ID |
| Repository `findByIdStartsWith("a")` | Query ID prefix | Có thể `LIST` metadata rồi `GET` document | KV không chạy truy vấn theo field như SQL |

Với KV v2, **đường dẫn policy để đọc dữ liệu** sử dụng `secret/data/...` và **đường dẫn policy để liệt kê** sử dụng `secret/metadata/...`. Mỗi abstraction che bớt phần ghép URL, nhưng **không thay đổi quy tắc quyền phía Vault**.

### Ví dụ policy đọc một secret cấu hình

~~~hcl
path "secret/data/apps/orders/payment" {
  capabilities = ["read"]
}
~~~

### Ví dụ quyền cho công cụ nội bộ quản lý repository

~~~hcl
# Công cụ quản trị chỉ làm việc trong keyspace partner-credentials.
path "secret/data/partner-credentials/*" {
  capabilities = ["create", "read", "update", "delete"]
}

# Chỉ cấp khi thật sự cần findAll/count/query theo ID prefix.
path "secret/metadata/partner-credentials" {
  capabilities = ["list"]
}
~~~

Các policy trên là ví dụ về **data/metadata paths** của KV v2. Một bản triển khai có thể cần thêm quyền/đường dẫn cho khám phá mount qua `sys/internal/ui/mounts/...` tùy phiên bản và cấu hình Vault server; xác minh bằng integration test với role thật. Không cấp quyền wildcard cho toàn bộ `secret/*` hoặc `sys/*` chỉ vì gặp lỗi khởi tạo repository.

## 8. Khi nào một secret trở thành cấu hình? Khi nào thành entity?

Giả sử API key đối tác nằm ở KV:

| Cách nhìn | Đối tượng trong Java | Ai quản lý vòng đời? |
|---|---|---|
| API trực tiếp | `String apiKey` được lấy tại điểm nghiệp vụ | Business service chọn refresh/cache và xử lý khi key bị rotate |
| PropertySource | `payment.api-key` trong `Environment`, bind vào bean | Infrastructure nạp property; app phải cập nhật bean/client khi giá trị đổi |
| Repository | `PartnerCredential` có ID, version, field bí mật | Công cụ quản trị gọi save/delete; chính sách ngoài Vault vẫn cần revoke API key ở nhà phát hành |

Trong cả ba cách, một **secret tĩnh** trong KV v2 không tự hết hiệu lực chỉ vì version đổi, và nội dung đã đi vào heap vẫn là plaintext mà ứng dụng cần bảo vệ. Đối với **secret động** như Database credentials, TTL/lease và cơ chế cấp lại ảnh hưởng thiết kế; trường hợp này API hoặc tích hợp PropertySource/lease chuyên biệt thường phù hợp hơn CRUD repository.

### Phân biệt ba loại thời hạn

1. **Vault token TTL:** thời gian workload được dùng token để gọi Vault; có thể renew/re-login nếu auth method và server cho phép.
2. **Secret lease TTL:** thời hạn credential động được engine phát hành (ví dụ Database); quản lý renew/reissue/revoke riêng và phối hợp connection pool.
3. **KV v2 version:** lịch sử của document KV; **không** quyết định tuổi thọ API key tại hệ thống đích.

`LifecycleAwareSessionManager` của Spring Vault xử lý vòng đời token khi phù hợp; `SecretLeaseContainer` quản lý một số leased secrets **được đăng ký**. Chúng không tự làm mới tất cả bean đã bind từ `PropertySource`, không tự cập nhật mọi connection pool và không làm repository trở thành một credential lease manager.

## 9. Quyết định lựa chọn: một cây lựa chọn thực dụng

~~~mermaid
flowchart TD
    START{"Ứng dụng cần làm gì với Vault?"}
    START -->|"Encrypt/decrypt, PKI, dynamic creds<br/>hoặc thao tác theo runtime input"| API["Dùng VaultOperations / VaultTemplate"]
    START -->|"Nạp property lúc cấu hình"| CONFIG{"Cần quản lý config<br/>qua Spring Boot?"}
    CONFIG -->|"Có, theo context/profile"| CLOUD["Spring Cloud Vault Config Data"]
    CONFIG -->|"Đã có VaultTemplate,<br/>cần vài property nguồn"| PS["Spring Vault @VaultPropertySource"]
    START -->|"CRUD tập hợp JSON documents<br/>theo ID"| REP{"Có thực sự cần list/query<br/>và nhiều document?"}
    REP -->|"Có, số lượng phù hợp"| REPOS["Vault Repository + Spring Data"]
    REP -->|"Không, chỉ vài key rõ tên"| API
    REPOS --> CHECK["Kiểm tra KV engine, ID queries,<br/>list policy, version và write semantics"]
~~~

Một số lựa chọn cụ thể:

| Yêu cầu | Ưu tiên | Điều cần kiểm tra |
|---|---|---|
| Chỉ đọc một secret khi xử lý job | API trực tiếp | Có cache không, lỗi runtime, quyền đúng path |
| Nạp mật khẩu SMTP khi Spring khởi động | PropertySource | Config precedence, thiếu secret, cách refresh/restart |
| Nạp cấu hình theo application/profile của Spring Boot | Spring Cloud Vault | Context paths, version tương thích, bootstrap auth |
| Công cụ nội bộ CRUD đối tác theo ID | Repository | Keyspace, quyền create/update/list, version CAS, tác động khi delete |
| Cần query theo email, status, createdAt | Database/index chuyên dụng, không phải Vault Repo | Vault query derivation chủ yếu theo ID, không có SQL engine |
| Cần Transit encrypt per request | API trực tiếp | Quyền encrypt, encode payload, timeout/không fallback plaintext |
| Nhận DB credential động và xoay pool | API/lease-aware integration | Token TTL khác lease TTL; thay connection pool đúng thời điểm |
| Nhận chứng chỉ mTLS từ PKI | API/PKI-aware lifecycle | Private key, TTL, nạp lại TLS context/cert |

## 10. Xử lý lỗi: đọc đúng tín hiệu của từng abstraction

| Triệu chứng | Cách có thể gặp | Nguyên nhân thường gặp | Hướng xử lý |
|---|---|---|---|
| HTTP 403 từ Vault | Cả ba | Token thiếu `read`/`list`/`update`; wrong KV v2 path; mount discovery bị chặn | Đối chiếu Vault audit/policy và API path thực; không thử lại bằng root token |
| HTTP 404/key thiếu | API, PropertySource, Repository | Sai mount, key, context, version đã xóa | Phân biệt required vs optional, không coi tất cả là thành công rỗng |
| Bean không được tạo khi startup | PropertySource, Cloud Vault | Nguồn config khởi tạo quá muộn, Vault unavailable, auth/TLS sai | Sửa bootstrap/context ordering, dependency và fail-fast policy |
| Property mới nhưng HTTP client vẫn dùng key cũ | PropertySource | Bean đã bind snapshot và cache cũ | Rebuild/reconfigure client theo chiến lược rotation |
| `findAll`/`count` bị từ chối | Repository | Thiếu `list` ở KV v2 metadata path | Cấp `list` có giới hạn nếu thật sự cần; nếu không, dùng `findById` |
| Save ghi đè field hoặc conflict | Repository | Full-document mapping, @Version CAS conflict | Dùng schema thống nhất, optimistic locking và xử lý conflict có kiểm soát |
| Repository không phát hiện mount | Repository, PropertySource | Cơ chế `sys/internal/ui/mounts/...` không khả dụng hoặc quyền không phù hợp | Kiểm tra behavior/ACL ở phiên bản Vault đang dùng |
| Token expired/revoked | Cả ba | TTL/renewability/auth method | Re-auth hoặc fail closed; phân biệt token với secret lease |
| Lease DB hết hạn | API/PropertySource dynamic credential | Không renew/reissue và chưa thay pool | Tạo credential mới, rollover connection pool, kiểm thử với DB thật |
| TLS handshake/timeout/5xx | Cả ba | CA, DNS, network, Vault HA, quá tải | Giữ xác minh TLS, timeout + retry giới hạn và theo tính idempotent |

**Không gộp mọi lỗi thành “secret không có”.** Một lỗi `403` là bị từ chối bởi Vault policy; timeout là sự cố hạ tầng; `404` có thể là key/context thiếu. Với secret bắt buộc để xác thực/mã hóa, ứng dụng cần có hành vi **fail closed**, không dùng một mật khẩu mặc định hoặc lưu plaintext.

### Error handling trong code

Khi dùng API trực tiếp, Java có thể phân loại lỗi tại điểm gọi bằng các exception phù hợp của Spring Vault/client transport. Khi dùng PropertySource, lỗi có thể xuất hiện **trước khi REST server khởi động**. Khi dùng Repository, lỗi có thể xuất hiện khi gọi `save`, `findById`, `findAll` và trong cơ chế mapping/versioning. Chính thời điểm lỗi khác nhau quyết định chỗ đặt retry, cảnh báo và fallback.

## 11. Hiệu năng và bảo mật: không đánh đổi một cách vô thức

### 11.1. Hiệu năng

- **API trực tiếp:** một lời gọi runtime có độ trễ mạng, auth/session và engine. Cache có thể giảm tải KV nhưng kéo dài thời gian dùng secret đã bị rotate.
- **PropertySource:** thuận tiện khi chỉ nạp một số config context lúc startup; nếu nạp quá nhiều key/context, startup có thể phụ thuộc mạnh vào Vault. Secret đã bind không tự đổi trong mọi bean.
- **Repository:** với query prefix/sort/page, Vault có thể cần list IDs và đọc nhiều document. Đây không phải cơ sở dữ liệu nghiệp vụ tối ưu cho tìm kiếm/analytics hoặc write throughput cao.

### 11.2. Bảo mật

- **Least privilege:** mỗi workload nhận role riêng; cấp đúng capability trên đúng API path. Đừng dùng một token chung để vừa đọc KV runtime vừa cấp quyền sửa/xóa mọi repository key.
- **PropertySource exposure:** `Environment`, `@ConfigurationProperties` và actuator/config dump có thể gián tiếp bộc lộ giá trị. Hạn chế endpoint quản trị và scrub log.
- **Repository exposure:** `findAll`/`count` có thể làm lộ nhiều key/ID; `save` có thể phá dữ liệu nếu schema khác nhau. Đừng expose một REST controller cho phép caller cung cấp arbitrary keyspace/ID rồi trả entity bí mật.
- **Transport:** Vault chạy qua HTTPS với kiểm tra CA và hostname. Không tắt TLS verification.
- **Vòng đời:** ghi KV v2 version mới không thu hồi API key cũ ở bên thứ ba; code phải phối hợp rotation và revoke tại hệ thống gốc.
- **Audit:** bật và vận hành Vault audit devices phù hợp; không ghi Vault token, secret value, private key, Transit plaintext vào log/trace/metrics.

## 12. Kiểm thử tích hợp cho ba cách trong cùng ứng dụng

Mock `VaultOperations` hữu ích để kiểm tra logic đọc field và xử lý lỗi, nhưng không chứng minh policy path, nhận diện KV v2, discovery mount hoặc repository query hoạt động. Hãy dùng Vault thật **chỉ dành cho test** (ví dụ container/dev server cô lập) và secret giả.

### 12.1. Chuẩn bị test

1. Khởi chạy Vault test với TLS/cấu hình phù hợp bài kiểm thử; bật KV v2 tại mount `secret`.
2. Tạo key `apps/orders/payment` chứa `api-key` giả; tạo keyspace `partner-credentials/` cho repository.
3. Thiết lập auth role/token có quyền tối thiểu và một role cố tình thiếu `read`/`list` để thử negative cases.
4. Đăng ký `VaultOperations` bean và cấu hình `@VaultPropertySource` hoặc Spring Cloud Vault tùy case; bật `@EnableVaultRepositories` cùng dependency phù hợp.
5. Bảo đảm log, test report và stack trace không in raw secret.

### 12.2. Ma trận tình huống

| Kiểm thử | Điều xác nhận |
|---|---|
| API KV v2 đọc đúng | `kv.get("apps/orders/payment")` nhận field `api-key`; path thực tương ứng `secret/data/...` |
| API sai path/thiếu quyền | 404/null và 403 được xử lý khác nhau, không retry vô hạn |
| PropertySource mapping | `payment.api-key` xuất hiện đúng trong `Environment`, precedence và prefix hợp lệ |
| Config Data import | `vault://` hoặc contextual path chọn đúng source; lỗi bootstrap/required secret được xử lý theo cấu hình |
| PropertySource refresh | Sau khi KV rotate, bean/HTTP client đang dùng key cũ có thực sự được cập nhật theo chiến lược đã thiết kế |
| Repository CRUD | `save`, `findById`, `deleteById` tác động lên keyspace đúng; không xóa nhầm key khác |
| Repository query | `findByIdStartsWith` hoạt động khi có `list`, bị từ chối hoặc thất bại có kiểm soát khi thiếu quyền |
| Repository CAS | Hai bản cùng version lưu cạnh tranh; `@Version` giúp phát hiện conflict trên KV v2 |
| Repository delete | Xác nhận delete mềm KV v2 khác destroy version vĩnh viễn |
| Mount detection | PropertySource/Repository xác định được KV engine khi auth/policy test phù hợp |
| Token hết hạn | Các đường API/config/repository phản ứng đúng với login token expired hoặc revoked |
| Vault không sẵn sàng | Startup/runtime có timeout, retry giới hạn và không fallback lộ dữ liệu |

### 12.3. Test nhỏ mô tả mục tiêu, không chứa credential thật

~~~java
// Pseudocode cho integration test trên Vault test instance:
String value = paymentKeyGateway.getApiKey();
assertThat(value).isEqualTo("demo-key");

assertThat(environment.getProperty("payment.api-key"))
    .isEqualTo("demo-key");

PartnerCredential saved =
    partnerCredentialRepository.save(
        new PartnerCredential("acme", "fake-key"));

assertThat(partnerCredentialRepository.findById("acme"))
    .isPresent();
~~~

Đây là khung assertion minh họa; cần dựng Spring context, Vault test instance, policy, import/config và bean đầy đủ. Không chạy mã trong bài lý thuyết hoặc xem bốn assertion này là bằng chứng test integration đã pass.

## 13. Bài tập tình huống và câu hỏi tự kiểm tra

### Tình huống 1 — Có một API key, nên dùng repository?

Một service chỉ cần đọc `secret/apps/orders/payment` khi gọi cổng thanh toán. Bạn không cần tạo, query hay sửa một danh sách key theo ID. **API KV trực tiếp hoặc PropertySource** là lựa chọn đơn giản, tùy thời điểm đọc. Thêm Vault Repository chỉ tăng abstraction và có thể phát sinh yêu cầu discovery/list không cần thiết.

### Tình huống 2 — Nhiều đối tác nhưng cần truy vấn theo ngày tạo

Công cụ quản trị chứa hàng nghìn partner credentials và cần tìm theo `createdAt`, `status`, nhiều tiêu chí và phân trang. Vault repository hỗ trợ query dựa trên ID, không phải SQL/Elastic search. **Một cơ sở dữ liệu có index** có thể giữ metadata không nhạy cảm để tra cứu, trong khi secret thực vẫn ở Vault theo key, với policy và lifecycle riêng.

### Tình huống 3 — `@VaultPropertySource` chạy được nhưng datasource vẫn đăng nhập sai

KV có version mới, property source đã nhận giá trị, nhưng datasource được khởi tạo trước đó còn dùng password cũ. Giải pháp không phải tăng quyền đọc Vault: cần thiết kế refresh/rebuild datasource và thay connection pool hợp lệ. Nếu credential động có lease, cần theo dõi TTL/renew/reissue riêng.

### Tình huống 4 — Repository `deleteById` đã gọi, yêu cầu xóa vĩnh viễn chưa đạt

Với KV v2, repository `deleteById` không hủy vĩnh viễn các version cũ. Nếu quy định bắt buộc xóa vật lý, cần operation destroy hoặc quản lý retention phù hợp, quyền quản trị riêng, kế hoạch backup/audit và kiểm chứng kết quả. Không gọi `deleteById` rồi suy luận dữ liệu đã không thể khôi phục.

### Câu hỏi tự kiểm tra

1. Khác biệt về **thời điểm gọi Vault** giữa `kv.get(...)`, `@VaultPropertySource` và `repository.findById(...)` là gì?
2. Spring Vault core có `@VaultPropertySource` không, hay bắt buộc phải dùng Spring Cloud Vault?
3. Với KV v2 mount `secret` và key logic `apps/orders/payment`, nêu API path đọc và policy path.
4. Vì sao `@Secret`/`@Id` và `CrudRepository` không biến Vault thành một cơ sở dữ liệu có thể query bất kỳ field?
5. Vì sao `findByIdStartsWith` có thể cần `list`, còn `findById("acme")` không nhất thiết cần?
6. `@Version` giúp giải quyết vấn đề gì? Nó khác TTL và lease ở đâu?
7. Tại sao `CrudRepository.deleteById` với KV v2 không tương đương destroy vĩnh viễn?
8. Khi PropertySource đã đổi password nhưng HikariCP vẫn dùng mật khẩu cũ, phần nào phải được sửa?
9. Vì sao Transit encrypt theo input từng request phù hợp với API trực tiếp hơn `@Value` hoặc repository?
10. Những test nào phải chạy với Vault thật để kiểm chứng mount detection, policy và optimistic locking?

## 14. Ghi nhớ

Ba cách tích hợp giải quyết **ba yêu cầu khác nhau**:

- **API:** thao tác cụ thể ở thời điểm Java quyết định; đầy đủ nhất khi cần KV/Database/Transit/PKI.
- **PropertySource:** chuyển secret thành cấu hình Spring; giảm code đọc nhưng phải kiểm soát bootstrap, precedence, refresh và rò rỉ cấu hình.
- **Repository:** CRUD document KV theo ID; thuận tiện cho công cụ quản trị secret có cấu trúc, nhưng phụ thuộc metadata/list/engine version và không thay thế database nghiệp vụ.

Các lớp tiện ích trên **không thay Vault server**, **không tự cấp policy**, **không biến KV version thành TTL** và **không tự bảo vệ plaintext sau khi đã được đọc vào JVM**. Lựa chọn đúng là lựa chọn làm rõ chủ thể được phép truy cập, thao tác thực tế, vòng đời thay đổi và hậu quả khi Vault từ chối hoặc gián đoạn.

## Tài liệu chính thức

- [Spring Vault — Reference Documentation](https://docs.spring.io/spring-vault/reference/)
- [Spring Vault — VaultTemplate](https://docs.spring.io/spring-vault/reference/vault/imperative-template.html)
- [Spring Vault — Property Sources](https://docs.spring.io/spring-vault/reference/vault/propertysource.html)
- [Spring Vault — Vault Repositories](https://docs.spring.io/spring-vault/reference/vault/vault-repositories.html)
- [Spring Vault — Credentials Rotation](https://docs.spring.io/spring-vault/reference/vault/credential-rotation.html)
- [Spring Cloud Vault — ConfigData API](https://docs.spring.io/spring-cloud-vault/reference/config-data.html)
- [Spring Cloud Vault — Reference Documentation](https://docs.spring.io/spring-cloud-vault/reference/)
- [HashiCorp Vault — KV v2 HTTP API](https://developer.hashicorp.com/vault/api-docs/secret/kv/kv-v2)
- [HashiCorp Vault — ACL Policies](https://developer.hashicorp.com/vault/docs/concepts/policies)
- [Spring Data Commons — Working with Repositories](https://docs.spring.io/spring-data/commons/reference/repositories.html)

> **Lưu ý phiên bản và phạm vi:** Các API repository, annotation mapping, xử lý discovery mount, Config Data và lifecycle chịu ảnh hưởng của phiên bản Spring Vault/Spring Cloud Vault và HashiCorp Vault thực tế. Mã trong bài là ví dụ minh họa bằng dữ liệu giả; để dùng trong production phải cấu hình auth theo workload, TLS, role/policy, kiểm tra ma trận phụ thuộc và chạy integration test cho đúng backend.
