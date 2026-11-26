# Dùng cơ chế tương ứng cho LDAP, Okta và RADIUS trong Spring Vault

## 1. Ba hệ thống danh tính, ba phương thức xác thực Vault

Ứng dụng Java sử dụng **Spring Vault** để truy cập HashiCorp Vault thông qua `VaultTemplate` cần chứng minh danh tính trước khi đọc secret, gọi Transit encryption hay PKI. Khi doanh nghiệp đã quản lý **tài khoản con người** bằng LDAP, Okta hoặc RADIUS, Vault cung cấp các **auth method** tương ứng để xác thực người dùng với hệ thống bên ngoài và phát hành **Vault token** mang quyền hạn phù hợp.

Bài này thuộc chương **Chứng thư và tài khoản**. Mục tiêu chính là chọn đúng cơ chế cho nguồn danh tính, cấu hình kết nối, ánh xạ tài khoản hoặc nhóm thành Vault policy, tích hợp với Spring Vault và kiểm tra kết quả cấp quyền. Những cơ chế này dành chủ yếu cho **đăng nhập bằng tài khoản người dùng**; ứng dụng server chạy tự động thường nên sử dụng danh tính workload như Kubernetes auth, JWT/OIDC cho workload được hỗ trợ hoặc AppRole theo mô hình triển khai. Không nên đưa mật khẩu LDAP/Okta/RADIUS của nhân viên vào service chạy nền.

### So sánh nhanh

| Tiêu chí | LDAP | Okta auth | RADIUS |
| --- | --- | --- | --- |
| Nguồn xác thực | LDAP server hoặc Active Directory | Tổ chức Okta và API xác thực của Okta | RADIUS server hỗ trợ **PAP** |
| Auth mount mặc định | `auth/ldap/` | `auth/okta/` | `auth/radius/` |
| Thông tin đăng nhập | Username/password | Username/password; có thể thêm TOTP/Okta Verify theo cấu hình | Username/password được RADIUS kiểm tra |
| Ánh xạ quyền thông dụng | LDAP group hoặc người dùng → Vault policy | Okta group hoặc người dùng → Vault policy | Tên người dùng đã đăng ký → Vault policy |
| Cấu hình chính | URL, DN, bộ lọc người dùng/nhóm, TLS, tài khoản bind tùy chọn | Domain/organization, API token, nhóm, MFA | Host, cổng UDP, shared secret, user mapping |
| Điều cần lưu ý | DN và group filter sai, TLS không tin cậy, nhóm lồng nhau | API token/nhóm, MFA tương tác, chính sách Okta | PAP, kết nối UDP, shared secret và quyền người dùng chưa đăng ký |

**LDAP auth, Okta auth và RADIUS auth không phải các secrets engine.** Chúng xác minh danh tính và phát hành token. Sau khi đăng nhập, Vault tiếp tục áp dụng ACL trên các đường dẫn của secrets engine; quyền `read` của một user không được suy ra chỉ từ việc password hợp lệ.

Luồng chung:

~~~mermaid
flowchart LR
    U["Người dùng / CLI / Java client"] -->|"username + password"| V["Vault auth mount"]
    V -->|"Xác minh"| I{"LDAP, Okta hoặc RADIUS"}
    I -->|"Chấp nhận"| P["Ánh xạ user / group sang policy"]
    I -->|"Từ chối"| X["Không phát hành Vault token"]
    P --> T["Vault token có TTL và policy"]
    T -->|"API call từ VaultTemplate"| A{"Vault ACL"}
    A -->|"Cho phép"| S["KV v2 / Transit / PKI"]
    A -->|"Từ chối"| D["403 permission denied"]
~~~

Một lần đăng nhập thành công chứng minh **xác thực** đã qua, còn việc đọc được secret cụ thể chứng minh **phân quyền** trên secret đó. Hai điều kiện phải được kiểm tra độc lập.

## 2. Chuẩn bị lab: policy chung và dữ liệu kiểm thử

Ví dụ dùng một Vault test qua HTTPS, mount KV v2 tại `secret/`, hai secret giả lập và hai policy:

| Dữ liệu | Đường dẫn logic CLI | API path dùng trong Vault ACL |
| --- | --- | --- |
| Reporting Dev | `secret/dev/reporting` | `secret/data/dev/reporting` |
| Reporting Prod | `secret/prod/reporting` | `secret/data/prod/reporting` |

Chuẩn bị bằng Vault admin hoặc một identity chỉ có quyền setup lab; không chạy lệnh quản trị bằng Vault token được cấp cho người dùng thường:

~~~bash
# Chỉ chạy lệnh enable nếu mount secret/ chưa tồn tại.
vault secrets enable -path=secret -version=2 kv

