# Kiểm thử điều kiện role không cho phép cấp chứng thư

## 1. Mục tiêu và ngữ cảnh

Trong **SPRING_VAULT**, ứng dụng Java dùng `VaultTemplate` hoặc `VaultPkiOperations` để yêu cầu HashiCorp Vault cấp chứng thư X.509 cho máy chủ TLS, mTLS giữa các dịch vụ hoặc client authentication. Khi PKI secrets engine đã có CA/issuer hợp lệ, mỗi yêu cầu cấp chứng thư phải qua **hai lớp kiểm soát độc lập**:

1. **ACL của token:** danh tính workload (Kubernetes auth, AppRole hoặc phương thức khác) có được gọi `pki/issue/<role>` hay `pki/sign/<role>` không?
2. **Điều kiện của PKI role:** tên miền, CN, Subject Alternative Names (SAN), kiểu chứng thư và thời hạn yêu cầu có đáp ứng chính sách cấp phát của role không?

Bài này tập trung vào **kiểm thử các điều kiện của role dẫn đến yêu cầu cấp chứng thư bị từ chối**, đồng thời chứng minh rằng các yêu cầu hợp lệ vẫn được cấp. Đây là kiểm thử bảo mật cần thiết: chỉ kiểm thử đường đi thành công có thể bỏ sót việc role vô tình cho phép tên miền ngoài phạm vi, wildcard, IP SAN hoặc thời hạn quá dài.

Ví dụ xuyên suốt:

- Mount PKI: `pki/`.
- PKI role: `orders-server`.
- Phạm vi được phép: **các subdomain của `apps.example.test`**; không cấp cho chính `apps.example.test`, không cấp wildcard.
- Workload: dịch vụ Orders chỉ được yêu cầu chứng thư qua `pki/issue/orders-server`.
- Ví dụ hợp lệ: `api.apps.example.test`.
- Ví dụ cần bị từ chối: `api.other.example.test`, `apps.example.test`, `*.apps.example.test`, IP SAN bất kỳ.

Các tên `example.test` chỉ là dữ liệu mô phỏng trong môi trường thử nghiệm, không đại diện cho DNS công khai hay một CA sản xuất.

## 2. Vai trò của PKI role khác với quyền ACL

| Lớp kiểm soát | Ví dụ | Nếu không đáp ứng | Cần kiểm chứng |
|---|---|---|---|
| Workload identity và ACL | Token có `update` trên `pki/issue/orders-server` | Yêu cầu bị chặn bởi cơ chế xác thực/phân quyền, thường có HTTP 403 | Token hiện dùng, namespace, capability trên API path |
| PKI role | `allowed_domains=apps.example.test`, `allow_subdomains=true` | Vault từ chối yêu cầu cấp với tên không hợp lệ, thường ở mức validation (ví dụ 400) | Cấu hình role, CN và **mọi SAN** trong request |
| CA/issuer và mount | Issuer mặc định tồn tại, còn hiệu lực, tương thích với request | Không thể cấp dù ACL và role hợp lệ | Mount, issuer, chain, trạng thái CA |
| Thời hạn và loại chứng thư | `max_ttl=72h`, `server_flag=true` | Yêu cầu vượt giới hạn hoặc không tương thích bị từ chối/điều chỉnh theo quy tắc liên quan | Cấu hình role, issuer, mount TTL và request |

**Không đồng nhất “role từ chối” với “token không có quyền”.** Một token có đầy đủ quyền gọi `pki/issue/orders-server` vẫn phải bị Vault từ chối khi xin cấp chứng thư cho `attacker.example.test`. Ngược lại, role cho phép một CN không tự cấp quyền truy cập endpoint đó cho token không được phép.

Khi sửa lỗi, không mở rộng `allowed_domains` hay bật `allow_any_name` để xử lý một lỗi 403 do ACL; cũng không cấp `sys/*` hoặc `pki/roles/*` cho ứng dụng để xử lý một lỗi validation.

## 3. Những điều kiện role cần đưa vào bộ kiểm thử

