# Tách client vận hành khỏi danh tính của ứng dụng trong Spring Vault

## 1. Bài toán và mục tiêu

Trong một hệ thống Java sử dụng **HashiCorp Vault**, dịch vụ nghiệp vụ thường chỉ cần đọc một số KV secrets, gọi Transit để mã hóa dữ liệu, xin dynamic credentials hoặc chứng thư PKI. Ngược lại, công cụ vận hành có thể cần xem danh sách mount, kiểm tra auth methods, quản lý ACL policy hoặc bật một secrets engine. Hai nhóm công việc dùng chung Vault server nhưng **không nên dùng chung danh tính có quyền quản trị**.

**Spring Vault** cung cấp **VaultOperations** (thường được triển khai bởi **VaultTemplate**) và các API như **opsForKeyValue(...)**, **opsForTransit(...)**, **opsForPki(...)**, **opsForSys()**. Chúng chỉ cung cấp cách gọi HTTP API; **Vault ACL và danh tính gắn với token** mới quyết định request nào được phép thực hiện.

Nếu ứng dụng đặt một token quản trị vào **VaultTemplate** mặc định, mọi service có thể tiêm bean đó đều có khả năng dùng token với quyền rộng hơn nhu cầu nghiệp vụ. Một lỗi logic, endpoint bị khai thác hoặc lộ cấu hình có thể trở thành sự cố toàn Vault.

Mục tiêu của bài:

- Phân biệt **runtime client** với **operations/provisioning client** theo nhiệm vụ và quyền.
- Thiết kế **hai VaultTemplate sử dụng hai danh tính khác nhau**, quản lý xác thực/phiên riêng và chọn đúng bean khi tiêm dependency.
- Hiểu vì sao hai bean Java chưa tạo thành ranh giới bảo mật nếu cả hai token vẫn nằm trong một tiến trình.
- Cấu hình chính sách ACL theo nguyên tắc **least privilege**, bao gồm path **sys/** cho tác vụ vận hành.
- Kiểm thử rằng ứng dụng làm được việc được cấp nhưng bị từ chối khi gọi System API.
- Vận hành an toàn token/lease, kết nối TLS, audit và triển khai workload.

Ví dụ xuyên suốt:

- **order-api**: ứng dụng Spring Boot cần đọc KV v2 **kv-app/data/orders/config** và mã hóa thông qua **transit/encrypt/orders**.
- **vault-ops**: job vận hành độc lập cần đọc danh sách secrets engine **sys/mounts** và auth methods **sys/auth**. Khi có thay đổi được phê duyệt, một job provisioning riêng có thể được cấp quyền tạo mount thử nghiệm.

## 2. Tách biệt thực chất là tách danh tính

~~~mermaid
flowchart TB
    subgraph App["Workload: order-api"]
        S["Business service"]
        S --> VT1["VaultTemplate runtime"]
        VT1 --> AU1["Auth: role order-api"]
    end
    subgraph Ops["Workload: vault-ops"]
        J["Inventory / provisioning job"]
        J --> VT2["VaultTemplate ops"]
        VT2 --> AU2["Auth: role vault-ops"]
    end
    AU1 --> P1["ACL: KV/Transit theo nhu cầu"]
    AU2 --> P2["ACL: endpoint sys/ cần thiết"]
    P1 --> V["HashiCorp Vault"]
    P2 --> V
~~~

Hai client có thể kết nối **cùng Vault cluster**, tin cậy **cùng CA TLS** và sử dụng cùng thư viện **spring-vault-core**. Điểm quyết định là chúng đăng nhập bằng **hai workload identities** được gắn **hai tập policy khác nhau**.

| Thuộc tính | Client ứng dụng | Client vận hành |
| --- | --- | --- |
| Mục tiêu | Đọc secret, mã hóa/giải mã, xin chứng thư/credential | Xem trạng thái hệ thống, quản lý mount/auth/policy khi được giao |
| Định danh | Role và service account của **order-api** | Role và service account của **vault-ops** |
| Token | Chỉ có quyền nghiệp vụ | Chỉ có quyền ops cần thiết |
| Nơi chạy | Tiến trình phục vụ request | Job/service vận hành được cách ly |
| Thời điểm chạy | Liên tục | Theo lịch, theo nhiệm vụ hoặc sự kiện |
| Audit | Xác định service nghiệp vụ | Xác định job/người vận hành và hành động |
| Kết quả khi gọi sys API | Thông thường **403** | Cho phép một số endpoint cụ thể |
| Rủi ro nếu token lộ | Giới hạn trong quyền ứng dụng | Giới hạn trong phạm vi ops được cấp |

**Hai VaultTemplate có tên khác nhau nhưng dùng cùng một token không hề tách quyền.** Ngay cả hai token khác nhau cũng chưa tạo được ranh giới vững chắc nếu **order-api** có thể đọc token ops từ environment, Secret volume, memory hoặc cấu hình chung. Nên đặt ops credential trong **workload riêng** mà order-api không có quyền tiếp cận.

## 3. Chính sách quyền tối thiểu tại Vault

### 3.1 Runtime policy

Ví dụ file **order-api.hcl**:

~~~hcl
path "kv-app/data/orders/config" {
  capabilities = ["read"]
}

path "transit/encrypt/orders" {
  capabilities = ["update"]
}
~~~

KV v2 sử dụng endpoint **data/** để đọc giá trị. Endpoint **transit/encrypt/** dùng quyền **update**. Policy này không cho phép đọc các secret khác, không cho phép decrypt và không mở quyền **sys/**. Nếu ứng dụng cần thêm nghiệp vụ, mở đúng đường dẫn sau khi đánh giá use case; không thêm **path "*"**.

### 3.2 Ops policy dành cho quan sát

Ví dụ file **vault-ops-observe.hcl**:

~~~hcl
path "sys/mounts" {
  capabilities = ["read"]
}

path "sys/auth" {
  capabilities = ["read"]
}
~~~

Job có policy này được phép gọi những endpoint quan sát đã định nghĩa, không có quyền tạo hoặc xóa mount. Với **VaultSysOperations**, các phương thức tương ứng là **getMounts()** và **getAuthMounts()**.

Khi cần tạo một mount trong môi trường test, chỉ job provisioning được bổ sung quyền trên **một path cụ thể**, ví dụ:

~~~hcl
path "sys/mounts/kv-sandbox" {
  capabilities = ["create", "update", "delete", "sudo"]
}
~~~

Một số endpoint root-protected cần capability **sudo** bên cạnh capability tương ứng. **sudo** trong Vault ACL không phải Linux sudo. Quyền **delete** mount ảnh hưởng dữ liệu/leases; không nên cấp cho danh tính quan sát thường trực. Đối chiếu quyền chính xác với Vault version và API được gọi.

Quản trị viên được phép cấu hình hai policy:

~~~bash
vault policy write order-api order-api.hcl
vault policy write vault-ops-observe vault-ops-observe.hcl
~~~

**Viết policy chưa đủ:** phải gắn đúng policy vào **hai auth roles hoặc hai danh tính workload khác nhau**. Nếu cả hai role cùng được gắn tập policy rộng, việc tách tên Java không giúp giảm quyền thực tế.

### 3.3 Kiểm chứng effective capabilities

Từ phiên CLI đã xác thực riêng cho **order-api**:

~~~bash
vault token capabilities kv-app/data/orders/config
vault token capabilities transit/encrypt/orders
vault token capabilities sys/mounts
vault token capabilities sys/mounts/kv-sandbox
~~~

Kỳ vọng tương ứng là **read**, **update**, **deny**, **deny** (khi token chỉ có quyền trong ví dụ).

Với token của **vault-ops-observe**:

~~~bash
vault token capabilities sys/mounts
vault token capabilities sys/auth
vault token capabilities kv-app/data/orders/config
vault token capabilities sys/mounts/kv-sandbox
~~~

Kỳ vọng: **read**, **read**, **deny**, **deny**. Vault còn có thể áp dụng policy gắn qua identity entity/group, namespace hoặc các giới hạn khác; vì thế cần kiểm tra **token thực được sử dụng**, không chỉ nhìn file HCL.

## 4. Kiến trúc triển khai phù hợp

Ưu tiên **hai deployment độc lập**:

1. **order-api** chạy bằng Kubernetes ServiceAccount/JWT/AppRole dành cho ứng dụng và đăng nhập Vault bằng role **order-api**.
2. **vault-ops** chạy bằng danh tính riêng, nhận policy **vault-ops-observe** hoặc policy provisioning chỉ cho nhiệm vụ xác định.
3. Mỗi workload tạo **VaultTemplate**, **ClientAuthentication** và **SessionManager** riêng.
4. Runtime code không được cung cấp ops credential; ops job không cần biết các secret nghiệp vụ.
5. Log/audit và metric phải phân biệt nguồn request của hai danh tính.

~~~mermaid
sequenceDiagram
    participant A as order-api
    participant O as vault-ops
    participant V as Vault
    A->>V: Login với runtime role
    V-->>A: Token A, policy order-api
    O->>V: Login với ops role
    V-->>O: Token B, policy vault-ops-observe
    A->>V: GET kv-app/data/orders/config với A
    V-->>A: 200 (secret được phép)
    A->>V: GET sys/mounts với A
    V-->>A: 403 permission denied
    O->>V: GET sys/mounts với B
    V-->>O: 200 (mount inventory)
~~~

**403 đối với runtime gọi sys/mounts là hành vi mong muốn**. Một lần test quyền bị từ chối có giá trị tương đương test nghiệp vụ thành công vì nó kiểm chứng ranh giới quyền.

## 5. Ví dụ Spring Vault với hai cấu hình tách deployment

Ví dụ sau dùng **org.springframework.vault:spring-vault-core** và constructor hỗ trợ rộng rãi **VaultTemplate(VaultEndpoint, ClientAuthentication)**. Cấu hình **TokenAuthentication** giả định token được **cấp từ bên ngoài**, ví dụ một hệ thống bootstrap hoặc agent. Sản phẩm thực tế nên dùng xác thực theo workload (Kubernetes/JWT/AppRole) và quản lý rotation/renewal phù hợp; không nhúng token cố định vào mã nguồn.

Các đoạn cấu hình nằm trong cùng repository để giảng dạy, nhưng phải được **triển khai thành hai workload**. Profile chỉ giúp chọn mã Java; quyền Vault và cách ly credential mới là cơ chế bảo vệ.

### 5.1 Cấu hình VaultTemplate cho runtime

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Profile;
import org.springframework.core.env.Environment;
import org.springframework.vault.authentication.TokenAuthentication;
import org.springframework.vault.client.VaultEndpoint;
import org.springframework.vault.core.VaultOperations;
import org.springframework.vault.core.VaultTemplate;

@Configuration(proxyBeanMethods = false)
@Profile("app-runtime")
public class RuntimeVaultConfiguration {

    @Bean("runtimeVaultOperations")
    VaultOperations runtimeVaultOperations(Environment env) {
        String address = env.getRequiredProperty("app.vault.uri");
        String token = env.getRequiredProperty("app.vault.runtime-token");

        return new VaultTemplate(
                VaultEndpoint.from(address),
                new TokenAuthentication(token)
        );
    }
}
~~~

Chỉ deployment **order-api** được cấp thuộc tính bí mật **app.vault.runtime-token** qua cơ chế quản lý secret đáng tin cậy. Deployment này **không được nhận** thuộc tính **app.vault.ops-token**.

### 5.2 Cấu hình VaultTemplate cho operations

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Profile;
import org.springframework.core.env.Environment;
import org.springframework.vault.authentication.TokenAuthentication;
import org.springframework.vault.client.VaultEndpoint;
import org.springframework.vault.core.VaultOperations;
import org.springframework.vault.core.VaultTemplate;

@Configuration(proxyBeanMethods = false)
@Profile("ops-job")
public class OperationsVaultConfiguration {

    @Bean("opsVaultOperations")
    VaultOperations opsVaultOperations(Environment env) {
        String address = env.getRequiredProperty("app.vault.uri");
        String token = env.getRequiredProperty("app.vault.ops-token");

        return new VaultTemplate(
                VaultEndpoint.from(address),
                new TokenAuthentication(token)
        );
    }
}
~~~

Deployment **vault-ops** kích hoạt **ops-job**, được cấp token ops riêng và không được cấp secret chỉ phục vụ ứng dụng. Tránh bật đồng thời hai profile trong một deployment thực tế.

**Cấu hình kết nối:** URI nên dùng HTTPS, ví dụ **https://vault.internal.example:8200**. Trước khi đưa vào môi trường thật, cấu hình truststore cho CA Vault, timeout và connection pool thích hợp. Nếu dùng Spring Cloud Vault auto-configuration, cần rà soát bean mặc định và xác định rõ client nào được auto-wire, không để ops bean trở thành **@Primary** cho mọi component.

### 5.3 Runtime service chỉ dùng runtime bean

~~~java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.stereotype.Service;
import org.springframework.vault.core.VaultOperations;
import org.springframework.vault.support.VaultResponse;

@Service
public class OrderConfigurationService {

    private final VaultOperations vault;

    public OrderConfigurationService(
            @Qualifier("runtimeVaultOperations") VaultOperations vault) {
        this.vault = vault;
    }

    public VaultResponse loadConfiguration() {
        // KV v2 dùng endpoint <mount>/data/<path>.
        return vault.read("kv-app/data/orders/config");
    }
}
~~~

**@Qualifier** giúp xác nhận service nghiệp vụ dùng đúng bean. Không trả nguyên **VaultResponse** chứa secret qua REST API công khai hoặc ghi đối tượng vào log. Với KV v2, payload thực thường nằm trong phần **data.data** của JSON Vault response.

### 5.4 Operations service chỉ dùng ops bean

~~~java
import java.util.Map;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.stereotype.Service;
import org.springframework.vault.core.VaultOperations;
import org.springframework.vault.core.VaultSysOperations;
import org.springframework.vault.support.VaultMount;

@Service
public class VaultMountInventoryService {

    private final VaultSysOperations sys;

    public VaultMountInventoryService(
            @Qualifier("opsVaultOperations") VaultOperations operations) {
        this.sys = operations.opsForSys();
    }

    public Map<String, VaultMount> listMounts() {
        return sys.getMounts();
    }
}
~~~

Lớp inventory trên nằm trong deployment ops, không trong HTTP request path của **order-api**. Không cung cấp endpoint kiểu **/admin/vault?path=...** nhận đường dẫn tùy ý rồi dùng ops token thực hiện yêu cầu của caller. Nếu cần giao tác vụ từ ứng dụng cho ops, chỉ công khai **một operation cụ thể**, có xác thực/ủy quyền, kiểm tra input, approval cho mutation và audit đầy đủ.

