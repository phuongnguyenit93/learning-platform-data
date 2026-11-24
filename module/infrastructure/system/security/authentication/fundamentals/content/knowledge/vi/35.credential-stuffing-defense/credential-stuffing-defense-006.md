# Offline guessing — Bảo vệ password verifier khi dữ liệu xác thực bị lộ

Một dịch vụ bị xâm nhập và attacker lấy được bản sao database tài khoản. Trong database không có mật khẩu dạng plaintext; mỗi tài khoản chỉ có một password verifier được tạo từ mật khẩu và salt. Điều đó giảm thiệt hại, nhưng không làm mật khẩu an toàn tuyệt đối. Attacker có thể mang bản sao verifier ra khỏi hệ thống và thử đoán mật khẩu trên thiết bị của họ, không cần gửi request tới trang đăng nhập. Khi việc đoán diễn ra ngoài hệ thống, rate limit, CAPTCHA, khóa tài khoản và MFA của luồng đăng nhập trực tuyến không thể trực tiếp giới hạn tốc độ thử.

**Offline guessing (đoán mật khẩu ngoại tuyến)** là quá trình attacker dùng password verifier đã lấy được để kiểm tra các phỏng đoán mật khẩu cục bộ. Mỗi phỏng đoán được chuyển qua cùng thuật toán hash/password-based KDF và so sánh với verifier. Nếu mật khẩu yếu, phổ biến hoặc được dùng lại ở nhiều dịch vụ, attacker có thể tìm được mật khẩu mà không tạo thêm dấu vết đăng nhập trên hệ thống gốc.

Bài học thuộc chương **Chống đoán credential** của học phần **SECURITY_AUTHENTICATION_FUNDAMENTALS**. Nội dung liên hệ offline guessing với mật khẩu, credential, MFA, passkey, token, phiên, liên kết danh tính và khôi phục tài khoản. Người học sẽ biết mô hình hóa ranh giới tin cậy, phòng chống lộ verifier, replay credential và lạm dụng sau sự cố; đồng thời thiết kế lưu trữ mật khẩu, nâng cấp thuật toán và quy trình ứng phó phù hợp.

## 1. Kết quả học tập

Sau bài này, người học có thể:

- Phân biệt online password guessing, credential stuffing và offline guessing.
- Giải thích vì sao password verifier bị lộ cho phép kiểm tra phỏng đoán mà không đi qua login endpoint.
- Đánh giá rủi ro của mật khẩu yếu, phổ biến, tái sử dụng và dữ liệu breach.
- Chọn password hashing/KDF phù hợp như Argon2id, scrypt, bcrypt hoặc PBKDF2 theo yêu cầu.
- Giải thích vai trò của salt duy nhất, pepper, memory hardness và work factor.
- Thiết kế password verifier format có thuật toán, tham số và phiên bản để hỗ trợ nâng cấp.
- Lập kế hoạch migration từ hash cũ sang KDF mạnh hơn mà không cần biết plaintext của người dùng.
- Kết hợp password hashing với MFA, passkey, breached-password screening và recovery an toàn.
- Xây dựng quy trình phản ứng khi database/verifier hoặc pepper bị lộ.
- Viết tiêu chí kiểm thử cho hash parameters, salt uniqueness, rehash, reset và bảo vệ secret.

## 2. Offline guessing khác gì online guessing và credential stuffing?

Ba kiểu tấn công có liên quan nhưng khác điểm kiểm soát:

| Kiểu tấn công | Attacker làm gì? | Hệ thống có thể kiểm soát trực tiếp ở đâu? |
| --- | --- | --- |
| Online guessing | Gửi nhiều mật khẩu phỏng đoán tới login endpoint | Rate limit, throttling, risk scoring, MFA, bot detection và giám sát |
| Credential stuffing | Thử cặp username/password lấy từ breach khác trên dịch vụ mục tiêu | Chặn mật khẩu đã lộ, phát hiện login bất thường, MFA/passkey và chống automation |
| Offline guessing | Lấy password verifier rồi kiểm tra phỏng đoán trên hạ tầng của attacker | Thiết kế verifier khó tính, bảo vệ database/pepper, giảm giá trị mật khẩu yếu và phản ứng sự cố |

Rate limit bảo vệ login endpoint nhưng không thể giới hạn việc attacker tính toán trên bản sao database đã lấy. CAPTCHA cũng không làm cho một verifier yếu trở nên khó đoán hơn. MFA có thể ngăn attacker đăng nhập chỉ bằng mật khẩu đã đoán được, nhưng không xóa rủi ro từ việc mật khẩu bị lộ và không bảo vệ các luồng fallback yếu.

