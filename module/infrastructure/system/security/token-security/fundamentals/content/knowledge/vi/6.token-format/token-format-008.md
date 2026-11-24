# Không đặt dữ liệu nhạy cảm trong token dễ đọc

Một ứng dụng nhận được JWT access token có chữ ký hợp lệ. Lập trình viên nhìn vào phần payload thấy \`email\`, \`phone_number\`, \`address\` và cả \`customer_bank_account\`, rồi cho rằng các trường đó an toàn vì “token đã ký” và API chỉ giao tiếp qua HTTPS. Nhận định ấy **sai ở ranh giới bảo mật**: **JWT được ký thông thường bảo vệ tính toàn vẹn và nguồn phát hành, không bảo mật nội dung payload trước người có token**.

Trong module **SECURITY_TOKEN_SECURITY_FUNDAMENTALS**, chủ đề **Token format** gắn chặt với mô hình tin cậy của OAuth 2.0/OpenID Connect (OIDC): chọn JWT hay opaque token, access token hay refresh token; giới hạn claims, scope và audience; bảo vệ nơi lưu, nơi truyền, khả năng thu hồi và rủi ro token bị đánh cắp hoặc phát lại. Bài này tập trung vào một nguyên tắc thiết kế: **chỉ đưa vào token những dữ liệu tối thiểu, đúng mục đích và chấp nhận được nếu bên giữ token đọc thấy**.

Sau bài học, bạn cần có khả năng giải thích vì sao Base64url không phải mã hóa, nhận diện dữ liệu không nên đưa vào token, phân biệt ký với mã hóa, thiết kế claims tối thiểu, và xử lý an toàn khi thông tin nhạy cảm đã bị phát hành trong token.

## 1. JWT được ký không có nghĩa payload được giữ bí mật

JWT là một định dạng biểu diễn claims. Với **JWS compact serialization**, một JWT thường gồm ba phần, ngăn bằng dấu chấm:

~~~text
base64url(header).base64url(payload).base64url(signature)
~~~

Ví dụ về header và payload **trước khi được mã hóa Base64url**:

~~~json
{
  "alg": "RS256",
  "typ": "JWT",
  "kid": "key-01"
}
~~~

~~~json
{
  "iss": "https://auth.example.org",
  "sub": "user-42",
  "aud": "orders-api",
  "scope": "orders:read",
  "iat": 1899999000,
  "exp": 1900000800
}
~~~

Các giá trị chỉ để minh họa, không phải token có thể sử dụng. Trong JWS compact, phần header và payload được **mã hóa Base64url** để vận chuyển thuận tiện; **bất kỳ ai giữ token đều có thể giải mã Base64url để xem nội dung**. Không cần private signing key, public key hay quyền gọi Authorization Server chỉ để *đọc* hai phần này.

Chữ ký số cho phép Resource Server xác minh payload chưa bị sửa đổi và phù hợp với **khóa của issuer đã tin cậy**. Người giữ token có thể đọc payload nhưng không thể tùy tiện thay \`scope\` hoặc \`sub\` mà vẫn tạo chữ ký đúng nếu không có quyền ký. **Không thể sửa khác với không thể đọc**.

| Khái niệm | Bảo vệ được điều gì? | Không bảo vệ được điều gì? |
|---|---|---|
| **Base64url encoding** | Biểu diễn byte thành chuỗi ký tự dễ truyền | Không giấu được nội dung khỏi người có token |
| **JWS signature** | Tính toàn vẹn và xác minh nguồn ký theo trust configuration | Không mã hóa claims; không tự ngăn đánh cắp/phát lại bearer token |
| **TLS/HTTPS** | Bảo vệ dữ liệu khi truyền qua kênh được thiết lập đúng | Không che payload đối với client đang cầm token, bên nhận hợp lệ hay log sau điểm kết thúc TLS |
| **JWE encryption** | Giữ bí mật payload trước bên **không có khóa giải mã**, theo thiết kế và quản lý khóa | Không loại bỏ nhu cầu phân quyền, giới hạn claims, bảo vệ token và chống replay |
| **Opaque reference token** | Không bộc lộ claims qua một cấu trúc có thể đọc ở bên giữ token | Bản thân token vẫn là credential; nguồn lưu/introspection vẫn cần bảo vệ |

**Điểm mấu chốt:** Nếu một client nắm JWT ký thông thường, client thường có thể đọc claims kể cả khi chỉ định gửi token đến API bằng HTTPS. Scope và audience giới hạn **quyền và nơi token được chấp nhận**, chứ không phải cơ chế giấu nội dung claims.

## 2. Dữ liệu nào không nên cho vào token dễ đọc?

Hãy đặt câu hỏi: **Nếu mọi bên được phép cầm token đều đọc được trường này, điều gì sẽ xảy ra?** Cần xét cả log, công cụ giám sát, extension, crash report, bộ nhớ tiến trình và những bên được ủy quyền đi qua chuỗi yêu cầu.

| Nhóm dữ liệu | Ví dụ | Vì sao nên tránh trong JWT dễ đọc? | Cách thay thế |
|---|---|---|---|
| **Bí mật xác thực** | Mật khẩu, OTP, API key, private key, client secret | Lộ thông tin có thể giúp truy cập hệ thống khác, vượt xa phạm vi token | Không nhúng; lưu trong secret manager/kho bảo mật phù hợp |
| **Credential có thể dùng tiếp** | Refresh token, session secret, access token của dịch vụ khác | Một token bị lộ kéo theo nhiều credential mới hoặc nhiều hệ thống khác | Giữ các credential riêng, quản lý và truyền qua đúng kênh của chúng |
| **Dữ liệu định danh cá nhân chi tiết** | Số giấy tờ, địa chỉ đầy đủ, ngày sinh, số điện thoại, email nếu không cần | Tăng khả năng bị nhận diện, liên kết hoạt động và lộ dữ liệu trong log/thiết bị | Dùng ID tối thiểu; lấy hồ sơ qua API được phân quyền |
| **Dữ liệu tài chính, sức khỏe, nhân sự** | Số tài khoản ngân hàng, lịch sử điều trị, mức lương | Tổn thất quyền riêng tư và tác động lớn khi token bị chia sẻ/lưu lại | Giữ trong hệ thống dữ liệu chuyên trách; truy xuất có kiểm soát |
| **Thông tin nội bộ nhạy cảm** | Cấu hình hệ thống, token truy cập môi trường khác, key nội bộ | Bộc lộ kiến trúc và khả năng truy cập không cần thiết | Đưa vào config/secret store của server và phân quyền độc lập |
| **Toàn bộ hồ sơ hoặc danh sách quyền chi tiết** | JSON profile lớn, danh sách khách hàng, mọi quan hệ tổ chức | Token bị phát tán nhiều nơi; dữ liệu dễ cũ, tăng bề mặt rò rỉ | Chỉ cấp claims thực sự cần, tra cứu quyền/tài nguyên tại API |

Đừng mặc định \`email\` hoặc \`name\` luôn bị cấm trong mọi token. Một **OIDC ID token** dành cho đúng client có thể chứa claims hồ sơ theo scope/claim đã được cấp và chính sách phù hợp. Nhưng việc một claim *có thể* được chuẩn hỗ trợ **không có nghĩa nên đưa vào mọi access token**. Hãy chứng minh rằng bên nhận thực sự cần nó và hiểu rủi ro phát tán.

Các định danh tưởng chừng vô hại cũng cần cân nhắc: một \`sub\` ổn định giữa nhiều ứng dụng có thể cho phép liên kết hành vi của cùng người dùng. Các profile OIDC có thể hỗ trợ **pairwise subject identifier** để giảm liên kết giữa các client. \`jti\`, tenant ID hay role có thể làm lộ metadata vận hành; chỉ đưa vào khi cần và giới hạn mức chi tiết.

## 3. Ai có thể đọc và vô tình làm lộ token?

Một access token có thể xuất hiện tại nhiều điểm trong vòng đời:

~~~mermaid
flowchart LR
    AS["Authorization Server"] -->|Phát access token| C["Client / trình duyệt"]
    C -->|Bearer token| G["Gateway / proxy"]
    G -->|Bearer token| API["Resource Server"]
    C -.->|DevTools, storage, crash report| L1["Bản sao ngoài ý muốn"]
    G -.->|Access log / tracing sai cấu hình| L2["Bản sao ngoài ý muốn"]
    API -.->|Exception log / APM sai cấu hình| L3["Bản sao ngoài ý muốn"]
~~~

**HTTPS bảo vệ đường truyền**, nhưng token xuất hiện ở dạng rõ tại hai đầu kết nối và có thể đi qua nhiều hệ thống đã giải mã TLS. Một số tình huống rủi ro:

- Người phát triển dán JWT vào ticket hỗ trợ, ảnh chụp màn hình, trình phân tích token hoặc công cụ thử API không được kiểm soát.
- Proxy, API gateway hay ứng dụng ghi nguyên header \`Authorization\` vào access log, tracing hoặc bản ghi lỗi.
- Trình duyệt có XSS, extension độc hại hoặc JavaScript bên thứ ba đọc token được lưu trong \`localStorage\` hoặc biến của ứng dụng.
- Crash report, telemetry, bộ đệm giao tiếp hoặc lịch sử request của công cụ kiểm thử chứa nguyên bearer token.
- Token bị gửi trong query string và xuất hiện trong browser history, URL log, referrer hoặc công cụ analytics.

Với **JWT ký nhưng không mã hóa**, mỗi bản sao token đồng thời làm lộ các claims chứa trong nó. Với **opaque token**, bản sao thường không trực tiếp cho thấy metadata, nhưng **vẫn có thể dùng để gọi API nếu token là bearer và chưa bị thu hồi**. Vì thế, cả hai phải được xử lý như credential bí mật.

Không bao giờ xem “đã ký bằng private key” là lý do an toàn để gửi token nguyên văn cho bên không cần biết. Chữ ký bảo vệ khả năng sửa đổi claims; nó không giới hạn người đọc.

## 4. Phân biệt JWT/JWS/JWE, opaque, access, refresh và ID token

Các thuật ngữ thuộc những trục phân loại khác nhau:

| Tên gọi | Nói về điều gì? | Hệ quả đối với dữ liệu nhạy cảm |
|---|---|---|
| **JWT** | Định dạng biểu diễn một tập claims | Cần xem JWT được bảo vệ bằng JWS, JWE hay cấu hình khác |
| **JWS** | Chữ ký hoặc MAC bảo đảm tính toàn vẹn và xác minh nguồn theo khóa tin cậy | Payload trong JWS compact thông thường đọc được |
| **JWE** | Mã hóa nội dung cho bên nhận có khóa giải mã | Có tính bí mật trước bên không sở hữu khóa, nhưng dữ liệu lộ sau giải mã cho bên được phép |
| **Opaque token** | Bên giữ token không có hợp đồng để tự diễn giải nội dung | Giảm việc lộ claims trực tiếp qua token; server vẫn phải quản lý dữ liệu nguồn |
| **Access token** | Credential để client gọi Resource Server | Dùng đúng audience/scope; có thể là JWT hoặc opaque |
| **Refresh token** | Credential để xin access token mới tại Authorization Server | Không gửi vào Resource Server; cần bảo vệ đặc biệt, thu hồi/rotation thích hợp |
| **OIDC ID token** | Chứng cứ xác thực danh tính dành cho client/Relying Party | Có thể chứa claims danh tính; audience và cách sử dụng khác access token |

Một **ID token** thường được biểu diễn bằng JWT, nhưng **không được đưa vào header Bearer để thay access token ở API nghiệp vụ**. Trong OIDC, nếu client cần dữ liệu hồ sơ, có thể sử dụng **UserInfo endpoint** hoặc API phù hợp đã được phân quyền, thay vì ép mọi trường hồ sơ vào access token. Người nhận vẫn phải kiểm tra claims và ngữ cảnh theo chuẩn và hợp đồng hệ thống.

Một **refresh token** dù có chuỗi khó đọc vẫn là bí mật có giá trị cao: nếu bị đánh cắp, kẻ tấn công có thể xin thêm access token tùy chính sách và biện pháp bảo vệ. Không nhúng refresh token làm claim trong access token hoặc ID token.

## 5. Thiết kế claims theo nguyên tắc tối thiểu hóa dữ liệu

Để cấp một access token cho \`orders-api\`, câu hỏi không phải “issuer biết gì về người dùng?”, mà là **“API cần bằng chứng nào để xác minh token và áp dụng chính sách?”**.

### Ví dụ thiết kế kém

~~~json
{
  "iss": "https://auth.example.org",
  "sub": "user-42",
  "aud": "orders-api",
  "scope": "orders:read",
  "email": "example.user@example.org",
  "phone_number": "+00-000-000-000",
  "home_address": "123 Example Road",
  "national_identifier": "<example-only-sensitive-id>",
  "bank_account": "<example-only-account>",
  "refresh_token": "<example-only-refresh-token>",
  "customer_profile": {
    "date_of_birth": "1990-01-01",
    "salary": "<example-only-salary>"
  }
}
~~~

Tất cả các giá trị chỉ là **dữ liệu giả minh họa**. Nếu payload này nằm trong JWT chỉ được ký, bất cứ ai có JWT đều có thể đọc các trường. API đọc đơn hàng không cần số tài khoản ngân hàng, lương, địa chỉ, giấy tờ định danh hay refresh token để xác minh bearer access token.

### Thiết kế gọn hơn

~~~json
{
  "iss": "https://auth.example.org",
  "sub": "user-42",
  "aud": "orders-api",
  "scope": "orders:read",
  "iat": 1899999000,
  "exp": 1900000800,
  "jti": "sample-token-id-123"
}
~~~

Đây chỉ là **payload minh họa**, không phải token có chữ ký hợp lệ. Resource Server cần xác minh chữ ký và issuer tin cậy, \`aud\`, thời hạn, loại token và scope; đồng thời kiểm tra người gọi có quyền với **đơn hàng cụ thể**. \`jti\` chỉ cần nếu cơ chế truy vết/thu hồi sử dụng nó. Các trường khác phụ thuộc profile và chính sách API. Ví dụ này không nhằm định nghĩa bắt buộc chính xác mọi JWT đều phải chứa cùng bộ claims.

Với dữ liệu hồ sơ cần hiển thị, client có thể gọi endpoint riêng sau khi được phân quyền:

~~~http
GET /me/profile HTTP/1.1
Host: profile.example.org
Authorization: Bearer <access_token-for-profile-api>
~~~

**Profile API** lấy thông tin từ kho dữ liệu đã được bảo vệ, xác minh token có đúng audience, scope và người dùng đích, rồi chỉ trả về các trường mà client thực sự cần. Token cho \`orders-api\` không tự động được phép truy cập \`profile-api\`; cần access token phù hợp audience hoặc cơ chế ủy quyền được thiết kế rõ ràng.

### Danh mục câu hỏi khi thêm một claim

1. **Ai sẽ giữ token?** Trình duyệt, ứng dụng mobile, backend, gateway và những Resource Server nào có thể nhìn thấy nó?
2. **Claim dùng để quyết định điều gì?** Xác thực token, phân quyền, định tuyến hay chỉ để UI khỏi gọi API thêm?
3. **Có nguồn dữ liệu ít rủi ro hơn không?** Có thể lấy thông tin từ API được phân quyền hoặc tra cứu ở server?
4. **Dữ liệu có thay đổi nhanh không?** Role, membership hoặc trạng thái tài khoản có thể hết đúng trước khi token hết hạn.
5. **Nếu token bị sao chép, hậu quả gì?** Có lộ thông tin cá nhân, bí mật hay tạo khả năng liên kết người dùng giữa dịch vụ không?
6. **Có thể bỏ, rút gọn, ẩn danh hoặc dùng identifier theo từng audience không?** Hạn chế dữ liệu theo nguyên tắc cần biết.

Một claim chỉ nên xuất hiện khi có **mục đích cụ thể, audience rõ và biện pháp bảo vệ tương ứng**. Việc nhét toàn bộ user profile vào JWT để “giảm một lần query” thường gây chi phí bảo mật và tính nhất quán lớn hơn lợi ích.

## 6. Ký không phải mã hóa: khi nào cân nhắc JWE?

Nếu **bên nhận phải giải mã một payload có nội dung riêng tư**, có thể cân nhắc **JWE (JSON Web Encryption)**. Trong dạng JWE compact phổ biến, token có năm phần:

~~~text
protected-header.encrypted-key.iv.ciphertext.authentication-tag
~~~

JWE bảo vệ bí mật nội dung và tính toàn vẹn của bản mã theo thuật toán được hỗ trợ và quản lý khóa phù hợp. Bên **không có khóa giải mã** không thể đọc plaintext chỉ bằng Base64url-decoding. Tuy nhiên:

- **Chọn đúng đối tượng giải mã:** nếu client có khóa giải mã, client có thể đọc toàn bộ claims; không thể dùng JWE để giữ bí mật khỏi chính bên có quyền giải mã.
- **Giới hạn claims vẫn bắt buộc:** sau giải mã, payload có thể bị sao chép vào log, bộ nhớ, telemetry hoặc chuyển tiếp ngoài ý muốn.
- **Không nhầm encryption với authorization:** Resource Server còn phải kiểm tra issuer, audience, thời hạn, scope và quyền trên tài nguyên.
- **Quản lý khóa phức tạp hơn:** cần bảo vệ, cấp phát, thu hồi, xoay khóa giải mã và đảm bảo hệ thống xử lý đúng profile JWT/JWE, kể cả trường hợp dùng nested JWT.
- **Không tự động chống replay:** một token mã hóa nhưng mang tính Bearer vẫn có thể bị dùng lại khi kẻ tấn công giữ nguyên chuỗi token hợp lệ.

**JWE không phải lý do để đưa mật khẩu, refresh token, private key hoặc dữ liệu hồ sơ không cần thiết vào access token.** Nếu bài toán chỉ cần “API xác minh người gọi” và “truy vấn thông tin hồ sơ”, thiết kế ít dữ liệu trong token thường dễ kiểm soát hơn.

Một số hệ thống dùng **opaque reference access token**, nhờ đó client không nhìn thấy claims nội bộ và Resource Server lấy metadata qua introspection đáng tin. Phương án này cũng có chi phí: độ trễ, hạ tầng introspection, cache và khả năng thu hồi. Hơn nữa, opaque token không đảm bảo dữ liệu lưu ở Authorization Server được mã hóa hoặc kiểm soát truy cập đúng; chúng là bài toán riêng.

## 7. Quy trình đọc JWT để học không được dùng làm quy trình xác minh

Để thấy vì sao payload không bí mật, ta có thể giải mã Base64url bằng các lớp chuẩn của Java. **Đoạn mã dưới đây chỉ để học/kiểm tra cấu trúc JWT trong môi trường kiểm soát**. Nó **không xác thực chữ ký**, **không xác nhận issuer/audience**, **không kiểm tra thời hạn** và **không được dùng để cấp quyền truy cập**.

~~~java
import java.nio.charset.StandardCharsets;
import java.util.Base64;

public class JwtPayloadInspectionDemo {
    public static String decodePayloadForDemo(String compactJws) {
        String[] parts = compactJws.split("\\.", -1);
        if (parts.length != 3) {
            throw new IllegalArgumentException("Expected compact JWS format");
        }

        byte[] bytes = Base64.getUrlDecoder().decode(parts[1]);
        return new String(bytes, StandardCharsets.UTF_8);
    }
}
~~~

Lệnh \`Base64.getUrlDecoder().decode(...)\` **không cần khóa**. Một người có token ký thông thường đều có thể thực hiện thao tác tương đương bằng ngôn ngữ hay công cụ khác.

Trong ứng dụng thật, Resource Server phải dùng thư viện JWT/OAuth 2.0 được duy trì để **kiểm tra chữ ký theo khóa issuer tin cậy, giới hạn thuật toán chấp nhận, xác minh \`iss\`, \`aud\`, \`exp\` và các claims khác theo profile** trước khi biến dữ liệu thành principal hoặc quyết định quyền. **Không tự lấy claims từ một payload chưa xác minh** rồi tin \`sub\`, \`roles\` hay \`scope\`.

**Không dùng công cụ decode JWT công khai cho token production** khi chưa đánh giá và được phép, bởi dán token vào một bên thứ ba đồng nghĩa với việc có thể chuyển **toàn bộ bearer credential** và claims cho họ. Cần sử dụng token giả hoặc công cụ nội bộ được kiểm soát.

## 8. Bảo vệ token ở nơi lưu, lúc truyền và khi ghi log

Giảm claims nhạy cảm giúp giảm hậu quả lộ nội dung, nhưng **bản thân Bearer token vẫn là bí mật**: người nắm token có thể dùng nó trong phạm vi, thời hạn còn hiệu lực nếu chưa có biện pháp ràng buộc chủ sở hữu khác.

### 8.1. Khi truyền token

- Chỉ truyền token qua **HTTPS/TLS** tới đúng endpoint. Với bearer access token, dùng header \`Authorization: Bearer <token>\` theo hợp đồng Resource Server.
- Không đặt bearer token vào URL query hoặc fragment để sử dụng như cơ chế xác thực; tránh token bị lưu trong history, log, analytics hoặc bị vô tình chia sẻ.
- Resource Server phải kiểm tra **audience**: token dành cho \`orders-api\` không được dùng để gọi \`billing-api\`, dù scope giống nhau.
- Giữ token ở đúng ranh giới: client gửi **access token** tới API; **refresh token** chỉ gửi đến endpoint/token flow của Authorization Server.
- Nếu hệ thống chuyển tiếp request qua nhiều service, tránh chuyển nguyên token đến dịch vụ không cần nó. Khi cần gọi thay mặt người dùng, dùng cơ chế delegation/token exchange phù hợp và token giới hạn audience, scope.

### 8.2. Khi lưu token

| Môi trường | Nguyên tắc |
|---|---|
| **Browser** | Ưu tiên thiết kế giảm token tiếp xúc với JavaScript khi phù hợp, như BFF/session cookie cấu hình \`HttpOnly\`, \`Secure\`, \`SameSite\`; cần bảo vệ CSRF theo cách dùng cookie. |
| **Single-page app** | Cân nhắc rủi ro XSS và JavaScript bên thứ ba. Lưu token dài hạn trong \`localStorage\` làm tăng tác động khi script độc hại đọc được. |
| **Mobile** | Dùng secure storage của nền tảng khi thích hợp; bảo vệ refresh token, giới hạn quyền ứng dụng và tránh xuất token ra log/backup không an toàn. |
| **Backend** | Lưu secrets trong nơi quản lý phù hợp, giới hạn quyền truy cập, không hard-code, không đẩy token vào source control hay file cấu hình công khai. |
| **Resource Server** | Chỉ giữ token hoặc metadata trong thời gian cần thiết; nếu cache, bảo vệ cache, giới hạn TTL, có chiến lược thu hồi và không sử dụng claims chưa xác minh. |

Cookie \`HttpOnly\` giúp ngăn JavaScript đọc cookie trực tiếp, nhưng **không loại bỏ XSS**: mã độc có thể phát request dưới phiên của người dùng. Cookie tự gửi trong request cũng làm phát sinh nhu cầu phòng **CSRF** tương ứng. Không có một cơ chế lưu trữ duy nhất phù hợp mọi loại client.

### 8.3. Khi ghi log và telemetry

Những nơi cần cấu hình **redaction** gồm API gateway, proxy, access log, HTTP client tracing, exception report, APM, công cụ hỗ trợ khách hàng và pipeline phân tích. Không ghi:

~~~text
Authorization: Bearer eyJ...
Cookie: session=<credential>
refresh_token=<credential>
id_token=<credential>
~~~

Cần ghi các thông tin **không tái sử dụng được làm credential**: request ID, mã lỗi, issuer/audience đã xác minh, identifier nội bộ phù hợp, thời điểm và chính sách từ chối. Nếu cần đối soát cùng token qua log, dùng mã tham chiếu hoặc fingerprint không thể dùng thay token, được tính/bảo vệ theo chính sách; vẫn cân nhắc rủi ro liên kết người dùng giữa hệ thống.

## 9. Sự cố thực tế giả định: Phát hành JWT chứa dữ liệu khách hàng

Giả sử Authorization Server phát hành JWT access token cho \`orders-api\` với các trường \`sub\`, \`scope\`, \`email\`, \`full_address\`, \`bank_account\`. Gateway vô tình ghi nguyên header Authorization vào log và chuyển log tới dịch vụ phân tích nội bộ có nhiều người được xem.

**Những gì đã xảy ra:**

1. Chữ ký JWT vẫn hoàn toàn hợp lệ và payload chưa bị chỉnh sửa.
2. Dịch vụ phân tích và người có quyền đọc log có thể **giải mã Base64url** để xem thông tin khách hàng.
3. Bất kỳ ai lấy được bản sao Bearer token còn hạn cũng có thể thử **phát lại** token tới API phù hợp nếu không có sender-constraining/thu hồi.
4. Kể cả khi access token đã hết hạn, các **bản sao dữ liệu cá nhân trong log** vẫn có thể tồn tại và bị đọc nếu không được xử lý.

**Hướng khắc phục theo từng lớp:**

- **Ngăn rò rỉ mới:** dừng cấp claims không cần thiết, cập nhật cấu hình claims mapping, tắt ghi nguyên header/token ở mọi lớp, kiểm soát quyền xem log.
- **Xử lý credential đã bị lộ:** đánh giá phạm vi token chịu ảnh hưởng, áp dụng thu hồi hoặc giới hạn thời hạn sử dụng theo cơ chế đang có; thu hồi refresh token nếu chúng cũng lộ; giám sát truy cập bất thường.
- **Xử lý dữ liệu đã bị sao chép:** tìm phạm vi log, tracing, backup, công cụ hỗ trợ và bên xử lý liên quan; hạn chế truy cập, áp dụng quy trình lưu giữ/xóa và ứng phó sự cố theo chính sách tổ chức.
- **Khôi phục có kiểm chứng:** phát hành token tối thiểu mới, dùng positive/negative tests kiểm tra payload, cấu hình redaction và quyền API; đưa việc rà soát claims vào quy trình review phát hành token.

**Thu hồi access token hoặc xoay signing key không thể làm những thông tin đã bị đọc trở lại bí mật.** Các bản sao có thể vẫn còn. Vì vậy, giảm dữ liệu ngay từ lúc phát hành là biện pháp phòng ngừa có giá trị lâu dài.

## 10. Mối liên hệ với scope, audience, phân quyền và thu hồi

Để tránh nhầm các lớp bảo vệ, hãy phân biệt:

| Vấn đề | Cơ chế chính | Điều cần nhớ |
|---|---|---|
| **Ai phát hành token?** | Xác minh \`iss\`, chữ ký/JWKS hoặc introspection đáng tin | Chữ ký hợp lệ không làm payload bí mật |
| **Token dành cho đâu?** | \`aud\` và cấu hình Resource Server | Audience không ngăn người giữ token đọc claims |
| **Được gọi API nào?** | \`scope\` và chính sách API | Scope không cấp quyền trên mọi tài nguyên |
| **Có quyền với đối tượng không?** | Membership, role, ownership, tenant, state nghiệp vụ | Cần kiểm tra dữ liệu hiện hành; role trong JWT có thể cũ |
| **Token còn hiệu lực không?** | \`exp\`, \`nbf\`, introspection hoặc cơ chế revoke | Token hết hạn không xóa được dữ liệu nhạy cảm đã lộ |
| **Có ai đọc được payload không?** | Tối thiểu claims, JWE khi cần, kiểm soát luồng dữ liệu | JWS và TLS không che claims khỏi mọi bên đang cầm token |
| **Token bị đánh cắp có dùng lại được không?** | Giảm hạn dùng, thu hồi, sender-constraining khi phù hợp | JWT/opaque bearer đều có nguy cơ replay |

**Claims tối thiểu** và **policy tại Resource Server** bổ trợ cho nhau. Thay vì nhúng danh sách mọi đơn hàng người dùng được đọc vào access token, hãy giới hạn token bằng \`aud=orders-api\`, \`scope=orders:read\`, rồi để Orders API kiểm tra owner/tenant/role hiện hành. Điều này giảm dữ liệu phát tán và tránh lệ thuộc vào snapshot phân quyền cũ.

Với opaque access token, Resource Server có thể dùng **OAuth 2.0 token introspection** để lấy metadata. Đừng coi kết quả \`active=true\` là Permit tuyệt đối: vẫn phải kiểm tra audience, scope, quyền tài nguyên và tính đáng tin của endpoint introspection. Bản thân metadata trả về từ introspection cũng cần **giới hạn theo nhu cầu của Resource Server** và không ghi bừa vào log.

## 11. Danh sách kiểm tra trước khi phát hành một token

Hãy dùng các câu hỏi sau khi thiết kế hoặc review Authorization Server:

1. **Định dạng:** Token là JWT ký, JWE hay opaque? Ai có thể giải mã/diễn giải payload?
2. **Mục đích:** Đây là access token, refresh token hay OIDC ID token? Bên nào phải nhận và kiểm tra nó?
3. **Audience:** Token đã giới hạn đúng API/client nhận chưa? Có nguy cơ chuyển tiếp qua API khác không?
4. **Claims:** Mỗi claim có mục đích, người đọc dự kiến và nguồn dữ liệu rõ ràng không? Có thể loại bỏ PII hoặc secrets không?
5. **Thời gian:** Claims có thể cũ khi quyền hoặc tài khoản thay đổi không? Token sống bao lâu và thu hồi ra sao?
6. **Lưu trữ:** Client/Resource Server có lưu token ở nơi XSS, log, backup hoặc hệ thống hỗ trợ có thể truy cập không?
7. **Bảo vệ đường truyền:** Token có xuất hiện trong URL, redirect không phù hợp, tracing hoặc HTTP không mã hóa không?
8. **Kiểm tra:** API xác minh issuer, key/signature hoặc introspection, audience, scope, thời hạn và quyền tài nguyên thế nào?
9. **Sự cố:** Khi một token hoặc claims bị lộ, tổ chức có khả năng xác định bản sao, thu hồi credential và giảm phát hành thêm không?
10. **Kiểm thử:** Bài test có giải mã payload JWT để kiểm xem không có bí mật/PII ngoài allowlist, kiểm tra redaction và mô phỏng token rò rỉ không?

Một **contract claims** rõ ràng nên đi cùng kiểm thử tự động ở Authorization Server. Với thay đổi thêm claim mới, review phải hỏi “ai thực sự cần dữ liệu này?” và “kênh nào sẽ nhìn thấy token?”. Đừng coi tên claim ít nhạy cảm hơn dữ liệu thật; một ID ổn định cũng có thể cần bảo vệ tùy ngữ cảnh.

## 12. Câu hỏi tự đánh giá

**1. JWT đã ký RS256 có che \`email\` khỏi client không?** Không. Payload JWS compact được Base64url-encode, ai có token thường đều đọc được; RS256 bảo vệ chữ ký, không mã hóa.

**2. Nếu API chỉ dùng HTTPS, có thể đưa số tài khoản ngân hàng vào JWT không?** HTTPS bảo vệ đường truyền; token vẫn được đọc ở client, gateway, API và nơi lưu/log. Không nên đưa dữ liệu không cần vào JWT dễ đọc.

**3. Thay JWT bằng opaque access token có làm việc bảo mật hoàn tất không?** Không. Opaque thường che metadata khỏi client, nhưng bản thân token vẫn có thể bị đánh cắp/phát lại; kho dữ liệu và endpoint introspection cũng cần bảo vệ.

**4. Khi nào JWE hữu ích?** Khi có yêu cầu thực sự giữ kín payload trước bên không có khóa giải mã và quản lý được khóa/người nhận. Vẫn cần giới hạn claims và phân quyền sau giải mã.

**5. ID token có thể thay access token cho Orders API không?** Không. ID token phục vụ xác thực danh tính đối với client theo OIDC; Resource Server phải dùng access token đúng audience và loại token.

**6. Token hết hạn có làm dữ liệu cá nhân từng nhúng trong token biến mất khỏi log không?** Không. Dữ liệu đã được sao chép vẫn có thể tồn tại; cần xử lý nơi phát tán, chính sách lưu giữ và giảm claims từ đầu.

**7. API cần xem số điện thoại để hiển thị thì giải pháp nào thường tốt hơn?** Dùng endpoint hồ sơ được phân quyền đúng scope/audience, chỉ trả trường cần thiết, thay vì đưa số điện thoại vào mọi access token phát hành cho API khác.

**Ghi nhớ:** **Đã ký không có nghĩa đã mã hóa; Base64url không phải bảo mật nội dung.** Với JWT dễ đọc, giả định rằng mọi bên nắm token đều có thể xem claims. Giữ payload tối thiểu, không nhúng secrets hoặc dữ liệu cá nhân không cần thiết, xác minh đúng issuer/audience/scope và phân quyền tại Resource Server; đồng thời bảo vệ **chính chuỗi token** trong quá trình cấp, lưu, truyền, ghi log và thu hồi.
