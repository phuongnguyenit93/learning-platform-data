# Transit secrets engine và mô hình mã hóa như một dịch vụ

## 1. Mục tiêu và bối cảnh

Khi một ứng dụng Java cần lưu thông tin nhạy cảm như số định danh khách hàng, dữ liệu hồ sơ hoặc mã định danh giao dịch, ứng dụng phải bảo vệ dữ liệu ngay cả khi cơ sở dữ liệu hoặc bản sao lưu bị lộ. Cách thông thường là tự quản lý khóa mã hóa trong ứng dụng. Cách này tạo thêm vấn đề: khóa lưu ở đâu, ai được giải mã, xoay vòng khóa như thế nào và làm sao kiểm toán những lần sử dụng khóa?

**HashiCorp Vault Transit secrets engine** giải quyết một phần quan trọng của bài toán đó bằng mô hình *Encryption as a Service* (EaaS, mã hóa như một dịch vụ). Ứng dụng gửi dữ liệu cần mã hóa tới Vault qua kết nối được bảo vệ; Vault sử dụng khóa do mình quản lý và trả kết quả mã hóa cho ứng dụng. Ứng dụng giữ bản mã để lưu vào hệ thống của mình, còn Vault giữ và quản trị khóa.

Trong phạm vi **Spring Vault**, ứng dụng Java sử dụng `VaultTemplate` hoặc giao diện `VaultOperations` để gọi các API Transit; đồng thời phải xác thực theo danh tính workload, sử dụng policy đúng quyền cần thiết, xử lý lỗi và vận hành vòng đời token. Bài này tập trung vào cơ chế Transit, ranh giới bảo mật và cách đưa nó vào một dịch vụ Java.

Sau bài học, bạn có thể:

- Phân biệt Transit với KV secrets engine, mã hóa dữ liệu tại ứng dụng và mã hóa lưu trữ của cơ sở dữ liệu.
- Diễn giải luồng `encrypt`, `decrypt`, `rewrap` và quá trình xoay vòng phiên bản khóa.
- Tạo khóa, policy theo quyền tối thiểu và gọi Transit từ Spring Vault.
- Xác định giới hạn của EaaS, thiết kế xử lý lỗi, giám sát và kiểm thử tích hợp.

## 2. Transit là gì và không làm gì?

Transit là một **secrets engine thực hiện thao tác mật mã**. Với khóa đối xứng mặc định, Vault nhận bản rõ, mã hóa bằng khóa đang hoạt động và trả về bản mã có thông tin phiên bản khóa. Khi giải mã, Vault nhận bản mã, tìm đúng phiên bản khóa tương ứng và trả lại bản rõ nếu caller được phép.

**Transit không lưu bản rõ hoặc bản mã nghiệp vụ thay ứng dụng.** Vault lưu cấu hình và vật liệu khóa; cơ sở dữ liệu, object storage hoặc hệ thống thông điệp của ứng dụng vẫn chịu trách nhiệm lưu dữ liệu đã mã hóa. Chẳng hạn, một service lưu trường `email_encrypted` vào PostgreSQL và chỉ gọi Transit khi cần đọc hoặc cập nhật giá trị email.

| Giải pháp | Thành phần quản lý | Công dụng chính | Giới hạn cần nhớ |
| --- | --- | --- | --- |
| Vault KV | Giá trị secret, phiên bản và metadata | Cung cấp cấu hình nhạy cảm như API key hoặc password | Không phải API mã hóa dữ liệu ứng dụng tùy ý |
| Vault Transit | Khóa mật mã và thao tác trên khóa | Mã hóa, giải mã, rewrap và một số nghiệp vụ mật mã khác | Không lưu dữ liệu nghiệp vụ; service phải gọi Vault |
| Mã hóa ở DB/ổ đĩa | Khóa và mã hóa của hạ tầng lưu trữ | Bảo vệ media hoặc file backup | Người có quyền truy vấn DB có thể vẫn nhìn thấy bản rõ |
| Mã hóa trong ứng dụng | Khóa hoặc DEK được ứng dụng sử dụng | Kiểm soát xử lý, có thể mã hóa phía client | Ứng dụng cần quản lý vòng đời khóa và điểm lộ khóa |

