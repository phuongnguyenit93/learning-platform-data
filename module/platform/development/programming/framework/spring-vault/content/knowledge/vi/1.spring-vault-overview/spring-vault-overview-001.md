# Spring Vault là gì và bài toán quản lý bí mật (secret)

> **Chương:** Bản đồ Spring Vault  
> **Phạm vi:** Hiểu vì sao ứng dụng Java cần quản lý bí mật tập trung, vai trò của HashiCorp Vault và Spring Vault, cùng bức tranh tổng thể về xác thực workload, phân quyền, KV, token/lease, Transit và PKI.

## Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt **secret**, cấu hình thông thường và danh tính của một workload.
2. Giải thích những rủi ro khi để mật khẩu, API key hoặc chứng chỉ trong mã nguồn, file cấu hình và biến môi trường không được quản trị.
3. Mô tả ranh giới trách nhiệm giữa **HashiCorp Vault**, **Spring Vault** và **Spring Cloud Vault**.
4. Diễn giải luồng một ứng dụng Java xác thực với Vault, nhận token, được policy cho phép đọc secret và xử lý việc hết hạn.
5. Chọn đúng hướng tiếp cận ban đầu cho KV secrets, dynamic secrets, Transit encryption và PKI.
6. Đọc một ví dụ sử dụng `VaultOperations`/`VaultTemplate` và nhận diện các điểm cần bổ sung trước khi triển khai thực tế.

## 1. Vấn đề: secret trong ứng dụng Java được quản lý thế nào?

Giả sử dịch vụ `order-service` cần kết nối PostgreSQL, gọi cổng thanh toán và xác thực với một dịch vụ nội bộ. Một cấu hình ngây thơ có thể trông như sau:

~~~yaml
# application.yml — ví dụ KHÔNG nên dùng trong hệ thống thực tế
payment:
  api-key: "example-secret-in-repository"
spring:
  datasource:
    username: "order_app"
    password: "example-db-password"
~~~

Mã ví dụ không chứa khóa thật, nhưng cách tổ chức này tạo ra hàng loạt câu hỏi khó:

- **Ai được đọc?** Người có quyền truy cập repository, bản build, log của pipeline hoặc môi trường triển khai có thể nhìn thấy giá trị này.
- **Đổi khóa ở đâu?** Nếu một khóa được dùng ở nhiều service, việc thay thế đòi hỏi tìm đủ nơi đã sao chép và triển khai lại một cách có kiểm soát.
- **Thu hồi bằng cách nào?** Khi khóa bị lộ, không dễ xác định những bản sao còn hoạt động hoặc ứng dụng nào đang dùng khóa cũ.
- **Ai đã truy cập?** Một file cấu hình thường không cung cấp nhật ký kiểm toán tập trung theo danh tính workload.
- **Phân quyền ra sao?** Hai ứng dụng vô tình dùng chung thông tin đăng nhập có thể nhận nhiều quyền hơn nhu cầu thực tế.
- **Hết hạn và gia hạn thế nào?** Một số thông tin xác thực có TTL hoặc cần thay đổi theo chu kỳ, nhưng mã ứng dụng không theo dõi vòng đời đó.

**Secret** là dữ liệu phải được bảo vệ khi truy cập, lưu trữ và sử dụng: mật khẩu cơ sở dữ liệu, API key, access token, private key, certificate có private key đi kèm, khóa ký hoặc khóa mã hóa. Trong khi đó, tên service, timeout hay tên môi trường thường là **cấu hình thông thường**. URL nội bộ hoặc tên tài khoản đôi khi cũng cần hạn chế tiết lộ theo chính sách của tổ chức, nhưng không mặc nhiên được xử lý như private key.

Một biến môi trường như `PAYMENT_API_KEY` có thể tốt hơn việc commit khóa vào Git, song **biến môi trường tự nó không giải quyết** việc cấp phát, chia sẻ, kiểm toán, giới hạn quyền, luân chuyển, thu hồi hoặc ngăn các tiến trình/người dùng có quyền phù hợp đọc được giá trị. Kubernetes Secret cũng cần kiểm soát RBAC, mã hóa lưu trữ, truy cập ở node và quy trình luân chuyển riêng. Những cơ chế này có thể cùng tồn tại với Vault.

## 2. HashiCorp Vault và Spring Vault là gì?

