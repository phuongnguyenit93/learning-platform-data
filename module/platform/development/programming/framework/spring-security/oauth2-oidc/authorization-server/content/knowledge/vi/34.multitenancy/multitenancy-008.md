# Quản lý vòng đời tenant và cấu hình domain

## 1. Bối cảnh và mục tiêu

Một **OAuth 2.0/OpenID Connect Authorization Server** dùng **Spring Security**, **Spring Authorization Server** và **Spring Boot** có thể phục vụ nhiều tổ chức trên cùng một nền tảng. Mỗi tổ chức là một tenant với client, người dùng, chính sách xác thực, authorization, consent và cấu hình domain riêng. Khi nền tảng hỗ trợ custom domain, mỗi tenant còn có thể yêu cầu hostname đăng nhập mang thương hiệu của họ.

Quản lý tenant không chỉ là thêm một hàng vào bảng tenant. Một tenant mới cần được xác minh quyền sở hữu domain, cấu hình DNS, cấp chứng chỉ TLS, tạo namespace dữ liệu, cấu hình client và khóa ký, công bố discovery metadata, kiểm tra luồng đăng nhập rồi mới được phép phục vụ traffic. Khi tenant bị tạm ngưng hoặc rời nền tảng, các bước ngược lại phải xử lý token, session, key, dữ liệu và domain theo một trình tự có kiểm soát.

Ví dụ xuyên suốt: nền tảng đăng nhập `login.example.com` phục vụ Acme, Fabrikam và Northwind. Acme muốn dùng `auth.acme.example` làm custom login domain; Fabrikam dùng subdomain do nền tảng cấp; Northwind đang hoạt động nhưng có thể chuyển sang domain mới vào quý tới. Cả ba tenant chạy trên một cụm Spring Authorization Server sau reverse proxy.

Sau bài học, bạn có thể:

1. Mô hình hóa vòng đời tenant bằng trạng thái và chuyển trạng thái có điều kiện.
2. Thiết kế quy trình onboarding có thể retry và không tạo dữ liệu trùng.
3. Xác minh quyền sở hữu custom domain bằng DNS hoặc HTTP challenge.
4. Cấu hình DNS, TLS certificate, SNI và reverse proxy cho domain tenant.
5. Phân biệt tenant ID, custom domain, canonical host và OIDC issuer.
6. Định tuyến request tới đúng tenant bằng domain registry đáng tin cậy.
7. Quản lý thay đổi domain mà không vô tình phá vỡ issuer và trust của client.
8. Xử lý suspension, reactivation, offboarding và xóa dữ liệu.
9. Tổ chức provisioning, outbox, audit và quyền quản trị tenant.
10. Kiểm thử domain takeover, Host header poisoning, certificate failure và cross-tenant routing.

**Phạm vi phiên bản:** Ví dụ tham chiếu Spring Authorization Server 1.5.8 và Spring Security 6.x. Framework cung cấp các core service và cấu hình endpoint; vòng đời tenant, domain registry, DNS verification, certificate provisioning và workflow quản trị là trách nhiệm của ứng dụng/hạ tầng.

## 2. Các khái niệm cần tách biệt

### 2.1. Tenant ID

Tenant ID là định danh nội bộ ổn định của tenant, ví dụ `tenant-acme-001`. Nó được dùng trong database, audit, routing và policy. Tenant ID không nên phụ thuộc vào tên công ty, hostname hoặc issuer URL vì các giá trị đó có thể thay đổi.

### 2.2. Domain

Domain là hostname mà người dùng hoặc client dùng để truy cập dịch vụ, ví dụ:

- `acme.login.example.com`: subdomain nền tảng cấp cho Acme.
- `auth.acme.example`: custom domain do Acme sở hữu.
- `login.example.com`: domain chung của nền tảng.

Một tenant có thể có nhiều domain alias cùng trỏ tới một tenant. Một domain đã xác minh không mặc nhiên trở thành issuer.

### 2.3. Canonical host

Canonical host là hostname chuẩn mà hệ thống chọn làm địa chỉ chính cho một mục đích cụ thể, chẳng hạn trang đăng nhập hoặc endpoint tenant. Hệ thống có thể giữ domain cũ làm alias và chuyển hướng giao diện sang domain canonical.

Canonical host phải được chọn từ domain registry đã xác minh. Không lấy trực tiếp giá trị Host của request rồi coi đó là canonical host.

### 2.4. OIDC issuer

Issuer là định danh của OpenID Provider, được công bố trong discovery metadata và xuất hiện trong claim `iss` của ID Token. Client và Resource Server dùng issuer để xác minh token thuộc OP đã tin cậy.

Ví dụ:

~~~text
Issuer: https://login.example.com
Login domain: https://auth.acme.example
Tenant ID: tenant-acme-001
~~~

Ba giá trị có thể khác nhau. Nếu client đã cấu hình trust vào `https://login.example.com` thì đổi trang đăng nhập sang `https://auth.acme.example` không tự động yêu cầu đổi issuer. Ngược lại, nếu đổi issuer, đó là migration giao thức cần cập nhật client và Resource Server.

### 2.5. Domain verification và TLS certificate

Domain verification chứng minh tenant kiểm soát domain tại thời điểm xác minh. TLS certificate chứng minh endpoint có thể hoàn tất TLS handshake cho hostname đó. Đây là hai bước khác nhau:

- DNS TXT challenge có thể chứng minh quyền quản lý DNS.
- HTTP challenge có thể chứng minh khả năng phục vụ một resource dưới hostname.
- Certificate được cấp sau đó cho phép endpoint dùng HTTPS.

Không coi certificate hợp lệ là bằng chứng duy nhất về quyền sở hữu tenant; cũng không coi DNS verification đã hoàn tất là certificate đã sẵn sàng.

### 2.6. Quy tắc định dạng và tính ổn định của issuer

Issuer identifier trong OpenID Connect là URL dùng HTTPS. Giá trị này không được chứa query hoặc fragment; nên chọn URL canonical ổn định và giữ nguyên cách biểu diễn trong discovery metadata và token. Các biến thể chỉ khác dấu slash cuối, hostname alias hoặc scheme có thể bị client so sánh như những issuer khác nhau.

Không đổi issuer theo mỗi lần đăng nhập, theo tenant label có thể đổi tên hoặc theo hostname do request tự cung cấp. Nếu tenant đổi tên hiển thị, giữ issuer identifier cũ; thay đổi issuer URL phải được xử lý như migration giao thức.

## 3. Vòng đời tenant

### 3.1. Mô hình trạng thái

Một tenant có thể đi qua các trạng thái:

| Trạng thái | Ý nghĩa | Có phục vụ protocol traffic? |
| --- | --- | --- |
| REQUESTED | Đã nhận yêu cầu tạo tenant. | Không |
| PENDING_VERIFICATION | Đang xác minh tổ chức/domain. | Không |
| PROVISIONING | Đang tạo cấu hình, storage, key và domain resources. | Không |
| READY | Provisioning hoàn tất, đã qua kiểm tra readiness. | Chưa, chờ activate |
| ACTIVE | Tenant được phép sử dụng. | Có |
| SUSPENDED | Tạm ngừng theo policy hoặc yêu cầu vận hành. | Không hoặc giới hạn theo policy |
| DECOMMISSIONING | Đang thu hồi client/token, tháo domain và xử lý retention. | Không nhận giao dịch mới |
| DELETED | Tenant đã được xóa hoặc ẩn danh theo retention policy. | Không |
| FAILED | Workflow provisioning thất bại và cần retry hoặc can thiệp. | Không |