Transit tách việc **quản lý và sử dụng khóa** khỏi logic nghiệp vụ. Tuy nhiên, nó không làm bản rõ biến mất khỏi mọi nơi: service Java vẫn giữ bản rõ trước khi mã hóa và sau khi giải mã; Vault cũng xử lý bản rõ trong lúc thực hiện phép toán. Vì vậy TLS, bảo mật bộ nhớ, chính sách truy cập dữ liệu và kiểm soát log vẫn bắt buộc.

### 2.1. Mô hình EaaS trong hệ thống Java

~~~mermaid
sequenceDiagram
    participant Client as Client
    participant App as Spring Boot API
    participant Vault as Vault Transit
    participant DB as Database

    Client->>App: Gửi dữ liệu cần bảo vệ
    App->>Vault: encrypt(key, Base64(UTF-8(plaintext)))
    Note over App,Vault: TLS + Vault token theo workload
    Vault-->>App: ciphertext = vault:v1:...
    App->>DB: Lưu ciphertext
    DB-->>App: Thành công
    App-->>Client: Kết quả nghiệp vụ

    Client->>App: Yêu cầu đọc dữ liệu được phép
    App->>DB: Đọc ciphertext
    DB-->>App: vault:v1:...
    App->>Vault: decrypt(key, ciphertext)
    Vault-->>App: Base64(UTF-8(plaintext))
    App-->>Client: Dữ liệu theo quyền của client
~~~

Điểm quan trọng của sơ đồ là **hai lớp phân quyền độc lập**. Ứng dụng xác định người dùng cuối có được xem dữ liệu hay không; Vault xác định workload của ứng dụng có được gọi phép toán với một khóa hay không. Có token cho phép `decrypt` không có nghĩa bất kỳ người dùng HTTP nào cũng được xem bản rõ.

### 2.2. Cơ chế mật mã và dạng dữ liệu

Với khóa đối xứng kiểu `aes256-gcm96` thường dùng trong Transit, Vault thực hiện mã hóa xác thực (AEAD). Kết quả vừa bảo vệ tính bí mật vừa cho phép phát hiện bản mã bị sửa đổi. Với chế độ thông thường, mã hóa cùng một bản rõ nhiều lần có thể cho các bản mã khác nhau vì sử dụng nonce; không thể dựa vào việc so sánh bản mã để kiểm tra hai giá trị bản rõ có bằng nhau.

Một kết quả Transit thường có dạng:

~~~text
vault:v1:...
~~~

`v1` là **phiên bản khóa Transit** đã dùng, không phải phiên bản API hay một định dạng mà ứng dụng tự phân tích để giải mã. Hãy lưu **toàn bộ chuỗi bản mã** nguyên vẹn. Khi gọi API, trường `plaintext` phải là **Base64 của byte bản rõ**; Base64 chỉ là biểu diễn dữ liệu qua JSON, **không phải mã hóa bảo mật**.

## 3. Khởi tạo Transit và áp dụng nguyên tắc ít quyền nhất

Các lệnh trong phần này minh họa cách quản trị Vault bằng CLI, giả sử đã thiết lập kết nối TLS tới Vault và có phiên đăng nhập quản trị phù hợp. Không thực hiện việc cấp quyền quản trị từ một ứng dụng xử lý yêu cầu người dùng.

### 3.1. Bật engine và tạo khóa

~~~bash
# Thực hiện một lần bởi vai trò quản trị, nếu mount chưa tồn tại.
vault secrets enable -path=transit transit

# Tạo khóa AES đối xứng cho dữ liệu của dịch vụ orders.
vault write -f transit/keys/orders-pii

# Xem metadata khóa, không phải bản rõ dữ liệu nghiệp vụ.
vault read transit/keys/orders-pii
~~~

`transit` là tên mount trong ví dụ; hệ thống khác có thể đặt `crypto` hoặc một mount riêng. Khi đổi mount, tất cả đường dẫn API và policy phải đổi tương ứng. Khóa `orders-pii` là định danh **bên trong mount**. Trong thiết kế production, cần quyết định rõ loại khóa, quyền export, quyền backup, phân tách môi trường và yêu cầu vận hành trước khi tạo.

### 3.2. Phân quyền theo thao tác

Ví dụ policy HCL cho một service cần mã hóa, giải mã và chuyển bản mã sang khóa mới:

~~~hcl
# orders-transit.hcl
path "transit/encrypt/orders-pii" {
  capabilities = ["update"]
}

path "transit/decrypt/orders-pii" {
  capabilities = ["update"]
}

path "transit/rewrap/orders-pii" {
  capabilities = ["update"]
}
~~~

Quản trị viên áp dụng bằng `vault policy write orders-transit orders-transit.hcl`. Với API dùng phương thức POST, capability `update` là quyền chính cần thiết. Service chỉ cần ghi dữ liệu thì nên được cấp **`encrypt`**, không cấp `decrypt`. Một tác vụ migration có thể được cấp `rewrap` riêng. Quyền tạo khóa, xoay vòng, thay cấu hình hoặc xóa khóa phải nằm ở vai trò quản trị tương ứng, không nằm trong policy ứng dụng.

| Danh tính | Quyền phù hợp | Mục đích |
| --- | --- | --- |
| `orders-writer` | `transit/encrypt/orders-pii` | Ghi thông tin nhạy cảm mới |
| `orders-reader` | `transit/decrypt/orders-pii` | Đọc dữ liệu đã qua kiểm tra quyền nghiệp vụ |
| `orders-migrator` | `transit/rewrap/orders-pii` | Nâng phiên bản mã hóa của dữ liệu đã lưu |
| Vault administrator | Các endpoint quản lý khóa có kiểm soát | Tạo, rotate và thay policy/cấu hình |

Không sử dụng token root hoặc policy bao trùm `transit/*` cho ứng dụng. Đồng thời, cần nhớ policy Vault chỉ ràng buộc *danh tính service*; tầng API Java vẫn phải thực hiện authentication và authorization của người dùng cuối.

### 3.3. Xác thực bằng workload

Production nên gắn quyền Vault với danh tính workload và cấp token có hạn sử dụng:

1. Trong Kubernetes, Pod có ServiceAccount riêng; Vault Kubernetes auth kiểm tra JWT và ràng buộc ServiceAccount/namespace với Vault role.
2. Vault role cấp policy cần thiết cho workload, ví dụ `orders-transit`, cùng thời hạn token phù hợp.
3. Spring Vault sử dụng cơ chế `ClientAuthentication` thích hợp và quản lý phiên đăng nhập/token; chỉ những lời gọi hợp lệ mới được thực hiện.
4. Cấu hình giám sát token hết hạn, gia hạn và khả năng đăng nhập lại theo đặc điểm auth method. Token hoặc JWT không được hardcode trong mã nguồn, đưa vào log hay commit lên Git.

Ví dụ, sau khi quản trị viên đã bật và cấu hình Kubernetes auth với Kubernetes API, có thể tạo role ràng buộc đúng ServiceAccount và namespace:

~~~bash
vault write auth/kubernetes/role/orders-api \
  bound_service_account_names=orders-api \
  bound_service_account_namespaces=production \
  token_policies=orders-transit \
  token_ttl=1h
~~~

Role này chỉ minh họa phần ánh xạ danh tính; workload còn phải cấu hình cơ chế Kubernetes login trong Spring Vault, và policy `orders-transit` phải được tạo trước. Các lựa chọn khác gồm AppRole, JWT/OIDC hoặc cơ chế xác thực hạ tầng tùy nơi chạy. **Không đồng nhất vòng đời token với vòng đời khóa:** token dùng để *ủy quyền gọi Vault* và có thể hết hạn/được gia hạn; khóa Transit dùng để *mã hóa dữ liệu* và có lịch sử phiên bản độc lập. Bản mã Transit không phải một dynamic secret có lease tự hết hạn.

## 4. Các API cốt lõi: encrypt, decrypt, rewrap

Các endpoint bên dưới nằm dưới `/v1/` của Vault HTTP API; khi dùng `VaultTemplate`, đường dẫn truyền vào thường **không chứa `/v1/`**.

### 4.1. Encrypt: bản rõ thành bản mã

~~~http
POST /v1/transit/encrypt/orders-pii
Content-Type: application/json
X-Vault-Token: <workload-token>

{
  "plaintext": "aGVsbG8="
}
~~~

Trong ví dụ, `aGVsbG8=` là Base64 của chuỗi UTF-8 `hello`. Một phản hồi rút gọn:

~~~json
{
  "data": {
    "ciphertext": "vault:v1:...",
    "key_version": 1
  }
}
~~~

Ứng dụng lưu `data.ciphertext`. Không lưu bản rõ trong bảng dữ liệu, log nghiệp vụ hoặc queue chỉ vì Vault đã trả bản mã.

### 4.2. Decrypt: bản mã thành bản rõ

~~~http
POST /v1/transit/decrypt/orders-pii
Content-Type: application/json
X-Vault-Token: <workload-token>

{
  "ciphertext": "vault:v1:..."
}
~~~

Phản hồi có `data.plaintext` ở dạng Base64. Bên nhận giải mã Base64 thành byte gốc rồi chuyển UTF-8 nếu bản rõ là chuỗi văn bản. Với dữ liệu nhị phân, phải giữ nguyên `byte[]` và tránh chuyển đổi qua `String`.

Vault kiểm tra phiên bản khóa và tính xác thực của ciphertext. Một chuỗi không hợp lệ, bản mã bị sửa hoặc key không khớp có thể khiến thao tác thất bại; ứng dụng không được tự trả dữ liệu rỗng hoặc bản rõ dự phòng như thể đã giải mã thành công.

### 4.3. Rewrap: cập nhật phiên bản mã hóa

Khi có phiên bản khóa mới, bản mã cũ có thể được đưa vào API `rewrap`:

~~~http
POST /v1/transit/rewrap/orders-pii
Content-Type: application/json
X-Vault-Token: <workload-token>

{
  "ciphertext": "vault:v1:..."
}
~~~

Vault giải mã và mã hóa lại **bên trong Vault**, trả ciphertext dưới phiên bản khóa hiện hành, chẳng hạn `vault:v2:...`. Phía ứng dụng không nhận lại plaintext trong phản hồi `rewrap`. Nhờ vậy có thể thiết kế job migration chỉ có quyền `rewrap` và không có quyền `decrypt`.

| Thao tác | Đầu vào chính | Đầu ra chính | Service có cần quyền giải mã? |
| --- | --- | --- | --- |
| `encrypt` | Plaintext Base64 | Ciphertext | Không |
| `decrypt` | Ciphertext | Plaintext Base64 | Có |
| `rewrap` | Ciphertext cũ | Ciphertext với khóa hiện hành | Không; chỉ cần quyền rewrap |

## 5. Gọi Transit bằng Spring Vault

Ví dụ sau dùng `VaultOperations` — giao diện mà `VaultTemplate` hiện thực — để thể hiện trực tiếp cấu trúc request/response của Vault. Ứng dụng cần cấu hình một bean `VaultOperations` với endpoint HTTPS, TLS trust và `ClientAuthentication` theo workload. Nếu hệ thống dùng Spring Cloud Vault để auto-configure client, kiểm tra bean và cơ chế khởi tạo theo phiên bản starter thực tế của dự án. Không hardcode token thử nghiệm vào bean production.

Nếu tự cấu hình Spring Vault, một bean có thể ghép endpoint và chiến lược xác thực đã được cấu hình ở nơi khác:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.vault.authentication.ClientAuthentication;
import org.springframework.vault.client.VaultEndpoint;
import org.springframework.vault.core.VaultOperations;
import org.springframework.vault.core.VaultTemplate;

@Configuration
class VaultClientConfiguration {
    @Bean
    VaultOperations vaultOperations(VaultEndpoint endpoint,
                                    ClientAuthentication authentication) {
        return new VaultTemplate(endpoint, authentication);
    }
}
~~~

Đây là phần *lắp ghép*: dự án vẫn phải cung cấp các bean `VaultEndpoint` và `ClientAuthentication` theo TLS, Kubernetes auth/AppRole và vòng đời token thực tế. Không khai báo bean trùng nếu Spring Cloud Vault đã tạo client thích hợp.

~~~java
package com.example.orders.security;

import java.nio.charset.StandardCharsets;
import java.util.Base64;
import java.util.Map;
import java.util.Objects;

import org.springframework.stereotype.Service;
import org.springframework.vault.core.VaultOperations;
import org.springframework.vault.support.VaultResponse;

@Service
public class TransitCryptoService {

