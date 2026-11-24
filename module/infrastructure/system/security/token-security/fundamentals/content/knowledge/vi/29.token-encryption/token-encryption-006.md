# Token size khi mã hóa

**Token size khi mã hóa** là bài toán ước lượng và kiểm soát **độ dài của security token sau khi đóng gói/mã hóa**, đặc biệt là **JSON Web Encryption (JWE)** được dùng để giữ bí mật claims trong JWT hoặc payload. Một token có vài trăm byte JSON có thể trở thành chuỗi hàng nghìn ký tự do **Base64url, JOSE header, khóa nội dung được mã hóa, IV/nonce, authentication tag, chữ ký lồng nhau và metadata chọn khóa**.

Bài học thuộc chương **Token encryption** của module **SECURITY_TOKEN_SECURITY_FUNDAMENTALS**, kết nối mô hình tin cậy và vòng đời token, JWT/opaque token, access/refresh/ID token, xác thực và phân quyền OAuth 2.0/OIDC, claims, scope, audience, lưu trữ, thu hồi và phòng chống token bị đánh cắp/phát lại.

**Nguyên tắc:** mã hóa **không phải cách giảm kích thước token**. JWE bảo vệ bí mật plaintext và integrity của ciphertext với thuật toán/khóa thích hợp; token sau serialization thường **lớn hơn**, và vẫn để lộ metadata cùng độ dài. Tối ưu bắt đầu bằng **giảm claims và chọn đúng token/transport architecture**, không phải cắt IV, tag hay signature.

## 1. “Kích thước token” là đại lượng nào?

| Phép đo | Ví dụ | Điểm cần nhớ |
|---|---|---|
| **Plaintext bytes** | Claims JSON UTF-8: 1.024 byte | Đầu vào thực của content encryption |
| **JWE Compact characters** | Chuỗi token dài 1.447 ký tự | Base64url, header, IV, tag, dấu chấm |
| **HTTP header bytes** | `Authorization: Bearer <JWE>` | Thêm tên header, Bearer scheme và cấu trúc HTTP |
| **Cookie bytes** | `__Host-session=<JWE>; ...` | Thêm cookie name, attributes và các cookies khác |
| **JSON response bytes** | `{"access_token":"..."}` | Thêm field names, quotes, metadata, escaping |
| **URI bytes** | URL có token trong query | Có thể tăng bởi encoding; **không nên đưa bearer token vào URL** |
| **Wire bytes** | HTTP/2 HPACK, HTTP/3 QPACK, TLS | Không xóa logical header/RS parsing limits |

`String.length()` trong Java đo **UTF-16 code units**, không phải UTF-8 bytes. JavaScript `text.length` cũng đo code units, còn `new TextEncoder().encode(text).length` đo bytes. JWE Compact chỉ chứa ký tự Base64url ASCII và dấu `.` nên **một ký tự JWE Compact bằng một byte khi encode chuỗi đó dưới UTF-8**, khác với JSON claims có Unicode.

**Đặt ngân sách theo cả token length, serialized HTTP field và giới hạn từng hop**, không chỉ dựa trên số ký tự của input JSON.

## 2. Encoding, signing và encryption khác nhau

| Cơ chế | Có giữ bí mật claims? | Thêm gì vào size? | Mục đích |
|---|---|---|---|
| **Base64url** | **Không** | Tăng khoảng 33% với dữ liệu lớn | Biểu diễn bytes bằng chữ URL-safe |
| **JWS/JWT có chữ ký** | **Không** | Header, chữ ký và 2 dấu chấm | Toàn vẹn, xác minh nguồn ký theo trust model |
| **JWE/JWT mã hóa** | **Có** với người không có key | Header, encrypted CEK, IV, tag, 4 dấu chấm | Confidentiality, ciphertext integrity |
| **Nested JWS → JWE** | **Có** ở lớp ngoài | Overhead của **cả JWS lẫn JWE** | Ẩn claims và verify issuer signature |
| **Opaque reference token** | Claims không có ngay trong token | Thường ngắn, tùy thiết kế AS | RS tra trạng thái/claims theo reference |

**JWT không mặc định là encrypted.** Signed JWT/JWS Compact có **ba segment** `header.payload.signature` và claims decode được. **JWE Compact có năm segment**. Một chuỗi có đủ số segment chỉ chứng minh cấu trúc sơ bộ, **không chứng minh token hợp lệ**.

## 3. Năm thành phần của JWE Compact

