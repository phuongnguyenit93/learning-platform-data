# Namespace header và phạm vi áp dụng cho yêu cầu

## 1. Namespace giúp giải quyết vấn đề gì?

Ứng dụng Java dùng **Spring Vault** có thể truy cập HashiCorp Vault qua `VaultTemplate` để đăng nhập theo workload, đọc KV secrets, dùng Transit encryption, cấp chứng chỉ PKI hoặc quản lý token và lease. Trong hệ thống có nhiều nhóm, dự án hoặc môi trường, cùng một cụm Vault có thể cần những không gian độc lập cho cấu hình và bí mật của từng nhóm.

**Vault namespace** là khả năng phân tách tenant của **Vault Enterprise** và các dịch vụ Vault được quản lý có hỗ trợ namespace (chẳng hạn HCP Vault Dedicated). Mỗi namespace có thể có secrets engines, auth methods, policy, token và identity riêng. Đây là **không gian logic bên trong Vault**, không phải một HTTP host hay một thư mục trên máy chạy Java.

Ví dụ hệ thống có hai namespace:

```text
Vault cluster: https://vault.example.internal:8200
└── root namespace
    └── engineering/
        ├── payments/
        │   ├── auth/kubernetes/
        │   └── secret/             (KV v2 mount)
        └── catalog/
            ├── auth/kubernetes/
            └── secret/             (KV v2 mount)
```

Cả hai ứng dụng có thể gọi **cùng host và cùng đường dẫn tương đối** `secret/data/app/config`, nhưng kết quả phụ thuộc **namespace đích của request**. Secret trong `engineering/payments` không tự động trở thành secret của `engineering/catalog`.

> **Phạm vi tính năng:** Namespace theo nghĩa này không phải tính năng phổ thông của Vault Community. Nếu đang dùng Community edition, đừng thêm `X-Vault-Namespace` rồi kỳ vọng Vault tạo một namespace mới hoặc cô lập tenant; cần kiểm tra edition và cách triển khai trước.

## 2. `X-Vault-Namespace` là gì?

Vault HTTP API cho phép chỉ định namespace đích bằng HTTP request header:

```http
GET /v1/secret/data/app/config HTTP/1.1
Host: vault.example.internal:8200
X-Vault-Namespace: engineering/payments
X-Vault-Token: <token-hợp-lệ>
```

Đây là ví dụ biểu diễn HTTP để hiểu cấu trúc, **không phải** lời khuyên đưa token thật vào tài liệu. Header `X-Vault-Namespace` chọn **phạm vi định tuyến** của lời gọi; header `X-Vault-Token` cung cấp **credential** để Vault xét quyền.

| Thành phần request | Ví dụ | Trả lời câu hỏi nào? |
| --- | --- | --- |
| Scheme, host, port | `https://vault.example.internal:8200` | Java kết nối đến điểm mạng nào và xác minh TLS với host nào? |
| Namespace header | `X-Vault-Namespace: engineering/payments` | Lời gọi được diễn giải trong không gian logic nào của Vault? |
| API path | `/v1/secret/data/app/config` | Muốn thực hiện hành động nào, tại mount/path nào trong namespace đó? |
| Token header | `X-Vault-Token: ...` | Workload có credential nào để Vault kiểm tra policy? |

**Không** dùng `X-Vault-Namespace` thay cho token hoặc policy. Header chỉ thay đổi **ngữ cảnh xử lý request**, không chứng minh danh tính workload và không tự cấp quyền đọc secret.

### 2.1. Header có tác dụng trên từng HTTP request

Mỗi request có header và đường dẫn riêng. Vault **không nhớ namespace của request trước** để ngầm áp dụng cho request kế tiếp chỉ vì hai request dùng cùng TCP/TLS connection.

```text
HTTP connection được dùng lại
  ├── GET /v1/secret/data/app/config
  │     X-Vault-Namespace: engineering/payments
  │     └── xử lý tại namespace payments
  │
  └── GET /v1/secret/data/app/config
        X-Vault-Namespace: engineering/catalog
        └── xử lý tại namespace catalog
```

Nếu HTTP client cấu hình **default namespace**, client sẽ thêm header này vào những request thuộc phạm vi cấu hình; đó là hành vi của **client**, không phải trạng thái “đăng nhập vào namespace” được lưu trên kết nối mạng.

