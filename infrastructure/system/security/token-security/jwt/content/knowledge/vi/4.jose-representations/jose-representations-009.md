# Các tùy chọn JOSE không thể mặc nhiên áp dụng cho JWT

## 1. JOSE rộng hơn JWT

**JOSE** (*JSON Object Signing and Encryption*) là họ tiêu chuẩn mô tả cách ký, xác thực, mã hóa và biểu diễn khóa cho dữ liệu. Các thành phần chính gồm JWS, JWE, JWK và JWA. **JWT** (*JSON Web Token*) là một định dạng claims được xây dựng trên các cơ chế JOSE này.

Điểm dễ gây nhầm lẫn là một tính năng có thể hợp lệ trong JWS hoặc JWE tổng quát nhưng **không thuộc cách biểu diễn JWT được RFC 7519 quy định**, hoặc chỉ được dùng khi một profile/giao thức cụ thể cho phép. Không thể suy luận rằng mọi serialization, header parameter, thuật toán hoặc phần mở rộng của JOSE đều tự động áp dụng cho JWT.

Trong module **SECURITY_TOKEN_SECURITY_JWT — Security - JSON Web Token (JWT)**, bài này tập trung vào ranh giới giữa JOSE tổng quát và JWT: định dạng Compact, payload, header, recipient, AAD, phần mở rộng và chính sách lựa chọn thuật toán. Đây là kiến thức ở mức giao thức bảo mật, độc lập với ngôn ngữ lập trình và framework.

Theo RFC 7519, JWT được biểu diễn bằng:

- **JWS Compact Serialization** nếu JWT được bảo vệ bằng chữ ký/MAC hoặc là Unsecured JWT.
- **JWE Compact Serialization** nếu JWT được mã hóa.

Vì vậy, JWT Compact có cấu trúc chuỗi ba phần hoặc năm phần tùy loại. Các JSON Serialization của JWS/JWE là định dạng JOSE tổng quát; không tự động trở thành JWT chỉ vì payload bên trong là JSON có các claim quen thuộc.

## 2. Bản đồ: tính năng JOSE nào áp dụng cho JWT?

| Tính năng JOSE | Có trong JOSE tổng quát? | Có thể dùng trực tiếp làm JWT theo RFC 7519? | Điều cần nhớ |
| --- | --- | --- | --- |
| JWS Compact | Có | **Có** | JWT có chữ ký/MAC dùng ba phần Compact |
| JWE Compact | Có | **Có** | JWT được mã hóa dùng năm phần Compact |
| JWS JSON General/Flattened | Có | **Không** | JWT theo RFC 7519 dùng JWS Compact |
| JWE JSON General/Flattened | Có | **Không** | JWT theo RFC 7519 dùng JWE Compact |
| Nhiều chữ ký (mảng signatures) | Có trong JWS General | **Không phải cấu trúc JWT Compact** | Chính sách nhiều chữ ký thuộc ứng dụng/protocol riêng |
| Nhiều recipient (mảng recipients) | Có trong JWE General | **Không phải cấu trúc JWT Compact** | Một ciphertext có thể được mở bởi nhiều recipient |
| Unprotected Header | Có trong JSON Serialization | **Không có trong Compact JWT** | Header của Compact JWT được bảo vệ |
| Detached JWS payload | Có trong JWS tổng quát | **Không phải JWT tự chứa Claims Set thông thường** | Payload được truyền ngoài token; phải có profile riêng |
| JWS b64: false | Có theo RFC 7797 | **Bị cấm đối với JWT** | JWT payload phải dùng base64url encoding thông thường |
| JWE JSON AAD | Có trong JWE JSON Serialization | **Không có trường AAD riêng trong JWE Compact JWT** | Protected Header vẫn là AAD mặc định |
| crit và header extension | Có | Có thể dùng khi tuân thủ yêu cầu JWT và profile | Bên nhận phải hiểu critical parameter, nếu không phải từ chối |
| JWE zip | Có trong JWE | Không mặc nhiên bật | Cần đánh giá hỗ trợ, rủi ro nén và chính sách profile |
| jku, jwk, x5u, x5c | Có trong JOSE Header | Có thể xuất hiện theo đặc tả | Không tự tạo niềm tin vào khóa hoặc URL |
| alg: none | Có trong JWS | RFC 7519 định nghĩa Unsecured JWT | Không chấp nhận trong luồng xác thực/phân quyền thông thường |