### 2.1. Vì sao offline guessing nguy hiểm?

Trong online guessing, mỗi lần thử phải đi qua hệ thống mục tiêu. Request có thể bị giới hạn, ghi log, yêu cầu step-up hoặc bị chặn. Trong offline guessing, attacker có thể:

- Thử phỏng đoán mà không gửi request tới dịch vụ.
- Chạy thử song song trên nhiều thiết bị/hệ thống tính toán.
- Dừng, tiếp tục và ưu tiên tài khoản theo giá trị của dữ liệu bị lấy.
- Tập trung vào mật khẩu phổ biến, biến thể dễ đoán hoặc mật khẩu đã lộ ở nơi khác.
- Không kích hoạt cảnh báo login failure của dịch vụ gốc.

Password hashing tốt làm tăng chi phí cho mỗi phỏng đoán. Nó không biến mật khẩu yếu thành bí mật mạnh, nhưng làm giảm số lượng phỏng đoán attacker có thể kiểm tra trong cùng thời gian và ngân sách.

### 2.2. Hash không phải encryption

Password verifier được tạo bằng hàm một chiều có chủ đích. Hệ thống không giải mã verifier để lấy lại mật khẩu; khi đăng nhập, hệ thống chạy KDF trên mật khẩu người dùng nhập với salt/tham số đã lưu rồi so sánh kết quả.

Nếu attacker có verifier, họ có thể tự thực hiện phép kiểm tra đó. Do vậy, bảo vệ database và chọn KDF phù hợp là hai lớp phòng thủ trực tiếp trước offline guessing.

## 3. Mô hình đe dọa và điều gì khiến mật khẩu dễ bị đoán

Attacker thường không cần thử mọi chuỗi có thể. Họ ưu tiên phỏng đoán có khả năng đúng:

- Mật khẩu phổ biến hoặc nằm trong danh sách đã lộ.
- Mật khẩu có quy luật đơn giản như từ thông dụng kèm năm/số/ký tự.
- Biến thể của mật khẩu cũ hoặc thông tin công khai về người dùng.
- Mật khẩu dùng lại từ dịch vụ khác.
- Credential của tài khoản đặc quyền, email chính hoặc tài khoản có quyền khôi phục nhiều hệ thống.

Rủi ro phụ thuộc cả chất lượng mật khẩu lẫn cấu hình verifier. Một mật khẩu mạnh được lưu bằng hash nhanh, không salt hoặc dùng chung salt vẫn có thể chịu rủi ro lớn khi database bị lộ. Một KDF mạnh làm mỗi phỏng đoán đắt hơn, nhưng không thể cứu mật khẩu đã bị attacker biết từ breach khác.

### 3.1. Các tài sản cần bảo vệ

- Password verifier và salt trong identity database.
- Pepper hoặc khóa dùng kết hợp với verifier.
- Database backup, snapshot, replica, export và analytics copy.
- Secret manager/KMS/HSM chứa pepper hoặc khóa liên quan.
- Password reset token, recovery code và session/token được cấp sau login.
- Log, trace, crash dump và công cụ hỗ trợ có thể vô tình ghi dữ liệu bí mật.

### 3.2. Ranh giới tin cậy

~~~mermaid
flowchart TD
    U[Người dùng nhập mật khẩu] --> A[Authentication service]
    A --> K[Password KDF]
    K --> V[(Password verifier store)]
    A --> P[Secret manager / HSM: pepper]
    A --> S[Session and token service]
    V -. database compromise .-> X[Attacker có bản sao verifier]
    X --> O[Offline guessing environment]
    O -. kiểm tra phỏng đoán cục bộ .-> X
~~~

Database verifier và secret manager phải là hai ranh giới bảo vệ riêng. Nếu verifier và pepper cùng nằm trong một database hoặc cùng được đóng gói trong image, pepper không còn tạo thêm lớp bảo vệ đáng kể khi database/image bị lấy.

## 4. Password hashing và KDF

Không dùng hàm hash tổng quát nhanh như SHA-256, SHA-1 hoặc MD5 trực tiếp để lưu password verifier. Các hàm này được thiết kế để tính nhanh, khiến attacker có thể kiểm tra số lượng phỏng đoán rất lớn. Password hashing/KDF được thiết kế để làm mỗi phép thử tốn thời gian và/hoặc bộ nhớ hơn.

### 4.1. Các lựa chọn thường gặp

