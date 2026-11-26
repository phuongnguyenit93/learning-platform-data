# Dữ liệu giả, cấu hình ngoài mã nguồn và phạm vi dọn dẹp

## 1. Mục tiêu của môi trường thực hành

Khi một ứng dụng Java dùng **Spring Vault**, các lời gọi **VaultTemplate** có thể đọc KV secrets, gọi **Transit encryption**, yêu cầu chứng chỉ từ **PKI** hoặc sử dụng token/lease có thời hạn. Những chức năng này rất thuận tiện để học với HashiCorp Vault cục bộ, nhưng cũng tạo ra hai rủi ro thường bị xem nhẹ: dữ liệu thử nghiệm vô tình chứa thông tin thật và lệnh dọn dẹp được thực hiện trên phạm vi rộng hơn dự kiến.

Chủ đề của bài là **tạo dữ liệu giả**, **đưa cấu hình ra khỏi mã nguồn** và **xác định chính xác phạm vi dọn dẹp**. Mọi ví dụ đều đặt trong chương **Môi trường thực hành** và sử dụng một Vault riêng cho học tập; mục đích là có thể chạy lại bài mà không cần trao đổi mật khẩu, token hay dữ liệu nội bộ giữa những người học.

Sau bài này, bạn có thể:

1. Chọn dữ liệu tổng hợp có cấu trúc sát nghiệp vụ nhưng không chứa credential hoặc dữ liệu cá nhân thật.
2. Khởi tạo một KV v2 mount riêng, đặt tên logical key nhất quán và quan sát tác động của việc ghi lại lên version.
3. Tách endpoint, mount, logical key, token và thông tin tin cậy TLS khỏi mã nguồn Java.
4. Đọc dữ liệu mẫu qua **VaultTemplate** bằng token chỉ đọc và xác minh policy không cho phép ghi.
5. Hiểu vòng đời dữ liệu thực hành trong KV v2, Transit, PKI, AppRole, client token và dynamic lease.
6. Chọn đúng cấp dọn dẹp: dừng ứng dụng, thu hồi token, xóa một version, xóa một key, vô hiệu hóa mount hay xóa toàn bộ lab.
7. Xây dựng checklist trước/sau khi dọn dẹp để không tác động Vault hoặc tài nguyên không thuộc bài thực hành.

**Quy ước:** Địa chỉ **127.0.0.1**, domain **example.invalid**, user **demo** và các chuỗi có tiền tố **fake-** trong bài đều dành cho lab. Vault dev mode dùng HTTP và root token cố định chỉ để tạo tài nguyên; token root không được đưa vào ứng dụng Java. Không chạy các lệnh xóa dữ liệu ngoài môi trường học mà bạn có quyền sở hữu và đã xác định rõ phạm vi.

## 2. Thiết kế dữ liệu giả: đủ thật để kiểm thử, không chứa bí mật thật

### 2.1. Dữ liệu giả khác dữ liệu đã che bớt

**Dữ liệu giả/tổng hợp** được tạo riêng cho bài tập, không lấy từ sản phẩm hay tài khoản thật. Ngược lại, thay vài ký tự của mật khẩu thật, che một phần API key, sử dụng bản sao database production hoặc sửa tên khách hàng trong dữ liệu nhạy cảm vẫn có thể làm lộ thông tin.

| Trường cần minh họa | Giá trị giả phù hợp | Không nên đưa vào lab |
| --- | --- | --- |
| Tên ứng dụng | **orders-training** | Tên gắn với hệ thống hoặc khách hàng nhạy cảm khi không cần thiết |
| API endpoint | **https://orders.example.invalid/api** | URL dịch vụ nội bộ thật |
| Tên database | **orders_lab** | Tên database production kèm host thật |
| Tài khoản database | **demo_reader** | Tài khoản thật hoặc bản sao thông tin đăng nhập |
| Mật khẩu trong ví dụ | **fake-db-password-001** | Mật khẩu đang được dùng ở bất kỳ môi trường nào |
| API token trong ví dụ | **fake-token-no-access** | Token thực, kể cả token đã được che một phần |
| Email kiểm thử | **learner@example.invalid** | Email cá nhân/khách hàng thật |
| Dữ liệu nghiệp vụ | **order_id=LAB-ORDER-001**, **amount=125000** | Bản ghi giao dịch thật, dữ liệu được trích xuất từ production |

Miền **.invalid** được dùng để biểu thị đích không tồn tại trong ví dụ; đừng trông đợi HTTP request tới **example.invalid** thành công. Nếu bài cần gọi một dịch vụ thực, hãy tạo một mock server local và cấp địa chỉ của mock qua cấu hình chạy test.

Giá trị **fake-db-password-001** là một chuỗi minh họa, không được coi là mật khẩu “khá mạnh” hoặc credential dành cho một hệ thống thật. Một lab có thể dùng giá trị giả có vẻ giống cấu hình nghiệp vụ để kiểm thử luồng đọc, nhưng không cần chứng minh chúng đăng nhập được vào dịch vụ bên ngoài.

### 2.2. Tạo dataset nhỏ, đặt tên dễ truy vết

Giả sử có hai workload **orders-api** và **billing-worker**. Mỗi workload có cấu hình riêng:

~~~text
lab-kv/                            # Mount KV v2 dành riêng cho phòng lab
└── exercises/
    └── cleanup-008/
        ├── orders/
        │   ├── config              # Cấu hình ứng dụng Orders giả
        │   └── db                  # Credential database giả
        └── billing/
            └── config              # Secret khác để test 403
~~~

