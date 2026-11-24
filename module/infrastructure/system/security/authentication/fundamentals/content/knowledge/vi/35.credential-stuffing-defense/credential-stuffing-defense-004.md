# Dictionary attack — Tấn công đoán mật khẩu bằng từ điển

> **Chương:** Chống đoán credential  
> **Chủ đề:** Dictionary attack  
> **Phạm vi:** Bài học thuộc module SECURITY_AUTHENTICATION_FUNDAMENTALS, tìm hiểu nguyên lý xác thực danh tính từ credential, mật khẩu, MFA, passkey và chứng chỉ đến token, phiên, liên kết danh tính và khôi phục tài khoản. Bài này phân tích cách attacker dùng danh sách mật khẩu và quy tắc biến đổi để đoán credential, phân biệt dictionary attack trực tuyến với cracking offline, và thiết kế phòng vệ theo nhiều lớp.

## 1. Dictionary attack là gì?

**Dictionary attack (tấn công từ điển)** là kỹ thuật thử các mật khẩu ứng viên lấy từ danh sách từ, cụm từ, mẫu phổ biến hoặc dữ liệu đã biết thay vì thử mọi chuỗi ký tự có thể. Attacker thường bắt đầu từ các mật khẩu phổ biến, biến thể có quy tắc hoặc từ ngữ gắn với người/tổ chức mục tiêu.

Ví dụ, một người dùng đặt mật khẩu theo tên đội bóng yêu thích cộng năm hiện tại. Attacker có thể thử các biến thể phổ biến của cụm từ đó. Với nhiều account, attacker có thể dùng một tập từ điển gồm mật khẩu phổ biến, các biến thể chữ hoa/chữ thường, số và ký tự thêm vào cuối.

Dictionary attack có thể diễn ra theo hai bối cảnh khác nhau:

- **Online dictionary attack:** gửi các lần đăng nhập tới dịch vụ thật và nhận phản hồi thành công/thất bại. Dịch vụ có thể áp dụng rate limit, MFA, phát hiện bot và giám sát.
- **Offline dictionary attack:** attacker đã lấy được password hash hoặc verifier database rồi thử đoán mật khẩu trên hạ tầng của mình. Khi đó, rate limit của trang đăng nhập không còn bảo vệ được hash bị đánh cắp; salt và password-hashing function tốn tài nguyên trở thành lớp phòng vệ quan trọng.

Dictionary attack khai thác việc người dùng chọn mật khẩu có cấu trúc dễ dự đoán. Nó không cần thử toàn bộ không gian mật khẩu nếu một phần lớn người dùng dùng các mẫu quen thuộc.

### Mục tiêu học tập

Sau bài này, người học có thể:

1. Giải thích dictionary attack và cách tạo tập mật khẩu ứng viên.
2. Phân biệt dictionary attack với brute force, password spraying và credential stuffing.
3. Phân biệt tấn công online với cracking offline sau khi lộ password hash.
4. Thiết kế password policy và breached-password blocklist để giảm mật khẩu dễ đoán.
5. Chọn password-hashing function, salt, parameters và pepper phù hợp.
6. Áp dụng rate limit và phát hiện abuse mà không tạo account-lockout DoS.
7. Kết hợp MFA, passkey và password manager để giảm tác động đoán password.
8. Xây dựng telemetry, incident response và test cho dictionary attack.

## 2. Attacker xây dựng password dictionary như thế nào?

Danh sách từ điển có thể được tạo từ nhiều nguồn:
- danh sách mật khẩu phổ biến và mật khẩu mặc định;
- các cụm từ thường gặp, câu trích dẫn, tên đội thể thao, địa danh hoặc nhân vật nổi tiếng;
- các password đã bị lộ trong những vụ rò rỉ trước đây;
- từ/cụm từ liên quan tới tổ chức, sản phẩm, mùa vụ hoặc sự kiện;
- mẫu password do người dùng thường tạo, chẳng hạn từ + số, tên + năm hoặc chuỗi bàn phím;
- các biến thể theo quy tắc: đổi chữ thành số, thêm ký tự ở cuối, viết hoa ký tự đầu hoặc đảo thứ tự.

