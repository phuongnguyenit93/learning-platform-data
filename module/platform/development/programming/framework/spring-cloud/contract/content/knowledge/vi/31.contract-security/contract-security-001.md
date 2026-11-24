# Giả lập xác thực và phân quyền trong producer test

Một API có thể trả đúng JSON và HTTP status cho người dùng hợp lệ nhưng lại **truy cập được khi không có token**, **trả dữ liệu cho người không đủ quyền** hoặc **cho phép đọc dữ liệu của tenant khác**. Nếu producer contract test chỉ dựng một controller không có bộ lọc bảo mật, bài test có thể xanh dù ứng dụng thật đang có lỗi bảo mật nghiêm trọng.

**Spring Cloud Contract** cho phép mô tả hành vi HTTP hoặc thông điệp bằng **Groovy/YAML DSL**, sinh kiểm thử phía producer, đóng gói stub để consumer dùng **Stub Runner**, và gắn các bước này vào **CI** nhằm phát hiện thay đổi API không tương thích. Trong lộ trình **SPRING_CLOUD_CONTRACT**, nội dung bài thuộc chương **Bảo mật hợp đồng**, với chủ đề **Giả lập xác thực và phân quyền trong producer test**.

Mục tiêu không phải dựng một hệ thống danh tính giả có mọi tính năng của production. Mục tiêu là **giả lập có kiểm soát những danh tính và quyền cần thiết cho kịch bản hợp đồng**, đồng thời vẫn kiểm tra rằng **Spring Security và logic phân quyền thực của producer** đưa ra kết quả đúng. Bài học cũng chỉ rõ phần nào **không thể chứng minh** bằng một token giả, vì sao `401` khác `403`, cách tránh rò rỉ bí mật trong stubs JAR và cách xác minh kết quả bằng generated producer tests.

## 1. Authentication và authorization khác nhau thế nào?

Hai khái niệm liên quan nhưng không đồng nhất:

- **Authentication (xác thực):** yêu cầu đến từ ai hoặc từ service nào? Ví dụ kiểm tra một bearer token hợp lệ và rút ra danh tính `checkout-service`.
- **Authorization (phân quyền):** danh tính đã xác thực **được phép làm gì, trên tài nguyên nào**? Ví dụ chỉ principal có scope `orders.read` mới được đọc Order Service, và chỉ tenant sở hữu đơn hàng mới được xem dữ liệu đó.

Một lời gọi HTTP có thể trải qua nhiều tầng:

```mermaid
flowchart TD
    A[Checkout gửi GET /api/orders/ORDER-42] --> B[Spring Security filter chain]
    B --> C{Token có xác thực được không?}
    C -- Không --> D[401 Unauthorized]
    C -- Có --> E{Principal có scope/role được yêu cầu?}
    E -- Không --> F[403 Forbidden]
    E -- Có --> G{Được truy cập tài nguyên/tenant này?}
    G -- Không --> H[403 hoặc 404 theo chính sách]
    G -- Có --> I[Controller / Service / Repository]
    I --> J[200 + JSON theo contract]
```

**Token hợp lệ không đồng nghĩa đủ quyền.** Một token có chữ ký hợp lệ nhưng thiếu scope `orders.read` vẫn cần bị từ chối. Ngược lại, một token chứa chuỗi scope mong muốn nhưng không được xác thực không thể được coi là danh tính hợp lệ trong production.

### 1.1. Các trường hợp API thường phải bảo vệ

| Tình huống | Đầu vào | Kết quả thường mong đợi | Điều cần xác minh |
|---|---|---|---|
| Đã xác thực, đủ quyền | Bearer token hợp lệ với `orders.read` | `200 OK` | Response đúng hợp đồng |
| Không có credentials | Thiếu `Authorization` | `401 Unauthorized` | Không đọc dữ liệu được |
| Token sai hoặc không được chấp nhận | `Bearer invalid-token` | `401 Unauthorized` | Không được bỏ qua authentication |
| Token hợp lệ, thiếu scope | Token có `orders.audit` | `403 Forbidden` | Rule authorization được thực thi |
| Có scope, không sở hữu đơn | Tenant khác | `403` hoặc `404` theo API policy | Không lộ dữ liệu xuyên tenant |
| Đã được phép nhưng tài nguyên không tồn tại | `ORDER-MISSING` | `404 Not Found` | Lỗi nghiệp vụ đúng schema |
| POST thiếu CSRF trong ứng dụng cookie-session | Session đã xác thực, thiếu CSRF token | Có thể `403` | Phải phân biệt lỗi CSRF và thiếu role |
| Request có header không đúng format | `Authorization: something` | Thường `401` hoặc lỗi phù hợp security stack | Không được chấp nhận ngoài ý muốn |

**Không mặc định** một API luôn trả đúng các mã trên ở mọi framework/configuration. Phải đọc chính sách của producer và những HTTP semantics đã được nhóm thỏa thuận. Với yêu cầu che giấu sự tồn tại tài nguyên, API có thể cố ý trả `404` thay vì `403` cho người không được phép; các tests phải tuân chính sách đã công bố.

## 2. Phạm vi của producer contract test về bảo mật

Một bài producer contract test có thể chứng minh:

1. Request đúng credentials, quyền và fixture trả `200` với body đã cam kết.
2. Request không có xác thực bị từ chối theo policy.
3. Request có danh tính hợp lệ nhưng thiếu quyền nhận `403`.
4. Request có scope nhưng không có quyền với tài nguyên cụ thể không được tiết lộ dữ liệu.
5. Error status, headers, body và media type đã công bố vẫn ổn định.
6. Generated tests dùng **security filter chain và application code thật**, không chỉ một controller mock.
7. Producer thay đổi security rules ngoài dự kiến sẽ gây thất bại cho hợp đồng có liên quan.

Ngược lại, một test dùng `JwtDecoder` giả **không chứng minh**:

- JWT signature được kiểm tra bằng private/public key production.
- JWK key rotation, issuer discovery, audience validation và revocation hoạt động đúng.
- TLS, mTLS, ingress proxy hoặc API gateway đã được cấu hình an toàn.
- OAuth2 authorization code/client credentials flow hoạt động với Identity Provider thật.
- Chính sách session, CSRF, CORS hay cookie trong browser đã được kiểm tra đầy đủ.
- Mọi tài nguyên và mọi tổ hợp role/permission không được mô tả trong contract đều an toàn.

Những phần đó cần **security integration tests**, authentication provider tests, authorization policy tests, API gateway tests hoặc penetration testing thích hợp.

### 2.1. Ranh giới ba lớp kiểm tra

| Lớp | Cách thử | Giá trị | Giới hạn |
|---|---|---|---|
| **Producer contract test** | Generated test gửi request với test credentials đến producer context | Bảo vệ status/header/body và authorization behavior đã cam kết | Chỉ bao phủ case được mô tả |
| **Security integration test** | Token được xác minh qua decoder/JWK/IdP test thật, proxy hoặc gateway | Kiểm tra cơ chế authn end-to-end hơn | Tốn hạ tầng và thời gian |
| **Consumer Stub Runner test** | Consumer gửi credentials tới WireMock stub và đọc response | Kiểm tra client gửi header, xử lý `401/403` đúng | Stub không xác minh JWT như IdP/producer thật |

Mỗi lớp nên có mục tiêu rõ. Không coi một stub mapping `Authorization` là cơ chế authentication thực tế.

## 3. Ví dụ xuyên suốt: Checkout gọi Order Service

Giả sử Checkout là consumer gọi:

```http
GET /api/orders/ORDER-42
Accept: application/json
Authorization: Bearer contract-reader-token
```

Khi credentials và quyền phù hợp:

```http
HTTP/1.1 200 OK
Content-Type: application/json

{"id":"ORDER-42","status":"PAID","totalAmount":125000}
```

Trong **môi trường test**, ta định nghĩa hai token giả mang ý nghĩa nhất quán:

| Token giả | Principal | Scope | Tenant | Mục đích |
|---|---|---|---|---|
| `contract-reader-token` | `checkout-contract-test` | `orders.read` | `TENANT-42` | Kiểm tra `200` |
| `contract-auditor-token` | `audit-contract-test` | `orders.audit` | `TENANT-42` | Kiểm tra `403` do thiếu scope |
| Không có header | Anonymous | Không có | Không có | Kiểm tra `401` |
| `unknown-contract-token` | Không có principal được chấp nhận | Không có | Không có | Kiểm tra token bị từ chối |

**Đây không phải JWT thực**, không có chữ ký hợp lệ của bất kỳ Identity Provider nào. Các chuỗi này chỉ là fixture IDs để một `JwtDecoder` trong **Spring test context** có thể trả một principal kiểm thử hoặc từ chối credentials.

Trong production, hệ thống phải dùng bearer token thật, được xác minh theo issuer, audience, thời hạn, signature và các yêu cầu khác của kiến trúc.

### 3.1. Bốn contract cases cần độc lập

