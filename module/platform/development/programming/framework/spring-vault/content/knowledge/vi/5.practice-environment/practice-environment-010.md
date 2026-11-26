# Thiết kế bài thực hành có thể tạo lại và thực hiện độc lập

## 1. Vì sao cần một bài thực hành tự chứa?

Trong **Spring Vault**, ứng dụng Java có thể dùng **VaultTemplate** để đọc KV secrets, xác thực bằng danh tính workload, quản lý token và lease, gọi Transit encryption hoặc xin chứng chỉ PKI. Các ví dụ chỉ có giá trị học tập khi người học có thể tạo được môi trường cần thiết mà **không phụ thuộc vào bài trước, dữ liệu còn sót hoặc token của người khác**.

Một bài thực hành thiếu tính độc lập thường gây ra các vấn đề khó nhận biết: trên máy tác giả chạy được vì đã có mount KV v2; trên CI lại trả 404; test “phân quyền” dùng root token nên luôn thành công; chạy lại lệnh seed làm phiên bản KV tăng khiến assertion sai; hoặc lệnh dọn dẹp tháo cả secrets engine dùng chung với bài khác.

Mục tiêu bài này là thiết kế **một đơn vị thực hành có thể tái tạo từ đầu đến cuối**: xác định đầu vào, dựng Vault, khởi tạo fixture, cấp danh tính có quyền tối thiểu, chạy các phép thử, thu thập kết quả và dọn **đúng phạm vi sở hữu**. Ví dụ cơ sở là đọc cấu hình Orders từ KV v2; Transit, PKI, AppRole và TLS được trình bày dưới dạng các module mở rộng độc lập.

Sau khi học, bạn có thể:

1. Viết “hợp đồng thực hành” nêu rõ tiền điều kiện, thao tác, đầu ra và tiêu chí thành công/thất bại.
2. Chọn mức cô lập hợp lý cho Vault local, container test và CI; tránh phụ thuộc tài nguyên tồn tại sẵn.
3. Thiết kế **bootstrap** và **teardown** có kiểm tra trạng thái, không nhận nhầm mọi lệnh là idempotent.
4. Ghi dữ liệu tổng hợp, mount KV v2 và policy một cách có thể kiểm chứng.
5. Sử dụng token hạn chế với **VaultTemplate** và kiểm thử cả trường hợp được phép lẫn bị từ chối.
6. Tổ chức test có thể chạy một mình, theo thứ tự bất kỳ và chạy song song khi cần.
7. Phân biệt phần nền tảng bắt buộc với những bài mở rộng về AppRole, token/lease, Transit, PKI, TLS, giám sát và lỗi tích hợp.

**Giới hạn an toàn:** Các ví dụ dùng Vault dev mode ở loopback và **chỉ có dữ liệu giả**. Không áp dụng root token dev, HTTP không TLS hoặc lệnh dọn mount/volume một cách máy móc vào Vault staging/production. Những đường dẫn và credential mẫu không phải tài sản thực.

## 2. Định nghĩa “tái tạo được” và “độc lập”

### 2.1. Năm thuộc tính của một lab tốt

| Thuộc tính | Ý nghĩa kiểm chứng được | Phản ví dụ |
| --- | --- | --- |
| **Tự chứa** | Tất cả mount, key, policy, role cần cho bài đều được mô tả/cấp trong lab | “Hãy dùng secret đã tạo ở bài hôm qua” |
| **Tái tạo được** | Từ trạng thái sạch, làm theo cùng bước cho cùng cấu trúc tài nguyên và kết quả mong đợi | Phải đoán version KV hoặc tên mount |
| **Cô lập** | Không làm thay đổi dữ liệu của bài khác, người khác hoặc môi trường thật | Test dùng một Vault chung và cùng key |
| **Có thể quan sát** | Mỗi bước có lệnh xác minh và lỗi phân loại được | Chỉ thấy chương trình Java báo “failed” |
| **Có thể dọn** | Biết tài nguyên nào do bài sở hữu và tác động khi thu hồi/xóa | Dùng **secrets disable** chỉ để xóa một key |

**Tái tạo được không có nghĩa mỗi byte đầu ra phải giống nhau.** Token do Vault phát, thời điểm tạo secret, ciphertext Transit và số serial chứng chỉ PKI có thể thay đổi giữa các lần chạy. Một bài tốt kiểm tra **thuộc tính bất biến** (ví dụ policy, logical key, cấu trúc dữ liệu, khả năng giải mã) thay vì so sánh những giá trị ngẫu nhiên hoặc phụ thuộc thời gian.

**Độc lập không có nghĩa mọi thành phần bắt buộc phải ở một container.** Có thể dùng Docker Compose, Testcontainers hoặc một môi trường lab riêng; điều quan trọng là đầu vào/tài nguyên của bài không phụ thuộc vào những tài nguyên ngoài phạm vi đã khai báo.

### 2.2. Hợp đồng đầu vào và đầu ra

Trước khi viết lệnh, mô tả bài dưới dạng hợp đồng:

