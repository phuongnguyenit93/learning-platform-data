# Test clock skew: kiểm thử sai lệch đồng hồ khi xác minh token

## 1. Bối cảnh và mục tiêu

Trong OAuth 2.0 và OpenID Connect, access token thường mang các mốc thời gian để giới hạn vòng đời. Với JWT, các claim như **exp** (thời điểm hết hạn), **nbf** (thời điểm bắt đầu có hiệu lực) và **iat** (thời điểm phát hành) được biểu diễn theo **NumericDate**. Authorization server phát hành token theo đồng hồ của nó; resource server xác minh token theo đồng hồ của máy đang xử lý request. Nếu hai đồng hồ lệch nhau, một token hợp lệ có thể bị từ chối quá sớm hoặc một token đáng lẽ đã hết hạn vẫn được chấp nhận.

Sai lệch này gọi là **clock skew**. Nó có thể đến từ NTP không đồng bộ, máy ảo/container bị suspend, cấu hình thời gian sai, đồng hồ host bị điều chỉnh, nhiều node có offset khác nhau hoặc môi trường test dùng thời gian không được kiểm soát.

**Test clock skew** kiểm tra hệ thống xác minh token hoạt động đúng khi đồng hồ giữa issuer, resource server và các thành phần liên quan không hoàn toàn giống nhau. Bài học thuộc chương **Integration testing** của module **SECURITY_TOKEN_SECURITY_FUNDAMENTALS**, gắn với mô hình tin cậy và vòng đời token, JWT/opaque token, access/refresh token, claims, scope, audience, lưu trữ, thu hồi và chống token bị đánh cắp hoặc phát lại.

Sau bài này, người học có thể:

1. Giải thích ảnh hưởng của clock skew lên **exp**, **nbf** và **iat**.
2. Xác định cách áp dụng leeway (khoảng dung sai) có giới hạn và nhất quán.
3. Viết kiểm thử xác định ở các mốc trước, đúng tại và sau ranh giới thời gian.
4. Tạo integration test với clock giả lập thay vì phụ thuộc vào sleep.
5. Kiểm tra sai lệch giữa nhiều resource server, cache, issuer và môi trường triển khai.
6. Phân biệt lỗi thời gian với lỗi chữ ký, issuer, audience, scope hoặc trạng thái thu hồi.

## 2. Clock skew và các loại đồng hồ

Giả sử Authorization Server phát hành JWT lúc 10:00:00 UTC, **exp** là 10:05:00 UTC. Resource Server A có đồng hồ nhanh hơn 40 giây; Resource Server B có đồng hồ chậm hơn 50 giây. Cùng một token có thể bị A xem là hết hạn sớm, trong khi B tiếp tục chấp nhận sau thời điểm hết hạn thực tế.

| Thành phần | Đồng hồ được dùng | Tác động nếu sai lệch |
| --- | --- | --- |
| Authorization Server / issuer | Tạo **iat**, **nbf**, **exp** khi phát hành token | Phát hành token với mốc thời gian quá sớm hoặc quá muộn. |
| API Gateway | Xác minh token trước khi route | Có thể từ chối request trước khi downstream nhận được. |
| Resource Server | Xác minh access token tại API | Có thể chấp nhận hoặc từ chối token khác với node khác. |
| Introspection service | Đánh giá trạng thái opaque token và metadata | Kết quả active có thể khác thời điểm nếu service dùng clock/cache không nhất quán. |
| Job/worker | Refresh token, xử lý scheduled task hoặc kiểm tra session | Có thể refresh quá sớm, quá muộn hoặc xử lý token đã hết hạn. |
| Test runner | Tạo token, điều khiển thời gian và kiểm tra kết quả | Test flaky nếu phụ thuộc đồng hồ thật và thời gian chờ thực. |

### 2.1. Wall clock và monotonic clock