Các mục dưới đây giải thích vì sao cần phân biệt như vậy.

## 3. JSON Serialization của JWS/JWE không phải serialization JWT

### 3.1. JWS JSON General và Flattened

JWS JSON Serialization có hai dạng:

- **General:** đối tượng JSON có payload và mảng signatures; có thể chứa nhiều chữ ký.
- **Flattened:** đối tượng JSON có payload và một chữ ký ở cấp cao nhất.

Ví dụ General:

```json
{
  "payload": "<payload-base64url>",
  "signatures": [
    {
      "protected": "<protected-header-A>",
      "signature": "<signature-A>"
    },
    {
      "protected": "<protected-header-B>",
      "signature": "<signature-B>"
    }
  ]
}
```

Đây là biểu diễn JWS tổng quát. Dù payload chứa JSON với iss, sub, aud và exp, đối tượng bên ngoài vẫn là JWS JSON Serialization. RFC 7519 định nghĩa JWT Compact dựa trên JWS Compact, không định nghĩa JWT bằng mảng signatures.

### 3.2. JWE JSON General và Flattened

JWE JSON Serialization có:

- **General:** mảng recipients, cho phép nhiều recipient.
- **Flattened:** một recipient ở cấp cao nhất.

Ví dụ General:

```json
{
  "protected": "<protected-header>",
  "recipients": [
    {
      "header": {"alg": "RSA-OAEP-256", "kid": "recipient-A"},
      "encrypted_key": "<encrypted-cek-A>"
    },
    {
      "header": {"alg": "RSA-OAEP-256", "kid": "recipient-B"},
      "encrypted_key": "<encrypted-cek-B>"
    }
  ],
  "iv": "<iv>",
  "ciphertext": "<shared-ciphertext>",
  "tag": "<authentication-tag>"
}
```

Đây là JWE JSON tổng quát, không phải JWE Compact JWT. Trong một JWE General, các recipient dùng chung ciphertext, IV và tag; thông tin quản lý CEK được biểu diễn riêng cho từng recipient. JWT Compact không có mảng recipients.

### 3.3. Hệ quả khi thiết kế API

Nếu một API tuyên bố nhận JWT theo RFC 7519, nó cần xác định rõ JWS Compact hoặc JWE Compact tương ứng. Không nên gửi JWS/JWE JSON Serialization vào endpoint chỉ hỗ trợ JWT Compact, hoặc tự chuyển đổi một JSON Serialization thành JWT bằng cách chỉ lấy payload.

Nếu một giao thức thực sự cần nhiều chữ ký hoặc nhiều recipient, hãy mô tả nó là một cấu trúc JOSE theo profile riêng, quy định rõ cách xử lý và không gọi nó là JWT Compact.

## 4. Unprotected Header không có trong Compact JWT

JWS/JWE JSON Serialization cho phép header được chia thành protected và unprotected. Tuy nhiên, trong Compact Serialization chỉ có một Protected Header:

- JWS Compact: protected header nằm trong đoạn đầu tiên và tham gia signing input.
- JWE Compact: protected header nằm trong đoạn đầu tiên và được đưa vào AAD.
- Compact JWT không có trường JSON header hoặc unprotected để truyền thêm header không được bảo vệ.

Ví dụ JWS JSON có unprotected header:

```json
{
  "payload": "<payload-base64url>",
  "protected": "<base64url-of-protected-header>",
  "header": {
    "comment": "metadata"
  },
  "signature": "<signature>"
}
```

Trường header trong ví dụ không tham gia signing input. Không thể mang cấu trúc này sang JWT Compact rồi kỳ vọng có cùng ngữ nghĩa.

Tương tự, JWE JSON có thể có unprotected dùng chung và header riêng cho recipient. Những vùng này không được Authentication Tag bảo vệ. JWE Compact JWT chỉ có Protected Header.