| Thành phần | Quy ước trong bài mẫu |
| --- | --- |
| Công cụ | Docker Engine/Desktop, Compose v2; JDK và Spring Vault Core nếu chạy Java |
| Hạ tầng | Một Vault dev container riêng, cổng host **127.0.0.1:8200** |
| Mount bắt buộc | **lab010-kv/**, engine KV v2 |
| Key chính | **apps/orders/config** |
| Key đối chứng | **apps/billing/config** |
| Dữ liệu | Chỉ dữ liệu tổng hợp; không gọi dịch vụ thật |
| Chính sách | **lab010-orders-reader** chỉ có quyền đọc Orders |
| Credential ứng dụng | Token ngắn hạn, tách khỏi root token bootstrap |
| Đầu ra thành công | Read bằng CLI và VaultTemplate đúng giá trị mẫu |
| Đầu ra từ chối | Đọc Billing và ghi Orders bằng token reader bị từ chối |
| Phạm vi dọn dẹp | Token và tài nguyên **lab010-*** trong Compose project riêng |

Tên **lab010** là tiền tố mẫu để nhìn ra quyền sở hữu. Người học có thể chọn một tên khác khi sao chép lab, nhưng phải thay tên nhất quán ở **mount, policy, lệnh kiểm tra và code**. Không đặt tiền tố theo tên người dùng hoặc dữ liệu cá nhân nếu không cần thiết.

~~~mermaid
flowchart LR
    A["Môi trường sạch<br/>Docker + JDK"] --> B["Start Vault dev<br/>project lab riêng"]
    B --> C["Bootstrap<br/>KV v2 + fixture + policy"]
    C --> D["Cấp token read-only"]
    D --> E["CLI và VaultTemplate<br/>positive + negative tests"]
    E --> F["Đối chiếu kết quả<br/>và ghi trạng thái"]
    F --> G["Revoke token + teardown<br/>đúng project"]
~~~

### 2.3. Những thứ phải *được ghi rõ*, không suy đoán

Mỗi hướng dẫn nên nói rõ **phiên bản công cụ được thử**, cách gọi lệnh trên Bash/PowerShell khi khác nhau, vị trí chạy lệnh, địa chỉ truy cập theo host/container, tên mount, loại KV (v1 hay v2), credential dành cho bootstrap và credential dành cho ứng dụng, trạng thái sạch hay đã tồn tại dữ liệu, cũng như thao tác nào gây mất dữ liệu.

Chốt phiên bản image hoặc dependency giúp giảm biến động giữa lần chạy, nhưng không đảm bảo tái lập tuyệt đối. Với bài dùng lâu dài, cân nhắc pin **image digest**, phiên bản JDK/Spring/Testcontainers, lưu lockfile nếu có và kiểm thử sau khi cập nhật. Ví dụ ở đây dùng **hashicorp/vault:1.19.0** như một phiên bản lab minh họa, không tuyên bố đó là bản mới nhất.

## 3. Cấu trúc “lab-as-code” tối thiểu

Một bài có thể được lưu cùng tài liệu và file cấu hình không chứa bí mật:

~~~text
spring-vault-lab010/
├── README.md                     # Mục tiêu, preflight, lệnh chạy/dọn
├── compose.yaml                  # Vault container chỉ dùng cho lab
├── policies/
│   └── orders-reader.hcl         # Policy có phạm vi hẹp
├── examples/
│   └── application-local.yml     # Giá trị không bí mật
├── scripts/
│   ├── bootstrap.example         # Thứ tự khởi tạo, có kiểm tra trạng thái
│   ├── verify.example            # Test positive/negative và kết quả
│   └── teardown.example          # Chỉ xóa tài nguyên sở hữu
├── .env.example                  # Chỉ placeholder, không có token thật
└── .gitignore
~~~

Cấu trúc trên là **bản thiết kế nội dung**, không yêu cầu tạo đủ file nếu chỉ thực hành thủ công. Khi hiện thực hóa, các script phải chịu trách nhiệm báo lỗi đúng, có guard target và dùng biến môi trường hợp lệ trên shell tương ứng; không lấy danh sách lệnh rời rạc rồi mặc định một script chạy bao lần cũng an toàn.

**Nên được version control:** tệp Compose, policy HCL, code Java/test, sơ đồ, tài liệu, dữ liệu giả. **Không được commit:** root token, client token, AppRole secret ID, private key, unseal key, file **.env** chứa credential, database dump thật hoặc file log chứa secret.

Ví dụ **.gitignore** cho thư mục lab:

~~~gitignore
.env
.env.*
!.env.example
*.key
*.p12
logs/
secrets/
~~~

Không dựa vào **.gitignore** để bảo vệ một credential đã bị commit trước đó; phải revoke/rotate credential và xử lý bản sao theo quy trình ứng phó sự cố.

## 4. Dựng Vault dev trong Compose project được đặt tên

### 4.1. Cấu hình máy chủ

Tạo **compose.yaml** trong một thư mục lab riêng:

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

Từ thư mục chứa **compose.yaml**, dùng tên project **sv-lab010** cố định:

~~~bash
docker compose -p sv-lab010 up -d
docker compose -p sv-lab010 ps
docker compose -p sv-lab010 logs --tail=60 vault
docker compose -p sv-lab010 exec -T vault vault status
~~~

Kỳ vọng Vault dev đã được initialized, unsealed. Đối với một máy tính đang chạy nhiều bài, **cổng host 8200 vẫn là tài nguyên dùng chung**: chỉ có một service có thể bind tới **127.0.0.1:8200** tại một thời điểm. Muốn chạy nhiều lab song song, cấp cổng host khác hoặc sử dụng cổng động qua Testcontainers, đồng thời cung cấp URL tương ứng cho client.

**Lưu ý:** Tên Compose project giúp tránh đụng tên container/network giữa các lab nhưng **không tự cô lập mọi thứ** nếu bạn vẫn dùng chung volume bên ngoài, cùng cổng host hoặc kết nối tới Vault server khác. Không sử dụng biến **VAULT_ADDR** của một lab khác để điều khiển lệnh này.

### 4.2. Kiểm tra đúng đích và trạng thái trước bootstrap

~~~bash
docker compose -p sv-lab010 exec -T vault vault status
docker compose -p sv-lab010 exec -T vault vault secrets list -detailed
curl -i http://127.0.0.1:8200/v1/sys/health
~~~

**vault status** và health API thuộc hai góc nhìn khác nhau: một cái cho trạng thái instance, cái còn lại trả HTTP health status. Trong dev mode sạch, health thường là **200**. Ở non-dev, **501** có thể báo uninitialized, **503** báo sealed, **429** thường là standby theo mã mặc định. Không tự chạy operator init hoặc unseal trên một cụm không thuộc lab chỉ vì thấy mã khác 200.

Trong container, các lệnh **vault ...** nhận root token dev từ Compose để bootstrap. Đây là đặc quyền quản trị trong môi trường tạm; khi thử quyền workload bắt buộc ghi đè token và không để chương trình Java dùng root token.

## 5. Bootstrap tối thiểu: KV v2, data fixture và policy

### 5.1. Chọn trạng thái đích

Tài nguyên bài mẫu:

~~~text
Vault dev lab010
└── lab010-kv/                          # KV version 2
    └── apps/
        ├── orders/
        │   └── config                 # Được orders-api đọc
        └── billing/
            └── config                 # Bị orders-api từ chối

Policy: lab010-orders-reader
Token: client token TTL 15 phút, mang policy trên
~~~

Fixture Orders gồm các trường:

| Trường | Giá trị giả | Mục đích |
| --- | --- | --- |
| **app_name** | **orders-training** | Kiểm tra đọc đúng key |
| **service_url** | **https://orders.example.invalid/api** | Không gọi dịch vụ thật |
| **timeout_ms** | **1500** | Kiểm tra dữ liệu cấu hình |
| **env_label** | **lab010** | Phát hiện đọc nhầm lab |

Fixture Billing chứa **app_name=billing-training**, **api_token=fake-token-unused** và không được cấp quyền cho Orders token. Đừng dùng bản sao secret production hay token còn hiệu lực để bài “giống thực tế”.

### 5.2. Kiểm tra mount và chỉ enable khi chưa có

Trước tiên:

~~~bash
docker compose -p sv-lab010 exec -T vault vault secrets list -detailed
~~~

Nếu **lab010-kv/** chưa tồn tại trong lab mới:

~~~bash
docker compose -p sv-lab010 exec -T vault vault secrets enable -path=lab010-kv kv-v2
docker compose -p sv-lab010 exec -T vault vault secrets list -detailed
~~~

Kỳ vọng loại engine là **kv**, tùy chọn version **2**. Nếu đã có mount trùng path nhưng type/version khác, **dừng bootstrap** và báo cấu hình sai; không tự disable hoặc ghi đè mount để “sửa”.

### 5.3. Seed hai secret giả

~~~bash
docker compose -p sv-lab010 exec -T vault vault kv put -mount=lab010-kv apps/orders/config app_name=orders-training service_url=https://orders.example.invalid/api timeout_ms=1500 env_label=lab010

docker compose -p sv-lab010 exec -T vault vault kv put -mount=lab010-kv apps/billing/config app_name=billing-training api_token=fake-token-unused env_label=lab010

docker compose -p sv-lab010 exec -T vault vault kv get -mount=lab010-kv apps/orders/config
docker compose -p sv-lab010 exec -T vault vault kv get -mount=lab010-kv apps/billing/config
~~~

Các lệnh trên cung cấp đầy đủ dữ liệu cho **một lần bootstrap trên Vault sạch**. Với KV v2, gọi lại **kv put** trên key cũ sẽ tạo version mới. Do đó, *script seed không tự idempotent* chỉ vì nó ghi cùng key và cùng giá trị.

Để cho phép chạy lại theo kiểu **reconcile**, cần đọc trạng thái trước:

1. Nếu key chưa có, tạo fixture lần đầu.
2. Nếu key đã tồn tại và **app_name**, **env_label** cùng schema đúng, giữ nguyên; không ghi thêm version.
3. Nếu key tồn tại nhưng dữ liệu khác, **fail với thông báo rõ ràng** hoặc yêu cầu chế độ reset của lab đã xác minh ownership; không tự xóa dữ liệu chỉ vì sai kỳ vọng.
4. Nếu muốn test versioning, dùng một bài tập riêng có kỳ vọng version theo trạng thái ban đầu.

**Đường dẫn KV v2:** CLI dùng **-mount=lab010-kv** và logical key **apps/orders/config**; HTTP data API tương ứng **/v1/lab010-kv/data/apps/orders/config**. Thao tác metadata/list lại dùng **lab010-kv/metadata/...**. Policy phải viết theo **API path**, không phải theo chuỗi URL có tiền tố **/v1/**.

### 5.4. Policy chỉ đọc để có phép thử âm

Tạo **policies/orders-reader.hcl**:

~~~hcl
path "lab010-kv/data/apps/orders/config" {
  capabilities = ["read"]
}
~~~

Nạp policy vào container:

~~~bash
docker compose -p sv-lab010 cp policies/orders-reader.hcl vault:/tmp/orders-reader.hcl
docker compose -p sv-lab010 exec -T vault vault policy write lab010-orders-reader /tmp/orders-reader.hcl
docker compose -p sv-lab010 exec -T vault vault policy read lab010-orders-reader
~~~

Không có quyền đọc Billing hoặc ghi Orders. Cũng không cấp **list** trên metadata vì ứng dụng đang đọc một logical key đã biết. Nếu bài cần list, cấp capability **list** trên path **lab010-kv/metadata/apps/orders** thích hợp, chứ không cho phép toàn bộ mount chỉ để một phép đọc hoạt động.

### 5.5. Cấp token ngắn hạn, tách người quản trị khỏi ứng dụng

~~~bash
docker compose -p sv-lab010 exec -T vault vault token create -policy=lab010-orders-reader -ttl=15m -field=token
~~~

Lệnh in một token dành cho workload thử nghiệm. Trên Bash/zsh, đưa token vào biến của phiên terminal:

~~~bash
export LAB010_APP_TOKEN="<token-reader-vua-tao>"
~~~

Trên PowerShell:

~~~powershell
$env:LAB010_APP_TOKEN = "<token-reader-vua-tao>"
~~~

Không đưa client token vào **compose.yaml**, mã Java, file policy, chat/issue tracker, log CI hoặc source control. Token được tạo bằng quyền quản trị chỉ để **bootstrap**; bài test của ứng dụng phải dùng đúng token hạn chế. Khi token hết TTL, tạo token mới hoặc sử dụng auth method có cơ chế login/renew được thiết kế theo workload.

## 6. Xác minh kết quả: phải có test được phép và bị từ chối

### 6.1. Kiểm tra bằng CLI với đúng token ứng dụng

Trong container Vault, Compose đã đặt biến **VAULT_TOKEN=dev-root-only**. Nếu không thay giá trị đó, phép thử phân quyền có thể trả kết quả sai. Trước khi chạy, bảo đảm **LAB010_APP_TOKEN** đã được gán token vừa phát hành và không phải root token.

Lệnh dành cho Bash/zsh:

~~~bash
# Trường hợp được phép: đọc Orders
docker compose -p sv-lab010 exec -T -e "VAULT_TOKEN=$LAB010_APP_TOKEN" vault vault kv get -mount=lab010-kv apps/orders/config

# Trường hợp phải bị từ chối: đọc Billing
docker compose -p sv-lab010 exec -T -e "VAULT_TOKEN=$LAB010_APP_TOKEN" vault vault kv get -mount=lab010-kv apps/billing/config

# Trường hợp phải bị từ chối: ghi Orders
docker compose -p sv-lab010 exec -T -e "VAULT_TOKEN=$LAB010_APP_TOKEN" vault vault kv put -mount=lab010-kv apps/orders/config app_name=should-be-denied
~~~

Nếu chạy bằng PowerShell, sử dụng cú pháp **-e "VAULT_TOKEN=$env:LAB010_APP_TOKEN"**:

~~~powershell
docker compose -p sv-lab010 exec -T -e "VAULT_TOKEN=$env:LAB010_APP_TOKEN" vault vault kv get -mount=lab010-kv apps/orders/config
~~~

| Phép thử | Kết quả mong đợi | Ý nghĩa |
| --- | --- | --- |
| Read Orders | **Thành công**, trường **app_name=orders-training** | Đúng data path, token, mount |
| Read Billing | **403 permission denied** | Token không có quyền với key khác |
| Put Orders | **403 permission denied** | Token không có **create/update** |
| Xem KV metadata bằng token reader | Có thể bị **403** | Policy không cấp metadata read/list |
| Đọc lại Orders bằng root token bootstrap | Không có version bị ghi sai | Lệnh put bị từ chối không được tạo version |

Sau phép thử âm, kiểm tra version của Orders bằng root token **chỉ trong container lab**:

~~~bash
docker compose -p sv-lab010 exec -T vault vault kv metadata get -mount=lab010-kv apps/orders/config
~~~

Trong một lần bootstrap sạch và chưa chạy thao tác ghi nào khác, version hiện tại dự kiến là **1**. Không viết assertion cố định version 1 khi test của bạn cho phép reuse một Vault đã có dữ liệu; khi đó phải lấy mốc version trước và sau phép thử ghi bị từ chối.

**Một request bị 403 chưa tự nói rõ nguyên nhân.** Token có thể hết hạn, bị revoke, thuộc policy khác, hoặc policy thiếu **data/** của KV v2. Phải kiểm tra credential đúng và endpoint được dùng trước khi quyết định nới quyền.

### 6.2. Trả lời chính xác “bài có hoàn thành không?”

Không chỉ dựa vào việc **Vault health trả 200** hoặc Java không ném exception. Đầu ra cần thỏa mãn đồng thời:

1. **Vault đúng đích:** endpoint thuộc Compose project lab được kiểm tra.
2. **Fixture đúng:** hai logical key chứa dữ liệu giả với schema đã định.
3. **Phân quyền đúng:** read Orders thành công, read Billing và put Orders bị từ chối.
4. **Không có tác dụng phụ lạ:** phép thử read-only không tạo KV version, token quyền rộng hoặc certificate ngoài dự kiến.
5. **Có thể lặp lại:** dọn lab rồi chạy lần nữa vẫn có cấu trúc và kết quả trên.

Đầu ra token, timestamps và request IDs có thể khác nhau sau mỗi lần chạy. So sánh các giá trị đó byte-for-byte sẽ làm test mong manh mà không chứng minh được chức năng Spring Vault.

## 7. Chạy cùng fixture qua VaultTemplate

### 7.1. Ví dụ Java tối thiểu

Đặt dependency **org.springframework.vault:spring-vault-core** theo phiên bản phù hợp với Spring Framework/Spring Boot của dự án. Ví dụ dưới đây không yêu cầu Spring Boot context; nó chỉ kiểm chứng **VaultTemplate** đọc đúng KV v2 bằng token quyền tối thiểu.

~~~java
import java.net.URI;
import java.util.Map;

import org.springframework.vault.authentication.TokenAuthentication;
import org.springframework.vault.client.VaultEndpoint;
import org.springframework.vault.core.VaultTemplate;
import org.springframework.vault.support.Versioned;

public final class Lab010VaultCheck {

    public static void main(String[] args) {
        String address = System.getenv("VAULT_ADDR");
        String token = System.getenv("LAB010_APP_TOKEN");

        if (address == null || address.isBlank()
                || token == null || token.isBlank()) {
            throw new IllegalStateException(
                    "VAULT_ADDR and LAB010_APP_TOKEN are required");
        }

        VaultEndpoint endpoint = VaultEndpoint.from(URI.create(address));
        VaultTemplate template = new VaultTemplate(
                endpoint, new TokenAuthentication(token));

        Versioned<Map<String, Object>> response = template
                .opsForVersionedKeyValue("lab010-kv")
                .get("apps/orders/config");

        if (response == null || response.getData() == null) {
            throw new IllegalStateException("Orders fixture is missing");
        }

        Map<String, Object> values = response.getData();
        if (!"orders-training".equals(values.get("app_name"))
                || !"lab010".equals(values.get("env_label"))) {
            throw new IllegalStateException(
                    "Unexpected fixture or wrong Vault environment");
        }

        // Không log raw Vault response, secret, client token.
        System.out.println("Lab010 KV read: PASS");
    }
}
~~~

Khi chạy Java trên máy host, cung cấp:

~~~bash
# Bash / zsh
export VAULT_ADDR="http://127.0.0.1:8200"
# LAB010_APP_TOKEN đã được cấp ở bước bootstrap.
~~~

~~~powershell
# PowerShell
$env:VAULT_ADDR = "http://127.0.0.1:8200"
# LAB010_APP_TOKEN đã được cấp ở bước bootstrap.
~~~

Mã đọc **lab010-kv/data/apps/orders/config**, vì API KV v2 thêm **data/** phía sau mount. Với **opsForVersionedKeyValue("lab010-kv")**, phần key chỉ là **apps/orders/config**; không tự thêm **data/** vào key.

Nếu thay key trong Java bằng **apps/billing/config** nhưng giữ token reader, thao tác phải báo lỗi quyền. Trường hợp key Orders không tồn tại khi token có quyền, SDK có thể trả **null** hoặc một lỗi liên quan endpoint tùy cách gọi; cả hai phải được xử lý rõ ràng, không tự chuyển sang mount khác hoặc dùng root token.

### 7.2. Tách thông tin môi trường khỏi logic nghiệp vụ

Đoạn Java trên có mount/key cố định để một người mới có thể chạy độc lập. Với ứng dụng thật, nên đưa chúng ra ngoài mã nguồn:

~~~yaml
# application-local.yml của ứng dụng lab
training:
  vault:
    uri: ${LAB_VAULT_URI:http://127.0.0.1:8200}
    mount: ${LAB_VAULT_MOUNT:lab010-kv}
    orders-key: apps/orders/config
~~~

Các key **training.vault.*** chỉ là thuộc tính **tùy chỉnh**: ứng dụng phải bind chúng và chuyển sang **VaultEndpoint/VaultTemplate**; khai báo YAML không tự làm Spring Vault Core đọc các giá trị đó. Với Spring Cloud Vault, cơ chế import property từ Vault là tích hợp riêng và cần cấu hình đúng phiên bản. Không giả định cả hai cách nạp secret là giống nhau.

Ở môi trường triển khai, không dùng URL HTTP loopback hay credential dev. Để bảo đảm bài độc lập, mỗi profile cần khai báo rõ URI, mount, namespace (nếu có), auth method và CA trust; không fallback từ staging/production về lab010.

**TokenAuthentication** trong ví dụ là lựa chọn smoke test. Token có TTL, có thể hết hạn hoặc bị revoke. Ứng dụng chạy dài hạn cần xác thực theo workload và thành phần quản lý phiên thích hợp (**ClientAuthentication**, **SessionManager**) để xử lý login/renew/re-login có kiểm soát.

### 7.3. Đừng biến preflight thành thao tác ghi

Một phép kiểm tra readiness chỉ cần GET một secret giả hoặc một cấu hình bắt buộc. Không nên thường xuyên chạy **kv put**, tạo Transit key, cấp PKI certificate hay tạo dynamic credential trong readiness; các thao tác đó có tác dụng phụ và có thể sinh version/lease/certificate mới mỗi lần health checker chạy.

Nếu ứng dụng thực tế không có quyền hoặc không cần đọc một key chuyên dành cho preflight, thiết kế phép kiểm tra theo chính nhu cầu nghiệp vụ. Không cấp thêm quyền ghi chỉ vì một đoạn smoke test được viết thiếu nguyên tắc quyền tối thiểu.

## 8. Tái tạo lại từ đầu và chạy lại trên trạng thái cũ

### 8.1. Hai chế độ khác nhau

| Chế độ | Điều kiện bắt đầu | Được phép làm | Không nên làm |
| --- | --- | --- | --- |
| **Fresh run** | Vault dev riêng vừa được tạo, chưa có fixture | Enable mount, seed, policy, tạo token | Dùng lại token hoặc dữ liệu từ lần trước |
| **Rerun/verify** | Cùng Vault còn đang chạy, fixture đã có | Kiểm tra mount/type, đọc fixture, thử quyền | Mặc định chạy lại mọi **kv put** và tạo CA/Transit key |
| **Reset-owned-lab** | Đã chứng minh sở hữu toàn bộ Compose project | Dừng/khởi tạo lại project lab và seed mới | Xóa volume/mount của Vault chia sẻ |

Với bài này, **dev mode lưu state trong bộ nhớ**. Sau khi dừng container bằng **docker compose -p sv-lab010 down** rồi khởi động lại, fixture/tokens cần được seed lại. Nếu chỉ chạy **docker compose -p sv-lab010 up -d** khi container cũ đang hoạt động, state cũ có thể vẫn còn; không gọi đó là fresh run.

Nếu một test buộc phải bắt đầu với version 1, cách đơn giản nhất là dùng **Vault tạm mới** cho test đó. Nếu phải làm việc trên một Vault đã tồn tại, lấy metadata version trước test và viết assertion theo thay đổi kỳ vọng thay vì giả định version hiện tại.

### 8.2. Idempotency theo loại tài nguyên

| Thao tác bootstrap | Tác động khi chạy lại | Cách xử lý có kiểm soát |
| --- | --- | --- |
| **secrets enable -path=...** | Báo lỗi nếu mount đã tồn tại | Kiểm tra danh sách mount/type trước |
| **kv put** | Tạo KV v2 version mới | Đọc trước và chỉ ghi khi cần; báo conflict nếu khác |
| **policy write** | Tạo/cập nhật policy theo tên | Kiểm tra policy tương thích và owner |
| **token create** | Phát một token mới | Chỉ cấp khi cần; giới hạn TTL và số token tồn tại |
| **auth enable** | Báo lỗi nếu auth path trùng | Kiểm tra **auth list** trước |
| **Transit keys create** | Key có state riêng, lệnh tạo có thể không phù hợp chạy lại | Kiểm tra metadata key và rotation policy |
| **PKI issue** | Phát chứng chỉ mới mỗi lần gọi | Chỉ issue khi bài cần, lưu kết quả một cách an toàn |
| **operator init** của non-dev | Không được dùng để “làm mới” Vault đã init | Chỉ thao tác trên cluster mới với quy trình quản trị |

**Lệnh chạy thành công không chứng minh được tính idempotent.** Cần xác định trước/post-state: số version không tăng khi chỉ verify, số token/certificate không phát sinh ngoài chủ đích, policy không bị sửa ngoài phạm vi và không có yêu cầu cấp quyền rộng.

### 8.3. Các nguồn gây lệch kết quả

Những yếu tố hay làm test không ổn định gồm **thời gian hệ thống**, TTL token/lease, nonce, khóa/ciphertext, port host, thứ tự test, khả năng tải image, certificate sắp hết hạn và tài nguyên được chia sẻ giữa suite. Cách kiểm tra hợp lý:

- Với TTL: xác minh thời hạn **nằm trong giới hạn phù hợp**, không so với một con số chính xác từng giây.
- Với Transit: kiểm tra **decrypt(ciphertext) trả plaintext ban đầu** (khi role cho phép), không so sánh ciphertext với chuỗi cố định.
- Với PKI: kiểm tra **SAN, issuer, validity, role constraint**; không giả định serial number như lần chạy trước.
- Với port: dùng địa chỉ do container/test runner cung cấp, không hardcode cổng của máy tác giả.
- Với dữ liệu KV: kiểm tra schema và các giá trị giả do bài seed, không phụ thuộc version tăng do test khác.

**Tái tạo được kết quả về hành vi quan trọng hơn tái tạo được mọi giá trị ngẫu nhiên.**

## 9. Tổ chức test tích hợp độc lập trong CI

### 9.1. Mỗi test phải biết ai sở hữu fixture

**Unit test** của logic xử lý Orders không nhất thiết cần Vault thật: có thể mock một adapter đọc cấu hình và kiểm tra business logic. **Integration test Spring Vault** cần Vault API và policy thật để kiểm chứng đúng hành vi. Tránh biến mọi unit test thành test có phụ thuộc mạng/Vault, vì tốc độ và độ tin cậy của bộ test sẽ giảm.

Ba cấp cô lập thường gặp:

| Mức cô lập | Ưu điểm | Rủi ro cần quản lý |
| --- | --- | --- |
| Một Vault test container **cho mỗi test case** | State sạch nhất, dễ chạy song song | Chi phí khởi tạo container lớn hơn |
| Một Vault test container **cho mỗi test class/suite** | Giảm thời gian startup | Phải reset fixture hoặc dùng key khác nhau giữa các test |
| Vault test dùng chung cho nhiều job | Tiết kiệm hạ tầng | Dễ đụng mount/key/token, yêu cầu namespace/định danh và teardown chặt chẽ |

Với bài học, ưu tiên **mỗi test suite sở hữu một container**. Nếu cần chạy song song, các suite không cùng ghi lên một prefix hoặc dùng chung token bootstrap. Khi không có lý do rõ ràng, đừng kết nối test tới Vault staging/production.

### 9.2. Trình tự Testcontainers chuẩn

~~~mermaid
sequenceDiagram
    participant T as JUnit/Test runner
    participant V as VaultContainer
    participant B as Bootstrap fixture
    participant J as VaultTemplate

    T->>V: Start container (port động)
    V-->>T: Host/port + ready
    T->>B: Enable ci-kv, seed và policy
    B->>V: Ghi dữ liệu giả, cấp test token
    V-->>B: Client token giới hạn
    B-->>T: Endpoint + app token
    T->>J: Tạo VaultTemplate theo test identity
    J->>V: GET /v1/ci-kv/data/apps/orders/config
    V-->>J: Fixture Orders
    T->>J: Thử đọc Billing / ghi Orders
    V-->>J: 403 permission denied
    T->>V: Revoke token và stop container
~~~

**Thứ tự quan trọng:** bootstrap mount/data/policy/token **trước khi Spring tạo bean có thể gọi Vault**, không chỉ trước một test method bất kỳ. Nếu ứng dụng có cơ chế import secret khi tạo ApplicationContext, một **@BeforeAll** của JUnit có thể không đủ sớm. Khi đó cần lifecycle hook khởi động container/fixture trước khi nạp context, hoặc test configuration cung cấp sẵn một client được bootstrap đúng.

### 9.3. Khung Java Testcontainers

Ví dụ mang tính cấu trúc với **JUnit Jupiter** và module **Testcontainers Vault**:

~~~java
import org.junit.jupiter.api.Test;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.vault.VaultContainer;

@Testcontainers
class IsolatedVaultLabTest {

    @Container
    static final VaultContainer<?> vault =
            new VaultContainer<>("hashicorp/vault:1.19.0")
                    .withVaultToken("ci-bootstrap-only");

    @Test
    void readsFixtureWithRestrictedToken() {
        String address = "http://" + vault.getHost()
                + ":" + vault.getMappedPort(8200);

        // Bước fixture: gọi Vault CLI/API để tạo ci-kv,
        // ghi Orders/Billing và nạp policy reader.
        // Bước identity: tạo app token chỉ đọc từ bootstrap token.
        // Tạo VaultTemplate với address + app token, KHÔNG
        // dùng ci-bootstrap-only làm credential nghiệp vụ.
        // Assert: Orders đọc thành công; Billing/put bị 403.
    }
}
~~~

Khung trên **chưa phải một test hoàn chỉnh chạy được ngay**: cần dependencies Testcontainers/JUnit, bước khởi tạo tài nguyên, lấy token và assertions. Nó chỉ minh họa cách lấy **host/port động** từ VaultContainer. Mỗi bản triển khai phải cụ thể hóa việc gọi lệnh bootstrap và truyền token **trước khi** tạo VaultTemplate.

Nếu dùng **@SpringBootTest** với **@DynamicPropertySource**, hãy bind URI test container vào property mà ứng dụng thật sự đọc. **@DynamicPropertySource không tự cấp token hoặc tạo mount**. Một cấu hình test dành riêng có thể cung cấp **ClientAuthentication** của token test; không để Spring test chọn nhầm bean production hoặc dùng biến môi trường từ máy lập trình viên.

### 9.4. Tính độc lập theo thứ tự test

Một bộ test tốt phải tiếp tục đúng khi:

- Chạy riêng **chỉ một test** bằng IDE.
- Chạy toàn bộ suite theo thứ tự khác.
- Lặp lại suite sau khi một test trước đó thất bại.
- Chạy song song các suite với cổng được phân bổ động.
- Chạy trên runner CI mới, không có Docker volume hoặc token thủ công từ trước.

**Anti-pattern:** Test A tạo key, Test B cập nhật nó, Test C đọc version 2 và chỉ chạy đúng khi A → B → C. **Thiết kế lại:** mỗi test tự tạo state cần thiết trong fixture riêng hoặc test suite khai báo rõ một kịch bản tuần tự duy nhất, không giả vờ các test case đó độc lập.

Nếu một test kiểm tra rollback KV v2, nó nên tạo chính key/versions đó trong vùng namespace riêng. Không lấy version hiện tại của key được dùng chung rồi giả định đây là version 2.

### 9.5. Test dữ liệu, quyền và lỗi hệ thống

| Nhóm test | Input do suite sở hữu | Assertion hữu ích |
| --- | --- | --- |
| **KV read** | Mount **ci-kv/** + Orders key | Đọc đúng schema và nhãn test |
| **KV write denied** | Token chỉ read | Request bị từ chối, không có version mới |
| **Isolation** | Billing key + Orders token | Đọc Billing bị từ chối |
| **Missing key** | Key không seed | Client xử lý null/404 rõ ràng |
| **Token lifecycle** | Token TTL ngắn hoặc bị revoke | Client xử lý phiên hết hạn theo thiết kế |
| **Connectivity** | Stop riêng container của suite | Connection error/timeout được phân loại |
| **TLS** | Vault HTTPS test có CA/SAN riêng | Đúng CA thành công; sai CA/hostname bị chặn |
| **Transit** | Transit test key và policy riêng | Encrypt đúng, decrypt chỉ khi được cấp quyền |
| **PKI** | CA/role/certificate test độc lập | SAN/TTL/role giới hạn đúng |

Khi một test âm dự kiến 403, **bắt đúng lỗi liên quan quyền** thay vì coi mọi exception đều là thành công. Ví dụ connection refused không chứng minh policy đã từ chối thao tác ghi.

## 10. Mở rộng bài mà không phá tính độc lập

Core lab KV v2 đã đủ để thực hành **VaultTemplate + policy**. Các module sau có thể được bật theo nhu cầu; mỗi module có fixture, quyền, kết quả và teardown riêng. Không biến chúng thành **tiền điều kiện ngầm** cho bài core.

### 10.1. Xác thực bằng AppRole thay token thủ công

Thêm auth mount **lab010-approle/** trong Vault test nếu chưa tồn tại:

~~~bash
docker compose -p sv-lab010 exec -T vault vault auth list
docker compose -p sv-lab010 exec -T vault vault auth enable -path=lab010-approle approle

docker compose -p sv-lab010 exec -T vault vault write auth/lab010-approle/role/orders-api bind_secret_id=true token_policies=lab010-orders-reader token_ttl=15m token_max_ttl=1h secret_id_ttl=30m secret_id_num_uses=1
~~~

Chỉ chạy lệnh **auth enable** khi mount đó chưa tồn tại. Người quản trị đọc **role_id** và cấp **secret_id** mới cho lần đăng nhập. Workload dùng cặp này gọi **auth/lab010-approle/login**, nhận client token mang policy **lab010-orders-reader**, sau đó đọc cùng key Orders như bài core.

Các điều kiện cần xác nhận:

- **role_id** định danh role, còn **secret_id** là credential nhạy cảm; không commit.
- Nếu **secret_id_num_uses=1**, dùng lại secret ID cho lần login tiếp theo phải thất bại; cần cấp secret ID mới.
- Client token đã cấp có TTL/renew/revoke riêng; secret ID hết lượt dùng không đồng nghĩa token vừa phát lập tức hết hạn.
- Không tự bật auth mount hoặc tạo role bằng credential của ứng dụng. Đó là công việc bootstrap/quản trị.

Khi chạy trên Kubernetes, cloud hoặc một môi trường có workload identity, có thể thay AppRole bằng auth method tương ứng mà **không cần đổi logic đọc KV**. Chỉ thay adapter xác thực và quy trình cấp danh tính; policy vẫn giới hạn endpoint được gọi.

### 10.2. Transit module: mã hóa với khóa riêng của bài

Nếu chưa có **lab010-transit/**, người quản trị lab tạo mount và khóa:

~~~bash
docker compose -p sv-lab010 exec -T vault vault secrets enable -path=lab010-transit transit
docker compose -p sv-lab010 exec -T vault vault write -f lab010-transit/keys/orders-lab
~~~

Với một Vault sạch, khóa được tạo tại mount riêng. Không chạy lại lệnh enable nếu mount đã tồn tại; khi rerun cần kiểm tra metadata của khóa và chủ đích trước khi thay đổi.

Thử mã hóa chuỗi tổng hợp **ping-test**; plaintext phải được Base64-encode (**cGluZy10ZXN0**):

~~~bash
docker compose -p sv-lab010 exec -T vault vault write -field=ciphertext lab010-transit/encrypt/orders-lab plaintext=cGluZy10ZXN0
~~~

Kết quả là ciphertext dạng **vault:v1:...**. Với policy decrypt phù hợp, gửi ciphertext thực tế đó tới **lab010-transit/decrypt/orders-lab**, kiểm tra Base64 plaintext trả về giải mã thành **ping-test**. Không hardcode ciphertext từ một lần chạy trước: Transit có thể tạo ciphertext khác giữa các lần mã hóa.

Policy workload **chỉ cần mã hóa** nên có **update** trên **lab010-transit/encrypt/orders-lab**, **không** tự cấp **decrypt**, quyền chỉnh khóa hoặc quyền đọc dữ liệu KV. Khi dọn, không xóa Transit key nếu còn ciphertext của bài khác cần giải mã.

### 10.3. PKI module: phát hành chứng chỉ có hạn và ràng buộc

Chỉ mở rộng trong Vault test **do bài sở hữu**, có thể bật PKI engine:

~~~bash
docker compose -p sv-lab010 exec -T vault vault secrets enable -path=lab010-pki pki
docker compose -p sv-lab010 exec -T vault vault secrets tune -max-lease-ttl=8760h lab010-pki
docker compose -p sv-lab010 exec -T vault vault write -field=certificate lab010-pki/root/generate/internal common_name=lab010.internal ttl=8760h
docker compose -p sv-lab010 exec -T vault vault write lab010-pki/roles/orders-server allowed_domains=lab010.internal allow_subdomains=true max_ttl=24h
~~~

Phát hành certificate thử cho **orders.lab010.internal**:

~~~bash
docker compose -p sv-lab010 exec -T vault vault write -field=certificate lab010-pki/issue/orders-server common_name=orders.lab010.internal ttl=1h
~~~

Sử dụng **-field=certificate** để không in private key ra terminal. Không xem lệnh issue là “read”: mỗi lần issue có thể tạo thêm chứng chỉ mới. Test nên kiểm tra tên, thời hạn và ràng buộc role, không cố định serial number. Quyền gọi **lab010-pki/issue/orders-server** được kiểm soát bởi Vault policy, còn danh sách tên miền/TTL được giới hạn bởi **PKI role**.

**PKI của ứng dụng khác với certificate HTTPS của chính Vault listener.** Khi muốn kiểm thử TLS, cần chuẩn bị listener certificate/CA cho Vault server và truststore JVM trước khi client kết nối; không mặc định có thể dùng ngay một certificate do Vault PKI cấp để khởi động chính Vault trong mọi kiến trúc.

### 10.4. Token và dynamic lease: cần đúng engine

KV v2 lưu secret có version, nhưng **đọc secret KV tĩnh không cấp dynamic lease**. Nếu mục tiêu học lease renewal/revocation, thêm một engine có phát hành credential động (ví dụ database secrets engine và **database giả/test container** do suite sở hữu). Cần dựng đủ backend, role, TTL và cơ chế dọn tài khoản động; đừng tự bịa lease ID hoặc dùng version KV thay cho lease.

Một bài về vòng đời nên phân biệt:

| Thành phần | Điều cần kiểm tra | Phạm vi dọn |
| --- | --- | --- |
| **AppRole secret ID** | TTL/lượt dùng, login một lần hay nhiều lần | Revoke secret ID do bài tạo |
| **Client token** | TTL, renewable, revoke và login lại | Thu hồi token ứng dụng |
| **Dynamic lease** | lease_id, TTL, renew/revoke khi engine hỗ trợ | Revoke đúng lease do bài sinh |
| **KV v2 version** | Version mới, soft delete/undelete/destroy | Đúng key/version, không phải revoke lease |
| **PKI certificate** | Validity, role, phát hành/cấp lại | Theo quy trình thu hồi certificate riêng |

Không giả định token renew thành công vô hạn. **max_ttl**, auth role, parent token và chính sách Vault có thể giới hạn khả năng gia hạn. Trong CI, dùng TTL ngắn nhưng đủ cho suite, và không in raw token/lease credentials vào log.

### 10.5. TLS module: kiểm thử riêng, không vô hiệu hóa xác minh

Core lab local dùng HTTP ở loopback. Một module HTTPS riêng phải tạo CA lab, server certificate có SAN phù hợp địa chỉ gọi, cấu hình Vault listener TLS, rồi đưa CA vào JVM truststore hoặc SSLContext của Spring Vault HTTP client.

Kiểm thử ít nhất ba tình huống:

1. **Đúng CA và SAN:** handshake thành công; sau đó policy quyết định quyền nghiệp vụ.
2. **Sai CA:** client từ chối certificate trước khi vào lớp Vault token.
3. **Sai hostname/SAN:** client từ chối, kể cả chứng thư có thể được ký bởi CA tin cậy.

Không dùng **curl -k**, trust-all SSLContext hoặc tắt hostname verification để làm test chạy qua. **VAULT_CACERT** dành cho Vault CLI không tự động cấu hình truststore JVM.

## 11. Teardown có kiểm kê và giới hạn phạm vi

### 11.1. Tách vòng đời của từng loại tài nguyên

Không có một lệnh xóa nào phù hợp với mọi thứ trong Vault. Cần liệt kê trước những tài nguyên mà **chính bài** tạo:

| Tài nguyên | Bài mẫu sở hữu? | Teardown mong đợi |
| --- | --- | --- |
| Compose project **sv-lab010** | Có, nếu tạo riêng cho bài | Dừng/xóa container/network của project |
| Mount **lab010-kv/** | Có trong Vault dev riêng | Mất khi dev container kết thúc; không xóa mount dùng chung |
| Key Orders/Billing | Có | Kiểm tra/xóa riêng nếu phải giữ Vault chạy tiếp |
| Policy **lab010-orders-reader** | Có | Xem xét xóa sau khi không còn token/role phụ thuộc |
| Token **LAB010_APP_TOKEN** | Có | Revoke token hoặc cho hết TTL, không ghi lại giá trị |
| Auth mount AppRole mở rộng | Chỉ nếu module AppRole tạo và sở hữu | Dọn role/secret ID, chỉ disable mount khi hoàn toàn riêng |
| Transit key mở rộng | Chỉ nếu bài tạo | Không xóa khi còn ciphertext cần giải mã |
| PKI CA/role/certificate mở rộng | Chỉ nếu bài tạo | Theo lifecycle PKI, không xóa CA dùng chung |
| File cấu hình, log, token ở host | Do người học quản lý | Kiểm tra riêng, Compose down không xóa |
| Vault production hoặc staging | **Không** | Không được tác động |

Nếu **toàn bộ Vault dev** thuộc Compose project của bài và không có tài nguyên người khác, teardown đơn giản nhất là dừng project:

~~~bash
docker compose -p sv-lab010 down
~~~

Với Compose dev mẫu ở mục 4, không có persistent volume của Vault; state trong bộ nhớ biến mất khi server kết thúc. Lệnh **down** không tự xóa file **compose.yaml**, policy, mã Java, dữ liệu đã in trong log, clipboard hoặc biến môi trường trên host.

**Không thêm tùy chọn -v theo thói quen.** Nếu sau này đổi cấu hình sang Vault non-dev có named volume, **docker compose down -v** có thể xóa volume và mất dữ liệu bền vững; đây không còn là thao tác tương đương với stop dev server. Với môi trường chia sẻ, không được tự xóa volume/mount khi chỉ muốn kết thúc một bài.

### 11.2. Thu hồi token trước khi dừng Vault

Khi token reader đã được kiểm tra đúng là token của bài và không phải root token, có thể cho token **tự thu hồi**:

~~~bash
# Bash / zsh: chỉ chạy sau khi kiểm tra biến có token app hợp lệ.
docker compose -p sv-lab010 exec -T -e "VAULT_TOKEN=$LAB010_APP_TOKEN" vault vault token lookup
docker compose -p sv-lab010 exec -T -e "VAULT_TOKEN=$LAB010_APP_TOKEN" vault vault token revoke -self
~~~

Với PowerShell, dùng **-e "VAULT_TOKEN=$env:LAB010_APP_TOKEN"**. Không chạy các lệnh trên khi biến rỗng hoặc khi chưa xác nhận token thuộc bài; trong container có root token mặc định, nên thao tác cần được kiểm tra kỹ. Nếu token đã hết hạn, revoke có thể thất bại vì không còn hợp lệ; điều đó không yêu cầu cấp thêm quyền.

Sau khi xử lý token, xóa biến khỏi phiên shell đang làm việc:

~~~bash
# Bash / zsh
unset LAB010_APP_TOKEN
~~~

~~~powershell
# PowerShell
Remove-Item Env:LAB010_APP_TOKEN
~~~

Việc xóa biến khỏi shell hiện tại **không** xóa token đã lọt vào history, log hoặc process khác. Với credential thật bị lộ, phải revoke/rotate theo quy trình ứng phó sự cố.

### 11.3. Nếu phải giữ server chạy: dọn theo key, không theo toàn mount

Đôi khi nhiều bài lab chia sẻ một Vault cục bộ. Trường hợp đó, không dùng **docker compose down** cho server chung và không **secrets disable lab010-kv** nếu mount có tài nguyên ngoài phạm vi. Chỉ quản lý đúng key được tạo bởi bài.

Ví dụ lệnh quản trị kiểm tra trước khi xóa:

~~~bash
docker compose -p sv-lab010 exec -T vault vault kv metadata get -mount=lab010-kv apps/orders/config
docker compose -p sv-lab010 exec -T vault vault kv metadata get -mount=lab010-kv apps/billing/config
~~~

Nếu đã xác minh đây thực sự là hai key **của riêng bài** và cần xóa vĩnh viễn mọi version, có thể sử dụng cú pháp KV v2:

~~~bash
# Destructive: chỉ dùng trong Vault lab thuộc quyền sở hữu của bạn.
docker compose -p sv-lab010 exec -T vault vault kv metadata delete -mount=lab010-kv apps/orders/config
docker compose -p sv-lab010 exec -T vault vault kv metadata delete -mount=lab010-kv apps/billing/config
~~~

**metadata delete** xóa cả lịch sử version của key, khác với **vault kv delete** vốn soft-delete version mới nhất và có thể undelete khi chưa destroy. Chỉ dùng thao tác permanent delete khi bạn chắc chắn không cần khôi phục và không còn workload phụ thuộc. Với Vault chứa dữ liệu thật, tuân theo chính sách retention/backup thay vì áp dụng lệnh lab.

### 11.4. Khi test thất bại giữa chừng

Teardown không được chỉ chạy khi mọi assertion pass. Trong code test, nên dùng lifecycle hooks hoặc **try/finally** thích hợp để đóng HTTP client, dừng container và giải phóng resource dù test throw exception. Đồng thời đừng xóa sạch log chẩn đoán **trước khi** lưu đủ thông tin không nhạy cảm để xác định nguyên nhân thất bại.

Ở CI có cơ chế tự dọn Testcontainers, nhưng vẫn cần kiểm soát token test, volume tạm, file TLS/CA và các tài nguyên ngoài container nếu suite tạo ra. Nếu test tạo tài khoản động trong database bên ngoài, dừng Vault container không tự chứng minh những tài khoản đó đã bị thu hồi.

## 12. Tài liệu hóa kết quả và xử lý sự cố

### 12.1. Mẫu biên bản kết quả

Một bản ghi kết quả nên có:

~~~text
Lab: spring-vault-lab010
Scope: Vault dev container owned by this run
Image: hashicorp/vault:1.19.0
Profile: local (không chứa credential)
KV engine: lab010-kv, version 2
Fixture: Orders + Billing (synthetic only)
Expected positive: Orders read -> PASS
Expected negative: Billing read -> 403 -> PASS
Expected negative: Orders put -> 403 -> PASS
Spring Vault smoke: PASS
Teardown: token revoked; project stopped
Credential values: NOT RECORDED
~~~

Với CI, có thể ghi thêm commit/build ID, thời điểm chạy, phiên bản JDK/Spring/Testcontainers, thời lượng và error category. Không ghi token, AppRole secret ID, password, plaintext, private key hoặc raw Vault response.

**Quan trọng:** Không mặc định đánh dấu PASS nếu chưa chạy lệnh thật. Người viết tài liệu có thể nêu kỳ vọng, nhưng kết quả thực nghiệm chỉ được đánh dấu sau khi môi trường tương ứng đã thực thi và kiểm tra.

### 12.2. Bảng nguyên nhân thường gặp

| Hiện tượng | Nguyên nhân hay gặp | Cách xử lý đúng tầng |
| --- | --- | --- |
| Container không khởi động | Port 8200 đã có người dùng, image không tải được, Docker chưa chạy | Kiểm tra Compose ps/log, cổng host và Docker |
| Vault health không là 200 | Node sealed/uninitialized/standby hoặc dịch vụ chưa sẵn sàng | Đọc status/health và ngữ cảnh HA, không tự dùng root |
| **secrets enable** báo path đã tồn tại | Lab không còn ở trạng thái fresh | Kiểm tra mount và engine version |
| Fixture read cho kết quả khác | Chạy vào Vault khác hoặc key bị test trước sửa | Kiểm tra Compose project, mount, env_label |
| KV version tăng bất ngờ | Bootstrap lặp **kv put**, test ghi trên key chung | Kiểm tra metadata và thứ tự fixture |
| **403** khi Orders read | Token sai/hết hạn hoặc policy sai **data/** path | Kiểm tra auth, TTL và policy |
| Billing read thành công bằng token reader | Có thể đang dùng root token hoặc token mang policy rộng | Kiểm tra **-e VAULT_TOKEN** và token policies |
| Java không tìm được KV | Sai URI, mount/key hoặc startup trước bootstrap | So CLI/API/Java, kiểm tra sequencing |
| **Connection refused/timeout** | Vault chưa chạy, sai host/port hoặc network | Kiểm tra TCP trước policy |
| Java **PKIX** hoặc hostname mismatch | JVM truststore thiếu CA hoặc SAN không khớp | Sửa truststore/URI, không tắt TLS verification |
| Token hoạt động rồi hết hạn | TTL ngắn, không có renew/re-login | Tạo token mới trong lab; cấu hình SessionManager khi cần |
| Transit decrypt thất bại | Sai key/mount, ciphertext hoặc thiếu quyền | Kiểm tra đúng endpoint và policy decrypt |
| PKI issue không thành công | CN/TTL ngoài role hoặc policy không có update | Kiểm tra PKI role và API issue path |
| Dọn lab làm mất dữ liệu khác | Xóa mount/volume hoặc dùng sai project | Phục hồi theo backup nếu có, sửa guard ownership |

**Đừng sửa sai tầng:** lỗi DNS không giải quyết bằng policy; lỗi TLS không giải quyết bằng token; lỗi thiếu key không giải quyết bằng retry vô hạn; và 403 không phải lý do tự mở quyền root.

### 12.3. Quan sát tối thiểu mà không rò rỉ bí mật

Một bài độc lập vẫn nên quan sát được trạng thái:

- **Vault status/health** để biết kết nối và seal/active state.
- **HTTP status và độ trễ** của request bằng token app.
- **Loại lỗi**: network, TLS, authentication, authorization, data missing, rate/timeout.
- **Tài nguyên được tạo**: tên mount/key/role đã biết, version metadata phù hợp, không phải raw secret.
- **Cleanup**: token không còn sử dụng được, container/project đã dừng đúng phạm vi.

Với workload production, telemetry, audit device, retention và cảnh báo cần được quản trị riêng. Một log có mã 403 là dữ liệu chẩn đoán, không phải lời mời ghi thêm client token để “xem có vấn đề gì”.

## 13. Một runbook thực hành từ đầu đến cuối

Đây là bản tóm lược thứ tự thực hiện cho người học **không cần làm bài trước**:

1. **Chuẩn bị:** Docker/Compose/JDK, một thư mục lab riêng, xác nhận cổng 8200 còn trống; không sử dụng Vault thật.
2. **Tạo server:** lưu **compose.yaml** và chạy **docker compose -p sv-lab010 up -d**.
3. **Preflight:** chạy **vault status**, xem health và danh sách mount. Chỉ tiến hành khi đúng server và trạng thái dev hợp lệ.
4. **Bootstrap:** enable **lab010-kv/** nếu chưa có; seed **apps/orders/config** và **apps/billing/config** bằng dữ liệu giả.
5. **Gắn quyền:** nạp **lab010-orders-reader** với read trên đúng **data/** path; phát token TTL ngắn.
6. **CLI verify:** dùng **-e VAULT_TOKEN** của ứng dụng để xác minh Orders được đọc, Billing và put Orders bị từ chối.
7. **Java verify:** chạy **VaultTemplate** với cùng URI/token, kiểm tra **app_name** và **env_label**, không log secret.
8. **Tùy chọn:** làm bài AppRole, Transit, PKI hoặc TLS trong fixture riêng; không để module mở rộng thay đổi kết quả của core lab.
9. **Ghi kết quả:** lưu thông tin test PASS/FAIL, loại lỗi, cấu hình phiên bản và tài nguyên sở hữu; loại bỏ credential.
10. **Teardown:** thu hồi token lab nếu còn hợp lệ, xóa biến môi trường, rồi **docker compose -p sv-lab010 down**.
11. **Tái tạo:** chạy lại từ bước 2 với một Vault dev mới; xác minh cùng hành vi, chấp nhận token/timestamps khác.

### 13.1. Ma trận kiểm tra nghiệm thu

| Tiêu chí | Phép kiểm tra | Điều kiện đạt |
| --- | --- | --- |
| Reproducible bootstrap | Fresh lab không có tài nguyên từ bài khác | Có mount KV v2, hai key đúng schema |
| Correct targeting | Đối chiếu URI/mount/nhãn fixture | Không đọc nhầm Vault khác |
| Least privilege | Token app chỉ có read Orders | Read Orders thành công; Billing/put bị 403 |
| Java integration | VaultTemplate dùng mount và key đúng | Giá trị giả đúng, không log secret |
| Retry/rerun behavior | Chạy verify lần hai trên state cũ | Không sinh thêm KV version |
| Independent execution | Chạy suite đơn lẻ và trong CI mới | Không cần dữ liệu thủ công từ trước |
| Cleanup safety | Dừng đúng Compose project | Không tác động tới Vault khác |
| Optional extensions | AppRole/Transit/PKI/TLS có preconditions riêng | Core lab vẫn chạy được khi bỏ các module đó |

## 14. Bài tập và tình huống mở rộng

**Bài 1 — Viết hợp đồng fixture.** Thiết kế bài độc lập cho một **billing-service** cần đọc key **apps/billing/config**. Liệt kê mount, key, field giả, policy, positive/negative test, trạng thái ban đầu và phạm vi cleanup. Không giả định trước có key Orders hoặc policy của người học khác.

**Bài 2 — Chạy lại mà không tăng version.** Chạy bootstrap KV v2 trên một Vault sạch, ghi nhận version. Chạy lại bước verify, không chạy put. Nếu muốn viết script seed rerunnable, hãy nêu thuật toán **read/compare/create-or-fail** và giải thích vì sao ghi lại cùng giá trị vẫn tạo version.

**Bài 3 — Kiểm thử token giới hạn.** Cấp token chỉ read Orders, chạy ba lệnh read Orders, read Billing, put Orders. Giải thích vì sao một test chỉ kiểm tra read thành công bằng root token không đủ xác nhận quyền.

**Bài 4 — Test song song.** Có hai suite cùng muốn ghi **apps/orders/config**. Chọn hai cách cô lập (container riêng hoặc prefix độc lập) và phân tích ảnh hưởng lên version assertions, token, cổng mạng và teardown.

**Bài 5 — AppRole lifecycle.** Tạo một AppRole role test gắn policy Orders với secret ID một lượt. Đăng nhập rồi thử đăng nhập lại bằng secret ID cũ. Phân biệt thời hạn của secret ID và client token, nêu cách cấp lại credential mà không hardcode trong code.

**Bài 6 — Transit không so ciphertext cố định.** Mã hóa **ping-test** bằng Transit key của lab, giải mã lại bằng role có quyền, kiểm tra plaintext. Giải thích vì sao test so ciphertext với chuỗi lưu sẵn là không bền vững.

**Bài 7 — PKI và TLS.** Thiết kế test xin chứng chỉ cho **orders.lab010.internal**, kiểm tra SAN/TTL/role và phân biệt với certificate của Vault listener. Nêu cách đặt CA/test truststore riêng để không dùng credential hoặc CA production.

**Bài 8 — Dọn dẹp theo quyền sở hữu.** Giả sử **lab010-kv/** chứa thêm key do một nhóm khác tạo. Hãy chọn hành động xóa khi kết thúc bài core; giải thích vì sao **secrets disable** hoặc xóa cả volume là sai nếu bạn không sở hữu toàn bộ mount/cluster.

## 15. Checklist hoàn thành bài

- [ ] Bài có hợp đồng đầu vào, fixture, lệnh kiểm tra, đầu ra và điều kiện hoàn thành.
- [ ] Vault thuộc project/môi trường riêng, không kết nối tới production hoặc dữ liệu thật.
- [ ] Đã xác minh Vault health, mount type và KV version trước bootstrap.
- [ ] Fixture được tạo từ dữ liệu tổng hợp; không cần bản sao của secret có thật.
- [ ] Token app khác root token bootstrap, có policy tối thiểu và TTL phù hợp.
- [ ] CLI kiểm chứng được cả thao tác **được phép** và **bị từ chối**.
- [ ] VaultTemplate đọc đúng data path KV v2, xử lý dữ liệu thiếu và không in secret.
- [ ] Bài phân biệt fresh run, rerun/verify và reset; biết những lệnh không idempotent.
- [ ] Test có thể chạy độc lập với test trước và không phụ thuộc cổng/token cố định trong CI.
- [ ] Các module AppRole, Transit, PKI, TLS và lease (nếu dùng) có fixture/cleanup riêng.
- [ ] Kết quả được kiểm tra theo thuộc tính ổn định, không so token/ciphertext/serial ngẫu nhiên.
- [ ] Có danh sách tài nguyên do bài sở hữu và teardown đúng phạm vi.
- [ ] Không có token, private key, secret ID, plaintext hoặc mật khẩu thật trong mã nguồn/log.

**Kết luận:** Bài thực hành Spring Vault có chất lượng không chỉ là tập hợp lệnh chạy thành công một lần. Nó phải tạo được **một môi trường độc lập**, dựng lại từ trạng thái sạch, dùng **dữ liệu giả và quyền tối thiểu**, kiểm chứng cả đường đi thành công lẫn thất bại, sau đó **thu hồi đúng những gì bài sở hữu**. Khi áp dụng các nguyên tắc ấy, người học có thể luyện KV, vòng đời token/lease, Transit, PKI, TLS và kiểm thử tích hợp một cách lặp lại, quan sát được và an toàn hơn.
