# Chi phí xác minh HMAC, RSA, ECDSA và EdDSA theo tải thực tế

## 1. Vì sao cần đo chi phí xác minh JWT?

Trong một hệ thống dùng JSON Web Token (JWT), issuer thường ký token khi phát hành, còn resource server có thể xác minh token ở gần như mọi request được bảo vệ. Nếu một access token được dùng cho hàng nghìn request, chi phí xác minh có thể lặp lại nhiều lần trong khi chi phí ký chỉ xảy ra một lần khi cấp token.

Vì vậy, lựa chọn thuật toán chữ ký không nên chỉ dựa trên tốc độ tạo token hoặc một bảng benchmark tổng quát. Cần xem:

- Chi phí ký tại Authorization Server (AS).
- Chi phí xác minh tại Resource Server (RS).
- Số lượng request cần xác minh mỗi giây.
- Số lượng issuer, resource server và key rotation.
- Kích thước chữ ký và tổng kích thước token.
- Chi phí parse token, chọn khóa, cache JWKS và kiểm tra claims.
- Hỗ trợ của thư viện, hệ điều hành, CPU, HSM hoặc cryptographic provider.
- Mức độ bảo mật, khả năng phân phối khóa và phạm vi ảnh hưởng khi khóa bị lộ.

Một thuật toán có phép xác minh nhanh nhưng chữ ký lớn có thể tăng băng thông và chi phí gateway. Một thuật toán có chữ ký nhỏ nhưng thư viện ở nền tảng triển khai không tối ưu có thể cho kết quả thực tế kém hơn dự kiến.

**Chi phí cần tối ưu là chi phí của toàn bộ đường xử lý request trong môi trường thật, không chỉ thời gian gọi một hàm verify.**

Bài viết thuộc phạm vi **Security - JSON Web Token (JWT)** tổng quát, tập trung vào so sánh HMAC, RSA, ECDSA và EdDSA theo tải thực tế, không phụ thuộc ngôn ngữ lập trình hay framework.

## 2. Đường xử lý JWT có những khoản chi phí nào?

### 2.1. Tách chi phí mật mã khỏi chi phí xung quanh

Khi resource server nhận một JWT, đường xử lý thường gồm:

1. Nhận HTTP request và lấy Bearer token.
2. Kiểm tra kích thước, cú pháp và parse compact serialization.
3. Đọc protected header để lấy thuật toán và key identifier.
4. Chọn khóa xác minh từ key cache/JWKS đã cấu hình.
5. Tính toán và xác minh chữ ký hoặc MAC.
6. Kiểm tra issuer, audience, thời gian, token type và claims bắt buộc.
7. Tạo principal/security context.
8. Đánh giá quyền và thực hiện nghiệp vụ.

Chỉ bước 5 là phép xác minh mật mã. Các bước khác cũng có chi phí CPU, bộ nhớ, mạng và độ trễ. Nếu mỗi request đều tải JWKS, parse PEM hoặc khởi tạo lại crypto provider, benchmark sẽ đo cả lỗi thiết kế vận hành thay vì chỉ đo thuật toán.

~~~mermaid
flowchart TD
    A["HTTP request"] --> B["Extract và parse JWT"]
    B --> C["Chọn issuer / kid / key"]
    C --> D["Verify HMAC hoặc chữ ký"]
    D --> E["Validate issuer, audience, time, profile"]
    E --> F["Tạo verified principal"]
    F --> G["Authorization policy"]
    G --> H["Business operation"]
    C -. "Cache miss / rotation" .-> K["JWKS hoặc Key Provider"]
    K --> C
~~~

### 2.2. Chi phí phát hành và xác minh khác nhau

| Vị trí | Công việc | Tần suất điển hình |
| --- | --- | --- |
| Authorization Server | Xác minh grant, tạo claims, ký token | Khi phát hành hoặc refresh token |
| Resource Server | Parse, chọn khóa, xác minh chữ ký/MAC và claims | Mỗi request mang access token, trừ khi có cache phù hợp |
| JWKS/key provider | Phân phối khóa xác minh | Khi khởi động, hết cache hoặc phát hiện key ID mới |
| Policy/data provider | Kiểm tra quyền và trạng thái nghiệp vụ | Theo request hoặc theo cache/policy |

Với hệ thống phát hành token ít nhưng xác minh rất nhiều, hiệu năng verify thường quan trọng hơn hiệu năng sign. Với hệ thống phát hành assertion liên tục hoặc có nhiều client, chi phí sign cũng có thể trở thành nút thắt.

### 2.3. Không phải request nào cũng cần xác minh lại theo cùng một cách

Mặc định an toàn phổ biến là xác minh chữ ký trên mỗi request. Có thể cache kết quả xác minh hoặc principal trong một số kiến trúc, nhưng cache phải được giới hạn bởi:

- Thời hạn token.
- Khả năng thu hồi token hoặc khóa.
- Thay đổi trạng thái tài khoản/quyền.
- Audience, issuer và token profile.
- Rủi ro replay hoặc sender constraint.

