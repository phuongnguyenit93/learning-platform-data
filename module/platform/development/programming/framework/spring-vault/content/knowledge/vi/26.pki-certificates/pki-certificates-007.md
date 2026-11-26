# Thu hồi chứng thư theo số sê-ri

## 1. Vì sao cần thu hồi chứng thư trước hạn?

Chứng thư số X.509 có khoảng thời gian hiệu lực từ `notBefore` đến `notAfter`. Trong khoảng thời gian này, hệ thống xác thực có thể chấp nhận chứng thư nếu chuỗi tin cậy, mục đích sử dụng, tên định danh và các điều kiện kiểm tra khác đều hợp lệ. Nhưng có những trường hợp phải **ngừng tin cậy chứng thư trước khi hết hạn**:

- Khóa riêng của máy chủ hoặc client bị lộ hay nghi bị xâm phạm.
- Một máy chủ, workload, tài khoản dịch vụ hoặc nhân sự không còn được phép sử dụng chứng thư.
- Chứng thư được cấp sai tên miền, sai định danh hoặc theo sai policy.
- Khóa/cấu hình của một thành phần cần thay thế khẩn cấp sau sự cố.

**Thu hồi chứng thư** (*certificate revocation*) là thao tác CA ghi nhận một chứng thư đã cấp không còn được tin cậy kể từ thời điểm thu hồi. Với **HashiCorp Vault PKI secrets engine**, một phương thức phổ biến là gửi **số sê-ri** (*serial number*) của chứng thư tới endpoint `pki/revoke`.

Trong module **Spring Vault**, ứng dụng Java có thể gọi endpoint này qua `VaultTemplate`/`VaultOperations`. Tuy nhiên, thành công của API chỉ là một phần quy trình: để chứng thư bị từ chối thực sự, bên kiểm tra chứng thư cũng cần dùng thông tin thu hồi, chẳng hạn CRL hoặc OCSP, theo cấu hình kiểm tra tin cậy của mình.

**Mục tiêu bài học:** sau khi đọc, bạn có thể xác định serial cần thu hồi, cấp quyền Vault đúng phạm vi, gọi thao tác revoke bằng CLI/HTTP/Java, xác minh hiệu lực thu hồi và xây dựng quy trình ứng cứu có thể kiểm toán.

## 2. Nền tảng: serial, issuer, CA và trạng thái thu hồi

### 2.1. Số sê-ri định danh chứng thư như thế nào?

Theo mô hình X.509, số sê-ri do CA cấp và phải được xét **trong phạm vi CA phát hành (issuer)**. Hai chứng thư có cùng common name (`CN`) vẫn có thể khác serial; một dịch vụ được cấp lại chứng thư cũng nhận một chứng thư mới với serial mới.

Ví dụ thông tin nghiệp vụ cần lưu khi cấp chứng thư:

| Thuộc tính | Ví dụ minh họa | Ý nghĩa |
| --- | --- | --- |
| PKI mount | `pki-app` | Định vị secrets engine đang quản lý chứng thư |
| Issuer | `app-intermediate-ca` | CA phát hành, cần phân biệt khi có nhiều CA |
| Serial number | `4a:6f:12:9b:...` | Định danh chứng thư cần thu hồi trong phạm vi CA |
| Subject/SAN | `orders.internal.example` | Danh tính ghi trên chứng thư; không thay serial |
| `notAfter` | `2027-02-01T00:00:00Z` | Thời điểm hết hạn bình thường |
| Trạng thái nội bộ | `ACTIVE`, `REVOKE_REQUESTED`, `REVOKED` | Trạng thái theo dõi của ứng dụng, không tự thay thế bằng chứng PKI |

Trong ứng dụng có nhiều PKI mount hoặc CA, hãy lưu ít nhất **mount/issuer tương ứng cùng serial**. Đừng chỉ lưu `CN` hay tên host rồi đoán chứng thư nào cần thu hồi. Một yêu cầu thu hồi sai serial có thể ảnh hưởng chứng thư khác hoặc không tìm thấy chứng thư cần xử lý.

Serial thường được biểu diễn dưới dạng số hexadecimal, có thể có ký tự phân cách. **Ưu tiên giữ nguyên giá trị `serial_number` mà Vault trả về lúc cấp chứng thư.** Không chuyển sang số nguyên Java `int`/`long`: serial có thể dài hơn nhiều so với các kiểu đó. Nếu cần chuẩn hóa hoặc chuyển định dạng, phải xác minh định dạng đầu vào được phiên bản Vault đang dùng hỗ trợ.

