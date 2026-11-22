# Bảo vệ luồng nghiệp vụ nhạy cảm khỏi tự động hóa lạm dụng

API **POST /v1/campaigns/{id}/redemptions** có thể nhận JWT và JSON hợp lệ nhưng vẫn bị tài khoản tự động vét ưu đãi. Tương tự, request giữ hàng hợp lệ có thể khóa tồn kho hàng loạt. **Authentication/authorization đúng chưa đủ chống lạm dụng hành động hợp lệ.**

Bài thuộc **Phân quyền và an toàn**, module **INTEGRATION_API_REST**, kết hợp HTTP, idempotency, Java/Spring, giới hạn nghiệp vụ và kiểm thử. Giảm lạm dụng nhưng vẫn tôn trọng người dùng thật, trợ năng và quyền riêng tư.

## 1. Mục tiêu học tập và phạm vi

Sau bài này, bạn có thể:

1. Phân biệt **bot traffic hợp lệ**, hành vi tự động hóa có ích, **resource exhaustion**, **BOLA/IDOR** và **abuse of sensitive business flows**.
2. Nhận diện bất biến nghiệp vụ cần bảo vệ ở **đăng ký, gửi OTP, giữ hàng, áp mã, mua hàng, rút tiền và nhận thưởng**.
3. Thiết kế nhiều lớp: **xác thực → phân quyền → giới hạn tốc độ/chi phí → chính sách rủi ro → cập nhật dữ liệu nguyên tử → audit**.
4. Chọn **quota, rate limit, concurrency limit, CAPTCHA/challenge, step-up MFA** theo tín hiệu đáng tin và tác động lên người dùng.
5. Dùng **HTTP 429, Retry-After, 401, 403, 404, 409, 412, 422** rõ ngữ nghĩa và trả **Problem Details** nhất quán.
6. Triển khai ví dụ Spring Boot/Spring Security cùng Redis atomic counter và SQL conditional update, nắm giới hạn của các biện pháp.
7. Kiểm thử đồng thời, replay, thay tenant, vượt quota, lỗi Redis/DB, false positive và khả năng phục hồi sau sự cố.

**Abuse** phụ thuộc tác động cả chuỗi hành động, không phải lỗi cú pháp. **Không phải mọi automation đều xấu**: batch đối tác, trợ năng và người dùng nhanh có thể hợp lệ. Cần đo false positive và có ngoại lệ/kháng nghị.

## 2. Mô hình đe dọa theo hành trình nghiệp vụ

Mô hình hóa **người nhận lợi ích, tài nguyên bị giữ/tiêu thụ, thao tác không đảo ngược và tín hiệu vượt mục tiêu sản phẩm**.

| Luồng | Lạm dụng cần phòng | Bất biến cần giữ | Kiểm soát điển hình |
|---|---|---|---|
| Đăng ký/đăng nhập | Tạo tài khoản hàng loạt, credential stuffing | Giới hạn chi phí xác thực, không lộ tài khoản | Rate limit đa chiều, phát hiện rủi ro, MFA phù hợp |
| Gửi OTP/reset password | OTP bombing, dò mã, user enumeration | Mã một lần, TTL ngắn, giới hạn thử | Quota theo account/đích, cooldown, consume atomically |
| Giữ vé/đặt chỗ | Scalping, giữ chỗ rồi bỏ | Số giữ chỗ không vượt tồn, TTL/cleanup đúng | Quota actor/beneficiary, hold atomic, lease expiration |
| Khuyến mãi/điểm thưởng | Tài khoản ảo, nhận trùng, lạm dụng referral | Mỗi đối tượng nhận đúng số quyền lợi | Unique constraint, eligibility, risk review |
| Checkout/thanh toán | Card testing, mua lượng bất thường, replay | Không trùng đơn/thu tiền, không âm kho | Idempotency, step-up, giới hạn chi phí, kiểm soát PSP |
| Đổi tài khoản nhận tiền | Account takeover, đổi đích và rút ngay | Người có quyền thật xác nhận thay đổi | Re-auth/step-up, cooling-off, cảnh báo và audit |
| API tìm kiếm/xuất báo cáo | Scraping, tạo job tốn chi phí | Công bằng tài nguyên/chi phí | Pagination/max size, cost budget, async job quota |

