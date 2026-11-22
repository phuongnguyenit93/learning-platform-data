# 32.9. Đồng bộ thời gian hệ thống và xử lý clock skew

## 1. Bối cảnh: đăng nhập OIDC thành công ở node này nhưng lỗi ở node khác

Một hệ thống **Spring Boot + Spring Security OAuth 2.0/OIDC Client** hoạt động qua ba replicas, đăng nhập qua OpenID Provider (OP) và dùng access token để gọi Resource Server. Trong production, những lỗi khó tái hiện bắt đầu xuất hiện:

- User vừa đăng nhập nhưng Client từ chối ID Token vì <code>exp</code> đã qua hoặc <code>iat</code> ở tương lai.
- Access token dường như còn hạn ở Client nhưng Resource Server trả HTTP 401 <code>invalid_token</code>.
- Client refresh liên tục, trong khi node khác lại giữ token sắp hết hạn quá lâu.
- Resource Server báo JWT <code>nbf</code> “not yet valid” ngay sau khi OP phát token.
- TLS connection tới Discovery/JWKS/Token Endpoint bị báo certificate not yet valid.
- Người vận hành thấy logs lệch bảy giờ và tưởng đồng hồ server bị lỗi, trong khi đó chỉ là khác timezone hiển thị.

Đằng sau những triệu chứng này có thể là **clock skew**: độ lệch giữa đồng hồ của những máy độc lập dùng để xác định thời điểm hiện tại. Với OAuth2 và OIDC, tính đúng của thời gian ảnh hưởng đến authentication, token validation, token renewal, jobs, sessions và cả TLS.

> **Thông điệp chính:** Phải đồng bộ thời gian cho mọi máy trước, rồi dùng clock skew tolerance nhỏ có chủ đích. Tăng tolerance không sửa được một node lệch nhiều phút, không thay thế kiểm tra chữ ký/issuer/audience, và không được dùng để che giấu lỗi vận hành.

## 2. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt UTC, timezone, wall clock, monotonic clock, drift, offset và clock skew.
2. Hiểu ngữ nghĩa JWT claims <code>exp</code>, <code>nbf</code>, <code>iat</code>, OIDC <code>auth_time</code> và thời gian code/token.
3. Phân biệt **leeway khi xác minh JWT** với **buffer làm mới token sớm**.
4. Cấu hình clock skew cho các Spring Security authorized-client providers đúng mục đích.
5. Hiểu vai trò <code>JwtTimestampValidator</code>, <code>Clock</code> và OIDC ID Token validation.
6. Đồng bộ đồng hồ bằng NTP/chrony/systemd-timesyncd/Windows Time hoặc time service của cloud.
7. Phân tích clock của Kubernetes nodes, containers, VMs, NTP outages và timezone.
8. Thiết kế unit/integration tests với <code>Clock.fixed</code>, <code>Clock.offset</code> và boundary timestamps.
9. Phân biệt expired token do time skew với token revocation, refresh rotation, issuer mismatch và session errors.
10. Xây dựng metrics, alerts, troubleshooting workflow và runbook cho production.

## 3. Các khái niệm thời gian: không được đánh đồng

| Khái niệm | Ví dụ | Tác động |
|---|---|---|
| UTC instant | <code>2026-11-16T10:00:00Z</code> | Mốc thời gian tuyệt đối cho token expiry |
| Timezone | <code>Asia/Ho_Chi_Minh</code> | Định dạng giờ địa phương; không tự làm lệch instant |
| Wall clock | <code>Instant.now()</code> | Giờ hệ thống, có thể được NTP chỉnh |
| Monotonic elapsed time | <code>System.nanoTime()</code> | Đo latency/timeout, không dùng làm epoch |
| Clock offset/skew | Host nhanh hơn UTC chuẩn 45 giây | Có thể làm JWT sai hiệu lực |
| Clock drift | Mỗi ngày host nhanh thêm 0,2 giây | Sai số tích lũy nếu không đồng bộ |
| Clock step | Nhảy từ 10:00 lên 10:02 | Những deadline có thể tới “đột ngột” |
| Clock slew | Đồng hồ được điều chỉnh tốc độ dần | Giảm các bước nhảy lớn |
| JWT validation leeway | Chấp nhận sai lệch 60 giây | Mở rộng cửa sổ chấp nhận JWT |
| Token refresh buffer | Refresh trước expiry 90 giây | Giảm gửi token sắp hết hạn |

### 3.1. UTC không phải timezone

~~~text
UTC:              2026-11-16 10:00:00Z
Asia/Ho_Chi_Minh: 2026-11-16 17:00:00+07:00
~~~

Đây là **một instant**, dù dạng hiển thị chênh lệch bảy giờ.

~~~java
import java.time.Instant;
import java.time.ZoneId;
import java.time.ZonedDateTime;

Instant issuedAt = Instant.parse("2026-11-16T10:00:00Z");
ZonedDateTime display = issuedAt.atZone(
    ZoneId.of("Asia/Ho_Chi_Minh"));
~~~

Nếu một node in UTC và node khác in ICT, không được kết luận node lệch clock trước khi so sánh các UTC instants của chúng.

### 3.2. Wall clock và monotonic clock

JWT có absolute expiration time:

~~~java
Instant now = Instant.now();
boolean expired = !now.isBefore(expiresAt);
~~~

Phép so sánh cần wall clock và một giá trị <code>Instant</code>.

Để đo Token Endpoint latency:

~~~java
long started = System.nanoTime();
// HTTP request to Token Endpoint
long latencyNanos = System.nanoTime() - started;
~~~

<code>System.nanoTime()</code> không có epoch UTC chung giữa processes; không dùng nó tạo <code>exp</code> hoặc so sánh timestamps giữa JVMs.

### 3.3. Clock skew giữa hai hệ thống

Giả sử:

~~~text
Real UTC:                 10:00:00
Authorization Server:    10:00:00
OAuth2 Client A:          10:00:45 (+45 s)
Resource Server B:       09:59:20 (-40 s)
~~~

Hai nodes A và B khác nhau **85 giây**, dù mỗi node chỉ lệch UTC vài chục giây. Đây là nguyên nhân khiến token có thể bị coi “expired” ở một nơi, “not yet valid” ở nơi khác.

## 4. Các mốc thời gian trong OAuth2/OIDC

### 4.1. JWT NumericDate

JWT biểu diễn nhiều claims bằng <code>NumericDate</code>: số giây kể từ Unix epoch theo UTC, không phải chuỗi giờ địa phương.

~~~json
{
  "iss": "https://sso.example.org/realms/company",
  "sub": "user-123",
  "aud": "portal-web",
  "iat": 1794823200,
  "nbf": 1794823200,
  "exp": 1794826800
}
~~~

Các epoch values chỉ dùng để minh họa định dạng. Khi tự tạo test token, nên sinh từ <code>Instant.getEpochSecond()</code> để không gõ nhầm.

### 4.2. exp — expiration

<code>exp</code> là thời điểm JWT không còn được chấp nhận theo timestamp validation, ngoại trừ một leeway nhỏ được cấu hình.

Mô hình căn bản:

~~~text
now < exp       → chưa quá hạn
now >= exp      → hết hạn, nếu không có leeway
~~~

JWT còn phải vượt qua signature, issuer, audience, token purpose và các validations khác.

### 4.3. nbf — not before

<code>nbf</code> chỉ thời điểm sớm nhất token được chấp nhận:

~~~text
now < nbf       → token chưa có hiệu lực
now >= nbf      → qua điều kiện not-before
~~~

Leeway có thể cho phép một sai lệch nhỏ trước thời điểm <code>nbf</code>.

### 4.4. iat — issued at

<code>iat</code> là thời điểm token được phát hành. Nó hữu ích cho token age, auditing và một số chính sách xác thực.

**Không giả định** mọi JWT validator mặc định kiểm tra <code>iat</code> với cùng semantics như <code>nbf</code>. Một số validation layers/profiles có quy tắc riêng về thời gian phát hành.

### 4.5. OIDC auth_time

<code>auth_time</code> thể hiện thời điểm OP xác thực user, khác với <code>iat</code> của ID Token:

~~~text
auth_time = lúc user xác thực tại OP
iat       = lúc ID Token được phát hành
~~~

Trong những flow sử dụng <code>max_age</code> hoặc step-up, <code>auth_time</code> có thể tham gia quyết định authentication còn đủ mới không. Clock skew có thể gây nhận định sai về độ mới nếu các node lệch lớn.

### 4.6. Authorization code, access token và refresh token

Không phải mọi token trong OAuth2 đều là JWT:

- Authorization code thường là credential ngắn hạn, chỉ được dùng một lần.
- Access token có thể là JWT hoặc opaque token.
- Refresh token có lifecycle, expiry, rotation/revocation riêng và có thể opaque.
- OIDC ID Token là JWT phục vụ authentication của Client.

Client không được parse mọi access/refresh token như JWT. Spring Security <code>OAuth2AccessToken</code> có <code>issuedAt</code>/<code>expiresAt</code> đã được framework xử lý từ response metadata.

### 4.7. expires_in tính bằng seconds

Token Endpoint có thể trả:

~~~json
{
  "access_token": "opaque-test-value",
  "token_type": "Bearer",
  "expires_in": 3600
}
~~~

<code>expires_in</code> theo OAuth2 protocol thường là **số giây** đến khi access token hết hạn. Không nhầm thành milliseconds, cũng không cộng bằng chuỗi giờ local.

