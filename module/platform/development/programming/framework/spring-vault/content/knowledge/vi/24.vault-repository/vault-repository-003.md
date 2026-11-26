# Kích hoạt bằng @EnableVaultRepositories

## 1. Vấn đề: vì sao cần Vault Repository?

Trong ứng dụng Java, `VaultTemplate` có thể đọc/ghi các secret trên HashiCorp Vault bằng đường dẫn cụ thể. Khi nhiều phần của ứng dụng cần làm việc với những đối tượng có ID cố định, lập trình viên thường viết lại mã ánh xạ từ JSON sang Java, kiểm tra giá trị trả về và thực hiện CRUD.

**Spring Vault Repository** áp dụng mô hình **Spring Data Repository** lên **KV secrets engine** của Vault: lập trình viên khai báo một interface như `CrudRepository<PaymentCredential, String>`, và Spring tạo implementation thông qua repository proxy. Annotation **`@EnableVaultRepositories`** kích hoạt cơ chế phát hiện các interface repository đó.

Bài thuộc chương **Vault Repository** của module **SPRING_VAULT**. Module bao quát ứng dụng Java truy cập Vault bằng `VaultTemplate`, xác thực theo workload và ACL, KV secrets, token/lease, Transit encryption, PKI, xử lý lỗi, giám sát và kiểm thử tích hợp. Ở đây, phạm vi chính là **cách bật repository trong Spring context, wiring đúng Vault client và kiểm tra repository đã hoạt động**.

Học xong, bạn cần:

1. Hiểu `@EnableVaultRepositories` kích hoạt điều gì, không kích hoạt điều gì.
2. Khai báo domain `@Secret`, trường `@Id` và interface kế thừa `CrudRepository`.
3. Chọn đúng package để scan qua `basePackageClasses` hoặc `basePackages`.
4. Cung cấp `VaultOperations` / `VaultTemplate` và dependencies tương thích.
5. Đọc/ghi/xóa entity trên KV v2 theo policy tối thiểu, phân biệt quyền `read`, `create`, `update`, `delete`, `list`.
6. Chẩn đoán lỗi repository bean không xuất hiện, đường dẫn KV sai, quyền thiếu hoặc secret bị soft-delete.

> **Ranh giới:** repository của Spring Vault phục vụ **KV secrets**. Nó không tự biến Transit, PKI, AppRole hoặc dynamic database credentials thành các entity CRUD có khả năng query như SQL.

## 2. Repository hoạt động theo chuỗi nào?

~~~mermaid
flowchart TD
    A["Spring @Configuration có @EnableVaultRepositories"] --> B["VaultRepositoriesRegistrar"]
    B --> C["Quét interface repository theo base package"]
    C --> D["Tạo repository proxy"]
    D --> E["Dùng KeyValueOperations / VaultKeyValueTemplate"]
    E --> F["VaultOperations / VaultTemplate"]
    F --> G["Vault HTTP API và ACL"]
    G --> H["KV secrets engine v1/v2"]
    I["@Secret và @Id của entity"] --> E
    J["Workload authentication và Vault token"] --> F
~~~

Các thành phần và trách nhiệm:

| Thành phần | Vai trò |
| --- | --- |
| `@EnableVaultRepositories` | Bật repository scanning và đăng ký cơ sở hạ tầng tạo proxy |
| `VaultRepositoriesRegistrar` | Tích hợp cấu hình repository với Spring bean registry |
| `CrudRepository<Entity, String>` | Giao diện ứng dụng dùng để `save`, `findById`, `deleteById` và thao tác CRUD |
| `@Secret` | Đánh dấu aggregate root và định nghĩa keyspace + KV mount |
| `@Id` | Chỉ trường định danh; Vault Repository dùng **String ID** |
| `VaultKeyValueTemplate` | `KeyValueOperations` dành cho repository, ánh xạ và thao tác KV |
| `VaultTemplate` | Client thực hiện lời gọi Vault bằng token workload |
| Vault KV | Lưu giá trị và thực thi policy trên API path |

**Annotation chỉ đăng ký hạ tầng trong Spring.** Nó **không** tự bật `secret/` KV engine, tự cấu hình auth method, cấp Vault token, sửa ACL, tạo entity trong Vault hoặc chấp nhận mọi phương thức truy vấn tùy ý.

## 3. Điều kiện chuẩn bị

Bạn cần:

- JDK và Spring Boot tương thích phiên bản Spring Vault được chọn.
- Dependency `spring-vault-core` và Spring Data KeyValue, với phiên bản do BOM phù hợp quản lý.
- Một `VaultTemplate` đã được tạo từ Vault endpoint, TLS và `ClientAuthentication`.
- KV secrets engine v1 hoặc v2 ở mount dự kiến; Vault Repository hỗ trợ KV v2 từ Spring Vault 2.4 và có thể xác định phiên bản mount lúc chạy.
- Vault token của workload có quyền đúng **data path** và, nếu dùng `count`, `findAll` hay truy vấn theo ID prefix, **metadata/list path** đối với KV v2.
- Package chứa repository interface phải nằm trong phạm vi được `@EnableVaultRepositories` quét.

Ví dụ dependencies **khi dự án đã có BOM quản lý phiên bản**:

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

`spring-data-keyvalue` kéo theo nhiều thành phần Spring Data Commons; không bỏ dependency này rồi kỳ vọng chỉ có `spring-vault-core` là đủ cho repository abstraction. Nếu không dùng BOM, phải khai báo **các phiên bản tương thích** theo hướng dẫn Spring Vault/Spring Data của bản đang triển khai; không lấy ngẫu nhiên phiên bản mới nhất của từng thư viện để ghép lại.

## 4. Ví dụ domain: một secret có ID rõ ràng