| Thuộc tính role | Ý nghĩa | Ca thử từ chối tiêu biểu |
|---|---|---|
| `allowed_domains` | Danh sách miền có thể xin cấp; được diễn giải cùng các cờ match | CN/SAN ngoài miền đã được duyệt |
| `allow_bare_domains` | Có cho phép tên đúng bằng một miền trong `allowed_domains` không | Xin cấp chính `apps.example.test` khi flag là `false` |
| `allow_subdomains` | Có cho phép subdomain của tên được khai báo không | Tên subdomain bị chặn khi flag `false` |
| `allow_glob_domains` | Có cho phép biểu thức glob trong danh sách domain không | Tên chỉ khớp glob nhưng role không cho glob |
| `allow_any_name` | Nới rộng kiểm tra tên, có rủi ro cấp sai phạm vi | Kiểm chứng flag giữ `false`; test ngoài miền vẫn bị từ chối |
| `allow_wildcard_certificates` | Có cho phép chứng thư tên wildcard không | `*.apps.example.test` bị chặn dù subdomain thông thường được phép |
| `allow_ip_sans` | Có cho yêu cầu IP SAN không | `ip_sans=192.0.2.10` bị từ chối khi `false` |
| `allow_localhost` | Cho phép các tên localhost đặc biệt | `common_name=localhost` không được cấp khi role bị giới hạn |
| `enforce_hostnames` | Kiểm tra tính hợp lệ hostname trong CN/DNS SAN | Tên sai định dạng phải bị từ chối |
| `require_cn` | Có bắt buộc trường common name trong yêu cầu issue không | Không gửi `common_name` khi `true` |
| `max_ttl` | Ngưỡng thời hạn tối đa role cho phép | Xin cấp `ttl=96h` khi `max_ttl=72h` |
| `server_flag` / `client_flag` | Mục đích sử dụng chứng thư được thiết lập trên role | Kiểm chứng EKU trên chứng thư thành công; role server-only không nên tạo client auth ngoài mục đích |

Một số chi tiết quan trọng:

- Role phải xét **toàn bộ tên xin cấp**, gồm `common_name` và `alt_names` (DNS/email SAN). Nếu **một** SAN không được phép, Vault từ chối **toàn bộ** yêu cầu; không tự xóa SAN sai rồi cấp phần còn lại.
- CN không thay thế DNS SAN trong kiểm tra danh tính TLS hiện đại. Với ca thành công, cần kiểm tra chứng thư thực tế chứa SAN phù hợp và chuỗi tin cậy hợp lệ.
- `allow_subdomains=true` không có nghĩa là tự động cho phép cấp wildcard khi đã tắt `allow_wildcard_certificates`.
- Các rule cho URI SAN, Other SAN, `cn_validations`, template và CSR có thể làm phạm vi chấp nhận thay đổi. Nếu hệ thống sử dụng chúng, bổ sung ca thử tương ứng; đừng mặc định những kiểm tra trên đủ cho mọi biến thể cấu hình.
- Giới hạn TTL còn phụ thuộc mount, issuer, quy tắc `leaf_not_after_behavior` và thời hạn CA; nếu kết quả khác kỳ vọng, phải quan sát cấu hình đó trước khi kết luận một policy role hoạt động sai.

## 4. Chuẩn bị môi trường và vai trò minh họa

Chạy bài thực hành trên một **Vault dev instance hoặc cụm thử nghiệm cô lập**. Giả định mount `pki` đã được bật, có CA và một **issuer mặc định đang hoạt động**, thời hạn CA đủ dài. Các công việc khởi tạo CA, quản trị issuer và cấp policy do tài khoản vận hành thực hiện; test workload chỉ dùng token của mình.

Định nghĩa role tối giản, cố định các cờ quan trọng để kết quả thử nghiệm không phụ thuộc mặc định thay đổi giữa phiên bản:

~~~bash
# Chạy bằng danh tính quản trị PKI, trong môi trường kiểm thử.
vault write pki/roles/orders-server \
  allowed_domains="apps.example.test" \
  allow_bare_domains=false \
  allow_subdomains=true \
  allow_glob_domains=false \
  allow_any_name=false \
  allow_wildcard_certificates=false \
  enforce_hostnames=true \
  allow_localhost=false \
  allow_ip_sans=false \
  require_cn=true \
  ttl="24h" \
  max_ttl="72h" \
  server_flag=true \
  client_flag=false
