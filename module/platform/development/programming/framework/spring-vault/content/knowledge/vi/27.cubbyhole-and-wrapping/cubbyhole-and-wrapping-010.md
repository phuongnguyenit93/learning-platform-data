# Tách quyền tạo dữ liệu khỏi quyền nhận dữ liệu cuối cùng

## 1. Bài toán: hệ thống cấp dữ liệu và hệ thống sử dụng dữ liệu có quyền khác nhau

Giả sử một hệ thống triển khai Java/Spring cần cấp `SecretID` để một container mới đăng nhập HashiCorp Vault bằng AppRole. Pipeline CI/CD có quyền **tạo SecretID**; container runtime chỉ cần **nhận SecretID và dùng nó đăng nhập**. Nếu CI/CD đọc SecretID dưới dạng rõ rồi chuyển qua nhiều lớp orchestration, giá trị bí mật có thể xuất hiện trong log, biến môi trường, lịch sử lệnh, API response hoặc dữ liệu build.

Trong module **Spring Vault**, `VaultTemplate`/`VaultOperations` là cổng Java truy cập Vault; việc xác thực workload, chính sách Vault ACL, token/lease, KV, Transit encryption và PKI đều có thể tạo ra dữ liệu nhạy cảm. **Response wrapping** của Vault giải quyết một phần quan trọng của bài toán phân phối: bên tạo yêu cầu nhận **wrapping token có thời hạn ngắn**, còn bên nhận cuối cùng dùng token đó để lấy dữ liệu gốc **một lần**.

Ý tưởng phân quyền:

- **Producer / provisioning service:** được Vault ACL cho phép gọi endpoint tạo dữ liệu (ví dụ sinh AppRole SecretID) với response wrapping bắt buộc; chuyển wrapping token qua kênh được bảo vệ.
- **Transport / orchestrator:** chuyển wrapping token đến đúng workload; không cần đọc giá trị thực của SecretID.
- **Consumer / workload Java:** nhận token, kiểm tra nguồn gốc và hạn sử dụng, unwrap một lần, rồi sử dụng secret theo nghiệp vụ; không có quyền tạo SecretID cho chính nó.
- **Vault:** giữ dữ liệu wrapped trong cubbyhole gắn với wrapping token, kiểm soát TTL và từ chối sử dụng lại token đã tiêu thụ.

Cần hiểu chính xác: đây là **tách quyền truy cập Vault API và tách trách nhiệm xử lý**, đồng thời giảm việc lộ plaintext trên đường phân phối. Wrapping token vẫn là một **bearer credential**: ai sở hữu token chưa dùng và còn hạn đều có thể unwrap. Vì producer từng nhận wrapping token, giải pháp không bảo đảm bằng mật mã rằng producer *không có khả năng* đọc giá trị nếu cố tình unwrap. Để ngăn producer cố ý sử dụng token, phải bổ sung ranh giới tin cậy, giới hạn quyền, kênh giao hàng bảo mật, audit và cơ chế giám sát.

## 2. Cubbyhole khác response wrapping như thế nào?

`cubbyhole/` là secrets engine đặc biệt được Vault bật sẵn. Mỗi Vault token có **không gian cubbyhole riêng**; token A không đọc được dữ liệu trong cubbyhole của token B. Dữ liệu trong cubbyhole tồn tại gắn với **vòng đời của token**: khi token hết hạn/bị thu hồi, cubbyhole của nó bị hủy; mỗi giá trị cubbyhole không có TTL riêng như một secret dynamic lease.

**Response wrapping** là cơ chế của Vault dùng cubbyhole trong nền:

1. Client yêu cầu một API bình thường và yêu cầu wrapping, ví dụ header `X-Vault-Wrap-TTL: 90s`.
2. Vault xử lý API, tạo response gốc, lưu response này vào cubbyhole của một **wrapping token mới**.
3. Vault trả về `wrap_info` chứa token, TTL, thời điểm và `creation_path`; không trả data/auth secret gốc cho producer.
4. Bên nhận dùng wrapping token với `sys/wrapping/lookup` để kiểm tra thông tin trước khi mở, rồi dùng `sys/wrapping/unwrap` để lấy response gốc.
5. Unwrap thành công sẽ **tiêu thụ wrapping token**; gọi lần hai với token đó thất bại.

