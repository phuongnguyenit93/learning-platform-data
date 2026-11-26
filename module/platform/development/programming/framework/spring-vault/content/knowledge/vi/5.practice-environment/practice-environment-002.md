# Phân biệt máy chủ chế độ dev với cấu hình vận hành

## 1. Vì sao cần phân biệt?

Trong quá trình học **Spring Vault**, một ứng dụng Java thường kết nối đến **HashiCorp Vault** qua **VaultTemplate** để đọc KV secrets, gọi Transit encryption, sử dụng PKI hoặc thực hiện các tác vụ cần token và lease. Cùng một đoạn code Java có thể kết nối được cả Vault **dev mode** và Vault được cấu hình để vận hành, nhưng hai loại máy chủ này khác nhau căn bản về **dữ liệu được giữ lại**, **cách khởi tạo và mở khóa**, **bảo vệ kết nối** và **quản trị quyền**.

**Dev mode** là một chế độ khởi chạy Vault được thiết kế để thử nghiệm nhanh. **Cấu hình vận hành (non-dev)** là cách chạy Vault với các khối cấu hình tường minh về listener, storage, seal, địa chỉ cụm và các biện pháp bảo vệ phù hợp. Chạy Vault không có cờ **-dev** chưa có nghĩa hệ thống đã sẵn sàng production: một non-dev server vẫn có thể chỉ là một máy lab yếu về bảo mật và độ sẵn sàng.

Sau bài này, người học có thể:

- Nhận biết khác biệt giữa lệnh khởi chạy **vault server -dev** và **vault server -config=...**.
- Giải thích vòng đời **init → sealed → unseal → active/standby** của máy chủ non-dev.
- Phân tích ảnh hưởng của bộ lưu trữ, TLS, quyền truy cập, HA, backup, giám sát và audit đối với hệ thống dùng Spring Vault.
- Đọc một ví dụ cấu hình Vault non-dev dùng **integrated storage (Raft)**, đồng thời xác định các phần còn thiếu trước khi triển khai thật.
- Thực hiện thí nghiệm quan sát mất dữ liệu ở dev mode và xây dựng bảng kiểm chứng trước khi chuyển ứng dụng Java sang môi trường vận hành.

> **Ranh giới bài thực hành:** Các giá trị token, hostname, chứng chỉ và secrets trong ví dụ đều là dữ liệu minh họa. Không đưa root token, unseal key, recovery key, secret ID, private key hoặc file snapshot nhạy cảm vào repository.

## 2. So sánh từng khía cạnh

| Khía cạnh | Vault dev mode | Vault non-dev được tổ chức để vận hành |
| --- | --- | --- |
| Mục đích | Thử API, học CLI, làm smoke test và thí nghiệm ngắn | Cung cấp dịch vụ secrets có khả năng quản trị, kiểm soát rủi ro và khôi phục |
| Cách chạy | **vault server -dev** với các tùy chọn dev | **vault server -config=/path/vault.hcl** hoặc nhiều file cấu hình |
| Khởi tạo Vault | Tự động init và unseal khi tiến trình bắt đầu | Cần init một lần cho cụm mới; unseal bằng quy trình đã thiết kế |
| Storage | Mặc định lưu trong bộ nhớ, mất dữ liệu khi tiến trình dev kết thúc | Cấu hình storage bền vững, ví dụ integrated storage (Raft) |
| Root token | Có root token thử nghiệm được xuất hoặc định sẵn | Initial root token chỉ được sinh khi init; phải kiểm soát vòng đời và quyền sử dụng |
| TLS | Mặc định nghe HTTP, thường dùng localhost | Nên dùng TLS hợp lệ; client phải tin cậy CA và xác minh hostname |
| Xác thực workload | Dễ thử bằng token hoặc AppRole | Chọn auth method theo danh tính workload; quản lý cấp phát và vòng đời credential |
| Policy | Có thể thử nhanh nhưng dễ bị bỏ qua nếu mọi thứ dùng root token | Policy theo nguyên tắc quyền tối thiểu và tách trách nhiệm |
| Tính sẵn sàng | Phục vụ một phiên học cục bộ | Cần thiết kế số node, quorum, HA, địa chỉ truy cập và cơ chế chuyển vai |
| Giám sát/audit | Có health API, log; audit không tự bật chỉ vì ở dev mode | Bật audit device, telemetry, cảnh báo và giới hạn truy cập log theo yêu cầu |
| Sao lưu/khôi phục | Không phù hợp để kiểm chứng độ bền dữ liệu | Có lịch backup, quản lý snapshot, diễn tập restore và quy trình sự cố |
| Nâng cấp/vận hành | Có thể xóa và tạo lại dễ dàng | Cần kế hoạch nâng cấp, rollback, kiểm tra tương thích API/client và khôi phục |