~~~

Đọc lại role sau khi ghi:

~~~bash
vault read pki/roles/orders-server
~~~

**Tại sao phải đọc lại?** Lệnh `vault write` trên role có thể thay thế các trường không được truyền bằng giá trị mặc định. Kiểm thử phải dựa trên **cấu hình role thực tế**, gồm các flag đang tác động đến kiểm tra tên và SAN. Nếu role dùng `issuer_ref`, xác minh issuer tương ứng; nếu mount chưa có issuer phù hợp, một ca “đúng tên” cũng thất bại và không thể dùng để đánh giá rule.

Điểm cần nắm rõ: cấu hình trên **cho phép** `api.apps.example.test` nhưng **không cho phép** chính `apps.example.test`. Nếu muốn chính domain gốc hợp lệ, phải chủ động đặt `allow_bare_domains=true`; không nên suy diễn từ `allow_subdomains`.

### Policy của workload

Token ứng dụng chỉ được cấp quyền gọi đúng endpoint issue:

~~~hcl
# orders-pki-issue.hcl
path "pki/issue/orders-server" {
  capabilities = ["update"]
}
~~~

Người vận hành có thể tải policy bằng:

~~~bash
vault policy write orders-pki-issue orders-pki-issue.hcl
~~~

Sau đó gán policy vào **auth role chuyên biệt của workload**, đăng nhập bằng phương thức thực tế và dùng token vừa nhận cho các yêu cầu sau. Cách gắn policy phụ thuộc Kubernetes auth, AppRole hoặc auth method đang triển khai.

Để chứng minh quyền của token đang dùng:

~~~bash
# Các lệnh tiếp theo phải sử dụng token và namespace của workload.
vault token capabilities pki/issue/orders-server
vault token capabilities pki/issue/another-role
vault token capabilities pki/roles/orders-server
~~~

Kỳ vọng: `pki/issue/orders-server` có `update`, các đường dẫn khác không có quyền thao tác tương đương. Quyền tạo hoặc sửa role thuộc danh tính vận hành; ứng dụng không cần quyền đó.

## 5. Thiết kế test matrix: thành công và bị từ chối

Bộ test phải có ít nhất **một ca thành công** dùng cùng role, issuer và workload token. Nếu mọi request đều lỗi do CA không tồn tại, token hết hạn hoặc Vault mất kết nối, các phép thử âm tính sẽ là **false positive**.

| Mã | Request tới `pki/issue/orders-server` | Kỳ vọng | Lý do |
|---|---|---|---|
| P01 | `common_name=api.apps.example.test`, `ttl=1h` | **Được cấp** | Subdomain được cho phép; TTL dưới ngưỡng |
| N01 | `common_name=api.other.example.test` | **Bị từ chối** | Ngoài `allowed_domains` |
| N02 | `common_name=apps.example.test` | **Bị từ chối** | `allow_bare_domains=false` |
| N03 | `common_name=api.apps.example.test`, `alt_names=admin.other.example.test` | **Bị từ chối** | Một SAN ngoài miền làm thất bại toàn bộ request |
| N04 | `common_name=*.apps.example.test` | **Bị từ chối** | `allow_wildcard_certificates=false` |
| N05 | `common_name=api.apps.example.test`, `ip_sans=192.0.2.10` | **Bị từ chối** | `allow_ip_sans=false` |
| N06 | `common_name=api.apps.example.test`, `ttl=96h` | **Bị từ chối theo ràng buộc TTL** | `max_ttl=72h` |
| N07 | Thiếu `common_name`, không có tên thay thế phù hợp | **Bị từ chối** | `require_cn=true` |
| N08 | `common_name=localhost` | **Bị từ chối** | Không thuộc domain, `allow_localhost=false` |
| A01 | Cùng request P01 nhưng token không có `pki/issue/orders-server` | **Bị từ chối bởi ACL** | Phân quyền API, không phải rule tên |

