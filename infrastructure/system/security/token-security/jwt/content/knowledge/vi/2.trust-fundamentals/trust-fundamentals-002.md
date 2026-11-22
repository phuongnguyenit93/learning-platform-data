# Chữ ký số, mã xác thực thông điệp và mã hóa bảo vệ những gì?

Trong **Security – JSON Web Token (JWT)**, việc một token được **ký**, được **kiểm tra MAC** hoặc được **mã hóa** quyết định những loại rủi ro mà token có thể chống lại. Ba cơ chế này thường được nhắc cùng nhau nhưng không thể thay thế nhau: chữ ký số và mã xác thực thông điệp chủ yếu chứng minh **tính toàn vẹn và nguồn gốc theo một quan hệ tin cậy**, còn mã hóa chủ yếu bảo vệ **tính bí mật**. Một số cách mã hóa hiện đại đồng thời bảo vệ tính toàn vẹn, nhưng bản thân việc giải mã thành công không luôn chứng minh ai là người gửi.

Bài học thuộc chương **Nền tảng tin cậy**, trình bày các khái niệm bảo mật áp dụng cho JWT, API và hệ thống phân tán nói chung, không phụ thuộc ngôn ngữ lập trình hay framework.

## 1. Trước hết, xác định thuộc tính cần bảo vệ

| Thuộc tính | Câu hỏi đặt ra | Rủi ro điển hình |
| --- | --- | --- |
| **Toàn vẹn dữ liệu (integrity)** | Dữ liệu có bị sửa đổi trái phép so với nội dung được bảo vệ không? | Kẻ tấn công đổi claim quyền từ đọc thành ghi |
| **Xác thực nguồn gốc (origin authentication)** | Dữ liệu có được tạo/phát hành bởi một bên nắm khóa tin cậy không? | Kẻ lạ tự tạo token rồi tự xưng là hệ thống định danh |
| **Bí mật (confidentiality)** | Bên không có quyền có đọc được nội dung hay không? | Người có token nhìn thấy email, thông tin cá nhân hoặc dữ liệu nghiệp vụ trong payload |
| **Chống phát lại (replay resistance)** | Thông điệp từng hợp lệ có bị dùng lại trái phép không? | Kẻ trộm dùng lại bearer token chưa hết hạn |
| **Phân quyền (authorization)** | Chủ thể được phép làm gì trên tài nguyên cụ thể? | Token hợp lệ của Alice được dùng để xem hóa đơn của Bob |

Chữ ký, MAC và mã hóa chỉ giải quyết những thuộc tính nhất định trong bảng. Chúng **không tự động** quyết định quyền truy cập, thời hạn hiệu lực, đối tượng nhận token, hay việc người gửi hiện tại có thật sự là chủ thể trong token.

### Bảng đối chiếu nhanh

| Cơ chế | Toàn vẹn | Xác thực nguồn gốc | Bí mật | Ai xác minh hoặc đọc được? |
| --- | --- | --- | --- | --- |
| **Chữ ký số** | Có, nếu kiểm chứng thành công | Có, với điều kiện khóa công khai được gắn đúng bên ký đáng tin | **Không** | Bất kỳ ai có khóa công khai phù hợp có thể kiểm chứng |
| **MAC**, ví dụ HMAC | Có, nếu đối chiếu MAC thành công | Có, trong **nhóm bên giữ cùng khóa bí mật**; không phân biệt được thành viên nào đã tạo MAC | **Không** | Chỉ bên biết khóa bí mật dùng chung mới kiểm tra được |
| **Mã hóa không xác thực** | Không được bảo đảm | Không được bảo đảm | Có, nếu thuật toán, khóa và cách sử dụng an toàn | Bên giữ khóa giải mã phù hợp có thể đọc |
| **Mã hóa có xác thực (AEAD)** | Có, cho ciphertext và associated data được xác thực | Chứng minh bên tạo được thông điệp hợp lệ biết/kiểm soát khóa thích hợp; **không luôn xác định danh tính người gửi** | Có | Bên có khóa giải mã hợp lệ có thể đọc và kiểm tra |

Lưu ý: “có” trong bảng giả định thuật toán an toàn, khóa không bị lộ và việc xác minh được thực hiện đúng. Không phải mọi phép biến đổi tên là “mã hóa” đều tạo ra sự bảo vệ tương đương.

## 2. Chữ ký số: bảo vệ tính toàn vẹn và nguồn phát hành có thể kiểm chứng

### 2.1. Cách hoạt động

Chữ ký số thường dựa trên **mật mã bất đối xứng**:

1. Bên phát hành có **khóa riêng (private key)** và tạo chữ ký trên thông điệp theo thuật toán được chọn.
2. Bên nhận dùng **khóa công khai (public key)** tương ứng để xác minh chữ ký.
3. Nếu xác minh thành công, bên nhận có cơ sở cho rằng thông điệp không bị chỉnh sửa sau khi được ký bởi bên nắm khóa riêng phù hợp.
4. Để kết luận thông điệp đến từ **bên phát hành A**, bên nhận còn phải xác định khóa công khai đó thực sự thuộc về A hoặc được A ủy quyền.

~~~mermaid
flowchart LR
    A["Bên phát hành"] --> B["Thông điệp + khóa riêng"]
    B --> C["Tạo chữ ký"]
    C --> D["Thông điệp + chữ ký"]
    D --> E["Bên nhận: khóa công khai tin cậy"]
    E --> F{"Xác minh chữ ký"}
    F -- "Hợp lệ" --> G["Tiếp tục kiểm tra ngữ cảnh và chính sách"]
    F -- "Không hợp lệ" --> H["Từ chối"]
~~~

Nếu kẻ tấn công thay đổi một phần thông điệp thuộc phạm vi đã ký mà không có khả năng tạo chữ ký hợp lệ mới, kết quả kiểm chứng phải thất bại. Việc chỉ giải mã hoặc đọc thông điệp không phải là xác minh chữ ký.

**Chữ ký số bảo vệ:**

- Tính toàn vẹn của các byte/thành phần nằm trong phạm vi được ký.
- Tính xác thực của bên ký **khi** khóa xác minh được ràng buộc với bên phát hành tin cậy và khóa riêng được bảo vệ.
- Khả năng bên thứ ba kiểm chứng mà **không cần giữ khóa riêng**; hữu ích khi nhiều API cần xác minh token từ một bên phát hành.

**Chữ ký số không tự bảo vệ:**

- Tính bí mật: nội dung được ký vẫn có thể đọc được.
- Khả năng chống dùng lại thông điệp đã ký: một chữ ký đúng vẫn đúng khi bị phát lại.
- Tính đúng đắn về nghiệp vụ: một token ký hợp lệ vẫn có thể chứa dữ liệu cũ, sai mục đích hoặc quyền đã bị thu hồi.
- Việc người đang trình token chính là chủ thể ghi trong token: bearer token bị đánh cắp vẫn mang chữ ký hợp lệ.

Chữ ký có thể đóng góp vào khả năng **quy trách nhiệm/không thể chối bỏ (non-repudiation)** trong một hệ thống có quản lý danh tính, khóa, bằng chứng và quy trình phù hợp. **Không được xem một chữ ký hợp lệ là bằng chứng pháp lý tuyệt đối** về hành vi của một cá nhân: khóa riêng có thể bị lộ, bị sử dụng trái phép hoặc không gắn chắc với danh tính mong đợi.

### 2.2. Ví dụ về token ký bất đối xứng

Một nhà phát hành sử dụng **RS256** để ký JWT. Các API biết khóa công khai đáng tin của nhà phát hành và dùng khóa đó để xác minh. API có thể xác minh token mà không có quyền tạo thêm token với chữ ký của nhà phát hành. Điều này hỗ trợ phân tách quyền giữa **bên phát hành** và **bên chỉ được kiểm chứng**.

Nhưng nếu API lấy khóa công khai từ một URL tùy ý do token chưa được tin cậy đề xuất, kẻ tấn công có thể hướng API tới khóa công khai của chính mình. Thuật toán chữ ký đúng vẫn không cứu được **chuỗi tin cậy khóa sai**.

## 3. MAC: toàn vẹn và xác thực bên giữ khóa bí mật dùng chung

**Message Authentication Code (MAC)** là một giá trị xác thực được tính từ thông điệp và một **khóa bí mật**. Ví dụ phổ biến là **HMAC**, sử dụng hàm băm kết hợp với khóa theo cấu trúc được xác định rõ.

**HMAC khác với một hàm băm thuần túy.** Khi gửi dữ liệu kèm giá trị băm thông thường, kẻ tấn công có thể sửa dữ liệu rồi tính lại hash. Nếu không có nguồn hash đáng tin độc lập, bên nhận không thể biết dữ liệu đã bị giả mạo. HMAC thêm yếu tố **khóa bí mật** vào quá trình xác thực; người không biết khóa không thể tự tạo MAC hợp lệ trên nội dung đã sửa, với giả định thuật toán an toàn.

~~~text
tag = MAC(khoa_bi_mat, thong_diep)
xac_minh = so_sanh(tag_nhan_duoc, MAC(khoa_bi_mat, thong_diep_nhan_duoc))
~~~

Trong thực tế nên dùng thư viện mật mã tin cậy cùng cơ chế so sánh an toàn về thời gian, thay vì tự ghép chuỗi hoặc tự thiết kế thuật toán MAC.

