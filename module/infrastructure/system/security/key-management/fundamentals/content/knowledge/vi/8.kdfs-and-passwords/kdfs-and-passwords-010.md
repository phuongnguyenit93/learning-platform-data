# Password reset và key derivation — Đặt lại mật khẩu và dẫn xuất khóa an toàn

## 1. Tại sao password reset liên quan đến key derivation?

**Password reset** là quy trình cấp cho người dùng cách thiết lập **mật khẩu mới** khi họ không còn dùng được hoặc không nhớ mật khẩu hiện tại. **Key derivation** là quá trình tạo ra một hoặc nhiều khóa/vật liệu mật mã từ đầu vào khác theo một **hàm dẫn xuất khóa (Key Derivation Function — KDF)**.

Hai khái niệm liên quan nhưng **không đồng nhất**. Trong một hệ thống đơn giản, mật khẩu chỉ dùng **xác thực tài khoản**: máy chủ lưu một giá trị kiểm tra mật khẩu, còn dữ liệu người dùng được mã hóa bằng các khóa độc lập do KMS/HSM quản lý. Khi đặt lại mật khẩu, máy chủ thay giá trị kiểm tra; các khóa mã hóa dữ liệu **không nhất thiết thay đổi**.

Nhưng trong một hệ thống mã hóa đầu cuối (*end-to-end encryption*) hoặc kho dữ liệu được bảo vệ bằng khóa dẫn xuất từ mật khẩu, mật khẩu cũ có thể là **đầu vào duy nhất** để khôi phục khóa giải mã. Khi người dùng quên mật khẩu, hệ thống **không thể đơn giản sinh lại khóa cũ** từ một mật khẩu mới.

Đây là một điểm nối quan trọng giữa chương **KDF và mật khẩu** với mục tiêu tổng thể của quản lý khóa mật mã: bảo vệ vòng đời **tạo, cấp phát, lưu trữ, sử dụng, xoay vòng, thu hồi, hủy**, kết hợp mật mã đối xứng/bất đối xứng, chữ ký số, KMS/HSM, envelope encryption, kiểm soát truy cập và kiểm toán.

> **Nguyên tắc cốt lõi:** **Reset mật khẩu đăng nhập** chỉ chứng minh người dùng đã đi qua một quy trình khôi phục tài khoản đủ điều kiện. Nó **không tự cung cấp lại khóa giải mã** được dẫn xuất từ mật khẩu cũ. Muốn khôi phục dữ liệu đã mã hóa mà không biết mật khẩu cũ, hệ thống phải có **đường phục hồi khóa được thiết kế từ trước**, hoặc chấp nhận dữ liệu không thể phục hồi.

### Ba câu hỏi hệ thống phải trả lời

1. Mật khẩu đang dùng để **đăng nhập**, để **dẫn xuất khóa giải mã**, hay cho **cả hai** mục đích?
2. Ai đang nắm **DEK (Data Encryption Key)** thực sự mã hóa dữ liệu, và DEK được bảo vệ bằng cách nào?
3. Khi người dùng quên mật khẩu, ai có thể phục hồi DEK mà **không dựa vào mật khẩu cũ**, nếu chính sách cho phép?

Nếu chưa trả lời ba câu này, việc thiết kế màn hình “Quên mật khẩu?” có thể vô tình tạo lỗ hổng bảo mật hoặc khiến dữ liệu bị mất vĩnh viễn.

## 2. Các thuật ngữ cần phân biệt

| Khái niệm | Mục đích | Điều dễ nhầm |
| --- | --- | --- |
| **Password change** | Người dùng còn biết mật khẩu cũ, tự đổi sang mật khẩu mới | Không giống *reset* không cần cung cấp mật khẩu cũ |
| **Password reset** | Người dùng qua một quy trình khôi phục danh tính để tạo mật khẩu mới | Không tự chứng minh họ còn khả năng giải mã dữ liệu bằng khóa cũ |
| **Password verifier/hash** | Giá trị lưu để kiểm tra mật khẩu khi đăng nhập | Không phải password và không nên được dùng như DEK/KEK |
| **Password hashing / password KDF** | Hàm có chi phí tính toán và thường dùng salt để chống đoán mật khẩu hàng loạt | Không giống gọi SHA-256 một lần lên password |
| **KDF dùng cho khóa phiên** | Dẫn xuất khóa từ vật liệu bí mật đủ entropy hoặc shared secret | **HKDF** không phải lựa chọn mặc định để xử lý mật khẩu ít entropy |
| **Salt** | Giá trị độc lập gắn với mỗi trường hợp dẫn xuất/hash | Có thể công khai; **không** phải khóa bí mật |
| **Pepper** | Bí mật cấp hệ thống dùng bổ sung khi bảo vệ password verifier theo kiến trúc phù hợp | Không thay thế salt, password hashing hoặc MFA |
| **DEK** | Khóa đối xứng trực tiếp mã hóa dữ liệu | Không nên tạo lại DEK bằng hash đơn giản của mật khẩu |
| **KEK** | Khóa dùng để bọc/giải bọc DEK hoặc khóa khác | Có thể dẫn xuất từ mật khẩu hoặc được KMS quản lý |
| **Wrapped DEK** | DEK đã được bảo vệ bằng cơ chế bọc khóa/AEAD phù hợp | Không thể giải bọc khi đã mất **mọi** đường tới KEK hợp lệ |
| **Recovery key / recovery secret** | Bí mật hoặc khóa phục hồi độc lập được cấp theo chính sách | Không nên tạo từ cùng mật khẩu đã quên mà không có bản sao khác |
| **Reset token** | Bằng chứng **tạm thời, một lần** cho phép đi vào quy trình reset | Không phải session token và không phải khóa mã hóa dữ liệu |

### Phân biệt dữ liệu bí mật và metadata

Các **salt**, key ID, thuật toán, KDF parameters, phiên bản định dạng và IV/nonce thường có thể được lưu cùng bản ghi để phục vụ xác minh/giải mã. Ngược lại, **mật khẩu rõ, recovery secret, DEK rõ, KEK rõ, private key và token reset chưa sử dụng** phải được xử lý như bí mật, không đưa vào log hoặc bản ghi telemetry.

## 3. Ba kiến trúc thường gặp và tác động của reset

### 3.1. Mô hình A — Mật khẩu chỉ dùng để đăng nhập