vault kv put -mount=secret dev/reporting username=report-dev-sample
vault kv put -mount=secret prod/reporting username=report-prod-sample
~~~

Tạo file `reporting-dev-read.hcl`:

~~~hcl
path "secret/data/dev/reporting" {
  capabilities = ["read"]
}
~~~

Và `reporting-prod-read.hcl`:

~~~hcl
path "secret/data/prod/reporting" {
  capabilities = ["read"]
}
~~~

Nạp chính sách vào Vault:

~~~bash
vault policy write reporting-dev-read reporting-dev-read.hcl
vault policy write reporting-prod-read reporting-prod-read.hcl
~~~

Ba phương thức đăng nhập sẽ được cấu hình để tài khoản thử nghiệm có quyền `reporting-dev-read`. Phép kiểm thử quan trọng là: **đọc Dev thành công, đọc Prod bị từ chối**. Lưu ý: Vault CLI `vault kv get -mount=secret dev/reporting` tự xử lý phân đoạn `data/` của KV v2; trong ACL phải ghi rõ `secret/data/dev/reporting`.

Tất cả tên người dùng, host và giá trị secret trong bài chỉ là ví dụ. Khi dùng hệ thống LDAP, Okta hay RADIUS thật, cần một môi trường kiểm thử được cấp phép, tài khoản chuyên dụng và đường truyền phù hợp.

## 3. LDAP auth: dùng directory và nhóm LDAP để cấp Vault policy

### 3.1. Khi nào chọn LDAP?

Chọn **LDAP auth** nếu tổ chức đã có OpenLDAP hoặc Active Directory và muốn người dùng xác thực bằng tài khoản directory. Vault kết nối LDAP server để kiểm tra thông tin đăng nhập, có thể tìm người dùng và nhóm theo DN/filter, rồi ánh xạ thành policy. LDAP không yêu cầu tạo bản sao password người dùng trong Vault.

Ví dụ directory dùng các entry:

~~~text
ou=People,dc=example,dc=org
  uid=alice,ou=People,dc=example,dc=org

ou=Groups,dc=example,dc=org
  cn=vault-reporting-dev,ou=Groups,dc=example,dc=org
~~~

Ví dụ nhóm `vault-reporting-dev` chứa `alice`. Để Vault tìm đúng thành viên, cần căn cứ **schema của LDAP server**: nhóm `groupOfNames` thường dùng thuộc tính `member`, trong khi một số cấu hình directory có `memberUid` hoặc `memberOf`. Không sao chép `groupfilter` giữa OpenLDAP và Active Directory nếu cấu trúc nhóm khác nhau.

### 3.2. Cấu hình LDAP qua TLS

~~~bash
# Chỉ enable khi auth/ldap chưa được mount.
vault auth enable -path=ldap ldap

# Biến môi trường được nạp an toàn bởi phiên làm việc quản trị.
vault write auth/ldap/config \
  url="ldaps://ldap.example.org:636" \
  userdn="ou=People,dc=example,dc=org" \
  userattr="uid" \
  groupdn="ou=Groups,dc=example,dc=org" \
  groupfilter="(&(objectClass=groupOfNames)(member={{.UserDN}}))" \
  groupattr="cn" \
  binddn="cn=vault-reader,ou=ServiceAccounts,dc=example,dc=org" \
  bindpass="$LDAP_BIND_PASSWORD" \
  certificate=@ldap-ca.pem \
  insecure_tls=false
~~~

Trong ví dụ:

- `url` dùng LDAPS; `certificate` là CA PEM giúp Vault xác minh chứng thư LDAP server. Nếu server sử dụng LDAP trên cổng 389 với StartTLS, dùng `starttls=true` và cấu hình URL tương ứng. Không tắt kiểm tra TLS để giải quyết lỗi CA trong production.
- `userdn` và `userattr` điều khiển tìm người dùng; `groupdn`, `groupfilter` và `groupattr` điều khiển việc truy vấn nhóm.
- `binddn`/`bindpass` dùng tài khoản có quyền **tìm kiếm** người dùng và nhóm; nó không phải tài khoản được Vault cấp policy khi `alice` đăng nhập. Quyền của tài khoản bind nên là quyền đọc directory tối thiểu.
- `{{.UserDN}}` là biến mẫu được **Vault LDAP auth** thay bằng DN đã tìm được; hai dấu ngoặc nhọn là một phần của filter, không phải cú pháp shell.

Không đưa `LDAP_BIND_PASSWORD` vào source code hoặc log. Ngay cả khi lấy từ biến môi trường, việc truyền password thành đối số CLI có thể làm lộ thông tin trong danh sách tiến trình hoặc bản ghi shell ở một số hệ thống; cấu hình production nên sử dụng công cụ triển khai secret và cơ chế nhập an toàn do tổ chức quản lý.