Đối với N06, kiểm tra lỗi/TTL theo **phiên bản Vault cụ thể** và các giới hạn của mount/issuer; không dựa duy nhất vào mã HTTP. Test nhằm chứng minh role không phát chứng thư có thời hạn vượt `max_ttl`, bất kể chính sách xử lý thời hạn ở tầng issuer có ảnh hưởng đến kết quả.

Trong các ca N01–N08, cần giữ **cùng token có quyền gọi endpoint** như P01; chỉ thay đổi field đầu vào đang kiểm tra. Nếu dùng token khác cho một ca, kết quả không cô lập được nguyên nhân từ chối.

## 6. Thực hành Vault CLI: quan sát kết quả thực

### 6.1. Ca hợp lệ để xác nhận môi trường đã sẵn sàng

~~~bash
# In ra serial number thay vì toàn bộ private key.
vault write -field=serial_number pki/issue/orders-server \
  common_name="api.apps.example.test" \
  ttl="1h"
~~~

Kỳ vọng lệnh thành công và trả về serial number. Kiểm thử tự động nên nhận toàn bộ response vào vùng nhớ bí mật, phân tích certificate, serial number, SAN và validity; **không ghi private_key ra log**.

### 6.2. Tên miền ngoài phạm vi

~~~bash
vault write -field=serial_number pki/issue/orders-server \
  common_name="api.other.example.test" \
  ttl="1h"
~~~

Kỳ vọng request không được cấp chứng thư vì role chỉ cho phép subdomain của `apps.example.test`. Nếu lệnh thành công, coi đó là lỗi kiểm soát phạm vi cần điều tra: role có thể đã bật `allow_any_name`, có glob quá rộng, template sai hoặc role thực tế khác với cấu hình dự kiến.

### 6.3. Không cho phép domain gốc

~~~bash
vault write -field=serial_number pki/issue/orders-server \
  common_name="apps.example.test" \
  ttl="1h"
~~~

Yêu cầu phải bị từ chối vì `allow_bare_domains=false`. Đây là ca dễ bị bỏ qua khi team chỉ kiểm tra “danh sách domain được phép” mà không kiểm tra cờ đối chiếu.

### 6.4. CN đúng nhưng SAN sai

~~~bash
vault write -field=serial_number pki/issue/orders-server \
  common_name="api.apps.example.test" \
  alt_names="admin.other.example.test" \
  ttl="1h"
~~~

Kỳ vọng **toàn bộ yêu cầu bị từ chối**. Không được chấp nhận kết quả chỉ bỏ tên SAN sai và trả chứng thư hợp lệ cho CN; đó không phải hành vi bảo mật cần chứng minh.

### 6.5. Wildcard, IP SAN và TTL

~~~bash
# Wildcard bị chặn.
vault write -field=serial_number pki/issue/orders-server \
  common_name="*.apps.example.test" ttl="1h"

# IP SAN bị chặn.
vault write -field=serial_number pki/issue/orders-server \
  common_name="api.apps.example.test" \
  ip_sans="192.0.2.10" ttl="1h"

# TTL yêu cầu vượt max_ttl=72h.
vault write -field=serial_number pki/issue/orders-server \
  common_name="api.apps.example.test" ttl="96h"
~~~

Mỗi lệnh thử âm tính cần được harness xác minh **exit code khác 0 và lý do cụ thể liên quan đến role/request**. Chỉ thấy non-zero exit chưa đủ: lỗi mất mạng, Vault sealed, token hết hạn, namespace sai hoặc issuer hỏng cũng có thể tạo exit code khác 0.

Ví dụ với shell trong môi trường test, có thể dùng điều kiện thất bại cơ bản:

~~~bash
if vault write -field=serial_number pki/issue/orders-server \
  common_name="api.other.example.test" ttl="1h"; then
  echo "FAIL: role unexpectedly issued for forbidden domain"
  exit 1
else
  echo "Request rejected; inspect response to verify it was a role validation error"
fi
~~~

