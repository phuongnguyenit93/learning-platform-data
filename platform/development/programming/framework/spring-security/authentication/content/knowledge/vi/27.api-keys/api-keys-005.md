# API key: Định danh khóa, phạm vi quyền và giới hạn môi trường sử dụng

## 1. Mục tiêu

Một **API key** là credential do một hệ thống phát hành để nhận diện và kiểm soát bên gọi API, thường là ứng dụng, dịch vụ, tác vụ tự động hoặc một tích hợp đối tác. API key có thể rất đơn giản về hình thức, nhưng muốn dùng an toàn phải trả lời đồng thời ba câu hỏi:

1. **Định danh khóa:** đang dùng *khóa nào*, thuộc chủ sở hữu/service account nào, ai quản lý vòng đời của nó?
2. **Phạm vi quyền:** khóa được phép gọi những API, thao tác và tài nguyên nào?
3. **Môi trường sử dụng:** khóa có được phát hành cho đúng môi trường `dev`, `staging` hay `prod`, và có đang được dùng đúng nơi được phép không?

Ví dụ, một khóa chỉ dành cho ứng dụng đồng bộ báo cáo ở môi trường `staging`, có scope `reports:read`, **không được** phép tạo báo cáo, sửa dữ liệu production hoặc gọi API của tenant khác.

> **Nguyên tắc:** API key chỉ trở thành một danh tính có quyền *sau khi* phía server kiểm tra secret và metadata đáng tin cậy. Tên khóa, prefix, scope hay environment do client tự khai không có giá trị chứng minh quyền.

Bài này sử dụng **Spring Security Servlet stack** (Spring Boot 3.x, Spring Security 6.x, Java 17+) để minh họa một cơ chế xác thực API key có key ID, secret ngẫu nhiên, quyền giới hạn và kiểm tra môi trường. Đây là mẫu giảng dạy cho API tự quản lý key; nếu tổ chức có API gateway/identity platform chuyên trách, nên dùng khả năng quản lý key tập trung và đưa kết quả xác thực vào hệ thống thông qua ranh giới tin cậy rõ ràng.

## 2. API key xác thực cái gì?

Trong phương thức dùng API key dạng bearer, bên nào **có được khóa hợp lệ** có thể trình khóa để yêu cầu quyền của khóa đó. Không nên diễn giải `keyId` hoặc `ownerId` thành bằng chứng rằng một con người đang trực tiếp đăng nhập.

~~~text
Client / service / batch job
    |
    | HTTPS
    | X-API-Key: ak_dev_<key-id>.<random-secret>
    v
API gateway hoặc Spring Security
    |
    +--> Parse key ID (định danh để tìm bản ghi)
    +--> Lookup server-side key metadata
    +--> So khớp secret với hash/digest đã lưu
    +--> Kiểm tra revoked / expired / environment
    +--> Nạp scopes, owner/service, tenant đáng tin cậy
    v
SecurityContext Authentication
    |
    +--> Endpoint-level authorization
    +--> Resource / tenant / object-level authorization
    v
Ứng dụng trả dữ liệu đúng quyền
~~~

Có hai lớp cần tách:

- **Authentication:** key secret có đúng, key có còn active và hợp lệ trong môi trường hiện tại không?
- **Authorization:** key đã xác thực được phép làm việc này với tài nguyên/tenant này không?

Không được thay authentication bằng cách kiểm tra `X-Key-ID` hoặc `X-Environment` do client gửi. Những header đó có thể tự giả mạo.

### API key, OAuth access token và session

| Loại credential | Thường đại diện cho | Điểm cần nhớ |
|---|---|---|
| API key | Một ứng dụng, service account, đối tác hoặc một key cụ thể | Thường cần tự quản lý key ID, secret, scopes, revocation |
| OAuth 2.0 access token | Quyền được Authorization Server cấp cho client/chủ thể | Có thể có audience, expiry, scope; cũng có thể là bearer |
| OIDC ID Token | Kết quả xác thực người dùng cho OIDC Client | Không mặc định dùng làm API access token |
| Browser session cookie | Phiên ứng dụng đã đăng nhập | Có cookie, session, CSRF, logout riêng |
| mTLS client certificate | Danh tính/khả năng giữ private key của một client | Có proof-of-possession nhưng vẫn cần phân quyền |

API key phù hợp hơn cho các tích hợp **machine-to-machine đơn giản** với chính sách quyền rõ ràng. Với đăng nhập người dùng, ủy quyền đa bên phức tạp, delegated access hoặc yêu cầu token chuẩn hóa, thường cân nhắc OAuth2/OIDC và identity platform.

## 3. Key ID và secret: vai trò hoàn toàn khác nhau

### 3.1. Định danh khóa (key ID)

**Key ID** là mã dùng để tìm đúng bản ghi khóa trong cơ sở dữ liệu và phục vụ quản trị: hiển thị, audit, thu hồi, phân biệt nhiều khóa của cùng một tích hợp. Một ID có thể được nhìn thấy trong log đã được kiểm soát.

Ví dụ định dạng:

~~~text
ak_dev_3zT5GkQK9_pRAwXt.rE5oDTKJ7C8jl1lC04GbVyiS_Xrtx42lJ7sTc_ZkaXA
└────────────────────────┘ └─────────────────────────────────────────┘
           key ID                    secret ngẫu nhiên
~~~

Đây là **chuỗi minh họa cấu trúc**; không dùng làm credential thực tế. Trong ví dụ triển khai, `ak_dev_<randomId>` là phần **key ID**, đoạn sau dấu chấm là secret.

Key ID nên:
- duy nhất trong hệ thống hoặc namespace môi trường;
- đủ khó đoán nếu muốn giảm khả năng liệt kê, nhưng không phụ thuộc vào việc khó đoán để bảo mật;
- không dùng trực tiếp làm quyền;
- có cấu trúc quản trị dễ nhận biết nếu hữu ích (như `ak_dev_`, `ak_prod_`);
- không chứa PII, email, password, thông tin mật hoặc token.

**Không có khái niệm “biết key ID nghĩa là đã xác thực”.** Khóa chỉ hợp lệ khi secret đúng và mọi policy server-side đều được thỏa.

### 3.2. Secret là credential cần bảo vệ

**Secret** phải đủ entropy để chống đoán/brute force. Cách tốt là dùng `SecureRandom` sinh **ít nhất 256 bit ngẫu nhiên** rồi encode Base64URL (32 byte → 43 ký tự Base64URL không padding). Không dùng tên hệ thống, timestamp, UUID rút gọn, số tăng dần, mật khẩu do người dùng tự nghĩ hay `Math.random()` để tạo secret.

Ví dụ quan hệ quản trị:

~~~text
key_id:       ak_prod_Xb1qeM85mf4pwH0z
secret:       chỉ hiển thị một lần lúc cấp (không lưu plaintext)
secret_hash:  SHA-256(secret ngẫu nhiên 256-bit) hoặc HMAC với pepper
environment:  prod
scopes:       ["reports:read"]
owner:        integration:partner-alpha
expires_at:   2026-12-31T00:00:00Z
revoked_at:   null
~~~

Các giá trị chỉ minh họa **metadata**, không phải một key phát hành. `secret_hash` là giá trị phía server lưu; khi nhận request server lấy secret vừa trình, tính digest rồi so sánh. Với secret **ngẫu nhiên thực sự 256 bit**, SHA-256 là lựa chọn thường phù hợp để xác minh một cách quyết định: attacker lấy digest không thể brute force secret khả thi. Nếu secret có entropy thấp như password con người, phải dùng password hashing phù hợp (Argon2id/bcrypt/PBKDF2) và tuyệt đối không giả định SHA-256 trần là đủ.

### 3.3. Vì sao nên lưu digest thay vì API key nguyên văn?

Nếu database hoặc trang quản trị bị lộ, lưu nguyên key sẽ cho attacker **đăng nhập ngay**. Lưu digest của secret (với random entropy cao) giảm rủi ro lộ credential thực tế. Lưu key ID công khai cho lookup và digest của phần secret:

~~~text
Request: "ak_dev_<id>.<secret>"
         │                 │
         │                 └─ SHA-256 → so sánh với stored digest
         └─ DB lookup theo ID
~~~

Không log key nguyên văn ở application, reverse proxy, tracing, metrics, exception hoặc analytics. Không gửi key trong URL query vì URL có thể xuất hiện trong access log/history/referrer; với API tự thiết kế, gửi qua HTTPS trong `X-API-Key` (hoặc chuẩn `Authorization` theo contract của hệ thống).

Một phiên bản quản trị chặt hơn có thể dùng **HMAC-SHA-256(secret, server-side pepper)** hoặc secret hashing có pepper được quản lý trong KMS/secret manager; điều đó thêm độ phức tạp vận hành. Cần xác định rõ cấu trúc digest để không tự chuyển thuật toán mà làm hỏng khóa cũ.

## 4. Metadata của một API key

Mô hình dữ liệu đề xuất:

| Trường | Nội dung | Dùng làm gì? |
|---|---|---|
| `key_id` | ID duy nhất của từng khóa | Lookup, log an toàn, rotation/revocation |
| `secret_digest` | Digest của secret ngẫu nhiên | Xác thực credential, không lưu plaintext |
| `owner_type`, `owner_id` | Service account/partner/integration được cấp | Quản trị ai chịu trách nhiệm, truy vết |
| `environment` | `dev` / `staging` / `prod` | Chặn dùng khóa sai môi trường |
| `scopes` | Ví dụ `reports:read`, `reports:write` | Giới hạn thao tác trên API |
| `tenant_id` | Tenant hoặc tổ chức được cấp | Chống truy cập chéo tenant |
| `resource_constraints` | Nhóm tài nguyên, project/account ID được phép | Kiểm tra mức đối tượng |
| `created_at`, `expires_at` | Thời điểm phát hành/hết hạn | Kiểm soát vòng đời |
| `revoked_at`, `status` | Trạng thái thu hồi/vô hiệu | Khóa ngay khi cần |
| `last_used_at` | Thời điểm dùng thành công gần nhất | Dọn khóa không hoạt động |
| `allowed_networks` | Tùy chọn CIDR theo chính sách | Phòng thủ bổ sung, không thay secret |
| `description` / `rotation_parent` | Mục đích và nhóm rotation | Thay khóa có kiểm soát |

Schema SQL minh họa (PostgreSQL):

~~~sql
CREATE TABLE api_keys (
    key_id         VARCHAR(100) PRIMARY KEY,
    secret_digest  BYTEA NOT NULL,
    owner_type     VARCHAR(32) NOT NULL,
    owner_id       VARCHAR(100) NOT NULL,
    environment    VARCHAR(16) NOT NULL
                   CHECK (environment IN ('dev', 'staging', 'prod')),
    tenant_id      VARCHAR(100),
    scopes         TEXT[] NOT NULL,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at     TIMESTAMPTZ NOT NULL,
    revoked_at     TIMESTAMPTZ,
    last_used_at   TIMESTAMPTZ,
    description    VARCHAR(300),
    CONSTRAINT ck_secret_digest_size
        CHECK (octet_length(secret_digest) = 32)
);
~~~

Schema chỉ minh họa kiểu dữ liệu và policy; trong production cần phân quyền DB, migrations, kiểm soát ownership, transaction khi phát hành và chỉ cấp quyền đọc các trường thực sự cần. Scope/tenant nên tham chiếu policy rõ ràng; không để người dùng tự sửa JSON metadata thành `admin`.

**Mỗi integration nên có key riêng cho từng môi trường, từng mục đích hoặc đối tác.** Nếu tất cả dịch vụ dùng chung một key, việc audit, thu hồi và giới hạn thiệt hại trở nên khó khăn.

## 5. Phạm vi quyền: chỉ cấp những gì cần thiết

### 5.1. Scope không đến từ request

Một key được cấp `reports:read` có thể đọc báo cáo. Client **không thể** tự bổ sung quyền bằng:

~~~http
GET /api/reports HTTP/1.1
Host: api.example.org
X-API-Key: ak_prod_valid-key-and-secret
X-Scope: reports:write
X-Role: ADMIN
~~~

Các header `X-Scope` và `X-Role` là input không đáng tin, **không thay thế** scope được lưu với bản ghi key. Server phải đọc scopes **sau khi secret được xác minh**, rồi kiểm tra đối với endpoint và đối tượng.

Ví dụ:

| Scope được cấp | GET /api/reports | POST /api/reports | DELETE /api/reports/{id} |
|---|---|---|---|
| `reports:read` | Có thể, nếu được quyền đối tượng | Từ chối | Từ chối |
| `reports:write` | Từ chối nếu không có read | Có thể theo policy | Từ chối nếu không có delete |
| `reports:read` + `reports:write` | Có thể | Có thể | Từ chối |
| `reports:delete` | Không mặc nhiên có read | Không mặc nhiên có write | Có thể, nếu đúng tenant/object |

Hệ thống có thể chọn scope theo tài nguyên (`orders.read`) hoặc thao tác (`reports:read`); quan trọng là **một hợp đồng nhất quán**, không tự cho rằng `read` bao hàm `write` hoặc ngược lại.

### 5.2. Quyền ở nhiều mức

