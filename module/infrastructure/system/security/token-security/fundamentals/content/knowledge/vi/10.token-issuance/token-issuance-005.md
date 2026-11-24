# Thời điểm bắt đầu hiệu lực

Một access token có chữ ký đúng và chưa hết hạn **chưa chắc đã được phép dùng ngay**. Authorization server có thể phát hành token lúc 10:00, nhưng chỉ cho phép dùng từ 10:00:30. Trong JWT, claim **`nbf` (*not before*)** biểu diễn ngưỡng thời gian này. Nếu API bỏ qua `nbf`, quyền truy cập có thể được sử dụng **trước thời điểm được cấp phép**. Nếu API kiểm tra sai đơn vị hoặc đồng hồ giữa các hệ thống lệch nhau, token hợp lệ lại có thể bị từ chối.

Trong chương **Token issuance**, bài học này giải thích cách xác định **thời điểm bắt đầu hiệu lực** trong vòng đời JWT và opaque token, phân biệt `nbf` với `iat`, `exp`, `auth_time` và `expires_in`, rồi áp dụng vào OAuth 2.0/OpenID Connect (OIDC). Đồng thời, bài đề cập việc xác minh issuer, audience, scope, thu hồi token và phòng chống token bị đánh cắp hoặc phát lại.

> **Nguyên tắc:** Thời gian trong token chỉ trở thành căn cứ bảo mật khi được lấy từ **token/metadata đã xác minh**. `nbf` không thay thế kiểm tra chữ ký, audience, quyền truy cập hoặc trạng thái thu hồi.

## 1. Thời điểm bắt đầu hiệu lực là gì?

Một credential có thể trải qua các thời điểm khác nhau:

1. **Người dùng xác thực:** hệ thống định danh xác nhận user và có thể lập phiên đăng nhập.
2. **Authorization server cấp quyền:** hệ thống xác định principal, client, resource, scope và thời hạn cho phép.
3. **Token được phát hành:** token được tạo/ký hoặc ghi vào token store, có thời điểm `iat` nếu dùng JWT.
4. **Token bắt đầu có thể được chấp nhận:** token đạt thời điểm `nbf` hoặc thời điểm active theo trạng thái của hệ thống.
5. **Token hết hạn hoặc bị thu hồi:** resource server không được tiếp tục chấp nhận token theo chính sách.

Các mốc trên **không bắt buộc trùng nhau**. Thông thường, access token có hiệu lực gần như ngay sau khi phát hành. Một số nghiệp vụ lại cần **phát trước, dùng sau**, chẳng hạn quyền dành cho một đợt vận hành chỉ bắt đầu tại thời điểm đã phê duyệt.

Ví dụ:

~~~text
10:00:00  Người dùng đã được xác thực và AS phát access token
           iat = 10:00:00

10:00:30  Token bắt đầu có hiệu lực
           nbf = 10:00:30

10:15:30  Token hết hạn
           exp = 10:15:30

Trước 10:00:30:  từ chối request dù token có chữ ký hợp lệ.
Từ 10:00:30:    có thể chấp nhận nếu các điều kiện khác đều đạt.
Từ 10:15:30:    từ chối token đã hết hạn.
~~~

Thời điểm bắt đầu hiệu lực **không phải một lời hứa chắc chắn rằng request sẽ thành công**. Tại hoặc sau `nbf`, API vẫn cần xác minh token, scope, tenant, ownership và các policy hiện hành. Token đã bị thu hồi hoặc được cấp cho audience khác phải bị từ chối dù đã đến giờ kích hoạt.

## 2. Phân biệt `nbf`, `iat`, `exp` và `auth_time`

| Trường | Tên đầy đủ | Ý nghĩa | Điều **không** được suy ra |
| --- | --- | --- | --- |
| **`nbf`** | Not Before | JWT **không được chấp nhận trước** thời điểm này, trừ độ lệch đồng hồ được chính sách cho phép | Không chứng minh user vừa đăng nhập hoặc có đủ quyền |
| **`iat`** | Issued At | Thời điểm JWT được phát hành | Không mặc nhiên là lúc token **bắt đầu** hợp lệ hoặc lúc user vừa xác thực |
| **`exp`** | Expiration Time | JWT **không được chấp nhận từ** thời điểm này trở đi, trừ leeway được cho phép | Không chứng minh token chưa bị thu hồi hoặc có scope phù hợp |
| **`auth_time`** | Authentication Time (OIDC) | Lúc user đã được xác thực chủ động, khi claim được cung cấp theo OIDC | Không phải thời điểm phát hành/hiệu lực của access token |
| **`expires_in`** | OAuth token response field | Thời lượng sống của access token tính bằng giây theo phản hồi token endpoint | Không phải claim JWT và không tự mô tả thời điểm `nbf` |
| **`active`** | Token introspection response field | Token được introspection service đánh giá đang hoạt động tại thời điểm trả kết quả | Không miễn trừ kiểm tra audience, scope và policy của API |

Theo **RFC 7519**, `nbf`, `iat`, `exp` là các *Registered Claim Names*. **`nbf` là tùy chọn theo JWT tổng quát**; yêu cầu có hay không phụ thuộc profile token và hợp đồng giữa issuer và consumer. Việc claim không xuất hiện **không có nghĩa tự động phải từ chối mọi JWT** hoặc được phép bỏ các kiểm tra bắt buộc khác.

### 2.1. `iat` mới không có nghĩa user vừa xác thực

Giả sử user đăng nhập lúc 08:00, sau đó client dùng refresh token xin access token mới lúc 10:00. Token mới có thể ghi `iat=10:00`, nhưng sự kiện xác thực người dùng vẫn xảy ra lúc 08:00 (`auth_time=08:00`, nếu thông tin này được đưa vào token/profile).