~~~mermaid
flowchart LR
    P[Mật khẩu người dùng] --> V[Password hashing/KDF + salt]
    V --> DB[(Password verifier)]
    L[Ứng dụng sau khi xác thực] --> K[KMS/HSM quản lý KEK]
    K --> D[Giải bọc DEK theo quyền]
    D --> E[Giải mã dữ liệu bằng DEK]
~~~

Hệ thống lưu password verifier bằng Argon2id, scrypt hoặc PBKDF2 được cấu hình phù hợp. DEK/KEK **không được dẫn xuất trực tiếp từ mật khẩu**; chúng do hệ thống quản lý khóa độc lập.

**Khi reset:** sau khi xác minh yêu cầu khôi phục, máy chủ cập nhật password verifier và session/token theo chính sách. Dữ liệu có thể tiếp tục truy cập bởi người dùng đã được xác thực, **vì việc truy cập DEK được kiểm soát bởi IAM/KMS và chính sách nghiệp vụ**, không phải bởi mật khẩu cũ.

**Đánh đổi:** Nhà vận hành dịch vụ hoặc danh tính được cấp quyền KMS có thể có khả năng giải mã dữ liệu theo kiến trúc. Không được mô tả đây là hệ thống “server không bao giờ có thể giải mã”.

### 3.2. Mô hình B — Mật khẩu dẫn xuất khóa để giải mã

~~~mermaid
flowchart LR
    P[Mật khẩu của người dùng] --> F[Password KDF: salt, parameters]
    F --> KEK[KEK dẫn xuất từ mật khẩu]
    KEK --> U[Giải bọc DEK]
    W[(Wrapped DEK)] --> U
    U --> D[DEK rõ trong phạm vi xử lý được phép]
    D --> E[Giải mã dữ liệu AEAD]
~~~

DEK có thể được tạo ngẫu nhiên rồi **bọc bởi KEK dẫn xuất từ mật khẩu**, thay vì dùng thẳng đầu ra KDF làm khóa mã hóa mọi bản ghi. Đây là một dạng **envelope encryption** có lớp KEK dựa vào mật khẩu.

**Khi đổi mật khẩu và còn mật khẩu cũ:** hệ thống có thể dẫn xuất KEK cũ để giải bọc DEK; sau đó dẫn xuất KEK mới từ mật khẩu mới và salt mới, rồi **bọc lại DEK**. Dữ liệu không nhất thiết phải mã hóa lại toàn bộ.

**Khi quên mật khẩu cũ:** nếu không có recovery key, thiết bị đã được ủy quyền đang giữ một đường khôi phục hợp lệ, hoặc một đường bọc DEK độc lập khác, hệ thống **không thể tính lại KEK cũ**. Tạo verifier mới không giúp lấy lại DEK. Đây là hệ quả có chủ đích của mô hình bảo mật chứ không phải lỗi giao diện reset.

### 3.3. Mô hình C — Mật khẩu cộng một đường recovery độc lập

~~~mermaid
flowchart TD
    D[DEK ngẫu nhiên] --> P[Wrapped DEK theo password-derived KEK]
    D --> R[Wrapped DEK theo recovery KEK]
    PW[Password + password KDF] --> P
    REC[Recovery secret/thiết bị hợp lệ hoặc KMS có quyền] --> R
    P --> U[Chọn một đường giải bọc hợp lệ]
    R --> U
    U --> DATA[DEK dùng giải mã dữ liệu]
~~~

DEK được bọc **nhiều lần độc lập**: một bản dưới KEK từ mật khẩu, một bản dưới recovery KEK do thiết bị khác, hardware-backed key, recovery code có entropy cao hoặc KMS quản lý theo chính sách. Khi reset do quên mật khẩu, hệ thống chỉ có thể giải bọc DEK nếu người dùng/đơn vị phục hồi **được phép sử dụng đường recovery đó**.

**Đánh đổi bảo mật:** Một đường phục hồi giúp tăng khả năng lấy lại dữ liệu nhưng cũng trở thành **đường truy cập cần bảo vệ nghiêm ngặt**. Nếu tổ chức giữ recovery KEK trong KMS và có quyền giải bọc, không được quảng bá hệ thống là “không ai ngoài người dùng có thể giải mã” theo nghĩa tuyệt đối. Nếu không giữ đường phục hồi ở phía server, cần nói rõ khả năng mất dữ liệu khi mất password và recovery secret.

## 4. Password hashing và key derivation khác nhau thế nào?

Cùng tên **KDF**, nhưng mục tiêu và đầu vào rất khác.

| Nhu cầu | Đầu vào | Thuật toán có thể phù hợp | Đầu ra | Cần chú ý |
| --- | --- | --- | --- | --- |
| **Lưu verifier đăng nhập** | Mật khẩu có entropy hạn chế + salt | **Argon2id** ưu tiên trong nhiều thiết kế hiện đại; scrypt; PBKDF2 khi cần tương thích/tuân thủ | Giá trị xác minh có thể lưu trong DB | Cost/memory/iterations, salt riêng, nâng cấp parameters |
| **Dẫn xuất KEK từ mật khẩu** | Mật khẩu + salt + ngữ cảnh | Password KDF như Argon2id/scrypt/PBKDF2, cấu hình riêng | Khóa dùng bọc/giải bọc DEK | Mất password có thể mất KEK; cần recovery path nếu yêu cầu |
| **Dẫn xuất khóa phiên từ shared secret** | Shared secret đủ mạnh của (EC)DH | **HKDF** theo giao thức | Khóa phiên cho từng mục đích | Binding ngữ cảnh, transcript, algorithm |
| **Dẫn xuất khóa con từ master key** | Bí mật có entropy cao | HKDF hoặc KDF chuẩn do hệ thống quy định | Các khóa tách mục đích | Không dùng lại context/info gây va chạm vai trò |
| **Bọc DEK bằng KEK** | DEK và KEK | AES-KW, cơ chế key wrap/KMS hoặc AEAD phù hợp | Wrapped DEK | Quyền unwrap, thuật toán, IV/nonce nếu có |

### 4.1. Tại sao không dùng SHA-256(password)?

Mật khẩu do con người đặt thường có **entropy thấp** và có thể đoán bằng từ điển. Tính một hash nhanh như:

~~~text
verifier = SHA-256(password)
~~~

giúp kẻ tấn công có bản dump database thử một lượng lớn ứng viên rất nhanh. Thêm salt nhưng chỉ hash một lần vẫn có tốc độ thử cao. **Password KDF** được thiết kế để tăng chi phí mỗi lần đoán; nhiều lựa chọn hiện đại còn dùng **memory-hardness**, làm cho thử mật khẩu hàng loạt trên phần cứng song song tốn kém hơn.