## 3. Namespace header kết hợp với API path như thế nào?

Vault có thể xác định namespace từ **header**, từ **phần đầu của API path**, hoặc kết hợp cả hai theo quy tắc định tuyến namespace.

Giả sử trong namespace `engineering/payments` có KV v2 mount tên `secret` và key `app/config`. Những cách biểu diễn dưới đây đều hướng đến cùng phạm vi logic khi request được phép:

| Namespace header | Path sau `/v1/` | Cách hiểu |
| --- | --- | --- |
| `engineering/payments/` | `secret/data/app/config` | Header chỉ định đủ namespace; path là tương đối trong đó. |
| `engineering/` | `payments/secret/data/app/config` | Header định vị namespace cha; path đi tiếp vào namespace con. |
| Không gửi | `engineering/payments/secret/data/app/config` | Path chứa tiền tố namespace đầy đủ. |

Trong ứng dụng Spring Vault, **cách dễ đọc và ít nhầm nhất** là đặt namespace đầy đủ bằng header, sau đó dùng path tương đối `secret/data/app/config` hoặc API operations phù hợp. Dùng cả header đầy đủ **và** lặp tiền tố `engineering/payments` trong path có thể làm lời gọi nhắm sai đường dẫn.

```text
Đúng, nhất quán:
  header: engineering/payments
  path:   secret/data/app/config

Sai ý đồ, dễ bị nhân đôi:
  header: engineering/payments
  path:   engineering/payments/secret/data/app/config
```

**Phân biệt ba loại “đường dẫn”:**

- `engineering/payments`: **namespace path**, chọn không gian tenant.
- `secret`: **secrets engine mount** trong namespace.
- `data/app/config`: **API path của KV v2** và key tương ứng; với KV v1 không có thành phần `data/` theo cách này.

Ngoài ra, `/v1` là **tiền tố phiên bản Vault HTTP API**, không phải namespace. Đừng đặt `/v1` vào giá trị `X-Vault-Namespace`.

### 3.1. Root namespace và đường dẫn tương đối

Vault có **root namespace** làm không gian gốc. Với endpoint Vault thông thường không dùng listener chroot, request **không chỉ định namespace** được xử lý theo ngữ cảnh định tuyến mặc định từ root. **Không** giả định chuỗi `root` là một namespace con hợp lệ để tự động gửi qua header.

Một số triển khai Enterprise có **chroot namespace trên listener** hoặc mô hình dịch vụ được quản lý có namespace gốc hiển thị cho tenant (ví dụ `admin` trong một số môi trường HCP). Khi đó đường dẫn namespace mà client nhìn thấy có thể được diễn giải từ một root logic khác. Cần xác nhận hợp đồng endpoint/namespace của cụm trước khi sao chép ví dụ dành cho Vault Enterprise self-managed.

## 4. Namespace ảnh hưởng tới những lời gọi nào?

Vì `X-Vault-Namespace` thuộc **từng HTTP request**, cần xét toàn bộ đường gọi mà Spring Vault tạo, không chỉ lệnh đọc KV.

| Nhóm lời gọi | Đường dẫn ví dụ, tương đối với namespace | Điểm cần chú ý |
| --- | --- | --- |
| Đăng nhập Kubernetes auth | `POST /v1/auth/kubernetes/login` | Auth mount `kubernetes` phải tồn tại trong namespace đích hoặc được định tuyến hợp lệ. |
| Đăng nhập AppRole | `POST /v1/auth/approle/login` | Role và mount path được xét trong ngữ cảnh namespace tương ứng. |
| Đọc KV v2 | `GET /v1/secret/data/app/config` | Mount `secret` và key thuộc namespace được chọn. |
| Transit encrypt | `POST /v1/transit/encrypt/app-key` | Transit mount và key có phạm vi theo namespace. |
| PKI issue | `POST /v1/pki/issue/app-role` | PKI mount và role phải tồn tại, token phải có capability phù hợp. |
| Token lookup/renew | `/v1/auth/token/lookup-self`, `/v1/auth/token/renew-self` | Cần giữ nhất quán token, namespace và HTTP client dùng cho session lifecycle. |
| Quản lý lease | `/v1/sys/leases/renew`, `/v1/sys/leases/revoke` | Lease ID, quyền thao tác và namespace phải tương thích. |
| Hệ thống/quản trị | Một số `/v1/sys/...` | Có API bị hạn chế theo root/admin namespace hoặc đòi capability riêng; không phải mọi sys API đều dùng được từ mọi namespace. |