1. **Endpoint + HTTP method:** ví dụ `GET /api/reports` cần `reports:read`, `POST` cần `reports:write`.
2. **Owner/tenant:** key thuộc tenant A không được đọc báo cáo tenant B, kể cả có scope read.
3. **Resource:** key đối tác chỉ dùng trong một project/account đã cho phép.
4. **Operation sensitivity:** thao tác có rủi ro cao có thể cần quyền chuyên biệt, phê duyệt hoặc xác thực bổ sung.

Ví dụ key `reports:read` của tenant `acme` không được dùng:

~~~http
GET /api/tenants/another-tenant/reports/42 HTTP/1.1
X-API-Key: ...
~~~

Backend phải so sánh tenant/requested resource với `tenant_id` trong **metadata đã xác thực**, không tin tenant ID do client khai. Có thể dùng policy-based authorization hoặc `@PreAuthorize` với service kiểm tra object-level, bên cạnh `hasAuthority`.

### 5.3. Authority trong Spring Security

Một cách biểu diễn scope là `GrantedAuthority("SCOPE_reports:read")`; khi cấu hình:

~~~java
.requestMatchers(HttpMethod.GET, "/api/reports")
    .hasAuthority("SCOPE_reports:read")
~~~

Spring Security kiểm tra chuỗi authority chính xác. Đây là **quy ước mapping do ứng dụng thiết kế** cho custom API key. Không tự động chuyển `X-Scope` của request thành `GrantedAuthority`, cũng không tự lấy role người dùng chỉ từ `ownerId`.

## 6. Giới hạn môi trường: dev, staging và prod

### 6.1. Vì sao phân môi trường?

- `dev`: có thể sử dụng dữ liệu giả, thử tích hợp; khóa bị lộ trong máy phát triển không được gọi production.
- `staging`: thử nghiệm gần production, nhưng vẫn phải có tài khoản/dữ liệu và quyền tách biệt.
- `prod`: dữ liệu thật, giám sát chặt, rotation, chính sách cấp phát nghiêm ngặt.

**Không sử dụng một secret API key duy nhất cho cả dev, staging và prod.** Tách key giúp sự cố ở môi trường yếu hơn không lan vào production, giảm khả năng người vận hành nhầm endpoint và hỗ trợ thu hồi độc lập.

Một chiến lược phân tách hiệu quả gồm:
1. Key record có `environment` được server quản lý.
2. Runtime đọc `app.environment` từ deployment configuration đáng tin (không lấy từ header/query/body).
3. Khi xác thực, yêu cầu `key.environment == app.environment`.
4. Key stores, secrets, IAM roles, mạng và dữ liệu được tách giữa các môi trường khi có thể.
5. API gateway có policy môi trường riêng, không cho route test trỏ lầm sang production.
6. Việc phát hành key ghi nhận đúng environment, không tự nâng cấp key test thành live.

### 6.2. Prefix chỉ để con người nhận biết

Ví dụ prefix `ak_dev_` hoặc `ak_prod_` có ích khi đọc log/redacted key ID, nhưng **không đủ để quyết định môi trường**. Attacker có thể thay text prefix nếu biết/có khả năng tạo request. Giá trị có thẩm quyền là bản ghi key **được tra cứu và xác thực**, cùng cấu hình runtime đáng tin.

Ví dụ:

~~~text
Client gửi:
  key_id prefix: ak_prod_...
Server tra trong DB:
  key.environment = staging
Server đang chạy:
  app.environment = prod

Kết quả: từ chối — metadata không khớp, không tin prefix.
~~~

Nếu có khóa bị tạo với prefix sai nhưng metadata đúng, nên sửa quy trình issuance và audit sự kiện; không cho prefix thay thế policy DB.

### 6.3. IP, origin, referrer và miền gọi API

Có thể giới hạn key thêm theo **nguồn kết nối hoặc dịch vụ gọi**, nhưng phải hiểu giới hạn:

- IP/CIDR allowlist có ích đối với server-to-server khi peer/network identity xác định được; IP có thể thay đổi qua NAT/egress.
- `X-Forwarded-For`, `X-Real-IP` có thể do client tự chèn nếu edge không làm sạch. Chỉ dùng khi reverse proxy trust chain được cấu hình chính xác.
- `Origin`, `Referer`, HTTP `Host` không phải chứng minh máy đang giữ secret trong các HTTP client tự do; client không phải browser có thể đặt giá trị tùy ý.
- API key nhúng trong JavaScript public website/mobile bundle không thật sự là secret: người sử dụng có thể trích xuất. Trong trường hợp đó phải dùng cơ chế thích hợp cho public clients, quota/restrictions của nhà cung cấp, BFF/ủy quyền hoặc token ràng buộc phù hợp; không dùng API key làm credential quản trị nhạy cảm.

Giới hạn môi trường là **phòng thủ nhiều lớp**, không chỉ một biểu thức so sánh prefix.

## 7. Phát hành, lưu trữ, rotation và thu hồi

### 7.1. Phát hành key một lần

Quy trình chuẩn:

1. Xác thực người quản trị hoặc workflow được phép phát hành.
2. Chọn owner/service account, environment, scopes, tenant, ngày hết hạn và quota.
3. Tạo key ID ngẫu nhiên duy nhất và secret ngẫu nhiên đủ mạnh (`SecureRandom`).
4. Lưu metadata + digest của secret theo transaction; lưu audit sự kiện phát hành.
5. **Hiển thị/truyền secret đầy đủ chỉ một lần** qua kênh bảo mật đến hệ thống nhận.
6. Bên nhận đưa secret vào secret manager/CI secret/OS secure store; không commit source, đặt trong URL hoặc ảnh chụp.
7. Từ lần sau trang quản trị chỉ xem key ID, mô tả, scopes, environment, expiry và hoạt động, **không xem lại secret**.

Không thể “khôi phục secret” từ digest: nếu mất secret, phát hành key mới và thay trong consumer.

### 7.2. Rotation không làm gián đoạn

~~~text
Thời điểm T0: key A active
T1: phát hành key B cùng owner/môi trường, scopes đã duyệt
T2: cài B vào secret manager của consumer
T3: consumer chuyển sang B, quan sát success/error
T4: thu hồi A sau khoảng chồng lấp được phê duyệt
T5: dọn key A và kiểm tra không còn request cũ
~~~

Không thay secret của A âm thầm trong DB khi consumer vẫn dùng A. Khóa mới có key ID mới; có thể dùng `rotation_parent` hoặc `key_family` để truy vết. Với sự cố lộ key, **thu hồi khẩn cấp** có thể cần diễn ra ngay, chấp nhận gián đoạn nếu rủi ro vượt quá lợi ích duy trì hoạt động.

### 7.3. Thu hồi và cache

Một key có thể bị `revoked`, hết hạn, khóa owner bị disable hoặc mất scope. Nếu ứng dụng cache thông tin key, phải giới hạn TTL cache, có cơ chế invalidation và định nghĩa độ trễ thu hồi chấp nhận được. Không dùng cache vô thời hạn, nhất là ở gateway hoặc nhiều replica.

