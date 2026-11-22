# Gửi thuộc tính tối thiểu, xác minh dữ liệu và bảo vệ kênh gọi

> **Spring Security – authorization · Chính sách động.** Bài Knowledge này thiết kế quy trình hỏi quyền từ ứng dụng Spring (**Policy Enforcement Point – PEP**) đến một **Policy Decision Point – PDP** như Open Policy Agent (OPA): chỉ chuyển thuộc tính thực sự cần thiết, xác minh nguồn trước khi gửi và bảo vệ kênh giao tiếp cũng như kết quả trả về. Mẫu Spring sử dụng Java 17+, Spring Boot 3.x, Spring Security 6.x. Các khối trích đoạn khác với chương trình Java thuần có thể chạy bằng `javac`.

## 1. Mục tiêu và ví dụ

Sau bài, bạn có thể chọn dữ liệu cần cho ABAC (subject/resource/action/environment), biết thuộc tính nào đến từ authentication/DB/directory thay vì client, dùng mTLS hoặc token service-to-service đúng cách, xử lý thiếu quyết định theo fail closed, kiểm thử một PEP Spring Security, OPA REST và các tình huống timeout/revocation/privacy.

Giả sử tenant alpha có Alice (role EDITOR), Document 7 classification CONFIDENTIAL owner Alice; tenant beta có Bob (role READER), Document 7 classification INTERNAL owner Bob. Chính sách:
- Người gọi authenticated và có membership ở tenant đã chọn.
- Record thực sự thuộc tenant đó.
- INTERNAL: role READER hoặc EDITOR có thể READ.
- CONFIDENTIAL: chỉ EDITOR đồng thời là owner được READ.
- Các action/role/classification khác bị DENY.

**Sai: gửi nguyên context và nội dung nhạy cảm cho PDP**:

~~~json
{
  "requestHeaders": {"Authorization": "Bearer [raw JWT]"},
  "authentication": {"credentials": "[secret]", "principal": "[whole object]"},
  "document": {
    "id": 7, "title": "ALPHA:Secret",
    "body": "[confidential business content]",
    "ownerEmail": "alice@example.invalid",
    "classification": "CONFIDENTIAL"
  }
}
~~~

Ngay cả với TLS, những trường đó có thể vào APM, debug logs, reverse proxy hoặc OPA decision logs.

**Đúng với policy mẫu:**

~~~json
{
  "input": {
    "verifiedTenant": "alpha",
    "resourceTenant": "alpha",
    "role": "EDITOR",
    "action": "READ",
    "resourceType": "Document",
    "classification": "CONFIDENTIAL",
    "ownerMatches": true
  }
}
~~~

Không phải gửi user token, owner email, content, title, toàn bộ roles hay documentId khi rule không cần chúng. `ownerMatches` do PEP so authenticated stable principal ID và owner metadata đáng tin, tuyệt đối không copy boolean client khai.

## 2. PEP/PDP/PIP/PAP và đường tin cậy

| Thành phần | Trách nhiệm | Ví dụ |
| --- | --- | --- |
| PEP | Tạo request đã được xác minh, chặn/cho phép hành động thực | Spring application service |
| PDP | Đánh giá policy từ input | OPA hoặc remote authorization service |
| PIP | Cung cấp dữ liệu có thẩm quyền cho attributes | User/tenant directory, document metadata DB |
| PAP | Quản lý, test, version và rollout policy | Rego Git repository và bundles |
| Audit | Gắn request, policy revision, decision ID với kết quả thực thi | PEP/PDP logs được kiểm soát |

~~~text
HTTP -> validated Authentication
     -> membership verified for requested tenant
     -> resource metadata WHERE tenant = verifiedTenant AND id = requestedId
     -> derived trusted role/classification/ownerMatches
     -> minimal typed PDP request
     -> HTTPS, server identity + service authentication
     -> PDP evaluates current policy
     -> only explicit ALLOW continues to protected read/write
     -> DENY/undefined/error/timeout never returns protected data
~~~

**PEP phải enforce**, không chỉ log. PDP không thay thế tenant predicate, transaction, object classification hay response redaction. Ngược lại, policy được cập nhật qua bundle không tự làm mọi PIP value mới ngay nếu membership/ACL đang có cache stale.

## 3. Contract thuộc tính tối thiểu

