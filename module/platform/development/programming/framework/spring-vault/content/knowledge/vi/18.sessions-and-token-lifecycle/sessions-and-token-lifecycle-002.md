# SimpleSessionManager và phạm vi trách nhiệm

## 1. Vì sao ứng dụng Spring Vault cần quản lý phiên?

Một ứng dụng Java sử dụng **Spring Vault** và `VaultTemplate` để đọc KV secrets, gọi Transit encryption hoặc PKI có thể gửi nhiều yêu cầu đến HashiCorp Vault. Mỗi yêu cầu cần một Vault token có hiệu lực, nhưng việc đăng nhập lại theo workload (Kubernetes, AppRole, AWS IAM...) sau **mỗi** thao tác vừa tốn thời gian vừa tăng tải lên auth method.

`SimpleSessionManager` cung cấp cách quản lý phiên tối giản: lấy `VaultToken` từ `ClientAuthentication` và **tái sử dụng token** trong các lần gọi tiếp theo. Điểm giới hạn cần ghi nhớ: nó **không tự gia hạn token, không tự đăng nhập lại khi token hết hạn và không tự revoke token lúc dừng ứng dụng**.

Bài thuộc chương **Phiên và vòng đời token** của module **SPRING_VAULT**, giúp người học:

1. Hiểu quan hệ giữa `ClientAuthentication`, `SessionManager`, `VaultToken` và `VaultTemplate`.
2. Giải thích cache token, đồng bộ login ban đầu và phạm vi tái sử dụng của `SimpleSessionManager`.
3. Nhận biết token đã expired/revoked, phân biệt lỗi xác thực với lỗi policy.
4. So sánh `SimpleSessionManager` và `LifecycleAwareSessionManager`.
5. Viết ví dụ Java và kiểm chứng với Vault dev server.

## 2. Những thành phần tham gia

| Thành phần | Chức năng | Phạm vi |
| --- | --- | --- |
| `ClientAuthentication` | `login()` để trả `VaultToken` | Có thể gọi login endpoint hoặc trả token đã được cấu hình |
| `VaultToken` | Định danh phiên truy cập Vault | Chỉ chứa giá trị token; không phải policy hay bộ lập lịch |
| `SessionManager` | Cung cấp token qua `getSessionToken()` | Interface cho chiến lược quản lý token |
| `SimpleSessionManager` | Lấy token lần đầu và dùng lại | Không renew/revoke |
| `VaultTemplate` | Thực hiện thao tác với Vault bằng token | Không quyết định token có những capability nào |
| Vault server | Xác minh token và ACL của từng request | Giới hạn thời gian, policy, path và capability |

**Xác thực workload** quyết định ứng dụng được cấp token dưới danh tính nào. **Phân quyền Vault** quyết định token đó được phép thực hiện thao tác nào. `SimpleSessionManager` chỉ xử lý cách Java lấy và sử dụng token; nó không nâng quyền, đổi role hoặc sửa policy.

## 3. Luồng SimpleSessionManager

~~~mermaid
sequenceDiagram
    participant A as Java application
    participant T as VaultTemplate
    participant S as SimpleSessionManager
    participant C as ClientAuthentication
    participant V as Vault
    A->>T: kv.get("apps/demo")
    T->>S: getSessionToken()
    alt Chưa có token trong manager
        S->>C: login()
        C-->>S: VaultToken T1
        Note over S: Lưu T1
    end
    S-->>T: T1
    T->>V: GET KV v2 với T1
    V-->>T: Kết quả theo ACL và hiệu lực token
    A->>T: kv.get("apps/demo") lần hai
    T->>S: getSessionToken()
    S-->>T: T1 đã lưu
    T->>V: GET KV v2 với T1
    V-->>T: Kết quả
~~~

Khi lần đầu cần token, `SimpleSessionManager` yêu cầu `ClientAuthentication.login()`. Việc login được **đồng bộ**: các luồng cùng sử dụng **một instance** không đua nhau đăng nhập trùng lặp tại thời điểm khởi tạo phiên. Token được lưu trong manager và trả lại cho những lời gọi sau.