JWT NumericDate dựa trên thời gian tuyệt đối kể từ Unix epoch, vì vậy việc kiểm tra **exp**, **nbf** và **iat** cần một **wall clock** có thể ánh xạ sang UTC/Instant. Trong Java, Instant hoặc Clock là các API phù hợp để biểu diễn thời điểm tuyệt đối.

**Monotonic clock** đo thời lượng trôi qua và không nên bị lùi/nhảy do đồng bộ giờ hệ thống. Nó phù hợp để đo timeout, latency, thời gian thực thi và backoff. Không dùng monotonic counter làm giá trị exp hoặc iat; ngược lại, không dùng wall clock để đo duration nhạy với việc đồng hồ bị điều chỉnh.

Múi giờ hiển thị (UTC, GMT+7...) không làm thay đổi NumericDate. Nên chuẩn hóa xử lý về UTC/Instant; không cộng trừ offset múi giờ thủ công khi xác minh JWT.

## 3. Các claim thời gian trong JWT

### 3.1. exp — expiration time

**exp** chỉ ra thời điểm hoặc sau thời điểm đó JWT không còn được chấp nhận. Theo RFC 7519, thời điểm hiện tại phải **trước exp**; sau khi đến hoặc vượt thời điểm này, token không được chấp nhận. Hệ thống có thể cho phép một khoảng leeway nhỏ để bù sai lệch đồng hồ.

Ví dụ token có exp là 10:05:00Z:

- Không có leeway: tại 10:04:59 token còn hiệu lực; tại 10:05:00 token đã hết hạn.
- Leeway 30 giây: validator có thể tiếp tục chấp nhận tới ngay trước 10:05:30; tại hoặc sau ranh giới exp + leeway, token phải bị từ chối.

Leeway làm tăng khoảng thời gian token còn được chấp nhận. Vì vậy không đặt leeway quá rộng chỉ để làm giảm lỗi 401.

### 3.2. nbf — not before

**nbf** chỉ ra thời điểm trước đó JWT chưa được chấp nhận. Nếu resource server có đồng hồ chậm hơn issuer, token có thể bị xem là chưa có hiệu lực ngay sau khi được phát hành. Leeway cho phép một khoảng dung sai nhỏ trước nbf.

Với leeway L, quy tắc kiểm tra phổ biến là từ chối khi now + L < nbf. Tại ranh giới now + L = nbf, token có thể được chấp nhận. Cần xác minh đúng semantics của thư viện JWT đang dùng, vì cách đặt dấu bằng và đơn vị thời gian có thể khác nhau.

### 3.3. iat — issued at

**iat** ghi nhận thời điểm JWT được phát hành. RFC 7519 không quy định mọi validator bắt buộc phải từ chối token chỉ vì iat nằm trong tương lai; ứng dụng có thể áp dụng policy kiểm tra iat để phát hiện token có thời gian phát hành bất thường.

Nếu policy kiểm tra iat, cần xác định rõ:

- Có từ chối iat lớn hơn now + leeway hay không.
- Có giới hạn tuổi token tối đa hay không (ví dụ token không được cũ quá 10 phút).
- Khi clock issuer chậm hơn resource server, iat có thể trông như nằm trong quá khứ nhiều hơn thực tế.
- Khi clock issuer nhanh hơn resource server, iat có thể trông như nằm trong tương lai.

Không dùng iat thay cho exp. Một token có iat cũ không mặc nhiên hết hạn nếu không có exp hoặc chính sách tuổi token được áp dụng.

### 3.4. NumericDate và độ chính xác

NumericDate biểu diễn số giây kể từ Unix epoch tại UTC; giá trị có thể là số nguyên hoặc có phần thập phân. Nhiều thư viện hoặc định dạng lưu trữ chỉ giữ độ chính xác đến giây. Kiểm thử cần biết hệ thống làm tròn, cắt phần thập phân hay giữ milliseconds để đặt expected boundary chính xác.

Không tạo token bằng cách chuyển thời gian sang chuỗi local như 2026-11-23 10:05:00 rồi tự parse trong từng service. Dùng giá trị epoch/Instant nhất quán và kiểm thử ở các biên có phần mili giây nếu hệ thống hỗ trợ.

