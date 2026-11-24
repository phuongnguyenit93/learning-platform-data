# Header token, cookie và chứng chỉ bằng dữ liệu kiểm thử trong Spring Cloud Contract

Trong hệ thống microservices, một consumer có thể gọi đúng URL và xử lý đúng JSON nhưng vẫn không giao tiếp được với producer vì **thiếu header xác thực**, **cookie phiên không hợp lệ** hoặc **kết nối TLS từ chối chứng chỉ**. Khi nhóm dùng **Spring Cloud Contract (SCC)**, những thành phần này dễ bị hiểu nhầm: một HTTP stub có thể kiểm tra chuỗi `Authorization` nhưng không tự xác minh chữ ký JWT; một stub trả `Set-Cookie` nhưng không tự quản lý session thật; và một contract DSL mô tả HTTP response không tự kiểm tra certificate chain hay mutual TLS.

Bài thuộc chương **Bảo mật hợp đồng**, với chủ đề **Header token, cookie và chứng chỉ bằng dữ liệu kiểm thử**, hướng dẫn tạo fixture bảo mật an toàn, dùng **Groovy/YAML DSL** kiểm tra giao diện HTTP, để **Spring Cloud Contract Verifier** sinh **provider verification tests**, phát hành stubs và chạy consumer tests bằng **Stub Runner**. Đồng thời, bài chỉ ra những yêu cầu phải chuyển sang **Spring Security integration tests**, **HTTPS/mTLS transport tests** hoặc kiểm thử browser/broker phù hợp.

Ví dụ xuyên suốt dùng `order-producer` cung cấp `GET /api/orders/1001`, `checkout-consumer` gọi API bằng bearer token, và một endpoint session-based dành cho giao diện quản trị. Tất cả token, cookie, username và chứng chỉ được nhắc tới đều là **dữ liệu mô phỏng**, không phải bí mật hoặc certificate production.

## 1. Ba tầng bảo vệ không được đánh đồng

Một request có thể đi qua nhiều lớp:

```mermaid
flowchart TD
    C["Consumer HTTP client"] --> T["TLS: server certificate / optional mTLS"]
    T --> H["HTTP: Authorization, Cookie, headers"]
    H --> S["Security filter: authentication + authorization"]
    S --> A["Controller / business logic"]
    A --> R["HTTP status, headers, JSON response"]
    X["SCC contract / WireMock stub"] -. "Mô phỏng một phần HTTP contract" .-> H
    Y["Transport integration tests"] -. "Kiểm tra trust, hostname, client cert" .-> T
    Z["Security integration tests"] -. "Kiểm tra token, session, roles" .-> S
```

| Tầng | Câu hỏi cần trả lời | Công cụ kiểm thử phù hợp |
| --- | --- | --- |
| HTTP contract | Consumer có gửi `Authorization`/`Cookie` đúng định dạng và xử lý 200/401/403 không? | SCC DSL, generated tests, Stub Runner, WireMock |
| Authentication | Token có chữ ký hợp lệ, chưa hết hạn, issuer/audience đúng không? | Spring Security integration tests, test issuer/JWKS |
| Authorization | Principal này có quyền đọc đơn hàng thuộc tenant tương ứng không? | Security tests có filter chain/permission logic |
| Session | Cookie có gắn với phiên còn hiệu lực, có bị rotate/invalidate không? | Session integration tests, cookie jar/browser tests |
| TLS | Client có tin server certificate và kiểm tra hostname không? | HTTPS client/server integration tests |
| mTLS | Server có đòi certificate phía client và kiểm tra trust chain không? | TLS handshake tests với test keystore/truststore |
| Vận hành | Cert có rotation/expiry đúng? Auth service unavailable xử lý ra sao? | Resilience, security và deployment tests |

**Không có một request matcher nào tự chứng minh cả bảy tầng.** Cần xác định bài test đang chứng minh giao diện, logic bảo mật hay kết nối thực.

### 1.1. Một test xanh có phạm vi cụ thể

Nếu WireMock nhận:

```http
GET /api/orders/1001 HTTP/1.1
Authorization: Bearer contract-test-token
Accept: application/json
```

và trả 200, bài test có thể cho thấy **client gửi đúng chuỗi header và đọc được body mẫu**. Nó **không** chứng minh token được ký bởi identity provider tin cậy, đã qua kiểm tra `exp`, hoặc có quyền đọc mọi đơn hàng.

## 2. Phân loại dữ liệu kiểm thử bảo mật

Chỉ nên dùng **dữ liệu do test tạo ra, có phạm vi và vòng đời rõ ràng**.

| Loại fixture | Ví dụ | Có thể đưa vào contract/stub? | Cần bảo vệ gì? |
| --- | --- | --- | --- |
| Token giả thuần chuỗi | `contract-test-token` | Có, khi chỉ kiểm tra matching HTTP | Không được nhận nhầm là token production |
| JWT được ký bằng khóa test-only | Token tạo trong test với issuer giả | Có điều kiện, thường tạo tại runtime | Không tái sử dụng private key production |
| Cookie phiên giả | `session_id=test-session-42` | Có cho request/response matching | Không dùng session ID thật |
| Role/scope test | `orders:read`, `orders:write` | Có trong fixture identity | Tách quyền thực tế với test scope |
| Certificate self-signed test | Cert cho `localhost` trong test CA | Nên tạo ở test environment | Key riêng không nằm trong repository |
| Truststore test | PKCS#12 chỉ chứa test CA/cert | Có thể tạo ephemeral trong CI | Không ghép nhầm với truststore production |
| Refresh token / API key thật | Không có ví dụ hợp lệ trong lesson | **Không** | Không ghi vào Git, JAR, report hoặc log |

### 2.1. Quy tắc thiết kế fixture

1. **Dễ nhận diện:** đặt tên `test-` hoặc dùng issuer `https://issuer.test.invalid`, tuyệt đối không giống credentials hoạt động thật.
2. **Deterministic khi có thể:** xác định principal, scope, tenant, request path và response mẫu.
3. **Ephemeral khi liên quan private key:** sinh key/cert trong CI test job hoặc lấy từ secret manager dành riêng cho thử nghiệm.
4. **Không có quyền production:** test token không được endpoint production chấp nhận.
5. **Không lộ PII:** dùng `CUS-TEST-42`, không dùng email/địa chỉ khách thật.
6. **Có cleanup:** xóa keystore tạm, session fixtures và request journals chứa dữ liệu auth.
7. **Không giả vờ kiểm chứng bảo mật thật:** nếu chỉ match literal token, mô tả rõ đây là contract test.

### 2.2. Test token và test JWT khác nhau

Chuỗi `contract-test-token` chỉ là một **fixture string**. JWT thực có định dạng ba phần, signature và claims; một test JWT muốn kiểm tra chữ ký phải được ký bằng **khóa kiểm thử mà verifier thật tin cậy theo test configuration**.

Không viết `Bearer abc.def.ghi` rồi cho rằng một resource server chuẩn bắt buộc công nhận nó; đó có thể chỉ là một string match trong WireMock.

## 3. Authorization header: cấu trúc giao diện

Ví dụ bearer authentication:

```http
GET /api/orders/1001 HTTP/1.1
Host: order.example.test
Accept: application/json
Authorization: Bearer contract-test-token
```

Phân biệt:

- `Authorization` là **HTTP header của request**.
- `Bearer` là một authentication scheme; giá trị sau khoảng trắng là credential.
- Credential thực tế có thể là access token opaque hoặc JWT.
- API còn có thể sử dụng cookie-based session hoặc mTLS; đây là những cơ chế khác nhau.
- `WWW-Authenticate` ở response 401 là tín hiệu về cơ chế xác thực theo giao thức HTTP nếu server sử dụng.