### 2.2. Thu hồi, hết hạn và xóa khóa là những việc khác nhau

- **Hết hạn**: đồng hồ đi qua `notAfter`; bộ kiểm tra chứng thư từ chối chứng thư hết hạn mà không cần thao tác revoke.
- **Thu hồi**: CA đánh dấu một chứng thư cụ thể không còn hợp lệ trước hoặc trong thời hạn của nó; không làm thay đổi trực tiếp `notAfter` trong tệp PEM đã cấp.
- **Cấp lại/luân chuyển chứng thư**: tạo một chứng thư mới, thường nên dùng cặp khóa mới; chứng thư cũ chỉ thực sự bị thu hồi nếu có thao tác revoke tương ứng.
- **Xóa hoặc thay khóa trong hệ thống ứng dụng**: không tự tạo thông tin thu hồi X.509 tại CA.
- **Token/lease của Vault**: việc hết hạn hoặc thu hồi Vault token dùng gọi API không mặc nhiên thu hồi chứng thư X.509 đã được cấp trước đó.

Hành động thu hồi thường không có thao tác “undo” an toàn để chứng thư trở lại như cũ. Khi thu hồi nhầm hoặc thu hồi vì sự cố, hướng khắc phục đúng là **cấp chứng thư mới** rồi triển khai lại danh tính mới.

## 3. Luồng thu hồi chứng thư với Vault PKI

~~~mermaid
sequenceDiagram
    autonumber
    participant Operator as Security/Operations
    participant Service as Spring Boot revoke service
    participant Vault as Vault PKI
    participant Store as Inventory/Audit DB
    participant Peer as TLS verifier

    Operator->>Service: Yêu cầu thu hồi certificateId + lý do
    Service->>Store: Tìm mount, issuer, serial; xác minh quyền
    Store-->>Service: pki-app + serial tương ứng
    Service->>Vault: POST /v1/pki-app/revoke {serial_number}
    Note over Service,Vault: HTTPS + Vault token của workload
    Vault-->>Service: Trả kết quả ghi nhận thu hồi
    Service->>Store: Ghi trạng thái + thời điểm + audit metadata
    Service-->>Operator: Kết quả và mã đối chiếu
    Vault-->>Peer: Thông tin revocation qua CRL/OCSP
    Peer->>Peer: Kiểm tra chứng thư và trạng thái thu hồi
~~~

Sơ đồ có hai giai đoạn khác nhau:

1. **Vault ghi nhận thao tác revoke:** yêu cầu được xác thực, phân quyền và xử lý ở PKI engine đang quản lý chứng thư.
2. **Hệ thống tiêu thụ tin về revoke:** các client, reverse proxy, gateway hoặc TLS peer cần truy xuất và thực sự kiểm tra thông tin thu hồi trước khi quyết định tin chứng thư.

Không được suy ra rằng mọi kết nối TLS đang tồn tại sẽ bị cắt ngay khi Vault API trả thành công. Việc sử dụng CRL/OCSP, thời gian cache và chính sách kiểm tra trạng thái của từng bên xác thực quyết định thời điểm tác động.

## 4. Điều kiện tiên quyết và quyền truy cập

Giả sử môi trường đã có:

- Vault đã được khởi tạo và mở khóa, có kết nối HTTPS từ ứng dụng.
- PKI secrets engine gắn tại đường dẫn `pki-app`, có CA/issuer và role cấp chứng thư được quản trị trước đó.
- Chứng thư đích là chứng thư do CA tương ứng quản lý; serial được lưu trong inventory khi cấp.
- Danh tính workload thực hiện thu hồi có Vault policy tối thiểu và cơ chế đăng nhập phù hợp (Kubernetes auth, AppRole, JWT/OIDC...).
- Các bên xác thực chứng thư đã có chiến lược kiểm tra thu hồi qua CRL/OCSP theo yêu cầu an toàn của hệ thống.

### 4.1. Policy chỉ cho phép thao tác thu hồi

Ví dụ policy HCL cho service chuyên thu hồi tại một mount:

~~~hcl
# pki-revoker.hcl
path "pki-app/revoke" {
  capabilities = ["update"]
}
~~~

Quản trị viên cấp policy:

~~~bash
vault policy write pki-revoker pki-revoker.hcl
~~~

