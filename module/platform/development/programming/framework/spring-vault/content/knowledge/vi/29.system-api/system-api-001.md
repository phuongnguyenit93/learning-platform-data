# VaultSysOperations và phạm vi thao tác quản trị

## 1. Mục tiêu bài học và vị trí của System API

**HashiCorp Vault** có hai nhóm nhu cầu truy cập khác nhau. Một ứng dụng Java thông thường đọc KV secrets, xin dynamic credentials, mã hóa bằng Transit hoặc lấy chứng thư PKI. Người vận hành Vault lại cần biết máy chủ có **initialized/sealed/standby** hay không, những secrets engine và authentication method nào đang được bật, chính sách ACL nào đang có hiệu lực, và đôi khi phải thay đổi cấu hình hệ thống.

Trong **Spring Vault**, **VaultOperations** (thường do **VaultTemplate** triển khai) là điểm vào để làm việc với Vault; gọi **opsForSys()** nhận một **VaultSysOperations** dành cho *một tập thao tác quản trị và trạng thái hệ thống*. Các lời gọi này đi tới **System Backend** của Vault, chủ yếu dưới tiền tố HTTP **/v1/sys/**.

Bài học giúp bạn:

1. Hiểu **VaultSysOperations** làm gì, khác gì với **VaultKeyValueOperations**, **VaultTransitOperations**, **VaultPkiOperations** và các thao tác token/lease.
2. Phân loại thao tác quan sát, thay đổi mount, quản lý ACL policy và thao tác khởi tạo/seal.
3. Dùng Java đọc trạng thái Vault và danh sách mount trong một **công cụ quản trị nội bộ**.
4. Hiểu sự khác biệt giữa *API Java có phương thức* và *danh tính workload được quyền gọi endpoint*.
5. Thiết kế policy quyền tối thiểu, tách danh tính admin và ứng dụng, kiểm soát lỗi, giám sát và kiểm thử tích hợp.

**Giới hạn quan trọng:** **VaultSysOperations** chỉ bao phủ **một phần** System Backend; HashiCorp Vault có nhiều endpoint **sys/** khác (audit, leases, capabilities, wrapping, raft, v.v.). Không suy diễn rằng phương thức không có trong interface thì Vault không hỗ trợ nghiệp vụ đó.

## 2. Bức tranh tổng thể: Ops nghiệp vụ và Ops hệ thống

~~~mermaid
flowchart LR
    A["Ứng dụng Java"] --> B["VaultOperations / VaultTemplate"]
    B --> C["opsForKeyValue(...)"]
    B --> D["opsForTransit(...)"]
    B --> E["opsForPki(...)"]
    B --> F["opsForSys()"]
    C --> G["KV secrets engine"]
    D --> H["Transit secrets engine"]
    E --> I["PKI secrets engine"]
    F --> J["System Backend: /v1/sys/*"]
    K["Token + ACL policy"] -. "Kiểm tra từng endpoint" .-> G
    K -. "Kiểm tra từng endpoint" .-> H
    K -. "Kiểm tra từng endpoint" .-> I
    K -. "Kiểm tra từng endpoint" .-> J
~~~

Các lời gọi từ cùng một **VaultTemplate** thường dùng cùng cấu hình địa chỉ Vault, TLS và cơ chế xác thực mà template được cấp. Khi gọi **opsForSys()**, ứng dụng **không tự có quyền admin**; Vault vẫn kiểm tra token, policy, namespace (nếu dùng) và các ràng buộc liên quan đến endpoint.

| Mục tiêu | API Spring Vault thích hợp | Ví dụ |
| --- | --- | --- |
| Đọc KV v2 | **opsForKeyValue(...)** hoặc **opsForVersionedKeyValue(...)** | Đọc cấu hình dịch vụ |
| Mã hóa/giải mã | **opsForTransit(...)** | Bảo vệ giá trị lưu database |
| Cấp chứng thư | **opsForPki(...)** | Xin certificate cho workload |
| Quản trị auth, mount, ACL và trạng thái Vault | **opsForSys()** | Liệt kê mount, bật auth method, xem policy |
| Quản lý vòng đời token | **opsForToken()** hoặc authentication/session tương ứng | Lookup/renew/revoke token |
| Response wrapping | **opsForWrapping()** | Bàn giao một phản hồi bằng wrapping token |

**Tình huống thực tế:** ứng dụng thanh toán cần đọc **kv/payment/data/config** chỉ nên được cấp quyền **read** cho path đó. Một công cụ triển khai Vault được phép liệt kê mounts hoặc tạo policy nên dùng **danh tính quản trị riêng**, với quyền giới hạn theo hành động. Không đưa quyền **sys/** vào policy của ứng dụng thanh toán chỉ vì nó phụ thuộc Spring Vault.

## 3. Danh mục phương thức VaultSysOperations

Các nhóm sau tóm tắt interface **org.springframework.vault.core.VaultSysOperations**. Tên chính xác cần dựa trên phiên bản Spring Vault trong dự án.

### 3.1 Trạng thái và khởi tạo Vault

| Phương thức | Ý nghĩa | Mức độ tác động |
| --- | --- | --- |
| **isInitialized()** | Trả lời Vault đã được khởi tạo hay chưa. | Quan sát |
| **health()** | Đọc **VaultHealth**: initialized, sealed, standby, version và trạng thái liên quan. | Quan sát; cần hiểu HTTP status |
| **getUnsealStatus()** | Lấy **VaultUnsealStatus**: sealed, shares, threshold, progress. | Quan sát |
| **initialize(VaultInitializationRequest)** | Khởi tạo Vault **chưa initialized**, tạo thông tin khóa/recovery và root token theo quy trình seal. | **Rất nhạy cảm; bootstrap một lần** |
| **unseal(String keyShare)** | Gửi một phần unseal key trong cấu hình sử dụng key shares thủ công. | **Rất nhạy cảm** |
| **seal()** | Đưa Vault vào trạng thái sealed. | **Có thể gây gián đoạn dịch vụ** |

Không bao giờ gọi **initialize()**, **seal()** hay **unseal()** như một bước health check, startup hook hoặc retry nghiệp vụ. Với auto-unseal qua KMS/HSM, quy trình vận hành khác với thủ công nhập Shamir key shares; phải theo cấu hình seal thực tế và kế hoạch khôi phục của hệ thống.

### 3.2 Secrets engine mounts

| Phương thức | Tác động | API Vault tương ứng |
| --- | --- | --- |
| **getMounts()** | Liệt kê thông tin secrets engine đã mount | **GET /v1/sys/mounts** |
| **mount(path, VaultMount)** | Bật secrets engine tại một mount path | **POST /v1/sys/mounts/{path}** |
| **unmount(path)** | Tắt secrets engine tại mount path | **DELETE /v1/sys/mounts/{path}** |

**Mount path** là vị trí trong cây đường dẫn Vault, ví dụ **kv-app/** hoặc **transit/**; **engine type** có thể là **kv**, **transit**, **pki**. Với KV v2, ngoài type **kv** còn cần tùy chọn mount **version=2**, nếu không có thể nhận KV v1 tùy cấu hình.

**Cảnh báo:** **unmount** có thể dẫn đến mất quyền truy cập dữ liệu tại mount và thu hồi secrets/leases liên quan; đây là thao tác vận hành có ảnh hưởng lớn. Ví dụ thực hành chỉ bật mount mới trong Vault lab riêng.

### 3.3 Authentication method mounts

| Phương thức | Tác động | API Vault |
| --- | --- | --- |
| **getAuthMounts()** | Liệt kê auth methods đang bật | **GET /v1/sys/auth** |
| **authMount(path, VaultMount)** | Bật auth method tại mount path | **POST /v1/sys/auth/{path}** |
| **authUnmount(path)** | Tắt auth method tại mount path | **DELETE /v1/sys/auth/{path}** |

Ví dụ **authMount("approle-lab", VaultMount.create("approle"))** tạo auth method có endpoint đăng nhập tại **auth/approle-lab/**, nếu token quản trị có đủ quyền và mount chưa tồn tại. Tham số **path** là tên mount (không tự thêm **auth/** khi gọi phương thức). Bật auth method **chưa đồng nghĩa** đã cấu hình roles, mappings, bound service account hay policy cho workload.

Tắt auth method có thể làm hỏng luồng đăng nhập của các workload đang dùng method đó; cần kiểm tra dependency và phương án rollback trước khi thực hiện.

### 3.4 ACL policy

| Phương thức | Ý nghĩa |
| --- | --- |
| **getPolicyNames()** | Liệt kê tên ACL policy |
| **getPolicy(name)** | Đọc đối tượng **Policy** khi biểu diễn chính sách tương thích; có thể trả **null** nếu không tồn tại |
| **createOrUpdatePolicy(name, Policy)** | Tạo hoặc thay thế/cập nhật chính sách đã đặt tên |
| **deletePolicy(name)** | Xóa ACL policy đã đặt tên |

**Lưu ý tương thích:** đối tượng **Policy** của Spring Vault biểu diễn policy thành dữ liệu có cấu trúc JSON. Với policy lưu ở dạng **HCL**, phương thức **getPolicy(name)** có thể ném **UnsupportedOperationException** thay vì trả về được một **Policy**. Trong trường hợp cần kiểm tra HCL nguyên gốc, sử dụng CLI **vault policy read <name>** hoặc endpoint đọc policy phù hợp cho công cụ quản trị thay vì mặc định mọi policy đều giải mã được thành **Policy** của Spring Vault.

Thay đổi policy có thể **tác động tức thời** đến các token/danh tính đang có chính sách đó. Xóa policy không chỉ là thao tác dọn tên; nó có thể làm mất quyền của các workload đang chạy.

## 4. Phân loại cấp quyền quản trị

Một hệ thống thường cần nhiều danh tính thay vì một token có mọi quyền:

| Danh tính | Việc cần làm | Quyền khuyến nghị |
| --- | --- | --- |
| **Runtime workload** | Đọc secret, gọi Transit/PKI theo nghiệp vụ | Chỉ các path engine phục vụ workload |
| **Monitoring/diagnostic agent** | Kiểm tra health và metadata trạng thái phù hợp | Quyền quan sát tối thiểu, không cấp mount/unmount/policy write |
| **Provisioning job** | Bật mount mới, tạo policy trong phạm vi tài nguyên dự án | Chỉ các **sys/** endpoint và hành động được giao |
| **Break-glass operator** | Xử lý init, seal/unseal, sự cố nghiêm trọng | Quy trình vận hành đặc biệt, có quản trị khóa và audit riêng |

Trong Vault ACL, quyền như **read**, **list**, **create**, **update**, **delete** là các **capabilities** được gắn với đường dẫn. Một số endpoint **sys/** còn yêu cầu **sudo** capability bên cạnh capability thao tác thông thường; đây là capability **của Vault**, không phải lệnh Linux **sudo**.

Không suy từ **read** ra quyền **list** hoặc từ **update** ra **create**. Cần kiểm tra tài liệu endpoint, version Vault và capability thực tế của danh tính.

### Ví dụ policy cho ứng dụng nghiệp vụ

Đây là policy **runtime workload** dùng KV v2, **không có quyền system admin**:

~~~hcl
# app-runtime.hcl
path "kv-app/data/payment/config" {
  capabilities = ["read"]
}
~~~

Quản trị viên có thể tạo policy bằng CLI:

~~~bash
vault policy write app-runtime app-runtime.hcl
~~~

Sau đó gắn **app-runtime** với danh tính workload thông qua cơ chế auth phù hợp (Kubernetes, AppRole, v.v.). **Không cấp policy root** hoặc wildcard **path "*"** cho ứng dụng để sửa lỗi HTTP 403.

### Ví dụ policy quan sát mounts cho công cụ nội bộ

Policy minh họa nhằm cấp quyền **đọc danh sách secrets engine** tại **/sys/mounts**:

~~~hcl
path "sys/mounts" {
  capabilities = ["read"]
}
~~~

Policy này **không có quyền tạo hay xóa mount**. Với các API khác như **sys/auth**, **sys/policy/** hoặc **sys/policies/acl/**, cần thêm path và capability đúng theo endpoint mà công cụ thật sự gọi. Một số phiên bản/endpoint đòi **sudo** bổ sung; phải thử với token thực tế trong môi trường lab trước khi triển khai.

Kiểm tra quyền của danh tính đang đăng nhập bằng:

~~~bash
vault token capabilities sys/mounts
vault token capabilities sys/mounts/transit-lab
vault token capabilities sys/auth/approle-lab
vault token capabilities sys/policy/app-runtime
~~~

Một kết quả như **read** hoặc **deny** chỉ phản ánh khả năng theo policy trên path; việc request thành công còn phụ thuộc ràng buộc tham số, trạng thái Vault, version, path chính xác và các cơ chế kiểm soát khác.

## 5. Đọc trạng thái Vault từ Spring Boot

Với dependency **org.springframework.vault:spring-vault-core** và một bean **VaultOperations** đã được cấu hình, có thể viết một service chỉ quan sát.

~~~java
import org.springframework.stereotype.Service;
import org.springframework.vault.core.VaultOperations;
import org.springframework.vault.core.VaultSysOperations;
import org.springframework.vault.support.VaultHealth;
import org.springframework.vault.support.VaultUnsealStatus;

@Service
public class VaultSystemStatusService {

    private final VaultSysOperations sys;

    public VaultSystemStatusService(VaultOperations operations) {
        this.sys = operations.opsForSys();
    }

    public Status readStatus() {
        VaultHealth health = sys.health();
        return new Status(
                health.isInitialized(),
                health.isSealed(),
                health.isStandby(),
                health.getVersion()
        );
    }

    public boolean initialized() {
        return sys.isInitialized();
    }

    public boolean currentlySealed() {
        VaultUnsealStatus status = sys.getUnsealStatus();
        return status.isSealed();
    }

    public record Status(
            boolean initialized,
            boolean sealed,
            boolean standby,
            String version) {
    }
}
~~~

**opsForSys()** kế thừa endpoint, TLS và xác thực từ **VaultOperations**. Không có bước đăng nhập admin ẩn nào trong đoạn mã. Thực tế **getUnsealStatus()** và **isInitialized()** hữu ích cho chẩn đoán; còn việc đọc health nên được giám sát qua endpoint/probe được thiết kế phù hợp.

**Chú ý với health:** endpoint **/sys/health** có **HTTP status** mang ý nghĩa riêng. Ví dụ mặc định **200** khi Vault active và unsealed, **429** khi standby, **501** khi uninitialized và **503** khi sealed. Tùy HTTP client, cấu hình và cách Spring Vault xử lý phản hồi, lời gọi **health()** có thể ném **VaultException** trong một số trạng thái thay vì luôn trả đối tượng **VaultHealth**. Vì vậy health probe cần phân biệt **trạng thái server** với **lỗi giao tiếp**, không kết luận rằng mọi status khác 200 đều là hỏng hệ thống.