## 5. Timeline: “expired” và “not yet valid” có thể cùng xuất hiện

OP phát token:

~~~text
OP clock: 10:00:00 UTC
nbf:      10:00:00 UTC
exp:      10:05:00 UTC
~~~

Resource Server chậm 50 giây:

~~~text
RS wall clock: 09:59:10
JWT nbf:       10:00:00
~~~

RS có thể báo not-yet-valid nếu allowance quá nhỏ.

Client nhanh 90 giây:

~~~text
Client clock: 10:05:20
JWT exp:      10:05:00
~~~

Client có thể coi token đã hết hạn sớm hơn OP/RS.

~~~mermaid
flowchart TD
    OP["OP phát hành JWT với nbf=10:00, exp=10:05"] --> C["OAuth2 Client clock nhanh +90s"]
    OP --> RS["Resource Server clock chậm -50s"]
    C --> R["Client cho rằng cần refresh sớm"]
    RS --> N["RS có thể cho rằng JWT chưa đến nbf"]
    R --> X["Cần đồng bộ đồng hồ và kiểm soát tolerance"]
    N --> X
~~~

Clock skew tolerance chỉ giải quyết **sai số có giới hạn**. Nếu node lệch nhiều phút, sửa đồng hồ là trách nhiệm hạ tầng.

## 6. Hai cơ chế gọi là clock skew nhưng có ý nghĩa ngược nhau

| Cơ chế | Câu hỏi | Công thức minh họa | Tác động |
|---|---|---|---|
| **JWT validation leeway** | JWT còn được chấp nhận không? | <code>now &lt; exp + tolerance</code>, <code>now + tolerance &gt;= nbf</code> | Có thể chấp nhận token hơi quá hạn hoặc hơi sớm |
| **Early refresh buffer** | Client có nên lấy token mới chưa? | <code>now &gt;= expiresAt - buffer</code> | Refresh **trước** hạn |

### 6.1. Validation leeway

~~~text
JWT exp:            10:30:00
Resource Server now:10:30:35
Allowed skew:       60 seconds
~~~

Một validator cho phép 60 giây có thể vẫn chấp nhận điều kiện timestamp. Điều đó làm **rộng cửa sổ token có thể dùng**, nên phải cân đối security policy. Nó không cứu JWT có signature/issuer/audience sai.

### 6.2. Early refresh

~~~text
Access token expiresAt: 10:30:00
Refresh buffer:         90 seconds
Refresh threshold:      10:28:30
~~~

Khi Client đạt 10:28:30, nó có thể chủ động refresh để tránh token hết hạn giữa chuyến gọi API. Buffer không làm Resource Server nhận expired JWT lâu hơn.

### 6.3. Không chọn một Duration cho cả hai theo quán tính

<code>clockSkew(Duration.ofSeconds(90))</code> trong authorized-client provider và <code>JwtTimestampValidator(Duration.ofSeconds(90))</code> có **hai hậu quả khác nhau**.

- Ở OAuth2 Client, refresh sớm có thể giảm lỗi downstream.
- Ở JWT validator, leeway lớn hơn có thể tăng thời gian một access token cũ còn được chấp nhận.

### 6.4. Cẩn thận đơn vị

~~~java
Duration.ofSeconds(60);  // 60 s
Duration.ofMinutes(2);   // 120 s
Duration.ofMillis(60);   // 0.06 s, không phải 60 s
~~~

Một lỗi nhầm ms/s có thể khiến token refresh muộn hoặc tolerance quá rộng.

## 7. Đồng bộ thời gian trước khi sửa Java code

Một triển khai cần:

1. Các hosts/nodes lấy thời gian từ trusted NTP/cloud time sources.
2. Xác minh **system clock synchronized**, không chỉ chọn timezone UTC.
3. Theo dõi clock offset, frequency/drift, reachability và last synchronization.
4. Kiểm tra Authorization Server, OAuth2 Client, Resource Server, ingress, database và Kubernetes nodes theo kiến trúc.
5. Dùng UTC timestamps trong telemetry để correlating events.
6. Cảnh báo khi mất sync hoặc offset vượt error budget.
7. Chọn leeway nhỏ sau khi đã có dữ liệu về expected jitter/latency.

### 7.1. Không đòi lệch tuyệt đối bằng không

Ngay cả NTP hoạt động tốt vẫn có sai số nhỏ. Mục tiêu là **offset thấp, ổn định, đo được** trong giới hạn bảo mật, không phải tất cả clocks đồng nhất nanosecond.

### 7.2. TLS cũng phụ thuộc thời gian

Chứng chỉ X.509 có <code>NotBefore</code> và <code>NotAfter</code>. Host lệch nhiều phút có thể từ chối chứng chỉ đúng vì “not yet valid” hoặc “expired”.

Nới JWT leeway **không thay đổi** TLS certificate validation. Sửa đồng hồ, truststore hoặc certificate deployment; không bật trust-all TLS để làm request chạy.

## 8. Linux: chrony, NTP và timesyncd

Trên Linux, dịch vụ đồng bộ có thể là <code>chronyd</code>, <code>systemd-timesyncd</code> hoặc một NTP client khác. Chọn dịch vụ phù hợp hệ điều hành/cloud image, tránh chạy nhiều services cạnh tranh điều chỉnh cùng clock.

### 8.1. Kiểm tra thời gian và trạng thái đồng bộ

~~~bash
date -u
timedatectl status
~~~

Quan sát UTC, timezone, system clock synchronized và NTP service. Một lệnh <code>date -u</code> in giờ có vẻ đúng **không chứng minh** node đã đồng bộ với nguồn thời gian.

### 8.2. Chrony

~~~bash
chronyc tracking
chronyc sources -v
~~~

<code>tracking</code> cung cấp dữ liệu liên quan tới offset, drift/frequency và trạng thái đồng bộ. <code>sources -v</code> giúp xem time sources reachable hay không.

Nếu các sources đều unreachable, điều tra DNS, firewall, policy mạng, NTP sources và cloud time service.

### 8.3. systemd-timesyncd

~~~bash
timedatectl timesync-status
timedatectl show-timesync --all
~~~

Các lệnh con tùy version systemd. Nếu host dùng chrony, xem chrony thay vì suy diễn timesyncd phải luôn active.

### 8.4. Tránh chỉnh giờ thủ công trong production

Một clock step lớn có thể gây biến động:

~~~text
Token expiry decisions
Cache TTLs
Scheduled jobs
Log ordering
Session expiry
Distributed leases
TLS certificate validation
~~~

Không chỉnh <code>date -s</code> trên host production tùy tiện; tuân thủ runbook/cơ chế time synchronization của đội vận hành.

## 9. Windows Server và virtual machines

Với Windows Time Service:

~~~powershell
w32tm /query /status
w32tm /query /source
w32tm /query /peers
~~~

Windows PowerShell 5.1 có thể dùng:

~~~powershell
[DateTime]::UtcNow.ToString("o")
~~~

để in một UTC timestamp. Không áp dụng <code>Get-Date -AsUTC</code> nếu runtime PowerShell không hỗ trợ parameter đó.

Nếu máy thuộc Active Directory domain, clock hierarchy có thể được domain policy quản lý. Không tự đổi nguồn NTP của domain controller/server tổ chức khi chưa được phép.

### 9.1. VM resume và snapshots

Sau suspend/resume hoặc VM snapshot restore, guest clock có thể bị lệch tạm thời. Cần xác minh time synchronization **sau** resume, nhất là khi node mới trở lại load balancer.

### 9.2. Timezone Windows không làm đổi JWT NumericDate

Windows host hiển thị local time khác Linux UTC không đồng nghĩa sai token validation. Mọi xử lý <code>exp</code>/<code>nbf</code> nên dùng UTC instants.

## 10. Kubernetes và Docker: container thường chia sẻ clock của node

Trong triển khai Linux containers thông thường, JVM trong container sử dụng system clock của **host kernel**. Thay timezone trong container không đồng nghĩa thay instant. Một Pod cũng không nên tự có đặc quyền thay đồng hồ Kubernetes node.

~~~text
Kubernetes Node A clock
  ├── Portal pod A1
  ├── Portal pod A2
  └── API pod A3

Kubernetes Node B clock
  ├── Portal pod B1
  └── API pod B2
~~~

Các Pods trên cùng node thường dùng cùng system clock nền. Pods ở **hai nodes khác nhau** có thể lệch nhau nếu node time sync bị lỗi.

### 10.1. Scale-out làm lỗi xuất hiện ngẫu nhiên

~~~text
Node A: UTC + 3 seconds
Node B: UTC + 95 seconds
Node C: UTC - 70 seconds
~~~

Request đi vào A có thể thành công, vào B lại bị đánh giá expired, vào C báo not-yet-valid. Cần correlate lỗi theo **node/instance**, không chỉ URL.

### 10.2. Cần kiểm tra ở node level

- Time synchronization service trên node image.
- Cloud/NTP source reachability.
- Clock offset theo node và node age.
- Nodes sau autoscaling, rolling replacement, VM resume.
- Drift trend, missed sync và alert rules.
- Mạng và quyền truy cập time service của cloud provider.

Restart Pod thường **không sửa** đồng hồ node sai. Không chạy privileged NTP pod có khả năng thay host clock nếu không có quy trình platform/security kiểm soát.

### 10.3. TZ khác nhau không đồng nghĩa clock khác nhau

