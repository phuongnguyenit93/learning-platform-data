# Kiểm tra thuật toán, loại khóa và nguồn khóa

## 1. Ba câu hỏi phải trả lời trước khi dùng khóa

Khi xác minh JSON Web Token (JWT), việc tìm được một khóa có cùng mã định danh với trường **kid** chưa đủ để sử dụng khóa đó. Bên nhận cần xác định đồng thời:

1. **Thuật toán nào được phép?** Thuật toán trong JOSE header có nằm trong chính sách của endpoint, issuer và token profile không?
2. **Khóa có đúng loại và đủ mạnh không?** Loại khóa, kích thước, đường cong, mục đích sử dụng và metadata của khóa có tương thích với thuật toán không?
3. **Nguồn khóa có đáng tin cậy không?** Khóa đến từ cấu hình được quản trị, JWKS đã gắn với issuer, kho bí mật hoặc chuỗi chứng chỉ được xác minh theo trust anchor đã biết?

Ba câu hỏi này tạo thành một chuỗi kiểm soát. Thuật toán hợp lệ nhưng khóa không phù hợp vẫn phải bị từ chối. Khóa đúng định dạng nhưng đến từ nguồn do token tự chỉ định cũng không được tin cậy. Nguồn khóa tin cậy nhưng thuật toán nằm ngoài allowlist cũng không thể được sử dụng.

Điểm xuất phát luôn là **chính sách xác minh đã được cấu hình từ ngữ cảnh tin cậy**. Header và metadata do token mang theo chỉ giúp đối chiếu và chọn ứng viên bên trong phạm vi đó. Chúng không được tự tạo danh sách thuật toán, mở rộng nguồn khóa hoặc thay đổi mục đích sử dụng khóa.

Nội dung này thuộc chương Xác minh token của module Security - JSON Web Token (JWT), áp dụng cho bảo mật JWT/JOSE nói chung, không phụ thuộc ngôn ngữ lập trình hay framework.

## 2. Ràng buộc thuật toán bằng allowlist

Trường **alg** trong JWS header chỉ ra thuật toán chữ ký mà token tự khai báo. Trong JWE, **alg** chỉ thuật toán quản lý khóa hoặc thiết lập khóa nội dung, còn **enc** chỉ thuật toán mã hóa nội dung. Bên nhận cần hiểu đúng ngữ nghĩa theo loại JOSE đang xử lý.

Không được để token quyết định thuật toán được phép. Một endpoint nên có allowlist nhỏ, rõ ràng và gắn với issuer/token profile. Ví dụ:

~~~yaml
signedJwtPolicy:
  issuer: https://identity.example.org/
  tokenProfile: access-token
  allowedAlgorithms:
    - RS256
  requiredKeyType: RSA
  minimumRsaBits: 2048
~~~

Đây là cấu hình minh họa, không phải cú pháp chuẩn. Hệ thống có thể dùng thuật toán khác nếu profile và mô hình khóa yêu cầu, nhưng phải định nghĩa rõ thuật toán nào được chấp nhận và loại khóa tương ứng.

### 2.1. Không chấp nhận thuật toán ngoài chính sách

Nếu policy chỉ cho phép RS256:

- Header có **alg = RS256**: tiếp tục kiểm tra khóa RSA phù hợp và xác minh chữ ký.
- Header có **alg = HS256**: từ chối; không diễn giải khóa công khai RSA thành bí mật HMAC.
- Header có **alg = none**: từ chối trong profile yêu cầu chữ ký.
- Header thiếu alg, sai kiểu hoặc dùng tên thuật toán không hỗ trợ: từ chối.

Không thử lần lượt nhiều thuật toán cho tới khi có một phép xác minh thành công. Cách làm đó làm rộng bề mặt tấn công và có thể tạo ra lỗi algorithm confusion hoặc downgrade. Nếu một thuật toán hoặc thư viện gặp lỗi, không tự động chuyển sang thuật toán yếu hơn.

### 2.2. Phân biệt tên thuật toán và cấu hình thực thi

Tên thuật toán là một phần của hợp đồng JOSE, nhưng chỉ tên đúng chưa đảm bảo cách thực thi đúng. Bộ xác minh cần dùng triển khai tuân thủ chuẩn, bao gồm các tham số bắt buộc như:

- RSA-PSS (PS256, PS384, PS512): hash, MGF1 và độ dài salt phải theo yêu cầu của JWA.
- ECDSA (ES256, ES384, ES512): đường cong và định dạng chữ ký phải phù hợp thuật toán tương ứng.
- EdDSA: loại đường cong Edwards và định dạng khóa phải được profile hỗ trợ.
- HMAC (HS256, HS384, HS512): độ dài bí mật phải đủ theo thuật toán; không dùng mật khẩu người dùng hoặc chuỗi dễ đoán làm khóa.

Không tự cài đặt phép toán mật mã từ các ví dụ. Nên dùng thư viện JOSE/crypto đã được kiểm chứng và cấu hình chính xác allowlist cùng tham số.

