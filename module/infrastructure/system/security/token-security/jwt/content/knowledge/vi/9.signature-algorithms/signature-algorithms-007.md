# Entropy của khóa HMAC và nguy cơ dùng mật khẩu làm khóa

## 1. Vì sao khóa HMAC phải có entropy cao?

Trong **Security - JSON Web Token (JWT)**, nhóm thuật toán `HS256`, `HS384`, `HS512` dùng HMAC để tạo chữ ký JWS. Bên phát hành và mọi bên xác minh phải biết **cùng một khóa bí mật**. An toàn của chữ ký phụ thuộc trực tiếp vào việc khóa đó khó đoán đến mức nào.

Một khóa có thể đủ dài về số byte nhưng vẫn yếu nếu được tạo từ mật khẩu, tên hệ thống, chuỗi cấu hình quen thuộc hoặc một giá trị có thể đoán. Nếu attacker lấy được một JWT đã ký, họ có thể thử các khóa ứng viên **ngoại tuyến**: tính lại HMAC cho signing input của token và so sánh với chữ ký đã có. Không cần gửi từng lần đoán tới API và cũng không cần làm verifier phát sinh lỗi.

Vì vậy, khóa HMAC dùng cho JWT phải là dữ liệu ngẫu nhiên có entropy cao, được sinh bằng **cryptographically secure pseudorandom number generator (CSPRNG)** và được quản lý như một bí mật có khả năng phát hành token.

Bài học thuộc chương **Thuật toán chữ ký** của module **Security - JSON Web Token (JWT)**. Phạm vi tập trung vào entropy khóa, nguy cơ mật khẩu, tấn công đoán khóa, cách sinh và lưu trữ secret, cũng như vòng đời thay khóa. Nội dung áp dụng chung, không phụ thuộc ngôn ngữ lập trình hay framework.

## 2. Độ dài khóa và entropy là hai khái niệm khác nhau

### 2.1. Độ dài khóa

Độ dài khóa là số byte thực tế được đưa vào thuật toán HMAC. Theo **RFC 7518, mục 3.2**, khóa của mỗi thuật toán HS phải có kích thước ít nhất bằng độ dài đầu ra của hàm băm tương ứng:

| Thuật toán JWS | Hàm băm | Độ dài MAC | Khóa tối thiểu theo JWA |
| --- | --- | ---: | ---: |
| `HS256` | SHA-256 | 32 byte | 32 byte (256 bit) |
| `HS384` | SHA-384 | 48 byte | 48 byte (384 bit) |
| `HS512` | SHA-512 | 64 byte | 64 byte (512 bit) |

Đây là yêu cầu về **độ dài khóa sau khi giải mã về byte**, không phải số ký tự nhìn thấy trong file cấu hình. Một chuỗi Base64 dài 44 ký tự có thể đại diện cho 32 byte; một chuỗi 64 ký tự hex có thể đại diện cho 32 byte. Cần biết ứng dụng đang dùng chuỗi biểu diễn hay byte sau khi giải mã.

### 2.2. Entropy

Entropy mô tả mức độ khó đoán của dữ liệu ngẫu nhiên. Nếu một khóa được chọn đều từ một không gian có N khả năng, entropy tối đa là:

~~~text
H = log2(N) bit
~~~

Nếu mỗi ký tự được chọn độc lập và đồng đều từ bảng chữ cái có A ký tự, chuỗi dài L ký tự có entropy tối đa:

~~~text
H = L * log2(A) bit
~~~

Đây là mô hình lý tưởng khi các lựa chọn thực sự đồng đều và độc lập. Mật khẩu do con người nghĩ ra không đáp ứng giả định này: người dùng thường chọn từ ngữ, mẫu bàn phím, ngày tháng, tên riêng và biến thể quen thuộc. Vì vậy không thể tính entropy thực tế của mật khẩu chỉ bằng cách đếm số ký tự.

**Độ dài đạt chuẩn không tự chứng minh entropy đạt chuẩn.** Ví dụ, chuỗi 32 ký tự ASCII có thể đáp ứng 32 byte cho HS256, nhưng nếu là `correcthorsebatterystaple...`, entropy thực tế có thể thấp hơn rất nhiều so với 256 bit. Ngược lại, 32 byte sinh ngẫu nhiên đồng đều từ CSPRNG có thể cung cấp xấp xỉ 256 bit entropy.

