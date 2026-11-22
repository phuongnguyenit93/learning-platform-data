# Phân biệt chữ ký hợp lệ với token hợp lệ theo ngữ cảnh

## 1. Chữ ký hợp lệ chưa đủ để chấp nhận JWT

Một **JSON Web Token (JWT)** có thể mang các claims về chủ thể, bên nhận, thời hạn, phạm vi truy cập và ngữ cảnh nghiệp vụ. Với JWT được ký theo **JSON Web Signature (JWS)**, bên nhận có thể kiểm tra chữ ký để phát hiện nội dung bị thay đổi và xác minh chữ ký được tạo bằng khóa tương ứng.

Tuy nhiên, kết quả xác minh chữ ký chỉ trả lời một câu hỏi mật mã: **chữ ký trên dữ liệu này có hợp lệ theo thuật toán và khóa đang được sử dụng hay không?** Nó chưa trả lời các câu hỏi:

- Khóa đó có thực sự thuộc issuer mà API tin cậy không?
- Token có được phát hành cho API hiện tại không?
- Token có đúng loại và đúng mục đích sử dụng không?
- Token còn hiệu lực về thời gian không?
- Claims có đáp ứng hợp đồng của API không?
- Chủ thể có quyền thực hiện hành động trên tài nguyên cụ thể không?

Ví dụ, một token được ký đúng bởi hệ thống định danh dành cho API hồ sơ người dùng. Nếu API thanh toán nhận token đó và chỉ kiểm tra chữ ký, nó có thể chấp nhận một token được phát hành cho mục đích khác. Chữ ký vẫn đúng, nhưng việc sử dụng token tại API thanh toán là sai ngữ cảnh.

**Chữ ký hợp lệ là một điều kiện cần trong nhiều hồ sơ JWT có ký; token hợp lệ theo ngữ cảnh còn phải vượt qua toàn bộ các kiểm tra về nguồn tin cậy, mục đích, thời gian, claims và quyền truy cập.**

## 2. Chữ ký JWS chứng minh điều gì?

Với JWS Compact Serialization, dữ liệu ký được tạo từ phần header đã mã hóa Base64URL và payload đã mã hóa Base64URL:

~~~text
BASE64URL(UTF8(protected header))
  + "."
  + BASE64URL(payload)
~~~

Chữ ký được tính theo thuật toán JWS đã chọn trên signing input này. Khi xác minh thành công, bên nhận biết dữ liệu được ký không bị thay đổi kể từ khi chữ ký được tạo, với giả định thuật toán và khóa được triển khai đúng.

Ví dụ token có payload:

~~~json
{
  "iss": "https://identity.example.org",
  "sub": "user_42",
  "aud": "https://api.profile.example.org",
  "exp": 1893456900,
  "role": "profile_reader"
}
~~~

Nếu chữ ký hợp lệ dưới khóa ký đã được xác minh thuộc issuer tin cậy, API có thể tin rằng issuer đã ký đúng nội dung payload này. Nhưng API vẫn phải kiểm tra token có dành cho mình không, claim có hợp lệ theo profile không và role có được phép dùng cho thao tác cụ thể không.

### 2.1. Chữ ký hợp lệ không chứng minh mọi claim là sự thật tuyệt đối

Chữ ký chứng minh nguồn ký theo khóa đã chọn và tính toàn vẹn của dữ liệu, chứ không chứng minh issuer đã lấy dữ liệu từ nguồn nghiệp vụ đúng. Nếu issuer bị cấu hình sai và ký role=admin dựa trên dữ liệu client tự khai báo, chữ ký vẫn hợp lệ.

Do đó, độ tin cậy của claim còn phụ thuộc vào:

- Quy trình xác thực chủ thể và client tại issuer.
- Nguồn có thẩm quyền dùng để tạo từng claim.
- Chính sách cấp scope, vai trò, tenant và entitlement.
- Quy trình quản lý khóa ký và giới hạn ai được phép sử dụng khóa.
- Hợp đồng giữa issuer với consumer về ngữ nghĩa claims.

### 2.2. Chữ ký hợp lệ không làm payload bí mật