## 3. Tách chính sách JWS và JWE

JWS và JWE đều sử dụng JOSE header nhưng mục đích mật mã khác nhau. Không dùng một trường alg với cùng cách hiểu cho cả hai.

| Thành phần | JWS | JWE |
| --- | --- | --- |
| Mục tiêu | Bảo vệ tính toàn vẹn và xác thực nguồn ký theo khóa | Bảo vệ tính bí mật và tính toàn vẹn của nội dung theo cơ chế mã hóa có xác thực |
| alg | Thuật toán chữ ký/MAC | Thuật toán quản lý khóa hoặc thiết lập khóa |
| enc | Không dùng | Thuật toán mã hóa nội dung |
| Khóa điển hình | Public key để xác minh chữ ký bất đối xứng hoặc shared secret cho HMAC | Private key/secret để giải mã hoặc khóa thỏa thuận theo thuật toán |
| Bằng chứng | Signature hoặc MAC | Authentication tag và kết quả giải mã được xác thực |
| Câu hỏi tin cậy | Ai có quyền ký bằng khóa này? | Ai có thể tạo/giải mã nội dung và hợp đồng có chứng minh issuer riêng không? |

Một JWE có thể được tạo bởi bất kỳ bên nào có khả năng mã hóa bằng public key của người nhận. Vì vậy, giải mã JWE thành công không nhất thiết chứng minh nội dung do issuer cụ thể phát hành. Nếu cần xác thực issuer, profile có thể yêu cầu chữ ký JWS bên trong (nested JWT) hoặc một cơ chế xác thực nguồn riêng.

### 3.1. Chính sách JWE phải kiểm tra cả alg và enc

Ví dụ một policy JWE có thể chỉ cho phép một cặp thuật toán:

~~~yaml
encryptedJwtPolicy:
  allowedKeyManagementAlgorithms:
    - RSA-OAEP-256
  allowedContentEncryptionAlgorithms:
    - A256GCM
  requiredRecipientKeyType: RSA
  requireAuthenticatedEncryption: true
~~~

Không chỉ kiểm tra enc rồi bỏ qua alg hoặc ngược lại. Cặp thuật toán phải tương thích với loại khóa, cách phân phối khóa và profile đã định nghĩa. Nếu header yêu cầu thuật toán quản lý khóa hoặc mã hóa nội dung ngoài allowlist, từ chối trước khi thực hiện thao tác mật mã.

## 4. Chọn loại khóa phù hợp với thuật toán

Mỗi thuật toán JOSE đòi hỏi loại khóa và tham số cụ thể. Bên xác minh phải kiểm tra khóa sau khi tra cứu, kể cả khi kid khớp.

| Thuật toán | Loại khóa | Ràng buộc chính |
| --- | --- | --- |
| RS256, RS384, RS512 | RSA | Public RSA key hợp lệ, modulus đủ lớn, exponent hợp lệ |
| PS256, PS384, PS512 | RSA | Khóa RSA đủ mạnh và tham số PSS đúng chuẩn |
| ES256 | EC | Đường cong P-256 |
| ES384 | EC | Đường cong P-384 |
| ES512 | EC | Đường cong P-521 |
| EdDSA | OKP | Đường cong Edwards được thuật toán/profile hỗ trợ, ví dụ Ed25519 hoặc Ed448 |
| HS256, HS384, HS512 | oct (symmetric secret) | Bí mật có entropy và độ dài phù hợp; quản lý như secret |

Bảng trên nêu các nhóm thường gặp, không phải danh sách cho phép mặc định. Một hệ thống có thể hỗ trợ một tập con phù hợp với môi trường và thư viện đang dùng.

### 4.1. RSA

JWK RSA biểu diễn khóa công khai bằng các thành phần như **n** (modulus) và **e** (public exponent). Bộ xác minh cần kiểm tra:

- n và e có mặt, đúng kiểu Base64URLUInt và giải mã thành số nguyên dương hợp lệ.
- Modulus có kích thước tối thiểu theo thuật toán và chính sách; với các thuật toán RSA JOSE phổ biến theo RFC 7518, yêu cầu tối thiểu là 2048 bit.
- Public exponent hợp lệ và không tạo cấu hình yếu hoặc không tương thích.
- Khóa chỉ có thành phần công khai trong nguồn public JWKS; không để lộ private exponent hay các tham số riêng.
- Không dùng một RSA public key như HMAC secret.

Với RSA-PSS, thư viện phải áp dụng đúng tham số hash/MGF1/salt của JWA. Không thay thế bằng cấu hình PSS tùy ý chỉ vì tên thuật toán có chữ PS.

### 4.2. Elliptic Curve (EC)

JWK EC thường có **crv**, **x** và **y**. Bộ xác minh cần kiểm tra:

- Đường cong nằm trong danh sách được thuật toán/profile hỗ trợ.
- Tọa độ x/y có độ dài và định dạng đúng.
- Điểm công khai nằm trên đường cong và không phải điểm vô hiệu theo yêu cầu của thư viện/chuẩn.
- Đường cong phù hợp đúng thuật toán; ví dụ ES256 yêu cầu P-256, không dùng P-384 chỉ vì nó cũng là EC.
- Không chấp nhận tham số private d trong một public JWKS.

Không tự chuyển đổi hoặc đoán đường cong dựa trên độ dài tọa độ. Thuộc tính crv phải được kiểm tra rõ ràng.

### 4.3. OKP và EdDSA

JWK loại **OKP** có thể dùng cho các đường cong Edwards. Các trường thường gồm **crv** và **x** cho public key; **d** là private key material.

Chỉ chấp nhận đường cong được profile và thư viện hỗ trợ, ví dụ Ed25519 hoặc Ed448 theo đặc tả tương ứng. Không suy luận rằng mọi OKP đều dùng EdDSA hoặc mọi thuật toán EdDSA đều chấp nhận mọi đường cong.

### 4.4. Khóa đối xứng HMAC

JWK loại **oct** chứa bí mật trong trường **k**. Đây là key material nhạy cảm và không được công bố trong JWKS công khai.

Độ dài khóa HMAC phải tối thiểu bằng độ dài đầu ra hash theo yêu cầu của JWA: HS256 cần ít nhất 256 bit, HS384 ít nhất 384 bit và HS512 ít nhất 512 bit. Khóa phải được tạo bằng nguồn ngẫu nhiên mật mã phù hợp, không phải chuỗi mật khẩu hoặc giá trị dễ đoán.

HMAC có đặc tính mọi bên giữ shared secret đều có khả năng tạo MAC hợp lệ. Vì vậy, nếu nhiều resource server cùng biết một bí mật, mỗi server đều có năng lực ký token theo bí mật đó. Cần cân nhắc blast radius, phân phối secret và quyền truy cập. Với hệ thống nhiều bên xác minh độc lập, chữ ký bất đối xứng thường giúp tách quyền ký của issuer khỏi quyền xác minh của resource server.

## 5. Kiểm tra metadata JWK

Một JWK có thể chứa các trường metadata giúp giới hạn mục đích sử dụng khóa. Các trường này không thay thế kiểm tra vật liệu khóa, nhưng cần được kiểm tra khi xuất hiện và theo profile.

| Trường JWK | Ý nghĩa | Quy tắc xác minh |
| --- | --- | --- |
| **kty** | Loại khóa | Bắt buộc tương thích với thuật toán và vật liệu khóa |
| **kid** | Định danh khóa | So khớp trong đúng tập khóa của issuer; không coi là bằng chứng tin cậy |
| **use** | Mục đích tổng quát, ví dụ sig hoặc enc | Nếu có phải phù hợp thao tác; không dùng khóa sig cho mục đích enc trái policy |
| **key_ops** | Các thao tác được phép trên khóa | Nếu có phải cho phép thao tác cần thiết, ví dụ verify hoặc decrypt |
| **alg** | Thuật toán mà khóa được dự định sử dụng | Nếu có phải khớp thuật toán trong policy |
| **crv** | Đường cong cho EC/OKP | Phải nằm trong tập được hỗ trợ và phù hợp thuật toán |
| **n**, **e** | Thành phần public RSA | Phải hợp lệ và đạt kích thước yêu cầu |
| **x**, **y** | Tọa độ EC hoặc public coordinate của OKP | Phải đúng định dạng, độ dài và đường cong |
| **d**, **p**, **q**, **dp**, **dq**, **qi**, **k** | Thành phần private hoặc secret tùy loại khóa | Không được xuất hiện trong public JWKS; chỉ lưu trong vùng bí mật phù hợp |

### 5.1. use và key_ops phải nhất quán

Trường **use** thường là sig cho chữ ký hoặc enc cho mã hóa. Trường **key_ops** mô tả các thao tác được phép như sign, verify, encrypt, decrypt, wrapKey, unwrapKey, deriveKey hoặc deriveBits.

Nếu một JWK có cả use và key_ops, chúng phải nhất quán. Ví dụ:

- JWS verification cần khóa có thể thực hiện verify; nếu use có mặt, use phải phù hợp với sig.
- JWE decryption cần khóa có thể thực hiện decrypt hoặc thao tác quản lý khóa tương ứng; nếu use có mặt, use phải phù hợp với enc.
- Một khóa chỉ cho encrypt không thể được dùng để decrypt.
- Một khóa chỉ cho sign không thể được dùng để verify nếu metadata giới hạn thao tác và profile yêu cầu kiểm tra nó.

Metadata có thể vắng mặt trong JWK hợp lệ; khi đó policy vẫn phải xác định cách dùng khóa. Không tự suy ra mọi thao tác đều được phép chỉ vì trường use hoặc key_ops không có.

### 5.2. Không để khóa có nhiều vai trò ngoài dự kiến