**HashiCorp Vault** là dịch vụ quản lý bí mật và các thao tác mật mã theo danh tính. Vault xác thực chủ thể truy cập, áp dụng **policy** trên đường dẫn/API tương ứng, quản lý các secrets engines và hỗ trợ audit. Tùy engine, Vault có thể lưu secret tĩnh, phát hành thông tin xác thực động, thực hiện phép mã hóa hoặc cấp chứng chỉ.

**Spring Vault** là thư viện Java trong hệ sinh thái Spring giúp **ứng dụng giao tiếp với Vault** bằng các API Spring, đặc biệt `VaultTemplate`/`VaultOperations`, cơ chế xác thực `ClientAuthentication` và quản lý phiên `SessionManager`. Thư viện này **không chạy thay Vault server**, không quyết định policy và không biến secret thành an toàn chỉ vì đã đọc qua một API Java.

**Spring Cloud Vault** tích hợp Vault với hệ thống cấu hình của ứng dụng Spring Boot/Spring Cloud, cho phép nạp các giá trị từ Vault vào `Environment` và cấu hình ứng dụng theo cơ chế của phiên bản Spring đang dùng. Spring Vault phù hợp khi cần thao tác trực tiếp bằng Java; Spring Cloud Vault thuận tiện khi mục tiêu chính là nguồn cấu hình. Một dự án có thể dùng cả hai, nhưng phải xác định rõ vòng đời dữ liệu và nơi bí mật đi vào bộ nhớ ứng dụng.

| Thành phần | Trách nhiệm chính | Ví dụ |
|---|---|---|
| Vault server | Xác thực, phân quyền, secrets engines, audit, TTL/thu hồi | Chỉ cho `order-service` đọc secret dành cho chính nó |
| Spring Vault | API Java, client, quản lý token/phiên, thao tác Vault | `vaultOperations.opsForKeyValue(...)` |
| Spring Cloud Vault | Tích hợp secret vào nguồn cấu hình Spring | Nạp cấu hình khởi động của ứng dụng từ Vault |
| Ứng dụng Java | Quyết định lúc nào lấy, dùng, xóa tham chiếu hoặc làm mới secret | Dùng credential để tạo kết nối DB, xử lý lỗi hết hạn |
| Nền tảng triển khai | Cấp **danh tính ban đầu** cho workload và kết nối an toàn | Kubernetes ServiceAccount, IAM, TLS, mạng riêng |

Lợi ích của Vault đến từ **hệ thống chính sách và vận hành hoàn chỉnh**, không chỉ từ việc chuyển chuỗi mật khẩu ra khỏi `application.yml`.

## 3. Bức tranh kiến trúc: ứng dụng lấy secret ở thời điểm chạy

~~~mermaid
sequenceDiagram
    autonumber
    participant A as Java order-service
    participant I as Nguồn danh tính workload
    participant V as HashiCorp Vault
    participant P as Policy / secrets engine
    participant D as Dịch vụ đích
    A->>I: Nhận bằng chứng danh tính<br/>(ví dụ ServiceAccount JWT/IAM)
    A->>V: Login bằng phương thức auth phù hợp
    V->>I: Kiểm tra bằng chứng (tùy phương thức)
    V-->>A: Vault token có TTL và policies
    A->>V: Đọc KV hoặc yêu cầu credential/crypto
    V->>P: Kiểm tra path + capability
    P-->>V: Cho phép / từ chối
    V-->>A: Kết quả hoặc lỗi
    A->>D: Sử dụng secret đúng mục đích
    Note over A,V: Theo dõi hết hạn, đổi khóa,<br/>thu hồi và audit theo nhu cầu
~~~

Diễn giải theo thứ tự:

1. **Bootstrap danh tính:** workload cần một bằng chứng có thể tin cậy để bắt đầu. Ví dụ pod Kubernetes có ServiceAccount token, hoặc workload trên cloud có thông tin danh tính IAM. Không nên thay bài toán “lấy mật khẩu” bằng một root token Vault cố định nằm trong Git.
2. **Đăng nhập:** phương thức xác thực (auth method) của Vault kiểm chứng bằng chứng đó và phát hành token có policies, TTL và những thuộc tính liên quan.
3. **Ủy quyền:** mỗi yêu cầu đến một **path** của Vault được đối chiếu với quyền như `read`, `create`, `update`, `list` hoặc `delete`. Đăng nhập thành công **không đồng nghĩa** được đọc mọi secret.
4. **Sử dụng:** ứng dụng chỉ nhận dữ liệu cần thiết; dữ liệu sau khi đọc vẫn phải được bảo vệ trong RAM, log, exception và hệ thống đích.
5. **Vòng đời:** token hoặc credential động có thể hết hạn, được gia hạn hoặc bị thu hồi. Ứng dụng và hạ tầng phải xử lý tác động đến kết nối đang tồn tại.