## 4. Leeway: dung sai có giới hạn

**Leeway** là khoảng thời gian cho phép để bù sai lệch giữa đồng hồ phát hành và đồng hồ xác minh. RFC 7519 cho phép một khoảng nhỏ; tài liệu nêu thông lệ thường không quá vài phút. Đây không phải khuyến nghị đặt mặc định vài phút cho mọi hệ thống. Giá trị phù hợp cần dựa trên khả năng đồng bộ thời gian, độ nhạy của API và threat model.

Ví dụ với leeway 30 giây:

| Claim | Điều kiện minh họa để chấp nhận | Điều kiện bị từ chối |
| --- | --- | --- |
| exp | now - L < exp | now - L >= exp |
| nbf | now + L >= nbf | now + L < nbf |
| iat nếu policy kiểm tương lai | iat <= now + L | iat > now + L |
| Tuổi tối đa nếu policy áp dụng | now - iat <= maxAge + L | now - iat > maxAge + L |

Đây là mô hình minh họa để thiết kế test. Cần xác nhận semantics thực tế của thư viện, nhất là việc so sánh tại ranh giới, độ chính xác NumericDate và cách áp leeway cho từng claim.

### 4.1. Leeway quá nhỏ hoặc không đồng nhất

- Quá nhỏ: node có offset vài giây có thể từ chối token gần nbf hoặc exp, gây lỗi không ổn định.
- Quá lớn: token hết hạn vẫn có thể được dùng lâu hơn, tăng thời gian replay nếu token bị đánh cắp.
- Mỗi service cấu hình khác nhau: API Gateway chấp nhận nhưng downstream từ chối, hoặc ngược lại.
- Chỉ cấu hình leeway ở một số validator: các luồng JWT, opaque introspection và refresh token có hành vi không đồng nhất.

Nên quản lý leeway như một policy có chủ đích, thống nhất theo nhóm resource server và có kiểm thử cấu hình. Không tự ý tăng leeway tại từng service để xử lý sự cố.

## 5. Mô hình kiểm thử clock skew

Giả sử:

- Issuer clock: T.
- Resource Server clock: T + delta.
- delta > 0: resource server chạy **nhanh** hơn issuer.
- delta < 0: resource server chạy **chậm** hơn issuer.
- L: leeway được cấu hình tại validator.

~~~mermaid
flowchart TD
    I[Issuer phát hành JWT tại T] --> C[JWT có iat, nbf, exp]
    C --> R[Resource Server kiểm tra tại T + delta]
    R --> V{delta và leeway L}
    V -->|Token nằm trong cửa sổ chấp nhận| A[Accept]
    V -->|Vượt exp hoặc chưa tới nbf| D[Deny]
    A --> P[Tiếp tục kiểm scope, audience và quyền]
    D --> E[401 / invalid_token theo policy]
~~~

### 5.1. Các chiều cần kiểm tra

| Chiều test | Mục đích |
| --- | --- |
| Issuer nhanh hơn resource server | Xác minh token có iat/nbf ở tương lai tương đối với validator. |
| Issuer chậm hơn resource server | Xác minh token bị xem là hết hạn sớm. |
| Clock lệch dương và âm | Không chỉ test một chiều offset. |
| Offset nhỏ hơn, bằng và lớn hơn leeway | Xác minh đúng ranh giới chấp nhận. |
| exp gần thời điểm hiện tại | Kiểm tra token vừa hết hạn và leeway. |
| nbf ở tương lai | Kiểm tra token chưa có hiệu lực. |
| iat tương lai/tuổi token | Kiểm tra policy bổ sung nếu ứng dụng bật. |
| Nhiều resource server | Kiểm tra các node dùng policy/time source thống nhất. |
| Cache và introspection | Kiểm tra độ trễ cập nhật khi trạng thái thay đổi. |

### 5.2. Ma trận biên cho exp và nbf

Với L=30s, lấy thời gian validator là now:

| Claim | Giá trị claim | Kỳ vọng theo quy tắc minh họa |
| --- | --- | --- |
| exp | now + 1s | Accept |
| exp | now | Accept nếu leeway cho phép; nếu L=0, reject |
| exp | now - 29s | Accept khi L=30s |
| exp | now - 30s | Reject tại biên now - L == exp |
| exp | now - 31s | Reject |
| nbf | now - 1s | Accept |
| nbf | now + 29s | Accept khi L=30s |
| nbf | now + 30s | Accept tại biên now + L == nbf theo quy tắc minh họa |
| nbf | now + 31s | Reject |

Các hàng có exp=now cần đọc đúng semantics: nếu leeway bằng 0 thì JWT đã hết hạn tại exp; nếu leeway dương thì có thể còn trong cửa sổ dung sai. Không suy luận expected chỉ từ tên method; hãy kiểm thử thư viện và policy thật.

## 6. Thiết kế integration test xác định bằng clock giả lập

Không nên dùng Thread.sleep() để chờ token hết hạn. Cách đó làm test chậm, phụ thuộc tải máy và có thể flaky. Thay vào đó:

1. Tiêm Clock hoặc time provider vào thành phần phát hành token nếu kiểm soát được issuer trong test.
2. Tiêm clock vào validator tự viết hoặc cấu hình time source mà thư viện hỗ trợ.
3. Tạo token có iat, nbf, exp cụ thể dựa trên một Instant cố định.
4. Dịch clock issuer và clock resource server độc lập.
5. Kiểm tra kết quả ở các offset trước/sau ranh giới mà không đợi thời gian thật trôi qua.

### 6.1. Ví dụ Java: time policy có thể kiểm thử

Đoạn code sau minh họa logic thời gian độc lập với thư viện JWT. Đây là ví dụ học tập; validator production còn phải xác minh chữ ký, issuer, audience, token type và các policy khác.

~~~java
public final class JwtTimePolicy {
    private final Clock clock;
    private final Duration leeway;

    public JwtTimePolicy(Clock clock, Duration leeway) {
        if (leeway.isNegative()) {
            throw new IllegalArgumentException("leeway must not be negative");
        }
        this.clock = clock;
        this.leeway = leeway;
    }

    public boolean isValid(Instant expiresAt, Instant notBefore) {
        Instant now = clock.instant();

        // exp: now - leeway phải vẫn nằm trước exp.
        if (expiresAt != null && !now.minus(leeway).isBefore(expiresAt)) {
            return false;
        }

        // nbf: now + leeway phải đạt tới hoặc vượt nbf.
        if (notBefore != null && now.plus(leeway).isBefore(notBefore)) {
            return false;
        }

        return true;
    }
}
~~~

Sử dụng Clock.fixed để kiểm tra:

~~~java
class JwtTimePolicyTest {
    private static final Instant BASE =
        Instant.parse("2026-11-23T10:00:00Z");

    @Test
    void acceptsTokenWithinExpirationLeeway() {
        Clock clock = Clock.fixed(BASE, ZoneOffset.UTC);
        JwtTimePolicy policy =
            new JwtTimePolicy(clock, Duration.ofSeconds(30));

        assertThat(policy.isValid(BASE.minusSeconds(29), null)).isTrue();
    }

    @Test
    void rejectsTokenAtExpirationLeewayBoundary() {
        Clock clock = Clock.fixed(BASE, ZoneOffset.UTC);
        JwtTimePolicy policy =
            new JwtTimePolicy(clock, Duration.ofSeconds(30));

        assertThat(policy.isValid(BASE.minusSeconds(30), null)).isFalse();
    }

    @Test
    void rejectsTokenNotYetValidBeyondLeeway() {
        Clock clock = Clock.fixed(BASE, ZoneOffset.UTC);
        JwtTimePolicy policy =
            new JwtTimePolicy(clock, Duration.ofSeconds(30));

        assertThat(policy.isValid(null, BASE.plusSeconds(31))).isFalse();
    }
}
~~~