### 3.1. MAC giải quyết điều gì?

Nếu chỉ Alice và dịch vụ X biết khóa MAC K, và K được giữ kín, việc kiểm tra MAC thành công có thể cho dịch vụ X tin rằng thông điệp không bị thay đổi ngoài nhóm bên được cấp K. Tuy nhiên, **dịch vụ X cũng có K**, nên chính dịch vụ X cũng có thể tự tạo MAC trên bất kỳ thông điệp nào. Vì vậy MAC thường **không cung cấp bằng chứng cho bên thứ ba** rằng chính Alice đã tạo thông điệp.

| Tiêu chí | Chữ ký số | MAC |
| --- | --- | --- |
| Tạo giá trị bảo vệ | Khóa riêng | Khóa bí mật dùng chung |
| Kiểm chứng | Khóa công khai | Cùng khóa bí mật dùng chung |
| Bên chỉ kiểm chứng có thể tạo giá trị hợp lệ mới? | Không, nếu không có khóa riêng | **Có**, vì bên kiểm chứng cũng biết khóa MAC |
| Nhiều bên kiểm chứng | Có thể phân phối khóa công khai | Phải chia sẻ bí mật cho các bên kiểm chứng |
| Chứng minh nguồn cho bên thứ ba độc lập | Có thể hỗ trợ khi có hạ tầng tin cậy phù hợp | Không phân biệt được ai trong nhóm có cùng bí mật đã tạo MAC |
| Có che giấu nội dung? | Không | Không |

### 3.2. HMAC trong JWT

Một JWT ở dạng JWS có thể sử dụng thuật toán **HS256** để tạo và kiểm tra MAC. Khi đó bên phát hành token và bên xác minh token đều phải sở hữu **khóa bí mật tương ứng**.

Ví dụ: nếu ba API cùng có khóa HS256 để xác minh access token, về khả năng mật mã **cả ba API đều có thể tạo token có MAC hợp lệ** bằng khóa đó. Việc này có thể không phù hợp nếu thiết kế yêu cầu các API chỉ được xác minh mà tuyệt đối không được phát hành token.

MAC phù hợp khi các bên cần có quan hệ tin cậy chung, quản lý được phạm vi chia sẻ khóa và rủi ro một bên bị xâm nhập. Khóa HMAC cần đủ ngẫu nhiên và đủ mạnh theo thuật toán; không lấy mật khẩu dễ đoán làm khóa trực tiếp.

## 4. Mã hóa: bảo vệ người không có khóa khỏi đọc nội dung

**Encryption** biến bản rõ (*plaintext*) thành bản mã (*ciphertext*) để người không có khóa giải mã thích hợp khó khôi phục nội dung. Mục tiêu cốt lõi là **tính bí mật**.

### 4.1. Mã hóa đối xứng và bất đối xứng

| Loại | Cách hoạt động ở mức khái niệm | Ứng dụng điển hình |
| --- | --- | --- |
| **Mã hóa đối xứng** | Bên mã hóa và giải mã dùng cùng khóa bí mật hoặc các khóa liên quan theo giao thức | Bảo vệ lượng dữ liệu lớn; phần nội dung bên trong JWE |
| **Mã hóa khóa công khai** | Có thể mã hóa cho bên sở hữu khóa riêng tương ứng với khóa công khai nhận | Trao đổi/bọc khóa nội dung hoặc truyền thông điệp tới người nhận cụ thể |
| **Mã hóa lai (hybrid)** | Dùng cơ chế khóa công khai/thỏa thuận khóa để thiết lập khóa nội dung, rồi dùng mật mã đối xứng để bảo vệ payload | Cách tổ chức phổ biến của nhiều cấu hình JWE |

Việc nội dung đã được mã hóa **không đủ** để khẳng định không thể bị sửa. Một số kiểu mã hóa không xác thực có thể bị tác động lên ciphertext, khiến plaintext sau giải mã bị thay đổi hoặc gây lỗi có thể khai thác.

### 4.2. Mã hóa có xác thực (AEAD)

**Authenticated Encryption with Associated Data (AEAD)**, ví dụ **AES-GCM** hoặc **ChaCha20-Poly1305** khi triển khai theo giao thức phù hợp, cung cấp đồng thời:

- **Bí mật** của plaintext được mã hóa.
- **Toàn vẹn/xác thực mật mã** đối với ciphertext và phần dữ liệu liên kết (*associated data*, AAD) được bảo vệ.
- Tín hiệu kiểm tra thất bại nếu bản mã, tag hoặc AAD được bảo vệ không khớp.

AAD thường **được xác thực nhưng không được mã hóa**. Nghĩa là người quan sát vẫn có thể đọc AAD, nhưng không thể tự ý thay đổi nó và tạo tag hợp lệ nếu không có khả năng mật mã cần thiết.