### 4.1. Header phải có ngay khi login

Đây là lỗi tích hợp điển hình:

```text
1. Login thiếu namespace:
   POST /v1/auth/kubernetes/login
   X-Vault-Namespace: [không có]
   → tìm auth mount ở ngữ cảnh khác

2. Đọc KV có namespace:
   GET /v1/secret/data/app/config
   X-Vault-Namespace: engineering/payments
   → không tự khắc phục được login sai ở bước 1
```

Vì vậy, đừng chỉ thêm namespace header vào `VaultTemplate.read(...)` ở tầng nghiệp vụ rồi bỏ quên **HTTP client dùng để xác thực và quản lý session**. Với Spring Cloud Vault, dùng cấu hình namespace được hỗ trợ để các request thuộc phần tích hợp được gắn header nhất quán.

### 4.2. Policy và token vẫn có phạm vi

Trong mỗi namespace, quyền dựa trên **policy gắn với token**. Ví dụ trong namespace `engineering/payments`, một policy cho phép đọc KV v2 có thể có đoạn:

```hcl
path "secret/data/app/config" {
  capabilities = ["read"]
}
```

Đây là **path tương đối trong ngữ cảnh policy/namespace được quản trị đúng**; không mặc định thêm `engineering/payments/` vào mọi policy khi đã tạo policy bên trong namespace đó.

Một token không trở thành token “toàn quyền ở namespace khác” chỉ vì client đổi `X-Vault-Namespace`. Vault có quy tắc về token, quyền của namespace cha/con và các cơ chế truy cập xuyên namespace được cấu hình cụ thể. **Không giả định** mọi token đều có thể dùng qua lại giữa các namespace; cũng không khẳng định namespace tự nó thay thế mọi kiểm tra policy.

## 5. Thực hành trực tiếp với Vault HTTP API

Giả sử người quản trị đã tạo namespace `engineering/payments`, bật KV v2 ở mount `secret` và cấp một token có **quyền read** đối với `secret/data/app/config` trong phạm vi phù hợp.

Trước tiên, thiết lập endpoint và CA cho môi trường thử nghiệm:

```bash
export VAULT_ADDR="https://vault.example.internal:8200"
export VAULT_CACERT="/etc/vault/tls/vault-ca.pem"
export VAULT_NAMESPACE="engineering/payments"
```

`VAULT_NAMESPACE` là cách Vault CLI biết namespace mặc định. **Nó không tự cấu hình header cho mọi HTTP client Java**; đối với Spring Cloud Vault phải dùng `spring.cloud.vault.namespace`, hoặc cấu hình namespace tại transport/API client được Spring Vault hỗ trợ.

### 5.1. Gọi bằng curl với namespace header

```bash
curl --fail-with-body --silent --show-error \
  --cacert "$VAULT_CACERT" \
  --header "X-Vault-Namespace: $VAULT_NAMESPACE" \
  --header "X-Vault-Token: $VAULT_TOKEN" \
  "$VAULT_ADDR/v1/secret/data/app/config"
```

Ví dụ yêu cầu biến `VAULT_TOKEN` đã được cấp an toàn từ trước; **không đặt token thật vào shell history, file bài học hoặc mã nguồn**. `curl --fail-with-body` hoạt động trên các phiên bản curl đủ mới; nếu không hỗ trợ, dùng `--include` để quan sát HTTP status thay thế.

Nếu endpoint trả HTTP `200`, chứng tỏ token và policy có thể truy cập đúng resource trong namespace đã chọn. Nếu `403` hoặc `404`, cần kiểm tra cả namespace, token, mount path và KV version chứ không kết luận ngay là mạng lỗi.

### 5.2. Đọc bằng Vault CLI

```bash
# VAULT_ADDR, VAULT_CACERT, VAULT_NAMESPACE đã được thiết lập
vault kv get -mount=secret app/config
```