Đối với endpoint `POST /v1/pki-app/revoke`, capability `update` là quyền cần thiết. Không cần cấp `create`/`update` trên `pki-app/roles/*`, `pki-app/root/*`, `pki-app/issuers/*` hoặc toàn bộ `pki-app/*` chỉ để thu hồi theo serial.

Điều quan trọng là **phân quyền ở hai tầng**: Vault policy giới hạn **workload nào** được gọi revoke; tầng nghiệp vụ Java vẫn phải xác minh **người dùng hoặc tác vụ nào** được quyền yêu cầu thu hồi **chứng thư nào**. Một HTTP endpoint cho phép nhập serial bất kỳ, chuyển thẳng vào token revoker có thể bị lạm dụng để thu hồi hàng loạt chứng thư.

Nếu có nhiều đơn vị hoặc môi trường, nên dùng PKI mount riêng và token riêng để tách quyền. Trên cùng một mount, quyền `pki-app/revoke` về cơ bản bao phủ mọi serial mà endpoint đó có thể xử lý; ứng dụng phải thực thi thêm quyền theo danh sách chứng thư được giao quản lý.

### 4.2. Gắn token với workload

Ví dụ đối với một job chạy trên Kubernetes, Vault auth role có thể ánh xạ ServiceAccount `pki-revoker` ở namespace `security-ops` sang policy `pki-revoker`:

~~~bash
# Chỉ chạy bởi người quản trị sau khi auth/kubernetes đã cấu hình.
vault write auth/kubernetes/role/pki-revoker \
  bound_service_account_names=pki-revoker \
  bound_service_account_namespaces=security-ops \
  token_policies=pki-revoker \
  token_ttl=30m
~~~

Spring Vault dùng cơ chế `ClientAuthentication` tương ứng với hạ tầng và thiết lập session/token theo vòng đời phù hợp. Tránh token root, token dài hạn nằm trong source code hoặc ghi token vào log. Cần kiểm soát riêng ai được quyền sửa Kubernetes ServiceAccount, Vault role và Vault policy.

## 5. Xác định chính xác số sê-ri cần thu hồi

### 5.1. Lấy serial từ kết quả cấp chứng thư

Khi ứng dụng hoặc công cụ phát hành chứng thư qua Vault PKI `pki-app/issue/<role>`, phản hồi thường có `data.serial_number`, `data.certificate`, `data.issuing_ca` và thông tin khóa tùy cách cấp. Ví dụ logic Java:

~~~java
VaultResponse issued = vaultOperations.write(
        "pki-app/issue/service-client",
        Map.of("common_name", "orders.internal.example", "ttl", "24h"));

if (issued == null || issued.getData() == null) {
    throw new IllegalStateException("Missing PKI issue response");
}

String serial = (String) issued.getData().get("serial_number");
if (serial == null || serial.isBlank()) {
    throw new IllegalStateException("PKI response does not contain serial");
}

// Ghi serial + mount/issuer + certificateId vào inventory kiểm soát quyền.
// Tuyệt đối không log toàn bộ issued.getData(): có thể chứa private_key.
~~~

Đoạn mã chỉ minh họa **cách lấy serial**; hoạt động cấp chứng thư là quyền và quy trình riêng. Khi Vault trả cả private key trong phản hồi, phải bảo vệ nghiêm ngặt bộ nhớ, kênh truyền, nơi lưu và log. Không dùng policy thu hồi để cấp chứng thư.

### 5.2. Đối chiếu từ một tệp PEM có sẵn

Nếu đã có tệp chứng thư của chính workload hoặc máy chủ cần thu hồi:

~~~bash
openssl x509 -in service-cert.pem -noout -serial -issuer -subject -dates
~~~

Lệnh trên giúp xem serial và issuer từ chứng thư. OpenSSL có thể hiển thị serial dưới dạng chuỗi hex liên tục, trong khi Vault thường biểu diễn serial với dấu phân cách. Khi chuyển định dạng, phải đối chiếu giá trị với inventory hoặc phản hồi cấp chứng thư; **không gửi nhầm serial của intermediate CA, leaf khác hoặc mount khác**.

Đối với chứng thư chuỗi, cần kiểm tra bạn đang đọc **leaf certificate** cần revoke chứ không phải file `ca.pem`. Thu hồi CA/intermediate là sự kiện ảnh hưởng diện rộng, cần quy trình ứng cứu riêng và đánh giá toàn bộ chứng thư con.

## 6. Thu hồi theo serial qua Vault CLI và HTTP API

Giả sử serial mẫu được cấp tại mount `pki-app`:

~~~text
4a:6f:12:9b:23:cd
~~~

Đây là giá trị minh họa; trong thực tế hãy dùng serial chính xác từ dữ liệu của chứng thư cần thu hồi.

### 6.1. Dùng Vault CLI

~~~bash
# Dùng phiên đăng nhập Vault với policy pki-revoker.
vault write pki-app/revoke serial_number="4a:6f:12:9b:23:cd"
~~~

Vault sẽ trả dữ liệu kết quả về thao tác, trong đó có thể có thời điểm thu hồi như `revocation_time`. Thời điểm được dùng trong audit nội bộ cần lấy từ phản hồi thực tế; không tự suy đoán rằng thời gian trên máy client chính là thời gian CA ghi nhận.

Đây là một thao tác thay đổi trạng thái có hậu quả bảo mật, nên trước khi chạy trong production phải kiểm tra yêu cầu, danh tính chứng thư, lý do và quyền của người vận hành.

### 6.2. Gọi HTTP API

~~~http
POST /v1/pki-app/revoke HTTP/1.1
Host: vault.internal.example
X-Vault-Token: <workload-token>
Content-Type: application/json

{
  "serial_number": "4a:6f:12:9b:23:cd"
}
~~~

Phản hồi thành công thường chứa các trường thông tin thu hồi trong `data`. Ví dụ dạng rút gọn:

~~~json
{
  "data": {
    "revocation_time": 1790000000
  }
}
~~~

Giá trị `revocation_time` trong ví dụ chỉ để minh họa định dạng thời gian Unix, **không phải kết quả đã thực thi**. Tùy phiên bản Vault và cấu hình PKI, phản hồi có thể có thêm trường khác.

Với cả CLI và HTTP, phải xác định chính xác mount. `pki-app/revoke` và `pki/revoke` là hai đường dẫn khác nhau nếu môi trường có hai PKI mount; không thay thế tùy tiện.

## 7. Triển khai bằng Spring Vault

Spring Vault cung cấp `VaultOperations` để gọi các endpoint Vault và `VaultTemplate` là một triển khai thông dụng. Đoạn mã sau giữ nguyên endpoint Transit/PKI dạng đường dẫn logic **không có prefix `/v1/`**, vì Spring Vault xử lý phần URL API này.

### 7.1. Service thu hồi theo serial

~~~java
package com.example.security.pki;

import java.time.Instant;
import java.util.Map;
import java.util.Objects;
import java.util.regex.Pattern;

import org.springframework.stereotype.Service;
import org.springframework.vault.core.VaultOperations;
import org.springframework.vault.support.VaultResponse;

@Service
public class PkiCertificateRevocationService {

    private static final String REVOKE_PATH = "pki-app/revoke";

    // Chấp nhận hex và dấu phân cách; giới hạn chiều dài request.
    // Không đổi giá trị serial sau khi đã xác minh nguồn cấp.
    private static final Pattern SERIAL_PATTERN =
            Pattern.compile("[0-9a-fA-F:-]{1,256}");

    private final VaultOperations vaultOperations;

    public PkiCertificateRevocationService(VaultOperations vaultOperations) {
        this.vaultOperations = vaultOperations;
    }

    public RevocationReceipt revokeBySerial(String serialNumber) {
        Objects.requireNonNull(serialNumber, "serialNumber");
        String serial = serialNumber.trim();

        if (!SERIAL_PATTERN.matcher(serial).matches()) {
            throw new IllegalArgumentException("Invalid certificate serial");
        }

        VaultResponse response = vaultOperations.write(
                REVOKE_PATH,
                Map.of("serial_number", serial));

        if (response == null || response.getData() == null) {
            throw new IllegalStateException("Missing Vault PKI response");
        }

        Object rawTime = response.getData().get("revocation_time");
        if (!(rawTime instanceof Number time)) {
            throw new IllegalStateException(
                    "Vault PKI response has no revocation_time");
        }

        return new RevocationReceipt(
                serial, Instant.ofEpochSecond(time.longValue()));
    }

    public record RevocationReceipt(
            String serialNumber, Instant revokedAt) {}
}
~~~

Đoạn mã dùng cú pháp `record` và pattern matching phù hợp với Java 17 trở lên. Với phiên bản Java cũ, dùng POJO và kiểm tra kiểu truyền thống.

**Điểm cần chú ý:**