Không bỏ xác minh chỉ để tăng throughput. Nếu dùng cache verified token, phải đánh giá chính xác thời gian cửa sổ mà token bị thu hồi hoặc khóa bị thay đổi vẫn có thể được chấp nhận.

## 3. HMAC, RSA, ECDSA và EdDSA khác nhau ở đâu?

### 3.1. HMAC (HS256, HS384, HS512)

HMAC là cơ chế MAC đối xứng. Issuer và mọi verifier đều giữ cùng một secret:

~~~text
signature = HMAC(hash_function, secret_key, signing_input)
~~~

Đặc điểm:

- Phép tính thường rất nhanh, đặc biệt với HMAC-SHA-256 trên CPU và thư viện được tối ưu.
- Kích thước MAC cố định theo hàm băm: HS256 là 32 byte, HS384 là 48 byte, HS512 là 64 byte.
- Xác minh và ký đều cần cùng secret.
- Mọi verifier giữ secret cũng có khả năng phát hành token giả nếu bị xâm nhập.
- Secret phải có entropy và kích thước tối thiểu theo JWA.

HMAC thường có chi phí mật mã thấp, nhưng chi phí phân phối secret và phạm vi ảnh hưởng có thể cao trong hệ thống nhiều resource server hoặc nhiều tổ chức.

### 3.2. RSA (RS256, PS256 và các biến thể)

RSA dùng cặp khóa private/public. Issuer ký bằng private key; resource server xác minh bằng public key.

Đặc điểm:

- RS256 dùng RSASSA-PKCS1-v1_5 với SHA-256.
- PS256 dùng RSASSA-PSS với SHA-256 theo tham số JOSE quy định.
- Chữ ký có độ dài bằng kích thước modulus RSA.
- RSA-2048 tạo chữ ký 256 byte; RSA-3072 tạo chữ ký 384 byte; RSA-4096 tạo chữ ký 512 byte.
- Xác minh RSA với public exponent phổ biến 65537 thường có thể rất hiệu quả; ký bằng private key thường đắt hơn verify.
- RSA có độ tương thích rộng, nhưng chữ ký lớn hơn đáng kể so với HMAC, ECDSA P-256 và Ed25519.

RS256 và PS256 không phải cùng một thuật toán chỉ vì đều dùng RSA và SHA-256. Verifier phải allowlist đúng thuật toán đã thỏa thuận. Hỗ trợ PS256 có thể khác nhau giữa thư viện và hệ thống cũ.

### 3.3. ECDSA (ES256, ES384, ES512)

ECDSA dùng đường cong elliptic. Trong JOSE:

- ES256 dùng P-256 và SHA-256.
- ES384 dùng P-384 và SHA-384.
- ES512 dùng P-521 và SHA-512.

Đặc điểm:

- Kích thước chữ ký nhỏ hơn RSA ở mức bảo mật tương đương thường được so sánh.
- ES256 có chữ ký JOSE dài đúng 64 byte: 32 byte R nối với 32 byte S.
- ES384 có chữ ký 96 byte; ES512 có chữ ký 132 byte.
- Một số API mật mã cấp thấp biểu diễn chữ ký ECDSA theo ASN.1 DER; JWS yêu cầu biểu diễn cố định R || S. Thư viện JOSE phải chuyển đổi đúng định dạng.
- Tốc độ sign/verify phụ thuộc đường cong, thư viện, phần cứng và provider.
- Việc tạo chữ ký cần nonce ECDSA an toàn; tái sử dụng hoặc sinh nonce sai có thể làm lộ private key.

ECDSA hấp dẫn khi cần chữ ký gọn, nhưng phải kiểm tra chất lượng triển khai, hỗ trợ curve và xử lý định dạng chữ ký trong thư viện.

### 3.4. EdDSA (Ed25519 và Ed448)

JOSE định nghĩa thuật toán EdDSA qua RFC 8037. Các lựa chọn thường gặp là Ed25519 và Ed448.

Đặc điểm:

- Ed25519 dùng public key 32 byte và chữ ký 64 byte.
- Ed448 dùng public key 57 byte và chữ ký 114 byte.
- EdDSA có chữ ký kích thước cố định, không cần biểu diễn R/S theo định dạng DER.
- Ed25519 có quy trình ký xác định, tránh yêu cầu sinh nonce ngẫu nhiên theo cách ECDSA truyền thống.
- EdDSA thường có hiệu năng phần mềm tốt và chữ ký gọn, nhưng hiệu năng cụ thể vẫn phụ thuộc thư viện/provider và nền tảng.
- Hỗ trợ EdDSA trên hệ sinh thái cũ hoặc HSM/provider nhất định có thể chưa đồng đều như RSA.

Trong JOSE, tên thuật toán là `EdDSA`; loại curve được xác định qua khóa. Không tự giả định mọi thư viện hỗ trợ mọi biến thể EdDSA.

## 4. So sánh chi phí xác minh và ký

### 4.1. Xu hướng tổng quát

Bảng dưới đây mô tả xu hướng thường gặp, không phải thứ hạng hiệu năng cố định:

| Thuật toán | Chi phí verify thường gặp | Chi phí sign thường gặp | Kích thước chữ ký |
| --- | --- | --- | --- |
| HS256 | Rất thấp | Rất thấp | 32 byte |
| HS384 | Thấp | Thấp | 48 byte |
| HS512 | Thấp; xử lý nhiều byte hơn HS256 | Thấp; xử lý nhiều byte hơn HS256 | 64 byte |
| RS256 | Thường khá hiệu quả với public exponent phổ biến | Cao hơn verify đáng kể trong nhiều triển khai | Theo modulus: 256 byte ở RSA-2048 |
| PS256 | Cùng họ chi phí RSA; tùy triển khai PSS | Thường đắt hơn verify | Theo modulus: 256 byte ở RSA-2048 |
| ES256 | Phụ thuộc tối ưu P-256; thường ở mức vừa | Phụ thuộc thư viện và nonce generation | 64 byte |
| ES384 | Thường đắt hơn ES256 do curve lớn hơn | Thường đắt hơn ES256 | 96 byte |
| ES512 | Curve P-521 có thể tốn CPU hơn đáng kể | Có thể tốn CPU hơn ES256/ES384 | 132 byte |
| EdDSA / Ed25519 | Thường hiệu quả trong phần mềm hiện đại | Thường hiệu quả trong phần mềm hiện đại | 64 byte |
| EdDSA / Ed448 | Thường nặng hơn Ed25519 | Thường nặng hơn Ed25519 | 114 byte |

Không thể kết luận “HMAC luôn nhanh nhất” hoặc “Ed25519 luôn nhanh hơn RSA” cho mọi môi trường. Một RSA verifier được tối ưu bằng phần cứng có thể vượt một triển khai ECDSA/EdDSA thiếu tối ưu. Một HSM có thể làm thay đổi hoàn toàn tương quan giữa sign và verify.

### 4.2. Vì sao RSA verify có thể nhanh?

RSA public-key operation thường dùng public exponent nhỏ, phổ biến là 65537. Điều này giúp phép xác minh có thể ít tốn CPU hơn phép ký dùng private exponent. Tuy nhiên:

- Modulus lớn làm chữ ký dài hơn.
- Private-key operation có chi phí cao hơn và cần bảo vệ khóa.
- RSA-3072/4096 tăng kích thước token và chi phí tính toán so với RSA-2048.
- Hiệu năng phụ thuộc provider, CPU acceleration, HSM và thư viện.

Nếu RS xác minh nhiều hơn AS ký, RSA có thể là lựa chọn vận hành hợp lý dù chi phí ký cao hơn.

### 4.3. Vì sao ECDSA và EdDSA thường có chữ ký nhỏ?

ECDSA và EdDSA dựa trên elliptic-curve cryptography. Chúng đạt mức bảo mật thực tế tương đương với khóa ngắn hơn RSA, nên chữ ký và public key thường nhỏ hơn. Điều này có thể giảm:

- Số byte truyền qua mạng.
- Kích thước header Authorization.
- Dung lượng log/trace nếu metadata token được lưu có kiểm soát.
- Chi phí xử lý tại gateway/proxy có giới hạn header.

Kích thước nhỏ không đồng nghĩa phép verify chắc chắn nhanh hơn. Cần đo cả thời gian CPU và tổng request latency.

### 4.4. HMAC-SHA-256 so với HS384/HS512

HMAC có cấu trúc hiệu quả; thay SHA-256 bằng SHA-384/SHA-512 không nhất thiết làm chi phí tăng theo tỷ lệ kích thước digest. Trên một số CPU, SHA-512 có thể đạt throughput tốt; trên nền tảng khác, SHA-256 có acceleration tốt hơn. HMAC-SHA-256 cũng tạo MAC ngắn hơn.

Chọn HS256/384/512 theo profile, yêu cầu an toàn và khả năng tương tác. Không tăng digest chỉ vì nghĩ số bit lớn hơn luôn đem lại lợi ích tổng thể.

### 4.5. So sánh ở cùng chính sách mức an toàn

Benchmark chỉ có ý nghĩa khi các lựa chọn đều đáp ứng chính sách mật mã của hệ thống. Không so một khóa RSA quá ngắn hoặc curve không còn được chấp nhận với một cấu hình hiện đại rồi kết luận thuật toán đó nhanh hơn.

Một số ràng buộc JOSE cần nhớ:

- HS256, HS384 và HS512 yêu cầu khóa HMAC tối thiểu lần lượt 256, 384 và 512 bit theo RFC 7518.
- RSA trong JWA yêu cầu modulus tối thiểu 2048 bit.
- ES256, ES384 và ES512 gắn với P-256, P-384 và P-521 tương ứng.
- EdDSA trong JOSE dùng khóa OKP tương ứng với Ed25519 hoặc Ed448.