| Field | Gửi không? | Nguồn và lý do |
| --- | --- | --- |
| `verifiedTenant` | Có | Membership của authenticated user trên tenant đang chọn |
| `resourceTenant` | Có | DB metadata, kiểm equality cross-tenant |
| `role` | Có | Role của **tenant đó** từ trusted membership store |
| `action` | Có | Enum/hằng server, READ/WRITE có ngữ nghĩa rõ |
| `resourceType` | Có | Canonical type do backend xác định |
| `classification` | Có | Resource metadata; không từ JSON request |
| `ownerMatches` | Có | Derived boolean từ trusted principal + DB owner |
| `subjectId`/`resourceId` | Không trong policy này | Thêm opaque ID khi rule object/user-specific cần |
| `title`/`document.body`/owner email | Không | Không cần, gây disclosure |
| JWT/password/cookies/raw headers | Không | Credential dành cho authentication, không phải policy attributes |
| IP/device/MFA/time/region | Tùy rule | Chỉ từ trusted proxy/attestation/clock với expiry phù hợp |
| Policy/ACL/membership revision | Tùy consistency | Phải là version thực, không hardcode latest |

Mỗi field cần quy định type, allow-list enum, độ dài, canonicalization, nguồn tin cậy, freshness, privacy classification, schema version và policy nào sử dụng. Unknown/missing value không được biến thành PUBLIC, EDITOR hay grant. `verifiedTenant` chỉ là tên field, **không tự chứng minh** nó đã được verify.

### 3.1. Subject

Trong Servlet, Spring Security đặt `Authentication` vào `SecurityContextHolder` sau khi authentication filter/provider xác thực. Với JWT, validate chữ ký, issuer, expiry/nbf và audience theo resource server policy. `Authentication#getName()` có thể là username hoặc stable user ID theo cấu hình, cần convention thống nhất.

Một user có thể EDITOR alpha và READER beta. Truyền role alpha vào quyết định của beta là lỗi phân quyền. Nếu role thay đổi, membership cache/token claim có thể stale; phải xác định freshness/revocation SLA.

### 3.2. Resource

Hãy query có tenant:

~~~java
Optional<DocumentMetadata> meta =
        repository.findByTenantIdAndId(verifiedTenant, documentId);
~~~

Thay vì query global:

~~~java
Optional<DocumentMetadata> meta = repository.findById(documentId);
~~~

ID hợp lệ nhưng thuộc tenant khác phải không xuất hiện trong lookup tenant hiện tại. Với resource nhạy cảm, dùng metadata projection để kiểm trước khi tải full content, và transaction/version check để tránh resource đổi tenant/owner/classification giữa PDP decision và DB operation.

### 3.3. Environment

Không tin `X-Forwarded-For` hoặc deviceTrusted=true do client khai. Real client IP cần trusted ingress; device posture cần signed attestation/MDM; MFA age cần authentication event; time-based policy cần trusted clock và skew policy. Không thêm field nếu policy không sử dụng.

### 3.4. Ai được khẳng định boolean có độ tin cậy cao?

mTLS xác minh service gửi request, nhưng không chứng minh `ownerMatches=true` được tính đúng. Nếu PDP không hoàn toàn tin PEP, nó có thể lấy owner/tenant/classification từ PIP độc lập, xác minh signed claims/attestation hoặc áp policy riêng về workload nào được phép assert attribute nào. Thiết kế phải mô tả **nguồn của từng sự thật**.

## 4. Bảo vệ kênh gọi PDP

Ba lớp độc lập phải cùng tồn tại:
1. **TLS/HTTPS:** PEP verify CA/certificate chain, hostname/SAN và mã hóa traffic. Không dùng trust-all hoặc disable hostname verifier.
2. **Workload authentication:** PDP biết PEP service nào đang gọi, bằng client mTLS certificate hoặc token máy–máy có issuer/audience/scope/expiry được kiểm tra. Không forward raw JWT của Alice thành credential dùng chung.
3. **PDP authorization:** service chỉ được query đúng policy endpoint, không tự `PUT /v1/policies` hoặc đọc raw sensitive `data` nếu không được cấp quyền.

Thêm host/port allowlist để ngăn SSRF (không nhận URL PDP từ request), chặn redirects sang host lạ, quản lý secrets/cert rotation, bounded connect/read timeout, pool/concurrency limits, rate limiting, metrics và không log credentials.

OPA service phải **được cấu hình** authentication/authorization; không giả định API mặc định đã khóa. Với mTLS, cấu hình TLS server, trusted client CA, `--authentication=tls`, `--authorization=basic` và policy `system.authz` hạn chế các API. localhost/sidecar giúp giảm network hops nhưng không tự là security boundary nếu các process khác có thể gọi.

**Không** khắc phục lỗi certificate bằng `curl -k`, `trustAll`, downgrade HTTP hoặc tắt hostname validation. Cần sửa CA/SAN/truststore/DNS/cert rotation.

## 5. OPA REST Data API: chỉ Boolean true mới ALLOW

Request:

~~~http
POST /v1/data/app/documents/allow HTTP/1.1
Host: pdp.internal.example
Content-Type: application/json

{"input":{"verifiedTenant":"alpha","resourceTenant":"alpha","role":"EDITOR","action":"READ","resourceType":"Document","classification":"CONFIDENTIAL","ownerMatches":true}}
~~~