Ví dụ minh họa một mật khẩu yếu có thể được tạo từ một cụm từ dễ nhớ cộng năm hoặc dấu câu. Khi một mẫu đã phổ biến, việc thêm một ký tự đơn giản ở cuối không làm nó trở nên khó đoán đáng kể.

Không nên coi việc bắt người dùng thêm một chữ hoa, một số và một dấu chấm than là biện pháp đủ mạnh. Nếu mọi người đều tuân theo cùng một quy tắc, attacker có thể áp dụng đúng quy tắc đó để mở rộng danh sách ứng viên.

## 3. Dictionary attack khác các kiểu đoán credential khác thế nào?

Các kỹ thuật có thể dùng chung wordlist nhưng khác cách phân phối mục tiêu và nguồn dữ liệu.

| Kỹ thuật | Cách hoạt động | Dấu hiệu thường gặp |
| --- | --- | --- |
| **Dictionary attack** | Thử mật khẩu ứng viên từ wordlist và biến thể | Nhiều candidate có cấu trúc từ/cụm từ phổ biến. |
| **Brute force** | Thử các tổ hợp trong một không gian ký tự | Số lượng candidate tăng theo độ dài và bảng ký tự. |
| **Password spraying** | Thử một số password phổ biến trên nhiều account | Một password/candidate xuất hiện trên nhiều account trong cùng khoảng thời gian. |
| **Credential stuffing** | Dùng cặp username/password đã lộ từ dịch vụ khác | Nhiều cặp credential thực tế được thử lại trên dịch vụ đích. |
| **Offline hash cracking** | Thử candidate cục bộ để tìm password khớp hash | Không tạo request đăng nhập tới hệ thống nạn nhân. |

Một cuộc tấn công có thể kết hợp nhiều kỹ thuật. Ví dụ attacker có thể dùng danh sách password phổ biến để spraying, sau đó dùng cặp username/password đã lộ để stuffing. Vì vậy, telemetry nên phân tích cả account, IP/network, thiết bị, candidate pattern và thời gian.

## 4. Online dictionary attack

Trong online attack, mỗi candidate được gửi tới endpoint đăng nhập hoặc giao thức xác thực. Dịch vụ có thể quan sát request và áp dụng kiểm soát.

Rủi ro phụ thuộc vào:
- số lần thử được phép;
- độ trễ và chi phí xử lý password;
- khả năng phân tán request qua proxy, botnet hoặc nhiều thiết bị;
- việc endpoint có tiết lộ account tồn tại hay không;
- MFA có bắt buộc và được triển khai đúng không;
- việc dịch vụ có phát hiện password spraying/credential stuffing hay không.

Một giới hạn chỉ theo địa chỉ IP thường không đủ. Nhiều người dùng có thể chung một NAT; attacker cũng có thể thay đổi IP. Cần kết hợp rate limit theo account, network, device/session signals và toàn hệ thống.

## 5. Offline dictionary attack

Offline cracking thường bắt đầu khi attacker lấy được password hash từ database backup, application server, source repository hoặc một bản dump bị lộ. Attacker có thể thử candidate mà không tương tác với dịch vụ đăng nhập.

Mức độ khó phụ thuộc:
- password entropy thực tế và khả năng dự đoán;
- thuật toán hash;
- salt riêng cho từng password;
- parameters/work factor;
- pepper nếu được dùng đúng cách và lưu tách biệt;
- tốc độ phần cứng attacker có thể huy động.

Nếu hệ thống lưu `SHA-256(password)` đơn thuần, attacker có thể thử candidate rất nhanh. Password hashing cần được thiết kế chuyên biệt để làm mỗi lần đoán tốn CPU/RAM/thời gian hơn.

**Rate limit ở login endpoint không ngăn offline cracking** khi attacker đã có hash. Ngược lại, Argon2id không ngăn attacker gửi hàng nghìn request online nếu endpoint không có rate limit. Hai bối cảnh cần lớp phòng vệ khác nhau.