**Quy tắc thực hành:** khi xử lý JWT Compact, coi header nhận được là Protected Header; kiểm tra tham số, allowlist thuật toán và nguồn khóa theo profile. Không tự bổ sung ngữ nghĩa unprotected header của JSON Serialization vào Compact JWT.

## 5. Detached Payload: chữ ký JWS không đồng nghĩa JWT tự chứa

JWS tổng quát có thể dùng **detached payload**: payload được truyền riêng ngoài đối tượng JWS, trong khi phần biểu diễn chữ ký không mang nội dung payload. Bên xác minh phải có đúng payload bên ngoài để tạo signing input.

Ví dụ về hình dạng detached JWS Compact:

```text
BASE64URL(Protected Header)..BASE64URL(Signature)
```

Đoạn giữa rỗng vì payload được cung cấp ngoài băng. Đây là cách biểu diễn JWS cho những giao thức ký dữ liệu ngoài token, chẳng hạn một tài liệu hoặc nội dung lớn được truyền riêng.

JWT theo RFC 7519 biểu diễn một JWT Claims Set trong payload của JWS Compact hoặc plaintext của JWE Compact. Một detached JWS mà payload claims không nằm trong token **không phải JWT tự chứa Claims Set theo cách dùng thông thường**. Bên nhận không được tự suy diễn nội dung JWT từ một payload ngoài băng nếu profile không quy định rõ.

Nếu một giao thức cần tham chiếu dữ liệu ngoài token, cần định nghĩa:

1. Payload ngoài được lấy từ nguồn nào và được ràng buộc với token ra sao.
2. Cách xác minh đúng bytes payload trước khi sử dụng.
3. Cách chống tráo đổi payload giữa các request hoặc tài nguyên.
4. Cách phân biệt thông điệp đó với JWT Compact thông thường.

Không nên dùng detached payload như một cách rút gọn JWT nếu chưa có profile thống nhất.

## 6. b64: false: tùy chọn JWS không được dùng cho JWT

RFC 7797 định nghĩa phần mở rộng **JWS Unencoded Payload Option**. Tham số header b64 điều khiển payload có được base64url-encode trước khi tạo signing input hay không.

Với JWS mặc định:

```text
signingInput = ASCII(
    BASE64URL(protectedHeader)
    + "."
    + BASE64URL(payload)
)
```

Với JWS dùng b64: false, payload không được base64url-encode trong signing input theo quy tắc phần mở rộng:

```text
signingInput = ASCII(BASE64URL(protectedHeader) + ".")
               || payloadBytes
```

Phần mở rộng này hữu ích trong một số giao thức ký dữ liệu có định dạng riêng hoặc payload cần giữ nguyên biểu diễn. Tuy nhiên, RFC 7797 **cấm sử dụng tùy chọn unencoded payload này trong JWT**. JWT Claims Set phải được biểu diễn theo quy tắc base64url của JWS Compact.

Khi dùng phần mở rộng với JWS tổng quát:

- b64 phải nằm trong Protected Header.
- b64 phải được liệt kê trong crit.
- Bên nhận phải hiểu và hỗ trợ đầy đủ phần mở rộng.
- Nếu không hiểu tham số critical, phải từ chối JWS.

Không được chấp nhận b64: false chỉ vì thư viện JWS tổng quát có hỗ trợ. Một bộ xác minh JWT phải áp dụng ràng buộc JWT riêng và từ chối tùy chọn này.

## 7. JWE Additional Authenticated Data: khác biệt Compact và JSON

JWE sử dụng AAD (*Additional Authenticated Data*) để bảo vệ tính toàn vẹn của header và dữ liệu bổ sung. Cần phân biệt:

### 7.1. JWE Compact JWT

Trong JWE Compact, AAD mặc định là bytes ASCII của protected header segment:

```text
AAD = ASCII(BASE64URL(UTF8(Protected Header)))
```

Compact không có trường JSON aad riêng. Vì JWT mã hóa theo RFC 7519 dùng JWE Compact, nó không thể tùy ý thêm trường AAD ngoài băng vào serialization JWT.