Có thể quan sát bằng CLI trong Vault lab:

~~~bash
vault status
# Lệnh trả thông tin Initialized, Sealed, HA Mode...

# Xem cả HTTP status lẫn response, dùng HTTPS theo cấu hình Vault lab:
curl -i "$VAULT_ADDR/v1/sys/health"
~~~

Không sử dụng **initialize()** hoặc **unseal()** tự động khi check health thất bại. Vấn đề mạng, token, sealed, standby và chưa initialized là các trạng thái khác nhau; mỗi trạng thái cần quy trình xử lý riêng.

## 6. Liệt kê secrets engine và auth method bằng Java

Một công cụ inventory có quyền phù hợp có thể dùng **getMounts()** và **getAuthMounts()**. Ví dụ:

~~~java
import java.util.Map;
import java.util.TreeMap;

import org.springframework.stereotype.Service;
import org.springframework.vault.core.VaultOperations;
import org.springframework.vault.core.VaultSysOperations;
import org.springframework.vault.support.VaultMount;

@Service
public class VaultMountInventory {

    private final VaultSysOperations sys;

    public VaultMountInventory(VaultOperations operations) {
        this.sys = operations.opsForSys();
    }

    public Map<String, String> secretEngineTypes() {
        Map<String, String> result = new TreeMap<>();

        for (Map.Entry<String, VaultMount> entry
                : sys.getMounts().entrySet()) {
            result.put(entry.getKey(), entry.getValue().getType());
        }

        return result;
    }

