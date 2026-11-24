# Test signature mismatch: kiểm thử khi chữ ký token không khớp

## 1. Bối cảnh và mục tiêu

Một resource server chỉ được chấp nhận access token sau khi xác minh được token do issuer đáng tin cậy phát hành và nội dung chưa bị thay đổi. Với JWT được ký theo JSON Web Signature (JWS), bước xác minh chữ ký bảo vệ phần header và payload. Nếu một byte trong dữ liệu đã ký bị thay đổi, hoặc verifier sử dụng sai khóa hay thuật toán, việc xác minh phải thất bại.

**Signature mismatch** là tình huống chữ ký nhận được không hợp lệ đối với signing input và khóa xác minh được chọn. Đây là lỗi xác thực token. API phải từ chối request trước khi gọi nghiệp vụ hoặc đọc dữ liệu được bảo vệ.

Trong nền tảng **Security Token Security Fundamentals**, kiểm thử này nằm trong chuỗi kiểm soát vòng đời token: phát hành, vận chuyển, xác minh, kiểm tra claims, phân quyền, thu hồi và giám sát. Một token có chữ ký đúng vẫn cần được kiểm tra issuer, audience, thời hạn, token type, scope và tenant context. Ngược lại, một token có claims trông hợp lý nhưng chữ ký sai phải bị loại bỏ trước khi các claims đó được tin cậy.

Sau bài này, người học có thể:

- Giải thích dữ liệu nào được bảo vệ bởi chữ ký JWS và vì sao thay đổi một byte làm chữ ký không còn hợp lệ.
- Phân biệt chữ ký sai với token sai định dạng, thuật toán không được hỗ trợ, không tìm thấy khóa và claims không hợp lệ.
- Tạo test dương và test âm cho payload bị sửa, signature bị sửa, sai khóa, sai thuật toán và vòng đời khóa.
- Kiểm tra resource server thực sự chạy bước xác minh mật mã, thay vì chỉ giả lập một người dùng đã đăng nhập.
- Đảm bảo request có token không hợp lệ bị từ chối trước khi chạy nghiệp vụ và không làm lộ token trong log hoặc response.

## 2. Chữ ký JWS được xác minh như thế nào?

JWT là một định dạng mang claims. JWT có thể được biểu diễn bằng JWS để bảo vệ tính toàn vẹn và xác thực nguồn phát hành, hoặc bằng JWE để mã hóa nội dung. Một JWT dạng JWS Compact Serialization thường có ba phần Base64URL, ngăn cách bằng dấu chấm:

```text
BASE64URL(protected-header)
.
BASE64URL(payload)
.
BASE64URL(signature)
```

Ví dụ minh họa cấu trúc, không phải token có thể sử dụng:

```text
eyJhbGciOiJSUzI1NiIsImtpZCI6ImtleS0yMDI2In0
.
eyJpc3MiOiJodHRwczovL2lkcC5leGFtcGxlIiwic3ViIjoiYWxpY2UifQ
.
<signature>
```

Với JWS Compact Serialization, dữ liệu đầu vào của thuật toán chữ ký là hai phần đã mã hóa, nối bằng một dấu chấm:

```text
ASCII(
  BASE64URL(UTF8(protected-header))
  + "."
  + BASE64URL(payload)
)
```

Verifier lấy `alg` từ protected header nhưng chỉ sử dụng thuật toán đã được ứng dụng cho phép. Sau đó nó chọn khóa xác minh từ nguồn tin cậy, tính toán hoặc kiểm tra chữ ký trên đúng signing input và so sánh kết quả mật mã với phần signature nhận được. Với thuật toán bất đối xứng như RS256, issuer ký bằng private key và resource server xác minh bằng public key tương ứng. Với HS256, hai phía dùng cùng một secret.

Điểm quan trọng là chữ ký gắn với **byte đã ký**, không chỉ với ý nghĩa JSON sau khi parse. Những thay đổi sau đây đều làm signing input khác đi:

- Sửa một claim, chẳng hạn `sub`, `scope`, `aud` hoặc `tenant_id`.
- Thay đổi protected header, ví dụ `alg` hoặc `kid`.
- Thay đổi khoảng trắng, thứ tự thuộc tính JSON hoặc cách biểu diễn một giá trị rồi mã hóa lại header/payload.
- Cắt cụt token, ghép nhầm các phần hoặc làm hỏng ký tự trong quá trình truyền.

Ngay cả khi hai payload sau khi parse có cùng ý nghĩa, việc serialize lại JSON thường tạo ra chuỗi Base64URL khác. Không được parse token, sửa hoặc serialize lại rồi kỳ vọng chữ ký cũ vẫn hợp lệ.

### 2.1. Những nguyên nhân thường gặp

| Nguyên nhân | Điều xảy ra | Cách tạo test |
| --- | --- | --- |
| Payload bị sửa | Claims sau khi ký không còn giống payload ban đầu. | Thay `sub` hoặc `scope`, giữ nguyên signature. |
| Signature bị sửa | Một hoặc nhiều byte chữ ký không còn là chữ ký do signer tạo. | Đảo một bit trong phần signature rồi mã hóa Base64URL lại. |
| Dùng sai khóa | Token được ký bằng private key/secret khác với khóa verifier đang dùng. | Ký bằng key pair A, xác minh bằng public key B. |
| Chọn nhầm `kid` | Verifier lấy nhầm JWK hoặc không tìm được khóa tương ứng. | Dùng `kid` không tồn tại hoặc ánh xạ sai khóa trong JWKS fixture. |
| Sai thuật toán | Signer và verifier không dùng cùng thuật toán hoặc cấu hình không cho phép thuật toán đó. | Tạo token bằng thuật toán ngoài allowlist. |
| Không tương thích key type/curve | Ví dụ cấu hình RSA trong khi token dùng EC, hoặc sai đường cong ECDSA. | Dùng fixture khác loại khóa hoặc curve. |
| Hỏng dữ liệu khi vận chuyển | Token bị cắt, escape, decode/encode sai hoặc ghép chuỗi sai. | Cắt từng segment hoặc thay ký tự trong token. |

Với ECDSA, cần lưu ý JWS dùng biểu diễn chữ ký `R || S` có độ dài cố định theo profile JOSE. Một số API mật mã Java biểu diễn chữ ký ECDSA theo ASN.1 DER. Thư viện JOSE phải chuyển đổi đúng định dạng; không tự lấy byte DER rồi đặt trực tiếp vào segment signature. Với RSA, RS256 và PS256 cũng là hai thuật toán khác nhau: RS256 dùng RSASSA-PKCS1-v1_5 với SHA-256, còn PS256 dùng RSASSA-PSS với SHA-256.

### 2.2. Phân biệt với các lỗi xác minh khác

Không phải mọi lỗi khi nhận JWT đều là signature mismatch. Phân loại đúng giúp test chỉ ra lớp đang có vấn đề:

| Lỗi | Ví dụ | Kết quả mong đợi |
| --- | --- | --- |
| Sai định dạng | Token thiếu segment, có segment rỗng không hợp lệ hoặc Base64URL lỗi. | Parser từ chối; không chạy nghiệp vụ. |
| Thuật toán không được phép | Header khai báo `alg=none` hoặc thuật toán ngoài allowlist. | Từ chối trước khi cấp danh tính. |
| Không tìm thấy khóa | `kid` không có trong tập JWKS tin cậy. | Không tự chọn khóa khác tùy tiện; từ chối nếu không thể xác định khóa hợp lệ. |
| Chữ ký không hợp lệ | Payload/signature bị sửa hoặc ký bằng khóa khác. | Xác minh mật mã thất bại. |
| Claims không hợp lệ | Chữ ký đúng nhưng `iss`, `aud`, `exp` hoặc `nbf` không đạt chính sách. | Từ chối ở bước kiểm tra claims. |
| Không đủ quyền | Token hợp lệ nhưng thiếu scope hoặc không có quyền trên tài nguyên/tenant. | Thường trả 403 theo chính sách API. |

Thông báo từ thư viện có thể gom nhiều nguyên nhân vào một ngoại lệ xác minh token. Vì vậy, test nên kiểm tra hành vi bảo mật quan sát được ở ranh giới API, đồng thời dùng mã lỗi nội bộ hoặc test fixture để xác định nguyên nhân. Không nên phụ thuộc vào chuỗi thông báo ngoại lệ của một phiên bản thư viện cụ thể.