`READY` là trạng thái hữu ích để tách provisioning khỏi activation. Một tenant có thể đã có database, key và certificate nhưng chưa được đưa vào load balancer hoặc tenant resolver.

### 3.2. State transition

~~~mermaid
stateDiagram-v2
    [*] --> REQUESTED
    REQUESTED --> PENDING_VERIFICATION
    PENDING_VERIFICATION --> PROVISIONING: Domain / organization verified
    PENDING_VERIFICATION --> FAILED: Verification expired
    PROVISIONING --> READY: Provisioning and health checks pass
    PROVISIONING --> FAILED: Unrecoverable provisioning error
    FAILED --> PROVISIONING: Retry / repair
    READY --> ACTIVE: Explicit activation
    ACTIVE --> SUSPENDED: Admin / security / billing policy
    SUSPENDED --> ACTIVE: Reinstatement checks pass
    ACTIVE --> DECOMMISSIONING: Offboarding approved
    SUSPENDED --> DECOMMISSIONING: Offboarding approved
    DECOMMISSIONING --> DELETED: Retention and cleanup complete
~~~

Không cho phép mọi transition tùy ý. Ví dụ:

- `REQUESTED → ACTIVE` phải bị từ chối nếu chưa verification và provisioning.
- `FAILED → ACTIVE` phải bị từ chối nếu chưa chạy lại readiness checks.
- `DELETED → ACTIVE` không được phép; nếu khách hàng quay lại, tạo tenant mới hoặc quy trình phục hồi riêng.
- `SUSPENDED → ACTIVE` phải kiểm tra lý do suspension đã được giải quyết.
- `DECOMMISSIONING` không được nhận domain binding mới hoặc cấp token mới.

### 3.3. Transition phải có actor, lý do và version

Mỗi thay đổi trạng thái nên ghi:

- Tenant ID.
- Trạng thái cũ và trạng thái mới.
- Actor hoặc service thực hiện.
- Lý do và ticket/reference liên quan.
- Timestamp.
- Version trước/sau.
- Correlation ID của workflow.

Version tăng đơn điệu giúp phát hiện update đồng thời và event đến sai thứ tự. Không cho phép một lệnh cũ ghi đè trạng thái mới hơn.

### 3.4. Tenant state không thay thế domain state

Tenant có thể ACTIVE nhưng một custom domain đang có `certificate_status=PENDING` hoặc binding SUSPENDED. Ngược lại, domain có thể VERIFIED nhưng tenant vẫn PENDING_VERIFICATION hoặc SUSPENDED.

Quản lý tenant và domain bằng hai state machine liên kết nhưng độc lập. Điều này cho phép tạm ngừng một domain bị lỗi mà vẫn giữ tenant hoạt động qua domain nền tảng, nếu policy cho phép.

## 4. Mô hình dữ liệu tenant và domain

### 4.1. Tenant record

Một tenant record có thể chứa:

| Field | Ý nghĩa |
| --- | --- |
| `tenant_id` | Định danh bất biến. |
| `display_name` | Tên hiển thị có thể thay đổi. |
| `status` | Trạng thái tenant. |
| `issuer` | Issuer canonical nếu tenant có issuer riêng; có thể dùng issuer chung của nền tảng. |
| `default_domain_id` | Domain canonical cho giao diện hoặc endpoint theo policy. |
| `created_at` / `updated_at` | Thời điểm tạo/cập nhật. |
| `version` | Optimistic locking/version. |
| `policy_ref` | Tham chiếu policy xác thực, token và retention. |

Tenant ID không nên được tái sử dụng sau khi tenant bị xóa.

### 4.2. Domain record

Một domain registry có thể lưu:

| Field | Ý nghĩa |
| --- | --- |
| `domain_id` | ID của domain binding. |
| `tenant_id` | Tenant sở hữu binding. |
| `hostname_ascii` | Hostname chuẩn hóa dưới dạng ASCII/IDNA A-label. |
| `hostname_display` | Hostname hiển thị nếu cần giữ Unicode. |
| `domain_type` | PLATFORM_SUBDOMAIN hoặc CUSTOM_DOMAIN. |
| `purpose` | LOGIN, ISSUER, API hoặc mục đích đã định nghĩa. |
| `verification_status` | PENDING, VERIFIED, EXPIRED hoặc FAILED. |
| `dns_status` | UNKNOWN, PENDING, READY hoặc MISMATCH. |
| `certificate_status` | PENDING, ACTIVE, RENEWING, FAILED hoặc EXPIRED. |
| `binding_status` | PENDING, ACTIVE, SUSPENDED hoặc REMOVED. |
| `is_canonical` | Domain canonical cho purpose tương ứng. |
| `verified_at` | Thời điểm xác minh thành công. |
| `certificate_ref` | Tham chiếu certificate trong secret/certificate manager. |
| `version` | Version để chống update/event cũ. |

Một hostname không được đồng thời bind cho hai tenant. Cần unique constraint trên hostname canonical, có tính đến trạng thái reservation/release.

### 4.3. Ví dụ schema

Ví dụ PostgreSQL giản lược:

~~~sql
CREATE TABLE tenant (
    tenant_id varchar(100) PRIMARY KEY,
    display_name varchar(200) NOT NULL,
    status varchar(32) NOT NULL,
    issuer varchar(500),
    default_login_domain_id varchar(100),
    version bigint NOT NULL DEFAULT 0,
    created_at timestamptz NOT NULL,
    updated_at timestamptz NOT NULL
);

CREATE TABLE tenant_domain (
    domain_id varchar(100) PRIMARY KEY,
    tenant_id varchar(100) NOT NULL REFERENCES tenant(tenant_id),
    hostname_ascii varchar(253) NOT NULL,
    domain_type varchar(32) NOT NULL,
    purpose varchar(32) NOT NULL,
    verification_status varchar(32) NOT NULL,
    dns_status varchar(32) NOT NULL,
    certificate_status varchar(32) NOT NULL,
    binding_status varchar(32) NOT NULL,
    is_canonical boolean NOT NULL DEFAULT false,
    verified_at timestamptz,
    certificate_ref varchar(300),
    version bigint NOT NULL DEFAULT 0,
    created_at timestamptz NOT NULL,
    updated_at timestamptz NOT NULL
);

CREATE UNIQUE INDEX uq_tenant_domain_hostname_reserved
    ON tenant_domain (hostname_ascii)
    WHERE binding_status <> 'RELEASED';

CREATE UNIQUE INDEX uq_tenant_domain_canonical_purpose
    ON tenant_domain (tenant_id, purpose)
    WHERE is_canonical AND binding_status = 'ACTIVE';