Trong code thực tế, không nên tự viết lại toàn bộ validator nếu thư viện JWT/Spring Security đã cung cấp cơ chế được kiểm thử. Dùng ví dụ để hiểu semantics và tạo test cho **cấu hình validator thật**. Nếu thư viện không cho tiêm clock, có thể bọc time policy hoặc dùng một abstraction phù hợp trong adapter của ứng dụng; tránh thay đổi đồng hồ hệ điều hành trong test suite thông thường.

### 6.2. Test issuer và resource server với hai clock

~~~java
Instant base = Instant.parse("2026-11-23T10:00:00Z");
Clock issuerClock = Clock.fixed(base, ZoneOffset.UTC);
Clock resourceClock = Clock.offset(issuerClock, Duration.ofSeconds(45));

String jwt = testIssuer.issueAccessToken(
    issuerClock,
    base.minusSeconds(10),   // iat
    base.minusSeconds(5),    // nbf
    base.plusSeconds(60));   // exp

HttpResponse response = resourceServer.callWithBearer(jwt, resourceClock);
~~~

Các hàm issueAccessToken và callWithBearer là helper giả định của test harness. Điểm quan trọng là test điều khiển **độc lập** thời gian của issuer và resource server; không sửa system clock toàn máy. Thay đổi offset theo từng test để kiểm tra nhanh/chậm và leeway.

## 7. Kiểm thử cấu hình JWT validator trong Spring Security

Spring Security Resource Server có các validator thời gian cho JWT. Cần kiểm tra phiên bản thư viện và cấu hình ứng dụng thực tế, vì default leeway và API cấu hình có thể thay đổi theo phiên bản. Ví dụ, JwtTimestampValidator hỗ trợ cấu hình clock skew; không nên giả định mọi validator tùy chỉnh tự dùng cùng giá trị này.

Ví dụ cấu hình khái niệm:

~~~java
Duration allowedClockSkew = Duration.ofSeconds(30);
JwtTimestampValidator timestampValidator = new JwtTimestampValidator();
timestampValidator.setClockSkew(allowedClockSkew);

OAuth2TokenValidator<Jwt> issuerValidator =
    new JwtIssuerValidator("https://auth.example.com");

OAuth2TokenValidator<Jwt> validator =
    new DelegatingOAuth2TokenValidator<>(
        issuerValidator,
        timestampValidator,
        audienceValidator("orders-api")
    );
~~~

audienceValidator ở trên là validator ứng dụng tự định nghĩa. Khi viết test, xác minh:

- Leeway cấu hình đúng và được áp dụng cho exp/nbf.
- iat tương lai có được kiểm tra hay không theo policy ứng dụng; không mặc định framework tự từ chối.
- Audience validator vẫn chạy; clock skew không được làm bỏ qua issuer, audience hoặc chữ ký.
- Các resource server sử dụng cùng policy thời gian.
- Token sai chữ ký hoặc issuer vẫn bị từ chối ngay cả khi exp/nbf nằm trong cửa sổ leeway.

Nếu cần điều khiển clock của thư viện, xem API chính xác của phiên bản đang dùng. Có thể kiểm tra logic thời gian ở unit test bằng Clock riêng và kiểm thử integration với validator thật bằng token có claim được tạo tương đối so với thời gian test. Không reflection hoặc thay đổi global system clock để ép thư viện.

## 8. Test matrix cho clock skew