Một password hash an toàn vẫn **không thể biến mật khẩu yếu thành bí mật entropy cao**. Cần kết hợp chính sách mật khẩu, kiểm tra mật khẩu phổ biến/bị lộ, rate limit, MFA và phát hiện đăng nhập bất thường.

### 4.2. Argon2id, scrypt, PBKDF2 và HKDF

- **Argon2id:** Password hashing/KDF memory-hard phổ biến; thường là lựa chọn ưu tiên cho hệ thống mới khi môi trường và chính sách cho phép. Cần điều chỉnh **memory cost, time cost và parallelism** theo hiệu năng/độ an toàn thực tế.
- **scrypt:** Password KDF memory-hard, có thể sử dụng khi đáp ứng yêu cầu nền tảng và chính sách.
- **PBKDF2-HMAC-SHA-256:** Password KDF dựa trên HMAC với số vòng lặp; có sẵn trong JCA/JCE phổ biến. Phù hợp trong môi trường cần tương thích hoặc yêu cầu cụ thể nhưng phải cấu hình và đánh giá cost; không có đặc tính memory-hard như Argon2id/scrypt.
- **HKDF:** Rất hữu ích để dẫn xuất các khóa từ **nguồn vật liệu bí mật phù hợp**. **Không dùng HKDF đơn độc như cơ chế làm chậm đoán mật khẩu** trong lưu verifier hay dẫn xuất KEK từ password dễ đoán.

**Không dùng chung đầu ra password verifier làm KEK.** Nếu giá trị verifier được lưu trong database và cũng chính là KEK, người có database có thể giải bọc DEK **mà không cần đoán mật khẩu**. Dùng hai quá trình với **salt/label/mục đích độc lập** hoặc một thiết kế KDF có domain separation được đánh giá kỹ, bảo đảm vật liệu khóa giải mã **không xuất hiện trong bản ghi xác thực**.

### 4.3. Salt và pepper

**Salt** nên được tạo ngẫu nhiên cho từng password verifier hoặc từng mục đích dẫn xuất, thường tối thiểu 16 byte khi phù hợp thiết kế. Salt **không phải bí mật** và phải được giữ cùng algorithm, version, parameters để xác minh.

**Pepper** là bí mật cấp hệ thống có thể được dùng bổ sung nhằm tăng chi phí khi chỉ database bị lộ, ví dụ dùng HMAC có khóa pepper lên kết quả password hashing theo thiết kế được đánh giá. Pepper phải nằm ngoài database cùng verifier, trong secret manager/KMS/HSM thích hợp, với chính sách truy cập và rotation riêng.

Pepper **không thay thế salt**, không làm phép SHA-256(password) thành một cấu trúc password hashing mạnh, và việc xoay pepper có thể phải xác minh lại từng mật khẩu hoặc triển khai chuyển đổi có kiểm soát theo sơ đồ đã chọn.

## 5. Password reset cho xác thực tài khoản: luồng an toàn

Đây là trường hợp **mật khẩu chỉ là thông tin xác thực**, không dùng để mở một DEK vốn chỉ có thể truy cập qua mật khẩu cũ.

### Các bước cơ bản

1. **Nhận yêu cầu quên mật khẩu** với định danh tài khoản như email; không tiết lộ tài khoản tồn tại hay không qua thông báo/trạng thái đáp ứng.
2. **Kiểm soát lạm dụng** bằng giới hạn tần suất theo tài khoản/nguồn, phát hiện bot, giám sát và cơ chế phù hợp; không tạo cơ chế khóa tài khoản cho phép người ngoài cố tình gây từ chối dịch vụ.
3. **Phát hành reset token ngẫu nhiên khó đoán**, đủ entropy (ví dụ **32 byte từ CSPRNG**), chỉ trao qua kênh phục hồi đã được kiểm soát.
4. **Lưu dạng bảo vệ của token** trên server, chẳng hạn SHA-256 của token ngẫu nhiên có entropy cao, kèm user ID, thời điểm hết hạn, loại mục đích và trạng thái đã dùng. Không cần dùng Argon2id cho token ngẫu nhiên thật sự đủ entropy; bài toán khác mật khẩu người dùng.
5. **Gửi liên kết qua kênh được chọn**, ví dụ email đã xác minh; tránh link tùy tiện hình thành từ `Host` header chưa kiểm tra, tránh chuyển hướng mở và không đặt token trong log/analytics.
6. **Xác minh token**: đúng mục đích, chưa hết hạn, chưa bị dùng/thu hồi, đúng tài khoản/quy trình; tiêu thụ token **một lần theo cơ chế nguyên tử** để chặn hai yêu cầu đồng thời cùng thành công.
7. **Nhận mật khẩu mới** qua HTTPS, kiểm tra chính sách và mật khẩu đã bị lộ/phổ biến nếu áp dụng; hash bằng password KDF với salt mới và parameters phù hợp.
8. **Cập nhật credential**, đánh dấu token đã dùng và cập nhật trạng thái bảo mật trong một giao dịch hoặc cơ chế tương đương có tính nhất quán.
9. **Vô hiệu hóa session/refresh token hoặc yêu cầu tái xác thực** theo chính sách; tránh tự đăng nhập ngay chỉ vì có reset token, đặc biệt với tài khoản rủi ro cao.
10. **Thông báo cho chủ tài khoản** rằng mật khẩu đã thay đổi qua kênh độc lập khi khả thi, ghi audit và cảnh báo hoạt động bất thường. Không gửi mật khẩu mới trong email.

~~~mermaid
sequenceDiagram
    participant User as Người dùng
    participant App as Account service
    participant DB as Credential/Reset store
    participant Channel as Kênh phục hồi
    User->>App: Yêu cầu reset
    App->>DB: Kiểm tra giới hạn, phát hành token entropy cao nếu phù hợp
    DB-->>App: Metadata reset + token digest
    App->>Channel: Gửi liên kết reset qua kênh được chấp nhận
    App-->>User: Phản hồi chung, không lộ trạng thái tài khoản
    User->>App: Token + mật khẩu mới qua HTTPS
    App->>DB: Xác minh token, kiểm tra TTL và dùng một lần
    App->>App: Password KDF + salt mới
    App->>DB: Giao dịch: cập nhật verifier, tiêu thụ token
    App->>DB: Thu hồi phiên/refresh token theo chính sách
    App-->>User: Kết quả + thông báo an ninh