Để tránh thao tác với dữ liệu thật, dùng credential giả cho bài học. Domain lưu trong KV mount `secret/` với keyspace `payment-credentials`:

~~~java
package com.example.payment.vault.domain;

import org.springframework.data.annotation.Id;
import org.springframework.vault.repository.mapping.Secret;

@Secret(value = "payment-credentials", backend = "secret")
public class PaymentCredential {

    @Id
    private String id;

    private String clientId;
    private String apiKey;

    protected PaymentCredential() {
        // Dành cho mapper.
    }

    public PaymentCredential(String id, String clientId, String apiKey) {
        this.id = id;
        this.clientId = clientId;
        this.apiKey = apiKey;
    }

    public String getId() {
        return id;
    }

    public String getClientId() {
        return clientId;
    }

    public String getApiKey() {
        return apiKey;
    }

    // Không sinh toString chứa apiKey.
}
~~~

Lưu ý:

- `@Secret` ở **lớp**, không phải `@EnableVaultRepositories`. `value` là **keyspace** và `backend` là tên KV mount.
- `@Id` thuộc `org.springframework.data.annotation.Id`. ID của Vault Repository phải là `String`; không dùng JPA `@Id` rồi mong hai hệ thống tương đương.
- Một entity có ID `lab-01` được lưu dưới key logic **`payment-credentials/lab-01`** ở mount **`secret/`**.
- Mapper xử lý dữ liệu JSON; với domain phức tạp, cần kiểm tra cách serialize nested object, metadata `_class` và tương thích Java constructor.
- Ví dụ có `apiKey` để minh họa secret, nhưng không log toàn bộ entity hay đưa getter secret trực tiếp vào API công khai.

## 5. Interface repository: khai báo thay vì tự viết CRUD

~~~java
package com.example.payment.vault.repository;

import java.util.List;

import org.springframework.data.repository.CrudRepository;
import com.example.payment.vault.domain.PaymentCredential;

public interface PaymentCredentialRepository
        extends CrudRepository<PaymentCredential, String> {

    // Vault hỗ trợ điều kiện truy vấn trên trường ID.
    List<PaymentCredential> findByIdStartsWith(String prefix);
}
~~~

Repository interface **không cần annotation `@Repository`** để được Spring phát hiện khi `@EnableVaultRepositories` quét đúng package. Spring sẽ tạo proxy thực thi các thao tác của `CrudRepository`; ứng dụng không cần tự viết lớp `PaymentCredentialRepositoryImpl` cho CRUD thông thường.

Đừng suy từ `findByIdStartsWith` rằng Vault có một hệ thống truy vấn tương đương database quan hệ. Khoá truy vấn được hỗ trợ chủ yếu xoay quanh **ID**; việc tìm theo `apiKey` hoặc các field tùy ý không có chỉ mục/query engine như SQL. Một số thao tác query phải list IDs rồi đọc các secret cần thiết, có thể tốn I/O và đòi quyền `list`.

## 6. Kích hoạt bằng `@EnableVaultRepositories`: cách cấu hình tối thiểu

Đây là phần cốt lõi của bài học. Đặt annotation trên một lớp `@Configuration` được Spring nạp vào context:

~~~java
package com.example.payment.config;

import java.net.URI;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.vault.authentication.TokenAuthentication;
import org.springframework.vault.client.VaultEndpoint;
import org.springframework.vault.core.VaultTemplate;
import org.springframework.vault.repository.configuration.EnableVaultRepositories;

import com.example.payment.vault.repository.PaymentCredentialRepository;

@Configuration
@EnableVaultRepositories(
        basePackageClasses = PaymentCredentialRepository.class
)
public class VaultRepositoryConfiguration {

    @Bean("vaultTemplate")
    VaultTemplate vaultTemplate() {
        String address = required("VAULT_ADDR");
        String token = required("LAB_VAULT_TOKEN");

        return new VaultTemplate(
                VaultEndpoint.from(URI.create(address)),
                new TokenAuthentication(token)
        );
    }

    private static String required(String name) {
        String value = System.getenv(name);
        if (value == null || value.isBlank()) {
            throw new IllegalStateException(name + " is required");
        }
        return value;
    }
}
~~~

Trong ví dụ:

1. `@Configuration` cho Spring biết đây là lớp khai báo bean và cấu hình.
2. `@EnableVaultRepositories` import `VaultRepositoriesRegistrar` để đăng ký các repository nằm trong package cần quét.
3. `basePackageClasses = PaymentCredentialRepository.class` **xác định package chứa interface** theo kiểu type-safe, tránh hardcode tên package thành chuỗi.
4. `@Bean("vaultTemplate")` cung cấp `VaultOperations` mặc định mà repository infrastructure cần. Tên `vaultTemplate` khớp giá trị mặc định của thuộc tính `vaultTemplateRef`.
5. Hạ tầng Vault Repository sử dụng `VaultKeyValueTemplate`/`KeyValueOperations` để ánh xạ `PaymentCredential` và gọi Vault thông qua `VaultTemplate`.

**Đây chỉ là cấu hình phòng lab:** `LAB_VAULT_TOKEN` đại diện token ngắn hạn do operator tạo, không dùng root token hoặc credential thực. Ở production, dùng workload authentication, session token renewal phù hợp, Vault TLS/CA tin cậy và giới hạn policy theo từng ứng dụng. Nếu Spring Cloud Vault hoặc `AbstractVaultConfiguration` đã cung cấp bean `VaultTemplate`, **không tạo thêm bean trùng tên**; thay vào đó, tái sử dụng bean đang được quản lý.

### Tại sao phải nạp được cấu hình này vào context?