### 7.2. JWE JSON Serialization

JWE JSON có thể có trường aad, chứa dữ liệu bổ sung được base64url-encode. AAD thực tế là:

```text
AAD = ASCII(
    BASE64URL(UTF8(Protected Header))
    + "."
    + BASE64URL(JWE AAD)
)
```

AAD được xác thực nhưng không được mã hóa. Bên nhận phải có đúng bytes AAD để kiểm tra Authentication Tag.

Nếu một ứng dụng cần ràng buộc thông điệp với ngữ cảnh ngoài token, nó có thể thiết kế giao thức JWE JSON dùng AAD. Nhưng không thể coi trường aad là một claim JWT hoặc tự thêm nó vào JWE Compact JWT. Cần chọn đúng serialization và định nghĩa rõ cách hai phía tạo lại AAD.

## 8. crit và các phần mở rộng JOSE

JOSE cho phép mở rộng header bằng tham số mới. Tham số crit liệt kê các phần mở rộng mà bên nhận **bắt buộc phải hiểu** vì chúng có thể thay đổi cách diễn giải hoặc xử lý thông điệp.

Ví dụ:

```json
{
  "alg": "PS256",
  "crit": ["example-mode"],
  "example-mode": "strict"
}
```

Khi gặp tham số critical:

1. crit phải nằm trong Protected Header.
2. Tên được liệt kê phải tồn tại trong cùng JOSE Header.
3. Bên nhận phải hiểu đúng ngữ nghĩa và thực hiện phần xử lý tương ứng.
4. Nếu không hỗ trợ, phải từ chối; không được bỏ qua âm thầm.

Một JWT profile có thể cho phép một số phần mở rộng JOSE nhất định, nhưng việc phần mở rộng tồn tại trong registry không có nghĩa mọi bộ xử lý JWT đều phải hỗ trợ nó. Profile phải nêu rõ các header parameter được phép, bắt buộc và bị cấm.

Đối với JWT, đặc biệt cần tránh:

- Tự chấp nhận tham số header lạ mà không biết tác động của nó.
- Bỏ qua crit vì chữ ký đã hợp lệ.
- Dùng cùng một profile cho nhiều loại token có ngữ nghĩa khác nhau.
- Cho phép một phần mở rộng làm thay đổi cách xác minh mà không ràng buộc bằng Protected Header.

## 9. JWE zip: nén không phải mặc định an toàn

JWE định nghĩa header parameter zip để chỉ thuật toán nén plaintext trước khi mã hóa. Đây là một tính năng JWE hợp lệ, nhưng không nên mặc nhiên bật trong mọi JWT được mã hóa.

Rủi ro cần xem xét:

- **Rò rỉ qua độ dài:** nén dữ liệu bí mật cùng dữ liệu do đối phương kiểm soát có thể làm độ dài ciphertext tiết lộ thông tin về nội dung.
- **Tốn tài nguyên giải nén:** dữ liệu nén có thể phình lớn khi giải nén, gây tiêu thụ CPU/bộ nhớ.
- **Khác biệt hỗ trợ:** không phải mọi profile hoặc recipient đều hỗ trợ cùng thuật toán nén.
- **Phức tạp xử lý:** bên nhận phải kiểm tra zip, xác thực tag trước, rồi mới giải nén theo giới hạn tài nguyên.

Nếu giao thức cho phép zip, cần quy định rõ thuật toán, giới hạn kích thước trước/sau giải nén và điều kiện chấp nhận. Với token chứa dữ liệu nhạy cảm hoặc dữ liệu do đối phương kiểm soát, nên tránh nén trước mã hóa trừ khi đã đánh giá rủi ro. RFC 8725 khuyến nghị không nén plaintext trước khi mã hóa JWT do nguy cơ rò rỉ thông tin.

## 10. Header chỉ dẫn khóa không tự tạo niềm tin

Các tham số JOSE như kid, jku, jwk, x5u, x5c hỗ trợ định danh hoặc phân phối thông tin khóa/chứng thư. Tuy nhiên, chúng không tự xác lập nguồn tin cậy:

| Tham số | Công dụng | Vì sao không thể mặc nhiên tin? |
| --- | --- | --- |
| kid | Gợi ý chọn khóa trong một tập khóa | Chuỗi định danh do bên gửi cung cấp; phải tra trong tập khóa đã tin cậy |
| jku | URL của JWK Set | URL có thể do đối phương kiểm soát; tải tùy ý có thể tạo SSRF hoặc đưa khóa giả vào |
| jwk | Khóa được nhúng trong header | Khóa do bên gửi cung cấp không tự chứng minh quyền sở hữu hoặc quan hệ với issuer |
| x5u | URL tới chứng thư X.509 | Cần giới hạn nguồn và xác minh chuỗi chứng thư |
| x5c | Chuỗi chứng thư được nhúng | Phải xác minh chuỗi, chủ thể, mục đích và chính sách tin cậy |

Quy trình an toàn:

1. Xác định issuer hoặc recipient được phép từ cấu hình tin cậy.
2. Lấy khóa từ trust store hoặc nguồn JWKS đã được cấu hình cho đúng bên đó.
3. Dùng kid làm gợi ý tra cứu trong phạm vi nguồn tin cậy.
4. Kiểm tra loại khóa, thuật toán, mục đích và trạng thái khóa.
5. Xác minh chữ ký hoặc thực hiện giải mã.
6. Sau khi xác minh mật mã, tiếp tục kiểm tra issuer, audience, thời hạn và loại token.

Không tự động tải URL bất kỳ từ header, không dùng kid làm đường dẫn file hoặc URL, và không coi khóa nhúng là đáng tin chỉ vì nó nằm trong một token có cấu trúc đúng.

## 11. alg: none: được định nghĩa không có nghĩa nên chấp nhận

RFC 7519 định nghĩa **Unsecured JWT** sử dụng JWS với alg: none, có ba đoạn Compact nhưng phần chữ ký rỗng:

```text
BASE64URL(Protected Header).BASE64URL(Claims Set).
```

Đây là một trường hợp được tiêu chuẩn định nghĩa, nhưng không có chữ ký/MAC để phát hiện sửa đổi ở cấp JWT. Nó không phù hợp cho xác thực hoặc phân quyền thông thường.

Một số nguyên tắc:

- JWT profile thông thường nên từ chối none.
- Không cho token tự chọn thuật toán ngoài allowlist.
- Không dùng cùng luồng xử lý cho token có chữ ký và token không chữ ký.
- Nếu một giao thức đặc biệt cần token không bảo vệ mật mã, phải xác định cơ chế bảo vệ độc lập, nguồn gửi và ranh giới tin cậy một cách tường minh.

Việc thư viện JOSE hỗ trợ none theo RFC không buộc ứng dụng phải chấp nhận nó. Chính sách của bên nhận quyết định tập thuật toán được phép.

## 12. Cách xây dựng một JWT profile an toàn

Một **JWT profile** là tập quy tắc cụ thể mà issuer và recipient thống nhất để phát hành, truyền và xác minh một loại JWT. Profile giúp giới hạn tập tính năng JOSE có thể sử dụng.

Một profile nên xác định:

1. **Serialization:** chỉ nhận JWS Compact, JWE Compact hay Nested JWT; không nhận JSON Serialization nếu không được định nghĩa rõ.
2. **Thuật toán:** allowlist alg và enc; loại bỏ none trong luồng thông thường.
3. **Khóa:** nguồn khóa tin cậy, cách tra kid, loại khóa, mục đích và quy trình xoay vòng.
4. **Header:** tham số nào bắt buộc, tùy chọn, bị cấm; cách xử lý crit; không chấp nhận header trùng tên hoặc mơ hồ.
5. **Payload:** JWT Claims Set phải được mang trong payload theo serialization chuẩn; không sử dụng b64: false hoặc detached payload như thể JWT tự chứa.
6. **Recipient và AAD:** nếu cần nhiều recipient hoặc AAD riêng, xác định đó là giao thức JWE JSON riêng, không gọi nhầm là JWT Compact.
7. **Nén:** quy định có cho phép zip hay không; mặc định nên tránh nén plaintext trước mã hóa.
8. **Claims:** xác định issuer, audience, thời hạn, loại token và claim bắt buộc.
9. **Lỗi:** từ chối token sai cấu trúc, thuật toán không hỗ trợ, critical extension lạ hoặc xác minh mật mã thất bại.
10. **Phân biệt token:** mỗi loại token có profile và quy tắc xác minh riêng để tránh cross-JWT confusion.