Một khóa có thể được cấu hình cho nhiều thao tác trong một số hệ thống, nhưng việc dùng chung một vật liệu khóa cho nhiều mục đích làm tăng nguy cơ nhầm lẫn. Nên tách khóa ký và khóa mã hóa khi có thể; tách khóa theo issuer, môi trường và mục đích; tránh dùng chung key material giữa các giao thức khác nhau.

Nếu policy yêu cầu một khóa chỉ dùng cho một thuật toán, trường alg trong JWK nên được kiểm tra và ràng buộc. Không dùng cùng một kid để đại diện cho nhiều vật liệu khóa hoặc nhiều thuật toán không tương thích trong cùng một tập khóa.

## 6. Phân biệt public key, private key và secret

Nguồn khóa và vai trò của bên tham gia cần được xác định rõ:

| Mô hình | Bên phát hành | Bên xác minh/nhận |
| --- | --- | --- |
| Chữ ký bất đối xứng JWS | Giữ private signing key | Giữ public verification key |
| HMAC JWS | Giữ shared secret | Cũng phải giữ cùng shared secret |
| JWE với public-key encryption | Dùng public key của người nhận để mã hóa/thiết lập khóa | Giữ private decryption key |
| JWE với shared secret | Dùng secret theo thuật toán quản lý khóa | Giữ secret tương ứng |
| Nested signed-and-encrypted JWT | Có thể ký bằng private key rồi mã hóa cho người nhận | Giải mã lớp ngoài, sau đó xác minh chữ ký lớp trong |

Với chữ ký bất đối xứng, public key có thể được phân phối rộng hơn, nhưng private key phải được giới hạn cho issuer hoặc hệ thống được ủy quyền ký. Với HMAC, mọi bên xác minh đều nắm khả năng tạo MAC, do đó quyền xác minh và quyền phát hành không được tách biệt bằng mật mã.

Không bao giờ đưa private key hoặc HMAC secret vào public JWKS, log, mã nguồn, image triển khai công khai hoặc phản hồi API. Private material phải được lưu trong secret manager, HSM hoặc kho khóa có kiểm soát truy cập phù hợp. Việc chọn một khóa đúng loại không có nghĩa là quyền truy cập vào khóa đó cũng an toàn; quyền đọc, sử dụng, xoay vòng và thu hồi phải được quản trị riêng.

## 7. Xác minh nguồn gốc của khóa

Một khóa chỉ đáng tin cậy nếu bên nhận biết **vì sao khóa đó thuộc về issuer hoặc vai trò đang được kiểm tra**. Các nguồn thường gặp:

| Nguồn khóa | Cách thiết lập tin cậy | Rủi ro cần kiểm soát |
| --- | --- | --- |
| Cấu hình public key tĩnh | Khóa được provision qua kênh quản trị tin cậy, có fingerprint và quy trình thay thế | Cấu hình cũ, sai môi trường, thay khóa không đồng bộ |
| JWKS của issuer | JWKS URI được gắn với issuer đã đăng ký hoặc metadata discovery đã xác minh | SSRF, issuer mix-up, cache chéo issuer, phản hồi giả |
| Chứng chỉ X.509 | Chuỗi chứng chỉ được kiểm tra đến trust anchor đã cấu hình | Chứng chỉ tự ký, sai hostname, hết hạn, sai key usage/EKU |
| Secret manager | Secret được tạo và cấp qua quy trình quản trị bí mật | Lộ secret, phân phối quá rộng, dùng chung môi trường |
| HSM hoặc thiết bị quản lý khóa | Key handle và quyền thao tác được cấp theo danh tính hệ thống | Cấu hình quyền sai, key slot nhầm, phụ thuộc vận hành |

### 7.1. JWKS: tin cậy issuer trước, sau đó mới tin tập khóa

JWKS là một tập các JWK được công bố để bên nhận lấy khóa. Việc một URL trả về JSON có cấu trúc JWKS không làm cho các khóa trong đó tự động đáng tin cậy.

Quy trình thiết lập nguồn JWKS:

1. Bắt đầu từ issuer đã được đăng ký và phê duyệt trong cấu hình tin cậy.
2. Nếu dùng discovery, lấy metadata từ issuer đã đăng ký qua HTTPS và xác minh trường issuer khớp chính xác giá trị dự kiến.
3. Lấy jwks_uri từ metadata đã được xác minh hoặc từ cấu hình trực tiếp; không lấy URL từ jku/x5u chưa xác minh trong JWT.
4. Kiểm soát TLS, DNS, redirect, egress, timeout và kích thước phản hồi.
5. Parse JWKS nghiêm ngặt; kiểm tra số lượng khóa, kid, kty, use, key_ops, alg và vật liệu khóa.
6. Gắn tập khóa với issuer và nguồn đã xác minh; không dùng chung cache chỉ theo kid.

Nếu nhiều issuer có cùng kid, chúng vẫn là những khóa khác nhau trong các miền tin cậy khác nhau. Cache key cần bao gồm issuer và nguồn JWKS, không chỉ kid.