Ví dụ 401 không có credential:

```http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer
Content-Type: application/json

{"code":"AUTH_REQUIRED"}
```

Ví dụ 403 với principal đã xác thực nhưng không có quyền:

```http
HTTP/1.1 403 Forbidden
Content-Type: application/json

{"code":"ORDER_ACCESS_DENIED"}
```

**401 thường liên quan việc chưa xác thực hoặc credential không hợp lệ; 403 thường liên quan đã xác thực nhưng không đủ quyền.** Ứng dụng có thể chủ động trả 404 để tránh lộ sự tồn tại tài nguyên; khi đó quyết định security đó phải được các nhóm thống nhất.

### 3.1. Không coi status 401 và 403 là tương đương

Consumer có thể cần:

- Với `401`: refresh access token qua cơ chế an toàn nếu được hỗ trợ, hoặc yêu cầu đăng nhập.
- Với `403`: không lặp lại cùng credential vô hạn; hiển thị không có quyền hoặc xử lý domain error.
- Với `429` hoặc `503`: cân nhắc retry theo policy riêng, không nhầm với auth failure.

Test phải phân biệt các nhánh này; một stub “mọi lỗi đều trả 401” làm mất ý nghĩa giao diện.

## 4. Contract Groovy DSL kiểm tra header token thử nghiệm

Giả sử producer và consumer đã thống nhất rằng request đọc đơn hàng phải có header `Authorization` và trả JSON khi hợp lệ.

```groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    description 'Đọc đơn hàng với header bearer fixture'

    request {
        method GET()
        url '/api/orders/1001'
        headers {
            header('Accept', 'application/json')
            header('Authorization', 'Bearer contract-test-token')
        }
    }

    response {
        status OK()
        headers {
            contentType(applicationJson())
        }
        body(
            id: 1001,
            status: 'CREATED',
            currency: 'VND'
        )
    }
}
```

Đoạn contract mô tả **một request HTTP cụ thể**. Khi SCC sinh provider test, test cần có setup để `contract-test-token` được chấp nhận trong **test environment**; nếu Spring Security đang xác minh JWT thật, chuỗi giả đó sẽ bị từ chối 401 trừ khi bạn thiết lập decoder/test issuer phù hợp.

### 4.1. Một lựa chọn: test fixture token được resource server chấp nhận có kiểm soát

Có thể cung cấp **test-only authentication component** hoặc fake `JwtDecoder` dành riêng cho provider contract tests, để header `Bearer contract-test-token` ánh xạ thành principal `test-user-42` với scope `orders:read`.

Cách này kiểm tra request path và authorization rules được đi qua filter chain ở mức đã cấu hình, nhưng **không kiểm chứng chữ ký JWT production** nếu decoder bị thay bằng fake. Vì vậy vẫn cần một lớp integration test xác minh cryptographic validation với **test signing key và JWT thực được tạo tại runtime**.

### 4.2. Không dùng token production trong contract

Contract file được commit, chia sẻ qua repository và có thể đóng gói vào stubs JAR. Một token production trong fixture có thể tồn tại lâu trong Git history, artifact mirror và CI logs ngay cả khi sau này xóa khỏi file.

**Nếu một secret thật từng bị commit, cần thu hồi/rotate credential**, không chỉ xóa text ở commit mới.

## 5. YAML DSL diễn đạt cùng yêu cầu Authorization

Một ví dụ tương đương với Groovy:

```yaml
description: "Đọc đơn hàng với header bearer fixture"
request:
  method: GET
  url: /api/orders/1001
  headers:
    Accept: application/json
    Authorization: "Bearer contract-test-token"
response:
  status: 200
  headers:
    Content-Type: application/json
  body:
    id: 1001
    status: CREATED
    currency: VND
```

Chọn **Groovy hoặc YAML** cho cùng kịch bản trong build thật, tránh sinh các mapping trùng nhau.

Phần sau vẫn cần kiểm tra:

1. Generated provider test có gửi header đúng không?
2. Security filter trong producer test context có được bật không?
3. Auth fixture có tạo đúng principal/authority không?
4. Producer trả status/body đúng contract không?
5. WireMock mapping sinh ra có ràng buộc `Authorization` đúng như mong muốn không?
6. Consumer thật có tạo header này khi dùng Stub Runner không?

**SCC không tự cung cấp identity provider hoặc cấp token hợp lệ** chỉ vì YAML khai báo header `Authorization`.

## 6. Bằng chứng từ Stub Runner và WireMock có giới hạn

Từ contract trên, SCC có thể sinh HTTP stub mapping. Khi consumer test dùng Stub Runner:

```java
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cloud.contract.stubrunner.spring.AutoConfigureStubRunner;
import org.springframework.cloud.contract.stubrunner.spring.StubRunnerProperties;

@SpringBootTest(properties = {
    "order.api.base-url=http://localhost:8085"
})
@AutoConfigureStubRunner(
    ids = "com.example:order-producer:1.4.0:stubs:8085",
    stubsMode = StubRunnerProperties.StubsMode.LOCAL
)
class CheckoutConsumerContractTest {
    // Inject OrderClient thật và kiểm tra response.
}
```

Stub Runner dùng stubs JAR đã publish/install để khởi chạy mô phỏng producer. Với HTTP, WireMock có thể từ chối request thiếu header do mapping không match.

Nhưng cần phân biệt **WireMock unmatched 404** với **401 do producer security contract mô tả**. Nếu consumer quên header và mapping success không match, WireMock có thể trả 404 mặc định. Không thể xem response 404 ấy là bằng chứng endpoint production trả 404 thay vì 401.

### 6.1. Một request matcher không phải JWT validator

Nếu WireMock mapping yêu cầu:

```json
{
  "request": {
    "method": "GET",
    "urlPath": "/api/orders/1001",
    "headers": {
      "Authorization": {
        "equalTo": "Bearer contract-test-token"
      }
    }
  },
  "response": {
    "status": 200,
    "headers": {
      "Content-Type": "application/json"
    },
    "jsonBody": {
      "id": 1001,
      "status": "CREATED"
    }
  }
}
```

nó chỉ so sánh **giá trị header**. Nếu bỏ cơ chế xác thực thật ở producer và chỉ dựa vào stub, test có thể xanh dù producer chấp nhận token giả mạo trong runtime.

### 6.2. Regex cho token chỉ kiểm tra định dạng

Một matcher kiểu `Bearer [A-Za-z0-9._~-]+` có thể hữu ích để consumer gửi token có cấu trúc hợp lý, nhưng **không bảo đảm chữ ký, issuer, audience, expiration, scopes hoặc quyền sở hữu resource**.

Đừng dùng regex quá rộng và gọi đó là kiểm thử authentication. Kiểm chứng identity phải diễn ra trong security runtime/integration tests phù hợp.

## 7. Dùng WireMock kiểm tra 200/401/403 theo header

Nếu muốn bổ sung stub để consumer kiểm tra error handling, có thể khai báo ba mapping **có điều kiện loại trừ nhau**. Chúng là **mappings dành cho bài kiểm thử**; trong hệ thống thật, các status và error code thuộc public API nên được thỏa thuận với producer và xác minh bằng provider tests.

### 7.1. Auth header hợp lệ theo fixture → 200

```json
{
  "name": "authorized-test-user",
  "priority": 2,
  "request": {
    "method": "GET",
    "urlPath": "/api/orders/1001",
    "headers": {
      "Authorization": {
        "equalTo": "Bearer contract-test-token"
      }
    }
  },
  "response": {
    "status": 200,
    "headers": {
      "Content-Type": "application/json"
    },
    "jsonBody": {
      "id": 1001,
      "status": "CREATED"
    }
  }
}
```

