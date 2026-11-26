# Phân biệt xác thực ứng dụng với xác thực người dùng cuối

## 1. Mục tiêu bài học

Trong hệ thống Java dùng **Spring Vault** và **HashiCorp Vault**, hai câu hỏi thường xuất hiện cùng lúc:

- **Ai đang gọi API của ứng dụng?** Ví dụ, người dùng Alice gửi JWT để truy cập API thanh toán.
- **Ứng dụng nào đang gọi Vault?** Ví dụ, service `payments-api` chạy trong Kubernetes cần đọc khóa kết nối cổng thanh toán.

Đó là **hai luồng xác thực khác nhau**, có chủ thể, credential, điểm kiểm tra và chính sách cấp quyền khác nhau. Kết quả đăng nhập hợp lệ của người dùng không tự tạo quyền đọc secret trong Vault; một ứng dụng có quyền đọc secret trong Vault cũng không đồng nghĩa mọi người dùng của ứng dụng đều được thực hiện mọi chức năng.

Sau bài này, bạn có thể:

1. Phân biệt xác thực (*authentication*) với phân quyền (*authorization*) ở cả API và Vault.
2. Xác định danh tính **workload/service** và danh tính **người dùng cuối** trong sơ đồ yêu cầu.
3. Giải thích vai trò của JWT/OIDC, Kubernetes ServiceAccount, AppRole và Vault token.
4. Tích hợp `VaultTemplate` vào luồng phía máy chủ mà không chuyển token Vault cho trình duyệt.
5. Thiết kế kiểm thử chứng minh hai lớp xác thực, phân quyền hoạt động độc lập.

**Ngữ cảnh module SPRING_VAULT:** ứng dụng Java truy cập secret qua `VaultTemplate`, xác thực theo workload và policy của Vault; bài này đặt nền tảng cho các chủ đề KV secrets, vòng đời token/lease, Transit encryption, PKI, xử lý lỗi và kiểm thử tích hợp sau đó.

## 2. Bốn khái niệm cần tách bạch

| Khái niệm | Câu hỏi | Ví dụ |
| --- | --- | --- |
| Xác thực người dùng cuối | Người đang sử dụng chức năng này là ai? | OIDC provider cấp JWT cho Alice |
| Phân quyền người dùng cuối | Alice được gọi chức năng nào và thao tác trên tài nguyên của ai? | Alice có scope `payments:read` và thuộc đúng tenant |
| Xác thực ứng dụng/workload | Tiến trình đang yêu cầu secret là service nào? | Pod sử dụng Kubernetes ServiceAccount `payments-api` để đăng nhập Vault |
| Phân quyền ứng dụng tại Vault | Workload đó được gọi API/path nào của Vault? | Vault ACL chỉ cho phép `read` trên `secret/data/apps/payments` |

**Authentication** xác minh danh tính người gọi. **Authorization** quyết định thao tác được phép dựa trên danh tính và chính sách. Ở Vault, xác thực thành công thường dẫn đến việc có **Vault token** gắn policy; mọi yêu cầu tiếp theo dùng token ấy để Vault kiểm tra capability trên API path cụ thể.

Không nên nhầm:

- **JWT của người dùng:** do nhà cung cấp danh tính phát hành để gọi API của ứng dụng; API có nhiệm vụ xác thực chữ ký, issuer, expiry và các điều kiện áp dụng.
- **Credential của workload:** ví dụ JWT ServiceAccount Kubernetes hoặc thông tin AppRole; dùng để chứng minh danh tính tiến trình khi đăng nhập Vault.
- **Vault token:** credential do Vault cấp (hoặc đã được cấp trước), được Spring Vault dùng cho các yêu cầu gọi Vault; nó có policy, thời hạn và có thể bị thu hồi.
- **Vault lease:** cơ chế vòng đời của nhiều secret động, tách khỏi thời hạn của token; gia hạn hay thu hồi secret động cần xử lý theo cơ chế lease tương ứng.

Cả JWT người dùng và JWT Kubernetes đều có thể là chuỗi theo định dạng JWT, nhưng **mục đích, issuer, audience, nơi xác minh và quyền được suy ra hoàn toàn khác nhau**. Không suy luận hai token có thể thay thế cho nhau chỉ vì hình thức giống nhau.