    public Map<String, String> authMethodTypes() {
        Map<String, String> result = new TreeMap<>();

        for (Map.Entry<String, VaultMount> entry
                : sys.getAuthMounts().entrySet()) {
            result.put(entry.getKey(), entry.getValue().getType());
        }

        return result;
    }
}
~~~

Ví dụ một kết quả inventory (tùy môi trường):

~~~text
Secrets engines:
  kv-app/   -> kv
  transit/  -> transit
  pki/      -> pki
Auth methods:
  token/      -> token
  kubernetes/ -> kubernetes
  approle/    -> approle
~~~

Kết quả này chỉ thể hiện **engine type/mount path**. Nó **không chứng minh** ai được phép đọc secret tại mount, mount có đầy đủ cấu hình hợp lệ hay auth method đã có các role chính xác. Nếu cần kiểm tra KV v1/v2, đọc thêm **options.version** của **VaultMount**, không dựa vào duy nhất **getType() == "kv"**.

Tránh phơi bày toàn bộ mount inventory ra endpoint REST công khai. Danh sách mounts/auth methods có thể tiết lộ kiến trúc nội bộ, engine đang dùng hoặc cách xác thực của tổ chức.

## 7. Thao tác thay đổi cấu hình: cách dùng và ranh giới

Chỉ các công cụ provisioning được cấp quyền mới thực hiện nhóm thao tác thay đổi. Đoạn Java sau minh họa **một mount mới trong Vault lab**, không nên đưa vào **@PostConstruct**, startup hook hay request handler của ứng dụng nghiệp vụ.