`@EnableVaultRepositories` phải nằm trên lớp `@Configuration` mà Spring thực sự phát hiện/import. Một lớp nằm ngoài `@SpringBootApplication` component scan và không được `@Import` thì annotation có đúng cũng **không có tác dụng**.

Ví dụ nếu `PaymentApplication` ở `com.example.payment`, còn `VaultRepositoryConfiguration` ở `com.example.payment.config`, Spring Boot thường scan được cấu hình. Nếu cấu hình nằm ở một package khác ngoài phạm vi scan, có thể import tường minh:

~~~java
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Import;
import com.example.payment.config.VaultRepositoryConfiguration;

@SpringBootApplication
@Import(VaultRepositoryConfiguration.class)
public class PaymentApplication {
}
~~~

Không nhân đôi đăng ký cấu hình bằng nhiều cách cùng lúc khi không cần thiết; ứng dụng có nhiều `@EnableVaultRepositories` quét trùng interface có thể gây bean definition conflict.

## 7. Các thuộc tính quan trọng của annotation

`@EnableVaultRepositories` không có duy nhất một công tắc bật/tắt. Nó còn xác định cách quét repository và các bean mà repository sẽ sử dụng.

| Thuộc tính | Mặc định / ý nghĩa | Khi nào dùng? |
| --- | --- | --- |
| Không chỉ định package | Quét package của lớp được gắn annotation | Dự án nhỏ, interface nằm gần lớp cấu hình |
| `value` | Alias của `basePackages` | Viết ngắn `@EnableVaultRepositories("com.example.payment.vault.repository")` |
| `basePackages` | Danh sách package dạng chuỗi | Repository nằm ở package khác |
| `basePackageClasses` | Lấy package từ class/interface | Ưu tiên khi muốn refactor an toàn |
| `vaultTemplateRef` | `"vaultTemplate"` | Dùng một `VaultOperations` bean tên khác |
| `keyValueTemplateRef` | `"vaultKeyValueTemplate"` | Dùng một `KeyValueOperations` tùy biến/đã đặt tên |
| `repositoryImplementationPostfix` | `"Impl"` | Đổi hậu tố lớp triển khai fragment custom |
| `considerNestedRepositories` | `false` | Chỉ cần khi interface repository là nested interface |
| `includeFilters`, `excludeFilters` | Bộ lọc loại repository candidates | Hạn chế scan nếu chung package nhiều repository |
| `repositoryFactoryBeanClass` | `VaultRepositoryFactoryBean` | Tùy chỉnh hạ tầng repository chuyên sâu |

**Lựa chọn khuyến nghị để tránh quét nhầm**:

~~~java
@EnableVaultRepositories(
    basePackageClasses = PaymentCredentialRepository.class
)
~~~

Annotation này quét **package của lớp truyền vào** cùng phạm vi package con phù hợp, **không có nghĩa** chỉ đăng ký đúng một interface truyền vào. Nếu package còn chứa repository khác, chúng cũng có thể được phát hiện.

So sánh:

~~~java
// Quét theo chuỗi: dễ sai khi đổi package mà quên sửa.
@EnableVaultRepositories(
    basePackages = "com.example.payment.vault.repository"
)

// Quét package của marker/interface: compiler giúp phát hiện đổi tên.
@EnableVaultRepositories(
    basePackageClasses = PaymentCredentialRepository.class
)

// Không cấu hình: chỉ dựa vào package của lớp cấu hình.
@EnableVaultRepositories
~~~

Nếu bạn đặt cấu hình ở `com.example.payment.config` nhưng repository ở `com.example.payment.vault.repository`, lựa chọn cuối **không nhất thiết tìm được repository**, vì package mặc định của annotation là `com.example.payment.config`. Đừng nhầm với cơ chế component scan mặc định của Spring Boot: đó là **hai phạm vi cấu hình cần xem xét riêng**.

### `vaultTemplateRef` và `keyValueTemplateRef` khác nhau

`vaultTemplateRef` trỏ đến bean hiện thực `VaultOperations`, tức lớp **gọi HTTP Vault** và quản lý xác thực. `keyValueTemplateRef` trỏ đến bean `KeyValueOperations` sử dụng cho mapping/repository. Không dùng một tên bean `VaultTemplate` để điền vào `keyValueTemplateRef`: `VaultTemplate` và `VaultKeyValueTemplate` khác vai trò, dù tên gần giống nhau.

Ví dụ khi ứng dụng đã có `VaultOperations` tên `paymentVaultTemplate`:

~~~java
@Configuration
@EnableVaultRepositories(
    basePackageClasses = PaymentCredentialRepository.class,
    vaultTemplateRef = "paymentVaultTemplate"
)
class PaymentVaultRepositoryConfig {
    // Bean paymentVaultTemplate được khai báo ở một cấu hình khác.
}
~~~

Nếu thay tên `keyValueTemplateRef` theo ý muốn, bạn phải bảo đảm **một `KeyValueOperations` bean tương ứng thực sự tồn tại** và được wiring với Vault client/mapping context đúng. Sai bean name hoặc bean type có thể làm ứng dụng fail khi khởi tạo repository.

## 8. Repository được sử dụng ra sao sau khi kích hoạt?

Khi Spring context khởi động thành công, có thể **constructor-inject** `PaymentCredentialRepository` như một dependency bình thường:

~~~java
package com.example.payment.service;

import org.springframework.stereotype.Service;
import com.example.payment.vault.domain.PaymentCredential;
import com.example.payment.vault.repository.PaymentCredentialRepository;

@Service
public class PaymentCredentialService {

    private final PaymentCredentialRepository repository;

    public PaymentCredentialService(PaymentCredentialRepository repository) {
        this.repository = repository;
    }

    public boolean exists(String id) {
        return repository.findById(id).isPresent();
    }