Ví dụ một profile đơn giản cho access token có chữ ký:

```text
Serialization: JWS Compact
Allowed algorithms: PS256
Unsecured JWT: reject
Detached payload: reject
JWS b64=false: reject
Unprotected header: not applicable to Compact
Trusted keys: configured issuer JWKS
Required claims: iss, sub, aud, exp
Audience: exact API identifier
Token type: application-specific access-token profile
Unknown critical headers: reject
```

Ví dụ trên chỉ là một profile minh họa; thuật toán và claim thực tế phải phù hợp với hệ thống, khả năng tương thích và chính sách mật mã đang áp dụng.

## 13. Ma trận quyết định: khi nào dùng tính năng nào?

| Nhu cầu | Cách tiếp cận phù hợp | Ranh giới cần nhớ |
| --- | --- | --- |
| JWT có chữ ký/MAC thông thường | JWS Compact | Payload đọc được; xác minh chữ ký/MAC và claims |
| JWT cần giữ kín | JWE Compact | Một recipient; xác minh tag trước khi dùng plaintext |
| Vừa giữ kín vừa xác thực issuer | Nested JWT | Ký JWS trước, mã hóa JWE sau; xác minh cả hai lớp |
| Nhiều bên ký cùng tài liệu | JWS General JSON | Đây là JWS tổng quát, không phải JWT Compact |
| Nhiều bên nhận cùng nội dung mã hóa | JWE General JSON | Đây là JWE tổng quát, không phải JWT Compact |
| Ký payload ngoài băng | Detached JWS | Không tự coi là JWT tự chứa claims |
| Payload không base64url trong JWS | JWS b64: false theo RFC 7797 | Không được dùng trong JWT |
| AAD bổ sung ngoài protected header | JWE JSON Serialization | Không có trường aad riêng trong JWE Compact JWT |
| Mở rộng JOSE Header | crit và profile tương ứng | Bên nhận không hiểu critical parameter phải từ chối |
| Nén trước khi mã hóa | JWE zip, chỉ khi được profile cho phép | Đánh giá rò rỉ độ dài và tài nguyên giải nén |

## 14. Checklist kiểm tra trước khi chấp nhận JWT

- [ ] Đầu vào có đúng serialization mà profile quy định không?
- [ ] Có nhầm JWS/JWE JSON Serialization với JWT Compact không?
- [ ] Có detached payload hoặc b64: false không? Nếu đang xử lý JWT, phải từ chối tùy chọn b64: false và không coi payload ngoài băng là Claims Set tự chứa.
- [ ] Có tham số unprotected header không? Compact JWT không có vùng này.
- [ ] Có trường AAD riêng không? JWE Compact JWT không có trường aad riêng.
- [ ] crit có được xử lý đầy đủ không? Critical parameter không hiểu phải bị từ chối.
- [ ] alg/enc có nằm trong allowlist và tương thích khóa không?
- [ ] kid, jku, jwk, x5u, x5c có được ràng buộc với nguồn khóa tin cậy không?
- [ ] zip có được profile cho phép và đã đánh giá rủi ro nén chưa?
- [ ] Có từ chối alg: none trong luồng xác thực/phân quyền thông thường không?
- [ ] Chữ ký/MAC hoặc Authentication Tag đã được xác minh trước khi sử dụng claims chưa?
- [ ] iss, aud, exp, nbf, token type và quyền ứng dụng đã được kiểm tra chưa?
- [ ] Loại token có được tách biệt với các loại token khác không?