Named policy decision có thể trả:

~~~json
{"result":true}
~~~

hoặc:

~~~json
{"result":false}
~~~

Nếu rule/path không định nghĩa, OPA Data API có thể trả HTTP 200 nhưng body:

~~~json
{}
~~~

**Đó không phải ALLOW.** `status==200`, `body!=null` hoặc `body.contains("true")` đều không đủ. Parse typed result; chỉ chính xác Boolean.TRUE mới mở quyền. Nếu PDP trả obligations (maskFields, filterRows, requireMFA) thì PEP phải validate và enforce, không bỏ qua chúng.

| PDP state | PEP |
| --- | --- |
| 2xx + result Boolean true | Có thể allow nếu mọi local invariant đúng |
| result false | Deny |
| result missing/null/wrong type | Error closed / deny |
| HTTP 401/403 | Error closed, kiểm workload credentials/authorization |
| HTTP 404/500, timeout, DNS/TLS failure | Error closed, không fallback permitAll |
| ALLOW nhưng resource tenant khác | Deny |
| ALLOW nhưng resource/role đổi trước write | Revalidate trong transaction |
| Cached ALLOW sau revoke | Không dùng nếu không bảo đảm freshness |

Fail closed không đồng nghĩa lúc nào cũng 403. PDP outage có thể trả API 503 để client retry, nhưng không thực hiện protected operation. Metrics nội bộ nên phân biệt `POLICY_DENIED`, `UNDEFINED`, `UNAVAILABLE`, `MALFORMED` và `INVALID_CONTEXT` mà không lộ dữ liệu tenant khác trong response.

## 6. Spring Boot demo: PEP và PDP giả lập để kiểm luồng

Ứng dụng demo chạy không cần OPA bằng `LocalDecisionClient`. Remote OPA adapter ở mục tiếp theo. Mẫu yêu cầu Spring Boot 3.x, Java 17+ và Spring Web/Security.

Lưu `src/main/java/demo/dynamic/DynamicPolicyApplication.java`:

~~~java
package demo.dynamic;

import java.util.Map;
import java.util.Optional;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Profile;
import org.springframework.http.HttpStatus;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.stereotype.Component;
import org.springframework.stereotype.Service;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@SpringBootApplication
@EnableMethodSecurity
public class DynamicPolicyApplication {
    public static void main(String[] args) {
        SpringApplication.run(DynamicPolicyApplication.class, args);
    }

    @Bean
    SecurityFilterChain filterChain(HttpSecurity http) throws Exception {
        return http.authorizeHttpRequests(a -> a
                    .requestMatchers("/api/tenants/**").authenticated()
                    .anyRequest().denyAll())
                .httpBasic(Customizer.withDefaults())
                .build();
    }

    @Bean
    UserDetailsService users() {
        return new InMemoryUserDetailsManager(
                User.withUsername("alice").password("{noop}demo")
                    .authorities("document:read").build(),
                User.withUsername("bob").password("{noop}demo")
                    .authorities("document:read").build(),
                User.withUsername("carol").password("{noop}demo")
                    .authorities("document:read").build(),
                User.withUsername("viewer").password("{noop}demo")
                    .authorities("profile:read").build());
    }
}

record Document(long id, String tenant, String classification,
                String owner, String title) {}
record DocKey(String tenant, long id) {}
record DocumentView(long id, String tenant, String title) {}

record PdpInput(String verifiedTenant, String resourceTenant,
                String role, String action, String resourceType,
                String classification, boolean ownerMatches) {}

interface DecisionClient {
    boolean allow(PdpInput input);
}

@Component
class TenantMemberships {
    private final Map<String, Map<String,String>> roles = Map.of(
            "alice", Map.of("alpha","EDITOR"),
            "bob", Map.of("beta","READER"),
            "carol", Map.of("alpha","READER"));

    String requireRole(Authentication actor, String tenant) {
        if (actor == null || !actor.isAuthenticated()
                || actor instanceof AnonymousAuthenticationToken
                || tenant == null
                || !tenant.matches("[a-z][a-z0-9-]{0,31}")) {
            throw new AccessDeniedException("Tenant access denied");
        }
        String role = roles.getOrDefault(
                actor.getName(),Map.of()).get(tenant);
        if (role == null) {
            throw new AccessDeniedException("Tenant access denied");
        }
        return role;
    }
}

@Component
class DocumentStore {
    private final Map<DocKey,Document> data = Map.of(
            new DocKey("alpha",7L),
                new Document(7L,"alpha","CONFIDENTIAL",
                             "alice","ALPHA:Secret"),
            new DocKey("beta",7L),
                new Document(7L,"beta","INTERNAL",
                             "bob","BETA:Public"),
            new DocKey("alpha",8L),
                new Document(8L,"alpha","INTERNAL",
                             "carol","ALPHA:Public"));