JWS cung cấp tính toàn vẹn và xác thực nguồn ký theo khóa, không mã hóa payload. Người giữ token thường có thể giải mã phần payload và đọc claims. Nếu cần bảo vệ tính bí mật, phải dùng cơ chế mã hóa thích hợp như JWE theo mô hình khóa được thiết kế đúng.

Mã hóa cũng không thay thế xác minh nguồn phát hành và chính sách truy cập. Một payload được giải mã thành công vẫn cần kiểm tra các ràng buộc của token.

## 3. Những lớp kiểm tra để chấp nhận một JWT

Một resource server nên xem việc chấp nhận token là một chuỗi kiểm tra có liên hệ với nhau. Các bước cụ thể phụ thuộc token profile, nhưng có thể chia thành các lớp:

| Lớp | Câu hỏi | Ví dụ kiểm tra |
| --- | --- | --- |
| Cấu trúc | Dữ liệu có đúng định dạng và giới hạn không? | Số phần, encoding, JSON hợp lệ, kích thước |
| Thuật toán | Thuật toán có được hệ thống cho phép không? | Allowlist thuật toán, loại khóa phù hợp |
| Khóa và issuer | Khóa xác minh có thuộc issuer được tin cậy không? | Cấu hình issuer, JWKS tin cậy, key use |
| Chữ ký | Chữ ký có hợp lệ trên đúng signing input không? | JWS verification |
| Loại token | Token có đúng mục đích và profile không? | typ, quy tắc phân biệt access token/ID token |
| Issuer và audience | Token do đúng bên phát hành và dành cho API này không? | iss, aud |
| Thời gian | Token đã có hiệu lực và chưa hết hạn chưa? | exp, nbf, iat, clock skew |
| Schema và ngữ nghĩa | Claims có đáp ứng hợp đồng không? | Required claims, kiểu dữ liệu, miền giá trị |
| Authorization | Chủ thể có quyền làm việc này trên tài nguyên này không? | Scope, entitlement, tenant, ownership, policy |

Một token chỉ được chấp nhận khi các điều kiện bắt buộc theo profile và chính sách của API đều đạt. Không được xem một kết quả signature verification thành công là kết luận cuối cùng.

## 4. Chọn thuật toán và khóa xác minh theo cấu hình tin cậy

### 4.1. Không để header tự quyết định chính sách thuật toán

JOSE header chứa tham số alg để chỉ thuật toán được dùng. Header nằm trong token đầu vào, nên trước khi xác minh chữ ký, nó là dữ liệu chưa đáng tin cậy.

Resource server phải cấu hình trước danh sách thuật toán được phép cho issuer và loại token đang xử lý. Khi đọc alg, server chỉ chấp nhận giá trị nằm trong allowlist và tương thích với loại khóa đã cấu hình.

Ví dụ, nếu profile chỉ cho phép RS256, token khai báo alg=none hoặc một thuật toán khác phải bị từ chối. Không tự động chấp nhận mọi thuật toán mà thư viện có thể hỗ trợ.

Không để cùng một luồng xác minh diễn giải khóa RSA công khai như khóa HMAC bí mật hoặc ngược lại. Lỗi nhầm lẫn thuật toán/khóa có thể khiến kẻ tấn công tạo chữ ký mà verifier chấp nhận theo cách ngoài dự kiến.

### 4.2. Khóa phải được ràng buộc với issuer

Xác minh chữ ký bằng một khóa bất kỳ không đủ để kết luận token đến từ issuer mong đợi. Resource server cần biết khóa nào được phép xác minh token của issuer nào.

Với chữ ký bất đối xứng:

- Issuer giữ khóa riêng để ký.
- Resource server dùng khóa công khai tương ứng để xác minh.
- Khóa công khai phải được lấy từ nguồn tin cậy đã gắn với issuer, chẳng hạn cấu hình/JWKS endpoint được đăng ký trước.
- Chính sách phải kiểm tra mục đích sử dụng khóa, thuật toán tương thích và trạng thái khóa.

Với HMAC, bên ký và bên xác minh cùng giữ bí mật. Bất kỳ thành phần nào có secret đều có khả năng tạo chữ ký hợp lệ. Vì vậy, chia sẻ một HMAC secret cho nhiều API làm mở rộng phạm vi các bên có thể phát hành token. Cần cân nhắc mô hình tin cậy và phạm vi ảnh hưởng trước khi chọn.