~~~text
Pod A TZ=UTC
Pod B TZ=Asia/Ho_Chi_Minh
~~~

vẫn có thể trả cùng <code>Instant.now()</code>. Tách giờ hiển thị khỏi thời gian tuyệt đối.

## 11. Java Instant và Clock

### 11.1. So sánh expiry bằng Instant

~~~java
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;

Clock clock = Clock.systemUTC();
Instant now = Instant.now(clock);
Instant expiresAt = Instant.parse("2026-11-16T10:30:00Z");

boolean expired = !now.isBefore(expiresAt);
boolean closeToExpiry = !now.isBefore(
    expiresAt.minus(Duration.ofSeconds(90)));
~~~

Đoạn này minh họa arithmetic. Trong Spring Security, ưu tiên để authorized-client provider và JWT validators thực hiện lifecycle phù hợp; không tự viết token manager thay framework chỉ bằng boolean trên.

### 11.2. Tránh LocalDateTime cho một expiry tuyệt đối

Không lưu token expiry bằng một chuỗi không có timezone:

~~~text
2026-11-16 10:30:00
~~~

rồi đọc với timezone khác nhau. Dùng <code>Instant</code>, <code>OffsetDateTime</code> hoặc database timestamp strategy giữ instant nhất quán.

~~~java
Instant expiresAt =
    Instant.now(clock).plus(Duration.ofMinutes(5));
~~~

Khi hiển thị, chuyển sang timezone của user tại presentation layer.

### 11.3. Epoch milliseconds và seconds

~~~java
long seconds = Instant.now().getEpochSecond();
long millis = System.currentTimeMillis();
~~~

JWT NumericDate thường dùng **seconds**. Nếu ghi milliseconds vào <code>exp</code>, token có thể giống như còn hiệu lực hàng ngàn năm. Nếu đọc seconds như milliseconds, token có thể bị coi hết hạn từ rất lâu.

### 11.4. Inject Clock để test xác định

~~~java
public final class ExpiryPolicy {
    private final Clock clock;
    private final Duration buffer;

    public ExpiryPolicy(Clock clock, Duration buffer) {
        this.clock = clock;
        this.buffer = buffer;
    }

    public boolean shouldRefresh(Instant expiresAt) {
        return !Instant.now(clock).isBefore(
            expiresAt.minus(buffer));
    }
}
~~~

Đây là policy minh họa, không phải class built-in của Spring Security. Tránh vừa inject <code>Clock</code> vừa dùng <code>Instant.now()</code> không có parameter trong cùng service, vì test không thể điều khiển đầy đủ logic.

## 12. Access token expiresAt và refresh sớm

<code>OAuth2AuthorizedClient</code> gắn một ClientRegistration/principal với access token và refresh token nếu có.

~~~java
import org.springframework.security.oauth2.core.OAuth2AccessToken;
import java.time.Instant;

OAuth2AccessToken token = authorizedClient.getAccessToken();
Instant issuedAt = token.getIssuedAt();
Instant expiresAt = token.getExpiresAt();
~~~

### 12.1. Token hết hạn giữa chuyến gọi API

~~~text
Client chọn token:       10:29:58
Token expiresAt:         10:30:00
Network/queue latency:   3 seconds
API nhận request:        10:30:01
~~~

Resource Server có thể từ chối, dù hai đồng hồ đồng bộ. Đây là lý do hữu ích cho **early refresh buffer**.

### 12.2. Buffer 90 giây

~~~text
Token expiresAt: 10:30:00
Buffer:          90 seconds
Refresh at:      10:28:30 or later
~~~

Buffer giảm nguy cơ token hết hạn trước khi API xử lý. Nó không trực tiếp thay đổi Resource Server JWT validation.

### 12.3. Không dùng buffer dài hơn token lifetime tùy tiện

Nếu token sống 60 giây mà refresh buffer là 90 giây, provider có thể coi token gần hết hạn ngay sau khi nhận, dẫn đến refresh liên tục hoặc token churn.

Chọn buffer theo:

- Token lifetime do OP phát.
- Token Endpoint p95/p99 latency và retry budget.
- Queue/processing latency trước API call.
- Clock offset đã đo được.
- Refresh-token rotation/concurrency policy.
- Token rate limits và expected traffic.

## 13. Spring Security OAuth2AuthorizedClientProvider clockSkew

Các authorized-client providers như refresh token và client credentials cho phép cấu hình clock skew để **lấy access token mới sớm**.

### 13.1. Service manager cho background jobs

~~~java
package example.security;

import java.time.Duration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.client
    .AuthorizedClientServiceOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientProvider;
import org.springframework.security.oauth2.client
    .OAuth2AuthorizedClientProviderBuilder;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientService;
import org.springframework.security.oauth2.client.registration
    .ClientRegistrationRepository;

@Configuration
public class JobOAuth2ClientConfig {

    @Bean
    OAuth2AuthorizedClientManager jobAuthorizedClientManager(
            ClientRegistrationRepository registrations,
            OAuth2AuthorizedClientService clientService) {

        Duration buffer = Duration.ofSeconds(90);

        OAuth2AuthorizedClientProvider provider =
            OAuth2AuthorizedClientProviderBuilder.builder()
                .refreshToken(refresh ->
                    refresh.clockSkew(buffer))
                .clientCredentials(client ->
                    client.clockSkew(buffer))
                .build();

        var manager =
            new AuthorizedClientServiceOAuth2AuthorizedClientManager(
                registrations, clientService);

        manager.setAuthorizedClientProvider(provider);
        return manager;
    }
}
~~~

Đây là manager phù hợp cho service/job flows không cần <code>HttpServletRequest</code>. Nó không tự mở browser, tạo authorization code consent hoặc thay <code>oauth2Login()</code>.

### 13.2. Web Servlet manager

Khi sử dụng <code>DefaultOAuth2AuthorizedClientManager</code>:

~~~java
import java.time.Duration;
import org.springframework.security.oauth2.client
    .DefaultOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client
    .OAuth2AuthorizedClientProviderBuilder;

var manager = new DefaultOAuth2AuthorizedClientManager(
    clientRegistrations,
    authorizedClientRepository);

manager.setAuthorizedClientProvider(
    OAuth2AuthorizedClientProviderBuilder.builder()
        .authorizationCode()
        .refreshToken(refresh ->
            refresh.clockSkew(Duration.ofSeconds(90)))
        .build());
~~~

Snippet giả định <code>clientRegistrations</code> và <code>authorizedClientRepository</code> đã được inject. Web manager có thể cần servlet request/response context; không mang nó vào background scheduler tùy tiện.

### 13.3. Không nhầm với JWT validation

<code>clockSkew</code> của authorized-client provider:

- Ảnh hưởng thời điểm authorize/refresh token.
- Không sửa <code>exp</code> bên trong ID Token.
- Không thay đổi clock của host/Pod.
- Không làm Resource Server chấp nhận expired JWT lâu hơn.
- Không sửa sai issuer, nonce hoặc chữ ký.

Nếu JWT bị từ chối bởi Resource Server do <code>nbf</code>, tăng refresh buffer chưa chắc giải quyết vấn đề.

## 14. Lưu expiresAt trong cluster và database

Một token state storage nên giữ absolute expiry instant, tránh timezone-dependent string conversions.

Ví dụ PostgreSQL schema khái niệm:

~~~sql
CREATE TABLE oauth2_authorized_client_state (
    registration_id VARCHAR(120) NOT NULL,
    principal_key VARCHAR(240) NOT NULL,
    access_token_ciphertext BYTEA NOT NULL,
    refresh_token_ciphertext BYTEA,
    access_expires_at TIMESTAMPTZ NOT NULL,
    version BIGINT NOT NULL DEFAULT 0,
    PRIMARY KEY (registration_id, principal_key)
);
~~~

Đây **không phải** schema thay thế đầy đủ cho Spring Security JDBC authorized-client implementation; nó chỉ minh họa việc lưu token state mã hóa, expiry và version.

### 14.1. TIMESTAMPTZ không có nghĩa hiển thị luôn UTC

PostgreSQL <code>TIMESTAMPTZ</code> lưu instant, nhưng format hiển thị có thể theo session timezone. Không so sánh string output của hai sessions khác timezone để chẩn đoán drift.

### 14.2. Metadata token và timezone

Nếu hai JVM lưu/đọc <code>Instant</code> qua JDBC, hãy integration-test với những timezone settings khác nhau. Dữ liệu thời gian không được “đổi giờ” khi chuyển giữa các nodes.

### 14.3. Refresh token không được suy từ expiresAt của access token

Refresh token có expiry/revocation/rotation policy riêng, không nhất thiết có claim <code>exp</code>. Một <code>invalid_grant</code> có thể do token bị revoke, reuse hoặc client binding sai, không chỉ vì đồng hồ.

## 15. JwtTimestampValidator: leeway khi xác minh JWT

Trong Spring Security OAuth2 Resource Server, class:

~~~java
org.springframework.security.oauth2.jwt.JwtTimestampValidator
~~~

kiểm tra temporal claims như <code>exp</code> và <code>nbf</code> với một khoảng clock skew tolerance.

### 15.1. Leeway khác buffer

Giả sử Resource Server có:

~~~text
JWT exp:                  10:30:00
Resource Server clock:    10:30:35
Configured leeway:        60 giây
~~~

Điều kiện timestamp có thể vẫn được chấp nhận vì thời gian mới vượt <code>exp</code> 35 giây. **Đây là mở rộng cửa sổ chấp nhận token**, không phải yêu cầu Client refresh trước hạn.