    Optional<Document> findWithinTenant(String tenant, long id) {
        return Optional.ofNullable(data.get(new DocKey(tenant,id)));
    }
}

@Component
@Profile("!remote-pdp")
class LocalDecisionClient implements DecisionClient {
    private volatile PdpInput lastInput;

    @Override
    public boolean allow(PdpInput p) {
        lastInput = p;
        if (p == null || !"READ".equals(p.action())
                || !"Document".equals(p.resourceType())
                || !p.verifiedTenant().equals(p.resourceTenant())) {
            return false;
        }
        boolean allowedRole = "READER".equals(p.role())
                || "EDITOR".equals(p.role());
        if ("INTERNAL".equals(p.classification())) {
            return allowedRole;
        }
        if ("CONFIDENTIAL".equals(p.classification())) {
            return "EDITOR".equals(p.role()) && p.ownerMatches();
        }
        return false;
    }

    PdpInput lastInput() {
        return lastInput;
    }
}

@Service
class DocumentService {
    private final TenantMemberships memberships;
    private final DocumentStore store;
    private final DecisionClient client;

    DocumentService(TenantMemberships memberships,
                    DocumentStore store, DecisionClient client) {
        this.memberships = memberships;
        this.store = store;
        this.client = client;
    }

    @PreAuthorize("hasAuthority('document:read')")
    public DocumentView read(String requestedTenant, long id) {
        Authentication auth = SecurityContextHolder
                .getContext().getAuthentication();
        String role = memberships.requireRole(auth, requestedTenant);
        Document doc = store.findWithinTenant(requestedTenant,id)
                .orElseThrow(() -> new ResponseStatusException(
                        HttpStatus.NOT_FOUND, "Document not found"));

        // ownerMatches do PEP tạo từ trusted auth và resource metadata.
        PdpInput input = new PdpInput(
                requestedTenant, doc.tenant(), role, "READ",
                "Document", doc.classification(),
                doc.owner().equals(auth.getName()));
        boolean grant;
        try {
            grant = client.allow(input);
        } catch (RuntimeException unavailable) {
            throw new AccessDeniedException(
                    "Authorization service unavailable", unavailable);
        }
        if (!grant) {
            throw new AccessDeniedException("Policy denied");
        }
        return new DocumentView(doc.id(),doc.tenant(),doc.title());
    }
}

@RestController
@RequestMapping("/api/tenants/{tenant}/documents")
class DocumentController {
    private final DocumentService service;

    DocumentController(DocumentService service) {
        this.service = service;
    }

    @GetMapping("/{id}")
    DocumentView read(@PathVariable("tenant") String tenant,
                      @PathVariable("id") long id) {
        return service.read(tenant,id);
    }
}
~~~

Dòng dữ liệu được bảo vệ bởi authentication route, method `@PreAuthorize`, tenant membership, scoped document lookup, typed PDP input và explicit allow. `PdpInput` có bảy fields, không gửi content/title/ownerId/user JWT sang PDP. Trong code production, dùng DB metadata projection rồi lấy nội dung sau ALLOW; ràng buộc transaction/version để resource không thay đổi giữa check và use.

Gradle dependencies (trong project đã có plugin/configuration):

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
~~~

`{noop}` mật khẩu và user in-memory chỉ dành cho demo; production dùng password encoder đáng tin, JWT/session configuration đúng và directory persistent.

## 7. MockMvc: kiểm chứng PEP có enforce thật

Lưu `src/test/java/demo/dynamic/DynamicPolicyApplicationTest.java`:

~~~java
package demo.dynamic;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers
        .jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers
        .status;

@SpringBootTest
@AutoConfigureMockMvc
class DynamicPolicyApplicationTest {
    @Autowired MockMvc mvc;
    @Autowired LocalDecisionClient pdp;

    @Test
    void aliceReadsOwnConfidentialDoc() throws Exception {
        mvc.perform(get("/api/tenants/alpha/documents/7")
                    .with(httpBasic("alice","demo")))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.title").value("ALPHA:Secret"));
        PdpInput p = pdp.lastInput();
        assertNotNull(p);
        assertEquals("alpha",p.verifiedTenant());
        assertEquals("EDITOR",p.role());
        assertTrue(p.ownerMatches());
    }

    @Test
    void bobReadsBetaWithSameDocumentId() throws Exception {
        mvc.perform(get("/api/tenants/beta/documents/7")
                    .with(httpBasic("bob","demo")))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.title").value("BETA:Public"));
    }

    @Test
    void bobCannotSelectAlpha() throws Exception {
        mvc.perform(get("/api/tenants/alpha/documents/7")
                    .with(httpBasic("bob","demo")))
                .andExpect(status().isForbidden());
    }

