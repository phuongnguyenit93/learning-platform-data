# Tổ chức một môi trường Vault cục bộ dành cho học tập

## 1. Mục tiêu và phạm vi

Spring Vault là thư viện giúp ứng dụng Java làm việc với HashiCorp Vault thông qua các API như **VaultTemplate**: đọc và ghi secret, xác thực, sử dụng các secrets engine, đồng thời quản lý phiên làm việc với Vault. Để học có hệ thống, cần một môi trường có thể tạo lại nhanh, quan sát được quyền truy cập và cố ý gây lỗi mà không ảnh hưởng hạ tầng thật.

Sau bài này, bạn có thể:

- Chạy một Vault cục bộ bằng Docker Compose và hiểu giới hạn của **dev mode**.
- Tổ chức thư mục, địa chỉ truy cập, chính sách và dữ liệu thử nghiệm theo cách dễ tái tạo.
- Tạo KV secrets engine phiên bản 2, ghi secret giả lập và cấp quyền đọc tối thiểu cho ứng dụng.
- Tập xác thực bằng token ngắn hạn và **AppRole** như một mô phỏng đơn giản của xác thực theo workload.
- Kết nối một ứng dụng Java với Vault bằng **VaultTemplate**, xác minh đường dẫn KV v2 và phân biệt các lỗi thường gặp.
- Chuẩn bị phần mở rộng để luyện **Transit encryption**, **PKI**, vòng đời token/lease, giám sát và kiểm thử tích hợp.

**Phạm vi an toàn:** Đây là phòng thí nghiệm chạy trên máy cá nhân, chỉ dùng dữ liệu giả và token dùng thử. Ví dụ cố ý sử dụng HTTP, root token cố định và Vault dev mode để dễ học; không sử dụng cấu hình này cho production, máy dùng chung hoặc Vault có dữ liệu thật.

## 2. Sơ đồ và quy ước môi trường

~~~mermaid
flowchart LR
    Java["Ứng dụng Java<br/>Spring Vault / VaultTemplate"] -->|"HTTP localhost:8200<br/>token hoặc AppRole"| V["Vault dev<br/>Docker container"]
    CLI["Vault CLI / trình duyệt"] --> V
    V --> Auth["auth/token<br/>auth/approle"]
    V --> KV["lab-kv/<br/>KV v2"]
    V --> Transit["lab-transit/<br/>Transit"]
    V --> PKI["lab-pki/<br/>PKI"]
~~~

Quy ước dùng xuyên suốt bài:

| Thành phần | Giá trị trong phòng lab | Mục đích |
| --- | --- | --- |
| Địa chỉ từ máy host | http://127.0.0.1:8200 | Chỉ mở Vault trên loopback của máy học |
| Container/service | vault | Chạy Vault và sử dụng CLI ngay trong container |
| Root token dev | dev-root-only | Chỉ dành cho người quản trị lab |
| KV v2 mount | lab-kv/ | Secret tĩnh cho bài thực hành Java |
| Transit mount | lab-transit/ | Mã hóa/giải mã mà ứng dụng không giữ khóa |
| PKI mount | lab-pki/ | Cấp chứng chỉ thử nghiệm |
| AppRole | spring-lab | Mô phỏng danh tính workload của ứng dụng |
| Policy | spring-lab | Cấp quyền đọc đúng secret cần thiết |

Luồng quyền nên có hai vai trò riêng: **người quản trị lab** dùng root token để cấu hình auth, mount và policy; **ứng dụng Java** dùng token gắn policy hạn chế hoặc AppRole. Nếu dùng root token trong code, bài kiểm thử về phân quyền sẽ mất ý nghĩa.

Một cách sắp xếp thư mục lab độc lập với mã nguồn ứng dụng:

~~~text
vault-lab/
├── compose.yaml
├── policies/
│   └── spring-lab.hcl
└── notes/                 # Ghi lệnh và kỳ vọng, KHÔNG lưu secret/token thật
~~~

Các tệp trên là gợi ý để người học tự tạo khi thực hành. Không cần đưa token, role secret ID, private key hay giá trị secret vào Git.

## 3. Khởi động Vault dev bằng Docker Compose

### 3.1. Điều kiện tiên quyết