Trong mỗi request hoặc theo một cache policy được đánh giá, cần kiểm tra:
- secret;
- trạng thái active/revoked;
- `expires_at`;
- environment;
- owner/tenant hiện còn hợp lệ;
- scopes hiện được cấp.

Hệ thống lớn có thể để API gateway xác thực và gắn identity xuống backend qua mTLS/trusted headers; khi đó backend chỉ tin headers đến từ gateway được khóa bằng network policy, không tin headers do client tự khai.

## 8. Ví dụ chạy được với Spring Boot 3.x, Spring Security 6.x và Java 17+

Ví dụ dưới đây minh họa **một ứng dụng API stateless**, tự xác thực header `X-API-Key` bằng các lớp Spring Security chuẩn. Nó có một key record trong bộ nhớ, được thiết lập bằng môi trường test; **không phải kho quản lý key production**. Production thay `KeyRepository` bằng DB/gateway, có revocation, audit, rate limit và secret manager thật.

### 8.1. Cấu trúc dự án

~~~text
api-key-demo/
├── pom.xml
└── src/main/
    ├── java/com/example/apikey/
    │   ├── ApiKeyDemoApplication.java
    │   ├── KeyIssuer.java
    │   ├── KeyRepository.java
    │   ├── DemoKeyRepositoryConfiguration.java
    │   ├── ApiKeyAuthentication.java
    │   ├── ApiKeyAuthenticationProvider.java
    │   ├── ApiKeyFilter.java
    │   ├── SecurityConfiguration.java
    │   └── ReportController.java
    └── resources/application.yml
~~~

### 8.2. Maven dependencies