CREATE INDEX idx_tenant_domain_tenant
    ON tenant_domain (tenant_id, purpose, binding_status);
~~~

DDL chỉ minh họa các thuộc tính cốt lõi. Production cần thêm reservation expiry, ownership challenge, audit fields, certificate renewal metadata, soft-delete/retention và constraint bảo đảm mỗi tenant có tối đa một canonical domain cho từng purpose. Cần thiết kế partial unique index hoặc transaction constraint theo database đang dùng.

### 4.4. Không lưu private key trong domain record

Domain record chỉ lưu reference tới certificate/key manager. Private key TLS phải nằm trong certificate manager, HSM hoặc secret store có kiểm soát. Signing key OAuth/OIDC cũng phải có key lifecycle riêng; không dùng chung private key TLS làm signing key token.

## 5. Onboarding tenant

### 5.1. Quy trình tổng thể

Một onboarding workflow có thể gồm:

1. Nhận yêu cầu và tạo tenant ở trạng thái REQUESTED.
2. Xác minh tổ chức/người quản trị theo quy trình đăng ký.
3. Tạo domain binding ở trạng thái PENDING.
4. Cấp ownership challenge và xác minh domain.
5. Cấu hình DNS trỏ về ingress của nền tảng.
6. Cấp TLS certificate và kiểm tra HTTPS.
7. Provision client registry, authorization/consent namespace, signing key và tenant policy.
8. Kiểm thử discovery, authorization, token và Resource Server validation.
9. Chuyển tenant sang READY.
10. Admin hoặc activation workflow chuyển tenant sang ACTIVE.

~~~mermaid
flowchart TD
    A["Tenant request"] --> B["Create REQUESTED tenant"]
    B --> C["Verify organization and domain"]
    C --> D{"Verification passed?"}
    D -->|No| E["FAILED / retry / expire"]
    D -->|Yes| F["Configure DNS"]
    F --> G["Issue TLS certificate"]
    G --> H["Provision tenant services and keys"]
    H --> I["Run readiness checks"]
    I --> J{"All checks pass?"}
    J -->|No| E
    J -->|Yes| K["READY"]
    K --> L["Explicit activation"]
    L --> M["ACTIVE"]
~~~

### 5.2. Idempotent provisioning

Provisioning có thể bị retry do timeout, worker restart hoặc external API trả lỗi tạm thời. Mỗi bước phải idempotent:

- Tạo tenant với idempotency key.
- Tạo domain binding bằng unique hostname constraint.
- Tạo signing key bằng stable key alias, không tạo key mới mỗi lần retry.
- Tạo client/policy với stable identifier.
- Tạo certificate order có thể tra cứu lại trước khi gửi order mới.
- Ghi workflow step và external resource ID để tiếp tục sau restart.

Không dùng một transaction database dài để bao trùm DNS provider, ACME CA, HSM và broker. Đây là distributed workflow; dùng saga/outbox, retry có backoff và compensation phù hợp.

### 5.3. Readiness checks trước activation

Trước khi tenant ACTIVE, kiểm tra:

- Domain ownership còn hiệu lực theo policy.
- DNS resolve tới đúng ingress.
- TLS handshake thành công và certificate SAN chứa hostname.
- Discovery metadata trả đúng issuer/endpoint.
- JWKS endpoint truy cập được và chứa public key phù hợp.
- RegisteredClient lookup không đọc chéo tenant.
- Authorization và consent store đúng tenant namespace.
- Token được phát hành với issuer, audience và tenant claim đúng.
- Resource Server xác minh token và tenant binding thành công.
- Audit/monitoring có tenant context.

Không chỉ kiểm tra HTTP 200 ở trang login. Một trang đăng nhập tải được chưa chứng minh token endpoint, discovery, JWKS và tenant isolation đã sẵn sàng.

## 6. Xác minh quyền sở hữu custom domain

### 6.1. DNS TXT challenge

DNS TXT là phương pháp phổ biến để chứng minh tenant kiểm soát DNS zone. Workflow:

1. Tenant gửi hostname, ví dụ `auth.acme.example`.
2. Server chuẩn hóa hostname và kiểm tra domain có thể đăng ký.
3. Server tạo challenge ngẫu nhiên đủ entropy.
4. Server lưu challenge hash, tenant ID, hostname, expiry và trạng thái PENDING.
5. Server yêu cầu tenant tạo TXT record dưới một tên challenge cố định, ví dụ `_platform-verify.auth.acme.example`.
6. Verification worker truy vấn DNS authoritative/recursive theo policy.
7. So sánh TXT value với challenge đang chờ.
8. Nếu khớp, đánh dấu VERIFIED và lưu thời điểm xác minh.

Ví dụ:

~~~text
Name:  _platform-verify.auth.acme.example
Type:  TXT
Value: platform-domain-verification=7mK...random...Q2
~~~

Challenge phải:

- Được sinh bằng cryptographically secure random generator.
- Có entropy đủ cao và không dự đoán được.
- Chỉ có hiệu lực cho một tenant và một hostname.
- Có thời hạn ngắn và one-time use.
- Được lưu an toàn; ưu tiên lưu hash nếu không cần đọc lại plaintext.
- Bị vô hiệu hóa sau khi xác minh hoặc khi domain binding bị hủy.

Không dùng một chuỗi challenge cố định cho mọi tenant.

### 6.2. HTTP well-known challenge

Một phương án khác là yêu cầu tenant phục vụ một resource tại đường dẫn challenge cố định, ví dụ:

~~~text
https://auth.acme.example/.well-known/platform-domain-verification
~~~

Verification worker fetch URL và kiểm tra nội dung khớp challenge. Cách này phù hợp khi tenant có quyền cấu hình web server nhưng không có quyền DNS zone.

Phải giới hạn outbound fetch:

- Chỉ fetch hostname đang được xác minh.
- Không theo redirect sang IP/host khác ngoài policy.
- Chặn private, loopback, link-local và metadata service IP.
- Kiểm soát DNS resolution/rebinding trong lúc kết nối.
- Giới hạn timeout, response size và content type.
- Chỉ dùng HTTPS với certificate hợp lệ theo yêu cầu challenge.

Nếu không kiểm soát các điều kiện này, domain verification endpoint có thể trở thành SSRF primitive.

### 6.3. Chọn phương pháp verification

| Phương pháp | Phù hợp khi | Giới hạn |
| --- | --- | --- |
| DNS TXT | Tenant quản lý DNS zone. | Cần chờ propagation/cache; record có thể bị xóa sau đó. |
| HTTP challenge | Tenant quản lý web server tại hostname. | Cần bảo vệ verifier khỏi SSRF và redirect abuse. |
| CNAME delegation | Tenant trỏ hostname tới target do nền tảng cấp. | Cần xác minh ownership ban đầu và quản lý target lifecycle. |
| Registrar/API integration | Nền tảng có tích hợp nhà cung cấp domain. | Phụ thuộc provider và quyền API. |

Không coi việc hostname đang trỏ tới ingress của nền tảng là đủ để chứng minh tenant sở hữu domain; attacker có thể cấu hình CNAME tới một dịch vụ bất kỳ nếu chưa có challenge.