**BOLA** là truy cập resource ngoài quyền; **business-flow abuse** có thể xảy ra trên chính resource hợp lệ. **Rate limit không thay authorization**, và ngược lại.

### 2.1. Tài sản, actor và ranh giới tin cậy

Xác định user, tenant, session, thiết bị, người thụ hưởng, ưu đãi, tồn kho và lệnh thanh toán. Các ranh giới tin cậy:

- **JWT/session đã xác thực** là cơ sở nhận dạng người gọi, nhưng không chứng minh một người chỉ có một tài khoản hoặc thiết bị.
- **IP, User-Agent, device fingerprint** chỉ là tín hiệu tương quan, có thể chia sẻ, thay đổi hoặc giả mạo; không dùng làm định danh người dùng duy nhất.
- **tenantId, userId, promoCode, beneficiaryId trong JSON/query** là đầu vào cần kiểm tra, không phải bằng chứng quyền.
- **Webhook, message queue và retry của đối tác** cũng có thể tái gửi: cần kiểm tra chữ ký, nguồn tin cậy và chống trùng theo operation ID.
- **CDN/WAF/gateway** chỉ thấy một phần HTTP; service/database mới biết giao dịch có vi phạm bất biến nghiệp vụ hay không.

### 2.2. Bản đồ một luồng nhạy cảm

~~~mermaid
flowchart TD
    A["Client POST /redemptions"] --> B["Gateway: TLS, max body, admission"]
    B --> C["Spring Security: token/issuer/audience"]
    C --> D["Service: owner/tenant/eligibility"]
    D --> E{"Risk / policy budget"}
    E -->|Chặn hoặc cần xác minh| F["429 / 403 / step-up có contract"]
    E -->|Cho tiếp tục| G["DB transaction: quota + unique + inventory"]
    G -->|Đã dùng/quá quota| H["409 hoặc kết quả replay idempotent"]
    G -->|Commit| I["201 + Location / kết quả"]
    G --> J["Outbox + audit chống trùng"]
~~~

Sơ đồ minh họa; thứ tự chi tiết tùy hợp đồng. Nhận diện **replay cùng Idempotency-Key sau authz**, trước khi tính một lần nhận quyền lợi mới; vẫn giới hạn replay spam.

## 3. Các giới hạn khác nhau bảo vệ những thứ khác nhau

### 3.1. Rate limit, quota và concurrency

| Cơ chế | Câu hỏi được giải quyết | Ví dụ |
|---|---|---|
| **Rate limit** | Cho phép bao nhiêu request trong đơn vị thời gian? | 6 lần gửi OTP / 10 phút / tài khoản |
| **Business quota** | Một người hoặc người thụ hưởng được nhận bao nhiêu quyền lợi? | 1 lượt nhận mã / chiến dịch / người đủ điều kiện |
| **Concurrency limit** | Bao nhiêu tác vụ cùng chạy/giữ slot? | 2 job xuất báo cáo đang chạy / tenant |
| **Cost budget** | Tổng tài nguyên/tiền/đối tượng bị tiêu tốn bao nhiêu? | 100.000 đơn vị compute / ngày / tenant |
| **Velocity signal** | Chuỗi hành vi tăng đột biến bất thường thế nào? | Nhiều tài khoản đổi cùng đích nhận tiền |
| **Global circuit breaker** | Có cần bảo vệ hệ thống khi upstream/DB bão hòa? | Tạm hạn chế tạo job mới lúc queue đầy |

**Rate limit khác business quota:** bot chậm vẫn vét ưu đãi; OTP lỗi vẫn tốn SMS/CPU. Gateway bảo vệ tải chung, service áp policy, **database bảo vệ bất biến**.

### 3.2. Thiết kế key cho từng giới hạn

Key dựa trên **tenant + verified actor + operation + beneficiary**. Chuẩn hóa email/điện thoại trước khi pseudonymize bằng **HMAC**; không lưu PII/token/session ID thô trong key/log.

IP chỉ là tín hiệu bổ sung: NAT có thể cho nhiều khách chung địa chỉ. **Forwarded/X-Forwarded-For** chỉ đáng tin khi ingress đã strip/overwrite header của client.

