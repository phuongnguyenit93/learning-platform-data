# Chuẩn bị token hoặc role có quyền phù hợp với ví dụ

## 1. Mục tiêu và tình huống học tập

Khi ứng dụng Java sử dụng **Spring Vault** và **VaultTemplate** để truy cập HashiCorp Vault, việc biết đúng URL và đường dẫn secret chưa đủ. Mỗi request cần một danh tính được Vault chấp nhận và một **policy** cho phép thao tác trên đúng API path. Một ứng dụng có thể đăng nhập thành công nhưng vẫn nhận **403 permission denied** nếu token không có quyền phù hợp.

Bài học thuộc chương **Môi trường thực hành**, tập trung vào cách **chuẩn bị token hoặc auth role** để thực hiện ví dụ có kiểm soát. Các ví dụ dùng KV v2, Transit encryption và PKI, đồng thời tạo nền cho các bài về vòng đời token/lease, xử lý lỗi, giám sát và kiểm thử tích hợp.

Sau bài này, bạn có thể:

1. Phân biệt **token**, **Vault policy**, **auth method**, **AppRole role** và **role của secrets engine**.
2. Viết policy có quyền tối thiểu cho một workload đọc KV v2, một workload mã hóa Transit và một workload phát hành chứng chỉ PKI.
3. Tạo token ngắn hạn để smoke test, xác minh một thao tác được phép và một thao tác phải bị từ chối.
4. Tạo AppRole với **role_id** và **secret_id**, đăng nhập lấy client token và giải thích cách token nhận policy.
5. Dùng token hạn chế với **VaultTemplate** mà không đưa root token hay secret ID vào mã nguồn.
6. Đọc TTL, thử renew/revoke, phân biệt quyền trên token với lease của dynamic secrets và xử lý lỗi theo nguyên nhân.

**Giới hạn an toàn:** Các giá trị trong bài chỉ dành cho Vault cục bộ, chứa dữ liệu giả và chạy trong phòng lab. HTTP, root token cố định và cách in token vào terminal ở một vài lệnh minh họa không phù hợp với môi trường thật. Không commit token, role secret ID, unseal key, private key hoặc dữ liệu secret vào Git.

## 2. Token, role và policy liên hệ với nhau thế nào?