| Case | URL | Authorization | Kỳ vọng |
|---|---|---|---|
| Happy path | `/api/orders/ORDER-42` | `Bearer contract-reader-token` | `200` + JSON |
| Chưa xác thực | `/api/orders/ORDER-42` | Không có | `401` |
| Thiếu quyền | `/api/orders/ORDER-42` | `Bearer contract-auditor-token` | `403` |
| Không tìm thấy | `/api/orders/ORDER-MISSING` | `Bearer contract-reader-token` | `404` + error body |

Việc dùng cùng URL cho `200/401/403` là **có chủ đích** để kiểm tra ảnh hưởng của credentials. Tuy nhiên, khi các mappings này được đóng gói thành stubs, phải đảm bảo request matchers phân biệt **header có mặt, không có hoặc giá trị khác nhau**. Nếu mapping `401` quá rộng, consumer test có thể nhận `401` ngay cả khi đã gửi token đúng.

## 4. Contract Groovy DSL: có quyền đọc trả `200`

File ví dụ `src/test/resources/contracts/checkout/get_paid_order_authorized.groovy`:

```groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    name 'checkout_get_paid_order_authorized_200'
    description 'Checkout có scope orders.read đọc được đơn'

    request {
        method GET()
        url '/api/orders/ORDER-42'
        headers {
            header 'Accept', 'application/json'
            header 'Authorization', 'Bearer contract-reader-token'
        }
    }

    response {
        status OK()
        headers {
            contentType(applicationJson())
        }
        body(
            id: 'ORDER-42',
            status: 'PAID',
            totalAmount: 125000
        )
    }
}
```

Đây là **contract ở tầng HTTP**. Verifier sinh test gửi HTTP request với header đã định nghĩa vào producer test setup, rồi assert status/body. Nhưng test **chỉ chứng minh phân quyền đúng** nếu filter chain hoặc authorization interceptor tương ứng đang thực sự được chạy.

Nếu base test dùng một controller mock luôn trả `200`, contract sẽ xanh cả khi production security rules bị xóa. Đó là **false positive**.

### 4.1. Token mẫu không phải secret

`contract-reader-token` không được ánh xạ tới real username/password, production API key hay token của bất kỳ người dùng nào. Không lưu token OAuth2 thật trong Groovy/YAML DSL vì:

- Contracts có thể được commit vào Git.
- Generated tests in/log request data.
- Stubs JAR có thể được publish cho nhiều consumer.
- WireMock request journal có thể giữ headers.
- CI artifacts thường có vòng đời lưu trữ dài.

Để test cùng một bộ credentials qua nhiều module, chọn **chuỗi test cố định, không nhạy cảm** và quy ước nhất quán trong môi trường test.

## 5. Contract YAML: thiếu xác thực trả `401`

File `src/test/resources/contracts/checkout/get_paid_order_unauthenticated.yml`:

```yaml
name: checkout_get_paid_order_unauthenticated_401
description: Request không có bearer token phải bị từ chối
request:
  method: GET
  url: /api/orders/ORDER-42
  headers:
    Accept: application/json
response:
  status: 401
```

Đặc điểm:

- Không có header `Authorization` trong request.
- Response được kỳ vọng là `401 Unauthorized`.
- Không tự giả định producer luôn trả JSON error body.
- Chỉ thêm `WWW-Authenticate` vào contract nếu header/value thực sự được API cam kết và generated assertion kiểm tra theo semantics phù hợp.

**Điểm quan trọng:** contract request “không khai báo `Authorization`” **không tự diễn đạt một matcher cấm mọi Authorization header** trong generated WireMock mapping. Với producer verification, generated test thường gửi đúng các headers được khai báo, nên có thể kiểm tra thiếu credentials. Nhưng với consumer stub test, mapping không có matcher Authorization có thể vô tình **khớp cả request có bearer token**.

Nếu cần consumer test dùng chung `200` và `401` mappings trên cùng URL, phải kiểm tra generated mapping thực tế, áp dụng **absent-header matcher**/priority phù hợp WireMock version hoặc dùng các kịch bản được cô lập. Không suy rằng một contract thiếu header tự khiến mapping chỉ nhận anonymous request.

### 5.1. `WWW-Authenticate` trong lỗi 401

Trong nhiều Bearer resource servers, phản hồi `401` có header:

```http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer
```

Tùy trường hợp token sai, header có thể chứa thêm `error` hoặc metadata theo chuẩn Bearer. Không khóa cứng một chuỗi duy nhất cho mọi lỗi xác thực nếu framework có nhiều error cases. Khi header này là một phần của giao diện consumer dùng, hãy định nghĩa assertion tương ứng theo Contract DSL/version hỗ trợ hoặc một producer integration test rõ ràng.

## 6. Contract YAML: đã xác thực nhưng thiếu quyền trả `403`

File `src/test/resources/contracts/checkout/get_paid_order_forbidden.yml`:

```yaml
name: checkout_get_paid_order_forbidden_403
description: Token có thể xác thực nhưng thiếu scope orders.read
request:
  method: GET
  url: /api/orders/ORDER-42
  headers:
    Accept: application/json
    Authorization: 'Bearer contract-auditor-token'
response:
  status: 403
```

Kịch bản này chỉ có ý nghĩa nếu:

1. `contract-auditor-token` được test decoder **chấp nhận**.
2. Decoder sinh ra principal hợp lệ có scope `orders.audit`.
3. Spring Security filter chain/authorization manager yêu cầu `orders.read`.
4. Request đi qua filter chain thật.
5. Kết quả là `403` do thiếu quyền, **không phải `401` do token sai**.

Nếu decoder từ chối auditor token, generated test sẽ nhận `401` và fail, nhưng nguyên nhân **không phải authorization**. Vì vậy fixture phải phân biệt rõ “token sai” và “token hợp lệ nhưng thiếu scope”.

### 6.1. Đừng dùng `403` như tên chung cho mọi lỗi bảo mật

- `401`: authentication còn thiếu/không được chấp nhận theo API policy.
- `403`: principal đã được xác thực nhưng **không được phép** thực hiện hành động, hoặc bị chặn bởi một chính sách khác như CSRF.
- `404`: có thể là tài nguyên không tồn tại, hoặc API cố ý che giấu tài nguyên mà caller không được phép biết.

Một `403` có thể do **CSRF protection**, method security hoặc một gateway policy. Test cần biết **chính sách nào** đã chặn request trước khi kết luận đúng.

## 7. Contract bổ sung: đã được phép nhưng không có tài nguyên

File Groovy minh họa:

```groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    name 'checkout_get_missing_order_authorized_404'

    request {
        method GET()
        url '/api/orders/ORDER-MISSING'
        headers {
            header 'Accept', 'application/json'
            header 'Authorization', 'Bearer contract-reader-token'
        }
    }

    response {
        status NOT_FOUND()
        headers {
            contentType(applicationJson())
        }
        body(
            code: 'ORDER_NOT_FOUND'
        )
    }
}
```

Khi verify, base fixture cần đảm bảo `ORDER-MISSING` không tồn tại và token đã được chấp nhận. Nếu test nhận `401`, lỗi nằm ở authentication setup; nếu nhận `403`, có thể do authorization; nếu nhận `404` nhưng body khác, cần phân biệt lỗi nghiệp vụ với unmatched route.

Tình huống này giúp bảo vệ ranh giới **authorization được phép** và **business resource lookup thất bại**.

## 8. Cấu hình Spring Security của producer cần được kiểm tra

Giả sử Order Service là Spring Boot MVC dùng OAuth2 Resource Server và security rules:

- Mọi `GET /api/orders/**` yêu cầu authority `SCOPE_orders.read`.
- Những API khác cần authentication theo policy.
- JWT bearer token được xử lý bởi Spring Security.
- Controller/service thật phải chịu trách nhiệm tìm đơn và trả DTO.

Một cấu hình tối giản **mang tính minh họa**:

```java
package com.example.order.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class ApiSecurityConfiguration {

    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(
                    HttpMethod.GET,
                    "/api/orders/**"
                ).hasAuthority("SCOPE_orders.read")
                .anyRequest().authenticated()
            )
            .oauth2ResourceServer(oauth -> oauth.jwt(Customizer.withDefaults()))
            .build();
    }
}
```

Để cấu hình này có hiệu lực, producer phải có dependencies Spring Security và OAuth2 Resource Server tương thích. Với ứng dụng stateless bearer-token API, `POST/PUT/DELETE` có thể chịu tác động của CSRF nếu chưa thiết kế security configuration riêng; ví dụ chỉ dùng `GET` nên chưa đề cập việc tắt CSRF.

**Không sao chép `csrf().disable()` vào mọi ứng dụng chỉ để test qua.** Nếu API sử dụng session/cookie từ browser, bỏ CSRF protection có thể tạo lỗ hổng. Cách xử lý CSRF phải dựa trên threat model và loại authentication thực tế.

### 8.1. Scope và authority không có cùng tên

Một JWT có claim:

```json
{
  "sub": "checkout-contract-test",
  "scope": "orders.read",
  "tenant_id": "TENANT-42"
}
```

Trong cách chuyển đổi mặc định của Spring Security Resource Server, scope `orders.read` thường trở thành authority:

```text
SCOPE_orders.read
```