~~~java
import org.springframework.vault.core.VaultOperations;
import org.springframework.vault.core.VaultSysOperations;
import org.springframework.vault.support.VaultMount;

public final class LabVaultProvisioner {

    private static final String LAB_PATH = "transit-lab";

    private final VaultSysOperations sys;

    public LabVaultProvisioner(VaultOperations adminOperations) {
        this.sys = adminOperations.opsForSys();
    }

    public void enableLabTransit() {
        // Xác minh trạng thái hiện có trước khi thay đổi.
        boolean alreadyExists = sys.getMounts().keySet().stream()
                .anyMatch(path -> path.equals(LAB_PATH + "/"));

        if (!alreadyExists) {
            // Chỉ chạy trong Vault lab với danh tính có quyền cấp mount.
            sys.mount(LAB_PATH, VaultMount.create("transit"));
        }
    }
}
~~~

Phương thức **mount** có thể lỗi nếu mount đã tồn tại, token thiếu quyền hoặc request không hợp lệ. Kiểm tra trước khi gọi chỉ giúp giảm thay đổi dư thừa; nó **không tạo transaction**. Một provisioning job khác có thể mount trong khoảng giữa hai request, vì vậy vẫn phải xử lý xung đột/race condition và đối chiếu kết quả thực tế sau lời gọi.

Để tắt engine hoặc auth method:

~~~java
// Ví dụ tên phương thức của API; KHÔNG tự động chạy:
// sys.unmount("transit-lab");
// sys.authUnmount("approle-lab");
~~~

**Hậu quả khác nhau:** **unmount** có thể làm mất khả năng truy cập dữ liệu tại secrets engine và thu hồi leases liên quan; **authUnmount** có thể ngăn workload tiếp tục đăng nhập và ảnh hưởng đến luồng token. Đây không phải thao tác dọn bộ nhớ vô hại. Trước khi xóa mount, cần biết dữ liệu nào tồn tại, ứng dụng nào phụ thuộc, quy trình sao lưu/khôi phục và ai đã phê duyệt thay đổi.

### Tạo policy có cấu trúc trong provisioning job