### 15.2. Cấu hình timestamp validator

~~~java
import java.time.Duration;
import org.springframework.security.oauth2.jwt.JwtTimestampValidator;

JwtTimestampValidator validator =
    new JwtTimestampValidator(Duration.ofSeconds(60));
~~~

Điều này chỉ kiểm tra **timestamp**. Nó không chứng minh chữ ký hợp lệ, issuer đúng, audience đúng hay user có scope cần thiết.

### 15.3. Fixed Clock cho validator

~~~java
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.ZoneOffset;
import org.springframework.security.oauth2.jwt.JwtTimestampValidator;

Clock testClock = Clock.fixed(
    Instant.parse("2026-11-16T10:00:00Z"),
    ZoneOffset.UTC);

JwtTimestampValidator validator =
    new JwtTimestampValidator(Duration.ofSeconds(60));

validator.setClock(testClock);
~~~

Test này xác định “now” mà validator sử dụng, không thay đồng hồ hệ điều hành. API customization cần đối chiếu đúng version Spring Security.

### 15.4. Tránh ghi đè validator chain thành timestamp-only

Ví dụ nguy hiểm:

~~~java
// Sai nếu đây trở thành toàn bộ JWT validation của Resource Server.
decoder.setJwtValidator(
    new JwtTimestampValidator(Duration.ofMinutes(10)));
~~~

Một resource server cần giữ checks về signature, issuer, audience, token purpose và policies khác. Nếu ghi đè validator chain để chỉ còn timestamp validator, hệ thống có thể đánh mất validation thiết yếu.

Khi cần chỉnh tolerance, hãy dùng documented customization point của phiên bản Spring Security đang chạy và **compose đầy đủ** các validators cần thiết. Không làm “JWT hợp lệ” đồng nghĩa “timestamp pass”.

### 15.5. Default issuer validation

Spring Security hỗ trợ:

~~~java
import org.springframework.security.oauth2.jwt.JwtValidators;

var validators = JwtValidators.createDefaultWithIssuer(
    "https://sso.example.org/realms/company");
~~~

Validator chain này giúp minh họa việc giữ default validations và issuer. Với Resource Server thực, có thể còn cần audience/scope/tenant-specific validation. Không thay mặc định bằng một timestamp-only validator.

## 16. OIDC ID Token: thời gian là một phần của authentication

Trong OAuth2 Login với OpenID Connect, ID Token dùng cho **authentication của user với Relying Party**. Một pipeline đúng cần:

- Xác minh chữ ký theo OP JWKS/algorithm policy.
- Xác minh <code>iss</code> đúng issuer đã cấu hình.
- Xác minh <code>aud</code> chứa Client ID.
- Kiểm tra <code>exp</code>, <code>iat</code> và những temporal requirements khác theo OIDC profile.
- Kiểm tra <code>nonce</code> nếu authorization request dùng nonce.
- Xử lý <code>azp</code> và <code>auth_time</code> khi flow/policy yêu cầu.

### 16.1. Khi RP clock quá nhanh

~~~mermaid
sequenceDiagram
    autonumber
    participant B as Browser
    participant RP as OIDC Client
    participant OP as OpenID Provider
    B->>RP: Callback code + state
    RP->>OP: Token request
    OP-->>RP: ID Token, iat=10:00, exp=10:05
    RP->>RP: Local clock reads 10:07
    RP->>RP: Temporal validation fails
    RP-->>B: Login authentication failure
~~~

Nếu RP nhanh hơn OP nhiều phút, việc login thất bại có thể phản ánh time sync issue. Không tắt expiry validation hoặc tự tin claims từ JWT chưa được xác minh.

### 16.2. Resource Server validator không tự áp dụng cho oauth2Login

<code>JwtTimestampValidator</code> thường được nhắc trong OAuth2 Resource Server. OIDC Login có decoder/validators được xây theo <code>ClientRegistration</code> và OIDC rules.

Nếu cần tùy chỉnh leeway của ID Token bằng <code>OidcIdTokenDecoderFactory</code> hoặc extension point theo version:

1. Kiểm tra public API và documented behavior của Spring Security version trong project.
2. Giữ toàn bộ issuer/audience/signature/nonce/azp validation.
3. Không thay validator mặc định bằng một validator timestamp đơn độc.
4. Giới hạn tolerance nhỏ, có security review và metrics.
5. Test boundary cases và token sai signature/issuer vẫn bị từ chối.

### 16.3. auth_time và max_age

Nếu Portal yêu cầu authentication không quá 5 phút:

~~~text
max_age = 300 seconds
auth_time = 10:00:00
Client now = 10:05:20
~~~

Các semantics reauthentication/step-up phụ thuộc OP và Client policy. Một Client clock chậm có thể đánh giá nhầm authentication cũ còn đủ mới; nới tolerance quá rộng làm yếu yêu cầu step-up.

### 16.4. State/nonce không phải timestamp

<code>state</code> và <code>nonce</code> dùng correlation/replay protection. Lỗi:

~~~text
authorization_request_not_found
invalid_state
nonce mismatch
~~~

không mặc nhiên là clock skew; có thể do session cookie, request repository, wrong instance, multi-tab hoặc tampering. Không bỏ các checks đó để né một sự cố đồng hồ.

## 17. Resource Server HTTP 401: không phải lỗi nào cũng do thời gian

Resource Server có thể trả:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer error="invalid_token"
~~~

Nhưng <code>invalid_token</code> không tiết lộ tự động nguyên nhân chính xác.

| Nguyên nhân | Liên quan clock? | Điều tra |
|---|---|---|
| JWT exp quá hạn | Có | Token TTL, offset, refresh |
| JWT nbf ở tương lai | Có | OP/RS clocks |
| Issuer sai | Không trực tiếp | OIDC/OAuth2 issuer trust |
| Audience sai | Không | Token audience/resource indicator |
| Signature/JWK không khớp | Không | Key rotation/JWKS |
| Token revoked | Không nhất thiết | OP revocation/policy |
| Authorization header bị xóa | Không | Proxy/WebClient integration |
| Token sai type/purpose | Không | Validation policy |

Một token timestamp pass vẫn cần signature, issuer, audience, scopes và business authorization. HTTP 403 <code>insufficient_scope</code> là lỗi quyền, không nên sửa bằng clock skew hoặc refresh liên tục.

## 18. Client Credentials và token acquisition concurrency

Service dùng <code>client_credentials</code> nhận token TTL ngắn. Khi token vào early refresh window:

~~~text
10:28:30 — token sắp hết hạn
10:28:31 — 50 worker threads đồng thời yêu cầu token
10:28:32 — nhiều token acquisition requests có thể phát sinh
~~~

Clock skew buffer chỉ giúp quyết định **khi nào** lấy token; nó không đảm bảo chỉ một worker xin token.

### 18.1. Single-flight theo key

~~~text
key = registrationId + trustedServicePrincipal
~~~

Một cache/token manager dùng lock hoặc single-flight có thể giảm duplicate token requests. Không lấy authorized client của tenant hoặc principal khác để làm fallback khi Token Endpoint timeout.

### 18.2. Chọn buffer từ số đo thật

Ví dụ số đo:

~~~text
Observed max offset:       2 seconds
Token Endpoint p99 latency:1.5 seconds
API queueing:             4 seconds
Retry safety margin:      policy-specific
~~~

Các số trên **chỉ minh họa**. Buffer phải nhỏ hơn token lifetime theo use case và đủ để xử lý network/queue latency thực tế.

### 18.3. Token response đã già đi trong mạng

Nếu OP phát token lúc T0 nhưng response đến Client lúc T0+3 giây, thời gian hiệu lực còn lại đã ngắn hơn nominal TTL. Đo Token Endpoint latency và dựa vào expiry metadata framework; không giả định nhận token xong thì còn trọn vẹn <code>expires_in</code> bất chấp network delay.

## 19. Clock skew và refresh-token rotation

Trong token rotation:

~~~text
Initial: access A0, refresh R0
Refresh: access A1, refresh R1
Reuse R0: OP có thể trả invalid_grant hoặc kích hoạt reuse detection
~~~

Hai nodes đọc cùng token R0:

~~~mermaid
sequenceDiagram
    autonumber
    participant A as Node A - clock nhanh
    participant B as Node B - clock thường
    participant DB as Shared Token Store
    participant OP as Token Endpoint
    A->>DB: Read A0/R0, version 7
    B->>DB: Read A0/R0, version 7
    A->>OP: Refresh R0
    OP-->>A: A1/R1
    B->>OP: Refresh R0
    OP-->>B: invalid_grant
    A->>DB: Save A1/R1, version 8
    B->>DB: Unconditional remove?
    Note over DB: B có thể xóa version 8 của A
~~~

### 19.1. Đồng bộ clock không đủ chống race

Ngay cả hai clocks chính xác vẫn có thể cùng refresh R0. Cần concurrency coordination:

~~~text
1. Load authorized client đúng registration/principal.
2. Nếu access token đủ hạn → dùng.
3. Nếu cần refresh → acquire per-key distributed lock/single-flight.
4. Sau lock, re-read latest token state.
5. Nếu token đã được refresh → dùng bản mới.
6. Nếu chưa → refresh grant.
7. Atomic save access+refresh token mới với version/CAS.
8. Khi invalid_grant, conditional remove đúng version cũ.
9. Release lock với ownership/lease policy.
~~~