Pre-auth cần quota theo mạng, đích OTP và ngân sách chung; tránh khóa tài khoản chỉ vì attacker gửi nhiều lần thử.

### 3.3. Các thuật toán giới hạn tốc độ

- **Fixed window counter:** dễ triển khai Redis INCR/EXPIRE, nhưng có thể tạo burst gần ranh giới cửa sổ.
- **Sliding window/log:** công bằng hơn trong thời gian, đổi lại bộ nhớ và CPU; log có thể tăng cao nếu không dọn TTL.
- **Token bucket:** cho phép burst nhỏ rồi hồi token theo tốc độ ổn định, phù hợp API interactive.
- **Leaky bucket/queue:** làm mượt tốc độ xử lý; phải giới hạn hàng đợi và thời gian chờ, không tự xếp công việc vô hạn.

Chọn theo user/downstream, đo tải, chi phí và false positive; không có ngưỡng chuẩn cho mọi API.

## 4. Hợp đồng HTTP khi hạn chế hoặc từ chối

API phải giải thích phản hồi đủ cho client, **không tiết lộ logic phát hiện gian lận**.

~~~http
POST /v1/campaigns/c-17/redemptions HTTP/1.1
Host: api.example.test
Authorization: Bearer <access-token>
Idempotency-Key: redeem-c17-transaction-019
Content-Type: application/json

{"offerCode":"WELCOME-17"}
~~~

Một response giới hạn tạm thời:

~~~http
HTTP/1.1 429 Too Many Requests
Retry-After: 60
Content-Type: application/problem+json
Cache-Control: no-store

{
  "type": "https://api.example.test/problems/rate-limited",
  "title": "Too many requests",
  "status": 429,
  "detail": "Please retry later.",
  "code": "RATE_LIMITED"
}
~~~

**Retry-After** nhận số giây hoặc HTTP-date; client cần jitter/backoff, tránh **thundering herd**. Không trả 429 cho quyền lợi đã nhận hết, khiến client tưởng chờ là được.

| Nguyên nhân | HTTP thường phù hợp | Ghi chú |
|---|---|---|
| Thiếu/hết hạn credential | **401 Unauthorized** | Challenge phù hợp; không tự biến thành 429 |
| Đã xác thực nhưng không có quyền | **403 Forbidden** hoặc **404 che resource** | Không công bố owner/tenant khác |
| JSON/giới hạn field sai | **400 Bad Request** | Validation trước workflow; không lộ dữ liệu |
| Vượt nhịp request tạm thời | **429 Too Many Requests** | Retry-After hoặc rate-limit metadata nếu hợp đồng có |
| Đã nhận thưởng/quota nghiệp vụ hết | **409 Conflict**, hoặc **422** theo domain | Không khuyến khích retry vô nghĩa |
| Thay đổi resource với ETag cũ | **412 Precondition Failed** | Phân biệt với limit |
| Cần xác thực tăng cường | **401/403 + challenge hợp đồng** | Không coi CAPTCHA là quyền truy cập |
| Server quá tải/phụ thuộc tạm lỗi | **503 Service Unavailable** | Retry theo budget, không báo user “gian lận” |

**Problem Details (RFC 9457)** cần mã lỗi ổn định, trace ID an toàn; không phát fingerprint, lý do rủi ro nội bộ, SQL hoặc secret.

## 5. Giới hạn có tính nguyên tử trong hệ nhiều replica

Bốn instance với counter RAM riêng có thể cho vượt quota nhiều lần. Dùng **shared/atomic counter**, và bảo vệ quyền lợi bằng **database transaction**.

### 5.1. Fixed-window Redis INCR + EXPIRE qua Lua

Ví dụ **10 lần thử / 60 giây / actor + campaign**. Lua cho **INCR + EXPIRE nguyên tử** trên Redis dùng chung.

~~~lua
-- KEYS[1]: key đã pseudonymize bởi server.
-- ARGV[1]: thời gian sống tính bằng giây.
local n = redis.call('INCR', KEYS[1])
if n == 1 then
    redis.call('EXPIRE', KEYS[1], tonumber(ARGV[1]))