### 7.2. Chứng chỉ X.509 và x5c

Một header có thể chứa chuỗi chứng chỉ x5c hoặc tham chiếu chứng chỉ. Bên nhận không được coi chứng chỉ nhúng là trust anchor. Nếu profile cho phép dùng chứng chỉ:

- Xác minh chuỗi chứng chỉ tới CA/trust anchor được cấu hình.
- Kiểm tra thời hạn hiệu lực, trạng thái thu hồi theo chính sách và mục đích sử dụng.
- Kiểm tra key usage và extended key usage phù hợp vai trò ký/xác minh.
- Kiểm tra danh tính/issuer theo hợp đồng; không chỉ dựa vào việc chứng chỉ có chữ ký CA.
- Đối chiếu khóa công khai trong chứng chỉ với vật liệu khóa được dùng xác minh.

Không tự động truy cập x5u do token chỉ định. Nếu cần tải chứng chỉ, nguồn phải được giới hạn và xác minh độc lập.

### 7.3. Khóa tĩnh và fingerprint

Với hệ thống nhỏ hoặc tích hợp cố định, public key có thể được provision trực tiếp. Cần có kênh quản trị tin cậy để phân phối khóa, ghi nhận fingerprint, xác định issuer, mục đích và thời gian hiệu lực. Thay đổi fingerprint phải được quản lý như thay đổi trust configuration, không phải cập nhật dữ liệu thông thường.

Không lấy public key từ email, request hoặc tệp tải lên rồi tự động đưa vào trust store. Khóa mới phải được phê duyệt và gắn với đúng issuer/profile trước khi được sử dụng.

## 8. Chống SSRF và nguồn khóa do token điều khiển

Các header như **jku** và **x5u** chứa URL. Nếu bộ xác minh tự động truy cập URL chưa xác minh, token có thể trở thành phương tiện yêu cầu máy chủ truy cập:

- Địa chỉ loopback hoặc mạng nội bộ.
- Metadata endpoint của nền tảng cloud.
- Dịch vụ quản trị hoặc hệ thống chỉ truy cập được từ mạng nội bộ.
- Máy chủ do kẻ tấn công kiểm soát để trả về public key của họ.

Đây là rủi ro SSRF và trust substitution. Cách phòng tránh:

1. Không tự động tải jku/x5u từ header chưa xác minh.
2. Dùng JWKS URI được cấu hình hoặc discovery từ issuer đã đăng ký.
3. Áp dụng egress allowlist và chặn địa chỉ IP riêng, loopback, link-local cùng các vùng nhạy cảm.
4. Kiểm tra redirect từng bước; tốt nhất không cho redirect hoặc chỉ cho đích đã được phê duyệt.
5. Giới hạn DNS resolution, tránh DNS rebinding và xác thực địa chỉ kết nối cuối cùng.
6. Dùng HTTPS và xác minh chứng chỉ máy chủ.
7. Giới hạn timeout, số lần retry, kích thước phản hồi và số khóa.
8. Không chuyển sang nguồn khóa khác khi nguồn tin cậy bị lỗi.

Nếu một profile yêu cầu tham chiếu khóa bên ngoài, hãy thiết kế nó như một cơ chế trust establishment riêng với danh sách cho phép và audit trail. Không coi URL trong token là một nguồn có thẩm quyền.

## 9. Lựa chọn khóa trong JWKS

Sau khi đã có JWKS tin cậy gắn với issuer, bộ xác minh mới tiến hành lọc ứng viên:

1. Đọc protected header trong giới hạn; kiểm tra alg thuộc allowlist.
2. Nếu policy yêu cầu kid, tìm khóa có kid khớp chính xác trong JWKS của issuer đó.
3. Kiểm tra kty phù hợp với thuật toán.
4. Kiểm tra use/key_ops nếu có; chúng phải cho phép thao tác cần thực hiện.
5. Kiểm tra alg trong JWK nếu có; không mâu thuẫn với policy/header.
6. Kiểm tra tham số vật liệu khóa, kích thước và đường cong.
7. Loại khóa đã bị vô hiệu hóa hoặc không còn trong thời gian được chấp nhận theo policy.
8. Đảm bảo kết quả không mơ hồ và số ứng viên nằm trong giới hạn.
9. Dùng khóa được chọn để xác minh mật mã; nếu thất bại thì từ chối token.

Nếu kid không có trong JWKS cache, có thể làm mới JWKS một lần theo chính sách rate limit. Sau khi refresh vẫn không có khóa phù hợp, từ chối. Không thử mọi khóa trong hệ thống, không tra cứu kid ở issuer khác và không tự tải URL trong header.

### 9.1. Trường hợp không có kid

Không phải mọi profile đều yêu cầu kid, nhưng khi không có kid, bên nhận cần quy tắc rõ ràng:

- Nếu policy yêu cầu kid, từ chối ngay.
- Nếu policy cho phép thiếu kid, chỉ tìm trong một tập khóa rất nhỏ, được gắn với đúng issuer và có thể phân giải duy nhất theo thuật toán/metadata.
- Nếu có nhiều khóa phù hợp, từ chối do mơ hồ hoặc dùng quy tắc lựa chọn đã được chuẩn hóa và kiểm thử.
- Giới hạn số phép thử mật mã; không cho phép một token buộc hệ thống thử hàng trăm khóa.

Không coi thiếu kid là lý do để nới allowlist thuật toán hoặc chuyển sang nguồn khóa khác.

## 10. Cache, rotation và thu hồi khóa

Nguồn JWKS có thể thay đổi khi issuer luân chuyển khóa. Bộ xác minh phải hỗ trợ giai đoạn chuyển tiếp nhưng vẫn kiểm soát việc dùng khóa cũ.

### 10.1. Cache an toàn

Cache nên được gắn với:

- Issuer đã xác minh.
- JWKS URI hoặc định danh nguồn khóa đã được đăng ký.
- Thời điểm lấy, TTL và chính sách stale.
- Phiên bản/dấu vân tay tập khóa nếu hệ thống dùng.
- Trạng thái khóa và metadata đã kiểm tra.

Không cache vô thời hạn. Không chia sẻ cache giữa issuer khác nhau chỉ vì kid trùng. Khi nguồn khóa không truy cập được, chỉ dùng stale cache trong thời gian và điều kiện đã định nghĩa; không bỏ qua xác minh.

### 10.2. Luân chuyển khóa thông thường

Một quy trình rotation thường gồm:

1. Issuer tạo khóa mới và công bố public key mới trong JWKS.
2. Resource server có thời gian tải và cache khóa mới.
3. Issuer bắt đầu ký token bằng khóa mới và kid tương ứng.
4. JWKS tiếp tục chứa khóa cũ trong thời gian token cũ còn hiệu lực.
5. Sau khi token cũ hết hạn cộng thời gian leeway/cache cần thiết, issuer loại khóa cũ.
6. Resource server cập nhật cache và ngừng chấp nhận khóa cũ.

Thời gian overlap cần dựa trên TTL, thời hạn token, độ lệch đồng hồ và độ trễ phân phối. Không loại khóa cũ quá sớm khiến token hợp lệ bị lỗi; cũng không giữ khóa đã bị lộ lâu hơn mức cần thiết.

### 10.3. Khóa bị lộ hoặc cần vô hiệu hóa khẩn cấp

Nếu private key hoặc shared secret bị lộ, quy trình thông thường không đủ. Cần:

- Đánh dấu khóa không còn được chấp nhận trong policy.
- Gỡ khóa khỏi tập khóa được tin cậy hoặc áp dụng denylist theo định danh/fingerprint.
- Làm mới cache trên mọi instance, không chờ TTL thông thường.
- Ngừng phát hành token bằng khóa đó và phát hành khóa thay thế.
- Đánh giá token/phiên đã phát hành trong khoảng thời gian bị ảnh hưởng.
- Kiểm tra log và điều tra phạm vi truy cập có thể đã bị xâm phạm.

Với HMAC secret, phải thay secret trên tất cả bên dùng chung và tính đến việc mọi bên có secret đều có thể tạo MAC.

## 11. Rủi ro khi kiểm tra thuật toán và khóa không đầy đủ

| Lỗi | Hậu quả có thể xảy ra | Kiểm soát cần có |
| --- | --- | --- |
| Tin alg do token khai báo | Algorithm confusion, downgrade hoặc chấp nhận none | Allowlist theo policy, không thử thuật toán dự phòng |
| Không kiểm tra kty | Dùng khóa sai loại hoặc sai thuật toán | Ràng buộc alg-kty-key material |
| Không kiểm tra kích thước/đường cong | Khóa yếu, sai định dạng hoặc lỗi thư viện | Kiểm tra tham số theo JWA và policy |
| Dùng RSA public key làm HMAC secret | Giả mạo MAC khi xảy ra nhầm lẫn thuật toán | Tách loại khóa và thuật toán |
| Tin kid như định danh toàn cục | Chọn nhầm khóa giữa issuer | Phân vùng JWKS/cache theo issuer |
| Tin jku/x5u tùy ý | SSRF hoặc attacker-controlled key | Nguồn khóa được cấu hình và kiểm soát egress |
| Tin jwk/x5c nhúng | Tự xác minh token bằng khóa do người gửi tự tạo | Trust anchor và xác minh chứng chỉ độc lập |
| Bỏ qua use/key_ops | Dùng khóa sai mục đích | Kiểm tra metadata và policy |
| JWKS chứa private material | Lộ khả năng ký/giải mã | Từ chối public JWK có thành phần bí mật |
| Không giới hạn refresh khi kid lạ | DoS qua mạng/JWKS | Rate limit, single-flight và cache có giới hạn |
| Dùng stale key vô thời hạn | Tiếp tục tin khóa đã bị thu hồi | TTL, emergency invalidation và rotation policy |