### 7.2. Không có Authorization → 401

```json
{
  "name": "missing-authorization",
  "priority": 1,
  "request": {
    "method": "GET",
    "urlPath": "/api/orders/1001",
    "headers": {
      "Authorization": {
        "absent": true
      }
    }
  },
  "response": {
    "status": 401,
    "headers": {
      "Content-Type": "application/json",
      "WWW-Authenticate": "Bearer"
    },
    "jsonBody": {
      "code": "AUTH_REQUIRED"
    }
  }
}
```

### 7.3. Token fixture không đủ quyền → 403

```json
{
  "name": "insufficient-scope",
  "priority": 1,
  "request": {
    "method": "GET",
    "urlPath": "/api/orders/1001",
    "headers": {
      "Authorization": {
        "equalTo": "Bearer contract-test-no-read-scope"
      }
    }
  },
  "response": {
    "status": 403,
    "headers": {
      "Content-Type": "application/json"
    },
    "jsonBody": {
      "code": "ORDER_ACCESS_DENIED"
    }
  }
}
```

Các mapping này không tự kiểm chứng logic token: mỗi fixture được gán một response cố định. Một request gửi token bất kỳ khác có thể **không match mapping nào**, dẫn tới 404 của WireMock thay vì 401; nếu cần behavior cho unknown tokens, thêm mapping cụ thể có kiểm soát và bài test tương ứng, tránh fallback rộng làm che lỗi request.

### 7.4. Bảng kịch bản consumer

| Request | Kỳ vọng trong stub suite | Điều consumer phải assert |
| --- | --- | --- |
| `Bearer contract-test-token` | 200 JSON | DTO và business flow |
| Không có `Authorization` | 401 `AUTH_REQUIRED` | Auth error mapping |
| `Bearer contract-test-no-read-scope` | 403 | Permission denied |
| `Bearer random-string` | Chưa có mapping nếu chưa định nghĩa | Không diễn giải unmatched như contract 401 |
| Sai method/path | Unmatched | Bắt được lỗi client route |
| Token hết hạn trong security integration test | 401 từ verifier thật/test issuer | Không refresh vô hạn |

**Đừng chạy cả ba mapping cùng với một catch-all `priority=1`**: catch-all có thể che kịch bản chuyên biệt. Khi SCC sinh mappings, cần kiểm tra priority và matcher tương ứng trên WireMock server.

## 8. Tách xác thực và phân quyền trong producer tests

Có ít nhất ba cấp độ kiểm thử:

| Cấp độ | Cách làm | Có thể khẳng định |
| --- | --- | --- |
| Contract/stub | So chuỗi `Authorization`, trả status mẫu | HTTP client và error handling phù hợp fixture |
| Security rule integration | Tạo test principal với scopes, chạy filter/authorization rules | Quy tắc role/scope/ownership hoạt động trong test configuration |
| Cryptographic validation | Ký token bằng test key, cấu hình decoder/test issuer rồi gửi bearer token qua HTTP thật | Chữ ký, issuer, audience, lifetime… theo config được kiểm tra |

### 8.1. Spring Security test principal không phải token ký thật

Ví dụ một test Spring MVC khi có dependency `spring-security-test`:

```java
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.jwt;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.security.core.authority.SimpleGrantedAuthority;

@SpringBootTest
@AutoConfigureMockMvc(addFilters = true)
class OrderAuthorizationTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void userWithReadScopeCanRead() throws Exception {
        mockMvc.perform(get("/api/orders/1001")
                .with(jwt()
                    .jwt(jwt -> jwt.subject("test-user-42"))
                    .authorities(
                        new SimpleGrantedAuthority("SCOPE_orders:read"))))
            .andExpect(status().isOk());
    }

    @Test
    void userWithoutScopeIsForbidden() throws Exception {
        mockMvc.perform(get("/api/orders/1001")
                .with(jwt()
                    .jwt(jwt -> jwt.subject("test-user-42"))
                    .authorities(
                        new SimpleGrantedAuthority("SCOPE_orders:write"))))
            .andExpect(status().isForbidden());
    }
}
```

Đoạn code giả định ứng dụng đã cấu hình **Spring Security filter chain** yêu cầu `orders:read` để truy cập endpoint, controller có fixture `1001` và dependencies tương thích. `jwt()` tạo một principal mô phỏng, không gửi/cấp phát một JWT có chữ ký thật qua network.

**Test này chủ yếu kiểm chứng authorization rules, không chứng minh bearer parser hay JWT signature verification.** Với authentication validation, cần một bài test riêng dùng token thật được ký bởi **test-only key**, đi qua decoder/filter configuration phù hợp.

### 8.2. Cẩn thận khi vô hiệu hóa filter trong generated provider tests

`@AutoConfigureMockMvc(addFilters = false)` có thể khiến các endpoint yêu cầu auth được gọi dễ dàng hơn trong test. Điều đó có thể phù hợp với một số isolated controller tests, nhưng **không thể dùng kết quả pass để kết luận Spring Security bảo vệ endpoint đúng**.

Khi contract bao gồm behavior 401/403 hoặc auth header, cần security integration tests riêng hoặc provider test setup thực thi filter chain đúng phạm vi. Đọc generated tests để biết request có đi qua security hay không.

## 9. JWT fixture: claims, thời gian và khóa ký

JWT kiểm thử nên được tạo bằng test key/issuer riêng, với claims có chủ đích. Một payload mang tính minh họa:

```json
{
  "iss": "https://issuer.test.invalid",
  "sub": "test-user-42",
  "aud": ["order-api"],
  "scope": "orders:read",
  "tenant_id": "TENANT-TEST-1",
  "iat": 1795500000,
  "nbf": 1795500000,
  "exp": 1795500600
}
```

Đây là **payload JSON ví dụ**, chưa phải JWT có chữ ký hợp lệ. Các epoch seconds ở đây chỉ minh họa định dạng; **không dùng timestamps cố định này làm credential test lâu dài**, vì test sẽ thất bại khi thời gian thực vượt `exp`.

### 9.1. Ma trận claims quan trọng

| Thuộc tính | Ca thành công | Ca từ chối |
| --- | --- | --- |
| Signature | Test private key tương ứng trusted public key | Tampered signature |
| `iss` | Issuer được cấu hình tin cậy | Issuer lạ |
| `aud` | Có audience `order-api` theo validation policy | Audience sai/thiếu |
| `exp` | Còn hiệu lực | Hết hạn |
| `nbf` | Đã đến thời điểm hợp lệ | Chưa có hiệu lực |
| `scope` | Có `orders:read` | Chỉ có `orders:write` |
| `tenant_id` | Khớp tenant của resource | Tenant khác |
| `kid` | Chỉ đến test key được trust | Key ID không tồn tại hoặc đã rotate |

Tùy framework, audience validation có thể cần cấu hình bổ sung; đừng mặc định mọi resource server kiểm tra `aud` chỉ vì claim này tồn tại.

### 9.2. Kiểm soát thời gian bằng test clock

Nếu test cần token “hết hạn sau 60 giây”, tạo nó tương đối với **clock được kiểm soát trong test**, hoặc inject test clock vào lớp xử lý thời gian phù hợp. Tránh commit một token JWT cố định có `exp` trong quá khứ và hi vọng bài test vẫn pass nhiều năm.

Khi kiểm thử `nbf` và `exp`, cần làm rõ policy về clock skew/tolerance. Một assertion “hết hạn đúng một mili giây” dễ flaky nếu phụ thuộc đồng hồ hệ điều hành, scheduler hoặc lệch giờ giữa containers.

### 9.3. Key rotation chỉ nên thử với khóa dành riêng cho test