end
return n
~~~

Spring Data Redis (Java 17, Spring Boot 3) có thể gọi Lua từ class service:

~~~java
import java.time.Duration;
import java.util.List;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.data.redis.core.script.DefaultRedisScript;
import org.springframework.stereotype.Component;

@Component
class RedemptionRateBudget {
    private static final int MAX_PER_WINDOW = 10;
    private static final int WINDOW_SECONDS = 60;
    private static final String SCRIPT = """
            local n = redis.call('INCR', KEYS[1])
            if n == 1 then
                redis.call('EXPIRE', KEYS[1], tonumber(ARGV[1]))
            end
            return n
            """;

    private final StringRedisTemplate redis;
    private final DefaultRedisScript<Long> incrementScript;

    RedemptionRateBudget(StringRedisTemplate redis) {
        this.redis = redis;
        this.incrementScript = new DefaultRedisScript<>();
        this.incrementScript.setScriptText(SCRIPT);
        this.incrementScript.setResultType(Long.class);
    }

    boolean allow(String pseudonymousActorCampaignKey) {
        String key = "abuse:redemption:" + pseudonymousActorCampaignKey;
        Long count = redis.execute(incrementScript,
                List.of(key), String.valueOf(WINDOW_SECONDS));
        if (count == null) {
            throw new IllegalStateException("Budget unavailable");
        }
        return count <= MAX_PER_WINDOW;
    }
}
~~~

**Giới hạn:** fixed window tính từ request đầu có thể burst ở ranh giới; counter không chứng minh danh tính, công bằng hay lượt nhận thành công. Redis failover có thể mất counter; **không dùng nó làm bảo vệ tài chính cuối cùng**.

Key quota do server sinh từ identity/campaign đã xác minh và **HMAC**. Không dùng raw email/JWT hoặc key do client chọn; OTP cần quota theo đích, không chỉ IP.

### 5.2. Cho phép hoặc từ chối khi Redis hỏng?

Không có một chính sách fail-open/fail-closed cho mọi route:

- **Đăng ký bản tin/đọc catalog**: có thể suy giảm sang quota bảo thủ tại gateway và ghi cảnh báo nếu rủi ro chấp nhận được.
- **Nhận coupon có ngân sách, rút tiền, OTP trả phí**: thường ưu tiên không tiếp tục bước tiêu tốn giá trị khi không chứng minh được quota; trả **503** với thông điệp trung tính, có retry budget.
- **Request đang có kết quả idempotent đã ghi**: nếu hệ dữ liệu xác minh được kết quả cũ, có thể trả lại nó theo hợp đồng mà không tạo operation mới.

Có **SLO/runbook** cho Redis; không ngụy trang outage thành 429 hoặc fallback RAM không kiểm soát. Test failover/TTL/multi-replica.

### 5.3. Rate limiting không thay concurrency limit

Một job kéo dài 20 phút vẫn tốn tài nguyên dù RPS thấp. Giới hạn **QUEUED/RUNNING**, dùng lease/TTL, cleanup và queue capacity. Không trả 202 nếu job chưa được nhận bền vững.

## 6. Bảo vệ bất biến tại database thay vì chỉ chặn bot

Với chiến dịch **100 lượt**, mỗi beneficiary nhận một lần, hai request có thể cùng đọc **remaining=1** và cùng trừ nếu chỉ check-then-act:

~~~text
// Anti-pattern: hai transaction cùng đọc remaining = 1.
if (campaign.remaining > 0 && !alreadyRedeemed(user)) {
    campaign.remaining--;
    createRedemption();
}
~~~

Thay bằng **giao dịch và ràng buộc dữ liệu**:

~~~sql
-- Thực hiện trong transaction; cần WHERE tenant/campaign đúng.
UPDATE campaigns
   SET remaining = remaining - 1
 WHERE id = :campaign_id
   AND tenant_id = :tenant_id
   AND status = 'ACTIVE'
   AND starts_at <= CURRENT_TIMESTAMP
   AND ends_at > CURRENT_TIMESTAMP
   AND remaining > 0;

-- Chỉ tiếp tục khi affected_rows = 1.
INSERT INTO redemptions
       (id, campaign_id, tenant_id, beneficiary_id, created_at)