~~~

### Tính một lần phải được bảo đảm ở server

Không thể chỉ làm:

~~~text
if resetToken.used == false:
    resetToken.used = true
    updatePassword()
~~~

mà không xét **race condition**. Hai yêu cầu đồng thời có thể cùng đọc `used=false`. Nên thiết kế cơ chế tiêu thụ token atomically, trong transaction đảm bảo tính nhất quán. Ví dụ **mã giả SQL khái niệm**:

~~~sql
BEGIN;

-- Chỉ một yêu cầu được phép đánh dấu token còn hiệu lực là đã sử dụng.
-- Cú pháp RETURNING và cơ chế khóa hàng phụ thuộc hệ quản trị CSDL.
UPDATE password_reset_request
SET consumed_at = CURRENT_TIMESTAMP
WHERE token_digest = :sha256_of_submitted_token
  AND purpose = 'password_reset'
  AND consumed_at IS NULL
  AND expires_at > CURRENT_TIMESTAMP
RETURNING user_id;

-- Yêu cầu cập nhật đúng một token hợp lệ; nếu không, ROLLBACK.
-- Sau đó tạo password verifier mới với salt/parameters mới.
UPDATE user_credentials
SET password_hash_record = :new_phc_or_equivalent_record
WHERE user_id = :validated_user_id;

COMMIT;
~~~

Trong hệ thống thật, cần xử lý việc `user_id` bị thay đổi hoặc xóa, các giao dịch lồng ghép, rollback khi lưu verifier thất bại và lịch sử token cùng danh tính được ủy quyền. Không copy mã giả trên vào một DB không hỗ trợ `RETURNING`; triển khai transaction theo dialect phù hợp.

### Reset token phải có giới hạn quyền

Reset token chỉ là quyền **thực hiện hành động reset cụ thể**, không phải quyền xem hồ sơ, giải mã dữ liệu hay gọi KMS. Nên gắn token với một mục đích và tài khoản, hết hạn ngắn theo chính sách, bị vô hiệu hóa sau khi dùng. Đừng dùng cùng token cho **reset MFA, đổi email, xác thực thanh toán hoặc xuất recovery key** nếu không có thiết kế xác thực/phê duyệt tách biệt.

## 6. Chi tiết bảo mật cho reset link và kênh khôi phục

### 6.1. Không lộ tài khoản tồn tại

Thông báo cho người yêu cầu nên có nội dung tương đương: “Nếu tài khoản phù hợp tồn tại, hướng dẫn sẽ được gửi qua kênh đã đăng ký.” Cần giảm cả **sự khác biệt về HTTP status, timing và hành vi rate limit** có thể làm lộ sự tồn tại của email.

Đây không phải lý do để bỏ qua quan sát nội bộ. Hệ thống vẫn cần audit có phân quyền để phát hiện email bị spam, enumeration và yêu cầu reset không bình thường.

### 6.2. Chống rò rỉ reset token trong URL

Token trong link có thể bị lộ qua browser history, reverse proxy log, analytics, Referer header tới tài nguyên bên thứ ba, extension hoặc ảnh chụp màn hình. Các biện pháp:

- Chỉ dùng **HTTPS/HSTS** và origin reset cố định được cấu hình, không xây link từ header do client kiểm soát.
- Không nhúng script/ảnh bên thứ ba vào trang chứa reset token nếu không có biện pháp giảm rủi ro; dùng **Referrer-Policy** phù hợp như `no-referrer`.
- Sau khi token được xác minh bước đầu, có thể chuyển sang trạng thái phiên reset ngắn hạn được bảo vệ, rồi **loại token khỏi URL** theo thiết kế.
- Không log query string chứa token; lọc secret khỏi APM, crash reports và email support/ticket.
- Chống **CSRF** và thay đổi trạng thái trái phép trong luồng reset; token trong link và CSRF token giải quyết các bài toán khác nhau.

### 6.3. MFA và phương thức phục hồi cấp cao

Với tài khoản quản trị hoặc tài khoản có quyền xuất khóa/giải mã dữ liệu nhạy cảm, reset mật khẩu có thể là bước **khôi phục quyền lực rất lớn**. Không được coi email access là bằng chứng đủ để vượt qua mọi yêu cầu MFA mà không có chính sách. Tổ chức có thể cần recovery codes, thiết bị đã đăng ký, thủ tục xác minh độc lập hoặc phê duyệt nhiều người.

**MFA recovery** nên được xem là quy trình riêng, có mức bảo đảm tương ứng, tránh biến chức năng quên mật khẩu thành đường vòng bỏ qua MFA, passkeys hoặc xác thực mạnh.

## 7. Thay mật khẩu khi còn mật khẩu cũ: rewrap DEK đúng cách

Nếu dữ liệu được mã hóa bằng **DEK ngẫu nhiên** và DEK được bọc bằng **KEK dẫn xuất từ mật khẩu cũ**, luồng đổi mật khẩu có thể được thực hiện mà không mã hóa lại từng bản ghi:

1. Người dùng xác thực lại theo chính sách và cung cấp **mật khẩu cũ** (hoặc có đường giải bọc độc lập hợp lệ).
2. Dẫn xuất **old KEK** từ mật khẩu cũ với **salt, algorithm, parameters và version cũ** đã lưu.
3. Dùng old KEK **giải bọc DEK** với cơ chế có kiểm tra tính toàn vẹn. Nếu giải bọc thất bại, **không** cập nhật credential hoặc ghi đè wrapped DEK.
4. Sinh **salt mới** và dẫn xuất **new KEK** từ mật khẩu mới bằng password KDF được phê duyệt, tách biệt với verifier đăng nhập.
5. Bọc lại **cùng DEK** bằng new KEK với key wrapping hoặc AEAD được định nghĩa. Nếu dùng AEAD để bọc, tạo nonce mới, quản lý AAD và tag đúng quy tắc.
6. Cập nhật **wrapped DEK mới + KDF metadata + password verifier mới** theo giao dịch hoặc quy trình nguyên tử/khôi phục nhất quán.
7. Thử giải bọc với mật khẩu mới trong một luồng được kiểm soát, thu hồi bản bọc/phiên cũ theo chính sách, xóa các bản sao KEK/DEK dạng rõ trong phạm vi có thể.