Với JWKS test server, có thể thử hai key IDs `test-key-a` và `test-key-b`, kiểm tra token cũ/mới theo chính sách rotation. Không sử dụng private key của identity provider production hay secret chung giữa test và production.

## 10. Cookie request và Set-Cookie response: hai chiều khác nhau

Trong mô hình session-based:

```http
GET /admin/orders/1001 HTTP/1.1
Cookie: session_id=test-session-42
Accept: application/json
```

Server có thể phản hồi bằng cookie mới hoặc cookie để xóa session:

```http
HTTP/1.1 200 OK
Set-Cookie: session_id=test-session-42; Path=/; Secure; HttpOnly; SameSite=Lax
Content-Type: application/json

{"id":1001,"status":"CREATED"}
```

**`Cookie` là header client gửi lên; `Set-Cookie` là header server gửi về.** Chúng không thay thế nhau. Một test chỉ assert `Set-Cookie` xuất hiện chưa chứng minh client/browser đã lưu cookie rồi gửi lại nó ở request sau.

### 10.1. Ý nghĩa thuộc tính cookie thường gặp

| Thuộc tính | Ý nghĩa | Test nên kiểm tra |
| --- | --- | --- |
| `Path` | Giới hạn path cookie được gửi | Có áp dụng đúng URL không |
| `Domain` | Ranh giới domain cookie | Không vô ý mở rộng domain |
| `Secure` | Cookie chỉ gửi qua secure context theo quy tắc client/browser | HTTPS test và browser behavior |
| `HttpOnly` | Không cho JavaScript thông thường đọc qua `document.cookie` | Browser/security behavior |
| `SameSite=Lax` | Hạn chế gửi cookie trong một số cross-site contexts | Browser integration |
| `SameSite=Strict` | Chính sách cross-site nghiêm hơn | Browser integration |
| `SameSite=None; Secure` | Cho phép cross-site theo chính sách browser, thường đòi Secure | Browser integration |
| `Max-Age` / `Expires` | Thời hạn cookie | Cookie jar/session expiry tests |
| `Partitioned` nếu sử dụng | Quy tắc cookie partition theo browser hiện đại | Browser compatibility tests |

**WireMock không tự thực thi trình duyệt.** Nó có thể phát header `Set-Cookie` nhưng không tự chứng minh `HttpOnly` đã chặn JavaScript hoặc `SameSite` bảo vệ cross-site request đúng cách.

### 10.2. Không đặt session ID thật trong stubs JAR

Cookie fixture như `test-session-42` là dữ liệu tổng hợp. Không trích xuất `JSESSIONID` hoặc session cookie thực tế từ trình duyệt của nhân viên/người dùng rồi đưa vào hợp đồng hoặc log CI.

## 11. Contract Groovy/YAML cho session cookie

Ví dụ contract của một endpoint **giả định phiên kiểm thử đã tồn tại**:

```groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    description 'Đọc trang quản trị với test session cookie'

    request {
        method GET()
        url '/admin/orders/1001'
        headers {
            header('Cookie', 'session_id=test-session-42')
            header('Accept', 'application/json')
        }
    }

    response {
        status OK()
        headers {
            contentType(applicationJson())
            header('Set-Cookie',
                'session_id=test-session-42; Path=/; Secure; HttpOnly; SameSite=Lax')
        }
        body(
            id: 1001,
            status: 'CREATED'
        )
    }
}
```

YAML tương đương:

```yaml
description: "Đọc trang quản trị với test session cookie"
request:
  method: GET
  url: /admin/orders/1001
  headers:
    Cookie: "session_id=test-session-42"
    Accept: application/json
response:
  status: 200
  headers:
    Content-Type: application/json
    Set-Cookie: "session_id=test-session-42; Path=/; Secure; HttpOnly; SameSite=Lax"
  body:
    id: 1001
    status: CREATED
```

Đây là **hợp đồng HTTP về header và response cụ thể**, không phải cơ chế cấp session. Producer test setup phải tạo một session fixture hoặc test-only session resolver để request được chấp nhận khi chạy provider tests.

**Trong thực tế không nên bắt một endpoint GET bình thường lúc nào cũng trả lại cùng một session ID.** Ví dụ chỉ minh họa cách kiểm tra một tình huống phát cookie đã được thỏa thuận. Với session renewal, login hoặc logout, hãy viết contract/test đúng endpoint và semantics của chúng.

### 11.1. Khi nào cần kiểm tra cookie bằng matcher riêng?

Header `Cookie` có thể chứa nhiều cặp `name=value`, thứ tự khác nhau và các giá trị động. So khớp cả chuỗi `Cookie` có thể quá cứng. WireMock hỗ trợ matcher cookie riêng cho từng tên, ví dụ:

```json
{
  "name": "admin-session-test-fixture",
  "request": {
    "method": "GET",
    "urlPath": "/admin/orders/1001",
    "cookies": {
      "session_id": {
        "equalTo": "test-session-42"
      }
    }
  },
  "response": {
    "status": 200,
    "headers": {
      "Content-Type": "application/json"
    },
    "jsonBody": {
      "id": 1001,
      "status": "CREATED"
    }
  }
}
```

Lưu ý: **WireMock JSON mapping schema và Spring Cloud Contract YAML schema là hai thứ khác nhau**. Đừng chép trường `cookies` vào SCC YAML mà không xác minh version/plugin hỗ trợ. Với hợp đồng nguồn, chọn cú pháp được SCC version xác nhận rồi **xem generated WireMock mapping**.

### 11.2. Không coi cookie matcher là session validator

Matcher `session_id=test-session-42` không kiểm tra session có bị revoke, đã expire, thuộc đúng account hoặc có quyền admin. Các ràng buộc đó thuộc security/session integration tests.

## 12. Session lifecycle: login, dùng cookie, logout

Một luồng thực tế thường gồm ba bước:

```mermaid
sequenceDiagram
    participant U as Client / browser
    participant A as Auth/session service
    participant O as Order API
    U->>A: POST /login (test credentials)
    A-->>U: Set-Cookie: session_id=...
    U->>O: GET /admin/orders/1001 + Cookie
    O-->>U: 200 / 403
    U->>A: POST /logout + session cookie
    A-->>U: Set-Cookie: session_id=; Max-Age=0
    U->>O: GET /admin/orders/1001 + old Cookie
    O-->>U: 401 / redirect theo chính sách
```

Một stub tĩnh có thể phát cookie ở lần đầu và nhận cookie ở request tiếp theo, nhưng **không tự quản lý trạng thái session, invalidation và lưu cookie của browser**.

Để kiểm tra session lifecycle:

- Chạy Spring Security/session implementation thật trong integration test.
- Dùng HTTP client có cookie jar hoặc browser test.
- Kiểm tra session fixation protection/rotation nếu ứng dụng yêu cầu.
- Kiểm tra logout khiến session cũ không còn hiệu lực.
- Kiểm tra idle/absolute expiration theo policy.
- Assert cookie flags (`Secure`, `HttpOnly`, `SameSite`) qua response/header và browser behavior phù hợp.

### 12.1. Không mặc định mọi 401 sẽ tự redirect

Browser session apps đôi khi redirect về login (302) thay vì trả JSON 401. API clients thường muốn 401/403. Đó là **quyết định giao diện cần được thỏa thuận**, không phải giá trị cố định của Spring Cloud Contract.

## 13. CSRF và cookie-based authentication

Cookie-based session thường cần chú ý **Cross-Site Request Forgery** vì trình duyệt có thể tự gửi cookie theo chính sách của nó. Cơ chế bảo vệ có thể yêu cầu CSRF token riêng cho các thao tác thay đổi trạng thái.

Ví dụ:

```http
POST /admin/orders/1001/cancel HTTP/1.1
Cookie: session_id=test-session-42
X-CSRF-TOKEN: csrf-test-value
Content-Type: application/json

{"reason":"CUSTOMER_REQUEST"}
```

Một hợp đồng có thể kiểm tra header `X-CSRF-TOKEN` tồn tại ở request, nhưng **không chứng minh token đó liên kết đúng session hoặc có tính ngẫu nhiên/chống replay**. Security filter và CSRF repository phải được test.

Ví dụ kiểm thử Spring Security MVC:

```java
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@Test
void rejectsPostWithoutCsrf() throws Exception {
    mockMvc.perform(post("/admin/orders/1001/cancel")
            .with(user("admin-test").roles("ADMIN")))
        .andExpect(status().isForbidden());
}

@Test
void acceptsPostWithCsrfWhenAuthorized() throws Exception {
    mockMvc.perform(post("/admin/orders/1001/cancel")
            .with(user("admin-test").roles("ADMIN"))
            .with(csrf()))
        .andExpect(status().isOk());
}
```

Đoạn minh họa giả định có `MockMvc`, import `user` từ Spring Security test, filter chain bật, endpoint trả 200 khi thành công, và ứng dụng thực sự có CSRF protection. Mã là một **đoạn test method minh họa**, không phải cả class độc lập biên dịch ngay. Một resource server dùng stateless bearer token có thể có CSRF policy khác: không áp dụng mô hình cookie session máy móc cho mọi API.

## 14. Chứng chỉ TLS: không phải HTTP header

Chứng chỉ server được trao đổi trong **TLS handshake**, trước khi HTTP request được chuyển tới ứng dụng. Nó không phải chuỗi header như:

```text
X-Client-Cert: ....
```

Một gateway có thể truyền thông tin client certificate qua header nội bộ sau khi **đã xác minh mTLS**, nhưng header tự gửi từ bên ngoài **không chứng minh danh tính client**. Chỉ tin vào header kiểu này khi gateway/proxy được cấu hình xóa dữ liệu do client tự cung cấp và chèn thông tin đã xác thực theo trust boundary rõ ràng.

### 14.1. TLS server authentication

Consumer kết nối:

```text
https://localhost:<test-https-port>/api/orders/1001
```

Client cần xác minh:

1. Certificate chain dẫn tới CA/cert được truststore tin cậy.
2. Hostname khớp subject alternative name (SAN).
3. Certificate còn hiệu lực theo thời gian của hệ thống.
4. Thuật toán và chính sách TLS được cấu hình cho test client/server.
5. Khi có revocation/OCSP policy, cơ chế đó được test riêng nếu cần.

Không nên tắt certificate verification chỉ để consumer test xanh.

### 14.2. mTLS: xác thực cả hai phía

Với **mutual TLS**, server ngoài việc trình certificate của mình còn yêu cầu **client certificate**. Cần:

- **Server keystore:** private key + certificate của server.
- **Client truststore:** trusted CA/cert dùng xác minh server.
- **Client keystore:** private key + certificate của client.
- **Server truststore:** CA/cert dùng xác minh client.

```mermaid
sequenceDiagram
    participant C as Consumer HTTPS client
    participant S as Producer / test HTTPS server
    C->>S: TLS ClientHello
    S-->>C: Server certificate + certificate request nếu mTLS
    Note over C: Validate server chain và hostname
    C->>S: Client certificate nếu được yêu cầu
    Note over S: Validate client chain và policy
    C->>S: HTTP GET + Authorization/Cookie nếu có
    S-->>C: HTTP response
```

**TLS authentication và bearer token authentication có thể cùng tồn tại**. Một certificate hợp lệ không mặc nhiên cấp mọi scope `orders:read`; một JWT hợp lệ cũng không thay thế certificate nếu server bắt buộc mTLS.

## 15. Tạo certificate và truststore chỉ dành cho test

Có thể sinh certificate self-signed `localhost` với JDK `keytool` trong **môi trường thử nghiệm**. Ví dụ dưới đây chỉ nhằm học cách tạo **server test certificate**, không phải CA/PKI production:

```bash
keytool -genkeypair \
  -alias localhost \
  -keyalg RSA \
  -keysize 2048 \
  -validity 7 \
  -storetype PKCS12 \
  -keystore server-test.p12 \
  -storepass TEST_ONLY_PASSWORD \
  -keypass TEST_ONLY_PASSWORD \
  -dname "CN=localhost" \
  -ext "SAN=dns:localhost,ip:127.0.0.1"
```

Xuất certificate public từ keystore:

```bash
keytool -exportcert \
  -rfc \
  -alias localhost \
  -keystore server-test.p12 \
  -storepass TEST_ONLY_PASSWORD \
  -file server-test.crt
```

Tạo truststore phía test client:

```bash
keytool -importcert \
  -noprompt \
  -alias localhost-test \
  -file server-test.crt \
  -storetype PKCS12 \
  -keystore truststore-test.p12 \
  -storepass TEST_ONLY_PASSWORD
```

**Các lệnh trên là ví dụ chạy trong workspace test riêng, không được thực thi trong quá trình viết bài này.** `TEST_ONLY_PASSWORD` phải được thay bằng giá trị test thích hợp; không dùng nó hoặc các file key test này làm secrets production. Nên tạo file tạm trong CI và xóa theo lifecycle job, thay vì commit private key vào Git.

### 15.1. Vì sao cần SAN?

Nhiều TLS clients hiện đại xác minh hostname bằng **Subject Alternative Name**. Một certificate chỉ chứa `CN=localhost` nhưng thiếu SAN có thể bị từ chối dù truststore đã tin cậy certificate.

Nếu URL test dùng `127.0.0.1`, SAN phải hỗ trợ địa chỉ IP tương ứng; nếu dùng `localhost`, cần DNS SAN phù hợp. **Không sửa lỗi hostname mismatch bằng cách tắt hostname verification.**

### 15.2. Chứng chỉ có thể hết hạn trong CI

Một certificate commit trong test fixtures với thời hạn 7 ngày sẽ làm pipeline fail sau một tuần. Giải pháp thường là **sinh certificate ephemeral khi job chạy** hoặc quản lý test CA/certificate lifecycle có rotation, không phải tăng thời hạn vô hạn hoặc bỏ kiểm tra expiration.

Khi test chính sách certificate expiry, dùng test clocks/fixtures phù hợp; không cần đợi certificate thật hết hạn mới biết client từ chối.

## 16. WireMock HTTPS: kiểm tra kết nối thực thay vì chỉ so header

Một WireMock HTTP stub chạy trên `http://localhost:8085` **không thể** kiểm tra TLS certificate validation vì kết nối không dùng HTTPS.

Để consumer test truststore/hostname, khởi động HTTPS stub server. Ví dụ Java DSL với **API/configuration tương thích WireMock version đang dùng**:

```java
import static com.github.tomakehurst.wiremock.core.WireMockConfiguration.options;
import static com.github.tomakehurst.wiremock.client.WireMock.*;

import com.github.tomakehurst.wiremock.WireMockServer;

WireMockServer server = new WireMockServer(
    options()
        .dynamicPort()
        .dynamicHttpsPort()
        .keystorePath("build/test-certs/server-test.p12")
        .keystorePassword("TEST_ONLY_PASSWORD")
);

server.start();

server.stubFor(
    get(urlEqualTo("/api/orders/1001"))
        .willReturn(okJson(
            "{\"id\":1001,\"status\":\"CREATED\"}"
        ))
);

int tlsPort = server.httpsPort();
// Client phải gọi https://localhost:<tlsPort>/api/orders/1001
// Dừng server trong afterEach/finally.
```