**Ranh giới cần nhớ:** hai bean khác tên nhưng cùng JVM vẫn có thể bị truy cập chéo nếu JVM bị chiếm quyền. Tách process/container/service account và ngăn runtime đọc credential ops mới giải quyết căn nguyên.

## 6. Phân tách ClientAuthentication và SessionManager

**ClientAuthentication** xử lý đăng nhập hoặc cung cấp Vault token. **SessionManager** quyết định cách token được lấy lại và quản lý trong phiên làm việc. Hai đối tượng này phải gắn với danh tính của **từng workload**, không dùng chung session manager hay Vault token giữa runtime và ops.

~~~mermaid
flowchart LR
    A["Auth runtime"] --> B["SessionManager runtime"]
    B --> C["VaultTemplate runtime"]
    D["Auth ops"] --> E["SessionManager ops"]
    E --> F["VaultTemplate ops"]
    C --> G["Vault cluster"]
    F --> G
~~~

Trong Spring Vault:

- **SimpleSessionManager** lấy token từ **ClientAuthentication** và tái sử dụng token, không chủ động lên lịch renew/revoke.
- **LifecycleAwareSessionManager** có khả năng quản lý vòng đời, lên lịch renew với token có thể renew và thu hồi login token phù hợp khi đóng session, tùy loại token và cấu hình.