Đối với **step-up authentication** yêu cầu xác thực trong vòng 5 phút, không được lấy `iat` hoặc `nbf` để thay `auth_time`. Tương tự, có một access token mới **không đồng nghĩa** user vừa thực hiện MFA.

### 2.2. `nbf` khác ngày bắt đầu một quyền nghiệp vụ

Một hợp đồng có thể cho phép truy cập dữ liệu từ 00:00 ngày mai. **Nếu ứng dụng chỉ dựa vào `nbf` của JWT**, nó còn phải xử lý trường hợp hợp đồng bị hủy sau khi token đã được phát. JWT được xác minh offline có thể tiếp tục có hiệu lực đến `exp` nếu không có thu hồi hoặc kiểm tra policy hiện hành.

Vì vậy, `nbf` là **điều kiện cần về thời gian cho token**, không tự bảo đảm mọi quy tắc thời gian của nghiệp vụ. Phân quyền theo hợp đồng, membership, tenant hoặc trạng thái giao dịch vẫn cần nguồn tin cậy và cách thu hồi phù hợp.

## 3. NumericDate: thời gian trong JWT được tính thế nào?

Các claim `nbf`, `iat`, `exp` sử dụng kiểu **NumericDate** theo RFC 7519: số giây kể từ **1970-01-01T00:00:00Z (UTC)** theo cách đếm tương thích thời gian POSIX/Unix, không tính giây nhuận như đơn vị giây bổ sung. Giá trị có thể là số không nguyên; trong nhiều hệ thống, mốc **giây nguyên** được dùng để dễ tương thích.

Ví dụ payload JWT:

~~~json
{
  "iss": "https://auth.example.com",
  "sub": "user-42",
  "aud": "https://api.example.com/orders",
  "scope": "orders.read",
  "iat": 1800000000,
  "nbf": 1800000030,
  "exp": 1800000930
}
~~~

Đây là **payload minh họa**, không phải token đã ký. Trong ví dụ:

- Token phát hành ở giây `1800000000`.
- Token **bắt đầu** có hiệu lực sau 30 giây, tại `1800000030`.
- Token hết hạn 900 giây sau khi bắt đầu, tại `1800000930`.

Một số client hoặc API nhầm **giây** với **mili-giây**. Java `System.currentTimeMillis()` trả mili-giây, còn JWT NumericDate thường được thư viện Java biểu diễn qua `Instant` hoặc epoch **seconds**. So sánh trực tiếp hai số khác đơn vị có thể khiến token tưởng như hết hạn ngay hoặc chưa bao giờ có hiệu lực.

~~~java
import java.time.Instant;

long issuedAtSeconds = 1_800_000_000L;
Instant issuedAt = Instant.ofEpochSecond(issuedAtSeconds); // ĐÚNG

// Sai khi diễn giải giây JWT như mili-giây:
Instant incorrect = Instant.ofEpochMilli(issuedAtSeconds);
~~~

Một số lưu ý:

- **Không dùng timezone của người dùng** để điều chỉnh NumericDate. Epoch seconds có cùng ý nghĩa toàn cầu; timezone chỉ ảnh hưởng cách **hiển thị**.
- **Không dùng đồng hồ monotonic** như `System.nanoTime()` để làm epoch timestamp. Clock monotonic phù hợp đo khoảng thời gian, không đại diện thời gian UTC.
- **Không làm tròn sai** khi token dùng NumericDate có phần thập phân; validator nên sử dụng parser thư viện và chính sách thời gian nhất quán.
- Kiểm tra số quá lớn, quá nhỏ, giá trị sai kiểu hoặc không biểu diễn được; không cho phép dữ liệu thời gian bất thường gây overflow hoặc bỏ qua validation.

## 4. Quy tắc chấp nhận theo thời gian

Nếu **không tính độ lệch đồng hồ**, JWT có `nbf` và `exp` chỉ đạt điều kiện thời gian khi:

\[
\texttt{now} \geq \texttt{nbf}
\quad \land \quad
\texttt{now} < \texttt{exp}
\]

Điều này có nghĩa:

- Tại **`now = nbf`**, token có thể được chấp nhận, nếu các kiểm tra khác đều đạt.
- Tại **`now = exp`**, token đã hết hạn và phải bị từ chối.
- Nếu `exp <= nbf`, khoảng hiệu lực không dương; trong một profile yêu cầu khoảng hiệu lực, token nên bị từ chối khi phát hành hoặc validation.

| `now` (giây) | So với `nbf=1800000030` và `exp=1800000930` | Kết quả thời gian, chưa có leeway |
| ---: | --- | --- |
| 1800000000 | 30 giây trước `nbf` | Chưa hiệu lực |
| 1800000029 | 1 giây trước `nbf` | Chưa hiệu lực |
| 1800000030 | Chính bằng `nbf` | Hợp lệ về mốc bắt đầu |
| 1800000600 | Nằm trong khoảng | Hợp lệ về thời gian |
| 1800000929 | 1 giây trước `exp` | Hợp lệ về thời gian |
| 1800000930 | Chính bằng `exp` | Đã hết hạn |
| 1800001000 | Sau `exp` | Đã hết hạn |

~~~mermaid
flowchart LR
    A["Phát hành JWT<br/>iat"] --> B["Chưa được dùng<br/>now < nbf"]
    B --> C["Bắt đầu hiệu lực<br/>now >= nbf"]
    C --> D["Trong thời hạn<br/>now < exp"]
    D --> E["Hết hạn<br/>now >= exp"]
~~~

**`iat` không phải điều kiện `now >= iat` được áp đặt giống nhau bởi mọi thư viện JWT.** Nó mô tả thời điểm phát hành; tùy profile, resource server có thể yêu cầu `iat` hiện diện, hợp lý và không nằm quá xa trong tương lai. Trong một hợp đồng cụ thể, nếu token có `iat > now` vượt sai số đồng hồ cho phép, đó là dấu hiệu thời gian phát hành bất thường và nên bị từ chối.