CLI có thể tự đưa namespace vào request từ `VAULT_NAMESPACE`. Muốn kiểm tra rõ ràng bằng tùy chọn, dùng `-namespace` theo cú pháp của phiên bản Vault CLI đang sử dụng. Quan trọng là **CLI và ứng dụng Java là hai HTTP client khác nhau**: CLI thành công chưa chứng minh `VaultTemplate` đã gửi header cùng giá trị.

### 5.3. Thử hai namespace để quan sát hiệu quả

Trong môi trường thử nghiệm có đủ quyền, chạy cùng thao tác đọc `secret/data/app/config` dưới `engineering/payments` và `engineering/catalog` với **credentials phù hợp cho từng namespace**. Dù API path giống nhau, giá trị secret và quyền truy cập có thể khác nhau; đó chính là tác dụng của phân tách namespace.

Không dùng một token quyền quản trị toàn cụm làm bằng chứng rằng namespace không cô lập: token quyền rộng có thể vượt ra ngoài ranh giới mà token workload thực tế bị hạn chế.

## 6. Spring Cloud Vault: một namespace nhất quán cho ứng dụng

Nếu ứng dụng dùng **Spring Cloud Vault** để lấy cấu hình hoặc dùng Vault integration tự động, thuộc tính được hỗ trợ là:

```yaml
spring:
  config:
    import: "vault://"
  cloud:
    vault:
      uri: "https://vault.example.internal:8200"
      namespace: "engineering/payments"
      authentication: TOKEN
      token: "${VAULT_TOKEN}"
      kv:
        enabled: true
        backend: secret
        backend-version: 2
```

Đây là ví dụ **minh họa cách namespace gắn với config integration**; dùng `TOKEN` để dễ thấy tách biệt giữa namespace và xác thực. Trong môi trường vận hành, nên chọn **workload authentication** (Kubernetes/AppRole hoặc phương thức thích hợp) và quản lý token/lease thay vì sử dụng token tĩnh lâu dài. Vai trò, auth mount và policy vẫn phải được tạo đúng namespace.

`spring.cloud.vault.namespace` làm Spring Cloud Vault thêm header `X-Vault-Namespace` cho các HTTP request **do hạ tầng tích hợp đó quản lý**, bao gồm giai đoạn tải cấu hình khi phiên bản và cách khởi tạo được hỗ trợ. Không nên giả định property này sẽ thay đổi một `RestTemplate`, `WebClient` hoặc `VaultTemplate` tùy chỉnh dùng HTTP client hoàn toàn độc lập.

### 6.1. Thời điểm bootstrap quan trọng

Khi dùng `spring.config.import: "vault://"`, Spring Cloud Vault có thể phải gọi Vault **trước khi ứng dụng khởi tạo các Spring bean thông thường**. Namespace phục vụ Config Data phải được cấp qua nguồn cấu hình đọc được ở thời điểm đó (ví dụ `application.yml`, biến môi trường hoặc cơ chế bootstrap được phiên bản hỗ trợ).

Nếu một nhóm chỉ gắn `X-Vault-Namespace` bằng bean interceptor được tạo **sau startup**, bước Config Data import có thể đã thất bại trước khi bean đó xuất hiện.

### 6.2. Không nhầm `namespace` với `kv.backend`

| Property | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| `spring.cloud.vault.uri` | `https://vault.example.internal:8200` | HTTP(S) endpoint. |
| `spring.cloud.vault.namespace` | `engineering/payments` | Namespace đích của request. |
| `spring.cloud.vault.kv.backend` | `secret` | KV mount nằm **bên trong namespace**. |
| `spring.cloud.vault.kv.backend-version` | `2` | Cách truy cập KV version 2; không thay đổi namespace. |
| `spring.config.import` | `vault://` | Cơ chế import Spring Config Data; không phải TLS scheme hay namespace header. |

Nếu namespace đã được chọn bằng property, không nhân đôi `engineering/payments` trong `kv.backend`. Với KV v2, Spring Cloud Vault cũng có thể tự tạo đường dẫn `data/` theo cách quản lý KV của nó; hãy kiểm tra đường dẫn cuối cùng thay vì tự thêm tiền tố namespace vào mọi vị trí.

## 7. Spring Vault trực tiếp: cấu hình namespace ở HTTP client