## 6. Vì sao mật khẩu theo mẫu dễ đoán?

Người dùng thường chọn password để dễ nhớ. Những lựa chọn có vẻ phức tạp như từ quen thuộc cộng năm, ký tự đặc biệt hoặc thay chữ bằng số vẫn có thể thuộc những mẫu rất phổ biến.

Các nguyên nhân:
- reuse một password ở nhiều dịch vụ;
- dùng tên, ngày tháng, đội thể thao hoặc từ liên quan cá nhân;
- thêm số tăng dần khi password hết hạn;
- tuân theo một quy tắc thành phần phổ biến;
- dùng password mặc định hoặc không đổi password ban đầu;
- chọn password ngắn vì khó nhớ chuỗi dài;
- không dùng password manager hoặc passkey.

Độ dài và tính khó đoán quan trọng hơn việc áp đặt một tổ hợp ký tự hình thức. Một passphrase dài, riêng biệt và không xuất hiện trong danh sách phổ biến thường khó đoán hơn một chuỗi ngắn được biến đổi theo mẫu quen thuộc.

## 7. Chặn mật khẩu phổ biến và đã bị lộ

Khi người dùng tạo hoặc đổi password, hệ thống nên kiểm tra password có nằm trong danh sách mật khẩu phổ biến, mặc định hoặc đã bị lộ hay không.

Một breached-password check cần:
- dùng nguồn dữ liệu đáng tin cậy và cập nhật;
- không gửi password plaintext tới dịch vụ bên thứ ba nếu không có thiết kế bảo vệ phù hợp;
- cân nhắc k-anonymity hoặc phương thức tra cứu bảo vệ riêng tư khi dùng dịch vụ bên ngoài;
- không lưu password người dùng nhập vào telemetry;
- thông báo rõ password không được chấp nhận và gợi ý chọn passphrase riêng;
- có quy trình xử lý false positive và khả năng dịch vụ kiểm tra tạm thời unavailable.

Không nên chỉ kiểm tra danh sách nhỏ các password phổ biến được hardcode rồi cho rằng đã chặn dictionary attack. Nguồn từ điển thay đổi theo thời gian và khác nhau giữa ngôn ngữ, khu vực, tổ chức.

### Khi nào kiểm tra?

- **Enrollment:** kiểm tra password mới trước khi lưu verifier.
- **Password change:** kiểm tra password mới và tránh tái sử dụng gần đây theo policy.
- **Recovery/reset:** áp dụng cùng policy như enrollment.
- **Existing accounts:** có thể phát hiện password yếu qua kiểm tra an toàn sau khi người dùng xác thực thành công, hoặc qua kiểm tra offline được thiết kế bảo vệ dữ liệu.

Không thể kiểm tra password plaintext của toàn bộ người dùng bằng cách giải mã database; password hash không được thiết kế để giải mã ngược.

## 8. Password hashing: giảm tốc độ đoán offline

Password phải được lưu dưới dạng verifier tạo bởi password-hashing function phù hợp, không lưu plaintext và không dùng hash nhanh tổng quát đơn thuần.

Các lựa chọn thường gặp:
- **Argon2id:** password hashing có memory-hard design, cho phép điều chỉnh memory, iterations và parallelism.
- **scrypt:** memory-hard password-based key derivation.
- **bcrypt:** password hashing phổ biến, có cost factor; cần chú ý giới hạn độ dài đầu vào và cách triển khai.
- **PBKDF2:** password-based key derivation với số vòng lặp; có thể cần thiết trong môi trường yêu cầu tương thích hoặc tiêu chuẩn cụ thể.

Hãy chọn theo khuyến nghị bảo mật hiện hành, thư viện được duy trì và khả năng vận hành. Không tự xây dựng thuật toán hash.

### Salt

Mỗi password verifier cần salt ngẫu nhiên, riêng biệt. Salt không cần giữ bí mật; nó làm cho cùng một password không tạo ra cùng verifier ở các account khác nhau và khiến precomputed rainbow table khó tái sử dụng.