### 6.4. Chuẩn hóa hostname

Trước khi lưu/so sánh hostname:

1. Chỉ nhận hostname, không nhận URL đầy đủ có scheme/path/query.
2. Loại bỏ trailing dot theo canonicalization policy.
3. Chuẩn hóa chữ hoa/thường thành lowercase.
4. Chuyển Unicode domain sang IDNA A-label theo một profile thống nhất.
5. Kiểm tra độ dài label và tổng hostname.
6. Từ chối wildcard nếu sản phẩm không có quy trình quản lý wildcard riêng.
7. Từ chối IP literal, localhost, internal suffix và domain không được phép theo policy.
8. Lưu canonical ASCII hostname để unique constraint và routing.

Không tự viết thuật toán IDNA. Dùng thư viện/platform implementation đã được kiểm thử, đồng thời giữ rõ Unicode display form và ASCII canonical form.

### 6.5. Domain reservation và chống takeover

Khi một tenant yêu cầu hostname, tạo reservation ngay để ngăn hai workflow đồng thời cùng bind domain. Reservation có expiry và trạng thái riêng:

- PENDING_VERIFICATION: đang chờ challenge.
- VERIFIED: tenant đã chứng minh quyền kiểm soát.
- ACTIVE: domain đã được route vào tenant.
- RELEASE_PENDING: đang chờ offboarding/cooldown.
- RELEASED: có thể đăng ký lại theo policy.

Khi tenant offboard, không lập tức giải phóng hostname nếu DNS/TLS/proxy còn trỏ tới nền tảng hoặc cache mapping chưa hết. Nếu domain bị giải phóng rồi tenant cũ hoặc chủ thể khác kiểm soát lại, nguy cơ domain takeover có thể ảnh hưởng callback, login page và issuer endpoint.

### 6.6. Xác minh lại domain

Verification ban đầu không chứng minh tenant vẫn kiểm soát domain mãi mãi. Tùy mức rủi ro, có thể:

- Yêu cầu re-verification khi đổi owner/admin hoặc thay đổi domain binding.
- Kiểm tra định kỳ DNS target và certificate.
- Cảnh báo khi TXT proof bị xóa nếu policy yêu cầu proof tồn tại liên tục.
- Tạm ngừng domain khi DNS trỏ sang đích ngoài policy.
- Giữ domain binding trong trạng thái SUSPENDED cho đến khi xác minh lại.

Không tự động xóa tenant chỉ vì một lần DNS lookup thất bại; DNS propagation, resolver outage và lỗi tạm thời cần được phân biệt với mất quyền kiểm soát thực sự.

## 7. DNS và TLS certificate lifecycle

### 7.1. DNS record

Với subdomain tenant, nền tảng thường yêu cầu một trong các cấu hình:

~~~text
auth.acme.example  CNAME  tenant-ingress.example.net
~~~

Hoặc A/AAAA record tới địa chỉ ingress được cấp. Với apex/root domain, DNS provider có thể hỗ trợ ALIAS/ANAME hoặc flattening vì CNAME ở zone apex có giới hạn theo DNS chuẩn và provider.

Hướng dẫn DNS phải ghi rõ record name, record type, target/value, TTL khuyến nghị, record cũ có cần xóa không, cách kiểm tra bằng DNS lookup và thời điểm hệ thống bắt đầu cấp certificate.

### 7.2. Kiểm tra DNS

Không chỉ kiểm tra một resolver. Có thể cần kiểm tra public recursive resolver, authoritative nameserver, A và AAAA record, CNAME chain, TTL/propagation và DNSSEC validation nếu domain bật DNSSEC.

Nếu A record trỏ đúng ingress nhưng AAAA trỏ tới server cũ, một số client sẽ đi IPv6 và gặp certificate hoặc routing lỗi. Readiness check nên xem cả record type mà ingress hỗ trợ.

### 7.3. TLS certificate

Sau khi ownership verification và DNS readiness đạt yêu cầu, workflow có thể yêu cầu certificate qua ACME hoặc certificate provider:

~~~mermaid
sequenceDiagram
    autonumber
    participant T as Tenant
    participant D as DNS
    participant P as Platform
    participant CA as ACME CA
    T->>D: Tạo TXT ownership proof và CNAME/A record
    P->>D: Kiểm tra proof và ingress target
    P->>CA: Tạo certificate order
    CA->>D: DNS-01 challenge (nếu dùng)
    D-->>CA: TXT challenge response
    CA-->>P: Certificate issued
    P->>P: Lưu certificate reference
    P->>P: Bind SNI / ingress route
    P-->>T: Domain ready
~~~

Certificate lifecycle có thể gồm PENDING, ISSUED, ACTIVE, RENEWING, FAILED, EXPIRED và REVOKED. Theo dõi expiry trước nhiều ngày, tự động renew và cảnh báo khi renewal lỗi.

### 7.4. Certificate và signing key là hai loại key khác nhau

TLS certificate dùng để bảo vệ kết nối HTTPS và chứng minh hostname tại TLS layer. Signing key của Authorization Server dùng để ký JWT/ID Token. Không dùng chung private key chỉ vì cả hai gắn với cùng tenant.

TLS certificate có SAN cho hostname; JWK có các thuộc tính `kid`, `use`, `alg` và public key parameters phù hợp. Hai lifecycle, quyền truy cập và quy trình rotation khác nhau.

### 7.5. SNI và certificate selection

Khi nhiều tenant dùng custom domain, TLS terminator thường chọn certificate dựa trên Server Name Indication (SNI) trong TLS ClientHello. Domain registry/certificate manager phải đảm bảo:

- SNI hostname đã được xác minh và bind ACTIVE.
- Certificate SAN khớp hostname.
- Certificate chưa hết hạn/revoked.
- Unknown SNI không trả certificate tenant khác ngoài policy.
- Khi certificate renew, cập nhật route an toàn và không làm gián đoạn handshake.

Nếu TLS terminate tại load balancer/CDN, cần xác định rõ nơi sở hữu private key và cách đồng bộ certificate giữa edge locations.

### 7.6. Reverse proxy và forwarded headers

Ứng dụng sau reverse proxy có thể nhận `Forwarded`, `X-Forwarded-Host`, `X-Forwarded-Proto` và port. Chỉ tin các header được trusted proxy xóa và ghi lại. Không để client Internet tự gửi các header này rồi điều khiển public URL hoặc issuer.

Quy trình an toàn:

1. Ingress chỉ nhận traffic từ public network theo policy.
2. Ingress strip forwarded headers từ request gốc.
3. Ingress đặt lại scheme/host/port đã chuẩn hóa.
4. Application chỉ trust header từ proxy network được xác thực.
5. Tenant resolver kiểm tra host với domain registry.
6. Discovery/redirect URL dùng canonical configuration đã xác minh.

Không bật xử lý forwarded headers một cách mù quáng trên mọi network interface.

## 8. Định tuyến request tới đúng tenant

### 8.1. Domain registry là nguồn sự thật

