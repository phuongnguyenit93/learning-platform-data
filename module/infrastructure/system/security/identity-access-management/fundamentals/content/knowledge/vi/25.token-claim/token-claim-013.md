# Claim validation

Claim validation là quá trình kiểm tra những phát biểu trong token có đáp ứng hợp đồng mà bên nhận chấp nhận hay không. Token có chữ ký hợp lệ vẫn có thể dành cho API khác, đến từ issuer không được tin cậy trong ngữ cảnh này, đã hết hạn hoặc thiếu thông tin cần cho quyết định truy cập.

Trong hệ thống IAM, việc xác minh phải trả lời đủ ba câu hỏi: dữ liệu được bảo vệ bởi bên nào, token có đúng mục đích sử dụng không, và các claim có phù hợp với yêu cầu đang xử lý không. Bài học lấy signed JWT access token làm ví dụ chính, đồng thời phân biệt với ID token và opaque token.

## 1. Đọc được claim chưa có nghĩa là tin được claim

Một ứng dụng có thể base64url-decode payload JWT và đọc được:

```json
{
  "iss": "https://identity.example.org",
  "sub": "user-42",
  "aud": "https://api.training.example.org",
  "roles": ["training.tenant-admin"]
}
```

Đây chỉ là dữ liệu minh họa, không phải token hoàn chỉnh hay bằng chứng người dùng có quyền quản trị. Trước khi dùng role, API cần xác minh cơ chế bảo vệ token và toàn bộ điều kiện của hợp đồng được hỗ trợ.

Phân biệt các lớp xử lý:

| Lớp | Câu hỏi chính |
|---|---|
| Parse | Token có đúng cấu trúc mà hệ thống hỗ trợ không? |
| Xác minh mật mã | Chữ ký có hợp lệ với thuật toán và khóa được tin cậy không? |
| Kiểm tra claim | Issuer, audience, thời hạn, kiểu dữ liệu và các ràng buộc có đúng không? |
| Phân quyền | Chủ thể được thực hiện thao tác này trên tài nguyên này không? |

Một lớp thành công không thay thế các lớp còn lại. Đặc biệt, chữ ký hợp lệ không chứng minh người gọi được đọc mọi dữ liệu của ứng dụng.

## 2. Xác định profile trước khi kiểm tra

Không nên có một hàm “chấp nhận mọi JWT” dùng chung cho mọi mục đích. Trước hết cần xác định API nhận loại token nào, từ những issuer nào và theo profile nào.