~~~mermaid
flowchart LR
    Old[Password cũ] --> O[Password KDF với salt cũ]
    O --> OK[Old KEK]
    W[(Wrapped DEK cũ)] --> U[Unwrap + kiểm tra toàn vẹn]
    OK --> U
    U --> D[DEK không đổi]
    New[Password mới] --> N[Password KDF với salt mới]
    N --> NK[New KEK]
    D --> R[Rewrap DEK]
    NK --> R
    R --> W2[(Wrapped DEK mới + metadata)]
~~~

**Rewrap không nhất thiết là re-encrypt.** Nếu DEK của dữ liệu không đổi, bản mã dữ liệu và nonce/IV tương ứng thường có thể giữ nguyên. Tuy nhiên, nếu old KEK hoặc DEK bị nghi **lộ cho kẻ tấn công**, chỉ rewrap không xóa bỏ khả năng họ đã giữ DEK hoặc plaintext. Khi đó cần **đánh giá thay DEK và mã hóa lại dữ liệu**, cùng phạm vi exfiltration và backup.

### Tách password verifier khỏi password-derived KEK

Ngay cả khi cùng một mật khẩu người dùng cấp hai mục đích, nên thiết kế **đường dẫn xuất riêng** và không lưu kết quả KEK trong database. Ví dụ:

~~~text
authVerifier = PasswordHash(
    password,
    authSalt,
    authParameters
)

wrapKEK = PasswordKDF(
    password,
    wrapSalt,
    wrapParameters,
    context="data-wrap/v1" theo sơ đồ hỗ trợ
)
~~~

Nếu KDF không có tham số `context` chuẩn hóa, sử dụng **salt độc lập** và định nghĩa cơ chế domain separation được đánh giá; không tự thêm một chuỗi vào password rồi giả định đã an toàn. Thông số và cách biểu diễn các trường cần tuân theo thuật toán/KDF thực tế.

## 8. Quên mật khẩu cũ khi dữ liệu bị khóa theo password

Đây là tình huống đòi quyết định kiến trúc và chính sách rõ ràng.

| Thiết kế | Server có thể reset credential? | Có thể truy cập lại dữ liệu cũ khi mất password cũ? |
| --- | --- | --- |
| **Xác thực bằng password verifier; dữ liệu dùng DEK trong KMS** | Có | Có thể, nếu danh tính đã phục hồi được cấp quyền KMS theo chính sách |
| **Password-derived KEK là đường duy nhất để unwrap DEK** | Có thể cập nhật verifier | **Không**, nếu không còn password, KEK cũ, recovery secret hoặc bản DEK hợp lệ |
| **Wrapped DEK có thêm recovery key được người dùng lưu** | Có | Có, nếu người dùng còn recovery key và cơ chế unwrap hợp lệ |
| **Wrapped DEK có thêm recovery key trong KMS của tổ chức** | Có | Có, nếu tổ chức được phép và đủ kiểm soát sử dụng recovery KEK |
| **Thiết bị khác còn phiên/khóa phục hồi hợp lệ** | Có | Có thể, nếu giao thức hỗ trợ xuất/rewrap DEK có kiểm soát |
| **Người dùng mất mọi recovery path trong hệ thống zero-knowledge** | Có thể | Không nên hứa khôi phục được dữ liệu |

### Hai phương án quản trị phổ biến

**Phương án ưu tiên phục hồi nghiệp vụ:** Hệ thống giữ một recovery wrap do KMS/HSM quản lý, với MFA, dual control hoặc phê duyệt theo chính sách để dùng. Cần nói rõ nhà vận hành có **khả năng kỹ thuật phục hồi**, hạn chế quyền, audit và quản lý rủi ro nội bộ.

**Phương án ưu tiên bí mật đầu cuối:** Hệ thống không giữ recovery key giải mã. Người dùng được cung cấp recovery code/secret có entropy cao hoặc thiết bị ủy quyền để tự quản lý; khi mất tất cả đường phục hồi, dữ liệu có thể **không thể lấy lại**. Cần truyền đạt điều này trước khi người dùng lưu dữ liệu quan trọng.

Không có một công thức KDF nào biến password mới thành old KEK khi không biết password cũ hoặc vật liệu phục hồi. Nếu một sản phẩm tuyên bố “server hoàn toàn không có khóa mà vẫn khôi phục toàn bộ dữ liệu đã mã hóa chỉ từ email reset”, cần xem xét **đường phục hồi ẩn hoặc giới hạn của tuyên bố zero-knowledge**.

## 9. Ví dụ Java: PBKDF2 và token reset ngẫu nhiên

Ví dụ sau nhằm làm rõ hai bài toán riêng: **dẫn xuất từ password** bằng PBKDF2-HMAC-SHA-256 và **tạo token reset** bằng CSPRNG rồi lưu **digest của token**. Java SE phổ biến hỗ trợ PBKDF2; trong hệ thống mới nên đánh giá **Argon2id** với thư viện đã được thẩm định khi chính sách cho phép.

**Không coi số vòng lặp trong ví dụ là ngưỡng chuẩn production**; phải benchmark và cập nhật theo môi trường, mô hình tấn công và hướng dẫn hiện hành. Đoạn mã chưa có persistence, email, CSRF, MFA, database transaction, rate limit hoặc quá trình reset hoàn chỉnh.

~~~java
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.MessageDigest;
import java.security.SecureRandom;
import java.util.Arrays;
import java.util.Base64;
import javax.crypto.SecretKeyFactory;
import javax.crypto.spec.PBEKeySpec;

public final class PasswordResetKdfDemo {
    private static final SecureRandom RNG = new SecureRandom();

    static byte[] randomBytes(int size) {
        byte[] out = new byte[size];
        RNG.nextBytes(out);
        return out;
    }

    static byte[] deriveWithPbkdf2(
            char[] password, byte[] salt, int iterations)
            throws GeneralSecurityException {
        if (salt == null || salt.length < 16 || iterations < 1) {
            throw new IllegalArgumentException("Invalid KDF parameters");
        }

        PBEKeySpec spec = new PBEKeySpec(
                password, salt, iterations, 256); // output 256 bit
        try {
            return SecretKeyFactory
                    .getInstance("PBKDF2WithHmacSHA256")
                    .generateSecret(spec)
                    .getEncoded();
        } finally {
            spec.clearPassword();
        }
    }

    static byte[] sha256(byte[] value)
            throws GeneralSecurityException {
        return MessageDigest.getInstance("SHA-256").digest(value);
    }