### Work factor

Parameters phải được benchmark trên phần cứng production:
- quá thấp: attacker có thể thử candidate offline nhanh hơn;
- quá cao: login hợp lệ tiêu tốn tài nguyên quá lớn và có thể tạo DoS;
- cần có capacity planning, rate limit và nâng parameters theo vòng đời.

Ví dụ cấu trúc minh họa:

~~~text
$argon2id$v=19$m=65536,t=3,p=1$<salt>$<derived-hash>
~~~

Thông số trong ví dụ không phải giá trị mặc định phù hợp cho mọi hệ thống. Benchmark và policy sẽ xác định parameters thực tế.

## 9. Pepper và bảo vệ password verifier database

**Pepper** là secret bổ sung có thể kết hợp với password hashing để giảm khả năng offline cracking khi chỉ database bị lộ. Pepper phải được lưu tách biệt khỏi password database, ví dụ trong secret manager hoặc HSM.

Cần lưu ý:
- pepper không thay thế salt;
- pepper không thay thế password-hashing function chậm;
- nếu cả database và pepper cùng bị lộ, lợi ích giảm mạnh;
- rotation cần thiết kế trước vì thay pepper có thể yêu cầu rehash khi người dùng đăng nhập hoặc reset password;
- không hardcode pepper trong source code hoặc cùng database chứa verifier;
- quyền truy cập pepper cần least privilege và audit.

Pepper có thể là một lớp phòng vệ bổ sung, nhưng không nên làm hệ thống không thể xác minh password khi secret manager tạm thời unavailable mà không có kế hoạch availability rõ ràng.

## 10. Password policy chống dictionary attack

Một policy tốt nên giảm password dễ đoán mà vẫn giúp người dùng tạo và quản lý credential an toàn.

Khuyến nghị:
- yêu cầu password đủ dài theo loại account và risk;
- hỗ trợ passphrase và password manager;
- chặn password phổ biến, mặc định và đã bị lộ;
- không áp đặt các quy tắc thành phần cứng nhắc nếu chúng tạo mẫu dễ đoán;
- không bắt đổi password định kỳ vô cớ; đổi khi có bằng chứng compromise hoặc policy yêu cầu;
- cho phép paste và autofill;
- không cắt ngắn password âm thầm;
- định nghĩa rõ Unicode normalization và giới hạn byte;
- khuyến khích password duy nhất cho mỗi dịch vụ;
- ưu tiên passkey hoặc phương thức chống phishing khi có thể.

Không đưa gợi ý password quá cụ thể ngay trong lỗi đăng nhập, vì attacker có thể dùng phản hồi để tinh chỉnh dictionary. Gợi ý chọn passphrase nên xuất hiện ở enrollment/reset.

## 11. Rate limiting cho online guessing

Rate limiting làm chậm attacker và bảo vệ verifier khỏi bị quá tải. Không có một ngưỡng duy nhất phù hợp cho mọi account, network và credential type.

Có thể kết hợp:
- per-account throttling;
- per-IP/network throttling;
- global capacity limit;
- progressive delay/cooldown;
- device/session risk signals;
- rate limit cho OTP và recovery;
- giới hạn gửi email/SMS/push;
- adaptive challenge hoặc bot detection;
- alert khi một candidate xuất hiện trên nhiều account.

Tránh hard lock account chỉ sau vài lần sai. Attacker có thể cố ý gửi password sai để khóa tài khoản của nạn nhân. Thay vào đó, dùng cooldown, progressive delay, step-up hoặc yêu cầu hỗ trợ tùy risk; luôn bảo vệ availability cho người dùng hợp lệ.

### Không dựa riêng IP

IP có thể thay đổi do VPN, mobile carrier hoặc proxy; nhiều người có thể chung NAT. Kết hợp nhiều chiều và điều chỉnh theo false positive. Không dùng device fingerprint làm định danh chắc chắn hoặc thu thập dữ liệu quá mức.

## 12. Phát hiện hành vi dictionary attack