Chọn tiền tố **exercises/cleanup-008/** để người thực hành nhận ra tài nguyên được tạo bởi bài này. Đây là **logical key prefix bên trong KV**, không phải namespace bảo mật độc lập. Quyền truy cập được kiểm soát bởi policy trên **API path**; prefix chỉ hỗ trợ tổ chức, kiểm thử và xác định phạm vi cleanup.

Mẫu dữ liệu và kỳ vọng:

| Logical key | Trường trong secret | Dùng để kiểm thử |
| --- | --- | --- |
| **exercises/cleanup-008/orders/config** | app_name, api_url, timeout_ms | Đọc KV v2 bằng VaultTemplate |
| **exercises/cleanup-008/orders/db** | jdbc_url, username, password | Giữ dữ liệu giả theo cấu trúc credential |
| **exercises/cleanup-008/billing/config** | app_name, api_token | Kiểm tra Orders không đọc được Billing |

Quy tắc tốt cho fixture: mỗi key có một mục đích; một lần chạy test biết rõ nó tạo và sửa những key nào; tên key không trùng với dữ liệu không thuộc lab. Khi cần thử version, dùng một key cụ thể chứ không ghi đi ghi lại tùy ý lên toàn bộ mount.

### 2.3. Dữ liệu giả vẫn cần được đối xử như secret trong code

Ngay cả khi nội dung là giả, **ứng dụng và test nên có thói quen không log nguyên response**. Nếu luồng code được sao chép sang production mà trước đó có dòng **System.out.println(secret)**, thông tin thật có thể xuất hiện trong log.

Có thể ghi log loại request, mount/key logic (sau khi kiểm tra không chứa thông tin nhạy cảm), mã HTTP, thời gian thực hiện và số version. Không log giá trị của các trường **password**, **api_token**, plaintext Transit, private key PKI hoặc client token. Trong test, assertion nên so khớp dữ liệu giả rồi báo kết quả, không tự động dump toàn bộ cấu hình mỗi khi thất bại.

## 3. Chạy Vault dev chỉ trên máy cá nhân

### 3.1. Cấu hình Docker Compose

Ví dụ dưới đây yêu cầu Docker Engine/Docker Desktop, Docker Compose v2 và cổng **8200** còn trống. Tạo một thư mục lab riêng và tệp **compose.yaml**:

~~~yaml
services:
  vault:
    image: hashicorp/vault:1.19.0
    cap_add:
      - IPC_LOCK
    command: server -dev -dev-listen-address=0.0.0.0:8200
    environment:
      VAULT_ADDR: http://127.0.0.1:8200
      VAULT_DEV_ROOT_TOKEN_ID: dev-root-only
      VAULT_TOKEN: dev-root-only
    ports:
      - "127.0.0.1:8200:8200"
    restart: "no"
~~~

Từ thư mục chứa **compose.yaml**:

~~~bash
docker compose up -d
docker compose ps
docker compose exec -T vault vault status
docker compose exec -T vault vault secrets list -detailed
~~~

Trạng thái kỳ vọng: **Initialized = true**, **Sealed = false**. Cổng trên host chỉ được bind vào **127.0.0.1**; trong container Vault nghe **0.0.0.0:8200** để Docker có thể chuyển tiếp kết nối. Image được cố định phiên bản để lab lặp lại được, không hàm ý đó là phiên bản Vault mới nhất.

Ví dụ sử dụng **Vault CLI bên trong container** thông qua **docker compose exec -T vault vault**. Các lệnh bootstrap có quyền root từ biến môi trường trong container; **phải thay token** khi kiểm thử vai trò ứng dụng.

**Tính chất dev mode:** Trạng thái được lưu trong bộ nhớ và có thể mất khi tiến trình/container restart. Việc dữ liệu biến mất sau restart không chứng minh cơ chế cleanup production hoạt động; đó là đặc điểm của máy chủ dev. Trong non-dev, dữ liệu có thể còn trên storage sau khi container dừng.

### 3.2. Nhận diện Vault trước khi tạo hoặc xóa tài nguyên

Trước khi thao tác, kiểm tra:

~~~bash
docker compose ps
docker compose exec -T vault vault status
docker compose exec -T vault vault secrets list -detailed
~~~

Phạm vi phải xác nhận gồm **Compose project/thư mục**, **container service**, **VAULT_ADDR**, **Vault namespace nếu có**, **mount path** và **token hiện dùng**. Nếu chạy CLI trên host thay vì container, token và Vault URL có thể khác; việc gõ đúng tên mount nhưng trỏ tới server khác vẫn tác động sai hệ thống.

Không dùng root token từ phòng lab để chạy Java. Khi tạo token ứng dụng, truyền vào một biến môi trường khác và kiểm chứng nó chỉ có policy cần thiết.

## 4. Seed dữ liệu giả trong KV v2

### 4.1. Tạo mount riêng

Nếu trong **vault secrets list -detailed** chưa có **lab-kv/**:

~~~bash
docker compose exec -T vault vault secrets enable -path=lab-kv kv-v2
docker compose exec -T vault vault secrets list -detailed
~~~

Khi mount đã tồn tại, bỏ qua lệnh **secrets enable**. Mount này có thể phục vụ nhiều bài học trong một lab; vì vậy việc dọn một bài nên bắt đầu từ **logical key prefix** của bài đó, không tự động disable toàn bộ mount.

### 4.2. Ghi các bản ghi giả

Các lệnh một dòng sau chạy được qua CLI trong container mà không cần cài Vault CLI trên host:

~~~bash
docker compose exec -T vault vault kv put -mount=lab-kv exercises/cleanup-008/orders/config app_name=orders-training api_url=https://orders.example.invalid/api timeout_ms=1500
docker compose exec -T vault vault kv put -mount=lab-kv exercises/cleanup-008/orders/db jdbc_url=jdbc:postgresql://127.0.0.1:5432/orders_lab username=demo_reader password=fake-db-password-001
docker compose exec -T vault vault kv put -mount=lab-kv exercises/cleanup-008/billing/config app_name=billing-training api_token=fake-token-no-access
~~~

Đọc lại bằng CLI:

~~~bash
docker compose exec -T vault vault kv get -mount=lab-kv exercises/cleanup-008/orders/config
docker compose exec -T vault vault kv get -mount=lab-kv exercises/cleanup-008/orders/db
docker compose exec -T vault vault kv list -mount=lab-kv exercises/cleanup-008/
docker compose exec -T vault vault kv list -mount=lab-kv exercises/cleanup-008/orders/
~~~

Lệnh **kv list** liệt kê *tên key hoặc prefix con* chứ không in nội dung mọi secret. Trong phòng lab có thể đọc giá trị giả để kiểm chứng; trên hệ thống thật, không nên in credential lên terminal được lưu log.

### 4.3. Version tạo ra tác động phụ khi seed lại

Gọi **kv put** lần thứ hai trên cùng key sẽ tạo version mới. Để quan sát có kiểm soát:

~~~bash
docker compose exec -T vault vault kv patch -mount=lab-kv exercises/cleanup-008/orders/config timeout_ms=2500
docker compose exec -T vault vault kv get -mount=lab-kv exercises/cleanup-008/orders/config
docker compose exec -T vault vault kv metadata get -mount=lab-kv exercises/cleanup-008/orders/config
~~~

Nếu mount/key mới được tạo và chưa có version bổ sung, lần **kv put** đầu tạo version 1, còn **kv patch** tạo version 2. Nếu chạy lại các bước, số version tiếp tục tăng. **kv patch** giữ các trường cũ không được thay; **kv put** mới có thể thay thế toàn bộ tập dữ liệu của version hiện tại nếu bỏ trường.

Trong KV v2:

- CLI **vault kv get -mount=lab-kv exercises/cleanup-008/orders/config** sử dụng logical key.
- HTTP API đọc ở **/v1/lab-kv/data/exercises/cleanup-008/orders/config**.
- Vault policy cho dữ liệu viết **path "lab-kv/data/exercises/cleanup-008/orders/config"**.
- Metadata dùng **lab-kv/metadata/exercises/cleanup-008/orders/config**; quyền list khác quyền read.

