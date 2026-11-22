# Khóa đối xứng và cặp khóa bất đối xứng

Mật mã học hiện đại sử dụng khóa để biến dữ liệu thành dạng chỉ bên có quyền mới có thể đọc, hoặc để chứng minh dữ liệu được tạo bởi bên nắm giữ một bí mật. Hai mô hình khóa cơ bản là **mật mã đối xứng (symmetric cryptography)** và **mật mã bất đối xứng (asymmetric cryptography)**. Hiểu rõ cách hai mô hình này hoạt động giúp lựa chọn đúng cơ chế ký, xác minh, mã hóa và trao đổi khóa khi triển khai JSON Web Token (JWT).

Bài học thuộc chương **Nền tảng tin cậy** của module **Security – JSON Web Token (JWT)**. Nội dung trình bày nền tảng mật mã áp dụng cho API và hệ thống phân tán nói chung, không phụ thuộc ngôn ngữ lập trình hay framework.

## 1. Khóa mật mã là gì?

**Khóa mật mã (cryptographic key)** là một giá trị được thuật toán sử dụng để thực hiện phép biến đổi hoặc kiểm tra mật mã. Thuật toán có thể công khai; điều cần được bảo vệ là khóa và cách hệ thống sử dụng khóa.

Một số thuật ngữ cơ bản:

- **Bản rõ (plaintext):** dữ liệu ở dạng có thể đọc hoặc xử lý trước khi mã hóa.
- **Bản mã (ciphertext):** dữ liệu sau khi được mã hóa.
- **Mã hóa (encryption):** biến bản rõ thành bản mã bằng thuật toán và khóa.
- **Giải mã (decryption):** khôi phục bản rõ từ bản mã bằng khóa phù hợp.
- **Chữ ký số (digital signature):** giá trị mật mã được tạo bằng khóa riêng và kiểm chứng bằng khóa công khai tương ứng.
- **MAC (Message Authentication Code):** giá trị xác thực được tạo và kiểm tra bằng khóa bí mật dùng chung.
- **Trao đổi/thỏa thuận khóa (key agreement):** các bên thiết lập một bí mật chung qua kênh có thể bị quan sát mà không gửi bí mật đó dưới dạng rõ.
- **Dẫn xuất khóa (key derivation):** tạo khóa mới từ bí mật đầu vào và ngữ cảnh bằng một hàm dẫn xuất khóa (KDF).

Khóa không giống mật khẩu. Khóa mật mã thường là dữ liệu nhị phân có độ ngẫu nhiên cao, được sinh bằng bộ sinh số ngẫu nhiên mật mã (CSPRNG). Mật khẩu do con người chọn thường có entropy thấp và cần quy trình xử lý riêng; không nên lấy một chuỗi mật khẩu tùy ý làm khóa ký JWT.

## 2. Mật mã đối xứng: các bên dùng chung bí mật

Trong **mật mã đối xứng**, bên thực hiện thao tác và bên kiểm tra/giải mã cùng nắm một khóa bí mật (hoặc khóa liên quan được dẫn xuất theo một giao thức). Bất kỳ bên nào sở hữu khóa đều có thể thực hiện các thao tác mà khóa cho phép.

### 2.1. Mô hình hoạt động

~~~mermaid
flowchart LR
    K["Khóa bí mật K"] --> E["Bên gửi"]
    K --> D["Bên nhận"]
    P["Bản rõ"] --> E
    E --> C["Bản mã"]
    C --> D
    D --> O["Bản rõ sau giải mã"]
~~~

Ví dụ với mã hóa đối xứng:

~~~text
ban_ma = Encrypt(khoa_K, ban_ro, nonce_va_tham_so)
ban_ro = Decrypt(khoa_K, ban_ma, nonce_va_tham_so)
~~~

Đây là mô hình khái niệm, không phải chỉ dẫn tự xây thuật toán. Trong hệ thống thực tế phải dùng chế độ mã hóa và thư viện chuẩn phù hợp, đồng thời quản lý nonce/IV, tag và định dạng dữ liệu theo yêu cầu của thuật toán.

**Ví dụ thuật toán mã hóa đối xứng:**

- **AES (Advanced Encryption Standard):** thuật toán khối phổ biến với các độ dài khóa 128, 192 hoặc 256 bit.
- **ChaCha20:** thuật toán mã hóa dòng; thường được dùng cùng Poly1305 trong cấu trúc mã hóa có xác thực ChaCha20-Poly1305.

Mã hóa đối xứng thường nhanh và phù hợp để bảo vệ lượng dữ liệu lớn. Điểm khó quan trọng là **phân phối và bảo vệ khóa chung**: làm sao để hai bên được phép có khóa mà người khác không lấy được khóa đó?

### 2.2. MAC cũng sử dụng khóa đối xứng

Mật mã đối xứng không chỉ dùng để mã hóa. **HMAC** và các MAC khác sử dụng khóa bí mật chung để kiểm tra tính toàn vẹn và xác thực thông điệp trong nhóm các bên biết khóa.

~~~text
tag = HMAC(khoa_K, thong_diep)
hop_le = Verify_HMAC(khoa_K, thong_diep_nhan, tag_nhan)
~~~