| ID | Tình huống | Setup | Kết quả mong đợi |
| --- | --- | --- | --- |
| CS-001 | Không có skew | Issuer và resource server cùng T | Token còn hạn và đã tới nbf được chấp nhận. |
| CS-002 | Resource server nhanh hơn issuer | delta=+10s, L=30s | Token vẫn trong leeway được chấp nhận. |
| CS-003 | Resource server chậm hơn issuer | delta=-10s, L=30s | Token mới phát hành không bị từ chối vì nbf trong giới hạn. |
| CS-004 | Skew nhỏ hơn leeway | abs(delta)=20s, L=30s | Kết quả theo policy leeway, không phát sinh 401 bất thường. |
| CS-005 | Skew bằng leeway | abs(delta)=30s, L=30s | Kết quả đúng semantics boundary của validator. |
| CS-006 | Skew vượt leeway | abs(delta)=31s, L=30s | Token vượt ranh giới thời gian bị từ chối. |
| CS-007 | Token vừa hết hạn | exp tại now | Reject khi không có leeway; với leeway dương kiểm tra đúng cửa sổ. |
| CS-008 | Token quá hạn trong leeway | now-exp < L | Accept nếu các kiểm tra khác hợp lệ. |
| CS-009 | Token quá hạn ngoài leeway | now-exp > L | Reject. |
| CS-010 | Token chưa tới nbf trong leeway | nbf-now < L | Accept theo policy. |
| CS-011 | Token chưa tới nbf ngoài leeway | nbf-now > L | Reject. |
| CS-012 | iat trong tương lai | iat > now+L | Reject nếu policy ứng dụng bật future-iat validation. |
| CS-013 | Token quá cũ | now-iat vượt max token age | Reject nếu policy max-age được cấu hình. |
| CS-014 | Signature sai nhưng thời gian hợp lệ | Sửa payload không ký lại | Reject do chữ ký, không accept nhờ leeway. |
| CS-015 | Issuer sai nhưng thời gian hợp lệ | iss không nằm trong trust config | Reject. |
| CS-016 | Audience sai nhưng thời gian hợp lệ | aud=payments-api gửi tới Orders | Reject. |
| CS-017 | Nhiều resource server | Node A/B có offset khác nhau | Kết quả phù hợp policy và giới hạn offset đã định. |
| CS-018 | Cache introspection | Kết quả active được cache trong TTL | Đo độ trễ và xác minh hành vi theo policy. |
| CS-019 | Opaque token expiry | Introspection trả inactive sau expiry | Resource server từ chối; không tự áp JWT leeway nếu STS không quy định. |
| CS-020 | Đồng hồ nhảy lùi/tiến | Time source bị điều chỉnh trong test | Hành vi có kiểm soát; timeout/duration không bị đo bằng wall clock sai cách. |
| CS-021 | Clock lệch qua ngày/tháng/năm | Thời gian gần ranh giới lịch | Xác minh dùng Instant/epoch, không lỗi múi giờ/DST. |
| CS-022 | Millisecond boundary | Claim có NumericDate thập phân | Rounding/truncation theo thư viện được kiểm chứng. |
| CS-023 | Refresh token hết hạn | Clock của token endpoint khác client | Refresh bị từ chối đúng policy; không áp leeway quá rộng. |
| CS-024 | Leeway không đồng nhất | Gateway 30s, downstream 0s | Test phát hiện chênh lệch hành vi và yêu cầu thống nhất policy. |

## 9. Kiểm thử hệ thống và NTP

Unit test với Clock.fixed giúp xác minh logic, nhưng không chứng minh máy chủ production được đồng bộ thời gian. Cần thêm kiểm thử hệ thống và quan sát vận hành:

1. Kiểm tra trạng thái đồng bộ NTP/chrony hoặc dịch vụ time synchronization của hạ tầng.
2. Theo dõi offset giữa các node và cảnh báo khi vượt ngưỡng vận hành.
3. Kiểm tra node mới khởi động, VM resume, container host thay đổi hoặc node bị mất kết nối NTP.
4. Kiểm tra nhiều availability zone/region có offset khác nhau.
5. Kiểm tra gateway và downstream dùng cùng policy leeway.
6. Xác định hành vi khi time source không đáng tin hoặc hệ thống phát hiện clock jump.

Không cần làm lệch đồng hồ thật của máy production để kiểm thử. Dùng test harness, virtual clock, container/VM cô lập hoặc môi trường staging được kiểm soát. Nếu kiểm tra NTP ở cấp hệ điều hành, phải dùng môi trường riêng và quy trình vận hành an toàn; không sửa giờ máy chia sẻ đang phục vụ người dùng.