Cần Docker Engine/Docker Desktop và Docker Compose v2 (lệnh **docker compose**), một cổng 8200 còn trống, Java và công cụ build phù hợp dự án Spring. Có thể dùng Vault CLI cài trên host, nhưng bài này ưu tiên gọi CLI **bên trong container** để không phụ thuộc cách cài đặt trên Windows, macOS hoặc Linux.

Trong thư mục **vault-lab**, tạo tệp **compose.yaml**:

~~~yaml
services:
  vault:
    image: hashicorp/vault:1.19.0
    cap_add:
      - IPC_LOCK
    command: server -dev -dev-listen-address=0.0.0.0:8200
    environment:
      VAULT_DEV_ROOT_TOKEN_ID: dev-root-only
      VAULT_ADDR: http://127.0.0.1:8200
      VAULT_TOKEN: dev-root-only
    ports:
      - "127.0.0.1:8200:8200"
    restart: "no"
~~~

Phiên bản image được ghi cụ thể để các lần làm bài dùng cùng một nền tảng. Khi đổi phiên bản Vault, hãy kiểm tra lại thay đổi CLI/API và ghi phiên bản mới trong tài liệu lab. **VAULT_TOKEN** đặt trong container chỉ giúp chạy lệnh quản trị ở ví dụ; ứng dụng Java trên host phải dùng thông tin xác thực riêng.

Khởi chạy và xác nhận trạng thái:

~~~bash
docker compose up -d
docker compose ps
docker compose exec -T vault vault status
curl -i http://127.0.0.1:8200/v1/sys/health
~~~

Kết quả mong đợi: Vault đã **Initialized = true**, **Sealed = false**; endpoint health của active node trả **HTTP 200**. Truy cập **http://127.0.0.1:8200/ui** nếu muốn quan sát giao diện quản trị Vault (đăng nhập bằng dev root token của lab).

Nếu không có **curl** trên host, có thể chỉ dùng **vault status** trong container. Xem lỗi khởi động bằng lệnh sau:

~~~bash
docker compose logs --tail=100 vault
~~~

**Dev mode có tính chất tạm thời:** Vault tự khởi tạo, tự unseal, dùng storage trong bộ nhớ và có root token được chỉ định. Việc khởi động lại tiến trình/container có thể làm mất các mount, policy, token và secret đã tạo. Đây là đặc điểm phù hợp để đặt lại bài thực hành, nhưng không thích hợp để học sao lưu/khôi phục dữ liệu bền vững hoặc quy trình init/unseal thực tế.

## 4. Khởi tạo KV v2 và dữ liệu thử nghiệm