    @Test
    void carolCannotReadAliceConfidentialDoc() throws Exception {
        mvc.perform(get("/api/tenants/alpha/documents/7")
                    .with(httpBasic("carol","demo")))
                .andExpect(status().isForbidden());
    }

    @Test
    void anonymousAndViewerAreRejected() throws Exception {
        mvc.perform(get("/api/tenants/alpha/documents/7"))
                .andExpect(status().isUnauthorized());
        mvc.perform(get("/api/tenants/alpha/documents/7")
                    .with(httpBasic("viewer","demo")))
                .andExpect(status().isForbidden());
    }

    @Test
    void pdpInputHasOnlyWhitelistedFields() throws Exception {
        mvc.perform(get("/api/tenants/alpha/documents/7")
                    .with(httpBasic("alice","demo")))
                .andExpect(status().isOk());
        PdpInput p = pdp.lastInput();
        assertNotNull(p);
        assertEquals(7,PdpInput.class.getRecordComponents().length);
        assertFalse(p.toString().contains("ALPHA:Secret"));
        assertFalse(p.toString().contains("ownerId"));
        assertFalse(p.toString().contains("Bearer "));
    }
}
~~~

Test này đi qua Spring HTTP filter và method-security proxy với PDP giả lập; nó **không thể chứng minh TLS/mTLS**. Nếu bật JUnit parallel, `lastInput` trên singleton là instrumentation đơn giản có nguy cơ trộn test, nên thay bằng spy/context isolation. Trong production không lưu PdpInput vào singleton field.

## 8. Adapter OPA thực với RestClient và mTLS

Spring Boot 3.2+ có `RestClientSsl` để áp SSL bundle. Tạo file `src/main/java/demo/dynamic/RemotePdpConfiguration.java`:

~~~java
package demo.dynamic;

import java.net.URI;

import com.fasterxml.jackson.annotation.JsonProperty;
import org.springframework.boot.autoconfigure.web.client.RestClientSsl;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Profile;
import org.springframework.core.env.Environment;
import org.springframework.http.MediaType;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.RestClientException;

@Configuration
@Profile("remote-pdp")
class RemotePdpConfiguration {
    @Bean
    RestClient opaHttp(RestClient.Builder builder,
                       RestClientSsl ssl, Environment env) {
        URI endpoint = URI.create(
                env.getRequiredProperty("app.pdp.base-url"));
        if (!"https".equalsIgnoreCase(endpoint.getScheme())
                || !"pdp.internal.example".equalsIgnoreCase(
                        endpoint.getHost())
                || endpoint.getUserInfo() != null
                || endpoint.getRawQuery() != null
                || endpoint.getRawFragment() != null) {
            throw new IllegalArgumentException("Untrusted PDP endpoint");
        }

        return builder.baseUrl(endpoint.toString())
                .apply(ssl.fromBundle("pdp-client"))
                .build();
    }

    @Bean
    DecisionClient remoteDecisionClient(RestClient opaHttp) {
        return new OpaDecisionClient(opaHttp);
    }
}

record OpaRequest(PdpInput input) {}
record OpaResponse(Boolean result,
        @JsonProperty("decision_id") String decisionId) {}

final class OpaDecisionClient implements DecisionClient {
    private final RestClient http;

    OpaDecisionClient(RestClient http) {
        this.http = http;
    }

    @Override
    public boolean allow(PdpInput input) {
        if (input == null) return false;
        try {
            OpaResponse reply = http.post()
                    .uri("/v1/data/app/documents/allow")
                    .contentType(MediaType.APPLICATION_JSON)
                    .body(new OpaRequest(input))
                    .retrieve().body(OpaResponse.class);
            return reply != null
                    && Boolean.TRUE.equals(reply.result());
        } catch (RestClientException error) {
            return false;
        }
    }
}
~~~

Response thiếu `result`, result null hoặc false không ALLOW. JSON sai kiểu/HTTP error thường dẫn tới lỗi client và bị chặn; service cũng có catch RuntimeException cuối. Trong production nên phân loại network/schema errors để alert và có thể trả API 503, nhưng vẫn fail closed.

**Lưu ý:** `ssl.fromBundle(...)` có thể thay request factory. Đặt timeout, retry, pooling và redirect policy trong cùng SSL-compatible request factory và test theo Spring Boot version, không tự giả định timeout đặt trước `apply` vẫn tồn tại. Kiểm CA, client cert, hostname verification, rotation và authorized PDP endpoints.

Cấu hình mẫu:

~~~yaml
app:
  pdp:
    base-url: https://pdp.internal.example:8181

spring:
  ssl:
    bundle:
      pem:
        pdp-client:
          keystore:
            certificate: file:/run/secrets/pdp-client.crt
            private-key: file:/run/secrets/pdp-client.key
          truststore:
            certificate: file:/run/secrets/pdp-ca.crt