- `REVOKE_PATH` cần lấy từ cấu hình triển khai được kiểm soát nếu ứng dụng hỗ trợ nhiều PKI mount. Không xây dựng path tùy ý từ tham số HTTP của client.
- `serial_number` nằm trong **JSON body**, không được nối vào URL. Dữ liệu cần xuất phát từ inventory/issuance và được đối chiếu với issuer trước khi gọi.
- `revocation_time` phải lấy từ phản hồi Vault khi có. Phần phản hồi không đúng hợp đồng cần được báo lỗi; audit phải phân biệt “Vault có thể đã ghi nhận” với “ứng dụng đọc được receipt”.
- Mọi lỗi HTTP/permission/connection của Spring Vault phải được xử lý ở tầng gọi phù hợp. Không đánh dấu thành công chỉ vì request đã được gửi.
- Chỉ service đã xác minh quyền nghiệp vụ mới được gọi `revokeBySerial`. Không mở một endpoint công khai nhận serial bất kỳ.

**Về kiểm tra đầu vào:** regex minh họa chỉ là bước lọc đơn giản. Nó không chứng minh serial tồn tại, thuộc đúng CA hoặc hợp lệ với từng phiên bản Vault. Việc xác định **certificateId → mount + issuer + serial** trong kho dữ liệu đáng tin cậy mới là kiểm tra quan trọng.

### 7.2. Gắn với quy trình nghiệp vụ

Giả sử có bảng `issued_certificates` lưu các trường `id`, `mount`, `issuer`, `serial`, `owner`, `status`. Tầng ứng dụng nên điều phối theo hướng:

~~~java
// Pseudocode: những interface dưới đây thuộc ứng dụng, không phải Spring Vault.
void revokeCertificate(UUID certificateId, Operator operator, String reason) {
    IssuedCertificate cert = certificateStore.findById(certificateId)
            .orElseThrow();

    authorization.checkCanRevoke(operator, cert);
    requireApprovedReason(reason);
    verifyExpectedMountAndIssuer(cert);

    audit.recordRevocationRequested(operator, cert.id(), reason);

    // Phải có cơ chế xử lý trạng thái trung gian khi Vault đã xử lý
    // nhưng việc ghi database hoặc nhận response thất bại.
    var receipt = revocationService.revokeBySerial(cert.serial());

    certificateStore.markRevoked(cert.id(), receipt.revokedAt());
    audit.recordRevocationConfirmed(operator, cert.id(), receipt.revokedAt());
}
~~~

Vì đây là lời gọi qua mạng tới hệ thống ngoài, việc cập nhật DB và revoke trong Vault **không tạo thành một transaction phân tán nguyên tử**. Trong production cần lưu yêu cầu và trạng thái trung gian, có cơ chế đối soát, chống xử lý trùng từ phía ứng dụng, và kế hoạch khôi phục khi DB ghi lỗi hoặc kết nối bị ngắt sau khi Vault đã xử lý.

Nếu thời gian chờ của API bị vượt quá sau khi gửi request, không thể tự kết luận request chưa đến Vault. Trước khi retry tự động, hãy kiểm tra trạng thái đã được ghi nhận và tính an toàn của thao tác lặp theo phiên bản Vault; không giả định mọi lần revoke lặp luôn trả cùng kết quả.

### 7.3. Cấu hình client Spring Vault và vòng đời token

Ứng dụng có thể nhận `VaultOperations` qua một bean `VaultTemplate` được Spring Vault/Spring Cloud Vault cấu hình với:

- HTTPS endpoint và truststore phù hợp.
- `ClientAuthentication` theo danh tính workload; các service phải có danh tính riêng.
- Cơ chế đăng nhập lại hoặc quản lý session/token theo auth method; TTL token cần được theo dõi.
- Timeout, retry giới hạn cho sự cố tạm thời và giới hạn số yêu cầu revoke song song.

Token có thể hết hạn hay bị revoke trong khi chứng thư đã thu hồi vẫn giữ trạng thái thu hồi. Ngược lại, **thu hồi token Vault không tự thu hồi chứng thư X.509**. Hai loại vòng đời này phải được theo dõi độc lập, đặc biệt trong quy trình rời tổ chức hoặc xử lý khóa bị lộ.

## 8. Kiểm tra thu hồi qua CRL và OCSP

### 8.1. CRL là gì?

**Certificate Revocation List (CRL)** là danh sách do CA phát hành, chứa các serial đã bị thu hồi và thông tin liên quan. Client kiểm tra CRL do đúng CA phát hành, xác minh chữ ký và thời hạn của CRL, rồi đối chiếu serial của chứng thư.