| Thuật toán | Đặc điểm | Khi nào cân nhắc |
| --- | --- | --- |
| **Argon2id** | KDF memory-hard; kết hợp đặc tính chống tấn công side-channel và GPU phù hợp | Lựa chọn ưu tiên phổ biến cho hệ thống mới nếu nền tảng hỗ trợ tốt |
| **scrypt** | KDF memory-hard, tăng chi phí bộ nhớ cho mỗi phỏng đoán | Hệ thống cần lựa chọn memory-hard đã được triển khai rộng |
| **bcrypt** | Password hashing có work factor; phù hợp hệ thống legacy, nhưng có giới hạn thiết kế/đầu vào cần hiểu rõ | Duy trì hoặc migration hệ thống cũ; cấu hình cost theo benchmark |
| **PBKDF2** | KDF dựa trên lặp HMAC; được hỗ trợ rộng và có profile phù hợp môi trường yêu cầu chuẩn hóa/FIPS | Khi yêu cầu tương thích hoặc tiêu chuẩn bắt buộc; dùng số vòng phù hợp và kiểm tra baseline |

Việc chọn thuật toán cần dựa trên thư viện đã được duy trì, profile bảo mật, khả năng vận hành và benchmark trên phần cứng production. Không tự viết thuật toán password hashing hoặc tự ghép các hash theo cách chưa được đánh giá.

### 4.2. Argon2id và memory hardness

Argon2id yêu cầu thời gian tính toán và bộ nhớ cho mỗi phép thử. Memory hardness làm tăng chi phí khi attacker muốn chạy rất nhiều phép thử song song, đặc biệt trên phần cứng tối ưu cho phép tính song song nhưng có bộ nhớ hữu hạn.

Các tham số quan trọng:

- **Memory cost:** lượng bộ nhớ dùng cho mỗi lần derive.
- **Time cost/iterations:** số vòng xử lý.
- **Parallelism:** mức song song trong một lần derive.
- **Salt:** dữ liệu ngẫu nhiên riêng cho mỗi password verifier.
- **Output length:** độ dài kết quả được lưu.

Không có một bộ tham số phù hợp với mọi hệ thống. Cần chọn baseline theo hướng dẫn bảo mật hiện hành, benchmark trên phần cứng thật và đo ảnh hưởng tới login throughput, latency và khả năng chống DoS. Ghi tham số cùng verifier để có thể nâng cấp về sau.

### 4.3. Work factor và khả năng chống DoS

Tăng chi phí KDF làm offline guessing đắt hơn nhưng cũng khiến login hợp lệ tốn CPU/RAM hơn. Attacker có thể gửi nhiều login request để buộc server thực hiện KDF, gây cạn tài nguyên.

Biện pháp cân bằng:

- Rate limit và admission control trước bước KDF ở mức phù hợp.
- Giới hạn concurrency và bảo vệ hàng đợi xác thực.
- Benchmark thời gian p50/p95/p99 và memory per request.
- Theo dõi login failure burst, request rate và tài nguyên KDF.
- Không giảm tham số KDF chỉ để xử lý một đợt traffic mà chưa đánh giá.
- Tách worker/pool xác thực nếu cần để giới hạn tài nguyên.

## 5. Salt: duy nhất cho từng verifier

Salt là giá trị ngẫu nhiên được lưu cùng password verifier và đưa vào KDF. Salt không cần bí mật. Mục tiêu là làm cho cùng một mật khẩu ở hai tài khoản tạo ra verifier khác nhau và ngăn attacker tái sử dụng trước bảng tính toán cho mọi tài khoản.

### Yêu cầu đối với salt

- Sinh bằng CSPRNG.
- Mỗi password verifier có salt riêng, không dùng chung toàn hệ thống.
- Đủ độ dài theo thư viện/chuẩn triển khai; 16 byte ngẫu nhiên thường là mức thực hành phổ biến.
- Lưu salt cùng verifier và tham số KDF.
- Không lấy username, email, user ID hoặc timestamp làm salt.
- Khi đổi mật khẩu hoặc tạo verifier mới, tạo salt mới.

Salt không phải pepper. Salt công khai và được lưu cạnh verifier; pepper là bí mật bổ sung được lưu tách biệt.

### 5.1. Salt chống lại điều gì?

Nếu hai tài khoản cùng dùng một mật khẩu, salt riêng khiến verifier của họ khác nhau. Attacker không thể tính một kết quả duy nhất rồi đối chiếu trực tiếp cho mọi tài khoản. Salt cũng làm các bảng tính trước không thể dùng lại nguyên vẹn giữa các salt.

Salt không làm mật khẩu yếu trở nên mạnh. Khi attacker có verifier và salt, họ vẫn có thể kiểm tra phỏng đoán; KDF và chất lượng mật khẩu quyết định chi phí/khả năng thành công.