### 4.3. kid chỉ là gợi ý tìm khóa

kid thường giúp chọn một khóa trong tập khóa của issuer, đặc biệt khi xoay khóa. Nhưng kid nằm trong header chưa được xác minh; không được coi nó là bằng chứng khóa thuộc issuer.

Quy tắc an toàn:

- Chỉ tìm kid trong tập khóa đã gắn với issuer được cấu hình.
- Không lấy khóa từ URL tùy ý trong token như jku hoặc x5u.
- Không tự tin một khóa chỉ vì nó có kid trùng với giá trị trong token.
- Nếu không tìm được khóa hợp lệ hoặc khóa không phù hợp thuật toán/profile, từ chối token.
- Có quy trình cache và cập nhật JWKS để hỗ trợ key rotation nhưng không chấp nhận khóa ngoài nguồn tin cậy.

Nếu hệ thống nhận token từ nhiều issuer, không dùng chung một kho khóa không phân biệt nguồn. Phải ràng buộc issuer, khóa và token profile trong cấu hình.

## 5. Xác minh issuer và audience sau khi kiểm tra chữ ký

### 5.1. iss — token đến từ issuer nào?

Claim iss xác định bên phát hành theo hợp đồng JWT. Consumer phải so khớp nó với issuer được phép phát hành token cho API.

Không chỉ kiểm tra iss có tồn tại hoặc là chuỗi không rỗng. Ví dụ, API đơn hàng chỉ tin https://identity.example.org; token có iss là https://unknown.example.net phải bị từ chối dù chữ ký có thể hợp lệ dưới một khóa nào đó.

Khi có nhiều issuer, mỗi issuer cần tập khóa, thuật toán và profile được cấu hình rõ. Có thể dùng giá trị iss chưa xác minh như một chỉ mục để tra trong danh sách issuer cố định, nhưng không được tạo niềm tin động hoặc tải khóa từ một địa chỉ bất kỳ chỉ vì token nêu ra issuer đó. Sau xác minh chữ ký, vẫn phải kiểm tra iss chính xác theo cấu hình.

### 5.2. aud — token dành cho ai?

Claim aud xác định bên nhận dự kiến. Resource server phải xác nhận định danh của chính nó nằm trong audience được phép theo profile.

Ví dụ:

~~~json
{
  "iss": "https://identity.example.org",
  "sub": "user_42",
  "aud": "https://api.profile.example.org",
  "exp": 1893456900
}
~~~

Token trên dành cho API hồ sơ. API thanh toán không được chấp nhận nó chỉ vì chữ ký hợp lệ và issuer được tin cậy. Token phải có audience phù hợp với API thanh toán.

Theo RFC 7519, aud có thể là một chuỗi hoặc một mảng chuỗi. Consumer phải kiểm tra đúng dạng và ngữ nghĩa của profile, đồng thời so khớp audience chính xác; không dùng phép so khớp chuỗi con hoặc tiền tố lỏng lẻo.

### 5.3. Vì sao iss và aud phải đi cùng nhau?

Issuer đáng tin cậy có thể phát hành nhiều loại token cho nhiều dịch vụ. Một token từ issuer hợp lệ nhưng dành cho dịch vụ khác vẫn không hợp lệ tại API hiện tại. Ngược lại, token có aud trùng API nhưng do issuer không được tin cậy phát hành cũng phải bị từ chối.

Hãy kiểm tra đồng thời:

- Issuer có được phép phát hành token cho profile này không?
- Audience có đúng resource server đang xử lý không?
- Tổ hợp issuer + audience có được cấu hình và cho phép không?

## 6. Xác nhận đúng loại token và mục đích sử dụng

### 6.1. Tránh token substitution và cross-JWT confusion

Một token có thể được ký đúng nhưng được phát hành cho mục đích khác. Nếu một API chấp nhận nhầm token loại khác, đây là lỗi **token substitution** hoặc **cross-JWT confusion**.

Ví dụ:

- Dùng ID token của OpenID Connect làm access token để gọi API.
- Dùng access token dành cho API hồ sơ tại API thanh toán.
- Dùng token dành cho một loại thao tác như token ủy quyền giao dịch ở endpoint thông thường.
- Dùng token từ issuer khác nhưng có claim names trùng nhau.