AEAD **không tự cho biết cá nhân hoặc tổ chức nào là người gửi**. Chẳng hạn nếu bất kỳ ai đều có thể tạo thông điệp được mã hóa tới người nhận bằng khóa công khai của người đó, người nhận giải mã thành công không vì thế mà xác nhận được thông điệp xuất phát từ một bên phát hành cụ thể. Phải xét cơ chế quản lý khóa và có thể cần thêm chữ ký.

Khi dùng AEAD, cần tôn trọng điều kiện của thuật toán về **nonce/IV**, khóa và tag. Ví dụ, tái sử dụng nonce với cùng khóa trong AES-GCM có thể phá vỡ bảo đảm bảo mật rất nghiêm trọng. Không tự thiết kế quy trình ghép mã hóa và MAC hoặc tự xây định dạng mật mã.

### 4.3. Mã hóa nội dung không giống bảo vệ kết nối

TLS bảo vệ dữ liệu **trong từng kết nối** với các bên đầu cuối của kết nối đó. Khi thông điệp đi qua gateway, proxy, hàng đợi hoặc được lưu để xử lý về sau, nội dung có thể đã được giải mã tại một điểm trung gian được tin cậy. Mã hóa trực tiếp payload/token theo phạm vi người nhận có thể giúp duy trì bí mật qua các bước trung gian, tùy thiết kế.

Ngược lại, mã hóa nội dung không thay thế TLS: metadata kết nối, việc xác thực endpoint và khả năng chống tấn công trên đường truyền vẫn cần được xử lý riêng.

## 5. Trong JWT, JWS và JWE tương ứng cơ chế nào?

JWT là **định dạng mang các claims**. Cách bảo vệ claims phụ thuộc vào việc JWT được biểu diễn bằng **JWS** (chữ ký hoặc MAC) hay **JWE** (mã hóa). Cả hai cùng thuộc họ chuẩn JOSE, nhưng giải quyết những mục tiêu khác nhau.

### 5.1. JWS: ký hoặc MAC, không giữ bí mật payload

JWS Compact Serialization thường có **ba phần**, ngăn bởi dấu chấm:

~~~text
BASE64URL(protected_header).BASE64URL(payload).BASE64URL(signature_or_mac)
~~~

Ví dụ về header và claims **ở dạng đã giải mã để minh họa**, không phải một JWT hợp lệ có chữ ký thực:

~~~json
{
  "alg": "RS256",
  "typ": "JWT"
}
~~~

~~~json
{
  "iss": "https://identity.example.org",
  "sub": "user-42",
  "aud": "https://payments-api.example.org",
  "exp": 2000000000,
  "scope": "payment:read"
}
~~~

Trong JWS Compact, phần protected header và payload tham gia vào dữ liệu được ký/MAC theo quy tắc của JWS. Kẻ tấn công sửa `scope` thành `payment:write` mà không tạo được chữ ký/MAC hợp lệ sẽ khiến việc xác minh thất bại.

**Điều không được hiểu sai:** Base64url là cách biểu diễn nhị phân thành chuỗi ký tự. Bất kỳ ai có JWS thông thường đều có thể giải mã Base64url để **đọc payload**, cho dù không thể giả mạo chữ ký. Ký không đồng nghĩa với mã hóa.

- **RS256**, **ES256** hoặc các thuật toán chữ ký phù hợp là ví dụ về JWS dùng khóa ký riêng và khóa kiểm chứng công khai.
- **HS256** là ví dụ về JWS dùng HMAC với khóa bí mật chung.
- Header `alg` mô tả thuật toán dùng với JWS nhưng là **dữ liệu đầu vào chưa đáng tin** trước khi chính sách xác minh và nguồn khóa được kiểm tra.

JWS Compact cho JWT thường được nhắc như “signed JWT”, nhưng tiêu chuẩn JOSE có cả trường hợp **unsecured JWT**. Một hệ thống yêu cầu xác thực mật mã cần chủ động từ chối token không được bảo vệ, thay vì mặc định mọi JWT đều đã ký.

### 5.2. JWE: mã hóa nội dung, đồng thời dùng kiểm tra toàn vẹn phù hợp

JWE Compact Serialization có **năm phần**:

~~~text
BASE64URL(protected_header).BASE64URL(encrypted_key).BASE64URL(iv).BASE64URL(ciphertext).BASE64URL(authentication_tag)
~~~

Trong một số chế độ quản lý khóa, phần `encrypted_key` có thể rỗng nhưng vị trí của nó trong năm phần vẫn tồn tại.

Ví dụ protected header của một cấu hình JWE:

~~~json
{
  "alg": "RSA-OAEP-256",
  "enc": "A256GCM",
  "typ": "JWT"
}
~~~