Điểm dễ nhầm: **dev mode không có nghĩa mọi API bị mô phỏng**. Bạn vẫn có thể tạo AppRole, policy, KV v2, Transit hay PKI và gọi chúng bằng Spring Vault thật. Khác biệt là trạng thái và các cơ chế vận hành quanh Vault không phản ánh đầy đủ một cụm production.

### 2.1. Hai vòng đời khởi động

~~~mermaid
flowchart TB
    subgraph DEV["Dev mode"]
        A["vault server -dev"] --> B["Tự init + unseal"]
        B --> C["Sẵn sàng dùng root token dev"]
        C --> D["Tiến trình dừng / khởi động lại"]
        D --> E["Trạng thái dev trước đó bị mất"]
    end
    subgraph NONDEV["Non-dev với Shamir seal"]
        F["vault server -config=..."] --> G{"Cụm đã init?"}
        G -- "Chưa" --> H["vault operator init — một lần"]
        G -- "Rồi" --> I["Trạng thái sealed sau khi khởi động"]
        H --> I
        I --> J["Unseal đủ ngưỡng khóa"]
        J --> K["Active / standby theo topology"]
        K --> L["Dữ liệu được lưu trên storage đã cấu hình"]
    end
~~~

Sơ đồ non-dev minh họa **Shamir seal** (mở khóa thủ công). Nếu cấu hình **auto-unseal** qua KMS/HSM hoặc cơ chế seal được hỗ trợ, bước mở khóa và việc giữ **recovery keys** có đặc điểm khác. Không suy ra rằng mọi non-dev server đều luôn phải nhập từng unseal key sau mỗi lần khởi động.

## 3. Quan sát trực tiếp một Vault dev

### 3.1. Tạo một máy chủ dùng một lần

Nếu đã có Docker và cổng 8200 còn trống, có thể chạy thí nghiệm độc lập bằng lệnh:

~~~bash
docker run -d --rm --name vault-dev-compare \
  -p 127.0.0.1:8200:8200 \
  -e VAULT_DEV_ROOT_TOKEN_ID=dev-root-only \
  hashicorp/vault:1.19.0 \
  server -dev -dev-listen-address=0.0.0.0:8200
~~~

Trong lệnh này, **-dev-listen-address=0.0.0.0:8200** là địa chỉ mà tiến trình Vault nghe **bên trong container**; ánh xạ Docker **127.0.0.1:8200:8200** chỉ công bố cổng trên loopback **của máy host**. Không thay bằng ánh xạ mọi interface khi chỉ học trên máy cá nhân.

Kiểm tra và tạo một secret giả lập:

~~~bash
docker exec -e VAULT_ADDR=http://127.0.0.1:8200 \
  -e VAULT_TOKEN=dev-root-only vault-dev-compare vault status

docker exec -e VAULT_ADDR=http://127.0.0.1:8200 \
  -e VAULT_TOKEN=dev-root-only vault-dev-compare \
  vault secrets enable -path=lab-kv kv-v2

docker exec -e VAULT_ADDR=http://127.0.0.1:8200 \
  -e VAULT_TOKEN=dev-root-only vault-dev-compare \
  vault kv put -mount=lab-kv app/config username=student password=demo-only