Tenant resolver nhận canonical hostname và tra domain registry:

~~~java
TenantDomainBinding binding =
    domainRegistry.findActiveByHostname(canonicalHost);

if (binding == null || !binding.isRoutable()) {
    throw new UnknownTenantDomainException(canonicalHost);
}

Tenant tenant = tenantRepository.findActive(binding.tenantId())
    .orElseThrow(UnknownTenantDomainException::new);
~~~

Đây là pseudocode. Lookup phải xác nhận cả domain binding và tenant state. Domain ACTIVE nhưng tenant SUSPENDED vẫn không được route vào protocol flow.

### 8.2. Request-scoped tenant context

Sau khi resolve, bind tenant context trong suốt request:

~~~java
TenantContext context = tenantResolver.resolve(request);

try (TenantContextScope ignored = tenantContext.bind(context)) {
    filterChain.doFilter(request, response);
}
~~~

Context có thể gồm tenant ID, canonical domain, issuer, policy và runtime reference. Clear context trong finally/close. Với async servlet, executor hoặc reactive flow, truyền context bằng cơ chế tương ứng; không dựa vào ThreadLocal mà không có propagation strategy.

### 8.3. Không fallback tenant mặc định

Nếu hostname không được đăng ký hoặc binding đã suspended, trả lỗi phù hợp và không route sang tenant mặc định. Fallback có thể làm lộ trang login hoặc metadata của tenant khác, tạo confusion trong OIDC flow.

### 8.4. Chặn Host header poisoning

Không xây URL redirect, issuer hoặc discovery endpoint bằng cách nối trực tiếp Host header:

~~~java
// Host is input for lookup only; issuer comes from verified configuration.
String issuer = tenantRegistry.require(tenantId).issuer();
~~~

Public URL phải lấy từ tenant registry/configuration đã được xác minh. Host header chỉ là đầu vào để tìm binding, không phải nguồn dữ liệu được tin cậy.

### 8.5. Cache domain mapping

Domain registry có thể được cache để giảm lookup, nhưng domain binding và tenant state là dữ liệu nhạy cảm. Khi domain chuyển tenant, bị suspended hoặc offboard:

- Evict hostname mapping cũ và mới.
- Phát invalidation event tới mọi node.
- Dùng version/generation để chặn stale loader ghi mapping cũ.
- Nếu invalidation lag vượt SLA, bypass cache hoặc từ chối host đang chuyển trạng thái.

Không giữ cache mapping lâu hơn reservation/binding policy.

## 9. Cấu hình domain và issuer trong Spring Authorization Server

### 9.1. AuthorizationServerSettings

Spring Authorization Server dùng `AuthorizationServerSettings` để cấu hình issuer và endpoint URI. Trong một server context đơn giản, settings thường là bean cấu hình tĩnh:

~~~java
@Bean
AuthorizationServerSettings authorizationServerSettings() {
    return AuthorizationServerSettings.builder()
        .issuer("https://login.example.com")
        .build();
}
~~~

Ví dụ này cấu hình issuer chung. Custom login domain của tenant có thể chỉ là domain trình bày/login; không cần đổi issuer nếu issuer chung vẫn là trust identity mà client sử dụng.

### 9.2. Nhiều domain nhưng một issuer

Nếu nhiều hostname cùng phục vụ một issuer:

- Domain registry ánh xạ hostname tới tenant/UI context.
- Issuer settings giữ giá trị canonical chung.
- Discovery metadata phải công bố issuer chung.
- Endpoint URL phải được tạo từ public endpoint configuration đáng tin cậy.
- Client phải dùng issuer canonical khi discovery.

Nếu cần endpoint canonical chung, có thể chuyển hướng trang UI hoặc cung cấp alias theo policy. Không tự tạo discovery metadata với issuer khác nhau chỉ vì request tới hostname khác.

### 9.3. Một issuer cho mỗi tenant

Nếu tenant có issuer riêng, mỗi request phải resolve đúng tenant-specific settings trước khi endpoint cần issuer được xử lý. Không mutate một singleton `AuthorizationServerSettings` dùng chung theo từng request; hai request song song có thể ghi đè issuer của nhau.

Các cách triển khai:

- Application context/filter chain riêng cho từng issuer.
- Tenant runtime registry với adapter/context được thiết kế cho multi-issuer.
- Deployment riêng theo tenant hoặc nhóm tenant.

Phải kiểm thử song song request từ hai hostname để chứng minh issuer, endpoint, JWK source và core service không bị trộn.

### 9.4. AuthorizationServerContext

Spring Authorization Server dùng `AuthorizationServerContext` để cung cấp issuer/settings cho xử lý request. Nếu ứng dụng mở rộng context theo tenant, context phải được bind đúng thời điểm và gắn với request hiện tại. Không sửa global/static value hoặc singleton mutable để đổi issuer.

Đặc biệt kiểm tra discovery endpoint, authorization response và ID Token, JWT access token `iss`, token generator/JWK source, metadata endpoint cache, error response và redirect URL.

### 9.5. Domain change không tự động là issuer change

Có thể thay login domain từ `login.example.com` sang `auth.acme.example` mà vẫn giữ issuer `https://login.example.com`. Client tiếp tục discovery theo issuer canonical; người dùng nhìn thấy custom domain trong browser.

Nếu hợp đồng yêu cầu issuer là custom domain, hãy lập migration issuer riêng. Không thay issuer giữa chừng mà không cập nhật client, Resource Server, discovery, JWKS và token lifecycle.

## 10. Thay đổi domain

### 10.1. Thêm domain alias

Khi tenant muốn thêm domain:

1. Tạo domain binding PENDING.
2. Xác minh ownership.
3. Kiểm tra hostname không thuộc tenant khác.
4. Cấu hình DNS và TLS.
5. Thêm mapping ở ingress và tenant resolver.
6. Chạy readiness checks.
7. Chuyển binding sang ACTIVE.
8. Giữ domain canonical cũ cho đến khi có quyết định chuyển đổi.

Không activate domain trước khi certificate và routing sẵn sàng.

### 10.2. Chuyển canonical login domain

Khi đổi domain chính:

1. Xác minh domain mới và cấp certificate.
2. Cấu hình domain mới làm ACTIVE alias.
3. Kiểm thử discovery/login/token flow theo issuer policy.
4. Cập nhật UI links, email links, admin portal và tenant configuration.
5. Chuyển canonical login domain trong một transaction có version.
6. Giữ domain cũ ở trạng thái alias/redirect trong thời gian chuyển tiếp.
7. Theo dõi callback, cookie, session và lỗi OIDC.
8. Chỉ release domain cũ sau khi hết dependency và cooldown.

Cookie domain, SameSite, Secure, redirect URI và browser session có thể bị ảnh hưởng khi hostname đổi. Không giả định cookie được chia sẻ giữa hai registrable domain khác nhau.

### 10.3. Nếu domain cũ là issuer

Nếu domain cũ đồng thời là issuer, phải migration protocol:

- Duy trì discovery/JWKS cũ trong thời gian chuyển tiếp.
- Công bố issuer mới và metadata mới.
- Cập nhật OIDC client và Resource Server trusted issuer.
- Phát hành token mới với issuer mới.
- Không sửa claim `iss` của token cũ.
- Chờ token cũ hết hạn hoặc revoke theo policy.
- Retire issuer cũ sau khi client/session/token dependency đã được xử lý.

Không thể dùng HTTP redirect từ issuer cũ sang issuer mới để thay thế issuer validation; client phải biết issuer mới và trust nó.

### 10.4. Đổi domain ownership

Khi tenant chuyển domain cho tổ chức khác:

- Yêu cầu xác minh lại ownership.
- Tạm dừng domain binding cũ.
- Thu hồi certificate và route cũ theo thứ tự an toàn.
- Xóa association giữa hostname và tenant cũ.
- Áp dụng cooldown trước khi bind hostname cho tenant khác.
- Kiểm tra callback/redirect URI và custom domain references.

Không chuyển domain binding chỉ vì một admin đổi display name hoặc gửi yêu cầu qua email chưa xác thực.

## 11. Suspension, reactivation và offboarding

### 11.1. Suspension

Tenant có thể bị suspended vì yêu cầu của tenant, vi phạm điều khoản hoặc rủi ro bảo mật, billing/contract, domain verification hết hiệu lực, signing key/certificate compromise hoặc incident vận hành.

Khi suspend, cần xác định rõ các thao tác:

- Chặn authorization request mới.
- Chặn token issuance/refresh.
- Chặn dynamic client registration và thay đổi cấu hình.
- Có tiếp tục phục vụ discovery/JWKS hay không.
- Có giữ logout endpoint để kết thúc session không.
- Có revoke token/session hiện hữu không.
- Resource Server xử lý token cũ như thế nào.

Không cho rằng chặn login sẽ tự làm access token đã phát hành mất hiệu lực.

### 11.2. Suspension theo domain

Nếu custom domain lỗi DNS/certificate nhưng tenant vẫn hợp lệ, có thể suspend riêng domain binding và tiếp tục dùng platform domain. Nếu domain bị takeover hoặc trỏ sang endpoint không tin cậy, cần gỡ route/certificate nhanh và cảnh báo tenant.

Không nhất thiết suspend toàn tenant khi chỉ một domain alias bị lỗi, trừ khi domain đó là issuer hoặc security boundary bắt buộc.

### 11.3. Reactivation

Trước khi re-activate:

1. Xác nhận lý do suspension đã được giải quyết.
2. Re-verify domain nếu ownership hoặc DNS thay đổi.
3. Kiểm tra certificate và key status.
4. Xác nhận client/redirect URI không bị thay đổi trái phép.
5. Kiểm tra token/session policy và quyết định có yêu cầu đăng nhập lại.
6. Chạy readiness checks.
7. Ghi actor/reason và chuyển trạng thái bằng optimistic locking.

Không tự động ACTIVE chỉ vì billing hoặc external provider báo đã khôi phục.

### 11.4. Offboarding

Offboarding là workflow có thứ tự:

1. Chuyển tenant sang DECOMMISSIONING và ngăn provisioning mới.
2. Chặn authorization/token issuance và client registration.
3. Disable client credentials và revoke client nếu policy yêu cầu.
4. Revoke refresh token, authorization và session theo retention/security policy.
5. Xử lý JWT access token đã phát hành theo chiến lược revocation đã công bố.
6. Gỡ domain route và certificate binding.
7. Retire signing key theo quy trình lưu trữ/audit.
8. Export hoặc giữ dữ liệu audit theo hợp đồng/quy định.
9. Xóa hoặc ẩn danh dữ liệu khi retention cho phép.
10. Release domain sau cooldown và xác nhận không còn dependency.
11. Chuyển tenant sang DELETED.

### 11.5. Xóa tenant không phải một câu DELETE

Tenant data có thể nằm trong nhiều hệ thống: RegisteredClient và client secrets; OAuth2Authorization, access/refresh token và metadata; authorization consent; signing key/HSM; TLS certificate manager; domain/DNS provider; cache và message broker; audit log, backup và analytics; Resource Server tenant registry.

Deletion workflow phải theo dõi từng external resource và có retry. Một thao tác delete database không tự thu hồi certificate, DNS record, key hoặc cache mapping.

### 11.6. Retention và backup

Retention policy phải nói rõ:

- Dữ liệu nào xóa ngay khi offboarding.
- Dữ liệu nào giữ để audit/điều tra.
- Token/secret nào phải hủy sớm.
- Backup hết hạn sau bao lâu.
- Cách áp dụng deletion khi restore backup.
- Dữ liệu nào phải ẩn danh thay vì xóa vật lý ngay.

Không giữ signing key hoạt động chỉ để giải mã hoặc xác minh dữ liệu cũ nếu không có yêu cầu rõ ràng. Key archive và key destruction phải có policy riêng.

## 12. Workflow, transaction và event

### 12.1. Tenant lifecycle là distributed workflow

Provisioning domain thường gọi nhiều hệ thống: database, DNS provider, ACME CA, load balancer, HSM/KMS và message broker. Không thể giả định một transaction ACID bao trùm tất cả.

Dùng saga/workflow có workflow ID và idempotency key, step status và retry count, external resource ID, deadline/expiry, compensation action, audit event và dead-letter/manual repair path.

### 12.2. Transactional outbox

Khi đổi trạng thái tenant/domain trong database, ghi event vào outbox cùng transaction:

~~~sql
CREATE TABLE tenant_outbox (
    event_id varchar(100) PRIMARY KEY,
    tenant_id varchar(100) NOT NULL,
    aggregate_type varchar(40) NOT NULL,
    aggregate_version bigint NOT NULL,
    event_type varchar(100) NOT NULL,
    payload jsonb NOT NULL,
    created_at timestamptz NOT NULL,
    published_at timestamptz
);
~~~

Ví dụ event:

~~~json
{
  "eventId": "evt-1002",
  "tenantId": "tenant-acme-001",
  "aggregateType": "TENANT_DOMAIN",
  "aggregateVersion": 8,
  "eventType": "DOMAIN_ACTIVATED",
  "domainId": "domain-42",
  "hostname": "auth.acme.example"
}
~~~

Event không nên chứa private key, client secret hoặc token. Domain hostname có thể là dữ liệu cấu hình công khai nhưng vẫn cần bảo vệ theo policy.

### 12.3. Event consumer idempotent

Consumer có thể nhận event lặp. Dùng event ID, aggregate version và trạng thái hiện tại để bảo đảm:

- Activate domain hai lần không tạo hai ingress route.
- Provision key retry không tạo key alias ngẫu nhiên mới.
- Remove domain lặp không xóa nhầm binding khác.
- Event cũ không đưa tenant từ SUSPENDED trở lại ACTIVE.

### 12.4. Compensation

Nếu certificate issuance thành công nhưng provisioning key thất bại, workflow có thể giữ domain ở PROVISIONING/FAILED để retry, hủy certificate order hoặc revoke certificate nếu đã cấp mà không còn dùng, gỡ route tạm thời và giữ reservation để tránh tenant khác chiếm hostname giữa workflow.