Đoạn shell này **chưa phải assertion đầy đủ**: cần kiểm tra thêm thông báo phản hồi hoặc audit log và bảo đảm P01 thành công cùng token ngay trước đó.

## 7. Kiểm thử bằng Spring Vault trong ứng dụng Java

Spring Vault cung cấp `VaultPkiOperations` với `issueCertificate(roleName, request)` để cấp chứng thư; `VaultTemplate` cũng có thể gọi trực tiếp endpoint `pki/issue/<role>`. Để minh họa điều kiện đầu vào và so sánh từng ca, ví dụ dưới sử dụng request map qua `VaultOperations.write`.

~~~java
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.util.Map;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.vault.VaultException;
import org.springframework.vault.core.VaultOperations;
import org.springframework.vault.support.VaultResponse;

@SpringBootTest
class PkiRoleRejectionIntegrationTest {

    private static final String ISSUE_PATH = "pki/issue/orders-server";

    @Autowired
    private VaultOperations vault; // Bean dùng workload identity của test.

    @Test
    void allowedSubdomainIsIssued() {
        VaultResponse response = vault.write(
            ISSUE_PATH,
            Map.of("common_name", "api.apps.example.test",
                   "ttl", "1h")
        );

        assertNotNull(response);
        assertNotNull(response.getData());
        assertNotNull(response.getData().get("certificate"));
        assertNotNull(response.getData().get("serial_number"));
        // Không in response: có thể chứa private_key.
    }

    @Test
    void forbiddenDomainIsRejected() {
        // Kiểm tra baseline cùng token để tránh false positive
        // do Vault chưa sẵn sàng hoặc credential sai.
        allowedSubdomainIsIssued();

        assertThrows(VaultException.class, () ->
            vault.write(
                ISSUE_PATH,
                Map.of("common_name", "api.other.example.test",
                       "ttl", "1h")
            )
        );
    }

    @Test
    void forbiddenSanRejectsWholeRequest() {
        allowedSubdomainIsIssued();

        assertThrows(VaultException.class, () ->
            vault.write(
                ISSUE_PATH,
                Map.of("common_name", "api.apps.example.test",
                       "alt_names", "admin.other.example.test",
                       "ttl", "1h")
            )
        );
    }

    @Test
    void wildcardIsRejected() {
        allowedSubdomainIsIssued();

        assertThrows(VaultException.class, () ->
            vault.write(
                ISSUE_PATH,
                Map.of("common_name", "*.apps.example.test",
                       "ttl", "1h")
            )
        );
    }

    @Test
    void ipSanIsRejected() {
        allowedSubdomainIsIssued();

        assertThrows(VaultException.class, () ->
            vault.write(
                ISSUE_PATH,
                Map.of("common_name", "api.apps.example.test",
                       "ip_sans", "192.0.2.10",
                       "ttl", "1h")
            )
        );
    }
}
~~~

Điều kiện chạy ví dụ:

1. `@SpringBootTest` phải nạp được một bean `VaultOperations` đã cấu hình đúng endpoint Vault và auth workload; Java không nên nhúng token cố định vào test.
2. PKI mount, issuer và role do fixture hoặc setup quản trị chuẩn bị trước; test chỉ dùng quyền `pki/issue/orders-server`.
3. `assertThrows(VaultException.class, ...)` xác nhận Spring Vault báo lỗi, nhưng **chưa phân loại được lỗi**. Một bộ test production cần kết hợp thông tin HTTP status/response từ client đang dùng hoặc audit log để khẳng định request bị từ chối vì **đúng ràng buộc role**; tránh assert cứng chuỗi tiếng Anh vốn thay đổi theo phiên bản.
4. Baseline trong mỗi test trên cố ý cấp thêm một chứng thư hợp lệ nhằm cô lập lỗi kết nối; khi tối ưu bộ test thực tế, có thể gom vào setup/health check dùng chung và giảm số chứng thư phát sinh.
5. Đối với chứng thư cấp thành công, cần phân tích X.509 để xác nhận `subjectAltName`, `notBefore`, `notAfter`, `extendedKeyUsage`, issuer và chain; không chỉ xét `response != null`.