Ví dụ trước dùng **TokenAuthentication** để minh họa ranh giới, **không bảo đảm việc đổi token tự động**. Nếu token tĩnh ngắn hạn hết hạn, cần cơ chế được thiết kế riêng để thay token hoặc dùng đăng nhập theo workload. Không giải quyết sự cố TTL bằng cách tái sử dụng token ops cho runtime.

**TTL của token** khác với **TTL của dynamic secret lease**, **TTL wrapping token** và thời hạn chứng thư PKI. Khi tạo client mới, kiểm tra cả việc renew token, revoke token, đăng nhập lại, nguồn JWT/role credentials và cách ứng dụng xử lý Vault tạm thời không sẵn sàng.

Một mô hình triển khai hiệu quả: ops job nhận token ngắn hạn theo phiên chạy, hoàn tất việc quan sát/provisioning được giao, ghi audit và kết thúc; **không cần giữ token quản trị trong memory của service runtime**.

## 7. Ví dụ phân quyền theo workload với Kubernetes

Giả sử Kubernetes Auth ở Vault đã được bật và cấu hình tin cậy với cluster. Dùng hai ServiceAccounts:

- **order-api-sa** trong namespace **orders**, gắn Vault role **order-api**.
- **vault-ops-sa** trong namespace **platform-ops**, gắn Vault role **vault-ops**.