| Đặc điểm | Cubbyhole thông thường | Response wrapping |
| --- | --- | --- |
| Dữ liệu lưu ở đâu? | `cubbyhole/<path>` thuộc token đang dùng. | Response gốc nằm trong cubbyhole của wrapping token do Vault cấp. |
| Ai đọc được? | Token sở hữu cubbyhole và có quyền tương ứng. | Người có wrapping token hợp lệ, chưa unwrap. |
| Thời gian tồn tại | Theo vòng đời token sở hữu. | Theo TTL của wrapping token (độc lập với TTL của secret gốc). |
| Đọc bao nhiêu lần? | Đọc theo policy và vòng đời token. | **Unwrap một lần**; lookup metadata không tiêu thụ token. |
| Dùng vào việc gì? | Kho dữ liệu tạm gắn với danh tính token. | Chuyển giao response nhạy cảm giữa bên gọi API và bên tiêu thụ cuối. |
| API thường dùng | `cubbyhole/...` | `sys/wrapping/lookup`, `sys/wrapping/unwrap`, `sys/wrapping/rewrap`. |

**Đừng mô phỏng response wrapping bằng cách ghi secret vào cubbyhole của token CI/CD rồi đưa token CI/CD cho ứng dụng.** Làm như vậy sẽ chuyển cả quyền của CI/CD cho consumer và phá vỡ ranh giới phân quyền. Sử dụng **wrapping token chuyên dụng** do Vault tạo; token này không có quyền chung như token tạo dữ liệu.

## 3. Kiến trúc phân phối và ranh giới quyền

Ví dụ phân phối AppRole SecretID cho dịch vụ `orders-service`:

~~~mermaid
sequenceDiagram
    autonumber
    participant P as CI/CD (Producer)
    participant V as Vault
    participant O as Orchestrator
    participant C as Java workload (Consumer)
    P->>V: POST auth/approle/role/orders-service/secret-id + Wrap-TTL
    V->>V: Sinh SecretID; lưu response vào cubbyhole của wrapping token
    V-->>P: wrap_info: token, TTL, creation_path
    P->>O: Bàn giao wrapping token qua kênh được bảo vệ
    O->>C: Gửi wrapping token đến đúng workload
    C->>V: sys/wrapping/lookup
    V-->>C: creation_path, creation_time, TTL
    C->>C: Kiểm tra path, TTL và ngữ cảnh mong đợi
    C->>V: sys/wrapping/unwrap (một lần)
    V-->>C: SecretID gốc; token wrapped bị tiêu thụ
    C->>V: auth/approle/login với RoleID + SecretID
    V-->>C: Token runtime có policy tối thiểu
~~~

Ở đây `RoleID` và `SecretID` của AppRole là hai thông tin khác nhau: RoleID có thể phân phối qua một kênh cấu hình riêng; SecretID phải được bảo vệ và có thể có TTL, giới hạn số lần dùng. Nếu attacker có cả RoleID và SecretID, họ có thể thử đăng nhập, trừ khi có các ràng buộc khác như CIDR, TTL, usage count và chính sách xác thực phù hợp.

**Bảng phân quyền đề xuất:**

| Tác nhân | Có quyền | Không cần quyền |
| --- | --- | --- |
| Vault administrator / IaC | Quản lý AppRole, gắn policy và đặt ràng buộc wrapping. | Không tham gia nhận mọi SecretID trong luồng runtime. |
| CI/CD producer | Gọi `auth/approle/role/orders-service/secret-id` **với wrapping bắt buộc**. | Không cần token runtime của `orders-service` hoặc quyền đọc dữ liệu nghiệp vụ. |
| Orchestrator | Nhận và giao wrapping token, điều phối đúng instance. | Không cần quyền gọi API tạo SecretID. |
| Java consumer | Lookup/unwrap wrapping token đã giao, dùng SecretID để login theo AppRole. | Không cần quyền gọi endpoint tạo SecretID hoặc thay policy/role. |

Một thành phần trung gian vẫn có thể đánh cắp token mà nó nhìn thấy. Mục tiêu thiết kế là hạn chế dữ liệu rõ đi qua trung gian, giảm thời gian phơi lộ và **phát hiện** token bị dùng sớm; không được xem wrapping token như một giá trị công khai.

## 4. Thiết kế policy producer: buộc Vault trả response đã wrap

Trong môi trường test, đội vận hành cấu hình AppRole `orders-service` trước và gán token policy chỉ đủ cho workload (chẳng hạn đọc một số đường dẫn KV phù hợp). Producer có Vault token riêng, gắn ACL giới hạn đúng endpoint tạo SecretID.

Ví dụ policy của **producer**:

~~~hcl
# orders-secretid-producer.hcl
path "auth/approle/role/orders-service/secret-id" {
  capabilities = ["create", "update"]

  # Bắt buộc có response wrapping, không chấp nhận response plaintext.
  min_wrapping_ttl = "1s"

  # Hạn chế thời gian token có thể được giao đến consumer.
  max_wrapping_ttl = "120s"
}
~~~