Một request sai đơn lẻ thường không đủ để kết luận tấn công. Cần quan sát mẫu theo thời gian.

Tín hiệu có thể gồm:
- nhiều password failure trên cùng account;
- nhiều account bị thử trong một khoảng thời gian ngắn;
- tỷ lệ candidate phổ biến cao;
- nhiều request từ một network hoặc ASN;
- cùng device/session signal xuất hiện trên nhiều account;
- nhiều IP phân tán nhưng có chung nhịp hoặc mẫu request;
- user-agent bất thường hoặc automation pattern;
- đăng nhập thành công sau một chuỗi thử sai;
- sign-in thành công từ môi trường chưa từng thấy sau khi credential stuffing/guessing.

Tín hiệu không phải bằng chứng tuyệt đối. Người dùng hợp lệ có thể quên password, dùng VPN hoặc đăng nhập từ thiết bị mới. Risk engine cần kết hợp context, false positive review và cơ chế step-up phù hợp.

## 13. User enumeration và thông báo lỗi

Dictionary attack thường đi kèm account discovery. Nếu endpoint trả “account không tồn tại” khác “password sai”, attacker có thể xác định danh sách username trước khi đoán password.

Phòng vệ:
- thông báo công khai chung cho identifier không tồn tại và proof sai;
- response shape/status nhất quán khi phù hợp;
- tránh timing gap rõ ràng; có thể dùng dummy hash verification cho account không tồn tại;
- rate limit lookup và login;
- không hiển thị trạng thái disabled/locked trong public error;
- giữ reason code chi tiết trong audit nội bộ;
- kiểm thử cả endpoint recovery và password reset.

Không thể làm mọi nhánh có timing hoàn toàn giống nhau trong hệ thống phân tán. Mục tiêu là giảm tín hiệu dễ khai thác và kết hợp với throttling, monitoring.

## 14. MFA, passkey và giảm tác động dictionary attack

Nếu attacker đoán được password, MFA có thể ngăn họ hoàn tất đăng nhập. Tuy nhiên, mức bảo vệ phụ thuộc phương thức:

- **Passkey/WebAuthn:** chống phishing theo RP ID/origin khi triển khai đúng; private key không được gửi tới server.
- **Security key:** cung cấp public-key authentication và có thể hỗ trợ user verification.
- **TOTP:** bổ sung authenticator code nhưng có thể bị phishing/relay theo thời gian thực.
- **SMS OTP:** có rủi ro SIM swap và phishing; không nên là lựa chọn duy nhất cho account rủi ro cao.
- **Push approval:** cần chống push fatigue, hiển thị ngữ cảnh và number matching khi phù hợp.

MFA không làm password policy trở nên không cần thiết. Password bị lộ vẫn có thể được dùng để truy cập dịch vụ khác, bypass recovery yếu hoặc tấn công các hệ thống chưa bật MFA.

### Pre-authentication state

Sau khi password đúng, nếu MFA còn bắt buộc, server chỉ nên tạo một trạng thái pre-authentication giới hạn. Không cấp session đầy đủ trước khi yếu tố bổ sung hoàn tất. Không tin cờ `mfaCompleted=true` do client tự gửi.

## 15. Password manager và passphrase

Password manager giúp người dùng tạo và lưu mật khẩu dài, ngẫu nhiên và duy nhất cho từng dịch vụ. Điều này giảm reuse và làm dictionary attack khó thành công hơn.

Thiết kế UX nên:
- hỗ trợ autofill và paste;
- không chặn password manager bằng input quirks;
- không ép người dùng ghi nhớ một chuỗi phức tạp duy nhất;
- không tự động cắt hoặc biến đổi password;
- cung cấp flow recovery có bảo đảm;
- hướng dẫn bật MFA/passkey.

Passphrase dài có thể dễ nhớ hơn nhưng vẫn cần tránh câu trích dẫn phổ biến hoặc thông tin cá nhân dễ đoán. Độ dài không tự động đảm bảo khó đoán nếu cụm từ đã xuất hiện trong dictionary.

## 16. Credential reuse và breached password

