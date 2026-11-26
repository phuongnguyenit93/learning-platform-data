# PCF và danh tính ứng dụng dựa trên chứng thư của nền tảng

## 1. Bài toán: ứng dụng trên Cloud Foundry tự xác thực với Vault

Một dịch vụ Spring Boot có thể chạy trên **Pivotal Cloud Foundry (PCF)**, còn thường được nhắc đến trong các hệ thống hiện đại bằng tên Cloud Foundry hoặc Tanzu Application Service. Dịch vụ cần đọc mật khẩu database từ HashiCorp Vault thông qua Spring Vault (`VaultTemplate`), nhưng không nên được cấp sẵn **Vault root token**, token dài hạn hoặc cặp username/password dùng chung.

PCF cung cấp cơ chế **instance identity**: môi trường chạy có thể cấp cho mỗi application instance một chứng thư X.509 và khóa riêng tương ứng. Vault có **Cloud Foundry (CF) auth method**, cho phép ứng dụng chứng minh đang sở hữu khóa riêng của instance, kiểm tra danh tính ứng dụng qua Cloud Foundry, rồi nhận một **Vault token có policy giới hạn**.

> Phân biệt tên gọi: trong giao diện Spring Cloud Vault, phương thức cấu hình là `PCF`; auth method của Vault được bật dưới tên **`cf`** (ví dụ endpoint `auth/cf/login`). Tên mount có thể được đổi theo cấu hình người quản trị.

Sau bài học, bạn sẽ:

1. Giải thích chứng thư instance do nền tảng cấp khác gì với TLS server certificate và Vault token.
2. Mô tả cách Vault xác minh chữ ký, CA, danh tính application/space/organization, điều kiện role và thời gian ký.
3. Cấu hình policy và CF auth role theo **đặc quyền tối thiểu**.
4. Áp dụng `spring.cloud.vault.authentication: PCF` hoặc `PcfAuthentication` trong ứng dụng Java.
5. Kiểm tra luồng cấp token, quyền đọc secret KV v2, hành vi bị từ chối và các lỗi vận hành thường gặp.

Bài thuộc chương **Xác thực cloud** của module **SPRING_VAULT**: trọng tâm là ứng dụng Java có danh tính workload tin cậy để sử dụng `VaultTemplate`, từ đó tiếp cận KV secrets, vòng đời token/lease, Transit encryption, PKI, giám sát và kiểm thử tích hợp.

## 2. Bốn chủ thể và ba loại credential

| Thành phần | Vai trò | Dữ liệu nắm giữ |
| --- | --- | --- |
| **Cloud Foundry platform** | Quản lý application instance, cấp instance identity và duy trì metadata ứng dụng | Identity CA (được bảo vệ), chứng thư/khóa riêng instance |
| **Ứng dụng Java** | Chứng minh đang chạy dưới danh tính instance, gọi Vault | Đường dẫn `CF_INSTANCE_CERT`, `CF_INSTANCE_KEY`; Vault token sau đăng nhập |
| **Vault CF auth method** | Xác minh chứng thư và chữ ký, đối chiếu CF API và role, cấp token | Danh sách CA tin cậy, cấu hình CF API, ràng buộc role |
| **Vault secrets engine** | Thực thi quyền của token trên KV/Transit/PKI | Secret và Vault ACL policy |

Nhận diện chính xác từng credential:

- **Instance certificate**: chứng thư X.509 gắn danh tính application instance do môi trường CF cấp; không phải Vault token.
- **Instance private key**: khóa riêng tương ứng để ký yêu cầu chứng minh quyền sở hữu; không được gửi lên Vault dưới dạng plaintext hoặc log.
- **Vault token**: được Vault cấp **sau khi** xác thực thành công, chứa policy và thông tin vòng đời; Spring Vault sử dụng khi gọi secrets engine.
- **CF API credentials dành cho phía Vault**: thông tin quản trị cấu hình để Vault xác minh trạng thái application/space/organization qua CF API; chúng không được nhúng vào ứng dụng Java.

Hai biến môi trường được nền tảng cung cấp cho instance khi cơ chế identity đã bật:

~~~text
CF_INSTANCE_CERT=/đường/dẫn/do/nền/tảng/cấp/instance.crt
CF_INSTANCE_KEY=/đường/dẫn/do/nền/tảng/cấp/instance.key
~~~