### 2.3. Vì sao hash mật khẩu không tạo ra entropy?

Giả sử lấy mật khẩu yếu rồi tính SHA-256 để thu được 32 byte:

~~~text
K = SHA256(password)
~~~

Đầu ra có đúng 32 byte, nhưng số khả năng của khóa vẫn bị giới hạn bởi số mật khẩu có thể đoán. Hàm băm làm thay đổi biểu diễn, không tạo thêm thông tin ngẫu nhiên. Nếu mật khẩu chỉ có khoảng 30 bit entropy thì kết quả SHA-256 cũng không đột nhiên trở thành khóa có 256 bit entropy.

Tương tự, chuyển mật khẩu sang Base64, hex hoặc nối thêm chuỗi cố định không làm nó khó đoán hơn. **Độ dài đầu ra của hàm băm không phải entropy của đầu vào.**

## 3. Vì sao dùng mật khẩu làm HMAC secret nguy hiểm?

### 3.1. Attacker có thể đoán khóa ngoại tuyến

Một JWS Compact có dạng:

~~~text
header64.payload64.signature64
~~~

Với HS256, signing input chính là:

~~~text
ASCII(header64 + "." + payload64)
~~~

Header và payload thường có thể đọc được vì Base64URL không phải mã hóa bí mật. Chữ ký cũng nằm ngay trong token. Nếu attacker có một token đã ký, họ có thể:

1. Đọc giá trị `alg` để biết thuật toán được sử dụng.
2. Lấy nguyên văn `header64.payload64` làm signing input.
3. Thử một mật khẩu hoặc khóa ứng viên.
4. Tính HMAC bằng khóa ứng viên.
5. So sánh kết quả với chữ ký trong token.
6. Nếu khớp, ứng viên gần như chắc chắn là khóa đã dùng để ký.

Quá trình này diễn ra ngoại tuyến. Attacker có thể dùng wordlist, mật khẩu từng bị lộ, quy tắc thay chữ, tên tổ chức, tên sản phẩm, giá trị mặc định trong mã nguồn hoặc dữ liệu công khai để tạo danh sách đoán.

### 3.2. Ví dụ kiểm tra khóa ứng viên

Mã giả sau chỉ minh họa nguyên lý tấn công ngoại tuyến:

~~~text
function testCandidate(token, candidateKey):
    (header64, payload64, signature64) = splitJws(token)
    header = decodeBase64UrlJson(header64)

    require header.alg == "HS256"

    signingInput = ASCII(header64 + "." + payload64)
    candidateMac = HMAC_SHA256(candidateKey, signingInput)
    receivedMac = BASE64URL_DECODE(signature64)

    return candidateMac == receivedMac
~~~

Attacker không cần quyền gọi endpoint xác minh. Họ chỉ cần token và biết cách HMAC/JWS được cấu tạo. Trong thực tế, kiểm tra một khóa ứng viên có thể được tối ưu bằng phần cứng và chạy song song trên nhiều token.

### 3.3. Khi đoán được khóa, attacker có thể làm gì?

Nếu tìm được secret HMAC, attacker có khả năng tạo chữ ký cho header và payload mới. Họ có thể thử giả mạo:

- `sub`: chủ thể hoặc tài khoản.
- `iss`: issuer.
- `aud`: API nhận token.
- `exp`: thời hạn.
- `scope`, `role` hoặc claims quyền hạn.

Verifier vẫn phải kiểm tra các claims, nhưng nếu secret bị lộ thì attacker có thể tự tạo chữ ký hợp lệ cho các claims giả mạo. Do đó việc xác minh chữ ký không còn chứng minh được token do issuer thật phát hành.

### 3.4. Hết hạn token không ngăn đoán khóa

`exp` giới hạn thời gian token được chấp nhận, nhưng không ngăn attacker thử khóa ngoại tuyến. Một JWT đã hết hạn vẫn có thể cung cấp signing input và MAC để kiểm tra mật khẩu ứng viên.

Vì thế:

- TTL ngắn giúp giảm thời gian sử dụng token bị đánh cắp.
- TTL ngắn **không thay thế** secret có entropy cao.
- Thu hồi token không làm khóa yếu trở nên mạnh.
- Đổi `HS256` thành `HS512` mà vẫn dùng mật khẩu cũ không giải quyết gốc rễ vấn đề.

## 4. Vì sao mật khẩu con người không phải khóa HMAC phù hợp?

### 4.1. Mật khẩu có cấu trúc dễ đoán

Con người thường tạo mật khẩu theo các mẫu:

- Từ trong từ điển hoặc cụm từ phổ biến.
- Tên người, tên công ty, tên ứng dụng, tên dự án.
- Ngày sinh, năm hiện tại, số điện thoại hoặc chuỗi có ý nghĩa.
- Mẫu bàn phím như `qwerty`, `123456`.
- Một từ quen thuộc cộng thêm ký tự `!`, số hoặc năm.
- Mật khẩu tái sử dụng từ dịch vụ khác đã từng bị rò rỉ.

Quy tắc “có chữ hoa, chữ thường, số và ký tự đặc biệt” không bảo đảm entropy cao. `Company2026!` có thể dễ đoán hơn một chuỗi ngẫu nhiên ngắn hơn nhưng được tạo đồng đều.

### 4.2. Ví dụ về độ dài và entropy lý tưởng

Giả sử ký tự được chọn độc lập và đồng đều:

| Cách tạo chuỗi | Độ dài | Entropy lý tưởng xấp xỉ | Nhận xét |
| --- | ---: | ---: | --- |
| 32 ký tự chữ và số từ bảng 62 ký tự | 32 | 190 bit | Có thể đủ 32 byte nhưng chưa đạt 256 bit entropy |
| 32 byte ngẫu nhiên | 32 byte | 256 bit | Đáp ứng mức tối thiểu HS256 |
| 48 byte ngẫu nhiên | 48 byte | 384 bit | Đáp ứng mức tối thiểu HS384 |
| 64 byte ngẫu nhiên | 64 byte | 512 bit | Đáp ứng mức tối thiểu HS512 |
| Một mật khẩu dài do con người tự nghĩ | Tùy ý | Không thể suy ra từ độ dài | Có thể vẫn dễ đoán theo từ điển/mẫu |

Các con số entropy lý tưởng không áp dụng cho mật khẩu tự chọn. Chúng chỉ đúng khi bộ sinh thực sự chọn đều từ không gian nêu trên.

### 4.3. Không dùng secret mặc định hoặc secret mẫu

Các giá trị như:

~~~text
secret
password
change-me
your-256-bit-secret
development-secret
company-name-2026
~~~

chỉ có thể xuất hiện trong tài liệu minh họa hoặc môi trường kiểm thử cô lập. Nếu một giá trị mẫu được giữ nguyên trong production, nó có thể đã xuất hiện công khai trong tài liệu, repository hoặc các bản triển khai khác.

Không dùng secret mặc định của thư viện, ví dụ trên blog, giá trị trong file mẫu hoặc secret được copy từ môi trường development.

## 5. Sinh khóa HMAC đúng cách

### 5.1. Dùng CSPRNG để sinh byte ngẫu nhiên

Khóa cần được sinh từ nguồn ngẫu nhiên an toàn mật mã của hệ điều hành, runtime hoặc dịch vụ quản lý khóa đáng tin cậy. Yêu cầu:

1. Chọn độ dài theo thuật toán JWA.
2. Lấy đúng số byte từ CSPRNG.
3. Không tự viết PRNG, không dùng timestamp, bộ đếm, ID hoặc hàm random không dành cho mật mã.
4. Không dùng seed cố định hoặc seed lấy từ tên máy, tên ứng dụng.
5. Lưu khóa an toàn và kiểm tra rằng mọi bên nhận đúng cùng dãy byte.

Ví dụ tạo khóa ở mức khái niệm:

~~~text
HS256_KEY = CSPRNG(32 bytes)
HS384_KEY = CSPRNG(48 bytes)
HS512_KEY = CSPRNG(64 bytes)
~~~

Không cần khóa có thể ghi nhớ. Máy tính và secret manager được thiết kế để lưu trữ các chuỗi ngẫu nhiên dài.

### 5.2. Biểu diễn khóa bằng Base64 hoặc hex