Vì vậy `hasAuthority("SCOPE_orders.read")` phải khớp với converter đang dùng. Nếu dự án có `JwtAuthenticationConverter` tùy biến, prefix hoặc cách lấy claim có thể khác; hãy kiểm tra runtime test configuration, không tự suy từ token string.

### 8.2. Role khác permission và scope

| Cấp độ | Ví dụ | Dùng khi nào |
|---|---|---|
| Role | `ROLE_ADMIN` | Quyền theo nhóm người dùng |
| OAuth2 scope | `orders.read` | Capability của client/token |
| Authority trong Spring Security | `SCOPE_orders.read` | Rule `hasAuthority` |
| Business permission | `CAN_READ_ORDER` | Rule của ứng dụng theo tài nguyên |
| Tenant ownership | `TENANT-42` | Chặn truy cập chéo tenant |
| Resource ownership | `order.ownerId` | Kiểm tra principal sở hữu tài nguyên |

Một role `ADMIN` không tự động có mọi scope nếu application không cấu hình mapping. Một scope `orders.read` cũng không tự động cho phép đọc **mọi tenant**. Các quy tắc nghiệp vụ cần được cài đặt riêng.

## 9. Producer test base: giữ filter chain, giả lập JWT decoder

Đây là phần trung tâm của bài.

Ta muốn generated contract tests gửi HTTP requests như bình thường qua **Spring MockMvc** và bộ lọc bảo mật thật. Nhưng trong CI, không muốn phụ thuộc một Identity Provider bên ngoài chỉ để lấy token thật. Một cách là thay **chỉ JwtDecoder trong test context** bằng decoder kiểm soát fixtures:

- `contract-reader-token` → principal có scope `orders.read`.
- `contract-auditor-token` → principal có scope `orders.audit`.
- Mọi token khác → authentication exception.
- Thiếu token → Spring Security bearer filter xử lý anonymous/401.
- **SecurityFilterChain vẫn giữ nguyên** để thực thi authorization.

Một base test class minh họa:

```java
package com.example.order.contract;

import io.restassured.module.mockmvc.RestAssuredMockMvc;
import org.junit.jupiter.api.BeforeEach;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Import;
import org.springframework.context.annotation.Primary;
import org.springframework.security.oauth2.jwt.BadJwtException;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.test.web.servlet.MockMvc;

import java.time.Instant;

@SpringBootTest
@AutoConfigureMockMvc(addFilters = true)
@Import(OrderContractTestBase.ContractJwtDecoderConfig.class)
public abstract class OrderContractTestBase {

    @Autowired
    MockMvc mockMvc;

    @Autowired
    OrderContractFixture fixture;

    @BeforeEach
    protected void beforeContractTest() {
        fixture.resetOrders();
        fixture.insertPaidOrder(
            "ORDER-42",
            "TENANT-42",
            125000
        );
        fixture.ensureAbsent("ORDER-MISSING");

        RestAssuredMockMvc.mockMvc(mockMvc);
    }

    @TestConfiguration
    static class ContractJwtDecoderConfig {

        @Bean
        @Primary
        JwtDecoder contractJwtDecoder() {
            return token -> {
                final String scope;
                final String subject;

                if ("contract-reader-token".equals(token)) {
                    scope = "orders.read";
                    subject = "checkout-contract-test";
                } else if ("contract-auditor-token".equals(token)) {
                    scope = "orders.audit";
                    subject = "audit-contract-test";
                } else {
                    throw new BadJwtException(
                        "Token not accepted by contract test decoder"
                    );
                }

                return Jwt.withTokenValue(token)
                    .header("alg", "RS256")
                    .subject(subject)
                    .claim("scope", scope)
                    .claim("tenant_id", "TENANT-42")
                    .issuedAt(Instant.parse("2025-01-01T00:00:00Z"))
                    .expiresAt(Instant.parse("2035-01-01T00:00:00Z"))
                    .build();
            };
        }
    }
}
```

**Ví dụ học tập cần ghép vào project thật:**

- `OrderContractFixture` là helper do producer tự cài đặt, không có sẵn trong Spring Cloud Contract.
- `JwtDecoder` test double chấp nhận **chuỗi giả**, không kiểm chứng chữ ký JWT, issuer, audience hoặc key rotation.
- `@Primary` giúp test context ưu tiên decoder này nếu có nhiều beans; cũng cần kiểm tra không khởi tạo decoder thứ hai từ cấu hình issuer-uri/JWK discovery không mong muốn.
- Test profile phải được cô lập khỏi production deployment; decoder giả không được đưa vào source set/runtime chính.
- `RestAssuredMockMvc.mockMvc(mockMvc)` cấu hình adapter dùng trong generated tests ở mode `MOCKMVC`; mode khác cần setup khác.
- Thời hạn `2035` là fixture minh họa, không có ý nghĩa với kiểm tra expiry thực. Nếu cần test expiry, sử dụng decoder/validator thực trong **security integration test**.
- Code cần có Spring Security OAuth2 Resource Server, Spring Test, RestAssured MockMvc và Spring Cloud Contract Verifier dependencies tương thích.

### 9.1. Decoder giả là một điểm thay thế có chủ đích

Nhìn đường đi của request:

```mermaid
flowchart LR
    A[Generated producer test] --> B[RestAssuredMockMvc]
    B --> C[MockMvc + security filters]
    C --> D[BearerTokenAuthenticationFilter]
    D --> E[JwtDecoder test-only]
    E --> F[Spring Security authorities]
    F --> G[AuthorizationManager / method security]
    G --> H[Controller thật + service thật]
    H --> I[HTTP response được verify]
```

Ta **không mock toàn bộ filter chain**, không mock controller để trả sẵn JSON, không đặt một `SecurityContext` toàn cục cho mọi test. Chỉ rút ngắn bước xác minh cryptographic token để kiểm tra những hành vi contract liên quan đến authentication outcome/authorization.

### 9.2. Vì sao không dùng token thật?

Một token thật từ Identity Provider có thể:

- Hết hạn sau vài phút, làm CI flaky.
- Yêu cầu network gọi tới IdP hoặc JWKS endpoint.
- Được cấp với quyền/tenant không ổn định giữa các môi trường.
- Lộ vào source, test reports, logs, stubs archive hoặc request journal.
- Khiến producer tests phụ thuộc state ngoài API implementation.

**Test fixtures không chứa bí mật** tốt hơn cho test hợp đồng có thể lặp lại. Tuy nhiên, cần thêm integration suite riêng để xác nhận cơ chế JWT/OAuth2 thật.

### 9.3. Không vô hiệu toàn bộ Spring Security trong contract test

Một cách làm nguy hiểm:

```java
@AutoConfigureMockMvc(addFilters = false)
```

Nếu tắt filters, request không có token có thể đi thẳng đến controller. Trường hợp tệ hơn: nhóm chỉ tạo contract `200` có token và generated test vẫn pass dù header đó không được kiểm tra.

Các cách tương tự cần cẩn trọng:

- `MockMvcBuilders.standaloneSetup(controller)` nhưng không thêm security filters.
- Test profile `permitAll()` cho `/api/**`.
- `@WithMockUser` được áp dụng toàn bộ base class khiến cả test anonymous cũng có principal.
- Mock method `OrderAuthorizationService.canRead()` luôn trả true.
- Stub controller/service trả `200` mà không đi qua implementation thật.

**Mutation test tốt:** tạm xóa/đổi một rule security trong nhánh thử nghiệm và xác nhận generated tests thích hợp fail. Nếu không fail, test chưa bảo vệ quyền như mong đợi.

## 10. `@WithMockUser` và `jwt()` giúp gì, giới hạn ở đâu?

Spring Security Test có các tiện ích như `@WithMockUser`, `user()` và `jwt()`. Chúng rất hữu ích, nhưng không luôn phù hợp với việc kiểm thử **HTTP bearer authentication** qua contract.

### 10.1. `@WithMockUser` đặt SecurityContext, không tạo bearer token thật

Ví dụ:

```java
@WithMockUser(
    username = "reader",
    authorities = "SCOPE_orders.read"
)
@Test
void canReadOrder() {
    // ...
}
```

Điều này hữu ích khi kiểm thử business authorization hoặc controller với một principal có sẵn. Nó **không chứng minh**:

- Request `Authorization` được parse đúng.
- JWT decoder từ chối token giả mạo.
- Issuer/audience/signature được xác minh.
- Mất header Authorization sẽ gây 401.

Không áp dụng `@WithMockUser` trên mọi generated test trong base class nếu còn các contract cases **không xác thực**; một principal giả tồn tại sẵn có thể khiến `401` không được kiểm tra đúng.

### 10.2. Request post-processor `jwt()`

Một test MockMvc viết thủ công có thể dùng:

```java
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.jwt;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.status;

@Test
void readerWithScopeCanAccess() throws Exception {
    mockMvc.perform(
        get("/api/orders/ORDER-42")
            .with(jwt().authorities(
                new SimpleGrantedAuthority("SCOPE_orders.read")
            ))
    ).andExpect(status().isOk());
}
```

`jwt()` giúp cài authentication object cho MockMvc request; nó thường **bỏ qua JWT decoder** thay vì gửi bearer token thực để decoder parse. Đó là công cụ tốt cho **authorization rule test**, nhưng không tự xác minh authentication filter/token parsing.