### Bài toán “bí mật để lấy bí mật”

Nếu phải đưa một Vault token có quyền rộng vào môi trường để đọc các secret khác, vấn đề ban đầu chỉ bị dời chỗ. Thiết kế tốt sử dụng **workload identity**: ứng dụng chứng minh mình là đúng workload bằng cơ chế sẵn có trong hạ tầng; Vault ánh xạ danh tính đó tới role và policy tối thiểu.

Không có cách bootstrap chung cho mọi môi trường:

| Môi trường | Hướng xác thực thường gặp | Điều cần kiểm soát |
|---|---|---|
| Kubernetes | Kubernetes auth với ServiceAccount token | Ràng buộc role với ServiceAccount, namespace, audience và thời hạn token thích hợp |
| AWS/cloud | Auth theo danh tính máy hoặc IAM/JWT tùy nền tảng | Trust relationship, phạm vi role và quyền của workload |
| Máy chủ/batch ngoài cloud | AppRole hoặc phương thức định danh máy phù hợp | Bảo vệ và vận chuyển `SecretId`; TTL, số lượt dùng, response wrapping nếu áp dụng |
| Máy phát triển cục bộ | Token giới hạn quyền, thời hạn ngắn phục vụ thử nghiệm | Không commit token, không dùng root token cho ứng dụng |

Những lựa chọn này **không tương đương** về mô hình tin cậy; cần cấu hình và kiểm tra auth method tương ứng ở Vault server.

## 4. Bảy khái niệm cốt lõi phải nắm

### 4.1. Auth method khác với secrets engine

- **Auth method** trả lời: *“Bạn là ai, và có được nhận Vault token không?”* Ví dụ Kubernetes, AppRole, AWS IAM hoặc JWT.
- **Secrets engine** trả lời: *“Bạn được yêu cầu dữ liệu hay chức năng gì?”* Ví dụ KV, Database, Transit hoặc PKI.
- **Policy** trả lời: *“Với token này, bạn có quyền gọi hành động đó ở path ấy không?”*

Ví dụ, một pod đăng nhập qua `auth/kubernetes/login`, nhận policy `orders-read`, rồi đọc secret tại `secret/data/apps/orders`. Path auth và path KV phục vụ hai nhiệm vụ khác nhau.

### 4.2. Mount path, secret path và API path

Một secrets engine được **mount** tại đường dẫn cấu hình, ví dụ `secret/`. Bên trong mount có key logic như `apps/orders`. Với **KV v2**, HTTP API dùng đoạn `data/` khi đọc/ghi dữ liệu và `metadata/` khi liệt kê/quản lý metadata:

| Mức nhìn | Ví dụ | Ý nghĩa |
|---|---|---|
| Mount | `secret/` | Engine KV v2 do quản trị viên bật |
| Key logic | `apps/orders` | Vị trí của secret trong engine |
| Đọc dữ liệu qua HTTP API | `secret/data/apps/orders` | Path mà policy `read` cần bao phủ |
| Liệt kê qua HTTP API | `secret/metadata/apps/` | Path cần capability `list` nếu muốn liệt kê |
| API cấp cao của Spring Vault | `opsForKeyValue("secret", KV_2).get("apps/orders")` | Thư viện xử lý phần khác biệt đường dẫn KV v2 |

Không nên ghép bừa `data/` vào đối số `get` của API KV cấp cao, vì dễ thành sai path. Với KV v1, cách gọi API và ý nghĩa version khác KV v2.

### 4.3. Policy và nguyên tắc quyền tối thiểu

Ví dụ HCL cho một ứng dụng **chỉ đọc** đúng một KV v2 secret:

~~~hcl
# Mount: secret/ (KV v2)
# Key:   apps/orders
path "secret/data/apps/orders" {
  capabilities = ["read"]
}
~~~