## 3. Quy tắc an toàn trước khi viết test

**Chỉ xác minh bằng khóa và thuật toán được cấu hình tin cậy.** Header JWT là dữ liệu do người gửi kiểm soát cho đến khi chữ ký được xác minh. `alg`, `kid`, `jku` hoặc `x5u` trong token không được phép tự tạo trust mới. Ứng dụng phải giới hạn thuật toán, chọn khóa từ issuer/JWKS đã onboarding và kiểm tra issuer phù hợp với khóa đó.

Các nguyên tắc cần giữ:

1. Không chấp nhận `alg=none` cho access token có yêu cầu chữ ký.
2. Không dùng cùng một luồng xác minh linh hoạt cho RSA và HMAC theo cách có thể gây nhầm lẫn loại khóa. Không lấy public key RSA làm HMAC secret.
3. Không tải khóa từ URL tùy ý do token cung cấp. Cấu hình JWKS URI từ nguồn tin cậy hoặc cơ chế discovery đã được kiểm soát.
4. `kid` chỉ là gợi ý chọn khóa trong tập khóa tin cậy; nó không chứng minh token đáng tin.
5. Không parse claims rồi cấp quyền trước khi xác minh chữ ký. Một thư viện có thể hỗ trợ decode không xác minh để phục vụ mục đích kỹ thuật; kết quả đó không được dùng làm danh tính hoặc quyết định phân quyền.
6. Không thử lần lượt mọi thuật toán hoặc mọi loại khóa cho đến khi một cách xác minh thành công. Cách fallback này có thể mở ra lỗi algorithm confusion hoặc downgrade.
7. Không ghi bearer token, refresh token, private key hay HMAC secret vào log, báo cáo test hoặc thông báo lỗi.

Test nên dùng key pair và secret được sinh riêng cho môi trường test. Không sao chép token production, private key production hay dữ liệu định danh thật vào fixture. Với RSA, dùng kích thước khóa phù hợp chính sách hiện hành; với HMAC, secret phải có entropy đủ lớn và không phải chuỗi dễ đoán.

## 4. Thiết kế bộ test signature mismatch

Một bộ test tốt có **test dương** để chứng minh cấu hình có thể xác minh token hợp lệ và **test âm** để chứng minh các biến thể bị sửa đều bị từ chối. Nếu chỉ viết test âm, một decoder luôn từ chối mọi token cũng có thể làm test pass. Nếu chỉ viết test dương, lỗi chấp nhận token bị giả mạo sẽ không được phát hiện.

### 4.1. Chuẩn bị fixture

Tạo fixture cô lập, có thể tái tạo:

- Sinh một key pair RSA hoặc EC trong bộ test; giữ private key chỉ ở phía signer fixture và truyền public key cho decoder.
- Cấu hình rõ thuật toán được phép, issuer và audience dành cho API test.
- Phát hành một access token mẫu có `iss`, `sub`, `aud`, `iat`, `exp` và claims cần thiết.
- Lưu token hợp lệ trong biến fixture trong bộ nhớ test; không commit token có thể truy cập hệ thống thật.
- Tạo các biến thể token bằng cách sửa từng thành phần sau khi ký. Mỗi test chỉ nên thay đổi một điều kiện để kết quả dễ chẩn đoán.

Đối với kiểm thử HMAC, tạo token bằng secret test rồi xác minh bằng secret khác có cùng độ dài để cô lập lỗi sai khóa. Đối với kiểm thử RSA/EC, ký bằng private key A và cấu hình decoder với public key B. Không dùng cùng một key cho tất cả test vì sẽ khó phát hiện lỗi ánh xạ khóa.

### 4.2. Test token hợp lệ trước

```java
@Test
void acceptsTokenSignedByTrustedKey() {
    String token = tokenSignedByFixturePrivateKey();

    Jwt jwt = decoder.decode(token);

    assertEquals("https://issuer.test", jwt.getIssuer().toString());
    assertEquals("alice", jwt.getSubject());
    assertTrue(jwt.getAudience().contains("documents-api"));
}
```