~~~

Không commit private key/token vào source; file paths đại diện mounted secrets. Đặt profile `remote-pdp` chỉ khi PDP server được cấu hình mTLS/authz. SSL bundle ở client không tự bật authentication ở OPA server.

Rego tương ứng:

~~~rego
package app.documents

import rego.v1

default allow := false

tenant_match if {
    input.verifiedTenant == input.resourceTenant
}

known_role if {
    input.role == "READER"
}
known_role if {
    input.role == "EDITOR"
}

allow if {
    tenant_match
    input.action == "READ"
    input.resourceType == "Document"
    input.classification == "INTERNAL"
    known_role
}

allow if {
    tenant_match
    input.action == "READ"
    input.resourceType == "Document"
    input.classification == "CONFIDENTIAL"
    input.role == "EDITOR"
    input.ownerMatches == true
}
~~~

Khi field thiếu/lạ, default false. Đây là Rego logic minh họa, chưa có production policy rollout, bundle signatures và external PIP trust rules. Một mock REST client test chỉ chứng minh parse/shape. Mở kết nối thật bằng mTLS test environment để thử missing/expired cert, wrong hostname, 401/403 và API quản trị bị hạn chế.

## 9. Java 17 độc lập: thuộc tính tối thiểu và fail closed

Chương trình **chạy bằng JDK thuần**, không có Spring/OPA/TLS. Nó minh họa lookup theo tenant, role tin cậy từ map và chỉ gửi sáu attributes cho một policy cố định resource type Document.

Lưu `MinimalAttributeDemo.java`:

~~~java
import java.util.Map;

public class MinimalAttributeDemo {
    record Key(String tenant, long id) {}
    record Doc(String tenant, String classification,
               String owner, String title) {}
    record User(String name, Map<String,String> roles) {}
    record MinimalInput(String verifiedTenant,
                        String resourceTenant, String role,
                        String action, String classification,
                        boolean ownerMatches) {}

    static final Map<Key,Doc> DATA = Map.of(
            new Key("alpha",7L),
                new Doc("alpha","CONFIDENTIAL","alice","ALPHA:Secret"),
            new Key("beta",7L),
                new Doc("beta","INTERNAL","bob","BETA:Public"),
            new Key("beta",9L),
                new Doc("beta","INTERNAL","bob","BETA:Another"));

    static boolean policy(MinimalInput in) {
        if (!in.verifiedTenant().equals(in.resourceTenant())
                || !"READ".equals(in.action())) return false;
        boolean known = "EDITOR".equals(in.role())
                || "READER".equals(in.role());
        if ("INTERNAL".equals(in.classification())) return known;
        if ("CONFIDENTIAL".equals(in.classification())) {
            return "EDITOR".equals(in.role()) && in.ownerMatches();
        }
        return false;
    }

    static String read(User user, String tenant, long id,
                       boolean pdpAvailable) {
        if (user == null || tenant == null) return "DENY_TENANT";
        String role = user.roles().get(tenant);
        if (role == null) return "DENY_TENANT";
        Doc doc = DATA.get(new Key(tenant,id));
        if (doc == null) return "NOT_FOUND";
        MinimalInput input = new MinimalInput(
                tenant,doc.tenant(),role,"READ",
                doc.classification(),user.name().equals(doc.owner()));
        if (!pdpAvailable) return "DENY_UNAVAILABLE";
        if (!policy(input)) return "DENY_POLICY";
        return "ALLOW:" + doc.title();
    }

    public static void main(String[] args) {
        User alice = new User("alice",Map.of("alpha","EDITOR"));
        User bob = new User("bob",Map.of("beta","READER"));
        User carol = new User("carol",Map.of("alpha","READER"));

        System.out.println("alice-alpha=" +
                read(alice,"alpha",7L,true));
        System.out.println("bob-beta=" +
                read(bob,"beta",7L,true));
        System.out.println("bob-alpha=" +
                read(bob,"alpha",7L,true));
        System.out.println("carol-confidential=" +
                read(carol,"alpha",7L,true));
        System.out.println("beta-resource-via-alpha=" +
                read(alice,"alpha",9L,true));
        System.out.println("pdp-unavailable=" +
                read(alice,"alpha",7L,false));

        MinimalInput input = new MinimalInput(
                "alpha","alpha","EDITOR","READ","CONFIDENTIAL",true);
        System.out.println("payload-fields=" +
                MinimalInput.class.getRecordComponents().length);
        System.out.println("payload-contains-title=" +
                input.toString().contains("ALPHA:Secret"));
    }
}
~~~

Lệnh:

~~~bash
javac --release 17 MinimalAttributeDemo.java
java MinimalAttributeDemo
~~~

Stdout chính xác:

~~~text
alice-alpha=ALLOW:ALPHA:Secret
bob-beta=ALLOW:BETA:Public
bob-alpha=DENY_TENANT
carol-confidential=DENY_POLICY
beta-resource-via-alpha=NOT_FOUND
pdp-unavailable=DENY_UNAVAILABLE
payload-fields=6
payload-contains-title=false
~~~

Chương trình chứng minh logic minimal payload, không xác thực HTTPS hay user credentials. Với production Java, việc đóng gói request qua HTTP phải được làm trong service authenticated và host-bound.

## 10. Quyền động, cache và TOCTOU

Giữa t1 PDP quyết định và t2 SQL update, owner/classification/tenant hoặc membership có thể đổi. Với hành động ghi nhạy cảm, bảo vệ bằng transaction, optimistic version/lock và conditional predicate:

~~~sql
UPDATE document
SET title = :newTitle, version = version + 1
WHERE tenant_id = :verifiedTenant
  AND id = :id
  AND version = :expectedVersion;
~~~

Kiểm row count, không fallback sang UPDATE thiếu tenant. Nếu rule phụ thuộc classification/owner, xác minh cùng transaction hoặc thêm predicate/version theo data model.

**Cache ALLOW** phải có key đủ tenant, principal, resource type/id, action, membership/ACL/policy/resource revision thật và invalidation đúng. Với dữ liệu nhạy cảm, không cache ALLOW thường đơn giản và an toàn hơn. TTL 5 phút không tự đáp ứng revoke ngay. Token role cũ và sidecar bundle eventual consistency cũng có thể stale dù không cache decision.

`{"result":true}` không phải bearer token được reuse giữa resources. Nếu dùng signed decision token, cần audience/action/subject/tenant/resource binding, expiry, nonce/replay protections và signature được review, không tự nghĩ crypto scheme.

PDP unavailable: bounded timeouts, circuit breaker, retry có giới hạn, rate limiting, local PDP/sidecar nếu cần availability; không dùng `catch(Exception) { return true; }`.

Với `@Async`/queue, thread-local security context/tenant có thể bị mất hoặc rò giữa tasks. Dùng context capture/cleanup trong `finally`, explicit trusted tenant parameters và worker revalidate rights ở use-time. Không serialize nguyên SecurityContext/JWT vào queue như quyết định vĩnh viễn.

## 11. Decision logs và dữ liệu cá nhân

PEP có thể lưu actor stable ID, resource type/ID, verified tenant, action, decision outcome, request correlation ID và PDP decision ID; PDP chỉ cần minimal PdpInput. OPA decision log khi bật có thể lưu input/result/bundle revision, có `data.system.log.mask` để xóa/mask sensitive fields. Kiểm cả application, HTTP client, APM, ingress và exporters; không log authorization headers, document body, email, access token, client private keys.

mTLS giảm nguy cơ nghe lén nhưng **không xóa** nghĩa vụ privacy của dữ liệu tenant/role/opaque IDs. Khi PDP ở region khác, đánh giá residency, retention, người xem logs và khả năng re-identification. PDP ALLOW không chứng minh file đã được download xong; muốn điều tra cần nối response/business/storage access log.

## 12. Ma trận kiểm thử trước production

| Case | Kết quả mong muốn |
| --- | --- |
| Alice owner confidential, role EDITOR alpha | ALLOW |
| Bob role READER beta, cùng ID 7 | ALLOW beta, không lộ alpha |
| Bob chọn alpha | DENY trước PDP |
| Carol READER alpha trên doc confidential Alice | DENY |
| Tenant selector/path giả, role header giả | Không đổi trusted attributes |
| Client giả classification/ownerMatches | PEP dùng DB/auth, không body |
| Resource không tồn tại trong tenant | 404/no metadata leak |
| User anonymous hoặc thiếu feature authority | DENY |
| Null/enum lạ/cấu trúc JSON sai | DENY/error closed |
| PDP `{"result":true}` | ALLOW nếu local invariants đạt |
| PDP `{"result":false}` hoặc `{}` | DENY |
| HTTP 200 nhưng result sai type | ERROR CLOSED |
| PDP 401/403/500 hoặc timeout | Không grant |
| Untrusted CA, wrong hostname, expired client cert | Không nối/không grant |
| Runtime service thử update policy | PDP authorization từ chối |
| Cross-host redirect/SSRF | Bị chặn |
| Membership/ACL revoked sau cache warm | Không dùng stale ALLOW |
| Resource đổi state giữa check/write | Transaction/version guard |
| @Async worker tái sử dụng thread | Không giữ tenant cũ |
| Decision logs bật | Không có raw JWT/content/PII thừa |
| MockRestServiceServer test xanh | Không tuyên bố mTLS đã test |
| Multi-PDP policy revision mismatch | Monitoring theo consistency contract |