Không compensation bằng cách xóa dữ liệu đã được dùng cho token đang lưu hành nếu hành động đó phá audit hoặc khả năng xử lý revoke.

## 13. Quản trị tenant và bảo mật thao tác

### 13.1. Phân quyền quản trị

Tách các quyền:

- Tenant owner: quản lý profile và domain của tenant mình.
- Tenant administrator: quản lý user/client theo policy.
- Platform operator: quản lý lifecycle và trạng thái tenant.
- Security operator: suspend, revoke và xử lý incident.
- DNS/certificate service account: chỉ thao tác resource domain/certificate cần thiết.

Một tenant admin không được bind domain đã thuộc tenant khác, đổi issuer tùy ý hoặc đọc domain challenge của tenant khác.

### 13.2. Domain challenge phải chống replay

Challenge cần gắn tenant ID, hostname, purpose và expiry. Khi sử dụng thành công, đánh dấu consumed. Nếu tenant đổi hostname, tạo challenge mới. Không cho một TXT record xác minh hostname A rồi dùng lại để xác minh hostname B.

### 13.3. Rate limit và abuse controls

Các endpoint tạo tenant/domain verification có thể bị lạm dụng để tạo nhiều reservation, gửi hàng loạt DNS lookup, tạo nhiều ACME order, dùng HTTP verifier làm SSRF hoặc chiếm domain binding bằng race.

Áp dụng rate limit theo account, tenant, IP và provider quota; giới hạn số domain pending; có approval theo threat model; giới hạn concurrent verification.

### 13.4. Audit

Ghi audit cho tenant create/activate/suspend/reactivate/delete; domain add/verify/activate/change canonical/release; certificate issue/renew/revoke; issuer change; signing key create/rotate/retire; client registration và secret rotation; offboarding và data deletion.

Audit cần actor, tenant ID, domain ID, timestamp, correlation ID, old/new state và reason. Không ghi challenge plaintext, token, client secret hoặc private key.

## 14. Các lỗi thường gặp

### Lỗi 1: Activate tenant ngay khi tạo database row

**Triệu chứng:** Tenant truy cập được endpoint nhưng discovery, key hoặc certificate chưa sẵn sàng.

**Nguyên nhân:** Không tách provisioning khỏi activation.

**Cách xử lý:** Dùng trạng thái READY và readiness checks trước ACTIVE.

### Lỗi 2: Coi DNS trỏ đúng ingress là proof ownership

**Triệu chứng:** Domain có thể bị bind bởi người không sở hữu domain.

**Nguyên nhân:** Không có challenge gắn tenant và hostname.

**Cách xử lý:** DNS TXT/HTTP challenge ngẫu nhiên, có expiry và one-time use.

### Lỗi 3: Coi verification đồng nghĩa TLS đã sẵn sàng

**Triệu chứng:** Domain VERIFIED nhưng browser báo certificate error.

**Nguyên nhân:** Không quản lý certificate issuance/activation riêng.

**Cách xử lý:** State machine domain riêng và TLS readiness check.

### Lỗi 4: Dùng Host header làm issuer

**Triệu chứng:** Token có issuer không ổn định hoặc attacker điều khiển public URL.

**Nguyên nhân:** Tin request header thay vì issuer registry.

**Cách xử lý:** Lấy issuer từ cấu hình đã xác minh; host chỉ dùng để lookup binding.

### Lỗi 5: Mutate AuthorizationServerSettings singleton theo request

**Triệu chứng:** Request Acme nhận issuer hoặc endpoint của Fabrikam.

**Nguyên nhân:** Dùng shared mutable settings trong concurrent request.

**Cách xử lý:** Tenant-specific runtime/context được thiết kế rõ, hoặc tách application context/deployment.

### Lỗi 6: Chỉ xóa domain mapping khi offboard

**Triệu chứng:** Certificate, DNS, cache hoặc issuer endpoint vẫn hoạt động.

**Nguyên nhân:** Offboarding không theo dõi external resources.

**Cách xử lý:** Saga có resource inventory, retry và verification sau cleanup.

### Lỗi 7: Giải phóng domain ngay lập tức

**Triệu chứng:** Domain cũ bị bind sang tenant khác khi cache/route/callback còn tồn tại.

**Nguyên nhân:** Không có cooldown và kiểm tra dependency.

**Cách xử lý:** RELEASE_PENDING, gỡ route/certificate, flush cache, xác nhận xong rồi mới release.

### Lỗi 8: Chỉ suspend login nhưng giữ refresh token hoạt động

**Triệu chứng:** Tenant bị suspend nhưng client vẫn refresh và nhận token mới.

**Nguyên nhân:** Chỉ chặn authorization endpoint.

**Cách xử lý:** Áp dụng tenant status tại token endpoint, refresh, client auth và các grant liên quan.

### Lỗi 9: Cho rằng revoke ở Authorization Server tự revoke JWT offline

**Triệu chứng:** Resource Server vẫn chấp nhận JWT đã phát hành.

**Nguyên nhân:** API chỉ xác minh chữ ký và expiry tại chỗ.

**Cách xử lý:** Dùng introspection, denylist/version check hoặc TTL ngắn theo yêu cầu.

### Lỗi 10: Domain Unicode được chuẩn hóa không nhất quán

**Triệu chứng:** Cùng domain hiển thị có thể tạo hai binding hoặc bị so sánh sai.

**Nguyên nhân:** Không dùng canonical IDNA representation.

**Cách xử lý:** Dùng thư viện IDNA, lưu A-label và unique constraint trên hostname canonical.

### Lỗi 11: Certificate renewal lỗi nhưng không cảnh báo

**Triệu chứng:** Custom domain đột ngột hết hạn certificate.

**Nguyên nhân:** Chỉ kiểm tra certificate lúc onboarding.

**Cách xử lý:** Theo dõi expiry, renew trước hạn, alert và có fallback domain theo policy.

### Lỗi 12: Async worker xử lý event cũ

**Triệu chứng:** Tenant đã SUSPENDED nhưng event cũ kích hoạt lại domain.

**Nguyên nhân:** Consumer không kiểm tra aggregate version/current state.

**Cách xử lý:** Version monotonic, idempotency key và transition guard.

## 15. Ma trận kiểm thử