    public PaymentCredential createTestOnly() {
        PaymentCredential credential = new PaymentCredential(
                "lab-01",
                "client-for-sandbox",
                "LAB_DUMMY_KEY_ONLY"
        );
        return repository.save(credential);
    }
}
~~~

`exists("lab-01")` trả boolean để minh họa kiểm tra một ID; dữ liệu domain có `apiKey` vẫn được giữ ở backend, **không** nên expose trực tiếp `PaymentCredential` qua REST hoặc log object. `save(...)` là **thao tác ghi** tới Vault khi phương thức được gọi, khác với `ReactiveVaultTemplate` vốn trả publisher cold.

Không tạo một `PaymentCredentialRepository` bằng `new`: đó là **interface**. Nếu Spring không tạo proxy, việc injection sẽ thất bại, giúp phát hiện cấu hình scan sai ngay khi khởi động.

## 9. Ánh xạ đường dẫn repository sang Vault KV v2

Khi dùng domain:

~~~java
@Secret(value = "payment-credentials", backend = "secret")
public class PaymentCredential {
    @Id String id;
}
~~~

và ID `lab-01`, cách nhìn đường dẫn là:

| Lớp | Ví dụ |
| --- | --- |
| Mount | `secret/` |
| Keyspace | `payment-credentials` |
| ID | `lab-01` |
| Key logic | `payment-credentials/lab-01` |
| Vault CLI | `vault kv get -mount=secret payment-credentials/lab-01` |
| KV v2 HTTP read | `GET /v1/secret/data/payment-credentials/lab-01` |
| KV v2 HTTP list keyspace | `LIST /v1/secret/metadata/payment-credentials` |

Tầng Repository và KV adapter xử lý sự khác nhau giữa KV v1/KV v2; không cần thêm `data/` vào `@Secret(value=...)`. Nếu thêm nhầm `data/` vào keyspace, dữ liệu có thể được đọc/ghi sang **một path logic khác** so với điều bạn dự định.

**Quan trọng về ACL:** người gọi Spring Vault cần token có quyền trên **API path thực tế**. Với KV v2, policy cho đọc/ghi dữ liệu khác với policy cho list metadata. Không thể lấy một policy `read` đơn thuần trên `secret/payment-credentials/*` rồi mặc định nó bảo vệ đúng API path của KV v2.

### Các thao tác CRUD tương ứng

| Repository method | Hành vi KV điển hình | Quyền / lưu ý |
| --- | --- | --- |
| `save(entity)` | Ghi JSON ở key `keyspace/id` | `create` khi tạo key mới, `update` khi thay giá trị |
| `findById(id)` | Đọc nội dung một key | `read` trên `secret/data/...` |
| `existsById(id)` | Kiểm tra có key tương ứng hay không | Có thể cần quyền đọc/kiểm tra path tùy implementation |
| `deleteById(id)` | Xóa secret/key theo semantics của engine | `delete` trên `secret/data/...`; KV v2 mặc định là soft delete |
| `count()`, `findAll()` | Liệt kê IDs và có thể đọc các secret | `list` trên `secret/metadata/keyspace`, `read` khi cần nội dung |
| `findByIdStartsWith(prefix)` | Liệt kê IDs, lọc theo tiền tố ID | Không phải SQL index, có chi phí list và fetch |

Với KV v2, **`delete` không đồng nghĩa hủy vĩnh viễn mọi phiên bản secret**. Spring Vault lưu ý các thao tác xóa repository sử dụng KV v2 `DELETE`, không tự gọi `destroy`. Muốn hủy version hoặc metadata vĩnh viễn phải thiết kế quy trình cấp quyền riêng, không dùng `CrudRepository.delete(...)` như một bảo đảm xóa vật lý.

### Vai trò của `@Version` trên KV v2

Nếu entity có một field số được đánh dấu `@Version` (Spring Data), Spring Vault có thể dùng **CAS** (compare-and-set) của KV v2 để thực hiện optimistic locking. Hai tiến trình cùng đọc một version rồi cùng ghi: một bên có thể gặp `OptimisticLockingFailureException` thay vì ghi đè mất cập nhật của bên khác.

Đây là tính năng riêng của KV v2 và cần test theo phiên bản thư viện. Chỉ gắn `@Version` không biến Vault Repository thành transaction database; các thao tác nhiều key không tự trở thành một giao dịch ACID.

## 10. Policy tối thiểu cho từng kiểu kiểm thử

Trong một Vault dev/test dùng KV v2 mount `secret/`, nếu demo cần `save`, `findById`, `deleteById` và `findAll`, operator có thể cấp policy giới hạn dưới keyspace lab:

~~~hcl
# Policy thử nghiệm, không dùng trực tiếp cho production.
path "secret/data/payment-credentials/*" {
  capabilities = ["create", "read", "update", "delete"]
}

path "secret/metadata/payment-credentials" {
  capabilities = ["list"]
}
~~~

Đối với ứng dụng thật chỉ cần đọc một ID, **thu hẹp** quyền:

~~~hcl
path "secret/data/payment-credentials/lab-01" {
  capabilities = ["read"]
}
~~~

Một token chỉ có `read` trên key cụ thể sẽ không có quyền `save`, `delete`, cũng không nhất thiết `findAll`/đếm vì thiếu `list`. Dùng policy riêng cho **test writer** và **production reader**, tránh cấp một policy CRUD rộng để “cứ cho chạy”.

Spring Vault Repository dùng endpoint nội bộ của Vault để xác định KV mount, thông thường liên quan `sys/internal/ui/mounts/...`. Nếu repository không thể khởi tạo hoặc mọi thao tác báo thiếu quyền dù đã cho phép data path, kiểm tra khả năng **mount discovery** theo tài liệu Vault và policy thực tế. Không vội thêm wildcard `path "sys/*"` hay dùng root token; hãy xác định chính xác endpoint cần truy cập và yêu cầu bảo mật của foundation.