`min_wrapping_ttl` lớn hơn 0 (ví dụ `1s`) khiến response wrapping trở thành điều kiện cho request trên path đó; `max_wrapping_ttl` đặt trần. Không đánh đồng TTL của wrapping token với `secret_id_ttl`, `secret_id_num_uses` hoặc TTL token phát sinh sau khi AppRole login.

Policy nên giới hạn chính xác tên role. Dùng wildcard như `auth/approle/role/+/secret-id` chỉ khi producer thực sự có nhiệm vụ tạo SecretID cho nhiều role và đã kiểm soát ranh giới ủy quyền. Bản thân người tạo token producer cũng phải được xác thực theo phương thức workload/CI phù hợp. Không nhúng Vault root token trong pipeline.

**Tách quyền là sự kết hợp của ACL và policy wrapping:** nếu producer có đường API khác trả cùng dữ liệu mà không bắt buộc wrapping, hoặc producer đồng thời sở hữu credential consumer, chính sách ở trên không đủ để đạt yêu cầu tách trách nhiệm.

## 5. Thực hành end-to-end bằng Vault CLI

Các lệnh này minh họa trên một **Vault development/test** đã có AppRole `orders-service`. Tổ chức quản trị tạo role, cấu hình policy và cung cấp RoleID bằng kênh riêng. Không chạy dòng lệnh với credential thật vào terminal có lưu lịch sử hoặc CI log.

### 5.1. Producer xin SecretID đã được wrap

~~~bash
# VAULT_TOKEN hiện tại là token của producer.
# -f gửi POST không cần dữ liệu body bổ sung.
vault write -wrap-ttl=90s -f \
  auth/approle/role/orders-service/secret-id
~~~

Kết quả hiển thị metadata tương tự (giá trị chỉ là minh họa, không phải token hợp lệ):

~~~text
Key                          Value
---                          -----
wrapping_token               <ONE_TIME_WRAPPING_TOKEN>
wrapping_accessor            <WRAPPING_ACCESSOR>
wrapping_token_ttl           1m30s
wrapping_token_creation_path auth/approle/role/orders-service/secret-id
~~~

Producer bàn giao **chỉ** `wrapping_token` qua kênh bảo vệ (ví dụ cơ chế secret injection có giới hạn quyền vào đúng pod/VM); không gửi SecretID gốc, không đặt token trong URL, query string, issue tracker hay artifact lâu dài. Token phải được xem như secret và không được ghi giá trị vào log.

### 5.2. Consumer xác minh và unwrap

Bên nhận có thể dùng Vault CLI trong môi trường test để minh họa:

~~~bash
# Thay giá trị dưới bằng token nhận qua kênh riêng.
WRAPPING_TOKEN="<ONE_TIME_WRAPPING_TOKEN>"

# Lookup chỉ xem metadata, không trả SecretID và không tiêu thụ token.
vault write sys/wrapping/lookup token="$WRAPPING_TOKEN"

# Sau khi đã kiểm tra creation_path và thời hạn:
vault unwrap "$WRAPPING_TOKEN"
~~~

Kết quả lookup cần có `creation_path` chính xác bằng `auth/approle/role/orders-service/secret-id`. Nếu dùng Vault namespace, cả producer và consumer phải làm việc trong namespace mà wrapping token được cấp; kiểm tra Vault address/TLS server identity và namespace đã cấu hình.

`vault unwrap` trong bài lab sẽ in SecretID rõ ra terminal, vì vậy **production nên unwrap trực tiếp trong memory của ứng dụng/agent**, không xuất dữ liệu ra stdout, file tạm, tracing hoặc metrics. Sau unwrap thành công, gọi lại `vault unwrap "$WRAPPING_TOKEN"` phải thất bại. Nếu bị lỗi vì token đã dùng hoặc hết TTL, không retry vô hạn với token cũ; yêu cầu producer cấp **wrapping token mới** sau khi điều tra.

> **Quy tắc HTTP cần nhớ:** Khi gọi `POST /v1/sys/wrapping/unwrap`, có thể dùng wrapping token làm header `X-Vault-Token` *hoặc* dùng token khác có quyền và truyền wrapping token trong body. Không truyền **cùng một wrapping token ở cả header lẫn body**, vì điều đó có thể khiến token bị tiêu thụ sai và mất response.

### 5.3. Consumer đăng nhập và lấy token runtime

Sau khi unwrap được SecretID, consumer đã có RoleID nhận từ kênh khác:

~~~bash
# Minh họa lab: các placeholder được nạp vào môi trường test an toàn.
vault write auth/approle/login \
  role_id="<ROLE_ID_FOR_ORDERS_SERVICE>" \
  secret_id="<UNWRAPPED_SECRET_ID>"
~~~