Chữ ký hợp lệ không loại bỏ các nhầm lẫn này. Consumer phải biết trước loại token mà endpoint chấp nhận và kiểm tra token theo đúng profile.

### 6.2. Dùng typ và các dấu hiệu profile đúng cách

JOSE header có thể chứa typ để biểu thị loại nội dung. Ví dụ, RFC 9068 quy định JWT access token có thể dùng media type at+jwt để phân biệt với JWT dùng mục đích khác.

typ chỉ là một phần của kiểm tra loại token. Nó không thay thế xác minh chữ ký, iss, aud, thời gian hoặc claims bắt buộc. Không chấp nhận token chỉ vì typ có giá trị mong đợi.

Nếu profile quy định một loại token cụ thể, hãy kiểm tra header và các claims theo toàn bộ profile. Không dùng một bộ kiểm tra chung quá rộng cho access token, ID token, refresh token hoặc token nội bộ có mục đích khác nhau.

### 6.3. Không chấp nhận unsecured JWT trong profile yêu cầu chữ ký

JWS định nghĩa thuật toán none cho chữ ký không bảo vệ. Một profile yêu cầu token được ký phải từ chối token alg=none và mọi dạng token không có cơ chế bảo vệ được cấu hình. Không hạ cấp từ chữ ký sang không chữ ký chỉ vì token hoặc client yêu cầu.

## 7. Kiểm tra thời gian và vòng đời token

Chữ ký có thể vẫn hợp lệ sau khi token hết hạn. Vì vậy, xác minh chữ ký không thay thế kiểm tra thời gian.

| Claim | Ý nghĩa | Kiểm tra thường cần |
| --- | --- | --- |
| exp | Thời điểm hết hạn | Từ chối khi thời điểm hiện tại đã đến hoặc vượt quá exp, theo quy tắc clock skew của profile |
| nbf | Thời điểm bắt đầu có hiệu lực | Không chấp nhận trước thời điểm nbf, tính đến clock skew được phép |
| iat | Thời điểm phát hành | Kiểm tra hợp lý, không ở tương lai vượt giới hạn; áp dụng max token age nếu profile yêu cầu |
| jti | Định danh JWT | Có thể dùng cho audit, thu hồi hoặc chống phát lại khi có cơ chế theo dõi tương ứng |

iat không tự định nghĩa thời hạn token. jti có mặt cũng không tự làm token chỉ dùng một lần; resource server cần lưu trạng thái hoặc cơ chế chống replay phù hợp nếu muốn thực thi điều đó.

Các thời điểm exp, nbf, iat dùng NumericDate theo RFC 7519, tức số giây từ Unix epoch. Không diễn giải chúng như chuỗi ngày giờ hoặc số mili giây nếu profile không quy định chuyển đổi riêng.

Clock skew nên nhỏ và được cấu hình rõ. Nếu cho phép sai lệch quá lớn, token hết hạn có thể tiếp tục được chấp nhận lâu hơn dự kiến.

## 8. Kiểm tra schema và ngữ nghĩa claims

Sau khi token vượt qua các kiểm tra mật mã và ngữ cảnh cơ bản, consumer cần xác nhận Claims Set đáp ứng hợp đồng:

- Có đủ required claims theo token profile và API.
- Kiểu dữ liệu JSON chính xác; không ép kiểu tùy tiện.
- Giá trị nằm trong miền hợp lệ, đúng định dạng và giới hạn kích thước.
- Không có tên claim trùng theo quy tắc parser an toàn.
- Claims tùy biến được hiểu theo đúng issuer và profile.
- Các quan hệ giữa claims nhất quán, ví dụ ngữ cảnh tenant và resource.

Ví dụ token có chữ ký hợp lệ nhưng exp là chuỗi:

~~~json
{
  "iss": "https://identity.example.org",
  "sub": "user_42",
  "aud": "https://api.orders.example.org",
  "exp": "1893456900",
  "tenant_id": "tenant_17"
}
~~~

Nếu profile yêu cầu NumericDate, exp phải là JSON number. Chuỗi chứa chữ số không tương đương với số. Consumer không nên tự ép kiểu để biến token sai schema thành hợp lệ.