## 5. Clock skew và leeway: vì sao token vẫn có thể bị từ chối sát ngưỡng?

Authorization server và resource server có thể có đồng hồ lệch nhau vài giây. Token vừa được phát lúc 10:00:00 tại AS nhưng đồng hồ API đang ở 09:59:58 có thể bị coi là **chưa đến `nbf`**, dù hai bên đều hoạt động đúng về mặt nghiệp vụ.

RFC 7519 cho phép validator dùng **leeway nhỏ** để bù sai số đồng hồ khi đánh giá `nbf` và `exp`. Với leeway \(\delta\) giây, kiểm tra thường có dạng tương đương:

\[
\texttt{now} + \delta \geq \texttt{nbf}
\quad \land \quad
\texttt{now} - \delta < \texttt{exp}
\]

Leeway thường được chọn cỡ **vài giây hoặc vài chục giây** tùy độ chính xác đồng hồ và yêu cầu bảo mật; tiêu chuẩn không áp một giá trị cứng cho mọi ứng dụng. Với `nbf=10:00:30` và leeway 30 giây, API **có thể chấp nhận token ngay từ 10:00:00**. Điều này rất quan trọng khi nghiệp vụ đòi **không được dùng trước một thời điểm tuyệt đối**.

| Thiết lập | Lợi ích | Chi phí/rủi ro |
| --- | --- | --- |
| `leeway = 0` | Ranh giới chính xác theo đồng hồ của API | Dễ gặp từ chối giả nếu hai đồng hồ lệch |
| Leeway nhỏ, được kiểm soát | Giảm lỗi gần `nbf`/`exp` | Có thể chấp nhận sớm hơn `nbf`, muộn hơn `exp` một chút |
| Leeway quá lớn | Có vẻ ít lỗi thời gian | Mở rộng khoảng dùng token và cửa sổ replay; che giấu lỗi đồng bộ đồng hồ |

### 5.1. Cách xử lý đồng hồ phân tán

1. Dùng dịch vụ đồng bộ thời gian đáng tin cậy cho AS, API gateway, resource server và cơ sở dữ liệu khi có liên quan.
2. Đo chênh lệch giữa các nút, cảnh báo khi vượt ngưỡng; không tăng leeway vô hạn để che lỗi.
3. Cấu hình leeway **nhất quán** trong các lớp xác minh token, hiểu chính xác thư viện áp dụng cho `nbf`, `exp` và có kiểm tra `iat` hay không.
4. Nếu nghiệp vụ có giờ kích hoạt nghiêm ngặt, kiểm tra **thời điểm nghiệp vụ tại nguồn tin cậy**, có thể kết hợp trạng thái activation trong server-side store; không xem `nbf` với leeway như ranh giới tuyệt đối.
5. Log **độ lệch thời gian và kết quả kiểm tra**, tránh log nguyên token hoặc thông tin đăng nhập.

**Độ lệch đồng hồ là một ngoại lệ được cho phép có giới hạn**, không phải quyền bỏ qua `nbf` và `exp`.

## 6. Khi nào nên phát hành token có `nbf` trong tương lai?

Đa số luồng đăng nhập và API cần access token **có thể dùng ngay**. Đặt `nbf` tương lai không cần thiết sẽ khiến client nhận token nhưng lập tức bị `401`, dẫn đến retry hoặc trải nghiệm khó hiểu.

Có thể cân nhắc thời điểm kích hoạt trong tương lai khi:

- Một quyền truy cập **đã được phê duyệt trước** và chỉ bắt đầu trong khung giờ cụ thể, ví dụ truy cập dữ liệu theo lịch kiểm toán.
- Một hệ thống xử lý công việc theo lịch sử dụng credential riêng cho **cửa sổ vận hành** đã xác định.
- Token dùng cho một **giai đoạn rollout** có thời điểm bắt đầu thống nhất giữa bên phát hành và bên tiêu thụ.

Ngay cả trong các tình huống đó, cần trả lời:

| Câu hỏi thiết kế | Vì sao quan trọng? |
| --- | --- |
| Ai quyết định `notBefore`? | Client tự khai giờ kích hoạt không được trở thành nguồn quyền |
| Có thể hủy quyền trước giờ bắt đầu không? | JWT ký sẵn có thể vẫn dùng được khi đến giờ nếu không có revocation |
| Token sẽ hết hạn lúc nào? | `exp` phải được tính theo TTL được định nghĩa rõ |
| Client biết token chưa active bằng cách nào? | Tránh gửi lại liên tục gây tải và làm lộ thông tin |
| API nào chấp nhận token? | `aud` và scope phải được giới hạn, kể cả sau `nbf` |
| Giới hạn clock skew bao nhiêu? | Leeway có thể cho phép dùng token **trước giờ dự kiến** |
| Có cần kiểm tra policy lúc kích hoạt không? | Quyền/tenant/membership có thể bị thay đổi sau khi token được phát |

**Không dùng token phát trước như bằng chứng không thể hủy ngang.** Nếu cần đảm bảo quyền chỉ hoạt động sau một quyết định nghiệp vụ tại thời điểm đó, mô hình **opaque token với lookup**, trạng thái server-side hoặc kết hợp kiểm tra policy hiện hành thường dễ thu hồi và kiểm soát hơn.

## 7. Phát hành JWT với mốc bắt đầu có chủ đích

Một authorization server cần xây dựng mốc thời gian từ **chính sách của server**, dùng **cùng nguồn thời gian** để tránh mâu thuẫn:

~~~mermaid
sequenceDiagram
    autonumber
    participant C as OAuth client
    participant AS as Authorization server
    participant P as Grant / policy store
    participant API as Resource server
    C->>AS: Hoàn thành grant / token request
    AS->>AS: Xác thực user/client theo luồng
    AS->>P: Kiểm tra grant, scope, audience, quyền và thời điểm
    P-->>AS: Policy được phép, thời điểm kích hoạt
    AS->>AS: Đặt iat, nbf, exp; ký JWT bằng khóa được quản lý
    AS-->>C: Access token + expires_in (theo hợp đồng)
    C->>API: Gửi access token trước nbf
    API-->>C: 401, chưa thể chấp nhận token
    C->>API: Gửi lại sau nbf theo luồng hợp lệ
    API->>API: Validate chữ ký, iss, aud, thời gian, scope, policy
    API-->>C: Phản hồi theo quyền thực tế
~~~

**`nbf` không tạo ra quyền mới.** Trước khi phát token, AS vẫn phải kiểm tra principal, consent/grant, client registration, scope và audience. Nếu user bị khóa, tenant bị thu hồi quyền hoặc token bị đưa vào denylist, API phải từ chối dù đồng hồ đã vượt `nbf`.

### 7.1. Cách tính TTL: từ `iat` hay từ `nbf`?

Có hai hợp đồng minh họa:

**Phương án A — TTL từ lúc phát hành:** `exp = iat + 900`. Nếu `nbf = iat + 30`, khoảng sử dụng thực tế chỉ còn **870 giây**.

**Phương án B — TTL từ lúc bắt đầu:** `exp = nbf + 900`. Nếu `nbf = iat + 30`, token dùng được trong **900 giây** sau khi có hiệu lực.

Không có quy tắc cho mọi tổ chức rằng phải chọn một trong hai. Điều cần thiết là **thống nhất với client và API**, bảo đảm `exp > nbf`, token không sống lâu bất thường, và `expires_in` trong token response không gây hiểu nhầm.

Theo OAuth 2.0, `expires_in` trong phản hồi token endpoint là **thời lượng sống tính bằng giây từ thời điểm phản hồi được tạo**. Nếu AS cấp token phát trước có `nbf` trong tương lai, nó phải phản ánh chính xác đời sống token trong `expires_in` theo định nghĩa giao thức; **không tự đặt `expires_in = exp - nbf`** khi response được tạo trước `nbf`. Client phải phân biệt thời gian sống còn lại với khoảng thời gian token được phép sử dụng.

### 7.2. Ví dụ phát hành JWT bằng Java và Spring Security

Đoạn mã dưới đây minh họa **xây claims và ký JWT tại authorization server**. Nó không xử lý đầy đủ toàn bộ quy trình OAuth 2.0: authorization grant, client authentication, user authentication, consent và phân quyền phải được kiểm tra **trước** khi gọi hàm phát hành.

~~~java
import java.time.Clock;
import java.time.Instant;
import java.time.temporal.ChronoUnit;
import java.util.List;
import org.springframework.security.oauth2.jose.jws.SignatureAlgorithm;
import org.springframework.security.oauth2.jwt.JwsHeader;
import org.springframework.security.oauth2.jwt.JwtClaimsSet;
import org.springframework.security.oauth2.jwt.JwtEncoder;
import org.springframework.security.oauth2.jwt.JwtEncoderParameters;

public final class ScheduledAccessTokenIssuer {
    private static final String ISSUER = "https://auth.example.com";
    private static final String ORDERS_API =
        "https://api.example.com/orders";

    private final JwtEncoder encoder;
    private final Clock clock;

    public ScheduledAccessTokenIssuer(JwtEncoder encoder, Clock clock) {
        this.encoder = encoder;
        this.clock = clock;
    }

    public String issueForApprovedGrant(String subject) {
        // Chỉ gọi sau khi AS đã kiểm tra grant, audience, scope, policy.
        Instant issuedAt = clock.instant().truncatedTo(ChronoUnit.SECONDS);
        Instant validFrom = issuedAt.plusSeconds(30);
        Instant expiresAt = validFrom.plusSeconds(15 * 60);

        JwtClaimsSet claims = JwtClaimsSet.builder()
            .issuer(ISSUER)
            .subject(subject)
            .audience(List.of(ORDERS_API))
            .issuedAt(issuedAt)
            .notBefore(validFrom)
            .expiresAt(expiresAt)
            .claim("scope", "orders.read")
            .build();

        JwsHeader header = JwsHeader.with(SignatureAlgorithm.RS256)
            .type("at+jwt")
            .build();

        return encoder.encode(
            JwtEncoderParameters.from(header, claims)
        ).getTokenValue();
    }
}
~~~

Trong ví dụ, `issuedAt` và `validFrom` được tính từ **`Clock` do server kiểm soát**; `exp` cách `nbf` 15 phút. Dùng `Clock` được inject giúp test các mốc thời gian ổn định. `JwtEncoder` phải được cấu hình khóa ký an toàn và cơ chế quản lý khóa/rotation phù hợp. Tên claim `scope` và header `typ=at+jwt` cần thống nhất với profile access token mà resource server chấp nhận.

**Không lấy `validFrom` trực tiếp từ request client rồi ký** nếu client chưa được cấp quyền yêu cầu lịch kích hoạt đó. Hạn tối đa, khoảng trì hoãn và audience phải do policy của AS kiểm soát.

## 8. Resource server xác minh thời điểm bắt đầu hiệu lực thế nào?

Một JWT có thể chứa `nbf` nhưng **API không được tin giá trị đó trước khi xác minh token**. Với JWT access token, quy trình đáng tin cậy bao gồm:

1. Lấy token từ kênh được hỗ trợ, thường `Authorization: Bearer ...`, qua HTTPS.
2. Xác minh chữ ký bằng khóa/thuật toán được phép của **issuer đã cấu hình**; không dùng JWKS URL tùy ý từ token chưa đáng tin.
3. Kiểm tra `iss`, `aud`, token type/profile và các claim bắt buộc.
4. Kiểm tra `nbf`, `exp`, `iat` theo chính sách và leeway có giới hạn.
5. Kiểm tra scope, principal type, tenant, trạng thái grant/thu hồi nếu policy yêu cầu.
6. Kiểm tra quyền trên tài nguyên thực tế trước khi thực hiện tác vụ.