## 11. Bài lab: bật repository và kiểm tra một entity thật

Các ví dụ lệnh dùng Bash trên **Vault dev server**. Cần Vault CLI, một ứng dụng Spring Boot tương thích với các đoạn Java ở trên và package được cấu hình đúng. Không dùng credential thật.

### Bước 1 — Chạy Vault dev và kiểm tra KV v2

Terminal thứ nhất:

~~~bash
vault server -dev -dev-root-token-id=root
~~~

Terminal thứ hai:

~~~bash
export VAULT_ADDR="http://127.0.0.1:8200"
export VAULT_TOKEN="root"

vault status
vault secrets list -detailed
~~~

Vault dev mặc định thường có mount `secret/` dạng KV v2. **Chỉ khi chưa có mount**, mới tạo bằng:

~~~bash
vault secrets enable -path=secret -version=2 kv
~~~

Đừng chạy lệnh `vault secrets enable` đè lên mount đã tồn tại. Nếu `secret/` là KV v1 trong foundation khác, hành vi API và ACL thay đổi; bài lab này mặc định KV v2.

### Bước 2 — Tạo policy test và cấp token không phải root

~~~bash
vault policy write payment-repository-lab - <<'HCL'
path "secret/data/payment-credentials/*" {
  capabilities = ["create", "read", "update", "delete"]
}
path "secret/metadata/payment-credentials" {
  capabilities = ["list"]
}
HCL

LAB_TOKEN="$(vault token create \
  -policy=payment-repository-lab \
  -ttl=15m \
  -field=token)"
~~~

Token này chỉ dành cho khóa trong keyspace thử nghiệm. Kiểm tra capability:

~~~bash
VAULT_TOKEN="$LAB_TOKEN" vault token capabilities \
  secret/data/payment-credentials/lab-01

VAULT_TOKEN="$LAB_TOKEN" vault token capabilities \
  secret/metadata/payment-credentials
~~~

Lệnh đầu thường trả `create, read, update, delete`; lệnh sau có `list`. Nếu server áp chính sách khác hoặc Vault namespace riêng, kết quả có thể khác; phải đọc policy và mount đúng môi trường.

### Bước 3 — Cấp token cho tiến trình Spring Boot

~~~bash
export VAULT_ADDR="http://127.0.0.1:8200"
export LAB_VAULT_TOKEN="$LAB_TOKEN"

# Khởi động ứng dụng Spring Boot bằng IDE hoặc runner của dự án.
# Đảm bảo VaultRepositoryConfiguration được nạp vào Spring context.
~~~

**Không** chạy ứng dụng với `VAULT_TOKEN=root` rồi coi đó là chứng minh chính sách workload hoạt động. Ví dụ `VaultRepositoryConfiguration` sử dụng `LAB_VAULT_TOKEN` riêng, nên dù CLI shell có token quản trị, ứng dụng phải hoạt động bằng token lab đúng quyền.

### Bước 4 — Thực hiện CRUD bằng Spring bean

Trong một test hoặc entrypoint nội bộ dành riêng cho sandbox:

~~~java
PaymentCredential created = repository.save(
        new PaymentCredential(
                "lab-01",
                "lab-client-id",
                "LAB_DUMMY_API_KEY"
        )
);

boolean found = repository.findById("lab-01").isPresent();
long total = repository.count();
repository.deleteById("lab-01");

// Dùng assertion thay vì in created hoặc apiKey.
if (!found || total < 1) {
    throw new AssertionError("Vault repository CRUD failed");
}
~~~

Các lời gọi repository là **imperative**: phương thức `save` và `deleteById` thực thi I/O khi được gọi. Khác `ReactiveVaultTemplate`, chúng không trả `Mono`/`Flux` để đợi subscriber.

**Nếu bài lab chỉ muốn kiểm tra annotation đã được bật mà không ghi secret**, hãy inject repository và xác minh bean tồn tại; không cần `save` khi chưa cho phép ghi.

### Bước 5 — Đối chiếu bằng Vault CLI

Trước khi delete, một secret có thể được kiểm tra bằng:

~~~bash
VAULT_TOKEN="$LAB_TOKEN" vault kv get \
  -mount=secret payment-credentials/lab-01
~~~

Với key đã delete trên KV v2, việc gọi `vault kv get` thường báo phiên bản hiện tại đã bị xóa hoặc không có dữ liệu. Nhưng metadata/version cũ có thể vẫn còn. Hãy phân biệt:

- `findById("lab-01")` không còn trả entity như trước sau delete.
- `vault kv get` thất bại/không có dữ liệu cho phiên bản hiện tại.
- `vault kv metadata get` (bằng token operator có quyền thích hợp) có thể vẫn cho thấy metadata/versions chưa bị destroy.

**Không** xóa vĩnh viễn metadata của key production để “dọn thử” rồi mong có thể phục hồi bằng `CrudRepository`.

### Bước 6 — Dọn môi trường thử nghiệm

~~~bash
# Lệnh operator trên dev server sau khi ứng dụng đã dừng.
vault token revoke "$LAB_TOKEN"

# Xóa hẳn metadata của key thử nghiệm trên Vault dev.
vault kv metadata delete -mount=secret payment-credentials/lab-01

vault policy delete payment-repository-lab
~~~

`vault kv metadata delete` sẽ xóa vĩnh viễn mọi phiên bản của **key đó**. Chỉ dùng trong Vault dev/test đã xác nhận mount và path chính xác.

## 12. Kiểm thử việc kích hoạt và phân quyền