### 9.1. Wall-clock jump và duration

Nếu wall clock bị điều chỉnh lùi, phép đo thời lượng bằng Instant.now() có thể âm hoặc lớn bất thường. Timeout HTTP, circuit breaker, retry delay và latency nên dựa trên monotonic time của runtime/thư viện. Kiểm tra JWT vẫn cần wall clock vì claims là mốc thời gian tuyệt đối. Hai trách nhiệm này phải được test riêng.

## 10. Opaque token và introspection khi clock skew

Với opaque access token, resource server thường không tự đọc exp từ chuỗi token. Nó gọi introspection endpoint và nhận kết quả như active, exp, scope, aud hoặc các thuộc tính theo profile. Khi đó cần phân biệt:

- **Clock của authorization server:** quyết định token còn active hay đã hết hạn.
- **Clock của resource server:** có thể dùng để diễn giải exp trả về, nếu client tự kiểm tra thời gian.
- **Cache TTL:** kết quả introspection cũ có thể tiếp tục được sử dụng sau khi token hết hạn hoặc bị thu hồi.
- **Clock của cache/node:** ảnh hưởng thời điểm cache hết hạn nếu implementation dựa vào wall clock.

Nếu authorization server đã trả active=false, resource server không nên tự chuyển kết quả thành active chỉ vì local leeway. Nếu contract cho phép local check exp, cần xác định rõ nguồn thời gian và semantics. Không tự áp dụng JWT leeway vào opaque introspection response mà chưa có thiết kế.

Test nên tạo opaque token trong issuer test, điều khiển clock issuer và resource server, quan sát introspection response, cache hit/miss và thời điểm API từ chối. Đo cả độ trễ khi cache được invalidated sau expiry.

## 11. Lỗi thường gặp khi test clock skew

| Lỗi | Vì sao sai | Cách sửa |
| --- | --- | --- |
| Chỉ test token hết hạn rõ ràng nhiều giờ | Không kiểm tra ranh giới và leeway | Test trước, tại và sau exp/nbf theo từng giây/millisecond. |
| Dùng Thread.sleep() | Test chậm và phụ thuộc tải máy | Tiêm Clock hoặc time provider có thể điều khiển. |
| Chỉ test issuer nhanh, bỏ qua issuer chậm | Bỏ sót lỗi token mới có nbf trong tương lai tương đối | Kiểm tra cả delta dương và âm. |
| Tăng leeway để làm hết 401 | Che lỗi đồng bộ giờ và kéo dài khả năng replay | Theo dõi NTP, đặt leeway nhỏ dựa trên đo đạc. |
| Cho mọi validator leeway khác nhau | Gateway và downstream bất đồng | Quản lý policy tập trung, test cấu hình từng node. |
| Cho rằng iat bắt buộc phải validate như exp | RFC 7519 không bắt buộc mọi validator từ chối iat tương lai | Xác định policy ứng dụng và test rõ. |
| Chỉ test time claim, bỏ chữ ký/audience | Có thể accept token giả hoặc token dành cho API khác | Kết hợp negative test độc lập cho mọi validator. |
| Dùng local timezone | Lỗi DST/offset và so sánh không nhất quán | Dùng UTC/Instant/NumericDate. |
| Nhầm clock skew với cache delay | Không biết lỗi đến từ validator hay introspection cache | Ghi nhận time source, cache state và response introspection riêng. |
| Sửa system clock trong test suite chia sẻ | Ảnh hưởng tiến trình khác, DB, log và CI | Dùng virtual clock hoặc môi trường cô lập. |

## 12. Logging, metrics và chẩn đoán

Khi token bị từ chối do thời gian, cần có đủ thông tin chẩn đoán mà không làm lộ token. Có thể ghi:

- Logical issuer ID và resource server ID.
- Loại claim thời gian gây lỗi: exp, nbf, iat hoặc max-age policy.
- Policy/leeway version hoặc giá trị cấu hình đã áp dụng.
- Khoảng lệch đã chuẩn hóa, nếu có thể đo an toàn.
- Node ID, request/trace ID và timestamp UTC.
- Kết quả validator và reason code, không chứa raw token.

Không ghi Authorization header, refresh token, JWT đầy đủ hoặc toàn bộ claims có dữ liệu cá nhân. Metrics có thể theo dõi tỷ lệ expired, not_yet_valid, future_iat, số request bị từ chối theo node và offset NTP. Tránh đưa subject/email hoặc token vào metric label vì tạo dữ liệu nhạy cảm và cardinality lớn.

Một dashboard hữu ích có thể so sánh:

| Metric | Ý nghĩa |
| --- | --- |
| clock_offset_seconds | Độ lệch thời gian của node so với time source. |
| jwt_validation_failure_total{reason="expired"} | Số lần từ chối do exp. |
| jwt_validation_failure_total{reason="not_yet_valid"} | Số lần từ chối do nbf. |
| jwt_future_iat_total | Số lần iat nằm ngoài policy cho phép. |
| introspection_cache_age_seconds | Tuổi của kết quả introspection đang dùng. |
| auth_validation_skew_seconds | Chênh lệch thời gian quan sát giữa issuer/resource server nếu hệ thống đo được. |

## 13. Checklist triển khai và kiểm thử

- [ ] Dùng UTC/Instant và NumericDate nhất quán; không so sánh chuỗi local time.
- [ ] Xác định policy cho exp, nbf, iat và max token age.
- [ ] Đặt leeway nhỏ, có căn cứ từ offset đo được và threat model.
- [ ] Xác minh chính xác semantics boundary của thư viện JWT đang dùng.
- [ ] Tiêm clock/time provider vào logic có thể kiểm thử; tránh sleep và thay system clock.
- [ ] Test issuer nhanh/chậm, resource server nhanh/chậm và nhiều node.
- [ ] Test trước, tại và sau ranh giới exp/nbf, cả milliseconds nếu hỗ trợ.
- [ ] Xác nhận clock skew không làm bỏ qua chữ ký, issuer, audience, scope hoặc token type.
- [ ] Kiểm tra opaque introspection, cache TTL và revocation propagation riêng.
- [ ] Theo dõi NTP offset và cảnh báo node vượt ngưỡng.
- [ ] Dùng monotonic time cho timeout/duration; wall clock cho JWT absolute timestamps.
- [ ] Scrub token/claims nhạy cảm khỏi log, trace và metrics.

## 14. Kết luận và tài liệu tham khảo

Clock skew là vấn đề giữa các time source, không phải lý do để nới lỏng xác thực token vô hạn. Leeway giúp bù sai lệch nhỏ nhưng làm rộng cửa sổ chấp nhận token; cần cấu hình có căn cứ, thống nhất và được kiểm thử ở ranh giới. Test hiệu quả dùng clock có thể điều khiển để xác minh exp, nbf, policy iat, offset dương/âm và hành vi giữa nhiều node. Đồng thời phải giữ nguyên các kiểm tra chữ ký, issuer, audience, scope và trạng thái thu hồi.

Tài liệu tiêu chuẩn liên quan:

- **RFC 7519 — JSON Web Token:** NumericDate và semantics của exp, nbf, iat.
- **RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens:** profile JWT dành cho access token.
- **RFC 6749 — OAuth 2.0 Authorization Framework:** vòng đời access token và refresh token.
- **RFC 7662 — OAuth 2.0 Token Introspection:** trạng thái opaque token qua introspection.
- **RFC 7009 — OAuth 2.0 Token Revocation:** thu hồi token và ảnh hưởng tới trạng thái token.
- **RFC 3339 — Date and Time on the Internet:** định dạng timestamp Internet khi trao đổi/hiển thị thời gian.
- **Spring Security Resource Server JWT documentation:** validator timestamp, issuer và audience theo phiên bản framework đang triển khai.