Đối với JWT theo **RFC 9068**, resource server còn phải tuân các yêu cầu validation dành cho access token trong profile đó. **Không dùng ID token OIDC** có `nbf` hợp lệ làm access token cho API: ID token thường có audience là OIDC client, không phải resource server.

### 8.1. Ví dụ cấu hình timestamp validation trong Spring Security

Đoạn cấu hình sau minh họa resource server dùng **Spring Security** và tập validator tường minh. `JwtTimestampValidator` xử lý `nbf`/`exp` có clock skew; các validator còn lại kiểm tra issuer, audience và cấu trúc thời gian theo hợp đồng của API.

~~~java
import java.time.Duration;
import java.time.Instant;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.JwtIssuerValidator;
import org.springframework.security.oauth2.jwt.JwtTimestampValidator;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;

@Configuration
public class OrdersJwtValidationConfig {
    private static final String ISSUER = "https://auth.example.com";
    private static final String AUDIENCE =
        "https://api.example.com/orders";

    @Bean
    JwtDecoder jwtDecoder() {
        NimbusJwtDecoder decoder = NimbusJwtDecoder
            .withJwkSetUri("https://auth.example.com/.well-known/jwks.json")
            .build();

        JwtTimestampValidator timestamps =
            new JwtTimestampValidator(Duration.ofSeconds(30));

        OAuth2TokenValidator<Jwt> audience = jwt -> {
            if (jwt.getAudience() != null &&
                    jwt.getAudience().contains(AUDIENCE)) {
                return OAuth2TokenValidatorResult.success();
            }
            return OAuth2TokenValidatorResult.failure(
                new OAuth2Error("invalid_token", "Unexpected audience", null)
            );
        };

        // Ví dụ hợp đồng riêng: access token phải có iat và exp.
        // nbf tùy chọn theo JWT tổng quát nhưng khi có phải < exp.
        OAuth2TokenValidator<Jwt> requiredTimeClaims = jwt -> {
            Instant iat = jwt.getIssuedAt();
            Instant exp = jwt.getExpiresAt();
            Instant nbf = jwt.getNotBefore();

            boolean malformed = iat == null || exp == null
                || !exp.isAfter(iat)
                || (nbf != null && !exp.isAfter(nbf));
            if (malformed) {
                return OAuth2TokenValidatorResult.failure(
                    new OAuth2Error("invalid_token",
                        "Missing or inconsistent time claims", null)
                );
            }
            return OAuth2TokenValidatorResult.success();
        };

        decoder.setJwtValidator(
            new DelegatingOAuth2TokenValidator<>(
                new JwtIssuerValidator(ISSUER),
                timestamps,
                audience,
                requiredTimeClaims
            )
        );
        return decoder;
    }
}
~~~

Đây là **ví dụ các kiểm tra thời gian chính**, chưa phải toàn bộ cấu hình resource server production. Cần bảo đảm khóa xác minh, thuật toán, header `typ`, hạn tối đa, scope và token profile được ràng buộc đúng. Nếu hợp đồng yêu cầu `nbf` **bắt buộc**, thêm điều kiện từ chối khi thiếu claim. Nếu profile yêu cầu `iat` **không được nằm trong tương lai vượt giới hạn**, thêm validator riêng với `Clock` và sai số cho phép.

**Cẩn thận với leeway 30 giây**: nó có thể làm token được chấp nhận **trước** `nbf` 30 giây, hoặc **sau** `exp` một khoảng tương tự. Nếu thời điểm kích hoạt có ý nghĩa pháp lý/nghiệp vụ tuyệt đối, không chỉ dựa vào validator có leeway như một khóa thời gian chính xác.

### 8.2. Vì sao `iat` cần validator riêng theo chính sách?

`JwtTimestampValidator` thường tập trung vào `nbf` và `exp`. Việc **token có `iat` rất xa trong tương lai** hoặc khoảng cách `exp-iat` quá dài cần được kiểm soát theo profile và yêu cầu riêng. Ví dụ một policy có thể từ chối:

- `iat > now + maxClockSkew` (phát hành trong tương lai vượt sai số đồng hồ).
- `exp - iat` lớn hơn **TTL tối đa** mà hệ thống cho phép đối với loại access token đó.
- `nbf` hoặc `exp` sai kiểu hoặc nằm ngoài khoảng giá trị thời gian hợp lệ.

Nếu cần, cũng có thể kiểm tra `nbf - iat` không vượt **khoảng phát trước tối đa**. Đây là **quy tắc sản phẩm**, không phải một định đề áp dụng cho mọi JWT.

## 9. Opaque token và trạng thái kích hoạt phía server

Với **opaque access token**, client chỉ mang một chuỗi không tự giải mã. Authorization server hoặc token store giữ thông tin bắt đầu hiệu lực, thời hạn, scope và trạng thái thu hồi:

~~~text
Token store (minh họa, không ghi token thô vào log)
  token_hash    = <hash-or-reference>
  subject       = user-42
  audience      = orders-api
  scopes        = orders.read
  valid_from    = 10:00:30 UTC
  expires_at    = 10:15:30 UTC
  revoked       = false
~~~

Resource server có thể dùng **OAuth 2.0 Token Introspection (RFC 7662)** để xác định token còn hoạt động. Một phản hồi minh họa khi token đã được chấp nhận theo chính sách:

~~~json
{
  "active": true,
  "iss": "https://auth.example.com",
  "sub": "user-42",
  "aud": "https://api.example.com/orders",
  "scope": "orders.read",
  "iat": 1800000000,
  "nbf": 1800000030,
  "exp": 1800000930
}
~~~

