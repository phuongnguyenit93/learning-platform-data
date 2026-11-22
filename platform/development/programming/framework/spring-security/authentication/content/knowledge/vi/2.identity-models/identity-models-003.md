# Credentials và giới hạn vòng đời dữ liệu nhạy cảm

Trong mô hình danh tính của Spring Security, **credential** (thông tin xác thực) là thứ một chủ thể trình ra để hệ thống kiểm tra khả năng kiểm soát một tài khoản, khóa, phiên hoặc danh tính dịch vụ. Mật khẩu, mã OTP, khóa API, bearer token và cookie phiên khác nhau về cách kiểm chứng, nhưng có cùng một rủi ro: nếu xuất hiện ở sai nơi hoặc tồn tại quá lâu, kẻ khác có thể dùng chúng để mạo danh.

Ranh giới vòng đời dữ liệu nhạy cảm là câu trả lời cho các câu hỏi rất cụ thể: **Ai được tạo và nhận dữ liệu? Nó được phép đi qua thành phần nào? Được lưu ở đâu, bao lâu? Khi nào phải xóa, hết hạn, luân chuyển hoặc thu hồi? Ai được biết kết quả xác thực mà không cần biết credential gốc?** Bài này đặt các câu hỏi đó vào luồng xác thực Spring Security; phạm vi trọng tâm là bảo vệ credential và dữ liệu nhạy cảm trong suốt vòng đời, không phải thiết kế toàn bộ quy tắc authorization.

## 1. Mục tiêu

Sau bài học, bạn có thể:

1. Phân biệt định danh, credential gốc, bằng chứng đã kiểm, kết quả `Authentication`, credential dẫn xuất và dữ liệu cá nhân nhạy cảm.
2. Lập vòng đời từ cấp phát → truyền → xác minh → sử dụng → lưu giữ → rotation/revocation → hết hạn và xóa; đặt ranh giới tin cậy cho từng chặng.
3. Giải thích vì sao không được lưu/log mật khẩu gốc, session ID, token và khóa; hiểu password hashing, giới hạn của mã hóa, masking và xóa bộ nhớ.
4. Hiểu `PasswordEncoder`, `AuthenticationManager`/`ProviderManager`, `CredentialsContainer`, `eraseCredentials()` và `SecurityContext` trong ứng dụng Spring Security Servlet.
5. Chọn chính sách vòng đời hợp lý cho mật khẩu, OTP, access/refresh token, session, khóa ký và service secret; biết cách thử những trường hợp hết hạn, thu hồi, rò rỉ và replay.

## 2. Dữ liệu nào là credential? Không được đánh đồng mọi trường danh tính

| Dữ liệu | Vai trò | Có phải bí mật dùng để xác thực? | Đối xử an toàn |
| --- | --- | --- | --- |
| `username`, account ID | Identifier để tìm chủ thể | Thường không, nhưng có thể là dữ liệu cá nhân | Không xem việc biết username là đã xác thực; hạn chế lộ thông tin định danh. |
| Mật khẩu gốc, mã khôi phục tài khoản | Bí mật để chứng minh quyền kiểm soát | **Có** | Chỉ xử lý đủ để xác minh/đổi, không log hoặc lưu dạng rõ. |
| Mã OTP/TOTP | Bằng chứng ngắn hạn, có thể dùng một lần | **Có**, trong cửa sổ hợp lệ | Giới hạn thời gian/thử lại, chống phát lại; không ghi vào log. |
| Private key/passkey private key, API key, client secret | Phương tiện để ký/chứng minh hoặc gọi dịch vụ | **Có** | Giữ trong thành phần được phép sử dụng; bảo vệ khóa riêng, quyền ít nhất cần thiết, luân chuyển/thu hồi. |
| Password hash có salt và tham số thuật toán | Bản lưu để đối chiếu mật khẩu | Không dùng trực tiếp như mật khẩu với verifier chuẩn, **nhưng rất nhạy cảm** | Bảo vệ DB, backup và quyền đọc; chống tấn công đoán mật khẩu offline. |
| Access token bearer | Chứng từ mang quyền truy cập tới API | **Có khi còn hiệu lực**: ai sở hữu có thể dùng | Hạn dùng/scope/audience hẹp, bảo vệ vận chuyển và bộ nhớ, không log. |
| Refresh token | Chứng từ để xin access token mới | **Có, thường nhạy cảm hơn access token ngắn hạn** | Lưu an toàn theo loại client, luân chuyển và phát hiện replay theo thiết kế. |
| Session ID / cookie phiên | Định danh phiên để nối lại kết quả xác thực | **Có khi còn hiệu lực** | Cookie `Secure`/`HttpOnly`/`SameSite` theo rủi ro, session timeout và invalidate. |
| JWT claims, email, số điện thoại, tên thật | Thông tin mô tả chủ thể/thuộc tính | Không nhất thiết là credential, nhưng có thể là PII | Chỉ thu thập/cung cấp đúng nhu cầu, kiểm quyền xem, bảo vệ lưu giữ. |
| Public key/JWKS | Dùng để kiểm chữ ký | Thông thường **không** là bí mật | Vẫn phải xác thực nguồn khóa, issuer, thuật toán, tính mới và ràng buộc trust. |

**Một secret có thể đồng thời là credential, nhưng mọi dữ liệu nhạy cảm không nhất thiết là credential.** Ví dụ email của người dùng có thể là PII dù không đủ để đăng nhập. Ngược lại, session ID là một chuỗi khó đoán, có thể không mang tên người dùng nhưng đủ để chiếm phiên nếu bị lộ.

Phân biệt ba trạng thái:

- **Giá trị do client trình ra:** `Authorization` header, mật khẩu, OTP, cookie, một trường JSON hoặc client certificate. Đây là **đầu vào cần kiểm chứng**, chưa phải kết luận tin cậy.
- **Bằng chứng đã được kiểm chứng:** kết quả so khớp mật khẩu, kiểm chữ ký/challenge, xác nhận phiên còn hợp lệ và đúng phạm vi. Cần xem cả nguồn phát hành, thời hạn và mục đích.
- **Kết quả dùng cho nghiệp vụ:** `Authentication` đã xác thực với principal và authorities thích hợp. Service nghiệp vụ nên nhận identity/authorization result cần thiết, **không cần nhận mật khẩu/OTP/raw bearer token**.

Một bí mật có thể không hiện ra trong tham số nghiệp vụ nhưng vẫn bị rò nếu gateway log toàn bộ HTTP header, exception in object request, APM ghi body, hoặc nền tảng sao chép biến môi trường vào bản chẩn đoán.

## 3. Bản đồ vòng đời: ranh giới nào dữ liệu được phép đi qua?

```text
[Khởi tạo/cấp phát credential]
           |
           | (1) Đăng ký: kiểm quyền sở hữu, cấp qua kênh phù hợp
           v
[Người dùng / thiết bị / secret store]
           |
           | (2) TLS; form login / Authorization header / cookie / mTLS
           v
[Reverse proxy / load balancer] -- (5) --> [Logs/APM/traces: chỉ metadata đã lọc]
           |
           | (3) forwarding rules; không tin header tự khai
           v
[Spring Security: filters / AuthenticationManager / token verifier]
           |                                |
           | (4) tra password hash            +--> [Issuer/JWKS/introspection tin cậy]
           +-----------> [User store]
           |
           v
[Authentication được kiểm chứng / SecurityContext]
           |
           +--> [Authorization + business service nhận principal/scopes]
           |
           +--> [Session store nếu thiết kế stateful]
           |
           v
[Timeout / logout / rotate / revoke / delete]
```

Với mỗi mũi tên, hãy ghi rõ **nguồn, đích, quyền truy cập, kênh bảo vệ, dữ liệu tối thiểu, thời hạn và cách hủy/thu hồi**:

1. **Cấp phát:** chỉ nguồn được ủy quyền tạo credential; random secret cần entropy phù hợp, giới hạn quyền và môi trường. Không nhúng private key, password dịch vụ hoặc production token trong source code.
2. **Truyền:** dùng TLS và endpoint đúng. Bảo đảm proxy, gateway, ingress và service mesh không ghi lại `Authorization`, `Cookie`, request body chứa mật khẩu hoặc query string nhạy cảm.
3. **Chấp nhận:** server xác minh theo cơ chế phù hợp. Client không được tự tăng quyền bằng các trường `userId`, `role`, `X-Authenticated-User`; proxy chỉ chuyển tiếp danh tính đã xác thực khi thiết lập được chuỗi tin cậy rõ ràng.
4. **Chuyển hóa:** credential gốc chỉ tồn tại đủ lâu cho việc kiểm chứng; kết quả là principal/scopes/quyền cho logic nghiệp vụ, không phải bản sao mật khẩu. Password hash được giữ ở user store cho lần xác thực tiếp theo.
5. **Quan sát:** log/tracing chỉ ghi sự kiện có ích như principal ID đã chuẩn hóa, loại xác thực, kết quả, request ID, lý do từ chối đã làm sạch; không ghi secret và bản chứa credential vào nơi lưu quan sát dài hạn.
6. **Kết thúc:** logout, account disable, password reset, token expiry và key rotation có **điểm kết thúc khác nhau**. Xóa chuỗi bên client **không tự vô hiệu hóa** session/token mà server vẫn chấp nhận.

### Đặt ranh giới thời gian

**Thời gian tồn tại của credential** không đồng nghĩa **thời gian tồn tại của kết quả xác thực**:

- Mật khẩu được nhập tại thời điểm T0, kiểm với hash rồi bỏ bản gốc; một session có thể giữ trạng thái đăng nhập đến T1.
- Access token ngắn hạn có thể vẫn dùng được cho tới `exp` nếu hệ thống chưa có cơ chế thu hồi tức thì.
- Refresh token có thể sống lâu hơn access token, vì vậy cần được bảo vệ chặt hơn và thiết kế rotation/reuse detection.
- Tài khoản bị khóa hoặc thay quyền tại T2 có được áp dụng ngay hay không phụ thuộc điểm kiểm trạng thái và freshness policy; đừng giả định hệ thống tự thu hồi mọi JWT đã phát.
- Dữ liệu đã bị ghi vào backup, crash dump hoặc log có vòng đời riêng; xóa biến Java hoặc bản ghi DB không đồng nghĩa tất cả bản sao biến mất.

## 4. Password: từ bí mật tạm thời đến verifier lâu dài

### 4.1 Nhập và kiểm chứng

1. Người dùng nhập mật khẩu qua form/HTTP Basic trên **HTTPS**. Mật khẩu trong request là plaintext tại lớp ứng dụng sau khi TLS được giải mã, nên gateway, filter, tracing và error handler vẫn có thể thấy nó.
2. Ứng dụng tìm tài khoản theo identifier và lấy **password hash** đã lưu. Hash không phải mật khẩu và không nên được gửi cho client; dù vậy lộ hash vẫn có thể cho phép kẻ tấn công đoán password offline.
3. Spring Security đối chiếu bằng `PasswordEncoder.matches(rawPassword, encodedPassword)`. Một thuật toán password hashing thích hợp phải chống brute-force tốt, sử dụng salt/chi phí phù hợp; **SHA-256 thông thường hay mã hóa reversible một mình không phải cách lưu mật khẩu**.
4. Nếu thông tin hợp lệ, server tạo kết quả xác thực và gắn principal/authorities; mật khẩu gốc **không có lý do nghiệp vụ để được đưa vào `SecurityContext`, response, message bus hoặc log**.
5. Khi thay mật khẩu/reset, kiểm quyền hoặc chứng minh sở hữu qua cơ chế an toàn, lưu hash mới, xử lý các phiên/token cũ theo chính sách, vô hiệu hóa reset token đã dùng và ghi audit event không chứa password.