Token nhận từ AppRole login là **Vault client token runtime**, gắn policy nghiệp vụ của `orders-service`, khác với wrapping token dùng một lần và token producer. Spring Vault có thể quản lý token/runtime session và vòng đời renew theo cơ chế authentication/session manager thích hợp.

Trong ứng dụng thật, AppRole login nên được xử lý bằng cấu hình Spring Vault `AppRoleAuthentication` hoặc `CubbyholeAuthentication`/Vault Agent khi phù hợp; không hard-code RoleID/SecretID vào code. Nếu tự xử lý SecretID, hạn chế tối đa thời gian giữ biến nhạy cảm và bảo vệ heap dump, crash report, thông tin chẩn đoán.

## 6. Tích hợp Spring Vault qua VaultWrappingOperations

Spring Vault cung cấp `VaultWrappingOperations` thông qua:

~~~java
import org.springframework.vault.core.VaultOperations;
import org.springframework.vault.core.VaultWrappingOperations;

VaultWrappingOperations wrapping = vaultOperations.opsForWrapping();
~~~

Các phương thức chính:

| Spring Vault API | Ý nghĩa | Lưu ý |
| --- | --- | --- |
| `lookup(VaultToken)` | Đọc metadata wrapping token. | Không tiêu thụ token; có thể trả `null` nếu hết hạn/không tồn tại. |
| `read(VaultToken)` | Unwrap và trả `VaultResponse`. | Chỉ một lần; có thể trả `null` hoặc ném exception khi token không hợp lệ. |
| `read(VaultToken, Class<T>)` | Unwrap với kiểu dữ liệu đã khai báo. | Chọn kiểu phù hợp response gốc. |
| `rewrap(VaultToken)` | Đổi wrapping token mà không đọc plaintext. | Token cũ mất hiệu lực; creation TTL được tái sử dụng. |
| `wrap(Object, Duration)` | Wrap dữ liệu do caller gửi lên Vault. | Producer đã có dữ liệu rõ trước khi gọi; creation path là `sys/wrapping/wrap`. |

### 6.1. Java consumer: kiểm tra nguồn gốc trước khi unwrap

Ví dụ service dưới đây xử lý riêng thao tác **nhận SecretID đã được wrap trực tiếp từ endpoint AppRole**. Bean `VaultOperations` phải được cấu hình kết nối Vault an toàn trong đúng namespace; wiring của auth/session tuân theo cách Spring Vault đang dùng ở dự án.

~~~java
import java.util.Map;
import org.springframework.stereotype.Service;
import org.springframework.vault.authentication.VaultToken;
import org.springframework.vault.core.VaultOperations;
import org.springframework.vault.core.VaultWrappingOperations;
import org.springframework.vault.support.VaultResponse;
import org.springframework.vault.support.WrappedMetadata;

@Service
public class AppRoleSecretIdReceiver {

    private static final String EXPECTED_CREATION_PATH =
            "auth/approle/role/orders-service/secret-id";

    private final VaultWrappingOperations wrapping;

    public AppRoleSecretIdReceiver(VaultOperations vaultOperations) {
        this.wrapping = vaultOperations.opsForWrapping();
    }

    /** Chỉ gọi một lần cho mỗi wrapping token nhận qua kênh an toàn. */
    public String receiveSecretId(String deliveredWrappingToken) {
        VaultToken token = VaultToken.of(deliveredWrappingToken);

        WrappedMetadata metadata = wrapping.lookup(token);

        if (metadata == null
                || !EXPECTED_CREATION_PATH.equals(metadata.getPath())) {
            // Không log token/SecretID. Cần báo cảnh báo bảo mật riêng.
            throw new IllegalStateException(
                    "Wrapping token không hợp lệ hoặc sai nguồn");
        }

        VaultResponse response = wrapping.read(token);
        Map<String, Object> data =
                response == null ? null : response.getData();

        if (data == null || !(data.get("secret_id") instanceof String id)
                || id.isBlank()) {
            throw new IllegalStateException(
                    "Không thể nhận SecretID từ wrapped response");
        }

        return id; // Chuyển ngay đến bước AppRole login; không log.
    }
}
~~~

Ở mã sản xuất, nên thêm kiểm tra metadata về `creationTime`, TTL và deadline vận hành; xác thực Vault TLS endpoint/namespace; xử lý exception phân loại được nhưng không làm lộ token. `lookup` rồi `read` không phải một giao dịch nguyên tử: token có thể hết hạn hoặc bị bên khác tiêu thụ giữa hai bước. Khi `read` thất bại sau `lookup` thành công, phải coi là bất thường cần điều tra, không âm thầm fallback sang token producer hay nguồn dữ liệu rõ.

Các thao tác `VaultWrappingOperations` có từ Spring Vault 2.1; ví dụ trên giả định đã khai báo phụ thuộc phiên bản Spring Vault tương thích. Tránh lưu `deliveredWrappingToken` trong field của singleton service hoặc vô tình xuất nó bằng `toString()`.