MAC không che giấu thông điệp. Nó chỉ giúp phát hiện thay đổi trái phép và xác nhận rằng bên tạo giá trị MAC thuộc nhóm có khả năng sử dụng khóa. Do bên xác minh cũng có khóa, bên đó cũng có thể tự tạo MAC hợp lệ.

Trong JWT, thuật toán **HS256** dùng HMAC với SHA-256. Bên phát hành và mọi bên xác minh HS256 đều phải nắm cùng bí mật. Nếu một API chỉ cần xác minh token nhưng có khóa HS256, về khả năng mật mã API đó cũng có thể tạo token với MAC hợp lệ.

### 2.3. Ưu điểm và giới hạn

| Ưu điểm | Giới hạn |
| --- | --- |
| Hiệu năng tốt, phù hợp dữ liệu lớn | Các bên cần chia sẻ bí mật an toàn |
| Khóa và thuật toán thường gọn, dễ áp dụng ở quy mô nhỏ | Số lượng bên tăng làm bài toán phân phối và quản lý khóa phức tạp |
| Có thể cung cấp bí mật với mã hóa hoặc toàn vẹn với MAC/AEAD | Bất kỳ bên nào giữ khóa chung đều có thể tạo giá trị hợp lệ |
| Phù hợp bảo vệ dữ liệu lưu trữ hoặc dữ liệu giữa hai workload đã thiết lập quan hệ tin cậy | Khi khóa bị lộ, mọi bên dùng cùng khóa có thể bị ảnh hưởng |

**Bài toán phân phối khóa:** nếu nhiều bên độc lập cùng xác minh MAC, tất cả phải nhận bí mật chung. Khó phân biệt bên nào đã tạo một MAC hợp lệ và khó giới hạn tác động nếu một bên bị xâm nhập.

## 3. Mật mã bất đối xứng: một cặp khóa có vai trò khác nhau

Trong **mật mã bất đối xứng**, một thực thể sở hữu một cặp khóa toán học liên quan:

- **Khóa riêng (private key):** phải được giữ bí mật và chỉ cấp cho thành phần được phép thực hiện thao tác riêng tư tương ứng.
- **Khóa công khai (public key):** có thể phân phối cho các bên cần kiểm chứng chữ ký, mã hóa dữ liệu cho chủ khóa hoặc tham gia thỏa thuận khóa, tùy loại thuật toán.

Không phải mọi cặp khóa đều dùng cho mọi mục đích. Một cặp khóa chữ ký số, một cặp khóa mã hóa và một cặp khóa thỏa thuận bí mật có thể có quy tắc sử dụng khác nhau. Hệ thống nên tách khóa theo mục đích thay vì dùng một khóa cho nhiều chức năng không tương thích.

### 3.1. Chữ ký số: khóa riêng ký, khóa công khai xác minh

Đối với thuật toán chữ ký số:

1. Bên phát hành dùng **khóa riêng** để tạo chữ ký trên dữ liệu.
2. Bên nhận dùng **khóa công khai tương ứng** để kiểm tra chữ ký.
3. Nếu chữ ký hợp lệ và khóa công khai được ràng buộc với issuer đáng tin, bên nhận có bằng chứng mật mã rằng dữ liệu không bị sửa sau khi ký và được tạo bởi bên nắm khóa riêng tương ứng.

~~~mermaid
flowchart LR
    P["Thông điệp"] --> S["Bên ký"]
    SK["Khóa riêng"] --> S
    S --> SIG["Thông điệp + chữ ký"]
    SIG --> V["Bên xác minh"]
    PK["Khóa công khai tin cậy"] --> V
    V --> R{"Chữ ký hợp lệ?"}
    R -- "Có" --> OK["Chấp nhận bước kiểm chứng mật mã"]
    R -- "Không" --> NO["Từ chối"]
~~~

Khóa công khai không cần bí mật, nên có thể phân phối cho nhiều API. Các API có thể xác minh token mà không có khả năng tạo chữ ký mới của issuer. Đây là lợi thế quan trọng trong kiến trúc có nhiều resource server.

**Ví dụ thuật toán chữ ký:** RSA-PSS, RSA PKCS#1 v1.5, ECDSA và EdDSA. Trong các hồ sơ JWT/JWS, các tên thuật toán thường gặp gồm RS256, PS256, ES256 và EdDSA (tùy mức hỗ trợ của hệ thống).

### 3.2. Mã hóa bất đối xứng: mã hóa bằng khóa công khai, giải mã bằng khóa riêng

Trong mô hình mã hóa khóa công khai cơ bản, người gửi mã hóa dữ liệu hoặc thiết lập khóa nội dung cho **người nhận** bằng thông tin khóa công khai của người nhận. Chỉ người sở hữu khóa riêng tương ứng mới có thể giải mã hoặc khôi phục khóa nội dung.

~~~mermaid
flowchart LR
    P["Bản rõ / khóa nội dung"] --> E["Bên gửi"]
    PK["Khóa công khai của người nhận"] --> E
    E --> C["Bản mã / khóa đã bọc"]
    C --> D["Bên nhận"]
    SK["Khóa riêng của người nhận"] --> D
    D --> O["Khôi phục nội dung"]
~~~