### 3.3. Gắn nhóm và người dùng vào policy

~~~bash
# Nhóm LDAP vault-reporting-dev được cấp quyền đọc Reporting Dev.
vault write auth/ldap/groups/vault-reporting-dev \
  policies=reporting-dev-read

# Kiểm tra mapping bằng identity quản trị.
vault read auth/ldap/groups/vault-reporting-dev
~~~

Nếu có nhu cầu cấp thêm quyền cá nhân trong lab, endpoint `auth/ldap/users/<username>` cho phép ánh xạ policy trực tiếp. Khi vận hành, ưu tiên ánh xạ theo nhóm nếu có thể để thay đổi nhân sự được quản lý tại directory, nhưng cần kiểm tra rằng thành viên nhóm có thực sự được Vault tìm thấy.

Người dùng thử đăng nhập bằng CLI:

~~~bash
vault login -method=ldap username=alice
# CLI sẽ yêu cầu nhập mật khẩu mà không hiển thị khi gõ.
~~~

Sau đăng nhập, Vault trả về token và danh sách policy. Nếu password đúng nhưng nhóm không được ánh xạ, user có thể vẫn đăng nhập thành công nhưng không nhận `reporting-dev-read`. Đây là lý do phải kiểm tra **policy và quyền thực tế**, không chỉ kiểm tra thành công login.

Thử cả password sai, nhóm không có mapping, lỗi CA và thay đổi membership. Với một thành viên bị thu hồi quyền, cần xem xét **revoke Vault token đã phát hành**: cập nhật LDAP group không tự thay đổi policy trên token còn hiệu lực.

## 4. Okta auth: xác thực danh tính tập trung và kiểm tra MFA

### 4.1. Chọn đúng loại tích hợp với Okta

Vault **Okta auth** sử dụng đăng nhập username/password qua Okta Authentication API; tùy cấu hình tổ chức, người dùng có thể cần Okta Verify Push hoặc mã TOTP. Phương thức này khác với **Vault JWT/OIDC auth**: đăng nhập browser bằng redirect và ID token/OIDC nên được thiết kế riêng với auth method `jwt/` nếu đó là yêu cầu. Không đánh đồng “có Okta” với “phải dùng okta auth”; lựa chọn tùy mô hình tương tác và chính sách IdP.

Okta auth thích hợp khi tổ chức dùng Okta cho nhân sự, muốn xác thực từ Vault CLI hoặc một ứng dụng có **phiên đăng nhập người dùng tương tác** và ánh xạ Okta group thành Vault policy. Không sử dụng mật khẩu và mã MFA của một cá nhân làm thông tin đăng nhập lâu dài cho daemon.

### 4.2. Cấu hình Okta organization

~~~bash
vault auth enable -path=okta okta

vault write auth/okta/config \
  base_url="okta.com" \
  org_name="dev-example" \
  api_token="$OKTA_API_TOKEN"
~~~

Thay `dev-example` bằng tên organization thực tế. Tên host có thể khác `okta.com` khi tổ chức dùng miền hỗ trợ khác; xác nhận với quản trị Okta trước khi cấu hình.

`api_token` để Vault gọi API Okta, trong đó có truy vấn group membership. Khi thiếu API token, không nên kỳ vọng Vault tự lấy được nhóm từ Okta; việc chỉ dựa vào cấu hình nhóm cục bộ khi không có API token là cách vận hành đã bị cảnh báo về hỗ trợ trong tài liệu Vault. Token này cần quyền Okta API tối thiểu và phải được lưu, luân chuyển, thu hồi theo chính sách doanh nghiệp.

### 4.3. Ánh xạ Okta group và kiểm thử MFA

Giả sử user `bob` thuộc nhóm Okta `vault-reporting-dev`. Tại Vault:

~~~bash
vault write auth/okta/groups/vault-reporting-dev \
  policies=reporting-dev-read

vault read auth/okta/groups/vault-reporting-dev
~~~

Mặc dù tên nhóm trong LDAP và Okta có thể giống nhau, các mapping `auth/ldap/groups/...` và `auth/okta/groups/...` thuộc **hai auth mount độc lập**. Một mapping ở LDAP không tự tạo mapping tương ứng ở Okta.

Đăng nhập tương tác:

~~~bash
vault login -method=okta username=bob
~~~

Với phương thức MFA phù hợp, Vault CLI có thể xử lý các bước Okta Verify Push hoặc chấp nhận TOTP:

~~~bash
# Người dùng nhập giá trị TOTP thực tế từ thiết bị của mình.
vault login -method=okta username=bob totp=123456 provider=OKTA
~~~

Mã `123456` chỉ là placeholder để hiểu hình dạng lệnh, không phải mã dùng được. Truyền OTP trực tiếp trên command line có thể để lại dấu vết trong history hoặc process listing; ưu tiên hình thức đăng nhập tương tác được tổ chức phê duyệt. Nếu có nhiều TOTP provider, `provider` giúp xác định nguồn mã; khả năng MFA cụ thể phụ thuộc chính sách Okta và phiên bản Vault.

**Cảnh báo:** không bật `bypass_okta_mfa` để tránh các ca login tương tác thất bại; điều đó có thể làm giảm bảo vệ hoặc bỏ qua trạng thái tài khoản quan trọng. Nếu cần chính sách MFA ở Vault, đánh giá khả năng MFA riêng của Vault và quy tắc IdP.

Kiểm tra cả trường hợp MFA bị từ chối, user không thuộc nhóm mapped và API token Okta thiếu quyền truy vấn nhóm. Vì MFA có thể cần thiết bị thật, tách bài test tương tác khỏi unit test CI, không cố định OTP cá nhân trong mã.

## 5. RADIUS auth: xác thực qua RADIUS server và quản lý user mapping

### 5.1. Đặc điểm và giới hạn

Vault **RADIUS auth** tương tác với RADIUS server chấp nhận cơ chế **PAP** (Password Authentication Protocol). Vault là bên gửi yêu cầu xác thực tới RADIUS theo host, cổng và **shared secret** đã cấu hình. Khi RADIUS chấp nhận, Vault có thể ánh xạ tên user đã đăng ký sang Vault policy.

RADIUS thường xuất hiện trong hạ tầng xác thực tập trung hiện có, nhưng cần lưu ý:

- RADIUS truyền thống thường dùng **UDP cổng 1812** và shared secret giữa hai bên. Không coi cơ chế này tương đương kênh HTTPS end-to-end; bảo vệ mạng giữa Vault và RADIUS bằng phân vùng mạng, tunnel hoặc cách tương ứng với chính sách tổ chức.
- Cơ chế **PAP** đòi hỏi server hỗ trợ đúng dạng xác thực; không giả định mọi RADIUS server chỉ hỗ trợ EAP/CHAP đều tương thích.
- Vault **không tự suy ra Vault policy từ mọi nhóm RADIUS** như cách LDAP/Okta tra cứu group. Thiết kế phổ biến là ánh xạ tên user cụ thể hoặc policy chung cho user chưa đăng ký.

### 5.2. Kết nối RADIUS server

~~~bash
vault auth enable -path=radius radius

vault write auth/radius/config \
  host="radius.example.org" \
  port=1812 \
  secret="$RADIUS_SHARED_SECRET" \
  unregistered_user_policies="" \
  token_ttl=15m
~~~

`RADIUS_SHARED_SECRET` phải được lấy qua cơ chế cung cấp bí mật an toàn, không commit vào repo hay ghi vào log. Tham số `unregistered_user_policies=""` chủ ý tránh cấp một policy ứng dụng cho tất cả tài khoản mà RADIUS đã xác thực nhưng Vault chưa có user mapping. Không thêm quyền `reporting-dev-read` vào giá trị này nếu chỉ một nhóm người dùng cụ thể được phép đọc secret.

Ánh xạ người dùng `carol`:

~~~bash
vault write auth/radius/users/carol \
  policies=reporting-dev-read

vault read auth/radius/users/carol
~~~

Đăng nhập:

~~~bash
vault login -method=radius username=carol
~~~

Người dùng nhập mật khẩu tương ứng khi Vault CLI yêu cầu. Với user RADIUS xác thực thành công nhưng chưa có mapping trong `auth/radius/users/`, Vault vẫn có thể phát hành token với policy mặc định; nó **không mặc nhiên** nhận policy Dev nếu `unregistered_user_policies` để rỗng. Vì thế, cần kiểm tra quyền truy cập KV để chứng minh từ chối.

Khi test RADIUS, thử password sai, user chưa mapped, lỗi shared secret/UDP và đọc key ngoài policy. Nếu cần quyền theo nhóm phức tạp, hãy xác định cách đồng bộ user mapping hoặc cân nhắc cơ chế xác thực có group mapping phù hợp.

## 6. Gọi từ Java bằng Spring Vault