File `pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.7</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>api-key-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-security</artifactId>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### 8.3. Server environment và key record từ deployment

File `src/main/resources/application.yml`:

~~~yaml
app:
  environment: ${APP_ENV}

demo:
  key:
    id: ${DEMO_KEY_ID}
    secret-sha256: ${DEMO_KEY_HASH}
    environment: ${DEMO_KEY_ENV}
    expires-at: ${DEMO_KEY_EXPIRES_AT}
~~~

Cả `app.environment` và `demo.key.environment` đến từ deployment/secret configuration. Trong demo có thể đặt hai giá trị `dev`; **trong production** môi trường runtime phải do deployment platform kiểm soát, metadata key lấy từ DB/chính sách phát hành, không tự gán `environment=app.environment` cho mọi key khi load.

Tất cả biến môi trường cần cung cấp trước khi chạy. Nếu chưa có, ứng dụng nên fail startup vì thiếu cấu hình, không dùng key mặc định có thể đoán.

### 8.4. Sinh key ID và secret ngẫu nhiên

File `src/main/java/com/example/apikey/KeyIssuer.java`:

~~~java
package com.example.apikey;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.SecureRandom;
import java.util.Base64;
import java.util.HexFormat;
import java.util.Set;

public final class KeyIssuer {

    public static void main(String[] args) throws Exception {
        if (args.length != 1 ||
                !Set.of("dev", "staging", "prod").contains(args[0])) {
            throw new IllegalArgumentException(
                    "Expected environment: dev, staging, or prod");
        }

        SecureRandom random = new SecureRandom();
        byte[] idBytes = new byte[12];
        byte[] secretBytes = new byte[32];
        random.nextBytes(idBytes);
        random.nextBytes(secretBytes);

        Base64.Encoder encoder =
                Base64.getUrlEncoder().withoutPadding();
        String id = "ak_" + args[0] + "_"
                + encoder.encodeToString(idBytes);
        String secret = encoder.encodeToString(secretBytes);

        byte[] digest = MessageDigest.getInstance("SHA-256")
                .digest(secret.getBytes(StandardCharsets.UTF_8));

        System.out.println("key_id=" + id);
        System.out.println("api_key=" + id + "." + secret);
        System.out.println("secret_sha256_hex="
                + HexFormat.of().formatHex(digest));
    }
}
~~~

Đây là **chương trình Java độc lập**, biên dịch/chạy từ thư mục project, không cần Spring runtime:

~~~bash
javac -d out src/main/java/com/example/apikey/KeyIssuer.java
java -cp out com.example.apikey.KeyIssuer dev
~~~

Output gồm ba dòng `key_id=...`, `api_key=...`, `secret_sha256_hex=...`; **giá trị cụ thể thay đổi mỗi lần** vì dùng `SecureRandom`, không có stdout cố định để so sánh. Secret được hiển thị một lần để demo cấp phát; ở production phải hiển thị/truyền an toàn, không đẩy output vào CI build logs hoặc hệ thống ghi lại console.

**Lưu ý kỹ thuật:** digest được tính từ **secret**, không từ toàn chuỗi `id.secret`. Server cần biết quy tắc này để kiểm tra đúng. Key ID có 12 byte random → 16 ký tự Base64URL; secret có 32 byte → 43 ký tự Base64URL không padding.

### 8.5. Kho metadata key

File `src/main/java/com/example/apikey/KeyRepository.java`:

~~~java
package com.example.apikey;

import java.time.Instant;
import java.util.Optional;
import java.util.Set;

interface KeyRepository {
    Optional<StoredKey> findById(String keyId);
}

record StoredKey(
        String keyId,
        byte[] secretSha256,
        String environment,
        Set<String> scopes,
        Instant expiresAt,
        boolean revoked
) {}
~~~

Các trường record là **metadata server-side**, không lấy từ HTTP request. Với DB thật, `findById` trả một bản ghi key duy nhất, scope/owner/tenant được quản lý tập trung.

File `src/main/java/com/example/apikey/DemoKeyRepositoryConfiguration.java`:

~~~java
package com.example.apikey;

import java.time.Instant;
import java.util.HexFormat;
import java.util.Optional;
import java.util.Set;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class DemoKeyRepositoryConfiguration {

    @Bean
    KeyRepository keyRepository(
            @Value("${demo.key.id}") String keyId,
            @Value("${demo.key.secret-sha256}") String hashHex,
            @Value("${demo.key.environment}") String keyEnvironment,
            @Value("${demo.key.expires-at}") String expiresAt) {

        byte[] digest = HexFormat.of().parseHex(hashHex);
        if (digest.length != 32) {
            throw new IllegalArgumentException(
                    "Expected a 32-byte SHA-256 digest");
        }

        StoredKey row = new StoredKey(
                keyId,
                digest,
                keyEnvironment,
                Set.of("reports:read"),
                Instant.parse(expiresAt),
                false);

        return candidateId ->
                keyId.equals(candidateId)
                        ? Optional.of(row) : Optional.empty();
    }
}
~~~

**Chỉ dùng trong demo:** bản ghi này có một key với scope `reports:read`. Nó sử dụng digest truyền qua environment, không lưu secret gốc trong nguồn Java. Production phải thay cấu hình `DemoKeyRepositoryConfiguration` bằng repository DB và quản trị nhiều key/revocation, có ràng buộc owner, tenant và môi trường thực.

### 8.6. Kiểu Authentication cho API key

File `src/main/java/com/example/apikey/ApiKeyAuthentication.java`:

~~~java
package com.example.apikey;

import java.util.Collection;
import org.springframework.security.authentication.AbstractAuthenticationToken;
import org.springframework.security.core.GrantedAuthority;

public final class ApiKeyAuthentication
        extends AbstractAuthenticationToken {

    private final Object principal;
    private Object credentials;

    private ApiKeyAuthentication(
            Object principal,
            Object credentials,
            Collection<? extends GrantedAuthority> authorities,
            boolean verified) {
        super(authorities);
        this.principal = principal;
        this.credentials = credentials;
        super.setAuthenticated(verified);
    }

    static ApiKeyAuthentication presented(String rawKey) {
        return new ApiKeyAuthentication(null, rawKey, null, false);
    }

    static ApiKeyAuthentication verified(
            String keyId,
            Collection<? extends GrantedAuthority> authorities) {
        return new ApiKeyAuthentication(keyId, null, authorities, true);
    }

    @Override
    public Object getPrincipal() {
        return principal;
    }

    @Override
    public Object getCredentials() {
        return credentials;
    }

    @Override
    public void eraseCredentials() {
        super.eraseCredentials();
        credentials = null;
    }
}
~~~

Trước khi xác thực, token chứa raw key trong `credentials` và `authenticated=false`. **Chỉ AuthenticationProvider** sau khi kiểm tra thành công mới tạo token xác thực có `principal=keyId`, authorities và **không giữ raw key trong kết quả**.

### 8.7. AuthenticationProvider kiểm tra secret + environment + trạng thái

File `src/main/java/com/example/apikey/ApiKeyAuthenticationProvider.java`:

~~~java
package com.example.apikey;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.time.Instant;
import java.util.List;

import org.springframework.security.authentication.AuthenticationProvider;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;

public final class ApiKeyAuthenticationProvider
        implements AuthenticationProvider {

    private final KeyRepository repository;
    private final String runtimeEnvironment;

    public ApiKeyAuthenticationProvider(
            KeyRepository repository, String runtimeEnvironment) {
        this.repository = repository;
        this.runtimeEnvironment = runtimeEnvironment;
    }

    @Override
    public Authentication authenticate(Authentication authentication) {
        if (!(authentication instanceof ApiKeyAuthentication) ||
                !(authentication.getCredentials() instanceof String raw)) {
            return null;
        }

        int dot = raw.indexOf('.');
        if (dot <= 0 || dot != raw.lastIndexOf('.') ||
                dot == raw.length() - 1) {
            throw new BadCredentialsException("Invalid API key");
        }

        String id = raw.substring(0, dot);
        String secret = raw.substring(dot + 1);

        if (!id.matches("ak_(dev|staging|prod)_[A-Za-z0-9_-]{16}") ||
                !secret.matches("[A-Za-z0-9_-]{43}")) {
            throw new BadCredentialsException("Invalid API key");
        }

        StoredKey stored = repository.findById(id)
                .orElseThrow(() ->
                        new BadCredentialsException("Invalid API key"));

        byte[] candidate = sha256(secret);
        boolean correctSecret = MessageDigest.isEqual(
                stored.secretSha256(), candidate);
        boolean active = !stored.revoked()
                && Instant.now().isBefore(stored.expiresAt());
        boolean correctEnvironment = stored.environment()
                .equals(runtimeEnvironment);

        if (!correctSecret || !active || !correctEnvironment) {
            throw new BadCredentialsException("Invalid API key");
        }

        List<GrantedAuthority> authorities = stored.scopes()
                .stream()
                .map(scope ->
                        (GrantedAuthority) new SimpleGrantedAuthority(
                                "SCOPE_" + scope))
                .toList();

        return ApiKeyAuthentication.verified(
                stored.keyId(), authorities);
    }

    private static byte[] sha256(String value) {
        try {
            return MessageDigest.getInstance("SHA-256")
                    .digest(value.getBytes(StandardCharsets.UTF_8));
        } catch (NoSuchAlgorithmException ex) {
            throw new IllegalStateException(
                    "SHA-256 is required by the Java platform", ex);
        }
    }

    @Override
    public boolean supports(Class<?> authenticationType) {
        return ApiKeyAuthentication.class
                .isAssignableFrom(authenticationType);
    }
}
~~~

Giải thích:
1. **Parse nghiêm ngặt:** chỉ chấp nhận một dấu chấm giữa ID/secret và định dạng key do hệ thống cấp. Regex ID cho phép `dev/staging/prod`; **regex không thay kiểm tra môi trường**.
2. **Tra cứu theo key ID:** identifier không phải secret; không cần scan toàn bộ key.
3. **So sánh digest:** `MessageDigest.isEqual` tránh so sánh byte-by-byte dừng sớm; secret ngẫu nhiên 256 bit khiến SHA-256 digest phù hợp ví dụ.
4. **Trạng thái và expiry:** key thu hồi hoặc đã hết hạn bị từ chối. `Instant.now().isBefore(expiresAt)` có nghĩa **đến đúng thời điểm hết hạn cũng không còn hiệu lực**.
5. **Environment:** metadata được server lưu phải khớp `app.environment` của chính runtime, không lấy từ client.
6. **Authority:** chỉ sau khi tất cả kiểm tra thành công, scope server-side mới thành `SCOPE_...`. Bản demo không đọc `X-Scope`, `X-Role` hoặc `X-Environment`.
7. **Thông báo chung:** sai key ID, secret, environment và revoked đều dẫn tới `BadCredentialsException("Invalid API key")`; tránh lộ chi tiết key tồn tại hay không qua response.

Trong production cần thêm lookup timeout, audit có thể truy vết key ID, rate limiting, kiểm tra owner/tenant và thu hồi có hiệu lực trên mọi replica. Không log raw key trong exception/debug tracing.

### 8.8. Filter nhận header mà không lưu credential trong session

File `src/main/java/com/example/apikey/ApiKeyFilter.java`:

~~~java
package com.example.apikey;

import java.io.IOException;
import java.util.Enumeration;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.AuthenticationException;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.web.filter.OncePerRequestFilter;

public final class ApiKeyFilter extends OncePerRequestFilter {

    private final AuthenticationManager authenticationManager;

    public ApiKeyFilter(AuthenticationManager authenticationManager) {
        this.authenticationManager = authenticationManager;
    }

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain chain) throws ServletException, IOException {

        Enumeration<String> values = request.getHeaders("X-API-Key");

        if (!values.hasMoreElements()) {
            chain.doFilter(request, response);
            return;
        }

        String presented = values.nextElement();
        if (values.hasMoreElements() || presented.isBlank()
                || presented.length() > 256 || presented.contains(",")) {
            response.sendError(401, "Invalid API key");
            return;
        }

        Authentication verified;
        try {
            verified = authenticationManager.authenticate(
                    ApiKeyAuthentication.presented(presented));
        } catch (AuthenticationException ex) {
            SecurityContextHolder.clearContext();
            response.sendError(401, "Invalid API key");
            return;
        }

        SecurityContext context =
                SecurityContextHolder.createEmptyContext();
        context.setAuthentication(verified);
        SecurityContextHolder.setContext(context);
        chain.doFilter(request, response);
    }
}
~~~

- Filter xử lý đúng **một request** và yêu cầu `X-API-Key` theo contract. Header lặp hoặc giá trị mơ hồ bị từ chối.
- Nếu **không có header**, filter không tự tạo principal; Spring authorization phía sau từ chối endpoint được bảo vệ.
- Nếu header sai, filter gửi 401 mà không để lỗi xác thực chưa xử lý chạy ra ngoài; không đưa nội dung secret vào thông báo.
- Khi đúng, dùng `SecurityContextHolder.createEmptyContext()` để lập context mới rồi lưu authentication. Spring Security quản lý/giải phóng context theo vòng đời request; demo dùng stateless, không lưu session.
- Kiểm tra duplicate ở Servlet API là một lớp bảo vệ; edge/proxy phải chuẩn hóa và từ chối request headers mơ hồ vì cách gộp header phụ thuộc từng hop.
- Filter được tạo **bên trong SecurityFilterChain**, không khai báo như một Servlet `@Bean Filter` khác để tránh tự đăng ký/chạy hai lần.

### 8.9. SecurityFilterChain kiểm tra scope theo HTTP method

File `src/main/java/com/example/apikey/SecurityConfiguration.java`:

~~~java
package com.example.apikey;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.UsernamePasswordAuthenticationFilter;

@Configuration
public class SecurityConfiguration {

    @Bean
    SecurityFilterChain apiSecurity(
            HttpSecurity http,
            KeyRepository repository,
            @Value("${app.environment}") String environment)
            throws Exception {

        var provider = new ApiKeyAuthenticationProvider(
                repository, environment);
        var manager = new ProviderManager(provider);

        return http
                .sessionManagement(session -> session
                        .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
                .csrf(AbstractHttpConfigurer::disable)
                .httpBasic(AbstractHttpConfigurer::disable)
                .formLogin(AbstractHttpConfigurer::disable)
                .authorizeHttpRequests(authorize -> authorize
                        .requestMatchers(HttpMethod.GET, "/api/reports")
                            .hasAuthority("SCOPE_reports:read")
                        .requestMatchers(HttpMethod.POST, "/api/reports")
                            .hasAuthority("SCOPE_reports:write")
                        .anyRequest().denyAll())
                .exceptionHandling(exceptions -> exceptions
                        .authenticationEntryPoint((request, response, ex) ->
                                response.sendError(
                                        401, "API key required")))
                .addFilterBefore(
                        new ApiKeyFilter(manager),
                        UsernamePasswordAuthenticationFilter.class)
                .build();
    }
}
~~~

- `anyRequest().denyAll()` đóng toàn bộ endpoint chưa được khai báo; các route quản trị hoặc health check phải có một chính sách riêng được duyệt nếu cần.
- `hasAuthority("SCOPE_reports:read")` khớp chính xác authority do Provider tạo từ **scopes của key record**.
- `STATeless` không dùng HTTP session để lưu identity; mỗi request phải trình key hoặc cơ chế khác được thiết kế rõ.
- `csrf(...disable)` **chỉ phù hợp với ví dụ API thuần, không dựa trên cookie trình duyệt tự gửi credential**. Nếu cùng ứng dụng có web session/cookie hoặc endpoint xử lý qua browser, cần security chain/CSRF strategy riêng; không sao chép tắt CSRF cho mọi ứng dụng.
- `httpBasic` và `formLogin` được tắt vì ví dụ chỉ nhận API key. Không tự mở fallback authentication khác làm sai policy.
- Đây là **custom API key authentication**, không phải Spring Security mặc định có sẵn bộ lọc API key hoàn chỉnh.

### 8.10. Endpoint minh họa và main class

File `src/main/java/com/example/apikey/ApiKeyDemoApplication.java`:

~~~java
package com.example.apikey;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ApiKeyDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(ApiKeyDemoApplication.class, args);
    }
}
~~~

File `src/main/java/com/example/apikey/ReportController.java`:

~~~java
package com.example.apikey;

import java.util.Map;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ReportController {

    @GetMapping("/api/reports")
    Map<String, String> read(Authentication authentication) {
        return Map.of(
                "status", "read granted",
                "keyId", authentication.getName());
    }

    @PostMapping("/api/reports")
    Map<String, String> write() {
        return Map.of("status", "write granted");
    }
}
~~~

`authentication.getName()` trong mẫu này là **key ID**; không có raw secret trong `Authentication` đã xác minh. Khi xây hệ thống thực, controller không nhất thiết trả key ID cho client; dùng key ID cho audit log được kiểm soát, và lấy `ownerId`/tenant từ principal server-side nếu có chính sách dữ liệu.

### 8.11. Chạy demo bằng PowerShell (Windows)

Trong thư mục `api-key-demo`, tạo key thử:

~~~powershell
javac -d out src/main/java/com/example/apikey/KeyIssuer.java
$issued = java -cp out com.example.apikey.KeyIssuer dev

$values = @{}
foreach ($line in $issued) {
    $pair = $line.Split('=', 2)
    $values[$pair[0]] = $pair[1]
}

$env:APP_ENV = "dev"
$env:DEMO_KEY_ENV = "dev"
$env:DEMO_KEY_ID = $values["key_id"]
$env:DEMO_KEY_HASH = $values["secret_sha256_hex"]
$env:DEMO_KEY_EXPIRES_AT = (Get-Date).ToUniversalTime()
    .AddHours(2).ToString("yyyy-MM-ddTHH:mm:ssZ")
$env:API_KEY = $values["api_key"]

mvn spring-boot:run
~~~

Các biến chỉ dùng trong môi trường demo. Lệnh `mvn spring-boot:run` giữ terminal chạy ứng dụng; có thể mở terminal thứ hai để gọi API, cung cấp key vừa cấp theo cách an toàn. Ở production, không giữ key dưới dạng `$env:API_KEY` lâu dài hoặc xuất key ra log.

**Nếu PowerShell gặp lỗi khi copy đoạn gán thời hạn bị xuống dòng**, viết phép gán này thành một dòng:

~~~powershell
$env:DEMO_KEY_EXPIRES_AT = (Get-Date).ToUniversalTime().AddHours(2).ToString("yyyy-MM-ddTHH:mm:ssZ")
~~~

Lúc chạy, cả `APP_ENV` và `DEMO_KEY_ENV` là `dev`. Scope của key demo là **chỉ `reports:read`**.

### 8.12. Thử request và kỳ vọng

Từ terminal có biến `API_KEY`:

~~~powershell
# Hợp lệ: chỉ đọc.
curl.exe -i -H "X-API-Key: $env:API_KEY" http://localhost:8080/api/reports

# Không có key: từ chối.
curl.exe -i http://localhost:8080/api/reports

# Có key chỉ đọc nhưng yêu cầu ghi: từ chối.
curl.exe -i -X POST -H "X-API-Key: $env:API_KEY" http://localhost:8080/api/reports
~~~

**Kỳ vọng:**
- GET với key hợp lệ: HTTP `200` và JSON chứa `status: "read granted"` cùng key ID.
- GET không có key: HTTP `401`.
- POST với key chỉ có scope read: HTTP `403`.

Đây là kết quả dự kiến của ứng dụng khi được build/chạy đúng cấu hình; **không có stdout cố định từ KeyIssuer** vì key được tạo ngẫu nhiên. Trong môi trường thật, thay `http://localhost` bằng HTTPS có chứng chỉ tin cậy và chính sách hạ tầng đúng.