## 6. Pepper: bí mật bổ sung được bảo vệ riêng

Pepper là một bí mật bổ sung được kết hợp vào quá trình tạo/kiểm tra verifier. Khác salt, pepper không được lưu trong cùng database với password verifier. Có thể lưu pepper trong secret manager, KMS hoặc HSM và giới hạn quyền truy cập cho authentication service.

### Lợi ích

- Nếu attacker chỉ lấy database verifier mà không lấy được pepper, việc kiểm tra phỏng đoán sẽ khó hơn vì thiếu một thành phần bí mật.
- Có thể giảm tác động của một số dạng database-only compromise.

### Giới hạn

- Nếu authentication service, runtime memory, secret manager hoặc pepper key bị chiếm, lớp bảo vệ này có thể mất.
- Pepper không thay thế salt hoặc KDF memory-hard.
- Nếu pepper bị mất, hệ thống có thể không xác minh được verifier cũ.
- Nếu pepper bị lộ, không thể đơn giản tính lại verifier mới nếu không có plaintext password.

### Quản lý pepper

- Lưu tách khỏi database và backup chứa verifier.
- Dùng quyền tối thiểu; authentication service chỉ có quyền cần thiết.
- Mã hóa/quản lý bằng KMS/HSM hoặc secret manager phù hợp.
- Audit việc truy cập và xoay vòng theo policy.
- Có kế hoạch versioning và migration; không hardcode pepper trong source code/container image.
- Không log pepper hoặc đưa vào error message/telemetry.

### Pepper rotation

Do server không biết plaintext password, không thể rehash hàng loạt verifier cũ với pepper mới ngay lập tức. Các chiến lược:

1. Gắn pepper version vào verifier metadata.
2. Khi người dùng đăng nhập thành công bằng pepper cũ, derive verifier mới bằng pepper hiện hành rồi cập nhật an toàn.
3. Với tài khoản không đăng nhập trong thời hạn migration, yêu cầu password reset hoặc xử lý theo risk policy.
4. Nếu pepper bị compromise, đánh giá incident và có thể buộc reset mật khẩu cho phạm vi bị ảnh hưởng.

Không xóa pepper cũ trước khi các verifier phụ thuộc đã được migrate hoặc đã có kế hoạch reset/retire rõ ràng.

## 7. Lưu trữ password verifier đúng cách

Verifier cần mang đủ thông tin để hệ thống xác minh và nâng cấp:

- Thuật toán và phiên bản.
- Tham số KDF.
- Salt.
- Kết quả derive.
- Pepper/key version nếu áp dụng.

Một biểu diễn khái niệm:

~~~text
algorithm = argon2id
version = v
memory_cost = configured_value
time_cost = configured_value
parallelism = configured_value
salt = random_unique_value
hash = derived_output
pepper_version = key-v3
~~~

Trong thực tế nên dùng encoded format do thư viện chuẩn cung cấp nếu nó lưu được thuật toán, tham số và salt một cách an toàn. Không tự thiết kế parser/encoding thiếu kiểm tra. Khi đọc verifier, validate format và giới hạn tham số để tránh dữ liệu bị sửa khiến server cấp phát bộ nhớ/thời gian quá lớn.

### 7.1. Không lưu plaintext hoặc reversible encryption

- Không lưu mật khẩu ở plaintext.
- Không mã hóa mật khẩu bằng khóa có thể giải mã để “phục vụ đăng nhập”.
- Không ghi password vào log, tracing, analytics, crash dump hoặc support ticket.
- Không gửi password qua email/SMS hoặc lưu trong event.
- Không để password verifier trong source repository, public artifact hoặc client application.

Encryption có thể bảo vệ dữ liệu khi lưu, nhưng nếu hệ thống có thể giải mã hàng loạt password thì attacker lấy khóa cũng có thể lấy lại toàn bộ mật khẩu. Password verifier phải được tạo bằng KDF một chiều phù hợp.

### 7.2. Giới hạn đầu vào

Xác định rõ encoding, Unicode normalization policy và giới hạn kích thước đầu vào. Không cắt ngắn mật khẩu âm thầm; việc cắt ngắn có thể khiến hai mật khẩu khác nhau trở thành cùng một giá trị. Cần từ chối đầu vào vượt giới hạn an toàn với thông báo phù hợp, đồng thời tránh giới hạn thấp làm giảm khả năng dùng passphrase dài.

## 8. Chất lượng mật khẩu và ngăn mật khẩu đã lộ

Password hashing làm chậm phỏng đoán nhưng không ngăn một attacker dùng mật khẩu đã biết. Dịch vụ cần giảm khả năng người dùng chọn mật khẩu phổ biến hoặc đã xuất hiện trong các vụ breach.