Trong introspection, `active` là kết luận của authorization server về trạng thái token. **Trước thời điểm được phép sử dụng**, dịch vụ nên trả `active=false` theo hợp đồng, hoặc cung cấp `nbf` để resource server thực thi chính sách thời gian tương ứng khi token đã đủ điều kiện và được trả về. Cách cung cấp metadata cụ thể phụ thuộc AS.

**Không tự coi `active=true` là quyền đọc mọi dữ liệu**: API vẫn cần kiểm tra `aud`, `scope`, principal, tenant và quyền trên resource. Nếu API cache kết quả introspection quá lâu, token bị thu hồi hoặc chưa active có thể gây sai lệch trạng thái giữa cache và AS. Thiết kế cache phải phù hợp yêu cầu thu hồi và activation.

### 9.1. Khi nào opaque token hữu ích hơn?

Nếu nghiệp vụ yêu cầu **kích hoạt/thu hồi tức thì theo dữ liệu hiện hành**, opaque token với lookup tập trung có thể thuận tiện hơn JWT được kiểm tra offline. Tuy nhiên:

- Mỗi lần lookup/introspection cần độ sẵn sàng, độ trễ và kiểm soát tải phù hợp.
- Cache có thể kéo dài hiệu lực của kết quả cũ; phải quản lý invalidation và TTL.
- Dịch vụ introspection phải xác thực resource server theo cấu hình và chỉ trả thông tin được phép.
- Với JWT đã phát trước, một denylist, token version hoặc kiểm tra grant hiện hành có thể cung cấp quyền kiểm soát tương tự, kèm chi phí tra cứu.

Lựa chọn JWT hay opaque phải dựa trên mô hình tin cậy, tần suất thu hồi, mức chấp nhận độ trễ và yêu cầu API, không chỉ vì sự hiện diện của `nbf`.

## 10. Tác động tới OAuth 2.0 và OIDC

### 10.1. Authorization Code + PKCE

Trong luồng authorization code, client đổi code lấy token tại token endpoint. **Authorization code**, **access token** và **ID token** là các đối tượng có vai trò/thời hạn khác nhau. Không lấy thời điểm code được phát, thời điểm trình duyệt được redirect hoặc thời điểm user click “Đăng nhập” làm `nbf` của access token nếu không có hợp đồng như vậy.

Nếu access token có `nbf` tương lai, client nên xử lý trạng thái chưa active rõ ràng. Nó không nên tự sửa JWT hay bỏ yêu cầu audience, cũng không nên làm mới token liên tục với hy vọng “đổi `iat` sẽ sửa `nbf`”. Authorization server quyết định giờ hiệu lực theo chính sách.

### 10.2. ID token và `auth_time`

ID token OIDC được gửi cho **OIDC client** để xác nhận sự kiện user authentication. ID token có `iat` và `exp` bắt buộc theo OIDC Core; nếu có `nbf` thì client phải diễn giải claim theo quy tắc JWT/profile. Khi client yêu cầu xác thực mới bằng `max_age`, nó kiểm tra `auth_time`; không thay bằng `nbf`.

**API không chấp nhận ID token chỉ vì `nbf` đã qua.** API yêu cầu **access token** đúng issuer, audience, loại và scope.

### 10.3. Refresh token và grant

Refresh token được dùng với authorization server để xin access token mới; refresh **không phải** một lần user authentication chủ động. Token mới có `iat` mới và `nbf` theo chính sách của AS, nhưng:

- Refresh token không được tự biến một grant chưa active thành quyền có hiệu lực trước giờ.
- Nếu quyền bị thu hồi hoặc membership không còn, AS phải áp policy khi cấp token mới.
- Refresh token/authorization grant có vòng đời độc lập với access token; không suy ra refresh token được dùng chỉ vì JWT access token đã quá `nbf`.

### 10.4. Scope, audience và tenant vẫn quyết định phạm vi quyền

`nbf` chỉ trả lời **“sớm nhất khi nào token có thể được chấp nhận?”**. Nó không trả lời:

- Token được cấp cho **API nào**? → kiểm tra `aud`.
- Token do **issuer nào** phát hành? → kiểm tra `iss` và khóa tin cậy.
- Token được cấp **loại thao tác nào**? → kiểm tra scope/permissions.
- Token đại diện **người dùng hay dịch vụ**? → kiểm tra principal type/profile.
- Token có quyền trên **đơn hàng/tenant nào**? → kiểm tra dữ liệu và resource policy.

Token có `nbf` đúng nhưng thiếu `orders.write` vẫn không được phép tạo đơn hàng. Token có `orders.read` của tenant Acme không được đọc tài nguyên Globex nếu quyền không cho phép.

## 11. Phân biệt các lỗi HTTP và cách client xử lý

| Trường hợp | Kết quả thông thường | Client xử lý thế nào? |
| --- | --- | --- |
| Không có token tại API bảo vệ | `401 Unauthorized` | Khởi động/khôi phục luồng nhận credential |
| JWT có `nbf` tương lai vượt leeway | `401`, có thể `invalid_token` | Không retry dồn dập; nhận token hợp lệ/đợi theo chính sách |
| JWT hết `exp` | `401`, thường `invalid_token` | Dùng refresh/authorization flow hợp lệ |
| JWT sai chữ ký, issuer, audience hoặc token type | `401` | Không coi là vấn đề đồng hồ; sửa nguồn token/cấu hình |
| Token hợp lệ về thời gian nhưng thiếu scope | `403 Forbidden`, có thể `insufficient_scope` | Xin quyền được phép, không sửa token ở client |
| Token có scope đủ nhưng user không sở hữu resource | `403` hoặc `404` theo policy | Từ chối; không retry để vượt phân quyền |
| Token đã bị thu hồi dù chưa đến `exp` | `401` hoặc từ chối theo thiết kế | Xử lý session/grant, không giả định JWT ký là đủ |

Ví dụ Bearer challenge khi token chưa có hiệu lực:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer error="invalid_token"
Cache-Control: no-store
Content-Type: application/json