Một số chứng thư chứa **CRL Distribution Points (CDP)**, chỉ ra vị trí lấy CRL. Vault PKI có cấu hình URL cho phép đưa các địa chỉ phân phối tương ứng vào chứng thư được cấp. Ví dụ:

~~~bash
# Chỉ chạy bởi quản trị viên PKI trong môi trường đã thiết kế URL phù hợp.
vault write pki-app/config/urls \
  issuing_certificates="https://pki.example.internal/v1/pki-app/ca" \
  crl_distribution_points="https://pki.example.internal/v1/pki-app/crl" \
  ocsp_servers="https://pki.example.internal/v1/pki-app/ocsp"
~~~

Các URL trên chỉ là ví dụ. Tùy cấu hình Vault, issuer, HA/replication và phiên bản API, đường dẫn phân phối có thể khác. Chúng phải truy cập được từ **các bên kiểm tra chứng thư**; một URL chỉ truy cập được nội bộ Vault nhưng không truy cập được từ client thì không giúp client lấy CRL.

Có thể kiểm tra một CRL được xuất bản ở dạng PEM bằng:

~~~bash
# URL minh họa: cần TLS hợp lệ và endpoint PKI được cấu hình tương ứng.
curl --fail --silent --show-error \
  "https://pki.example.internal/v1/pki-app/crl/pem" \
  -o current-crl.pem

openssl crl -in current-crl.pem -noout -text
~~~

Kiểm tra serial mục tiêu trong danh sách, đồng thời xác minh CRL được ký bởi CA phù hợp, còn hiệu lực và đã được cập nhật. Lệnh `openssl crl -text` hiển thị dữ liệu để chẩn đoán; một hệ thống xác thực phải thực hiện kiểm tra chữ ký/issuer/thời hạn đúng chuẩn thay vì chỉ tìm chuỗi serial trong một file không được xác thực.

### 8.2. OCSP là gì?

**Online Certificate Status Protocol (OCSP)** cho phép bên kiểm tra chứng thư hỏi trạng thái của một chứng thư từ responder phù hợp, thay vì phải tải toàn bộ CRL. Vault PKI có thể cung cấp endpoint OCSP theo cấu hình phiên bản triển khai; chứng thư thường khai báo địa chỉ qua **Authority Information Access (AIA)**.

OCSP, CRL và thời gian cache có đặc điểm riêng. Không nên khẳng định “gọi revoke xong thì mọi TLS client lập tức từ chối”: một client có thể không bật kiểm tra revocation, dùng CRL/OCSP cache, hoặc có hành vi *soft-fail* khi không truy cập được nguồn trạng thái.

### 8.3. Hệ quả thực tế khi thu hồi

| Tình huống | Ý nghĩa vận hành |
| --- | --- |
| Vault trả revoke thành công | CA đã ghi nhận yêu cầu; cần xác minh kênh phân phối trạng thái thu hồi |
| CRL đã có serial bị thu hồi | Client kiểm tra đúng CRL mới có thể phát hiện chứng thư đã bị thu hồi |
| OCSP trả trạng thái revoked | Client dùng OCSP phù hợp có thể từ chối chứng thư đó |
| Client không kiểm tra CRL/OCSP | Chứng thư có thể vẫn được chấp nhận nếu các điều kiện khác hợp lệ |
| Kết nối TLS đang hoạt động | Không nhất thiết bị ngắt ngay; cần biện pháp cắt kết nối hoặc rút quyền riêng |
| Client dùng CRL/OCSP cũ trong cache | Có độ trễ cho đến khi cập nhật theo chính sách kiểm tra |

Với hệ thống nhạy cảm, phải kiểm thử rõ **revocation checking** trên đúng client library, JVM/TLS stack, ingress, service mesh, load balancer hoặc thiết bị mạng đang vận hành. Đừng chỉ kiểm tra Vault API rồi mặc định chính sách TLS đã được thực thi.

## 9. Xử lý sự cố, lỗi API và giám sát

### 9.1. Phân loại lỗi trước khi hành động