### 8.1. Blocklist mật khẩu phổ biến/bị lộ

Khi tạo hoặc đổi mật khẩu:

- Kiểm tra mật khẩu có nằm trong danh sách mật khẩu phổ biến, dễ đoán hoặc đã bị lộ theo nguồn được chấp nhận không.
- So sánh theo cách bảo vệ quyền riêng tư, ví dụ cơ chế k-anonymity hoặc dịch vụ có hợp đồng/kiến trúc phù hợp.
- Không gửi plaintext password tới analytics hoặc dịch vụ bên ngoài không được phê duyệt.
- Thông báo người dùng chọn passphrase khác; không tiết lộ danh sách nội bộ hoặc cách né kiểm tra.

Không cần bắt người dùng thay mật khẩu thường xuyên nếu không có dấu hiệu compromise hoặc yêu cầu chính sách cụ thể. Forced periodic reset có thể khiến người dùng tạo biến thể dễ đoán và ghi mật khẩu ra nơi không an toàn.

### 8.2. Passphrase và password manager

Khuyến khích mật khẩu dài, duy nhất cho mỗi dịch vụ và dùng password manager. Đừng ép quy tắc thành phần quá cứng khiến người dùng chọn mẫu dễ đoán. Cho phép paste và autofill nếu không có lý do bảo mật cụ thể để hạn chế; chặn password manager có thể làm giảm chất lượng mật khẩu.

Mật khẩu dùng lại là rủi ro lớn: khi một dịch vụ khác bị breach, attacker có thể thử credential đó trên hệ thống mục tiêu. Hashing mạnh tại hệ thống mục tiêu không ngăn việc password đã bị lộ từ nguồn khác.

## 9. MFA, passkey và các lớp phòng thủ bổ sung

Offline guessing có thể giúp attacker tìm ra mật khẩu, nhưng không nhất thiết đủ để chiếm tài khoản nếu hệ thống yêu cầu một yếu tố độc lập:

- **Passkey/WebAuthn:** xác thực bằng khóa công khai/riêng, có ràng buộc RP/origin và khả năng chống phishing tốt.
- **Security key:** authenticator vật lý có thể cung cấp bằng chứng chống phishing.
- **MFA:** bổ sung yếu tố khác; cần xem xét nguy cơ phishing, relay, fatigue và recovery.
- **Risk-based authentication:** yêu cầu step-up khi có tín hiệu bất thường.
- **Session/token controls:** giới hạn thời hạn, rotation, sender constraint và revoke khi có compromise.

MFA không thay thế password hashing. Nếu attacker lấy được password verifier, họ vẫn có thể đoán password và sử dụng nó ở dịch vụ khác nếu người dùng tái sử dụng. Nếu MFA fallback yếu hoặc recovery dễ bị chiếm, password compromise vẫn có thể dẫn tới account takeover.

### 9.1. Không để fallback làm mất lợi ích passkey

Một tài khoản có passkey mạnh nhưng vẫn cho phép reset qua email yếu hoặc password-only có thể bị chiếm qua fallback. Cần threat model toàn bộ đường vào tài khoản: đăng nhập, thiết bị mới, thêm authenticator, recovery, support override và account linking.

### 9.2. Re-authentication cho thao tác nhạy cảm

Đổi password, xóa passkey, thêm recovery method, xuất dữ liệu hoặc thay đổi thông tin thanh toán có thể cần xác thực lại bằng phương thức phù hợp. Không dùng việc người dùng đã đăng nhập lâu trước đó làm bằng chứng đủ cho thao tác có tác động lớn.

## 10. Migration từ password hash cũ

Hệ thống có thể đang lưu MD5/SHA-1/SHA-256 trực tiếp, bcrypt với cost thấp hoặc PBKDF2/Argon2id tham số cũ. Migration cần giảm rủi ro mà không buộc toàn bộ người dùng reset cùng lúc nếu chưa cần.

### 10.1. Rehash on successful login

Khi người dùng đăng nhập:

1. Đọc verifier và kiểm tra format/algorithm/parameters.
2. Xác minh mật khẩu nhập bằng verifier cũ theo cách tương thích.
3. Nếu xác minh thành công và verifier yếu/cũ, tạo salt mới và derive verifier bằng cấu hình hiện hành.
4. Cập nhật verifier trong transaction có kiểm soát; tránh ghi đè thay đổi password mới xảy ra đồng thời.
5. Giữ nguyên session/authentication flow theo policy và ghi metadata migration không chứa bí mật.

