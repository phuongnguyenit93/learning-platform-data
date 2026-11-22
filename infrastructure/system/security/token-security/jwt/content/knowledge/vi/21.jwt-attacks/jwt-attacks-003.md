# Khóa HMAC yếu và thử đoán khóa ngoại tuyến

## 1. Vì sao khóa HMAC yếu là rủi ro nghiêm trọng?

JSON Web Signature (JWS) có thể dùng HMAC để tạo và xác minh chữ ký JWT. Với các thuật toán như HS256, HS384 và HS512, issuer và verifier cùng sử dụng một bí mật đối xứng. Bí mật đó vừa cho phép tạo chữ ký, vừa cho phép xác minh chữ ký.

Nếu bí mật HMAC được chọn từ mật khẩu dễ đoán, chuỗi ngắn hoặc giá trị mặc định, kẻ tấn công có thể thử các khóa ứng viên **ngoại tuyến** sau khi lấy được một JWT có chữ ký. Họ không cần gửi hàng triệu yêu cầu đến API. Với mỗi khóa ứng viên, họ tính HMAC trên đúng phần dữ liệu được ký và so sánh kết quả với chữ ký trong token.

Khi một khóa ứng viên khớp, kẻ tấn công đã tìm được bí mật có thể dùng để tạo chữ ký hợp lệ. Nếu verifier tin khóa đó, attacker có thể tự tạo JWT với claims do họ lựa chọn, trong phạm vi các quy tắc xác minh còn cho phép.

Điểm cần nhớ:

- HMAC an toàn khi khóa có đủ entropy và được bảo vệ tốt.
- Độ dài chuỗi nhìn thấy được không đồng nghĩa với entropy.
- HS512 không cứu được một khóa mật khẩu yếu.
- JWT có chữ ký không mã hóa payload; người có token thường có thể đọc header và claims để kiểm tra khóa ứng viên.
- Rate limit của API không làm chậm phép đoán khóa ngoại tuyến.

Bài viết thuộc phạm vi **Security - JSON Web Token (JWT)** tổng quát, tập trung vào rủi ro khóa HMAC yếu, cách hiểu đúng về thử đoán ngoại tuyến và biện pháp phòng vệ, không phụ thuộc ngôn ngữ lập trình hay framework.

## 2. HMAC trong JWT hoạt động như thế nào?

### 2.1. JWS signing input

Với JWS Compact Serialization, dữ liệu được ký có dạng:

~~~text
BASE64URL(protected-header) + "." + BASE64URL(payload)
~~~

Chuỗi ghép này được gọi là signing input. Với HS256, chữ ký được tính bằng HMAC-SHA-256 trên signing input và khóa bí mật K:

~~~text
signature = HMAC-SHA-256(K, signing-input)
~~~

JWT compact sau đó chứa ba phần:

~~~text
BASE64URL(header).BASE64URL(payload).BASE64URL(signature)
~~~

Ví dụ header minh họa:

~~~json
{
  "alg": "HS256",
  "typ": "JWT"
}
~~~

Header cho biết thuật toán được khai báo là HS256. Verifier vẫn phải áp dụng allowlist thuật toán do hệ thống cấu hình; không được để token tự quyết định thuật toán được chấp nhận.

### 2.2. Cùng một bí mật dùng để ký và xác minh

HMAC là cơ chế xác thực thông điệp bằng khóa đối xứng:

- Issuer có K và dùng K để tạo MAC.
- Verifier có cùng K và dùng K để tính lại MAC.
- Nếu MAC tính lại khớp chữ ký nhận được, thông điệp được xác minh theo khóa K.

Hệ quả quan trọng: bất kỳ thành phần nào có K đều có khả năng tạo JWT có chữ ký hợp lệ, không chỉ xác minh JWT. Vì vậy, chia sẻ bí mật HMAC cho nhiều API verifier làm tăng số nơi có thể giả mạo token nếu một nơi bị xâm nhập.

### 2.3. Chữ ký không che giấu payload

Với JWS thông thường, header và payload được Base64url-encode chứ không được mã hóa. Người lấy được token có thể đọc claims như issuer, subject, audience, thời gian và các dữ liệu khác.