docker exec -e VAULT_ADDR=http://127.0.0.1:8200 \
  -e VAULT_TOKEN=dev-root-only vault-dev-compare \
  vault kv get -mount=lab-kv app/config
~~~

Bạn sẽ thấy máy chủ được báo **Initialized: true**, **Sealed: false**, và secret vừa ghi có thể được đọc lại. Lệnh **vault status** trong dev mode **không chứng minh** máy chủ đã cấu hình storage bền vững hoặc TLS.

### 3.2. Kiểm chứng điều gì xảy ra khi restart

~~~bash
docker restart vault-dev-compare

docker exec -e VAULT_ADDR=http://127.0.0.1:8200 \
  -e VAULT_TOKEN=dev-root-only vault-dev-compare \
  vault secrets list

docker exec -e VAULT_ADDR=http://127.0.0.1:8200 \
  -e VAULT_TOKEN=dev-root-only vault-dev-compare \
  vault kv get -mount=lab-kv app/config
~~~

Sau restart, mount **lab-kv/** tự tạo trước đó sẽ không còn; lệnh đọc secret có thể báo không tìm thấy mount/đường dẫn. Nguyên nhân là tiến trình Vault **dev mode** sử dụng storage trong bộ nhớ và khởi tạo lại khi bắt đầu. Kể cả có gắn một volume Docker không được cấu hình làm storage của Vault, volume đó cũng **không biến dev mode thành storage bền vững**.

Kết thúc thí nghiệm:

~~~bash
docker stop vault-dev-compare
~~~

**Lưu ý tái sử dụng:** Ví dụ tạo root token cố định và dùng HTTP chỉ nhằm xác minh hành vi dev mode; không đưa kiểu khởi chạy này lên máy public hoặc dùng với dữ liệu thật. Trên PowerShell, có thể nhập mỗi lệnh trên một dòng thay cho ký tự nối dòng **\\** của bash.

## 4. Khung cấu hình non-dev: những gì phải chỉ rõ

Một cấu hình vận hành phải trả lời tối thiểu bốn câu hỏi: **Vault lưu dữ liệu ở đâu? Client kết nối bằng kênh nào? Node tự nhận diện trong cụm ra sao? Cụm được init/unseal và phục hồi bằng quy trình nào?**

Ví dụ cấu hình **vault.hcl** dưới đây dùng **integrated storage (Raft)** và TLS:

~~~hcl
# Cấu hình minh họa cho một node non-dev.
# Các hostname, thư mục và chứng chỉ cần được cấp thật trước khi chạy.
ui = true
log_level = "info"

api_addr = "https://vault-1.lab.internal:8200"
cluster_addr = "https://vault-1.lab.internal:8201"

storage "raft" {
  path    = "/var/lib/vault"
  node_id = "vault-1"
}

listener "tcp" {
  address       = "0.0.0.0:8200"
  tls_cert_file = "/etc/vault/tls/vault.crt"
  tls_key_file  = "/etc/vault/tls/vault.key"
}
~~~

| Khối cấu hình | Ý nghĩa | Lỗi thực tế hay gặp |
| --- | --- | --- |
| **storage "raft"** | Dữ liệu Vault được ghi xuống đường dẫn bền vững; node có ID riêng | Đường dẫn không được ghi, volume không persistent, phân quyền file sai |
| **listener "tcp"** | Địa chỉ Vault lắng nghe request từ client; chứng chỉ và private key phục vụ TLS | Chưa có chứng chỉ, key sai quyền, CN/SAN không khớp hostname |
| **api_addr** | Địa chỉ API được Vault quảng bá cho client và các thành phần liên quan | Dùng localhost/địa chỉ container khiến client ở host khác không truy cập được |
| **cluster_addr** | Địa chỉ nội bộ cho giao tiếp trong cụm Vault | DNS/firewall hoặc cổng cụm không thông |
| **ui** | Cho phép sử dụng giao diện web | Tưởng UI chính là cơ chế xác thực/phân quyền |
| **log_level** | Mức log máy chủ | Ghi thiếu ngữ cảnh vận hành hoặc để mức debug liên tục |

Đây là **khung minh họa**, chưa phải cấu hình production hoàn chỉnh. Nó mô tả **một node** nên chưa tạo ra HA; để vận hành thực tế còn cần topology Raft, cách join node, quorum, volume, DNS, firewall, kiểm soát mlock/swap, quản lý khóa seal, service supervision, backup, audit, cảnh báo và quy trình khôi phục. Cần chuẩn bị DNS **vault-1.lab.internal**, chứng chỉ có SAN hợp lệ và đường dẫn lưu trữ có quyền phù hợp. **Không nên copy cấu hình này rồi coi hệ thống đã an toàn chỉ vì TLS được bật.**

Lệnh khởi chạy trên host/container đã được chuẩn bị đường dẫn:

~~~bash
vault server -config=/etc/vault/vault.hcl
~~~

Lệnh không sử dụng **-dev**. Vault sẽ đọc cấu hình và không tự tạo root token dev. Việc init/unseal và phân quyền phải được thực hiện theo quy trình quản trị.

### 4.1. Storage bền vững khác với backup

Integrated storage **Raft** giữ dữ liệu giữa những lần restart khi đường dẫn storage vẫn còn, nhưng **không thay thế backup**. Xóa volume, mất quorum, sai thao tác quản trị hoặc sự cố cụm đều có thể gây mất khả năng truy cập dữ liệu. Một hệ thống vận hành cần:

1. Lưu dữ liệu trên đĩa/volume được quản lý và bảo vệ quyền truy cập.
2. Thiết kế nhiều node và quorum phù hợp yêu cầu HA.
3. Tạo snapshot Raft định kỳ, bảo vệ bản snapshot như dữ liệu mật và thử restore vào môi trường tách biệt.
4. Ghi nhận bản Vault, storage, seal, phương thức khôi phục và những phụ thuộc ngoài Vault như KMS, DNS, CA.

Snapshot Raft thường được tạo qua lệnh **vault operator raft snapshot save** khi kết nối và quyền cho phép. Snapshot có thể chứa dữ liệu nhạy cảm đã được Vault mã hóa; vẫn phải kiểm soát truy cập, lưu trữ và quy trình phục hồi. **Snapshot không đồng nghĩa với việc backup được unseal/recovery keys hoặc cấu hình KMS bên ngoài.**

### 4.2. TLS phải hoạt động từ đầu cuối

Ở dev mode, client có thể dùng **http://127.0.0.1:8200**. Ở cấu hình vận hành, client nên dùng **https://vault-1.lab.internal:8200** hoặc một địa chỉ dịch vụ TLS tin cậy. Máy Java phải xác minh hostname và tin tưởng CA phát hành chứng chỉ server.

Ví dụ cấu hình CLI từ máy đã có CA:

~~~bash
export VAULT_ADDR="https://vault-1.lab.internal:8200"
export VAULT_CACERT="/path/to/trusted-ca.pem"
vault status
~~~

**VAULT_CACERT** ảnh hưởng đến Vault CLI, không tự động cấu hình trust store cho JVM. Với Java/Spring Vault, sử dụng trust store của JVM hoặc SSL configuration được hỗ trợ bởi HTTP client tương ứng. Tránh dùng cách bỏ qua xác minh chứng chỉ (**insecure skip verify**) để chữa lỗi TLS: việc đó làm mất khả năng xác minh Vault thật.

## 5. Init, sealed, unseal và HA

### 5.1. Khởi tạo cụm lần đầu

Với Vault non-dev mới chưa được init, người vận hành kết nối tới một node rồi thực hiện khởi tạo **một lần**. Ví dụ mô hình Shamir seal có năm key shares với ngưỡng ba:

~~~bash
vault operator init -key-shares=5 -key-threshold=3
~~~

Lệnh có thể xuất các unseal key shares và initial root token. Đây là thông tin cực kỳ nhạy cảm: phải phân phối và lưu theo quy trình bảo mật ngoài repository, ngoài CI log và ngoài lịch sử terminal được đồng bộ. Không chạy **operator init** lặp lại trên cụm đã khởi tạo; các node tham gia cùng cụm **không được init độc lập**.

Với Shamir seal, khi Vault còn **sealed**, cần đủ số key shares theo ngưỡng để **unseal**:

~~~bash
vault operator unseal
vault status
~~~

Chạy bước unseal theo hướng dẫn tương tác và quy trình giữ khóa; không ghi unseal key trực tiếp vào script. Nếu dùng auto-unseal, hành vi và loại khóa phục hồi khác: **recovery key không đồng nhất với unseal key Shamir và không thay thế khả năng truy cập KMS/HSM**.

### 5.2. Active, standby và quorum

Một cụm HA có node **active** xử lý yêu cầu và node **standby** sẵn sàng tiếp quản theo cơ chế HA của Vault. Với integrated storage Raft, các node phải duy trì **quorum** để hoạt động an toàn; nhiều container đơn lẻ trên cùng một máy cũng không đảm bảo HA trước sự cố máy chủ.

Phân biệt ba khái niệm:

- **Unsealed:** Vault đã có thể truy cập khóa cần thiết để hoạt động; chưa đảm bảo node có thể phục vụ mọi yêu cầu.
- **Active/standby:** vai trò của node trong topology HA; thay đổi khi failover.
- **Healthy/ready:** trạng thái dùng cho health check và khả năng tiếp nhận yêu cầu tại thời điểm đó; cần tính đến active/standby, sealed, uninitialized và loại node.

Một **single-node non-dev** có thể lưu dữ liệu bền vững nhưng **không có khả năng chịu lỗi node**. Ngược lại, việc tạo nhiều bản chạy dev không tạo nên một cụm Raft có HA.

## 6. Ảnh hưởng trực tiếp đến ứng dụng Spring Vault

Ứng dụng Java sử dụng **VaultTemplate** có thể gọi cùng API để lấy **KV v2 secrets**, làm việc với **Transit**, yêu cầu chứng chỉ từ **PKI** hoặc nhận secret động. Tuy nhiên, cách cấu hình client cần thay đổi khi rời môi trường học:

| Chủ đề phía Spring Vault | Trong bài lab dev | Trong môi trường vận hành |
| --- | --- | --- |
| Endpoint | **http://127.0.0.1:8200** | DNS/VIP hoặc địa chỉ dịch vụ có TLS và failover |
| Tin cậy server | Không có bước xác minh chứng chỉ với HTTP | Thiết lập CA/trust store, hostname validation |
| Authentication | Có thể dùng token thử nghiệm để học API | Xác thực theo workload: AppRole, Kubernetes, JWT/OIDC, cloud auth… tùy hạ tầng |
| Authorization | Dễ kiểm thử bằng policy giới hạn | Xem policy là hợp đồng quyền tối thiểu cho từng workload và engine path |
| Token lifecycle | Thử TTL ngắn, revoke, login lại | Dùng session/token manager phù hợp, xử lý renew và đăng nhập lại |
| Lease/secret động | Có thể thử lease bằng engine hỗ trợ | Theo dõi TTL, renew/revoke, rotation và thời gian sống của tài nguyên thật |
| Transit/PKI | Mã hóa dữ liệu giả, CA tự ký của lab | Chính sách encrypt/decrypt tách biệt, quản lý CA, phân phối chứng chỉ và thu hồi |
| Lỗi và giám sát | Đọc console/log thủ công | Metrics, alert, retry có giới hạn, audit và phân tích lỗi theo mã HTTP |

### 6.1. Tạo VaultTemplate không đồng nghĩa với đã sẵn sàng vận hành

Đoạn code dưới đây chỉ minh họa cách địa chỉ và thông tin xác thực ảnh hưởng đến client. Nó thích hợp làm **smoke test có kiểm soát** với token đã được cấp quyền giới hạn:

~~~java
import java.net.URI;
import java.util.Map;

import org.springframework.vault.authentication.TokenAuthentication;
import org.springframework.vault.client.VaultEndpoint;
import org.springframework.vault.core.VaultTemplate;
import org.springframework.vault.support.Versioned;

public class VaultConnectionCheck {
    public static void main(String[] args) {
        String address = System.getenv("VAULT_ADDR");
        String token = System.getenv("VAULT_TOKEN");
        if (address == null || address.isBlank()
                || token == null || token.isBlank()) {
            throw new IllegalStateException(
                    "Can cau hinh VAULT_ADDR va VAULT_TOKEN");
        }

        VaultEndpoint endpoint = VaultEndpoint.from(URI.create(address));
        VaultTemplate vault = new VaultTemplate(
                endpoint, new TokenAuthentication(token));

        Versioned<Map<String, Object>> secret = vault
                .opsForVersionedKeyValue("lab-kv")
                .get("app/config");

        if (secret == null || secret.getData() == null) {
            throw new IllegalStateException("Khong tim thay secret");
        }
        // Không in giá trị secret ra log.
        System.out.println("Truong du lieu: " + secret.getData().keySet());
    }
}
~~~

Với môi trường vận hành, ứng dụng không nên giữ một root token hoặc hardcode token trong source code. Cần dùng phương thức đăng nhập theo danh tính workload, quản lý session/token và cấu hình trust store phù hợp. Một cách là dùng thành phần **ClientAuthentication** và **SessionManager** trong Spring Vault; chiến lược renew/đăng nhập lại phụ thuộc auth method và vòng đời credential cấp cho workload.

**Đường dẫn KV v2** cũng quan trọng với policy: thao tác **opsForVersionedKeyValue("lab-kv").get("app/config")** đọc dữ liệu qua API path **lab-kv/data/app/config**. Policy chỉ ghi **lab-kv/app/config** sẽ không cấp đúng quyền trên endpoint KV v2.

Một policy chỉ đọc có thể bắt đầu từ:

~~~hcl
path "lab-kv/data/app/config" {
  capabilities = ["read"]
}
~~~

Policy này không cho phép ghi KV, yêu cầu Transit decrypt hay phát hành PKI; các quyền như **lab-transit/encrypt/orders**, **lab-transit/decrypt/orders** và **lab-pki/issue/lab-server** phải được cấp riêng cho từng workload đúng nhu cầu. Dev mode có thể được dùng để chứng minh policy hoạt động, nhưng việc thử bằng **root token** sẽ che giấu lỗi thiết kế phân quyền.

### 6.2. Token TTL, lease và secret phiên bản là ba chuyện khác nhau

Khi thiết kế môi trường vận hành:

- **Token TTL:** giới hạn thời gian client token được Vault chấp nhận. Một số token được phép renew trong giới hạn, số khác phải đăng nhập lại hoặc được cấp mới; token bị revoke không còn hợp lệ.
- **Dynamic secret lease:** secrets engine có thể cấp credential tạm thời kèm **lease_id** và TTL; cần xử lý renew/revoke khi engine hỗ trợ. Quyền truy cập Vault và thời gian sống credential bên ngoài Vault có thể khác nhau.
- **KV v2 version:** một lần **kv put** tạo phiên bản secret; đọc KV v2 không tự cấp dynamic lease giống database secrets engine.
- **PKI certificate validity:** thời hạn hiệu lực trên chứng chỉ không tương đương với khả năng renew tùy ý bằng **vault lease renew**; thông thường hệ thống phải cấp và triển khai chứng chỉ mới.

Ứng dụng có thể xử lý lỗi đọc KV tạm thời bằng retry có backoff trong các trường hợp phù hợp, nhưng **không được retry vô hạn 403** vì sai policy hoặc credential, và không được coi mọi request như idempotent. Với các thao tác phát hành secret/chứng chỉ hay ghi dữ liệu, cần cân nhắc hậu quả của retry sau timeout.

## 7. Health check, log và audit: quan sát đúng thứ cần quan sát

### 7.1. Health API không chỉ có HTTP 200

~~~bash
curl -i http://127.0.0.1:8200/v1/sys/health
~~~

Trên dev mode đang chạy tốt, active node thường trả **200**. Trong non-dev HA, mã HTTP có thể thể hiện các trạng thái khác:

| Mã mặc định thường gặp | Ý nghĩa |
| --- | --- |
| **200** | Node active, đã init và unsealed |
| **429** | Node standby |
| **472** | DR secondary |
| **473** | Performance standby trong các cấu hình hỗ trợ |
| **501** | Vault chưa initialized |
| **503** | Vault đang sealed |

Mã trả về có thể được điều chỉnh bởi tham số health endpoint, phiên bản hoặc tính năng của Vault. Vì vậy, phải xác định health check này dùng để kiểm tra **node đang sống**, **node sẵn sàng nhận traffic** hay **mức sẵn sàng của cả cụm**. Đừng coi mọi mã khác 200 là đồng nghĩa với máy chủ đã chết; cũng đừng chuyển traffic ứng dụng vào một node sealed chỉ vì TCP port còn mở.

Khi dùng TLS, đổi URL thành HTTPS và cấp CA tin cậy; không vô hiệu hóa xác minh chứng chỉ để thu được health status.

### 7.2. Audit và telemetry là cấu hình bổ sung

Vault không tự bật mọi cơ chế audit chỉ vì chạy non-dev. Người vận hành phải thiết kế và bật audit device phù hợp, giới hạn quyền truy cập vào log và bảo đảm dung lượng/độ tin cậy của đích ghi log. Telemetry, metrics, dashboard và alert cũng cần cấu hình, không xuất hiện đầy đủ chỉ từ việc tạo **vault.hcl**.

Trong ứng dụng Spring Vault, dữ liệu giám sát hữu ích gồm: loại thao tác (KV read, token login/renew, Transit encrypt…), thời gian gọi API, HTTP status, trạng thái retry, correlation/request ID và thời gian còn lại của token/lease **khi có thể lấy an toàn**. Tuyệt đối không ghi token, role secret ID, mật khẩu, private key, plaintext hay nội dung secret vào log.

Những dấu hiệu nên cảnh báo bao gồm Vault sealed, mất quorum, tỉ lệ **403** hoặc **5xx** tăng bất thường, độ trễ tăng, thời hạn chứng chỉ gần hết và lỗi renew/login lặp lại. Với môi trường nhiều node, cảnh báo cần phân biệt lỗi một node và lỗi toàn cụm.

## 8. Bài thực hành so sánh và tiêu chí đánh giá

### 8.1. Bảng quan sát

Hoàn thành hai cột **Kết quả thực tế** và **Giải thích** khi thử trên dev mode và một non-dev lab có cấu hình hợp lệ:

| Thử nghiệm | Dev mode — kỳ vọng | Non-dev — kỳ vọng |
| --- | --- | --- |
| Khởi động server lần đầu | Tự init/unseal | Cần init lần đầu hoặc join vào cụm đã init |
| Kiểm tra **vault status** | Initialized, unsealed | Phụ thuộc init, seal và vai trò node |
| Ghi một KV v2 secret rồi restart | Secret/mount tự tạo bị mất | Secret còn nếu persistent storage không bị xóa/hỏng và cụm được mở khóa đúng |
| Truy cập API không có TLS | Có thể dùng HTTP ở localhost | HTTPS với CA hợp lệ; HTTP không được mở ngoài ý muốn |
| Dùng root token dev | Có token đã biết trong lab | Không có root token dev tự tạo; initial root token được quản trị |
| Dùng token read-only để ghi KV | 403 nếu policy đúng | 403 nếu policy đúng |
| Health check khi sealed | Dev mode thường tự unseal | Phản ánh sealed/uninitialized theo trạng thái |
| Dừng một node trong cụm nhiều node | Không có HA cụm thật | Kết quả phụ thuộc quorum, topology và failover |

**Phép thử về quyền:** Cố ý dùng một token có capability **read** trên **lab-kv/data/app/config** để gọi ghi **kv put**. Thao tác phải bị từ chối cả ở dev và non-dev nếu policy được áp đúng. Điều này cho thấy **phân quyền của Vault là cơ chế thật** ngay cả trong dev mode; điểm khác biệt nằm ở cách bạn tổ chức danh tính và quản trị credential.

**Phép thử về an toàn kết nối:** Với một non-dev lab có TLS hợp lệ, cấu hình Java trust store tin cậy CA sẽ cho phép kết nối. Khi CA hoặc hostname không khớp, kết nối phải thất bại do xác minh TLS. Không dùng cách bỏ xác minh TLS để làm cho test “xanh”.

### 8.2. Tình huống thiết kế

Một đội triển khai ứng dụng Spring Boot gồm ba workload: **API** đọc cấu hình từ KV v2, **worker** chỉ mã hóa qua Transit và **certificate-job** yêu cầu chứng chỉ từ PKI. Đội đang dùng một container Vault dev với root token chung và muốn chuyển lên môi trường dùng thật.

Hãy đề xuất:

1. Cách triển khai Vault non-dev, storage, seal/unseal, TLS, số node và chiến lược HA/backup cần xem xét.
2. Auth method gắn với **danh tính từng workload**, cách phân phối credential và vòng đời token/lease.
3. Ba policy riêng: API chỉ **read** đường dẫn KV v2; worker chỉ được **update** endpoint Transit encrypt cần thiết; certificate-job chỉ được **update** endpoint PKI issue cho role được phép.
4. Kế hoạch giám sát, audit, cảnh báo và kiểm thử khi Vault sealed, thiếu policy, token hết hạn hoặc mất kết nối.
5. Cách đưa các endpoint/CA/credential vào cấu hình Java mà không hardcode bí mật.

Kết quả cần có bảng phân quyền và sơ đồ luồng gọi API; mỗi workload không được dùng root token hay quyền của workload còn lại.

## 9. Checklist quyết định và chuyển môi trường

**Chỉ dùng dev mode** khi bạn cần một Vault có thể xóa/tạo lại, đang học VaultTemplate hoặc kiểm tra nhanh KV, AppRole, Transit, PKI và xử lý lỗi. Chỉ đưa vào phòng lab dữ liệu giả; ghi rõ bước bootstrap vì toàn bộ state dev có thể mất khi restart.

**Chuẩn bị non-dev lab** khi bạn muốn kiểm tra thực tế quy trình init/unseal, quyền trên volume, xác thực TLS, backup/restore và hành vi khi restart. Một non-dev lab có thể chỉ gồm một node để giảm độ phức tạp, nhưng phải ghi rõ nó chưa đáp ứng HA.

**Đánh giá trước khi vận hành thực tế** theo các câu hỏi:

- Storage được bảo vệ và có khả năng khôi phục thực tế hay chưa? Backup đã **thử restore** chưa?
- Mô hình seal (Shamir hoặc auto-unseal) và việc giữ khóa có rõ người chịu trách nhiệm không?
- DNS, TLS, CA/trust store và mạng nội bộ đã được thiết kế cho cả Vault lẫn Spring Vault client chưa?
- Từng workload có auth method và policy tối thiểu; token/lease có chiến lược cấp mới, renew/revoke không?
- HA có đáp ứng mục tiêu vận hành và kiểm thử failover/quorum không?
- Audit, telemetry, cảnh báo, nhật ký sự cố và quy trình nâng cấp đã được kiểm tra không?
- Có kịch bản kiểm thử tích hợp Spring Vault cho lỗi **403**, **404**, **sealed**, timeout, token hết hạn, TLS và các secrets engine được dùng không?

**Ghi nhớ:** Khác biệt cốt lõi không nằm ở việc **VaultTemplate gọi được API hay không**. Dev mode giúp học API nhanh; một Vault vận hành cần bảo đảm dữ liệu, danh tính workload, vòng đời khóa/token/lease, khả năng khôi phục và trạng thái phục vụ của cả hệ thống. Chuyển từ dev sang non-dev vì thế là một thay đổi kiến trúc, bảo mật và quy trình vận hành, chứ không chỉ thay địa chỉ **VAULT_ADDR**.