| Dấu hiệu | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| HTTP `403` | Token thiếu quyền `update` trên `pki-app/revoke` hoặc bị ràng buộc sai policy | Kiểm tra auth role, token policy và mount; không cấp token root để xử lý tạm |
| HTTP `400` | Serial không hợp lệ, không được nhận diện hoặc trạng thái đầu vào không được chấp nhận | Kiểm tra serial từ issuance, CA/issuer và yêu cầu thực tế |
| HTTP `404` | Sai PKI mount, thiếu endpoint hoặc tài nguyên tương ứng | Xác minh mount và cấu hình PKI đang triển khai |
| HTTP `429`/`5xx` | Giới hạn tải hoặc lỗi Vault/hạ tầng | Giới hạn retry theo backoff và giám sát khả dụng |
| Timeout/đứt kết nối | Trạng thái xử lý request không chắc chắn | Đối soát trước khi lặp; không đánh dấu thất bại cuối cùng ngay |
| Vault báo thành công, client vẫn chấp nhận cert | CRL/OCSP chậm, cache, client không bật kiểm tra revocation | Kiểm tra URL phân phối, CRL/OCSP và cấu hình trust thực tế |

Không xử lý mọi exception bằng cách trả `REVOKED`. Đặc biệt, timeout không cho biết chắc chắn Vault đã ghi nhận hay chưa; ghi trạng thái trung gian `UNKNOWN`/`RECONCILIATION_REQUIRED` sẽ hỗ trợ điều tra và đối soát.

### 9.2. Audit và metrics

Với mỗi yêu cầu thu hồi, hệ thống nên lưu có kiểm soát:

- `certificateId`, PKI mount/issuer, serial và định danh chủ sở hữu.
- Ai yêu cầu, ai phê duyệt (nếu cần), lý do và thời điểm yêu cầu.
- Mã đối chiếu/idempotency key của nghiệp vụ, kết quả trả về từ Vault và thời điểm ghi nhận.
- Trạng thái đối soát, thời điểm CRL/OCSP đã phản ánh revocation theo phép kiểm tra của hệ thống.

Theo dõi số lượng revoke theo kết quả, tỷ lệ `403`/`4xx`/`5xx`, độ trễ p95/p99, token authentication failures, độ mới của CRL và khả năng truy cập responder. Tránh log private key, token Vault, toàn bộ payload phát hành chứng thư hoặc thông tin không cần thiết. Audit của Vault và audit nghiệp vụ phục vụ các mục đích bổ sung nhau.

### 9.3. Khi khóa riêng thực sự bị lộ

Nếu nguy cơ đang diễn ra, nên xem đây là một quy trình ứng cứu:

1. Xác định chính xác chứng thư, CA và nơi sử dụng; khoanh vùng phiên bản khóa và các workload liên quan.
2. Thu hồi chứng thư và xác minh phản hồi Vault.
3. Phân phối/cập nhật trạng thái revocation; kiểm tra đường đi CRL/OCSP từ các TLS peer.
4. Ngừng sử dụng cặp khóa cũ, khóa hoặc cô lập workload bị ảnh hưởng; cắt các kết nối không còn tin cậy khi cần.
5. Tạo cặp khóa mới, phát hành chứng thư mới theo quyền thích hợp, triển khai có kiểm soát.
6. Lưu bằng chứng sự cố và kiểm thử rằng chứng thư cũ bị từ chối ở các điểm xác thực quan trọng.

Không giữ private key cũ chỉ vì chứng thư mới có tên miền giống chứng thư trước.

## 10. Kiểm thử tích hợp với Vault PKI

Để kiểm thử đúng hành vi, nên dùng Vault test cô lập với PKI mount/CA/role dành riêng cho test. Không tạo rồi thu hồi chứng thư production chỉ để kiểm tra mã thử.

Các trường hợp cần kiểm chứng:

1. **Happy path**: phát hành một leaf certificate test, lưu serial, gọi `revoke` qua Spring Vault bằng token chỉ có quyền thu hồi, xác nhận phản hồi và trạng thái đã ghi nhận.
2. **CRL xuất bản**: tải CRL của đúng CA sau revoke, xác minh chữ ký/hiệu lực và serial được ghi nhận; thời gian CRL phản ánh thu hồi có thể phụ thuộc cấu hình engine.
3. **Phân quyền**: token chỉ có quyền issue hoặc chỉ đọc không thể gọi `pki-app/revoke`.
4. **Sai đối tượng**: serial không tồn tại, serial của mount khác hoặc issuer không phù hợp phải được phát hiện và xử lý mà không đánh dấu chứng thư mục tiêu đã thu hồi thành công.
5. **Lỗi mạng**: giả lập timeout sau khi request đã được gửi; bảo đảm trạng thái nội bộ có thể đối soát thay vì báo sai.
6. **Đầu cuối TLS**: thiết lập client kiểm tra CRL/OCSP thật, xác nhận chứng thư cũ bị từ chối sau khi revocation đã được phân phối.
7. **Token và lease**: hết hạn Vault token không đồng nghĩa chứng thư X.509 hết hạn hoặc bị thu hồi; kiểm thử hai vòng đời riêng biệt.