**PasswordEncoder dùng để bảo vệ mật khẩu khi lưu giữ; TLS dùng để bảo vệ khi truyền; kiểm soát log/bộ nhớ dùng để giới hạn nơi mật khẩu xuất hiện.** Đây là ba lớp bảo vệ riêng. Không thay thế tầng này bằng tầng kia.

Spring Security có `PasswordEncoderFactories.createDelegatingPasswordEncoder()` tạo `DelegatingPasswordEncoder`, cho phép định dạng `{id}encodedValue` và xác minh các thuật toán được cấu hình theo id, hỗ trợ chuyển đổi hash cũ theo kế hoạch. Ví dụ `{bcrypt}$2a$...` là password hash với prefix nhận diện thuật toán; `{noop}plain` chỉ phục vụ mẫu/dữ liệu cũ đặc biệt và **không an toàn cho mật khẩu thực**. Chi phí hashing cần hiệu chỉnh theo môi trường và khả năng phòng chống DoS.

**Không cần ép mọi người dùng đổi mật khẩu định kỳ vô điều kiện.** Theo chính sách hiện đại, nên yêu cầu đổi khi có bằng chứng/nghi ngờ lộ, tài khoản bị chiếm hoặc yêu cầu nghiệp vụ phù hợp; kết hợp MFA có khả năng chống phishing, chặn password nằm trong danh sách đã lộ và giới hạn thử đăng nhập. “Tăng số lần đổi mật khẩu” không bù được cách lưu hoặc kiểm chứng yếu.

### 4.2 Hash, salt, pepper và key không giống nhau

- **Salt** là giá trị ngẫu nhiên riêng cho mỗi password record, thường lưu kèm hash, giúp phá việc dùng bảng tra cứu chung; salt **không cần bí mật**.
- **Password hash** được tạo từ password, salt và cấu hình thuật toán (ví dụ bcrypt hoặc Argon2id tùy chính sách, thư viện hỗ trợ). Hash vẫn cần được bảo vệ vì có thể bị tấn công offline.
- **Pepper** (nếu kiến trúc sử dụng) là secret bổ sung quản lý tách khỏi database, không phải phần mặc định của mọi `PasswordEncoder`; thiết kế cần có cơ chế đổi pepper và xử lý rủi ro khi lộ.
- **Encryption key** dùng để mã hóa/giải mã dữ liệu cần phục hồi; không dùng encryption reversible thay password hashing cho mật khẩu người dùng. Các bí mật bắt buộc lấy lại được, như credential truy cập hệ thống khác, cần vault/KMS và quyền truy cập rõ ràng.

### 4.3 Giới hạn trong Java heap

Với secret nhận từ terminal hoặc thư viện hỗ trợ buffer, ưu tiên hạn chế số bản sao, phạm vi sống và xóa **mảng do mình sở hữu** sau khi dùng. Tuy nhiên, `String` là immutable: không có API chuẩn để xóa chắc chắn các bản sao trong heap; body parser, framework, log, debugger hoặc GC có thể giữ bản sao khác. Không khẳng định `Arrays.fill(char[], '\0')` là giải pháp zeroization hoàn chỉnh.

Ví dụ Java 17+ độc lập, có thể biên dịch để hiểu phạm vi xóa **một buffer cụ thể**. File `SecretBufferDemo.java`:

```java
import java.util.Arrays;

public final class SecretBufferDemo {
    public static void main(String[] args) {
        char[] demoSecret = {'d', 'e', 'm', 'o'};
        try {
            System.out.println("characters=" + demoSecret.length);
            // Minh họa thao tác sử dụng buffer. Không in giá trị secret.
        } finally {
            Arrays.fill(demoSecret, '\0');
        }
        boolean cleared = true;
        for (char value : demoSecret) {
            if (value != '\0') {
                cleared = false;
            }
        }
        System.out.println("owned-buffer-cleared=" + cleared);
    }
}
```

Biên dịch và chạy:

```bash
javac SecretBufferDemo.java
java SecretBufferDemo
```

Stdout chính xác:

```text
characters=4
owned-buffer-cleared=true
```

Đây **chỉ là minh họa xóa mảng tự quản lý**, không phải một lớp xác thực và không chứng minh bộ nhớ process không còn bản sao bí mật. Trong ứng dụng Spring Security thông thường, các cơ chế chuẩn có thể dùng `String`/`CharSequence` nội bộ; tránh tự tạo thêm bản sao khi không cần và không log giá trị đó.

## 5. Xóa credential trong Spring Security: có ích nhưng có giới hạn

Luồng phổ biến của đăng nhập username/password phía Servlet có các bước:

```text
UsernamePasswordAuthenticationFilter / authentication filter
  -> Authentication yêu cầu kiểm chứng (chứa credential đầu vào)
  -> AuthenticationManager, thường là ProviderManager
  -> DaoAuthenticationProvider + UserDetailsService + PasswordEncoder
  -> Authentication thành công (principal + authorities)
  -> ProviderManager cố gắng erase credentials trong kết quả
  -> SecurityContextHolder chứa kết quả cho request hiện tại
  -> repository lưu/khôi phục context giữa các request nếu cấu hình stateful
  -> ủy quyền truy cập controller/service
```

Đây là mô hình của flow username/password; HTTP Basic, form login, OAuth2 resource server và custom filter có điểm vào, provider và cơ chế lưu context khác nhau. **Không suy ra mọi cơ chế đều đi qua cùng một `DaoAuthenticationProvider`.**

Các API quan trọng:

- `Authentication.getCredentials()` chứa dữ liệu dùng để xác thực *tùy từng giai đoạn và loại token*. Sau xác thực thành công nó có thể đã bị xóa hoặc không còn ý nghĩa; đừng để business logic dựa vào giá trị này.
- `CredentialsContainer.eraseCredentials()` là hợp đồng cho đối tượng có credential cần xóa. Nhiều kiểu nội bộ như `UsernamePasswordAuthenticationToken` và `User` triển khai nó.
- `ProviderManager` theo mặc định cố gắng xóa credentials trên đối tượng `Authentication` thành công **nếu** đối tượng triển khai `CredentialsContainer`. Đây không phải lời hứa rằng mọi tham chiếu, HTTP body, request log hoặc bản sao bộ nhớ đều bị xóa.
- `SecurityContextHolder` chứa `SecurityContext` cho execution context hiện tại. Với Servlet, chiến lược mặc định dựa trên `ThreadLocal`, framework quản lý việc nạp/xóa trong chu kỳ filter. Không giữ raw password vào principal/details/session rồi mong hành vi erase của manager xử lý hết.
- `SecurityContextRepository` quyết định cách duy trì context theo cấu hình. Việc authentication thành công trong một request **không tự chứng minh** kết quả đã được lưu an toàn hoặc sẽ còn hiệu lực ở request tiếp theo.
- Custom `AuthenticationProvider` nên trả về đối tượng đã xác thực **không chứa dữ liệu nhạy cảm không cần thiết**; custom token có credential cần cơ chế xóa thích hợp. Cần tránh sao chép raw credential vào `details` hoặc metadata kèm theo.

### Bẫy thực tế: cùng tham chiếu UserDetails trong cache

Giả sử custom provider đặt nguyên đối tượng `UserDetails` lấy từ cache vào `Authentication.principal`. Khi `eraseCredentials()` được gọi, password trong `UserDetails` đó cũng có thể bị xóa; **nếu là cùng object của cache**, lần xác thực tiếp theo có thể không còn hash để đối chiếu. Cách thiết kế tốt là có ranh giới rõ giữa bản lưu verifier trong cache/store và bản principal trả cho request, tạo bản sao phù hợp nếu cần, và kiểm thử thực tế. Không bật `eraseCredentialsAfterAuthentication=false` chỉ để “chữa” lỗi cache mà bỏ mất lớp bảo vệ.

Phân biệt:

- **Xóa khỏi kết quả authentication:** giảm việc giữ raw credential trong đối tượng Spring Security.
- **Dọn `SecurityContext`:** xử lý state theo request/luồng, thông thường do filter chịu trách nhiệm; mã tự quản luồng/test có thể cần `SecurityContextHolder.clearContext()` đúng chỗ.
- **Hủy phiên/thu hồi token:** hành động bảo mật liên quan server và issuer, không được thực hiện chỉ bằng xóa một biến Java.

**Chỉ tạo `Authentication` ở thành phần có thẩm quyền xác thực.** Không đọc `X-User`/`role` từ request rồi tạo một token `authenticated=true` để đi đường tắt. Credential erasure không khắc phục sự cố tin nhầm dữ liệu client.

## 6. Session, access token và refresh token: ba vòng đời khác nhau

### 6.1 Session dựa trên cookie

Sau khi đăng nhập thành công, ứng dụng stateful có thể giữ authentication state phía server và đặt session ID vào cookie. Cookie là **bearer credential** cho các request tiếp theo, không phải bản sao mật khẩu. Yêu cầu thiết kế:

- Session ID đủ khó đoán; thay session ID tại đăng nhập nhằm giảm session fixation theo cơ chế và cấu hình phù hợp.
- Cookie `Secure` chỉ gửi qua HTTPS, `HttpOnly` ngăn JavaScript đọc trực tiếp, `SameSite` hỗ trợ giảm một số luồng cross-site; chọn `Domain`/`Path` chặt chẽ.
- Kiểm idle timeout, absolute timeout nếu chính sách cần, giới hạn số phiên đồng thời, logout/invalidate phía server và chính sách buộc đăng nhập lại khi thay credential.
- Bảo vệ CSRF cho luồng dựa trên cookie tự gửi; `HttpOnly` và `SameSite` **không thay thế** mọi biện pháp CSRF, XSS hoặc kiểm quyền object.
- Trong distributed system, session store/replication có lifecycle và quyền truy cập riêng; tuyệt đối không đưa raw password vào session attributes để “tiện lần sau”.

**Dấu hiệu rủi ro:** test logout xong chỉ thấy cookie biến mất ở browser nhưng dùng lại cookie cũ vẫn truy cập được endpoint. Điều đó chứng tỏ hiệu lực phía server chưa bị hủy theo mong đợi.

### 6.2 Bearer access token tới resource server

Access token có scope/audience/thời gian sử dụng được cấp bởi authorization server. Nếu là JWT tự chứa, API phải kiểm chữ ký, issuer tin cậy, audience cho **đúng API**, thời gian (`exp`/`nbf`) và ràng buộc khác như scope hoặc tenant. **Decode Base64 không phải verify**; tên `sub` nằm trong payload chưa đủ để xác thực.

- Chỉ nhận token qua kênh/header phù hợp trên TLS; tránh token trong URL vì URL có thể lưu ở browser history, referrer, proxy và log.
- Không trả lại access token vào error JSON, log, tracing span hoặc message queue. Nếu cần liên kết sự kiện, dùng request ID hoặc token ID **đã được làm sạch và không đủ để dùng lại credential**.
- JWT hợp lệ về chữ ký chưa chắc đã **thu hồi ngay** khi account disable hoặc logout. Muốn immediate revocation cần cơ chế bổ sung (ví dụ introspection, allow/deny list có kiểm soát, key invalidation theo phạm vi phù hợp, hoặc token sống rất ngắn).
- Token tự thân không phải bằng chứng mạnh rằng đúng người dùng ban đầu đang gửi nó: bearer token bị đánh cắp có thể bị dùng lại trong thời gian hiệu lực; sender-constrained token có cơ chế kiểm soát khác như mTLS/DPoP.