Trong hệ thống thực tế, mã hóa khóa công khai thường được dùng trong **mã hóa lai**: một khóa nội dung đối xứng ngẫu nhiên được tạo để mã hóa dữ liệu lớn; khóa nội dung sau đó được bọc/mã hóa hoặc thiết lập bằng cơ chế khóa công khai. Cách này kết hợp hiệu năng của mã hóa đối xứng và khả năng phân phối khóa của mật mã bất đối xứng.

Một JWE có thể dùng thuật toán quản lý khóa như RSA-OAEP hoặc ECDH-ES để thiết lập/bọc khóa nội dung, rồi dùng thuật toán `enc` như AES-GCM để bảo vệ payload.

Lưu ý: **mã hóa cho người nhận không tự xác thực danh tính người gửi**. Bất kỳ ai có khóa công khai của người nhận đều có thể tạo nội dung mã hóa gửi tới người nhận. Nếu người nhận cần biết thông điệp do một issuer cụ thể phát hành, cần thêm chữ ký hoặc cơ chế xác thực nguồn phù hợp.

### 3.3. Thỏa thuận khóa: hai bên cùng tạo bí mật

Một ứng dụng khác của mật mã bất đối xứng là **key agreement**, ví dụ Diffie–Hellman hoặc Elliptic-Curve Diffie–Hellman (ECDH). Hai bên trao đổi dữ liệu công khai và dùng khóa riêng tương ứng để tính ra cùng một bí mật chung, mà không gửi bí mật đó trực tiếp trên mạng.

~~~mermaid
sequenceDiagram
    participant A as Bên A
    participant B as Bên B
    A->>A: Tạo khóa riêng và khóa công khai tạm thời
    B->>B: Tạo khóa riêng và khóa công khai tạm thời
    A->>B: Gửi khóa công khai
    B->>A: Gửi khóa công khai
    A->>A: Tính bí mật chung từ private A và public B
    B->>B: Tính bí mật chung từ private B và public A
    Note over A,B: Hai bên thu được cùng bí mật chung
~~~

Thỏa thuận khóa cần xác thực danh tính/khóa công khai để chống tấn công man-in-the-middle. Một giao thức như TLS kết hợp các cơ chế trao đổi khóa, xác thực chứng chỉ, dẫn xuất khóa phiên và bảo vệ bản tin; không nên xem phép tính Diffie–Hellman đơn lẻ là đã có một kênh an toàn hoàn chỉnh.

## 4. So sánh hai mô hình khóa

| Tiêu chí | Đối xứng | Bất đối xứng |
| --- | --- | --- |
| Thành phần khóa | Một bí mật chung cho các bên được phép | Cặp khóa riêng và công khai có quan hệ toán học |
| Ai cần giữ bí mật? | Mọi bản sao của khóa chung | Khóa riêng; khóa công khai có thể phân phối |
| Phân phối khóa | Phải chuyển bí mật qua kênh an toàn hoặc thiết lập bằng giao thức | Có thể phân phối khóa công khai, nhưng cần xác thực khóa thuộc đúng chủ thể |
| Hiệu năng | Thường nhanh hơn, phù hợp dữ liệu lớn | Các phép toán thường tốn tài nguyên hơn; hay dùng để ký, trao đổi hoặc bọc khóa |
| Chữ ký số | Không cung cấp chữ ký số bất đối xứng; MAC dùng khóa chung | Có thể ký bằng khóa riêng và xác minh bằng khóa công khai |
| Xác thực nguồn | Xác thực trong nhóm biết chung bí mật | Có thể xác thực bên ký khi khóa công khai được gắn với danh tính tin cậy |
| Mã hóa | Mã hóa và giải mã bằng khóa bí mật chung | Mã hóa/thiết lập khóa cho người nhận bằng cặp khóa thích hợp |
| Rủi ro khi lộ khóa | Các bên cùng khóa và dữ liệu phụ thuộc khóa có thể bị ảnh hưởng | Lộ khóa riêng ảnh hưởng chức năng của cặp khóa; lộ khóa công khai không làm lộ bí mật nhưng thay khóa có thể gây giả mạo nếu bị thay thế |
| Ví dụ | AES-GCM, ChaCha20-Poly1305, HMAC-SHA-256 | RSA, elliptic-curve cryptography, EdDSA |

Không nên hiểu bất đối xứng luôn “an toàn hơn” đối xứng. Hai mô hình giải quyết những bài toán khác nhau và thường phối hợp trong cùng một giao thức.

## 5. Khóa công khai phải được gắn với đúng danh tính

Khóa công khai có thể đọc được bởi nhiều người, nhưng bên nhận phải biết **khóa đó thuộc về ai và được phép dùng cho mục đích nào**. Nếu kẻ tấn công thay khóa công khai hợp lệ bằng khóa của mình, chữ ký do kẻ tấn công tạo có thể được xác minh thành công bằng khóa giả đó.

### 5.1. Các cách thiết lập niềm tin