Không thể chuyển trực tiếp một hash cũ sang Argon2id tương đương với hash mật khẩu ban đầu nếu không có plaintext. Bọc hash cũ vào KDF mới có thể là biện pháp chuyển tiếp có giới hạn nhưng cần được đánh giá; mục tiêu cuối vẫn là rehash từ mật khẩu người dùng nhập hoặc reset.

### 10.2. Migration theo mức rủi ro

- Ưu tiên tài khoản đặc quyền, verifier yếu và tài khoản có dấu hiệu compromise.
- Rehash on login cho tài khoản còn hoạt động.
- Yêu cầu reset cho verifier quá yếu hoặc không thể xác minh an toàn sau thời hạn.
- Theo dõi số tài khoản còn dùng thuật toán cũ và đặt deadline retire.
- Không giữ nhánh xác minh cũ vô thời hạn vì điều đó duy trì bề mặt tấn công.

### 10.3. Tránh race condition

Nếu người dùng đổi password cùng lúc với login rehash, cập nhật cần compare-and-swap theo verifier version hoặc transaction. Rehash từ password cũ không được ghi đè verifier mới. Nếu account bị disable/revoke trong lúc login, không tạo session mới chỉ vì password KDF đã xác minh thành công.

## 11. Ứng phó khi password verifier bị lộ

Khi phát hiện database hoặc backup chứa verifier bị truy cập trái phép, coi đó là sự cố bảo mật ngay cả khi chưa có bằng chứng password đã bị đoán thành công.

### Các bước phản ứng

1. **Containment:** cô lập nguồn rò rỉ, thu hồi quyền truy cập trái phép và bảo vệ bản sao còn lại.
2. **Scope:** xác định database/table/backup/replica bị ảnh hưởng, số tài khoản và loại verifier.
3. **Secret assessment:** xác định pepper/key có bị lộ cùng verifier không; kiểm tra KMS/HSM/secret manager access.
4. **Risk triage:** ưu tiên tài khoản đặc quyền, mật khẩu yếu, password reuse risk và verifier dùng thuật toán/tham số cũ.
5. **Credential protection:** buộc reset hoặc step-up theo phạm vi/rủi ro; revoke session/token nếu có dấu hiệu account takeover.
6. **Monitoring:** tăng giám sát login, password reset, MFA changes, token refresh và credential stuffing.
7. **User communication:** thông báo qua kênh đã xác minh, hướng dẫn thay mật khẩu duy nhất và kiểm tra tài khoản khác nếu người dùng tái sử dụng.
8. **Remediation:** nâng cấp KDF/parameters, xoay pepper nếu phù hợp, xóa bản sao không cần và vá nguyên nhân rò rỉ.
9. **Evidence:** bảo toàn audit/forensic evidence tối thiểu, không sao chép thêm plaintext hoặc secret.
10. **Closure:** kiểm chứng các credential/phiên bị ảnh hưởng đã được xử lý và các hệ thống downstream đã áp dụng.

Không mặc định mọi tài khoản đều phải reset cùng lúc nếu sự cố chỉ ảnh hưởng một phạm vi đã xác định; cũng không trì hoãn bảo vệ tài khoản đặc quyền hoặc credential có bằng chứng compromise. Quyết định cần dựa trên phạm vi, loại verifier, pepper exposure và yêu cầu pháp lý.

### 11.1. Nếu chỉ database verifier bị lộ

Nếu pepper được bảo vệ độc lập và chưa có dấu hiệu bị lộ, lớp pepper có thể giảm khả năng kiểm tra phỏng đoán. Tuy nhiên, attacker vẫn có salt/verifier và có thể thử các phỏng đoán theo cách được thiết kế của hệ thống nếu có đủ thông tin. Cần đánh giá khả năng xâm nhập tới authentication service, memory dump, backup và secret manager; không kết luận pepper an toàn chỉ vì chưa thấy nó trong database.

### 11.2. Nếu pepper bị lộ

Nếu pepper bị lộ, coi toàn bộ verifier phụ thuộc pepper đó là có rủi ro cao hơn. Xác định version/nhóm tài khoản, rotate key, yêu cầu password reset hoặc rehash khi login theo mức độ rủi ro. Không thể tính verifier mới với pepper mới nếu không có plaintext password; cần thiết kế migration thực tế thay vì chỉ đổi cấu hình key.

## 12. Liên hệ với token, session, federation và account recovery

Password verifier chỉ là một phần của hệ thống danh tính:

- **Session:** sau khi attacker đoán được password, họ có thể tạo session nếu không có yếu tố độc lập hoặc policy bổ sung. Khi có compromise, cần revoke session đã phát sinh.
- **Refresh token:** attacker đã chiếm phiên có thể giữ quyền sau khi password được đổi nếu refresh token không bị thu hồi theo policy.
- **Federation:** password của IdP có thể bảo vệ nhiều ứng dụng; compromise tại IdP có tác động rộng. RP cần kiểm tra issuer/subject và phản ứng theo sự kiện từ IdP.
- **Account linking:** không tự động liên kết tài khoản chỉ vì email giống nhau; cần issuer/subject đã xác minh và xác nhận quyền sở hữu.
- **Recovery:** không để reset flow yếu hơn login; recovery code, email hoặc support override cần bảo vệ và audit.
- **Credential cleanup:** sau reset/compromise, revoke verifier cũ, reset token, session, refresh token và authenticator không còn tin cậy theo phạm vi.

## 13. Pseudocode: tạo và xác minh password verifier

Ví dụ khái niệm. Trong production, dùng thư viện password hashing được duy trì, có format mã hóa tham số và hỗ trợ constant-time verification.

~~~ts
async function createPasswordVerifier(password) {
  const salt = secureRandomBytes(16);
  const params = currentPasswordKdfPolicy();
  const pepper = await secretManager.getCurrentPepper(params.pepperVersion);

  const derived = await argon2id({
    password: encodePasswordAccordingToPolicy(password),
    salt,
    pepper,
    memoryCost: params.memoryCost,
    timeCost: params.timeCost,
    parallelism: params.parallelism,
    outputLength: params.outputLength
  });

  return encodeVerifier({
    algorithm: "argon2id",
    params,
    salt,
    derived
  });
}

async function verifyPassword(password, storedVerifier) {
  const parsed = parseAndValidateVerifier(storedVerifier, {
    allowedAlgorithms: configuredAlgorithms(),
    maximumMemoryCost: safeMaximumMemory(),
    maximumTimeCost: safeMaximumTime()
  });
  if (!parsed.valid) return { valid: false, needsReset: true };

  const pepper = await secretManager.getPepper(parsed.pepperVersion);
  const candidate = await deriveWithStoredParameters(password, parsed, pepper);
  const valid = constantTimeEqual(candidate, parsed.derived);

  return {
    valid,
    needsRehash: valid && needsUpgrade(parsed, currentPasswordKdfPolicy())
  };
}
~~~

Pseudocode này không định nghĩa API Argon2 cụ thể. Cần kiểm tra encoding/normalization nhất quán, giới hạn tham số đọc từ database để tránh resource exhaustion, constant-time comparison và xử lý lỗi secret manager. Không log password, pepper hoặc derived verifier. Khi needsRehash là true, chỉ cập nhật sau khi xác minh thành công và bảo đảm không ghi đè một lần đổi mật khẩu đồng thời.

## 14. Kiến trúc lưu trữ và kiểm soát

~~~mermaid
flowchart TD
    A[Password input over TLS] --> B[Authentication service]
    B --> C[Input validation and rate control]
    C --> D[Password KDF]
    D --> E[(Verifier store: hash + salt + params)]
    B --> F[Secret manager / HSM: pepper]
    B --> G[Credential policy and MFA/passkey]
    G --> H[Session/token service]
    E -. database copy stolen .-> X[Attacker]
    X --> Y[Offline guessing]
    F -. separately protected .-> Z[Additional secret boundary]
~~~

### Kiểm soát ở từng lớp

- **Client/transport:** TLS, không gửi password qua URL, không lưu trong local storage hoặc analytics.
- **Authentication service:** rate limit trước/bao quanh KDF, input validation, constant-time compare và xử lý lỗi không tiết lộ tài khoản tồn tại.
- **Verifier store:** quyền tối thiểu, encryption at rest, backup access control, audit và tách môi trường.
- **Pepper store:** tách database, KMS/HSM, access policy, rotation và monitoring.
- **Session/token:** giới hạn thời hạn, refresh rotation, revoke khi compromise và kiểm tra authorization.
- **Operations:** patching, secret scanning, backup lifecycle, incident response và kiểm thử định kỳ.

## 15. Tiêu chí chấp nhận và kiểm thử