**Policy** là model hỗ trợ tạo ACL dạng có cấu trúc. Đoạn minh họa sau cấp quyền đọc đúng một KV v2 secret:

~~~java
import org.springframework.vault.core.VaultOperations;
import org.springframework.vault.core.VaultSysOperations;
import org.springframework.vault.support.Policy;

public final class LabPolicyProvisioner {

    private final VaultSysOperations sys;

    public LabPolicyProvisioner(VaultOperations adminOperations) {
        this.sys = adminOperations.opsForSys();
    }

    public void createAppReadPolicy() {
        Policy.Rule onlyConfig = Policy.Rule.builder()
                .path("kv-app/data/payment/config")
                .capabilities("read")
                .build();

        Policy policy = Policy.of(onlyConfig);
        sys.createOrUpdatePolicy("app-runtime", policy);
    }
}
~~~

Lệnh **createOrUpdatePolicy(...)** thay đổi tài nguyên ACL ở Vault. Nó không cấp policy đó cho workload ngay lập tức; người quản trị còn cần cấu hình mapping/binding ở auth method, ví dụ Kubernetes role hoặc AppRole. Mặt khác, nếu **app-runtime** đã được cấp cho các danh tính, nội dung policy mới có thể ảnh hưởng quyền của chúng ngay lập tức. Provisioning phải kiểm tra bản policy đang có, đánh giá diff và kiểm chứng quyền sau áp dụng.

Spring Vault **getPolicy(name)** chỉ nên dùng khi chính sách được lưu/diễn giải ở dạng JSON phù hợp. Nếu chính sách do người vận hành tạo dưới dạng HCL, không xem **UnsupportedOperationException** là bằng chứng policy không tồn tại.

### Khi nào dùng API hệ thống thô?

