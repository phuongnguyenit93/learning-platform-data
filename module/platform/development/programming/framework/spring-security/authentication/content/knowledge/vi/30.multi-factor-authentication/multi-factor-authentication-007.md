# Tích hợp TOTP hoặc HOTP: phần thư viện hỗ trợ và phần ứng dụng cần xây dựng

> **Phạm vi:** Xây dựng lớp xác thực yếu tố thứ hai dựa trên mã OTP từ ứng dụng authenticator trong hệ thống Spring Security. Trọng tâm là phân biệt **thuật toán TOTP/HOTP mà một thư viện có thể tính toán** với **vòng đời MFA, trạng thái tài khoản, quyết định cấp quyền, chống replay và quy trình vận hành mà ứng dụng phải thiết kế**. Ví dụ dùng Java 17+, Spring Boot 3.x / Spring Security 6.x cho hướng tích hợp custom; đồng thời chỉ ra khả năng MFA/one-time-token của Spring Security 7.x mà không nhầm chúng với chuẩn TOTP/HOTP.

## 1. Vì sao “đã có thư viện OTP” vẫn chưa có MFA hoàn chỉnh?

Một thư viện tính TOTP/HOTP có thể trả lời câu hỏi hẹp:

> “Với secret K, thời gian hoặc bộ đếm C và cấu hình thuật toán, chuỗi 6–8 chữ số kỳ vọng là gì?”

Hệ thống đăng nhập thật lại phải trả lời nhiều câu hỏi khác:

- Ai đã **được xác thực bằng yếu tố thứ nhất** và họ đang hoàn thành thử thách MFA của tài khoản nào?
- Secret thuộc đúng **thiết bị/factor** nào? Đã enrollment và xác nhận sở hữu chưa?
- OTP có **còn hạn, nằm trong cửa sổ cho phép và chưa dùng thành công trước đó** không?
- Có vượt số lần thử, bị khóa tạm, đang reset MFA, thiết bị đã thu hồi hoặc tài khoản đã bị khóa không?
- Khi xác minh thành công, Spring Security sẽ biểu diễn **đủ hai yếu tố** trong session / security context ra sao?
- Nếu OTP đúng nhưng database hoặc cache bị lỗi ngay lúc commit trạng thái chống replay, có được coi là đăng nhập thành công không? **Không**.
- Nếu user yêu cầu đổi thiết bị, mất authenticator, bị mất session hoặc đăng nhập ở nhiều tab, đâu là quy trình an toàn?

**Ranh giới trách nhiệm:** Thuật toán đúng là cần thiết nhưng chưa đủ. Thư viện xử lý *mật mã và phép so mã*; Spring Security cung cấp *framework xác thực và kiểm soát truy cập*; ứng dụng phải nối hai phần bằng *state machine, lưu trữ, giao dịch, chính sách và kiểm thử*. 

## 2. TOTP khác HOTP như thế nào?

| Đặc điểm | HOTP — RFC 4226 | TOTP — RFC 6238 |
| --- | --- | --- |
| Moving factor | Counter sự kiện C, tăng khi tạo/sử dụng mã | Time step T tính từ Unix time |
| Công thức | `HOTP(K,C) = Truncate(HMAC(K,C)) mod 10^Digits` | `TOTP(K,t) = HOTP(K,floor((t - T0)/X))` |
| Đồng bộ | Server phải theo dõi counter tiếp theo, có thể cần look-ahead | Server và thiết bị cần đồng hồ tương đối đồng bộ |
| Thời gian sử dụng | Không tự hết hạn theo đồng hồ; hợp lệ trong chuỗi counter chấp nhận | Thường 30 giây/step; cửa sổ trượt nhỏ để bù lệch giờ |
| Chống replay | Tiến counter đã dùng bằng cập nhật **nguyên tử** | Lưu **last accepted time step** (hoặc dữ liệu tương đương) với cập nhật nguyên tử |
| Khả năng triển khai | Device hoặc token tăng counter khi tạo mã | Phổ biến ở ứng dụng authenticator trên điện thoại |
| Tham số cần thống nhất | Secret, thuật toán HMAC, số chữ số, counter ban đầu | Secret, thuật toán HMAC, số chữ số, period X, T0 |

Cả hai sử dụng **shared secret** giữa authenticator và server; không phải mật mã bất đối xứng. Với phần lớn authenticator app, cấu hình phổ biến là **HMAC-SHA1, 6 chữ số, period 30 giây**; nhưng RFC 6238 cho phép HMAC-SHA256/512 và các cấu hình khác. Không tự đổi thuật toán hoặc số chữ số nếu thiết bị của người dùng không hỗ trợ.

**Không nhầm hai thứ:** “OTP” ở đây là mã số do authenticator tính từ secret. “One-Time Token Login” (OTT) mà Spring Security cung cấp là một cơ chế token server cấp và thường gửi bằng magic link/email/SMS; **`oneTimeTokenLogin()` không tự hiện thực TOTP/HOTP hay enrollment QR với authenticator app**.

### Vì sao một mã sáu chữ số cần kiểm soát số lần thử?

Mã 6 chữ số có khoảng một triệu khả năng. Nếu server chấp nhận 3 step TOTP đồng thời, về mặt xấp xỉ một lượt thử ngẫu nhiên có thể khớp một trong ba mã. Tăng số step, không giới hạn số lần thử và cho nhiều IP đoán cùng tài khoản sẽ làm suy yếu MFA. Vì vậy cần rate limit theo tài khoản/factor/challenge, backoff, telemetry và chính sách khóa có thể phục hồi; **không chỉ dựa vào thời gian 30 giây**.

## 3. Phần thư viện hỗ trợ và phần ứng dụng sở hữu