## 3. Kiến trúc: hai lớp tin cậy, hai quyết định độc lập

Giả sử `payments-api` phục vụ endpoint xem trạng thái cấu hình thanh toán. Ứng dụng cần đọc secret từ KV v2 của Vault để kiểm tra kết nối cổng thanh toán. Người dùng không cần và không được nhìn thấy secret này.

~~~mermaid
sequenceDiagram
    actor U as Người dùng cuối
    participant IdP as OIDC Identity Provider
    participant API as Spring Boot payments-api
    participant Auth as Spring Security
    participant V as Vault
    U->>IdP: Đăng nhập
    IdP-->>U: Access token JWT dành cho API
    U->>API: GET /api/payments/status + Bearer JWT
    API->>Auth: Xác thực JWT và kiểm tra scope/quyền
    alt JWT thiếu, sai hoặc không đủ quyền
        Auth-->>U: HTTP 401 hoặc 403 từ API
    else JWT và quyền ứng dụng hợp lệ
        Auth-->>API: Cho thực thi controller
        Note over API,V: VaultTemplate dùng danh tính của workload
        API->>V: Đăng nhập Vault (nếu cần cấp/đổi Vault token)
        V-->>API: Vault token gắn ACL policy
        API->>V: GET KV v2 với Vault token của service
        alt Vault ACL cho phép
            V-->>API: Secret cho tiến trình máy chủ
            API-->>U: HTTP 200, chỉ dữ liệu API được phép công khai
        else Vault ACL từ chối
            V-->>API: HTTP 403 từ Vault
            API-->>U: Lỗi phụ thuộc dịch vụ theo hợp đồng API
        end
    end
~~~

Sơ đồ thể hiện hai điểm kiểm tra:

1. **Biên client → ứng dụng:** Spring Security (hoặc lớp bảo mật tương đương) kiểm tra token người dùng và quyền truy cập nghiệp vụ. Endpoint bị từ chối thì không chạy phần mã đọc Vault.
2. **Biên ứng dụng → Vault:** Spring Vault gửi Vault token đại diện **workload**, Vault kiểm tra token cùng policy và đường dẫn API được gọi. Vault không mặc định biết Alice là ai chỉ vì Alice là người kích hoạt HTTP request.

Thành công ở biên thứ nhất **không bảo đảm** thành công ở biên thứ hai. Ngược lại, Vault cho phép `payments-api` đọc secret cũng **không cho phép** bỏ qua kiểm tra quyền trong Spring Security.

## 4. So sánh cụ thể hai loại xác thực

| Tiêu chí | Xác thực ứng dụng tới Vault | Xác thực người dùng cuối tới API |
| --- | --- | --- |
| Chủ thể | Service, Pod, job, máy chủ, CI workload | Cá nhân sử dụng web/mobile/CLI |
| Điểm vào | Vault auth method | API gateway, backend, Spring Security |
| Credential ban đầu | Kubernetes ServiceAccount JWT, AppRole, cloud IAM hoặc phương thức khác | OIDC/OAuth 2.0 access token, session hoặc cơ chế người dùng được chọn |
| Bên xác minh | Vault và hệ thống tin cậy được cấu hình cho auth method | API hoặc IdP/authorization server theo mô hình ứng dụng |
| Credential dùng cho thao tác | Vault token do Vault quản lý | Bearer access token của API, session cookie, v.v. |
| Quyền được kiểm tra | Vault ACL policy trên `secret/data/...`, `transit/...`, `pki/...` | Scope, role, quyền sở hữu dữ liệu, tenant, nghiệp vụ |
| Vòng đời | TTL, renewal/revocation của Vault token và lease secret khi có | Expiry, refresh, logout/revocation theo hệ thống danh tính |
| Mục tiêu | Cho workload sử dụng tài nguyên Vault được cấp | Cho người dùng thực hiện chức năng ứng dụng được cấp |

Một hệ thống có thể dùng OIDC/JWT **để Vault trực tiếp xác thực người dùng**, chẳng hạn khi nhân viên thao tác Vault UI hoặc CLI. Trường hợp đó là một luồng Vault auth dành cho người dùng, khác với JWT mà ứng dụng nhận để bảo vệ API. Cần cấu hình rõ role, audience, issuer, claim mapping và policy tại mỗi bên; không tự coi chúng là cùng một phiên đăng nhập.