Người quản trị có thể cấu hình roles:

~~~bash
vault write auth/kubernetes/role/order-api \
  bound_service_account_names="order-api-sa" \
  bound_service_account_namespaces="orders" \
  policies="order-api" \
  ttl="15m"

vault write auth/kubernetes/role/vault-ops \
  bound_service_account_names="vault-ops-sa" \
  bound_service_account_namespaces="platform-ops" \
  policies="vault-ops-observe" \
  ttl="10m"
~~~

Đây là ví dụ ràng buộc **role**, chưa bao gồm phần cấu hình Kubernetes auth, projected service account token hoặc **KubernetesAuthentication** trong Spring Vault. Khi dùng KubernetesAuthentication, mỗi deployment phải khai báo đúng role của mình và xác thực bằng JWT service account dành riêng cho workload.

Tương tự, với AppRole hoặc JWT/OIDC, mỗi job có role, bound claims/audience, thời hạn token và policy riêng. Trong CI/CD, không tái sử dụng token root tĩnh ở tất cả pipeline; cấp quyền ops cho đúng job, gắn với môi trường và điều kiện triển khai.

Nếu Vault có namespace, mỗi VaultTemplate phải dùng đúng namespace và policy tương ứng. Hai request giống path nhưng khác namespace có thể truy cập các đối tượng khác nhau; không suy diễn chỉ từ tên mount.

## 8. Các lỗi thiết kế thường gặp