Khi ứng dụng **tự tạo `VaultTemplate`**, cần bảo đảm HTTP client gắn namespace cho các request. Cách cấu hình tùy **phiên bản Spring Vault**.

### 7.1. Spring Vault 4.1 trở lên: `VaultClient.defaultNamespace`

Đây là ví dụ theo API **Spring Vault 4.1.x**. Nó dùng `VaultClient` với namespace mặc định, rồi tạo `VaultTemplate` sử dụng client đó:

```java
import java.util.Objects;

import org.springframework.vault.authentication.ClientAuthentication;
import org.springframework.vault.authentication.TokenAuthentication;
import org.springframework.vault.client.VaultClient;
import org.springframework.vault.client.VaultEndpoint;
import org.springframework.vault.core.VaultTemplate;

VaultEndpoint endpoint = new VaultEndpoint();
endpoint.setScheme("https");
endpoint.setHost("vault.example.internal");
endpoint.setPort(8200);

VaultClient client = VaultClient.builder()
        .endpoint(endpoint)
        .defaultNamespace("engineering/payments")
        .build();

String token = Objects.requireNonNull(
        System.getenv("VAULT_TOKEN"), "Thiếu VAULT_TOKEN");
ClientAuthentication authentication = new TokenAuthentication(token);

VaultTemplate vaultTemplate = new VaultTemplate(client, authentication);

// Đường dẫn tương đối trong namespace đã cấu hình:
var result = vaultTemplate.read("secret/data/app/config");
```

**Giới hạn của ví dụ:** token chỉ được lấy từ môi trường để dễ hình dung; phải được cấp đúng namespace và quyền. Với xác thực Kubernetes/AppRole, phần `ClientAuthentication` cần được cấu hình để **login tới đúng namespace**, và những HTTP client khác dùng cho login/renewal cũng phải nhận cấu hình namespace tương ứng.

Ưu điểm của `defaultNamespace` là không cần tự ghép `engineering/payments` vào từng API path. Đây là giá trị mặc định của client: các request gắn với client sẽ dùng namespace đó trừ khi API cho phép chỉ định khác ở từng request.

### 7.2. Đổi namespace cho một request cụ thể

Ở API `VaultClient` mới, có phương thức `.namespace(...)` trên request spec. Ví dụ khi cần thao tác ở một namespace khác bằng credentials **được phép cho namespace đó**:

```java
import org.springframework.vault.authentication.VaultToken;
import org.springframework.vault.client.VaultClient;

// 'client' là VaultClient được cấu hình endpoint như ví dụ trên.
// 'tokenForCatalog' được cung cấp an toàn cho namespace catalog.
String tokenForCatalog = java.util.Objects.requireNonNull(
        System.getenv("VAULT_CATALOG_TOKEN"), "Thiếu VAULT_CATALOG_TOKEN");
var response = client.get()
        .path("secret/data/app/config")
        .namespace("engineering/catalog")
        .token(VaultToken.of(tokenForCatalog))
        .retrieve()
        .requiredBody();
```

`.namespace(...)` trên request chọn header cho **request đó**; nó không phải phép thay đổi global để mọi thread dùng client lập tức chuyển namespace. Cũng không dùng một token của payments theo thói quen rồi gắn namespace catalog và kỳ vọng quyền được tự động chuyển.

Để vận hành dễ kiểm soát, **ưu tiên cấu hình một client/session theo một tenant hoặc một workload**. Nếu bắt buộc phục vụ nhiều namespace trong một process, dùng thiết kế tách client, credentials và lifecycle hoặc thao tác per-request được kiểm soát, không dùng biến global mutable `currentNamespace`.

### 7.3. Với Spring Vault phiên bản cũ hơn

Một số phiên bản Spring Vault trước 4.1 sử dụng `RestTemplate` hoặc interceptor `VaultClients.createNamespaceInterceptor(...)` để đặt `X-Vault-Namespace`. API này đã được đánh dấu deprecated ở Spring Vault 4.1, nơi `VaultClient.Builder.defaultNamespace` và request `.namespace(...)` là hướng được giới thiệu.