Khóa ngẫu nhiên thường được lưu dưới dạng Base64/Base64URL hoặc hex để dễ đưa vào cấu hình:

| Dữ liệu gốc | Biểu diễn thường gặp | Điều cần nhớ |
| --- | --- | --- |
| 32 byte | 64 ký tự hex | Giải mã hex sẽ thu được 32 byte |
| 32 byte | 44 ký tự Base64 có padding | Giải mã Base64 sẽ thu được 32 byte |
| 32 byte | 43 ký tự Base64URL không padding | Giải mã Base64URL sẽ thu được 32 byte |
| 48 byte | 96 ký tự hex | Giải mã hex sẽ thu được 48 byte |
| 64 byte | 128 ký tự hex | Giải mã hex sẽ thu được 64 byte |

**Ví dụ quan trọng:** một secret HS256 được tạo từ 32 byte ngẫu nhiên rồi mã hóa Base64URL sẽ có 43 ký tự nếu bỏ padding. 43 ký tự đó là biểu diễn của 32 byte, không phải khóa 43 byte.

Các thành phần phải thống nhất quy ước:

- Cấu hình chứa Base64 hay Base64URL?
- Có padding `=` hay không?
- Ứng dụng giải mã thành byte trước khi gọi HMAC hay dùng nguyên văn chuỗi?
- Có vô tình giải mã hai lần hoặc không giải mã không?

Nếu issuer dùng byte sau khi decode nhưng verifier dùng các ký tự Base64 như UTF-8, MAC sẽ không khớp. Ngược lại, nếu cả hai bên vô tình dùng cùng một quy ước sai, token vẫn có thể hoạt động nhưng kích thước và entropy thực tế cần được đánh giá theo đúng byte đang sử dụng.

### 5.3. Độ dài lớn hơn mức tối thiểu có cần thiết không?

JWA quy định mức tối thiểu cho HS256/384/512 như bảng ở mục 2. Không cần tùy tiện nối nhiều chuỗi hoặc băm đi băm lại để tạo khóa dài hơn. Điều quan trọng là:

- Khóa có đủ entropy.
- Độ dài byte đáp ứng JWA.
- Khóa được sinh từ CSPRNG.
- Khóa được bảo vệ và phân phối đúng cách.

Một chuỗi rất dài nhưng được tạo từ mật khẩu yếu vẫn có entropy thấp. Một khóa ngẫu nhiên đủ độ dài là lựa chọn đúng.

## 6. Hash mật khẩu, KDF và khóa HMAC là các mục đích khác nhau

### 6.1. HMAC không phải password hashing

HMAC là mã xác thực thông điệp dùng khóa bí mật. Nó được thiết kế để tính nhanh và xác minh thông điệp với secret. Đây là đặc tính tốt cho việc ký JWT nhưng không phù hợp để lưu mật khẩu người dùng.

Password hashing/KDF được thiết kế để xử lý mật khẩu con người theo cách làm cho mỗi lần thử đoán tốn chi phí hơn. Các thuật toán như Argon2id, scrypt hoặc PBKDF2 có tham số salt và cost phù hợp với mục đích lưu mật khẩu hoặc dẫn xuất khóa theo một quy trình được thiết kế riêng.

Không dùng `HMAC(password, message)` thay cho password hashing. Cũng không dùng `SHA256(password)` làm password storage hoặc làm cách biến mật khẩu thành secret HMAC mạnh.

### 6.2. KDF không tạo thêm entropy

Một KDF có thể làm mỗi lần đoán mật khẩu tốn thời gian và bộ nhớ hơn, nhưng không biến một mật khẩu yếu thành bí mật có entropy cao. Attacker có token vẫn có thể chạy KDF cho từng mật khẩu ứng viên rồi tính HMAC để so sánh. Salt và tham số KDF làm quá trình đoán tốn kém hơn, không loại bỏ khả năng tấn công ngoại tuyến.

Vì vậy, **không nên dùng mật khẩu người dùng làm khóa ký JWT**, kể cả khi đã băm hoặc dẫn xuất nó thành chuỗi đủ 32/48/64 byte.

### 6.3. Nếu hệ thống buộc phải dẫn xuất khóa từ passphrase

