# Liệt kê và cấu hình auth mount trong Vault System API

Trong chương **API hệ thống**, chúng ta tìm hiểu cách kiểm tra và quản lý các *authentication methods* (phương thức xác thực) đã được bật trong HashiCorp Vault. Một ứng dụng Java dùng **Spring Vault** thường đăng nhập bằng AppRole, Kubernetes, AWS IAM hoặc cơ chế workload khác trước khi đọc KV secrets, dùng Transit encryption hay gọi PKI. Để những lượt đăng nhập đó hoạt động, **người vận hành** cần biết auth method được mount ở đâu, đang dùng loại nào, được cấu hình giới hạn token ra sao và chính sách nào cho phép thao tác.

Bài này đi sâu vào hai nhóm công việc:

1. **Liệt kê/kiểm tra auth mount**: lấy danh sách method, nhận diện `path`, `type`, `accessor` và cấu hình hiện hành.
2. **Cấu hình auth mount**: bật method ở đường dẫn mong muốn, tune TTL/hiển thị, xác minh kết quả và xử lý thay đổi an toàn.

Ví dụ xuyên suốt sử dụng auth method **AppRole** có mount path `approle-ci/` để các workload CI/CD xác thực. Các ví dụ khác như Kubernetes cũng tuân cùng hợp đồng `sys/auth` nhưng có API cấu hình riêng. Phần thực hành quản trị phải được chạy bằng danh tính có **quyền quản trị tách biệt** với token mà ứng dụng sử dụng hằng ngày.

## 1. Phân biệt auth method, auth mount và secrets engine

Vault có nhiều phương thức xác thực: `token`, `approle`, `kubernetes`, `userpass`, `oidc` và một số phương thức khác. **Auth method** là loại backend thực hiện kiểm chứng danh tính; **auth mount** là một instance của backend được bật tại một đường dẫn cụ thể. Các mount đều có tiền tố `auth/` khi dùng để đăng nhập.

Ví dụ, tổ chức muốn tách hai môi trường:

| Loại backend | Mount path trong kết quả `sys/auth` | API đăng nhập (ví dụ) | Mục đích |
| --- | --- | --- | --- |
| `approle` | `approle-ci/` | `auth/approle-ci/login` | Workload CI/CD |
| `approle` | `approle-batch/` | `auth/approle-batch/login` | Batch job |
| `kubernetes` | `k8s-prod/` | `auth/k8s-prod/login` | Pod sản xuất |
| `token` | `token/` | `auth/token/lookup-self` và các API token | Xử lý token nền tảng |

Hai auth mount cùng `type=approle` **không tự động chia sẻ role, cấu hình và policy**: `auth/approle-ci/role/orders` và `auth/approle-batch/role/orders` thuộc hai backend khác nhau.

Điểm phân biệt quan trọng:

- `sys/auth` quản lý **đăng ký và cấu hình chung của auth mount**: liệt kê, bật, tắt, đọc metadata và tune.
- `auth/<mount>/...` là API **nghiệp vụ bên trong auth method**, ví dụ `auth/approle-ci/role/orders` và `auth/approle-ci/login`.
- `sys/mounts` dùng để quản lý **secrets engine** (KV, Transit, PKI...). Không bật auth method bằng `vault secrets enable`.
- `sys/mounts/auth/<mount>` và `sys/mounts/auth/<mount>/tune` là các đường dẫn hệ thống bổ sung để xem/tune auth mount ở những phiên bản Vault hỗ trợ; chính sách của các đường dẫn này không tự động dùng chung với `sys/auth/...`.

Đừng nhầm thao tác “bật AppRole” với “tạo AppRole role”. Sau khi bật mount `approle-ci/`, chưa có role `orders`, chính sách token, hoặc thông tin đăng nhập phù hợp. Phải thực hiện cấu hình backend và cấp policy riêng theo nhu cầu.

## 2. Sơ đồ luồng vận hành

~~~mermaid
flowchart TD
    A[Người vận hành lấy inventory từ sys/auth] --> B{Mount approle-ci đã tồn tại?}
    B -- Chưa --> C[Bật type approle tại path approle-ci]
    B -- Có --> D{Type có đúng approle?}
    D -- Sai --> E[Dừng: path đang bị backend khác sử dụng]
    D -- Đúng --> F[Đọc mount config và tune]
    C --> F
    F --> G[Cấu hình TTL và mô tả theo chính sách]
    G --> H[Đọc lại sys/auth và tune]
    H --> I[Cấu hình AppRole role và policy riêng]
    I --> J[Thử login bằng workload test]
    J --> K[Đo token TTL và quyền thực tế]