**Không sao chép lẫn constructor và API của nhiều major version.** Khi dự án chỉ dùng Spring Vault core mà không có Spring Cloud Vault, property `spring.cloud.vault.namespace` không tự tạo header cho mọi client tự xây dựng.

## 8. Namespace trong auth, session và token/lease lifecycle

Một ứng dụng thường có nhiều lời gọi Vault hơn là một `read`:

```text
Startup:
  POST /v1/auth/kubernetes/login  [namespace engineering/payments]
           │
           ▼
  nhận Vault token có policy phù hợp
           │
           ▼
Runtime:
  GET  /v1/secret/data/app/config [cùng ngữ cảnh namespace]
  POST /v1/transit/encrypt/key    [cùng ngữ cảnh namespace]
           │
           ▼
Lifecycle:
  POST /v1/auth/token/renew-self [namespace/token phù hợp]
  POST /v1/sys/leases/renew      [namespace/lease phù hợp]
```

Thiết kế cần trả lời:

1. **Client đăng nhập** có gắn namespace đúng với auth mount trong Vault không?
2. **Client thực hiện Vault operations** có gửi header đúng mỗi request không?
3. **Session manager/lease manager** có dùng đúng HTTP client hoặc cấu hình namespace liên quan không?
4. **Token được cấp** thuộc ngữ cảnh nào, có policy cho mount/path mong muốn không?
5. Khi workload thay đổi tenant, **credentials và lifecycle** có được tách đúng thay vì vô tình tái sử dụng token của tenant trước không?

Không dùng header như cơ chế “đổi danh tính” của token đã cấp. Vault xử lý quyền theo danh tính và policy thực sự của token, đồng thời áp dụng các quy tắc quan hệ namespace cha/con khi được cấu hình. Tránh khẳng định mọi token đều chỉ được dùng trong chính xác một namespace hoặc đều có quyền ở namespace con; phải kiểm tra quyền trên cụm cụ thể.

## 9. Proxy, TLS và ranh giới tin cậy của namespace header

Namespace header là metadata **HTTP**, không phải thông số của TLS. Vì thế:

- `https://vault.example.internal:8200` vẫn cần **CA, truststore và hostname verification** đúng dù request có `X-Vault-Namespace` hay không.
- Trong đường hầm HTTPS CONNECT không giải mã, forward proxy thường không xem được HTTP headers nằm bên trong TLS.
- Nếu ingress/reverse proxy **kết thúc TLS**, nó có thể quan sát, chuyển tiếp, xóa hoặc ghi đè các headers trước khi request tới Vault.
- Tên namespace **không thay** `Host`, SNI, SAN của certificate hoặc địa chỉ mà Java dùng để kết nối.

Nếu mọi request qua ingress đều bất ngờ rơi về namespace mặc định, hãy xác minh proxy **có chuyển nguyên `X-Vault-Namespace`** đến Vault hay không. Không tự tin vào kết quả test `curl` đi direct nếu ứng dụng thật đi qua gateway.

### 9.1. Không nhận namespace tùy ý từ người dùng bên ngoài

Với API đa tenant, việc lấy trực tiếp một chuỗi `namespace` từ URL, header của người dùng hoặc request body rồi gắn vào `X-Vault-Namespace` có thể gây **nhầm lẫn tenant** và rủi ro vượt quyền nếu ứng dụng đang nắm credential quyền rộng.

Hướng an toàn:

1. Xác thực danh tính tenant của request nghiệp vụ tại ứng dụng.
2. Ánh xạ danh tính đó tới namespace từ **cấu hình allowlist do hệ thống quản lý**, không từ chuỗi tùy ý.
3. Dùng token/role có **least privilege** và ràng buộc phù hợp với tenant đó.
4. Tách client/session giữa tenant khi cần, bảo đảm không rò request headers và cache giữa các lời gọi đồng thời.
5. Ghi audit metadata theo mã tenant an toàn, không ghi token, secret value hoặc dữ liệu nhạy cảm.

Namespace tạo ranh giới tổ chức dữ liệu; **policy và thiết kế credential** vẫn quyết định mức cô lập quyền truy cập thực tế.

## 10. Chẩn đoán khi namespace không đúng