Việc lấy token có thể diễn ra khi `VaultTemplate` khởi tạo hoặc khi ứng dụng phát sinh thao tác có xác thực, tùy cách cấu hình. Token được cache **theo đối tượng manager**, không phải bộ nhớ dùng chung giữa các JVM, Pod hay mọi Spring application context.

Mỗi lần request đến Vault, server vẫn xác minh token và quyền ACL. Một token còn nằm trong bộ nhớ ứng dụng **không đồng nghĩa** nó vẫn hợp lệ trên Vault.

## 4. Ranh giới trách nhiệm của SimpleSessionManager

Có thể khởi tạo trực tiếp qua các API của Spring Vault:

~~~java
ClientAuthentication authentication = /* cơ chế phù hợp workload */;
SessionManager sessions = new SimpleSessionManager(authentication);
VaultToken token = sessions.getSessionToken();
~~~

Các lớp nằm trong `org.springframework.vault.authentication` (`ClientAuthentication`, `SessionManager`, `SimpleSessionManager`); `VaultToken` nằm trong `org.springframework.vault.support`.

| Hành vi | SimpleSessionManager thực hiện? |
| --- | --- |
| Nhận `ClientAuthentication` khi khởi tạo | Có |
| Gọi `ClientAuthentication.login()` để lấy token ban đầu | Có |
| Đồng bộ yêu cầu login đầu tiên của nhiều luồng | Có |
| Giữ và trả token cho các yêu cầu sau | Có |
| Lập lịch gia hạn token theo TTL | **Không** |
| Tự gọi `auth/token/renew-self` | **Không** |
| Tự nhận diện token hết hạn rồi tạo phiên mới | **Không** |
| Tự revoke token khi Spring context bị hủy | **Không** |
| Tự xoay vòng AppRole secret ID, Kubernetes JWT, AWS credential | **Không** |
| Tự quản lý lease của database credential hoặc chứng thư PKI | **Không** |

**Hệ quả thực tế:** nếu token T1 bị thu hồi hoặc hết thời hạn, manager vẫn có thể trả lại T1 từ bộ nhớ. Vault có thể phản hồi **403 Forbidden** khi nhận yêu cầu dùng T1. Việc gọi `getSessionToken()` lặp lại không phải thao tác buộc manager đăng nhập lại.

Cũng không nên đặt một `SimpleSessionManager` mới vào mỗi method đọc secret: mỗi instance mới có cache riêng, làm mất lợi ích tái sử dụng và có thể tạo nhiều lượt login nếu `ClientAuthentication` cần gọi Vault để lấy token.

## 5. TTL token khác TTL của secret lease

Token TTL do **Vault server** quyết định theo auth method, role, chính sách và giới hạn thời hạn. Spring Vault có thể được thông báo token có thể gia hạn hay không; `SimpleSessionManager` vẫn không tự lập lịch sử dụng thông tin đó.

Ví dụ một token không được gia hạn có TTL 60 giây:

~~~text
t = 00s   Workload nhận Vault token T1, TTL=60s
t = 05s   Spring Vault dùng T1 -> GET thành công
t = 25s   Spring Vault dùng lại T1 -> GET thành công
t = 60s   T1 hết hiệu lực theo Vault server
t = 65s   SimpleSessionManager vẫn có thể trả T1
t = 65s   Vault từ chối request dùng T1 (thường HTTP 403)
~~~

Nếu chương trình chạy dài hơn TTL, cần cơ chế gia hạn/re-authentication phù hợp, không thể tăng `SimpleSessionManager` lên thành hệ thống renewal bằng cách gọi lại `getSessionToken()`.

Phân biệt bốn khái niệm:

- **Token TTL:** thời gian Vault cho phép dùng token của workload.
- **Token renewal:** gia hạn token đủ điều kiện, chịu giới hạn của Vault.
- **Secret lease TTL:** thời gian tồn tại credential động, ví dụ tài khoản database do Vault cấp hoặc chứng thư PKI.
- **Lease renewal/revocation:** hoạt động riêng trên secret động; token còn hiệu lực không có nghĩa mọi secret lease đã được gia hạn.

Spring Vault có cơ chế quản lý lease riêng. `SimpleSessionManager` không quản lý vòng đời database credential, Transit key, PKI certificate, và cũng không tự cấp quyền trên các API `secret/data/...`, `transit/...`, `pki/...`.

## 6. Ví dụ Java: cấu hình SimpleSessionManager tường minh

Đoạn ví dụ sau dành cho **Spring Vault 4.1+**, sử dụng API `VaultClient`. Để dễ nhìn hành vi cache, ví dụ nhận token ngắn hạn từ biến môi trường `LAB_VAULT_TOKEN`; đây là cách học tập, không phải phương thức xác thực workload dành cho production.

~~~java
import java.net.URI;

import org.springframework.vault.authentication.ClientAuthentication;
import org.springframework.vault.authentication.SessionManager;
import org.springframework.vault.authentication.SimpleSessionManager;
import org.springframework.vault.authentication.TokenAuthentication;
import org.springframework.vault.client.VaultClient;
import org.springframework.vault.client.VaultEndpoint;
import org.springframework.vault.core.VaultKeyValueOperationsSupport;
import org.springframework.vault.core.VaultTemplate;
import org.springframework.vault.support.VaultResponse;

public class SimpleSessionDemo {

    public static void main(String[] args) {
        String address = System.getenv().getOrDefault(
                "VAULT_ADDR", "http://127.0.0.1:8200");
        String token = System.getenv("LAB_VAULT_TOKEN");

        if (token == null || token.isBlank()) {
            throw new IllegalArgumentException("LAB_VAULT_TOKEN is required");
        }

        VaultEndpoint endpoint =
                VaultEndpoint.from(URI.create(address));
        ClientAuthentication authentication =
                new TokenAuthentication(token);

        SessionManager sessionManager =
                new SimpleSessionManager(authentication);

        VaultClient client = VaultClient.builder()
                .endpoint(endpoint)
                .build();

        VaultTemplate vault =
                new VaultTemplate(client, sessionManager);

        for (int i = 1; i <= 2; i++) {
            VaultResponse response = vault.opsForKeyValue(
                    "secret",
                    VaultKeyValueOperationsSupport.KeyValueBackend.KV_2
            ).get("apps/session-demo");

            if (response == null || response.getData() == null) {
                throw new IllegalStateException("Secret not found");
            }

            // Không log giá trị secret hoặc token.
            System.out.println("READ_OK attempt=" + i);
        }
    }
}
~~~

Cả hai lượt đọc dùng chung một `sessionManager`; `VaultTemplate` gửi token đó lên Vault. `TokenAuthentication` lấy token đã cung cấp từ môi trường, do đó đoạn code này minh họa việc tái sử dụng token, **không chứng minh có hai hay một lượt gọi endpoint đăng nhập Vault**.

Với **Spring Vault 3.x**, có thể thay phần tạo template bằng overload nhận `VaultEndpoint`, `ClientHttpRequestFactory` và `SessionManager`:

~~~java
import org.springframework.http.client.SimpleClientHttpRequestFactory;

VaultTemplate vault = new VaultTemplate(
        endpoint,
        new SimpleClientHttpRequestFactory(),
        sessionManager
);
~~~

Overload này vẫn hiện diện trong Spring Vault 4.1 nhưng được đánh dấu **deprecated**. Khi cập nhật major version, kiểm tra API tương ứng với dependency của dự án.

## 7. Kiểm chứng cache mà không cần Vault server

Để phân biệt **cache token** với việc đăng nhập mỗi lần, dùng một `ClientAuthentication` giả, đếm số lần gọi `login()`. Ví dụ Java sau chỉ là kiểm tra mức thành phần, không gửi token giả cho Vault:

~~~java
import java.util.concurrent.atomic.AtomicInteger;
import org.springframework.vault.authentication.ClientAuthentication;
import org.springframework.vault.authentication.SimpleSessionManager;
import org.springframework.vault.support.VaultToken;

public class SessionCacheCheck {

    public static void main(String[] args) {
        AtomicInteger loginCalls = new AtomicInteger();

        ClientAuthentication fakeAuth = () -> {
            loginCalls.incrementAndGet();
            return VaultToken.of("fake-token-for-unit-test");
        };

        SimpleSessionManager sessions =
                new SimpleSessionManager(fakeAuth);

        VaultToken first = sessions.getSessionToken();
        VaultToken second = sessions.getSessionToken();

        if (loginCalls.get() != 1 || first != second) {
            throw new AssertionError("Unexpected token reuse");
        }

        System.out.println("PASS loginCalls=" + loginCalls.get());
    }
}
~~~

Kỳ vọng:

~~~text
PASS loginCalls=1
~~~

Nếu chạy nhiều luồng, cần **dùng chung đúng một instance** rồi kiểm tra login ban đầu không bị nhân lên vì race condition. Khi tạo một `SimpleSessionManager` mới cho mỗi luồng, kết quả sẽ khác vì mỗi manager có cache của riêng mình.

Không nên kết luận rằng token vẫn còn hợp lệ chỉ vì `first == second`. Phép kiểm tra trên không xác thực token, TTL hay policy với Vault thật.

## 8. Bài thực hành Vault: thành công, hết hạn và bị thu hồi

Thực hành chỉ dùng **Vault dev server** và dữ liệu giả, chạy lệnh Bash trên Linux/macOS/Git Bash. Cần Vault CLI và cURL nếu muốn kiểm tra mã HTTP trực tiếp.

### 8.1. Chuẩn bị Vault và KV v2

Terminal thứ nhất:

~~~bash
vault server -dev -dev-root-token-id=root
~~~

Terminal thứ hai:

~~~bash
export VAULT_ADDR="http://127.0.0.1:8200"
export VAULT_TOKEN="root"

vault status
vault secrets list -detailed
~~~

Trong chế độ dev, mount `secret/` thường đã được bật ở dạng KV v2. Nếu **chưa tồn tại**, tạo bằng lệnh sau; nếu đã tồn tại, chỉ xác nhận đúng version, không mount chồng:

~~~bash
vault secrets enable -path=secret -version=2 kv
~~~

Tạo secret thử nghiệm và policy **chỉ đọc** cho đúng key:

~~~bash
vault kv put -mount=secret apps/session-demo \
  value="for-local-testing-only"

vault policy write session-demo-read - <<'HCL'
path "secret/data/apps/session-demo" {
  capabilities = ["read"]
}
HCL
~~~

Lưu ý KV v2 dùng API path **`secret/data/apps/session-demo`**, dù lệnh CLI sử dụng key logic `apps/session-demo`.

### 8.2. Cấp token ngắn hạn cho ứng dụng

Dùng root token chỉ để tạo token mô phỏng; không truyền root token vào Java:

~~~bash
APP_TOKEN="$(vault token create \
  -policy=session-demo-read \
  -ttl=90s \
  -renewable=false \
  -field=token)"
~~~

Vault có thể giới hạn TTL bởi cấu hình hệ thống. Dùng `-renewable=false` để việc không gia hạn trở nên rõ ràng trong lab; **`SimpleSessionManager` vẫn không tự renew cả khi token renewable**.

Kiểm tra quyền trước khi TTL hết:

~~~bash
VAULT_TOKEN="$APP_TOKEN" vault kv get \
  -mount=secret apps/session-demo
~~~

Kỳ vọng lệnh đọc thành công. Nếu muốn chạy Java ví dụ ở mục 6, truyền cùng token qua biến môi trường:

~~~bash
export LAB_VAULT_TOKEN="$APP_TOKEN"

# Chạy lớp SimpleSessionDemo đã biên dịch trong IDE/ứng dụng Java.
# Không in giá trị LAB_VAULT_TOKEN vào terminal hoặc CI logs.
~~~

Kỳ vọng Java in `READ_OK attempt=1` và `READ_OK attempt=2`, khi token còn hạn và secret tồn tại.

### 8.3. Kiểm tra sau khi token hết hạn

Để token hết hạn theo TTL thực tế rồi dùng **cùng token cũ**, không tạo lại token:

~~~bash
VAULT_TOKEN="$APP_TOKEN" vault kv get \
  -mount=secret apps/session-demo
~~~

Vault thường từ chối với lỗi liên quan token/permission denied (HTTP 403). Trong ứng dụng Java còn chạy, `SimpleSessionManager` vẫn có thể trả token cũ; yêu cầu `kv.get` tiếp theo sẽ thất bại. Nếu khởi động lại Java nhưng vẫn truyền `LAB_VAULT_TOKEN` cũ, một manager mới **không thể tự làm token cũ hợp lệ trở lại**.

### 8.4. Kiểm tra revoke trước khi TTL hết

Tạo token khác có TTL dài hơn cho phép kiểm tra chủ động revoke:

~~~bash
REVOKE_TOKEN="$(vault token create \
  -policy=session-demo-read \
  -ttl=10m \
  -field=token)"

VAULT_TOKEN="$REVOKE_TOKEN" vault kv get \
  -mount=secret apps/session-demo

# Shell hiện vẫn giữ VAULT_TOKEN=root, nên revoke dùng quyền root.
vault token revoke "$REVOKE_TOKEN"

VAULT_TOKEN="$REVOKE_TOKEN" vault kv get \
  -mount=secret apps/session-demo
~~~

Kết quả: lần đọc trước revoke thành công; lần đọc sau revoke thất bại. Chứng minh **Vault server quyết định hiệu lực token**, không phải giá trị token đang được cache trong JVM.

### 8.5. Phân biệt lỗi phân quyền với token hết hiệu lực

Token còn hạn nhưng không có policy `read` đúng path vẫn bị Vault từ chối. Đây là vấn đề **ACL**, không phải lỗi của `SimpleSessionManager`. Tương tự, nếu token có `read` nhưng key không tồn tại, kết quả thường là **404/không có dữ liệu**, không nên tự động xử lý thành lỗi quyền truy cập.

Trong service Java, cần phân loại nguồn lỗi để vận hành: xác thực workload, token hết hạn/thu hồi, ACL path thiếu capability, KV key bị xóa, lỗi mạng hoặc TLS. Không retry vô hạn bằng token cũ và không chuyển sang root token khi gặp 403.

## 9. So sánh với LifecycleAwareSessionManager

Đối với workload chạy dài, Spring Vault có `LifecycleAwareSessionManager` để quản lý token theo vòng đời. Khác biệt thực tế:

| Tiêu chí | `SimpleSessionManager` | `LifecycleAwareSessionManager` |
| --- | --- | --- |
| Lấy token qua `ClientAuthentication` | Có | Có |
| Tái sử dụng token trong phiên | Có | Có |
| Đồng bộ login giữa các luồng | Có | Có |
| Renew token đủ điều kiện theo lịch | **Không** | Có |
| Theo dõi TTL/renewability bằng lookup khi phù hợp | **Không** | Có |
| Bỏ token cũ và thử login lại khi renewal gặp lỗi báo token không hợp lệ | **Không** | Có |
| Revoke login token khi dispose | **Không** | Có, với **service token** phù hợp |
| Tham gia lifecycle bean và cần scheduler | Không có lịch quản lý | Có |
| Quản lý lease của secret động | Không | Không phải nhiệm vụ cốt lõi |