~~~

Khi hệ thống đã hoạt động, không nên gọi `enable` hoặc `tune` tự động trong quá trình khởi động mọi replica Spring Boot. Đây là thay đổi **control plane** có thể ảnh hưởng nhiều workload, nên quản lý qua công cụ triển khai, quy trình phê duyệt và danh tính operator riêng. Ứng dụng business chỉ dùng phương thức đăng nhập đã được provision.

## 3. Bảng hợp đồng HTTP API `sys/auth`

Các đường dẫn dưới đây nằm dưới tiền tố `/v1/` trong HTTP API:

| Nhiệm vụ | HTTP method | Đường dẫn | Quyền ACL chính |
| --- | --- | --- | --- |
| Liệt kê auth mount | `GET` | `/v1/sys/auth` | `read` trên `sys/auth` |
| Bật auth mount | `POST` | `/v1/sys/auth/<path>` | `create/update` và `sudo` trên đường dẫn mount |
| Đọc metadata của mount | `GET` | `/v1/sys/auth/<path>` | `read` và `sudo` |
| Đọc cấu hình tune | `GET` | `/v1/sys/auth/<path>/tune` | `read` và `sudo` |
| Thay cấu hình tune | `POST` | `/v1/sys/auth/<path>/tune` | `update` và `sudo` |
| Tắt auth mount | `DELETE` | `/v1/sys/auth/<path>` | `delete` và `sudo` |

**`sudo` trong Vault ACL không phải câu lệnh `sudo` của hệ điều hành.** Đây là capability bổ sung được yêu cầu trên các endpoint *root-protected*. Một token chỉ có `update` nhưng không có `sudo` sẽ bị từ chối khi tune hoặc bật auth mount.

Đường dẫn `<path>` là tên mount **không gồm `auth/`**. Ví dụ mount dùng để đăng nhập là `auth/approle-ci/login` thì quản lý bằng `sys/auth/approle-ci`. Tên auth mount không phải tên method: `approle-ci` là `path`; `approle` là `type`.

### 3.1. Liệt kê mount: `GET /sys/auth`

~~~bash
# Chạy bằng token operator có quyền xem inventory.
vault auth list

# Có thêm accessor và cấu hình mount.
vault auth list -detailed

# Trả về JSON, thuận tiện cho automation.
vault auth list -format=json

# Tương đương dùng System HTTP API.
curl --fail-with-body --silent --show-error \
  --header "X-Vault-Token: $VAULT_TOKEN" \
  "$VAULT_ADDR/v1/sys/auth"
~~~

Để tránh ghi token vào lịch sử terminal, ví dụ trên giả định `VAULT_TOKEN` đã được cấp qua môi trường bí mật phù hợp; trong môi trường thật cần ngăn việc log giá trị header. Chỉ dùng HTTPS/TLS tới Vault production.

Response từ `GET /v1/sys/auth` có `data` là map, các khóa là **mount path có dấu `/` cuối**:

~~~json
{
  "data": {
    "token/": {
      "type": "token",
      "accessor": "auth_token_example",
      "description": "token based credentials",
      "config": { "default_lease_ttl": 0, "max_lease_ttl": 0 }
    },
    "approle-ci/": {
      "type": "approle",
      "accessor": "auth_approle_example",
      "description": "AppRole cho CI workloads",
      "config": { "default_lease_ttl": 1800, "max_lease_ttl": 7200 }
    }
  }
}
~~~

JSON trên chỉ minh họa các trường quan trọng, không phải phản hồi đầy đủ; `accessor` là giá trị động do Vault phát sinh, không đoán theo tên. Một response thực còn có `request_id`, thông tin plugin, `local`, `seal_wrap`, `options` và các trường khác tùy phiên bản.

| Field | Diễn giải | Cách sử dụng |
| --- | --- | --- |
| Khóa `approle-ci/` | Đường dẫn mount hiện hành | Dùng để xác định endpoint login/role chính xác |
| `type` | Loại backend (`approle`, `kubernetes`...) | Kiểm tra mount có đúng loại dự kiến |
| `accessor` | Định danh mount do Vault tạo | Dùng trong identity alias/đối chiếu kiểm toán; không gán cố định |
| `description` | Nhãn phục vụ vận hành | Nên mô tả workload/nhóm dùng mount |
| `config.default_lease_ttl` | TTL mặc định cấp bởi mount, dạng giây trong response | Kiểm tra so với yêu cầu quản lý token |
| `config.max_lease_ttl` | TTL tối đa của mount theo cấu hình | Đối chiếu với giới hạn cluster và role |
| `config.token_type` | Kiểu token mặc định/ép kiểu theo mount | Cần hiểu khác biệt service token, batch token |
| `local`, `seal_wrap`, `options` | Thuộc tính hệ thống hoặc tùy chọn plugin | So sánh cấu hình theo hạ tầng đang dùng |