| Hiện tượng | Nguyên nhân có thể | Kiểm tra đúng lớp |
| --- | --- | --- |
| Login tới `auth/kubernetes/login` trả `404` | Mount không tồn tại trong namespace mà request đang nhắm, hoặc path auth sai. | Xem namespace header trên **request login** và mount path thực tế. |
| KV trả `404` mặc dù CLI đọc được | CLI và Java dùng namespace khác; key/mount v1-v2 sai; resource không tồn tại. | So sánh `VAULT_NAMESPACE`, `spring.cloud.vault.namespace`, `X-Vault-Namespace`, path cuối cùng. |
| KV/Transit trả `403` | Token không có capability đúng path, role/policy hoặc namespace không phù hợp. | Kiểm tra auth method, token, policy và quyền trong namespace đích. |
| Thêm header nhưng ứng dụng vẫn truy cập root | HTTP client tạo request không dùng interceptor/default namespace, hoặc proxy loại header. | Quan sát request outgoing an toàn và cấu hình đúng HTTP client. |
| Chỉ lỗi khi token renew | Session manager dùng HTTP client khác hoặc token/namespace không tương thích. | Kiểm tra client cho renewal, TTL, token và đường dẫn renew. |
| Spring Cloud Vault lỗi ngay startup | Config Data import diễn ra trước bean tùy chỉnh; namespace property chưa được cung cấp. | Kiểm tra bootstrap/config sources và namespace của client sớm. |
| Đúng namespace nhưng gọi `sys/...` bị từ chối | API quản trị có hạn chế root/admin hoặc capability riêng. | Đọc yêu cầu endpoint và quyền admin, không tự chuyển sang root bằng token workload. |
| HTTP `502/504`, timeout hoặc lỗi TLS | Đường mạng/proxy/truststore. | Chẩn đoán route, TLS, timeout; namespace header không giải quyết lỗi transport. |

**Không kết luận mã `404` chỉ có một nguyên nhân.** Vault có thể không thấy mount ở namespace đó, key thực sự không tồn tại hoặc request sai KV version. Một số tình huống còn che giấu thông tin về resource theo chính sách. Cần phối hợp thông tin từ role, namespace, mount path và response/lifecycle.

### 10.1. So sánh một request qua curl với ứng dụng

Trong môi trường test được phép, dùng một request **có header** và một request **không có header** để thấy sự khác nhau của namespace:

```bash
# Có namespace header:
curl --include --cacert "$VAULT_CACERT" \
  -H "X-Vault-Namespace: engineering/payments" \
  -H "X-Vault-Token: $VAULT_TOKEN" \
  "$VAULT_ADDR/v1/secret/data/app/config"

# Không chỉ định namespace:
curl --include --cacert "$VAULT_CACERT" \
  -H "X-Vault-Token: $VAULT_TOKEN" \
  "$VAULT_ADDR/v1/secret/data/app/config"
```

Hai kết quả có thể khác nhau về status hoặc nội dung, tùy token và namespace. **Không hiển thị/log response secret ở nơi không được phép** và chỉ thực hiện trong môi trường test với dữ liệu giả.

## 11. Kiểm thử tích hợp Spring Vault theo từng request

Một kiểm thử tốt cần kiểm tra **HTTP header thực sự được gửi**, không chỉ assert giá trị cấu hình Java/YAML.

| Kịch bản | Kết quả mong đợi |
| --- | --- |
| Spring Cloud Vault cấu hình namespace đúng | Request bootstrap, login và KV từ thành phần tích hợp có namespace phù hợp. |
| Spring Vault 4.1 `defaultNamespace` | Các request do `VaultClient` tạo có `X-Vault-Namespace` mặc định. |
| Gọi `.namespace(...)` trên một request | Header của request đó được đặt đúng; request khác không tự đổi namespace. |
| Cùng path dưới namespace payments/catalog | Được định tuyến tới hai phạm vi riêng; token/policy kiểm soát kết quả. |
| Login không có namespace | Test phát hiện sai mount/path thay vì chỉ phát hiện ở KV read về sau. |
| KV v2 với header và `secret/data/...` | Không lặp tiền tố namespace hay `data/`; request nhắm đúng mount. |
| Token/lease renewal | HTTP client dùng namespace/token tương ứng, không thất bại do header mất. |
| Ingress/reverse proxy | Header được chuyển tiếp, không bị loại hoặc chèn sai; TLS vẫn xác minh đúng. |
| Header do user cung cấp không nằm trong allowlist | Ứng dụng từ chối request hoặc dùng mapping tenant được quản trị an toàn. |
| Vault Community edition | Không mặc định coi namespace là tính năng được hỗ trợ; test theo edition thực. |