Việc payload có thể đọc được giúp attacker biết signing input cần kiểm tra. Họ không cần đoán nội dung bí mật của payload trước khi thử khóa; token đã cung cấp phần header và payload được ký.

Không đưa mật khẩu, API secret hoặc dữ liệu nhạy cảm không cần thiết vào JWT. Nếu cần bảo mật nội dung, phải đánh giá JWE hoặc một cơ chế bảo vệ dữ liệu phù hợp; mã hóa payload không thay thế việc dùng khóa ký mạnh.

## 3. Thử đoán khóa HMAC ngoại tuyến diễn ra thế nào?

### 3.1. Điều kiện để có thể kiểm tra khóa ứng viên

Một cuộc thử đoán khóa ngoại tuyến thường cần:

1. Một JWT/JWS có chữ ký HMAC hợp lệ được tạo bằng khóa mục tiêu.
2. Header và payload của token để dựng lại signing input.
3. Chữ ký nhận được để so sánh.
4. Một tập khóa ứng viên, chẳng hạn mật khẩu phổ biến, chuỗi mặc định, tên sản phẩm hoặc các biến thể có quy luật.

Attacker không cần quyền gọi token endpoint hoặc quyền truy cập API xác minh. Họ có thể kiểm tra từng ứng viên trên thiết bị của mình.

### 3.2. Ý tưởng kiểm tra ở mức khái niệm

Quy trình logic:

~~~text
signing_input = encoded_header + "." + encoded_payload
observed_signature = signature_from_token

for each candidate_key:
    candidate_signature = HMAC(candidate_key, signing_input)
    if constant_time_compare(candidate_signature, observed_signature):
        candidate_key matches the token
~~~

Đây là mô tả nguyên lý để hiểu và phòng vệ, không phải hướng dẫn khai thác một hệ thống cụ thể. Mỗi ứng viên chỉ cần một phép tính HMAC và phép so sánh cục bộ. Không có server-side rate limit hoặc khóa tài khoản nào tự động làm chậm vòng lặp này.

### 3.3. Vì sao chỉ cần một token?

Một token cung cấp signing input và MAC tương ứng. Attacker có thể kiểm tra xem một khóa ứng viên có tạo ra chữ ký đó hay không. Nhiều token có thể giúp xác nhận thêm một ứng viên, nhưng không cần gửi yêu cầu đến issuer để thực hiện phép kiểm tra cơ bản.

Nếu một khóa yếu được dùng để ký nhiều token, việc lấy được một token có thể đủ để kiểm tra danh sách ứng viên. Nếu khóa được khôi phục, attacker có thể tạo token mới thay vì chỉ sửa token cũ.

### 3.4. Vì sao đây là tấn công ngoại tuyến?

Trong tấn công trực tuyến, attacker gửi từng yêu cầu đến một dịch vụ và phụ thuộc vào phản hồi của dịch vụ. Dịch vụ có thể áp dụng rate limit, phát hiện bất thường hoặc khóa tài khoản.

Trong tấn công ngoại tuyến:

- Việc tính HMAC diễn ra cục bộ.
- API không nhận được từng lần thử.
- Không có phản hồi lỗi để giám sát.
- Có thể chạy song song trên nhiều lõi hoặc thiết bị.
- Tốc độ chủ yếu phụ thuộc phần cứng, thuật toán và chi phí mỗi phép thử.

Vì vậy, biện pháp trọng tâm là làm cho khóa không thể đoán thực tế, chứ không dựa vào rate limit của endpoint.

## 4. Mật khẩu không phải khóa HMAC phù hợp

### 4.1. Độ dài và entropy là hai khái niệm khác nhau

Một chuỗi có nhiều ký tự vẫn có thể có entropy thấp nếu được tạo theo quy luật hoặc lấy từ từ điển. Ví dụ:

| Kiểu giá trị | Đặc điểm | Rủi ro |
| --- | --- | --- |
| Tên sản phẩm hoặc tên công ty | Dễ đoán theo ngữ cảnh | Có thể nằm trong danh sách ứng viên |
| Mật khẩu phổ biến | Được chọn bởi nhiều người | Có sẵn trong từ điển |
| Cụm từ có quy luật | Dài nhưng dễ suy luận | Không gian tìm kiếm thực tế nhỏ |
| Chuỗi ngẫu nhiên do CSPRNG tạo | Không có cấu trúc dễ đoán | Có entropy gần với số bit ngẫu nhiên sinh ra |

Không đánh giá khóa chỉ bằng số ký tự. Hãy đánh giá cách tạo khóa và số bit entropy thực tế.

### 4.2. Vì sao dùng mật khẩu làm secret nguy hiểm?

Mật khẩu của con người thường được chọn để dễ nhớ. Người dùng có xu hướng dùng từ, tên, ngày tháng, mẫu bàn phím hoặc biến thể quen thuộc. Các lựa chọn đó tạo ra phân bố không đồng đều; attacker có thể thử ứng viên có xác suất cao trước.

Khóa HMAC cần là bí mật máy được tạo ngẫu nhiên với entropy đủ lớn. Một chuỗi dễ nhớ, kể cả có thêm tiền tố/hậu tố hoặc thay chữ bằng số, không tương đương khóa ngẫu nhiên.

### 4.3. Không thể sửa khóa yếu bằng cách tăng độ dài thuật toán

HS256, HS384 và HS512 dùng các kích thước đầu ra HMAC khác nhau, nhưng mức an toàn vẫn phụ thuộc khóa. Dùng HS512 với một mật khẩu yếu không biến mật khẩu đó thành bí mật 512-bit.

Đầu ra MAC dài không thể bù cho khóa có ít khả năng lựa chọn. Nếu attacker đoán đúng khóa, họ có thể tạo MAC hợp lệ theo thuật toán đã dùng.

## 5. Yêu cầu độ dài khóa theo HMAC JWA

RFC 7518 quy định yêu cầu kích thước khóa tối thiểu cho các thuật toán HMAC trong JSON Web Algorithms:

| Thuật toán | Hàm băm | Kích thước khóa tối thiểu theo JWA |
| --- | --- | --- |
| HS256 | SHA-256 | 256 bit |
| HS384 | SHA-384 | 384 bit |
| HS512 | SHA-512 | 512 bit |

Các kích thước này là yêu cầu tối thiểu cho khóa của thuật toán tương ứng. Khóa nên được sinh từ nguồn ngẫu nhiên mật mã với ít nhất lượng entropy tương ứng, thay vì lấy một mật khẩu rồi đệm thêm ký tự cho đủ độ dài.

Ví dụ, 32 byte ngẫu nhiên độc lập cung cấp 256 bit entropy trước khi mã hóa thành chuỗi biểu diễn. Nếu biểu diễn bằng Base64url, chuỗi kết quả dài hơn 32 ký tự nhưng không có thêm entropy; entropy vẫn đến từ 32 byte ban đầu.

### 5.1. Độ dài chuỗi không chứng minh độ mạnh

Không nên:

- Dùng một câu dễ nhớ làm khóa HS256 chỉ vì nó dài hơn 32 ký tự.
- Thêm nhiều số 0 hoặc ký tự cố định vào mật khẩu để đạt 256 bit.
- Dùng hash của mật khẩu làm khóa mà không giải quyết entropy gốc.
- Dùng chung một secret ngắn cho HS256, HS384 và HS512.
- Coi tên thuật toán là bằng chứng khóa được tạo đúng.

### 5.2. KDF có giải quyết được mật khẩu yếu không?

Password KDF như PBKDF2, scrypt hoặc Argon2 được thiết kế để làm chậm việc kiểm tra mật khẩu. Chúng có thể tăng chi phí cho mỗi lần đoán nếu hệ thống cần xử lý bí mật do người dùng cung cấp, nhưng không tạo ra entropy mới từ một mật khẩu yếu.

Không nên biến mật khẩu người dùng thành khóa HMAC JWT theo cách tự thiết kế. Hãy sinh khóa HMAC bằng CSPRNG theo yêu cầu thuật toán. Nếu có một yêu cầu đặc biệt buộc phải dẫn xuất khóa, cần một thiết kế mật mã được đánh giá riêng, KDF phù hợp và đầu ra đáp ứng đầy đủ yêu cầu khóa của JWA; KDF không thay thế nguồn bí mật đủ mạnh.