Đây là pseudocode kiến trúc, **không phải hành vi mặc định** của <code>DefaultOAuth2AuthorizedClientManager</code>.

### 19.2. Refresh timeout là unknown outcome

OP có thể đã nhận R0 và phát R1 nhưng response bị mất. Retry R0 có thể trả <code>invalid_grant</code> hoặc trigger token-family revocation. Tăng clock skew không giải quyết trạng thái distributed transaction không xác định.

## 20. Clock step, jobs và distributed leases

System clock có thể bị điều chỉnh trong quá trình vận hành.

### 20.1. Step forward

~~~text
Host clock jumps 10:00 → 10:03
~~~

Scheduled refresh jobs có thể thấy nhiều deadlines đã quá hạn cùng lúc, tạo thundering herd. Với clock step lớn, token validation và TLS validity cũng có thể thay đổi đột ngột.

### 20.2. Step backward

~~~text
Host clock jumps 10:00 → 09:58
~~~

Logic retry/deadline tự viết dựa trên wall clock có thể đợi lâu hơn dự kiến. Với elapsed timeouts, ưu tiên library/monotonic scheduling facilities phù hợp.

### 20.3. Distributed lock lease

Một lock store dùng server-side TTL khác một implementation tự so sánh <code>expires_at</code> với local Client clock. Cần hiểu clock nguồn nào quyết định lease timeout.

Ngay cả khi store có TTL ổn định, GC pause/network delays có thể làm lease hết trước khi refresh hoàn tất. Dùng re-read/version/CAS/fencing khi consistency requirements đòi hỏi.

## 21. Chọn tolerance là quyết định vận hành và bảo mật

Đánh giá:

1. Max observed offset giữa OP, Client và Resource Server.
2. NTP jitter và time source stability.
3. Token Endpoint latency p95/p99 và queueing.
4. Access token TTL, refresh rotation policy và rate limits.
5. Replay risk nếu stolen token còn được nhận trong leeway.
6. Step-up requirements và <code>auth_time</code>/<code>max_age</code>.
7. Security/compliance constraints.
8. Testing/rollout/alerting capability.

### 21.1. Ví dụ hai chính sách tách biệt

| Parameter | Giá trị minh họa | Ý nghĩa |
|---|---|---|
| Desired max host offset | Dưới 2 giây | Internal operations SLO |
| JWT timestamp leeway | 60 giây | Cho phép sai số nhỏ tại Resource Server |
| Early refresh buffer | 90 giây | Giảm nguy cơ expired token giữa API request |
| Access token TTL | 15 phút | OP policy |
| Token Endpoint timeout | Theo latency SLO | Không treo vô hạn |

Giá trị trên **không phải chuẩn mặc định cho mọi hệ thống**. Chọn theo thông số đã đo và Spring Security/OP version cụ thể.

### 21.2. Leeway quá lớn

Nếu Resource Server chấp nhận <code>exp</code> quá 10 phút, một access token bị lộ có thể tiếp tục hữu dụng trong phần kéo dài đó. Với <code>nbf</code>, token có thể được chấp nhận sớm hơn nominal start time.

Đừng tăng skew lên hàng chục phút để che một NTP outage. Ưu tiên sửa time synchronization.

### 21.3. Buffer quá lớn

~~~text
Access token TTL=60s
Refresh buffer=90s
~~~

Client có thể coi token “sắp hết hạn” ngay sau khi cấp, gây refresh loops hoặc token churn. Buffer phải có quan hệ hợp lý với TTL.

### 21.4. Duration.ZERO

<code>Duration.ZERO</code> có thể loại bỏ extra leeway hoặc early refresh buffer, tùy component. Không phải lúc nào “zero tolerance” cũng ổn định trong hệ phân tán vì latency/clock jitter luôn tồn tại.

## 22. Observability: nhìn thấy clock offset thay vì chỉ error

### 22.1. Structured logs ở UTC

~~~text
timestamp=2026-11-16T10:00:15.123Z
service=portal
instance=portal-7f5dc8
node=node-b
registrationId=company
operation=oidc_login
stage=id_token_validation
errorCategory=timestamp_invalid
clockSyncHealthy=false
correlationId=example-123
~~~

Không log raw authorization code, state, nonce, access/refresh/ID Tokens, client secrets hoặc session cookie.

### 22.2. Node time metrics

Tùy exporter/platform, có thể theo dõi:

~~~text
node_timex_offset_seconds
node_timex_sync_status
node_timex_maxerror_seconds
node_timex_estimated_error_seconds
~~~

Tên metrics và semantics phụ thuộc exporter version; xác minh trên nền tảng thật trước khi viết alert.

### 22.3. OAuth2 application metrics

~~~text
oauth2_login_failure_total{provider,category}
oauth2_token_refresh_total{provider,result}
oauth2_token_request_latency_seconds{provider,grant_type}
oauth2_id_token_timestamp_failure_total{provider}
oauth2_resource_server_invalid_token_total{issuer_alias,category}
~~~

Các tên trên là **metric gợi ý do ứng dụng instrument**, không phải mọi metric đã có sẵn trong Spring Security.

### 22.4. Alert thresholds

Ví dụ internal alert rule cho một môi trường mong offset nhỏ:

~~~text
WARN: abs(clock_offset) > 1s liên tục 5 phút
CRITICAL: mất synchronization hoặc abs(clock_offset) > 5s
~~~

Không xem đây là ngưỡng phổ quát; phải hiệu chỉnh theo hạ tầng, expected jitter và security policy. Nên alert trước khi offset gần tới tolerance của JWT validators.

### 22.5. Tracing

~~~text
traceId=request-123
  ├── oidc.callback
  ├── oidc.token.exchange
  ├── authorized_client.lookup
  └── resource_server.api_call
~~~

Latency nên đo bằng monotonic elapsed time; event timestamps dùng UTC wall clock. Không kết luận thứ tự nhân quả dựa duy nhất vào logs từ nodes đang lệch giờ.

### 22.6. Metric labels an toàn

Sử dụng provider alias, operation, normalized error category và service. Không đưa user email, <code>sub</code>, JWT, <code>jti</code>, request ID hoặc raw error description vào metric labels có cardinality cao.

## 23. Unit tests với Clock.fixed và Clock.offset

Đừng đổi giờ OS của CI runner để test token expiry. Dùng injected <code>Clock</code> cho deterministic tests.

### 23.1. Test early refresh threshold

~~~java
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.ZoneOffset;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

class ExpiryPolicyTest {

    @Test
    void refreshesAtThreshold() {
        Clock clock = Clock.fixed(
            Instant.parse("2026-11-16T10:28:30Z"),
            ZoneOffset.UTC);
        ExpiryPolicy policy = new ExpiryPolicy(
            clock, Duration.ofSeconds(90));

        assertTrue(policy.shouldRefresh(
            Instant.parse("2026-11-16T10:30:00Z")));
    }

    @Test
    void waitsBeforeThreshold() {
        Clock clock = Clock.fixed(
            Instant.parse("2026-11-16T10:28:29Z"),
            ZoneOffset.UTC);
        ExpiryPolicy policy = new ExpiryPolicy(
            clock, Duration.ofSeconds(90));

        assertFalse(policy.shouldRefresh(
            Instant.parse("2026-11-16T10:30:00Z")));
    }
}
~~~

Đây là test cho policy ví dụ ở mục 11, **không phải test implementation nội bộ của Spring Security provider**.

### 23.2. Bảng boundary

| now | expiresAt | buffer | shouldRefresh |
|---|---|---|---|
| 10:28:29 | 10:30:00 | 90s | false |
| 10:28:30 | 10:30:00 | 90s | true |
| 10:29:00 | 10:30:00 | 90s | true |
| 10:30:00 | 10:30:00 | 90s | true |

### 23.3. Mô phỏng nhanh/chậm bằng Clock.offset

~~~java
Clock base = Clock.fixed(
    Instant.parse("2026-11-16T10:00:00Z"),
    ZoneOffset.UTC);

Clock fast = Clock.offset(
    base, Duration.ofSeconds(30));
Clock slow = Clock.offset(
    base, Duration.ofSeconds(-30));
~~~

Không làm ảnh hưởng đồng hồ của process/test khác. Tránh <code>Thread.sleep</code> khi bạn chỉ cần kiểm tra boundary.

## 24. Unit test JwtTimestampValidator

~~~java
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.ZoneOffset;
import org.junit.jupiter.api.Test;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtTimestampValidator;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

class JwtTimeValidationTest {

    private final Instant now =
        Instant.parse("2026-11-16T10:00:00Z");

    @Test
    void tokenExpiredThirtySecondsAgoWithinSkew() {
        Jwt jwt = jwtWithExpiry(now.minusSeconds(30));

        var validator = new JwtTimestampValidator(
            Duration.ofSeconds(60));
        validator.setClock(Clock.fixed(now, ZoneOffset.UTC));

        assertFalse(validator.validate(jwt).hasErrors());
    }

    @Test
    void tokenExpiredNinetySecondsAgoIsRejected() {
        Jwt jwt = jwtWithExpiry(now.minusSeconds(90));

        var validator = new JwtTimestampValidator(
            Duration.ofSeconds(60));
        validator.setClock(Clock.fixed(now, ZoneOffset.UTC));

        assertTrue(validator.validate(jwt).hasErrors());
    }