Dictionary attack thường hiệu quả hơn khi người dùng tái sử dụng password. Một dịch vụ khác bị breach có thể làm lộ credential mà attacker thử lại ở hệ thống hiện tại.

Các biện pháp:
- khuyến khích password duy nhất theo dịch vụ;
- chặn password đã bị lộ ở enrollment/reset;
- không gửi password plaintext sang hệ thống threat intelligence;
- phát hiện login thành công đáng ngờ sau một chuỗi fail;
- yêu cầu reset hoặc step-up khi có bằng chứng compromise;
- revoke session/token nếu account bị chiếm;
- thông báo qua kênh đã xác minh.

Không ép reset toàn bộ account chỉ vì một nguồn danh sách password có chất lượng không rõ. Đánh giá mức tin cậy của dữ liệu, dấu hiệu sử dụng thành công và phạm vi rủi ro.

## 17. Xử lý khi nghi ngờ dictionary attack

Một playbook có thể gồm:

1. Xác định account, network, credential type và khoảng thời gian bị ảnh hưởng.
2. Phân loại online guessing, spraying, stuffing hay dấu hiệu offline hash exposure.
3. Rate limit hoặc chặn nguồn abuse theo risk; tránh khóa account hàng loạt thiếu căn cứ.
4. Yêu cầu MFA/step-up hoặc passkey cho account có dấu hiệu rủi ro.
5. Xác định login thành công đáng ngờ và hành động sau đăng nhập.
6. Revoke session, refresh token và credential bị compromise theo policy.
7. Buộc đổi password nếu có bằng chứng credential bị lộ hoặc sử dụng trái phép.
8. Kiểm tra password database, backup, logs, secret manager và quyền truy cập nếu nghi offline exposure.
9. Thông báo người dùng qua kênh đã xác minh và hướng dẫn bảo vệ account.
10. Điều chỉnh detection/rate limit sau khi phân tích false positive và nguyên nhân.

Nếu password hash database bị lộ, cần đánh giá thuật toán, parameters, salt và khả năng pepper compromise. Đổi password là cần thiết với account có rủi ro, nhưng cũng phải xử lý session/token đã phát hành và nguồn lộ dữ liệu.

## 18. Logging, metrics và privacy

Có thể ghi:
- account ID nội bộ hoặc pseudonymous identifier;
- thời điểm và kết quả sign-in;
- credential type;
- reason code như invalid proof, throttled, challenge required;
- network/device risk signal ở mức tối thiểu;
- correlation ID;
- số lần thử theo cửa sổ thời gian;
- MFA/passkey outcome và session revoke event.

Không log:
- password plaintext;
- password hash hoặc pepper;
- OTP/TOTP seed/recovery code;
- raw passkey assertion nếu chứa dữ liệu nhạy cảm không cần thiết;
- session cookie/access token/refresh token;
- danh sách candidate password mà client đã gửi.

Metrics:
- failed/successful sign-in rate;
- throttling và challenge rate;
- số account bị thử theo network/time window;
- password hash verification latency và resource use;
- breached-password rejection rate;
- MFA completion/failure;
- account enumeration test result;
- false positive và support escalation;
- số session/token revoke sau incident.

Bảo vệ telemetry bằng access control, retention, aggregation và data minimization. IP, device fingerprint và account behavior có thể là dữ liệu cá nhân; dùng theo mục đích đã xác định.

## 19. Ví dụ policy và pseudocode phòng vệ

Một luồng password sign-in có thể thực hiện:

~~~java
SignInResult signIn(String identifierInput, char[] passwordInput,
                    NetworkContext network) {
    rateLimiter.requireAllowed(identifierInput, network);

    Identifier identifier = identifierPolicy.normalize(identifierInput);
    Account account = accountRepository.findForSignIn(identifier).orElse(null);

    PasswordVerifier verifier = account == null
        ? dummyVerifier
        : credentialRepository.activePasswordVerifier(account.id());

    boolean valid = passwordHasher.verify(passwordInput, verifier);

    if (account == null || !valid) {
        riskEngine.recordFailedAttempt(identifier, network);
        throw genericSignInFailure();
    }

    accountPolicy.requireActive(account);

    if (mfaPolicy.requiresAdditionalFactor(account)) {
        return preAuthService.createRestrictedChallenge(account);
    }

    return sessionService.createFreshSession(account);
}
~~~