{"error":"access_token_not_yet_valid"}
~~~

`access_token_not_yet_valid` trong JSON ở đây là **mã lỗi ứng dụng minh họa**, không phải một error code chuẩn thay `invalid_token` của RFC 6750. Không nên trả nguyên token, các claims nhạy cảm hoặc cấu hình đồng hồ nội bộ cho client chưa được tin cậy.

### 11.1. Không retry vô hạn khi token chưa active

Sai lầm thường gặp:

~~~text
API: 401 vì nbf chưa tới
Client: refresh token, gọi lại ngay
API: 401
Client: refresh, gọi lại ngay
... lặp vô hạn
~~~

Client nên xử lý lỗi có giới hạn theo hợp đồng: giữ trạng thái chờ đến thời điểm hợp lý nếu được phép, dùng backoff, dừng khi token hết hạn, và yêu cầu một grant/token mới khi chính sách thay đổi. **Giải mã JWT tại client để hiển thị thời gian không biến các claims đó thành bằng chứng an toàn**; quyết định cuối cùng vẫn thuộc resource server.

## 12. Rủi ro bảo mật khi xác định giờ hiệu lực

### 12.1. Chỉ giải mã `nbf` mà không xác minh JWT

Attacker tự tạo payload:

~~~json
{
  "sub": "admin",
  "aud": "orders-api",
  "scope": "orders.write",
  "nbf": 0,
  "exp": 4102444800
}
~~~

Nếu API decode Base64url rồi tin những claim đó, attacker có thể đặt `nbf` rất sớm và `exp` rất xa. **Phải xác minh chữ ký, thuật toán, issuer, audience, loại token, thời gian và scope trước khi tin bất kỳ claim nào**. JWT có chữ ký giúp phát hiện sửa đổi, nhưng không mã hóa payload và không tự chống replay của token bị đánh cắp.

### 12.2. Cho phép leeway quá lớn

Một API dùng leeway 10 phút để tránh lỗi đồng hồ. Token dự kiến chỉ active sau 5 phút lại có thể được dùng **ngay lập tức**, và token đã hết hạn vẫn có thể được dùng thêm. Cần giảm leeway, sửa đồng hồ và dùng kiểm tra activation phía server cho nghiệp vụ có mốc tuyệt đối.

### 12.3. Bỏ qua thu hồi trước khi token có hiệu lực

Một user bị xóa khỏi organization lúc 10:00:20; JWT đã ký lúc 10:00:00 có `nbf=10:00:30`. Nếu resource server chỉ xác minh offline, nó có thể chấp nhận token lúc 10:00:30 dù membership đã bị thu hồi.

Giải pháp phù hợp có thể là **trạng thái grant hiện hành, denylist, opaque introspection hoặc token version**; chọn theo mức rủi ro. `nbf` không thay thế thu hồi.

### 12.4. Đặt `nbf` quá xa làm mất khả năng kiểm soát

Phát JWT dùng được vài ngày sau có thể tạo rủi ro credential bị rò rỉ và nằm chờ kích hoạt. Nếu quyền thay đổi giữa lúc ký và lúc bắt đầu, token offline có thể không phản ánh quyết định mới. Với tác vụ lên lịch, cân nhắc **chỉ phát token gần thời điểm cần dùng** hoặc dùng token tham chiếu với trạng thái kích hoạt được quản lý ở server.

### 12.5. Token bị đánh cắp hoặc phát lại sau `nbf`

`nbf` ngăn token được sử dụng quá sớm theo đồng hồ của validator, nhưng **không ràng buộc token với thiết bị, client hay người đang cầm token**. Bearer access token bị đánh cắp có thể bị replay sau khi bắt đầu có hiệu lực. Cần TLS, hạn ngắn, tránh log token/URL, lưu trữ phù hợp, audience/scope tối thiểu và cân nhắc token ràng buộc bên gửi như **DPoP hoặc mTLS** khi phù hợp.

### 12.6. Cache và race condition quanh thời điểm kích hoạt

Nhiều API/gateway có thể đánh giá token hoặc cache introspection vào các thời điểm khác nhau. Nếu cache kết quả `active=false` quá lâu, token bị từ chối **sau** giờ kích hoạt; nếu cache `active=true` quá lâu, token bị thu hồi vẫn được dùng. Nên thiết kế TTL/cache invalidation và thử nghiệm request đồng thời sát mốc `nbf`/`exp`.

## 13. Kiểm thử các mốc thời gian

Ví dụ giả định `iat=1800000000`, `nbf=1800000030`, `exp=1800000930`, không leeway trừ khi nêu riêng:

| Trường hợp kiểm thử | Kỳ vọng |
| --- | --- |
| `now=nbf-1` | Từ chối vì chưa hiệu lực |
| `now=nbf` | Qua kiểm tra `nbf`, tiếp tục các kiểm tra khác |
| `now=nbf+1` | Qua kiểm tra `nbf` |
| `now=exp-1` | Vẫn hợp lệ về thời gian |
| `now=exp` | Từ chối vì hết hạn |
| `now=exp+1` | Từ chối |
| `iat` nằm trong tương lai vượt policy | Từ chối theo quy tắc `iat` của issuer/consumer |
| `nbf >= exp` | Từ chối vì khoảng hiệu lực không hợp lệ theo profile |
| Thiếu `nbf` trong JWT cho phép claim tùy chọn | Áp chính sách của profile; không tự bịa mốc bắt đầu |
| Thiếu `nbf` trong profile bắt buộc có claim | Từ chối |
| `nbf` ghi mili-giây thay vì giây | Từ chối do sai schema/thời gian bất thường |
| `nbf` là chuỗi thay vì NumericDate | Từ chối nếu schema/profile yêu cầu NumericDate |
| `now=nbf-20s`, leeway 30s | Có thể vượt kiểm tra thời gian; kiểm thử rủi ro chấp nhận sớm |
| `now=exp+20s`, leeway 30s | Có thể vượt kiểm tra thời gian; kiểm thử rủi ro chấp nhận muộn |
| JWT có `nbf` đúng nhưng sai chữ ký | Từ chối |
| JWT có `nbf` đúng nhưng sai audience | Từ chối |
| Token active, nhưng thiếu scope hoặc sai tenant | Từ chối theo phân quyền |
| JWT đã đến `nbf` nhưng bị revoke | Từ chối khi hệ thống yêu cầu kiểm tra thu hồi |
| Opaque token bị cache `active=false` sau giờ kích hoạt | Phải xử lý TTL/invalidation, tránh lỗi lâu dài |
| Hai resource server có clock skew khác nhau | Kết quả trong phạm vi policy đã định, có giám sát lệch đồng hồ |