ID token của OIDC chủ yếu chứng minh sự kiện đăng nhập với client/relying party; **không dùng ID token như access token cho API**. Claim nào được cấp cho bên nhận nào phải được kiểm theo hợp đồng giao thức.

### 6.3 Refresh token

Refresh token có thể tạo access token mới mà không yêu cầu nhập lại password, vì vậy một refresh token bị lộ có thể duy trì quyền truy cập lâu dài hơn access token. Cần:

1. Lưu theo năng lực bảo vệ của client: confidential server-side client có kho secret; public client cần cơ chế được authorization server hỗ trợ, chẳng hạn refresh-token rotation hoặc sender-constraining theo chính sách.
2. Có expiry, phạm vi và ràng buộc client/subject. Không đưa refresh token vào local log, response không cần thiết hoặc URL.
3. Khi refresh, nếu dùng rotation, phát token mới và vô hiệu hóa token cũ theo chính sách; replay của token cũ phải được phát hiện và xử lý nhất quán, có thể thu hồi cả token family khi nghi ngờ bị đánh cắp.
4. Khi logout toàn cục, revoke grant, đổi trạng thái tài khoản hoặc phát hiện sự cố, định nghĩa rõ cơ chế thu hồi tại authorization server và ảnh hưởng đến access token đã cấp.

### Bảng phân định

| Sự kiện | Password | Session cookie phía server | Access token tự chứa | Refresh token |
| --- | --- | --- | --- | --- |
| User vừa đăng nhập | Chỉ cần để kiểm tại thời điểm đó | Có thể tạo session | Có thể được cấp theo flow | Có thể được cấp theo flow |
| User đăng xuất | Không còn cần nhập trong request hiện tại | Invalidate server-side session | Có thể vẫn hoạt động tới hạn, tùy cơ chế thu hồi | Cần revoke theo chính sách |
| Password đổi | Hash mới trong store | Quyết định hủy các session cũ | Không tự động mất hiệu lực nếu API không kiểm trạng thái | Quyết định revoke/rotate theo policy |
| Token bị lộ | Không tác động trực tiếp tới password, cần điều tra liên quan | Nếu lộ cookie: revoke session ID | Chặn/thu hồi theo thiết kế hoặc hạn dùng | Revoke token family/grant và kiểm replay |
| Hết hạn | Password thường không có TTL tự động cố định | Theo timeout của phiên | `exp` và policy validation | Theo token lifetime/rotation |

Bảng mô tả **những cơ chế có thể áp dụng**, không khẳng định cấu hình mặc định nào cũng tự vô hiệu hóa tất cả session/token khi user đổi mật khẩu.

## 7. Service secret, API key và khóa ký: quản lý như tài sản có thể bị lộ

Không chỉ người dùng có credential. Ứng dụng còn cần database password, API key, OAuth2 client secret, khóa mã hóa/ký, chứng chỉ mTLS và service-account secret. Nếu một trong số này bị lộ, phạm vi thiệt hại có thể lớn hơn một tài khoản đơn lẻ.

### Vòng đời cho machine credentials

1. **Create:** tạo bằng nguồn entropy phù hợp, cấp owner, môi trường, purpose, quyền tối thiểu, TTL/rotation policy, tên phiên bản; không dùng secret giống nhau giữa dev và production.
2. **Provision:** chuyển tới đúng workload qua secret manager/KMS/vault hoặc cơ chế nền tảng có kiểm soát; tránh secret trong Git, Docker image, artifact, command line, log, crash report, tài liệu công khai.
3. **Use:** chỉ thành phần cần biết được đọc; ưu tiên danh tính workload/short-lived credential so với secret dài hạn khi hạ tầng hỗ trợ; không trả service secret cho frontend.
4. **Rotate:** tạo phiên bản mới, triển khai người tiêu thụ, chấp nhận giai đoạn chồng lấn nếu giao thức yêu cầu, xác nhận hoạt động, rồi ngừng phiên bản cũ. Rotation cần tính đến caching, connection pool và nhiều instance.
5. **Revoke/expire:** khi bị nghi lộ hoặc không còn cần, thu hồi ở nguồn xác thực; xóa bản sao không sử dụng, kiểm audit và phát hiện sử dụng secret đã thu hồi.
6. **Review/delete:** áp dụng retention cho dữ liệu phụ như backup và log; không tuyên bố đã xóa hoàn toàn khi backup chưa hết vòng đời.

**Phân biệt public key và private key:** IdP/issuer có thể công bố public key qua JWKS cho bên xác minh chữ ký, nhưng private signing key phải ở HSM/KMS hoặc kho khóa được bảo vệ. Rotation khóa ký JWT cần giai đoạn chấp nhận khóa cũ cho token chưa hết hạn nếu chính sách yêu cầu; không vô tình mở chấp nhận mọi `kid`/issuer do client tự chọn.

**Không dùng cơ chế rotation cố định cho mọi thứ:** service secret có thể cần rotation tự động, còn mật khẩu của người dùng không nhất thiết bắt buộc đổi theo tháng nếu không có dấu hiệu lộ. Tần suất phụ thuộc loại credential, threat model, lifetime và chi phí vận hành.

## 8. Ví dụ Spring Boot Servlet: kiểm chứng mật khẩu mà không trả credential

Dưới đây là ứng dụng Java 17+, **Spring Boot 3.x / Spring Security 6.x** với `spring-boot-starter-web` và `spring-boot-starter-security`. Ví dụ dùng HTTP Basic và user in-memory **chỉ cho máy học**: controller trả thông tin principal đã xác thực, hoàn toàn không trả hay log password. Password được encode thành hash ở khâu tạo user.

File `src/main/java/demo/CredentialDemoApplication.java`:

```java
package demo;

import java.util.Map;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class CredentialDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(CredentialDemoApplication.class, args);
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(PasswordEncoder encoder) {
        UserDetails learner = User.withUsername("learner")
                .password(encoder.encode("local-demo-password"))
                .roles("READER")
                .build();
        return new InMemoryUserDetailsManager(learner);
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        return http
                .authorizeHttpRequests(authorize -> authorize
                        .requestMatchers("/public").permitAll()
                        .requestMatchers("/api/me").authenticated()
                        .anyRequest().denyAll())
                .httpBasic(Customizer.withDefaults())
                .build();
    }
}

@RestController
class WhoAmIController {

    @GetMapping("/public")
    String publicEndpoint() {
        return "public";
    }

    @GetMapping("/api/me")
    Map<String, Object> currentUser(Authentication authentication) {
        return Map.of(
                "subject", authentication.getName(),
                "authenticated", authentication.isAuthenticated());
    }
}
```

**Cách chạy:** Tạo ứng dụng Spring Boot 3.x với Java 17+ và hai starter trên, đặt file đúng đường dẫn package rồi chạy `./gradlew bootRun` (Linux/macOS), `.\gradlew.bat bootRun` (Windows PowerShell) hoặc `./mvnw spring-boot:run` với project Maven tương đương. Vì cần Spring Boot và các dependency, **không thể biên dịch ví dụ bằng một lệnh `javac` trần** như `SecretBufferDemo` ở phần 4.3.

Gửi thử các request:

```bash
curl -i http://localhost:8080/public
curl -i http://localhost:8080/api/me
curl -i -u learner:wrong http://localhost:8080/api/me
curl -i -u learner:local-demo-password http://localhost:8080/api/me
```

Trên Windows PowerShell có thể dùng `curl.exe` thay vì alias `curl`. Kỳ vọng:

| Request | Kết quả | Giải thích |
| --- | --- | --- |
| `GET /public` | HTTP 200, body `public` | Endpoint công khai. |
| `GET /api/me` không có credential | HTTP 401 kèm HTTP Basic challenge | Chưa có chứng cứ xác thực hợp lệ. |
| `GET /api/me` với sai password | HTTP 401 | Hash check thất bại. |
| `GET /api/me` với `learner:local-demo-password` | HTTP 200, JSON có `subject` = `learner`, `authenticated` = `true` | Credential đã được kiểm; endpoint chỉ dùng principal, không xuất mật khẩu. Thứ tự khóa JSON không cố định. |

**Vì sao ví dụ an toàn hơn việc trả lại credential?** Đối tượng controller chỉ cần `Authentication.getName()` và trạng thái xác thực. Nó không gọi `authentication.getCredentials()`, không dựng response chứa `Authorization` và không log password. Spring Security thực hiện kiểm tra theo cơ chế được cấu hình.

**Ranh giới của ví dụ:** `local-demo-password` là dữ liệu demo cố định, **không dùng trong production**, HTTP Basic chỉ được dùng trên HTTPS trong thực tế, cần quản lý secret, password policy và chống brute-force. Trong môi trường thật, user store phải được thiết kế và bảo vệ theo yêu cầu; đừng hardcode password, không công khai endpoint debug kể cả đã đăng nhập. Đoạn mã **không khẳng định đã thực thi kiểm thử runtime trên mọi phiên bản Spring Boot**.

### 8.1 Ví dụ sai cần tránh

Các ví dụ sau chỉ minh họa lỗi, **không phải chương trình độc lập**:

```java
// Sai: ghi nguyên request, có thể chứa password/Authorization/Cookie.
log.info("login request={}", requestBody);

// Sai: dựa vào dữ liệu do client tự khai để đặt principal.
String caller = request.getHeader("X-User");
SecurityContextHolder.getContext().setAuthentication(
        UsernamePasswordAuthenticationToken.authenticated(
                caller, null, List.of(new SimpleGrantedAuthority("ROLE_ADMIN"))));

// Sai: để credential gốc trong session hoặc gửi sang service nghiệp vụ.
session.setAttribute("password", rawPassword);
paymentService.processPayment(rawPassword, accountId);
```

Cách làm đúng là giới hạn API/filter chỉ cho component authentication nhìn thấy credential, nhận kết quả `Authentication` đã xác thực và **truyền principal cùng quyền đã kiểm tới service**. Logger nhận event dạng `login_failed`, request ID và lý do đã làm sạch. Nếu buộc phải log thông tin nhận diện, tuân thủ chính sách PII và chống log injection; masking token vài ký tự cuối vẫn có thể tiết lộ dữ liệu, nên ưu tiên không ghi.

## 9. Biên giới quan sát: log, trace, error, dump và cache

Dữ liệu nhạy cảm thường bị lộ ở **các bản sao phụ**, sau khi chương trình xác thực đã xử lý đúng. Thiết kế kiểm soát theo cả dòng dữ liệu:

| Điểm phát sinh | Lỗi thường gặp | Ràng buộc cần có |
| --- | --- | --- |
| Gateway/WAF/request logging | Log toàn bộ `Authorization`, `Cookie`, query chứa `token` | Chỉ log metadata cần thiết, scrub trước khi ghi; hạn chế quyền đọc log. |
| App logger | `log.debug("auth={}", authentication)`, dump request, JSON request body | Allowlist trường log; không dựa vào `toString()` để an toàn với mọi kiểu token tùy biến. |
| Exception/error response | Trả lỗi có stack trace, secret hoặc request header | Error format thống nhất, không echo credential, trace nội bộ có access control. |
| Tracing/APM | Tự bắt request headers/body hoặc baggage có token | Loại trừ/sanitize field nhạy cảm từ đầu; kiểm sampling và retention. |
| Session/cache | Lưu mật khẩu gốc, key không TTL, đối tượng principal giữ credential | Chỉ lưu trạng thái tối thiểu; kiểm TTL, quyền truy cập, encryption-at-rest khi cần. |
| Queue/message/event | Phát bản ghi `LoginAttempt` chứa password/OTP | Chỉ xuất event đã tách secret; không dùng credential làm correlation ID. |
| Git/CI/CD | Commit `application.yml` chứa password thật, in env secret | Secret manager, CI masking, secret scanning và quyền trên artifacts; thu hồi ngay nếu bị lộ. |
| Backup/crash dump | Thông tin nhạy cảm còn lưu sau khi nguồn xóa | Mã hóa, giới hạn truy cập, retention/deletion, quy trình xử lý sự cố. |
| Browser/client | Lưu token không kiểm soát trong localStorage, history, URL | Chọn cơ chế phù hợp threat model, CSP/XSS phòng thủ, tránh token trong URL, giảm thời gian tồn tại. |