### 6.2. Producer Java: wrap ngay tại endpoint gốc

Tùy phiên bản và cách cấu hình HTTP client, request có thể gửi `X-Vault-Wrap-TTL` khi gọi endpoint gốc. Với Spring Vault 4.1+, `VaultClient` cung cấp `ResponseSpec.wrap(Duration)`; ví dụ minh họa (client phải có Vault endpoint/TLS và token producer đã cấu hình):

~~~java
import java.time.Duration;
import java.util.Map;
import org.springframework.vault.client.VaultClient;
import org.springframework.vault.support.WrappedMetadata;

// vaultClient đã cấu hình để sử dụng Vault endpoint an toàn.
// producerToken có policy tạo SecretID với min/max wrapping TTL.
WrappedMetadata wrapped = vaultClient.post()
        .path("auth/approle/role/orders-service/secret-id")
        .token(producerToken)
        .body(Map.of())
        .retrieve()
        .wrap(Duration.ofSeconds(90));

// Chỉ chuyển wrapped.getToken() qua kênh giao hàng an toàn.
// Không serialize cả wrapped metadata vào log.
~~~

Lợi ích của việc wrap **ở request gốc** là producer không nhận response chứa SecretID rõ, và metadata `creation_path` phản ánh chính xác endpoint cấp SecretID. Nếu sử dụng `VaultWrappingOperations.wrap(body, ttl)` để gửi một map mà producer đã có, đây là **wrapped arbitrary data** với `creation_path=sys/wrapping/wrap`. Nó hữu ích khi cần bao gói dữ liệu tùy ý, nhưng **không chứng minh** data được Vault tạo từ endpoint nghiệp vụ dự kiến; consumer không nên chấp nhận nó như bằng chứng nguồn gốc SecretID.

### 6.3. Đừng nhầm CubbyholeAuthentication với response wrapping API

Spring Vault còn có `CubbyholeAuthentication` phục vụ luồng bootstrap, lấy wrapped token/secret khi xác thực và phối hợp với `AuthenticationSteps`. Lớp này giải quyết **luồng đăng nhập của ứng dụng**. `VaultWrappingOperations` là API cho **lookup/unwrap/rewrap/wrap**. Hai phần có thể được phối hợp, nhưng không phải class nào tên “cubbyhole” cũng là cách đọc trực tiếp `cubbyhole/...` của token runtime.

Khi đã có hệ thống tự động hóa đăng nhập (Spring Cloud Vault, Vault Agent), nên dùng cấu hình auth chuẩn thay vì tái hiện toàn bộ logic cấp và nhận SecretID trong controller hoặc startup listener riêng.

## 7. Xác thực wrapping token: không chỉ kiểm tra token còn hạn

Quy trình bảo vệ phía consumer nên thực hiện đúng thứ tự:

1. **Xác định kỳ vọng trước khi nhận:** path chính xác, namespace, môi trường Vault, workload đích, thời hạn tối đa và khoảng thời gian có thể giao hàng.
2. **Nhận token qua kênh riêng:** gắn đúng instance workload, dùng TLS, cơ chế giao bí mật của nền tảng và tránh log/đường dẫn URL.
3. **Lookup trước khi unwrap:** gọi `sys/wrapping/lookup`, xác minh token chưa bị dùng/hết hạn và `creation_path` đúng API dự kiến.
4. **Unwrap một lần:** gọi `sys/wrapping/unwrap`, chỉ xử lý payload có schema và identity mong đợi.
5. **Dùng và dọn dữ liệu:** dùng SecretID để login, không lưu lâu; theo dõi sự kiện thành công/thất bại mà không ghi giá trị bí mật.
6. **Điều tra khi token sai:** token hết hạn, bị revoke hay bị kẻ khác unwrap trước đều có thể gây lỗi. Kết hợp audit log và thông tin kênh bàn giao để xác định nguyên nhân.

Đối với AppRole mẫu, `creation_path` dự kiến phải là:

~~~text
auth/approle/role/orders-service/secret-id
~~~

Không chỉ kiểm tra path bắt đầu bằng `auth/approle/role/` vì token có thể đến từ role khác. Nếu expected secret nằm trong KV, kiểm tra chính xác path và phiên bản API tương ứng (KV v1/v2 khác đường dẫn). Nếu bất ngờ thấy `sys/wrapping/wrap` hoặc `cubbyhole/...` khi mong chờ endpoint AppRole, coi đó là lỗi nguồn gốc; người trung gian có thể đã tạo response wrapped khác sau khi đọc dữ liệu trước đó.