Đây là test kiểm tra đường đi thành công. `decoder` phải được cấu hình bằng public key tương ứng với private key fixture, thuật toán được phép và validator claims của API test. Các hàm tạo fixture được lược khỏi ví dụ vì cách triển khai phụ thuộc thư viện JOSE mà dự án sử dụng.

### 4.3. Sửa riêng phần signature

Với một JWS hợp lệ, đảo một bit trong byte chữ ký rồi mã hóa lại bằng Base64URL. Header và payload được giữ nguyên, do đó test tập trung vào xác minh chữ ký:

```java
private static String flipSignatureBit(String compactJws) {
    String[] parts = compactJws.split("\\.", -1);
    if (parts.length != 3 || parts[2].isEmpty()) {
        throw new IllegalArgumentException("Expected a signed compact JWS");
    }

    byte[] signature = Base64.getUrlDecoder().decode(parts[2]);
    if (signature.length == 0) {
        throw new IllegalArgumentException("Signature is empty");
    }

    signature[0] ^= 0x01;
    String changedSignature = Base64.getUrlEncoder()
            .withoutPadding()
            .encodeToString(signature);

    return parts[0] + "." + parts[1] + "." + changedSignature;
}

@Test
void rejectsChangedSignature() {
    String validToken = tokenSignedByFixturePrivateKey();
    String tamperedToken = flipSignatureBit(validToken);

    assertThrows(JwtException.class, () -> decoder.decode(tamperedToken));
}
```

Test này cần token JWS đã ký thật. Không mock phương thức kiểm tra chữ ký vì mục tiêu là xác minh thư viện mật mã thực sự từ chối chữ ký bị sửa. `JwtException` là kiểu ngoại lệ tổng quát minh họa cho Spring Security; có thể điều chỉnh kiểu ngoại lệ theo decoder đang dùng.

### 4.4. Sửa payload nhưng giữ signature cũ

Tạo payload fixture có claim dễ nhận diện, ví dụ `"sub":"alice"`. Sau khi ký, decode riêng segment payload, thay giá trị thành `mallory`, mã hóa Base64URL lại và giữ nguyên header cùng signature. Decoder phải từ chối vì signing input đã thay đổi.

```java
private static String replaceSubjectWithoutResigning(String compactJws) {
    String[] parts = compactJws.split("\\.", -1);
    if (parts.length != 3) {
        throw new IllegalArgumentException("Expected a compact JWS");
    }

    byte[] payloadBytes = Base64.getUrlDecoder().decode(parts[1]);
    String payload = new String(payloadBytes, StandardCharsets.UTF_8);
    String changedPayload = payload.replace("\"sub\":\"alice\"", "\"sub\":\"mallory\"");
    if (changedPayload.equals(payload)) {
        throw new IllegalArgumentException("Fixture subject was not found");
    }

    String encodedPayload = Base64.getUrlEncoder()
            .withoutPadding()
            .encodeToString(changedPayload.getBytes(StandardCharsets.UTF_8));

    return parts[0] + "." + encodedPayload + "." + parts[2];
}

@Test
void rejectsChangedPayloadWithOriginalSignature() {
    String validToken = tokenSignedByFixturePrivateKey();
    String tamperedToken = replaceSubjectWithoutResigning(validToken);

    assertThrows(JwtException.class, () -> decoder.decode(tamperedToken));
}
```

Hàm thay thế trên giả định fixture JSON chứa đúng chuỗi `"sub":"alice"`. Nếu serializer thêm khoảng trắng hoặc thay đổi cách serialize, hãy tạo payload fixture ổn định hoặc dùng JSON parser để sửa claim rồi serialize lại. Dù cách nào, không ký lại payload đã sửa: mục tiêu là giữ signature cũ để chứng minh verifier phát hiện dữ liệu đã bị thay đổi.

### 4.5. Xác minh bằng sai khóa

Ký token bằng private key A nhưng cấu hình decoder chỉ có public key B. Test phải từ chối token. Cần phân biệt hai biến thể:

- `kid` trỏ tới một khóa tồn tại nhưng khóa đó không khớp với signer: thường dẫn tới xác minh chữ ký thất bại.
- `kid` không tồn tại trong JWKS: lỗi có thể được phân loại là không tìm thấy khóa thay vì signature mismatch.

Hai trường hợp đều phải bị từ chối, nhưng test riêng giúp phát hiện lỗi trong quá trình tải, cache và ánh xạ JWKS.

### 4.6. Xác minh thuật toán và loại khóa

Tạo test cho các tình huống:

- Token dùng `alg=none` trong khi API yêu cầu chữ ký.
- Token khai báo thuật toán không nằm trong allowlist.
- Token dùng HS256 trong khi API chỉ cho phép RS256.
- Token dùng RS256 nhưng decoder được cấu hình với khóa EC hoặc khóa RSA không tương ứng.
- Token dùng `kid` của khóa đã bị loại khỏi tập tin cậy.

Kỳ vọng là từ chối. Không khẳng định tất cả trường hợp này phải trả cùng một thông báo lỗi nội bộ: thuật toán không hỗ trợ, khóa không tìm thấy và chữ ký không hợp lệ là các nhánh khác nhau. Điều cần giữ nhất quán là không trường hợp nào được tạo ra một danh tính đã xác thực.

## 5. Kiểm thử tại resource server

Unit test decoder chứng minh lớp mật mã hoạt động. Integration test cần chứng minh toàn bộ chuỗi HTTP cũng từ chối token sai chữ ký và không chạy nghiệp vụ.

Một kịch bản điển hình:

1. Khởi động resource server test với decoder dùng public key fixture.
2. Gọi endpoint được bảo vệ bằng access token hợp lệ; xác nhận response thành công.
3. Gửi lại request bằng token đã bị sửa signature hoặc payload.
4. Xác nhận API trả 401 và response không chứa dữ liệu nghiệp vụ.
5. Xác nhận service/repository không được gọi.

Ví dụ kiểm tra với Spring MockMvc (giả định ứng dụng đã cấu hình OAuth2 Resource Server và endpoint `/api/documents`):

```java
mockMvc.perform(get("/api/documents")
        .header(HttpHeaders.AUTHORIZATION, "Bearer " + tamperedToken))
    .andExpect(status().isUnauthorized());

verifyNoInteractions(documentService);
```

Đoạn trên là phần assertion của integration test; test fixture phải cung cấp `tamperedToken` được tạo từ một token ký hợp lệ. Có thể kiểm tra thêm header `WWW-Authenticate` theo hợp đồng API, thường mang lỗi bearer `invalid_token`. Không nên phụ thuộc vào body lỗi chi tiết của framework nếu ứng dụng không cam kết định dạng đó.

**Lưu ý quan trọng về test giả lập:** `@WithMockUser`, `jwt()` request post-processor hoặc việc mock `JwtDecoder` thường đặt sẵn một danh tính đã xác thực. Chúng hữu ích để test authorization rule, scope và controller, nhưng không chạy xác minh chữ ký thật. Vì vậy, chúng không thay thế integration test gửi bearer token thực qua filter chain và decoder được cấu hình.

## 6. Kiểm thử JWKS và vòng đời khóa

Trong môi trường nhiều instance, resource server thường lấy public key từ JWKS endpoint của issuer. Một token hợp lệ có thể bị từ chối nếu cache khóa sai hoặc quá cũ; ngược lại, cấu hình giữ khóa đã thu hồi quá lâu có thể tiếp tục chấp nhận token không còn được phép.

Thiết kế test cho các tình huống sau:

| Tình huống | Cách kiểm thử | Kỳ vọng |
| --- | --- | --- |
| Khóa hiện hành | JWKS có public key đúng `kid`. | Token ký bằng private key tương ứng được xác minh. |
| `kid` không tồn tại | JWKS không có khóa được yêu cầu. | Từ chối; không lấy khóa từ URL không tin cậy trong header. |
| Xoay khóa | JWKS công bố khóa mới trong khi token cũ còn hạn. | Hành vi chấp nhận/từ chối tuân theo thời gian overlap đã thiết kế. |
| Khóa cũ hết thời gian overlap | JWKS đã bỏ khóa cũ và cache được cập nhật. | Token dùng khóa cũ bị từ chối theo chính sách. |
| JWKS tạm thời không truy cập được | Giả lập timeout hoặc HTTP lỗi. | Không bỏ qua xác minh; áp dụng cache/fail-closed policy đã cấu hình. |
| JWKS trả dữ liệu lỗi | JSON/JWK thiếu trường, key type sai hoặc `kid` trùng gây mơ hồ. | Không chọn khóa không an toàn; phát sinh lỗi xác minh có kiểm soát. |
| Cache đồng thời | Nhiều request cùng gặp `kid` mới. | Không tạo tải truy vấn JWKS không giới hạn hoặc race condition làm sai lựa chọn khóa. |

Không nên mặc định rằng mọi `kid` lạ đều cần gọi JWKS liên tục. Nếu thư viện có cơ chế refresh khi không tìm thấy khóa, cần giới hạn tần suất và kiểm thử hành vi đó để tránh bị lợi dụng gây cạn tài nguyên. Cache chỉ được dùng theo chính sách tin cậy; khi cache lỗi hoặc hết hạn, ứng dụng không được chuyển sang chế độ chấp nhận token mà không xác minh.

## 7. Kết hợp chữ ký với kiểm tra claims và phân quyền

Thứ tự xử lý ở resource server nên thể hiện rõ các ranh giới:

```text
HTTP Authorization: Bearer <token>
             |
             v
      Parse token format
             |
             v
  Select trusted issuer/key/algorithm
             |
             v
     Verify JWS signature
       |             |
      FAIL          PASS
       |             |
   401 invalid       v
                 Validate iss/aud/exp/nbf/typ
                       |
                       v
                Check scope/roles
                       |
                       v
             Check tenant/resource policy
                       |
                       v
                Run application logic
```

Nếu chữ ký sai, không tiếp tục kiểm tra claims như thể chúng là dữ liệu đáng tin. Sau khi chữ ký đúng, vẫn phải kiểm tra:

- `iss` đúng issuer được API tin cậy.
- `aud` bao gồm audience của resource server hiện tại.
- `exp` chưa hết hạn và `nbf` đã có hiệu lực; áp dụng clock skew có giới hạn.
- Token là access token theo profile/hợp đồng mà API chấp nhận; không dùng ID token hoặc refresh token thay thế.
- Scope/role đủ cho hành động.
- Tenant context và quyền trên tài nguyên được xác minh theo dữ liệu phía server.

Test chữ ký nên tách khỏi test claims để chẩn đoán chính xác. Ví dụ, token có chữ ký hợp lệ nhưng `aud` sai phải bị từ chối vì audience; token có chữ ký sai và `aud` sai phải bị từ chối ngay từ bước xác minh chữ ký. Không gộp hai điều kiện vào cùng một test âm nếu mục tiêu là xác định lớp nào phát hiện lỗi.

Opaque access token không có JWS signature để resource server tự xác minh. Với loại token này, API thường gọi authorization server qua introspection và kiểm tra `active`, audience, scope cùng metadata liên quan. Không áp dụng test sửa segment chữ ký cho opaque token; hãy viết test introspection trả token không active hoặc metadata không phù hợp.

JWE cũng cần test riêng. JWE Compact Serialization có năm phần và sử dụng mã hóa nội dung cùng authentication tag. Một lỗi authentication tag hoặc giải mã JWE không đồng nghĩa với lỗi chữ ký JWS. Nếu hệ thống dùng nested JWT (ví dụ JWS nằm bên trong JWE), phải kiểm tra đúng thứ tự giải mã và xác minh theo profile đã chọn.

## 8. Ma trận test đề xuất