Đây là **đoạn minh họa setup**, không phải test class hoàn chỉnh. Tên và hành vi cấu hình keystore có thể khác giữa các phiên bản WireMock; kiểm tra API và file test certificate thực tế của dự án.

### 16.1. Client phải dùng truststore riêng

Java HTTP client có thể được cấu hình `SSLContext` từ PKCS#12 truststore **do test tạo**, thay vì sử dụng một global “trust all”:

```java
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.KeyStore;
import javax.net.ssl.SSLContext;
import javax.net.ssl.TrustManagerFactory;
import java.net.http.HttpClient;

char[] password = "TEST_ONLY_PASSWORD".toCharArray();

KeyStore truststore = KeyStore.getInstance("PKCS12");
try (InputStream in = Files.newInputStream(
        Path.of("build/test-certs/truststore-test.p12"))) {
    truststore.load(in, password);
}

TrustManagerFactory tmf = TrustManagerFactory.getInstance(
    TrustManagerFactory.getDefaultAlgorithm()
);
tmf.init(truststore);

SSLContext sslContext = SSLContext.getInstance("TLS");
sslContext.init(null, tmf.getTrustManagers(), null);

HttpClient client = HttpClient.newBuilder()
    .sslContext(sslContext)
    .build();
```

Tiếp theo, test phải dùng `client` này để gọi URL HTTPS stub, assert response 200 hoặc exception mong đợi và xác minh client thật của ứng dụng dùng **cấu hình TLS tương ứng**. Đoạn mã này không mô tả mTLS vì chưa cài **client key managers**.

### 16.2. Ba trường hợp HTTPS tối thiểu

| Test case | Test server / client | Kỳ vọng |
| --- | --- | --- |
| Server cert hợp lệ theo truststore test | Cert `localhost`, client trust test cert | HTTPS request thành công |
| Cert không nằm trong truststore | Client chỉ trust CA khác | TLS handshake fail |
| Hostname không khớp SAN | Client gọi tên host khác certificate | TLS validation fail |

Tùy HTTP client, lỗi có thể xuất hiện dưới dạng `SSLHandshakeException`, `SSLPeerUnverifiedException` hoặc exception adapter có root cause tương ứng. Không buộc mọi client library ném cùng một Java exception class nếu API của ứng dụng chuẩn hóa lỗi ở tầng khác.

## 17. mTLS: test có và không có client certificate

Đối với mTLS, phải cấu hình test server **yêu cầu client certificate** và tin cậy một test CA hoặc test client certificate cụ thể.

Ma trận:

| Server yêu cầu mTLS | Client cert | Client cert trusted? | Kỳ vọng |
| --- | --- | --- | --- |
| Có | Không có | Không áp dụng | TLS handshake bị từ chối |
| Có | Có | Có | Handshake qua, rồi kiểm tra HTTP/auth |
| Có | Có | Không | TLS handshake bị từ chối |
| Có | Có nhưng hết hạn | Không hợp lệ theo validation | Bị từ chối |
| Không | Không có | Không áp dụng | Có thể vào HTTP, tùy bearer/session auth |

Không nên dùng phản hồi 401 hoặc 403 từ WireMock để thay thế kịch bản **TLS handshake failure**. Khi server bắt buộc client certificate và handshake thất bại, thông thường **HTTP request chưa đến controller**, do đó không có HTTP status do controller tạo.

### 17.1. Những thành phần phải kiểm tra khi cấu hình mTLS

- Test server có bật chế độ **need client authentication** hay chỉ tùy chọn client cert?
- Server truststore có chứa đúng CA/cert của test client?
- Client keystore có private key và certificate chain?
- Key managers có được đưa vào client `SSLContext`?
- Server cert có SAN khớp URL mà client gọi?
- Certificate có đúng mục đích sử dụng/EKU theo policy?
- Truststores và test credentials có được cô lập/cleanup sau job?

**Lưu ý:** SCC Groovy/YAML contract không cung cấp một trường đơn giản để “bật mTLS cho WireMock”. Đây là cấu hình của transport/security test infrastructure; cần chạy test riêng với TLS stack thật.

### 17.2. Header client certificate do proxy chèn vào

Một số gateway dùng header như `X-Forwarded-Client-Cert` để chuyển metadata của client cert đã xác minh. Consumer không được tự gửi header đó tới backend được expose mà backend lại tin nó vô điều kiện. Cần test proxy **xóa header do client tự cung cấp** và chỉ chèn giá trị từ TLS handshake đã xác thực.

Một SCC contract có thể kiểm tra backend nhận đúng header ở ranh giới tin cậy, nhưng **không thay thế proxy security integration tests**.

## 18. Cookie Secure, TLS và browser behavior phải đi cùng nhau

Một contract có thể trả:

```http
Set-Cookie: session_id=test-session-42; Path=/; Secure; HttpOnly; SameSite=None
```

Tuy nhiên:

- `Secure` có ý nghĩa khi client/browser áp dụng HTTPS semantics.
- `HttpOnly` liên quan quyền truy cập cookie từ JavaScript, không phải khả năng Java test đọc header.
- `SameSite=None` trong browser hiện đại thường phải đi kèm `Secure` và vẫn chịu các chính sách tracking/cookie khác.
- `Path` và `Domain` quyết định request sau có mang cookie không.
- `Max-Age=0` có thể được dùng để xóa cookie theo name/path/domain tương ứng.

Nếu mục tiêu là bảo đảm browser gửi cookie đúng khi người dùng điều hướng cross-site, phải dùng **browser integration tests** với ngữ cảnh origin/HTTPS phù hợp. WireMock trả chuỗi header không đủ.

### 18.1. Không bỏ kiểm tra certificate để test cookie nhanh hơn

Nếu cookie chỉ được gửi qua HTTPS, việc đổi consumer test sang HTTP và bỏ `Secure` sẽ làm mất một phần quan trọng của behavior. Bạn có thể có **một suite contract HTTP đơn giản** và **một suite browser/TLS security** riêng; đừng tuyên bố suite HTTP đã chứng minh Secure/SameSite behavior.

## 19. Kiểm thử nhiều danh tính: token, cookie và certificate không có cùng owner

Trong môi trường thực tế:

| Dữ liệu | Chủ sở hữu điển hình | Quyết định cần phối hợp |
| --- | --- | --- |
| Bearer access token | Identity provider / auth platform | Issuer, audience, scopes, lifetime |
| Session cookie | Web app / session service | Session store, expiry, rotation, SameSite/CSRF |
| Server certificate | Platform/PKI | CA trust, SAN, renewals |
| Client certificate mTLS | Platform/service identity | Identity binding, cert issuance/revocation |
| Resource permission | Producer/domain/security | Ai được đọc/sửa từng đơn hàng |
| Stub fixture string | Producer/consumer test teams | Format và test behavior đã cam kết |

Một nhóm consumer không nên tự quyết rằng producer phải bỏ kiểm tra audience chỉ để token test dễ dùng; producer cũng không nên thay cookie/permission semantics mà không thông báo consumer phụ thuộc.

### 19.1. Token và certificate có thể phối hợp

Một hệ thống có thể dùng:

```text
mTLS client cert -> xác minh service identity
Bearer token     -> xác minh user/subject/scopes
Cookie           -> phiên browser (nếu có)
Resource policy  -> xác minh tenant/order ownership
```

Mỗi lớp có thể fail độc lập. Test nên cô lập nguyên nhân thay vì gom mọi lỗi thành `AUTH_FAILED` mà không phân biệt TLS, authentication, authorization và session expiry.

## 20. Secrets và log: bảo mật ngay trong kiểm thử

Test fixture giả vẫn nên được xử lý theo nguyên tắc bảo mật, vì pipeline có thể vô tình nhận token thật trong lúc debug.