    private Jwt jwtWithExpiry(Instant expiry) {
        return Jwt.withTokenValue("test-header.payload.signature")
            .header("alg", "RS256")
            .subject("alice-test")
            .issuedAt(now.minusSeconds(300))
            .notBefore(now.minusSeconds(300))
            .expiresAt(expiry)
            .build();
    }
}
~~~

<code>test-header.payload.signature</code> chỉ là placeholder, **không phải JWT thật đã ký**. Test này chỉ kiểm tra timestamp validator, không có signature verification, issuer, audience hoặc OIDC protocol.

### 24.1. Token nbf tương lai

~~~java
@Test
void allowsNbfThirtySecondsInFutureWithSixtySecondSkew() {
    Instant now = Instant.parse("2026-11-16T10:00:00Z");

    Jwt jwt = Jwt.withTokenValue("test-token")
        .header("alg", "RS256")
        .subject("alice-test")
        .issuedAt(now)
        .notBefore(now.plusSeconds(30))
        .expiresAt(now.plusSeconds(600))
        .build();

    var validator = new JwtTimestampValidator(
        Duration.ofSeconds(60));
    validator.setClock(Clock.fixed(now, ZoneOffset.UTC));

    org.junit.jupiter.api.Assertions.assertFalse(
        validator.validate(jwt).hasErrors());
}
~~~

Tạo case khác với <code>nbf=now+90s</code> để xác minh bị từ chối khi tolerance chỉ 60 giây.

### 24.2. Không nhầm unit test với decoder integration

Trong test thực:

~~~text
Signed JWT from test OP
    ↓
JwtDecoder signature/JWKS
    ↓
Issuer + audience + timestamps + other validators
    ↓
Resource Server authorization
~~~

Unit test <code>JwtTimestampValidator</code> không thay thế bất kỳ bước nào khác trong pipeline đó.

## 25. Integration test OIDC Login với sai lệch thời gian

Một OIDC integration suite có OP test/stub ký ID Tokens hợp lệ:

~~~text
Test OP issuer: https://sso.test.example/realms/it
Client ID:      portal-it
Flow:           Authorization Code + PKCE khi áp dụng
Callback:       /login/oauth2/code/it-op
~~~

### 25.1. Các trường hợp cần phân biệt

| Tình huống | Fixture | Kỳ vọng |
|---|---|---|
| Login bình thường | ID Token exp đủ xa | Authentication thành công |
| ID Token exp quá hạn | exp cũ hơn tolerance | Authentication thất bại |
| ID Token gần expiry | exp nằm gần now | Behavior theo validator policy |
| ID Token issued in future | iat future theo test profile | OIDC temporal validation đúng |
| Wrong issuer | iss khác ClientRegistration | Failure dù timestamps đúng |
| Wrong audience | aud không chứa client ID | Failure |
| Nonce mismatch | nonce khác authorization request | Failure |
| Bad JWT signature | JWK không verify được | Failure |
| OP lệch clock nhỏ | Temporal claims nằm trong tolerance | Xác nhận behavior |
| OP lệch clock lớn | Temporal claims ngoài tolerance | Failure + clock health alert |

**Không coi mọi iat tương lai là một quy tắc validator thống nhất**: tiêu chí cụ thể tùy OIDC profile, Spring Security version và custom validators. Mục đích integration test là xác minh contract đang thực thi.

### 25.2. oidcLogin() chỉ mô phỏng principal

~~~java
mockMvc.perform(get("/private").with(oidcLogin()));
~~~

có thể dùng để test controller/authorization khi đã authenticated. Nó **không** chạy Token Endpoint, code exchange, ID Token signature/issuer/nonce validation hoặc authentication success/failure handler.

Để test clock skew trong OIDC login, cần callback thật với OP test/stub có JWT và validation hợp lệ.

### 25.3. Không chỉnh đồng hồ của CI runner

Sử dụng:

- Test JWT fixtures với temporal claims được chọn.
- <code>Clock.fixed</code>/<code>Clock.offset</code> ở các components có injected Clock.
- Test OP/Token Endpoint stub với public/private test signing keys.
- Negative fixtures cho expiry, iat, nonce và issuer.

Không dùng OS date command để thay đổi giờ host chung rồi sửa lại sau khi test.

## 26. Integration test: Authorization Server, Client và Resource Server

Một lab:

~~~text
Authorization Server test:
    issuer = https://sso.test.example
    access token TTL = 5 minutes

OAuth2 Client:
    authorized-client provider early refresh buffer = 60 seconds

Resource Server:
    issuer/audience/signature validation
    JWT timestamp tolerance = 30 seconds
~~~

**Đây là cấu hình test minh họa, không phải default production bắt buộc.**

### 26.1. Đồng hồ đồng bộ

1. OP phát token với <code>nbf/iat/exp</code> hợp lệ.
2. Client lấy token.
3. Client gọi Resource Server trước expiry.
4. Resource Server kiểm tra signature/issuer/audience/time.
5. Endpoint kiểm tra scope/role/business ownership và trả kết quả.

### 26.2. Client nhanh hơn 45 giây

1. Mô phỏng Client authorization decision clock nhanh 45 giây.
2. Client refresh sớm hơn nominal wall clock.
3. Không phát sinh refresh loop hoặc token churn bất thường.
4. API vẫn được gọi với access token đúng.

### 26.3. Resource Server chậm hơn 45 giây

1. OP phát JWT có <code>nbf=now</code>.
2. RS validator clock được cố định <code>now-45s</code>.
3. Khi tolerance 30 giây, timestamp validation thất bại.
4. Khi tolerance 60 giây theo policy test, timestamp có thể pass.
5. Signature/issuer/audience vẫn phải được kiểm tra độc lập.

### 26.4. Offset lớn vượt tolerance

Khi node lệch 5 phút nhưng tolerance chỉ 30–60 giây:

~~~text
Expected: token timestamp failure
Expected: node time synchronization alert
Expected: security validation remains enabled
~~~

Không tăng test tolerance lên 10 phút chỉ để làm test xanh.

### 26.5. Token Endpoint outage

Nếu Client định refresh nhưng Token Endpoint timeout/503:

- Không tự coi expired access token là còn hợp lệ vô hạn.
- Resource Server vẫn áp dụng validation theo policy.
- Ứng dụng có thể trả domain-level dependency error, bounded retry hoặc reauthorization theo ngữ cảnh.
- Không log hoặc trả raw refresh token/error description cho browser.

## 27. Phân biệt clock skew và những lỗi OAuth2 khác

| Triệu chứng | Có thể do clock skew? | Những nguyên nhân khác cần xét |
|---|---|---|
| JWT expired ngay sau issuance | Có | TTL rất ngắn, timezone/epoch conversion lỗi |
| JWT not-yet-valid | Có | OP phát nbf tương lai theo policy |
| ID Token iat future | Có thể | Test fixture/provider issue |
| Authorization code invalid_grant | Có thể gián tiếp | Code reuse, redirect_uri, PKCE, client mismatch |
| Refresh token invalid_grant | Có thể nhưng không mặc định | Rotation, revocation, client binding |
| OAuth state mismatch | Thường không trực tiếp | Cookie, session, multi-tab, request repository |
| Issuer mismatch | Không trực tiếp | Public OP hostname, discovery, wrong registration |
| Audience mismatch | Không | Client/resource ID |
| JWT signature invalid | Không | Wrong key/JWK, tampering |
| TLS certificate not yet valid | Có | Certificate validity/deployment |
| Resource Server 403 insufficient_scope | Không | Scope/role/tenant authorization |
| Token Endpoint 503 | Không trực tiếp | OP outage/network |

### 27.1. invalid_grant không mặc định là lỗi thời gian

Trong Authorization Code Flow, <code>invalid_grant</code> có thể vì code hết hạn, đã dùng lại, PKCE verifier sai, redirect URI sai hoặc client binding không đúng.

Trong Refresh Token Flow, có thể vì token bị revoke, rotation reuse detection, expired refresh token hoặc token family bị vô hiệu hóa.

Phải xem **grant type, stage và storage state** trước khi quy cho NTP.

### 27.2. Callback không tìm thấy authorization request

Lỗi:

~~~text
authorization_request_not_found
invalid_state
~~~

có thể do session cookie không quay về Portal, SameSite policy, reverse proxy, node B không đọc được shared session hoặc authorization request bị ghi đè. Tăng JWT tolerance không khôi phục được request correlation.

### 27.3. Dấu hiệu clock error xuất hiện ngoài OAuth2

Node lệch nhiều phút thường còn gặp:

~~~text
TLS certificate time errors
Scheduled jobs early/late
Unexpected cache expiration
Audit logs out of order
Database timestamps inconsistent
Distributed lease anomalies
~~~

Nếu nhiều service cùng có lỗi liên quan thời gian trên một node, điều tra node time synchronization trước.

## 28. Quy trình troubleshooting production

~~~mermaid
flowchart TD
    A["Login/API thất bại"] --> B{"Lỗi nói tới exp, nbf, iat hoặc certificate time?"}
    B -->|Không| C["Kiểm tra issuer/audience/PKCE/state/scope/network"]
    B -->|Có| D["Xác định OP, app, node/instance và UTC timestamps"]
    D --> E{"Node time synchronization healthy?"}
    E -->|Không| F["Sửa NTP/cloud time, cân nhắc isolate node"]
    E -->|Có| G["So observed offset với token exp/nbf/iat"]
    G --> H{"Offset trong budget nhưng gần expiry boundary?"}
    H -->|Có| I["Đo request latency, kiểm tra refresh buffer và leeway"]
    H -->|Không| J["Kiểm tra TTL, OP behavior, refresh race/storage"]
    F --> K["Chạy lại E2E login/API/TLS và quan sát metrics"]
    I --> K
    J --> K