Đây là pseudocode. Production cần:
- xác minh account và credential state nhất quán trước session commit;
- rate limit đa chiều và bảo vệ hash verifier khỏi DoS;
- dummy verifier có parameters tương đương để giảm timing gap;
- xóa/zeroize password input khi có thể;
- dùng thư viện password hashing đã kiểm chứng;
- không ghi password hoặc verifier vào log;
- xử lý concurrency, retry và account state change;
- không tạo session đầy đủ khi MFA còn pending.

Ví dụ policy khái niệm:

~~~text
IF failed_attempts_per_account exceed adaptive_threshold
  THEN apply progressive delay or step-up

IF many_accounts share repeated candidate pattern
  THEN raise spraying/dictionary risk signal

IF account has breached-password evidence
  THEN require password reset and revoke affected sessions per policy

IF password proof succeeds but MFA is required
  THEN create restricted pre-auth transaction only

IF account/credential is disabled or revoked
  THEN deny sign-in even when submitted proof matches
~~~

## 20. Kiểm thử dictionary attack defense

| Ca kiểm thử | Kết quả mong đợi |
| --- | --- |
| Password phổ biến ở enrollment | Bị từ chối và yêu cầu chọn password khác. |
| Password có trong breached-password source | Bị từ chối hoặc xử lý theo policy đã công bố. |
| Password dài, ngẫu nhiên và hợp lệ | Được verify đúng, không bị cắt ngắn. |
| Password manager paste/autofill | Hoạt động bình thường. |
| Nhiều candidate sai trên một account | Progressive throttling/risk control kích hoạt. |
| Một candidate thử trên nhiều account | Phát hiện spraying/dictionary pattern. |
| Request phân tán qua nhiều IP | Multi-dimensional/global controls vẫn có tác dụng. |
| Account không tồn tại | Response công khai không tiết lộ account existence. |
| Account tồn tại nhưng password sai | Public response tương tự unknown account. |
| Hash database bị lộ trong test lab | Parameters/salt làm offline guessing tốn tài nguyên theo mục tiêu. |
| Password verifier dùng hash nhanh | Security review phát hiện và chặn triển khai. |
| Pepper không truy cập được | Hệ thống xử lý availability theo policy, không log secret. |
| Password hashing bị flood | Rate limit bảo vệ CPU/RAM và availability. |
| Attacker cố khóa account nạn nhân | Không có hard lockout dễ bị lạm dụng; có cooldown/risk policy. |
| Password đúng, MFA chưa hoàn tất | Chỉ có pre-auth state giới hạn. |
| TOTP bị replay | Từ chối mã đã tiêu thụ theo policy. |
| Passkey được bật | Dictionary password không thể thay thế passkey proof. |
| Credential compromise được xác nhận | Reset/revoke session/token theo incident policy. |
| Nguồn breached-password unavailable | Áp dụng availability policy rõ, không âm thầm bỏ qua kiểm soát bắt buộc. |
| Logging review | Không có password, hash, pepper, OTP hoặc token. |

### Đánh giá offline hash resistance

Trong môi trường kiểm thử được kiểm soát, so sánh password-hashing parameters và chi phí verify trên phần cứng mục tiêu. Ghi rõ thuật toán, version, salt, memory/time/parallelism parameters và benchmark. Không dùng một con số tốc độ đơn lẻ để tuyên bố hệ thống “không thể crack”; mục tiêu là tăng chi phí đoán và giảm khả năng attacker tìm password trong thời gian hữu ích.

## 21. Bài tập tình huống