    private static final String KEY_NAME = "orders-pii";
    private static final String MOUNT = "transit";

    private final VaultOperations vault;

    public TransitCryptoService(VaultOperations vault) {
        this.vault = vault;
    }

    public String encrypt(String plaintext) {
        Objects.requireNonNull(plaintext, "plaintext");

        String encoded = Base64.getEncoder().encodeToString(
                plaintext.getBytes(StandardCharsets.UTF_8));

        VaultResponse response = vault.write(
                MOUNT + "/encrypt/" + KEY_NAME,
                Map.of("plaintext", encoded));

        return requiredData(response, "ciphertext");
    }

    public String decrypt(String ciphertext) {
        Objects.requireNonNull(ciphertext, "ciphertext");

        VaultResponse response = vault.write(
                MOUNT + "/decrypt/" + KEY_NAME,
                Map.of("ciphertext", ciphertext));

        String encoded = requiredData(response, "plaintext");
        byte[] bytes = Base64.getDecoder().decode(encoded);
        return new String(bytes, StandardCharsets.UTF_8);
    }

    public String rewrap(String ciphertext) {
        Objects.requireNonNull(ciphertext, "ciphertext");

        VaultResponse response = vault.write(
                MOUNT + "/rewrap/" + KEY_NAME,
                Map.of("ciphertext", ciphertext));

        return requiredData(response, "ciphertext");
    }

    private static String requiredData(VaultResponse response, String field) {
        if (response == null || response.getData() == null) {
            throw new IllegalStateException("Missing Transit response data");
        }

        Object value = response.getData().get(field);
        if (!(value instanceof String result) || result.isBlank()) {
            throw new IllegalStateException("Missing Transit field: " + field);
        }

        return result;
    }
}
~~~

**Giải thích lựa chọn thiết kế:**

- `VaultOperations` cho phép kiểm thử và thay thế cách cấu hình client mà không gắn business service với cách cấp token.
- `MOUNT` và `KEY_NAME` phải đồng bộ với cấu hình Vault/policy. Trong hệ thống nhiều môi trường, nên đưa định danh mount/key vào cấu hình đã kiểm soát thay vì để controller HTTP quyết định tên khóa.
- `vault.write(...)` gọi API dạng POST và trả `VaultResponse`. Phản hồi lỗi HTTP sẽ dẫn tới exception của lớp client; không giả định mọi request đều có `data`.
- Ví dụ trả `String` cho dữ liệu văn bản để dễ học. Với dữ liệu có yêu cầu hạn chế lưu bản rõ trong heap, thiết kế API xử lý `byte[]` và làm sạch bộ đệm tạm khi thích hợp; Java `String` không bảo đảm có thể xóa khỏi bộ nhớ ngay lập tức.
- Spring Vault còn có các API chuyên biệt cho từng secrets engine. Khi dùng chúng, phải đối chiếu chữ ký phương thức với phiên bản thư viện được khóa trong dự án; cơ chế và phân quyền Transit vẫn như nhau.

### 5.1. Cách dùng từ tầng nghiệp vụ

Giả sử bản ghi khách hàng chứa cột `email_ciphertext`:

~~~java
// Khi tạo hoặc cập nhật khách hàng:
String ciphertext = transitCryptoService.encrypt(request.email());
customer.setEmailCiphertext(ciphertext);
customerRepository.save(customer);

// Khi một use case đã kiểm tra quyền xem email:
String email = transitCryptoService.decrypt(
        customer.getEmailCiphertext());
~~~

Đừng đặt `decrypt` mặc định trong mapper chung, `toString()` hoặc cơ chế serialize JSON; những nơi đó có thể vô tình giải mã rồi trả dữ liệu nhạy cảm cho caller không được phép. Hãy chỉ giải mã trong use case đã kiểm tra quyền.

### 5.2. Định dạng dữ liệu, binary payload và context

Với API Transit, `plaintext` là Base64 của bytes. Chuỗi Unicode phải được mã hóa UTF-8 một cách nhất quán; dữ liệu nhị phân không cần qua bước UTF-8. Một số cách sử dụng khóa dẫn xuất yêu cầu `context` được mã hóa Base64 và cung cấp nhất quán giữa `encrypt`/`decrypt`/`rewrap`. Chỉ bật derived key, convergent encryption hoặc các lựa chọn mật mã khác khi đã phân tích yêu cầu, vì chúng thay đổi điều kiện gọi API và mô hình an toàn.