Spring Vault hỗ trợ nhóm phương thức đăng nhập username/password cho `userpass`, **LDAP**, **Okta** và **RADIUS**. Ở các phiên bản hiện đại, `UsernamePasswordAuthenticationOptions` cho phép chọn **auth mount path** qua `.path(...)`; `UsernamePasswordAuthentication` sử dụng thông tin đó để lấy Vault token. Phần đọc secret sau xác thực vẫn dùng `VaultTemplate`, bất kể người dùng đăng nhập qua nguồn nào.

### 6.1. Cấu hình `ClientAuthentication` theo mount

Đây là ví dụ cho một ứng dụng **tương tác có quyền sử dụng tài khoản thử nghiệm**, với cấu hình kết nối Vault qua HTTPS:

~~~java
import java.net.URI;
import java.util.Set;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Configuration;
import org.springframework.vault.authentication.ClientAuthentication;
import org.springframework.vault.authentication.UsernamePasswordAuthentication;
import org.springframework.vault.authentication.UsernamePasswordAuthenticationOptions;
import org.springframework.vault.config.AbstractVaultConfiguration;
import org.springframework.vault.client.VaultEndpoint;

@Configuration
public class HumanVaultAuthenticationConfig extends AbstractVaultConfiguration {

    @Value("${example.vault.uri}")
    private URI vaultUri;

    @Value("${example.vault.auth-mount}")
    private String authMount;

    @Value("${example.vault.username}")
    private String username;

    @Value("${example.vault.password}")
    private String password;

    @Override
    public VaultEndpoint vaultEndpoint() {
        return VaultEndpoint.from(vaultUri);
    }

    @Override
    public ClientAuthentication clientAuthentication() {
        if (!Set.of("ldap", "okta", "radius").contains(authMount)) {
            throw new IllegalArgumentException("Unsupported Vault auth mount");
        }

        UsernamePasswordAuthenticationOptions options =
            UsernamePasswordAuthenticationOptions.builder()
                .path(authMount)
                .username(username)
                .password(password)
                .build();

        return new UsernamePasswordAuthentication(options, vaultClient());
    }
}
~~~

Các thuộc tính `@Value` sử dụng cú pháp `${...}` của Spring; đây chỉ là ví dụ wiring. Đọc mật khẩu từ nguồn credential được bảo vệ, không đưa vào Git hoặc log.

Các property ví dụ:

~~~properties
example.vault.uri=https://vault.example.org:8200
example.vault.auth-mount=ldap
example.vault.username=alice
# Mật khẩu được cung cấp bằng nguồn bí mật bảo mật, không commit.
~~~

Đổi `example.vault.auth-mount` thành `okta` hoặc `radius` để chọn phương thức khác; mỗi mount phải được admin cấu hình trước. **Không mặc định** `userpass`: nếu bỏ `.path("ldap")`, trình đăng nhập có thể gọi sai backend. Với môi trường có mount tùy chỉnh như `corp-ldap/`, cần sửa allowlist và path khớp chính xác với auth mount thật.

**Về MFA Okta:** `UsernamePasswordAuthenticationOptions` cũng có tùy chọn `.totp(...)` trong các phiên bản hỗ trợ. Chỉ dùng nếu mã được lấy từ người dùng trong phiên đăng nhập phù hợp và làm mới mỗi lần; ví dụ cấp password cố định ở trên không bao quát luồng Okta Push/number challenge. Nên thiết kế một ứng dụng đăng nhập tương tác hoặc OIDC cho luồng tương ứng.

**Về vòng đời mật khẩu:** ví dụ `@Value` chỉ minh họa cấu hình; môi trường production cần nguồn credential bảo mật, cơ chế xóa khỏi bộ nhớ khi có thể, TLS tin cậy và cách luân chuyển khi password hết hạn. Các phiên bản Spring Vault có thể khác API cấu hình; đối chiếu tài liệu đúng version dự án.

### 6.2. Đọc KV v2 sau khi đã xác thực

~~~java
import java.util.Map;

import org.springframework.stereotype.Service;
import org.springframework.vault.core.VaultTemplate;
import org.springframework.vault.support.Versioned;

@Service
public class ReportingSettingsService {

    private final VaultTemplate vaultTemplate;

    public ReportingSettingsService(VaultTemplate vaultTemplate) {
        this.vaultTemplate = vaultTemplate;
    }

    public String readDevUsername() {
        Versioned<Map<String, Object>> response =
            vaultTemplate.opsForVersionedKeyValue("secret")
                .get("dev/reporting");

        if (response == null || response.getData() == null) {
            throw new IllegalStateException("Reporting Dev secret missing");
        }

        Object value = response.getData().get("username");
        if (!(value instanceof String)) {
            throw new IllegalStateException("Unexpected secret format");
        }
        return (String) value;
    }
}
~~~