Đây không phải lựa chọn mặc định cho JWT. Nếu một ràng buộc đặc biệt buộc nhiều thành phần phải dẫn xuất cùng khóa từ passphrase, thiết kế cần được đánh giá riêng:

- Dùng KDF chuyên dụng, được phê duyệt, có salt ngẫu nhiên và tham số cost được quản lý.
- Thống nhất chính xác phiên bản KDF, salt, tham số, encoding và output length giữa issuer/verifier.
- Không tái sử dụng KDF hoặc salt tùy tiện giữa các mục đích.
- Đánh giá khả năng attacker kiểm tra passphrase ngoại tuyến từ token.
- Có quy trình thay passphrase/derived key và xử lý khi passphrase bị lộ.

KDF làm tăng chi phí mỗi lần đoán, nhưng entropy cuối cùng vẫn bị giới hạn bởi passphrase. Nếu có thể chọn kiến trúc, hãy sinh một khóa HMAC ngẫu nhiên độc lập thay vì bắt con người ghi nhớ passphrase.

## 7. Quản lý secret HMAC trong hệ thống JWT

### 7.1. Lưu trữ và phân phối

- Lưu secret trong secret manager, KMS hoặc HSM phù hợp.
- Phân quyền theo nguyên tắc ít quyền nhất; nhớ rằng quyền đọc secret hoặc quyền MAC đều có thể cho phép phát hành token.
- Truyền secret qua kênh được bảo vệ, chỉ tới các thành phần thực sự cần xác minh hoặc ký.
- Không ghi secret vào source code, Git, log, URL, ticket, ảnh chụp màn hình hoặc tài liệu công khai.
- Tách secret theo môi trường, issuer, tenant và loại token khi mô hình tin cậy yêu cầu.
- Không gửi secret qua email/chat thông thường hoặc nhúng secret vào JWT.

Nếu dùng dịch vụ KMS/HSM không cho export khóa, cần xác minh nó hỗ trợ thao tác HMAC tương ứng và mọi bên xác minh có cách thực hiện MAC qua dịch vụ đó. Không thể giả định một KMS hỗ trợ RSA signing cũng hỗ trợ HMAC hoặc có cùng chính sách phân phối.

### 7.2. Không dùng chung khóa cho nhiều mục đích

Không tái sử dụng HMAC secret của JWT cho:

- API key hoặc webhook signature khác.
- Mã hóa dữ liệu.
- Lưu mật khẩu.
- Ký cookie hoặc session token có chính sách khác.
- Môi trường development, staging và production.

Tách khóa giúp giảm ảnh hưởng khi một mục đích hoặc thành phần bị xâm nhập. Nếu cần dẫn xuất nhiều khóa từ một khóa gốc, phải dùng cơ chế KDF/key derivation được thiết kế và quản trị rõ ràng, với context/domain separation; không tự nối chuỗi theo cách tùy tiện.

### 7.3. Ràng buộc khóa với thuật toán và issuer

Mỗi khóa nên có metadata quản trị:

| Metadata | Mục đích |
| --- | --- |
| `kid` | Định danh khóa |
| Issuer | Xác định issuer được phép dùng khóa |
| `alg` | Thuật toán được phép, ví dụ `HS256` |
| Key purpose | Loại token hoặc mục đích sử dụng |
| Environment | Development, staging hoặc production |
| Created/activated time | Thời điểm sinh và bắt đầu sử dụng |
| Retirement time | Thời điểm ngừng ký/ngừng xác minh |
| Status | Active, verify-only, retired hoặc compromised |

`kid` không phải bí mật và không thay thế allowlist. Verifier chỉ tra `kid` trong tập khóa được cấu hình cho issuer; không lấy khóa từ URL hoặc nguồn không tin cậy chỉ vì header yêu cầu.

## 8. Luân chuyển khóa và xử lý khi lộ secret

### 8.1. Rotation có kế hoạch

Một quy trình rotation HMAC có thể thực hiện:

1. Sinh secret mới bằng CSPRNG với độ dài đúng cho thuật toán.
2. Phân phối secret mới an toàn tới tất cả verifier trước khi issuer sử dụng.
3. Cấu hình verifier nhận diện khóa cũ và khóa mới qua mapping tin cậy; nếu dùng `kid`, gắn mỗi ID với đúng secret và thuật toán.
4. Chuyển issuer sang ký token mới bằng secret mới và `kid` mới.
5. Tiếp tục xác minh token cũ bằng secret cũ trong thời gian token hợp lệ, cộng clock skew được phép.
6. Khi token cũ đã hết hạn và không còn nhu cầu xác minh, gỡ secret cũ khỏi verifier và kho bí mật.