`creation_path` giúp kiểm tra nguồn yêu cầu ban đầu trên **đúng Vault server đáng tin**, nhưng nó không xác thực danh tính người nhận cuối và không phải chữ ký số trên payload. Kết hợp TLS xác thực Vault, namespace đúng, cơ chế delivery có quyền hạn, audit và kiểm soát một lần dùng.

### 7.1. Những TTL cần phân biệt

| TTL / giới hạn | Phát sinh ở đâu? | Ý nghĩa |
| --- | --- | --- |
| Wrapping token TTL | `-wrap-ttl=90s`, header hoặc `wrap(Duration)` | Thời gian cho phép consumer unwrap. |
| Min/max wrapping TTL | Policy của producer | Ép wrap và giới hạn thời gian giao token. |
| AppRole SecretID TTL | Cấu hình AppRole như `secret_id_ttl` | Thời hạn SecretID để đăng nhập sau unwrap. |
| SecretID number of uses | `secret_id_num_uses` | Số lần SecretID có thể được dùng để đăng nhập. |
| Runtime Vault token TTL | Token trả về từ `auth/approle/login` | Thời gian workload có quyền gọi API Vault với policy runtime. |

TTL wrapping không “gia hạn” TTL SecretID. Khi wrapping token hết hạn, bên nhận không thể lấy response nữa, dù SecretID bên trong về nguyên tắc chưa hết thời hạn. Khi đã unwrap thành công, không thể tái sử dụng wrapping token; SecretID nhận được có lifecycle riêng.

### 7.2. Rewrap có phải unwrap không?

`sys/wrapping/rewrap` tạo một wrapping token mới chứa **cùng response**, không trả dữ liệu rõ cho caller. Token cũ mất hiệu lực và token mới có creation TTL tương ứng để giao lại. Chỉ dùng rewrap khi có lý do vận hành rõ, ví dụ đổi token trong hệ thống bàn giao mà không được xem secret. Nếu đang dựa vào `creation_path` để xác minh nguồn gốc, kiểm tra đặc tính nguồn gốc trong hệ thống/version đang dùng trước khi chấp nhận token đã rewrap; không mặc định nó giữ nguyên cách kiểm chứng của wrapped response tạo trực tiếp tại API gốc.

Rewrap cũng không gia hạn TTL của chính SecretID/token được chứa bên trong. Một hệ thống có yêu cầu rotation phải quản lý vòng đời secret gốc song song.

## 8. Các lỗi thiết kế phổ biến

| Hiện tượng / cách làm sai | Vấn đề | Cách thiết kế lại |
| --- | --- | --- |
| Producer gọi API không wrap rồi tự gửi plaintext. | Dữ liệu rõ đi qua producer, CI log hoặc orchestrator. | Ép `min_wrapping_ttl`, request gốc có wrap TTL và kiểm tra response chỉ có wrap info. |
| Gửi token producer cho consumer để đọc cubbyhole. | Consumer nhận luôn quyền của producer. | Dùng wrapping token chuyên dụng, không chia sẻ token có policy tạo secret. |
| Producer có cả quyền tạo SecretID và quyền đăng nhập như consumer. | Tách trách nhiệm không có tác dụng. | Thiết kế auth role, ACL, kênh cấp RoleID/SecretID riêng và role workload tối thiểu. |
| Wrapping token đưa vào URL hoặc log. | Đây là bearer credential, có thể bị dùng sớm. | Kênh giao hàng bảo vệ, chỉ trao đúng workload, che token trong log/trace. |
| Không lookup `creation_path` trước unwrap. | Không biết token được tạo từ API nào. | So khớp path chính xác với endpoint đã định. |
| Dùng `sys/wrapping/wrap` cho SecretID nhưng tin là do endpoint AppRole sinh. | Người gửi có thể bọc dữ liệu tùy ý. | Wrap trực tiếp endpoint SecretID, xác minh creation path. |
| TTL wrapping quá dài. | Tăng thời gian token có thể bị đánh cắp. | Chọn TTL ngắn nhưng thực tế đủ qua thời gian provisioning và startup. |
| TTL wrapping quá ngắn. | Pod khởi động chậm, token hết hạn trước khi unwrap. | Đo thời gian thực, đặt timeout/retry điều phối và cấp token mới có kiểm soát. |
| Retry unwrap cùng token sau lỗi không phân loại. | Unwrap single-use; response có thể đã bị tiêu thụ. | Ghi nhận thất bại, kiểm audit, cấp wrapped response mới khi phù hợp. |
| Dùng Vault auth token TTL thay cho wrapping TTL. | Nhầm thời hạn của phiên đăng nhập và thời gian bảo vệ dữ liệu bàn giao. | Theo dõi 3 vòng đời: wrapping token, SecretID, runtime token. |