Mutation testing: cố tình bỏ membership check, bỏ tenant predicate, đổi `ownerMatches` thành true hoặc coi HTTP 200 là ALLOW — test negative phải đỏ. Nếu không đỏ, suite chưa bảo vệ ranh giới.

## 13. Lỗi phổ biến và biện pháp

- Gửi raw token/Authentication/JPA entity: thay bằng typed attributes whitelist.
- Trust role/tenant từ header hoặc JSON: verify ở authentication/membership/DB.
- TLS không có workload identity: thêm mTLS/token và PDP authorization.
- Tắt certificate validation: sửa CA/SAN/truststore, không trust-all.
- Cho PEP service query/update mọi OPA API: giới hạn policy endpoint.
- HTTP 200 là ALLOW: chỉ Boolean true đúng contract.
- PDP timeout thì permitAll: là fail open, phải deny/503 không side-effect.
- Cache decision theo document ID: thiếu tenant/principal/action/revisions.
- Không kiểm resource state giữa PDP decision và DB write: dùng transaction/version checks.
- Owner boolean được client khai: tính từ principal + DB, hoặc PDP tự lấy từ PIP.
- Tin mọi IP/region/device header: environment source cần attestation/trusted proxy.
- Log toàn input: OPA decision logs có thể trở thành kho PII.
- Mock local PDP được coi là chứng minh TLS: phải có TLS/certificate integration tests.
- Coi result ALLOW là token vĩnh viễn: decision gắn context, không replay tùy ý.
- PDP URL client-controlled: SSRF/exfiltration, dùng allowlist.
- Async context không clear: dễ rò tenant/role sang task sau.

## 14. Bài tập tự kiểm tra

**Câu 1:** Policy chỉ cần ownerMatches. Có nên gửi owner email và document body không?

**Đáp án:** Không, nếu PEP tính boolean từ nguồn tin cậy; nếu PDP không tin PEP, cần PIP độc lập chứ không tự gửi cả entity.

**Câu 2:** Alice EDITOR alpha và VIEWER beta, request beta. Role nào vào PDP?

**Đáp án:** Role đã xác minh của beta, không dùng EDITOR alpha.

**Câu 3:** OPA trả 200 và body `{}`. Có cho READ không?

**Đáp án:** Không; result undefined, fail closed.

**Câu 4:** mTLS hợp lệ chứng minh được ownerMatches đúng không?

**Đáp án:** Không; nó xác thực workload và bảo vệ channel, không chứng minh semantic data đúng.

**Câu 5:** MockMvc local PDP test xanh có chứng minh SSL client cert config đúng không?

**Đáp án:** Không; cần handshake/hostname/mTLS/API-authorization integration test riêng.

**Câu 6:** PDP outage khi muốn DELETE có được bỏ qua không?

**Đáp án:** Không. Deny hoặc 503 mà không thực thi protected operation.

## 15. Tóm tắt

~~~text
Authenticated user
  + verified tenant membership and role
  + tenant-scoped resource metadata
  + trusted action/environment
     -> minimal typed PDP input
     -> HTTPS verified PDP + authenticated PEP workload
     -> PDP evaluates policy
     -> ONLY Boolean TRUE permits enforcement
     -> protected operation within current data/transaction scope
     -> minimal audit with decision/correlation ID
~~~

**Ba yêu cầu gắn chặt:** (1) **chỉ gửi thuộc tính cần thiết**; (2) **xác minh provenance và freshness**, không tin client tự khai; (3) **bảo vệ kênh và thực thi fail closed** bằng TLS/mTLS hoặc service token, PDP authz, PEP enforcement và transaction/data scoping. Thiếu bất cứ một phần nào đều có thể làm chính sách động cấp sai quyền hoặc lộ dữ liệu.

## Tài liệu tham khảo chính thức

- [NIST SP 800-162 – ABAC Definition and Considerations](https://csrc.nist.gov/pubs/sp/800/162/upd2/final): ABAC/PEP/PDP/PIP.
- [OPA – Integration](https://www.openpolicyagent.org/docs/integration): named Data API decisions, sidecar.
- [OPA – REST API](https://www.openpolicyagent.org/docs/rest-api): input, result, undefined response.
- [OPA – Security](https://www.openpolicyagent.org/docs/security): TLS, mTLS, API authentication/authorization.
- [OPA – Decision Logs](https://www.openpolicyagent.org/docs/management-decision-logs): input, decision_id, masking.
- [Spring Security – Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html): @EnableMethodSecurity/@PreAuthorize.
- [Spring Security – JWT Resource Server](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html): JWT validation.
- [Spring Boot 3.5 RestClientSsl API](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/autoconfigure/web/client/RestClientSsl.html): SSL bundles for RestClient.
- [Spring Boot – SSL Bundles](https://docs.spring.io/spring-boot/reference/features/ssl.html): TLS trust/key material.