Không để verifier thử tất cả secret tùy ý mà không có giới hạn. Cấu hình key ID và thuật toán phải rõ ràng, có log kiểm toán nhưng tuyệt đối không log giá trị secret.

### 8.2. Khi secret bị lộ hoặc nghi ngờ yếu

Nếu phát hiện secret là mật khẩu, secret mặc định, đã nằm trong Git hoặc có thể đã bị đoán:

1. Coi secret là đã bị xâm phạm; không tiếp tục dùng nó vì token hiện tại vẫn xác minh được.
2. Sinh secret mới đủ entropy.
3. Cập nhật verifier và issuer theo quy trình khẩn cấp.
4. Ngừng tin secret cũ càng sớm càng tốt.
5. Đánh giá và thu hồi token/phiên có thể đã bị giả mạo hoặc đánh cắp.
6. Kiểm tra log/audit, repository, CI/CD và nơi secret từng được phân phối.
7. Loại bỏ secret khỏi các nơi lưu trữ không an toàn và xử lý lịch sử rò rỉ theo quy trình ứng phó.

Nếu attacker đã biết secret, họ có thể tạo JWT có chữ ký hợp lệ cho đến khi verifier ngừng tin khóa đó. Đổi thời hạn token hoặc nâng SHA không đủ để khắc phục.

## 9. Khi nào nên dùng chữ ký bất đối xứng thay cho HMAC?

Entropy cao giải quyết nguy cơ đoán secret, nhưng **không giải quyết việc chia sẻ quyền ký**. Mọi verifier biết HMAC secret vẫn có thể tạo chữ ký.

Hãy cân nhắc RSA, RSA-PSS, ECDSA hoặc EdDSA khi:

- Có nhiều API hoặc tổ chức độc lập chỉ cần xác minh.
- Không muốn phân phối quyền ký cho gateway, đối tác hoặc resource server.
- Cần công bố public key qua JWKS.
- Muốn cô lập khóa riêng tại issuer hoặc HSM/KMS.
- Muốn giảm phạm vi ảnh hưởng khi một verifier bị xâm nhập.

Ví dụ mô hình:

~~~text
Issuer:
  giữ private key
  ký JWT
       |
       | JWT + kid
       v
API A / API B / Partner:
  nhận public key từ JWKS tin cậy
  xác minh chữ ký
  không có quyền ký token
~~~

HMAC vẫn có thể là lựa chọn tốt trong ranh giới tin cậy nhỏ nếu secret được sinh, lưu và phân phối đúng cách. Quyết định phải dựa trên quyền mà mỗi bên cần có, không chỉ dựa trên entropy.

## 10. Checklist đánh giá HMAC secret

### 10.1. Trước khi triển khai

- [ ] Đã chọn HS256, HS384 hoặc HS512 theo profile được phép.
- [ ] Secret được sinh bằng CSPRNG.
- [ ] Độ dài byte sau khi decode tối thiểu 32/48/64 byte tương ứng.
- [ ] Secret không bắt nguồn từ mật khẩu, tên hệ thống, timestamp hoặc giá trị mặc định.
- [ ] Đã xác định rõ Base64/Base64URL/hex và quy tắc decode.
- [ ] Issuer và verifier dùng đúng cùng một dãy byte.
- [ ] Secret được lưu trong secret manager/KMS/HSM phù hợp.
- [ ] Secret tách biệt theo môi trường, issuer và mục đích cần thiết.
- [ ] Verifier chỉ chấp nhận thuật toán đã allowlist.
- [ ] Đã xác định các thành phần biết secret và quyền ký mà chúng có.
- [ ] Có `kid`/key mapping và quy trình rotation.
- [ ] Có quy trình ứng phó khi secret bị lộ.

### 10.2. Dấu hiệu cần thay khóa ngay