Đoạn trên là **minh họa**, cần imports của JUnit, MockMvc, `SimpleGrantedAuthority` và Spring Security Test phù hợp.

### 10.3. Khi nào chọn cách nào?

| Cách setup | Mục tiêu | Giới hạn |
|---|---|---|
| `@WithMockUser` | Unit/controller/method-security test với principal được đặt sẵn | Không kiểm tra Authorization header/token |
| `jwt()` request post-processor | MockMvc authorization test theo claims/authorities | Không kiểm tra JWT signature/decoder |
| Test `JwtDecoder` + filter chain thật | Producer contract tests với Bearer header giả và authorization thật | Không kiểm tra crypto token |
| Test IdP/JWKS local/real integration | Chữ ký, issuer, audience, expiry, key rotation | Tốn hạ tầng/test setup |
| Stub Runner/WireMock | Consumer gửi header và xử lý stub response | Không có production auth enforcement |

Chọn **điểm thay thế nhỏ nhất** đáp ứng mục tiêu test. Càng mock sâu vào authorization policy, test càng dễ bỏ qua chính hành vi cần bảo vệ.

## 11. Dùng `@WebMvcTest` có đủ không?

`@WebMvcTest` thường chỉ nạp một lát cắt web layer, có thể phù hợp với controller contract tests nhanh. Nhưng khi dự án có custom `SecurityFilterChain`, method security, tenant policy hoặc dependencies phức tạp, slice test có thể không nạp tất cả những gì production dùng.

Một số nguy cơ:

- Security configuration bị loại khỏi slice ngoài ý muốn.
- Bean `OrderAccessPolicy` không được nạp; test mock nó và vô tình luôn cho phép.
- Method security proxy không hoạt động đúng như ứng dụng đầy đủ.
- Exception handler, filter hoặc argument resolver khác production.
- Controller mock trả dữ liệu mà không kiểm tra database owner/tenant.

Có thể dùng `@WebMvcTest` **nếu đã chứng minh** slice bao gồm các filter/rule cần verify. Với hợp đồng bảo mật liên quan dữ liệu/tenant, `@SpringBootTest` cộng `@AutoConfigureMockMvc(addFilters=true)` thường giúp gần integration behavior hơn, dù chạy chậm hơn.

**Không có một annotation nào tự đảm bảo an toàn.** Phải xem generated test source và hành vi thực tế khi thử thiếu token hoặc thiếu scope.

## 12. Ví dụ kiểm tra độc lập bằng MockMvc trước khi chạy Verifier

Trước khi chạy generated contract suite, có thể viết một JUnit test kiểm tra chính setup được dùng:

```java
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.status;

@Test
void anonymousRequestIsRejected() throws Exception {
    mockMvc.perform(
        get("/api/orders/ORDER-42")
            .header("Accept", "application/json")
    ).andExpect(status().isUnauthorized());
}

@Test
void auditorTokenIsForbidden() throws Exception {
    mockMvc.perform(
        get("/api/orders/ORDER-42")
            .header("Authorization",
                "Bearer contract-auditor-token")
    ).andExpect(status().isForbidden());
}

@Test
void readerTokenIsAllowed() throws Exception {
    mockMvc.perform(
        get("/api/orders/ORDER-42")
            .header("Authorization",
                "Bearer contract-reader-token")
    ).andExpect(status().isOk());
}
```

Đây là **test methods cần đặt trong một JUnit class có Spring context và inject MockMvc**, không phải file biên dịch độc lập. Chúng có thể kiểm tra test decoder + security filter chain trước khi đổ lỗi cho Contract DSL.

Nếu anonymous request bất ngờ trả `200`, hãy dừng lại để điều tra filter chain có được áp dụng hay không, chứ đừng viết lại contract `401` thành `200` để test xanh.

### 12.1. Với OAuth2 resource server, 401 và 403 diễn ra ở đâu?

Một cách hình dung:

- Thiếu bearer token: request bị auth entry point/challenge trả `401` khi endpoint yêu cầu authentication.
- Bearer token không được decoder chấp nhận: authentication thất bại, thường `401`.
- Bearer token được decoder chấp nhận nhưng thiếu scope: request authenticated, authorization manager trả `403`.
- Có đủ scope nhưng business policy từ chối: có thể `403` hoặc `404` theo chính sách resource-level.

**Không trả `500` vì một JWT thiếu quyền.** Các exception mappings cho security nên được cấu hình/test riêng để không biến một lỗi thông thường thành internal server error.

## 13. Authorization theo tenant và từng tài nguyên

HTTP `403` do thiếu scope mới chỉ là kiểm tra thô. Trong hệ thống nhiều tenant, một principal có `orders.read` có thể chỉ được xem **đơn hàng thuộc tenant của nó**.

Ví dụ:

| Order ID | Tenant sở hữu | Reader tenant | Kết quả |
|---|---|---|---|
| `ORDER-42` | `TENANT-42` | `TENANT-42` | `200` |
| `ORDER-99` | `TENANT-99` | `TENANT-42` | `403` hoặc `404` theo policy |
| `ORDER-MISSING` | Không tồn tại | `TENANT-42` | `404` |

Nếu policy cho phép che giấu tài nguyên không thuộc tenant, response `404` có thể được chọn để tránh tiết lộ ID tồn tại. **Contract phải phản ánh quyết định thiết kế đã được review**, không dùng `404` mặc định của WireMock làm bằng chứng security.

### 13.1. Method security có thể kiểm tra business policy

Ví dụ một service method:

```java
@PreAuthorize("@orderAccessPolicy.canRead(authentication, #orderId)")
public OrderDto getOrder(String orderId) {
    return orderRepository.findById(orderId)
        .map(orderMapper::toDto)
        .orElseThrow(OrderNotFoundException::new);
}
```

Đoạn này chỉ hoạt động theo ý định nếu:

- `@EnableMethodSecurity` được bật khi dùng method authorization theo Spring Security version.
- Bean `orderAccessPolicy` là implementation thật hoặc test double có dữ liệu rõ.
- Proxy/interceptor method security thực sự được áp dụng.
- `orderRepository` và `orderMapper` được cấu hình.
- Controller chuyển `orderId` đúng vào method.
- Exception handlers chuyển access denied/not found thành status đã cam kết.

**Không mock `orderAccessPolicy.canRead()` luôn trả true** rồi kết luận đã kiểm tra tenant isolation.

### 13.2. Contract test quyền theo tài nguyên

Một DSL minh họa với hai tenant:

```yaml
name: checkout_cross_tenant_order_forbidden_403
request:
  method: GET
  url: /api/orders/ORDER-99
  headers:
    Accept: application/json
    Authorization: 'Bearer contract-reader-token'
response:
  status: 403
```

Điều kiện: base fixture tạo `ORDER-99` thuộc `TENANT-99` trong khi `contract-reader-token` mang tenant `TENANT-42`; business policy từ chối và API quy định trả `403`.

Nếu chính sách quy định trả `404` để che giấu sự tồn tại tài nguyên, hãy thay status trong contract cho đúng chính sách đó, không viết `403` theo thói quen.

### 13.3. Test cần chứng minh ngăn truy cập chéo tenant

Ngoài status, kiểm tra không có side effect nguy hiểm:

- Không trả bất kỳ trường PII của tenant khác.
- Không tạo access log chứa dữ liệu nhạy cảm ngoài chính sách.
- Không cập nhật trạng thái đơn hàng khi caller bị từ chối.
- Không suy ra tài nguyên tồn tại qua lỗi phân biệt quá chi tiết nếu hệ thống yêu cầu che giấu.
- Không sử dụng ownerId/tenantId do request body tự khai báo như bằng chứng quyền mà chưa xác thực.

Những yêu cầu này có thể cần **integration/security tests ngoài Contract DSL**, đặc biệt khi cần assert dữ liệu database không bị thay đổi.

## 14. Kiểm tra `401`, `403` và error response body

Một hệ thống có thể công bố error envelope riêng:

```json
{
  "code": "FORBIDDEN",
  "message": "Access denied",
  "traceId": "TRACE-TEST-42"
}
```

Tuy nhiên, **Spring Security mặc định không bảo đảm** mọi `401` hoặc `403` sẽ có JSON body theo format đó. Nếu nhóm muốn error envelope nhất quán, phải cài đặt:

- AuthenticationEntryPoint cho `401`.
- AccessDeniedHandler cho `403`.
- Exception handling phù hợp cho business `404`.
- Content-Type và header challenge theo policy.
- Log/redaction an toàn.

Chỉ khi implementation thực sự trả body trên, mới viết contract yêu cầu `code=FORBIDDEN`.

### 14.1. Ví dụ error contract có custom handler

```groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    name 'checkout_insufficient_scope_json_403'

    request {
        method GET()
        url '/api/orders/ORDER-42'
        headers {
            header 'Authorization', 'Bearer contract-auditor-token'
        }
    }

    response {
        status FORBIDDEN()
        headers {
            contentType(applicationJson())
        }
        body(
            code: 'FORBIDDEN',
            message: 'Access denied'
        )
    }
}
```