Policy trên không cấp quyền ghi, xóa hay liệt kê. Nếu ứng dụng cần đọc nhiều key, hãy mở đúng các nhánh cần thiết theo môi trường và nghiệp vụ. Quyền `list` với KV v2 nằm trên `metadata/` và có thể làm lộ **tên** các secret, nên không thêm theo thói quen. Một số thao tác tự phát hiện mount/version của client cũng liên quan endpoint `sys/internal/ui/mounts/...`: cần kiểm tra hành vi và quyền theo bản Vault/Spring Vault thực tế.

Lưu ý policy kiểm soát **API path**, không kiểm soát được cách ứng dụng sử dụng dữ liệu *sau khi* đã nhận plaintext.

### 4.4. Token và session

**Vault token** là thông tin xác thực mà client gửi trong các yêu cầu tiếp theo. Nó được gắn với policy và các giới hạn về thời gian/quyền. **SessionManager** của Spring Vault quản lý việc lấy và tái sử dụng token; `LifecycleAwareSessionManager` có khả năng lên lịch gia hạn token khi đủ điều kiện và thu hồi login token khi đóng phiên. `SimpleSessionManager` không tự gia hạn/thu hồi theo vòng đời đó.

Không nên suy luận rằng “dùng Spring Vault” thì mọi token đều tự làm mới vô thời hạn: khả năng gia hạn còn phụ thuộc loại token, auth method, TTL tối đa và cấu hình server. Token có thể bị revoke bất ngờ, khi đó phải xác thực lại hoặc xử lý lỗi phù hợp.

### 4.5. Lease, TTL và credential động

Một **lease** biểu diễn vòng đời của secret có thể được Vault cấp phát động, ví dụ database username/password được engine Database tạo cho một ứng dụng. Lease có ID, TTL và hành vi gia hạn/thu hồi theo khả năng engine. Khi lease hết hạn hoặc bị thu hồi, credential có thể không còn hợp lệ.

Phân biệt ba trường hợp:

| Trường hợp | Có thời hạn ở đâu? | Hệ quả |
|---|---|---|
| KV secret tĩnh | Thường không có lease tự động cho giá trị KV | Đổi khóa/rotation theo quy trình riêng; version KV v2 **không** phải TTL credential |
| Vault login token | Token có TTL và chính sách gia hạn riêng | Client có thể cần gia hạn hoặc đăng nhập lại |
| Database credential động | Lease và TTL của credential do engine phát hành | Kết nối mới cần thông tin mới; connection pool phải tính đến rotation |

**Token TTL** và **secret lease TTL** là hai đồng hồ khác nhau. Làm mới token không mặc nhiên kéo dài tuổi thọ credential Database đã cấp; làm mới credential cũng không tự chuyển kết nối đang sử dụng sang tài khoản mới.

### 4.6. Audit

Vault có audit devices để ghi nhận yêu cầu và phản hồi phục vụ truy vết. Việc audit phụ thuộc cấu hình phía Vault, hạ tầng lưu log và quyền truy cập log. Không vì có audit mà ứng dụng được phép in token, payload secret hoặc private key ra log. Theo dõi kết quả đọc thất bại, số lần xác thực, tỷ lệ lỗi và tình trạng gia hạn bằng **metadata phù hợp**, giới hạn thông tin nhạy cảm.

### 4.7. TLS và ranh giới tin cậy

Ứng dụng nên kết nối Vault bằng **HTTPS có kiểm tra chứng chỉ**; triển khai CA trust đúng, không tắt kiểm tra hostname/chain để “chạy được”. Vault có thể lưu dữ liệu mã hóa, nhưng khi một ứng dụng được phép đọc KV secret, plaintext vẫn tồn tại ở phía ứng dụng. Vault không thay thế việc cô lập tiến trình, bảo vệ bộ nhớ, hạn chế log và giảm thời gian tồn tại của thông tin nhạy cảm.

## 5. Làm việc với Spring Vault từ Java

`VaultTemplate` là triển khai trung tâm của interface `VaultOperations`. Nó hỗ trợ read/write/delete và các API theo secrets engine; `ClientAuthentication` đăng nhập, `SessionManager` duy trì phiên. Trong ứng dụng Spring, thường đăng ký bean một lần rồi inject qua interface `VaultOperations`.