Claims tùy biến như tenant_id, roles hoặc permissions cần hợp đồng định nghĩa nguồn phát hành, kiểu, ý nghĩa và phạm vi. Tên claim trông có vẻ quen thuộc không tự chứng minh nó có cùng ngữ nghĩa giữa các issuer.

## 9. Authorization: token hợp lệ vẫn có thể không được phép thực hiện hành động

Xác thực token trả lời liệu request có mang một token được chấp nhận cho API hay không. Authorization trả lời chủ thể có được phép thực hiện hành động cụ thể trên tài nguyên cụ thể không.

Giả sử token hợp lệ có:

~~~json
{
  "iss": "https://identity.example.org",
  "sub": "user_42",
  "aud": "https://api.orders.example.org",
  "exp": 1893456900,
  "tenant_id": "tenant_17",
  "scope": "orders:read"
}
~~~

Token có thể được chấp nhận cho API đơn hàng. Nhưng nếu người dùng gọi:

~~~text
GET /orders/order_999
~~~

API vẫn cần kiểm tra:

1. Scope có cho phép thao tác đọc đơn hàng không?
2. Đơn hàng có thuộc tenant_17 không?
3. Người dùng có quyền xem đơn hàng cụ thể theo quan hệ sở hữu/chia sẻ không?
4. Đơn hàng có đang ở trạng thái cho phép đọc không?
5. Có chính sách bổ sung nào áp dụng cho tài nguyên này không?

Nếu đơn hàng thuộc tenant khác, yêu cầu phải bị từ chối dù chữ ký, issuer, audience và thời gian đều hợp lệ.

Không đồng nhất scope với quyền trên mọi tài nguyên. Scope thường giới hạn loại thao tác ở mức API; authorization theo đối tượng còn cần kiểm tra quan hệ và trạng thái tài nguyên.

## 10. Quy trình xác minh tổng thể

Một quy trình thực tế có thể tổ chức theo luồng sau:

~~~text
Nhận JWT
   |
   v
Kiểm tra cấu trúc, kích thước và dạng token được hỗ trợ
   |
   v
Xác định profile/issuer dự kiến từ cấu hình tin cậy
   |
   v
Đọc header chưa tin cậy để tra cứu trong allowlist
   |
   +--> alg có được phép?
   +--> kid có thuộc tập khóa của issuer?
   +--> key type/use có phù hợp?
   |
   v
Xác minh chữ ký JWS
   |
   v
Kiểm tra iss và aud chính xác
   |
   v
Kiểm tra typ / token profile / mục đích
   |
   v
Kiểm tra exp, nbf, iat và trạng thái token nếu cần
   |
   v
Kiểm tra schema và ngữ nghĩa claims
   |
   v
Kiểm tra scope, tenant, quyền trên tài nguyên
   |
   v
Chấp nhận request hoặc từ chối
~~~

Thứ tự triển khai chi tiết có thể khác tùy thư viện và profile. Một số thông tin header cần đọc trước để chọn khóa/thuật toán, nhưng chúng vẫn là dữ liệu chưa tin cậy và không được phép tự mở rộng chính sách. Claims payload không được dùng để cấp quyền trước khi chữ ký và các ràng buộc token đã được xác minh.

## 11. Ví dụ: cùng chữ ký hợp lệ nhưng kết quả chấp nhận khác nhau

Giả sử issuer https://identity.example.org phát hành token access cho hai API:

- API hồ sơ: https://api.profile.example.org
- API đơn hàng: https://api.orders.example.org

Token A:

~~~json
{
  "iss": "https://identity.example.org",
  "sub": "user_42",
  "aud": "https://api.profile.example.org",
  "exp": 1893456900,
  "scope": "profile:read"
}
~~~

Token B:

~~~json
{
  "iss": "https://identity.example.org",
  "sub": "user_42",
  "aud": "https://api.orders.example.org",
  "exp": 1893456900,
  "scope": "orders:read"
}
~~~

Giả sử cả hai token đều có chữ ký hợp lệ bằng khóa của issuer và còn hạn:

| Nơi nhận | Token A | Token B |
| --- | --- | --- |
| API hồ sơ | Có thể chấp nhận nếu các kiểm tra khác đạt | Từ chối vì sai audience |
| API đơn hàng | Từ chối vì sai audience | Có thể chấp nhận nếu các kiểm tra khác đạt |