Khi một giá trị TTL bằng `0`, thường có nghĩa mount **kế thừa** cấu hình mặc định có liên quan; đó không phải chỉ báo token sẽ sống vĩnh viễn. Hãy đọc TTL của token được cấp thực tế để hiểu giới hạn cuối cùng.

Đừng dùng `LIST /sys/auth` chỉ vì tên công việc là “liệt kê”. API chính thức của inventory sử dụng **HTTP GET**, tương ứng capability `read`. `VaultOperations.list(...)` chuyên phục vụ những endpoint hỗ trợ HTTP LIST nên không phải lựa chọn phù hợp ở đây.

### 3.2. Bật mount: `POST /sys/auth/<path>`

Ví dụ bật thêm một mount AppRole:

~~~bash
# Thực hiện ở môi trường kiểm thử hoặc qua workflow quản trị đã duyệt.
vault auth enable \
  -path=approle-ci \
  -description="AppRole cho CI workloads" \
  approle

vault auth list -detailed
~~~

Lệnh này làm cho AppRole được truy cập dưới `auth/approle-ci/...`. Nếu mount path đã tồn tại, Vault trả lỗi; không tự xóa mount cũ để bật lại. Tên path cần được quản lý như một cấu hình ổn định vì client có thể đang dùng nó để login.

HTTP body tương ứng có thể là:

~~~http
POST /v1/sys/auth/approle-ci
Content-Type: application/json

{
  "type": "approle",
  "description": "AppRole cho CI workloads",
  "config": {
    "default_lease_ttl": "30m",
    "max_lease_ttl": "2h",
    "listing_visibility": "hidden"
  }
}
~~~

`type` xác định plugin auth thực tế; `path` nằm trong URL. `config` là cấu hình **toàn mount**, chưa bao gồm các trường riêng của AppRole role như `role_id`, `secret_id`, `token_policies`. Nếu muốn sửa TTL sau khi mount đã tồn tại, dùng endpoint `/tune`.

### 3.3. Đọc và cập nhật tune của mount

~~~bash
# Đọc tham số tune hiện hành.
vault read sys/auth/approle-ci/tune

# Cập nhật qua CLI, với giá trị duration dễ đọc.
vault auth tune \
  -default-lease-ttl=30m \
  -max-lease-ttl=2h \
  -description="AppRole cho CI workloads" \
  approle-ci/

# Đọc lại để xác minh trạng thái.
vault read sys/auth/approle-ci/tune
~~~

Ví dụ HTTP tương đương khi muốn đặt TTL theo **số giây**:

~~~http
POST /v1/sys/auth/approle-ci/tune
Content-Type: application/json

{
  "default_lease_ttl": 1800,
  "max_lease_ttl": 7200,
  "description": "AppRole cho CI workloads"
}
~~~

Những tham số tune thường gặp:

| Tham số | Ý nghĩa | Rủi ro nếu cấu hình sai |
| --- | --- | --- |
| `default_lease_ttl` | TTL mặc định cho token do mount cấp | Quá dài tăng thời gian sử dụng token bị lộ; quá ngắn gây lỗi gia hạn |
| `max_lease_ttl` | Giới hạn TTL của mount | Workload chạy lâu có thể bị ngắt khi token hết khả năng renew |
| `token_type` | Mặc định/ép kiểu service hoặc batch token | Batch token có thuộc tính vòng đời khác service token; không chọn tùy tiện |
| `description` | Mô tả mount | Sai nhãn khiến vận hành nhầm mount |
| `listing_visibility` | Hiển thị mount trong endpoint dành cho UI, ví dụ `hidden`/`unauth` | Nhầm UI visibility với kiểm soát truy cập thật |
| `audit_non_hmac_request_keys` và `audit_non_hmac_response_keys` | Khóa được phép xuất hiện không HMAC trong audit log | Có thể làm lộ thông tin nhạy cảm nếu chọn sai |
| `passthrough_request_headers`, `allowed_response_headers` | Header được chuyển đến/từ plugin | Rủi ro lộ header hoặc mở rộng bề mặt plugin nếu cấu hình quá rộng |

Không nên thay nhiều tham số không liên quan trong cùng một lần tune. `max_lease_ttl` cần phù hợp với `default_lease_ttl` và policy của từng role. Tuning TTL không phải thao tác “gia hạn ngay” token đang có: ứng dụng vẫn phải theo dõi `lease_duration`, thời gian hết hạn và khả năng renew của token thực tế.