    public static void main(String[] args) throws Exception {
        // CHỈ ĐỂ DEMO: password thật không được hard-code.
        char[] password = { 'D', 'e', 'm', 'o', '-', 'N', 'o', 't', '-', 'R', 'e', 'a', 'l' };
        byte[] authSalt = randomBytes(16);
        int demoIterations = 100_000; // không phải khuyến nghị production

        byte[] verifier = deriveWithPbkdf2(
                password, authSalt, demoIterations);
        byte[] again = deriveWithPbkdf2(
                password, authSalt, demoIterations);

        System.out.println("Verifier matches: "
                + MessageDigest.isEqual(verifier, again));

        // Reset token là dữ liệu NGẪU NHIÊN entropy cao,
        // không phải mật khẩu do con người chọn.
        byte[] rawToken = randomBytes(32);
        String resetToken = Base64.getUrlEncoder()
                .withoutPadding()
                .encodeToString(rawToken);

        // Lưu token digest, userId, expiresAt, usedAt ở DB,
        // chỉ gửi resetToken qua kênh phục hồi được chấp nhận.
        byte[] tokenDigestForStorage = sha256(
                resetToken.getBytes(StandardCharsets.US_ASCII));

        // Minh họa kiểm tra digest; TTL, one-time và transaction
        // bắt buộc được thực thi riêng ở tầng lưu trữ.
        byte[] receivedDigest = sha256(
                resetToken.getBytes(StandardCharsets.US_ASCII));
        System.out.println("Reset token digest matches: "
                + MessageDigest.isEqual(
                        tokenDigestForStorage, receivedDigest));

        // Best effort đối với các mảng do ứng dụng quản lý.
        Arrays.fill(password, '\0');
        Arrays.fill(verifier, (byte) 0);
        Arrays.fill(again, (byte) 0);
        Arrays.fill(rawToken, (byte) 0);
        Arrays.fill(tokenDigestForStorage, (byte) 0);
        Arrays.fill(receivedDigest, (byte) 0);

        // Không in resetToken hoặc giá trị dẫn xuất ra log.
    }
}
~~~

### Cách hiểu đúng ví dụ

- Password được người dùng đặt nên cần password KDF **có chi phí tính toán**. Trong demo, PBKDF2 tạo 32 byte đầu ra; ở production, phải dùng thuật toán và parameters được chính sách phê duyệt.
- Reset token được tạo từ **32 byte CSPRNG** và có entropy cao. Lưu SHA-256 digest cho token ngẫu nhiên là khác với việc lưu SHA-256(password) vốn có nguy cơ đoán offline.
- `Base64.getUrlEncoder().withoutPadding()` chỉ mã hóa biểu diễn cho URL; **không mã hóa bảo mật token**. Bảo mật đến từ entropy, TTL, phạm vi và tính một lần.
- `MessageDigest.isEqual()` hỗ trợ so sánh giá trị nhạy cảm theo cách phù hợp hơn so với tự dùng so sánh byte dừng sớm; tầng database vẫn cần bảo đảm chọn đúng bản ghi và xử lý giao dịch.
- Xóa `char[]` và `byte[]` chỉ **best effort**: Java runtime/provider và `String resetToken` có thể có bản sao trong bộ nhớ không xóa trực tiếp được.
- Không dùng cùng `verifier` trong ví dụ làm **KEK giải mã dữ liệu**. Luồng dẫn xuất KEK cần thiết kế độc lập, salt riêng, kiểm tra toàn vẹn khi unwrap và cơ chế recovery phù hợp.

## 10. Lưu metadata KDF và wrapped DEK đúng cách

Trong password hashing, cần lưu đủ thông tin để **kiểm tra và nâng cấp** password verifier. Một bản ghi khái niệm:

~~~yaml
userId: user-123
passwordVerifier:
  algorithm: argon2id
  version: "profile-2026-01"
  parameters:
    memoryCost: "<theo chính sách đã benchmark>"
    timeCost: "<theo chính sách đã benchmark>"
    parallelism: "<theo chính sách đã benchmark>"
  salt: "<bytes mã hóa Base64>"
  hash: "<bytes mã hóa Base64>"

encryption:
  dekId: "user-123-data-key"
  wrappedDek:
    algorithm: "được KMS hoặc thư viện phê duyệt"
    kdfAlgorithm: "argon2id hoặc password KDF đã chọn"
    kdfParameters: "<tham số riêng cho chức năng wrap>"
    wrapSalt: "<salt độc lập với passwordVerifier.salt>"
    wrappedKey: "<bytes>"
    nonceAndTag: "<nếu thuật toán wrap/AEAD yêu cầu>"
  recoveryWrap: "<chỉ nếu đã thiết kế và phê duyệt recovery path>"
~~~

Đây là **mô hình dữ liệu minh họa**, không phải cấu hình có thể chạy hoặc gói JSON/YAML production. Với Argon2id password verifier, nhiều thư viện hỗ trợ **định dạng encoded hash chuẩn** chứa tham số, salt và kết quả; ưu tiên khả năng nâng cấp và tính tương thích của thư viện đã chọn. **Không đặt giá trị bí mật thật** trong bản mẫu, log hay tài liệu hướng dẫn.

Với dữ liệu đã mã hóa cần giữ:

- `keyId`, `keyVersion` của DEK/KEK tương ứng;
- thuật toán và tham số AEAD/key wrap, cùng IV/nonce/tag nếu có;
- AAD/context ràng buộc với đúng dữ liệu, tenant, version và mục đích;
- phiên bản KDF, salt và policy để khôi phục **đúng khóa**, không phụ thuộc cấu hình mặc định hiện tại;
- metadata về đường recovery, trạng thái và retention.

**Không đồng nhất thay đổi tham số password KDF với việc có thể tính lại KEK cũ.** Khi nâng cấp parameters dùng bảo vệ DEK, cần giải bọc bằng **thông số cũ** rồi bọc lại theo thông số mới, tương tự quy trình đổi mật khẩu.

## 11. Quản lý khóa trong KMS/HSM và phân tách quyền

Khi KMS/HSM tham gia quản lý DEK, KEK hoặc recovery KEK, mỗi vai trò có phạm vi quyền riêng:

| Vai trò | Trách nhiệm thường gặp | Không nên mặc nhiên có |
| --- | --- | --- |
| **Key owner** | Chọn yêu cầu phục hồi, cryptoperiod, retention, mức rủi ro, quy trình reset nhạy cảm | Quyền tự xuất DEK hoặc bỏ qua phê duyệt |
| **Key custodian** | Tạo/cấu hình khóa, quản lý IAM/key policy, rotation, vô hiệu hóa và hủy theo phê duyệt | Quyền tự yêu cầu recovery trái mục đích |
| **Account service** | Xác minh reset token và cập nhật password verifier | Quyền giải mã toàn bộ dữ liệu nếu không cần |
| **Encryption service** | `Encrypt`, `Decrypt`, `Wrap`, `Unwrap` theo đúng key ID và tenant | Quyền tự sửa policy hoặc xóa khóa |
| **Recovery operator/service** | Kích hoạt đường recovery có kiểm soát, ghi nhận chấp thuận và điều kiện | Quyền khôi phục mọi DEK bằng một thao tác không kiểm soát |
| **Security/auditor** | Rà soát sự kiện, trách nhiệm và bằng chứng phục hồi | Khả năng tự sửa log hoặc dùng key material |

Một tài khoản vừa được reset mật khẩu **không nên tự động nhận lại mọi quyền nhạy cảm** mà không có bước đánh giá cần thiết. Với quyền xuất dữ liệu đặc biệt, sử dụng recovery KEK, thay email phục hồi hoặc thu hồi MFA, có thể yêu cầu **step-up authentication**, giới hạn thời gian, nhiều người phê duyệt hoặc trì hoãn theo chính sách.

### Liên hệ với envelope encryption

Hệ thống có thể dùng **AES-GCM** để mã hóa dữ liệu bằng DEK ngẫu nhiên; DEK được bọc bởi KEK trong KMS. Password reset của tài khoản truy cập hệ thống chỉ thay đổi quyền xác thực, **không tự thay DEK/KEK**. Nhưng nếu password-derived KEK là một đường wrap của DEK, thì cần rewrap khi đổi mật khẩu; muốn reset khi quên password cũ phải có đường recovery độc lập.

**Chữ ký số** cũng là khía cạnh riêng: reset mật khẩu tài khoản không tự thu hồi private signing key, chứng thư hay chữ ký đã tạo. Nếu người dùng có chứng thư để ký hóa đơn/artefact, cần chính sách xác thực việc sử dụng private signing key, xử lý khóa bị lộ và cập nhật chứng thư độc lập với mật khẩu login.

## 12. Xử lý sự cố và vòng đời khóa khi reset

Một yêu cầu reset có thể là hoạt động bình thường, cũng có thể là tín hiệu **account takeover**, credential stuffing hoặc đường vòng tấn công dữ liệu mã hóa.

### Một kịch bản cụ thể

Giả sử tài khoản dùng email để nhận reset link và DEK của khách hàng được bọc bằng recovery KEK trong KMS. Kẻ tấn công chiếm được hộp thư, reset password thành công và tìm cách yêu cầu hệ thống phục hồi DEK.

Nếu account service xem việc reset email là đủ để cấp **quyền Unwrap bằng recovery KEK**, đối thủ có thể lấy dữ liệu dù không biết password cũ. Đây là lý do cần **phân tách chứng minh quyền kiểm soát email khỏi quyền khôi phục vật liệu khóa**, đặc biệt với dữ liệu nhạy cảm.

**Biện pháp:** xác minh yếu tố mạnh độc lập khi yêu cầu recovery, giới hạn quyền KMS, phát hiện bất thường, phê duyệt đối với trường hợp rủi ro cao, audit và thông báo ngoài băng khi thích hợp.

### Phân loại sự cố và hành động

| Tình huống | Nguy cơ | Hành động ưu tiên |
| --- | --- | --- |
| Có nhiều yêu cầu reset bất thường | Enumeration, quấy rối, dò quyền | Rate limit, giám sát, không lộ trạng thái tài khoản |
| Reset token lộ trước khi sử dụng | Account takeover trong TTL | Thu hồi token, điều tra log/kênh rò rỉ, tăng bảo vệ reset |
| Mật khẩu cũ bị lộ nhưng DEK chưa chắc bị lộ | Đoán/đăng nhập trái phép, nguy cơ unwrap nếu có wrapped DEK | Thay credential, rà soát phiên, đánh giá có phải xoay KEK/DEK |
| Attacker đã lấy **old KEK hoặc DEK** | Có thể đã giải mã dữ liệu cũ | Không chỉ rewrap; đánh giá rotate DEK/re-encrypt, ảnh hưởng và thông báo |
| Recovery KEK trong KMS bị lạm dụng | Mở rộng phạm vi truy cập dữ liệu nhiều người | Cô lập quyền, điều tra event KMS, thay/thu hồi đường recovery nếu cần |
| Không còn password cũ hay recovery path | Không thể giải bọc DEK | Không hứa khôi phục; thực thi chính sách mất dữ liệu/khôi phục từ đường hợp lệ khác |
| KMS key bị hủy nhầm | Dữ liệu có thể mất khả năng giải mã vĩnh viễn | Kiểm kê phụ thuộc, retention, backup và phê duyệt trước khi hủy |

### Vòng đời thành phần liên quan

- **Password verifier:** cập nhật khi đổi/reset mật khẩu, nâng cấp password KDF khi người dùng đăng nhập hợp lệ hoặc qua quy trình di chuyển được đánh giá.
- **Reset token:** tạo, cấp qua kênh phục hồi, hết hạn nhanh, dùng một lần, thu hồi/hủy sau sử dụng; chỉ giữ log metadata an toàn.
- **Password-derived KEK:** dẫn xuất theo phiên/mục đích, không ghi rõ ra DB/log; sau reset/change chỉ dùng KEK mới khi đã thực hiện rewrap hợp lệ.
- **DEK:** có cryptoperiod, key ID/version, chính sách AEAD nonce, retention và khả năng giải mã dữ liệu cũ. **Đổi password không mặc nhiên là đổi DEK**.
- **Recovery KEK:** cần chính sách truy cập riêng, backup/HA/DR, dual control khi thích hợp, audit và kế hoạch thay thế khi bị lộ.
- **Signing key/private key:** có thể liên quan xác thực hoặc ký giao dịch, nhưng không nên xử lý vòng đời chỉ bằng thay mật khẩu đăng nhập.

## 13. Những sai lầm phổ biến