| Khái niệm | Vai trò | Ví dụ của bài |
| --- | --- | --- |
| **Vault policy** | Quy định capability nào được áp dụng trên API path nào | **orders-reader** cho phép **read** KV v2 |
| **Client token** | Credential được gửi khi gọi Vault API; mang tập policy và thuộc tính vòng đời | Token thử nghiệm TTL 15 phút |
| **Auth method** | Cơ chế xác thực để nhận client token | **token/**, **AppRole**, Kubernetes, JWT/OIDC, cloud auth |
| **AppRole role** | Cấu hình cách một workload nhận token, gồm policies, TTL, giới hạn secret ID… | **orders-api** trong mount **lab-approle/** |
| **role của PKI engine** | Ràng buộc dữ liệu được phát hành bởi PKI, như tên miền/TTL chứng chỉ | **lab-server** trong **lab-pki/roles/** |
| **Khóa Transit** | Khóa do Transit quản lý để mã hóa/giải mã | **orders-lab** ở mount **lab-transit/** |

**Một role không tự thay thế policy.** AppRole role chỉ định policy gắn lên token khi đăng nhập; Vault sau đó kiểm tra **capabilities của token tại đường dẫn được gọi**. PKI role lại là cấu hình *của engine phát hành chứng chỉ*: người dùng vẫn phải có Vault policy cho endpoint phát hành tương ứng.

~~~mermaid
flowchart LR
    A["Java workload<br/>orders-api"] -->|"role_id + secret_id"| B["auth/lab-approle/login"]
    B -->|"client token"| C["Vault API"]
    P["Policy orders-reader"] -. "gắn vào token" .-> C
    C -->|"read lab-kv/data/apps/orders/config"| D["KV v2 secret"]
    C -. "write/billing/transit<br/>bị từ chối" .-> E["Các path ngoài policy"]
~~~

Một token mang policy **default** có thể có quyền tự xem thông tin token hoặc thao tác phiên cá nhân tùy cấu hình Vault, nhưng **default không cấp quyền đọc tất cả secrets**. Trái lại, **root token** có quyền đặc biệt rất rộng, không đại diện cho các workload ứng dụng.

## 3. Chuẩn bị phòng lab và dữ liệu mẫu

### 3.1. Điều kiện cần

Bài dùng Vault dev mode trong Docker với service tên **vault** và cổng host **127.0.0.1:8200**. Một cấu hình Compose tối thiểu:

~~~yaml
services:
  vault:
    image: hashicorp/vault:1.19.0
    command: server -dev -dev-listen-address=0.0.0.0:8200
    cap_add:
      - IPC_LOCK
    environment:
      VAULT_ADDR: http://127.0.0.1:8200
      VAULT_DEV_ROOT_TOKEN_ID: dev-root-only
      VAULT_TOKEN: dev-root-only
    ports:
      - "127.0.0.1:8200:8200"
    restart: "no"
~~~

Chạy các lệnh trong thư mục chứa **compose.yaml**:

~~~bash
docker compose up -d
docker compose exec -T vault vault status
docker compose exec -T vault vault secrets list -detailed
docker compose exec -T vault vault auth list
~~~

Kỳ vọng Vault có **Initialized: true**, **Sealed: false**. Các lệnh **docker compose exec -T vault vault ...** thực thi Vault CLI **trong container**, nơi root token dev được đặt sẵn để người quản trị cấu hình lab. Phần kiểm thử ứng dụng ở các mục sau sẽ **ghi đè token mặc định**; nếu không, mọi bài kiểm tra phân quyền rất dễ cho kết quả sai.

Ví dụ dưới đây giả sử tồn tại các mount và tài nguyên:

| Mount/tài nguyên | API path được dùng | Chức năng |
| --- | --- | --- |
| KV v2 mount **lab-kv/**, key **apps/orders/config** | **lab-kv/data/apps/orders/config** | Orders API đọc cấu hình |
| KV v2 key **apps/billing/config** | **lab-kv/data/apps/billing/config** | Dữ liệu để thử truy cập trái quyền |
| Transit mount **lab-transit/**, key **orders-lab** | **lab-transit/encrypt/orders-lab** | Worker mã hóa |
| PKI mount **lab-pki/**, role **lab-server** | **lab-pki/issue/lab-server** | Job xin chứng chỉ |

Nếu một mount **chưa tồn tại**, có thể khởi tạo trong Vault lab sạch bằng các lệnh tương ứng sau. **Không chạy lại lệnh enable** với mount đã có; không tạo lại root CA trên môi trường chứa dữ liệu cần giữ:

~~~bash
docker compose exec -T vault vault secrets enable -path=lab-kv kv-v2
docker compose exec -T vault vault kv put -mount=lab-kv apps/orders/config app_name=orders-api timeout_ms=1500
docker compose exec -T vault vault kv put -mount=lab-kv apps/billing/config app_name=billing-api api_token=fake-demo-token

docker compose exec -T vault vault secrets enable -path=lab-transit transit
docker compose exec -T vault vault write -f lab-transit/keys/orders-lab

docker compose exec -T vault vault secrets enable -path=lab-pki pki
docker compose exec -T vault vault secrets tune -max-lease-ttl=8760h lab-pki
docker compose exec -T vault vault write -field=certificate lab-pki/root/generate/internal common_name=lab.internal ttl=8760h
docker compose exec -T vault vault write lab-pki/roles/lab-server allowed_domains=lab.internal allow_subdomains=true max_ttl=24h
~~~

Với lab đã có sẵn, bỏ qua các lệnh khởi tạo tương ứng và dùng **vault secrets list -detailed**, **vault kv get**, **vault read** để xác nhận trạng thái. Ví dụ cố ý sử dụng **example data**; role PKI chỉ phát hành tên trong miền giả **lab.internal**.

## 4. Thiết kế quyền trước khi tạo token

Chọn ba workload với nhu cầu riêng. Phân quyền theo thao tác thực tế giúp phát hiện lỗi dễ hơn so với tạo một token có mọi quyền.

| Workload | Policy | Được phép | Phải bị từ chối |
| --- | --- | --- | --- |
| **orders-api** | **orders-reader** | Read **lab-kv/data/apps/orders/config** | Ghi KV, đọc Billing, dùng Transit, cấp chứng chỉ |
| **orders-worker** | **transit-encryptor** | Update **lab-transit/encrypt/orders-lab** | Transit decrypt, đọc KV, chỉnh khóa |
| **certificate-job** | **pki-issuer** | Update **lab-pki/issue/lab-server** | Chỉnh role PKI, cấp qua role khác, đọc KV |

Trong policy Vault, capability **update** thường được yêu cầu cho endpoint **Transit encrypt/decrypt** và **PKI issue**, dù thao tác mang ý nghĩa mã hóa hoặc phát hành. Đừng tự suy ra rằng mọi endpoint có tên **read** đều chỉ dùng GET; phải đối chiếu **phương thức API** và **đường dẫn thực tế**.

### 4.1. Policy đọc KV v2 cho Orders

Tạo tệp **policies/orders-reader.hcl** trên máy host:

~~~hcl
path "lab-kv/data/apps/orders/config" {
  capabilities = ["read"]
}
~~~

Đường dẫn **data/** rất quan trọng với **KV v2**. Với CLI, người học có thể gọi:

~~~bash
vault kv get -mount=lab-kv apps/orders/config
~~~

nhưng Vault thực sự xử lý API path **GET /v1/lab-kv/data/apps/orders/config**. Nếu viết policy chỉ cho **lab-kv/apps/orders/config**, token sẽ không có quyền đọc KV v2 như mong đợi.

**Không cần thêm capability list** chỉ để đọc một key đã biết. Nếu bài yêu cầu liệt kê key bằng **vault kv list**, phải cấp thêm **list** trên các đường dẫn phù hợp dưới **lab-kv/metadata/**. Tránh cấp **lab-kv/metadata/** rộng chỉ để sửa một lệnh đọc.

### 4.2. Policy chỉ mã hóa cho Transit

Tạo **policies/transit-encryptor.hcl**:

~~~hcl
path "lab-transit/encrypt/orders-lab" {
  capabilities = ["update"]
}
~~~

Không có **lab-transit/decrypt/orders-lab**, vì trong tình huống giả lập worker chỉ mã hóa rồi gửi ciphertext cho thành phần khác. Cũng không có quyền **lab-transit/keys/orders-lab** để tạo, sửa hoặc xóa khóa.

### 4.3. Policy chỉ phát hành chứng chỉ theo role

Tạo **policies/pki-issuer.hcl**:

~~~hcl
path "lab-pki/issue/lab-server" {
  capabilities = ["update"]
}
~~~

Policy chỉ cho phép gọi endpoint của role **lab-server**. Chính **PKI role** mới kiểm soát tên miền, độ dài thời hạn và các ràng buộc phát hành. Vì vậy cần kiểm tra **cả** policy và role; policy rộng không thay thế cấu hình role chặt chẽ.

### 4.4. Nạp và kiểm tra policy

Sau khi tạo các file trong thư mục **policies/**:

~~~bash
docker compose cp policies/orders-reader.hcl vault:/tmp/orders-reader.hcl
docker compose cp policies/transit-encryptor.hcl vault:/tmp/transit-encryptor.hcl
docker compose cp policies/pki-issuer.hcl vault:/tmp/pki-issuer.hcl

docker compose exec -T vault vault policy write orders-reader /tmp/orders-reader.hcl
docker compose exec -T vault vault policy write transit-encryptor /tmp/transit-encryptor.hcl
docker compose exec -T vault vault policy write pki-issuer /tmp/pki-issuer.hcl

docker compose exec -T vault vault policy read orders-reader
docker compose exec -T vault vault policy read transit-encryptor
docker compose exec -T vault vault policy read pki-issuer
~~~

Các lệnh **vault policy write** tạo/cập nhật định nghĩa policy theo tên; không tự cấp token cho workload. Không cần thêm **deny** trên mọi path khác: Vault mặc định từ chối thao tác chưa được policy cho phép. Khi kiểm thử, phải kiểm tra các policy khác có thể được gắn cùng token để tránh hiệu ứng cộng quyền ngoài ý muốn.

## 5. Cách 1: Token ngắn hạn để chạy smoke test

Token tạo trực tiếp phù hợp khi học API hoặc thực hiện kiểm thử thủ công. Đây là bước đơn giản nhất để xác nhận policy hoạt động trước khi thêm phức tạp của AppRole.

### 5.1. Phát hành token cho từng workload

Lệnh dưới đây chạy bằng root token **chỉ trong container quản trị lab**:

~~~bash
docker compose exec -T vault vault token create -policy=orders-reader -ttl=15m -field=token
docker compose exec -T vault vault token create -policy=transit-encryptor -ttl=15m -field=token
docker compose exec -T vault vault token create -policy=pki-issuer -ttl=15m -field=token
~~~

Mỗi lệnh in ra **một token khác nhau**. Token thường được gắn thêm **default policy**, trừ khi người tạo cấu hình bỏ policy mặc định; default policy không cho phép tự động đọc các secret tùy ý. TTL yêu cầu có thể chịu giới hạn từ cấu hình Vault, auth/token role và parent token, nên **kiểm tra TTL thực tế** sau khi tạo.

Để không nhầm ba credential, đặt tên biến shell tương ứng. Trên **bash/zsh**, tự nhập token nhận được vào chỗ giữ chỗ:

~~~bash
export ORDERS_TOKEN="<token-orders-reader>"
export ENCRYPT_TOKEN="<token-transit-encryptor>"
export PKI_TOKEN="<token-pki-issuer>"
~~~

Trên **PowerShell**:

~~~powershell
$env:ORDERS_TOKEN = "<token-orders-reader>"
$env:ENCRYPT_TOKEN = "<token-transit-encryptor>"
$env:PKI_TOKEN = "<token-pki-issuer>"
~~~

Đây là thao tác thủ công trong lab. Với production, không copy token qua tài liệu, chat, issue tracker, ảnh chụp màn hình hoặc file cấu hình được commit. Tránh để command history hoặc log CI ghi lại giá trị credential.

### 5.2. Ghi đè token root mặc định khi thử quyền

Vì **compose.yaml** đã đặt **VAULT_TOKEN=dev-root-only** cho container, cần dùng tham số **-e** để gửi **token workload** khi gọi CLI. Với bash/zsh:

~~~bash
docker compose exec -T -e "VAULT_TOKEN=$ORDERS_TOKEN" vault vault kv get -mount=lab-kv apps/orders/config
docker compose exec -T -e "VAULT_TOKEN=$ORDERS_TOKEN" vault vault kv get -mount=lab-kv apps/billing/config
docker compose exec -T -e "VAULT_TOKEN=$ORDERS_TOKEN" vault vault kv put -mount=lab-kv apps/orders/config timeout_ms=9999
~~~

Trong PowerShell, thay **"$ORDERS_TOKEN"** thành **"$env:ORDERS_TOKEN"** bên trong chuỗi **VAULT_TOKEN=...**. Ví dụ:

~~~powershell
docker compose exec -T -e "VAULT_TOKEN=$env:ORDERS_TOKEN" vault vault kv get -mount=lab-kv apps/orders/config
~~~

Kết quả kỳ vọng:

| Request bằng token Orders | Kết quả | Vì sao? |
| --- | --- | --- |
| Đọc **apps/orders/config** | Thành công | Policy cho **read** trên path KV v2 tương ứng |
| Đọc **apps/billing/config** | **403 permission denied** | Billing nằm ngoài policy |
| Ghi **apps/orders/config** | **403 permission denied** | Policy không có capability ghi |

Thao tác thử **kv put** cố ý bị từ chối và không được làm thay đổi secret. Nếu ghi thành công, hãy kiểm tra token gửi vào container và tập policies của token, đặc biệt xem có vô tình dùng **root token** hoặc một policy rộng khác không.

### 5.3. Thử Transit và PKI bằng token đúng vai trò

**Transit** nhận plaintext ở dạng Base64. Giá trị **cGluZy10ZXN0** là Base64 của chuỗi thử nghiệm **ping-test**:

~~~bash
docker compose exec -T -e "VAULT_TOKEN=$ENCRYPT_TOKEN" vault vault write -field=ciphertext lab-transit/encrypt/orders-lab plaintext=cGluZy10ZXN0
~~~

Kết quả thành công trả ciphertext dạng **vault:v1:...**. Token **transit-encryptor** không có quyền giải mã; dù cầm ciphertext hợp lệ, gọi **lab-transit/decrypt/orders-lab** vẫn bị từ chối nếu không được cấp quyền **update** tại path đó.

**PKI** chỉ in trường certificate (khóa công khai) để tránh xuất private key ra terminal:

~~~bash
docker compose exec -T -e "VAULT_TOKEN=$PKI_TOKEN" vault vault write -field=certificate lab-pki/issue/lab-server common_name=orders.lab.internal ttl=1h
~~~

Nếu role PKI và CA đã được cấu hình, kết quả là chứng chỉ PEM. Trong phản hồi đầy đủ của API cấp chứng chỉ có thể có **private key**; không lưu nguyên phản hồi vào log. Việc phát hành là thao tác có tác dụng tạo chứng chỉ mới, không nên lặp lại tùy tiện khi kiểm thử.

**Lưu ý:** Một lỗi PKI như **common_name không được role cho phép** không nhất thiết là lỗi quyền policy; cần phân biệt quyền gọi API với việc dữ liệu đầu vào vi phạm ràng buộc của engine.

## 6. Cách 2: AppRole cho danh tính workload

Token thủ công giúp kiểm chứng policy. Với ứng dụng cần tự đăng nhập, **AppRole** cho phép định nghĩa **role** và dùng cặp **role_id + secret_id** để nhận client token mang policy tương ứng.

### 6.1. Tạo auth mount độc lập

Kiểm tra auth mounts:

~~~bash
docker compose exec -T vault vault auth list
~~~

Nếu chưa có **lab-approle/**, bật:

~~~bash
docker compose exec -T vault vault auth enable -path=lab-approle approle
~~~

Tên mount **lab-approle/** là một ví dụ; đường dẫn login chính xác sẽ là **auth/lab-approle/login**. Không nhầm mount này với secrets engine **lab-kv/** hoặc role PKI **lab-pki/roles/lab-server**.

### 6.2. Định nghĩa role gắn với policy

Tạo ba AppRole roles riêng. Ở đây **secret_id_num_uses=1** giúp quan sát hành vi secret ID dùng một lần trong lab:

~~~bash
docker compose exec -T vault vault write auth/lab-approle/role/orders-api bind_secret_id=true token_policies=orders-reader token_ttl=15m token_max_ttl=1h secret_id_ttl=30m secret_id_num_uses=1

docker compose exec -T vault vault write auth/lab-approle/role/orders-worker bind_secret_id=true token_policies=transit-encryptor token_ttl=15m token_max_ttl=1h secret_id_ttl=30m secret_id_num_uses=1

docker compose exec -T vault vault write auth/lab-approle/role/certificate-job bind_secret_id=true token_policies=pki-issuer token_ttl=15m token_max_ttl=1h secret_id_ttl=30m secret_id_num_uses=1
~~~

Từng tham số có ý nghĩa riêng:

| Tham số | Ý nghĩa |
| --- | --- |
| **bind_secret_id=true** | Yêu cầu secret ID khi đăng nhập AppRole |
| **token_policies** | Danh sách policy áp dụng lên **client token** nhận được |
| **token_ttl=15m** | TTL ban đầu được yêu cầu cho token |
| **token_max_ttl=1h** | Giới hạn thời gian sống/gia hạn cho token theo role và cấu hình Vault |
| **secret_id_ttl=30m** | Thời gian secret ID còn có thể được dùng để đăng nhập |
| **secret_id_num_uses=1** | Một secret ID chỉ dùng cho một lần đăng nhập thành công |

Thay đổi **token_policies** của role sẽ ảnh hưởng tới những token được tạo bởi các lần đăng nhập về sau; không giả định tập policy đã gắn trên mọi token đang tồn tại cũng tự thay đổi theo tên role. Ngược lại, sửa **nội dung một policy** có thể ảnh hưởng tới quyết định cấp quyền khi các token tham chiếu policy đó thực hiện request tiếp theo.

### 6.3. Lấy role ID, secret ID và đăng nhập

Người quản trị có thể lấy **role_id** và tạo **secret_id** mới cho Orders API:

~~~bash
docker compose exec -T vault vault read -field=role_id auth/lab-approle/role/orders-api/role-id
docker compose exec -T vault vault write -f -field=secret_id auth/lab-approle/role/orders-api/secret-id
~~~

**role_id** xác định role, còn **secret_id** là thành phần nhạy cảm phải được bảo vệ như một credential. Trong lab, nhập hai giá trị vào biến môi trường của shell:

~~~bash
export LAB_ROLE_ID="<role-id-vua-doc>"
export LAB_SECRET_ID="<secret-id-vua-tao>"
~~~

Trên PowerShell:

~~~powershell
$env:LAB_ROLE_ID = "<role-id-vua-doc>"
$env:LAB_SECRET_ID = "<secret-id-vua-tao>"
~~~

Gọi endpoint **login không cần root token**. Ví dụ bash/zsh dưới đây ghi đè biến **VAULT_TOKEN** trong container bằng giá trị rỗng để không dựa vào token quản trị:

~~~bash
docker compose exec -T -e "VAULT_TOKEN=" vault vault write -format=json auth/lab-approle/login role_id="$LAB_ROLE_ID" secret_id="$LAB_SECRET_ID"
~~~

Trên PowerShell:

~~~powershell
docker compose exec -T -e "VAULT_TOKEN=" vault vault write -format=json auth/lab-approle/login role_id="$env:LAB_ROLE_ID" secret_id="$env:LAB_SECRET_ID"
~~~

Trong JSON trả về, xem **auth.client_token**, **auth.policies**, **auth.lease_duration** và **auth.renewable**. Lấy **client token** mới nhận để thử đọc KV theo bước 5.2; không sử dụng root token. Đừng ghi lại JSON phản hồi vào file hoặc log vì nó chứa token.

**Phép thử bắt buộc:** Dùng lại cùng **secret_id** để login lần hai. Do role đặt **secret_id_num_uses=1**, lần đăng nhập sau phải bị từ chối. Điều này **không** có nghĩa client token nhận từ lần đăng nhập đầu tiên lập tức hết hạn; token có TTL và cơ chế thu hồi riêng. Khi ứng dụng cần đăng nhập lại, phải được cấp secret ID mới theo quy trình phân phối an toàn.

### 6.4. Xác thực theo workload trong môi trường vận hành

AppRole thích hợp cho một số môi trường, nhưng việc cấp phát và bảo vệ **secret_id** là trách nhiệm thiết kế riêng. Khi dịch vụ chạy trong Kubernetes hoặc một nền tảng cloud, cân nhắc auth method dựa trên danh tính thực của workload (ví dụ Kubernetes, JWT/OIDC hoặc auth method của cloud). Các phương thức này cũng trao client token, và policy vẫn phải giới hạn quyền dựa trên nhu cầu thực tế.

Trong production, nên quản lý được credential rotation, khả năng thu hồi, thời hạn, phạm vi workload, kênh phân phối và log truy vết. Không hardcode secret ID trong JAR, image Docker, YAML được commit hoặc pipeline output.

## 7. Dùng token hạn chế với VaultTemplate

Để kiểm chứng phần cấu hình quyền từ Java, trước hết dùng một token **orders-reader** ngắn hạn. Ví dụ này sử dụng thư viện **Spring Vault Core**, dependency Maven/Gradle có tọa độ **org.springframework.vault:spring-vault-core** và phiên bản phù hợp với nền Spring của dự án.

~~~java
import java.net.URI;
import java.util.Map;

import org.springframework.vault.authentication.TokenAuthentication;
import org.springframework.vault.client.VaultEndpoint;
import org.springframework.vault.core.VaultTemplate;
import org.springframework.vault.support.Versioned;

public class OrdersVaultSmokeTest {
    public static void main(String[] args) {
        String address = System.getenv("VAULT_ADDR");
        String token = System.getenv("VAULT_TOKEN");
        if (address == null || address.isBlank()
                || token == null || token.isBlank()) {
            throw new IllegalStateException(
                    "Missing VAULT_ADDR or VAULT_TOKEN");
        }

        VaultEndpoint endpoint =
                VaultEndpoint.from(URI.create(address));
        VaultTemplate template =
                new VaultTemplate(endpoint, new TokenAuthentication(token));

        Versioned<Map<String, Object>> secret = template
                .opsForVersionedKeyValue("lab-kv")
                .get("apps/orders/config");
        if (secret == null || secret.getData() == null) {
            throw new IllegalStateException("Config not found");
        }

        // Log tên trường, không xuất giá trị secret.
        System.out.println("Fields: " + secret.getData().keySet());
    }
}
~~~

Đặt biến môi trường trên máy chạy ứng dụng:

~~~bash
export VAULT_ADDR="http://127.0.0.1:8200"
export VAULT_TOKEN="$ORDERS_TOKEN"
~~~

~~~powershell
$env:VAULT_ADDR = "http://127.0.0.1:8200"
$env:VAULT_TOKEN = $env:ORDERS_TOKEN
~~~

Nếu policy, KV mount và token hợp lệ, chương trình in tên các trường trong **apps/orders/config**. **VaultTemplate** sẽ gọi endpoint KV v2 tương ứng **lab-kv/data/apps/orders/config**, đúng với policy đã viết.

Thử đổi logical key trong code thành **apps/billing/config**: request phải bị từ chối vì token không có quyền. Đây là phép kiểm thử thực tế cho nguyên tắc quyền tối thiểu; không cần một ứng dụng Spring Boot lớn để nhìn thấy lỗi policy.

**Đối với AppRole**, dùng thành phần **AppRoleAuthentication** của Spring Vault cùng cấu hình **role_id/secret_id**, auth mount chính xác và cơ chế quản lý phiên **SessionManager** thích hợp. Ví dụ sử dụng **TokenAuthentication** trực tiếp chỉ dành cho smoke test: token hết hạn hoặc bị revoke sẽ làm request tiếp theo thất bại, và chương trình không tự đăng nhập lại.

Trong môi trường thật, địa chỉ thường dùng HTTPS; JVM/HTTP client phải tin cậy CA và xác minh hostname. Thay token không phải là biện pháp xử lý lỗi TLS.

## 8. Vòng đời token, lease và thu hồi quyền

### 8.1. Quan sát token đang dùng

Với token Orders trong bash/zsh:

~~~bash
docker compose exec -T -e "VAULT_TOKEN=$ORDERS_TOKEN" vault vault token lookup
~~~

Kiểm tra các thông tin như **policies**, **ttl**, **renewable** và **creation_time** khi có. Token có thể mang nhiều policy; quyền thực tế là kết quả đánh giá các policy gắn với token cùng các cơ chế kiểm soát khác của Vault.

Nếu token được phép renew, có thể thử:

~~~bash
docker compose exec -T -e "VAULT_TOKEN=$ORDERS_TOKEN" vault vault token renew -increment=10m
~~~

Việc renew **không được bảo đảm luôn thành công**: token có thể không renewable, vượt **max_ttl**, đã hết hạn hoặc bị revoke. Token ở ví dụ được tạo với TTL ngắn để quan sát hành vi; đừng giả định mọi token đều có thể sống mãi bằng renew.

Để chủ động thu hồi token Orders trong lab, dùng quyền quản trị:

~~~bash
docker compose exec -T vault vault token revoke "<token-orders-reader>"
~~~

Thay placeholder bằng token thật khi thực hành. Sau khi revoke, thử đọc KV bằng token cũ và kiểm tra lỗi. Không tiếp tục dùng token đã thu hồi; nếu cần test lại, tạo token mới. Token có thể bị lộ khi nhập ở dòng lệnh hoặc qua cơ chế quan sát process; chỉ sử dụng thao tác đơn giản này trong lab. Ở môi trường vận hành, cân nhắc quy trình thu hồi qua accessor và công cụ quản trị bí mật phù hợp.

### 8.2. Secret ID không phải client token

| Thành phần | Được dùng để làm gì? | Hết hạn/thu hồi có tác động gì? |
| --- | --- | --- |
| **AppRole role_id** | Định danh AppRole role | Không phải token truy cập Vault API |
| **AppRole secret_id** | Kết hợp role_id để đăng nhập | Secret ID hết hạn/hết lượt dùng làm lần login tiếp theo thất bại |
| **Client token** | Xác thực từng request sau login | Token hết hạn/revoke khiến request không còn được chấp nhận |
| **Dynamic secret lease_id** | Quản lý vòng đời secret động từ engine hỗ trợ | Lease có thể có TTL, khả năng renew/revoke riêng |
| **KV v2 version** | Chỉ một phiên bản dữ liệu tĩnh của key | Không phải TTL hay lease cấp cho client |

Nếu dùng **database secrets engine** để phát hành user/password động, Vault có thể trả **lease_id** và **lease_duration**. Đó là vòng đời của secret được cấp, khác với vòng đời token đã dùng để xin secret. Bài này chưa bật database engine nên không tự bịa ra lease cho KV v2.

### 8.3. Quyền có thể thay đổi trong khi token còn sống

Hai thao tác quản trị có ảnh hưởng khác nhau:

- **Sửa nội dung policy orders-reader**: quyết định cấp quyền ở các request tiếp theo có thể thay đổi đối với token đang mang policy đó.
- **Sửa role AppRole để gắn policy khác**: token phát hành từ các lần đăng nhập sau có thể nhận tập policy mới; token đã phát hành vẫn mang tập tên policy gắn tại thời điểm phát hành, trừ khi token được thay thế/thu hồi.

Trong bài thực hành, nên ưu tiên tạo policy hoặc token thử nghiệm mới thay vì thay đổi policy đang dùng bởi nhiều workload, để phép kiểm thử không gây tác dụng phụ bất ngờ.

## 9. Chẩn đoán lỗi quyền và xác thực

| Hiện tượng | Điều cần phân biệt | Cách kiểm tra |
| --- | --- | --- |
| **403** khi đọc KV v2 | Token không hợp lệ, thiếu policy hoặc sai **data/** path | Xem token đang dùng, **vault policy read**, API path |
| **403** khi ghi KV nhưng đọc thành công | Hợp lệ nếu role chỉ có **read** | Xác minh capability, không mở rộng quyền nếu không cần |
| **403** khi Transit decrypt | Token chỉ có quyền encrypt | Kiểm tra path **lab-transit/decrypt/orders-lab** |
| AppRole login lần hai thất bại | **secret_id_num_uses=1** hoặc secret ID hết TTL | Cấp secret ID mới; xem cấu hình role |
| **404** khi đọc secret | Mount/key/version chưa tồn tại hoặc path sai | **vault secrets list**, **vault kv get -mount=...** |
| PKI từ chối tên miền | Role PKI không cho phép common name | Kiểm tra **lab-pki/roles/lab-server** |
| **connection refused/timeout** | Không kết nối được Vault; chưa phải lỗi policy | Docker, **VAULT_ADDR**, cổng, firewall |
| Lỗi TLS/certificate | CA không được tin cậy hoặc hostname không hợp lệ | Trust store, certificate SAN, URL |
| Đọc được mọi secret dù policy rất hẹp | Thường đang dùng root token hoặc token khác có quyền rộng | Kiểm tra biến môi trường và token policies |

Không coi mọi lỗi là **403**: một token hợp lệ nhưng đọc key không tồn tại có thể nhận kết quả rỗng/404 tùy API/client. Ngược lại, với token thiếu quyền, Vault có thể trả 403 trước khi xác nhận key có tồn tại.

Các thông tin nên ghi vào log ứng dụng khi xử lý lỗi: loại thao tác, đường dẫn logic, mã HTTP, thời lượng request, lần retry và correlation ID. Không log toàn bộ Vault response nếu có nguy cơ chứa secret, token, private key hoặc giá trị cấu hình nhạy cảm.

## 10. Kiểm thử tích hợp và cách tổ chức quyền lâu dài

Với **Testcontainers VaultContainer** hoặc Vault dev độc lập trong CI, khởi tạo mount, policy và dữ liệu giả theo đúng thứ tự, sau đó kiểm thử bằng token của từng workload. Tách một tài khoản bootstrap có quyền cao khỏi tài khoản dùng trong test nghiệp vụ.

Một bộ kiểm thử hữu ích gồm:

1. **orders-api** đăng nhập hợp lệ và đọc **apps/orders/config** thành công bằng **VaultTemplate**.
2. Cùng token Orders không ghi được **apps/orders/config** và không đọc được **apps/billing/config**.
3. **orders-worker** gọi Transit encrypt thành công nhưng decrypt bị từ chối; không cần quyền xem vật liệu khóa.
4. **certificate-job** xin chứng chỉ **orders.lab.internal** qua đúng PKI role; common name không được phép phải bị từ chối bởi ràng buộc PKI.
5. Token hết hạn/revoke dẫn đến phản hồi lỗi rõ ràng, session manager (nếu có) xử lý theo chiến lược xác thực.
6. AppRole secret ID chỉ dùng một lần không thể đăng nhập lần thứ hai; token đã nhận vẫn có vòng đời riêng.
7. Mất kết nối Vault hoặc sai CA không bị báo nhầm thành lỗi policy; retry có giới hạn và không làm lộ credential.

Kiểm thử phải độc lập với token thủ công của người học và không kết nối tới Vault thật. Trong hệ thống có nhiều môi trường, nên tách danh tính ứng dụng, mounts/namespaces hoặc cụm Vault theo ranh giới quản trị phù hợp; quyền trong dev mode chỉ là mô hình để kiểm tra cách thiết kế, không thay thế đánh giá bảo mật production.

### 10.1. Checklist trước khi cấp credential cho ứng dụng

- [ ] Đã xác định rõ workload nào cần KV read, Transit encrypt/decrypt hoặc PKI issue.
- [ ] Policy chứa **đúng API path** và capability, đặc biệt **data/** với KV v2.
- [ ] Mỗi workload dùng token/role riêng; không dùng root token trong Java.
- [ ] TTL/khả năng renew/re-login phù hợp với thời gian sống của workload.
- [ ] Secret ID, token và private key được phân phối/lưu trữ an toàn.
- [ ] Thử ít nhất một thao tác **được phép** và một thao tác **bị từ chối**.
- [ ] Có kế hoạch revoke/rotation, log không lộ bí mật và test trường hợp hết hạn.
- [ ] Ứng dụng xác minh TLS/CA khi kết nối đến Vault vận hành.

## 11. Bài tập tự đánh giá

**Bài 1 — Sửa quyền KV v2.** Tạo policy **billing-reader** chỉ cho phép đọc **lab-kv/data/apps/billing/config**. Cấp token TTL 10 phút và chứng minh token này không đọc được Orders, không ghi được Billing.

**Bài 2 — Phân biệt role và policy.** Tạo AppRole **billing-api** gắn policy **billing-reader**. Hãy chỉ ra thành phần nào giữ danh tính workload, thành phần nào cấp quyền và thành phần nào thực sự được gửi trong request đọc secret.

**Bài 3 — Transit quyền một chiều.** Dùng policy **transit-encryptor**, mã hóa **ping-test** thành ciphertext. Thử decrypt bằng cùng token và giải thích nguyên nhân bị từ chối. Sau đó thiết kế một role **orders-decryptor** độc lập chỉ dành cho dịch vụ cần giải mã.

**Bài 4 — Vòng đời.** Tạo AppRole secret ID dùng một lần, đăng nhập và ghi lại TTL của token (không ghi token). Sau khi sử dụng secret ID, thử đăng nhập lại; phân biệt lỗi hết lượt secret ID với lỗi token hết hạn.

**Bài 5 — Java.** Chạy smoke test **VaultTemplate** với token Orders và token Billing. Giải thích vì sao cùng một đoạn code/đường dẫn có kết quả khác nhau khi đổi **VAULT_TOKEN**, dù ứng dụng không đổi API.

**Tiêu chí hoàn thành:** Bạn chuẩn bị được token hoặc AppRole role với policy vừa đủ cho ví dụ, giải thích đúng luồng **workload → auth method → token → policy → API path**, xác minh được các thao tác bị chặn, và biết quản lý vòng đời token/secret ID mà không dùng root token trong ứng dụng.