| Công việc | Thư viện chuẩn OTP có thể làm | Ứng dụng / Spring Security phải chịu trách nhiệm |
| --- | --- | --- |
| Sinh mã HOTP/TOTP | HMAC, dynamic truncation, zero-padding | Chọn cấu hình tương thích và test vector |
| Xác minh mã với moving factor | So mã ở counter/step chỉ định; có thể hỗ trợ validation window | Định nghĩa giới hạn cửa sổ, rate limit và commit chống replay |
| Sinh secret mới | Một số thư viện có CSPRNG helper | Secret per-factor, entropy, lưu mã hóa và vòng đời |
| Base32, `otpauth://` và QR | Có thư viện hỗ trợ mã hóa chuỗi/QR | UX enrollment, CSRF, QR chỉ hiển thị an toàn, xác nhận sở hữu |
| OTP khi đổi thiết bị | Chỉ tính/kiểm tra mã | Reauthenticate, thay factor, revoke secret cũ, audit |
| Retry, HOTP resync | Một số thư viện hỗ trợ look-ahead | Bounded look-ahead, counter transaction và chống thao túng |
| Tài khoản, session, authorization | **Không** | Spring `Authentication`, filter chain, chính sách route, step-up |
| Recovery codes và hỗ trợ mất thiết bị | Thường không | Sinh ngẫu nhiên, hash, consume once, luồng cứu hộ |
| TOTP replay trên nhiều instance | Hàm verify thuần không đủ | Store chia sẻ + atomic compare-and-set hoặc row lock |
| Nâng quyền phiên sau MFA | **Không** | Upgrade SecurityContext/phiên hoặc token với mức xác thực rõ |
| Mã hóa secret, KMS, key rotation | Thư viện OTP có thể không cung cấp | Encryption-at-rest, ACL, audit, backup/restore an toàn |
| Telemetry/incident response | **Không** | Đo failures, abuse, policy reset, khôi phục và theo dõi |

**Chọn thư viện theo hợp đồng cụ thể** chứ không chỉ theo chữ “OTP”: có hỗ trợ chuẩn RFC và test vectors, SHA1/256/512 đúng cấu hình, 6/8 digits, Base32, provision URI, window, đầu vào invalid, clock injection, kiểm soát error, lịch cập nhật/dependency và security review không? Một thư viện tự nhận “TOTP MFA” vẫn chưa thay bạn lưu pending factor, quản lý session hoặc thu hồi.

## 4. Thư viện Spring Security làm gì?

### Spring Security 6.x / Spring Boot 3.x

Spring Security cung cấp các mảnh ghép chính:

- `AuthenticationManager` và `AuthenticationProvider` cho quá trình xác thực.
- `Authentication`/`GrantedAuthority` để biểu diễn danh tính và mức được phép truy cập.
- `SecurityContextHolder` và `SecurityContextRepository` cho ngữ cảnh xác thực Servlet/phiên.
- `SecurityFilterChain`, `AuthorizationManager`, `AuthenticationEntryPoint`, success/failure handler để tạo biên bảo vệ.
- Các cơ chế `formLogin`, OAuth2 Login, LDAP hoặc các authentication mechanism khác để xử lý yếu tố thứ nhất.

**Điều Spring không tự làm thay ứng dụng custom TOTP/HOTP:** sinh và giữ secret per-user, xuất QR provision, xác nhận enrollment, kiểm tra từng time step/counter, chống mã đã dùng lại, rate limiting theo factor, recovery, reset và nâng cấp phiên sau xác minh.

Một cách tích hợp là **custom authentication provider/filter/service** cho OTP, giữ “password passed” và “MFA passed” là hai trạng thái khác nhau. Đừng thêm authority `FACTOR_TOTP` dựa trên request parameter, tên role hay tình trạng “user có bật MFA” trong DB; authority này chỉ được trao **sau khi server thực sự kiểm tra OTP và commit chống replay thành công**.

### Spring Security 7.x và tài liệu MFA mới

Các phiên bản Spring Security 7.x có khái niệm **`FactorGrantedAuthority`**, chính sách yêu cầu nhiều factor và `@EnableMultiFactorAuthentication`. Đây là cơ chế **điều phối các factor đã xác thực**, không có nghĩa Spring có một TOTP authenticator app verifier mặc định. Tài liệu mẫu thường kết hợp password với **OTT** (`FACTOR_OTT`); OTT của framework khác TOTP/HOTP theo RFC. Nếu dùng TOTP custom, phải tích hợp chứng cứ factor vào cơ chế xác thực/authorization của đúng phiên bản Spring. **Không** tự sao chép `FACTOR_OTT` để đánh dấu TOTP nếu chưa dùng chính cơ chế OTT mà framework kỳ vọng.

Spring Security 6.x và 7.x có thể khác API/dsl. Trước khi copy snippet trên internet, đọc đúng phiên bản dependency được BOM quản lý. Ví dụ Java dưới dùng API chung của Spring Security 6 Servlet, còn phần verify OTP giữ tách biệt khỏi authentication framework.

### Authentication khác MFA authorization

- **Authentication (yếu tố 1):** user đã nhập password đúng hoặc có OIDC session được IdP xác minh. Đây chưa mặc nhiên đáp ứng chính sách MFA của ứng dụng.
- **MFA challenge:** cho phép truy cập màn hình enrollment/challenge tối thiểu; chưa được truy cập tài nguyên đòi hai yếu tố.
- **MFA success:** OTP của đúng factor đã được xác nhận và chống replay atomically; sau đó mới ghi dấu chứng cứ vào session/security context.
- **Authorization:** mọi URL/API nhạy cảm cần kiểm tra đủ factor. Kiểm tra chỉ ở trang login hoặc chỉ ở menu frontend là không đủ.

Nếu login thông qua OIDC IdP đã làm MFA, ứng dụng nên ưu tiên dựa trên **`acr`/`amr` hoặc hợp đồng về mức xác thực đã được IdP xác minh** thay vì bắt người dùng cung cấp TOTP lần thứ hai không cần thiết. Không tin một `amr` string do browser tự gửi hoặc claims chưa xác minh.

## 5. Công thức và cửa sổ xác minh

Với secret `K` và counter `C`:

~~~text
H = HMAC-SHA1(K, big_endian_8_byte(C))
offset = H[last_byte] & 0x0F
binary = DT(H, offset) & 0x7FFFFFFF
HOTP = binary mod 10^digits
~~~