| Cách làm | Vấn đề | Cách khắc phục |
| --- | --- | --- |
| Một VaultTemplate duy nhất dùng token root | Service nghiệp vụ mang quyền quản trị toàn Vault | Chia danh tính runtime và ops với ACL tối thiểu |
| Hai bean nhưng cùng token | Vault thấy cùng một danh tính, không tạo ranh giới quyền | Hai auth roles và hai token thực sự khác nhau |
| Hai token khác nhau nhưng nằm trong container runtime | Runtime có thể đọc và sử dụng token ops | Deploy ops độc lập, cách ly Secret volumes/environment |
| Dựa vào **@Profile** như một biện pháp bảo mật | Bật nhầm profile hoặc mount nhầm secret vẫn làm lộ quyền | Kiểm soát workload identity, RBAC, distribution và ACL |
| Đặt opsVaultOperations thành **@Primary** | Các thành phần autowire có thể nhận nhầm client | Dùng tên bean và **@Qualifier**, tách deployment |
| Cấp **sys/** wildcard cho microservice | Mở quyền thay đổi nhiều thành phần Vault | Cấp quyền theo endpoint, method và use case |
| Dùng ops client làm proxy thực thi path tùy ý | Caller có thể lạm dụng token ops | Chỉ cho phép nghiệp vụ cụ thể có ủy quyền và audit |
| Chỉ test luồng đọc secret thành công | Không phát hiện runtime có quyền quản trị thừa | Thêm test xác minh **403** với System API |
| Không quản lý token TTL/rotation | Sau khi token hết hạn, các thao tác thất bại | Xác thực workload và quản lý phiên độc lập |
| Ghi body hoặc X-Vault-Token vào log | Làm lộ secret/token trong hệ thống quan sát | Log metadata tối thiểu, lọc trường nhạy cảm |

## 9. Kiểm thử tích hợp quyền thực tế

Không thể kiểm tra tách danh tính chỉ bằng cách mock **VaultOperations**. Cần Vault test có hai identities thực, các policy tương ứng, KV v2 **kv-app** và secret giả **orders/config**.

### 9.1 Runtime chỉ được đọc đúng secret

~~~java
import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.vault.VaultException;
import org.springframework.vault.core.VaultOperations;
import org.springframework.vault.support.VaultResponse;

@SpringBootTest
@ActiveProfiles("app-runtime")
class RuntimeVaultPermissionsIT {

    @Autowired
    @Qualifier("runtimeVaultOperations")
    VaultOperations runtime;

    @Test
    void readsAllowedKvAndCannotListSystemMounts() {
        VaultResponse response = runtime.read("kv-app/data/orders/config");
        assertThat(response).isNotNull();

        assertThatThrownBy(() -> runtime.opsForSys().getMounts())
                .as("Runtime token must not read sys/mounts")
                .isInstanceOf(VaultException.class)
                .hasMessageContaining("403");
    }
}
~~~

**Điều kiện quan trọng:** test cần nhận được **403 permission denied** từ Vault. Mã trên kiểm tra thông báo lỗi của **VaultException** theo cách Spring Vault thường hiển thị; tùy phiên bản, có thể cần đọc status từ exception/response cụ thể. Timeout, lỗi TLS hay Vault bị sealed **không được tính là PASS** cho test phân quyền.

### 9.2 Ops chỉ đọc metadata được cấp

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import java.util.Map;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.vault.core.VaultOperations;
import org.springframework.vault.support.VaultMount;

@SpringBootTest
@ActiveProfiles("ops-job")
class OpsVaultPermissionsIT {

    @Autowired
    @Qualifier("opsVaultOperations")
    VaultOperations ops;

    @Test
    void listsMountsWithOperationsIdentity() {
        Map<String, VaultMount> mounts = ops.opsForSys().getMounts();
        assertThat(mounts).containsKey("sys/");
    }
}
~~~

Test này chỉ đọc metadata và chỉ cần policy **vault-ops-observe**. Không gọi **mount(...)**, **unmount(...)**, **seal()**, **initialize(...)** hoặc **deletePolicy(...)** trong test dùng môi trường chung.

### 9.3 Ma trận quyền mong đợi

| Request | Token order-api | Token vault-ops-observe |
| --- | --- | --- |
| GET **kv-app/data/orders/config** | Cho phép | Từ chối |
| POST **transit/encrypt/orders** | Cho phép | Từ chối |
| GET **sys/mounts** | Từ chối | Cho phép |
| GET **sys/auth** | Từ chối | Cho phép |
| POST **sys/mounts/kv-sandbox** | Từ chối | Từ chối |
| DELETE **sys/mounts/kv-sandbox** | Từ chối | Từ chối |

Ma trận giả định các token **không có policy bổ sung** mở rộng quyền. Nếu cần kiểm chứng job provisioning, phải dùng danh tính thứ ba chỉ trong Vault lab, có phạm vi mount được phép và quy trình dọn dữ liệu tách biệt.

## 10. Giám sát, xử lý lỗi và thay đổi an toàn

**Khi runtime bị 403 trên sys API:** đây thường là ranh giới đúng. Không sửa bằng cách thêm policy ops vào role runtime.

**Khi ops bị 403 ở sys/mounts:** xác minh nó đã nhận đúng auth role, token còn hạn, namespace đúng và có capability **read** cho path thực tế. Một số endpoint sys khác có quy tắc **sudo** riêng, nên chỉ cấp quyền sau khi đã xác định endpoint cụ thể.

**Khi cả hai client lỗi kết nối:** kiểm tra DNS, Vault address, CA/truststore, timeout, Vault sealed/standby và network policy. Đừng coi mọi exception là lỗi quyền.

**Khi một client mất quyền sau khi đổi policy:** đọc lại effective capabilities của token, xác minh binding của entity/group và phân biệt token đã cấp với phiên đăng nhập mới. Chính sách Vault có thể ảnh hưởng ngay các phiên đang hoạt động.

**Khi ops mutation timeout:** kết quả thay đổi có thể đã được Vault áp dụng dù client chưa nhận phản hồi. Trước khi retry, đọc lại trạng thái tài nguyên, xem audit, xác định tính idempotent và chỉ thực hiện theo runbook.

Gợi ý log có thể đối chiếu:

~~~text
service=order-api operation=kv-read status=200
service=order-api operation=sys-mounts-list status=403
service=vault-ops operation=sys-mounts-list status=200
~~~

Chỉ ghi operation, status, thời gian, correlation ID và danh tính logic; không ghi **Vault token**, JWT, Secret ID, private key, plaintext KV, response chứa secret hoặc nguyên đường dẫn nếu nó là dữ liệu nhạy cảm. Phân quyền truy cập Vault audit log và bảo vệ dữ liệu audit theo quy định của tổ chức.

Nếu Spring Cloud Vault đã tạo bean mặc định và bootstrap secrets lúc ứng dụng khởi chạy, phải rà soát auto-configuration để tránh hai Vault clients cạnh tranh vai trò **@Primary** hoặc dùng nhầm token quản trị. Với ứng dụng nhạy cảm, nên tách hoàn toàn mã ops khỏi runtime artifact khi có thể.

## 11. Checklist thực hành

1. Liệt kê những endpoint runtime thật sự cần (KV, Transit, PKI, token/lease), không cấp quyền **sys/** mặc định.
2. Cấp auth role riêng cho **runtime** và **ops**, có policy, TTL, namespace và nguồn credential riêng.
3. Đặt **VaultTemplate runtime** trong workload ứng dụng; đặt **VaultTemplate ops** trong job/service vận hành độc lập.
4. Dùng **@Qualifier** để chọn đúng bean và không đặt ops client thành bean mặc định cho nghiệp vụ.
5. Chọn **ClientAuthentication/SessionManager** đáp ứng việc xin token, renew/revoke, TTL và tái xác thực của từng workload.
6. Cách ly ServiceAccount/Secret volumes, RBAC, network, TLS trust và quyền quan sát audit.
7. Kiểm thử **cho phép** với request đúng path và **từ chối 403** với request ngoài phạm vi; phân biệt 403 với lỗi hạ tầng.
8. Cấp quyền mutation theo đúng job, có kiểm tra trước/sau thay đổi, audit và phương án khôi phục.

**Kết luận kỹ thuật:** tách client vận hành khỏi danh tính ứng dụng trong **SPRING_VAULT** gồm hai lớp. Ở Java, dùng **VaultOperations/VaultTemplate** và dependency injection rõ ràng. Ở Vault/hạ tầng, phải tách **workload identity, ACL policy, token/session và môi trường chứa credential**. Chỉ khi cả hai lớp được áp dụng, runtime mới có thể xử lý nghiệp vụ KV, Transit, PKI và vòng đời secret mà không sở hữu quyền quản trị Vault.

## Tài liệu tham khảo chính thức

- [Spring Vault — Introduction to VaultTemplate](https://docs.spring.io/spring-vault/reference/vault/imperative-template.html).
- [Spring Vault — VaultTemplate API](https://docs.spring.io/spring-vault/reference/api/java/org/springframework/vault/core/VaultTemplate.html).
- [Spring Vault — VaultSysOperations API](https://docs.spring.io/spring-vault/reference/api/java/org/springframework/vault/core/VaultSysOperations.html).
- [Spring Vault — Authentication Methods](https://docs.spring.io/spring-vault/reference/vault/authentication.html).
- [Spring Vault — SessionManager API](https://docs.spring.io/spring-vault/reference/api/java/org/springframework/vault/authentication/SessionManager.html).
- [HashiCorp Vault — Policies](https://developer.hashicorp.com/vault/docs/concepts/policies).
- [HashiCorp Vault — System Mounts API](https://developer.hashicorp.com/vault/api-docs/system/mounts).