| ID | Fixture/request | Lớp được kiểm tra | Kết quả mong đợi |
| --- | --- | --- | --- |
| SIG-01 | Token ký bằng private key tin cậy, claims hợp lệ. | Đường đi dương của decoder. | Chấp nhận và trả claims đã xác minh. |
| SIG-02 | Đảo một bit trong signature. | JWS signature verification. | Từ chối. |
| SIG-03 | Sửa `sub` trong payload, giữ signature cũ. | Tính toàn vẹn payload. | Từ chối. |
| SIG-04 | Sửa protected header sau khi ký. | Tính toàn vẹn header. | Từ chối hoặc bị chặn bởi kiểm tra thuật toán/header. |
| SIG-05 | Token ký bằng key A, decoder dùng public key B. | Key selection/verification. | Từ chối. |
| SIG-06 | `kid` không có trong JWKS. | JWKS lookup. | Từ chối, không fallback tùy tiện. |
| SIG-07 | `alg=none`. | Algorithm allowlist. | Từ chối. |
| SIG-08 | Thuật toán ngoài allowlist hoặc key type không phù hợp. | Cấu hình thuật toán. | Từ chối. |
| SIG-09 | Token hợp lệ sau khi JWKS công bố khóa mới. | Key rotation. | Chấp nhận theo overlap policy. |
| SIG-10 | Token dùng khóa cũ sau khi khóa bị loại và cache cập nhật. | Key retirement. | Từ chối theo policy. |
| SIG-11 | JWKS timeout/HTTP 5xx. | Dependency failure. | Không bỏ qua xác minh; phản hồi lỗi xác thực có kiểm soát. |
| SIG-12 | Token chữ ký đúng nhưng issuer hoặc audience sai. | Claims validation. | Từ chối ở bước claims. |
| SIG-13 | Token chữ ký đúng nhưng hết hạn. | Token lifetime. | Từ chối. |
| SIG-14 | Token chữ ký sai gọi endpoint bảo vệ. | Filter chain/integration. | 401; service/repository không được gọi. |
| SIG-15 | Token chữ ký đúng nhưng thiếu scope. | Authorization. | 403 theo policy. |
| SIG-16 | Dùng `jwt()` hoặc mock decoder cho test chữ ký. | Chất lượng test. | Đánh dấu không phải test xác minh mật mã; bổ sung test bearer token thật. |

Với mỗi test âm, kiểm tra cả hai điều: token không tạo ra authentication thành công và không có side effect nghiệp vụ. Với test dương, xác nhận token hợp lệ vẫn hoạt động để tránh cấu hình decoder bị khóa quá mức.

## 9. Kết quả HTTP, log và vận hành

Với OAuth 2.0 Bearer Token, token không hợp lệ thường được biểu diễn bằng phản hồi **401 Unauthorized** và challenge `WWW-Authenticate` có lỗi `invalid_token`. Khi token đã xác thực nhưng người dùng không có quyền thực hiện hành động, API thường trả **403 Forbidden**. Cần giữ quy ước nhất quán trong toàn bộ API.

Client chỉ cần biết thông tin đủ để xử lý việc xác thực lại hoặc yêu cầu token mới. Không trả stack trace, nội dung JWT đã decode, khóa công khai nội bộ, secret, chi tiết thuật toán hoặc thông tin giúp dò cấu hình khóa. Ở phía server, có thể ghi nhận mã lý do như `TOKEN_SIGNATURE_INVALID`, `TOKEN_KEY_NOT_FOUND`, `TOKEN_ALGORITHM_REJECTED` hoặc `JWKS_UNAVAILABLE`.

Log và metric nên hỗ trợ điều tra mà không lưu token:

- Correlation/request ID, tên service và endpoint.
- Issuer đã cấu hình, thuật toán đã được cho phép và `kid` sau khi xử lý an toàn nếu cần điều tra.
- Mã lý do xác minh, kết quả allow/deny và thời gian xử lý.
- Số lần JWKS refresh, cache hit/miss, timeout và lỗi tải khóa.
- Không ghi raw bearer token, refresh token, private key, HMAC secret hoặc toàn bộ payload có dữ liệu cá nhân.

Nếu tỷ lệ signature mismatch tăng đột ngột, điều đó có thể đến từ token bị sửa, client gửi token sai API, key rotation chưa đồng bộ, cache JWKS lỗi hoặc cấu hình issuer/algorithm không nhất quán. Hãy đối chiếu thời điểm triển khai, `kid`, trạng thái JWKS và log phát hành token đã được làm sạch dữ liệu. Không tắt xác minh chữ ký để khôi phục dịch vụ.

## 10. Những lỗi kiểm thử thường gặp