### 8.13. Kiểm tra khóa ở sai môi trường

Để chứng minh ranh giới môi trường, đặt bản ghi key là `dev` nhưng runtime là `prod`:

~~~powershell
$env:APP_ENV = "prod"
$env:DEMO_KEY_ENV = "dev"
mvn spring-boot:run
~~~

Với cùng key được tạo cho dev, request GET bị HTTP `401` vì `stored.environment != runtimeEnvironment`. Trong production thực tế, việc tách database/key store, cấu hình deployment và IAM vẫn phải được duy trì; demo chỉ chứng minh lớp **kiểm tra môi trường của ứng dụng**.

## 9. Những chỗ mẫu demo khác hệ thống production

**Ví dụ chỉ có một key trong bộ nhớ.** Để đưa vào production, cần bổ sung:

- **Key management service/repository thật:** phát hành, lưu digest, lookup theo ID, thu hồi, rotation, expiry, owner, tenant, scopes, audit.
- **Secret quản lý tập trung:** người/ứng dụng nhận secret chỉ một lần; dùng secret manager, không dùng YAML có plaintext hoặc dùng source control.
- **Môi trường tách biệt:** key store, database, secret namespace, IAM, API endpoint, network policy tách dev/staging/prod; server-side environment check làm lớp bảo vệ bổ sung.
- **Giới hạn truy cập đối tượng:** dùng owner/tenant/project metadata sau xác thực để lọc dữ liệu. Chỉ `SCOPE_reports:read` chưa đủ để được đọc báo cáo của tổ chức khác.
- **Rate limit/quota:** theo key ID, owner, tenant, client và tuyến truy cập, kết hợp phát hiện dò key/abuse; không log raw key.
- **Cache có thể thu hồi:** TTL ngắn và invalidation rõ; việc revoke phải có thời gian hiệu lực được đo.
- **Đường kết nối:** HTTPS ở edge và hop nội bộ, xác minh TLS peer, firewall/network policies, ngăn header giả từ proxy khác.
- **Quyền phát hành:** cấp scope/env/tenant cần được review, tránh tự nâng quyền khi tạo key.
- **Error handling:** client nhận thông báo chung cho key sai; server audit nguyên nhân đủ để điều tra nhưng không để lộ secret/hash.
- **Phân biệt API key với user identity:** nếu key thuộc đối tác, principal nên là service account/key ID; user-level authorization cần một cơ chế riêng.
- **Key format/version:** nếu cần thay định dạng, chuẩn bị `key_version` và lộ trình migration, tránh parse brittle khi nhiều thế hệ key tồn tại.
- **Key rotation và endpoint downtime:** có thời gian overlap được kiểm soát, quan sát key cũ còn hoạt động, revoke sau chuyển đổi.