| Trường hợp | Kết quả mong đợi |
| --- | --- |
| Tạo tenant mới | REQUESTED, chưa phục vụ traffic. |
| Verification hợp lệ | Domain VERIFIED và workflow được tiếp tục. |
| Challenge hết hạn | Không activate; tạo challenge mới theo policy. |
| TXT challenge của tenant A dùng cho tenant B | Bị từ chối. |
| HTTP challenge redirect sang private IP | Verifier chặn request. |
| Hai tenant đăng ký cùng hostname | Unique constraint/reservation chỉ cho một tenant thắng. |
| Hostname Unicode/punycode | Canonicalization nhất quán, không duplicate binding. |
| DNS A đúng, AAAA sai | Readiness fail hoặc cảnh báo theo ingress policy. |
| Certificate SAN không khớp | Domain không được ACTIVE. |
| Certificate renewal | Certificate mới được bind không gián đoạn. |
| Unknown SNI/Host | Không trả certificate/tenant mapping của tenant khác. |
| Forwarded header giả | Không thay đổi tenant, issuer hoặc public URL. |
| Tenant READY | Chưa nhận traffic trước explicit activation. |
| Tenant SUSPENDED | Không cấp authorization/token mới theo policy. |
| Domain suspended, tenant active | Domain khác vẫn phục vụ nếu policy cho phép. |
| Tenant reactivation | Chạy readiness checks và audit actor/reason. |
| Domain change, issuer giữ nguyên | Client vẫn validate issuer; login domain mới hoạt động. |
| Issuer migration | Client/resource server trust mới theo giai đoạn; token cũ không bị sửa iss. |
| Offboarding | Client/token/domain/key được xử lý theo workflow. |
| Event trùng lặp/sai thứ tự | Không tạo resource trùng hoặc activate trạng thái cũ. |
| Worker restart giữa provisioning | Retry tiếp tục từ step đã lưu. |
| Domain release cooldown | Hostname chưa được bind lại trước khi cleanup hoàn tất. |
| Cross-tenant lookup | Không thể truy cập client, authorization hoặc domain của tenant khác. |

## 16. Checklist production

| Hạng mục | Điều kiện cần xác nhận |
| --- | --- |
| Tenant state machine | Có trạng thái, transition guard và actor/reason/version? |
| Domain state machine | Verification, DNS, certificate và binding được quản lý riêng? |
| Tenant ID | Bất biến và không tái sử dụng? |
| Domain canonicalization | Lowercase, IDNA A-label, trailing dot và validation thống nhất? |
| Ownership proof | Challenge ngẫu nhiên, tenant-bound, hostname-bound, expiring và one-time? |
| Reservation | Unique hostname và reservation expiry chống race? |
| DNS | Có hướng dẫn A/AAAA/CNAME/TXT, TTL và propagation? |
| TLS | Certificate SAN, SNI, renewal và private key storage đúng? |
| Proxy | Forwarded headers chỉ tin từ trusted proxy? |
| Routing | Unknown/suspended domain fail closed, không fallback tenant? |
| Issuer | Canonical issuer độc lập với request Host? |
| SAS configuration | Không mutate singleton settings để đổi issuer theo request? |
| Provisioning | Idempotent, retryable và có compensation? |
| Persistence | Client/authorization/consent namespace theo tenant? |
| Key lifecycle | TLS key và token signing key tách biệt? |
| Domain change | Có alias/cutover/cooldown và issuer migration riêng? |
| Suspension | Chặn cả authorization, token, refresh và DCR theo policy? |
| Offboarding | Xử lý token, session, key, certificate, DNS, cache và retention? |
| Audit | Có actor, old/new state, reason, version và correlation ID? |
| Observability | Có certificate expiry, DNS mismatch, provisioning backlog và event lag? |
| Recovery | Có retry/manual repair và runbook cho external provider failure? |
| Tests | Có SSRF, domain takeover, Host poisoning, cross-tenant và concurrency tests? |

## 17. Bài tập thực hành

Một SaaS có 5.000 tenant, chạy Spring Authorization Server trên ba vùng triển khai. Mỗi tenant có một subdomain mặc định; một số tenant trả thêm custom domain. Nền tảng dùng issuer chung `https://login.example.com`. Domain custom cần TLS tự động. Tenant có thể bị suspend vì billing hoặc security incident.

Hãy thiết kế:

1. Tenant state machine và domain state machine.
2. Tenant/domain schema với unique hostname reservation và optimistic version.
3. DNS TXT challenge có expiry, one-time use và retry.
4. HTTP verification worker có SSRF protection.
5. DNS readiness và TLS certificate lifecycle.
6. SNI/ingress mapping và trusted forwarded header policy.
7. Tenant resolver không fallback khi hostname unknown/suspended.
8. Quy trình thêm domain alias và chuyển canonical login domain.
9. Cách giữ issuer chung khi đổi custom login domain.
10. Quy trình issuer migration nếu một tenant yêu cầu issuer riêng.
11. Suspension/offboarding workflow bao gồm token, session, key, certificate, DNS và retention.
12. Transactional outbox, idempotent worker và compensation cho lỗi ACME/HSM.
13. Metrics/SLO cho certificate renewal, provisioning latency và domain routing.
14. Integration test hai tenant đăng ký cùng hostname và test Host/X-Forwarded-Host poisoning.

**Tiêu chí đạt:** Tenant chỉ ACTIVE sau readiness checks; domain chỉ route sau ownership verification và TLS readiness; domain mapping lấy từ registry đáng tin cậy; issuer không được tạo từ Host header; suspension/offboarding xử lý cả token và external resources; retry không tạo resource trùng.

## 18. Tài liệu đối chiếu

- [OpenID Connect Discovery 1.0](https://openid.net/specs/openid-connect-discovery-1_0.html): issuer, Provider Configuration và discovery endpoint.
- [RFC 8414 — OAuth 2.0 Authorization Server Metadata](https://www.rfc-editor.org/rfc/rfc8414): issuer và metadata endpoint.
- [RFC 1034 — Domain Names: Concepts and Facilities](https://www.rfc-editor.org/rfc/rfc1034) và [RFC 1035 — Domain Names: Implementation and Specification](https://www.rfc-editor.org/rfc/rfc1035): DNS naming, records và resolution.
- [RFC 8555 — Automatic Certificate Management Environment (ACME)](https://www.rfc-editor.org/rfc/rfc8555): certificate order và challenge lifecycle.
- [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110): authority/Host và HTTP request semantics.
- [Spring Authorization Server 1.5.8 — Configuration Model](https://docs.spring.io/spring-authorization-server/reference/configuration-model.html): cấu hình Authorization Server và endpoint settings.
- [Spring Authorization Server 1.5.8 — AuthorizationServerSettings Javadoc](https://docs.spring.io/spring-authorization-server/reference/api/java/org/springframework/security/oauth2/server/authorization/settings/AuthorizationServerSettings.html): issuer và endpoint configuration.
- [Spring Authorization Server 1.5.8 — Core Model / Components](https://docs.spring.io/spring-authorization-server/reference/core-model-components.html): RegisteredClient, authorization, consent và core service contracts.
- [Spring Framework — ForwardedHeaderFilter Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/filter/ForwardedHeaderFilter.html): xử lý forwarded headers từ proxy và giới hạn trust boundary.
- [Spring Authorization Server 1.5.8 — AuthorizationServerContext Javadoc](https://docs.spring.io/spring-authorization-server/reference/api/java/org/springframework/security/oauth2/server/authorization/context/AuthorizationServerContext.html): context chứa issuer và AuthorizationServerSettings trong request.
- [Let's Encrypt — Challenge Types](https://letsencrypt.org/docs/challenge-types/): HTTP-01 và DNS-01 challenge cho TLS certificate issuance.
- [Let's Encrypt — Certificate Renewal](https://letsencrypt.org/docs/renewal/): tự động gia hạn certificate và vận hành ACME client.