**Đây là đường dẫn đến tệp**, không phải nội dung PEM trong chuỗi biến môi trường. Đường dẫn cụ thể phụ thuộc foundation. Trước khi chạy Spring Vault, cần xác nhận nền tảng thực sự cung cấp các tệp, application process có quyền đọc, và key trùng khớp chứng thư. Không tự đặt hai biến trỏ tới chứng thư tự ký rồi kỳ vọng Vault chấp nhận.

### PCF instance identity khác với mTLS ra sao?

Trong CF auth, ứng dụng tạo **chữ ký của một yêu cầu đăng nhập** bằng khóa riêng instance. Vault kiểm tra chữ ký và chứng thư thông qua auth plugin. Điều này **khác với việc chỉ xuất trình client certificate trong một phiên TLS**; dù cả hai có thể dùng X.509, cơ chế kiểm chứng, endpoint và kết quả cấp quyền khác nhau.

Kênh ứng dụng → Vault vẫn cần **HTTPS/TLS đáng tin cậy** khi chạy trong môi trường thật. Chứng thư instance không tự thay thế TLS server certificate của Vault.

## 3. Luồng đăng nhập bằng danh tính nền tảng

~~~mermaid
sequenceDiagram
    participant CF as Cloud Foundry
    participant APP as Spring Boot workload
    participant AUTH as Vault CF auth
    participant API as Cloud Foundry API
    participant KV as Vault KV v2
    CF-->>APP: CF_INSTANCE_CERT + CF_INSTANCE_KEY (đường dẫn)
    APP->>APP: Ghép role, chứng thư, thời gian ký
    APP->>APP: Ký yêu cầu bằng khóa riêng instance
    APP->>AUTH: POST /v1/auth/cf/login
    AUTH->>AUTH: Kiểm tra chữ ký, thời gian, chuỗi CA, điều kiện role
    AUTH->>API: Kiểm tra application, space, organization
    API-->>AUTH: Metadata và trạng thái
    alt Hợp lệ
        AUTH-->>APP: Vault token với policy/TTL
        APP->>KV: GET /v1/secret/data/apps/payment (Vault token)
        KV-->>APP: Secret nếu policy cho phép
    else Không hợp lệ
        AUTH-->>APP: Lỗi xác thực, không cấp token
    end
~~~

Theo tài liệu của Vault CF auth, trình tự về mặt logic:

1. Application lấy **nội dung** chứng thư từ đường dẫn `CF_INSTANCE_CERT`, tên **role** được yêu cầu và thời gian ký hiện tại.
2. Application tạo chữ ký **RSA-PSS/SHA-256** bằng khóa riêng ở `CF_INSTANCE_KEY` theo định dạng request mà plugin yêu cầu.
3. Vault nhận `role`, `cf_instance_cert`, `signing_time` và `signature` qua `POST /v1/auth/cf/login`.
4. Vault kiểm tra thời gian ký có nằm trong cửa sổ được phép, chứng thư có chuỗi CA phù hợp, chữ ký có đúng khóa của chứng thư và các ràng buộc role có thỏa mãn.
5. Vault dùng CF API để kiểm tra danh tính application, space, organization liên quan vẫn hợp lệ; có thể áp thêm điều kiện nguồn IP theo cấu hình role.
6. Vault cấp token với policy và TTL của role. Từ đây các yêu cầu tới KV/Transit/PKI phải qua **ACL của token**.

Ở cấu hình mặc định được mô tả trong tài liệu CF auth, cửa sổ thời gian ký cho phép khoảng **300 giây trong quá khứ và 60 giây trong tương lai**; có thể cấu hình các giá trị này. Vì vậy **đồng bộ thời gian** giữa instance và Vault là điều kiện vận hành, bên cạnh việc xoay vòng CA/chứng thư.

Điểm quan trọng: bằng chứng chứng thư trả lời câu hỏi *workload này là ai?*; còn **Vault role + ACL policy** trả lời câu hỏi *workload được làm gì?*. Chứng thư hợp lệ không tự cho phép đọc toàn bộ Vault.

## 4. Policy và role: cấp quyền cho đúng ứng dụng

Giả sử `payment-api` chạy trong một CF foundation, chỉ cần đọc secret KV v2 có mount `secret` và key `apps/payment`. ACL phải dùng **đường dẫn API thực tế**:

~~~hcl
path "secret/data/apps/payment" {
  capabilities = ["read"]
}
~~~

Với KV v2, `secret/data/apps/payment` cho phép đọc nội dung; nó không cấp quyền `create`, `update`, `list` metadata hoặc bất cứ quyền nào trên Transit hay PKI.