## 15. Câu hỏi tự kiểm tra

**Câu 1.** Một JWS JSON General có payload chứa iss, sub, aud và exp có tự động là JWT theo RFC 7519 không?

**Đáp án:** Không. JWT theo RFC 7519 được biểu diễn bằng JWS Compact hoặc JWE Compact; JWS JSON General là serialization JWS tổng quát.

**Câu 2.** Có thể sử dụng b64: false trong JWT nếu thư viện hỗ trợ không?

**Đáp án:** Không. RFC 7797 cấm tùy chọn unencoded payload trong JWT.

**Câu 3.** Detached JWS có tự mang Claims Set trong token không?

**Đáp án:** Không. Payload được truyền ngoài băng; đây là mô hình JWS tổng quát và cần profile riêng nếu muốn kết hợp với dữ liệu dạng claims.

**Câu 4.** JWE Compact JWT có thể có trường aad riêng như JWE JSON không?

**Đáp án:** Không. AAD mặc định của JWE Compact là protected header segment; trường AAD bổ sung thuộc JWE JSON Serialization.

**Câu 5.** Vì sao không thể mặc nhiên tin jku hoặc jwk?

**Đáp án:** Vì URL hoặc khóa được cung cấp trong header có thể do bên gửi kiểm soát; nguồn khóa phải được xác minh độc lập và ràng buộc với issuer/recipient tin cậy.

**Câu 6.** crit có thể bị bỏ qua nếu chữ ký đã hợp lệ không?

**Đáp án:** Không. Bên nhận phải hiểu tất cả critical parameter; nếu không hỗ trợ thì từ chối.

**Câu 7.** Có nên bật zip cho mọi JWT được mã hóa không?

**Đáp án:** Không. Cần đánh giá rò rỉ thông tin qua độ dài, khả năng hỗ trợ và giới hạn giải nén; RFC 8725 khuyến nghị tránh nén plaintext trước mã hóa JWT.

**Câu 8.** Một tính năng được định nghĩa trong JOSE có bắt buộc phải được mọi JWT processor hỗ trợ không?

**Đáp án:** Không. Profile JWT phải xác định tập serialization, header, thuật toán và phần mở rộng được phép; bên nhận từ chối tính năng ngoài profile.

## 16. Tài liệu chuẩn tham khảo

- [RFC 7519 — JSON Web Token (JWT)](https://www.rfc-editor.org/rfc/rfc7519): định nghĩa JWT Claims Set và các dạng tuần tự hóa JWT.
- [RFC 7515 — JSON Web Signature (JWS)](https://www.rfc-editor.org/rfc/rfc7515): JWS Compact/JSON Serialization, detached payload và signing input.
- [RFC 7516 — JSON Web Encryption (JWE)](https://www.rfc-editor.org/rfc/rfc7516): JWE Compact/JSON Serialization, recipient, AAD và zip.
- [RFC 7517 — JSON Web Key (JWK)](https://www.rfc-editor.org/rfc/rfc7517): JWK, JWK Set và biểu diễn khóa.
- [RFC 7518 — JSON Web Algorithms (JWA)](https://www.rfc-editor.org/rfc/rfc7518): thuật toán JOSE và các tham số liên quan.
- [RFC 7797 — JWS Unencoded Payload Option](https://www.rfc-editor.org/rfc/rfc7797): phần mở rộng b64 và quy định không sử dụng unencoded payload trong JWT.
- [RFC 8725 — JSON Web Token Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725): kiểm soát thuật toán, nguồn khóa, nén, phân biệt loại JWT và xác minh claims.

**Ghi nhớ:** JOSE là họ cơ chế rộng hơn JWT. JWT theo RFC 7519 dùng Compact Serialization; nhiều chữ ký, nhiều recipient, unprotected header, detached payload, b64: false và AAD riêng của JWE JSON thuộc các khả năng JOSE tổng quát hoặc phần mở rộng có ranh giới cụ thể. Hãy chọn một JWT profile rõ ràng, chỉ cho phép tính năng đã được quy định và từ chối mọi phần mở rộng không được hiểu hoặc không được phép.