Đây là ví dụ cú pháp và tên thuật toán, **không phải cấu hình bắt buộc** cho mọi hệ thống. Trường `alg` của JWE mô tả cách quản lý/thỏa thuận khóa, còn `enc` xác định thuật toán bảo vệ nội dung. Thuật toán và nguồn khóa được phép phải do chính sách bên nhận quyết định.

Đối với JWE với AEAD phù hợp:

- Claims trong **ciphertext** không hiển thị ở dạng rõ khi thiếu khóa giải mã.
- Ciphertext, tag và protected header/AAD được xác thực theo cấu trúc JWE.
- **Protected header vẫn đọc được**, dù được kiểm tra toàn vẹn; không đưa bí mật vào header.
- **Giải mã thành công chưa đủ để xác thực bên phát hành danh tính** nếu bất kỳ ai có thể tạo một JWE hợp lệ tới người nhận. Người nhận phải kiểm tra claims, ngữ cảnh và quan hệ tin cậy sau giải mã, đồng thời dùng chữ ký nếu cần chứng thực bên phát hành.

### 5.3. Cần vừa xác thực bên phát hành vừa giữ bí mật nội dung?

Một phương án là **ký trước, mã hóa sau**: tạo JWS chứa claims, rồi mã hóa JWS đó thành JWE. Người nhận giải mã JWE, xác minh JWS bên trong, rồi mới xử lý claims theo chính sách.

~~~mermaid
flowchart TD
    A["Claims gốc"] --> B["Phát hành JWS: ký/MAC"]
    B --> C["Mã hóa JWS thành JWE"]
    C --> D["Truyền hoặc lưu JWE"]
    D --> E["Bên nhận giải mã và xác thực JWE"]
    E --> F["Xác minh JWS bên trong"]
    F --> G{"Issuer, audience, thời hạn, quyền và ngữ cảnh hợp lệ?"}
    G -- "Có" --> H["Tiếp tục xử lý yêu cầu"]
    G -- "Không" --> I["Từ chối"]
~~~

Trong các hệ thống dùng JWT lồng nhau (*nested JWT*), cần quy định rõ loại token và thứ tự kiểm tra; với trường hợp ký rồi mã hóa, header ngoài có thể sử dụng `cty: "JWT"` theo quy tắc của chuẩn để báo nội dung là JWT lồng nhau. Không tự động xem JWE ngoài là bằng chứng về bên phát hành JWS trong.

Mã hóa bổ sung độ phức tạp quản lý khóa, kiểm tra và vận hành. Nếu payload không chứa thông tin bí mật cần ẩn khỏi bên cầm token, JWS kết hợp TLS và claims tối thiểu có thể đã phù hợp. Quyết định cuối cùng phải dựa trên mô hình đe dọa và yêu cầu bảo vệ dữ liệu.

## 6. Cùng một tình huống, cơ chế bảo vệ khác nhau cho kết quả khác nhau

Xét một token chứa các claims:

~~~json
{
  "sub": "alice",
  "scope": "invoice:read",
  "tenant_id": "company-A"
}
~~~

| Tình huống | Chữ ký số trên JWT | MAC trên JWT | JWE với AEAD |
| --- | --- | --- | --- |
| Kẻ tấn công đọc được token trên thiết bị client | Payload **vẫn đọc được** | Payload **vẫn đọc được** | Payload được che giấu nếu không có khóa giải mã |
| Kẻ tấn công sửa `scope` thành `invoice:write` | Xác minh chữ ký phải thất bại | Kiểm tra MAC phải thất bại | Kiểm tra tag/giải mã xác thực phải thất bại |
| API chỉ muốn **xác minh**, không được tự phát hành | Có thể chỉ giữ khóa công khai | API có khóa MAC nên về kỹ thuật có thể tạo MAC | Chỉ khả năng giải mã không tự chứng thực issuer |
| Token bị đánh cắp nhưng chưa hết hạn | Vẫn có thể bị phát lại | Vẫn có thể bị phát lại | Vẫn có thể bị phát lại nếu hệ thống chấp nhận bearer token đó |
| `alice` cố truy cập hóa đơn của Bob | Vẫn cần phân quyền trên hóa đơn | Vẫn cần phân quyền trên hóa đơn | Vẫn cần phân quyền trên hóa đơn |

### Ví dụ 1 — Sai lầm “JWT đã ký thì payload an toàn”

Nhà phát hành đưa số định danh cá nhân hoặc thông tin sức khỏe vào JWS vì cho rằng ba phần của token đã được “mã hóa Base64”. Người cầm token chỉ cần giải mã Base64url để thấy nội dung. Giải pháp là **hạn chế claims nhạy cảm** và, khi có yêu cầu rõ ràng phải ẩn nội dung, áp dụng mã hóa phù hợp với các bên được phép giải mã.