Một cổng nội bộ cho phép password tối thiểu 8 ký tự và bắt buộc có chữ hoa, chữ thường, số và dấu đặc biệt. Người dùng thường đặt password theo tên công ty cộng năm hiện tại. Hệ thống lưu `SHA-256(password)`, không có salt, không chặn password đã lộ và chỉ rate limit theo IP. Attacker đã lấy một bản backup database.

**Yêu cầu phân tích:**

1. Vì sao policy thành phần không ngăn được dictionary attack?
2. Attacker có thể khai thác hash database offline như thế nào?
3. Những thuộc tính nào của password hashing cần thay đổi?
4. Salt, work factor và pepper có vai trò gì?
5. Vì sao rate limit IP không giúp khi cracking offline?
6. Thiết kế breached-password check và password manager UX ra sao?
7. Khi nào cần reset password và revoke session/token?
8. Làm sao đo hiệu quả mà không tuyên bố “không thể crack”?

**Hướng phân tích:** Candidate list có thể chứa tên công ty và năm cùng các biến thể quen thuộc. Hash nhanh không salt cho phép thử candidate rất nhanh và so sánh giữa account. Dùng Argon2id hoặc scheme phù hợp, salt riêng, parameters benchmark và pepper tách biệt nếu có. Rate limit bảo vệ online endpoint, không bảo vệ hash dump. Chặn password phổ biến/đã lộ tại enrollment/reset, hỗ trợ passphrase/password manager, triển khai MFA/passkey. Sau backup exposure, đánh giá phạm vi hash/pepper và buộc reset account có rủi ro, revoke session/token liên quan và điều tra nguồn lộ.

## 22. Checklist review

- [ ] Dictionary attack được phân biệt với brute force, spraying và credential stuffing.
- [ ] Online guessing và offline hash cracking có threat model riêng.
- [ ] Password verifier dùng password-hashing function phù hợp, không dùng hash nhanh đơn thuần.
- [ ] Mỗi password có salt riêng; parameters được benchmark và nâng cấp.
- [ ] Pepper (nếu dùng) lưu tách biệt, có rotation và recovery plan.
- [ ] Password phổ biến/mặc định/đã lộ được chặn tại enrollment và reset.
- [ ] Password policy ưu tiên độ dài, tính riêng biệt và password manager.
- [ ] Không trim, case-fold hoặc truncate password ngoài policy đã công bố.
- [ ] Rate limit đa chiều bảo vệ verifier và giảm online guessing.
- [ ] Không dùng hard lockout dễ bị khai thác để DoS account.
- [ ] Phát hiện candidate pattern, spraying và request phân tán.
- [ ] Error response không tiết lộ account existence hoặc trạng thái nhạy cảm.
- [ ] MFA/passkey được áp dụng trước khi tạo authenticated session đầy đủ.
- [ ] OTP/push có replay, rate-limit và phishing controls phù hợp.
- [ ] Incident response xử lý password reset, session/token revoke và hash exposure.
- [ ] Telemetry không chứa password/hash/pepper/OTP/token và tuân thủ data minimization.
- [ ] Có test online, offline-lab, timing, concurrency, availability và false positive.

## 23. Ghi nhớ

**Dictionary attack khai thác mật khẩu có thể dự đoán bằng cách thử các candidate từ danh sách từ, mẫu phổ biến và biến thể.** Với online guessing, cần rate limit, phát hiện abuse, error response an toàn và MFA/passkey. Với offline cracking sau khi hash bị lộ, cần password-hashing function chuyên dụng như Argon2id, salt riêng, parameters đủ mạnh và pepper được quản lý tách biệt nếu sử dụng. Password policy nên chặn mật khẩu phổ biến/đã lộ, hỗ trợ passphrase và password manager thay vì chỉ ép quy tắc ký tự.

Khi review, hãy hỏi: **Attacker đang thử online hay đã có password hash? Candidate có thể được tạo từ mẫu nào? Hash có salt riêng và work factor phù hợp không? Rate limit có chống được phân tán không? Password phổ biến/đã lộ bị chặn ở đâu? MFA có hoàn tất trước session không? Khi phát hiện compromise, session/token cũ và credential liên quan được thu hồi thế nào?**