[RFC 7516](https://www.rfc-editor.org/rfc/rfc7516) định nghĩa chuỗi:

~~~text
BASE64URL(UTF8(protected_header))
.
BASE64URL(encrypted_key)
.
BASE64URL(initialization_vector)
.
BASE64URL(ciphertext)
.
BASE64URL(authentication_tag)
~~~

| Segment | Nội dung trước Base64url | Độ dài phụ thuộc |
|---|---|---|
| **1 — Protected header** | `alg`, `enc`, `kid`, `epk`, `cty`... | Header JSON đã serialize thành UTF-8 |
| **2 — Encrypted key** | Content Encryption Key (CEK) được encrypt/wrap | Có thể rỗng (`dir` hoặc `ECDH-ES` direct) hoặc lớn (RSA) |
| **3 — IV/nonce** | Initialization vector content-encryption | A256GCM thường 12 byte |
| **4 — Ciphertext** | Plaintext đã encrypt (hoặc byte nén nếu `zip`) | GCM không nén: cùng byte length với plaintext |
| **5 — Authentication tag** | AEAD/MAC tag | A256GCM thường 16 byte |

~~~mermaid
flowchart LR
    P["Claims JSON hoặc inner JWS"] --> UTF["UTF-8 bytes"]
    UTF --> ENC["Encrypt với Content Encryption Key"]
    IV["IV / nonce"] --> ENC
    ENC --> CT["Ciphertext"]
    ENC --> TAG["Authentication tag"]
    HEAD["Protected JOSE header"] --> OUT["5 Base64url segments + 4 dots"]
    KEY["Encrypted CEK hoặc empty"] --> OUT
    IV --> OUT
    CT --> OUT
    TAG --> OUT
~~~

**Segment #2 rỗng là hợp lệ** với `alg=dir` và `ECDH-ES` direct. Ví dụ cấu trúc `HEADER..IV.CIPHERTEXT.TAG` có **hai dấu chấm liên tiếp**. Không được bỏ hẳn segment đó vì JWE Compact vẫn luôn có **năm vị trí**.

**Chú ý:** JWE **JSON Serialization** có cấu trúc khác và có thể chứa nhiều recipients. Công thức năm phần chỉ áp dụng cho **Compact Serialization**.

## 4. Base64url không padding tăng kích thước thế nào?

Với `n` byte, Base64url không padding theo JOSE tạo `B(n)` ký tự:

\[
B(n)=4\left\lfloor\frac{n}{3}\right\rfloor+
\begin{cases}
0,& n\bmod 3=0\\
2,& n\bmod 3=1\\
3,& n\bmod 3=2
\end{cases}
\]

Điều này tương đương `ceil(4*n/3)` với `n` nguyên không âm; **không được dùng `4*ceil(n/3)`** (đó là số ký tự Base64 tính cả padding).

| `n` byte | `B(n)` ký tự | Ứng dụng |
|---:|---:|---|
| 0 | 0 | Encrypted key segment rỗng |
| 1 | 2 | Không còn `==` |
| 2 | 3 | Không còn `=` |
| 3 | 4 | Một nhóm Base64 đầy đủ |
| 12 | 16 | IV AES-GCM |
| 16 | 22 | Tag AES-GCM |
| 32 | 43 | Thumbprint/32-byte value |
| 40 | 54 | AES-KW wrap 32-byte CEK |
| 64 | 86 | Chữ ký ECDSA P-256 raw JOSE |
| 256 | 342 | RSA-2048 encrypted CEK/signature |
| 1.024 | 1.366 | Payload lớn |

**Không cộng raw bytes của năm segment rồi Base64url một lần.** JWE encode **mỗi segment riêng**; sai khác do rounding có thể làm công thức không chính xác, đặc biệt với payload nhỏ.

## 5. Công thức tổng độ dài JWE Compact

Đặt:

- `H` = protected header **UTF-8 bytes sau JSON serialization**.
- `K` = encrypted CEK bytes, **0** nếu key-management direct.
- `V` = IV bytes.
- `C` = ciphertext bytes.
- `T` = authentication-tag bytes.

Khi đó:

\[
\boxed{L_{\mathrm{JWE}}=B(H)+B(K)+B(V)+B(C)+B(T)+4}
\]

`+4` là **bốn dấu chấm**. Các số `H` và `K` phải dựa trên **thuật toán, key size, header thực**. Một thư viện JOSE có thể thêm `kid`/`cty`/`epk`/`zip` và thay đổi `H` ngay cả khi claims không đổi.

Với **A256GCM không nén**, cấu hình JOSE phổ biến có **IV 12 byte, tag 16 byte, ciphertext dài bằng plaintext bytes P**:

\[
L_{\mathrm{GCM}}=B(H)+B(K)+16+B(P)+22+4
\]

Hằng số `16`/`22` trong biểu thức này là **ký tự Base64url**, không phải IV/tag bytes. Nếu dùng `zip` hoặc algorithm block cipher có padding, **`C` không còn bằng `P`**.

## 6. Tính chính xác: alg=dir, enc=A256GCM

Giả sử JWE dùng direct key management `alg=dir` và A256GCM. Protected header được serializer tạo **compact không whitespace**:

~~~text
{"alg":"dir","enc":"A256GCM"}
~~~

Header này **29 byte UTF-8 → 39 ký tự Base64url**. Với `dir`, encrypted-key segment rỗng nên `K=0`. IV 12 byte → 16 ký tự; tag 16 byte → 22 ký tự.

Với plaintext `P` byte:

\[
L_{\mathrm{dir}}=39+0+16+B(P)+22+4
=\boxed{81+B(P)}
\]

**Ví dụ P = 1.024 byte:**

| Thành phần | Bytes trước encoding | Ký tự sau Base64url |
|---|---:|---:|
| Protected header | 29 | 39 |
| Encrypted CEK (`dir`) | 0 | 0 |
| IV | 12 | 16 |
| Ciphertext | 1.024 | 1.366 |
| Tag | 16 | 22 |
| Dấu chấm | — | 4 |
| **Tổng** | — | **1.447** |

Đây là **kết quả chính xác cho header và tham số cụ thể**, không phải mọi token A256GCM đều dài như vậy.

**Security caveat:** `dir` yêu cầu key trực tiếp phù hợp (ví dụ 256-bit cho A256GCM) được quản lý an toàn. IV/nonce **không được tái sử dụng với cùng key** trong AES-GCM. Giảm vài trăm ký tự bằng cách dùng key chia sẻ rộng rãi có thể làm xấu đi trust model giữa AS và Resource Server.

## 7. Tính chính xác: RSA-OAEP-256 + A256GCM, RSA 2048-bit

JWE có thể encrypt một CEK cho người nhận bằng **RSA public key**, còn payload do AES-GCM mã hóa. `RSA-OAEP-256` **không trực tiếp mã hóa cả token JSON**; nó encrypt CEK.

Header compact giả định:

~~~text
{"alg":"RSA-OAEP-256","enc":"A256GCM"}
~~~

Header **38 byte → 51 ký tự Base64url**. Với RSA modulus **2048-bit**, encrypted CEK là RSA ciphertext **256 byte → 342 ký tự**.

\[
L_{\mathrm{RSA2048}}=51+342+16+B(P)+22+4
=\boxed{435+B(P)}
\]

Với plaintext `P=1.024` byte, `B(P)=1.366`, nên tổng là **435 + 1.366 = 1.801 ký tự**.

| Segment | Ký tự |
|---|---:|
| Header | 51 |
| RSA-2048 encrypted CEK | 342 |
| IV | 16 |
| Ciphertext | 1.366 |
| Tag | 22 |
| 4 dấu chấm | 4 |
| **Tổng** | **1.801** |

RSA dài hơn ví dụ `dir` **354 ký tự**, nhưng hai cách **khác nhau về phân phối key và quyền của recipient**. Không nên chọn `dir` chỉ để giảm size nếu mỗi RS cần khóa giải mã riêng.

## 8. Bảng kích thước theo payload không nén

Giả định **đúng hai header ví dụ** ở mục 6–7, A256GCM IV 12B/tag 16B, RSA 2048-bit, không `kid`/`cty`/`zip`/nested JWS, `P` là UTF-8 bytes:

| Plaintext `P` (bytes) | `B(P)` | JWE `dir` (chars) | JWE RSA-2048 (chars) |
|---:|---:|---:|---:|
| 32 | 43 | 124 | 478 |
| 256 | 342 | 423 | 777 |
| 512 | 683 | 764 | 1.118 |
| 1.024 | 1.366 | 1.447 | 1.801 |
| 2.048 | 2.731 | 2.812 | 3.166 |
| 3.072 | 4.096 | 4.177 | 4.531 |
| 4.096 | 5.462 | 5.543 | 5.897 |

**Với payload lớn**, phần ciphertext Base64url chiếm ưu thế, tỷ lệ tăng gần 4/3. **Với payload nhỏ**, header/encrypted key/IV/tag là phần trăm overhead đáng kể. Bảng **không** chứng minh kích thước nào sẽ luôn vừa cookie/header ở từng hệ thống.

## 9. Key-management algorithm và chi phí encrypted CEK

| `alg` / giả định | Encrypted key segment | Chi phí khác cần tính |
|---|---|---|
| **`dir`** | Rỗng | Key sharing và IV uniqueness cần review |
| **`RSA-OAEP-256`, RSA-2048** | 256B → 342 chars | `kid` và các header khác |
| **`RSA-OAEP-256`, RSA-3072** | 384B → 512 chars | Lớn hơn, public/private-key policy riêng |
| **`A256KW` + A256GCM** | Wrap CEK 32B → **40B = 54 chars** | Bảo vệ Key Encryption Key (KEK) |
| **`ECDH-ES` direct** | Rỗng | `epk` public key trong header, có thể thêm `apu`/`apv` |
| **`ECDH-ES+A256KW`** | 40B → 54 chars | `epk` header **và** wrapped key |
| **`A256GCMKW`** | Wrapped CEK và thêm key-wrap IV/tag | IV/tag của key wrap thường nằm **trong header** |
| **`PBES2-HS256+A128KW`** | Wrapped CEK và PBES2 parameters | `p2s`/`p2c` tăng size; password/KDF policy |

**40-byte AES-KW** giả định CEK 32 byte cho `A256GCM`; content-encryption algorithm khác có CEK length khác. **ECDH-ES direct** có encrypted-key segment rỗng nhưng protected header chứa `epk`, nên không tự động ngắn hơn mọi cấu hình RSA. Phải đo **toàn bộ header được serialize**.

## 10. CBC-HMAC không dùng công thức ciphertext = plaintext

JOSE hỗ trợ content-encryption algorithms như `A128CBC-HS256` và `A256CBC-HS512`. Với AES-CBC + PKCS#7 padding, block size 16 byte:

\[
C_{\mathrm{CBC}}=16\left(\left\lfloor\frac{P}{16}\right\rfloor+1\right)
\]

**Ngay cả khi P là bội số 16, cần thêm một block padding**.

| `enc` | IV | Authentication tag | Ciphertext |
|---|---|---|---|
| **`A256GCM`** | 12B → 16 chars | 16B → 22 chars | `P` bytes nếu không nén |
| **`A128CBC-HS256`** | 16B → 22 chars | 16B → 22 chars | `16*(floor(P/16)+1)` bytes |
| **`A256CBC-HS512`** | 16B → 22 chars | 32B → 43 chars | `16*(floor(P/16)+1)` bytes |

Ví dụ header compact `{"alg":"dir","enc":"A128CBC-HS256"}` có **35B → 47 chars**. Với plaintext **1.024B**, CBC ciphertext **1.040B → 1.387 chars**. Tổng:

\[
47+0+22+1387+22+4=\boxed{1482}
\]

So với **1.447** của `dir+A256GCM` cùng plaintext, CBC-HMAC dài thêm **35 chars** trong ví dụ. **Không chọn thuật toán chỉ vì vài chục chars**; phải dựa crypto policy và thư viện chuẩn, không tự ráp AES-CBC/HMAC dễ phát sinh padding-oracle/validation errors.

## 11. Unicode, JSON escaping và claims làm byte length khó đoán

Ví dụ claims chứa tiếng Việt:

~~~json
{
  "sub": "u42",
  "aud": "orders-api",
  "name": "Nguyễn Ánh",
  "scope": "orders:read"
}
~~~

- ASCII thường chiếm **1 byte/ký tự**; nhiều ký tự Unicode có dấu chiếm 2–3 byte UTF-8; emoji thường 4 byte.
- Serializer có thể ghi Unicode trực tiếp hoặc escape một phần thành `\\uXXXX`; số byte khác.
- Pretty JSON thêm whitespace/indentation; compact JSON thường ngắn hơn.
- JSON object field name/order, arrays, UUIDs, resource/permission lists làm payload tăng.
- Java `String.length()` đo UTF-16 code units nên không dùng để suy JWE ciphertext length.

**Đo `json.getBytes(UTF_8).length` sau serialization thật**, không lấy số ký tự bản hiển thị. Không rút ngắn **tên claim chuẩn** như `iss`, `aud`, `exp` nếu điều đó làm sai JWT/OAuth/OIDC profile.

## 12. Nested JWS→JWE: cộng chi phí cả hai lớp

Khi cần **bí mật claims** và chứng minh **issuer đã ký**, có thể sign JWT thành JWS Compact, rồi encrypt **chính chuỗi JWS** thành JWE:

~~~mermaid
flowchart LR
    CLAIMS["Claims JSON P bytes"] --> SIGN["JWS Compact: header.payload.signature"]
    SIGN --> ENC["JWE: encrypt toàn bộ JWS Compact"]
    ENC --> RS["Recipient decrypt"]
    RS --> VERIFY["Verify JWS signature rồi validate claims"]
~~~

JWS Compact có **ba segments**, tức:

\[
L_{\mathrm{JWS}}=B(JH)+B(P)+B(S)+2
\]

`JH` = JWS protected-header bytes, `P` = claims bytes, `S` = signature bytes. Với JWS RS256/RSA-2048, signature 256B → 342 chars. Giả sử header compact:

~~~text
{"alg":"RS256","typ":"at+jwt"}
~~~

Header có **30B → 40 chars**. Nếu claims `P=1.024B`:

\[
L_{\mathrm{JWS}}=40+1366+342+2=\boxed{1750}
\]

Outer JWE `dir+A256GCM` có header compact:

~~~text
{"alg":"dir","enc":"A256GCM","cty":"JWT"}
~~~

Header **41B → 55 chars**, ciphertext plaintext là **JWS Compact 1.750 ASCII bytes → 2.334 Base64url chars**:

\[
L_{\mathrm{nested,dir}}=55+0+16+2334+22+4=\boxed{2431}
\]

Outer `RSA-OAEP-256+A256GCM` với header:

~~~text
{"alg":"RSA-OAEP-256","enc":"A256GCM","cty":"JWT","kid":"as-k-2026"}
~~~

Header **68B → 91 chars**, encrypted CEK 342 chars, nên:

\[
L_{\mathrm{nested,RSA}}=91+342+16+2334+22+4=\boxed{2809}
\]

| Biểu diễn cùng claims gốc 1.024B | Size minh họa |
|---|---:|
| Claims JSON raw | 1.024 bytes |
| JWE `dir+A256GCM` (không nested) | 1.447 chars |
| JWE RSA-OAEP-256/RSA-2048 (không nested) | 1.801 chars |
| JWS RS256/RSA-2048 | 1.750 chars |
| **Nested JWS→JWE dir** | **2.431 chars** |
| **Nested JWS→JWE RSA-2048** | **2.809 chars** |

**Cảnh báo:** các con số giả định **chính xác header compact ví dụ**, signature size và không nén. Với `kid`, `epk`, key size khác hoặc JSON escape khác, phải tính lại.

**Không phải mọi JWE bắt buộc lồng JWS**. Nhưng với RSA public-key JWE, **bất kỳ ai giữ public key recipient đều có thể encrypt JWE cho recipient**, nên decrypt/tag thành công **không tự xác minh issuer là AS**. Inner signed JWS hoặc trust mechanism được thiết kế đúng sẽ bảo vệ issuer authenticity khi cần.

## 13. Header metadata có thể làm JWE nở lớn

Header cơ bản `{"alg":"dir","enc":"A256GCM"}` là **29B**, nhưng production có thể thêm:

~~~json
{
  "alg": "dir",
  "enc": "A256GCM",
  "kid": "key-rotation-2026-11",
  "cty": "JWT",
  "typ": "JWT"
}
~~~

Các field ảnh hưởng `H`:

- `kid` chọn khóa, **không phải secret**, có thể dài nếu tên khóa/certification path dài.
- `cty` mô tả content, thường `JWT` trong nested JWS→JWE.
- `typ` phân biệt token/object type ở layer phù hợp; không thay token-purpose validation.
- `epk` (ECDH-ES) chứa ephemeral public-key JWK (`kty`, `crv`, `x`, `y`), có thể thêm hàng trăm ký tự.
- `apu`/`apv`, `p2s`/`p2c`, `iv`/`tag` cho key wrap, certificate references `x5c`... đều tăng size.
- `zip` thêm compression metadata và đổi length của ciphertext sau nén.

**Protected JWE header chỉ Base64url-encode, không encrypt.** Người nhìn thấy JWE có thể đọc `alg`, `enc`, `kid` và metadata trong protected header. Không đưa email, PII, access token/refresh token hay credential khác vào header tùy ý.

## 14. Compression zip=DEF: đôi khi giảm size, nhưng tăng rủi ro side channel

JWE cho phép tùy chọn `zip` trong protected header; giá trị chuẩn thường gặp là **`DEF`**. Compression diễn ra **trước content encryption**, nên:

~~~text
JSON claims hoặc nested JWS
    |
    +-- (Optional) DEFLATE -> compressed bytes P'
    |
    +-- Content encryption -> ciphertext C=P' với GCM
    |
    +-- Base64url từng segment -> JWE Compact
~~~

Khi payload nén từ `P` xuống `P'` byte:

\[
L_{\mathrm{zip+GCM}}=B(H_{\mathrm{zip}})+B(K)+16+B(P')+22+4
\]

**Không thể suy `P'` chỉ từ `P` bằng một hệ số cố định.** JSON lặp có thể nén mạnh; ciphertext-looking data, các giá trị ngẫu nhiên hoặc plaintext quá nhỏ có thể **không giảm, thậm chí tăng**. Header thêm `zip` cũng làm `H` lớn hơn.

### Rủi ro compression length oracle

Kẻ tấn công có thể kiểm soát một phần plaintext được nén **cùng bí mật** (token, session secrets hoặc PII), yêu cầu hệ thống phát nhiều ciphertext, sau đó quan sát **sự thay đổi độ dài**. Dù ciphertext không đọc được, length pattern có thể rò thông tin qua compression side channel.

**Không bật `zip=DEF` mặc định chỉ để ép token vừa cookie/header**. Cần threat model cho input attacker-controlled, secret co-compression, số lần quan sát, URL/header transport và các biện pháp giảm rủi ro. Mã hóa **không xóa độ dài bản mã khỏi thứ mà người ngoài có thể đo**.

## 15. JWE JSON Serialization và nhiều recipients

**JWE General JSON Serialization** có thể chứa nhiều recipients để các bên nhận khác nhau giải cùng ciphertext qua encrypted CEK riêng:

~~~json
{
  "protected": "<BASE64URL_PROTECTED_HEADER>",
  "iv": "<BASE64URL_IV>",
  "ciphertext": "<BASE64URL_CIPHERTEXT>",
  "tag": "<BASE64URL_TAG>",
  "recipients": [
    {
      "header": { "kid": "rs-a" },
      "encrypted_key": "<BASE64URL_CEK_FOR_A>"
    },
    {
      "header": { "kid": "rs-b" },
      "encrypted_key": "<BASE64URL_CEK_FOR_B>"
    }
  ]
}
~~~

Đây là **cấu trúc JSON minh họa**, placeholders không phải token có thể decrypt thật.

| Thành phần | Sizing consequence |
|---|---|
| `protected` | Base64url của shared protected header |
| `unprotected` hoặc recipient `header` | Plain JSON bytes trong envelope |
| `iv`, `ciphertext`, `tag` | Có thể dùng chung cho recipients |
| `recipients[]` | Mỗi recipient thêm JSON object/header/encrypted key |
| JSON wrapper/whitespace | Field names, dấu nháy, dấu phẩy, brackets |
| Outer API JSON response | Có thể còn một lớp serialize/escaping khác |

**Không dùng công thức năm segment của JWE Compact để tính JWE JSON**. Phải serialize envelope thật thành UTF-8, đo byte length và test number of recipients thực tế. Một ciphertext dùng chung không đồng nghĩa overhead recipients bằng 0.

## 16. HTTP Authorization header và giới hạn gateway

Access token thường được gửi tới Resource Server bằng:

~~~http
GET /orders/123 HTTP/1.1
Host: orders-api.example.test
Authorization: Bearer <JWE_COMPACT_TOKEN>
Accept: application/json
~~~

Token dài làm tăng kích thước header. Trên đường đi, mỗi thành phần có thể áp dụng giới hạn **riêng**:

- Một header value hoặc header field.
- Tổng số và tổng bytes các headers.
- HTTP/2/HTTP/3 **header list size sau giải nén**.
- Upstream reverse proxy, API gateway, CDN, WAF, load balancer.
- Servlet container/Java framework, gRPC gateway, service mesh.

**Không có một ngưỡng chung 8 KB/16 KB/32 KB áp dụng cho mọi hạ tầng.** Khi vượt hạn mức, có thể trả **431 Request Header Fields Too Large**, 400, đôi khi 413, đóng kết nối hoặc lỗi gateway riêng tùy implementation. Không phải tất cả tình huống đều báo 431.

### HPACK/QPACK có khiến JWE “nhỏ” đi không?

HTTP/2 HPACK và HTTP/3 QPACK có thể nén một phần representation trên wire, nhưng:

- Proxy vẫn xử lý **giá trị logical headers**, và có thể enforce size sau decompression.
- Header `Authorization` có giá trị bí mật, cần tránh indexing/caching gây rò.
- RS phải parse/decrypt **toàn bộ token**.
- Chi phí log, memory, crypto và framework vẫn tồn tại.

**Không chọn JWE quá lớn vì hy vọng HTTP/2 sẽ tự xử lý.** Đo header budgets trên **toàn đường** client → CDN → gateway → app.

## 17. Cookie 4 KB: mức tham khảo, không phải cam kết toàn cầu

Một số ứng dụng lưu session/token trong cookie:

~~~http
Set-Cookie: __Host-session=<ENCRYPTED_SESSION>; Path=/; Secure; HttpOnly; SameSite=Lax
~~~

Nhiều browser áp dụng giới hạn gần **4 KB mỗi cookie**, nhưng giới hạn cụ thể, cách tính kích thước, số cookie và chính sách eviction khác nhau. Ngoài token còn có:

- Cookie name + dấu `=`.
- Cookie attributes và phạm vi domain/path.
- Các cookie khác cùng đi trong request `Cookie`.
- HTTP headers khác, limits của proxy/web server.
- SameSite/Secure/HttpOnly requirements.

**Token 4.000 ký tự không bảo đảm vừa một cookie 4 KB**. Và browser lưu cookie được không có nghĩa gateway chịu được toàn bộ `Cookie` header khi hàng chục cookie cùng gửi.

Ví dụ JWE `dir+A256GCM` không nén với `P=3.072B` theo bảng trên dài **4.177 ký tự**, **chưa có tên/attributes cookie**. Đây là dấu hiệu nên đổi kiến trúc hoặc giảm claims.

### Kiến trúc thường hợp lý

Với **BFF/server-side session**, lưu token OAuth/JWE ở server-side store và chỉ gửi **opaque session identifier ngắn** qua cookie. Cookie nên có `Secure`, `HttpOnly`, `SameSite` thích hợp; ứng dụng cookie-authenticated vẫn phải có CSRF protection. Không chuyển refresh token vào cookie JavaScript-readable chỉ vì JWE đã che claims.

**Không cắt JWE thành nhiều cookie** nếu chưa có protocol an toàn bảo đảm thứ tự, toàn vẹn, replay resistance, atomic reassembly, expiry và cleanup. Chia cookie thường chỉ làm vấn đề quản lý phiên trở nên phức tạp hơn.

## 18. Token dài không phải lý do chuyển sang query/path/fragment

Không biến API thành:

~~~text
GET /orders?access_token=<JWE_TOKEN>   # KHÔNG LÀM
~~~

Dù ciphertext không đọc trực tiếp được, **cả JWE bearer token vẫn là credential có thể bị sao chép để replay** nếu thiếu sender binding. URL có thể lọt vào reverse proxy/CDN logs, browser history, analytics, cache, link sharing hoặc HTTP `Referer` (tùy policy), và fragment có thể bị JavaScript/telemetry/history đọc.

**Base64url URL-safe chỉ nói chuỗi token dễ đặt trong URL về mặt cú pháp**, không có nghĩa việc đưa credential vào URL là bảo mật.

Không chuyển bearer token thành HTTP GET query hoặc custom form body chỉ để vượt giới hạn Authorization header. `RFC 6750` ưu tiên bearer token trong Authorization header; các phương thức khác có điều kiện sử dụng chặt và thêm rủi ro transport/logging.

Nếu header token quá lớn: **giảm claims, dùng BFF/reference token hoặc thay đổi token profile**. Điều chỉnh gateway limit chỉ khi threat model và sản phẩm thật sự yêu cầu, có headroom/rate limits hợp lý.

## 19. Tối giản claims trước khi mã hóa

Size giảm bền vững nhất bằng cách bỏ dữ liệu **không cần thiết cho quyết định security tại recipient**.

| Claim/data | Có cần trong token? | Cách xử lý |
|---|---|---|
| `iss`, `aud`, `sub`, `exp`, `iat`, `jti` | Theo JWT/token profile | Giữ trường bắt buộc, validate đúng semantics |
| `scope` hoặc `scp` | Khi AS/RS contract cần | Chỉ scope được cấp, không sao chép mọi permission |
| `tenant_id` | Khi RS cần tenant isolation | Dùng định danh có nghĩa rõ, không serialize toàn tenant object |
| Vài roles/entitlements | Có thể, nếu scope phù hợp | Tránh role tree/permission tree khổng lồ |
| Danh sách hàng nghìn object IDs | **Thường không** | RS kiểm tra object-level ACL bằng service/DB |
| Email/phone/address/PII | Hạn chế theo data minimization | Truy xuất từ profile server khi thực sự cần |
| Avatar, UI preferences, locale, debug | Thường **không** cho AT | Gửi qua endpoint user profile |
| Full user object/serialized Java entity | **Không** | Rủi ro rò PII, nặng và stale |
| Password/RT/secret khác | **Tuyệt đối không** | Không lồng credential bí mật vào claims |

Đừng tự đổi `exp` thành `e` hay `aud` thành `a` để tiết kiệm vài bytes nếu phá chuẩn. Với API cần quá nhiều quyền động, cân nhắc **opaque reference token + introspection** hoặc JWT tối giản và RS tra chính sách.

### Claims lớn gây lỗi vận hành ngoài size

Token chứa permission tree lớn dễ **stale** khi quyền thay đổi, tăng thời gian crypto, gây khó khăn thu hồi và phát tán PII. **Scope không thay object-level authorization**: user có `orders:read` vẫn không tự có quyền đọc order của tenant khác.

## 20. Chọn opaque, JWS hay JWE theo trust model

| Tiêu chí | Opaque reference AT | JWS access JWT | JWE encrypted JWT |
|---|---|---|---|
| Claims nhìn thấy trong token | Không chứa trực tiếp | Decode được | Cần decrypt key |
| Size | Thường ngắn, tùy AS | Header + payload + signature | 5 segments + crypto overhead |
| RS xử lý | Introspection/lookup tin cậy | Verify signature, issuer/aud/exp/scope | Decrypt, verify issuer/authenticity/claims; JWS inner nếu profile dùng |
| Thu hồi | AS trạng thái, cache có delay | Denylist/short TTL/AS state nếu cần | Tương tự JWT, encryption **không tự revoke** |
| Key management | AS/RS introspection credentials | Signing JWKS/public keys | Private decryption keys, key distribution, rotation |
| Khi phù hợp | Giảm claims lộ, muốn state lookup | Offline verification và RS tin cậy | Cần giấu claims khỏi holder/intermediary |

**Mã hóa không phải mặc định bắt buộc của access token**. Với OAuth 2.0/OIDC, **signed JWT access token** đã đủ cho nhiều trust models khi API được phép xem claims; JWE chỉ cần khi confidentiality tới recipient là yêu cầu thực. Opaque token có thể giảm size và cải thiện centralized revocation visibility nhưng thêm network/AS dependency.

## 21. Decrypt thành công không đồng nghĩa token do issuer hợp lệ cấp

JWE bảo vệ ciphertext integrity dưới CEK, nhưng **ai có thể tạo JWE hợp lệ** phụ thuộc key distribution:

- Với **RSA public-key encryption**, **bất kỳ ai có public key recipient** đều có thể encrypt dữ liệu cho recipient. Decrypt/tag success **không tự chứng minh Authorization Server đã phát hành token**.
- Với `alg=dir`, các bên giữ **cùng symmetric key** đều có thể tạo ciphertext; recipient giữ key có thể không phân biệt nguồn tạo chỉ từ GCM tag.
- Một inner **JWS ký bởi issuer** (sign-then-encrypt) có thể được recipient verify sau decrypt; hoặc hệ thống có cơ chế authentication nguồn phát khác đã threat-model đúng.
- Recipient vẫn phải kiểm tra `iss`, `aud`, `exp`/`nbf`, token type/usage, scope và object/tenant ACL.

**Không tự viết JWT/JWE decryption parser** bằng cách decode Base64url rồi cho phép truy cập. Thư viện được bảo trì phải enforce allowlist `alg`/`enc`, key type, authenticated encryption/tag, nested JWS verification và claims.

**Không tin remote key URLs từ JOSE header** như `jku`/`x5u` nếu URL không đến từ metadata/key configuration đáng tin, vì có thể dẫn tới SSRF hoặc token forgery.

## 22. IV/nonce uniqueness, tag integrity và length side channel

**Không cắt IV hoặc authentication tag để token ngắn hơn.**

### AES-GCM IV uniqueness

- A256GCM trong JOSE thường dùng 96-bit IV (12 bytes). **Không được reuse IV dưới cùng CEK**.
- Với `dir` và key tồn tại lâu qua nhiều nodes/regions, cần quản lý nonce uniqueness phù hợp; random IV 96-bit cần quan tâm collision risk/budget, đặc biệt khi phát hành rất nhiều tokens.
- Không chỉ dùng timestamp hoặc counter cục bộ dễ trùng sau crash/restart/backup restore.
- Không tự gắn `jti` làm IV trừ khi có bảo đảm uniqueness mật mã/toàn cục và thư viện/profile hỗ trợ.
- Với CEK mới cho mỗi JWE, vẫn dùng JOSE library đúng chuẩn và không suy rằng tag/IV là tùy chọn.

### Ciphertext length cũng có thể rò thông tin

Người không có key vẫn có thể quan sát **chiều dài token**, protected header `alg`/`enc`/`kid`, tần suất phát token và request pattern. Nếu payload length liên quan roles, account type hoặc secret, length khác nhau có thể gây **length side channel**. Với `zip`, rủi ro càng lớn nếu attacker kiểm soát một phần plaintext được nén cùng secret.

Giảm bề mặt: payload shape ổn định theo policy, không nén chung attacker input+secret, rate limit issuance, không log raw JWE, cân nhắc padding ở lớp thích hợp khi threat model yêu cầu. **Padding luôn tăng size**; nó cần được cân nhắc chứ không phải giải pháp chung.

## 23. Hiệu năng, throughput và sizing budget

JWE lớn tác động tới:

- **Network bandwidth** vì token gửi mỗi request.
- **Header parsing/buffer** ở CDN, gateway, servlet container và HTTP client.
- **CPU** encrypt/decrypt AES-GCM; RSA-OAEP/ECDH key management; nested JWS signature verification.
- **Memory/GC** do nhiều bản sao string và buffers trong Java hoặc browser.
- **Mobile/IoT** có băng thông, CPU/pin và RAM hạn chế.
- **Observability**: nếu log/tracing vô tình thu thập Authorization/Cookie headers, vừa tốn storage vừa rò bearer credential.
- **Operational changes**: thêm `kid`, claims, tenant fields hoặc xoay key size có thể đẩy token vượt limit.

Nên định nghĩa **budget riêng** cho kích thước token và toàn bộ transport:

~~~text
JWE token target: <= 2000 ASCII chars (project-specific policy)
Authorization header value: "Bearer " + JWE
Other auth/trace/request headers: phải đo thực tế
Gateway/header-list limits: xác nhận trên từng hop
Headroom: theo SLO và config, không có con số RFC chung
~~~

Đây là **ngân sách minh họa**, không phải ngưỡng do RFC 7516 quy định. Nếu vượt, ưu tiên **bỏ claims, dùng opaque/BFF hoặc đổi cơ chế token**; không bỏ chữ ký, cắt tag hoặc ép compression một cách không kiểm toán.

## 24. Java 17: estimator JWE Compact size

Estimator chỉ tính **số ký tự lý thuyết** dựa trên serialized header bytes, ciphertext length, CEK/IV/tag. Nó **không tạo khóa, mã hóa, verify hay phát token**.

~~~java
import java.nio.charset.StandardCharsets;

public final class JweSizeEstimator {
    private JweSizeEstimator() {}

    private static final String DIR_GCM_HEADER =
            "{\"alg\":\"dir\",\"enc\":\"A256GCM\"}";
    private static final String RSA_GCM_HEADER =
            "{\"alg\":\"RSA-OAEP-256\",\"enc\":\"A256GCM\"}";
    private static final String NESTED_DIR_HEADER =
            "{\"alg\":\"dir\",\"enc\":\"A256GCM\",\"cty\":\"JWT\"}";
    private static final String JWS_RS256_HEADER =
            "{\"alg\":\"RS256\",\"typ\":\"at+jwt\"}";

    public static long base64urlLength(long byteCount) {
        if (byteCount < 0) {
            throw new IllegalArgumentException("Negative byte count");
        }
        long groups = Math.multiplyExact(byteCount / 3L, 4L);
        long tail = switch ((int) (byteCount % 3L)) {
            case 0 -> 0L;
            case 1 -> 2L;
            default -> 3L;
        };
        return Math.addExact(groups, tail);
    }

    public static long compactJwe(
            long headerBytes, long encryptedKeyBytes,
            long ivBytes, long ciphertextBytes, long tagBytes
    ) {
        long length = 4L; // Four separators
        for (long n : new long[] {
                headerBytes, encryptedKeyBytes,
                ivBytes, ciphertextBytes, tagBytes
        }) {
            length = Math.addExact(length, base64urlLength(n));
        }
        return length;
    }

    private static long utf8Bytes(String text) {
        return text.getBytes(StandardCharsets.UTF_8).length;
    }

    public static long dirGcm(String plaintext) {
        return compactJwe(
                utf8Bytes(DIR_GCM_HEADER), 0L,
                12L, utf8Bytes(plaintext), 16L
        );
    }

    public static long rsa2048Gcm(String plaintext) {
        return compactJwe(
                utf8Bytes(RSA_GCM_HEADER), 256L,
                12L, utf8Bytes(plaintext), 16L
        );
    }

    public static long nestedRs256DirGcm(long claimsJsonBytes) {
        long headerAndPayload = Math.addExact(
                base64urlLength(utf8Bytes(JWS_RS256_HEADER)),
                base64urlLength(claimsJsonBytes)
        );
        long innerJwsLength = Math.addExact(
                headerAndPayload,
                Math.addExact(base64urlLength(256L), 2L)
        );
        // JWS Compact contains ASCII characters only.
        return compactJwe(
                utf8Bytes(NESTED_DIR_HEADER), 0L,
                12L, innerJwsLength, 16L
        );
    }

    public static void main(String[] args) {
        // ASCII string: exactly 1024 UTF-8 bytes.
        String payload = "A".repeat(1024);

        System.out.println(dirGcm(payload));          // 1447
        System.out.println(rsa2048Gcm(payload));      // 1801
        System.out.println(nestedRs256DirGcm(1024L)); // 2431

        String unicode = "{\"name\":\"Nguyễn Ánh\"}";
        System.out.println("UTF-8 bytes: " + utf8Bytes(unicode));
        System.out.println("dir JWE chars: " + dirGcm(unicode));
    }
}
~~~

### Điều estimator không làm

1. Header được giả định **chính xác các compact JSON strings** nêu ở đầu code; thư viện thật có thể thêm `kid`/`cty`/metadata.
2. RSA encrypted-key size 256B **chỉ** đúng RSA-2048, không đúng RSA-3072/ECDH/AES-KW.
3. A256GCM IV/tag và `C=P` giả định **không nén**, profile GCM như ví dụ.
4. Nested JWS giả định RS256 RSA-2048 signature **256B**, claims bytes đã biết, inner header 30B.
5. `utf8Bytes` đo input string; app thật phải đo **kết quả của JSON serializer**, không text hiển thị.
6. `Math.addExact`/`Math.multiplyExact` xử lý overflow của estimator; API thật cần **giới hạn network payload/token length** trước khi decrypt.
7. Không thay JOSE library cho key generation, encryption, tag verify, signature verify, issuer/audience/expiry/scope validation.

**Độ dài thực của JWE Compact phải được đo sau JOSE library serialize**. Estimator phù hợp kiểm tra giả định, budget và regression, không chứng minh giao thức triển khai an toàn.

## 25. Ma trận kiểm thử kích thước và bảo mật

~~~mermaid
flowchart TD
    A["Sinh test claims giả như production"] --> B["Serialize JSON và đo UTF-8 bytes"]
    B --> C["JWS sign nếu cần"]
    C --> D["JWE encrypt bằng JOSE library trong staging"]
    D --> E["Đo Compact length và mọi segments"]
    E --> F["Đóng gói vào Authorization/Cookie/JSON"]
    F --> G["Test qua browser/CDN/gateway/backend thật"]
    G --> H{"Budget và crypto/token-policy tests PASS?"}
    H -->|"Có"| OK["Cho phép deployment theo SLO"]
    H -->|"Không"| FIX["Giảm claims/đổi architecture hoặc chỉnh policy"]
    FIX --> A
~~~

| Test | Đầu vào/thao tác | Kết quả mong đợi |
|---|---|---|
| **T1 — Empty segment** | JWE `alg=dir` | Vị trí #2 rỗng nhưng đủ 5 segments |
| **T2 — B64 0 byte** | `n=0` | `B(n)=0` |
| **T3 — B64 1 byte** | `n=1` | `B(n)=2` |
| **T4 — B64 2 byte** | `n=2` | `B(n)=3` |
| **T5 — B64 3 byte** | `n=3` | `B(n)=4` |
| **T6 — GCM IV** | 12B IV | 16 Base64url chars |
| **T7 — GCM tag** | 16B tag | 22 Base64url chars |
| **T8 — dir 1024B** | Header 29B, P=1024B | 1.447 JWE chars |
| **T9 — RSA 1024B** | Header 38B, RSA-2048 | 1.801 JWE chars |
| **T10 — RSA modulus** | Thay RSA-2048 bằng RSA-3072 | Encrypted CEK 256→384B |
| **T11 — AES-KW** | Wrap CEK 32B bằng `A256KW` | Encrypted CEK 40B → 54 chars |
| **T12 — CBC full block** | P=1.024B | Ciphertext 1.040B |
| **T13 — CBC non-block** | P=1.025B | Padding đến block length phù hợp |
| **T14 — JWS** | RS256 RSA-2048, P=1024B | JWS 1.750 chars theo header demo |
| **T15 — Nested dir** | JWS T14, outer header 41B | JWE 2.431 chars |
| **T16 — Nested RSA** | JWS T14, outer header 68B | JWE 2.809 chars |
| **T17 — Unicode** | Claims có dấu/emoji | Đo UTF-8 bytes, không đo JS/Java length |
| **T18 — JSON serialization** | Pretty vs compact/escaped | Kết quả size đúng bytes đã serialize |
| **T19 — Added kid** | Tăng độ dài `kid` | Header Base64url và JWE size tăng |
| **T20 — ECDH epk** | ECDH-ES public `epk` | Đo full protected header |
| **T21 — ZIP compression** | `zip=DEF` với JSON lặp | Có thể giảm nhưng chỉ bật qua security review |
| **T22 — Incompressible** | Dữ liệu random/short | Có thể tăng size |
| **T23 — JWE JSON** | General Serialization 2 recipients | Không dùng 5-part formula |
| **T24 — Cookie size** | JWE + name/attributes | Browser/gateway chấp nhận hoặc fail đúng policy |
| **T25 — Cookie aggregate** | Nhiều cookie cùng request | Tổng Cookie header dưới giới hạn |
| **T26 — Authorization field** | Bearer JWE qua gateway | Không bị cắt/truncate hoặc lỗi 431/400 |
| **T27 — Limit boundary** | Token gần/vượt header size config | Đo failure code, logging và headroom |
| **T28 — Header compression** | HTTP/2/3 | Không dựa wire compression để bypass limits |
| **T29 — URI misuse** | Đưa test bearer token vào URL | Phát hiện/phòng rò và policy chặn |
| **T30 — Inner signature** | JWE decrypt thành JWS ký sai | RS từ chối |
| **T31 — Wrong alg/enc** | JOSE header ngoài allowlist | RS từ chối |
| **T32 — Tamper** | Đổi một byte ciphertext/tag | Tag/decrypt thất bại |
| **T33 — Audience** | JWE hợp lệ nhưng `aud` sai | RS từ chối |
| **T34 — Expiry** | Claims `exp` quá hạn | RS từ chối |
| **T35 — Token-purpose confusion** | Encrypted ID token được gửi như access token | API từ chối |
| **T36 — Revocation** | JWT/JWE đã revoke nhưng chưa `exp` | RS tuân revoke/introspection/denylist architecture |
| **T37 — Nonce reuse** | Cố ý gây trùng IV khi test | Không cho production key/nonce lifecycle không an toàn |
| **T38 — Key rotation** | `kid` thay đổi | Chọn đúng trusted key, không fetch arbitrary URLs |
| **T39 — Compression side channel** | Attacker thay input bên cạnh secret | Review/chặn quan sát có rủi ro |
| **T40 — Log canary** | JWE giả vào gateway/APM/tracing | Không lộ token, key, Authorization/Cookie |
| **T41 — Byte boundaries** | P=0,1,2,3,15,16,17,1024,4096B | Estimator trùng real JOSE output theo profile |
| **T42 — Entitlements lớn** | Nhiều roles/tenant/resource IDs | Token giảm claims hoặc đổi architecture |

**Chạy cả size tests và security tests.** Một token vừa 2 KB vẫn có thể không an toàn nếu recipient chấp nhận JWT giả, sai `aud`, thiếu `exp` hoặc dùng ID token như API access token. Sử dụng **mock/staging/canary**, không đưa key hoặc bearer credential production vào HAR/CI logs.

## 26. Những hiểu lầm thường gặp

**“Mã hóa giúp token ngắn hơn.”** Sai. A256GCM ciphertext không nén có độ dài byte gần plaintext, cộng Base64url, header, IV, tag và encrypted CEK.

**“JWE có 5 phần đều không rỗng.”** Sai. Với `dir` hoặc ECDH-ES direct, encrypted key segment rỗng.

**“JWT luôn có 3 phần.”** Sai. JWS Compact 3; JWE Compact 5; nested có nhiều lớp.

**“A256GCM biến 1 KB data thành 256 bytes.”** Sai. 256 là **bit length của key**; không phải byte length của ciphertext.

**“RSA-OAEP mã hóa trực tiếp toàn bộ JWT.”** Sai. JWE mã hóa CEK bằng RSA, mã hóa payload bằng content encryption.

**“Base64url length = 4*ceil(n/3).”** Sai. Công thức đó tính padding; JOSE bỏ `=`.

**“JWE size = Base64url(header+ciphertext).”** Sai. Có 5 segments riêng biệt và bốn dấu chấm.

**“Protected header đã được mã hóa.”** Sai. Protected header **integrity-protected** nhưng vẫn đọc được `alg`/`kid`.

**“Bật zip luôn nhỏ hơn và an toàn hơn.”** Sai. Có thể phình size và tạo compression length side channel.

**“Một cookie luôn chứa đủ 4.096 ký tự token.”** Sai. Name/attributes, browser/proxy/aggregate limits thay đổi.

**“HTTP/2 nén headers nên không có giới hạn header.”** Sai. Logical headers và backend limits vẫn tồn tại.

**“JWE trong URL an toàn vì claims đã mã hóa.”** Sai. Với bearer credential, attacker chỉ cần sao chép nguyên token để replay.

**“Decrypt thành công nghĩa issuer là AS.”** Sai nếu public-key encryption cho phép bất kỳ ai encrypt; cần xác minh nguồn phát phù hợp.

**“Encrypted JWT không cần revoke.”** Sai. Encrypted JWT vẫn có TTL, audience, scope và revoke/rotation policy như token khác.

## 27. Checklist triển khai và tài liệu tham khảo

1. **Chọn đúng token format**: opaque, JWS, JWE Compact/JSON hay nested JWS→JWE.
2. **Đo raw claims UTF-8 bytes thực** sau serialization, không dùng Java/JS `length` cho Unicode.
3. **Áp dụng `B(n)` Base64url không padding**, tính từng segment độc lập.
4. **Tính đủ H, K, IV, ciphertext, tag và bốn dấu chấm** cho JWE Compact.
5. **Đo header thật**: `alg`/`enc`/`kid`/`epk`/`cty`/`zip`, không đo template thiếu metadata.
6. **Dùng content-encryption đúng profile**: GCM `C=P` nếu không nén; CBC có padding và tag khác.
7. **Tính nested JWS trước**, dùng JWS Compact ASCII string làm plaintext JWE.
8. **Chọn RSA/dir/ECDH/AES-KW theo trust model**, không chỉ theo token length.
9. **Không cắt IV/tag, không reuse nonce**, không dùng key/password yếu.
10. **Không xem JWE decrypt/tag thành công là issuer authentication**: verify signature/trust và claims.
11. **Tối giản claims**, bỏ PII/debug/resource lists; giữ field bắt buộc của token profile.
12. **Review `zip`** trước khi dùng, nhất là secret + attacker-controlled plaintext.
13. **Đặt budgets riêng cho Authorization header, cookie, JSON response, gateway và browser**.
14. **Kiểm tra toàn bộ proxy chain và HTTP versions**, không dựa một con số header/cookie chung.
15. **Không đưa bearer token vào URL** để né giới hạn.
16. **Ưu tiên BFF + opaque session cookie** nếu browser không cần đọc OAuth tokens.
17. **Cân nhắc opaque AT/introspection** khi JWE quá lớn hoặc không cần self-contained claims.
18. **Dùng JOSE library được bảo trì**, không tự viết cryptography/JWE parser.
19. **Validate token sau decrypt**: `iss`, `aud`, `exp`, `nbf`, type/purpose, scope, proof và object ACL.
20. **Thiết kế revoke riêng** cho JWT/JWE/opaque, lưu ý cached introspection hoặc offline JWT.
21. **Đo token phát hành thật bằng JOSE library**, so với estimator ở dữ liệu biên và Unicode.
22. **Test key rotation, nested signature, malformed/tampered JWE và algorithm confusion**.
23. **Quan sát kích thước p50/p95/p99**, các lỗi 431/400/414, latency/CPU/memory mà không log raw credentials.
24. **Chốt budget theo SLO và security policy**, không hy sinh crypto để giảm vài trăm ký tự.

**Kết luận:** kích thước JWE Compact được quyết định bởi **năm segment Base64url riêng biệt**: header, encrypted key, IV, ciphertext và tag. Với một plaintext **1.024 byte**, ví dụ đã tính **1.447 ký tự** cho `dir+A256GCM` và **1.801 ký tự** cho `RSA-OAEP-256+A256GCM` với RSA-2048; nested JWS→JWE có thể tăng lên **2.431–2.809 ký tự** theo header cụ thể. Giải pháp tốt là **đo chính xác serializer/JOSE output, giảm claims, chọn đúng token architecture và kiểm thử transport limits**, không phải giảm IV/tag, bỏ chữ ký hoặc truyền token qua URL.

### Tài liệu tiêu chuẩn

- [RFC 7516 — JSON Web Encryption (JWE)](https://www.rfc-editor.org/rfc/rfc7516): Compact/JSON Serialization, protected header, encrypted key, IV, ciphertext, tag và `zip`.
- [RFC 7518 — JSON Web Algorithms (JWA)](https://www.rfc-editor.org/rfc/rfc7518): `dir`, RSA-OAEP, ECDH-ES, AES-KW, A256GCM và CBC-HMAC.
- [RFC 7515 — JSON Web Signature (JWS)](https://www.rfc-editor.org/rfc/rfc7515): 3-segment JWS Compact và signature.
- [RFC 7519 — JSON Web Token (JWT)](https://www.rfc-editor.org/rfc/rfc7519): encrypted/nested JWT, claims.
- [RFC 7517 — JSON Web Key (JWK)](https://www.rfc-editor.org/rfc/rfc7517): JWK/JWKS và public-key parameters.
- [RFC 7520 — JOSE Examples](https://www.rfc-editor.org/rfc/rfc7520): ví dụ JWE/JWS và kiểm chứng interoperability.
- [RFC 8725 — JWT Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725): algorithm, token confusion, encryption và compression considerations.
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068): access token typ, audience, issuer.
- [RFC 6749 — OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749): OAuth roles, access/refresh tokens.
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750): Bearer Authorization header và URL token risks.
- [RFC 7662 — Token Introspection](https://www.rfc-editor.org/rfc/rfc7662): opaque token và RS active state.
- [RFC 7009 — Token Revocation](https://www.rfc-editor.org/rfc/rfc7009): token/grant revoke.
- [RFC 9700 — OAuth 2.0 Security BCP](https://www.rfc-editor.org/rfc/rfc9700): token theft/replay, sender binding và refresh-token security.
- [RFC 6265 — HTTP State Management Mechanism](https://www.rfc-editor.org/rfc/rfc6265): cookies, implementation limits.
- [RFC 6585 — Additional HTTP Status Codes](https://www.rfc-editor.org/rfc/rfc6585): HTTP `431 Request Header Fields Too Large`.
- [NIST SP 800-38D — GCM/GMAC](https://csrc.nist.gov/pubs/sp/800/38/d/final): AES-GCM IV uniqueness.
- [OWASP JWT for Java Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/JSON_Web_Token_for_Java_Cheat_Sheet.html): Java JWT/JWE deployment.