**Redaction tốt nhất đặt trước điểm ghi**, ví dụ trước logging middleware hoặc instrumentation, để credential không xuất hiện trong log/tracing ngay từ đầu. Thêm một bước “xóa log định kỳ” sau đó không sửa được việc secret đã đến nơi không có quyền.

Ghi nhận sự kiện thất bại đủ để phát hiện tấn công mà không tiết lộ có tài khoản hay không cho client. Event có thể gồm thời điểm, request ID, tên cơ chế, kết quả, ứng dụng nguồn, mã lý do nội bộ được chuẩn hóa; giới hạn PII và tuân thủ retention.

## 10. Quy trình ứng phó khi credential bị lộ

Tùy loại credential, “đổi password” chưa chắc là hành động đủ:

1. **Xác nhận loại và phạm vi:** password người dùng, session cookie, access/refresh token, API key, private key hay dữ liệu PII. Xác định issuer, môi trường, tài nguyên và thời điểm.
2. **Contain/revoke:** khóa hoặc thu hồi credential ở **nơi thực sự xác minh nó**. Nếu session bị lộ, invalidate phía server; refresh token bị lộ, revoke grant/family theo cơ chế hệ thống; service key bị lộ, rotate/revoke tại vault và downstream API.
3. **Thay thế an toàn:** cấp credential mới, cập nhật consumer với quyền cần thiết, kiểm hoạt động trước/sau cutover. Với khóa ký, quản lý `kid`/JWKS, thời hạn token và rollback có kiểm soát.
4. **Xử lý bản sao:** tìm credential trong log, trace, issue tracker, CI output, Git history, backup và hệ thống giám sát; thu hẹp quyền truy cập, scrub/redact theo quy định và giữ evidence điều tra cần thiết.
5. **Kiểm tra sử dụng trái phép:** audit đăng nhập, hành động dùng secret, reuse detection, truy cập khác thường; chặn lỗ hổng khiến secret bị ghi ra trước khi phát hành lại.
6. **Đóng sự cố:** ghi vòng đời, owner và ngày xử lý; xác minh credential cũ bị từ chối ở mọi điểm cần thiết. Không coi “đã xóa khỏi repo” là đã kết thúc nếu token còn dùng được.

**Kịch bản cụ thể:** Một developer vô tình bật HTTP request debug và ghi bearer token của production vào log. Xóa dòng log cục bộ không làm token ở hệ thống tập trung hết hiệu lực. Cần thu hồi/giới hạn token tại issuer/API theo kiến trúc, khóa log, xử lý bản sao đã bị lưu, sửa cấu hình debug và xác nhận replay token cũ bị từ chối.

## 11. Ma trận kiểm thử các ranh giới vòng đời

| Tình huống kiểm thử | Điều cần chứng minh |
| --- | --- |
| Login đúng và sai mật khẩu | Chỉ login đúng tạo authenticated principal; không có password trong response/log/traces. |
| DB chứa password hash | Hash có thuật toán/salt/chi phí phù hợp; không có plaintext hay hash kiểu SHA-256 đơn giản; kiểm `PasswordEncoder.matches`. |
| `Authentication` thành công | Business code không cần `getCredentials()`; kiểm hành vi credential erasure của loại token/provider đang dùng. |
| Cache `UserDetails` | Sau lần login đầu, lần login thứ hai vẫn xác thực được; tránh làm mất password hash ở object cache dùng lại. |
| Logout với session cookie | Dùng lại cookie cũ bị từ chối từ server; timeout và session fixation policy hoạt động. |
| Access token sai chữ ký, `iss`, `aud` hoặc hết hạn | Resource server từ chối, không cấp principal/quyền. |
| Token bị thu hồi, account disabled | Hệ thống thực thi chính sách revoke/freshness đã cam kết; kiểm thực tế với token đã cấp trước đó. |
| Refresh-token rotation | Token cũ không cấp access token mới; replay được phát hiện/xử lý theo policy. |
| Key/service secret rotation | Secret cũ bị từ chối đúng thời điểm; consumer chuyển sang secret mới, không lộ vào logs/CI. |
| Request body chứa OTP/password | Gateway, error, APM, tracing, queue, metrics không ghi dữ liệu nhạy cảm. |
| Custom filter/header `X-User` | Dữ liệu client tự khai không được nâng thành `Authentication` đáng tin. |
| Request cross-site dùng session cookie | CSRF defense đúng với ứng dụng browser và hành động thay đổi state. |
| Không tồn tại user / password sai | Client nhận thông báo phù hợp để tránh lộ account enumeration; audit vẫn hữu ích. |
| Token có trong URL/query | API không thiết kế phát tán token qua URL; log và browser history không tích lũy token. |

Kiểm thử không chỉ xem HTTP 200/401. Cần xem **mọi nơi có thể giữ lại credential** sau request: DB, cache, session, audit, log pipeline, trace, metrics labels, queue, browser storage và backup theo quyền kiểm tra phù hợp.

## 12. Những hiểu nhầm cần tránh