| Tình huống | Kết quả mong đợi |
| --- | --- |
| Hai tài khoản dùng cùng password | Salt riêng tạo verifier khác nhau |
| Password mới được lưu | Chỉ lưu verifier KDF; không có plaintext hoặc reversible encryption |
| Verifier dùng SHA-256 trực tiếp | Bị đánh dấu legacy và có kế hoạch migration; không dùng cho tài khoản mới |
| Verifier có tham số vượt giới hạn | Parser từ chối an toàn, không cấp phát tài nguyên không giới hạn |
| Pepper nằm trong cùng database với verifier | Kiểm tra kiến trúc thất bại; pepper phải được tách khỏi verifier store |
| Pepper version không còn khả dụng | Không âm thầm bỏ pepper; chuyển reset/recovery hoặc incident flow theo policy |
| Password được xác minh bằng verifier cũ | Rehash bằng KDF hiện hành và salt mới nếu chính sách yêu cầu |
| Password đổi đồng thời với login rehash | Rehash cũ không ghi đè verifier mới |
| Database verifier bị lộ | Incident workflow xác định phạm vi, pepper exposure, tài khoản ưu tiên và hành động bảo vệ |
| Password phổ biến/bị lộ được đăng ký | Blocklist/policy từ chối và hướng dẫn người dùng chọn mật khẩu khác |
| Người dùng từ chối GPS hoặc device signal không có | Không làm password verification thất bại chỉ vì thiếu tín hiệu không bắt buộc |
| MFA chưa hoàn tất | Không tạo session success hoặc thông báo login thành công |
| Password bị reset sau compromise | Reset token cũ bị vô hiệu hóa; session/refresh token được xử lý theo policy |
| Refresh token reuse sau password reset | Phát hiện và revoke token family/session liên quan theo policy |
| KDF cost tăng | Benchmark latency/memory và kiểm tra login DoS trước rollout |
| KDF service/pepper store tạm lỗi | Không fallback sang hash yếu hoặc bỏ qua pepper |
| Password dài/Unicode | Encoding/normalization nhất quán; không cắt ngắn âm thầm |
| Audit/telemetry | Không chứa password, OTP, pepper, token hoặc secret thô |
| Backup cũ còn verifier | Quyền truy cập backup bị giới hạn; retention/purge theo policy |
| Account bị disable trong lúc login | Không cấp session mới sau khi trạng thái disable có hiệu lực |

### Chỉ số vận hành

Theo dõi phân bố thuật toán và tham số verifier, tỷ lệ rehash thành công, số tài khoản còn dùng hash legacy, KDF latency/memory, login failure/rate-limit, password reset sau incident, tỷ lệ password blocklist hit, lỗi pepper service và thời gian xử lý compromise. Không ghi giá trị password hoặc verifier đầy đủ vào metric label/log.

## 16. Bài tập tự kiểm tra

Một dịch vụ có 2 triệu tài khoản. Hệ thống cũ lưu SHA-256(password + salt) với salt ngẫu nhiên; pepper chưa được triển khai. Một bản backup bị truy cập trái phép. Hệ thống đang hỗ trợ password login và MFA qua TOTP; nhóm phát triển muốn chuyển sang Argon2id và thêm passkey.

Hãy:

1. Giải thích attacker có thể làm gì với backup verifier mà không cần gửi login request.
2. Phân biệt rủi ro của SHA-256 trực tiếp với Argon2id/scrypt/bcrypt/PBKDF2.
3. Đề xuất cách chọn memory/time/parallelism dựa trên benchmark và threat model.
4. Thiết kế salt, pepper và vị trí lưu pepper tách khỏi verifier database.
5. Lập kế hoạch rehash on login, reset tài khoản không đăng nhập và retire SHA-256.
6. Xác định khi nào cần revoke session/refresh token và khi nào yêu cầu reset password.
7. Giải thích MFA/passkey giảm rủi ro nào và các fallback vẫn cần bảo vệ ra sao.
8. Viết test case cho pepper outage, concurrent password change, verifier tampering, database-only compromise và backup retention.

**Gợi ý đánh giá:** câu trả lời tốt phải hiểu rằng offline guessing không bị rate limit của login endpoint kiểm soát; dùng password KDF có salt riêng và tham số phù hợp; giữ pepper tách biệt; có migration và incident response; đồng thời xử lý session/token/recovery. Không tuyên bố hashing làm password không thể bị đoán.

---

**Ghi nhớ:** offline guessing xảy ra khi attacker có password verifier và tự kiểm tra phỏng đoán bên ngoài dịch vụ. Hãy dùng password KDF chuyên dụng như **Argon2id** (hoặc lựa chọn phù hợp theo yêu cầu), salt ngẫu nhiên riêng cho từng verifier, tham số được benchmark và pepper được bảo vệ tách biệt nếu áp dụng. Kết hợp blocklist mật khẩu bị lộ, MFA/passkey, session/token revocation và migration có phiên bản. Hashing làm mỗi phỏng đoán đắt hơn; nó không cứu mật khẩu yếu hoặc mật khẩu đã bị lộ ở dịch vụ khác.