Ví dụ tối thiểu dưới đây **chỉ minh họa cách kết nối cho môi trường học tập**, giả sử Vault đã chạy tại `https://vault.internal.example:8200` và token thử nghiệm đã có quyền đọc phù hợp. Ở production, ưu tiên cấu hình auth theo workload và HTTPS với truststore đúng chuẩn:

~~~java
import java.util.Objects;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.vault.authentication.TokenAuthentication;
import org.springframework.vault.client.VaultEndpoint;
import org.springframework.vault.core.VaultOperations;
import org.springframework.vault.core.VaultTemplate;

@Configuration
class VaultConfig {

    @Bean
    VaultOperations vaultOperations() {
        // Token ngắn hạn phục vụ demo; không đưa token vào Git.
        String token = Objects.requireNonNull(
            System.getenv("VAULT_TOKEN"), "VAULT_TOKEN is required");

        return new VaultTemplate(
            VaultEndpoint.create("vault.internal.example", 8200),
            new TokenAuthentication(token));
    }
}
~~~

Với KV v2 đã mount tại `secret/` và key logic `apps/orders`, ứng dụng có thể đọc như sau:

~~~java
import org.springframework.stereotype.Service;
import org.springframework.vault.core.VaultKeyValueOperations;
import org.springframework.vault.core.VaultKeyValueOperationsSupport.KeyValueBackend;
import org.springframework.vault.core.VaultOperations;
import org.springframework.vault.support.VaultResponse;

@Service
public class PaymentSecretReader {

    private final VaultKeyValueOperations secrets;

    public PaymentSecretReader(VaultOperations vault) {
        this.secrets = vault.opsForKeyValue("secret", KeyValueBackend.KV_2);
    }

    public String getPaymentApiKey() {
        VaultResponse response = secrets.get("apps/orders");
        if (response == null) {
            throw new IllegalStateException("Required Vault secret is missing");
        }

        Object value = response.getRequiredData().get("payment-api-key");
        if (!(value instanceof String) || ((String) value).isBlank()) {
            throw new IllegalStateException("Required secret field is missing");
        }
        return (String) value;
    }
}
~~~

Để ví dụ hoạt động, phía Vault phải **tồn tại** KV v2 engine, key tương ứng, role/token đủ quyền và kết nối TLS được tin cậy. Spring Vault không tự tạo secret hoặc policy từ lời gọi `get`. Mã trên xử lý secret thiếu nhưng chưa trình bày vòng đời refresh, retry, cache hay quy trình sử dụng key ở hệ thống thanh toán; những phần đó là quyết định thiết kế riêng.

> **Vì sao dùng `opsForKeyValue`?** API này nhận mount và phiên bản KV, giúp code biểu diễn key logic. Nếu gọi `vaultOperations.read("secret/data/apps/orders")` trực tiếp, người viết phải hiểu và xử lý cấu trúc response lồng `data` của KV v2; sự nhầm lẫn rất phổ biến khi chuyển từ KV v1 sang v2.

### Khi nào dùng `VaultTemplate`, khi nào dùng cấu hình tự động?

- **Đọc/ghi theo nghiệp vụ trong runtime:** dùng `VaultOperations` và API chuyên biệt như `opsForKeyValue`, Transit hoặc PKI; kiểm soát rõ chỗ đọc dữ liệu, lỗi và vòng đời.
- **Nạp cấu hình khi ứng dụng khởi động:** cân nhắc Spring Cloud Vault cùng cơ chế import/configuration tương thích Spring Boot. Phải xác định chiến lược refresh khi secret đổi.
- **Thao tác đặc thù ít được abstraction hỗ trợ:** sử dụng client API phù hợp với phiên bản Spring Vault, nhưng vẫn giữ xác thực, TLS, timeout và giới hạn quyền.

Không nên dùng Vault như cơ sở dữ liệu nghiệp vụ để lưu record có tần suất ghi/đọc lớn. Secret store được thiết kế cho quản lý bí mật và thao tác mật mã theo chính sách; dữ liệu giao dịch vẫn thuộc hệ quản trị dữ liệu phù hợp.

## 6. Các nhóm chức năng quan trọng trong hệ sinh thái Vault

### 6.1. KV: secret tĩnh có tổ chức