## 12. Mã giả kiểm tra thuật toán, khóa và nguồn khóa

Đoạn mã giả mô tả logic kiểm tra JWS. Các hàm parse và mật mã phải được thực hiện bằng thư viện JOSE/crypto đã được đánh giá:

~~~text
function validateSignedJwt(rawToken, trustedPolicy):
    compact = strictParseJwsCompactWithinLimits(rawToken)
    header = strictParseProtectedHeader(compact.protectedHeader)

    require header.alg is a string
    require header.alg in trustedPolicy.allowedSignatureAlgorithms
    require header.alg != "none"
    require criticalHeadersAreSupported(header, trustedPolicy)

    keySet = loadTrustedKeySet(
        issuer = trustedPolicy.issuer,
        source = trustedPolicy.configuredJwksSource
    )
    require keySet.source is bound to trustedPolicy.issuer

    candidates = selectByKidIfRequired(keySet.keys, header.kid, trustedPolicy)
    candidates = filterByAlgorithmAndKeyType(candidates, header.alg)
    candidates = filterByUseAndKeyOps(candidates, requiredOperation = "verify")
    candidates = filterByJwkAlgIfPresent(candidates, header.alg)
    candidates = filterByKeyStrengthAndParameters(candidates, trustedPolicy)

    require candidates.count == 1
    key = candidates[0]
    require key contains public verification material only
    require verifyJwsOriginalSigningInput(rawToken, key, header.alg)

    claims = parseVerifiedClaims(compact.payload)
    require claims.iss exactly equals trustedPolicy.issuer
    require claims.aud contains trustedPolicy.expectedAudience
    require validateTimeClaims(claims, trustedPolicy.timePolicy)
    require validateTokenProfile(claims, header, trustedPolicy)

    return ValidatedTokenContext(claims, trustedPolicy.id)
~~~

Với JWE, thay bước xác minh chữ ký bằng quy trình kiểm tra cặp **alg/enc**, chọn khóa giải mã hoặc khóa quản lý nội dung phù hợp, xác thực authentication tag và giải mã theo chuẩn. Sau đó tiếp tục kiểm tra nested JWT/chữ ký bên trong nếu profile yêu cầu. Không dùng pseudocode JWS làm quy trình xác minh JWE.

## 13. Ví dụ quyết định chấp nhận hoặc từ chối

Giả sử endpoint hóa đơn chỉ chấp nhận JWS access token do issuer **https://identity.example.org/** phát hành, audience là **https://api.example.org/invoices**, thuật toán RS256 và khóa RSA tối thiểu 2048 bit từ JWKS đã đăng ký.

| Đầu vào | Quyết định | Lý do |
| --- | --- | --- |
| alg=RS256, kid hợp lệ, RSA key 3072 bit, use=sig, key_ops có verify, JWKS đúng issuer | Tiếp tục xác minh chữ ký | Thuật toán, khóa và nguồn đều phù hợp |
| alg=RS256 nhưng kid trỏ tới EC key | Từ chối | Loại khóa không tương thích |
| alg=HS256 trong khi policy chỉ cho RS256 | Từ chối | Thuật toán ngoài allowlist |
| RSA key chỉ 1024 bit | Từ chối | Không đạt mức tối thiểu theo chính sách/JWA |
| EC key dùng P-384 nhưng header khai ES256 | Từ chối | Đường cong không phù hợp thuật toán |
| JWK có use=enc nhưng đang dùng để verify JWS | Từ chối | Sai mục đích sử dụng |
| JWK có key_ops chỉ gồm sign | Từ chối | Không cho phép thao tác verify |
| kid đúng nhưng JWKS được tải từ URL jku do token cung cấp | Từ chối | Nguồn khóa không được tin cậy |
| JWKS đúng issuer nhưng public JWK chứa private exponent d | Từ chối và cảnh báo nguồn khóa | Public key set làm lộ private material |
| Chữ ký hợp lệ nhưng iss/aud không khớp policy | Từ chối token | Khóa đúng không làm token đúng đối tượng |

Ví dụ cho thấy kết quả chỉ có thể được chấp nhận khi **thuật toán, khóa, nguồn khóa và claims** cùng phù hợp.

## 14. Kiểm thử và quan sát vận hành

### 14.1. Ma trận kiểm thử