### Cấu hình vai trò CF chặt chẽ

Role `payment-pcf` sẽ ràng buộc instance với ba UUID đã tra cứu trong CF API:

- **Application ID** của `payment-api`.
- **Space ID** nơi ứng dụng chạy.
- **Organization ID** sở hữu space.

Có thể ràng buộc instance ID nhưng một lần `cf push` có thể đổi instance ID, nên ràng buộc đó thường không phù hợp cho service được triển khai lại thường xuyên. Ngược lại, **không cấu hình bất kỳ `bound_*` nào** sẽ cho phép nhiều workload mang chứng thư hợp lệ của CA được chấp nhận vào cùng role, làm tăng rủi ro phân quyền quá rộng.

Nguyên tắc: một role riêng cho mỗi nhóm workload có nhu cầu quyền tương tự, ràng buộc ít nhất application/space/organization theo mô hình quản trị; cấp policy chỉ chứa các capability thực sự dùng.

## 5. Chuẩn bị nền tảng thực hành

**Bài lab này cần một Cloud Foundry/PCF foundation thật hoặc môi trường sandbox có identity certificate.** Vault `-dev` chạy đơn lẻ trên laptop **không thể tự phát hành chứng thư CF instance hợp lệ** hoặc mô phỏng đầy đủ việc Vault kiểm tra CF API.

Điều kiện cần có:

1. Một CF foundation cấp được chứng thư instance cùng private key, application có thể đọc đường dẫn trong `CF_INSTANCE_CERT` và `CF_INSTANCE_KEY`.
2. Một Vault server thử nghiệm có CF auth method/plugin khả dụng và ứng dụng có thể kết nối qua HTTPS.
3. Tài khoản quản trị Vault có quyền cấu hình auth method, policy và Vault role.
4. Thông tin CA của dịch vụ instance identity CF (chứng thư công khai), CF API URL, CF API account dành cho Vault và chứng thư tin cậy nếu CF API dùng CA nội bộ.
5. UUID application, space, organization lấy từ **CF API/CLI của foundation**. Không điền tên hiển thị thay cho UUID.
6. KV v2 mount `secret/` và secret thử nghiệm `apps/payment`, được operator chuẩn bị trước.

Tất cả UUID, URL và đường dẫn tệp trong lệnh ví dụ dưới đây là **tham số phải lấy từ môi trường thử nghiệm**. Không triển khai trực tiếp lên foundation production mà chưa đối chiếu đối tượng và quyền.

## 6. Quản trị viên Vault bật CF auth

### 6.1. Ghi policy tối thiểu

Khi đăng nhập Vault với quyền quản trị phù hợp, tạo policy:

~~~bash
vault policy write payment-secret-read - <<'HCL'
path "secret/data/apps/payment" {
  capabilities = ["read"]
}
HCL
~~~

Nếu KV mount khác tên `secret`, sửa path ACL theo đúng mount thực tế; Spring Vault cũng phải dùng cùng mount.

### 6.2. Bật và cấu hình auth method

~~~bash
# Chỉ bật nếu path auth/cf chưa được sử dụng.
vault auth enable -path=cf cf
~~~

Sau khi quản trị viên lấy CA chứng thư instance và dữ liệu CF API, cấu hình:

~~~bash
# Các biến phải được cấp từ hệ thống quản lý cấu hình/bí mật tin cậy.
# Không nhập mật khẩu thật trực tiếp vào tài liệu hay commit vào Git.
vault write auth/cf/config \
  identity_ca_certificates=@/secure/config/cf-instance-ca.crt \
  cf_api_addr="$CF_API_URL" \
  cf_username="$CF_API_USERNAME" \
  cf_password="$CF_API_PASSWORD" \
  cf_api_trusted_certificates=@/secure/config/cf-api-ca.crt
~~~

Phần `cf_api_trusted_certificates` phục vụ kiểm tra TLS của **CF API** khi dùng CA riêng; khác với `identity_ca_certificates` dùng xác minh **CF instance certificate**. Nếu CF API dùng CA đã được hệ thống tin cậy, cấu hình tin cậy TLS cần tuân theo cách triển khai của foundation.