Một lỗi quan trọng khác là **cho API hoặc middleware tự động log HTTP response body/header**. Khi bật debug wire logging, cả `wrap_info.token` lẫn `secret_id` sau unwrap đều cần được che. Kiểm tra cấu hình APM, tracing và exception handler trước khi triển khai.

## 9. Giám sát, audit và xử lý sự cố

Vault audit log giúp điều tra khi token bị tiêu thụ ngoài dự kiến, nhưng cần kiểm tra cách audit device và công cụ log ghi token/accessor; không sao chép dữ liệu nhạy cảm ra hệ thống quan sát không được bảo vệ.

Nên đo:

- Số lượng wrapped response được tạo và gửi thành công cho consumer, theo môi trường và loại endpoint (không dùng token làm metric label).
- Thời gian từ lúc tạo wrapping token đến lúc workload unwrap; tỷ lệ token hết hạn trước khi dùng.
- Số lần lookup/unwrap thất bại, sai `creation_path`, schema payload bất thường hoặc token đã dùng trước.
- Tỷ lệ AppRole login thành công sau unwrap, TTL SecretID và runtime token, sai lệch đồng hồ và lỗi Vault/network.
- Các sự kiện revoke/rotation để phát hiện giao nhầm token hoặc cấp sai role.

Tình huống xử lý tiêu biểu:

**Case A — lookup báo token invalid:** token có thể đã hết TTL, bị revoke hoặc đã unwrap bởi bên khác. Dừng quy trình bootstrapping, đối chiếu audit và thời điểm delivery. Không tự động xem đây là chắc chắn bị tấn công, nhưng cần xử lý như tín hiệu bất thường.

**Case B — lookup hợp lệ, unwrap thất bại:** có thể có cuộc đua giữa hai consumer hoặc hết hạn giữa hai request. Bảo đảm chỉ một workload được giao token; không retry vô hạn và không ghi token vào log. Cấp token khác chỉ sau khi xác nhận trạng thái cấp dữ liệu có thể lặp lại an toàn.

**Case C — creation path khác kỳ vọng:** từ chối ngay cả khi token vẫn hợp lệ; kiểm lại Vault endpoint, namespace, API gốc, middleware và pipeline cấp dữ liệu. Không dùng plaintext từ payload sai nguồn.

**Case D — unwrap thành công nhưng AppRole login thất bại:** wrapping đã hoàn thành; kiểm tra RoleID/SecretID đúng role, SecretID TTL/uses, CIDR policy và Vault auth path. Không coi token wrapping là token runtime; xin SecretID mới theo quy trình nếu secret đã không còn dùng được.

## 10. Kiểm thử tích hợp có ý nghĩa

Kiểm thử luồng thật trên Vault test, dùng token producer và consumer có quyền riêng. Chỉ mock client thì không phát hiện được chính sách bắt buộc wrapping, hành vi token một lần hay phân quyền Vault.

1. **Policy bắt buộc wrap:** producer gọi endpoint tạo SecretID *không có* wrap TTL phải bị Vault từ chối; gọi với `90s` được `wrap_info` và không chứa SecretID plaintext.
2. **Kiểm tra role và path:** lookup phải trả `creation_path=auth/approle/role/orders-service/secret-id`; token từ role khác hoặc từ `sys/wrapping/wrap` phải bị consumer từ chối.
3. **Cách ly quyền:** producer không có policy đọc KV nghiệp vụ của `orders-service`; consumer chưa login không thể gọi endpoint tạo SecretID.
4. **Single-use:** sau một unwrap thành công, lookup/unwrap lại token cũ phải không thành công.
5. **Hết hạn:** tạo token TTL ngắn trong test có kiểm soát, đợi hết hạn và kiểm tra consumer báo lỗi an toàn; không dùng test phụ thuộc thời gian ngẫu nhiên.
6. **Delivery đúng workload:** cùng token không được cấp đồng thời cho hai pod/instance; khi một consumer nhận thành công, lần còn lại không nhận được plaintext.
7. **Đăng nhập runtime:** RoleID và SecretID được unwrap có thể tạo token AppRole giới hạn đúng policy; token đó không có quyền admin hay tạo SecretID.
8. **Kiểm tra logging:** các giá trị wrapping token, SecretID, runtime token không xuất hiện trong log pipeline, log Spring, trace, crash report hoặc test report.

Ví dụ pseudo-assertion ở consumer:

~~~java
VaultToken wrappedToken = VaultToken.of(deliveredToken);

WrappedMetadata meta = wrapping.lookup(wrappedToken);
assertNotNull(meta);
assertEquals(
        "auth/approle/role/orders-service/secret-id",
        meta.getPath());