**Lưu ý phiên bản Vault:** từ **Vault 2.2.0 trở lên**, cả `GET` và `POST` tới `sys/mounts/auth/<path>/tune` cũng yêu cầu `sudo`. Các phiên bản trước có thể khác; `sys/auth/<path>/tune` vốn đã yêu cầu `sudo`. Chính sách cho `sys/auth/...` không tự cấp quyền `sys/mounts/auth/...`. Khi nâng cấp Vault/Terraform provider, phải đối chiếu endpoint thực được client sử dụng và ACL chính xác.

### 3.4. Tắt mount: thao tác có ảnh hưởng lớn

~~~bash
# CHỈ để minh họa cú pháp; KHÔNG chạy trên mount đang phục vụ production.
# vault auth disable approle-ci/
~~~

`DELETE /v1/sys/auth/approle-ci` hoặc `vault auth disable approle-ci/` **gỡ toàn bộ auth method tại mount đó**. Token đã được cấp từ auth method này sẽ bị vô hiệu theo cơ chế Vault, khiến các workload cần đăng nhập/gia hạn có thể mất truy cập. Việc bật lại cùng tên không tự khôi phục role, cấu hình, accessor hay identity alias đã mất.

Trước bất kỳ thao tác disable/migrate nào, cần inventory các role và client, lên kế hoạch thay login path, kiểm thử, giám sát luồng đăng nhập và bảo đảm có phương thức operator dự phòng. Không dùng xóa mount làm cách xử lý lỗi “already enabled”.

## 4. Phân quyền System API theo nguyên tắc tối thiểu

Giả sử công cụ đọc inventory và công cụ provision được tách riêng:

~~~hcl
# Policy cho công cụ kiểm kê auth mounts.
path "sys/auth" {
  capabilities = ["read"]
}
~~~

Ví dụ policy **operator provision** riêng, chỉ cho mount `approle-ci`:

~~~hcl
# Các thao tác bật và đọc thông tin mount đúng một path.
path "sys/auth/approle-ci" {
  capabilities = ["create", "update", "read", "sudo"]
}

# Đọc/tune cùng mount; không có quyền delete.
path "sys/auth/approle-ci/tune" {
  capabilities = ["read", "update", "sudo"]
}
~~~

Như vậy công cụ provision **không được mặc định cấp quyền disable**. Khi có nhu cầu dùng đường dẫn thay thế trong Vault 2.2.0+:

~~~hcl
# Chỉ khi client thật sự đọc/tune qua sys/mounts/auth.
path "sys/mounts/auth/approle-ci/tune" {
  capabilities = ["read", "update", "sudo"]
}
~~~

Các đường dẫn này không cho phép cấu hình role bên trong AppRole. Quyền như `auth/approle-ci/role/orders-service` phải được cấp bằng policy khác, chỉ cho chủ thể chịu trách nhiệm quản lý role. Token mà ứng dụng orders dùng để đọc `secret/data/orders/...` không cần bất kỳ quyền `sys/auth` nào.

**Giao quyền `sudo` trong Vault rất nhạy cảm:** chỉ cấp cho chủ thể quản trị đã kiểm soát, với scope nhỏ nhất. Một operator có quyền tạo auth method và định nghĩa role/token policies có thể trở thành đường leo thang quyền nếu thiếu kiểm soát; tách nhiệm vụ, xét duyệt IaC, audit và xác minh token sau khi provision.

`listing_visibility=hidden` chỉ tác động đến **cách hiển thị mount ở endpoint UI**; nó không thay cho Vault ACL, không ngăn một client đã biết path thử login. Quyền thực sự đến từ auth backend, role, token policy, identity và các lớp bảo mật khác.

## 5. Làm việc với System API bằng Spring Vault

Spring Vault cung cấp `VaultOperations.opsForSys()` trả về `VaultSysOperations`, có sẵn các thao tác:

- `getAuthMounts()`: liệt kê `Map<String, VaultMount>`.
- `authMount(path, VaultMount)`: bật mount tại path đã chọn.
- `authUnmount(path)`: gỡ mount (chỉ dành cho workflow có kiểm soát).

Riêng **tune mount**, có thể dùng `VaultOperations.write("sys/auth/<path>/tune", body)` để gọi API. `VaultTemplate` xử lý tiền tố `/v1/` dựa trên Vault endpoint; code Java không cần tự ghép `/v1/`.

### 5.1. Chỉ đọc inventory bằng Java