Trong ứng dụng thực tế, có thể thay lệnh `vault.write` bằng:

~~~java
import java.time.Duration;
import org.springframework.vault.core.VaultPkiOperations;
import org.springframework.vault.support.VaultCertificateRequest;

// vaultOps được inject từ cấu hình ứng dụng.
VaultPkiOperations pki = vaultOps.opsForPki("pki");

VaultCertificateRequest request = VaultCertificateRequest.builder()
    .commonName("api.apps.example.test")
    .ttl(Duration.ofHours(1))
    .build();

pki.issueCertificate("orders-server", request);
~~~

Cả hai cách đều đi qua cùng cơ chế kiểm tra ACL và role phía Vault. Với `signCertificateRequest`, cần viết thêm test cung cấp **CSR thực tế**, gồm CN/SAN nằm trong CSR, vì endpoint `pki/sign/<role>` có thể được cấp quyền và có luồng dữ liệu khác với `issue`. Không mặc định test `issue` đã bao phủ `sign`.

## 8. Kiểm chứng chính sách bằng cách đọc chứng thư thành công

Một chứng thư được cấp thành công vẫn có thể không khớp mục đích vận hành nếu role hoặc issuer cấu hình sai. Đọc X.509 chứng thư trong test để kiểm tra:

- **DNS SAN:** chứa `api.apps.example.test` và không có tên ngoài phạm vi được yêu cầu.
- **Subject:** CN tương ứng nếu role yêu cầu; lưu ý các client TLS hiện đại chủ yếu kiểm chứng SAN.
- **Validity:** `NotBefore` / `NotAfter` phù hợp thời hạn mong đợi trong giới hạn role, mount và issuer; đừng assert chính xác tuyệt đối tới từng giây vì có thể có backdating.
- **Extended Key Usage:** theo role `server_flag=true` và `client_flag=false`, xác minh chứng thư phù hợp mục đích TLS server.
- **Issuer và CA chain:** issuer đúng cấu hình và certificate có thể xác thực đến trust anchor thích hợp.
- **Serial number:** tồn tại để có thể theo dõi và xử lý thu hồi chứng thư test được cấp.

Phần lớn response `pki/issue` chứa **private key** do Vault tạo. Không đưa toàn bộ JSON response vào log hoặc báo cáo CI; cần thiết kế quản lý khóa riêng tư ngay trong test và xóa sạch dữ liệu sau khi hoàn tất.

Nếu chỉ cần xác nhận policy tên, kiểm tra endpoint thực tế bằng cùng token là thiết yếu. Thực hiện test success với token quản trị nhưng test denial với workload token sẽ không chứng minh được ranh giới role.

## 9. Xử lý lỗi: xác định đúng nguyên nhân từ chối

| Triệu chứng | Giả thuyết đầu tiên | Kiểm tra có ý nghĩa |
|---|---|---|
| `permission denied`, HTTP 403 | Token thiếu `update` trên đúng issue/sign path; token sai hoặc hết hạn | `vault token capabilities` bằng token workload, auth role, namespace, TTL |
| Tên nằm ngoài phạm vi và request bị từ chối | `allowed_domains`, `allow_bare_domains`, `allow_subdomains` hoặc SAN validation | Đọc lại role và toàn bộ CN/SAN request |
| Tên đúng nhưng không cấp được | Issuer chưa sẵn sàng, CA hết hạn, role không tồn tại, mount/namespace sai | Ca P01, `vault read pki/roles/orders-server` bằng operator, issuer config |
| Chỉ request wildcard bị từ chối | `allow_wildcard_certificates=false` | Kiểm tra flag và tên wildcard thực được yêu cầu |
| Chỉ request có IP SAN bị từ chối | `allow_ip_sans=false` | Kiểm tra payload `ip_sans` và role |
| Request TTL lớn gặp lỗi | Role `max_ttl`, mount/issuer TTL hoặc CA gần hết hạn | So sánh TTL request với role/mount/issuer, kiểm tra response |
| Một client đi qua được, client khác thất bại | Token, Vault namespace, mount, role hoặc CSR payload khác nhau | Ghi lại method/path và field không nhạy cảm của từng request |
| Test âm tính “pass” dù Vault offline | Harness chỉ check exception hoặc exit code | Bắt buộc test baseline thành công, xác nhận response/loại lỗi |