## 5. Workload đăng nhập Vault bằng cách nào?

Để tránh lưu một Vault token có tuổi thọ rất dài trong source code, ứng dụng thường lấy Vault token từ phương thức xác thực phù hợp môi trường.

### 5.1. Kubernetes authentication

Một mô hình thông dụng:

1. Pod `payments-api` chạy dưới ServiceAccount riêng, ví dụ `payments-api` trong namespace `production`.
2. Workload cung cấp JWT ServiceAccount cho Vault Kubernetes auth method.
3. Vault xác minh JWT theo cấu hình và kiểm tra ràng buộc của Vault role: tên ServiceAccount, namespace cùng các giới hạn được cấu hình.
4. Vault trả về Vault token kèm policy `payments-secret-read`.
5. Spring Vault dùng token đó khi đọc KV v2; vòng đời token phải được quản lý phù hợp.

Ví dụ lệnh cấu hình **Vault role** (giả định quản trị viên đã bật và cấu hình đúng Kubernetes auth method, gồm thông tin cluster/reviewer cần thiết):

~~~bash
vault write auth/kubernetes/role/payments-api \
  bound_service_account_names="payments-api" \
  bound_service_account_namespaces="production" \
  policies="payments-secret-read" \
  ttl="1h"
~~~

Lệnh trên tạo **vai trò xác thực**: nó ràng buộc danh tính Kubernetes với policy Vault; bản thân nó không tạo ServiceAccount và không cấu hình kết nối Vault với Kubernetes. Trong triển khai thật, ưu tiên danh tính workload riêng cho mỗi service, xác minh audience và các ràng buộc phù hợp với phiên bản Vault/Kubernetes.

### 5.2. AppRole authentication

Trong môi trường máy chủ hoặc automation phù hợp, một workload có thể dùng **AppRole** với `role_id` và `secret_id` để đăng nhập `auth/approle/login`. Các giá trị này phải được phân phối qua kênh an toàn, giới hạn số lần dùng/TTL khi phù hợp; không commit `secret_id` vào Git.

### 5.3. Token tĩnh trong phòng lab

Trong bài thực hành đơn giản có thể tạo Vault token ngắn hạn rồi truyền qua biến môi trường cho tiến trình Java để minh họa rõ hai lớp xác thực. Đây là **cách mô phỏng**, không phải thiết kế quản lý workload token cho production. Trong production cần chọn auth method, session/renewal và rotation phù hợp; có thể tích hợp qua Spring Vault hoặc cơ chế hỗ trợ tương ứng của Spring Cloud Vault.

## 6. Phân quyền Vault cho chính workload

Bài lab giả định mount KV v2 tên `secret/`, với một secret tại key `apps/payments`. Khi Vault API truy cập **nội dung** KV v2, path thực tế là:

~~~text
/v1/secret/data/apps/payments
~~~

Policy ACL chỉ cho phép workload đọc đúng path đó:

~~~hcl
path "secret/data/apps/payments" {
  capabilities = ["read"]
}
~~~

Nguyên tắc này có ba hệ quả:

- Service chỉ đọc nội dung secret ở `apps/payments`; policy này không cấp `create` hoặc `update`.
- Path ACL chứa phân đoạn **`data/`** của KV v2. Chỉ viết `secret/apps/payments` là sai đối với API dữ liệu của KV v2.
- `read` trên `secret/data/apps/payments` không tự cấp `list` trên `secret/metadata/...`, cũng không cấp quyền gọi Transit encryption hoặc PKI.

Một token ứng dụng gắn policy đó được phép đọc secret cho **tiến trình service**. Không chuyển token ứng dụng hoặc giá trị secret ra response, JavaScript trên trình duyệt, mobile app hay URL.

## 7. Tích hợp Spring Security và VaultTemplate

Ví dụ sau dùng Spring Boot với Spring Security OAuth2 Resource Server để xác thực JWT người dùng, và Spring Vault để đọc secret bằng Vault token của **ứng dụng**. Hai phần cấu hình có nhiệm vụ riêng.

### 7.1. Spring Security xác thực người dùng