**Không lưu vào repository hoặc stubs JAR:**

- Real bearer token/API key.
- Refresh token.
- Session cookie của người dùng thật.
- Private key dùng cho production certificate.
- Password của keystore/truststore production.
- Credentials Maven repository.
- Full request journal chứa Authorization header không được redact.

### 20.1. Redact trong logs và reports

Một log chưa an toàn:

```text
GET /api/orders/1001
Authorization: Bearer LIVE_TOKEN_SHOULD_NEVER_APPEAR_HERE
Cookie: session_id=REAL_SESSION_SHOULD_NEVER_APPEAR_HERE
```

Một log tốt hơn:

```text
GET /api/orders/1001
Authorization: Bearer [REDACTED]
Cookie: session_id=[REDACTED]
TLS: handshake failed, category=UNTRUSTED_SERVER_CERT
```

Khi lưu WireMock request journal hoặc HTTP client debug logs, cấu hình masking cho `Authorization`, `Cookie`, `Set-Cookie` và headers tùy biến chứa credentials. Không xuất toàn bộ object request/response lên CI artifact nếu chưa qua kiểm soát dữ liệu.

### 20.2. Test-only secret vẫn phải có vòng đời

Nếu CI tạo một test private key hoặc keystore password, tốt nhất để nó tồn tại **trong job thử nghiệm**, chỉ phân phối tới các container cần thiết và xóa sau khi dùng. Đừng gửi file private key qua upload-artifact mặc định khi chỉ cần test report.

Khi pipeline cần chia sẻ test cert giữa jobs, cân nhắc **chỉ chuyển public cert/trust anchor**, còn private key tạo trong job sở hữu nó; nếu bắt buộc chia sẻ private key trong test infrastructure, phải có encryption, quyền truy cập, retention và cleanup rõ ràng.

## 21. CI matrix: kiểm tra HTTP auth và TLS theo cổng riêng

Một chiến lược pipeline:

```mermaid
flowchart TD
    A["Producer PR: contract + code"] --> B["Generate / execute SCC provider tests"]
    B --> C{"Provider tests pass và không bị skip?"}
    C -->|Không| X["Block candidate"]
    C -->|Có| D["Package candidate stubs JAR"]
    D --> E["Consumer Stub Runner HTTP tests"]
    C --> S["Producer security tests: JWT/scope/session/CSRF"]
    C --> T["HTTPS/mTLS tests: trust/hostname/client cert"]
    E --> G["Aggregate release gate"]
    S --> G
    T --> G
    G --> H{"Required gates pass?"}
    H -->|Không| X
    H -->|Có| I["Review / promote artifact"]
```

Từng suite nên phát biểu phạm vi:

| CI job | Bằng chứng tối thiểu |
| --- | --- |
| Contract provider verify | Generated tests thực thi, HTTP/message assertions pass |
| Stubs artifact | GAV/classifier `stubs`, version/digest đúng |
| Consumer Stub Runner | Client thật gửi header/cookie fixture, parse 200/401/403 |
| AuthN/AuthZ integration | JWT claim/signature tests, scopes/tenant ownership |
| Session/CSRF | Cookie lifecycle, invalidation, CSRF enforcement |
| TLS server authentication | Truststore, SAN/hostname, handshake errors |
| mTLS | Client cert required/trusted/rejected |
| Secrets hygiene | Không có credentials thật trong artifacts/logs |
| Release gate | Tất cả suite bắt buộc pass với đúng candidate |

Nếu auth service, gateway hoặc PKI nằm ngoài producer repository, có thể cần CI từ các nhóm khác. **Không biến những cổng chưa chạy thành PASS chỉ vì provider contract test xanh.**

### 21.1. Tách fixture theo môi trường và principal

Ví dụ ma trận:

```text
Fixture A: test-user-reader, scope orders:read, tenant TENANT-TEST-1
Fixture B: test-user-writer, scope orders:write, tenant TENANT-TEST-1
Fixture C: test-user-reader, scope orders:read, tenant TENANT-TEST-2
Fixture D: no credential
Fixture E: expired test JWT
Fixture F: valid test session cookie
Fixture G: revoked test session cookie
Fixture H: valid server cert, client trust configured
Fixture I: untrusted server cert
Fixture J: mTLS server requires client cert, client sends none
```

Không cần chạy tất cả tổ hợp chéo nếu không có giá trị. Hãy chọn những **ranh giới bảo mật** mà consumer/producer thật sự phụ thuộc.

## 22. Một bộ kiểm tra consumer có assertions thực tế

Giả sử consumer `OrderClient` dùng HTTP client thật và ánh xạ các trường hợp:

| Test | Input | Assertion nghiệp vụ |
| --- | --- | --- |
| Reader hợp lệ | `Bearer contract-test-token` | Đọc đúng `id/status/currency` |
| Thiếu token | Không gửi `Authorization` | Trả `Unauthenticated`/điều hướng đăng nhập theo policy |
| Thiếu scope | `Bearer contract-test-no-read-scope` | Trả `Forbidden`, không retry vô hạn |
| Token hết hạn | Token ký test key, `exp` đã qua | 401 từ security integration, refresh/logout hợp lệ |
| Cookie phiên hợp lệ | Cookie jar chứa test session | Client gửi cookie đúng host/path và parse response |
| Cookie bị revoke | Session đã invalidate | Request sau không được coi là authenticated |
| TLS CA không tin cậy | Không có cert trong truststore | Không thực hiện HTTP request thành công |
| mTLS thiếu client cert | Server bắt buộc client auth | Handshake fail, không giả vờ là 401 |

### 22.1. Ví dụ kiểm tra HTTP request đã gửi tới stub

Một test WireMock có thể xác minh:

```java
import static com.github.tomakehurst.wiremock.client.WireMock.*;

wireMockServer.verify(
    1,
    getRequestedFor(urlEqualTo("/api/orders/1001"))
        .withHeader(
            "Authorization",
            equalTo("Bearer contract-test-token")
        )
);
```

Đây là ví dụ kiểm tra **tương tác HTTP** sau khi consumer thực sự gọi `OrderClient`. Nó không xác thực chữ ký hoặc quyền của token, và log request journal có thể chứa header fixture. Với token thật, tránh ghi giá trị vào assertion message/log.

### 22.2. Không tự viết request thay cho consumer

Nếu test chỉ dùng `curl` hoặc một `HttpClient` mới không thuộc ứng dụng để gửi đúng header, nó chưa kiểm tra interceptor/token propagation/cookie jar của consumer thật.

Để giá trị cao, test phải gọi **use case hoặc client của sản phẩm**, nơi tự tạo Authorization/Cookie headers và xử lý response/security exceptions.

## 23. Những lỗi thường gặp và cách chẩn đoán