| Nhóm | Ca kiểm thử |
| --- | --- |
| Allowlist | Thuật toán được phép, ngoài allowlist, none, sai kiểu, sai chữ hoa/thường |
| Algorithm confusion | Thay RS256 thành HS256; thay đổi alg nhưng giữ nguyên key material |
| Loại khóa | RSA/EC/OKP/oct không tương thích; curve sai; RSA modulus nhỏ; secret HMAC quá ngắn |
| JWK metadata | use sai, key_ops sai, alg JWK xung đột, kid trùng, thiếu kid, tham số khóa sai |
| Key material | Public JWKS có d/p/q/k; tọa độ EC không hợp lệ; số nguyên RSA không hợp lệ |
| Nguồn khóa | JWKS đúng issuer, JWKS issuer khác, jku/x5u tùy ý, redirect, TLS lỗi, DNS rebinding |
| Cache/rotation | Khóa mới, khóa cũ, kid lạ, refresh đồng thời, stale cache, khóa khẩn cấp bị vô hiệu |
| JWE | alg/enc hợp lệ, cặp không được phép, key type sai, tag sai, khóa giải mã sai |
| Multi-issuer | Hai issuer cùng kid, cùng alg; xác minh không dùng chéo cache hoặc JWKS |
| Vận hành | JWKS timeout, phản hồi quá lớn, nhiều khóa, lỗi mạng, rate limit và log an toàn |

### 14.2. Chỉ số và log

Theo dõi các số liệu giúp phát hiện sai cấu hình hoặc tấn công:

- Số token bị từ chối do thuật toán ngoài allowlist.
- Số lần kid không tìm thấy, khóa không tương thích hoặc nhiều ứng viên mơ hồ.
- Số lần tải/làm mới JWKS, thời gian phản hồi, kích thước và số khóa nhận được.
- Số lỗi TLS, issuer mismatch, nguồn khóa không hợp lệ và lỗi parse JWK.
- Số khóa đang hoạt động, sắp hết hạn, bị vô hiệu hóa và số lần rotation.
- Tỷ lệ xác minh thành công/thất bại theo policy ID và endpoint.

Không ghi JWT, private key, HMAC secret hoặc toàn bộ JWK nhạy cảm. Có thể ghi policy ID, issuer ID đã được cấu hình, kid sau khi giới hạn độ dài, fingerprint public key và mã lỗi. Dữ liệu chưa xác minh phải được escape/giới hạn trước khi ghi log.

## 15. Checklist triển khai

1. [ ] Chính sách xác minh có allowlist thuật toán cụ thể theo endpoint, issuer và token profile.
2. [ ] JWS và JWE được xử lý theo hai quy trình đúng ngữ nghĩa; JWE kiểm tra cả alg và enc.
3. [ ] Loại khóa tương thích với thuật toán; kiểm tra RSA size, EC curve, OKP curve và độ dài HMAC secret.
4. [ ] JWK được kiểm tra kty, kid, use, key_ops, alg và vật liệu khóa.
5. [ ] Public JWKS không chứa private key material hoặc HMAC secret.
6. [ ] Khóa ký, khóa mã hóa và secret được phân tách theo mục đích khi có thể.
7. [ ] JWKS source được gắn với issuer đã đăng ký; không tải jku/x5u tùy ý.
8. [ ] Chứng chỉ x5c được xác minh đến trust anchor và đúng mục đích nếu profile sử dụng.
9. [ ] Cache khóa gắn với issuer/source; có giới hạn refresh và kế hoạch rotation/khẩn cấp.
10. [ ] Không có fallback thuật toán hoặc nguồn khóa khi xác minh thất bại.
11. [ ] Có kiểm thử algorithm confusion, key confusion, SSRF, kid trùng và key metadata sai.
12. [ ] Log/metrics không tiết lộ token hoặc bí mật và có thể truy vết policy đã áp dụng.

## 16. Tài liệu tiêu chuẩn liên quan

- **RFC 7515 — JSON Web Signature (JWS):** chữ ký, protected header và xác minh JWS.
- **RFC 7516 — JSON Web Encryption (JWE):** thuật toán quản lý khóa, mã hóa nội dung và authentication tag.
- **RFC 7517 — JSON Web Key (JWK):** loại khóa, metadata, JWK Set và cách biểu diễn vật liệu khóa.
- **RFC 7518 — JSON Web Algorithms (JWA):** thuật toán JOSE và các ràng buộc tham số/độ dài khóa.
- **RFC 7519 — JSON Web Token (JWT):** cấu trúc JWT và claims.
- **RFC 7638 — JSON Web Key (JWK) Thumbprint:** cách tạo dấu vân tay khóa từ các thành phần JWK được xác định.
- **RFC 8037 — CFRG Elliptic Curve Diffie-Hellman (ECDH) and Signatures in JOSE:** OKP, EdDSA và các thuật toán liên quan.
- **RFC 8725 — JSON Web Token Best Current Practices:** lựa chọn thuật toán, ràng buộc khóa và nguồn khóa, phòng algorithm confusion và issuer confusion.

**Nguyên tắc ghi nhớ:** Chỉ sử dụng thuật toán nằm trong allowlist; chỉ sử dụng khóa đúng loại, đúng mục đích và đủ mạnh; chỉ tin khóa có nguồn gốc được thiết lập độc lập với token. Sau phép xác minh mật mã, vẫn phải kiểm tra issuer, audience, thời gian và token profile trước khi chấp nhận JWT.