**Điều kiện bắt buộc:** producer có custom `AccessDeniedHandler` hoặc cơ chế xử lý tương đương trả JSON này. Nếu chưa cấu hình, hãy dùng hợp đồng chỉ assert `403` thay vì tạo một contract “đẹp” nhưng không khớp implementation.

### 14.2. Tránh contract leak nội bộ qua body lỗi

Error body không nên tiết lộ:

- JWT claims đầy đủ.
- Danh sách roles/permissions nội bộ của resource.
- Stack trace hoặc tên class Spring Security.
- Database keys, địa chỉ máy hoặc thông tin cấu hình.
- Chi tiết phân biệt tenant/resource existence khi policy cần che giấu.

Thông điệp lỗi giúp consumer xử lý đúng, nhưng không nên làm API lộ bí mật.

## 15. Cẩn trọng với `Authorization` trong generated WireMock stubs

Một hợp đồng producer có:

```http
GET /api/orders/ORDER-42
Authorization: Bearer contract-reader-token
```

có thể sinh WireMock mapping **chỉ so khớp header**:

```json
{
  "request": {
    "method": "GET",
    "url": "/api/orders/ORDER-42",
    "headers": {
      "Authorization": {
        "equalTo": "Bearer contract-reader-token"
      }
    }
  },
  "response": {
    "status": 200,
    "headers": {
      "Content-Type": "application/json"
    },
    "jsonBody": {
      "id": "ORDER-42",
      "status": "PAID",
      "totalAmount": 125000
    }
  }
}
```

Đây là **WireMock JSON mapping minh họa**, không phải output đã sinh thật từ plugin version cụ thể. Khi request khớp exact header, WireMock trả response đã định nghĩa. Nó **không xác minh chữ ký JWT**, issuer, expiry hoặc tenant ownership.

### 15.1. Tại sao dễ có false positive?

Giả sử mapping `401` không khai báo Authorization matcher. Nếu WireMock nhận cùng URL với token reader, cả `401` và `200` mappings có thể khớp khi xét các điều kiện hiện có; kết quả có thể phụ thuộc mapping priority/đăng ký.

Cần:

1. Xem file JSON mapping được **sinh thật** trong stubs JAR.
2. Kiểm tra request matcher cho từng scenario.
3. Dùng mapping có điều kiện **Authorization absent** nếu version và mục tiêu test yêu cầu.
4. Dùng priority có chủ đích khi cùng path tồn tại nhiều mapping.
5. Hoặc tách server/test scopes để không nạp các mappings mâu thuẫn.
6. Chạy consumer smoke test với reader token, auditor token và không có token.

**Một response `401` từ WireMock vì không khớp stub không chứng minh producer authentication hoạt động đúng.** Trong nhiều trường hợp unmatched request cũng trả `404`, không phải `401`.

### 15.2. Tránh matcher bảo mật quá rộng

Không nên để consumer stub nhận:

```json
{
  "Authorization": {
    "matches": ".*"
  }
}
```

nếu bài test cần bảo vệ “client gửi Bearer scheme”. Regex này có thể match cả chuỗi không hợp lệ. Một matcher `Bearer .+` chỉ chứng minh đúng **hình dạng header**, không chứng minh token thật hợp lệ.

Với consumer stub tests, mục tiêu thường là **client đặt header đúng và xử lý HTTP responses**. Với producer auth tests, mục tiêu là **filter chain và authorization behavior**. Với real auth integration tests, mục tiêu là **chữ ký/claims/IdP/JWKS**.

## 16. Không đưa bí mật thật vào contract hoặc stubs artifact

Nguyên tắc tối thiểu:

| Thứ | Có thể nằm trong contract? | Ghi chú |
|---|---|---|
| `Bearer contract-reader-token` giả | **Có**, cho test | Không được chấp nhận bởi production decoder |
| JWT thật của production user | **Không** | Credential nhạy cảm và có hạn sử dụng |
| API key thật | **Không** | Có thể bị lộ qua Git/stubs JAR |
| Private signing key | **Không** | Phải giữ trong secret vault/test PKI chuyên dụng |
| Fake tenant ID `TENANT-42` | **Có** | Dữ liệu giả không nhận diện người dùng thật |
| Customer PII thật | **Không** | Không đưa vào fixture/artifact |
| Test public key không nhạy cảm | Có thể | Quản lý theo yêu cầu test PKI |
| Test private key | Chỉ khi đáp ứng security policy riêng | Không để lộ trong public artifact hoặc logs |
| Token được nhận qua CI secrets | Không ghi vào contracts | Chỉ inject cho integration tests được phép |

### 16.1. Artifact stubs thường có phạm vi chia sẻ rộng

Một stubs JAR có thể đi từ producer CI lên Maven artifact repository, rồi tới nhiều consumer pipelines. Nếu contract chứa real bearer token, **bất cứ ai được quyền đọc artifact cũng có thể xem token**.

Cần:

- Ghim fixtures giả có ý nghĩa nhưng không nhạy cảm.
- Quét secret trước commit/publish.
- Không echo Authorization headers vào CI logs.
- Redact token/cookie trong request journal.
- Dùng quyền tối thiểu cho Maven repository và CI runners.
- Không dùng test JWT decoder trong runtime production.
- Có quy trình vô hiệu hóa/rotate credentials nếu đã lộ.

### 16.2. Test log có thể là một kênh rò rỉ

RestAssured, MockMvc hoặc WireMock request/response logging đôi khi in nguyên headers. Nếu test fail, log có thể giữ bearer token lâu hơn vòng đời request. Hãy log thông tin cần thiết như request ID, status, scope test case và correlation ID; không log raw credentials.

Trong ví dụ bài học, token strings là giá trị **không nhạy cảm** để minh họa, nhưng chính sách redaction vẫn cần được áp dụng cho các bài tích hợp dùng secrets thật.

## 17. Các loại xác thực khác: Basic, API key, session và mTLS

Không phải mọi producer dùng JWT bearer. Spring Cloud Contract chỉ mô tả **HTTP request–response được thỏa thuận**, không tự quyết định cơ chế authentication.

### 17.1. HTTP Basic

Header dạng:

```http
Authorization: Basic <base64-of-username-colon-password>
```

`Basic` chỉ mã hóa Base64, **không mã hóa bí mật**. Nếu cần test Basic auth, dùng credentials **giả** và test security configuration riêng; HTTPS vẫn là bắt buộc trong hệ thống thật. Không đưa password thật vào DSL.

### 17.2. API key

Ví dụ:

```http
X-API-Key: contract-api-key
```

Một contract có thể kiểm tra client gửi header và producer từ chối khi thiếu key. Nhưng nếu authentication filter được mock bỏ qua, header xuất hiện trong DSL **không chứng minh** key validation thực.

### 17.3. Session cookie và CSRF

Với trình duyệt dùng cookie-session:

- Authentication có thể dựa vào `JSESSIONID` hoặc session mechanism khác.
- POST/PUT/DELETE có thể cần CSRF token.
- `403` có thể do CSRF, không phải role thiếu.
- Cookies cần thuộc tính `Secure`, `HttpOnly`, `SameSite` theo policy.
- CORS cần kiểm tra bằng request Origin/preflight trong test riêng.

Không dùng bearer-token fixture để suy kết quả cho cookie-session application.

### 17.4. Mutual TLS (mTLS)

mTLS diễn ra ở **TLS handshake** trước hoặc ngoài tầng HTTP controller. Một contract DSL với header `X-Client-Cert` không thể chứng minh client certificate đã được xác minh bởi ingress/proxy. Cần môi trường tích hợp có TLS/client certificate và reverse proxy/gateway phù hợp.

## 18. Scope, role và ownership cần ma trận test rõ

Một lỗi thường gặp là chỉ kiểm tra “admin được phép” rồi coi phân quyền đã đủ. Hãy lập ma trận:

| Principal | Scope | Owner tenant | Resource tenant | Expected |
|---|---|---|---|---|
| Checkout reader | `orders.read` | `TENANT-42` | `TENANT-42` | `200` |
| Auditor | `orders.audit` | `TENANT-42` | `TENANT-42` | `403` |
| Checkout reader | `orders.read` | `TENANT-42` | `TENANT-99` | `403/404` theo policy |
| Anonymous | Không có | — | `TENANT-42` | `401` |
| Invalid bearer | Không xác thực | — | `TENANT-42` | `401` |
| Reader, order missing | `orders.read` | `TENANT-42` | Không tồn tại | `404` |

Test cases phải phân biệt:

1. **Authentication failed**.
2. **Authentication success nhưng thiếu capability**.
3. **Có capability nhưng thiếu quyền trên tài nguyên cụ thể**.
4. **Có quyền nhưng tài nguyên không tồn tại**.

Nếu chỉ assert `403` trong các trường hợp này, một lỗi auth/fixture có thể bị che lấp.

### 18.1. Kiểm tra “deny by default”

Khi có endpoint mới, nếu security configuration dùng:

```java
.anyRequest().permitAll()
```

một route mới có thể vô tình mở công khai. Nên dùng policy rõ và kiểm tra **negative tests** cho resource nhạy cảm. Một lựa chọn phù hợp với nhiều APIs là:

```java
.anyRequest().authenticated()
```

nhưng điều đó vẫn **không đồng nghĩa đã kiểm tra authorization theo scope/resource**. Các endpoints cần permission khác nhau phải có rules cụ thể.

Không tự áp dụng một rule tổng quát vào toàn hệ thống mà chưa xét public health endpoints, authentication callback routes hoặc static resources; mẫu trên chỉ để minh họa nguyên tắc.

## 19. Producer Contract Verifier và test runner: đảm bảo tests thật sự chạy

Trong Maven producer, một cấu hình plugin thường bao gồm:

```xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-contract-verifier</artifactId>
    <scope>test</scope>
</dependency>
```

Và build plugin:

```xml
<plugin>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-contract-maven-plugin</artifactId>
    <version>CONTRACT_PLUGIN_VERSION_PHU_HOP</version>
    <extensions>true</extensions>
    <configuration>
        <baseClassForTests>
            com.example.order.contract.OrderContractTestBase
        </baseClassForTests>
        <testMode>MOCKMVC</testMode>
        <testFramework>JUNIT5</testFramework>
    </configuration>
</plugin>
```

Đây là **POM fragments**; để chạy cần Spring Boot/Cloud/Contract versions tương thích, test runtime, Security/OAuth2 Resource Server dependencies và parent/BOM phù hợp. `CONTRACT_PLUGIN_VERSION_PHU_HOP` là placeholder, không phải version thực.

### 19.1. Các bước kiểm tra trên Maven

```bash
./mvnw -version
./mvnw -B -ntp clean verify

# Kiểm tra mã generated test và reports thực tế.
find target/generated-test-sources/contracts -type f -print
find target/surefire-reports -type f -name 'TEST-*.xml' -print
```

Các paths trên phổ biến trong Maven plugin, nhưng có thể khác theo version/configuration. Trong multi-module, cần chạy lệnh ở đúng producer module và kiểm tra reports đúng module.

**Bằng chứng cần có:**

- Có generated test cho `200`, `401`, `403`, `404`.
- Test classes kế thừa đúng `OrderContractTestBase`.
- MockMvc/request adapter sử dụng filters tương ứng.
- Tests thực thi, không bị `skipTests` hoặc exclude.
- Test reports ghi failures/errors/skips rõ.
- Có số generated contract tests như kỳ vọng, không chỉ “0 test nhưng BUILD SUCCESS”.

### 19.2. Không sửa generated test trong `target`

Khi test fail vì security, hãy sửa:

- Contract nếu contract mô tả sai hành vi đã thỏa thuận.
- Security configuration hoặc implementation nếu producer thực sự sai.
- Test-only JwtDecoder/fixture nếu setup sai.
- Test mode/base class nếu generated request không qua filter chain.
- Plugin/dependency nếu generation/compilation sai.

Không chỉnh tay Java files trong `target/generated-test-sources`; chúng sẽ bị ghi đè trong lần build sau.

## 20. Mutation test: chứng minh filter và authorization rule không bị bypass

Một cách mạnh để phát hiện test giả an toàn là **cố ý làm sai implementation trong một nhánh thử nghiệm**, rồi xem contract tests có fail đúng nguyên nhân không.

### 20.1. Mutation 1 — bỏ yêu cầu authentication

Giả sử một developer thay rule:

```java
.requestMatchers(HttpMethod.GET, "/api/orders/**")
    .permitAll()
```

thay vì:

```java
.requestMatchers(HttpMethod.GET, "/api/orders/**")
    .hasAuthority("SCOPE_orders.read")
```

Kỳ vọng:

- Test `200` với reader token có thể vẫn pass.
- Test `401` anonymous **phải fail** nếu filter/route thực sự đang được kiểm tra.
- Test `403` auditor **phải fail** khi endpoint bị mở quá rộng.

Nếu cả `401` và `403` vẫn pass dù route đã `permitAll()`, hãy kiểm tra response có bị mock trả sẵn, security rule khác có chặn request hoặc generated tests có thật sự chạy không.

### 20.2. Mutation 2 — bỏ kiểm tra tenant

Nếu code xóa `orderAccessPolicy.canRead(authentication, orderId)`, test cross-tenant phải fail khi một principal của `TENANT-42` có thể lấy `ORDER-99` thuộc `TENANT-99`.

Nếu contract chỉ assert `200` happy path, sẽ không có bằng chứng chặn truy cập xuyên tenant.

### 20.3. Mutation 3 — decoder chấp nhận mọi token

Nếu test decoder vô tình luôn trả principal reader cho mọi chuỗi:

```java
return token -> createReaderJwt(token);
```

thì test invalid-token `401` phải fail. Nhưng lưu ý: test decoder **vốn dĩ không chứng minh cryptographic validation**. Mutation chỉ kiểm tra contract test setup phân biệt test credentials, không thay thế real JWT integration tests.

## 21. Spring Cloud Contract Stub Runner nhìn nhận security ra sao?

Producer phát hành stubs JAR từ contracts đã verified. Consumer có thể cấu hình:

```java
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cloud.contract.stubrunner.spring.AutoConfigureStubRunner;
import org.springframework.cloud.contract.stubrunner.spring.StubRunnerProperties;

@SpringBootTest(
    properties = "clients.orders.base-url=http://localhost:8085"
)
@AutoConfigureStubRunner(
    ids = "com.example:order-service:1.4.0:stubs:8085",
    stubsMode = StubRunnerProperties.StubsMode.LOCAL
)
class CheckoutOrderClientContractTest {
    // Inject OrderClient thực của Checkout.
    // Verify Authorization header và xử lý 200/401/403/404.
}
```

**Đây là test configuration minh họa**, không phải class test độc lập. Property `clients.orders.base-url` do Checkout tự định nghĩa. Cổng `8085` thuộc stub HTTP server, không phải Maven artifact identity.

### 21.1. Consumer nên xác minh những gì?

- Client thật gửi header `Authorization` theo cơ chế được cấu hình.
- Client không vô tình bỏ tiền tố `Bearer `.
- Với response `401`, client phân loại là unauthenticated và xử lý refresh/login/propagation đúng policy.
- Với response `403`, client không retry mù hoặc báo `404` giả.
- Với response `404` nghiệp vụ, client xử lý `ORDER_NOT_FOUND`.
- Không log raw token.
- Không retry vô hạn request bị `401/403`.
- Nếu token acquisition là một service khác, client có test integration riêng cho quy trình lấy token.

**Không lấy kết quả xanh của WireMock để kết luận production JWT signature validation an toàn.** Stub Runner dùng HTTP mappings, không chạy Spring Security filter chain của Order Service.

### 21.2. Stub mappings có thể cần chỉnh để tránh trùng

Các contract cases dùng cùng URL nhưng khác headers, do đó cần inspect generated WireMock mappings, đặc biệt **anonymous `401`** và **reader `200`**. Nếu generated mapping không thể biểu đạt absent Authorization với DSL đã chọn, có thể:

1. Tách consumer tests theo server/mappings được nạp.
2. Dùng WireMock custom mapping cho `401` có absent-header matcher.
3. Dùng priority được cấu hình rõ.
4. Sử dụng kịch bản request khác khi đúng phạm vi hợp đồng.
5. Xác minh generated producer tests vẫn bảo vệ API, không làm lỏng contract vì stub conflict.

Không tự sửa generated mapping rồi quên lần package tiếp theo sẽ ghi đè; nếu phải tùy biến, quản lý custom mapping và packaging rõ theo version/plugin.

## 22. Message security: không nhầm HTTP auth với broker authorization

Order Service có thể phát event `ORDER_PAID` cho Billing:

```groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    name 'billing_order_paid_v1'
    label 'billing_order_paid_event_v1'

    input {
        triggeredBy('publishOrderPaid()')
    }

    outputMessage {
        sentTo('orders.events')
        headers {
            header('contentType', 'application/json')
            header('eventType', 'ORDER_PAID')
        }
        body(
            eventId: 'EVENT-42',
            eventType: 'ORDER_PAID',
            orderId: 'ORDER-42'
        )
    }
}
```

Producer message contract có thể xác minh **destination, header và payload** của message được phát qua test binder/broker. Nhưng nó **không tự xác minh**:

- Kafka ACL/SASL hoặc RabbitMQ permissions thật.
- TLS/mTLS đến broker.
- Consumer group có quyền subscribe topic/queue.
- Dữ liệu message được mã hóa/signature theo chính sách.
- Broker không cho publisher trái phép gửi events.
- Secret rotation/certificate expiry.

Một test binder in-memory có thể rất hữu ích cho contract tests, nhưng cần **broker security integration tests** riêng khi producer chạy qua middleware thực.

### 22.1. Không nhúng access token trong event

Message thường không nên mang raw access token của user trong body/header trừ khi có threat model và yêu cầu đặc biệt được review. Producer contract nên dùng event ID, actor ID giả, correlation ID và những claims nghiệp vụ tối thiểu cần thiết. Đừng biến broker thành nơi phân phối bearer tokens thông qua stubs JAR.

## 23. CI: producer security contract verification

Một pipeline producer có thể như sau:

```mermaid
flowchart TD
    A[Review Groovy/YAML auth contracts] --> B[Kiểm tra test fixtures không có secrets thật]
    B --> C[Generate producer tests]
    C --> D[Spring TestContext + security filter chain]
    D --> E[Test decoder và dữ liệu tenant có kiểm soát]
    E --> F[Chạy cases 200, 401, 403, 404]
    F --> G{Generated tests thực sự chạy và đạt?}
    G -- Không --> H[Fail build / sửa security hoặc fixture]
    G -- Có --> I[Convert mappings + package stubs]
    I --> J[Kiểm tra archive, classifier, không có secret]
    J --> K[Publish verified stubs theo quyền]
    K --> L[Consumer Stub Runner tests]
    L --> M[CI compatibility gate]
```

### 23.1. Checklist CI

- [ ] Contract nguồn mô tả rõ authorized/unauthenticated/forbidden/resource-not-found cases.
- [ ] Spring Security filters được bật trong producer contract test.
- [ ] Test decoder chỉ tồn tại trên test classpath/profile.
- [ ] Test decoder chỉ chấp nhận những fixture tokens đã định nghĩa.
- [ ] Authorization scope/role mapping khớp policy thực của producer.
- [ ] Tenant/object-level checks có test riêng khi cần.
- [ ] `401` được phân biệt với `403` và `404`.
- [ ] `WWW-Authenticate` và error body được assert nếu thuộc hợp đồng.
- [ ] Generated producer tests thực thi, không bị skip.
- [ ] Surefire/Failsafe reports ghi số tests/failures rõ.
- [ ] Có negative test để phát hiện security filter bị vô hiệu.
- [ ] Không có token/API key/PII thật trong source, logs và stubs artifact.
- [ ] Stubs JAR cùng build/version với producer đã verification.
- [ ] Consumer Stub Runner tests xử lý auth errors bằng client thật.
- [ ] JWT signature/issuer/audience/JWK tests được kiểm tra trong suite riêng.
- [ ] Broker ACL/TLS/mTLS được kiểm tra ở mức tích hợp nếu hệ thống sử dụng.
- [ ] CI release không publish khi security contract cases fail.
- [ ] Pull request từ nguồn không tin cậy không có quyền đọc deploy secrets.

### 23.2. Maven verification minh họa

```bash
./mvnw -B -ntp clean verify

# Theo dõi kết quả generated tests trong output path của project.
find target/surefire-reports -type f -name 'TEST-*.xml' -print

# Mở danh sách entries trong stubs JAR đúng version.
jar tf target/order-service-1.4.0-stubs.jar
```

Lệnh này chỉ là **hướng dẫn thực hành**. Tên artifact/path, Maven plugin lifecycle và reports phải được kiểm tra theo project. Không dùng `-DskipTests` rồi đánh dấu stubs là verified.

### 23.3. Phân tách pipeline auth contract và auth integration

| Pipeline/test nhóm | Mục tiêu | Thường chạy khi nào? |
|---|---|---|
| Producer contract security | `200/401/403/404`, header/body, permission rules | Mọi PR/merge quan trọng |
| JWT validation integration | Chữ ký, exp/nbf, issuer/audience, JWKS rotation | PR chọn lọc hoặc pipeline security |
| API gateway security | TLS, mTLS, forwarding headers, ingress rules | Integration/staging |
| Browser/session security | CSRF, CORS, cookies, session policies | Web app security suite |
| Broker authorization | SASL/ACL/TLS, topic/queue permissions | Messaging integration |
| Consumer stub security | Client gửi header, map error statuses, không lộ token | Consumer CI |
| Penetration/security audit | Kiểm tra rủi ro ngoài kịch bản contracts | Theo lịch chính sách bảo mật |

**Contract tests là một tầng kiểm soát**, không phải chứng chỉ rằng toàn bộ hệ thống an toàn.

## 24. Các lỗi thường gặp và cách chẩn đoán

| Triệu chứng | Nguyên nhân có thể | Bước điều tra |
|---|---|---|
| Không có token vẫn nhận `200` | Filters bị tắt hoặc route `permitAll` | `addFilters`, SecurityFilterChain và mutation test |
| Reader token nhận `401` | Test decoder không được nạp hoặc token không khớp | `JwtDecoder` bean, fixture string, logs đã redact |
| Auditor token nhận `401` thay vì `403` | Decoder từ chối token | Phân biệt accepted token và missing scope |
| Reader token nhận `403` | Scope → authority mapping sai | Kiểm tra `SCOPE_orders.read` và converter |
| Cross-tenant request nhận `200` | Thiếu object-level policy | `OrderAccessPolicy` và fixture tenant |
| Cross-tenant trả `404` thay vì `403` | Chính sách ẩn tài nguyên hoặc mapper | Đối chiếu contract API policy |
| `403` khi POST trong session app | CSRF token thiếu | Kiểm tra CSRF setup, không kết luận role thiếu |
| API `401` không có JSON body | Default Spring Security entry point | Chỉ assert body nếu có handler thật |
| Generated test luôn pass dù bỏ auth | Mocked controller hoặc pre-seeded principal | Kiểm tra filter chain, `@WithMockUser` và test code |
| Stub Runner trả `401` cho reader token | Anonymous mapping quá rộng | Inspect mapping/priority/absent-header rules |
| Stub Runner trả `404` khi thiếu token | Request không match mapping | Phân biệt WireMock unmatched `404` |
| CI chỉ fail token test | Hard-coded real token đã hết hạn | Dùng test decoder/fixture không nhạy cảm |
| JWT production invalid nhưng test vẫn xanh | Test decoder không kiểm tra crypto | Chạy real JWT integration tests |
| Build xanh với `Tests run: 0` | Plugin/runner không thực thi generated tests | Check test reports, failOnNoContracts |
| Không compile `JwtDecoder` | Thiếu OAuth2 Resource Server dependencies | POM/BOM compatibility |
| `@WithMockUser` làm case 401 pass sai | SecurityContext bị đặt sẵn | Không áp annotation lên anonymous tests |
| Test leak tenant data khi chạy song song | Fixture dùng chung DB | Reset/isolation/correlation IDs |
| Artifact stubs chứa token thật | Contract hoặc logs chứa secret | Secret scan và rotate/revoke credential |

### 24.1. Quy trình debug nhanh

1. Xác định request thực sự gửi header Authorization nào trong **test**, không in token nhạy cảm.
2. Kiểm tra MockMvc có security filters được đăng ký.
3. Kiểm tra test `JwtDecoder` bean có được dùng hay không.
4. Xác nhận token fixture reader/auditor được giải mã thành authorities/tenant đúng.
5. Xác nhận SecurityFilterChain path/method matcher khớp request.
6. Nếu có method security, kiểm tra proxy và business policy.
7. Kiểm tra fixture tài nguyên/tenant.
8. So status và error body thực với DSL.
9. Đọc generated tests và Surefire/Failsafe reports.
10. Với consumer stub failures, kiểm tra WireMock mappings/priority chứ không sửa producer implementation theo suy đoán.

**Không sửa contract `403` thành `200` chỉ để giảm lỗi CI** khi chưa biết test base đang bypass security hay implementation đã mất policy.

## 25. Bài thực hành: bảo vệ Order API bằng contract tests

Bài thực hành kết hợp cả authentication và authorization.

### Giai đoạn A — tạo hợp đồng

1. Tạo Groovy `checkout_get_paid_order_authorized_200`.
2. Tạo YAML `checkout_get_paid_order_unauthenticated_401`.
3. Tạo YAML `checkout_get_paid_order_forbidden_403`.
4. Tạo Groovy `checkout_get_missing_order_authorized_404`.
5. Nếu dùng multi-tenancy, thêm contract từ chối `ORDER-99` cho tenant khác.
6. Chọn response headers/body đúng với API policy thật, không bịa JSON lỗi.

### Giai đoạn B — Spring Security và fixtures

1. Bật `SecurityFilterChain` yêu cầu `SCOPE_orders.read` cho GET orders.
2. Dùng `@SpringBootTest` và `@AutoConfigureMockMvc(addFilters=true)`.
3. Tạo test-only `JwtDecoder` map reader/auditor token giả.
4. Giữ business authorization policy thật, không mock luôn true.
5. Seed `ORDER-42` thuộc `TENANT-42`; `ORDER-99` thuộc `TENANT-99` nếu có.
6. Dọn fixture độc lập trước mỗi generated test.

### Giai đoạn C — xác minh từng case

1. Gửi reader token, assert `200` và body.
2. Bỏ token, assert `401`.
3. Gửi auditor token, assert `403`.
4. Gửi token không được fixture chấp nhận, assert `401`.
5. Dùng reader token với `ORDER-MISSING`, assert `404 ORDER_NOT_FOUND`.
6. Dùng reader token với tài nguyên tenant khác, assert `403` hoặc `404` theo policy.
7. Nếu response khác kỳ vọng, chẩn đoán authn, authz và data riêng.

### Giai đoạn D — kiểm tra khả năng phát hiện lỗi