| Triệu chứng | Nguyên nhân thường gặp | Hướng kiểm tra |
| --- | --- | --- |
| Stub trả 404 khi quên token | Mapping không match, WireMock unmatched | Request journal và mapping, đừng nhầm với contract 401 |
| Contract có token giả nhưng provider test fail 401 | Security verifier thật không chấp nhận fixture | Test issuer/decoder setup và filter chain |
| Provider test pass dù route public nhầm | Security filters bị tắt | Test config và security integration |
| WireMock trả 200 cho token bất kỳ | Matcher regex/catch-all quá rộng | Giới hạn mapping và tách JWT integration |
| Token có đúng chữ ký nhưng fail 401 | `iss`/`aud`/`exp`/`nbf`/`kid` sai | JWT decoder logs đã redact và test clock |
| Token hợp lệ nhưng fail 403 | Thiếu scope hoặc sai tenant/ownership | Authority mapping và domain policy |
| Cookie header có nhưng server không nhận | Domain/path/session store/sameSite/expiry | Session/browser integration |
| Cookie được trả nhưng browser không lưu | `Secure` trên HTTP, SameSite/Domain policy | Browser devtools/test environment |
| Logout xong vẫn truy cập được | Session chưa invalidate | Test session lifecycle và cache |
| HTTPS fail ngay trước controller | Cert/hostname/truststore mismatch | TLS handshake, SAN, trust anchors |
| mTLS fail dù có bearer token | Thiếu client certificate hoặc server không trust client | mTLS configuration, key/trust stores |
| HTTPS test pass sau khi “trust all” | TLS validation đã bị vô hiệu hóa | Bỏ bypass, dùng test truststore |
| CI hết hạn certificate sau vài ngày | Test cert cố định/không rotate | Sinh ephemeral cert hoặc quản lý test PKI |
| Test pass local nhưng fail CI | Ports, clocks, test certificates, profiles, secrets | Cô lập và ghi toolchain/environment |
| Stubs artifact lộ token | Test dùng credential thật | Thu hồi token, xóa khỏi artifact/Git history theo quy trình |

### 23.1. Runbook phân biệt lỗi từng tầng

```text
1. Xác định request dùng http:// hay https://, có yêu cầu mTLS không.
2. Nếu TLS fail: kiểm tra truststore, SAN/hostname, client certificate.
3. Nếu đã có HTTP response: phân biệt 401, 403 và 404 unmatched.
4. Xác nhận consumer client đã gửi Authorization/Cookie như mong đợi.
5. Đối chiếu request với WireMock mapping được chọn.
6. Xác nhận token/cookie fixture chỉ tồn tại trong test environment.
7. Ở producer, kiểm tra filter chain, test issuer/decoder, scope/tenant logic.
8. Ở consumer, kiểm tra auth interceptor, cookie jar, retry/error mapping.
9. Xác nhận stubs JAR version/classifier thuộc candidate đang kiểm tra.
10. Xem test reports và logs đã redact; không copy secret vào ticket.
```

**Đừng sửa mọi lỗi thành HTTP 200 trong stub chỉ để CI xanh.** Nếu consumer thiếu scope hoặc TLS client từ chối server certificate, đổi stub response có thể che vấn đề thật.

## 24. Thực hành: xây ba suite bảo vệ giao diện và cơ chế bảo mật

Chuẩn bị một producer Spring Boot có Spring Cloud Contract và Spring Security, một consumer dùng Stub Runner, cùng WireMock/test certificates chỉ dành cho môi trường học tập.

1. **Định nghĩa hợp đồng:** Viết `GET /api/orders/1001` có header `Authorization: Bearer contract-test-token` và response 200 bằng Groovy.
2. **Chuyển DSL:** Viết YAML tương đương ở nhánh riêng, không giữ hai contract trùng kịch bản trong cùng build.
3. **Provider verification:** Cấu hình base test/filter chain và test-only authentication fixture; chạy generated tests.
4. **Thử lỗi:** Bỏ Authorization khỏi request generated provider test hoặc fixture và xác nhận hành vi không còn như contract.
5. **Phát hành stub:** Tạo stubs JAR classifier `stubs`, kiểm tra WireMock mapping đã ràng buộc header.
6. **Consumer Stub Runner:** Chạy client thật với token giả, assert DTO/nhánh nghiệp vụ thành công.
7. **Thiếu credential:** Thêm stub 401 có matcher `Authorization.absent`; assert consumer xử lý unauthenticated.
8. **Thiếu quyền:** Thêm stub 403 theo test-only token `no-read-scope`; assert không retry vô hạn.
9. **Security integration:** Viết test Spring Security principal có `orders:read`, thiếu scope và sai tenant.
10. **JWT signature:** Sinh JWT runtime bằng test key và test issuer; kiểm tra valid, tampered, expired, wrong issuer/audience.
11. **Cookie header:** Viết contract session fixture và response `Set-Cookie`, kiểm tra path/flags.
12. **Cookie jar:** Dùng HTTP client/browser test qua login → request → logout; xác minh session cũ không được chấp nhận.
13. **CSRF:** Với session-based POST, xác minh request thiếu CSRF bị từ chối theo security policy và request hợp lệ được chấp nhận.
14. **Test HTTPS:** Tạo certificate `localhost` với SAN và truststore riêng; chạy WireMock HTTPS.
15. **Negative TLS:** Gọi bằng client không trust cert test; xác nhận handshake fail.
16. **Hostname:** Thử URL host không khớp SAN; không tắt validation để “sửa”.
17. **mTLS:** Trong môi trường có cấu hình server yêu cầu client cert, thử client hợp lệ, thiếu cert và cert không tin cậy.
18. **Logs:** Kiểm tra request journal, CI reports và artifacts không chứa token/cookie/private key thật.
19. **CI gates:** Tách provider contract, consumer stub, auth integration và HTTPS/mTLS suites; xác nhận gate fail khi suite bắt buộc fail.
20. **Tổng kết:** Viết bảng cho biết từng test chứng minh tầng HTTP, authentication, authorization, cookie/session hay TLS.

### 24.1. Checklist tự đánh giá

| Năng lực | Bằng chứng đạt |
| --- | --- |
| Phân biệt ranh giới | Không nhầm matcher header với xác minh JWT |
| Token fixture | Không dùng credential production trong contract |
| SCC Groovy/YAML | Kiểm tra được request Authorization và response |
| 401/403 | Consumer có assertion phân biệt auth/permission |
| WireMock | Hiểu unmatched 404 và giới hạn của static mappings |
| Spring Security | Test scope, tenant và filter chain đúng phạm vi |
| Cookie | Phân biệt `Cookie`/`Set-Cookie` và flags |
| Session | Test rotation/revocation/expiry bằng integration |
| TLS | Xác minh truststore và SAN mà không tắt certificate checks |
| mTLS | Hiểu client keystore/server truststore và handshake failure |
| Data hygiene | Không leak token, cookie hoặc private keys qua Git/JAR/log |
| CI | Có nhiều cổng kiểm thử bổ sung và candidate stubs đúng version |

## 25. Kết luận: fixture đúng giúp kiểm tra đúng tầng bảo mật

**Spring Cloud Contract** giúp producer và consumer mô tả, xác minh và sử dụng **HTTP/message interface đã thỏa thuận**. Với **header token và cookie**, Groovy/YAML contract và WireMock stubs có thể kiểm tra request/response shape, header propagation và xử lý mã lỗi. Nhưng **token giả khớp chuỗi không phải JWT hợp lệ**, **cookie stub không phải session store**, và **chứng chỉ TLS không nằm trong HTTP contract body/header**.

Hãy áp dụng bốn nguyên tắc:

1. **Dữ liệu chỉ dành cho test:** dùng synthetic token/cookie và test-only cert/key; không đưa production secret vào source hoặc artifact.
2. **Đúng công cụ đúng lớp:** contract tests cho giao diện, security integration cho claims/scope/session, HTTPS/mTLS tests cho trust và handshake.
3. **Bảo vệ client thực:** consumer tests phải gọi client/listener của ứng dụng, không chỉ gọi WireMock bằng mã thử nghiệm khác.
4. **CI có chuỗi bằng chứng:** provider verification pass, candidate stubs đúng version, consumer assertions pass và các security gates bắt buộc không bị skip.

Khi tách rõ **matching**, **authentication**, **authorization**, **session** và **TLS**, nhóm sẽ tránh những kết luận sai kiểu “stub trả 200 nghĩa là token an toàn”, đồng thời phát hiện sớm những thay đổi API hoặc cấu hình bảo mật có thể làm producer và consumer không còn tương thích.