**Quy trình chẩn đoán đề xuất:**

1. Xác định chính xác endpoint mà Java gọi: `pki/issue/orders-server` hay `pki/sign/orders-server`.
2. Dùng cùng danh tính workload và Vault namespace để kiểm tra quyền endpoint.
3. Đọc cấu hình role bằng danh tính vận hành, đối chiếu tất cả flag liên quan.
4. Chạy P01 để chứng minh CA/issuer, mount và đường truyền có thể cấp chứng thư hợp lệ.
5. Thực hiện một ca negative, chỉ thay một điều kiện, giữ nguyên token/role/issuer.
6. Phân loại lỗi role validation và lỗi ACL dựa trên response/audit; kiểm tra rằng không có chứng thư cho request bị từ chối.
7. Kiểm tra chứng thư hợp lệ thực tế và lặp lại test sau mỗi lần cập nhật role, issuer hoặc thư viện.

Đừng dựa duy nhất vào HTTP status như một “chứng minh” tuyệt đối: phiên bản Vault, proxy, client HTTP của Spring Vault và nguyên nhân lỗi có thể ảnh hưởng biểu hiện. Bằng chứng nên bao gồm input, chính sách role thực tế, token capability, kết quả ca positive và nguyên nhân request bị từ chối.

## 10. Mở rộng bài test: CSR, templates và các SAN đặc biệt

Các ca thử nền tảng ở trên mô tả luồng `issue`; môi trường sản xuất thường phức tạp hơn.

**CSR và `sign`:** nếu ứng dụng tự tạo private key và gửi CSR, cần kiểm tra cả subject/SAN trong CSR lẫn các tham số request ký. Với cấu hình như `use_csr_values`, dữ liệu subject và extension được lấy theo cơ chế riêng. Test phải cố ý đưa CN/SAN không được phép vào CSR và xác nhận không được ký thành công. Chỉ cấp quyền `pki/sign/<role>` khi workload cần; tránh vô tình cấp endpoint thay đổi issuer theo path.

**URI SAN và workload identity:** môi trường service mesh có thể dùng `spiffe://...` trong `uri_sans`. Khi role thiết lập `allowed_uri_sans`, kiểm tra URI được duyệt và URI ngoài phạm vi. URI SAN có quy tắc riêng, không đồng nhất với `allowed_domains` dành cho DNS/email.

**Other SAN và template:** nếu dùng `allowed_other_sans` hoặc `allowed_domains_template` / `allowed_uri_sans_template`, thêm trường hợp principal không khớp template, namespace khác hoặc prefix giả mạo. Việc dùng glob `*` quá rộng có thể vô tình mở toàn bộ namespace; vì vậy ca negative cần bao gồm giá trị gần giống tên hợp lệ.

**Kiểm tra hostname validation:** nếu bật cấu hình vô hiệu hóa các kiểm tra CN, phải đánh giá lại toàn bộ giả định về `allowed_domains`. Bất kỳ ngoại lệ nào với xác thực tên cần được kiểm thử ở mức certificate payload, thay vì chỉ dựa trên tên flag.

**Độ dài khóa và mục đích sử dụng:** trường `key_type`/`key_bits`, `server_flag`/`client_flag` và thời hạn chứng thư thường do operator quyết định tại role; workload không nên được tự ý sửa role để đáp ứng một request bất thường. Xác minh bằng cách đọc certificate thực thay vì suy luận từ JSON request.

## 11. Lưu ý khi chạy test trên CI và môi trường tích hợp

Kiểm thử negative thật sự nên giao tiếp với Vault instance được cô lập (ví dụ môi trường integration test sử dụng Vault dev/test hoặc Testcontainers nếu dự án hỗ trợ), vì mock `VaultTemplate` sẽ không chứng minh Vault áp dụng role policy. Dùng tên role và CA dành riêng cho bộ test, tránh phụ thuộc vào issuer sản xuất.