Trong Vault, **mount path** là tên nơi một secrets engine được gắn; **đường dẫn secret** là phần bên trong engine đó. Tạo mount riêng cho lab để tránh nhầm với mount **secret/** có thể có sẵn trong dev mode.

~~~bash
docker compose exec -T vault vault secrets enable -path=lab-kv kv-v2
docker compose exec -T vault vault secrets list -detailed
docker compose exec -T vault vault kv put -mount=lab-kv app/config username=student password=demo-only
docker compose exec -T vault vault kv get -mount=lab-kv app/config
docker compose exec -T vault vault kv metadata get -mount=lab-kv app/config
~~~

Với KV v2, lệnh CLI **vault kv get -mount=lab-kv app/config** tương ứng với API đọc **GET /v1/lab-kv/data/app/config**. Phân biệt hai đường dẫn này rất quan trọng khi viết Vault policy: policy đối với dữ liệu KV v2 phải bao gồm phân đoạn **data/**, trong khi thao tác liệt kê metadata sử dụng **metadata/**.

Hãy thử cập nhật secret để nhìn thấy phiên bản:

~~~bash
docker compose exec -T vault vault kv put -mount=lab-kv app/config username=student password=demo-changed
docker compose exec -T vault vault kv get -mount=lab-kv -version=1 app/config
docker compose exec -T vault vault kv get -mount=lab-kv -version=2 app/config
~~~

**Kiểm chứng:** Hai phiên bản có giá trị **password** khác nhau; mỗi lần **kv put** ở KV v2 tạo một phiên bản. Secret này là cấu hình tĩnh, **không có lease động** tự cấp khi đọc. TTL/lease thường thấy ở token, secret động và một số API phát hành chứng chỉ, không nên đánh đồng với version của KV v2.

### 4.1. Policy tối thiểu cho ứng dụng

Tạo tệp **policies/spring-lab.hcl**:

~~~hcl
path "lab-kv/data/app/config" {
  capabilities = ["read"]
}
~~~

Nạp policy từ thư mục **vault-lab**:

~~~bash
docker compose cp policies/spring-lab.hcl vault:/tmp/spring-lab.hcl
docker compose exec -T vault vault policy write spring-lab /tmp/spring-lab.hcl
docker compose exec -T vault vault policy read spring-lab
~~~

Policy trên **không** cho ứng dụng cập nhật, xóa hoặc liệt kê toàn bộ secret. Nếu bài tập yêu cầu liệt kê các tên bên dưới **app/**, phải xem xét cấp thêm **list** cho **lab-kv/metadata/app/**; quyền **list** khác quyền **read**, và không nên cấp khi chỉ cần đọc một cấu hình cụ thể.

### 4.2. Thử token ngắn hạn trước khi dùng AppRole

Tạo một token có policy **spring-lab**, hết hạn dự kiến sau 30 phút:

~~~bash
docker compose exec -T vault vault token create -policy=spring-lab -ttl=30m -field=token
~~~

Lệnh in ra token mới. Chỉ dùng token này trong shell của ứng dụng hoặc trong trình chạy thử; không chép vào tệp nguồn, ảnh chụp màn hình hay nhật ký. Trên **PowerShell**:

~~~powershell
$env:VAULT_ADDR = "http://127.0.0.1:8200"
$env:VAULT_TOKEN = "<token-ung-dung-vua-tao>"
~~~

Trên **bash/zsh**:

~~~bash
export VAULT_ADDR="http://127.0.0.1:8200"
export VAULT_TOKEN="<token-ung-dung-vua-tao>"
~~~

Nếu Vault CLI đã cài trên host, với token ứng dụng trong biến môi trường, có thể thử:

~~~bash
vault kv get -mount=lab-kv app/config
vault kv put -mount=lab-kv app/config username=forbidden
~~~

Lệnh đọc phải thành công, còn lệnh ghi phải bị từ chối (**403 permission denied**). Nếu lệnh ghi vẫn thành công, thường bạn đang dùng nhầm root token hoặc đã gán policy quá rộng.

## 5. Mô phỏng xác thực theo workload với AppRole

Trong hệ thống triển khai thật, danh tính của workload có thể được xác thực qua Kubernetes, IAM hoặc một cơ chế phù hợp hạ tầng. Ở máy cá nhân, **AppRole** giúp học ý tưởng: ứng dụng cung cấp **role_id** và **secret_id** để nhận **client token** ngắn hạn; các quyền truy cập thực tế vẫn do policy trên token quyết định.

Tạo auth method và role bằng CLI quản trị trong container:

~~~bash
docker compose exec -T vault vault auth enable approle
docker compose exec -T vault vault write auth/approle/role/spring-lab token_policies=spring-lab token_ttl=15m token_max_ttl=1h secret_id_ttl=30m secret_id_num_uses=1
docker compose exec -T vault vault read -field=role_id auth/approle/role/spring-lab/role-id
docker compose exec -T vault vault write -f -field=secret_id auth/approle/role/spring-lab/secret-id
~~~

Hai lệnh cuối xuất **role_id** và **secret_id** để đưa vào môi trường chạy ứng dụng; đừng lưu các giá trị đó cùng mã nguồn. Secret ID ở ví dụ chỉ sử dụng được **một lần** và hết hạn sau tối đa 30 phút. Khi cần đăng nhập lại, tạo secret ID mới; muốn học cơ chế xoay vòng và phân phối bí mật thật, cần bổ sung quy trình cấp phát riêng thay vì cố định secret ID trong cấu hình.

Một luồng cần hiểu:

1. Người quản trị cấp role_id và secret_id qua một kênh phù hợp.
2. Ứng dụng gọi **auth/approle/login** để nhận client token.
3. Vault gắn policy **spring-lab** vào token; ứng dụng đọc **lab-kv/data/app/config**.
4. Khi token hết hạn, bị thu hồi hoặc vượt **max_ttl**, phiên truy cập không còn hợp lệ; phải đăng nhập/nhận token mới theo cấu hình client.

Các giá trị **token_ttl**, **token_max_ttl**, **secret_id_ttl** và **secret_id_num_uses** kiểm soát những vòng đời khác nhau. Token có thể được renew **chỉ khi được cấp dạng renewable, còn trong giới hạn thời gian và đáp ứng policy**; secret ID không phải token và không được gia hạn theo cùng cách.

## 6. Kết nối Java bằng VaultTemplate

Đối với dự án Spring quản lý phiên bản qua BOM, khai báo dependency **org.springframework.vault:spring-vault-core** với phiên bản tương thích; dự án không dùng BOM cần tự chỉ định phiên bản. Ví dụ Gradle khi phiên bản đã được quản lý:

~~~kotlin
dependencies {
    implementation("org.springframework.vault:spring-vault-core")
}
~~~

Đây là một chương trình smoke test độc lập, dùng token hạn chế ở mục 4.2:

~~~java
import java.net.URI;
import java.util.Map;

import org.springframework.vault.authentication.TokenAuthentication;
import org.springframework.vault.client.VaultEndpoint;
import org.springframework.vault.core.VaultTemplate;
import org.springframework.vault.support.Versioned;

public class VaultSmokeTest {
    public static void main(String[] args) {
        String token = System.getenv("VAULT_TOKEN");
        if (token == null || token.isBlank()) {
            throw new IllegalStateException("VAULT_TOKEN chua duoc cau hinh");
        }

        VaultEndpoint endpoint =
                VaultEndpoint.from(URI.create("http://127.0.0.1:8200"));
        VaultTemplate vault = new VaultTemplate(
                endpoint, new TokenAuthentication(token));

        Versioned<Map<String, Object>> result = vault
                .opsForVersionedKeyValue("lab-kv")
                .get("app/config");

        if (result == null || result.getData() == null) {
            throw new IllegalStateException("Khong tim thay app/config");
        }
        // Chi in ten truong, khong in gia tri cua secret.
        System.out.println("Doc KV v2 thanh cong: " + result.getData().keySet());
    }
}
~~~

**Kết quả mong đợi:** Chương trình in tên các trường **username**, **password**, không xuất giá trị của chúng. Nếu nhận **403**, hãy kiểm tra token/policy; nếu **404** hoặc **null**, kiểm tra mount, đường dẫn, version secret và việc có dùng đúng thao tác KV v2 hay không.

Khi chuyển sang AppRole, thay **TokenAuthentication** bằng **AppRoleAuthentication** hoặc cấu hình Spring Vault tương ứng, rồi cung cấp role_id/secret_id từ môi trường chạy. Với ứng dụng hoạt động lâu dài, cần cân nhắc **SessionManager** hỗ trợ làm mới/đăng nhập lại và xử lý token bị thu hồi; ví dụ token trực tiếp ở trên chỉ kiểm tra kết nối, không tự xử lý toàn bộ vòng đời xác thực.

Không nên nhầm **VaultTemplate** (truy cập API khi chạy) với cơ chế nạp property của **Spring Cloud Vault** vào Spring Environment. Chúng có thể bổ trợ nhau nhưng là hai cách tích hợp có vòng đời và điểm cấu hình khác nhau.

## 7. Mở rộng phòng lab cho Transit và PKI

Các bài thực hành sau có thể dùng lại một Vault nhưng tách mount, policy và tên dữ liệu, nhờ đó việc quan sát quyền trở nên rõ ràng.

### 7.1. Transit: mã hóa mà ứng dụng không nắm khóa

~~~bash
docker compose exec -T vault vault secrets enable -path=lab-transit transit
docker compose exec -T vault vault write -f lab-transit/keys/orders
docker compose exec -T vault vault write lab-transit/encrypt/orders plaintext=c2VjcmV0
~~~

Chuỗi **c2VjcmV0** là Base64 của từ thử nghiệm **secret**. Lệnh cuối trả **ciphertext** dạng gần giống **vault:v1:...**; dùng ciphertext đó để gọi **lab-transit/decrypt/orders**, sau đó giải mã kết quả Base64 để đối chiếu plaintext. Việc mã hóa/giải mã dùng API Transit; khóa được quản lý trong Vault, không xuất cho ứng dụng.

Policy của workload phải được mở rộng **có chủ đích** nếu muốn dùng Transit:

~~~hcl
path "lab-transit/encrypt/orders" {
  capabilities = ["update"]
}

path "lab-transit/decrypt/orders" {
  capabilities = ["update"]
}
~~~

Chỉ cấp **encrypt** cho tác vụ cần ghi dữ liệu bảo mật, và chỉ cấp **decrypt** cho tác vụ thật sự cần đọc lại dữ liệu. Không nên cấp cả hai cho mọi workload theo mặc định. Phần HCL này là **ví dụ bổ sung** cho policy tùy bài tập, không tự động có hiệu lực khi chỉ xem tài liệu.

### 7.2. PKI: phát hành chứng chỉ thử nghiệm

~~~bash
docker compose exec -T vault vault secrets enable -path=lab-pki pki
docker compose exec -T vault vault secrets tune -max-lease-ttl=8760h lab-pki
docker compose exec -T vault vault write -field=certificate lab-pki/root/generate/internal common_name=lab.internal ttl=8760h
docker compose exec -T vault vault write lab-pki/roles/lab-server allowed_domains=lab.internal allow_subdomains=true max_ttl=72h
docker compose exec -T vault vault write lab-pki/issue/lab-server common_name=api.lab.internal ttl=1h
~~~

Vault trả chứng chỉ, private key và metadata liên quan cho yêu cầu cấp phát. **Không ghi private key vào log hoặc commit vào repository**. Đây là CA tự ký dành riêng cho lab; client chưa tin cậy CA này nếu chưa cấu hình trust store. Role phát hành cần policy trên đường dẫn **lab-pki/issue/lab-server** với capability **update** và không nên được gán bừa cho role chỉ đọc KV.

Lưu ý khi học vòng đời: **TTL của chứng chỉ không đồng nghĩa với việc có thể renew một chứng chỉ đã cấp bằng vault lease renew**. Thường phải phát hành chứng chỉ mới và triển khai cơ chế thay thế trước khi chứng chỉ cũ hết hạn. Tìm hiểu riêng về revoke/CRL và quản trị CA khi học sâu PKI.

## 8. Quan sát vòng đời, lỗi và kiểm thử

### 8.1. Tập quan sát token và lease

Trong shell đang sử dụng **token ứng dụng**, nếu đã cài Vault CLI trên host:

~~~bash
vault token lookup
vault token renew
~~~

**vault token lookup** giúp quan sát TTL, renewable, policy và thời điểm tạo token. **vault token renew** có thể thất bại nếu token không renewable, quá giới hạn gia hạn hoặc đã hết hạn; đó là một kết quả có ý nghĩa để phân tích. Người quản trị có thể thu hồi token bằng **vault token revoke** với token cần thu hồi. Với những secrets engine phát hành **dynamic secret kèm lease_id**, dùng **vault lease lookup** và **vault lease revoke** để học vòng đời lease; secret tĩnh KV v2 không tạo lease_id như vậy.

Trên Spring Vault, nên ghi nhận **loại thao tác**, **đường dẫn logic**, **mã HTTP**, **thời gian xử lý** và **mã tương quan** trong log/metric; không ghi token, secret ID, plaintext, ciphertext nhạy cảm hay private key. Đối với Vault server, có thể dùng health API, telemetry và audit device trong một bài lab chuyên sâu; audit log cũng cần bảo vệ quyền đọc và thời gian lưu trữ.

### 8.2. Ma trận lỗi cần cố ý tạo ra

| Thử nghiệm | Cách gây lỗi | Hiện tượng kỳ vọng | Hướng điều tra |
| --- | --- | --- | --- |
| Không kết nối được | Dừng container rồi chạy ứng dụng | Connection refused/timeout | Docker, cổng 8200, địa chỉ host |
| Sai token | Cấu hình token không hợp lệ hoặc bị revoke | Thường là HTTP 403 | Auth method, TTL, token hiện hành |
| Thiếu policy | Dùng token chỉ đọc để ghi KV | HTTP 403 permission denied | Capability và chính xác API path có **data/** |
| Nhầm KV v1/v2 | Gọi endpoint không có **data/** | Có thể HTTP 404/405 hoặc không có dữ liệu | Loại mount và client API |
| Secret không tồn tại | Đọc một path chưa tạo | HTTP 404 hoặc kết quả rỗng tùy API/client | Mount, key, version, trạng thái xóa |
| AppRole secret ID đã dùng | Đăng nhập lại bằng secret ID một lần | Đăng nhập bị từ chối | **secret_id_num_uses**, TTL và quy trình xoay vòng |
| Vault bị sealed/chưa init | Chỉ có thể thử trên non-dev mode | Health không trả 200, thao tác thất bại | **vault status**, quy trình init/unseal |

Các mã/lỗi do client ném ra có thể khác nhau theo phiên bản Spring Vault, Vault và tình huống; hãy dựa trên HTTP status cùng thông điệp thực tế, không kiểm tra cứng một tên exception duy nhất cho mọi trường hợp.

### 8.3. Checklist kiểm thử tích hợp

Khi có thể tự động hóa, dùng **Testcontainers VaultContainer** (hoặc một container Vault dev riêng cho test) để tạo môi trường **mới cho từng suite**, rồi chạy bootstrap mount/policy/secret trước khi tạo **VaultTemplate**. Các ca kiểm thử nên xác nhận:

1. Đăng nhập bằng token hoặc AppRole hợp lệ và đọc đúng KV v2, kể cả metadata phiên bản.
2. Token chỉ đọc nhận lỗi **403** khi thử ghi hoặc truy cập path ngoài policy.
3. Secret ở path không tồn tại được xử lý có chủ đích, không gây rò rỉ dữ liệu vào log.
4. Khi token hết hạn/bị revoke, ứng dụng báo lỗi hợp lý hoặc đăng nhập lại theo chiến lược đã cấu hình.
5. Transit mã hóa rồi giải mã đúng chuỗi đầu vào với quyền phù hợp; tài khoản không có quyền decrypt bị từ chối.
6. PKI chỉ cấp được chứng chỉ nằm trong miền được phép và có TTL trong giới hạn role.

Đảm bảo kiểm thử **độc lập**: không dùng token/secret đã tạo thủ công trên máy cá nhân, không phụ thuộc thứ tự chạy và không kết nối tới Vault thật. Tài liệu bài này cung cấp cấu trúc môi trường; phần test code cụ thể tùy Spring Boot/Spring Vault/Testcontainers phiên bản của dự án.

## 9. Phục hồi trạng thái và dọn dẹp

Các lệnh tạo engine, auth method và policy thường **không idempotent**: chạy lại **vault secrets enable** trên mount đã tồn tại sẽ báo đường dẫn đã được sử dụng. Đối với bài học ngắn, cách đơn giản nhất để có trạng thái sạch là dừng và tạo lại Vault dev:

~~~bash
docker compose down
docker compose up -d
docker compose exec -T vault vault status
~~~

Sau khi tạo lại container, phải thực hiện lại các bước khởi tạo KV, policy và AppRole; token/secret ID cũ có thể không còn dùng được. Nên lưu **các câu lệnh bootstrap không chứa bí mật** để chạy lại theo thứ tự, và cấp secret ID mới khi ứng dụng bắt đầu bài tập.

Nếu cần học **init/unseal**, **persistence**, backup hoặc khôi phục, hãy tạo một môi trường non-dev **tách biệt**, dùng storage và cấu hình listener riêng, khởi tạo với **vault operator init**, sau đó thực hành **vault operator unseal**. Khi đó phải bảo vệ unseal key và initial root token. Không được coi dev mode là bài thực hành chính xác của quá trình vận hành Vault production.

## 10. Bài tập tự đánh giá

**Bài 1 — Quyền tối thiểu.** Tạo thêm **app/feature-flags** trong **lab-kv**. Giữ policy chỉ đọc **app/config** và xác minh ứng dụng không đọc được **app/feature-flags**. Sau đó bổ sung đúng đường dẫn cần thiết, nạp lại policy và thử lại bằng token phù hợp.

**Bài 2 — Vòng đời xác thực.** Tạo AppRole với secret ID chỉ dùng một lần. Thử đăng nhập hai lần bằng cùng secret ID, giải thích sự khác nhau giữa hết lượt dùng secret ID và hết hạn client token.

**Bài 3 — Tái lập môi trường.** Xóa container dev, khởi động lại, nạp mount, policy, dữ liệu giả và chạy smoke test Java. Tự kiểm tra rằng người khác có thể làm theo tài liệu để nhận cùng kết quả mà không cần token hay dữ liệu bí mật từ máy bạn.

**Tiêu chí hoàn thành:** Vault cục bộ chỉ lắng nghe trên loopback; KV v2 đọc được bằng VaultTemplate; ứng dụng không dùng root token; một thao tác trái quyền trả 403; giải thích được khi nào token, AppRole secret ID và lease hết hạn; có thể tạo lại phòng lab sạch bằng các bước rõ ràng.