- **Chứng chỉ số (certificate):** một CA hoặc hệ thống PKI ký xác nhận mối liên kết giữa danh tính và khóa công khai theo chính sách chứng chỉ.
- **JWKS từ issuer đã cấu hình:** resource server lấy tập khóa công khai từ endpoint được cấu hình tin cậy cho issuer.
- **Pinning hoặc cấu hình khóa tin cậy:** ứng dụng có thể ghim khóa/fingerprint trong môi trường phù hợp, kèm quy trình cập nhật và khôi phục khi luân chuyển.
- **Kênh phân phối được xác thực:** khóa được phân phối qua hệ thống quản lý cấu hình/kho khóa có kiểm soát truy cập và kiểm tra tính toàn vẹn.

Một khóa công khai không tự chứng minh danh tính. Niềm tin đến từ cách khóa được phân phối, chứng thực, cập nhật và ràng buộc với issuer.

### 5.2. JWK và JWKS trong JWT

**JSON Web Key (JWK)** là định dạng biểu diễn một khóa mật mã bằng JSON. **JSON Web Key Set (JWKS)** là một tập hợp các JWK. Một issuer có thể công bố các khóa công khai để resource server xác minh chữ ký JWT.

Ví dụ một JWK RSA công khai ở dạng rút gọn:

~~~json
{
  "kty": "RSA",
  "use": "sig",
  "kid": "signing-key-2026-01",
  "alg": "RS256",
  "n": "<public-modulus>",
  "e": "AQAB"
}
~~~

Các trường `n` và `e` là thành phần công khai của khóa RSA. Khóa riêng có thêm thành phần bí mật, chẳng hạn `d`, và các giá trị riêng tư liên quan; không được đưa những thành phần đó vào JWKS công khai.

Với JWK dạng đối xứng (`kty: "oct"`), trường `k` chứa chính khóa bí mật. Không công bố JWK đối xứng trong endpoint JWKS công khai. Không nhầm việc endpoint JWKS có thể truy cập công khai với việc mọi loại JWK đều được phép công bố.

### 5.3. Vai trò và giới hạn của kid

Header `kid` là **Key ID**, giúp bên nhận chọn khóa phù hợp trong tập khóa tin cậy. Nó chỉ là định danh để tra cứu, không phải chữ ký, không phải bằng chứng khóa thuộc issuer và không phải quyền cho phép tải khóa từ bất kỳ nơi nào.

Quy trình an toàn cần:

1. Xác định issuer từ cấu hình tin cậy.
2. Lấy JWKS từ nguồn đã gắn với issuer đó theo chính sách.
3. Chọn khóa phù hợp dựa trên `kid` và loại khóa.
4. Kiểm tra thuật toán được phép, mục đích sử dụng khóa và các ràng buộc của hồ sơ token.
5. Xác minh chữ ký, sau đó mới sử dụng claims.

Không tự động tin URL `jku`, `x5u` hoặc chỉ dẫn tải khóa khác từ header JWT chưa xác minh. Nếu cho token tùy ý quyết định nguồn khóa, kẻ tấn công có thể điều hướng hệ thống tới khóa do mình kiểm soát.

## 6. Hai mô hình khóa được dùng thế nào trong JWT?

JWT là định dạng mang claims; JOSE quy định cách bảo vệ các claims đó bằng JWS và JWE. Việc chọn thuật toán quyết định loại khóa cần có ở bên phát hành và bên nhận.

### 6.1. JWS với khóa đối xứng: HS256

HS256 là HMAC sử dụng SHA-256 với khóa bí mật chung:

~~~text
Issuer:        HMAC(shared_secret, protected_header || "." || payload)
Resource API:  kiểm tra HMAC bằng cùng shared_secret
~~~

Ưu điểm:

- Cấu hình đơn giản khi chỉ có một số ít thành phần trong cùng miền tin cậy.
- Hiệu năng tốt.
- Không cần công bố khóa xác minh.

Giới hạn:

- Mọi bên xác minh đều phải có bí mật chung và do đó có thể tạo MAC.
- Phân phối khóa cho nhiều API làm tăng số nơi phải bảo vệ bí mật.
- Nếu một bên làm lộ khóa, kẻ tấn công có thể tạo token hợp lệ cho mọi bên dùng khóa đó.

Chỉ dùng HS256 khi mô hình tin cậy cho phép tất cả bên xác minh có khả năng ký và có quy trình phân phối/luân chuyển bí mật rõ ràng. Khóa phải được tạo ngẫu nhiên với entropy phù hợp, không dùng mật khẩu hoặc chuỗi dễ đoán.

### 6.2. JWS với cặp khóa bất đối xứng: RS256, PS256, ES256, EdDSA

Với chữ ký bất đối xứng:

- Issuer giữ **khóa riêng** để ký.
- Resource server giữ **khóa công khai** để xác minh.
- Resource server không cần biết bí mật có thể tạo chữ ký.

| Thuật toán JWS | Họ mật mã | Đặc điểm khái quát |
| --- | --- | --- |
| RS256 | RSA + SHA-256, RSASSA-PKCS1-v1_5 | Tương thích rộng trong nhiều hệ thống JOSE |
| PS256 | RSA-PSS + SHA-256 | Dùng cơ chế padding PSS |
| ES256 | ECDSA trên P-256 + SHA-256 | Chữ ký gọn hơn RSA ở mức bảo mật tương đương theo cấu hình phù hợp |
| EdDSA | Ed25519/Ed448 theo hồ sơ JOSE | Chữ ký dựa trên Edwards-curve, cần hỗ trợ tương thích từ các bên |