**KV v2 version không phải dynamic lease**. Việc đọc một secret KV tĩnh không tự tạo credential tạm thời có **lease_id** như database secrets engine. Đừng dùng cách xóa lease để thay thế quy trình xóa version KV v2.

## 5. Quyền tối thiểu để Java đọc dữ liệu mẫu

### 5.1. Policy read-only

Tạo tệp **policies/cleanup-008-reader.hcl** ở thư mục lab:

~~~hcl
path "lab-kv/data/exercises/cleanup-008/orders/config" {
  capabilities = ["read"]
}

path "lab-kv/data/exercises/cleanup-008/orders/db" {
  capabilities = ["read"]
}
~~~

Policy này không cấp quyền cho dữ liệu Billing, không cho ghi vào KV và không cho thao tác trên Transit, PKI hoặc path quản trị. Không cần cấp **list** trên **metadata/** nếu ứng dụng chỉ đọc hai key đã biết.

Nạp policy:

~~~bash
docker compose cp policies/cleanup-008-reader.hcl vault:/tmp/cleanup-008-reader.hcl
docker compose exec -T vault vault policy write cleanup-008-reader /tmp/cleanup-008-reader.hcl
docker compose exec -T vault vault policy read cleanup-008-reader
~~~

Tạo token TTL ngắn và chỉ dành cho lab:

~~~bash
docker compose exec -T vault vault token create -policy=cleanup-008-reader -ttl=15m -field=token
~~~

Lưu token vừa tạo vào biến môi trường trong shell thực hành, **không ghi token trực tiếp vào code**. Với Bash/zsh:

~~~bash
export LAB_VAULT_TOKEN="<reader-token-vua-tao>"
~~~

Với PowerShell:

~~~powershell
$env:LAB_VAULT_TOKEN = "<reader-token-vua-tao>"
~~~

### 5.2. Kiểm chứng policy bằng token ứng dụng

Container Vault đang có **VAULT_TOKEN=dev-root-only**; để không vô tình chạy bằng root, cần ghi đè biến này cho từng request kiểm thử. Bash/zsh:

~~~bash
docker compose exec -T -e "VAULT_TOKEN=$LAB_VAULT_TOKEN" vault vault kv get -mount=lab-kv exercises/cleanup-008/orders/config
docker compose exec -T -e "VAULT_TOKEN=$LAB_VAULT_TOKEN" vault vault kv get -mount=lab-kv exercises/cleanup-008/billing/config
docker compose exec -T -e "VAULT_TOKEN=$LAB_VAULT_TOKEN" vault vault kv put -mount=lab-kv exercises/cleanup-008/orders/config app_name=unauthorized
~~~

Với PowerShell, dùng **-e "VAULT_TOKEN=$env:LAB_VAULT_TOKEN"** thay cho cách tham chiếu biến của Bash. Kỳ vọng: lệnh đọc Orders thành công; đọc Billing và ghi Orders bị **403 permission denied**. Nếu ghi được thì cần kiểm tra token, chính sách gắn với token và xem có đang dùng root token hay không.

**Không cấp root token để sửa lỗi 403.** Lỗi có thể do policy sai API path **data/**, thiếu capability, token hết hạn, sai mount hoặc gọi bằng credential không phải của workload. Khi triển khai, dùng AppRole, Kubernetes/JWT hoặc cloud auth phù hợp danh tính workload và quản lý token TTL/renew/re-login, thay vì phát một token thủ công dùng lâu dài.

## 6. Đưa cấu hình kết nối ra khỏi mã nguồn

### 6.1. Phân loại những gì cần cấu hình từ bên ngoài

| Giá trị | Có thể đặt trong file cấu hình được review? | Nguồn khuyến nghị |
| --- | --- | --- |
| **Tên mount lab-kv** | Có, nếu không nhạy cảm | File profile/environment config |
| **Logical key exercises/cleanup-008/orders/config** | Có, nếu không tiết lộ dữ liệu nhạy cảm | File profile hoặc deployment config |
| **Vault URL local** | Có, nếu là URL giả hoặc loopback | File profile local |
| **Vault URL production** | Tùy chính sách hạ tầng, thường là cấu hình không bí mật | Deployment/environment config |
| **Root token / client token** | **Không** | Workload identity, secret delivery hoặc biến môi trường bảo vệ |
| **AppRole secret ID, JWT riêng tư, client private key** | **Không** | Cơ chế cấp credential an toàn của nền tảng |
| **Mật khẩu DB, API key thật** | **Không** | Vault KV/dynamic secrets engine phù hợp |
| **CA certificate công khai** | Có thể phân phối như trust anchor được xác minh | Truststore, cấu hình TLS |
| **Private key của CA/PKI/server TLS** | **Không** | Cơ chế quản lý khóa/secret riêng và quyền đọc giới hạn |

Một quy tắc đơn giản: **nội dung secret không nên được đưa vào artifact build**, còn tên key và cấu hình định tuyến có thể được kiểm soát bằng version control nếu không làm lộ thông tin nhạy cảm. File cấu hình chỉ nên chứa cách **tìm** và **được phép đọc** secret, không chứa bản sao secret.

### 6.2. Ví dụ Spring Boot profile local

Giả sử ứng dụng dùng Spring Boot với **Spring Vault Core**. Có thể định nghĩa các thuộc tính tùy chỉnh dưới **training.vault** trong **application-local.yml**:

~~~yaml
training:
  vault:
    uri: ${LAB_VAULT_URI:http://127.0.0.1:8200}
    kv-mount: ${LAB_VAULT_KV_MOUNT:lab-kv}
    config-key: exercises/cleanup-008/orders/config
~~~

Các thuộc tính **training.vault.*** **không tự động** cấu hình VaultTemplate; cần có Java configuration đọc chúng và tạo client. Profile local cho phép default loopback để học. Đối với profile staging/production, phải yêu cầu người triển khai cung cấp URI HTTPS, auth method và trust configuration thực tế, không có fallback về localhost hoặc root token.

Ví dụ **application-prod.yml** biểu đạt sự khác nhau:

~~~yaml
training:
  vault:
    uri: ${LAB_VAULT_URI}
    kv-mount: ${LAB_VAULT_KV_MOUNT}
    config-key: exercises/cleanup-008/orders/config
~~~

Đường dẫn **exercises/cleanup-008/orders/config** chỉ được dùng ở đây để minh họa khả năng tham số hóa. Không triển khai profile production thật với một key của bài lab; trong ứng dụng vận hành, thay bằng key nghiệp vụ, policy và mount được quản trị riêng.

**Phân biệt Spring Vault Core và Spring Cloud Vault:** **VaultTemplate** là API truy cập Vault tại runtime. **Spring Cloud Vault** có thêm cơ chế nạp property từ Vault vào Spring Environment nếu được cấu hình đúng theo phiên bản dự án. Không nên nhầm một thuộc tính tùy chỉnh như **training.vault.kv-mount** với thuộc tính tự động được Spring Cloud Vault hiểu; một hệ thống cần xác định rõ cơ chế nạp secret nào đang là nguồn chính.

### 6.3. Java cấu hình VaultTemplate chỉ dành cho local

Ví dụ dưới đây minh họa việc đọc URL từ Spring profile và token từ environment của tiến trình Java:

~~~java
import java.net.URI;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Profile;
import org.springframework.vault.authentication.TokenAuthentication;
import org.springframework.vault.client.VaultEndpoint;
import org.springframework.vault.core.VaultTemplate;

@Configuration
@Profile("local")
public class LocalVaultConfiguration {

    @Bean
    VaultTemplate vaultTemplate(
            @Value("${training.vault.uri}") String vaultUri) {

        String token = System.getenv("LAB_VAULT_TOKEN");
        if (token == null || token.isBlank()) {
            throw new IllegalStateException(
                    "LAB_VAULT_TOKEN is required for the local lab");
        }

        URI uri = URI.create(vaultUri);
        if (!"http".equalsIgnoreCase(uri.getScheme())
                || !"127.0.0.1".equals(uri.getHost())) {
            throw new IllegalStateException(
                    "Local lab expects http://127.0.0.1");
        }

        return new VaultTemplate(
                VaultEndpoint.from(uri),
                new TokenAuthentication(token));
    }
}
~~~

Đây là **cấu hình local có chủ đích**, không phải cấu hình production. Khi dùng alias **localhost** thay IP, phải điều chỉnh kiểm tra URI cho phù hợp; ví dụ buộc đúng IP nhằm tránh vô tình kết nối đến một host khác. Trong môi trường deploy, cần một **VaultTemplate bean khác** với HTTPS, CA/truststore và **ClientAuthentication/SessionManager** theo workload. Không làm fallback sang token root nếu thiếu token ứng dụng.

Service đọc secret cũng lấy mount và logical key từ cấu hình:

~~~java
import java.util.Map;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;
import org.springframework.vault.core.VaultTemplate;
import org.springframework.vault.support.Versioned;

@Component
public class OrdersLabConfigReader {

    private final VaultTemplate template;
    private final String mount;
    private final String logicalKey;

    public OrdersLabConfigReader(
            VaultTemplate template,
            @Value("${training.vault.kv-mount}") String mount,
            @Value("${training.vault.config-key}") String logicalKey) {
        this.template = template;
        this.mount = mount;
        this.logicalKey = logicalKey;
    }

    public Map<String, Object> read() {
        Versioned<Map<String, Object>> version = template
                .opsForVersionedKeyValue(mount)
                .get(logicalKey);

        if (version == null || version.getData() == null) {
            throw new IllegalStateException("Lab KV config not found");
        }
        return version.getData();
    }
}
~~~

Lời gọi Java **opsForVersionedKeyValue("lab-kv").get("exercises/cleanup-008/orders/config")** tương ứng với API **GET /v1/lab-kv/data/exercises/cleanup-008/orders/config**. Việc chọn sai **mount** không thể được sửa bằng cách thêm **data/** vào logical key.

Khi thực hành, sử dụng bean đọc này trong một test hoặc controller chỉ in **tên các trường**, không in toàn bộ bản đồ dữ liệu. Nếu đưa dữ liệu thực tế vào log, việc dọn KV sau đó cũng không xóa bản sao từng xuất hiện trong hệ thống log.

### 6.4. Chạy local bằng biến môi trường

Trên Bash/zsh:

~~~bash
export SPRING_PROFILES_ACTIVE=local
export LAB_VAULT_URI="http://127.0.0.1:8200"
export LAB_VAULT_KV_MOUNT="lab-kv"
# LAB_VAULT_TOKEN phải là token read-only đã cấp ở mục 5.
~~~

Trên PowerShell:

~~~powershell
$env:SPRING_PROFILES_ACTIVE = "local"
$env:LAB_VAULT_URI = "http://127.0.0.1:8200"
$env:LAB_VAULT_KV_MOUNT = "lab-kv"
# LAB_VAULT_TOKEN phải là token read-only đã cấp ở mục 5.
~~~

Chọn profile từ môi trường chạy, ví dụ dùng cấu hình của IDE, lệnh khởi chạy ứng dụng hoặc test harness. Không cấu hình production sao cho profile local có thể tự kích hoạt hoặc bị ghi đè bởi một file test.

Nếu cần một tệp mẫu cho đồng đội, có thể cung cấp **.env.example** chỉ có placeholder:

~~~dotenv
SPRING_PROFILES_ACTIVE=local
LAB_VAULT_URI=http://127.0.0.1:8200
LAB_VAULT_KV_MOUNT=lab-kv
LAB_VAULT_TOKEN=<obtain-a-read-only-token-locally>
~~~

File **.env.example** là tài liệu tham chiếu, không chứa credential thật. Nếu sử dụng **.env** thật để chạy ứng dụng, phải giới hạn quyền đọc và bảo đảm nó không được commit. Một đoạn **.gitignore** gợi ý:

~~~gitignore
.env
.env.*
!.env.example
*.key
*.p12
local-secrets/
~~~

Đây là gợi ý cho thư mục lab độc lập, không phải chỉ thị tự động thay **.gitignore** của dự án. **.gitignore không loại bỏ một bí mật đã từng được commit**; khi lỡ đưa credential thật vào lịch sử Git, cần thu hồi/đổi credential và xử lý lịch sử theo quy trình sự cố của tổ chức.

### 6.5. Dùng Secret Manager không đồng nghĩa với được log dữ liệu

Trong test CI, một số hệ thống có thể truyền token qua environment, file mount hoặc secret injection. Phương thức nào cũng cần xét quyền đọc của job/container, cấu hình shell tracing, log test thất bại và thời gian sống của credential. Tránh in toàn bộ biến môi trường hoặc Spring Environment khi debug vì có thể chứa token.

Với production, ưu tiên workload identity phù hợp hạ tầng như Kubernetes auth/JWT/cloud auth hoặc AppRole có kênh phân phối **secret_id** được quản lý. Không sao chép token đọc lab vào container image hoặc manifest deploy. Cấu hình bên ngoài mã nguồn là điều kiện cần, còn policy tối thiểu, TLS và vòng đời credential mới quyết định hệ thống có vận hành đúng hay không.

## 7. Phạm vi cleanup: hiểu tài nguyên trước khi xóa

Không có một lệnh “dọn lab” duy nhất phù hợp mọi trường hợp. Các tài nguyên do Vault quản lý có phạm vi và ý nghĩa thu hồi khác nhau:

| Tài nguyên | Phạm vi chịu tác động | Có thể phục hồi? | Ghi chú |
| --- | --- | --- | --- |
| Biến môi trường ở shell | Chỉ phiên shell/process liên quan | Có thể cấp lại | Không xóa bản sao trong log, IDE, CI hoặc process đã chạy |
| Client token | Credential cụ thể và quan hệ token/lease liên quan | Thường phải cấp token mới sau revoke | Không tương đương xóa KV secret |
| AppRole secret ID | Một khả năng đăng nhập cụ thể | Cấp secret ID mới | Không tự thu hồi mọi token đã login từ trước |
| KV v2 **delete version** | Version đang được soft-delete | Có thể undelete nếu chưa destroy và theo cấu hình | Metadata và version khác có thể vẫn còn |
| KV v2 **destroy version** | Dữ liệu của version chỉ định | Không khôi phục bằng undelete | Phạm vi hẹp hơn xóa toàn bộ key |
| KV v2 **metadata delete** | **Toàn bộ các version** và metadata của một logical key | Không phục hồi qua KV undelete | Phải xác minh chính xác key |
| **secrets disable** một mount | Toàn bộ dữ liệu và cấu hình engine tại mount | Không dùng làm thao tác dọn key lẻ | Dễ tác động tới nhiều bài và workload |
| Transit key / PKI CA / PKI role | Khả năng mã hóa/giải mã hoặc phát hành chứng chỉ | Phụ thuộc loại tài nguyên và backup | Có thể gây tác động lâu dài đến ciphertext/chứng chỉ |
| Docker container dev | Tiến trình và storage dev trong bộ nhớ | Có thể seed lại dữ liệu giả | Không tự xóa các file trên host |
| Named volume non-dev | Dữ liệu Vault bền vững của volume đó | Cần backup/restore ngoài volume | Xóa volume là tác động lớn |

**Quy tắc sắp xếp:** Bắt đầu từ tài nguyên hẹp nhất mà bài tạo ra; chỉ mở rộng phạm vi khi người học biết chắc không còn đối tượng khác phụ thuộc. **Prefix logical key** không tự là một mount; không được dùng lệnh **secrets disable** chỉ vì muốn xóa dữ liệu dưới prefix.

### 7.1. Hai loại “xóa” dễ bị nhầm của KV v2

Giả sử key **exercises/cleanup-008/orders/config** có version 1 và version 2:

- **Soft delete:** đánh dấu một hoặc nhiều version bị xóa; metadata và các version khác vẫn tồn tại, phiên bản soft-deleted có thể undelete theo điều kiện.
- **Destroy:** phá hủy dữ liệu của version được chọn; không thể lấy lại bằng thao tác undelete.
- **Delete metadata:** xóa bản ghi metadata và toàn bộ lịch sử version của logical key; đây là thao tác có phạm vi rộng nhất ở mức key.

Đọc metadata trước khi quyết định:

~~~bash
docker compose exec -T vault vault kv metadata get -mount=lab-kv exercises/cleanup-008/orders/config
~~~

Với key của **chính bài này**, thao tác soft-delete version hiện tại có dạng:

~~~bash
# Chỉ thực hiện trên Vault lab đã xác minh đúng target.
docker compose exec -T vault vault kv delete -mount=lab-kv exercises/cleanup-008/orders/config
~~~

**kv delete** của KV v2 soft-delete version mới nhất của key; version cũ và metadata vẫn có thể còn. Để phục hồi version bị soft-delete, cần biết số version thật sự và có policy phù hợp. Ví dụ, nếu version 2 vừa bị soft-delete:

~~~bash
docker compose exec -T vault vault kv undelete -versions=2 -mount=lab-kv exercises/cleanup-008/orders/config
~~~

Số **2** chỉ là ví dụ. Nếu key đã được ghi lại nhiều lần, phải xem metadata thay vì giả định version bị xóa là 2. Đối với các thao tác **destroy** hoặc **metadata delete**, không có “undelete” tương đương để khôi phục dữ liệu đã phá hủy.

### 7.2. Khi thật sự cần xóa hoàn toàn một key

Trong một lab hoàn toàn dành riêng cho bạn, sau khi đã liệt kê và xác nhận **đúng mount**, **đúng key**, **không còn bài khác sử dụng**, có thể xóa metadata và mọi version của **một key** như sau:

~~~bash
# Không chạy khi key/mount có dữ liệu của người hoặc bài khác.
docker compose exec -T vault vault kv metadata delete -mount=lab-kv exercises/cleanup-008/orders/config
~~~

Lệnh này **xóa toàn bộ lịch sử của key đã chỉ định**. Nó khác với **vault kv delete** vốn soft-delete version; sau **metadata delete**, không thể dùng **kv undelete** để lấy lại các version cũ. Dùng lệnh tương tự cho key **orders/db** hoặc **billing/config** chỉ khi các key đó do bài thực hành sở hữu và đã được kiểm kê.

Một thao tác khác là phá hủy **chỉ một số version**:

~~~bash
# Ví dụ phá hủy version 1: không thể khôi phục bằng undelete.
docker compose exec -T vault vault kv destroy -versions=1 -mount=lab-kv exercises/cleanup-008/orders/config
~~~

Chỉ dùng khi bài tập thật sự yêu cầu chứng minh sự khác nhau giữa **soft delete** và **destroy**. Với mục tiêu thông thường là bỏ hết fixture của bài, xóa metadata của đúng key sau khi kiểm tra phụ thuộc sẽ rõ nghĩa hơn việc gọi destroy nhiều lần cho từng version. Với mục tiêu cho phép quay lại phiên bản trước, **không destroy**.

**Thứ tự an toàn:** Dừng các ứng dụng/test đang dùng key → kiểm tra target Vault → ghi lại các key do bài sở hữu → quyết định cần soft delete hay permanent delete → thực hiện từng key → xác minh hậu trạng thái. Không tạo một script dùng wildcard rộng rồi mặc định chạy trên mọi Vault.

### 7.3. Dọn token, AppRole và lease

Trước khi kết thúc bài, nên thu hồi token ứng dụng dành riêng cho bài. Khi token hợp lệ vẫn còn trong **LAB_VAULT_TOKEN** và bạn đã xác nhận đó **không phải root token**, token có thể tự revoke bằng chính credential của nó:

~~~bash
# Bash/zsh: chỉ dùng với token lab của chính bài; biến không được rỗng.
docker compose exec -T -e "VAULT_TOKEN=$LAB_VAULT_TOKEN" vault vault token lookup
docker compose exec -T -e "VAULT_TOKEN=$LAB_VAULT_TOKEN" vault vault token revoke -self
~~~

PowerShell dùng **-e "VAULT_TOKEN=$env:LAB_VAULT_TOKEN"** thay vì biến Bash. Nếu biến chưa được cấp hoặc đã rỗng, hãy dừng và kiểm tra thay vì dựa vào token mặc định của container. Sau revoke, token đó không còn được dùng để đọc KV; nếu muốn tiếp tục bài, tạo token mới có policy phù hợp.

Nếu một bài khác đã bật AppRole và tạo **secret ID** thử nghiệm, việc secret ID hết hạn, hết lượt dùng hoặc bị thu hồi sẽ ngăn *lần đăng nhập mới* bằng secret ID đó; các **client token đã được phát hành trước đó** có vòng đời riêng. Không giả định xóa AppRole secret ID sẽ tự thu hồi mọi token đã nhận từ AppRole. Muốn dọn một client token cụ thể, dùng quy trình revoke phù hợp với quyền quản trị hoặc cơ chế tự revoke của token.

Với secrets engine sinh **dynamic lease** (ví dụ credential database), phải xem **lease_id**, thời hạn và khả năng renew/revoke của tài nguyên được cấp. Một lease có thể liên quan đến tài khoản thực ở hệ thống bên ngoài. Chỉ revoke những lease do bài tạo và đã định danh rõ; tránh lệnh revoke theo prefix rộng trong Vault dùng chung. Dữ liệu KV v2 tĩnh không có dynamic lease để dọn theo cách này.

### 7.4. Transit và PKI: không xóa khóa vì muốn xóa bản ghi

**Transit key** có thể là chìa khóa để giải mã ciphertext đã được ứng dụng lưu ở nơi khác. Xóa khóa Transit có thể làm các ciphertext đó không thể giải mã được. Nếu bài chỉ mã hóa một chuỗi giả rồi bỏ ciphertext, thường **không cần** xóa khóa nếu mount thuộc môi trường chia sẻ; trong lab tách biệt có thể dọn cả mount khi chắc chắn không còn dữ liệu cần giải mã. Tránh tự động xóa khóa chỉ vì tên có chữ **test**.

**PKI** còn có nhiều lớp tài nguyên: CA, role, certificate đã cấp, private key người nhận, CRL và TTL. Xóa **PKI role** sẽ ngăn cấp chứng chỉ mới qua role đó, nhưng **không tự làm các chứng chỉ đã cấp hết hiệu lực**. Nếu cần thu hồi chứng chỉ đã phát hành, phải dùng quy trình revoke/CRL của PKI và hiểu việc client kiểm tra thu hồi. Không xóa root CA hoặc toàn bộ PKI mount như bước “dọn tệp tạm” thông thường.

**Auth mount** cũng có phạm vi riêng: vô hiệu hóa cả auth method như **approle/** có thể ảnh hưởng nhiều role và workload; dọn một secret ID hoặc một role cụ thể có phạm vi nhỏ hơn. Tách biệt cách dọn cấu hình engine với cách thu hồi credential đang được sử dụng.

### 7.5. Dừng container và volume

Với **Vault dev mode** Compose ở mục 3:

~~~bash
docker compose down
~~~

Lệnh này dừng/xóa container và network của Compose project. Vì dev server trong bài lưu trạng thái Vault trong bộ nhớ, dữ liệu lab bị mất khi tiến trình dev kết thúc. Tuy nhiên lệnh **không tự xóa**:

- File **compose.yaml**, policy HCL, file **.env** trên host.
- Token/credential đã được in vào terminal, copy sang clipboard hoặc ghi log.
- Các file truststore, certificate/private key do bài TLS khác tạo.
- Dữ liệu từ một **dịch vụ khác** hoặc volume được quản lý ngoài Compose project này.

Đối với Vault **non-dev** có named volume hoặc persistent storage, **docker compose down** thường vẫn giữ volume. Tùy project và lựa chọn dọn dẹp, **docker compose down -v** có thể xóa named volumes của project và làm mất dữ liệu bền vững; không dùng tùy chọn **-v** trên hệ thống có dữ liệu cần giữ. Nếu muốn xóa hoàn toàn một lab non-dev, phải kiểm tra tên Compose project, volume và backup trước khi chọn thao tác xóa.

**Không sử dụng** lệnh **vault secrets disable lab-kv** như bước mặc định cuối bài nếu mount **lab-kv/** còn chứa key của các bài khác. Lệnh đó loại bỏ *toàn bộ secrets engine tại mount*, không chỉ các key dưới **exercises/cleanup-008/**.

## 8. Quy trình dọn dẹp theo phạm vi đã xác minh

Một runbook tốt giúp người học trả lời được: *Tài nguyên nào do bài tạo? Những gì sẽ bị ảnh hưởng? Tôi sẽ kiểm tra điều gì sau thao tác?*

### 8.1. Bảng sở hữu tài nguyên

Trước khi xóa, ghi lại một bảng cho **chính phiên thực hành hiện tại**:

| Tài nguyên | Chủ sở hữu trong lab | Cách kiểm tra trước | Hành động phù hợp |
| --- | --- | --- | --- |
| **lab-kv/** | Có thể dùng chung nhiều bài | **vault secrets list -detailed** | Giữ mount nếu bài khác dùng |
| **exercises/cleanup-008/orders/config** | Bài này | **vault kv metadata get** | Soft delete hoặc metadata delete đúng key |
| **exercises/cleanup-008/orders/db** | Bài này | **vault kv metadata get** | Dọn riêng key |
| **exercises/cleanup-008/billing/config** | Bài này | **vault kv metadata get** | Dọn riêng key |
| Policy **cleanup-008-reader** | Bài này, nếu chỉ token của bài dùng | **vault policy read** | Xem xét xóa sau khi token đã revoke |
| Token **LAB_VAULT_TOKEN** | Phiên lab này | **vault token lookup** bằng token ấy | Revoke token, rồi bỏ biến khỏi shell |
| Vault dev container | Compose project của lab | **docker compose ps** | **docker compose down** khi kết thúc |
| File HCL/.env trên host | Thư mục lab | Danh sách file do chính mình tạo | Giữ làm tài liệu hoặc dọn theo mục tiêu |

Một mount có thể được chia sẻ, nhưng các logical key của bài đã được đặt trong prefix riêng. **Không tự suy rộng quyền sở hữu từ tên prefix**: nếu có worker khác đồng thời làm trên cùng key, cần phối hợp thay vì dọn khi họ đang sử dụng.

### 8.2. Thứ tự cleanup mẫu

1. **Ngừng client/test** đang đọc hoặc ghi secret của bài; nếu không, chúng có thể tạo lại version hoặc báo lỗi giữa chừng.
2. **Xác minh đúng Vault** qua Compose project, trạng thái server, địa chỉ và danh sách mount. Với Vault nhiều namespace, phải xác nhận namespace.
3. **Xem metadata và version** của từng key trong **exercises/cleanup-008/**; quyết định soft delete hay permanent delete theo mục tiêu.
4. **Dọn đúng các key của bài**. Không đưa cả **lab-kv/** hay **exercises/** vào thao tác disable rộng.
5. **Thu hồi token test**. Chỉ dọn policy/auth role khi chắc chắn không còn ứng dụng nào phụ thuộc.
6. **Đọc lại để xác minh** key/version không còn khả dụng theo kết quả mong đợi và các key ngoài phạm vi vẫn tồn tại.
7. **Dừng container** khi không cần Vault nữa; xử lý biến môi trường và file cục bộ theo chính sách của lab.

Một bài có yêu cầu giữ lịch sử KV để so sánh nên **không** xóa metadata ngay. Khi mục tiêu chỉ là khôi phục một bản trước đó, dùng version/undelete phù hợp thay vì xóa hết key.

### 8.3. Kiểm tra hậu trạng thái

Sau khi soft-delete hoặc metadata-delete một key, dùng CLI quản trị kiểm tra kết quả:

~~~bash
docker compose exec -T vault vault kv get -mount=lab-kv exercises/cleanup-008/orders/config
docker compose exec -T vault vault kv list -mount=lab-kv exercises/cleanup-008/orders/
docker compose exec -T vault vault secrets list -detailed
~~~

**Kết quả khác nhau tùy thao tác đã chọn:** Nếu chỉ soft-delete version mới nhất, metadata và version cũ có thể vẫn hiện diện; lệnh list có thể vẫn cho thấy tên key. Nếu metadata đã bị xóa hoàn toàn, tên key không còn như trước và không thể undelete. Điều cần kiểm tra là **đúng phạm vi mong đợi**, không phải mọi lệnh đều trả “not found”.

Để chắc chắn không ảnh hưởng ngoài phạm vi, trước khi dọn có thể tạo key giả **exercises/keep-me/config** (nếu bạn thực sự sở hữu nó) rồi xác minh key đó vẫn đọc được sau khi dọn **exercises/cleanup-008/**. Không tạo hoặc sửa key của người khác chỉ để kiểm tra cleanup.

Cuối cùng, bỏ biến token khỏi shell hiện tại:

~~~bash
# Bash / zsh
unset LAB_VAULT_TOKEN
~~~

~~~powershell
# PowerShell
Remove-Item Env:LAB_VAULT_TOKEN
~~~

Thao tác này chỉ xóa biến trong **shell hiện tại**. Nó không xóa credential từng được sao chép vào file, history, log, clipboard hoặc process đã kế thừa biến trước đó. Nếu phát hiện đã dùng token thật trong log, phải thu hồi/rotate token và xử lý bản ghi theo quy trình sự cố, không coi **unset** là đủ.

## 9. Kiểm thử tích hợp và phòng ngừa chạy nhầm môi trường

### 9.1. Test fixture phải tự tạo, tự dọn

Trong CI, ưu tiên một Vault dev tạm thời bằng **Testcontainers VaultContainer** hoặc container riêng cho mỗi test suite. Mỗi run nên thực hiện:

~~~mermaid
flowchart LR
    Start["Bắt đầu suite"] --> Vault["Tạo Vault test<br/>host/port động"]
    Vault --> Seed["Bootstrap ci-kv<br/>dữ liệu giả"]
    Seed --> Policy["Cấp policy + token test"]
    Policy --> Execute["VaultTemplate read<br/>negative permissions"]
    Execute --> Revoke["Revoke token<br/>nếu cần"]
    Revoke --> Stop["Dọn container<br/>và fixture test"]
~~~

Không dùng URL cố định của Vault trên máy lập trình viên làm fallback cho test. Khi test suite thiếu endpoint do container cấp, nó nên **thất bại sớm** thay vì kết nối đến Vault bên ngoài. Dữ liệu test không phụ thuộc vào key, mount hoặc token được tạo thủ công từ phiên học trước.

**Kiểm thử quyền tối thiểu:** token chỉ đọc Orders phải đọc được Orders, không ghi được Orders và không đọc được Billing. Kiểm thử âm bằng root token sẽ không phát hiện đúng lỗi policy.

### 9.2. Checklist kiểm thử có thể tự động hóa

| Ca test | Chuẩn bị | Kỳ vọng |
| --- | --- | --- |
| Seed độc lập | Khởi tạo mount **ci-kv/** và key tổng hợp | Chạy lặp lại trên Vault mới vẫn có dữ liệu dự kiến |
| Token reader | Policy read đúng API **data/** | **VaultTemplate** đọc được key |
| Truy cập ngoài quyền | Đọc Billing, ghi Orders bằng token reader | **403** hoặc lỗi quyền tương ứng; không sinh version mới |
| KV v2 version | Put rồi patch một field | Version mới, các field giữ/đổi như kỳ vọng |
| Soft delete | Xóa version cụ thể trong fixture | Version bị đánh dấu xóa, metadata vẫn còn |
| Metadata delete | Xóa đúng một key do test tạo | Key không còn, key đối chứng vẫn nguyên |
| Token revoke | Thu hồi token test | Request tiếp theo không còn được chấp nhận |
| Lỗi kết nối | Dừng Vault test | Phân loại connection error, retry có giới hạn |
| TLS | Chạy test chuyên biệt với CA/SAN khác nhau | CA hoặc hostname sai bị từ chối |
| Transit/PKI | Seed engine và quyền test riêng | Chỉ thao tác được phép thành công |

Đối với Transit, **ciphertext** giả có thể dùng để kiểm tra encrypt/decrypt khi role cho phép, nhưng test không nên xóa khóa còn cần để giải mã dữ liệu khác. Với PKI, test nên dùng CA/role riêng, tránh dùng CA production hoặc xuất private key vào log.

### 9.3. Ngăn profile production trỏ về lab

Một profile production hợp lệ phải có những điều kiện cơ bản:

- **HTTPS** với CA và hostname xác minh được; không có chế độ bỏ qua kiểm tra certificate.
- Endpoint nằm trong nhóm địa chỉ Vault production được quản trị.
- Danh tính workload được cấp riêng, không dựa trên **LAB_VAULT_TOKEN** hay **dev-root-only**.
- Mount/key/role và namespace đúng môi trường; không trỏ tới **lab-kv/** hay key **exercises/cleanup-008/**.
- Secret không tồn tại hoặc token không được phép sẽ gây lỗi có kiểm soát, **không fallback sang local**.

Kiểm tra startup trong Spring Boot có thể xác minh scheme, host, mount và auth mode đã cấu hình. Tuy vậy, profile name không phải ranh giới bảo mật duy nhất: policy Vault, TLS, mạng và workload identity vẫn phải kiểm soát độc lập.

## 10. Chẩn đoán lỗi thường gặp

| Hiện tượng | Nguyên nhân có khả năng | Cách kiểm tra |
| --- | --- | --- |
| Java **Missing LAB_VAULT_TOKEN** | Chưa cấp token cho process, sai tên env | Cấu hình IDE/test runner, không in giá trị token |
| **403** khi đọc Orders | Token hết hạn, policy thiếu **data/** hoặc dùng token sai | **vault token lookup**, **vault policy read**, path API |
| **403** khi Billing | Đúng kỳ vọng với token Orders | Xác nhận test âm đi đúng key |
| **404** / kết quả null | Key chưa được seed, bị xóa, sai mount/version | **vault kv metadata get** và **kv get** bằng admin lab |
| Version tăng sau khi chạy lại | **kv put/patch** được gọi thêm lần nữa | Metadata versions, thứ tự seed |
| Key “đã xóa” vẫn xuất hiện trong list | Chỉ soft-delete version | Xem metadata; cân nhắc mục tiêu cleanup |
| **kv undelete** không khôi phục | Version bị destroy hoặc metadata đã bị xóa | Xác định thao tác xóa đã dùng |
| Container dừng nhưng file/token vẫn còn | **compose down** không dọn host environment/file | Kiểm tra thư mục lab, CI log, shell session |
| CI đọc dữ liệu lạ | Test trỏ nhầm Vault local/shared | Endpoint được inject, Compose project, namespace |
| **PKIX** hoặc hostname mismatch | JVM chưa tin CA hoặc SAN không khớp URL | Truststore, chain, hostname, TLS scheme |
| **503** từ Vault | Server sealed/unavailable | Vault status/health, cơ chế unseal |
| Transit/PKI bị từ chối | Thiếu quyền đúng endpoint hoặc role hạn chế dữ liệu | Policy encrypt/decrypt, PKI issue role |

**Không retry vô hạn** với lỗi 403, 404 do key thiếu hoặc lỗi cấu hình truststore. Với lỗi mạng/5xx có thể retry có giới hạn, backoff và quan sát. Các thao tác như cấp chứng chỉ PKI, ghi KV hoặc tạo token không phải lúc nào cũng an toàn khi tự động gửi lại sau timeout mà không biết request đầu đã thành công hay chưa.

## 11. Bài tập cuối bài

**Bài A — Tạo dữ liệu tổng hợp có ý nghĩa.** Thiết kế ba key riêng cho Orders, Billing và một worker khác. Dùng **example.invalid**, user demo và token giả. Viết hai phép thử khẳng định dữ liệu có cấu trúc hợp lệ và không cần dịch vụ ngoài lab.

**Bài B — Cấu hình ngoài mã nguồn.** Tạo profile local gồm URI, mount và logical key; đưa token vào môi trường của process Java. Dùng **VaultTemplate** để đọc một key. Thử bỏ biến token và xác nhận ứng dụng báo thiếu credential thay vì tự dùng root token.

**Bài C — Quyền tối thiểu.** Tạo token read-only cho Orders, thử đọc Billing và ghi Orders. Kết quả mong đợi là bị từ chối. Giải thích vì sao tên key **exercises/cleanup-008/** chưa đủ để tạo ranh giới quyền nếu không có policy đúng API path.

**Bài D — Ba cách xóa của KV v2.** Trên một key giả hoàn toàn thuộc quyền sở hữu của bạn, so sánh soft delete, undelete và metadata delete. Ghi lại ảnh hưởng lên **kv get**, **kv list**, metadata và khả năng phục hồi. Không thực hiện thử nghiệm destructive trên mount/key dùng chung.

**Bài E — Dọn token và client.** Dùng token lab kiểm tra TTL, revoke chính token đó, sau đó thử đọc lại. Phân biệt thu hồi client token với việc xóa một KV secret; giải thích trường hợp AppRole secret ID đã dùng nhưng client token vẫn còn hiệu lực.

**Bài F — Ranh giới Docker.** Dừng Vault dev bằng **docker compose down**. Liệt kê thứ gì mất trong Vault dev, thứ gì còn lại trên host và sự khác biệt nếu Vault được cấu hình storage bền vững trên named volume.

**Bài G — Mở rộng Transit/PKI.** Giả sử ciphertext Transit và chứng chỉ PKI được cấp cho một ứng dụng thật. Hãy giải thích vì sao xóa Transit key hoặc root CA không phải thao tác dọn fixture tương đương xóa một key KV giả.

## 12. Checklist hoàn thành

- [ ] Dữ liệu mẫu được **tạo mới cho lab**, không sao chép bản ghi hoặc credential thật.
- [ ] Có mount KV v2 và prefix logical key riêng để nhận diện dữ liệu của bài.
- [ ] Đã seed, đọc và xem metadata/version bằng Vault CLI; hiểu chạy lại **kv put** tạo version mới.
- [ ] Các thông số URI/mount/key được đưa ra ngoài code, token được cấp theo môi trường chạy.
- [ ] Java **VaultTemplate** đọc bằng token có policy tối thiểu; không log nội dung secret.
- [ ] Biết phân biệt **data/** và **metadata/** trong policy của KV v2.
- [ ] Hiểu **soft delete**, **destroy version**, **metadata delete** và **secrets disable** có phạm vi khác nhau.
- [ ] Trước khi dọn, đã xác minh Compose project, Vault endpoint, namespace, mount, key và quyền sở hữu tài nguyên.
- [ ] Đã thu hồi token lab khi kết thúc và kiểm tra còn file/env/log nào có credential.
- [ ] Biết **docker compose down** khác với xóa named volume hoặc xóa file trên host.
- [ ] Không dùng cách dọn KV để suy luận sai về token/lease, Transit key hoặc PKI CA.
- [ ] CI/test suite có fixture độc lập và không tự fallback sang Vault của staging/production.

**Kết luận học tập:** Một môi trường Spring Vault tốt cần dữ liệu giả có thể tái tạo, cấu hình được cung cấp lúc chạy và một phạm vi dọn dẹp được mô tả rõ. Khi mỗi lệnh biết chính xác **Vault nào, mount nào, key/version/token nào** chịu tác động, người học có thể thực hành KV, token/lease, Transit và PKI mà không làm lẫn dữ liệu hay quyền truy cập giữa các workload và môi trường.