VALUES (:redemption_id, :campaign_id, :tenant_id,
        :beneficiary_id, CURRENT_TIMESTAMP);
~~~

Thêm **UNIQUE (tenant_id, campaign_id, beneficiary_id)** và foreign key phù hợp. Insert lỗi phải rollback cả decrement; kiểm tra **affected rows = 1**, không tin cache precheck. Quota xuyên chiến dịch cần ledger/constraint riêng.

Unique userId không chống một người nhiều tài khoản. Xác minh beneficiary hợp pháp, tối thiểu hóa dữ liệu; fingerprint không phải identity.

### 6.1. State machine ngăn lặp hoặc vượt bước

Giữ chỗ/thu tiền nên có trạng thái và chuyển tiếp có điều kiện:

~~~text
NEW -> ELIGIBLE -> RESERVED -> CONFIRMED
                   |            |
                   v            v
                 EXPIRED      REFUNDED
~~~

**confirm** đòi đúng actor/tenant, TTL và state; conditional UPDATE theo status/version. Worker/webhook cũng phải tuân state machine.

### 6.2. Idempotency phục vụ retry, không phải quota nhận thưởng

**Idempotency-Key** xác định **logical operation** cho retry, **không cấp thêm quyền lợi**. Server cần:

1. **Scope** key theo tenant/principal/operation và xác thực actor.
2. Lưu **fingerprint payload**; cùng key khác payload phải bị từ chối.
3. Lưu trạng thái/kết quả/TTL với **unique constraint và transaction**.
4. Replay trả kết quả cũ hoặc trạng thái processing, **không tạo side effect mới**.
5. Timeout sau commit cần đối soát operation status.

Ví dụ ràng buộc:

~~~sql
CREATE UNIQUE INDEX uq_redemption_operation
    ON redemption_operations
       (tenant_id, actor_id, operation_key);

CREATE UNIQUE INDEX uq_redemption_benefit
    ON redemptions
       (tenant_id, campaign_id, beneficiary_id);
~~~

Hai request cùng key có thể đến trước commit: dùng **unique claim**, chờ/trả in-progress và đọc kết quả sau commit. **DataIntegrityViolationException** thường yêu cầu transaction mới để đọc lại; không giữ PII/thẻ trong fingerprint hoặc log.

### 6.3. Bảo vệ thứ tự thao tác và ngân sách

Với **hoàn tiền/đổi thụ hưởng rồi rút tiền**, thêm xác minh beneficiary, **cooling-off**, step-up MFA, quota số tiền, kiểm tra số dư nguyên tử và review. Đây là **policy server**, không dựa JavaScript.

PSP không rollback cùng DB: dùng operation ID, idempotency, outbox, event dedupe và đối soát **PENDING/UNKNOWN** sau timeout.

## 7. Chính sách dựa trên rủi ro, xác minh tăng cường và công bằng

CAPTCHA/khóa tài khoản cho mọi request có thể bị lạm dụng thành DoS với nạn nhân. Phân lớp theo **giá trị, velocity, lịch sử, thiết bị và người nhận quyền lợi**.

| Mức rủi ro | Phản ứng điển hình | Điểm cần lưu ý |
|---|---|---|
| Thấp | Cho xử lý, ghi telemetry tối thiểu | Không tăng friction vô ích |
| Tăng bất thường | Rate limit, giảm concurrency hoặc cooldown | Có Retry-After chính xác, không “shadow ban” tùy tiện |
| Nghi vấn cần xác minh | Step-up MFA/re-auth/challenge | Kiểm tra bằng chứng server-side, có lối đi cho trợ năng |
| Giá trị cao/thiệt hại lớn | Giữ trạng thái PENDING_REVIEW, kiểm tra bổ sung | Không báo đã hoàn tất/đã ghi có khi chưa commit |
| Có bằng chứng lạm dụng rõ | Từ chối, cảnh báo, điều tra, thu hồi quyền hợp lệ | Có audit, chính sách kháng nghị và hạn chế chia sẻ dữ liệu |

**CAPTCHA không thay authz/quota/DB**. Xác minh challenge **server-side** với action, TTL và chống replay; không tin flag JavaScript. Hỗ trợ trợ năng và đường xác minh thay thế.