### Ví dụ 2 — Sai lầm “Có khóa công khai là có quyền cấp token”

API nhận khóa công khai của một nhà phát hành dùng RS256 để xác minh JWT. Khóa công khai không cho API tạo chữ ký có thể kiểm chứng như nhà phát hành. Nếu hệ thống trao cả khóa riêng cho API chỉ cần xác minh, ranh giới phân quyền quản lý khóa đã bị mở rộng không cần thiết.

### Ví dụ 3 — Sai lầm “Tất cả hệ thống cùng biết HMAC thì issuer được cô lập”

Trong HS256, mọi bên giữ cùng khóa HMAC đều có thể tạo MAC hợp lệ. Khi một dịch vụ xác minh bị xâm nhập và làm lộ khóa, kẻ tấn công có thể tạo token có MAC đúng trong phạm vi khóa bị lộ. Nếu cần nhiều bên chỉ xác minh độc lập, chữ ký bất đối xứng thường tạo ra ranh giới tin cậy rõ ràng hơn.

### Ví dụ 4 — Sai lầm “Giải mã được JWE chứng tỏ do đối tác gửi”

Bên nhận công bố khóa công khai để đối tác mã hóa dữ liệu gửi tới. Một người khác cũng biết khóa công khai có thể tạo một JWE được mã hóa tới bên nhận. Nếu yêu cầu chứng minh nội dung **do đối tác cụ thể phát hành**, cần xác thực nguồn phát hành riêng, chẳng hạn xác minh JWS bên trong hoặc cơ chế xác thực kênh/đối tác với thuộc tính tin cậy thích hợp.

### Ví dụ 5 — Sai lầm “Chữ ký hợp lệ là đủ để chấp nhận”

Token được ký đúng, nhưng có `aud` dành cho API khác, `exp` đã quá hạn, hoặc người dùng hiện không được phép đọc tài nguyên. Cơ chế mật mã vẫn hoàn thành phần việc của nó; **kiểm tra claims và chính sách phân quyền** phải quyết định từ chối.

### Ví dụ 6 — Sai lầm “Mã hóa làm token không thể bị sử dụng lại”

Một JWE còn hạn bị sao chép từ thiết bị và phát lại. Người nhận có thể giải mã, xác thực tag và thấy claims hợp lệ. Muốn chống phát lại cần thiết kế thêm thời hạn sử dụng, ràng buộc bên gửi, số định danh dùng một lần hoặc trạng thái thu hồi theo tính chất giao thức; không thể trông chờ vào mã hóa.

## 7. Bảo vệ phần nào của token và phần nào của hệ thống?

Câu hỏi “bảo vệ gì?” luôn phải đi cùng câu hỏi **“bảo vệ phạm vi byte, kênh và quan hệ tin cậy nào?”**.

| Đối tượng | Cơ chế thích hợp | Giới hạn cần nhận thức |
| --- | --- | --- |
| Header và claims của JWS | Chữ ký/MAC JWS và xác minh bằng khóa tin cậy | Không giấu claims; token có thể bị phát lại |
| Claims cần giữ bí mật đối với người không có khóa | JWE/mã hóa nội dung phù hợp | Độ an toàn phụ thuộc quản lý khóa, thuật toán và bên giải mã |
| Yêu cầu HTTP đi trên mạng | TLS, xác thực bên đầu cuối và kiểm tra phù hợp | TLS không tự kiểm tra quyền trên tài nguyên hoặc tính đúng của payload ứng dụng |
| Body HTTP cần bảo đảm nguồn gốc xuyên nhiều trung gian | Cơ chế ký/xác thực thông điệp ở tầng ứng dụng phù hợp | Chữ ký trên **JWT** không mặc nhiên bao phủ body HTTP |
| Dữ liệu lưu trong kho | Kiểm soát truy cập và mã hóa dữ liệu lưu trữ khi phù hợp | Mã hóa token không đồng nghĩa dữ liệu trong cơ sở dữ liệu đã được bảo vệ |
| Quyết định cấp quyền | Kiểm tra chính sách, scope, vai trò, quan hệ sở hữu và ngữ cảnh | Không thể suy ra quyền từ việc token có chữ ký hoặc giải mã thành công |

Đặc biệt, chữ ký của một access token không ký luôn cả đường dẫn URL, phương thức HTTP, body yêu cầu, kết quả trả về hoặc dữ liệu lưu ở hệ thống khác. Nếu cần ràng buộc token với một thông điệp cụ thể, phải thiết kế cơ chế bảo vệ thông điệp đó ở phạm vi phù hợp.

## 8. Quản lý khóa và quy tắc xác minh là một phần của bảo đảm bảo mật