Ví dụ service Java 17+ đã được inject `VaultOperations` (bean Spring Vault được cấu hình TLS và workload authentication phù hợp):

~~~java
import java.util.Map;
import java.util.TreeMap;

import org.springframework.stereotype.Service;
import org.springframework.vault.core.VaultOperations;
import org.springframework.vault.support.VaultMount;

@Service
public class VaultAuthMountInventory {

    private final VaultOperations vault;

    public VaultAuthMountInventory(VaultOperations vault) {
        this.vault = vault;
    }

    public Map<String, String> getAuthTypesByPath() {
        Map<String, VaultMount> mounts = vault.opsForSys().getAuthMounts();
        Map<String, String> types = new TreeMap<>();

        mounts.forEach((path, mount) ->
                types.put(path, mount.getType()));

        return types;
    }
}
~~~

Ví dụ dữ liệu được trả về:

~~~text
{
  "approle-ci/" = "approle",
  "k8s-prod/"   = "kubernetes",
  "token/"      = "token"
}
~~~

Đây là phương pháp **read-only**, thích hợp cho công cụ inventory có token `read` trên `sys/auth`. Map key chứa dấu `/` cuối. Không lấy `getMounts()` để liệt kê auth methods: phương thức đó liệt kê **secrets engine mounts**.

### 5.2. Provision và tune với một danh tính operator riêng

Đoạn mã tiếp theo minh họa một lệnh quản trị chạy có chủ đích. Nó kiểm tra mount có tồn tại và đúng type trước khi tạo; nếu trùng path nhưng khác type thì báo lỗi thay vì ghi đè. **Không gọi từ `@PostConstruct` hay mỗi lần Spring Boot khởi động.**

~~~java
import java.util.Map;

import org.springframework.vault.core.VaultOperations;
import org.springframework.vault.support.VaultMount;

public final class AppRoleMountProvisioner {

    private static final String MOUNT_PATH = "approle-ci";
    private final VaultOperations adminVault;

    // adminVault PHẢI sử dụng token/identity của operator, không phải app.
    public AppRoleMountProvisioner(VaultOperations adminVault) {
        this.adminVault = adminVault;
    }

    public void ensureMounted() {
        Map<String, VaultMount> mounts =
                adminVault.opsForSys().getAuthMounts();
        VaultMount existing = mounts.get(MOUNT_PATH + "/");

        if (existing == null) {
            adminVault.opsForSys()
                    .authMount(MOUNT_PATH, VaultMount.create("approle"));
        } else if (!"approle".equals(existing.getType())) {
            throw new IllegalStateException(
                    "Mount path đã có backend loại " + existing.getType());
        }

        VaultMount readback = adminVault.opsForSys()
                .getAuthMounts().get(MOUNT_PATH + "/");

        if (readback == null || !"approle".equals(readback.getType())) {
            throw new IllegalStateException("Auth mount readback thất bại");
        }
    }

    public void tuneTtl() {
        // HTTP POST /v1/sys/auth/approle-ci/tune.
        // Theo API sys/auth: TTL được truyền bằng số giây.
        adminVault.write(
                "sys/auth/" + MOUNT_PATH + "/tune",
                Map.of(
                        "default_lease_ttl", 1800,
                        "max_lease_ttl", 7200,
                        "description", "AppRole cho CI workloads"));
    }
}
~~~

Chạy hai bước dưới danh tính operator, sau đó **đọc lại** cấu hình:

~~~bash
vault auth list -detailed
vault read sys/auth/approle-ci/tune
~~~

Khi `write(...)` gọi endpoint tune chỉ trả thành công không kèm body, phản hồi Java có thể `null`; **đừng coi `null` là thất bại** nếu lời gọi không ném lỗi. Thành công cần dựa vào HTTP status/API exception và readback TTL/description thực tế. Với nhiều operator song song, đoạn `getAuthMounts()` → `authMount()` vẫn có thể gặp *race*: nếu một tiến trình khác vừa tạo mount thì Vault có thể từ chối; cần quản lý quyền sở hữu rollout và re-read sau lỗi thay vì retry tạo mù.

Ví dụ chưa bao gồm cơ chế phê duyệt, rollback, quản lý namespace hoặc policy của chính AppRole. Các phần này thuộc pipeline provision riêng. Nếu đang dùng Vault Enterprise namespaces hoặc HCP Vault, phải xác minh request chạy ở đúng namespace; có thể cần header `X-Vault-Namespace` do client được cấu hình. Kết quả inventory chỉ có nghĩa trong phạm vi namespace được truy vấn.