Các thuật toán có yêu cầu định dạng khóa, kích thước, encoding chữ ký và mức hỗ trợ khác nhau. Không tự chuyển đổi byte chữ ký giữa các thư viện nếu chưa tuân thủ đúng định dạng JWS. Hệ thống phải cấu hình danh sách thuật toán cho phép; không để header `alg` của token quyết định tùy ý thuật toán xác minh.

### 6.3. JWE kết hợp hai mô hình

JWE thường phối hợp quản lý khóa bất đối xứng hoặc bí mật chung với mã hóa nội dung đối xứng:

- Trường `alg` chỉ định thuật toán quản lý khóa hoặc thiết lập khóa nội dung, ví dụ `RSA-OAEP-256`, `ECDH-ES` hoặc `dir`.
- Trường `enc` chỉ định thuật toán mã hóa nội dung, ví dụ `A256GCM` hoặc `A128CBC-HS256`.

Với `RSA-OAEP-256`, người gửi có thể dùng khóa công khai người nhận để bảo vệ khóa nội dung; người nhận dùng khóa riêng để khôi phục khóa nội dung rồi giải mã payload. Với `ECDH-ES`, hai bên sử dụng trao đổi khóa ECDH theo quy tắc JOSE để dẫn xuất khóa. Với `dir`, khóa nội dung đối xứng được chia sẻ trực tiếp theo cấu hình.

Do đó, một JWE không đơn giản là “mã hóa bằng khóa RSA”. Nó có thể dùng cơ chế khóa bất đối xứng để thiết lập khóa và dùng thuật toán đối xứng để bảo vệ dữ liệu thực tế.

### 6.4. Bảng chọn nhanh theo vai trò

| Kiến trúc | Mô hình thường cân nhắc | Lý do |
| --- | --- | --- |
| Một issuer và một API trong cùng miền tin cậy | HS256 có thể phù hợp | Ít bên chia sẻ khóa; cả hai cùng được phép tạo MAC theo mô hình tin cậy |
| Một issuer phát hành token cho nhiều API độc lập | Chữ ký bất đối xứng như RS256/PS256/ES256/EdDSA | API chỉ cần khóa công khai để xác minh, không có khóa phát hành |
| API cần đọc claims nhưng không muốn mọi bên nhìn thấy payload | JWE, cùng cơ chế xác thực issuer phù hợp | Bảo vệ bí mật payload; cần kiểm tra lớp chữ ký nếu phải xác thực issuer độc lập |
| Cần vừa xác minh issuer vừa giữ bí mật claims | JWS lồng trong JWE | Chữ ký xác thực nội dung/issuer; lớp mã hóa giới hạn người đọc |

Không có thuật toán phù hợp cho mọi kiến trúc. Lựa chọn phải xét số lượng bên xác minh, ranh giới tin cậy, cách phân phối khóa, khả năng tương thích, hiệu năng, yêu cầu bí mật và quy trình ứng phó khi khóa bị lộ.

## 7. Quản lý vòng đời khóa

Khóa an toàn không chỉ là khóa có độ dài đủ lớn. Khóa phải được tạo, phân phối, lưu trữ, sử dụng, luân chuyển và hủy theo một quy trình kiểm soát.

### 7.1. Sinh khóa

- Dùng CSPRNG hoặc cơ chế sinh khóa do thư viện mật mã/KMS/HSM đáng tin cung cấp.
- Chọn độ dài và loại khóa theo thuật toán, mức bảo mật và khuyến nghị hiện hành.
- Không tự tạo khóa từ timestamp, số tăng dần, tên người dùng hoặc mật khẩu yếu.
- Không dùng lại cùng khóa cho nhiều mục đích như ký, mã hóa và MAC nếu thiết kế/chuẩn không cho phép.

### 7.2. Lưu trữ và kiểm soát truy cập

**Khóa riêng và khóa đối xứng là dữ liệu bí mật có giá trị cao.** Nên giới hạn thành phần, tài khoản và người vận hành được phép sử dụng khóa.

- Dùng HSM hoặc KMS khi yêu cầu bảo vệ và khả năng kiểm toán cần thiết.
- Dùng secret manager cho bí mật ứng dụng; giới hạn quyền đọc và ghi theo workload.
- Không commit khóa vào repository, image container, frontend bundle, ticket hoặc log.
- Tách quyền sử dụng khóa khỏi quyền quản trị hạ tầng khi mô hình tổ chức yêu cầu.
- Ghi audit việc tạo, sử dụng, xoay vòng và thu hồi khóa mà không ghi giá trị bí mật.

Mã hóa khóa khi lưu trữ không giải quyết mọi rủi ro nếu tiến trình ứng dụng có thể đọc khóa ở dạng rõ hoặc kẻ tấn công chiếm được quyền gọi dịch vụ ký. HSM/KMS có thể giữ khóa không xuất được và chỉ cho phép thao tác ký/giải mã theo chính sách, nhưng vẫn cần bảo vệ quyền gọi API của KMS.

### 7.3. Phân phối khóa