| Sai lầm | Hậu quả | Cách phòng tránh |
| --- | --- | --- |
| Coi password reset là tự động khôi phục dữ liệu E2EE | Hứa sai tính năng hoặc làm mất dữ liệu khi cập nhật wrapped DEK | Phân biệt authentication và encryption; thiết kế recovery path từ đầu |
| Lưu `SHA-256(password)` làm verifier | Dò mật khẩu offline nhanh nếu database bị lộ | Password KDF mạnh + salt riêng + chính sách bổ sung |
| Dùng HKDF đơn độc để “làm chậm” đoán mật khẩu | Không tăng chi phí guess theo ý định | Argon2id/scrypt/PBKDF2 được cấu hình phù hợp |
| Lấy password verifier đã lưu làm KEK | Lộ verifier đồng nghĩa lộ khóa giải mã | Tách mục đích và đường dẫn xuất; không lưu KEK trong DB |
| Giữ nguyên salt và parameters nhưng mặc định đầu ra KDF không đổi khi password đổi | Đọc dữ liệu cũ không được hoặc sai key wrapping | Dùng old KEK unwrap, new KEK rewrap, lưu metadata |
| Đổi password rồi xóa wrapped DEK cũ trước khi verify | Không thể khôi phục sau crash/sự cố | Giao dịch nhất quán, kiểm thử trước commit và recovery strategy |
| Reset token quá ngắn, dùng timestamp/UUID yếu | Có thể đoán token | CSPRNG với entropy cao, TTL, hạn mức và dùng một lần |
| Lưu reset token dạng rõ | Database leak cho phép reset tài khoản | Lưu token digest, không ghi token vào log |
| Token dùng nhiều lần hoặc không xử lý race condition | Nhiều yêu cầu reset cùng hợp lệ | Atomic consume + transaction |
| Trả “email không tồn tại” | Liệt kê tài khoản | Phản hồi chung, giảm khác biệt timing/trạng thái |
| Link reset dựa trên Host header đầu vào | Reset URL bị tiêm domain độc hại | Origin cấu hình cố định và allowlist |
| Cho phép reset email rồi lập tức `Unwrap` recovery DEK | Chiếm email dẫn tới giải mã dữ liệu | Recovery policy/step-up riêng và audit KMS |
| Chỉ thay password khi nghi DEK đã lộ | Đối thủ vẫn có thể giữ DEK hoặc plaintext | Đánh giá khóa/dữ liệu đã lộ và thực hiện rotate/re-encrypt khi cần |
| Xóa KMS/recovery KEK khi còn backup cũ | Không thể mở dữ liệu lưu trữ | Inventory phụ thuộc, kiểm thử restore, retention trước khi hủy |
| Mã hóa mật khẩu bằng khóa đối xứng để “xác thực” | Server giữ khả năng giải mã password, tăng rủi ro | Lưu password verifier bằng password hashing đúng mục đích |

## 14. Checklist thiết kế và vận hành

Trước khi đưa chức năng **Password reset và key derivation** vào production, đội kỹ thuật nên kiểm tra:

1. **Phân biệt mục đích:** Mật khẩu chỉ xác thực hay còn dẫn xuất KEK giải mã dữ liệu? Tài liệu có ghi rõ hậu quả khi quên mật khẩu?
2. **Password hashing:** Có thuật toán password KDF được phê duyệt, salt riêng, parameters được benchmark, định dạng có version và kế hoạch nâng cấp?
3. **Tách khóa:** Password verifier, password-derived KEK, DEK, recovery KEK và signing key có được tách về chức năng và quyền không?
4. **Token reset:** Token đủ entropy, lưu digest, mục đích giới hạn, TTL hợp lý, **atomic single-use** và không xuất hiện trong log/analytics?
5. **Kênh phục hồi:** Reset URL từ origin tin cậy, HTTPS, không lộ email tồn tại, chống spam/rate limit và xử lý token rò rỉ?
6. **MFA/step-up:** Reset tài khoản quản trị hay quyền khôi phục khóa có yêu cầu xác thực mạnh hơn việc sở hữu email không?
7. **Đổi mật khẩu:** Nếu có password-wrapped DEK, quy trình có thể dùng old KEK unwrap, new KEK rewrap, salt mới và kiểm tra toàn vẹn không?
8. **Quên mật khẩu:** Nếu không có old KEK, hệ thống có **recovery path thực sự độc lập** hay phải báo dữ liệu không thể phục hồi?
9. **Tính nhất quán:** Cập nhật verifier và wrapped DEK có giao dịch/chiến lược khôi phục không? Retry có làm mất bản bọc còn hợp lệ?
10. **KMS/HSM:** Có key owner/custodian, IAM least privilege, audit và phê duyệt riêng cho `Unwrap` bằng recovery KEK?
11. **Mã hóa dữ liệu:** DEK dùng AEAD đúng nonce, key ID/version, dữ liệu cũ và backup vẫn truy cập được theo chính sách?
12. **Khóa bị lộ:** Phát hiện lộ password, old KEK, DEK hay recovery KEK có dẫn tới đúng quy trình rotate/re-encrypt và đánh giá sự cố?
13. **Session và thông báo:** Reset có thu hồi phiên thích hợp, gửi cảnh báo bảo mật và không tự động trao quyền nhạy cảm ngoài dự kiến?
14. **Kiểm toán:** Có log request/complete reset, thay credential, sự kiện recovery, thao tác KMS mà không ghi token, password, KEK/DEK hay plaintext?

### Ghi nhớ

**Password reset** là quá trình khôi phục quyền thiết lập mật khẩu mới; **key derivation** là cách sinh vật liệu mật mã từ đầu vào. Nếu mật khẩu **chỉ dùng xác thực**, reset verifier có thể độc lập với DEK/KEK trong KMS. Nếu mật khẩu **dùng dẫn xuất KEK để mở DEK**, đổi mật khẩu có thể thực hiện bằng **unwrap rồi rewrap**, nhưng quên mật khẩu cũ đòi một **đường phục hồi độc lập**; nếu không có, dữ liệu có thể không thể giải mã. Sử dụng password KDF phù hợp (**Argon2id, scrypt hoặc PBKDF2 theo chính sách**), không nhầm với **HKDF**, bảo vệ reset token, quản lý quyền KMS/HSM và vòng đời khóa, đồng thời duy trì **kiểm toán, xoay vòng, thu hồi và hủy có kiểm soát**. Đây là cách thiết kế bảo vệ dữ liệu và tài khoản nhất quán thay vì chỉ triển khai một biểu mẫu “Quên mật khẩu?”.