- **Thứ tự thiết lập:** Vault sẵn sàng → PKI mount/issuer hợp lệ → role → ACL/auth role → workload token → positive baseline → negative matrix.
- **Tính ổn định:** chốt version Vault của test để diễn giải lỗi và khả năng cấu hình; đối chiếu lại khi upgrade Vault/Spring Vault.
- **Cô lập:** tránh chỉnh sửa role đang được service khác dùng trong khi test. Tạo namespace hoặc mount riêng nếu môi trường hỗ trợ.
- **Dữ liệu nhạy cảm:** không log private key, token, CA private key, CSR chứa thông tin nhạy cảm hoặc toàn bộ response.
- **Tiêu chí pass:** positive request được cấp và certificate đúng thuộc tính; từng negative request bị từ chối **vì ràng buộc đã nêu**; token không có quyền thực sự bị ACL chặn.
- **Dọn dẹp:** thu hồi chứng thư test đã cấp khi phù hợp và xóa role/mount tạm chỉ trong môi trường được cấp quyền dọn dẹp; không xóa PKI mount dùng chung.
- **Giám sát:** theo dõi số lần cấp thành công, tỉ lệ request bị từ chối, latency, lỗi issuer và lỗi token; log theo mã request/correlation ID, không theo nội dung private key.

Việc role từ chối request ngoài phạm vi là một **kết quả bảo mật mong đợi**, không nhất thiết là sự cố. Theo dõi tỉ lệ lỗi cần phân biệt “rejection theo policy” với “PKI không cấp được khi hợp lệ”, nhất là khi nâng phiên bản thư viện hoặc cập nhật workload identity.

## 12. Câu hỏi tự kiểm tra

1. Token có `update` trên `pki/issue/orders-server`. Vì sao request `common_name=admin.other.example.test` vẫn phải bị từ chối?
2. Role có `allowed_domains=apps.example.test` và `allow_subdomains=true`. Vì sao `apps.example.test` vẫn có thể bị từ chối?
3. Khi CN hợp lệ nhưng `alt_names` chứa tên ngoài phạm vi, Vault nên cấp chứng thư đã lược bỏ SAN hay từ chối toàn bộ?
4. Một integration test `assertThrows` luôn pass ngay cả khi Vault bị ngắt mạng. Thiếu bước xác minh nào?
5. Vì sao test `pki/issue/<role>` không tự động bao phủ đường đi ký CSR `pki/sign/<role>`?

## 13. Tổng kết

Để kiểm thử **điều kiện role không cho phép cấp chứng thư** trong Vault PKI, cần xây dựng ma trận gồm **ca được phép** và **ca bị cấm** cho tên miền, domain gốc, SAN ngoài phạm vi, wildcard, IP SAN, CN bắt buộc và TTL. Mỗi negative test phải dùng cùng token có quyền gọi endpoint như positive test để phân biệt lỗi validation của role với lỗi ACL, token, issuer hoặc đường truyền.

Trong Spring Vault, `VaultPkiOperations` và `VaultTemplate` chỉ gửi request; **Vault mới là nơi thực thi các điều kiện role**. Bộ kiểm thử có giá trị khi chứng minh request hợp lệ cấp được chứng thư với thuộc tính đúng và request vi phạm bị từ chối bởi chính điều kiện cần bảo vệ. Khi cần kiểm tra CSR, URI SAN hay role template, hãy mở rộng thêm ca thử theo cấu hình thực tế.

### Tài liệu tham khảo

- [HashiCorp Vault — PKI secrets engine HTTP API](https://developer.hashicorp.com/vault/api-docs/secret/pki)
- [HashiCorp Vault — Build your own certificate authority](https://developer.hashicorp.com/vault/tutorials/pki/pki-engine)
- [Spring Vault — Vault secrets engines, mục PKI](https://docs.spring.io/spring-vault/reference/vault/vault-secret-engines.html)
- [Spring Vault — `VaultPkiOperations` API](https://docs.spring.io/spring-vault/reference/api/java/org/springframework/vault/core/VaultPkiOperations.html)