KV thích hợp cho API key của bên thứ ba, client secret hoặc cấu hình nhạy cảm được cấp trước. KV v1 chỉ giữ giá trị hiện tại; KV v2 hỗ trợ lịch sử phiên bản, metadata và các hành vi xóa/khôi phục theo phiên bản. **Có version không có nghĩa là key tự luân chuyển**: cần quy trình phát hành khóa mới, cập nhật ứng dụng phụ thuộc và thu hồi khóa cũ ở hệ thống gốc.

Ví dụ phân tách:

~~~text
secret/                       (mount KV v2)
  apps/orders                 (key logic của order-service)
  apps/inventory              (key logic của inventory-service)
  shared/payment-gateway      (nếu thật sự có nhu cầu chia sẻ)
~~~

Nên tách không gian theo môi trường, ứng dụng và quyền. Một service không nên được phép đọc toàn bộ `secret/*` chỉ vì “các bí mật đều ở cùng Vault”.

### 6.2. Dynamic secrets: giảm vòng đời credential

Với Database secrets engine, Vault có thể cấp username/password theo role với TTL. Cách này có thể giảm việc dùng chung một mật khẩu database dài hạn. Tuy nhiên, database vẫn cần cấu hình role/permissions đúng; application connection pool cần cơ chế tái tạo kết nối khi credential đổi. Spring Vault cung cấp cách tương tác và các công cụ hỗ trợ lifecycle, nhưng không thể tự bảo đảm không có gián đoạn giao dịch khi secret hết hạn.

### 6.3. Transit: cryptography as a service

**Transit** nhận yêu cầu mã hóa/giải mã, ký/xác minh hoặc các thao tác mật mã tương ứng; khóa được quản lý phía Vault. Điểm quan trọng: Transit **không phải nơi lưu trữ plaintext/ciphertext nghiệp vụ**. Chẳng hạn ứng dụng gửi plaintext cần mã hóa qua TLS, nhận ciphertext rồi tự lưu ciphertext vào database của mình.

~~~mermaid
flowchart LR
    A["Ứng dụng Java<br/>có dữ liệu cần bảo vệ"] -->|Yêu cầu mã hóa qua TLS| T["Vault Transit<br/>quản lý khóa"]
    T -->|Trả ciphertext| A
    A -->|Lưu ciphertext| D[("Database ứng dụng")]
    D -->|Đọc ciphertext| A
    A -->|Yêu cầu giải mã khi được cấp quyền| T
    T -->|Trả plaintext| A
~~~

Chính sách nên tách quyền `transit/encrypt/<key>` và `transit/decrypt/<key>` nếu nghiệp vụ chỉ cần một chiều. Transit giảm nhu cầu đưa encryption key vào app, nhưng Vault vẫn nhìn thấy dữ liệu đầu vào theo giao thức dịch vụ; TLS, chính sách và hạn chế log vẫn bắt buộc.

### 6.4. PKI: phát hành chứng chỉ ngắn hạn

**PKI secrets engine** có thể phát hành chứng chỉ X.509 theo role và giới hạn tên miền, TTL, loại chứng chỉ. Ví dụ service được phát hành chứng chỉ client để dùng mTLS; khi gần hết hạn cần cấp mới, cập nhật TLS context/keystore và quản lý kết nối cũ. PKI không chỉ là “đọc một file certificate”: quy trình cấp, gia hạn, revoke và phân phối chứng chỉ phải phối hợp với hệ thống sử dụng TLS.

### Bản đồ lựa chọn nhanh

| Yêu cầu của ứng dụng | Chức năng Vault phù hợp | Thao tác ứng dụng cần quản lý |
|---|---|---|
Đọc một API key cố định | KV v2 | Phiên bản, rotation, cache, thiếu key |
| Cấp tài khoản DB theo từng workload | Database dynamic secrets | Lease, connection pool, TTL |
| Mã hóa dữ liệu trước khi lưu DB | Transit | Chính sách encrypt/decrypt, ciphertext, timeout |
| Cấp certificate cho mTLS | PKI | CSR/key handling, TTL, thay chứng chỉ |
| Cho workload đăng nhập an toàn | Auth method + policy | Bootstrap identity, token/session, revoke |

## 7. Những lỗi triển khai thường gặp và nguyên tắc xử lý