1. **“Mật khẩu hash rồi là không nhạy cảm nữa.”** Hash có thể bị lấy để dò offline; cần kiểm soát DB, backup và chính sách password.
2. **“`ProviderManager` erase xong là hết mọi bản sao trong heap.”** Erase áp dụng cho một số đối tượng/đường đi; không xử lý mọi `String`, log, cache hoặc framework copy.
3. **“Xóa cookie ở browser đồng nghĩa session server hết hiệu lực.”** Server phải invalidate phiên/kiểm timeout; browser không kiểm soát bản cookie kẻ khác giữ.
4. **“JWT đúng chữ ký có thể dùng ở mọi API.”** Resource server phải kiểm issuer, audience, purpose, thời hạn, scope và policy.
5. **“Bearer token bị lộ vẫn an toàn nhờ chữ ký.”** Người giữ token hợp lệ có thể dùng lại trong giới hạn quyền của token đến khi bị từ chối.
6. **“Dùng HTTPS rồi có thể log Authorization header.”** TLS bảo vệ kênh truyền; log/trace là kênh sao chép khác.
7. **“Cần lưu raw password trong session để biết người dùng.”** Lưu principal đã xác thực; không lưu bí mật gốc.
8. **“Mọi loại secret đều phải đổi mật khẩu mỗi 30 ngày.”** Rotation và expiry phải theo loại credential và rủi ro; mật khẩu người dùng nên đổi khi có dấu hiệu lộ, còn service secrets có thể cần rotation tự động.
9. **“Xóa `char[]` nghĩa là không còn bí mật ở đâu trong JVM.”** Chỉ xóa mảng đó; bản sao, immutable `String` và crash dump có giới hạn riêng.
10. **“Chỉ cần scrub log sau khi lưu.”** Secret đã đi qua hệ thống logging; phải chặn ở điểm thu thập, thu hẹp quyền và xử lý sự cố nếu đã bị phát tán.

## 13. Tự kiểm tra

**Câu 1.** User đăng nhập bằng password, sau đó gọi 100 request bằng session cookie. Có nên giữ password gốc trong `HttpSession` để tránh kiểm lại không?

**Đáp án:** Không. Session lưu trạng thái xác thực có kiểm soát; password chỉ cần cho lần kiểm tại login hoặc reauthentication. Cookie/session ID có vòng đời và rủi ro riêng.

**Câu 2.** Vì sao password hash và access token đều cần bảo vệ, dù chỉ token có thể dùng trực tiếp để gọi API?

**Đáp án:** Access token bearer có thể bị replay trực tiếp khi còn hiệu lực. Password hash cho phép tấn công đoán password offline và có thể dẫn tới chiếm tài khoản; cả hai đều gây hại nếu bị lộ, nhưng cơ chế khai thác và thu hồi khác nhau.

**Câu 3.** Custom `Authentication` đã xóa `credentials`. Có thể khẳng định hệ thống không còn secret trong bộ nhớ không?

**Đáp án:** Không. Cần xét bản sao input, principal/details, cache, request object, chuỗi immutable, log và JVM dumps. Erasure làm giảm phạm vi lưu giữ, không xóa toàn bộ dấu vết.

**Câu 4.** Một access token JWT bị đánh cắp vừa được cấp cho API A, có `exp` sau 10 phút. User bấm logout ở browser. Vì sao API A có thể vẫn nhận token bị đánh cắp?

**Đáp án:** Xóa token phía browser không tự thu hồi JWT đã cấp. Nếu API A chỉ kiểm chữ ký và thời gian, token vẫn hợp lệ trong khoảng còn lại; cần cơ chế revoke/freshness hoặc TTL ngắn theo chính sách.

**Câu 5.** Sau khi đổi password, một phiên cũ vẫn truy cập được. Điều này luôn là lỗi Spring Security?

**Đáp án:** Không thể kết luận chỉ từ trạng thái đó. Tính hợp lệ phiên cũ phụ thuộc chính sách và cấu hình invalidate/session management của ứng dụng; nếu hệ thống cam kết hủy tất cả phiên khi đổi mật khẩu thì đây là lỗi cần sửa.

**Câu 6.** Khi gặp lỗi ở bước kiểm mật khẩu, nên log toàn bộ request để debug không?

**Đáp án:** Không. Log metadata an toàn như request ID, loại xác thực, kết quả và reason code đã chuẩn hóa; tránh password, OTP, bearer token, cookie và dữ liệu cá nhân không cần thiết.

## 14. Tài liệu chuyên sâu

- [Spring Security — Authentication Architecture](https://docs.spring.io/spring-security/reference/servlet/authentication/architecture.html): `Authentication`, `ProviderManager`, `CredentialsContainer` và giới hạn của erase khi có cache.
- [Spring Security — CredentialsContainer](https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/credentials-container.html): ý nghĩa `eraseCredentials()` và việc tự triển khai credential object.
- [Spring Security — Password Storage](https://docs.spring.io/spring-security/reference/features/authentication/password-storage.html): `PasswordEncoder`, `DelegatingPasswordEncoder` và format hash.
- [Spring Security — Session Management](https://docs.spring.io/spring-security/reference/servlet/authentication/session-management.html): phiên, session fixation và lifecycle.
- [OWASP — Secrets Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html): cấp phát, rotation, revocation, expiry, logging và kiểm soát secret.
- [OWASP — Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html): các nhóm dữ liệu cần loại khỏi log.
- [OWASP — Password Storage Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html): thuật toán hashing và quản lý password.
- [NIST SP 800-63 Digital Identity Guidelines](https://pages.nist.gov/800-63-4/): yêu cầu về authenticator, kiểm chứng và chính sách password hiện đại.

**Điểm ghi nhớ:** Xác thực không kết thúc ở thao tác `PasswordEncoder.matches()`. Một credential chỉ an toàn khi **đúng nơi được tạo, đúng kênh được truyền, đúng bên xác minh, tồn tại đúng thời gian, được thay thế/thu hồi đúng cách và không phát sinh bản sao ngoài phạm vi tin cậy**.