## 6. Cấu hình bên trong auth method: bước tiếp sau mount

Sau khi mount `approle-ci/` tồn tại, mới cấu hình **AppRole role** và policy mà token của workload sẽ nhận. Đây là API khác với `sys/auth`:

~~~bash
# Đã có policy "orders-read" được tạo riêng và cấp quyền đọc cần thiết.
vault write auth/approle-ci/role/orders-service \
  token_policies="orders-read" \
  token_ttl="30m" \
  token_max_ttl="2h" \
  secret_id_ttl="10m" \
  secret_id_num_uses=1

# Chỉ đọc cấu hình role bằng danh tính vận hành phù hợp.
vault read auth/approle-ci/role/orders-service
~~~

Workload khi đăng nhập AppRole sẽ gọi `POST /v1/auth/approle-ci/login` bằng `role_id` và `secret_id` được phân phối an toàn. Không đặt hai giá trị này trong ví dụ cấu hình commit vào Git hoặc log response token. Trong Spring Vault, cần khai báo đúng **AppRole path** của mount (ở đây `approle-ci`) khi cấu hình `ClientAuthentication`; nếu code vẫn trỏ tới `auth/approle/login` mặc định thì dù mount đã bật thành công, login vẫn thất bại.

### Ràng buộc TTL nhiều tầng

Một token được cấp phụ thuộc đồng thời vào:

1. Giới hạn toàn Vault/namespace.
2. `default_lease_ttl` và `max_lease_ttl` của auth mount.
3. Tham số cụ thể của role như `token_ttl`, `token_max_ttl`, `token_period`, số lần sử dụng hoặc kiểu token (nếu được hỗ trợ).
4. Cơ chế renew, số lần sử dụng và tình trạng token thực.

Vì vậy một role cấu hình `token_ttl=1h` không bảo đảm token sẽ có TTL 1 giờ nếu mount có giới hạn thấp hơn. Ngược lại, tune mount thành 2 giờ cũng không tự kéo dài token đã phát hành. Spring Vault session manager cần theo dõi và gia hạn/đăng nhập lại theo khả năng thực tế; test phải kiểm tra `auth.lease_duration`, `auth.renewable` và token behavior.

### Ví dụ luồng end-to-end

~~~mermaid
sequenceDiagram
    participant O as Vault operator
    participant V as Vault
    participant A as Spring application
    O->>V: GET /sys/auth
    V-->>O: token/, approle-ci/, ...
    O->>V: POST /sys/auth/approle-ci (nếu chưa tồn tại)
    O->>V: POST /sys/auth/approle-ci/tune
    O->>V: Configure auth/approle-ci/role/orders-service
    O->>V: GET /sys/auth và /tune để xác minh
    A->>V: POST /auth/approle-ci/login
    V-->>A: Vault token + policies + TTL
    A->>V: GET /secret/data/orders/config
    V-->>A: Secret (nếu token được policy cho phép)
~~~

Các bước operator và workload dùng **hai danh tính, hai nhóm quyền khác nhau**. Service ứng dụng không cần liệt kê/tune mount chỉ để có thể đăng nhập qua mount đó.

## 7. Xử lý lỗi và giám sát

| Hiện tượng | Nguyên nhân có thể | Cách khắc phục |
| --- | --- | --- |
| `GET sys/auth` trả 403 | Token inventory thiếu capability `read` | Kiểm tra đúng policy/namespace, không nâng quyền cho token ứng dụng |
| `POST sys/auth/...` trả 403 | Thiếu `create/update` hoặc `sudo` | Dùng operator identity được cấp đúng path; kiểm tra capability thực |
| `GET/POST .../tune` trả 403 | Thiếu `sudo`, hoặc client gọi `sys/mounts/auth/.../tune` mà policy chỉ cấp `sys/auth/.../tune` | Đối chiếu URL thực, phiên bản Vault và ACL tương ứng |
| Enable báo path đã có | Mount trùng tên | Đọc inventory, kiểm tra `type` và ownership, không disable để retry |
| `GET .../tune` báo 404 | Path sai, mount chưa tồn tại hoặc nhầm namespace | Kiểm tra `sys/auth`, dấu gạch chéo và loại mount |
| `vault auth list` đã có AppRole nhưng login báo 404 | Ứng dụng gọi nhầm `auth/approle/login` thay vì `auth/approle-ci/login` | Đồng bộ cấu hình AppRole path trong Spring Vault |
| Token được cấp ngắn hơn mong đợi | Mount max TTL, role TTL hoặc global max TTL giới hạn | Đối chiếu các lớp cấu hình và thời gian sống token thực |
| Đổi mount xong workload bị 403 khi đọc KV | Policy gắn cho role/token không đúng | Kiểm tra role, identity mapping, token policies; không cấp `sys/auth` bừa bãi |
| Auth method bị disable | Quá trình vận hành đã gỡ mount, token thuộc mount mất hiệu lực | Dừng rollout, khôi phục theo quy trình dự phòng và cấu hình lại đúng có kiểm soát |
| Lỗi 429, timeout, 5xx | Quá tải, Vault không sẵn sàng, leader change hoặc mạng | Retry có giới hạn và jitter cho thao tác đọc; thận trọng với thao tác thay đổi trạng thái |