Dynamic truncation (DT) chọn bốn byte liên tiếp từ HMAC tại offset rồi trích 31 bit dương. Khi chuyển thành chuỗi, **zero-padding bên trái** tới 6 hoặc 8 chữ số; ví dụ `07081804` phải giữ số 0 đầu, không lưu kiểu số nguyên khiến mất định dạng.

Với TOTP:

~~~text
timeStep = floor((UnixSeconds(now) - T0) / periodSeconds)
TOTP(K, now) = HOTP(K, timeStep)
T0 = 0, periodSeconds = 30 là giá trị phổ biến theo RFC 6238
~~~

Nếu dùng 30 giây/step và policy nhận step hiện tại ±1, việc kiểm tra diễn ra tại **tối đa ba step**. Window chỉ là cơ chế chịu độ lệch clock và độ trễ truyền; không cho window tăng tùy ý. Một time step lớn hơn làm mã sống lâu hơn và tăng thời gian attacker có thể dùng lại mã bị lộ.

**Điểm then chốt của RFC 6238:** Dù mã TOTP còn trong cùng step, validator **không được chấp nhận lần thứ hai sau lần xác minh thành công đầu tiên**. Chỉ so HMAC rồi trả true không thỏa tính “one-time” khi có retry hoặc hai request đến hai node cùng lúc.

## 6. Java 17 chạy độc lập: HOTP/TOTP khớp test vector RFC

Ví dụ này chỉ tính **thuật toán mật mã**, không triển khai enrollment, lưu secret, login hoặc MFA state. Dùng JDK 17 `javax.crypto.Mac`, `ByteBuffer` và `Instant`; test secret cố định **chỉ để kiểm thử**, tuyệt đối không dùng để phát khóa cho người dùng thật.

Tệp `OtpRfcDemo.java`:

~~~java
import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.time.Instant;
import java.util.Locale;
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;

public final class OtpRfcDemo {
    private OtpRfcDemo() {
    }

    static String hotp(byte[] secret, long counter, int digits)
            throws GeneralSecurityException {
        if (secret == null || secret.length == 0 || counter < 0
                || digits < 6 || digits > 8) {
            throw new IllegalArgumentException("Invalid HOTP parameters");
        }

        byte[] message = ByteBuffer.allocate(Long.BYTES)
                .putLong(counter)
                .array();

        Mac mac = Mac.getInstance("HmacSHA1");
        mac.init(new SecretKeySpec(secret, "HmacSHA1"));
        byte[] hmac = mac.doFinal(message);

        int offset = hmac[hmac.length - 1] & 0x0f;
        int binary = ((hmac[offset] & 0x7f) << 24)
                | ((hmac[offset + 1] & 0xff) << 16)
                | ((hmac[offset + 2] & 0xff) << 8)
                | (hmac[offset + 3] & 0xff);

        int modulus = 1;
        for (int i = 0; i < digits; i++) {
            modulus *= 10;
        }
        return String.format(Locale.ROOT,
                "%0" + digits + "d", binary % modulus);
    }

    static String totp(byte[] secret, Instant time, int digits,
            int periodSeconds) throws GeneralSecurityException {
        if (periodSeconds <= 0 || time == null) {
            throw new IllegalArgumentException("Invalid TOTP parameters");
        }
        long step = Math.floorDiv(time.getEpochSecond(), periodSeconds);
        return hotp(secret, step, digits);
    }

    public static void main(String[] args)
            throws GeneralSecurityException {
        byte[] secret = "12345678901234567890"
                .getBytes(StandardCharsets.US_ASCII);

        System.out.println("HOTP C=0: " + hotp(secret, 0, 6));
        System.out.println("HOTP C=1: " + hotp(secret, 1, 6));
        System.out.println("HOTP C=2: " + hotp(secret, 2, 6));

        System.out.println("TOTP t=59: " +
                totp(secret, Instant.ofEpochSecond(59), 8, 30));
        System.out.println("TOTP t=1111111109: " +
                totp(secret, Instant.ofEpochSecond(1111111109L), 8, 30));
    }
}
~~~

Chạy với JDK 17+:

~~~bash
javac OtpRfcDemo.java
java OtpRfcDemo
~~~

Stdout chính xác theo các test vector HMAC-SHA1 của RFC 4226 / RFC 6238:

~~~text
HOTP C=0: 755224
HOTP C=1: 287082
HOTP C=2: 359152
TOTP t=59: 94287082
TOTP t=1111111109: 07081804
~~~

**Vì sao dùng 8 chữ số ở TOTP test?** RFC 6238 công bố test vectors 8 chữ số để kiểm tra thuật toán; trên authenticator thực tế cấu hình có thể là 6 chữ số. Chọn số chữ số và HMAC giống hệt cấu hình khi enrollment.

**Giới hạn của code:** Hàm `hotp/totp` chưa kiểm tra candidate code từ người dùng, không có cửa sổ lệch giờ, counter commit, chống replay hoặc account lockout. Nó là **bộ sinh code dùng kiểm thử thuật toán**, không phải một MFA verifier an toàn. Secret RFC cố định là **dữ liệu public test vector** và không được dùng cho production. Khi phát secret thật dùng CSPRNG riêng cho mỗi user/factor; khi lưu dùng mã hóa có quản lý khóa.

## 7. Trạng thái factor và data model ứng dụng phải dựng

Mỗi user có thể có một hoặc nhiều factor. Nên tách thông tin người dùng và record factor:

| Cột gợi ý | Tác dụng |
| --- | --- |
| `factor_id`, `user_id` | Factor thuộc đúng tài khoản đã được xác minh ở bước trước |
| `type` | `TOTP` hoặc `HOTP`; không hoán đổi tùy tiện |
| `status` | `PENDING`, `ACTIVE`, `DISABLED`/`REVOKED` |
| `secret_ciphertext` | **Secret mã hóa**, không plaintext hoặc chỉ hash |
| `secret_key_version` | Mã khóa KMS/KEK để đọc và rotate mã hóa |
| `algorithm`, `digits` | Ví dụ HmacSHA1, 6 hoặc 8 digits |
| `period_seconds`/`t0` | Chỉ TOTP; ví dụ 30 giây/0 |
| `last_accepted_step` | TOTP chống replay, cập nhật atomically |
| `next_counter` | HOTP quản lý counter đã tiêu thụ |
| `created_at`, `confirmed_at` | Audit enrollment |
| `revoked_at`, `revision` | Thu hồi, optimistic locking và loại trừ request stale |
| `failed_attempts`, `locked_until` | Quy tắc rate limit (có thể ở store khác) |
| `device_label` | Nhãn do user đặt, không phải bằng chứng bảo mật |

**Vì sao không hash TOTP seed?** Để kiểm tra TOTP/HOTP cho counter/step mới, server phải tính HMAC từ **secret gốc** hoặc thông qua một dịch vụ giữ/giải mã secret an toàn. Hash một chiều seed như password sẽ không đủ đầu vào cho tính toán OTP. Phải **mã hóa seed at rest** (ví dụ envelope encryption với KMS/HSM, AEAD như AES-GCM), phân quyền decrypt tối thiểu, có audit/rotation/backup và không bao giờ log seed.

Mỗi factor cần một secret riêng từ `SecureRandom`. Với HMAC-SHA1, seed 20 byte ngẫu nhiên (160 bit) là lựa chọn tương thích thường gặp; một số authenticator có quy tắc khác. Không dùng seed chia sẻ giữa nhiều user, không dùng username/email làm seed, không dùng `Random` hoặc secret cố định trong config. Kiểm tra provisioning thực tế cho các ứng dụng authenticator mục tiêu.

### QR chứa secret, không phải hình vô hại

Chuỗi provisioning thường có dạng:

~~~text
otpauth://totp/ExampleApp%3Auser%40example.test
  ?secret=BASE32_RANDOM_SECRET
  &issuer=ExampleApp
  &algorithm=SHA1
  &digits=6
  &period=30
~~~

Dòng trên **xuống dòng chỉ để trình bày**; URL thật phải nằm trên một dòng và được URL-encode đúng. Secret `BASE32_RANDOM_SECRET` là ký hiệu minh họa. Với HOTP, dùng kiểu `otpauth://hotp/...` và tham số `counter=...` thay `period`, đồng thời xác nhận app authenticator thực sự hỗ trợ HOTP.

Dùng thư viện Base32/QR đáng tin để dựng URI, URL-encode label/issuer và render QR. **QR là secret lâu dài**: chỉ hiển thị trong enrollment session qua HTTPS, `Cache-Control: no-store`, không đưa vào URL ngoài hệ thống, logs, analytics, error report, ảnh ticket hoặc log CDN. Không trả secret từ API “xem lại QR” sau khi factor active. Nếu người dùng cần thiết bị mới, thực hiện quy trình thêm/đổi factor an toàn.

## 8. Enrollment hai pha: không kích hoạt ngay khi hiện QR

Một luồng an toàn tối thiểu:

1. User đã xác thực yếu tố thứ nhất và yêu cầu thêm TOTP/HOTP. Với thay đổi phương thức bảo mật, yêu cầu **reauthentication mới** hoặc một factor hiện có theo policy; không chỉ dựa vào cookie phiên cũ.
2. Server sinh seed ngẫu nhiên **theo từng factor**, lưu mã hóa ở trạng thái `PENDING`, gắn với `user_id` từ authentication hiện tại. Sinh QR/URI tương ứng và trả qua session bảo vệ bằng TLS, no-store.
3. User quét bằng authenticator app; app hiển thị OTP. Server **chưa** coi factor này là active và chưa chấp nhận nó để vượt yêu cầu MFA.
4. User nhập mã xác nhận. Server kiểm tra OTP thuộc **đúng factor pending của user đã xác thực**, rate limit và ràng buộc phiên; áp dụng hạn enrollment.
5. Chỉ nếu xác minh mã và transaction thành công mới chuyển `PENDING -> ACTIVE`, ghi `confirmed_at`, cập nhật `last_accepted_step`/`next_counter` (vì mã vừa dùng cũng không được tái sử dụng), phát audit.
6. Cho user lấy/ghi lại bộ recovery codes qua kênh an toàn nếu policy cho phép; lưu recovery codes dưới dạng hash, chỉ xem raw một lần.
7. Thông báo sự kiện thêm factor qua kênh ngoài phiên đã thay đổi (ví dụ email thông báo), đồng thời cung cấp quy trình báo cáo không phải do attacker điều khiển.

**Không** coi việc mở trang QR là bằng chứng user đã cài app. Không cho user đặt status `ACTIVE` từ request JSON. Không cho người dùng A xác nhận secret của B bằng cách thay `userId`/`factorId` trên endpoint. Không tạo đầy đủ MFA session tự động ngay khi enrollment nếu quy tắc sản phẩm yêu cầu một challenge mới; định nghĩa rành mạch “đã thêm factor” và “đã dùng factor để nâng cấp phiên”.

Ví dụ state transitions:

~~~text
NOT_ENROLLED
    |
    | bắt đầu enrollment sau first factor + fresh reauth
    v
PENDING --(OTP đúng, transaction thành công)--> ACTIVE
    |                                         |
    +-- timeout/cancel --> DELETED             +-- lost/replace --> REVOKED
                                              |
                                              +-- factor mới -> PENDING -> ACTIVE
~~~

Thao tác xóa/đổi factor sau khi MFA bị tấn công phải có kiểm soát truy cập riêng, lịch sử và cảnh báo. Một pending factor có thể hết hạn và bị xóa mà không làm thay đổi khả năng đăng nhập qua factor active khác.

## 9. Xác minh TOTP và chống replay — không chỉ compare mã

Tại MFA challenge, server đã có user từ **yếu tố thứ nhất**; không lấy user ID theo một tham số tùy ý. Sau khi lấy các factor ACTIVE của user, giải mã seed trong vùng quyền hạn chế và chọn policy window.

**Thuật toán khái niệm**:

~~~text
authenticatedUser = firstFactorContext.principal
factor = loadActiveFactorFor(authenticatedUser)
assert not locked + allowedAttempts

stepNow = floor(Clock.now().epochSeconds / periodSeconds)
candidates = [stepNow - 1, stepNow, stepNow + 1]   # ví dụ window nhỏ

for step in candidates:
    if step < 0: continue
    if constantTimeEqual(hotp(secret, step), submittedOtp):
        BEGIN TRANSACTION
        UPDATE factor
            SET last_accepted_step = step
            WHERE factor_id = expectedFactor
              AND user_id = authenticatedUser
              AND status = ACTIVE
              AND revision = expectedRevision
              AND (last_accepted_step IS NULL OR last_accepted_step < step)
        IF exactly one row changed:
            COMMIT
            record verified MFA for this session
            return SUCCESS
        ROLLBACK
        return REPLAY_OR_STALE
return INVALID_OTP
~~~

Pseudocode trên không phải Java/SQL hoàn chỉnh. Khi cùng một giá trị số có thể trùng ở nhiều step (hiếm nhưng có thể), implementation phải định nghĩa **thứ tự chọn step và quy tắc one-time**; không được cho phép cùng một OTP tái sử dụng bằng cách thử step khác khi đã có một lần thành công. Với ứng dụng yêu cầu chặt chẽ, lưu thêm fingerprint/giá trị mã đã tiêu thụ theo thời gian cùng factor hoặc chính sách chọn step rõ ràng để ngăn collision edge case. Luồng transaction/lock phải xử lý hai request song song trên hai instance.

**Mốc thời gian:** `last_accepted_step` phải tăng đơn điệu; không chấp nhận step trước hoặc bằng step đã thành công. Cần giải quyết clock skew bằng đồng bộ NTP và window nhỏ, không mở ±10 step tùy tiện. Nếu code có 6 chữ số, luôn giữ zero-padding; chỉ nhận chuỗi có độ dài/charset đúng, không parse thành integer làm mất số 0 đầu.

**Chống brute force:** rate limit theo account + factor + challenge/session, có thêm IP/device signal và alert. Không khóa vĩnh viễn một tài khoản chỉ vì attacker cố ý spam 6 chữ số; cơ chế delay/lockout phải cân nhắc DoS và recovery. Khi backend không đọc/ghi state chống replay được, **không** đánh dấu MFA thành công.

## 10. HOTP verification: counter và resynchronization

HOTP không phụ thuộc Unix time. Server lưu `next_counter` (counter tiếp theo được chấp nhận), xác minh trong cửa sổ counter hữu hạn, ví dụ `[nextCounter, nextCounter+5]` theo policy.

Nếu user nhấn generate nhiều lần trên token trước khi nhập vào ứng dụng, counter ở device có thể đi trước server. Look-ahead giúp resync, nhưng cửa sổ lớn mở rộng khả năng đoán và phải có rate limit.

~~~text
expectedStart = factor.next_counter

for counter in [expectedStart .. expectedStart + allowedLookAhead]:
    if constantTimeEqual(hotp(secret, counter), submittedOtp):
        BEGIN TRANSACTION
        UPDATE factor
          SET next_counter = counter + 1
          WHERE factor_id = thisFactor
            AND status = ACTIVE
            AND next_counter = expectedStart
        IF exactly one row:
            COMMIT
            return SUCCESS
        ROLLBACK
        return CONCURRENT_OR_REPLAY
return INVALID_OTP
~~~

**Không tăng counter một cách vô điều kiện khi mã sai**; có thể làm lệch device/server vô hạn hoặc tạo DoS. Với resynchronization quá lớn, áp dụng quy trình mạnh hơn (một số hệ yêu cầu hai mã liên tiếp, kiểm tra sở hữu và audit), không mở cửa sổ vô hạn. Mọi cập nhật counter phải atomically commit trên kho chia sẻ; cập nhật biến trong RAM của một pod là chưa đủ.

Một lần HOTP hợp lệ tại counter C khiến lần thử tiếp theo chỉ được dùng counter **lớn hơn C**, và token cũ không được replay. Như với TOTP, khi nhận mã đúng mà commit next counter thất bại thì **không** nâng cấp session.

## 11. Ràng buộc MFA vào Spring Security Servlet

Ví dụ dưới minh họa **biên authorization**: sau bước username/password, user chỉ được vào màn hình MFA; mọi route khác yêu cầu một authority custom `FACTOR_TOTP`. Tên này do ứng dụng định nghĩa cho **Spring Security 6.x**, không phải tự động được Spring cấp. Nếu dùng HOTP, tên factor có thể là `FACTOR_HOTP` hoặc một marker chính sách đã được thiết kế; không hardcode một marker mà user tự yêu cầu.

Tệp `MfaBoundaryConfig.java` — mảnh cấu hình của ứng dụng Spring Boot đã có các dependency bảo mật cần thiết:

~~~java
package example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class MfaBoundaryConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/login", "/error", "/assets/**")
                        .permitAll()
                        .requestMatchers("/mfa/challenge",
                                "/mfa/verify",
                                "/mfa/enroll/**")
                        .authenticated()
                        .anyRequest()
                        .hasAuthority("FACTOR_TOTP"))
                .formLogin(form -> form
                        .successHandler((request, response, authentication) ->
                                response.sendRedirect(
                                        request.getContextPath() + "/mfa/challenge")))
                .build();
    }
}
~~~

Với HTTP request thực tế, filter chain phải có login form/user store và MVC endpoints `/mfa/challenge`, `/mfa/verify`, `/mfa/enroll/**` do ứng dụng xây. Chúng **không** được tự cung cấp bởi đoạn cấu hình. Handler thành công của form chỉ đưa user tới challenge, không cấp `FACTOR_TOTP`.

**Đặc biệt quan trọng:** `.authenticated()` trên các endpoint `/mfa/**` chỉ chứng minh user đã qua first factor theo cơ chế hiện tại; các thao tác **đăng ký/thay/thu hồi** factor yêu cầu **fresh reauthentication và chính sách mạnh hơn**, kiểm tra CSRF cho POST và ownership, không cho bất kỳ first-factor-only session cũ nào thay seed. Nếu có endpoints công khai cần truy cập trước MFA, phải liệt kê rõ và đánh giá rủi ro thay vì thêm `.anyRequest().authenticated()` phía sau, vì điều đó có thể làm lộ API nhạy cảm chỉ cần mật khẩu.

Sau khi OTP được xác minh thành công **và atomic anti-replay state đã commit**, ứng dụng phải:

1. Xác định user/factor từ ngữ cảnh first factor và kho dữ liệu tin cậy, không theo user ID được gửi trong form.
2. Tạo hoặc cập nhật chứng cứ MFA của **đúng phiên** (ví dụ custom Authentication đã xác minh với authority `FACTOR_TOTP`); không giả `isAuthenticated=true` theo tham số `otpVerified`.
3. Ghi `SecurityContext` bằng cơ chế persistence phù hợp (như `SecurityContextRepository.saveContext` trên Servlet), kiểm tra session fixation protection và tính hết hạn của bằng chứng MFA.
4. Redirect an toàn tới saved request **sau khi** đã có đầy đủ factor; không dùng external redirect URL từ client.
5. Giữ đủ logs/audit để chứng minh challenge thành công, nhưng không ghi OTP, seed hoặc token session.

Đoạn mã xác nhận OTP/phát authority không được trình bày như một mảnh “cứ paste là chạy”: nó bắt buộc phụ thuộc transaction store, factor policy, challenge session và bảo mật của ứng dụng. Trong Spring Security 7, nếu dùng `FactorGrantedAuthority` và chính sách MFA tích hợp, hãy tích hợp TOTP/HOTP đã kiểm chứng như một factor theo contract của phiên bản đó thay vì tạo marker có ngữ nghĩa lệch.

### Vì sao không chỉ dùng biến session `mfa=true`?

Một attribute tự set có thể bỏ qua ngữ cảnh Spring, không rõ thời hạn/scope và có nguy cơ bị khôi phục từ session cũ. Nếu chọn session state, phải kiểm tra với authorization manager ở mọi route, gắn đúng user, timestamp, factor type, challenge ID, session ID và phiên bản trạng thái factor; chính sách hủy khi logout, đổi mật khẩu, reset MFA hoặc factor bị thu hồi. Markers/authorities trong Spring cũng cần các kiểm soát đó, không chỉ một cờ boolean.

## 12. Phân loại lỗi và tránh tạo đường vòng

| Tình huống | Quyết định an toàn | Ghi chú |
| --- | --- | --- |
| Chưa qua first factor | Không vào MFA verify hoặc protected resource | Dẫn về luồng đăng nhập thích hợp |
| OTP thiếu/sai định dạng/sai mã | Không nâng MFA, trả thông báo chung | Log mã loại lỗi, không log OTP |
| Mã TOTP đúng nhưng đã được tiêu thụ trong step trước | Reject replay | Không mở rộng window để “chữa” |
| HOTP đúng mã nhưng cập nhật counter mất race | Reject hoặc challenge lại theo policy | Không coi là success khi transaction fail |
| User chưa enrollment hoặc factor revoked | Không nâng MFA | Có luồng thiết lập/khôi phục riêng |
| Rate limit vượt ngưỡng | Trả 429 hoặc backoff phù hợp | Hạn chế brute-force và DoS |
| DB/KMS/secret store unavailable | Lỗi dịch vụ, fail closed | Không biến outage thành OTP sai và không bỏ qua MFA |
| Password đúng, OTP sai | Chỉ first factor thành công | Tuyệt đối không cấp quyền protected resource |
| OTP đúng nhưng session first factor đã đổi user/logout | Reject, không ghép chứng cứ của hai user | Gắn challenge vào session/principal/version |
| Đã qua MFA nhưng thiếu `ROLE_ADMIN` | 403, không gán quyền admin | MFA != business authorization |

**Đừng bao giờ có fallback “MFA service lỗi thì cho qua để đảm bảo uptime”.** Nếu yêu cầu MFA, mất khả năng xác minh/ghi chống replay đồng nghĩa không thể hoàn thành yêu cầu. Tùy môi trường, lỗi hạ tầng có thể được báo 503, còn mã sai nhận phản hồi chung, nhưng cả hai đều không làm phát session đầy đủ.

## 13. Recovery, reset và đổi thiết bị — phần ứng dụng tự xây

Khi mất điện thoại/token HOTP, người dùng cần quy trình khôi phục. Đây là điểm dễ bị attacker lợi dụng hơn cả thuật toán OTP.

**Recovery codes** nên được tạo độc lập bằng CSPRNG, đủ entropy, chỉ hiển thị một lần; trong DB lưu **hash có salt/KDF phù hợp với dạng secret** và trạng thái `unused/used`. Khi một code được dùng, **consume atomically** để không thể tái sử dụng trên hai instance. Các mã recovery thường có mức entropy thấp hơn token API 256-bit, nên phải áp dụng rate limit, hashing phù hợp, giữ bí mật như mật khẩu và không log.

**Đổi/thêm factor:** Yêu cầu reauthentication gần đây bằng yếu tố độc lập, hoặc một factor đã enrollment theo policy. Khi đổi điện thoại, không xóa factor cũ ngay nếu chưa xác minh thiết bị mới và chính sách yêu cầu continuity; nhưng khi báo lộ thiết bị cũ, phải revoke ngay rồi khôi phục bằng quy trình xác minh mạnh. Gửi thông báo ngoài phiên đang thay đổi và xem xét delay/challenge bổ sung khi rủi ro cao.

**Quên cả mật khẩu và MFA:** Một email recovery không được bảo vệ đúng có thể trở thành yếu tố duy nhất để takeover; thiết kế threat model, quy trình hỗ trợ có kiểm tra danh tính, logging, cảnh báo và giới hạn tần suất. Không hiển thị seed cũ qua chức năng “xem lại” hoặc cho support đọc seed plaintext.

**Session hiện có:** Reset MFA có thể đòi hủy các full-MFA session trước đó hoặc bắt step-up lại, tùy chính sách. Khi xóa factor, mọi session có chứng cứ factor đó phải được đánh giá lại; nếu chỉ lưu `FACTOR_TOTP` vô thời hạn trong session, người dùng vẫn có thể truy cập sau khi thiết bị đã revoke. Dùng factor revision, auth-time/expiry hoặc event invalidation nếu cần chính sách thu hồi nhanh.

## 14. Threat model: TOTP/HOTP có chống phishing không?

TOTP/HOTP tăng khó khăn khi attacker **chỉ** biết password, nhưng vẫn có thể bị:

- **Phishing realtime / reverse proxy:** attacker lừa user nhập OTP hiện tại rồi dùng ngay trong cửa sổ hợp lệ.
- **Malware / screen capture** lấy OTP hoặc QR enrollment chứa seed.
- **SIM/social recovery attack** nếu luồng cứu hộ yếu và dùng kênh phục hồi kém tin cậy.
- **Brute-force online** nếu không giới hạn lần thử và mở window quá lớn.
- **Session hijack** sau khi user đã hoàn thành MFA: attacker dùng cookie/session, không cần biết OTP mới.
- **Replay/race đa node** nếu chỉ so mã thuần mà không commit trạng thái.
- **Seed compromise** nếu DB lưu plaintext hoặc KMS key/secret management bị chiếm.

**Không coi TOTP là phishing-resistant.** Khi cần mức bảo vệ chống phishing mạnh, xem xét FIDO2/WebAuthn/passkeys hoặc phương thức xác thực gắn nguồn gốc (origin-bound), theo chính sách doanh nghiệp. Nếu doanh nghiệp dùng IdP OIDC đã có MFA, nên đánh giá việc dùng `acr`/`amr` đã xác minh thay vì tự triển khai một luồng MFA tại từng microservice.

## 15. Kiểm thử bắt buộc: thuật toán khác giao dịch và ứng dụng

### A. Unit test thuật toán / thư viện

- RFC 4226 test vector: C=0/1/2 cho 6 chữ số trả `755224`/`287082`/`359152`.
- RFC 6238 test vector SHA1/30s/8 digits: t=59 trả `94287082`, t=1111111109 trả `07081804`.
- Các giá trị có số 0 ở đầu giữ nguyên 6/8 digits.
- Mã âm/chuỗi rỗng/ký tự khác chữ số, sai period/digits/algorithm bị từ chối; seed null và time ngoài phạm vi không được làm ứng dụng cấp quyền.
- Kiểm tra SHA256/512 nếu cấu hình dùng chúng và thư viện thực tế hỗ trợ; test provisioning với đúng authenticator app.

### B. State và concurrency

- Enrollment chưa confirmed vẫn PENDING; OTP đúng sau commit mới ACTIVE; mã confirmation không được tái dùng.
- OTP đúng cho user A không thể xác minh challenge thuộc user B, session bị thay đổi hoặc factor version cũ.
- Hai request cùng TOTP/cùng step đến hai node: chỉ **một** transaction cập nhật `last_accepted_step` thành công.
- HOTP lookahead thành công cập nhật `next_counter=matched+1`; mã cũ bị từ chối; hai request cùng counter không cùng thành công.
- Đồng hồ lệch ±1 step theo policy có thể nhận; quá window bị từ chối; đừng mặc định mở ±10 step.
- Rate limit theo account/factor/challenge hoạt động xuyên instance; account không bị khóa vĩnh viễn do một IP spam.
- Seed encrypted-at-rest, DB dump không lộ plaintext; QR không vào log, cache, referrer hoặc analytics.
- KMS/DB outage: không có false MFA success, không cấp role hay session; audit rõ loại lỗi.

### C. Integration test Spring Security

| Kịch bản | Kỳ vọng |
| --- | --- |
| Chưa đăng nhập, vào resource protected | Yêu cầu first-factor authentication |
| Password đúng, chưa TOTP | Chỉ được vào challenge/enrollment hợp lệ, protected route bị chặn |
| Password đúng, TOTP đúng, state commit thành công | Session có chứng cứ factor thứ hai và truy cập đúng quyền |
| OTP sai hoặc replay cùng 30-second step | Không nâng cấp phiên |
| OTP đúng cho user khác hoặc challenge session khác | Không nâng MFA |
| User đủ MFA nhưng thiếu business role | 403 với resource yêu cầu role |
| Đổi factor, logout, session expires | State MFA cũ mất hiệu lực theo policy |
| Reset/revoke factor khi session cũ đang mở | Session phải bị đánh giá lại theo yêu cầu revocation |
| Failed attempts quá ngưỡng | Rate limit/backoff/lockout theo policy |
| Store outage giữa OTP match và CAS update | Không có authenticated full-MFA state |
| Đăng nhập bằng OIDC/passkey/remember-me ngoài password flow | Không lách requirement, factor evidence đúng nguồn |

Với ứng dụng Servlet, dùng `MockMvc` và test với session/cookie thật theo khả năng. Với WebFlux, dùng `WebTestClient` và `ReactiveSecurityContextHolder`, tránh blocking KMS/DB trong event loop. Test trạng thái của request/authorization, không chỉ unit test hàm `totp(...)`.

## 16. Mẫu kiến trúc triển khai

Có thể tách bốn lớp:

~~~text
HTTP Controller / Security FilterChain
         |
         v
MfaChallengeService  [bound principal, challenge, attempts]
         |
         +-- FactorRepository [owner, status, revision, lastStep/counter]
         |
         +-- SecretProtector   [KMS, AEAD decrypt/encrypt]
         |
         +-- OtpAlgorithm      [HOTP/TOTP generate/verify]
         |
         v
Transaction: compare-and-set anti-replay
         |
         v
MfaSessionUpgrader  [trusted factor proof + context persistence]
         |
         v
AuthorizationManager [đòi đủ factor + business permission]
~~~

Lớp `OtpAlgorithm` nên là **pure function** có clock được inject để test; mọi state thay đổi nằm ở `FactorRepository` hoặc transaction service. `MfaChallengeService` quyết định user/attempt policy; `MfaSessionUpgrader` chỉ được gọi từ đường thành công đã commit. Lớp mã hóa bảo đảm không làm lộ seed qua DTO, logs, toString hoặc exception.

Một phép kiểm chứng thành công nhưng mất network khi commit là trạng thái **không xác định** ở phía client; hệ thống phải dùng idempotency/challenge ID, đọc lại transaction state hoặc yêu cầu mã tiếp theo theo policy, không “chấp nhận tạm” do mã trước đó đúng.

## 17. Những lỗi phổ biến và cách sửa

| Sai lầm | Vì sao sai | Hướng xử lý |
| --- | --- | --- |
| Gọi `oneTimeTokenLogin()` và nghĩ đã có Google Authenticator TOTP | OTT framework khác TOTP/HOTP | Dùng thư viện OTP + custom factor flow |
| Secret TOTP chỉ lưu hash một chiều | Không có secret gốc để tính HMAC counter mới | Mã hóa seed và quản lý key |
| Hiển thị QR rồi đánh dấu factor active | User có thể chưa sở hữu authenticator | PENDING rồi xác nhận OTP và commit |
| So OTP rồi cấp full session, không lưu last step | Cùng OTP dùng lại nhiều lần | CAS/transaction atomic anti-replay |
| HOTP verify mà không tăng server counter | Replay mã cũ | Commit next_counter atomically |
| Cho window ±10 steps để “đỡ lỗi” | Mở rộng bề mặt brute-force | Đồng bộ thời gian, cửa sổ nhỏ |
| OTP 6 chữ số nhưng không rate limit | Dễ đoán mã khi spam | Phối hợp account/factor/IP/session rate limits |
| Nhận `userId`/`otpVerified` từ request để cấp MFA | Vượt quyền hoặc ghép factor khác user | Gắn challenge với first-factor principal |
| Chỉ kiểm tra MFA ở login page, không kiểm tra API | Endpoint khác có thể bị bypass | Require factor ở authorization layer |
| Cấp `FACTOR_TOTP` trước khi transaction chống replay thành công | Replay/race có thể nâng phiên | Chỉ ghi trusted evidence sau commit |
| Xem recovery email là “bỏ qua mọi kiểm tra” | Đường takeover tài khoản | Recovery riêng, reauth, audit, rate limit |
| Không vô hiệu session sau reset/revoke factor | Quyền MFA cũ tồn tại | Factor revision, session invalidation/reauth |
| Log raw OTP, seed, URI `otpauth://` hoặc QR | Lộ secret/mã | Redaction, no-store, quyền truy cập tối thiểu |
| Nghĩ OTP chống phishing realtime | Attacker có thể relay OTP trong vài giây | Ưu tiên WebAuthn/passkeys khi phù hợp |

## 18. Checklist trước production

- [ ] Chọn TOTP hay HOTP theo khả năng device và nhu cầu; xác minh đúng RFC/thuật toán/digits/period.
- [ ] Thư viện OTP được kiểm tra dependency, test vector, window và hành vi input lỗi; không tự tin chỉ vì một mã demo.
- [ ] Sinh seed per-factor qua CSPRNG, lưu mã hóa và giữ khóa trong KMS/HSM/secret manager với audit.
- [ ] Enrollment yêu cầu first factor + fresh reauth; PENDING -> ACTIVE chỉ sau OTP confirmation có transaction.
- [ ] QR/`otpauth://` chứa secret không lọt vào log, browser history, analytics hoặc cache.
- [ ] TOTP có chống replay bằng last-accepted-step/collision policy; HOTP có next-counter và look-ahead hữu hạn.
- [ ] Rate limit, anti-automation và lockout/recovery được thiết kế chống brute force lẫn DoS.
- [ ] Spring Security chỉ cấp chứng cứ `FACTOR_TOTP`/factor tương ứng **sau** verify và commit; các resource đều kiểm tra requirement.
- [ ] Session sau MFA có thời hạn/reauth policy, session fixation protection, logout và vô hiệu bằng chứng khi reset factor.
- [ ] Recovery codes được tạo/lưu/tiêu thụ an toàn; đổi thiết bị có reauth, cảnh báo và audit.
- [ ] Xác minh các nhánh đăng nhập OIDC, password, remember-me, API token và WebFlux không bypass MFA.
- [ ] Test hai node xác nhận cùng một OTP, cửa sổ thời gian, counter, lỗi DB/KMS, đổi factor và phiên cũ.
- [ ] Phân biệt OTP của authenticator với OTT/magic link của Spring; ưu tiên phishing-resistant MFA khi cần rủi ro cao.

**Kết luận:** Thuật toán RFC cho bạn **một phép tính OTP**, Spring Security cho bạn **khung xác thực và quyết định quyền**, còn ứng dụng phải thực hiện **enrollment, secret management, chống replay, rate limit, session upgrade, recovery và thu hồi factor**. TOTP/HOTP chỉ trở thành một yếu tố MFA có giá trị khi toàn bộ những phần đó được nối với nhau an toàn và được kiểm thử end-to-end.

## Tài liệu chuẩn để đối chiếu

- [RFC 4226 — HOTP: HMAC-Based One-Time Password Algorithm](https://www.rfc-editor.org/rfc/rfc4226)
- [RFC 6238 — TOTP: Time-Based One-Time Password Algorithm](https://www.rfc-editor.org/rfc/rfc6238)
- [OWASP — Multifactor Authentication Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Multifactor_Authentication_Cheat_Sheet.html)
- [Spring Security 7.x — Multi-Factor Authentication](https://docs.spring.io/spring-security/reference/servlet/authentication/mfa.html)
- [Spring Security — One-Time Token Login và phân biệt OTP/OTT](https://docs.spring.io/spring-security/reference/servlet/authentication/onetimetoken.html)
- [Spring Security — Servlet Authentication Architecture](https://docs.spring.io/spring-security/reference/servlet/authentication/architecture.html)
- [Java SE 17 — javax.crypto.Mac](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/crypto/Mac.html)