Việc `VaultTemplate` đọc được `dev/reporting` dựa trên policy của Vault token. Nếu đổi đường dẫn thành `prod/reporting` nhưng token chỉ có policy `reporting-dev-read`, request phải bị Vault từ chối. Với KV v2, phương thức `opsForVersionedKeyValue("secret")` nhận **mount path** còn `.get("dev/reporting")` nhận **key path**; không thêm `data/` vào đây.

Spring Vault cung cấp `SessionManager` để quản lý token xác thực, bao gồm khả năng làm mới hoặc đăng nhập lại khi cấu hình phù hợp. Token từ LDAP/Okta/RADIUS không sống mãi; xử lý `403`, token hết hạn và thay đổi quyền theo chính sách backend và phiên người dùng. Không log password, token hoặc nội dung secret từ exception/HTTP body.

### 6.3. Phân biệt người dùng tương tác và máy chủ chạy nền

| Tình huống | Phương án phù hợp |
| --- | --- |
| Nhân viên dùng Vault CLI và có tài khoản LDAP | LDAP auth + nhóm LDAP ánh xạ policy. |
| Nhân viên dùng Okta và phải qua MFA | Okta auth tương tác hoặc OIDC auth theo yêu cầu đăng nhập. |
| Doanh nghiệp có RADIUS/PAP và tài khoản thử nghiệm | RADIUS auth + user mapping riêng. |
| Java backend chạy không có người dùng đăng nhập | Xác thực theo workload (Kubernetes/JWT/AppRole...) và policy service riêng. |
| UI có người dùng LDAP/Okta nhưng backend cần secret dịch vụ | Tách danh tính người dùng ứng dụng với danh tính service của backend; tránh tái sử dụng password người dùng làm credential dài hạn. |

Trong ứng dụng web nhiều người dùng, một singleton `VaultTemplate` dùng một `SessionManager` chung thường mang **một danh tính Vault**. Không dùng nó như một cách ngầm định để đại diện đồng thời cho mọi tài khoản nhân viên; nếu cần phân quyền Vault theo từng người, phải thiết kế phiên và token riêng theo từng identity, quản lý revoke và không để lộ token giữa request.

## 7. Kiểm thử đăng nhập và chính sách quyền truy cập

Ba auth method có API login tương tự nhau. Khi mount tại đường dẫn mặc định, người dùng nhập password và Vault trả về token trong `auth.client_token` nếu đăng nhập thành công:

| Method | Đường dẫn API login |
| --- | --- |
| LDAP | `POST /v1/auth/ldap/login/:username` |
| Okta | `POST /v1/auth/okta/login/:username` |
| RADIUS | `POST /v1/auth/radius/login/:username` |

Request body cơ bản:

~~~json
{
  "password": "MẬT_KHẨU_CHỈ_DÙNG_CHO_TEST"
}
~~~

Nếu Okta cần TOTP, có thể có thêm field `totp` và `provider`. Không gửi password qua HTTP thường, không gửi JSON chứa password vào log/trace và không đưa vào bài kiểm thử tự động chạy trên môi trường không bảo mật.

### 7.1. Ma trận test tối thiểu

| Ca | Identity | Kết quả đăng nhập | Kết quả KV v2 |
| --- | --- | --- | --- |
| LDAP-01 | LDAP `alice`, nhóm `vault-reporting-dev` | PASS | Đọc Dev PASS; Prod DENY. |
| LDAP-02 | LDAP user khác, password sai | DENY | Không nhận Vault token. |
| LDAP-03 | LDAP user hợp lệ nhưng không có mapping policy | Có thể PASS | Dev DENY. |
| OKTA-01 | Okta `bob`, nhóm phù hợp, MFA hoàn thành | PASS | Đọc Dev PASS; Prod DENY. |
| OKTA-02 | Okta `bob`, MFA bị từ chối | DENY | Không nhận Vault token. |
| OKTA-03 | Okta user không thuộc group mapped | Có thể PASS | Dev DENY. |
| RADIUS-01 | RADIUS `carol`, có user mapping | PASS | Đọc Dev PASS; Prod DENY. |
| RADIUS-02 | RADIUS user bị từ chối | DENY | Không nhận Vault token. |
| RADIUS-03 | RADIUS user hợp lệ, chưa đăng ký | Có thể PASS | Dev DENY khi `unregistered_user_policies` không cấp quyền. |
| TTL-01 | Token Vault đã hết hạn hoặc bị revoke | Không cần login lại ở bước này | Request bằng token cũ DENY; cần xác thực lại. |

Để kiểm tra capability thực tế cho một token **đã được cấp đúng user**, dùng:

~~~bash
vault token capabilities secret/data/dev/reporting
vault token capabilities secret/data/prod/reporting
~~~