**Step-up MFA** cho đổi thụ hưởng/rút tiền lớn cần kiểm tra **auth_time, acr/amr** theo IdP, gắn với principal, action, transaction và TTL; login MFA trước đó không tự đủ.

Đo **false-positive rate**, retention và kháng nghị; chỉ lưu reason code tối thiểu, không phát luật chặn chi tiết.

## 8. Java/Spring: một API nhận quyền lợi có kiểm soát

Ví dụ Spring Boot 3/Java 17 với JWT và DB atomic commit. **Bộ khung** cần triển khai identity, service, Redis/SQL và chính sách rủi ro.

### 8.1. Bảo vệ route bằng Spring Security

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class RedemptionSecurity {
    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        http.authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.POST,
                        "/v1/campaigns/*/redemptions")
                    .hasAuthority("SCOPE_campaign:redeem")
                .anyRequest().authenticated())
            .oauth2ResourceServer(oauth2 ->
                    oauth2.jwt(Customizer.withDefaults()))
            .sessionManagement(session ->
                    session.sessionCreationPolicy(
                            SessionCreationPolicy.STATELESS))
            .csrf(csrf -> csrf.disable());
        return http.build();
    }
}
~~~

Chỉ **tắt CSRF** cho API bearer-only không dùng cookie tự gửi; browser session/BFF vẫn cần CSRF. Kiểm tra JWT **issuer, audience, lifetime, algorithm**; scope không thay authz theo tenant/beneficiary.

### 8.2. Controller chỉ điều phối HTTP

~~~java
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;
import java.net.URI;
import java.util.UUID;
import org.springframework.http.CacheControl;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.util.UriComponentsBuilder;

record RedemptionInput(@NotBlank @Size(max = 80) String offerCode) {}
record RedemptionView(UUID id, String status) {}
record VerifiedActor(UUID tenantId, UUID userId) {}

interface VerifiedActorResolver {
    VerifiedActor fromValidatedJwt(Jwt jwt);
}

interface RedemptionWorkflow {
    // Key scoped theo actor/operation và response replay.
    RedemptionView redeem(VerifiedActor actor, UUID campaignId,
                          RedemptionInput input, String idempotencyKey);
}

@RestController
@RequestMapping("/v1/campaigns/{campaignId}/redemptions")
class RedemptionController {
    private final RedemptionWorkflow workflow;
    private final VerifiedActorResolver actorResolver;

    RedemptionController(RedemptionWorkflow workflow,
            VerifiedActorResolver actorResolver) {
        this.workflow = workflow;
        this.actorResolver = actorResolver;
    }

    @PostMapping(consumes = MediaType.APPLICATION_JSON_VALUE)
    ResponseEntity<RedemptionView> redeem(
            @PathVariable UUID campaignId,
            @RequestHeader("Idempotency-Key") String idemKey,
            @Valid @RequestBody RedemptionInput input,
            @AuthenticationPrincipal Jwt jwt) {
        VerifiedActor actor = actorResolver.fromValidatedJwt(jwt);
        RedemptionView result = workflow.redeem(
                actor, campaignId, input, idemKey);
        URI location = UriComponentsBuilder
                .fromPath("/v1/redemptions/{id}")
                .encode().buildAndExpand(result.id()).toUri();

        return ResponseEntity.created(location)
                .cacheControl(CacheControl.noStore())
                .body(result);
    }
}
~~~

**201 + Location** chỉ khi tạo mới. Replay cùng key phải trả kết quả/status/headers ban đầu theo contract; controller chưa minh họa nhánh replay. Key mới không được nhận thêm quyền lợi.

Validate Idempotency-Key, scope/fingerprint; không tin tenant tự khai. **Relative Location** tránh Host giả; absolute URL phải dùng public base đáng tin.

### 8.3. Ranh giới service: thứ tự kiểm soát

~~~text
1. Xác thực JWT -> actor từ issuer/audience/claims đã validate.
2. Kiểm tra campaign/tenant/beneficiary trong phạm vi được quyền xem.
3. Tra durable operation (actor, campaign, idemKey, payload fingerprint):
   - Đã hoàn tất + cùng payload -> trả kết quả đã lưu.
   - Khác payload -> từ chối; đang xử lý -> trả trạng thái phù hợp.