Tài liệu Spring Vault mô tả `LifecycleAwareSessionManager` lập lịch gia hạn cho token có khả năng renew, làm mới token khi cần và xử lý revoke khi dừng bean. Tuy nhiên **không có bảo đảm renewal vô hạn**: còn phụ thuộc max TTL, token type, policy và tình trạng auth method. Một số token (ví dụ batch token) có đặc điểm khác service token; không mặc định tất cả token sẽ được revoke khi shutdown.

**Mặc định phụ thuộc cách khởi tạo:**

- Khi tự dựng `new SimpleSessionManager(authentication)`, bạn chủ động chọn hành vi không renew/revoke.
- Khi dùng `new VaultTemplate(endpoint, authentication)`, template có thể dùng quản lý session đơn giản cho `ClientAuthentication` được cung cấp.
- Khi mở rộng `AbstractVaultConfiguration`, Spring Vault mặc định cấu hình **`LifecycleAwareSessionManager`**.
- Nếu dùng Spring Cloud Vault hoặc Vault Agent, cần xem lớp auto-configuration và cơ chế token được sử dụng trong **phiên bản dự án**; không áp đặt giả định một manager cho mọi kiểu tích hợp.

### Nên chọn khi nào?

`SimpleSessionManager` phù hợp với demo, unit test hoặc batch job ngắn hạn có token và cơ chế cleanup riêng. Một service Spring Boot chạy liên tục với token TTL ngắn thường cần chiến lược renew/re-authentication phù hợp hoặc giải pháp quản lý token riêng ngoài tiến trình.

**Không tăng TTL lên vô hạn, lưu root token trong mã hoặc bỏ ACL chỉ để tránh xử lý lifecycle.** Tốt hơn là cấp danh tính workload có đặc quyền tối thiểu, quản lý credential an toàn và xác minh hành vi khi token trở nên không hợp lệ.

## 10. Lỗi thường gặp và cách phân biệt

### “SimpleSessionManager có thể gọi lại login khi token hết hạn?”

Không có cơ chế refresh hoặc re-authentication tự động theo vòng đời. Nó tái sử dụng token đang lưu; gọi `getSessionToken()` nhiều lần không biến token hết hạn thành token mới.

### “Thay sang LifecycleAwareSessionManager sẽ sửa lỗi 403 do policy?”

Không. `403` có thể do token không hợp lệ **hoặc** token hợp lệ thiếu capability cho path. Gia hạn phiên không sửa ACL. Phải kiểm tra role, policies và đường dẫn API thực tế, ví dụ KV v2 có `data/`.

### “Một SessionManager có nên dùng riêng cho từng người dùng cuối?”

Trong mô hình ứng dụng Java truy cập Vault bằng **danh tính workload**, session manager đại diện cho ứng dụng. Vault policy của token này không tự phân quyền theo người dùng/tenant. API vẫn phải xác thực và phân quyền từng người dùng qua Spring Security hoặc lớp nghiệp vụ.

### “Có thể xem một token từ cache là bằng chứng Vault luôn online?”

Không. Manager lưu giá trị token, không đảm bảo server hoạt động, TLS hợp lệ, token còn hạn hoặc secret key tồn tại. Kiểm chứng phải dựa trên request thật và các trạng thái của Vault.

### “Token được renew thì dynamic secret cũng được renew?”

Không. Token TTL và lease TTL của dynamic database credential/PKI là hai vòng đời riêng. Cần dùng cơ chế lease management và chính sách renewal/revocation thích hợp của secrets engine.

### “Có nên log token để tìm lỗi?”

Không. Ghi mức thao tác, role/workload, Vault path đã được kiểm soát, status và correlation ID khi cần. Không ghi Vault token, AppRole secret ID, Kubernetes JWT, giá trị secret hoặc dữ liệu nhạy cảm từ response.

## 11. Ma trận kiểm thử khuyến nghị