Các cơ chế mật mã chỉ có ý nghĩa khi bên nhận biết mình đang tin **khóa nào, của ai, cho mục đích gì**.

1. **Thiết lập nguồn khóa tin cậy:** khóa công khai xác minh JWS phải gắn với bên phát hành được phép; khóa giải mã JWE phải thuộc đúng người nhận; khóa HMAC chỉ phân phối cho những bên được phép cùng nắm bí mật.
2. **Ràng buộc thuật toán với cấu hình:** chỉ chấp nhận tập thuật toán đã cho phép cho loại token và khóa tương ứng. Không tin thuật toán chỉ vì header token tự tuyên bố; tránh nhầm lẫn thuật toán bất đối xứng và HMAC.
3. **Xử lý metadata khóa như dữ liệu chưa tin cậy:** `kid` có thể giúp chọn khóa trong tập khóa tin cậy, **không cấp quyền** tải hoặc tin khóa tùy ý. Không tự động theo các URL tham chiếu khóa từ header chưa xác minh nếu không có chính sách chặt chẽ.
4. **Tách trách nhiệm phát hành và xác minh:** với chữ ký bất đối xứng, chỉ bên được phép phát hành giữ khóa riêng; các bên nhận chỉ cần khóa công khai. Với MAC, chấp nhận có chủ đích việc bên xác minh sở hữu khả năng tạo MAC.
5. **Bảo vệ vòng đời khóa:** tạo khóa đủ mạnh, lưu an toàn, giới hạn truy cập, luân chuyển định kỳ hoặc khi có sự cố, và có chiến lược xử lý token ký bằng khóa cũ trong thời gian chuyển đổi.
6. **Tuân thủ điều kiện nonce/IV và tag:** với mã hóa có xác thực, không tái sử dụng nonce trái quy tắc, không bỏ qua lỗi xác thực tag, không giải mã rồi sử dụng nội dung trước khi xác thực hoàn tất.
7. **Kiểm tra claims sau khi mật mã hợp lệ:** issuer, audience, thời hạn, loại token, quyền và đối tượng tài nguyên phải đúng hợp đồng; không coi dữ liệu đã ký là dữ liệu luôn còn hiệu lực.
8. **Không tự thiết kế mật mã:** dùng thư viện được duy trì, thuật toán chuẩn và hồ sơ tương thích với hệ thống; tránh thuật toán lạc hậu và chế độ mã hóa không xác thực khi yêu cầu bảo mật bao gồm toàn vẹn.

### Luồng đánh giá tại bên nhận

~~~mermaid
flowchart TD
    A["Nhận token"] --> B{"Đúng loại token/hồ sơ được phép?"}
    B -- "Không" --> X["Từ chối"]
    B -- "Có" --> C{"JWS hay JWE, có lồng nhau?"}
    C --> D["Áp dụng cơ chế xác minh/giải mã được cấu hình"]
    D --> E{"Mật mã và nguồn khóa hợp lệ?"}
    E -- "Không" --> X
    E -- "Có" --> F["Kiểm tra issuer, audience, thời hạn và mục đích"]
    F --> G{"Claims hợp lệ theo hợp đồng?"}
    G -- "Không" --> X
    G -- "Có" --> H["Đánh giá phân quyền trên hành động/tài nguyên"]
    H --> I{"Cho phép?"}
    I -- "Không" --> X
    I -- "Có" --> J["Thực thi"]
~~~

Luồng này minh họa nguyên tắc, không phải API kiểm chứng dùng được cho mọi JWT. Ví dụ, JWT dưới dạng JWE chứa JWS phải **xác minh JWS sau khi giải mã JWE**; token có nhiều lớp cần kiểm tra đầy đủ từng lớp theo hợp đồng.

## 9. Chọn cơ chế theo yêu cầu thực tế

| Yêu cầu | Lựa chọn thường cân nhắc | Vì sao |
| --- | --- | --- |
| API cần xác minh access token do một bên phát hành duy nhất cấp, payload không chứa bí mật | JWS dùng chữ ký bất đối xứng, kết hợp TLS và kiểm tra claims | API kiểm chứng được bằng khóa công khai mà không sở hữu khóa phát hành |
| Hai thành phần cùng thuộc một miền tin cậy muốn xác thực thông điệp bằng bí mật chung | MAC/HMAC được chuẩn hóa | Bảo vệ toàn vẹn và xác thực trong nhóm biết bí mật, với giả định chia sẻ khóa được chấp nhận |
| Token cần che claims khỏi bên không phải người nhận | JWE với thuật toán bảo vệ nội dung có xác thực | Cung cấp tính bí mật cùng kiểm tra toàn vẹn ciphertext |
| Phải vừa ẩn claims vừa kiểm chứng issuer độc lập | JWS được ký rồi bọc trong JWE, cùng chính sách xác minh từng lớp | Tách yêu cầu tin bên phát hành khỏi yêu cầu chỉ người nhận được đọc |
| Chỉ cần bảo vệ token trong quá trình truyền giữa client và API | TLS, cách lưu token an toàn và token với claims tối thiểu | Bảo vệ kết nối; JWE chỉ cần thêm khi có yêu cầu bí mật ngoài phạm vi kết nối |
| Cần quyết định có cho phép truy cập dữ liệu khách hàng cụ thể không | Phân quyền ở API/tài nguyên | Chữ ký, MAC và mã hóa đều không thay thế chính sách truy cập |