Nên tách **bài kiểm tra Spring đã tạo proxy** khỏi **bài kiểm tra repository truy cập Vault**. Một test chỉ assert có bean sẽ phát hiện lỗi package scanning nhưng chưa chứng minh token/ACL và KV path hoạt động. Một test đọc/ghi KV thành công cho thấy cả hai phía được wiring đúng trong môi trường thử nghiệm.

### 12.1. Khẳng định có đúng repository bean

Với JUnit 5 và Spring Boot Test, sau khi cấu hình Vault lab đầy đủ:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;

import com.example.payment.vault.repository.PaymentCredentialRepository;

@SpringBootTest
class VaultRepositoryRegistrationTest {

    @Autowired
    ApplicationContext context;

    @Test
    void createsVaultRepositoryProxy() {
        PaymentCredentialRepository repository =
                context.getBean(PaymentCredentialRepository.class);

        assertThat(repository).isNotNull();
        assertThat(context.getBeansOfType(
                PaymentCredentialRepository.class)).hasSize(1);
    }
}
~~~

Test này chỉ có thể chạy khi **ApplicationContext khởi động được**; nếu cấu hình Vault phải kết nối ngay lúc tạo bean, cần Vault dev/test sẵn sàng hoặc thay thế adapter trong unit test. **Không** suy ra `assertThat(repository).isNotNull()` là đã ghi hoặc đọc dữ liệu được từ Vault.

Nếu bean không xuất hiện, trước tiên kiểm tra package chứa interface có nằm trong `basePackageClasses`/`basePackages` không, và lớp cấu hình có được import vào context không. Việc đăng ký `@Component` trên interface không phải cách sửa cho một `@EnableVaultRepositories` chưa được kích hoạt.

### 12.2. Kiểm tra chính sách đọc được nhưng ghi bị từ chối

Tạo policy chỉ đọc dành riêng cho một key:

~~~bash
vault policy write payment-repo-reader - <<'HCL'
path "secret/data/payment-credentials/lab-01" {
  capabilities = ["read"]
}
HCL

READER_TOKEN="$(vault token create \
  -policy=payment-repo-reader \
  -ttl=5m \
  -field=token)"
~~~

Nếu đã xóa `lab-01` ở bước lab trước, operator tạo lại **key giả trên sandbox** trước khi thử token chỉ đọc:

~~~bash
# Chạy bằng token operator có quyền ghi, không dùng READER_TOKEN.
vault kv put -mount=secret payment-credentials/lab-01 \
  clientId="lab-reader-test" apiKey="LAB_ONLY"
~~~

Sau đó chạy các lệnh sau bằng `READER_TOKEN`:

~~~bash
# Được phép đọc.
VAULT_TOKEN="$READER_TOKEN" vault kv get \
  -mount=secret payment-credentials/lab-01

# Bị từ chối vì policy không có quyền ghi.
VAULT_TOKEN="$READER_TOKEN" vault kv put \
  -mount=secret payment-credentials/lab-01 \
  clientId="should-not-write" apiKey="DENIED"
~~~

Kết quả mong đợi: `get` thành công, `put` bị Vault từ chối (thường **HTTP 403**, thông báo CLI `permission denied`). Lúc tích hợp Java, nếu truyền `READER_TOKEN` vào `LAB_VAULT_TOKEN`, gọi `findById` trên key đã tồn tại có thể thành công, còn `save` với cùng ID sẽ lỗi do ACL. Đừng ép bắt mọi lỗi thành “không tìm thấy secret”: 403 khác 404 và khác lỗi kết nối.

~~~bash
# Cleanup token/policy chỉ đọc bằng operator trên sandbox.
vault token revoke "$READER_TOKEN"
vault policy delete payment-repo-reader
~~~

### 12.3. Kiểm tra quyền list tách biệt với read

Một token chỉ có `read` trên `secret/data/payment-credentials/lab-01` có thể gọi `findById("lab-01")` thành công nhưng **không tự động được phép** dùng `findAll()` hoặc `count()`: để liệt kê keyspace, Repository cần danh sách IDs. Với KV v2, quyền `list` được kiểm tra trên `secret/metadata/payment-credentials`, không phải `secret/data/.../*`.

Điều này cho phép thiết kế API nội bộ: workload chỉ biết ID được cấp sẵn thì chỉ cần quyền đọc key đó; chỉ thành phần quản trị thật sự cần liệt kê toàn bộ đối tượng mới nhận `list`. Các test nên tách hai kỳ vọng để tránh vô tình cấp thêm quyền khi gặp lỗi `findAll()`.