Lỗi `403` có thể đến từ policy, namespace hoặc yêu cầu `sudo`; không thể kết luận chỉ bằng HTTP status. Dùng audit/request ID để tìm nguyên nhân, đồng thời tránh in token, SecretID, RoleID hoặc dữ liệu xác thực nhạy cảm ra log.

Những số liệu vận hành đáng theo dõi:

- **Số lượng và danh sách auth mount** theo namespace, `type`, `path` và trạng thái chênh lệch so với cấu hình mong muốn.
- **Tỷ lệ login thành công/thất bại** theo mount và role; sự gia tăng 403/429, độ trễ auth và số token sắp hết hạn.
- **Sự kiện cấu hình control plane**: enable, tune, disable, đổi `description`/`token_type` hoặc điều chỉnh TTL; ghi danh tính operator và request ID.
- **Chất lượng cấu hình**: mount nào tồn tại mà không có role hợp lệ, TTL vượt chính sách nội bộ, role tạo token rộng quyền hoặc mount ít được sử dụng.

Nếu hệ thống dùng Micrometer, có thể tự xây metric `vault_auth_mount_inventory_count` hoặc `vault_auth_login_failure_total`. Đây là **metric minh họa cho ứng dụng/giám sát**, không phải tên metric mặc định của Spring Vault. Các thông tin trong audit log cần tuân thủ cấu hình HMAC và chính sách bảo vệ dữ liệu nhạy cảm.

## 8. Kiểm thử tích hợp theo hợp đồng API

Trong một Vault test instance hoặc môi trường lab tách biệt, hãy thực hiện các kiểm thử sau:

| Tình huống | Thao tác | Điều kiện đạt |
| --- | --- | --- |
| Liệt kê mount | Gọi `GET /sys/auth` bằng token chỉ có quyền inventory | Có map `data`; mỗi key gồm `path/` và `type` hợp lệ |
| Thiếu quyền xem | Dùng token ứng dụng không có `sys/auth` | Nhận 403, nhưng vẫn có thể login qua auth method được cấp |
| Bật AppRole | Enable mount `approle-ci` mới với operator token | `sys/auth` trả mount cùng `type=approle`, có `accessor` |
| Enable trùng | Gọi enable lần hai cùng path | API từ chối; không làm mất backend/role đã có |
| Sai loại mount | Path tồn tại với `type=kubernetes` nhưng provision code yêu cầu `approle` | Code dừng và báo sai type |
| Tune TTL | Đặt `1800/7200` giây rồi đọc lại `/tune` | Giá trị đọc về tương ứng 30 phút/2 giờ |
| Thiếu `sudo` | Token có `update` nhưng không có `sudo` gọi tune | Bị 403 |
| Khác endpoint tune | Kiểm thử `sys/auth/.../tune` và `sys/mounts/auth/.../tune` trên Vault 2.2+ | Mỗi endpoint tuân theo quyền riêng; cả hai yêu cầu `sudo` |
| Auth method đã bật nhưng chưa có role | Gọi login bằng một AppRole chưa provision | Bị từ chối; không cấp token trái phép |
| Token lifecycle | Tạo AppRole role, login và đọc token TTL | TTL và policies tuân theo global/mount/role; renew thực tế đúng kỳ vọng |
| Kiểm tra namespace | Liệt kê cùng path trên namespace khác | Không nhầm hai inventory/role giữa các namespace |

Đối với trường hợp disable, nên thử **chỉ trên mount dùng riêng cho lab** và không dùng credential của hệ thống đang phục vụ. Sau kiểm thử, quan sát ảnh hưởng tới login/token rồi khởi tạo lại lab theo quy trình; không đưa xóa mount vào bài test chạy tự động trên môi trường dùng chung.

Kiểm thử trong Java có thể sử dụng instance Vault test được provision sẵn và assert kết quả `VaultSysOperations.getAuthMounts()`, không cần mô phỏng chính method đang test bằng mock. Các phép thử create/tune đòi hỏi operator token riêng; test read-only dùng token ít quyền hơn để xác minh ranh giới.