Độ dài digest, kích thước khóa, kích thước chữ ký và mức an toàn mật mã là những đại lượng khác nhau. Hãy xác định trước thuật toán/parameter set được chính sách chấp nhận, sau đó benchmark các lựa chọn hợp lệ. Không giảm kích thước khóa hoặc chọn curve yếu hơn chỉ để tăng số verify mỗi giây.

## 5. Kích thước chữ ký ảnh hưởng đến token và mạng

### 5.1. Kích thước sau Base64url

Chữ ký trong JWT compact được Base64url-encode. Base64url làm tăng kích thước khoảng một phần ba so với byte gốc, trừ các chi tiết padding được lược bỏ.

| Chữ ký | Byte gốc | Ký tự Base64url gần đúng |
| --- | ---: | ---: |
| HS256 | 32 | 43 |
| HS384 | 48 | 64 |
| HS512 | 64 | 86 |
| ES256 | 64 | 86 |
| Ed25519 | 64 | 86 |
| ES384 | 96 | 128 |
| Ed448 | 114 | 152 |
| ES512 | 132 | 176 |
| RS256 với RSA-2048 | 256 | 342 |
| RS256 với RSA-3072 | 384 | 512 |
| RS256 với RSA-4096 | 512 | 683 |

Đây chỉ là độ dài phần chữ ký, chưa bao gồm protected header, payload và hai dấu chấm phân cách. Kích thước thực tế còn phụ thuộc claims và header.

### 5.2. Chi phí lặp lại trên mỗi request

Nếu mỗi request gửi token trong Authorization header, kích thước token được truyền lặp lại:

~~~text
extra_bytes_per_second =
    extra_token_bytes * authenticated_requests_per_second
~~~

Ví dụ, nếu một chữ ký RSA-2048 làm token lớn hơn khoảng 250 byte so với một chữ ký 64 byte, ở mức 10.000 request/giây, lượng dữ liệu tăng thêm có thể xấp xỉ 2,5 MB/giây trước overhead của HTTP/TLS. Đây là phép tính minh họa; chênh lệch token thực tế phụ thuộc header, payload và thuật toán so sánh.

Kích thước token lớn còn có thể:

- Tăng băng thông và chi phí truyền qua gateway.
- Tăng số packet hoặc ảnh hưởng compression/record framing.
- Chạm giới hạn header của reverse proxy, CDN hoặc API gateway.
- Tăng bộ nhớ tạm khi parse request.
- Làm request log dài hơn nếu hệ thống cấu hình sai và ghi token.

Không đánh giá thuật toán chỉ theo CPU nếu hệ thống bị giới hạn bởi mạng hoặc kích thước header.

## 6. Phân phối khóa và kiến trúc nhiều resource server

### 6.1. HMAC: verify nhanh nhưng chia sẻ quyền ký

Với HS256/384/512, mọi verifier cần cùng secret với issuer. Nếu có 30 resource server, secret phải được phân phối và bảo vệ ở nhiều nơi.

Hệ quả:

- Mỗi verifier bị xâm nhập có thể làm lộ khả năng ký token.
- Rotation cần cập nhật secret ở mọi nơi.
- Khó giới hạn phạm vi ảnh hưởng theo từng API.
- Việc cấp secret cho bên thứ ba có nghĩa cấp khả năng phát hành token.

Vì vậy, HMAC có thể phù hợp cho hệ thống nhỏ, miền tin cậy khép kín hoặc một số trường hợp service nội bộ, nhưng cần cân nhắc kỹ khi có nhiều verifier độc lập.

### 6.2. RSA, ECDSA và EdDSA: private key tập trung

Với chữ ký bất đối xứng:

- AS giữ private key để ký.
- RS giữ public key để xác minh.
- Public key có thể phân phối qua JWKS.
- Một RS bị xâm nhập không tự có quyền ký token mới nếu chỉ giữ public key.
- Có thể tách quyền phát hành và quyền xác minh.

Đổi lại, cần vận hành JWKS, cache, key ID, rotation, metadata và xử lý khi khóa mới chưa được phân phối.

### 6.3. Chi phí JWKS không phải chi phí verify chữ ký

Nếu mỗi request tải JWKS, độ trễ mạng sẽ lấn át chi phí mật mã. Thực tế nên:

- Cache JWKS theo issuer.
- Chọn public key bằng `kid` sau khi xác định issuer tin cậy.
- Chỉ refresh khi cache hết hạn hoặc gặp key ID chưa biết, có cooldown.
- Giới hạn timeout, kích thước response và tần suất refresh.
- Không lấy JWKS URI từ token header không tin cậy.
- Không bỏ qua verify khi JWKS endpoint tạm thời lỗi và không có khóa cache tin cậy.

Benchmark phải ghi rõ JWKS cache hit hay miss. Trộn cả hai vào một con số sẽ làm sai kết luận về hiệu năng thuật toán.

## 7. So sánh theo từng tiêu chí vận hành