| Trường hợp | Thiết lập | Kỳ vọng |
| --- | --- | --- |
| Login ban đầu | Mock `ClientAuthentication` có bộ đếm | Token được lấy một lần khi cần |
| Cache token | Hai lần `getSessionToken()` trên cùng manager | Cùng token, không login lại |
| Truy cập đồng thời | Nhiều luồng chia sẻ manager | Không nhân bản lần login khởi đầu do race |
| Token hết TTL | Vault dev, token ngắn hạn | Request sau TTL bị Vault từ chối |
| Token bị revoke | Operator revoke token đang được dùng | Lần đọc sau bị từ chối; Simple manager không tự hồi phục |
| Token hợp lệ thiếu ACL | Policy không cho `read` KV path | Vault trả 403 dù token chưa hết hạn |
| Secret bị xóa | Token có quyền nhưng key không tồn tại | Phân loại dữ liệu thiếu riêng với 403 |
| Service chạy dài | Token renewable, manager có lifecycle | Kiểm tra renew/re-login theo khả năng thực tế của token |
| Dynamic secret hết lease | Cấp credential với lease ngắn | Cơ chế lease riêng chịu trách nhiệm |

Đối với kiểm thử tích hợp, nên dùng Vault dev/test được cô lập hoặc Testcontainers, xác minh **hành vi thực tế**: mã lỗi, có/không có secret, không lộ giá trị nhạy cảm và không cấp quyền rộng hơn mong đợi.

## 12. Dọn môi trường lab và tự kiểm tra

Chỉ trên **Vault dev server** dùng riêng cho bài, root token có thể dọn dữ liệu thử nghiệm:

~~~bash
# Token hết hạn có thể không còn đối tượng để revoke.
vault token revoke "$APP_TOKEN"

# Xóa secret KV v2 và toàn bộ version của key thử nghiệm.
vault kv metadata delete -mount=secret apps/session-demo
vault policy delete session-demo-read
~~~

Lệnh `vault kv metadata delete` là thao tác xóa vĩnh viễn dữ liệu của key. Không thực hiện với secret thật hoặc mount chưa xác định chính xác.

Câu hỏi tự kiểm tra:

1. Có 100 lần đọc Vault qua cùng một `SimpleSessionManager`. Tại sao không cần gọi `ClientAuthentication.login()` 100 lần?
2. Token T1 hết hạn rồi, `getSessionToken()` có bảo đảm trả token T2 không?
3. `LifecycleAwareSessionManager` cải thiện những nhiệm vụ nào so với `SimpleSessionManager`?
4. Khi JWT workload/AppRole credential bị đổi, `SimpleSessionManager` có tự tạo session mới không?
5. Vì sao thời hạn của Vault token và lease của database credential phải theo dõi riêng?

**Gợi ý trả lời:** (1) cache token; (2) không; (3) renewal/revocation và lifecycle; (4) không; (5) token bảo vệ lời gọi Vault còn lease kiểm soát secret động được cấp.

### Tài liệu tham khảo

- [Spring Vault — VaultTemplate và Session Management](https://docs.spring.io/spring-vault/reference/vault/imperative-template.html).
- [SimpleSessionManager — Spring Vault API](https://docs.spring.io/spring-vault/reference/api/java/org/springframework/vault/authentication/SimpleSessionManager.html).
- [SessionManager — Spring Vault API](https://docs.spring.io/spring-vault/reference/api/java/org/springframework/vault/authentication/SessionManager.html).
- [LifecycleAwareSessionManager — Spring Vault API](https://docs.spring.io/spring-vault/reference/api/java/org/springframework/vault/authentication/LifecycleAwareSessionManager.html).
- [VaultTemplate — Spring Vault API](https://docs.spring.io/spring-vault/reference/api/java/org/springframework/vault/core/VaultTemplate.html).

`SimpleSessionManager` giúp ứng dụng Java **lấy và dùng lại Vault token trong một phiên đơn giản**. Mọi yêu cầu về gia hạn/thu hồi token, re-authentication và vòng đời secret lease phải được xử lý bởi những thành phần có trách nhiệm tương ứng.