[RFC 7519](https://www.rfc-editor.org/rfc/rfc7519.html#section-4.1) định nghĩa các registered claim nhưng không bắt buộc mọi JWT phải có tất cả chúng. Profile ứng dụng có thể đặt yêu cầu chặt hơn. Chẳng hạn, [RFC 9068](https://www.rfc-editor.org/rfc/rfc9068.html#section-2) yêu cầu JWT access token theo profile này có `iss`, `exp`, `aud`, `sub`, `client_id`, `iat`, `jti`, được ký và nhận diện loại bằng `typ` phù hợp; không dùng thuật toán `none`.

Đội phát triển cần công bố hợp đồng như sau:

```text
Loại được nhận: JWT access token theo profile đã thống nhất
Issuer: giá trị chính xác trong cấu hình kết nối tin cậy
Audience: định danh của API đào tạo
Thuật toán/khóa: tập được cấu hình cho issuer này
Claim bắt buộc: theo profile và yêu cầu ứng dụng
Claim riêng: tenant_id có kiểu và ý nghĩa được định nghĩa
Chính sách quyền: scope, role và quan hệ với tài nguyên
```

Ví dụ trên là danh sách cấu hình cần quyết định, không phải cấu hình thực thi hoàn chỉnh. Nếu một issuer dùng profile khác RFC 9068, phải kiểm tra theo hợp đồng đã hỗ trợ rõ ràng; không tự chuyển profile sau khi token thất bại để cố chấp nhận nó.

## 3. Gắn claim với nguồn tin cậy

Trước khi tiêu thụ claim để cấp quyền, lớp xác minh cần ràng buộc thuật toán, khóa và issuer. Không tin một khóa chỉ vì token gửi kèm nó hoặc cho biết một URL tải khóa. Header `alg` và `kid` là dữ liệu nhận vào, không phải quyền tự thay cấu hình bảo mật.

[RFC 8725](https://www.rfc-editor.org/rfc/rfc8725.html#section-3) hướng dẫn xác minh thuật toán, nguồn khóa, issuer/audience và dùng quy tắc riêng để tránh nhầm lẫn giữa các loại JWT. Các URL như `jku` hoặc `x5u` không được tự động trở thành nguồn tin cậy chỉ vì xuất hiện trong token.

Trong hệ thống nhiều issuer, ứng dụng có thể đọc một giá trị chưa được xác minh để định tuyến đến tập cấu hình cho phép. Tuy nhiên, đó chỉ là bước chọn ứng viên: trước khi cấp quyền vẫn phải xác minh chữ ký và issuer theo cấu hình được chọn.

Ví dụ lỗi thiết kế: API đào tạo chấp nhận mọi JWT có chữ ký hợp lệ với bất kỳ public key nào tìm được trên Internet. Người gửi có thể tự tạo issuer và token của họ. Cần một quan hệ tin cậy đã cấu hình, không chỉ một phép tính chữ ký đúng.

## 4. Kiểm tra schema và giá trị claim

Các claim phổ biến có vai trò khác nhau:

| Claim | Ý nghĩa | Điều cần đối chiếu |
|---|---|---|
| `iss` | Bên phát hành | Issuer được cấu hình |
| `sub` | Chủ thể | Namespace và kiểu chủ thể |
| `aud` | Bên nhận dự kiến | Định danh API hoặc client tương ứng |
| `exp` | Hết hạn | Thời gian hiện tại |
| `nbf` | Chưa được dùng trước mốc này | Thời gian hiện tại |
| `iat` | Thời điểm phát hành | Chính sách tuổi token nếu có |
| `jti` | Định danh token | Chính sách theo dõi hoặc chống replay nếu có |

Theo RFC 7519, `aud` có thể là một chuỗi hoặc mảng chuỗi; các mốc thời gian trên dùng NumericDate, tức số giây theo quy ước Unix. Không tự diễn giải milliseconds thành seconds. Xem [RFC 7519, mục 2 và 4.1](https://www.rfc-editor.org/rfc/rfc7519.html).

Đối với hợp đồng cụ thể, cần kiểm tra cả kiểu dữ liệu và sự hiện diện. Ví dụ, ứng dụng minh họa quy định `roles` là mảng chuỗi, `scope` là chuỗi scope phân cách bằng dấu cách, `tenant_id` là chuỗi không rỗng. Không tự đổi một object thành chuỗi rồi so sánh role, hoặc coi `null` là giá trị mặc định có đặc quyền.

Một chính sách parser chặt có thể từ chối JSON có tên claim trùng nhau để tránh các thành phần diễn giải khác nhau. Đây là lựa chọn cần thống nhất trong triển khai; không để gateway đọc một giá trị `aud` còn API đọc giá trị khác của cùng thông điệp.

Claim không được nhận biết không tự tạo ra quyền mới. Ngược lại, claim bắt buộc bị thiếu phải làm kiểm tra thất bại; không tự điền `exp` bằng một thời điểm mới để token hết hạn hoặc thiếu hạn trở thành hợp lệ.

## 5. Issuer, subject và audience phải đúng ngữ cảnh

### Issuer

Đối chiếu issuer theo quy tắc của profile và cấu hình đã tin cậy. Không dùng kiểm tra chứa chuỗi, hậu tố tên miền hay tự sửa dấu `/` để chấp nhận một issuer khác giá trị đã thống nhất.

Ví dụ, điều kiện `iss.contains("identity.example.org")` không phải cách xác nhận issuer. Ứng dụng cần kiểm tra chính xác định danh mong đợi và ràng buộc khóa xác minh với issuer đó.

### Subject

`sub: "user-42"` từ issuer A không mặc nhiên là cùng người với `sub: "user-42"` từ issuer B. Hệ thống nên ánh xạ chủ thể trong namespace của kết nối/issuer theo hợp đồng, không dùng chuỗi `sub` trần để gộp mọi danh tính.

Ngoài ra, subject có thể biểu diễn workload trong một số grant. Không suy ra mọi token có `sub` đều đại diện một người đã đăng nhập tương tác.

### Audience

Nếu API đào tạo yêu cầu audience `https://api.training.example.org`, token chỉ dành cho API báo cáo không đáp ứng yêu cầu dù cùng issuer và còn hạn.

Ví dụ cách đối chiếu logic cho hợp đồng minh họa:

```text
audiences = readAudienceAsStringOrStringArray(claims)
require audiences.containsExact(TRAINING_API_AUDIENCE)
```

Không so khớp theo tiền tố URL hoặc lấy role `admin` làm lý do bỏ qua audience. Nếu profile còn ràng buộc tập audience hoặc yêu cầu khác, áp dụng đầy đủ những điều kiện đó.

## 6. Thời hạn, clock skew và tuổi token

Ví dụ payload rút gọn có các mốc thời gian giả định:

```json
{
  "iat": 1799999940,
  "nbf": 1799999970,
  "exp": 1800000300
}
```

Giả sử đồng hồ kiểm tra có giá trị `1800000000`. Token đã qua mốc `nbf` và chưa đến `exp`. Những số trên phục vụ phép tính minh họa, không phải thời gian của một phiên thực tế.

Không có leeway, quy tắc thời gian cơ bản là:

```text
Nếu có nbf: now >= nbf
Nếu có exp: now < exp
```

Ứng dụng có thể dùng sai lệch đồng hồ nhỏ theo profile và chính sách. Phải giới hạn rõ leeway, đồng bộ thời gian và có quan sát vận hành. Không tăng leeway lên hàng giờ chỉ để che lỗi đồng hồ hoặc kéo dài quyền truy cập.

`iat` cho biết lúc phát hành; nó không tự thay thế `nbf` hay `exp`. Nếu ứng dụng yêu cầu token không được quá một độ tuổi nhất định hoặc không được phát hành quá xa trong tương lai, đó cần là quy tắc được định nghĩa và kiểm tra rõ ràng.

Tương tự, thời điểm phát hành token mới không chứng minh người dùng vừa xác thực lại. Trong luồng có refresh token, muốn yêu cầu xác thực gần đây cần dùng tín hiệu và quy tắc phù hợp, thay vì chỉ nhìn `iat`.

## 7. Claim của ID token có kiểm tra theo giao dịch đăng nhập

ID token phục vụ client xác minh kết quả xác thực, nên audience cần gắn với client đó. Nó không trở thành access token dành cho API chỉ vì có cùng dạng JWT.

Trong OpenID Connect, nếu request đã gửi `nonce`, ID token phải mang nonce tương ứng và client phải đối chiếu với giao dịch đã khởi tạo. Những yêu cầu khác về audience, authorized party, mức xác thực hoặc thời điểm xác thực phụ thuộc trường hợp áp dụng. Xem [OpenID Connect Core, mục 3.1.3.7](https://openid.net/specs/openid-connect-core-1_0.html#IDTokenValidation).

Vì vậy, client không chỉ kiểm tra “có nonce”; cần kiểm tra đúng giá trị và trạng thái giao dịch theo luồng hỗ trợ. Cũng không lấy một ID token hợp lệ của client A để xác lập phiên cho client B.

Nếu tác vụ quản trị yêu cầu xác thực gần đây hoặc mức đảm bảo cụ thể, cần đối chiếu `auth_time`, `acr`, `amr` theo chính sách đã thỏa thuận với bên xác thực. Có role quản trị không tự chứng minh MFA hoặc đáp ứng yêu cầu tăng cường xác thực.

## 8. Scope, role và tenant cần được diễn giải theo hợp đồng

Sau khi xác minh token, các claim phân quyền vẫn cần kiểm tra tại đúng thao tác. Xét ví dụ ứng dụng đào tạo:

```text
require tokenIsValidForTrainingApi
require scopes.containsExact("courses:write")
require recognizedRoles.contains("training.instructor")
require subjectIsAssignedTo(course)
require principalTenant == course.tenantId
```

Đây là một chính sách minh họa. Không có quy tắc chung rằng mọi ứng dụng phải kiểm tra đúng tập điều kiện trên.

Những lỗi diễn giải cần tránh:

- Dùng tìm chuỗi con `read` thay cho kiểm tra đúng phần tử scope.
- Coi `admin` từ mọi issuer là quyền quản trị nội bộ.
- Coi email đã xác minh là bằng chứng có quyền quản trị.
- Chỉ so tenant trong request mà không kiểm tra quan hệ với tenant của tài nguyên.
- Coi role trong token là quyền đọc hoặc sửa mọi đối tượng trong ứng dụng.

Nếu thiếu claim mà chính sách cần, không được suy luận sang một giá trị rộng quyền hơn. Có thể từ chối thao tác hoặc chuyển sang cơ chế lấy thông tin được thiết kế sẵn; không tự tin dữ liệu bổ sung do client gửi thay claim đã thiếu.

## 9. Opaque token cũng cần kiểm tra metadata

Opaque token không cung cấp payload để API tự đọc. API có thể dùng introspection từ endpoint tin cậy, với xác thực và bảo vệ đường truyền phù hợp. [RFC 7662](https://www.rfc-editor.org/rfc/rfc7662.html) định nghĩa `active` và metadata tùy chọn của phản hồi.

`active: true` chưa thay thế chính sách về scope, tài nguyên đích và điều kiện nghiệp vụ. Hợp đồng với AS cần xác định dữ liệu nào được trả về và ràng buộc tài nguyên được bảo đảm bằng cách nào. Không mặc định thiếu `aud` nghĩa token được dùng ở mọi API.

Cache metadata có thể làm API nhìn thấy trạng thái cũ sau khi token bị thu hồi. Khi phản hồi có `exp`, không cache vượt mốc đó; thời gian cache còn phải phù hợp mục tiêu thu hồi của hệ thống. Không coi timeout introspection là kết quả active và không kéo dài cache vô hạn để tiếp tục cấp quyền.

Trong cả JWT và opaque token, việc xác minh tại một thời điểm không tự bảo đảm tài khoản hoặc quyền sẽ không thay đổi sau đó. Tác vụ đặc quyền có thể cần thêm kiểm tra trạng thái theo thiết kế.

## 10. Triển khai trong ứng dụng Java

Spring Security Resource Server hỗ trợ kiểm tra JWT với `JwtDecoder` và các validator. Tài liệu mô tả kiểm tra issuer/thời gian, cấu hình audience và khả năng bổ sung `OAuth2TokenValidator`. Xem [Spring Security: JWT validation](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html).

Khi cấu hình, cần đối chiếu hành vi của phiên bản đang dùng với hợp đồng API. Không giả định chỉ bật Resource Server là đã kiểm tra mọi claim riêng, loại token, audience hoặc điều kiện tenant của ứng dụng.

Một kiến trúc phân lớp có thể gồm:

```text
Yêu cầu HTTP
  -> Bộ lọc nhận token
  -> Xác minh token và các claim của profile
  -> Chuẩn hóa principal theo hợp đồng
  -> Ánh xạ authority được nhận biết
  -> Chính sách thao tác và tài nguyên
  -> Xử lý nghiệp vụ
```

Validator phải được kết hợp đúng. Khi thêm kiểm tra tenant hoặc audience, không vô tình thay thế và làm mất kiểm tra issuer/thời hạn đang cần. Tránh nhiều thành phần tự decode token theo những quy tắc khác nhau rồi truyền kết quả chưa xác minh vào principal.

## 11. Các tình huống cần thiết kế để từ chối

Bảng sau là những ca minh họa khi xây dựng kiểm tra cho API, không phải kết quả chạy kiểm thử của một ứng dụng cụ thể:

| Tình huống | Kết quả mong đợi theo hợp đồng minh họa |
|---|---|
| Chữ ký sai hoặc thuật toán không được cho phép | Từ chối token |
| Issuer không thuộc kết nối được tin | Từ chối token |
| Token hợp lệ nhưng audience là API khác | Từ chối tại API đào tạo |
| Đã đến `exp`, không còn trong leeway cho phép | Từ chối token |
| Chưa đến `nbf` ngoài sai lệch cho phép | Chưa chấp nhận token |
| Claim bắt buộc thiếu hoặc sai kiểu | Từ chối theo profile |
| ID token được trình thay access token | Từ chối theo quy tắc loại token |
| Token hợp lệ nhưng thiếu quyền trên khóa học | Từ chối thao tác |
| Tenant của tài nguyên không thuộc phạm vi quyền | Từ chối truy cập chéo tenant |

Nhật ký nên giúp phân biệt lỗi mật mã, issuer, audience, thời gian, schema và chính sách. Phản hồi cho người gọi cần phù hợp giao thức và không lộ thông tin nhạy cảm; không ghi toàn bộ token vào log để phục vụ chẩn đoán.

## 12. Tự kiểm tra

**Token có chữ ký đúng và role admin, nhưng audience là dịch vụ khác. Có được chấp nhận không?**

Không. Quyền trong token không làm thay đổi bên nhận mà token được cấp cho.

**Token thiếu exp có luôn sai theo mọi chuẩn JWT không?**

Không có yêu cầu chung như vậy cho mọi JWT trong RFC 7519. Tuy nhiên, nếu profile API yêu cầu `exp`, chẳng hạn RFC 9068, token thiếu claim đó phải bị từ chối.

**Có jti có tự chống được việc dùng lại bearer access token không?**

Không. Định danh token chỉ là dữ liệu. Muốn dùng nó để phát hiện hoặc ngăn replay cần cơ chế lưu trạng thái và chính sách phù hợp; bearer access token thông thường có thể được dùng cho nhiều yêu cầu hợp lệ.

**Sau khi kiểm tra claim thành công, có thể bỏ kiểm tra chủ sở hữu tài nguyên không?**

Không. Claim validation xác lập ngữ cảnh đầu vào đáng tin theo hợp đồng; chính sách tài nguyên mới quyết định thao tác hiện tại có được phép hay không.

Claim validation có hiệu quả khi được gắn với một profile rõ ràng và một quan hệ tin cậy cụ thể. Hãy xác minh dữ liệu trước khi sử dụng, đối chiếu đúng mục đích của token và giữ quyết định quyền gắn với tài nguyên thực tế.