| Tiêu chí | HMAC | RSA | ECDSA | EdDSA |
| --- | --- | --- | --- | --- |
| Loại khóa | Secret đối xứng | Private/public | Private/public | Private/public |
| Quyền ký ở verifier | Có | Không nếu chỉ giữ public key | Không nếu chỉ giữ public key | Không nếu chỉ giữ public key |
| Chi phí verify | Thường rất thấp | Thường hiệu quả với public exponent phổ biến | Phụ thuộc curve/provider | Thường hiệu quả trong phần mềm hiện đại |
| Kích thước chữ ký | 32/48/64 byte | Bằng modulus | 64/96/132 byte | 64 byte Ed25519; 114 byte Ed448 |
| Phân phối khóa | Phải phân phối secret | Phân phối public key | Phân phối public key | Phân phối public key |
| Hỗ trợ hệ sinh thái | Rất rộng | Rất rộng | Rộng nhưng cần kiểm tra curve/format | Tốt ở nền tảng hiện đại, cần kiểm tra hệ cũ |
| Vấn đề đặc thù | Secret compromise và shared signing authority | Token/signature lớn, private operation tốn hơn | Nonce an toàn, DER vs JOSE raw format | Hỗ trợ provider/HSM và curve |
| Phù hợp thường gặp | Miền tin cậy nhỏ, secret distribution kiểm soát được | Tương tác rộng, hệ thống cần độ tương thích cao | Muốn chữ ký nhỏ và có hỗ trợ P-curve tốt | Nền tảng hiện đại hỗ trợ Ed25519/Ed448 tốt |

## 8. Các yếu tố làm benchmark sai lệch

### 8.1. So sánh thư viện khác nhau

Nếu HMAC được đo bằng thư viện tối ưu còn ECDSA được đo qua một wrapper nhiều tầng, kết quả không phản ánh riêng thuật toán. Nên:

- Dùng cùng một thư viện JOSE nếu thư viện hỗ trợ các thuật toán cần so sánh.
- Nếu buộc dùng thư viện khác, ghi rõ phiên bản và cấu hình.
- Kiểm tra thư viện có dùng native crypto provider hay implementation thuần phần mềm.
- Không so sánh API sign ở một thư viện với API verify ở thư viện khác mà không kiểm soát khác biệt.

### 8.2. Đo cả parse và crypto

Benchmark chỉ đo verify trên signing input có sẵn sẽ bỏ qua parse Base64url, JSON và key selection. Benchmark end-to-end cần bao gồm các bước tương tự request thật. Đồng thời, nên có benchmark riêng cho crypto để phân tích nguyên nhân.

### 8.3. Không parse hoặc nạp khóa trong vòng lặp nếu production không làm vậy

Parse PEM, decode JWK, tạo RSA key object hoặc khởi tạo provider trên mỗi request làm tăng chi phí giả tạo. Trong production, khóa thường được parse một lần rồi tái sử dụng; JWKS được cache.

Ngược lại, không loại bỏ hoàn toàn chi phí key rotation/JWKS refresh nếu production có nhiều issuer và thường xuyên thay khóa. Hãy đo riêng cold-start và cache miss.

### 8.4. Token và payload phải đại diện cho dữ liệu thật

Payload 100 byte và payload 8 KB có chi phí parse, Base64url và truyền tải khác nhau. Benchmark cần dùng:

- Kích thước header gần thực tế.
- Số lượng claims tương đương.
- Kích thước payload trung bình và phân vị lớn.
- Số issuer/kid tương tự production.
- Token có đủ claims và profile validation thực tế.

### 8.5. Bỏ qua authorization và network có thể che nút thắt thật

Một API có thể tốn nhiều thời gian hơn ở database, policy service, TLS handshake, JSON serialization hoặc downstream call. Nếu verify chỉ chiếm 2% request latency, cải thiện verify 50% chỉ giảm tổng latency khoảng 1% theo định luật Amdahl.

Hãy đo cả riêng từng stage lẫn toàn request trước khi tối ưu.

## 9. Phương pháp benchmark phù hợp

### 9.1. Xây dựng ma trận thử nghiệm

Một ma trận cơ bản:

| Chiều đo | Giá trị nên thử |
| --- | --- |
| Thuật toán | HS256, RS256, PS256, ES256, ES384, EdDSA/Ed25519 nếu được hỗ trợ |
| Token size | Nhỏ, trung bình, lớn theo production |
| Key state | Warm key cache, cold start, JWKS refresh |
| Load | Thấp, tải dự kiến, peak và burst |
| Concurrency | Một worker, nhiều worker, giới hạn CPU |
| Runtime | Phiên bản production, provider và cấu hình production |
| Key source | Key object đã parse, JWKS cache, HSM/KMS nếu dùng |
| Kết quả | Valid token, invalid signature, wrong issuer/audience, expired |

Không dùng token sai chữ ký cho toàn bộ benchmark rồi suy ra chi phí xác minh token hợp lệ. Đường xử lý lỗi có thể kết thúc sớm hoặc có hành vi khác.

### 9.2. Warm-up và thời gian đo

Đối với runtime có JIT hoặc provider cần khởi tạo:

1. Khởi động tiến trình với cấu hình production.
2. Nạp khóa và JWKS cache.
3. Chạy warm-up đủ lâu để ổn định runtime.
4. Chạy workload trong khoảng thời gian cố định.
5. Lặp lại nhiều vòng và ghi nhận độ biến thiên.
6. Đo cold-start riêng, không trộn với warm steady-state.

Không dùng một mẫu vài chục lần gọi để kết luận throughput ở tải cao.

### 9.3. Chỉ số cần thu thập

| Chỉ số | Ý nghĩa |
| --- | --- |
| Verify latency p50 | Độ trễ điển hình |
| Verify latency p95/p99 | Đuôi độ trễ dưới tải |
| Throughput (verify/s) | Số lần xác minh hoàn tất mỗi giây |
| CPU time/request | Chi phí CPU trung bình cho một lần xác minh |
| CPU utilization | Mức sử dụng CPU khi tải ổn định |
| Allocation/GC hoặc memory pressure | Chi phí bộ nhớ và runtime |
| Token bytes | Kích thước token và header |
| JWKS cache hit ratio | Mức độ hiệu quả của key cache |
| Error rate | Tỷ lệ timeout, invalid token và lỗi dependency |
| Saturation | Điểm mà throughput không tăng nhưng latency tăng |

Phải phân biệt wall-clock latency và CPU time. Một request có thể chờ key provider hoặc scheduler mà không tiêu thụ CPU tương ứng.

### 9.4. Kiểm soát điều kiện

- Chạy trên cùng loại CPU, số core, memory và operating system.
- Ghi lại phiên bản thư viện, crypto provider và cấu hình acceleration.
- Giữ cùng payload/header và số lượng claims.
- Tắt debug logging hoặc ghi nhận rõ chi phí logging.
- Tránh benchmark đồng thời các thuật toán trên cùng CPU nếu chúng tranh chấp tài nguyên.
- Dùng tải phát sinh ổn định và đo cả khi có burst.
- Lặp lại nhiều lần và báo khoảng dao động.
- Kiểm tra kết quả bằng workload end-to-end.

## 10. Ví dụ tính tải và năng lực xác minh

Giả sử hệ thống có:

- 8.000 request được bảo vệ mỗi giây ở mức tải thông thường.
- 20.000 request/giây ở peak.
- Mỗi request cần xác minh một access token.
- Mục tiêu sử dụng CPU cho verify không vượt quá 20% tổng CPU capacity.

Nếu benchmark trên đúng phần cứng cho biết một core xử lý được V lần verify/giây trong điều kiện tải đại diện, số core lý thuyết tối thiểu cho verify ở peak là:

~~~text
required_cores = peak_verify_rate / (V * target_utilization)
~~~

Ví dụ giả định, nếu benchmark cho V = 5.000 verify/s/core:

~~~text
required_cores = 20.000 / (5.000 * 0.20)
               = 20 cores
~~~

Đây chỉ là phép tính năng lực cho phần verify, chưa bao gồm parse, HTTP, authorization, database, GC, hệ điều hành và headroom. Trong thực tế cần dự phòng burst, p99 latency, rolling deployment và node failure.

### 10.1. Không lấy một con số benchmark làm cam kết production

Throughput thực tế giảm khi:

- Payload lớn hơn.
- Nhiều issuer/kid làm cache kém hiệu quả.
- Có JWKS refresh hoặc HSM call.
- CPU bị tranh chấp bởi request nghiệp vụ.
- Token invalid tạo đường xử lý khác.
- TLS, network và authorization dependency tăng độ trễ.

Benchmark chỉ là dữ liệu để sizing và so sánh trong cùng điều kiện. Cần load test trên staging gần production và theo dõi sau triển khai.

## 11. Tối ưu đường xác minh mà không giảm bảo mật

### 11.1. Nạp và tái sử dụng khóa

- Parse public key/JWK một lần khi nạp JWKS.
- Cache key object theo issuer và kid.
- Dùng cấu trúc cache thread-safe phù hợp.
- Không parse lại PEM/JWK trên mỗi request.
- Có giới hạn bộ nhớ và quy tắc eviction không xóa khóa đang cần xác minh.
- Hỗ trợ rotation và invalidation rõ ràng.

### 11.2. Tránh network call trên mỗi request

JWKS, introspection và revocation lookup đều có thể tạo network latency. Cần lựa chọn mô hình theo yêu cầu thu hồi:

- JWT tự xác minh với public key cache có độ trễ thấp.
- Introspection khi cần trạng thái tập trung và chấp nhận network dependency.
- Denylist/event propagation cho các trường hợp thu hồi chọn lọc.
- Cache trạng thái có TTL được giới hạn theo threat model.

Không đánh đổi khả năng thu hồi tức thì mà nghiệp vụ yêu cầu chỉ để loại bỏ một network call.

### 11.3. Giữ validation đầy đủ

Không bỏ qua các kiểm tra issuer, audience, expiration, not-before, token type hoặc scope để tăng tốc. Hãy tối ưu implementation:

- Dùng allowlist thuật toán cố định.
- Chọn issuer từ cấu hình/tenant mapping tin cậy.
- Giới hạn kích thước token.
- Dùng thư viện JOSE đã được đánh giá.
- Tránh parse payload nhiều lần.
- Chỉ tạo principal với claims cần thiết.
- Tách crypto verification metrics khỏi authorization metrics.

### 11.4. Xử lý invalid token hiệu quả

Token sai định dạng hoặc chữ ký sai có thể bị gửi hàng loạt để tiêu thụ CPU. Cần:

- Giới hạn kích thước header/token.
- Giới hạn số request và áp dụng rate limit theo client/IP ở tầng phù hợp.
- Không thực hiện JWKS refresh vô hạn khi kid lạ.
- Có timeout và circuit breaker cho dependency.
- Trả lỗi tổng quát, không tiết lộ chi tiết khóa.
- Theo dõi tỷ lệ invalid signature và bất thường.

Rate limit không thay thế khóa mạnh, nhưng có thể giảm DoS trực tuyến và lạm dụng API.

## 12. Chọn thuật toán theo kiểu workload

### 12.1. Hệ thống nhỏ, một miền tin cậy

HMAC có thể hấp dẫn vì verify/sign nhanh và triển khai đơn giản. Tuy nhiên, mọi service giữ secret đều có quyền ký. Nếu có nhiều API độc lập hoặc ranh giới tổ chức, chi phí quản lý secret có thể lớn hơn lợi ích CPU.

### 12.2. Nhiều resource server, AS ký ít

RSA, ECDSA hoặc EdDSA thường phù hợp hơn về phân tách quyền: AS giữ private key, resource server chỉ giữ public key. Nếu ưu tiên tương thích rộng, RSA có thể dễ tích hợp. Nếu ưu tiên chữ ký nhỏ và nền tảng hỗ trợ tốt, ECDSA hoặc EdDSA đáng benchmark.

### 12.3. API có throughput rất cao

Ở tải cao, cần benchmark verify/s trên đúng CPU/provider và token size. HMAC thường có chi phí CPU thấp, RSA verify có thể rất hiệu quả, Ed25519 có thể cho hiệu năng phần mềm tốt. ECDSA phụ thuộc đường cong và implementation. Không chọn theo lý thuyết mà không đo.

### 12.4. Token đi qua gateway hoặc header có giới hạn

Chữ ký RSA dài có thể làm token vượt giới hạn header hoặc tăng băng thông. ECDSA P-256 và Ed25519 có chữ ký 64 byte, trong khi RSA-2048 là 256 byte. Nếu token size là nút thắt, đây là khác biệt đáng kể.

### 12.5. HSM hoặc KMS bắt buộc

Nếu private key nằm trong HSM/KMS, chi phí ký có thể bị chi phối bởi:

- Network round trip đến dịch vụ khóa.
- Queueing và giới hạn request/giây.
- Chính sách kiểm soát truy cập.
- Hỗ trợ thuật toán/curve của HSM.
- Kích thước batch và khả năng ký song song.

Hãy đo thời gian end-to-end của thao tác ký qua HSM, không chỉ benchmark thuật toán trong bộ nhớ. Với RS, ES và EdDSA, khả năng hỗ trợ của thiết bị có thể khác nhau đáng kể.

## 13. Ma trận quyết định thực tế

| Nhu cầu ưu tiên | Lựa chọn nên benchmark trước | Điều cần xác minh |
| --- | --- | --- |
| Verify CPU thấp, hệ thống nhỏ và secret distribution kiểm soát được | HS256 | Entropy, phạm vi chia sẻ secret, khả năng rotation |
| Tương thích rộng với nhiều hệ thống | RS256 | Kích thước token, RSA key size, chi phí verify/sign |
| Muốn chữ ký ngắn, hỗ trợ P-256 tốt | ES256 | JOSE raw signature format, nonce, provider |
| Nền tảng hiện đại, Ed25519 được hỗ trợ đầy đủ | EdDSA/Ed25519 | Tương thích JOSE, HSM/provider, interoperability |
| Policy yêu cầu RSA-PSS | PS256 | Hỗ trợ PSS đồng nhất giữa issuer và verifier |
| Hệ thống nhiều verifier không được phép ký | Chữ ký bất đối xứng | Private key chỉ ở issuer, public key phân phối an toàn |
| Token size/header là nút thắt | ES256 hoặc Ed25519 | Mức bảo mật, support, throughput và tổng latency |

Ma trận chỉ gợi ý điểm bắt đầu. Quyết định cuối cùng phải thỏa token profile, thuật toán được các bên hỗ trợ, mức bảo mật, yêu cầu compliance và kết quả đo trong workload thực tế.

## 14. Những sai lầm thường gặp khi tối ưu