**Chỉ kiểm tra token parse được.** Parse thành công không chứng minh chữ ký đúng. Test phải gọi decoder/validator có bật xác minh mật mã.

**Mock decoder trong test chữ ký.** Khi mock trả về một `Jwt` hợp lệ, test bỏ qua hoàn toàn khóa, thuật toán và signing input. Giữ mock cho test authorization; dùng decoder thật với key fixture cho test chữ ký.

**Sửa payload rồi ký lại.** Token mới có chữ ký hợp lệ, nên test không còn kiểm tra signature mismatch. Phải giữ signature cũ sau khi sửa payload.

**Chỉ test token sai mà không có token đúng.** Decoder từ chối tất cả token vẫn làm test âm pass. Luôn có test dương dùng key fixture tương ứng.

**Dùng token production làm fixture.** Token có thể còn hạn, chứa dữ liệu thật hoặc bị vô tình ghi vào log. Hãy sinh key và token riêng trong test.

**Nhầm sai `kid` với sai chữ ký.** Không tìm thấy khóa và xác minh bằng khóa sai là hai nhánh khác nhau. Viết test riêng để xác nhận cả hai đều fail closed.

**Bỏ qua lỗi JWKS.** Không truy cập được khóa không có nghĩa token hợp lệ. Kiểm thử timeout, HTTP lỗi, dữ liệu JWK sai định dạng và cache stale.

**Chỉ kiểm tra status code.** Một endpoint có thể trả 401 nhưng đã chạy một phần nghiệp vụ trước đó. Xác nhận service/repository không được gọi và không phát sinh side effect.

## 11. Checklist hoàn thành

- [ ] Có test dương cho token được ký bằng khóa fixture tin cậy.
- [ ] Có test âm sửa signature và test âm sửa payload nhưng giữ signature cũ.
- [ ] Có test sai khóa, `kid` không tồn tại, thuật toán không được phép và loại khóa không phù hợp.
- [ ] Có test phân biệt lỗi chữ ký với lỗi định dạng, issuer, audience, thời hạn và scope.
- [ ] Có test JWKS rotation, cache, timeout và dữ liệu khóa lỗi.
- [ ] Integration test gửi bearer token thực qua resource server filter chain.
- [ ] Request có chữ ký sai nhận phản hồi xác thực thất bại và không gọi nghiệp vụ.
- [ ] Test dương vẫn hoạt động sau khi cấu hình allowlist và key selection.
- [ ] Không có token hoặc secret production trong fixture, log, response hay báo cáo.
- [ ] Opaque token và JWE được kiểm thử theo cơ chế tương ứng, không nhầm với JWS signature mismatch.

**Ghi nhớ:** chữ ký JWS xác nhận tính toàn vẹn của đúng header và payload đã ký. Test signature mismatch phải chứng minh một thay đổi sau khi ký, một khóa sai hoặc một cấu hình thuật toán không phù hợp đều không thể tạo ra authentication hợp lệ; đồng thời, token có chữ ký đúng vẫn phải đi qua các bước kiểm tra claims và quyền riêng biệt.

## Tài liệu đối chiếu

- [RFC 7515 — JSON Web Signature (JWS)](https://www.rfc-editor.org/rfc/rfc7515): cấu trúc JWS, signing input và các dạng biểu diễn chữ ký.
- [RFC 7518 — JSON Web Algorithms (JWA)](https://www.rfc-editor.org/rfc/rfc7518): thuật toán ký, loại khóa và định dạng chữ ký JOSE.
- [RFC 7519 — JSON Web Token (JWT)](https://www.rfc-editor.org/rfc/rfc7519): cấu trúc và claims của JWT.
- [RFC 8725 — JSON Web Token Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725): các biện pháp chống nhầm thuật toán, issuer, audience và kiểu token.
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068): profile JWT access token dành cho OAuth 2.0.
- [RFC 6750 — The OAuth 2.0 Authorization Framework: Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750): cách sử dụng bearer token và biểu diễn lỗi `invalid_token`.
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662): cơ chế introspection dành cho opaque token và resource server.
- [Spring Security — OAuth 2.0 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html): cấu hình JWT decoder và resource server trong Spring Security.