Có thể dùng mock HTTP server để capture method, path và `X-Vault-Namespace` từ Java client, kết hợp test Vault Enterprise/HCP thật trong môi trường kiểm thử để xác minh **định tuyến namespace và policy**. Mock server chỉ chứng minh client gửi header; nó không thay Vault xử lý namespace.

Khi đo telemetry, nên ghi **loại thao tác** (ví dụ `kv_read`, `kubernetes_login`, `transit_encrypt`) và một namespace label đã chuẩn hóa, giới hạn số lượng giá trị. Không ghi `X-Vault-Token`, Kubernetes JWT, AppRole secret ID, request/response body chứa secrets hoặc tên tenant nhạy cảm không cần thiết.

## 12. Tình huống tự suy luận

**Tình huống A — Đổi `spring.cloud.vault.kv.backend` thành `engineering/payments/secret`:** request có thể nhắm sai mount nếu namespace đã được cấu hình bằng `spring.cloud.vault.namespace`. Hãy giữ `kv.backend: secret` và namespace riêng `engineering/payments`.

**Tình huống B — CLI đọc được nhưng Spring Vault `404`:** CLI có `VAULT_NAMESPACE=engineering/payments`, ứng dụng Java chỉ khai báo endpoint và token mà không thêm namespace header. Đối chiếu HTTP header ở Java; `VAULT_NAMESPACE` của CLI không tự áp dụng cho Spring Vault.

**Tình huống C — Đã thêm header cho KV nhưng Kubernetes login thất bại:** auth mount `auth/kubernetes` tồn tại trong namespace payments, còn client login không mang namespace. Cần cấu hình namespace cho **client authentication** chứ không chỉ `VaultTemplate.read`.

**Tình huống D — Dịch vụ multi-tenant nhận namespace tùy ý từ API caller:** workload dùng token quản trị quyền rộng nên việc người gọi đổi namespace trở nên nguy hiểm. Cần ràng buộc tenant qua identity, allowlist và credential tối thiểu; tốt nhất tách client/session cho những miền quyền độc lập.

**Tình huống E — Ingress bảo toàn TLS nhưng mất namespace header:** Java gửi `X-Vault-Namespace` đúng, gateway có rule xóa header không thuộc allowlist. Vault nhìn request ở namespace mặc định hoặc trả lỗi. Cần sửa cấu hình forward header tại gateway và test ở phía Vault, không chữa bằng cách nhân đôi namespace trong API path.

### Ghi nhớ

**`X-Vault-Namespace` chọn namespace cho một HTTP request tới Vault**, còn **`X-Vault-Token` và policy xác định quyền**. Namespace không nằm trong hostname, không phải KV mount, không được giữ ngầm trên TCP connection và không thay thế quá trình login. Với Spring Cloud Vault, dùng `spring.cloud.vault.namespace`; với Spring Vault trực tiếp, đặt namespace trên **Vault HTTP client thực sự sử dụng**. Hãy kiểm tra nhất quán các request login, KV, Transit, PKI, token/lease lifecycle, bảo toàn header qua proxy và thử quyền ở cả namespace cha/con theo chính sách của hệ thống.

## Tài liệu chính thức để đối chiếu phiên bản

- [HashiCorp Vault — Namespaces](https://developer.hashicorp.com/vault/docs/enterprise/namespaces): cách định tuyến namespace bằng header/path và khái niệm tenant.
- [HashiCorp Vault — Namespace and mount structure](https://developer.hashicorp.com/vault/docs/enterprise/namespaces/namespace-structure): namespace hierarchy, mount path và listener chroot.
- [Spring Cloud Vault — Reference](https://docs.spring.io/spring-cloud-vault/reference/): thuộc tính `spring.cloud.vault.namespace` và cấu hình Config Data.
- [Spring Vault — Vault Client Access](https://docs.spring.io/spring-vault/reference/vault/vault-client.html): `VaultClient`, `VaultTemplate` và namespace per-request.