Hai token đều có chữ ký hợp lệ. Sự khác biệt nằm ở ngữ cảnh sử dụng: audience và scope. Nếu API chỉ kiểm tra chữ ký mà bỏ qua aud, token A có thể bị dùng sai tại API đơn hàng.

## 12. Chứng minh bên giữ token và sender-constrained token

JWT bearer token thường có thể được sử dụng bởi bất kỳ bên nào nắm giữ token. Chữ ký hợp lệ không chứng minh request hiện tại được gửi bởi đúng client ban đầu đã nhận token.

Trong một số kiến trúc, cần ràng buộc token với bằng chứng sở hữu khóa hoặc chứng thư của bên gửi (*sender-constrained token*). Ví dụ:

- **Mutual TLS (mTLS) certificate-bound access token:** token được ràng buộc với chứng thư client; resource server kiểm tra kết nối TLS và claim ràng buộc theo profile.
- **Demonstrating Proof of Possession (DPoP):** client gửi proof được ký bằng khóa riêng tương ứng; resource server kiểm tra proof, token binding và các ràng buộc như method/URI theo đặc tả.

Những cơ chế này bổ sung bằng chứng về bên gửi request. Chúng không thay thế xác minh chữ ký token, issuer, audience, thời gian hoặc authorization trên tài nguyên.

Nếu hệ thống không sử dụng sender constraint, hãy hiểu rõ rủi ro bearer token bị đánh cắp và giới hạn thời hạn, phạm vi, nơi lưu trữ và cách truyền token phù hợp.

## 13. Các tình huống phải từ chối dù chữ ký hợp lệ

| Tình huống | Lý do từ chối |
| --- | --- |
| Khóa xác minh không thuộc issuer được tin cậy | Không xác lập được nguồn phát hành hợp lệ |
| alg không nằm trong allowlist | Vi phạm chính sách thuật toán |
| iss không đúng issuer được cấu hình | Sai nguồn phát hành |
| aud không chứa API hiện tại | Token dành cho resource khác |
| Token là ID token nhưng endpoint yêu cầu access token | Sai loại token/mục đích |
| exp đã qua | Token hết hạn |
| Chưa đến nbf | Token chưa có hiệu lực |
| Thiếu claim bắt buộc theo profile | Không đáp ứng hợp đồng |
| Claim sai kiểu hoặc ngữ nghĩa | Claims Set không hợp lệ |
| Scope không cho phép thao tác | Không có quyền ở mức chức năng |
| Tài nguyên thuộc tenant khác | Không có quyền trên tài nguyên |
| Trạng thái tài khoản hoặc entitlement đã bị thu hồi | Không còn đáp ứng chính sách hiện hành |
| Sender constraint không khớp | Request không chứng minh được quyền sở hữu token |

Các tình huống trên cho thấy chữ ký là một lớp bảo vệ trong quy trình, không phải giấy phép sử dụng token ở mọi nơi.

## 14. Kiểm thử validation theo nhiều lớp

Nên kiểm thử riêng từng điều kiện và kết quả tổng thể:

| Trường hợp kiểm thử | Chữ ký | Ngữ cảnh/claims | Kết quả |
| --- | --- | --- | --- |
| Token đúng issuer, audience, profile, còn hạn | Hợp lệ | Hợp lệ | Có thể tiếp tục authorization |
| Payload bị sửa sau khi ký | Không hợp lệ | Không cần xét | Từ chối |
| Chữ ký hợp lệ dưới khóa không được tin | Có thể hợp lệ về toán học | Sai nguồn | Từ chối |
| Chữ ký hợp lệ, sai audience | Hợp lệ | Sai audience | Từ chối |
| Chữ ký hợp lệ, token sai loại | Hợp lệ | Sai profile | Từ chối |
| Chữ ký hợp lệ, token hết hạn | Hợp lệ | Sai thời gian | Từ chối |
| Chữ ký hợp lệ, thiếu claim required | Hợp lệ | Sai schema | Từ chối |
| Chữ ký hợp lệ, scope thiếu quyền | Hợp lệ | Không đủ quyền | Từ chối thao tác |
| Chữ ký hợp lệ, tài nguyên ngoài tenant | Hợp lệ | Sai quyền tài nguyên | Từ chối thao tác |
| Token bearer bị dùng từ client khác khi yêu cầu sender constraint | Hợp lệ | Proof/binding không khớp | Từ chối |