## 6. Ví dụ về khóa yếu và khóa được sinh đúng cách

### 6.1. Ví dụ giá trị không nên dùng

Các giá trị sau chỉ minh họa loại lựa chọn rủi ro, tuyệt đối không dùng làm secret:

~~~text
secret
password
company-name-2026
jwt-signing-key
welcome-to-our-service
<chuoi-mat-khau-tu-con-nguoi>
~~~

Chúng có thể xuất hiện trong từ điển, tài liệu cấu hình mẫu hoặc suy luận theo bối cảnh tổ chức.

### 6.2. Ví dụ quy trình tạo khóa phù hợp

Đối với HS256, quy trình khái niệm:

1. Dùng bộ sinh số ngẫu nhiên mật mã (CSPRNG) của nền tảng tin cậy.
2. Sinh ít nhất 32 byte ngẫu nhiên độc lập.
3. Lưu byte khóa trong secret manager hoặc kho bí mật phù hợp.
4. Chỉ cung cấp khóa cho issuer và các verifier thực sự cần xác minh HMAC.
5. Không ghi khóa vào source code, repository, image build hoặc log.
6. Luân chuyển khóa theo quy trình có phiên bản và thời gian chuyển tiếp rõ ràng.

Với HS384 và HS512, kích thước khóa tối thiểu lần lượt là 48 byte và 64 byte theo yêu cầu JWA.

Nếu dùng công cụ sinh khóa, phải bảo đảm công cụ dùng CSPRNG và xuất đúng số byte ngẫu nhiên, không phải sinh một chuỗi có vẻ ngẫu nhiên từ timestamp hoặc bộ sinh không mật mã.

## 7. Hậu quả khi attacker khôi phục được khóa

Khi attacker tìm được khóa HMAC, họ có thể tạo JWT mới có chữ ký hợp lệ đối với verifier đang tin khóa đó. Tùy hệ thống, hậu quả có thể gồm:

- Tự chọn subject hoặc client claims.
- Tự đặt audience vào một API dùng cùng secret.
- Tự khai scope, role hoặc quyền tùy chỉnh.
- Tự đặt thời điểm phát hành và hết hạn theo cách verifier chấp nhận.
- Giả mạo token cho nhiều dịch vụ nếu các dịch vụ dùng chung khóa.
- Duy trì truy cập bằng token giả mới ngay cả khi token cũ đã bị thu hồi riêng lẻ.

Hậu quả phụ thuộc chính sách xác minh phía resource server. Nếu API kiểm tra issuer, audience, thời gian, loại token và quyền bổ sung đúng cách, một số token giả có thể bị chặn. Tuy nhiên, khi attacker có đúng khóa ký, chữ ký không còn là bằng chứng đáng tin để phân biệt token do issuer hợp lệ tạo ra.

### 7.1. Claims thời gian không cứu được khóa đã bị đoán

Việc kiểm tra exp, nbf và iat vẫn cần thiết, nhưng không giải quyết được việc attacker có thể tạo chữ ký bằng khóa đã khôi phục. Attacker có thể đặt các claims thời gian trong giới hạn mà verifier cho phép.

Thời hạn ngắn giúp giảm cửa sổ sử dụng của token được phát hành hợp lệ, nhưng không khôi phục độ tin cậy của khóa. Khi khóa đã bị đoán hoặc lộ, cần thay khóa và ngừng chấp nhận chữ ký từ khóa bị ảnh hưởng.

### 7.2. Chia sẻ HMAC secret làm tăng phạm vi ảnh hưởng

Với HMAC, mỗi verifier phải biết bí mật để xác minh chữ ký. Vì vậy, mỗi verifier cũng có khả năng ký token. Nếu nhiều API, môi trường hoặc tổ chức dùng chung một secret:

- Một API bị xâm nhập có thể làm lộ khóa dùng ở các API khác.
- Môi trường thử nghiệm có thể trở thành đường lộ khóa production.
- Việc thu hồi một khóa ảnh hưởng nhiều dịch vụ.
- Khó xác định thành phần nào đã tạo ra token giả.