1. **Chỉ benchmark signing:** bỏ qua việc RS xác minh token ở mỗi request.
2. **Chỉ đo hàm crypto:** không đo parse, key selection, claims validation và network.
3. **Dùng một token/payload quá nhỏ:** kết quả không đại diện production.
4. **Nạp khóa trong mỗi vòng lặp:** tạo overhead không có trong đường xử lý tối ưu.
5. **Bỏ cache JWKS trong benchmark:** trộn chi phí mạng với chi phí verify.
6. **Bỏ qua cold start và rotation:** bỏ sót spike latency khi deploy hoặc đổi khóa.
7. **So sánh thư viện không tương đương:** quy kết chênh lệch implementation thành chênh lệch thuật toán.
8. **Chỉ xem throughput trung bình:** bỏ qua p95/p99 và saturation.
9. **Chọn HMAC chỉ vì nhanh:** không tính chi phí chia sẻ secret và quyền ký tại mọi verifier.
10. **Chọn chữ ký nhỏ mà không kiểm tra provider:** thư viện/HSM có thể không hỗ trợ tốt thuật toán.
11. **Bỏ validation để giảm CPU:** làm thay đổi mô hình bảo mật.
12. **Cache authorization quá lâu:** token hoặc quyền đã bị thu hồi vẫn được chấp nhận.
13. **Không đo kích thước header:** token lớn có thể bị gateway từ chối dù crypto nhanh.
14. **Coi benchmark lab là cam kết capacity:** production còn có downstream, noisy neighbor và burst.

## 15. Checklist benchmark và vận hành

### Chuẩn bị

- [ ] Xác định tỷ lệ phát hành so với xác minh.
- [ ] Xác định request/s trung bình, peak và burst.
- [ ] Chọn thuật toán/profile hợp lệ mà các bên cùng hỗ trợ.
- [ ] Chuẩn bị token với payload/header gần production.
- [ ] Dùng đúng CPU, runtime, thư viện và crypto provider.
- [ ] Parse/nạp khóa theo mô hình production.

### Đo lường

- [ ] Đo sign và verify riêng.
- [ ] Đo crypto-only và end-to-end request.
- [ ] Đo p50, p95, p99 và throughput.
- [ ] Đo CPU time/request, CPU utilization và memory.
- [ ] Đo kích thước token/header và bytes truyền.
- [ ] Đo warm cache, cold start, JWKS refresh và key rotation.
- [ ] Đo valid token và invalid token.
- [ ] Đo tại tải dự kiến, peak, burst và khi dependency lỗi.

### Bảo mật và vận hành

- [ ] Không giảm validation để đạt benchmark tốt hơn.
- [ ] HMAC secret có entropy đủ mạnh và chỉ phân phối nơi cần.
- [ ] Với asymmetric, private key được bảo vệ và public key cache an toàn.
- [ ] Có rotation và xử lý key compromise.
- [ ] JWKS refresh có timeout, cooldown và giới hạn.
- [ ] Cache verified result không vượt exp hoặc chính sách thu hồi.
- [ ] Theo dõi invalid signature, dependency errors và latency tail.
- [ ] Load test staging trước khi quyết định capacity production.

## 16. Kết luận

HMAC thường có chi phí xác minh thấp và chữ ký gọn, nhưng mọi verifier giữ secret đều có khả năng ký token. RSA có độ tương thích rộng và verify có thể hiệu quả nhờ public exponent, đổi lại chữ ký lớn và private-key signing tốn kém hơn. ECDSA tạo chữ ký ngắn, nhưng cần triển khai đúng định dạng JOSE và nonce an toàn. EdDSA/Ed25519 thường có hiệu năng phần mềm tốt cùng chữ ký nhỏ, nhưng phải xác minh hỗ trợ của thư viện, provider và HSM.

Trong hệ thống có nhiều resource server, xác minh thường lặp lại nhiều hơn phát hành. Vì vậy cần đo verify trên workload thật, tính cả kích thước token, cache JWKS, key rotation, CPU, p99 latency và network. Không có thuật toán nhanh nhất cho mọi môi trường.

**Hãy chọn thuật toán đáp ứng profile và ranh giới tin cậy trước, sau đó benchmark đường xử lý thực tế để sizing và tối ưu.** Giữ nguyên các kiểm tra bảo mật trong mọi phép đo và không đánh đổi khả năng xác minh đúng để lấy throughput.

## Tài liệu chuẩn để đọc tiếp

- [RFC 7515 — JSON Web Signature (JWS)](https://www.rfc-editor.org/rfc/rfc7515): signing input và JWS compact.
- [RFC 7517 — JSON Web Key (JWK)](https://www.rfc-editor.org/rfc/rfc7517): biểu diễn và phân phối khóa.
- [RFC 7518 — JSON Web Algorithms (JWA)](https://www.rfc-editor.org/rfc/rfc7518): HS*, RS*, PS* và ES* trong JOSE.
- [RFC 8037 — CFRG Elliptic Curve Diffie-Hellman (ECDH) and Signatures in JOSE](https://www.rfc-editor.org/rfc/rfc8037): EdDSA và OKP key types trong JOSE.
- [RFC 8725 — JSON Web Token Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725): thuật toán, khóa và xác minh JWT an toàn.
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068): profile JWT access token.
- [NIST SP 800-57 Part 1](https://csrc.nist.gov/pubs/sp/800/57/pt1/r5/final): quản lý khóa và mức an toàn mật mã.