Lệnh trên minh họa cấu hình tối thiểu; **tham số mật khẩu truyền qua command-line vẫn có thể hiện trong lịch sử thao tác/process arguments**, tùy môi trường. Khi triển khai thật, dùng quy trình cấp credential bảo mật của tổ chức (automation và hệ thống secret management), kiểm soát log, quyền operator và vòng đời credential. Không xuất thông số cấu hình nhạy cảm vào log CI.

### 6.3. Tạo role ràng buộc danh tính ứng dụng

~~~bash
# CF_APP_GUID, CF_SPACE_GUID, CF_ORG_GUID phải là UUID thật.
vault write auth/cf/roles/payment-pcf \
  bound_application_ids="$CF_APP_GUID" \
  bound_space_ids="$CF_SPACE_GUID" \
  bound_organization_ids="$CF_ORG_GUID" \
  policies="payment-secret-read" \
  token_ttl="30m" \
  token_max_ttl="1h"
~~~

Ý nghĩa:

| Trường | Vai trò |
| --- | --- |
| `bound_application_ids` | Chỉ nhận danh tính thuộc application được chỉ định |
| `bound_space_ids` | Hạn chế tới CF space được chọn |
| `bound_organization_ids` | Hạn chế tới CF organization được chọn |
| `policies` | Gán ACL khi Vault cấp token |
| `token_ttl`, `token_max_ttl` | Điều khiển thời hạn token theo role và giới hạn của Vault |

Đừng vô tình tạo role rộng bằng cách để trống mọi `bound_*`. Nếu đổi tên mount auth từ `cf` sang tên khác, tất cả đường dẫn quản trị/đăng nhập và cấu hình client phải đổi tương ứng.

### 6.4. Kiểm tra phía operator

~~~bash
vault auth list
vault read auth/cf/roles/payment-pcf
vault policy read payment-secret-read
~~~

Cần xác nhận đúng UUID, chính sách và TTL. Việc operator **đọc được policy** không chứng minh app xác thực thành công; phần tiếp theo phải chạy **trong CF application instance** được cấp chứng thư thật.

## 7. Xác thực từ đúng CF instance

Trong container của `payment-api`, các biến đường dẫn chứng thư được nền tảng cung cấp. Xác minh **chỉ sự tồn tại và quyền đọc**, không in private key:

~~~bash
test -n "$CF_INSTANCE_CERT" && test -r "$CF_INSTANCE_CERT"
test -n "$CF_INSTANCE_KEY" && test -r "$CF_INSTANCE_KEY"
~~~

Sử dụng Vault CLI có hỗ trợ auth method CF, với kết nối Vault tin cậy:

~~~bash
export VAULT_ADDR="https://vault.example.internal:8200"

# Nếu đang dùng shell quản trị có VAULT_TOKEN, cần bỏ token đó
# trước khi xác minh quyền của application.
unset VAULT_TOKEN

# Chỉ chạy bên trong instance CF có danh tính đúng role.
vault login -method=cf role=payment-pcf
~~~

Lệnh CLI xây dựng chữ ký từ chứng thư/khóa riêng instance; người học **không cần tự viết chữ ký** hoặc gửi khóa riêng lên Vault. Hãy bảo vệ kết quả đăng nhập: Vault CLI có thể hiển thị token, do đó không ghi output nguyên vẹn vào CI hoặc chia sẻ screenshot. Nếu dùng token helper, xác minh token đang dùng thực sự là token CF vừa nhận, không phải token root được thừa kế từ shell.

Sau khi đăng nhập, dùng token vừa nhận để kiểm chứng:

~~~bash
vault token lookup
vault token capabilities secret/data/apps/payment
vault kv get -mount=secret apps/payment
~~~

Kết quả cần quan sát:

- Token có **policy** `payment-secret-read` (có thể kèm `default` tùy cấu hình), TTL phù hợp với role.
- Capability trên `secret/data/apps/payment` bao gồm `read`.
- `vault kv get -mount=secret apps/payment` hoạt động nếu secret tồn tại và policy đúng.
- Token này không được tự động có quyền ghi/cập nhật hay đọc mọi secret khác.

Không dùng root token để kiểm thử quyền của workload; root token bỏ qua nhiều giới hạn ACL thông thường.

## 8. Spring Cloud Vault: tự động dùng danh tính PCF

Đối với ứng dụng Spring Boot dùng Spring Cloud Vault, một cấu hình gọn thường có dạng:

~~~yaml
spring:
  cloud:
    vault:
      uri: https://vault.example.internal:8200
      authentication: PCF
      pcf:
        role: payment-pcf
        pcf-path: cf
~~~

Trong đó:

- `authentication: PCF` yêu cầu client dùng chứng thư instance do CF cung cấp để đăng nhập Vault.
- `pcf.role` phải khớp tên **CF role** đã cấu hình tại Vault.
- `pcf.pcf-path` là tên mount auth, đặt `cf` nếu operator đã bật tại `auth/cf`.
- Nếu không khai báo đường dẫn chứng thư/khóa riêng, cơ chế client sử dụng `CF_INSTANCE_CERT` và `CF_INSTANCE_KEY` của môi trường.

Có thể chỉ định rõ đường dẫn nếu foundation cần:

~~~yaml
spring:
  cloud:
    vault:
      authentication: PCF
      pcf:
        role: payment-pcf
        pcf-path: cf
        instance-certificate: /etc/cf-instance-credentials/instance.crt
        instance-key: /etc/cf-instance-credentials/instance.key
~~~

Các đường dẫn `/etc/...` ở ví dụ chỉ là mẫu; không được dùng thay thế nếu platform thực tế cung cấp đường dẫn khác. Với môi trường không phải PCF, các biến chứng thư sẽ không có và phương thức `PCF` sẽ không hoạt động.

**Phụ thuộc thư viện:** ngoài Spring Cloud Vault phù hợp phiên bản Spring Boot, PCF authentication cần BouncyCastle để ký RSA-PSS. Chọn artifact và phiên bản BouncyCastle tương thích với Spring Vault/JDK của ứng dụng (theo BOM và tài liệu phiên bản đang dùng). Trường hợp thiếu thư viện thường phát sinh lỗi lúc tạo chữ ký hoặc đăng nhập.

Spring Cloud Vault có thể xử lý authentication/session theo cấu hình và cung cấp thành phần Vault cho ứng dụng; cần kiểm tra cơ chế vòng đời token của đúng phiên bản thư viện, đặc biệt khi ứng dụng chạy dài, token hết hạn hoặc instance certificate được xoay vòng.

## 9. Dùng Spring Vault và VaultTemplate trong Java

### 9.1. Cấu hình trực tiếp ClientAuthentication

Nếu ứng dụng cấu hình **Spring Vault Core** trực tiếp, API `PcfAuthentication` và `PcfAuthenticationOptions` cho phép kết nối cùng auth method:

~~~java
import java.net.URI;

import org.springframework.context.annotation.Configuration;
import org.springframework.vault.authentication.ClientAuthentication;
import org.springframework.vault.authentication.PcfAuthentication;
import org.springframework.vault.authentication.PcfAuthenticationOptions;
import org.springframework.vault.client.VaultEndpoint;
import org.springframework.vault.config.AbstractVaultConfiguration;

@Configuration
public class PcfVaultConfiguration extends AbstractVaultConfiguration {

    @Override
    public VaultEndpoint vaultEndpoint() {
        return VaultEndpoint.from(
            URI.create("https://vault.example.internal:8200")
        );
    }

    @Override
    public ClientAuthentication clientAuthentication() {
        PcfAuthenticationOptions options =
            PcfAuthenticationOptions.builder()
                .role("payment-pcf")
                .path("cf")
                .build();

        return new PcfAuthentication(options, vaultClient());
    }
}
~~~

Mẫu trên minh họa các thành phần của Spring Vault; cấu hình URI từ environment/application properties và TLS truststore đúng môi trường khi đưa vào dự án. `PcfAuthenticationOptions` mặc định tìm chứng thư và khóa riêng qua hai biến CF; nó không được gửi token của người dùng cuối vào Vault.

**Chọn một cách tích hợp cho dự án:** dùng auto-configuration của Spring Cloud Vault **hoặc** chủ động cấu hình bean qua Spring Vault Core theo kiến trúc hiện tại, tránh tạo nhiều cấu hình Vault client/token session xung đột.

### 9.2. Đọc một secret KV v2

Sau khi `VaultTemplate` được cấu hình với authentication/session tương ứng, service Java đọc secret bằng đúng mount và key:

~~~java
import org.springframework.stereotype.Service;
import org.springframework.vault.core.VaultKeyValueOperations;
import org.springframework.vault.core.VaultKeyValueOperationsSupport;
import org.springframework.vault.core.VaultTemplate;
import org.springframework.vault.support.VaultResponse;

@Service
public class PaymentCredentialService {

    private final VaultKeyValueOperations kv;