Giảm phạm vi chia sẻ bằng khóa riêng theo issuer, môi trường, nhóm dịch vụ hoặc purpose khi kiến trúc cho phép.

## 8. Phòng vệ ở lớp tạo và quản lý khóa

### 8.1. Sinh khóa bằng CSPRNG

- Sinh khóa bằng nguồn ngẫu nhiên mật mã của hệ điều hành hoặc HSM/secret manager tin cậy.
- Đáp ứng kích thước tối thiểu của thuật toán JWA.
- Không dùng mật khẩu, từ điển, tên tổ chức, timestamp hoặc chuỗi mặc định.
- Không tái sử dụng khóa giữa production, staging, development và test.
- Không dùng một khóa cho nhiều mục đích mật mã không liên quan.

### 8.2. Lưu trữ và phân phối bí mật

- Lưu secret trong secret manager hoặc hệ thống quản lý khóa có kiểm soát truy cập.
- Giới hạn quyền đọc theo nguyên tắc least privilege.
- Mã hóa dữ liệu lưu trữ và bảo vệ kênh phân phối khóa.
- Không hardcode secret trong source, cấu hình mẫu, container image hoặc pipeline log.
- Không đưa secret vào ticket, chat, tài liệu hướng dẫn hoặc biến môi trường bị ghi lại không kiểm soát.
- Ghi audit về việc đọc, tạo, xoay vòng và thu hồi khóa.

### 8.3. Tách khóa theo môi trường và phạm vi

Mỗi môi trường nên có khóa độc lập. Không dùng chung khóa HMAC giữa:

- Development và production.
- Staging và production.
- Các tenant không cùng miền tin cậy.
- Các issuer độc lập.
- Các API có ranh giới bảo mật khác nhau nếu không có lý do rõ ràng.

Phân tách khóa giúp một sự cố có phạm vi ảnh hưởng nhỏ hơn và cho phép thu hồi có chọn lọc.

## 9. Phòng vệ ở lớp xác minh JWT

Khóa mạnh là yêu cầu nền tảng, nhưng verifier vẫn cần xác minh token theo ngữ cảnh:

1. Cấu hình allowlist thuật toán; nếu endpoint chỉ hỗ trợ HS256 thì chỉ chấp nhận HS256.
2. Không chọn thuật toán theo cách tin mù quáng giá trị alg trong token.
3. Kiểm tra chữ ký bằng đúng khóa được liên kết với issuer và thuật toán.
4. Kiểm tra iss và aud theo giá trị được cấu hình.
5. Kiểm tra exp, nbf, iat và giới hạn tuổi token.
6. Kiểm tra typ hoặc loại token theo profile nếu hệ thống sử dụng.
7. Kiểm tra scope, quyền và các claims bắt buộc.
8. Không dùng chung validator lỏng lẻo cho ID token, access token và assertion.

Các kiểm tra này hạn chế việc dùng token sai ngữ cảnh. Chúng không thay thế khóa mạnh: nếu attacker đã có secret HMAC, họ có thể tạo chữ ký hợp lệ và cố đáp ứng các claims mà verifier yêu cầu.

## 10. Khi nào nên cân nhắc chữ ký bất đối xứng?

Với HMAC, mọi bên xác minh đều phải giữ cùng một secret có khả năng ký. Nếu có nhiều resource server hoặc nhiều tổ chức cần xác minh token nhưng không được phép phát hành token, chữ ký bất đối xứng có thể phù hợp hơn:

| Tiêu chí | HMAC (HS*) | Chữ ký bất đối xứng (RS*, ES*, PS* tùy profile) |
| --- | --- | --- |
| Khóa ký | Bí mật dùng chung | Private key của issuer |
| Khóa xác minh | Cùng secret với khóa ký | Public key tương ứng |
| Verifier có thể tự ký token? | Có, vì giữ secret | Không, nếu chỉ giữ public key |
| Phân phối khóa | Phải bảo vệ secret tại mọi verifier | Có thể phân phối public key qua JWKS |
| Phạm vi ảnh hưởng khi verifier bị lộ | Có thể lộ khả năng ký | Public key bị lộ không cho phép ký |
| Vận hành | Quản lý secret dùng chung | Bảo vệ private key và phân phối/luân chuyển public key |