## 13. Chẩn đoán lỗi cấu hình thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách kiểm tra / xử lý |
| --- | --- | --- |
| `NoSuchBeanDefinitionException` cho repository | Chưa có `@EnableVaultRepositories`, lớp cấu hình không được nạp hoặc scan sai package | Kiểm tra `@Configuration`, `@Import`, `basePackageClasses` |
| Không tìm thấy `vaultTemplate` | Không khai báo `VaultOperations` hoặc bean name không đúng | Kiểm tra `vaultTemplateRef` và tên bean thực tế |
| Lỗi `KeyValueOperations` / template bean | Thiếu Spring Data KeyValue hoặc `keyValueTemplateRef` không đúng | Kiểm tra dependencies, `VaultKeyValueTemplate`, bean name |
| Repository bean trùng/khởi tạo hai lần | Nhiều cấu hình cùng scan interface, hoặc nhiều Spring Data modules quét chồng | Giới hạn package và chỉ đăng ký một lần |
| `@Secret` mapping sai path | Nhầm keyspace/mount hoặc chèn `data/` vào keyspace | Đối chiếu `@Secret(value, backend)` với key logic và Vault CLI |
| `save` hoặc `findById` nhận 403 | Token hết hạn hoặc thiếu `create`/`update`/`read` | Dùng token workload kiểm tra capability trên `secret/data/...` |
| `count()` / `findAll()` nhận 403 | Thiếu `list` metadata KV v2 | Kiểm tra `secret/metadata/payment-credentials` |
| Lỗi phát hiện KV mount | Mount không tồn tại hoặc endpoint `sys/internal/ui/mounts` không truy cập được | Kiểm tra mount, auth và quyền theo tài liệu Vault |
| `findById` không thấy key vừa xóa | KV v2 soft delete version hiện tại | Xem metadata/versions bằng operator đủ quyền |
| Query theo field `apiKey` không khả dụng | Vault Repository chỉ hỗ trợ predicates theo ID | Thiết kế ID/keyspace phù hợp; không coi Vault là database tìm kiếm |
| `save` ghi đè field không mong đợi | Entity không map tất cả dữ liệu hiện có | Đảm bảo model ánh xạ đầy đủ, cân nhắc `@Version` và CAS |
| Kết nối chậm/hết TTL | Lỗi network, Vault seal, session token hoặc auth role | Theo dõi từng lớp, không fallback sang root token |

### Cấu hình nhiều Spring Data module

Nếu ứng dụng cũng dùng JPA, MongoDB hoặc một repository module khác, phải tránh để các scanner khác nhau xử lý sai cùng một repository interface. Giới hạn package dành cho Vault dưới `com.example.payment.vault.repository` và cấu hình scanner của các module khác ở những package riêng.

Đặc biệt, interface `PaymentCredentialRepository` nên được đặt trong package chỉ dành cho Vault, domain dùng annotation `@Secret` để bộ hạ tầng Vault nhận diện. Không coi annotation `@EnableVaultRepositories` là thay thế cho mọi `@EnableJpaRepositories` hoặc scanner khác.

## 14. Ranh giới thiết kế và bảo mật

### Vault Repository không phải cơ sở dữ liệu quan hệ

- Không có join, transaction đa key hay SQL query cho mọi field.
- Derived query predicates chủ yếu hoạt động trên **identifier**.
- Paging/sorting có thể cần list rồi xử lý hoặc đọc nhiều secret, khiến I/O và quyền `list` tăng.
- Dữ liệu lưu trong Vault KV có thể phù hợp cho **cấu hình/secret có ID rõ ràng**, không phải tập dữ liệu nghiệp vụ biến động lớn như đơn hàng, lịch sử giao dịch.
- Entity mapping có thể bao gồm metadata `_class` và toàn bộ trường được map. Không ghi dữ liệu nhạy cảm không cần thiết, và không log entity.

### Vault Repository không quản lý tất cả lifecycle

Repository dùng **Vault token** do Spring Vault client/session cung cấp. Việc tạo proxy không tự đăng nhập theo workload, không tự gia hạn token và không quyết định policy. Đối với KV tĩnh, một lần `save` không tạo secret lease động tương đương database credentials. Nếu ứng dụng còn dùng dynamic secrets hoặc PKI, quản lý lease và credential rotation vẫn là **một trách nhiệm riêng**, chẳng hạn qua `SecretLeaseContainer` hoặc thành phần phù hợp.

Không dùng repository để thay các API Transit/PKI: Transit cần capability `transit/encrypt/...`, PKI có endpoint cấp/thu hồi chứng thư riêng; `@EnableVaultRepositories` chỉ kích hoạt **KV-oriented repositories**.

### Đặc quyền tối thiểu và giám sát

- Cho mỗi workload đúng `read/create/update/delete/list` cần dùng, theo mount/keyspace.
- Bảo vệ Vault token, AppRole SecretID, JWT/Kubernetes credential, TLS truststore và bản thân giá trị secret.
- Không để HTTP controller trả thẳng `PaymentCredential` chứa `apiKey`; dùng DTO không có secret hoặc Boolean trạng thái khi thích hợp.
- Không in `repository.findAll()`, `VaultResponse`, object mapper hay exception raw có thể mang secret ra log.
- Ghi metric lỗi theo lớp (Vault auth, ACL, KV path, mount discovery), độ trễ request, số lần gọi `list`; hạn chế thông tin nhạy cảm trong label.
- Đối với dữ liệu concurrent, cân nhắc `@Version`/CAS trên KV v2; không hứa transaction nhiều key.

## 15. Kiểm tra nhanh theo tình huống

**Tình huống A — Repository interface đã viết nhưng Spring báo không tìm thấy bean.** Bạn có interface `com.example.payment.vault.repository.PaymentCredentialRepository` nhưng lớp `@EnableVaultRepositories` đặt ở `com.example.payment.config` và không khai báo `basePackages`. Khắc phục: dùng `basePackageClasses=PaymentCredentialRepository.class` hoặc package đúng, đồng thời bảo đảm Spring đã nạp lớp `@Configuration`.

**Tình huống B — Bean được tạo nhưng đọc một key trả 403.** Annotation đã làm đúng việc **đăng ký proxy**. Lỗi nằm ở việc gọi Vault: kiểm tra token workload, mount, API path `secret/data/payment-credentials/lab-01` và capability `read`, thay vì liên tục sửa `@EnableVaultRepositories`.

**Tình huống C — `findById` được, `count` lỗi 403.** Không phải repository scan hoạt động “một nửa”: hai thao tác dùng quyền khác nhau. `findById` đọc nội dung, còn `count` có thể phải `list` metadata. Chỉ cấp `list` khi ứng dụng thật sự cần enumerate keyspace.