### 13.1. Dùng `Clock.fixed` để kiểm tra Java

Khi test logic thời gian riêng của ứng dụng, dùng **`Clock` có thể thay thế** để kiểm soát chính xác các mốc:

~~~java
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;

Instant before = Instant.ofEpochSecond(1_800_000_029L);
Instant atStart = Instant.ofEpochSecond(1_800_000_030L);
Instant atExpiry = Instant.ofEpochSecond(1_800_000_930L);

Clock clockBefore = Clock.fixed(before, ZoneOffset.UTC);
Clock clockAtStart = Clock.fixed(atStart, ZoneOffset.UTC);
Clock clockAtExpiry = Clock.fixed(atExpiry, ZoneOffset.UTC);

// Test từng trường hợp bằng policy/validator nhận Clock;
// tránh Thread.sleep() và phụ thuộc thời gian thật của máy.
~~~

Nếu test Spring Security bằng **mock JWT**, cần nhớ mock có thể **bỏ qua chữ ký và decoder thật**. Tách kiểm thử **business time policy** khỏi **integration test** của JWT decoder để chắc chắn chữ ký, issuer, audience, `nbf`, `exp` đều được xác minh như thiết kế.

## 14. Checklist thiết kế thời điểm bắt đầu hiệu lực

1. **Xác định yêu cầu nghiệp vụ:** token cần active ngay hay được phát trước rồi dùng sau? Nếu là giới hạn tuyệt đối, có cần kiểm tra activation server-side không?
2. **Đặt nghĩa thống nhất cho các mốc:** `iat` là lúc phát hành; `nbf` là ngưỡng bắt đầu; `exp` là ngưỡng hết hạn; `auth_time` thuộc sự kiện xác thực user.
3. **Chọn đơn vị đúng:** NumericDate thường tính bằng epoch **seconds**, không dùng mili-giây hay local timezone.
4. **Xây claims từ policy của AS:** client không tự quyết định `nbf`, scope, audience hoặc ngày hết hạn vượt quyền.
5. **Thống nhất TTL và `expires_in`:** xét `exp-iat`, `exp-nbf` và thời điểm tạo token response.
6. **Xác minh đầy đủ tại API:** chữ ký/introspection, issuer, audience, loại token, `nbf`, `exp`, `iat` theo profile và các giới hạn bổ sung.
7. **Kiểm soát leeway:** đồng bộ đồng hồ, đặt sai số nhỏ có chủ đích, hiểu rủi ro chấp nhận trước `nbf` và sau `exp`.
8. **Giữ nguyên phân quyền:** kiểm tra scope, principal, tenant, membership, resource ownership và trạng thái grant sau khi qua thời gian.
9. **Có đường thu hồi:** xử lý quyền bị rút trước giờ kích hoạt, access token JWT còn hạn, opaque cache và refresh token.
10. **Không coi `nbf` là chống replay:** bảo vệ bearer token, TLS, log, lưu trữ và cân nhắc sender-constrained token.
11. **Kiểm thử ranh giới:** `nbf-1`, `nbf`, `exp-1`, `exp`, skew, thiếu claim, sai kiểu, issuer khác và concurrent request.
12. **Quan sát vận hành an toàn:** ghi mã lỗi, thời điểm máy chủ, độ lệch và token metadata đã lọc; không ghi nguyên credential.

## 15. Tài liệu tham khảo

- [RFC 7519 — JSON Web Token (JWT)](https://www.rfc-editor.org/rfc/rfc7519): các mục 2, 4.1.4, 4.1.5 và 4.1.6 định nghĩa NumericDate, `exp`, `nbf`, `iat`.
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068): profile JWT access token và các yêu cầu phát hành/validation cho resource server.
- [RFC 6749 — OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749): phạm vi cấp quyền, token response và ý nghĩa `expires_in`.
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662): trạng thái `active`, `nbf`, `iat`, `exp` và metadata của token opaque.
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750): truyền bearer token, `invalid_token` và `WWW-Authenticate`.
- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html): ID token, `auth_time`, `max_age` và phân biệt xác thực user với phát hành token.
- [RFC 8725 — JSON Web Token Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725): xác minh JWT, thuật toán, loại token và tránh token confusion.
- [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700): bảo vệ access/refresh token, rủi ro token bị đánh cắp và vòng đời quyền.
- [Spring Security — OAuth 2.0 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html): kiểm tra JWT trong resource server, `JwtTimestampValidator` và tùy biến validation.

**Ghi nhớ:** `nbf` xác định **token sớm nhất có thể được chấp nhận**, `iat` xác định **token được phát hành khi nào**, còn `exp` xác định **khi nào token phải bị coi là hết hạn**. Độ lệch đồng hồ có thể làm ranh giới thực tế thay đổi; vì vậy phải chọn leeway có chủ đích. Chỉ cho phép request sau khi token đã được **xác minh toàn diện** và quyền đối với tài nguyên thực tế đã được kiểm tra; qua `nbf` không tự biến token thành quyền truy cập vô điều kiện.