Giả sử JWT do IdP tin cậy phát hành, trong claim `scope` có giá trị `payments:read`. Spring Security có thể ánh xạ scope thành authority `SCOPE_payments:read` theo cấu hình mặc định.

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class ApiSecurityConfig {

    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/payments/status")
                .hasAuthority("SCOPE_payments:read")
                .anyRequest().authenticated()
            )
            .oauth2ResourceServer(oauth2 -> oauth2.jwt(Customizer.withDefaults()));

        return http.build();
    }
}
~~~

Ví dụ cần dependency OAuth2 Resource Server và cấu hình JWT decoder. Khi dùng issuer discovery, cấu hình một issuer thực sự tin cậy; địa chỉ dưới đây chỉ minh họa, phải thay bằng IdP đang sử dụng:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://idp.example.test/realms/demo
~~~

Trong production, xác minh thêm audience dự kiến của API và chính sách claim/tenant theo yêu cầu hệ thống. Kiểm tra scope chỉ là **một lớp**; với tài nguyên cá nhân hoặc nhiều tenant, backend còn phải kiểm tra quyền sở hữu dữ liệu, không suy ra quyền chỉ từ một scope chung.

### 7.2. VaultTemplate dùng danh tính của ứng dụng

Trong phòng lab, cấu hình `VaultTemplate` bằng **Vault token của service**, cung cấp qua `VAULT_APP_TOKEN`. Token này không lấy từ header `Authorization` do người dùng gửi.

~~~java
import java.net.URI;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.vault.authentication.TokenAuthentication;
import org.springframework.vault.client.VaultEndpoint;
import org.springframework.vault.core.VaultTemplate;

@Configuration
public class VaultClientConfig {

    @Bean
    VaultTemplate vaultTemplate() {
        String url = System.getenv().getOrDefault(
                "VAULT_ADDR", "http://127.0.0.1:8200");
        String serviceToken = System.getenv("VAULT_APP_TOKEN");

        if (serviceToken == null || serviceToken.isBlank()) {
            throw new IllegalStateException("VAULT_APP_TOKEN is required");
        }

        VaultEndpoint endpoint = VaultEndpoint.from(URI.create(url));
        return new VaultTemplate(
                endpoint,
                new TokenAuthentication(serviceToken)
        );
    }
}
~~~

`TokenAuthentication` minh họa cách truyền token ở bước học. Khi triển khai thực tế, lựa chọn `ClientAuthentication` thích hợp cho workload và cơ chế quản lý phiên/token tương ứng để tránh phụ thuộc vào token tĩnh; chỉ cấu hình `VaultTemplate` được sử dụng trong phạm vi service.

### 7.3. Đọc secret ở máy chủ và trả dữ liệu đã kiểm soát

Giả sử KV v2 chứa field `gateway_key`. Service sau chỉ xác nhận field đó tồn tại, không trả giá trị khóa bí mật:

~~~java
import java.util.Map;

import org.springframework.stereotype.Service;
import org.springframework.vault.core.VaultKeyValueOperationsSupport;
import org.springframework.vault.core.VaultTemplate;
import org.springframework.vault.support.VaultResponse;

@Service
public class PaymentConfigService {

    private final VaultTemplate vault;

    public PaymentConfigService(VaultTemplate vault) {
        this.vault = vault;
    }

    public boolean isGatewayConfigured() {
        VaultResponse response = vault.opsForKeyValue(
                "secret",
                VaultKeyValueOperationsSupport.KeyValueBackend.KV_2
        ).get("apps/payments");

        if (response == null || response.getData() == null) {
            return false;
        }

        Map<String, Object> data = response.getData();
        Object gatewayKey = data.get("gateway_key");
        return gatewayKey instanceof String
                && !((String) gatewayKey).isBlank();
    }
}
~~~

Controller cung cấp phản hồi nghiệp vụ tối thiểu:

~~~java
import java.util.Map;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/payments")
public class PaymentStatusController {

    private final PaymentConfigService config;

    public PaymentStatusController(PaymentConfigService config) {
        this.config = config;
    }

    @GetMapping("/status")
    public Map<String, Boolean> status() {
        return Map.of("configured", config.isGatewayConfigured());
    }
}
~~~

Luồng khi có yêu cầu hợp lệ:

1. `GET /api/payments/status` qua Spring Security: xác minh **JWT người dùng** và authority `SCOPE_payments:read`.
2. Controller gọi `PaymentConfigService`.
3. Service gọi `VaultTemplate` với **VAULT_APP_TOKEN** (hoặc token workload được quản lý tự động theo cấu hình thực tế).
4. Vault áp policy trên `secret/data/apps/payments`.
5. Ứng dụng chỉ trả về cờ `configured`; không gửi secret hay Vault token cho người dùng.

Các đoạn Java này mô tả kiến trúc. Để chạy thực tế cần Spring Web, Spring Security, OAuth2 Resource Server, Spring Vault cùng issuer/JWT và Vault server hợp lệ; nếu workload chưa có quyền thì Vault sẽ từ chối yêu cầu dù người dùng đã đăng nhập thành công.

## 8. Bài thực hành với Vault dev server

Các lệnh dưới đây dành cho **Vault dev server riêng của bài lab**, dùng Bash và Vault CLI đã cài đặt. Không thực hiện trên Vault production và không dùng dữ liệu thật.

### 8.1. Khởi tạo secret và policy

Chạy Vault ở terminal thứ nhất:

~~~bash
vault server -dev -dev-root-token-id=root
~~~

Ở terminal thứ hai, dùng root token **chỉ để chuẩn bị** tài nguyên:

~~~bash
export VAULT_ADDR="http://127.0.0.1:8200"
export VAULT_TOKEN="root"

# Dev mode thông thường đã có KV v2 ở secret/.
vault secrets list -detailed

vault kv put -mount=secret apps/payments \
  gateway_key="DUMMY_FOR_LOCAL_LAB"

vault policy write payments-secret-read - <<'HCL'
path "secret/data/apps/payments" {
  capabilities = ["read"]
}
HCL
~~~

Nếu mount `secret/` không tồn tại, quản trị viên phải tạo KV v2 tại đó trước khi `vault kv put`. Nếu đã tồn tại, cần xác nhận đúng version 2; không bật chồng mount cùng path.

### 8.2. Tạo token workload và token không có quyền

~~~bash
APP_VAULT_TOKEN="$(vault token create \
  -policy=payments-secret-read \
  -ttl=15m \
  -field=token)"

UNPRIVILEGED_TOKEN="$(vault token create \
  -policy=default \
  -ttl=15m \
  -field=token)"
~~~

Trong ví dụ, `APP_VAULT_TOKEN` mô phỏng danh tính đã được Vault xác thực của ứng dụng. Nó **khác** JWT người dùng được gửi vào API Spring Boot. Token `UNPRIVILEGED_TOKEN` giúp chứng minh Vault thực sự thực thi ACL.

### 8.3. Kiểm chứng ở biên Vault

~~~bash
# Workload được phép đọc: HTTP 200.
curl -sS -o /dev/null -w "app read: %{http_code}\n" \
  -H "X-Vault-Token: $APP_VAULT_TOKEN" \
  "$VAULT_ADDR/v1/secret/data/apps/payments"

# Token không có quyền đọc: HTTP 403.
curl -sS -o /dev/null -w "unprivileged read: %{http_code}\n" \
  -H "X-Vault-Token: $UNPRIVILEGED_TOKEN" \
  "$VAULT_ADDR/v1/secret/data/apps/payments"

# Token ứng dụng không có quyền ghi: HTTP 403.
curl -sS -o /dev/null -w "app write: %{http_code}\n" \
  -X POST \
  -H "X-Vault-Token: $APP_VAULT_TOKEN" \
  -H "Content-Type: application/json" \
  --data '{"data":{"gateway_key":"SHOULD_NOT_CHANGE"}}' \
  "$VAULT_ADDR/v1/secret/data/apps/payments"
~~~

Các giá trị kỳ vọng là **200, 403, 403** theo thứ tự. Nếu lần ghi cuối thất bại, dữ liệu secret và số phiên bản phải giữ nguyên. Khi chạy ứng dụng Java trong terminal khác, chuyển token mô phỏng qua biến môi trường:

~~~bash
export VAULT_ADDR="http://127.0.0.1:8200"
export VAULT_APP_TOKEN="$APP_VAULT_TOKEN"
~~~

Cần có một IdP/JWT test **độc lập** để kiểm tra phía API. Không dùng `APP_VAULT_TOKEN` làm Bearer JWT người dùng.

### 8.4. Kiểm chứng ở biên API