| Dấu hiệu | Đánh giá |
| --- | --- |
| Secret là `secret`, `password`, `change-me` hoặc giá trị mẫu | Không an toàn |
| Secret được tạo từ mật khẩu người dùng | Không phù hợp cho HMAC JWT |
| Secret đã xuất hiện trong Git hoặc log | Coi như bị lộ |
| Secret chỉ được băm để đủ số byte | Không tăng entropy |
| Secret dùng chung giữa development và production | Phạm vi ảnh hưởng quá rộng |
| Không biết chính xác byte nào được HMAC sử dụng | Không thể xác nhận cấu hình khóa |
| Không rõ những verifier nào đang giữ secret | Không kiểm soát được quyền ký |

## 11. Những hiểu lầm phổ biến

**“Chuỗi đủ 32 ký tự là khóa HS256 an toàn.”** Sai. JWA yêu cầu tối thiểu 32 byte, nhưng entropy phụ thuộc cách tạo. Mật khẩu 32 ký tự vẫn có thể dễ đoán.

**“SHA-256 mật khẩu sẽ tạo khóa 256 bit.”** Sai. Nó tạo đầu ra 32 byte nhưng không tăng entropy của mật khẩu.

**“Base64 làm secret khó đoán hơn.”** Sai. Base64 chỉ thay đổi biểu diễn. Attacker có thể decode hoặc thử khóa theo đúng cách hệ thống dùng.

**“JWT hết hạn nên attacker không thể đoán secret từ token cũ.”** Sai. MAC trong token cũ vẫn cho phép kiểm tra ứng viên ngoại tuyến.

**“HS512 an toàn hơn nên có thể giữ nguyên mật khẩu secret.”** Sai. HMAC-SHA-512 không biến mật khẩu yếu thành khóa ngẫu nhiên 512 bit.

**“KDF biến password thành khóa có entropy cao.”** Sai. KDF tăng chi phí đoán; entropy vẫn bị giới hạn bởi password.

**“Verifier chỉ có nhiệm vụ xác minh nên giữ HMAC secret không có quyền ký.”** Sai. Biết secret là có khả năng tạo MAC hợp lệ.

## 12. Câu hỏi tự kiểm tra

1. Phân biệt độ dài byte của khóa và entropy của khóa.
2. Theo RFC 7518, HS256, HS384 và HS512 yêu cầu khóa tối thiểu bao nhiêu byte?
3. Vì sao một chuỗi 32 ký tự có thể đủ độ dài cho HS256 nhưng vẫn không đủ entropy?
4. Attacker có thể kiểm tra mật khẩu ứng viên ngoại tuyến từ JWT HS256 bằng cách nào?
5. Vì sao `SHA256(password)` không biến password thành khóa có 256 bit entropy?
6. KDF như Argon2id hoặc PBKDF2 giúp gì và không giải quyết được điều gì trong tình huống này?
7. 32 byte ngẫu nhiên được biểu diễn bằng Base64URL không padding có bao nhiêu ký tự? Vì sao phải decode trước khi xác định độ dài khóa?
8. Nếu secret HMAC bị lộ, tại sao đổi HS256 thành HS512 không đủ để xử lý?
9. Khi nào nên chuyển sang chữ ký bất đối xứng để tách quyền ký và quyền xác minh?

## 13. Tiêu chuẩn và tài liệu tham khảo

- [RFC 2104 — HMAC: Keyed-Hashing for Message Authentication](https://www.rfc-editor.org/rfc/rfc2104), cấu trúc HMAC và cách xử lý khóa.
- [RFC 7515 — JSON Web Signature (JWS)](https://www.rfc-editor.org/rfc/rfc7515), signing input và cấu trúc JWS Compact.
- [RFC 7518 — JSON Web Algorithms (JWA)](https://www.rfc-editor.org/rfc/rfc7518), đặc biệt **mục 3.2** quy định HS256, HS384, HS512 và kích thước khóa tối thiểu.
- [RFC 8725 — JSON Web Token Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725), khuyến nghị dùng khóa đủ mạnh, tránh secret yếu và xác minh thuật toán.
- [RFC 9106 — Argon2 Memory-Hard Function for Password Hashing and Proof-of-Work Applications](https://www.rfc-editor.org/rfc/rfc9106), mô tả Argon2 và các cấu hình tham khảo cho password hashing/KDF.