| Tình huống | Nguyên nhân thường gặp | Hướng xử lý |
|---|---|---|
| HTTP 403 / permission denied | Policy thiếu capability; dùng sai KV v2 path; role nhận sai policies | Kiểm tra token role và path thực, quyền `read` trên `secret/data/...`; không tự nới rộng `*` |
| HTTP 404 hoặc secret rỗng | Key không tồn tại, mount khác, KV v1/v2 nhầm, version đã xóa | Kiểm tra mount, key logic và version; phân biệt với 403 |
| Token hết hạn / bị revoke | TTL, không renewable, session config, role bị thay đổi | Thiết kế đăng nhập lại/gia hạn hợp lệ; theo dõi hết hạn; tránh token hard-code |
| Credential DB không còn dùng được | Lease hết hạn hoặc revoke; pool còn connection cũ | Làm mới credential và pool có kiểm soát, kiểm thử rollover |
| Timeout, 429 hoặc lỗi 5xx tạm thời | Mạng, Vault bận, điều kiện rate-limit/HA | Timeout hợp lý, retry có backoff + jitter và giới hạn; phân loại thao tác an toàn trước khi retry |
| TLS handshake lỗi | CA/hostname/certificate không khớp | Sửa truststore/chuỗi chứng chỉ, không tắt xác minh TLS |
| Ứng dụng chạy nhưng secret lộ vào log | Log full config, request, exception hoặc debug HTTP | Redact, giảm log mức nhạy cảm, hạn chế quyền đọc log |

**Không chuyển mọi lỗi Vault thành “secret không tồn tại”.** `403` là tín hiệu bị từ chối; `404` thường liên quan resource/path; timeout và `5xx` là sự cố liên lạc/dịch vụ; các trường hợp cần phản ứng khác nhau. Với hệ thống phụ thuộc secret để xác thực, cần xác định rõ **fail closed** khi không thể lấy thông tin bắt buộc, thay vì âm thầm dùng giá trị mặc định không an toàn.

Đừng đặt chu kỳ gọi Vault trong mọi request người dùng chỉ vì đã có `VaultTemplate`. Cần cân nhắc cache trong bộ nhớ với TTL phù hợp, tác động của rotation, chế độ khởi động khi Vault không sẵn sàng và giới hạn truy cập. Cache secret quá lâu có thể làm chậm revoke; không cache có thể làm hệ thống dễ bị ảnh hưởng bởi độ trễ và outage.

## 8. Một kịch bản thiết kế từ đầu đến cuối

Yêu cầu: `order-service` chạy trên Kubernetes, dùng API key tĩnh của cổng thanh toán và cần mã hóa một trường nhạy cảm trong cơ sở dữ liệu.

1. **Thiết lập quyền phía Vault:** bật KV v2 tại mount phù hợp; lưu API key dưới key logic dành riêng cho orders; tạo Transit key cho dữ liệu orders; viết policy chỉ có `read` ở KV và `update` ở endpoint Transit phù hợp. Phân biệt chính xác đường dẫn/capability theo API engine.
2. **Định danh workload:** cấu hình Kubernetes auth, bind role với ServiceAccount và namespace của `order-service`; ứng dụng lấy danh tính từ pod, không nhúng root token.
3. **Kết nối từ Java:** cấu hình HTTPS tin cậy, `ClientAuthentication`, `SessionManager` rồi inject `VaultOperations` vào service cần dùng; lưu ý tương thích phiên bản Spring Vault.
4. **Thực thi nghiệp vụ:** chỉ lấy API key khi cần theo chiến lược cache đã định; gọi Transit để mã hóa trước khi lưu dữ liệu; giới hạn người có quyền giải mã.
5. **Vận hành:** định nghĩa quy trình thay API key, chính sách token TTL/renewal, giám sát lỗi Vault và audit; thử tình huống pod restart, token revoke, Vault timeout và dữ liệu cũ sau key rotation.

Trong thiết kế này, bí mật vẫn xuất hiện trong bộ nhớ ứng dụng khi cần sử dụng. Lợi ích chính là có **điểm kiểm soát danh tính, quyền, vòng đời và quan sát tập trung**, giúp giảm số bản sao tồn tại dài hạn và thu hẹp tác động khi một workload gặp sự cố.

## 9. Kiểm thử và điều kiện sẵn sàng đưa vào production