| Loại khóa | Cách phân phối |
| --- | --- |
| Khóa đối xứng | Kênh bảo mật, secret manager/KMS hoặc thiết lập bí mật qua giao thức đã xác thực |
| Khóa riêng bất đối xứng | Không phân phối rộng; giữ tại issuer hoặc HSM/KMS được phép ký |
| Khóa công khai | JWKS, chứng chỉ, PKI hoặc kênh cấu hình được xác thực |
| Khóa dẫn xuất/khóa phiên | Dẫn xuất theo giao thức và ngữ cảnh; giới hạn thời gian, mục đích và bên sử dụng |

Không gửi khóa đối xứng qua cùng kênh không bảo vệ với dữ liệu mà khóa đó phải bảo vệ. Không tin khóa công khai chỉ vì nhận được nó; phải xác minh mối liên hệ giữa khóa và chủ thể.

### 7.4. Luân chuyển khóa (key rotation)

Khóa cần được thay khi đến lịch, khi nghi ngờ bị lộ, khi nhân sự/quyền truy cập thay đổi hoặc khi thuật toán không còn được chấp nhận.

Một quy trình luân chuyển khóa ký JWT có thể gồm:

1. Tạo cặp khóa mới và lưu khóa riêng ở nơi được bảo vệ.
2. Công bố khóa công khai mới trong JWKS với `kid` mới.
3. Đảm bảo resource server có thể nhận khóa mới, tính tới cache và thời gian lan truyền.
4. Chuyển issuer sang ký token bằng khóa mới.
5. Giữ khóa công khai cũ trong thời gian các token ký bằng khóa cũ còn được phép sử dụng.
6. Sau khi token cũ hết hạn hoặc bị vô hiệu theo chính sách, gỡ khóa công khai cũ.

Nếu khóa riêng bị xâm phạm, không thể chỉ thực hiện rotation thông thường rồi tin mọi token cũ. Cần đánh giá khả năng giả mạo, ngừng tin khóa bị lộ, thu hồi/đánh dấu token liên quan và cập nhật tất cả resource server. Thời gian cache JWKS phải được tính vào kế hoạch.

### 7.5. Tách khóa theo mục đích

Một hệ thống có thể cần nhiều loại khóa:

- Khóa ký access token.
- Khóa mã hóa JWE cho từng nhóm người nhận.
- Khóa HMAC cho MAC hoặc fingerprint log.
- Khóa mã hóa dữ liệu lưu trữ.
- Khóa TLS/chứng chỉ cho workload.

Không nên dùng cùng một byte sequence cho mọi chức năng. Tách khóa giúp giảm tác động khi một khóa bị lộ và tránh nhầm lẫn giữa mục đích sử dụng. Khi dẫn xuất nhiều khóa từ một bí mật gốc, dùng KDF chuẩn có context/label riêng cho từng mục đích.

## 8. Những lỗi thường gặp khi sử dụng khóa

### Lỗi A — Nghĩ rằng khóa công khai phải được giữ bí mật

Khóa công khai được thiết kế để phân phối. Điều phải bảo vệ là **tính xác thực của khóa**: người nhận cần biết khóa thuộc đúng issuer. Che giấu khóa công khai không thay thế xác minh nguồn gốc.

### Lỗi B — Đưa khóa riêng vào JWKS công khai

JWK RSA/EC có thể chứa cả trường công khai và trường riêng. Nếu vô tình xuất bản `d`, `p`, `q`, `k` hoặc thành phần bí mật khác, khóa có thể bị xâm phạm. JWKS công khai chỉ chứa thành phần công khai phù hợp.

### Lỗi C — Tất cả API giữ chung khóa HS256

Mỗi API có khóa HMAC đều có khả năng tạo MAC hợp lệ. Nếu API chỉ cần xác minh, việc phân phối khóa riêng cho từng API bằng mô hình chữ ký bất đối xứng có thể giảm quyền phát hành không cần thiết.

### Lỗi D — Tin `kid` hoặc `jku` từ token chưa xác minh

`kid` chỉ giúp chọn khóa trong tập đã tin cậy. URL tải khóa trong header không được tự động xem là nguồn tin. Phải ràng buộc issuer và nguồn JWKS bằng cấu hình đáng tin.

### Lỗi E — Dùng cùng khóa cho mã hóa và ký

Việc tái sử dụng khóa cho nhiều thuật toán/mục đích có thể phá vỡ giả định bảo mật và gây lỗi liên miền. Dùng khóa riêng theo mục đích, thuật toán và bên sử dụng.

### Lỗi F — Dùng mật khẩu làm khóa HMAC

Mật khẩu thường dễ đoán hơn khóa ngẫu nhiên. Nếu cần dùng bí mật do người dùng cung cấp, phải có quy trình dẫn xuất khóa phù hợp và mục tiêu bảo mật rõ ràng; với khóa ký hệ thống, ưu tiên khóa ngẫu nhiên đủ mạnh được quản lý an toàn.

### Lỗi G — Đổi khóa nhưng xóa khóa công khai cũ quá sớm

Resource server có thể vẫn nhận token hợp lệ được ký bằng khóa cũ. Xóa khóa công khai trước khi token cũ hết hạn hoặc trước khi các cache cập nhật có thể gây lỗi xác minh hàng loạt. Cần có giai đoạn chồng lấp khóa theo chính sách.