Ví dụ phác thảo test JUnit/AssertJ (giả sử fixture đã cấu hình Vault test và tạo chứng thư):

~~~java
@Test
void revokesCertificateBySerial() {
    String serial = testCertificate.serialNumber();

    var receipt = revocationService.revokeBySerial(serial);

    assertThat(receipt.serialNumber()).isEqualTo(serial);
    assertThat(receipt.revokedAt()).isNotNull();

    // Fixture chờ/đối soát CRL phù hợp, sau đó xác minh trạng thái
    // qua kiểm tra CRL hoặc OCSP đã được cấu hình cho CA test.
    assertThat(testPkiVerifier.isRevoked(serial)).isTrue();
}
~~~

Đây là ví dụ cấu trúc test, không phải test chạy độc lập: `testCertificate` và `testPkiVerifier` là fixture phải tự triển khai. Tránh dùng `Thread.sleep` cố định để chờ CRL; nên dùng polling có timeout hữu hạn dựa trên trạng thái quan sát được, và lưu bằng chứng lỗi nếu hết thời gian.

## 11. Bài thực hành: thu hồi client certificate của một workload

**Bối cảnh:** service `orders-worker` dùng mTLS để gọi một API nội bộ. Workload bị ngừng hoạt động; bạn cần thu hồi chứng thư đang được sử dụng dù chưa tới hạn `notAfter`.

Thực hiện lần lượt trong môi trường test:

1. Phát hành chứng thư client từ PKI mount `pki-app` bằng role test; ghi lại serial, issuer, chủ sở hữu và hạn dùng.
2. Tạo policy `pki-revoker` chỉ có `update` ở `pki-app/revoke` và đăng nhập bằng danh tính workload test.
3. Từ Spring Vault, gọi `PkiCertificateRevocationService.revokeBySerial(serial)`; lưu thời điểm thu hồi và kết quả audit.
4. Kiểm tra CRL/OCSP tương ứng, xác nhận serial được coi là đã thu hồi bởi bên xác thực đã bật kiểm tra revocation.
5. Thử một kết nối mTLS mới bằng chứng thư đã thu hồi để quan sát hành vi từ chối; đồng thời xác minh một chứng thư test khác chưa bị thu hồi vẫn hợp lệ.
6. Thử gọi revoke bằng token không có quyền và với serial sai; xác nhận không báo thành công.
7. Cấp chứng thư mới cho workload thay thế, sử dụng cặp khóa mới và cập nhật inventory.

**Câu hỏi tự kiểm tra:**

1. Vì sao `CN` và serial không thể dùng thay thế nhau khi yêu cầu thu hồi?
2. Vì sao cần lưu đồng thời PKI mount/issuer và serial trong hệ thống có nhiều CA?
3. `vault write pki-app/revoke serial_number=...` khác gì với thu hồi Vault token?
4. Sau khi Vault trả thành công, vì sao một số client TLS vẫn có thể chấp nhận chứng thư?
5. Nếu hệ thống mất kết nối đúng lúc gọi revoke, làm sao tránh báo nhầm trạng thái thành công/thất bại?
6. Vì sao token chỉ có quyền thu hồi vẫn cần tầng authorization nghiệp vụ ở Spring Boot?

## 12. Kết luận

Thu hồi chứng thư theo số sê-ri là một thao tác quản trị bảo mật quan trọng của **Vault PKI**. Để thao tác đúng, ứng dụng Java cần nhận diện chính xác **mount + issuer + serial**, sử dụng **VaultTemplate/VaultOperations** với quyền `update` tối thiểu trên endpoint `pki/revoke` tương ứng, ghi nhận kết quả có thể kiểm toán và xử lý trạng thái bất định khi lỗi mạng.

Quan trọng không kém là **hiệu lực ở phía kiểm tra chứng thư**: CRL/OCSP phải được cấu hình, phân phối và thực sự được TLS peers kiểm tra. Với Spring Vault, bảo vệ chứng thư cần kết hợp xác thực theo workload, phân quyền, theo dõi vòng đời token, vận hành PKI, xử lý lỗi, giám sát và kiểm thử tích hợp từ khâu phát hành đến khi chứng thư cũ bị từ chối.