Ngoài các trường hợp đơn lẻ, cần kiểm thử token substitution giữa issuer, audience và loại token; kiểm thử key rotation; kiểm thử kid không tồn tại; kiểm thử alg không được hỗ trợ; và kiểm thử cấu hình JWKS lỗi hoặc không khả dụng.

## 15. Những lỗi triển khai thường gặp

| Lỗi | Hậu quả | Cách phòng tránh |
| --- | --- | --- |
| Chỉ gọi hàm verify signature rồi chấp nhận | Token sai audience, hết hạn hoặc sai loại vẫn được dùng | Xây dựng validation theo token profile |
| Tin alg trong header | Có thể chấp nhận thuật toán yếu hoặc nhầm loại khóa | Allowlist thuật toán từ cấu hình |
| Dùng một tập khóa cho mọi issuer | Khóa đúng nhưng nguồn bị gán nhầm | Ràng buộc khóa với issuer |
| Tải jku/x5u tùy ý từ token | Có nguy cơ tin khóa do bên gửi kiểm soát | Dùng nguồn khóa đã cấu hình |
| Bỏ qua aud | Token của API khác bị sử dụng | Kiểm tra audience chính xác |
| Không phân biệt access token và ID token | Cross-JWT confusion | Kiểm tra loại token và profile |
| Chỉ kiểm tra iat mà không kiểm tra exp | Token có thể được dùng quá hạn | Kiểm tra đầy đủ vòng đời |
| Xem jti tự động chống replay | Token có thể được phát lại | Có kho trạng thái/cơ chế replay protection |
| Coi scope là quyền trên mọi tài nguyên | Truy cập chéo tenant hoặc đối tượng | Authorization theo tài nguyên |
| Tin chữ ký là claim đúng nghiệp vụ | Issuer ký nhầm hoặc cấp quyền quá mức vẫn được chấp nhận | Kiểm soát quy trình phát hành và nguồn claims |

## 16. Ghi nhớ

Chữ ký JWS hợp lệ chứng minh dữ liệu đã ký không bị thay đổi và chữ ký khớp với khóa xác minh đang dùng. Để kết luận token có thể được sử dụng, resource server còn phải xác lập khóa thuộc issuer tin cậy, kiểm tra thuật toán, loại token, audience, thời gian, schema và ngữ nghĩa claims.

Ngay cả khi token vượt qua toàn bộ validation, API vẫn phải áp dụng authorization cho hành động và tài nguyên cụ thể. Với bearer token, chữ ký cũng không chứng minh người gửi request hiện tại là đúng chủ thể; nếu cần, dùng cơ chế sender constraint như mTLS hoặc DPoP.

**Đừng dừng ở câu hỏi “chữ ký có đúng không?”. Hãy xác định token có được phát hành bởi bên mình tin cậy, dành cho đúng API, đúng mục đích, còn hiệu lực và đủ quyền cho hành động hiện tại hay không.**

## Tài liệu tham khảo

- [RFC 7515 — JSON Web Signature (JWS)](https://www.rfc-editor.org/rfc/rfc7515): signing input, protected header và quy trình xác minh chữ ký JWS.
- [RFC 7519 — JSON Web Token (JWT)](https://www.rfc-editor.org/rfc/rfc7519): Claims Set, iss, sub, aud, exp, nbf, iat, jti và NumericDate.
- [RFC 8725 — JSON Web Token Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725): kiểm tra thuật toán, issuer/audience, loại token và phòng tránh cross-JWT confusion.
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068): hồ sơ access token JWT và nhận diện loại token bằng typ.
- [RFC 8705 — OAuth 2.0 Mutual-TLS Client Authentication and Certificate-Bound Access Tokens](https://www.rfc-editor.org/rfc/rfc8705): ràng buộc access token với chứng thư client.
- [RFC 9449 — OAuth 2.0 Demonstrating Proof of Possession (DPoP)](https://www.rfc-editor.org/rfc/rfc9449): cơ chế proof-of-possession cho access token.