Để mã hóa lượng dữ liệu lớn, có thể chọn **envelope encryption**: Vault Transit tạo hoặc bảo vệ data encryption key (DEK), còn ứng dụng dùng DEK để mã hóa payload cục bộ. Khi đó ứng dụng phải quản lý vòng đời và khả năng xóa DEK bản rõ trong bộ nhớ. Không nên truyền payload rất lớn qua Transit theo từng byte hoặc dùng EaaS như một dịch vụ streaming không có thiết kế tải.

## 6. Xoay vòng khóa và chiến lược cập nhật bản mã

Một khóa Transit có nhiều **key version**. Xoay vòng tạo phiên bản khóa mới cho lần mã hóa tiếp theo; bản mã cũ vẫn mang prefix phiên bản cũ và có thể giải mã nếu cấu hình cho phép.

~~~bash
# Vai trò quản trị: tạo phiên bản mới.
vault write -f transit/keys/orders-pii/rotate

# Kiểm tra metadata để biết phiên bản mới nhất.
vault read transit/keys/orders-pii
~~~

Nếu đã lưu nhiều bản mã phiên bản cũ, có hai cách phổ biến:

1. **Lazy rewrap**: mỗi khi bản ghi được xử lý, gọi `rewrap` và ghi lại ciphertext mới trong một transaction cập nhật phù hợp.
2. **Batch migration**: job có quyền `rewrap` đọc bản mã theo lô, nhận bản mã phiên bản mới, lưu bằng cơ chế chống ghi đè đồng thời, lưu checkpoint để tiếp tục sau lỗi.

Ví dụ sau khi tất cả dữ liệu cần giữ đã được chuyển sang phiên bản mới, quản trị viên *có thể* đặt phiên bản tối thiểu được giải mã:

~~~bash
# CHỈ chạy sau khi đã kiểm kê toàn bộ ciphertext v1
# và xác minh không còn bản mã cũ cần giải mã.
vault write transit/keys/orders-pii/config min_decryption_version=2
~~~

Thay đổi `min_decryption_version` quá sớm có thể khiến dữ liệu hoặc bản backup cũ không thể giải mã theo cấu hình hiện tại. **Rotation không tự động rewrap bản mã đã được lưu**; phải có kế hoạch di trú và kiểm thử phục hồi backup. Nếu mất hoàn toàn vật liệu khóa hoặc cố ý hủy phiên bản cần dùng, khả năng giải mã bản mã liên quan cũng mất theo.

## 7. Biên tin cậy và các giới hạn bảo mật

Đặt Vault làm nơi giữ khóa giúp giảm nguy cơ lộ khóa khi mã nguồn, container image hoặc DB bị truy cập trái phép. Nhưng EaaS vẫn có các ranh giới:

| Tình huống | Transit giúp gì? | Kiểm soát bổ sung |
| --- | --- | --- |
| Bản sao lưu DB bị lộ | Dữ liệu nhạy cảm vẫn ở dạng ciphertext | Bảo vệ khóa, giới hạn quyền decrypt, tránh lưu bản rõ song song |
| Token chỉ có encrypt bị lộ | Kẻ tấn công không có quyền decrypt qua token đó | TTL ngắn, thu hồi token, giới hạn nguồn truy cập, audit |
| Token có decrypt bị lộ | Chỉ bảo vệ trong giới hạn quyền còn lại; có thể bị lạm dụng giải mã | Chia tách quyền, phát hiện bất thường, thu hồi nhanh |
| JVM/service bị chiếm quyền | Service có thể bị đọc bản rõ tại nơi xử lý | Bảo mật runtime, tránh debug/log nhạy cảm, ràng buộc quyền nghiệp vụ |
| Vault/đường truyền không sẵn sàng | Không thể gọi encrypt/decrypt trực tuyến | HA, timeout, retry có giới hạn, kế hoạch khôi phục |
| Ciphertext bị sửa | Chế độ mã hóa xác thực có thể phát hiện tính toàn vẹn bị phá | Không bỏ qua lỗi xác thực, bảo vệ tính toàn vẹn nghiệp vụ và nguồn dữ liệu |