Không có thuật toán “tốt nhất” cho mọi tình huống. Tiêu chí chọn phải xuất phát từ việc **ai được phát hành**, **ai được kiểm chứng**, **ai được đọc**, **ai có thể giữ khóa bí mật**, và **bằng chứng nào cần duy trì qua các ranh giới hệ thống**.

## 10. Tự kiểm tra nhận thức

Hãy xác định cơ chế nào giải quyết vấn đề và cơ chế nào còn thiếu:

| Câu hỏi | Kết luận |
| --- | --- |
| JWS ký bằng RS256 được xác minh đúng; người có token có đọc được payload không? | **Có.** Chữ ký không che giấu payload. |
| API xác minh JWS dùng HS256 có thể tự tạo token hợp lệ nếu giữ cùng khóa không? | **Có.** MAC là cơ chế dùng khóa bí mật chung. |
| Một JWE dùng AES-GCM bị thay ciphertext; người nhận có nên trả plaintext ra ứng dụng không? | **Không.** Phải xác minh thành công tag; sai tag thì từ chối. |
| Nhận JWE mã hóa tới khóa công khai của API có chứng minh đối tác X là người gửi không? | **Không tự động.** Có thể cần chữ ký hoặc cơ chế xác thực nguồn phát hành riêng. |
| Chữ ký JWT có chứng minh người cầm bearer token chính là chủ thể ghi trong token không? | **Không.** Token có thể bị đánh cắp và sử dụng lại. |
| JWT có MAC hợp lệ, nhưng quyền trên tài nguyên đã bị thu hồi; có nên chấp nhận không? | **Không**, nếu chính sách hiện hành yêu cầu từ chối. MAC không đồng nghĩa phân quyền. |
| Có cần bảo vệ khóa công khai xác minh JWS khỏi bị đọc trộm như khóa riêng không? | **Không cần giữ bí mật**, nhưng phải bảo vệ tính đúng đắn và mối liên kết với issuer. |

## 11. Kết luận cốt lõi

- **Chữ ký số**: bảo vệ toàn vẹn và có thể xác thực nguồn ký nhờ cặp khóa riêng/công khai cùng chuỗi tin cậy; **không che giấu** dữ liệu.
- **MAC/HMAC**: bảo vệ toàn vẹn và xác thực trong **nhóm biết chung khóa bí mật**; bên kiểm chứng cũng có khả năng tạo MAC; **không che giấu** dữ liệu.
- **Mã hóa**: bảo vệ **bí mật nội dung**; muốn chống sửa đổi cần dùng cơ chế xác thực thích hợp như AEAD; giải mã thành công **không tự chứng minh danh tính issuer**.
- **JWS** áp dụng chữ ký/MAC cho token; **JWE** áp dụng mã hóa và kiểm tra toàn vẹn phù hợp; khi cần cả bí mật và xác thực issuer, có thể dùng JWT lồng nhau và kiểm chứng đầy đủ từng lớp.
- **Không cơ chế nào trong ba cơ chế tự thay thế** việc quản lý khóa đúng cách, kiểm tra claims, chống đánh cắp/phát lại token hoặc quyết định phân quyền trên tài nguyên.

### Tiêu chuẩn và tài liệu tham chiếu

- [RFC 7519 – JSON Web Token (JWT)](https://www.rfc-editor.org/rfc/rfc7519)
- [RFC 7515 – JSON Web Signature (JWS)](https://www.rfc-editor.org/rfc/rfc7515)
- [RFC 7516 – JSON Web Encryption (JWE)](https://www.rfc-editor.org/rfc/rfc7516)
- [RFC 7518 – JSON Web Algorithms (JWA)](https://www.rfc-editor.org/rfc/rfc7518)
- [RFC 8725 – JSON Web Token Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725)
- [RFC 5116 – An Interface and Algorithms for Authenticated Encryption](https://www.rfc-editor.org/rfc/rfc5116)
- [NIST SP 800-38D – Galois/Counter Mode (GCM) and GMAC](https://csrc.nist.gov/pubs/sp/800/38/d/final)