## 10. Bộ kiểm thử cho key ID, scope và environment

| Tình huống | Kết quả mong đợi |
|---|---|
| Key ID hợp lệ, secret đúng, environment trùng, active, đúng scope | Authentication thành công, truy cập endpoint được cấp |
| Key ID có thật nhưng secret sai | 401 |
| Key ID không tồn tại | 401, không xác nhận key có tồn tại |
| Chỉ biết key ID mà không có secret | 401 |
| Secret sai một ký tự | 401 |
| Key bị `revoked` | 401, kể cả secret đúng |
| Key đã qua `expires_at` | 401 |
| Khóa dev gửi tới runtime prod | 401, dù đổi prefix/header |
| Scope `reports:read` gọi POST cần `reports:write` | 403 |
| Tự thêm `X-Scope: reports:write` | Vẫn 403, vì quyền lấy từ server |
| Đổi `X-Environment: prod` trên request | Không có tác dụng |
| Hai header `X-API-Key` hoặc header gộp mơ hồ | Bị từ chối |
| API key truyền trong URL query, không qua header contract | Không xác thực |
| Key đúng scope nhưng trỏ tới tenant khác | Bị chặn theo tenant/object policy |
| Key đúng nhưng `owner` bị disable | Bị chặn theo chính sách thực tế |
| Thử hàng nghìn key đoán mò | Không đoán được secret, có throttling và alert |
| Key bị thu hồi khi nhiều replica cùng cache | Tất cả replica ngừng chấp nhận trong SLA revocation |
| Callback/HTTP host/Origin giả | Không được nâng quyền hoặc đổi environment |
| Key từ client JS public bị lộ | Thực thi giới hạn quota/restrictions, không cấp quyền nhạy cảm |

**Lưu ý phân loại lỗi:** `401 Unauthorized` là thiếu/sai credential; `403 Forbidden` là đã xác thực nhưng không có quyền cần thiết. Ở mức API, server có thể dùng 404 để không tiết lộ sự tồn tại của object theo policy. Các mã có thể được custom qua `AuthenticationEntryPoint`/`AccessDeniedHandler`, nhưng bảo mật và ý nghĩa phải nhất quán.

### Test tích hợp cần dùng cả middleware và network

Unit test Provider kiểm tra digest, revoked, expiry, env và scope. Integration test `MockMvc`/HTTP kiểm tra filter, lỗi header trùng, status 401/403, không mở endpoint khác, và thay role/scope trong DB không thể bị client tự nâng. Kiểm tra **đường đi thực** qua gateway/reverse proxy: IP, header normalization, HTTPS, hop metadata và giới hạn đường vào backend.