    public PaymentCredentialService(VaultTemplate vaultTemplate) {
        this.kv = vaultTemplate.opsForKeyValue(
            "secret",
            VaultKeyValueOperationsSupport.KeyValueBackend.KV_2
        );
    }

    public String loadProviderEndpoint() {
        VaultResponse response = kv.get("apps/payment");
        if (response == null || response.getData() == null) {
            throw new IllegalStateException(
                "Payment secret does not exist"
            );
        }

        Object endpoint = response.getData().get("endpoint");
        if (!(endpoint instanceof String value) || value.isBlank()) {
            throw new IllegalStateException(
                "Payment endpoint missing or invalid"
            );
        }
        return value;
    }
}
~~~

Ở đây `kv.get("apps/payment")` được thực hiện với token của **workload CF**, còn Vault kiểm tra policy `read` trên API path `secret/data/apps/payment`. `VaultKeyValueOperations` cho KV v2 xử lý phần path `data/` thay vì yêu cầu người gọi tự ghép trong Java.

Trường hợp dùng mật khẩu thật, không trả giá trị ra endpoint công khai và không log `VaultResponse`, token, certificate hoặc private key. Đoạn code chọn field `endpoint` để dễ quan sát; secret mẫu cần chứa trường này trước khi thực hành, ví dụ operator có thể ghi trên mount dev/test:

~~~bash
vault kv put -mount=secret apps/payment \
  endpoint="https://payment-sandbox.example.test" \
  api_key="DUMMY_ONLY"
~~~

Lệnh ghi được chạy bởi operator có quyền quản trị dữ liệu thử nghiệm; workload đọc bằng policy đã giới hạn.

## 10. Kiểm thử hai lớp: xác thực CF và quyền Vault

Thiết kế kiểm thử tách rõ **authentication** (nhận token) và **authorization** (sử dụng token).

| Tình huống | Đăng nhập `auth/cf/login` | Đọc `secret/data/apps/payment` | Ý nghĩa |
| --- | --- | --- | --- |
| Chứng thư đúng CA, chữ ký hợp lệ, role khớp UUID | Thành công, nhận token | Thành công nếu token có `read` | Luồng chuẩn |
| Chứng thư không do CA tin cậy cấp | Bị từ chối | Không có token mới | Chặn danh tính giả |
| Khóa riêng không trùng chứng thư | Bị từ chối | Không có token mới | Chữ ký không hợp lệ |
| Chữ ký quá cũ hoặc lệch giờ quá mức | Bị từ chối | Không có token mới | Chặn yêu cầu cũ/replay |
| Application thuộc space/org khác role ràng buộc | Bị từ chối | Không có token mới | Ràng buộc danh tính |
| Đăng nhập hợp lệ, token thiếu `read` KV | Thành công | Bị Vault từ chối (thường HTTP 403) | Xác thực khác phân quyền |
| Đăng nhập hợp lệ, có `read` nhưng không có `update` | Thành công | Đọc được; ghi bị Vault từ chối | Đặc quyền tối thiểu |
| Token hợp lệ nhưng bị revoke/hết hạn | Cần đăng nhập lại | Yêu cầu cũ thất bại | Vòng đời token |

Dùng identity thật trên sandbox CF để kiểm chứng các trường hợp có thể thực hiện. Với các trường hợp chứng thư/khóa không hợp lệ, dùng bộ fixture dành riêng cho kiểm thử bảo mật hoặc test instance được cô lập; không sao chép private key từ các instance đang chạy trên production.

### Bài kiểm tra đọc và từ chối ghi trên Vault dev/test

Sau khi **đã đăng nhập thành công bằng CF auth**:

~~~bash
# Chỉ token của application, không dùng root.
vault token capabilities secret/data/apps/payment
vault kv get -mount=secret apps/payment

# Bài lab dùng key riêng, ghi phải bị từ chối theo policy chỉ đọc.
vault kv put -mount=secret apps/payment \
  endpoint="https://should-not-change.example.test"
~~~

Kết quả mong đợi:

- `capabilities` có `read`, không có `create`/`update`.
- `get` được phép nếu key tồn tại.
- `put` bị từ chối; secret và version giữ nguyên sau yêu cầu thất bại.

**Không đánh giá thành công chỉ vì login nhận token.** Trường hợp role gắn policy sai, CF login vẫn có thể thành công nhưng `VaultTemplate` đọc KV trả `403`. Ngược lại, `403` tại `auth/cf/login` cần chẩn đoán authentication trước khi kiểm tra ACL của secret.