4. Với yêu cầu mới: rate/cost budget -> risk policy/step-up nếu cần.
5. Bắt đầu DB transaction:
   claim operation -> điều kiện campaign ACTIVE -> decrement remaining
   -> insert redemption UNIQUE beneficiary -> lưu kết quả -> outbox.
6. Commit; chỉ khi đó phát 201 + Location.
7. Consumer xử lý outbox idempotently; audit, metrics và cảnh báo.
~~~

**Authz trước khi tra operation ID** để tránh rò tenant. Không đếm replay như redemption mới, nhưng giới hạn replay spam. Redis/DB lỗi áp 503/fail-safe.

### 8.4. Exception mapping cho 429

~~~java
import java.net.URI;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ProblemDetail;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

class RateBudgetExceeded extends RuntimeException {}

@RestControllerAdvice
class AbuseProblemAdvice {
    @ExceptionHandler(RateBudgetExceeded.class)
    ResponseEntity<ProblemDetail> rateLimited(RateBudgetExceeded ignored) {
        ProblemDetail body = ProblemDetail.forStatusAndDetail(
                HttpStatus.TOO_MANY_REQUESTS, "Please retry later.");
        body.setType(URI.create(
                "https://api.example.test/problems/rate-limited"));
        body.setTitle("Too many requests");
        body.setProperty("code", "RATE_LIMITED");
        return ResponseEntity.status(HttpStatus.TOO_MANY_REQUESTS)
                .contentType(MediaType.valueOf("application/problem+json"))
                .header(HttpHeaders.RETRY_AFTER, "60")
                .header(HttpHeaders.CACHE_CONTROL, "no-store")
                .body(body);
    }
}
~~~

**Retry-After: 60** chỉ minh họa; thực tế dựa **TTL/reset time** và kiểm thử gateway. Mapping 409/422, 401/403, 503 riêng, không gom thành 429.

## 9. Kiểm thử theo luồng, bao gồm đồng thời và lỗi hạ tầng

| Tình huống | Kết quả phải chứng minh |
|---|---|
| Không có bearer token / sai scope | 401/403 từ security chain, không tạo redemption |
| JWT tenant A thao tác campaign của tenant B | 403/404 không lộ campaign, không tiêu ngân sách |
| Vượt 10 request/cửa sổ trên nhiều instance | Counter chung chặn theo policy, 429 + Retry-After |
| Cùng key và cùng payload sau commit | Replay trả kết quả cũ, **không trừ remaining lần hai** |
| Cùng key, payload khác | Bị từ chối, không dùng record của request khác |
| Hai key khác nhau cùng beneficiary | Unique constraint cho **tối đa một lượt**, rollback counter |
| Hai actor tranh slot cuối | Tổng redemption không vượt remaining ban đầu |
| Redis lỗi / DB timeout | 503/fail-safe theo policy, không coi là user abuse |
| Gửi OTP sai/lặp nhiều lần | Giới hạn thử và consume một lần, không lộ người nhận |
| Kịch bản NAT chia sẻ, trợ năng, đối tác batch | Đo false positive và có hạn mức/ngoại lệ duyệt |

MockMvc kiểm tra security boundary trước business workflow:

~~~java
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.jwt;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class RedemptionSecurityTest {
    @Autowired MockMvc mvc;

    private static final String URL =
        "/v1/campaigns/41ea9158-1338-4868-ac5d-ac04b2c6c7c0/redemptions";

    @Test
    void noTokenIsRejected() throws Exception {
        mvc.perform(post(URL)
                .header("Idempotency-Key", "operation-001")
                .contentType("application/json")
                .content("{\"offerCode\":\"WELCOME-17\"}"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void tokenWithoutScopeIsRejected() throws Exception {
        mvc.perform(post(URL)
                .with(jwt().authorities(
                        new SimpleGrantedAuthority("SCOPE_catalog:read")))
                .header("Idempotency-Key", "operation-002")
                .contentType("application/json")
                .content("{\"offerCode\":\"WELCOME-17\"}"))
            .andExpect(status().isForbidden());
    }
}
~~~

Mẫu cần JUnit/Spring imports và **spring-security-test**. **jwt() chỉ mock principal**, không test chữ ký/audience; bổ sung JWKS integration. Test Redis atomicity/TTL và DB race bằng **barrier + database thật**.

## 10. Vận hành, quyền riêng tư và ứng phó sự cố

Đo **allowed/throttled/challenged/replayed/committed**, p95, lỗi, quota, chi phí và queue; label theo route template/policy version, không raw JWT/PII.

Ngưỡng cần version/canary, theo dõi **false positive**, owner, retention và kháng nghị. Alert khi 429/503 tăng, Redis lỗi hoặc tồn âm; khi vi phạm bất biến, dừng ghi và đối soát ledger.

## 11. Bài tập: bảo vệ chiến dịch nhận voucher

Một chiến dịch có **100 voucher**; mỗi khách đủ điều kiện nhận tối đa một voucher, còn mỗi user được tối đa **6 lần thử mỗi phút**. API chạy bốn replica, có Redis, PostgreSQL và mobile client tự retry sau timeout. Một số khách dùng chung IP công ty, đối tác có batch job hợp lệ.

Hãy thiết kế: **(1)** các giới hạn theo user/campaign/beneficiary và IP bổ sung; **(2)** response 429 + Retry-After và 409 khi đã nhận; **(3)** transactional SQL để không nhận trùng/âm voucher; **(4)** idempotency key khi response mất; **(5)** ít nhất sáu test, trong đó có two-request race, Redis outage, tenant isolation và false positive; **(6)** phương án step-up/thẩm định thủ công công bằng.

**Gợi ý:** Redis giữ nhịp request, PostgreSQL là nguồn đúng cho ngân sách/unique beneficiary. Không chặn mọi nhân viên chỉ vì chung IP; dùng actor đã xác minh và quota theo quyền lợi. Replay cùng key chỉ đọc lại kết quả, không trừ thêm. Nếu Redis lỗi, áp fail-safe cho lượt nhận mới, nhưng không báo “người dùng gian lận” khi lỗi hạ tầng.

## 12. Checklist và tham khảo

- [ ] Có threat model theo **lợi ích, trạng thái và chi phí** chứ không chỉ RPS.
- [ ] JWT/session/tenant/owner được xác minh; tránh BOLA và key do client tự khai.
- [ ] Rate limit, quota, concurrency, risk policy và DB invariant có trách nhiệm riêng.
- [ ] Counter/quota atomically cập nhật; transaction và unique constraint chống race.
- [ ] Idempotency giải quyết replay, không thay anti-abuse; POST timeout không đồng nghĩa thất bại.
- [ ] 429/Retry-After, 409, 401/403/404, 503 và Problem Details dùng đúng ngữ nghĩa.
- [ ] Challenge/step-up không phá accessibility; có giám sát false positive và kháng nghị.
- [ ] Có integration test qua gateway, Redis, DB, multi-replica và fault injection.

Tham khảo: **OWASP API Security Top 10 (API4/Unrestricted Resource Consumption, API6/Unrestricted Access to Sensitive Business Flows)**, https://owasp.org/API-Security/editions/2023/en/0x11-t10/; **OWASP Automated Threats to Web Applications**, https://owasp.org/www-project-automated-threats-to-web-applications/; **RFC 9110 HTTP Semantics**, https://www.rfc-editor.org/rfc/rfc9110.html; **RFC 9457 Problem Details**, https://www.rfc-editor.org/rfc/rfc9457.html; **Spring Security**, https://docs.spring.io/spring-security/reference/; **Redis scripting**, https://redis.io/docs/latest/develop/programmability/eval-intro/.

**Kết luận:** Chống tự động hóa lạm dụng là **bảo vệ hành trình nghiệp vụ và quyền lợi** bằng nhiều lớp: nhận diện đúng actor, giới hạn chi phí, xác minh theo rủi ro, lưu trạng thái nguyên tử, chống replay và quan sát false positives. **Không một CAPTCHA, JWT, WAF hay rate limiter đơn lẻ nào thay thế được bất biến dữ liệu và kiểm tra quyền trên từng thao tác.**