Với policy `reporting-dev-read`, key Dev phải có `read` và key Prod phải không có `read` (thường hiển thị `deny`). Xác nhận tiếp bằng request thật:

~~~bash
vault kv get -mount=secret dev/reporting
vault kv get -mount=secret prod/reporting
~~~

Lệnh thứ hai phải trả lỗi phân quyền. Nếu gặp `404` vì key thiếu, `503` vì Vault không sẵn sàng, lỗi DNS hoặc TLS, **không** đánh dấu ca “Prod DENY” là PASS: phải xác định đúng lỗi quyền (thường `403 permission denied`).

Không chạy các phép thử quyền bằng root token: root token bỏ qua ACL thông thường, khiến kết quả không đại diện cho người dùng thực. Bài test đăng nhập và bài test truy cập KV cần giữ hai kết quả riêng biệt.

## 8. Lỗi hay gặp và cách khoanh vùng

| Triệu chứng | Nơi điều tra | Gợi ý xử lý |
| --- | --- | --- |
| LDAP login lỗi dù password đúng | LDAP connection, TLS/CA, `userdn`, `userattr`, `binddn`/`bindpass` | Kiểm tra mạng, CA, quyền search và DN thực tế. |
| LDAP login PASS nhưng thiếu policy | `groupdn`, `groupfilter`, `groupattr`, group mapping | Đọc group mapping và kết quả membership; đối chiếu schema directory. |
| Okta login lỗi sau password | Okta status/MFA, host, organization, xác thực Okta API | Kiểm tra user status, MFA và cấu hình Okta; không tắt MFA để vượt qua lỗi. |
| Okta login PASS nhưng nhóm không được ánh xạ | Okta API token, group membership, `auth/okta/groups/` | Xác minh quyền token API, tên nhóm, mapping. |
| RADIUS login timeout | Host/UDP 1812, firewall, shared secret, RADIUS backend | Đọc log phía Vault và RADIUS, kiểm tra đường mạng an toàn. |
| RADIUS login PASS nhưng Dev bị DENY | User mapping hoặc `unregistered_user_policies` không cấp quyền | Xem `auth/radius/users/:username`, xác minh chính sách mong đợi. |
| Login PASS nhưng KV trả `403` | Vault ACL và KV v2 API path | Kiểm tra `secret/data/...` và danh sách policy/token. |
| Đổi nhóm nhưng token cũ vẫn đọc được | Policy được gán khi token phát hành | Thu hồi token cần thiết, giảm TTL, tổ chức lại phiên đăng nhập. |
| Java login sai backend | Mount path cấu hình sai hoặc thiếu `.path(...)` | Đối chiếu `vault auth list`, sửa tên mount trong `UsernamePasswordAuthenticationOptions`. |
| Java thỉnh thoảng không đọc được secret | Token TTL/renewal, không có refresh credential, lỗi mạng | Theo dõi token lifecycle, kiểm tra `SessionManager`, không lặp lại login vô hạn khi password sai. |

Nếu Vault bật audit device, đối chiếu bản ghi ở `auth/ldap/login`, `auth/okta/login`, `auth/radius/login` và `secret/data/...` để xác định lỗi xảy ra tại **đăng nhập** hay **truy cập secret**. Không xuất mật khẩu, shared secret, API token, OTP hoặc Vault token vào log ứng dụng. Audit log cũng phải được kiểm soát quyền đọc và thời hạn lưu trữ.

Trong hệ thống production, theo dõi lỗi login theo auth mount, tỷ lệ `403` trên secrets engine, token revocation/expiration, độ trễ IdP và sự cố kết nối LDAP/Okta/RADIUS. Thiết lập giới hạn retry và cảnh báo phù hợp để tránh tạo cơn bão đăng nhập khi hệ thống xác thực bên ngoài gián đoạn.

## 9. Cách áp dụng chính sách bảo mật và vòng đời tài khoản

### Tối thiểu hóa quyền

1. **TLS/transport:** Vault phải được truy cập qua HTTPS với certificate được xác minh; LDAP nên dùng LDAPS/StartTLS; kết nối RADIUS PAP cần được bảo vệ bởi hạ tầng mạng thích hợp.
2. **Secret quản trị:** LDAP bind password, Okta API token và RADIUS shared secret phải được cấp quyền tối thiểu, bảo vệ khi lưu và luân chuyển định kỳ.
3. **Vault policy:** Cấp `read` trên key cụ thể; không cấp `root`, `sudo`, `secret/*` hoặc capability sửa/xóa cho người chỉ cần đọc.
4. **Token lifecycle:** Đặt TTL/max TTL phù hợp; kiểm tra revoke khi nhân viên nghỉ hoặc thay đổi quyền. Vault token có TTL riêng với lease của dynamic secret và hạn dùng chứng thư PKI.
5. **Phân tách auth method:** Không vì LDAP, Okta, RADIUS cùng cho một policy mà cho phép mọi danh tính cùng quyền. Mỗi mapping phải được quản lý và kiểm tra riêng.
6. **MFA:** Giữ MFA của IdP theo chính sách; TOTP là yếu tố chỉ dùng một lần, không phải cấu hình cố định của Spring service.