## 11. Vận hành: thời hạn, xoay vòng và giám sát

### Vòng đời token không đồng nhất vòng đời chứng thư

Instance certificate có thời hạn và có thể được platform đổi/rotate. **Vault token** cũng có TTL riêng, quyền gia hạn, chính sách thu hồi và giới hạn theo role. Một token đã cấp có thể tiếp tục được sử dụng cho đến khi hết hiệu lực dù chứng thư instance thay đổi; việc phát hành lại token đòi hỏi một lần xác thực mới bằng danh tính hợp lệ.

Ứng dụng chạy dài phải có cơ chế quản lý session/renewal hoặc re-authentication được kiểm chứng với phiên bản Spring Vault đang chạy. Đừng giả định chứng thư được rotate là Vault token lập tức được thay. Nếu ứng dụng còn dùng dynamic secrets, lease của từng secret phải được theo dõi riêng.

### Xoay vòng CA và rủi ro khóa CA

CF auth tin tưởng instance certificates được ký bởi **identity CA đã cấu hình**. Khi CA sắp hết hạn hoặc được rotate, Vault có thể cần tin cậy đồng thời CA cũ và CA mới trong khoảng chuyển tiếp theo quy trình quản trị. Lỗi tin cậy CA có thể khiến hàng loạt workload không đăng nhập được.

**Bảo vệ khóa riêng của CF identity CA là điều kiện cốt lõi.** Tài liệu HashiCorp lưu ý một số vai trò đặc quyền trong CF có thể lấy CA private key; nếu khóa này bị lộ, kẻ tấn công có thể tạo chứng thư giả thỏa role. Cần kiểm soát chặt quyền truy cập hệ thống cấp chứng thư, audit và vòng đời CA.

### Những tín hiệu vận hành nên theo dõi

- Tỷ lệ login thành công/thất bại tại `auth/cf/login`, theo workload/role (không ghi token).
- Trễ hoặc lỗi mạng khi Vault truy cập **CF API**, độ tin cậy CA của CF API và chứng thư server.
- Lỗi chênh lệch đồng hồ, chứng thư hết hạn hoặc chuỗi CA không tin cậy.
- Lỗi `403` ở KV/Transit/PKI sau khi đã nhận Vault token, thể hiện policy/path không phù hợp.
- Số lần token cần gia hạn/xác thực lại, các lần bị revoke, tình trạng lease của dynamic secret (nếu có).
- Audit log Vault theo chính sách của tổ chức, correlation ID và metric đã loại bỏ credential/secret.

## 12. Chẩn đoán sự cố theo lớp

| Hiện tượng | Điểm kiểm tra | Hướng xử lý |
| --- | --- | --- |
| Không tìm thấy `CF_INSTANCE_CERT` hoặc `CF_INSTANCE_KEY` | Nền tảng/ứng dụng | Xác minh instance identity feature, biến môi trường và quyền đọc tệp |
| Chứng thư có nhưng Java lỗi tạo RSA-PSS signature | Client Spring Vault | Kiểm tra khóa trùng cert, cấu hình `PcfAuthenticationOptions` và dependency BouncyCastle |
| Login bị từ chối do signer/CA | Vault CF auth | Kiểm tra chuỗi certificate với identity CA, key và cấu hình CA tin cậy; không tắt xác minh |
| Login bị từ chối do role mismatch | Vault role + CF API | Đối chiếu UUID application/space/org hiện tại và `bound_*` |
| Login thất bại sau `cf push` | CF identity/role | Kiểm tra thay đổi instance ID hoặc metadata; tránh ràng buộc instance ID không cần thiết |
| Login thất bại qua proxy | IP checking | Kiểm tra IP khớp chứng thư/đường đi mạng; cân nhắc `disable_ip_matching` **chỉ** sau đánh giá bảo mật |
| `x509: certificate signed by unknown authority` khi gọi CF API | TLS CF API | Cấu hình đúng `cf_api_trusted_certificates`, không bỏ kiểm tra TLS |
| Login thất bại do thời gian ký | Clock/signature window | Đồng bộ NTP, kiểm tra giới hạn cửa sổ thời gian |
| Login thành công nhưng `kv.get` nhận 403 | ACL policy KV v2 | Xem token policies và path `secret/data/apps/payment` |
| KV GET trả lỗi 404 hoặc thiếu field | Secret/data | Kiểm tra mount, key, version, field trong secret, khác lỗi thiếu quyền |
| Đăng nhập lại không được sau rotate | CA/client session | Kiểm tra CA mới đã được Vault tin cậy, chứng thư và key instance mới có thể đọc |
| Token hết hạn, revoke hoặc không renew được | Session/token | Kiểm tra TTL, role, cách session tự gia hạn hoặc xác thực lại |