Ba hiểu lầm cần tránh:

1. **Base64 không bảo mật**: encode để truyền payload qua JSON hoàn toàn khác encryption.
2. **Có ciphertext không có nghĩa là có thể tìm kiếm theo giá trị bản rõ**: mã hóa AEAD thông thường không cho phép so sánh equality bằng ciphertext. Muốn tìm kiếm, cần thiết kế chỉ mục riêng với phân tích rò rỉ thông tin, không tùy tiện bật convergent encryption.
3. **Key rotation không đồng nghĩa thu hồi quyền ngay lập tức**: thu hồi/quản lý token ảnh hưởng ai có thể sử dụng API, còn rotate tạo phiên bản khóa mới. Hai quy trình phục vụ mục đích khác nhau.

## 8. Xử lý lỗi và vận hành ổn định

Các lời gọi Transit là lời gọi mạng. Chúng có thể thất bại vì xác thực, policy, dữ liệu không hợp lệ, độ trễ mạng hoặc Vault quá tải. Ứng dụng nên phân loại trước khi quyết định retry.

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| `403` hoặc lỗi permission | Token không có quyền đúng endpoint/key; role/policy sai | Kiểm tra auth role, mount, key và policy; không cấp root để chữa cháy |
| `400` và lỗi đầu vào | Base64 sai, ciphertext sai, thiếu `context` hoặc tham số không hợp lệ | Sửa dữ liệu/cấu hình; không retry vô hạn |
| `404` hoặc đường dẫn không tồn tại | Sai mount, key hoặc endpoint | Xác minh tên mount/key và quá trình provisioning |
| `429`, `5xx`, timeout | Rate limit, Vault chưa sẵn sàng, mạng chập chờn | Timeout hợp lý; retry giới hạn có backoff/jitter và metrics |
| Decrypt thất bại với bản mã cũ | Thay đổi phiên bản tối thiểu hoặc thiếu key version | Kiểm tra lịch sử key, batch migration và chính sách backup |

Các nguyên tắc triển khai:

- **Fail closed**: nếu không giải mã được, trả lỗi nghiệp vụ phù hợp; không tiếp tục bằng dữ liệu rỗng hoặc plaintext giả.
- **Không log dữ liệu nhạy cảm**: không ghi `plaintext`, JWT, token hoặc toàn bộ request/response Transit. Audit Vault và log ứng dụng phải được cấu hình với chính sách bảo mật riêng.
- **Retry có kỷ luật**: chỉ retry lỗi tạm thời; cần bảo đảm thao tác ghi DB sau mã hóa không tạo bản ghi trùng khi request bị lặp. Ciphertext của hai lần encrypt có thể khác nhau dù bản rõ giống nhau.
- **Timeout và giới hạn tải**: giới hạn concurrency, đo độ trễ p50/p95/p99 cho thao tác Transit, tỷ lệ lỗi theo loại, số lần đăng nhập/gia hạn token và trạng thái Vault HA.
- **Tách quyền quản trị**: hệ thống tự động deploy service không nên có quyền tạo/xóa/rotate key trừ khi có quy trình quản trị riêng.
- **Lập kế hoạch khôi phục**: backup/restore Vault key material theo quy trình được hỗ trợ, kiểm thử khả năng giải mã dữ liệu từ backup và tránh phụ thuộc duy nhất vào một Vault instance.

Transit hỗ trợ các chức năng mật mã khác như HMAC, chữ ký số, verify và tạo data key. HMAC/chữ ký số phục vụ mục đích khác với bảo mật nội dung bằng encrypt/decrypt; không dùng nhầm một loại thao tác để thay thế loại còn lại.

## 9. Kiểm thử tích hợp với Vault thật

Không nên tự mô phỏng thuật toán Vault trong unit test để khẳng định mã hóa an toàn. Unit test có thể kiểm tra cách business service xử lý lỗi và việc gọi interface; **integration test** cần kết nối tới Vault test độc lập (chẳng hạn Vault dev mode trong môi trường test bị cô lập, hoặc container có cấu hình và lifecycle rõ ràng).

Một kịch bản tích hợp tối thiểu:

1. Khởi tạo Transit mount, khóa test và policy test trong Vault test. Không dùng key/token production.
2. Với input chứa tiếng Việt hoặc Unicode, gọi `encrypt`, xác nhận đầu ra là ciphertext hợp lệ và không chứa nguyên bản input.
3. Gọi `decrypt` bằng đúng khóa, xác nhận byte/chuỗi UTF-8 khớp ban đầu.
4. Gọi `rewrap` sau khi rotate khóa test; xác nhận dữ liệu được giải mã đúng và ciphertext mang phiên bản mới.
5. Dùng token chỉ có quyền `encrypt` thử `decrypt`, kỳ vọng bị Vault từ chối.
6. Thử ciphertext bị sửa, token hết hạn, sai mount/key và Vault tạm thời không sẵn sàng; xác nhận ứng dụng báo lỗi phù hợp, không log plaintext và không trả dữ liệu sai.

Một test round-trip đơn giản, với `TransitCryptoService` đã được cấu hình kết nối tới Vault test, có thể có dạng:

~~~java
@Test
void encryptThenDecryptReturnsOriginalUnicodeText() {
    String original = "Khách hàng số 42";
    String ciphertext = transitCryptoService.encrypt(original);

    assertThat(ciphertext).startsWith("vault:v");
    assertThat(ciphertext).doesNotContain(original);
    assertThat(transitCryptoService.decrypt(ciphertext))
            .isEqualTo(original);
}
~~~

Đây là phác thảo một phần test JUnit/AssertJ: fixture, cấu hình kết nối Vault và lifecycle container phải do dự án thiết lập. Kiểm thử luôn cần bao gồm phân quyền thật để tránh tình trạng mã hóa/giải mã chạy đúng nhưng service được cấp quá nhiều quyền.

## 10. Bài thực hành và câu hỏi tự kiểm tra

**Bài thực hành: bảo vệ trường thông tin khách hàng**

Thiết kế một `Orders API` dùng Spring Vault với khóa `orders-pii`. Hệ thống có service ghi dữ liệu, service đọc dữ liệu được cấp quyền và một migration worker.

- Tạo Transit mount và khóa trong môi trường Vault test; đặt policy riêng cho ba workload.
- Viết adapter Java dựa trên `VaultOperations` để encrypt/decrypt/rewrap; lưu ciphertext vào database và kiểm soát đường đi của bản rõ.
- Rotate khóa, rewrap toàn bộ bản ghi thử nghiệm và chứng minh dữ liệu vẫn đọc được.
- Thử chủ động cấp nhầm token writer cho API decrypt để xác nhận phép toán bị từ chối.
- Đo thời gian xử lý trước/sau khi thêm cuộc gọi Transit; chọn timeout và backoff phù hợp theo kết quả thực tế.

**Câu hỏi tự kiểm tra:**

1. Vì sao Transit không thay thế cơ sở dữ liệu và KV secrets engine?
2. Vì sao quyền `transit/decrypt/orders-pii` nên được tách khỏi quyền `transit/encrypt/orders-pii`?
3. Tại sao rotate khóa không tự nâng phiên bản toàn bộ ciphertext đang lưu?
4. `rewrap` giảm bề mặt lộ plaintext trong migration bằng cách nào?
5. Nếu service Java đã nhận plaintext từ client, chỉ sử dụng Transit có đủ để bảo đảm dữ liệu chưa bao giờ xuất hiện trong log hoặc memory dump không?

## 11. Tổng kết

Vault Transit hiện thực mô hình **mã hóa như một dịch vụ**: Vault quản lý khóa, thực hiện phép toán mật mã theo policy; ứng dụng Java giữ và sử dụng bản mã trong quy trình nghiệp vụ. Spring Vault giúp tích hợp việc gọi API qua `VaultTemplate`/`VaultOperations`, nhưng chất lượng bảo mật phụ thuộc vào danh tính workload, phân quyền, cách xử lý bản rõ, theo dõi token và quy trình quản lý phiên bản khóa.

Với hệ thống thật, hãy thiết kế từ đầu cả ba luồng **encrypt → lưu ciphertext**, **kiểm tra quyền → decrypt**, và **rotate → rewrap → xác minh dữ liệu**. Những luồng này, cùng kiểm thử tích hợp và kế hoạch phục hồi, quyết định việc dùng Transit có an toàn và vận hành được lâu dài hay không.