1. Tạm thay `hasAuthority("SCOPE_orders.read")` bằng `permitAll()` trong nhánh thử nghiệm.
2. Chạy generated contract tests; case anonymous/auditor phải fail khi route bị mở.
3. Khôi phục security rule.
4. Tạm bypass policy kiểm tra tenant; case cross-tenant phải fail.
5. Khôi phục và chạy suite đạt.
6. Xác minh test report có số generated tests đúng, không bị skip.

### Giai đoạn E — đóng gói và consumer Stub Runner

1. Chạy producer verification đúng Maven/Gradle lifecycle.
2. Đóng gói stubs JAR với classifier `stubs`.
3. Kiểm tra archive không chứa real credentials.
4. Inspect generated WireMock mappings khi các cases cùng URL.
5. Consumer dùng Stub Runner và client thật để kiểm tra headers/error mapping.
6. Ghi nhận rằng WireMock không xác minh JWT signature.

### Giai đoạn F — security integration

1. Tạo test với JWKS/IdP giả lập có **chữ ký JWT thật** trong môi trường test riêng.
2. Kiểm tra invalid signature, expired token, invalid issuer/audience theo security policy.
3. Nếu API đi qua gateway, bổ sung ingress/auth forwarding tests.
4. Nếu có cookie session, thêm CSRF/CORS tests.
5. Nếu có broker messaging, kiểm tra ACL/TLS và không để token trong event.
6. Gắn test reports vào CI và chặn release khi security-contract tests fail.

**Tiêu chí hoàn thành:** generated producer tests đi qua security filters và ứng dụng thật, phân biệt đúng `200/401/403/404`, không tiết lộ dữ liệu tenant khác, stubs artifact không có secrets, và nhóm có thể giải thích **vì sao test JWT decoder giả không chứng minh JWT crypto trong production an toàn**.

## 26. Checklist trước khi merge

- [ ] Contracts ghi nhận rõ authorized, anonymous, insufficient-scope và resource-not-found cases.
- [ ] `Authorization` trong contracts chỉ là fixture không nhạy cảm.
- [ ] Test profile không thay đổi production security configuration ngoài điểm giả lập đã phê duyệt.
- [ ] Security filters không bị tắt trong producer contract test.
- [ ] Test decoder chỉ được dùng trong test environment.
- [ ] Reader/auditor tokens có authorities khác nhau, đủ phân biệt `200` và `403`.
- [ ] Không dùng `@WithMockUser` toàn cục cho case anonymous.
- [ ] Có kiểm tra object-level/tenant-level authorization nếu sản phẩm yêu cầu.
- [ ] `401`, `403`, `404` không bị gộp thành một nhóm lỗi.
- [ ] Error body/headers trong contract khớp implementation thật.
- [ ] Generated tests được sinh, biên dịch và thực thi.
- [ ] Có negative/mutation tests chứng minh filter/policy không bị bypass.
- [ ] WireMock mappings có matcher/priority phù hợp khi cùng URL.
- [ ] Stubs JAR không chứa JWT thật, API key, PII hoặc secrets.
- [ ] Consumer client test xử lý HTTP auth errors theo policy.
- [ ] Real JWT/IdP/JWKS validation có test riêng.
- [ ] Session/CSRF/CORS và gateway/mTLS được kiểm tra nếu liên quan.
- [ ] CI lưu reports, artifacts đúng version và không publish khi tests fail.

## 27. Câu hỏi tự kiểm tra

1. **Authentication khác authorization thế nào?** Authentication xác định danh tính; authorization quyết định danh tính được phép làm gì trên tài nguyên nào.
2. **Khi nào trả `401`?** Thường khi không có hoặc không chấp nhận được authentication credentials.
3. **Khi nào trả `403`?** Thường khi principal đã xác thực nhưng không có quyền; cũng có thể do chính sách như CSRF.
4. **`404` có thể dùng để ẩn tài nguyên không được phép xem không?** Có, nếu đó là policy của API.
5. **Vì sao contract `200` có Authorization header chưa chứng minh security hoạt động?** Vì filter chain có thể bị bypass và controller vẫn trả `200`.
6. **`@AutoConfigureMockMvc(addFilters=false)` có nguy cơ gì?** Bỏ các security filters cần kiểm tra.
7. **Test-only JwtDecoder có kiểm chứng JWT signature thật không?** Không, nó chỉ mô phỏng kết quả giải mã.
8. **Vì sao auditor token phải được decoder chấp nhận nhưng thiếu scope?** Để test thực sự đo `403` authorization, không phải `401` authentication.
9. **`scope=orders.read` thường thành authority nào?** `SCOPE_orders.read` trong converter mặc định của Spring Security Resource Server.
10. **Có thể dùng `@WithMockUser` để kiểm chứng Bearer header được parse đúng không?** Không, nó chủ yếu đặt SecurityContext.
11. **`jwt()` request post-processor kiểm tra gì?** Authentication object/authorization path trong MockMvc, không phải chữ ký JWT.
12. **Vì sao không mock business policy luôn true?** Vì làm mất chính kiểm tra phân quyền theo tài nguyên.
13. **Test tenant isolation cần fixture nào?** Hai tài nguyên thuộc hai tenants và principal có tenant cụ thể.
14. **Nếu anonymous request nhận `200`, cần kiểm tra gì?** Filter chain, security rules và generated tests.
15. **Spring Security có tự trả JSON body cho mọi `401/403` không?** Không; có thể cần custom handlers.
16. **`WWW-Authenticate` dùng để làm gì?** Truyền authentication challenge/metadata phù hợp.
17. **Contract không có Authorization header có tự tạo WireMock absent-header matcher không?** Không nên giả định.
18. **Stub Runner có xác minh cryptographic JWT không?** Không; WireMock chủ yếu match request/serve response.
19. **Vì sao không đưa token production vào DSL?** Có thể bị lộ qua Git, logs và stubs artifact.
20. **Dùng JWT giả có cần real JWT integration test nữa không?** Có nếu cần kiểm chứng signature, issuer, audience, expiry và JWKS.
21. **`403` khi POST có chắc do thiếu role không?** Không; trong session app có thể do CSRF.
22. **mTLS có thể được chứng minh bằng một Authorization header không?** Không; cần TLS/proxy integration test.
23. **Generated tests cần bằng chứng nào trong CI?** Source, reports, số tests thực thi và kết quả đạt.
24. **Test mutation security rule giúp gì?** Chứng minh negative contracts thực sự phát hiện endpoint bị mở rộng quyền.
25. **Message contract có tự kiểm chứng Kafka ACL không?** Không; cần broker security integration test.

## 28. Tài liệu tham khảo và giới hạn phiên bản

Tham khảo các tài liệu chính thức, đối chiếu với version Spring Cloud Contract/Spring Security thực tế của dự án:

- [Spring Cloud Contract — Reference](https://docs.spring.io/spring-cloud-contract/reference/)
- [Spring Cloud Contract — Contract DSL](https://docs.spring.io/spring-cloud-contract/reference/)
- [Spring Cloud Contract — Stub Runner](https://docs.spring.io/spring-cloud-contract/reference/)
- [Spring Security — OAuth2 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html)
- [Spring Security — MockMvc Security](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/index.html)
- [Spring Security — Testing with Mock Users](https://docs.spring.io/spring-security/reference/servlet/test/method.html)
- [Spring Security — Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html)
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750)
- [OWASP — API Security Top 10](https://owasp.org/www-project-api-security/)

**Giới hạn phiên bản:** package/imports, tên annotation, test-mode support, cơ chế sinh mappings và claim-to-authority conversion có thể khác giữa các Spring Cloud Contract/Spring Security/Spring Boot versions. Trong các phiên bản Spring Boot/Spring Framework mới, annotations mock bean cũng có thể thay đổi; vì vậy bài ưu tiên `@TestConfiguration` và một test-only decoder minh họa thay vì giả định một `@MockBean` API duy nhất dùng được mọi release train.

Các ví dụ code trong bài hướng dẫn cách thiết kế; **chưa được chạy build trong một producer project cụ thể**. Khi áp dụng, cần kiểm tra generated test source, dependencies, Spring TestContext, security filters và test report đúng với toolchain đã ghim.

## Kết luận

**Giả lập xác thực và phân quyền trong producer test không có nghĩa là vô hiệu hóa bảo mật để request dễ chạy hơn.** Cách tiếp cận đúng là mô phỏng **danh tính/credentials có kiểm soát** bằng fixtures test-only, nhưng vẫn để **Spring Security filter chain, authorization rules, business policy và implementation producer thật** quyết định kết quả. Các contracts cho `200`, `401`, `403`, `404` và truy cập chéo tenant giúp bảo vệ những hành vi mà Checkout/Billing thực sự phụ thuộc.

Kết hợp **Groovy/YAML DSL**, **generated producer verification**, **stubs JAR không chứa secrets**, **consumer tests qua Stub Runner** và **CI release gates** sẽ giúp phát hiện sớm cả thay đổi API không tương thích lẫn sai lệch trong hành vi bảo mật đã cam kết. Tuy vậy, **test JwtDecoder giả không thay thế kiểm tra JWT signature/issuer/audience, gateway, TLS, CSRF hay broker ACL**; những yêu cầu đó cần integration/security tests độc lập để có bằng chứng đáng tin cậy.