**Không sửa lỗi bằng cách cấp root token cho ứng dụng**, bỏ các ràng buộc UUID, vô hiệu hóa TLS hoặc in nội dung private key/token ra log. Các cách đó có thể che dấu triệu chứng nhưng mở rộng đáng kể quyền truy cập.

## 13. Câu hỏi tình huống và bài tập

**Tình huống 1:** Hai ứng dụng CF cùng trong một space, chỉ một ứng dụng có quyền đọc `secret/data/apps/payment`. Nếu role chỉ ràng buộc space, cơ chế nào ngăn ứng dụng thứ hai đăng nhập bằng role đó? Bạn cần bổ sung `bound_application_ids` và rà soát ACL.

**Tình huống 2:** Vault chấp nhận login nhưng `VaultTemplate` ném lỗi 403 khi đọc secret. Hãy xác định token đã được cấp, đọc policy gắn với token và so sánh **KV v2 API path** với ACL. Không kết luận chứng thư sai chỉ từ một lỗi 403 ở KV.

**Tình huống 3:** Sau khi nền tảng rotate identity CA, ứng dụng đồng loạt không lấy được token mới. Hãy lập thứ tự kiểm tra: CA đang tin cậy ở Vault, chứng thư instance vừa phát hành, thời hạn/chuỗi CA và đường đi đến CF API.

**Tình huống 4:** Nhóm vận hành muốn tái sử dụng token PCF cho người dùng cuối đăng nhập website. Vì sao điều đó sai mô hình? Token PCF đại diện **workload**, không đại diện từng người dùng. API vẫn phải xác thực và phân quyền người dùng bằng cơ chế dành cho họ.

**Tình huống 5:** Dịch vụ chuyển từ đọc KV sang gọi Transit encrypt và xin chứng thư từ PKI. Role CF có cần thay đổi không? Có thể giữ phương thức xác thực workload nhưng **policy ACL phải cấp thêm đúng API path/capability** của Transit/PKI, kiểm soát đặc quyền tối thiểu và TTL/lease phù hợp.

## 14. Tiêu chí hoàn thành

Bạn hoàn thành bài khi có thể chứng minh đủ các điểm sau:

1. Mô tả được **CF instance certificate + private key** tạo bằng chứng danh tính, và Vault token chỉ xuất hiện **sau khi Vault CF auth xác thực thành công**.
2. Giải thích được bốn trường login `role`, `cf_instance_cert`, `signing_time`, `signature` và vai trò của CA, CF API, UUID role bounds.
3. Viết được policy KV v2 chỉ đọc và cấu hình role giới hạn application/space/org.
4. Cấu hình được `PCF` authentication của Spring Cloud Vault hoặc `PcfAuthentication` của Spring Vault Core; ứng dụng truy cập bằng `VaultTemplate`.
5. Kiểm chứng được login hợp lệ, một trường hợp login bị từ chối, một thao tác KV được phép và một thao tác KV bị từ chối.
6. Biết vì sao phải quản lý TLS, CA, private key, token TTL và re-authentication trong vận hành.

**Nguồn tài liệu tham chiếu để tra cứu theo phiên bản triển khai:**

- HashiCorp: [Cloud Foundry (CF) auth method](https://developer.hashicorp.com/vault/docs/auth/cf).
- HashiCorp: [Cloud Foundry auth HTTP API](https://developer.hashicorp.com/vault/api-docs/auth/cf).
- Spring Vault: [Authentication — PCF](https://docs.spring.io/spring-vault/reference/vault/authentication.html).
- Spring Cloud Vault: [Authentication methods — Pivotal Cloud Foundry](https://docs.spring.io/spring-cloud-vault/reference/authentication.html).

Nền tảng của bài là **tin cậy danh tính do PCF quản lý, xác minh bằng chứng mật mã và giới hạn quyền qua Vault role/policy**. Kỹ thuật đó cho phép dịch vụ Java nhận quyền truy cập secret theo đúng workload và tiếp tục vận hành các luồng KV, Transit, PKI hay secret lease mà không cần nhúng Vault token dài hạn vào mã nguồn.