**Khi phạm vi thay đổi:** đăng nhập bằng chứng thư X.509 dùng Vault **cert auth** với mTLS. Dynamic database credentials cần policy trên database secrets engine và xử lý lease riêng; Transit và PKI cũng yêu cầu ACL trên endpoint tương ứng. Ứng dụng không có người dùng tương tác nên xác thực theo workload.

## 10. Bài thực hành tổng hợp

Trên một Vault test kết nối với cả ba IdP kiểm thử, thực hiện tuần tự:

1. Dùng Vault admin tạo mount KV v2 và hai secret giả; nạp policy `reporting-dev-read` và `reporting-prod-read`.
2. Cấu hình LDAP và mapping nhóm `vault-reporting-dev` → `reporting-dev-read`. Đăng nhập bằng `alice`; xác nhận Dev đọc được và Prod bị từ chối.
3. Cấu hình Okta và mapping Okta group tương ứng. Đăng nhập `bob` với MFA bắt buộc; xác nhận đúng policy và quyền KV.
4. Cấu hình RADIUS shared secret và user mapping của `carol`; thử cả user đã đăng ký và user RADIUS hợp lệ nhưng chưa đăng ký.
5. Dùng `UsernamePasswordAuthenticationOptions.path(...)` trong môi trường Java test để chọn một mount, lấy token và đọc `dev/reporting` qua `VaultTemplate`.
6. Đoạn tuyệt quan trọng: thay user/group mapping ở IdP, thử token cũ và token đăng nhập lại, xác minh TTL và cách revoke. Ghi lại kết quả mà không lưu secret hoặc token trong file bài nộp.

Mẫu biên bản kiểm thử:

| Trường | Ví dụ giá trị |
| --- | --- |
| `test_id` | `OKTA-01` |
| `auth_mount` | `okta` |
| `identity` | `bob` (không ghi password) |
| `login_result` | `PASS` |
| `expected_policy` | `reporting-dev-read` |
| `dev_read` | `PASS` |
| `prod_read` | `DENY_403` |
| `audit_request_id` | Mã request thích hợp từ môi trường thử nghiệm |

### Câu hỏi tự kiểm tra

1. LDAP group và Okta group cùng tên có tự động chia sẻ policy mapping trong Vault hay không? Vì sao?
2. Nếu user RADIUS xác thực thành công nhưng chưa có user mapping, điều gì quyết định quyền trên `secret/data/dev/reporting`?
3. Nếu LDAP login trả token nhưng người dùng không đọc được secret, cần kiểm tra những thông tin nào ở LDAP và Vault?
4. Tại sao không nên gán `unregistered_user_policies=reporting-dev-read` trong một hệ thống có nhiều người dùng RADIUS khác nhau?
5. Khi thay password hoặc thu hồi thành viên nhóm Okta/LDAP, tại sao Vault token đã cấp có thể chưa mất hiệu lực ngay?
6. Trong Spring Vault, ý nghĩa của `.path("ldap")` là gì? Điều gì xảy ra khi backend được mount dưới một đường dẫn khác?
7. Khi nào nên chọn JWT/OIDC hoặc Kubernetes/AppRole thay vì LDAP, Okta auth hay RADIUS cho ứng dụng Java?

## Tài liệu tham khảo

- [HashiCorp Vault: LDAP auth method](https://developer.hashicorp.com/vault/docs/auth/ldap)
- [HashiCorp Vault: Okta auth method](https://developer.hashicorp.com/vault/docs/auth/okta)
- [HashiCorp Vault: RADIUS auth method](https://developer.hashicorp.com/vault/docs/auth/radius)
- [HashiCorp Vault: RADIUS auth API](https://developer.hashicorp.com/vault/api-docs/auth/radius)
- [Spring Vault: Authentication Methods](https://docs.spring.io/spring-vault/reference/vault/authentication.html)

Điều cần ghi nhớ: **LDAP xác thực theo directory và nhóm; Okta xác thực theo tổ chức IdP, nhóm và MFA; RADIUS xác thực qua RADIUS/PAP cùng user mapping. Cả ba chỉ tạo Vault token; quyền sử dụng KV, Transit hoặc PKI do Vault policy quyết định.**