~~~

### 28.1. Thu thập context

~~~text
service
instanceId / podName
nodeName
providerAlias
registrationId
operation = oidc_login | token_refresh | api_call
stage = callback | token_endpoint | resource_server
normalizedErrorCategory
UTC event timestamp
nodeClockSyncStatus
correlationId
~~~

Không đưa ID Token, code, state, client secret, Authorization header hoặc session cookies vào logs.

### 28.2. Kiểm tra từng lớp

1. **OP:** JWT issuance timestamps, time service, issuer settings.
2. **Client:** Node wall clock, token expiresAt, refresh buffer.
3. **Resource Server:** Node wall clock, JWT timestamp validator, issuer/audience.
4. **TLS:** Certificate NotBefore/NotAfter, JVM truststore, current host time.
5. **Session:** Cookie/SameSite, state repository, session TTL.
6. **Telemetry:** UTC timestamps, node labels, offset metrics.

### 28.3. Incident với nhiều regions

Đừng so <code>10:00:00</code> từ một region và <code>17:00:00</code> từ region khác nếu chúng được ghi theo local timezone. Chuẩn hóa thành UTC instants trước khi xác định causal ordering.

## 29. Runbook khi host lệch thời gian

### 29.1. Xác định phạm vi

~~~text
Affected:
  OAuth2 Login?
  Resource Server JWT?
  Background token refresh?
  TLS to OP?
  Session store?

Scope:
  One pod?
  One node?
  One availability zone?
  OP itself?
~~~

### 29.2. Thu thập trạng thái

Linux:

~~~bash
date -u
timedatectl status
chronyc tracking
chronyc sources -v
~~~

Windows:

~~~powershell
w32tm /query /status
w32tm /query /source
~~~

### 29.3. Khắc phục hạ tầng trước

1. Xác minh NTP/time service hoạt động.
2. Kiểm tra time-source DNS/network reachability.
3. Đối chiếu current offset, drift/frequency, last synchronization.
4. Nếu node lệch nặng, cân nhắc rút khỏi traffic theo runbook.
5. Sửa node time sync hoặc thay node theo quy trình platform.
6. Chỉ đưa node nhận traffic trở lại khi clock health đạt policy.
7. Đo lại login failure, invalid_token và TLS errors.

Không tùy tiện đổi system clock của máy chia sẻ hoặc domain controller.

### 29.4. Chỉnh application config sau khi node healthy

Khi clocks đã đồng bộ mà token vẫn thường hết hạn giữa API request:

- Đo Token Endpoint/API latency.
- Kiểm tra issuedAt/expiresAt conversion và token TTL.
- Điều chỉnh early refresh buffer hợp lý.
- Đánh giá validator leeway theo threat model.
- Rà soát refresh rotation/concurrency và token storage.
- Test boundary, rollout nhỏ và theo dõi metrics.

Không dùng một tolerance hàng chục phút để che sự cố NTP.

### 29.5. Xác minh hậu khắc phục

1. OIDC login E2E thành công.
2. ID Token sai issuer/expired ngoài tolerance vẫn bị từ chối.
3. Resource Server nhận access token hợp lệ, từ chối token quá hạn.
4. Refresh token xảy ra đúng threshold.
5. Không có refresh loop/race mới.
6. TLS handshake với OP/Discovery/JWKS thành công.
7. UTC metrics/logs nhất quán.
8. Node time offset trở về SLO.

## 30. Anti-patterns cần tránh

### 30.1. Tắt token expiry validation

Không bỏ <code>exp</code>/<code>nbf</code> để tránh lỗi user đăng nhập. Cần sửa đồng hồ và tolerance có giới hạn.

### 30.2. Bỏ issuer/audience/signature để “khắc phục”

JWT timestamp hợp lệ không chứng minh JWT do đúng OP ký hoặc được phát cho đúng Client/Resource Server. Không bỏ trust validation.

### 30.3. Dùng leeway cực lớn

Leeway có thể gia tăng thời gian một token bị lộ tiếp tục được chấp nhận; cần security review và monitoring.

### 30.4. Dùng LocalDateTime làm expiration absolute

<code>LocalDateTime</code> thiếu timezone/offset, có thể bị diễn giải khác giữa nodes. Dùng <code>Instant</code>.

### 30.5. Dùng System.nanoTime làm epoch

<code>System.nanoTime()</code> để đo duration, không phải Unix timestamp.

### 30.6. Tạo một scheduler refresh trên mỗi node mà không coordination

Clock buffer không tự serialize token requests; với rotation, có thể tạo replay/race.

### 30.7. Retry invalid_grant vô hạn

Code hoặc refresh token đã tiêu thụ không trở lại hợp lệ chỉ bằng retry; reuse có thể làm token family bị revoke.

### 30.8. Restart Pod để “reset NTP”

Clock của container thường là clock host node. Restart Pod không sửa NTP outage node.

### 30.9. Đổi giờ CI runner để kiểm thử

Việc chỉnh OS clock có thể làm TLS, package manager, background jobs và tests khác bị hỏng; dùng fixed Clock/JWT fixture.

### 30.10. Log raw tokens vì cần xem exp

Token có thể chứa credentials và PII. Dùng expiry delta đã lọc và metadata an toàn, hạn chế raw JWT diagnostics.

## 31. Ma trận kịch bản kiểm thử

| ID | Scenario | Kỳ vọng |
|---|---|---|
| TIME-01 | OP/Client/RS clocks gần nhau | Token hợp lệ được nhận |
| TIME-02 | JWT exp quá hạn trong tolerance | Timestamp behavior theo policy |
| TIME-03 | JWT exp quá hạn ngoài tolerance | Token bị từ chối |
| TIME-04 | JWT nbf tương lai trong tolerance | Timestamp behavior theo policy |
| TIME-05 | JWT nbf tương lai ngoài tolerance | Token bị từ chối |
| TIME-06 | ID Token iat future | OIDC/profile checks đúng |
| TIME-07 | ID Token expired | Login failure |
| TIME-08 | Signature sai, time đúng | Vẫn failure |
| TIME-09 | Issuer/audience sai, time đúng | Vẫn failure |
| TIME-10 | Token còn 91s, buffer 90s | Chưa refresh |
| TIME-11 | Token còn 90s, buffer 90s | Refresh theo policy |
| TIME-12 | TTL nhỏ hơn refresh buffer | Không tạo refresh loop |
| TIME-13 | Token Endpoint latency cao | Không gửi token sắp chết tùy tiện |
| TIME-14 | Token Endpoint timeout | Unknown outcome/recovery theo policy |
| TIME-15 | Hai nodes cùng dùng R0 | Không xóa nhầm R1 |
| TIME-16 | Một K8s node lệch 5 phút | Detect/alert/isolate |
| TIME-17 | JVMs dùng timezone khác nhau | Instant comparison vẫn đúng |
| TIME-18 | Epoch seconds/millis conversion | Không tạo expiry vô lý |
| TIME-19 | TLS cert not yet valid | Điều tra clock/cert, không trust-all |
| TIME-20 | API 403 insufficient_scope | Không coi là time skew |
| TIME-21 | Callback missing state | Điều tra session, không disable state |
| TIME-22 | VM resume sau suspend | Đồng bộ trước khi nhận traffic |
| TIME-23 | NTP source unreachable | Alert & recovery |
| TIME-24 | NTP phục hồi | OIDC login/JWT/TLS ổn định |

Chia unit deterministic, component protocol tests, OP integration và infrastructure chaos tests theo chi phí. Security-critical tests phải giữ những trường hợp sai issuer/signature và ngoài tolerance.

## 32. Bài tập tự luyện

### Bài 1 — Timezone hay clock skew?

Server A ghi <code>10:00 UTC</code>, server B ghi <code>17:00 Asia/Ho_Chi_Minh</code>.

**Đáp án:** Có thể là cùng instant; chuyển về UTC để so sánh trước khi nói clocks lệch.

### Bài 2 — JWT exp và leeway

JWT exp=10:30:00, RS now=10:30:40, allowance=60s.

**Đáp án:** Timestamp validation có thể pass trong tolerance; chữ ký/issuer/audience/quyền vẫn phải hợp lệ.

### Bài 3 — JWT nbf

JWT nbf=10:00:00, RS now=09:58:30, leeway=60s.

**Đáp án:** Chưa đạt not-before vì lệch 90 giây > 60 giây.

### Bài 4 — Refresh buffer

expiresAt=10:30:00, buffer=90s.

**Đáp án:** Client có thể bắt đầu refresh từ 10:28:30.

### Bài 5 — Leeway khác buffer

**Đáp án:** Validator leeway nới cửa sổ nhận JWT; early refresh buffer quyết định lúc Client xin token mới.

### Bài 6 — Offset giữa nodes

Node A nhanh +45s, node B chậm -40s.

**Đáp án:** Chênh lệch giữa A và B là 85 giây.

### Bài 7 — NumericDate

Developer ghi <code>System.currentTimeMillis()</code> vào <code>exp</code>.

**Đáp án:** Sai đơn vị phổ biến; NumericDate dùng seconds, còn currentTimeMillis dùng milliseconds.

### Bài 8 — LocalDateTime trong database