Sau khi khởi động ứng dụng với cấu hình JWT đúng, thử ba tình huống:

~~~bash
# Không có JWT người dùng: kỳ vọng 401 từ Spring Security.
curl -i http://localhost:8080/api/payments/status

# JWT người dùng hợp lệ nhưng không có payments:read:
# kỳ vọng 403 từ Spring Security.
curl -i \
  -H "Authorization: Bearer <VALID_JWT_WITHOUT_REQUIRED_SCOPE>" \
  http://localhost:8080/api/payments/status

# JWT người dùng hợp lệ, đúng scope và các điều kiện khác:
# kỳ vọng 200 khi Vault token của service cũng hợp lệ.
curl -i \
  -H "Authorization: Bearer <VALID_JWT_WITH_PAYMENTS_READ_SCOPE>" \
  http://localhost:8080/api/payments/status
~~~

Các chuỗi `<...>` là placeholder, phải thay bằng token thử nghiệm thật do **IdP** của môi trường test cấp. Ví dụ không cung cấp cơ chế phát hành JWT giả hoặc bỏ kiểm tra chữ ký; test tích hợp có thể dùng IdP test riêng hoặc cơ chế JWT test được cấu hình kiểm soát.

Với endpoint trên, yêu cầu bị Spring Security từ chối sẽ không đi vào controller, nên không cần đọc Vault. Khi ứng dụng đã qua kiểm tra người dùng nhưng Vault token bị revoke/hết hạn hoặc không còn policy, Vault sẽ trả lỗi ở lớp backend; ứng dụng phải xử lý như lỗi phụ thuộc dịch vụ phù hợp và ghi nhận cho vận hành.

## 9. Ma trận kiểm thử hai lớp

| Trường hợp | JWT người dùng | Quyền Vault của service | Kết quả cần quan sát |
| --- | --- | --- | --- |
| A | Không gửi | Token service hợp lệ | API trả **401**; không gọi Vault |
| B | Hợp lệ, thiếu `payments:read` | Token service hợp lệ | API trả **403**; không gọi Vault |
| C | Hợp lệ, đủ `payments:read` | `read` đúng KV path | API trả **200** với dữ liệu an toàn |
| D | Hợp lệ, đủ `payments:read` | Token service không có `read` | Vault từ chối **403**; API báo lỗi backend theo thiết kế |
| E | Hợp lệ, đủ `payments:read` | Token service bị revoke/hết hạn | Vault từ chối do token không hợp lệ; API báo lỗi backend theo thiết kế |
| F | Hợp lệ, đủ scope nhưng sai tenant/tài nguyên | Token service hợp lệ | API phải từ chối theo phân quyền nghiệp vụ trước khi đọc dữ liệu nhạy cảm |
| G | Hợp lệ, đủ quyền | Vault đọc được nhưng secret/key không tồn tại | Xử lý trạng thái dữ liệu thiếu, không coi là thiếu quyền người dùng |

**Lưu ý về HTTP:** `401`/`403` ở API phản ánh chính sách **API**; `403` từ Vault phản ánh kiểm tra **Vault token/policy**. Backend không nên tự động trả `403` cho người dùng chỉ vì tài khoản workload không được Vault cấp quyền. Đó thường là lỗi cấu hình hay tình trạng vận hành của backend, cần phân loại và giám sát riêng.

Để tự động hóa, có thể viết kiểm thử tích hợp dùng JWT hợp lệ của test IdP, thay đổi scope và tạo các Vault token có policy khác nhau trên Vault dev/Testcontainers; đếm số lần `VaultTemplate` được gọi ở các trường hợp A/B, đồng thời kiểm tra status và nội dung phản hồi đối với C/D/E. Đảm bảo bài kiểm thử không log giá trị `gateway_key`.

## 10. Các trường hợp dễ nhầm

### "Người dùng có JWT hợp lệ, vậy có quyền đọc Vault?"

**Không.** JWT người dùng chỉ cung cấp bằng chứng nhận dạng và các claim để API đánh giá. Vault không mặc định chấp nhận JWT đó. Nếu thật sự cần đăng nhập Vault trực tiếp bằng JWT/OIDC, phải cấu hình Vault auth method và role mapping riêng, kèm policy phù hợp.

### "Service có Vault token đọc được tất cả secret, có cần phân quyền API nữa không?"