### Lỗi H — Đổi khóa nhưng vẫn tin khóa riêng đã lộ

Khi khóa riêng bị xâm phạm, kẻ tấn công có thể tiếp tục ký token giả bằng khóa cũ. Phải ngừng tin khóa đó và xử lý các token có thể bị giả mạo, không chỉ tạo khóa mới cho các token phát hành trong tương lai.

## 9. Ví dụ tổng hợp: chọn khóa cho hệ thống JWT nhiều API

Giả sử một Identity Provider phát hành access token cho ba resource server: billing, payment và reporting.

**Phương án A: dùng HS256 chung**

- Identity Provider và cả ba API cùng giữ bí mật HMAC.
- Các API có thể xác minh token nhanh.
- Mỗi API cũng có khả năng tạo MAC hợp lệ.
- Khi một API bị xâm nhập và lộ khóa, phạm vi ảnh hưởng có thể bao trùm mọi bên dùng khóa chung.

**Phương án B: dùng chữ ký bất đối xứng**

- Identity Provider giữ khóa riêng trong HSM/KMS để ký.
- Ba API lấy khóa công khai từ JWKS đã gắn với issuer tin cậy.
- Các API xác minh được chữ ký nhưng không thể tạo chữ ký mới của issuer.
- Khóa công khai có thể cache và cần quy trình cập nhật/luân chuyển.

~~~mermaid
flowchart TD
    I["Identity Provider"] -->|"Ký bằng private key"| T["JWT access token"]
    I -->|"Công bố public keys qua JWKS"| J["JWKS đã xác thực nguồn"]
    T --> B["Billing API"]
    T --> P["Payment API"]
    T --> R["Reporting API"]
    J --> B
    J --> P
    J --> R
    B --> V1["Xác minh chữ ký + claims + quyền"]
    P --> V2["Xác minh chữ ký + claims + quyền"]
    R --> V3["Xác minh chữ ký + claims + quyền"]
~~~

Phương án B tạo ranh giới rõ giữa thành phần phát hành và các thành phần xác minh. Dù vậy, mỗi API vẫn phải kiểm tra `iss`, `aud`, thời hạn, loại token và quyền trên tài nguyên. Khóa công khai đúng không khiến token dành cho billing tự động được chấp nhận ở payment.

Nếu hệ thống còn cần ẩn claims khỏi bên cầm token, có thể xem xét JWE. Khi cần vừa bảo mật payload vừa xác thực độc lập issuer, có thể dùng JWS lồng trong JWE với thứ tự xác minh đúng.

## 10. Chọn mô hình khóa theo câu hỏi kiến trúc

Trước khi chọn thuật toán, hãy trả lời:

1. Có bao nhiêu thành phần cần xác minh? Chúng có cùng miền tin cậy không?
2. Bên xác minh có được phép tự tạo thông điệp/token hợp lệ không?
3. Có yêu cầu giữ bí mật nội dung hay chỉ cần toàn vẹn và xác thực nguồn?
4. Khóa được phân phối và luân chuyển bằng cách nào?
5. Nếu một thành phần bị xâm nhập, phạm vi khóa bị lộ là bao nhiêu?
6. Có yêu cầu tương thích với thư viện, nền tảng hoặc đối tác hiện có không?
7. Có cần HSM/KMS, audit, separation of duties hoặc chứng chỉ không?

| Nhu cầu | Mô hình nên xem xét |
| --- | --- |
| Một nhóm nhỏ cùng tin cậy, cần MAC giữa các thành viên | Khóa đối xứng |
| Một issuer ký token cho nhiều API chỉ cần xác minh | Cặp khóa bất đối xứng cho chữ ký |
| Bảo vệ bí mật dữ liệu lớn | Mã hóa đối xứng, thường qua AEAD |
| Gửi dữ liệu bí mật cho một người nhận | Mã hóa lai, thiết lập/bọc khóa bằng cơ chế bất đối xứng và mã hóa nội dung đối xứng |
| Hai bên thiết lập khóa phiên qua mạng | Key agreement đã xác thực, ví dụ ECDH trong giao thức chuẩn |
| Cần xác minh nguồn phát hành và giấu payload JWT | JWS kết hợp JWE |

## 11. Checklist quản lý khóa cho hệ thống JWT

### Thiết kế và lựa chọn

- [ ] Xác định mục đích khóa: ký, xác minh, MAC, mã hóa, thỏa thuận khóa hay TLS.
- [ ] Chọn thuật toán và kích thước khóa theo tiêu chuẩn/hồ sơ được chấp nhận.
- [ ] Xác định rõ bên nào được ký, bên nào chỉ xác minh và bên nào được giải mã.
- [ ] Dùng khóa riêng biệt cho từng mục đích, issuer, môi trường hoặc workload khi phù hợp.
- [ ] Cấu hình allowlist thuật toán; không để token tự chọn thuật toán tùy ý.

### Sinh, lưu và phân phối