**Tình huống D — `deleteById` thành công nhưng operator vẫn thấy version cũ.** Trong KV v2, xóa theo repository dùng thao tác delete chứ không destroy vĩnh viễn. Đây là cơ chế versioning, cần giải thích rõ trong quy trình xóa dữ liệu và yêu cầu tuân thủ bảo mật.

**Tình huống E — Muốn tìm theo `apiKey` ở hàng triệu entities.** Vault Repository không có query engine để index field tùy ý. Dùng database hoặc search engine thích hợp cho nhu cầu truy vấn đó; Vault vẫn có thể giữ secret được truy cập bằng ID.

**Tình huống F — Ứng dụng bật Spring Cloud Vault và tự thêm một `VaultTemplate` mới.** Có thể phát sinh hai bean/phiên hoặc sự khác nhau về Vault endpoint, token, namespace và lifecycle. Cần xác định nguồn bean hiện có và chỉ định `vaultTemplateRef` nếu thực sự sử dụng nhiều Vault clients.

## 16. Câu hỏi tự đánh giá

1. `@EnableVaultRepositories` kích hoạt những phần nào trong Spring? Nó có tạo KV mount hoặc cấp token trên Vault không?
2. Tại sao `basePackageClasses` thường an toàn hơn `basePackages` khi đổi package Java?
3. `@Secret(value="payment-credentials", backend="secret")` kết hợp ID `lab-01` cho key logic nào?
4. `vaultTemplateRef` và `keyValueTemplateRef` trỏ tới hai loại bean nào?
5. Vì sao `findById("lab-01")` có thể thành công nhưng `findAll()` lại bị từ chối bởi Vault?
6. Khi làm việc với KV v2, tại sao ACL dùng `secret/data/...` còn quyền list cần `secret/metadata/...`?
7. Xóa bằng `CrudRepository.deleteById` trên KV v2 có bảo đảm destroy tất cả version không?
8. Có thể viết `findByApiKey(...)` rồi kỳ vọng Vault truy vấn như SQL không?
9. Khi ứng dụng dùng KV v2 và có cập nhật đồng thời, `@Version` giúp tránh lỗi gì?
10. Tại sao không nên đưa entity chứa `apiKey` trực tiếp vào một `@RestController` trả JSON?

**Gợi ý đáp án ngắn:** (1) Quét và tạo repository proxy, không cấu hình Vault server. (2) Type-safe khi refactor. (3) `payment-credentials/lab-01`. (4) `VaultOperations` và `KeyValueOperations`. (5) Read khác list. (6) KV v2 có API path data và metadata riêng. (7) Không. (8) Không, query predicates tập trung vào ID. (9) Optimistic locking/CAS. (10) Vì nguy cơ rò rỉ secret.

## 17. Checklist hoàn thành

Một bài triển khai `@EnableVaultRepositories` được coi là đã **hoàn thành về mặt kỹ thuật** khi:

- [ ] Đã có dependencies Spring Vault Core và Spring Data KeyValue tương thích.
- [ ] `VaultTemplate` hoặc `VaultOperations` bean dùng endpoint/auth/CA đúng môi trường.
- [ ] `@EnableVaultRepositories` đặt trên cấu hình được nạp vào context.
- [ ] Package scan bao gồm đúng repository interface và tránh trùng với các module khác.
- [ ] Domain có `@Secret`, ID kiểu `String` và mô hình dữ liệu không làm lộ secret.
- [ ] Đã hiểu `backend` và `value` quyết định mount/keyspace khác nhau.
- [ ] KV v2 mount tồn tại và token workload được phép sử dụng đúng path.
- [ ] Repository bean được inject thành công; gọi CRUD/test với dữ liệu giả trong sandbox.
- [ ] Đã kiểm thử ít nhất một thao tác **được phép** và một thao tác **bị từ chối** bằng policy tối thiểu.
- [ ] Đã biết `findAll/count` có thể đòi quyền `list`, `delete` không phải `destroy`.
- [ ] Không log password/token, không trả entity bí mật trong response công khai.
- [ ] Đã phân biệt trách nhiệm repository KV với quản lý token/lease, Transit và PKI.

### Tài liệu tham khảo

- [Spring Vault — Vault Repositories](https://docs.spring.io/spring-vault/reference/vault/vault-repositories.html).
- [Spring Vault — EnableVaultRepositories API](https://docs.spring.io/spring-vault/reference/api/java/org/springframework/vault/repository/configuration/EnableVaultRepositories.html).
- [Spring Vault — Secret annotation API](https://docs.spring.io/spring-vault/reference/api/java/org/springframework/vault/repository/mapping/Secret.html).
- [Spring Vault — VaultKeyValueTemplate API](https://docs.spring.io/spring-vault/reference/api/java/org/springframework/vault/repository/core/VaultKeyValueTemplate.html).
- [Spring Vault — VaultRepositoryFactoryBean API](https://docs.spring.io/spring-vault/reference/api/java/org/springframework/vault/repository/support/VaultRepositoryFactoryBean.html).
- [Spring Data — Repositories](https://docs.spring.io/spring-data/commons/reference/repositories.html).
- [HashiCorp Vault — KV secrets engine](https://developer.hashicorp.com/vault/docs/secrets/kv).
- [HashiCorp Vault — KV v2 API](https://developer.hashicorp.com/vault/api-docs/secret/kv/kv-v2).

**Kết luận:** `@EnableVaultRepositories` là điểm kết nối giữa Spring Data repository interfaces và Vault KV engine. Đăng ký đúng package, đúng `VaultTemplate`, ánh xạ đúng `@Secret`/`@Id` và cấp chính xác Vault ACL sẽ cho phép ứng dụng Java dùng CRUD theo interface. Khả năng này **không thay thế** kiểm soát danh tính workload, bảo vệ secret và quản lý vòng đời token/lease.