## 9. Những lỗi thiết kế thường gặp

1. **Nhầm `type` với `path`:** bật `approle` tại `approle-ci/` nhưng client vẫn login ở `auth/approle/login`.
2. **Dùng `sys/mounts` cho auth:** API đó quản lý secrets engines; auth phải dùng `sys/auth` hoặc `VaultSysOperations.getAuthMounts()`.
3. **Gán `sudo` cho ứng dụng:** quyền vận hành mount không phục vụ yêu cầu đọc secrets/Transit/PKI thông thường.
4. **Xem `listing_visibility=hidden` là tính năng chặn login:** đây chỉ là hiển thị; quyền login vẫn do backend và policy kiểm soát.
5. **Đọc `default_lease_ttl=0` là token vô hạn:** phải hiểu cơ chế kế thừa và đối chiếu token thật.
6. **Tự động disable và enable lại khi nhận “already mounted”:** có thể thu hồi token, mất role/cấu hình và làm gián đoạn hệ thống.
7. **Đọc `vault.write(.../tune) == null` thành thất bại:** nhiều system endpoint trả response rỗng khi thành công; cần readback.
8. **Bỏ qua phiên bản Vault và endpoint thực:** quyền `sudo` của `sys/mounts/auth/<path>/tune` thay đổi ở Vault 2.2+; policy phải khớp đường dẫn client sử dụng.

### Câu hỏi tự kiểm tra

1. `GET /v1/sys/auth` khác `GET /v1/sys/mounts` ở đối tượng được liệt kê như thế nào?
2. Khi kết quả list có khóa `approle-ci/` và `type=approle`, URL login AppRole của client nằm ở đâu?
3. Vì sao policy có `update` trên `sys/auth/approle-ci/tune` vẫn có thể nhận 403?
4. Cấu hình `default_lease_ttl=30m` ở mount có tự động gia hạn token đang còn hiệu lực thành 30 phút không?
5. Tại sao cần tách token operator quản lý auth mount khỏi token Spring application đọc KV?
6. Khi `VaultSysOperations.getAuthMounts()` báo mount đã tồn tại với `type=kubernetes` nhưng automation muốn bật `approle` cùng path, bạn nên làm gì?
7. Những bước readback nào giúp xác minh mount đã bật đúng và ứng dụng thực sự có thể đăng nhập?

## 10. Ghi nhớ

**Auth mount là một instance phương thức xác thực nằm dưới `auth/<mount>/`.** `sys/auth` cho phép operator liệt kê, bật và tune mount; cấu hình role/identity nằm ở API riêng của từng auth method. Trong Spring Vault, `opsForSys().getAuthMounts()` và `authMount(...)` cung cấp thao tác hệ thống ở mức cao, còn `VaultOperations.write("sys/auth/.../tune", ...)` dùng được cho yêu cầu tune.

Mọi thay đổi phải được kiểm soát bằng **đúng path, đúng quyền ACL và `sudo`**, readback cấu hình sau khi ghi, rồi kiểm tra **token TTL, policy và login thật**. Những ứng dụng chỉ cần đọc secret hay dùng Transit/PKI nên xác thực qua auth mount đã được provision mà không mang quyền quản trị mount vào runtime.

### Tài liệu tham khảo

- [HashiCorp Vault — System API `/sys/auth`](https://developer.hashicorp.com/vault/api-docs/system/auth)
- [HashiCorp Vault — Authentication methods](https://developer.hashicorp.com/vault/docs/auth)
- [HashiCorp Vault — `vault auth enable`](https://developer.hashicorp.com/vault/docs/commands/auth/enable)
- [HashiCorp Vault — `vault auth tune`](https://developer.hashicorp.com/vault/docs/commands/auth/tune)
- [HashiCorp Vault — ACL policy và capability `sudo`](https://developer.hashicorp.com/vault/docs/concepts/policies)
- [HashiCorp Vault — Important changes, `sys/mounts/auth/.../tune` ở Vault 2.2.0+](https://developer.hashicorp.com/vault/docs/updates/important-changes)
- [Spring Vault — `VaultSysOperations`](https://docs.spring.io/spring-vault/reference/api/java/org/springframework/vault/core/VaultSysOperations.html)
- [Spring Vault — `VaultMount`](https://docs.spring.io/spring-vault/reference/api/java/org/springframework/vault/support/VaultMount.html)
- [Spring Vault — `VaultOperations`](https://docs.spring.io/spring-vault/reference/api/java/org/springframework/vault/core/VaultOperations.html)