- [ ] Sinh khóa bằng CSPRNG hoặc KMS/HSM đáng tin.
- [ ] Không dùng mật khẩu yếu, timestamp hoặc dữ liệu dễ đoán làm khóa.
- [ ] Không commit khóa riêng/khóa đối xứng vào repository hoặc frontend.
- [ ] Giới hạn quyền truy cập và thao tác khóa theo nguyên tắc tối thiểu.
- [ ] Phân phối public key qua JWKS/chứng chỉ/kênh tin cậy; xác minh liên kết với issuer.
- [ ] Không công bố thành phần khóa riêng trong JWKS công khai.

### Vận hành và luân chuyển

- [ ] Có `kid` để nhận diện khóa và quy trình cập nhật JWKS.
- [ ] Có thời gian chồng lấp hợp lý khi chuyển khóa bình thường.
- [ ] Có quy trình khẩn cấp khi private key hoặc shared secret bị lộ.
- [ ] Kiểm soát cache JWKS và xử lý khóa không còn được tin cậy.
- [ ] Audit thao tác sử dụng/luân chuyển/thu hồi mà không ghi giá trị bí mật.
- [ ] Kiểm tra khả năng tương thích thuật toán giữa issuer và tất cả resource server.

## 12. Tự kiểm tra

| Câu hỏi | Đáp án |
| --- | --- |
| Trong HS256, resource server có khóa bí mật có thể tự tạo MAC hợp lệ không? | **Có.** Mọi bên giữ shared secret đều có khả năng tạo và xác minh MAC. |
| Resource server chỉ giữ public key RS256 có thể ký token như issuer không? | **Không.** Việc ký cần private key tương ứng. |
| Public key có thể công bố rộng rãi không? | **Có**, nhưng phải bảo vệ tính xác thực của nguồn phân phối và mối liên kết với issuer. |
| Mã hóa bằng public key của người nhận có chứng minh người gửi là ai không? | **Không.** Bất kỳ ai có public key đều có thể tạo nội dung mã hóa tới người nhận. |
| ECDH có tự xác thực hai bên không? | **Không.** Cần xác thực khóa công khai/định danh bằng chứng chỉ hoặc cơ chế tin cậy của giao thức. |
| JWK RSA công khai có được chứa `d` không? | **Không.** `d` là thành phần private của khóa RSA. |
| Trường `kid` có phải bằng chứng khóa thuộc issuer không? | **Không.** Nó chỉ giúp chọn khóa trong tập khóa đã tin cậy. |
| Khi một API giữ khóa HS256 bị xâm nhập, chỉ API đó có bị ảnh hưởng không? | **Không nhất thiết.** Nếu shared secret bị lộ, mọi bên dùng khóa đó và token liên quan có thể bị ảnh hưởng. |
| Có nên xóa public key cũ ngay khi bắt đầu ký bằng key mới không? | **Không mặc định.** Cần duy trì khóa cũ trong thời gian token cũ còn hợp lệ, trừ tình huống khóa bị xâm phạm cần ngừng tin khẩn cấp. |

## 13. Ghi nhớ

- **Đối xứng:** các bên dùng chung bí mật. Hiệu năng tốt, phù hợp mã hóa dữ liệu lớn và MAC; bài toán khó là phân phối, bảo vệ và giới hạn số bên có khóa.
- **Bất đối xứng:** dùng cặp khóa riêng/công khai. Khóa riêng thực hiện thao tác ký hoặc giải mã/thỏa thuận tương ứng; khóa công khai được phân phối để xác minh, mã hóa cho người nhận hoặc tham gia thỏa thuận khóa.
- **Chữ ký JWT:** HS256 dùng khóa HMAC chung; RS256, PS256, ES256 và EdDSA là các ví dụ dùng chữ ký bất đối xứng.
- **Mã hóa JWT:** JWE thường kết hợp quản lý khóa với mã hóa nội dung; `alg` và `enc` có vai trò khác nhau.
- **Niềm tin vào khóa công khai:** cần xác minh nguồn phân phối và mối liên kết với issuer; `kid` không tự tạo ra niềm tin.
- **Quản lý khóa:** sinh ngẫu nhiên, tách mục đích, lưu an toàn, phân phối đúng, luân chuyển có kế hoạch và xử lý khẩn cấp khi bị lộ.

### Tiêu chuẩn và tài liệu tham khảo

- [RFC 7515 – JSON Web Signature (JWS)](https://www.rfc-editor.org/rfc/rfc7515)
- [RFC 7516 – JSON Web Encryption (JWE)](https://www.rfc-editor.org/rfc/rfc7516)
- [RFC 7517 – JSON Web Key (JWK)](https://www.rfc-editor.org/rfc/rfc7517)
- [RFC 7518 – JSON Web Algorithms (JWA)](https://www.rfc-editor.org/rfc/rfc7518)
- [RFC 8037 – CFRG Elliptic Curve Diffie-Hellman and Signatures in JOSE](https://www.rfc-editor.org/rfc/rfc8037)
- [RFC 8725 – JSON Web Token Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725)
- [NIST SP 800-57 Part 1 – Recommendation for Key Management](https://csrc.nist.gov/pubs/sp/800/57/pt1/r5/final)
- [NIST SP 800-56A – Recommendation for Pair-Wise Key-Establishment Schemes](https://csrc.nist.gov/pubs/sp/800/56/a/r3/final)