VaultResponse once = wrapping.read(wrappedToken);
assertNotNull(once);
assertNotNull(once.getData().get("secret_id"));

// Token đã tiêu thụ: không được nhận dữ liệu rõ lần hai.
VaultResponse twice = wrapping.read(wrappedToken);
assertNull(twice);
~~~

Với phiên bản API/thiết lập Vault trả exception thay vì `null` khi unwrap lần hai, test cần chấp nhận **lỗi token không hợp lệ** đúng loại; tiêu chí là không nhận lại dữ liệu. Không dùng mock để tự chứng minh tính single-use.

## 11. Khi nào dùng và khi nào không nên dùng response wrapping?

**Phù hợp:** Bootstrapping AppRole SecretID cho VM/pod, chuyển credential động giữa các hệ thống provisioning và runtime, cấp tài liệu/khóa nhạy cảm từ Vault sang đúng consumer theo một lượt nhận, tránh làm lộ response qua các tầng trung gian.

**Không thay thế:** Workload authentication mạnh; Vault ACL/RBAC; TLS; kiểm tra CA/tên server; khóa mã hóa Transit; vòng đời KV/dynamic secrets; quản trị token/lease; bảo vệ nguồn dữ liệu và bản thân consumer sau unwrap.

Nếu workload có thể **tự xác thực trực tiếp** đến Vault bằng Kubernetes/AWS/IAM/workload identity mà không phải giao một SecretID từ CI/CD, cách đó thường loại bỏ nhu cầu chuyển SecretID lúc bootstrap. Khi vẫn cần chuyển dữ liệu nhạy cảm qua trung gian, response wrapping là cơ chế hữu ích để giảm số bên tiếp xúc plaintext và cung cấp khả năng phát hiện token bị dùng trước.

## 12. Câu hỏi tự đánh giá

1. Producer được quyền tạo SecretID vì sao không cần biết plaintext SecretID ở thời điểm giao hàng?
2. Vì sao không thể giao cho consumer token Vault của producer để đọc cubbyhole thông thường?
3. `min_wrapping_ttl` và `max_wrapping_ttl` giúp tách quyền ra sao? TTL wrapping có làm SecretID lâu sống hơn không?
4. Vì sao wrapping token vẫn phải được bảo vệ như một credential dù không trực tiếp chứa plaintext?
5. Nếu `creation_path=sys/wrapping/wrap` nhưng ứng dụng mong đợi `auth/approle/role/orders-service/secret-id`, phải xử lý thế nào?
6. Vì sao `lookup` phải thực hiện trước `unwrap` và vì sao lookup thành công vẫn không đảm bảo unwrap sẽ thành công?
7. Khi unwrap thất bại lần hai, điều đó chứng minh và *không* chứng minh điều gì?
8. Trong Spring Vault, `opsForWrapping()` khác `CubbyholeAuthentication` ở trách nhiệm nào?
9. Với nhiều replica, làm thế nào bảo đảm mỗi wrapping token chỉ được giao cho đúng một nơi nhận?
10. Có trường hợp nào ứng dụng dùng Kubernetes authentication trực tiếp đơn giản hơn AppRole SecretID wrapping không?

## Tài liệu tham khảo

- [HashiCorp Vault — Response Wrapping](https://developer.hashicorp.com/vault/docs/concepts/response-wrapping)
- [HashiCorp Vault — Cubbyhole secrets engine](https://developer.hashicorp.com/vault/docs/secrets/cubbyhole)
- [HashiCorp Vault — Policies và min/max wrapping TTL](https://developer.hashicorp.com/vault/docs/concepts/policies)
- [HashiCorp Vault — AppRole best practices, response wrapping](https://developer.hashicorp.com/vault/docs/auth/approle/approle-pattern)
- [HashiCorp Vault — AppRole tutorial: response wrap SecretID](https://developer.hashicorp.com/vault/tutorials/auth-methods/approle)
- [HashiCorp Vault — Wrapping lookup API](https://developer.hashicorp.com/vault/api-docs/system/wrapping-lookup)
- [HashiCorp Vault — Wrapping unwrap API](https://developer.hashicorp.com/vault/api-docs/system/wrapping-unwrap)
- [HashiCorp Vault — Wrapping rewrap API](https://developer.hashicorp.com/vault/api-docs/system/wrapping-rewrap)
- [Spring Vault — VaultWrappingOperations API](https://docs.spring.io/spring-vault/reference/api/java/org/springframework/vault/core/VaultWrappingOperations.html)
- [Spring Vault — VaultOperations API](https://docs.spring.io/spring-vault/reference/api/java/org/springframework/vault/core/VaultOperations.html)
- [Spring Vault — VaultClient usage (Spring Vault 4.1+)](https://docs.spring.io/spring-vault/reference/vault/vault-client.html)