Đối với demo, các trường hợp cần chạy trước khi triển khai sản phẩm là GET hợp lệ 200, thiếu/secret sai 401, sai môi trường 401, ghi thiếu scope 403. Khi có tenant/object-level authorization, thêm test cross-tenant ở tầng repository/service.

## 11. Sai lầm phổ biến

1. **Coi key ID là secret:** key ID có thể bị nhìn thấy; chỉ chứng minh quyền khi secret hợp lệ và policy đúng.
2. **Coi prefix `ak_prod_` là bảo mật:** prefix chỉ giúp quản trị; environment phải kiểm tra từ metadata server và runtime configuration.
3. **Hardcode key trong Git, mobile app hoặc frontend JS:** secret có thể bị trích xuất; phải dùng cơ chế phù hợp với loại client, secret manager và không cấp quyền nhạy cảm cho public client.
4. **Sinh key bằng timestamp/UUID đơn giản:** không đạt entropy secret cần thiết; dùng `SecureRandom`.
5. **Lưu key plaintext trong DB hoặc log:** DB/log leak trở thành credential leak; lưu digest secret, redact request header.
6. **Dùng SHA-256 cho password tự đặt:** SHA-256 trần chỉ phù hợp ở đây vì secret ngẫu nhiên có entropy cao; password con người cần password hashing.
7. **Tin `X-Scope`/`X-Role` do client gửi:** quyền phải lấy từ metadata đã xác thực hoặc identity service đáng tin.
8. **Cấp một key `admin` cho mọi hệ thống:** không audit/revoke được độc lập và tăng blast radius; cấp key ít quyền theo consumer/môi trường.
9. **Chỉ bảo vệ URL, không bảo vệ HTTP method:** scope đọc/ghi phải gắn với thao tác, object-level authorization và tenant.
10. **Không đặt expiry hoặc không có revocation:** key có thể sống vô hạn; có quy trình khóa khẩn, rotation, overlap và cache invalidation.
11. **Dùng `Origin`/`Referer` như chứng cứ key đến từ đúng ứng dụng:** HTTP client có thể giả mạo; không dùng làm điều kiện xác thực duy nhất.
12. **Tin `X-Forwarded-For` từ Internet:** cần edge sanitization và proxy trust chain; IP chỉ là biện pháp bổ sung.
13. **Cho khóa staging truy cập production cùng dữ liệu:** phải tách key store/secret/database/IAM và kiểm tra môi trường.
14. **Filter hoạt động nhưng controller bỏ qua tenant:** `authenticated()` và scope check không giải quyết hết IDOR/BOLA.
15. **Tự đăng ký filter hai lần:** tránh `@Bean Filter` và `addFilterBefore` cùng lúc khi không có kiểm soát servlet auto-registration.
16. **Cho fallback auth khi API key lỗi:** nếu endpoint được chỉ định API-key-only, không âm thầm bypass bằng anonymous hoặc cơ chế yếu hơn.
17. **Log quá nhiều khi debugging:** không ghi `X-API-Key` hay `Authorization` nguyên văn; audit key ID, owner/service và kết quả đã xử lý an toàn.

## 12. Checklist thiết kế API key production

- [ ] Key ID duy nhất, stable, đủ cho lookup và audit; không chứa dữ liệu nhạy cảm.
- [ ] Secret sinh từ CSPRNG, ít nhất 256 bit, truyền an toàn một lần, không thể xem lại.
- [ ] DB lưu digest/metadata; kiểm tra digest an toàn, không lưu plaintext.
- [ ] Mỗi key thuộc owner/service cụ thể, tenant và môi trường được phê duyệt.
- [ ] `dev`, `staging`, `prod` có secret và chính sách độc lập.
- [ ] Server từ chối khi key environment khác deployment environment.
- [ ] Scopes gắn với bản ghi key, không lấy từ header/query/body của client.
- [ ] Phân quyền theo HTTP method + resource + tenant/object, áp dụng least privilege.
- [ ] Có expiration, revocation, rotation, quản lý key không dùng và audit.
- [ ] Có rate limit/quota, detection của abuse, không log raw key.
- [ ] HTTPS/TLS đầy đủ; backend/gateway trust boundary được thiết kế và kiểm thử.
- [ ] Không nhúng API key nhạy cảm trong client public; không dùng query parameter.
- [ ] Test thiếu key/sai secret/đúng ID/invalid env/insufficient scope/cross-tenant.
- [ ] Khi dùng gateway, backend chỉ tin kết quả xác thực qua kênh gateway đã được bảo vệ.
- [ ] Có tài liệu cho đối tác về cấp key, rotate, revoke, giới hạn quyền và xử lý lỗi 401/403.

## 13. Ghi nhớ

**Key ID cho biết đây là khóa nào; secret chứng minh bên gọi đang nắm credential; metadata xác định được làm gì và dùng ở đâu.** Sau khi kiểm tra secret, Spring Security có thể đưa key ID vào `principal`, đưa scope đã cấp vào `GrantedAuthority`, từ đó thực thi các rule `hasAuthority` trên API.

Một hệ thống API key an toàn không chỉ hỏi **“key có đúng không?”** mà còn hỏi **“key này có còn active, do ai quản lý, thuộc tenant nào, có đúng environment và có quyền thao tác với tài nguyên cụ thể không?”**.

## 14. Tài liệu tham khảo

1. [Spring Security — Servlet Authentication Architecture](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/architecture.html): `Authentication`, `AuthenticationManager`, `ProviderManager`, `AuthenticationProvider`, `SecurityContext`.
2. [Spring Security — Servlet Security Filter Chain](https://docs.spring.io/spring-security/reference/6.5/servlet/architecture.html): `SecurityFilterChain`, cách đặt authentication filter, `OncePerRequestFilter`.
3. [Spring Security — Authorize HTTP Requests](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/authorize-http-requests.html): `requestMatchers`, `hasAuthority`, `denyAll`.
4. [OWASP API Security Top 10 — Broken Object Level Authorization (API1:2023)](https://owasp.org/API-Security/editions/2023/en/0xa1-broken-object-level-authorization/): scope chung không thay kiểm tra quyền từng object.
5. [OWASP Secrets Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html): quản lý credential/secret và rotation.
6. [Google Cloud — Best practices for managing API keys](https://docs.cloud.google.com/docs/authentication/api-keys-best-practices): key restrictions, bảo vệ lưu trữ/truyền, xóa key không dùng.
7. [Oracle Java SE 17 — SecureRandom](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/SecureRandom.html): sinh byte ngẫu nhiên đủ mạnh.
8. [Oracle Java SE 17 — MessageDigest](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/MessageDigest.html): SHA-256 và `isEqual` dùng so sánh digest.