**Có.** Vault ACL không biết một yêu cầu trong `payments-api` thuộc Alice, Bob hay tenant nào nếu tất cả được xử lý dưới cùng token service. Ứng dụng vẫn phải giới hạn chức năng và dữ liệu theo quyền của từng người dùng. Nên thu hẹp policy Vault của service theo các secret thật sự cần, tránh wildcard cấp rộng.

### "Có thể chuyển nguyên Bearer JWT của người dùng xuống Vault để khỏi xác thực workload?"

**Không nên tự động chuyển tiếp.** Bearer JWT API có audience và mục đích dành cho API; Vault chỉ có thể xác minh khi được cấu hình auth method phù hợp. Nếu yêu cầu audit và phân quyền trực tiếp theo người dùng tại Vault, cần thiết kế rõ cơ chế delegated identity/token exchange, claim mapping, Vault policies, hạn sử dụng và cách cách ly từng request. Đó là một kiến trúc khác, không phải hành vi mặc định của `VaultTemplate`.

### "Đăng nhập Vault thành công thì token không bao giờ hết hạn?"

**Không.** Vault token có TTL, có thể gia hạn tùy loại và cấu hình, đồng thời có thể bị revoke. Một `VaultTemplate` dùng token tĩnh không tự đảm bảo thay mới token. Nếu dùng dynamic database credential, PKI certificate hoặc các secret có lease, vòng đời lease của secret còn cần được quản lý riêng.

### "Lỗi Vault 403 và API 403 có giống nhau?"

Cả hai đều có thể mang mã **403**, nhưng khác lớp và nguyên nhân. Trong log/metric nên ghi rõ nguồn lỗi, Vault path đã được chuẩn hóa, workload/role liên quan và request correlation ID; **không** ghi token, credential, dữ liệu secret, hay các claim nhạy cảm.

## 11. Câu hỏi và bài tập tự kiểm tra

1. Nếu Alice không có quyền `payments:read`, nhưng `payments-api` đang sở hữu Vault token có `read`, hệ thống phải dừng ở lớp nào?
2. Nếu JWT của Alice hợp lệ và đủ scope, nhưng Vault token của service đã bị thu hồi, đây là lỗi phân quyền của Alice hay lỗi ở biên service–Vault?
3. Vì sao Vault policy `secret/data/apps/payments` không tự phân tách quyền giữa Alice và Bob?
4. Khi chuyển môi trường chạy từ Kubernetes sang CI agent, điều gì cần thay đổi: JWT của người dùng, phương thức xác thực workload, hay cả hai?
5. Khi service chuyển từ KV v2 sang Transit/PKI, có thể tái sử dụng policy KV cũ không? Vì sao?

**Gợi ý tự đối chiếu:** (1) Spring Security/quyền nghiệp vụ, (2) lớp workload–Vault, (3) service dùng một danh tính chung trừ khi xây cơ chế ủy quyền riêng, (4) chủ yếu là cách workload xác thực với Vault phù hợp môi trường, (5) không vì mỗi engine có API path/capability riêng.

## 12. Kết luận và vệ sinh môi trường lab

Trong kiến trúc Spring Vault, **JWT người dùng bảo vệ chức năng API**, còn **Vault token của workload bảo vệ thao tác với secret**. Mỗi biên có điểm xác thực, chính sách và vòng đời credential độc lập. Ứng dụng Java dùng `VaultTemplate` đọc secret thay cho người dùng; nó phải tự chịu trách nhiệm quyết định dữ liệu nào được phép xuất hiện trong phản hồi API.

Sau khi thử nghiệm trên môi trường dev riêng, thu hồi hai token và dọn policy/secret mẫu bằng root token:

~~~bash
vault token revoke "$APP_VAULT_TOKEN"
vault token revoke "$UNPRIVILEGED_TOKEN"

vault kv metadata delete -mount=secret apps/payments
vault policy delete payments-secret-read
~~~

Lệnh xóa metadata KV v2 loại bỏ dữ liệu phiên bản của secret tương ứng; chỉ chạy trong **môi trường lab đã kiểm tra đúng path**. Bài học đạt mục tiêu khi bạn phân biệt đúng nguồn `401/403`, chứng minh service truy cập Vault theo policy riêng, và xác nhận token/secret không bị trả cho người dùng cuối.