Chữ ký bất đối xứng không tự động an toàn nếu private key yếu, bị lộ hoặc verifier cấu hình sai. Tuy nhiên, nó giảm nhu cầu chia sẻ bí mật có quyền ký đến mọi resource server.

## 11. Xử lý khi nghi ngờ khóa HMAC yếu hoặc bị đoán

Nếu phát hiện secret là mật khẩu, chuỗi mặc định, có entropy không rõ hoặc có khả năng đã bị lộ, hãy coi độ tin cậy của chữ ký từ khóa đó là bị ảnh hưởng.

Các bước xử lý:

1. **Xác định phạm vi:** issuer, thuật toán, môi trường, API và token nào sử dụng secret.
2. **Tạo khóa mới:** sinh khóa ngẫu nhiên bằng CSPRNG, đáp ứng kích thước tối thiểu theo JWA.
3. **Chuyển issuer sang khóa mới:** bắt đầu ký token mới bằng secret mới.
4. **Ngừng tin khóa cũ:** nếu nghi ngờ khóa đã bị khôi phục, không giữ khóa cũ chỉ để chờ token hết hạn nếu điều đó cho phép attacker tiếp tục giả mạo.
5. **Vô hiệu hóa credential liên quan:** thu hồi phiên, refresh token hoặc token state theo khả năng của hệ thống.
6. **Yêu cầu xác thực/cấp token lại:** khi cần, buộc client nhận credential mới.
7. **Kiểm tra log và sự kiện:** tìm token bất thường, thay đổi quyền, truy cập từ nguồn lạ và dấu hiệu secret bị truy cập.
8. **Rà soát nơi lưu khóa:** secret manager, CI/CD, repository, backup, image và log.
9. **Xác minh tất cả verifier:** bảo đảm mọi API đã ngừng chấp nhận khóa cũ.

Nếu dùng khóa HMAC cũ và mới song song trong giai đoạn chuyển tiếp bình thường, chỉ làm vậy khi khóa cũ vẫn đáng tin. Khi khóa cũ bị nghi ngờ đã bị đoán, khoảng chấp nhận song song cũng là khoảng attacker có thể tiếp tục ký token giả.

### 11.1. Vai trò của kid trong luân chuyển

Header kid có thể giúp verifier chọn phiên bản khóa. kid không phải secret và không chứng minh khóa mạnh. Verifier phải ánh xạ kid tới khóa đã được cấu hình tin cậy; không được dùng kid để tải hoặc tin một khóa tùy ý.

Với HMAC, việc phân phối secret mới đến verifier cần được bảo vệ. Không công bố HMAC secret trong JWKS công khai; JWKS có thể chứa khóa đối xứng trong một số ngữ cảnh nội bộ được bảo vệ, nhưng không được phát tán bí mật cho bên không có quyền ký.

## 12. Những ngộ nhận thường gặp

| Ngộ nhận | Thực tế |
| --- | --- |
| Secret càng dài thì càng mạnh | Độ mạnh phụ thuộc entropy và cách sinh, không chỉ số ký tự |
| HS512 luôn an toàn hơn HS256 | Khóa yếu vẫn yếu dù dùng hàm băm đầu ra dài hơn |
| JWT có chữ ký thì payload được mã hóa | JWS thông thường chỉ ký; payload có thể đọc được |
| Rate limit API ngăn brute-force HMAC | Thử khóa có thể diễn ra ngoại tuyến, không gọi API |
| Hash mật khẩu một lần là có khóa mạnh | Hash không tạo thêm entropy từ mật khẩu yếu |
| Thêm ký tự cố định làm secret đủ 256 bit | Padding không tăng entropy thực tế |
| jti hoặc exp ngăn attacker ký token giả | Attacker có khóa có thể tạo jti và exp mới |
| Chỉ issuer cần giữ secret HMAC | Mọi verifier HMAC cũng cần secret và có khả năng ký |
| Đổi kid là đủ để thu hồi khóa cũ | Verifier phải ngừng tin khóa cũ; kid chỉ là định danh |
| Có thể giữ khóa bị lộ đến khi token cũ hết hạn | Attacker có thể tiếp tục tạo token mới trong thời gian đó |