Token expiry được lưu dạng <code>2026-11-16 10:30:00</code> không timezone.

**Đáp án:** Không an toàn khi các readers có timezone khác nhau; dùng Instant/UTC-aware mapping.

### Bài 9 — API 403

Resource Server báo <code>insufficient_scope</code>.

**Đáp án:** Đây là authorization/scope issue, không tự điều chỉnh clock skew để sửa.

### Bài 10 — Refresh R0

Node A lưu R1, Node B với R0 nhận invalid_grant.

**Đáp án:** Có thể là rotation race; dùng coordination/re-read/versioned conditional cleanup.

### Bài 11 — Docker timezone

Pod A dùng <code>TZ=UTC</code>, Pod B dùng <code>TZ=Asia/Ho_Chi_Minh</code>.

**Đáp án:** Timezone hiển thị khác không tự làm Instant khác; cần xem clock offset của các host nodes.

### Bài 12 — Node lệch 5 phút

Nhóm muốn tăng JWT leeway lên 10 phút.

**Đáp án:** Không xem đó là root fix; phải sửa time source/NTP, isolate node lỗi và giữ leeway phù hợp threat model.

### Bài 13 — Nonce mismatch

ID Token chưa hết hạn nhưng <code>nonce</code> không khớp.

**Đáp án:** OIDC login phải fail; clock skew không làm nonce hợp lệ.

### Bài 14 — TLS certificate

Token Endpoint báo certificate not yet valid.

**Đáp án:** Kiểm tra host clock/certificate validity/truststore. JwtTimestampValidator không tác động TLS.

### Bài 15 — Chrony

**Yêu cầu:** Dùng <code>chronyc tracking</code> và <code>chronyc sources -v</code> xác định node có synchronized không.

**Gợi ý:** Xem offset, stratum, reachability, reference source, last sync và drift; không chỉ xem timezone.

### Bài 16 — Clock.fixed

**Yêu cầu:** Test ExpiryPolicy tại 10:28:29 và 10:28:30 với expiry 10:30, buffer 90s.

**Đáp án:** Trước ngưỡng false; đúng ngưỡng true.

### Bài 17 — Clock.offset

Mô phỏng Client nhanh 30 giây bằng <code>Clock.offset(base, Duration.ofSeconds(30))</code>.

**Đáp án:** Có thể test early-refresh decision mà không thay đồng hồ OS.

### Bài 18 — Test JWT leeway

JWT vừa hết hạn 30 giây, validator leeway 60 giây.

**Đáp án:** Timestamp condition có thể pass; decoder full pipeline vẫn phải verify signature/issuer/audience.

### Bài 19 — invalid_grant trong code exchange

Token Endpoint từ chối authorization code.

**Đáp án:** Điều tra code TTL, reuse, PKCE, redirect URI và ClientRegistration; clock skew có thể liên quan nhưng không mặc định.

### Bài 20 — One-node incident

Chỉ node C báo expired/not-yet-valid nhiều.

**Đáp án:** Correlate pod/node, đo NTP offset, isolate node nếu cần, sửa time sync, kiểm tra alerts và JWT validation sau phục hồi.

### Bài 21 — Unknown refresh outcome

OP phát R1 từ R0 nhưng response timeout.

**Đáp án:** Client không biết R0 đã tiêu thụ chưa. Retry mù có thể tạo invalid_grant/reuse detection; cần recovery coordination.

### Bài 22 — Step-up auth_time

User xác thực 8 phút trước, endpoint yêu cầu authentication trong 5 phút.

**Đáp án:** Cần reauthentication/step-up theo policy, không tăng leeway để hợp thức hóa auth_time quá cũ.

### Bài 23 — Logging

Đội vận hành log toàn bộ JWT/code/state để xem timestamps.

**Đáp án:** Rủi ro lộ credentials/PII. Dùng metrics offset, normalized errors và expiry delta đã lọc.

### Bài 24 — Thực hành tổng hợp

Xây lab bao gồm:

1. OP test phát JWT với TTL xác định.
2. Spring Security OIDC Client dùng Authorization Code Flow.
3. Resource Server kiểm tra signature, issuer, audience và timestamps.
4. Early refresh buffer được cấu hình riêng với JWT validation leeway.
5. Unit tests dùng <code>Clock.fixed</code> cho <code>exp/nbf</code> boundaries.
6. Unit tests dùng <code>Clock.offset</code> cho fast/slow Client clocks.
7. OIDC integration tests dùng signed ID Tokens từ test OP.
8. Negative tests wrong issuer/signature/nonce vẫn fail dù temporal claims hợp lệ.
9. Test JWT expired ngoài tolerance.
10. Test Resource Server 401/403 phân loại đúng.
11. Test refresh-token rotation trên hai nodes không xóa nhầm bản mới.
12. Theo dõi node time offsets và synchronization status.
13. Test TLS cert validity errors mà không tắt TLS validation.
14. Ghi runbook phục hồi NTP và logs an toàn.

Giải thích vì sao **NTP synchronization**, **JWT validation leeway** và **OAuth2 early refresh buffer** là ba cơ chế khác nhau, cần vận hành và kiểm thử tách biệt.

## 33. Tổng kết

- **UTC Instant** là cơ sở cho token expiration; timezone chỉ ảnh hưởng hiển thị. JWT NumericDate thường dùng epoch seconds.
- OIDC và OAuth2 có nhiều mốc thời gian: <code>exp</code>, <code>nbf</code>, <code>iat</code>, <code>auth_time</code>, authorization code TTL, access token <code>expiresAt</code>, refresh policy và TLS certificate validity.
- **JwtTimestampValidator leeway** chấp nhận một sai số nhỏ khi kiểm tra timestamp, có tác động security vì mở rộng cửa sổ token được nhận.
- **OAuth2AuthorizedClientProvider clockSkew/early refresh buffer** làm Client xin token mới trước hạn; không tự đổi JWT validation ở Resource Server.
- Đừng dùng cùng một Duration cho cả hai mà không hiểu semantics, token TTL và threat model.
- Đồng bộ NTP/chrony/Windows Time/cloud time service là nền tảng; không dùng leeway lớn để thay time synchronization.
- Containers thường chia sẻ wall clock của host node; restart Pod không sửa đồng hồ node.
- Java <code>Instant</code> và <code>Clock</code> thích hợp cho expiry/tests; monotonic elapsed time thích hợp đo latency.
- <code>OAuth2AuthorizedClientProviderBuilder</code> có thể cấu hình early refresh cho refresh-token/client-credentials providers.
- <code>JwtTimestampValidator</code> không thay signature, issuer, audience, nonce hoặc authorization checks. Không thay validator chain thành timestamp-only.
- OIDC ID Token validation có pipeline riêng, cần temporal claims và những checks theo OIDC flow.
- HTTP 401 <code>invalid_token</code> có thể do thời gian nhưng cũng có thể do trust/audience/revocation. HTTP 403 <code>insufficient_scope</code> là lỗi permission.
- Refresh rotation races vẫn tồn tại khi clocks đồng bộ; cần lock/single-flight, re-read, CAS và conditional cleanup.
- Clock step có thể ảnh hưởng jobs, caches và locks; dùng platform runbook thay vì đổi OS clock tùy tiện.
- Unit tests nên dùng <code>Clock.fixed</code>, <code>Clock.offset</code> và JWT fixtures; integration tests vẫn phải kiểm tra signature/issuer/audience.
- Observability cần UTC timestamps, node offset/synchronization status, operation/stage/category và metrics có cardinality giới hạn, không log tokens/code/state/secrets.
- Runbook production phải xác định node/issuer bị ảnh hưởng, sửa time source rồi xác minh E2E OIDC Login, Resource Server JWT và TLS sau phục hồi.

### Tài liệu tham khảo

- **Spring Security Reference — OAuth2 Client:** authorized-client providers, token refresh, client credentials và clockSkew.
- **Spring Security Java API — OAuth2AuthorizedClientProviderBuilder:** cấu hình refresh/client-credentials providers.
- **Spring Security Java API — JwtTimestampValidator:** exp, nbf, Clock và timestamp tolerance.
- **Spring Security Reference — OAuth2 Resource Server JWT:** issuer, JWT signature, timestamps và audience validation.
- **Spring Security Reference — OIDC Login:** ID Token validation, nonce, issuer, audience và authentication flows.
- **RFC 7519 — JSON Web Token (JWT):** NumericDate, exp, nbf, iat và clock skew leeway.
- **RFC 6749 — OAuth 2.0 Authorization Framework:** token expiration metadata, authorization code và refresh grants.
- **RFC 6750 — Bearer Token Usage:** invalid_token, insufficient_scope và Resource Server HTTP errors.
- **RFC 9700 — Best Current Practice for OAuth 2.0 Security:** token replay, refresh rotation và OAuth security.
- **OpenID Connect Core 1.0:** ID Token temporal claims, auth_time, nonce và max_age.
- **Java Platform API — java.time.Clock, Instant, Duration:** UTC instants và deterministic tests.
- **chrony Documentation — tracking and sources:** clock offset, frequency/drift và time source monitoring.
- **systemd-timesyncd/timedatectl Documentation:** Linux time synchronization.
- **Microsoft Windows Time Service Documentation:** w32tm và Windows Time hierarchy.
- **Kubernetes/Cloud Provider Node Time Documentation:** host clocks, managed node synchronization và containers.
- **OWASP Logging Cheat Sheet:** log events an toàn, UTC timestamps và không lưu credentials/PII.