**VaultSysOperations** không có phương thức chuyên dụng cho mọi endpoint **/sys/**. Ví dụ kiểm tra capabilities token, cấu hình audit, lease operations hay một số endpoint vận hành khác có API riêng hoặc cần HTTP call trực tiếp. Với **VaultOperations.read(...)**, **write(...)**, HTTP client hoặc Vault CLI, luôn dùng path và HTTP method đúng tài liệu endpoint; **không** cố ép một endpoint vào một method Java chỉ vì cùng tiền tố **sys/**.

## 8. Init, seal và unseal: ý nghĩa vận hành

Ba thao tác này có hậu quả lớn hơn nhiều so với đọc trạng thái.

**initialize(VaultInitializationRequest)**

- Chỉ dùng cho Vault **chưa initialized** theo quy trình triển khai mới.
- Kết quả có thể chứa vật liệu recovery/unseal và token đặc quyền; phải xử lý bằng cơ chế bàn giao khóa bảo mật của tổ chức.
- Với cấu hình auto-unseal, cách tạo/quản lý recovery keys khác với Shamir seal thủ công.
- Không tạo lại các key shares/tokens bằng cách gọi initialize trong ứng dụng đã chạy.

**seal()**

- Đưa Vault vào trạng thái sealed, làm nhiều thao tác secret/auth thông thường không hoạt động cho đến khi unseal.
- Có thể ảnh hưởng đến tất cả workload đang dựa vào Vault. Không gọi tự động khi ứng dụng Java thấy lỗi kết nối hoặc lỗi đăng nhập.
- Chỉ thực hiện trong quy trình vận hành với đánh giá tác động và giám sát.

**unseal(String keyShare)**

- Dành cho quy trình unseal thủ công cần các key shares theo ngưỡng cấu hình.
- **Không lưu unseal key shares trong code, env của workload thông thường, Git, log hoặc unit test**.
- Không tái sử dụng token runtime để giả làm tác nhân phục hồi hạ tầng; hệ thống có auto-unseal cần tuân thủ cơ chế đó.

### Bảng quyết định thực tế

| Tình huống | Kiểm tra phù hợp | Có nên gọi init/seal/unseal từ ứng dụng? |
| --- | --- | --- |
| Vault trả 403 khi đọc KV | Policy workload, auth, đúng KV v2 path | Không |
| Vault ở HA standby | Health/status và tuyến request đến cluster | Không |
| Vault báo sealed | Health, trạng thái seal, runbook operator | Không tự động |
| Vault chưa initialized trong môi trường lab mới | Xác nhận kế hoạch bootstrap | Chỉ theo quy trình khởi tạo được kiểm soát |
| App không tìm thấy Transit mount | Inventory và cấu hình deployment | Provisioning job riêng có thể tạo mount nếu được giao |
| Worker dùng auth method bị tắt | Inventory auth mounts, role/mapping | Điều tra trước khi bật lại; tránh thao tác mù |

## 9. Lỗi thường gặp, khả năng quan sát và kiểm thử

### 9.1 Lỗi phải phân loại

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| **403 permission denied** | Token không có capability đúng hoặc endpoint yêu cầu thêm **sudo**. | Kiểm tra policy cho path thực tế; không tăng thẳng lên root. |
| **404 / unsupported path** | Sai mount path, nhầm **sys/mounts** với engine path, engine chưa bật, hoặc hạn chế hiển thị. | Kiểm tra path và version Vault. |
| **400** khi mount | Engine type hoặc options sai, mount trùng, request không hợp lệ. | Xem cấu hình và error code; không retry vô hạn. |
| **getPolicy** ném **UnsupportedOperationException** | Policy được lưu dạng HCL, không ánh xạ thành **Policy** JSON. | Đọc HCL bằng CLI/endpoint phù hợp. |
| **health()** thất bại khi Vault standby/sealed | HTTP health dùng status đặc biệt, client coi là lỗi. | Phân biệt HTTP status với lỗi mạng; cấu hình probe phù hợp. |
| **503** hoặc timeout | Vault sealed, quá tải, tạm bảo trì hoặc kết nối lỗi. | Kiểm tra health/audit/tracing, giảm retry dồn dập. |
| Sau **unmount** không đọc được secret | Engine đã tắt, dữ liệu/lease có thể bị ảnh hưởng. | Thực hiện phục hồi theo runbook; tránh mount lại mù. |

**Giám sát:** ghi thời gian phản hồi, loại thao tác (read-only/mutation), endpoint đã làm sạch, mã trạng thái, Vault cluster/namespace phù hợp và correlation ID. Với thao tác admin, bật và bảo vệ audit devices theo chính sách tổ chức. Không log giá trị token, unseal key, root token, response nhạy cảm hoặc toàn bộ nội dung policy có thông tin bí mật.

**Retry:** có thể retry có giới hạn cho lỗi giao tiếp tạm thời. Không tự retry các lệnh **initialize**, **seal**, **unmount**, **authUnmount**, **deletePolicy** vì nhiều thao tác có hậu quả nghiêm trọng hoặc kết quả không rõ khi timeout. Trước mọi retry mutation, phải đọc trạng thái thật và thực hiện đối chiếu.

### 9.2 Kiểm thử tích hợp trong Vault test

Kiểm thử về **VaultSysOperations** nên chạy trên Vault riêng cho test, dùng xác thực được cấp quyền **read** các endpoint cần kiểm tra. Không dùng Vault production để unit/integration test các phương thức thay đổi cấu hình.

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import java.util.Map;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.vault.core.VaultOperations;
import org.springframework.vault.core.VaultSysOperations;
import org.springframework.vault.support.VaultMount;

@SpringBootTest
class VaultSystemInventoryIT {

    @Autowired
    VaultOperations vaultOperations;

    @Test
    void canReadInitializationStateAndSecretEngineInventory() {
        VaultSysOperations sys = vaultOperations.opsForSys();

        // Lab phải initialized và có quyền đọc danh sách mounts.
        assertThat(sys.isInitialized()).isTrue();

        Map<String, VaultMount> mounts = sys.getMounts();

        assertThat(mounts).isNotEmpty();
        assertThat(mounts.values())
                .allSatisfy(mount -> assertThat(mount.getType()).isNotBlank());
    }
}
~~~

Bài test này kiểm tra kết nối thật, phương thức **opsForSys()**, quyền danh sách mounts và dữ liệu trả về. Test chỉ có ý nghĩa nếu Vault test đang hoạt động và token test có đủ quyền. Nếu policy chỉ cho phép đọc KV, **getMounts()** có thể bị 403; đó là kết quả đúng của phân quyền và không phải lý do mở rộng quyền workload.

**Những kiểm thử quan trọng khác:**

1. Token runtime chỉ có **kv-app/data/payment/config** phải bị từ chối khi gọi endpoint quản trị như **sys/mounts/transit-lab**; kiểm chứng quyền tối thiểu.
2. Token diagnostics có quyền quan sát inventory nhưng không có quyền **mount/unmount**.
3. Provisioning job trên Vault test có thể tạo **transit-lab**, đọc lại trạng thái rồi dọn sạch theo runbook riêng; không dùng dữ liệu quan trọng.
4. Một policy HCL có sẵn được đọc bằng CLI bình thường nhưng **getPolicy(name)** phải được xử lý nếu bị **UnsupportedOperationException**.
5. Health probe phân biệt **active**, **standby**, **sealed**, **uninitialized** và lỗi mạng theo HTTP semantics thực tế.

## 10. Checklist triển khai có kiểm soát

- Xác nhận trước **endpoint sys/** thực sự cần và phương thức **VaultSysOperations** tương ứng.
- Tách bean/danh tính quản trị khỏi **VaultOperations** dùng cho nghiệp vụ; tránh cung cấp route REST cho phép client bên ngoài gọi trực tiếp mọi method **opsForSys()**.
- Thiết kế Vault policy theo **path + capabilities + sudo nếu endpoint yêu cầu**, kiểm tra quyền với **vault token capabilities** và audit.
- Chỉ dùng **isInitialized()**, **getUnsealStatus()**, **health()** cho quan sát phù hợp; hiểu các status health đặc biệt.
- Gọi **mount/authMount/createOrUpdatePolicy** trong provisioning có đánh giá thay đổi, idempotency và xác minh readback.
- Dành **initialize/seal/unseal/unmount/authUnmount/deletePolicy** cho quy trình vận hành được kiểm soát với quản trị khóa, sao lưu, cảnh báo và kiểm tra ảnh hưởng.
- Kiểm tra lỗi 403/404/409/5xx đúng nguyên nhân, không tự nâng quyền hoặc retry mutation vô hạn.
- Viết kiểm thử tích hợp trên Vault test cho cả đường thành công và đường bị từ chối do ACL.

Khi sử dụng **SPRING_VAULT**, việc chọn **VaultSysOperations** cho các thao tác quản trị phải đi kèm một **ranh giới quyền rõ ràng**: *đối tượng Java cho phép xây dựng lời gọi; Vault policy và trạng thái hệ thống mới quyết định lời gọi nào được thực thi*. Tách trách nhiệm như vậy giúp ứng dụng Java khai thác KV, Transit, PKI và token/lease đúng nghiệp vụ mà không phải mang theo quyền điều khiển Vault.

### Tài liệu tham khảo chính thức

- [Spring Vault — VaultSysOperations API](https://docs.spring.io/spring-vault/reference/api/java/org/springframework/vault/core/VaultSysOperations.html).
- [Spring Vault — VaultOperations API](https://docs.spring.io/spring-vault/reference/api/java/org/springframework/vault/core/VaultOperations.html).
- [Spring Vault — VaultMount API](https://docs.spring.io/spring-vault/reference/api/java/org/springframework/vault/support/VaultMount.html).
- [Spring Vault — Policy API](https://docs.spring.io/spring-vault/reference/api/java/org/springframework/vault/support/Policy.html).
- [HashiCorp Vault — System Backend](https://developer.hashicorp.com/vault/api-docs/system).
- [HashiCorp Vault — Sys Mounts API](https://developer.hashicorp.com/vault/api-docs/system/mounts).
- [HashiCorp Vault — Sys Auth API](https://developer.hashicorp.com/vault/api-docs/system/auth).
- [HashiCorp Vault — Sys Policies API](https://developer.hashicorp.com/vault/api-docs/system/policies).
- [HashiCorp Vault — Sys Health API](https://developer.hashicorp.com/vault/api-docs/system/health).