Một bài kiểm thử tích hợp có ý nghĩa cần dùng Vault thực trong môi trường test cô lập (có thể chạy Vault dev server hoặc container test chỉ phục vụ kiểm thử), tạo mount/role/policy/secret kiểm thử rồi xác nhận **cả đường thành công lẫn đường bị từ chối**. Test mock `VaultOperations` hữu ích cho logic của service nhưng không chứng minh auth method, policy path hay tính tương thích KV v2 hoạt động.

Các tình huống tối thiểu cần thử:

1. Workload đúng role đọc được đúng secret; workload khác nhận `403`.
2. Key hoặc field thiếu được xử lý như lỗi cấu hình/kinh doanh theo thiết kế, không trả về giá trị rỗng im lặng.
3. Token hết hạn/revoke được xử lý đúng; không tạo vòng lặp đăng nhập vô hạn.
4. Credential/lease được thay khi hết hạn; kết nối cũ và mới có hành vi rõ ràng.
5. Vault chậm, mất kết nối, lỗi TLS hoặc bị giới hạn lưu lượng không khiến ứng dụng lộ dữ liệu qua log.
6. Không có secret thật trong Git, image, tài liệu, log, trace, metric labels hoặc thông báo lỗi trả ra ngoài.

Checklist triển khai: **quyền tối thiểu**, **identity của workload**, **TLS chuẩn**, **chiến lược rotation/expiry**, **audit/monitoring**, **kế hoạch khôi phục khi Vault gián đoạn**. Những điều kiện này phải được kiểm tra theo nghiệp vụ cụ thể; việc build thành công ví dụ Java chỉ chứng minh một phần nhỏ.

## 10. Tổng kết và câu hỏi tự kiểm tra

Spring Vault là lớp tích hợp Java giúp ứng dụng nói chuyện với HashiCorp Vault, đặc biệt thông qua `VaultTemplate` và `VaultOperations`. Vault giải quyết bài toán quản lý bí mật bằng cách kết hợp xác thực danh tính, policy, secrets engines, audit và quản lý vòng đời. Lựa chọn KV, Database, Transit hay PKI phụ thuộc loại dữ liệu và hành vi mà ứng dụng cần; không có một API “lấy secret” chung giải quyết mọi vấn đề.

Hãy tự trả lời trước khi chuyển sang bài tiếp theo:

1. Vì sao đưa mật khẩu từ `application.yml` sang biến môi trường **chưa đủ** để giải quyết bài toán rotation và audit?
2. Sự khác biệt giữa auth method, secrets engine, policy và token là gì?
3. Với KV v2 mount `secret/` và key `apps/orders`, policy đọc dữ liệu cần áp vào path nào? API `opsForKeyValue` nên nhận key nào?
4. Vì sao hết hạn của Vault token và lease của database credential không thể xem là cùng một việc?
5. Trường hợp nào nên chọn KV, Transit hoặc PKI; và vì sao dùng Transit không có nghĩa Vault lưu các bản ghi đã mã hóa của ứng dụng?
6. Khi Vault trả `403` hoặc timeout, ứng dụng nên phản ứng khác nhau như thế nào?

## Tài liệu tham khảo chính thức

- [Spring Vault — Introduction to VaultTemplate](https://docs.spring.io/spring-vault/reference/vault/imperative-template.html)
- [Spring Vault — Authentication Methods](https://docs.spring.io/spring-vault/reference/vault/authentication.html)
- [Spring Vault — Vault Secrets Engines, KV v1/v2](https://docs.spring.io/spring-vault/reference/vault/vault-secret-engines.html)
- [HashiCorp Vault — How Vault Works](https://developer.hashicorp.com/vault/docs/about-vault/how-vault-works)
- [HashiCorp Vault — Policies](https://developer.hashicorp.com/vault/docs/concepts/policies)
- [HashiCorp Vault — Transit Secrets Engine](https://developer.hashicorp.com/vault/docs/secrets/transit)
- [HashiCorp Vault — PKI Secrets Engine](https://developer.hashicorp.com/vault/docs/secrets/pki)

> **Lưu ý về phiên bản:** Tên class và chữ ký API có thể thay đổi giữa các nhánh Spring Vault, Spring Boot và Vault. Ví dụ trong bài dùng những API phổ biến của Spring Vault để minh họa ý tưởng; khi thực hành, đối chiếu với reference và dependency version thực tế của dự án.