## 13. Checklist đánh giá khóa HMAC

### Tạo khóa

- [ ] Khóa được sinh bằng CSPRNG hoặc HSM phù hợp.
- [ ] HS256 dùng khóa tối thiểu 256 bit; HS384 tối thiểu 384 bit; HS512 tối thiểu 512 bit.
- [ ] Khóa có entropy tương ứng với kích thước yêu cầu, không chỉ đủ số ký tự.
- [ ] Không dùng mật khẩu người dùng, chuỗi mặc định hoặc dữ liệu có thể suy luận.
- [ ] Không dùng chung secret giữa môi trường hoặc miền tin cậy không liên quan.

### Lưu trữ và phân phối

- [ ] Secret nằm trong hệ thống quản lý bí mật có kiểm soát.
- [ ] Quyền đọc secret giới hạn theo least privilege.
- [ ] Không hardcode hoặc commit secret vào repository.
- [ ] Secret không xuất hiện trong log, ticket, chat hoặc image build.
- [ ] Có audit cho việc truy cập và thay đổi khóa.
- [ ] Có quy trình backup/khôi phục và rotation.

### Xác minh và ứng phó

- [ ] Verifier dùng allowlist thuật toán.
- [ ] Kiểm tra issuer, audience, thời gian và loại token.
- [ ] Secret HMAC chỉ được phân phối đến các thành phần thực sự cần.
- [ ] Có kế hoạch thu hồi khóa và xác minh mọi verifier đã ngừng tin khóa cũ.
- [ ] Có quy trình xử lý token/session/refresh credential khi khóa bị lộ.
- [ ] Đánh giá khả năng chuyển sang chữ ký bất đối xứng nếu có nhiều verifier.

## 14. Kết luận

Khóa HMAC yếu tạo điều kiện cho thử đoán ngoại tuyến: khi attacker có một JWT đã ký, họ có thể tự tính HMAC cho từng khóa ứng viên và so sánh với chữ ký mà không cần gọi API. Nếu đoán đúng secret, họ có thể tạo JWT mới có chữ ký hợp lệ đối với các verifier vẫn tin khóa đó.

Biện pháp phòng vệ cốt lõi là sinh khóa bằng CSPRNG với entropy và kích thước tối thiểu theo JWA, không dùng mật khẩu làm secret, bảo vệ và phân tách khóa, giới hạn thuật toán và có quy trình luân chuyển/thu hồi. Nếu nhiều resource server chỉ cần xác minh mà không cần quyền phát hành, chữ ký bất đối xứng có thể giảm phạm vi chia sẻ bí mật.

**Chữ ký HMAC chỉ đáng tin khi khóa thực sự bí mật và đủ mạnh.** Thời hạn token, rate limit hoặc việc tăng HS256 lên HS512 không thể bù cho một khóa dễ đoán.

## Tài liệu chuẩn để đọc tiếp

- [RFC 7515 — JSON Web Signature (JWS)](https://www.rfc-editor.org/rfc/rfc7515): signing input và cấu trúc JWS.
- [RFC 7518 — JSON Web Algorithms (JWA), Section 3.2](https://www.rfc-editor.org/rfc/rfc7518#section-3.2): yêu cầu kích thước khóa cho HMAC SHA-2.
- [RFC 7519 — JSON Web Token (JWT)](https://www.rfc-editor.org/rfc/rfc7519): cấu trúc JWT và registered claims.
- [RFC 8725 — JSON Web Token Best Current Practices, Section 3.5](https://www.rfc-editor.org/rfc/rfc8725#section-3.5): yêu cầu khóa đủ mạnh.
- [RFC 2104 — HMAC: Keyed-Hashing for Message Authentication](https://www.rfc-editor.org/rfc/rfc2104): nguyên lý HMAC.
- [NIST SP 800-57 Part 1](https://csrc.nist.gov/pubs/sp/800/57/pt1/r5/final): hướng dẫn quản lý khóa mật mã.
